# AGENTS 3장 — 파일별 책임 > 입력과 상태

### 입력과 상태

- `src/capa_simulation/application_bootstrap.py` — 빈 시나리오 저장소에만 내장 시드로 첫 시나리오·공식버전을 만든다.
  - 시드 생성 뒤 발행 전에 멈췄으면 다음 시작에서 발행만 복구한다. 공식버전 없는 사용자 시나리오는 발행하지 않는다.
  - 보관본도 사용자 시나리오다 — 공식 없이 보관본만 남은 저장소는 빈 저장소가 아니라 시드를 만들지 않는다
    (`list_scenarios(include_archived=True)`). 발행 복구는 저장소(보관본 포함)에 시드 하나뿐일 때만이다 — 곁에 다른 시나리오가
    있으면 되돌린 보관 시드로 보고 발행하지 않는다.
  - `seed=False`(운영 서버 — `scenario_activation.builtin_seed_allowed`)면 시드를 만들지도, 발행 전에 멈춘 시드를 발행하지도
    않는다 — 빈 저장소는 공식버전 없이 남는다(`empty_without_seed`, 2026-11-14 물음 보드 seed (nopub)). 기본값은 참이라
    스크립트(`bootstrap_builtin_seed.py` · `benchmark_home.py`)는 그대로 시드를 만든다.
- `src/capa_simulation/scenario_registration.py` — BigDataQuery 원천을 리비전 1 시나리오로 저장하는 **세션 없는** 등록 길이다.
  - 화면 등록(`components/bigdataquery_registration.py`)과 자동 갱신이 같은 `save_bigdataquery_scenario` 를 불러 원천
    메타·메모(상세 조회기간 · CS 가 비어 뺀 행 수 · 대당 Capa 멈춤의 꼴과 개수)가 같은 꼴로 남는다. 세션 활성화와 프리셋은
    부르는 쪽 몫이다.
  - 리비전 1 메모 끝 조각 차례는 CUSTOM 원천 대조 · 업무 키 충돌 · CS 빈 행 · 부대공정 판 · 대당 Capa 멈춤(늘 끝)이다. 앞
    둘은 `source_check_memo` 한 곳 — 「CUSTOM 원천 대조 — 종류 n · 행 수 다른 칸 m · 한쪽에만 있는 칸 k」(BigDataQuery 등록이면
    늘 — `CustomSourceCheck.memo`, CUSTOM 원천 끄개로 묻지 않은 등록은 같은 자리에 「CUSTOM 원천 붙이지 않음 — 부품 구분 없음(-)」,
    CSV · 시드 · 가짜 공급자는 None 이라 없음) · 「업무 키 충돌 n그룹(키밖 a · 그 밖 b)」(있을
    때만 — `core_data_pipeline.reference_conflict_memo`)이고, 자동 갱신이 같은 함수로 실행 기록 사유 · 리비전 2 · 공식버전 메모에
    잇는다(`_RunLog.source_memo`).
  - 저장 **전에** 대당 Capa 를 한 번 돌려 보고(`check_registration_capacity`) 멈춰도 저장한다(2026-11-01 사용자 결정 —
    알리기만). 결과(`BigDataQueryRegistration.capacity`)로 화면은 저장 알림 뒤 경고(알림창 · Alarm 에만 — `popup_only`), 자동 갱신은 지정까지 가지 못한 회차 사유 끝(등록한 시나리오를 남겼다는 끝 글 앞 — 어느 갈래든 한 번, `_RunLog.fix_hint`. 푸는 길이 원천 다시 등록이면(`fixed_at_source`) 끝 글은 「…은 남겼습니다」 까지이고 「…손으로 지정하세요」 꼬리를 달지 않는다 — 검수 보드 sc-runner-word)에 무엇이
    멈췄고 어디서 푸는지(기준 정보 화면 그 표 → 다음 리비전, `RQ_MODULE`·표가 깨진 꼴은 원천 다시 등록 · 빈 경로 표(`RQ_UPEH`·
    `RQ_REQB`·`RQ_EQP_AVBL` — 계산 앞에서 `ROUTE_TABLES` 로 먼저 잡는다, 메모 꼴 `대당 Capa 계산 멈춤(빈 표 RQ_UPEH · …)`,
    2026-11-08 결정 U3)는 원천 다시 등록. 등록이 CS 가 비어 뺀 경로 행 수(`blank_cs_routes` = `BlankCsDrop.route_rows`)를 넘겨, 그
    수가 있으면 그 CS 를 채우라고, 없으면 경로 행을 넣으라고 가른다. 반대로 경로 행만 있는 원천의 빈 계획 표(`RQ_PKG_PLAN` —
    `PLAN_TABLES`, 필드 `empty_plan`)도 같은 꼴로 잡는다 — 대당 Capa 는 서고 HOME · 생산 계획 · 표준 목표가 멈추므로 글 · 메모 머리는
    `stop_scope` 「HOME · 생산 계획 · 표준 목표 계산」(메모 `HOME · 생산 계획 · 표준 목표 계산 멈춤(빈 표 RQ_PKG_PLAN)`), 푸는 길은 원천에 계획 행을 넣어
    다시 등록, 검수 보드 st-route-only)를 적는다.
  - 화면의 저장 결과 칸은 폼 맨 아래 `DB 조회 후 시나리오 저장` 단추 **바로 아래** 늘 서 있는 한 칸이다(탭 맨 위 칸은 스크롤한
    화면에서 보이지 않았다 — 2026-11-01 E2E). 저장 알림과 저장 뒤 경고(업무 키 충돌 `SC-04` · CUSTOM 원천 대조 `SC-05` · CUSTOM 원천 끄개 `SC-06` · CS 빈 행 · 대당 Capa 멈춤)는 알림창 · Alarm 으로만 가고
    (`popup_only` — 설계 규칙 UI-NTF-03 · AMB-05 (나)) 칸에는 저장하지 못한 까닭(거부 · 실패)이 선다. 칸에 글을 그린
    회차에만 칸 끝의 스크립트(`REVEAL_NOTICE_SCRIPT` — `st.html(unsafe_allow_javascript=True)`, 회차마다 다른 일회 표지)가 칸이
    화면 밖일 때만 본문을 옮긴다(`scrollIntoView({block: "nearest"})`).
  - 부대공정(BDQ 밖 공정 — 2026-11-13 · 11-14 보드 답으로 정한 설계 1단계)은 `load_active_extra_pack` 이 DB 의 활성 판을 판 내용
    표에서 다시 읽어(S3 를 읽지 않는다) 등록 이음매(`core_data_pipeline.fetch_registration_dataset`)에 넘기고,
    `save_bigdataquery_scenario(extra=…)` 가 리비전 메모 조각(「부대공정 판 n · k 합침 · m 뺌」)과 데이터셋 출처 줄
    (`provenance_records` → `create_scenario(extra_process=…)`)을 남긴다. 판이 없거나 꺼졌으면 전과 같다.
- `src/capa_simulation/extra_process_intake.py` — 부대공정 판 들이기의 화면 밖 몸통(세션 없음). 가져오기 원천은 **꽂는 자리 하나**
  (`ExtraProcessSource` · `install_source` — 받기 `fetch()` · 머리 보기 `head()`)이고 C-DEP 진입 파일만 S3 Drive 원천
  (`extra_process_drive`)을 꽂는다 — 개발 · 사내 PC · WebIDE(`app.py`)에는 입력 길이 없어 Admin 「부대공정」 의 가져오기 단추가
  서지 않는다. 받을 것이 아직 없음은 `SourceNotReady`(낱말 · 안내 — 실패 아님)다. 받은 파일 판정(`stage_pack` — 접수
  검증 + 판 번호 판정 + 지금 판 · 앞 판과의 차이 `changes`, 받은 때의 판 이력 마지막 차례를 든다) · 미리보기 시험 계산
  (`preview_pack` — 지금 시나리오 표에 이미 든 부대공정을 걷고 합쳐 본다, 저장 안 함, 합친 표의 전체 기간 계산은 한 번 돌려 월별
  확보율 · 경로 수 · 따라가는 공정에서 이어받은 대당 Capa 결손 줄 R-02 가 함께 쓴다 — 부하 예외 선언은 부르는 화면이 읽은 판
  `route_exceptions` 를 받는다) · C-DEP 판정(`production_place` — 동기화
  `managed` + 기동 때 읽은 S3 접속 정보). **내보내기도 꽂는 자리 하나다**(`ExtraProcessSink` — HEAD · PUT, `install_sink`) — 놓는
  꼴이 낱장 여섯으로 바뀐 뒤(2026-11-20) 여섯을 덮을지 정하지 않아 **앱 코드는 꽂지 않고 시험만 꽂는다**. 쓰기(`write_back`)는 PUT 바로 앞 HEAD 의 ETag 를 기준
  ETag(`ExtraProcessState.baseline`)와 견줘 같거나 파일이 없을 때만 덮고, 다르면 덮지 않는다(적용하지 않은 사람 파일 — G5). 상태 줄
  낱말(`head_word` — 없음 · 같음 · 옛 판 · 마지막으로 가져온 파일의 낱말 · 새 파일)과 「새 판」 쓰기 대기 판정(`needs_write`) ·
  사람이 놓은 같은 새 판 판정(`placed_matches`)도 둔다.
- `src/capa_simulation/extra_process_drive.py` — 부대공정 S3 Drive 가져오기 원천(설계 A6 — 2026-11-20 보드 결정-2 (가) 「낱장 CSV
  여섯」). 버킷 `extra_process/` 아래 정해진 이름 여섯(`00_info.csv` ~ `05_rate_vital.csv`)만 GET · HEAD 로 본다 — 목록(LIST)은 앱
  열쇠로 재지 않은 능력이라 쓰지 않아 다른 이름 · 남는 파일은 보지 않는다(그 장은 「파일 없음」 거절). 받기는 여섯을 받고 머리를
  한 번 더 본 뒤 `bundle_pack_files` 로 판 한 벌(ZIP — 앱 안의 판 꼴, `pack_to_zip` 과 같은 묶개라 내려받은 양식을 그대로 놓으면
  같은 sha)로 넘긴다. 여섯 다 없음 · 놓는 중(다시 본 ETag 가 다름 또는 가장 늦게 놓인 장이 저장소 `Date` 로 `SETTLE_SECONDS`
  120초 안)은 `SourceNotReady`, 일부 빠짐은 접수 검증의 「파일 없음」, 일부만 바뀜은 판 번호 규칙이 가른다. 상한은 여섯 장 합
  8 MiB, 마감은 받기 · 머리 보기마다 하나이고 첫 실패에서 멈춘다. ETag 는 여섯을 묶은 값(`set_etag` — 모르는 ETag 가 있으면 기준
  없음)이다. 닿을 곳은 C-DEP 꼴(`managed` + `runtime.config().access_s3`)에서만 있다. `capa_server.py` 가 런타임 전에
  `install_drive_source` 로 꽂는다(Streamlit 없음 — `tests/test_server_pre_runtime_imports.py`). 시험
  `tests/test_extra_process_drive.py`(가짜 S3).
- `src/capa_simulation/auto_official_update_runner.py` — 공식버전 자동 갱신 한 회차를 세션 없이 돌리고 실행 기록에 남긴다.
  - 조회·시계·발행 뒤 정리는 주입받는다. 위험하면 발행하지 않고(`PUBLISH_SKIPPED` — 계산 실패·판정 가능 공정 0·발행 검사
    실패·회차 도중 최신 공식버전이 바뀜) 만든 시나리오는 남긴다. 한 번 받은 코드(`received_codes`)는 다시 받지 않는다.
    원천 CSV 로만 받은 코드는 「등록됨」 으로 세지 않는다(`source_bridge.settled_source_codes` — 7장 「원천은 두 길」).
  - 이어받은 수동 off 와 HOME 표지(`auto_off_marks`)는 같은 근거(`_auto_exclusions` — 조상, 복제본은 복제 전 자동
    리비전 2)를 본다. 같은 프로세스의 겹친 회차는 기다리지 않고 돌아간다(`_RUN_LOCK`).
  - 부하 예외 선언은 「judge」 단계 앞에서 저장소(`load_route_load_exceptions` — 캐시 래퍼 없이)로 한 번 읽어 판정과 발행 검사가 같은
    판으로 셈한다. 선언이 있으면 실행 기록 사유의 발행 줄 쪽 끝과 리비전 2 · 공식버전 메모에 「부하 예외 판 n」(이름 없음 —
    `_route_exception_memo`)을 붙여 공식 숫자가 어느 판으로 났는지 되짚는다. 선언이 없으면 조각이 없다.
  - 사유의 발행 줄 쪽 끝 · 리비전 2 · 공식버전 메모의 조각 차례는 원천 조각(`_RunLog.source_memo` — CUSTOM 원천 대조 · 업무 키
    충돌, `scenario_registration.source_check_memo`) · CS 빈 행 · 부대공정 판 · 부하 예외 판이다. 소요대수 밖 수요 경고는 그 뒤
    `_WARNING_SEPARATOR` 로 잇고 `split_published_reason` 이 경고 머리로만 가른다 — 대조 조각 안의 「—」 는 가르지 않는다.
    CUSTOM 원천 끄개(`CAPA_BDQ_CUSTOM_SOURCE=off` — 7장)로 받은 회차는 원천 조각이 「CUSTOM 원천 붙이지 않음 — 부품 구분 없음(-)」 이고
    회차는 그대로 공식으로 올린다(2026-11-24 사용자 답 Q2 (가) — 회차 코드는 끄개를 모른다, 시험
    `test_a_switched_off_run_registers_blank_parts_and_carries_the_switch_memo`).
  - 회차를 멈춘 예외는 traceback 과 함께 로그에 남기되(`_log_failure_trace`), BigDataQuery 조회 실패(`BigDataQueryCallError`)면 예외
    사슬을 따라가지 않는다 — 감싼 패키지 원문(`__cause__`)에는 요청자 계정 · CUSTOM 원천 표 이름이 가리지 않은 채 든다. 그 실패를
    실행 기록에 쓰지 못한 줄도 문맥이 그 조회 실패라 같이 끊는다(`test_a_custom_query_failure_keeps_the_table_name_out_of_the_log`).
- `src/capa_simulation/object_sync_worker.py` — 정본 버킷 동기화 일꾼. 앱의 둘째이자 마지막 배경 스레드다(5장 4·9장).
  차례는 `object_sync_engine.py` 다. `capa_server.py` 가 세우고 `managed` + 부트 기록이 있을 때만 선다. 감사 기록기가 켜진
  서버면 감사 할 일(`audit/shipper.py` 의 `AuditTasks` — 비우기 10초 · 올리기 5분 또는 200줄 · 일별 묶음 · 미러)도 같은 고리가
  한다(새 스레드 없음). 감사 올리기는 DB 올리기보다 먼저고 DB 막힘과 상관없으며 그 실패는 감사 쪽이 삼킨다(DB 실패 수 ·
  `SY-02` 를 건드리지 않는다). 「지금 올리기」 는 감사부터 올린다(열린 시간 묶음을 앞당겨 닫고, DB 올리기 뒤 그 몫까지 —
  5장 40). 누름은 물러남 대기만 비우고 연속 실패 수는 성공 때만 0 이다 — 계속 실패하는 동안 누를 때마다 0 이면 배지가
  「누르면 저장 잃음」 에 닿지 못한다. 감사 할 일을 못 세우면 일꾼은 감사 없이 서고 `AD-12` 「올리기 없음」 이 선다.
- `src/capa_simulation/auto_update_scheduler.py` — 공식버전 자동 갱신을 매일 지정 시각에 돌리는 배경 스레드다(5장 4·9장).
  - 실행 줄 `CAPA_AUTO_OFFICIAL_UPDATE=1` 일 때만 서고, 지정 시각이 직전 확인과 지금 사이일 때만 돈다(`crossed_slot` —
    놓친 날은 따라잡지 않는다). 스레드 이름(`THREAD_NAME`)으로 하나를 지키고 `st.cache_resource` 는 쓰지 않는다.
  - 시험은 `tests/conftest.py` 가 실행 줄 허락을 늘 빼고(`scripts/benchmark_home.py` 도),
    `tests/test_auto_update_scheduler.py` 가 실행 문맥 없는 캐시 정리를 본다.
- `src/capa_simulation/services/builtin_seed.py`, `config/bootstrap_display_order.json` — GitHub 독립 실행용 합성 Core Data
  (`DEMO_*`)와 최소 표시순서를 CSV·BigDataQuery 와 같은 변환·저장 길로 낸다.
  - `data/input/RQ_DISPLAY_ORDER.csv` 가 있으면 첫 공용 표시순서 이관에 우선 쓴다(커밋·배포하지 않는다).
  - 표시순서 시드(로컬 CSV·내장 JSON)는 쓰일 때만 읽고 검사한다 — 공용 프로필이 없을 때(첫 이관)와 빈 시나리오
    저장소에 내장 시드를 만들 때다. 기동 길(`persistence/cache.py`)은 결과가 아니라 읽는 함수
    (`load_builtin_display_order`)를 넘기므로, 프로필이 있으면 쓰지 않는 시드가 검사에 걸려도 앱 기동을 막지 않는다
    (`tests/test_duckdb_repository.py` 의 `broken_seed` 시험).
- `src/capa_simulation/io/excel_reader.py` — 초기 이관·병행 검증 도구용 `RQ_*` Excel Table 읽기다(앱 런타임은 안 쓴다).
- `src/capa_simulation/io/core_data_source.py` — CSV·사내 조회가 공유하는 78컬럼 계약·정규화·해시·프로파일과
  `CoreDataProvider` 규약이다. 스크립트의 CSV 는 `read_core_data_csv` 로 읽는다 — 화면 입구(DB 등록 탭 「CSV 파일」 길)의 원천
  CSV 는 `io/source_csv.py` 가 같은 계약 객체로 읽는다(함수는 스크립트용 그대로).
  - `CoreDataBatch` 끝 칸 `custom_check` 는 CUSTOM 원천 표 대조 수(`custom_source_check.CustomSourceCheck`)이고 기본 None 이다
    (CSV · 시드 · 가짜 공급자). 그 모듈이 `core_data_derivation` → 이 모듈을 부르므로 import 는 `TYPE_CHECKING` 안이다.
- `src/capa_simulation/io/source_csv.py` — 원천 웹에서 받은 시나리오 CSV 읽기와 그 원천 묶음 공급자다. 같은 계약 객체(`load_core_data_contract`)를 쓰고
  `read_core_data_csv` 는 그대로 둔다(경로만 받고 곧바로 78열 검사라 남는 열 셋을 뺄 수 없다).
  - 요약 `summarize_source_csv` → `SourceCsvSummary`(수 KB — 표 · 해독한 글 없음): `csv` 모듈로 한 번 흘려 읽는다(`strict=True`
    — 닫히지 않은 따옴표도 깨진 줄). 인코딩은 첫 머리 줄 바이트로 UTF-8(BOM) → 계약 인코딩 차례로 정하고, 정한 뒤 안 풀리는
    바이트는 다시 읽지 않고 멈춘다. 머리는 날 머리를 공백 · 대소문자를 접어 맞추고(겹침 · 모르는 열 · 모자란 계약 열은 멈춤, 남는
    열 셋 `SOURCE_CSV_EXTRA_COLUMNS` · 값 없는 이름 없는 열은 읽지 않음), 줄마다 칸 수를 머리와 견주고(어긋난 줄 멈춤 — pandas 는
    그런 줄을 조용히 받는다), (시뮬레이션 ID, PLAN ID) 를 앞뒤 공백을 뗀 값으로 센다. 감싼 글 읽개는 늘 `detach` 한다(올린 파일이
    닫히지 않게).
  - 행 `read_source_csv_rows`: 고른 코드 행만 계약 78열 차례로(정규화 전) — 글자 열 `string`, 결측은 빈칸만, 숫자 `round_trip`,
    `header=0, names=` · `index_col=False`. 행 수가 요약과 다르면 멈춘다. 멈춤은 모두 `SourceCsvError`(`ValueError`) 한 글이다.
    숫자 칸 꼴은 pandas 가 파일 전체로 정하므로, 다른 코드 행의 글자 탓에 글자로 읽힌 숫자 계약 칸은 고른 행만 글자마다 `float`
    로 되돌린다(`_restore_number_columns` — 수 글자가 아닌 값이 하나라도 있으면 그대로 두어 정규화가 멈춘다).
  - 공급자 `SourceCsvCoreDataProvider`(`CoreDataProvider` 규약): `fetch` 가 코드(앞뒤 공백 뗌 · 어댑터의 `is_valid_simulation_code`)
    → 파일 다시 흘려 읽기(요약과 다르면 「올린 파일이 바뀌었습니다」) → 고른 코드 행 → 숫자 글자 칸 맞춤 → 설비대수변화관리 빈 글자
    (DB 조회문 상수와 같음) → CUSTOM 붙이기(`custom_rows_of` 답 · `FILE_WORDS` — 둘째 표와 같은 판정 · 정규화) → 원천 보정
    (어댑터 `apply_source_corrections`) 차례로 DB 등록과 같은 `CoreDataBatch` 를 낸다. `custom_check` 는 None(대조 없음 — 끄개의
    「붙이지 않음」 아님)이고 CUSTOM 값 종류 수는 `custom_kinds` 로 남긴다(화면이 메모를 짓는다). CUSTOM 원천 표 · 끄개 · 조회 SQL ·
    패키지 판정은 부르지 않는다.
  - 숫자 글자 칸 맞춤 `align_number_text_columns`: `SOURCE_CSV_NUMBER_TEXT_COLUMNS`(DB 조회가 숫자로 넘길 수 있는 계약 글자 칸
    일곱) 가운데 값이 모두 숫자 글자인 칸은 실수 칸으로 넘겨 정규화가 DB 길과 같은 글자(정수꼴 `3` → `3.0`)를 짓는다. 앞자리 0 ·
    앞뒤 공백 · 글자가 하나라도 든 칸은 그대로다. DB 조회가 이 칸들을 글자로 넘긴다고 확인되면 묶음을 비운다(그때는 파일 글자
    그대로가 DB 와 같다 — 두 꼴 모두 `tests/test_source_csv.py` 의 두 길 같음 시험이 본다).
  - 원천 유형 `SOURCE_CSV_SOURCE_TYPE`(`CSV_CORE_DATA_UPLOAD`). 시험 견본은 `tests/source_csv_samples.py`(내장 합성 시드 값).
  - 견줌 스크립트 `scripts/inspect_source_csv.py`(사본 · 읽기만 · 값 없이 수만): 같은 길(요약 → 공급자 → 정규화)로 읽은 CSV 원천을
    DB 사본에 같은 코드로 받아 둔 DB 길 원천(파생 넷 · CSV 원천 밖, 가장 최근 적재)과 견준다 — 원천 행 · 접은 행, 저장 해시(원천 코드
    불변 검사의 값) 같음, 지금 파이프라인으로 다시 파생한 16표의 정확 · 오차 안(`rtol` 1e-12 · `atol` 0 — 행 차례는 숫자 아닌 칸이 앞
    열쇠), 오차 밖으로 값 묶음이 다른 계약 열, CUSTOM 을 빈 값 표지로 둔 16표(CUSTOM 둘째 표를 붙이기 전 DB 등록분은 CUSTOM 키 표가
    늘 갈린다). 운영 DB 자리는 `inspect_revision_calculations.py` 와 같은 판정으로 열기 전에 거절하고, 코드 · 파일 이름 · 예외 문구는
    찍지 않으며(멈춤은 단계와 예외 종류만) 끝에 코드마다 `전송용 요약:` 한 줄이다. 사내 권한 템플릿 deny 에 든다 — 사용자가 별도 창에서 친다.
- `src/capa_simulation/io/company_bigdataquery_adapter.py` — 사내 SQL·컬럼 매핑 전용 접속부로, 결과를 CSV 로 남기지 않고
  공통 파이프라인에 넘긴다(`bigdataquery` 지연 import, 0행·`공정`·`모듈수` 누락은 보정 전에 막는다).
  - 조회 창은 호출자의 `QueryWindow` 이고 포함/배타 변환은 `sql_bounds()` 한 곳이다. 상세 창은 사용자가 정하며(목록에서
    고르면 등록일 −7~+3일) 넓은 기본 창으로 조용히 떨어지지 않는다. 같은 코드 재수신은 원천 코드 불변 검사가 막는다.
  - CUSTOM 은 CUSTOM 원천 표에서 받는다(7장 — 표 이름은 환경변수 `CAPA_BDQ_CUSTOM_TABLE` · `BDQ_CUSTOM_TABLE_ENV` 로만, 저장소 ·
    ZIP 에 두지 않는다). `fetch` 차례는 코드 검증 → 본 조회문 짓기(미설정 SQL 검사) → 끄개 · 표 이름 판정(`custom_source_problem` — 끄개가
    켜졌을 때만 `custom_table_problem` 의 없음 · 꼴 틀림, 영문 · 숫자 · 밑줄 낱말 하나나 점으로 이은 둘, 값은 글에 싣지 않는다 — 끄개와
    표 이름은 한 번 읽은 값 `_custom_source_setting` 으로 판정과 갈래를 함께 고르고, 공급자가 따로 받은 `custom_table` 이 환경변수보다
    앞선다) → 패키지 → CUSTOM 원천 표 조회(`build_custom_query`
    · `CUSTOM_QUERY_TEMPLATE` — 기간 없이 코드 하나, 열 이름은 설계 초안이라 사내 확인 거리) · `check_custom_rows` → 본 조회 → 0행 ·
    칸 · 중복 검사 → 이름 바꾸기 → `attach_custom_values`(본 표 CUSTOM 칸만 Capa Code 로 덮는다 — 덮은 프레임이 원천 스냅샷) →
    원천 보정(`apply_source_corrections` — MPGA TEST 모듈수, 원천 묶음 뒤처리 한 곳)이고, 대조 수는 `CoreDataBatch.custom_check`
    로 간다. 본 조회문 `QUERY_TEMPLATE` 은 글자 그대로 두고(지문 시험) 그
    상수 CUSTOM 칸을 붙이기가 덮는다. CUSTOM 원천 표 조회 실패는 같은 길(`call_get_data`)의 `BigDataQueryCallError` 에 「CUSTOM 원천
    표(CAPA_BDQ_CUSTOM_TABLE) 조회에서 멈췄습니다」 머리를 단 사본(`retold` — 갈래 · 낱말 · 종류 이름은 다시 가르지 않음)이고, SQL
    갈래면 값 · 조회 권한을 보라고 덧붙인다. 원문(`_original_text`)은 요청자 계정과 함께 표 이름(값 전체 · 점 뒤 끝 조각, 3글자
    이상, 대소문자 무시)을 `CUSTOM_TABLE_MASK` 로 한 번에 가린다(`_texts_to_hide` · `_hide_texts`) — 자동 갱신 실행 기록 사유가
    원문을 그대로 남긴다. 시험은 `tests/conftest.py` autouse 가 합성 값 `demo_schema.demo_custom` 을 넣고 끄개를 지우며, 「없음」 갈래와
    끄개를 내린 갈래는 그 시험이 직접 바꾼다. 같은 판정(`custom_source_problem`)을 DB 등록 탭의 저장 단추 잠금 · `AD-04` 와 Admin
    「서버 시작 점검」 의 「CUSTOM 원천 표」 줄(`AD-01`)이 읽는다 — 그 줄 · 제목 판정 · `AD-01` 은 `tests/test_custom_table_setting.py`,
    잠금 · `AD-04` 는 `tests/test_bigdataquery_registration.py` 가 본다.
  - CUSTOM 원천 끄개(`BDQ_CUSTOM_SOURCE_ENV` = `CAPA_BDQ_CUSTOM_SOURCE`, 2026-11-24 정식판 마감 1번 — 7장)는 값이 `off`(앞뒤 공백 ·
    대소문자 무시)일 때만 끈다(`custom_source_on` — 비었거나 `of` · `false` 같은 다른 값은 켬, 부를 때마다 읽는다 — 메모리 공유 스위치와
    같은 꼴). 끄면 표 이름을 판정하지 않고(`custom_source_problem` 이 None — 변수가 없거나 꼴이 틀려도) 패키지 뒤 CUSTOM 원천 표를 묻지
    않으며, 본 조회 · 0행 · 칸 · 중복 검사 · 이름 바꾸기 뒤 CUSTOM 칸을 모두 빈 값 표지로 덮는다(`custom_source_check.blank_custom_values` —
    조회문 상수 그대로가 아니다). 대조는 「붙이지 않음」(`CustomSourceCheck.switched_off`)이라 메모 조각 · 등록 알림 `SC-06` 이 늘
    선다. 판정 자리는 `build_query` 뒤라 「SQL 미설정」 글이 먼저다. 켬 길 판정 · 글은 끄개 전과 같다. 시험은
    `tests/test_company_bigdataquery_adapter.py` 의 `test_only_off_turns_the_custom_source_off` · `test_the_switch_off_*` ·
    `test_the_switch_is_judged_after_the_unconfigured_sql_check`.
  - `getData` 가 낸 패키지 예외는 `call_get_data` 가 `BigDataQueryCallError`(`RuntimeError`)로 감싼다 — 패키지의 `Error`
    같은 종류는 화면의 `BOOTSTRAP_ERRORS` 밖이라 그대로 두면 목록·저장 화면이 traceback 으로 멈춘다. 감싼 예외는 갈래
    (`classify_query_failure` — 토큰·서버 혼잡·시간 초과·연결·SQL·그 밖, 사슬의 종류 이름과 문구 낱말로 가른 추정)와 다시 할 길을 말하고
    원문(300자까지)과 원래 예외(`__cause__`)를 남긴다. 갈래 · 근거 낱말 · 토큰 안내(`is_login_token_failure`) · 요청자 계정 안내 판정은
    고리 글을 만들다 깨지면(패키지 예외의 `__str__`) 빈 글로 보고 종류 이름 · 다른 고리의 글로 가르고, 원문 한 줄(조회 · 패키지
    불러오기 실패)은 그때 「(문구 없음)」 이다(`_link_text`, 시험 `tests/test_bdq_failure_text.py`). 토큰은 맨 앞에 보고 분명한 근거만 쓴다 — 토큰 예외 종류 이름
    (`_TOKEN_FAILURE_TYPE_WORDS` — `TokenNotFound…` · 만료를 단 이름, 문법 낱말보다 먼저)이나 분명한 토큰 낱말(`_TOKEN_FAILURE_WORDS`
    — `invalid token` · `token expired` 류와 패키지의 「no bigdataquery token」, 종류 이름 `InvalidToken…` 도 이쪽)이고, 이쪽은 문법
    낱말이 함께 있으면 SQL 로 둔다(구문 오류의 「unexpected token」). 종류 이름의 `token` 하나 · 토큰 자리(`.credential`)만으로는
    갈래가 서지 않는다. 사슬에 `ConnectionError` 가 있어도 「연결」(네트워크 · 다시)이 아니라 「다시 해도 같으니 …」 이고
    8-5 도 다시 묻지 않는다. 그 끝 절은 자리마다다 — 서버 시작 기록(`start_check_hint` 가 단락을 내는 C-DEP)이 있으면 「개발자에게」,
    없으면(WebIDE · 사내 PC) 「BigDataQuery 로그인을 다시 하세요」(`token_advice` — 2026-11-12 남은 물음 보드 ⑤-4 (나)). 시작 점검 토큰 줄 안내(`is_login_token_failure`)는 갈래 「토큰」 이면 늘 붙고 종류 이름의 `token` ·
    `.credential` 문구에도 붙는다(덧붙일 뿐이라 넓다 — 2026-11-12 리뷰 202611111500 보드 N7). 사외로 가는 스크립트(`inspect_real_data_checks.py` 8-5)는 갈래와
    종류 이름(`type_names`), 그리고 갈래를 정한 목록 낱말(`query_failure_clue` · `BigDataQueryCallError.clue` — 문구 원문이
    아니다)만 찍는다. 까닭을 말하지 않는 낱말(`sql` 등)은 갈래가 그 밖이고 단서로만 붙으며, 그 밖과 넓은 SQL 낱말(`not found` ·
    `does not exist` 등 — 문법 낱말 `_QUERY_TEXT_WORDS` 를 뺀 것)의 실패가 `LONG_FAILURE_SECONDS`(5분)를 넘겨 나면
    `call_get_data` 가 잰 시간으로 시간 초과로 올린다 — 조회문 거절은 초 단위로 돌아오고, 긴 조회 중 다시 적재한 표는 그 낱말로
    실패할 수 있으며, 앱은 조회에 시간 제한을 걸지 않는다(취소할 길이 없고 새 배경 스레드를 세우지 않는다). 같은 조회문이 도는
    동안의 부름은 새로 묻지 않고 그 결과를 같이 기다린다 — 조회 중에 단추를 다시 누르면 Streamlit 이 앞 회차를 멈추지 못한 채 새
    회차를 세워 서버에 같은 조회가 겹쳐 쌓였다(`call_get_data` 의 `_IN_FLIGHT`, 캐시가 아니다). 합류는 조회 시작부터
    `IN_FLIGHT_JOIN_SECONDS`(20분 — 잰 가장 긴 실패 907초를 넘긴 자리)까지이고, 그 뒤의 첫 부름이 자리를 넘겨받아 새로 묻는다 —
    돌아오지 않는 `getData` 하나가 프로세스의 그 조회문 부름을 재시작까지 멈춰 세우지 않게 한다.
  - 「서버 혼잡」(`QUERY_FAILURE_BUSY`)은 DB 서버 대기열이 가득 차 조회를 받지 않은 것이다(Impala `queue full` — `pyodbc.Error`
    HY000, 2026-11-16 사내 확인 · D8). 토큰 다음, 다른 갈래보다 먼저 본다(`_BUSY_PATTERN` — `queue full` · `queue is full` 따위,
    대소문자 무시, 근거 낱말 `BUSY_CLUE`) — 같은 문구의 「Rejected query」 · `SQL…` 함수 이름이 그 밖으로 가르지 않게. 안내는
    「잠시 뒤 같은 조회를 다시」 뿐이고 앱은 스스로 다시 묻지 않는다. 오래 기다린 끝이어도 시간 초과로 올리지 않는다.
  - 요청자 계정(`resolve_user_name`)은 계정 하나의 원천(`bdq_login_store.effective_account` — C-DEP 자동 로그인에 저장된
    계정이 있으면 그 ID, Admin 폼으로 바뀌면 곧바로 새 ID, 없으면 `CAPA_BDQ_USER_NAME`)이고 저장 객체 읽기가 깨지면 환경변수
    계정으로 물러선다. `getData` 는 `bdq_login.run_with_relogin` 안에서 부른다(`_get_data_once`) — 저장된 계정이 있고 멈춤이
    아니며 토큰 파일 없음(`bdq_login.RELOGIN_EXCEPTIONS` — `TokenNotFoundException`)이나 만료 · 무효 토큰(사슬 고리의 글에
    `bdq_login.RELOGIN_MESSAGES` 문구 「You have invalid token」 — 응답 코드는 보지 않고(실측은 400), 바깥 `ConnectionError` 를 연결로
    먼저 가르지 않는다)으로 실패하면 다시 로그인해 같은 조회를 한 번 다시 한다(누가 이미 다시 로그인했으면 로그인 없이). 사슬은
    `bdq_login.failure_chain` 하나로 갈래(`_failure_chain`)와 같다 — 원인이 있으면 원인, 없으면 문맥을 따라 5고리까지(traceback 차례),
    둘째 고리부터 앱이 만든 예외(종류 · 상위 종류가 `capa_simulation` 모듈 — `BigDataQueryCallError` · 모듈 창구 `BigDataQueryError`)
    앞에서 그 고리의 글도 보지 않고 멈춘다(호출자가 앞 실패를 처리하는 `except` 안에서 다시 조회해도 앞 토큰 실패가 새 실패의 근거가
    되지 않게). 다시 한 조회가 토큰과 상관없는 실패(SQL · 연결 · 시간 초과)면 그 갈래로 올라가고 멈추지 않는다. 다시 한 조회도 토큰 오류면 멈춤을
    저장하고, 로그인 거절도 멈춤 저장, 닿지 못함 · 패키지 없음은 멈추지 않고 원래 실패다(D3 · D4 · D6). 그 문구 밖의 토큰 낱말만
    맞은 갈래는 다시 로그인하지 않는다(`AD-10` 만 — 2026-11-16 사용자 결정이 D9 「종류에서만」 을 문구 기준으로 바꿈). 갈래 판정도 그
    문구를 문법 낱말보다 먼저 봐 다시 로그인한 실패가 「토큰」 이다. 감싸기 · 토큰 표지 · 실패 초는 다시 로그인을 거친 마지막 부름에
    한 번이다. 저장된
    계정이 없으면(키 없음 · `managed` 아님 · 객체 없음) 지금과 같다 — 하위 프로세스 0 · 키가 없으면 S3 요청 0. 같은 조회문 합류
    (`_IN_FLIGHT`) 안이라 겹친 부름은 다시 로그인을 함께 기다린다. 모듈 창구 `module_api.query_bigdataquery` 도 같은 길이다.
    Streamlit 을 부르지 않는다(공식버전 자동 갱신 스레드 — `tests/test_company_bigdataquery_adapter.py` 가 별도 프로세스의 맨
    스레드로 본다).
  - import 실패도 `load_bigdataquery_module` 이 모두 `RuntimeError` 로 올린다. 「패키지가 없습니다」는 패키지 자체가 없을
    때만이고(점검 스크립트가 이 문구로 가른다), 깔렸는데 불러오다 깨지면(DLL·numpy 판·패키지가 쓰는 모듈 없음) 「불러오지
    못했습니다」와 빠진 모듈 이름 또는 원문을 단다.
  - C-DEP CD 시작 점검 결과 파일이 있으면 「패키지가 없습니다」·로그인 토큰 오류(`is_login_token_failure`)·`user_name`
    안내 **뒤에** 그 단계의 결과 한 단락과 넣을 환경변수를 덧붙인다(첫 문장·갈래·종류 이름은 그대로, 파일이 없으면 지금
    문구 그대로). `BDQ_USER_NAME_ENV` 는 `io/container_start_report.py` 가 이름을 갖고 여기서 다시 내보낸다.
  - 누구나 볼 꼴 `public_failure_text(message)` — 이 어댑터가 낸 실패 글을 개발자가 아닌 등급에게 줄인 꼴이고, 어댑터가 낸 글이 아니면
    None 이다. 머리 글 상수(`FAILED_QUERY_LEAD` · `ORIGINAL_LEAD` · `ORIGINAL_TO_DEVELOPER` · `CUSTOM_QUERY_LEAD` · `USER_NAME_LEAD` ·
    `PACKAGE_MISSING_LEAD` · `PACKAGE_LOAD_LEAD` · `CUSTOM_TABLE_MISSING` · `CUSTOM_TABLE_MALFORMED`)는 글을 지을 때와 알아볼 때 같이 쓴다(문구만
    고친 배포가 판정을 깨지 않게). 머리는 글 어디에 있어도 알아보고(앞머리는 남김) 가장 앞 머리 하나로 고른다 — 조회 실패는 첫 단락
    「<머리>(<갈래>). <할 일>」 만(원문 · 서버 시작 점검 단락을 걷고 「아래 원문을 개발자에게」 → 「개발자에게」), CUSTOM 원천 표 조회 실패는
    머리의 변수 이름 · SQL 갈래 덧말을 걷은 같은 꼴, 준비 실패(패키지 없음 · 불러오기 실패 · 요청자 계정 없음 · CUSTOM 원천 표 변수 없음 ·
    꼴 틀림)는 `PUBLIC_SETUP_TEXT` 한 문장, 데이터 멈춤 글 · 끄개 메모는 None 이다. 어댑터의 글 자체와 로그(`_log_failure` — 원문 없음)는
    그대로다 — 자동 갱신 스레드 · 점검 스크립트 · 모듈 창구가 같은 글을 받는다. 부르는 곳은 `admin_view.diagnostic_message` 하나다(공식버전
    자동 갱신 탭 「마지막 확인」 · 실행 기록 「사유」 칸 · DB 등록 조회 · 저장 곁 오류). Streamlit 을 부르지 않는다. 시험 `tests/test_company_bigdataquery_adapter.py` 의
    `test_the_public_failure_text_keeps_the_kind_and_what_to_do_and_drops_the_original` · `test_setup_failures_read_as_one_tell_the_developer_sentence_for_others` ·
    `test_a_custom_query_failure_reads_without_the_variable_for_others` · `test_with_the_custom_switch_off_a_query_failure_reads_the_plain_public_form` ·
    `test_a_text_the_adapter_did_not_write_has_no_public_form`, 등급마다는 `tests/test_grade_ui_core.py`.
- `src/capa_simulation/io/container_start_report.py` — C-DEP CD 시작 스크립트(`scripts/container_start.py`)와 앱이 함께
  쓰는 환경변수 이름 다섯(`CD_ENVIRONMENT` — 사내 패키지 저장소 주소 `CAPA_COMPANY_INDEX_URL` 을 더해. 사내 PC 도 넣는 이름이라
  CD 서버인지 가르는 `CD_ONLY_ENVIRONMENT` 에는 없다. 앱이 읽지 않는 옛 갱신 토큰 이름
  `CAPA_BDQ_REFRESH_TOKEN`(`RETIRED_BDQ_REFRESH_TOKEN_ENV`)은 표에 남아 있어도 앱 · 하위 프로세스에 넘기지 않고 가리도록
  `APP_WITHHELD_ENVIRONMENT` 에만 둔다. BigDataQuery 자동 로그인 키 `CAPA_BDQ_SECRET_KEY`(`BDQ_SECRET_KEY_ENV` — Fernet 키)는 세
  묶음 어디에도 없다 — 앱이 쓰므로 `APP_WITHHELD_ENVIRONMENT`(앱 환경에 있으면 「시작 스크립트가 안 돎」 표지)에 넣지 않고, 운영 앱은
  기동 때 빼므로 CD 서버를 가르는 `CD_ONLY_ENVIRONMENT` 에도(키를 넣고 `app.py` 로 띄운 자리에 「결과 없음」 안내가 붙지 않게), 넣지
  않은 서버가 늘 빈 값으로 적지 않게 `CD_ENVIRONMENT` 에도 넣지 않는다)·결과 파일(`settings.CONTAINER_START_REPORT_PATH` =
  `data/temp/container_start.json`) 꼴·화면 안내 문장(`step_hint`)이다. 결과 파일의 자동 로그인 칸 `bdq_login`(`LoginStart` ·
  `parse_login` — 갈래 `LOGIN_*`(`unconfirmed` 포함) · 까닭 코드 · 키 꼴 검사 · 남은 분 · 예외 종류 · S3 읽기 분류 · 객체에 결과를 못 씀 ·
  판정한 객체의 넣은 시각 · 하위 프로세스 진단 `child`(`ChildDiag` · `parse_child` — 종료 코드 · 시그널 · 걸린 초 · 닿은 단계 · 표준 오류
  마지막 예외 종류 · bigdataquery · getpass_asterisk 판 · 패키지를 불러온 길 `load`(알 때만) · 하위 프로세스 앞뒤 메모리 단서 `memory`(`ChildMemory` · `parse_memory` — cgroup 사용 ·
  한도(「max」 는 한도 없음) · OOM 종료 수 · 앱 RSS 앞뒤와 그 하위 자신의 최고 RSS 한 값, MiB · 수, 그 OOM 종료 수를 읽은 자리 낱말 `oom_src`(`OOM_SOURCES` —
  `events` · `events_local` · `oom_control`, 못 찾은 갈래 `OOM_UNKNOWN` — `no_file` · `no_line` · `unread`, 그 밖의 낱말은 비우고 모르면 빈 글 — 앞뒤 수를 모두 모르고
  갈래를 알면 화면 「oom_kill 모름(<까닭>)」 — 까닭은 파일 없음 · 줄 없음 · 못 읽음 가운데 하나), 한도 닿음 앞뒤 수 `hit_before` · `hit_after`(OOM 종료 수와 같은 범위, 하나라도 읽었을 때만 화면
  OOM 종료 수 바로 뒤 「한도 닿음 앞→뒤」 — 둘 다 모르면 줄이 지금 꼴), 칸 이름 `MEMORY_FIELDS` — 그 칸이 하나도 없는 옛
  파일은 `None` 이라 화면 글도 옛 꼴, 옛 하위 최고 앞뒤 칸 `LEGACY_MEMORY_FIELDS` 는 예외 없이 지나치고 옮기지 않는다) · 띄우기 바로 앞 프로세스 단서 `process`(`ProcessClues` ·
  `parse_process` — 부른 프로세스가 뜬 시간(소수 첫째 자리) · 스레드 · 열린 파일 · cgroup 프로세스 · 스레드 수 · 한도(「max」 는 그 cgroup 에 한도 없음) · 프로세스 수 · 좀비 수, 칸 이름 `PROCESS_FIELDS`
  `app_h` · `threads` · `fds` · `pids` · `pids_max` · `procs` · `zombies` — 그 칸이 하나도 없는 옛 파일 · 메모리 칸만 든 기록은 `None` 이라 화면 글이 「하위 최고 …」 로 끝나는 지금 꼴), 화면 글 `text` · 로그 글 `code` · 칸 `fields` 는 Admin 「BDQ 자동 로그인」 진단 줄 · 감사 상세와 한
  벌) · 비밀번호를 보내기 전에 끊긴 시작 시도가 몇 번째 다시 시도였나 `retry`(처음 시도 · 옛 파일은 0 — 「서버 시작 점검」 진단 줄 끝 「다시 시도 n/3」), 꼴이 어긋난 칸은 비운다, 계정 · 비밀번호 · 키 없음)과 그 표 줄 낱말(`login_step` — 꺼짐 · 계정 없음 · 정상(남은
  시간) · 멈춤(까닭) · 닿지 못함 · 못 함(예비 토큰) · 확인 못 함 · 결과 저장 못 함, `managed` 가 아닌 서버는 줄 없음 — 판정 `report_verdict`
  에 들되 키가 없어 꺼진 줄은 기능 상태라 세지 않는다 `LoginStart.counted`)도 여기다. 줄 이름 `BDQ_LOGIN_LABEL`(「BDQ 자동 로그인」)은 Admin Area
  의 계정 넣는 자리 이름이기도 하다 — 알림 글이 그 이름으로 가리킨다. 표준 라이브러리와 `settings` 만 읽는다 — 시작 스크립트가 앱 의존성보다 먼저 쓴다.
  - CD 는 시작 명령을 못 바꾸고 셸도 없어 이미지 `CMD` 가 그 스크립트다. 스크립트는 `bigdataquery` 를 하위 프로세스로
    불러 보고, 없으면 `requirements-company.txt` 의 판·인덱스로 pip 를 두 번 부른다(인덱스 줄은 사내 주소 대신
    `${CAPA_COMPANY_INDEX_URL}` 을 가리키고 pip · uv 와 같은 꼴로 펼친다 — 비면 설치를 건너뛰고 이름을 대며, `https://주소` 꼴이
    아니거나 계정·토큰이 들어 있으면 pip 를 부르지 않고 실패다. 값은 싣지 않는다) — 패키지 자신은 **사내 인덱스
    하나만** 보고 `--no-deps` 로(공개 미러를 추가 인덱스로 함께 보면 의존성 혼동에 열린다. 자격증명은 명령줄이 아니라
    그 pip 의 `PIP_INDEX_URL` 로, pip 설정 파일은 끈다), 의존성은 이미지 기본 인덱스로 앱 판 고정을 제약 삼아 채운다.
    토큰을 `/config/.credential/` 에 0600 으로 쓴 뒤(폴더는 이미지가 `$DSUSER` 몫으로 만들어 둔다 — 푼 내용이 비거나
    `MIN_TOKEN_BYTES` 보다 짧으면 쓰지 않고 「실패」 다) `os.execvpe` 로 옛
    `CMD` 와 같은 `streamlit run` 줄이 된다. 비밀값은 결과 파일·표준 출력·명령줄·하위 프로세스와 앱의 환경 어디에도
    남기지 않고(`tests/test_container_start.py`), 예상하지 못한 예외가 나도 「도중에 멈춤」 결과를 남기고 앱은 뜬다 — **`managed` 의 DB 받기만 예외다**
    (앱을 띄우는 길은 그 실행의 `boot-pull` 종료 코드 0 한 길, `tests/test_container_start_sync.py`). 틀린 모드 값은 받지 않고 앱이 뜨고(`SY-01`) 모드가 `managed` 인데 설정이 깨졌으면 머문다. 모드 칸이 비었거나 `local` 인데 버킷에 세대가 있으면 앱은 뜨되 결과 파일에 표지(`head_ignored`)를 남겨 `SY-05` 가 알린다(빈 버킷은 알리지 않는다 — 2026-11-12 리뷰 202611111500 보드 R2: 이 스크립트는 C-DEP 이미지에서만 돌아 그 자리의 `local` 은 이관 뒤 빠뜨린 `managed` 와 같다. 결과 파일이 없는 사내 PC · 개발 실행에는 표지가 없다). 그 자리에서 주소 · 버킷 · 프로필 CD 환경변수가 비어 버킷 목록을 못 보았으면 `SY-05` 를 가릴 수 없으니 빈 이름(`head_unchecked`)을 남겨 `SY-06` 이 알린다(이름만 — 2026-11-12 사내 S3 값 걷기 뒤 프로필에 기본값이 없다).
    시험은 `tests/conftest.py` 가 결과 파일 자리를 늘 없는 곳으로 돌리고 CD 전용 환경변수를 지운다.
  - 시작 차례는 ① 임시 응답(`scripts/container_stage.py` — 맨 앞에서 앱 포트를 잡아 상태 검사 셋 꼴에 답하고 고정 글 · 갈래 낱말 · 시각 · 횟수만 보인다. 꼴은 앱 밖 화면의 공통 틀(표지 「시작 중」 · 「다시 시도」 · 「점검 중」 · 단계 줄 · 지난 시간 · 다음 시도 n초 · 문의 줄 · 참고 줄 · 접힌 「개발자용 진단」)이고 Streamlit · `design.tokens` 를 불러오지 않아 두 팔레트를 상수로 두고 시험이 토큰과 맞댄다. 앱이 서기 전의 단순한 꼴(스크립트 · 단계 줄 · 값 줄)은 이 화면 몫이고, 표지 낱말 · 색 역할과 「개발자용 진단」 · 「문의」 · 「참고」 는 로그인 화면 틀의 표(`auth/page_frame.py` 의 `CHIP_WORDS` · `CHIP_ROLES` — 시작 중 `ALERT_ACTION` · 다시 시도 · 점검 중 `ALERT_CHECK`)를 불러 쓴다(그 모듈은 tokens 를 그릴 때만 부른다 — 2026-11-14 보드 decided 8). 결 값(`tone` — `start` · `retry` · `check`, `/_capa_stage` 셋째 줄)은 그대로 두고 `TONE_CHIPS` 가 틀의 표지 키로 잇는다. 글은 틀 · 띠처럼 띄어쓰기에서만 줄을 바꾸고 띄어쓰기 없는 긴 메일 · 주소만 접는다(본문 규칙의 `word-break: keep-all` · `overflow-wrap: anywhere` — 틀과 같은 두 선언을 시험이 맞댄다, 390 창에서 「시작하지 못했습니 / 다」 로 갈리던 것). 「다시 시도」 판의 제목 · 띠 글은 저장소에 닿지 못함 · 시간 초과일 때만 「저장소에 잠시 닿지 못했습니다」 · 「저장소에 잠시 닿지 못함 · 다시 시도 중」 이고, 원인을 모르는 실패(`other` 등)는 원인을 말하지 않는 「데이터를 잠시 받지 못했습니다」 · 「데이터를 잠시 받지 못함 · 다시 시도 중」 이다(`STORE_NOT_REACHED` — 표지 · 까닭 · 값 줄 · 10분 문의 줄은 같다, UI-DAT-11). 시작 스크립트는 단계 · 시도 · 실패만 알리고(`Stage.begin` · `step` · `attempt` · `fail`) 순수 `stage_view` 하나가 쪽과 `/_capa_stage`(제목 · 값 한 줄 · JSON 셋째 줄)를 함께 낸다. 앱이 뜨면 쪽은 처음 연 주소를 다시 읽는다 — POST 로 받은 쪽 · 콜백 경로만 바탕 주소, 거절 화면의 「접속 권한 신청」 POST 는 「다시 눌러 주세요」 한 줄(`NOTE_REGISTER_LOST` — 판을 갈아 끼워도 쪽 JS 가 옮겨 단다)과 함께 같은 주소를 GET 으로(`return_mode` · `returnWay` — 다시 읽으면 POST 를 다시 보낸다). 다시 받기가 도는 동안의 값 줄 「n번째 받는 중 · 지난 시간」 과 두 노트는 잠시 닿지 못함 · 이관 전 · 되돌리기 갈래(깨짐 · 갈라짐)가 함께 쓰되, 이관 전 · 되돌리기 갈래는 그 시도가 실제 내려받기로 넘어간 뒤만이다 — 받기는 하위 프로세스라 `boot-pull --download-mark` 가 멤버를 받기 직전 결과 파일 옆에 남기는 빈 표지(`container_boot_download`)로 알고, 시작 스크립트가 시도마다 지우며 임시 응답은 상태를 읽을 때 묻는다(`open_stage(download_seen=…)` — 넘어가면 판을 올린다). 받는 동안은 열어 둔 탭의 재시작 띠 글(`/_capa_stage` 셋째 줄 `band`)도 값 줄과 같은 「데이터 받는 중 · n번째 받기」 다(`_pull_band` — 첫 받기 · 다시 받기와 한 글). 받기로 넘어가기 전에 머무는 확인(처음 올리기 전 · 갈라짐 · 깨진 포인터)은 「확인하는 중」 · 「다시 확인하는 중」 이다 — 깨진 멤버(없음 · 크기 · 해시)는 받는 도중에 드러나 되돌리기 전의 300초 확인도 실제 받기라 그동안은 받는 값 줄이다. CI/CD 로 고치는 사람 갈래는 「다시 확인하는 중」 이다, 시험 `tests/test_container_stage.py` · `tests/test_container_start_sync.py`) ② `~/.aws` 프로필(`object_storage.render_profile_files`, 0600)
    ③ 점검 ④ 설치 · 자동 로그인 · 토큰(자동 로그인 — `managed` + 키 + 저장 객체가 `ok` 이거나 보내기 전 끊김으로만 막혔으면(대기 · `cut_limit` — 판정은 `start_login` 안의 `_cut_only_block`) 저장된 계정으로 한 번 로그인, `auto_login_step` ·
    `bdq_login.start_login`. 성공하면 `CAPA_BDQ_TOKEN` 을 쓰지 않고, 그 밖은 예비 토큰 길이며 파일 이름은 계정 하나의 원천(저장된 계정 →
    `CAPA_BDQ_USER_NAME`)이다. 풀린 계정 · 비밀번호 · 키는 가리개에 통째로 들고 키는 하위 프로세스에 넘기지 않는다, 예상하지 못한 예외는
    종류 이름만 남기고 예비 토큰 길 — 시험 `tests/test_container_start_login.py`, 키도 객체도 없는 서버의 잠든 불변식 포함) ⑤ `boot-pull` 되풀이(사람이 손대야 풀리는 갈래 `BOOT_HUMAN_KINDS` 아홉 — 설정 · aws 없음 · 거절 · 버킷 없음 · 디스크 · 깨짐 · 갈라짐 · 어긋남 · 판 새로움 — 은 300초마다 · 화면 표지 「점검 중」. 끝줄의 이름 · 수 칸(필요 · 남은 바이트 · 바뀐 DB · DB 판 · 코드 판 · 세대 — `BootOutcome` 의 더한 칸)은 `parse_boot_line` 이 닫힌 꼴로 다시 보고 임시 화면의 접힌 「개발자용 진단」 에 싣는다 — 모르는 수는 줄을 뺀다) ⑥ 소켓을 닫고 앱. 결과의 `sync` 칸은 더하기만 한 꼴이고(`parse_sync` — 옛 파일은 `None`), 앱 응답 시각은 `capa_server.py` 끝의 `note_app_ready` 가 결과 파일 옆에 남긴다.
    판 값 `AWS_CLI_VERSION` 은 `docker/Dockerfile-prod` 의 `awscli==` 한 줄과 시험이 맞댄다 — `requirements.txt` · 락 밖이고(`tests/test_requirements_export.py` 가 범위를 본다) 사외 개발 환경에 넣지 않는다. 실제 `aws` 왕복은 `CAPA_TEST_AWS_BIN` 이 있을 때 돈다.
- `src/capa_simulation/io/bdq_token.py` — BigDataQuery 로그인 토큰 파일(`/config/.credential/bigdataquery.token.<계정>`)의 자리 ·
  0600 원자적 쓰기 · 넣기 판정 · 만료 읽기 한 곳. 시작 스크립트(CD 환경변수 `CAPA_BDQ_TOKEN` → 파일)와 Admin 「토큰 넣기」
  (`components/bdq_token_admin.py`)가 같은 쓰기 길(`put_token`)을 쓴다(2026-11-12 사용자 결정 — 패키지는 조회마다 토큰을 다시 읽고,
  프로세스 환경변수 `BIGDATAQUERY_LOGIN_TOKEN` 이 파일보다 앞이라 그 key 가 있으면 넣기를 잠근다). 표준 라이브러리만 쓴다 — 시작
  스크립트가 앱 의존성보다 먼저 읽는다. 토큰 글 · 길이를 어떤 까닭 글에도 싣지 않고, 만료 시각만 (자리, inode, 수정 시각, 크기)
  열쇠로 기억한다(넣기는 쓴 뒤 기억을 비운다 — inode 를 믿을 수 없는 파일 체계). 만료는 JWT `exp` 하나만 읽고 그 밖은 「모름」 이다
  — 실제 토큰(WebIDE 실측 35바이트)의 꼴은 사내 확인 거리라 꼴을 짐작해 늘리지 않는다. 만료 읽기는 예외를 내지 않는다 — 깊은
  중첩 몸(`RecursionError`) · 어느 시각대로도 못 옮길 먼 시각(9999-12-31 같은 「만료 없음」 자리표시)도 「모름」 이다. C-DEP 컨테이너를 다시 띄우면 시작 스크립트가 CD 환경변수 값으로 파일을 다시 쓴다.
  파일 이름의 계정은 계정 하나의 원천(`account_name` → `bdq_login_store.peek_account` — 이 프로세스가 기억한 저장된 자동 로그인 계정이
  있으면 그 ID, 없으면 `CAPA_BDQ_USER_NAME`, S3 에 묻지 않음)이다 — 지금 토큰 줄 · 「토큰 넣기」 · 만료 알림이 같은 파일을 본다. 시험은
  `tests/conftest.py` 가 토큰 폴더를 없는 곳으로 돌리고 `BIGDATAQUERY_LOGIN_TOKEN` 을 지운다(`tests/test_bdq_token.py`).
- `src/capa_simulation/io/bdq_login_store.py` — BigDataQuery 자동 로그인 계정의 저장 객체 한 곳(버킷 `secrets/bdq_login.json` —
  세대 · 스냅샷 · `access/` · `modules/` 밖, 2026-11-16 사용자 결정 D1 · D2). 계정 · 비밀번호 JSON 을 CD 환경변수 `CAPA_BDQ_SECRET_KEY`
  (cryptography Fernet)로 감싼 `cipher` 와 메타(`entered_by` 넣은 개발자 앱 ID 앞 두 글자 · `entered_at` · `state` `ok`/`stopped` ·
  `stop_reason` · `stopped_at` · `misses` — 성공 없이 이어진 닿지 못함 · 확인 못 함의 수, 없으면 0 · `cuts` — 성공 · 넣기 없이 이어진 비밀번호를
  보내기 전 끊김의 수, 없으면 0 · `retry_after` — 그 끊김 뒤 다음 자동 시도를 기다리는 KST ISO 시각, 없으면 `null`)다. `managed` 이고 키 꼴이 맞을 때만
  선다(`availability` — 키가 없으면 S3 에 묻지 않는다). 키 없음 · 틀림 · 객체 없음 · 깨짐 · 판 다름 · 풀리지 않음은 모두 「저장된 계정
  없음」 이고 죽지도 멈추지도 않는다. 멈춤 표시(`mark_stopped`) · 자동 시도 앞의 시도 표시(`mark_attempting` — 멈춤 `attempting`, 기억은
  바꾸지 않음) · 시도 결과(`record_outcome` — 상태 · `misses` · `cuts` · `retry_after`)는 `cipher` 를 손대지 않고 메타만 고쳐 쓴다(그 사이 다른 계정으로
  바뀌었으면 쓰지 않음). 작은 객체 읽기 · 쓰기 · 지우기는 `io/s3_small` 이다. 앱 프로세스는 한 번 읽은 결과를 기억하고(`load_state` ·
  `current` — 저장 · 지우기 · 멈춤 · 결과 쓰기가 바꾼다, S3 를 못 읽었으면 60초 뒤 다시) 계정 원천 `effective_account` · S3 에 묻지
  않는 보기 `peek_state` · `peek_account` 를 낸다. 기억 잠금은 S3 를 기다리며 쥐지 않는다 — S3 읽기는 따로 한 번에 하나(그동안 다른
  부름은 옛 기억 · 처음 읽기만 기다림)이고 읽는 동안 기억이 바뀌었으면(세대 수) 읽은 결과를 버린다. 앱은 기동 때 키를 쥐고
  환경에서 뺀다(`take_secret_key` — 앱의 aws 하위 프로세스가 물려받지 않게). 풀린 값(`LoginSecret`) · `cipher` 는 repr 에 없고 풀기 ·
  읽기 실패는 까닭 코드만 돌려준다. 무거운 의존성(cryptography · 설정)은 함수 안에서 불러온다. 시험 `tests/test_bdq_login_store.py`.
- `src/capa_simulation/io/bdq_login.py` — BigDataQuery 자동 로그인 실행기. 로그인 한 번(`attempt_login`)은 `sys.executable` 하위
  프로세스(`io/bdq_login_child.py` — 표준 라이브러리만, `runpy`)이고 계정 · 비밀번호는 표준 입력으로만, 하위 환경은 비밀 이름 · `CAPA_S3_*` ·
  `AWS_*` 를 뺀 것이고 표준 입출력은 UTF-8 · `surrogateescape`(앱 자리의 로캘과 무관 — Windows cp949 파이프에서도 표지를 읽고, POSIX C 로캘 기본 오류 처리기와 같다), 출력은 버리고 표지 한 줄과 단계
  줄만 읽는다(표준 오류는 마지막 traceback 의 예외 종류 이름만 — `stderr_kind`, 계정 · 비밀번호를 품은 이름은 버린다). 하위 프로세스를 띄운
  시도마다 진단(`child_diag` → `LoginResult.diag` — 종료 코드 · 시그널 · 걸린 초 · 닿은 단계 · 예외 종류 · 판 · 패키지를 불러온 길 · 띄우기 바로
  앞과 끝난 바로 뒤의
  메모리 단서와 띄우기 바로 앞 한 번 읽은 프로세스 단서(`memory_probe.process_clues` — 뒤 값은 싣지 않는다), 도는 동안 `CHILD_POLL_SECONDS`(0.1초)마다 잰 그 하위 자신의 최고 RSS(`io/memory_probe` — 바깥 SIGKILL 을 가를 값. `Popen` 뒤
  `communicate` 를 짧은 제한으로 되풀이 — 새 스레드 없음, 시간 제한을 넘기면 끊고 남은 출력을 `CHILD_DRAIN_SECONDS` 까지 거둔다), 결과의 같음 판정 밖)을 남기고 로그 · Admin 진단 줄 · 감사 상세 · 시작 결과 칸
  `child` 가 읽는다. 표지 없음(`no_marker`)은 거절(멈춤)로 다루되 화면 낱말은 「로그인 확인
  못 함」(`UNCONFIRMED_REJECT_REASONS`)이다(시간 제한 60초, 새 세션으로 띄움 — 앞뒤 다이제스트는 이 프로세스의 「토큰 넣기」
  쓰기를 막은 채 잰다). 판정은 로그인 전후 토큰 파일 다이제스트가 바뀌었고 같은 하위 프로세스가 잰 남은 분이 7시간을 넘으면 성공(2026-11-16
  사용자 답), 바뀌었는데 남은 시간을 모르거나 7시간 이하면 `unconfirmed`(성공도 거절도 아님 — 폼은 저장하지 않고 자동 길은 멈추지 않되
  쉬는 시간 · 연속 수에 든다), 그 밖은 표지로 `rejected`(애매해도 — 계정 잠김 방지) · `unreached`(요청을 보내기 전 연결 단계의 양의 증거 —
  OS 연결 errno · 이름 풀기 · `urllib3` 연결 단계 종류 · 그것을 든 응답 없는 `requests` 연결 실패, 또는 하위 프로세스 시간 초과. 종류 이름만
  연결인 401 · 읽기 시간 초과 · 끊김은 거절) · `unavailable`(패키지 없음 · 시도 전 거절 · 비밀번호를 보내기 전 바깥 강제 종료 `import_killed` —
  표지 없이 시그널로 끝났고 받은 마지막 단계 줄이 `PRE_SEND_STAGES`(`import`)인 것만, `killed_before_send` — 하위 본문은 단계 줄 `login` 을
  내보내지 못하면 `login()` 에 들어가지 않는다). 자동 시도(시작 · 조회 중)는 로그인 **앞에** 객체를
  멈춤(`attempting`)으로 써 두고(쓰지 못하면 로그인하지 않음) 결과로 고쳐 쓴다 — 결과를 적지 못하거나 도중에 끊기면 다음 시작이 로그인하지
  않는다. 거절은 다시 시도하지 않고 프로세스 안에 멈추고 객체에 멈춤을 쓴다(D3). `unreached` · `unconfirmed` 는 멈추지 않되(D6 — 개발자
  알림 `AD-24`) 객체의 `misses` 를 올려 재시작을 건너 세고 성공 없이 `MISS_LIMIT`(3)번이면 멈춘다(까닭 `miss_limit`). `import_killed` 는
  멈추지 않고(2026-11-20 사용자 답 「쉬고 다시」) 객체의 `cuts` 를 올리고 다음 시도 시각 `retry_after`(`CUT_RETRY_SECONDS` 5 · 10 · 20분 —
  재시작을 건너 센다)를 적어 조회 중 자동 시도는 그 시각까지 쉬고(`SKIP_CUT_WAIT`), 시작 로그인(`start_login`)은 보내기 전 끊김으로만
  막혔으면(`_cut_only_block` — 대기 · `cut_limit`) 한 번 바로 한다 — 2026-11-21 사용자(컨테이너 시작마다 한 번 — 그 시도가 거절되면 그
  까닭의 멈춤이라 다음 시작부터 안 함, 거절 · 표지 없음 · `miss_limit` · `attempting` 멈춤은 그대로 안 함). 다시 시도
  `CUT_RETRY_LIMIT`(3)번도 끊기면 멈춘다(까닭 `cut_limit` — `AD-23`). 셈은 성공 · 폼 저장에만 비고 넘겨도 4 에 머문다 — 결과 적기
  `_settle` 은 성공이 아니고 그 시도로 멈추지 않았는데 셈이 상한을 넘었으면 `cut_limit` 멈춤으로 남긴다(「정상 + 셈 4」 를 쓰지 않음). 자동 시도 연속 3번
  (하위 프로세스를 띄운 수 — `import_killed` 는 빼고) · `unreached` 뒤 5분 쉼 · 프로세스 잠금 하나, 다시 로그인은 토큰 파일 없음(`bigdataquery.exceptions` 의
  종류 — `RELOGIN_EXCEPTIONS`)과 만료 · 무효 토큰(사슬 `failure_chain` 의 고리 글에 `RELOGIN_MESSAGES` 문구 「You have invalid token」 —
  `casefold` 로 견주고 응답 코드는 보지 않으며 판정에만 쓴다)에서만이다(`is_relogin_error` · `run_with_relogin` — 어댑터 `_get_data_once` 가 `getData` 를
  감싼다). 다시 로그인 뒤 재조회도 토큰 오류일 때의 멈춤은 그 잠금 아래에서 지금 기억한 한 벌이 그 로그인의 한 벌일 때만 쓴다. 폼 제출(`login_from_form` — 실패면
  저장하지 않음, D5) · 지우기(`forget_login`) · 시작(`start_login` — 시작 스크립트)이 같은 잠금이다. 앱 기동 한 번(`start_in_app` —
  `capa_server.py`)은 키를 쥐고 빼고 저장 객체를 읽어 두며, 이번 시작이 거절을 보고도 멈춤 표시를 쓰지 못했거나 로그인 단계가 예상하지
  못하게 멈췄으면 그 한 벌(결과 칸의 넣은 시각 `entered_at` 이 같은 것)을 프로세스에서 멈춘다(시작 스크립트의 프로세스 안 멈춤은 앱으로
  바뀌며 사라진다 — 거절은 표시를 다시 써 본다). 시작이 멈추지 않은 채 서지 못했으면 그 갈래를 이어받는다(`AD-24`). 화면 회차의 상태는
  S3 에 묻지 않는 `current_view`(`off` · `none` · `ok` · `stopped` 와 서지 못한 갈래 `trouble` — 기억이 없으면 이번 시작 기록, 거절 ·
  멈춤 · `error` 는 멈춤)다. Streamlit 을 부르지 않는다 — 공식버전 자동 갱신 스레드도 어댑터를 지난다. 결과 · 로그에 계정 · 비밀번호 ·
  예외 문구 · 하위 출력이 없다. 시험 `tests/test_bdq_login.py`(가짜 패키지 `tests/fixtures/bdq_fake/` 를 진짜 하위 프로세스로 띄워
  `login()` 이 불린 수를 센다) · `tests/test_container_start_login.py`(앱 기동).
- `src/capa_simulation/io/bdq_login_child.py` — 자동 로그인 하위 프로세스 본문(표준 라이브러리만). 표준 입력 첫 줄이 계정이고 나머지는
  패키지 `login()` 이 읽는다(계정 `input()` · 비밀번호 `getpass` 폴백). 로그인 뒤 `getTokenTime` 의 나뉜 남은 시간(`remaining_days` 두
  철자 · `remaining_hours` · `remaining_minutes`)을 분으로 합쳐 표지 한 줄(`capa-bdq-login stage=… error=<모듈.이름> net=… minutes=…`)만
  찍는다 — 예외 문구 · 패키지 출력은 싣지 않는다. 표지와 따로 패키지 불러오기 · `login()` · `getTokenTime` 에 들어가기 바로 앞에 단계 줄
  (`capa-bdq-login-step stage=… bigdataquery=<판> getpass_asterisk=<판> load=<light|full>` — 판은 불러온 모듈의 `__version__`, 아니면 설치 정보, 낯선 꼴은 `?`)을
  곧바로 내보낸다 — 표지 없이 끝나도 부르는 쪽이 어디까지 갔는지와 판을 읽고, 낯선 판 글자가 표지를 깨지 않는다. 단계 줄 `login` 을 내보내지
  못하면 `login()` 에 들어가지 않는다(표지 `import` · `capa_step_unwritten` — 「비밀번호를 보내기 전」 판정 `import_killed` 의 근거). `net`(닿지 못함의 증거 — `is_unreached`)은 요청을 보내기 전 연결 단계의 실패만이고
  종류 이름으로 가르지 않는다(errno 없는 `ConnectionError` · 글만 든 `requests` 연결 실패 · 응답을 든 것 · 읽기 시간 초과는 아님).
  **가벼운 불러오기 길**(2026-11-23 사용자 요청 — 리뷰 `202611211432` 발견 1 덧붙임): 패키지 전체 import 는 판 하위 꾸러미(`bigdataquery/py<주판><부판>`)
  `__init__` 의 망 초기화를 하위에서 한 번 더 해 메모리를 크게 쓰므로, 설치 판(`importlib.metadata`)이 `LIGHT_VERSION`(`2.5.0`)이고 판 폴더가 있고
  끄개 `CAPA_BDQ_LOGIN_LIGHT=off` 가 없으면(`light_folder` — 자리 찾기는 맨 위 이름에만, 패키지 코드를 돌리지 않음) 꾸러미 둘을 빈 꾸러미(`__path__` 만 —
  판 하위 꾸러미는 맨 위 꾸러미의 속성으로 묶음)로 `sys.modules` 에 심고 판 하위 꾸러미의 `server_auth` 만 불러와 `login` · `getTokenTime` 을 묶는다
  (`load_light` — `nest_asyncio.apply()` 는 빈 꾸러미를 채우는 자리 `fill_package` 가 부르고, `pyarrow` 는 `server_auth` 를 불러오는 동안만 막았다가
  묶은 뒤 걷는다 — 그 앞에 이미 불린 것은 막지 않음). 그 준비는 모두 단계 줄 `login` 앞이고 무엇이 실패해도(예외 · 속성 없음 · 부를 수 없음)
  `bigdataquery` · `bigdataquery.*` 모듈과 우리가 둔 `pyarrow` 막음을 걷고 같은 프로세스에서 전체 import 로 간다(`import` 단계 줄을 `load=full` 로 한 번
  더) — 준비에서 난 실패는 `login()` 안(거절 판정 자리)으로 넘어가지 않는다. `login()` · `getTokenTime` 이 빈 꾸러미의 꼴(꾸러미 전역 · 속성 · 꾸러미에서
  이름을 찾는 늦은 import)이나 막은 동안 불린 모듈(pandas 따위)이 정한 「`pyarrow` 없음」 에 기대 나는 실패는 그 뒤에서 나고 지금처럼 거절 · 확인 못 함이다. 단계 줄 끝 칸 `load` 는 부르는 쪽 `bdq_login._STEP_LINE` ·
  `parse_step`(`StepLine` — 그 칸이 없는 줄도 단계 · 판은 읽음)과 함께 바꾸고 진단(`ChildDiag.load` — 칸 `load`, 화면 「불러오기 light」, 알 때만)에
  실린다. `server_auth` 가 판 하위 꾸러미 `__init__` 이 만들던 전역을 기대하는지는 pod 확인 거리다(`docs/TODO.md` 1장).
  시험 `tests/test_bdq_login_light.py`(가짜 `tests/bdq_light_support.py` 를 시험마다 임시 자리에 지어 진짜 하위 프로세스로 — 기존 가짜는 설치 정보 ·
  판 폴더가 없어 늘 전체 길).
- `src/capa_simulation/io/memory_probe.py` — 자동 로그인 하위 프로세스 앞뒤의 메모리 단서와 그 하위 자신의 최고 RSS(사내 리뷰 `202611181400` 사외요청 2 — 하위가
  import 단계에서 바깥 SIGKILL 로 끝난 갈래를 가를 값). `attempt_login` 이 띄우기 바로 앞 · 끝난 바로 뒤에 한 번씩 읽고(`read`), 도는 동안 하위의
  최고 RSS 를 되풀이해 읽어(`process_peak_bytes` · `higher`) MiB · 수로 접어(`child_memory` → `container_start_report.ChildMemory`) 진단에 싣는다 — cgroup 사용 · 한도(v2 뿌리 `memory.current` ·
  `memory.max`, 없으면 v1 `memory/` 의 `memory.usage_in_bytes` · `memory.limit_in_bytes`, 뿌리는 시작 스크립트의 한도 읽기와 같은 `/sys/fs/cgroup`) · OOM 종료 수
  (`oom_kill` 줄이 처음 나온 자리 — v2 는 `memory.events` → `memory.events.local` → 혼합 마운트의 `memory/memory.oom_control`, v1 은 `memory/memory.oom_control` —
  와 그 자리 낱말 `OOM_SOURCES`, 어디서도 못 찾으면 수는 모름이고 갈래 `OOM_UNKNOWN` 을 남긴다: 어느 자리를 읽었는데 줄이 없음 `no_line`(옛 커널의
  `oom_control` 꼴) · 파일은 있는데 읽기 실패 `unread`(`FileNotFoundError` 밖의 `OSError` — 도우미 `_read`) · 후보가 하나도 없음 `no_file` 가운데 앞의 것.
  접을 때 자리는 뒤 읽기를 앞세우고, cgroup 읽기가 뜻밖의 예외로 통째 물러서면 낱말 없이 지금처럼 「oom_kill 모름」) · 한도 닿음 수(`limit_hits` — 컨테이너 메모리가
  한도에 닿은 횟수, v2 `memory.events` 의 `max` 줄 · v1 `memory/memory.failcnt`, 다른 자리로 내려가지 않고 못 읽으면 모름. 닿아도 커널이 거둬 버티면 강제로 끝내지 않아
  OOM 종료 수와 다른 값이고, 접을 때 앞뒤를 따로 싣는다), 앱 RSS(`/proc/self/status` 의 `VmRSS`), 하위 자신의 최고 RSS
  (`/proc/<pid>/status` 의 `VmHWM` — 좀비 · 없는 프로세스 · `/proc` 없는 Windows 는 모름. `getrusage(RUSAGE_CHILDREN)` 은 쓰지 않는다 — Linux 의 하위
  `ru_maxrss` 는 exec 앞에 물려받은 부모 주소 공간의 최고를 세어 앱 RSS 아래로 내려가지 않는다). 못 읽은 값은 `None`
  (화면 「모름」)이고 판정하지 않는다 — 앞뒤 OOM 종료 수가 다르면 그 사이 cgroup 이 죽인 것이라는 읽기는 사람 몫이다. 표준 라이브러리만이고 예외를
  내지 않는다. 띄우기 바로 앞에는 프로세스 단서도 한 번 읽는다(`process_clues` → `container_start_report.ProcessClues` — 2026-11-21 사내 확인: 멈춤이 저장된 채 CI/CD 뒤 새 pod 는 「넣기」 가 되고
  약 16시간 떠 있던 pod 는 import 단계에서 바깥 SIGKILL, 2026-11-21 사용자 결정 「이번 배포에 더하기」) — 부른 프로세스(앱이면 Streamlit 서버, 시작 스크립트면 그
  프로세스)가 뜬 시간(`/proc/self/stat` 22째 칸 시작 틱 — `comm` 이 괄호 · 공백을 품어도 마지막 `)` 뒤부터 가른다 — ÷ `os.sysconf("SC_CLK_TCK")` 를 `/proc/uptime` 에서
  뺌, Windows 는 틱을 묻지 않고 모름 `clock_ticks`), 스레드(`/proc/self/status` 의 `Threads`), 열린 파일(`/proc/self/fd` 항목 수 — 세는 동안 연 것 하나를 품는다),
  cgroup 프로세스 · 스레드 수 · 한도(v2 뿌리 `pids.current` · `pids.max`, 없으면 v1 `pids/` — 커널이 스레드도 하나씩 세어 앱 스레드 수 이상이다. 「max」 는 그 cgroup 에 한도
  없음이고 pod 단계 한도(`podPidsLimit` — 부모 cgroup)는 컨테이너 안에서 보이지 않을 수 있다), 프로세스 · 좀비 수(`/proc` 숫자 폴더 가운데 `stat` 을 읽은 수 —
  스레드는 세지 않는다 — 와 그 가운데 상태 `Z` 인 수, 세는 사이 사라진 것은 건너뛰고 하나도 못 읽으면 둘 다 모름 — 늘어난 것이 앱 스레드인지 프로세스인지는
  pids · 스레드 · 프로세스를 견줘 가른다). 앱은 시작 스크립트가 `os.execvpe` 로 갈아 끼운 같은 프로세스라 앱의 뜬 시간은 시작 스크립트가 시작한 때부터다.
  `/proc/uptime` 만 컨테이너 기준으로 바꿔 보이는 자리(lxcfs 류)는 시작 틱(호스트 부팅 기준)과 1초 넘게 어긋나 「앱 뜬 지」 만 모름이 된다. 뿌리는 같은 모듈 값(`PROC_ROOT` 아래 `uptime` · `self/stat` · `self/fd` · `<pid>/stat`, `PROC_STATUS`, `CGROUP_ROOT`)을
  부를 때 읽고, 값마다 무엇이 나도 모름으로 물러선다. 시험 `tests/test_memory_probe.py`(가짜 cgroup 뿌리 v2 · v1 · 없음 · OOM 종료 수 자리 차례 · 못 찾은 갈래 셋과 겹친 갈래 · 낯선 자리 낱말 · 한도 닿음 수(v2 `max` 줄 · v1 `failcnt` · 없음 · 낯선 값 · 앞뒤 따로) · 가짜 `/proc` — 괄호 · 공백 든 `comm` · 프로세스 · 좀비 셈 · 값마다 물러서기 · 아주 큰 시작 틱 ·
  사라진 프로세스 · 한도 없음 · 옛 기록 · 범위 밖 값, Linux 에서 큰 앱 아래 작은 진짜 하위의 최고가 앱 RSS 보다 작음 · 막 띄운 진짜 하위의 뜬 시간이 몇 초 안).
- `src/capa_simulation/io/object_storage.py` — 사내 S3 호환 스토리지의 큰 파일(DuckDB 스냅샷)을 `aws` CLI 로 주고받는 경계이자 앱의 유일한
  `subprocess` 자리다(명령 실행기 주입, 모든 명령에 `--profile`). 프로필 줄 한 벌(`profile_settings`)과 실패 갈래(`classify_failure` — 서버 글을 화면에 싣지 않는다)도 여기다.
  - `aws` 가 찍는 시각은 두 꼴이다 — 목록(XML)은 ISO, HEAD · GET 은 `Last-Modified` 머리 글 그대로(RFC 1123 — `aws` 1 판, 운영 이미지 판).
    둘 다 읽고(`_parse_timestamp`) 못 읽으면 모름이다 — HEAD 시각을 못 읽으면 감사 기록의 시계 차이 확인(`sys_clock_skew`)이 말없이 끝난다
    (E2E C-17). 시험 실행기(`tests/s3_mock_runner.py`)도 HEAD · GET 시각을 `aws` 1 판처럼 머리 글 그대로 돌려준다.
  - 주소 · 버킷 · 프로필(`CAPA_S3_ENDPOINT_URL` · `CAPA_S3_BUCKET` · `CAPA_S3_PROFILE`)은 사내 값이라 **환경변수로만** 받는다 — 코드 · 설정 파일에
    기본값이 없고(공개 저장소, 2026-11-12 사용자 결정) 하나라도 비면 `aws` 를 부르기 전에 넣을 이름을 대고 멈춘다(`require_settings` — 실패
    갈래 `config`). 값을 읽는 `load_settings` 는 멈추지 않는다(동기화를 쓰지 않는 앱이 설정 오류로 내려앉지 않게). 모드 · 영역은
    `CAPA_S3_*` > `config/object_storage.json` > 상수이고, 커밋되는 `mode` 는 반드시 `local` 이다. 사내 값의 꼴이 추적 파일에 다시 들어오면
    `tests/test_public_repo_hygiene.py` 가 실패한다(10장).
- `src/capa_simulation/io/s3_small.py` — 같은 저장소의 작은 객체 하나(접속 명단 파일 · 모듈 데이터 파일 — 모듈 쪽은 `module_helpers` 가 상한 8 MiB · 크기에 맞춘 마감을 넘긴다 · BigDataQuery 자동 로그인 계정 객체 `io/bdq_login_store` · 부대공정 S3 Drive 낱장 여섯 `extra_process_drive`)를 앱 프로세스가 직접 GET · PUT · HEAD · DELETE(`delete_object` — 없는 키도 성공) 하는 경계. 받기 · 머리 보기는 놓인 시각(`Last-Modified`)과 저장소 시각(`Date`)도 읽는다(`S3Object` · `head_meta` — 부대공정 「놓는 중」 판정). 콜백 자리에서 `aws` 프로세스를 띄우지 않고 프로필 없이 환경변수 키로 붙고 의존성을 늘리지 않으려 표준 라이브러리(`http.client` · `hmac` · `hashlib`)로 SigV4 를 서명한다(경로 스타일 · 연결 3초 · 읽기 5초 · 재시도 없음 · 프록시와 리다이렉트를 따르지 않음 · 받는 본문 1 MiB 상한). Streamlit 을 끌고 오지 않는다 — `auth/` 가 import 한다. 블로킹이라 이벤트 루프에서 부르지 않는다. 실패는 `S3Failure`(까닭 분류 · HTTP 상태 · 저장소 오류 코드뿐 — 키 · 주소 · 본문 없음). S3 에 붙는 자리는 이 둘뿐이다.
- `src/capa_simulation/io/xlsx_small.py` — 값 · 서식(칠 · 글자 · 숫자 꼴 · 테두리 · 정렬) · 열 너비 · 줄 높이 · 고정을 든 작은 xlsx 통을 표준 라이브러리(`zipfile` · 글자 XML)만으로 쓴다 — 새 의존성을 넣지 않는다(사내 이미지 · WebIDE 가 새 패키지를 받는지 따로 확인해야 한다). Excel 이 「복구」 창 없이 여는 꼴을 지킨다: ECMA-376 요소 차례, `fills` 첫 둘 `none` · `gray125`, 사용자 숫자 꼴 164 부터, 색 `FFRRGGBB`, sharedStrings, XML 이 받지 않는 제어 문자 걷기, NaN · 무한은 빈 칸, 파트와 `[Content_Types].xml` · 관계 파일의 짝(뼈대는 xlsxwriter 출력과 같고 테마 파트만 없다 — 글꼴이 테마를 가리키지 않는다). 숫자처럼 보이는 글자 칸(글자로 둔 달 머리 「26.11」 — 숫자로 두면 「26.1」 처럼 끝 0 이 사라진다)은 작성기가 스스로 모아 시트의 「오류 무시」 표지(`ignoredErrors` · `numberStoredAsText` — `pageMargins` 바로 뒤, 이웃 칸은 범위로 묶음)로 덮어 Excel 의 초록 삼각형(「텍스트 형식으로 저장된 숫자」)을 끈다 — 시트를 짓는 쪽은 범위를 넘기지 않고, 숫자 칸 · 숫자로 안 보이는 글자 칸은 덮지 않는다(2026-11-11 사용자 실기 Q2-6). 같은 입력은 같은 바이트다. 작성기가 내는 바이트가 바뀌면 통을 세션에 기억하는 세 판(`process_capa_view.SHEET_SCHEMA_VERSION` · `availability_gap_panel.GAP_SHEET_SCHEMA_VERSION` · `calculation_result.SHEET_SCHEMA_VERSION`)을 함께 올린다 — 올리지 않으면 같은 조건의 옛 통이 세션에서 그대로 나온다. 토큰 · 도메인을 모른다(`tests/test_xlsx_small.py` — 되읽기는 표준 라이브러리 시험 도우미 `tests/xlsx_read.py`).
- `src/capa_simulation/io/bigdataquery_catalog.py` — 기간 내 코드 목록만 조회한다(상세 SQL·정규화 경로와 섞지 않는다).
- `src/capa_simulation/io/reference_cache.py` — 세션 활성 리비전의 표·공용 표시순서 경계다(5장 1, XLSB 대체 없음). 활성
  리비전이 없는 읽기는 `NoActiveRevision`(`RuntimeError`)이고, `page_bootstrap.bootstrap_error_message` 가 저장소를 보고 글 넷
  (`reference_cache` 의 `NO_OFFICIAL_MESSAGE` · `EMPTY_STORE_MESSAGE`(시나리오가 하나도 없음 — DB 등록, 2026-11-14 물음 보드 seed (nopub)) ·
  `ARCHIVED_ONLY_MESSAGE`(보관함 › 되돌리기 — 작은 결정 a8) · `NOT_LOADED_MESSAGE`(공식은 있는데
  이 세션이 안 불러옴))로 가른다(`no_revision_message` — 그 갈래만 저장소를 읽고 없는 DB 는 만들지 않는다). 그 글은 오류가 아니라 빈
  상태다 — 화면은 「데이터 Error」 마크 대신 회색 한 줄(「공식버전 없음」)을 세운다(`page_bootstrap.empty_state` · `data_error_mark`,
  2026-11-14 「앱 대신 뜨는 화면」 보드 카드 p1-no-revision). 공식버전이 없는 세 갈래의 알림은 화면마다 따로 내지 않고 상태 알림
  `SC-01` 하나이고, 멈춘 회차의 사이드바 잠긴 값 칸도 「계산 멈춤」 대신 그 회색 줄 글이다(`page_bootstrap.stopped_field_value` —
  2026-11-14 물음 보드 decided 5).
- `src/capa_simulation/persistence/` — 시뮬레이션·설비 DuckDB 의 마이그레이션·Repository·캐시를 독립된 모듈·파일로 둔다.
  - 쓰기는 프로세스 잠금 + 단일 트랜잭션, 읽기는 작업별 연결이다. `app.py` 는 rerun 한 번을 `pinned_connections` 의
    게으른 핀으로 감싼다(상시 앵커가 아니다, 9장).
  - 리비전 스냅샷은 `st.cache_resource` 에 읽기 전용 한 벌을 두고, 시나리오를 여는 길에는 같은 배열의 겉껍데기 사본
    (`load_scenario_snapshot_for_activation`), 그 밖에는 깊은 사본(`_private_copy`)을 넘긴다(5장 20). 목록은 캐시하지
    않고, 무효화는 DB 를 바꾼 호출부의 `clear_*_cache()` 다(5장).
  - 표 저장 위치는 4장·`docs/data_model.md` 다. `compare_legacy_results.py` 의 대조 기준은 리비전 1 이다.
- `src/capa_simulation/home_state.py` — HOME 토글 일곱 개의 세션 키와 불변 기본값, HOME 팝업 열림 칸 하나
  (`HOME_DIALOG_KEY` — `home_open_dialog`, 「HOME 설정」 · 공정 필터 · 주요공정 히트맵 셋이 같이 쓴다 — 값 `settings` ·
  `process_filter` · `key_process`, HOME 팝업 호스트 key `HOME_DIALOG_HOST_KEY` 는 `home_dialog_host`)·안쪽 탭 key·라벨을 UI·저장소
  import 없이 선언한다. 페이지 스크립트는 import 할
  수 없어 팝업 상수도 여기다(주요 Case 칩이 팝업을 `비교 · 주요 Case` 탭으로 연다). 안쪽 탭은 다섯(`HOME_SETTINGS_TAB_LABELS`)이고
  앞 넷(`HOME_PREFERENCE_TABS`)이 Preference 편집기 몫이다. HOME 정렬 메모 칸 이름(`HOME_SORT_MEMO_KEY` — `home_sort_memo`, 3장
  `home.py`)도 같은 까닭으로 여기 두고 HOME 화면 · 시나리오를 바꾸는 자리(`scenario_activation._STALE_VALUE_KEYS`)가 함께 읽는다.
- `src/capa_simulation/shared_process.py` — 화면 사이 공용 공정 값(2026-11-08 답 P1 · P2 — 공정 공유 1차)의 값과 규칙 한 곳.
  세션 동안만 살고 DB · 리비전 · 공용 프로필에 쓰지 않으며 원본 공정명이다. 화면은 공개 함수만 부르고 세션 칸은 이 모듈 밖에서
  만지지 않는다(5장 38, 그물 `tests/test_shared_process.py`). HOME 은 보내기만(`publish_from_home`), 하나 고름 화면은 받고
  (`follow_single`) 사이드바 공정 칸 팝업에서 직접 고른 공정만 보낸다(`pick_single` — 2026-11-09 보드 C2 (가)), 여러 개 따라감
  화면은 값 칸이 쓰고(`process_field.render_process_filter`), 거름 밖 초안 수는 `count_outside` 다. 따라가는 화면은 선언 한 곳
  (`FOLLOWERS` — 페이지 파일 → 출처 이름 · 갈래)이고, 화면마다 마지막으로 그린 선택지(`note_drawn`)로 `screen_mark` 가 탭 표지 ·
  머리 칩의 근거(걸리나 · 없는 공정)를 낸다. 보내는 화면의 보이는 글자는 값과 함께 싣는다(`labels`). 원본 이름으로 그리는
  화면은 `ORIGINAL_NAME_SCREENS`(Space 하나 — 값 칸을 `labels` 없이 그린다)이고 그 화면에서는 머리 칩 · 판 · 그 탭 깔때기 풍선도 원본이다(2026-11-10
  보드 Q-3 · 2차 보드 Q2-17 — 한 화면 한 이름). 그 밖의 화면은 그 화면 표시명이다 — 지금 공용 표시명 프로필로 적고(보낸 글자보다 먼저 —
  같은 세션에 표시명이 바뀌어도 옛 이름이 남지 않는다), 그린 화면은 마지막으로 그린 선택지(`drawn_options`)로 겹친 표시명을 값 칸처럼
  「표시명 (원본)」 으로 가른다(그리지 않은 화면 · HOME 은 공용 값과 그린 화면 선택지 전부로 가른다). 보낸 글자는 프로필이 비었을 때(DB 파일이 아직 없음 · 읽지 못함)만 쓴다(2차 보드 Q2-18, `process_field._label_of`). 사용자 메모(모니터링 · 원복 검토)에 맞춘 원복 길은 이 모듈과 `components/process_field.py`, 그 둘을 부르는 줄을 걷고 화면마다
  고르는 칸을 되살리는 것이다.
- `src/capa_simulation/process_detail_state.py` — 공정 Capa 상세의 세션 키·주소 인자 계약과 HOME 칸 클릭 전달을 맡는다.
  - 칸 클릭 콜백은 이동 대기 칸만 적고(`queue_home_cell`), HOME 프래그먼트 본문 첫 줄이 전달 칸을 적어 옮기며
    (`switch_to_queued_process_detail` → `open_process_detail`), 받는 페이지 맨 앞에서 꺼낸다(`take_process_detail_request`).
  - 주소 `from` 은 `home`·`gap`·`shortening` 이고 들어온 회차의 `ProcessDetailEntry.source` 가 된다. `shortening` 링크는
    그 카드의 `target`·`period`·`shortened`·`new` 도 싣고(`shortening_card_query_params`) 상세는 그것만 읽어
    `ShorteningOrigin`(그 공정을 보는 동안만)·`shortening_band_text` 를 낸다. ◀▶ 차례
    (`process_steps`)와 그 콜백(`step_to_process` — 공정과 그 공정의 첫 미달 달)도 여기다.
  - 설비 시나리오 **방문 기준**(`PROCESS_DETAIL_EQUIPMENT_BASIS_KEY`)도 여기다. HOME 칸으로 들어온 방문은 `"official"` 이고
    출처 띠와 달리 ◀▶ 로 공정을 넘겨도 그 방문 동안 남는다. 새 방문(탭을 닫았다 다시 연 것 포함 — 아래)·다른 길(카드·
    주소)이면 걷어 세션 설비 시나리오를 따른다. 필요 단축 일정 카드 링크의 `eq` 는 그 카드가 본 설비 시나리오 한 마디(표시용)이고, 이 화면 기준과
    다를 때만 출처 띠 끝에 적는다(`equipment_band_tail`).
  - 「새 방문」 판정(`_continues_this_page`)은 **이미 연 화면 탭으로 다시 들어온 회차를 이어 봄으로 본다**
    (`page_tabs_state.reentered_open_tab`, 2026-10-24) — 탭을 오가도 출처 띠·가로 시작 달·설비 방문 기준이 남는다.
    탭을 닫았다 다시 열면 새 방문이다.
- `src/capa_simulation/page_tabs_state.py` — 머리 띠 아래 화면 탭 줄의 상태다(2026-10-24 사용자 결정). 이 접속에서 연 탭
  (`PageSpec.path`, 보이는 차례)·고정한 탭·이동 대기 칸·「이미 연 탭으로 들어옴」 표지(`reentered_open_tab`)를 세션에 두고,
  열기(끝에 붙임)·닫기(지금 탭이면 오른쪽, 없으면 왼쪽 이웃)·고정(고정 탭은 왼쪽, 닫기 없음, 마지막 하나는 닫지 않음)·
  차례(`moved` — 고정하지 않은 탭을 `before` 탭 앞, 없으면 끝으로. 고정 탭은 움직이지 않고 그 앞으로도 가지 않는다 —
  2026-11-02 사용자 요청)·상한(`MAX_TABS` 10 — 넘는 화면은 열지 않고 탭 줄에 알림)을 순수 함수로 정한다. 탭 줄 JS 가
  묶어 보낸 그림의 차례는 `arranged` 가 목록에 입힌다(열린 탭·고정은 서버, 차례는 그림 — 2026-11-03)와 그 그림 번호
  (`PAGE_TABS_ORDER_SEQ_KEY` — `order_seq`·`note_order_seq`, 더 큰 번호만)도 여기다. 탭 줄 JS 가 누르자마자 그린 그림과
  서버 목록(열린 탭·고정)이 어긋나면 `resync_strip` 이 epoch 만 올려 다음 data 로 다시 그리게 한다. UI 가 없어
  `process_detail_state` 가 불러온다. 탭 줄 컴포넌트 key(`PAGE_TABS_COMPONENT_KEY`)도 여기다 — 껍데기 CSS 가 그 key 를 고른다.
  - 옮기는 것은 `app.py` 의 `st.navigation()` 바로 뒤 본문(`switch_to_queued_tab` — 테마 인자를 싣는 `st.switch_page`)이다.
    콜백은 칸만 적는다(9장 「팝업과 콜백」). 목록은 이 접속에만 산다 — 새로고침·테마 바꾸기는 HOME(고정)과 지금 화면만
    남는다.
  - 상한은 **옮기기 전에** 막는다 — 화면을 옮기는 파이썬 도우미(HOME 칸 `open_process_detail`, 공정 Capa 상세의
    `open_shortening_page`·`open_availability_gap`)는 전달 칸을 적기 전에 `refused_at_tab_limit` 을 부른다(걸리면 알림을
    남기고 `st.rerun()`). `st.switch_page` 로 옮긴 뒤 `app.py` 가 되돌리면 Streamlit 프런트가 두 화면을 `pushState` 로
    쌓아 뒤로가기가 그 화면에 갇히고, 넘기던 칸이 실패한 클릭인데도 남는다. 새 이동 도우미도 같은 줄을 둔다. HOME 칸은
    그림 선택 **콜백**(`queue_home_cell`)에서 거른다 — 본문에서 거르면 그림 선택 값이 걷혀 브라우저가 되보낸 선택이 다음
    조작에 다시 들어온다(9장 「팝업과 콜백」 끝). `open_process_detail` 의 거름은 마지막 안전망이다.
  - `_switch`(`st.switch_page`)는 주소 인자를 다시 적느라 프런트가 떠나는 화면 경로로 기록을 한 칸 먼저 쌓는다. 탭 줄 JS 가
    문서의 `history.pushState` 를 감싸 같은 경로의 쌓기를 늘 칸 바꾸기로 돌린다(`page_tabs.js` 의 `<tabs-history>`) — 탭
    줄·HOME 칸·다음 화면 단추 어느 길의 `st.switch_page` 든, 링크 인자를 받아 지우는 화면(`st.query_params.from_dict`·`del`)이든
    이동 한 번이 기록 한 칸이고 뒤로가기 한 번이 직전 화면이다. 같은 화면의 주소 인자 바꾸기(Space `?floor=` 등)도 칸을
    더하지 않는다 — 뒤로가기로 층을 거슬러 가지 않는다(세션이 먼저라 어차피 되돌지 못하고 갇혔다).
  - 「이미 연 탭으로 들어옴」 표지는 화면이 바뀐 회차에 정하고 **같은 화면에 머무는 동안 그대로 둔다** — 다시 들어온 첫
    회차가 끊기면 실행 표지가 앞 화면 그대로라, 다음 회차에 표지를 지우면 새 방문으로 보았다(2026-10-25 리뷰).
  - `_switch` 는 옮기러 가는 화면을 늦게 온 옛 화면 회차 막이에 적는다(`stale_page_guard.note_switch` — 9장 「화면 탭 줄」).
    `switch_back_to` 는 그 막이가 가른 회차를 옮겨 간 화면으로 다시 보내는 같은 길이다.
- `src/capa_simulation/stale_page_guard.py` — 늦게 온 옛 화면 회차 막이(2026-11-19 — 칸을 고치자마자 누른 화면 탭이 Space 로
  되돌아오던 수). 브라우저는 회차 요청에 마지막으로 받은 `new_session` 의 화면을 싣는다 — 탭 · 링크로 옮기는 요청 뒤 옮긴
  화면이 닿기 전에 떠나는 화면 위젯이 보낸 메시지(편집표가 접힌 편집을 걷고 0.15초 뒤 보내는 상태 등)는 떠나는 화면 주소로
  간다. 이번 회차 화면이 들인(또는 옮기러 간) 화면과 다르고 **그 화면 본문 위젯의 값을 실었으면** 옛 메시지로 보고
  (`stale_verdict` — 프런트의 옮기는 요청은 앱 칸 값만 싣는다) 옮겨 간 화면 경로를 돌려준다(`stale_target`). 기록은 세션 칸
  하나(`GUARD` — 들인 화면 · 옮기러 간 화면 · 화면별 본문 위젯 id)이고 `app.py` 가 세 자리에서 부른다 — 회차 맨 앞
  (`st.navigation()` · 머리 띠 · 부트스트랩 앞 — 떠난 화면 주소가 기록에 쌓이지 않는다), `st.navigation()` 바로 뒤(`note_page`
  — 주소로 연 회차), 페이지 본문 앞뒤(`body_widgets_before` · `note_body_widgets`). 요청의 위젯 값 · 회차에 등록한 위젯 id ·
  요청한 화면 · 화면 목록의 파일 자리는 공개 API 가 없어 Streamlit 내부(`_new_widget_state` · `ctx.shared.widget_ids_this_run` ·
  `pages_manager.intended_page_script_hash` · `get_pages()` 의 `script_path` · `main_script_path`)를 읽고, 못 읽으면 막지 않는다
  (`streamlit==1.63.0` 고정 — `sidebar_status._only_this_widget_changed` 와 같은 자리). 회차 맨 앞의 화면 경로 찾기는 같은 세션의
  앞 회차가 적은 화면 목록을 읽는다(세션이 화면 목록 칸 하나를 회차마다 넘긴다). 시계를 쓰지 않는다. 시험
  `tests/test_stale_page_guard.py` — 판정 · 가짜 실행 문맥 차례에 더해 읽는 내부를 실제 실행(AppTest — `st.navigation` 앱)으로
  본다(판을 올려 말없이 꺼지는 것을 잡게).
- `src/capa_simulation/scenario_state.py` — 세션별 활성 시나리오와 `revision`·`content_token` 을 관리한다(5장 3). 편집
  없는 토큰은 리비전 고정값(`pristine_content_token`)이라 세션끼리 계산 캐시를 나눈다. 편집본은 잠긴 원본이면 같은 배열의
  겉껍데기 사본, 아니면 깊은 사본이다(`_session_copy` — 5장 20). 활성 시나리오를 바꾸거나 버리는 길(편집 적용
  `apply_month_updates`·`apply_table_updates` · 원본 되돌리기 `reset_active_scenario` · 불러오기와 저장 뒤
  `activate_scenario_tables` · `clear_active_scenario`)이 갈아끼워지는 **편집본** 토큰의 전체 기간 칸을 걷는다
  (`_retire_edit_cell` → `simulation_cache.retire_full_capacity_outcome` — pristine 칸은 걷지 않는다,
  `tests/test_edit_token_retire.py`). 걷는 키는 이 세션이 마지막으로 읽은 부하 예외 선언(`ROUTE_EXCEPTIONS_SEEN` —
  `page_bootstrap.route_exceptions_of` 가 `note_route_exceptions` 로 적는다)으로 접은 것이고 걷기는 DB 를 열지 않는다(5장 45).
  다른 모듈이 활성 시나리오 칸을 읽는 창구는 `ACTIVE_SCENARIO`(`SessionSlot` 「있거나 없음」 칸 —
  `peek`, 5장 42)이고 쓰기는 이 모듈의 함수만 한다.
- `src/capa_simulation/frame_sharing.py` — 세션끼리 함께 쓰는 표의 numpy 배열(데이터 블록 · 축 · 확장 배열 칸) 잠금
  (`lock_frame`) · 잠김 확인(`frame_is_locked`) · 잠긴 표의 겉껍데기 사본(`shared_view` — 프레임 · 축 객체만 새로) · 잠긴
  배열에 쓰다 난 오류 가르기(`is_locked_write_error` — 계산 결과 칸이 담지 않고 다시 올린다)를 한 곳에 둔다(5장 20). pandas · numpy 만 보는 잎이라 `persistence/cache.py` · `io/reference_cache.py` · `scenario_state.py` 가 함께
  쓴다.
- `src/capa_simulation/scenario_activation.py`, `scenario_preset_state.py` — 저장 리비전과 그 프리셋을 세션에 원자적으로
  활성화한다(새 세션은 최신 공식 리비전). 프리셋 키·기본값은 이 파일과 `persistence/models.py` 에만 선언한다.
  - 저장소가 비었으면 첫 세션 부트스트랩(`bootstrap_latest_official_scenario`)이 운영 서버가 아닐 때만 내장 시드로 첫
    공식버전을 세운다(`builtin_seed_allowed` — `SsoConfig.operational` 의 반대, Admin Area 잠금과 같은 판정. 2026-11-14 물음
    보드 seed (nopub), `tests/test_application_bootstrap.py`).
  - 값 칸(`_STALE_VALUE_KEYS` — 편집 화면 원본 토큰 · 자기 적용 칸, HOME Figure 칸, HOME 정렬 메모, 두 편집 그리드 칸)을 지우고 HOME
    토글에 기본값을 적으므로 토글을 그리기 전에만 부른다(9장). 활성
    시나리오의 새 리비전 저장(`activate_saved_revision`)은 토글을 둔다. UPEH 가정 % 도 같은 길에서 100 을 적고 그
    공유 위젯의 주인 칸을 지운다(구간은 둔다, `tests/test_scenario_activation.py`).
  - 이름 변경은 활성화가 아니다 — `rename_active_scenario_label`·`rename_active_revision_label` 이 같은 id 일 때 이름표
    한 칸만 고친다(다른 세션은 다시 불러올 때 바뀐다).
  - 올라온 시나리오의 최신 리비전 번호(`ACTIVE_SCENARIO_LATEST_KEY`)는 `app.py` 가 `check_active_scenario_latest` 로
    `LATEST_RECHECK_SECONDS`(30초)에 한 번(다른 시나리오를 불러온 회차는 곧바로) 보관본까지 목록을 읽어 적고, 줄 배지·머리 띠는
    `newer_active_revision_no` 로 세션만 읽는다(5장 23, `tests/test_scenario_activation.py`·`test_app_navigation.py`).
  - 프리셋을 걸 때 HOME 의 아는 공정 기억(`PROCESS_SEEN_KEY`)을 지운다(`tests/test_process_filter_activation.py`).
- `src/capa_simulation/equipment_scenario_activation.py` — 세션의 설비 시나리오(시뮬레이션 `scenario_activation.py` 의 짝).
  세션은 (설비 시나리오, 일정 리비전) 하나를 고정해 들고(`equipment_scenario_selection_v1` — 기본형만), 보는 한 벌은
  (공통 대장 최신, 고른 일정 리비전) 쌍을 합친 스냅샷이다.
  - 페이지 진입은 `resolve_equipment_session(path)` 다 — 설비 화면이 `BOOTSTRAP_ERRORS` 아래에서 부르고(`app.py` 는 설비
    DB 를 열지 않는다) 목록·공통 최신 id·합친 본문을 모두 캐시에서 받는다. 선택이 없으면 공식(최신 발행 → 없으면 목록 첫
    시나리오 최신)이다. 고정 쌍을 지금 공통과 합칠 수 없으면(`EquipmentScenarioIncompatible`) 그 시나리오 최신 → 공식으로
    옮기고 편집본을 다시 세운 뒤 그 회차 `EquipmentSession.notice` 로 한 번 알린다.
  - 판정은 셋이다(「공식」 하나로 가르지 않는다) — **공식 시나리오**(세션 시나리오 = 최신 발행의 시나리오: 설정 팝업 Cut-off 편집·
    미확인은 자기 일정·Space 공식 배치 편집), **공식 발행 쌍**(세션 쌍 = 최신 발행: 기준선 저장), **가정**(공식 시나리오가
    아님: 설정 팝업 Cut-off 읽기 전용·미확인은 공식 기준·Space 는 그 시나리오의 배치 차이). 따로 **낡음**(세션 리비전 ≠ 그
    시나리오 최신)은 일정 칸·행 추가를 잠근다. 발행이 하나도 없으면 공식 시나리오의 최신을 공식 자리로 본다. Space·설비
    마스터 탭 배치 칸의 편집 권한은 `space_edit_mode` 한 곳이다(`SpaceEditMode` — 3장 `space_status.py`).
  - `select_equipment_scenario` 는 팝업 「불러오기」 다 — 미저장 설비 편집이 있으면 「변경을 버리고 불러오기」 체크가 있어야
    하고, 합친 스냅샷을 먼저 읽어 검증한 뒤에야 편집본을 비우고(FAB 대기분은 남김) 선택을 적는다. 자기 저장이 일정 리비전을
    만들었으면 다음 회차 선택이 그 리비전으로 옮긴다(작업 공간 표지 칸 — 거꾸로 import 하면 순환이다).
  - 머리 띠·사이드바 줄 글자 재료는 라벨 칸(`equipment_scenario_label_v1`)에 페이지가 그 회차 목록을 읽은 뒤 적는다(5장 23).
    `select_equipment_scenario` 도 옮긴 쌍으로 라벨을 바로 적는다 — `app.py` 가 페이지보다 먼저 그리는 변경 칩 「설비 가정」
    (`change_summary.session_changes`)이 옮긴 회차에 맞는다(한 회차 늦지 않게, 시험 `test_equipment_scenario_session.py`).
- `src/capa_simulation/shared_widget_state.py` — 여러 페이지가 같은 key 로 그리는 위젯 값을 첫 회차에도 다시 알린다(9장).
- `src/capa_simulation/session_slot.py` — 새 코드가 세션 칸을 쓰는 한 창구 `SessionSlot`(5장 42 — 칸 이름 · 꼴 · 처음 값 선언 한 줄,
  `get` · `peek` · `setdefault` · `set` · `clear` · `exists`, 처음 값 없는 「있거나 없음」 칸은 `peek`). 바로 쓰는 자리 수 그물은
  `tests/test_session_state_sites.py`(파일마다 기준선 `tests/session_state_baseline.py`), 창구 시험은 `tests/test_session_slot.py`.
- `src/capa_simulation/constraint_simulation_state.py` — 제약 시뮬레이션의 세션 키(모두 `constraint_sim_` 접두)·버튼 값·기본값
  (D8 — 제약 120% · 기준 HOME · 개조 켬 30일 · 비중대로 켬, 2판 — 보유 0 · 신규 끔 · 기준일 오늘)·주소 인자 계약(`constraint_query_params`·
  `take_constraint_process_request`)과 칸 선택 그림 key 둘(`app.py` `CELL_SELECT_CHART_KEYS`)을 UI 없이 선언한다. 공정 Capa
  상세 머리 링크와 `app.py` 가 import 한다.
  - 제약 시작·끝 상자는 정수 달 선택지라 `prune_choice`(글자 선택지 전용)가 아니라 `settle_period` 가 위젯 앞에서 매 회차
    잡는다 — 사용자가 상자를 고치기 전에는 늘 기본값(그 제품의 첫 소요 달 ~ 보이는 마지막 달 — 제품·공정을 바꾸면 그 제품의
    첫 소요 달로 다시 선다, 2026-10-25 E2E), 고친 뒤에는 그 값이 보이는 달 밖일 때만 가장 가까운 달을, **다를 때만** 적는다.
    엇갈림은 `on_change` 콜백 둘(`follow_period_start`·`follow_period_end`)이 다른 상자 칸을 맞추고(승인 초안 그대로) 「고침」
    표지(`CONSTRAINT_PERIOD_EDITED_KEY`)를 세운다.
    범위 `st.select_slider` 는 쓰지 않는다 — 1.63 은 `value=` 없이는 범위로 서지 않아 손잡이를 움직이면 첫 달 하나로 떨어진다.
  - 목록에 없는 보유 제약 설비 숫자 칸·신규 기준일 날짜 칸은 위젯 앞에서 틀린 꼴(범위 밖 정수·날짜 아님)일 때만 기본값을
    심는다(`seed_owned_units`·`seed_new_since`) — 범위 밖 옛 값이 위젯 예외가 되지 않게. 기준일은 자정을 넘긴 세션에서도 그날
    값 그대로다(칸에 보이는 값이 곧 계산 값).
  - 보유 「호기 고르기」(2026-11-01 결정 B3)는 정본이 위젯 아닌 칸 하나(`CONSTRAINT_HELD_KEY` — `{공정: [설비키]}`, 틀린 꼴은
    빈 것으로 본다)이고 multiselect 칸(`CONSTRAINT_HELD_INPUT_KEY`)은 `settle_held_units` 가 위젯 앞에서 **매 회차** 그 공정
    목록을 적는다(`prune_list_selection` 과 같은 까닭 — 선택지 글자에 날짜가 들어 시나리오를 바꾸면 글자가 바뀐다). 콜백
    `follow_held_units(공정)` 이 위젯 값을 정본으로 옮긴다. 공정마다 따로라 공정을 바꿔도 다른 공정의 고름이 남는다. 지금 선택지에
    없는 호기는 정본에서 빼고 (공정, 그 회차 선택지, 뺀 설비키) 를 알림 칸(`CONSTRAINT_HELD_DROPPED_KEY`)에 두어 같은 공정 · 같은
    선택지인 동안 한 줄로 알리고, 공정·선택지가 바뀌거나 고름을 바꾸면 걷는다(B3-2). 선택지는 조회기간에 하루라도 있는 호기라
    조회기간을 좁혀 선택지에서 빠진 호기도 같은 길로 빠진다(알림 글은 「지금 설비 시나리오 · 조회기간의 이 공정 목록에 없는」).
    계획 앞에서 멈추는 갈래의 잠긴 빈 칸은 제 key(`CONSTRAINT_HELD_IDLE_KEY`)로 선다.
  - 시나리오를 바꿔도 조건은 남는다(`scenario_activation._STALE_UI_KEYS` 에 넣지 않는다 — 값이 아니라 가정이다). 공정·제품은
    `prune_choice`, 기간은 `settle_period` 가 맞춘다.
- `src/capa_simulation/modification_schedule_state.py` — 제약 시뮬레이션 「개조 일정」 모드의 모드 전환 칸(`constraint_sim_mode`)과
  조건 세션 키(모두 `constraint_sim_sched_` 접두)·기본값(4대 · 30일 · 동시 상한 없음 · 안전 여유 0% · 내일부터 · 기한 없음 ·
  가장 빨리)·버튼 값을 UI 없이 선언한다. 시작·기한 상자는 정수 선택지(0 = 「내일」·「없음」)라 `settle_choice` 가 위젯 앞에서
  선택지 밖 값을 0 으로 **다를 때만** 적고, 목적은 기한이 없으면 `settle_objective` 가 「가장 빨리」 로 적는다. 제약 모드 계약과
  나눠 둔 것은 두 모드를 병행 가지가 따로 고치기 때문이다.
- `src/capa_simulation/upeh_assumption_state.py` — UPEH 가정 세 칸(%·적용 시작·끝)의 세션 키와 기본값. UI 를 import 하지
  않아 시나리오 전환 초기화(`scenario_activation`)가 읽는다.
- `src/capa_simulation/sync_boot.py` — managed 모드일 때만 `sync_state` 에 두 DB 경로를 등록한다. 판정은 프로세스에 한 번이고 설정을 못 읽으면 앱은 띄운 채 값 없는 고정 낱말로 까닭을 남긴다(`SY-01`). 시작 점검의 `head_ignored` · `head_unchecked` 표지도 여기서 읽는다(`SY-05` · `SY-06`). 부트 기록(`data/temp/object_sync_boot.json`)도 여기다.
- `src/capa_simulation/performance.py` — HOME 단계별 소요시간을 잰다. 업무 데이터는 기록하지 않는다.
- `src/capa_simulation/services/simulation_cache.py` — 계산 함수의 content-addressed Streamlit 캐시 래퍼를 모은 경계다
  (5장 4·「키 방침」). 큰 프레임은 `_` 인자 + 내용 지문(`frame_digest`)으로 받는다.
  - 대당 Capa·소요대수는 전체 기간으로 한 번 계산해 자르고(`get_full_capacity_outcome` → `slice_capacity_months`,
    `tests/test_full_period_capacity.py`) 오류도 `CapacityOutcome` 으로 캐시한다. 캐시는 전체 기간 칸 하나다
    (`FULL_CAPACITY_MAX_ENTRIES` 8칸) — `get_scenario_capacity_and_demand` 는 칸을 두지 않고 부를 때마다 그 칸에서
    자르며(이름 · 인자 · 실패 동작은 그대로, 조회기간 오류 칸 `get_period_capacity_error` 는 따로), 편집본 칸은 새 편집
    토큰이 설 때 키로 걷는다(`retire_full_capacity_outcome`, 5장 3). 배경 회차는 순수 코어
    `full_capacity_outcome` 을 부른다. 화면에서 그 순수 코어를 캐시 없이 부르는 곳은 넷이다 — 입력 점검(고른 리비전마다 계산하므로
    결과 대신 묶음만 요약 칸 `get_revision_input_check` 에 둔다, 5장 39), 그리고 부대공정을 합친 표를 보는 셋(Admin 「부대공정」 의
    「시험 계산」 · 「부대공정 얹기」 · DB 등록의 R-07 등록 점검 — `extra_process_merge.capacity_stop` · `capacity_outcome`). 셋은
    한 번 누른 회차에만 돌고 저장 전 표라 공유 칸에 두지 않는다(미리보기는 합친 표의 계산 하나를 두 셈이 함께 쓰고, 얹기는 바탕
    리비전 · 판마다 세션 메모 한 벌).
  - 계산 키는 빌더 셋으로만 짓는다 — `scenario_cache_key`(조회기간 칸) · `full_scenario_cache_key`(전체 기간 칸 · 입력 점검 칸 ·
    편집본 칸 걷기) · `build_home_simulation_cache_key`(HOME). 셋 다 부하 예외 선언(`route_exceptions` — 기본값 없음)을 받아 내용
    토큰에 접은 **계산 토큰**(`calculation_token` — 빈 선언이면 내용 토큰 그대로)을 둘째 칸에 싣고, 전체 기간 칸 · 조회기간 오류
    칸이 그 토큰에서 선언을 푼다(`token_route_exceptions`, 5장 44). 선언을 접지 않는 편집표 키 `scenario_content_key` 는 생산
    계획 · 기준 정보 편집표 두 자리만 쓴다. 소요대수 길(`get_capacity_and_demand` · `full_capacity_outcome`)도 선언 칸에 기본값이
    없다(`tests/test_route_load_exception_keys.py`).
  - 계산 밖 공정 칸(`get_unimplemented_basis_processes` — 소요기준 BOX · PCB 경로가 있는 공정, 11장)은 계산 칸이 아니라 빌더 셋
    밖이다. 키는 활성 시나리오 `content_token` + 조회기간 스칼라이고 부하 예외 선언을 접지 않는다(선언이 목록을 바꾸지 않음).
    `RQ_REQB` 는 `_` 인자(프레임 또는 빗나갈 때만 부르는 로더)다(`tests/test_scenario_result_cache.py`).
  - HOME Figure 는 묶음별 공용 LRU(`shared_home_figure_store`)에 pickle 바이트로 둔다(복원 `components/home_rendering.py`,
    `tests/test_home_figure_cache.py`). 「소요대수만」 돌려주는 래퍼는 두지 않는다.
  - 설비 마스터를 받는 래퍼는 표를 Streamlit 이 해시하지 않는다 — 일정 미정 · 사용기준 밖 · 주차 집계는 `_cached_*` 의 `_`
    인자 + 내용 지문 키이고, 그 셋과 일정 확인(`get_schedule_confirmation_issues`) · Space 기준일 상태(`space_status_cache_key` ·
    `get_space_equipment_status`) · 구간 키(`equipment_span_cache_key`) · 필요 단축 키(`required_shortening_cache_key`) · 설비 일정 키
    (`process_equipment_timeline_cache_key`)는 키워드 `equipment_digest` 를 받는다(`_equipment_digest` — 주면 그 값, 안 주면
    `frame_digest(equipment)` 라 같은 지문이면 같은 칸). 넘기는 쪽은 그 표의 지문임을 지킨다 — 거른 표에는 넘기지 않는다(세션
    메모는 `equipment_data_workspace.remembered_digest`). 지금 넘기는 화면은 가용설비 현황 · Space 이고 필요 단축 일정 · 공정 Capa
    상세 · 제약 시뮬레이션은 아직 넘기지 않는다(`docs/TODO.md` 2장 「성능」 A2).
  - 월 부하 환산에는 키 꼴 `get_monthly_volume_by_key`(다섯 표를 `_` 인자로 받고 부르는 쪽 키 — 시나리오 `content_token` ·
    기준정보 판 · 표시순서 지문 · 거른 계획 지문 등 — 로 칸을 가른다)가 있다. 값은 `get_monthly_volume` 과 같고, 부르는 곳은 아직
    없다(생산 계획 환산이 그 꼴로 옮기는 일 — `docs/TODO.md` 2장 「성능」 A1).
  - 필요 단축 일정 계획 키 끝 칸은 UPEH 가정 토큰이다. 공식 칸과 가정 칸(공정 Capa 상세의 목표 하나 칸 하나 —
    `ASSUMED_PLAN_MAX_ENTRIES`)은 따로이고 서로의 키를 받지 않으며, 계획은 키와 한 묶음(`KeyedShorteningPlan`)으로만
    CSV·진척 캐시에 간다 — 그 둘은 공식 키만 받는다(5장 31, `tests/test_upeh_assumption_cache.py`).
  - 범용 편집 그리드 껍데기(`get_edit_grid_base`)는 키 전용 래퍼다 — 양식·규격·표시명은 `_` 인자로, 키는 내용 토큰·줄 차례 지문·
    표 이름·표시명 지문이고 색인(op 반영)과 껍데기 본문을 한 묶음(`EditGridBase`)으로 돌려준다. `get_edit_grid_base_within` 은
    같은 키에 본문 바이트 상한(`max_bytes`)을 더해 넘는 표는 본문 대신 None 을 담는다 — 큰 표 상한에 걸린 표의 전체 본문(수
    MB)이 캐시 칸을 차지하거나 크기만 보려고 회차마다 풀리지 않게(2026-11-03 마지막 검토 C6).
