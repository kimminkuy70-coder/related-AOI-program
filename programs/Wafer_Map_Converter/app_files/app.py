from pathlib import Path
from collections import Counter
import ctypes
import json
import os
import threading
import time
import webview
import engine

APP_TITLE = 'Wafer Map Converter WebView2 v4'


class WindowsJob:
    """Own only this app instance and its child processes.

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE ensures WebView2 child processes created
    by this app are terminated when the Python host exits, without killing
    WebView2 processes that belong to Teams, Outlook, or another application.
    """
    def __init__(self):
        self.handle = None
        if os.name != 'nt':
            return
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        CreateJobObjectW = kernel32.CreateJobObjectW
        CreateJobObjectW.restype = ctypes.c_void_p
        SetInformationJobObject = kernel32.SetInformationJobObject
        AssignProcessToJobObject = kernel32.AssignProcessToJobObject
        GetCurrentProcess = kernel32.GetCurrentProcess

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('PerProcessUserTimeLimit', ctypes.c_int64),
                ('PerJobUserTimeLimit', ctypes.c_int64),
                ('LimitFlags', ctypes.c_uint32),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', ctypes.c_uint32),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', ctypes.c_uint32),
                ('SchedulingClass', ctypes.c_uint32),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ('ReadOperationCount', ctypes.c_uint64),
                ('WriteOperationCount', ctypes.c_uint64),
                ('OtherOperationCount', ctypes.c_uint64),
                ('ReadTransferCount', ctypes.c_uint64),
                ('WriteTransferCount', ctypes.c_uint64),
                ('OtherTransferCount', ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ('IoInfo', IO_COUNTERS),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t),
            ]

        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        handle = CreateJobObjectW(None, None)
        if not handle:
            return
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not SetInformationJobObject(handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(handle)
            return
        if not AssignProcessToJobObject(handle, GetCurrentProcess()):
            # A corporate launcher may already place Python in a Job Object.
            # Normal shutdown still works; do not fail program startup.
            kernel32.CloseHandle(handle)
            return
        self.handle = handle

    def close(self):
        if self.handle and os.name == 'nt':
            ctypes.WinDLL('kernel32').CloseHandle(self.handle)
            self.handle = None


class API:
    def __init__(self):
        self.window = None
        self.root = None
        self.items = []
        self.mode = 'txt'
        self.cancel = threading.Event()
        self.scan_cancel = threading.Event()
        self.shutdown_event = threading.Event()
        self.lock = threading.RLock()
        self.workers = []
        self.state = {'scan': 'idle', 'run': 'idle', 'percent': 0, 'logs': []}

    def _thread(self, target, *args):
        t = threading.Thread(target=target, args=args, daemon=True)
        self.workers.append(t)
        t.start()
        return t

    def choose_folder(self, mode):
        if self.shutdown_event.is_set():
            return {'cancelled': True}
        r = self.window.create_file_dialog(webview.FileDialog.FOLDER, allow_multiple=False)
        if not r:
            return {'cancelled': True}
        self.root = Path(r[0]); self.mode = mode
        self.scan_cancel.clear()
        with self.lock:
            self.state.update({'scan': 'running', 'scan_message': '폴더 검색 준비', 'scan_current': str(self.root), 'found': 0})
        self._thread(self._scan)
        return {'cancelled': False, 'root': str(self.root)}

    def _scan(self):
        try:
            files = engine.discover(self.root, ('.txt',) if self.mode == 'txt' else ('.xlsx', '.xlsm'))
            items = []
            for i, p in enumerate(files, 1):
                if self.scan_cancel.is_set() or self.shutdown_event.is_set():
                    break
                with self.lock:
                    self.state.update({'scan_message': f'{i}/{len(files)} 분석 중', 'scan_current': str(p), 'found': i})
                try:
                    if self.mode == 'txt':
                        d = engine.parse_txt(p); m = d['meta']
                        cnt = Counter(x for r in d['rows'] for x in r)
                        bins = {k: v for k, v in sorted(cnt.items()) if k not in ('000', '___')}
                        item = {'id': len(items), 'valid': True, 'path': str(p), 'relative': str(p.relative_to(self.root)), 'wafer': m.get('WAFER', p.stem), 'device': m.get('DEVICE', ''), 'lot': m.get('LOT', ''), 'size': f"{d['row_count']}x{d['col_count']}", 'bins': bins, 'error': ''}
                    else:
                        item = {'id': len(items), 'valid': True, 'path': str(p), 'relative': str(p.relative_to(self.root)), 'wafer': p.stem, 'device': '', 'lot': '', 'size': 'Excel', 'bins': {}, 'error': ''}
                except Exception as exc:
                    item = {'id': len(items), 'valid': False, 'path': str(p), 'relative': str(p.relative_to(self.root)), 'wafer': p.stem, 'device': '', 'lot': '', 'size': '-', 'bins': {}, 'error': str(exc)}
                items.append(item)
            self.items = items
            with self.lock:
                self.state.update({'scan': 'cancelled' if self.scan_cancel.is_set() else 'complete', 'items': items, 'found': len(items), 'scan_message': '검색 완료'})
        except Exception as exc:
            with self.lock:
                self.state.update({'scan': 'error', 'scan_message': str(exc)})

    def get_state(self):
        with self.lock:
            return json.loads(json.dumps(self.state, default=str))

    def start(self, ids):
        if self.shutdown_event.is_set():
            return {'ok': False, 'error': '프로그램 종료 중입니다.'}
        selected = [self.items[int(i)] for i in ids if self.items[int(i)]['valid']]
        if not selected:
            return {'ok': False, 'error': '정상 파일을 선택하세요.'}
        self.cancel.clear()
        with self.lock:
            self.state.update({'run': 'running', 'percent': 0, 'results': [], 'errors': [], 'total': len(selected)})
        self._thread(self._work, selected)
        return {'ok': True}

    def _work(self, items):
        results, errors = [], []
        for i, x in enumerate(items, 1):
            if self.cancel.is_set() or self.shutdown_event.is_set():
                break
            p = Path(x['path'])
            with self.lock:
                self.state.update({'message': p.name + ' 변환 중', 'current': str(p), 'processed': i - 1})
            try:
                if self.mode == 'txt':
                    out = p.with_name(p.stem + '_Map_Edit.xlsx'); engine.txt_to_excel(p, out)
                else:
                    out = p.with_name(p.stem + '_Converted.txt'); engine.excel_to_txt(p, out)
                results.append(str(out))
            except Exception as exc:
                errors.append({'path': str(p), 'error': str(exc)})
            with self.lock:
                self.state.update({'percent': round(i / len(items) * 100, 1), 'processed': i, 'results': results, 'errors': errors})
        with self.lock:
            stopped = self.cancel.is_set() or self.shutdown_event.is_set()
            self.state.update({'run': 'cancelled' if stopped else 'complete', 'percent': self.state.get('percent', 0) if stopped else 100})

    def cancel_job(self):
        self.cancel.set(); return True

    def open_root(self):
        if self.root and os.name == 'nt':
            os.startfile(self.root); return True
        return False

    def begin_shutdown(self):
        """Called from JS before window.close when possible."""
        self.shutdown_event.set(); self.cancel.set(); self.scan_cancel.set()
        with self.lock:
            self.state.update({'run': 'closing', 'scan': 'closing'})
        return True

    def shutdown(self):
        self.begin_shutdown()
        # Give cooperative workers a short chance to observe the flags.
        deadline = time.time() + 0.8
        for worker in list(self.workers):
            remain = deadline - time.time()
            if remain <= 0:
                break
            if worker.is_alive():
                worker.join(timeout=min(0.15, remain))
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
        except Exception:
            pass


def main():
    job = WindowsJob()
    api = API()
    ui = Path(__file__).parent / 'ui' / 'index.html'
    window = webview.create_window(APP_TITLE, str(ui), js_api=api, width=1180, height=820, min_size=(980, 700), background_color='#0b1220')
    api.window = window
    closing_once = threading.Event()

    def on_closing():
        if closing_once.is_set():
            return True
        closing_once.set()
        api.begin_shutdown()
        return True

    def on_closed():
        api.shutdown()
        job.close()
        # os._exit guarantees that the local HTTP server and lingering daemon
        # threads cannot keep pythonw.exe alive after the window is closed.
        os._exit(0)

    window.events.closing += on_closing
    window.events.closed += on_closed
    try:
        webview.start(gui='edgechromium', debug=False, http_server=True)
    finally:
        api.shutdown()
        job.close()
        os._exit(0)


if __name__ == '__main__':
    main()
