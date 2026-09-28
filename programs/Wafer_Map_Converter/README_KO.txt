Wafer Map Converter WebView2 v6

실행 파일
- Wafer_Map_Converter_WebView2_v6.vbs

실행 방법
1. ZIP 전체를 새 로컬 폴더에 압축 해제합니다. (기존 버전 폴더에 덮어쓰지 마세요)
2. Wafer_Map_Converter_WebView2_v6.vbs 를 더블클릭합니다.
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

v6 변경 사항
- 결과 저장 위치 선택 (03 파일 선택 단계)
  · 원본 맵 파일과 같은 폴더(기본) 또는 다른 위치
  · 다른 위치를 고르면 원본의 하위 폴더 구조를 그대로 만들어 저장 (같은 이름의 맵이 서로 덮어쓰지 않음)
- 03 검색 결과에서 파일 이름(경로)을 클릭하거나 [열기]를 누르면 원본 맵 파일(.txt/.xlsx)이 기본 프로그램으로 열림
- 05 완료 화면에서 결과 바로 보기
  · 변환한 맵 파일마다 카드 표시: 원본 맵 파일(.txt/.xlsx), 결과 파일, 저장 폴더
  · [Excel 열기] (Excel→TXT 모드는 [TXT 열기] / [원본 Excel 열기]), [폴더에서 보기]
  · Bin Code Map / Bin Meaning Map 썸네일 → 클릭 시 전체 화면 뷰어
    뷰어에서 ◀ ▶ 버튼 또는 키보드 ←/→ 로 모든 결과 이미지를 넘겨 보기, Esc 닫기,
    원본 크기/화면 맞춤 전환, 기본 뷰어로 열기, 이미지 위치와 원본 맵 파일 표시
  · 결과가 많을 때 검색창으로 Wafer/파일명/경로 필터, 썸네일은 화면에 보일 때만 불러옴
- 결과 Excel의 Map_Edit 시트 오른쪽에 Bin Code 범례와 수정 가이드 추가
  · Bin Code / 색상(이름·코드) / Defect 종류 / 한글 설명 / 맵 수량(수정 즉시 재계산) / 이 맵에 있음
  · 범례의 Bin Code 셀은 맵 die와 같은 서식이라 복사(Ctrl+C) → die에 붙여넣기(Ctrl+V)하면 코드와 색이 함께 바뀜
  · 맵 셀은 텍스트 형식이라 직접 003 입력 시 앞자리 0 유지, 숫자로 입력된 3도 Excel→TXT 변환 시 003으로 복원
  · 어두운 색 Bin은 흰 글자로 표시해 가독성 개선
- 버그 수정
  · Excel→TXT 모드에서 *_Map_Edit.xlsx 파일이 검색 목록에서 빠지던 문제 (수정한 Excel을 되돌릴 수 없던 문제)
  · BOM 없는 원본 TXT를 Excel→TXT로 되돌리면 BOM이 붙던 문제 (이제 원본과 바이트 단위로 동일)
  · 파일명에 점이 있는 경우(예: LOT.01.txt) 맵 이미지 이름이 잘려 다른 파일과 겹치던 문제
  · Excel 임시 잠금 파일(~$...)이 검색 목록에 나타나던 문제

v5 변경 사항
- JS API 객체의 창 참조를 비공개로 바꿔 "Python API 연결 준비 중" 지연/멈춤 원인 제거
- 실행 환경 설치와 프로그램 실행 분리 (AOI Color-Gray Matcher와 공용 환경 사용)
- 로컬 HTTP 서버 제거(인라인 화면), 영구 WebView2 프로필 사용
- 중복 실행 방지 추가 (같은 결과 파일 동시 덮어쓰기 방지)
- "새 작업" 후 작업이 막히던 문제 수정 (페이지 새로고침 시 종료 신호가 전달되던 문제)
- 종료 시 matplotlib를 불필요하게 불러오지 않도록 수정
- 실행기(VBS)를 BOM 없는 CP949로 저장 (v4는 UTF-8이라 한글 메시지가 깨질 수 있었음)

지원 기능 (v4와 동일)
- TXT -> Excel + Bin Code/Meaning 이미지, Excel -> TXT + Bin Code/Meaning 이미지
- 하위 폴더 재귀 검색, 전체/개별 선택 및 검색 필터
- WAFER, DEVICE, LOT, SIZE, Bin 수량 분석, 원본과 동일 폴더에 결과 저장
