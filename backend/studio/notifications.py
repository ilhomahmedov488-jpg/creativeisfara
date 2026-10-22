from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .errors import Unavailable
from .models import Booking, Notification
from .sms import send_sms


def dispatch_batch(limit=50):
    candidates = list(Notification.objects.filter(state='pending', due_at__lte=timezone.now())
                      .order_by('due_at').values('id', 'booking_id')[:limit])
    sent = 0
    for candidate in candidates:
        with transaction.atomic():
            # Match the booking -> notification lock order used by rescheduling.
            booking = Booking.objects.select_for_update().select_related('client').get(pk=candidate['booking_id'])
            notification = Notification.objects.select_for_update().get(pk=candidate['id'])
            if notification.state != 'pending' or notification.due_at > timezone.now():
                continue
            valid = notification.schedule_version == booking.schedule_version and booking.status != 'cancelled'
            if notification.kind == 'reminder':
                valid = valid and booking.status == 'confirmed' and booking.shoot_start is not None
                valid = valid and timezone.localdate() < timezone.localdate(booking.shoot_start)
                start = timezone.localtime(booking.shoot_start).strftime('%H:%M') if booking.shoot_start else ''
                text = f'Creative Studio: ёдрас мекунем, пагоҳ наворбардории шумо соати {start} оғоз мешавад.'
            else:
                valid = valid and booking.status == 'ready'
                text = 'Creative Studio: маводи шумо омода аст! Барои гирифтани он бо студия тамос гиред.'
            if not valid:
                notification.state = 'cancelled'
                notification.save(update_fields=['state'])
                continue
            notification.attempts += 1
            try:
                send_sms(booking.client.phone, text)
            except Unavailable:
                notification.error_code = 'provider_unavailable'
                notification.state = 'failed' if notification.attempts >= 5 else 'pending'
                notification.due_at = timezone.now() + timedelta(minutes=2 ** notification.attempts)
            else:
                notification.state = 'sent'
                notification.sent_at = timezone.now()
                notification.error_code = ''
                sent += 1
            notification.save()
    return sent
