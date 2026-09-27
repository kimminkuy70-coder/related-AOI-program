# -*- coding: utf-8 -*-
from pathlib import Path
import ctypes
from ctypes import wintypes
import importlib.util
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox

BASE = Path(__file__).resolve().parent
NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
MUTEX_NAME = 'Local\\AOI_Color_Gray_Matcher_Final_v15'

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('PerProcessUserTimeLimit', ctypes.c_longlong),
        ('PerJobUserTimeLimit', ctypes.c_longlong),
        ('LimitFlags', wintypes.DWORD),
        ('MinimumWorkingSetSize', ctypes.c_size_t),
        ('MaximumWorkingSetSize', ctypes.c_size_t),
        ('ActiveProcessLimit', wintypes.DWORD),
        ('Affinity', ctypes.c_size_t),
        ('PriorityClass', wintypes.DWORD),
        ('SchedulingClass', wintypes.DWORD),
    ]
class IO_COUNTERS(ctypes.Structure):
    _fields_ = [('ReadOperationCount', ctypes.c_ulonglong),('WriteOperationCount', ctypes.c_ulonglong),('OtherOperationCount', ctypes.c_ulonglong),('ReadTransferCount', ctypes.c_ulonglong),('WriteTransferCount', ctypes.c_ulonglong),('OtherTransferCount', ctypes.c_ulonglong)]
class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),('IoInfo', IO_COUNTERS),('ProcessMemoryLimit', ctypes.c_size_t),('JobMemoryLimit', ctypes.c_size_t),('PeakProcessMemoryUsed', ctypes.c_size_t),('PeakJobMemoryUsed', ctypes.c_size_t)]

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9

class Bootstrap:
    def __init__(self):
        self.mutex = None
        self.job = None
        self.child = None
        self.root = tk.Tk()
        self.root.title('AOI Color-Gray Matcher v15')
        self.root.geometry('540x235')
        self.root.resizable(False, False)
        self.root.configure(bg='#0b1220')
        self.root.protocol('WM_DELETE_WINDOW', self.request_close)
        tk.Label(self.root,text='AOI COLOR · GRAY MATCH',bg='#0b1220',fg='#eef6ff',font=('Segoe UI',17,'bold')).pack(anchor='w',padx=28,pady=(26,2))
        tk.Label(self.root,text='IMAGE ALIGNMENT SYSTEM · v15',bg='#0b1220',fg='#21c55d',font=('Segoe UI',9,'bold')).pack(anchor='w',padx=28)
        self.status=tk.StringVar(value='중복 실행 확인 중...')
        tk.Label(self.root,textvariable=self.status,bg='#0b1220',fg='#9fb0c3',font=('Segoe UI',10),wraplength=480,justify='left').pack(anchor='w',padx=28,pady=(27,8))
        self.elapsed=tk.StringVar(value='경과 00:00')
        tk.Label(self.root,textvariable=self.elapsed,bg='#0b1220',fg='#60758a',font=('Consolas',9)).pack(anchor='w',padx=28)
        self.started=time.time(); self.closing=False
        self.tick()
        threading.Thread(target=self.prepare,daemon=True).start()
    def tick(self):
        sec=int(time.time()-self.started); self.elapsed.set(f'경과 {sec//60:02d}:{sec%60:02d}')
        self.root.after(500,self.tick)
    def set_status(self,text): self.root.after(0,self.status.set,text)
    def acquire_mutex(self):
        if os.name != 'nt': return True
        kernel32=ctypes.windll.kernel32
        self.mutex=kernel32.CreateMutexW(None,False,MUTEX_NAME)
        if kernel32.GetLastError()==183:
            return False
        return True
    def create_job(self):
        if os.name != 'nt': return
        k=ctypes.windll.kernel32
        self.job=k.CreateJobObjectW(None,None)
        info=JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.job,JobObjectExtendedLimitInformation,ctypes.byref(info),ctypes.sizeof(info)):
            raise ctypes.WinError()
    def assign_job(self,process):
        if os.name=='nt' and self.job:
            if not ctypes.windll.kernel32.AssignProcessToJobObject(self.job,wintypes.HANDLE(process._handle)):
                err=ctypes.get_last_error()
                if err not in (0,5): raise ctypes.WinError(err)
    def prepare(self):
        try:
            if not self.acquire_mutex():
                self.root.after(0,lambda:messagebox.showwarning('AOI Color-Gray Matcher v15','프로그램이 이미 실행 중입니다. 기존 창을 확인하세요.'))
                self.root.after(0,self.root.destroy); return
            missing=[x for x in ('webview','PIL','openpyxl','clr') if importlib.util.find_spec(x) is None]
            if missing:
                self.set_status('최초 실행 패키지 설치 중...')
                proc=subprocess.Popen([sys.executable,'-m','pip','install','--user','-r',str(BASE/'requirements.txt'),'--disable-pip-version-check'],cwd=BASE,creationflags=NO_WINDOW,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace')
                for line in proc.stdout:
                    line=line.strip()
                    if line:self.set_status('패키지 준비: '+line[:85])
                if proc.wait()!=0: raise RuntimeError('필수 Python 패키지 설치에 실패했습니다.')
            self.set_status('프로그램 프로세스 시작 중...')
            exe=Path(sys.executable); candidate=exe.with_name('pythonw.exe'); exe=candidate if candidate.exists() else exe
            self.create_job()
            self.child=subprocess.Popen([str(exe),str(BASE/'app.py')],cwd=BASE,creationflags=NO_WINDOW,close_fds=True)
            self.assign_job(self.child)
            self.set_status('WebView2 창 연결 중...')
            self.root.after(700,self.root.withdraw)
            code=self.child.wait()
            self.child=None
            self.close_handles()
            self.root.after(0,self.root.destroy)
        except Exception as exc:
            self.root.after(0,lambda:messagebox.showerror('AOI Color-Gray Matcher v15',str(exc)))
            self.root.after(0,self.root.destroy)
    def request_close(self):
        if self.closing:return
        self.closing=True
        if self.child and self.child.poll() is None:
            try:self.child.terminate()
            except:pass
        self.close_handles(); self.root.destroy()
    def close_handles(self):
        if os.name=='nt':
            k=ctypes.windll.kernel32
            if self.job:
                k.CloseHandle(self.job); self.job=None
            if self.mutex:
                k.ReleaseMutex(self.mutex); k.CloseHandle(self.mutex); self.mutex=None

if __name__=='__main__':
    app=Bootstrap(); app.root.mainloop()
