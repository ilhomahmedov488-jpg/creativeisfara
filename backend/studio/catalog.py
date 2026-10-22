from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .access import require_manager
from .errors import Conflict
from .models import AuditLog, CatalogItem


def quote_for(event, package, extras):
    if len(extras) != len(set(extras)):
        raise ValidationError({'extras': 'Услуги не должны повторяться.'})
    if event == 'wedding':
        if package not in ('standard', 'pro', 'premium'):
            raise ValidationError({'package': 'Выберите свадебный пакет.'})
        codes = [package] + extras
        if 'foteha_one' in extras and 'foteha_two' in extras:
            raise ValidationError({'extras': 'Выберите один вариант фотехакунон.'})
        if package == 'premium' and 'foteha_two' in extras:
            raise ValidationError({'extras': 'Цену двух камер для Премиум нужно согласовать.'})
        included = ['album', 'foteha_one'] if package == 'premium' else []
        allowed = {'foteha_one', 'foteha_two', 'love_story', 'album', 'hall_screen'}
        if set(extras) - allowed:
            raise ValidationError({'extras': 'Неизвестная дополнительная услуга.'})
    else:
        allowed = {'love_story': {'love_story'}, 'foteha': {'foteha_one', 'foteha_two'}}
        if event not in allowed or package not in allowed[event] or extras:
            raise ValidationError('Неверный формат отдельной съёмки.')
        codes, included = [package], []
    # Every creation/requote locks the same ordered rate rows used by price updates.
    items = {i.code: i for i in CatalogItem.objects.select_for_update().filter(code__in=set(codes + included)).order_by('code')}
    if set(codes + included) - items.keys() or any(not i.active for i in items.values()):
        raise ValidationError('Услуга недоступна.')
    lines, total = [], Decimal('0.00')
    for code in dict.fromkeys(codes + included):
        item = items[code]
        amount = Decimal('0.00') if code in included else item.price
        total += amount
        lines.append({'code': code, 'title_ru': item.title_ru, 'title_tg': item.title_tg,
                      'price': str(amount), 'catalog_price': str(item.price),
                      'revision': item.revision, 'included': code in included})
    return {'package': package, 'extras': extras, 'lines': lines, 'total': str(total),
            'deposit': str((total * Decimal('0.20')).quantize(Decimal('0.01'))),
            'currency': 'TJS', 'love_story_base_price': 'love_story' in codes,
            'transport_included': False, 'delivery_days': 60}


@transaction.atomic
def update_prices(actor, updates):
    require_manager(actor)
    codes = [u['code'] for u in updates]
    if len(codes) != len(set(codes)):
        raise ValidationError('Код услуги повторяется.')
    items = {i.code: i for i in CatalogItem.objects.select_for_update().filter(code__in=codes).order_by('code')}
    for update in updates:
        item = items.get(update['code'])
        if item is None:
            raise ValidationError('Неизвестная услуга.')
        if item.revision != update['revision']:
            raise Conflict('Прайс уже изменён. Обновите страницу.')
        old = str(item.price)
        item.price, item.revision = update['price'], item.revision + 1
        item.save(update_fields=['price', 'revision'])
        AuditLog.objects.create(actor=actor, action='price.changed', target=item.code,
                                details={'before': old, 'after': str(item.price)})
    return list(items.values())
