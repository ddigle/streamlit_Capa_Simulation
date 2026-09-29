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
| `src/capa_simulation/persistence/migrations/0015_global_process_rename.sql` | 시나리오와 독립된 공용 공정 표시명 프로필(원본 공정 → 화면 표시명)과 버전 번호를 저장한다(단일 행 프로필, 원본·표시명 UNIQUE 로 1:1을 받치며 이전 규칙은 보존하지 않는다). |
| `src/capa_simulation/persistence/migrations/0016_standard_target_preset_view_settings.sql` | 표준 목표 Capa 「조회·집계 설정」(시작일·종료일·상세 토글·제품 분류 수준·출력 지표)을 리비전 프리셋 스칼라 컬럼으로 저장한다(과거 리비전은 NULL 로 읽혀 기본값으로 열린다). |
| `src/capa_simulation/persistence/migrations/0017_scenario_list_order.sql` | 시나리오 목록의 사용자 지정 누적 순서 컬럼을 추가하고, 보관 기능이 삭제로 바뀌면서 갈 곳이 없어진 `ARCHIVED` 시나리오·데이터셋을 활성으로 되돌린다. |
| `src/capa_simulation/persistence/migrations/0018_global_advance_load.sql` | 시나리오와 독립된 공용 선행 투입 물량 프로필(월별 억Gb 가감분)과 버전 번호를 저장한다(단일 행 프로필, 월이 기본키라 한 달에 한 값이며 이전 값은 보존하지 않는다). |
| `src/capa_simulation/persistence/migrations/0019_global_past_data.sql` | 적재 시점 이전 과거 구간의 월별 Density·Wafer Total, 계획 세부수량, 공정별 확보율을 시나리오와 독립된 공용 프로필로 저장한다(단일 행 프로필, 교체마다 version+1). |
| `src/capa_simulation/persistence/equipment_migrations/0001_initial.sql` | 가용설비 DB의 메타·운영 스키마와 초기 리비전·기준·일정 테이블을 생성한다. |
| `src/capa_simulation/persistence/equipment_migrations/0002_unified_equipment_input.sql` | 설비 호기와 운영 비가동을 통합 입력하는 스냅샷 구조를 추가한다. |
| `src/capa_simulation/persistence/equipment_migrations/0003_equipment_master_contract.sql` | 30컬럼 설비 마스터 계약과 계약 버전을 추가한다. |
| `src/capa_simulation/persistence/equipment_migrations/0004_qual_confirmation_status.sql` | 설비 마스터에 Qual 확정상태를 추가하고 기존 값을 이관한다. |
| `src/capa_simulation/persistence/equipment_migrations/0005_standard_target_availability.sql` | 표준 목표 Capa용 공정·주차별 수동 가용대수 최신값을 저장한다. |
| `src/capa_simulation/persistence/equipment_migrations/0006_manager_name.sql` | 설비 마스터에 담당자 컬럼을 추가한다. |
| `src/capa_simulation/persistence/equipment_migrations/0007_floor_layout_profile.sql` | 동·층별 배경 도면과 캔버스 치수를 리비전과 무관한 단일 저장값으로 보관한다. |
| `src/capa_simulation/persistence/equipment_migrations/0008_equipment_conversion_ratio.sql` | 설비 마스터에 공정 내 모델별 생산성 환산비(기준 1.0)를 추가한다. DuckDB 가 `ADD COLUMN` 에 제약을 받지 않아 양수 검사는 서비스 검증이 맡는다. |
| `src/capa_simulation/persistence/equipment_migrations/0009_process_cutoff.sql` | 공정별 Cut-off(그 공정 이후 입고까지의 표준 납기) 일수를 리비전 없는 현행값으로 저장한다. TAT 와 공정 선후관계가 저장소에 없어 파생값이 아니라 사람이 적는 원장이고, `product_scope` 는 나중 제품 축이 붙을 자리라 지금은 모두 `'*'` 이다. |
| `src/capa_simulation/persistence/equipment_migrations/0010_equipment_parent_unit.sql` | 설비 마스터에 모듈 행을 설비 한 대로 묶는 모체호기(`parent_equipment_id`)를 추가한다. 옛 리비전은 NULL(묶음 없음)이라 대수가 바뀌지 않고, 묶음 규칙은 서비스 검증이 맡는다. |
| `src/capa_simulation/persistence/migrations/0020_global_comparison_scenario.sql` | GAP 의 비교 대상(시나리오·리비전)을 시나리오와 독립된 공용 프로필로 저장한다(단일 행 프로필, 교체마다 version+1). 고르지 않은 상태는 두 값이 NULL 이다. |
| `src/capa_simulation/persistence/migrations/0021_global_execution_capacity.sql` | 실행 Capa 반영(년월·공정별 확보율 증감)을 시나리오와 독립된 공용 프로필로 저장한다(헤더 1행 + 조정 N행, 교체마다 version+1). 증감 단위는 퍼센트포인트이고, 소유 컬럼을 두지 않아 시나리오 삭제·보관이 건드리지 않는다. |
| `src/capa_simulation/persistence/migrations/0022_global_top5_band.sql` | B/N Top5 막대가 표현하는 확보율 구간(기본 50~200%)을 시나리오와 독립된 공용 프로필로 저장한다(단일 행, 교체마다 version+1). 소유 컬럼을 두지 않아 시나리오 삭제·보관이 건드리지 않는다. |
| `src/capa_simulation/persistence/migrations/0023_global_summary_note.sql` | HOME 상단 Summary 공지 문구를 시나리오와 독립된 공용 프로필로 저장한다(단일 행, 교체마다 version+1). 빈 문자열은 「공지를 내린 상태」라 막지 않는다. 소유 컬럼을 두지 않아 시나리오 삭제·보관이 건드리지 않는다. |
| `src/capa_simulation/persistence/migrations/0024_global_key_process.sql` | HOME `주요공정 확보율` 히트맵이 그릴 공정 목록을 시나리오와 독립된 공용 프로필로 저장한다(헤더 1행 + 공정 N행, 교체마다 version+1). 고른 차례가 곧 히트맵 행 순서이고, 0건(전체 해제)도 정상 저장이라 version 이 올라간다. 소유 컬럼을 두지 않아 시나리오 삭제·보관이 건드리지 않는다. |
| `src/capa_simulation/persistence/migrations/0025_voc_board.sql` | VOC 자유 게시판의 글(`voc_post`)과 답글(`voc_reply`) 표를 만든다. 계산에 닿지 않고 시나리오·리비전 어디에도 매이지 않아 시나리오를 지워도 그때 나온 질문이 남는다. 소유 컬럼을 두지 않아 `_owned_tables` 자동 발견이 건드리지 않는다. |
| `src/capa_simulation/persistence/migrations/0026_edp_top_division_retry.sql` | `0014` 가 놓친 EDP-TSV 행의 `WF 구분` 을 `Top_e` 로 다시 맞춘다. `0014` 는 `trim("WF 구분") = 'Top'` 으로 맞댔는데 **원천 표기가 대문자 `TOP`** 이라 운영 데이터에서 0행이었다(주 원인). 여기서는 `upper(trim(...))` 로 대소문자를 가리지 않고, 원천 이름을 파생과 같은 규칙으로 정규화해 조인하며(NBSP 는 RE2 의 `\s` 가 못 잡아 `chr(160)` 으로 따로 바꾼다), 한 제품이 한 타입일 때만 바꾼다. 쓰는 값은 `Top_e` 그대로이고 나머지 행은 원천 표기를 유지한다. 두 번 돌려도 같다. 적용 전 `scripts/inspect_top_remigration.py` 가 같은 식으로 미리 세며, 그 수와 실제 변경분이 같음을 확인했다. |
| `src/capa_simulation/persistence/migrations/0027_display_order_scope_rename.sql` | 표시순서 규칙의 `페이지 구분` 을 실제 페이지 제목으로 옮긴다. 옛 구분자가 어느 것도 실제 페이지 이름이 아니었고 하나가 여러 페이지에 걸쳐 있어(`공정별 Capa` = `기준 정보` 여섯 탭 + `산출 결과` 한 탭) 단순 개명이 아니라 `(옛 페이지, 탭)` 쌍마다 갈 곳을 정한다. `표준 목표` 는 `표준 대비 재공 현황` 과 규칙 한 벌을 공유한다(2026-09-24 사용자 결정). 대응은 `services/display_order_scopes.LEGACY_SCOPE_RENAMES`·`config/bootstrap_display_order.json` 과 같아야 하고 `tests/test_display_order_scopes.py` 가 셋을 함께 본다. 어긋나면 오류가 아니라 **정렬이 조용히 기본값으로 돌아간다.** 옛 이름만 찾으므로 두 번 돌려도 같다. |
| `src/capa_simulation/persistence/migrations/0028_global_key_process_preset.sql` | HOME 주요공정 히트맵의 공정 목록을 **이름 붙은 프리셋 여럿**으로 저장한다(2026-09-29 사용자 요청 — `global_key_process_preset`·`_item`). 헤더는 0024 의 `global_key_process`(version)를 그대로 쓰고, `프리셋순서` 0 번이 새 세션의 기본 프리셋이다. 한 공정이 여러 프리셋에 들 수 있다. 0024 의 단일 목록은 **「기본」 프리셋으로 옮긴다**(비어 있으면 만들지 않는다). 옛 `global_key_process_item` 은 지우지 않는다 — 옛 배포로 되돌려도 HOME 이 열리게 두고, 0028 뒤로는 아무도 읽지 않는다. 두 번 돌려도 같다(대상 표가 비었을 때만 옮긴다). |
