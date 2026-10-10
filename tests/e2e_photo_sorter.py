# -*- coding: utf-8 -*-
"""Rapid key input end-to-end test of the Photo Sorter screen in Chromium (WebView2's engine).

The real page and the real Python server/engine run together; only the network share
is simulated (per-file latency, optionally a photo held back). Needs Pillow and
Playwright with a Chromium build, otherwise skipped:

    AOI_TOOLS_HOME=/tmp/aoi_test python -m unittest tests.e2e_photo_sorter -v
"""
import importlib
import json
import os
import random
import shutil
import statistics
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP_DIR = REPO / 'programs' / 'AOI_Photo_Sorter' / 'app_files'
os.environ.setdefault('AOI_TOOLS_HOME', tempfile.mkdtemp(prefix='aoi_tools_test_'))

try:
    from playwright.sync_api import sync_playwright
    from PIL import Image
except ImportError:  # pragma: no cover
    sync_playwright = None


def load_modules():
    for name in ('engine', 'server', 'runtime'):
        sys.modules.pop(name, None)
    sys.path.insert(0, str(APP_DIR))
    try:
        return importlib.import_module('server'), importlib.import_module('runtime')
    finally:
        sys.path.remove(str(APP_DIR))
        for name in ('engine', 'server', 'runtime'):
            sys.modules.pop(name, None)


server, runtime = load_modules()


def color_of(i):
    return ((i % 8) * 32 + 16, ((i // 8) % 8) * 32 + 16, ((i // 64) % 8) * 32 + 16)


def index_of(rgb):
    r, g, b = [round((v - 16) / 32) for v in rgb[:3]]
    return r + g * 8 + b * 64


class SlowShare:
    """Network share stand-in: latency per file, gates that hold chosen files back,
    an outage switch (reads and the folder probe fail) and per-file read failures."""

    def __init__(self, latency):
        self.latency = latency
        self.gates = {}
        self.online = True
        self.fail = set()

    def __call__(self, path):
        gate = self.gates.get(os.path.basename(path))
        if gate is not None:
            gate.wait(30)
        time.sleep(self.latency)
        if not self.online:
            raise OSError(64, 'The specified network name is no longer available')
        if os.path.basename(path) in self.fail:
            raise OSError(5, 'Access is denied')
        with open(path, 'rb') as handle:
            return handle.read()

    def probe(self):
        if not self.online:
            raise OSError(64, 'The specified network name is no longer available')


CUR = 'window.__sorter.current()'


def wait(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@unittest.skipIf(sync_playwright is None, 'playwright / Pillow not installed')
class RapidInputTest(unittest.TestCase):
    N = 500

    @classmethod
    def setUpClass(cls):
        cls.photos = tempfile.mkdtemp(prefix='LOT_E2E_')
        for i in range(cls.N):
            Image.new('RGB', (640, 480), color_of(i)).save(os.path.join(cls.photos, 'IMG_%04d.jpg' % i), quality=95)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        shutil.rmtree(cls.photos, ignore_errors=True)

    def setUp(self):
        self.out = tempfile.mkdtemp()
        self.base = tempfile.mkdtemp()
        self.share = SlowShare(0.015)
        self.controller = server.Controller(self.base, reader=self.share, probe=self.share.probe)
        self.web = server.Server(self.controller, runtime.inline_ui(APP_DIR / 'ui'))
        self.page = self.browser.new_page(viewport={'width': 1400, 'height': 900})
        self.errors = []
        self.allow_503 = False  # outage tests: failed photo requests are expected
        self.page.on('pageerror', lambda exc: self.errors.append(str(exc)))
        self.page.on('console', lambda msg: self.errors.append(msg.text) if msg.type == 'error' else None)

    def tearDown(self):
        self.page.close()
        self.web.close()
        self.controller.close()
        for gate in self.share.gates.values():
            gate.set()
        self.share.online = True
        shutil.rmtree(self.out, ignore_errors=True)
        shutil.rmtree(self.base, ignore_errors=True)
        if self.allow_503:
            self.errors = [e for e in self.errors if 'status of 503' not in e]
        self.assertEqual(self.errors, [])

    def small_window(self, **settings):
        """Restart the Python side with a small read-ahead window (settings.json)."""
        self.web.close()
        self.controller.close()
        Path(self.base, 'settings.json').write_text(json.dumps(settings), encoding='utf-8')
        self.controller = server.Controller(self.base, reader=self.share, probe=self.share.probe)
        self.web = server.Server(self.controller, runtime.inline_ui(APP_DIR / 'ui'))

    def card(self):
        return self.page.inner_text('#card') if self.page.is_visible('#card') else ''

    # helpers
    def start(self, folder=None):
        page = self.page
        page.goto(self.web.url)
        page.fill('#folder', folder or self.photos)
        page.fill('#output', self.out)
        page.wait_for_function("!document.getElementById('startBtn').disabled")
        started = time.monotonic()
        page.keyboard.press('Enter')
        page.wait_for_function('window.__sorter.S.painted === 0', timeout=30000)
        return time.monotonic() - started

    def js(self, expr):
        return self.page.evaluate(expr)

    def wait_painted(self):
        self.page.wait_for_function('window.__sorter.S.painted === %s' % CUR)

    def shown_index(self):
        rgb = self.js("(() => { const c = document.getElementById('view'); "
                      "return Array.from(c.getContext('2d').getImageData(c.width >> 1, c.height >> 1, 1, 1).data); })()")
        return index_of(rgb)

    def trace(self):
        return self.js('window.__sorter.trace')

    def ui_good(self):
        return set(self.js('Array.from(window.__sorter.S.good).flatMap((v, i) => v ? [i] : [])'))

    # tests
    def test_photo_on_screen_matches_position(self):
        self.start()
        self.assertEqual(self.shown_index(), 0)
        for _ in range(40):
            self.page.keyboard.press('ArrowRight')
            self.wait_painted()
            self.assertEqual(self.shown_index(), self.js(CUR))
        for _ in range(5):
            self.page.keyboard.press('ArrowLeft')
            self.wait_painted()
            self.assertEqual(self.shown_index(), self.js(CUR))
        self.assertEqual(self.js(CUR), 35)

    def test_rapid_random_keys(self):
        """1,000 random actions 5 ms apart: taps, held keys (auto-repeat), → + Space chords,
        and now and then a short look at the photo before Space."""
        self.start()
        keyboard = self.page.keyboard
        rnd = random.Random(20261009)
        sent = {'ArrowRight': 0, 'ArrowLeft': 0, 'Space': 0}
        for _ in range(1000):
            roll = rnd.random()
            if roll < 0.55:
                keys = [('ArrowRight', 1)]
            elif roll < 0.68:
                keys = [('ArrowLeft', 1)]
            elif roll < 0.88:
                if rnd.random() < 0.4:
                    time.sleep(0.15)  # looked at the photo, then GOOD
                keys = [('Space', 1)]
            elif roll < 0.93:
                keys = [('Space', rnd.randint(2, 6))]  # held: 1 keydown + repeats
            elif roll < 0.96:
                keys = [('ArrowRight', rnd.randint(2, 6))]
            else:
                keys = 'chord'
            if keys == 'chord':
                keyboard.down('ArrowRight')
                keyboard.down('Space')
                keyboard.up('Space')
                keyboard.up('ArrowRight')
                sent['ArrowRight'] += 1
                sent['Space'] += 1
            else:
                for key, count in keys:
                    for _ in range(count):
                        keyboard.down(key)
                    keyboard.up(key)
                    sent[key] += count
            time.sleep(0.005)
        self.wait_painted()
        self.assertTrue(self.js('window.__sorter.flush()'))
        trace = self.trace()

        # every key press is accounted for: applied or deliberately ignored, none lost
        def count(key, kind):
            return sum(1 for t in trace if t['type'] == kind and t.get('key') == key)
        self.assertEqual(sent['Space'], sum(1 for t in trace if t['type'] == 'toggle') + count('space', 'ignored'))
        self.assertEqual(sent['ArrowRight'], count('right', 'move') + count('right', 'ignored'))
        self.assertEqual(sent['ArrowLeft'], count('left', 'move') + count('left', 'ignored'))

        # Space only ever hit the photo that was on screen, and only after it had been there
        # space_min_view_ms; moving forward (→ or Space) never left an unpainted photo;
        # every applied Space went straight on to the next photo
        min_view = self.js('window.__sorter.cfg.space_min_view_ms')
        screen = shown_at = None
        for k, t in enumerate(trace):
            if t['type'] == 'paint':
                screen, shown_at = t['i'], t['t']
            elif t['type'] in ('move', 'jump'):
                if t.get('key') in ('right', 'space'):
                    self.assertEqual(screen, t['from'], 'moved forward from a photo that was not on screen')
                screen = None
            elif t['type'] == 'toggle':
                self.assertEqual(screen, t['i'], 'Space applied to a photo that was not on screen')
                self.assertGreaterEqual(t['t'] - shown_at, min_view - 1)
                if t['i'] < self.N - 1:  # on the last photo Space marks it and stays
                    nxt = trace[k + 1]
                    self.assertEqual((nxt['type'], nxt.get('key'), nxt.get('from')), ('move', 'space', t['i']))
        self.assertGreater(sum(1 for t in trace if t['type'] == 'toggle'), 20)

        # held Space toggled once per press, never by auto-repeat
        self.assertGreater(sum(1 for t in trace if t['type'] == 'ignored' and t.get('reason') == 'repeat' and t['key'] == 'space'), 0)

        # GOOD set: screen == XOR of applied toggles == Python session; seen == painted photos
        expected = set()
        for t in trace:
            if t['type'] == 'toggle':
                expected ^= {t['i']}
        self.assertEqual(self.ui_good(), expected)
        state = self.controller.state()
        self.assertEqual(set(state['good']), expected)
        painted = {t['i'] for t in trace if t['type'] == 'paint' and t['ok']}
        self.assertEqual({i for i, c in enumerate(state['seen']) if c == '1'}, painted)

        # key → frame latency for photos that were ready (paint frame right after the key)
        lat = sorted(t['frame'] - t['keyT'] for t in trace if t['type'] == 'paint' and t.get('keyT') is not None)
        p50, p95 = statistics.median(lat), lat[int(len(lat) * 0.95)]
        print('\n  moves %d, toggles %d, ignored %d, key→frame p50 %.1f ms p95 %.1f ms max %.1f ms' % (
            count('right', 'move') + count('left', 'move'), sum(1 for t in trace if t['type'] == 'toggle'),
            sum(1 for t in trace if t['type'] == 'ignored'), p50, p95, lat[-1]))
        self.assertLess(p50, 34)  # within two frames

        # the saved files are exactly that set
        result = self.controller.save({'job': state['job'], 'good': sorted(expected)})
        self.assertTrue(result['ok'])
        names = state['names']
        self.assertEqual(Path(result['good_path']).read_bytes(),
                         ''.join(names[i] + '\r\n' for i in sorted(expected)).encode('utf-8'))
        self.assertEqual(result['reject_count'], self.N - len(expected))

    def test_twenty_keys_per_second_drops_nothing(self):
        """The plan's target: → at 20 presses/s over a slow share, with a GOOD (Space after a
        150 ms look at the photo) every fourth photo. Nothing may be dropped."""
        self.start()
        keyboard = self.page.keyboard
        presses = (['ArrowRight'] * 3 + ['Space']) * 75
        next_at = time.monotonic()
        for key in presses:
            if key == 'Space':
                # A person presses GOOD after looking at the photo: the 150 ms count from when
                # it is on screen (a busy CI runner may paint a photo later than the key + 50 ms).
                self.wait_painted()
                time.sleep(0.15)
                next_at = time.monotonic()
            else:
                next_at += 0.05
                time.sleep(max(0, next_at - time.monotonic()))
            keyboard.press(key)
        self.wait_painted()
        trace = self.trace()
        ignored = [t for t in trace if t['type'] == 'ignored']
        self.assertEqual(ignored, [])
        self.assertEqual(self.js(CUR), 300)  # Space moved on as well
        self.assertEqual(self.ui_good(), set(range(3, 300, 4)))

    def test_space_goods_and_moves_on_hold_and_double_press(self):
        self.start()
        keyboard = self.page.keyboard
        time.sleep(0.2)
        for _ in range(6):  # held: one keydown and five auto-repeats
            keyboard.down('Space')
        keyboard.up('Space')
        self.assertEqual((self.ui_good(), self.js(CUR)), ({0}, 1))  # GOOD, and on to the next photo
        self.wait_painted()
        time.sleep(0.2)
        keyboard.press('Space')
        time.sleep(0.04)
        keyboard.press('Space')  # 40 ms later the next photo is barely up: bounce/double press, ignored
        self.assertEqual((self.ui_good(), self.js(CUR)), ({0, 1}, 2))
        keyboard.press('ArrowLeft')  # back to a GOOD photo: Space takes it back to REJECT, and moves on
        self.wait_painted()
        self.page.wait_for_function("document.getElementById('fTag').textContent === 'GOOD'")
        time.sleep(0.2)
        keyboard.press('Space')
        self.assertEqual((self.ui_good(), self.js(CUR)), ({0}, 2))
        reasons = [t.get('reason') for t in self.trace() if t['type'] == 'ignored']
        self.assertEqual((reasons.count('repeat'), reasons.count('too-soon')), (5, 1))

    def test_forward_waits_for_a_loading_photo(self):
        gate = threading.Event()
        self.share.gates['IMG_0003.jpg'] = gate  # this photo is stuck on the network
        self.start()
        for _ in range(2):
            self.page.keyboard.press('ArrowRight')
            self.wait_painted()
        self.page.keyboard.press('ArrowRight')  # → onto the stuck photo: moves, shows "불러오는 중"
        self.page.keyboard.press('Space')
        self.page.keyboard.press('ArrowRight')
        self.page.keyboard.press('ArrowRight')
        time.sleep(0.3)
        self.assertEqual((self.js(CUR), self.js('window.__sorter.S.painted')), (3, -1))
        self.assertIn('불러오는 중', self.page.inner_text('#card'))
        # a read that hangs (a dead Windows share does that) is reported after a few seconds
        self.page.wait_for_function("document.getElementById('net').textContent.includes('응답 대기')", timeout=15000)
        gate.set()
        self.wait_painted()
        self.assertEqual(self.js(CUR), 3)  # the dropped → presses were not replayed
        self.assertEqual(self.shown_index(), 3)
        self.assertEqual(self.ui_good(), set())  # the early Space did not mark it
        reasons = [(t['key'], t['reason']) for t in self.trace() if t['type'] == 'ignored']
        self.assertEqual(reasons, [('space', 'not-painted'), ('right', 'not-painted'), ('right', 'not-painted')])
        self.page.wait_for_function("document.getElementById('net').classList.contains('hidden')")

    def test_network_outage_recovers_by_itself(self):
        """The network folder drops mid-session: photos already read keep coming, the rest
        show "연결 끊김" at once, and when the folder is back everything continues without
        any key press. Photos skipped during the outage stay unseen (End finds them)."""
        self.allow_503 = True
        self.small_window(ahead_count=30, behind_count=10)
        self.start()
        self.assertTrue(wait(lambda: self.controller.state()['stats']['ready_ahead'] == 30))
        self.share.online = False
        page, keyboard = self.page, self.page.keyboard
        for _ in range(30):  # the read-ahead photos still show
            keyboard.press('ArrowRight')
            self.wait_painted()
            self.assertEqual((self.card(), self.shown_index()), ('', self.js(CUR)))
        keyboard.press('ArrowRight')  # photo 31 was never read
        page.wait_for_function("document.getElementById('cardTitle').textContent === '네트워크 폴더 연결 끊김'", timeout=15000)
        page.wait_for_function("document.getElementById('net').textContent.includes('연결 끊김')")
        for _ in range(3):  # further photos fail at once (no long wait)
            started = time.monotonic()
            keyboard.press('ArrowRight')
            self.wait_painted()
            self.assertLess(time.monotonic() - started, 1.0)
            self.assertIn('연결 끊김', self.card())
        self.assertEqual(self.js(CUR), 34)
        self.share.online = True  # the folder is back: no key press from here on
        page.wait_for_function("window.__sorter.S.painted === window.__sorter.current() && "
                               "document.getElementById('card').classList.contains('hidden')", timeout=10000)
        self.assertEqual(self.shown_index(), 34)
        page.wait_for_function("document.getElementById('net').classList.contains('hidden')")
        for _ in range(10):
            keyboard.press('ArrowRight')
            self.wait_painted()
            self.assertEqual((self.card(), self.shown_index()), ('', self.js(CUR)))
        keyboard.press('End')  # first photo never seen: 31, skipped during the outage
        self.wait_painted()
        self.assertEqual((self.js(CUR), self.card(), self.shown_index()), (31, '', 31))
        self.assertEqual(self.controller.state()['stats']['errors'], 0)

    def test_refresh_key_reloads_failed_photos(self):
        """Some files fail while the folder itself answers (not an outage): they stay
        failed until F5, which reads them again."""
        self.allow_503 = True
        self.small_window(ahead_count=30, behind_count=10)
        self.share.fail = {'IMG_%04d.jpg' % i for i in range(5, 15)}
        self.start()
        page, keyboard = self.page, self.page.keyboard
        for _ in range(5):
            keyboard.press('ArrowRight')
            self.wait_painted()
        self.assertIn('읽기 실패', self.card())
        self.share.fail = set()
        time.sleep(3)
        self.assertIn('읽기 실패', self.card())  # a file error is not retried by itself
        keyboard.press('F5')
        page.wait_for_function("window.__sorter.S.painted === window.__sorter.current() && "
                               "document.getElementById('card').classList.contains('hidden')", timeout=10000)
        self.assertEqual(self.shown_index(), 5)
        for _ in range(10):
            keyboard.press('ArrowRight')
            self.wait_painted()
            self.assertEqual((self.card(), self.shown_index()), ('', self.js(CUR)))

    def test_review_and_resume_after_restart(self):
        self.start()
        for _ in range(3):
            time.sleep(0.2)  # a look at the photo
            self.page.keyboard.press('Space')  # GOOD and next
            self.wait_painted()
        self.assertEqual((self.ui_good(), self.js(CUR)), ({0, 1, 2}, 3))
        self.page.keyboard.press('Escape')
        self.page.keyboard.press('Enter')  # menu → review
        self.page.wait_for_selector('#review.show')
        self.page.wait_for_function("document.querySelectorAll('.cell').length === 3")
        self.page.keyboard.press('ArrowRight')
        self.page.keyboard.press('Space')  # un-GOOD the 2nd one in the grid, selection moves on
        self.assertEqual(self.ui_good(), {0, 2})
        self.assertEqual(self.js('document.querySelector(".cell.sel .cname").textContent'), 'IMG_0002.jpg')
        self.assertEqual(self.page.inner_text('#rGood'), '2')
        self.assertTrue(self.js('window.__sorter.flush()'))
        # "restart": a new controller and page on the same settings/session folder
        self.page.close()
        self.web.close()
        self.controller.close()
        self.controller = server.Controller(self.base, reader=self.share, probe=self.share.probe)
        self.web = server.Server(self.controller, runtime.inline_ui(APP_DIR / 'ui'))
        self.page = self.browser.new_page(viewport={'width': 1400, 'height': 900})
        self.page.goto(self.web.url)
        self.page.fill('#folder', self.photos)
        self.page.wait_for_function("document.getElementById('output').value !== ''")  # remembered output folder
        self.page.wait_for_function("!document.getElementById('startBtn').disabled")
        self.assertIn('GOOD 2', self.page.inner_text('#resume'))
        self.page.keyboard.press('Enter')
        self.page.wait_for_function('window.__sorter.S.painted === 3')  # back at the old position
        self.assertEqual(self.ui_good(), {0, 2})


    def test_extra_good_review(self):
        """v4: a saved result, then 추가 GOOD 검토 over the photos still REJECT."""
        label = os.path.basename(self.photos)
        good_txt, reject_txt = Path(self.out, label + '_GOOD.txt'), Path(self.out, label + '_REJECT.txt')
        good_txt.write_bytes(b'IMG_0001.jpg\r\nIMG_0003.jpg\r\n')
        reject_txt.write_bytes(''.join('IMG_%04d.jpg\r\n' % i for i in range(self.N) if i not in (1, 3)).encode())
        page = self.page
        page.goto(self.web.url)
        page.fill('#folder', self.photos)
        page.fill('#output', self.out)
        page.wait_for_selector('#extra:not(.hidden)')
        self.assertIn('GOOD 2 / REJECT %d' % (self.N - 2), page.inner_text('#extra'))
        page.click('#extraBtn')
        page.wait_for_function('window.__sorter.S.painted === 0', timeout=30000)
        names = self.js('window.__sorter.S.names')
        self.assertEqual((len(names), names[:3]), (self.N - 2, ['IMG_0000.jpg', 'IMG_0002.jpg', 'IMG_0004.jpg']))
        self.assertEqual(page.inner_text('#hPos'), 'REJECT %s장 중 1번째' % format(self.N - 2, ','))
        self.assertTrue(page.is_visible('#hExtra'))
        self.page.keyboard.press('ArrowRight')  # IMG_0002
        self.wait_painted()
        self.assertEqual(self.shown_index(), 2)
        time.sleep(0.2)
        self.page.keyboard.press('Space')  # IMG_0002 GOOD, on to IMG_0004
        self.wait_painted()
        self.assertEqual(self.shown_index(), 4)
        self.assertEqual(page.inner_text('#hGoodLabel') + ' ' + page.inner_text('#hGood'), '추가 GOOD 1')
        self.page.keyboard.press('Escape')
        self.page.keyboard.press('Enter')  # menu → review
        page.wait_for_selector('#review.show')
        page.wait_for_function("document.querySelectorAll('.cell').length === 1")
        self.assertIn('기존 GOOD 2장', page.inner_text('#rExtra'))
        page.keyboard.press('Control+s')
        page.keyboard.press('Enter')  # unseen photos stay REJECT: save anyway
        page.wait_for_selector('#done.show')
        self.assertEqual(good_txt.read_bytes(), b'IMG_0001.jpg\r\nIMG_0002.jpg\r\nIMG_0003.jpg\r\n')
        self.assertNotIn(b'IMG_0002.jpg', reject_txt.read_bytes())
        self.assertEqual(len(reject_txt.read_bytes().split(b'\r\n')) - 1, self.N - 3)
        files = os.listdir(self.out)
        self.assertEqual(len([f for f in files if '_이전_' in f]), 2)
        added = [f for f in files if '_GOOD_추가_' in f]
        self.assertEqual(Path(self.out, added[0]).read_bytes(), b'IMG_0002.jpg\r\n')
        self.assertIn('추가 GOOD', page.inner_text('#doneFiles'))

@unittest.skipIf(sync_playwright is None, 'playwright / Pillow not installed')
class TenThousandTest(unittest.TestCase):
    def test_ten_thousand_photos(self):
        photos = tempfile.mkdtemp(prefix='LOT_10K_')
        out, base = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            for i in range(10000):
                Image.new('RGB', (320, 240), color_of(i % 512)).save(os.path.join(photos, 'P_%05d.jpg' % i), quality=85)
            controller = server.Controller(base, reader=SlowShare(0.02))
            web = server.Server(controller, runtime.inline_ui(APP_DIR / 'ui'))
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport={'width': 1400, 'height': 900})
                page.goto(web.url)
                page.fill('#folder', photos)
                page.fill('#output', out)
                page.wait_for_function("!document.getElementById('startBtn').disabled")
                started = time.monotonic()
                page.keyboard.press('Enter')
                page.wait_for_function('window.__sorter.S.painted === 0', timeout=30000)
                first = time.monotonic() - started
                for _ in range(300):
                    page.keyboard.press('ArrowRight')
                    time.sleep(0.01)
                page.wait_for_function('window.__sorter.S.painted === window.__sorter.current()')
                trace = page.evaluate('window.__sorter.trace')
                lat = sorted(t['frame'] - t['keyT'] for t in trace if t['type'] == 'paint' and t.get('keyT') is not None)
                stats = controller.state()['stats']
                page.keyboard.press('End')
                page.wait_for_function('window.__sorter.S.painted === window.__sorter.current()')
                # 2,000 GOOD photos in the review grid (virtual scrolling)
                page.evaluate('(() => { const S = window.__sorter.S; for (let i = 0; i < 10000; i += 5) { S.good[i] = 1; } S.goodCount = 2000; })()')
                t0 = time.monotonic()
                page.keyboard.press('Escape')
                page.keyboard.press('Enter')
                page.wait_for_function("document.querySelectorAll('.cell').length > 0")
                review = time.monotonic() - t0
                cells = page.evaluate("document.querySelectorAll('.cell').length")
                page.evaluate("document.getElementById('grid').scrollTop = 1e9")
                page.wait_for_function("Array.from(document.querySelectorAll('.cell .cname')).some(e => e.textContent === 'P_09995.jpg')")
                browser.close()
            web.close()
            controller.close()
            print('\n  10,000 photos: start→first photo %.2f s, key→frame p50 %.1f ms p95 %.1f ms, '
                  'review open %.2f s (%d cells in DOM), cache %d photos / %.1f MB'
                  % (first, statistics.median(lat), lat[int(len(lat) * 0.95)], review, cells, stats['cached'], stats['cached_bytes'] / 1e6))
            self.assertLess(first, 5)
            self.assertLess(cells, 200)  # only the visible rows exist
            self.assertLess(statistics.median(lat), 34)
        finally:
            for path in (photos, out, base):
                shutil.rmtree(path, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
