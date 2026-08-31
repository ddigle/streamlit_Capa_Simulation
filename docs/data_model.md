# DuckDB 데이터 모델

마지막 갱신일: 2026-09-01

## 운영 원칙

- 시뮬레이션 운영 파일은 `data/capa_simulation.duckdb`, 설비 운영 파일은
  `data/equipment_availability.duckdb`이며 둘 다 Git과 배포 패키지에 포함하지 않는다.
- `시나리오 1개 = 데이터셋 1개`다. 새 시나리오는 RQ 16개를 물리 복제하고 기존
  데이터셋을 덮어쓰지 않는다.
- 데이터셋의 읽기 전용 기준정보를 바꾸려면 새 시나리오를 만든다.
- 계획·수율·Capa·설비대수 입력 12개와 표시순서 변경은 불변 전체 리비전으로 저장한다.
- 리비전은 조회기간, B/N 포함 공정, 표준 목표 Capa 공정 기본값, 확보·경고 기준
  프리셋을 함께 소유한다.
- 공식버전은 특정 불변 리비전을 가리키는 append-only 발행 이력이며 최신 발행을 새 웹
  세션의 기본값으로 사용한다.
- 저장과 보관 상태 변경은 Repository의 쓰기 잠금과 DuckDB 트랜잭션 안에서 실행한다.
- 기존 보유대수, 호기 마스터와 운영 비가동 일정은 시뮬레이션 DB·시나리오·`RQ_*`와
  독립된 불변 전체 스냅샷 리비전으로 저장한다.
- 앱은 단일 Streamlit 서버 프로세스와 서로 독립된 로컬 DuckDB 두 개를 전제로 한다.
- 시나리오 DB가 완전히 비어 있으면 Git에 포함된 비민감 표시순서와 합성 78컬럼 Core
  Data로 초기 데이터셋·리비전·공식버전을 만든다. 공식버전이나 사용자 시나리오가 있으면
  자동 부트스트랩은 상태를 변경하지 않는다.

## 스키마 관계

```text
# data/capa_simulation.duckdb
app_meta.scenario 1 ── 1 app_meta.dataset
       │                       │
       │                       ├── N raw_data.core_data
       │                       ├── 78 raw_data.source_column_profile
       │                       └── N ref_data.rq_* (16개 기본 스냅샷)
       │
       └── N app_meta.scenario_revision
                    │
                    ├── N rev_data.rq_* (편집 12개 + 표시순서)
                    ├── 1 app_meta.scenario_preset
                    ├── N app_meta.scenario_preset_process
                    └── N app_meta.scenario_preset_standard_target_process

app_meta.official_release N ── 1 app_meta.scenario_revision
        └── 전역 증가 release_no의 공식 발행 이력

# data/equipment_availability.duckdb
equipment_ops.revision
       ├── N equipment_ops.baseline_snapshot
       ├── N equipment_ops.equipment_master_snapshot
       └── N equipment_ops.downtime_schedule_snapshot

equipment_ops.standard_target_weekly_availability
       └── 공정·Weeknum별 비버전 최신 가용대수
```

DuckDB 1.5.5는 서로 다른 스키마 사이의 외래 키를 만들 수 없으므로 스키마 간 FK는
DDL에 선언하지 않는다. 대신 Repository가 같은 트랜잭션 안에서 소유 관계, 상위 리비전,
행 수와 필수 테이블을 검증한다. 각 테이블의 PK·UNIQUE·CHECK 제약은 DB에 유지한다.

## 스키마별 책임

### `app_meta`

- `schema_migration`: 적용한 SQL 마이그레이션 버전과 체크섬
- `scenario`: 이름, 원천 시뮬레이션 코드/명, 활성·보관 상태, 현재 최신 리비전
- `dataset`: 시나리오 소유 데이터셋, 원천 등록·적재 시각, 원천 해시, 변환 버전
- `scenario_revision`: 증가하는 리비전 번호, 부모 리비전, 입력 해시와 변경 메모
- `scenario_preset`: 조회 시작·종료월, 내부 비율의 확보·경고 기준, 프리셋 해시
- `scenario_preset_process`: 리비전별 B/N 집계 포함 공정과 저장 순서
- `scenario_preset_standard_target_process`: 리비전별 표준 목표 Capa 공정 공용 기본값과
  저장 순서. 행이 없으면 전체 공정으로 해석한다.
- `official_release`: 전역 공식버전 번호, 대상 시나리오·리비전, 공식버전명·메모·발행시각

`scenario_revision.parent_revision_id`는 과거 리비전에서 새 리비전을 저장하는 분기 이력을
보존한다. `scenario.active_revision_id`는 가장 최근에 저장한 리비전을 가리키며, 사용자는
드롭다운에서 그보다 오래된 리비전도 별도로 불러올 수 있다.

`official_release`는 과거 행을 수정하지 않는다. 가장 큰 `release_no`의 대상 리비전이 새
세션의 기본값이며, 대상 리비전은 해당 시나리오 소유인지 Repository가 검증한다. 최신 공식
시나리오는 기본 진입점 단절을 막기 위해 다른 공식버전을 먼저 발행하기 전에는 보관할 수 없다.

### `ref_data`

시나리오 생성 시 데이터셋 소유로 복제하는 RQ 16개다.

```text
RQ_PKG_PLAN        RQ_YLD           RQ_CHIP_QTY
RQ_CHIP_EQ         RQ_DISPLAY_ORDER RQ_REQB
RQ_UPEH            RQ_RUN_RATE      RQ_VITAL
RQ_MODULE          RQ_RUN_DAY       RQ_LOT_RATIO
RQ_WF_RATIO        RQ_EQP_OWN       RQ_EQP_LENT
RQ_EQP_AVBL
```

기술 키는 `(dataset_id, source_row_no)`다. `source_row_no`는 DataFrame의 현재 행 순서를
1부터 부여하며, 원본 컬럼명과 순서를 유지한다. 업무 고유 키는
`config/data_contract.yaml`의 `derived_keys`에 테이블별로 정의한다.
`RQ_UPEH`·`RQ_LOT_RATIO`·`RQ_WF_RATIO`는 생산계획년월·Area·공정·`STEP_SEQ`·
`MCP_SEQ`·양산구분·제품정보·Stack·WF 구분을 경로 키로 사용한다. `RQ_REQB`와 대당
Capa를 연결할 때도 Area·STEP·MCP를 포함해 정확히 일치시킨다.

### `rev_data`

리비전마다 다음 13개 테이블의 전체 스냅샷을 저장한다.

```text
RQ_PKG_PLAN  RQ_YLD       RQ_UPEH      RQ_RUN_RATE
RQ_VITAL     RQ_RUN_DAY   RQ_LOT_RATIO RQ_WF_RATIO
RQ_REQB      RQ_EQP_OWN   RQ_EQP_LENT   RQ_EQP_AVBL
RQ_DISPLAY_ORDER
```

기술 키는 `(revision_id, source_row_no)`다. 리비전을 읽을 때 이 13개는 `ref_data`의 같은
이름 테이블을 대체하고, 나머지 3개 읽기 전용 테이블은 데이터셋 기본 스냅샷을 사용한다.
`RQ_REQB`는 STEP 구성 변경을 리비전별로 재현하기 위해 데이터셋 기본본과 별도로 저장한다.

### `raw_data`

`core_data`는 `config/data_contract.yaml`에 정의한 원천 78개 컬럼을 VARCHAR·BIGINT·DOUBLE
타입으로 저장한다. 원천 행은 `(dataset_id, source_row_no)` 기술 키와 `row_hash`로 보존하고,
`source_column_profile`에는 원천/nullable dtype, null 수와 고유값 수를 컬럼 순서대로
저장한다. 원천 null은 보존하며 RQ 변환 단계에서 업무 키의 null·빈값과 동일 키의 값
충돌을 검증한다.

동일 시뮬레이션 코드는 불변 원천으로 취급한다. 행 순서와 무관한 multiset 데이터 해시가
같으면 다른 시나리오에 전체 물리 복제할 수 있지만, 해시가 다르면 등록을 거부한다.

### `result_data`

`simulation_run` 메타데이터 골격만 준비되어 있다. 계산 결과 테이블과 진단 데이터 저장은
후속 단계이며 Plotly Figure 자체는 저장하지 않는다.

### 설비 전용 DB의 `equipment_meta`, `equipment_ops`

- `equipment_meta.schema_migration`: 설비 DB에만 적용하는 SQL 버전과 체크섬
- `revision`: 설비 운영 입력의 증가 리비전 번호, 변경 메모, 입력 해시와 저장 시각
- `baseline_snapshot`: 공정·분류별 기존 보유대수와 비고의 전체 스냅샷
- `equipment_master_snapshot`: 호기를 키로 공정대/소분류, 참고 속성, 분류1~3, 동·층,
  Space X/Y 좌표와 X/Y 크기, 제진대·물류·입고·Qual·반출·이설 일정, Qual 실행관리용
  확정상태, 장기보관·기존설비·
  레이아웃 표시 여부, 호기이력과 비고를 저장하는 전체 스냅샷
- `downtime_schedule_snapshot`: 호기·유형·시작일 자연키와 종료일·상세사유·비고의
  전체 스냅샷
- `standard_target_weekly_availability`: 표준 목표 Capa 수동 입력용 공정·Weeknum별
  가용대수 최신값. 리비전을 만들지 않고 같은 키를 갱신하며 명시적 초기화 시 전체 삭제한다.
- `schedule_snapshot`: 마이그레이션 1에서 생성한 기존 입고·셋업 일정 보존용 레거시 테이블.
- `equipment_snapshot`, `downtime_snapshot`: 마이그레이션 2 계약의 과거 리비전
  보존용 레거시 테이블. 신규 저장은 마이그레이션 3의 두 스냅샷 테이블을 사용한다.

현재 화면은 가장 최근 리비전을 편집 원본, 가용설비 대시보드와 Space 현황의 공통 원천으로
사용한다. 일정 수정, 신규 호기·비가동 추가 또는 행 삭제 후 저장하면 기존 리비전을 갱신하지
않고 세 입력의 새 전체 스냅샷을 추가한다. 기존 보유대수는 즉시 가용, 신규 호기는 입고일부터
총대수, Qual일부터 가용대수로 계산한다. 장기보관과 활성 운영 비가동은 가용에서 제외하고,
반출·이설 실행일부터 보유·가용·레이아웃에서 제외한다.
확정상태는 Qual 일정의 계획·확정·완료·지연 모니터링 용도이며 가용 산식에는 사용하지 않는다.
집계형 기존 보유대수는 호기·좌표가 없어 Space 배치에는 포함하지 않는다. 시뮬레이션 DB의
공정·설비 테이블은 읽지 않으며, 공정명은 향후 Dynamic Capa 연결 계층의 호환 키로만 보존한다.

## Dynamic Capa 실적 이력 확장 원칙

Dynamic Capa의 표준과 실적은 수명주기가 다르므로 같은 리비전 스냅샷에 넣지 않는다.

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

## 마이그레이션과 복구

- 시뮬레이션 마이그레이션은 `persistence/migrations/`, 설비 전용 마이그레이션은
  `persistence/equipment_migrations/`의 번호순 SQL 파일이다.
- 적용된 파일의 체크섬이 바뀌면 시작을 중단한다. 운영 DB에 적용된 SQL은 수정하지 않고
  다음 번호 파일을 추가한다.
- 신규 시나리오 저장은 메타데이터, RQ 기본 스냅샷, 초기 리비전과 프리셋이 모두 성공해야
  커밋한다. 중간 오류는 전체 롤백한다.
- 설비 운영 저장도 리비전 메타데이터와 세 입력 스냅샷을 단일 트랜잭션으로 커밋한다.
- 시나리오 보관은 `ACTIVE → ARCHIVED` 논리 변경이며 물리 삭제하지 않는다.
- STEP·MCP 경로 키 도입 전 첫 행 유지 방식으로 저장한 사내 검증 시나리오는 의미를
  추정해 보정하지 않는다. 기존 시나리오를 제거하고 원천 Query로 신규 등록한다.
- 두 DuckDB 파일은 서로 독립적으로 백업·복원하며 정책은 운영 배포 절차에서 확정한다.
