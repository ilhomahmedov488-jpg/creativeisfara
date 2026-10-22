from urllib.parse import urlparse

import requests
from django.conf import settings

from .errors import Unavailable

# Used only by automated tests; messages are never logged or returned by the API.
outbox = []


def send_sms(phone, text):
    if settings.SMS_BACKEND == 'memory':
        outbox.append({'phone': phone, 'text': text})
        return
    endpoint = urlparse(settings.PAYOM_URL)
    if (endpoint.scheme != 'https' or not endpoint.hostname or endpoint.username
            or endpoint.password or endpoint.path != '/api/message'
            or not settings.PAYOM_TOKEN or not settings.PAYOM_SENDER):
        raise Unavailable()
    try:
        response = requests.post(
            settings.PAYOM_URL,
            headers={'Authorization': f'Bearer {settings.PAYOM_TOKEN}', 'Accept': 'application/json'},
            json={'telephone': phone, 'text': text, 'senderName': settings.PAYOM_SENDER, 'type': 'SMS'},
            timeout=(3, 10), allow_redirects=False,
        )
        if not 200 <= response.status_code < 300:
            raise Unavailable()
        # Payom's public docs do not specify a response schema. Reject explicit failures;
        # HTTP acceptance is not a delivery receipt. Confirm the tenant's contract at setup.
        try:
            result = response.json()
        except ValueError:
            result = None
        if isinstance(result, dict) and (result.get('success') is False or result.get('error')):
            raise Unavailable()
    except requests.RequestException:
        raise Unavailable() from None
