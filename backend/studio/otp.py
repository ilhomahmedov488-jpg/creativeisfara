import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import Throttled, ValidationError

from .access import normalize_phone
from .models import OTPChallenge, RateBucket, User
from .sms import send_sms


def digest(value):
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def consume_limit(key, limit, seconds):
    now = timezone.now()
    # get_or_create is protected by the primary key, then lock for concurrent requests.
    with transaction.atomic():
        RateBucket.objects.get_or_create(key=key, defaults={'started_at': now})
        bucket = RateBucket.objects.select_for_update().get(key=key)
        if bucket.started_at + timedelta(seconds=seconds) <= now:
            bucket.started_at, bucket.count = now, 0
        if bucket.count >= limit:
            raise Throttled(wait=max(1, int((bucket.started_at + timedelta(seconds=seconds) - now).total_seconds())))
        bucket.count += 1
        bucket.save()


def request_code(phone, ip):
    phone = normalize_phone(phone)
    consume_limit('ip:' + digest(ip), 20, 3600)
    consume_limit('cooldown:' + digest(phone), 1, 60)
    consume_limit('phone:' + digest(phone), 5, 3600)
    code = f'{secrets.randbelow(1000000):06d}'
    with transaction.atomic():
        # The per-phone rate bucket serializes creation during the cooldown.
        OTPChallenge.objects.filter(phone=phone, consumed=False).update(consumed=True)
        challenge = OTPChallenge.objects.create(
            phone=phone, digest='', expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
        )
        challenge.digest = digest(f'{challenge.pk}:{code}')
        challenge.save(update_fields=['digest'])
    try:
        send_sms(phone, f'Creative Studio: коди воридшавӣ {code}. Муҳлат: 5 дақиқа. Кодро ба касе надиҳед.')
    except Exception:
        OTPChallenge.objects.filter(pk=challenge.pk).update(consumed=True)
        raise
    return challenge


def verify_code(challenge_id, code, ip):
    consume_limit('verify:' + digest(ip), 50, 3600)
    user = None
    with transaction.atomic():
        challenge = OTPChallenge.objects.select_for_update().filter(pk=challenge_id).first()
        if (challenge and not challenge.consumed and challenge.expires_at > timezone.now()
                and challenge.attempts < settings.OTP_MAX_ATTEMPTS):
            challenge.attempts += 1
            if hmac.compare_digest(challenge.digest, digest(f'{challenge.pk}:{code}')):
                challenge.consumed = True
                user, _ = User.objects.get_or_create(phone=challenge.phone)
            if challenge.attempts >= settings.OTP_MAX_ATTEMPTS:
                challenge.consumed = True
            challenge.save(update_fields=['attempts', 'consumed'])
    # Failed-attempt increments must commit rather than roll back with the exception.
    if user is None or not user.is_active:
        raise ValidationError({'code': 'Код неверен или истёк. Запросите новый код.'})
    return user
