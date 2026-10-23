# DuckDB 데이터 모델

마지막 갱신일: 2026-10-15

## 운영 원칙

- 시뮬레이션 운영 파일은 `data/capa_simulation.duckdb`, 설비 운영 파일은
  `data/equipment_availability.duckdb`이며 둘 다 Git과 배포 패키지에 포함하지 않는다.
- `managed` 모드에서는 각 DuckDB 파일 옆에 `<파일명>.sync.json` 동기화 사이드카가 생긴다.
  원격 세대(`base_seq`·`base_sha256`·`base_snapshot_key`), 미반영 변경 표시(`dirty`), 게시하지
  못한 스냅샷 키와 실행 중 인스턴스의 심장박동을 담는다. 그 파일 자체가 동기화 대상이라 상태를
  DuckDB 안에 두면 순환이 되므로 DB 밖에 둔다. 사이드카를 읽지 못하면 변경 있음으로 본다.
  `local` 모드에서는 사이드카를 만들지 않는다.
- `시나리오 1개 = 데이터셋 1개`다. 새 시나리오(원천 등록·복제·연도 이동·월 병합)는 새
  데이터셋과 리비전 1 을 함께 만들고 기존 데이터셋을 덮어쓰지 않는다. RQ 16개는 **두 곳에
  나눠 한 번씩만** 적는다 — 데이터셋 표 둘(`RQ_DISPLAY_ORDER`·`RQ_MODULE`)은 `ref_data` 에,
  리비전 표 14개는 리비전 1 의 `rev_data` 에(`repository.DATASET_TABLES`·`REVISION_TABLES`).
  원천 78컬럼(`raw_data`)은 원천 등록(BigDataQuery·CSV·내장 시드)만 적고, 복제·연도 이동·
  월 병합은 원천 행 없이 RQ 만 적는다.
- 데이터셋 표 둘은 편집·리비전 대상이 아니다. 그 시나리오의 모든 리비전이 같은 데이터셋 표를
  물려받으므로 `RQ_MODULE` 이 모자란 시나리오(예: 덧붙일 쪽에만 있는 공정을 베이스 것만 남긴 월
  병합)는 앱 안에서 고칠 길이 없다 — 데이터셋의 읽기 전용 기준정보를 바꾸려면 새 시나리오를
  만든다(원천 다시 등록, 방향을 바꾼 머지). `RQ_DISPLAY_ORDER` 는 화면 정렬에 공용 프로필이
  앞서므로 데이터셋 사본은 사실상 읽히지 않는다.
- 계획·수율·Capa·설비대수·Chip 기준 입력 14개는 불변 전체 리비전으로 저장한다.
- 표시순서는 시나리오와 분리된 단일 공용 프로필로 저장하고 모든 시나리오에 적용한다.
  정렬우선순위는 행 정렬과 분류컬럼 배치에 함께 사용하며, 경로 상세 범위의
  `STEP_SEQ → MCP_SEQ`는 마지막 계층으로 자동 보강한다.
- 공정 표시명(Proc Rename)도 시나리오와 분리된 단일 공용 프로필이다. 원본 공정과
  표시명은 항상 1:1이며 **화면 표기에만** 적용한다. `RQ_*` 저장값, 보고용 CSV와
  붙여넣기 왕복 양식은 원본 공정명을 그대로 유지한다. 프로필이 없는 상태(버전 0)가
  정상이고, 규칙 0건으로 저장하면 지정을 전부 해제한다.
- 리비전은 조회기간, B/N 포함 공정, 표준 목표 Capa 공정 기본값, 확보·경고 기준
  프리셋을 함께 소유한다.
- 공식버전은 특정 리비전(내용 불변)을 가리키는 append-only 발행 이력이며 최신 발행을 새 웹
  세션의 기본값으로 사용한다. 리비전의 내용(표·프리셋·가상 제품·해시·부모·메모)은 갱신하지 않고, 이름표인
  `revision_name` 만 비교 후 쓰기로 고칠 수 있다(이력 없음 — AGENTS 5장 8).
- 저장과 삭제는 Repository의 쓰기 잠금과 DuckDB 트랜잭션 안에서 실행한다.
- 기존 보유대수, 설비 마스터와 운영 비가동 일정은 시뮬레이션 DB·시나리오·`RQ_*`와
  독립된 불변 전체 스냅샷 리비전으로 저장한다.
- 앱은 단일 Streamlit 서버 프로세스와 서로 독립된 로컬 DuckDB 두 개를 전제로 한다.
- 시나리오 DB가 완전히 비어 있으면 Git에 포함된 비민감 표시순서와 합성 78컬럼 Core
  Data로 초기 데이터셋·리비전·공식버전을 만든다. 공식버전이나 사용자 시나리오가 있으면
  자동 부트스트랩은 상태를 변경하지 않는다.

## 스키마 관계

```text
# data/capa_simulation.duckdb — 시나리오가 소유하는 것(소유 컬럼 scenario_id·dataset_id·revision_id)
app_meta.scenario 1 ── 1 app_meta.dataset                 (status ACTIVE·ARCHIVED — 보관은 숨김일 뿐)
       │                       │
       │                       ├── N raw_data.core_data            (원천 등록만 — 복제·파생은 0행)
       │                       ├── 78 raw_data.source_column_profile
       │                       └── N ref_data.rq_display_order · rq_module   (데이터셋 표 2 — 편집 대상 아님)
       │                           ref_data.rq_* 나머지 14 는 0033 이 남긴 옛 사본뿐(읽는 코드 없음)
       │
       └── N app_meta.scenario_revision (내용 append-only — revision_name 만 고침, parent_revision_id 로 분기)
                    │
                    ├── N rev_data.rq_* (리비전 표 14 — 편집·저장 단위)
                    │     rev_data.rq_display_order 는 0001 의 옛 자리(쓰지 않음, 공용 표시순서 첫 이관 때만 읽음)
                    ├── N app_meta.revision_virtual_product
                    ├── 1 app_meta.scenario_preset
                    ├── N app_meta.scenario_preset_process
                    └── N app_meta.scenario_preset_standard_target_process

app_meta.official_release N ── 1 app_meta.scenario_revision
        └── 전역 증가 release_no 의 공식 발행 이력(scenario_id 를 가져 시나리오 삭제가 함께 지운다)

result_data.simulation_run                                 (골격만 — 쓰는 코드 없음)

# data/capa_simulation.duckdb — 공용 프로필(소유 컬럼 없음, 단일 행 머리 profile_id = 1 + 자식 행,
#   교체마다 version+1, 시나리오 삭제·보관이 건드리지 않음)
app_meta.global_display_order        1 ── N global_display_order_rule        표시순서(0010)
app_meta.global_process_rename       1 ── N global_process_rename_rule       공정 표시명(0015, 화면 표기 전용)
app_meta.global_advance_load         1 ── N global_advance_load_month        선행 B/O(0018)
app_meta.global_past_data            1 ── N global_past_month                과거 구간(0019)
                                       ├── N global_past_plan_detail
                                       └── N global_past_securement
app_meta.global_comparison_scenario  1                                       GAP 비교 대상(0020 — 아래 예외)
app_meta.global_execution_capacity   1 ── N global_execution_capacity_row    확보율 보정(0021)
app_meta.global_top5_band            1                                       B/N Top5 구간(0022)
app_meta.global_summary_note         1                                       HOME Summary 공지(0023)
app_meta.global_key_process          1 ── N global_key_process_preset        주요공정 프리셋(0024·0028)
                                       ├── N global_key_process_preset_item
                                       └── N global_key_process_item         (0024 옛 목록 — 0028 뒤 읽지 않음)
app_meta.global_securement_threshold 1 ── N global_securement_threshold_month 확보율 판정 기준(0029)
app_meta.global_advance_shipment     1 ── N global_advance_shipment_month    선행 입고 실적(0031, 계산 밖)
app_meta.global_auto_official_update 1 ── N auto_official_update_setting_log 공식버전 자동 갱신 설정·변경 기록(0035)
app_meta.auto_official_update_run    1 ── N auto_official_update_exclusion   실행·자동 off 공정(0035, run_id·머리 없음)
app_meta.global_main_cases           1                                       HOME 주요 Case(0036 — 아래 예외)
app_meta.voc_post                    1 ── N voc_reply (post_id)              VOC 게시판(0025, 머리 없음)

app_meta.schema_migration · (옛 개발 DB 에만) 빈 equipment_ops 스키마(결번 2·3 의 흔적 — migration_catalog.md)

# data/equipment_availability.duckdb — 리비전(append-only 전체 스냅샷)
equipment_ops.revision
       ├── N equipment_ops.baseline_snapshot
       ├── N equipment_ops.equipment_master_snapshot
       ├── N equipment_ops.downtime_schedule_snapshot
       └── (레거시 — 쓰지 않음) schedule_snapshot(0001) · equipment_snapshot · downtime_snapshot(0002)

# data/equipment_availability.duckdb — 리비전 없는 공용 표(설비 리비전을 저장해도 복제되지 않음, 표끼리 FK 없음)
equipment_ops.standard_target_weekly_availability         공정·Weeknum별 수동 가용대수(0005)
equipment_ops.process_cutoff                              공정별 Cut-off 일수(0009, PK 공정·product_scope)
equipment_ops.floor_layout_profile 1 ── N floor_layout_mark   동·층 도면·캔버스와 비설비 요소(0007·0011·0017·0025)
                       (building, floor_name)
equipment_ops.floor_layout_group_label                    층 Main 설비명 위치(0025, 키 동·층·Main 설비, PK 없음)
equipment_ops.fab_layout_profile   1 ── N fab_layout_mark     S.PKG FAB 전체 도면과 층 블록(0013·0017·0025, layout_key 'FAB')
equipment_ops.shortening_filter_profile 1 ── N shortening_filter_process   필요 단축 일정 공용 조회 조건(0019)
equipment_ops.shortening_baseline  1 ── N shortening_baseline_process      진척 비교 기준선(0021 — 고칠 수 없는
                                     └── N shortening_baseline_unit        기록, 새로 저장하거나 통째로 지운다)

equipment_meta.schema_migration
```

`app_meta.global_comparison_scenario` 만 공용 프로필인데 `scenario_id`·`revision_id` 를 가진다 — 비교
대상을 **가리키는** 참조다. 그대로 두면 소유 자동 발견(`repository._owned_tables`)이 시나리오 소유로 보고
삭제 때 프로필 행을 통째로 지우므로 자동 발견에서 빼고(`_GLOBAL_PROFILE_TABLES`), 보관·삭제가 그 대상을
명시적으로 비운다(version+1). 공용 프로필을 새로 만들 때는 소유 컬럼을 두지 않는다.
`0035` 공식버전 자동 갱신의 네 표가 그 꼴이다 — 실행이 만든 시나리오·리비전·공식버전을
`created_scenario_id`·`base_revision_id`·`filtered_revision_id`·`official_release_id` 로 가리키기만 하고,
이름이 소유 컬럼과 달라 자동 발견에 걸리지 않으므로 시나리오를 지워도 그날의 기록이 남는다.
`0036` 주요 Case(`app_meta.global_main_cases`)도 가리키는 참조지만 칸 이름이 `case1_scenario_id`·
`case1_revision_id`·`case2_scenario_id`·`case2_revision_id` 라 자동 발견에 걸리지 않는다(`_GLOBAL_PROFILE_TABLES` 에
두지 않는다). 그래서 보관·영구 삭제가 같은 트랜잭션에서 그 시나리오를 가리키는 Case 만 명시적으로 비우고 행은
남긴다(version+1, 출처 칸에 「Case2 지정 비움 — 시나리오 보관」 처럼 까닭). 가리키는 시나리오·리비전의 이름 바꾸기는
version 만 올린다 — HOME 슬롯 글자가 시나리오명·리비전명을 싣는다.

DuckDB 1.5.5는 서로 다른 스키마 사이의 외래 키를 만들 수 없으므로 스키마 간 FK는
DDL에 선언하지 않는다. 대신 Repository가 같은 트랜잭션 안에서 소유 관계, 상위 리비전,
행 수와 필수 테이블을 검증한다. 각 테이블의 PK·UNIQUE·CHECK 제약은 DB에 유지한다.

## 스키마별 책임

### `app_meta`

- `schema_migration`: 적용한 SQL 마이그레이션 버전과 체크섬
- `global_advance_load`·`global_advance_load_month`: 시나리오와 독립된 공용 **선행 B/O**
  프로필(마이그레이션 0018 — 화면 이름은 2026-10-06 에 「선행 투입 물량」에서 「선행 B/O」로
  바꿨고 표·컬럼 이름 `선행 물량` 은 그대로다). 계획 밖으로 앞서 만든 B/O 재공(억Gb)이라 계획에
  더한다. 월이 기본키라 한 달에 한 값이고, 교체마다 version 이 오르며 이전 값은 보존하지
  않는다. 화면 산출 직전에만 곱해지고 어떤 `RQ_*` 표에도 오버레이되지 않는다.
- `global_advance_shipment`·`global_advance_shipment_month`: 시나리오와 독립된 공용 **선행 입고
  실적** 프로필(마이그레이션 0031). 계획보다 앞서 입고한 물량(억Gb, 부호는 입력한 그대로)이고
  생산계획에 이미 들어 있으므로 **계산에 들어가지 않는다** — HOME `Capa LOB 현황` Density 칸
  오른쪽 끝, 값과 같은 높이(값이 길면 겹칠 수 있음 — 2026-10-07 사용자 결정)에 적기만 한다. 모양·교체 규칙은 선행 B/O 와 같다(월 기본키, 0 은 행 없음, 교체마다
  version+1, 소유 컬럼 없음).
- `global_execution_capacity`·`global_execution_capacity_row`: 시나리오와 독립된 공용 실행
  Capa 반영 프로필(마이그레이션 0021). `(생산계획년월, 공정)` 이 기본키라 한 달·한 공정에 한
  값이고, 교체마다 version 이 오르며 이전 값은 보존하지 않는다. `증감 확보율` 의 단위는
  **퍼센트포인트**다. 확보율이 나온 뒤 화면 산출 직전에만 더해지고 어떤 `RQ_*` 표에도
  오버레이되지 않는다. **소유 컬럼(`scenario_id`·`dataset_id`·`revision_id`)을 두지 않는다** —
  두면 `_owned_tables` 자동 발견이 시나리오 소유로 판정해 시나리오 삭제가 이 프로필 행을
  함께 지운다.
- `global_auto_official_update`·`auto_official_update_setting_log`·`auto_official_update_run`·
  `auto_official_update_exclusion`: **공식버전 자동 갱신**(마이그레이션 0035). 설정은 헤더 한 행
  (켜짐·확인 시각·시뮬레이션명 키워드·기준 확보율 비율, version 대조)이고 저장마다 같은 version 의
  변경 기록이 한 행 붙는다. 실행 기록은 회차 하나가 한 행이며 `run_key` 유일 제약이 회차 선점이다
  (예약은 날짜당 하나). 자동 off 기록은 회차·공정마다 한 행(`AUTO` 판정 — 최저 확보율·그 달,
  `INHERITED` 직전 공식버전의 수동 off 이어받음)이다. 실행이 만든 시나리오·리비전·공식버전은
  `created_scenario_id`·`filtered_revision_id` 처럼 가리키기만 한다 — 소유 컬럼이 없어 시나리오를
  지워도 기록이 남는다.
- `scenario`: 이름, 원천 시뮬레이션 코드/명, 상태, 현재 최신 리비전과 목록 관리 화면이
  지정한 누적 순서(`list_order`, 마이그레이션 0017). 목록의 「변경 저장」이 순서를 고쳤을 때만
  적는다(이름만 바꾼 저장은 쓰지 않는다). 한 번도 저장하지 않은 시나리오는 NULL 이며 만든 시각의
  최근 것부터 뒤에 붙는다 — 이름 변경·새 리비전 저장으로 「최근 수정」이 올라도 움직이지 않는다.
  순서를 한 번 저장한 뒤 새로 만든 시나리오는 NULL 이라 맨 아래에 붙는다. `status` 는
  `ACTIVE`·`ARCHIVED`(보관) 둘이다 — 보관은 목록에서 숨길 뿐 행을 그대로 두고(`repository.archive_scenario`·
  `restore_scenario`), 보관한 시나리오에는 새 리비전을 저장할 수 없다. 보관본은 목록 관리의
  「보관된 시나리오 N건」 상자에서 되돌리거나 영구 삭제한다.
- `dataset`: 시나리오 소유 데이터셋, 원천 종류(`source_type` — `BIGDATAQUERY`·`CSV_CORE_DATA…`·
  `BUILTIN_SYNTHETIC_SEED`·`DUCKDB_SCENARIO_CLONE`·`SCENARIO_YEAR_SHIFT`·`SCENARIO_MONTH_MERGE`),
  원천 등록·적재 시각, 원천 행 수·해시, 변환 버전, 상태(`LOADING`→`READY`, 보관이면 `ARCHIVED`)
- `scenario_revision`: 증가하는 리비전 번호, 리비전명(이름표 — 시나리오 관리 리비전 표에서 고칠 수 있다), 부모 리비전,
  입력 해시와 변경 메모(시스템 출처 기록이 들어 고치지 않는다)
- `scenario_preset`: 조회 시작·종료월, 내부 비율의 확보·경고 기준, 프리셋 해시와 표준
  목표 Capa 「조회·집계 설정」(`standard_target_start_date`·`standard_target_end_date`·
  `standard_target_show_detail`·`standard_target_detail_level`·
  `standard_target_output_metric`). 조회·집계 설정 컬럼은 NULL 을 허용하며 값이 없으면
  화면 기본값으로 연다. DuckDB 는 `ADD COLUMN` 에 CHECK 를 받지 않으므로 시작일·종료일
  순서 같은 제약은 `ScenarioPreset.__post_init__` 이 지킨다.
- `scenario_preset_process`: 리비전별 B/N 집계 포함 공정과 저장 순서
- `scenario_preset_standard_target_process`: 리비전별 표준 목표 Capa 공정 공용 기본값과
  저장 순서. 행이 없으면 전체 공정으로 해석한다.
- `revision_virtual_product`: 리비전에 기록된 가상 제품(복제 원본 → 새 제품 키) 목록
- `official_release`: 전역 공식버전 번호, 대상 시나리오·리비전, 공식버전명·메모·발행시각
- `global_display_order`: 공용 표시순서 버전, 변경 출처와 갱신시각
- `global_display_order_rule`: 페이지·탭·분류컬럼별 현재 정렬 규칙과 원본 행 순서
- `global_process_rename`: 공용 공정 표시명 버전, 변경 출처와 갱신시각
- `global_process_rename_rule`: 원본 `공정` → 화면 `표시명` 규칙과 원본 행 순서.
  `(profile_id, 공정)`·`(profile_id, 표시명)` UNIQUE가 1:1을 받친다.
- `global_past_data`·`global_past_month`·`global_past_plan_detail`·`global_past_securement`
  (0019): 적재 시점 이전 과거 구간 — 월별 Density·Wafer Total, 계획 세부수량(제품정보·Stack·
  Customer), 공정별 확보율. HOME Past Data 가 읽고 계산 입력에는 들지 않는다.
- `global_comparison_scenario`(0020): GAP 비교 대상 시나리오·리비전. 고르지 않은 상태는 두 값이
  NULL 이다. 공용 프로필 가운데 유일하게 `scenario_id`·`revision_id` 를 가져 소유 자동 발견에서
  뺀다(위 「스키마 관계」 아래 문단).
- `global_main_cases`(0036): HOME 주요 Case — 슬롯 셋(공식버전·Case1·Case2) 가운데 Preference 에서 지정하는
  Case1·Case2 의 시나리오·리비전 짝(한 행에 Case 마다 칸 둘). 슬롯 1 은 늘 최신 공식버전이라 담지 않는다. 지정
  안 한 Case 는 두 값이 NULL 이고, 리비전만 있는 짝은 Case 마다 `CHECK` 가 막는다. 한 Case 교체는 다른 Case 를
  같은 쓰기 트랜잭션에서 옮겨 적는다(위 「스키마 관계」 아래 문단).
- `global_top5_band`(0022): B/N Top5 막대가 표현하는 확보율 구간(기본 50~200%).
- `global_summary_note`(0023): HOME 상단 Summary 공지. 빈 문자열은 「공지를 내린 상태」다.
- `global_key_process`(0024)·`global_key_process_preset`·`global_key_process_preset_item`(0028):
  HOME 주요공정 히트맵의 이름 붙은 프리셋 여럿. 머리(version)는 0024 것을 쓰고 `프리셋순서` 0 번이
  새 세션의 기본이다. 0024 의 단일 목록 `global_key_process_item` 은 0028 이 「기본」 프리셋으로 옮긴
  뒤 지우지 않고 남겼고 읽는 코드는 없다.
- `global_securement_threshold`·`global_securement_threshold_month`(0029): 확보율 판정 기준 —
  기본 확보·경고 기준(비율)과 그 달에만 다른 월별 예외. 저장은 편집 시작 version 과 대조한다.
  한 번도 저장하지 않아 행이 없으면 최신 공식버전 프리셋의 `secure_threshold`·
  `warning_threshold`(없으면 코드 기본값)를 쓴다 — 리비전 프리셋 열은 그 대체값으로만 읽힌다.
- `voc_post`·`voc_reply`(0025): VOC 게시판의 글·답글. 머리 행 없이 `post_id` 로 이어지고, 어느
  시나리오에도 매이지 않아 시나리오를 지워도 남는다.

`scenario_revision.parent_revision_id`는 과거 리비전에서 새 리비전을 저장하는 분기 이력을
보존한다. `scenario.active_revision_id`는 가장 최근에 저장한 리비전을 가리키며, 사용자는
드롭다운에서 그보다 오래된 리비전도 별도로 불러올 수 있다.

`official_release`는 과거 행을 수정하지 않는다. 가장 큰 `release_no`의 대상 리비전이 새
세션의 기본값이며, 대상 리비전은 해당 시나리오 소유인지 Repository가 검증한다. 최신 공식
시나리오는 기본 진입점 단절을 막기 위해 다른 공식버전을 먼저 발행하기 전에는 삭제할 수 없다.
그 외 시나리오를 삭제하면 그 시나리오를 가리키던 발행 이력도 함께 사라져 `release_no` 에
구멍이 생긴다. 다음 번호는 남은 최대값 + 1 이라 번호를 다시 쓰지는 않는다.

### `ref_data`

시나리오를 만들 때 데이터셋 소유로 적는 RQ 표다. 표는 16개 모두 있지만(스키마는 그대로) **새
데이터셋은 리비전 표가 아닌 둘만** 적는다(`repository.DATASET_TABLES`).

```text
RQ_DISPLAY_ORDER   RQ_MODULE
```

나머지 14개(아래 `rev_data`)는 리비전 1 에만 적는다(2026-10-06 사용자 결정 B3). 스냅샷은 그
14개를 `rev_data` 에서만 읽고 리비전은 불변이라, 데이터셋 사본은 읽는 곳 없이 행만 늘었다 — 내장
시드를 새로 부트스트랩하면 `ref_data` 649 → 21행, `ref_data`+`rev_data` 1,277 → 649행, 파일
5,189,632 → 4,714,496바이트(−9.2%)다(샘플 관측: `scripts/generate_sample_core_data.py` 리터럴에서
나온 내장 합성 시드 96행).

**이 결정 전에 만든 데이터셋의 14개 사본은 마이그레이션 `0033` 이 지운다**(2026-10-10 사용자 승인).
(데이터셋, 표)마다 그 사본의 모든 행이 데이터셋 시나리오의 **리비전 1** 에 행 단위로(소유 열만 빼고
`source_row_no` 와 값 열 전부, NULL 은 NULL 과 같게) 들어 있을 때만 지운다. 한 행이라도 리비전 1 에
없는 사본, 리비전 1 이 없거나 `app_meta.dataset` 에 없는 데이터셋의 사본은 통째로 남긴다 — 다른 곳에
없는 값일 수 있어서다. 남은 사본도 읽는 코드는 없다. 표를 다시 만들어 지우므로 행은 사라져도 파일은
줄지 않는다(공간 회수는 `scripts/compact_duckdb.py`). 샘플 관측(합성 데모 DB 사본, 3 데이터셋):
14표 사본 337,158행 → 0행, 약 1초, 파일 103,297,024바이트 그대로. 진단 스크립트
(`inspect_top_remigration.py`·`audit_top_remigration.py`·`inspect_wf_division.py`)는 두 스키마를 따로
세면서 사본이 남은 데이터셋 수(읽는 표 가운데 하나라도)를 함께 찍고, `inspect_real_data_checks.py` 의
8-1 은 남은 데이터셋 수와 사본 행 수를 찍는다. `compare_legacy_results.py` 의 대조 기준은 데이터셋
시나리오의 리비전 1 이다. 0014·0026 같은 앞선 마이그레이션은 이 표들에 남아 있던 옛 사본도 함께 고쳤다.

기술 키는 `(dataset_id, source_row_no)`다. `source_row_no`는 DataFrame의 현재 행 순서를
1부터 부여하며, 원본 컬럼명과 순서를 유지한다. 업무 고유 키는
`config/data_contract.json`의 `derived_keys`에 테이블별로 정의한다.
`RQ_UPEH`·`RQ_LOT_RATIO`·`RQ_WF_RATIO`는 생산계획년월·Area·공정·`STEP_SEQ`·
`MCP_SEQ`·양산구분·제품정보·Stack·WF 구분을 경로 키로 사용한다. `RQ_UPEH` 의 `UPEH` 는 Main 행의
시간당 처리량, `ST` 는 MI 행의 한 개당 분(min/unit)이다(정의 — 계산은 60 ÷ ST, AGENTS.md 6장). 조인 키로 쓰는 `WF 구분`의
값은 EDP-TSV 행에서 `Top`이 아니라 `Top_e`다. 원천에는 없는 값이며 `services/product_type.py`의
규칙에 따라 `build_q_core_data`가 파생 경계에서 한 번만 갈라 붙인다. 0014 이전에 적재한
기준정보·리비전 스냅샷은 마이그레이션이 같은 값으로 맞춘다. `RQ_REQB`와 대당 Capa를 연결할
때도 Area·STEP·MCP를 포함해 정확히 일치시킨다.

### `rev_data`

리비전마다 다음 14개 테이블의 전체 스냅샷을 저장한다.

```text
RQ_PKG_PLAN  RQ_YLD       RQ_UPEH      RQ_RUN_RATE
RQ_VITAL     RQ_RUN_DAY   RQ_LOT_RATIO RQ_WF_RATIO
RQ_REQB      RQ_EQP_OWN   RQ_EQP_LENT   RQ_EQP_AVBL
RQ_CHIP_QTY  RQ_CHIP_EQ
```

`RQ_PKG_PLAN`은 0013 부터 `제품타입`·`Pack Code`를 함께 싣는다. `Pack Code`는 2026-09-12
부터 업무 키(계약 `derived_keys` 8키의 마지막)이고 `제품타입`은 값 컬럼이다. 컬럼 순서는
DDL 순이라 둘 다 끝에 있다 — 메모리 프레임 순서를 바꾸면 리비전 왕복 동등성이 깨진다.

기술 키는 `(revision_id, source_row_no)`다. 리비전을 읽을 때 이 14개는 `rev_data` 에서만 읽고,
나머지 둘(`RQ_DISPLAY_ORDER`·`RQ_MODULE`)은 데이터셋 `ref_data` 를 사용한다. 새 데이터셋은 이
14개를 `ref_data` 에 적지 않으므로 리비전 1 이 원천 변환 결과의 유일한 사본이다.
`RQ_REQB`는 STEP 구성 변경을 리비전별로 재현하기 위해 리비전마다 저장한다.
`rev_data` 에는 이 14개 말고 `rq_display_order` 표도 있다(0001 의 옛 자리). 지금은 아무도 쓰지
않고, 공용 표시순서 프로필이 아직 없을 때 첫 이관(`display_order_store.load_existing_display_order`)이
옛 리비전·데이터셋 사본을 찾느라 읽을 뿐이다. 런타임 화면 정렬은
`app_meta.global_display_order_rule`의 현재 공용 프로필을 우선한다.

### `raw_data`

`core_data`는 `config/data_contract.json`에 정의한 원천 78개 컬럼을 VARCHAR·BIGINT·DOUBLE
타입으로 저장한다. 원천 행은 `(dataset_id, source_row_no)` 기술 키와 `row_hash`로 보존하고,
`source_column_profile`에는 원천/nullable dtype, null 수와 고유값 수를 컬럼 순서대로
저장한다. 원천 null은 보존하며 RQ 변환 단계에서 업무 키의 null·빈값과 동일 키의 값
충돌을 검증한다.

동일 시뮬레이션 코드는 불변 원천으로 취급한다. 행 순서와 무관한 multiset 데이터 해시가
같으면 같은 코드를 다른 시나리오로 다시 등록할 수 있고(원천 행도 그 데이터셋에 다시 적는다),
해시가 다르면 등록을 거부한다(보관본 포함). 복제·연도 이동·월 병합은 원천 행을 적지 않는다 —
이 데이터셋들의 `source_row_count` 는 0 이고, 원천을 읽는 쪽(`repository.load_source_data`)은
「원천 Core Data 가 저장되어 있지 않다」로 알린다.

### `result_data`

`simulation_run` 메타데이터 골격만 준비되어 있다. 계산 결과 테이블과 진단 데이터 저장은
후속 단계이며 Plotly Figure 자체는 저장하지 않는다.

### 설비 전용 DB의 `equipment_meta`, `equipment_ops`

- `equipment_meta.schema_migration`: 설비 DB에만 적용하는 SQL 버전과 체크섬
- `revision`: 설비 운영 입력의 증가 리비전 번호, 변경 메모, 입력 해시와 저장 시각
- `baseline_snapshot`: 공정·분류별 기존 보유대수와 비고의 전체 스냅샷
- `equipment_master_snapshot`: 설비명(`equipment_id`)을 키로 Area Code·공정대/소분류, Maker·Model,
  공정구분·투자Capa·투자구분·사용기준·담당자 등 참고 속성, 동·층, Space X/Y 좌표와 X/Y 크기,
  제진대·물류·반입 일정, 반입실적·반입상태, Qual 일정·Qual실적·Qual상태, 정지·반출/이설 일정,
  반입/Qual 이력·호기이력·설비이력, 보관유무·기존설비여부·레이아웃표시, 환산비·Main 설비, 메모1~3 을
  저장하는 전체 스냅샷(38열, 2026-10-16 사용자 결정). **`사용기준`(`classification_2`)은 참고 속성이
  아니라 가용대수 대상을 가른다** — 설비 일정 기준 가용대수·필요 단축 일정은 이 값이 `HBM` 또는 `EDP`(앞뒤
  공백·대소문자 무시, 완전 일치)인 행만 한 가용대수로 센다(2026-10-08 사용자 결정,
  `equipment_contract.counts_for_capacity`).
  저장 형식은 바뀌지 않았고 빈 값으로 저장된 옛 리비전의 호기는 그 결정으로 가용대수에서 빠진다.
  `baseline_snapshot` 에는 사용기준이 없어 기존 보유대수는 늘 센다. DB 컬럼은 영문이고 한글 계약 이름과의 매핑은
  `persistence/equipment_repository.py` 의 `EQUIPMENT_MASTER_DB_COLUMNS` 한 곳이다 — 2026-10-06·
  2026-10-16 이름 바꿈은 매핑만 바꿔 기존 리비전이 그대로 이어진다(`classification_1` = Area Code(옛
  구분), `removal_date` = 정지일정(옛 반출일정), `relocation_date` = 반출/이설일정(옛 이설일정),
  `qual_confirmation_status` = Qual상태(옛 확정상태)). 투자Capa·반입/Qual 이력·메모1~3 은 `0015` 의
  nullable 컬럼(`investment_capa`·`arrival_qual_history`·`memo_1~3`), 반입실적·반입상태·Qual실적은
  `0023` 의 nullable 컬럼(`arrival_actual_date` DATE·`arrival_status`·`qual_actual_date` DATE)이다.
  집계 이탈일은 min(`removal_date`, `relocation_date`), 도면 이탈일은 `relocation_date`(없으면
  `removal_date`)다 — 두 칸을 함께 적은 행은 2026-10-16 결정 뒤에만 생긴다.
  `business_unit`·`investment_basis`(옛 `투자기준`)·`classification_3`(옛 `설비가동현황`)은 입력
  계약에 없지만 그 값을 담은 과거 리비전이 남아 있어 컬럼을 유지한다. 신규 리비전에서는 NULL 이다.
  `투자기준` 은 되살리지 않기로 확정했다(2026-10-07 사용자 결정). `설비가동현황` 은 2026-10-16 사용자
  결정으로 빠졌다.
- `downtime_schedule_snapshot`: 설비명·유형·시작일 자연키와 종료일·상세사유·비고의
  전체 스냅샷
- `standard_target_weekly_availability`: 표준 목표 Capa 수동 입력용 공정·Weeknum별
  가용대수 최신값. 리비전을 만들지 않고 같은 키를 갱신하며 명시적 초기화 시 전체 삭제한다.
- `floor_layout_profile`: 동·층별 배경 도면과 캔버스 치수. `(building, floor_name)` PK 이고
  `revision_id` 가 없다 — `standard_target_weekly_availability` 와 같은 리비전 무관 공용
  프로필이라 설비 리비전을 저장해도 복제되지 않는다. 도면 원본은 `image_payload` BLOB 으로
  두고 조회 시에만 `data:{mime};base64,...` 로 만들어 Plotly 배경으로 넘긴다.
  이미지 없이 캔버스 치수만 저장할 수도 있다(`image_*` NULL).
  **저장은 append 가 아니라 UPDATE 다.** DuckDB 는 지운 페이지를 회수하지 않아
  행을 DELETE+INSERT 로 다시 쓰면 수정마다 BLOB 한 벌씩 파일이 커진다(실측: 3.8MB 한 장을
  6회 수정하면 51.7MB). 캔버스만 바꿀 때는 치수 두 컬럼만 UPDATE 하고, 같은 도면
  재업로드는 저장된 `sha256(image_payload)` 와 비교해 BLOB 쓰기를 건너뛴다.
- `floor_layout_mark`(마이그레이션 11): 동·층별 비설비 도면 요소(반입구·문·영역·기둥·글자·
  동선). `floor_layout_profile` 처럼 `revision_id` 가 없는 층 현행값이라 설비 리비전을 저장해도
  복제되지 않는다. 저장은 그 층 요소 전체를 DELETE+INSERT 로 갈아 끼우고(BLOB 이 없어 파일
  증가는 미미하다) `source_row_no` 가 그리는 순서다. PK 는 두지 않는다 — 같은 트랜잭션에서
  같은 id 를 지웠다 다시 넣는다. 종류(`mark_kind`)·회전·영역 색 키·캔버스 범위·층 안 id
  유일성은 `services/floor_layout_mark.py` 가 맡는다. 리비전 저장과 같은 트랜잭션에 쓸 수 있다.
  이름표 글자 크기 `font_size`(INTEGER, 9·11·13·16·20·24 화면 px)와 글자 색 `font_color`(영역 색 키)는
  마이그레이션 17 의 NULL 허용 컬럼이다 — NULL 은 자동 크기·기본 글자색이다. `fab_layout_mark`
  (마이그레이션 13)도 같은 두 컬럼을 갖는다. 영역의 테두리 모양 `border_style`(`dashed`·`solid`)과
  이름표 정렬 `label_align`(`left`·`center`·`right`)은 마이그레이션 25 의 NULL 허용 컬럼이다(두 표 모두) —
  NULL 은 지금 모습(점선·왼쪽)이고 영역이 아닌 요소는 늘 NULL 이다.
- `floor_layout_group_label`(마이그레이션 25): 층마다 Main 설비 모듈 묶음 이름표의 위치(`top`·`bottom`).
  설비 마스터 칸이 아니라 `floor_layout_mark` 처럼 리비전 없는 층 현행값이고, 가운데(기본)는 행이 없다.
  키는 (`building`, `floor_name`, `parent_equipment_id`)이고 층 단위 DELETE+INSERT 라 PK 를 두지 않는다.
  층 저장의 동시성 대조는 요소와 위치를 함께 본 지문(`floor_layout_fingerprint`)이다. 검사는
  `services/floor_layout_mark.prepare_group_labels`, 적용 합치기·이름 바꿈 따라가기는
  `services/space_layout_edit.next_group_labels`.
- `fab_layout_profile`·`fab_layout_mark`(마이그레이션 13): Space S.PKG FAB 전체 도면. 머리는
  `layout_key = 'FAB'` 한 행(캔버스·배경 도면 BLOB, `floor_layout_profile` 처럼 UPDATE 로 고친다)이고,
  요소는 `floor_layout_mark` 와 같은 열(동·층 제외)에 층 블록의 연결 대상 `link_building`·
  `link_floor` 를 더한 것이다(둘 다 있거나 둘 다 NULL, 층 블록은 필수). 층 표에 「FAB」 가짜 키를
  넣지 않으려고 표를 따로 둔다. 요소는 전체 교체(DELETE+INSERT)라 PK 가 없고, 요소 행이 없으면
  화면이 코드의 기본 배치를 그린다. 검사는 `services/fab_layout.py`.
- `process_cutoff`(마이그레이션 9): 공정별 Cut-off(그 공정 이후 입고까지의 표준 납기) 일수.
  `(process_name, product_scope)` PK 이고 `product_scope` 는 지금 모두 `'*'`(공정 전체 — 나중
  제품 축 자리)다. TAT·공정 선후관계가 저장소에 없어 파생값이 아니라 사람이 적는 원장이고,
  리비전 없는 현행값이다. `cutoff_days` 는 DOUBLE 로 받되 `services/wd_window.py` 가 내림해 쓴다.
  `필요 단축 일정` 화면·가용설비 현황 월별 가용대수가 읽는다.
- `shortening_filter_profile`·`shortening_filter_process`(마이그레이션 19): `필요 단축 일정` 화면의
  공용 조회 조건 — 머리 한 행(`start_month`·`end_month` `YYYYMM`, 둘 다 있거나 둘 다 NULL,
  version)과 고른 공정(`sort_order` 차례). 기간 NULL 은 「저장 안 함 → 조회기간 전체」, 공정 0행은
  「목표 미달 공정 전체」다. 기간과 공정은 따로 쓰고 쓸 때마다 version+1. 규칙은
  `services/shortening_filter_profile.py`.
- `shortening_baseline`·`shortening_baseline_process`·`shortening_baseline_unit`(마이그레이션 21):
  진척 비교의 **기준선** — 「기준선 저장」을 누른 그때의 필요단축 계획을 얼린 공용 기록이다.
  UPDATE 가 없고 새로 저장하거나 통째로 지운다(지우기는 자식 행부터 한 트랜잭션). 머리는
  `baseline_id`(uuid hex) PK·`baseline_name` UNIQUE 와 그때의 출처(설비 리비전·기준정보 버전·
  시나리오·리비전·`content_token` — 모르면 NULL), 공정 표는 그때 맞댄 공정과 Cut-off, 호기 표는
  목표(90~130%)마다 당긴 호기와 가상 호기(「추가N」)다. 외래키는 없다. SQL 은
  `persistence/shortening_baseline_store.py`, 얼리는 규칙은 `services/shortening_baseline.py`.
- `schedule_snapshot`: 마이그레이션 1에서 생성한 기존 입고·셋업 일정 보존용 레거시 테이블.
- `equipment_snapshot`, `downtime_snapshot`: 마이그레이션 2 계약의 과거 리비전
  보존용 레거시 테이블. 신규 저장은 마이그레이션 3의 두 스냅샷 테이블을 사용한다.

현재 화면은 가장 최근 리비전을 편집 원본, 가용설비 대시보드와 Space 현황의 공통 원천으로
사용한다. 일정 수정, 신규 호기·비가동 추가 또는 행 삭제 후 저장하면 기존 리비전을 갱신하지
않고 세 입력의 새 전체 스냅샷을 추가한다. 기존 보유대수는 즉시 가용, 신규 호기는 반입일부터
총대수, Qual일부터 가용대수로 계산한다. 보관유무 Y 와 활성 운영 비가동은 가용에서 제외하고,
정지일정·반출/이설일정 가운데 이른 날부터 보유·가용에서, 반출/이설일정(없으면 정지일정)부터
레이아웃에서 제외한다. 신규 호기의 반입·Qual 일정은 비워도
저장되며(`arrival_date`·`qual_date` NULL) 반입이 비면 입고 예정, Qual 이 비면 셋업 진행중으로
남아 가용대수에 들지 않는다.
Qual상태(옛 확정상태)는 Qual 일정의 계획·확정·완료·지연 모니터링 용도이며 가용 산식에는 사용하지
않는다. Qual일정이 있는 신규 호기에만 필수다. 반입상태도 같은 네 값의 모니터링 값이고 비워도
저장된다. 반입실적·Qual실적은 Space 실물 판정과 일정 확인 알림에만 쓰고 가용 산식에는 쓰지 않는다.
집계형 기존 보유대수는 호기·좌표가 없어 Space 배치에는 포함하지 않는다. 시뮬레이션 DB의
공정·설비 테이블은 읽지 않으며, 공정명은 향후 Dynamic Capa 연결 계층의 호환 키로만 보존한다.

## 실적 이력 확장 원칙

표준 Capa 와 실적(효율·UPEH·생산실적·수율 — 실행 관리가 모으고 Dynamic Capa 가 실현 Capa 로 다시
낸다)은 수명주기가 다르므로 같은 리비전 스냅샷에 넣지 않는다.

```text
시뮬레이션 시나리오·리비전
        └─ 표준 Capa 상세 (공정·제품·Stack·WF 속성·소요기준)

실적효율 누적 이력                    생산실적 누적 이력
        └─ 원천일자·배치ID·등록시각           └─ 원천일자·배치ID·등록시각
                   └──────── 조회 시점에 상세 키로 연결 ────────┘
```

- 실적효율과 생산실적은 원천 갱신 주기마다 신규 배치를 적재하고 과거 확정 행을 기본적으로
  덮어쓰지 않는다. 정정 데이터의 식별·최신 유효행 선택 정책은 실제 DB 계약 시 확정한다.
- 실적 이력은 시나리오마다 복제하지 않는다. 분석 실행에는 사용한 표준 `revision_id`, 실적
  원천 기준일, 배치 ID 또는 조회 시각을 기록해 같은 결과를 재현할 수 있게 한다.
- 기본 연결 수준은 `일자 + 공정 + 제품정보 + Stack + WF 구분`이며, 원천이 제공하면
  설비·호기·Shift를 상세 키로 추가한다. 명칭이 다른 원천은 별도 Master 매핑을 거친다.
- 제품 Mix 상세 Capa와 실적은 먼저 같은 상세 키에서 연결한다. 상위 Capa와 생산수량은
  합계, 효율은 계획시간, UPEH는 실가동시간 가중평균으로 집계하며 비율은 집계 합계에서
  다시 산출한다.
- Rundown·실가동·설비 Down·기타 제약시간의 실제 컬럼, 상호배타성 및 하루/설비 기준 시간
  합계 검증은 실적효율 DB 연결 단계에서 확정한다.
- **수율 실적**도 같은 원칙을 따른다 — 시나리오마다 복제하지 않는 누적 이력이고, 기준은 리비전의
  `RQ_YLD`(월·제품정보·Stack·WF 구분의 `EDS_수율`·`BE_수율`)다. 실적을 `RQ_YLD` 에 덮어쓰지
  않는다. 원천 컬럼·키·집계(투입 가중)·정정 규칙은 아직 계약 전이다(`docs/TODO.md` 「수율 실적
  DB 계약」). 지금 `수율 실적` 화면의 값은 합성 데모(`services/performance_actuals.py`)다.

## 마이그레이션과 복구

- 시뮬레이션 마이그레이션은 `persistence/migrations/`, 설비 전용 마이그레이션은
  `persistence/equipment_migrations/`의 번호순 SQL 파일이다.
- 적용된 파일의 체크섬이 바뀌면 시작을 중단한다. 운영 DB에 적용된 SQL은 수정하지 않고
  다음 번호 파일을 추가한다.
- 신규 시나리오 저장은 메타데이터, RQ 기본 스냅샷, 초기 리비전과 프리셋이 모두 성공해야
  커밋한다. 중간 오류는 전체 롤백한다.
- 설비 운영 저장도 리비전 메타데이터와 세 입력 스냅샷을 단일 트랜잭션으로 커밋한다.
- 목록에서 치우는 기본 수단은 보관이다 — `app_meta.scenario.status` 를 `ARCHIVED` 로
  바꾸고 `app_meta.dataset.status` 도 함께 옮긴다. 상태 컬럼은 `0001_initial.sql` 의
  `CHECK (status IN ('ACTIVE','ARCHIVED'))` 를 그대로 쓰므로 새 마이그레이션이 없다.
  보관 시 공용 GAP 비교 프로필(`app_meta.global_comparison_scenario`)의 대상과 그 시나리오를 가리키는 주요
  Case(`app_meta.global_main_cases`)도 비운다 — 되돌려도 지정은 돌아오지 않는다. 영구 삭제도 같다.
- 영구 삭제는 물리 삭제다. 지울 표는 `information_schema` 에서 소유 컬럼
  (`scenario_id`·`dataset_id`·`revision_id`)으로 찾아 한 트랜잭션에서 지운다. 표 목록을
  손으로 적으면 새 마이그레이션의 표가 빠져 주인 없는 행이 남고, 그 누락은 삭제한 뒤에야
  드러난다. DuckDB는 지운 페이지를 파일에 되돌려주지 않아 파일 크기는 줄지 않는다.
- STEP·MCP 경로 키 도입 전 첫 행 유지 방식으로 저장한 사내 검증 시나리오는 의미를
  추정해 보정하지 않는다. 기존 시나리오를 제거하고 원천 Query로 신규 등록한다.
- 마이그레이션 0015가 만드는 공용 공정 표시명 프로필은 `RQ_*` 어느 표에도 오버레이하지
  않는다. 표시순서와 달리 리비전 스냅샷 캐시를 비울 이유가 없고, 화면 Figure 캐시는
  프로필 버전 정수를 키 원소로 받아 무효화한다. 시나리오 `content_token`은 재발급하지
  않는다.
- 마이그레이션 0014는 이미 저장된 EDP-TSV 행의 `WF 구분` `Top`을 `Top_e`로 이관해 신규 파생과
  값을 맞춘다. `ref_data`·`rev_data`의 RQ 7개씩을 갱신하고, 판별은 `RQ_PKG_PLAN`의 `제품타입`과
  원천의 제품→타입 매핑을 쓰며 매핑이 갈리는 제품은 건드리지 않는다.
- 두 DuckDB 파일은 서로 독립적으로 백업·복원한다. 백업은 라이브 파일 복사가 아니라
  `persistence/snapshot_export.py`의 `ATTACH` + `_sql_helpers.copy_database()` 스냅샷이며, 설치할 때
  기존 파일과 `.wal`은 지우지 않고 `data/temp/objectstore/superseded/`로 물러난다. 사내 S3 호환
  스토리지와의 왕복은 앱을 끈 채 `scripts/sync_object_storage.py`의 `init`·`pull`·`push`를 사람이
  실행하고, 앱은 `sync_boot.py`가 켠 `persistence/sync_state.py` 사이드카에 변경 표시만 남긴다.
  사람이 해야 하는 절차는 `docs/objectstore_setup.md`에 있다.
- 새 DuckDB 파일은 `persistence/_sql_helpers.py`의 `DUCKDB_BLOCK_SIZE`(16 KiB)로 만든다.
  DuckDB 기본 블록 256 KiB는 행이 2,767개뿐인 첫 부팅 DB도 24.5 MiB로 부풀리며, 16 KiB에서는
  같은 내용이 4.2 MiB이고 리비전 저장당 증가분도 2.5~9.5 MB에서 0.6 MB로 줄어든다. 블록 크기는
  파일 생성 시점에 각인되므로 기존 파일은 영향을 받지 않는다. 같은 파일에 configuration이 다른
  연결이 하나라도 섞이면 DuckDB가 연결을 거부하므로 모든 연결은 `_sql_helpers.connect()`를 쓴다.
- DuckDB는 삭제·재작성으로 생긴 free 블록을 파일 안쪽에 남기고 `CHECKPOINT`·`VACUUM`으로 파일을
  줄이지 않는다. 공간 회수와 기존 파일의 블록 크기 전환은 `scripts/compact_duckdb.py`가 하는
  `ATTACH` + `_sql_helpers.copy_database()` 재구축뿐이며, 교체 전에 표 목록과 행 수 일치를 검증한다.
  `COPY FROM DATABASE` 는 외래 키 자식 행을 부모보다 먼저 넣어 제약 위반으로 멈출 수 있으므로(설비
  DB 의 `equipment_ops.revision` 자식 표들) `copy_database()` 는 구조만 `COPY FROM DATABASE … (SCHEMA)`
  로 옮기고 데이터는 부모 표부터 한 트랜잭션 안에서 `INSERT … SELECT` 한다. 스냅샷 내보내기도 같은 길이다.
  WAL이 남아 있으면 실행을 중단하지만 유휴 상태의 앱은 잠금도 WAL도 남기지 않으므로 반드시
  앱을 정상 종료한 뒤 실행한다. 원본은 행 수를 세는 순간부터 검증이 끝날 때까지 한 연결에서
  READ_ONLY 로 붙들어 그동안 앱의 쓰기 연결을 막고, managed 모드에서는 살아 있는 심장박동을 보면
  시작 전에 중단한다. 심장박동은 rerun 때만 적히므로 최근 90초 안에 rerun 한 앱만 잡히고 유휴
  앱은 managed 모드에서도 보이지 않는다. 교체 직전 닫고 옮기는 수 ms 의 틈은 남는다.
