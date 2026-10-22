// SPC Chart HTML: reads an Excel sheet of a fixed period and draws its control charts (scroll sideways through the whole period).
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var SPC = window.SPC;
  var TITLE = document.querySelector('meta[name="spc-title"]').content;
  var ROLES = ['USL', 'LSL', 'UCL', 'LCL', 'CL'];
  var ROLE_WORDS = {
    USL: ['usl', '규격상한', '상한규격', 'upperspec', 'specupper', 'specmax'],
    LSL: ['lsl', '규격하한', '하한규격', 'lowerspec', 'speclower', 'specmin'],
    UCL: ['extmvucl', 'ucl', '관리상한', '상한관리', 'uppercontrol'],
    LCL: ['extmvlcl', 'lcl', '관리하한', '하한관리', 'lowercontrol'],
    CL: ['extmvcenter', 'cl', 'target', 'tgt', '목표', '목표값', '중심', '중심선', 'centerline', 'nominal']
  };
  // SPC system export (one row per lot: EXT_MV with EXT_MV_UCL/CENTER/LCL, EXT_SIGMA with EXT_SIGMA_UCL/CENTER/LCL,
  // USL/LSL, LOT_ID, TRAN_TIME, VALUE_1..25): drawn like the SPC system, an XBAR chart (EXT_MV, UCL/LCL lines only)
  // over a SIGMA chart (EXT_SIGMA), X axis date and time.
  var SPC_FORMAT = {value: 'extmv', needs: 'extmvucl', label: ['trantime', '수정일시', 'lotid'], lot: 'lotid',
    sigma: {value: 'extsigma', UCL: 'extsigmaucl', LCL: 'extsigmalcl', CL: 'extsigmacenter'}, result: 'result'};
  var ITEM_WORDS = ['item', '항목', '측정항목', 'parameter', 'param', '파라미터', 'para'];
  var LABEL_WORDS = ['date', 'time', 'datetime', '날짜', '일자', '시간', '일시', '측정일', '측정시간', 'lot', 'lotid', 'wafer', 'waferid', 'no', '번호', 'sample', '시료'];
  var DEFAULT_OCAP = {
    OOS: '1. 해당 Lot 즉시 Hold\n2. 재측정으로 측정 오류인지 확인\n3. 설비 · 레시피 · 자재 변경 이력 확인 후 엔지니어에게 보고\n4. 원인 조치 후 Hold 해제 판정, 조치 내용 기록',
    R1: '1. 재측정으로 측정 오류인지 확인\n2. 설비 상태 · 레시피 · 자재 Lot 변경 이력 확인\n3. 엔지니어 보고, 원인과 조치 기록',
    R2: '1. 중심 이동 원인 확인 (자재 Lot, 설비 PM, 레시피 변경)\n2. 엔지니어 보고 후 보정 여부 판단',
    R3: '1. 설비 마모 · 드리프트 확인\n2. 다음 측정값 추이 감시, 필요하면 PM 또는 보정',
    R4: '1. 공정 변동 원인 확인\n2. 엔지니어 보고',
    R5: '1. 공정 변동 원인 확인\n2. 엔지니어 보고',
    R6: '1. 측정기 · 설비를 번갈아 쓰는지 확인 (층별)',
    R7: '1. 관리한계 재계산이 필요한지 검토 (데이터 층별 의심)',
    R8: '1. 서로 다른 조건(설비 · 챔버)이 섞였는지 확인'
  };

  // ---------- settings ----------
  var settings = normalize(load('spc.settings', {}));
  function normalize(settings) {
    settings.rules = Object.assign({}, SPC.DEFAULT_ON, settings.rules);
    settings.n = settings.n || {};
    settings.ocap = Object.assign({}, DEFAULT_OCAP, settings.ocap);
    settings.manual = settings.manual || {};
    if (settings.sound === undefined) settings.sound = true;
    // v1-v3 showed the last 100 points by default; from v4 the whole period is drawn and scrolled sideways (#24).
    if (!settings.v4) { settings.window = 0; settings.v4 = 1; }
    // v8: 2/3 > 2σ and 4/5 > 1σ are off by default (owner, #25: not OCAP / 7 run, only orange dots); turned off once
    // for settings saved by older versions, and can be turned on again in [규칙 · OCAP 설정].
    if (!settings.v8) { settings.rules.R4 = false; settings.rules.R5 = false; settings.v8 = 1; }
    // v11: Trend is 6 points by default (owner, #27). [규칙 · OCAP 설정] of older versions saved every point
    // count, so a stored 7 (the old default) goes; a count changed on purpose stays.
    if (!settings.v11) { if (settings.n.R3 === 7) delete settings.n.R3; settings.v11 = 1; }
    // v13 (owner, #29): XBAR and SIGMA have their own rules. XBAR = OCAP, 7 run; SIGMA = OCAP, 7 run, Trend 6.
    // Older versions shared one set and had Trend on, so XBAR Trend goes off once (it can be turned on again).
    if (!settings.v13) { settings.rules.R3 = false; settings.v13 = 1; }
    settings.sigma = settings.sigma || {};
    settings.sigma.rules = Object.assign({}, SPC.SIGMA_DEFAULT_ON, settings.sigma.rules);
    settings.sigma.n = settings.sigma.n || {};
    // v13 (owner, #29): no auto refresh any more; [새로고침] reads the file again
    delete settings.auto;
    delete settings.pollSec;
    if (!(settings.window >= 0)) settings.window = 0;
    if (!(settings.pitch >= 0)) settings.pitch = 16;
    if (!(settings.subgroup >= 1)) settings.subgroup = 1;
    if (!(settings.baseline >= 0)) settings.baseline = 0;
    return settings;
  }
  var ocapLog = load('spc.ocapLog', {});

  function load(key, def) {
    try { var v = JSON.parse(localStorage.getItem(key)); return v && typeof v === 'object' ? v : def; } catch (e) { return def; }
  }
  function save() {
    try {
      localStorage.setItem('spc.settings', JSON.stringify(settings));
      localStorage.setItem('spc.ocapLog', JSON.stringify(ocapLog));
    } catch (e) { /* private window: settings last until the page closes */ }
  }

  // ---------- state ----------
  var source = null;       // {name, kind: 'handle'|'file'|'demo', handle?, file?, demo?}
  var lastKey = null;      // lastModified:size of the file last read
  var book = null;         // [{name, rows}]
  var table = null;        // {headers, data, roles, sheet}
  var results = [];        // SPC.analyze results, one per item
  var seen = null;         // event keys already shown (null until the first read of a source)
  var newKeys = {};
  var busy = false;
  var lastBuf = null;      // bytes of the file last read (the saved copy is made from them)
  var edits = {};          // 'excelRow:col' -> {row, col, value, orig}: recommended values, only in the copy
  var yellow = {};         // excelRow -> rule ids breaking OCAP / 7 run in the file as read
  var nowFlags = {};       // excelRow -> rule ids breaking them with the edits applied
  var selectedRow = null;  // Excel row picked in the data table or by double-clicking a chart point
  var fixItems = [];       // items (with edits) behind results, for the recommended values
  var delMode = false;     // [삭제 시뮬레이션] on: charts and table show the data with delPlan's rows deleted (#27)
  var delPlan = null;      // {rounds: [[{key: excelRow, rules}]], clean, round: excelRow -> round (1, 2, ...), count}
  var mixPlan = null;      // [최소 행 변경] on (#30): {plan: SPC.minChangePlan result, series, prevEdits}; delMode is on with it
  var fixPlan = null;      // [시뮬레이션 · 행 수정만] on (#31): {prevEdits, made, failed}; the edits are its new values
  var simOpen = false;     // the three [시뮬레이션] buttons are shown (#31)
  var pick = null;         // cells picked in the data table by dragging (#31): {a: [row, col], b: [row, col]} in table.rows / cells

  $('ver').textContent = TITLE.replace(/^SPC Chart HTML\s*/, '');

  // ---------- reading ----------
  function setStatus(text, cls) {
    var s = $('status');
    s.textContent = text;
    s.className = 'status ' + (cls || 'muted');
  }

  function stamp() {
    var d = new Date();
    return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }

  async function openPicked() {
    if (window.showOpenFilePicker) {
      var handles;
      try {
        handles = await window.showOpenFilePicker({
          id: 'spc-excel',
          types: [{description: 'Excel / CSV', accept: {'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx', '.xlsm'], 'application/vnd.oasis.opendocument.spreadsheet': ['.ods'], 'text/csv': ['.csv', '.txt']}}]
        });
      } catch (e) {
        if (e && e.name === 'AbortError') return;
        setStatus('파일을 열지 못했습니다: ' + e.message, 'err');
        return;
      }
      useHandle(handles[0]);
    } else {
      $('fileIn').click();  // no live refresh in browsers without the File System Access API
    }
  }

  function useHandle(handle) {
    source = {name: handle.name, kind: 'handle', handle: handle};
    startSource();
  }

  function startSource() {
    lastKey = null;
    seen = null;
    newKeys = {};
    edits = {};
    selectedRow = null;
    lastBuf = null;
    hideAlarm();
    $('reloadBtn').disabled = false;
    refresh(true);
  }

  async function refresh(force) {
    if (busy || !source) return;
    busy = true;
    try {
      var name = source.name, buf, key;
      if (source.kind === 'demo') {
        key = source.demo.tick();
        if (!force && key === lastKey) return;
        book = source.demo.book();
      } else {
        var file;
        try {
          file = source.kind === 'handle' ? await source.handle.getFile() : source.file;
        } catch (e) {
          // Excel replaces the file while saving; try again on the next tick.
          setStatus(name + ' · 파일을 읽을 수 없음 (저장 중이거나 권한 없음) · ' + stamp(), 'warn');
          return;
        }
        key = file.lastModified + ':' + file.size;
        if (!force && key === lastKey) return;
        buf = await file.arrayBuffer();
        try {
          book = window.XLSXLite.read(name, buf);
          lastBuf = buf;
        } catch (e) {
          setStatus(name + ' · ' + e.message + ' · ' + stamp(), 'err');
          return;  // keep the last good charts; lastKey unchanged so the next tick retries
        }
      }
      lastKey = key;
      buildTable();
      analyzeAll();
      render();
      var live = source.kind === 'file' ? ' · [새로고침]으로 다시 읽을 수 없는 방식으로 열림 (다시 열기로 갱신)' : '';
      setStatus(name + ' · 읽은 시각 ' + stamp() + live, source.kind === 'file' ? 'warn' : 'muted');
    } finally {
      busy = false;
    }
  }

  // ---------- table: header, columns, roles ----------
  function norm(s) { return String(s).toLowerCase().replace(/[\s_\-.()\[\]]/g, ''); }


  function colName(i) {
    var s = '';
    for (i++; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + (i - 1) % 26) + s;
    return s;
  }

  function toNum(v) {
    if (typeof v === 'number') return isFinite(v) ? v : null;
    if (typeof v === 'string' && /^\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*$/.test(v)) return +v;
    return null;
  }

  function buildTable() {
    dropSim();
    var sheetName = settings.sheet;
    var sheet = book.filter(function (s) { return s.name === sheetName; })[0];
    if (!sheet) {
      // First sheet that has numbers.
      sheet = book.filter(function (s) { return s.rows.some(function (r) { return r.some(function (v) { return typeof v === 'number'; }); }); })[0] || book[0];
    }
    var rows = sheet ? sheet.rows : [];
    var h = 0;
    while (h < rows.length && rows[h].filter(function (v) { return v !== null && v !== undefined; }).length < 2) h++;
    var width = 0;
    rows.forEach(function (r) { width = Math.max(width, r.length); });
    var headers = [], used = {};
    for (var c = 0; c < width; c++) {
      var t = rows[h] && rows[h][c] !== null && rows[h][c] !== undefined ? String(rows[h][c]).trim() : '';
      if (t === '' || used[t]) t = (t || '열') + ' ' + colName(c);
      used[t] = 1;
      headers.push(t);
    }
    var data = [];
    for (var r = h + 1; r < rows.length; r++) {
      var row = rows[r];
      if (!row.some(function (v) { return v !== null && v !== undefined; })) continue;
      data.push({excelRow: r + 1, cells: row});
    }
    var kinds = headers.map(function (_, i) {
      var num = 0, text = 0, date = 0;
      data.forEach(function (d) {
        var v = d.cells[i];
        if (v instanceof Date) date++;
        else if (toNum(v) !== null) num++;
        else if (v !== null && v !== undefined) text++;
      });
      return num > 0 && num >= text + date ? 'num' : (date + text > 0 ? 'text' : 'empty');
    });
    // Limit columns: the first word of a role wins (EXT_MV_UCL before UCL), columns with numbers only.
    var roles = {}, normed = headers.map(norm);
    ROLES.forEach(function (r) {
      ROLE_WORDS[r].some(function (w) {
        var i = normed.indexOf(w);
        if (i >= 0 && kinds[i] === 'num') { roles[r] = headers[i]; return true; }
        return false;
      });
    });
    var spcForm = normed.indexOf(SPC_FORMAT.value) >= 0 && normed.indexOf(SPC_FORMAT.needs) >= 0 && kinds[normed.indexOf(SPC_FORMAT.value)] === 'num';
    table = {sheet: sheet ? sheet.name : '', sheets: book.map(function (s) { return s.name; }), headers: headers, data: data, kinds: kinds, roles: roles,
      spcForm: spcForm, sysCol: spcForm ? resultCol(normed, data) : -1, path: sheet && sheet.path, rows: rows, head: h, fmts: sheet && sheet.fmts || [], hidden: sheet && sheet.hidden || {}};

    var cols = settings.cols || {};
    var has = function (n) { return headers.indexOf(n) >= 0; };
    var roleCols = ROLES.map(function (r) { return roles[r]; });
    var item = cols.item === '' || has(cols.item) ? cols.item : headers.filter(function (n, i) { return kinds[i] === 'text' && ITEM_WORDS.indexOf(norm(n)) >= 0; })[0] || '';
    // A label picked in [X축] stays; otherwise it is chosen again (v2 saved LOT_ID for the SPC system format).
    var label = cols.labelPicked && (cols.label === '' || has(cols.label)) ? cols.label
      : (spcForm && SPC_FORMAT.label.map(function (w) { var i = normed.indexOf(w); return i >= 0 && kinds[i] !== 'empty' ? headers[i] : ''; }).filter(Boolean)[0])
      || headers.filter(function (n, i) { return n !== item && kinds[i] !== 'empty' && LABEL_WORDS.indexOf(norm(n)) >= 0; })[0]
      || headers.filter(function (n, i) { return n !== item && kinds[i] === 'text'; })[0] || '';
    var numeric = headers.filter(function (n, i) { return kinds[i] === 'num' && roleCols.indexOf(n) < 0 && n !== label && n !== item; });
    var values = (cols.values || []).filter(function (n) { return numeric.indexOf(n) >= 0; });
    if (!values.length || cols.sig !== numeric.join('|')) values = spcForm ? [headers[normed.indexOf(SPC_FORMAT.value)]] : numeric.slice();
    table.label = label;
    table.item = item;
    table.numeric = numeric;
    table.values = values;
    settings.sheet = table.sheet;
    settings.cols = {label: label, labelPicked: !!cols.labelPicked, item: item, values: values, sig: numeric.join('|')};
    save();

    // An edit stays only while the file still has the value it replaced (the file may have been saved meanwhile).
    var byRow = {};
    data.forEach(function (d) { byRow[d.excelRow] = d.cells; });
    Object.keys(edits).forEach(function (k) {
      var e = edits[k], cells = byRow[e.row];
      if (!cells || !same(cells[e.col], e.orig)) delete edits[k];
    });
  }

  function same(a, b) {
    if (a instanceof Date && b instanceof Date) return a.getTime() === b.getTime();
    return a === b || (a === undefined && b === null) || (a === null && b === undefined);
  }

  function cell(d, col, withEdits) {
    var e = withEdits && edits[d.excelRow + ':' + col];
    return e ? e.value : d.cells[col];
  }

  function fmtLabel(v, excelRow) {
    if (v instanceof Date) {
      var s = v.getFullYear() + '-' + pad(v.getMonth() + 1) + '-' + pad(v.getDate());
      if (v.getHours() || v.getMinutes() || v.getSeconds()) s += ' ' + pad(v.getHours()) + ':' + pad(v.getMinutes());
      return s;
    }
    if (v === null || v === undefined || v === '') return excelRow + '행';
    return String(v);
  }

  // keepAll: every row, also the ones [삭제 시뮬레이션] deletes (the file as read).
  function items(withEdits, keepAll) {
    var t = table, idx = function (n) { return t.headers.indexOf(n); };
    var gone = delPlan && !keepAll ? delPlan.round : {};
    var li = idx(t.label), ii = idx(t.item), groups = [], byName = {};
    t.data.forEach(function (d) {
      var g = ii >= 0 ? d.cells[ii] : null;
      g = g === null || g === undefined ? (ii >= 0 ? '(빈 항목)' : '') : (g instanceof Date ? fmtLabel(g) : String(g));
      if (!byName[g]) { byName[g] = []; groups.push(g); }
      byName[g].push(d);
    });
    var list = [];
    groups.forEach(function (g) {
      t.values.forEach(function (vn) {
        var vi = idx(vn), rows = byName[g];
        var name = g === '' ? vn : (t.values.length > 1 ? g + ' · ' + vn : g);
        var cols = {};
        ROLES.forEach(function (r) {
          if (t.roles[r]) { var ri = idx(t.roles[r]); cols[r] = rows.map(function (d) { return toNum(d.cells[ri]); }); }
        });
        var vals = rows.map(function (d) { return gone[d.excelRow] ? null : toNum(cell(d, vi, withEdits)); });
        if (!vals.some(function (v) { return v !== null; })) return;
        var sigma = null, lots = null, sys = null;
        if (t.spcForm && norm(vn) === SPC_FORMAT.value) {
          var col = function (w) {
            var i = t.headers.map(norm).indexOf(w);
            return i < 0 ? null : rows.map(function (d) { return toNum(d.cells[i]); });
          };
          // EXT_SIGMA takes recommended values too (#25); a row without EXT_MV has no SIGMA point either.
          var si = t.headers.map(norm).indexOf(SPC_FORMAT.sigma.value);
          sigma = si < 0 ? null : {col: si, values: rows.map(function (d, k) { return vals[k] === null ? null : toNum(cell(d, si, withEdits)); }),
            UCL: col(SPC_FORMAT.sigma.UCL), LCL: col(SPC_FORMAT.sigma.LCL), CL: col(SPC_FORMAT.sigma.CL)};
          if (sigma && !sigma.values.some(function (v) { return v !== null; })) sigma = null;
          var lt = t.headers.map(norm).indexOf(SPC_FORMAT.lot);
          if (lt >= 0) lots = rows.map(function (d) { return cellText(d.cells[lt]); });
          var rc = t.headers.map(norm).indexOf(SPC_FORMAT.result);
          if (rc >= 0) sys = rows.map(function (d) { return cellText(d.cells[rc]).trim(); });
        }
        list.push({
          spcForm: !!t.spcForm, sigma: sigma, lots: lots, sys: sys,
          name: name, values: vals, cols: cols, col: vi, excelRows: rows.map(function (d) { return d.excelRow; }),
          labels: rows.map(function (d) { return li >= 0 ? fmtLabel(d.cells[li], d.excelRow) : d.excelRow + '행'; })
        });
      });
    });
    return list;
  }

  // SPC system format: the XBAR chart too takes its CL only from the file (EXT_MV_CENTER) or a typed one,
  // without it no run / trend (owner, #34: "XBAR 차트도 똑같이"). Other sheets keep the computed CL of I-MR / Xbar-R.
  function optsFor(name) {
    return {subgroup: settings.subgroup, baseline: settings.baseline, rules: settings.rules, n: settings.n, manual: settings.manual[name] || {},
      fileCl: !!(table && table.spcForm)};
  }
  function fixRules() { return SPC.FIX_RULES.filter(function (id) { return settings.rules[id]; }); }

  // SIGMA chart rules (#25): OCAP = outside EXT_SIGMA_UCL/LCL, 7 run = run / trend around EXT_SIGMA_CENTER.
  // Without EXT_SIGMA_CENTER numbers no run / trend at all, like the SPC system (#33, fileCl).
  // No spec limits for a sigma. Their ids carry an S (SR1, SR2, SR3) next to the XBAR ones.
  var SIGMA_RULES = ['R1', 'R2', 'R3'];
  function sigmaRules() { return SIGMA_RULES.filter(function (id) { return settings.sigma.rules[id]; }); }
  function sigmaOpts() {
    var on = {};
    sigmaRules().forEach(function (id) { on[id] = true; });
    return {subgroup: 1, baseline: 0, rules: on, n: settings.sigma.n, manual: {}, min: 0, fileCl: true};
  }
  // The SIGMA series as an item of its own, row for row with its XBAR item (same indexes).
  function sigmaItem(it) {
    return {name: it.name + ' · SIGMA', values: it.sigma.values, labels: it.labels, cols: {UCL: it.sigma.UCL, LCL: it.sigma.LCL, CL: it.sigma.CL}};
  }
  function isSigmaRule(id) { return /^SR\d$/.test(id); }
  function baseRule(id) { return isSigmaRule(id) ? id.slice(1) : id; }

  // ---------- SPC system judgment (#34) ----------
  // The SPC system export carries the system's own verdict per row in RESULT: 7R(S) = 7 run on the SIGMA chart,
  // 6T(S) = 6 trend, 7R(X) / O(X) = run / OCAP on the XBAR chart, CutOff = new limits (no alarm). The system judges
  // each row when it comes in, with rows the export no longer shows (EXT_MS / EXT_MA tell the point before it),
  // so the program cannot compute the same from the rows; the file's RESULT is the judgment shown.
  function sysCodes(text) {
    return String(text || '').split(/[\s,;/]+/).filter(function (c) { return /^\d*[A-Za-z]+\((X|S)\)$/i.test(c); });
  }
  function sysRule(code) {
    var m = /^(\d*)([A-Za-z]+)\((X|S)\)$/i.exec(code), k = m[2].toUpperCase().charAt(0);
    var id = k === 'R' ? 'R2' : k === 'T' ? 'R3' : k === 'O' ? 'R1' : 'R1';
    return (m[3].toUpperCase() === 'S' ? 'S' : '') + id;
  }
  // RESULT used only when the system wrote something in it (an alarm or CutOff); an empty column = program judgment
  function resultCol(normed, data) {
    var i = normed.indexOf(SPC_FORMAT.result);
    return i >= 0 && data.some(function (d) { return d.cells[i] !== null && d.cells[i] !== undefined && String(d.cells[i]).trim() !== ''; }) ? i : -1;
  }
  function useSystem() { return !!(table && table.sysCol >= 0 && settings.sysJudge !== false); }
  function systemJudge(res) {
    if (!res.sys || !useSystem()) return;
    var x = {}, sg = {}, codes = {};
    res.points.forEach(function (p, i) {
      p.rows.forEach(function (k) {
        sysCodes(res.sys[k]).forEach(function (c) {
          var id = sysRule(c), to = id.charAt(0) === 'S' ? sg : x;
          to[id] = to[id] || [];
          if (to[id].indexOf(i) < 0) to[id].push(i);
          (codes[i] = codes[i] || []).push(c);
        });
      });
    });
    res.calc = {flags: res.flags, sigmaFlags: res.sigmaFlags, events: res.events};
    res.system = true;
    res.sysByPoint = codes;
    res.flags = x;
    res.sigmaFlags = sg;
    res.rangeFlags = sg.SR1 || [];
    var evs = SPC.events(x, res.points);
    if (res.sigma) evs = evs.concat(SPC.events(sg, res.points.map(function (p, i) { return {label: p.label, value: res.sigma.values[i]}; })));
    evs.forEach(function (ev) { ev.code = (codes[ev.start] || []).filter(function (c) { return sysRule(c) === ev.rule; })[0] || ''; });
    res.events = evs.sort(function (a, b) { return a.start - b.start; });
  }

  // excelRow -> rule ids (OCAP / 7 run) of the points on that row; the system's codes (SYS:7R(S)) for a system judgment
  function rowFlags(list) {
    var out = {}, rules = fixRules();
    list.forEach(function (res) {
      if (res.system) {
        Object.keys(res.sysByPoint).forEach(function (i) {
          res.points[i].rows.forEach(function (k) {
            var row = res.excelRows[k];
            out[row] = out[row] || [];
            res.sysByPoint[i].forEach(function (c) { if (out[row].indexOf('SYS:' + c) < 0) out[row].push('SYS:' + c); });
          });
        });
        return;
      }
      var mark = function (id) {
        return function (i) {
          res.points[i].rows.forEach(function (k) {
            var row = res.excelRows[k];
            out[row] = out[row] || [];
            if (out[row].indexOf(id) < 0) out[row].push(id);
          });
        };
      };
      rules.forEach(function (id) { (res.flags[id] || []).forEach(mark(id)); });
      Object.keys(res.sigmaFlags || {}).forEach(function (id) { res.sigmaFlags[id].forEach(mark(id)); });
    });
    return out;
  }

  // quiet: the values changed by recommended values, not by a save of the file (no alarm).
  function analyzeAll(quiet) {
    var run = function (list) {
      return list.map(function (it) {
        var res = SPC.analyze(it, optsFor(it.name));
        res.excelRows = it.excelRows;
        res.col = it.col;
        res.spcForm = it.spcForm;
        res.lots = it.lots;
        res.sys = it.sys;
        if (it.sigma && res.size === 1) sigmaChart(res, it);
        return res;
      });
    };
    var asRead = function (list) { list.forEach(systemJudge); return list; };
    delPlan = delMode ? (mixPlan ? mixDelPlan() : planDeletes()) : null;
    // The deletion is judged on the file's own values, so its charts leave the recommended values out
    // ([최소 행 변경] keeps them: its new values are the edits).
    fixItems = items(!delMode || !!mixPlan);
    results = run(fixItems);
    // The file as read is judged like the SPC system: its RESULT column (#34). Edits and simulations are
    // judged by the program (the system judges a row once, when it comes in).
    var plain = !Object.keys(edits).length && !delPlan;
    if (plain) asRead(results);
    yellow = rowFlags(plain ? results : asRead(run(items(false, true))));
    nowFlags = rowFlags(results);
    // New out-of-control events since the last read raise the alarm (not on the first read of a file).
    var keys = {}, fresh = [];
    results.forEach(function (res) {
      res.events.forEach(function (ev) {
        ev.item = res.name;
        ev.key = eventKey(res, ev);
        keys[ev.key] = 1;
        if (seen && !seen[ev.key]) fresh.push(ev);
      });
    });
    if (seen && fresh.length && !quiet) {
      fresh.forEach(function (ev) { newKeys[ev.key] = 1; });
      showAlarm(fresh);
    }
    seen = keys;
  }

  // SIGMA chart of the SPC system format: EXT_SIGMA per point with its own UCL/LCL columns. Since #25 it is
  // judged like the XBAR chart: OCAP (SR1, outside UCL/LCL) and 7 run (SR2 run, SR3 trend) rows go yellow,
  // get recommended values and are listed as events. Indexes in res.sigmaFlags are XBAR point indexes.
  function sigmaChart(res, it) {
    var sig = it.sigma;
    var at = function (a) { return a ? SPC.fillColumn(res.points.map(function (p) { return a[p.row]; })) : null; };
    var s = {name: 'SIGMA', col: sig.col, values: res.points.map(function (p) { return sig.values[p.row]; }), ucl: at(sig.UCL), lcl: at(sig.LCL), cl: at(sig.CL)};
    res.sigma = s;
    var piOfRow = {};
    res.points.forEach(function (p, i) { piOfRow[p.row] = i; });
    var sres = SPC.analyze(sigmaItem(it), sigmaOpts()), flags = {};
    Object.keys(sres.flags).forEach(function (id) {
      flags['S' + id] = sres.flags[id].map(function (k) { return piOfRow[sres.points[k].row]; }).filter(function (i) { return i !== undefined; });
    });
    res.sigmaFlags = flags;
    res.rangeFlags = flags.SR1 || [];
    var evs = SPC.events(flags, res.points.map(function (p, i) { return {label: p.label, value: s.values[i]}; }));
    res.events = res.events.concat(evs).sort(function (a, b) { return a.start - b.start; });
  }

  // [삭제 시뮬레이션] (#27): which rows to delete so that neither the XBAR nor the SIGMA chart has OCAP / 7 run.
  // One row at a time, oldest first, judged again after each (SPC.deletePlan): round 1 = yellow rows still
  // breaking a rule when their turn comes, round 2 = rows that only break one after that, ... File values, no edits.
  function planSeries() {
    var series = [], sub = settings.subgroup <= 1;
    items(false, true).forEach(function (it) {
      series.push({item: it, opts: optsFor(it.name), rules: fixRules(), keys: it.excelRows, tag: '', col: it.col});
      if (it.sigma && sub) series.push({item: sigmaItem(it), opts: sigmaOpts(), rules: sigmaRules(), keys: it.excelRows, tag: 'S', col: it.sigma.col});
    });
    return series;
  }
  function planDeletes() {
    var plan = SPC.deletePlan(planSeries()), round = {}, count = 0;
    plan.rounds.forEach(function (list, r) { list.forEach(function (x) { round[x.key] = r + 1; count++; }); });
    plan.round = round;
    plan.count = count;
    return plan;
  }

  // [최소 행 변경] (#30) in the shape of a delete plan: its deletions are one round, its new values are the edits.
  function mixDelPlan() {
    var p = mixPlan.plan, round = {};
    p.deletes.forEach(function (x) { round[x.key] = 1; });
    return {rounds: [p.deletes], clean: p.clean, round: round, count: p.deletes.length, mix: p};
  }

  // [최소 행 변경] (#30): fewest rows to delete or give a new value so that neither XBAR nor SIGMA has OCAP / 7 run
  // (SPC.minChangePlan, from the file's own values). The new values replace the edits (red cells, saved in the
  // copy), the deletions show like [삭제 시뮬레이션] and go to the OCAP 삭제 양식. Off again = the edits from before.
  function toggleMix() {
    if (!table || settings.subgroup > 1) { analyzeAll(true); render(); return; }
    setStatus('최소 행 변경 계산 중… (행이 많으면 몇 초 걸립니다)', 'muted');
    $('mixBtn').disabled = true;
    setTimeout(function () {
      var series = planSeries(), plan;
      try {
        plan = SPC.minChangePlan(series);
      } catch (e) {
        analyzeAll(true);
        render();
        setStatus('최소 행 변경을 계산하지 못했습니다: ' + e.message, 'err');
        return;
      }
      mixPlan = {plan: plan, series: series, prevEdits: edits};
      edits = {};
      plan.changes.forEach(function (c) { setEdit(c.key, series[c.series].col, c.value); });
      delMode = true;
      analyzeAll(true);
      render();
      setStatus(plan.rows ? '시뮬레이션 · 최소 행 변경: ' + plan.rows + '행 (삭제 ' + plan.deletes.length + ' · 값 수정 ' + mixRows(plan) + ') · 다시 누르면 원래대로' : '시뮬레이션 · 최소 행 변경: 바꿀 행 없음',
        plan.clean ? 'muted' : 'warn');
      $('delBox').scrollIntoView({block: 'nearest'});
    }, 30);
  }
  function mixRows(p) {
    var rows = {};
    p.changes.forEach(function (c) { rows[c.key] = 1; });
    return Object.keys(rows).length;
  }
  // A new file read, sheet, columns or rules make the plan stale: its edits stay as plain edits.
  function dropSim() {
    if (mixPlan) delMode = false;
    mixPlan = null;
    fixPlan = null;
  }

  // [시뮬레이션] (#31): one of three modes at a time, each from the file's own values and each saved in the company's
  // form: 'del' 행 삭제만 ([삭제 시뮬레이션], OCAP 삭제 양식), 'fix' 행 수정만 ([전체 일괄 추천값 입력], RAW_DATA
  // 수정 양식), 'mix' 최소 행 변경 (both forms). Off again = the data and the edits from before.
  function simMode() { return mixPlan ? 'mix' : fixPlan ? 'fix' : delMode ? 'del' : null; }
  function simOff() {
    var was = simMode();
    if (mixPlan) edits = mixPlan.prevEdits;
    if (fixPlan) edits = fixPlan.prevEdits;
    mixPlan = null;
    fixPlan = null;
    delMode = false;
    return was;
  }
  var SIM_NAME = {del: '행 삭제만', fix: '행 수정만', mix: '최소 행 변경 (삭제+수정)'};
  function setSim(mode) {
    var was = simOff();
    if (!table || was === mode) {
      analyzeAll(true);
      render();
      if (was) setStatus('시뮬레이션(' + SIM_NAME[was] + ')을 껐습니다 (원래대로)', 'muted');
      return;
    }
    if (mode === 'del') toggleDelete();
    else if (mode === 'fix') toggleFix();
    else toggleMix();
  }

  // point index -> SIGMA rule ids
  function sigmaFlagMap(r) {
    var m = {};
    Object.keys(r.sigmaFlags || {}).forEach(function (id) { r.sigmaFlags[id].forEach(function (i) { (m[i] = m[i] || []).push(id); }); });
    return m;
  }

  function eventKey(res, ev) { return res.name + '|' + ev.rule + '|' + ev.label + '|' + res.size; }

  // ---------- alarm ----------
  var alarmEvents = [];
  function showAlarm(fresh) {
    alarmEvents = fresh;
    var first = fresh[0], more = fresh.length > 1 ? ' 외 ' + (fresh.length - 1) + '건' : '';
    $('alarmText').textContent = '⚠ 새 이상 ' + fresh.length + '건: ' + first.item + ' — ' + ruleName(first.rule) + ' (' + first.label + ')' + more;
    var a = $('alarm');
    a.classList.add('hidden');
    void a.offsetWidth;  // restart the blink
    a.classList.remove('hidden');
    if (settings.sound) beep();
  }
  function hideAlarm() { $('alarm').classList.add('hidden'); }

  var audio = null;
  function beep() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.25].forEach(function (t) {
        var o = audio.createOscillator(), g = audio.createGain();
        o.frequency.value = 880;
        g.gain.value = 0.08;
        o.connect(g);
        g.connect(audio.destination);
        o.start(audio.currentTime + t);
        o.stop(audio.currentTime + t + 0.15);
      });
    } catch (e) { /* no sound device */ }
  }

  // point count of a rule; SIGMA rules (SR*) have their own counts (#29)
  function ruleN(id) {
    var base = baseRule(id), r = SPC.RULES.filter(function (x) { return x.id === base; })[0];
    return r && r.n ? (isSigmaRule(id) ? settings.sigma.n : settings.n)[base] || r.n : 0;
  }
  function ruleName(id) {
    var r = SPC.RULES.filter(function (x) { return x.id === baseRule(id); })[0];
    if (!r) return id;
    return (isSigmaRule(id) ? 'SIGMA ' : '') + r.name + (r.n ? ' (' + ruleN(id) + '점)' : '');
  }
  function ruleDesc(id) {
    var r = SPC.RULES.filter(function (x) { return x.id === baseRule(id); })[0];
    return r ? r.desc.replace('N점', ruleN(id) + '점') : '';
  }

  // ---------- rendering ----------
  function fmt(v) {
    if (v === null || v === undefined || !isFinite(v)) return '-';
    var a = Math.abs(v);
    if (a !== 0 && (a >= 1e6 || a < 1e-3)) return v.toExponential(3);
    return String(+v.toFixed(a >= 100 ? 2 : a >= 1 ? 4 : 5));
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; });
  }
  function opt(value, text, sel) { return '<option value="' + esc(value) + '"' + (sel ? ' selected' : '') + '>' + esc(text) + '</option>'; }

  function renderControls() {
    var t = table;
    $('controls').classList.remove('hidden');
    $('sheetSel').innerHTML = t.sheets.map(function (s) { return opt(s, s, s === t.sheet); }).join('');
    $('labelSel').innerHTML = opt('', '(행 번호)', !t.label) + t.headers.map(function (h) { return opt(h, h, h === t.label); }).join('');
    $('itemSel').innerHTML = opt('', '(없음)', !t.item) + t.headers.filter(function (h, i) { return t.kinds[i] === 'text'; }).map(function (h) { return opt(h, h, h === t.item); }).join('');
    // folded by default (#31): the summary line says which columns are charted
    $('valueBox').innerHTML = t.numeric.map(function (h) {
      return '<label class="chk"><input type="checkbox" value="' + esc(h) + '"' + (t.values.indexOf(h) >= 0 ? ' checked' : '') + '> ' + esc(h) + '</label>';
    }).join('');
    renderValueSum();
    $('sizeIn').value = settings.subgroup;
    $('baseIn').value = settings.baseline;
    $('winIn').value = settings.window;
    $('pitchSel').value = String(settings.pitch);
    var view = $('viewSel').value;
    $('viewSel').innerHTML = opt('', '전체 항목', !view) + results.map(function (r) { return opt(r.name, r.name, r.name === view); }).join('');
  }

  function statusOf(res) {
    var last = res.points.length - 1;
    var lastFlags = Object.keys(res.flags).filter(function (id) { return res.flags[id].indexOf(last) >= 0; });
    if (lastFlags.indexOf('OOS') >= 0) return {cls: 'bad', text: '규격 이탈'};
    if (lastFlags.length || res.rangeFlags.indexOf(last) >= 0 || sigmaFlagMap(res)[last]) return {cls: 'warn', text: '관리 이탈'};
    // a fixed period (#24): an alarm anywhere in it shows, not only on the last point (#34 "알림조차 안떠")
    if (res.events.length) return {cls: 'warn', text: (res.system ? '시스템 경고 ' : '이상 ') + res.events.length + '건'};
    return {cls: 'ok', text: '정상'};
  }

  function openCount(res) {
    return res.events.filter(function (ev) { return !(ocapLog[ev.key] && ocapLog[ev.key].done); }).length;
  }

  // Which file is on screen (#32): the file name (and the sheet when the file has several) at the top
  function showCurrent() {
    var el = $('curFile');
    if (!source) { el.classList.add('hidden'); return; }
    var sheet = table && table.sheets && table.sheets.length > 1 ? ' · 시트 ' + table.sheet : '';
    el.textContent = '보고 있는 파일: ' + source.name + sheet;
    el.title = el.textContent;
    el.classList.remove('hidden');
  }

  function render() {
    $('empty').classList.add('hidden');
    showCurrent();
    renderControls();
    var view = $('viewSel').value, shown = results.filter(function (r) { return !view || r.name === view; });

    // Summary
    var s = '<table class="grid"><tr><th>항목</th><th>상태</th><th>점 수</th><th>마지막 값</th><th>평균</th><th>σ(within)</th><th>Cp</th><th>Cpk</th><th>Ppk</th><th>USL</th><th>LSL</th><th>UCL</th><th>LCL</th><th>이상(미조치)</th></tr>';
    results.forEach(function (r, i) {
      var st = statusOf(r), L = r.limits, n = r.points.length;
      var lv = function (k) { return L[k].values && n ? fmt(L[k].values[n - 1]) : '-'; };
      s += '<tr class="click" data-i="' + i + '"><td>' + esc(r.name) + '</td><td><span class="badge ' + st.cls + '">' + st.text + '</span></td><td>' + n + '</td><td>' + fmt(r.x[n - 1]) +
        '</td><td>' + fmt(r.stats.mean) + '</td><td>' + fmt(r.stats.sigmaW) + '</td><td>' + fmt(r.stats.cp) + '</td><td>' + fmt(r.stats.cpk) + '</td><td>' + fmt(r.stats.ppk) +
        '</td><td>' + lv('USL') + '</td><td>' + lv('LSL') + '</td><td>' + lv('UCL') + '</td><td>' + lv('LCL') + '</td><td>' + r.events.length + ' (' + openCount(r) + ')</td></tr>';
    });
    s += '</table>';
    if (!results.length) s = '<p class="muted">차트로 그릴 숫자 열이 없습니다. 첫 줄은 제목, 그 아래에 숫자 데이터가 있는지 확인해 주세요.</p>';
    $('summary').innerHTML = s;
    $('summary').classList.remove('hidden');

    // Cards: reuse canvases so live redraws do not flicker.
    var box = $('cards'), want = shown.map(function (r) { return r.name; });
    Array.prototype.slice.call(box.children).forEach(function (el) { if (want.indexOf(el.dataset.name) < 0) el.remove(); });
    shown.forEach(function (r, k) {
      var card = box.querySelector('[data-name="' + CSS.escape(r.name) + '"]');
      if (!card) {
        card = document.createElement('div');
        card.className = 'item-card';
        card.dataset.name = r.name;
        card.innerHTML = '<div class="ihead"><b></b><span class="badge"></span><span class="istats"></span><span class="spacer"></span><button class="ghost small lim-btn">한계 설정</button></div>' +
          '<div class="xscroll"><div class="xinner"><canvas class="cx"></canvas><canvas class="cr"></canvas></div></div><canvas class="ch"></canvas><div class="note"></div>';
        card.querySelector('.lim-btn').onclick = function () { limitsDialog(card.dataset.name); };
        card.querySelector('.xscroll').addEventListener('scroll', function () { queueCard(card); }, {passive: true});
      }
      if (box.children[k] !== card) box.insertBefore(card, box.children[k] || null);
      card.classList.toggle('spc', !!r.sigma);
      var st = statusOf(r);
      card.querySelector('b').textContent = r.name;
      var b = card.querySelector('.badge');
      b.className = 'badge ' + st.cls;
      b.textContent = st.text;
      card.querySelector('.istats').textContent = (r.sigma ? 'XBAR · SIGMA' : r.size > 1 ? 'Xbar-R (n=' + r.size + ')' : 'I-MR') + ' · 점 ' + r.points.length + ' · 평균 ' + fmt(r.stats.mean) +
        ' · σ ' + fmt(r.stats.sigmaW) + ' · Cpk ' + fmt(r.stats.cpk) + ' · 이상 ' + r.events.length + '건';
      var L = r.limits;
      card.querySelector('.note').textContent = '한계 출처: ' + ROLES.map(function (k2) { return k2 + ' ' + L[k2].source; }).join(' · ') +
        (r.stats.baseline < r.points.length ? ' · 관리한계는 처음 ' + r.stats.baseline + '점으로 계산' : '');
      card._res = r;
    });
    drawAll();
    renderData();
    renderEvents();
  }

  // ---------- data table: yellow = OCAP / 7 run rows, red = recommended values ----------
  function cellText(v) {
    if (v instanceof Date) {
      v = new Date(Math.round(v.getTime() / 1000) * 1000);  // Excel shows 33.640 s as 34 s
      return v.getFullYear() + '-' + pad(v.getMonth() + 1) + '-' + pad(v.getDate()) + ' ' + pad(v.getHours()) + ':' + pad(v.getMinutes()) + ':' + pad(v.getSeconds());
    }
    return v === null || v === undefined ? '' : String(v);
  }

  // A cell as Excel shows it with its number format (#34: "엑셀 데이터랑 표가 일치하지 않음"): fixed decimals
  // (###0.0000 -> 64.9600), %, thousands, dates; the value itself (and every calculation) is unchanged.
  function excelText(v, code) {
    if (!code || typeof v !== 'number' || !isFinite(v)) {
      if (v instanceof Date && code && !/s/i.test(code.replace(/"[^"]*"/g, ''))) {
        var t = cellText(new Date(Math.floor(v.getTime() / 60000) * 60000));  // h:mm drops the seconds like Excel
        return /h/i.test(code) ? t.slice(0, 16) : t.slice(0, 10);
      }
      return cellText(v);
    }
    var secs = code.split(';'), sec = v < 0 && secs[1] ? secs[1] : (v === 0 && secs[2] ? secs[2] : secs[0]);
    var plain = sec.replace(/"[^"]*"/g, '').replace(/\[[^\]]*\]/g, '').replace(/\\./g, '').replace(/_./g, '');
    if (/general/i.test(plain) || plain.indexOf('@') >= 0 || !/[0#?]/.test(plain)) return cellText(v);
    var x = Math.abs(v), pct = plain.indexOf('%') >= 0, out;
    if (pct) x *= 100;
    var dec = (plain.match(/\.([0#?]*)/) || ['', ''])[1], min = (dec.match(/0/g) || []).length;
    if (/E[+-]/i.test(plain)) out = x.toExponential(dec.length).replace('e', 'E').replace(/E(\d)/, 'E+$1');
    else {
      out = (+(Math.round(+(x + 'e' + dec.length)) + 'e-' + dec.length)).toFixed(dec.length);  // 3.7125 -> 3.713 like Excel, not 3.712
      if (dec.length > min) out = out.replace(new RegExp('0{0,' + (dec.length - min) + '}$'), '').replace(/\.$/, '');
      if (/[0#?],[0#?]/.test(plain)) out = out.replace(/^(\d+)/, function (m) { return m.replace(/\B(?=(\d{3})+(?!\d))/g, ','); });
    }
    var neg = v < 0 && (!secs[1] || /-/.test(plain)) && +out.replace(/[^\d.E+-]/g, '') !== 0;
    return (neg ? '-' : '') + out + (pct ? '%' : '');
  }
  function fmtCode(d, c) {
    var f = table.fmts[d.excelRow - 1];
    return f && f[c] || null;
  }

  function renderValueSum() {
    var t = table;
    $('sysJudgeBox').classList.toggle('hidden', !(t.sysCol >= 0));
    $('sysJudge').checked = settings.sysJudge !== false;
    $('valueSum').innerHTML = '<b>' + esc(t.values.join(', ') || '(없음)') + '</b> <span class="muted small">(' + t.values.length + ' / ' + t.numeric.length + '개 · 눌러서 ' +
      ($('valueFold').open ? '접기' : '펼치기') + ')</span>' + (t.spcForm ? ' <span class="badge ok">SPC 시스템 양식</span>' : '') +
      (Object.keys(t.roles).length ? ' <span class="muted small">한계 열: ' + esc(ROLES.filter(function (r) { return t.roles[r]; }).map(function (r) { return r + '=' + t.roles[r]; }).join(', ')) + '</span>' : '');
  }
  function shortRule(id) {
    if (/^SYS:/.test(id)) return '시스템 ' + id.slice(4);
    return {OOS: '규격 이탈', R1: '관리한계 이탈', SR1: 'SIGMA 관리한계 이탈'}[id] || ruleName(id);
  }

  function renderData() {
    var t = table, box = $('dataBox');
    box.classList.toggle('hidden', !t || !t.data.length);
    if (!t) return;
    var only = $('flagOnly').checked;
    // The charted value columns are repeated after 판정 so a changed value shows without scrolling right.
    var vcols = t.values.map(function (n) { return t.headers.indexOf(n); });
    if (t.spcForm) {  // EXT_SIGMA gets recommended values too (#25)
      var si = t.headers.map(norm).indexOf(SPC_FORMAT.sigma.value);
      if (si >= 0 && vcols.indexOf(si) < 0 && t.values.some(function (n) { return norm(n) === SPC_FORMAT.value; })) vcols.push(si);
    }
    var td = function (d, c) {
      var e = edits[d.excelRow + ':' + c], f = fmtCode(d, c);
      return e ? '<td class="fixed" title="원래 값 ' + esc(excelText(e.orig, f)) + '">' + esc(excelText(e.value, f)) + '</td>' : '<td>' + esc(excelText(d.cells[c], f)) + '</td>';
    };
    // columns hidden in Excel stay hidden here too (#34)
    var shown = t.headers.map(function (_, c) { return c; }).filter(function (c) { return !t.hidden[c]; });
    var h = '<thead><tr><th class="rn">행</th><th class="l">판정</th>' + vcols.map(function (c) { return '<th class="vcol">' + esc(t.headers[c]) + '</th>'; }).join('') +
      '<th class="gap"></th>' + shown.map(function (c0) {
      var n = t.headers[c0], c = t.values.indexOf(n) >= 0 ? ' class="vcol"' : '';
      return '<th' + c + '>' + esc(n) + '</th>';
    }).join('') + '</tr></thead><tbody>';
    var count = 0;
    var gone = delPlan ? delPlan.round : {};
    t.data.forEach(function (d) {
      var row = d.excelRow, y = yellow[row], now = nowFlags[row], del = gone[row];
      if (only && !y && !now && !del) return;
      count++;
      var cls = (y || now ? 'y' : '') + (del ? ' del' : '') + (row === selectedRow ? ' sel' : '');
      var touched = vcols.some(function (c) { return edits[row + ':' + c]; });
      var sysOnly = y && !now && y.every(function (id) { return /^SYS:/.test(id); }) && !touched;
      var verdict = now ? now.map(shortRule).join(', ') : sysOnly ? esc(y.map(shortRule).join(', ')) : (y ? '<span class="okfix">수정됨 ✓</span> <s>' + esc(y.map(shortRule).join(', ')) + '</s>' : '');
      if (now) verdict = esc(verdict);
      if (del) verdict = '<span class="deltag r' + Math.min(del, 3) + '">' + (mixPlan ? '삭제 (최소 행 변경)' : '삭제 ' + del + '차') + '</span> ' + esc(delRules(row).map(shortRule).join(', '));
      h += '<tr data-row="' + row + '"' + (cls.trim() ? ' class="' + cls.trim() + '"' : '') + '><td class="rn">' + row + '</td><td class="l verdict">' + verdict + '</td>' +
        vcols.map(function (c) { return td(d, c); }).join('') + '<td class="gap"></td>';
      shown.forEach(function (c) { h += td(d, c); });
      h += '</tr>';
    });
    if (!count) h += '<tr><td colspan="' + (shown.length + vcols.length + 3) + '" class="l muted">' + (only ? 'OCAP · 7run 행 없음' : '데이터 없음') + '</td></tr>';
    $('dataTable').innerHTML = h + '</tbody>';
    pick = null;
    renderDelBox();
    dataInfo();
  }

  // Rule ids that put the row on the delete list (in its round).
  function delRules(row) {
    var r = delPlan && delPlan.round[row], out = [];
    if (r) delPlan.rounds[r - 1].forEach(function (x) { if (x.key === row) out = x.rules; });
    return out;
  }

  function rowText(row) {
    var t = table, d = t.data.filter(function (x) { return x.excelRow === row; })[0], li = t.headers.indexOf(t.label);
    var lot = t.headers.map(norm).indexOf(SPC_FORMAT.lot);
    return {label: d && li >= 0 ? fmtLabel(d.cells[li], row) : row + '행', lot: d && lot >= 0 && lot !== li ? cellText(d.cells[lot]) : ''};
  }

  // The result of [시뮬레이션] above the data table. 행 삭제만: the rounds, which rows, and what is left after them.
  function renderDelBox() {
    var box = $('delBox');
    box.classList.toggle('hidden', !delPlan && !fixPlan);
    if (fixPlan) { renderFixBox(box); return; }
    if (!delPlan) return;
    if (mixPlan) { renderMixBox(box); return; }
    var p = delPlan, both = results.some(function (r) { return !!r.sigma; }) ? 'XBAR · SIGMA 차트 모두' : '차트에';
    var h = '<div class="dhead"><b>시뮬레이션 · 행 삭제만</b><span class="muted small">파일 원래 값 기준 (추천값 수정은 빼고 계산) · 아래 차트 · 표는 이 행들을 지운 모습(회색)</span>' +
      '<span class="spacer"></span><button id="ocapFormBtn" class="primary small"' + (p.count ? '' : ' disabled') + ' title="삭제할 행을 회사 OCAP 삭제 양식(EDC Plan · Spec seq# · Data seq#) 엑셀로 저장">OCAP 삭제 양식 엑셀 저장</button>' +
      '<button id="delCsvBtn" class="ghost small"' + (p.count ? '' : ' disabled') + '>삭제 목록 CSV</button></div>';
    if (!p.count) {
      h += '<p class="ok">OCAP · 7run 행이 없어 지울 행이 없습니다.</p>';
    } else {
      h += '<ol class="rounds">';
      p.rounds.forEach(function (list, r) {
        h += '<li><b>' + (r + 1) + '차</b> ' + (r ? '(앞 차수를 지우면 새로 생기는 OCAP · 7run)' : '(노란 행 ' + Object.keys(yellow).length + '개 중 지워야 하는 행)') + ' · ' + list.length + '행: ' +
          list.map(function (x) { return '<a href="#" data-row="' + x.key + '" title="' + esc(rowText(x.key).label + ' · ' + x.rules.map(shortRule).join(', ')) + '">' + x.key + '</a>'; }).join(', ') + '</li>';
      });
      h += '</ol>';
      var keep = Object.keys(yellow).filter(function (row) { return !p.round[row]; }).length;  // a 7-point run loses a point
      h += p.clean
        ? '<p class="ok"><b>모두 ' + p.count + '행</b>(' + p.rounds.length + '차까지)을 지우면 ' + both + ' OCAP · 7run이 나오지 않습니다.' +
          (p.rounds.length > 1 ? ' 1차만 지우면 ' + p.rounds.slice(1).reduce(function (n, l) { return n + l.length; }, 0) + '행에서 다시 생깁니다.' : '') +
          (keep ? ' 노란 행 중 ' + keep + '행은 앞 행을 지우면 풀려서 남깁니다.' : '') + '</p>'
        : '<p class="warn">' + p.rounds.length + '차까지 지워도 OCAP · 7run이 남습니다 (' + p.count + '행).</p>';
    }
    box.innerHTML = h;
  }

  // 행 수정만 (#31): the rows given recommended values, and whether OCAP / 7 run is gone.
  function renderFixBox(box) {
    var both = results.some(function (r) { return !!r.sigma; }) ? 'XBAR · SIGMA 차트 모두' : '차트에';
    var byKey = editRows(), keys = Object.keys(byKey).map(Number).sort(function (a, b) { return a - b; }), left = Object.keys(nowFlags).length;
    var h = '<div class="dhead"><b>시뮬레이션 · 행 수정만</b><span class="muted small">파일 원래 값 기준 · 노란 행을 모두 추천값으로 · 아래 차트 · 표는 값을 고친(빨간 칸) 모습</span>' +
      '<span class="spacer"></span><button id="fixFormBtn" class="primary small"' + (keys.length ? '' : ' disabled') + ' title="값을 고친 행을 회사 RAW_DATA 수정 양식(DATA_SEQ# · Raw Value 1~25 · MAX · MIN · AVG · STD) 엑셀로 저장">RAW_DATA 수정 양식 엑셀 저장</button>' +
      '<button id="delCsvBtn" class="ghost small"' + (keys.length ? '' : ' disabled') + '>수정 목록 CSV</button></div>';
    if (!keys.length && !left) {
      box.innerHTML = h + '<p class="ok">OCAP · 7run 행이 없어 고칠 행이 없습니다.</p>';
      return;
    }
    h += '<ol class="rounds"><li><b>값 수정</b> ' + keys.length + '행: ' + keys.map(function (k) {
      return '<a href="#" data-row="' + k + '" title="' + esc(rowText(k).label + ' · ' + byKey[k].join(', ')) + '">' + k + '</a>'; }).join(', ') + '</li></ol>';
    h += !left
      ? '<p class="ok"><b>' + keys.length + '행</b>(' + Object.keys(edits).length + '칸)을 추천값으로 고치면 ' + both + ' OCAP · 7run이 나오지 않습니다.</p>'
      : '<p class="warn">추천값으로 고쳐도 ' + left + '행에 OCAP · 7run이 남습니다' + (fixPlan.failed ? ' (' + fixPlan.failed + '점은 다른 점을 새로 걸리게 하지 않는 값을 찾지 못함)' : '') + '.</p>';
    h += '<p class="muted small">고친 값은 [RAW_DATA 수정 양식 엑셀 저장]과 표 아래 [수정본 엑셀 저장](빨간 칸)에 들어갑니다. 다시 [행 수정만]을 누르면 원래대로.</p>';
    box.innerHTML = h;
  }
  // excelRow -> ['EXT_MV → 6.5', ...] of the edits
  function editRows() {
    var out = {};
    Object.keys(edits).forEach(function (k) {
      var e = edits[k];
      (out[e.row] = out[e.row] || []).push(table.headers[e.col] + ' → ' + fmt(e.value));
    });
    return out;
  }

  function renderMixBox(box) {
    var p = mixPlan.plan, both = results.some(function (r) { return !!r.sigma; }) ? 'XBAR · SIGMA 차트 모두' : '차트에';
    var link = function (key, title) { return '<a href="#" data-row="' + key + '" title="' + esc(title) + '">' + key + '</a>'; };
    var h = '<div class="dhead"><b>시뮬레이션 · 최소 행 변경 (삭제+수정)</b><span class="muted small">파일 원래 값 기준 · 아래 차트 · 표는 이 행들을 지우고(회색) 값을 고친(빨간 칸) 모습</span>' +
      '<span class="spacer"></span><button id="bothFormBtn" class="primary small"' + (p.rows ? '' : ' disabled') + ' title="삭제할 행은 OCAP 삭제 양식, 값을 고친 행은 RAW_DATA 수정 양식으로, 엑셀 파일 2개를 한 번에 저장 (저장할 폴더를 고릅니다)">양식 2개 엑셀 저장 (삭제 + 수정)</button>' +
      '<button id="delCsvBtn" class="ghost small"' + (p.rows ? '' : ' disabled') + '>변경 목록 CSV</button></div>';
    if (!p.rows) {
      box.innerHTML = h + '<p class="ok">OCAP · 7run 행이 없어 바꿀 행이 없습니다.</p>';
      return;
    }
    var byKey = {}, keys = [];
    p.changes.forEach(function (c) {
      if (!byKey[c.key]) { byKey[c.key] = []; keys.push(c.key); }
      byKey[c.key].push(table.headers[mixPlan.series[c.series].col] + ' → ' + fmt(c.value));
    });
    h += '<ol class="rounds"><li><b>삭제</b> ' + p.deletes.length + '행' + (p.deletes.length ? ': ' + p.deletes.map(function (x) { return link(x.key, rowText(x.key).label + ' · ' + x.rules.map(shortRule).join(', ')); }).join(', ') : '') + '</li>' +
      '<li><b>값 수정</b> ' + keys.length + '행' + (keys.length ? ': ' + keys.map(function (k) { return link(k, rowText(k).label + ' · ' + byKey[k].join(', ')); }).join(', ') : '') + '</li></ol>';
    var cmp = p.compare, part = function (n) { return n === null ? '안 풀림' : n + '행'; };
    var how = {mix: '삭제 · 수정 섞기', 'delete': '행 삭제만', fix: '행 수정만'}[p.method];
    h += p.clean
      ? '<p class="ok"><b>모두 ' + p.rows + '행</b>(삭제 ' + p.deletes.length + ' + 값 수정 ' + keys.length + ')을 바꾸면 ' + both + ' OCAP · 7run이 나오지 않습니다 (' + how + '가 가장 적음).</p>'
      : '<p class="warn">' + p.rows + '행을 바꿔도 OCAP · 7run이 남습니다.</p>';
    h += '<p class="muted small">비교: 삭제 · 수정 섞기 ' + part(cmp.mix) + ' · 행 삭제만 ' + part(cmp['delete']) + ' · 행 수정만 ' + part(cmp.fix) +
      '. [양식 2개 엑셀 저장]: 삭제 행 → OCAP 삭제 양식, 값 수정 행 → RAW_DATA 수정 양식 (각각의 파일). 값 수정은 표 아래 [수정본 엑셀 저장](빨간 칸)에도 들어갑니다.</p>';
    box.innerHTML = h;
  }

  function delCsv() {
    if (mixPlan) { mixCsv(); return; }
    if (fixPlan) { fixCsv(); return; }
    if (!delPlan || !delPlan.count) return;
    var lots = table.headers.map(norm).indexOf(SPC_FORMAT.lot) >= 0;
    var lines = [['차수', '엑셀 행', 'X축', lots ? 'LOT_ID' : '', '판정'].filter(function (v, i) { return i !== 3 || lots; })];
    delPlan.rounds.forEach(function (list, r) {
      list.forEach(function (x) {
        var tx = rowText(x.key), line = [r + 1, x.key, tx.label];
        if (lots) line.push(tx.lot);
        line.push(x.rules.map(shortRule).join(', '));
        lines.push(line);
      });
    });
    downloadCsv(lines, 'SPC_삭제목록_');
  }

  // [최소 행 변경] list: deletions, then new values (one line per cell)
  function mixCsv() {
    var p = mixPlan.plan, lots = table.headers.map(norm).indexOf(SPC_FORMAT.lot) >= 0, byRow = {};
    table.data.forEach(function (d) { byRow[d.excelRow] = d; });
    var line = function (kind, key, col, orig, value, rules) {
      var tx = rowText(key), l = [kind, key, tx.label];
      if (lots) l.push(tx.lot);
      return l.concat([col, orig, value, rules.map(shortRule).join(', ')]);
    };
    var lines = [['구분', '엑셀 행', 'X축'].concat(lots ? ['LOT_ID'] : [], ['열', '원래 값', '새 값', '판정'])];
    p.deletes.forEach(function (x) { lines.push(line('삭제', x.key, '', '', '', x.rules)); });
    p.changes.forEach(function (c) {
      var col = mixPlan.series[c.series].col, d = byRow[c.key];
      lines.push(line('값 수정', c.key, table.headers[col], d ? cellText(d.cells[col]) : '', c.value, c.rules));
    });
    downloadCsv(lines, 'SPC_최소변경목록_');
  }

  // [행 수정만] list: one line per new value
  function fixCsv() {
    var lots = table.headers.map(norm).indexOf(SPC_FORMAT.lot) >= 0;
    var lines = [['엑셀 행', 'X축'].concat(lots ? ['LOT_ID'] : [], ['열', '원래 값', '새 값', '판정'])];
    Object.keys(edits).map(function (k) { return edits[k]; }).sort(function (a, b) { return a.row - b.row || a.col - b.col; }).forEach(function (e) {
      var tx = rowText(e.row), l = [e.row, tx.label];
      if (lots) l.push(tx.lot);
      lines.push(l.concat([table.headers[e.col], cellText(e.orig), e.value, (yellow[e.row] || []).map(shortRule).join(', ')]));
    });
    downloadCsv(lines, 'SPC_수정목록_');
  }

  function downloadCsv(lines, prefix) {
    var csv = '\ufeff' + lines.map(function (l) { return l.map(function (v) { v = String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }).join(','); }).join('\r\n');
    var a = document.createElement('a'), d = new Date();
    a.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv'}));
    a.download = prefix + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + '_' + pad(d.getHours()) + pad(d.getMinutes()) + '.csv';
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
  }

  // [OCAP 삭제 양식 저장] (#28): the rows to delete in the company's OCAP 삭제 양식, apart from the copy above.
  // Since v14 laid out exactly like the owner's form file (#30): one sheet "Sheet1", title B2, row 5
  // "OCAP 전체 삭제 시 / OCAP 일부 삭제 시 / 요청 사항", row 6 the grey header, from row 7 one line per row to delete
  // (EDC Plan = PLAN_NAME, Spec seq# = SPEC_SEQ, Data seq# = DATA_SEQ: a partial delete), empty bordered lines
  // down to row 26. No sheets per Spec seq# any more (v10-v13).
  var OCAP_FORM = {title: 'OCAP 삭제 양식', sheet: 'Sheet1', request: 'Data 자체를 완전 삭제 & 히스토리 삭제 (Data 자체 완전 삭제', lastRow: 26, grey: 'FFAEAAAA'};
  function ocapFormSheets(plan) {
    var hs = table.headers.map(norm), at = function (d, w) { var i = hs.indexOf(w); return i < 0 ? null : d.cells[i]; };
    var ii = table.headers.indexOf(table.item), byRow = {};
    table.data.forEach(function (d) { byRow[d.excelRow] = d; });
    var title = {sz: 10, b: true, h: 'center'}, group = {sz: 10, h: 'center'}, head = {sz: 10, fill: OCAP_FORM.grey, border: true, h: 'center'};
    var cell = {sz: 10, border: true, h: 'center'}, plan0 = {sz: 10, b: true, border: true}, small = {sz: 9, border: true};
    var V = function (st) { return function (v) { return {v: v, s: st}; }; };
    var rows = [[], [null, V(title)(OCAP_FORM.title)], [], [],
      [null, null, V(group)('OCAP 전체 삭제 시'), V(group)('OCAP 일부 삭제 시'), V({sz: 10, h: 'center', wrap: true})('요청 사항')],
      [null, V(head)('EDC Plan'), V(head)('Spec seq#'), V(head)('Data seq#'), V(head)('요청 내용')]];
    Object.keys(plan.round).map(Number).sort(function (a, b) { return a - b; }).forEach(function (row) {
      var d = byRow[row];
      if (!d) return;
      var edc = cellText(at(d, 'planname')) || (ii >= 0 ? cellText(d.cells[ii]) : '') || (table.sheet || '');
      rows.push([null, V(plan0)(edc), V(cell)(at(d, 'specseq')), V(cell)(at(d, 'dataseq')), V(small)(OCAP_FORM.request)]);
    });
    while (rows.length < OCAP_FORM.lastRow) rows.push([null, V(cell)(null), V(cell)(null), V(cell)(null), V(cell)(null)]);
    return [{name: OCAP_FORM.sheet, rows: rows, widths: [0, 64.9, 17.8, 21.8, 44.3]}];
  }

  // [수정 양식 저장] (#30): the rows with new values (red cells) in the owner's RAW_DATA form: "S/S 25>" in B2, row 3
  // DATA_SEQ# · Raw Value 1..25 · MAX · MIN · AVG · STD, from row 4 one yellow line per changed row. The SPC system
  // keeps the 25 raw values (VALUE_1..25) and works EXT_MV / EXT_SIGMA out of them, so the new raw values are the
  // old ones moved by the change of EXT_MV and stretched by the change of EXT_SIGMA (same shape, new mean and
  // spread); without raw values in the file only AVG / STD are written.
  var RAW_FORM = {sheet: 'Sheet1', title: 'S/S 25>', n: 25, fmt: '###0.0000;\\-###0.0000'};
  function rawFormRows() {
    var hs = table.headers.map(norm), mvi = hs.indexOf(SPC_FORMAT.value), sgi = hs.indexOf(SPC_FORMAT.sigma.value), seq = hs.indexOf('dataseq');
    var raw = [];
    for (var i = 1; i <= RAW_FORM.n; i++) raw.push(hs.indexOf('value' + i));
    var byRow = {}, rows = {};
    table.data.forEach(function (d) { byRow[d.excelRow] = d; });
    Object.keys(edits).forEach(function (k) { rows[edits[k].row] = 1; });
    return Object.keys(rows).map(Number).sort(function (a, b) { return a - b; }).map(function (row) {
      var d = byRow[row], mine = Object.keys(edits).filter(function (k) { return edits[k].row === row; }).map(function (k) { return edits[k]; });
      var mv = mvi >= 0 ? mvi : mine[0].col, newOf = function (c) { var e = edits[row + ':' + c]; return e ? e.value : toNum(d.cells[c]); };
      var mv0 = toNum(d.cells[mv]), mv1 = newOf(mv), sg0 = sgi >= 0 ? toNum(d.cells[sgi]) : null, sg1 = sgi >= 0 ? newOf(sgi) : null;
      var vals = raw.map(function (c) { return c >= 0 ? toNum(d.cells[c]) : null; }), nums = vals.filter(function (v) { return v !== null; });
      var out = {row: row, seq: seq >= 0 ? d.cells[seq] : row, raw: vals.map(function () { return null; }), avg: mv1, std: sg1, max: null, min: null};
      if (!nums.length) return out;
      var m0 = SPC.mean(nums), sdS = SPC.sd(nums), sdP = nums.length > 1 ? sdS * Math.sqrt((nums.length - 1) / nums.length) : 0;
      // EXT_SIGMA is the sample or the population SD of the raw values: the one nearer the file's EXT_SIGMA
      var pop = sg0 !== null && isFinite(sdS) && Math.abs(sdP - sg0) < Math.abs(sdS - sg0), sd0 = pop ? sdP : sdS;
      var k = sg1 !== null && sg0 !== null && sg1 !== sg0 && sd0 > 0 ? sg1 / sd0 : 1;
      var m1 = m0 + (mv0 !== null && mv1 !== null ? mv1 - mv0 : 0), digits = 4;
      nums.forEach(function (v) { var x = String(+v.toPrecision(12)).match(/\.(\d+)$/); if (x) digits = Math.max(digits, x[1].length); });
      var f = Math.pow(10, Math.min(digits, 10));
      out.raw = vals.map(function (v) { return v === null ? null : Math.round((m1 + (v - m0) * k) * f) / f; });
      var got = out.raw.filter(function (v) { return v !== null; }), s1 = SPC.sd(got);
      out.max = Math.max.apply(null, got);
      out.min = Math.min.apply(null, got);
      out.avg = SPC.mean(got);
      out.std = got.length > 1 ? (pop ? s1 * Math.sqrt((got.length - 1) / got.length) : s1) : 0;
      return out;
    });
  }
  function rawFormSheets() {
    var head = function (fill) { return {sz: 12, b: true, fill: fill, border: true, h: 'center'}; }, V = function (st) { return function (v) { return {v: v, s: st}; }; };
    var yel = {sz: 12, b: true, fill: 'FFFFFF00', border: true, h: 'center'}, num = Object.assign({fmt: RAW_FORM.fmt}, yel), std = head('FFD0CECE');
    var top = [null, V(head('FFC6E0B4'))('DATA_SEQ#')];
    for (var i = 1; i <= RAW_FORM.n; i++) top.push(V(head('FFD9E1F2'))('Raw Value ' + i));
    ['MAX', 'MIN', 'AVG'].forEach(function (t) { top.push(V(head('FFF8CBAD'))(t)); });
    top.push(V(std)('STD'));
    var rows = [[], [null, V({sz: 12, h: 'center'})(RAW_FORM.title)], top];
    rawFormRows().forEach(function (r) {
      rows.push([V({sz: 12, b: true, fill: 'FFFFFF00', h: 'center'})(null), V(yel)(r.seq)].concat(r.raw.map(V(yel)), [V(num)(r.max), V(num)(r.min), V(num)(r.avg), V(std)(r.std)]));
    });
    var widths = [5.6, 17.3, 14.7];
    while (widths.length < 27) widths.push(0);
    return [{name: RAW_FORM.sheet, rows: rows, widths: widths.concat([16.1, 16.4, 17.8, 16.3]), height: 17.5}];
  }
  // Form file names (#32): (양식 제목)_(SPEC_SEQ)_yyyymmddhhmm.xlsx. SPEC_SEQ of the rows in the form; several
  // values are joined with '+'; no SPEC_SEQ column: the sheet name.
  var RAW_FORM_TITLE = 'RAW_DATA 수정 양식';
  function minuteStamp() {
    var d = new Date();
    return d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + pad(d.getHours()) + pad(d.getMinutes());
  }
  function specSeqOf(rows) {
    var si = table.headers.map(norm).indexOf('specseq'), byRow = {}, seen = {}, out = [];
    if (si >= 0) {
      table.data.forEach(function (d) { byRow[d.excelRow] = d; });
      rows.forEach(function (r) {
        var d = byRow[r], v = d ? cellText(d.cells[si]).trim() : '';
        if (v && !seen[v]) { seen[v] = 1; out.push(v); }
      });
    }
    var name = out.length ? out.join('+') : String(table.sheet || 'SPC');
    return name.replace(/[\\/:*?"<>|]/g, '_');
  }
  function editedRows() { var r = {}; Object.keys(edits).forEach(function (k) { r[edits[k].row] = 1; }); return Object.keys(r).map(Number); }
  function delRows(plan) { return Object.keys(plan.round).map(Number); }
  function formName(title, rows) { return title + '_' + specSeqOf(rows) + '_' + minuteStamp() + '.xlsx'; }
  function rawFormName() { return formName(RAW_FORM_TITLE, editedRows()); }
  async function saveRawForm() {
    if (!table || !Object.keys(edits).length) return;
    var bytes;
    try {
      bytes = window.XLSXLite.book(rawFormSheets());
    } catch (e) {
      setStatus('수정 양식을 만들지 못했습니다: ' + e.message, 'err');
      return;
    }
    await saveBytes(bytes, rawFormName(), '수정 양식');
  }

  function ocapFormName() { return formName(OCAP_FORM.title, delRows(delPlan)); }

  async function saveOcapForm() {
    if (!delPlan || !delPlan.count) return;
    var bytes;
    try {
      bytes = window.XLSXLite.book(ocapFormSheets(delPlan));
    } catch (e) {
      setStatus('OCAP 삭제 양식을 만들지 못했습니다: ' + e.message, 'err');
      return;
    }
    await saveBytes(bytes, ocapFormName(), 'OCAP 삭제 양식');
  }

  // [양식 2개 엑셀 저장] (#31, 최소 행 변경): the OCAP 삭제 양식 and the RAW_DATA 수정 양식 as two files in one go.
  // One folder picker for both (two save dialogs in a row would lose the click that allows the second one); the two
  // files go into a new folder named after SPEC_SEQ inside the picked folder (#32).
  async function saveBothForms() {
    if (!mixPlan || !delPlan) return;
    var files = [];
    try {
      if (delPlan.count) files.push({name: ocapFormName(), bytes: window.XLSXLite.book(ocapFormSheets(delPlan)), what: 'OCAP 삭제 양식'});
      if (Object.keys(edits).length) files.push({name: rawFormName(), bytes: window.XLSXLite.book(rawFormSheets()), what: RAW_FORM_TITLE});
    } catch (e) {
      setStatus('양식을 만들지 못했습니다: ' + e.message, 'err');
      return;
    }
    if (!files.length) return;
    var what = files.map(function (f) { return f.what; }).join(' + ');
    if (files.length === 1) { await saveBytes(files[0].bytes, files[0].name, what); return; }
    if (window.showDirectoryPicker) {
      try {
        var top = await window.showDirectoryPicker({id: 'spcForms', mode: 'readwrite'});
        var folder = specSeqOf(delRows(delPlan).concat(editedRows()));
        var dir = await top.getDirectoryHandle(folder, {create: true});
        for (var i = 0; i < files.length; i++) {
          var w = await (await dir.getFileHandle(files[i].name, {create: true})).createWritable();
          await w.write(files[i].bytes);
          await w.close();
        }
        setStatus('양식 2개 저장: ' + top.name + '\\' + folder + ' 폴더에 ' + files.map(function (f) { return f.name; }).join(', '), 'muted');
      } catch (e) {
        if (!e || e.name !== 'AbortError') setStatus('양식을 저장하지 못했습니다: ' + e.message, 'err');
      }
      return;
    }
    files.forEach(function (f) {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([f.bytes], {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
      a.download = f.name;
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
    });
    setStatus('양식 2개 내려받기: ' + files.map(function (f) { return f.name; }).join(', '), 'muted');
  }

  function toggleDelete() {
    delMode = true;
    analyzeAll(true);
    render();
    setStatus(delPlan.count ? '시뮬레이션 · 행 삭제만: ' + delPlan.count + '행(' + delPlan.rounds.length + '차)을 지운 차트입니다 · 다시 누르면 원래대로' : '시뮬레이션 · 행 삭제만: 지울 행 없음', delPlan.clean ? 'muted' : 'warn');
    $('delBox').scrollIntoView({block: 'nearest'});
  }

  // [시뮬레이션 · 행 수정만] (#31): every yellow row gets its recommended value, from the file's own values (the
  // edits from before wait in prevEdits). The new values are the red cells, saved in the RAW_DATA 수정 양식.
  function toggleFix() {
    if (!table || settings.subgroup > 1) { analyzeAll(true); render(); return; }
    var prev = edits;
    edits = {};
    analyzeAll(true);
    var out = applyFixAll();
    fixPlan = {prevEdits: prev, made: out.made, failed: out.failed};
    analyzeAll(true);
    render();
    setStatus('시뮬레이션 · 행 수정만: 추천값 ' + out.made + '칸' + (out.failed ? ' · ' + out.failed + '점은 추천값을 찾지 못함' : '') + ' · 다시 누르면 원래대로', out.failed ? 'warn' : 'muted');
    $('delBox').scrollIntoView({block: 'nearest'});
  }

  function dataInfo() {
    var nEdits = Object.keys(edits).length, nYellow = Object.keys(yellow).length, nowCount = Object.keys(nowFlags).length;
    var mode = simMode();
    $('dataInfo').textContent = '노란 행 ' + nYellow + '개 (남은 ' + nowCount + ') · 수정 ' + nEdits + '칸' + (delPlan ? ' · 삭제 ' + delPlan.count + '행' : '') +
      (mode ? ' · 시뮬레이션: ' + SIM_NAME[mode] : '') +
      (selectedRow ? ' · 선택 ' + selectedRow + '행' : ' · 표의 행을 누르거나 차트의 점을 더블클릭해 선택');
    var sub = settings.subgroup > 1;
    // Recommended values work on the file's rows; while a simulation is on they wait.
    $('fixOneBtn').disabled = sub || !selectedRow || !!mode;
    $('simBtn').textContent = mode ? '시뮬레이션: ' + SIM_NAME[mode] + ' ▾' : '시뮬레이션 ▾';
    $('simBtn').classList.toggle('on', !!mode);
    $('simMenu').classList.toggle('hidden', !simOpen && !mode);
    [['delBtn', 'del'], ['fixAllBtn', 'fix'], ['mixBtn', 'mix']].forEach(function (b) {
      var on = mode === b[1], el = $(b[0]);
      el.classList.toggle('on', on);
      el.textContent = (on ? '✓ ' : '') + SIM_NAME[b[1]];
      el.disabled = !on && b[1] !== 'del' && sub;
    });
    $('undoBtn').disabled = !nEdits || mode === 'mix' || mode === 'fix';
    $('rawFormBtn').disabled = !nEdits;
    $('fixOneBtn').title = sub ? 'subgroup 1 (I-MR)에서만 추천값을 계산합니다' : '선택한 행(표에서 클릭 또는 차트 점 더블클릭)의 값을 추천값으로 바꿉니다';
  }

  // ---------- drag over the data table, Ctrl+C, paste in Excel as it looks (#31) ----------
  // Cells are picked as a rectangle of table.rows / cells (header line included). The copy is an HTML table with
  // the colours of the screen written into each cell (Excel takes inline styles) plus tab-separated text.
  function pickCell(el) {
    var c = el && el.closest && el.closest('#dataTable td, #dataTable th');
    if (!c || c.parentNode.cells.length < 3) return null;  // the "no data" line
    return [c.parentNode.rowIndex, c.cellIndex];
  }
  function showPick() {
    var t = $('dataTable');
    Array.prototype.forEach.call(t.querySelectorAll('.pick'), function (x) { x.classList.remove('pick'); });
    $('copyBtn').disabled = !pick;
    if (!pick) return;
    var r0 = Math.min(pick.a[0], pick.b[0]), r1 = Math.max(pick.a[0], pick.b[0]), c0 = Math.min(pick.a[1], pick.b[1]), c1 = Math.max(pick.a[1], pick.b[1]);
    for (var r = r0; r <= r1; r++) {
      var cells = t.rows[r].cells;
      for (var c = c0; c <= c1 && c < cells.length; c++) cells[c].classList.add('pick');
    }
  }
  var CELL_STYLE = {
    head: 'background:#eef2f8;color:#334155;font-weight:bold;text-align:center;', vhead: 'background:#dbe6fb;color:#334155;font-weight:bold;text-align:center;',
    gap: 'background:#d9dee6;', rn: 'background:#f6f8fb;color:#6b7486;', y: 'background:#fff59d;', del: 'background:#cbd5e1;color:#64748b;',
    fixed: 'background:#ef4444;color:#ffffff;font-weight:bold;', verdict: 'color:#9a3412;font-weight:bold;'
  };
  function cellStyle(el) {
    var tr = el.parentNode, cl = el.classList, st = 'border:0.5pt solid #d9dee6;white-space:nowrap;';
    if (el.tagName === 'TH') return st + (cl.contains('gap') ? CELL_STYLE.gap : cl.contains('vcol') ? CELL_STYLE.vhead : CELL_STYLE.head);
    if (cl.contains('gap')) return st + CELL_STYLE.gap;
    st += cl.contains('l') ? 'text-align:left;' : 'text-align:right;';
    var del = tr.classList.contains('del');
    if (cl.contains('fixed')) st += CELL_STYLE.fixed;
    else if (del) st += CELL_STYLE.del + (cl.contains('rn') || cl.contains('verdict') ? '' : 'text-decoration:line-through;');
    else if (tr.classList.contains('y')) st += CELL_STYLE.y;
    else if (cl.contains('rn')) st += CELL_STYLE.rn;
    if (cl.contains('verdict') && !cl.contains('fixed')) st += CELL_STYLE.verdict;
    return st;
  }
  function pickedCopy() {
    if (!pick) return null;
    var t = $('dataTable'), r0 = Math.min(pick.a[0], pick.b[0]), r1 = Math.max(pick.a[0], pick.b[0]), c0 = Math.min(pick.a[1], pick.b[1]), c1 = Math.max(pick.a[1], pick.b[1]);
    var html = '<table style="border-collapse:collapse;font-family:\'Malgun Gothic\';font-size:9pt">', text = [];
    for (var r = r0; r <= r1; r++) {
      var cells = t.rows[r].cells, line = [];
      html += '<tr>';
      for (var c = c0; c <= c1 && c < cells.length; c++) {
        var el = cells[c], v = el.textContent.replace(/\s+/g, ' ').trim();
        // text that is not a plain number stays text in Excel (ids with leading zeros, '1/2', dates as shown)
        var asText = v !== '' && !/^-?\d+(\.\d+)?([eE][-+]?\d+)?$/.test(v);
        html += '<td style="' + cellStyle(el) + (asText ? 'mso-number-format:\'\\@\';' : '') + '">' + esc(v) + '</td>';
        line.push(v);
      }
      html += '</tr>';
      text.push(line.join('\t'));
    }
    return {html: html + '</table>', text: text.join('\r\n'), rows: r1 - r0 + 1, cols: c1 - c0 + 1};
  }
  (function () {
    var t = $('dataTable'), dragging = false, moved = false;
    t.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      var at = pickCell(e.target);
      if (!at) return;
      e.preventDefault();
      if (e.shiftKey && pick) pick.b = at;
      else pick = {a: at, b: at};
      dragging = true;
      moved = false;
      showPick();
    });
    t.addEventListener('mouseover', function (e) {
      if (!dragging) return;
      var at = pickCell(e.target);
      if (!at || (at[0] === pick.b[0] && at[1] === pick.b[1])) return;
      pick.b = at;
      moved = true;
      showPick();
    });
    document.addEventListener('mouseup', function () { dragging = false; });
    // dragging near the edge of the table box scrolls it
    var wrap = t.parentNode;
    wrap.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      var r = wrap.getBoundingClientRect(), m = 24;
      if (e.clientY > r.bottom - m) wrap.scrollTop += 20; else if (e.clientY < r.top + m + 20) wrap.scrollTop -= 20;
      if (e.clientX > r.right - m) wrap.scrollLeft += 30; else if (e.clientX < r.left + m) wrap.scrollLeft -= 30;
    });
    document.addEventListener('copy', function (e) {
      var a = document.activeElement;
      if (!pick || (a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) || String(window.getSelection())) return;
      var out = pickedCopy();
      e.clipboardData.setData('text/html', '<html><body>' + out.html + '</body></html>');
      e.clipboardData.setData('text/plain', out.text);
      e.preventDefault();
      setStatus('복사: ' + out.rows + '행 × ' + out.cols + '열 · 엑셀에서 Ctrl+V 하면 화면 색 그대로 들어갑니다', 'muted');
    });
    t.addEventListener('click', function (e) {
      if (moved) e.stopImmediatePropagation();  // a drag over several cells does not pick the row
    }, true);
  })();

  function selectRow(row, scroll) {
    selectedRow = row;
    if ($('flagOnly').checked && !yellow[row] && !nowFlags[row]) {
      $('flagOnly').checked = false;
      renderData();
    } else {
      Array.prototype.forEach.call($('dataTable').querySelectorAll('tr.sel'), function (x) { x.classList.remove('sel'); });
      var cur = $('dataTable').querySelector('tr[data-row="' + row + '"]');
      if (cur) cur.classList.add('sel');
      dataInfo();
    }
    var tr = $('dataTable').querySelector('tr[data-row="' + row + '"]');
    if (tr && scroll) {
      tr.scrollIntoView({block: 'center'});
      tr.classList.remove('flash');
      void tr.offsetWidth;
      tr.classList.add('flash');
    }
  }

  function setEdit(row, col, value) {
    var d = table.data.filter(function (x) { return x.excelRow === row; })[0];
    if (!d) return;
    edits[row + ':' + col] = {row: row, col: col, value: value, orig: d.cells[col] === undefined ? null : d.cells[col]};
  }

  function afterEdits(msg) {
    analyzeAll(true);
    render();
    setStatus(msg, 'muted');
  }

  function fixOne() {
    var row = selectedRow, rules = fixRules(), made = 0, tried = 0, moved = [];
    if (!row || settings.subgroup > 1) return;
    fixItems.forEach(function (it, j) {
      var k = it.excelRows.indexOf(row);
      if (k < 0) return;
      var res = results[j], pi = -1;
      res.points.forEach(function (p, i) { if (p.row === k) pi = i; });
      if (pi < 0) return;
      // XBAR (EXT_MV) and SIGMA (EXT_SIGMA) of the row each get the value that clears that chart (#25)
      // When no value of this row works, another point of the same run / trend is changed instead.
      var apply = function (ch, col, name) {
        tried++;
        if (!ch) return;
        var r = it.excelRows[ch.row];
        setEdit(r, col, ch.value);
        made++;
        if (r !== row) moved.push(name + ' ' + r + '행');
      };
      if (SPC.flagged(res, rules)[pi]) apply(SPC.suggestChange(it, optsFor(it.name), k, rules), it.col, table.headers[it.col]);
      if (res.sigma && sigmaFlagMap(res)[pi]) apply(SPC.suggestChange(sigmaItem(it), sigmaOpts(), k, sigmaRules()), it.sigma.col, table.headers[it.sigma.col]);
    });
    if (!tried) setStatus(row + '행은 OCAP · 7run이 없습니다 (이미 수정됐거나 정상)', 'warn');
    else if (!made) setStatus(row + '행: 다른 점을 새로 걸리게 하지 않는 추천값을 찾지 못했습니다', 'warn');
    else if (made < tried) { afterEdits(row + '행에 추천값 ' + made + '칸 입력 · ' + (tried - made) + '칸은 찾지 못함'); setStatus($('status').textContent, 'warn'); }
    else afterEdits((moved.length ? row + '행 값만으로는 안 풀려 같은 런의 ' + moved.join(', ') : row + '행') + '에 추천값 입력 · 저장하려면 [수정본 엑셀 저장]');
  }

  function applyFixAll() {
    var rules = fixRules(), made = 0, failed = 0;
    fixItems.forEach(function (it, j) {
      var out = SPC.fixAll(it, optsFor(it.name), rules);
      out.changes.forEach(function (ch) { setEdit(it.excelRows[ch.row], it.col, ch.value); made++; });
      failed += out.failed;
      if (results[j] && results[j].sigma) {
        out = SPC.fixAll(sigmaItem(it), sigmaOpts(), sigmaRules());
        out.changes.forEach(function (ch) { setEdit(it.excelRows[ch.row], it.sigma.col, ch.value); made++; });
        failed += out.failed;
      }
    });
    return {made: made, failed: failed};
  }

  function undoEdits() {
    edits = {};
    afterEdits('추천값 수정을 모두 취소했습니다');
  }

  // The copy: the file as read, recommended values in red cells, OCAP / 7 run rows yellow. The original is not touched.
  function copyBytes() {
    var list = Object.keys(edits).map(function (k) { return edits[k]; });
    var rows = Object.keys(yellow).map(Number);
    var xlsx = source && source.kind !== 'demo' && lastBuf && table.path && /\.(xlsx|xlsm)$/i.test(source.name);
    return window.XLSXLite.copy(xlsx ? {buf: lastBuf, sheetPath: table.path} : {rows: table.rows, sheetName: table.sheet}, list, rows);
  }

  function copyName() {
    var d = new Date(), base = source.kind === 'demo' ? '예제' : source.name.replace(/\.[^.]+$/, '');
    var ext = /\.xlsm$/i.test(source.name) ? '.xlsm' : '.xlsx';
    return base + '_SPC수정_' + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + '_' + pad(d.getHours()) + pad(d.getMinutes()) + ext;
  }

  async function saveCopy() {
    if (!table) return;
    var bytes, name = copyName();
    try {
      bytes = copyBytes();
    } catch (e) {
      setStatus('수정본을 만들지 못했습니다: ' + e.message, 'err');
      return;
    }
    await saveBytes(bytes, name, '수정본');
  }

  // Save picker (never over the opened file), or a download when the browser has no picker.
  async function saveBytes(bytes, name, what) {
    var type = /\.xlsm$/.test(name) ? 'application/vnd.ms-excel.sheet.macroEnabled.12' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    if (window.showSaveFilePicker) {
      try {
        var h = await window.showSaveFilePicker({suggestedName: name, types: [{description: 'Excel', accept: {[type]: [name.slice(-5)]}}]});
        if (source.kind === 'handle' && (await h.isSameEntry(source.handle))) {
          setStatus('원본 파일에는 덮어쓰지 않습니다. 다른 이름으로 저장해 주세요', 'err');
          return;
        }
        var w = await h.createWritable();
        await w.write(bytes);
        await w.close();
        setStatus(what + ' 저장: ' + h.name + ' (원본 ' + source.name + '은 그대로)', 'muted');
      } catch (e) {
        if (!e || e.name !== 'AbortError') setStatus(what + '을 저장하지 못했습니다: ' + e.message, 'err');
      }
      return;
    }
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([bytes], {type: type}));
    a.download = name;
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
    setStatus(what + ' 내려받기: ' + name + ' (원본은 그대로)', 'muted');
  }

  function renderEvents() {
    var rows = [];
    results.forEach(function (r) { r.events.forEach(function (ev) { rows.push(ev); }); });
    rows.reverse();
    rows.sort(function (a, b) { return (newKeys[b.key] ? 1 : 0) - (newKeys[a.key] ? 1 : 0); });
    var openOnly = $('openOnly').checked;
    if (openOnly) rows = rows.filter(function (ev) { return !(ocapLog[ev.key] && ocapLog[ev.key].done); });
    $('eventsBox').classList.toggle('hidden', !results.length);
    var h = '<tr><th class="l">항목</th><th class="l">위치 (X축)</th><th>값</th><th class="l">규칙</th><th class="l">OCAP</th><th class="l">상태</th><th class="l">메모</th></tr>';
    rows.forEach(function (ev) {
      var log = ocapLog[ev.key] || {};
      var where = ev.label === ev.endLabel ? ev.label : ev.label + ' ~ ' + ev.endLabel;
      h += '<tr class="click' + (newKeys[ev.key] ? ' new' : '') + (log.done ? ' done' : '') + '" data-key="' + esc(ev.key) + '"><td>' + esc(ev.item) + '</td><td class="l">' + esc(where) +
        '</td><td>' + fmt(ev.value) + '</td><td class="l"><span class="rule ' + baseRule(ev.rule) + '">' + esc(ev.code ? '시스템 ' + ev.code + ' (' + ruleName(ev.rule) + ')' : ruleName(ev.rule)) + '</span></td><td class="l">' +
        esc((settings.ocap[baseRule(ev.rule)] || '').split('\n')[0]) + ' …</td><td class="l">' + (log.done ? '조치 완료' : '<b>미조치</b>') + '</td><td class="l">' + esc(log.note || '') + '</td></tr>';
    });
    if (!rows.length) h += '<tr><td colspan="7" class="l muted">' + (openOnly ? '미조치 이상 없음' : '이상 없음') + '</td></tr>';
    $('events').className = 'grid';
    $('events').innerHTML = h;
  }

  // ---------- charts ----------
  function setup(canvas) {
    var dpr = window.devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.font = '11px "Segoe UI", "Malgun Gothic", sans-serif';
    return {ctx: ctx, w: w, h: h};
  }

  function niceTicks(lo, hi, count) {
    var span = hi - lo, step = Math.pow(10, Math.floor(Math.log10(span / count))), err = span / count / step;
    step *= err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
    var out = [];
    for (var v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(12));
    return out;
  }

  function domain(vals) {
    var lo = Infinity, hi = -Infinity;
    vals.forEach(function (v) { if (v !== null && isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } });
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    if (hi - lo < 1e-12) { var d = Math.abs(lo) * 0.05 || 1; lo -= d; hi += d; }
    var pad2 = (hi - lo) * 0.08;
    return [lo - pad2, hi + pad2];
  }

  function frame(g, lo, hi, left, right, top, bottom) {
    var ctx = g.ctx, ph = g.h - top - bottom;
    var Y = function (v) { return top + (hi - v) / (hi - lo) * ph; };
    ctx.strokeStyle = '#eef1f5';
    ctx.fillStyle = '#6b7486';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    niceTicks(lo, hi, Math.max(2, Math.floor(ph / 40))).forEach(function (t) {
      ctx.beginPath(); ctx.moveTo(left, Y(t)); ctx.lineTo(g.w - right, Y(t)); ctx.stroke();
      ctx.fillText(fmt(t), left - 6, Y(t));
    });
    ctx.strokeStyle = '#c9d0db';
    ctx.strokeRect(left, top, g.w - left - right, ph);
    return Y;
  }

  // Limit line across the visible points; label at the right end.
  var CL_BLUE = '#2563eb';  // CL of the SPC system charts: blue dashed (#34)
  function limitLine(g, X, Y, vals, from, to, color, dash, label) {
    if (!vals) return;
    var ctx = g.ctx;
    ctx.save();
    clipPlot(g);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.3;
    ctx.setLineDash(dash);
    ctx.beginPath();
    for (var i = from; i < to; i++) {
      var y = Y(vals[i]), x0 = X(i) - (X(1) - X(0)) / 2, x1 = X(i) + (X(1) - X(0)) / 2;
      if (i === from) ctx.moveTo(x0, y); else ctx.lineTo(x0, y);
      ctx.lineTo(x1, y);
    }
    ctx.stroke();
    ctx.restore();
    if (label) {
      ctx.fillStyle = color;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(label + ' ' + fmt(vals[to - 1]), Math.min(X(to - 1) + (X(1) - X(0)) / 2, g.w - g.right) + 4, Y(vals[to - 1]));
    }
  }

  // "2026-07-01 02:06:02" -> ['2026-07-01', '02:06'] (date over time on the X axis), else null
  var DATE_TIME = /^(\d{4}-\d{2}-\d{2})[ T](\d{1,2}:\d{2})(:\d{2})?/;
  function dateTime(label) {
    var m = DATE_TIME.exec(String(label));
    return m ? [m[1], m[2]] : null;
  }
  function twoLine(labels, from, to) {
    for (var i = from; i < to; i++) if (dateTime(labels[i])) return true;
    return false;
  }

  // Labels every few points counted from the first point of the period, so they do not jump while scrolling.
  function xLabels(g, sp, labels, bottom) {
    var ctx = g.ctx, X = sp.X, every = Math.max(1, Math.ceil(90 / sp.step));
    ctx.save();
    clipPlot(g);
    ctx.fillStyle = '#6b7486';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    for (var i = sp.a + (((sp.from - sp.a) % every) + every) % every; i < sp.b; i += every) {
      var s = String(labels[i]), dt = dateTime(s);
      if (dt) {
        ctx.fillText(dt[0], X(i), g.h - bottom + 5);
        ctx.fillText(dt[1], X(i), g.h - bottom + 18);
      } else {
        ctx.fillText(s.length > 16 ? s.slice(0, 15) + '…' : s, X(i), g.h - bottom + 6);
      }
    }
    ctx.restore();
  }

  // Horizontal layout of a time chart: every point of the period gets settings.pitch px (0 = fit the card), the
  // inner box of .xscroll is that wide so the card scrolls sideways, and the canvas stays the card's width (sticky)
  // drawing only the part scrolled into view, so the Y axis and limit labels stay in place. XBAR and SIGMA (or MR)
  // share one .xscroll and scroll together. Call before setup(canvas): it sets the canvas width.
  var LEFT = 62, RIGHT = 92;
  function xspan(canvas, n, from) {
    var sc = canvas.parentNode.parentNode, inner = canvas.parentNode, vw = sc.clientWidth;
    var pw = Math.max(10, vw - LEFT - RIGHT), count = Math.max(1, n - from);
    var step = settings.pitch > 0 ? Math.max(settings.pitch, pw / count) : pw / count;
    var full = Math.max(vw, Math.ceil(count * step + LEFT + RIGHT));
    if (inner.style.width !== full + 'px') inner.style.width = full + 'px';
    if (canvas.style.width !== vw + 'px') canvas.style.width = vw + 'px';
    var off = Math.max(0, Math.min(sc.scrollLeft, full - vw));
    sc._geo = {from: from, step: step, pw: pw};
    return {from: from, step: step, off: off,
      X: function (i) { return LEFT + (i - from + 0.5) * step - off; },
      a: Math.max(from, from + Math.floor(off / step) - 1), b: Math.min(n, from + Math.ceil((off + pw) / step) + 1)};
  }

  // Lines and points stay inside the plot box (scrolled-out parts would cover the Y axis labels).
  function clipPlot(g) {
    g.ctx.beginPath();
    g.ctx.rect(g.left, 0, g.w - g.left - g.right, g.h);
    g.ctx.clip();
  }

  function chartTitle(g, text, left) {
    g.ctx.fillStyle = '#334155';
    g.ctx.textAlign = 'left';
    g.ctx.textBaseline = 'top';
    g.ctx.fillText(text, left, 1);
  }

  function drawControl(canvas, r) {
    var n = r.points.length, from = settings.window > 0 ? Math.max(0, n - settings.window) : 0;
    var sp = xspan(canvas, n, from), g = setup(canvas);
    var labels = r.points.map(function (p) { return p.label; });
    // SPC system format: an XBAR chart with the UCL/LCL lines and the CL as a blue dashed line (owner, #34).
    var lines = r.spcForm ? ['UCL', 'LCL', 'CL'] : ROLES;
    var left = g.left = LEFT, right = g.right = RIGHT, top = r.spcForm ? 18 : 10, bottom = twoLine(labels, from, n) ? 36 : 26;
    var L = r.limits, vis = r.x.slice(from);
    lines.forEach(function (k) { if (L[k].values) vis = vis.concat(L[k].values.slice(from)); });
    var dm = domain(vis), Y = frame(g, dm[0], dm[1], left, right, top, bottom), ctx = g.ctx;
    var step = sp.step, X = sp.X, a = sp.a, b = sp.b;
    canvas._hit = {from: a, to: b, X: X, Y: Y, res: r, kind: 'x'};
    if (r.spcForm) chartTitle(g, (r.size > 1 ? 'XBAR 차트 (n=' + r.size + ')' : 'XBAR 차트') + (r.limits.CL.values ? '' : ' (CL 없음: Run · Trend 판정 안 함)'), left);
    if (!n) return;

    if (r.spcForm) {
      limitLine(g, X, Y, L.UCL.values, from, n, '#ea580c', [6, 4], 'UCL');
      limitLine(g, X, Y, L.LCL.values, from, n, '#ea580c', [6, 4], 'LCL');
      limitLine(g, X, Y, L.CL.values, from, n, CL_BLUE, [5, 4], 'CL');
    } else if (L.CL.values && L.UCL.values && L.LCL.values) {
      // ±1σ, ±2σ guide lines from the control limits.
      [1, 2].forEach(function (k) {
        limitLine(g, X, Y, L.CL.values.map(function (c, i) { return c + (L.UCL.values[i] - c) * k / 3; }), from, n, '#cfd5df', [2, 4]);
        limitLine(g, X, Y, L.CL.values.map(function (c, i) { return c - (c - L.LCL.values[i]) * k / 3; }), from, n, '#cfd5df', [2, 4]);
      });
    }
    if (!r.spcForm) {
      limitLine(g, X, Y, L.USL.values, from, n, '#dc2626', [], 'USL');
      limitLine(g, X, Y, L.LSL.values, from, n, '#dc2626', [], 'LSL');
      limitLine(g, X, Y, L.UCL.values, from, n, '#ea580c', [6, 4], 'UCL');
      limitLine(g, X, Y, L.LCL.values, from, n, '#ea580c', [6, 4], 'LCL');
      limitLine(g, X, Y, L.CL.values, from, n, '#16a34a', [], 'CL');
    }

    ctx.save();
    clipPlot(g);
    ctx.strokeStyle = '#2563eb';
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    for (var i = a; i < b; i++) { if (i === a) ctx.moveTo(X(i), Y(r.x[i])); else ctx.lineTo(X(i), Y(r.x[i])); }
    ctx.stroke();
    var bad = flagMap(r), rad = step > 7 ? 3.5 : 2.2;
    for (i = a; i < b; i++) {
      var f = bad[i];
      ctx.beginPath();
      ctx.arc(X(i), Y(r.x[i]), f ? rad + 1.5 : rad, 0, Math.PI * 2);
      ctx.fillStyle = !f ? '#2563eb' : (f.indexOf('OOS') >= 0 ? '#dc2626' : '#f59e0b');
      ctx.fill();
      if (f) { ctx.strokeStyle = '#7f1d1d'; ctx.lineWidth = 1; ctx.stroke(); }
      var row = r.excelRows[r.points[i].rows[0]];
      if (edits[row + ':' + r.col]) {
        ctx.beginPath();
        ctx.arc(X(i), Y(r.x[i]), rad + 4, 0, Math.PI * 2);
        ctx.strokeStyle = '#dc2626';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      if (row === selectedRow) {
        ctx.beginPath();
        ctx.arc(X(i), Y(r.x[i]), rad + 7, 0, Math.PI * 2);
        ctx.strokeStyle = '#111827';
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }
    ctx.restore();
    xLabels(g, sp, labels, bottom);
  }

  function flagMap(r) {
    var m = {};
    Object.keys(r.flags).forEach(function (id) { r.flags[id].forEach(function (i) { (m[i] = m[i] || []).push(id); }); });
    return m;
  }

  // SIGMA chart (SPC system format): EXT_SIGMA with its UCL/LCL lines and the blue dashed CL, date and time under it like the XBAR chart.
  function drawSigma(canvas, r) {
    var n = r.points.length, from = settings.window > 0 ? Math.max(0, n - settings.window) : 0, S = r.sigma;
    var sp = xspan(canvas, n, from), g = setup(canvas);
    var labels = r.points.map(function (p) { return p.label; });
    var left = g.left = LEFT, right = g.right = RIGHT, top = 18, bottom = twoLine(labels, from, n) ? 36 : 26, ctx = g.ctx;
    var vis = S.values.slice(from);
    if (S.ucl) vis = vis.concat(S.ucl.slice(from));
    if (S.lcl) vis = vis.concat(S.lcl.slice(from));
    if (S.cl) vis = vis.concat(S.cl.slice(from));
    var dm = domain(vis), Y = frame(g, dm[0], dm[1], left, right, top, bottom);
    var step = sp.step, X = sp.X, a = sp.a, b = sp.b;
    chartTitle(g, S.cl ? 'SIGMA 차트' : 'SIGMA 차트 (CL 없음: Run · Trend 판정 안 함)', left);
    canvas._hit = {from: a, to: b, X: X, Y: Y, res: r, kind: 's'};
    if (!n) return;
    limitLine(g, X, Y, S.ucl, from, n, '#ea580c', [6, 4], 'UCL');
    limitLine(g, X, Y, S.lcl, from, n, '#ea580c', [6, 4], 'LCL');
    limitLine(g, X, Y, S.cl, from, n, CL_BLUE, [5, 4], 'CL');
    ctx.save();
    clipPlot(g);
    ctx.strokeStyle = '#475569';
    ctx.lineWidth = 1.3;
    ctx.beginPath();
    var started = false;
    for (var i = a; i < b; i++) {
      if (S.values[i] === null) continue;
      if (!started) { ctx.moveTo(X(i), Y(S.values[i])); started = true; } else ctx.lineTo(X(i), Y(S.values[i]));
    }
    ctx.stroke();
    var rad = step > 7 ? 3 : 2;
    var bad = sigmaFlagMap(r);
    for (i = a; i < b; i++) {
      if (S.values[i] === null) continue;
      var out = !!bad[i];
      ctx.beginPath();
      ctx.arc(X(i), Y(S.values[i]), out ? rad + 1.5 : rad, 0, Math.PI * 2);
      ctx.fillStyle = out ? '#f59e0b' : '#475569';
      ctx.fill();
    }
    ctx.restore();
    xLabels(g, sp, labels, bottom);
  }

  function drawRange(canvas, r) {
    if (r.sigma) { drawSigma(canvas, r); return; }
    var n = r.points.length, from = settings.window > 0 ? Math.max(0, n - settings.window) : 0, R = r.range;
    var sp = xspan(canvas, n, from), g = setup(canvas);
    var left = g.left = LEFT, right = g.right = RIGHT, top = 16, bottom = 8, ctx = g.ctx;
    var dm = domain(R.values.slice(from).concat([R.ucl, R.lcl, R.cl]));
    var Y = frame(g, Math.max(dm[0], R.lcl - (dm[1] - dm[0]) * 0.05), dm[1], left, right, top, bottom);
    var X = sp.X, a = sp.a, b = sp.b;
    ctx.fillStyle = '#334155';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(R.name + ' 차트', left, 1);
    canvas._hit = {from: a, to: b, X: X, Y: Y, res: r, kind: 'r'};
    if (!n || !isFinite(R.cl)) return;
    var c = function (v) { var a = []; for (var i = 0; i < n; i++) a.push(v); return a; };
    limitLine(g, X, Y, c(R.ucl), from, n, '#ea580c', [6, 4], 'UCL');
    if (R.lcl > 0) limitLine(g, X, Y, c(R.lcl), from, n, '#ea580c', [6, 4], 'LCL');
    limitLine(g, X, Y, c(R.cl), from, n, '#16a34a', [], R.name + '̄');
    ctx.save();
    clipPlot(g);
    ctx.strokeStyle = '#64748b';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    var started = false;
    for (var i = a; i < b; i++) {
      if (R.values[i] === null) continue;
      if (!started) { ctx.moveTo(X(i), Y(R.values[i])); started = true; } else ctx.lineTo(X(i), Y(R.values[i]));
    }
    ctx.stroke();
    for (i = a; i < b; i++) {
      if (R.values[i] === null) continue;
      var out = r.rangeFlags.indexOf(i) >= 0;
      ctx.beginPath();
      ctx.arc(X(i), Y(R.values[i]), out ? 3.5 : 2, 0, Math.PI * 2);
      ctx.fillStyle = out ? '#f59e0b' : '#64748b';
      ctx.fill();
    }
    ctx.restore();
  }

  function drawHist(canvas, r) {
    var g = setup(canvas), ctx = g.ctx, all = [];
    r.points.forEach(function (p) { all.push.apply(all, p.raw); });
    canvas._hit = null;
    ctx.fillStyle = '#334155';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('히스토그램', 8, 1);
    if (all.length < 2) return;
    // Bars with their frequency on top, the normal curve, the spec limits and the mean ± 3σ lines.
    var n = r.points.length, L = r.limits, lim = function (k) { return L[k].values ? L[k].values[n - 1] : null; };
    var m = r.stats.mean, s = r.stats.sd, three = s > 0 ? [['-3σ', m - 3 * s], ['+3σ', m + 3 * s]] : [];
    var dm = domain(all.concat([lim('USL'), lim('LSL')], three.map(function (p) { return p[1]; })));
    var bins = Math.max(5, Math.min(30, Math.ceil(Math.log2(all.length)) + 1)), counts = new Array(bins).fill(0);
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), bw = (hi - lo) / bins || 1;
    all.forEach(function (v) { counts[Math.min(bins - 1, Math.floor((v - lo) / bw))]++; });
    var left = 8, right = 8, top = 30, bottom = 18, pw = g.w - left - right, ph = g.h - top - bottom;
    var X = function (v) { return left + (v - dm[0]) / (dm[1] - dm[0]) * pw; };
    var max = Math.max.apply(null, counts);
    var peak = s > 0 ? all.length * bw / (s * Math.sqrt(2 * Math.PI)) : 0;
    var H = function (c) { return top + ph - c / Math.max(max, peak) * ph; };
    ctx.fillStyle = '#bfd3fb';
    ctx.strokeStyle = '#7aa2f0';
    for (var b = 0; b < bins; b++) {
      var x0 = X(lo + b * bw), x1 = X(lo + (b + 1) * bw);
      ctx.fillRect(x0, H(counts[b]), Math.max(1, x1 - x0 - 1), top + ph - H(counts[b]));
    }
    ctx.fillStyle = '#1f2937';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    for (b = 0; b < bins; b++) {
      if (counts[b]) ctx.fillText(String(counts[b]), (X(lo + b * bw) + X(lo + (b + 1) * bw)) / 2, H(counts[b]) - 1);
    }
    canvas._bins = counts;
    if (s > 0) {
      ctx.strokeStyle = '#1e3a8a';
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      for (var k = 0; k <= 80; k++) {
        var v = dm[0] + (dm[1] - dm[0]) * k / 80, y = H(peak * Math.exp(-0.5 * Math.pow((v - m) / s, 2)));
        if (k) ctx.lineTo(X(v), y); else ctx.moveTo(X(v), y);
      }
      ctx.stroke();
    }
    var marks = [['LSL', lim('LSL'), '#dc2626', []], ['USL', lim('USL'), '#dc2626', []]].concat(three.map(function (p) { return [p[0], p[1], '#7c3aed', [4, 3]]; }));
    marks.forEach(function (p) {
      var v = p[1];
      if (v === null || !isFinite(v)) return;
      ctx.save();
      ctx.strokeStyle = p[2];
      ctx.setLineDash(p[3]);
      ctx.beginPath(); ctx.moveTo(X(v), top - 12); ctx.lineTo(X(v), top + ph); ctx.stroke();
      ctx.restore();
      ctx.fillStyle = p[2];
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(p[0], X(v), top + ph + 3);
    });
    canvas._marks = marks.filter(function (p) { return p[1] !== null && isFinite(p[1]); }).map(function (p) { return p[0]; });
  }

  function drawAll() {
    Array.prototype.forEach.call($('cards').children, function (card) { drawCard(card, true); });
  }
  function drawCard(card, hist) {
    var r = card._res;
    if (!r) return;
    drawControl(card.querySelector('.cx'), r);
    drawRange(card.querySelector('.cr'), r);
    if (hist) drawHist(card.querySelector('.ch'), r);
  }
  // Scrolling sideways redraws only the time charts of that card, once per frame.
  function queueCard(card) {
    if (card._queued) return;
    card._queued = true;
    requestAnimationFrame(function () { card._queued = false; drawCard(card, false); });
  }

  // Scroll every chart so the point of this Excel row is in view (picked in the data table).
  function revealRow(row) {
    Array.prototype.forEach.call($('cards').children, function (card) {
      var r = card._res, sc = card.querySelector('.xscroll'), geo = sc._geo;
      if (!r || !geo) return;
      for (var i = geo.from; i < r.points.length; i++) {
        if (r.points[i].rows.some(function (k) { return r.excelRows[k] === row; })) {
          var x = (i - geo.from + 0.5) * geo.step;
          if (x < sc.scrollLeft || x > sc.scrollLeft + geo.pw) sc.scrollLeft = Math.max(0, x - geo.pw / 2);
          return;
        }
      }
    });
  }

  var redrawQueued = false;
  new ResizeObserver(function () {
    if (redrawQueued) return;
    redrawQueued = true;
    requestAnimationFrame(function () { redrawQueued = false; drawAll(); });
  }).observe($('cards'));

  // Tooltip: nearest point under the mouse.
  $('cards').addEventListener('mousemove', function (e) {
    var c = e.target, hit = c && c._hit, tip = $('tip');
    if (!hit || hit.to <= hit.from) { tip.classList.add('hidden'); return; }
    var rect = c.getBoundingClientRect(), mx = e.clientX - rect.left;
    var step = hit.X(1) - hit.X(0), i = Math.round((mx - hit.X(hit.from)) / step) + hit.from;
    if (i < hit.from || i >= hit.to) { tip.classList.add('hidden'); return; }
    var r = hit.res, p = r.points[i], L = r.limits, lines = [p.label];
    if (hit.kind === 'x') {
      if (r.lots) lines.push('LOT ' + r.lots[p.row]);
      lines.push((r.size > 1 ? '평균 ' : '값 ') + fmt(p.value) + (r.size > 1 ? '  (' + p.raw.map(fmt).join(', ') + ')' : ''));
      ROLES.forEach(function (k) { if (L[k].values) lines.push(k + ' ' + fmt(L[k].values[i])); });
      var f = flagMap(r)[i];
      if (f) lines.push('⚠ ' + f.map(ruleName).join(', '));
      var ed = edits[r.excelRows[p.rows[0]] + ':' + r.col];
      if (ed) lines.push('추천값으로 수정됨 (원래 ' + cellText(ed.orig) + ')');
      lines.push('엑셀 ' + p.rows.map(function (k) { return r.excelRows[k]; }).join(', ') + '행 · 더블클릭: 아래 표의 그 행으로');
    } else if (hit.kind === 's') {
      if (r.lots) lines.push('LOT ' + r.lots[p.row]);
      lines.push('SIGMA ' + fmt(r.sigma.values[i]));
      if (r.sigma.ucl) lines.push('UCL ' + fmt(r.sigma.ucl[i]));
      if (r.sigma.lcl) lines.push('LCL ' + fmt(r.sigma.lcl[i]));
      var sf = sigmaFlagMap(r)[i];
      if (sf) lines.push('⚠ ' + sf.map(ruleName).join(', '));
      var se = edits[r.excelRows[p.rows[0]] + ':' + r.sigma.col];
      if (se) lines.push('추천값으로 수정됨 (원래 ' + cellText(se.orig) + ')');
    } else {
      lines.push(r.range.name + ' ' + fmt(r.range.values[i]));
      if (r.rangeFlags.indexOf(i) >= 0) lines.push('⚠ ' + r.range.name + ' 관리한계 이탈');
    }
    tip.textContent = lines.join('\n');
    tip.classList.remove('hidden');
    tip.style.left = Math.min(window.innerWidth - 330, e.clientX + 14) + 'px';
    tip.style.top = (e.clientY + 14) + 'px';
  });
  $('cards').addEventListener('mouseleave', function () { $('tip').classList.add('hidden'); });

  // Double-click a point: select its row in the data table below and scroll there.
  function pointAt(e) {
    var c = e.target, hit = c && c._hit;
    if (!hit || hit.to <= hit.from) return null;
    var rect = c.getBoundingClientRect(), step = hit.X(1) - hit.X(0);
    var i = Math.round((e.clientX - rect.left - hit.X(hit.from)) / step) + hit.from;
    return i < hit.from || i >= hit.to ? null : {res: hit.res, i: i};
  }
  $('cards').addEventListener('dblclick', function (e) {
    var p = pointAt(e);
    if (!p) return;
    e.preventDefault();
    selectRow(p.res.excelRows[p.res.points[p.i].rows[0]], true);
    drawAll();
  });

  // ---------- dialogs ----------
  function modal(html, bind) {
    $('modal').innerHTML = html;
    $('modalBack').classList.remove('hidden');
    bind($('modal'));
  }
  function closeModal() { $('modalBack').classList.add('hidden'); }
  $('modalBack').addEventListener('mousedown', function (e) { if (e.target === $('modalBack')) closeModal(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });

  // XBAR and SIGMA charts have their own rules and point counts (#29); the OCAP texts are shared by rule.
  function settingsDialog() {
    var h = '<h3>판정 규칙 · OCAP 설정</h3><div class="row"><label class="chk"><input type="checkbox" id="dSound"' + (settings.sound ? ' checked' : '') + '> 새 이상이 생기면 소리</label></div>';
    var ruleRow = function (r, chart, set) {
      return '<div class="row"><label class="chk"><input type="checkbox" data-chart="' + chart + '" data-rule="' + r.id + '"' + (set.rules[r.id] ? ' checked' : '') + '> <b>' + esc(r.name) + '</b></label>' +
        (r.n ? '<label><input type="number" min="2" max="50" data-chart="' + chart + '" data-n="' + r.id + '" value="' + (set.n[r.id] || r.n) + '"> 점</label>' : '') +
        '<span class="muted">' + esc(r.desc) + '</span></div>';
    };
    h += '<h4>XBAR 차트 (값 차트)</h4><p class="muted small">SPC 시스템 양식에서 EXT_MV_CENTER(CL)가 비어 있으면 SPC 시스템처럼 Run · Trend는 판정하지 않습니다 (규격 · 관리한계 이탈만).</p>';
    SPC.RULES.forEach(function (r) {
      h += '<div class="ruleset">' + ruleRow(r, 'x', settings) + '<textarea data-ocap="' + r.id + '" placeholder="이 규칙에 걸리면 할 조치 (OCAP, 두 차트 공통)">' + esc(settings.ocap[r.id] || '') + '</textarea></div>';
    });
    h += '<h4>SIGMA 차트 (SPC 시스템 양식의 EXT_SIGMA)</h4><p class="muted small">OCAP 조치 문구는 위 XBAR 차트의 같은 규칙 문구를 같이 씁니다. EXT_SIGMA_CENTER(CL)가 비어 있으면 SPC 시스템처럼 Run · Trend는 판정하지 않습니다 (관리한계 이탈만).</p>';
    SPC.RULES.forEach(function (r) {
      if (SIGMA_RULES.indexOf(r.id) >= 0) h += '<div class="ruleset">' + ruleRow(r, 's', settings.sigma) + '</div>';
    });
    h += '<div class="buttons"><button class="ghost" id="dReset">기본값으로</button><span class="spacer"></span><button class="ghost" id="dCancel">취소</button><button class="primary" id="dOk">저장</button></div>';
    modal(h, function (m) {
      m.querySelector('#dCancel').onclick = closeModal;
      m.querySelector('#dReset').onclick = function () {
        settings.rules = Object.assign({}, SPC.DEFAULT_ON);
        settings.n = {};
        settings.sigma = {rules: Object.assign({}, SPC.SIGMA_DEFAULT_ON), n: {}};
        settings.ocap = Object.assign({}, DEFAULT_OCAP);
        save();
        settingsDialog();
      };
      m.querySelector('#dOk').onclick = function () {
        settings.sound = m.querySelector('#dSound').checked;
        var setOf = function (c) { return c.dataset.chart === 's' ? settings.sigma : settings; };
        m.querySelectorAll('[data-rule]').forEach(function (c) { setOf(c).rules[c.dataset.rule] = c.checked; });
        // only counts that differ from the default are kept, so a later default (Trend 7 -> 6 in v11) reaches them
        m.querySelectorAll('[data-n]').forEach(function (c) {
          var v = +c.value | 0, d = SPC.RULES.filter(function (r) { return r.id === c.dataset.n; })[0].n, n = setOf(c).n;
          if (v >= 2 && v !== d) n[c.dataset.n] = v; else delete n[c.dataset.n];
        });
        m.querySelectorAll('[data-ocap]').forEach(function (c) { settings.ocap[c.dataset.ocap] = c.value; });
        save();
        closeModal();
        recompute();
      };
    });
  }

  function limitsDialog(name) {
    var r = results.filter(function (x) { return x.name === name; })[0];
    if (!r) return;
    var man = settings.manual[name] || {}, n = r.points.length;
    var h = '<h3>한계 설정 — ' + esc(name) + '</h3><p class="muted">비워 두면 엑셀 열 값 또는 계산값을 씁니다. 숫자를 넣으면 그 값으로 고정합니다.</p><div class="lim">';
    ROLES.forEach(function (k) {
      var L = r.limits[k], cur = L.values && n ? fmt(L.values[n - 1]) : '-';
      h += '<b>' + k + '</b><input data-k="' + k + '" value="' + (man[k] !== undefined ? man[k] : '') + '" placeholder="' + esc(cur) + '"><span class="muted">지금 ' + esc(cur) + ' (' + esc(L.source) + ')</span>';
    });
    h += '</div><div class="buttons"><button class="ghost" id="dCancel">취소</button><button class="primary" id="dOk">적용</button></div>';
    modal(h, function (m) {
      m.querySelector('#dCancel').onclick = closeModal;
      m.querySelector('#dOk').onclick = function () {
        var v = {};
        m.querySelectorAll('[data-k]').forEach(function (c) { var x = toNum(c.value); if (x !== null) v[c.dataset.k] = x; });
        if (Object.keys(v).length) settings.manual[name] = v; else delete settings.manual[name];
        save();
        closeModal();
        recompute();
      };
    });
  }

  function ocapDialog(key) {
    var ev = null;
    results.forEach(function (r) { r.events.forEach(function (e) { if (e.key === key) ev = e; }); });
    if (!ev) return;
    var log = ocapLog[key] || {};
    var where = ev.label === ev.endLabel ? ev.label : ev.label + ' ~ ' + ev.endLabel;
    var h = '<h3>OCAP — ' + esc(ev.item) + '</h3><div class="row"><span class="rule ' + baseRule(ev.rule) + '">' + esc(ruleName(ev.rule)) + '</span><span class="muted">' + esc(ruleDesc(ev.rule)) + '</span></div>' +
      '<div class="row">위치: <b>' + esc(where) + '</b> · 값 <b>' + fmt(ev.value) + '</b></div><div class="steps">' + esc(settings.ocap[baseRule(ev.rule)] || '(조치 내용 없음: [규칙 · OCAP 설정]에서 입력)') + '</div>' +
      '<div class="row"><label class="chk"><input type="checkbox" id="dDone"' + (log.done ? ' checked' : '') + '> 조치 완료</label>' + (log.at ? '<span class="muted small">기록 ' + esc(log.at) + '</span>' : '') + '</div>' +
      '<textarea id="dNote" placeholder="조치 내용 메모 (이 PC의 브라우저에만 저장)">' + esc(log.note || '') + '</textarea>' +
      '<div class="buttons"><button class="ghost" id="dCancel">닫기</button><button class="primary" id="dOk">저장</button></div>';
    modal(h, function (m) {
      m.querySelector('#dCancel').onclick = closeModal;
      m.querySelector('#dOk').onclick = function () {
        var d = new Date();
        ocapLog[key] = {done: m.querySelector('#dDone').checked, note: m.querySelector('#dNote').value, at: d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + stamp()};
        delete newKeys[key];
        save();
        closeModal();
        render();
      };
    });
  }

  function recompute() {
    if (!table) return;
    dropSim();
    analyzeAll(true);
    render();
  }

  // ---------- IndexedDB (the settings file handle; the old 'recent' entry of v15 and earlier is no longer used) ----------
  function idb(mode, fn) {
    return new Promise(function (resolve) {
      try {
        var req = indexedDB.open('spc-chart', 1);
        req.onupgradeneeded = function () { req.result.createObjectStore('kv'); };
        req.onsuccess = function () {
          var tx = req.result.transaction('kv', mode), st = tx.objectStore('kv'), out = fn(st);
          tx.oncomplete = function () { resolve(out && out.result); };
          tx.onerror = tx.onabort = function () { resolve(null); };
        };
        req.onerror = function () { resolve(null); };
      } catch (e) { resolve(null); }
    });
  }

  // [설정 저장] (#30): the settings into this browser (read back to check) and into a settings file, for PCs whose
  // browser forgets site data when it closes. The first save asks where to put the file; later saves overwrite it
  // (its handle is kept in IndexedDB, Edge may ask once for permission). [설정 불러오기] reads such a file back.
  var SETTINGS_FILE = 'SPC_Chart_설정.json';
  async function saveSettingsNow() {
    save();
    var kept = false;
    try { kept = localStorage.getItem('spc.settings') === JSON.stringify(settings); } catch (e) { kept = false; }
    var text = JSON.stringify({app: 'SPC Chart HTML', version: TITLE, saved: new Date().toISOString(), settings: settings}, null, 1);
    var file = null;
    try {
      file = await writeSettingsFile(text);
    } catch (e) {
      setStatus('설정 파일을 저장하지 못했습니다: ' + e.message + (kept ? ' · 브라우저에는 저장함' : ''), 'err');
      return;
    }
    var parts = [];
    if (kept) parts.push('이 PC 브라우저');
    if (file) parts.push('파일 ' + file);
    setStatus(parts.length ? '설정 저장: ' + parts.join(' + ') + ' · ' + stamp() + ' · 다음에 열면 이 설정으로 시작합니다' : '설정을 저장하지 못했습니다 (브라우저 저장 막힘, 파일 저장 취소)', parts.length ? 'muted' : 'err');
  }
  async function writeSettingsFile(text) {
    if (!window.showSaveFilePicker) {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([text], {type: 'application/json'}));
      a.download = SETTINGS_FILE;
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
      return SETTINGS_FILE + ' (내려받기)';
    }
    var h = await idb('readonly', function (st) { return st.get('settingsFile'); });
    if (h) {
      try {
        if ((await h.queryPermission({mode: 'readwrite'})) !== 'granted' && (await h.requestPermission({mode: 'readwrite'})) !== 'granted') h = null;
      } catch (e) { h = null; }
    }
    if (!h) {
      try {
        h = await window.showSaveFilePicker({suggestedName: SETTINGS_FILE, id: 'spc-settings', types: [{description: 'SPC Chart 설정', accept: {'application/json': ['.json']}}]});
      } catch (e) {
        if (e && e.name === 'AbortError') return null;
        throw e;
      }
      idb('readwrite', function (st) { st.put(h, 'settingsFile'); });
    }
    var w = await h.createWritable();
    await w.write(text);
    await w.close();
    return h.name;
  }
  async function loadSettingsFile(f) {
    var got;
    try {
      got = JSON.parse(await f.text());
    } catch (e) {
      setStatus(f.name + ': 설정 파일(.json)이 아닙니다', 'err');
      return;
    }
    var s = got && got.settings;
    if (!s || typeof s !== 'object' || !s.rules) {
      setStatus(f.name + ': [설정 저장]으로 만든 SPC Chart 설정 파일이 아닙니다', 'err');
      return;
    }
    settings = normalize(s);
    save();
    if (table) { buildTable(); recompute(); }
    setStatus('설정 불러옴: ' + f.name + (got.saved ? ' (저장 ' + String(got.saved).slice(0, 16).replace('T', ' ') + ' UTC)' : '') + ' · 이 PC 브라우저에도 저장함', 'muted');
  }

  // ---------- demo: two items, a point added every few seconds ----------
  function demoSource() {
    var t0 = new Date(2026, 9, 1, 8, 0), rows = [['날짜', '항목', '측정값', 'USL', 'LSL']], seed = 7, k = 0;
    function rnd() { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; }
    function gauss() { return Math.sqrt(-2 * Math.log(rnd() || 1e-9)) * Math.cos(2 * Math.PI * rnd()); }
    function add() {
      var d = new Date(t0.getTime() + k * 3600000), shift = k > 45 && k < 56 ? 0.12 : 0;
      rows.push([d, '두께', +(10 + shift + gauss() * 0.08).toFixed(3), 10.4, 9.6]);
      rows.push([d, '폭', +(25 + gauss() * 0.15 + (k === 30 ? 0.9 : 0)).toFixed(3), 25.8, 24.2]);
      k++;
    }
    for (var i = 0; i < 300; i++) add();
    return {
      tick: function () { return k; },
      book: function () { return [{name: '예제', rows: rows.slice()}]; }
    };
  }

  // ---------- events ----------
  $('openBtn').onclick = openPicked;
  $('fileIn').onchange = function () {
    var f = $('fileIn').files[0];
    if (!f) return;
    source = {name: f.name, kind: 'file', file: f};
    startSource();
    $('fileIn').value = '';
  };
  $('reloadBtn').onclick = function () { refresh(true); };
  $('demoBtn').onclick = function () {
    settings.sheet = '예제';
    settings.cols = {};
    source = {name: '예제 데이터 (300시간 기간)', kind: 'demo', demo: demoSource()};
    startSource();
  };
  $('settingsBtn').onclick = settingsDialog;
  $('alarmClose').onclick = hideAlarm;
  $('alarmOcap').onclick = function () { hideAlarm(); if (alarmEvents[0]) ocapDialog(alarmEvents[0].key); };
  $('openOnly').onchange = renderEvents;
  $('events').addEventListener('click', function (e) {
    var tr = e.target.closest('tr[data-key]');
    if (tr) ocapDialog(tr.dataset.key);
  });
  $('summary').addEventListener('click', function (e) {
    var tr = e.target.closest('tr[data-i]');
    if (!tr) return;
    var name = results[+tr.dataset.i].name, card = $('cards').querySelector('[data-name="' + CSS.escape(name) + '"]');
    if (card) card.scrollIntoView({behavior: 'smooth', block: 'start'});
  });

  function onColumns() {
    var vals = Array.prototype.map.call($('valueBox').querySelectorAll('input:checked'), function (c) { return c.value; });
    settings.cols = {label: $('labelSel').value, labelPicked: settings.cols.labelPicked || $('labelSel').value !== table.label,
      item: $('itemSel').value, values: vals, sig: table.numeric.join('|')};
    buildTable();
    recompute();
  }
  $('sheetSel').onchange = function () { settings.sheet = $('sheetSel').value; settings.cols = {}; edits = {}; selectedRow = null; buildTable(); recompute(); };
  $('flagOnly').onchange = renderData;
  $('sysJudge').onchange = function () {
    settings.sysJudge = $('sysJudge').checked;
    save();
    if (!table) return;
    analyzeAll(true);
    render();
  };
  $('dataTable').addEventListener('click', function (e) {
    var tr = e.target.closest('tr[data-row]');
    if (!tr) return;
    selectRow(+tr.dataset.row, false);
    revealRow(+tr.dataset.row);
    drawAll();
  });
  $('fixOneBtn').onclick = fixOne;
  $('simBtn').onclick = function () { simOpen = !simOpen || !!simMode(); dataInfo(); };
  $('delBtn').onclick = function () { setSim('del'); };
  $('fixAllBtn').onclick = function () { setSim('fix'); };
  $('mixBtn').onclick = function () { setSim('mix'); };
  $('rawFormBtn').onclick = saveRawForm;
  $('saveSetBtn').onclick = saveSettingsNow;
  $('loadSetBtn').onclick = function () { $('setIn').click(); };
  $('setIn').onchange = function () {
    var f = $('setIn').files[0];
    $('setIn').value = '';
    if (f) loadSettingsFile(f);
  };
  $('delBox').addEventListener('click', function (e) {
    if (e.target.id === 'delCsvBtn') { delCsv(); return; }
    if (e.target.id === 'ocapFormBtn') { saveOcapForm(); return; }
    if (e.target.id === 'fixFormBtn') { saveRawForm(); return; }
    if (e.target.id === 'bothFormBtn') { saveBothForms(); return; }
    var a = e.target.closest('a[data-row]');
    if (!a) return;
    e.preventDefault();
    selectRow(+a.dataset.row, true);
  });
  $('undoBtn').onclick = undoEdits;
  $('copyBtn').onclick = function () { if (pick) document.execCommand('copy'); };
  $('valueFold').addEventListener('toggle', function () { if (table) renderValueSum(); });
  $('saveBtn').onclick = saveCopy;
  $('labelSel').onchange = onColumns;
  $('itemSel').onchange = onColumns;
  $('valueBox').onchange = onColumns;
  $('sizeIn').onchange = function () { settings.subgroup = Math.max(1, Math.min(25, +$('sizeIn').value | 0 || 1)); save(); recompute(); };
  $('baseIn').onchange = function () { settings.baseline = Math.max(0, +$('baseIn').value | 0); save(); recompute(); };
  $('winIn').onchange = function () { settings.window = Math.max(0, +$('winIn').value | 0); save(); render(); };
  $('pitchSel').onchange = function () { settings.pitch = Math.max(0, +$('pitchSel').value | 0); save(); drawAll(); };
  $('viewSel').onchange = render;

  $('csvBtn').onclick = function () {
    var lines = [['항목', '시작', '끝', '값', '규칙', '상태', '메모', '기록 시각']];
    results.forEach(function (r) {
      r.events.forEach(function (ev) {
        var log = ocapLog[ev.key] || {};
        lines.push([ev.item, ev.label, ev.endLabel, fmt(ev.value), ruleName(ev.rule), log.done ? '조치 완료' : '미조치', log.note || '', log.at || '']);
      });
    });
    var csv = '﻿' + lines.map(function (l) { return l.map(function (v) { v = String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }).join(','); }).join('\r\n');
    var a = document.createElement('a'), d = new Date();
    a.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv'}));
    a.download = 'SPC_이상목록_' + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + '_' + pad(d.getHours()) + pad(d.getMinutes()) + '.csv';
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
  };

  // Drag a file from Explorer onto the page (Edge gives a live handle, so refresh still works).
  document.addEventListener('dragover', function (e) { e.preventDefault(); });
  document.addEventListener('drop', async function (e) {
    e.preventDefault();
    var item = e.dataTransfer.items && e.dataTransfer.items[0];
    if (item && item.getAsFileSystemHandle) {
      var h = await item.getAsFileSystemHandle();
      if (h && h.kind === 'file') { useHandle(h); return; }
    }
    var f = e.dataTransfer.files[0];
    if (f) { source = {name: f.name, kind: 'file', file: f}; startSource(); }
  });

  // For tests: open a file handle without the picker.
  window.__spc = {useHandle: useHandle, results: function () { return results; }, table: function () { return table; }, refresh: refresh, get settings() { return settings; },
    edits: function () { return edits; }, revealRow: revealRow, yellow: function () { return yellow; }, nowFlags: function () { return nowFlags; },
    selected: function () { return selectedRow; }, copyBytes: copyBytes, copyName: copyName, delPlan: function () { return delPlan; }, mixPlan: function () { return mixPlan && mixPlan.plan; }, fixPlan: function () { return fixPlan; }, simMode: simMode,
    ocapFormSheets: function () { return delPlan && ocapFormSheets(delPlan); }, ocapFormName: ocapFormName};
})();
