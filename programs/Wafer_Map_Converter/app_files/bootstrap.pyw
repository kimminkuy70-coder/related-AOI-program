from pathlib import Path
import importlib.util,json,os,subprocess,sys,threading,time,tkinter as tk
from tkinter import messagebox
BASE=Path(__file__).resolve().parent
REQ=BASE/'requirements.txt';MARK=BASE/'.setup_complete.json';LOG=BASE/'setup_install.log'
NO_WINDOW=0x08000000 if os.name=='nt' else 0
REQUIRED=('webview','openpyxl','numpy','matplotlib')
class Bootstrap:
 def __init__(self):
  self.root=tk.Tk();self.root.title('Wafer Map Converter WebView2 v4');self.root.geometry('540x235');self.root.resizable(False,False);self.root.configure(bg='#0b1220')
  tk.Label(self.root,text='WAFER MAP CONVERTER',bg='#0b1220',fg='#eef6ff',font=('Segoe UI',17,'bold')).pack(anchor='w',padx=28,pady=(26,2))
  tk.Label(self.root,text='MAP DATA WORKFLOW · WEBVIEW2 v4',bg='#0b1220',fg='#21c55d',font=('Segoe UI',9,'bold')).pack(anchor='w',padx=28)
  self.status=tk.StringVar(value='실행 환경 확인 중...');tk.Label(self.root,textvariable=self.status,bg='#0b1220',fg='#9fb0c3',font=('Segoe UI',10),wraplength=480,justify='left').pack(anchor='w',padx=28,pady=(27,8))
  self.elapsed=tk.StringVar(value='경과 00:00');tk.Label(self.root,textvariable=self.elapsed,bg='#0b1220',fg='#60758a',font=('Consolas',9)).pack(anchor='w',padx=28)
  self.started=time.time();self.tick();threading.Thread(target=self.prepare,daemon=True).start()
 def tick(self):
  sec=int(time.time()-self.started);self.elapsed.set(f'경과 {sec//60:02d}:{sec%60:02d}');self.root.after(500,self.tick)
 def set_status(self,text):self.root.after(0,self.status.set,text)
 def marker_ok(self):
  try:
   d=json.loads(MARK.read_text(encoding='utf-8'));return d.get('python')==str(Path(sys.executable).resolve()) and d.get('requirements')==REQ.stat().st_mtime_ns
  except Exception:return False
 def prepare(self):
  try:
   if not self.marker_ok():
    missing=[x for x in REQUIRED if importlib.util.find_spec(x) is None]
    if missing:
     self.set_status('최초 1회 패키지 설치 중: '+', '.join(missing))
     with LOG.open('w',encoding='utf-8') as log:r=subprocess.run([sys.executable,'-m','pip','install','--user','-r',str(REQ),'--disable-pip-version-check'],cwd=BASE,creationflags=NO_WINDOW,stdout=log,stderr=subprocess.STDOUT,check=False)
     if r.returncode:raise RuntimeError('패키지 설치 실패. setup_install.log를 확인하세요.')
    remaining=[x for x in REQUIRED if importlib.util.find_spec(x) is None]
    if remaining:raise RuntimeError('필수 패키지 누락: '+', '.join(remaining))
    MARK.write_text(json.dumps({'python':str(Path(sys.executable).resolve()),'requirements':REQ.stat().st_mtime_ns,'completed':time.strftime('%Y-%m-%d %H:%M:%S')},ensure_ascii=False,indent=2),encoding='utf-8')
   self.set_status('WebView2 프로그램 시작 중...')
   exe=Path(sys.executable);pyw=exe.with_name('pythonw.exe');exe=pyw if pyw.exists() else exe
   subprocess.Popen([str(exe),str(BASE/'app.py')],cwd=BASE,creationflags=NO_WINDOW,close_fds=True)
   self.root.after(350,self.root.destroy)
  except Exception as exc:
   self.root.after(0,lambda:messagebox.showerror('Wafer Map Converter WebView2 v4',str(exc)));self.root.after(0,self.root.destroy)
if __name__=='__main__':Bootstrap().root.mainloop()
