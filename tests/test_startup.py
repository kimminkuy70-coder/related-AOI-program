# -*- coding: utf-8 -*-
"""Regression tests for the startup fixes (run with an environment that has pywebview).

    AOI_TOOLS_HOME=/tmp/aoi_test python -m unittest discover -s tests -v
"""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROGRAMS = {'aoi': REPO / 'programs' / 'AOI_Color_Gray_Matcher' / 'app_files',
            'wafer': REPO / 'programs' / 'Wafer_Map_Converter' / 'app_files'}
JS_CALLS = {'aoi': {'choose_folder', 'cancel_scan', 'choose_output', 'start', 'get_state', 'cancel_job', 'open_result', 'new_job'},
            'wafer': {'choose_folder', 'choose_output', 'get_state', 'start', 'cancel_job', 'open_root', 'new_job',
                      'open_file', 'show_in_folder', 'get_image', 'open_source'}}
os.environ.setdefault('AOI_TOOLS_HOME', tempfile.mkdtemp(prefix='aoi_tools_test_'))


def load_program(name):
    """Import app.py/engine.py/runtime.py of one program as fresh modules."""
    folder = str(PROGRAMS[name])
    for module in ('app', 'engine', 'runtime', 'setup_env'):
        sys.modules.pop(module, None)
    sys.path.insert(0, folder)
    try:
        return importlib.import_module('app'), importlib.import_module('engine')
    finally:
        sys.path.remove(folder)


class Node:
    """Stand-in for window.native: a deep, self-referencing object graph like the
    WinForms/.NET tree that froze v15. A fresh child on every access defeats the
    id()-based dedupe in pywebview, exactly like pythonnet wrappers."""
    def __init__(self, depth=0):
        self._depth = depth

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        Node.accessed += 1
        if Node.accessed > 10000:
            raise RuntimeError('walked into window.native')
        return Node(self._depth + 1)

    def __dir__(self):
        return ['Controls', 'Parent', 'webview', 'CoreWebView2']


class FakeWebviewWindow:
    """Like webview.Window: a regular class instance (has __module__) with .native."""
    def __init__(self):
        self.native = Node()

    def evaluate_js(self, script):
        return None


class OldApi:
    """v15/v4 layout: the window stored as a public attribute."""
    def __init__(self):
        self.window = FakeWebviewWindow()

    def get_state(self):
        return {}


class JsApiExposureTest(unittest.TestCase):
    def exposed(self, name):
        import webview
        from webview import util
        app, engine = load_program(name)
        api = app.API(webview, engine)
        api._window = FakeWebviewWindow()
        captured = {}

        class FakeWindow:
            _js_api = api
            _functions = {}
            _expose_lock = threading.Lock()
            events = types.SimpleNamespace(before_load=threading.Event(), _pywebviewready=threading.Event(), loaded=threading.Event())

            def run_js(self, script):
                if 'functions' not in captured and '"func"' in script:
                    captured['functions'] = script

        Node.accessed = 0
        fake = FakeWindow()
        original = util.load_js_files
        util.load_js_files = lambda window, platform: ('', '%(functions)s')
        try:
            util.inject_pywebview('edgechromium', fake)
            self.assertTrue(fake.events.loaded.wait(10), 'pywebviewready never fired')
        finally:
            util.load_js_files = original
        return {entry['func'] for entry in json.loads(captured['functions'])}

    def test_only_js_methods_are_exposed(self):
        for name in PROGRAMS:
            with self.subTest(program=name):
                Node.accessed = 0
                funcs = self.exposed(name)
                self.assertEqual(funcs, JS_CALLS[name])
                self.assertEqual(Node.accessed, 0, 'window.native must not be walked')

    def test_old_layout_walks_window(self):
        """Documents the v15/v4 bug: a public .window makes pywebview walk native."""
        from webview import util
        api = OldApi()
        Node.accessed = 0
        state = {}

        class FakeWindow:
            _js_api = api
            _functions = {}
            _expose_lock = threading.Lock()
            events = types.SimpleNamespace(before_load=threading.Event(), _pywebviewready=threading.Event(), loaded=threading.Event())

            def run_js(self, script):
                state['script'] = script

        original = util.load_js_files
        util.load_js_files = lambda window, platform: ('', '%(functions)s')
        try:
            util.inject_pywebview('edgechromium', FakeWindow())
            FakeWindow.events.loaded.wait(10)
        finally:
            util.load_js_files = original
        self.assertGreater(Node.accessed, 1000)  # stopped only by the Node guard
        self.assertIn('window.evaluate_js', state['script'])  # and window methods leak to JS


class StartupCostTest(unittest.TestCase):
    def test_engine_imports_no_heavy_packages(self):
        for name, folder in PROGRAMS.items():
            with self.subTest(program=name):
                code = ('import sys; sys.path.insert(0, %r); import engine; '
                        'print(sorted(m for m in ("PIL", "openpyxl", "numpy", "matplotlib") if m in sys.modules))' % str(folder))
                out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True).stdout.strip()
                self.assertEqual(out, '[]')

    def test_inline_ui(self):
        for name in PROGRAMS:
            with self.subTest(program=name):
                app, _ = load_program(name)
                html = sys.modules['runtime'].inline_ui(app.UI_DIR)
                self.assertIn('<style>', html)
                self.assertNotIn('src="app.js"', html)
                self.assertIn('pywebview.api.new_job()', html)
                self.assertNotIn('location.reload()', html)
                self.assertNotIn('beforeunload', html)


class SetupEnvUnitTest(unittest.TestCase):
    def setUp(self):
        sys.modules.pop('setup_env', None)
        sys.path.insert(0, str(PROGRAMS['aoi']))
        self.setup_env = importlib.import_module('setup_env')
        sys.path.remove(str(PROGRAMS['aoi']))

    def cand(self, version, bits=64, venv=True):
        return self.setup_env.Candidate({'exe': '/py/%s-%d' % (version, bits), 'version': [int(x) for x in version.split('.')] + [0],
                                         'bits': bits, 'venv': venv, 'ensurepip': venv})

    def test_support_range(self):
        self.assertFalse(self.cand('3.8').usable)
        self.assertTrue(self.cand('3.9').usable)
        self.assertTrue(self.cand('3.14').usable)
        self.assertFalse(self.cand('3.15').usable)
        self.assertFalse(self.cand('3.12', venv=False).usable)

    def test_rank_prefers_64bit_then_newest(self):
        ranked = self.setup_env.rank([self.cand('3.13', 32), self.cand('3.10'), self.cand('3.12'), self.cand('3.8')])
        self.assertEqual([(c.version[:2], c.bits) for c in ranked], [((3, 12), 64), ((3, 10), 64), ((3, 13), 32)])

    def test_missing_modules(self):
        sys.path.insert(0, str(PROGRAMS['aoi']))
        sys.modules.pop('runtime', None)
        runtime = importlib.import_module('runtime')
        sys.path.remove(str(PROGRAMS['aoi']))
        self.assertEqual(runtime.missing_modules({'modules': ['json', 'surely_not_installed_pkg']}), ['surely_not_installed_pkg'])


# Every program in the release, including ones without the API(webview, engine) layout above.
ALL_PROGRAMS = list(PROGRAMS.values()) + [REPO / 'programs' / 'AOI_Photo_Sorter' / 'app_files']


class SharedFilesTest(unittest.TestCase):
    def test_shared_files_identical(self):
        for name in ('setup_env.py', 'runtime.py', 'constraints.txt'):
            for folder in ALL_PROGRAMS[1:]:
                self.assertEqual((ALL_PROGRAMS[0] / name).read_bytes(), (folder / name).read_bytes(), '%s: %s' % (folder.parent.name, name))

    def test_launchers_are_cp949_without_bom_and_crlf(self):
        for folder in ALL_PROGRAMS:
            manifest = json.loads((folder / 'app_manifest.json').read_text(encoding='utf-8'))
            launcher = folder.parent / (manifest['release'] + '.vbs')
            raw = launcher.read_bytes()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
            self.assertNotIn(b'\n', raw.replace(b'\r\n', b''))
            text = raw.decode('cp949')
            self.assertIn('Const APP_ID = "%s"' % manifest['app_id'], text)
            self.assertIn('Const ENV_REVISION = %d' % manifest['env_revision'], text)


if __name__ == '__main__':
    unittest.main()
