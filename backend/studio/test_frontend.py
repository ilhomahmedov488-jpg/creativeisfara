"""The public shell and real session/API contract used by frontend/.

SMS is replaced only by the isolated test backend; no test code is exposed by HTTP.
"""
import re
from datetime import timedelta

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from . import sms


class FrontendIntegrationTests(TestCase):
    def test_shell_resolves_local_assets_without_private_or_demo_data(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="tg"')
        self.assertContains(response, '/static/studio/app.js')
        self.assertNotContains(response, '{%')
        self.assertNotContains(response, '123456')
        self.assertNotContains(response, 'switch-role')
        for name in ('app.js', 'api.js', 'domain.js', 'i18n.js', 'styles.css', 'logo.png'):
            self.assertIsNotNone(finders.find('studio/' + name))

    def test_browser_session_can_create_and_read_own_booking_then_log_out(self):
        api = APIClient(enforce_csrf_checks=True)
        csrf = api.get('/api/auth/csrf/').json()['csrfToken']
        api.credentials(HTTP_X_CSRFTOKEN=csrf)
        sms.outbox.clear()
        challenge = api.post('/api/auth/request-code/', {'phone': '+992000000009'}, format='json')
        self.assertEqual(challenge.status_code, 201)
        self.assertNotIn('code', challenge.json())
        code = re.search(r'\d{6}', sms.outbox[-1]['text']).group()
        verified = api.post('/api/auth/verify-code/', {
            'challenge_id': challenge.json()['challenge_id'], 'code': code,
        }, format='json')
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json()['cabinet'], 'client')
        api.credentials(HTTP_X_CSRFTOKEN=verified.json()['csrfToken'])
        day = (timezone.localdate() + timedelta(days=40)).isoformat()
        created = api.post('/api/bookings/', {
            'event': 'wedding', 'package': 'premium', 'extras': ['love_story'],
            'client_name': 'Тестовый клиент', 'date': day, 'location': 'Зал', 'client_note': '',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        body = created.json()
        self.assertEqual(body['total'], '12000.00')
        self.assertEqual(body['quote']['deposit'], '2400.00')
        self.assertEqual({line['code'] for line in body['quote']['lines'] if line['included']}, {'album', 'foteha_one'})
        self.assertIsNone(body['countdown_seconds'])
        fetched = api.get('/api/bookings/' + body['id'] + '/').json()
        self.assertEqual(fetched['quote'], body['quote'])
        self.assertNotIn('client_phone', fetched)
        self.assertEqual(api.get('/api/me/').json()['cabinet'], 'client')
        self.assertEqual(api.post('/api/auth/logout/', {}, format='json').status_code, 204)
        self.assertEqual(api.get('/api/bookings/').status_code, 403)

    def test_root_never_enables_anonymous_write_access(self):
        api = APIClient(enforce_csrf_checks=True)
        self.assertEqual(api.get('/').status_code, 200)
        self.assertEqual(api.post('/api/bookings/', {}, format='json').status_code, 403)
        self.assertEqual(api.patch('/api/management/prices/', {}, format='json').status_code, 403)
