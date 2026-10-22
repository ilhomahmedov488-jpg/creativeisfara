from datetime import date
import ipaddress

from django.contrib.auth import login, logout
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated, SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from . import booking as booking_service
from . import otp
from .access import ManagerOnly, TeamOnly, is_manager, member_for
from .catalog import update_prices
from .errors import Conflict
from .models import AuditLog, Booking, ChangeRequest, CatalogItem, DailyReservation, FAQ, PhoneBinding, PortfolioPost, Review, TeamMember
from .serializers import (BindingInput, BookingInput, BookingUpdateInput, CatalogSerializer, ChangeInput,
    DecisionInput, FAQSerializer, PhoneInput, PortfolioSerializer, PricesInput, ProfileInput,
    ReviewSerializer, TeamSerializer, VerifyInput)


def validated(cls, data):
    serializer = cls(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def client_ip(request):
    # Enable only with the loopback-only app and the supplied proxy header overwrite.
    value = request.META.get('REMOTE_ADDR', 'unknown')
    if getattr(settings, 'TRUST_CLIENT_IP_HEADER', False):
        try:
            value = str(ipaddress.ip_address(request.META.get('HTTP_X_REAL_IP', '')))
        except ValueError:
            pass
    return value


@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({'csrfToken': get_token(request)})


def health(request):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    return JsonResponse({'status': 'ok'})


def account_data(user):
    member = member_for(user)
    role = member.access if member else ('admin' if user.is_superuser else 'client')
    return {'id': user.pk, 'phone': user.phone, 'role': role,
            'member': TeamSerializer(member).data if member else None,
            'cabinet': 'management' if is_manager(user) else ('employee' if member else 'client')}


class AuthView(APIView):
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        # DRF's session authentication skips CSRF for anonymous requests, so explicitly
        # enforce it here too to protect SMS requests and login against cross-site POSTs.
        if request.method not in SAFE_METHODS:
            SessionAuthentication().enforce_csrf(request)
        return super().initial(request, *args, **kwargs)


class RequestCode(AuthView):
    def post(self, request):
        data = validated(PhoneInput, request.data)
        challenge = otp.request_code(data['phone'], client_ip(request))
        return Response({'challenge_id': str(challenge.pk), 'expires_in': 300}, status=201)


class VerifyCode(AuthView):
    def post(self, request):
        data = validated(VerifyInput, request.data)
        user = otp.verify_code(data['challenge_id'], data['code'], client_ip(request))
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return Response({**account_data(user), 'csrfToken': get_token(request)})


class Me(APIView):
    def get(self, request):
        return Response(account_data(request.user))


class Logout(AuthView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=204)


class Catalog(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(CatalogSerializer(CatalogItem.objects.filter(active=True), many=True).data)


class Prices(APIView):
    permission_classes = [ManagerOnly]

    def patch(self, request):
        result = update_prices(request.user, validated(PricesInput, request.data)['items'])
        return Response(CatalogSerializer(result, many=True).data)


class Team(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(TeamSerializer(TeamMember.objects.filter(active=True), many=True, context={'request': request}).data)


class MyProfile(APIView):
    permission_classes = [TeamOnly]

    def get(self, request):
        return Response(TeamSerializer(get_object_or_404(TeamMember, pk=getattr(member_for(request.user), 'pk', None)), context={'request': request}).data)

    def patch(self, request):
        member = get_object_or_404(TeamMember, pk=getattr(member_for(request.user), 'pk', None))
        data = validated(ProfileInput, request.data)
        old_photo = member.photo.name
        for k, v in data.items():
            setattr(member, k, v)
        member.save()
        if 'photo' in data and old_photo:
            member.photo.storage.delete(old_photo)
        return Response(TeamSerializer(member, context={'request': request}).data)


def booking_data(booking, user):
    manager = is_manager(user)
    member = member_for(user)
    employee = member is not None and not manager
    data = {'id': str(booking.pk), 'event': booking.event, 'date': booking.date, 'status': booking.status,
            'wedding_time': booking.wedding_time, 'shoot_start': booking.shoot_start,
            'shoot_end': booking.shoot_end, 'location': booking.location, 'version': booking.version,
            'crew': list(booking.assignments.values('member', 'duty'))}
    if employee:
        return data
    now = timezone.now()
    seconds = max(0, int((booking.shoot_start - now).total_seconds())) if booking.status == 'confirmed' and booking.shoot_start else None
    data.update(client_name=booking.client_name, client_note=booking.client_note,
                quote=booking.quote, total=str(booking.total), paid_amount=str(booking.paid_amount),
                countdown_seconds=seconds, server_time=now, created_at=booking.created_at,
                change_requests=list(booking.change_requests.values('id', 'kind', 'requested_date', 'requested_time', 'reason', 'state', 'decision_note')))
    if manager:
        data.update(client_phone=booking.client.phone, admin_note=booking.admin_note, client_id=booking.client_id)
    return data


class BookingViewSet(viewsets.GenericViewSet):
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        queryset = Booking.objects.select_related('client').prefetch_related('assignments', 'change_requests')
        if is_manager(self.request.user):
            return queryset
        member = member_for(self.request.user)
        if member:
            return queryset.filter(assignments__member=member).distinct()
        return queryset.filter(client=self.request.user)

    def list(self, request):
        queryset = self.get_queryset()
        date_value = request.query_params.get('date')
        if date_value:
            try:
                queryset = queryset.filter(date=date.fromisoformat(date_value))
            except ValueError:
                raise ValidationError({'date': 'Неверная дата.'})
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response([booking_data(b, request.user) for b in page])

    def retrieve(self, request, pk=None):
        return Response(booking_data(self.get_object(), request.user))

    def create(self, request):
        booking = booking_service.create_booking(request.user, validated(BookingInput, request.data))
        return Response(booking_data(booking, request.user), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        if not is_manager(request.user):
            raise PermissionDenied()
        self.get_object()
        result = booking_service.update_booking(request.user, pk, validated(BookingUpdateInput, request.data))
        return Response(booking_data(result, request.user))

    @action(detail=True, methods=['post'], url_path='change-requests')
    def change_requests(self, request, pk=None):
        booking = self.get_object()
        if booking.client_id != request.user.pk or member_for(request.user):
            raise PermissionDenied()
        change = booking_service.request_change(request.user, booking.pk, validated(ChangeInput, request.data))
        return Response({'id': change.pk, 'state': change.state}, status=201)


class Availability(APIView):
    permission_classes = [ManagerOnly]

    def get(self, request):
        try:
            day = date.fromisoformat(request.query_params.get('date', ''))
        except ValueError:
            raise ValidationError({'date': 'Укажите дату YYYY-MM-DD.'})
        reservations = {r.member_id: str(r.booking_id) for r in DailyReservation.objects.filter(day=day)}
        return Response([{'member': m.pk, 'name': m.name, 'busy': m.pk in reservations,
                          'booking': reservations.get(m.pk)} for m in TeamMember.objects.filter(active=True)])


class ChangeDecision(APIView):
    permission_classes = [ManagerOnly]

    def post(self, request, pk):
        get_object_or_404(ChangeRequest, pk=pk)
        change = booking_service.decide_change(request.user, pk, validated(DecisionInput, request.data))
        return Response({'id': change.pk, 'state': change.state, 'booking_version': change.booking.version})


class Bindings(APIView):
    permission_classes = [ManagerOnly]

    def get(self, request):
        return Response(list(PhoneBinding.objects.values('member', 'phone')))

    @transaction.atomic
    def put(self, request):
        data = validated(BindingInput, request.data)
        # Global ordering also prevents duplicate updates to the same phone by two admins.
        list(TeamMember.objects.select_for_update().order_by('pk'))
        member = get_object_or_404(TeamMember, pk=data['member'])
        own = member_for(request.user)
        if own and own.pk == member.pk:
            raise ValidationError('Ваш номер должен менять другой администратор.')
        try:
            with transaction.atomic():
                PhoneBinding.objects.update_or_create(member=member, defaults={'phone': data['phone']})
        except IntegrityError:
            raise Conflict('Этот номер уже связан с другим участником.') from None
        AuditLog.objects.create(actor=request.user, action='binding.changed', target=str(member.pk))
        return Response({'member': member.pk, 'phone': data['phone']})


class BindingDelete(APIView):
    permission_classes = [ManagerOnly]

    @transaction.atomic
    def delete(self, request, pk):
        list(TeamMember.objects.select_for_update().order_by('pk'))
        member = get_object_or_404(TeamMember, pk=pk)
        own = member_for(request.user)
        if own and own.pk == member.pk:
            raise ValidationError('Нельзя удалить свой доступ.')
        PhoneBinding.objects.filter(member=member).delete()
        AuditLog.objects.create(actor=request.user, action='binding.deleted', target=str(pk))
        return Response(status=204)


class PublicReadManagerWrite:
    def get_permissions(self):
        return [AllowAny()] if self.request.method in SAFE_METHODS else [ManagerOnly()]


class PortfolioViewSet(viewsets.ModelViewSet):
    serializer_class = PortfolioSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        return [AllowAny()] if self.request.method in SAFE_METHODS else [TeamOnly()]

    def get_queryset(self):
        queryset = PortfolioPost.objects.select_related('author').all()
        for key in ('event', 'placement', 'author'):
            value = self.request.query_params.get(key)
            if value:
                if key == 'author' and not value.isdigit():
                    raise ValidationError({'author': 'Нужен ID сотрудника.'})
                queryset = queryset.filter(**{key: value})
        return queryset

    def perform_create(self, serializer):
        member = member_for(self.request.user)
        if not member:
            raise ValidationError('Для публикации нужен профиль участника команды.')
        serializer.save(author=member)

    def check_owner(self, post):
        member = member_for(self.request.user)
        if not is_manager(self.request.user) and (not member or member.pk != post.author_id):
            raise PermissionDenied()

    def perform_update(self, serializer):
        self.check_owner(serializer.instance)
        old = serializer.instance.video.name
        post = serializer.save()
        if old != post.video.name:
            post.video.storage.delete(old)

    def perform_destroy(self, instance):
        self.check_owner(instance)
        file = instance.video
        instance.delete()
        file.delete(save=False)


class ReviewViewSet(PublicReadManagerWrite, viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return Review.objects.all().order_by('-created_at') if is_manager(self.request.user) else Review.objects.filter(published=True, consent=True).order_by('-created_at')


class FAQViewSet(PublicReadManagerWrite, viewsets.ModelViewSet):
    serializer_class = FAQSerializer
    queryset = FAQ.objects.all()
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
