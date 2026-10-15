# -*- coding: utf-8 -*-
"""Build check of the standalone .exe, run by tools/build_exe.py on the Windows build machine.

    AOI_Photo_Sorter_v10.exe --selftest report.json          packages and data files inside, the page
                                                             served, a photo folder sorted and saved
    AOI_Photo_Sorter_v10.exe --selftest-window report.json   the same, then WebView2 opens the page
                                                             and app.js runs in it

The .exe has no console: the result is the report file and the exit code (0 = passed).
"""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path


def run(args, title, ui_dir):
    window = args[0] == '--selftest-window'
    report_path = Path(args[1] if len(args) > 1 else 'selftest.json')
    report = {'ok': False, 'title': title, 'frozen': bool(getattr(sys, 'frozen', False)), 'python': sys.version, 'steps': []}

    def write():
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')

    def give_up():  # WebView2 never answered: say so instead of hanging the build
        report['error'] = 'timed out at: %s' % (report['steps'][-1] if report['steps'] else 'start')
        write()
        os._exit(3)

    watchdog = threading.Timer(150, give_up)
    watchdog.daemon = True
    watchdog.start()
    temp = tempfile.mkdtemp(prefix='aoi_selftest_')
    try:
        _checks(report, title, ui_dir, Path(temp), window)
        report['ok'] = True
    except BaseException:
        report['error'] = traceback.format_exc()
    finally:
        watchdog.cancel()
        shutil.rmtree(temp, ignore_errors=True)
    write()
    return 0 if report['ok'] else 1


def _wait(predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _checks(report, title, ui_dir, temp, window):
    started = time.monotonic()
    step = report['steps'].append

    import runtime
    import engine
    import server
    import webview
    from PIL import Image
    try:
        from importlib.metadata import version
        step('imports: pywebview %s, Pillow %s' % (version('pywebview'), version('Pillow')))
    except Exception:  # package metadata is not inside the .exe
        step('imports: pywebview, Pillow')
    if os.name == 'nt':
        import clr  # noqa: F401  (pythonnet: .NET for the WinForms window)
        from webview.platforms import winforms
        step('winforms renderer: %s' % getattr(winforms, 'renderer', '?'))

    html = runtime.inline_ui(Path(ui_dir))
    assert 'id="subsList"' in html and 'window.__sorter' in html, 'page files missing'
    step('page files')

    parent, out = temp / 'LOT_SELFTEST', temp / 'out'
    (parent / 'A').mkdir(parents=True)
    out.mkdir()
    for i in range(3):
        Image.new('RGB', (64, 48), (i * 60, 120, 80)).save(str(parent / 'A' / ('IMG_%d.jpg' % i)), quality=90)
    controller = server.Controller(temp / 'data', title=title)
    web = server.Server(controller, html)
    try:
        conn = http.client.HTTPConnection('127.0.0.1', web.port, timeout=10)
        conn.request('GET', '/%s/' % web.token, headers={'Host': web.host})
        response = conn.getresponse()
        assert response.status == 200 and b'AOI Photo Sorter' in response.read(), 'page not served'
        conn.close()
        step('page served')

        assert _wait(lambda: controller.tree(str(parent), str(out))['state'] == 'done', 20), 'folder list not done'
        entries = controller.tree(str(parent), str(out))['entries']
        assert [e['parts'] for e in entries] == [['A']], entries
        folder = entries[0]['path']
        started_job = controller.start(folder, str(out), False, '', str(parent))
        assert started_job['ok'], started_job
        assert _wait(lambda: controller.state()['phase'] == 'ready', 20), controller.state()
        job = controller.state()['job']
        data, mime = controller.image(job, 1)
        assert data == (parent / 'A' / 'IMG_1.jpg').read_bytes() and mime == 'image/jpeg'
        assert controller.thumbnail(job, 1)[0][:2] == b'\xff\xd8'
        saved = controller.save({'job': job, 'good': [1]})
        assert saved['ok'], saved
        assert Path(saved['good_path']).name == 'LOT_SELFTEST_A_1차리뷰_%s_GOOD.txt' % saved['when'], saved['good_path']
        assert Path(saved['good_path']).read_bytes() == b'IMG_1.jpg\r\n'
        assert engine.read_results(str(out), folder, 'LOT_SELFTEST_A')['round'] == 1
        controller.new()
        step('sorted and saved a photo folder')
        report['seconds_to_ready'] = round(time.monotonic() - started, 2)

        if window:
            _window(report, webview, web.url, title, temp / 'webview2')
    finally:
        controller.close()
        web.close()


def _window(report, webview, url, title, storage):
    """WebView2 opens the page and app.js runs: the start screen shows the version."""
    step = report['steps'].append
    version = title.replace('AOI Photo Sorter', '').strip()
    seen = {}
    step('window: opening')
    view = webview.create_window(title, url=url, width=1100, height=760)

    def check():
        try:
            if not view.events.loaded.wait(90):
                seen['error'] = 'page never loaded'
                return
            step('window: page loaded')
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                seen['ver'] = view.evaluate_js("document.getElementById('ver').textContent")
                seen['sorter'] = view.evaluate_js("typeof window.__sorter")
                if seen['ver'] == version and seen['sorter'] == 'object':
                    break
                time.sleep(0.2)
        except Exception:
            seen['error'] = traceback.format_exc()
        finally:
            view.destroy()

    webview.start(check, gui='edgechromium' if os.name == 'nt' else None, private_mode=True, storage_path=str(storage))
    report['window'] = seen
    assert 'error' not in seen, seen.get('error')
    assert seen.get('ver') == version and seen.get('sorter') == 'object', seen
    step('window: app.js running, start screen shows %s' % version)
