# AI 인수인계 (related-AOI-program)

마지막 갱신: 2026-10-19 · 기준 커밋 `79c07e4` (`claude/relaxed-goldberg-dnf5nt` 끝) · 이슈 #20

## 지금 상태
- 작업 브랜치: 저장소 기본 브랜치 `claude/program-startup-performance-pjltyn`. #20에서 `claude/relaxed-goldberg-dnf5nt`(HTML sorter, 2026-10-18 대화 작업)를 기본 브랜치로 fast-forward 해서 합침 (기본 브랜치에만 있던 커밋은 없었음, 잃은 것 없음).
- 프로그램:
  - `programs/AOI_Photo_Sorter_HTML/` **AOI Photo Sorter HTML v2** (`AOI_Photo_Sorter_HTML_v2.html`, Edge에서 여는 HTML 한 파일, Python·.exe 없음)가 sorter의 유일한 버전. 소스 `src/`, 빌드 `python tools/build_html.py` (`--check`로 최신인지 확인). 버전 이름은 `version.json`.
  - `AOI_Color_Gray_Matcher` (Final_v16), `Wafer_Map_Converter` (WebView2_v6): 그대로.
  - 속도 시험 페이지: `experiments/browser_speed_test/AOI_Browser_Speed_Test.html`.
- 시험 (2026-10-19, Linux):
  - `python -m unittest tests.e2e_html_sorter`: 11개 통과 (pip로 `playwright==1.56.0`, `pillow`를 넣어야 함. 1.56.0이 `/opt/pw-browsers`의 chromium-1194와 맞음. 최신 playwright는 없는 브라우저를 찾다 실패).
  - `tests.test_startup`, `tests.test_wafer_engine`: 8개 오류, 모두 `webview`/`openpyxl` 없음 (변경 전과 같음). pytest 없음.
- 릴리스: **없음**. HTML sorter는 `release.yml`(app_manifest.json 기준)이 다루지 않음. #20에서 REST로 GitHub Release `AOI_Photo_Sorter_HTML_v2`를 만들려 했으나 막힘: `Creating, editing, or deleting releases is not permitted for this session type. (HTTP 403)`. 태그도 만들지 않음 (`*_v*` 태그를 push하면 release.yml이 돌다 "no program has the release name"으로 실패하므로). 프로그램 파일은 기본 브랜치의 `programs/AOI_Photo_Sorter_HTML/AOI_Photo_Sorter_HTML_v2.html`에서 바로 내려받으면 됨.

## 이슈 이력
| 날짜 | 이슈 | 요청 | 결과 |
|---|---|---|---|
| 2026-10-18 | (대화) | Sorter HTML v1만 남기고 Python/.exe 버전 삭제, HTML 브랜치 합침, 개발자 워터마크 | `claude/relaxed-goldberg-dnf5nt`에 반영 |
| 2026-10-19 | #20 | 브랜치 이름 정리 + HTML v1 Esc 메뉴 박스 크기, 오른쪽 위 "개발자 : 김민규" | 화면 수정은 HTML v2로 완료. 브랜치 이름 변경은 하지 않고 소유자 확인 요청 (아래 남은 일) |

## #20 내용
- Esc 메뉴(상위 폴더 작업이면 버튼 6개: 확인 화면으로/새로고침/다음 폴더/전체 결과 보기/폴더 목록으로/계속)가 고정 폭 560px 상자 밖으로 튀어나오던 문제: 상자 폭을 내용에 맞추고(최소 560px, 최대 1400px·화면 94%), 넘치면 버튼이 다음 줄로 감 (`src/styles.css` `.modal`). headless Chromium 1914×919, 900×700에서 버튼이 모두 상자 안에 있는지 확인 (v1은 둘 다 밖으로 나감).
- 워터마크: 오른쪽 아래 `Developed by kimminkuy70-coder` → 오른쪽 위 `개발자 : 김민규` (연한 회색, 클릭 방해 없음). 위쪽 막대(`.hud`, `.rhead`)는 오른쪽 120px를 비워 글자가 버튼을 가리지 않게 함. `<meta name="author">`도 김민규.
- v1 파일 `AOI_Photo_Sorter_HTML_v1.html`은 지우고 v2 파일로 바꿈 (git history에 남음).
- 첨부 사진은 이 환경의 proxy가 `private-user-images.githubusercontent.com`을 막아(CONNECT 403) 못 열었음. 글 설명만 보고 고침.

## 내가 정한 해석 (확인 전)
- "HTML v1 수정"은 기본 브랜치에 없던 HTML sorter를 고치는 일이라, 그 브랜치를 기본 브랜치로 fast-forward 하고 거기서 고침. 이로써 2026-10-18의 "Python/.exe sorter 삭제"도 기본 브랜치에 들어감.
- 수정 뒤 이름을 v2로 올림 (sorter는 이슈마다 버전을 올려 옴).

## 남은 일 / 소유자에게 물은 것
- **브랜치 이름 정리 (#20, 답 기다림)**: routine 규칙상 브랜치 삭제·이름 변경은 하지 않음. 제안: ① 기본 브랜치 `claude/program-startup-performance-pjltyn` → `main`으로 이름 변경 (Settings → Branches, GitHub가 열린 PR·기본 브랜치 설정을 옮겨 줌), ② 다 합쳐진 `claude/relaxed-goldberg-dnf5nt`, `claude/cool-meitner-n7uz0l` 삭제, ③ `ccr-0b38d41f-r1uk33`(KLA-Camtek Converter 초기 작업, 지금은 KLA-CAMTEK-CONVERTER 저장소로 옮겨짐) 삭제 또는 `archive/...`로 이름 변경. 프로그램별 브랜치를 따로 두기보다 한 브랜치(`main`)에 `programs/<이름>/` 폴더로 나누는 지금 구조를 유지하자고 제안. 소유자가 직접 바꾸거나 허락하면 진행. 기본 브랜치 이름을 바꾸면 routine 지시문(작업 브랜치 = 기본 브랜치)은 그대로 맞음.
- Windows/Edge에서 HTML v2 실제 확인은 아직 안 됨.
- HTML sorter 릴리스 방법: 소유자가 GitHub 화면에서 Release를 만들거나, release.yml이 `version.json`도 읽도록 고치는 것을 허락하면 다음 run이 처리 (routine은 workflow를 이슈 요청 없이 고치지 않음).

## 소유자 선호
- 한국어로 답, 영어 표현은 영어 그대로. .exe는 Defender 오탐으로 고생해서 쓰지 않는 방향.
- 개발자 표시는 "개발자 : 김민규" (#20).

## 명령
- HTML 빌드: `python tools/build_html.py` / 확인 `python tools/build_html.py --check`
- 시험: `python -m unittest tests.e2e_html_sorter -v`, `tests/test_*.py`는 `python -m unittest tests.test_startup tests.test_wafer_engine`
- `tools/build_release.py`는 Windows 전용 (Linux에서 돌리지 않음).
