# -*- coding: utf-8 -*-
"""Runtime helpers shared by the AOI tools (identical copy in every program).

Only the standard library is imported here, so app.py can take the
single-instance lock and handle a broken environment before loading
pywebview or any heavy package.
"""
import ctypes
import json
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
from pathlib import Path

IS_WIN = os.name == 'nt'
HERE = Path(__file__).resolve().parent


def tools_root():
    override = os.environ.get('AOI_TOOLS_HOME')
    if override:
        return Path(override)
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / '.local' / 'share')
    return Path(base) / 'AOI_Tools'


TOOLS_ROOT = tools_root()


def load_manifest():
    return json.loads((HERE / 'app_manifest.json').read_text(encoding='utf-8'))


def setup_logging(app_id):
    log_dir = TOOLS_ROOT / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / ('%s.log' % app_id)
    handler = logging.handlers.RotatingFileHandler(str(path), maxBytes=1024 * 1024, backupCount=1, encoding='utf-8')
    handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s %(name)s: %(message)s'))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return path


def message_box(title, text, error=True):
    if IS_WIN:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)
    else:
        sys.stderr.write('%s: %s\n' % (title, text))


class SingleInstance:
    """Named mutex per program. GetLastError is read through use_last_error so
    ctypes cannot overwrite it between CreateMutexW and the check."""
    def __init__(self, app_id):
        self.handle = None
        if not IS_WIN:
            return
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        self.kernel32 = kernel32
        self.handle = kernel32.CreateMutexW(None, False, 'Local\\AOI_Tools_App_' + app_id)
        self.already_running = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS

    def acquired(self):
        # If the mutex cannot be created at all, start anyway rather than refuse to run.
        return not IS_WIN or not self.handle or not self.already_running

    def close(self):
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None


def focus_window(title):
    """Bring an already running instance to the front. Returns True when found."""
    if not IS_WIN:
        return False
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = ctypes.c_void_p
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    user32.ShowWindow(ctypes.c_void_p(hwnd), 9)  # SW_RESTORE
    user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    return True


class WindowsJob:
    """Own only this process and the WebView2 processes it starts.

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE ends this instance's WebView2 children when
    the Python host exits, without touching Teams, Outlook or another app's WebView2.
    """
    def __init__(self):
        self.handle = None
        if not IS_WIN:
            return
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.SetInformationJobObject.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        kernel32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        self.kernel32 = kernel32

        class BASIC(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', ctypes.c_uint32), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', ctypes.c_uint32),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', ctypes.c_uint32), ('SchedulingClass', ctypes.c_uint32)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                                                             'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

        class EXTENDED(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', BASIC), ('IoInfo', IO), ('ProcessMemoryLimit', ctypes.c_size_t),
                        ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)) \
                or not kernel32.AssignProcessToJobObject(handle, kernel32.GetCurrentProcess()):
            # A corporate launcher may already own a Job Object; startup must not fail.
            kernel32.CloseHandle(handle)
            return
        self.handle = handle

    def close(self):
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None


def webview_storage(app_id):
    """Persistent WebView2 profile per program: no cold profile creation on every start,
    and two programs never share (and lock) one user data folder."""
    path = TOOLS_ROOT / 'webview2' / app_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def missing_modules(manifest):
    """Required packages that are not installed. find_spec only looks at the file
    system, so this is cheap even though the packages themselves load lazily."""
    import importlib.util
    names = list(manifest['modules']) + (list(manifest.get('windows_modules', [])) if IS_WIN else [])
    missing = []
    for name in names:
        try:
            if importlib.util.find_spec(name) is None:
                missing.append(name)
        except (ImportError, ValueError):
            missing.append(name)
    return missing


def is_dependency_error(exc, manifest):
    name = (getattr(exc, 'name', None) or '').split('.')[0]
    return name in set(manifest['modules']) | set(manifest.get('windows_modules', []))


def request_repair(manifest, exc):
    """A required package is missing or broken: hand over to setup_env.py --repair.

    It runs on the base interpreter, not this venv, because the venv may be rebuilt.
    Returns False when repair already ran once for this start (avoid a loop)."""
    if os.environ.get('AOI_TOOLS_AFTER_SETUP') == '1':
        return False
    base = getattr(sys, '_base_executable', None) or sys.executable
    windowed = os.path.join(os.path.dirname(base), 'pythonw.exe')
    runner = windowed if IS_WIN and os.path.isfile(windowed) else base
    logging.getLogger(__name__).warning('dependency import failed (%s), starting repair with %s', exc, runner)
    flags = (0x00000008 | 0x00000200) if IS_WIN else 0
    subprocess.Popen([runner, str(HERE / 'setup_env.py'), '--repair'], cwd=str(HERE), close_fds=True, creationflags=flags)
    return True


def inline_ui(ui_dir):
    """index.html with styles.css and app.js inlined (no local HTTP server needed)."""
    html = (ui_dir / 'index.html').read_text(encoding='utf-8')
    css = (ui_dir / 'styles.css').read_text(encoding='utf-8')
    js = (ui_dir / 'app.js').read_text(encoding='utf-8')
    link, script = '<link rel="stylesheet" href="styles.css">', '<script src="app.js"></script>'
    if link not in html or script not in html:
        raise RuntimeError('index.html 형식이 예상과 다릅니다 (styles.css/app.js 태그 없음).')
    return html.replace(link, '<style>' + css + '</style>').replace(script, '<script>' + js + '</script>')
