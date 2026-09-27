Wafer Map Converter WebView2 v4

참고 구조
- AOI Color-Gray Matcher Final v13의 Bootstrap + WebView2 + 5단계 Command Center 흐름을 참고했습니다.

실행
1. ZIP 전체를 새 로컬 폴더에 압축 해제합니다.
2. Wafer_Map_Converter_WebView2_v4.vbs를 실행합니다.

성능 개선
- Bootstrap 창은 즉시 작업표시줄에 표시됩니다.
- 패키지 설치는 PC/Python 환경별 최초 1회만 수행합니다.
- 이후 실행에서는 pip 및 패키지 설치를 생략합니다.
- 메인 WebView2 창 안의 boot overlay가 Python API 연결 완료 시 자동 제거됩니다.
- NumPy와 Matplotlib은 실제 이미지 생성 시점에만 로드합니다.
- 폴더 검색과 파일 변환은 백그라운드 스레드에서 실행합니다.

지원 기능
- TXT -> Excel + Bin Code/Meaning 이미지
- Excel -> TXT + Bin Code/Meaning 이미지
- 하위 폴더 재귀 검색
- 전체/개별 선택 및 검색 필터
- WAFER, DEVICE, LOT, SIZE, Bin 수량 분석
- 090 Customer Map Reject Die
- 원본과 동일 폴더에 결과 저장

완전 종료 처리 v4
- 창 닫기 시 폴더 검색, 변환 작업, 이미지 생성에 취소 신호를 전달합니다.
- 종료 이벤트는 closing과 closed 두 단계로 처리합니다.
- Python 작업 스레드는 짧게 종료 대기 후 호스트 프로세스를 강제 종료합니다.
- 로컬 HTTP 서버와 pythonw.exe가 창을 닫은 뒤 남지 않도록 os._exit(0)을 보장합니다.
- Windows Job Object의 KILL_ON_JOB_CLOSE를 사용해 이 프로그램 인스턴스가 만든 WebView2 자식 프로세스만 정리합니다.
- Teams, Outlook 등 다른 프로그램의 WebView2 프로세스는 종료하지 않습니다.
