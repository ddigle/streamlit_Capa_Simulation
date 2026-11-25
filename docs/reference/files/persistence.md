# AGENTS 3장 — 파일별 책임 > 영속성 모듈

### 영속성 모듈

- `src/capa_simulation/persistence/snapshot_export.py` — DuckDB 스냅샷 내보내기와 받은 스냅샷 검증·설치. 앱을 끈 자리는 `ATTACH` + `_sql_helpers.copy_database()` 다
  (구조는 `COPY FROM DATABASE … (SCHEMA)`, 데이터는 외래 키 부모 표부터 — `scripts/compact_duckdb.py` 와 같은 길). 앱 안에서는 쓰기 잠금 · CHECKPOINT · stat 대조 아래서만 바이트로 읽는다(`checkpoint_copy` —
  COMMIT 이 `.wal` 에만 있을 수 있고, ATTACH 복사는 1GiB 안에서 앱과 함께 돌지 못한다). 라이브 파일은 닫지 않는 번호로 읽는다 — 열었다 닫으면 프로세스 잠금이 풀린다.
- `src/capa_simulation/persistence/sync_state.py` — DB 옆 `.sync.json` 사이드카에 미반영 변경 번호를, `sync_generation.json` 한 파일에 게시 상태(base · pending · 미게시 · 넘긴 표지)를 기록한다(DB
  안은 순환, 메모리는 죽으면 사라진다). `enable()` 전에는 파일을 만들지 않고 못 읽는 사이드카는 「변경 있음」 이다. 첫 미반영 시각 · 깨우기는 메모리다 — 일꾼이 멈춰도 그 값이 함께 멈추지 않게.
  - 미게시로 옮기는 것은 담은 저장이 있는 게시뿐이다. 답이 끊긴 펜스(`observed` 가 빔)는 미게시로 옮기지 않고 버린다(`object_sync_engine._park_pending`) — 옮기면 변경 없는 새 pod 가 「원격과 어긋남」 으로 머문다.
- `src/capa_simulation/persistence/repository.py` — `DuckDBScenarioRepository` 의 입력 검증·연결·쓰기 잠금·트랜잭션
  경계. 커밋과 변경 신호는 Repository 만 갖고 store 는 열린 연결을 받는다.
  - 교체 실패 시 행·버전을 복구하고 신호를 내지 않는다. 바뀐 것이 없는 쓰기(`initialize_global_display_order` 등)는
    트랜잭션을 열지 않는다. `load_revision_table` 은 확인·읽기를 한 트랜잭션에서 하고 없으면 `KeyError` 다.
  - `save_revision(..., skip_unchanged=True)`(화면 길만 — 자동 갱신·시험은 기본 False)는 쓰기 잠금 안에서 그 시나리오
    `active_revision_id`(최신) 리비전과 견줘 같으면 아무것도 쓰지 않고 `RevisionUnchanged(revision_no)` 다(개선 I5).
    견주기는 `_same_revision_content` — 프리셋(`_preset_key`: 포함 공정은 집합, 레거시 확보·경고는 9자리)·가상 제품 이력(행
    집합)을 먼저, 표 14 는 저장된 `reference_hash` 와 같으면 같고 다르면 그 리비전 표를 `rev_data` 에서 읽어 지문을 다시
    짓는다 — 등록 때 지문은 변환 직후의 형으로 지어 DB 를 오간 세션 표와 갈린다. 리비전명·메모는 보지 않는다.
  - `load_source_blank_cs_rows(scenario_id)` 는 등록 때 CS 가 비어 뺀 원천 행(`raw_data.core_data` 78칸 그대로, 원천 행 차례)을
    다시 읽는다 — 원천이 없는 시나리오(복제 · 월 머지 · 연도 Shift)는 None, 시나리오가 없으면 `KeyError`. SQL 공백 패턴
    (`SOURCE_BLANK_TEXT_PATTERN`)은 파이썬 `str.isspace` 집합과 같고, 그 위에 파생과 같은 식(`core_data_derivation.blank_cs_mask`)으로 한 번 더
    가른다 — 수가 등록 파생(`derive_q_core_data(...).blank_cs`)과 같다(`tests/test_revision_input_check.py`). 목록 관리 「점검」 이 쓴다.
  - Capa 시나리오 이름은 보관본까지 겹치지 못한다 — 쓰기 트랜잭션 안에서 앞뒤 공백을 뗀 완전 일치로 막고(`DUPLICATE_SCENARIO_NAME_MESSAGE` — 이름 수정은 자기 자신을 빼고, 목록 「변경 저장」 은 이 저장이 끝난 뒤의 이름끼리 같은 규칙으로 견준다), 이 규칙 전 DB 에 같은 이름이 남아 있을 수 있어 DB UNIQUE 제약은 걸지 않는다.
- `src/capa_simulation/persistence/advance_load_store.py` — 공용 선행 B/O 프로필(`0018`)의 조회·교체 SQL.
- `src/capa_simulation/persistence/advance_shipment_store.py` — 공용 선행 입고 실적 프로필(`0031`)의 조회·교체 SQL.
- `src/capa_simulation/persistence/securement_threshold_store.py` — 공용 확보율 판정 기준 프로필(`0029`)의 조회·교체
  SQL과 버전 대조(`SecurementThresholdConflict`). 미저장일 때의 기본값은 Repository 가 정한다.
- `src/capa_simulation/persistence/auto_official_update_store.py` — 공식버전 자동 갱신(`0035`)의 설정(버전 대조)·변경
  기록·실행 기록·자동 off 기록 SQL. `run_key` 유일이 회차 선점이고, 소유 컬럼이 없어 시나리오를 지워도 남는다.
- `src/capa_simulation/persistence/extra_process_store.py` — 부대공정 판(`0037`)의 판 내용(sha256 키 · ZIP 바이트 한 벌) · 판 이력
  (넣기만 — 마지막 줄이 지금 상태, 화면이 본 마지막 차례와 대조 `ExtraProcessMoved`) · 데이터셋 출처(같은 (공정, 판 차례)는 앞
  줄만) · S3 Drive 쓰기 기록(`0038` — 넣기만, `append_write`) SQL. 판 이력 · 내용 · 쓰기 기록 표는 소유 칸이 없어 시나리오를
  지워도 남고, 출처 표는 `dataset_id` 소유라 함께 지워진다.
- `src/capa_simulation/persistence/route_load_exception_store.py` — 공정별 부하 산출 예외 선언 판 이력(`0040`)의 읽기 · 넣기 SQL.
  넣기만 하고 마지막 줄이 지금 선언이다(모두 뺀 저장도 비움 판 한 줄). 쓰기는 검증(계산 쪽 정규화 — 모르는 산식 id · 빈 공정
  이름은 표에 들지 않음) → 화면이 본 판 차례 대조(`RouteLoadExceptionMoved`) → 견줌 키 지문 대조(같으면
  `RouteLoadExceptionUnchanged` — 쓰지 않음) 차례다. 읽기는 표가 없으면 `None` 이다(확인 스크립트가 여는 `0040` 전 사본 — 표를
  만들지 않는다). 소유 칸이 없어 시나리오를 지워도 남는다. 저장소 쓰기(`append_route_load_exceptions`)는 `admin.area` 벽 뒤이고
  COMMIT 뒤에 바로 올림(`sync_state.request_upload`)을 청한다 — 공식 발행과 같은 까닭(리비전 없이 모든 시나리오의 숫자를
  바꾸는 쓰기라 모아 올리는 창 안에서 운영 서버가 다시 떠도 되돌아가지 않게). 감사 `admin_route_load_exception` 은 판 차례 ·
  공정 수만 싣는다. 계산은 이 판을 공용 프로필 · 저장소 · 사본 연결로 읽어 넘긴다(5장 45). 확인 스크립트가 선언 표 없는 사본에
  찍는 표지는 `BEFORE_ROUTE_EXCEPTION_COPY`(`사본 0040 전`)다.
- `src/capa_simulation/persistence/key_process_store.py` — 공용 주요공정 프리셋 프로필(`0024`·`0028`)의 조회·교체 SQL.
  맨 앞 프리셋이 기본, 공정 차례가 행 순서다.
- `src/capa_simulation/persistence/home_profile_store.py` — HOME 공용 Top5 구간·Capa 요약·GAP 비교 대상(`0020`)·주요
  Case(`0036`)의 조회·교체·해제 SQL.
  - 주요 Case 는 한 행에 Case 마다 칸 둘(`case1_scenario_id`…)이다. 칸 이름이 `scenario_id` 가 아니라 `_owned_tables`
    자동 발견에 걸리지 않고, 보관·영구 삭제는 그 시나리오를 가리키는 Case 만 비우며 출처 칸에 까닭을 적는다
    (`clear_global_main_cases` — 「Case2 지정 비움 — 시나리오 보관」). 가리키는 시나리오·리비전의 이름 바꾸기는
    version 만 올린다(`touch_global_main_cases`·`touch_global_main_cases_revision` — 슬롯 글자가 둘 다 싣는다). Case
    하나 교체는 다른 Case 를 같은 트랜잭션에서 옮겨 적는다.
- `src/capa_simulation/persistence/shortening_baseline_store.py` — 필요 단축 일정 기준선(설비 DB `0021`)의
  넣기·목록·읽기·지우기 SQL(UPDATE 없음)과 칸 매핑(`BASELINE_UNIT_DB_COLUMNS`). 설비 쪽 출처 칸 넷(`0027` —
  `equipment_schedule_revision_ref`·`_no`·`equipment_scenario_name`·`equipment_release_no`)은 가리키기만 한다.
- `src/capa_simulation/persistence/shortening_progress_log_store.py` — 필요 단축 일정 누적 진척(설비 DB `0036`)의 읽기와 주 한 줄
  넣기 · 고치기 · 지우기, 목표 머리 갈아 쓰기 SQL. 저장소 메서드(`save_shortening_progress_entry` · `delete_shortening_progress_entry` ·
  `save_shortening_progress_goal`)가 쓰기 잠금 안에서 화면이 본 값 · version 과 대조하고 감사 사건(`data_progress_log_save` ·
  `data_progress_log_delete` · `data_progress_goal_save`)을 단다. 캐시는 `equipment_cache.load_shortening_progress_log`(DB stat ·
  쓰기 세대 `shortening_progress` · TTL — 입력 비가동과 같은 꼴).
- `src/capa_simulation/persistence/shortening_progress_snapshot_store.py` — 누적 진척 넣기 스냅숏(설비 DB `0037` — 머리 · 범위
  공정 · 호기 세 표)의 읽기 · 갈아 쓰기 · 지우기 SQL. 쓰기는 저장소 `save_shortening_progress_entry(…, snapshot=)` 가 기록 줄을 쓴
  **같은 트랜잭션**에서 부르고(대조에서 지면 둘 다 안 씀) 머리의 `log_updated_at` 은 그 기록 줄 `updated_at` 을 SQL 로 옮겨 적는다 —
  읽기는 그 값이 지금 기록 줄과 같은 머리만이다. 갈아 쓰기는 새 `snapshot_id`(머리 제자리 · 새 자식 넣고 옛 자식 지움), 같은 수 ·
  같은 구성 글이면 쓰지 않고 같은 수 · 다른 구성이면 스냅숏만 갈아 쓴다. 넣기 없이 고친 저장은 고치기 전 기록과 함께 쓴 스냅숏을
  새 기록 시각으로 옮기고(`carry_progress_snapshot` — 그 차이는 까닭 「손 고침」) 그 밖의 머리는 지운다. 기록 지우기는 같은
  트랜잭션에서 셋 다 지운다(`delete_progress_snapshot`). 캐시는 `equipment_cache.load_shortening_progress_snapshots`(기록과 같은 쓰기
  세대 `shortening_progress` — `clear_shortening_progress_cache` 가 함께 비움)이고, 띠는 그 위에서 센 까닭 캐시
  `load_shortening_progress_reasons`(같은 세대 — 「주차별」 을 편 띠만 부름)만 부른다. 감사 사건은 기록 저장 그대로
  (`data_progress_log_save` — 호기 표 · 값 원문은 싣지 않는다).
- `src/capa_simulation/persistence/floor_state_store.py` — Space 동·층 사용 상태(설비 DB `0029` — 머리
  `floor_state_profile`, 층 `floor_state` 행 = 비활성 층·PK (동, 층))의 읽기·쓰기 SQL. 쓰기는 같은 트랜잭션에서 읽은 저장본과
  견줘 **바뀐 층만** 고친다(다시 켠 층 DELETE · 사유만 바꾼 층 키 아닌 칸 UPDATE · 새로 끈 층 INSERT — 같은 키를 지웠다 넣지
  않는다). 읽기는 30개 층 밖 행을 버리고 머리 없는 층 행은 version 0 으로 싣고 빈 사유는 `UNUSED` 로 읽는다(DB 행은
  고치지 않는다 — 같은 내용 저장은 쓰지 않는다).
- `src/capa_simulation/persistence/manual_downtime_store.py` — 입력 비가동대수(설비 DB `0032` — 머리
  `manual_downtime_profile`, 칸 `manual_downtime` 행 = 0 아닌 (공정, 달)·PK (공정, 달), 이력 `manual_downtime_save`)의 읽기·쓰기 SQL.
  쓰기는 층 사용과 같은 꼴로 **바뀐 칸만** 고치고(비운 칸 DELETE · 값만 바꾼 칸 UPDATE · 새 칸 INSERT) 머리를 다음 version 으로 쓴 뒤
  이력 한 행(바뀐 칸 수·채운 칸 수·대수 합·저장자·메모)을 더한다. 버전 대조·같은 내용이면 쓰지 않기는 저장소
  (`save_manual_downtime`)가 쓰기 잠금 안에서 한다.
- `src/capa_simulation/persistence/equipment_scenario_store.py` — 설비 DB `0027` 의 새 표 여섯(설비 시나리오·일정 리비전·일정
  스냅샷·일정 비가동 스냅샷·공식 발행·이관 경계)의 SQL. 열린 연결만 받고 트랜잭션·신호는 저장소 몫이다. 시나리오 칸 DB 매핑
  `SCENARIO_SCHEDULE_DB_COLUMNS`, 이관 시나리오 id `OPERATIONS_SCENARIO_ID`(`'operations'`), 「시나리오의 최신」 은 칸이 아니라
  `MAX(revision_no)` 다. 차례는 늘 `revision_no`·`release_no`·`boundary_no` 로 정하고 `created_at` 으로 정하지 않는다(한
  트랜잭션의 행은 시각이 같다). 옛 배포 흔적 수(`legacy_trace_count`)는 「마지막 경계 행의 `through_revision_no` 뒤 계약 v3
  이하 공통 리비전」 이다.
  - 배치 차이 세 표(설비 `0031`)도 여기다 — 일정 리비전을 넣을 때(`insert_schedule_revision(layout=)` — 기본값 없음) 지문
    `layout_hash` 와 함께 넣고(빈 차이도), `layout_overlay` 가 읽는다. 리비전 투영은 지문과 원시 행 수 셋, 시나리오 목록은 최신의
    원시 호기 차이 행 수·지문·**옛 코드 흔적 수**(차이가 있는 리비전보다 번호가 큰데 지문이 NULL 인 리비전 — 0031 을 모르는
    코드가 저장해 배치안이 빠졌다)를 낸다. `layout_marks_outside` 는 캔버스를 줄일 때 가정 요소를 센다. 일정 리비전 내용 표
    (일정·비가동·배치 차이 셋)에는 **UPDATE·DELETE 가 없다**(I1 — 시험이 소스를 훑는다). 그 소유 표 목록은
    `SCHEDULE_REVISION_OWNED_TABLES`(시험이 `information_schema` 와 견준다).
- `src/capa_simulation/persistence/past_data_store.py` — 공용 과거 구간 프로필 세 표의 조회·교체 SQL.
- `src/capa_simulation/persistence/preset_store.py` — `scenario_preset.preset_hash` 는 읽는 곳 없이 쓰기만 하는 해시지만 append-only 리비전의 감사값이라 칸 · 쓰기를 걷지 않는다.
- `src/capa_simulation/persistence/summaries.py` — 조회 행을 요약 모델로 바꾸고, 요약 SELECT 투영
  (`SCENARIO_SUMMARY_SELECT` 등)을 매퍼 옆에 두어 열 순서와 row 인덱스가 짝을 이룬다.
- `src/capa_simulation/persistence/_sql_helpers.py` — 프레임 저장·조회·값 변환과 트랜잭션 경계 공용 헬퍼. 두 Repository
  와 `_migration_core` 가 `transaction()` 한 벌을 쓰고, 공용 프로필 버전 대조 `require_profile_version()`
  (`ProfileVersionConflict` — 기본 스키마 `app_meta`, 설비 DB 층 사용 상태는 `schema="equipment_ops"`)과 감사 해시 `hash_frame()`(`tests/test_sql_helpers.py`)이 여기 있다. DB 통째 복사
  `copy_database()`(외래 키 부모 표부터)도 여기 있어 스냅샷 내보내기와 `scripts/compact_duckdb.py` 가 함께 쓴다.
  연결 설정 `DUCKDB_CONNECT_CONFIG` 는 한 벌(블록 16KiB + 메모리 한도 칸 — 아래 `duckdb_memory.py`)이고 두 DB 가 함께 쓴다 — 같은 파일의
  연결은 설정이 모두 같아야 해서 환경변수는 import 때 한 번만 읽는다. 가장 바깥 `pinned_connections` 블록이 핀을 닫기 직전에 그 핀으로
  DB 메모리 표본을 읽는다(`duckdb_memory.observe` — 새 연결을 열지 않는다).
- `src/capa_simulation/persistence/duckdb_memory.py` — DuckDB 메모리 한도 칸과 회차 끝 메모리 표본. 환경변수 `CAPA_DUCKDB_MEMORY_LIMIT`
  (사내 리뷰 202611162130 사외요청 3)가 없거나 비면 연결 설정에 넣지 않는다 — DuckDB 기본(보이는 메모리의 80%) 그대로다. 값은 사용자가
  정하고 코드 · 이미지에 기본값을 두지 않는다(`docker/Dockerfile-prod` 에 `ENV` 없음). 꼴은 수 + 단위(`KB` · `MB` · `GB` · `TB` ·
  `KiB` · `MiB` · `GiB` · `TiB`, 대소문자 · 띄어 씀 상관없음 — 수는 ASCII 숫자만, 값 전체가 ASCII. 전각 · 아라비아 숫자는 `float` 이 읽어도
  DuckDB 가 거절해 모든 연결이 실패하고 `boot-pull` 이 정상 스냅샷을 깨짐으로 내친다. 이 꼴은 DuckDB 가 받는 꼴의 부분이라 import 때 DuckDB 로
  시험하지 않는다 — `tests/test_duckdb_memory.py` 가 단위마다 연다. 판정은 import 때 돌아 끝없이 긴 수(무한대 — 범위 밖)에도 예외를 내지
  않는다)이고 받는 범위는 64MiB ~ 1TiB 다 — 권하는 값이 아니라 울타리다(너무 작으면
  DuckDB 가 첫 표에서 메모리 부족으로 멈춰 모든 DB 열기가 실패하고, 너무 크면 DuckDB 가 거절한다). 틀린 값은 넣지 않고 「서버 시작 점검」
  「DuckDB 메모리 한도」 줄 「실패」 · `AD-01` 이 알린다. 한도는 DB 파일(인스턴스)마다 같은 값이라 두 DB 합은 그 두 배까지 가고, 같은
  `connect()` 로 잠깐 여는 사본(동기화의 받은 사본 확인 · 스냅샷 짓기)도 같은 한도를 쓴다 — 따로 두지
  않은 것은 `connect()` 가 경로만 받는 한 곳이라 DB 를 가르려면 그 경계에 DB 종류를 들여야 하고, 설비 DB 는 작아 한도에 닿을 일이
  드물어서다. 한도를 넘는 질의의 넘침은 DuckDB 기본 `temp_directory`(DB 파일 옆 `<DB 파일>.tmp` — `.gitignore` 의 `*.tmp`) 다. 표본은
  `pinned_connections` 가 핀을 닫기 직전 그 핀으로 `duckdb_memory()` 를 읽어 DB 마다 마지막 · 최고 · 임시 파일 최고와 DuckDB 가 실제로
  쓰는 한도(DB 마다 처음 한 번)를 프로세스 메모리에 모은다(회차당 0.2ms 안팎 — 샘플 관측). 이 앱은 회차가 끝나면 인스턴스가 내려가
  아무 때나 재면 거의 늘 0 이라 회차 끝을 잰다 — 질의 중 순간 최고는 잡지 못한다. Streamlit 을 import 하지 않는다.
  시험 `tests/test_duckdb_memory.py`.
  리비전 · 데이터셋 표를 읽는 `load_frame()` 은 `fetchdf` 바로 뒤에 글자 칸의 같은 글을 한 객체로 모은다(`share_repeated_text` —
  비지 않은 값이 모두 정확히 `str` 인 객체 칸만, 그 읽기 동안만 쓰는 사전, 객체 블록에 제자리로 써 값 · dtype · 블록 꼴 · 빈 칸 ·
  해시가 그대로다. 숫자 · 참거짓 · `str` 하위형(`np.str_` 등)이 섞인 칸은 건드리지 않는다 — `1` · `1.0` · `True` 나 같은 글의
  `str` · `np.str_` 가 합쳐지면 `equals` 가 못 잡는다). 기본 켬이고
  환경변수 `CAPA_SHARE_STRINGS=off` 로 끈다(`settings.share_strings_enabled`). 실제로 모았는지(고유 객체 수 = 고유 값 수)는
  `tests/test_share_repeated_text.py` 가 DuckDB 읽기 길로 잠근다 — pandas 판이 바뀌어 칸이 쓸 수 있는 view 가 아니게 되면 값은
  맞은 채 효과만 사라진다.
- `src/capa_simulation/persistence/_migration_core.py` — 두 DuckDB 가 함께 쓰는 마이그레이션 적용 엔진(버전 순
  읽기·체크섬 대조·건별 트랜잭션).
  - 다시 해도 같은 실패는 `MigrationFailed`(`RuntimeError`)다 — 이미 적용된 파일이 바뀜(`MigrationChanged`)과, 새 SQL 이
    SQL · 데이터 오류(`_SQL_FAILURES` — 구문 · 표 · 제약 · 변환, 원래 오류는 `__cause__`)로 실패해 그 건을 되돌림. 입출력 ·
    메모리 · 트랜잭션 충돌은 감싸지 않는다. 앱 시작 실패 판(`components/boot_stop.py`)이 이 종류로 「다시 시도」 없는 갈래를 가른다.
  - DB 가 코드보다 새 것이면(옛 배포 ZIP 으로 되돌림) 막지 않고 `MigrationOutcome.schema_ahead`(`SchemaAheadOfCode`)로
    알린다. 최고 번호끼리만 견주어 결번 2·3 은 알리지 않는다. 화면 상태 알림(`page_bootstrap.render_schema_ahead_warning`)은
    시뮬레이션 DB 는 `app.py`(`GL-02`), 설비 DB 는 그 DB 를 여는 화면(`GL-06`)이 낸다.
- `src/capa_simulation/persistence/migration_runner.py`, `equipment_migration_runner.py` — 각 DB 를 엔진에 묶는 진입점.
- `src/capa_simulation/persistence/cache.py`, `equipment_cache.py` — 불변 리비전 스냅샷·공용 프로필 열세 종(부하 예외 선언 포함)과 설비
  스냅샷·층/FAB 도면·설비 마스터 탭 이력·필요 단축 일정 조건·기준선의 Streamlit 캐시 경계.
  - 키는 불변 id 나 DB 경로이고 저장 길이 맞는 `clear_*` 를 부른다(판정 기준은 공식버전 지정 때도,
    `clear_floor_layout_cache` 는 층과 FAB 를 함께).
  - 비교 시나리오의 리비전 id 목록(`scenario_has_revision` — HOME GAP 회차의 비교 짝 확인)은 비교 대상 프로필 · 후보 목록과 같은
    쓰기 세대 `"comparison_scenario"` 로 캐시한다. 리비전은 append-only 이고 목록에서 빠지는 길은 시나리오 보관 · 영구 삭제뿐인데
    둘 다 그 세대를 올린다(`clear_global_comparison_scenario_cache` 가 그 칸도 비운다). 새로 저장한 리비전(사이드바 저장 · 자동 갱신
    스레드 · 다른 세션)은 세대를 올리지 않으므로 목록에 없으면 DB 로 한 번 더 본다 — 「아니다」 는 늘 지금 DB 의 답이다.
  - 목록 관리 「점검」 은 이 경계의 칸을 쓰지 않는다 — 고른 리비전의 스냅샷(공용 표시순서를 얹지 않은 것)과 등록 때 CS 가 비어 뺀
    원천 행은 저장소에서 캐시 없이 읽고(`get_scenario_repository(...).load_revision(..., apply_global_display_order=False)` ·
    `load_source_blank_cs_rows`), 캐시는 요약 칸 하나다(5장 39 — 2026-11-11 검토 보드 F6 (나)).
  - 「지금 저장된 값」 읽기(`latest_equipment_revision_id`·`load_process_cutoff`·`load_standard_target_availability`·
    `load_floor_states`·`load_manual_downtime`·`load_manual_downtime_saves`)는 (DB 경로, DB·WAL stat, 쓰기 세대) 키에 TTL 15초다.
    입력 비가동(`0032`, 세대 `"manual_downtime"`)은 가용설비 현황 Preference 저장이 `clear_manual_downtime_cache()` 로 비운다 — 계산
    캐시는 프로필이 아니라 칸 자체를 키에 싣는다(5장 34). 층 사용 상태(`0029`, 세대 `"floor_state"`)는
    다른 PC·동기화로 받은 DB 의 변경도 회차 안에 보여야 하는 공용 설정이라 이 꼴이고, 도면 캐시와 묶지 않는다 — 저장 길(Space
    층 목록 저장 콜백)이 `clear_floor_state_cache()` 를 부르고 `clear_equipment_repository()` 도 부른다. 1차 장치는 비우기라 새 쓰기 길을 더하면 같은 비우기를 부른다.
  - 설비 쪽은 **리비전 내용(불변)과 바뀔 수 있는 것**을 나눈다. 합친 본문 `_load_merged_payload`(공개
    `load_merged_equipment_snapshot`)는 (DB, 공통 id, 일정 id) **쌍 키**에 세대가 없다(`MERGED_SNAPSHOT_CACHE_ENTRIES` 16칸).
    설비 시나리오 목록(`load_equipment_scenario_catalog` — 시나리오·각 최신·리비전 수·최신 발행·흔적 수)과 시나리오 리비전
    목록(`load_equipment_schedule_revisions` — 그 시나리오 리비전 전부, 같은 칸에 같은 줄에서 센 출처별 수
    `load_equipment_schedule_revision_counts` 를 함께 실어 표와 그 아래 「전체 N줄」 이 함께 갈린다. 팝업 라디오의 최근
    `SCHEDULE_REVISION_LIST_LIMIT` 개는 `load_recent_equipment_schedule_revisions` 가 같은 칸에서 자른다)은 (DB, stat, 세대
    `"equipment_scenario"`) 키에 TTL 15초, 8칸이다. 공식 스냅샷
    (`load_official_equipment_snapshot`)은 공통 최신 id + 목록의 최신 발행 → 합친 본문이라 발행만 바뀌어도 다른 쌍 키로 간다.
    CSV 바이트도 쌍 키다. 이름·리비전명·발행·복제·되돌리기·이어 쓰기 뒤에는 `clear_equipment_scenario_cache()` 만, 설비 마스터
    저장 뒤에는 `clear_equipment_snapshot_cache()`(앞의 것까지 부른다) — 호출부가 비운다. Space 층 사용 끄기 확인의 덧줄
    재료 `load_layout_overlay_floor_counts`(층마다 — ACTIVE 가정 시나리오 최신의 그 층 차이 호기 행 수)도 목록과 같은 세 장치(세대 `"equipment_scenario"`·stat·TTL)이고, 층
    배치 편집 「캔버스」 칸의 하한 재료 `load_layout_overlay_extent`(층마다 — 캔버스 저장이 보는 리비전의 차이 요소 범위·차이 호기 상자,
    S4 — 캔버스를 고치는 공식 세션 회차에만 읽는다)는 그 세 장치에 층 현행값 세대 `"floor_layout"` 을 더한다. 공식 발행 확인의 배치 판정 `load_layout_publish_preview`(S4 —
    (DB, 공통 최신 id, 발행할 리비전, 그 시나리오 최신) 불변 id 셋 + 층 현행값 세대)는 저장소 `preview_layout_publish` 가
    발행 쓰기와 같은 판정(`_layout_publish_preview`)을 쓰지 않고 낸 값이다.
  - **가정 배치 차이(설비 0031)도 리비전 내용이라 불변이다.** 호기 차이는 합친 본문이 이미 얹어 싣는다(`_MergedSnapshotPayload`
    에 공식 일곱 칸·버린 차이 수·다시 맞춘 묶음 — 시험이 `EquipmentSnapshot` 모든 필드의 왕복을 본다). 도면 요소·Main 설비명
    위치 차이는 (DB, 일정 id) 하나를 키로 한 칸 `load_schedule_layout_overlay`(`_load_schedule_layout_payload`, 16칸, 세대 없음 —
    기본형 payload 를 싣고 꺼낼 때 지금 클래스)가 들고, 그림은 「공식 층 현행값(쓰기 세대) ⊕ 그 차이」 를 회차마다 합친다(쓰기
    세대 종류는 늘지 않는다). `clear_equipment_snapshot_cache()` 가 그 칸도 비운다.
  - **리비전명은 바뀔 수 있는 이름표라 불변 본문에 싣지 않는다**(E7 — 5장 8). 합친 본문의 `schedule.revision_name` 은 늘 None
    으로 꺼내고, 이름은 리비전 목록 캐시(쓰기 세대 `"equipment_scenario"`·stat·TTL)에서만 읽는다(글자는
    `equipment_data_workspace.schedule_revision_title`). 되돌리기 확인 재료(`load_schedule_restore_preview`)는 (DB, 공통 id, 그 시나리오 최신 id, 고른 id)
    에 층 현행값 쓰기 세대 `"floor_layout"` 만 더한다 — 셋 다 내용이 불변이고 누가 저장하면 화면이 새 id 로 부르며, 되돌리기가 쓸
    배치 차이의 정규화만 층 현행값을 본다(공식 발행 확인 `load_layout_publish_preview` 와 같다).
  - **어느 캐시도 저장소의 호환 래퍼(`save_snapshot`·`save_space_layout`·`load_snapshot`)를 부르지 않는다** — 래퍼
    `load_snapshot` 은 발행에 따라 값이 바뀌는 뜻이라 공통 id 하나 키에 실으면 발행 뒤 낡은 값을 낸다. 시험이
    `app_pages/`·`components/`·이 파일을 훑는다(`tests/test_equipment_current_reads.py`).
- `src/capa_simulation/persistence/equipment_repository.py` — 설비 운영 세 표의 불변 스냅샷(공통 대장 리비전 + 설비 시나리오
  일정 리비전)과 Space 층·FAB 도면, 필요 단축 일정 조건·기준선 저장소.
  - **읽기 셋**은 연결을 받는 모듈 함수다 — 저장소 메서드와 읽기 전용 연결을 여는 `scripts/inspect_real_data_checks.py` 가
    같은 함수를 써서 합치기 규칙이 두 벌이 되지 않는다. `read_common`(공통 32칸 + 키, 일정 칸이 아예 없음)·`read_schedule`
    (키별 일곱 칸·비가동 — 이관 리비전은 옛 행을 읽기 투영·레거시 변환째)·`read_merged`(합친 39칸 스냅샷, 같은 레거시
    리비전이면 한 번만 읽음, 끝에 읽기 검증 — 실패는 `EquipmentScenarioIncompatible`)·`read_official_pair`(공통 최신, 최신
    발행 일정 리비전)·`legacy_trace_count`·`read_layout_overlay`(그 리비전의 배치 차이 — None·이관·지문 NULL·빈 지문이면 질의
    없이 빈 차이). `read_merged` 는 합친 **뒤, 읽기 검증 앞**에 호기 배치 차이를 얹는다(`apply_unit_overlay`, 실패 까닭에 「배치
    차이를 얹은 뒤」). 옛 `_read_snapshot` 은 `_read_legacy_snapshot` 이고 계약 v4 를 받으면 `ValueError` 다. 모델은 캐시에
    실리므로 필드에 기본값을 두고 `Mapping` 대신 쌍 튜플(`unit_key_pairs`·`layout_official_places`)·`frozenset` 을 쓴다.
    계약 v3 미만(v1 · v2) 옛 리비전을 읽는 길(`_legacy_snapshot` 의 `_load_legacy_equipment` · `_load_legacy_schedule` · `_load_legacy_downtime`)은 사내 설비 DB 의 리비전별 계약 판 수를 확인하기 전에는 걷지 않는다 — 그 수는 사내 DB 를 여는 확인이라 사용자가 별도 창에서 돌린 결과로만 받는다.
  - **저장은 `save_equipment(EquipmentSaveRequest)` 하나다**(연결 하나·트랜잭션 하나, 모든 쓰기가 `_write_transaction`).
    메모리에서 막기(옛 배포 흔적 → `EquipmentLegacyTraceError`, 공통 최신 ≠ 출발 공통 → `EquipmentRevisionConflict`, 일정을
    쓰는데 시나리오 최신 ≠ 출발 일정 → 같은 예외 `side`)·검증·호기 키·나누기·바뀐 쪽 가르기·함께 넣기·교차 검증·발행을 모두
    정한 뒤 쓴다. 바뀐 쪽만 쓰고 둘 다 그대로면 리비전을 만들지 않는다(`wrote=False`). 예외 하나 — 공통 최신이 계약 v3
    이하인 동안의 첫 저장은 공통이 그대로여도 v4 공통 한 벌을 함께 쓴다(`forced_common`, 옛 ZIP 으로 되돌리면 「빈 설비」 로
    드러나게). 출발 두 리비전은 잠금 안에서 다시 읽는다(불변이라 화면이 든 값과 같다).
  - **배치는 역할로 가른다**(설비 `0031`, 설비 시나리오 2단계 S2 — 설계 6장). 역할 = 쓰기 잠금 안에서 대상이 공식 설비
    시나리오인가. **공식**이면 위치는 공통 대장에(편집에서 바뀐 호기만), 도면 요소·Main 설비명 위치·캔버스는 층 현행값에 쓰고
    차이는 비운다(I2) — 그 시나리오가 가정이던 때의 차이가 있는 옛 리비전에서 배치·요소를 고치면 `EquipmentLayoutScopeError`
    (공통 칸 저장은 받고 그 리비전의 가정 자리가 공식으로 새지 않는다). **가정**이면 공통 쪽 배치는 공식 그대로이고(새 호기는
    자리 없이 크기·레이아웃표시만 — 있는 묶음의 새 모듈은 그 묶음 공식 동·층, Q1), 위치·요소·이름표는 그 시나리오 새 일정
    리비전의 **배치 차이**다(요소·이름표는 편집기가 낸 합친 전체를 그 층 공식과 견준 차이). 가정 대상의 캔버스·공식 층이 다른
    호기를 한 묶음으로 묶기는 `EquipmentLayoutScopeError`. 층 대조의 기대 지문은 「공식 현행 ⊕ 출발 리비전의 차이」 다.
    일정도 차이도 그대로면 쓰지 않는다. 공통이 바뀌었는지는 공식 배치를 둔 저장본(`_BaseState.official_common`)과 견준다.
  - **배치 빨리 감기**: 가정 배치만 바꾼 저장(일정·비가동은 출발과 같음)은 그 시나리오 최신의 배치 지문이 출발과 같으면 낡아도
    최신의 일정·비가동 위에 새 리비전으로 받는다 — 남의 일정 저장·함께 넣기가 배치 편집을 막지 않는다. 남이 배치를 바꿨으면
    지금처럼 `EquipmentRevisionConflict`. **끝 확인**: 가정 리비전을 쓴 저장은 커밋 전에 그 쌍을 `read_merged` 로 다시 읽고
    실패하면 `EquipmentScenarioGuardError`(까닭 「배치 차이를 얹으면 …」)로 통째로 되돌린다(I4).
  - **역할 대조**: `expected_layout_role`(배치 편집이 들어갈 역할, None 이면 배치를 건드리지 않은 저장 — S2 화면은 배치 편집이
    든 저장에 "official", 3장 `equipment_data_workspace`)이 잠금 안의 역할과 다르면 `EquipmentLayoutRoleChanged`. 공통 쪽에
    공식 값을 다시 둘 때는 견줄 꼴(`Place` — 소수 첫째 자리)이 아니라 공통 대장의 원래 칸 값을 옮긴다(`common_with_places(
    official=layout_cells(...))`, `_BaseState.official_common` 도 `read_common` 의 원래 값) — 가정 배치 저장이 공식 좌표를 반올림해
    공통 리비전을 만들지 않게. 도면 요소 차이는 정해진 차례(공식 id 는 공식 차례 → 새 요소 — `mark_changes`)라 편집기가 낸
    차례와 다시 합친 차례가 같은 지문을 내 배치 빨리 감기가 선다. **Main 설비 이름 바꾸기**(`group_renames` — 지금 → 저장본)는 어느 역할이든 공식
    Main 설비명 위치 행(층 현행값)의 옛 이름 키를 새 이름으로 옮긴다(설계 5-4 — 정체성을 따라가는 것이라).
  - **교차 검증**: 공통을 쓰거나 함께 넣기가 있으면 모든 시나리오(자기 포함)의 「이번 저장 뒤 최신」 과 최신 공식 발행을 새
    공통과 합쳐 읽기 검증을 돈다 — 실패는 `EquipmentScenarioGuardError`(어느 시나리오·rN·규칙과 빠져나갈 길). 그래서 각
    시나리오 최신과 최신 발행은 늘 합쳐진다. 합칠 때 각 리비전의 배치 차이(함께 넣기는 계획이 옮길 정규화한 차이)를 얹은
    **뒤** 검증한다(`_require_mergeable(overlay=)`). 함께 넣기는 받는 시나리오 최신의 차이를 이 저장 뒤 공식으로 정규화해
    그대로 옮긴다.
  - **발행**: 공식 시나리오에 새 일정 리비전이 생겼고(자기 저장이든 함께 넣기든) 저장 전 공식 = 그 시나리오 최신일 때만
    `publish_official` 이면 그 리비전을 발행한다. 남의 미발행 더 새 리비전이 있으면 발행하지 않고 `release_withheld`. 발행이
    없으면(빈 DB) 이 저장의 일정 리비전이 공식 v1 이다. `expected_release_no` 가 다르면 `EquipmentReleaseMoved`.
  - **배치 차이가 있으면 공식으로 발행하지 않는다**(LY5 「공식으로 올리기」 전까지 — Q4, I2 는 저장된 행 기준).
    `publish_equipment_release` 는 발행할 리비전과 그 시나리오 최신의 차이를 지금 공식으로 정규화해 — 저장된 행이 둘 다 없으면
    발행, 행은 있지만 정규화하면 비고 발행할 리비전이 최신이면 차이를 비운 `origin='layout_clear'` 리비전(메모 「공식과 같아진
    배치 차이 정리」)을 써서 **그것을** 발행(돌려준 발행의 리비전 id 가 그 새 리비전), 그 밖은 `EquipmentLayoutPublishBlocked`
    (실효 호기·요소·이름표 수와 빠져나갈 길 — 「배치 차이 모두 지우기」·「여기서 새 시나리오」). 저장·되돌리기의 자동 발행도
    발행할 리비전에 차이가 있으면 막는다(공식 시나리오는 차이가 없어 실제로는 발행이 없는 DB 의 첫 저장만). 「배치 차이 모두
    지우기」 는 `clear_layout_overlay`(그 시나리오 최신의 일정 그대로·차이만 비운 `layout_clear` 리비전, 지울 것이 없으면 None,
    낡음 대조는 저장과 같다). 판정은 `_layout_publish_preview` **한 곳**이다 — 발행 쓰기(`_layout_publishable`)와 확인 팝업의
    읽기(`preview_layout_publish(..., common_revision_id=, newest_schedule_revision_id=)` → `LayoutPublishPreview` action
    `publish`·`clean`·`blocked`, 저장된 행·`is_newest`·발행할 리비전과 그 시나리오 최신의 실효 수를 따로 — S4)가 같이 쓰고,
    막힘 글도 한 곳(`LayoutPublishPreview.block` → `layout_publish_blocked_words`)이라 발행 쓰기 거부(`EquipmentLayoutPublishBlocked(...,
    message=)`)가 확인 팝업과 같은 글을 낸다. 캔버스 검사·미리 보임이 보는 리비전도 한 곳
    (`_overlay_check_targets` — `_require_overlay_marks_fit`·`layout_overlay_extent` → `LayoutOverlayExtent`)이다. 목록 투영은
    최신의 저장된 요소·이름표 차이 행 수(`latest_layout_mark_count`·`latest_layout_label_count`)도 싣는다.
    공식 발행 정리로 쓰는 `layout_clear` 리비전의 저장자는 그 발행을 한 사람(`released_by`)이다.
  - 복제(`clone_equipment_scenario` — 출처는 그 시나리오의 **어느 일정 리비전이든**(E7 「여기서 새 시나리오」), SQL 사본이
    아니라 지금 공통과 합친 읽기 길로 읽은 일곱 칸·비가동을 새 두 표에, `origin='clone'`. 지금 공통과 합쳐지지 않는 옛 리비전은
    `EquipmentScenarioIncompatible`. 출처 리비전의 배치 차이도 지금 공식으로 정규화해 옮긴다)·이름(`rename_equipment_scenario` — 보관본까지 중복 금지(호기 이름처럼 대소문자·앞뒤 공백만 다른 이름도 같은
    이름 — `scenario_name_taken`, 복제도 같다. 제 이름의 대소문자만 바꾸기는 된다), `expected_name` 대조 →
    `EquipmentScenarioNameMoved`)·발행(`publish_equipment_release` — append-only)·이어 쓰기(`acknowledge_legacy_trace` — 흔적 수
    대조 뒤 경계 행 하나)가 1단계 관리 쓰기다.
    이미 대소문자 · 앞뒤 공백만 다르게 갈려 있는 두 설비 시나리오 이름은 그대로 두고 새로 만들거나 바꿀 때만 막는다(`scenario_name_taken`). 시뮬레이션 시나리오 이름은 이 규칙을 넓히지 않고 완전 일치로 가른다(`repository._require_unique_scenario_name`).
  - **E7 리비전 도구**: 리비전명(`rename_schedule_revision` — 이름표 한 칸만 UPDATE, 비우면 NULL, 비교 후 쓰기 →
    `EquipmentScheduleRevisionNameMoved`, 같은 이름이면 쓰지 않음 — 화면은 성공 대신 「바뀐 것이 없습니다」(개선 I5), 보관
    시나리오 거절)과 되돌리기(`restore_schedule_revision` —
    고른 리비전을 **지금 공통 대장**과 합친 일정·비가동으로 같은 시나리오에 새 리비전 `origin='restore'`, 메모 「rK 일정으로
    되돌림」. 옛 배포 흔적이면 `EquipmentLegacyTraceError`, 확인 때 본 공통 최신·시나리오 최신이 바뀌었으면
    `EquipmentRevisionConflict`, 지금 최신과 같으면 쓰지 않음(`schedule=None`), 발행은 저장과 같은 `_plan_publish`, 공통을 쓰지
    않아 교차 검증 없음). 되돌리기는 그 리비전의 **배치 차이**도 지금 공통·층 현행값으로 정규화해 되살린다 — 대상이 공식
    시나리오면 차이를 버린다(I2). 「쓸 것 없음」 은 확인 화면과 같은 `restore_writes_nothing(preview, official_scenario=)` —
    공식이면 일정·비가동만, 가정이면 **쓸 차이**(고른 리비전 차이를 지금 공통·층 현행값으로 정규화 — 그 뒤 지운 호기·공식과
    같아진 행이 빠진다)가 지금 최신 차이(같은 기준 정규화)와도 같을 때다(`restored_layout_same` — 원시 지문만 보면 지운 호기의
    차이를 「되살립니다」 라 하고 바뀐 것이 없는 리비전을 만들었다, E2E r2). 쓰기는 확인 재료와 같은 `_restore_preview` 가 낸
    정규화 차이를 그대로 쓴다. 확인 화면은 그 판정으로 단추를 세우고 확인 글을 정한
    역할을 `expected_layout_role` 로 넘긴다 — 잠금 안의 역할과 다르면 `EquipmentLayoutRoleChanged`(확인 글과 실제 쓰기가 갈리지
    않게). 확인 글·결과 글은 배치 차이를 되살리는지·버리는지를 한 줄로 적는다(`restore_layout_sentence` — 되살릴 수는 쓸 차이로, 빠지는 행이 있으면 그것도). 리비전명은 둘 다 앞뒤 공백을 뗀 뒤 `SCHEDULE_REVISION_NAME_MAX_CHARS`(40)자까지이고 넘으면 쓰기 전에
    `ValueError` 다(자르지 않는다 — 화면 칸 `max_chars` 도 이 수). 확인 재료는 `preview_schedule_restore`(읽기만 — 쓰기도 잠금
    안에서 같은 `_restore_preview` 로 다시 잰다). 「그 리비전 뒤에 공통 대장에 든 호기」 는 그 리비전이 함께 본
    공통(`common_revision_id`)에 키가 없는 호기다.
    보관한 시나리오에서는 되돌리기도 거절한다(리비전명과 같다). 옛 배포 흔적 · 확인 뒤 바뀜과 함께 쓰기 전에 막는다.
  - 옛 배포 흔적은 설비 마스터 저장과 되돌리기를 막는다(복제·이름·리비전명·발행은 막지 않는다). 이어 쓰기는 옛 배포 리비전이 ACTIVE
    시나리오마다의 최신·최신 공식 발행과 합쳐질 때만 쓴다(아니면 `EquipmentLegacyTraceUnmergeable` — 굳히면 그 일정을 다시 못
    읽는다). 탭은 `legacy_trace_review()`(흔적 수·빠지는 호기 수·합쳐지지 않는 까닭)로 확인 체크 글을 쓴다. 흔적이 공식과도
    합쳐지지 않는 동안 `resolve_equipment_session` 은 멈추지 않고 공통만 읽어 일정 없이 연다(`EquipmentSession.unmerged` — 공식
    발행 쌍이 아니고, 공식을 따로 읽는 자리(공정 Capa 상세 HOME 방문·가정 세션 미확인)는 `official_snapshot_for` 로 같은 한 벌을
    쓴다).
  - **비가동 「새 비가동」 판정**(`new_downtime_rows`): 이번 저장에서 같은 호기의 행이 사라졌거나 같은 (유형, 시작일) 이 다른
    호기에서 사라졌으면(지운 호기째 빠진 것은 빼고) 고침이라 퍼뜨리지 않는다 — 유형·시작일을 함께 고치거나 설비명만 옮긴 행이
    다른 시나리오에 겹친 공사로 남지 않게.
  - **붙여넣기 병합**(`services/equipment_csv._merge_by_keys`)은 같은 키 행을 제자리에서 바꾸고 새 키만 끝에 잇는다 — 행 차례가
    공통 대장 내용(`_common_digest`)이라 끝으로 옮기면 일정만 고친 붙여넣기가 공통 rN 까지 만들고 다른 세션의 미저장 편집을 버린다.
  - **발행이 하나도 없으면** 일정 리비전을 만드는 첫 저장이 `publish_official` 과 무관하게 공식 v1 이다(결과 알림이 「공식 v1 지정」 을 적는다).
  - **호환 래퍼**(시험·스크립트용 — 화면·캐시는 부르지 않는다): `save_snapshot`·`save_space_layout` 은 공식 시나리오에 늘
    공통 v4 와 일정 리비전을 함께 써 같은 트랜잭션에서 발행한다(래퍼만 쓰면 공통 rN 과 운영 일정 rN 이 같은 번호로 오른다).
    `load_snapshot(공통 id)` 은 그 공통을 `common_revision_id` 로 가진 공식 시나리오 일정 리비전 마지막 것과의 짝이고, 짝이
    없으면 최신 공식 발행 일정이다. `list_revisions()` 는 공통 대장 이력이고 v4 공통의 비가동 행 수는 0 이다(비가동은 일정
    리비전 요약이 센다).
  - 최신 리비전·캔버스·요소는 쓰기 잠금 안에서 읽고 출발 리비전·`floor_layout_bases`·FAB `base` 가 다르면 거부한다. 안 쓴
    저장은 dirty 를 세우지 않는다.
  - 층 Main 설비명 위치(`floor_layout_group_label`, `0025`)는 `floor_group_labels`(층마다 전체)로 같은 트랜잭션에 쓰고
    층 대조(`floor_layout_bases`)가 요소와 함께 본다. 영역 테두리 모양·이름표 정렬은 두 요소 표의 `border_style`·
    `label_align`(`0025`, 영역 아닌 요소는 NULL)이다. 요소 모양 값은 두 요소 표와 가정 차이 표의 `look_json`(`0033` — 정규 JSON
    글, 빈 글 ↔ NULL, 동선·발자국·베이·도형 아닌 요소는 NULL)이다. 도형의 채우기 색·빗금은 기존 `color_key`·`hatch` 칸이다.
  - 층 겹친 순서(`floor_layout_stack`, 설비 `0034` — 호기끼리 차례 · 호기 위로 올린 영역 · 도형)는 `floor_stacks`(층마다 전체 —
    호기는 **편집본 설비명** 꼴)로 같은 트랜잭션에 쓰고, 저장소가 같은 트랜잭션의 호기 키(`edit.unit_keys` — 새 호기 키 포함)로
    옮긴다. 키가 없는 설비명(그 사이 지운 호기)과 그 층 영역 · 도형이 아닌 올림은 쓰지 않고(읽을 때 건너뛰는 행이라 저장을 막지
    않는다), 요소를 갈아 끼우는 저장(`_replace_floor_marks`)은 지운 영역 · 도형의 올림 행을 걷는다. **공식 역할에서만** 받는다 —
    가정 역할이면 `EquipmentLayoutScopeError`(캔버스와 같은 자리), 공식이어도 가정이던 때의 배치 차이가 있는 층은 요소 · 위치와
    같이 거부한다. 층 대조(`floor_layout_bases`)의 지문(`floor_layout_fingerprint`)이 순서를 셋째 값(저장 꼴 — 호기 키)으로 보되
    순서 행이 없으면 `0034` 전 지문 그대로다. 가정 배치 차이(`0031`) · `layout_hash` 에는 들지 않는다. 읽기는
    `load_floor_layout_stack`(캐시 경계 `equipment_cache.load_floor_layout_stack` — 층 캐시와 같이 비운다)이고 계약 · 줄 세우기는
    `services/floor_layout_stack.py` 다.
  - 캔버스를 바꾸는 길은 모두 요소가 새 캔버스 안인지 본다(`_require_marks_fit`). 두 진입점(설비 저장의 캔버스·
    `save_floor_layout_canvas`)은 각 ACTIVE 설비 시나리오 최신·최신 공식
    발행의 **가정 요소**(`set`)도 본다(`_require_overlay_marks_fit` → `EquipmentLayoutOverflow`). 가정 차이 호기는 막지 않는다 —
    공식 호기처럼 그 시나리오의 다음 저장만 막힌다. 기준선(`0021`)은 갈아 쓰지 않는다. FAB
    도면은 `fab_layout_profile`·`fab_layout_mark`(`0013`)다.
  - 층 사용 상태(`load_floor_states`·`save_floor_states`, `0029`)는 리비전을 만들지 않는 공용 현행값이다 — 쓰기 잠금 안에서
    `require_profile_version(schema="equipment_ops")` 로 화면이 본 version 을 먼저 대조하고(내용이 같아도 version 이 다르면
    충돌), 같은 내용이면 쓰지 않는다(`wrote=False` — version·dirty 그대로). 설비 시나리오·리비전·공식 발행·옛 배포 흔적 잠금과
    무관하다.
