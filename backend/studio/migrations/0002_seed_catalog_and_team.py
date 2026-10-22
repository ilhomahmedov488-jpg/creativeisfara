from django.db import migrations


def seed(apps, schema_editor):
    Team = apps.get_model('studio', 'TeamMember')
    Item = apps.get_model('studio', 'CatalogItem')
    FAQ = apps.get_model('studio', 'FAQ')
    team = [
        ('abdu', 'Абдумачид Хасанов', 'Основатель студии, главный оператор', 'Асосгузори студия, наворбардори асосӣ', 12, 'admin'),
        ('ilhom', 'Илхомиддин Ахмедов', 'Основатель сайта, оператор', 'Асосгузори сомона, наворбардор', 3, 'owner'),
        ('amri', 'Амриддин Хакимов', 'Оператор со стабилизатором', 'Наворбардор бо стабилизатор', 6, 'employee'),
        ('muhammad', 'Мухаммадали Набиев', 'Оператор', 'Наворбардор', 4, 'employee'),
        ('sadr', 'Садриддин Иброхимов', 'Оператор', 'Наворбардор', 2, 'employee'),
        ('farrukh', 'Фаррух Шамсиев', 'Кран-оператор', 'Наворбардори кран', 3, 'employee'),
        ('muhi', 'Мухиббило Чураев', 'Оператор, фотограф', 'Наворбардор, суратгир', 5, 'employee'),
        ('abdul', 'Абдухаллок Нуридинов', 'Помощник оператора', 'Ёвари наворбардор', None, 'employee'),
        ('muhammadjon', 'Мухаммадчон Азамов', 'Помощник оператора', 'Ёвари наворбардор', None, 'employee'),
    ]
    for order, (slug, name, ru, tg, experience, access) in enumerate(team):
        Team.objects.create(slug=slug, name=name, position_ru=ru, position_tg=tg, experience=experience, access=access, order=order)
    catalog = [
        ('standard', 'package', 'Стандарт', 'Стандарт', '4000.00', {'operators': 1, 'photographers': 1, 'start': 'wedding_minus_6_hours'}),
        ('pro', 'package', 'Про', 'Про', '6000.00', {'operators': 2, 'photographers': 1, 'start': 'wedding_minus_6_hours'}),
        ('premium', 'package', 'Премиум', 'Премиум', '10000.00', {'operators': 4, 'photographers': 1, 'reels_makers': 1, 'reels': 3, 'start': '12:00', 'included': ['album', 'foteha_one']}),
        ('foteha_one', 'addon', 'Фотехакунон, 1 камера', 'Фотеҳахонон, 1 камера', '1000.00', {}),
        ('foteha_two', 'addon', 'Фотехакунон, 2 камеры', 'Фотеҳахонон, 2 камера', '1500.00', {}),
        ('love_story', 'addon', 'Love Story', 'Love Story', '2000.00', {'base_price': True, 'final_price_by_agreement': True}),
        ('album', 'addon', 'Альбом на 10 листов', 'Албоми 10-варақа', '500.00', {'leaves': 10}),
        ('hall_screen', 'addon', 'Изображение камер на экране зала', 'Пахши камераҳо дар экрани толор', '2000.00', {'internet_stream': False}),
    ]
    for code, kind, ru, tg, price, details in catalog:
        Item.objects.create(code=code, kind=kind, title_ru=ru, title_tg=tg, price=price, details=details)
    FAQ.objects.create(question_ru='Когда будет готов материал?', question_tg='Мавод кай омода мешавад?',
        answer_ru='До 60 дней. Выдаём готовый материал на флешке и диске с обложкой и футляром.',
        answer_tg='То 60 рӯз. Маводи омода дар флешка ва диск бо муқова ва қуттӣ дода мешавад.', order=1)
    FAQ.objects.create(question_ru='Как внести предоплату?', question_tg='Пешпардохтро чӣ тавр месупорам?',
        answer_ru='Предоплата — 20% вне сайта. Администратор согласует способ и отметит получение.',
        answer_tg='Пешпардохт 20% аст ва берун аз сомона супорида мешавад. Маъмур тарзи пардохтро мувофиқа мекунад.', order=2)
    FAQ.objects.create(question_ru='Включён ли транспорт?', question_tg='Хароҷоти роҳ дохил аст?',
        answer_ru='Транспорт оплачивается отдельно по согласованию.',
        answer_tg='Хароҷоти роҳ алоҳида мувофиқа ва пардохт мешавад.', order=3)


class Migration(migrations.Migration):
    dependencies = [('studio', '0001_initial')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
