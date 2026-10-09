# -*- coding: utf-8 -*-
"""Generate the .vbs launchers, check shared files, and build release ZIPs.

    python tools/build_release.py          # check + regenerate launchers
    python tools/build_release.py --zip    # also write dist/<release>.zip
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROGRAMS = [REPO / 'programs' / 'AOI_Color_Gray_Matcher', REPO / 'programs' / 'Wafer_Map_Converter',
            REPO / 'programs' / 'AOI_Photo_Sorter']
SHARED = ['setup_env.py', 'runtime.py', 'constraints.txt']
TEMPLATE = REPO / 'tools' / 'launcher_template.vbs'
SKIP = {'__pycache__'}


def manifest(program):
    return json.loads((program / 'app_files' / 'app_manifest.json').read_text(encoding='utf-8'))


def check_shared():
    errors = []
    first = PROGRAMS[0] / 'app_files'
    for program in PROGRAMS[1:]:
        for name in SHARED:
            if (first / name).read_bytes() != (program / 'app_files' / name).read_bytes():
                errors.append('%s differs between %s and %s' % (name, first.parent.name, program.name))
    return errors


def write_launcher(program):
    data = manifest(program)
    text = TEMPLATE.read_text(encoding='utf-8')
    for key, value in (('APP_ID', data['app_id']), ('TITLE', data['title']), ('REVISION', str(data['env_revision']))):
        text = text.replace('{{%s}}' % key, value)
    if '{{' in text:
        raise SystemExit('unfilled placeholder in launcher template')
    raw = text.replace('\r\n', '\n').replace('\n', '\r\n').encode('cp949')  # ANSI, no BOM, CRLF
    for old in program.glob('*.vbs'):
        old.unlink()
    target = program / (data['release'] + '.vbs')
    target.write_bytes(raw)
    return target


def build_zip(program):
    data = manifest(program)
    dist = REPO / 'dist'
    dist.mkdir(exist_ok=True)
    target = dist / (data['release'] + '.zip')
    with zipfile.ZipFile(str(target), 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(program.rglob('*')):
            if path.is_file() and not SKIP.intersection(path.parts) and path.suffix != '.pyc':
                archive.write(str(path), str(Path(data['release']) / path.relative_to(program)))
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', action='store_true')
    args = parser.parse_args()
    errors = check_shared()
    if errors:
        print('\n'.join(errors))
        return 1
    for program in PROGRAMS:
        print('launcher', write_launcher(program).relative_to(REPO))
        if args.zip:
            print('zip', build_zip(program).relative_to(REPO))
    return 0


if __name__ == '__main__':
    sys.exit(main())
