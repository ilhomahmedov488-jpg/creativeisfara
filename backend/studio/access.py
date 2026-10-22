from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission

from .models import PhoneBinding


def member_for(user):
    if not user or not user.is_authenticated or not user.is_active:
        return None
    binding = PhoneBinding.objects.select_related('member').filter(phone=user.phone, member__active=True).first()
    return binding.member if binding else None


def is_manager(user):
    member = member_for(user)
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or (member and member.access in ('admin', 'owner'))))


class ManagerOnly(BasePermission):
    def has_permission(self, request, view):
        return is_manager(request.user)


class TeamOnly(BasePermission):
    def has_permission(self, request, view):
        return is_manager(request.user) or member_for(request.user) is not None


def require_manager(user):
    if not is_manager(user):
        raise PermissionDenied('Нужны права администратора.')


def normalize_phone(value):
    import re
    value = re.sub(r'[\s()\-]', '', str(value))
    if re.fullmatch(r'\d{9}', value):
        value = '+992' + value
    elif re.fullmatch(r'992\d{9}', value):
        value = '+' + value
    if not re.fullmatch(r'\+992\d{9}', value):
        raise ValidationError({'phone': 'Введите номер Таджикистана: +992 и 9 цифр.'})
    return value
