# KLA-Camtek Converter — 개발 계획서 (준비)

- 상태: **뼈대만 있음.** 변환 방향과 파일 형식이 정해지면 구현을 시작
- 브랜치: `ccr-0b38d41f-r1uk33`
- 프로그램 폴더: `programs/KLA_Camtek_Converter/`
- 릴리스 이름: `KLA_Camtek_Converter_v1` (태그를 푸시하면 Release 워크플로가 ZIP을 게시)

## 1. 지금 들어 있는 것

| 항목 | 내용 |
|---|---|
| 실행 방식 | AOI Photo Sorter v10과 같은 **포터블 ZIP** (`"portable": true`). ZIP 안의 `runtime\` Python으로 실행, PC에 Python 설치 필요 없음 |
| 화면 | pywebview + WebView2, 인라인 HTML (Wafer Map Converter와 같은 구조). 지금은 "준비 중" 화면과 폴더 선택만 있음 |
| 엔진 | `engine.py`: `discover()`(하위 폴더 포함 파일 검색)만 동작. `inspect()` / `convert()`는 형식이 정해지면 구현 |
| 공용 파일 | `runtime.py`, `setup_env.py`, `constraints.txt` — 다른 AOI 도구와 바이트 단위로 같아야 함 (`tools/build_release.py`, `tests/test_startup.py`가 검사) |
| 실행기 | `KLA_Camtek_Converter_v1.vbs` — `python tools/build_release.py`가 `tools/launcher_portable.vbs`로 생성 (직접 고치지 않음) |

## 2. 정해야 할 것 (구현 전에 필요)

1. **변환 방향**: KLA → Camtek, Camtek → KLA, 또는 양방향
2. **입력 파일 형식**: 예) KLA KLARF(`.klarf`, `.000` 등) 결함 파일, KLA 웨이퍼 맵, Camtek 검사 결과/맵 파일
   - 샘플 파일 2~3개 (가능하면 실제 장비에서 나온 것, 민감 정보는 가려도 됨)
3. **출력 파일 형식**: 받는 쪽 장비/시스템이 읽는 형식과 그 샘플 (정답 예시가 있으면 가장 좋음)
4. **옮길 정보**: 웨이퍼 맵(die 좌표·Bin), 결함 목록(좌표·크기·분류 코드), 헤더(LOT, WAFER, DEVICE, 레시피 등) 중 무엇을 옮기는지
5. **좌표 기준**: 원점 위치(중심/좌하단 등), 축 방향, 노치(Flat) 방향, die pitch 단위(µm/mm)
6. **코드 매핑**: KLA 분류 코드(ClassNumber) ↔ Camtek Defect/Bin 코드 대응표
7. **작업 단위**: 파일 하나씩 / 폴더 일괄(하위 폴더 포함), 결과 저장 위치(원본과 같은 폴더 / 다른 위치)
8. **결과 확인**: 변환 후 맵 이미지·요약(개수 비교)이 필요한지

## 3. 구현 순서 (형식이 정해진 뒤)

1. `engine.py`: 입력 파서 → 공통 데이터 구조 → 출력 작성기, 샘플 파일로 왕복 테스트(`tests/test_kla_camtek_engine.py`)
2. `app.py` / `ui/`: Wafer Map Converter의 단계 화면(방향 → 폴더 → 파일 선택 → 진행 → 완료)을 기준으로 구성
3. 필요한 패키지를 `requirements.txt`와 `app_manifest.json`의 `"modules"`에 추가 (범위는 공용 `constraints.txt`)
4. `docs/releases/KLA_Camtek_Converter_v1.md` 릴리스 노트 작성 후 태그 푸시
