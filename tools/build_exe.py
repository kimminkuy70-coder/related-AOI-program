# -*- coding: utf-8 -*-
"""Build the standalone .exe of a program (on Windows): Python and every package inside, so the
PC needs nothing installed but the WebView2 Runtime that Windows 10/11 already has.

    python tools/build_exe.py --install --test                                # every program with "exe": true
    python tools/build_exe.py --release AOI_Photo_Sorter_v6 --install --test  # the program of one release

--install  pip install the program's requirements (constraints.txt) and PyInstaller first
--test     run the built .exe's self-test: --selftest, then --selftest-window (WebView2)
Output: dist/<release>.exe. In GitHub Actions it also sets the step output built=true|false.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYINSTALLER = 'pyinstaller>=6.10,<7'


def programs(release):
    for manifest in sorted(REPO.glob('programs/*/app_files/app_manifest.json')):
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if (not release or data['release'] == release) and data.get('exe'):
            yield manifest.parent, data


def install(app_files):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                           '-c', str(app_files / 'constraints.txt'), '-r', str(app_files / 'requirements.txt'), PYINSTALLER])


def build(app_files, data):
    work = REPO / 'build' / 'exe' / data['app_id']
    exe = REPO / 'dist' / (data['release'] + '.exe')
    if exe.exists():
        exe.unlink()
    command = [
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--log-level', 'WARN',
        '--onefile', '--windowed',  # one file to hand out; no console window
        '--name', data['release'], '--distpath', str(exe.parent), '--workpath', str(work), '--specpath', str(work),
        '--add-data', '%s%s.' % (app_files / 'app_manifest.json', os.pathsep),
        '--add-data', '%s%sui' % (app_files / 'ui', os.pathsep),
        '--exclude-module', 'tkinter',
        str(app_files / 'app.py'),
    ]
    started = time.monotonic()
    subprocess.check_call(command, cwd=str(app_files))
    if not exe.is_file():
        raise SystemExit('PyInstaller made no %s' % exe)
    print('built %s: %.1f MB in %.0f s' % (exe.name, exe.stat().st_size / 1e6, time.monotonic() - started))
    return exe


def selftest(exe, flag):
    report = REPO / 'build' / 'exe' / ('%s%s.json' % (exe.stem, flag.replace('--', '_')))
    if report.exists():
        report.unlink()
    started = time.monotonic()
    code = subprocess.call([str(exe), flag, str(report)], timeout=240)
    seconds = time.monotonic() - started
    data = json.loads(report.read_text(encoding='utf-8')) if report.exists() else {}
    print(json.dumps(data, indent=1))  # ASCII: the build machine's console may not be UTF-8
    print('%s %s: exit %d in %.1f s' % (exe.name, flag, code, seconds))
    if code != 0 or not data.get('ok'):
        raise SystemExit('self-test %s failed' % flag)
    return seconds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', default='')
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()
    built, summary = [], []
    for app_files, data in programs(args.release.strip()):
        if os.name != 'nt':
            raise SystemExit('the .exe is built on Windows (PyInstaller does not cross-compile)')
        if args.install:
            install(app_files)
        exe = build(app_files, data)
        line = '%s: %.1f MB' % (exe.name, exe.stat().st_size / 1e6)
        if args.test:
            line += ', self-test %.1f s, with window %.1f s' % (selftest(exe, '--selftest'), selftest(exe, '--selftest-window'))
        built.append(exe)
        summary.append(line)
    if not built:
        print('no program with "exe": true%s' % (' for ' + args.release if args.release else ''))
    for name, value in (('GITHUB_OUTPUT', 'built=%s\n' % ('true' if built else 'false')),
                        ('GITHUB_STEP_SUMMARY', ''.join('- %s\n' % line for line in summary))):
        if os.environ.get(name):
            with open(os.environ[name], 'a', encoding='utf-8') as handle:
                handle.write(value)
    return 0


if __name__ == '__main__':
    sys.exit(main())
