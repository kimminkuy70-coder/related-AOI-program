# -*- coding: utf-8 -*-
"""The browser-only speed test page (experiments/browser_speed_test) in Chromium.

The folder dialogs cannot be driven, so showDirectoryPicker is replaced by one that hands
out folders of the page's private file system (OPFS), the photo folder wrapped so every
file read waits like a network share. Everything else is the page's own code.

    python -m unittest tests.e2e_browser_speed_test -v
"""
import functools
import http.server
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

PAGE_DIR = Path(__file__).resolve().parent.parent / 'experiments' / 'browser_speed_test'
N = 300

FAKE_PICKER = """
window.__latency = 0;
window.showDirectoryPicker = async (opts) => {
  const root = await navigator.storage.getDirectory();
  if (opts && opts.mode === 'readwrite') return root.getDirectoryHandle('out', {create: true});
  const real = await root.getDirectoryHandle('LOT_TEST', {create: true});
  return {  // a slow share: every file read waits __latency ms first
    name: real.name, kind: 'directory',
    async *entries() {
      for await (const [name, handle] of real.entries()) {
        yield [name, handle.kind === 'file'
          ? {kind: 'file', name, getFile: async () => { await new Promise(r => setTimeout(r, window.__latency)); return handle.getFile(); }}
          : handle];
      }
    },
  };
};
"""

MAKE_PHOTOS = """async (n) => {
  const root = await navigator.storage.getDirectory();
  for (const name of ['LOT_TEST', 'out']) await root.removeEntry(name, {recursive: true}).catch(() => {});
  const dir = await root.getDirectoryHandle('LOT_TEST', {create: true});
  await dir.getDirectoryHandle('sub', {create: true});
  const write = async (name, blob) => { const w = await (await dir.getFileHandle(name, {create: true})).createWritable(); await w.write(blob); await w.close(); };
  const canvas = new OffscreenCanvas(160, 120), ctx = canvas.getContext('2d');
  for (let i = 1; i <= n; i++) {
    ctx.fillStyle = `rgb(${(i * 37) % 256}, ${(i * 91) % 256}, ${(i * 53) % 256})`;
    ctx.fillRect(0, 0, 160, 120);
    await write(`IMG_${i}.jpg`, await canvas.convertToBlob({type: 'image/jpeg', quality: 0.95}));
  }
  await write('notes.txt', new Blob(['not a photo']));
  await write('scan.tif', new Blob([new Uint8Array(64)]));
}"""

CENTER = """(() => { const c = document.getElementById('view');
  return Array.from(c.getContext('2d').getImageData(c.width >> 1, c.height >> 1, 1, 1).data).slice(0, 3); })()"""


def color(i):
    return [(i * 37) % 256, (i * 91) % 256, (i * 53) % 256]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipIf(sync_playwright is None, 'playwright not installed')
class BrowserSpeedTestPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(QuietHandler, directory=str(PAGE_DIR))
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.url = 'http://127.0.0.1:%d/AOI_Browser_Speed_Test.html' % cls.httpd.server_address[1]
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.httpd.shutdown()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1400, 'height': 860})
        self.errors = []
        self.page.on('pageerror', lambda exc: self.errors.append(str(exc)))
        self.page.on('console', lambda m: self.errors.append(m.text) if m.type == 'error' else None)
        self.page.add_init_script(FAKE_PICKER)
        self.page.goto(self.url)
        self.page.evaluate(MAKE_PHOTOS, N)

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    def js(self, expr):
        return self.page.evaluate(expr)

    def pick(self):
        self.page.click('#pick')
        self.page.wait_for_function("document.getElementById('pickMsg').textContent.startsWith('✓')")
        self.page.wait_for_function('window.__speedTest.S.painted === 0', timeout=15000)

    def shown(self):
        return self.js(CENTER)

    def assert_color(self, i):
        got = self.shown()
        self.assertTrue(all(abs(a - b) <= 6 for a, b in zip(got, color(i))), (got, color(i), i))

    def test_list_view_bench_save_summary(self):
        page, keyboard = self.page, self.page.keyboard
        self.assertIn('폴더 접근 기능 있음', page.inner_text('#env'))
        self.pick()
        self.assertIn('사진 %d장 (TIFF 1장)' % (N + 1), page.inner_text('#pickMsg'))
        names = self.js('window.__speedTest.S.items.map(i => i.name)')
        self.assertEqual(names[:3], ['IMG_1.jpg', 'IMG_2.jpg', 'IMG_3.jpg'])  # Explorer order: IMG_2 before IMG_10
        self.assertEqual(names[9], 'IMG_10.jpg')
        self.assertEqual(names[-1], 'scan.tif')
        self.assert_color(1)
        page.wait_for_function('window.__speedTest.S.cache.size >= 200')  # read ahead in the background
        for _ in range(4):
            keyboard.press('ArrowRight')
            page.wait_for_function('window.__speedTest.S.painted === window.__speedTest.S.pos')
        self.assert_color(5)
        keyboard.press('Space')  # IMG_5 GOOD, on to IMG_6
        page.wait_for_function('window.__speedTest.S.painted === 5')
        self.assert_color(6)
        self.assertEqual(self.js('[...window.__speedTest.S.good]'), [4])
        self.assertGreater(self.js('window.__speedTest.S.keyLat.length'), 0)

        page.click('#bench')
        page.wait_for_function("document.getElementById('benchMsg').textContent.startsWith('완료')", timeout=30000)
        bench = self.js('window.__speedTest.R.bench')
        self.assertEqual([b['conc'] for b in bench], [1, 4, 8, 16])
        self.assertTrue(all(b['perSec'] > 0 and b['errors'] == 0 for b in bench))
        self.assertEqual(page.locator('#benchTable tbody tr').count(), 4)

        page.click('#save')
        page.wait_for_function("document.getElementById('saveMsg').textContent.includes('성공')")
        saved = self.js("""(async () => {
          const out = await (await navigator.storage.getDirectory()).getDirectoryHandle('out');
          const files = [];
          for await (const [name, h] of out.entries()) {
            const bytes = new Uint8Array(await (await h.getFile()).arrayBuffer());
            files.push([name, Array.from(bytes.slice(0, 3)), new TextDecoder().decode(bytes)]);
          }
          return files; })()""")
        self.assertEqual(len(saved), 1)
        name, head, text = saved[0]
        self.assertRegex(name, r'^AOI_브라우저시험_\d{8}_\d{4}\.txt$')
        self.assertEqual(head, [0xEF, 0xBB, 0xBF])  # UTF-8 with BOM, CRLF: Notepad on Korean Windows reads it right
        self.assertTrue(text.startswith('AOI Photo Sorter 브라우저 속도 시험 결과'))
        self.assertIn('\r\n[GOOD으로 고른 사진]\r\nIMG_5.jpg\r\n', text)

        summary = page.input_value('#summary')
        for part in ('사진 %d장' % (N + 1), '목록 읽기', '첫 사진 표시까지', '동시 16:', '키→화면', '결과 저장 시험: 성공'):
            self.assertIn(part, summary)

    def out_tree(self):
        return self.js("""(async () => {
          const out = await (await navigator.storage.getDirectory()).getDirectoryHandle('out');
          const tree = {};
          for await (const [name, h] of out.entries()) {
            if (h.kind !== 'directory') continue;
            tree[name] = {};
            for await (const [f, fh] of h.entries()) tree[name][f] = Array.from(new Uint8Array(await (await fh.getFile()).arrayBuffer()).slice(0, 64)).join(',');
          }
          return tree; })()""")

    def source_head(self, name):
        return self.page.evaluate("""async (name) => {
          const dir = await (await navigator.storage.getDirectory()).getDirectoryHandle('LOT_TEST');
          return Array.from(new Uint8Array(await (await (await dir.getFileHandle(name)).getFile()).arrayBuffer()).slice(0, 64)).join(','); }""", name)

    def test_sort_into_folders_by_result_files(self):
        """⑤: a folder per result .txt (named like it), the listed photos copied in from the photo
        folder; UTF-8 (BOM) and ANSI (CP949) lists, names in another case, names not in the folder;
        running again copies nothing twice and never overwrites a different file."""
        page = self.page
        self.pick()
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        good = tmp / 'LOT_TEST_1차리뷰_20261015_1200_GOOD.txt'
        good.write_bytes('﻿IMG_5.jpg\r\nIMG_7.jpg\r\n불량_없음.jpg\r\n'.encode('utf-8'))
        reject = tmp / 'LOT_TEST_1차리뷰_20261015_1200_REJECT.txt'
        reject.write_bytes('IMG_1.jpg\r\nimg_2.JPG\r\n\r\nIMG_3.jpg\r\n'.encode('cp949'))
        page.set_input_files('#txtInput', [str(good), str(reject)])
        page.wait_for_function("!document.getElementById('sortGo').disabled")
        listing = page.inner_text('#sortList')
        self.assertIn('LOT_TEST_1차리뷰_20261015_1200_GOOD ← 2장 (사진 폴더에 없음 1장)', listing)
        self.assertIn('LOT_TEST_1차리뷰_20261015_1200_REJECT ← 3장', listing)
        # a different file already sits where IMG_3.jpg would go: it must stay as it is
        self.js("""(async () => {
          const out = await (await navigator.storage.getDirectory()).getDirectoryHandle('out', {create: true});
          const d = await out.getDirectoryHandle('LOT_TEST_1차리뷰_20261015_1200_REJECT', {create: true});
          const w = await (await d.getFileHandle('IMG_3.jpg', {create: true})).createWritable(); await w.write('mine'); await w.close(); })()""")
        page.click('#sortGo')
        page.wait_for_function("window.__speedTest.R.sort !== ''")
        result = self.js('window.__speedTest.sortState().result')
        self.assertEqual((result['copied'], result['already'], result['conflict'], result['failed']), (4, 0, 1, 0))
        tree = self.out_tree()
        self.assertEqual(sorted(tree), ['LOT_TEST_1차리뷰_20261015_1200_GOOD', 'LOT_TEST_1차리뷰_20261015_1200_REJECT'])
        self.assertEqual(sorted(tree['LOT_TEST_1차리뷰_20261015_1200_GOOD']), ['IMG_5.jpg', 'IMG_7.jpg'])
        self.assertEqual(sorted(tree['LOT_TEST_1차리뷰_20261015_1200_REJECT']), ['IMG_1.jpg', 'IMG_2.jpg', 'IMG_3.jpg'])
        self.assertEqual(tree['LOT_TEST_1차리뷰_20261015_1200_GOOD']['IMG_7.jpg'], self.source_head('IMG_7.jpg'))
        self.assertEqual(tree['LOT_TEST_1차리뷰_20261015_1200_REJECT']['IMG_3.jpg'], '109,105,110,101')  # 'mine': kept
        self.assertIn('다른 파일이 이미 있어 건너뜀 1', page.inner_text('#sortMsg'))
        self.assertIn('사진 폴더에 없음 1', page.input_value('#summary'))

        page.click('#sortGo')  # again: everything is there already
        page.wait_for_function("window.__speedTest.sortState().result && window.__speedTest.sortState().result.already === 4")
        self.assertEqual(self.js('window.__speedTest.sortState().result.copied'), 0)

        page.keyboard.press('Space')  # IMG_1 GOOD: sort by what was picked here
        page.wait_for_function('window.__speedTest.S.painted === 1')
        page.click('#sortMine')
        self.assertIn('LOT_TEST_GOOD ← 1장', page.inner_text('#sortList'))
        self.assertIn('LOT_TEST_REJECT ← %d장' % N, page.inner_text('#sortList'))

    def test_slow_share_never_skips_a_photo(self):
        """60 ms per file: a held → pages on but only over photos that were on screen, and
        the read-ahead keeps ahead of 10 photos/s."""
        page, keyboard = self.page, self.page.keyboard
        self.js('window.__latency = 60')
        self.pick()
        time.sleep(1.0)  # 8 reads at a time: ~130 photos/s against 10 photos/s of paging
        for _ in range(40):  # a held → (auto-repeat), 110 ms apart
            keyboard.down('ArrowRight')
            time.sleep(0.11)
        keyboard.up('ArrowRight')
        page.wait_for_function('window.__speedTest.S.painted === window.__speedTest.S.pos')
        pos, seen, waits = self.js('[window.__speedTest.S.pos, [...window.__speedTest.S.seen].sort((a, b) => a - b), window.__speedTest.S.waits]')
        self.assertGreaterEqual(pos, 30)
        self.assertEqual(seen, list(range(pos + 1)))  # every photo on the way was on screen
        self.assertLessEqual(waits, 1)  # only the very first photo had to be waited for
        self.assert_color(pos + 1)

    def test_retry_after_failed_reads(self):
        page = self.page
        self.js("window.__fail = true; const orig = window.showDirectoryPicker; window.showDirectoryPicker = async (o) => { "
                "const d = await orig(o); if (o && o.mode === 'readwrite') return d; return {name: d.name, kind: 'directory', "
                "async *entries() { for await (const [n, h] of d.entries()) yield [n, h.kind === 'file' ? {kind: 'file', getFile: "
                "async () => { if (window.__fail) throw new DOMException('share gone', 'NotReadableError'); return h.getFile(); }} : h]; } }; };")
        page.click('#pick')
        page.wait_for_function("document.getElementById('card').textContent.includes('읽기 실패')")
        self.assertGreater(self.js('window.__speedTest.S.errors'), 0)
        self.js('window.__fail = false')
        page.keyboard.press('KeyR')
        page.wait_for_function('window.__speedTest.S.painted === 0')
        self.assert_color(1)


if __name__ == '__main__':
    unittest.main()
