# -*- coding: utf-8 -*-
from pathlib import Path
import json
import logging
import os
import sys
import threading
import runtime

MANIFEST = runtime.load_manifest()
APP_TITLE = MANIFEST['title']
UI_DIR = Path(__file__).parent / 'ui'
# The portable ZIP (tools/build_portable.py) runs this file with runtime\pythonw.exe next to
# app_files: the official Python with every package inside. There is no shared environment to
# repair; a missing package means the ZIP was not fully extracted.
PORTABLE = Path(sys.executable).resolve().parent == Path(__file__).resolve().parent.parent / 'runtime'

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
        self._lock = threading.RLock()
        self._closing = threading.Event()
        self._state = {'root': '', 'items': []}

    def choose_folder(self):
        if self._closing.is_set():
            return {'cancelled': True}
        r = self._window.create_file_dialog(self._webview.FileDialog.FOLDER, allow_multiple=False)
        if not r:
            return {'cancelled': True}
        self._root = Path(r[0])
        with self._lock:
            self._state.update({'root': str(self._root), 'items': []})
        return {'cancelled': False, 'root': str(self._root)}

    def get_state(self):
        with self._lock:
            return json.loads(json.dumps(self._state, default=str))

    def new_job(self):
        """Reload the inline page through pywebview (location.reload() cannot reload an HTML string)."""
        if self._closing.is_set():
            return False
        with self._lock:
            self._root = None
            self._state = {'root': '', 'items': []}
        self._window.load_html(self._html)
        return True


def main():
    runtime.setup_logging(MANIFEST['app_id'])
    instance = runtime.SingleInstance(MANIFEST['app_id'])
    if not instance.acquired():
        if not runtime.focus_window(APP_TITLE):
            runtime.message_box(APP_TITLE, '프로그램이 이미 실행 중(또는 시작 중)입니다.', error=False)
        return
    missing = runtime.missing_modules(MANIFEST)
    if missing and PORTABLE:
        raise RuntimeError('runtime 폴더에 %s 이(가) 없습니다. ZIP 전체를 새 로컬 폴더에 다시 압축 해제하세요.'
                           % ', '.join(missing))
    if missing and runtime.request_repair(MANIFEST, 'missing: ' + ', '.join(missing)):
        return
    try:
        import webview
        import engine
    except ImportError as exc:
        if not PORTABLE and runtime.is_dependency_error(exc, MANIFEST) and runtime.request_repair(MANIFEST, exc):
            return
        raise
    job = runtime.WindowsJob()
    api = API(webview, engine)
    # Inline HTML: no local HTTP server thread and no port to collide with.
    api._html = runtime.inline_ui(UI_DIR)
    window = webview.create_window(APP_TITLE, html=api._html, js_api=api, width=1180, height=820,
                                   min_size=(980, 700), background_color='#0b1220')
    api._window = window

    def on_closing():
        api._closing.set()
        return True

    window.events.closing += on_closing
    try:
        webview.start(gui='edgechromium', debug=os.environ.get('AOI_TOOLS_DEBUG') == '1',
                      private_mode=False, storage_path=runtime.webview_storage(MANIFEST['app_id']))
    finally:
        job.close()
        instance.close()
        # os._exit guarantees lingering daemon threads cannot keep pythonw.exe alive.
        os._exit(0)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        logging.exception('startup failed')
        runtime.message_box(APP_TITLE, '프로그램 시작 중 오류가 발생했습니다.\n%s\n\n로그: %s' % (exc, runtime.TOOLS_ROOT / 'logs'))
        os._exit(1)
