from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as default_handler


class Conflict(APIException):
    status_code = 409
    default_detail = 'Данные изменились или сотрудник уже занят.'
    default_code = 'conflict'


class Unavailable(APIException):
    status_code = 503
    default_detail = 'Сервис SMS временно недоступен.'


def exception_handler(exc, context):
    return default_handler(exc, context)
