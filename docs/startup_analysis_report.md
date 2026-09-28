# AOI Color-Gray Matcher v15 / Wafer Map Converter v4 — 기동 성능 · 동시 실행 분석 보고서

- 분석 대상: `AOI_Color_Gray_Matcher_Final_v15.zip`, `Wafer_Map_Converter_WebView2_v4.zip`
- 기준 라이브러리: requirements 범위(`pywebview>=6,<7`)에서 현재 설치되는 **pywebview 6.2.1** 소스를 직접 대조
- 분석 방법: 코드 정적 분석, pywebview 내부 코드 추적, Linux에서 import 시간 측정
- 한계: Windows/WebView2 실기 재현은 하지 못했습니다. 아래 "원인" 항목은 코드 근거가 있는 판단입니다.

---

## 0. 요약

| # | 질문 | 결론 |
|---|---|---|
| 1 | 초기 실행이 느린 원인 | ① JS API 노출 과정에서 `api.window`(.NET WinForms 객체 트리)를 재귀 탐색함, ② 실행할 때마다 **새 임시 WebView2 프로필**을 만드는 private_mode 기본값, ③ Python 프로세스 2개 기동 + .NET CLR + WebView2 런타임 콜드 스타트, ④ AOI는 창을 띄우기 전에 Pillow/openpyxl을 import |
| 2 | AOI가 "Python API 연결 준비 중"에서 멈춤 | **`API.window`가 public 속성**이라 pywebview가 `window.native`(WinForms Form → WebView2 컨트롤 → CoreWebView2 …)를 백그라운드 스레드에서 끝없이 재귀 탐색함. 그동안 `window.pywebview.api`가 생성되지 않아 boot 오버레이가 사라지지 않음 |
| 3 | 두 프로그램 동시 실행 | 평상시 동작은 **대체로 안전**함(프로필·포트·Mutex 충돌 없음). 다만 **최초 설치를 동시에 하면 `pip --user` 경합**, Wafer는 **중복 실행 방지가 없음**, 둘 다 무거운 작업을 동시에 돌리면 CPU·메모리 부하로 렉이 생길 수 있음 |
| 4 | 초기 환경 구성 시간 단축 | `window` → `_window` 수정(필수), 영구 WebView2 프로필, 지연 import, 설치 완료 마커, 오프라인 wheelhouse / 공용 venv, 최종적으로 PyInstaller **onedir** 배포 |

---

## 1. 초기 실행이 오래 걸리는 원인

### 실행 체인 (두 프로그램 공통)

```
.vbs → pyw 런처 → bootstrap.pyw (Python #1, tkinter 스플래시)
      → pythonw app.py (Python #2) → import webview → pythonnet(.NET CLR 로드)
      → WinForms Form 생성 → WebView2 런타임(msedgewebview2.exe 여러 개) 기동
      → 페이지 로드 → pywebview JS 브리지 주입(get_functions) → pywebviewready
```

### 1-1. [가장 큰 원인] JS API 노출 과정에서 `window` 객체를 재귀 탐색함 (두 프로그램 공통)

`webview/util.py` `inject_pywebview()` → `get_functions()`는 js_api 객체를 `dir()`로 훑으면서,
**`_`로 시작하지 않는 non-callable 속성을 전부 재귀 탐색**합니다.

```python
# pywebview 6.2.1 util.py
for name in dir(obj):
    if name.startswith('_'): continue
    attr = getattr(obj, name)
    ...
    elif inspect.isclass(attr) or (not callable(attr) and hasattr(attr, '__module__')):
        get_functions(attr, full_name, functions)   # 재귀
```

두 프로그램 모두 `API`에 `self.window = window`를 **public**으로 넣습니다.

- AOI `app.py`: `api.window=window`
- Wafer `app.py`: `api.window = window`

탐색 경로는 다음과 같습니다.

`api.window` → `window.native` (WinForms `BrowserForm`) → `.browser` → `.webview` (WebView2 컨트롤) → `.CoreWebView2`, 그리고 Form의 `.Controls`, `.Parent`, `.BindingContext`, `.AccessibilityObject`, `.Font` … 같은 **.NET 속성 전체**

- 이 탐색은 **UI 스레드가 아닌 백그라운드 스레드**에서 실행됩니다. 그래서 WinForms/WebView2 속성에 교차 스레드로 접근하게 되고, 예외가 나면 그 속성만 건너뛰고 계속 진행합니다.
- 중복 방문은 `id(obj)`로만 막습니다. pythonnet은 .NET 속성에 접근할 때마다 새 래퍼 객체를 돌려줄 수 있어서, 순환 참조가 있는 .NET 객체 그래프에서는 중복 방지가 제대로 작동하지 않습니다. 그 결과 탐색이 **극단적으로 느려지거나 끝나지 않습니다**.
- 이 작업이 끝나야 `window.pywebview.api`가 생성되고 `pywebviewready`가 발생합니다.
- Linux(`window.native=None`)에서 같은 로직을 돌려 보면 탐색은 즉시 끝납니다. 대신 `window.evaluate_js`, `window.load_url`, `window.destroy` 등 **Window 메서드 22개가 JS에 그대로 노출**되는 것이 확인되었습니다(부수적인 보안 문제). Windows에서는 여기에 .NET 객체 트리 전체가 추가로 탐색됩니다.

### 1-2. 매 실행마다 새 WebView2 프로필 생성 (공통)

`webview.start()`에 `private_mode`/`storage_path`를 지정하지 않아 기본값 `private_mode=True`가 적용됩니다.
`winforms.init_storage()`는 이 경우 `tempfile.TemporaryDirectory().name`, 즉 **매번 다른 임시 폴더**를 WebView2 UserDataFolder로 씁니다.

그 결과 WebView2가 **매 실행마다 프로필을 콜드 생성**합니다(캐시·GPU 셰이더 캐시 재사용 불가). 사내 PC의 백신 실시간 검사가 새 파일 생성마다 개입하면 수 초씩 늘어날 수 있습니다. %TEMP%에 프로필 잔재가 쌓일 수도 있습니다.

### 1-3. Python 인터프리터 2회 기동 + .NET + WebView2 콜드 스타트 (공통)

- bootstrap(Tk)과 app.py가 **별도 프로세스**입니다. `pythonnet`의 CLR 로드와 WebView2 브라우저/GPU/렌더러 프로세스 기동은 첫 실행에서 보통 1~3초씩 걸립니다.
- `pyw` 런처가 기본 Python을 고르는 과정과 `--user` site-packages 스캔도 더해집니다.

### 1-4. AOI: 창을 띄우기 전에 무거운 라이브러리를 import

- `app.py` 첫 줄에서 `from engine import ...`를 실행하고, `engine.py`는 모듈 로드 시점에 `PIL`과 `openpyxl`을 import합니다.
- 측정 결과(Linux, warm cache): `import engine` **AOI 287 ms** / Wafer 23 ms. Wafer는 heavy import가 지연 로드로 분리되어 있습니다.
- 두 프로그램이 같은 Python `--user`에 설치되면, Wafer가 설치한 `numpy`를 openpyxl이 import 시점에 자동으로 불러옵니다(`openpyxl.compat.numbers`, 측정 122 ms). **Wafer를 설치하면 AOI 기동이 느려지는** 상호 영향이 있습니다. Windows 콜드 스타트 + 백신 환경에서는 이 값이 몇 배로 커집니다.

### 1-5. AOI: 매 실행마다 패키지 존재 검사

- Wafer는 `.setup_complete.json` 마커로 두 번째 실행부터 검사를 생략합니다. AOI는 매번 `find_spec` 4회를 수행합니다(비용은 작지만 네트워크 드라이브나 로밍 프로필에서는 체감될 수 있음).
- 설치 로그를 파일로 남기지 않아 실패 원인을 추적하기 어렵습니다.

---

## 2. AOI가 "Python API 연결 준비 중"에서 멈추는 원인

### 동작 흐름

1. `index.html`의 `#boot` 오버레이에 "Python API 연결 준비 중..."이 표시됩니다.
2. `app.js`는 `pywebviewready` 이벤트를 받거나, 400 ms마다 `window.pywebview?.api?.get_state`가 생겼는지 확인할 때만 오버레이를 제거합니다.
3. `pywebview.api`는 1-1의 `get_functions()`가 **끝나야** 생성됩니다.
4. `get_functions()`가 `api.window.native` 이하 .NET 객체 트리에 빠지면 끝나지 않고, 화면은 오버레이에 영원히 머뭅니다.
   - Python 쪽 예외는 `logger.error`로만 기록되고, `debug=False`에 `pythonw`로 실행되므로 **사용자에게는 아무 오류도 보이지 않습니다**.

### 수정 (필수, 두 프로그램 모두)

```python
# app.py (AOI / Wafer 공통)
class API:
    def __init__(self):
        self._window = None          # ← 반드시 '_' 접두사
        ...
    def choose_folder(self):
        result = self._window.create_file_dialog(...)   # self.window → self._window
```

```python
api._window = window                 # main()
```

같은 이유로 JS에 노출할 필요가 없는 속성은 모두 `_` 접두사로 바꾸는 것이 안전합니다(`lock`, `threads`, `workers`, `cancel_event`, `scan_cancel`, `state`, `root`, `wafers`, `items` 등).
지금은 `cancel_event.set`, `lock.acquire` 같은 내부 메서드까지 `pywebview.api.cancel_event.set()` 형태로 JS에 노출됩니다.

### AOI에만 있는 추가 요인

- `html=`(NavigateToString) 방식이라 페이지를 매번 문자열로 합성해 넘깁니다. 원인은 아니지만, 브리지 주입 실패 시 DevTools/로그 확인 수단이 없습니다.
- 권장: `webview.start(debug=True)` 스위치를 환경변수로 켤 수 있게 하고, `logging`을 파일(`%LOCALAPPDATA%\...\app.log`)로 남기세요.

---

## 3. 두 프로그램을 동시에 실행할 때

| 항목 | 판정 | 근거 |
|---|---|---|
| WebView2 UserDataFolder 충돌 | ✅ 없음 | 둘 다 private_mode라 매번 다른 임시 폴더 사용 (단, 1-2의 속도 손해가 있음). 개선 시 **앱별로 다른 storage_path**를 쓰면 충돌 없이 빨라집니다 |
| 로컬 HTTP 포트 | ✅ 없음 | AOI는 서버 없음, Wafer는 pywebview 내장 서버가 임의 포트 사용 |
| Mutex / Job Object | ✅ 서로 간섭 없음 | Mutex 이름 다름. Job은 각자 자기 프로세스 트리만 관리(다른 WebView2 앱 미종료) |
| **최초 설치를 동시에** | ⚠️ 위험 | 두 bootstrap이 동시에 `pip install --user`를 돌리면 공통 의존성(pywebview, pythonnet, openpyxl, bottle…)을 **같은 site-packages에 동시 기록**해 설치 손상 또는 실패가 날 수 있음 → 전역 설치 락이 필요함 |
| **Wafer 중복 실행** | ⚠️ 방지 없음 | AOI는 Mutex가 있지만 Wafer bootstrap에는 없음 → 더블클릭을 두 번 하면 두 인스턴스가 떠서 같은 폴더의 `_Map_Edit.xlsx`를 동시에 덮어쓸 수 있음 |
| CPU/메모리 부하 | ⚠️ 작업 동시 수행 시 렉 | AOI: Pillow LANCZOS로 대형 이미지 리사이즈 + 이미지 수백 장이 든 openpyxl 저장(메모리 큼). Wafer: 셀마다 새 `PatternFill/Font/Border` 객체 생성 + matplotlib 16×13in@180dpi PNG 2장. WebView2 인스턴스 2개(각 150~300 MB)까지 더하면 **8 GB 이하 PC에서 동시 대량 작업 시 버벅임** 가능. 기능 오류는 아님 |
| UI 폴링 | ℹ️ 경미 | 둘 다 350~400 ms마다 `get_state` 호출. AOI는 매번 로그 250줄을 JSON으로 왕복 → 로그 증분만 전달하도록 개선 권장 |
| Excel이 결과 파일을 열고 있음 | ℹ️ | 결과 xlsx를 Excel로 연 상태에서 재실행하면 PermissionError (Wafer는 파일 단위로 오류 표시, AOI는 작업 전체가 error로 끝남) |
| AOI Mutex 신뢰성 | ℹ️ | `ctypes.windll...GetLastError()`는 ctypes 내부 호출에 값이 덮일 수 있음 → `WinDLL('kernel32', use_last_error=True)` + `ctypes.get_last_error()` 권장 (Wafer app.py는 이미 올바르게 구현) |

**결론**: 설치가 끝난 상태에서 두 프로그램을 **동시에 켜는 것 자체는 문제없습니다**. 다만 ① 최초 설치 동시 진행, ② Wafer 중복 실행, ③ 대용량 작업 동시 처리 세 가지는 주의하거나 코드로 보완해야 합니다.

---

## 4. 초기 환경 구성 · 기동 시간 단축 방안 (효과 순)

### 즉시 적용 (코드 수정, 수십 줄 이내)

1. **`self.window` → `self._window`** (두 프로그램 공통, 2번 문제 해결 + 1번 최대 병목 제거)
2. **영구 WebView2 프로필 사용**. 두 번째 실행부터 프로필 콜드 생성이 사라집니다.
   ```python
   base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AOI_Tools'
   webview.start(gui='edgechromium', private_mode=False,
                 storage_path=str(base / 'AOI_Matcher_WebView2'))   # Wafer는 다른 폴더명
   ```
   Wafer는 `private_mode=False`이고 `http_port`가 없으면 pywebview가 **고정 포트 42001**을 씁니다. Wafer만 이 설정을 쓴다면 문제없지만, 다른 pywebview 앱과 겹치지 않도록 `http_port`를 명시하거나 AOI처럼 인라인 HTML 방식으로 통일하는 것을 권장합니다.
3. **AOI heavy import 지연**. `engine.py`의 `PIL`/`openpyxl` import를 `process_wafer`/`build_workbook` 안으로 옮기고, `discover`만 경량으로 남깁니다(Wafer와 같은 구조).
4. **AOI에도 설치 완료 마커 적용** (Wafer의 `.setup_complete.json` 방식)과 설치 로그 파일 기록.
5. **전역 설치 락**. 두 bootstrap이 공유하는 이름(예: `Local\\AOI_Tools_PipInstall`)의 Mutex를 pip 실행 구간에만 잡습니다. 최초 설치 경합이 사라집니다.
6. **Wafer bootstrap에 단일 인스턴스 Mutex 추가** (AOI v15 방식 이식).

### 설치 시간 단축 (배포 방식)

7. **오프라인 wheelhouse**. 한 PC에서 `pip download -r requirements.txt -d wheels`로 받아 ZIP에 포함하고, 설치는 `pip install --no-index --find-links wheels ...`로 합니다. 사내망 인터넷/프록시 대기와 다운로드 시간이 없어지고, 버전도 고정됩니다.
8. **공용 venv 1개**. `%LOCALAPPDATA%\AOI_Tools\venv`를 두 프로그램이 공유하고, 두 requirements를 합친 버전 고정 목록(lock)을 사용합니다. 설치는 1회만 하고 `--user` 오염도 없습니다.
9. **`python -m compileall app_files`**. 배포 전에 .pyc를 미리 만들어 둡니다. 설치 폴더가 읽기 전용이거나 네트워크 드라이브여서 `__pycache__`를 쓸 수 없는 환경에서 효과가 있습니다.
10. **최종 권장: PyInstaller `--onedir` 빌드**. Python/pip 설치가 필요 없고 기동 시 bootstrap 단계도 없어집니다. `--onefile`은 실행할 때마다 임시 폴더에 압축을 풀기 때문에 **오히려 느리므로 사용하지 마세요**.

### 체감 속도 개선 (UX)

11. **bootstrap 제거 또는 단일 프로세스화**. 설치 마커가 유효하면 bootstrap을 거치지 않고 app.py를 곧바로 실행합니다(VBS에서 마커를 확인하거나 `pyw app.py` 직행). Python 기동 1회와 Tk 초기화 비용이 없어집니다.
12. 두 창 모두 `background_color`가 있으므로 창은 바로 보입니다. 오버레이 문구를 "WebView2 초기화 중 → API 연결 중"처럼 단계별로 바꾸고, 10초가 지나도 연결되지 않으면 안내 문구(로그 경로)를 표시합니다.
13. **WebView2 Evergreen Runtime 사전 설치 확인**. 런타임이 없거나 손상되면 초기화가 지연되거나 실패합니다. 배포 체크리스트에 추가하세요.
14. **백신 예외 요청**. `%LOCALAPPDATA%\AOI_Tools` 폴더를 예외로 등록하면 .pyd/.dll 로드와 프로필 생성 검사 시간이 줄어듭니다(IT 정책 협의 필요).

### 예상 효과 (정성)

| 조치 | 영향 |
|---|---|
| 1 | AOI 무한 대기 해소, 두 앱 모두 브리지 연결 시간 대폭 단축 (가장 큼) |
| 2 | 두 번째 실행부터 WebView2 기동 단축 |
| 3, 11 | 창이 뜨기까지의 시간 단축 (수백 ms ~ 1 s 이상, 콜드/백신 환경일수록 큼) |
| 5–8, 10 | 최초 설치 시간 및 실패율 감소, 동시 설치 경합 제거 |

---

## 5. 구현 결과 (AOI v16 / Wafer v5)

설계 변경: 오프라인 wheel 파일은 넣지 않습니다. 코드로 온라인 설치하되, **설치와 실행을 분리**하고 **사용자별 Python 버전 차이**를 흡수합니다.

### 실행 흐름

```
{프로그램}.vbs
 ├─ 빠른 경로: %LOCALAPPDATA%\AOI_Tools\ready\<APP>.txt 가 유효하면
 │     (환경 리비전 OK, venv pythonw 존재, 기반 Python 존재)
 │     → venv\Scripts\pythonw.exe app.py 직접 실행 (Python 1회 기동, 설치 검사 없음)
 └─ 설치 경로: pyw -3 (없으면 레지스트리의 Python 3.6+) 로 app_files\setup_env.py 실행
       Python이 하나도 없으면 winget 으로 Python 3.12 사용자 설치 또는 다운로드 페이지 안내
```

`setup_env.py`는 두 프로그램에 동일하게 들어가며 다음 순서로 동작합니다.
1. `py -0p`, 레지스트리(PEP 514), PATH에서 Python을 찾고 병렬로 버전과 비트를 확인합니다. 지원 범위는 3.9~3.14입니다. 이미 만들어진 환경을 우선 재사용하고, 그다음 64bit, 최신 버전 순으로 고릅니다.
2. `%LOCALAPPDATA%\AOI_Tools\env\py3XX-x64`에 공용 venv를 만듭니다. 임시 폴더에 먼저 만든 뒤 이름을 바꾸므로, 중간에 끊겨도 깨진 환경이 남지 않습니다.
3. `pip install -r requirements.txt -c constraints.txt`를 실행합니다. C 확장이 있는 패키지는 wheel로만 설치해서 소스 빌드에 빠지지 않게 합니다. 버전이 맞지 않으면 다음 Python으로 자동 전환하고, 네트워크·프록시·인증서 오류는 원인별로 안내합니다.
4. import 검증을 통과하면 ready 파일(UTF-16)을 기록하고 프로그램을 실행합니다.
- 두 프로그램이 동시에 처음 실행되면 설치 Mutex가 순서를 정리합니다.
- 설치 실패 창에서 재시도하거나 로그를 열 수 있습니다.
- 사내 미러는 `%LOCALAPPDATA%\AOI_Tools\pip.ini`로 지정합니다.
- 실행 중 패키지 누락이나 손상을 발견하면 `--repair`로 자동 복구하고 다시 실행합니다(1회만 시도해 무한 반복을 막음).

### Python 버전별 설치 가능성 (pip 해석 결과, Windows wheel 기준)

| Python | 64bit | 32bit |
|---|---|---|
| 3.8 | 설치는 가능하지만 pywebview 6 지원 범위 밖이라 제외 | 제외 |
| 3.9 | ✅ (numpy 2.0, pythonnet 3.0.5) | ✅ |
| 3.10 ~ 3.11 | ✅ | ✅ |
| 3.12 ~ 3.14 | ✅ | AOI ✅ / Wafer ❌ (matplotlib 32bit wheel 없음 → 다른 Python 자동 시도 후 안내) |

### 적용한 코드 수정

| 항목 | AOI v16 | Wafer v5 |
|---|---|---|
| JS API의 창 참조를 비공개(`_window`)로 변경하고 내부 속성도 모두 비공개로 전환 | ✅ | ✅ |
| 영구 WebView2 프로필 (프로그램별 분리) | ✅ | ✅ |
| 무거운 패키지 지연 로드 | ✅ Pillow·openpyxl (`import engine` 287 ms → 15 ms) | 기존과 동일, 종료 시 matplotlib import 제거 |
| 로컬 HTTP 서버 제거 (인라인 UI) | 기존과 동일 | ✅ |
| 단일 인스턴스 Mutex (`use_last_error`) + 기존 창 활성화 | ✅ (bootstrap에서 app으로 이동) | ✅ 신규 |
| Job Object (이 인스턴스의 WebView2만 정리) | ✅ | ✅ |
| "새 작업" 버튼 수정 (`location.reload` → `load_html`) | ✅ | ✅ (reload 시 종료 신호가 가던 버그도 제거) |
| 실행 로그 파일, 시작 실패 메시지 박스, `AOI_TOOLS_DEBUG=1` | ✅ | ✅ |
| VBS를 CP949 + CRLF(BOM 없음)로 저장 | 유지 | ✅ (v4는 UTF-8이라 한글 메시지가 깨질 수 있었음) |

### 검증 (Linux 컨테이너, Windows 실기는 미실시)

- `tests/test_startup.py` 9개 통과
  - 구버전 구조에서 창 객체 재귀 탐색(1,000회 이상)과 창 메서드가 JS에 노출되는 것을 재현했고, 새 구조에서는 탐색 0회이며 JS 호출 목록만 노출되는 것을 확인
  - 두 프로그램 모두 `import engine` 시 무거운 패키지를 불러오지 않음
  - 인라인 UI, 공유 파일 동일성, VBS 인코딩 확인
- 새 PC 상태에서 AOI 설치: venv 생성 + pip + 검증 **4~7초** (이 환경의 네트워크 기준)
- AOI 설치 후 Wafer 설치: 공용 환경을 재사용하고 추가 패키지만 설치(9초)
- 두 프로그램 동시 첫 실행: 한쪽이 대기한 뒤 환경 재사용, `pip check` 이상 없음
- openpyxl을 지운 뒤 실행: 시작 단계에서 감지 → 자동 복구(1.1초) → 재실행
- Windows에서 확인이 필요한 항목: VBS 빠른/설치 경로, winget 설치, WebView2 확인, Job Object·Mutex·창 활성화, 실제 기동 시간

### 배포

`python tools/build_release.py --zip` 을 실행하면 `dist/AOI_Color_Gray_Matcher_Final_v16.zip`과 `dist/Wafer_Map_Converter_WebView2_v5.zip`이 만들어집니다. 이 과정에서 VBS 생성과 공유 파일 동일성 검사도 함께 수행됩니다.
