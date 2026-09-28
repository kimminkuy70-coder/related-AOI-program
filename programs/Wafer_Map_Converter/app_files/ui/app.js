let step = 1, root = '', items = [], ready = false, mode = 'txt', outputDir = '';
let results = [], gallery = [], viewIndex = 0;
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const dirname = p => p.replace(/[\\/][^\\/]*$/, '');
const basename = p => p.replace(/^.*[\\/]/, '');

function activate() {
  if (ready) return;
  ready = true;
  $('bridge').textContent = 'WebView2 연결됨';
  $('choose').disabled = false;
  $('boot').remove();
  $('status').textContent = '준비 완료';
}
window.addEventListener('pywebviewready', activate);
setInterval(() => { if (window.pywebview?.api?.get_state) activate(); }, 350);

function show(n) {
  step = Math.max(1, Math.min(5, n));
  document.querySelectorAll('.panel').forEach(x => x.classList.remove('show'));
  $('s' + step).classList.add('show');
  document.querySelectorAll('nav span').forEach((x, i) => x.classList.toggle('active', i + 1 === step));
  $('previous').style.visibility = step === 1 || step >= 4 ? 'hidden' : 'visible';
  $('next').style.visibility = step >= 3 ? 'hidden' : 'visible';
}
function move(d) {
  if (d > 0 && step === 2 && !root) return alert('폴더를 선택하세요.');
  show(step + d);
}
$('next').onclick = () => move(1);
$('previous').onclick = () => move(-1);
document.querySelectorAll('[name=mode]').forEach(x => x.onchange = () => mode = x.value);

// 02 folder scan
$('choose').onclick = async () => {
  const r = await pywebview.api.choose_folder(mode);
  if (r.cancelled) return;
  root = r.root;
  $('rootPath').textContent = root;
  $('scan').classList.remove('hidden');
  pollScan();
};
async function pollScan() {
  const s = await pywebview.api.get_state();
  $('scanMsg').textContent = s.scan_message || '검색 중';
  $('scanPath').textContent = s.scan_current || root;
  $('found').textContent = s.found || 0;
  if (s.scan === 'complete') { items = s.items || []; render(); show(3); return; }
  if (s.scan === 'error') { alert(s.scan_message); return; }
  setTimeout(pollScan, 300);
}

// 03 file selection + output location
function render() {
  const q = $('filter').value.toLowerCase().trim();
  $('list').innerHTML = items.map((x, i) => {
    const hay = (x.wafer + x.device + x.lot + x.relative).toLowerCase();
    if (q && !hay.includes(q)) return '';
    const tags = Object.entries(x.bins || {}).map(([k, v]) => `${k}:${v}`).join(' · ');
    return `<label class="file"><input type="checkbox" data-id="${i}" ${x.valid ? 'checked' : 'disabled'} onchange="counts()"><div><b>${esc(x.wafer)}</b><small>${esc(x.relative)}</small></div><div><b>${esc(x.device || '-')}</b><small>${esc(x.lot || x.error || '')}</small></div><span class="tags">${esc(tags || x.size)}</span></label>`;
  }).join('');
  $('total').textContent = items.length;
  counts();
}
function counts() { $('selected').textContent = document.querySelectorAll('.file input:checked').length; }
function selectAll(v) { document.querySelectorAll('.file input:not(:disabled)').forEach(x => x.checked = v); counts(); }
$('filter').oninput = render;
$('chooseOutput').onclick = async () => {
  const dir = await pywebview.api.choose_output();
  if (!dir) return;
  outputDir = dir;
  $('outputPath').textContent = dir;
  document.querySelector('[name=save][value=custom]').checked = true;
};
$('start').onclick = async () => {
  const custom = document.querySelector('[name=save]:checked').value === 'custom';
  if (custom && !outputDir) return alert('저장 위치를 선택하세요.');
  const ids = [...document.querySelectorAll('.file input:checked')].map(x => +x.dataset.id);
  const r = await pywebview.api.start(ids, custom ? outputDir : '');
  if (!r.ok) return alert(r.error);
  show(4);
  pollJob();
};

// 04 progress
async function pollJob() {
  const s = await pywebview.api.get_state();
  $('fill').style.width = (s.percent || 0) + '%';
  $('percent').textContent = (s.percent || 0).toFixed(1) + '%';
  $('jobTitle').textContent = s.message || '변환 중';
  $('current').textContent = s.current || '';
  $('logs').textContent = (s.results || []).map(x => '✓ ' + x.output).concat((s.errors || []).map(x => '✕ ' + x.path + ' · ' + x.error)).join('\n');
  if (s.run === 'complete' || s.run === 'cancelled') { finish(s); return; }
  setTimeout(pollJob, 350);
}
async function cancelJob() { await pywebview.api.cancel_job(); }
async function openRoot() { await pywebview.api.open_root(); }

// 05 completion: result cards + image viewer
function finish(s) {
  results = s.results || [];
  const errors = s.errors || [];
  const where = s.output_root ? s.output_root + ' (원본 하위 폴더 구조 유지)' : '원본 맵 파일과 같은 폴더';
  $('done').innerHTML = `<b>상태</b><span>${s.run === 'complete' ? '완료' : '취소됨'}</span><b>성공 / 실패</b><span>${results.length}개 / ${errors.length}개</span><b>저장 위치</b><span>${esc(where)}</span><b>맵 이미지</b><span>파일마다 Bin Code Map · Bin Meaning Map 2장 (결과 파일과 같은 폴더)</span>`;
  gallery = [];
  results.forEach((r, ri) => r.images.forEach(img => gallery.push({ri, kind: img.kind, path: img.path})));
  renderResults();
  $('failures').innerHTML = errors.length ? `<h3>변환 실패 ${errors.length}개</h3>` + errors.map(e => `<div class="fail"><b>${esc(e.relative || e.path)}</b><small>${esc(e.error)}</small></div>`).join('') : '';
  show(5);
}
function renderResults() {
  const q = $('resultFilter').value.toLowerCase().trim();
  const outLabel = mode === 'txt' ? 'Excel 열기' : 'TXT 열기';
  $('results').innerHTML = results.map((r, ri) => {
    const hay = (r.wafer + r.lot + r.source_relative + r.output).toLowerCase();
    if (q && !hay.includes(q)) return '';
    const thumbs = r.images.map(img => {
      const gi = gallery.findIndex(g => g.path === img.path);
      return `<figure data-gi="${gi}"><img data-path="${esc(img.path)}" alt=""><figcaption>${esc(img.kind)}<small>${esc(basename(img.path))}</small></figcaption></figure>`;
    }).join('');
    return `<article class="result"><div class="rhead"><b>${esc(r.wafer)}</b><span class="badge">${esc(r.source_type)} → ${esc(r.output_type)} + 이미지</span></div>
<dl><dt>원본 맵 파일</dt><dd title="${esc(r.source)}">${esc(r.source_relative)}</dd><dt>결과 파일</dt><dd>${esc(r.output_name)}</dd><dt>저장 폴더</dt><dd>${esc(r.folder)}</dd></dl>
<div class="thumbs">${thumbs}</div>
<div class="ractions"><button data-open="${ri}">${outLabel}</button>${mode === 'excel' ? `<button class="ghost" data-source="${ri}">원본 Excel 열기</button>` : ''}<button class="ghost" data-folder="${ri}">폴더에서 보기</button></div></article>`;
  }).join('') || '<p class="empty">표시할 결과가 없습니다.</p>';
  observeThumbs();
}
$('resultFilter').oninput = renderResults;
$('results').onclick = e => {
  const fig = e.target.closest('figure');
  if (fig) return openViewer(+fig.dataset.gi);
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.open) pywebview.api.open_file(results[+b.dataset.open].output);
  if (b.dataset.source) pywebview.api.open_file(results[+b.dataset.source].source);
  if (b.dataset.folder) pywebview.api.show_in_folder(results[+b.dataset.folder].output);
};

// Thumbnails load only when visible, two at a time, so many maps stay responsive.
let thumbQueue = [], thumbBusy = 0, thumbObserver = null;
function observeThumbs() {
  thumbObserver?.disconnect();
  thumbQueue = [];
  thumbObserver = new IntersectionObserver(entries => entries.forEach(en => {
    if (!en.isIntersecting) return;
    thumbObserver.unobserve(en.target);
    thumbQueue.push(en.target);
    pumpThumbs();
  }), {rootMargin: '300px'});
  document.querySelectorAll('.thumbs img[data-path]').forEach(img => thumbObserver.observe(img));
}
async function pumpThumbs() {
  while (thumbBusy < 2 && thumbQueue.length) {
    const img = thumbQueue.shift();
    thumbBusy++;
    pywebview.api.get_image(img.dataset.path, true).then(src => {
      if (src) img.src = src; else img.closest('figure').classList.add('missing');
    }).finally(() => { thumbBusy--; pumpThumbs(); });
  }
}

async function openViewer(i) {
  if (!gallery.length) return;
  viewIndex = (i + gallery.length) % gallery.length;
  const g = gallery[viewIndex], r = results[g.ri];
  $('viewer').classList.remove('hidden');
  $('vTitle').textContent = `${r.wafer} · ${g.kind}`;
  $('vSource').textContent = `원본 맵: ${r.source}  →  결과: ${r.output_name}`;
  $('vPath').textContent = `이미지 위치: ${g.path}`;
  $('vCount').textContent = `${viewIndex + 1} / ${gallery.length}`;
  $('vImg').removeAttribute('src');
  $('vLoading').style.display = 'block';
  const want = viewIndex;
  const src = await pywebview.api.get_image(g.path, false);
  if (want !== viewIndex) return;  // user moved on while loading
  $('vLoading').style.display = src ? 'none' : 'block';
  if (src) $('vImg').src = src; else $('vLoading').textContent = '이미지를 찾을 수 없습니다.';
}
function closeViewer() { $('viewer').classList.add('hidden'); $('vBody').classList.remove('actual'); $('vFit').textContent = '원본 크기'; }
$('vPrev').onclick = () => openViewer(viewIndex - 1);
$('vNext').onclick = () => openViewer(viewIndex + 1);
$('vClose').onclick = closeViewer;
$('vOpen').onclick = () => pywebview.api.open_file(gallery[viewIndex].path);
$('vFolder').onclick = () => pywebview.api.show_in_folder(gallery[viewIndex].path);
function toggleFit() {
  const actual = $('vBody').classList.toggle('actual');
  $('vFit').textContent = actual ? '화면 맞춤' : '원본 크기';
}
$('vFit').onclick = toggleFit;
$('vImg').onclick = toggleFit;
document.addEventListener('keydown', e => {
  if ($('viewer').classList.contains('hidden')) return;
  if (e.key === 'ArrowLeft') openViewer(viewIndex - 1);
  else if (e.key === 'ArrowRight') openViewer(viewIndex + 1);
  else if (e.key === 'Escape') closeViewer();
});

show(1);
