import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.test import APIClient

from . import otp, sms
from .access import is_manager, member_for, normalize_phone
from .booking import create_booking, decide_change, request_change, update_booking
from .catalog import update_prices
from .errors import Conflict, Unavailable
from .models import (Assignment, Booking, CatalogItem, ChangeRequest, DailyReservation,
                     Notification, OTPChallenge, PhoneBinding, PortfolioPost, RateBucket, TeamMember, User)
from .notifications import dispatch_batch


class StudioTests(TestCase):
    def setUp(self):
        self.client_api = APIClient()
        self.customer = User.objects.create_user('+992000000001')
        self.other = User.objects.create_user('+992000000002')
        self.manager = User.objects.create_user('+992000000003')
        self.owner = User.objects.create_user('+992000000004')
        self.staff = User.objects.create_user('+992000000005')
        self.abdu = TeamMember.objects.get(slug='abdu')
        self.ilhom = TeamMember.objects.get(slug='ilhom')
        self.amri = TeamMember.objects.get(slug='amri')
        self.photo = TeamMember.objects.get(slug='muhi')
        PhoneBinding.objects.create(member=self.abdu, phone=self.manager.phone)
        PhoneBinding.objects.create(member=self.ilhom, phone=self.owner.phone)
        PhoneBinding.objects.create(member=self.amri, phone=self.staff.phone)
        self.day = timezone.localdate() + timedelta(days=40)
        sms.outbox.clear()

    def booking(self, **overrides):
        data = {'event': 'wedding', 'package': 'standard', 'extras': [], 'date': self.day, 'client_name': 'Тестовый клиент'}
        data.update(overrides)
        return create_booking(self.customer, data)

    def crew(self, operator=None):
        return [{'member': (operator or self.amri).pk, 'duty': 'operator'}, {'member': self.photo.pk, 'duty': 'photographer'}]

    def confirm(self, booking, **overrides):
        data = {'version': booking.version, 'status': 'confirmed', 'wedding_time': time(19), 'crew': self.crew()}
        data.update(overrides)
        return update_booking(self.manager, booking.pk, data)

    def auth(self, user):
        self.client_api.force_authenticate(user=user)

    def test_seed_has_nine_members_no_helper_experience(self):
        self.assertEqual(TeamMember.objects.count(), 9)
        self.assertIsNone(TeamMember.objects.get(slug='abdul').experience)
        self.assertIsNone(TeamMember.objects.get(slug='muhammadjon').experience)

    def test_normalize_phone(self):
        self.assertEqual(normalize_phone('000 000 001'), '+992000000001')
        self.assertEqual(normalize_phone('992000000001'), '+992000000001')
        with self.assertRaises(ValidationError):
            normalize_phone('+70000000000')

    def test_both_managers_have_equal_permissions(self):
        for user in (self.manager, self.owner):
            self.auth(user)
            self.assertEqual(self.client_api.get('/api/management/bindings/').status_code, 200)
        self.assertFalse(is_manager(self.staff))

    def test_rebinding_revokes_old_session_role_and_keeps_member(self):
        self.assertEqual(member_for(self.staff), self.amri)
        self.auth(self.manager)
        result = self.client_api.put('/api/management/bindings/', {'member': self.amri.pk, 'phone': self.other.phone}, format='json')
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(member_for(self.staff))
        self.assertEqual(member_for(self.other), self.amri)
        self.auth(self.staff)
        self.assertEqual(self.client_api.patch('/api/me/profile/', {'bio_ru': 'Denied'}, format='json').status_code, 403)

    def test_binding_duplicate_rejected_without_overwrite(self):
        self.auth(self.manager)
        result = self.client_api.put('/api/management/bindings/', {'member': self.amri.pk, 'phone': self.owner.phone}, format='json')
        self.assertEqual(result.status_code, 409)
        self.assertEqual(PhoneBinding.objects.get(member=self.amri).phone, self.staff.phone)

    def test_own_binding_cannot_be_removed(self):
        self.auth(self.manager)
        self.assertEqual(self.client_api.delete(f'/api/management/bindings/{self.abdu.pk}/').status_code, 400)

    def test_public_team_does_not_expose_phones_or_access(self):
        response = self.client_api.get('/api/team/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('phone', response.data[0])
        self.assertNotIn('access', response.data[0])
        self.assertEqual(self.client_api.get('/api/management/bindings/').status_code, 403)

    def test_premium_gifts_are_not_charged(self):
        booking = self.booking(package='premium', extras=['album', 'foteha_one', 'hall_screen'])
        self.assertEqual(booking.total, Decimal('12000.00'))
        self.assertEqual(booking.quote['deposit'], '2400.00')
        self.assertEqual(len(booking.quote['lines']), 4)

    def test_premium_two_cameras_requires_agreement(self):
        with self.assertRaises(ValidationError):
            self.booking(package='premium', extras=['foteha_two'])

    def test_conflicting_foteha_and_duplicate_addons_rejected(self):
        for extras in (['foteha_one', 'foteha_two'], ['album', 'album'], ['unknown']):
            with self.assertRaises(ValidationError):
                self.booking(extras=extras)

    def test_price_edit_preserves_existing_quote(self):
        old = self.booking()
        item = CatalogItem.objects.get(code='standard')
        update_prices(self.owner, [{'code': item.code, 'price': Decimal('4500.00'), 'revision': item.revision}])
        old.refresh_from_db()
        self.assertEqual(old.total, Decimal('4000.00'))
        self.assertEqual(self.booking().total, Decimal('4500.00'))

    def test_stale_price_update_rolls_back_entire_batch(self):
        standard = CatalogItem.objects.get(code='standard')
        pro = CatalogItem.objects.get(code='pro')
        with self.assertRaises(Conflict):
            update_prices(self.manager, [{'code': standard.code, 'price': Decimal(1), 'revision': standard.revision},
                                        {'code': pro.code, 'price': Decimal(1), 'revision': 999}])
        standard.refresh_from_db()
        self.assertEqual(standard.price, Decimal('4000.00'))

    def test_client_cannot_inject_price_or_role_or_date_time(self):
        self.auth(self.customer)
        base = {'event': 'wedding', 'package': 'standard', 'date': str(self.day), 'client_name': 'Test'}
        for field, value in [('total', '1'), ('status', 'confirmed'), ('role', 'admin'), ('wedding_time', '19:00')]:
            result = self.client_api.post('/api/bookings/', {**base, field: value}, format='json')
            self.assertEqual(result.status_code, 400, field)

    def test_client_ownership_list_and_detail(self):
        booking = self.booking()
        self.auth(self.other)
        self.assertEqual(self.client_api.get(f'/api/bookings/{booking.pk}/').status_code, 404)
        self.assertEqual(self.client_api.get('/api/bookings/').data['count'], 0)
        self.auth(self.customer)
        self.assertEqual(self.client_api.get('/api/bookings/').data['count'], 1)
        self.assertEqual(self.client_api.patch(f'/api/bookings/{booking.pk}/', {'version': 1, 'status': 'cancelled'}, format='json').status_code, 403)

    def test_staff_assignment_hides_financial_and_private_details(self):
        booking = self.confirm(self.booking(client_note='Private'))
        self.auth(self.staff)
        response = self.client_api.get(f'/api/bookings/{booking.pk}/')
        self.assertEqual(response.status_code, 200)
        for key in ('total', 'quote', 'client_phone', 'client_name', 'client_note', 'paid_amount', 'admin_note'):
            self.assertNotIn(key, response.data)
        other = self.booking()
        self.assertEqual(self.client_api.get(f'/api/bookings/{other.pk}/').status_code, 404)

    def test_new_request_has_no_countdown_or_reservation(self):
        booking = self.booking()
        self.assertFalse(DailyReservation.objects.filter(booking=booking).exists())
        self.auth(self.customer)
        self.assertIsNone(self.client_api.get(f'/api/bookings/{booking.pk}/').data['countdown_seconds'])

    def test_standard_schedule_and_countdown_to_shoot_start(self):
        booking = self.confirm(self.booking())
        self.assertEqual(timezone.localtime(booking.shoot_start).time(), time(13))
        self.assertEqual(timezone.localtime(booking.shoot_end).time(), time(22))
        self.auth(self.customer)
        with patch('studio.views.timezone.now', return_value=booking.shoot_start - timedelta(seconds=10)):
            self.assertEqual(self.client_api.get(f'/api/bookings/{booking.pk}/').data['countdown_seconds'], 10)
        with patch('studio.views.timezone.now', return_value=booking.shoot_start + timedelta(seconds=10)):
            self.assertEqual(self.client_api.get(f'/api/bookings/{booking.pk}/').data['countdown_seconds'], 0)

    def test_premium_starts_at_noon_and_requires_full_crew(self):
        booking = self.booking(package='premium')
        with self.assertRaises(ValidationError):
            self.confirm(booking)
        members = list(TeamMember.objects.all()[:6])
        crew = [{'member': m.pk, 'duty': 'operator' if i < 4 else ('photographer' if i == 4 else 'reels')}
                for i, m in enumerate(members)]
        booking = self.confirm(booking, crew=crew)
        self.assertEqual(timezone.localtime(booking.shoot_start).time(), time(12))

    def test_admin_operator_can_be_reserved(self):
        booking = self.confirm(self.booking(), crew=self.crew(self.abdu))
        self.assertTrue(DailyReservation.objects.filter(booking=booking, member=self.abdu).exists())

    def test_same_person_two_bookings_conflict_and_roll_back(self):
        first = self.confirm(self.booking())
        second = self.booking()
        with self.assertRaises(Conflict):
            self.confirm(second)
        second.refresh_from_db()
        self.assertEqual(second.status, 'new')
        self.assertEqual(Assignment.objects.filter(booking=second).count(), 0)
        self.assertEqual(DailyReservation.objects.filter(booking=first).count(), 2)

    def test_multiple_weddings_same_day_with_different_crew(self):
        self.confirm(self.booking())
        crew = [{'member': self.abdu.pk, 'duty': 'operator'}, {'member': self.ilhom.pk, 'duty': 'photographer'}]
        second = self.confirm(self.booking(), crew=crew)
        self.assertEqual(second.status, 'confirmed')
        self.assertEqual(DailyReservation.objects.filter(day=self.day).count(), 4)

    def test_assignment_on_new_request_already_reserves_member(self):
        first = self.booking()
        update_booking(self.manager, first.pk, {'version': 1, 'crew': self.crew()})
        with self.assertRaises(Conflict):
            self.confirm(self.booking())

    def test_edit_does_not_conflict_with_same_booking(self):
        booking = self.confirm(self.booking())
        result = update_booking(self.manager, booking.pk, {'version': booking.version, 'admin_note': 'OK'})
        self.assertEqual(result.admin_note, 'OK')

    def test_cancel_releases_reservations_but_keeps_history(self):
        booking = self.confirm(self.booking())
        booking = update_booking(self.manager, booking.pk, {'version': booking.version, 'status': 'cancelled'})
        self.assertFalse(booking.reservations.exists())
        self.assertEqual(booking.assignments.count(), 2)
        self.confirm(self.booking())

    def test_database_enforces_one_member_per_day(self):
        first, second = self.booking(), self.booking()
        DailyReservation.objects.create(booking=first, member=self.amri, day=self.day)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DailyReservation.objects.create(booking=second, member=self.amri, day=self.day)

    def test_overnight_shoot_reserves_next_day(self):
        booking = self.confirm(self.booking(), wedding_time=time(23))
        self.assertEqual(booking.reservations.count(), 4)
        other = self.booking(date=self.day + timedelta(days=1))
        with self.assertRaises(Conflict):
            self.confirm(other)

    def test_unassign_and_date_move_free_previous_day(self):
        booking = self.booking()
        booking = update_booking(self.manager, booking.pk, {'version': 1, 'crew': self.crew()})
        booking = update_booking(self.manager, booking.pk, {'version': booking.version, 'date': self.day + timedelta(days=1)})
        self.assertFalse(DailyReservation.objects.filter(day=self.day).exists())
        update_booking(self.manager, booking.pk, {'version': booking.version, 'crew': []})
        self.assertFalse(DailyReservation.objects.exists())

    def test_stale_booking_version_rejected(self):
        booking = self.confirm(self.booking())
        with self.assertRaises(Conflict):
            update_booking(self.manager, booking.pk, {'version': 1, 'paid_amount': Decimal(800)})

    def test_payment_manual_and_custom_love_story_price(self):
        booking = self.booking(event='love_story', package='love_story')
        booking = update_booking(self.owner, booking.pk, {'version': 1, 'adjustment': Decimal(500), 'adjustment_reason': 'Индивидуальный формат'})
        self.assertEqual(booking.total, Decimal(2500))
        self.assertEqual(booking.quote['deposit'], '500.00')
        with self.assertRaises(ValidationError):
            update_booking(self.owner, booking.pk, {'version': booking.version, 'paid_amount': Decimal(3000)})

    def test_reschedule_deadline_and_single_pending_request(self):
        booking = self.booking(date=timezone.localdate() + timedelta(days=14))
        with self.assertRaises(ValidationError):
            request_change(self.customer, booking.pk, {'kind': 'reschedule', 'requested_date': self.day, 'reason': 'Test'})
        request_change(self.customer, booking.pk, {'kind': 'cancel', 'reason': 'Call me'})
        with self.assertRaises(Conflict):
            request_change(self.customer, booking.pk, {'kind': 'cancel', 'reason': 'Again'})

    def test_reschedule_conflict_keeps_old_schedule_and_request_pending(self):
        first = self.confirm(self.booking())
        second = self.confirm(self.booking(date=self.day + timedelta(days=1)))
        change = request_change(self.customer, first.pk, {'kind': 'reschedule', 'requested_date': second.date, 'reason': 'Move'})
        with self.assertRaises(Conflict):
            decide_change(self.manager, change.pk, {'version': first.version, 'approve': True})
        first.refresh_from_db(); change.refresh_from_db()
        self.assertEqual(first.date, self.day)
        self.assertEqual(change.state, 'pending')
        self.assertTrue(first.reservations.filter(day=self.day).exists())

    def test_approved_reschedule_replaces_crew_and_cancels_old_reminder(self):
        first = self.confirm(self.booking())
        self.confirm(self.booking(date=self.day + timedelta(days=1)))
        change = request_change(self.customer, first.pk, {'kind': 'reschedule', 'requested_date': self.day + timedelta(days=1), 'reason': 'Move'})
        crew = [{'member': self.abdu.pk, 'duty': 'operator'}, {'member': self.ilhom.pk, 'duty': 'photographer'}]
        decide_change(self.manager, change.pk, {'version': first.version, 'approve': True, 'crew': crew})
        first.refresh_from_db()
        self.assertEqual(first.schedule_version, 3)
        self.assertEqual(Notification.objects.filter(booking=first, state='pending').count(), 1)
        self.assertFalse(first.reservations.filter(day=self.day).exists())

    def test_cancel_request_does_not_auto_cancel(self):
        booking = self.confirm(self.booking())
        change = request_change(self.customer, booking.pk, {'kind': 'cancel', 'reason': 'Call me'})
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')
        decide_change(self.owner, change.pk, {'version': booking.version, 'approve': True, 'note': 'Обсудили по телефону'})
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')

    def test_non_wedding_reschedule_preserves_agreed_time(self):
        booking = self.booking(event='love_story', package='love_story')
        start = timezone.make_aware(datetime.combine(self.day, time(14)))
        booking = update_booking(self.manager, booking.pk, {'version': 1, 'status': 'confirmed',
            'shoot_start': start, 'shoot_end': start + timedelta(hours=2),
            'crew': [{'member': self.amri.pk, 'duty': 'operator'}]})
        new_day = self.day + timedelta(days=2)
        change = request_change(self.customer, booking.pk, {'kind': 'reschedule', 'requested_date': new_day, 'reason': 'Move'})
        decide_change(self.manager, change.pk, {'version': booking.version, 'approve': True})
        booking.refresh_from_db()
        self.assertEqual(timezone.localdate(booking.shoot_start), new_day)
        self.assertEqual(timezone.localtime(booking.shoot_start).time(), time(14))
        self.assertEqual(booking.shoot_end - booking.shoot_start, timedelta(hours=2))

    def test_individual_adjustment_is_replaced_not_added_twice(self):
        booking = self.booking()
        for _ in range(2):
            booking = update_booking(self.manager, booking.pk, {'version': booking.version,
                'adjustment': Decimal(500), 'adjustment_reason': 'Transport'})
        self.assertEqual(booking.total, Decimal(4500))
        self.assertEqual(booking.quote['deposit'], '900.00')

    def test_staff_cannot_change_prices(self):
        self.auth(self.staff)
        self.assertEqual(self.client_api.patch('/api/management/prices/', {'items': []}, format='json').status_code, 403)

    def test_profile_cannot_change_identity_or_role(self):
        self.auth(self.staff)
        self.assertEqual(self.client_api.patch('/api/me/profile/', {'access': 'owner'}, format='json').status_code, 400)
        self.assertEqual(self.client_api.patch('/api/me/profile/', {'bio_ru': 'Моя биография'}, format='json').status_code, 200)

    def test_real_sms_payload_and_provider_errors_are_sanitized(self):
        with override_settings(SMS_BACKEND='payom', PAYOM_URL='https://sms.example/api/message', PAYOM_TOKEN='private-token', PAYOM_SENDER='Creative'):
            with patch('studio.sms.requests.post', return_value=Mock(status_code=200, json=lambda: {'success': True})) as post:
                sms.send_sms(self.customer.phone, 'Text')
                self.assertEqual(post.call_args.kwargs['json']['telephone'], self.customer.phone)
                self.assertEqual(post.call_args.kwargs['json']['type'], 'SMS')
                self.assertFalse(post.call_args.kwargs['allow_redirects'])
            with patch('studio.sms.requests.post', return_value=Mock(status_code=401)):
                with self.assertRaises(Unavailable) as error:
                    sms.send_sms(self.customer.phone, 'Text')
                self.assertNotIn('private-token', str(error.exception))

    def test_sms_fails_closed_without_configuration(self):
        with override_settings(SMS_BACKEND='payom', PAYOM_URL='', PAYOM_TOKEN='', PAYOM_SENDER=''):
            with self.assertRaises(Unavailable):
                otp.request_code('+992000000009', '192.0.2.1')
        self.assertFalse(OTPChallenge.objects.filter(consumed=False).exists())

    def test_otp_one_time_and_server_assigns_role(self):
        api = APIClient(enforce_csrf_checks=True)
        token = api.get('/api/auth/csrf/').json()['csrfToken']
        api.credentials(HTTP_X_CSRFTOKEN=token)
        requested = api.post('/api/auth/request-code/', {'phone': self.staff.phone}, format='json')
        self.assertEqual(requested.status_code, 201)
        self.assertNotIn('code', requested.data)
        code = re.search(r'\d{6}', sms.outbox[-1]['text']).group()
        verified = api.post('/api/auth/verify-code/', {'challenge_id': requested.data['challenge_id'], 'code': code}, format='json')
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.data['role'], 'employee')
        self.assertTrue(api.cookies['sessionid']['httponly'])
        api.credentials(HTTP_X_CSRFTOKEN=verified.data['csrfToken'])
        replay = api.post('/api/auth/verify-code/', {'challenge_id': requested.data['challenge_id'], 'code': code}, format='json')
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(api.post('/api/auth/logout/').status_code, 204)
        self.assertEqual(api.get('/api/me/').status_code, 403)

    def test_csrf_required_for_anonymous_sms_and_verify(self):
        api = APIClient(enforce_csrf_checks=True)
        self.assertEqual(api.post('/api/auth/request-code/', {'phone': self.customer.phone}, format='json').status_code, 403)
        self.assertEqual(api.post('/api/auth/verify-code/', {}, format='json').status_code, 403)
        self.assertEqual(len(sms.outbox), 0)

    def test_otp_failed_attempts_commit_and_lock_after_five(self):
        challenge = otp.request_code(self.customer.phone, '192.0.2.1')
        code = re.search(r'\d{6}', sms.outbox[-1]['text']).group()
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(5):
            with self.assertRaises(ValidationError):
                otp.verify_code(challenge.pk, wrong, '192.0.2.1')
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts, 5)
        self.assertTrue(challenge.consumed)
        with self.assertRaises(ValidationError):
            otp.verify_code(challenge.pk, code, '192.0.2.1')

    def test_otp_expiry_and_resend_invalidates_old_code(self):
        old = otp.request_code(self.customer.phone, '192.0.2.1')
        RateBucket.objects.update(started_at=timezone.now() - timedelta(minutes=2))
        new = otp.request_code(self.customer.phone, '192.0.2.1')
        old.refresh_from_db()
        self.assertTrue(old.consumed)
        OTPChallenge.objects.filter(pk=new.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            otp.verify_code(new.pk, '000000', '192.0.2.1')

    def test_otp_cooldown(self):
        otp.request_code(self.customer.phone, '192.0.2.1')
        with self.assertRaises(Throttled):
            otp.request_code(self.customer.phone, '192.0.2.1')
        self.assertEqual(len(sms.outbox), 1)

    def test_ready_notification_once_and_retry(self):
        booking = self.confirm(self.booking())
        booking = update_booking(self.manager, booking.pk, {'version': booking.version, 'status': 'editing'})
        booking = update_booking(self.manager, booking.pk, {'version': booking.version, 'status': 'ready'})
        update_booking(self.manager, booking.pk, {'version': booking.version, 'admin_note': 'Ready'})
        self.assertEqual(Notification.objects.filter(kind='ready', booking=booking).count(), 1)
        with patch('studio.notifications.send_sms', side_effect=Unavailable()):
            self.assertEqual(dispatch_batch(), 0)
        notice = Notification.objects.get(kind='ready', booking=booking)
        self.assertEqual(notice.attempts, 1)
        self.assertEqual(notice.state, 'pending')
        Notification.objects.filter(pk=notice.pk).update(due_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(dispatch_batch(), 1)
        self.assertEqual(dispatch_batch(), 0)

    def test_day_before_reminder_and_cancelled_skip(self):
        booking = self.confirm(self.booking())
        notice = Notification.objects.get(booking=booking, kind='reminder')
        self.assertEqual(timezone.localtime(notice.due_at).time(), time(9))
        self.assertEqual(timezone.localdate(notice.due_at), self.day - timedelta(days=1))
        with patch('studio.notifications.timezone.now', return_value=notice.due_at + timedelta(minutes=1)):
            self.assertEqual(dispatch_batch(), 1)
        self.assertIn('13:00', sms.outbox[-1]['text'])

    def test_cancelled_notification_never_sends(self):
        booking = self.confirm(self.booking())
        update_booking(self.manager, booking.pk, {'version': booking.version, 'status': 'cancelled'})
        Notification.objects.filter(booking=booking).update(due_at=timezone.now() - timedelta(days=1))
        self.assertEqual(dispatch_batch(), 0)
        self.assertEqual(sms.outbox, [])

    def test_late_worker_does_not_send_tomorrow_message_on_shoot_day(self):
        booking = self.confirm(self.booking())
        with patch('studio.notifications.timezone.now', return_value=booking.shoot_start - timedelta(minutes=1)):
            self.assertEqual(dispatch_batch(), 0)

    def test_portfolio_own_video_publishes_immediately_and_owner_enforced(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            self.auth(self.staff)
            data = {'title_ru': 'Наш фильм', 'title_tg': 'Филми мо', 'event': 'wedding', 'placement': 'reels',
                    'permission_confirmed': True, 'video': SimpleUploadedFile('test.mp4', b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 20, 'video/mp4')}
            result = self.client_api.post('/api/portfolio/', data, format='multipart')
            self.assertEqual(result.status_code, 201, result.data)
            post_id = result.data['id']
            self.auth(self.owner)
            self.assertEqual(self.client_api.patch(f'/api/portfolio/{post_id}/', {'title_ru': 'Правка'}, format='json').status_code, 200)
            another = User.objects.create_user('+992000000006')
            PhoneBinding.objects.create(member=self.photo, phone=another.phone)
            self.auth(another)
            self.assertEqual(self.client_api.delete(f'/api/portfolio/{post_id}/').status_code, 403)
            self.auth(self.staff)
            self.assertEqual(self.client_api.delete(f'/api/portfolio/{post_id}/').status_code, 204)

    def test_invalid_video_or_missing_consent_rejected(self):
        self.auth(self.staff)
        data = {'title_ru': 'Test', 'title_tg': 'Test', 'event': 'wedding', 'placement': 'reels', 'permission_confirmed': True,
                'video': SimpleUploadedFile('bad.mp4', b'<script>alert(1)</script>', 'video/mp4')}
        self.assertEqual(self.client_api.post('/api/portfolio/', data, format='multipart').status_code, 400)

    def test_reviews_require_consent_and_manager(self):
        self.auth(self.manager)
        data = {'author_name': 'Test', 'text_ru': 'Text', 'text_tg': 'Text', 'published': True, 'consent': False}
        self.assertEqual(self.client_api.post('/api/reviews/', data, format='json').status_code, 400)
        self.auth(self.customer)
        self.assertEqual(self.client_api.post('/api/reviews/', data, format='json').status_code, 403)

    def test_health_and_no_store(self):
        self.assertEqual(self.client_api.get('/health/').status_code, 200)
        self.assertEqual(self.client_api.get('/api/catalog/')['Cache-Control'], 'no-store')


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL row locks; run the PostgreSQL CI job.')
class ConcurrentAssignmentTests(TransactionTestCase):
    def test_two_admins_cannot_reserve_same_operator(self):
        manager = User.objects.create_user('+992000000010', is_superuser=True)
        customer = User.objects.create_user('+992000000011')
        member = TeamMember.objects.create(slug='race', name='Test', position_ru='Test', position_tg='Test')
        day = timezone.localdate() + timedelta(days=40)
        bookings = [Booking.objects.create(client=customer, event='wedding', client_name='Test', date=day,
                    quote={'package': 'standard'}, total=4000) for _ in range(2)]
        gate = Barrier(2)

        def assign(pk):
            close_old_connections()
            try:
                actor = User.objects.get(pk=manager.pk)
                gate.wait(timeout=10)
                update_booking(actor, pk, {'version': 1, 'crew': [{'member': member.pk, 'duty': 'operator'}]})
                return 'reserved'
            except Conflict:
                return 'conflict'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(assign, [b.pk for b in bookings]))
        self.assertCountEqual(results, ['reserved', 'conflict'])
        self.assertEqual(DailyReservation.objects.count(), 1)
