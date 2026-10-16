# -*- coding: utf-8 -*-
"""Shared Python environment setup for the AOI tools.

This file is identical in every program (tools/build_release.py checks it).
The .vbs launcher runs it only when its fast path is not available:

1. find every installed Python and pick the best supported one
   (3.9-3.14, 64-bit preferred, an existing environment reused first)
2. create one shared venv per Python version under %LOCALAPPDATA%\\AOI_Tools\\env
3. pip install this program's requirements online (compiled packages as wheels only)
4. verify the imports, write the ready file the launcher reads, start the program

Keep the syntax compatible with Python 3.6 so an old default Python can still
run this file and report a clear message instead of failing silently.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
IS_WIN = os.name == 'nt'
NO_WINDOW = 0x08000000 if IS_WIN else 0
DETACHED = (0x00000008 | 0x00000200) if IS_WIN else 0  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

SUPPORTED_MIN = (3, 9)
SUPPORTED_MAX = (3, 14)
RECOMMENDED = '3.12'
# Packages with C extensions: never fall back to a source build (slow, needs a compiler).
BINARY_ONLY = 'numpy,matplotlib,pillow,contourpy,kiwisolver,fonttools,pythonnet,clr-loader,cffi,pycparser'
WEBVIEW2_URL = 'https://developer.microsoft.com/microsoft-edge/webview2/'
PYTHON_URL = 'https://www.python.org/downloads/windows/'
WEBVIEW2_CLIENT = r'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'


def tools_root():
    override = os.environ.get('AOI_TOOLS_HOME')
    if override:
        return Path(override)
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / '.local' / 'share')
    return Path(base) / 'AOI_Tools'


TOOLS_ROOT = tools_root()
ENV_ROOT = TOOLS_ROOT / 'env'
READY_DIR = TOOLS_ROOT / 'ready'
LOG_DIR = TOOLS_ROOT / 'logs'


class SetupError(Exception):
    """A failure with a user-facing Korean message.

    try_next: the chosen Python cannot satisfy the requirements, so another
    installed Python may still work.
    """
    def __init__(self, message, try_next=False):
        Exception.__init__(self, message)
        self.try_next = try_next


def load_manifest():
    data = json.loads((HERE / 'app_manifest.json').read_text(encoding='utf-8'))
    modules = list(data['modules'])
    if IS_WIN:
        modules += data.get('windows_modules', [])
    data['check_modules'] = modules
    return data


# ---------------------------------------------------------------- logging

class Log:
    def __init__(self, app_id):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.path = LOG_DIR / ('setup_%s.log' % app_id)
        if self.path.exists() and self.path.stat().st_size > 1024 * 1024:
            self.path.replace(self.path.with_suffix('.old.log'))
        self.lock = threading.Lock()

    def write(self, text):
        line = '[%s] %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), text.rstrip())
        with self.lock:
            with self.path.open('a', encoding='utf-8', errors='replace') as handle:
                handle.write(line)


# ---------------------------------------------------------------- python discovery

PROBE = (
    'import sys,struct,json,importlib.util as u;'
    'print(json.dumps({"version":list(sys.version_info[:3]),"bits":struct.calcsize("P")*8,'
    '"exe":sys.executable,"base_exe":getattr(sys,"_base_executable",sys.executable),'
    '"prefix":sys.prefix,"base_prefix":getattr(sys,"base_prefix",sys.prefix),'
    '"venv":u.find_spec("venv") is not None,"ensurepip":u.find_spec("ensurepip") is not None}))'
)


class Candidate:
    def __init__(self, info):
        self.exe = info['exe']
        self.version = tuple(info['version'])
        self.bits = info['bits']
        self.has_venv = info['venv'] and info['ensurepip']
        self.reason = ''
        if self.version[:2] < SUPPORTED_MIN or self.version[:2] > SUPPORTED_MAX:
            self.reason = '지원 범위(%d.%d~%d.%d) 밖의 버전' % (SUPPORTED_MIN + SUPPORTED_MAX)
        elif not self.has_venv:
            self.reason = 'venv/ensurepip 모듈 없음'

    @property
    def usable(self):
        return not self.reason

    @property
    def key(self):
        return 'py%d%d-%s' % (self.version[0], self.version[1], 'x64' if self.bits == 64 else 'x86')

    @property
    def label(self):
        return 'Python %s (%dbit) %s' % ('.'.join(map(str, self.version)), self.bits, self.exe)


def _norm(path):
    return os.path.normcase(os.path.realpath(str(path)))


def _is_store_stub(path):
    # The bare aliases in %LOCALAPPDATA%\Microsoft\WindowsApps (python.exe, python3.exe)
    # open the Store when Python is absent. A real Microsoft Store Python lives in a
    # package sub-folder (WindowsApps\PythonSoftwareFoundation.Python.3.x_...) and is kept.
    return IS_WIN and os.path.normcase(os.path.dirname(os.path.abspath(str(path)))).endswith(os.path.normcase('\\Microsoft\\WindowsApps'))


def _py_launcher_paths():
    names = []
    found = shutil.which('py')
    if found:
        names.append(found)
    for base in (os.environ.get('WINDIR'), os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Python', 'Launcher')):
        if base:
            names.append(os.path.join(base, 'py.exe'))
    return [p for p in dict.fromkeys(names) if os.path.isfile(p)]


def _from_py_launcher():
    out = []
    for launcher in _py_launcher_paths():
        try:
            text = subprocess.run([launcher, '-0p'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True, timeout=15, creationflags=NO_WINDOW).stdout
        except Exception:
            continue
        for line in text.splitlines():
            match = re.search(r'([A-Za-z]:\\.*?\.exe)\s*$', line.strip())
            if match:
                out.append(match.group(1))
        if out:
            break
    return out


def _from_registry():
    if not IS_WIN:
        return []
    import winreg
    out = []
    views = (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY)
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in views:
            try:
                root = winreg.OpenKey(hive, r'Software\Python', 0, winreg.KEY_READ | view)
            except OSError:
                continue
            with root:
                for company in _subkeys(winreg, root):
                    if company == 'PyLauncher':
                        continue
                    try:
                        company_key = winreg.OpenKey(root, company)
                    except OSError:
                        continue
                    with company_key:
                        for tag in _subkeys(winreg, company_key):
                            exe = _registry_exe(winreg, company_key, tag)
                            if exe:
                                out.append(exe)
    return out


def _subkeys(winreg, key):
    index = 0
    while True:
        try:
            yield winreg.EnumKey(key, index)
        except OSError:
            return
        index += 1


def _registry_exe(winreg, company_key, tag):
    try:
        with winreg.OpenKey(company_key, tag + r'\InstallPath') as install:
            try:
                return winreg.QueryValueEx(install, 'ExecutablePath')[0]
            except OSError:
                return os.path.join(winreg.QueryValueEx(install, '')[0], 'python.exe')
    except OSError:
        return None


def _from_path():
    names = ['python', 'python3'] + ['python3.%d' % minor for minor in range(SUPPORTED_MIN[1], SUPPORTED_MAX[1] + 1)]
    return [p for p in (shutil.which(n) for n in names) if p and not _is_store_stub(p)]


def _base_of_current():
    # When this file runs inside one of our venvs (repair), use its base interpreter.
    base = getattr(sys, '_base_executable', None) or sys.executable
    return [base, sys.executable]


def probe(exe, timeout=20):
    console = os.path.join(os.path.dirname(exe), 'python.exe')
    if os.path.basename(exe).lower() == 'pythonw.exe' and os.path.isfile(console):
        exe = console  # pythonw has no usable stdout for the probe
    try:
        result = subprocess.run([exe, '-I', '-c', PROBE], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True, timeout=timeout, creationflags=NO_WINDOW)
        info = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception:
        return None
    if info['prefix'] != info['base_prefix']:
        # A venv interpreter: describe its base Python instead.
        base = info['base_exe']
        if not base or _norm(base) == _norm(info['exe']):
            base = os.path.join(info['base_prefix'], 'python.exe' if IS_WIN else 'bin/python3')
        return probe(base, timeout) if os.path.isfile(base) and _norm(base) != _norm(exe) else None
    return Candidate(info)


def find_candidates(log):
    raw = _from_py_launcher() + _from_registry() + _from_path() + _base_of_current()
    paths = []
    seen = set()
    for path in raw:
        if not path or not os.path.isfile(path) or _is_store_stub(path):
            continue
        key = _norm(path)
        if key not in seen:
            seen.add(key)
            paths.append(path)
    results = [None] * len(paths)

    def run(index, path):
        results[index] = probe(path)

    threads = [threading.Thread(target=run, args=(i, p)) for i, p in enumerate(paths)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    candidates = []
    seen = set()
    for cand in results:
        if cand and _norm(cand.exe) not in seen:
            seen.add(_norm(cand.exe))
            candidates.append(cand)
            log.write('found %s%s' % (cand.label, ' -> ' + cand.reason if cand.reason else ''))
    return candidates


def rank(candidates):
    usable = [c for c in candidates if c.usable]
    # Reuse an environment that already works for this Python, then prefer 64-bit, then newest.
    usable.sort(key=lambda c: (env_python(ENV_ROOT / c.key).exists() and _env_base_matches(ENV_ROOT / c.key, c), c.bits == 64, c.version), reverse=True)
    return usable


# ---------------------------------------------------------------- environment

def env_python(env_dir, windowed=False):
    if IS_WIN:
        return env_dir / 'Scripts' / ('pythonw.exe' if windowed else 'python.exe')
    return env_dir / 'bin' / 'python'


def _read_meta(env_dir):
    try:
        return json.loads((env_dir / 'aoi_env.json').read_text(encoding='utf-8'))
    except Exception:
        return {}


def _write_meta(env_dir, meta):
    tmp = env_dir / 'aoi_env.json.tmp'
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(str(tmp), str(env_dir / 'aoi_env.json'))


def _env_base_matches(env_dir, cand):
    return _norm(_read_meta(env_dir).get('base', '')) == _norm(cand.exe)


def _healthy(env_dir, cand):
    if not env_python(env_dir).exists() or not _env_base_matches(env_dir, cand):
        return False
    try:
        return subprocess.run([str(env_python(env_dir)), '-I', '-c', 'import pip'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, creationflags=NO_WINDOW).returncode == 0
    except Exception:
        return False


def _forget_ready_files(env_dir):
    if not READY_DIR.exists():
        return
    for ready in READY_DIR.glob('*.txt'):
        try:
            lines = ready.read_text(encoding='utf-16').splitlines()
            if len(lines) > 3 and _norm(lines[3]) == _norm(env_dir):
                ready.unlink()
        except Exception:
            pass


def _remove_tree(path):
    for attempt in range(4):
        try:
            shutil.rmtree(str(path))
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 3:
                raise SetupError('기존 실행 환경을 지울 수 없습니다(사용 중).\n열려 있는 AOI 도구 프로그램을 모두 닫고 재시도하세요.\n%s' % path)
            time.sleep(1)


def ensure_env(cand, ui, log, rebuild=False):
    env_dir = ENV_ROOT / cand.key
    if not rebuild and _healthy(env_dir, cand):
        log.write('reuse env %s' % env_dir)
        return env_dir
    if env_dir.exists():
        log.write('rebuild env %s' % env_dir)
        _forget_ready_files(env_dir)
        _remove_tree(env_dir)
    ENV_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = ENV_ROOT / ('%s.tmp-%d' % (cand.key, os.getpid()))
    _remove_tree(tmp)
    ui.status('가상환경 생성 중 (1/3)', cand.label)
    result = subprocess.run([cand.exe, '-m', 'venv', str(tmp)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, errors='replace', timeout=600, creationflags=NO_WINDOW)
    log.write('venv rc=%s %s%s' % (result.returncode, result.stdout, ''))
    if result.returncode != 0:
        _remove_tree(tmp)
        raise SetupError('가상환경을 만들지 못했습니다: %s' % cand.label, try_next=True)
    _write_meta(tmp, {'base': cand.exe, 'version': list(cand.version), 'bits': cand.bits, 'apps': {}, 'created': time.strftime('%Y-%m-%d %H:%M:%S')})
    for attempt in range(6):  # antivirus may briefly hold new files
        try:
            os.replace(str(tmp), str(env_dir))
            break
        except OSError:
            if attempt == 5:
                raise SetupError('가상환경 폴더를 확정하지 못했습니다(백신 검사 중일 수 있음). 재시도하세요.')
            time.sleep(0.5)
    return env_dir


def requirement_hash():
    digest = hashlib.sha256()
    for name in ('requirements.txt', 'constraints.txt'):
        digest.update((HERE / name).read_bytes())
    return digest.hexdigest()[:16]


NETWORK_HINTS = ('ProxyError', 'SSLError', 'CERTIFICATE_VERIFY_FAILED', 'ConnectTimeout', 'ReadTimeout', 'NewConnectionError', 'Max retries exceeded', 'getaddrinfo failed', 'Temporary failure in name resolution')
INCOMPATIBLE_HINTS = ('No matching distribution found', 'Could not find a version that satisfies', 'ResolutionImpossible', 'requires a different Python')


def pip_install(env_dir, cand, manifest, ui, log):
    env = dict(os.environ)
    user_config = TOOLS_ROOT / 'pip.ini'
    if user_config.exists() and 'PIP_CONFIG_FILE' not in env:
        env['PIP_CONFIG_FILE'] = str(user_config)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    cmd = [str(env_python(env_dir)), '-m', 'pip', 'install',
           '-r', str(HERE / 'requirements.txt'), '-c', str(HERE / 'constraints.txt'),
           '--only-binary', BINARY_ONLY, '--prefer-binary',
           '--disable-pip-version-check', '--no-input', '--progress-bar', 'off',
           '--timeout', '30', '--retries', '3']
    log.write('pip: ' + ' '.join(cmd))
    ui.status('패키지 설치 중 (2/3) - 네트워크 속도에 따라 1~3분 소요', '')
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, errors='replace', env=env, creationflags=NO_WINDOW)
    tail = []
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        log.write('pip> ' + line)
        tail = (tail + [line])[-40:]
        if line.startswith(('Collecting', 'Downloading', 'Installing', 'Building', 'Successfully', 'Requirement already')):
            ui.status('패키지 설치 중 (2/3) - 네트워크 속도에 따라 1~3분 소요', line[:110])
    if proc.wait() == 0:
        return
    text = '\n'.join(tail)
    if any(h in text for h in INCOMPATIBLE_HINTS):
        raise SetupError('%s 용 패키지가 없습니다.' % cand.label, try_next=True)
    if any(h in text for h in NETWORK_HINTS):
        raise SetupError('패키지 서버(PyPI)에 연결하지 못했습니다.\n'
                         '- 사내 프록시/방화벽에서 pypi.org, files.pythonhosted.org 접근이 필요합니다.\n'
                         '- 사내 미러가 있으면 %s 에 index-url 을 지정하세요.\n'
                         '- 인증서 오류면 같은 파일에 cert = <사내 루트 인증서 경로> 를 지정하세요.' % user_config)
    raise SetupError('패키지 설치에 실패했습니다. 로그를 확인하세요.')


def verify(env_dir, manifest, log):
    script = ('import importlib,sys\nbad=[]\nfor m in sys.argv[1:]:\n'
              '    try: importlib.import_module(m)\n'
              '    except Exception as e: bad.append("%s: %s"%(m,e))\n'
              'print("\\n".join(bad)); sys.exit(1 if bad else 0)')
    result = subprocess.run([str(env_python(env_dir)), '-I', '-c', script] + manifest['check_modules'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, errors='replace', timeout=300, creationflags=NO_WINDOW)
    log.write('verify rc=%s %s' % (result.returncode, result.stdout))
    if result.returncode == 0:
        return None
    return result.stdout.strip() or 'import 실패'


def write_ready(env_dir, cand, manifest):
    READY_DIR.mkdir(parents=True, exist_ok=True)
    # UTF-16 so the .vbs launcher reads non-ASCII user paths correctly (OpenTextFile Unicode mode).
    lines = [str(manifest['env_revision']), str(env_python(env_dir, windowed=True)), cand.exe, str(env_dir)]
    target = READY_DIR / ('%s.txt' % manifest['app_id'])
    tmp = target.with_suffix('.tmp')
    tmp.write_text('\r\n'.join(lines) + '\r\n', encoding='utf-16')
    os.replace(str(tmp), str(target))


def remove_ready(app_id):
    try:
        (READY_DIR / ('%s.txt' % app_id)).unlink()
    except OSError:
        pass


# ---------------------------------------------------------------- cross-process lock

class InstallLock:
    """Serialises installs across programs so two first launches cannot race in pip."""
    def __init__(self):
        self.handle = None
        self.file = None

    def acquire(self, on_wait):
        if IS_WIN:
            import ctypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
            kernel32.ReleaseMutex.argtypes = (ctypes.c_void_p,)
            kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
            self.kernel32 = kernel32
            self.handle = kernel32.CreateMutexW(None, False, 'Local\\AOI_Tools_EnvSetup')
            waited = False
            while True:
                code = kernel32.WaitForSingleObject(self.handle, 500)
                if code in (0, 0x80):  # WAIT_OBJECT_0, WAIT_ABANDONED
                    return
                if not waited:
                    on_wait()
                    waited = True
        else:
            import fcntl
            TOOLS_ROOT.mkdir(parents=True, exist_ok=True)
            self.file = open(str(TOOLS_ROOT / 'setup.lock'), 'w')
            try:
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                on_wait()
                fcntl.flock(self.file, fcntl.LOCK_EX)

    def release(self):
        if self.handle:
            self.kernel32.ReleaseMutex(self.handle)
            self.kernel32.CloseHandle(self.handle)
            self.handle = None
        if self.file:
            self.file.close()
            self.file = None


# ---------------------------------------------------------------- checks

def webview2_installed():
    if not IS_WIN:
        return True
    import winreg
    locations = [(winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\WOW6432Node\\' + WEBVIEW2_CLIENT),
                 (winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\' + WEBVIEW2_CLIENT),
                 (winreg.HKEY_CURRENT_USER, 'Software\\' + WEBVIEW2_CLIENT)]
    for hive, path in locations:
        try:
            with winreg.OpenKey(hive, path) as key:
                version = winreg.QueryValueEx(key, 'pv')[0]
                if version and version != '0.0.0.0':
                    return True
        except OSError:
            continue
    return False


def no_python_message(candidates):
    lines = ['사용 가능한 Python이 없습니다.',
             'Python %d.%d ~ %d.%d (64bit 권장, %s 추천)을 설치한 뒤 다시 실행하세요.' % (SUPPORTED_MIN + SUPPORTED_MAX + (RECOMMENDED,)),
             PYTHON_URL]
    if candidates:
        lines.append('')
        lines.append('발견된 Python:')
        lines += ['- %s: %s' % (c.label, c.reason or '설치 실패') for c in candidates]
    return '\n'.join(lines)


# ---------------------------------------------------------------- main flow

def run_setup(manifest, ui, log, repair=False):
    ui.status('실행 환경 확인 중...', '설치된 Python 검색')
    candidates = find_candidates(log)
    ranked = rank(candidates)
    if not ranked:
        raise SetupError(no_python_message(candidates))
    if not webview2_installed():
        if ui.ask('Microsoft Edge WebView2 Runtime이 설치되어 있지 않습니다.\n\n다운로드 페이지를 열까요?\n(설치 후 프로그램을 다시 실행하세요. "아니요"를 누르면 그대로 진행합니다.)'):
            open_path(WEBVIEW2_URL)
            raise SetupError('WebView2 Runtime 설치 후 다시 실행하세요.')
    lock = InstallLock()
    lock.acquire(lambda: ui.status('다른 AOI 도구가 실행 환경을 설치 중입니다. 완료될 때까지 대기합니다...', ''))
    try:
        failures = []
        for cand in ranked:
            try:
                return install_for(cand, manifest, ui, log, repair)
            except SetupError as exc:
                log.write('candidate failed %s: %s' % (cand.label, exc))
                if not exc.try_next:
                    raise
                cand.reason = str(exc)
                failures.append(cand)
        raise SetupError(no_python_message(failures))
    finally:
        lock.release()


def install_for(cand, manifest, ui, log, repair):
    req_hash = requirement_hash()
    for rebuild in (False, True):
        env_dir = ensure_env(cand, ui, log, rebuild=rebuild)
        meta = _read_meta(env_dir)
        installed = meta.get('apps', {}).get(manifest['app_id'], {}).get('requirements') == req_hash
        if not installed or repair or rebuild:
            pip_install(env_dir, cand, manifest, ui, log)
        ui.status('설치 확인 중 (3/3)', ', '.join(manifest['check_modules']))
        problem = verify(env_dir, manifest, log)
        if problem is None:
            meta = _read_meta(env_dir)
            meta.setdefault('apps', {})[manifest['app_id']] = {'requirements': req_hash, 'revision': manifest['env_revision'], 'installed': time.strftime('%Y-%m-%d %H:%M:%S')}
            _write_meta(env_dir, meta)
            write_ready(env_dir, cand, manifest)
            return env_dir
        if [line.split(':')[0] for line in problem.splitlines()] == ['clr']:
            raise SetupError('.NET 런타임(pythonnet) 초기화에 실패했습니다.\n.NET Framework 4.7.2 이상이 필요합니다.\n\n' + problem[:600])
        log.write('verify failed, rebuild=%s' % (not rebuild))
    raise SetupError('설치 후 모듈 확인에 실패했습니다.\n' + problem[:600])


def launch(env_dir, manifest, log):
    entry = HERE / manifest['entry']
    env = dict(os.environ)
    env['AOI_TOOLS_AFTER_SETUP'] = '1'
    log.write('launch %s %s' % (env_python(env_dir, windowed=True), entry))
    subprocess.Popen([str(env_python(env_dir, windowed=True)), str(entry)], cwd=str(HERE), env=env, close_fds=True, creationflags=DETACHED)


def open_path(target):
    try:
        if IS_WIN:
            os.startfile(str(target))
        else:
            subprocess.Popen(['xdg-open', str(target)])
    except Exception:
        pass


# ---------------------------------------------------------------- UI

def message_box(title, text, error=True):
    if IS_WIN:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)
    else:
        sys.stderr.write('%s: %s\n' % (title, text))


class HeadlessUI:
    def __init__(self, title, log):
        self.title = title
        self.log = log

    def status(self, text, detail=''):
        self.log.write('status: %s %s' % (text, detail))

    def ask(self, text):
        self.log.write('ask (auto no): ' + text)
        return False

    def run(self, work):
        try:
            work()
            return 0
        except SetupError as exc:
            message_box(self.title, str(exc))
            return 1


class TkUI:
    BG = '#0b1220'

    def __init__(self, title, log):
        import tkinter as tk
        from tkinter import messagebox
        self.tk = tk
        self.messagebox = messagebox
        self.title = title
        self.log = log
        self.root = tk.Tk()
        self.root.title(title + ' - 실행 환경 설치')
        self.root.geometry('600x270')
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)
        tk.Label(self.root, text=title, bg=self.BG, fg='#eef6ff', font=('Segoe UI', 16, 'bold')).pack(anchor='w', padx=26, pady=(22, 2))
        tk.Label(self.root, text='최초 1회 실행 환경 설치 · 이후 실행에서는 생략됩니다', bg=self.BG, fg='#21c55d', font=('Segoe UI', 9, 'bold')).pack(anchor='w', padx=26)
        self.status_var = tk.StringVar(value='준비 중...')
        self.detail_var = tk.StringVar(value='')
        self.elapsed_var = tk.StringVar(value='경과 00:00')
        tk.Label(self.root, textvariable=self.status_var, bg=self.BG, fg='#dbe7f3', font=('Segoe UI', 10), wraplength=550, justify='left').pack(anchor='w', padx=26, pady=(20, 4))
        tk.Label(self.root, textvariable=self.detail_var, bg=self.BG, fg='#7f93a8', font=('Consolas', 8), wraplength=550, justify='left').pack(anchor='w', padx=26)
        tk.Label(self.root, textvariable=self.elapsed_var, bg=self.BG, fg='#60758a', font=('Consolas', 9)).pack(anchor='w', padx=26, pady=(8, 0))
        self.buttons = tk.Frame(self.root, bg=self.BG)
        self.buttons.pack(anchor='e', padx=26, pady=12)
        self.started = time.time()
        self.busy = False
        self.result = 1
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self._tick()

    def _tick(self):
        if self.busy:
            sec = int(time.time() - self.started)
            self.elapsed_var.set('경과 %02d:%02d' % (sec // 60, sec % 60))
        self.root.after(500, self._tick)

    def status(self, text, detail=''):
        self.log.write('status: %s %s' % (text, detail))
        self.root.after(0, self.status_var.set, text)
        self.root.after(0, self.detail_var.set, detail)

    def ask(self, text):
        answer = {}
        done = threading.Event()

        def show():
            answer['yes'] = self.messagebox.askyesno(self.title, text, parent=self.root)
            done.set()
        self.root.after(0, show)
        done.wait()
        return answer['yes']

    def close(self):
        if self.busy and not self.messagebox.askyesno(self.title, '설치를 중단할까요?\n다음 실행 때 다시 설치합니다.', parent=self.root):
            return
        self.root.destroy()

    def _clear_buttons(self):
        for child in self.buttons.winfo_children():
            child.destroy()

    def _fail(self, message):
        self.busy = False
        self.status_var.set('설치 실패')
        self.detail_var.set(message)
        self.root.geometry('600x%d' % min(560, 270 + 16 * message.count('\n')))
        self._clear_buttons()
        style = dict(bg='#1f2a3a', fg='#eef6ff', relief='flat', padx=14, pady=4, font=('Segoe UI', 9))
        self.tk.Button(self.buttons, text='재시도', command=self._start, **style).pack(side='left', padx=4)
        self.tk.Button(self.buttons, text='로그 열기', command=lambda: open_path(self.log.path), **style).pack(side='left', padx=4)
        self.tk.Button(self.buttons, text='닫기', command=self.root.destroy, **style).pack(side='left', padx=4)

    def _start(self):
        self._clear_buttons()
        self.busy = True
        self.started = time.time()
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            self.work()
            self.result = 0
            self.busy = False
            self.root.after(0, self.root.destroy)
        except SetupError as exc:
            self.root.after(0, self._fail, str(exc))
        except Exception as exc:
            self.log.write(traceback.format_exc())
            self.root.after(0, self._fail, '예상하지 못한 오류: %s\n로그: %s' % (exc, self.log.path))

    def run(self, work):
        self.work = work
        self._start()
        self.root.mainloop()
        return self.result


def make_ui(title, log, headless):
    if not headless:
        try:
            return TkUI(title, log)
        except Exception:
            log.write('tkinter unavailable, headless mode\n' + traceback.format_exc())
    return HeadlessUI(title, log)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--repair', action='store_true', help='reinstall after an import failure at program start')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--no-launch', action='store_true')
    args = parser.parse_args(argv)
    manifest = load_manifest()
    log = Log(manifest['app_id'])
    log.write('=== setup start app=%s python=%s repair=%s' % (manifest['app_id'], sys.version.split()[0], args.repair))
    if args.repair:
        remove_ready(manifest['app_id'])
    ui = make_ui(manifest['title'], log, args.headless)

    def work():
        started = time.time()
        env_dir = run_setup(manifest, ui, log, repair=args.repair)
        log.write('setup done in %.1fs' % (time.time() - started))
        if not args.no_launch:
            ui.status('프로그램 시작 중...', '')
            launch(env_dir, manifest, log)

    try:
        return ui.run(work)
    except Exception:
        log.write(traceback.format_exc())
        message_box(manifest['title'], '실행 환경 설치 중 오류가 발생했습니다.\n로그: %s' % log.path)
        return 1


if __name__ == '__main__':
    sys.exit(main())
