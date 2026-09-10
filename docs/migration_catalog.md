# SQL 마이그레이션 목적·출처 카탈로그

기존 SQL 마이그레이션은 적용 시점의 파일 체크섬을 DuckDB에 저장하므로 주석을 포함한
어떠한 사후 수정도 금지한다. 이 문서는 파일을 변경하지 않고 목적을 설명하기 위한
sidecar 카탈로그다.

각 마이그레이션을 누가 언제 작성했는지는 Git commit history를 근거로 하며 이 문서에
중복 기록하지 않는다. 기존 마이그레이션의 원래 작성 도구는 확인할 수 없다.

신규 SQL 마이그레이션은 최초 생성할 때 `AGENTS.md`의 `Purpose` 한 줄 헤더를 `--` 형식으로
포함하고 이 카탈로그에도 추가한다. 한 번이라도 적용한 SQL은 헤더를 포함해 절대 수정하지
않고, 변경이 필요하면 다음 번호의 마이그레이션을 추가한다.

## 재사용 금지 번호 (결번)

시뮬레이션 DB의 **2·3번은 영구 결번이다.** 파일은 저장소에 없지만 개발 DuckDB의
`app_meta.schema_migration` 에는 `0002_equipment_operations.sql` ·
`0003_equipment_baseline_double.sql` 이 적용 완료로 남아 있다. 설비 운영을 별도 DuckDB로
분리하면서 파일만 사라지고 적용 기록은 지워지지 않은 것이다. 그 흔적으로 시뮬레이션 DB에
빈 `equipment_ops` 스키마가 남아 있다.

러너는 파일명이 아니라 **버전 번호로 체크섬을 대조**한다(`migration_runner.py`). 그래서
누구든 `0002_*.sql` 또는 `0003_*.sql` 을 새로 추가하면, 그 번호가 이미 적용된 개발 DB에서만
"이미 적용된 DuckDB 마이그레이션이 변경되었습니다" 로 앱이 시작조차 못 한다. 신규 체크아웃
에서는 재현되지 않아 원인을 찾기 어렵다. 새 마이그레이션은 항상 마지막 번호 다음을 쓴다.
`tests/test_migration_numbering.py` 가 이 규칙을 강제한다.

| 파일 | 목적 |
|---|---|
| `src/capa_simulation/persistence/migrations/0001_initial.sql` | 시나리오 DB의 메타·원천·기준·리비전·결과 스키마와 초기 테이블을 생성한다. |
| `src/capa_simulation/persistence/migrations/0004_core_data_raw.sql` | 시나리오 데이터셋에 78컬럼 typed Core Data raw와 관련 메타데이터를 추가한다. |
| `src/capa_simulation/persistence/migrations/0005_official_release.sql` | 불변 시나리오 리비전의 append-only 공식 발행 이력을 추가한다. |
| `src/capa_simulation/persistence/migrations/0006_route_sequence_keys.sql` | UPEH·Lot/WF 측정률에 Area·STEP·MCP 경로 식별키를 추가해 이관한다. |
| `src/capa_simulation/persistence/migrations/0007_revision_reqb.sql` | `RQ_REQB`를 리비전 소유 편집 스냅샷으로 저장한다. |
| `src/capa_simulation/persistence/migrations/0008_revision_equipment_counts.sql` | 보유·대여·가용 설비대수 RQ를 리비전별 편집 스냅샷으로 저장한다. |
| `src/capa_simulation/persistence/migrations/0009_standard_target_preset_process.sql` | 표준 목표 Capa 공정 필터의 리비전별 공용 기본값을 저장한다. |
| `src/capa_simulation/persistence/migrations/0010_global_display_order.sql` | 시나리오와 독립된 공용 표시순서 프로필·규칙과 버전 번호를 저장한다(단일 행 프로필, 이전 규칙은 보존하지 않는다). |
| `src/capa_simulation/persistence/migrations/0011_virtual_product_reference.sql` | `RQ_CHIP_QTY`·`RQ_CHIP_EQ`를 리비전 소유 편집 스냅샷으로 승격하고, 가상 제품(기존 제품 복제 등록) 목록을 리비전 메타에 기록한다. |
| `src/capa_simulation/persistence/migrations/0012_fractional_core_columns.sql` | `모듈수`·`Side반영률`·`MCP_Chip_Ratio`·`설비보유HCB`를 DOUBLE로 넓혀 소수값을 받는다. |
| `src/capa_simulation/persistence/migrations/0013_pkg_plan_product_type.sql` | `RQ_PKG_PLAN`에 `제품타입`·`Pack Code`를 추가하고 원천에서 되채운다. |
| `src/capa_simulation/persistence/migrations/0014_edp_top_division.sql` | 이미 저장된 EDP-TSV 행의 `WF 구분` `Top`을 `Top_e`로 이관한다. |
| `src/capa_simulation/persistence/equipment_migrations/0001_initial.sql` | 가용설비 DB의 메타·운영 스키마와 초기 리비전·기준·일정 테이블을 생성한다. |
| `src/capa_simulation/persistence/equipment_migrations/0002_unified_equipment_input.sql` | 설비 호기와 운영 비가동을 통합 입력하는 스냅샷 구조를 추가한다. |
| `src/capa_simulation/persistence/equipment_migrations/0003_equipment_master_contract.sql` | 30컬럼 설비 마스터 계약과 계약 버전을 추가한다. |
| `src/capa_simulation/persistence/equipment_migrations/0004_qual_confirmation_status.sql` | 설비 마스터에 Qual 확정상태를 추가하고 기존 값을 이관한다. |
| `src/capa_simulation/persistence/equipment_migrations/0005_standard_target_availability.sql` | 표준 목표 Capa용 공정·주차별 수동 가용대수 최신값을 저장한다. |
| `src/capa_simulation/persistence/equipment_migrations/0006_manager_name.sql` | 설비 마스터에 담당자 컬럼을 추가한다. |
