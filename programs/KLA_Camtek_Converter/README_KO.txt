KLA-Camtek Converter v1 (개발 준비 중)

용도
- KLA 와 Camtek 장비 사이의 AOI 데이터 파일 변환 (변환 방향과 형식은 정해지는 대로 기록)
- 개발 계획과 확인할 항목: docs/kla_camtek_converter_plan.md

현재 상태
- 프로그램 뼈대만 있습니다. 창이 뜨고 폴더를 고를 수 있지만 아직 변환은 하지 않습니다.

실행 방법 (ZIP, Python 설치 필요 없음)
1. 릴리스에서 KLA_Camtek_Converter_v1.zip 을 받아 ZIP 전체를 새 로컬 폴더에 압축 해제합니다.
   - 네트워크 폴더나 ZIP 안에서 바로 실행하지 마세요.
2. KLA_Camtek_Converter_v1.vbs 를 더블클릭합니다.
- 압축 해제한 폴더 구성
     KLA_Camtek_Converter_v1.vbs   실행 (runtime\pythonw.exe 로 app_files\app.py 를 켜는 짧은 런처)
     runtime\                      실행용 Python 3.12 + 필요한 패키지
     app_files\                    프로그램
- 필요 조건: Windows 10/11, Microsoft Edge WebView2 Runtime (Windows 10/11 기본 포함)
- 로그: %LOCALAPPDATA%\AOI_Tools\logs\KLA_Camtek_Converter.log
