let ready = false;
const $ = id => document.getElementById(id);

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

$('choose').onclick = async () => {
  const r = await pywebview.api.choose_folder();
  if (r.cancelled) return;
  $('rootPath').textContent = r.root;
};
