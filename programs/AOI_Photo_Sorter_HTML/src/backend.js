'use strict';
// AOI Photo Sorter HTML: the work engine.py / server.py do in the Python version, done in the page.
//
// Folders are directories the user picked in Edge's folder dialog (File System Access API). The
// page knows a picked folder by a display string: its name, or the full path typed over it
// (\\server\share\LOT123); folders below it are "<display>\<sub>\<subsub>". Photos are read in
// the page (read-ahead like ImageCache), progress is kept in IndexedDB (like sessions\*.json),
// and the results are the same n차리뷰 .txt files the Python version writes (UTF-8, CRLF), so
// either version reads what the other saved. Nothing leaves the PC: the page's Content Security
// Policy forbids every network connection.
//
// The screen (app.js) calls Backend.call(name, body) with the same requests and gets the same
// answers as from the Python server; photos come as Blobs instead of URLs.

const Backend = (() => {
  const TITLE = (document.querySelector('meta[name="aoi-title"]') || {}).content || 'AOI Photo Sorter HTML';
  const MB = 1024 * 1024;
  const SEP = '\\';
  const IMAGE = /\.(jpe?g|png|bmp|tiff?)$/i, TIFF = /\.tiff?$/i;
  const MIME = {jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', bmp: 'image/bmp', tif: 'image/tiff', tiff: 'image/tiff'};
  const mimeOf = name => MIME[String(name).split('.').pop().toLowerCase()] || 'application/octet-stream';
  const collator = new Intl.Collator('ko', {numeric: true, sensitivity: 'base'});  // IMG_2 before IMG_10, like Explorer
  const byName = (a, b) => collator.compare(a, b) || (a < b ? -1 : a > b ? 1 : 0);
  const now = () => performance.now();
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const token = () => Math.random().toString(16).slice(2, 10);
  const lower = s => String(s).toLowerCase();  // Windows file names ignore case
  const hooks = () => window.__aoiTestHooks || {};  // tests: a slow or unreachable share
  const CFG = {read_threads: 8, ahead_count: 200, ahead_bytes: 384 * MB, behind_count: 50, behind_bytes: 128 * MB,
    retry_delays: [200, 500, 1000], thumb_size: 192, probe_ms: 2000, stall_ms: 5000, tree_threads: 6, tree_depth: 4,
    tree_folders: 2000, keep_names: 200000, reuse_ms: 60000};
  const OPTIONS = {arrow_repeat: false, arrow_repeat_ms: 100, space_min_view_ms: 120, path_panel: true, decode_ahead: 5, decode_behind: 3};
  const SCREEN_OPTIONS = ['arrow_repeat', 'path_panel'];  // what the screen may change

  class StaleError extends Error { constructor(m) { super(m); this.stale = true; } }
  class ReadError extends Error { constructor(m, kind) { super(m); this.kind = kind || 'read'; } }

  const pad = n => String(n).padStart(2, '0');
  const stamp = (d = new Date()) => `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}`;
  const clock = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const clockSec = (d = new Date()) => clock(d) + ':' + pad(d.getSeconds());
  const whenText = when => `${when.slice(0, 4)}-${when.slice(4, 6)}-${when.slice(6, 8)} ${when.slice(9, 11)}:${when.slice(11, 13)}`;
  const errText = err => (err && (err.message || err.name)) || String(err);

  // ------------------------------------------------------------------ storage (IndexedDB, memory if blocked)
  const memory = {kv: new Map(), sessions: new Map()};
  let dbPromise = null;
  function db() {
    if (!dbPromise) {
      dbPromise = new Promise(resolve => {
        try {
          const req = indexedDB.open('aoi-photo-sorter', 1);
          req.onupgradeneeded = () => { req.result.createObjectStore('kv'); req.result.createObjectStore('sessions'); };
          req.onsuccess = () => resolve(req.result);
          req.onerror = () => resolve(null);
        } catch (err) { resolve(null); }
      });
    }
    return dbPromise;
  }
  async function storeGet(store, key) {
    const d = await db();
    if (!d) return memory[store].get(key);
    return new Promise(resolve => {
      const req = d.transaction(store, 'readonly').objectStore(store).get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(undefined);
    });
  }
  async function storePut(store, key, value) {
    const d = await db();
    if (!d) { memory[store].set(key, value); return; }
    return new Promise((resolve, reject) => {
      const tx = d.transaction(store, 'readwrite');
      tx.objectStore(store).put(value, key);
      tx.oncomplete = () => resolve();
      tx.onerror = tx.onabort = () => reject(tx.error);
    });
  }

  // settings: screen options, the output folder, recent work, the picked folders (for session identity)
  let settings = null;
  async function loadSettings() {
    if (settings) return settings;
    const s = (await storeGet('kv', 'settings')) || {};
    const options = Object.assign({}, OPTIONS);
    for (const key of Object.keys(OPTIONS)) if (s.options && typeof s.options[key] === typeof OPTIONS[key]) options[key] = s.options[key];
    settings = {options, output: s.output || null, recent: Array.isArray(s.recent) ? s.recent : [],
      roots: Array.isArray(s.roots) ? s.roots : [], aliases: Array.isArray(s.aliases) ? s.aliases : []};
    return settings;
  }
  async function saveSettings() {
    try { await storePut('kv', 'settings', settings); return; } catch (err) { /* below */ }
    // folder handles could not be stored: everything else is, and progress is found by folder name
    const plain = {options: settings.options, output: null, aliases: settings.aliases,
      recent: [], roots: settings.roots.map(r => ({id: r.id, name: r.name}))};
    try { await storePut('kv', 'settings', plain); } catch (err) { console.warn('settings not saved', err); }
  }

  // ------------------------------------------------------------------ picked folders
  const roots = new Map();    // display -> {handle, id}: photo folders (a parent folder too)
  const outputs = new Map();  // display -> handle: result folders
  const dirCache = new Map(); // display path of a folder below a root -> handle

  function rootOf(path) {
    let best = null;
    for (const [display, r] of roots) {
      if ((path === display || path.startsWith(display + SEP)) && (!best || display.length > best.display.length)) best = {display, handle: r.handle, id: r.id};
    }
    if (!best) return null;
    best.parts = path.slice(best.display.length).split(SEP).filter(Boolean);
    return best;
  }
  async function resolveDir(path) {
    if (dirCache.has(path)) return dirCache.get(path);
    const hit = rootOf(path);
    if (!hit) return null;
    let h = hit.handle;
    for (const part of hit.parts) h = await h.getDirectoryHandle(part);
    dirCache.set(path, h);
    return h;
  }
  // A display typed over a picked folder (its full path): the same folder when the last part is its name.
  function adopt(path, map, isOutput) {
    if (!path || map.has(path) || (!isOutput && rootOf(path))) return;
    const last = path.split(/[\\/]+/).filter(Boolean).pop();
    for (const [, v] of map) {
      if ((isOutput ? v : v.handle).name === last) { map.set(path, v); return; }
    }
  }
  const nameOf = path => { const r = roots.get(path); return r ? r.handle.name : String(path).split(/[\\/]+/).filter(Boolean).pop() || 'photos'; };
  function relParts(root, path) {
    if (path === root) return [];
    if (!root || !path.startsWith(root + SEP)) return null;
    return path.slice(root.length + 1).split(SEP).filter(Boolean);
  }
  const cleanLabel = t => String(t).replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/^[ .]+|[ .]+$/g, '');
  // engine.result_label: the folder name, or <parent>_<sub>[_…] for a folder opened through its parent
  function resultLabel(path, root) {
    const rel = root ? relParts(root, path) : null;
    if (rel && rel.length) return cleanLabel([nameOf(root), ...rel].join('_')) || cleanLabel(nameOf(path)) || 'photos';
    return cleanLabel(nameOf(path)) || 'photos';
  }

  // Session identity: the same folder picked again (or picked inside / around one picked before)
  // finds its progress; isSameEntry / resolve compare the real paths without reading anything.
  async function rootIdFor(handle) {
    const s = await loadSettings();
    for (const r of s.roots) {
      try { if (r.handle && await r.handle.isSameEntry(handle)) { r.handle = handle; return r.id; } } catch (err) { /* stale handle */ }
    }
    const byName = s.roots.find(r => !r.handle && r.name === handle.name);  // stored without its handle
    if (byName) { byName.handle = handle; return byName.id; }
    const id = token();
    for (const r of s.roots) {
      if (!r.handle) continue;
      try {
        const inside = await r.handle.resolve(handle);  // the new folder is inside a known one
        if (inside) { s.aliases.push({prefix: id, target: [r.id, ...inside].join('/')}); break; }
        const around = await handle.resolve(r.handle);  // a known folder is inside the new one
        if (around && around.length) s.aliases.push({prefix: [id, ...around].join('/'), target: r.id});
      } catch (err) { /* stale handle */ }
    }
    s.roots.push({id, handle, name: handle.name});
    if (s.roots.length > 300) s.roots.splice(0, s.roots.length - 300);
    if (s.aliases.length > 600) s.aliases.splice(0, s.aliases.length - 600);
    await saveSettings();
    return id;
  }
  function canonical(key) {
    for (let k = 0; k < 6; k++) {
      const a = settings.aliases.find(x => key === x.prefix || key.startsWith(x.prefix + '/'));
      if (!a) break;
      key = a.target + key.slice(a.prefix.length);
    }
    return key;
  }
  function sessionKey(path, mode = '') {
    const hit = rootOf(path);
    if (!hit) return null;
    return canonical([hit.id, ...hit.parts].join('/')) + (mode ? '#' + mode : '');
  }

  async function permission(handle, mode, ask) {
    if (!handle) return 'none';
    if (hooks().permission) return hooks().permission;
    try {
      let p = await handle.queryPermission({mode});
      if (p !== 'granted' && ask) p = await handle.requestPermission({mode});
      return p;
    } catch (err) { return 'denied'; }
  }

  // Edge's folder dialog. read for photos, readwrite for results.
  async function pick(kind) {
    const isOutput = kind === 'output';
    let h;
    try {
      h = await window.showDirectoryPicker({id: isOutput ? 'aoi-output' : 'aoi-photos', mode: isOutput ? 'readwrite' : 'read'});
    } catch (err) {
      if (err.name === 'AbortError') return null;
      throw new Error('폴더를 열 수 없습니다 (' + errText(err) + '). 회사 정책으로 막혀 있으면 IT에 문의하세요.');
    }
    const map = isOutput ? outputs : roots;
    for (const [display, v] of map) {  // picked before: keep its display (a full path typed over it)
      try { if (await (isOutput ? v : v.handle).isSameEntry(h)) { setHandle(map, display, h, isOutput); return display; } } catch (err) { /* stale */ }
    }
    let display = h.name, k = 2;
    while (map.has(display)) display = `${h.name} (${k++})`;  // another folder of the same name
    if (isOutput) outputs.set(display, h);
    else roots.set(display, {handle: h, id: await rootIdFor(h)});
    if (isOutput) { const s = await loadSettings(); s.output = {display, handle: h}; await saveSettings(); }
    return display;
  }
  // the folder picked again: its new handle (just allowed by the dialog) for every display of it
  function setHandle(map, display, h, isOutput) {
    const old = map.get(display);
    if (isOutput) { for (const [d, v] of [...map]) if (v === old) map.set(d, h); }
    else old.handle = h;
    dirCache.clear();
  }

  async function grant(folder, output) {
    const out = {};
    const r = folder ? rootOf(folder) : null;
    if (r) out.folder = await permission(r.handle, 'read', true);
    const o = output ? outputs.get(output) : null;
    if (o) out.output = await permission(o, 'readwrite', true);
    return out;
  }

  // ------------------------------------------------------------------ folder listing
  const skipFolder = name => /^[.$]/.test(name) || lower(name) === 'system volume information';
  async function listDir(dir, progress, cancelled) {
    const files = [], dirs = [];
    for await (const [name, h] of dir.entries()) {
      if (cancelled && cancelled()) break;
      if (h.kind === 'directory') { if (!skipFolder(name)) dirs.push([name, h]); }
      else if (IMAGE.test(name)) {
        files.push([name, h]);
        if (progress && files.length % 200 === 0) progress(files.length);
      }
    }
    files.sort((a, b) => byName(a[0], b[0]));
    dirs.sort((a, b) => byName(a[0], b[0]));
    if (progress) progress(files.length);
    return {names: files.map(f => f[0]), handles: files.map(f => f[1]), dirs};
  }

  // engine.FolderTree: the photo folders at and below a folder, listed by 6 at a time in the background
  class FolderTree {
    constructor(root, handle) {
      Object.assign(this, {root, state: 'running', error: '', listed: 0, failed: 0, rootListed: false, found: 0,
        entries: new Map(), listings: new Map(), kept: 0, queue: [[handle, []]], pending: 1, seen: 1, active: 0, cancelled: false});
      this.kick();
    }
    cancel() { this.cancelled = true; if (this.state === 'running') this.state = 'stopped'; }
    snapshot() {
      const entries = [...this.entries.values()].sort((a, b) => {
        for (let k = 0; k < Math.min(a.parts.length, b.parts.length); k++) { const c = byName(a.parts[k], b.parts[k]); if (c) return c; }
        return a.parts.length - b.parts.length;
      });
      return {state: this.state, error: this.error, listed: this.listed, pending: this.pending, failed: this.failed,
        root_listed: this.rootListed, found: this.found, entries: entries.map(e => ({path: e.path, parts: e.parts.slice(), count: e.count}))};
    }
    listing(path) {
      const kept = this.listings.get(path);
      return kept && now() - kept.t < CFG.reuse_ms ? kept : null;
    }
    update(path, names) {
      const parts = relParts(this.root, path);
      if (parts === null) return;
      if (names.length) this.entries.set(path, {path, parts, count: names.length});
      else this.entries.delete(path);
    }
    kick() {
      while (this.active < CFG.tree_threads && this.queue.length && !this.cancelled) {
        this.active++;
        this.work(this.queue.shift()).finally(() => { this.active--; this.kick(); });
      }
    }
    async work([dir, parts]) {
      let listed = null, error = null;
      try { listed = await listDir(dir, parts.length ? null : n => { this.found = n; }, () => this.cancelled); } catch (err) { error = err; }
      this.pending--;
      if (this.cancelled) return;  // a cut-short listing is never used
      const path = parts.length ? this.root + SEP + parts.join(SEP) : this.root;
      if (error) {
        if (parts.length) this.failed++;
        else { this.state = 'error'; this.error = '폴더를 읽을 수 없습니다: ' + errText(error); }
      } else {
        this.listed++;
        if (!parts.length) this.rootListed = true;
        if (listed.names.length) {
          this.entries.set(path, {path, parts, count: listed.names.length});
          if (this.kept + listed.names.length <= CFG.keep_names) {
            this.kept += listed.names.length;
            this.listings.set(path, {t: now(), names: listed.names, handles: listed.handles});
          }
        }
        if (parts.length < CFG.tree_depth) {
          for (const [name, h] of listed.dirs) {
            if (this.seen >= CFG.tree_folders) break;
            this.seen++;
            this.pending++;
            this.queue.push([h, [...parts, name]]);
          }
        }
      }
      if (!this.pending && this.state === 'running') this.state = 'done';
    }
  }

  // ------------------------------------------------------------------ result files (engine.py, n차리뷰)
  const KINDS = ['추가GOOD', 'GOOD', 'REJECT'];
  const escapeRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  async function outputNames(out) {
    const names = [];
    for await (const name of out.keys()) names.push(name);
    return names;
  }
  function decodeText(buffer) {
    try { return new TextDecoder('utf-8', {fatal: true}).decode(buffer); }  // UTF-8, a BOM dropped
    catch (err) { return new TextDecoder('euc-kr').decode(buffer); }  // edited in Notepad and saved as ANSI (CP949)
  }
  async function readLines(out, name) {
    const file = await (await out.getFileHandle(name)).getFile();
    return {lines: decodeText(await file.arrayBuffer()).split(/\r?\n/).map(l => l.trim()).filter(Boolean), file};
  }
  function listRounds(names, label) {
    const re = new RegExp('^' + escapeRe(label) + '_(\\d+)차리뷰_(\\d{8})_(\\d{4})_(추가GOOD|GOOD|REJECT)\\.txt$', 'i');
    const rounds = new Map();
    for (const name of names) {
      const m = re.exec(name);
      if (!m) continue;
      const key = `${m[1]}|${m[2]}_${m[3]}`;
      if (!rounds.has(key)) rounds.set(key, {n: +m[1], when: `${m[2]}_${m[3]}`, files: {}});
      rounds.get(key).files[m[4].toUpperCase()] = name;
    }
    return [...rounds.values()];
  }
  const newestFirst = (a, b) => b.n - a.n || (a.when < b.when ? 1 : a.when > b.when ? -1 : 0);
  function findName(names, wanted) { const w = lower(wanted); return names.find(n => lower(n) === w); }
  async function legacyResults(out, names, label) {
    const res = {good: [], reject: []}, key = ['legacy'];
    let found = false, newest = 0;
    for (const [k, suffix] of [['good', '_GOOD.txt'], ['reject', '_REJECT.txt']]) {
      const name = findName(names, label + suffix);
      if (!name) { key.push(null); continue; }
      try {
        const {lines, file} = await readLines(out, name);
        res[k] = lines;
        key.push([file.lastModified, file.size]);
        newest = Math.max(newest, file.lastModified);
        found = true;
      } catch (err) { key.push(null); }
    }
    if (!found) return null;
    const extras = names.filter(n => lower(n).startsWith(lower(label + '_GOOD_추가_'))).length;
    return Object.assign(res, {round: 1 + extras, key, legacy: true, time: clock(new Date(newest)),
      files: [label + '_GOOD.txt', label + '_REJECT.txt']});
  }
  async function readResults(out, names, label) {
    for (const r of listRounds(names, label).filter(r => r.files.GOOD && r.files.REJECT).sort(newestFirst)) {
      try {
        const good = (await readLines(out, r.files.GOOD)).lines, reject = (await readLines(out, r.files.REJECT)).lines;
        return {good, reject, round: r.n, key: [r.n, r.when], legacy: false, time: whenText(r.when), files: [r.files.GOOD, r.files.REJECT]};
      } catch (err) { /* unreadable: the next newest */ }
    }
    return legacyResults(out, names, label);
  }
  async function lastRound(out, names, label) {
    const rounds = listRounds(names, label);
    if (rounds.length) return Math.max(...rounds.map(r => r.n));
    const legacy = await legacyResults(out, names, label);
    return legacy ? legacy.round : 0;
  }
  const resultsSummary = r => r ? {good: r.good.length, reject: r.reject.length, time: r.time, round: r.round, legacy: r.legacy} : null;
  // engine.results_index: the latest round of every label from one listing (no file read)
  function resultsIndex(names) {
    const rounds = new Map(), legacy = new Set(), extras = new Map(), out = {};
    const re = /^(.+)_(\d+)차리뷰_(\d{8})_(\d{4})_(추가GOOD|GOOD|REJECT)\.txt$/i;
    for (const name of names) {
      const m = re.exec(name);
      if (m) {
        const label = lower(m[1]), key = `${m[2]}|${m[3]}_${m[4]}`;
        if (!rounds.has(label)) rounds.set(label, new Map());
        const byKey = rounds.get(label);
        if (!byKey.has(key)) byKey.set(key, {n: +m[2], when: `${m[3]}_${m[4]}`, kinds: new Set()});
        byKey.get(key).kinds.add(m[5].toUpperCase());
        continue;
      }
      const l = lower(name);
      for (const suffix of ['_good.txt', '_reject.txt']) if (l.endsWith(suffix)) legacy.add(l.slice(0, -suffix.length));
      if (l.includes('_good_추가_')) { const label = l.slice(0, l.lastIndexOf('_good_추가_')); extras.set(label, (extras.get(label) || 0) + 1); }
    }
    for (const [label, byKey] of rounds) {
      const done = [...byKey.values()].filter(r => r.kinds.has('GOOD') && r.kinds.has('REJECT')).sort(newestFirst);
      if (done.length) out[label] = {round: done[0].n, time: whenText(done[0].when), legacy: false};
    }
    for (const label of legacy) if (!out[label]) out[label] = {round: 1 + (extras.get(label) || 0), time: '', legacy: true};
    return out;
  }
  // engine.plan_extra: the old GOOD stay GOOD (not shown again), every other photo is reviewed
  function planExtra(names, results) {
    const good = new Set(results.good.map(lower)), reject = new Set(results.reject.map(lower)), inFolder = new Set(names.map(lower));
    const base = [], targets = [], fresh = [];
    for (const name of names) {
      const key = lower(name);
      if (good.has(key)) base.push(name);
      else { targets.push(name); if (!reject.has(key)) fresh.push(name); }
    }
    let missing = 0;
    for (const key of new Set([...good, ...reject])) if (!inFolder.has(key)) missing++;
    return {base, targets, fresh, missing};
  }
  async function writeText(out, name, lines) {
    const handle = await out.getFileHandle(name, {create: true});
    const writer = await handle.createWritable();  // written to a temporary file, swapped in on close
    try {
      await writer.write(new Blob([lines.map(l => l + '\r\n').join('')], {type: 'text/plain'}));
      await writer.close();
    } catch (err) {
      await writer.abort().catch(() => {});
      throw err;
    }
  }
  // engine.save_round: a new round every save, never touching an earlier one
  async function saveRound(out, outDisplay, allNames, picked, {baseGood = null, baseKey = null, own = null, mergeNewer = false, minRound = 1, label}) {
    let names = await outputNames(out);
    const latest = await readResults(out, names, label);
    const latestKey = latest ? JSON.stringify(latest.key) : null;
    let base = baseGood, merged = false, n, when;
    if (own && latestKey === JSON.stringify([own[0], own[1]])) {
      [n, when] = own;
    } else {
      if (baseGood !== null && baseKey !== null && latestKey !== JSON.stringify(baseKey)) {
        if (!mergeNewer) return {ok: false, changed: true, latest_round: latest ? latest.round : 0};
        if (latest) {
          const newer = new Set(latest.good.map(lower));
          base = allNames.filter(x => newer.has(lower(x)));
          merged = true;
        }
      }
      n = Math.max((await lastRound(out, names, label)) + 1, minRound);
      when = stamp();
    }
    const good = new Set([...(base || []), ...picked]);
    const pickedSet = new Set(picked), baseSet = new Set(base || []);
    const goodLines = allNames.filter(x => good.has(x)), rejectLines = allNames.filter(x => !good.has(x));
    const addedLines = base === null ? null : allNames.filter(x => pickedSet.has(x) && !baseSet.has(x));
    const file = kind => `${label}_${n}차리뷰_${when}_${kind}.txt`;
    const paths = {};
    for (const [kind, lines] of [['추가GOOD', addedLines], ['REJECT', rejectLines], ['GOOD', goodLines]]) {  // GOOD last: the round counts once both exist
      if (lines === null) continue;
      await writeText(out, file(kind), lines);
      paths[kind] = outDisplay + SEP + file(kind);
    }
    return {ok: true, round: n, when, merged, base, time: whenText(when),
      good_path: paths.GOOD, reject_path: paths.REJECT, added_path: paths['추가GOOD'] || null,
      good_count: goodLines.length, reject_count: rejectLines.length,
      added_count: addedLines === null ? null : addedLines.length,
      base_count: addedLines === null ? null : goodLines.length - addedLines.length};
  }
  async function checkWritable(display) {
    if (!display) return [false, '결과 저장 위치를 지정하세요.'];
    adopt(display, outputs, true);
    const out = outputs.get(display);
    if (!out) return [false, '[폴더 고르기]로 결과 저장 위치를 고르세요. (브라우저는 입력한 경로를 직접 열 수 없습니다)'];
    const p = await permission(out, 'readwrite', false);
    if (p !== 'granted') return [true, '', 'grant'];
    const name = `.aoi_photo_sorter_${token()}.tmp`;
    try {
      const writer = await (await out.getFileHandle(name, {create: true})).createWritable();
      await writer.write('x');
      await writer.close();
      await out.removeEntry(name);
    } catch (err) {
      return [false, '저장 위치에 쓸 수 없습니다: ' + errText(err)];
    }
    return [true, ''];
  }

  // ------------------------------------------------------------------ sessions (engine.Session, in IndexedDB)
  const summaries = new Map();  // session key -> summary, kept current by every save
  const sessionSummary = data => {
    if (!data || !Array.isArray(data.names)) return null;
    return {total: data.names.length, seen: (String(data.seen || '').match(/1/g) || []).length, good: (data.good || []).length,
      updated: data.updated || '', saved: data.saved || null};
  };
  async function readSession(key) { return key ? (await storeGet('sessions', key)) || null : null; }
  async function summaryOf(path, mode = '') {
    const key = sessionKey(path, mode);
    if (!key) return null;
    if (!summaries.has(key)) summaries.set(key, sessionSummary(await readSession(key)));
    return summaries.get(key);
  }

  class Session {
    constructor(key, folder, output, names, previous, mode) {
      Object.assign(this, {key, folder, output, names, mode, good: new Set(), seen: new Uint8Array(names.length), cursor: 0, seq: 0,
        saved: null, added: 0, removed: 0, dirty: true, writing: Promise.resolve()});
      if (previous) this.restore(previous);
    }
    // by file name: photos added since start unseen, removed ones are dropped
    restore(prev) {
      const index = new Map(this.names.map((n, i) => [n, i]));
      const oldNames = Array.isArray(prev.names) ? prev.names : [], oldSeen = String(prev.seen || '');
      for (const name of prev.good || []) if (index.has(name)) this.good.add(index.get(name));
      oldNames.forEach((name, pos) => { if (oldSeen[pos] === '1' && index.has(name)) this.seen[index.get(name)] = 1; });
      const old = new Set(oldNames);
      this.removed = oldNames.filter(n => !index.has(n)).length;
      this.added = this.names.filter(n => !old.has(n)).length;
      const c = prev.cursor | 0;
      this.cursor = c >= 0 && c < oldNames.length && index.has(oldNames[c]) ? index.get(oldNames[c]) : 0;
      this.saved = prev.saved || null;
    }
    apply(payload) {
      const seq = payload.seq | 0;
      if (seq <= this.seq) return false;
      this.seq = seq;
      const n = this.names.length;
      for (const [k, v] of Object.entries(payload.good || {})) { const i = +k; if (i >= 0 && i < n) { if (v) this.good.add(i); else this.good.delete(i); } }
      for (const i of payload.seen || []) if (i >= 0 && i < n) this.seen[i] = 1;
      if ('cursor' in payload && payload.cursor >= 0 && payload.cursor < Math.max(1, n)) this.cursor = payload.cursor | 0;
      this.dirty = true;
      return true;
    }
    setGood(indices) { this.good = new Set(indices.filter(i => i >= 0 && i < this.names.length)); this.dirty = true; }
    seenText() { let s = ''; for (const v of this.seen) s += v ? '1' : '0'; return s; }
    state() {
      return {names: this.names, good: [...this.good].sort((a, b) => a - b), seen: this.seenText(), cursor: this.cursor, seq: this.seq,
        added: this.added, removed: this.removed, saved: this.saved};
    }
    save(force) {
      if (!this.dirty && !force) return this.writing;
      this.dirty = false;
      const data = {version: 1, mode: this.mode, folder: this.folder, output_dir: this.output, names: this.names,
        good: [...this.good].sort((a, b) => a - b).map(i => this.names[i]), seen: this.seenText(), cursor: this.cursor,
        saved: this.saved, updated: clockSec()};
      summaries.set(this.key, sessionSummary(data));
      this.writing = this.writing.then(() => storePut('sessions', this.key, data)).catch(err => { this.dirty = true; console.warn('session not saved', err); });
      return this.writing;  // one write after another: an older snapshot never lands last
    }
  }

  // ------------------------------------------------------------------ photos: read-ahead (engine.ImageCache)
  // The window is the cursor, up to 200 photos after it and 50 before it (and 384 / 128 MB), nearest
  // first, forward first; outside it everything is dropped. A photo asked for outside the window
  // jumps the queue. When a read fails the folder itself is checked: unreachable means offline (no
  // photo is marked failed; reading pauses and a check every 2 s resumes it), else the photo failed.
  class ImageCache {
    constructor(dir, names, handles, cursor) {
      const n = names.length;
      Object.assign(this, {dir, names, handles: handles || new Array(n), n, data: new Map(), sizes: new Float64Array(n), errors: new Map(),
        inflight: new Set(), started: new Map(), urgent: [], cursor: Math.max(0, Math.min(n - 1, cursor | 0)), order: [], window: new Set(),
        ahead: [], closed: false, offline: false, epoch: 0, bytes: 0, readCounts: new Uint16Array(n), waiters: []});
      this.plan();
      this.pump();
      this.monitor = setInterval(() => this.watch(), CFG.probe_ms);
    }
    plan() {
      const c = this.cursor, n = this.n;
      if (!n) { this.order = []; this.window = new Set(); this.ahead = []; return; }
      // sizes are known once read (the listing has none): the rest count as the average so far
      const average = this.data.size ? this.bytes / this.data.size : 512 * 1024;
      const size = i => this.sizes[i] || average;
      const ahead = [], behind = [];
      let total = 0;
      for (let i = c + 1; i < Math.min(n, c + 1 + CFG.ahead_count); i++) { total += size(i); if (total > CFG.ahead_bytes && ahead.length) break; ahead.push(i); }
      total = 0;
      for (let i = c - 1; i > Math.max(-1, c - 1 - CFG.behind_count); i--) { total += size(i); if (total > CFG.behind_bytes && behind.length) break; behind.push(i); }
      const order = [c, ...this.urgent.slice().reverse().filter(i => i !== c), ...ahead.slice(0, 10), ...behind.slice(0, 5), ...ahead.slice(10), ...behind.slice(5)];
      const seen = new Set();
      this.order = order.filter(i => !seen.has(i) && seen.add(i));
      this.window = seen;
      this.ahead = ahead;
      for (const i of [...this.data.keys()]) if (!seen.has(i)) { this.bytes -= this.sizes[i]; this.data.delete(i); }
    }
    notify() { const w = this.waiters; this.waiters = []; for (const fn of w) fn(); }
    changed(ms) { return new Promise(resolve => { this.waiters.push(resolve); setTimeout(resolve, ms); }); }
    pump() {
      if (this.closed || this.offline) return;
      for (const i of this.order) {
        if (this.inflight.size >= CFG.read_threads) break;
        if (this.data.has(i) || this.inflight.has(i) || this.errors.has(i)) continue;
        this.load(i);
      }
    }
    setCursor(index) {
      index = Math.max(0, Math.min(this.n - 1, index | 0));
      if (index === this.cursor) return;
      this.cursor = index;
      this.plan();
      this.pump();
    }
    async get(index, timeout = 60000) {
      if (!(index >= 0 && index < this.n)) throw new StaleError('없는 사진입니다.');
      const deadline = now() + timeout;
      for (;;) {
        if (this.data.has(index)) return this.data.get(index);
        if (this.errors.has(index)) throw new ReadError(this.errors.get(index), 'read');
        if (this.closed) throw new StaleError('작업이 종료되었습니다.');
        if (this.offline) throw new ReadError('네트워크 폴더 연결이 끊겼습니다.', 'offline');
        if (!this.window.has(index)) {
          this.urgent = this.urgent.filter(i => i !== index).concat(index).slice(-16);
          this.plan();
          this.pump();
        }
        const remain = deadline - now();
        if (remain <= 0) throw new ReadError('읽기 시간 초과', 'read');
        if (!this.inflight.has(index)) this.pump();
        await this.changed(Math.min(remain, 1000));
      }
    }
    peek(index) { return this.data.get(index) || null; }
    refresh() { this.offline = false; this.reset(); }
    reset() { this.errors.clear(); this.epoch++; this.notify(); this.pump(); }
    stats() {
      let ready = 0;
      for (const i of this.ahead) { if (!this.data.has(i)) break; ready++; }
      const oldest = Math.min(Infinity, ...this.started.values());
      return {cursor: this.cursor, ready_ahead: ready, ahead_target: this.ahead.length, cached: this.data.size, cached_bytes: this.bytes,
        errors: this.errors.size, offline: this.offline, epoch: this.epoch, stalled: oldest !== Infinity && now() - oldest > CFG.stall_ms};
    }
    close() { this.closed = true; clearInterval(this.monitor); this.data.clear(); this.bytes = 0; this.notify(); }
    async shareOk() {
      if (hooks().offline) return false;
      try { const it = this.dir.keys(); await it.next(); if (it.return) await it.return(); return true; } catch (err) { return false; }
    }
    async watch() {
      if (this.closed || !this.offline) return;
      if (await this.shareOk() && this.offline && !this.closed) { this.offline = false; this.reset(); }
    }
    async read(index) {
      const h = hooks();
      if (h.readDelay) await sleep(h.readDelay);
      if (h.offline || (h.failRead && h.failRead(this.names[index]))) throw new DOMException('The network path was not found', 'NotReadableError');
      if (!this.handles[index]) this.handles[index] = await this.dir.getFileHandle(this.names[index]);
      const file = await this.handles[index].getFile();
      return new Blob([await file.arrayBuffer()], {type: mimeOf(this.names[index])});  // really read now (a File is read lazily)
    }
    async load(index) {
      this.inflight.add(index);
      this.started.set(index, now());
      let blob = null, error = null, offline = false;
      for (const delay of [0, ...CFG.retry_delays]) {
        if (delay) await sleep(delay);
        if (this.closed) break;
        try { this.readCounts[index]++; blob = await this.read(index); error = null; break; }
        catch (err) { error = err; if (err && err.name === 'NotFoundError' && !hooks().offline) { /* the file itself is gone: no retry needed */ } }
      }
      if (error && !this.closed) offline = !(await this.shareOk());  // the whole folder gone, or only this photo?
      this.inflight.delete(index);
      this.started.delete(index);
      if (!this.closed) {
        if (offline) this.offline = true;  // not a failure of this photo: read again after reconnecting
        else if (error) this.errors.set(index, '읽기 실패: ' + errText(error));
        else if (this.window.has(index)) { this.sizes[index] = blob.size; this.bytes += blob.size; this.data.set(index, blob); }
      }
      this.notify();
      this.pump();
    }
  }

  // ------------------------------------------------------------------ TIFF (Edge cannot show it): UTIF in a worker
  let tiffWorker = null, tiffSeq = 0;
  const tiffWaiting = new Map();
  function worker() {
    if (tiffWorker !== null) return tiffWorker;
    try {
      const src = ['pako-src', 'utif-src'].map(id => document.getElementById(id).textContent).join('\n;\n') + `
        self.onmessage = e => {
          const {id, buffer} = e.data;
          try {
            const ifds = UTIF.decode(buffer), page = ifds[0];
            UTIF.decodeImage(buffer, page, ifds);
            const rgba = UTIF.toRGBA8(page);
            self.postMessage({id, w: page.width, h: page.height, rgba}, [rgba.buffer]);
          } catch (err) { self.postMessage({id, error: String(err && err.message || err)}); }
        };`;
      tiffWorker = new Worker(URL.createObjectURL(new Blob([src], {type: 'text/javascript'})));
      tiffWorker.onmessage = e => { const w = tiffWaiting.get(e.data.id); tiffWaiting.delete(e.data.id); if (w) w(e.data); };
      tiffWorker.onerror = () => { tiffWorker = false; for (const [, w] of tiffWaiting) w({error: 'worker'}); tiffWaiting.clear(); };
    } catch (err) {
      tiffWorker = false;  // no worker: decoded on the page itself
    }
    return tiffWorker;
  }
  function decodeHere(buffer) {
    const ifds = UTIF.decode(buffer), page = ifds[0];
    UTIF.decodeImage(buffer, page, ifds);
    return {w: page.width, h: page.height, rgba: UTIF.toRGBA8(page)};
  }
  async function tiffPixels(blob) {
    const buffer = await blob.arrayBuffer();
    const w = worker();
    let out = w ? await new Promise(resolve => { const id = ++tiffSeq; tiffWaiting.set(id, resolve); w.postMessage({id, buffer: buffer.slice(0)}); }) : null;
    if (!out || out.error === 'worker') out = decodeHere(buffer);
    if (out.error) throw new Error('TIFF 변환 실패: ' + out.error);
    return out;
  }
  async function bitmap(blob, options) {
    if (blob.type !== 'image/tiff') return options ? createImageBitmap(blob, options) : createImageBitmap(blob);
    const {w, h, rgba} = await tiffPixels(blob);
    const data = new ImageData(new Uint8ClampedArray(rgba.buffer, rgba.byteOffset, w * h * 4), w, h);
    return options ? createImageBitmap(data, options) : createImageBitmap(data);
  }
  // for <img>: TIFF as PNG
  async function displayable(blob) {
    if (blob.type !== 'image/tiff') return blob;
    const bmp = await bitmap(blob);
    const canvas = new OffscreenCanvas(bmp.width, bmp.height);
    canvas.getContext('2d').drawImage(bmp, 0, 0);
    bmp.close();
    return canvas.convertToBlob({type: 'image/png'});
  }
  async function thumbnail(blob, size = CFG.thumb_size) {
    const bmp = await bitmap(blob);
    const s = Math.min(1, size / Math.max(bmp.width, bmp.height));
    const w = Math.max(1, Math.round(bmp.width * s)), h = Math.max(1, Math.round(bmp.height * s));
    const canvas = new OffscreenCanvas(w, h), ctx = canvas.getContext('2d');
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(bmp, 0, 0, w, h);
    bmp.close();
    return canvas.convertToBlob({type: 'image/jpeg', quality: 0.8});
  }

  // thumbnails as blob: URLs, the newest kept
  class UrlCache {
    constructor(max) { this.max = max; this.map = new Map(); }
    get(key) { const u = this.map.get(key); if (u) { this.map.delete(key); this.map.set(key, u); } return u; }
    set(key, url) {
      this.map.set(key, url);
      while (this.map.size > this.max) { const [k, u] = this.map.entries().next().value; URL.revokeObjectURL(u); this.map.delete(k); }
      return url;
    }
    clear() { for (const u of this.map.values()) URL.revokeObjectURL(u); this.map.clear(); }
  }

  // GOOD photos' thumbnails made from the bytes already read when they are picked (engine.Thumbnails)
  class Thumbnails {
    constructor(cache) { Object.assign(this, {cache, urls: new UrlCache(5000), making: new Map(), queue: [], busy: false, closed: false}); }
    want(index) { if (!this.urls.map.has(index) && !this.queue.includes(index)) { this.queue.push(index); this.work(); } }
    async url(index) {
      const done = this.urls.get(index);
      if (done) return done;
      if (!this.making.has(index)) {
        this.making.set(index, (async () => {
          try { return this.urls.set(index, URL.createObjectURL(await thumbnail(await this.cache.get(index)))); }
          finally { this.making.delete(index); }
        })());
      }
      return this.making.get(index);
    }
    async work() {
      if (this.busy) return;
      this.busy = true;
      while (this.queue.length && !this.closed) {
        const index = this.queue.shift();
        if (this.urls.map.has(index) || !this.cache.peek(index)) continue;  // not in RAM: made when the review screen asks
        try { await this.url(index); } catch (err) { /* made again when asked */ }
      }
      this.busy = false;
    }
    close() { this.closed = true; this.urls.clear(); }
  }

  // ------------------------------------------------------------------ the job (server.Job / Controller)
  let job = null, tree = null, index = {output: null, t: 0, value: {}}, overviewView = null;
  const overviewUrls = new UrlCache(3000);

  class Job {
    constructor(folder, output, mode, root) {
      Object.assign(this, {id: token(), folder, output, mode, root, label: resultLabel(folder, root), allNames: [], baseGood: [], fresh: [],
        missing: 0, baseKey: null, baseRound: 0, own: null, resultsTime: '', phase: 'scanning', found: 0, message: '',
        names: [], cache: null, thumbs: null, session: null, cancelled: false});
    }
    close() {
      this.cancelled = true;
      if (this.session) this.session.save();
      if (this.thumbs) this.thumbs.close();
      if (this.cache) this.cache.close();
    }
  }
  function current(jobId) {
    if (!job || job.id !== jobId || job.phase !== 'ready') throw new StaleError('작업이 바뀌었거나 준비되지 않았습니다.');
    return job;
  }
  setInterval(() => { if (job && job.session) job.session.save(); }, 1000);  // autosave: at most once a second
  window.addEventListener('pagehide', () => { if (job && job.session) job.session.save(); });

  async function outputListing(display, fresh) {
    if (!fresh && index.output === display && now() - index.t < 2000) return index.value;
    const out = outputs.get(display);
    let value = {};
    if (out && (await permission(out, 'readwrite', false)) === 'granted') {
      try { value = resultsIndex(await outputNames(out)); } catch (err) { value = {}; }
    }
    index = {output: display, t: now(), value};
    return value;
  }

  async function remember(folder, output) {
    const s = await loadSettings();
    const r = rootOf(folder), o = outputs.get(output);
    if (!r || r.parts.length) return;
    s.recent = s.recent.filter(x => x.folder !== folder);
    s.recent.unshift({folder, handle: r.handle, output_dir: output, output: o || null, time: clock()});
    s.recent = s.recent.slice(0, 10);
    if (o) s.output = {display: output, handle: o};
    await saveSettings();
  }

  // ------------------------------------------------------------------ page API (server.Controller)
  async function home() {
    const s = await loadSettings();
    if (s.output && s.output.handle && !outputs.has(s.output.display)) outputs.set(s.output.display, s.output.handle);
    const recent = [];
    for (const item of s.recent) {
      if (!item.handle) continue;
      const known = roots.get(item.folder);
      let same = !known;
      try { same = same || await known.handle.isSameEntry(item.handle); } catch (err) { same = false; }
      if (!same) continue;  // another folder already shown under this name
      if (!known) roots.set(item.folder, {handle: item.handle, id: await rootIdFor(item.handle)});
      if (item.output && item.output_dir && !outputs.has(item.output_dir)) outputs.set(item.output_dir, item.output);
      recent.push({folder: item.folder, output_dir: item.output_dir, time: item.time, summary: await summaryOf(item.folder)});
    }
    return {title: TITLE, output_dir: s.output ? s.output.display : '', recent, config: Object.assign({}, s.options)};
  }

  async function options(payload) {
    const s = await loadSettings();
    for (const [key, value] of Object.entries(payload || {})) {
      if (!SCREEN_OPTIONS.includes(key) || typeof value !== typeof OPTIONS[key]) return {ok: false, error: 'bad option ' + key, status: 400};
      s.options[key] = value;
    }
    await saveSettings();
    return {ok: true, config: Object.assign({}, s.options)};
  }

  async function checkFolder(folder) {
    if (!folder) return [false, '사진 폴더를 지정하세요.'];
    adopt(folder, roots, false);
    const hit = rootOf(folder);
    if (!hit) return [false, '[폴더 고르기]로 사진 폴더를 고르세요. (브라우저는 입력한 경로를 직접 열 수 없습니다. 고른 뒤 이 칸에 전체 경로를 붙여 넣으면 표시용으로 씁니다)'];
    if ((await permission(hit.handle, 'read', false)) !== 'granted') return [true, '', 'grant'];
    try {
      await resolveDir(folder);  // a folder below the picked one: looked up once (listing it here would read it all)
    } catch (err) {
      return [false, '폴더를 찾을 수 없거나 접근할 수 없습니다.'];
    }
    return [true, ''];
  }

  async function check(folder, output, root) {
    folder = (folder || '').trim(); output = (output || '').trim(); root = (root || '').trim();
    if (root) adopt(root, roots, false);
    const label = folder ? resultLabel(folder, root) : '';
    const [folderOk, folderMsg, folderGrant] = await checkFolder(folder);
    const [outputOk, outputMsg, outputGrant] = await checkWritable(output);
    const needGrant = folderGrant === 'grant' || outputGrant === 'grant';
    const session = folderOk ? await summaryOf(folder) : null;
    let results = null, last = 0;
    const out = outputs.get(output);
    if (folder && outputOk && !outputGrant && out) {
      try {
        const names = await outputNames(out);
        results = resultsSummary(await readResults(out, names, label));
        last = await lastRound(out, names, label);
      } catch (err) { /* shown as no results */ }
    }
    const extra = folderOk && results ? await extraSession(folder) : null;
    return {folder_ok: folderOk, folder_msg: folderMsg, output_ok: outputOk, output_msg: outputMsg, need_grant: needGrant,
      folder, label, next_round: last + 1, session, results, extra_session: sessionSummary(extra)};
  }
  async function extraSession(folder) {
    const data = await readSession(sessionKey(folder, 'extra'));
    return data && !data.saved ? data : null;
  }

  async function folderTree(folder, rescan) {
    const dir = await resolveDir(folder);
    if (!tree || tree.root !== folder || rescan || tree.state === 'stopped' || tree.state === 'error') {
      if (tree) tree.cancel();
      tree = new FolderTree(folder, dir);
    }
    return tree;
  }

  async function treeCall(folder, output, rescan) {
    folder = (folder || '').trim(); output = (output || '').trim();
    const [ok, message, grantNeeded] = await checkFolder(folder);
    if (!ok) return {ok: false, error: message};
    if (grantNeeded) return {ok: false, need_grant: true, error: '폴더 접근 허용이 필요합니다.'};
    const out = (await folderTree(folder, rescan)).snapshot();
    const idx = await outputListing(output, rescan);
    for (const entry of out.entries) {
      entry.label = resultLabel(entry.path, folder);
      entry.results = idx[lower(entry.label)] || null;
      entry.session = await summaryOf(entry.path);
      const extra = await summaryOf(entry.path, 'extra');
      entry.extra_session = extra && !extra.saved ? extra : null;
    }
    return Object.assign(out, {ok: true, root: folder});
  }

  async function start(folder, output, resume, mode, root) {
    folder = (folder || '').trim(); output = (output || '').trim(); root = (root || '').trim();
    if (root && relParts(root, folder) === null) root = '';
    mode = mode === 'extra' ? 'extra' : '';
    const checked = await check(folder, output, root);
    if (!checked.folder_ok || !checked.output_ok) return {ok: false, error: checked.folder_msg || checked.output_msg};
    if (checked.need_grant) return {ok: false, error: '폴더 접근이 허용되지 않았습니다. [폴더 접근 허용]을 누르고 Edge 창에서 허용하세요.'};
    if (mode && !checked.results) return {ok: false, error: `저장 위치에 이 폴더의 이전 결과 파일(${checked.label}_n차리뷰_…_GOOD.txt / _REJECT.txt)이 없습니다.`};
    const next = new Job(folder, output, mode, root);
    if (job) job.close();
    job = next;
    if (tree) tree.cancel();  // the photo reads come first; a cut-short list is found again later
    await remember(root || folder, output);
    prepare(next, !!resume);
    return {ok: true, job: next.id};
  }

  async function prepare(j, resume) {
    try {
      const dir = await resolveDir(j.folder);
      const listed = tree ? tree.listing(j.folder) : null;  // listed a moment ago: not again
      let names, handles, dirs = [];
      if (listed) ({names, handles} = listed);
      else {
        ({names, handles, dirs} = await listDir(dir, n => { j.found = n; }, () => j.cancelled));
        if (tree && !j.cancelled) tree.update(j.folder, names);
      }
      if (j.cancelled) return;
      j.found = names.length;
      if (!names.length) {
        j.message = '사진이 없습니다 (jpg, jpeg, png, bmp, tif).' + (dirs.length ? '\n하위 폴더가 있으면 하위 폴더 목록이 나타난 뒤 목록에서 골라 시작하세요.' : '');
        j.phase = 'error';
        return;
      }
      const out = outputs.get(j.output);
      const outNames = await outputNames(out);
      let previous;
      if (j.mode === 'extra') {
        const results = await readResults(out, outNames, j.label);
        if (!results) throw new Error('이전 결과 파일을 읽을 수 없습니다.');
        const plan = planExtra(names, results);
        if (!plan.targets.length) { j.message = '추가로 검토할 REJECT 사진이 없습니다 (폴더의 사진이 모두 이미 GOOD입니다).'; j.phase = 'error'; return; }
        const position = new Map(names.map((n, i) => [n, i]));
        Object.assign(j, {allNames: names, baseGood: plan.base, missing: plan.missing, baseKey: results.key, baseRound: results.round, resultsTime: results.time});
        handles = plan.targets.map(n => handles[position.get(n)]);
        names = plan.targets;
        const fresh = new Set(plan.fresh);
        j.fresh = names.map((n, i) => (fresh.has(n) ? i : -1)).filter(i => i >= 0);
        previous = resume ? await extraSession(j.folder) : null;
      } else {
        previous = resume ? await readSession(sessionKey(j.folder)) : null;
        j.allNames = names;
        j.baseRound = await lastRound(out, outNames, j.label);
        const saved = (previous && previous.saved) || {};
        if (saved.round && saved.when && saved.output_dir === j.output && (saved.label || nameOf(j.folder)) === j.label) j.own = [saved.round, saved.when];
      }
      const session = new Session(sessionKey(j.folder, j.mode), j.folder, j.output, names, previous, j.mode);
      const cache = new ImageCache(dir, names, handles, session.cursor);
      if (j.cancelled) { cache.close(); return; }
      Object.assign(j, {names, session, cache, thumbs: new Thumbnails(cache), phase: 'ready'});
    } catch (err) {
      console.warn('prepare failed', err);
      j.message = '폴더를 읽을 수 없습니다: ' + errText(err);
      j.phase = 'error';
    }
  }

  function state() {
    if (!job) return {phase: 'idle'};
    const j = job;
    const out = {phase: j.phase, job: j.id, found: j.found, message: j.message, folder: j.folder, output_dir: j.output, label: j.label,
      root: j.root, parts: j.root ? relParts(j.root, j.folder) || [] : [], round: j.own ? j.own[0] : j.baseRound + 1};
    if (j.phase === 'ready') {
      Object.assign(out, j.session.state());
      out.stats = j.cache.stats();
      out.mode = j.mode;
      if (j.mode === 'extra') {
        out.extra = {base_good: j.baseGood.length, total: j.allNames.length, fresh: j.fresh, missing: j.missing,
          results_time: j.resultsTime, results_round: j.baseRound};
      }
    }
    return out;
  }

  function sync(payload) {
    const j = current(payload.job);
    const before = new Set(j.session.good);
    if (j.session.apply(payload)) {
      for (const i of j.session.good) if (!before.has(i)) j.thumbs.want(i);
      if ('cursor' in payload) j.cache.setCursor(payload.cursor);
    }
    return {ok: true, seq: j.session.seq, stats: j.cache.stats()};
  }

  async function save(payload) {
    const j = current(payload.job);
    const output = (payload.output_dir || j.output).trim();
    if (Array.isArray(payload.good)) j.session.setGood(payload.good.map(Number));
    const [ok, message, grantNeeded] = await checkWritable(output);
    if (!ok) return {ok: false, error: message};
    if (grantNeeded && (await permission(outputs.get(output), 'readwrite', true)) !== 'granted') {
      return {ok: false, error: '결과 저장 위치에 쓰기가 허용되지 않았습니다.'};
    }
    let result;
    try {
      const same = output === j.output;
      const picked = [...j.session.good].sort((a, b) => a - b).map(i => j.names[i]);
      result = await saveRound(outputs.get(output), output, j.allNames, picked, {
        baseGood: j.mode === 'extra' ? j.baseGood : null, baseKey: same ? j.baseKey : null, own: same ? j.own : null,
        mergeNewer: !!payload.overwrite, minRound: j.baseRound + 1, label: j.label});
    } catch (err) {
      return {ok: false, error: '결과 파일을 쓰지 못했습니다: ' + errText(err)};
    }
    if (result.ok) {
      index = {output: null, t: 0, value: {}};  // the subfolder list shows this round when the page asks next
      if (output !== j.output) { j.output = j.session.output = output; await remember(j.root || j.folder, output); }
      j.own = [result.round, result.when];
      const base = result.base;
      delete result.base;
      if (j.mode === 'extra') j.baseGood = base;  // merged with a newer result: saving again keeps that base
      j.session.saved = {good: result.good_count, reject: result.reject_count, round: result.round, when: result.when,
        output_dir: output, label: j.label, time: clock()};
      await j.session.save(true);
      result.output_dir = output;
    }
    return result;
  }

  function refresh(jobId) {
    const cache = current(jobId).cache;
    cache.refresh();
    return {ok: true, stats: cache.stats()};
  }

  function newJob() {
    if (job) job.close();
    job = null;
    return {ok: true};
  }

  // v8 overview: every photo folder's latest saved round under a parent folder, GOOD and REJECT names
  async function overview(folder, output, rescan) {
    folder = (folder || '').trim(); output = (output || '').trim();
    const [ok, message, grantNeeded] = await checkFolder(folder);
    if (!ok) return {ok: false, error: message};
    if (grantNeeded) return {ok: false, error: '폴더 접근 허용이 필요합니다.'};
    const out = outputs.get(output);
    if (!out || (await permission(out, 'readwrite', false)) !== 'granted') return {ok: false, error: '결과 저장 위치 폴더가 없거나 접근할 수 없습니다.'};
    const t = await folderTree(folder, rescan);
    const snap = t.snapshot();
    if (snap.state === 'running') return {ok: true, state: 'running', listed: snap.listed, found: snap.entries.length};
    const outNames = await outputNames(out);
    const idx = resultsIndex(outNames);
    const folders = [], photos = [];
    for (const entry of snap.entries) {
      const label = resultLabel(entry.path, folder);
      const results = idx[lower(label)] ? await readResults(out, outNames, label) : null;
      const row = {path: entry.path, parts: entry.parts, count: entry.count, label, first: photos.length, good: [], reject: [], round: 0, time: '',
        session: await summaryOf(entry.path)};
      if (results) {
        Object.assign(row, {good: results.good, reject: results.reject, round: results.round, time: results.time});
        for (const name of [...results.good, ...results.reject]) photos.push([entry.path, name]);
      }
      folders.push(row);
    }
    overviewView = {id: token(), photos};
    overviewUrls.clear();
    return {ok: true, state: snap.state, id: overviewView.id, root: folder, output_dir: output, folders, failed: snap.failed};
  }
  async function overviewBlob(id, g) {
    if (!overviewView || overviewView.id !== id || !(g >= 0 && g < overviewView.photos.length)) throw new StaleError('전체 결과 목록이 바뀌었습니다.');
    const [path, name] = overviewView.photos[g];
    try {
      const dir = await resolveDir(path);
      const file = await (await dir.getFileHandle(name)).getFile();
      return new Blob([await file.arrayBuffer()], {type: mimeOf(name)});
    } catch (err) {
      throw new ReadError('읽기 실패: ' + errText(err));
    }
  }

  // ------------------------------------------------------------------ for the screen
  async function call(name, body = {}) {
    try {
      await loadSettings();
      switch (name) {
        case 'home': return await home();
        case 'options': return await options(body);
        case 'check': return await check(body.folder, body.output_dir, body.root);
        case 'tree': return await treeCall(body.folder, body.output_dir, !!body.rescan);
        case 'start': return await start(body.folder, body.output_dir, body.resume, body.mode || '', body.root);
        case 'state': return state();
        case 'sync': return sync(body);
        case 'refresh': return refresh(body.job);
        case 'save': return await save(body);
        case 'new': return newJob();
        case 'overview': return await overview(body.folder, body.output_dir, !!body.rescan);
      }
      return {ok: false, error: 'unknown request ' + name, status: 404};
    } catch (err) {
      if (err && err.stale) return {ok: false, stale: true, error: err.message, status: 409};
      console.warn(name, 'failed', err);
      return {ok: false, error: errText(err), status: 500};
    }
  }

  return {
    title: TITLE, call, pick, grant, bitmap, displayable, mimeOf,
    // a photo of the job (Blob); errors carry kind 'offline' | 'read'
    image: (jobId, i) => current(jobId).cache.get(i),
    peek: (jobId, i) => (job && job.id === jobId && job.cache ? job.cache.peek(i) : null),
    thumbUrl: (jobId, i) => current(jobId).thumbs.url(i),
    async overviewThumbUrl(id, g) {
      const key = id + '/' + g, done = overviewUrls.get(key);
      if (done) return done;
      return overviewUrls.set(key, URL.createObjectURL(await thumbnail(await overviewBlob(id, g))));
    },
    async overviewImageUrl(id, g) { return URL.createObjectURL(await displayable(await overviewBlob(id, g))); },
    async useRecent(folder) {  // a click on a recent item: ask Edge for access again in one go
      const s = await loadSettings();
      const item = s.recent.find(x => x.folder === folder);
      if (!item) return null;
      await grant(item.folder, item.output_dir);
      return {folder: item.folder, output_dir: item.output_dir || ''};
    },
    debug: () => ({job, tree, roots, outputs, settings}),  // read by the automated tests
  };
})();
