# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 문서 우선순위

작업 전에 `README.md`, `AGENTS.md`, `docs/TODO.md`를 코드와 함께 확인한다. **`AGENTS.md`가
이 저장소의 상세 개발 규칙 문서**이며(파일별 책임, 기준정보 테이블 계약, 핵심 계산 규칙,
Streamlit 구현 규칙, 변경 체크리스트) 이 파일은 그 요약과 진입점이다. 계산식·테이블·화면을
바꾸기 전에는 `AGENTS.md`의 해당 절을 반드시 읽는다. 구조나 계산 규칙을 바꾸면 같은 변경에서
`AGENTS.md`·`README.md`·`docs/TODO.md`도 갱신한다.

직전 세션의 현재 상태와 다음 할 일은 `HANDOFF.md`에 있다. 정본이 아니라 그 시점의 세션
스냅샷이므로 위 세 문서·코드와 어긋나면 위를 따른다.

## 어느 환경에서 열렸는지 먼저 확인한다

이 저장소는 **사외(개발 PC)와 사내(WebIDE) 두 곳에서 열린다.** `git remote -v` 가
`github.com` 이면 사외, 사내 GitHub 주소면 사내다.

**사내에서는 소스를 고치지 않는다.** 코드의 정본은 사외(`origin/main`) 하나이고, 사내에서
만든 수정은 정본이 될 수 없다 — 두 저장소는 서로의 원격을 볼 수 없어 합칠 방법이 없다.
사내에서 쓸 수 있는 곳은 `review/` 뿐이고, 고쳐야 할 것은 코드가 아니라 리뷰 문서로 낸다.
배포 ZIP 적용도 손으로 덮어쓰지 않고 `scripts/apply_deploy_package.py` 로 한다.

사내에서 배포를 받아 적용하는 **한 번의 작업을 처음부터 끝까지** 적은 것은
`docs/internal_update_runbook.md` 다 — 사내 에이전트는 그것을 그대로 따라가면 된다.
전체 절차와 리뷰 문서 양식은 `docs/dual_env_workflow.md` 에 있다. 사내에서 작업을 시작하기
전에 그 문서를 먼저 읽는다.

## 명령

Python은 **3.10.11 64-bit** 고정이고 실행은 `.venv`를 쓴다(PowerShell 기준).

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py     # 앱 실행
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy                      # strict, app.py·app_pages·src·tests·scripts
.\.venv\Scripts\python.exe -m pytest
```

단일 테스트: `.\.venv\Scripts\python.exe -m pytest tests/test_home_page.py::test_home_renders_summary_dashboard_from_the_builtin_seed`

보조 스크립트: `scripts\inspect_wf_division.py`·`scripts\inspect_top_remigration.py`
(사내 실데이터의 `WF 구분`·재이관 전제를 **읽기 전용**으로 재는 것. 값은 찍지 않고
개수만 보고한다), `scripts\audit_top_remigration.py`(`0026` 적용 뒤 이관 결과의 오염·누락을
**읽기 전용**으로 점검), `scripts\inspect_real_data_checks.py`(실데이터로만 답이 나오는 확인 — 기존 결과
대조 분포·원천 `RQ_REQB` 소요기준·설비 DB·BigDataQuery 를 **읽기 전용**으로 재어 집계만 찍는다. 사내 런북
8장이 배포마다 부른다), `scripts\benchmark_home.py`(HOME 단계별 성능), `scripts\validate_duckdb_persistence.py`
(영속성 통합 검증), `scripts\generate_sample_core_data.py`(합성 Core Data 생성).
`scripts\build_deploy_package.py`(사내 배포 ZIP — 배포 세트 규칙과 금지 파일 검사를 갖는다).

`mypy`는 `tests/`·`scripts/`까지 같은 strict 로 검사한다. 테스트에서 끄는 것은 pandas 스칼라
합집합 마찰인 `operator` 하나뿐이고 모듈 셋으로 좁혀 두었다(`pyproject.toml` 의 overrides).
파일 하나만 볼 때도 저장소 루트에서 돌린다(`mypy_path` 가 상대경로다). Streamlit 화면·상태를
바꿨으면 `streamlit.testing.v1.AppTest` 또는 실제 브라우저로 페이지 진입·수정·왕복을 추가
검증한다.

DuckDB 파일은 프로세스 배타 잠금이다. 앱 서버가 떠 있으면 같은 DB를 여는 스크립트·테스트가
`duckdb.IOException`으로 실패한다 — 가상환경 손상이 아니다.

## 아키텍처

계산 파이프라인:

```text
Core_Data (BigDataQuery / data/input/Core_Data.csv / 내장 합성 시드)
  → 78컬럼 검증 + pandas RQ 16개 변환
  → data/capa_simulation.duckdb (시나리오·리비전·공식버전·공용 표시순서)
  → 활성 리비전 → 세션 활성 시나리오
  → 부하량 → 대당 Capa → 소요대수 → 확보율 → B/N → HOME 대시보드
```

계층과 경계:

- `app.py` — 진입점. `navigation.run()` 전에 공식 시나리오 부트스트랩, 공통 사이드바
  (시나리오 컨트롤·조회기간)를 만든다. 페이지 간 공유 위젯은 여기서만 만든다. 부트스트랩보다
  먼저 첫 접속 입장 화면(`components/intro_overlay.py`)을 매 회차 걸고, 부트스트랩 바로 뒤·페이지
  앞에서 그 화면 Summary 가 그릴 공식버전 요약(`components/intro_summary.py`)을 보낸다.
- `src/capa_simulation/navigation.py` — 사이드바 페이지 목록의 **선언 한 곳**. 하위 페이지
  추가·제목 변경뿐 아니라 **새 최상위 그룹**도 여기서 끝난다 — `SIDEBAR_GROUPS`에 한 줄을
  더하면 `app.py`의 박스·CSS 선택자·페이지 순서가 모두 그 선언에서 나온다. HOME과 Admin
  Area만 배치가 달라 `app.py`가 손수 그린다.
- `src/capa_simulation/page_bootstrap.py` — 계산 페이지 공통 진입 절차(활성 리비전·표시순서·
  조회기간)와 공용 예외 튜플 `BOOTSTRAP_ERRORS`. 페이지가 각자 예외 튜플을 만들지 않는다.
- `app_pages/` — UI만. 계산 로직을 페이지에 넣지 않는다.
- `src/capa_simulation/components/` — 페이지가 공유하는 화면 조각(앱·페이지 머리말, 월별 표,
  Figure 그리기 유틸, 탭 상태 등). 둘 이상의 페이지가 같은 UI를 쓰면 여기로 올린다.
- `src/capa_simulation/services/` — 순수 계산 함수. UI 상태에 접근하지 않는다.
- `src/capa_simulation/services/simulation_cache.py` — 계산 함수의 content-addressed
  Streamlit 캐시 래퍼. Streamlit 캐시는 정해진 경계 모듈에만 둔다 — 이 파일,
  `src/capa_simulation/persistence/cache.py`·`equipment_cache.py`(불변 리비전 스냅샷과 공용
  표시순서·설비 스냅샷의 캐시 경계), `src/capa_simulation/components/`의
  `display_order_management.py`·`process_rename_management.py`다. 뒤의 둘은 탭 국소
  예외로, 공용 프로필 `version`만 키로 쓰고 DB를 읽지 않는 CSV 직렬화다(항상 그리는 탭이라
  그 비용이 모든 rerun에 실린다). 그 밖의 모듈에 `@st.cache_data`·`@st.cache_resource`를
  새로 두지 않으며, 이 예외를 늘리려면 여기 목록을 같이 고친다.
- `src/capa_simulation/services/frame_contracts.py` — 서비스 공용 컬럼 계약과 업무 키 정규화.
- `src/capa_simulation/io/reference_cache.py` — 활성 기준정보 경계. 계산 페이지는 기준정보를
  직접 읽지 말고 `get_effective_reference_tables()`만 쓴다.
- `src/capa_simulation/persistence/` — DuckDB 마이그레이션·Repository·모델.
  `src/capa_simulation/design/tokens.py` — 색·서체·표 치수.

DB는 두 개이고 물리적으로 분리한다: 시뮬레이션(`data/capa_simulation.duckdb`)과 가용설비
운영(`data/equipment_availability.duckdb`). 설비 쪽은 전용 마이그레이션·Repository·캐시를 쓰고
시뮬레이션 DB나 `RQ_*`를 읽지 않는다.

### 상태·캐시 불변조건 (AGENTS.md 5장이 전문)

- 편집 적용마다 `revision`을 올리고 `content_token`을 재발급한다. 편집 UI는 `revision`을,
  **계산·Figure 캐시 키는 반드시 `content_token`**을 본다 — `revision` 번호는 내용이 달라도
  겹칠 수 있다.
- 리비전은 append-only다. 과거 리비전을 갱신하지 않고 새 전체 리비전으로만 저장한다.
  공식버전 발행도 append-only.
- 미저장 세션 편집과 저장 리비전을 구분한다. 미저장 편집은 세션 종료 시 사라진다.
- 표시순서는 시나리오에 종속되지 않는 공용 DB 프로필(`app_meta.global_display_order*`)이다.
- 내장 시드는 빈 저장소에만 쓰며 운영 시나리오가 아니다.

### SQL 마이그레이션

적용된 마이그레이션은 **버전 번호로 체크섬을 대조**하므로 주석 추가를 포함해 절대 수정하지
않는다. 후속 번호를 새로 추가한다. **시뮬레이션 DB의 2·3번은 영구 결번**이고 재사용하면
기존 DB에서 앱이 시작조차 못 한다(`tests/test_migration_numbering.py`가 막는다). 신규 SQL은
`--` 형식의 `Purpose` 한 줄과 `docs/migration_catalog.md` 항목을 함께 작성한다.

## 코드 규칙

- **Purpose 헤더**: `app.py`·`app_pages/`·`src/`·`scripts/`·`tests/` 아래 모든 `.py`·`.ps1`
  최상단에 `# Purpose: <단일 책임 한 문장>` 을 유지한다. 파일 책임이 바뀌면 같이 고친다.
  `tests/test_source_metadata.py`가 누락과 SQL 카탈로그 등록을 검사한다.
- 변경 이력·출처를 주석에 적지 않는다. Git commit history가 단일 근거다.
- 내부 컬럼명은 Excel/`Core_Data` 계약과 일치시킨다. 화면 라벨 때문에 원본 컬럼명을 바꾸지
  않는다.
- Streamlit: `use_container_width` 대신 `width="stretch"` / `width="content"`. 페이지 전용
  위젯에는 고유 `key`. 비싼 계산을 탭 안에서 반복하지 말고 캐시된 결과를 탭이 표시만 한다.
- 주석·문서·커밋 메시지는 한국어로 쓴다(기존 코드가 그렇다).

## 로컬 데이터는 합성 표본이다

`data/input/Core_Data.csv`와 `data/capa_simulation.duckdb`, `equipment_samples.py`,
`builtin_seed.py`, `dynamic_capacity.py`의 `DemoProfile`은 **실제 운영 데이터가 아니라
`scripts/generate_sample_core_data.py`의 리터럴에서 나온 합성 데모**다.

- 로컬 DB·CSV 쿼리 결과로 업무 구조를 판단하거나 설계를 바꾸지 않는다. 쿼리는 코드 경로가
  도는지 확인하는 용도다.
- 데이터를 집계해 얻은 수치는 `실측`이 아니라 `샘플 관측`이라고 적고 출처 리터럴을 남긴다.
- 표본 고유 수치(행 수, 공정 수 등)를 계약처럼 문서나 코드에 고정하지 않는다.

## Git 제외 자산

`*.xlsb`·`*.xlsx` 등 Excel, `data/*.duckdb`·`data/*.db`와 보조 파일, `.env`,
`.streamlit/secrets.toml`, `data/input`·`data/output`·`data/temp`의 실제 데이터는 커밋하지
않는다. `config/bootstrap_display_order.json`과 `builtin_seed.py`에는 합성 `DEMO_*` 값만 두고
실제 제품·고객·공정·설비 식별값을 넣지 않는다.
