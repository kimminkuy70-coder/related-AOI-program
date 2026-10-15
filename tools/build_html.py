# -*- coding: utf-8 -*-
"""Build the HTML version of AOI Photo Sorter: one .html file (styles and scripts inlined) that runs in Edge.

    python tools/build_html.py           # write programs/AOI_Photo_Sorter_HTML/<release>.html
    python tools/build_html.py --check   # fail if the committed .html is not what the sources build
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROGRAM = REPO / 'programs' / 'AOI_Photo_Sorter_HTML'
SRC = PROGRAM / 'src'
TAG = re.compile(r'<script(?P<id> id="[^"]+")? src="(?P<src>[^"]+)"></script>')


def build():
    version = json.loads((PROGRAM / 'version.json').read_text(encoding='utf-8'))
    html = (SRC / 'index.html').read_text(encoding='utf-8').replace('{{TITLE}}', version['title'])
    css = (SRC / 'styles.css').read_text(encoding='utf-8')
    link = '<link rel="stylesheet" href="styles.css">'
    if html.count(link) != 1:
        raise SystemExit('index.html: expected one %s' % link)
    html = html.replace(link, '<style>\n' + css + '\n</style>')

    def inline(match):
        code = (SRC / match.group('src')).read_text(encoding='utf-8')
        if re.search(r'</script', code, re.IGNORECASE):
            raise SystemExit('%s contains </script' % match.group('src'))
        return '<script%s>\n%s\n</script>' % (match.group('id') or '', code)

    html, count = TAG.subn(inline, html)
    if count != 4 or 'src=' in re.sub(r'<img[^>]*>', '', html.split('<body>', 1)[1]).split('<script', 1)[0]:
        raise SystemExit('index.html: expected 4 scripts to inline, found %d' % count)
    if '{{' in html:
        raise SystemExit('unfilled placeholder')
    return PROGRAM / (version['release'] + '.html'), html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    target, html = build()
    if args.check:
        if not target.is_file() or target.read_text(encoding='utf-8') != html:
            print('%s is not what the sources build: run python tools/build_html.py' % target.relative_to(REPO))
            return 1
        print('ok', target.relative_to(REPO))
        return 0
    for old in PROGRAM.glob('*.html'):
        if old != target:
            old.unlink()
    target.write_text(html, encoding='utf-8', newline='\n')
    print('built %s (%d KB)' % (target.relative_to(REPO), len(html.encode('utf-8')) // 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main())
