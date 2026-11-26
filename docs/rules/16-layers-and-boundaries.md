# CLAUDE 아키텍처 — 아키텍처

## 아키텍처

계산 파이프라인:

```text
Core_Data (BigDataQuery / 원천 CSV 올림 / data/input/Core_Data.csv / 내장 합성 시드)
  → 78컬럼 검증 + pandas RQ 16개 변환
  → data/capa_simulation.duckdb (시나리오·리비전·공식버전·공용 표시순서)
  → 활성 리비전 → 세션 활성 시나리오
  → 부하량 → 대당 Capa → 소요대수 → 확보율 → B/N → HOME 대시보드
```

계층과 경계:

- `app.py` — 진입점. `navigation.run()` 전에 공식 시나리오 부트스트랩, 공통 사이드바
  (시나리오 컨트롤·조회기간)를 만든다. 페이지 간 공유 위젯은 여기서만 만든다(화면 하나의 조작 상자 —
  `sidebar_status.PAGE_BOX_PREFIX`, 지금은 Space 「Space 도면」 하나 — 는 그 페이지가 조건 카드보다 먼저 세운다, AGENTS 9장). 부트스트랩보다
  먼저 첫 접속 입장 화면(`components/intro_overlay.py`)을 매 회차 걸고, 부트스트랩 바로 뒤·페이지
  앞에서 그 화면 Summary 가 그릴 공식버전 요약과 `Introduce` 티저 칸(`components/intro_summary.py`)을 보낸다.
  페이지 바로 앞에는 머리 띠 아래 연 화면 탭 줄(`components/page_tabs.py`, 상태 `page_tabs_state.py`)을 그리고
  `st.navigation()` 바로 뒤에서 탭이 적어 둔 이동을 한다.
- `src/capa_simulation/alerts.py` · `components/alert_center.py` — 알림 한 꼴(2026-11-03 D1 ~ D6). 등록부·사건/상태 표지 API 와,
  `app.py` 가 탭 줄 바로 뒤에 그리는 알림 칸(오른쪽 아래 알림창·툴바 Alarm·변경 칩). 동작 결과는 `queue_flash`(성공은 알림창으로만),
  조건 경고는 `alerts.state`(자리에 그리지 않음 — 화면 쪽 범위·딸린 표 조각은 `components/state_alerts.py`) — AGENTS 9장 「알림 칸」.
  페이지 본문에 설정 단추를 두지 않고 사이드바 설정 상자(`components/settings_box.py`)로 둔다(2026-11-03).
- `capa_server.py` — C-DEP 운영 진입점(시작 스크립트가 `streamlit run capa_server.py --server.port 8080` 으로 띄운다). `app.py` 를
  `st.App` 으로 감싸 통합인증 경로·문지기를 같은 프로세스에 붙인다(`src/capa_simulation/auth/`). 개발·WebIDE·시험·화면 확인은
  `app.py` 로 띄운다(통합인증 꺼짐). 자세한 것은 `docs/sso_setup.md`. 통합인증이 켜진 기동에서만 접속 · 작업 감사 기록기를
  켠다(`src/capa_simulation/audit/` — 메모리 큐 → 로컬 스풀 → 버킷 `audit/` 새 객체, 두 DB · 마이그레이션 밖. Admin Area 다섯째 탭
  「접속 · 작업 기록」 은 개발자만). 꺼진 곳(개발 · WebIDE · 시험 · 사내 PC)은 기록기 · 탭 호출이 0 이다.
  규칙은 AGENTS 5장 40, 운영은 `docs/audit_log_operations.md`.
- `src/capa_simulation/navigation.py` — 사이드바 페이지 목록의 **선언 한 곳**. 하위 페이지
  추가·제목 변경뿐 아니라 **새 최상위 그룹**도 여기서 끝난다 — `SIDEBAR_GROUPS`에 한 줄을
  더하면 `app.py`의 박스·CSS 선택자·페이지 순서가 모두 그 선언에서 나온다. HOME과 Admin
  Area만 배치가 달라 `app.py`가 손수 그린다. 계산 그룹은 셋이다(2026-10-17 — 2026-11-02 실행 관리와 Dynamic 사이에 「생산 진도」 상자가 섰다 — 머리 화면은 모듈 화면이 들어올 자리 하나(2026-11-03)) — Static Capa(약속) →
  실행 관리(이행: 공정 Capa 상세·필요 단축 일정·제약 시뮬레이션·가용설비·Space·실적 셋) → Dynamic Capa(실적:
  실현 Capa·재공). 「Dynamic」 은 실적 Capa 에만 쓰고, 설비 일정으로 낸 가용대수는 화면에서 「설비 일정
  기준 가용대수」, HOME 의 확보율 % 손입력은 「확보율 보정」이다 — 코드·키·DB 이름(`dynamic_*`·`execution`)은
  그대로다(AGENTS 1장 「세 영역」). 모듈 화면은 이 선언 밖이다 — `module_registry.py` 가 실행 때 `modules/*/module.json` 을 읽어
  별도 상자 「모듈」 을 세우고(켜진 모듈이 없으면 상자가 없다) `SIDEBAR_GROUPS` 에 넣지 않는다. 색인 화면 `app_pages/internal_modules.py`
  만 `ALL_SPECS` 에 있다.
- `src/capa_simulation/page_bootstrap.py` — 계산 페이지 공통 진입 절차(활성 리비전·표시순서·
  조회기간)와 공용 예외 튜플 `BOOTSTRAP_ERRORS`. 페이지가 각자 예외 튜플을 만들지 않는다.
- `app_pages/` — UI만. 계산 로직을 페이지에 넣지 않는다.
- 모듈(`modules/<id>/`) — 코어 공개 창구 `module_api.py` 만 import 하고 코어는 모듈을 import 하지 않는다.
  배경 스레드·`subprocess`·전역 CSS·`st.sidebar`·`st.set_page_config` 를 쓰지 않고 키는 `mod_<id>__` 로 시작한다. 실행 감싸기(그 화면만 오류 카드)는
  `module_runtime.py`, 콜백·프래그먼트 감싸기는 `module_api` 의 `ctx.callback`·`ctx.guard`, 기록은 `module_failures.py` — `scripts/check_module.py` 가
  규칙을 보고 모듈 시험은 감시 러너 `scripts/module_test_runner.py` 로 돈다.
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
  새로 두지 않으며, 이 예외를 늘리려면 여기 목록을 같이 고친다. 모듈의 `st.cache_*` 는 이 목록 밖이다 — 그 모듈의 `cache.py` 한 파일에만 두고(화면 파일에 두면 `__main__` 이라 모듈끼리
  칸이 겹친다) `check_module.py`(M12)가 본다.
- `src/capa_simulation/auto_update_scheduler.py` — 공식버전 자동 갱신 예약. 앱 프로세스의 **배경
  스레드 둘 가운데 하나**이고 실행 줄 환경변수 `CAPA_AUTO_OFFICIAL_UPDATE=1` 이 있을 때만 `app.py` 부트스트랩
  뒤 첫 회차에 선다(스레드 이름으로 프로세스에 하나 — `st.cache_resource` 를 쓰지 않아 캐시 경계가
  아니다). 스레드 안에서는 실행 문맥이 없으므로 `st.*`·`st.session_state`·`st.cache_data` 래퍼를
  부르지 않고 순수 코어만 쓰며, 캐시 정리는 전역 범위 `st.cache_data` 의 `.clear()` 만 부른다
  (AGENTS.md 5장 4·9장 「배경 스레드」). 예약 하나와 동기화 일꾼 하나뿐이고 더 세우지 않는다.
- `src/capa_simulation/object_sync_worker.py` — 정본 버킷 동기화 일꾼(스레드 `capa-object-sync`). `capa_server.py` 가
  시작 때 세우고 `managed` + 시작 받기의 부트 기록(`sync_boot`)이 있을 때만 선다 — `app.py` 개발 실행 · 사내 PC · 시험에는 없다.
  저장을 20 ~ 60초 모아 세대를 올리고 공식 발행 · 부하 예외 선언 판 저장은 바로 올리며 하루 한 번 정리한다. 감사 기록이 켜진 서버면 같은 고리에서 감사
  스풀 비우기(10초) · 올리기(5분 또는 200줄 — DB 올리기보다 먼저, DB 멈춤과 상관없이) · 일별 묶음 · 미러도 한다(`audit/shipper.py` —
  새 스레드 없음, 감사 실패는 DB 실패 수를 건드리지 않는다). Streamlit 을 import 하지 않고 캐시를 건드리지
  않는다. 차례는 `object_sync_engine.py`(유실을 막는 순서), 판정은 `services/object_storage_manifest.py`.
- `src/capa_simulation/services/frame_contracts.py` — 서비스 공용 컬럼 계약과 업무 키 정규화.
- `src/capa_simulation/io/reference_cache.py` — 활성 기준정보 경계. 계산 페이지는 기준정보를
  직접 읽지 말고 `get_effective_reference_tables()`만 쓴다.
- `src/capa_simulation/persistence/` — DuckDB 마이그레이션·Repository·모델.
  `src/capa_simulation/design/tokens.py` — 색·서체·표 치수.

DB는 두 개이고 물리적으로 분리한다: 시뮬레이션(`data/capa_simulation.duckdb`)과 가용설비
운영(`data/equipment_availability.duckdb`). 설비 쪽은 전용 마이그레이션·Repository·캐시를 쓰고
시뮬레이션 DB나 `RQ_*`를 읽지 않는다(화면 예외는 AGENTS 5장 9 — Static 대비 일정·필요 단축 일정·Space
「필요 단축」 보기는 켠 동안만). 거꾸로 설비 DB 를 여는 시뮬레이션 쪽 화면은 `표준 목표`(Static,
주차별 가용대수)와 `공정 Capa 상세`(실행 관리, 설비 운영 스냅샷·Cut-off 를 **읽기만**,
필요 단축 일정의 공용 조회 조건·기준선은 안 읽음), `제약 시뮬레이션`(실행 관리, 공정 Capa 상세와 같은 계획 칸을
**읽기만** — 어느 DB 에도 쓰지 않음), `표준 대비 재공 현황`(Dynamic, 표준 목표의 주차별
가용대수를 **읽기만**), `시나리오 관리`(「설비 시나리오」 탭이 열린 회차에만 — 설비 시나리오 목록·발행)다 — AGENTS 5장 9.
모듈은 코어 두 DB 를 열지 않고 `data/modules/<id>/` 만 쓴다(모듈 마이그레이션은 코어 번호 밖). v1 은 코어 데이터와
이어지지 않는다.
