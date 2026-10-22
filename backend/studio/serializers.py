import io
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image
from rest_framework import serializers

from .access import normalize_phone
from .models import CatalogItem, FAQ, PortfolioPost, Review, TeamMember


class StrictFields:
    def to_internal_value(self, data):
        unknown = set(data) - {k for k, f in self.fields.items() if not f.read_only}
        if unknown:
            raise serializers.ValidationError({k: 'Поле нельзя передавать.' for k in unknown})
        return super().to_internal_value(data)


class Input(StrictFields, serializers.Serializer):
    pass


class PhoneInput(Input):
    phone = serializers.CharField(max_length=30)

    def validate_phone(self, value):
        return normalize_phone(value)


class VerifyInput(Input):
    challenge_id = serializers.UUIDField()
    code = serializers.RegexField(r'^\d{6}$')


class CatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogItem
        fields = ['code', 'kind', 'title_ru', 'title_tg', 'price', 'revision', 'details', 'active']


class PriceInput(Input):
    code = serializers.SlugField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    revision = serializers.IntegerField(min_value=1)


class PricesInput(Input):
    items = PriceInput(many=True, allow_empty=False, max_length=20)


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMember
        fields = ['id', 'slug', 'name', 'position_ru', 'position_tg', 'experience', 'bio_ru', 'bio_tg', 'photo']


class ProfileInput(Input):
    bio_ru = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    bio_tg = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    photo = serializers.ImageField(required=False)

    def validate_photo(self, file):
        if file.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('Фото должно быть меньше 10 МБ.')
        image = Image.open(file)
        if image.width * image.height > 20_000_000:
            raise serializers.ValidationError('Фото слишком большое.')
        image = image.convert('RGB')
        image.thumbnail((1600, 1600))
        stream = io.BytesIO()
        image.save(stream, format='JPEG', quality=88)
        return ContentFile(stream.getvalue(), name='photo.jpg')


class BookingInput(Input):
    event = serializers.ChoiceField(choices=['wedding', 'love_story', 'foteha'])
    package = serializers.SlugField()
    extras = serializers.ListField(child=serializers.SlugField(), default=list, max_length=5)
    client_name = serializers.CharField(max_length=150)
    date = serializers.DateField()
    location = serializers.CharField(max_length=250, required=False, allow_blank=True)
    client_note = serializers.CharField(max_length=5000, required=False, allow_blank=True)


class CrewInput(Input):
    member = serializers.IntegerField(min_value=1)
    duty = serializers.ChoiceField(choices=['operator', 'photographer', 'reels', 'assistant'])


class BookingUpdateInput(Input):
    version = serializers.IntegerField(min_value=1)
    date = serializers.DateField(required=False)
    wedding_time = serializers.TimeField(required=False, allow_null=True)
    shoot_start = serializers.DateTimeField(required=False, allow_null=True)
    shoot_end = serializers.DateTimeField(required=False, allow_null=True)
    location = serializers.CharField(max_length=250, required=False, allow_blank=True)
    admin_note = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    package = serializers.SlugField(required=False)
    extras = serializers.ListField(child=serializers.SlugField(), required=False, max_length=5)
    status = serializers.ChoiceField(choices=['new', 'confirmed', 'editing', 'ready', 'cancelled'], required=False)
    paid_amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    crew = CrewInput(many=True, required=False, max_length=30)
    adjustment = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    adjustment_reason = serializers.CharField(max_length=1000, required=False)

    def validate(self, data):
        if ('adjustment' in data) != ('adjustment_reason' in data):
            raise serializers.ValidationError('Для индивидуального расчёта нужны сумма корректировки и причина.')
        return data


class ChangeInput(Input):
    kind = serializers.ChoiceField(choices=['cancel', 'reschedule'])
    requested_date = serializers.DateField(required=False)
    requested_time = serializers.TimeField(required=False)
    reason = serializers.CharField(max_length=3000)

    def validate(self, data):
        if data['kind'] == 'cancel' and (data.get('requested_date') or data.get('requested_time')):
            raise serializers.ValidationError('Для отмены дата и время не нужны.')
        return data


class DecisionInput(Input):
    version = serializers.IntegerField(min_value=1)
    approve = serializers.BooleanField()
    note = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    crew = CrewInput(many=True, required=False, max_length=30)


class BindingInput(PhoneInput):
    member = serializers.IntegerField(min_value=1)


class PortfolioSerializer(StrictFields, serializers.ModelSerializer):
    class Meta:
        model = PortfolioPost
        fields = ['id', 'author', 'title_ru', 'title_tg', 'event', 'placement', 'video', 'permission_confirmed', 'created_at']
        read_only_fields = ['id', 'author', 'created_at']

    def validate_permission_confirmed(self, value):
        if not value:
            raise serializers.ValidationError('Подтвердите разрешение на публикацию.')
        return value

    def validate_video(self, file):
        if file.size > settings.MAX_VIDEO_BYTES:
            raise serializers.ValidationError('Видео должно быть меньше 200 МБ.')
        extension = Path(file.name).suffix.lower()
        header = file.read(16)
        file.seek(0)
        if not ((extension == '.mp4' and header[4:8] == b'ftyp')
                or (extension == '.webm' and header[:4] == b'\x1a\x45\xdf\xa3')):
            raise serializers.ValidationError('Нужен файл MP4 или WebM.')
        return file


class ReviewSerializer(StrictFields, serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['id', 'author_name', 'text_ru', 'text_tg', 'published', 'consent', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, data):
        published = data.get('published', getattr(self.instance, 'published', False))
        consent = data.get('consent', getattr(self.instance, 'consent', False))
        if published and not consent:
            raise serializers.ValidationError('Для публикации отзыва нужно разрешение.')
        return data


class FAQSerializer(StrictFields, serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ['id', 'question_ru', 'question_tg', 'answer_ru', 'answer_tg', 'order']
        read_only_fields = ['id']
