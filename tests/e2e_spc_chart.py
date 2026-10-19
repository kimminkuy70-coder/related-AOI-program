# -*- coding: utf-8 -*-
"""SPC Chart HTML (programs/SPC_Chart_HTML): the built single .html in Chromium (Edge's engine).

Edge's file dialog cannot be driven, so showOpenFilePicker hands out a file of the page's private
file system (OPFS): a real file handle, re-read the same way as a picked Excel file. Rewriting that
file stands in for saving the workbook in Excel. Each test runs in a fresh browser context.

    python -m unittest tests.e2e_spc_chart -v
"""
import base64
import datetime
import functools
import http.server
import io
import json
import subprocess
import sys
import threading
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
    import openpyxl
except ImportError:  # pragma: no cover
    sync_playwright = None

REPO = Path(__file__).resolve().parent.parent
PROGRAM = REPO / 'programs' / 'SPC_Chart_HTML'
VERSION = json.loads((PROGRAM / 'version.json').read_text(encoding='utf-8'))
PAGE = VERSION['release'] + '.html'

PICKER = """
window.showOpenFilePicker = async () => {
  const root = await navigator.storage.getDirectory();
  return [await root.getFileHandle(window.__pick, {create: true})];
};
"""

PUT_FILE = """async ([name, b64]) => {
  const root = await navigator.storage.getDirectory();
  const h = await root.getFileHandle(name, {create: true});
  const w = await h.createWritable();
  await w.write(Uint8Array.from(atob(b64), c => c.charCodeAt(0)));
  await w.close();
}"""

ANALYZE = """([values, opts]) => {
  const r = SPC.analyze({name: 't', values, labels: values.map((_, i) => 'p' + i), cols: {}}, opts || {});
  return {cl: r.limits.CL.values[0], ucl: r.limits.UCL.values[0], lcl: r.limits.LCL.values[0], flags: r.flags,
          events: r.events.map(e => [e.rule, e.start, e.end]), range: r.range, stats: r.stats, points: r.points.length};
}"""


def workbook(rows, sheet='Data'):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def long_rows(n, extra=()):
    """Two items in one value column (항목 · 측정값), spec columns on every row."""
    t0 = datetime.datetime(2026, 10, 1, 8, 0)
    rows = [['날짜', '항목', '측정값', 'USL', 'LSL']]
    for i in range(n):
        d = t0 + datetime.timedelta(hours=i)
        rows.append([d, '두께', 10 + (0.05 if i % 2 else -0.05), 10.5, 9.5])
        rows.append([d, '폭', 25 + (0.1 if i % 3 else -0.1), 26, 24])
    rows.extend(extra)
    return rows


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class BuiltFileTest(unittest.TestCase):
    def test_built_file_is_current_and_self_contained(self):
        result = subprocess.run([sys.executable, str(REPO / 'tools' / 'build_html.py'), '--check', '--program', 'SPC_Chart_HTML'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        html = (PROGRAM / PAGE).read_text(encoding='utf-8')
        self.assertIn("connect-src 'none'", html)
        self.assertNotIn(' src="', html.split('<body>', 1)[1])  # nothing loaded from elsewhere
        self.assertNotIn('href="http', html)
        self.assertIn('<title>%s</title>' % VERSION['title'], html)
        self.assertIn('개발자 : 김민규', html)


@unittest.skipIf(sync_playwright is None, 'playwright / openpyxl not installed')
class SpcChartTest(unittest.TestCase):
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
        # the page forbids eval (CSP); Playwright's waits need it
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

    def js(self, expr, arg=None):
        return self.page.evaluate(expr, arg) if arg is not None else self.page.evaluate(expr)

    def put(self, name, data):
        self.js(PUT_FILE, [name, base64.b64encode(data).decode()])

    def open_file(self, name, data):
        self.put(name, data)
        self.js('n => { window.__pick = n; }', name)
        self.page.click('#openBtn')
        self.page.wait_for_function('() => window.__spc.results().length > 0')

    def results(self):
        return self.js("""() => window.__spc.results().map(r => ({name: r.name, n: r.points.length, last: r.x[r.x.length - 1],
            usl: r.limits.USL.values && r.limits.USL.values[0], src: r.limits.UCL.source, events: r.events.map(e => e.rule),
            label: r.points[0] && r.points[0].label}))""")

    # engine
    def test_imr_limits(self):
        r = self.js(ANALYZE, [[10, 12, 11, 13, 12]])
        mr = (2 + 1 + 2 + 1) / 4
        self.assertAlmostEqual(r['cl'], 11.6)
        self.assertAlmostEqual(r['ucl'], 11.6 + 3 * mr / 1.128, places=9)
        self.assertAlmostEqual(r['lcl'], 11.6 - 3 * mr / 1.128, places=9)
        self.assertAlmostEqual(r['range']['ucl'], 3.267 * mr)
        self.assertEqual(r['events'], [])

    def test_xbar_r_limits(self):
        vals = [10, 11, 12, 11, 10, 12, 13, 11, 12, 12]
        r = self.js(ANALYZE, [vals, {'subgroup': 5}])
        self.assertEqual(r['points'], 2)
        rbar = (2 + 2) / 2
        self.assertAlmostEqual(r['cl'], sum(vals) / 10)
        self.assertAlmostEqual(r['ucl'], sum(vals) / 10 + 0.577 * rbar)
        self.assertAlmostEqual(r['range']['ucl'], 2.114 * rbar)

    def test_run_of_seven(self):
        base = [10, 9, 11, 10.5, 9.5, 10, 10.2, 9.8] * 3
        six = self.js(ANALYZE, [base + [10.3] * 6, {'baseline': len(base)}])
        self.assertNotIn('R2', six['flags'])
        seven = self.js(ANALYZE, [base + [10.3] * 7, {'baseline': len(base)}])
        self.assertEqual(seven['flags']['R2'], [len(base) + 6])
        five = self.js(ANALYZE, [base + [10.3] * 5, {'baseline': len(base), 'n': {'R2': 5}}])
        self.assertEqual(five['flags']['R2'], [len(base) + 4])

    def test_trend_of_seven_is_one_event(self):
        vals = [10, 9, 11, 10, 9.5, 10.5, 10] * 3 + [9.1, 9.3, 9.5, 9.7, 9.9, 10.1, 10.3, 10.4]
        r = self.js(ANALYZE, [vals])
        n = len(vals)
        self.assertEqual(r['flags']['R3'], [n - 2, n - 1])  # 7th and 8th rising point
        self.assertIn(['R3', n - 2, n - 1], r['events'])

    def test_beyond_limits_and_spec(self):
        vals = [10, 10.1, 9.9, 10, 10.1, 9.9, 10, 10.05, 9.95, 10] * 2 + [11]
        r = self.js("""(vals) => { const n = vals.length;
            const res = SPC.analyze({name: 't', values: vals, labels: vals.map(String), cols: {USL: vals.map(() => 10.8), LSL: [9.2]}}, {baseline: n - 1});
            return {flags: res.flags, usl: res.limits.USL.values[n - 1], lsl: res.limits.LSL.values[n - 1], cpk: res.stats.cpk}; }""", vals)
        self.assertEqual(r['flags']['R1'], [len(vals) - 1])
        self.assertEqual(r['flags']['OOS'], [len(vals) - 1])
        self.assertEqual((r['usl'], r['lsl']), (10.8, 9.2))  # one LSL cell carries to every row
        self.assertIsNotNone(r['cpk'])

    def test_two_of_three_beyond_two_sigma(self):
        vals = [10, 10.2, 9.8, 10.1, 9.9, 10, 10.2, 9.8, 10.1, 9.9]
        r = self.js("""(vals) => { const res = SPC.analyze({name: 't', values: vals.concat([10.75, 10, 10.8]), labels: [], cols: {}},
            {manual: {CL: 10, UCL: 11, LCL: 9}}); return res.flags; }""", vals)
        self.assertEqual(r.get('R4'), [12])
        self.assertNotIn('R1', r)

    # file reading and live refresh
    def test_long_format_xlsx_with_dates_and_spec(self):
        self.open_file('data.xlsx', workbook(long_rows(30)))
        res = {r['name']: r for r in self.results()}
        self.assertEqual(sorted(res), ['두께', '폭'])
        self.assertEqual(res['두께']['n'], 30)
        self.assertEqual(res['두께']['usl'], 10.5)
        self.assertEqual(res['두께']['label'], '2026-10-01 08:00')
        self.assertEqual(res['두께']['events'], [])
        t = self.js('() => { const t = window.__spc.table(); return [t.label, t.item, t.values]; }')
        self.assertEqual(t, ['날짜', '항목', ['측정값']])
        self.assertEqual(self.page.locator('.item-card').count(), 2)
        self.assertTrue(self.js("""() => { const c = document.querySelector('.cx');
            const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
            for (let i = 0; i < d.length; i += 4) if (d[i + 2] > 200 && d[i] < 80) return true; return false; }"""))  # blue data line drawn

    def test_saving_the_workbook_updates_the_chart_and_raises_alarm(self):
        self.js('() => { window.__spc.settings.pollSec = 1; }')
        self.open_file('live.xlsx', workbook(long_rows(30)))
        self.assertTrue(self.page.locator('#alarm').is_hidden())
        last = datetime.datetime(2026, 10, 3, 0, 0)
        self.put('live.xlsx', workbook(long_rows(30, [[last, '두께', 10.9, 10.5, 9.5]])))  # "Ctrl+S" in Excel
        self.page.wait_for_function("() => window.__spc.results().find(r => r.name === '두께').points.length === 31", timeout=8000)
        res = {r['name']: r for r in self.results()}
        self.assertAlmostEqual(res['두께']['last'], 10.9)
        self.assertIn('OOS', res['두께']['events'])
        self.assertTrue(self.page.locator('#alarm').is_visible())
        self.assertIn('두께', self.page.inner_text('#alarmText'))
        self.assertEqual(self.page.locator('#events tr.new').count(), len(res['두께']['events']))
        # OCAP: mark the event done
        self.page.click('#alarmOcap')
        self.assertIn('Hold', self.page.inner_text('.steps'))
        self.page.check('#dDone')
        self.page.fill('#dNote', '재측정 OK')
        self.page.click('#dOk')
        self.assertIn('재측정 OK', self.page.inner_text('#events'))

    def test_broken_save_keeps_last_chart(self):
        self.js('() => { window.__spc.settings.pollSec = 1; }')
        self.open_file('b.xlsx', workbook(long_rows(10)))
        self.put('b.xlsx', b'PK\x03\x04 half written')
        self.page.wait_for_function("() => document.getElementById('status').className.includes('err')", timeout=8000)
        self.assertEqual(len(self.results()), 2)
        self.put('b.xlsx', workbook(long_rows(12)))
        self.page.wait_for_function("() => window.__spc.results()[0].points.length === 12", timeout=8000)

    def test_wide_format_with_limit_columns(self):
        rows = [['Lot', 'A', 'B', 'UCL', 'LCL']] + [['L%02d' % i, 1 + 0.01 * (i % 4), 2 + 0.02 * (i % 3), 1.2, 0.8] for i in range(20)]
        self.open_file('wide.xlsx', workbook(rows))
        res = {r['name']: r for r in self.results()}
        self.assertEqual(sorted(res), ['A', 'B'])
        self.assertEqual(res['A']['src'], '엑셀 열')
        self.assertEqual(res['A']['label'], 'L00')

    def test_csv_in_korean_excel_encoding(self):
        text = '일자,두께\n' + ''.join('2026-10-%02d,%s\n' % (i + 1, 10 + 0.01 * (i % 5)) for i in range(15))
        self.open_file('k.csv', text.encode('cp949'))
        res = self.results()
        self.assertEqual([r['name'] for r in res], ['두께'])
        self.assertEqual(res[0]['n'], 15)

    def test_manual_limits(self):
        self.open_file('m.xlsx', workbook(long_rows(20)))
        self.page.locator('.item-card').first.locator('.lim-btn').click()
        self.page.fill('[data-k="UCL"]', '10.02')
        self.page.click('#dOk')
        r = self.js("() => { const r = window.__spc.results()[0]; return [r.limits.UCL.values[0], r.limits.UCL.source, r.events.length]; }")
        self.assertEqual(r[:2], [10.02, '직접 입력'])
        self.assertGreater(r[2], 0)

    def test_demo(self):
        self.page.click('#demoBtn')
        self.page.wait_for_function('() => window.__spc.results().length === 2')
        self.assertEqual(self.page.locator('.item-card').count(), 2)
        self.assertGreater(self.page.locator('#events tr[data-key]').count(), 0)


if __name__ == '__main__':
    unittest.main()
