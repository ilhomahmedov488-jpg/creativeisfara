"""Build only the agreed public design prototypes for GitHub Pages; never copy runtime data."""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'preview-dist'


def build():
    shell = (ROOT / 'preview/shell.html').read_text()
    sources = [
        ('public', 'index.html', 'Сайт и бронирование'),
        ('accounts', 'accounts.html', 'Кабинеты команды'),
    ]
    fragments = {name: (ROOT / f'design/{name}.fragment.html').read_text() for name, _, _ in sources}
    bindings = re.search(r'\b(?:let|const)\s+phoneBindings\s*=\s*([^;]+);', fragments['accounts'])
    initializer = re.sub(r'\s+', '', bindings.group(1)) if bindings else ''
    if initializer not in ('{}', "Object.fromEntries(team.map(p=>[p.id,'']))"):
        raise ValueError('The public prototype must contain an empty phone binding map.')
    for name, fragment in fragments.items():
        if re.search(r'\b(?:fetch\s*\(|XMLHttpRequest|WebSocket)', fragment):
            raise ValueError(f'{name}: network access is not allowed in the design preview.')
        if not fragment.startswith('<div id=') or '<script>' not in fragment:
            raise ValueError(f'{name}: expected the existing interactive design fragment.')
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()
    for name, target, title in sources:
        page = shell.replace('<!--CONTENT-->', fragments[name]).replace('<!--TITLE-->', title)
        page = page.replace('<!--PUBLIC_ACTIVE-->', 'aria-current="page"' if name == 'public' else '')
        page = page.replace('<!--ACCOUNTS_ACTIVE-->', 'aria-current="page"' if name == 'accounts' else '')
        (OUTPUT / target).write_text(page)
    shutil.copyfile(ROOT / 'preview/preview.css', OUTPUT / 'preview.css')
    (OUTPUT / '.nojekyll').touch()
    (OUTPUT / 'robots.txt').write_text('User-agent: *\nDisallow: /\n')
    # Explicit output allowlist prevents publishing backend source, media, .env or contacts.
    assert {p.name for p in OUTPUT.iterdir()} == {'index.html', 'accounts.html', 'preview.css', '.nojekyll', 'robots.txt'}
    print('Built design preview: index.html, accounts.html, preview.css, .nojekyll, robots.txt')


if __name__ == '__main__':
    build()
