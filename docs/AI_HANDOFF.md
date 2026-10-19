# AI 인수인계 (related-AOI-program)

마지막 갱신: 2026-10-19 · 기준 커밋 `6bdaf67` (SPC 브랜치 `claude/loving-curie-79nq5k`, v6 커밋은 그 다음) · 이슈 #25 (후속: 대화)

## 지금 상태
- **SPC 프로그램(#21~#25)은 브랜치 `claude/loving-curie-79nq5k`에만 있음** (#21 이슈 제목 "새 브랜치에 작성"; #22~#24도 그 파일 수정이라 같은 브랜치에서 이어 작업). 기본 브랜치에는 이 문서만 같은 내용으로 올림. 합칠지는 소유자 결정 (아래 남은 일).
- 작업 브랜치: 저장소 기본 브랜치 `claude/program-startup-performance-pjltyn`. #20에서 `claude/relaxed-goldberg-dnf5nt`(HTML sorter, 2026-10-18 대화 작업)를 기본 브랜치로 fast-forward 해서 합침 (기본 브랜치에만 있던 커밋은 없었음, 잃은 것 없음).
- 프로그램:
  - `programs/AOI_Photo_Sorter_HTML/` **AOI Photo Sorter HTML v2** (`AOI_Photo_Sorter_HTML_v2.html`, Edge에서 여는 HTML 한 파일, Python·.exe 없음)가 sorter의 유일한 버전. 소스 `src/`, 빌드 `python tools/build_html.py` (`--check`로 최신인지 확인). 버전 이름은 `version.json`.
  - `AOI_Color_Gray_Matcher` (Final_v16), `Wafer_Map_Converter` (WebView2_v6): 그대로.
  - `programs/SPC_Chart_HTML/` **SPC Chart HTML v6** (`SPC_Chart_HTML_v6.html`, 브랜치 `claude/loving-curie-79nq5k`; v1→v2(#22)→v3(#23)→v4(#24)→v5(#25)→v6(#25 후속), 옛 파일은 git history에 남음). v6: SIGMA 차트도 OCAP·7run 판정, 추천값은 XBAR·SIGMA 두 칸을 같이 (아래 #25 후속). v5(#25): 다른 프로그램이 만든 .xlsx(zip 안 부분 이름이 엑셀과 다름)를 읽음 + .ods 읽기 + 못 읽을 때 파일 안 이름을 오류 글에 보여 줌 (아래 #25 내용). **실시간 감시가 아니라 정해진 기간의 데이터를 보는 프로그램** (소유자 #24). v4 추가(#24): 기간 전체를 그리고 가로 스크롤 (`표시 점 수` 기본 0 = 전체, `점 간격` 기본 16 px / 화면에 맞춤), XBAR와 SIGMA(MR)가 같이 스크롤, Y축 고정, 표의 행을 누르면 차트가 그 점으로 넘어감, [자동 새로고침](옛 [실시간]) 기본 꺼짐, 예제는 300점 고정 기간. v3 추가(#23): SPC 시스템 양식이면 SPC 시스템 화면처럼 XBAR 차트(EXT_MV, UCL/LCL 선만) 바로 아래 SIGMA 차트(EXT_SIGMA, EXT_SIGMA_UCL/LCL 선), X축 날짜·시간 두 줄(TRAN_TIME → 수정일시 → LOT_ID 순), 히스토그램 = 도수 글자 + 정규분포 곡선 + USL/LSL + 평균±3σ(모든 양식 공통, CL 선은 뺌). v2 추가(#22): SPC 시스템 양식 자동 인식(EXT_MV, EXT_MV_UCL/CENTER/LCL), HTML 표 파일 읽기, 차트 아래 데이터 표(OCAP·7run 행 노랑), 차트 점 더블클릭 → 표의 그 행, 추천값 입력(선택 행 / 전체 일괄), 수정본 xlsx 저장(원본 복사 + 고친 칸 빨강). 나머지는 v1과 같음: 엑셀(.xlsx/.xlsm/.csv)을 골라 I-MR / Xbar-R 관리도, MR/R 차트, 히스토그램, Cp/Cpk/Ppk를 그림. File System Access API 파일 handle을 2초마다 확인(lastModified·size)해 엑셀 저장 시 자동 갱신. 판정 규칙(규격 이탈, 관리한계 이탈, Run 7, Trend 7, 2/3>2σ, 4/5>1σ, 선택: 14 교대, 15 hugging, 8 1σ 밖), 새 이상 알림(배너+소리), OCAP 조치 표(규칙별 조치 문구 편집, 조치 완료·메모는 localStorage), CSV 저장, 예제 데이터. 소스 `src/` (`xlsx.js` 자체 xlsx 읽기 + pako, `spc.js` 계산, `app.js` 화면), 빌드 `python tools/build_html.py --program SPC_Chart_HTML`.
  - 속도 시험 페이지: `experiments/browser_speed_test/AOI_Browser_Speed_Test.html`.
- 시험 (2026-10-19, Linux):
  - #25 후속 v6 (브랜치 `claude/loving-curie-79nq5k`): 같은 명령 37개 통과 (SPC 26 = 25 + SIGMA 1). 시험 자료 `spc_rows()`의 EXT_SIGMA를 0.68 고정 → 0.68/0.45 교대로 바꿈 (고정이면 SIGMA 7run이 모든 행에 걸림), SIGMA 이탈 점은 `spc_rows(sigma_out=True)`일 때만. headless Chromium 스크린샷으로 SIGMA 주황 점·노란 행 확인.
  - #25 (브랜치 `claude/loving-curie-79nq5k`): `python3 -m unittest tests.e2e_spc_chart tests.e2e_html_sorter` 36개 통과 (SPC 25 = 기존 23 + #25 2). `test_startup`/`test_wafer_engine` 11개 오류는 전과 같음 (numpy·webview 없음). Windows Edge, 소유자의 실제 파일로는 확인 못 함.
  - #24 (브랜치 `claude/loving-curie-79nq5k`): `python3 -m unittest tests.e2e_spc_chart tests.e2e_html_sorter` 34개 통과 (SPC 23 = 기존 22 + #24 1). 기존 시험 수정: 자동 새로고침을 쓰는 시험 3개는 `#liveChk`를 켬, X축 라벨 기대값 `13:06` → `11:06` (라벨을 첫 점부터 세게 바꿈). `test_startup`/`test_wafer_engine` 11개 오류는 전과 같음 (numpy·webview 없음). headless Chromium 스크린샷으로 가로 스크롤 화면 확인. Windows Edge 확인 못 함.
  - #23 (브랜치 `claude/loving-curie-79nq5k`): `python3 -m unittest tests.e2e_spc_chart tests.e2e_html_sorter` 33개 통과 (SPC 22 = 기존 20 + #23 2, 기존 양식 시험 1개는 X축 기대값을 LOT_ID → TRAN_TIME으로 바꿈). headless Chromium 스크린샷으로 XBAR/SIGMA/히스토그램 확인. Windows Edge 확인 못 함.
  - #22 (브랜치 `claude/loving-curie-79nq5k`): `python -m unittest tests.e2e_spc_chart tests.e2e_html_sorter` 31개 통과 (SPC 20 = 기존 14 + #22 6). `test_startup`/`test_wafer_engine` 11개 오류는 전과 같음 (numpy·webview 없음). 수정본 xlsx를 LibreOffice(headless)로 열어 값 확인함. Excel/Edge에서는 확인 못 함.
  - `python -m unittest tests.e2e_html_sorter`: 11개 통과 (pip로 `playwright==1.56.0`, `pillow`를 넣어야 함. 1.56.0이 `/opt/pw-browsers`의 chromium-1194와 맞음. 최신 playwright는 없는 브라우저를 찾다 실패).
  - `tests.test_startup`, `tests.test_wafer_engine`: 8개 오류, 모두 `webview`/`openpyxl` 없음 (변경 전과 같음). pytest 없음.
  - #21 (2026-10-19, 브랜치 `claude/loving-curie-79nq5k`): `python -m unittest tests.e2e_html_sorter tests.e2e_spc_chart` 25개 통과 (`pip install playwright==1.56.0 pillow openpyxl`). `test_startup`/`test_wafer_engine`는 openpyxl을 넣으면 11개 오류 (numpy·webview 없음, `xlsx` UnboundLocalError) — #21 변경 전과 같은 결과.
- 릴리스: **없음**. HTML sorter는 `release.yml`(app_manifest.json 기준)이 다루지 않음. #20에서 REST로 GitHub Release `AOI_Photo_Sorter_HTML_v2`를 만들려 했으나 막힘: `Creating, editing, or deleting releases is not permitted for this session type. (HTTP 403)`. 태그도 만들지 않음 (`*_v*` 태그를 push하면 release.yml이 돌다 "no program has the release name"으로 실패하므로). 프로그램 파일은 기본 브랜치의 `programs/AOI_Photo_Sorter_HTML/AOI_Photo_Sorter_HTML_v2.html`에서 바로 내려받으면 됨.

## 이슈 이력
| 날짜 | 이슈 | 요청 | 결과 |
|---|---|---|---|
| 2026-10-18 | (대화) | Sorter HTML v1만 남기고 Python/.exe 버전 삭제, HTML 브랜치 합침, 개발자 워터마크 | `claude/relaxed-goldberg-dnf5nt`에 반영 |
| 2026-10-19 | #25 후속 (대화) | "ㅇㅇ 둘다해, 두 차트를 동시에 고려해서 알맞은 추천값" | SPC Chart HTML v6. SIGMA OCAP(SR1)·7run(SR2 Run, SR3 Trend) 판정·노란 행·이상 목록, 추천값은 걸린 차트의 칸(EXT_MV / EXT_SIGMA)을 같이. 시험 1개 추가, 37개 통과. 릴리스 없음 |
| 2026-10-19 | #25 | SPC v4에서 `20261019214451.xlsx`가 "엑셀 통합 문서(.xlsx)가 아닙니다"로 안 열림 → 수정 | SPC Chart HTML v5 (브랜치 `claude/loving-curie-79nq5k`). xlsx 부분을 `_rels/.rels`로 찾고 이름을 대소문자·`\`·앞 `/` 무시로 찾음, .ods 읽기, 오류 글에 zip 안 이름. 시험 2개 추가, 36개 통과. 실제 파일은 못 받아(403) 원인 확정 못 함. 릴리스 없음. 이슈 중 질문 "시그마 차트에서도 ocap·7run 뜨나"에 답함 (아니오, 확인 요청) |
| 2026-10-19 | #24 | SPC v3: 긴 기간 데이터가 화면에서 잘림 → 횡 스크롤. "실시간이 아니고 정해진 기간 동안 SPC 차트 보는 프로그램" | SPC Chart HTML v4 (브랜치 `claude/loving-curie-79nq5k`). 가로 스크롤, 자동 새로고침 기본 꺼짐. 시험 1개 추가, 34개 통과. 릴리스 없음 |
| 2026-10-19 | #23 | SPC v2 수정: 실제 SPC 화면처럼 XBAR·SIGMA 차트 2개만, UCL/LCL 선만, 히스토그램은 정규분포 선·spec limit·3σ 선·도수 글자, X축 날짜·시간 | SPC Chart HTML v3 (브랜치 `claude/loving-curie-79nq5k`). 시험 2개 추가, 33개 통과. 릴리스 없음 |
| 2026-10-19 | #22 | SPC v1 수정: 첨부 양식(SPC 시스템 export)대로 차트, 아래 데이터 표에 OCAP·7run 행 노랑, 점 더블클릭 → 그 행, 추천값 자동 입력(빨간 칸) 버튼 2개(한 행 / 일괄, 색 구분), 복사본 저장 | SPC Chart HTML v2 (브랜치 `claude/loving-curie-79nq5k`). 시험 6개 추가, 31개 통과. 첨부 xlsx는 403으로 못 받아 이슈 본문의 표(머리글 + 6행)로 양식을 맞춤. 릴리스 없음 |
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

## #22 내용 (SPC Chart HTML v2)
- 첨부 `20261019214451.xlsx`(`github.com/user-attachments/files/33667048/...`)는 다운로드 실패: `{"message":"This GitHub API path is not available: sessions are bound to their configured repositories..."}` (HTTP 403). 이슈 본문에 붙여 준 표(엑셀에서 복사한 머리글 120여 열 + 6행)로 양식을 맞춤. 본문 표의 USL 칸이 `####`(엑셀 열 너비 부족 표시)라 실제 USL 값은 모름 → 파일에 숫자가 있으면 그 값을 씀.
- 양식 인식 (`app.js` `SPC_FORMAT`): 머리글에 `EXT_MV`와 `EXT_MV_UCL`이 있으면 "SPC 시스템 양식". 값 열 기본 = EXT_MV만, X축 = LOT_ID, 항목 = Item. 한계 열은 역할마다 단어 우선순위(`ROLE_WORDS` 첫 단어가 이김)로 고르고 숫자가 있는 열만 씀: UCL=EXT_MV_UCL, LCL=EXT_MV_LCL, CL=EXT_MV_CENTER (TARGET보다 먼저), USL, LSL.
- 노란 행 = 파일 원래 값에서 `SPC.FIX_RULES` = OOS(규격 이탈), R1(관리한계 이탈) = "OCAP", R2(Run 7점), R3(Trend 7점) = "7run"에 걸린 점의 행 (설정에서 꺼진 규칙은 뺌). 규칙이 완성된 점(7번째 점부터)만 노랑, 런 전체가 아님. 추천값을 넣어도 노랑은 유지하고 판정 칸에 "수정됨 ✓".
- 추천값 (`spc.js` `suggest`/`fixAll`): 그 점이 FIX_RULES에서 빠지고 다른 점이 새로 걸리지 않는 값. 후보 순서: 원래 값에서 CL 쪽으로 10%씩 → CL 반대쪽 0.25σ~1σ → CL → CL±2σ 안 0.25σ 격자(원래 값과 가까운 순). 모두 CL±2σ 안, USL/LSL 안. σ = (UCL−CL)/3 (위/아래 따로), 없으면 σ(within). 소수 자리 = 그 열 값의 최대 자리(σ가 작으면 더 늘림). 일괄은 앞에서부터 한 점씩 고치고 다시 판정 (7 Run은 7번째 점 하나로 풀림). subgroup>1이면 버튼 꺼짐.
- 수정본 (`xlsx.js` `copy`): .xlsx/.xlsm이면 읽은 바이트에서 그 시트 XML의 칸만 바꾸고(`<v>`, 수식·문자 형식 제거), styles.xml에 노랑(FFFFFF00)·빨강(FFFF0000) fill과 xf 복제를 더함. 노란 행은 행 스타일(`customFormat`)과 있는 칸 모두. calcChain.xml은 빼고(Content_Types·rels에서도), `calcPr`가 있으면 `fullCalcOnLoad="1"`. 나머지 zip 항목은 압축된 그대로 복사, 바뀐 항목은 무압축 저장. CSV·HTML 표·예제는 새 xlsx(시트 1개)를 만듦. 저장은 `showSaveFilePicker`(원본 handle과 같은 파일이면 거부), 없으면 내려받기.
- 수정은 메모리에만 (`edits`, 'excelRow:col'). 원본 파일이 다시 저장돼 그 칸의 원래 값이 바뀌면 그 수정은 지움. 추천값 입력·설정 변경으로 생긴 판정 변화는 알림(배너·소리)을 띄우지 않음 (파일 저장으로 생긴 새 이상만 알림).
- 시험 (`tests/e2e_spc_chart.py`, #22 6개): 양식 인식·노란 행, 더블클릭 → 선택·화면 안, 한 행/일괄 추천값 → 저장(OPFS로 저장 picker 대신) → openpyxl로 값·fill 확인 + 원본 바이트 그대로, 원본 재저장 시 수정 정리, .xls 이름의 HTML 표, 엔진 fixAll.

## #23 내용 (SPC Chart HTML v3)
- `app.js`: `SPC_FORMAT.sigma`(EXT_SIGMA, EXT_SIGMA_UCL/LCL/CENTER 열)로 `items()`가 EXT_MV 항목에 `sigma`·`lots`(LOT_ID)를 붙이고, `sigmaChart()`가 `res.sigma`를 만들고 `res.rangeFlags`를 SIGMA 한계 이탈 점으로 바꿈 (MR 차트 대신). `drawRange` → `drawSigma`. `drawControl`은 `r.spcForm`이면 UCL/LCL 선만, 축 범위도 UCL/LCL/값만 (USL 13 같은 먼 규격이 차트를 납작하게 하지 않음). `xLabels`는 `YYYY-MM-DD HH:MM` 꼴 라벨을 날짜/시각 두 줄로. `drawHist`: 도수 글자, ±3σ(전체 sd) 보라 점선, CL 선 뺌, 제목 "히스토그램". 카드에 `spc` class → CSS로 SIGMA를 XBAR 아래 같은 폭으로.
- X축 자동 선택 우선순위 TRAN_TIME → 수정일시 → LOT_ID (`SPC_FORMAT.label` 순서). v2가 localStorage에 LOT_ID를 저장해 둔 것은 무시하도록 `settings.cols.labelPicked`(사용자가 [X축]에서 직접 바꾼 경우만 true)를 새로 둠.
- `spc.js`: `fillColumn`을 `SPC.fillColumn`으로 내보냄 (SIGMA 한계 열 빈칸 채우기).

## #24 내용 (SPC Chart HTML v4)
- 원인: v1~v3의 `표시 점 수` 기본값 100 (마지막 100점만 그림, 실시간 감시용 설정) + 차트 폭이 카드 폭에 고정. → `settings.window` 기본 0(기간 전체), 옛 localStorage 값 100은 `settings.v4` 표시로 한 번 0으로 바꿈.
- 구조 (`app.js` `xspan`): 카드 안 `.xscroll > .xinner > canvas.cx + canvas.cr`. `.xinner` 폭 = 점 수 × 점 간격 + 여백, canvas는 `position: sticky; left: 0`에 카드 폭 그대로이고 scrollLeft만큼 옮겨 보이는 점(a..b)만 그림 → Y축 눈금·오른쪽 UCL/LCL 글자 고정. 선·점·X축 글자는 `clipPlot`으로 그림 영역 안만. `canvas._hit.from/to`는 보이는 범위. 스크롤 시 그 카드의 시간 차트만 다시 그림 (`queueCard`). Y축 범위는 기간 전체 값으로 계산 (스크롤해도 눈금이 안 바뀜). X축 라벨은 첫 점부터 세어 일정 간격 (스크롤해도 안 튐).
- `점 간격` select(`settings.pitch`, 0 = 화면에 맞춤, 8~48 px, 기본 16). 점이 적어 화면보다 짧으면 화면 폭에 맞게 늘림. 데이터 표 행 클릭 → `revealRow`로 차트가 그 점 쪽으로 스크롤 (점 더블클릭 → 표 이동은 그대로).
- "실시간 아님": [실시간] 체크 → [자동 새로고침], 기본 꺼짐(`settings.auto`, 켜면 기억). [새로고침] 버튼으로 다시 읽음. 예제는 몇 초마다 1점 추가하던 것 → 300점 고정. 첫 화면·README 글도 "정해진 기간"으로.

## #25 내용 (SPC Chart HTML v5)
- 증상: 그 메시지는 `xlsx.js` `readXlsx`가 zip은 읽었는데 `xl/workbook.xml` 이름의 항목이 없을 때만 나옴 (zip이 아니면 "zip 끝을 찾지 못함"이 나옴). 즉 파일은 zip(OOXML)인데 안 부분 이름이 엑셀 기본과 다름. Excel은 이름이 아니라 `_rels/.rels`의 officeDocument 관계로 workbook을 찾고 이름 대소문자를 가리지 않아서 연다. 첨부 파일은 #22와 같은 이름이고 내려받기는 여전히 HTTP 403이라 실제 안 이름은 모름.
- 수정 (`xlsx.js`): `unzip`이 `partKey`(`\`→`/`, 앞 `./`·`/` 제거, 소문자)로 찾음. `parts(zip)`: workbook = `_rels/.rels` officeDocument → `[Content_Types].xml`의 `spreadsheetml.sheet.main` → 이름이 `workbook*.xml`인 항목 순. sharedStrings·styles·calcChain은 workbook의 .rels 관계로 (없으면 같은 폴더). Strict Open XML의 r:id 네임스페이스, `t="d"` 칸. `copyXlsx`(수정본)도 같은 방법으로 찾고, 바꾼 항목은 원래 zip 이름 그대로 씀. `mimetype`이 ODS면 `readOds`(content.xml, 반복 열·행). workbook이 `.bin`이면 .xlsb 안내. 그래도 못 찾으면 오류 글에 zip 안 이름 8개까지.
- 시험 (`tests/e2e_spc_chart.py` #25 2개): workbook 이름을 바꾸고 .rels로만 가리킨 파일, `\` 구분·대문자 이름 파일을 열고 일괄 추천값 → 수정본 이름 목록이 원본과 같은지·빨강 fill; .ods 열기; workbook 없는 zip은 안 이름을 보여 주는지; .xlsb 안내.

## #25 후속 내용 (SPC Chart HTML v6, 소유자 대화 지시)
- `app.js`: `sigmaItem(it)` = EXT_SIGMA를 XBAR 항목과 같은 행 순서의 별도 item(한계 EXT_SIGMA_UCL/LCL/CENTER 열)으로, `sigmaOpts()` = subgroup 1, 규칙 R1·R2·R3만(설정의 켜기·점 수를 같이 씀, OOS 없음), `min: 0`. `sigmaChart`가 `SPC.analyze`로 판정해 `res.sigmaFlags` = {SR1, SR2, SR3: XBAR 점 번호}, `res.rangeFlags` = SR1, SIGMA 이벤트를 `res.events`에 더함 (`SPC.events` 내보냄). 규칙 id `SR*`는 `ruleName`이 "SIGMA …"로, OCAP 문구는 `baseRule`로 R1~R3 것을 씀. `rowFlags`·`statusOf`·툴팁·SIGMA 점 색에 반영.
- 추천값: [선택 행]은 그 행의 XBAR가 걸리면 EXT_MV, SIGMA가 걸리면 EXT_SIGMA를 각각 `SPC.suggest`로 (둘 다면 두 칸). [전체 일괄]은 `SPC.fixAll`을 XBAR item, SIGMA item에 각각. EXT_MV와 EXT_SIGMA는 서로 다른 열이라 한 칸을 바꿔도 다른 차트 판정은 안 바뀜 → 각 차트에서 풀리는 값을 고르면 두 차트를 같이 만족. `spc.js` `suggest`에 `opts.min`(σ는 0 이상). `items()`의 sigma 값도 수정(edits)을 반영, `sigma.col`.
- 데이터 표: 판정 오른쪽 값 열에 EXT_SIGMA도 (SPC 양식일 때).

## 내가 정한 해석 (확인 전)
- #25 후속: SIGMA 7run도 XBAR와 같은 Run 7점·Trend 7점 (설정 공유), SIGMA 아래쪽 run(산포가 줄어든 경우)도 걸림. SIGMA 추천값 범위는 SIGMA CL ± 2σ(σ = (UCL−CL)/3 위·아래 따로) 안, 0 이상. 원 데이터(VALUE_1~25, EXT_AVERAGE)는 바꾸지 않음 (원하면 평균·σ가 추천값이 되도록 원 데이터를 바꾸는 방법을 제안해 둠).
- #25: 실제 파일을 못 봐서 "zip 안 부분 이름이 다르다"로 보고 고침. v5에서도 안 열리면 새 오류 글(파일 안 이름 목록)을 이슈에 붙여 달라고 함. 버전 이름 v5로 올림.
- #24: 자동 새로고침 기능은 지우지 않고 기본 꺼짐으로만 바꿈 (엑셀을 고쳐 저장하고 다시 볼 때 쓸 수 있게). 스크롤 처음 위치는 기간의 처음(왼쪽). 기본 점 간격 16 px (514행이면 약 8,200 px 폭). 새 이상 알림(배너·소리)은 그대로 두었음 (자동 새로고침을 켰을 때만 의미 있음).
- #23: "UCL/LCL line만 존재" = XBAR·SIGMA 차트에 UCL/LCL 선만 그림 (CL, USL/LSL, ±1σ·±2σ 선 없음). 판정(OCAP·7run)은 그대로 USL/LSL·EXT_MV_CENTER를 씀. SIGMA 한계 이탈은 주황 점과 상태 배지에만 반영, 노란 행·추천값 대상은 아님. 히스토그램 3σ 선 = 평균 ± 3 × 전체 표준편차(정규분포 곡선과 같은 σ). 히스토그램 변경(도수, 3σ, CL 선 제거)은 일반 양식에도 같이 적용. X축은 TRAN_TIME(측정 시각)을 씀.
- #22: "ocap" = 규격 이탈 + 관리한계(UCL/LCL) 이탈, "7run" = 7점 연속 중심선 한쪽 + 7점 연속 상승·하강으로 봄. 2/3>2σ, 4/5>1σ 등 다른 규칙은 노랑·추천값 대상이 아님 (차트·OCAP 목록에는 그대로 나옴).
- #22: "추천값" = 위 규칙을 풀면서 원래 값에 가장 가까운(CL 쪽으로 옮긴) 값, CL±2σ 안. 회사의 추천값 기준(예: CL로 바로, Target 값)이 따로 있으면 바꿔야 함.
- #22: SPC 시스템 양식은 차트 값(EXT_MV)만 고치고 같은 행의 EXT_AVERAGE·VALUE_1·EXT_MEDIAN 등은 그대로 둠. 노란 행은 런 전체가 아니라 규칙이 완성된 점(7번째부터)만.
- #22: 수정본 파일 이름 `원본이름_SPC수정_YYYYMMDD_HHMM.xlsx`, 버전 이름 v2로 올림 (이슈마다 버전 올리는 sorter 관행).
- #21: "새 브랜치"는 이름을 정하지 않아서 이 session에 지정된 `claude/loving-curie-79nq5k`를 기본 브랜치 끝에서 새로 만들어 씀. 프로그램 폴더는 `programs/SPC_Chart_HTML/` (sorter HTML과 같은 구조), 빌드 도구 `tools/build_html.py`에 `--program` 인자를 추가해 같이 씀 (sorter 기본 동작 그대로).
- #21: 관리한계 기본은 I-MR(평균 ± 2.66·MR평균), "7run"은 7점 연속 중심선 한쪽, Trend도 7점(한국 현장 관행)으로 정함. 점 수는 설정에서 바꿈. 14 교대/15 hugging/8 1σ 밖 규칙은 기본 꺼짐. OCAP 기본 문구는 일반 예시 (회사 기준 문구로 바꿔야 함).
- #21: 새 브랜치 작업이라 릴리스하지 않음 (routine 규칙: 이슈가 다른 브랜치를 지정하면 그 브랜치에서 릴리스하지 않음; 또 이 환경은 Release 생성이 HTTP 403, #20 참고). 파일은 브랜치의 `programs/SPC_Chart_HTML/SPC_Chart_HTML_v1.html`을 바로 내려받으면 됨.
- "HTML v1 수정"은 기본 브랜치에 없던 HTML sorter를 고치는 일이라, 그 브랜치를 기본 브랜치로 fast-forward 하고 거기서 고침. 이로써 2026-10-18의 "Python/.exe sorter 삭제"도 기본 브랜치에 들어감.
- 수정 뒤 이름을 v2로 올림 (sorter는 이슈마다 버전을 올려 옴).

## 남은 일 / 소유자에게 물은 것
- **#25 후속**: 소유자가 SIGMA OCAP·7run을 넣으라고 답함 ("ㅇㅇ 둘다해") → v6에서 끝남. 원 데이터 VALUE_1~25도 맞출지는 묻기만 함.
- **#25 (답 기다림)**: v6(또는 v5)로 `20261019214451.xlsx`가 열리는지 확인. 안 열리면 오류 글 전체를 알려 주거나 파일을 저장소에 commit.
- **#21~#24 SPC (답 기다림)**: ⑦ #24 해석 확인 (자동 새로고침을 아예 없앨지, 기본 점 간격 16 px·처음 위치 왼쪽이 괜찮은지). ⑥ #23 해석 확인 (SIGMA 이탈 OCAP은 #25 후속에서 넣음, X축 시간 열 TRAN_TIME이 맞는지, 히스토그램 3σ를 σ(within)로 할지). ① 첨부 사진·엑셀을 못 받아서(HTTP 403) 화면·양식이 실제와 다르면 글로 알려 주거나 파일을 저장소에 commit, ② 기본 브랜치에 합칠지 (합치면 그 뒤로는 기본 브랜치에서 이어 작업), ③ OCAP 규칙별 회사 조치 문구, 판정 규칙 기본값(7점 등) 확인, ④ Windows Edge + 엑셀 실제 사용 확인 (수정본을 Excel이 경고 없이 여는지 포함), ⑤ #22 해석 확인: ocap/7run 범위, 추천값 기준, EXT_MV 외 열(EXT_AVERAGE, VALUE_1)도 같이 고칠지, 노란 행을 런 전체로 할지.
- **브랜치 이름 정리 (#20, 답 기다림)**: routine 규칙상 브랜치 삭제·이름 변경은 하지 않음. 제안: ① 기본 브랜치 `claude/program-startup-performance-pjltyn` → `main`으로 이름 변경 (Settings → Branches, GitHub가 열린 PR·기본 브랜치 설정을 옮겨 줌), ② 다 합쳐진 `claude/relaxed-goldberg-dnf5nt`, `claude/cool-meitner-n7uz0l` 삭제, ③ `ccr-0b38d41f-r1uk33`(KLA-Camtek Converter 초기 작업, 지금은 KLA-CAMTEK-CONVERTER 저장소로 옮겨짐) 삭제 또는 `archive/...`로 이름 변경. 프로그램별 브랜치를 따로 두기보다 한 브랜치(`main`)에 `programs/<이름>/` 폴더로 나누는 지금 구조를 유지하자고 제안. 소유자가 직접 바꾸거나 허락하면 진행. 기본 브랜치 이름을 바꾸면 routine 지시문(작업 브랜치 = 기본 브랜치)은 그대로 맞음.
- Windows/Edge에서 HTML v2 실제 확인은 아직 안 됨.
- HTML sorter 릴리스 방법: 소유자가 GitHub 화면에서 Release를 만들거나, release.yml이 `version.json`도 읽도록 고치는 것을 허락하면 다음 run이 처리 (routine은 workflow를 이슈 요청 없이 고치지 않음).

## 소유자 선호
- 한국어로 답, 영어 표현은 영어 그대로. .exe는 Defender 오탐으로 고생해서 쓰지 않는 방향.
- 개발자 표시는 "개발자 : 김민규" (#20). SPC 프로그램에도 같은 표시 (오른쪽 위).
- 새 프로그램도 HTML 한 파일로 만드는 방향 (#21 "Html로 만들거야").
- SPC 프로그램은 실시간 감시용이 아니라 정해진 기간 동안의 SPC 차트를 보는 프로그램 (#24). 긴 기간은 잘리지 않고 횡 스크롤로 봄.

## 명령
- HTML 빌드: `python tools/build_html.py` / 확인 `python tools/build_html.py --check` (SPC: 둘 다 `--program SPC_Chart_HTML` 붙임)
- 시험: `python -m unittest tests.e2e_html_sorter -v`, SPC `python -m unittest tests.e2e_spc_chart -v` (playwright 1.56.0, openpyxl 필요; `python`이 3.11이면 `python -m pip install playwright==1.56.0 openpyxl pillow`로 같은 python에 설치), `tests/test_*.py`는 `python -m unittest tests.test_startup tests.test_wafer_engine`
- `tools/build_release.py`는 Windows 전용 (Linux에서 돌리지 않음).
