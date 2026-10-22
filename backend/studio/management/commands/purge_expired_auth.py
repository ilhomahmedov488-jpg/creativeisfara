from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from studio.models import OTPChallenge, RateBucket


class Command(BaseCommand):
    help = 'Remove expired authentication records; run daily.'

    def handle(self, *args, **options):
        OTPChallenge.objects.filter(expires_at__lt=timezone.now() - timedelta(days=1)).delete()
        RateBucket.objects.filter(started_at__lt=timezone.now() - timedelta(days=2)).delete()
        call_command('clearsessions')
        self.stdout.write('Expired authentication data removed.')
