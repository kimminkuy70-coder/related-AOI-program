# AI 인수인계 (related-AOI-program)

마지막 갱신: 2026-10-19 · 기준 커밋 `066e225` (기본 브랜치 끝) · 이슈 #21

## 지금 상태
- **#21 SPC 프로그램은 새 브랜치 `claude/loving-curie-79nq5k`에만 있음** (이슈 제목 "새 브랜치에 작성"). 기본 브랜치에는 이 문서만 같은 내용으로 올림. 합칠지는 소유자 결정 (아래 남은 일).
- 작업 브랜치: 저장소 기본 브랜치 `claude/program-startup-performance-pjltyn`. #20에서 `claude/relaxed-goldberg-dnf5nt`(HTML sorter, 2026-10-18 대화 작업)를 기본 브랜치로 fast-forward 해서 합침 (기본 브랜치에만 있던 커밋은 없었음, 잃은 것 없음).
- 프로그램:
  - `programs/AOI_Photo_Sorter_HTML/` **AOI Photo Sorter HTML v2** (`AOI_Photo_Sorter_HTML_v2.html`, Edge에서 여는 HTML 한 파일, Python·.exe 없음)가 sorter의 유일한 버전. 소스 `src/`, 빌드 `python tools/build_html.py` (`--check`로 최신인지 확인). 버전 이름은 `version.json`.
  - `AOI_Color_Gray_Matcher` (Final_v16), `Wafer_Map_Converter` (WebView2_v6): 그대로.
  - `programs/SPC_Chart_HTML/` **SPC Chart HTML v1** (`SPC_Chart_HTML_v1.html`, 브랜치 `claude/loving-curie-79nq5k`): 엑셀(.xlsx/.xlsm/.csv)을 골라 I-MR / Xbar-R 관리도, MR/R 차트, 히스토그램, Cp/Cpk/Ppk를 그림. File System Access API 파일 handle을 2초마다 확인(lastModified·size)해 엑셀 저장 시 자동 갱신. 판정 규칙(규격 이탈, 관리한계 이탈, Run 7, Trend 7, 2/3>2σ, 4/5>1σ, 선택: 14 교대, 15 hugging, 8 1σ 밖), 새 이상 알림(배너+소리), OCAP 조치 표(규칙별 조치 문구 편집, 조치 완료·메모는 localStorage), CSV 저장, 예제 데이터. 소스 `src/` (`xlsx.js` 자체 xlsx 읽기 + pako, `spc.js` 계산, `app.js` 화면), 빌드 `python tools/build_html.py --program SPC_Chart_HTML`.
  - 속도 시험 페이지: `experiments/browser_speed_test/AOI_Browser_Speed_Test.html`.
- 시험 (2026-10-19, Linux):
  - `python -m unittest tests.e2e_html_sorter`: 11개 통과 (pip로 `playwright==1.56.0`, `pillow`를 넣어야 함. 1.56.0이 `/opt/pw-browsers`의 chromium-1194와 맞음. 최신 playwright는 없는 브라우저를 찾다 실패).
  - `tests.test_startup`, `tests.test_wafer_engine`: 8개 오류, 모두 `webview`/`openpyxl` 없음 (변경 전과 같음). pytest 없음.
  - #21 (2026-10-19, 브랜치 `claude/loving-curie-79nq5k`): `python -m unittest tests.e2e_html_sorter tests.e2e_spc_chart` 25개 통과 (`pip install playwright==1.56.0 pillow openpyxl`). `test_startup`/`test_wafer_engine`는 openpyxl을 넣으면 11개 오류 (numpy·webview 없음, `xlsx` UnboundLocalError) — #21 변경 전과 같은 결과.
- 릴리스: **없음**. HTML sorter는 `release.yml`(app_manifest.json 기준)이 다루지 않음. #20에서 REST로 GitHub Release `AOI_Photo_Sorter_HTML_v2`를 만들려 했으나 막힘: `Creating, editing, or deleting releases is not permitted for this session type. (HTTP 403)`. 태그도 만들지 않음 (`*_v*` 태그를 push하면 release.yml이 돌다 "no program has the release name"으로 실패하므로). 프로그램 파일은 기본 브랜치의 `programs/AOI_Photo_Sorter_HTML/AOI_Photo_Sorter_HTML_v2.html`에서 바로 내려받으면 됨.

## 이슈 이력
| 날짜 | 이슈 | 요청 | 결과 |
|---|---|---|---|
| 2026-10-18 | (대화) | Sorter HTML v1만 남기고 Python/.exe 버전 삭제, HTML 브랜치 합침, 개발자 워터마크 | `claude/relaxed-goldberg-dnf5nt`에 반영 |
| 2026-10-19 | #21 | SPC 프로그램 새로 제작 (HTML, 엑셀 시트 → 실시간 그래프, USL/UCL, OCAP, 7 run 등), 새 브랜치에 | SPC Chart HTML v1을 새 브랜치 `claude/loving-curie-79nq5k`에 만듦. 시험 14개 추가·통과. 릴리스 없음 (새 브랜치, 기본 브랜치 아님). 첨부 사진은 proxy 403으로 못 봄 |
| 2026-10-19 | #20 | 브랜치 이름 정리 + HTML v1 Esc 메뉴 박스 크기, 오른쪽 위 "개발자 : 김민규" | 화면 수정은 HTML v2로 완료. 브랜치 이름 변경은 하지 않고 소유자 확인 요청 (아래 남은 일) |

## #20 내용
- Esc 메뉴(상위 폴더 작업이면 버튼 6개: 확인 화면으로/새로고침/다음 폴더/전체 결과 보기/폴더 목록으로/계속)가 고정 폭 560px 상자 밖으로 튀어나오던 문제: 상자 폭을 내용에 맞추고(최소 560px, 최대 1400px·화면 94%), 넘치면 버튼이 다음 줄로 감 (`src/styles.css` `.modal`). headless Chromium 1914×919, 900×700에서 버튼이 모두 상자 안에 있는지 확인 (v1은 둘 다 밖으로 나감).
- 워터마크: 오른쪽 아래 `Developed by kimminkuy70-coder` → 오른쪽 위 `개발자 : 김민규` (연한 회색, 클릭 방해 없음). 위쪽 막대(`.hud`, `.rhead`)는 오른쪽 120px를 비워 글자가 버튼을 가리지 않게 함. `<meta name="author">`도 김민규.
- v1 파일 `AOI_Photo_Sorter_HTML_v1.html`은 지우고 v2 파일로 바꿈 (git history에 남음).
- 첨부 사진은 이 환경의 proxy가 `private-user-images.githubusercontent.com`을 막아(CONNECT 403) 못 열었음. 글 설명만 보고 고침.

## #21 내용 (SPC Chart HTML v1)
- 요청: "SPC 프로그램, 엑셀 시트 데이터 → 실시간 그래프, 로딩 → 차트 → 데이터 수정 시 그래프 변화, HTML, USL/UCL 등, OCAP, 7run 등, 사진 참고".
- 첨부 사진(`github.com/user-attachments/assets/6b5a6343-…`)은 못 열었음: `github.com/user-attachments` 경로는 session 범위 밖(HTTP 403 "sessions are bound to their configured repositories"), 서명된 `private-user-images.githubusercontent.com` 주소는 proxy가 `CONNECT tunnel failed, response 403`. 화면 배치는 글 설명만 보고 정함 → 사진과 다르면 소유자가 글로 알려 주거나 사진을 저장소에 commit해 주면 맞춤.
- 실시간 방식: 브라우저는 파일 변경 알림이 없어서, [엑셀 열기]로 받은 file handle의 `getFile()`을 주기적으로(기본 2초) 다시 읽어 `lastModified:size`가 바뀌면 다시 그림. 읽기 실패(저장 중, zip 손상)면 전 차트 유지하고 다음 주기에 다시 시도. `<input type=file>`(handle 없음) 경로는 자동 갱신 불가라 상태 글로 알림.
- 시험(`tests/e2e_spc_chart.py`): OPFS 파일을 picker 대신 넘기고, 그 파일을 다시 써서 "엑셀 저장"을 흉내 냄 (갱신·알림·OCAP 저장, 손상 파일 후 회복, 세로/가로 형식, CP949 CSV, 한계 직접 입력, 계산식 검증).
- Linux headless Chromium에서만 확인. Windows Edge에서 실제 엑셀이 연 채로 저장하는 파일을 읽는지(잠금), Edge 권한 창 동작은 **확인 전**.

## 내가 정한 해석 (확인 전)
- #21: "새 브랜치"는 이름을 정하지 않아서 이 session에 지정된 `claude/loving-curie-79nq5k`를 기본 브랜치 끝에서 새로 만들어 씀. 프로그램 폴더는 `programs/SPC_Chart_HTML/` (sorter HTML과 같은 구조), 빌드 도구 `tools/build_html.py`에 `--program` 인자를 추가해 같이 씀 (sorter 기본 동작 그대로).
- #21: 관리한계 기본은 I-MR(평균 ± 2.66·MR평균), "7run"은 7점 연속 중심선 한쪽, Trend도 7점(한국 현장 관행)으로 정함. 점 수는 설정에서 바꿈. 14 교대/15 hugging/8 1σ 밖 규칙은 기본 꺼짐. OCAP 기본 문구는 일반 예시 (회사 기준 문구로 바꿔야 함).
- #21: 새 브랜치 작업이라 릴리스하지 않음 (routine 규칙: 이슈가 다른 브랜치를 지정하면 그 브랜치에서 릴리스하지 않음; 또 이 환경은 Release 생성이 HTTP 403, #20 참고). 파일은 브랜치의 `programs/SPC_Chart_HTML/SPC_Chart_HTML_v1.html`을 바로 내려받으면 됨.
- "HTML v1 수정"은 기본 브랜치에 없던 HTML sorter를 고치는 일이라, 그 브랜치를 기본 브랜치로 fast-forward 하고 거기서 고침. 이로써 2026-10-18의 "Python/.exe sorter 삭제"도 기본 브랜치에 들어감.
- 수정 뒤 이름을 v2로 올림 (sorter는 이슈마다 버전을 올려 옴).

## 남은 일 / 소유자에게 물은 것
- **#21 SPC (답 기다림)**: ① 첨부 사진을 못 봐서 화면이 사진과 다르면 바꿀 점을 글로 알려 주기, ② 기본 브랜치에 합칠지 (합치면 그 뒤로는 기본 브랜치에서 이어 작업), ③ OCAP 규칙별 회사 조치 문구, 판정 규칙 기본값(7점 등) 확인, ④ Windows Edge + 엑셀 실제 사용 확인.
- **브랜치 이름 정리 (#20, 답 기다림)**: routine 규칙상 브랜치 삭제·이름 변경은 하지 않음. 제안: ① 기본 브랜치 `claude/program-startup-performance-pjltyn` → `main`으로 이름 변경 (Settings → Branches, GitHub가 열린 PR·기본 브랜치 설정을 옮겨 줌), ② 다 합쳐진 `claude/relaxed-goldberg-dnf5nt`, `claude/cool-meitner-n7uz0l` 삭제, ③ `ccr-0b38d41f-r1uk33`(KLA-Camtek Converter 초기 작업, 지금은 KLA-CAMTEK-CONVERTER 저장소로 옮겨짐) 삭제 또는 `archive/...`로 이름 변경. 프로그램별 브랜치를 따로 두기보다 한 브랜치(`main`)에 `programs/<이름>/` 폴더로 나누는 지금 구조를 유지하자고 제안. 소유자가 직접 바꾸거나 허락하면 진행. 기본 브랜치 이름을 바꾸면 routine 지시문(작업 브랜치 = 기본 브랜치)은 그대로 맞음.
- Windows/Edge에서 HTML v2 실제 확인은 아직 안 됨.
- HTML sorter 릴리스 방법: 소유자가 GitHub 화면에서 Release를 만들거나, release.yml이 `version.json`도 읽도록 고치는 것을 허락하면 다음 run이 처리 (routine은 workflow를 이슈 요청 없이 고치지 않음).

## 소유자 선호
- 한국어로 답, 영어 표현은 영어 그대로. .exe는 Defender 오탐으로 고생해서 쓰지 않는 방향.
- 개발자 표시는 "개발자 : 김민규" (#20). SPC 프로그램에도 같은 표시 (오른쪽 위).
- 새 프로그램도 HTML 한 파일로 만드는 방향 (#21 "Html로 만들거야").

## 명령
- HTML 빌드: `python tools/build_html.py` / 확인 `python tools/build_html.py --check` (SPC: 둘 다 `--program SPC_Chart_HTML` 붙임)
- 시험: `python -m unittest tests.e2e_html_sorter -v`, SPC `python -m unittest tests.e2e_spc_chart -v` (playwright 1.56.0, openpyxl 필요), `tests/test_*.py`는 `python -m unittest tests.test_startup tests.test_wafer_engine`
- `tools/build_release.py`는 Windows 전용 (Linux에서 돌리지 않음).
