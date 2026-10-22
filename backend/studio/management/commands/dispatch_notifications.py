import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from studio.notifications import dispatch_batch


class Command(BaseCommand):
    help = 'Send due SMS notifications. Run one long-lived worker in production.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true')
        parser.add_argument('--interval', type=int, default=30)

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            sent = dispatch_batch()
            if sent:
                self.stdout.write(f'Sent {sent} notification(s).')
            if not options['loop']:
                break
            time.sleep(max(5, min(options['interval'], 60)))
