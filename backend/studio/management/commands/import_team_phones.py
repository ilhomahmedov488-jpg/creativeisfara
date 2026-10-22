import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.exceptions import ValidationError

from studio.access import normalize_phone
from studio.models import AuditLog, PhoneBinding, TeamMember


class Command(BaseCommand):
    help = 'Import private phone bindings from a local JSON map {member_slug: phone}. Never commit that file.'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--replace', action='store_true', help='Explicitly replace existing bindings.')

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            data = json.loads(Path(options['file']).read_text())
            if not isinstance(data, dict):
                raise ValueError()
            normalized = {slug: normalize_phone(phone) for slug, phone in data.items()}
        except (OSError, ValueError, ValidationError):
            raise CommandError('Expected a JSON object with valid Tajik phone numbers.') from None
        if len(set(normalized.values())) != len(normalized):
            raise CommandError('A phone cannot belong to two members.')
        members = {m.slug: m for m in TeamMember.objects.select_for_update().order_by('pk')}
        if normalized.keys() - members.keys():
            raise CommandError('Unknown member slug.')
        for slug, phone in normalized.items():
            binding = PhoneBinding.objects.filter(member=members[slug]).first()
            if binding and binding.phone != phone and not options['replace']:
                raise CommandError('Existing bindings differ. Review the file and use --replace explicitly.')
            if PhoneBinding.objects.filter(phone=phone).exclude(member=members[slug]).exists():
                raise CommandError('A phone is already bound to another member.')
            PhoneBinding.objects.update_or_create(member=members[slug], defaults={'phone': phone})
            AuditLog.objects.create(action='binding.imported', target=str(members[slug].pk))
        self.stdout.write(self.style.SUCCESS(f'Imported {len(normalized)} binding(s); numbers were not printed.'))
