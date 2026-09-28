# -*- coding: utf-8 -*-
from pathlib import Path
from collections import Counter
import json
import logging
import os
import sys
import threading
import time
import runtime

MANIFEST = runtime.load_manifest()
APP_TITLE = MANIFEST['title']
UI_DIR = Path(__file__).parent / 'ui'

# pywebview exposes every public attribute of the js_api object to JS and walks
# non-callable ones recursively. Everything that is not a JS-callable method is
# therefore private ('_'), above all the window: walking window.native (the WinForms
# form and its .NET object tree) stalls the "Python API 연결 준비 중" stage.


class API:
    def __init__(self, webview, engine):
        self._webview = webview
        self._engine = engine
        self._html = ''
        self._window = None
        self._root = None
        self._items = []
        self._mode = 'txt'
        self._cancel = threading.Event()
        self._scan_cancel = threading.Event()
        self._shutdown_event = threading.Event()
        self._lock = threading.RLock()
        self._workers = []
        self._state = {'scan': 'idle', 'run': 'idle', 'percent': 0, 'logs': []}

    def _thread(self, target, *args):
        t = threading.Thread(target=target, args=args, daemon=True)
        self._workers.append(t)
        t.start()
        return t

    def choose_folder(self, mode):
        if self._shutdown_event.is_set():
            return {'cancelled': True}
        r = self._window.create_file_dialog(self._webview.FileDialog.FOLDER, allow_multiple=False)
        if not r:
            return {'cancelled': True}
        self._root = Path(r[0]); self._mode = mode
        self._scan_cancel.clear()
        with self._lock:
            self._state.update({'scan': 'running', 'scan_message': '폴더 검색 준비', 'scan_current': str(self._root), 'found': 0})
        self._thread(self._scan)
        return {'cancelled': False, 'root': str(self._root)}

    def _scan(self):
        try:
            files = self._engine.discover(self._root, ('.txt',) if self._mode == 'txt' else ('.xlsx', '.xlsm'))
            items = []
            for i, p in enumerate(files, 1):
                if self._scan_cancel.is_set() or self._shutdown_event.is_set():
                    break
                with self._lock:
                    self._state.update({'scan_message': f'{i}/{len(files)} 분석 중', 'scan_current': str(p), 'found': i})
                try:
                    if self._mode == 'txt':
                        d = self._engine.parse_txt(p); m = d['meta']
                        cnt = Counter(x for r in d['rows'] for x in r)
                        bins = {k: v for k, v in sorted(cnt.items()) if k not in ('000', '___')}
                        item = {'id': len(items), 'valid': True, 'path': str(p), 'relative': str(p.relative_to(self._root)), 'wafer': m.get('WAFER', p.stem), 'device': m.get('DEVICE', ''), 'lot': m.get('LOT', ''), 'size': f"{d['row_count']}x{d['col_count']}", 'bins': bins, 'error': ''}
                    else:
                        item = {'id': len(items), 'valid': True, 'path': str(p), 'relative': str(p.relative_to(self._root)), 'wafer': p.stem, 'device': '', 'lot': '', 'size': 'Excel', 'bins': {}, 'error': ''}
                except Exception as exc:
                    item = {'id': len(items), 'valid': False, 'path': str(p), 'relative': str(p.relative_to(self._root)), 'wafer': p.stem, 'device': '', 'lot': '', 'size': '-', 'bins': {}, 'error': str(exc)}
                items.append(item)
            self._items = items
            with self._lock:
                self._state.update({'scan': 'cancelled' if self._scan_cancel.is_set() else 'complete', 'items': items, 'found': len(items), 'scan_message': '검색 완료'})
        except Exception as exc:
            with self._lock:
                self._state.update({'scan': 'error', 'scan_message': str(exc)})

    def get_state(self):
        with self._lock:
            return json.loads(json.dumps(self._state, default=str))

    def start(self, ids):
        if self._shutdown_event.is_set():
            return {'ok': False, 'error': '프로그램 종료 중입니다.'}
        selected = [self._items[int(i)] for i in ids if self._items[int(i)]['valid']]
        if not selected:
            return {'ok': False, 'error': '정상 파일을 선택하세요.'}
        self._cancel.clear()
        with self._lock:
            self._state.update({'run': 'running', 'percent': 0, 'results': [], 'errors': [], 'total': len(selected)})
        self._thread(self._work, selected)
        return {'ok': True}

    def _work(self, items):
        results, errors = [], []
        for i, x in enumerate(items, 1):
            if self._cancel.is_set() or self._shutdown_event.is_set():
                break
            p = Path(x['path'])
            with self._lock:
                self._state.update({'message': p.name + ' 변환 중', 'current': str(p), 'processed': i - 1})
            try:
                if self._mode == 'txt':
                    out = p.with_name(p.stem + '_Map_Edit.xlsx'); self._engine.txt_to_excel(p, out)
                else:
                    out = p.with_name(p.stem + '_Converted.txt'); self._engine.excel_to_txt(p, out)
                results.append(str(out))
            except Exception as exc:
                errors.append({'path': str(p), 'error': str(exc)})
            with self._lock:
                self._state.update({'percent': round(i / len(items) * 100, 1), 'processed': i, 'results': results, 'errors': errors})
        with self._lock:
            stopped = self._cancel.is_set() or self._shutdown_event.is_set()
            self._state.update({'run': 'cancelled' if stopped else 'complete', 'percent': self._state.get('percent', 0) if stopped else 100})

    def cancel_job(self):
        self._cancel.set(); return True

    def open_root(self):
        if self._root and os.name == 'nt':
            os.startfile(self._root); return True
        return False

    def new_job(self):
        """Reload the inline page through pywebview (location.reload() cannot reload an HTML string)."""
        if self._shutdown_event.is_set():
            return False
        with self._lock:
            if self._state.get('run') == 'running' or self._state.get('scan') == 'running':
                return False
            self._root = None
            self._items = []
            self._state = {'scan': 'idle', 'run': 'idle', 'percent': 0, 'logs': []}
        self._window.load_html(self._html)
        return True

    def _begin_shutdown(self):
        self._shutdown_event.set(); self._cancel.set(); self._scan_cancel.set()
        with self._lock:
            self._state.update({'run': 'closing', 'scan': 'closing'})
        return True

    def _shutdown(self):
        self._begin_shutdown()
        # Give cooperative workers a short chance to observe the flags.
        deadline = time.time() + 0.8
        for worker in list(self._workers):
            remain = deadline - time.time()
            if remain <= 0:
                break
            if worker.is_alive():
                worker.join(timeout=min(0.15, remain))
        plt = sys.modules.get('matplotlib.pyplot')  # never import matplotlib just to close it
        if plt is not None:
            try:
                plt.close('all')
            except Exception:
                pass


def main():
    runtime.setup_logging(MANIFEST['app_id'])
    instance = runtime.SingleInstance(MANIFEST['app_id'])
    if not instance.acquired():
        if not runtime.focus_window(APP_TITLE):
            runtime.message_box(APP_TITLE, '프로그램이 이미 실행 중(또는 시작 중)입니다.', error=False)
        return
    missing = runtime.missing_modules(MANIFEST)
    if missing and runtime.request_repair(MANIFEST, 'missing: ' + ', '.join(missing)):
        return
    try:
        import webview
        import engine
    except ImportError as exc:
        if runtime.is_dependency_error(exc, MANIFEST) and runtime.request_repair(MANIFEST, exc):
            return
        raise
    job = runtime.WindowsJob()
    api = API(webview, engine)
    # Inline HTML: no local HTTP server thread and no port to collide with.
    api._html = runtime.inline_ui(UI_DIR)
    window = webview.create_window(APP_TITLE, html=api._html, js_api=api, width=1180, height=820, min_size=(980, 700), background_color='#0b1220')
    api._window = window
    closing_once = threading.Event()

    def on_closing():
        if closing_once.is_set():
            return True
        closing_once.set()
        api._begin_shutdown()
        return True

    def on_closed():
        api._shutdown()
        job.close()
        instance.close()
        # os._exit guarantees lingering daemon threads cannot keep pythonw.exe alive.
        os._exit(0)

    window.events.closing += on_closing
    window.events.closed += on_closed
    try:
        webview.start(gui='edgechromium', debug=os.environ.get('AOI_TOOLS_DEBUG') == '1',
                      private_mode=False, storage_path=runtime.webview_storage(MANIFEST['app_id']))
    finally:
        api._shutdown()
        job.close()
        instance.close()
        os._exit(0)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        logging.exception('startup failed')
        runtime.message_box(APP_TITLE, '프로그램 시작 중 오류가 발생했습니다.\n%s\n\n로그: %s' % (exc, runtime.TOOLS_ROOT / 'logs'))
        os._exit(1)
