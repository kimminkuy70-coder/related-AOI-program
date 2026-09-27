# -*- coding: utf-8 -*-
from pathlib import Path
import json, os, threading, time, webview
from engine import discover, process_wafer, RESULT_FOLDER

class API:
    def __init__(self):
        self.window=None; self.root=None; self.wafers=[]
        self.cancel_event=threading.Event(); self.scan_cancel=threading.Event(); self.shutdown_started=threading.Event()
        self.lock=threading.RLock(); self.threads=set(); self.accept_jobs=True
        self.state={'status':'idle','scan_status':'idle','logs':[],'percent':0}
    def log(self,msg):
        with self.lock:self.state['logs']=(self.state.get('logs',[])+['['+time.strftime('%H:%M:%S')+'] '+msg])[-250:]
    def _start_thread(self,target,args=(),name='worker'):
        def runner():
            try:target(*args)
            finally:
                with self.lock:self.threads.discard(threading.current_thread())
        thread=threading.Thread(target=runner,name=name,daemon=True)
        with self.lock:self.threads.add(thread)
        thread.start(); return thread
    def _available(self):
        return self.accept_jobs and not self.shutdown_started.is_set()
    def choose_folder(self):
        if not self._available():return {'cancelled':True}
        result=self.window.create_file_dialog(webview.FileDialog.FOLDER,allow_multiple=False)
        if not result:return {'cancelled':True}
        self.root=Path(result[0]);self.wafers=[];self.scan_cancel.clear()
        with self.lock:self.state.update({'scan_status':'running','scan_message':'선택한 폴더 확인 중','scan_current':str(self.root),'scan_folders':0,'scan_found':0,'scan_queue':0})
        self._start_thread(self._scan,name='folder-scan')
        return {'cancelled':False,'root':str(self.root),'default_output':str(self.root/RESULT_FOLDER)}
    def _scan_callback(self,stage,path,scanned,found,queued):
        if self.shutdown_started.is_set():return
        labels={'scanning':'하위 폴더 검색 중','found':'Wafer 폴더 발견','complete':'검색 완료'}
        with self.lock:self.state.update({'scan_status':'complete' if stage=='complete' else 'running','scan_message':labels.get(stage,stage),'scan_current':str(path),'scan_folders':scanned,'scan_found':found,'scan_queue':queued})
    def _scan(self):
        try:
            wafers=discover(self.root,self._scan_callback,self.scan_cancel);self.wafers=wafers
            if not self.shutdown_started.is_set():
                with self.lock:self.state.update({'scan_status':'complete','wafers':[{'name':x.name,'path':str(x)} for x in wafers]})
                self.log(f'Wafer {len(wafers)}개 검색 완료')
        except Exception as exc:
            if not self.shutdown_started.is_set():
                with self.lock:self.state.update({'scan_status':'error','scan_message':str(exc),'wafers':[]})
    def cancel_scan(self):self.scan_cancel.set();return True
    def choose_output(self):
        if not self._available():return ''
        result=self.window.create_file_dialog(webview.FileDialog.FOLDER,allow_multiple=False);return str(result[0]) if result else ''
    def start(self,paths,custom_output=''):
        if not self._available():return {'ok':False,'error':'프로그램이 종료 중입니다.'}
        if not paths:return {'ok':False,'error':'처리할 Wafer를 선택하세요.'}
        output=Path(custom_output) if custom_output else self.root/RESULT_FOLDER;output.mkdir(parents=True,exist_ok=True);self.cancel_event.clear()
        with self.lock:self.state.update({'status':'running','result_root':str(output),'wafer_total':len(paths),'logs':[],'percent':0})
        self._start_thread(self._worker,(paths,output),'conversion-worker');return {'ok':True}
    def progress(self,wi,wt,ii,it,wafer,current,message,phase='image',ratio=0):
        if self.shutdown_started.is_set():return
        wafer_ratio=.82*ratio if phase=='image' else .82+.18*ratio;overall=((wi-1)+wafer_ratio)/max(1,wt)*100
        with self.lock:self.state.update({'wafer_index':wi,'wafer_total':wt,'image_index':ii,'image_total':it,'current_wafer':wafer,'current_file':current,'message':message,'phase':phase,'percent':round(overall,2)})
    def _worker(self,paths,output):
        try:
            results=[]
            for index,path in enumerate(paths,1):
                if self.cancel_event.is_set() or self.shutdown_started.is_set():break
                results.append(process_wafer(Path(path),output,self.progress,self.log,self.cancel_event,index,len(paths)))
            if not self.shutdown_started.is_set():
                with self.lock:self.state.update({'status':'complete' if not self.cancel_event.is_set() else 'cancelled','percent':100 if not self.cancel_event.is_set() else self.state.get('percent',0),'results':results})
        except Exception as exc:
            if not self.shutdown_started.is_set():
                self.log('ERROR '+str(exc));
                with self.lock:self.state.update({'status':'error','message':str(exc)})
    def get_state(self):
        with self.lock:return json.loads(json.dumps(self.state,default=str))
    def cancel_job(self):self.cancel_event.set();return True
    def open_result(self):
        if not self._available():return False
        path=self.state.get('result_root')
        if path and Path(path).exists():os.startfile(path);return True
        return False
    def request_shutdown(self):
        if self.shutdown_started.is_set():return
        self.shutdown_started.set();self.accept_jobs=False;self.scan_cancel.set();self.cancel_event.set()
        with self.lock:self.state.update({'status':'shutting_down','scan_status':'cancelled','message':'프로그램 종료 중'})
    def wait_threads(self,timeout=2.5):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            with self.lock:alive=[t for t in self.threads if t.is_alive() and t is not threading.current_thread()]
            if not alive:return
            for thread in alive:thread.join(timeout=min(.15,max(0,deadline-time.monotonic())))

api=None
def main():
    global api
    api=API();ui=Path(__file__).parent/'ui'/'index.html'
    # Inline HTML avoids a persistent local HTTP server entirely.
    html=ui.read_text(encoding='utf-8')
    css=(ui.parent/'styles.css').read_text(encoding='utf-8')
    js=(ui.parent/'app.js').read_text(encoding='utf-8')
    html=html.replace('<link rel="stylesheet" href="styles.css">','<style>'+css+'</style>').replace('<script src="app.js"></script>','<script>'+js+'</script>')
    window=webview.create_window('AOI Color-Gray Matcher v15',html=html,js_api=api,width=1180,height=820,min_size=(980,700),background_color='#0b1220');api.window=window
    def on_closing():api.request_shutdown();return True
    def on_closed():api.request_shutdown()
    window.events.closing+=on_closing;window.events.closed+=on_closed
    try:
        webview.start(gui='edgechromium',debug=False)
    finally:
        api.request_shutdown();api.wait_threads(2.5);os._exit(0)
if __name__=='__main__':main()
