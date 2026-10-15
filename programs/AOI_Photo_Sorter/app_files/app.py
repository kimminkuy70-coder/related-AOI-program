# -*- coding: utf-8 -*-
from pathlib import Path
import logging
import os
import subprocess
import sys
import runtime

MANIFEST = runtime.load_manifest()
APP_TITLE = MANIFEST['title']
UI_DIR = Path(__file__).parent / 'ui'
DATA_DIR = runtime.TOOLS_ROOT / 'Photo_Sorter'  # settings.json, sessions\
# The standalone .exe (tools/build_exe.py, PyInstaller): Python and every package are inside,
# so there is no environment to check or repair; settings and sessions are the same files.
FROZEN = bool(getattr(sys, 'frozen', False))
# The portable ZIP (tools/build_portable.py) runs this file with runtime\pythonw.exe next to
# app_files: the official Python with every package inside. Like the .exe there is nothing to
# repair; a missing package means the ZIP was not fully extracted.
PORTABLE = Path(sys.executable).resolve().parent == Path(__file__).resolve().parent.parent / 'runtime'

# pywebview exposes every public attribute of the js_api object to JS and walks
# non-callable ones recursively. Everything that is not a JS-callable method is
# therefore private ('_'), above all the window: walking window.native (the WinForms
# form and its .NET object tree) stalls the "Python API 연결 준비 중" stage.


class API:
    """pywebview bridge: native dialogs and Explorer only. Photos and state go through
    server.py, because the bridge answers via ExecuteScript on the UI thread."""

    def __init__(self, webview, controller):
        self._webview = webview
        self._controller = controller
        self._window = None

    def choose_folder(self, initial=''):
        if self._controller.closing:
            return ''
        result = self._window.create_file_dialog(self._webview.FileDialog.FOLDER, directory=initial or '', allow_multiple=False)
        return str(result[0]) if result else ''

    def open_path(self, path):
        """Open the photo folder, the output folder or a saved result file (nothing else)."""
        if not self._controller.can_open(path):
            return False
        if os.name == 'nt':
            os.startfile(path)
        else:
            subprocess.Popen(['xdg-open', str(path)])
        return True


def main():
    runtime.setup_logging(MANIFEST['app_id'])
    instance = runtime.SingleInstance(MANIFEST['app_id'])
    if not instance.acquired():
        if not runtime.focus_window(APP_TITLE):
            runtime.message_box(APP_TITLE, '프로그램이 이미 실행 중(또는 시작 중)입니다.', error=False)
        return
    missing = [] if FROZEN else runtime.missing_modules(MANIFEST)
    if missing and PORTABLE:
        raise RuntimeError('runtime 폴더에 %s 이(가) 없습니다. ZIP 전체를 새 로컬 폴더에 다시 압축 해제하세요.'
                           % ', '.join(missing))
    if missing and runtime.request_repair(MANIFEST, 'missing: ' + ', '.join(missing)):
        return
    try:
        import webview
        import server
    except ImportError as exc:
        if not FROZEN and not PORTABLE and runtime.is_dependency_error(exc, MANIFEST) and runtime.request_repair(MANIFEST, exc):
            return
        raise
    job = runtime.WindowsJob()
    controller = server.Controller(DATA_DIR, title=APP_TITLE)
    web = server.Server(controller, runtime.inline_ui(UI_DIR))
    api = API(webview, controller)
    window = webview.create_window(APP_TITLE, url=web.url, js_api=api, width=1280, height=900, min_size=(960, 680),
                                   maximized=True, background_color='#0b1220')
    api._window = window

    def on_closing():
        controller.close()  # writes the session before the window goes away
        return True

    window.events.closing += on_closing
    try:
        webview.start(gui='edgechromium', debug=os.environ.get('AOI_TOOLS_DEBUG') == '1',
                      private_mode=False, storage_path=runtime.webview_storage(MANIFEST['app_id']))
    finally:
        controller.close()
        web.close()
        job.close()
        instance.close()
        # os._exit guarantees lingering daemon threads cannot keep pythonw.exe alive.
        os._exit(0)


if __name__ == '__main__':
    if sys.argv[1:2] in (['--selftest'], ['--selftest-window']):  # build check of the .exe
        import selftest
        os._exit(selftest.run(sys.argv[1:], APP_TITLE, UI_DIR))
    try:
        main()
    except Exception as exc:
        logging.exception('startup failed')
        runtime.message_box(APP_TITLE, '프로그램 시작 중 오류가 발생했습니다.\n%s\n\n로그: %s' % (exc, runtime.TOOLS_ROOT / 'logs'))
        os._exit(1)
