# -*- coding: utf-8 -*-
from pathlib import Path
from collections import Counter
import base64
import io
import json
import logging
import os
import subprocess
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


def _key(path):
    return os.path.normcase(os.path.abspath(str(path)))


def _open(path):
    if not path or not Path(path).exists():
        return False
    if os.name == 'nt':
        os.startfile(path)
    else:
        subprocess.Popen(['xdg-open', str(path)])
    return True


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
        self._allowed = set()
        self._images = {}

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

    def choose_output(self):
        if self._shutdown_event.is_set():
            return ''
        r = self._window.create_file_dialog(self._webview.FileDialog.FOLDER, allow_multiple=False)
        return str(r[0]) if r else ''

    def start(self, ids, output=''):
        if self._shutdown_event.is_set():
            return {'ok': False, 'error': '프로그램 종료 중입니다.'}
        selected = [self._items[int(i)] for i in ids if self._items[int(i)]['valid']]
        if not selected:
            return {'ok': False, 'error': '정상 파일을 선택하세요.'}
        output_root = Path(output) if output else None
        if output_root is not None:
            try:
                output_root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return {'ok': False, 'error': '저장 위치를 만들 수 없습니다: %s' % exc}
        self._cancel.clear()
        with self._lock:
            self._allowed = set()
            self._images = {}
            self._state.update({'run': 'running', 'percent': 0, 'results': [], 'errors': [], 'total': len(selected),
                                'output_root': str(output_root) if output_root else '', 'source_root': str(self._root)})
        self._thread(self._work, selected, output_root)
        return {'ok': True}

    def _target(self, source, output_root):
        """Result path. With a custom location the source sub-folders are kept, so
        maps with the same name in different folders never overwrite each other."""
        name = source.stem + ('_Map_Edit.xlsx' if self._mode == 'txt' else '_Converted.txt')
        if output_root is None:
            return source.with_name(name)
        folder = output_root / source.parent.relative_to(self._root)
        folder.mkdir(parents=True, exist_ok=True)
        return folder / name

    def _work(self, items, output_root=None):
        results, errors = [], []
        for i, x in enumerate(items, 1):
            if self._cancel.is_set() or self._shutdown_event.is_set():
                break
            p = Path(x['path'])
            with self._lock:
                self._state.update({'message': p.name + ' 변환 중', 'current': str(p), 'processed': i - 1})
            try:
                out = self._target(p, output_root)
                convert = self._engine.txt_to_excel if self._mode == 'txt' else self._engine.excel_to_txt
                made = convert(p, out)
                result = {'wafer': x['wafer'], 'lot': x.get('lot', ''), 'device': x.get('device', ''),
                          'source': str(p), 'source_relative': x['relative'],
                          'source_type': 'TXT' if self._mode == 'txt' else 'Excel',
                          'output': made['output'], 'output_name': Path(made['output']).name,
                          'output_type': 'Excel' if self._mode == 'txt' else 'TXT',
                          'folder': str(Path(made['output']).parent), 'images': made['images']}
                with self._lock:
                    self._allowed.update([_key(p), _key(made['output'])] + [_key(img['path']) for img in made['images']])
                results.append(result)
            except Exception as exc:
                logging.exception('convert failed: %s', p)
                errors.append({'path': str(p), 'relative': x['relative'], 'error': str(exc)})
            with self._lock:
                self._state.update({'percent': round(i / len(items) * 100, 1), 'processed': i, 'results': results, 'errors': errors})
        with self._lock:
            stopped = self._cancel.is_set() or self._shutdown_event.is_set()
            self._state.update({'run': 'cancelled' if stopped else 'complete', 'percent': self._state.get('percent', 0) if stopped else 100})

    def cancel_job(self):
        self._cancel.set(); return True

    def open_source(self, index):
        """Open a map found by the folder scan (by list index, so JS cannot name arbitrary paths)."""
        try:
            path = self._items[int(index)]['path']
        except (IndexError, ValueError, TypeError):
            return False
        return _open(path)

    def open_root(self):
        target = self._state.get('output_root') or (str(self._root) if self._root else '')
        return _open(target) if target else False

    def _allowed_path(self, path):
        # JS may only open files this job read or produced.
        with self._lock:
            return bool(path) and _key(path) in self._allowed and Path(path).exists()

    def open_file(self, path):
        return _open(path) if self._allowed_path(path) else False

    def show_in_folder(self, path):
        if not self._allowed_path(path):
            return False
        if os.name == 'nt':
            subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
            return True
        return _open(str(Path(path).parent))

    def get_image(self, path, thumb=False):
        """PNG as a data URL; the inline page cannot load file:// images itself."""
        if not self._allowed_path(path):
            return ''
        cache_key = (_key(path), bool(thumb))
        if cache_key not in self._images:
            if thumb:
                from PIL import Image
                with Image.open(path) as image:
                    image.thumbnail((720, 720))
                    buffer = io.BytesIO()
                    image.convert('RGB').save(buffer, 'JPEG', quality=85)
                data = 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')
            else:
                data = 'data:image/png;base64,' + base64.b64encode(Path(path).read_bytes()).decode('ascii')
            self._images[cache_key] = data
        return self._images[cache_key]

    def new_job(self):
        """Reload the inline page through pywebview (location.reload() cannot reload an HTML string)."""
        if self._shutdown_event.is_set():
            return False
        with self._lock:
            if self._state.get('run') == 'running' or self._state.get('scan') == 'running':
                return False
            self._root = None
            self._items = []
            self._allowed = set()
            self._images = {}
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
