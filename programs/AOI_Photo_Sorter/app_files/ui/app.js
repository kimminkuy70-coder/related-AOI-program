'use strict';
// AOI Photo Sorter screen.
// Every key is handled here, synchronously: one key = one state change, in arrival
// order, without waiting for Python. Python only receives batched changes (api/sync).
// Rules that keep fast key mashing safe:
//  - a key acts only after the current photo has been painted: drawn, and the frame
//    holding it produced (rAF; the next key event is handled after that frame went to
//    the compositor), so Space never marks, and → never skips, a photo not on screen;
//  - → to a photo that is still loading moves and shows "불러오는 중"; further keys
//    wait until it is painted (keys are dropped, never queued);
//  - Space = GOOD (or back to REJECT if it already was GOOD) and the next photo; it counts
//    only after the photo has been on screen space_min_view_ms, so a bouncing or doubled
//    Space never marks the photo that just appeared; auto-repeat of Space is ignored,
//    arrow auto-repeat too unless arrow_repeat;
//  - keys are read by physical position (event.code): Korean IME / CapsLock do not matter.
// Extra GOOD review (v4): the same screens over only the photos still REJECT in the previous
// result files (S.mode 'extra'); the old GOOD photos are kept by Python and never shown.
// Network folder outages: Python reports offline/stalled and an epoch that grows whenever
// failures are forgotten (reconnect, F5). A new epoch reloads every failed photo here.

const $ = id => document.getElementById(id);
const fmt = n => Number(n || 0).toLocaleString('ko-KR');
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const bridge = () => (window.pywebview && window.pywebview.api && window.pywebview.api.choose_folder) ? window.pywebview.api : null;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const now = () => performance.now();
const labelOf = p => (String(p).split(/[\\/]+/).filter(Boolean).pop() || p);

let cfg = {arrow_repeat: false, space_min_view_ms: 120, decode_ahead: 5, decode_behind: 3};

async function api(name, body) {
  const init = body === undefined ? {cache: 'no-store'}
    : {method: 'POST', cache: 'no-store', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)};
  const r = await fetch('api/' + name, init);
  const type = r.headers.get('Content-Type') || '';
  const data = type.includes('json') ? await r.json() : {ok: false, error: await r.text()};
  data.status = r.status;
  return data;
}

// ------------------------------------------------------------------ screens / modal
let page = 'start';  // current screen id
function show(name) {
  page = name;
  document.querySelectorAll('.screen').forEach(s => s.classList.toggle('show', s.id === name));
  if (document.activeElement && document.activeElement !== document.body && name !== 'start') document.activeElement.blur();
  if (name === 'sort') resize();
  if (name === 'review') { renderReview(); renderGrid(true); }
  renderNet();
}

let modal = null;
function ask(title, text, buttons) {
  return new Promise(resolve => {
    $('mTitle').textContent = title;
    $('mText').textContent = text;
    const box = $('mButtons');
    box.innerHTML = '';
    buttons.forEach(b => {
      const el = document.createElement('button');
      el.textContent = b.label;
      el.className = b.primary ? 'primary' : 'ghost';
      el.tabIndex = -1;
      el.onmousedown = e => e.preventDefault();
      el.onclick = () => close(b.value);
      box.appendChild(el);
    });
    const close = value => { modal = null; $('modal').classList.add('hidden'); resolve(value); };
    modal = {buttons, close};
    $('modal').classList.remove('hidden');
    if (document.activeElement) document.activeElement.blur();
  });
}
const OK = [{label: '확인 (Enter)', value: 'ok', keys: ['Enter', 'NumpadEnter', 'Escape', 'Space'], primary: true}];
function modalKey(e) {
  e.preventDefault();
  e.stopPropagation();
  if (e.repeat) return;
  const hit = modal.buttons.find(b => (b.keys || []).includes(e.code));
  if (hit) modal.close(hit.value);
}

// ------------------------------------------------------------------ start screen
let checkTimer = null, checkSeq = 0, lastCheck = null;

async function loadHome() {
  const home = await api('home');
  Object.assign(cfg, home.config || {});
  if (!$('output').value) $('output').value = home.output_dir || '';
  renderRecent(home.recent || []);
  scheduleCheck();
}

function renderRecent(items) {
  const box = $('recent');
  if (!items.length) { box.innerHTML = '<small class="muted">없음</small>'; return; }
  box.innerHTML = '';
  items.forEach(item => {
    const s = item.summary;
    const info = !s ? '' : s.saved ? `저장 완료 · GOOD ${fmt(s.saved.good)}` : `${fmt(s.seen)} / ${fmt(s.total)} 확인 · GOOD ${fmt(s.good)}`;
    const el = document.createElement('button');
    el.innerHTML = `<span class="path">${esc(item.folder)}</span><span class="muted">${esc(info)}</span>`;
    el.onclick = () => { $('folder').value = item.folder; $('output').value = item.output_dir || $('output').value; scheduleCheck(); };
    box.appendChild(el);
  });
}

function setMsg(id, text, kind) {
  const el = $(id);
  el.textContent = text;
  el.className = 'msg' + (kind ? ' ' + kind : '');
}

function scheduleCheck() {
  clearTimeout(checkTimer);
  $('startBtn').disabled = true;
  checkTimer = setTimeout(runCheck, 300);
}

async function runCheck() {
  const seq = ++checkSeq;
  const folder = $('folder').value.trim(), output = $('output').value.trim();
  if (folder) setMsg('folderMsg', '확인 중…');
  if (output) setMsg('outputMsg', '확인 중…');
  let r;
  try { r = await api('check', {folder, output_dir: output}); } catch (err) { return; }
  if (seq !== checkSeq) return;
  lastCheck = r;
  setMsg('folderMsg', !folder ? '' : r.folder_ok ? '✓ 폴더 확인됨' : r.folder_msg, r.folder_ok ? 'ok' : 'bad');
  setMsg('outputMsg', !output ? '' : r.output_ok ? '✓ 쓰기 가능' : r.output_msg, r.output_ok ? 'ok' : 'bad');
  $('files').innerHTML = folder && r.files[0]
    ? `저장될 파일: <b>${esc(r.files[0])}</b> / <b>${esc(r.files[1])}</b>` +
      (r.existing.length ? ` <span class="warn-text">— 이미 있음 (저장할 때 덮어쓸지 묻습니다)</span>` : '')
    : '';
  const s = r.folder_ok ? r.session : null;
  $('resume').classList.toggle('hidden', !s);
  if (s) {
    $('resumeText').textContent = `이전 작업: ${fmt(s.seen)} / ${fmt(s.total)} 확인 · GOOD ${fmt(s.good)}` +
      (s.saved ? ` · 저장 완료(${s.saved.time})` : '') + (s.updated ? ` · ${s.updated}` : '');
  }
  $('startBtn').textContent = s ? '이어하기 (Enter)' : '시작 (Enter)';
  $('startBtn').disabled = !(r.folder_ok && r.output_ok);
  const res = r.folder_ok && r.output_ok ? r.results : null, x = res ? r.extra_session : null;
  $('extra').classList.toggle('hidden', !res);
  $('extraFresh').classList.toggle('hidden', !x);
  if (res) {
    $('extraText').textContent = `이전 결과: GOOD ${fmt(res.good)} / REJECT ${fmt(res.reject)} (저장 ${res.time})` +
      (x ? ` · 추가 검토 중: ${fmt(x.seen)} / ${fmt(x.total)} 확인, 추가 GOOD ${fmt(x.good)}` : '');
    $('extraBtn').textContent = x ? '추가 GOOD 검토 이어하기' : '추가 GOOD 검토 시작';
  }
  $('extraBtn').disabled = !res;
}

async function start(resume, mode = '') {
  if ($('startBtn').disabled) return;
  $('startBtn').disabled = true;
  const r = await api('start', {folder: $('folder').value.trim(), output_dir: $('output').value.trim(), resume, mode});
  if (!r.ok) { await ask('시작할 수 없습니다', r.error || '알 수 없는 오류', OK); scheduleCheck(); return; }
  $('loadMsg').textContent = '사진 목록 읽는 중…';
  $('loadDetail').textContent = $('folder').value.trim();
  show('loading');
  pollLoad(r.job);
}

async function pollLoad(job) {
  let s;
  try { s = await api('state'); } catch (err) { setTimeout(() => pollLoad(job), 300); return; }
  if (s.job !== job || page !== 'loading') return;
  if (s.phase === 'scanning') {
    $('loadMsg').textContent = `사진 목록 읽는 중… ${fmt(s.found)}장`;
    setTimeout(() => pollLoad(job), 100);
  } else if (s.phase === 'error') {
    await ask('사진을 불러올 수 없습니다', s.message, OK);
    show('start');
    scheduleCheck();
  } else if (s.phase === 'ready') {
    beginSort(s);
  }
}

async function pick(field) {
  const b = bridge();
  if (!b) return;
  const path = await b.choose_folder($(field).value.trim());
  if (path) { $(field).value = path; scheduleCheck(); }
}

// ------------------------------------------------------------------ sorting state
const S = {
  job: null, names: [], n: 0, good: new Uint8Array(0), seen: new Uint8Array(0), failed: new Uint8Array(0),
  goodCount: 0, seenCount: 0, folder: '', output: '', files: ['', ''], mode: '', extra: null, fresh: new Uint8Array(0),
  list: null, listName: '', pos: 0, allPos: 0, painted: -1, drawToken: 0,
  paintedAt: 0, lastMoveAt: 0, last: '', note: '', noteTimer: null, zoom: null, epoch: 0,
};
const trace = [];  // recent accepted/ignored inputs and paints (also read by the E2E test)
function record(entry) { entry.t = now(); trace.push(entry); if (trace.length > 20000) trace.splice(0, 5000); }
window.__sorter = {S, trace, cfg, flush: () => flushSync(), current: () => cur()};

const len = () => S.list ? S.list.length : S.n;
const idxAt = p => S.list ? S.list[p] : p;
const cur = () => idxAt(S.pos);

function beginSort(s) {
  dropAll();
  S.job = s.job; S.names = s.names; S.n = s.names.length;
  S.good = new Uint8Array(S.n); s.good.forEach(i => { S.good[i] = 1; });
  S.goodCount = s.good.length;
  S.seen = Uint8Array.from(s.seen, c => c === '1' ? 1 : 0);
  S.seenCount = S.seen.reduce((a, b) => a + b, 0);
  S.failed = new Uint8Array(S.n);
  S.folder = s.folder; S.output = s.output_dir; S.files = s.files;
  S.mode = s.mode || ''; S.extra = s.extra || null;
  S.fresh = new Uint8Array(S.n); (S.extra ? S.extra.fresh : []).forEach(i => { S.fresh[i] = 1; });
  S.list = null; S.listName = ''; S.pos = Math.min(Math.max(0, s.cursor || 0), S.n - 1); S.allPos = S.pos;
  S.painted = -1; S.zoom = null; S.last = '';
  syncSeq = s.seq || 0; pendingGood.clear(); pendingSeen.clear(); lastStats = s.stats || null;
  S.epoch = lastStats ? lastStats.epoch : 0;
  R.items = null;
  $('hFolder').textContent = labelOf(S.folder);
  $('hOut').textContent = '저장: ' + S.output;
  show('sort');
  if (s.added || s.removed) note(`폴더 변경: 추가 ${fmt(s.added)}장(미확인), 삭제 ${fmt(s.removed)}장 제외`, 6000);
  else if (S.extra) {
    const fresh = S.extra.fresh.length, missing = S.extra.missing;
    note(`추가 GOOD 검토: 이전 REJECT ${fmt(S.n - fresh)}장` + (fresh ? ` + 신규 ${fmt(fresh)}장` : '') +
      ` · 기존 GOOD ${fmt(S.extra.base_good)}장 유지` + (missing ? ` · 폴더에 없는 ${fmt(missing)}장 제외` : ''), 6000);
  }
  present();
  pump();
}

// ------------------------------------------------------------------ decode buffer
// Photos around the position are fetched and decoded off the main thread
// (createImageBitmap) before they are needed, so paging only draws a ready bitmap.
const buf = new Map();
let inflight = 0;
const MAX_INFLIGHT = 4;  // leaves browser connections free for api/sync

function wanted() {
  const out = [S.pos];
  for (let k = 1; k <= cfg.decode_ahead; k++) out.push(S.pos + k);
  for (let k = 1; k <= cfg.decode_behind; k++) out.push(S.pos - k);
  return out.filter(p => p >= 0 && p < len()).map(idxAt);
}

function pump() {
  if (!S.job) return;
  const want = wanted();
  const keep = new Set(want);
  for (const [i, e] of buf) if (!keep.has(i)) drop(i, e);
  const current = cur();
  for (const i of want) {
    if (buf.has(i)) continue;
    if (inflight >= MAX_INFLIGHT && i !== current) break;
    load(i);
  }
}

function drop(i, e) {
  if (e.ctrl) e.ctrl.abort();
  if (e.bmp) e.bmp.close();
  if (e.full) e.full.close();
  buf.delete(i);
}
function dropAll() { for (const [i, e] of [...buf]) drop(i, e); }

function screenPixels() { return window.screen.width * window.screen.height * (devicePixelRatio || 1) ** 2 || 2e6; }

async function decode(blob, full) {
  const bmp = await createImageBitmap(blob);
  const limit = Math.max(screenPixels() * 4, 16e6);
  if (full || bmp.width * bmp.height <= limit) return {bmp, w: bmp.width, h: bmp.height, reduced: false};
  // Very large photo: keep a screen-sized copy (memory), 100% view re-decodes the original.
  const s = Math.sqrt(limit / (bmp.width * bmp.height));
  const small = await createImageBitmap(bmp, {resizeWidth: Math.round(bmp.width * s), resizeHeight: Math.round(bmp.height * s), resizeQuality: 'high'});
  const out = {bmp: small, w: bmp.width, h: bmp.height, reduced: true};
  bmp.close();
  return out;
}

async function load(i) {
  const e = {state: 'loading', ctrl: new AbortController(), job: S.job};
  buf.set(i, e);
  inflight++;
  try {
    const r = await fetch(`img/${S.job}/${i}`, {signal: e.ctrl.signal, cache: 'no-store'});
    if (!r.ok) {
      e.state = 'error';
      e.kind = r.headers.get('X-Photo-Error') === 'offline' ? 'offline' : 'read';
      e.msg = (await r.text()) || ('HTTP ' + r.status);
    } else {
      const blob = await r.blob();
      try {
        Object.assign(e, await decode(blob, false));
        e.state = 'ready';
      } catch (err) {
        e.state = 'error'; e.kind = 'decode'; e.msg = '손상되었거나 지원하지 않는 형식입니다.';
      }
    }
  } catch (err) {
    if (err.name !== 'AbortError') { e.state = 'error'; e.kind = 'read'; e.msg = String(err.message || err); }
  } finally {
    inflight--;
    e.ctrl = null;
    if (buf.get(i) !== e) {
      if (e.bmp) e.bmp.close();
    } else if (page === 'sort' && i === cur() && S.painted !== i) {
      present();
    }
    pump();
  }
}

// ------------------------------------------------------------------ drawing
const canvas = $('view');
const ctx = canvas.getContext('2d', {alpha: false});

function resize() {
  const stage = $('stage');
  const dpr = devicePixelRatio || 1;
  const w = Math.max(1, Math.round(stage.clientWidth * dpr)), h = Math.max(1, Math.round(stage.clientHeight * dpr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  redraw();
}
new ResizeObserver(() => { if (page === 'sort') resize(); }).observe($('stage'));

function geometry(e) {
  const img = (S.zoom && e.full) ? e.full : e.bmp;
  const fit = Math.min(canvas.width / e.w, canvas.height / e.h);
  const scale = S.zoom ? S.zoom.scale : fit;  // scale in canvas px per original photo px
  const cx = S.zoom ? S.zoom.cx : e.w / 2, cy = S.zoom ? S.zoom.cy : e.h / 2;
  return {img, fit, scale, dx: canvas.width / 2 - cx * scale, dy: canvas.height / 2 - cy * scale, dw: e.w * scale, dh: e.h * scale};
}

function draw(e) {
  ctx.fillStyle = '#05080f';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!e || e.state !== 'ready') return;
  const g = geometry(e);
  ctx.imageSmoothingEnabled = g.scale < 2;  // pixel view when zoomed in
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(g.img, g.dx, g.dy, g.dw, g.dh);
}

function redraw() {
  if (page !== 'sort' || !S.job) return;
  const e = buf.get(cur());
  draw(e && e.state === 'ready' ? e : null);
}

function setCard(title, text, error) {
  $('cardTitle').textContent = title;
  $('cardText').textContent = text || '';
  $('card').classList.toggle('error', !!error);
  $('card').classList.remove('hidden');
}

// Draws the current photo and marks it painted once the frame that shows it is produced.
function present(keyT) {
  const i = cur();
  const e = buf.get(i);
  const token = ++S.drawToken;
  S.painted = -1;
  if (!e || e.state === 'loading') {
    draw(null);
    setCard('불러오는 중…', S.names[i]);
    hud();
    return;
  }
  if (e.state === 'error') {
    draw(null);
    if (e.kind === 'offline') setCard('네트워크 폴더 연결 끊김', S.names[i] + '\n연결되면 자동으로 다시 불러옵니다. F5: 지금 다시 시도', true);
    else if (e.kind === 'read') setCard('읽기 실패', e.msg + '\nF5 (또는 R): 새로고침', true);
    else setCard('표시할 수 없는 사진', e.msg, true);
  } else {
    $('card').classList.add('hidden');
    draw(e);
  }
  hud();
  requestAnimationFrame(t1 => {
    if (token !== S.drawToken) return;
    S.painted = i;
    S.paintedAt = now();
    record({type: 'paint', i, keyT, frame: t1, ok: e.state === 'ready'});
    if (e.state === 'ready') {
      if (!S.seen[i]) { S.seen[i] = 1; S.seenCount++; pendingSeen.add(i); scheduleSync(); }
      S.failed[i] = 0;
    } else if (e.kind === 'read' || e.kind === 'offline') {
      S.failed[i] = 1;
    }
    hud();
  });
}

// ------------------------------------------------------------------ HUD (one update per frame)
let hudQueued = false;
function hud() {
  if (hudQueued) return;
  hudQueued = true;
  requestAnimationFrame(() => { hudQueued = false; renderHud(); });
}
// Only values that changed are written, so a key press costs a few text nodes at most.
const shown = new Map();
function put(id, prop, value) {
  const key = id + '.' + prop;
  if (shown.get(key) === value) return;
  shown.set(key, value);
  const el = $(id);
  if (prop === 'text') el.textContent = value;
  else if (prop === 'class') el.className = value;
  else el.style[prop] = value;
}
function renderHud() {
  if (page !== 'sort' || !S.job) return;
  const i = cur(), good = !!S.good[i];
  const extra = S.mode === 'extra';
  put('hPos', 'text', extra && !S.list ? `REJECT ${fmt(len())}장 중 ${fmt(S.pos + 1)}번째` : `${fmt(S.pos + 1)} / ${fmt(len())}`);
  put('hGoodLabel', 'text', extra ? '추가 GOOD' : 'GOOD');
  put('hExtra', 'class', extra ? 'mode extra' : 'mode extra hidden');
  put('fNew', 'class', S.fresh[i] ? 'tag new' : 'tag new hidden');
  put('hSeen', 'text', S.list ? '' : `확인 ${(S.seenCount / S.n * 100).toFixed(1)}%`);
  put('hGood', 'text', fmt(S.goodCount));
  put('hBar', 'transform', `scaleX(${(S.list ? (S.pos + 1) / len() : S.seenCount / S.n).toFixed(3)})`);
  put('hMode', 'class', S.list ? 'mode' : 'mode hidden');
  put('hMode', 'text', S.listName + ' — Esc: 메뉴');
  put('stage', 'class', 'stage' + (good ? ' good' : '') + (S.zoom ? ' zoomed' : ''));
  put('fName', 'text', S.names[i] || '');
  put('fTag', 'text', good ? 'GOOD' : 'REJECT');
  put('fTag', 'class', good ? 'tag good' : 'tag');
  put('fNote', 'text', S.note);
  put('fLast', 'text', S.last ? '직전: ' + S.last : '');
  let dot = 'dot';
  if (!S.list && lastStats) {
    const remain = S.n - 1 - lastStats.cursor;
    const need = Math.min(20, remain);
    dot += lastStats.ready_ahead >= need ? ' green' : lastStats.ready_ahead >= Math.min(3, remain) ? ' yellow' : ' red';
  }
  if (lastStats && (lastStats.offline || lastStats.stalled)) dot = lastStats.offline ? 'dot red' : 'dot yellow';
  put('hDot', 'class', dot);
}

// ------------------------------------------------------------------ network folder state
function applyStats(st) {
  if (!st) return;
  lastStats = st;
  if (st.epoch !== S.epoch) { S.epoch = st.epoch; reloadFailed(); }
  renderNet();
  hud();
}

// After a reconnect or F5: photos that failed are fetched again, the one on screen first.
function reloadFailed() {
  let current = false;
  for (const [i, e] of [...buf]) {
    if (e.state !== 'error') continue;
    drop(i, e);
    if (i === cur()) current = true;
  }
  if (page === 'sort' && current) present();
  pump();
  if (page === 'review') { R.cells.forEach(el => el.remove()); R.cells.clear(); renderGrid(false); }
}

function renderNet() {
  const st = lastStats;
  const on = !!(st && S.job && (page === 'sort' || page === 'review') && (st.offline || st.stalled));
  put('net', 'class', !on ? 'netbar hidden' : st.offline ? 'netbar off' : 'netbar slow');
  put('net', 'text', !on ? '' : st.offline ? '네트워크 폴더 연결 끊김 — 연결되면 자동으로 이어집니다 (F5: 지금 다시 시도)'
    : '네트워크 폴더 응답 대기 중…');
}

let refreshing = false;
async function refreshNow() {
  if (!S.job || refreshing) return;
  refreshing = true;
  note('새로고침: 네트워크 폴더에 다시 연결합니다…');
  try {
    const r = await api('refresh', {job: S.job});
    if (r.ok) applyStats(r.stats);
  } catch (err) {
    note('새로고침 실패: ' + (err.message || err));
  } finally {
    refreshing = false;
  }
}

function note(text, ms = 1500) {
  S.note = text;
  clearTimeout(S.noteTimer);
  S.noteTimer = setTimeout(() => { S.note = ''; hud(); }, ms);
  hud();
}

// ------------------------------------------------------------------ actions
function move(d, e) {
  const key = d > 0 ? 'right' : 'left';
  const from = cur();
  if (e && e.repeat && (!cfg.arrow_repeat || now() - S.lastMoveAt < 100)) {  // hold-to-page (option): max 10 photos/s
    record({type: 'ignored', key, reason: 'repeat', i: from});
    return;
  }
  // Forward never leaves a photo that has not been on screen; backward only revisits.
  if (d > 0 && S.painted !== from) { record({type: 'ignored', key, reason: 'not-painted', i: from}); note('불러오는 중…'); return; }
  const np = S.pos + d;
  if (np < 0 || np >= len()) {
    record({type: 'ignored', key, reason: 'edge', i: from});
    if (np < 0) note('첫 사진입니다');
    else lastPhotoNote();
    return;
  }
  step(d, key, e ? e.timeStamp : undefined);
}

function step(d, key, keyT) {
  const from = cur();
  S.pos += d;
  S.lastMoveAt = now();
  S.zoom = null;
  record({type: 'move', key, from, to: cur()});
  present(keyT);
  pump();
  cursorChanged();
}

function lastPhotoNote() {
  note(S.list ? '마지막 사진입니다 — Esc: 메뉴' : '마지막 사진입니다 — Enter: 확인 화면으로', 3000);
}

// Space: GOOD (REJECT again if it already was GOOD), then straight to the next photo.
function goodAndNext(e) {
  const i = cur();
  if (e.repeat) { record({type: 'ignored', key: 'space', reason: 'repeat', i}); return; }
  if (S.painted !== i) { record({type: 'ignored', key: 'space', reason: 'not-painted', i}); note('불러오는 중…'); return; }
  if (now() - S.paintedAt < cfg.space_min_view_ms) { record({type: 'ignored', key: 'space', reason: 'too-soon', i}); return; }
  toggle(i);
  if (S.pos + 1 < len()) step(1, 'space', e.timeStamp);
  else { hud(); lastPhotoNote(); }
}

function jump(p) {
  if (p === S.pos) return;
  S.pos = Math.max(0, Math.min(len() - 1, p));
  S.zoom = null;
  record({type: 'jump', to: cur()});
  present();
  pump();
  cursorChanged();
}

function workPos() {
  if (S.list) return len() - 1;
  const i = S.seen.indexOf(0);
  return i < 0 ? S.n - 1 : i;
}

function toggle(i) {
  S.good[i] ^= 1;
  S.goodCount += S.good[i] ? 1 : -1;
  pendingGood.set(i, S.good[i]);
  scheduleSync();
  S.last = `${S.names[i]} → ${S.good[i] ? 'GOOD' : 'GOOD 해제'}`;
  record({type: 'toggle', i, value: S.good[i], painted: S.painted});
}

// ---- zoom: F toggles 100% / fit, wheel zooms at the pointer, drag pans
async function ensureFull(e) {
  if (!e.reduced || e.full || e.loadingFull) return;
  e.loadingFull = true;
  try {
    const r = await fetch(`img/${S.job}/${cur()}`, {cache: 'no-store'});
    const out = await decode(await r.blob(), true);
    if (buf.get(cur()) === e) { e.full = out.bmp; redraw(); } else out.bmp.close();
  } catch (err) { /* keep the reduced copy */ }
}
function setZoom(scale, px, py) {
  const e = buf.get(cur());
  if (!e || e.state !== 'ready') return;
  const g = geometry(e);
  if (scale <= g.fit * 1.0001) { S.zoom = null; redraw(); hud(); return; }
  scale = Math.min(scale, 32);
  // keep the photo point under (px, py) in place
  const ix = (px - g.dx) / g.scale, iy = (py - g.dy) / g.scale;
  S.zoom = {scale, cx: ix - (px - canvas.width / 2) / scale, cy: iy - (py - canvas.height / 2) / scale};
  ensureFull(e);
  redraw();
  hud();
}
function toggleZoom() {
  if (S.zoom) { S.zoom = null; redraw(); hud(); return; }
  const e = buf.get(cur());
  if (!e || e.state !== 'ready') return;
  const fit = geometry(e).fit;
  setZoom(fit >= 1 ? fit * 2 : 1, canvas.width / 2, canvas.height / 2);  // 100%, or 2x for photos smaller than the screen
}
$('stage').addEventListener('wheel', ev => {
  ev.preventDefault();
  const e = buf.get(cur());
  if (!e || e.state !== 'ready') return;
  const dpr = devicePixelRatio || 1;
  const g = geometry(e);
  setZoom(g.scale * (ev.deltaY < 0 ? 1.25 : 0.8), ev.offsetX * dpr, ev.offsetY * dpr);
}, {passive: false});
let drag = null;
$('stage').addEventListener('mousedown', ev => { if (S.zoom) drag = {x: ev.clientX, y: ev.clientY}; ev.preventDefault(); });
window.addEventListener('mouseup', () => { drag = null; });
window.addEventListener('mousemove', ev => {
  if (!drag || !S.zoom) return;
  const dpr = devicePixelRatio || 1;
  S.zoom.cx -= (ev.clientX - drag.x) * dpr / S.zoom.scale;
  S.zoom.cy -= (ev.clientY - drag.y) * dpr / S.zoom.scale;
  drag = {x: ev.clientX, y: ev.clientY};
  redraw();
});

// ---- sub-lists: GOOD only / unseen only, browsed with the same keys
function enterList(list, startPos, name) {
  if (!list.length) return;
  if (!S.list) S.allPos = S.pos;
  S.list = list.slice();
  S.listName = name;
  S.pos = Math.max(0, Math.min(list.length - 1, startPos));
  S.zoom = null;
  dropAll();
  show('sort');
  present();
  pump();
  cursorChanged();
}
function leaveList() {
  S.list = null;
  S.listName = '';
  S.pos = S.allPos;
  dropAll();
}

async function openMenu() {
  const refresh = {label: '새로고침 (F5)', value: 'refresh', keys: ['F5']};
  const buttons = S.list
    ? [{label: '확인 화면으로 (Enter)', value: 'review', keys: ['Enter', 'NumpadEnter'], primary: true}, refresh, {label: '계속 (Esc)', value: 'stay', keys: ['Escape']}]
    : [{label: '확인 화면으로 (Enter)', value: 'review', keys: ['Enter', 'NumpadEnter'], primary: true}, refresh,
       {label: '처음 화면으로', value: 'home'}, {label: '계속 (Esc)', value: 'stay', keys: ['Escape']}];
  const text = S.list ? `${S.listName}: ${fmt(S.pos + 1)} / ${fmt(len())}`
    : `확인 ${fmt(S.seenCount)} / ${fmt(S.n)} · ${S.mode === 'extra' ? '추가 ' : ''}GOOD ${fmt(S.goodCount)}\n진행 상황은 자동 저장됩니다.`;
  const a = await ask('메뉴', text, buttons);
  if (a === 'review') { const keep = !!S.list; if (S.list) leaveList(); openReview(keep); }
  else if (a === 'home') { await flushSync(); await api('new', {}); S.job = null; dropAll(); show('start'); loadHome(); }
  else if (a === 'refresh') refreshNow();
}

// ------------------------------------------------------------------ sync with Python (batched)
const pendingGood = new Map();
const pendingSeen = new Set();
let syncSeq = 0, syncTimer = null, syncBusy = false, cursorDirty = false, lastStats = null;

function cursorChanged() { cursorDirty = true; scheduleSync(); }
function scheduleSync(delay = 150) { if (!syncTimer) syncTimer = setTimeout(doSync, delay); }

async function doSync() {
  syncTimer = null;
  if (!S.job) return;
  if (syncBusy) { scheduleSync(); return; }  // one request in flight at a time keeps them in order
  if (!pendingGood.size && !pendingSeen.size && !cursorDirty) return;
  syncBusy = true;
  const good = Object.fromEntries(pendingGood), seen = [...pendingSeen];
  pendingGood.clear(); pendingSeen.clear(); cursorDirty = false;
  const job = S.job;
  try {
    const r = await api('sync', {job, seq: ++syncSeq, cursor: S.list ? cur() : S.pos, good, seen});
    if (r.ok) applyStats(r.stats);
    else if (r.status !== 409) throw new Error(r.error || 'sync failed');
  } catch (err) {
    if (S.job === job) {  // put the batch back (newer values win), retry soon
      for (const [k, v] of Object.entries(good)) if (!pendingGood.has(+k)) pendingGood.set(+k, v);
      seen.forEach(i => pendingSeen.add(i));
      cursorDirty = true;
      scheduleSync(1000);
    }
  } finally {
    syncBusy = false;
    if (pendingGood.size || pendingSeen.size || cursorDirty) scheduleSync();
  }
}

async function flushSync() {
  for (let k = 0; k < 100; k++) {
    if (!syncBusy && !pendingGood.size && !pendingSeen.size && !cursorDirty) return true;
    if (!syncBusy) { clearTimeout(syncTimer); syncTimer = null; await doSync(); } else await sleep(20);
  }
  return false;
}
// once a second: prefetch dot, network folder state (offline / back again)
setInterval(() => { if (S.job && (page === 'sort' || page === 'review')) cursorChanged(); }, 1000);

// ------------------------------------------------------------------ review
const R = {items: null, sel: 0, cols: 1, cells: new Map()};
const CELL_W = 196, CELL_H = 232;
const goodIndices = () => { const out = []; for (let i = 0; i < S.n; i++) if (S.good[i]) out.push(i); return out; };

function openReview(keepSnapshot) {
  if (!keepSnapshot || !R.items) { R.items = goodIndices(); R.sel = 0; }
  R.cells.forEach(el => el.remove());
  R.cells.clear();
  show('review');
  flushSync();
}

function renderReview() {
  const unseen = S.n - S.seenCount;
  const failed = S.failed.reduce((a, b) => a + b, 0);
  const extra = S.mode === 'extra';
  $('rTotalLabel').textContent = extra ? '검토 대상' : '전체';
  $('rGoodLabel').textContent = extra ? '추가 GOOD' : 'GOOD';
  $('rRejectLabel').textContent = extra ? '남는 REJECT' : 'REJECT';
  $('rExtra').classList.toggle('hidden', !extra);
  if (extra) {
    const x = S.extra;
    $('rExtra').textContent = `추가 GOOD 검토 — 이전 결과(${x.results_time}) 기준. 기존 GOOD ${fmt(x.base_good)}장은 그대로 유지되고, ` +
      `저장하면 GOOD ${fmt(x.base_good + S.goodCount)}장(기존 ${fmt(x.base_good)} + 추가 ${fmt(S.goodCount)})이 됩니다.` +
      (x.fresh.length ? ` 신규 사진 ${fmt(x.fresh.length)}장 포함.` : '') + (x.missing ? ` 폴더에 없는 ${fmt(x.missing)}장은 제외.` : '');
  }
  $('gridEmpty').textContent = extra ? '이번에 추가한 GOOD이 없습니다. 저장하면 이전 결과와 같은 내용이 됩니다.'
    : 'GOOD으로 고른 사진이 없습니다. 저장하면 전부 REJECT 목록에 들어갑니다.';
  $('rTotal').textContent = fmt(S.n);
  $('rGood').textContent = fmt(S.goodCount);
  $('rReject').textContent = fmt(S.n - S.goodCount);
  $('rUnseen').textContent = fmt(unseen);
  $('rWarn').classList.toggle('hidden', unseen === 0);
  $('rWarnText').textContent = `화면에 한 번도 표시되지 않은 미확인 사진 ${fmt(unseen)}장 — 저장하면 REJECT로 들어갑니다.` +
    (failed ? ` (읽기 실패 ${fmt(failed)}장 포함)` : '');
  $('rDest').textContent = extra
    ? `${S.output}  →  ${S.files[0]} (${fmt(S.extra.base_good + S.goodCount)}), ${S.files[1]} (${fmt(S.n - S.goodCount)}) · 이전 파일은 백업`
    : `${S.output}  →  ${S.files[0]} (${fmt(S.goodCount)}), ${S.files[1]} (${fmt(S.n - S.goodCount)})`;
  $('rBrowse').disabled = !R.items.length;
  $('gridEmpty').classList.toggle('hidden', R.items.length > 0);
}

function renderGrid(scrollToSel) {
  const grid = $('grid'), inner = $('gridInner');
  const cols = Math.max(1, Math.floor((grid.clientWidth - 24) / CELL_W));
  if (cols !== R.cols) { R.cells.forEach(el => el.remove()); R.cells.clear(); R.cols = cols; }
  const rows = Math.ceil(R.items.length / cols);
  inner.style.height = rows * CELL_H + 'px';
  if (scrollToSel) {
    const row = Math.floor(R.sel / cols);
    if (row * CELL_H < grid.scrollTop) grid.scrollTop = row * CELL_H;
    else if ((row + 1) * CELL_H > grid.scrollTop + grid.clientHeight - 24) grid.scrollTop = (row + 1) * CELL_H - grid.clientHeight + 24;
  }
  const r0 = Math.max(0, Math.floor(grid.scrollTop / CELL_H) - 2);
  const r1 = Math.min(rows, Math.ceil((grid.scrollTop + grid.clientHeight) / CELL_H) + 2);
  const visible = new Set();
  for (let p = r0 * cols; p < Math.min(R.items.length, r1 * cols); p++) {
    visible.add(p);
    let el = R.cells.get(p);
    if (!el) {
      const i = R.items[p];
      el = document.createElement('div');
      el.className = 'cell';
      el.style.transform = `translate(${(p % cols) * CELL_W}px, ${Math.floor(p / cols) * CELL_H}px)`;
      el.innerHTML = `<img alt="" decoding="async" src="thumb/${S.job}/${i}"><span class="cname">${esc(S.names[i])}</span><span class="ctag"></span>`;
      el.onclick = () => { R.sel = p; toggle(R.items[p]); updateCells(); renderReview(); };
      el.ondblclick = () => { R.sel = p; enterList(R.items, p, 'GOOD만 보기'); };
      $('gridInner').appendChild(el);
      R.cells.set(p, el);
    }
  }
  for (const [p, el] of R.cells) if (!visible.has(p)) { el.remove(); R.cells.delete(p); }
  updateCells();
}

function updateCells() {
  for (const [p, el] of R.cells) {
    const good = !!S.good[R.items[p]];
    el.classList.toggle('off', !good);
    el.classList.toggle('sel', p === R.sel);
    el.querySelector('.ctag').textContent = good ? 'GOOD' : 'REJECT';
  }
}
$('grid').addEventListener('scroll', () => renderGrid(false), {passive: true});
new ResizeObserver(() => { if (page === 'review') renderGrid(false); }).observe($('grid'));

function reviewKey(e) {
  const c = e.code;
  if (e.ctrlKey && c === 'KeyS') { e.preventDefault(); if (!e.repeat) save(); return; }
  if (['Space', 'ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown', 'Enter', 'NumpadEnter', 'Escape', 'Home', 'End', 'PageUp', 'PageDown'].includes(c)) e.preventDefault();
  if (c === 'Escape') { if (!e.repeat) { S.list = null; show('sort'); present(); pump(); } return; }
  if (c === 'KeyR') { if (!e.repeat) refreshNow(); return; }
  if (!R.items.length) return;
  const last = R.items.length - 1;
  const moves = {ArrowRight: 1, ArrowLeft: -1, ArrowDown: R.cols, ArrowUp: -R.cols, PageDown: R.cols * 3, PageUp: -R.cols * 3};
  if (c in moves) { R.sel = Math.max(0, Math.min(last, R.sel + moves[c])); renderGrid(true); }
  else if (c === 'Home') { R.sel = 0; renderGrid(true); }
  else if (c === 'End') { R.sel = last; renderGrid(true); }
  else if (c === 'Space' && !e.repeat) {  // same as the sorting screen: change, then the next one
    toggle(R.items[R.sel]);
    R.sel = Math.min(last, R.sel + 1);
    renderGrid(true);
    renderReview();
  }
  else if ((c === 'Enter' || c === 'NumpadEnter') && !e.repeat) enterList(R.items, R.sel, 'GOOD만 보기');
}

async function save() {
  if (modal) return;
  const unseen = S.n - S.seenCount;
  if (unseen > 0) {
    const a = await ask('미확인 사진이 있습니다', `화면에 한 번도 표시되지 않은 사진 ${fmt(unseen)}장은 REJECT로 저장됩니다.\n저장할까요?`,
      [{label: '저장 (Enter)', value: 'ok', keys: ['Enter', 'NumpadEnter'], primary: true}, {label: '취소 (Esc)', value: 'no', keys: ['Escape']}]);
    if (a !== 'ok') return;
  }
  await flushSync();
  let outputDir = S.output;
  let overwrite = false;
  for (;;) {
    const r = await api('save', {job: S.job, good: goodIndices(), overwrite, output_dir: outputDir});
    if (r.ok) { S.output = r.output_dir; $('hOut').textContent = '저장: ' + S.output; showDone(r); return; }
    if (r.changed) {
      const a = await ask('이전 결과 파일이 바뀌었습니다', `${outputDir}\n추가 검토를 시작한 뒤에 결과 파일이 바뀌었습니다(다른 PC에서 저장 등).\n` +
        '그래도 이 검토 내용으로 저장할까요? (지금 파일은 백업됩니다)',
        [{label: '저장 (Enter)', value: 'ok', keys: ['Enter', 'NumpadEnter'], primary: true}, {label: '취소 (Esc)', value: 'no', keys: ['Escape']}]);
      if (a !== 'ok') return;
      overwrite = true;
      continue;
    }
    if (r.conflict) {
      const a = await ask('같은 이름의 결과 파일이 있습니다', `${outputDir}\n${r.conflict.join('\n')}\n\n덮어쓸까요?`,
        [{label: '덮어쓰기 (Enter)', value: 'ok', keys: ['Enter', 'NumpadEnter'], primary: true}, {label: '취소 (Esc)', value: 'no', keys: ['Escape']}]);
      if (a !== 'ok') return;
      overwrite = true;
      continue;
    }
    const buttons = [{label: '취소 (Esc)', value: 'no', keys: ['Escape', 'Enter']}];
    if (bridge()) buttons.unshift({label: '다른 위치 선택', value: 'pick', primary: true});
    const a = await ask('저장하지 못했습니다', (r.error || '알 수 없는 오류') + '\n\n진행 상황은 자동 저장되어 있습니다.', buttons);
    if (a !== 'pick') return;
    const dir = await bridge().choose_folder(outputDir);
    if (!dir) return;
    outputDir = dir;
    overwrite = false;
  }
}

function showDone(r) {
  $('doneFiles').innerHTML =
    `<div><span class="g">GOOD</span> <b>${fmt(r.good_count)}</b>장<br><small class="muted">${esc(r.good_path)}</small></div>` +
    `<div><span class="r">REJECT</span> <b>${fmt(r.reject_count)}</b>장<br><small class="muted">${esc(r.reject_path)}</small></div>` +
    (r.added_path ? `<div><span class="g">추가 GOOD</span> <b>${fmt(r.added_count)}</b>장 (기존 GOOD ${fmt(r.base_count)}장 + 추가)<br><small class="muted">${esc(r.added_path)}</small></div>` : '') +
    (r.backups && r.backups.length ? `<div><span class="muted">이전 파일 백업</span><br><small class="muted">${r.backups.map(esc).join('<br>')}</small></div>` : '');
  show('done');
}

// ------------------------------------------------------------------ keyboard
const SORT_KEYS = new Set(['Space', 'ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown',
  'Enter', 'NumpadEnter', 'Escape', 'KeyF', 'KeyR', 'Tab', 'Backspace', 'F5']);

function sortKey(e) {
  const c = e.code;
  if (SORT_KEYS.has(c) || e.ctrlKey || e.altKey) e.preventDefault();
  if (!S.job) return;
  switch (c) {
    case 'Space': goodAndNext(e); break;
    case 'ArrowRight': move(1, e); break;
    case 'ArrowLeft': move(-1, e); break;
    case 'Home': if (!e.repeat) jump(0); break;
    case 'End': if (!e.repeat) jump(workPos()); break;
    case 'KeyF': if (!e.repeat) toggleZoom(); break;
    case 'KeyR': if (!e.repeat) refreshNow(); break;
    case 'Enter': case 'NumpadEnter':
      if (!e.repeat && !S.list && S.pos === len() - 1 && S.painted === cur()) openReview(false);
      break;
    case 'Escape': if (!e.repeat) openMenu(); break;
  }
}

window.addEventListener('keydown', e => {
  if (modal) { modalKey(e); return; }
  if (e.code === 'F5' || (e.ctrlKey && e.code === 'KeyR')) {  // 새로고침: reconnect, never a page reload
    e.preventDefault();
    if (e.repeat) return;
    if (page === 'sort' || page === 'review') refreshNow();
    else if (page === 'start') scheduleCheck();
    return;
  }
  if (page === 'sort') sortKey(e);
  else if (page === 'review') reviewKey(e);
  else if (page === 'start') {
    if ((e.code === 'Enter' || e.code === 'NumpadEnter') && !e.repeat) { e.preventDefault(); start(!!(lastCheck && lastCheck.session)); }
    else if (e.ctrlKey && e.code === 'KeyO') { e.preventDefault(); pick('folder'); }
  } else if (page === 'done' && e.code === 'Escape') { e.preventDefault(); openReview(true); }
}, true);
// Space on a focused button fires on keyup: swallow it outside the start screen.
window.addEventListener('keyup', e => { if (page !== 'start' && e.code === 'Space') e.preventDefault(); }, true);
window.addEventListener('focus', () => { if (page !== 'start' && document.activeElement) document.activeElement.blur(); });
document.addEventListener('contextmenu', e => { if (page !== 'start') e.preventDefault(); });

// ------------------------------------------------------------------ wiring
for (const b of document.querySelectorAll('button')) {
  b.tabIndex = -1;
  b.addEventListener('mousedown', e => e.preventDefault());  // buttons never take keyboard focus
}
$('folder').addEventListener('input', scheduleCheck);
$('output').addEventListener('input', scheduleCheck);
$('pickFolder').onclick = () => pick('folder');
$('pickOutput').onclick = () => pick('output');
$('startBtn').onclick = () => start(!!(lastCheck && lastCheck.session));
$('extraBtn').onclick = () => start(!!(lastCheck && lastCheck.extra_session), 'extra');
$('extraFresh').onclick = async () => {
  const a = await ask('추가 GOOD 검토 처음부터', '진행 중이던 추가 검토(추가 GOOD 지정, 확인 위치)를 지우고 지금 결과 파일 기준으로 처음부터 시작할까요?',
    [{label: '처음부터 (Enter)', value: 'ok', keys: ['Enter', 'NumpadEnter'], primary: true}, {label: '취소 (Esc)', value: 'no', keys: ['Escape']}]);
  if (a === 'ok') start(false, 'extra');
};
$('freshBtn').onclick = async () => {
  const a = await ask('새로 시작', '이전 진행 내용(GOOD 지정, 확인 위치)을 지우고 처음부터 시작할까요?',
    [{label: '새로 시작 (Enter)', value: 'ok', keys: ['Enter', 'NumpadEnter'], primary: true}, {label: '취소 (Esc)', value: 'no', keys: ['Escape']}]);
  if (a === 'ok') start(false);
};
$('loadCancel').onclick = async () => { await api('new', {}); show('start'); scheduleCheck(); };
$('rBack').onclick = () => { S.list = null; show('sort'); present(); pump(); };
$('rBrowse').onclick = () => enterList(R.items, 0, 'GOOD만 보기');
$('rUnseenBtn').onclick = () => { const list = []; for (let i = 0; i < S.n; i++) if (!S.seen[i]) list.push(i); enterList(list, 0, '미확인 사진 보기'); };
$('rSave').onclick = () => save();
$('doneOpen').onclick = () => { const b = bridge(); if (b) b.open_path(S.output); };
$('doneReview').onclick = () => openReview(true);
$('doneNew').onclick = async () => { await api('new', {}); S.job = null; dropAll(); show('start'); loadHome(); };

function bridgeReady() { document.querySelectorAll('.bridge-only').forEach(el => el.classList.toggle('hidden', !bridge())); }
window.addEventListener('pywebviewready', bridgeReady);
bridgeReady();
loadHome();
