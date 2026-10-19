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


# Header of the SPC system export the owner attached to issue #22 (values below are made up).
SPC_HEADERS = ('회사|라인|장비타입|PLAN_NAME|PLAN_DESC|Item|SPEC_NAME|플랜트|공정|PROC_NAME|패키지|DIMENSION|LEAD|STRIP_MARK|고객사|디바이스|'
               'PART_NAME|장비|장비명|LOT_ID|수정자|수정일시|USR_CMF_01|RESULT|USL|TARGET|LSL|EXT_MV|EXT_SIGMA|EXT_MIN|EXT_MAX|EXT_MEDIAN|'
               'EXT_AVERAGE|SITE_QTY|VALUE_COUNT|DISPLAY_FLAG|EXT_MV_UCL|EXT_MV_CENTER|EXT_MV_LCL|EXT_RANGE_UCL|EXT_RANGE_CENTER|EXT_RANGE_LCL|'
               'EXT_RAW_UCL|EXT_RAW_CENTER|EXT_RAW_LCL|TRAN_TIME|UNIT_NUM|DATA_SEQ|SPEC_SEQ|EXT_EWMA_M|EXT_EWMA_S|EXT_EWMA_R|EXT_MA|EXT_MS|'
               'DATA_DESC|DATA_INTERN_DESC|ACCEPT_FLAG|SPEC_LIMIT_ENABLE|RV_STORE_FLAG|LIMIT_ENABLE|IS_NULLVALUE|EXT_SIGMA_LCL|EXT_SIGMA_CENTER|'
               'EXT_SIGMA_UCL|EXT_EWMA_MV_LCL|EXT_EWMA_MV_CENTER|EXT_EWMA_MV_UCL|EXT_MA_MV_LCL|EXT_MA_MV_CENTER|EXT_MA_MV_UCL|EWMA_S_LCL|'
               'EWMA_S_CENTER|EWMA_S_UCL|EWMA_R_LCL|EWMA_R_CENTER|EWMA_R_UCL|EXT_MS_MV_LCL|EXT_MS_MV_CENTER|EXT_MS_MV_UCL|CL_ORIGIN|CPK|'
               'DATA_SEQ1|UNIT_NUM1|' + '|'.join('VALUE_%d' % i for i in range(1, 26)) + '|CNT').split('|')
SPC_SWING = [0.3, 0.1, 0.4, 0.2, 0.5]
SPC_OUT = 10              # data index above EXT_MV_UCL (OCAP)
SPC_RUN = range(20, 28)   # 8 points above EXT_MV_CENTER: the 7th and 8th break the 7 run
SPC_SIGMA_OUT = 5         # EXT_SIGMA above EXT_SIGMA_UCL


def spc_values():
    vals = [round(6.52 + (-1) ** i * SPC_SWING[i % 5], 2) for i in range(36)]  # alternating around EXT_MV_CENTER 6.52
    vals[SPC_OUT] = 8.9
    vals[SPC_RUN[0] - 1] = vals[SPC_RUN[-1] + 1] = 6.2
    for k, i in enumerate(SPC_RUN):
        vals[i] = 6.9 + 0.03 * (k % 3)
    return vals


def spc_rows():
    t0 = datetime.datetime(2026, 7, 1, 2, 6, 2)
    rows = [SPC_HEADERS]
    for i, v in enumerate(spc_values()):
        r = dict.fromkeys(SPC_HEADERS)
        r.update({'회사': 'K5', '라인': 'AS11100', 'PLAN_NAME': 'PLAN-A', 'Item': 'I02214', 'SPEC_NAME': 'TSV-COPLANARITY', '공정': 6311,
                  'DIMENSION': 12, 'LEAD': 134, '장비명': 'AOI-16', 'LOT_ID': 'LOT%03d.C0W' % i, '수정일시': t0 + datetime.timedelta(hours=i),
                  'USL': 13, 'LSL': 0, 'EXT_MV': v, 'EXT_SIGMA': 2.5 if i == SPC_SIGMA_OUT else 0.68,
                  'EXT_SIGMA_LCL': 0.0, 'EXT_SIGMA_CENTER': 0.564, 'EXT_SIGMA_UCL': 2.279, 'EXT_AVERAGE': v, 'SITE_QTY': 25, 'VALUE_COUNT': 25,
                  'DISPLAY_FLAG': 'Y', 'EXT_MV_UCL': 8.234, 'EXT_MV_CENTER': 6.52, 'EXT_MV_LCL': 4.805, 'TRAN_TIME': t0 + datetime.timedelta(hours=i),
                  'UNIT_NUM': 1, 'DATA_SEQ': 8153366 + i, 'SPEC_SEQ': 129588, 'ACCEPT_FLAG': 'YYYYYNYYYY', 'CPK': 3.2, 'VALUE_1': v, 'CNT': 514})
        rows.append([r[h] for h in SPC_HEADERS])
    return rows


SAVE_PICKER = """window.showSaveFilePicker = async (o) => {
  window.__savedAs = o.suggestedName;
  const root = await navigator.storage.getDirectory();
  return await root.getFileHandle('saved_copy.xlsx', {create: true});
};"""

GET_FILE = """async (name) => {
  const root = await navigator.storage.getDirectory();
  const f = await (await root.getFileHandle(name)).getFile();
  const u8 = new Uint8Array(await f.arrayBuffer());
  let s = ''; for (let i = 0; i < u8.length; i += 8192) s += String.fromCharCode.apply(null, u8.subarray(i, i + 8192));
  return btoa(s);
}"""


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
        self.page.add_init_script(SAVE_PICKER)
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
        self.page.check('#liveChk')  # off by default since #24 (fixed-period viewer)
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
        self.page.check('#liveChk')  # off by default since #24 (fixed-period viewer)
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

    # issue #22: SPC system format, data table, double-click, recommended values, saved copy
    def test_spc_system_format_is_recognised(self):
        self.open_file('20261019214451.xlsx', workbook(spc_rows()))
        t = self.js('() => { const t = window.__spc.table(); return [t.spcForm, t.values, t.label, t.item, t.roles]; }')
        self.assertEqual(t[:4], [True, ['EXT_MV'], 'TRAN_TIME', 'Item'])
        self.assertEqual(t[4], {'USL': 'USL', 'LSL': 'LSL', 'UCL': 'EXT_MV_UCL', 'LCL': 'EXT_MV_LCL', 'CL': 'EXT_MV_CENTER'})
        res = self.results()
        self.assertEqual([r['name'] for r in res], ['I02214'])
        self.assertEqual(res[0]['src'], '엑셀 열')
        self.assertEqual(res[0]['label'], '2026-07-01 02:06')
        yellow = self.js('() => window.__spc.yellow()')
        run_rows = [str(i + 2) for i in SPC_RUN][6:]
        self.assertEqual(sorted(yellow, key=int), [str(SPC_OUT + 2)] + run_rows)  # Excel row = data index + 2
        self.assertEqual(yellow[str(SPC_OUT + 2)], ['R1'])
        self.assertEqual(yellow[run_rows[0]], ['R2'])
        self.assertEqual(self.page.locator('#dataTable tbody tr.y').count(), 3)
        self.assertEqual(self.page.locator('#dataTable tbody tr').count(), 36)
        bg = self.js("() => getComputedStyle(document.querySelector('#dataTable tr.y td')).backgroundColor")
        self.assertEqual(bg, 'rgb(255, 245, 157)')
        self.page.check('#flagOnly')
        self.assertEqual(self.page.locator('#dataTable tbody tr').count(), 3)

    # issue #23: XBAR + SIGMA charts with UCL/LCL lines only, histogram, date and time on the X axis
    def test_spc_system_format_draws_xbar_and_sigma(self):
        self.open_file('x.xlsx', workbook(spc_rows()))
        r = self.js("""() => { const r = window.__spc.results()[0];
            return {sigma: r.sigma.values.slice(0, 7), ucl: r.sigma.ucl[0], lcl: r.sigma.lcl[0], rflags: r.rangeFlags, lots: r.lots.slice(0, 1),
                    card: document.querySelector('.item-card').classList.contains('spc'), stats: document.querySelector('.istats').textContent}; }""")
        self.assertEqual(r['sigma'][SPC_SIGMA_OUT], 2.5)
        self.assertEqual(r['sigma'][0], 0.68)
        self.assertEqual((r['ucl'], r['lcl']), (2.279, 0.0))
        self.assertEqual(r['rflags'], [SPC_SIGMA_OUT])
        self.assertEqual(r['lots'], ['LOT000.C0W'])
        self.assertTrue(r['card'])
        self.assertIn('XBAR · SIGMA', r['stats'])
        # the XBAR chart draws only UCL/LCL: USL 13 / LSL 0 do not stretch its scale
        dom = self.js("""() => { const h = document.querySelector('.cx')._hit; return [h.Y(8.234), h.Y(4.805), h.Y(13)]; }""")
        self.assertGreater(dom[1] - dom[0], 150)
        self.assertLess(dom[2], 0)
        # hover the SIGMA point: tooltip with LOT, SIGMA, limits
        self.page.locator('.item-card .cr').first.scroll_into_view_if_needed()
        xy = self.js("""(i) => { const c = document.querySelector('.cr'), h = c._hit, b = c.getBoundingClientRect();
            return [b.left + h.X(i), b.top + h.Y(h.res.sigma.values[i])]; }""", SPC_SIGMA_OUT)
        self.page.mouse.move(xy[0], xy[1])
        tip = self.page.locator('#tip').text_content()
        self.assertIn('SIGMA 2.5', tip)
        self.assertIn('LOT LOT005.C0W', tip)
        self.assertIn('2026-07-01 07:06', tip)
        # double-click on the SIGMA chart selects the row too
        self.page.mouse.dblclick(xy[0], xy[1])
        self.assertEqual(self.js('() => window.__spc.selected()'), SPC_SIGMA_OUT + 2)
        # histogram: frequencies add up to the points, spec limits and ±3σ lines
        h = self.js("() => { const c = document.querySelector('.ch'); return [c._bins, c._marks]; }")
        self.assertEqual(sum(h[0]), 36)
        self.assertEqual(h[1], ['LSL', 'USL', '-3σ', '+3σ'])

    def test_date_time_labels_on_two_lines(self):
        self.open_file('x.xlsx', workbook(spc_rows()))
        texts = self.js("""() => { const out = [], c = document.querySelector('.cx'), ctx = c.getContext('2d'), f = ctx.fillText;
            ctx.fillText = function (t) { out.push(String(t)); return f.apply(this, arguments); };
            window.__spc.refresh(true); return new Promise(r => setTimeout(() => { ctx.fillText = f; r(out); }, 300)); }""")
        self.assertIn('2026-07-02', texts)
        self.assertIn('11:06', texts)  # labels counted from the first point since #24 (02:06 + 3 h steps)
        self.assertIn('XBAR 차트', texts)
        self.assertNotIn('CL', [t.split(' ')[0] for t in texts])
        self.assertNotIn('USL', [t.split(' ')[0] for t in texts])

    def test_double_click_point_goes_to_its_row(self):
        self.open_file('d.xlsx', workbook(spc_rows()))
        self.page.locator('.item-card .cx').first.scroll_into_view_if_needed()
        xy = self.js("""(i) => { const c = document.querySelector('.cx'), h = c._hit, r = c.getBoundingClientRect();
            return [r.left + h.X(i), r.top + h.Y(h.res.x[i])]; }""", SPC_OUT)
        self.page.mouse.dblclick(xy[0], xy[1])
        self.assertEqual(self.js('() => window.__spc.selected()'), SPC_OUT + 2)
        tr = self.page.locator('#dataTable tr.sel')
        self.assertEqual(tr.get_attribute('data-row'), str(SPC_OUT + 2))
        self.assertTrue(self.js("""() => { const r = document.querySelector('#dataTable tr.sel').getBoundingClientRect();
            return r.top >= 0 && r.bottom <= window.innerHeight; }"""))
        self.assertFalse(self.page.locator('#fixOneBtn').is_disabled())

    def test_recommended_values_and_saved_copy(self):
        data = workbook(spc_rows())
        self.open_file('src.xlsx', data)
        mv = SPC_HEADERS.index('EXT_MV')
        # one row: the point above UCL
        self.page.click('#dataTable tr[data-row="%d"] td.rn' % (SPC_OUT + 2))
        self.page.click('#fixOneBtn')
        edits = self.js('() => Object.values(window.__spc.edits())')
        self.assertEqual(len(edits), 1)
        e = edits[0]
        self.assertEqual((e['row'], e['col'], e['orig']), (SPC_OUT + 2, mv, 8.9))
        self.assertLessEqual(abs(e['value'] - 6.52), 2 * (8.234 - 6.52) / 3 + 1e-9)  # inside ±2σ
        self.assertNotIn(str(SPC_OUT + 2), self.js('() => window.__spc.nowFlags()'))
        self.assertEqual(self.page.locator('#dataTable td.fixed').count(), 2)  # the value column after 판정 and the same cell in place
        self.assertEqual(self.page.locator('#dataTable tr.y').count(), 3)  # the row stays yellow
        # all: one value clears the 7 run
        self.page.click('#fixAllBtn')
        self.assertEqual(self.js('() => window.__spc.nowFlags()'), {})
        edits = self.js('() => Object.values(window.__spc.edits())')
        self.assertEqual(len(edits), 2)
        flags = self.js('() => window.__spc.results()[0].flags')
        for rule in ('OOS', 'R1', 'R2', 'R3'):
            self.assertNotIn(rule, flags)
        self.assertTrue(self.page.locator('#fixAllBtn').is_disabled())
        c1 = self.js("() => getComputedStyle(document.getElementById('fixOneBtn')).backgroundColor")
        c2 = self.js("() => getComputedStyle(document.getElementById('fixAllBtn')).backgroundColor")
        self.assertNotEqual(c1, c2)
        # save the copy
        self.page.click('#saveBtn')
        self.page.wait_for_function("() => document.getElementById('status').textContent.includes('수정본 저장')")
        self.assertRegex(self.js('() => window.__savedAs'), r'^src_SPC수정_\d{8}_\d{4}\.xlsx$')
        saved = base64.b64decode(self.js(GET_FILE, 'saved_copy.xlsx'))
        self.assertEqual(base64.b64decode(self.js(GET_FILE, 'src.xlsx')), data)  # the original is untouched
        ws = openpyxl.load_workbook(io.BytesIO(saved)).active
        orig = openpyxl.load_workbook(io.BytesIO(data)).active
        changed = {(x['row'], x['col']): x['value'] for x in edits}
        for row in range(1, ws.max_row + 1):
            for col in range(1, len(SPC_HEADERS) + 1):
                c = ws.cell(row, col)
                if (row, col - 1) in changed:
                    self.assertEqual(c.value, changed[(row, col - 1)])
                    self.assertEqual(c.fill.fgColor.rgb, 'FFFF0000')
                else:
                    self.assertEqual(c.value, orig.cell(row, col).value)
        for row in map(int, self.js('() => window.__spc.yellow()')):
            self.assertEqual(ws.cell(row, 1).fill.fgColor.rgb, 'FFFFFF00')
        self.assertNotEqual(ws.cell(3, 1).fill.fgColor.rgb, 'FFFFFF00')
        # undo
        self.page.click('#undoBtn')
        self.assertEqual(self.js('() => window.__spc.edits()'), {})
        self.assertEqual(len(self.js('() => window.__spc.nowFlags()')), 3)

    def test_edits_follow_live_refresh(self):
        self.js('() => { window.__spc.settings.pollSec = 1; }')
        self.page.check('#liveChk')  # off by default since #24 (fixed-period viewer)
        rows = spc_rows()
        self.open_file('live2.xlsx', workbook(rows))
        self.page.click('#fixAllBtn')
        self.assertEqual(len(self.js('() => window.__spc.edits()')), 2)
        rows[SPC_OUT + 1][SPC_HEADERS.index('EXT_MV')] = 6.5  # fixed in Excel and saved
        self.put('live2.xlsx', workbook(rows))
        self.page.wait_for_function('() => Object.keys(window.__spc.edits()).length === 1', timeout=8000)

    def test_html_table_saved_as_xls(self):
        rows = spc_rows()
        html = '<html><body><table>' + ''.join('<tr>' + ''.join('<td>%s</td>' % ('' if v is None else v) for v in r) + '</tr>' for r in rows) + '</table></body></html>'
        self.open_file('export.xls', html.encode('utf-8'))
        self.assertEqual(self.js('() => window.__spc.table().spcForm'), True)
        self.assertEqual(len(self.js('() => window.__spc.yellow()')), 3)
        self.page.click('#fixAllBtn')
        saved = bytes(self.js('() => Array.from(window.__spc.copyBytes())'))
        ws = openpyxl.load_workbook(io.BytesIO(saved)).active
        self.assertEqual(ws.cell(1, 1).value, '회사')
        self.assertEqual(ws.cell(SPC_OUT + 2, SPC_HEADERS.index('EXT_MV') + 1).fill.fgColor.rgb, 'FFFF0000')
        self.assertEqual(ws.cell(SPC_OUT + 2, 1).fill.fgColor.rgb, 'FFFFFF00')
        self.assertTrue(self.js("() => window.__spc.copyName().endsWith('.xlsx')"))

    def test_fix_all_engine_breaks_a_run_with_one_value(self):
        vals = [10, 9, 11, 10.5, 9.5, 10, 10.2, 9.8] * 3 + [10.3] * 9
        r = self.js("""(vals) => { const it = {name: 't', values: vals, labels: vals.map(String), cols: {}};
            const opts = {baseline: 24}, out = SPC.fixAll(it, opts, SPC.FIX_RULES);
            const v = vals.slice(); out.changes.forEach(c => { v[c.row] = c.value; });
            return {out, flags: SPC.analyze(Object.assign({}, it, {values: v}), opts).flags}; }""", vals)
        self.assertEqual(len(r['out']['changes']), 1)
        self.assertEqual(r['out']['changes'][0]['row'], 30)  # the 7th point of the run
        self.assertNotIn('R2', r['flags'])

    # issue #24: a long period scrolls sideways instead of being cut; auto refresh is off by default
    def test_long_period_scrolls_sideways(self):
        self.assertFalse(self.page.is_checked('#liveChk'))
        self.open_file('long.xlsx', workbook(long_rows(400)))
        self.assertEqual(self.js('() => window.__spc.settings.window'), 0)
        self.assertEqual(self.page.input_value('#pitchSel'), '16')
        geo = self.js("""() => { const s = document.querySelector('.xscroll'), c = s.querySelector('.cx');
            return {sw: s.scrollWidth, cw: s.clientWidth, canvas: c.clientWidth, from: c._hit.from, to: c._hit.to, n: c._hit.res.points.length}; }""")
        self.assertEqual(geo['n'], 400)  # nothing cut off
        self.assertGreaterEqual(geo['sw'], 400 * 16)
        self.assertEqual(geo['canvas'], geo['cw'])  # the canvas stays the card width
        self.assertEqual(geo['from'], 0)
        self.assertLess(geo['to'], 120)
        # scroll to the end: the last points are drawn, the MR chart follows, the Y axis stays at the left
        self.js("() => { const s = document.querySelector('.xscroll'); s.scrollLeft = s.scrollWidth; }")
        self.page.wait_for_function("() => document.querySelector('.cx')._hit.to === 400")
        h = self.js("""() => { const c = document.querySelector('.cx')._hit, r = document.querySelector('.cr')._hit;
            return [c.from, r.to, c.X(399) < document.querySelector('.cx').clientWidth - 92]; }""")
        self.assertGreater(h[0], 250)
        self.assertEqual(h[1], 400)
        self.assertTrue(h[2])
        # hover / double-click still find the right point after scrolling
        self.page.locator('.item-card .cx').first.scroll_into_view_if_needed()
        xy = self.js("""(i) => { const c = document.querySelector('.cx'), h = c._hit, b = c.getBoundingClientRect();
            return [b.left + h.X(i), b.top + h.Y(h.res.x[i])]; }""", 395)
        self.page.mouse.dblclick(xy[0], xy[1])
        row = self.js('() => window.__spc.selected()')
        self.assertEqual(row, self.js("() => { const r = document.querySelector('.cx')._hit.res; return r.excelRows[r.points[395].rows[0]]; }"))
        # picking a row in the table scrolls the chart back to it
        first = self.js("() => { const r = document.querySelector('.cx')._hit.res; return r.excelRows[r.points[3].rows[0]]; }")
        self.page.locator('#dataTable tr[data-row="%d"]' % first).click()
        self.page.wait_for_function("() => document.querySelector('.cx')._hit.from <= 3")
        # 화면에 맞춤: the whole period on one screen, no scroll
        self.page.select_option('#pitchSel', '0')
        geo = self.js("""() => { const s = document.querySelector('.xscroll'), h = s.querySelector('.cx')._hit; return [s.scrollWidth - s.clientWidth, h.from, h.to]; }""")
        self.assertEqual(geo, [0, 0, 400])


if __name__ == '__main__':
    unittest.main()
