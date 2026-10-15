# -*- coding: utf-8 -*-
"""AOI Photo Sorter HTML (programs/AOI_Photo_Sorter_HTML): the built single .html in Chromium (Edge's engine).

Edge's folder dialog cannot be driven, so showDirectoryPicker hands out folders of the page's
private file system (OPFS): real directory handles, with the same calls as a picked network
folder. window.__aoiTestHooks makes reads slow or the share unreachable. Everything else is
the page's own code. Each test runs in a fresh browser context (empty storage).

    python -m unittest tests.e2e_html_sorter -v
"""
import base64
import functools
import http.server
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
    from PIL import Image
except ImportError:  # pragma: no cover
    sync_playwright = None

REPO = Path(__file__).resolve().parent.parent
PROGRAM = REPO / 'programs' / 'AOI_Photo_Sorter_HTML'
VERSION = json.loads((PROGRAM / 'version.json').read_text(encoding='utf-8'))
PAGE = VERSION['release'] + '.html'


def load_engine():
    """The Python version's engine, to check that both versions read each other's result files."""
    os.environ.setdefault('AOI_TOOLS_HOME', tempfile.mkdtemp(prefix='aoi_tools_test_'))
    spec = importlib.util.spec_from_file_location('photo_sorter_engine', REPO / 'programs' / 'AOI_Photo_Sorter' / 'app_files' / 'engine.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def color_of(i):
    return ((i % 8) * 32 + 16, ((i // 8) % 8) * 32 + 16, ((i // 64) % 8) * 32 + 16)


def index_of(rgb):
    r, g, b = [round((v - 16) / 32) for v in rgb[:3]]
    return r + g * 8 + b * 64


PICKER = """
window.__picks = [];
window.__aoiTestHooks = {};
window.showDirectoryPicker = async () => {
  const path = window.__picks.shift();
  if (!path) throw new DOMException('closed', 'AbortError');
  let h = await navigator.storage.getDirectory();
  for (const p of path.split('/')) h = await h.getDirectoryHandle(p, {create: true});
  return h;
};
"""

MAKE_PHOTOS = """async ([dir, n, first]) => {
  let h = await navigator.storage.getDirectory();
  for (const p of dir.split('/')) h = await h.getDirectoryHandle(p, {create: true});
  const c = new OffscreenCanvas(160, 120), x = c.getContext('2d');
  for (let i = first; i < first + n; i++) {
    x.fillStyle = `rgb(${(i % 8) * 32 + 16},${(Math.floor(i / 8) % 8) * 32 + 16},${(Math.floor(i / 64) % 8) * 32 + 16})`;
    x.fillRect(0, 0, 160, 120);
    const w = await (await h.getFileHandle('IMG_' + String(i).padStart(4, '0') + '.jpg', {create: true})).createWritable();
    await w.write(await c.convertToBlob({type: 'image/jpeg', quality: 0.95}));
    await w.close();
  }
}"""

PUT_FILE = """async ([path, b64]) => {
  const parts = path.split('/'), name = parts.pop();
  let h = await navigator.storage.getDirectory();
  for (const p of parts) h = await h.getDirectoryHandle(p, {create: true});
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const w = await (await h.getFileHandle(name, {create: true})).createWritable();
  await w.write(bytes);
  await w.close();
}"""

READ_DIR = """async (dir) => {
  let h = await navigator.storage.getDirectory();
  for (const p of dir.split('/')) h = await h.getDirectoryHandle(p, {create: true});
  const out = {};
  for await (const [name, f] of h.entries()) {
    if (f.kind !== 'file') continue;
    const bytes = new Uint8Array(await (await f.getFile()).arrayBuffer());
    let s = ''; for (const b of bytes) s += String.fromCharCode(b);
    out[name] = btoa(s);
  }
  return out;
}"""

CENTER = """(() => { const c = document.getElementById('view');
  return Array.from(c.getContext('2d').getImageData(c.width >> 1, c.height >> 1, 1, 1).data); })()"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class BuiltFileTest(unittest.TestCase):
    def test_built_file_is_current_and_self_contained(self):
        result = subprocess.run([sys.executable, str(REPO / 'tools' / 'build_html.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        html = (PROGRAM / PAGE).read_text(encoding='utf-8')
        self.assertIn("connect-src 'none'", html)
        self.assertNotIn(' src="', html.split('<body>', 1)[1].replace('<img id="oImg" alt="">', ''))  # nothing loaded from elsewhere
        self.assertNotIn('href="http', html)
        self.assertIn('<title>%s</title>' % VERSION['title'], html)


@unittest.skipIf(sync_playwright is None, 'playwright / Pillow not installed')
class HtmlSorterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(PROGRAM)))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.url = 'http://127.0.0.1:%d/%s' % (cls.httpd.server_address[1], PAGE)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.httpd.shutdown()

    def setUp(self):
        # the page forbids eval (CSP); Playwright's waits need it, so tests look past the policy (see test_no_network)
        self.context = self.browser.new_context(viewport={'width': 1400, 'height': 900}, bypass_csp=True)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda exc: self.errors.append(str(exc)))
        self.page.on('console', lambda m: self.errors.append(m.text) if m.type == 'error' else None)
        self.page.add_init_script(PICKER)
        self.page.goto(self.url)

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    # helpers
    def js(self, expr, arg=None):
        return self.page.evaluate(expr, arg) if arg is not None else self.page.evaluate(expr)

    def photos(self, folder, n, first=0):
        self.js(MAKE_PHOTOS, [folder, n, first])

    def put(self, path, data):
        self.js(PUT_FILE, [path, base64.b64encode(data).decode()])

    def read_dir(self, folder):
        return {name: base64.b64decode(b64) for name, b64 in self.js(READ_DIR, folder).items()}

    def pick(self, field, path):
        self.js('p => window.__picks.push(p)', path)
        self.page.click('#pickFolder' if field == 'folder' else '#pickOutput')
        self.page.wait_for_function("id => document.getElementById(id).value !== ''", arg=field)

    def start(self, folder='photos/LOT_A', output='out', key='Enter'):
        self.pick('folder', folder)
        self.pick('output', output)
        self.page.wait_for_function("!document.getElementById('startBtn').disabled")
        self.page.keyboard.press(key)
        self.wait_painted()

    def wait_painted(self, timeout=15000):
        self.page.wait_for_function('window.__sorter.S.job && window.__sorter.S.painted === window.__sorter.current() && window.__sorter.S.painted >= 0',
                                    timeout=timeout)

    def shown(self):
        return index_of(self.js(CENTER))

    def save_from_sort(self):
        keyboard = self.page.keyboard
        keyboard.press('Escape')
        keyboard.press('Enter')  # menu → review
        self.page.wait_for_selector('#review.show')
        keyboard.press('Control+s')
        keyboard.press('Enter')  # unseen photos stay REJECT
        self.page.wait_for_selector('#done.show')

    def rounds(self, files, n):
        return {name.rsplit('_', 1)[1]: data for name, data in files.items() if '_%d차리뷰_' % n in name}

    # tests
    def test_sort_review_save_and_rounds(self):
        """1차 (GOOD / REJECT) → 추가 GOOD 검토 2차 (추가GOOD / GOOD / REJECT) → changed on the review
        screen and saved again: the same 2차 files rewritten. Same bytes as the Python version writes."""
        page, keyboard = self.page, self.page.keyboard
        self.photos('photos/LOT_A', 30)
        self.start()
        self.assertEqual(self.shown(), 0)
        self.assertEqual(page.inner_text('#hFolder'), 'LOT_A')
        time.sleep(0.2)
        keyboard.press('Space')  # IMG_0000 GOOD → IMG_0001
        self.wait_painted()
        keyboard.press('ArrowRight')  # → IMG_0002
        self.wait_painted()
        time.sleep(0.2)
        keyboard.press('Space')  # IMG_0002 GOOD → IMG_0003
        self.wait_painted()
        self.assertEqual(self.shown(), 3)
        self.save_from_sort()
        self.assertIn('1차리뷰 저장 완료', page.inner_text('#doneTitle'))
        first = self.rounds(self.read_dir('out'), 1)
        self.assertEqual(sorted(first), ['GOOD.txt', 'REJECT.txt'])
        self.assertEqual(first['GOOD.txt'], b'IMG_0000.jpg\r\nIMG_0002.jpg\r\n')  # UTF-8 without BOM, CRLF
        self.assertEqual(first['REJECT.txt'].count(b'\r\n'), 28)
        self.assertTrue(first['REJECT.txt'].startswith(b'IMG_0001.jpg\r\nIMG_0003.jpg\r\n'))

        page.click('#doneNew')
        page.wait_for_selector('#extra:not(.hidden)')
        self.assertIn('1차리뷰', page.inner_text('#extra'))
        self.assertIn('GOOD 2 / REJECT 28', page.inner_text('#extra'))
        page.click('#extraBtn')
        self.wait_painted()
        self.assertEqual(self.js('window.__sorter.S.names.slice(0, 2)'), ['IMG_0001.jpg', 'IMG_0003.jpg'])
        time.sleep(0.2)
        keyboard.press('Space')  # IMG_0001 added
        self.wait_painted()
        self.save_from_sort()
        self.assertIn('2차리뷰 저장 완료', page.inner_text('#doneTitle'))
        second = self.rounds(self.read_dir('out'), 2)
        self.assertEqual(sorted(second), ['GOOD.txt', 'REJECT.txt', '추가GOOD.txt'])
        self.assertEqual(second['GOOD.txt'], b'IMG_0000.jpg\r\nIMG_0001.jpg\r\nIMG_0002.jpg\r\n')
        self.assertEqual(second['추가GOOD.txt'], b'IMG_0001.jpg\r\n')

        page.click('#doneReview')  # take the 2차 pick back and save again: the same round, no 3차
        page.wait_for_selector('#review.show')
        page.wait_for_function("document.querySelectorAll('.cell').length === 1")
        keyboard.press('Space')
        keyboard.press('Control+s')
        keyboard.press('Enter')
        page.wait_for_selector('#done.show')
        files = self.read_dir('out')
        self.assertEqual(len(files), 2 + 3)
        again = self.rounds(files, 2)
        self.assertEqual(again['GOOD.txt'], b'IMG_0000.jpg\r\nIMG_0002.jpg\r\n')
        self.assertEqual(again['추가GOOD.txt'], b'')

    def test_fast_keys_on_a_slow_share(self):
        """Keys 25 ms apart while every photo takes 40 ms to read: → never leaves a photo that was not
        on screen, Space only marks a photo on screen (and not one that just appeared)."""
        page, keyboard = self.page, self.page.keyboard
        self.photos('photos/LOT_A', 150)
        self.js('window.__aoiTestHooks.readDelay = 40')
        self.start()
        keys = ['ArrowRight'] * 3 + ['Space'] + ['ArrowRight'] * 2 + ['Space', 'Space'] + ['ArrowLeft']
        for k in range(80):
            keyboard.press(keys[k % len(keys)])
            time.sleep(0.025)
        self.wait_painted()
        trace = self.js('window.__sorter.trace')
        moves = [t for t in trace if t['type'] == 'move']
        self.assertTrue(moves)
        for t in moves:
            self.assertEqual(abs(t['to'] - t['from']), 1)
        painted = {t['i'] for t in trace if t['type'] == 'paint'}
        for t in moves:
            if t['to'] > t['from']:
                self.assertIn(t['from'], painted)  # left only after it was on screen
        for t in [t for t in trace if t['type'] == 'toggle']:
            self.assertEqual(t['painted'], t['i'])
        seen = self.js('Array.from(window.__sorter.S.seen).flatMap((v, i) => v ? [i] : [])')
        self.assertEqual(seen, list(range(len(seen))))  # every photo on the way was shown
        self.assertEqual(self.shown(), self.js('window.__sorter.current()'))

    def test_parent_folder_to_the_end_and_overview(self):
        """A parent folder: its photo folders listed; at the last photo Enter saves and opens the next
        folder; after the last folder the overview shows every GOOD / REJECT photo."""
        page, keyboard = self.page, self.page.keyboard
        self.photos('photos/LOTP/A', 4)
        self.photos('photos/LOTP/B', 3, 10)
        self.photos('photos/LOTP/B/deep', 2, 20)
        self.pick('folder', 'photos/LOTP')
        self.pick('output', 'out')
        page.wait_for_function("document.querySelectorAll('#subsList .sub').length === 3")
        self.assertEqual(page.locator('#subsList .sub .sname').all_inner_texts(), ['A', 'B', 'B\\deep'])
        keyboard.press('ArrowDown')
        keyboard.press('ArrowUp')
        keyboard.press('Enter')
        self.wait_painted()
        self.assertIn('LOTP › A', page.inner_text('#hFolder'))
        time.sleep(0.2)
        keyboard.press('Space')  # A/IMG_0000 GOOD
        for _ in range(3):
            self.wait_painted()
            keyboard.press('ArrowRight')
        page.wait_for_selector('#modal:not(.hidden)')
        self.assertIn('이 폴더의 마지막 사진입니다', page.inner_text('#modal'))
        keyboard.press('Enter')  # save, next folder: B
        page.wait_for_function("window.__sorter.S.parts.join() === 'B' && window.__sorter.S.painted === 0")
        self.assertEqual(self.shown(), 10)
        files = self.read_dir('out')
        good = [d for n, d in files.items() if n.startswith('LOTP_A_1차리뷰_') and n.endswith('_GOOD.txt')]
        self.assertEqual(good, [b'IMG_0000.jpg\r\n'])
        for _ in range(2):
            self.wait_painted()
            keyboard.press('ArrowRight')
        self.wait_painted()
        keyboard.press('ArrowRight')
        page.wait_for_selector('#modal:not(.hidden)')
        keyboard.press('Enter')  # save B, then B\deep
        page.wait_for_function("window.__sorter.S.parts.join() === 'B,deep' && window.__sorter.S.painted === 0")
        time.sleep(0.2)
        keyboard.press('Space')
        self.wait_painted()
        keyboard.press('ArrowRight')
        page.wait_for_selector('#modal:not(.hidden)')
        self.assertIn('마지막 폴더입니다', page.inner_text('#modal'))
        keyboard.press('Enter')  # save the last folder → overview
        page.wait_for_selector('#overview.show')
        page.wait_for_function("document.getElementById('oTabGood').textContent.startsWith('GOOD 2')")
        self.assertIn('REJECT 7', page.inner_text('#oTabReject'))
        page.wait_for_function("[...document.querySelectorAll('#oGrid .cell img')].filter(i => i.naturalWidth > 0).length === 2")
        keyboard.press('Enter')  # big view of the first GOOD photo
        page.wait_for_function("document.getElementById('oImg').naturalWidth > 0")
        keyboard.press('Escape')
        keyboard.press('Digit2')
        page.wait_for_function("[...document.querySelectorAll('#oGrid .cell img')].filter(i => i.naturalWidth > 0).length === 7")
        self.assertEqual(sorted(n.split('_1차리뷰_')[0] for n in self.read_dir('out')), ['LOTP_A'] * 2 + ['LOTP_B'] * 2 + ['LOTP_B_deep'] * 2)

    def test_resume_after_closing_and_settings_kept(self):
        """Progress and the switches live in the browser (IndexedDB): reopened, the recent list
        brings back the folders (Edge asks for access again) and the work goes on where it stopped."""
        page, keyboard = self.page, self.page.keyboard
        self.photos('photos/LOT_A', 20)
        self.start()
        time.sleep(0.2)
        keyboard.press('Space')  # IMG_0000 GOOD
        self.wait_painted()
        keyboard.press('ArrowRight')
        self.wait_painted()
        page.click('#hRepeat')
        self.assertEqual(page.inner_text('#hRepeat'), '연속 넘김 ON')
        time.sleep(1.5)  # saved once a second
        page.goto(self.url)  # closed and opened again
        page.wait_for_function("document.querySelectorAll('#recent button').length === 1")
        self.assertIn('3 / 20 확인 · GOOD 1', page.inner_text('#recent'))  # IMG_0000..0002 were on screen
        page.click('#recent button')
        page.wait_for_function("document.getElementById('startBtn').textContent.startsWith('이어하기') && !document.getElementById('startBtn').disabled")
        self.assertEqual((page.input_value('#folder'), page.input_value('#output')), ('LOT_A', 'out'))
        keyboard.press('Enter')
        page.wait_for_function('window.__sorter.S.painted === 2')
        self.assertEqual(self.js('Array.from(window.__sorter.S.good.slice(0, 3))'), [1, 0, 0])
        self.assertEqual(page.inner_text('#hRepeat'), '연속 넘김 ON')

    def test_network_outage_recovers_by_itself(self):
        page = self.page
        self.photos('photos/LOT_A', 10)
        self.js('window.__aoiTestHooks.offline = true')
        self.pick('folder', 'photos/LOT_A')
        self.pick('output', 'out')
        page.wait_for_function("!document.getElementById('startBtn').disabled")
        page.keyboard.press('Enter')
        page.wait_for_function("document.getElementById('card').textContent.includes('네트워크 폴더 연결 끊김')")
        page.wait_for_function("document.getElementById('net').textContent.includes('연결 끊김')")
        self.js('window.__aoiTestHooks.offline = false')  # back: read again without a key
        page.wait_for_function('window.__sorter.S.painted === 0', timeout=10000)
        self.assertEqual(self.shown(), 0)
        page.wait_for_function("document.getElementById('net').classList.contains('hidden')")

    def test_tiff_photos_are_shown(self):
        """Edge cannot show TIFF: the page decodes it (UTIF in a worker), uncompressed and LZW."""
        page, keyboard = self.page, self.page.keyboard
        for i, compression in ((0, None), (1, 'tiff_lzw'), (2, 'tiff_adobe_deflate')):
            data = io.BytesIO()
            Image.new('RGB', (120, 90), color_of(i)).save(data, 'TIFF', compression=compression)
            self.put('photos/LOT_T/IMG_%04d.tif' % i, data.getvalue())
        self.start('photos/LOT_T')
        for i in range(3):
            self.assertEqual(self.shown(), i)
            time.sleep(0.2)
            keyboard.press('Space')
            if i < 2:
                self.wait_painted()
        keyboard.press('Escape')
        keyboard.press('Enter')
        page.wait_for_selector('#review.show')
        page.wait_for_function("[...document.querySelectorAll('.cell img')].filter(i => i.naturalWidth > 0).length === 3")

    def test_results_shared_with_the_python_version(self):
        """A 1차 saved by the Python version is the previous result here; the 2차 saved here is the
        latest result for the Python version."""
        engine = load_engine()
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        names = ['IMG_%04d.jpg' % i for i in range(12)]
        first = engine.save_round(str(tmp), r'\\srv\aoi\LOT_A', names, ['IMG_0003.jpg'])
        for name in os.listdir(tmp):
            self.put('out/' + name, (tmp / name).read_bytes())
        self.photos('photos/LOT_A', 12)
        self.pick('folder', 'photos/LOT_A')
        self.pick('output', 'out')
        page = self.page
        page.wait_for_selector('#extra:not(.hidden)')
        self.assertIn('1차리뷰', page.inner_text('#extra'))
        self.assertIn('GOOD 1 / REJECT 11', page.inner_text('#extra'))
        page.click('#extraBtn')
        self.wait_painted()
        time.sleep(0.2)
        page.keyboard.press('Space')  # IMG_0000 added
        self.wait_painted()
        self.save_from_sort()
        back = tmp / 'back'
        back.mkdir()
        for name, data in self.read_dir('out').items():
            (back / name).write_bytes(data)
        latest = engine.read_results(str(back), r'\\srv\aoi\LOT_A')
        self.assertEqual((latest['round'], latest['good']), (2, ['IMG_0000.jpg', 'IMG_0003.jpg']))
        self.assertEqual(first['round'], 1)

    def test_ten_thousand_photos(self):
        """10,000 photos in one folder: listed and on screen quickly, paging stays one frame per key."""
        page, keyboard = self.page, self.page.keyboard
        self.js("""async () => {
          let h = await navigator.storage.getDirectory();
          for (const p of ['photos', 'LOT_BIG']) h = await h.getDirectoryHandle(p, {create: true});
          const c = new OffscreenCanvas(64, 48), x = c.getContext('2d');
          x.fillStyle = '#4080c0'; x.fillRect(0, 0, 64, 48);
          const blob = await c.convertToBlob({type: 'image/jpeg'});
          const jobs = [];
          for (let i = 0; i < 10000; i++) jobs.push((async () => {
            const w = await (await h.getFileHandle('P_' + i + '.jpg', {create: true})).createWritable(); await w.write(blob); await w.close(); })());
          await Promise.all(jobs); }""")
        self.pick('folder', 'photos/LOT_BIG')
        self.pick('output', 'out')
        page.wait_for_function("!document.getElementById('startBtn').disabled", timeout=60000)
        started = time.monotonic()
        keyboard.press('Enter')
        self.wait_painted(timeout=60000)
        first = time.monotonic() - started
        self.assertEqual(self.js('window.__sorter.S.n'), 10000)
        self.assertEqual(self.js('window.__sorter.S.names.slice(0, 3)'), ['P_0.jpg', 'P_1.jpg', 'P_2.jpg'])
        for _ in range(60):
            keyboard.press('ArrowRight')
            self.wait_painted()
        paints = [t for t in self.js('window.__sorter.trace') if t['type'] == 'paint' and t.get('keyT')]
        lat = sorted(t['frame'] - t['keyT'] for t in paints)
        p50, p95 = lat[len(lat) // 2], lat[int(len(lat) * 0.95)]
        cached = self.js('Backend.debug().job.cache.stats().cached')
        print('\n  HTML, 10,000 photos: start→first photo %.2f s, key→frame p50 %.1f ms p95 %.1f ms, %d photos read ahead'
              % (first, p50, p95, cached))
        self.assertLess(first, 10.0)
        self.assertLess(p95, 100)
        self.assertGreater(cached, 150)

    def test_no_network(self):
        """With the page's own policy (not bypassed): nothing can be sent anywhere."""
        context = self.browser.new_context()
        page = context.new_page()
        self.addCleanup(context.close)
        requests = []
        page.on('request', lambda r: requests.append(r.url))
        page.goto(self.url)
        page.wait_for_selector('#start.show')
        blocked = page.evaluate("""() => fetch('https://example.com/x').then(() => 'sent', err => 'blocked')""")
        self.assertEqual(blocked, 'blocked')
        self.assertEqual([u for u in requests if not u.startswith('blob:')], [self.url])


if __name__ == '__main__':
    unittest.main()
