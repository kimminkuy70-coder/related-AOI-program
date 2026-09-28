AOI Color-Gray Matcher Final v16

실행 파일
- AOI_Color_Gray_Matcher_Final_v16.vbs

실행 방법
1. ZIP 전체를 새 로컬 폴더에 압축 해제합니다. (기존 버전 폴더에 덮어쓰지 마세요)
2. AOI_Color_Gray_Matcher_Final_v16.vbs 를 더블클릭합니다.
3. 최초 1회만 "실행 환경 설치" 창이 나타납니다. (네트워크에 따라 약 1~3분)
   설치가 끝나면 프로그램이 자동으로 실행되고, 이후에는 설치 과정 없이 바로 실행됩니다.

필요 조건
- Windows 10/11, Microsoft Edge WebView2 Runtime (Windows 11은 기본 포함)
- Python 3.9 ~ 3.14 (64bit 권장). 여러 버전이 설치되어 있으면 지원 범위의 최신 64bit 버전을 자동 선택합니다.
  Python이 없으면 실행 시 Python 3.12 자동 설치(winget, 관리자 권한 불필요) 또는 다운로드 페이지를 안내합니다.
- 최초 설치 시 pypi.org / files.pythonhosted.org 접속 (사내 미러 사용 시 아래 참고)

실행 환경 구조 (AOI 도구 공용)
- %LOCALAPPDATA%\AOI_Tools\env\py312-x64 등 : Python 버전별 공용 가상환경 (AOI Matcher, Wafer Map Converter 공유)
- %LOCALAPPDATA%\AOI_Tools\ready\         : 설치 완료 정보 (실행기가 읽어 바로 실행)
- %LOCALAPPDATA%\AOI_Tools\webview2\      : 프로그램별 WebView2 프로필 (재사용으로 기동 단축)
- %LOCALAPPDATA%\AOI_Tools\logs\          : setup_*.log (설치), <프로그램>.log (실행 오류)
- PC에 설치된 Python의 site-packages(--user)는 더 이상 사용하지 않습니다.

사내 미러 / 인증서 설정 (필요한 경우만)
- %LOCALAPPDATA%\AOI_Tools\pip.ini 파일을 만들고 예시처럼 작성합니다.
    [global]
    index-url = https://사내미러주소/simple
    cert = C:\경로\사내루트인증서.pem

문제 해결
- 설치 실패 창의 [로그 열기]로 원인을 확인하고 [재시도]를 누르세요.
- 패키지가 손상되면 프로그램 시작 시 자동으로 복구 설치가 실행됩니다.
- 완전히 초기화하려면 모든 AOI 도구를 닫고 %LOCALAPPDATA%\AOI_Tools\env 폴더를 삭제한 뒤 다시 실행하세요.
- 화면 디버그가 필요하면 환경변수 AOI_TOOLS_DEBUG=1 을 설정하고 실행하면 WebView2 개발자 도구가 활성화됩니다.

v16 변경 사항
- "Python API 연결 준비 중"에서 멈추는 문제 수정
  (JS API 객체에 창 객체가 공개 속성으로 들어 있어 pywebview가 .NET WinForms 객체 트리를 끝없이 탐색하던 문제)
- 실행 환경 설치와 프로그램 실행 분리: 설치는 최초 1회, 이후 실행은 검사 없이 바로 시작
- Python 버전 자동 선택(3.9~3.14), 버전별 공용 가상환경, 설치 동시 실행 잠금
- 영구 WebView2 프로필 사용, Pillow/openpyxl 지연 로드로 창 표시 단축
- 중복 실행 시 기존 창을 앞으로 가져옴, 창 제목·실행 파일명 v16 통일
- "새 작업" 버튼이 인라인 화면을 안전하게 다시 불러오도록 수정
- 실행기(VBS)는 v15와 동일하게 BOM 없는 CP949로 저장
