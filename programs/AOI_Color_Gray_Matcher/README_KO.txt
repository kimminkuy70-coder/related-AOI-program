AOI Color-Gray Matcher Final v15

실행 파일
- AOI_Color_Gray_Matcher_Final_v15.vbs

실행 방법
1. ZIP을 기존 버전과 다른 새 로컬 폴더에 압축 해제합니다.
2. AOI_Color_Gray_Matcher_Final_v15.vbs를 더블클릭합니다.
3. Lot 폴더 또는 단일 Wafer 폴더를 선택합니다.

v15 수정 사항
- Windows Script Host의 800A0408, 1행 1문자 오류 수정
- VBS 실행 파일을 UTF-8 BOM 없이 Windows ANSI(CP949)로 저장
- 실행 파일명, 창 제목, 초기 화면 버전을 v15로 통일
- v14의 완전 종료, 중복 실행 방지, Windows Job Object 관리 유지
- 로컬 HTTP 서버를 사용하지 않는 인라인 WebView2 UI 유지
- Lot/단일 Wafer 자동 인식 및 실시간 검색 상태 유지
- 안전한 Excel 셀 링크 및 Crop 상대경로 유지

오류 원인
- v14 VBS 파일 시작 부분에 UTF-8 BOM 문자가 포함되어 있었습니다.
- 일부 Windows Script Host 환경은 BOM을 유효하지 않은 첫 문자로 해석합니다.
- v15는 BOM이 없는 CP949 형식으로 저장해 이 문제를 제거했습니다.

주의
- v14 폴더에 덮어쓰지 말고 새 폴더에서 v15를 실행하세요.
- 프로그램은 로컬 폴더에서 실행하고, 데이터만 네트워크 경로에서 선택하는 방식을 권장합니다.
