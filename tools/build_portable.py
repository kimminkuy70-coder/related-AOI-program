# -*- coding: utf-8 -*-
"""Build the portable Python runtime of a program: the release ZIP then runs on a PC with no
Python installed, without any .exe built by this project.

The runtime is the official Windows Python from NuGet (package "python", published by the
Python Software Foundation; python.exe / pythonw.exe / python3XX.dll are Authenticode-signed
by the PSF) with the program's packages unpacked from their Windows wheels into
Lib\\site-packages. Antivirus judges the signed interpreter, not a fresh unsigned PyInstaller
.exe, so the Defender "Trojan:Win32/Wacatac...!ml" false positive of the .exe does not apply.

Runs on any OS (Linux CI included): nothing is executed for Windows, files are only downloaded
and unpacked. pip downloads the packages with --no-deps one by one, because pip evaluates
environment markers (sys_platform == "win32") for the machine it runs on, not for --platform.

    python tools/build_portable.py --release AOI_Photo_Sorter_v10   # -> build/portable/<release>/runtime
"""
import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

try:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name, parse_wheel_filename
    from packaging.version import Version
except ImportError:  # pip always carries a copy
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
    from pip._vendor.packaging.version import Version

REPO = Path(__file__).resolve().parent.parent
PYTHON_VERSION = '3.12.10'  # 3.12 is the newest line with a Windows wheel for every package in constraints.txt
NUGET_URL = 'https://api.nuget.org/v3-flatcontainer/python/{0}/python.{0}.nupkg'
# The interpreter is the same for every Windows 10/11 PC (64-bit), whatever machine builds the ZIP.
TARGET = {'sys_platform': 'win32', 'platform_system': 'Windows', 'os_name': 'nt', 'platform_machine': 'AMD64',
          'implementation_name': 'cpython', 'platform_python_implementation': 'CPython',
          'python_version': '.'.join(PYTHON_VERSION.split('.')[:2]), 'python_full_version': PYTHON_VERSION,
          'extra': ''}
# Not needed to run a program: headers, import libraries, pip itself, IDLE/tkinter demos, tests.
DROP = ('include/', 'libs/', 'Scripts/', 'Lib/ensurepip/', 'Lib/idlelib/', 'Lib/turtledemo/', 'Lib/test/',
        'Lib/lib2to3/', 'Lib/site-packages/pip/', 'Lib/site-packages/pip-')
MARKER_FILE = 'aoi_portable.json'


def programs(release):
    for manifest in sorted(REPO.glob('programs/*/app_files/app_manifest.json')):
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if (not release or data['release'] == release) and data.get('portable'):
            yield manifest.parent, data


def read_requirements(path):
    """Requirement lines of requirements.txt / constraints.txt (comments and options skipped)."""
    lines = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if line and not line.startswith('-'):
            lines.append(Requirement(line))
    return lines


def applies(requirement):
    return requirement.marker is None or requirement.marker.evaluate(TARGET)


def wheel_requirements(wheel):
    """Requires-Dist of a wheel that apply to Windows (extras are never requested)."""
    with zipfile.ZipFile(str(wheel)) as archive:
        name = next(item for item in archive.namelist() if re.match(r'[^/]+\.dist-info/METADATA$', item))
        text = archive.read(name).decode('utf-8', 'replace')
    found = []
    for line in text.split('\n\n', 1)[0].splitlines():
        if line.startswith('Requires-Dist:'):
            requirement = Requirement(line.split(':', 1)[1].strip())
            if applies(requirement):
                found.append(requirement)
    return found


def pip_download(spec, dest, binary):
    command = [sys.executable, '-m', 'pip', 'download', '--disable-pip-version-check', '--quiet', '--no-deps',
               '--dest', str(dest), spec]
    if binary:
        abi = 'cp' + TARGET['python_version'].replace('.', '')
        command[5:5] = ['--only-binary=:all:', '--platform', 'win_amd64', '--python-version', TARGET['python_version'],
                        '--implementation', 'cp', '--abi', abi, '--abi', 'abi3', '--abi', 'none']
    else:
        command[5:5] = ['--no-binary=:all:']
    return subprocess.call(command) == 0


def download(requirement, constraints, cache):
    """Download one package for Windows: its wheel (cp312 / win_amd64 or pure Python) or, for a
    pure-Python package published only as a source archive (proxy_tools), that archive."""
    name = canonicalize_name(requirement.name)
    specifier = requirement.specifier
    if name in constraints:
        specifier = specifier & constraints[name].specifier
    spec = name + str(specifier)
    if not pip_download(spec, cache / 'wheels', True):
        print('%s: no Windows wheel (pip error above), trying the source archive' % spec)
        if not pip_download(spec, cache / 'sdist', False):
            raise SystemExit('no Windows wheel or source archive for %s' % spec)
    matches = []
    for path in list((cache / 'wheels').glob('*.whl')) + list((cache / 'sdist').glob('*.tar.gz')):
        if path.suffix == '.whl':
            found, version = parse_wheel_filename(path.name)[:2]
        else:
            found, _, version = path.name[:-len('.tar.gz')].rpartition('-')
            found = canonicalize_name(found)
        if found == name and specifier.contains(version, prereleases=True):
            matches.append((path.suffix == '.whl', Version(str(version)), path))
    if not matches:
        raise SystemExit('nothing downloaded for %s' % spec)
    return max(matches)[2]  # prefer a wheel, then the newest version (the cache may hold older ones)


def resolve(app_files, cache):
    """requirements.txt plus every dependency for Windows, as downloaded files."""
    constraints = {canonicalize_name(item.name): item for item in read_requirements(app_files / 'constraints.txt')}
    queue = [item for item in read_requirements(app_files / 'requirements.txt') if applies(item)]
    done = {}
    while queue:
        requirement = queue.pop(0)
        name = canonicalize_name(requirement.name)
        if name in done:
            continue
        done[name] = download(requirement, constraints, cache)
        if done[name].suffix == '.whl':
            queue.extend(wheel_requirements(done[name]))
    return [done[name] for name in sorted(done)]


def nuget_python(cache):
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / ('python.%s.nupkg' % PYTHON_VERSION)
    if not target.is_file():
        with urllib.request.urlopen(NUGET_URL.format(PYTHON_VERSION), timeout=120) as response:
            data = response.read()
        zipfile.ZipFile(io.BytesIO(data)).testzip()
        target.write_bytes(data)
    return target


def unpack_python(nupkg, runtime):
    with zipfile.ZipFile(str(nupkg)) as archive:
        for item in archive.infolist():
            if not item.filename.startswith('tools/') or item.is_dir():
                continue
            relative = item.filename[len('tools/'):]
            if not relative or relative.startswith(DROP) or '__pycache__' in relative:
                continue
            target = runtime / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))
    for name in ('python.exe', 'pythonw.exe', 'python%s.dll' % TARGET['python_version'].replace('.', '')):
        if not (runtime / name).is_file():
            raise SystemExit('the NuGet Python has no %s' % name)


def unpack_wheel(wheel, site_packages):
    """A wheel is a zip of the installed files; *.data/purelib|platlib go to site-packages too."""
    with zipfile.ZipFile(str(wheel)) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            relative = item.filename
            data_dir = re.match(r'[^/]+\.data/(purelib|platlib)/(.+)$', relative)
            if data_dir:
                relative = data_dir.group(2)
            elif re.match(r'[^/]+\.data/', relative):
                continue  # scripts / headers: not used by the programs
            target = site_packages / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))


def unpack_sdist(archive_path, site_packages):
    """Copy the top-level modules of a pure-Python source archive (no build step, no setup.py run).
    Refused when it has anything to compile or declares dependencies we would miss."""
    with tarfile.open(str(archive_path)) as archive:
        members = [item for item in archive.getmembers() if item.isfile()]
        names = [item.name for item in members]
        if any(name.endswith(('.c', '.cpp', '.pyx', '.h')) for name in names):
            raise SystemExit('%s is not pure Python' % archive_path.name)
        top_file = next((name for name in names if name.count('/') == 2 and name.endswith('.egg-info/top_level.txt')), None)
        requires = next((name for name in names if name.count('/') == 2 and name.endswith('.egg-info/requires.txt')), None)
        if top_file is None:
            raise SystemExit('%s has no top_level.txt' % archive_path.name)
        if requires and archive.extractfile(requires).read().strip():
            raise SystemExit('%s has dependencies; publish a wheel instead' % archive_path.name)
        root = top_file.split('/')[0]
        tops = archive.extractfile(top_file).read().decode('utf-8').split()
        copied = 0
        for item in members:
            relative = item.name[len(root) + 1:]
            if relative.split('/')[0] in tops and relative.endswith('.py') or relative in [top + '.py' for top in tops]:
                target = site_packages / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(item).read())
                copied += 1
        if not copied:
            raise SystemExit('nothing to copy from %s' % archive_path.name)


def build_runtime(app_files, data, work=None):
    """Return build/portable/<release>/runtime: the Python and packages the release ZIP carries."""
    work = work or (REPO / 'build' / 'portable')
    runtime = work / data['release'] / 'runtime'
    if runtime.exists():
        shutil.rmtree(str(runtime))
    runtime.mkdir(parents=True)
    unpack_python(nuget_python(work / 'cache'), runtime)
    for folder in ('wheels', 'sdist'):
        (work / 'cache' / folder).mkdir(parents=True, exist_ok=True)
    packages = resolve(app_files, work / 'cache')
    site_packages = runtime / 'Lib' / 'site-packages'
    for package in packages:
        (unpack_wheel if package.suffix == '.whl' else unpack_sdist)(package, site_packages)
    for name in list(data['modules']) + list(data.get('windows_modules', [])):
        if not ((site_packages / name).is_dir() or (site_packages / (name + '.py')).is_file()):
            raise SystemExit('module %s is not in the portable runtime' % name)
    (runtime / MARKER_FILE).write_text(json.dumps({
        'python': PYTHON_VERSION, 'source': NUGET_URL.format(PYTHON_VERSION),
        'packages': [package.name for package in packages]}, indent=1), encoding='utf-8')
    return runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', default='')
    args = parser.parse_args()
    built = 0
    for app_files, data in programs(args.release.strip()):
        runtime = build_runtime(app_files, data)
        size = sum(path.stat().st_size for path in runtime.rglob('*') if path.is_file())
        print('runtime %s: %.1f MB' % (runtime.relative_to(REPO), size / 1e6))
        print('\n'.join('  ' + name for name in json.loads((runtime / MARKER_FILE).read_text(encoding='utf-8'))['packages']))
        built += 1
    if not built:
        print('no program with "portable": true%s' % (' for ' + args.release if args.release else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
