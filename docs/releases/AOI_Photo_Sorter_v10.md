## AOI Photo Sorter v10 — Python 없는 PC에서도 ZIP만 풀면 실행 (.exe 없이)

### 바뀐 점
- **ZIP 버전에 실행용 Python이 들어 있습니다.** `AOI_Photo_Sorter_v10.zip`을 새 로컬 폴더에 압축 해제하고 `AOI_Photo_Sorter_v10.vbs`를 더블클릭하면, Python이 설치되지 않은 PC에서도 설치 창 없이 바로 실행됩니다.
  - `runtime\` 폴더: python.org 공식 Windows Python 3.12(NuGet `python` 패키지)와 필요한 패키지(pywebview, pythonnet, Pillow 등). `python.exe` / `pythonw.exe` / `python312.dll`은 Python Software Foundation의 디지털 서명이 있습니다.
  - 이 프로젝트가 만든 .exe가 없으므로 v7~v9 .exe에서 생긴 Defender "트로이 목마(…!ml)" 오탐과 무관합니다.
  - `.vbs`는 `runtime\pythonw.exe`로 `app_files\app.py`를 켜기만 합니다. 설치·다운로드·레지스트리 변경을 하지 않으므로 스크립트 오탐 위험도 낮습니다.
  - PC에 다른 Python이 있어도 섞이지 않습니다. 압축 해제한 폴더를 통째로 다른 PC에 복사해도 됩니다.
- 기능과 사용법, 설정·진행 상황 위치(`%LOCALAPPDATA%\AOI_Tools`)는 v9와 같습니다.
- `.exe`도 계속 함께 올리지만, Defender가 막는 PC가 있어 ZIP 버전을 권장합니다.

### 참고
- 브라우저에서 받은 ZIP을 풀고 "보안 경고" 창이 뜨면 [실행]을 누르거나, ZIP 파일 속성에서 [차단 해제] 후 다시 압축 해제하세요.
- "필수 파일이 없습니다" 창이 뜨면 ZIP 전체를 새 폴더에 다시 압축 해제하세요.
- 서명된 Python을 쓰더라도 회사 PC의 백신 정책에 따라 막힐 가능성을 0으로 만들 수는 없습니다. 막히면 보호 기록의 위협 이름과 '영향을 받는 항목' 경로를 알려 주세요.

### 검증
- 단위 시험(포터블 runtime 구성: Windows 마커로 패키지 고르기, 휠·소스 압축 풀기, 릴리스 ZIP에 runtime 포함, 런처 내용)과 기존 시험을 Linux에서 통과했습니다. 실제 runtime 구성(Python 3.12.10 + 패키지 9개, 약 48 MB)도 만들어 확인했습니다.
- Linux 환경이라 Windows PC에서 포터블 ZIP 실행과 Defender 판정은 확인하지 못했습니다.
