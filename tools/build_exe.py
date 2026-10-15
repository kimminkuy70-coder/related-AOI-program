# -*- coding: utf-8 -*-
"""Build the standalone .exe of a program (on Windows): Python and every package inside, so the
PC needs nothing installed but the WebView2 Runtime that Windows 10/11 already has.

    python tools/build_exe.py --install --test                                # every program with "exe": true
    python tools/build_exe.py --release AOI_Photo_Sorter_v7 --install --test  # the program of one release

--install  pip install the program's requirements (constraints.txt) and PyInstaller first,
           PyInstaller with its launcher stub compiled here from source (see install())
--test     run the built .exe's self-test: --selftest, then --selftest-window (WebView2)
Output: dist/<release>.exe. In GitHub Actions it also sets the step output built=true|false.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYINSTALLER = 'pyinstaller>=6.10,<7'
COMPANY = 'AOI Tools'


def programs(release):
    for manifest in sorted(REPO.glob('programs/*/app_files/app_manifest.json')):
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if (not release or data['release'] == release) and data.get('exe'):
            yield manifest.parent, data


def install(app_files):
    pip = [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check']
    subprocess.check_call(pip + ['-c', str(app_files / 'constraints.txt'), '-r', str(app_files / 'requirements.txt')])
    # Known PyInstaller false positive: Windows Defender flags one-file .exe built with the
    # prebuilt launcher stub that pip ships (shared, unchanged across many packages), as
    # "Trojan:Win32/Wacatac" on some machines and not others. PyInstaller's own FAQ recommends
    # rebuilding that stub from source so each build is distinct; the result is a clean .exe of
    # this project's own code. Needs a C toolchain (the Windows runner's MSVC).
    started = time.time()
    subprocess.check_call(pip + ['--no-cache-dir', '--force-reinstall', '--no-binary', 'pyinstaller', PYINSTALLER],
                          env=dict(os.environ, PYINSTALLER_COMPILE_BOOTLOADER='1'))
    stub = Path(subprocess.check_output(
        [sys.executable, '-c', 'import PyInstaller, os; print(os.path.dirname(PyInstaller.__file__))'],
        universal_newlines=True).strip()) / 'bootloader' / 'Windows-64bit-intel' / 'runw.exe'
    if not stub.is_file() or stub.stat().st_mtime < started - 5:
        raise SystemExit('PyInstaller launcher stub was not rebuilt from source: %s' % stub)
    print('PyInstaller launcher stub rebuilt from source: %s' % stub)


def version_file(data, work):
    """Windows version resource (file properties -> Details). An unsigned internal .exe with no
    version info looks more suspect to antivirus heuristics; filling in the company, product and
    version from the release name (AOI_Photo_Sorter_v7 -> 7.0.0.0) makes the file self-describing."""
    found = re.search(r'_v(\d+)(?:\.(\d+))?(?:\.(\d+))?$', data['release'])
    numbers = (tuple(int(part or 0) for part in found.groups()) + (0,)) if found else (0, 0, 0, 0)
    text = '.'.join(str(number) for number in numbers)
    strings = [('CompanyName', COMPANY), ('FileDescription', data['title']), ('FileVersion', text),
               ('InternalName', data['app_id']), ('LegalCopyright', COMPANY + ' (internal use)'),
               ('OriginalFilename', data['release'] + '.exe'), ('ProductName', data['title']), ('ProductVersion', text)]
    work.mkdir(parents=True, exist_ok=True)
    path = work / 'version_info.txt'
    path.write_text(
        'VSVersionInfo(\n'
        '  ffi=FixedFileInfo(filevers=%r, prodvers=%r, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n'
        '  kids=[\n'
        '    StringFileInfo([StringTable(%r, [%s])]),\n'
        '    VarFileInfo([VarStruct(%r, [1042, 1200])])\n'
        '  ]\n'
        ')\n' % (numbers, numbers, '041204B0',
                 ', '.join('StringStruct(%r, %r)' % pair for pair in strings), 'Translation'),
        encoding='utf-8')
    return path


def build(app_files, data):
    work = REPO / 'build' / 'exe' / data['app_id']
    exe = REPO / 'dist' / (data['release'] + '.exe')
    if exe.exists():
        exe.unlink()
    command = [
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--log-level', 'WARN',
        '--onefile', '--windowed',  # one file to hand out; no console window
        '--noupx',  # UPX-compressed executables are flagged by antivirus far more often
        '--version-file', str(version_file(data, work)),
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
