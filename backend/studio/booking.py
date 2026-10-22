from collections import Counter
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .access import member_for, require_manager
from .catalog import quote_for
from .errors import Conflict
from .models import Assignment, AuditLog, Booking, ChangeRequest, DailyReservation, Notification, TeamMember


def validate_date(value):
    if value < timezone.localdate():
        raise ValidationError({'date': 'Нельзя выбрать прошедшую дату.'})


@transaction.atomic
def create_booking(user, data):
    if member_for(user) or user.is_superuser:
        raise ValidationError('Заявки создаются из кабинета клиента.')
    validate_date(data['date'])
    quote = quote_for(data['event'], data['package'], data.get('extras', []))
    booking = Booking.objects.create(client=user, quote=quote, total=Decimal(quote['total']),
        **{k: v for k, v in data.items() if k not in ('package', 'extras')})
    AuditLog.objects.create(actor=user, action='booking.created', target=str(booking.pk))
    return booking


def calculate_schedule(booking):
    if booking.event == 'wedding':
        if booking.wedding_time is None:
            booking.shoot_start = booking.shoot_end = None
            return
        wedding = timezone.make_aware(datetime.combine(booking.date, booking.wedding_time))
        if booking.quote['package'] == 'premium':
            booking.shoot_start = timezone.make_aware(datetime.combine(booking.date, time(12)))
            if wedding < booking.shoot_start:
                raise ValidationError({'wedding_time': 'Премиум начинается в 12:00. Согласуйте время свадьбы.'})
        else:
            booking.shoot_start = wedding - timedelta(hours=6)
        booking.shoot_end = wedding + timedelta(hours=3)
    elif booking.shoot_start:
        if timezone.localdate(booking.shoot_start) != booking.date:
            raise ValidationError({'shoot_start': 'Начало съёмки должно соответствовать дате заявки.'})
        if booking.shoot_end and booking.shoot_end <= booking.shoot_start:
            raise ValidationError({'shoot_end': 'Окончание должно быть позже начала.'})
    elif booking.shoot_end:
        raise ValidationError({'shoot_start': 'Сначала укажите начало съёмки.'})


def reservation_days(booking):
    first = timezone.localdate(booking.shoot_start) if booking.shoot_start else booking.date
    last = timezone.localdate(booking.shoot_end - timedelta(microseconds=1)) if booking.shoot_end else booking.date
    if (last - first).days > 7:
        raise ValidationError('Съёмку дольше 7 дней нужно оформить отдельными заказами.')
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def rebuild_reservations(booking, crew):
    ids = [row['member'] for row in crew]
    if len(ids) != len(set(ids)):
        raise ValidationError({'crew': 'Один участник не может занимать две позиции.'})
    # Deterministic member locks serialize overlapping crews before the unique index.
    members = list(TeamMember.objects.select_for_update().filter(pk__in=ids, active=True).order_by('pk'))
    if len(members) != len(ids):
        raise ValidationError({'crew': 'Участник не найден или неактивен.'})
    DailyReservation.objects.filter(booking=booking).delete()
    Assignment.objects.filter(booking=booking).delete()
    Assignment.objects.bulk_create([Assignment(booking=booking, member_id=c['member'], duty=c['duty']) for c in crew])
    if booking.status != Booking.Status.CANCELLED:
        days = reservation_days(booking)
        if DailyReservation.objects.filter(member_id__in=ids, day__in=days).exists():
            raise Conflict('Один из выбранных сотрудников уже занят в этот день.')
        try:
            with transaction.atomic():
                DailyReservation.objects.bulk_create([
                    DailyReservation(booking=booking, member_id=mid, day=day) for mid in ids for day in days
                ])
        except IntegrityError:
            raise Conflict('Сотрудник уже назначен на другую съёмку.') from None


def validate_crew(booking, crew):
    if booking.status not in (Booking.Status.CONFIRMED, Booking.Status.EDITING, Booking.Status.READY):
        return
    if not booking.shoot_start:
        raise ValidationError('Для подтверждения укажите начало съёмки.')
    counts = Counter(c['duty'] for c in crew)
    if booking.event == 'wedding':
        operators = {'standard': 1, 'pro': 2, 'premium': 4}[booking.quote['package']]
        needs = {'operator': operators, 'photographer': 1}
        if booking.quote['package'] == 'premium':
            needs['reels'] = 1
    elif booking.event == 'foteha':
        needs = {'operator': 2 if booking.quote['package'] == 'foteha_two' else 1}
    else:
        needs = {'operator': 1}
    if any(counts[duty] < count for duty, count in needs.items()):
        raise ValidationError({'crew': 'Назначьте команду согласно выбранному пакету.'})


def sync_notifications(booking, schedule_changed=False):
    if schedule_changed or booking.status == Booking.Status.CANCELLED:
        Notification.objects.filter(booking=booking, state='pending').update(state='cancelled')
    if booking.status == Booking.Status.CONFIRMED and booking.shoot_start:
        reminder_date = timezone.localdate(booking.shoot_start) - timedelta(days=1)
        due = timezone.make_aware(datetime.combine(reminder_date, time(settings.REMINDER_HOUR)))
        if timezone.now() < booking.shoot_start:
            Notification.objects.get_or_create(booking=booking, kind='reminder', schedule_version=booking.schedule_version,
                                              defaults={'due_at': due})
    if booking.status == Booking.Status.READY:
        Notification.objects.get_or_create(booking=booking, kind='ready', schedule_version=booking.schedule_version,
                                          defaults={'due_at': timezone.now()})


def _apply_update(actor, booking, data):
    if data['version'] != booking.version:
        raise Conflict('Заказ уже изменён. Обновите страницу.')
    before = {'status': booking.status, 'date': str(booking.date), 'paid_amount': str(booking.paid_amount), 'total': str(booking.total)}
    old_schedule = (booking.date, booking.wedding_time, booking.shoot_start, booking.shoot_end)
    old_status = booking.status
    allowed = {
        'new': {'new', 'confirmed', 'cancelled'}, 'confirmed': {'confirmed', 'editing', 'cancelled'},
        'editing': {'editing', 'ready', 'cancelled'}, 'ready': {'ready'}, 'cancelled': {'cancelled'},
    }
    status = data.get('status', booking.status)
    if status not in allowed[booking.status]:
        raise ValidationError({'status': 'Недопустимый переход статуса.'})
    if booking.status in ('cancelled', 'ready') and set(data) - {'version', 'paid_amount', 'admin_note'}:
        raise ValidationError('Завершённый заказ нельзя перепланировать.')
    if 'date' in data and data['date'] != booking.date:
        validate_date(data['date'])
        if booking.event != 'wedding' and booking.shoot_start:
            duration = booking.shoot_end - booking.shoot_start if booking.shoot_end else None
            booking.shoot_start = timezone.make_aware(datetime.combine(data['date'], timezone.localtime(booking.shoot_start).time()))
            booking.shoot_end = booking.shoot_start + duration if duration else None
    if 'package' in data or 'extras' in data:
        if booking.status != 'new':
            raise ValidationError('Состав и прайс можно менять только до подтверждения.')
        booking.quote = quote_for(booking.event, data.get('package', booking.quote['package']), data.get('extras', booking.quote['extras']))
        booking.total = Decimal(booking.quote['total'])
    if 'adjustment' in data:
        if booking.status != 'new':
            raise ValidationError('Индивидуальную стоимость согласуют до подтверждения.')
        base_total = sum(Decimal(line['price']) for line in booking.quote['lines'])
        total = base_total + data['adjustment']
        if total < 0 or total > Decimal('99999999.99'):
            raise ValidationError('Недопустимая итоговая стоимость.')
        booking.quote['adjustment'] = {'amount': str(data['adjustment']), 'reason': data['adjustment_reason']}
        booking.quote['total'] = str(total)
        booking.quote['deposit'] = str((total * Decimal('0.20')).quantize(Decimal('0.01')))
        booking.total = total
    for key in ('date', 'wedding_time', 'shoot_start', 'shoot_end', 'location', 'admin_note', 'paid_amount'):
        if key in data:
            setattr(booking, key, data[key])
    if Decimal(booking.paid_amount) > Decimal(booking.total):
        raise ValidationError({'paid_amount': 'Сумма превышает стоимость заказа.'})
    if booking.event == 'wedding' and ('shoot_start' in data or 'shoot_end' in data):
        raise ValidationError('Время свадебной съёмки рассчитывается из пакета и начала свадьбы.')
    booking.status = status
    calculate_schedule(booking)
    crew = data.get('crew', list(booking.assignments.values('member', 'duty')))
    validate_crew(booking, crew)
    rebuild_reservations(booking, crew)
    schedule_changed = old_schedule != (booking.date, booking.wedding_time, booking.shoot_start, booking.shoot_end)
    if schedule_changed:
        booking.schedule_version += 1
    booking.version += 1
    booking.save()
    sync_notifications(booking, schedule_changed)
    AuditLog.objects.create(actor=actor, action='booking.updated', target=str(booking.pk),
        details={'before': before, 'after': {'status': status, 'date': str(booking.date), 'paid_amount': str(booking.paid_amount), 'total': str(booking.total)},
                 'crew': crew, 'version': booking.version, 'previous_status': old_status})
    return booking


@transaction.atomic
def update_booking(actor, booking_id, data):
    require_manager(actor)
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    return _apply_update(actor, booking, data)


@transaction.atomic
def request_change(user, booking_id, data):
    booking = Booking.objects.select_for_update().get(pk=booking_id, client=user)
    if booking.status in ('ready', 'cancelled', 'editing'):
        raise ValidationError('Для этого статуса изменение недоступно.')
    if booking.change_requests.filter(state='pending').exists():
        raise Conflict('У вас уже есть заявка на изменение.')
    if data['kind'] == 'reschedule':
        original = timezone.localdate(booking.shoot_start) if booking.shoot_start else booking.date
        if original - timezone.localdate() < timedelta(days=15):
            raise ValidationError('Перенос доступен не позднее чем за 15 дней до съёмки.')
        if not data.get('requested_date'):
            raise ValidationError({'requested_date': 'Укажите желаемую дату.'})
        validate_date(data['requested_date'])
    change = ChangeRequest.objects.create(booking=booking, **data)
    AuditLog.objects.create(actor=user, action='change.requested', target=str(booking.pk), details={'kind': change.kind})
    return change


@transaction.atomic
def decide_change(actor, change_id, data):
    require_manager(actor)
    # Same lock order as booking updates: booking, then change request.
    candidate = ChangeRequest.objects.get(pk=change_id)
    booking = Booking.objects.select_for_update().get(pk=candidate.booking_id)
    change = ChangeRequest.objects.select_for_update().get(pk=change_id)
    if change.state != 'pending':
        raise Conflict('Заявка уже рассмотрена.')
    if data['version'] != booking.version:
        raise Conflict('Заказ уже изменён. Обновите страницу.')
    if data['approve']:
        update = {'version': data['version']}
        if change.kind == 'cancel':
            update['status'] = 'cancelled'
        else:
            update['date'] = change.requested_date
            if change.requested_time:
                if booking.event == 'wedding':
                    update['wedding_time'] = change.requested_time
                else:
                    update['shoot_start'] = timezone.make_aware(datetime.combine(change.requested_date, change.requested_time))
            if 'crew' in data:
                update['crew'] = data['crew']
        _apply_update(actor, booking, update)
    change.state = 'approved' if data['approve'] else 'rejected'
    change.decision_note = data.get('note', '')
    change.decided_at = timezone.now()
    change.save()
    AuditLog.objects.create(actor=actor, action='change.decided', target=str(booking.pk), details={'change': change.pk, 'state': change.state})
    return change
