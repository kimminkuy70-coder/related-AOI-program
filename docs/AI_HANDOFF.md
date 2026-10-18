# AI 인수인계 (related-AOI-program)

마지막 갱신: 2026-10-18 · 작업 브랜치 `claude/relaxed-goldberg-dnf5nt` · 이슈 번호 없음 (대화 요청)

## 지금 상태
- 프로그램: `programs/AOI_Photo_Sorter_HTML/` **AOI Photo Sorter HTML v1** (Edge에서 여는 HTML 한 파일, Python·.exe 없음)가 sorter의 유일한 버전입니다.
  - 소스 `src/`, 빌드 `python tools/build_html.py` (`--check`로 빌드 결과가 최신인지 확인).
- 다른 프로그램: `AOI_Color_Gray_Matcher` (Final_v16), `Wafer_Map_Converter` (WebView2_v6): 그대로 둠.
- 속도 시험: `experiments/browser_speed_test/AOI_Browser_Speed_Test.html` (HTML 방식이 되는지 확인하던 실험 페이지).
- 시험: 이 환경(Linux)에는 matplotlib, webview, playwright가 없어 `tests.test_startup`, `tests.test_wafer_engine`에서 11개 오류가 납니다 (이번 변경 전과 같은 오류). `tests/e2e_*.py`는 playwright가 없어 못 돌렸습니다. `build_html.py --check`, `build_release.py`는 통과.

## 이번 작업 (요청: Sorter HTML v1만 남기고 이전 버전 삭제, 그 브랜치로 합침)
- `claude/cool-meitner-n7uz0l`(HTML v1이 있던 브랜치)을 이 브랜치에 merge.
- 삭제: `programs/AOI_Photo_Sorter/`(Python/.exe sorter v1~v10), `docs/releases/AOI_Photo_Sorter_v*.md`, `docs/photo_sorter_plan.md`, `tests/test_photo_sorter.py`, `tests/e2e_photo_sorter.py`.
- sorter v10 전용이던 portable 도구도 삭제: `tools/build_portable.py`, `tools/launcher_portable.vbs`, `tests/test_portable.py`. `tools/build_release.py`에서 portable 처리 제거.
- 연쇄 수정: `tests/e2e_html_sorter.py`(Python 엔진과 결과 파일 교환 시험 삭제), `tests/test_startup.py`, `.github/workflows/release.yml`(constraints 경로, sorter e2e 단계).
- 이전 버전은 git history(커밋 `26aab3a` 등)에 남아 있어 필요하면 되살릴 수 있음.

## 워터마크 (요청: 개발자 워터마크)
- HTML v1 화면 오른쪽 아래에 `Developed by kimminkuy70-coder`(작은 회색 글씨, 클릭 방해 없음)와 `<meta name="author">`를 넣음 (`src/index.html`, `src/styles.css`, 빌드 결과 포함). headless Chromium 화면으로 표시 확인.

## 내가 정한 해석 (소유자 확인 전)
- 워터마크의 개발자 이름은 GitHub 계정 `kimminkuy70-coder`로 함 (다른 이름이면 알려주세요).
- "브랜치 ...로 합쳐"는 HTML v1 브랜치를 현재 작업 브랜치에 합치는 것으로 보았고, `claude/cool-meitner-n7uz0l`에는 push하지 않았습니다.
- "다른 버전"은 sorter의 Python/.exe 버전만으로 보고, 다른 두 프로그램과 속도 시험 페이지는 남겼습니다.
- `tools/build_exe.py`, `.github/workflows/build-exe.yml`은 다른 프로그램도 쓸 수 있는 도구라 남겼습니다.

## 남은 일
- `claude/cool-meitner-n7uz0l`과 `claude/program-startup-performance-pjltyn`(저장소 기본 브랜치)에 반영할지, 기본 브랜치를 바꿀지 소유자 확인.
- Windows/Edge에서 HTML v1 실제 확인은 아직 안 됨.

## 소유자 선호
- 한국어로 답, 영어 표현은 영어 그대로. .exe는 Defender 오탐으로 고생해서 쓰지 않는 방향.
