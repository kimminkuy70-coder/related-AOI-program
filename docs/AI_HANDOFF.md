# AI 인수인계 (related-AOI-program)

마지막 갱신: 2026-10-21 · 기준 커밋 `0598545` (SPC 브랜치 `claude/loving-curie-79nq5k`) · #31 (SPC v15: 측정값 열 접기, [시뮬레이션] 행 삭제만 · 행 수정만 · 최소 행 변경과 모드별 양식 저장, 데이터 표 드래그 복사)

## 지금 상태
- **SPC 프로그램(#21~#25)은 브랜치 `claude/loving-curie-79nq5k`에만 있음** (#21 이슈 제목 "새 브랜치에 작성"; #22~#24도 그 파일 수정이라 같은 브랜치에서 이어 작업). 기본 브랜치에는 이 문서만 같은 내용으로 올림. 합칠지는 소유자 결정 (아래 남은 일).
- 작업 브랜치: 저장소 기본 브랜치 `claude/program-startup-performance-pjltyn`. #20에서 `claude/relaxed-goldberg-dnf5nt`(HTML sorter, 2026-10-18 대화 작업)를 기본 브랜치로 fast-forward 해서 합침 (기본 브랜치에만 있던 커밋은 없었음, 잃은 것 없음).
- 프로그램:
  - `programs/AOI_Photo_Sorter_HTML/` **AOI Photo Sorter HTML v2** (`AOI_Photo_Sorter_HTML_v2.html`, Edge에서 여는 HTML 한 파일, Python·.exe 없음)가 sorter의 유일한 버전. 소스 `src/`, 빌드 `python tools/build_html.py` (`--check`로 최신인지 확인). 버전 이름은 `version.json`.
  - `AOI_Color_Gray_Matcher` (Final_v16), `Wafer_Map_Converter` (WebView2_v6): 그대로.
  - `programs/SPC_Chart_HTML/` **SPC Chart HTML v15** (`SPC_Chart_HTML_v15.html`, 브랜치 `claude/loving-curie-79nq5k`; v1→v2(#22)→v3(#23)→v4(#24)→v5(#25)→v6(#25 후속)→v7(#25 후속 2)→v8(#25 후속 4)→v9(#27)→v10(#28)→v11(#27 후속)→v12(#27 후속 3)→v13(#29)→v14(#30)→v15(#31), 옛 파일은 git history에 남음). v15: 측정값 열 접기(기본 접힘), 버튼 [선택 행 추천값 입력] | [시뮬레이션 ▾] → 행 삭제만 · 행 수정만 · 최소 행 변경(삭제+수정), 모드별 양식 저장(삭제 = OCAP 삭제 양식, 수정 = RAW_DATA 수정 양식, 최소 = 둘 다 한 번에 각각의 파일), [수정 모두 취소]·[수정본 엑셀 저장]·[수정 양식 저장]은 표 아래, 데이터 표 드래그 → Ctrl+C → 엑셀에 화면 색 그대로 (아래 #31 내용). v14: [설정 저장]/[설정 불러오기], [최소 행 변경](삭제+값 수정 섞어 바꾸는 행 수 최소), OCAP 삭제 양식을 소유자 양식 파일대로(Sheet1 하나, 지울 행마다 한 줄), [수정 양식 저장](RAW_DATA 수정 양식) (아래 #30 내용). v13: 판정 규칙을 XBAR·SIGMA 차트별로 따로 설정, 기본값 XBAR = OCAP·7run(Run 7), SIGMA = OCAP·7run·Trend 6, [자동 새로고침] 삭제 (아래 #29 내용). v12: OCAP 삭제 양식을 소유자 엑셀 사진대로 (아래 #27 후속 3). v11: 삭제 시뮬레이션을 한 행씩(가장 앞 행부터, 지울 때마다 다시 판정) + Trend 기본 7→6점 (아래 #27 후속 2). v10: [OCAP 삭제 양식 저장] (아래 #28 내용). v9: [삭제 시뮬레이션] (아래 #27 내용). v8: 2/3>2σ(R4)·4/5>1σ(R5) 기본 꺼짐. v7: 점 하나로 안 풀리는 Run/Trend는 같은 런의 다른 점을 고침. v6: SIGMA 차트도 OCAP·7run 판정, 추천값은 XBAR·SIGMA 두 칸을 같이 (아래 #25 후속). v5(#25): 다른 프로그램이 만든 .xlsx(zip 안 부분 이름이 엑셀과 다름)를 읽음 + .ods 읽기 + 못 읽을 때 파일 안 이름을 오류 글에 보여 줌 (아래 #25 내용). **실시간 감시가 아니라 정해진 기간의 데이터를 보는 프로그램** (소유자 #24). v4 추가(#24): 기간 전체를 그리고 가로 스크롤 (`표시 점 수` 기본 0 = 전체, `점 간격` 기본 16 px / 화면에 맞춤), XBAR와 SIGMA(MR)가 같이 스크롤, Y축 고정, 표의 행을 누르면 차트가 그 점으로 넘어감, [자동 새로고침](옛 [실시간]) 기본 꺼짐, 예제는 300점 고정 기간. v3 추가(#23): SPC 시스템 양식이면 SPC 시스템 화면처럼 XBAR 차트(EXT_MV, UCL/LCL 선만) 바로 아래 SIGMA 차트(EXT_SIGMA, EXT_SIGMA_UCL/LCL 선), X축 날짜·시간 두 줄(TRAN_TIME → 수정일시 → LOT_ID 순), 히스토그램 = 도수 글자 + 정규분포 곡선 + USL/LSL + 평균±3σ(모든 양식 공통, CL 선은 뺌). v2 추가(#22): SPC 시스템 양식 자동 인식(EXT_MV, EXT_MV_UCL/CENTER/LCL), HTML 표 파일 읽기, 차트 아래 데이터 표(OCAP·7run 행 노랑), 차트 점 더블클릭 → 표의 그 행, 추천값 입력(선택 행 / 전체 일괄), 수정본 xlsx 저장(원본 복사 + 고친 칸 빨강). 나머지는 v1과 같음: 엑셀(.xlsx/.xlsm/.csv)을 골라 I-MR / Xbar-R 관리도, MR/R 차트, 히스토그램, Cp/Cpk/Ppk를 그림. File System Access API 파일 handle을 2초마다 확인(lastModified·size)해 엑셀 저장 시 자동 갱신. 판정 규칙(규격 이탈, 관리한계 이탈, Run 7, Trend 7, 2/3>2σ, 4/5>1σ, 선택: 14 교대, 15 hugging, 8 1σ 밖), 새 이상 알림(배너+소리), OCAP 조치 표(규칙별 조치 문구 편집, 조치 완료·메모는 localStorage), CSV 저장, 예제 데이터. 소스 `src/` (`xlsx.js` 자체 xlsx 읽기 + pako, `spc.js` 계산, `app.js` 화면), 빌드 `python tools/build_html.py --program SPC_Chart_HTML`.
  - 속도 시험 페이지: `experiments/browser_speed_test/AOI_Browser_Speed_Test.html`.
- 시험 (2026-10-19~21, Linux):
  - #31 v15: `python3 -m unittest tests.e2e_spc_chart tests.e2e_html_sorter` 53개 통과 (SPC 42 = 38 + `test_layout_value_fold_and_buttons`, `test_fix_mode_saves_raw_form`, `test_mix_mode_saves_both_forms`, `test_drag_copy_keeps_colours`; 기존 시험은 `self.sim('#…Btn')`으로 [시뮬레이션] 메뉴를 열고 누르게, 행 수정만이 켜짐 상태(끄면 전 수정으로)인 것에 맞게 고침). `test_startup`/`test_wafer_engine` 11개 오류는 전과 같음. headless Chromium 스크린샷(예제 + 최소 행 변경)으로 버튼 배치 · 결과 상자 · 표 아래 버튼 · 접힌 측정값 열 확인. 실제 Excel에 붙여 넣기, Edge 폴더 선택 창은 확인 못 함 (시험은 합성 copy 이벤트의 text/html · text/plain, OPFS 폴더로 확인).
  - #30 v14: `python3 -m unittest tests.e2e_spc_chart` 38개 통과 (SPC 34 + `test_raw_data_form`, `test_min_change_plan_engine`, `test_min_change_button`, `test_save_and_load_settings`; `test_ocap_delete_form`은 새 양식으로 고침), `tests.e2e_html_sorter` 11개 통과. `test_startup`/`test_wafer_engine` 11개 오류는 전과 같음. `python3 -m pip install playwright==1.56.0 openpyxl` + `--force-reinstall pillow` 필요 (`pip`과 `python3`이 다른 Python이라 `python3 -m pip`으로). headless Chromium 스크린샷으로 최소 행 변경 상자 · 위쪽 버튼 확인. 합성 1,300행 자료로 최소 행 변경 계산 약 4.6초 (삭제만 274행 / 수정만 73행 → 섞기 71행). Windows Edge · Excel · 실제 파일로는 확인 못 함.
  - #29 v13: `python3 -m unittest tests.e2e_spc_chart tests.e2e_html_sorter` 45개 통과 (SPC 34 = 33 + `test_rules_per_chart`; 자동 새로고침 시험 3개는 [새로고침] 클릭으로, Trend 엔진 시험 2개는 R3를 직접 켜도록, R3 기본값 기대 False로 고침). `test_startup`/`test_wafer_engine` 11개 오류는 전과 같음. headless Chromium으로 설정 창(XBAR / SIGMA 두 칸) 확인. Windows Edge 확인 못 함.
  - #27 후속 3 v12: 같은 명령 44개 통과 (`test_ocap_delete_form`을 새 배치로 고침). 소유자 실제 파일(126762, scratchpad에서만)로 양식 저장 → 시트 `전체`, `126762`(머리글 + 15행, 110열) 확인, LibreOffice PDF로 모양 확인. Excel에서 연 모습은 확인 못 함.
  - #27 후속 2 v11: `python3 -m unittest tests.e2e_spc_chart tests.e2e_html_sorter` 44개 통과 (SPC 33 = 31 + 2; Trend 시험은 6점 기준으로 고침). 소유자 실제 파일(scratchpad에서만): 전체 기간 237행(v10) → 190행(185+5), 2026-07-01~ 기간 63행 → 51행(50+1), 모두 지운 뒤 XBAR·SIGMA 이상 0 (Trend 6점 기준이라 노란 행 수도 늘어남).
  - #28 v10: `python3 -m unittest tests.e2e_spc_chart tests.e2e_html_sorter` 42개 통과 (SPC 31 = 30 + #28 1). `pip install playwright==1.56.0 openpyxl` + `pip install --force-reinstall pillow` 필요했음. 저장한 양식 파일을 LibreOffice(headless)로 PDF 변환해 열리는지 확인. Windows Excel, 회사 실제 양식·시스템 업로드로는 확인 못 함.
  - #27 v9: `python3 -m unittest tests.e2e_spc_chart tests.e2e_html_sorter` 41개 통과 (SPC 30 = 28 + #27 2). `tests.test_startup`/`test_wafer_engine` 11개 오류는 전과 같음 (numpy·webview 없음). 이 환경의 시스템 Pillow가 깨져 있어(`cannot import name '_imaging'`) `pip install --force-reinstall pillow` 해야 sorter 시험이 건너뛰지 않음. headless Chromium으로 예제 데이터 삭제 시뮬레이션 화면 확인. Windows Edge, 실제 파일로는 확인 못 함.
  - #25 후속 4 v8: 39개 통과 (SPC 28 = 27 + 기본 꺼짐·옛 설정 시험 1, R4 시험은 규칙을 직접 켜도록 고침). 실제 파일: 일괄 수정 → 저장 → 다시 열기 후 XBAR·SIGMA 이상 점 0.
  - #25 후속 2 v7 (브랜치 `claude/loving-curie-79nq5k`): 38개 통과 (SPC 27 = 26 + 1). 소유자가 대화로 준 실제 파일(고객 데이터, 저장소에 넣지 않음, scratchpad에서만)로 확인: 열기 OK(v4도 OK), 일괄 추천값 → 남은 노란 행 0, 노란 행마다 [선택 행] 하나씩 → 모두 성공, 수정본 = 고친 칸 수만큼만 다르고 빨강.
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
| 2026-10-21 | #31 | 가독성: 측정값 열 접기(기본 접힘), [선택 행 추천값 입력]을 1번째 + 짧은 세로선 + 나머지 묶음, [수정 모두 취소]/[수정본 엑셀 저장]은 엑셀 차트(데이터 표) 아래, 표를 드래그 복사 → 엑셀에 화면 그대로, 나머지 묶음 = [시뮬레이션] 상위 버튼 + 하위 행 삭제만 / 행 수정만 / 최소 행 변경(삭제+수정), 모드별 결과를 양식 엑셀로 저장(최소는 2개 한 번에 각각), 데이터 표 문구 수정 | SPC Chart HTML v15 (브랜치 `claude/loving-curie-79nq5k`, `0598545`). 시험 4개 추가, 53개 통과. 릴리스 없음 |
| 2026-10-21 | #30 | 설정 저장 버튼(껐다 켜도 유지) + 삭제뿐 아니라 값 수정까지 고려해 행 변경 횟수 최소 로직과 실행 버튼. 같은 run 중 대화로 양식 파일 2개(OCAP 삭제 양식, RAW_DATA 수정 양식) 주며 "이 양식대로 저장, 지금 양식은 안 맞음, 삭제 요청 = 삭제 아이템, 나머지 = 수정 아이템" | SPC Chart HTML v14 (브랜치 `claude/loving-curie-79nq5k`, `53dd4ae`): [설정 저장]/[설정 불러오기], [최소 행 변경], OCAP 삭제 양식 새 배치, [수정 양식 저장]. 시험 4개 추가, 38개 통과. 릴리스 없음 |
| 2026-10-20 | #29 | Xbar 경고 = OCAP·7run, Sigma 경고 = OCAP·7run·6 Trend. 설정에서 그래프마다 분리, 자동 새로고침 삭제, 위 설정을 기본값으로 | SPC Chart HTML v13 (브랜치 `claude/loving-curie-79nq5k`, `bd75541`): [규칙 · OCAP 설정]에 XBAR 칸 / SIGMA 칸 따로(켜기·점 수), 기본값 요청대로, [자동 새로고침]·새로고침 간격 삭제. 시험 1개 추가, 45개 통과. 릴리스 없음 |
| 2026-10-20 | #27 후속 3 (대화) | 엑셀 화면 사진(OCAP 삭제 요청 아이템 파일: 시트 `전체` + Spec seq#별 시트) + "그냥 사진에 있는대로 전체 시트만 추려내서 만들라니까? Ocap 저장양식" | SPC Chart HTML v12: 양식 시트 이름 `전체`, 사진 배치(B2 제목, E1~E3 [Option] 하늘색, 5행 묶음 머리글, 6행 회색 머리글, 7행부터 데이터, 23행까지 빈 테두리), 요청 내용 글은 사진 그대로. Spec seq# 시트 = 원본 시트에서 지울 행만 추려 낸 것(원본 머리글 + 모든 열). 44개 통과. 릴리스 없음 |
| 2026-10-20 | #27 후속 2 (대화) | "바꾸고 추가로 trend 기본값 7에서 6으로" (= 삭제 시뮬레이션을 한 행씩 방식으로) | SPC Chart HTML v11: `SPC.deletePlan` 한 행씩, Trend 기본 6점 (옛 설정에 저장된 7은 한 번 지움, 일부러 바꾼 값은 유지; 설정 저장은 기본값과 다른 점 수만). 시험 2개 추가, 44개 통과. 릴리스 없음 |
| 2026-10-20 | #27 후속 (대화) | "삭제 전 파일은 3차까지, XBAR 노란 행만 지운 파일은 1차만 → 왜 다르냐" (실제 파일 2개, scratchpad에서만, v9로 확인) | 코드 수정 없음. 원인: ① 두 파일의 기간이 다름 (삭제 전 파일 1,344행 2025-08-29~, 지운 파일 651행 2026-07-01~; 2·3차 행 대부분이 7월 이전) ② 차수는 지운 횟수가 아니라 연쇄 단계 (같은 기간이면 원래 59+4=63행, 소유자 방식 48+12=60행). 한 행씩(가장 앞 행부터) 지우고 다시 판정하면 7월~ 기간 48행, 전체 기간 184행(차수 방식 237행)으로 줄어듦 → 방식 바꿀지 물음 |
| 2026-10-20 | #28 | 이슈 본문의 OCAP 삭제 양식(EDC Plan · Spec seq# · Data seq#(각 개별 sheet에 기입) · 요청 내용)에 맞게 삭제 아이템을 저장하는 기능, 지금 저장 기능과 별개, 이름은 OCAP 삭제 양식 | SPC Chart HTML v10 (브랜치 `claude/loving-curie-79nq5k`): 삭제 시뮬레이션 상자에 [OCAP 삭제 양식 저장] → `OCAP 삭제 양식_YYYYMMDD_HHMM.xlsx` (양식 시트 + Spec seq#별 시트에 DATA_SEQ 목록). 시험 1개 추가, 42개 통과. 릴리스 없음 |
| 2026-10-20 | #27 | 노란 행(OCAP·7run)을 지우면 다른 곳에서 다시 생길 수 있음 → 지웠을 때 추가로 생기는 점을 확인하고, XBAR·SIGMA 모두 OCAP·7run이 안 나오려면 어떤 점을 지워야 하는지 알려 주는 기능 | SPC Chart HTML v9 (브랜치 `claude/loving-curie-79nq5k`): [삭제 시뮬레이션] 버튼, 차수별(1차 = 노란 행, 2차 = 1차를 지우면 새로 생기는 행 …) 지울 행 목록, 지운 뒤 차트·표, 삭제 목록 CSV. 시험 2개 추가, 41개 통과. 릴리스 없음 |
| 2026-10-20 | #26 | 질문: 자동추천값을 어떤 원리로 고치는지, 쉬운 버전·중간 버전 2가지로 설명 | 코드 수정 없음 (SPC v8 그대로). 이슈 댓글로 답: `spc.js` `valueFor`/`suggestChange`/`fixAll` 기준 (후보 순서, CL±2σ·규격·0 이상 제한, 새 이상 금지, 같은 런의 앞 점 대신 고치기, 일괄은 앞에서부터 한 점씩 다시 판정). 시험 안 돌림 (코드 안 바뀜). 릴리스 없음 |
| 2026-10-18 | (대화) | Sorter HTML v1만 남기고 Python/.exe 버전 삭제, HTML 브랜치 합침, 개발자 워터마크 | `claude/relaxed-goldberg-dnf5nt`에 반영 |
| 2026-10-19 | #25 후속 4 (대화) | 주황 점 처리 = "규칙 끄기, 기본값을 꺼짐으로" | v8: `SPC.DEFAULT_ON` R4·R5 false, 옛 버전이 저장한 설정도 `settings.v8` 표시로 한 번만 끔 (다시 켜면 유지). 시험 39개 통과. 릴리스 없음 |
| 2026-10-19 | #25 후속 3 (대화) | "일괄 수정 → 저장 → 다시 열기 했는데 주황 점은 뭐야" | 코드 수정 없음. 실제 파일로 재현: 다시 열면 노란 행 0, SIGMA 이상 0, 남은 주황 점은 XBAR R4(2/3>2σ) 15점·R5(4/5>1σ) 10점 = OCAP·7run 밖이라 노랑·추천값 대상이 아닌 규칙 (#22 해석). 처리 방법 물음 (남은 일) |
| 2026-10-19 | #25 후속 2 (대화) | 실제 파일로 검증 + "추천값을 못 정할 때가 있는 이유" | 원인: Run 7번째 점을 CL 반대쪽으로 옮기면 다음 점과 Trend 7점이 생김 → 그 점 값만으로는 불가. v7에서 같은 런의 앞 점을 대신 고침. 실제 파일 실패 1점 → 0점. 릴리스 없음 |
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

## #27 내용 (SPC Chart HTML v9, 삭제 시뮬레이션)
- `spc.js` `SPC.deletePlan(series, maxRounds)`: series = [{item, opts, rules, keys(엑셀 행), tag}]. 차수마다 지운 행(key)을 모든 series에서 null로 두고 `analyze` → rules에 걸린 점의 행 = 이번 차수, 모두 지우고 다음 차수. 걸린 행이 없으면 `clean: true`. 기본 200차까지.
- `app.js`: `delMode`(버튼 `#delBtn` 켜기/끄기), `delPlan` = `planDeletes()` (파일 원래 값 `items(false, true)`, XBAR는 `fixRules()`, SIGMA는 `sigmaItem`·`sigmaOpts`·`sigmaRules()` tag `S`, subgroup 1일 때만 SIGMA). 켜 있으면 `items()`가 `delPlan.round`의 행을 null로 → 차트·`nowFlags`는 지운 뒤 모습, `yellow`는 파일 그대로. 표: 지운 행 class `del`(회색 취소선) + "삭제 N차" 표시, 표 위 `#delBox`에 차수별 행 번호(누르면 그 행), 결론 글, [삭제 목록 CSV](`delCsv`: 차수, 엑셀 행, X축, LOT_ID, 판정). 켜 있는 동안 추천값 버튼 꺼짐. 시험용 `window.__spc.delPlan()`.
- 시험 (`tests/e2e_spc_chart.py`): 엔진 차수 시험(OCAP 점을 지우면 6점+6점 런이 이어져 12점 런 → 2차 6행), SPC 양식 화면 시험(1차 = 노란 행, 켜면 XBAR·SIGMA 이상 0, 점 수 감소, CSV, 끄면 원래대로).

## #31 내용 (SPC Chart HTML v15)
- 측정값 열: `index.html` `<details id="valueFold">` (열지 않은 상태로 시작, 상태 저장 안 함). 요약 줄 `#valueSum` = 그리는 열 이름 · 개수 / 전체 숫자 열 수 · SPC 시스템 양식 표시 · 한계 열 (`renderValueSum()`, 펼치기·접기 때도 다시 씀).
- 버튼: 데이터 표 머리 `#fixOneBtn` → `.vsep`(짧은 세로선) → `.simgroup`(`#simBtn` + `#simMenu` 안 하위 버튼 `#delBtn` 행 삭제만, `#fixAllBtn` 행 수정만, `#mixBtn` 최소 행 변경). id는 시험 호환으로 그대로. `#simBtn`은 메뉴 펼치기만 (`simOpen`), 모드가 켜 있으면 메뉴가 계속 보이고 `#simBtn` 글이 "시뮬레이션: 모드 이름". `#undoBtn`·`#saveBtn`·`#rawFormBtn`·`#copyBtn`은 표 아래 `.dfoot`.
- 모드 (`app.js`): `simMode()` = 'mix' | 'fix' | 'del' | null, `setSim(mode)`: `simOff()`(mix·fix는 `prevEdits`로 되돌림, delMode 끔) 뒤 같은 모드면 끄기만, 다르면 켬 (`toggleDelete`/`toggleFix`/`toggleMix`는 켜기만). 새 `fixPlan = {prevEdits, made, failed}`: 켜면 edits를 비우고 파일 원래 값에서 `applyFixAll()`(옛 `fixAll`의 계산 부분). `dropMix` → `dropSim` (파일·시트·열·규칙이 바뀌면 mix·fix 계획만 끝내고 edits는 남김). 모드가 켜 있으면 `#fixOneBtn` 꺼짐, 행 수정만·최소일 때 `#undoBtn` 꺼짐.
- 결과 상자(`#delBox`): 행 삭제만 = 전과 같은 차수 목록 + `#ocapFormBtn` "OCAP 삭제 양식 엑셀 저장"; 행 수정만 = `renderFixBox` (고친 행 목록, 남은 OCAP·7run, `#fixFormBtn` → `saveRawForm`, CSV `fixCsv` "SPC_수정목록_"); 최소 = `renderMixBox` + `#bothFormBtn` → `saveBothForms()`: `showDirectoryPicker({id: 'spcForms', mode: 'readwrite'})` 한 번 → 폴더에 `OCAP 삭제 양식_…xlsx`, `RAW_DATA 수정 양식_…xlsx` 둘 다 씀 (저장 창을 두 번 띄우면 두 번째는 클릭 허가가 없어질 수 있어서 폴더 하나로). 한쪽이 비면 그 파일 하나만 `saveBytes`, 폴더 선택이 없는 브라우저면 내려받기 2개.
- 문구: 범례 "값을 고친 칸 (추천값 · 시뮬레이션)", "시뮬레이션에서 지운 행", 최소 행 변경의 삭제 행 표시 "삭제 (최소 행 변경)", 상태 글 "시뮬레이션 · …: … · 다시 누르면 원래대로", 비교 글 "행 삭제만 · 행 수정만", 첫 화면 안내 · README.
- 드래그 복사: `table.data { user-select: none }`, `mousedown`/`mouseover`로 `pick = {a, b}`(table.rows 줄 번호, cellIndex; 머리글 줄 포함), Shift+클릭으로 넓히기, 표 상자 가장자리에서 끌면 스크롤. 여러 칸을 끌었으면 그 click은 행 선택을 하지 않음 (capture에서 막음). `document` `copy` 이벤트(입력 칸에 focus가 있거나 글자가 선택돼 있으면 건드리지 않음): `text/html` = 칸마다 inline style(노랑 #fff59d, 빨강 #ef4444 흰 굵은 글, 삭제 회색 #cbd5e1 + 취소선, 머리글 #eef2f8 / 값 열 #dbe6fb, 판정 글 #9a3412, 얇은 테두리, 숫자가 아닌 글자는 `mso-number-format:'\@'`로 텍스트), `text/plain` = 탭 구분. 색은 getComputedStyle이 아니라 class로 정함 (마우스가 올라간 줄의 hover 색, 선택 줄 테두리가 섞이지 않게). `[고른 칸 복사]` 버튼 = `document.execCommand('copy')`.
- 시험용 `window.__spc.fixPlan()`, `simMode()`.

## #30 내용 (SPC Chart HTML v14)
- 양식 파일 2개는 소유자가 run 중 대화로 준 것 (이슈 첨부 아님, 저장소에 넣지 않음; 예시 행에 고객사 이름이 있어 문서에도 적지 않음). 읽은 배치:
  - OCAP 삭제 양식: 시트 하나(Sheet1), B2 제목(굵게 10pt), 5행 C~E "OCAP 전체 삭제 시 / OCAP 일부 삭제 시 / 요청 사항", 6행 B~E 머리글(회색 AEAAAA, 테두리), 7행부터 B EDC Plan(굵게) · C Spec seq# · D Data seq# · E 요청 내용(9pt), 26행까지 빈 테두리, 열 너비 B 64.9 · C 17.8 · D 21.8 · E 44.3. [Option] 상자, 개별 시트 없음.
  - RAW_DATA 수정 양식: Sheet1, B2 "S/S 25>"(12pt), 3행 B DATA_SEQ#(연두 C6E0B4) · C~AA Raw Value 1~25(하늘 D9E1F2) · AB~AD MAX/MIN/AVG(살구 F8CBAD) · AE STD(회색 D0CECE), 굵게 12pt 가운데 테두리, 4행 노란 줄(A도 노랑), MAX~AVG 숫자 형식 `###0.0000;\-###0.0000`, 행 높이 17.5, 열 너비 A 5.6 · B 17.3 · C 14.7 · AB 16.1 · AC 16.4 · AD 17.8 · AE 16.3. (theme 색은 Office 기본 테마 값으로 바꿔 씀.)
- `xlsx.js` `book`: 이름 붙인 스타일 7개 대신 셀마다 `{sz, b, fill, border, h, wrap, fmt}` 객체 → 쓰인 조합만 styles.xml에 만듦. 시트에 `height`(모든 행 높이), `widths`의 0은 건너뜀.
- `app.js` `ocapFormSheets(plan)`: 위 삭제 양식, 지울 행(plan.round 키)마다 한 줄 (PLAN_NAME, SPEC_SEQ, DATA_SEQ). `rawFormRows()`/`rawFormSheets()`/`saveRawForm()`: `edits`가 있는 행마다 한 줄. 새 Raw Value = m1 + (v − m0) × k, m0 = 원래 VALUE 평균, m1 = m0 + (새 EXT_MV − 원래 EXT_MV), k = 새 EXT_SIGMA / 원래 VALUE의 SD(표본·모집단 중 파일 EXT_SIGMA에 가까운 쪽; EXT_SIGMA를 안 고쳤으면 1). 소수 4자리(원 값이 더 길면 그 자리)로 반올림 뒤 MAX/MIN/AVG/STD 계산. VALUE 열이 없으면 AVG/STD만. 버튼 `#rawFormBtn`(데이터 표 머리, 수정이 있을 때만).
- `spc.js` `SPC.minChangePlan(series)`: deletePlan과 같은 series. 가장 앞 걸린 행 key0의 후보 = key0 삭제, key0 값 수정(걸린 모든 series를 `valueFor`로, 하나라도 못 찾으면 후보 아님), R2/R3면 앞 N−1점마다 삭제·값 수정. 후보를 적용해 다시 판정한 걸린 행 수가 가장 적은 것 (같으면 수정 > 삭제, key0 > 다른 행). 끝나면 뒤에서부터 하나씩 빼 보고 여전히 깨끗하면 뺌. deletePlan(삭제만), series별 fixAll(수정만)과 비교해 행 수가 가장 적은 깨끗한 것 반환 `{deletes, changes:[{key, series, index, value, rules}], rows, clean, method, compare}`. subgroup>1 series는 수정 안 함.
- `app.js` `mixPlan`·`toggleMix`·`mixDelPlan`·`renderMixBox`·`mixCsv`: 버튼 `#mixBtn`. 켜면 edits를 계획의 새 값으로 바꾸고(전 edits는 `prevEdits`로 보관, 끄면 되돌림), `delMode` = true + `delPlan` = 계획의 삭제(1차 하나). 이때 `fixItems = items(true)`(새 값 반영). `buildTable`/`recompute`에서 `dropMix()` (계획만 끝내고 edits는 남김). 켜 있는 동안 [삭제 시뮬레이션]·[수정 모두 취소]·추천값 버튼 꺼짐. 시험용 `window.__spc.mixPlan()`.
- 설정: `normalize(settings)`로 옛 설정 정리 코드를 함수로 뺌. `saveSettingsNow`: `save()` 후 localStorage 다시 읽어 확인 + `SPC_Chart_설정.json`(`{app, version, saved, settings}`)을 `showSaveFilePicker`(처음 한 번, handle은 IndexedDB `settingsFile`, 다음부터 덮어씀; 없으면 내려받기). `loadSettingsFile`: `#setIn`으로 고른 파일의 `settings`를 normalize → save → 다시 그림. `window.__spc.settings`는 getter로 바꿈 (불러오기로 객체가 바뀌므로). OCAP 기록(ocapLog)은 파일에 넣지 않음.

## #29 내용 (SPC Chart HTML v13)
- `spc.js`: `DEFAULT_ON.R3 = false` (XBAR Trend 기본 꺼짐), `SIGMA_DEFAULT_ON = {R1, R2, R3: true}` 내보냄. Trend 점 수 기본 6, Run 7 그대로.
- `app.js`: `settings.sigma = {rules, n}` (SIGMA 전용 켜기·점 수). `sigmaRules()`/`sigmaOpts()`가 이것을 씀. `ruleN(id)`: SR* 규칙은 SIGMA 점 수로 이름·설명. 설정 창: "XBAR 차트" 칸(모든 규칙 + OCAP 문구) / "SIGMA 차트" 칸(관리한계 이탈·Run·Trend, OCAP 문구는 같은 규칙 것을 같이 씀), 입력에 `data-chart="x"|"s"`. [기본값으로]는 두 차트 모두 기본값. 옛 설정은 `settings.v13` 표시로 XBAR R3를 한 번 끔 (다시 켜면 유지), `auto`·`pollSec` 지움.
- 자동 새로고침 삭제: `#liveChk`, `schedule()`/타이머, 설정 창의 새로고침 간격 없앰. [새로고침] 버튼으로만 다시 읽음 (새 이상 알림·소리는 [새로고침]으로 다시 읽을 때 그대로).

## #27 후속 3 내용 (SPC Chart HTML v12, OCAP 삭제 양식 = 사진대로)
- `app.js` `OCAP_FORM`(sheet `전체`, option 3줄, lastRow 23), `ocapFormSheets`: 위 배치. 개별 시트 = `table.rows[table.head]`(원본 머리글 줄, `buildTable`이 `head` 저장) + 지울 행의 `d.cells` 그대로 (예전 No/LOT_ID/X축/차수/판정 표는 없앰).
- `xlsx.js` `book` 스타일 추가: group(가운데, 테두리 없음), small(테두리, 왼쪽, 9pt), option(하늘색 FFDDEBF7, 9pt); title은 굵게 11pt 가운데.

## #27 후속 2 내용 (SPC Chart HTML v11)
- `spc.js` `deletePlan`: 차수 시작 때 걸린 행 집합(mine) 중 지금도 걸린 가장 앞 행 하나를 지우고 `judge()`(모든 series 다시 판정) 반복, mine이 다 풀리면 다음 차수 = 그때 걸린 행. 1차는 노란 행 중 실제로 지운 행 (앞 행을 지우면 Run이 짧아져 풀린 노란 행은 남음). 반환 모양(rounds, clean)은 그대로라 표 · CSV · #28 OCAP 삭제 양식은 그대로 씀.
- `RULES` R3 `n: 6`. `app.js`: `settings.v11` 표시로 저장된 `n.R3 === 7`을 한 번 지움. [규칙 · OCAP 설정] 저장은 기본값과 다른 점 수만 `settings.n`에 둠 (다음에 기본값이 바뀌어도 따라가게). 첫 화면 안내 글 Trend 6점. 삭제 상자 결론에 "노란 행 중 N행은 앞 행을 지우면 풀려서 남깁니다".
- SIGMA 차트 Trend도 같은 설정이라 6점.

## #28 내용 (SPC Chart HTML v10, OCAP 삭제 양식)
- 양식은 이슈 본문(엑셀에서 복사한 HTML 표)대로: B2 제목 "OCAP 삭제 양식", 4행 C~E "OCAP 전체 삭제 시 / OCAP 일부 삭제 시 / 요청 사항", 5행 B~E "EDC Plan / Spec seq# / Data seq# / 요청 내용" (회색 #AEAAAA, 테두리), 6행부터 한 줄씩. #22 본문의 실제 행을 보면 EDC Plan 문자열 = **PLAN_NAME 열**, Spec seq# = **SPEC_SEQ 열**, Data seq# = **DATA_SEQ 열**.
- `xlsx.js` `XLSXLite.book(sheets)`: 여러 시트 + 스타일 4개(title, head, cell, text) 새 xlsx. `app.js` `ocapFormSheets(plan)`: `delPlan`의 모든 차수 행을 (PLAN_NAME, SPEC_SEQ)로 묶어 양식 시트 한 줄씩, 묶음마다 시트(이름 = Spec seq#, 겹치면 " (2)") = EDC Plan, Spec seq#, 표(No, Data seq#, LOT_ID, X축, EXT_MV, EXT_SIGMA, 삭제 차수, 판정, 엑셀 행; 없는 열은 뺌). `saveOcapForm` → 공용 `saveBytes`(수정본 저장과 같은 picker, 원본 덮어쓰기 거부). 버튼 `#ocapFormBtn`은 `#delBox` 머리(삭제 시뮬레이션을 켜야 보임). 시험용 `window.__spc.ocapFormSheets()`, `ocapFormName()`.
- 시험 (`tests/e2e_spc_chart.py` `test_ocap_delete_form`): SPEC_SEQ 두 개 파일 → 시트 이름, 양식 칸·색·테두리, 시트마다 DATA_SEQ가 삭제 행과 같은지.

## #25 후속 2 (SPC Chart HTML v7)
- 실제 파일: 부분 이름은 엑셀 표준 그대로였고 v4로도 열림. 파일의 docProps 저장 시각이 이슈 오류 시각보다 약 1분 뒤 (Excel이 다시 저장한 파일) → 오류가 난 원래 파일(SPC 시스템이 내려준 그대로)은 확인 못 함. v5의 "이름이 다름" 원인은 짐작이었고 이 파일과는 맞지 않음. v5의 진단 오류 글(파일 안 이름 목록)은 그대로 둠: 원래 export 파일로 다시 나면 그 글로 원인을 알 수 있음.
- 추천값 실패 원인: `suggest`는 그 점 하나만 바꿈. Run 7번째 점 → CL 같은 쪽이면 Run 그대로, 반대쪽이면 앞 5점 하강 + 다음 점이 더 낮아 Trend 7점이 새로 생김 → 어떤 값도 안 됨. 그 밖의 실패 가능: CL ± 2σ·규격·0 이상 범위 안에 맞는 값이 없을 때, subgroup > 1.
- 수정 (`spc.js`): `valueFor(item, opts, res, before, pi, pj, rules)` = 점 pj의 값을 바꿔 pi를 풀고 새 이상이 없는 값 (예전 `suggest` 후보 순서 그대로, pj의 한계로). `suggestChange` = 먼저 그 점, 안 되면 그 점이 R2/R3이면 앞 N−1점 중 움직임(σ 단위)이 가장 작은 점 → `{row, value}`. `suggest`는 그 점 값만(호환). `fixAll`은 `suggestChange`를 씀. `app.js` `fixOne`은 다른 행을 고치면 상태 글에 "N행 값만으로는 안 풀려 같은 런의 EXT_MV M행에 추천값 입력".

## #25 후속 내용 (SPC Chart HTML v6, 소유자 대화 지시)
- `app.js`: `sigmaItem(it)` = EXT_SIGMA를 XBAR 항목과 같은 행 순서의 별도 item(한계 EXT_SIGMA_UCL/LCL/CENTER 열)으로, `sigmaOpts()` = subgroup 1, 규칙 R1·R2·R3만(설정의 켜기·점 수를 같이 씀, OOS 없음), `min: 0`. `sigmaChart`가 `SPC.analyze`로 판정해 `res.sigmaFlags` = {SR1, SR2, SR3: XBAR 점 번호}, `res.rangeFlags` = SR1, SIGMA 이벤트를 `res.events`에 더함 (`SPC.events` 내보냄). 규칙 id `SR*`는 `ruleName`이 "SIGMA …"로, OCAP 문구는 `baseRule`로 R1~R3 것을 씀. `rowFlags`·`statusOf`·툴팁·SIGMA 점 색에 반영.
- 추천값: [선택 행]은 그 행의 XBAR가 걸리면 EXT_MV, SIGMA가 걸리면 EXT_SIGMA를 각각 `SPC.suggest`로 (둘 다면 두 칸). [전체 일괄]은 `SPC.fixAll`을 XBAR item, SIGMA item에 각각. EXT_MV와 EXT_SIGMA는 서로 다른 열이라 한 칸을 바꿔도 다른 차트 판정은 안 바뀜 → 각 차트에서 풀리는 값을 고르면 두 차트를 같이 만족. `spc.js` `suggest`에 `opts.min`(σ는 0 이상). `items()`의 sigma 값도 수정(edits)을 반영, `sigma.col`.
- 데이터 표: 판정 오른쪽 값 열에 EXT_SIGMA도 (SPC 양식일 때).

## 내가 정한 해석 (확인 전)
- #31 "측정값 열" = 위쪽 설정 줄의 [측정값 열] 체크 상자 묶음 (SPC 양식이면 숫자 열이 100개 넘어 줄을 많이 차지함). 데이터 표의 열을 접는 뜻이었으면 고쳐야 함. 접힘 상태는 저장하지 않고 열 때마다 접힘.
- #31 나머지 묶음 = 삭제 시뮬레이션 · 전체 일괄 추천값 입력 · 최소 행 변경 → [시뮬레이션] 아래 행 삭제만 · 행 수정만 · 최소 행 변경. "행 수정만"도 시뮬레이션이라 다른 두 모드처럼 파일 원래 값에서 계산하고, 다시 누르면 켜기 전 수정으로 돌아감 (예전 [전체 일괄 추천값 입력]은 지금 수정 위에 더하고 [수정 모두 취소]로만 되돌렸음). 켜 있는 동안 [수정본 엑셀 저장]은 그 값으로 저장됨.
- #31 [수정 양식 저장](수동 추천값용)도 표 아래로 같이 옮김 (요청은 [수정 모두 취소]·[수정본 엑셀 저장]만 말함). "엑셀 차트" = 데이터 표로 봄.
- #31 최소 행 변경의 "2개 한번에" = 폴더를 한 번 고르면 두 파일을 각각 저장. 삭제나 수정 한쪽이 0행이면 있는 쪽 파일 하나만.
- #31 드래그 복사 범위는 사각형 하나 (Ctrl+클릭 여러 범위 없음). 붙여 넣으면 값은 화면 글자 그대로 (예: 날짜는 화면 모양 글자, 수식 없음).
- #30 설정 저장: 설정은 원래 바뀔 때마다 localStorage에 자동 저장되고 있었음. 소유자 PC에서 유지가 안 됐다면 Edge가 닫을 때 사이트 데이터를 지우는 회사 정책일 가능성이 커서, 버튼은 브라우저 저장 + 설정 파일 둘 다 함 (파일은 처음 한 번 위치를 물음). 브라우저가 지워졌으면 [설정 불러오기]로 파일을 직접 열어야 함 (브라우저는 사용자가 고르지 않은 파일을 못 읽음). 자동 저장은 그대로 둠.
- #30 최소 행 변경: "행 변경 횟수" = 지우는 행 + 값을 고치는 행 (한 행의 EXT_MV·EXT_SIGMA를 같이 고치면 1행). 수학적 최솟값이 아닌 탐욕 방법 + 정리 + 두 방법과 비교 (삭제만·수정만보다 많지 않음은 보장). 동점이면 값 수정 우선. 버튼은 계산 후 바로 적용(빨간 칸·회색 삭제 행)하고 다시 누르면 되돌림.
- #30 OCAP 삭제 양식: "일부 삭제"이므로 지울 데이터마다 한 줄, Data seq# 칸에 DATA_SEQ, Spec seq#도 같이 적음 (양식 예시는 Data seq# 칸이 비어 있었음). 26행 넘게 지우면 줄이 이어짐. 개별 시트는 없앰.
- #30 RAW_DATA 수정 양식: 고친 행 = 데이터 표의 빨간 칸이 있는 행 (추천값 버튼이든 최소 행 변경이든). Raw Value는 원 데이터를 평행 이동 + 비율 조정해서 만듦 (회사가 원하는 Raw 값 만드는 방법이 따로 있으면 바꿔야 함). EXT_MV를 VALUE 평균으로 보지 않고 "바뀐 만큼 옮김"으로 처리. MAX~STD는 값으로 넣음 (수식 아님). 파일 이름 `RAW_DATA 수정 양식_YYYYMMDD_HHMM.xlsx` (원래 양식 파일 이름의 한글 부분은 받은 파일 이름에서 깨져 있어 모름).
- #29: Xbar "7run" = Run 7점만 (Trend는 기본 꺼짐, 설정에서 켤 수 있음), Sigma "7run, 6 Trend" = Run 7점 + Trend 6점. 규격 이탈(OOS)은 XBAR OCAP에 그대로 포함 (SIGMA는 규격 없음). OCAP 조치 문구는 차트별로 나누지 않고 규칙마다 하나를 같이 씀. 옛 버전 설정의 점 수(Run·Trend)는 XBAR 쪽에만 남고 SIGMA는 기본값으로 시작. 자동 새로고침은 기능 자체를 지움 (#24에서는 기본 꺼짐만 했음).
- #27 후속 3: "전체 시트만 추려내서" = 사진의 `전체` 시트 모양 그대로 + 개별 시트는 원본 시트에서 지울 행만 추려 냄으로 봄. 개별 시트까지 빼고 `전체` 시트 하나만 원했으면 고쳐야 함. 요청 내용·Option 글은 사진처럼 닫는 괄호 없이. 열 너비는 사진 눈대중(A 12, B 75, C 22, D 27, E 58).
- #27 후속 2: "바꾸고" = 앞 답에서 물은 "한 행씩 지우고 다시 판정" 방식으로 바꿈 (두 방식 같이 보여 주기는 안 함). 순서는 엑셀 행 순서(가장 앞부터). 차수 표시는 유지 (1차 = 노란 행 중 지울 행, 2차 = 그 뒤에 새로 생긴 행). Trend 6점은 XBAR · SIGMA 둘 다, Run은 7점 그대로.
- #28: "삭제 아이템" = [삭제 시뮬레이션]의 모든 차수 행 (1차만이 아니라 다 지워야 OCAP·7run이 안 남으므로). 버튼은 삭제 시뮬레이션 상자 안에만 둠. 우리는 일부 삭제라 "OCAP 일부 삭제 시" Data seq# 칸 = "각 개별 sheet에 기입"(본문 예시 그대로), Spec seq#도 같이 적음. 요청 내용 글은 본문에서 잘려 보인 "…(Data 자체 완전 삭제"에 닫는 괄호를 붙여 고정 문구로 씀. 개별 시트는 Spec seq#마다 하나, 이름 = Spec seq#, 열 구성은 내가 정함 (회사 양식의 개별 시트 모양을 모름). 파일 이름 `OCAP 삭제 양식_YYYYMMDD_HHMM.xlsx`. 본문의 아래 빈 테두리 행(빈 칸 양식)은 넣지 않음.
- #27: "삭제" = 그 엑셀 행 전체를 지움 (XBAR 점과 SIGMA 점이 같이 빠짐). 원본 파일은 바꾸지 않고 화면에서만 지운 모습을 보여 주고 목록·CSV로 알려 줌 (수정본에서 행을 실제로 지우는 저장은 만들지 않음). 방법은 소유자 설명대로 차수별(그때 걸린 행을 모두 지움) → 지울 행 수가 가장 적은 조합이라는 보장은 없음. 계산은 파일 원래 값 기준 (추천값 수정은 뺌). 관리한계가 엑셀 열이면 지워도 한계 그대로, 계산 한계면 지운 뒤 데이터로 다시 계산. 판정 규칙은 노란 행과 같음 (OCAP·7run, 설정에서 켠 것).
- #25 후속 2: 그 점으로 안 풀리면 같은 런의 다른 점 하나를 바꿈 (두 점 이상 바꾸는 조합은 시도하지 않음). Trend 점도 같은 방법. OCAP(규격·관리한계 이탈) 점은 그 점 자체가 이탈이라 다른 점으로 대신하지 않음.
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
- **#31 (확인 요청)**: v15를 Edge에서 ① 측정값 열이 맞는 곳인지 (데이터 표 열 접기를 원했는지), ② 표 드래그 → 엑셀 붙여 넣기 모양, ③ [양식 2개 엑셀 저장]의 폴더 선택 · 두 파일, ④ 행 수정만을 끄면 수정이 되돌아가는 동작이 괜찮은지 확인 요청.
- **#30 (확인 요청)**: v14로 ① [설정 저장] 뒤 Edge를 껐다 켜서 설정이 남는지 (안 남으면 회사 정책으로 지워지는 것 → [설정 불러오기]), ② [최소 행 변경] 결과 행 수, ③ OCAP 삭제 양식 · RAW_DATA 수정 양식이 회사 시스템에 그대로 올라가는지 (Data seq# 칸에 DATA_SEQ를 넣은 것, Raw Value 만드는 방법, MAX~STD를 수식으로 원하는지) 확인 요청.
- **#30 후속 (대화 질문, 2026-10-21)**: "프로그램은 EXT_MV/EXT_SIGMA를 고치는데 양식은 AVG/STD냐, 나머지 데이터도 고쳤냐" → 답: 수정 양식의 Raw Value 1~25는 새 EXT_MV/EXT_SIGMA에 맞게 다시 만든 값이고 AVG/STD/MAX/MIN은 그 값으로 계산함. 단 [수정본 엑셀 저장] 복사본은 EXT_MV/EXT_SIGMA 칸만 바뀌고 VALUE_1~25, EXT_AVERAGE, EXT_MIN/MAX/MEDIAN은 그대로. 복사본의 원 데이터도 같이 고칠지 물음 (답 기다림). 코드 수정 없음.
- **#28**: OCAP 삭제 양식은 #30에서 소유자 양식 파일로 바꿈 (개별 sheet 질문은 끝남, 요청 내용 문구는 양식 그대로).
- **#27 (확인 요청)**: 실제 파일로 [삭제 시뮬레이션] 결과 확인. 행 수가 가장 적은 조합을 찾는 방법, 또는 행을 실제로 지운 수정본 저장이 필요한지 물음.
- **#25 후속**: 소유자가 SIGMA OCAP·7run을 넣으라고 답함 ("ㅇㅇ 둘다해") → v6에서 끝남. 원 데이터 VALUE_1~25도 맞출지는 묻기만 함.
- **#25 (답 기다림)**: v6(또는 v5)로 `20261019214451.xlsx`가 열리는지 확인. 안 열리면 오류 글 전체를 알려 주거나 파일을 저장소에 commit.
- **#21~#24 SPC (답 기다림)**: ⑦ #24 해석 확인 (기본 점 간격 16 px·처음 위치 왼쪽이 괜찮은지; 자동 새로고침은 #29에서 없앰). ⑥ #23 해석 확인 (SIGMA 이탈 OCAP은 #25 후속에서 넣음, X축 시간 열 TRAN_TIME이 맞는지, 히스토그램 3σ를 σ(within)로 할지). ① 첨부 사진·엑셀을 못 받아서(HTTP 403) 화면·양식이 실제와 다르면 글로 알려 주거나 파일을 저장소에 commit, ② 기본 브랜치에 합칠지 (합치면 그 뒤로는 기본 브랜치에서 이어 작업), ③ OCAP 규칙별 회사 조치 문구, 판정 규칙 기본값(7점 등) 확인, ④ Windows Edge + 엑셀 실제 사용 확인 (수정본을 Excel이 경고 없이 여는지 포함), ⑤ #22 해석 확인: ocap/7run 범위, 추천값 기준, EXT_MV 외 열(EXT_AVERAGE, VALUE_1)도 같이 고칠지, 노란 행을 런 전체로 할지.
- **브랜치 이름 정리 (#20, 답 기다림)**: routine 규칙상 브랜치 삭제·이름 변경은 하지 않음. 제안: ① 기본 브랜치 `claude/program-startup-performance-pjltyn` → `main`으로 이름 변경 (Settings → Branches, GitHub가 열린 PR·기본 브랜치 설정을 옮겨 줌), ② 다 합쳐진 `claude/relaxed-goldberg-dnf5nt`, `claude/cool-meitner-n7uz0l` 삭제, ③ `ccr-0b38d41f-r1uk33`(KLA-Camtek Converter 초기 작업, 지금은 KLA-CAMTEK-CONVERTER 저장소로 옮겨짐) 삭제 또는 `archive/...`로 이름 변경. 프로그램별 브랜치를 따로 두기보다 한 브랜치(`main`)에 `programs/<이름>/` 폴더로 나누는 지금 구조를 유지하자고 제안. 소유자가 직접 바꾸거나 허락하면 진행. 기본 브랜치 이름을 바꾸면 routine 지시문(작업 브랜치 = 기본 브랜치)은 그대로 맞음.
- Windows/Edge에서 HTML v2 실제 확인은 아직 안 됨.
- HTML sorter 릴리스 방법: 소유자가 GitHub 화면에서 Release를 만들거나, release.yml이 `version.json`도 읽도록 고치는 것을 허락하면 다음 run이 처리 (routine은 workflow를 이슈 요청 없이 고치지 않음).

## 소유자 선호
- OCAP 삭제 양식 · RAW_DATA 수정 양식은 소유자가 준 양식 파일 배치 그대로 (#30, "이 양식대로"). 삭제 요청 양식 = 삭제할 아이템, RAW_DATA 양식 = 수정할 아이템.
- SPC 경고 기본값 (#29, 소유자 결정): XBAR = OCAP·7run, SIGMA = OCAP·7run·6 Trend, 설정은 차트마다 따로. 자동 새로고침은 없앰.
- SPC Trend 기본 6점 (Run은 7점), 삭제 시뮬레이션은 한 행씩 지우고 다시 판정하는 방식 (#27 후속 2, 소유자 결정).
- SPC 판정 기본 규칙은 OCAP(규격·관리한계 이탈)·7run(Run·Trend)만. 2/3>2σ, 4/5>1σ는 기본 꺼짐 (#25 후속 4, 소유자 결정).
- 한국어로 답, 영어 표현은 영어 그대로. .exe는 Defender 오탐으로 고생해서 쓰지 않는 방향.
- 개발자 표시는 "개발자 : 김민규" (#20). SPC 프로그램에도 같은 표시 (오른쪽 위).
- 새 프로그램도 HTML 한 파일로 만드는 방향 (#21 "Html로 만들거야").
- SPC 프로그램은 실시간 감시용이 아니라 정해진 기간 동안의 SPC 차트를 보는 프로그램 (#24). 긴 기간은 잘리지 않고 횡 스크롤로 봄.

## 명령
- HTML 빌드: `python tools/build_html.py` / 확인 `python tools/build_html.py --check` (SPC: 둘 다 `--program SPC_Chart_HTML` 붙임)
- 시험: `python -m unittest tests.e2e_html_sorter -v`, SPC `python -m unittest tests.e2e_spc_chart -v` (playwright 1.56.0, openpyxl 필요; `python`이 3.11이면 `python -m pip install playwright==1.56.0 openpyxl pillow`로 같은 python에 설치), `tests/test_*.py`는 `python -m unittest tests.test_startup tests.test_wafer_engine`
- `tools/build_release.py`는 Windows 전용 (Linux에서 돌리지 않음).
