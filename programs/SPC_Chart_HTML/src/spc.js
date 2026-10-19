// SPC engine: control limits (I-MR or Xbar-R), out-of-control rules, capability. No DOM here.
(function () {
  'use strict';

  // Xbar-R constants by subgroup size n (2..25).
  var A2 = [0, 0, 1.880, 1.023, 0.729, 0.577, 0.483, 0.419, 0.373, 0.337, 0.308, 0.285, 0.266, 0.249, 0.235, 0.223, 0.212, 0.203, 0.194, 0.187, 0.180, 0.173, 0.167, 0.162, 0.157, 0.153];
  var D3 = [0, 0, 0, 0, 0, 0, 0, 0.076, 0.136, 0.184, 0.223, 0.256, 0.283, 0.307, 0.328, 0.347, 0.363, 0.378, 0.391, 0.403, 0.415, 0.425, 0.434, 0.443, 0.451, 0.459];
  var D4 = [0, 0, 3.267, 2.574, 2.282, 2.114, 2.004, 1.924, 1.864, 1.816, 1.777, 1.744, 1.717, 1.693, 1.672, 1.653, 1.637, 1.622, 1.608, 1.597, 1.585, 1.575, 1.566, 1.557, 1.548, 1.541];
  var D2 = [0, 0, 1.128, 1.693, 2.059, 2.326, 2.534, 2.704, 2.847, 2.970, 3.078, 3.173, 3.258, 3.336, 3.407, 3.472, 3.532, 3.588, 3.640, 3.689, 3.735, 3.778, 3.819, 3.858, 3.895, 3.931];

  var RULES = [
    {id: 'OOS', name: '규격 이탈', desc: 'USL/LSL 밖의 값'},
    {id: 'R1', name: '관리한계 이탈', desc: '1점이 UCL/LCL 밖'},
    {id: 'R2', name: 'Run', desc: 'N점 연속 중심선 한쪽', n: 7},
    {id: 'R3', name: 'Trend', desc: 'N점 연속 상승 또는 하강', n: 7},
    {id: 'R4', name: '2/3 > 2σ', desc: '연속 3점 중 2점이 같은 쪽 2σ 밖'},
    {id: 'R5', name: '4/5 > 1σ', desc: '연속 5점 중 4점이 같은 쪽 1σ 밖'},
    {id: 'R6', name: '교대 증감', desc: 'N점 연속 오르내림 반복', n: 14},
    {id: 'R7', name: '1σ 안 몰림', desc: 'N점 연속 ±1σ 안 (층별 의심)', n: 15},
    {id: 'R8', name: '1σ 밖 연속', desc: 'N점 연속 ±1σ 밖 (양쪽)', n: 8}
  ];
  var DEFAULT_ON = {OOS: true, R1: true, R2: true, R3: true, R4: true, R5: true, R6: false, R7: false, R8: false};

  function isNum(v) { return typeof v === 'number' && isFinite(v); }

  function mean(a) {
    var s = 0;
    for (var i = 0; i < a.length; i++) s += a[i];
    return a.length ? s / a.length : NaN;
  }

  function sd(a) {
    if (a.length < 2) return NaN;
    var m = mean(a), s = 0;
    for (var i = 0; i < a.length; i++) s += (a[i] - m) * (a[i] - m);
    return Math.sqrt(s / (a.length - 1));
  }

  // Per-point limit from a column: carry the last value forward, the first known value backward.
  function fillColumn(col) {
    if (!col) return null;
    var out = new Array(col.length), last = null, first = null, i;
    for (i = 0; i < col.length; i++) if (isNum(col[i])) { first = col[i]; break; }
    if (first === null) return null;
    for (i = 0; i < col.length; i++) {
      if (isNum(col[i])) last = col[i];
      out[i] = last === null ? first : last;
    }
    return out;
  }

  function constant(v, n) {
    var a = new Array(n);
    for (var i = 0; i < n; i++) a[i] = v;
    return a;
  }

  // item: {name, labels[], values[], cols: {USL:[],LSL:[],UCL:[],LCL:[],CL:[]}} (one entry per row)
  // opts: {subgroup, baseline, manual: {USL,...}, rules: {R1:true,...}, n: {R2:7,...}}
  function analyze(item, opts) {
    opts = opts || {};
    var size = Math.max(1, Math.min(25, opts.subgroup | 0 || 1));
    var manual = opts.manual || {};
    var rows = [];
    for (var r = 0; r < item.values.length; r++) if (isNum(item.values[r])) rows.push(r);

    // Points: one row each (I-MR) or n consecutive rows each (Xbar-R, an unfinished last subgroup waits).
    var points = [];
    for (var p = 0; p + size <= rows.length; p += size) {
      var idx = rows.slice(p, p + size), raw = idx.map(function (k) { return item.values[k]; });
      points.push({
        row: idx[0], rows: idx, label: item.labels[idx[0]], raw: raw, value: size > 1 ? mean(raw) : raw[0],
        range: size > 1 ? Math.max.apply(null, raw) - Math.min.apply(null, raw) : null
      });
    }
    var n = points.length, x = points.map(function (q) { return q.value; });
    var base = opts.baseline > 0 ? Math.min(n, opts.baseline | 0) : n;

    // Range chart (MR for n=1, R for n>1) and within-subgroup sigma from the baseline points.
    var rv = [], rbar, sigmaW;
    if (size === 1) {
      for (var i = 0; i < n; i++) rv.push(i ? Math.abs(x[i] - x[i - 1]) : null);
      rbar = mean(rv.slice(1, base).filter(isNum));
      sigmaW = rbar / D2[2];
    } else {
      rv = points.map(function (q) { return q.range; });
      rbar = mean(rv.slice(0, base));
      sigmaW = rbar / D2[size];
    }
    var xbar = mean(x.slice(0, base));
    var spread = size === 1 ? 3 * sigmaW : A2[size] * rbar;

    function limit(key, computed) {
      if (isNum(manual[key])) return {values: constant(manual[key], n), source: '직접 입력'};
      var col = item.cols && item.cols[key];
      if (col) {
        var per = fillColumn(points.map(function (q) { return col[q.rows[q.rows.length - 1]]; }));
        if (per) return {values: per, source: '엑셀 열'};
      }
      if (computed === null || !isFinite(computed)) return {values: null, source: '없음'};
      return {values: constant(computed, n), source: '계산'};
    }
    var usl = limit('USL', null), lsl = limit('LSL', null);
    var ucl0 = limit('UCL', null), lcl0 = limit('LCL', null);
    var cl = limit('CL', null);
    if (!cl.values && ucl0.values && lcl0.values) {
      cl = {values: ucl0.values.map(function (u, k) { return (u + lcl0.values[k]) / 2; }), source: '계산 (UCL/LCL 가운데)'};
    } else if (!cl.values && isFinite(xbar)) {
      cl = {values: constant(xbar, n), source: '계산'};
    }
    var clv = cl.values;
    var ucl = ucl0.values ? ucl0 : {values: clv && isFinite(spread) ? clv.map(function (c) { return c + spread; }) : null, source: '계산'};
    var lcl = lcl0.values ? lcl0 : {values: clv && isFinite(spread) ? clv.map(function (c) { return c - spread; }) : null, source: '계산'};

    var range = {
      values: rv,
      cl: rbar,
      ucl: size === 1 ? D4[2] * rbar : D4[size] * rbar,
      lcl: size === 1 ? 0 : D3[size] * rbar,
      name: size === 1 ? 'MR' : 'R'
    };

    var flags = rulesFor(points, x, {usl: usl.values, lsl: lsl.values, ucl: ucl.values, lcl: lcl.values, cl: clv}, opts);
    var rflags = [];
    if (opts.rules ? opts.rules.R1 !== false : true) {
      for (var j = 0; j < n; j++) if (isNum(rv[j]) && (rv[j] > range.ucl + 1e-12 || rv[j] < range.lcl - 1e-12)) rflags.push(j);
    }

    // Capability uses every individual value; within sigma from the range chart.
    var all = [];
    points.forEach(function (q) { all.push.apply(all, q.raw); });
    var m = mean(all), so = sd(all);
    var U = usl.values && n ? usl.values[n - 1] : null, L = lsl.values && n ? lsl.values[n - 1] : null;
    function cap(s) {
      if (!(s > 0)) return {cp: null, cpk: null};
      var cpu = U !== null ? (U - m) / (3 * s) : null, cpl = L !== null ? (m - L) / (3 * s) : null;
      return {
        cp: U !== null && L !== null ? (U - L) / (6 * s) : null,
        cpk: cpu !== null && cpl !== null ? Math.min(cpu, cpl) : (cpu !== null ? cpu : cpl)
      };
    }
    var cw = cap(sigmaW), co = cap(so);

    return {
      name: item.name, size: size, points: points, x: x,
      limits: {USL: usl, LSL: lsl, UCL: ucl, LCL: lcl, CL: cl},
      range: range, flags: flags, rangeFlags: rflags, events: events(flags, points),
      stats: {n: all.length, points: n, mean: m, sd: so, sigmaW: sigmaW, cp: cw.cp, cpk: cw.cpk, pp: co.cp, ppk: co.cpk, baseline: base}
    };
  }

  // flags[ruleId] = sorted point indexes where the rule's pattern is complete.
  function rulesFor(points, x, lim, opts) {
    var on = opts.rules || DEFAULT_ON, nOf = opts.n || {}, n = x.length, out = {};
    function N(id) {
      var d = RULES.filter(function (r) { return r.id === id; })[0].n;
      var v = nOf[id] | 0;
      return v >= 2 ? v : d;
    }
    function add(id, i) { (out[id] = out[id] || []).push(i); }
    var cl = lim.cl, eps = 1e-12;
    function z(i) {
      if (!cl) return 0;
      var c = cl[i], d = x[i] - c;
      if (d >= 0) return lim.ucl && lim.ucl[i] > c ? 3 * d / (lim.ucl[i] - c) : 0;
      return lim.lcl && lim.lcl[i] < c ? 3 * d / (c - lim.lcl[i]) : 0;
    }
    var zs = [], i;
    for (i = 0; i < n; i++) zs.push(z(i));

    if (on.OOS) {
      for (i = 0; i < n; i++) {
        var u = lim.usl ? lim.usl[i] : null, l = lim.lsl ? lim.lsl[i] : null;
        if (points[i].raw.some(function (v) { return (u !== null && v > u + eps) || (l !== null && v < l - eps); })) add('OOS', i);
      }
    }
    if (on.R1 && lim.ucl && lim.lcl) {
      for (i = 0; i < n; i++) if (x[i] > lim.ucl[i] + eps || x[i] < lim.lcl[i] - eps) add('R1', i);
    }
    if (!cl) return out;
    var k, c;
    if (on.R2) {
      k = N('R2'); c = 0;
      for (i = 0; i < n; i++) {
        var s = Math.sign(x[i] - cl[i]), ps = i ? Math.sign(x[i - 1] - cl[i - 1]) : 0;
        c = s === 0 ? 0 : (s === ps ? c + 1 : 1);
        if (c >= k) add('R2', i);
      }
    }
    if (on.R3) {
      k = N('R3'); var up = 1, down = 1;
      for (i = 1; i < n; i++) {
        up = x[i] > x[i - 1] ? up + 1 : 1;
        down = x[i] < x[i - 1] ? down + 1 : 1;
        if (up >= k || down >= k) add('R3', i);
      }
    }
    function mOfN(id, m, w, lim2) {
      for (i = 0; i < n; i++) {
        var side = zs[i] > lim2 ? 1 : (zs[i] < -lim2 ? -1 : 0);
        if (!side || i < w - 1) continue;
        var cnt = 0;
        for (var j = i - w + 1; j <= i; j++) if (zs[j] * side > lim2) cnt++;
        if (cnt >= m) add(id, i);
      }
    }
    if (on.R4) mOfN('R4', 2, 3, 2);
    if (on.R5) mOfN('R5', 4, 5, 1);
    if (on.R6) {
      // run = alternating steps ending at i; N points are N-1 steps.
      k = N('R6'); c = 0; var prev = 0;
      for (i = 1; i < n; i++) {
        var d = Math.sign(x[i] - x[i - 1]);
        c = d === 0 ? 0 : (prev && d === -prev ? c + 1 : 1);
        prev = d;
        if (c + 1 >= k) add('R6', i);
      }
    }
    if (on.R7) {
      k = N('R7'); c = 0;
      for (i = 0; i < n; i++) { c = Math.abs(zs[i]) < 1 ? c + 1 : 0; if (c >= k) add('R7', i); }
    }
    if (on.R8) {
      k = N('R8'); c = 0;
      for (i = 0; i < n; i++) { c = Math.abs(zs[i]) > 1 ? c + 1 : 0; if (c >= k) add('R8', i); }
    }
    return out;
  }

  // Consecutive flagged points of one rule are one event (a 20-point run is one OCAP row).
  function events(flags, points) {
    var list = [];
    Object.keys(flags).forEach(function (id) {
      var idx = flags[id], start = null;
      for (var k = 0; k < idx.length; k++) {
        if (start === null) start = idx[k];
        if (k === idx.length - 1 || idx[k + 1] !== idx[k] + 1) {
          list.push({rule: id, start: start, end: idx[k], label: points[start].label, endLabel: points[idx[k]].label, value: points[start].value});
          start = null;
        }
      }
    });
    list.sort(function (a, b) { return a.start - b.start || order(a.rule) - order(b.rule); });
    return list;
  }

  function order(id) {
    for (var i = 0; i < RULES.length; i++) if (RULES[i].id === id) return i;
    return 99;
  }

  // Rules whose rows the data table marks yellow and the recommended value must clear:
  // OCAP (spec limit, control limit) and 7 run (run on one side, trend).
  var FIX_RULES = ['OOS', 'R1', 'R2', 'R3'];

  function flagged(res, rules) {
    var s = {};
    rules.forEach(function (id) { (res.flags[id] || []).forEach(function (i) { s[i] = 1; }); });
    return s;
  }

  function decimals(values, sigma) {
    var d = 0;
    values.forEach(function (v) {
      if (!isNum(v)) return;
      var m = String(+v.toPrecision(12)).match(/\.(\d+)$/);  // 6.9 + 0.03 -> 6.93, not 6.930000000000001
      if (m) d = Math.max(d, m[1].length);
    });
    if (sigma > 0) d = Math.max(d, Math.ceil(-Math.log10(sigma)) + 1);
    return Math.max(0, Math.min(10, d));
  }

  // Value for point pj that clears point pi of `rules` without any other point starting to break them
  // (pj = pi normally; another point of the same run / trend when pi alone cannot be fixed). Tried in order:
  // moving toward CL (staying inside ±2σ and the spec), just across CL, then anything inside ±2σ nearest
  // the old value; never below opts.min when given. null if nothing works.
  function valueFor(item, opts, res, before, pi, pj, rules) {
    var L = res.limits, cl = L.CL.values ? L.CL.values[pj] : res.stats.mean, sw = res.stats.sigmaW;
    var up = L.UCL.values ? (L.UCL.values[pj] - cl) / 3 : sw, dn = L.LCL.values ? (cl - L.LCL.values[pj]) / 3 : sw;
    if (!(up > 0)) up = sw;
    if (!(dn > 0)) dn = sw;
    if (!isNum(cl) || !(up > 0) || !(dn > 0)) return null;
    var row = res.points[pj].row, x0 = item.values[row], d = x0 - cl, side = d >= 0 ? 1 : -1, other = side > 0 ? dn : up;
    var digits = decimals(item.values, Math.min(up, dn)), f = Math.pow(10, digits);
    var usl = L.USL.values ? L.USL.values[pj] : null, lsl = L.LSL.values ? L.LSL.values[pj] : null;
    var cands = [], t;
    for (t = 1; t <= 9; t++) cands.push(cl + d * (1 - t / 10));
    [0.25, 0.5, 0.75, 1].forEach(function (z) { cands.push(cl - side * z * other); });
    cands.push(cl);
    var grid = [];
    for (t = -8; t <= 8; t++) grid.push(cl + (t > 0 ? up : dn) * t / 4);
    grid.sort(function (a, b) { return Math.abs(a - x0) - Math.abs(b - x0); });
    cands = cands.concat(grid);
    var tried = {}, eps = 1e-9 * (Math.abs(cl) + up + dn);
    for (var c = 0; c < cands.length; c++) {
      var v = Math.round(cands[c] * f) / f;
      if (tried[v] || v === x0) continue;
      tried[v] = 1;
      if (v - cl > 2 * up + eps || cl - v > 2 * dn + eps) continue;
      if ((usl !== null && v > usl) || (lsl !== null && v < lsl)) continue;
      if (isNum(opts.min) && v < opts.min) continue;  // e.g. a sigma below 0
      var vals = item.values.slice();
      vals[row] = v;
      var after = flagged(analyze(Object.assign({}, item, {values: vals}), opts), rules);
      if (after[pi] || Object.keys(after).some(function (i) { return !before[i]; })) continue;
      return {value: v, z: Math.abs(v - x0) / (v >= x0 ? up : dn)};
    }
    return null;
  }

  // Recommended change for the point on item.values[row] (I-MR only): {row, value}, where row is that row,
  // or — when no value of that point works (e.g. moving the 7th point of a run across CL starts a 7-point
  // trend with the next point) — another point of the same run / trend, the one needing the smallest move.
  // null if the point is fine or nothing works.
  function suggestChange(item, opts, row, rules) {
    if ((opts.subgroup | 0) > 1) return null;
    var res = analyze(item, opts), pi = -1;
    for (var k = 0; k < res.points.length; k++) if (res.points[k].row === row) { pi = k; break; }
    if (pi < 0) return null;
    var before = flagged(res, rules);
    if (!before[pi]) return null;
    var own = valueFor(item, opts, res, before, pi, pi, rules);
    if (own) return {row: row, value: own.value};
    var inRun = ['R2', 'R3'].filter(function (id) { return rules.indexOf(id) >= 0 && (res.flags[id] || []).indexOf(pi) >= 0; });
    var span = 0;
    inRun.forEach(function (id) { span = Math.max(span, ruleN(id, opts) - 1); });
    var best = null;
    for (var j = pi - 1; j >= Math.max(0, pi - span); j--) {
      var got = valueFor(item, opts, res, before, pi, j, rules);
      if (got && (!best || got.z < best.z)) best = {row: res.points[j].row, value: got.value, z: got.z};
    }
    return best ? {row: best.row, value: best.value} : null;
  }

  function ruleN(id, opts) {
    var d = RULES.filter(function (r) { return r.id === id; })[0].n, v = (opts.n || {})[id] | 0;
    return v >= 2 ? v : d;
  }

  // Recommended value for item.values[row] itself (null if only another point could fix it).
  function suggest(item, opts, row, rules) {
    var ch = suggestChange(item, opts, row, rules);
    return ch && ch.row === row ? ch.value : null;
  }

  // Every point breaking `rules`, oldest first, gets its recommended change (a fixed run point usually
  // clears the rest of the run). Returns {changes: [{row, value}], failed: point count without a value}.
  function fixAll(item, opts, rules) {
    var vals = item.values.slice(), changes = [], failed = {};
    for (var guard = 0; guard <= vals.length; guard++) {
      var it = Object.assign({}, item, {values: vals}), res = analyze(it, opts), f = flagged(res, rules);
      var next = Object.keys(f).map(Number).sort(function (a, b) { return a - b; }).filter(function (i) { return !failed[i]; })[0];
      if (next === undefined) break;
      var ch = suggestChange(it, opts, res.points[next].row, rules);
      if (!ch) { failed[next] = 1; continue; }
      vals = vals.slice();
      vals[ch.row] = ch.value;
      changes = changes.filter(function (c) { return c.row !== ch.row; });
      changes.push({row: ch.row, value: ch.value});
    }
    return {changes: changes, failed: Object.keys(failed).length};
  }

  window.SPC = {RULES: RULES, DEFAULT_ON: DEFAULT_ON, FIX_RULES: FIX_RULES, analyze: analyze, fillColumn: fillColumn, flagged: flagged, events: events, suggest: suggest, suggestChange: suggestChange, fixAll: fixAll, mean: mean, sd: sd};
})();
