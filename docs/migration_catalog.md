# SQL 마이그레이션 목적·출처 카탈로그

기존 SQL 마이그레이션은 적용 시점의 파일 체크섬을 DuckDB에 저장하므로 주석을 포함한
어떠한 사후 수정도 금지한다. 이 문서는 파일을 변경하지 않고 목적을 설명하기 위한
sidecar 카탈로그다.

- 문서화 기준일: 2026-09-03 KST
- 문서화 Agent: OpenAI Codex
- 문서화 Model: GPT-5 (exact runtime variant unavailable)
- 기존 마이그레이션의 원래 작성 Agent·Model·작성일: 확인 불가, Git 기록 참조

신규 SQL 마이그레이션은 최초 생성할 때 `AGENTS.md`의 다섯 줄 헤더를 포함하고 이
카탈로그에도 추가한다. 한 번이라도 적용한 SQL은 헤더를 포함해 절대 수정하지 않고,
변경이 필요하면 다음 번호의 마이그레이션을 추가한다.

| 파일 | 목적 |
|---|---|
| `src/capa_simulation/persistence/migrations/0001_initial.sql` | 시나리오 DB의 메타·원천·기준·리비전·결과 스키마와 초기 테이블을 생성한다. |
| `src/capa_simulation/persistence/migrations/0004_core_data_raw.sql` | 시나리오 데이터셋에 78컬럼 typed Core Data raw와 관련 메타데이터를 추가한다. |
| `src/capa_simulation/persistence/migrations/0005_official_release.sql` | 불변 시나리오 리비전의 append-only 공식 발행 이력을 추가한다. |
| `src/capa_simulation/persistence/migrations/0006_route_sequence_keys.sql` | UPEH·Lot/WF 측정률에 Area·STEP·MCP 경로 식별키를 추가해 이관한다. |
| `src/capa_simulation/persistence/migrations/0007_revision_reqb.sql` | `RQ_REQB`를 리비전 소유 편집 스냅샷으로 저장한다. |
| `src/capa_simulation/persistence/migrations/0008_revision_equipment_counts.sql` | 보유·대여·가용 설비대수 RQ를 리비전별 편집 스냅샷으로 저장한다. |
| `src/capa_simulation/persistence/migrations/0009_standard_target_preset_process.sql` | 표준 목표 Capa 공정 필터의 리비전별 공용 기본값을 저장한다. |
| `src/capa_simulation/persistence/migrations/0010_global_display_order.sql` | 시나리오와 독립된 공용 표시순서 프로필·규칙·버전 이력을 저장한다. |
| `src/capa_simulation/persistence/equipment_migrations/0001_initial.sql` | 가용설비 DB의 메타·운영 스키마와 초기 리비전·기준·일정 테이블을 생성한다. |
| `src/capa_simulation/persistence/equipment_migrations/0002_unified_equipment_input.sql` | 설비 호기와 운영 비가동을 통합 입력하는 스냅샷 구조를 추가한다. |
| `src/capa_simulation/persistence/equipment_migrations/0003_equipment_master_contract.sql` | 30컬럼 설비 마스터 계약과 계약 버전을 추가한다. |
| `src/capa_simulation/persistence/equipment_migrations/0004_qual_confirmation_status.sql` | 설비 마스터에 Qual 확정상태를 추가하고 기존 값을 이관한다. |
| `src/capa_simulation/persistence/equipment_migrations/0005_standard_target_availability.sql` | 표준 목표 Capa용 공정·주차별 수동 가용대수 최신값을 저장한다. |
