# -*- coding: utf-8 -*-
from pathlib import Path
import json, logging, os, sys, threading, time
import runtime

MANIFEST = runtime.load_manifest()
APP_TITLE = MANIFEST['title']
UI_DIR = Path(__file__).parent / 'ui'

# pywebview exposes every public attribute of the js_api object to JS and walks
# non-callable ones recursively. Everything that is not a JS-callable method is
# therefore private ('_'), above all the window: walking window.native (the WinForms
# form and its .NET object tree) is what froze v15 at "Python API 연결 준비 중".
class API:
    def __init__(self, webview, engine):
        self._webview=webview; self._engine=engine
        self._window=None; self._html=''; self._root=None; self._wafers=[]
        self._cancel_event=threading.Event(); self._scan_cancel=threading.Event(); self._shutdown_started=threading.Event()
        self._lock=threading.RLock(); self._threads=set(); self._accept_jobs=True
        self._state={'status':'idle','scan_status':'idle','logs':[],'percent':0}
    def _log(self,msg):
        with self._lock:self._state['logs']=(self._state.get('logs',[])+['['+time.strftime('%H:%M:%S')+'] '+msg])[-250:]
    def _start_thread(self,target,args=(),name='worker'):
        def runner():
            try:target(*args)
            finally:
                with self._lock:self._threads.discard(threading.current_thread())
        thread=threading.Thread(target=runner,name=name,daemon=True)
        with self._lock:self._threads.add(thread)
        thread.start(); return thread
    def _available(self):
        return self._accept_jobs and not self._shutdown_started.is_set()
    def choose_folder(self):
        if not self._available():return {'cancelled':True}
        result=self._window.create_file_dialog(self._webview.FileDialog.FOLDER,allow_multiple=False)
        if not result:return {'cancelled':True}
        self._root=Path(result[0]);self._wafers=[];self._scan_cancel.clear()
        with self._lock:self._state.update({'scan_status':'running','scan_message':'선택한 폴더 확인 중','scan_current':str(self._root),'scan_folders':0,'scan_found':0,'scan_queue':0})
        self._start_thread(self._scan,name='folder-scan')
        return {'cancelled':False,'root':str(self._root),'default_output':str(self._root/self._engine.RESULT_FOLDER)}
    def _scan_callback(self,stage,path,scanned,found,queued):
        if self._shutdown_started.is_set():return
        labels={'scanning':'하위 폴더 검색 중','found':'Wafer 폴더 발견','complete':'검색 완료'}
        with self._lock:self._state.update({'scan_status':'complete' if stage=='complete' else 'running','scan_message':labels.get(stage,stage),'scan_current':str(path),'scan_folders':scanned,'scan_found':found,'scan_queue':queued})
    def _scan(self):
        try:
            wafers=self._engine.discover(self._root,self._scan_callback,self._scan_cancel);self._wafers=wafers
            if not self._shutdown_started.is_set():
                with self._lock:self._state.update({'scan_status':'complete','wafers':[{'name':x.name,'path':str(x)} for x in wafers]})
                self._log(f'Wafer {len(wafers)}개 검색 완료')
        except Exception as exc:
            if not self._shutdown_started.is_set():
                with self._lock:self._state.update({'scan_status':'error','scan_message':str(exc),'wafers':[]})
    def cancel_scan(self):self._scan_cancel.set();return True
    def choose_output(self):
        if not self._available():return ''
        result=self._window.create_file_dialog(self._webview.FileDialog.FOLDER,allow_multiple=False);return str(result[0]) if result else ''
    def start(self,paths,custom_output=''):
        if not self._available():return {'ok':False,'error':'프로그램이 종료 중입니다.'}
        if not paths:return {'ok':False,'error':'처리할 Wafer를 선택하세요.'}
        output=Path(custom_output) if custom_output else self._root/self._engine.RESULT_FOLDER;output.mkdir(parents=True,exist_ok=True);self._cancel_event.clear()
        with self._lock:self._state.update({'status':'running','result_root':str(output),'wafer_total':len(paths),'logs':[],'percent':0})
        self._start_thread(self._worker,(paths,output),'conversion-worker');return {'ok':True}
    def _progress(self,wi,wt,ii,it,wafer,current,message,phase='image',ratio=0):
        if self._shutdown_started.is_set():return
        wafer_ratio=.82*ratio if phase=='image' else .82+.18*ratio;overall=((wi-1)+wafer_ratio)/max(1,wt)*100
        with self._lock:self._state.update({'wafer_index':wi,'wafer_total':wt,'image_index':ii,'image_total':it,'current_wafer':wafer,'current_file':current,'message':message,'phase':phase,'percent':round(overall,2)})
    def _worker(self,paths,output):
        try:
            results=[]
            for index,path in enumerate(paths,1):
                if self._cancel_event.is_set() or self._shutdown_started.is_set():break
                results.append(self._engine.process_wafer(Path(path),output,self._progress,self._log,self._cancel_event,index,len(paths)))
            if not self._shutdown_started.is_set():
                with self._lock:self._state.update({'status':'complete' if not self._cancel_event.is_set() else 'cancelled','percent':100 if not self._cancel_event.is_set() else self._state.get('percent',0),'results':results})
        except Exception as exc:
            logging.exception('conversion failed')
            if not self._shutdown_started.is_set():
                self._log('ERROR '+str(exc));
                with self._lock:self._state.update({'status':'error','message':str(exc)})
    def get_state(self):
        with self._lock:return json.loads(json.dumps(self._state,default=str))
    def cancel_job(self):self._cancel_event.set();return True
    def open_result(self):
        if not self._available():return False
        path=self._state.get('result_root')
        if path and Path(path).exists():os.startfile(path);return True
        return False
    def new_job(self):
        # Reload the inline page through pywebview; location.reload() cannot reload an HTML string.
        if not self._available():return False
        with self._lock:
            if self._state.get('status')=='running' or self._state.get('scan_status')=='running':return False
            self._root=None;self._wafers=[];self._state={'status':'idle','scan_status':'idle','logs':[],'percent':0}
        self._window.load_html(self._html);return True
    def _request_shutdown(self):
        if self._shutdown_started.is_set():return
        self._shutdown_started.set();self._accept_jobs=False;self._scan_cancel.set();self._cancel_event.set()
        with self._lock:self._state.update({'status':'shutting_down','scan_status':'cancelled','message':'프로그램 종료 중'})
    def _wait_threads(self,timeout=2.5):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            with self._lock:alive=[t for t in self._threads if t.is_alive() and t is not threading.current_thread()]
            if not alive:return
            for thread in alive:thread.join(timeout=min(.15,max(0,deadline-time.monotonic())))

def main():
    runtime.setup_logging(MANIFEST['app_id'])
    instance=runtime.SingleInstance(MANIFEST['app_id'])
    if not instance.acquired():
        if not runtime.focus_window(APP_TITLE):
            runtime.message_box(APP_TITLE,'프로그램이 이미 실행 중(또는 시작 중)입니다.',error=False)
        return
    missing=runtime.missing_modules(MANIFEST)
    if missing and runtime.request_repair(MANIFEST,'missing: '+', '.join(missing)):return
    try:
        import webview
        import engine
    except ImportError as exc:
        if runtime.is_dependency_error(exc,MANIFEST) and runtime.request_repair(MANIFEST,exc):return
        raise
    job=runtime.WindowsJob()
    api=API(webview,engine);api._html=runtime.inline_ui(UI_DIR)
    window=webview.create_window(APP_TITLE,html=api._html,js_api=api,width=1180,height=820,min_size=(980,700),background_color='#0b1220');api._window=window
    def on_closing():api._request_shutdown();return True
    def on_closed():api._request_shutdown()
    window.events.closing+=on_closing;window.events.closed+=on_closed
    try:
        webview.start(gui='edgechromium',debug=os.environ.get('AOI_TOOLS_DEBUG')=='1',private_mode=False,storage_path=runtime.webview_storage(MANIFEST['app_id']))
    finally:
        api._request_shutdown();api._wait_threads(2.5);job.close();instance.close();os._exit(0)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        logging.exception('startup failed')
        runtime.message_box(APP_TITLE,f'프로그램 시작 중 오류가 발생했습니다.\n{exc}\n\n로그: {runtime.TOOLS_ROOT / "logs"}')
        os._exit(1)
