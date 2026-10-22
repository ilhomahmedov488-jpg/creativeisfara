import uuid
from pathlib import Path

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import Q


def media_path(instance, filename):
    return f'portfolio/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone, password=None, **kwargs):
        user = self.model(phone=phone, **kwargs)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password, **kwargs):
        kwargs.update(is_staff=True, is_superuser=True)
        return self.create_user(phone, password, **kwargs)


class User(AbstractUser):
    username = None
    phone = models.CharField(max_length=16, unique=True)
    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = []
    objects = UserManager()


class TeamMember(models.Model):
    class Access(models.TextChoices):
        OWNER = 'owner', 'Владелец'
        ADMIN = 'admin', 'Администратор'
        EMPLOYEE = 'employee', 'Сотрудник'

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=150)
    position_ru = models.CharField(max_length=180)
    position_tg = models.CharField(max_length=180)
    experience = models.PositiveSmallIntegerField(null=True, blank=True)
    bio_ru = models.TextField(blank=True)
    bio_tg = models.TextField(blank=True)
    photo = models.ImageField(upload_to=media_path, blank=True)
    access = models.CharField(max_length=12, choices=Access.choices, default=Access.EMPLOYEE)
    active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']


class PhoneBinding(models.Model):
    member = models.OneToOneField(TeamMember, on_delete=models.CASCADE, related_name='binding')
    phone = models.CharField(max_length=16, unique=True)


class OTPChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=16, db_index=True)
    digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed = models.BooleanField(default=False)


class RateBucket(models.Model):
    key = models.CharField(max_length=80, primary_key=True)
    started_at = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)


class CatalogItem(models.Model):
    code = models.SlugField(primary_key=True)
    kind = models.CharField(max_length=8, choices=[('package', 'Пакет'), ('addon', 'Услуга')])
    title_ru = models.CharField(max_length=150)
    title_tg = models.CharField(max_length=150)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    revision = models.PositiveIntegerField(default=1)
    details = models.JSONField(default=dict)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['kind', 'price']
        constraints = [models.CheckConstraint(condition=Q(price__gte=0), name='nonnegative_catalog_price')]


class Booking(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новая заявка'
        CONFIRMED = 'confirmed', 'Подтверждён'
        EDITING = 'editing', 'Монтаж'
        READY = 'ready', 'Готов'
        CANCELLED = 'cancelled', 'Отменён'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(User, on_delete=models.PROTECT, related_name='bookings')
    event = models.CharField(max_length=12, choices=[('wedding', 'Свадьба'), ('love_story', 'Love Story'), ('foteha', 'Фотехакунон')])
    client_name = models.CharField(max_length=150)
    date = models.DateField(db_index=True)
    wedding_time = models.TimeField(null=True, blank=True)
    shoot_start = models.DateTimeField(null=True, blank=True)
    shoot_end = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=250, blank=True)
    client_note = models.TextField(blank=True)
    admin_note = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    quote = models.JSONField()
    total = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    version = models.PositiveIntegerField(default=1)
    schedule_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(condition=Q(total__gte=0) & Q(paid_amount__gte=0), name='nonnegative_booking_money')]


class Assignment(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='assignments')
    member = models.ForeignKey(TeamMember, on_delete=models.PROTECT)
    duty = models.CharField(max_length=24, choices=[('operator', 'Оператор'), ('photographer', 'Фотограф'), ('reels', 'Reels maker'), ('assistant', 'Помощник')])

    class Meta:
        constraints = [models.UniqueConstraint(fields=['booking', 'member'], name='unique_booking_member')]


class DailyReservation(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='reservations')
    member = models.ForeignKey(TeamMember, on_delete=models.PROTECT)
    day = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['member', 'day'], name='one_shoot_per_member_day')]


class ChangeRequest(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='change_requests')
    kind = models.CharField(max_length=12, choices=[('reschedule', 'Перенос'), ('cancel', 'Отмена')])
    requested_date = models.DateField(null=True, blank=True)
    requested_time = models.TimeField(null=True, blank=True)
    reason = models.TextField()
    state = models.CharField(max_length=12, default='pending', choices=[('pending', 'Ожидает'), ('approved', 'Одобрено'), ('rejected', 'Отклонено')])
    decision_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['booking'], condition=Q(state='pending'), name='one_pending_change')]


class PortfolioPost(models.Model):
    author = models.ForeignKey(TeamMember, on_delete=models.PROTECT, related_name='posts')
    title_ru = models.CharField(max_length=180)
    title_tg = models.CharField(max_length=180)
    event = models.CharField(max_length=12, choices=Booking._meta.get_field('event').choices)
    placement = models.CharField(max_length=12, choices=[('reels', 'Reels'), ('portfolio', 'Портфолио')])
    video = models.FileField(upload_to=media_path)
    permission_confirmed = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Review(models.Model):
    author_name = models.CharField(max_length=150)
    text_ru = models.TextField()
    text_tg = models.TextField()
    published = models.BooleanField(default=False)
    consent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class FAQ(models.Model):
    question_ru = models.CharField(max_length=250)
    question_tg = models.CharField(max_length=250)
    answer_ru = models.TextField()
    answer_tg = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']


class Notification(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE)
    kind = models.CharField(max_length=12, choices=[('reminder', 'Напоминание'), ('ready', 'Материал готов')])
    schedule_version = models.PositiveIntegerField()
    due_at = models.DateTimeField(db_index=True)
    state = models.CharField(max_length=12, default='pending')
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['booking', 'kind', 'schedule_version'], name='unique_booking_notification')]


class AuditLog(models.Model):
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60)
    target = models.CharField(max_length=80)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
