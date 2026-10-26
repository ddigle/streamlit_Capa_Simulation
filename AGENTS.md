# Capa Simulation 개발 에이전트 가이드

이 문서는 저장소 전체에 적용되는 개발 인수인계 문서다. 작업을 시작하기 전에
`README.md`, 이 문서, `docs/TODO.md`를 읽고 실제 코드와 함께 현재 상태를 확인한다.
구조나 핵심 계산 규칙을 변경하면 이 문서와 README도 같은 변경에서 갱신한다.

> **사내(WebIDE)에서 이 문서를 읽고 있다면 `docs/dual_env_workflow.md` 와
> `docs/internal_update_runbook.md` 를 먼저 읽는다.** 사내에서는 소스를 고치지 않고
> `review/` 에만 쓴다. 어느 환경인지는 `git remote -v` 로 가른다 — `github.com` 이면
> 사외다.

## 0. 소스 파일 Purpose 헤더 규칙

Git으로 관리하는 Python·PowerShell 소스에는 파일 최상단에 다음 한 줄의 주석 헤더를
유지한다. 적용 대상은 `app.py`, `app_pages/`, `src/`, `scripts/`, `tests/` 아래의
`.py`·`.ps1` 파일이며 `#`를 주석 기호로 사용한다.

```text
# Purpose: 이 파일이 담당하는 단일 책임을 구체적인 한 문장으로 기술
```

- `Purpose`는 파일명 반복이 아니라 입력·처리·출력 또는 UI 책임을 알 수 있게 작성한다.
- 파일의 책임이 달라지면 같은 변경에서 `Purpose`도 함께 고친다.
- 변경 출처와 이력은 주석에 적지 않는다. 누가·언제·무엇을 바꿨는지는 Git commit history가
  단일 근거이며, 필요하면 `git log -1 --format='%ad %an %s' -- <파일>`로 확인한다.
  이전에 사용하던 `Applied`·`Agent`·`Model`·`Change` 네 줄은 파일마다 충돌만 만들고
  Git이 이미 더 정확히 답하므로 제거했다.
- 기존 SQL 마이그레이션은 적용 체크섬이 달라지므로 주석 추가를 포함해 절대 수정하지
  않는다. 목적과 문서화 출처는 `docs/migration_catalog.md`에서 관리한다. 신규 SQL은 최초
  생성 시 `--` 형식의 `Purpose` 한 줄과 카탈로그 항목을 함께 작성하며, 적용 후에는 헤더도
  수정하지 않고 후속 번호의 마이그레이션을 추가한다.
  - `tests/test_migration_checksums.py` 가 두 DB 의 적용된 파일 체크섬을 버전별 표로 고정하고,
    러너가 바뀐 체크섬을 거부하는지도 돌려 본다 — 그 거부는 그 번호가 이미 적용된 DB 에서만 나서
    새 DB 를 만드는 다른 시험으로는 드러나지 않는다. **새 번호를 더하면 그 표에 한 줄을 더한다**
    (빠지면 실패 문구가 붙여 넣을 줄을 찍는다).
  - **새 마이그레이션을 쓰는 중에는 pytest 를 돌린 뒤 그 파일을 고치지 않는다.** 검사가
    도는 동안 개발 DuckDB 에 그 번호가 적용되므로, 그다음 한 글자만 고쳐도 온 검사가
    「이미 적용된 마이그레이션이 변경되었습니다」로 죽는다. 아직 **어디에도 배포하지 않은**
    번호라면 개발 DB 에서 그 행만 지우고 다시 적용하면 된다 —
    `DELETE FROM app_meta.schema_migration WHERE version = <번호>`. 체크섬 표의 그 줄도 새 값으로
    바꾼다. 한 번이라도 배포한 번호에는 쓰지 않는다. 후속 번호를 쓰는 것이 그때의 유일한 길이다.
- 새 소스 파일도 같은 헤더를 포함해야 한다. `tests/test_source_metadata.py`가 Python·
  PowerShell `Purpose`의 누락·빈 항목과 모든 SQL의 카탈로그 등록을 검사하므로 기본
  검증 명령에 포함된 pytest를 반드시 통과시킨다.

## 1. 프로젝트 목표와 현재 경계

이 프로젝트는 월별 PKG 생산계획과 제품·공정 기준정보를 이용해 다음 순서로 Capa를
시뮬레이션하는 Streamlit 앱이다.

```text
PKG PLAN
→ PKG·Chip·Wafer·Density 부하량
→ 공정·제품·속성별 대당 Capa
→ RQ_REQB 경로별 소요대수
→ 공정별 가용대수 대비 확보율
→ 월별 Bottleneck 및 대시보드
```

기본 런타임 원본은 `data/capa_simulation.duckdb`의 최신 공식 리비전이며, 계산 페이지는
XLSB를 읽지 않는다. `templates/structure_template.xlsb`는 초기 표시순서 이관과 병행
검증에만 사용한다. SQLite 파일은 병행 검증용으로 앱에서 읽지 않는다. 가용설비 현황의
운영 데이터는 시뮬레이션과 물리적으로 분리된
`data/equipment_availability.duckdb`에 저장한다. `Core_Data` 78컬럼 계약·typed raw
적재와 pandas 기반 16개 RQ 변환은 구현되었고, BigDataQuery 어댑터의 실제 SQL·컬럼
매핑도 커밋을 마쳤고 사내에서 약 3만 행 조회와 시나리오 저장까지 확인했다. 남은 것은 상세 조회 창의 결정과
사내 런북 8장의 실데이터 대조 결과다.

GitHub 소스만 있는 빈 환경에서는 `config/bootstrap_display_order.json`과 코드로 생성한
비민감 `DEMO_*` Core Data를 공통 변환 파이프라인에 넣어 초기 시나리오·리비전·공식버전을
자동 생성한다. 기존 시나리오나 공식버전은 자동 시드가 변경하지 않으며 내장 시드는 운영
기준정보가 아니다. 실제 표시순서는 시나리오와 분리된 공용 DB 프로필이며, 선택적 로컬
`data/input/RQ_DISPLAY_ORDER.csv` 또는 웹 Excel 표 붙여넣기로 초기화할 수 있다.

### 세 영역 — Static · 실행 관리 · Dynamic (2026-10-17 사용자 결정)

사이드바 계산 그룹은 셋이고 차례도 이렇다(`navigation.SIDEBAR_GROUPS`).

| 그룹(상자 이름) | 뜻 | 화면 |
|---|---|---|
| **Static Capa** | **약속.** 기술팀이 공정별 설비 셋업 시점·성능(UPEH·효율·수율)을 기준정보에 정하고, 그 기준정보와 생산계획으로 미래 Capa 를 낸다. 자원운영팀(옛 Guide 의 「GO팀」과 같은 팀)이 그 부족대수로 투자한다. | 현황 요약 · 생산 계획 · 기준 정보 · 산출 결과 · 표준 목표 |
| **실행 관리** | **이행.** 제조팀이 약속된 Capa 가 실제로 확보되는지 공정·기간·호기로 재고, 어긋난 곳을 유관부서에 이행 요청하고, 지킬 수 없으면 Static 반영까지 추적한다. | 현황 요약(머리, `execution_management.py`) · 공정 Capa 상세 · 필요 단축 일정(2026-10-18 가용설비 현황 탭에서 뗀 별도 화면) · 제약 시뮬레이션(2026-10-24, 저장하지 않는 미래 가정) · 가용설비 현황 · Space 현황 · 효율·UPEH·수율 실적 |
| **Dynamic Capa** | **실적.** 실행 관리가 모은 실적으로 Capa 를 다시 내고 그 Capa 로 단기 운영(재공·Rundown·병목)을 한다. | 현황 요약(머리, `reference_integrity.py`, 주소 `dynamic_capa`) · 표준 대비 재공 현황 |

- **경계 규칙**: 약속 이행을 **재고·비교·요청·추적**하는 일은 실행 관리, 그 실적으로 **Capa 를 다시
  내거나 단기 운영에 쓰는** 일은 Dynamic 이다. 표준 목표는 약속(대당 Capa)을 일·주로 푼 표준이라
  Static 이고, 재공 현황이 그것을 기준선으로 링크해 쓴다.
- **「Dynamic」 은 실적 Capa 에만 쓴다.** 화면 글자·Guide·문서에서 설비 마스터 일정으로 낸 가용대수는
  **설비 일정 기준 가용대수**(짧게 「일정 기준 가용」, B/N 은 「일정 기준 B/N」)이고, 가용설비 현황의 그
  탭 이름은 `Static 대비 일정` 이다. 기준정보 `RQ_EQP_AVBL` 의 값은 「기준정보 가용대수」(Static)다.
  **코드 식별자·내부 파생 컬럼·세션/위젯 키·DB 이름은 그대로다** — `dynamic_*`·`DYNAMIC_*`·
  `Dynamic가용대수`·`Dynamic확보율`·`process_detail_dynamic_absent` 같은 이름과 그것을 설명하는 주석의
  「Dynamic」은 설비 일정 기준 가용을 뜻한다. 내부 컬럼이 화면 표 머리로 나갈 때만 표시용 이름으로 바꾼다.
- **「확보율 보정」**: HOME 의 토글·Preference 편집기·풍선 글자다(옛 화면 이름 「실행 Loss」·「실행 Capa
  반영」·「실행 반영 ±n%p」). 뜻은 「기준정보 밖 변수(비가동·UPEH·재공)를 확보율에 %p 로 더하고 빼는
  손입력 보정」이고 실행 관리 그룹과 상관없다. 코드·저장 이름은 `execution` 그대로다(공용 프로필
  `app_meta.global_execution_capacity`, 마이그레이션 0021, 토글 키 `EXECUTION_TOGGLE_KEY`, 내부 컬럼
  `실행 비고`).
- **「UPEH 가정」**(2026-10-22 사용자 요청): 공정 Capa 상세·필요 단축 일정 조건 카드 끝 「이 세션만」 % 칸이다. 뜻은 「적용
  구간의 달에 기준정보 계획 UPEH 전체(Main UPEH·MI ST)가 p% 라면」 이고 소요대수에 ÷f 를 사후로 건다(6장 「소요대수와
  확보율」). 세션 값이라 기준정보·리비전·HOME·공식버전·공용 프로필은 바뀌지 않는다. 「확보율 보정」(공용 손입력 %p
  덧셈)과 다른 것이라 화면 글자·Guide 에 「보정」이라는 말을 쓰지 않는다. 코드·키 이름은 `upeh_assumption*` 이다.
- 파일 이름·페이지 제목·주소는 그룹을 옮겨도 바꾸지 않는다 — 주소는 파일 이름에서 나오고, Static 하위
  네 제목은 표시순서 DB 의 페이지 키다(`services/display_order_scopes.py`). 그룹을 옮긴 화면의 북마크는
  그대로 산다.

## 2. 실행환경과 검증 기준

- 운영 호환 Python: **3.10.11 64-bit**
- UI: Streamlit 멀티페이지 앱
- 데이터 처리: pandas
- 차트: Plotly
- 초기 이관·병행 검증용 Excel 읽기: xlwings, Workbook 숨김·읽기 전용
- 타입 검사: mypy strict
- 린트/포맷: Ruff, target Python 3.10
- 테스트: pytest

변경 후 기본 검증 명령 — Windows 는 PowerShell, 사외(데스크탑 WSL)는 bash 로 같은 네 관문을 돈다. 사내가 배포 확인 때 치는
꼴은 `docs/internal_update_runbook.md` 4-3 의 `uv run --no-sync python -m …` 이다.

Windows(PowerShell):

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest
```

사외(데스크탑 WSL, bash):

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
.venv/bin/python -m pytest
```

사외 개발 자리는 데스크탑 WSL 하나다(2026-10-13 사용자 결정 — 서피스와 병행하지 않는다). 환경 준비와
샌드박스에서 걸리는 것은 `docs/wsl_dev_environment.md`.

`mypy`는 `pyproject.toml`의 `files` 설정에 따라 `app.py`·`app_pages/`·
`src/capa_simulation/`·`tests/`·`scripts/`를 모두 strict 로 검사한다.

- `tests/` 에는 `__init__.py` 를 두지 않는다. 넣으면 pytest 가 `tests/` 대신 저장소 루트를
  `sys.path` 에 넣어 테스트끼리의 맨이름 import(`from test_equipment_availability import ...`)가
  죽는다. `scripts/` 에도 없다. 그래서 mypy 는 두 폴더의 모듈을 `test_dashboard`·
  `compact_duckdb` 같은 맨이름으로 보고, overrides 의 `module` 도 그 이름으로 적는다
  (`tests.*` 는 아무것도 잡지 않고, `test_*` 같은 접두 와일드카드는 mypy 가 거절한다).
- `mypy_path = "tests, scripts"` 는 테스트가 `scripts/` 모듈을 맨이름으로 부르는 것을 파일
  하나만 검사할 때도 찾게 한다. 상대경로라 저장소 루트에서 돌린다.
- 테스트에서 끄는 오류 코드는 pandas-stubs 가 `df.loc[행, 열]` 한 칸을 열두 갈래 합집합으로
  돌려줘 생기는 `operator` 하나이고, 그 자리가 있는 모듈 셋에만 건다. `arg-type`·
  `typeddict-item`·`index` 는 끄지 않는다 — 테스트가 계약을 어긴 값을 굳히는 실제 결손이
  그 코드로 잡힌다. 마찰은 코드로 푼다: `**dict` 언팩은 `TypedDict`, `st.column_config`
  합집합은 `type` 키로 좁히기, AppTest 노드는 `app.markdown` 같은 타입 있는 접근자나
  `isinstance(node, Caption)`, `.loc[r, c]` 를 숫자로 볼 때는 변환 없이 비교(숫자인지까지 본다).
- 계약을 **일부러** 어기는 입력(검증 경로 시험)만 그 줄에 `# type: ignore[코드]` 를 단다.

(Windows 기준 — WSL 샌드박스 사정은 `docs/wsl_dev_environment.md` 2장.) Codex에서 `.venv\Scripts\python.exe`를 샌드박스 안에서 실행하면 가상환경이 참조하는
사용자 프로필의 Python 3.10 실행 파일 접근이 차단되어 `Unable to create process` 또는
`Access is denied`가 발생할 수 있다. 이는 가상환경 손상이 아니므로 `.venv`를 재생성하지
말고 동일한 명령을 `require_escalated`로 다시 실행한다. Streamlit 버전별 스킬 탐색기도
프로젝트 `.venv`와 탐색기 스크립트의 정확한 조합으로 승인된 샌드박스 외 실행을 사용한다.

Streamlit 페이지나 상태를 변경했다면 `streamlit.testing.v1.AppTest` 또는 실제 브라우저로
해당 페이지 진입, 수정, 페이지 왕복과 예외 여부를 추가 검증한다.

개발 환경에서 걸리는 것:

- pytest 를 여럿 동시에 돌릴 때는 각자 전용 `--basetemp` 를 준다 — 기본 임시 폴더(`pytest-of-<사용자>/pytest-N`)는
  오래된 차례를 지워 서로의 폴더를 지울 수 있다. 임시 공간이 차서 전체 pytest 가 `OSError: [Errno 28]` 로 멈추면 코드
  결함이 아니다 — 끝난 작업의 찌꺼기만 지우고 다시 돌린다.
- 샌드박스 안에서 `TMPDIR` 이 비면 파이썬 `tempfile` 은 실패하지 않고 저장소 루트로 내려간다 — 오류로 드러나지 않으니
  `echo $TMPDIR` 로 본다(`docs/wsl_dev_environment.md` 2장).
- UPEH 가정 계획 1회 시간은 `scripts/benchmark_upeh_assumption.py --data-dir <사본 폴더>` 로 잰다(사내 런북 6-3 b — 1초를
  넘으면 % 입력을 「적용」 단추 폼으로 바꾼다). 합성 시드와 샘플 fleet 은 공정이 겹치지 않아 사외에서는 뜻 있는 값이 없다.
- HOME 단계별 소요시간은 `scripts/benchmark_home.py` 로 잰다. 화면에서 봐야 할 때만 세션 키 `dashboard_show_performance`
  (`components/home_rendering.HOME_PERFORMANCE_KEY`)를 켠다 — 개발용 계측이 모든 사용자가 늘 보는 자리를 차지하지 않게
  사이드바 토글은 두지 않는다.

## 3. 파일별 책임

### 실행과 UI

- `app.py` — 유일한 실행 진입점. 공식 시나리오 부트스트랩·공통 사이드바·조회기간을 세우고 페이지를 돌린다.
  - 차례 「입장 화면(`intro_overlay.py`) → 껍데기 스타일 → 서체 → 툴바 → 부트스트랩(최신 공식 리비전 활성화) →
    자동 갱신 예약 → 요약(`intro_summary.py`) → 사이드바 → 조건 팝업 칸 → 화면 탭 줄 → 페이지」는 `test_app_navigation.py`·
    `test_page_tabs.py` 가 지킨다. 페이지가 `st.stop()` 해도 닿아야 할 것은 모두 그 앞이다. 탭 아이콘
    `static/icons/capa_mark.svg` 는 `test_settings.py` 가 본다.
  - 화면 탭 줄(`components/page_tabs.py`, 상태 `page_tabs_state.py`)의 훅은 세 자리다 — (a) `st.navigation()` 바로 뒤
    이동 대기·상한 처리(`route_page_tabs`), (b) 직전 화면 주소를 바꾼 바로 뒤 지금 화면을 목록에 더함
    (`note_current_page`), (c) 조건 팝업 칸 바로 뒤 탭 줄 그리기(`render_page_tabs`). 점 판정(`page_unsaved_marks`)은
    한 번 내어 테마 표지와 탭 줄이 함께 쓴다.
  - 사이드바는 `navigation.py` 선언을 그리기만 한다(CSS `sidebar_style.py`, 상자·카드 `sidebar_status.py`). 순번 고정 —
    그룹 상자 → `Support`·앱 카드(`app_credits.py`, `apply_deploy_package.py` 가 쓴 `.deploy/applied.json`) → 조회 조건.
  - 조건 패널(`condition_field.py`)의 시나리오(`scenario_status.py`)·조회기간(`period_field.py`)·설비 시나리오
    (`equipment_scenario_status.py`) 팝업은 키 붙은 호스트 프래그먼트가 매 전체 실행 빠짐없이 부른다. 공통 줄은 읽는 화면에만
    서고 기간 범위는 `scenario_month_bounds.py` 다. 설비 시나리오 칸은 빈 블록 칸만 세우고 줄은 페이지가 그린다 — `app.py`
    는 설비 DB 를 열지 않는다(9장).
- `app_pages/home.py` — HOME 대시보드. `Main`(계획·LOB·주요공정·B/N Figure)·`Preference`(공용 프로필 편집기)·
  `Past Data`(`past_data_management.py`) 세 탭으로 전체 계산 결과를 조합한다. 설명은 `guides/home.md`.
  - 보는 조건(토글 일곱·제품별 비중 단위)은 조건 카드 `LOB 표시 조건`, 키·기본값은 `home_state.py` 한 곳이다. 시나리오를
    바꾸면 토글을 기본값으로 적어 푼다(`scenario_activation.py`·`test_scenario_activation.py`). 공정 필터는 패널 칸이다.
  - 카드는 `Main` 탭에서만 서되(2026-09-29) 계산이 `BOOTSTRAP_ERRORS` 로 멈춘 회차에도 그린 뒤 멈춘다 — 오류문이 시키는
    `EDP 포함` 켜기·`GAP` 끄기를 그 자리에서 하게 하는 유일한 예외다(2026-10-22, `test_home_page.py` 의 `stopped_home`).
  - 얹기 규칙(EDP 제외 범위·확보율 보정 → 선행 `advance_load.py`·GAP 기준)은 6장, 판정 기준은 `securement_threshold.py`.
    비교 대상 프로필은 바뀔 때만 쓴다(`test_comparison_profile_writeback.py`·`test_summary_recheck_paths.py`).
  - Figure: 옵션과 무관한 행 높이·글자 크기, 조정 0건이면 조정 전과 같은 JSON(`test_bar_corner_radius.py`), 숨은 탭
    금지(`test_hidden_tab_rendering.py`). 제품별 비중(`product_share.py`)의 색 구분은 `test_categorical_palettes.py`.
  - `Main` 맨 위에는 결론 줄(최저 확보율 공정·기준 미달 수)도 「소요대수에 들지 않은 수요」 줄도 두지 않는다 — 계산
    알림은 Admin Area `알림 모음`(`components/alert_board.py`)이 시나리오 전체 기간으로 모은다. 측정률 가정 한 줄은 남는다.
  - 제목 줄 끝 칸은 주요 Case 칩 셋(`공식 vN`·`Case1`·`Case2` — `components/home_main_case_chips.py`, 2026-10-23)이고
    칩이 못 불러온 까닭은 그 밑 한 칸이다. 세 탭의 key·라벨은 `home_state.py`(칩이 미지정 Case 를 누르면 `Preference`).
- `app_pages/load_conversion.py` — `생산 계획` 화면. `환산`·`PKG PLAN`·`수율` 탭으로 계획·수율을 편집하고
  부하량 환산을 보인다. 조건 카드·Guide(`page_guide.py`, `guides/load_conversion.md`)를 처음 적용한 화면이다.
  - 환산 조건은 조건 카드이고 환산은 그 탭이 열렸을 때만 한다. 작업 줄(적용·붙여넣기·가상 제품 등록)은 표 위, 붙여넣기와
    등록은 세션 키 팝업이다. PKG PLAN 붙여넣기는 탭에만 올리고 전역 반영은 적용 한 곳이며, 수율 붙여넣기는 바로 적용한다.
  - 가상 제품 등록(기준정보 복제, `virtual_product.py`)은 미적용 편집을 버리므로 먼저 경고한다. 값이 비거나
    범위 밖인 수율 행은 잠가 원본 그대로 되붙이고, 0 이하·100% 초과는 계산을 멈춘다(숨기지 않는다).
  - 편집표 원본은 `simulation_cache` 가 시나리오 키 + 표시순서 지문으로 캐시한다(`test_plan_edit_table_cache.py`).
- `app_pages/reference_data.py` — `기준 정보` 화면. Capa 산출 입력(UPEH·설비대수·효율·여유율·일수·측정률·STEP 구성)을
  월별로 편집한다. 탭 차례는 대당 Capa 식의 차례이고 탭은 이름으로 받는다. 설명은 `guides/reference_data.md`.
  - 적용 검사는 계산이 멈추는 조건과 같게 `reference_consistency.py` 에 두고 페이지는 행만 만든다. 빈칸 뜻은 표마다
    다르고(경로 없음·1.0·0 대·중립값 없음), UPEH 검사는 적용 전 활성 시나리오와 견준다. 격자·붙여넣기는 한 길이다.
  - 편집표와 적용은 같은 적용 기간(선택기간 ∩ 활성 리비전 UPEH 범위)을 쓴다. 필터는 보기만 좁힌다(`month_editor.py`).
  - STEP 표·팝업은 STEP 탭이나 팝업이 열린 회차에만 만들고 팝업 값은 경로 키다(`test_reference_data_perf.py`).
  - UPEH 왕복은 고친 칸만 원본 위에 덮는다 — 원본 표기를 정규화해 저장하면 STEP 목록의 REQB 일치가 끊긴다.
  - UPEH 편집표는 증분 없이 유효숫자 서식(`EDITOR_FORMATS` 의 `%,.6g`)으로 그리고, 월 칸 머리 도움말
    (`EDITOR_VALUE_HELP`)이 Main 행 UPEH · MI 행 ST(분)를 밝힌다. Streamlit 숫자 칸은 증분의 소수 자릿수에서 값을
    잘라 0.01 증분이면 0.01분보다 작은 ST 가 0.00 으로 보이고 그렇게만 넣어진다.
  - 적용하지 않은 편집이 남은 탭의 주황 점(`tab_marks.py`)은 원본 토큰으로 편집표를 비운 뒤에 정한다.
  - 설비대수 세 편집표(보유 · 대여 · 가용)도 현황 표 · 다른 편집 탭과 같은 표시순서(`apply_display_order`)로 행을 세운다 —
    공정 이름순이 아니다.
- `app_pages/calculation_result.py` — `산출 결과` 화면. `대당 Capa`·`소요대수`·`확보율` 탭(언패킹 순서 = `TAB_NAMES`)과
  제외 목록을 보인다. 설명은 `guides/calculation_result.md`.
  - 대당 Capa·소요대수 프레임을 풀지 않는다 — 요약은 `get_scenario_result_summary`, 표는 키 전용 캐시에서 그 탭이
    열린 회차에만 꺼내고 오류도 그 탭에만 띄운다(`test_calculation_result_tabs.py`). `STEP별` 은 공정을 골라야 계산한다.
  - 표 조건 카드 하나를 세 탭이 쓰고 열린 탭 것만 그린다. 대당 Capa `표시 방식` 은 본문이다(「하위 보기 전환은 본문」).
  - 소요대수 탭은 경로 쪽 제외 뒤에 계획 쪽 목록 둘을 그리고, 대당 Capa 제외 표는 `대당 Capa` 탭 하나가 그린다.
- `app_pages/process_capa_detail.py` — `공정 Capa 상세`(실행 관리 첫 화면). 정체성은 **어느 화면에서든 공정 하나를 눌러
  바로 깊게 보는 목적지**다(머리말, 2026-10-22). 공정 하나의 산출 근거 → 부족한 달 → 그 달을 메우는 설비 일정을 잇는다.
  본문 프래그먼트는 `process_capa_view.py`, 설명은 `guides/process_capa_detail.md`.
  - 공정·달은 상자보다 먼저 정한다(HOME 전달 → 주소 → 세션 → 최저 확보율 공정의 첫 미달 달). 확보율은 키 전용 캐시다.
  - 설비 DB 는 읽기만 하고 필요 단축 일정의 공용 조회 조건·기준선·세션 칸은 읽지 않는다(5장 9). 판정을 통과한 공정만
    계획·설비 일정을 받고, 아니면 까닭 카드 한 장이다.
  - 설비는 **방문 기준**이다 — HOME 칸으로 들어온 방문은 ◀▶ 뒤에도 그 방문 동안 공식 설비 시나리오(사이드바 줄은 잠근
    꼴, 출처 띠 끝 「설비는 공식 vN 기준」), 그 밖의 길은 세션 설비 시나리오다(`process_detail_state`). 설비 시나리오는 공정·
    달을 정한 바로 뒤에 읽는다 — 출처 띠를 자리(`st.empty`)에 다시 쓰지 않게(9장 placeholder 시험). 설비 DB 가 코드보다
    새면 경고(`render_schema_ahead_warning`), 옛 배포 흔적이면 흔적 경고를 세운다. 팝업은 「불러오기」 만이다.
  - 필요 단축 일정 카드에서 왔으면(`from=shortening`) **주소 인자만** 읽어 그 카드의 목표·기간·단축/신규 대수로 출처
    띠(「이 화면은 확보기준·RQ_REQB 기간 기준이라 대수가 다를 수 있습니다」)와 「← 필요 단축 일정」 을 낸다. 필요 단축
    일정으로 옮기는 단추는 모두 그 화면의 「강조 공정」 칸만 적는다 — 공정 필터(0019 세션 칸)는 심지 않는다.
  - HOME 표시 확보율 줄은 HOME 과 같은 함수(`home_display_rates`)·같은 캐시 키로 낸다. 「구획」·「제품별 소요대수」·
    「분류」는 「상세는 카드」의 예외로 본문 표 도구 줄이다. 출처 띠는 캡션 한 줄이다(`docs/design_system.md` 2-3).
  - 밖에서 들어온 회차는 그 길(`from`)의 구획을 다시 편다(HOME → ①, `gap` → ④, `shortening` → ③). 머리 ◀▶ 는 미달
    공정을 최저 확보율 차례로 넘기고(세션 값, 공정별 요약은 세션 칸에 한 벌), KPI 아래·근거 패널은 부족 원인마다
    다음 화면(보유 → 투자 검토 대상·산출 결과, 불일치 → 가용설비 현황, 일정 → 필요 단축 일정)을 단다.
  - UPEH 가정(조건 카드 끝 「이 세션만」)이 켜지면 가정 요약(이미 받은 확보율 행에 ÷f — 캐시 밖)과 가정 계획(계획 키 끝
    칸 토큰 → 가정 칸)을 더 세운다. **판정은 한 기준**이다 — 부족 띠·② 판정 대조·KPI·원인은 가정, 공식 값은 ① 공식
    줄과 KPI 회색 줄 「공식 n」 에만. 머리 배지·효과 한 줄(그 화면의 목표·기간)·카드의 역산 둘(「이 값으로」)·호기 CSV
    표지가 선다. 기본 공정·달·◀▶·HOME 표시 확보율은 공식이다.
  - 진입(판정 기준·공통 진입·유효 기간·시나리오 키·확보율·공정 선택지)은 `page_bootstrap.process_page_inputs` 로 제약
    시뮬레이션과 나눈다 — 두 화면이 같은 계획 칸을 같은 키로 받는다. 머리 ◀▶ 뒤 「이 공정 제약 시뮬레이션」
    (`st.page_link` + 주소 `?process=`)은 늘 보이고 설비 일정이 서지 않는 공정이면 꺼진 채 풍선이 까닭을 말한다(D11).
    HOME 칸 방문(공식 잠금)이고 세션이 공식 발행 쌍이 아니면 링크 판정만 세션 스냅샷으로 한 번 더 낸다(제약
    시뮬레이션은 늘 세션 설비 시나리오다 — 캐시된 스냅샷의 거르기뿐).
- `app_pages/capa_chatbot.py` — 활성 시나리오 Capa 를 근거로 답하는 대화 화면의 답 모양(결론·근거 표·조건과 산식·한계)을
  대본으로 보여 준다.
  - 대본은 `chatbot_samples.py` 한 곳이고 LLM 을 붙일 때 바꾸는 자리도 거기 하나다. 공정 표시명 프로필 버전마다 세션에
    한 번 만든다 — 결론·질문·조건의 공정 이름은 대본이 페이지가 넘긴 `ProcessLabels.label` 로 적고(조사도 그 글자로
    고른다), 근거 표는 화면 복사본에 표시명을 입힌다(8장 ④). 대화 기록은 답 이름(`SampleAnswer.key`)이다 — 질문
    글자는 표시명을 따라 바뀐다.
  - 추천 질문·`대화 비우기` 는 `on_click` 콜백이다. LLM API·권한·대화 이력은 연결하지 않는다.
- `app_pages/static_capa.py` — `Static Capa` 머리. 확보·경고 기준별 월간 설비 부족대수와 추가 필요대수(산식 6장)를 보인다.
  - 하위 화면은 사이드바로만 간다. 판정 기준은 HOME Preference 공용 프로필이고 카드는 읽기 전용이며, 판정 적용은
    캐시하지 않고 매 회차 한다. 부서별 활용과 계산식 설명은 `guides/static_capa.md` 다.
  - 확보율은 키 전용 캐시로 꺼내고 오류는 `check_scenario_capacity` 로 「계산 멈춤」과 검증 오류를 가른다.
- `app_pages/execution_management.py` — `실행 관리` 머리. 그룹 정의·로드맵·하위 화면 목차를 데이터를 읽지 않고 그린다.
  - `PageSpec` 이 시나리오·조회기간을 읽지 않고 조건 카드·설비 DB 핀이 없다. 하위 화면이 늘면 `SUBPAGE_SUMMARIES` 도
    고친다. 설명은 `guides/execution_management.md`.
  - 이행 현황판 숫자는 다음 판이다. 넣을 때는 `PageSpec` 의 `reads_*`·`uses_equipment_db` 와 `test_app_navigation.py` 의
    설비 DB 단언부터 본다.
- `app_pages/reference_integrity.py` — `Dynamic Capa` 머리(주소 `dynamic_capa`). 실행 관리가 모은 실적으로 표준 Capa 의
  실현 Capa·손실을 다시 내는 데모 프로토타입이다(요약·공정 상세·산식 가이드 탭).
  - 손실 목차가 효율 → UPEH → 수율 실적 → 재공 현황 → 가용설비 현황을 `page_link.py` 로 잇는다.
  - 데모는 샘플 스위치로 끄고 세션에 한 번만 만든다(실DB 를 붙이면 그 칸 키에 원천 적재 시각을 넣는다).
  - 부서별 Gap·A/Item 로드맵은 실행 관리 머리에 있고 여기는 그쪽 링크 한 줄이다.
  - 세 탭은 `stateful_tabs` 다. 닫힌 탭의 그림과 정적 산식 가이드는 그리지 않고, 공정 상세의 조건 위젯은 숨어도 그린다.
- `app_pages/required_shortening.py` — `필요 단축 일정`(실행 관리 둘째 화면). 정체성은 **단축이 필요한 공정 전부의 진척
  관리 한 페이지**다(머리말, 2026-10-22). 설비 저장본·Cut-off·소요대수를 모아 `required_shortening_panel.py` 에 넘긴다.
  계산 규칙은 `services/required_shortening.py` 다.
  - 머리 끝 「Qual 마감 계산기」 단추(`render_page_header(trailing=)`)가 큰 팝업을 연다(2026-10-24 — 가용설비 현황의 탭이던
    것). 열림 칸은 페이지 한 칸(`required_shortening_open_dialog`, 값 `qual_calculator`)이고 여는 콜백은
    `forget_page_dialogs()` 부터다. 호스트는 머리 바로 뒤·데이터를 읽기 전이라 호기가 없어 화면이 `st.stop()` 해도 열리고,
    이벤트 칸에 늘 한 자리(열렸으면 팝업, 아니면 빈 스타일)를 쓴다 — 계산기 본문은 이벤트 칸에 쓰지 않는다
    (`qual_deadline_calculator.calculator_style_markup`). 그 뒤 기준선 알림 토스트 자리가 팝업을 여닫을 때 밀리지 않는다
    (`test_qual_deadline_calculator.py` 가 연 회차·닫은 회차의 이벤트 칸 자리 수를 견준다).
  - KPI 아래·카드 위에 공정 진척 보드·기한 임박·이행 지연(`components/shortening_board.py`)이 서고 카드마다 「공정 Capa
    상세에서 근거 보기」 와 그 옆 「도면에서 보기」(Space 현황 필요 단축 보기 — 그 공정의 층·같은 목표, 층은 본문이 공정 전부를
    한 번에 고른다 `shortening_space_floors`, 비활성 층 뺌 — 그래서 페이지가 층 사용 상태 `load_floor_states` 를 읽는다)다(주소
    인자, 샘플 fleet 이면 둘 다 숨김). 수요·달·계획 꺼내기는 Space 보기와 같은 `components/shortening_source.py` 다. 카드 차례·기한 임박 날수·강조 공정은 세션 값이고 DB 에 쓰지
    않는다.
  - 저장본·미저장 편집은 `equipment_data_workspace.py` 세션 칸(가용설비·Space 와 같은 토큰)에서, Cut-off 는 저장된
    값만 읽는다(고치는 곳은 가용설비 현황 「설정」 팝업). 조건 카드는 `shortening` 이다.
  - 소요대수 프레임은 넘기지 않고 시나리오 키와 로더를 넘긴다. 계산은 DB 에 쓰지 않고 패널이 공용 조회 조건(`0019`)과
    진척 비교 기준선(`0021`)만 쓴다. 알림 자리는 토스트 규칙을 따른다(`test_shortening_baseline_notice.py`).
  - UPEH 가정은 기본 보기를 바꾸지 않는다 — 머리 「UPEH 가정 비교」 를 켠 회차에만 가정 계획을 꺼내 공식→가정을 보인다.
    가정이 켜진 동안 기준선 저장은 거절하고 진척 비교는 늘 공식 계획이다.
  - 설비는 **세션 설비 시나리오**다(`resolve_equipment_session`). 기준선 저장은 세션이 공식 발행 쌍일 때만이고(거부 까닭은
    「가정 설비 시나리오」·「발행하지 않은 리비전」 둘), 기준선에는 공통 rN + 설비 시나리오·rN·공식 vN 출처가 실린다. 진척
    비교는 늘 보이고, 세션이 공식 발행 쌍이 아니면 머리에 「지금 = 셋업 실무 r4 · 기준선 = 공식」 을 적는다. 카드 링크는
    표시용 `eq`(그 카드가 본 설비 시나리오)를 싣는다.
- `app_pages/constraint_simulation.py` — `제약 시뮬레이션`(실행 관리 셋째 화면, 2026-10-24 사용자 결정). 정체성은 **공정
  하나에 미래 제약(제약 제품 전용 설비)이 생기면 제약 제품에 먼저 떼어 준 뒤 기존 제품 확보율이 언제부터 얼마나 떨어지는가**
  다. **저장하지 않는다** — 조건은 세션에만 있고 어느 DB 에도 쓰지 않는다. 계산은 `services/constraint_simulation.py`, 본문은
  `components/constraint_simulation_view.py`, 설명은 `guides/constraint_simulation.md`.
  - 입력은 새 무거운 계산이 없다 — 공통 진입은 공정 Capa 상세와 같은 `page_bootstrap.process_page_inputs`, 소요는 계획의
    `소요대수`(공정 합)와 `get_process_product_demand(split="제품정보", limit=CONSTRAINT_PRODUCT_LIMIT)`(제품별 — 「그 밖」 이
    생기지 않는 상한), 가용은 공정 Capa 상세 ② 와 **같은 계획 칸·같은 키**(`load_required_shortening_for_target` 공식 칸,
    목표는 키 맞춤용 HOME 확보기준)의 단축 전 `가용대수` 다. 설비는 늘 **세션 설비 시나리오**(HOME 칸 방문 공식 잠금을
    잇지 않는다 — D6)이고, 필요 단축 일정의 공용 조회 조건(`0019`)·기준선(`0021`)·세션 칸은 읽지도 쓰지도 않는다. UPEH
    가정·HOME 얹기는 걸지 않는다(UPEH 가정이 켜진 세션이면 출처 띠 끝 한 줄).
  - 주소 `?process=` 는 무엇보다 먼저 꺼내고 그 키 하나만 지운다(`take_constraint_process_request` — 테마 인자는 남는다). 한 번
    적용한 값은 `CONSTRAINT_QUERY_SEEN_KEY` 에 남겨 지운 것이 브라우저에 닿기 전 옛 주소를 실은 회차가 사용자가 그 뒤 고른 공정을
    덮지 않게 하고, 인자가 걷힌 회차에 비운다(공정 Capa 상세 `PROCESS_DETAIL_QUERY_SEEN_KEY` 와 같은 막이). 공정
    선택지는 공정 Capa 상세와 같은 전 공정이고(D12) 설비 일정이 서지 않으면 까닭 카드 한 장(`readiness.badge`·`detail`, 판정을
    지나도 계획에 없는 공정은 「계획에 공정 없음」·「Cut-off 미기재」)으로 멈춘다.
  - 오류는 넷으로 가른다 — 공통 진입(카드 캡션), 제품별 소요 받기(카드 캡션 + 본문 「제품별 소요를 읽지 못했습니다 — {글}」 —
    「소요가 있는 제품이 없다」 안내와 가른다), 계획 받기(「설비 일정을 계산하지 못했습니다」 + 두 DB 경로), 어댑터·서비스의
    `ValueError`·`KeyError`(「제약 시뮬레이션을 계산하지 못했습니다 — {글}」). `BOOTSTRAP_ERRORS` 에 `KeyError`·`ValueError`
    가 들어 있어 한 `try` 로 묶으면 뒤의 글이 앞의 글로 둔갑한다.
  - 조건 카드 「제약 시뮬레이션 조건」 은 대상(공정·제약 제품·제약 시작·제약 끝 상자 둘)과 「이 세션만」 의 확보율(제약 확보율·
    기준 확보율)·개조(토글·개조 기간·Cut-off 읽기만) 세 묶음이다(D2). 버튼 + 직접 입력은 `preset_number_field.py`(D10 —
    기준 확보율은 0.5% 단위, D18). 「소요 비중대로 나눴을 때 함께 보기」 는 보기 전환이라 본문 프래그먼트 안이다. 머리 한 줄
    오른쪽 끝 「← 공정 Capa 상세」 는 같은 공정으로 돌아간다.
- `app_pages/available_equipment_status.py` — `가용설비 현황`. 설비 운영 DB 의 입력·조회·Static 비교를 **탭 둘**로 다룬다
  (2026-10-24 사용자 결정 — 두 탭 개편): ① `설비 마스터`(처음 여는 탭 — 설비 마스터 표·작은 편집표 둘·오른쪽 칸 호기 상세/
  새 호기/저장 전 변경/저장 이력, 개편 B1·C — `components/equipment_master_tab.py`, 개편 전 `RawData`) ②
  `Summary`(안쪽 탭 `Main`·`Static 대비 일정` — 라벨 글자는 개편 전 그대로). 공정별 Cut-off 는 제목 줄 끝 「설정」 팝업
  (`equipment_settings_dialog.py`, 개편 전 `Preference` 탭), Qual 마감 계산기는 필요 단축 일정 머리의 팝업, 설비 시나리오 목록·
  리비전·발행은 시나리오 관리 › 설비 시나리오다. 설명은 `guides/available_equipment_status.md`.
  - 탭 선언은 `navigation`(`EQUIPMENT_TABS`·`EQUIPMENT_SUMMARY_TABS`, 안쪽 탭은 `ConditionTabs.sub` = `SubTabs`)이고 페이지는
    그 목록 그대로 `stateful_tabs` 를 세운다. 안쪽 탭은 바깥 Summary 블록 안에서 **늘** 부른다(위젯 값이 남아 사이드바가
    읽는다). 바깥이 숨으면 안쪽 고른 탭의 `open` 도 참이라, 본문 갈래와 두 부품(`render_equipment_explorer`·
    `render_availability_gap_panel`)의 `owner_tab` 은 바깥·안쪽을 합친 `tab_state.NestedTab` 이다 — ① 을 보는 회차에 Main
    탐색·Static 대비 일정 계산이 돌지 않는다. 바깥 key(`equipment_active_tab`)는 그대로라 옛 기억 값은 첫 탭으로 열린다.
  - ① 은 **열린 회차에만 그린다**(개편 B1 — 9장 「숨은 탭에서도 입력 위젯은 그린다」 의 예외). 표 편집은 세션 칸(편집본·출납
    기억)에 살아 숨은 회차에 그릴 까닭이 없고, 그 모듈(`equipment_master_tab`)은 표 컴포넌트를 등록하므로 열린 회차에만 불러온다.
    숨은 회차에 버려지는 것은 작은 편집표 둘의 적용 전 편집(화면 탭 줄 떠나기 확인이 묻는다)·변경 메모(입력 초안)·저장 칸 체크
    (기본값이 늘 같다)이고 저장자는 `persist_state` 로 남는다. 작은 편집표 제출은 그 탭의 모든 위젯을 그린 뒤 `st.rerun()` 으로
    끝나므로 **코드 차례는 Summary 블록 뒤**다(9장 「`st.rerun()` 은 그 화면의 모든 편집표를 그린 뒤에만」 — 화면 차례는
    `stateful_tabs` 목록이 정한다). 저장하지 않은 설비 편집(편집본·FAB 대기)이나 작은 편집표의 적용 전 편집
    (`small_editor_edits`)이 있으면 ① 탭 이름 옆에 점(`tab_marks`, 화면 탭 줄의 점과 같은 판정)을 찍는다.
  - 진입은 `resolve_equipment_session` 이고 계산은 `calculation_drafts()` 다(일정 없음 호기를 뺌 — 「일정 없음 n대」 한 줄).
    가정 설비 시나리오면 Main 미확인은 **공식 스냅샷의 미확인**을 화면 호기로 좁혀 쓰고(꼬리표 「공식 일정 기준」),
    「설정」 팝업의 Cut-off 는 읽기 전용(「설비 공정으로 채우기」 꺼짐)이다. 설비 시나리오 줄은 두 탭 모두 선다.
  - 「설정」·「엑셀·CSV로 한꺼번에」 팝업: 열림 칸은 페이지 한 칸(`available_equipment_open_dialog`, 값 `settings`·`import`)이고
    호스트(`render_equipment_dialog_host(import_dialog=)`)는 이벤트 칸에 늘 한 자리다(열렸으면 팝업, 아니면 빈 스타일). 새 방문
    회차에는 붙여넣기 미리보기를 거둔다(`withdraw_preview_on_new_visit` — 페이지가 매 회차 부른다). Cut-off 저장·「설비 공정으로 채우기」 뒤에도 팝업은 열려 있다(9장 「팝업과
    콜백」 의 예외). 첫 데이터 안내의 「설정에서 보기」 도 이 팝업을 연다. Static 대비 일정은 저장된 Cut-off 를 캐시 경계
    (`load_process_cutoff`)에서 직접 읽는다 — 팝업이 돌려준 값을 받지 않는다.
  - 첫 데이터 안내(「처음 사용하시나요?」)·샘플 스위치·`설비 조회 조건` 카드는 Summary 의 안쪽 탭이 보일 때만 선다
    (`viewing_tab_open`). 「설비 마스터 탭에서 붙여넣기」·「설비 데이터 입력」 은 ① 을 기억하고 「엑셀·CSV로 한꺼번에」 팝업을
    연다(첫 데이터도 그 팝업으로 넣고 「저장 전 변경」 에서 저장한다).
  - Main·① 은 설비 DB 만 쓰고 `Static 대비 일정` 만 시뮬레이션 DB 를 읽는다 — 못 읽어도 그 탭 안에서만 알린다
    (`test_equipment_scenario_demand.py`). ① 은 원본 이름(`test_process_label_boundaries.py`).
  - 조건은 탭마다 따로다 — `Static 대비 일정` 은 Main 의 공정소분류·추가 조건 키를 읽지 않고, 비교 범위는 이 탭의
    `공정`·`호기 필터` 만 정한다.
  - Main 틀은 `equipment_explorer.py`, 알림 줄은 `undated_equipment.py`·`schedule_confirmation.py`·`usage_basis.py`,
    대수 축은 `equipment_units.py`, 월별 안분은 `wd_window.py`(규칙은 6장). Cut-off 는 리비전 없이 표를 통째 갈아 끼운다.
  - 편집본은 `ensure_equipment_drafts` 한 곳이 씨뿌린다(Space 와 버퍼 공유). 입력 표를 더하면 draft 키 이름을 올리고
    Import·버퍼 교체 때 그 편집표를 `discard_editor` 로 버린다(9장). ① 본문은 `equipment_master_tab.py`, 편집본 경계·작은 편집표·
    저장은 `equipment_data_workspace.py` 다(옛 입력·직접 편집·저장 이력 폼은 개편 D 에서 걷었다).

- `app_pages/actual_efficiency.py`, `app_pages/actual_upeh.py`, `app_pages/yield_actual.py` — 실행 관리의 효율·UPEH·
  수율 실적 비교·개선관리 하위 페이지 셋이다.
  - 화면은 `components/performance_actual_screen.py` 한 벌이고 이 파일들은 `MetricSpec` 과 머리말 문구만 갖는다.
  - 생산이력·수율 실적 DB 와 `RQ_RUN_RATE`·`RQ_UPEH`·`RQ_YLD` 연결은 아직 없다. 샘플 스위치를 끄면 연결 뒤
    계산할 것을 적은 자리표시자만 남는다.
- `app_pages/wip_status.py` — Dynamic Capa 의 `표준 대비 재공 현황` 하위 페이지로, 오늘 −7~+3일의 공정·제품·
  STEP별 재공·유입·Flow 를 제품별 일 표준 가능량과 견준다(재공 값은 결정론적 데모, 재공 DB 연결은 미구현).
  - 소요대수에서 나오는 준비물(`services/wip_status.prepare_wip_route_choices`)은 세션에 한 벌 두고 키는
    `scenario_cache_key`·`display_order_digest(RQ_DISPLAY_ORDER)` 다. 가용대수는 다른 세션이 바꾸는 현행값이라
    매 회차 읽는다.
- `app_pages/space_status.py` — 실행 관리의 Space 현황으로, `S.PKG FAB 전체 → 층 상세` 2단 도면(`space_layout_editor.py`
  뷰어)에서 셋업 이행을 공간·호기로 본다. 상태별 대수·단계 전환은 가용설비 현황 몫이다(`guides/space_status.md`).
  - 연 층은 세션 키 `space_status_selected_building`·`_floor` 가 먼저이고 주소 `?floor=` 는 `floor` 만 넣고
    지운다(`st.query_params.clear()` 금지). 자리 이동은 모두 콜백이다. 브라우저 뒤로/앞으로는 층 이동이 아니다.
    **예외 하나** — 필요 단축 일정 「도면에서 보기」 주소(`?layer=short&floor=…&proc=…&target=…`)는 페이지 맨 앞에서 한 번 받아
    (`space_shortening_view.consume_layer_link`) 그 층이 세션 층을 **덮고**(`floor` 가 없거나 비활성 층이면 세션 층을 지워 FAB
    전체), 색 기준·목표·그 층 공정 칩을 적고 배치 편집 토글을 끈 뒤 남길 인자만 `from_dict` 한 번으로 다시 싣고 회차를 한 번 더
    돈다(사이드바 줄을 맞추려고 — 아직 그린 편집기가 없는 자리). 그 주소를 테마 인자 없이(다른 브라우저 등) 처음 열어 테마
    새로고침이 걸리면, 지운 링크 인자는 테마 스크립트가 문서를 연 주소에서 되살려 새 세션이 다시 받는다(`theme_toggle` 의
    `<theme-reopen>`).
  - **색 기준 「필요 단축」**(2026-10-24 결정 — 라디오 셋째 값, `services/space_shortening_layer.py`·
    `components/space_shortening_view.py`). 켠 동안만 필요 단축 일정과 같은 계획(같은 키·같은 칸, 설비는 세션 시나리오 — LY6)을
    꺼내고(5장 9), **본문 조작 줄**(늘 서는 `space_shortening_toolbar` — 목표 확보율 `st.segmented_control(required=True)`·
    「단축 없는 호기 흐리게」·기준 캡션·못 읽음 알림)·FAB 블록 셋째 줄·층 목록 칸 넷·요약·추가 호기 상자(늘 서는
    `space_shortening_fab_slot`)·층 보기 칸(늘 서는 테두리 없는 `space_shortening_slot` 안 — 공정 칩·「이 층에서 단축할 호기」·
    도면에 자리가 없는 호기·누른 호기 상세)을 그린다. 켠 회차의 기준일은 오늘로 고정이다(세션 기준일은 지우지도 쓰지도 않는다 —
    뷰어 `asOfPinned` 고정 줄). 배치 편집 중은 쉰다(라디오 값 그대로, 그리는 색은 공정구분 기본 —
    `effective_choice` 를 편집기·범례가 같이 쓴다). 쉬는 까닭 한 줄(`_render_layer_rest_caption`)은 한 화면에 한 번이다 — 층
    상세는 편집기 위 캡션, FAB 편집은 편집기 캡션이 없어 본문 조작 줄이 적는다. 비활성 층 상세에서는 쉬지 않고 배너 아래
    그대로 서되 추가N 을 붙이지 않는다(층 사용 명세 8-2). 층 보기 칸이 세는 행은 그 층에 **오늘 그려지는** 행이다(뷰어 roster 의 페이더 범위 합집합이 아니다 — FAB 층
    대수와 같은 축). 계획을 못 읽은 켠 회차의 범례는 채우기 칸 없이 테·덧표시만이다(뷰어가 지연·보관 면을 끈다 — D12). 상세 단추 「필요 단축 일정에서 이 공정 보기」 는 대기 칸만 적고 다음 회차
    본문 맨 앞(`switch_to_queued_shortening`)이 옮긴다. epoch 는 바뀌지 않는다(레이어·목표·칩·흐림은 epoch 밖). 사이드바
    시나리오·조회기간 줄은 그 값일 때만 선다(`navigation.SPACE_STATUS.condition_tabs` — 보기 값으로 가른다).
  - 기준일(`space_status_as_of`)은 층 도면 위 페이더가 손을 뗄 때 한 번 보내고 끄는 동안은 브라우저가 경계 날짜로
    칠한다(`services/space_unit_state.py` 와 같은 식, 날짜는 epoch 밖, 성능은 `scripts/check_deploy_screens.py`).
    분기 눈금 글자는 트랙 폭에 맞춰 솎는다(editor.js 순수 구획 `<fader-ticks>` — 「오늘」 은 늘 서고, 트랙 밖이거나 이웃과
    2px 안으로 붙는 글자는 `is-crowded` 로 숨김, 회차마다·크기가 바뀔 때 다시 잼, `tests/test_space_fader_ticks_js.py`).
    기준일 줄 폭 560px 아래(390px 창)에서는 날짜 칩이 13.5rem → 8.5rem 고정 폭이다(CSS 컨테이너 `sle-daterow`) — 390px
    창에서 트랙이 68px 로 줄어 글자 7쌍이 겹쳤다(E2E 결함, 고친 뒤 146px). 768·1400px 창은 예전 그대로다.
  - 보기는 **사이드바에서 고른 설비 시나리오**의 배치다(설비 시나리오 2단계 S3 — LY3, `PageSpec.equipment_scenario="session"`·
    `uses_equipment_db=True`). 그리는 한 벌은 세션 스냅샷(`resolve_equipment_session(...).snapshot.calculation_frames()`)
    하나이고 가정이면 그 리비전의 호기 배치 차이가 얹혀 있다. 층 도면 요소·Main 설비명 위치는 **모두**
    `components/space_floor_layout.effective_floor_layout`(공식 층 현행값 ⊕ 그 리비전의 요소·이름표 차이)을 지난다 — 뷰어·
    편집기·「그대로인가」 판정·층 대조 기준 지문·저장 안 한 상자의 겹침 경고(공식 현행값 직접 읽기 0 — 시험이 소스를
    훑는다). 머리 알림은 **그리는 스냅샷**으로 정한다(`space_layout_notices` — 「가정 배치 · 공식과 다른 호기 n대 · 도면 요소
    m개 · Main 설비명 위치 k개」, 차이 없는 가정은 「배치는 공식과 같습니다」 캡션, 공식 시나리오의 가정이던 때 리비전도
    알림, 묶음 다시 맞춤·버린 차이 둘째 줄). 그 시나리오에 일정이 없는 호기는 그리지 않는다(`unscheduled_notice` — 공식 발행
    쌍이면 「공식 일정 없음 n대」). 미확인은 가정이면 공식 일정 기준(가용설비 현황과 같은 `official_confirmation_master`),
    층 캔버스 줄이기 검사는 공식 배치 마스터다. 뷰어 epoch 는 편집 가능 여부와 떼어 늘 쌍 토큰을 담는다(샘플만 「sample」 —
    잠긴 두 쌍을 오갈 때 옛 좌표가 남지 않게, 검토 F1).
  - **「공식과 견주기」**(설계 시나리오 2단계 S4 — 설계 8-3). 경로 줄(`space_path`) 끝에 **늘 서는** 토글
    (`space_compare_official_v1`, `persist_state="session"`)이고, 해당 없는 회차(공식 배치·호기 차이 없음·층 배치 편집 중·샘플·
    일정 없이 엶)에는 다른 key(`space_compare_official_locked_v1`)의 끈 채 잠근 토글을 같은 자리에 세운다 — 조건부로 생겼다
    사라지면 아래 뷰어 순번이 밀려 다시 마운트되고 배율을 잃는다(검토 L11). 견줄 것은 **그리는 스냅샷**의 호기 차이
    (`layout_official_places` — 머리 알림과 같은 재료, 공식 스냅샷을 따로 읽지 않는다). 켜면 층 상세 뷰어 payload `compare`
    (`components/space_floor_layout.compare_payload` ← `services/layout_overlay.layout_compare` — **epoch 밖**이라 켜고 꺼도 다시
    마운트하지 않는다)가 공식 자리가 이 층인 차이 호기의 점선 상자(같은 층으로 옮겼으면 지금 상자와 가는 선, 다른 층이면
    「→ C2 3F」, 레이아웃표시 N 이면 「도면 제외(가정)」, 좌표가 없으면 「미배치(가정)」)와 다른 층(또는 공식 미배치)에서 온 호기
    꼬리표(「← C1 2F」·「← 공식 미배치」)를 싣고 편집기 JS 새 층 `sle-compare`(보기 전용·눌림 없음·겹쳐 숨기기와 무관, 순수
    `compareShapes` — `// <view-compare>` 구획, node 시험)가 그린다. 이웃한 꼬리표가 겹치면 뒤 꼬리표를 한 줄씩 위로 올린다
    (글자 폭 어림 — 한글·화살표 1em). 공정 필터·일정 없음으로 그리지 않는 호기는 견주지 않는다.
    편집기에는 보내지 않는다. FAB 전체는 층 목록 표 끝 「공식과 다름」 칸(`space_floor_list.FloorListColumn` — 그 층에서 나갔거나
    들어왔거나 그 층 안에서 옮긴 설비 수, 묶음은 1대 — `unit_differences_by_floor`)과 층 블록 풍선 한 줄 「가정 배치 n대 다름」
    (`floor_block_stats(layout_differences=)` → `linkStats.layout`)이다. FAB 셈도 층 상세와 같이 그리는 호기(공정소분류 필터를
    지난 것 — `floor_unit_differences(session, shown=)`)만 센다 — 같은 표의 배치대수와 어긋나지 않게. 도면 요소·Main 설비명 위치 차이는 머리 알림의 수만이다.
    데이터 꼴은 기준 쪽/보는 쪽 이름이라 반대 방향(공식 세션에서 고른 가정 시나리오를 점선으로)도 받을 수 있다(구현은 범위 밖).
  - **편집 권한은 `equipment_scenario_activation.space_edit_mode(session, stamped_role=)` 한 판정**(설계 8-4 표 — 설비
    마스터 탭 배치 칸·붙여넣기도 같은 `layout`). 공식 시나리오는 공식 배치(낡아도 — 위치는 공통, 새 호기 폼만 꺼짐), 공식
    시나리오의 가정이던 때 리비전은 잠금, 가정 최신은 그 시나리오의 배치 차이(새 호기 폼 켬 — Q1), 가정·낡음은 그 시나리오
    최신의 배치 지문이 이 리비전과 같으면 빨리 감기(캡션 — 저장소가 최신의 일정 위에 받는다) 다르면 잠금(「최신 rM
    불러오기」), 찍힌 역할 ≠ 지금 역할이면 잠금(「배치 변경만 버리기」), 일정 없이 엶은 잠금이다. FAB 전체·층 캔버스·배경
    도면·층 사용(0029)은 공식 시나리오에서만 편집한다(G5·Q3 — 꺼진 단추의 풍선이 까닭, FAB 자리에 「공식으로 바꾸기」 — 일정
    없이 연 세션에는 세우지 않는다, 공식으로 옮겨도 같은 까닭으로 합쳐지지 않는다). 찍힌 역할이 바뀐 잠금 글은 화면이 둘이다 —
    Space 는 그 자리의 「배치 변경만 버리기」, 설비 마스터 탭(`SpaceEditMode.master_tab_lock_reason`)은 그 단추가 있는 Space
    현황 저장 안 한 배치 변경 상자를 가리킨다. 「공식으로 바꾸기」·「최신 rM 불러오기」 실패는 저장 오류와 따로
    (`SWITCH_ERROR_KEY`) 잠금 줄 자리에 「설비 시나리오를 바꾸지 못했습니다」 로 선다. 편집기 「편집 영역」 칸은
    `canvas_editable=False` 면 JS 가 끄고 서버도 적용의 캔버스 값을 거부한다(두 겹). JS 잠금(편집 영역 칸·새 호기 단추)은
    회차마다 받은 값대로 켜고 끈다(`lockCanvasControls`·`lockNewUnitToggle` — 편집기 key 는 시나리오가 바뀌어도 같아 같은 DOM
    이 남는다). 사이드바 설비 시나리오 줄은 편집본을 세운 **뒤에** 그린다(남의 저장 뒤 배지가 한 회차 늦지 않게). FAB 대기분
    저장은 어느 세션에서나 된다(대기분은 공식 세션에서만 생기고 FAB 은 시나리오 없는 공용 값 — 가정 세션 저장 상자에 한 줄).
    1단계의 「공식 발행 쌍에서만 편집 — [공식으로 바꾸기]」 잠금과 `space_editing_allowed` 는 걷었다. 편집본은 실제
    저장본이면 늘 세션 토큰으로 세운다(세션 토큰 하나라 다른 화면 편집을 버리는 갈림이 없다).
  - 배치를 바꾸는 적용(호기·숨은 모듈·새 호기·캔버스·요소·Main 설비명 위치)은 그때의 역할을 찍는다(`stamp_layout_role` —
    설계 6-2). 층 배치가 잠긴 회차에 남은 배치 변경은 상자의 「배치 저장」 을 끄고 「배치 변경만 버리기」(`discard_layout_edits`
    — 배치 일곱 칸·층 대기분·편집기 모듈 모양·찍힌 역할만 버리고 공통·일정 편집·이름 바꿈·FAB 대기분은 남김)를 세운다.
    가정 세션 상자는 「「셋업 실무」의 새 리비전(가정 배치)으로 저장합니다 — 공식 배치는 바뀌지 않습니다」 이고 저장 칸은
    `render_equipment_save_fields(..., assumption=True)`(함께 넣기 기본 끔 — Q1) 다. 층 배치 잠금 줄은 늘 서는 칸
    (`space_edit_lock_slot`)에 그린다. 잠금 까닭(`lock_reason`)은 그 줄에만 한 번 적는다 — 상자는 「저장하지 않습니다 — 까닭은
    아래 잠금 줄에 있습니다」 와 「배치 변경만 버리기」 만(까닭이 없을 때만 「최신을 불러온 뒤 다시 고치세요」, E2E r2). 배치
    빨리 감기 글(`notice` — 「rM 이 더 새롭지만 배치는 같습니다 — …」)도 같은 칸의 ▸▸ 줄에만 한 번 적고 상자 캡션에 붙이지 않는다
    (E2E r3).
  - 배치 편집은 설비 마스터 탭과 같은 편집본에 저장 검사를 거쳐 얹고 `save_equipment_buffer` 로 저장한다(「배치 저장」 확인
    팝오버에 저장 칸 — 공통·일정이 모두 그대로면 층 값만 쓰고 리비전을 만들지 않는다). 도면 상자 앞 칸
    (`space_unsaved_layout_slot`)은 늘 세운다 — 순번이 밀리면 편집기가 다시 마운트된다.
  - 층의 Main 설비명 위치(대기분 `pending_floor_group_labels`, 없으면 `effective_floor_layout` 의 합친 값)를 편집기·뷰어에
    넘기고, 적용은 `next_group_labels`(실린 묶음의 모듈 수 `module_group_sizes` 로 처음 위치를 가른다)로 층 위치
    목록을 만들어 저장값과 다르면 `stage_floor_group_labels` 로 둔다. 편집기·뷰어 epoch 와 층 대조
    (`FloorLayoutBase`)는 요소와 위치를 함께 본 `floor_layout_fingerprint` 다.
  - 적용이 옮기거나 빼거나 보낸 모듈 묶음(이 적용의 `changes`·`hidden_moves` 에 모듈이 든 묶음)의 적용 뒤 모양
    (`module_layouts`)을 `stage_editor_module_layouts` 로 둔다 — 저장의 모듈 묶음 좌표·크기 검사가 그 모양 그대로인
    묶음을 편집기 결과로 통과시킨다(`equipment_data_workspace.saved_master_violations`).
  - 층 상세 아래 호기 표는 21칸(`space_layout.FLOOR_TABLE_COLUMNS` — 2026-10-23 요청 차례, 칸 이름은 설비 마스터 그대로,
    「단계」는 기준일 상태)이다. 뷰어에서 누른 호기(`on_pick` 콜백 → 세션 `space_status_picked_unit` = (동, 층, 설비명))가
    있으면 그 설비 줄만(`picked_unit_rows` — 모듈이면 같은 Main 설비 줄 전부, 누른 것이 첫 줄)이고 「층 전체 보기」
    (`space_floor_show_all_<동>_<층>`, 늘 세움)·빈 곳·Esc 로 풀린다. 다른 층·FAB 로 옮기거나 그 층 행에 없으면(필터·이름
    바꿈) 푼다. 층 CSV 는 늘 층 전체의 모든 칸이다. 뷰어 호기에는 설비지분 `share`(기준일 보유 지분
    `space_layout.row_unit_shares` — 범례·배치 대수와 같은 칸, 일부 모듈만 반입한 묶음의 반입 전 모듈은 0)를 싣는다.
  - **층 사용 상태**(설비 `0029`, 2026-10-24 결정 S1~S6 — `load_floor_states`, 설비 시나리오와 무관한 공용 현행값). FAB 아래 층
    목록 자리는 `components/space_floor_list.py` 다(사용 층 표 + 접힌 「비활성 층 n개」, 표 머리 `사용 편집`). 비활성 층 블록은
    FAB 도면에서 회색 빗금 + 사유로 그려 눌러도·Enter 로도 열지 않는다 — 뷰어 epoch 에 상태 지문(`floor_states_fingerprint`,
    배율은 그대로)을 넣고 편집기 epoch 에는 넣지 않으며(적용 전 FAB 편집을 지킨다), 뷰어·편집기 `on_open` 은 그린 회차의
    비활성 층을 서버에서도 거른다(`_open_unless_inactive`). `층 바로 가기`·배치 편집기 `다른 층으로 보내기` 선택지는
    `selectable_floor_keys(keep=연 층)` 이다(글자는 「C1 3F」 그대로 — 상태는 배너). 주소 `?floor=` 가 비활성 층이어도 열고
    늘 서는 칸(`space_floor_inactive_notice_slot`)에 배너를 세운다. 적용 검사(`parse_editor_apply(floors=ALL_FLOORS)`)·
    `valid_location_pairs`·`floor_placements` 는 30개 그대로이고, 목록이 줄기 전에 비활성 층으로 보낸 적용은 받고 flash 끝에
    알린다. FAB 요약은 모든 층 합 그대로에 「 · 비활성 층 n대」 를 붙인다.
- `app_pages/admin_area.py` — 사이드바 맨 아래 자기 상자의 운영 관리 화면으로 `Proc Rename`·`표시순서 관리`·
  `원천 품질`·`알림 모음` 네 탭(`TAB_NAMES`, `stateful_tabs`)을 모은다. 셋째는 `components/source_quality.py`, 넷째는
  `components/alert_board.py` 를 그린다.
  - 앞 두 탭(입력 폼)은 늘 그린다. `원천 품질`(위젯 없는 표 — 원천 읽기에 캐시가 없어 이 탭이 Admin 회차의 유일한 DB
    읽기다)과 `알림 모음`(`load_page_context()` 와 전체 기간 계산)은 닫혀 있으면 건너뛴다(`tab_is_hidden`,
    `tests/test_admin_area_page.py`). 조건 패널은 시나리오 줄만 선다.
  - 두 편집 탭의 붙여넣기 팝업 칸은 페이지에 하나(`components/admin_dialog.py`, 값 `PASTE_DIALOG` 가 탭을 가른다)다.
  - 탭 위에는 C-DEP CD 서버에서만 「서버 시작 점검」 펼침(`components/container_start_check.py`)이 선다 — 결과 파일도
    CD 전용 환경변수도 없는 개발·사내 PC 에서는 아무것도 그리지 않는다.
  - 거래선 정렬은 따로 없다 — `표시순서 관리` 에 `분류컬럼 = Customer` 규칙을 넣는다. 설명은 `guides/admin_area.md`.
- `app_pages/voc.py` — `Admin Area` 아래의 자유 게시판(질문·개선 요청·오류 신고와 답글)이다.
  - 계산에 닿지 않는다 — 시나리오·조회기간을 읽지 않고 `load_page_context()` 를 부르지 않는다.
  - 본문·답글은 `st.text` 로 그리고 게시판 읽기는 캐시하지 않는다. 폼은 `clear_on_submit` 없이 콜백이 성공한
    때만 비우고 작성자 이름은 폼 밖이다. 필터는 조건 카드 `VOC 필터`, 설명은 `guides/voc.md`.
  - 쓰기(새 글·답변·답변 완료 표시·글 삭제)는 모두 콜백이고 본문 `st.rerun()` 이 없다 — 끊긴 회차가 아래 글의
    「삭제 확인」 값을 버려 단추가 사라졌다. 새 글·답변 폼과 답변 완료 단추는 key 세대, 글 삭제는 지운 글 id 로
    빠른 두 번 누름을 거른다(9장, `tests/test_voc_page.py`). 세대 비교와 쓰기는 `components/write_guard.write_once` 라
    두 회차에 겹쳐 오는 더블클릭도 한 번만 쓴다 — 입력은 그 앞에서 읽고 세대 올리기는 뒷정리의 맨 끝이다. 느린 두 번
    누름이 방금 비운 새 폼에 닿은 빈 제출은 `write_guard.just_written` 으로 걸러 성공을 다시 알린다. 아주 빠른 둘째
    누름이 옛 화면의 단추에 닿은 회차(지나간 세대·이미 지운 글)도 쓰기 직후면 성공을 다시 알린다(9장).
  - 그 사이 다른 세션이 지운 글의 답변·답변 완료 표시는 저장소가 같은 쓰기 잠금 안에서 글을 확인해
    `VocPostGoneError` 로 거절한다(`voc_reply.post_id` 에 외래 키가 없어 막지 않으면 주인 없는 답글이 남는다).
    화면은 지운 글 상자 대신 머리 알림 칸에 거절과 적어 둔 답변을 그린다(`tests/test_voc_page.py`).
  - 글 상자 라벨의 제목·작성자와 답글 caption 의 작성자는 마크다운으로 그려지는 자리라
    `components/literal_markdown.py` 로 ASCII 구두점을 escape 해 적은 글자 그대로 싣는다(`tests/test_voc_page.py`).
- `app_pages/scenario_management.py` — `시나리오 관리`·`BigDataQuery 등록`·`자동 갱신` 세 탭(늘 그린다 — form 입력
  보존)으로 시나리오 목록·지금 편집본 복제·월 머지·연도 Shift·원천 등록을 맡는다. 설명은 `guides/scenario_management.md`.
  - 「시나리오 관리」 탭 맨 위 **「관리할 시나리오」 전환**(`scenario_management_kind_v1`, 「시뮬레이션 시나리오」·「설비
    시나리오」, 2026-10-24 사용자 결정 D4)이 고른 쪽 구획만 그린다 — 고르지 않은 쪽의 위젯은 그 회차에 버려진다(아래 「시나리오
    작업」 전환과 같은 성질). 목록·리비전 편집표의 미저장 편집은 위젯이 아니라 행 id 초안이라 전환을 오가도 남는다(Guide 도 그렇게
    적는다). 다른 화면(옛 배포 흔적 경고의 단추)이 값을 적으므로 `default=` 없이 칸이 없거나 목록 밖일 때만
    「시뮬레이션 시나리오」 를 심는다. 「설비 시나리오」 구획(`equipment_scenario_management.render_equipment_scenario_section`)만
    설비 DB 를 열고, 못 읽으면 그 구획 안에서만 알린다. 이 화면에는 사이드바 설비 시나리오 줄이 서지 않는다(구획 머리 「이
    세션: …」 한 줄과 세션 알림). 세 탭을 늘 그리므로 다른 탭을 보는 회차에도 구획이 세션을 푼다 — 그 회차에 세션을 다른
    리비전으로 옮겼다는 한 번뿐인 알림(미저장 설비 편집을 버렸다는 말)은 숨은 패널이 아니라 탭 묶음 위 `st.empty` 자리에
    그린다(`notice_slot`, 빈 자리는 `display:none` 이라 간격이 없다 — 2026-10-25 리뷰, `tests/test_equipment_scenario_screens.py`).
    설비 DB 핀을 선언하지만(`uses_equipment_db`) 게으른 핀이라 시뮬레이션 구획만 그린 회차에는 열지 않는다.
  - 목록 관리는 C안(2026-10-22 사용자 결정)이다 — 목록 편집표(고름·순서·시나리오명 ✎)와 표 위 「변경 저장」·「편집
    버리기」·위로/아래로/맨 위로, 고른 시나리오 카드의 리비전 편집표(고름·리비전명 ✎)와 그 위 「선택한 리비전 불러오기」·
    「공식으로 지정…」(확인 팝업 `OFFICIAL_DIALOG_KEY`)·「이름 저장 (n)」·「편집 버리기」, 카드 아래 늘 서는 접힘 칸 둘(공식
    발행 이력 — r 번호·공식버전명만, 보관된 시나리오). 고름·미저장 편집은 행 id 초안이다(`components/pick_edit_table.py`).
  - 저장은 모두 콜백이고 하나라도 거부되면 아무것도 쓰지 않는다(`apply_scenario_list_edits`·`rename_revisions` →
    `BatchEditRefused`, 결과·오류는 표 위·카드의 늘 서 있는 칸). 이름은 비교 후 쓰기, 순서는 처음 고칠 때의 저장 차례와
    지금 차례가 같을 때만 쓴다. 빠른 두 번 누름은 성공한 저장이 초안을 비우고 이름이 비교 후 쓰기라 두 번 쓰지 않는다.
    목록 차례는 `list_order NULLS LAST, created_at DESC`(`repository._SCENARIO_LIST_ORDER`, 목록과 저장 대조가 같은 글)다 —
    순서를 저장한 적 없는 행은 만든 시각 차례라 이름 변경·새 리비전 저장(「최근 수정」)으로 움직이지 않고 새 시나리오는
    맨 위에 선다. 이름만 바꾼 「변경 저장」은 `list_order` 를 쓰지 않는다(쓰면 그 뒤 새 시나리오가 맨 아래로 간다 —
    `tests/test_scenario_list_edits.py`).
  - 이름의 비교 대상은 그 칸을 처음 고친 편집이 붙은 표가 **보인** 저장 이름(`TableDraft.name_base`)이다 — 마지막 회차에
    다시 읽은 이름과 대조하면 남이 먼저 바꾼 뒤 회차가 한 번만 돌아도 대조가 통과해 남의 이름을 덮었다(2026-10-22 리뷰).
    먼저 바뀐 이름은 저장 전에 경고(`moved_names`)하고, 거부되면 그 행의 이름 편집만 버려(`drop_names`,
    `BatchEditRefused.moved_names`) 지금 이름을 다시 보인다.
  - 새 리비전 저장은 사이드바 시나리오 팝업 한 곳이다 — 이 페이지에는 「리비전 저장」 모드가 없고 모드 줄 아래 한 줄이
    그 길을 적는다(`REVISION_SAVE_GUIDE`).
  - `자동 갱신`(`components/auto_official_update_tab.py`)과 BigDataQuery 사내 조회는 버튼을 누른 회차에만 돈다.
    보관은 숨길 뿐 파일을 줄이지 않는다(회수는 영구 삭제 뒤 `scripts/compact_duckdb.py`).
  - 월 머지·연도 Shift 는 원본을 바꾸지 않고 새 시나리오로 저장하며 `capacity_gate` 파생 검사를 먼저 돈다. 무월 표
    규칙은 `scenario_month_merge.NON_MONTHLY_SUPPLEMENT_KEYS` 한 곳이다(`docs/scenario_merge_shift_implementation.md`).
  - 가상 제품 이력이 있는 리비전의 공식 지정은 폼 밖 확인 체크를 받는다(CLI 는 `--allow-virtual-products` —
    `scripts/bootstrap_initial_duckdb_scenario.py`·`tests/test_bootstrap_initial_duckdb_scenario.py`).
- `app_pages/standard_target_capa.py` — Static 하위에서 월간 공정별 대당 Capa 를 일로 풀고 주차별 가용대수를 곱한
  일 표준 가능량을 표·로직 분석·CSV 로 낸다(조건 카드 `표준 목표 조건`, 설명 `guides/standard_target_capa.md`).
  - 주차 계산은 `simulation_cache.get_weekly_standard_target_capacity`(PKG `get_pkg_equivalent_standard_target`)가
    키만 해시한다 — 소요대수를 해시 인자로 넘기지 않는다(`tests/test_standard_target_weekly_cache.py`). 재공 현황도
    제품 선택을 키에 실어 같은 캐시를 부른다.
  - 공정 필터는 전체 공정 결과(`get_standard_target_weekly_result`)를 거르고, 전체 계산 실패·공백 공정명·빈 결과일
    때만 고른 공정만 계산한다. 결과와 무관한 조작은 소요대수를 다시 풀지 않는다(`get_standard_target_split`).
  - 이 캐시들은 프로세스 전역이라 화면 테스트가 테스트마다 비운다(`tests/test_standard_target_capa_page.py`).
  - 저장된 주차별 가용설비가 0건이면 가용대수를 곱하는 표시 항목(`AVAILABILITY_BASED_METRICS` — 일 표준 가능량·가용대수)만
    입력 안내로 멈춘다. 대당 일 Capa·로직 분석은 그대로 선다 — 계산(`build_weekly_standard_target_capacity`)은 빈
    가용설비를 가용대수 빈칸으로 받는다(「행이 없습니다」 거절은 붙여넣기·저장 경로의 몫).
  - 로직 분석 식 세 줄(대당 Capa·대당 일 Capa·일 표준 가능량)도 **적힌 수로 다시 셈해도 적힌 결과**가 나와야 한다(제약
    시뮬레이션 고른 달 계산과 같은 규칙) — 결과는 원값의 둘째 자리 그대로 두고, 깎은 인수로 어긋날 때만 더 적는 자리 수의 합이
    가장 작게(같으면 오른 인수 먼저) 인수를 한 자리씩, 여섯째 자리까지 더 적는다(`_formula_operands` — 「54,698.63 ÷ 1.49386
    = 36,615.63」, 2026-10-26 E2E 3회차에 「÷ 1.49」 로 0.26% 어긋났다). 그래도 못 맞추면 처음 자리로 적고 등호를 「≈」 로
    둔다(9장 「화면 숫자는 검산되어야 한다」).
- `src/capa_simulation/components/reference_csv_tools.py` — 입력 RQ 월별 Wide 표의 UTF-8 CSV 양식 내려받기와 Excel
  붙여넣기 팝업 폼·적용 알림을 공통 제공한다(`render_reference_clipboard_form` 은 양식과 붙여넣기 칸만 그린다).
- `src/capa_simulation/components/horizontal_scrollbar.py` — HOME 월별 영역과 동기화되는 Components v2 가로 스크롤바다.
  - `initial_offset_px` 는 처음 그릴 때 한 번만 건다 — 적용 표시를 대상 요소의 `dataset` 에 남겨 리런이 사용자가
    옮긴 위치를 되돌리지 않게 하고, 적용은 `ResizeObserver` 가 폭을 잡은 뒤로 미룬다.
- `src/capa_simulation/components/month_range_picker.py` — 조회기간 팝업(`components/period_field.py`)의 시작·종료 월
  칸과 「적용」을 한 Components v2 컴포넌트로 묶는다(`render_month_range_apply` 는 적용한 회차에만 범위를 준다).
  - 칸 값은 초안이고 「적용」·Enter 때만 검사해 보낸다. 팝업 포커스 때문에 그림자 DOM 에 가두지 않는다
    (`isolate_styles=False`). 부르는 쪽은 모듈 속성으로 부른다(테스트가 갈아끼운다).
- `src/capa_simulation/components/condition_field.py` — 사이드바 통합 조건 패널의 한 줄(이름 줄 `condition_name_row`
  과 팝업을 여는 값 칸 `condition_field`)을 그린다.
  - 컨테이너 key 접두어(`condition_field_<slug>`·`condition_name_<slug>`)로 `sidebar_style.py` 가 서식을 건다.
    `with` 안에서는 `st.*` 로만 그린다 — `st.sidebar.*` 는 `with` 를 따르지 않아 패널 밖으로 샌다.
- `src/capa_simulation/components/period_field.py` — 패널의 조회기간 줄과 그 팝업(`sidebar_period_open_dialog`)을 그린다.
  - 팝업 안 월 선택은 초안이고 「적용」해 범위가 실제로 바뀔 때만 `MONTH_RANGE_KEY` 를 쓴다. 고를 수 있는 범위는
    매 회차 `month_selection_bounds()` 로 읽고 범위 밖 조회기간은 `clamp_month_range` 로 끝에 끼워 되적는다.
- `src/capa_simulation/components/scenario_status.py` — 사이드바 조건 패널의 시나리오 줄과 불러오기·새 리비전 저장·
  편집 되돌리기 팝업(`SCENARIO_DIALOG_KEY`)이다. 이름 변경·발행·삭제·신규 생성은 `시나리오 관리` 페이지 몫이고, 불러오기
  구획 끝 한 줄이 그리로 간다(「시나리오 관리에서 이름 바꾸기」 — 그 페이지에서 연 팝업이면 링크 대신 표 자리를 적는다).
  - 줄은 세션만 읽고 저장소는 팝업을 연 동안에만 읽는다(팝업 프래그먼트는 `app.py` 의 실행 핀 밖이라
    `pinned_connections` 를 스스로 잡는다). `tests/test_scenario_sidebar.py`·`test_app_navigation.py` 가 고정한다.
  - **적용하지 않은 편집은 시나리오에 없다** — 누른 회차에 `pending_edit_labels` 를 다시 세어 폼 밖 체크를 받는다.
    저장 폼은 성공 회차에만 key 세대(`SAVE_FORM_GENERATION_KEY`)를 올려 비운다.
  - 저장은 부모 리비전의 가상 제품 이력에 세션 등록을 더해 넘긴다(`inherit_virtual_product_records`, 활성화 전에 읽음).
  - **리비전 불러오기는 `load_saved_revision` 한 길이다** — 팝업 「불러오기」와 HOME 주요 Case 칩이 함께 쓴다(옛 리비전
    호환 검사 → 활성화 → 필드 알림·적용 전 편집 목록 비우기·팝업 닫기, 다시 돌리기는 부르는 쪽 — 팝업은 `st.rerun()`,
    칩은 콜백). `open_scenario_dialog_on` 은 팝업을 불러오기 구획·주어진 짝으로 연다(칩이 편집이 있을 때 같은 확인을
    거치는 길).
- `src/capa_simulation/components/space_layout.py` — Space 배치 집계(대수·점유율·층별 배치 `floor_placements`), 호기
  상자 면·글자(`unit_appearance`), 층 상세 범례(`space_legend_counts`), 층 상세 호기 표(`floor_table`·
  `picked_unit_rows`)와 영역·금지 색을 만든다. 색 기준 「필요 단축」 은 블록 셋째 줄(`floor_block_stats(short_lines=)` — 비활성
  층에는 싣지 않음)·구간 얹기(`apply_layer_looks` — 표시 호기 면을 비워 브라우저가 구간 변수로 칠함)·범례
  (`shortening_legend_markup` — 구간 넷·임박 테·흐림 + 테·덧표시 칸, 채우기 칸 없음)다.
  - 경계 날짜는 인자로 받는다(층 상세는 `simulation_cache.get_space_unit_boundaries` 로 한 번 구해 나눠 쓴다).
    Plotly 를 쓰지 않고 동·층 정의는 `services/fab_layout.py` 다. 층 블록 글자는 배치·미배치 대수뿐이고, 비활성 층
    블록은 그 대신 사유다(`floor_block_stats(inactive=)` — 그 층 칸에만 `inactive`, 대수 칸은 풍선에 남는다).
  - 층 캔버스는 `equipment_ops.floor_layout_profile` 의 층별 값이고 `invalid_equipment_rows` 도 같은 캔버스로
    판정한다. 편집기 모듈을 import 하지 않는다(그쪽은 읽을 때 컴포넌트를 등록한다).
- `src/capa_simulation/components/space_floor_list.py` — Space FAB 전체 아래 **층 목록**(2026-10-24 결정 S1~S6). 보기는
  사용 층 표(`사용` 칸, 행 고르기 = 층 열기)와 늘 서는 자리 칸 안의 접힌 「비활성 층 n개」 표(거기서도 연다), 표 머리
  `사용 편집` 토글을 켜면 저장 줄 · 끄기 확인 · 알림 · 동 머리 줄(`st.segmented_control` 다섯 — 값은 회차마다 초안에서
  세션에 적고 `default=`·세대 꼬리 없음) · 30줄 편집표다.
  - 초안(「C1 3F」 → 사유 코드)·편집 시작 저장본 `(version, rows)`·확인 대기·단추 세대는 세션 칸이고, 편집표 칸 편집은
    회차마다·콜백 첫머리에 초안으로 접는다(`_fold` — 빈 사유는 「사용 안 함」, 사용 층에서 사유를 고르면 끄기). 칸 편집은
    위젯에 남아 접은 초안을 그린 위에 얹혀 보이므로, 다시 세우는 것(`discard_editor`)은 그렇게 보일 값이 접은 값과 다를
    때뿐이다(비활성 층의 사유 지움 등) — 끄기·켜기·사유 고르기는 같은 위젯이라 보던 스크롤·초점이 남는다. `사유` 칸은
    `string` 으로 고정한다(9장 「편집표와 내려받기」). 쓰기 단추는 그린 회차의 세대를 인자로 받아 옛 누름을 거른다.
  - 호기가 남은 층을 새로 끄면 막지 않고 확인한다(호기 수는 편집 모드 본문이 센 `floor_unit_counts` 를 콜백 인자로).
    저장은 `save_floor_states(expected_version=…)` → 성공이면 `clear_floor_state_cache`·flash·토글 끄기, 충돌이면 알림
    칸 `st.warning` 과 초안을 최신으로 다시 세움, 같은 내용이면 `st.info`. 토글이 꺼진 채 그려지는 회차는 남은 초안을
    지운다(층을 열면 토글 위젯 상태가 버려진다). `floor_state_draft_pending()` 은 세션만 읽는 Space 탭 점·떠나기
    확인·테마 전환 표지다(`page_tabs.page_unsaved_marks`·`leave_notice` — Space 가 지금 화면일 때만) — `app.py` 가
    페이지보다 먼저 부르므로 이 회차 편집표 위젯 상태의 칸 편집까지 (적지 않고) 접어 저장본과 견준다.
  - **공식 설비 시나리오에서만 연다**(설비 시나리오 2단계 Q3 — 건물·층은 가정 시나리오가 없다, FAB 전체와 같은 까닭). 가정
    세션과 샘플 fleet 화면에서는 잠근다(값도 끈다 — `locked_reason` 풍선). 끄기 확인은 공식 배치의 호기 수에 더해 가정 설비
    시나리오의 배치에서 그 층에 놓인 호기 수를 덧줄로 적는다(`equipment_cache.load_layout_overlay_floor_counts` — 층 사용은
    공통이라 그 시나리오 목록·도면에서도 숨는다, 설계 13-2). 공식 배치에는 호기가 없어도 가정 배치가 그 층에 호기를 두었으면
    확인 대상이다(목록 꼬리 「공식 배치 호기 없음(가정 배치에만)」 — 배치안이 빈 층을 쓰는 경우). 초안이 있는데 사이드바 팝업에서
    가정 설비 시나리오를 고르면 「변경을 버리고 불러오기」 를 묻고(설계 9장), 불러온 회차에 팝업이 토글·초안을 걷는다
    (`discard_floor_state_draft` — Space 가 잠그며 버리기를 기다리면 그 앞의 `app.py` 탭 점·떠나기 확인이 버린 초안을 한 회차
    더 센다). 이 모듈에는 Streamlit 캐시를 두지 않는다.
  - 보기 표의 덧붙임 칸은 `extra_columns`(`FloorListColumn` — 칸 이름·층마다 값·칸 설정·`active_only`) 한 인자다. 「공식과
    견주기」 의 「공식과 다름」 은 사용·비활성 두 표에, 색 기준 「필요 단축」 을 켠 동안의 칸 넷(`단축 호기`·`최대 단축(일)`·
    `기한 지남`·`추가 호기` — `layer_columns`, `active_only=True`)은 사용 층 표에만 선다(비활성 층에는 층 대수를 싣지 않는다).
    둘 다 켜면 넘긴 차례(「공식과 다름」 → 칸 넷)로 기본 칸 뒤에 선다.
- `src/capa_simulation/components/space_floor_layout.py` — Space 가 그리는 층 도면 요소·Main 설비명 위치의 한 곳(설비 시나리오
  2단계 S3). `effective_floor_layout(db, 층, 세션)` = 공식 층 현행값(`load_floor_layout_marks`·`load_floor_group_labels` — 쓰기
  세대 캐시) ⊕ 세션 리비전의 요소·이름표 차이(`load_schedule_layout_overlay` — 일정 id 키 불변 칸, 차이 없으면 질의 없음)를
  회차마다 합친다(층 하나·수십 요소 — 캐시하지 않는다, 이 모듈에 캐시 데코레이터 없음). `floor_layout_differences` 는 머리
  알림의 실효 요소·이름표 수, `space_layout_notices` 는 머리 알림 줄(그리는 스냅샷 기준 — 설계 8-2)이다. 「공식과 견주기」(S4)
  재료 `compare_payload`(층 상세 뷰어 `compare`)·`floor_unit_differences`(FAB 층 목록 칸·블록 풍선)도 여기다 — 둘 다 그리는 세션
  스냅샷의 합친 본문과 마스터만 읽는다.
- `src/capa_simulation/components/floor_layout_upload.py` — Space 층·FAB 전체의 배경 도면 업로드·삭제와 캔버스 치수
  팝업(`FLOOR_LAYOUT_DIALOG_KEY`)이다. 성공하면 팝업 칸을 비우고 앱 전체를 다시 돌린다.
  - 캔버스를 줄여 생기는 호기 이탈은 저장된 설비 마스터의 그 층 호기 전부로 잰다(저장 검증과 같은 행, 확인 체크).
    도면 요소 이탈은 저장소가 거부하므로 단추를 막는다. 저장·삭제 뒤 그 층의 미저장 캔버스를 버린다.
  - 층이면 가정 설비 시나리오 배치도 미리 본다(S4 — 설계 6-4, `equipment_cache.load_layout_overlay_extent` — 캔버스를 바꾸는
    저장이 보는 ACTIVE 최신·최신 공식 발행의 그 층 차이). 차이 요소는 저장소가 막으므로 공식 요소처럼 범위에 넣어 단추를 끄고
    (「가정 배치 「…」 의 요소도 밖입니다」), 차이 호기는 공식 호기처럼 경고(「가정 배치 「…」 호기 n대가 범위를 벗어납니다」) 뒤
    같은 확인 체크로 받는다(그 시나리오의 다음 저장만 막힌다). 지우기의 기본 캔버스 캡션도 둘을 함께 센다.
- `src/capa_simulation/components/space_layout_editor.py` — Space 층·FAB 도면의 Components v2 편집기와 보기 전용 뷰어
  (`render_space_layout_viewer`·`render_fab_layout_viewer`·`render_fab_layout_editor`)다.
  - 「필요 단축」 payload(층 보기만, 값이 있을 때만 키 — 끈 동안 payload 그대로): 호기 `layer`(`s|m|l|x`)·`dim`,
    `shortBadges`(설비키마다 하나 — `ids` 는 그 층에 그린 모듈), `asOfPinned`(고정 줄 뒷글). 팔레트 `short-*` 칸은 늘 싣는다
    (CSS 변수는 모두 팔레트에 — 시험). JS 배지 자리는 `// <short-badge>` 구획의 순수 `badgeSpot`·`settleBadges`(배지끼리
    겹치면 뒤 배지가 한 칸 위로, 그래도 겹치면 그 배율에서 숨음)이다(node 시험). 배지를 다시 그릴 때 초점을 쥔 배지는 같은
    key(`data-key`)의 새 배지로 돌려준다(키보드로 고를 때 초점이 문서 처음으로 빠지지 않게). 「공식과 견주기」(`compare`)와
    함께 켜지면 견주기 층 `sle-compare` 가 흐린 상자·배지 층 `sle-short-badges` 위에 선다(눌림이 없어 배지 누르기는 그대로) —
    꼬리표와 배지가 서로 비키지는 않는다. FAB 블록 풍선은 단축 줄(`short`) 뒤에 견주기 줄(`layout`)이다.
  - HTML·CSS·JS 는 `space_layout_editor_assets/` 파일이고 모듈을 읽을 때 한 번 등록한다(`_EDITOR` — AppTest 는 JS 를
    못 돌려 `tests/conftest.py` 가 말 없는 대역을 깐다).
  - 편집 상태는 브라우저가 쥐고 `적용` 때 한 번 보내며 검증은 서비스(`parse_editor_apply`)다. epoch(내용 지문)가
    같으면 편집·배율을 지키고, 옛 epoch 로 온 적용·블록 열기(`on_navigate_change`)·호기 누르기(`on_pick_change`)는
    버린다.
  - FAB 블록 글자 `linkStats` 의 `inactive`(비활성 층의 짧은 사유)가 있으면 JS 가 그 블록을 `is-inactive` 로 —
    팔레트 `block-off` 면 + `#sle-hatch` 빗금 + `muted` 글자(고른 색·「글자 색」 인라인을 달지 않는다)로 그리고, 보기에서는
    `opensFloor` 가 거짓이라 열지도 고르지도 않으며(누름 갈래는 블록 종류로 `lastViewOnBlock`) 초점·역할을 걷는다. 편집에서는
    옮기기·연결은 되고 `[열기]` 만 꺼진다(`syncInspector`).
  - 호기 값은 `_clean_items`·첫 회차 `readUnit`·같은 epoch 합치기 세 경로를 모두 지난다. CSS 의 `--sle-*` 는 모두
    `_palette()` 에 둔다(블록 색 대비는 `tests/test_design_tokens.py`). 보기 높이는 localStorage 에만 둔다.
  - **Main 설비 모듈 묶음**(편집기 모듈 + 숨은 모듈이 둘 이상, 2026-10-23 사용자 요청)은 묶음 범위(이 층 도면에 선
    모듈의 바깥 상자)만 고치고 안은 바둑판 자동 배치다 — 모듈 2·3 은 가로 한 줄(열 n·행 1), 넷부터 ⌈√n⌉ 열(넷이면
    2×2, 2026-10-23 사용자 답). 바둑판 순수 함수는 `// <module-tiling>` 구획(`moduleGrid`·`moduleCells`·
    `tileModuleGroup`·`assignModuleCells`·`tileDeviation`·`relaidGroup`·`groupLabelDefault`)이고 파이썬 정본
    `space_layout_edit` 과 같은 규칙이다(`tests/test_space_module_group.py` 가 node 로 대조). 서랍에서 여러 덩이를 한
    번에 놓을 때 덩이끼리의 격자(`trayPlan`)는 이것과 따로 ⌈√n⌉ 열 그대로다(셋이면 2×2). 모듈 하나만 옮기거나 키우는 길은 없다 — 끌기·방향키·
    X·Y 칸은 `movePlan`(묶음은 범위), 크기(폭·높이 칸·Ctrl+방향키)는 `setSizes`, 범위 테두리 손잡이는
    `mode: 'range'`(`sle-range-handle`, 모듈 상자 손잡이는 `is-module` 로 숨김)이고 셋 모두 `relayGroup` 으로 다시
    놓는다. 선택은 묶음당 한 대(`onePerGroup`), 고른 묶음 범위 안의 빈 칸을 눌러도 그 묶음을 끈다(`pickedRangeAt`),
    빼기·다른 층 보내기·서랍 놓기는 묶음째다. 묶음 조작 하나가 되돌리기 한 번이다.
    - 칸 자리는 지금 자리를 지킨다(`assignModuleCells` — 이미 바둑판이면 이름 차례와 상관없이 제 칸, 옛 묶음은 가까운
      칸). 자연 정렬은 서랍에서 새로 놓을 때(`naturalSlots`)와 좌표 없던 형제에만 쓴다. 「n등분이 아님」 판정도 칸
      모양(`tileDeviation`)이다.
    - 바둑판이 아닌 옛 묶음은 읽을 때 바꾸지 않고, 범위가 실제로 바뀌는 첫 조작(또는 「범위에 맞춰 n등분」)에 그 범위로
      다시 놓는다. 범위가 눈금까지 그대로인 조작(벽에 막힌 방향키·제자리에서 뗀 끌기·같은 숫자)은 다시 놓지 않는다.
      1·2차 규칙(셋도 2×2)으로 놓인 모듈 셋 묶음도 이 옛 묶음이다(「3등분이 아님」 — 처음 만질 때 한 줄로 선다).
    - 숨은 모듈(`data.ghosts` → `S.ghosts`, 파이썬 `EditorInputs.ghosts`)은 그리지 않고 고르지 않지만 칸 수·자리에 들고
      (고른 묶음에서 점선 `sle-ghost-cell`) 묶음과 함께 옮겨져 적용값 `ghosts` 로 간다. 되돌리기·끌기 취소는 `itemOf` 로
      숨은 모듈도 되돌리고, 묶음 이름을 바꿔도 처음 Main 설비 이름(`groupKeyOf`)으로 이어진다. 보기 화면은 그대로다.
      묶음째 도면에서 빠지면(빼기·Delete·다른 층 보내기) 숨은 모듈은 처음(편집기에 실린) 자리로 돌아간다
      (`restoreGhosts`, 빼기·보내기와 같은 되돌리기 기록) — 옮기지 않고 바로 뺀 것과 같다.
  - **편집 조작 넷**(2026-10-23 사용자 요청, 층·FAB 편집 공통). 순수 판정은 `// <edit-tools>` 구획(`nearestSnap`·
    `guideSegments`·`namePrefix`·`borrowedSize`·`trayRangeIds`·`pasteShift`·`freeLinks`)이고
    `tests/test_space_editor_tools.py` 가 node 로 돌린다(둘레 함수는 선언 그대로 떼어 돌린다).
    - 정렬선: 끌기·크기(`alignDrag`)·서랍·팔레트 놓기·붙여넣기(`dropSpot`)에서 움직이는 것(모듈 묶음은 범위 — 1차 규칙)의
      왼·가운데·오른 x 와 아래·가운데·위 y 가 화면(viewBox)에 걸친 다른 호기·요소(묶음은 범위, `guideTargets`)의 선과 화면
      6px 안이면 그 선에 붙는다. 격자보다 먼저이고 Alt 면 붙지 않는다. 선은 맨 위 `sle-guides` 층에 긋고(색 `guide` =
      `tokens.SPACE_GUIDE`) 놓으면 지운다. 크기 바꾸기는 움직이는 변만 본다.
    - 크기 불러오기: 서랍에서 크기 없는 호기만, 같은 앞 3자리(공백은 파이썬 `str.strip` 의 것)·같은 종류(모듈 / 그 밖 —
      모듈은 편집본 전체에서 Main 설비 행이 둘 이상, `newUnit.moduleParents`) 가운데 이번 편집에서 마지막으로 놓은
      것(`S.placedLog`, 지금도 서 있고 층 가운데 크기 어림이 아닌 것) → 편집본에서 설비명 자연 정렬이 가장 뒤인 것
      (`newUnit.prefixSizes` = 파이썬 `prefix_sizes`) → 이 층 가운데 크기(`defaultSize`). 빌린 크기는 `sizeGuessed`·
      `sizeFrom` 이고 상태 줄에 「크기를 … 에서 불러옴」을 쓴다(`trayPlan`).
    - 서랍 Shift 범위(`pickChip`): 기준 칩(마지막으로 그냥·Ctrl 로 누른 칩, `S.trayAnchor`)부터 누른 칩까지 지금 보이는
      차례, Ctrl+Shift 는 더하기, 묶음 칩은 한 칸.
  - **키보드**(2026-10-26 E2E — 마우스 없이는 호기 하나를 고르거나 칩을 놓을 길이 없었다). 호기 상자(편집·층 보기)와 편집의
    도면 요소는 Tab 자리(`tabindex`·`role=button`·`aria-pressed`)이고 Enter·Space 가 누르기다(`host.onkeydown` — 편집은
    그것 하나, Ctrl·Shift 는 `toggleSelected`; 층 보기는 `select` + `notePick`). 서랍 칩은 이름(`sle-chip-name`)이 단추라
    「×」 와 나란하다 — Enter 는 보이는 도면 가운데(서랍 몫 `trayReserve` 를 뺀)에 놓고 초점을 놓은 호기로(`placeChipByKey`),
    Space 는 `pickChip`. 초점 테는 화면 px 로 띄운 rect(`sle-focus-ring`, `FOCUS_GAP_PX`)다 — SVG 안의 outline 은 배율로
    커진다. `renderItems` 는 그리기 전 초점(`focusSpot`)을 같은 id 의 새 노드로 돌려주고(`restoreFocus`), 칩이 사라졌으면
    (「×」 추가 취소 — 낭독 이름은 「<호기> 추가 취소」) 같은 자리의 이웃 칩, 없으면 검색 칸에 둔다(BODY 로 빠지지 않게). 시험은
    `tests/test_space_editor_keyboard.py`(되돌리기는 node).
    - 도면 요소 복사·붙여넣기(`copyMarks`·`pasteMarks`): 호기는 복사하지 않는다. 클립보드는 범위별 sessionStorage
      (`capa.space.clipboard.<floor|fab>`) + 페이지 안 쪽지(`window.__capaSpaceClipboard`)이고 모든 읽기·쓰기가 try 안이다.
      마우스가 도면 위면 그 자리가 묶음 가운데(`dropSpot`), 아니면 원본에서 max(격자, 1)씩 비켜(거듭하면 더) 붙인다. 영역
      안으로 밀고 새 id·되돌리기 한 번이며 층 블록은 빈 층(`freeLinks`)을 가리킨다. 글 칸 입력 중에는 가로채지 않는다.
      사본이 같은 종류 요소와 자리·크기까지 똑같이 겹치지 않는다(`stacksOnMarks`) — 마우스 자리가 원본 그대로면 비켜
      붙이기로 넘기고, 비켜 붙일 때 영역 끝에 막힌 축은 반대쪽으로 비키며(`pasteShift`), 그래도 겹치면 붙이지 않고 알린다.
      복사·붙여넣기 알림(`S.flash`)은 새 epoch 에서 지운다.
  - **모양·저장 셋**(2026-10-23 사용자 요청, 층·FAB 공통 — 3번째는 층만). 자리 계산은 `// <layout-look>` 구획
    (`zoneTagX`·`groupNameSpot`·`groupNameSize`·`shownRange`)이고 `tests/test_space_editor_tools.py` 가 node 로 돌린다.
    - 영역 테두리 모양(`borderStyle` 점선·실선)·이름표 정렬(`labelAlign` 왼쪽·가운데·오른쪽, 위 변 꼬리표)은 처음 값이 지금
      모습(점선·왼쪽)이고 영역 선택 칸의 `테두리`·`글자 정렬` 로 고른다. 고른 영역의 강조는 테두리 모양을 바꾸지 않고
      바깥 강조 테(`sle-zone-select`)로 따로 보인다. 읽기·바뀜 판정·적용값·복사·되돌리기 기록에 모두 든다.
    - 반입 예정(실물 없음) 테는 3.5px 점선(범례 견본 3px, `space_layout._mark_swatches`), TEST 면은 연한 남색에 검정
      글자다(`tokens.SPACE_LINE_TYPE_FILLS`·`_INKS` — 다른 면과의 ΔE 는 `tests/test_design_tokens.py`).
    - Main 설비명: 모듈 묶음(편집기 모듈 + 숨은 모듈 둘 이상, `moduleGroups`)의 범위에 `sle-group-names` 층(눌림 없음)으로
      알약 바탕 + 모듈 이름보다 굵은 글자를 그린다. 위치는 가운데(범위 정가운데)·위·아래(범위 바깥 바로 위·아래)이고,
      고른 위치(저장된 행 포함)는 묶음 열쇠(`groupKeyOf`)마다 `S.groupLabels` 에 쥔다. 고른 적이 없는 묶음은 모양의 처음
      위치(`groupLabelDefault` — 한 줄 묶음(모듈 2·3)은 위, 그 밖은 가운데, 2026-10-24 결정 (e))다. 모듈 수는 편집기는
      숨은 모듈까지(`groupCounts` = 파이썬 `module_group_sizes`), 보기 화면은 그리는 모듈만 센다(숨은 모듈을 받지 않아 드물게
      다를 수 있다). 묶음을 고르면 선택 칸
      `Main 설비명` 에서 바꾼다(되돌리기 한 번, `op: 'groupLabel'` — 처음 고른 것을 되돌리면 「고른 적 없음」으로). 적용값 `groupLabels` 는 이 층에 남는 묶음마다 [{group: 열쇠, position}](다른 층으로 보낸 묶음은
      빠짐)이다. `drawSelectionBox` 가 부르므로 옮기기·크기·배율을 따라가고, 보기 화면은 기준일에 묶음의 모듈이 하나도
      보이지 않으면(`__visible`) 이름도 숨기며 일부만 보이면 보이는 모듈의 바깥 상자(`shownRange`)에 세운다. 글자는 화면
      12px 에서 범위 폭에 맞춰 줄고 가운데는 범위 높이의 0.16 배까지이며 7px(`UNIT_LABEL_MIN_PX`) 아래면 숨는다 — 다만
      모듈 칸 이름표가 하나도 서 있지 않은 묶음의 가운데 이름은 7px 알약이 범위 안에 들면 7px 로 선다. 위·아래 알약이
      영역 위·아래 끝을 넘으면 범위 안쪽 띠로 뒤집는다(`groupNameSpot`).
  - **층 상세 보기 둘**(2026-10-23 사용자 요청 3·8, 보기 전용 층 뷰어만 — FAB·배치 편집기는 그대로).
    - 호기 누르기: 끌지 않고 누른 뒤·Esc 뒤 `notePick` 이 고른 호기(호기가 아니면 null)를 트리거 `pick`
      (`{epoch, id}`)으로 보낸다 — 같은 값은 다시 보내지 않는다. 파이썬 `_dispatch_pick` 이 epoch 를 대조해 `on_pick` 을
      부른다. `data.picked`(파이썬이 쥔 값)가 바뀐 회차에 `syncPick` 이 도면의 고르기를 맞추고 새로 선 도면은 다시 고른다.
      문턱(3px)을 넘은 끌기(`drag.travelled` — 전체 보기에서 화면이 움직이지 않아도)는 누르기가 아니다.
    - 겹친 반입 예정 숨기기: 기준일에 반입 전인 호기가 그날 보이는(반입했고 안 빠진) 다른 호기와 넓이가 0 보다 크게
      겹치면 `is-covered`(visibility hidden)다. 판정은 `// <view-cover>` 구획(`coveredBy`·`unitCountText`,
      `tests/test_space_viewer_pick.py` 가 node 로 돌림)이고 이웃은 겹침 짝(`overlapPairs`, `renderItems` 가 칠하기 전에
      비움)이다. 반입 전끼리·같은 Main 설비 묶음 모듈끼리는 숨기지 않는다. 숨김은 `__visible` 에 들어 Main 설비명·겹침
      꼭지가 따라가고, 판정이 바뀐 호기의 겹침 이웃도 다시 칠한다(`paintUnits`). 숨긴 호기의 설비지분(`share`) 합은
      `showSummary` 가 요약 끝에 「겹쳐 숨긴 반입 예정 n대」로 붙인다(파이썬 범례 대수는 그대로). 지분은 파이썬 기준일의
      것이라(같은 epoch 회차에도 `unitLook` 으로 새로 받음) 페이더를 끄는 동안에는 숨김(그날)과 지분(직전 날)이 섞인다.
- `src/capa_simulation/components/dynamic_capacity_dashboard.py` — Dynamic Capa 공정 비교·Capa 손실 Waterfall·일별
  표준·실효·실적 추이 Figure 를 만든다. 공정 간 단위가 다르면 수량을 합치지 않고 비율만 견준다.
- `src/capa_simulation/components/sample_data.py` — 원천이 붙지 않은 화면의 샘플 표시 스위치와 끈 상태의 자리표시자
  (`render_pending_source`)다. 세션 키 `dynamic_capa_sample_data` 하나를 미연결 화면 전체가 공유한다.
- `src/capa_simulation/components/performance_actual_screen.py` — 효율·UPEH·수율 실적 화면 한 벌로 `MetricSpec` 만
  갈아 끼운다.
  - 요약·상세 분석·개선과제 탭은 `stateful_tabs` 이고 숨은 탭에서도 조건 위젯은 그리며 Plotly 만 건너뛴다. 상세
    분석 `공정` 상자는 겹친 표시명을 가르고 매 회차 값을 다시 적는다(8장 ②).
- `src/capa_simulation/components/table_view_controls.py` — 편집표의 볼 컬럼·행 필터를 고르게 하고 거른 편집분을
  원본 전체에 되머지한다(가용설비 현황 설비 마스터 탭 세 표, 「설정」 팝업 Cut-off 표).
  - 행 필터 중에는 `num_rows="fixed"` 다 — 이 표들은 편집 결과가 곧 다음 리비전 전부다. 거른 편집인지는 호출자가
    `merge_edited_rows` 의 `filtered` 로 알려 준다(`tests/test_table_view_controls.py`). 모든 행이 남는 거름(「Select
    all」·한 호기뿐인 표의 「표에서 고치기」)은 원본(RangeIndex)을 그대로 돌려준다 — `.loc` 의 일반 정수 Index 를
    행 추가가 열린 편집표에 넘기면 Streamlit 1.63 이 `hide_index=True` 를 무시하고 머리 없는 인덱스 칸을 세운다.
  - 보이는 행이 바뀌면 `discard_editor` 로 새 위젯을 세운다. 보기 설정 위젯은 `st.form` 밖이고 `value_labels` 는
    보이는 글자만 바꾼다.
- `src/capa_simulation/components/securement_heatmap.py` — `산출 결과` 의 공정 × 월 확보율 상태 3색 격자다(범례 없이
  hover·칸 안 숫자가 값을 말한다).
  - 경계는 공용 판정 기준 프로필(`load_global_securement_threshold`)이고 두 축 모두 범주, 모든 행에 공정 이름이다.
  - HOME `주요공정 확보율`(`home_figures.build_key_process_heatmap_figures`)과는 다른 그림이고 판정 경계의 뜻만 같다.
- `src/capa_simulation/components/capacity_gate.py` — 리비전 저장·복제·파생 저장·공식 발행 **전에** 시나리오 전체
  기간 Capa 계산(대당 Capa·소요대수 + HOME Density 환산 `density_error`)이 되는지 검사한다.
  - 저장은 편집이 새로 깨뜨렸으면 막고 원래 안 되면 경고하며 허락한다(파생 저장은 원본이 「편집 전」). 발행은 막는다.
    소요대수에 들지 않은 수요는 막지 않고 건수를 경고한다.
  - 계산 페이지와 같은 캐시 칸(`pristine_content_token`)을 쓰고 BigDataQuery 등록·내장 시드는 검사하지 않는다. 새
    쓰기 경로는 `tests/test_capacity_gate.py` 목록에 더한다(`density_error` 는 `tests/test_gate_density_coverage.py`).
  - 자동 갱신 발행은 순수 코어 `simulation_cache.full_capacity_outcome` 로 같은 검사를 하고 경고를 실행 기록에 붙인다.
- `src/capa_simulation/components/capacity_assumption_notice.py` — 측정률 행이 없어 중립값 1.0 으로 이어 간 건수와
  달(조회기간 밖 포함)을 HOME·`산출 결과` 에 한 줄로 알리고, `알림 모음` 도 같은 문장(`assumption_message`)을 쓴다
  (6장 대당 Capa). 가정이 없으면 그리지 않는다.
- `src/capa_simulation/components/required_exclusion_notice.py` — 소요대수에 들지 않은 수요의 건수 문장
  (`required_exclusion_message`)과 산출 결과 소요대수 탭의 계획 쪽 목록 둘(`render_plan_exclusion_lists`)을 낸다.
  - 문장은 `알림 모음`·`capacity_gate`·자동 갱신이 모두 시나리오 전체 기간(`FULL_SCOPE`)으로 쓴다 — HOME 에는 띄우지
    않는다. 경로 쪽 `소요대수 제외 기준정보` 와 따로 둔다.
- `src/capa_simulation/components/alert_board.py` — Admin Area `알림 모음` 탭. 활성 시나리오의 계산 알림 셋(계산 멈춤 ·
  소요대수에 들지 않은 수요 · 측정률 가정)을 시나리오 전체 기간으로 늘 같은 차례에 둔다(없는 것은 「없음」).
  - 저장·발행 검사와 같은 `get_full_capacity_outcome` 캐시와 `capacity_gate.density_error` 를 읽어 문장도 같다. 고르는
    규칙은 순수 함수 `collect_alerts`(`tests/test_alert_board.py`)다.
- `src/capa_simulation/components/container_start_check.py` — Admin Area 탭 위 「서버 시작 점검」 펼침. C-DEP CD 시작
  스크립트의 결과 파일(`io/container_start_report.py`)이 있을 때만 단계 표(설치·로그인 토큰 파일·요청자 계정)·깔린 판·
  토큰 파일 수정 시각·자리·실행 사용자·HOME·비어 있던 환경변수·pip 출력 끝을 싣는다. 결과 파일이 없는데 CD 전용
  환경변수(`CD_ONLY_ENVIRONMENT`)가 앱에 있으면 「결과 없음」 펼침으로 스크립트가 돌지 않았거나 결과를 쓰지 못했음을
  알린다(`missing_report_notice`). 회차마다 그 작은 JSON 만 읽고 DB 를 열지 않는다.
- `src/capa_simulation/components/exclusion_table.py` — `산출 결과` 의 두 제외 표를 그리는 단일 렌더러다. 화면은
  표시명 복사본, CSV 는 원본이고, 캐시된 `attrs` 유래 입력을 제자리에서 고치지 않는다.
- `src/capa_simulation/components/exclusion_waterfall.py` — 후보 경로 → 사유별 차감 → 남은 경로 워터폴(단위는 경로
  수)이다. 사유 순서는 `services/unit_capacity.py` 가 거르는 차례와 같아야 한다(앞 사유가 행을 가져간다).
- `src/capa_simulation/components/plan_comparison_dumbbell.py` — 두 시나리오의 기간 계획 물량 차이를 분류별 덤벨로
  그린다. 한쪽에만 있는 분류는 다른 쪽을 0 으로 보고 연결선은 `DELTA_*` 다.
  - 그림은 `build_plan_comparison_dumbbell` 이 만들고 `render_plan_comparison_dumbbell` 은 받은 그림만 그린다(HOME 은
    계획 세부수량 Figure 묶음에 함께 캐시한다).
- `src/capa_simulation/components/source_quality.py` — 활성 시나리오 원천 78컬럼의 결측률·카디널리티 표다.
  `load_source_profile` 의 값만 써 새 조인이 없고 등급을 글자로도 적는다.
- `src/capa_simulation/components/equipment_lifecycle_gantt.py` — 호기별 생애주기 구간 Gantt 를 그리기만 한다(구간은
  `services/equipment_availability.build_equipment_lifecycle_spans`). Plotly 구간 끝이 배타적이라 끝날에 하루를 더한다.
- `src/capa_simulation/components/wip_status_dashboard.py` — 제품 행 × STEP·공정 열(`P → T`, 숫자 구간 오름차순)의
  고정 셀 Plotly 재공 격자(재공·유입·Flow 막대와 표준 가능량 기준선)를 만든다.
  - 화면은 `remembered_wip_status_grid_figure` 로 부른다 — 직전 Figure 한 벌을 세션에 두고 입력이 `DataFrame.equals`
    로 같으면 다시 쓴다. Streamlit 캐시가 아니라 캐시 경계 밖이다.
- `src/capa_simulation/components/grouped_monthly_table.py` — 환산 결과처럼 편집하지 않는 월별 표를 고정 분류 영역 +
  스크롤 월 영역 Plotly 표로 그린다. 계층 그룹·제품/양산구분 Total·전체 합계 행을 넣고 같은 구조의 CSV 프레임을
  만든다. 계산 원본은 바꾸지 않는다.
- `src/capa_simulation/components/hierarchical_monthly_table.py` — 대당 Capa·확보율·소요대수처럼 합계행 없는 월별
  결과를 같은 고정 분류 + 스크롤 월 Plotly 표로 그린다(반복값 생략·계층 경계, 숫자/퍼센트 모드, 큰 표는 페이지 단위).
  표시 모드는 원본 값을 바꾸지 않고, 화면과 같은 꼴의 CSV 프레임을 만든다.

페이지 파일은 직접 실행되는 Streamlit 스크립트 형태를 유지한다. 복잡한 계산을 페이지에
추가하지 말고 `src/capa_simulation/services/`로 옮긴다.

### 입력과 상태

- `src/capa_simulation/application_bootstrap.py` — 빈 시나리오 저장소에만 내장 시드로 첫 시나리오·공식버전을 만든다.
  - 시드 생성 뒤 발행 전에 멈췄으면 다음 시작에서 발행만 복구한다. 공식버전 없는 사용자 시나리오는 발행하지 않는다.
- `src/capa_simulation/scenario_registration.py` — BigDataQuery 원천을 리비전 1 시나리오로 저장하는 **세션 없는** 등록 길이다.
  - 화면 등록(`components/bigdataquery_registration.py`)과 자동 갱신이 같은 `save_bigdataquery_scenario` 를 불러 원천
    메타·메모가 같은 꼴로 남는다. 세션 활성화와 프리셋은 부르는 쪽 몫이다.
- `src/capa_simulation/auto_official_update_runner.py` — 공식버전 자동 갱신 한 회차를 세션 없이 돌리고 실행 기록에 남긴다.
  - 조회·시계·발행 뒤 정리는 주입받는다. 위험하면 발행하지 않고(`PUBLISH_SKIPPED` — 계산 실패·판정 가능 공정 0·발행 검사
    실패·회차 도중 최신 공식버전이 바뀜) 만든 시나리오는 남긴다. 한 번 받은 코드(`received_codes`)는 다시 받지 않는다.
  - 이어받은 수동 off 와 HOME 표지(`auto_off_marks`)는 같은 근거(`_auto_exclusions` — 조상, 복제본은 복제 전 자동
    리비전 2)를 본다. 같은 프로세스의 겹친 회차는 기다리지 않고 돌아간다(`_RUN_LOCK`).
- `src/capa_simulation/auto_update_scheduler.py` — 공식버전 자동 갱신을 매일 지정 시각에 돌리는 유일한 배경 스레드다(5장 4·9장).
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
  `CoreDataProvider` 규약이다. CSV 는 스크립트가 `read_core_data_csv` 로 읽고 화면 입구는 없다.
- `src/capa_simulation/io/company_bigdataquery_adapter.py` — 사내 SQL·컬럼 매핑 전용 접속부로, 결과를 CSV 로 남기지 않고
  공통 파이프라인에 넘긴다(`bigdataquery` 지연 import, 0행·`공정`·`모듈수` 누락은 보정 전에 막는다).
  - 조회 창은 호출자의 `QueryWindow` 이고 포함/배타 변환은 `sql_bounds()` 한 곳이다. 상세 창은 사용자가 정하며(목록에서
    고르면 등록일 −7~+3일) 넓은 기본 창으로 조용히 떨어지지 않는다. 같은 코드 재수신은 원천 코드 불변 검사가 막는다.
  - `getData` 가 낸 패키지 예외는 `call_get_data` 가 `BigDataQueryCallError`(`RuntimeError`)로 감싼다 — 패키지의 `Error`
    같은 종류는 화면의 `BOOTSTRAP_ERRORS` 밖이라 그대로 두면 목록·저장 화면이 traceback 으로 멈춘다. 감싼 예외는 갈래
    (`classify_query_failure` — 시간 초과·연결·SQL·그 밖, 사슬의 종류 이름과 문구 낱말로 가른 추정)와 다시 할 길을 말하고
    원문(300자까지)과 원래 예외(`__cause__`)를 남긴다. 사외로 가는 스크립트(`inspect_real_data_checks.py` 8-5)는 갈래와
    종류 이름(`type_names`)만 찍는다.
  - import 실패도 `load_bigdataquery_module` 이 모두 `RuntimeError` 로 올린다. 「패키지가 없습니다」는 패키지 자체가 없을
    때만이고(점검 스크립트가 이 문구로 가른다), 깔렸는데 불러오다 깨지면(DLL·numpy 판·패키지가 쓰는 모듈 없음) 「불러오지
    못했습니다」와 빠진 모듈 이름 또는 원문을 단다.
  - C-DEP CD 시작 점검 결과 파일이 있으면 「패키지가 없습니다」·로그인 토큰 오류(`is_login_token_failure`)·`user_name`
    안내 **뒤에** 그 단계의 결과 한 단락과 넣을 환경변수를 덧붙인다(첫 문장·갈래·종류 이름은 그대로, 파일이 없으면 지금
    문구 그대로). `BDQ_USER_NAME_ENV` 는 `io/container_start_report.py` 가 이름을 갖고 여기서 다시 내보낸다.
- `src/capa_simulation/io/container_start_report.py` — C-DEP CD 시작 스크립트(`scripts/container_start.py`)와 앱이 함께
  쓰는 환경변수 이름 넷(`CD_ENVIRONMENT`)·결과 파일(`settings.CONTAINER_START_REPORT_PATH` = `data/temp/container_start.json`)
  꼴·화면 안내 문장(`step_hint`)이다. 표준 라이브러리와 `settings` 만 읽는다 — 시작 스크립트가 앱 의존성보다 먼저 쓴다.
  - CD 는 시작 명령을 못 바꾸고 셸도 없어 이미지 `CMD` 가 그 스크립트다. 스크립트는 `bigdataquery` 를 하위 프로세스로
    불러 보고, 없으면 `requirements-company.txt` 의 판·인덱스로 pip 를 두 번 부른다 — 패키지 자신은 **사내 인덱스
    하나만** 보고 `--no-deps` 로(공개 미러를 추가 인덱스로 함께 보면 의존성 혼동에 열린다. 자격증명은 명령줄이 아니라
    그 pip 의 `PIP_INDEX_URL` 로, pip 설정 파일은 끈다), 의존성은 이미지 기본 인덱스로 앱 판 고정을 제약 삼아 채운다.
    토큰을 `/config/.credential/` 에 0600 으로 쓴 뒤(폴더는 이미지가 `$DSUSER` 몫으로 만들어 둔다) `os.execvpe` 로 옛
    `CMD` 와 같은 `streamlit run` 줄이 된다. 비밀값은 결과 파일·표준 출력·명령줄·하위 프로세스와 앱의 환경 어디에도
    남기지 않고(`tests/test_container_start.py`), 예상하지 못한 예외가 나도 「도중에 멈춤」 결과를 남기고 앱은 뜬다.
    시험은 `tests/conftest.py` 가 결과 파일 자리를 늘 없는 곳으로 돌리고 CD 전용 환경변수를 지운다.
- `src/capa_simulation/io/object_storage.py` — 사내 S3 호환 스토리지에 `aws` CLI 로 붙는 유일한 경계이자 앱의 유일한
  `subprocess` 자리다(명령 실행기 주입, 모든 명령에 `--profile`).
  - 설정은 `CAPA_S3_*` > `config/object_storage.json` > 상수이고, 커밋되는 `mode` 는 반드시 `local` 이다.
- `src/capa_simulation/io/bigdataquery_catalog.py` — 기간 내 코드 목록만 조회한다(상세 SQL·정규화 경로와 섞지 않는다).
- `src/capa_simulation/io/reference_cache.py` — 세션 활성 리비전의 표·공용 표시순서 경계다(5장 1, XLSB 대체 없음).
- `src/capa_simulation/persistence/` — 시뮬레이션·설비 DuckDB 의 마이그레이션·Repository·캐시를 독립된 모듈·파일로 둔다.
  - 쓰기는 프로세스 잠금 + 단일 트랜잭션, 읽기는 작업별 연결이다. `app.py` 는 rerun 한 번을 `pinned_connections` 의
    게으른 핀으로 감싼다(상시 앵커가 아니다, 9장).
  - 리비전 스냅샷은 `st.cache_resource` 에 읽기 전용 한 벌을 두고 깊은 사본(`_private_copy`)을 넘긴다. 목록은 캐시하지
    않고, 무효화는 DB 를 바꾼 호출부의 `clear_*_cache()` 다(5장).
  - 표 저장 위치는 4장·`docs/data_model.md` 다. `compare_legacy_results.py` 의 대조 기준은 리비전 1 이다.
- `src/capa_simulation/home_state.py` — HOME 토글 일곱 개의 세션 키와 불변 기본값, 세 탭의 key·라벨(`HOME_TAB_KEY`)을
  UI·저장소 import 없이 선언한다. 페이지 스크립트는 import 할 수 없어 탭 상수도 여기다(주요 Case 칩이 탭을 옮긴다).
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
  상한(`MAX_TABS` 10 — 넘는 화면은 열지 않고 탭 줄에 알림)을 순수 함수로 정한다. UI 가 없어
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
- `src/capa_simulation/scenario_state.py` — 세션별 활성 시나리오와 `revision`·`content_token` 을 관리한다(5장 3). 편집
  없는 토큰은 리비전 고정값(`pristine_content_token`)이라 세션끼리 계산 캐시를 나눈다.
- `src/capa_simulation/scenario_activation.py`, `scenario_preset_state.py` — 저장 리비전과 그 프리셋을 세션에 원자적으로
  활성화한다(새 세션은 최신 공식 리비전). 프리셋 키·기본값은 이 파일과 `persistence/models.py` 에만 선언한다.
  - 값 칸(`_STALE_VALUE_KEYS`)을 지우고 HOME 토글에 기본값을 적으므로 토글을 그리기 전에만 부른다(9장). 활성
    시나리오의 새 리비전 저장(`activate_saved_revision`)은 토글을 둔다. UPEH 가정 % 도 같은 길에서 100 을 적고 그
    공유 위젯의 주인 칸을 지운다(구간은 둔다, `tests/test_scenario_activation.py`).
  - 이름 변경은 활성화가 아니다 — `rename_active_scenario_label`·`rename_active_revision_label` 이 같은 id 일 때 이름표
    한 칸만 고친다(다른 세션은 다시 불러올 때 바뀐다).
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
- `src/capa_simulation/shared_widget_state.py` — 여러 페이지가 같은 key 로 그리는 위젯 값을 첫 회차에도 다시 알린다(9장).
- `src/capa_simulation/constraint_simulation_state.py` — 제약 시뮬레이션의 세션 키(모두 `constraint_sim_` 접두)·버튼 값·기본값
  (D8 — 제약 120% · 기준 HOME · 개조 켬 30일 · 비중대로 켬)·주소 인자 계약(`constraint_query_params`·
  `take_constraint_process_request`)과 칸 선택 그림 key 둘(`app.py` `CELL_SELECT_CHART_KEYS`)을 UI 없이 선언한다. 공정 Capa
  상세 머리 링크와 `app.py` 가 import 한다.
  - 제약 시작·끝 상자는 정수 달 선택지라 `prune_choice`(글자 선택지 전용)가 아니라 `settle_period` 가 위젯 앞에서 매 회차
    잡는다 — 칸이 없으면 기본값(그 제품의 첫 소요 달 ~ 보이는 마지막 달), 보이는 달 밖이면 가장 가까운 달을 **다를 때만**
    적는다. 엇갈림은 `on_change` 콜백 둘(`follow_period_start`·`follow_period_end`)이 다른 상자 칸을 맞춘다(승인 초안 그대로).
    범위 `st.select_slider` 는 쓰지 않는다 — 1.63 은 `value=` 없이는 범위로 서지 않아 손잡이를 움직이면 첫 달 하나로 떨어진다.
  - 시나리오를 바꿔도 조건은 남는다(`scenario_activation._STALE_UI_KEYS` 에 넣지 않는다 — 값이 아니라 가정이다). 공정·제품은
    `prune_choice`, 기간은 `settle_period` 가 맞춘다.
- `src/capa_simulation/upeh_assumption_state.py` — UPEH 가정 세 칸(%·적용 시작·끝)의 세션 키와 기본값. UI 를 import 하지
  않아 시나리오 전환 초기화(`scenario_activation`)가 읽는다.
- `src/capa_simulation/sync_boot.py` — managed 모드일 때만 `sync_state` 에 두 DB 경로를 등록한다(설정을 못 읽으면 조용히 끈다).
- `src/capa_simulation/performance.py` — HOME 단계별 소요시간을 잰다. 업무 데이터는 기록하지 않는다.
- `src/capa_simulation/services/simulation_cache.py` — 계산 함수의 content-addressed Streamlit 캐시 래퍼를 모은 경계다
  (5장 4·「키 방침」). 큰 프레임은 `_` 인자 + 내용 지문(`frame_digest`)으로 받는다.
  - 대당 Capa·소요대수는 전체 기간으로 한 번 계산해 자르고(`get_full_capacity_outcome` → `slice_capacity_months`,
    `tests/test_full_period_capacity.py`) 오류도 `CapacityOutcome` 으로 캐시한다. 배경 회차는 순수 코어
    `full_capacity_outcome` 을 부른다.
  - HOME Figure 는 묶음별 공용 LRU(`shared_home_figure_store`)에 pickle 바이트로 둔다(복원 `components/home_rendering.py`,
    `tests/test_home_figure_cache.py`). 「소요대수만」 돌려주는 래퍼는 두지 않는다.
  - 필요 단축 일정 계획 키 끝 칸은 UPEH 가정 토큰이다. 공식 칸과 가정 칸(`ASSUMED_PLAN_MAX_ENTRIES`)은 따로이고 서로의
    키를 받지 않으며, 계획은 키와 한 묶음(`KeyedShorteningPlan`)으로만 CSV·진척 캐시에 간다(5장 31,
    `tests/test_upeh_assumption_cache.py`).

### 계산 서비스

- `src/capa_simulation/services/load_calculator.py` — 계획·수율 편집 변환과 PKG·Chip·Wafer·Density 부하량을 낸다.
- `src/capa_simulation/services/unit_capacity.py` — Main/MI 환산 UPEH 와 경로별 대당 Capa 를 계산한다(6장).
- `src/capa_simulation/services/weighted_unit_capacity.py` — 원수요 부하량 ÷ STEP별 소요대수 합으로 공정별 대당 Capa 를
  만든다. 소요기준이 둘인 공정은 멈춘다.
- `src/capa_simulation/services/standard_target_capacity.py` — 주차별 일 표준 가능량과 PKG 기준 역산을 낸다. 표준 목표
  전용 제외(ER·`Pre B/D` DUMMY)는 `split_standard_target_required_equipment` 한 번으로 낸다. 두 계산 함수는 기본으로
  분리를 함께 하고, 이미 분리한 프레임(분리 결과 캐시 `get_standard_target_split` 와 그 행을 거른 것)은 `already_split=True`
  로 받아 다시 훑지 않는다 — `simulation_cache` 의 네 표준 목표 래퍼만 쓴다. 분리 안 한 프레임에 켜면 ER·DUMMY 가 섞인다.
- `src/capa_simulation/services/route_step_editor.py` — 네 경로 표의 MCP·STEP 일괄 복제·삭제와 고유 조합 수를 맡는다.
  요약·선택지를 함께 낼 때는 `route_step_tables` 로 `RQ_REQB` 를 한 번만 전처리한다.
- `src/capa_simulation/services/process_rename.py` — 공용 공정 표시명의 정규화·검증·직렬화다(치환은
  `components/process_labels.py` 에만, 8장).
- `src/capa_simulation/services/required_equipment.py` — `RQ_REQB` 경로 연결·소요대수와 제외 셈을 낸다(6장).
- `src/capa_simulation/services/securement_rate.py` — 확보율·추가 필요대수·부호 있는 과부족(`securement_balance`)을 낸다.
- `src/capa_simulation/services/process_capa_detail.py` — 공정 하나의 월별 요약·제품별 소요·경로 추적을 계산 결과에서 꺼낸다.
  - 새 계산이 없다. 대당 Capa 식을 바꾸면 `route_factor_product` 도 고친다(`tests/test_process_capa_detail.py`).
- `src/capa_simulation/services/constraint_simulation.py` — 제약 시뮬레이션(2026-10-24 결정, 저장하지 않는 미래 가정)의
  순수 계산. 공정 하나의 월별 소요(R)를 제약 제품(`제품정보` 하나)과 기존 제품으로 나누고, 설비 일정 기준 가용(단축 전
  환산 대수)에서 개조 비가동을 빼고 제약 몫을 먼저 정수로 뗀 뒤 기존 제품 확보율·「소요 비중대로」 견주기·요약 넷을 낸다
  (`simulate_constraint`). Streamlit·세션·캐시·DB 를 모르고, pandas 는 어댑터 `constraint_month_inputs`(필요 단축 일정
  계획의 공정 x 월 표 + `build_process_product_demand(split="제품정보")` 표 → 달마다 입력, 합이 R 과 어긋나거나 제약
  제품이 빈 이름이면 `ValueError`·계획에 공정이 없으면 `KeyError`) 하나만 쓴다. 빈 이름을 막는 까닭은 표가 빈 `제품정보` 를
  「그 밖」 이 아닌 한 묶음 행으로 두기 때문이다(제품 선택지도 빈 이름을 뺀다). 식은 6장 「제약 시뮬레이션」.
  - 기준 판정은 `secure()` → `capacity_status` 한 길(허용치 없음), 제약 충족은 `allocated >= need` 정수 비교다 — 이 모듈에
    기준·제약 확보율을 비율과 직접 견주는 식이 없는지 `tests/test_constraint_simulation.py` 가 AST 로 본다.
- `src/capa_simulation/services/securement_threshold.py` — 공용 판정 기준(기본 + 월별 예외)의 정규화·검증, 달별 실효 기준
  (`SecurementThresholds`)과 판정 부등호 `capacity_status`(기준 **이상**이면 확보)의 한 곳이다(6장).
- `src/capa_simulation/services/threshold_label.py` — 판정 기준을 사사오입 정수 퍼센트 글자로 바꾸는 한 곳이다(8장).
- `src/capa_simulation/services/equipment_count.py` — 보유·대여·가용 설비대수 월별 표다. 편집표 빈칸은 0 대로 받되(이 세
  표만) 원천 변환에서 미리 채우지 않는다 — 「미입력」과 「확인된 0 대」를 가른다.
- `src/capa_simulation/services/equipment_availability.py` — 주차별 총·가용·비가동대수, 호기 생애주기 구간, 비가동 호기,
  Space 단계·전환 이벤트를 낸다(검증은 `equipment_validation.py`, 샘플은 `equipment_samples.py`).
  - 상태 판정(`_build_equipment_status_from_prepared`)이 `집계분류`·`가용대수반영`·도면 칸을 붙인다 — 세는 자리는 그
    칸을, 이름을 보는 자리는 `상태` 를 본다(6장). 이탈일 규칙은 `tests/test_stop_and_exit_dates.py` 가 박아 둔다.
  - 판정은 시점 하나 또는 행마다의 시점(`as_of` Series)을 받는다. 생애주기 구간은 조회 시작일의 전 호기와, 그 뒤
    바뀔 수 있는 날마다 그날 일정·비가동 경계가 걸린 설비키 묶음만 쌓아 한 번 부른다(날마다 전 호기를 다시 판정하지
    않는다). 판정 줄을 고치면 두 길이 같은지 `tests/test_equipment_lifecycle_stacked.py` 가 본다.
- `src/capa_simulation/services/equipment_csv.py` — 설비 세 표의 CSV 양식·내보내기·붙여넣기 검증과 자연키 병합을 맡는다.
  - 내보낸 파일을 그대로 되붙여도 통과해야 한다(읽는 쪽 `*_COLUMNS` 와 같은 이름·차례, `reference_csv.guard_excel_text`).
  - 일부 열 붙여넣기(`read_equipment_update`)는 붙여넣은 열만 바꾸고(빈 칸 = 지움) 겹친 머리글을 막는다. 모르는
    머리글은 39열이 다 있거나 옛 36열·옛 38열(`시나리오 메모` 만 없음) 꼴일 때만 알림과 함께 넘기고 그 밖에는 막는다.
- `src/capa_simulation/services/dashboard.py` — HOME 월별 집계와 B/N 월별 순위(Top 1·Top 5·상세)·Wafer Capa 를 낸다.
  - 월 축은 양산 Density 가 있는 달이다 — 양산 없이 ER 만 있는 달은 Wafer 계획·Wafer Capa·B/N·Top5·연간 Total 에서
    빠진다. 그대로 두고 사내 런북 8-9 가 그런 달 수를 잰다(2026-10-22 결정 A). 넓힐 때는 이 파일의 조인 넷과
    `home.py` 축·`home_lob_figures` 위치 조회를 함께 바꾼다 — 조인만 바꾸면 B/N 그림이 `KeyError` 로 멈춘다.
- `src/capa_simulation/services/dynamic_capacity.py` — 실적을 차례로 얹는 Dynamic Capa 손실 분석과 데모(`DemoProfile`)다.
- `src/capa_simulation/services/wip_status.py` — 재공 DB 연결 계약·STEP 코드 정렬·제품별 표준 가능량 일 전개와 샘플을 낸다.
- `src/capa_simulation/services/display_order_scopes.py` — 표시순서 규칙이 걸리는 페이지·탭 구분자를 한 곳에 선언한다.
  - `LEGACY_SCOPE_RENAMES` 는 `0027_display_order_scope_rename.sql`·`config/bootstrap_display_order.json` 과 같은
    대응이어야 한다(`tests/test_display_order_scopes.py`).
- `src/capa_simulation/services/display_order.py` — `RQ_DISPLAY_ORDER` 기반 행 정렬이다. `prepare_display_order` 가 회차에
  한 번 검증해 `PreparedDisplayOrder` 를 만든다. 캐시는 두지 않는다(`simulation_cache.get_prepared_display_order`).
- `src/capa_simulation/services/month_filter.py` — YYYYMM 검증과 조회기간 필터다(원천·적재·계산이 같은 달력 검증을 쓴다).
- `src/capa_simulation/services/capacity_reference_editor.py` — Capa 기준정보 Long/Wide 편집 변환이다. 빈 칸은 「행 없음」이다.
  - 편집표 한 장(`build_reference_edit_table`)은 순수 조합이고 캐시는 `simulation_cache.get_reference_edit_table` 이
    건다(`tests/test_reference_data_page.py` 가 표시순서 교체를 본다).
- `src/capa_simulation/services/clipboard_table.py`, `reference_csv.py` — Excel 복사 TSV 파싱과 RQ Wide 표 검증이다.
  - 빈 열은 `drop_empty_unnamed_columns` 가 빼고, 못 읽는 값·범위 밖 값(`assert_edit_value_range`)은 막고 빈 칸은 센다.
- `src/capa_simulation/services/reference_consistency.py` — 기준정보 편집이 다른 표의 행을 빠뜨렸는지 저장 전에 가린다
  (`validate_upeh_edit`·`validate_required_edit`). 줄이는 규칙은 `unit_capacity._join_reference` 와 같아야 한다.
- `src/capa_simulation/services/reference_transformer.py` — XLSB `Q_Core_Data` 와 15개 Core 파생 Power Query 를 pandas 로
  대체하고 값 충돌 보고서를 함께 낸다(수동 `RQ_DISPLAY_ORDER` 는 `display_order_editor.transform_display_order`).
  - 경로 중복 접기·빈 대여 = 0 보정 때문에 `RQ_REQB`·`RQ_EQP_LENT`·`RQ_EQP_AVBL` 은 Power Query 와 일부러 다를 수
    있다 — `scripts/validate_duckdb_persistence.py` 는 같은 보정을 건 뒤 견준다.
- `src/capa_simulation/services/core_data_pipeline.py` — CSV·BigDataQuery 결과를 같은 정규화·RQ 변환 길로 잇는다.
- `src/capa_simulation/services/object_storage_manifest.py` — 원격 스냅샷의 키 계약과 pull·push 판정을 담는 순수 계층이다.
  - 가변 포인터(`current.json`) 없이 불변 키 시퀀스로 둔다. `scripts/sync_object_storage.py` 는 판정과 IO 를 잇기만 한다.
- `src/capa_simulation/services/bigdataquery_catalog_view.py` — 코드 목록을 표시·검색용으로 정리하고 등록 폼 기본값을
  만드는 순수 계층이다(Streamlit import 없음). 코드·PLAN 당 한 행만 남긴다.
- `src/capa_simulation/services/auto_official_update.py` — 공식버전 자동 갱신의 규칙(주차·후보·판정·설정·예약·표지)을
  정하는 순수 함수다(차례·기록은 `auto_official_update_runner.py`).
  - 후보(`select_candidate`)는 키워드가 맞고 주차(`W##`)가 더 크거나 같은 주차에서 더 늦게 생긴 코드다(생긴 시각 = 가장
    이른 원천 등록시각). 판정은 공정별 최저 원 확보율이 기준 **미만**이면 off 다(`falls_below_threshold`).
- `src/capa_simulation/services/core_data_derivation.py` — 원천 78컬럼에서 RQ 파생용 정규화 작업 프레임을 만든다.
  - CS → 양산구분은 `CS_PRODUCTION_CLASSES` 한 곳이고 규칙 밖 코드는 등록을 막는다(7장). `WF 구분` 의 표기 차이는 등록에서
    한 표기로 맞추고(`unify_case_variants`) 계산 쪽 조인은 대소문자 무시로 바꾸지 않는다.
- `src/capa_simulation/services/reference_conflicts.py` — 같은 업무 키의 값 충돌을 모아 보고서를 만들고 형제 행을 접는다.
  - 승자는 **값이 있는 첫 행**이다(숫자 `0`·빈 글자는 값 없음). 값을 지어내지 않고 행 순서를 바꾸지 않는다.
- `src/capa_simulation/components/monthly_table_base.py` — Plotly 월별 표가 공유하는 색·치수·글자 계산이다. 분류 칸 글자는
  반드시 `classification_cell_text()` 를 거친다(8장).
- `src/capa_simulation/services/frame_contracts.py` — 서비스 공용 필수 컬럼 검증·업무 키 정규화의 단일 정의다(14-5).
  정확 일치 검사는 `require_exact_columns` 하나다(`tests/test_exact_column_contracts.py`).
- `src/capa_simulation/services/frame_checks.py` — 중복 키 검사(`assert_unique_keys`)·텍스트 키 strip 의 단일 정의다.
  다음 주기에 `frame_contracts.py` 로 합칠 임시 자리라 새 검증을 더 쌓지 않는다.
- `src/capa_simulation/services/virtual_product.py` — 기준정보를 새 제품 키로 복제해 가상 제품을 만든다(8표, 계획 수량 0).
- `src/capa_simulation/services/iso_week_calendar.py` — ISO 주차 캘린더와 `YY-W##` 주차 코드 파싱을 제공한다.
- `src/capa_simulation/services/korean_particle.py` — 값 뒤 조사(을/를·은/는·이/가·으로/로)를 끝소리로 고르는 단일
  정의다(8장 — `tests/test_particle_sites.py` 가 지킨다). 패키지를 import 하지 않는 `scripts/apply_deploy_package.py` 는 고정
  명사를 사이에 둔다.
- `src/capa_simulation/services/weekly_availability_input.py` — 표준 목표 수동 가용대수 입력 표 계약이다(설비 Repository 도
  쓴다). 붙여넣기에서만 빈칸을 「그대로 둠」으로 떨어뜨리고, 보유 공정 밖 이름은 `known_processes` 로 거절한다.
- `src/capa_simulation/services/standard_target_logic.py` — 공정·주차 하나의 표준 목표를 제품·WF Mix 로 분해한다.
  소요대수는 숫자 월로 먼저 거른 뒤 공정명·소요기준을 다듬는다(고르는 행은 같고 글자 처리가 그 달 행에만 걸린다).
- `src/capa_simulation/services/equipment_contract.py` — 설비 세 입력의 컬럼 계약·허용값·상태 이름 상수를 정의한다(7장).
  - 기존 보유대수 자연키는 `BASELINE_KEY_COLUMNS`(공정, 분류)다. 옛 머리 이름은 입구에서 바꿔 읽고(`rename_legacy_headers`)
    빠진 컬럼(`OBSOLETE_EQUIPMENT_COLUMNS`)은 알림만 남긴다. 선택 컬럼은 없어도 된다 — 설비 마스터 입구
    (`read_equipment_update`)에서 새 호기는 빈 칸, 기존 호기는 저장값을 지킨다.
  - 사용기준 규칙(`COUNTED_USAGE_BASIS`·`counts_for_capacity`)과 모듈 일치 컬럼(`UNIT_CONSISTENT_COLUMNS`)의 단일
    선언이다. 한글↔DB 칸 매핑은 공통 칸이 `equipment_repository.EQUIPMENT_MASTER_DB_COLUMNS`, 시나리오 일곱 칸이
    `equipment_scenario_store.SCENARIO_SCHEDULE_DB_COLUMNS` 다(저장소가 그 모듈을 부르므로 그쪽에 둔다).
  - 설비 마스터 39칸은 **공통 32**(`COMMON_MASTER_COLUMNS`)와 **시나리오 7**(`SCENARIO_SCHEDULE_COLUMNS` — 날짜 여섯 +
    `시나리오 메모`)로 갈린다. `시나리오 메모` 는 `반출/이설일정` 다음 칸이고 선택 칸이다(`OPTIONAL_EQUIPMENT_COLUMNS` —
    옛 38칸 CSV·붙여넣기가 막히지 않는다). 화면 프레임에는 호기 키 칸을 두지 않는다(스냅샷이 따로 든다).
  - `환산비` 는 기준 모델 한 대 대비 몫(능력 축)이고 월별 환산대수·확보율 교차검증만 곱한다.
- `src/capa_simulation/services/equipment_scenario.py` — 설비 마스터를 공통 대장과 시나리오 일정으로 나누고 합치는 순수
  규칙(Streamlit·DB 를 모른다). 저장소와 `scripts/inspect_real_data_checks.py` 가 같은 합치기를 쓴다.
  - 호기 키: 옛 행은 `legacy_unit_key(설비명)` = `"n" + md5(설비명)`(SQL `'n' || md5(equipment_id)` 와 같아야 한다), 새 호기는
    uuid. `assign_unit_keys` 는 이름 지도(지금 → 저장본)로 이어받은 키가 먼저 차지하고 남은 호기는 같은 이름의 저장본 키를,
    그 밖은 새 키를 받는다 — 「A→B 이름 바꿈 + 새 A」 의 새 A 는 새 키, 결과 키가 겹치면 `ValueError` 다. 앞의 두 규칙(어느
    편집본 행이 어느 저장본 호기를 잇는가)은 `inherited_unit_names` 하나이고, 설비 마스터 탭 배치 칸 잠금(잠긴 회차)·「배치
    변경만 버리기」·배치 편집 판정(`layout_edits`)도 그것으로 「있던 호기」 를 고른다 — 둘이 갈리면 잠금이 새 호기로 본 행이
    저장에서 있던 호기의 칸을 고친다.
  - 합치기는 공통 행 차례대로 키로 왼쪽 결합(`one_to_one`)이고, 일정 행이 없는 호기는 일정 칸이 비고 **일정 없음**
    (`unscheduled_units`)에 든다. 공통에 없는 키의 일정·비가동은 버리고 `orphan_rows` 로 센다. 계산 프레임은 일정 없음 호기와
    그 비가동을 뺀다(`calculation_frames` — G2 결정의 한 곳, 기존설비·보관 Y 도 뺀다).
  - 되돌리기 확인 재료(`schedule_restore_preview` → `ScheduleRestorePreview`, E7): 같은 공통 대장과 합친 두 한 벌(지금 최신·
    고른 리비전)을 호기마다 견준다 — 일정 일곱 칸과 일정 행 있음/없음, 비가동 다섯 칸 묶음(차례와 무관). 바뀌는 호기 수·비가동
    행 수·되돌린 뒤 일정 없음·새로 일정 없음이 되는 호기·「그 리비전 뒤에 공통 대장에 든 호기」(그 리비전이 함께 본 공통에 키가
    없는 호기)를 낸다. 가정 배치(설비 0031)는 **불변 값만** 더한다 — 고른·지금 최신 리비전의 저장된 배치 차이 행 수·지문(빈
    차이는 None)·「그때와 자리가 다른 손대지 않은 호기 수」(`layout_moved_since`). 일정이 같고 배치 지문도 같아야 `identical` —
    되돌려도 리비전을 만들지 않는다(층 현행값 기준 정규화·공식 시나리오라 차이를 버림은 캐시 밖 쓰기 길이 본다).
  - 함께 넣기 후보: 새 호기 = 저장본 공통에 없던 키(`new_unit_keys`). 넣을 새 호기는 저장 요청이 새 호기마다 고른 이름
    (`EquipmentSaveRequest.propagate_units` — 설비 마스터 「새 호기」 칸, 개편 D8)이 있으면 그 이름의 새 호기만, 없으면
    `propagate_new_units` 하나로 모두 또는 아무것도다(`_propagated_unit_keys`). 새 비가동(`new_downtime_rows`)은 같은 (키, 유형)
    묶음에 저장본에 없던 시작일이 생겼고 그 묶음에서 사라진 행이 없을 때만이다 — 같은 (키, 시작일) 행이 다른 유형으로
    사라졌어도 고침으로 본다(시작일·유형만 고친 비가동은 퍼지지 않는다). 쓸 일정 행은 「저장본에 일정 행이 있던 호기 ∪
    일곱 칸에 값이 있는 호기 ∪ 비가동이 있는 호기 ∪ 새 호기」 다(`select_schedule_rows`).
- `src/capa_simulation/services/equipment_units.py` — 모듈 행을 설비 한 대로 묶는 `설비키`·`설비지분`과 소수 대수 표기의
  단일 정의다. 대수를 세는 곳은 행 수 대신 지분을 더한다. 모듈 묶음 환산비 경고는 줄 판정(`module_ratio_warning_rows`)과
  문장(`module_group_warnings`)이 같은 판정·같은 문구 조각(`MODULE_RATIO_WARNING`)이다 — 검증 전 편집본도 받고, Main 설비를
  적은 줄만 묶음으로 센다(설비명이 겹친 줄·설비명이 빈 줄은 묶음이 아니다). 화면 경고는 줄 판정 쪽(규칙 표 `module_ratio_default`
  → 설비 마스터 표 칸 경고 표지)이다 — 문장 쪽은 개편 D 뒤 운영 호출자가 없고 시험만 부른다(TODO 2장 「다음 손볼 때」).
- `src/capa_simulation/services/undated_equipment.py` — 반입·Qual 일정이 비어 가용대수에 들지 못하는 신규 설비를 지분으로
  세고 「일정 미정 N대」 한 줄을 만든다(화면은 `simulation_cache.get_undated_equipment`).
- `src/capa_simulation/services/schedule_confirmation.py` — 일정·실적·상태로 미확인·실적 누락·상태 갱신 필요를 고른다.
  - 오늘에 따라 답이 바뀌므로 검증(`prepare_*`)에 넣지 않고 저장도 막지 않는다(7장). 화면은
    `simulation_cache.get_schedule_confirmation_issues`(마스터 지문 + 오늘)로 읽는다.
- `src/capa_simulation/services/space_unit_state.py` — Space 호기 경계 날짜(`unit_boundaries`)·기준일 판정의 한 곳이다.
  - 실적은 여기서만 쓴다(6장). 편집기 JS 가 같은 판정을 하므로 `tests/test_space_unit_state.py` 가 둘을 대조한다.
- `src/capa_simulation/services/space_color_basis.py` — Space 「색 기준」 그룹(공정구분·투자Capa·필요 단축 — 셋째 값은 그룹이
  없다)을 정한다. 색 값은 모른다.
- `src/capa_simulation/services/space_shortening_layer.py` — Space 「필요 단축」 보기의 순수 규칙 — 계획의 단축 호기를 구간
  (1–7일·8–14일·15일 이상·기한 지남)·D-n·임박(필요 단축 일정 「기한 임박」 날수)으로 나누고, 층 행의 「설비키」 로 붙여 배지(설비키마다
  하나)·흐림·「이 층에서 단축할 호기」·자리 없는 호기·추가N(그 공정 호기가 그려진 사용 층마다, FAB 합계 한 번)·층 대수·FAB
  요약을 낸다. 「도면에서 보기」 층(`shortening_space_floors` — 공정 전부 한 번, 단축 호기 다수 사용 층 → 추가N 만이면 그려지는
  설비키 다수 사용 층, 비활성 층은 대상 아님)도 여기다. Streamlit·DB·색·공정 표시명을 모른다.
- `src/capa_simulation/services/usage_basis.py` — 사용기준이 HBM·EDP 가 아니어서 일정 기준 가용대수에 세지 않는 설비를
  고정 지분으로 세고 알림 한 줄을 만든다(`simulation_cache.get_usage_excluded_equipment`).
- `src/capa_simulation/services/equipment_bulk_delete.py` — 일괄 삭제·되돌리기를 업무 키로 한다(9장, 비가동 일정도 뺀다).
- `src/capa_simulation/services/equipment_validation.py` — 설비 세 입력의 정규화·검증(`prepare_*`)이다(조이지 않는다, 7장).
  - 설비 마스터는 **규칙 표 하나**(`MASTER_RULES` — 코드·찾는 함수·막음/경고)를 셋이 함께 본다. `prepare_equipment_master` 는
    차례대로 처음 걸린 규칙 하나를 예전 문구·예외 형으로 던지고, `equipment_master_issues` 는 같은 인자로 끝까지 보며 칸마다
    `MasterIssue`(줄 자리 `iloc`·설비명·대표 칸·규칙·칸 문구 = 거부 문구 앞머리·막음)를 낸다(못 읽은 값은 결측으로 보고 이어 봄).
    결과 차례는 규칙 표 → (칸 여럿을 따로 보는 규칙은) 칸 → 줄이고, 막는 결과가 있다 ⇔ 저장이 막힌다(처음 막는 결과가 던질
    규칙·칸). 경고 셋 — Area Code 목록 밖·대소문자만 다른 설비명·모듈 묶음 환산비 모두 1 — 도 표의 줄이고 막는 결과가 있어도 낸다.
    문장 경고와 줄 판정을 나눈다(`area_code_warnings` ↔ `area_code_warning_rows`, `module_group_warnings` ↔
    `module_ratio_warning_rows`) — 화면은 줄 판정을 규칙 표 결과(표 칸 경고 표지)로 쓰고, 문장 둘은 옛 폼이 걷힌 뒤 운영
    호출자가 없다(시험만 — TODO 2장). 대소문자는 붙여넣기 미리보기(새 이름 ↔ 편집본 이름)가 표 안 짝의 일부이고 열쇠가 같다.
    `coerce_master_cell` 은 칸 하나를 저장 정규화와 같은 함수(`_read_master_dates`·`_read_number`·`_read_ratio`·Y/N·Area Code·
    글·동층/상태 허용값)로 다듬고 못 맞추면 그 규칙 문구의 `CellParseError` 를 준다. 시간대가 붙은 날짜는 세 쓰임 모두 못 읽은
    날짜다(계약 칸은 시간대 없는 날짜 — 시간대를 떼고 받지 않는다). 비가동 일정 날짜(`_normalize_date`)도 같은 길로 읽어
    시간대가 섞인 붙여넣기가 pandas 예외 대신 그 값을 든 날짜 문구로 막힌다. 표 차례가 저장 거부 문구의 계약이고, 시험이 규칙마다 거부
    문구를 글자 그대로(예시·다섯 개 제한까지) 고정한다(`tests/test_equipment_validation_issues.py`).
  - 신규 호기의 반입·Qual 은 비워도 되고 순서는 있는 날짜끼리 본다. 정지 ≤ 반출/이설이고, 실적 검사는 저장할 때만
    `today=` 로 돈다. 환산비·좌표·크기는 빈 칸과 못 읽는 값을 가른다(`_read_number`·`_read_ratio`).
  - Space 위치: 레이아웃표시는 도면 대상인지만 가르고 좌표를 강제하지 않는다(없으면 미배치 트레이). X·Y·크기는 짝으로 둔다.
  - Main 설비는 다른 행의 설비명과 같을 수 없다(`UnitGroupCollisionError`, 문구는 `unit_group_collision_message` 한 곳).
- `src/capa_simulation/services/equipment_grid.py` — 가용설비 현황 「설비 마스터」 탭 표(개편 B1 — 표 컴포넌트는 아래
  화면 공통 계층)의 streamlit 을 모르는 부분. 탭 본문은 `components/equipment_master_tab.py` 다(B1-c).
  - 칸 정의 `GRID_COLUMNS`(계약 39칸 차례 — 브라우저로 가는 자리 번호는 모두 이 차례)·칸 묶음 `COLUMN_SETS`(기본·일정·위치·
    이력·메모·「전체 39칸」 = 엑셀 양식 차례)·상세 묶음 `DETAIL_GROUPS`(39칸이 한 번씩)·잠금 갈래 `LOCK_SETS`(모듈 묶음 좌표·크기 /
    배치 편집이 잠긴 회차의 있던 호기 배치 일곱 칸 `layout` · 새 호기 자리 넷 `place`(동·층·X좌표·Y좌표) / 낡은 세션의 시나리오 일곱
    칸, 지운 표시 줄은 모든 칸)와 칸 머리 도움말 `scenario_column_help`(공통·상태·배치 `LAYOUT_COLUMN_HELP`·시나리오)가 한
    곳이다. 칸 저장 갈래 `scope` 는 공통·배치(`layout` — 배치 일곱 칸, 설비 시나리오 2단계 S3)·시나리오·
    상태 넷이고 표 머리·상세 묶음(「위치」 는 배치)·값 넣기 칸·변경 줄·범례(공식이면 「공식 배치에 저장」, 가정이면 「그 시나리오에만
    저장(공식과 다른 것만)」)가 같은 꼬리표다.
  - **배치 편집이 잠긴 회차**(`GridContext.layout_lock` — 설비 시나리오 2단계 S3, 화면 쪽이 `space_edit_mode(...).layout ==
    "locked"` 일 때 `master_tab_lock_reason` 을 넘긴다)는 있던 호기 배치 일곱 칸·새 호기 자리 넷을 잠그고, 이름·Main 설비·배치·행을
    바꾼 op 뒤마다 `locked_layout`(작업 공간 `layout_edits(...).apply` 와 같은 판정 — `layout_overlay.assumption_common_places`,
    시험이 대조한다)으로 맞춘다: 있는 묶음에 드는 새 호기와 동·층 미정 호기는 그 묶음의 동·층에 X·Y 비움. 맞춘 칸은 그 op 의
    되돌리기 단계에 든다. 공식(`"official"`)·가정(`"overlay"`) 편집이면 `layout_lock` 은 None 이고 배치 칸은 잠기지 않는다 — 가정
    세션의 배치 칸 고침은 그 시나리오의 배치 차이로 저장된다. 화면 쪽(B1-c)은 op 를 얹은 뒤 `layout_edits` 가 비지 않으면 그때의
    역할을 찍는다(`stamp_layout_role` — 탭 제출과 같다).
  - 행 id 는 `s:` + 저장본 설비명(이름을 바꿔도 그대로)·`n:` + 지금 이름(새 호기)이고 짝은 저장의 호기 키 규칙
    `inherited_unit_names` 그대로다(`grid_index`). 같은 이름 둘째 줄 꼬리는 설비명에 나올 수 없는 글자(`DUPLICATE_MARK`)로 붙이고
    겹치면 번호를 올린다. 저장본 호기인지는 **id 글자를 풀지 않고** `GridIndex.saved`·`saved_name`·`is_new` 로 가른다(설비명 규칙은
    「~」 를 받는다). 칸 글자 `cell_text` 가 화면 글자이자 「바뀐 칸」 견줌 글자다.
  - `build_grid_view` 한 번에서 세 마운트 data(`grid_data`·`loader_data`·`detail_data`·`changes_data`)가 나온다 — 같은 입력이면
    같은 dict. 칸 초안이 있는 칸에는 편집본 옛 값의 규칙 결과를 싣지 않는다(초안 오류 하나). 출납을 보내는 마운트(표·오른쪽 칸 둘)
    는 저마다 제 `ack` 와 그 마운트가 보낸 조작의 토스트를 싣는다 — 화면 쪽은 토스트를 그 op 를 보낸 마운트에 싣는다(예외 하나:
    「호기 추가」 가 넣은 회차는 그 호기를 「호기 상세」 로 열므로 토스트·「되돌리기」 도 상세 칸에 — `GridApplied.added`). 토스트 dict 의
    `undo` 는 단계 표지(`GridApplied.toast_step`)이고 `toast_payload` 가 그 단계가 되돌리기 목록 맨 위(`undo_top`)일 때만 남긴다.
    `grid_data(open_id=)` 는 상세에 연 줄의 띠다. 불러오기 data 의 조건 칸(옛 표 보기 거르기 13칸, 사용자 R1)은 칸마다 값 번호를
    64자 고정 폭 글자로 잇는다(`encode_codes` ↔ JS `decodeCodes` — 브라우저는 고른 값을 번호가 아니라 글로 기억한다).
  - 출납: `pending_ops` 가 두 마운트의 상태 값 `outbox` 에서 반영 안 된 op 만 `(at, mount, seq)` 로 고르고, `apply_ops` 가 차례로
    얹는다 — `base` 가 다르면 버림, 잠긴 칸·지운 줄·낡은 세션의 저장본 호기 지우기는 파이썬도 막음, 칸 값은
    `coerce_master_cell`(저장 정규화와 같은 함수)로 다듬고 못 다듬은 글은 칸 초안(`overlay` — 편집본 밖)에 둔다. 설비명 칸
    확정은 이름 바꿈(`check_unit_rename`·`apply_name_changes`·`compose_unit_renames` — Space 와 같은 넷, 사용자 R2·G4)이다.
    지우기는 비가동을 함께 빼고, 되살리기는 **저장본 값**을 **저장본 차례** 자리에 넣는다(차례만 다른 공통 리비전을 만들지 않음).
    칸·호기 되돌리기(`revert`)는 저장본 쪽으로 가는 길이라 낡은 세션의 시나리오 칸·가정 배치 칸 잠금을 보지 않는다(낡기 전에 고친
    일정을 되돌려야 저장이 거부되지 않는다) — 모듈 묶음 좌표·크기만 그대로 두고 토스트로 알린다. `base` 가 달라 버린 op 는 까닭을
    가르지 않는 토스트(`DROPPED_TOAST` — 내 저장·모두 버리기·불러오기·남의 저장)로 센다.
  - 되돌리기 `UndoStep` 은 역 patch(조작 뒤 자리)라 나중 것부터만 맞는다 — 표의 조작만 쌓고 다른 길이 편집본을 바꾸면
    목록을 비운다(B1-c). 단계마다 표지 `token`(그 op 의 `mount#seq`)이 있고 `undo` op 의 `step` 이 맨 위가 아니면 되돌리지 않고
    알린다(토스트 「되돌리기」 뒤에 토스트 없는 칸 고침이 쌓인 경합). 불러온 목록은 화면 조작으로도 바뀌므로 사진으로 되돌리지 않고
    옮긴 id(`moved` — 새 호기 이름 바꿈, 칸 초안 열쇠 옮김도 역 patch)·뺀 자리(`unloaded`)로 되돌린다(통째 단계만 사진). 이름 바꿈을
    되돌리면 `renamed`·`moved` 를 거꾸로 알린다. 이름을 바꾸면 행 조각을 든 단계와 그 앞 단계를 버린다(`after_row_steps`). 통째
    단계는 하나다. 세션에는 `undo_to_state` 의 기본형으로 둔다.
  - **새 호기**(개편 단계 C — 오른쪽 「새 호기」 칸): `new_unit_check(초안 39칸 글, frames, saved_master, renames, context)` 한
    판정이 체크 상자 셋(「에러 없이 추가하려면」 설비명·공정소분류 + 필수 Y/N 셋 — 빈 초안 `blank_draft` 가 보관 N·기존설비 N·
    레이아웃표시 Y 로 채운다 — 과 **다른 칸 값 때문에 막는 칸**: Qual일정이 있는 신규 호기의 Qual상태(찼어도 그 줄에 남음)와 비어서
    막는 오류가 걸린 칸(좌표가 있는데 빈 크기 등, 잠긴 칸 빼고). 막대가 다 찼는데 「호기 추가」 가 막히지 않게 — 사용자 요구 「에러
    없이 추가하는 최소 칸」 / 「가용대수에 세려면」 반입·Qual 일정·사용기준 HBM·EDP(`counts_for_capacity` — D13) / 「도면에
    놓으려면」 동·층, 레이아웃표시 N 이면 없음)·칸 오류·잠금·「호기 추가」 막힘을 낸다. 칸 data 의 `required` 는 늘 필수인 칸(설비명·
    공정소분류·Y/N 셋)만이다(브라우저가 「호기 추가」 를 켜고 누를 때 만진 표지를 줌). 칸 오류는 칸
    다듬기(`coerce_master_cell`) + 설비명 규칙 `space_layout_edit.check_new_unit_name`(Space 새 호기와 같은 규칙 — 대소문자만 다른
    이름·Main 설비 이름·지운 채 저장 안 한 이름 막음, D12) + **저장 규칙 표**(`equipment_master_issues` — 저장과 같은 인자
    `GridContext.floor_canvases`·`today`)를 편집본의 관련 행(설비명·Main 설비가 초안의 설비명·Main 설비와 같은 행 —
    `_related_rows`)과 초안 한 줄에 돌린 결과 가운데 초안 줄의 것이다(설비명이 비거나 걸리면 자리 이름으로 돌린다 — 빈 이름 줄은 저장
    정규화가 조용히 뺀다). 잠금은 낡은 세션 통째(`new_rows_locked`), 배치 잠금 회차의 자리 넷(묶음에 드는 모듈은 그 묶음 동·층),
    있는 모듈 묶음에 드는 초안의 좌표·크기 넷(D9)이다. 「호기 추가」 는 출납 op `add`(`{"draftSeq", "draft", "propagate"}`) — 그
    `draftSeq` 가 세션 초안 번호(`GridState.draft_seq` — 넣으면 그 번호 + 1 로 오른다)보다 작으면 **말없이 버린다**(개편 명세 6-4 —
    두 번 누른 둘째 op 가 이름 겹침으로 거부되어 첫 op 의 성공 토스트·되돌리기를 덮지 않게, 가져오기 뒤 옛 초안이 들지 않게). 받은
    초안을 다시 보고 막히면 넣지 않고 그 까닭을 토스트로, 아니면 편집본 설비 마스터 **끝**(행 차례는 공통 대장 내용)에 한 줄을 잇고
    불러온 목록 맨 위에 두며 되돌리기 한 단계, `GridApplied.added` 에 (행 id, 설비명, 함께 넣기)를 싣는다. 가정 편집 회차면 토스트에
    「공식 배치에는 자리 없이」(설계 Q1). 가져오기는 `copied_draft`(호기 정보 묶음 — 설비명·Main 설비 뺌 — 와 동·층·레이아웃표시,
    기존설비여부 N, 투자구분 기존 → 신규)·`copy_source`(같은 이름 → 앞부분 첫 줄)이고, 추가 뒤 초안은 `kept_draft`(공정소분류·동·층).
    칸 data 는 `new_unit_data`(칸 자리 번호의 오류·경고·잠금·체크 줄·초안 번호 `seq`·`checked`).
- `src/capa_simulation/services/equipment_samples.py` — 설비 DB 가 빌 때만 쓰는 비영속 샘플 fleet 이다(연결 뒤 지운다).
  - `SAMPLE_BASELINE_COUNTS` 는 생성기 `PROCESS_SPECS` 를 옮긴 것이라 함께 고친다(`tests/test_equipment_availability.py`).
- `src/capa_simulation/services/chatbot_samples.py` — Capa Chatbot 답변 대본(결론·근거 표·산식·한계)이다. 순위·Gap 은
  원본 공정명으로 셈하고 결론·질문·조건의 공정 이름만 부르는 쪽이 넘긴 글자 함수(`process_name`)로 적는다 — 표시명
  모듈은 import 하지 않는다(8장).
- `src/capa_simulation/services/floor_layout_mark.py` — 층 도면 비설비 요소의 계약·검증(`prepare_floor_layout_marks`)이다.
  층 단위 전체 교체라 어긋난 항목 하나에 통째로 거부한다(7장).
  - 영역만 테두리 모양·이름표 정렬(`ZONE_BORDER_STYLES`·`ZONE_LABEL_ALIGNS`, 첫 값이 처음 값이자 옛 행의 값 —
    `zone_look`)을 갖는다. FAB 요소(`fab_layout.prepare_fab_layout_marks`)도 같은 규칙이다.
  - 층의 Main 설비명 위치(`GROUP_LABEL_POSITIONS` — 가운데·위·아래 모두 행으로 받는다. 고른 적이 없거나 처음 위치로
    되돌린 묶음은 행이 없고 모양의 처음 위치 `space_layout_edit.default_group_label` 로 선다 — 한 줄 묶음(모듈 2·3)은
    위라 가운데를 고르면 가운데 행이 남는다)의 검증은 `prepare_group_labels`(Main 설비 이름은
    빈칸 아닌 글자 — 설비 마스터처럼 길이·글자를 묶지 않아 적용이 받은 이름을 저장이 거부하지 않는다), 층 대조 지문은
    요소와 위치를 함께 본 `floor_layout_fingerprint` 다(위치가 없으면 `marks_fingerprint` 와 같다).
- `src/capa_simulation/services/layout_overlay.py` — **가정 설비 시나리오의 Space 배치 차이**(설비 `0031`, 설비 시나리오 2단계
  S2)의 순수 규칙. 공식 배치(공통 대장의 배치 일곱 칸 `SCENARIO_LAYOUT_COLUMNS` + 층 현행값) 위의 「공식과 다른 것만」 이다.
  - `LayoutOverlay` — 호기 차이(키·저장 당시 Main 설비·일곱 칸 **통째**), 층 요소 차이(id 마다 `set`·`drop`), Main 설비명 위치
    차이(None = 공식 행 지움). 지문 `digest()`(빈 차이는 `EMPTY_LAYOUT_DIGEST` = `empty`), 캐시용 기본형 payload
    (`to_payload`·`from_payload` — 꺼낼 때 지금 클래스). 만들 때는 `make_layout_overlay`(차례 맞춤).
  - 얹기 `apply_unit_overlay` 는 **예외를 내지 않는다**(I4) — 모듈 묶음(Main 설비 행 둘 이상, `space_layout_edit.module_group_rows`
    한 규칙)은 머문 구성원(기록한 Main 설비가 지금 묶음, 공식에서 이름만 바꾼 경우 포함)의 많은 쪽 층이 가정 자리이고, 소속이
    바뀐 모듈은 그 자리에 X·Y 를 비워 둔다(`regrouped`). 공통에서 지운 호기의 차이는 버리고 센다.
  - 나누기 `split_layout(편집본 LayoutBase, official, started, role, overlay_present)` — 공식 역할은 바뀐 호기만 공통에(가정이던
    때의 차이가 있는 옛 리비전에서 배치를 바꾸면 거부), 가정 역할은 공통 쪽 `hypothetical_common_places`(공식 그대로·새 호기는
    자리 없이·있는 묶음의 새 모듈과 묶음에 넣은 **공식 동·층 미정** 호기는 그 묶음 공식 동·층 — Q1)·공식 층이 다른 호기를 한
    묶음으로 묶으면 거부하고, 차이 = 편집본 ≠ 공통 쪽(묶음 통째). 공통 프레임에 적을 때는 `common_with_places(official=
    layout_cells(...))` 가 공식과 같은 자리를 원래 칸 값으로 옮기고 그 밖은 다른 칸만 바꾼다(`Place` 는 견줄 꼴 — 반올림).
    S2 화면 잠금 재료 `assumption_common_places`·`misplaced_rows`·`place_rows` 가 같은 규칙으로 편집본을 맞춘다.
    `assumption_group_refusal(편집본, 세션 저장본, origins, 공식 일곱 칸)` 은 그 묶음 거부를 저장소와 같은 글로 미리 낸다 — 설비
    마스터 탭 가정 세션은 그 묶음 고침을 「저장 전 변경」 고칠 것 한 줄로 올려 「리비전 저장」 을 막고
    (`equipment_master_tab._table_errors` — 배치 차이가 아직 없는 갓 복제 시나리오도), 붙여넣기는 미리보기 전에 거부한다
    (`assumption_group_paste_refusal` — 설계 10장·Q1(c)).
  - 정규화 `normalize_layout_overlay(overlay, base, official_floors)` — 그 쓰기의 공통·층 값과 같아진 차이를 지운다. 요소·이름표
    합치기·차이(`effective_floor_marks`·`mark_changes` — 차이 차례는 공식 id 의 공식 차례 → 새 요소라 지문이 편집기 차례에
    흔들리지 않는다·`effective_group_labels`·`label_changes`), 설비 단위 셈 `overlay_unit_count`(묶음은 1대)·머리 알림 재료
    `layout_difference`(실효 설비 수·레이아웃표시만 다른 수·일정 없어 뺀 수·저장된 행 수 — S3 가 그린다), 일정 리비전 출처
    허용값 `SCHEDULE_REVISION_ORIGINS`(+ `layout_clear`).
  - S4: 「공식과 견주기」 재료 `layout_compare`(층 하나 — 기준 쪽 점선 상자 `CompareGhost`·들어온 호기 `CompareArrival`, `shown` 은
    화면이 그리는 설비명)·`unit_differences_by_floor`(층마다 공식과 자리가 다른 설비 수 — 나간·들어온·안에서 옮긴, 묶음 1대,
    일정 없음 제외 — `shown=` 을 주면 그 설비명만), 남의 공통 저장 뒤 다시 얹기 `reapply_layout_edits(옛 저장본, 편집본, 새 저장본,
    origins=, old_keys=, new_names=, approved=)` → `ReappliedLayout`(다시 얹은 **설비 단위** 수 — 묶음 1대·빠진 호기·옮긴 편집기
    묶음 승인 — 있던 호기의 일곱 칸을 원래 칸 값 그대로), 공식 발행 막힘 글 한 곳 `layout_publish_blocked_words(PublishBlock)`(확인
    팝업·발행 쓰기 거부가 같이 쓴다).
- `src/capa_simulation/services/fab_layout.py` — FAB 동·층 정의, 층 이름·주소 인자 변환, FAB 전체 도면의 계약·검증
  (`prepare_fab_layout_marks`)을 둔다. 요소 행이 없으면 `default_fab_layout()` 기본 배치를 그린다.
- `src/capa_simulation/services/space_layout_edit.py` — Space 배치 편집기의 순수 계산(입력, 적용값 검증, 반영, 미저장
  차이)이다. 적용값은 하나라도 어긋나면 전체 거부한다(`parse_editor_apply`).
  - 이름 겹침은 바꾼 뒤 상태를 설비 마스터 전체에서 `scalar_match_key` 로 본다(저장 검증보다 엄하다). 지운 채 저장 안 한
    이름은 못 쓴다(`reserved_names`). 가림·겹침은 경고만 한다.
  - 새 호기 이름 규칙은 `_require_new_unit_name` 한 곳이다 — Space 편집기 새 호기(`_parse_created`)와 설비 마스터 「새 호기」
    칸(`check_new_unit_name(name, *, master, reserved)` — 걸리면 까닭, 받으면 None, 개편 단계 C)이 같은 글로 막는다.
  - **이름 바꾸기 공용 넷**(G4·R2 — 이름 바꾸기는 같은 호기, 설비 시나리오 2단계 S1). 이름 바꾸는 자리(Space 편집기·개편
    뒤 설비 마스터 호기 상세)는 모두 이것을 쓴다 — 새 자리가 규칙을 따로 짜지 않는다.
    `check_unit_rename(old, new, *, master, reserved, renaming, group_renaming, created)` 는 한 바꿈을 보고 거부 까닭(Space
    적용 거부 문구 그대로 — `_require_name`·`_require_distinct_names(only=…)` 를 지난다) 또는 None 을 낸다(`renaming` 은
    같은 제출의 다른 설비명 바꿈 — 맞바꿈·사슬은 받고 같은 새 이름은 막는다, `group_renaming`·`created` 는 같은 제출의 Main
    설비 바꿈·새 호기). `master` 는 바꾸기 **전** 편집본이든 제출 **뒤** 마스터(이 바꿈이 이미 든 — 설계 11-2 4단계)든 받는다
    (`_names_before` — 옛 이름이 모두 있으면 전, 아니고 새 이름이 모두 있으면 뒤로 읽어 새 이름 행 하나를 옛 이름으로 돌린다).
    Space 적용(`parse_editor_apply` → `_require_distinct_renames`)도 설비명 바꿈마다 이 함수를 부른다(이름 모음만 아는 자리라
    두 칸짜리 판정용 표 `_names_master` 를 넘긴다) — 규칙을 더하면 Space 도 따라간다. `compose_unit_renames` 는 저장 안 한 이름 지도
    (`PendingRenames.units`)를 잇고 `compose_renames` 가 그것을 부른다. `rename_followers` 는 설비명이 이미 새 이름인 마스터에서
    비가동 설비명과 자기 이름을 Main 설비로 적은 한 행 묶음의 Main 설비를 옮기고(같은 제출에서 사용자가 고친 칸
    `touched_*` 는 두고), `apply_name_changes` 가 그것을 지난다. 세션 쪽 넷째는 `equipment_data_workspace.follow_unit_renames`.
  - `saved_layout_drift`·`restore_saved_layout` 는 배치 칸 잠금(잠긴 회차)·「배치 변경만 버리기」(3장
    `equipment_data_workspace.layout_edits`) 재료다 — 저장본 호기를
    잇는 행(지금 설비명 → 저장본 설비명 지도, `equipment_scenario.inherited_unit_names`)의 배치 일곱 칸(`PLACE_COLUMNS`)을
    **저장본** 그 호기와 견주어 다른 행을 찾고 그 칸만 저장본 값으로 되돌린다(제출 전 편집본과 견주면 지운 뒤 다시 넣기·이름을
    바꿨다 되돌리기가 새 호기로 읽혀 지나간다).
  - 모듈 묶음 판정(Main 설비가 같은 행이 표 전체에서 둘 이상)은 `module_group_rows` 한 곳이다 — 저장 전 바둑판 검사와 가정
    배치 차이의 묶음 통째 규칙(`layout_overlay`)이 같이 쓴다. `PLACE_COLUMNS` 는 계약의 배치 일곱 칸 `SCENARIO_LAYOUT_COLUMNS` 다.
  - 모듈 묶음 바둑판의 정본은 `module_cells`(`module_grid` — 모듈 2·3 은 열 n·행 1, 넷부터 열 = ⌈√n⌉·행 = ⌈n÷열⌉,
    칸 번호는 왼→오·위→아래, 저장 정밀도 눈금으로
    똑같이 나누고 마지막 열·행이 나머지를 받아 틈·겹침 0, 칸마다 최소 한 눈금)와 칸 배정 `assign_module_cells`(지금
    자리에 가까운 칸 — 이미 바둑판이면 제 칸, 좌표 없는 형제는 남은 칸을 자연 정렬로)다. `tile_module_group` 은 새로
    놓을 때의 자연 정렬 배정이다. `parse_editor_apply` 는 `editor_items`·`editor_ghosts` 를 받으면 이 층에 놓이거나
    자리·크기가 바뀐 묶음(숨은 모듈 포함)이 적용 뒤 바깥 상자의 바둑판인지 보고, 모듈마다 한 눈금 안이면 칸 값으로
    **바로잡고** 더 다르면(모듈 하나만 옮기거나 키운 값) 거부한다. 안 바뀐 옛 묶음은 건드리지 않고, 묶음이 갈라져
    오면(일부만 빼거나 보내거나 좌표 없는 형제가 안 놓임) 거부한다. 상자를 한 모듈에만 그린 묶음의 좌표 없는 형제는
    `editor_inputs` 가 미배치 모듈로 함께 보낸다(서랍에는 뜨지 않고, 묶음을 처음 옮기거나 키울 때 제 칸에 놓인다).
  - 숨은 모듈(`EditorInputs.ghosts`)은 보내는 호기와 Main 설비가 같고 이 층에 상자가 있지만 도면 대상이 아닌
    형제(레이아웃표시 N·도면 이탈)다. 묶음의 칸 수·자리에 들어 기준일이 바뀌어도 바둑판이 그대로이고, 묶음과 함께
    옮겨진 값은 적용값 `ghosts` → `EditorApply.hidden_moves` 로 와서 `apply_layout_edits` 가 X·Y·크기만 바꾼다(층·
    레이아웃표시 그대로). 묶음째 빼거나 다른 층으로 보낸 적용에 옮겨진 숨은 모듈이 오면 거부한다(편집기는 처음 자리로
    되돌려 보낸다) — 빼면 숨은 모듈은 이 층 제자리에 남고, 보내면 `_harmonize_groups` 가 층을 맞추며 X·Y 를 비운다.
    상자 없는 숨은 형제는 세지 않는다.
  - **설비 마스터 저장의 묶음 좌표·크기**(2026-10-23 사용자 답 「막자」): `module_layout_violations` 는 저장 후보를
    저장본과 견줘, 묶음 행 하나라도 X좌표·Y좌표·Xsize·Ysize 가 바뀐 묶음(저장 안 한 Space 이름 바꿈 `renames`, 설비 마스터 탭에서
    이름만 바꾼 행은 저장본에서 사라진 행과 값이 같으면 같은 행)이 좌표 있는 행이 하나도 없거나 — 좌표를 잃은 행 없이 —
    좌표 있는 행의 바깥 상자를 그 행 수 바둑판으로 나눈 칸과 한 눈금 안이 아니면 그 Main 설비를 돌려준다(문구는
    `module_layout_message`). 안 바뀐 옛 묶음, Main 설비 칸만 고친 묶음 넣기·빼기, 좌표 없는 새 묶음은 막지 않는다.
    배치 편집기가 적용한 묶음은 적용 뒤 모양(`module_layouts`)이 `approved` 와 같으면 보지 않는다 — 숨은 모듈이 있는
    묶음을 빼거나 다른 층으로 보낸 결과처럼 이 규칙으로는 바둑판이 아닌 편집기 결과가 있다.
  - 적용값 `groupLabels`(실린 모듈 묶음만, `module_group_sizes`)는 `EditorApply.group_labels` 가 되고
    `next_group_labels` 가 층 위치 목록으로 합친다 — 실린 묶음은 보낸 위치로 갈고(그 묶음 모양의 처음 위치
    `default_group_label` 이면 행을 두지 않되 이미 같은 위치의 행이 있으면 그대로 둔다, 보내지 않은 실린 묶음 = 다른 층으로
    보냄은 빠짐), 실리지 않은 묶음은 그대로 두며, Main 설비 이름 바꿈(`group_renames`)을 새 이름으로 따라간다(실리지 않은
    묶음의 위치도 — 모듈 하나만 실려 묶음이 아닌 채 이름을 바꾼 때).
  - `prefix_sizes`(`new_unit_options` 의 `prefixSizes`)는 설비명 앞 3자리(`name_prefix` — 앞뒤 공백을 걷은 첫 세 글자,
    세 글자 미만은 빈 글자)마다 편집본에서 크기가 있는 설비 가운데 설비명 자연 정렬이 가장 뒤인 것의 크기다. 모듈 묶음의
    모듈(Main 설비가 같은 행이 둘 이상, `module_parents` — `newUnit.moduleParents` 로 함께 보내 편집기가 같은 기준으로
    종류를 가른다)과 그 밖을 따로 둔다 — 편집기 서랍의 크기 불러오기가 쓴다(편집기 절).
- `src/capa_simulation/services/floor_layout_profile.py` — 층 배경 도면의 치수 읽기·캔버스 기본값·크기 상한과 좌표 반올림
  (`rounded_to_canvas`)의 한 곳이다(`space_layout_edit`·`fab_layout` 이 import 한다 — 거꾸로 두면 순환).
- `src/capa_simulation/services/display_order_editor.py`, `display_order_csv.py` — 웹 편집 표시순서 규칙의 검증·범위
  교체·CSV 직렬화다. 분류값 중복은 `match_key` 로 본다(8장). 공용 프로필 교체는 현재본만 남긴다 — 이전 규칙을
  보존하지 않으므로 교체 전에 CSV 를 내려받아 두는 것이 유일한 되돌리기다.

### 화면 공통 계층

- `src/capa_simulation/navigation.py` — 사이드바 페이지 목록·그룹 상자·구역 제목을 선언하고 `st.Page` 묶음을
  만드는 단일 선언 지점이다. 페이지 추가·제목 변경·새 그룹은 여기서만 한다.
  - `PageSpec`·`SIDEBAR_GROUPS`·`SIDEBAR_SECTIONS`(`section.key` 가 컨테이너 key·CSS 선택자의 근거)·`ADMIN_AREA`·
    `ADMIN_BOX_PAGES`. 상태 접미는 `IMPLEMENTING_SUFFIX` 하나이고 `page_header.py` 가 배지로 쓴다.
  - `PageSpec` 이 화면이 `app.py` 에 바라는 공통 조건(`reads_*`·`condition_tabs`·`has_condition_cards`)과
    설비 DB 핀(`uses_equipment_db`)·설비 시나리오(`equipment_scenario` — `"session"`/`"official"`, `equipment_scenario_tabs`,
    `reads_equipment_scenario_on`)를 선언한다. `app.py` 는 선언만 따르고 화면 이름으로 가르지 않는다. 가용설비 현황 탭
    라벨(바깥 `EQUIPMENT_TABS`·Summary 안쪽 `EQUIPMENT_SUMMARY_TABS`)도 사이드바가 열린 탭을 보므로 여기 둔다. 안쪽 탭을
    품은 바깥 탭은 `ConditionTabs.sub`(`SubTabs`)로 적고, 사이드바는 `ConditionTabs.active_label`(위젯 값 → 기억 칸 → 첫
    탭, 라벨 목록 밖의 옛 값은 첫 탭)로 **가장 안쪽 라벨**을 본다 — `labels`·`card_labels` 도 안쪽 라벨로 적는다.
- `src/capa_simulation/page_bootstrap.py` — 계산 페이지 공통 진입 절차(활성 리비전·표시순서·활성 시나리오·
  조회기간과 원천 유효 구간 확정)다. 페이지는 `BOOTSTRAP_ERRORS` 를 잡는다.
  - 잡은 예외의 화면 문구는 `bootstrap_error_message` 한 곳이다. `duckdb.Error` 는 갈래마다 조치를 바꾼다 — 쥔 PID 가
    적힌 잠금(이 앱 자신이면 새로고침, 다른 프로그램이면 그것을 닫기), 쓰기 실패(DuckDB 영문 고정 문구 `Could not
    write`·`Failed to commit` — 「저장되지 않았습니다. 디스크 공간과 쓰기 권한」), 그 밖의 열기 실패(`IOException` 의
    `Cannot open`·`Could not set lock` — 다른 프로그램·파일 권한과 경로), 어느 것도 아니면 「데이터베이스 작업이
    실패했습니다」다. 쓰기 실패와 그 밖에는 원문(종류 이름 + 앞 300자, 줄바꿈을 접은 코드 표기)을 붙인다. 그 밖의
    예외는 서비스가 만든 한국어 문장 그대로다. 서명(`database_paths` — 어느 DB 인지는 부르는 쪽이 안다)은 화면 수십
    곳과 `scripts/sync_object_storage.py` 가 같은 꼴로 부르므로 바꾸지 않는다.
  - `scenario_capacity_and_demand`·`stop_calculation_on_error` 는 계산이 멈추면(ValueError) 사이드바를 「계산
    멈춤」으로 바꾸고 다시 던진다(뒤의 것은 시나리오 수준 오류만 나는 호출에만). 계산 함수는 부를 때
    `simulation_cache` 모듈에서 찾는다 — 페이지 테스트가 그 속성을 바꾼다.
  - `no_demand_message` 는 `resolve_effective_months` 를 거치지 않고 소요대수가 빈 것으로 「조회기간에 소요대수가
    없다」를 아는 자리(필요 단축 일정, Static 대비 일정의 확보율 교차검증)의 안내다 — 다른 계산 화면과 같은 문구에
    활성 시나리오 `RQ_REQB` 의 데이터 범위를 붙인다. 소요대수를 읽지 못한 갈래의 문구와 섞지 않는다.
  - `date_range_value`·`prune_list_selection`·`prune_choice` 가 위젯 값 정리다. 뒤의 둘은 위젯 앞에서 매 회차
    세션에 되쓴다(`pop` 하지 않는다). `prune_choice` 는 글자 선택지 전용이다(`str(saved) in options`) — 정수 달 상자는
    제 화면이 잡는다(`constraint_simulation_state.settle_period`). `render_schema_ahead_warning` 은 DB 가 코드보다 새
    버전일 때 경고한다.
  - `process_page_inputs(database_path)` 는 공정 하나를 보는 두 화면(공정 Capa 상세·제약 시뮬레이션)의 공통 진입이다 —
    판정 기준 → 공통 진입 → 유효 기간(`RQ_REQB`) → 시나리오 키 → 확보율(멈추면 「계산 멈춤」) → 달·공정 선택지를 **같은
    차례**로 내 두 화면의 계획 캐시 키가 같다. 카드 캡션·`st.error`·`st.stop` 은 페이지가 쥐고, DB 경로는 페이지가 그 회차의
    `settings` 에서 읽어 넘긴다(시험이 설정을 바꾼다).
  - `forget_page_dialogs`·`count_page_visit` 은 `app.py` 가 페이지가 바뀐 회차에 부른다(팝업 열림 칸 버림·방문
    차례 올림). 앞의 것은 팝업 여는 콜백도 부르지만 뒤의 것은 그 회차에만 부른다 — `page_visit` 으로 「다시
    들어왔다」를 아는 화면이 같은 페이지의 rerun 에서 위젯 아닌 칸을 거두지 않게.
- `src/capa_simulation/settings.py`, `sidebar_status.py` — 앱 이름·경로·조회기간 상수와 운영 DB 자리 판정
  (`settings.is_operational_database_place` — 사본 전용 스크립트의 거절과 점검 스크립트의 앱 프로세스 확인이 쓴다)과, 사이드바의
  구역 제목·조건 패널 칸·조회기간 상태 표시·접힘을 기억하는 상자·조건 카드(`sidebar_status`)다.
  - 월 표기 `YYYY-MM` 은 `settings.format_month` 한 벌이다. 조건 패널의 페이지 칸(`page_condition_slot`)은
    세션에 둔다 — 모듈 전역에 두면 세션끼리 나눠 쓴다.
  - `sidebar_expander`·`condition_card` 는 `key` + 상태 추적 `on_change` 로 펼침을 기억한다(`expanded=` 없음).
    조건 카드 key 는 `condition_card_<이름>` 이고 `sidebar_style.py` 가 그 접두어 하나로 서식을 건다.
  - 상자 여닫기는 9장 **여닫을 때 본문을 다시 돌리지 않는다**의 구현이다(`on_box_toggle`·`rerun_fragment_if_alone`·
    `keeps_app_run_open`·`begin_app_run`). 진짜 프래그먼트 회차는 `tests/fragment_browser.py` 대역으로 돌린다.
- `src/capa_simulation/design/tokens.py` — 색·서체·표 치수를 역할 이름으로 단일 정의하고 지금 테마의 값을
  돌려준다(규칙 `docs/design_system.md`). Figure 공통 유틸은 `components/plotly_layout.py` 다.
  - 두 팔레트(`_LIGHT`·`_DARK`)를 `__getattr__`(PEP 562)로 골라 쓰는 쪽은 `tokens.SURFACE` 그대로다. 두 팔레트의
    이름은 정확히 같아야 한다(`tests/test_design_tokens.py`). 별칭·계산값은 `_complete()` 가 팔레트에서 만든다.
  - 타입은 `if TYPE_CHECKING:` 블록이 알린다(`.pyi` 스텁은 mypy 가 무시한다). 테마를 타지 않는 치수는 팔레트 밖이다.
- `src/capa_simulation/design/theme.py` — 세션이 보는 테마를 실행 한 번에 한 번만 정해 스레드 칸에 담는다(모듈
  전역 아님). `app.py` 가 토큰을 하나라도 읽기 전에 `begin_run()` 을 부른다.
  - 프래그먼트만 도는 회차는 세션(`_capa_theme_mode`)의 직전 전체 회차 테마를 잇는다 — 프래그먼트 본문에서
    `begin_run()` 을 부르지 않는다(`tests/test_shortening_view_fragment.py`).
- `src/capa_simulation/components/page_header.py` — 모든 페이지의 제목·설명·상태 배지다(상태 접미는 사이드바
  라벨과 같은 문자열). **큰 제목은 키 칸(`PAGE_TITLE_KEY`)에 담아 화면에서만 sr-only 로 숨기고**(화면 탭 줄이 이름을
  말한다 — 2026-10-24) 인쇄·읽기 도구에 남긴다. 배지·설명 줄은 그대로다. `render_page_header_with_status` 는 진행
  표시 자리(`STATUS_SLOT_KEY` 안 `st.empty()`)를
  돌려주고, 그 자리를 머리 띠에 고정하는 것은 `app_header` 의 CSS 다. 두 함수 모두 `trailing` 을 주면 제목 줄 끝 칸에
  그것을 그린다(HOME 주요 Case 칩, 가용설비 현황 「설정」·필요 단축 일정 「Qual 마감 계산기」 단추 — `_render_title_row` 한
  벌) — 제목과 끝 칸은 `st.columns` 다(가로 컨테이너는 `h1` 여백을 지운다 — 9장). 두 칸의 폭은
  비율이 아니라 글자 폭이다(`TITLE_ROW_KEY` 컨테이너 바로 밑 칸만 고르는 CSS). 화면에서는 제목이 숨어(흐름에서 빠진다) 끝
  칸만 오른쪽 끝에 선다. 제목이 보이는 인쇄에서는 한 줄에 안 들면 끝 칸이 통째로 제목 밑 오른쪽으로 내려가고 제목은 접히지
  않는다(비율로 나누면 사이드바를 편 800~900px 에서 제목이 접히고 칩 줄이 넘쳤다).
- `src/capa_simulation/components/equipment_master_tab.py` — 가용설비 현황 탭 ① 「설비 마스터」 본문(개편 B1-c·d — 옛 RawData
  폼을 대신한다). 맨 위 줄(표 고르기 `equipment_master_table_v1` · 설비 시나리오 알약 · 리비전 · 「저장 전 변경 n건」) → 알림 칸 →
  두 칸(7:3 — 표 카드 또는 작은 편집표 · 오른쪽 칸 고르기 `equipment_master_side_v1` 「호기 상세 · 새 호기 · 저장 전 변경 · 저장
  이력」). 두 고르기는 `persist_state="session"` 이고 콜백이 값을 적으므로 `default=` 없이 위젯 앞에서 칸이 없을 때만 심는다
  (`required=True`). 받기 콜백이 오른쪽 칸을 바꿀 때는 그 칸을 바로 적지 않고 `_SIDE_NEXT_KEY` 에 두어 다음 고르기 **앞**에서
  적는다(진짜 콜백은 회차 맨 앞이라 같은 회차 — 시험 대역은 고르기 뒤 마운트에서 부르므로 위젯을 만든 뒤 적는 오류를 피한다).
  - **새 호기**(개편 단계 C): 오른쪽 「새 호기」 칸은 세션 초안(`NEW_UNIT_DRAFT_KEY` — {번호, 39칸 글, 함께 넣기}, 저장해도
    남는다)을 그 회차 편집본 위에서 `new_unit_check` 로 보고 그린다(합성 3천 대 한 번 약 0.05 s — 샘플 관측, 칸 결과처럼
    메모하지 않는다). 브라우저는 칸을 확정할 때마다 상태 값 `draft`(번호를 올림)를 보내고 받기 콜백은 번호가 세션 초안보다 작지
    않을 때만 적는다. 출납을 얹을 때 세션 초안 번호를 `GridState.draft_seq` 로 넘긴다(옛 번호의 `add` 는 서비스가 버림). 「호기
    추가」(`add` op) 뒤에는 넣은 호기마다 함께 넣기 고름을 적고(`remember_new_unit_propagation` → `NEW_UNIT_PROPAGATE_KEY`), 마지막
    호기를 「호기 상세」 로 열며(토스트 「되돌리기」 도 상세 칸), 초안은 번호를 올려 공정소분류·동·층만 남긴다. 막히면 받은 초안을
    세션 초안으로 둔다 — 세션 초안보다 번호가 작은 `add`(버린 두 번 누름)는 보지 않는다(다음 회차에 따로 온 둘째 누름이 넣은 뒤
    초안을 옛 초안으로 덮지 않게). 「새 호기」 칸 고름은 그 호기가 편집본에서 빠지면 걷는다(`prune_new_unit_propagation` — 표 출납
    뒤·Space 적용 뒤·엑셀·CSV 넣기 뒤, **이름 바꿈을 따라간 뒤**에 부른다) — 같은 이름이 다른 길로 다시 들면 저장 칸 체크를 따르고,
    되돌려 되살린 호기도 저장 칸 체크다. 가져오기(`copy` 트리거 — 상세 「이 호기로 새 호기 만들기」 는 빈 초안에,
    「비슷한 호기에서 값 가져오기」 는 브라우저 초안 위에)와 불러오기 「+ 새 호기」(`new`)가 이 칸을 연다. 가정 설비 시나리오면 칸
    위에 새 호기 자리 안내(공식 배치에는 자리 없이 — Q1)와, 함께 넣기를 켰을 때 공식 가용대수 경고(Space 저장 상자와 같은 글)를
    싣는다. 함께 넣기 기본값은 저장 칸과 같은 F6(켬)이다. 저장 구획은 그 칸에서 넣은 호기 수와 그 고름(같은 일정 n대 · 일정 없음
    m대)을 한 줄로 적는다(`new_unit_choice_line` — 사이드바 설비 시나리오 팝업 「저장」 과 Space 「저장 칸」 도 같은 줄, 가정 세션이면
    같은 일정으로 넣는 호기가 공식 가용대수에 센다는 꼬리 — 그 칸 고름이 세 저장 길 모두에서 저장 칸 체크를 이기므로).
  - **CCv2 마운트 앞의 자리는 고정한다** — 낡음 경고·잠금 줄·이름 바꿈 목록·비활성 층 경고는 늘 서 있는 칸 안, 알약 「저장 전
    변경」 도 늘 서 있는 칸 안이다(순번이 밀리면 표가 다시 마운트되어 보내지 않은 출납·고름을 잃는다 — 9장).
  - 한 회차에 표 모양(`build_view` → `equipment_grid.build_grid_view`)을 한 번 내고 세 마운트 data 를 그것에서 낸다. 칸 결과
    (`equipment_master_issues` — 저장과 같은 인자: 캔버스·오늘)는 편집본 세대·`buffer_base`·오늘·캔버스 열쇠로 세션 메모
    (`GRID_MEMO_KEY`, 튜플로 풂)에 한 번. 표 글자(`text_matrix` — 편집본은 편집본 세대·`buffer_base`, 저장본은 저장본 사본 토큰
    열쇠 → `GridSource.texts`)와 「내려받기」 현재 데이터 바이트(`_render_current_data_downloads(memo_key=)`)도 같은 메모 칸이다 —
    고친 편집본이 있는 세션의 바뀐 것 없는 회차가 3천 대 × 39칸 글자·직렬화를 다시 내지 않는다(개편 명세 8장 「payload 메모」).
    편집본을 이 두 함수(`replace_equipment_buffer`·`apply_master_grid_result`) 밖에서 세대를 올리지 않고 바꾸면 메모가 옛 글자를
    그린다 — 시험도 `BUFFER_GENERATION_KEY` 를 함께 올린다. 표 단위로 막는 것(기존 보유대수·비가동 일정 검증·예시 행·모듈 바둑판·가정 묶음 거부·
    낡은 세션의 지운 호기·낡기 전에 고친 시나리오 칸 — `stale_scenario_edits`, 칸을 되돌리면 공통 칸은 저장된다)은 「저장하기 전에
    고칠 것」 줄이다. 낡은 세션의 뒤 둘은 표 밖 저장 자리도 같은 판정으로 막는다 — `equipment_data_workspace.stale_save_refusal`
    을 사이드바 팝업 「저장」 이 경고 글에, `save_equipment_buffer` 가 거부 글에 쓴다(Space 「배치 저장」 도 — 저장소의
    「다른 사용자가 먼저 …」 거부는 고칠 칸을 말하지 않고 다시 불러오면 공통 편집까지 잃는다). 일정 확인 갈래는 내용 지문
    캐시(`get_schedule_confirmation_issues`).
  - **받기**: 표·오른쪽 칸 두 마운트의 출납을 `apply_outbox` 하나가 `pending_ops`(마운트별 seq 기억 `equipment_grid_applied_v1`)·
    `apply_ops`(그린 회차의 `GridContext` 를 콜백 인자로 묶는다)·`apply_master_grid_result` 로 반영하고, 토스트는 마지막 op 를 보낸
    마운트에(「호기 추가」 가 넣은 회차만 상세 칸에), 각 마운트 data 에는 제 `ack` 를 싣는다. 배치·설비명·Main 설비 칸을 바꾼 op 와
    `official`·`undo`(되돌리기가 걷힌 배치 편집을 되살릴 수 있다 — 「한 단계 되돌리기」 단추도)·`add`(새 호기 자리는 배치 편집 —
    붙여넣기 새 행·엑셀·CSV 넣기와 같다) 뒤에만 배치 편집 판정(`buffer_has_layout_edits` 메모)으로 역할을 찍는다
    (`stamp_layout_role`). 트리거(불러오기·목록 비우기·열기·빼기·goto·팝업)는 목록·상세 id·표 고르기 칸만 적는다. 콜백 안에서
    `st.rerun()` 을 부르지 않는다.
  - **토스트는 실어 보낸 마운트가 사라지면 거둔다**(`settle_grid_toasts` — 탭 끝에 그린 마운트 이름으로, 탭이 숨은 회차에는 빈 것으로
    부른다). 브라우저의 닫은 토스트 번호는 마운트마다 새로 시작해 표 고르기·탭·오른쪽 칸 왕복에 닫은 토스트가 되살아났다. 아직 실어
    보내지 않은 토스트(숨은 동안 쌓인 것)는 처음 마운트할 때 보인다(실어 보낸 번호 `GRID_TOAST_SHOWN_KEY`).
  - **저장 구획**(「저장 전 변경」 아래): 변경 메모(옛 `_NOTE_KEY` — 저장 성공의 비움 표지 그대로)·저장 칸·지우는 호기 다른 시나리오
    확인 체크·힌트 한 줄·「한 단계 되돌리기」(`undo` op)·「모두 버리기」(확인 팝오버 — `reset_equipment_drafts(keep_fab=True)`)·
    「리비전 저장」. 「리비전 저장」 은 **잠그지 않는다**(출납은 300ms 묶음 — 마지막 회차의 판정은 브라우저보다 늦다): 콜백이 그린
    회차의 `base` 가 지금과 다르면(저장 뒤 옛 누름) 아무것도 하지 않고, 출납을 먼저 반영한 뒤 오류 수(칸 결과·초안·표 단위)·
    바뀐 것 없음을 판정해 단추 아래 한 줄로 알린다. 저장 전에 「지금 id → 저장 뒤 id」 지도(`save_id_map`)를 만들어 성공하면 목록·
    상세 id 를 옮긴다.
  - 가정 설비 시나리오 편집 회차(`layout == "overlay"`)면 `GridContext.official_places`(`_official_places_by_name` — 공식과 다른
    호기의 공식 일곱 칸)를 넘겨 호기 상세 위치 묶음에 「공식: …」 한 줄과 「공식 자리로 되돌리기」(`official` op — 모듈이면 묶음
    통째)를 세운다(설비 시나리오 2단계 설계 13-1). 되돌리기는 **공식 원래 값**(`GridContext.official_cells` —
    `official_layout_cells`, 공식 스냅샷의 그 호기 칸 그대로)을 적는다 — `official_places` 는 견줄 꼴(`CANVAS_DECIMALS` 반올림)이라
    그대로 적으면 공식 좌표 12.25 가 12.2 로 들어가 모듈 묶음 바둑판이 어긋나 저장이 막힌다. 원래 값이 견줄 꼴과 맞지 않으면(낡은
    세션 등) 견줄 꼴을 적는다. 공식 층이 다른 호기를 한 묶음으로 묶는 고침의 「저장하기 전에 고칠 것」 줄은 `official_places` 가
    비어도(배치 차이가 없는 가정 시나리오) 판정한다. 「내려받기」 팝오버는 양식 셋 + 현재 데이터 셋(`_render_current_data_downloads`).
- `src/capa_simulation/components/equipment_import_dialog.py` — 가용설비 현황 「엑셀·CSV로 한꺼번에」 팝업(옛 입력 탭을 옮김, 개편
  명세 4-8). 열림 값 `import`(「설정」 과 한 열림 칸·한 호스트 — `render_equipment_dialog_host(import_dialog=)`), 여는 콜백은
  `forget_page_dialogs()` 부터. 미리보기는 옛 입력 탭 그대로(`build_import_review` + 낡은 세션 거절 + 배치 잠금·가정 묶음 거절 +
  CSV 시나리오 주의, 가정 세션 「배치 칸도 붙여넣기」 기본 끔 — Q2). 끝 단추는 **「편집본에 넣기」 하나**(D7 — 사용자 R4):
  `ImportReview.matches` 가 참이면 `apply_import_review` — 통째 되돌리기 단계(`whole_step`) 하나·`replace_equipment_buffer`·칸 초안
  비움·새로 든 설비명을 목록 맨 위로·표 토스트(되돌리기)·넣은 편집본에 배치 편집이 있으면 그때의 역할 찍기(`stamp_layout_role` —
  넣고 나중에 저장하므로 그 사이 역할이 바뀌면 저장소가 막는다, 설계 6-2) — 뒤 열림 칸을 지우고 앱을 다시 돌린다. 팝업을 닫으면
  (`_close_dialog` — on_dismiss) 미리보기도 거두고, 여는 콜백(`open_equipment_import` — 표 불러오기 줄 `dialog` 트리거도)도 남은
  미리보기를 거둔다(닫힌 회차에 입력 칸이 버려져 다시 열면 빈 입력에 옛 미리보기만 남는다). 팝업 안 폼 제출은 앱 범위
  `st.rerun()` 이다(앱 회차에서 `scope="fragment"` 는 오류). 팝업 알림은 작은 편집표 알림 칸과 가른 제 칸(`IMPORT_*_KEY`)이다.
  새 방문 회차의 미리보기 거두기는 페이지가 매 회차 부르는 `withdraw_preview_on_new_visit`.
- `src/capa_simulation/components/equipment_master_grid.py` (+ `equipment_master_grid_assets/` HTML·CSS·JS) — 가용설비 현황
  「설비 마스터」 탭 표(Components v2, 그림자 DOM, 개편 B1)의 등록·그리기·받기. 탭 본문(`equipment_master_tab`)이 부르고, 페이지는
  그 탭이 열린 회차에만 그 모듈을 불러온다 — 모듈을 읽을 때 등록한다(`test_benchmark_home.py`).
  - 한 등록을 세 자리에 다른 key 로 마운트한다 — 불러오기 `LOADER_KEY`·표 `GRID_KEY`·오른쪽 칸 `side_key(panel)`(호기 상세·새
    호기·저장 전 변경). key 가 정체라 data 가 바뀌어도 다시 마운트되지 않지만 앞 형제 순번이 밀리면 다시 마운트되어 보내지 않은 출납을
    잃는다 — 탭 본문은 마운트 앞의 생겼다 사라지는 칸을 늘 서 있는 칸 안에 둔다(9장 「key 가 있어도 자리는 고정한다」).
  - data 는 `services/equipment_grid` 의 dict + 팔레트(`_palette` — CSS 의 `--emg-*` 는 모두 여기, 새 토큰 `GRID_*` 열(배치 머리 `GRID_LAYOUT_HEAD` 포함) —
    대비는 `test_design_tokens`)다. 편집본을 바꾸는 조작은 상태 값 `outbox` 하나(9장 「스크립트와 컴포넌트」 — 「호기 추가」 도
    `add` op), 상태 값은 그 밖에 「새 호기」 초안 `draft`(편집본을 바꾸지 않는다 — `draft_value` 가 거른다) 하나다. 트리거는
    불러오기 `load`·`clear`·`new`·`dialog`, 표 `open`·`unload`, 오른쪽 칸 `open`·`goto`·`copy`(`copy_request`) 이다. 받기 콜백이 꼴을 거르고(표 트리거는
    그린 회차의 `view` 와 같을 때만) 화면 쪽 처리 함수에 넘긴다 — 출납 처리 함수는 `outbox_value` 로 두 마운트를 함께 읽는다.
  - 브라우저: 불러오기(설비명 부분 일치·목록 같음/앞부분·못 찾음, 공정, 조건 — 사용자 R1, 일정 확인 필요, 전체), 칸 묶음·정렬·
    고름(브라우저 몫 — 칸 묶음만 localStorage), 가상 스크롤(줄 34px), 칸 고치기 키(Enter·Esc·Tab·↑↓·F2), 엑셀 여러 칸 붙여넣기
    (`paste` 이벤트의 `clipboardData` 만 — 설비명 칸에서 붙이면 설비명 열은 넣지 못한 칸으로 세고 옆 칸부터, 엑셀이 따옴표로 감싼
    칸(줄바꿈·탭이 든 칸, 안의 `""`)은 한 칸으로 읽는다 — `parseClipboard`), 값 넣기·날짜 밀기·
    지우기·되살리기·되돌리기, 상세 칸·저장 전 변경의 칸/호기 되돌리기. 업무 검증은 하지 않는다. 데이터 글은 `textContent` 로만,
    처리한 키는 `stopPropagation`(Streamlit 단축키가 글자를 먹는다).
  - 토스트는 표와 오른쪽 칸이 저마다 그린다(`fillToast`) — 「되돌리기」 는 그 토스트의 단계 표지를 실어 보낸다(대상 없는
    `undo` 는 맨 위 단계를 되돌린다). `moved` 는 목록 지문(`view`)으로 고름·스크롤을 처음으로 돌리기 **전에** 얹는다. 불러오기
    회차가 돌아와도 초점이 표 등 불러오기 밖에 있으면 찾기 칸으로 가져오지 않는다(`focusIsFree`). 팝오버는 화면 오른쪽 밖으로
    나가면 왼쪽으로 당긴다(`popoverShift`). 팝오버를 열면 초점을 패널 안 첫 칸으로 옮기고(`enterPanel` — 공정은 찾기 칸, 조건은
    첫 조건 칸) Esc 는 패널에서도, 열린 채 돌아온 여는 단추에서도 닫는다(닫히면 초점은 여는 단추 — 닫힌 단추의 Esc 는 막지 않는다).
    표 본문의 Tab 정지는 초점 칸 하나(체크·「−」 는 `tabIndex -1`, 칸 위 Space = 줄 고르기).
    「새 호기」 칸(`drawNew`)은 브라우저 초안을 들고(받은 초안은 번호가 클 때만 — `adoptDraft`), 체크 상자 칸은 판정이 지금 초안의
    것이면 그 판정, 아니면 칸이 찼는지만 보이고(`tierDone`), 칸 오류는 그 칸을 만졌거나 값이 있을 때만 — 다만 늘 필수인 칸이
    아니면(다른 칸 값 때문에 막는 칸) 만지지 않아도 보이고(`showsError`), 「호기 추가」 는 필수 칸이 찼고 지금 초안의 판정이 막지
    않을 때 켠다(`canAdd` — 판정 전이면 켜 두고 파이썬이 `add` op 를 다시 본다). 칸을 통째로 다시 그리는 칩·함께 넣기 체크·「양식
    비우기」(상세 칩도)는 `data-fk` 를 달아 초점이 돌아온다(키보드로 채우는 동안 칸 처음으로 가지 않게). 오른쪽 칸의 새 토스트가 화면
    위로 나가 있으면(칸 아래쪽에서 누른 「호기 추가」·「이 호기로 새 호기 만들기」·「이 호기 지우기」) 칸 머리를 보인다(`revealToast`·
    `needsReveal`, 토스트 `scroll-margin-top` 이 머리 띠를 비킨다) — 그 칸이 처음 선 회차이거나 「되돌리기」 가 달린 토스트만(칸 안에서
    고치다 받은 거절 한 줄로 쓰던 자리를 잃지 않게). 표지 색은 새 토큰 없이 팔레트(오류 선·강조·배치 머리 면·머리
    면)이고 글자(필수·가용대수·도면)가 함께 간다.
    순수 구획 `// <grid-…>` 은 `tests/test_equipment_master_grid_assets.py` 가 node 로 돌린다.
- `src/capa_simulation/components/page_tabs.py` (+ `page_tabs_assets/` HTML·CSS·JS) — 머리 띠 아래 화면 탭 줄
  (Components v2, 그림자 DOM)이다. **`app.py` 에서만 불러온다**(모듈이 컴포넌트를 등록한다 — `test_benchmark_home.py`).
  조건 팝업 호스트 칸 바로 뒤·페이지 앞에서 고정 key 로 매 앱 전체 회차 그리고 프래그먼트로 감싸지 않는다(9장 「스크립트와
  컴포넌트」). data 는 세션 목록·`PageSpec` 상수뿐이고 DB 를 읽지 않는다. 트리거 셋(`select`·`close`·`pin`)의 콜백은 목록 칸·
  이동 대기 칸만 적는다. 탭 이름은 사이드바 라벨에서 「(구현중)」만 뗀 글, 아이콘은 사이드바 Material 아이콘이다.
  - 점(`page_unsaved_marks`)은 세션만 읽는다 — 붙여넣기 대기·설비 편집본(가용설비·Space 두 탭)·Past Data 초안·시나리오
    관리 표 초안은 어느 화면에서나, 편집표의 적용 전 편집과 Space 층 사용 편집 초안(`floor_state_draft_pending` — `사용
    편집` 토글이 위젯 상태라 화면을 떠나면 초안이 버려진다)·가용설비 현황 설비 마스터 탭 작은 편집표 둘의 적용 전 편집
    (`small_editor_edits` — 시나리오 편집 등록부에는 넣지 않는다, 시나리오 저장 경고가 아니다)은 지금 탭에만 찍는다. 지금 화면의 그 둘이 있으면 다른 탭
    누름·지금 탭 × 에서 `confirm` 으로 묻는다(`leave_notice`). 사이드바 링크·뒤로가기에는 묻지 않는다. 시나리오 미저장·
    Cut-off 초안·Qual 계산기는 점 대상이 아니다. 테마 단추의 「저장 안 함」 표지도 이 판정 하나를 쓴다.
    - 묻기는 앞 회차 data 의 `leave` 로 정하므로, 편집표 칸을 쓰는 중이거나 막 적용(Enter)한 직후의 누름은 그 편집을 실은
      회차가 돌아올 때까지 붙든다(`page_tabs.js` 의 순수 구획 `<tabs-hold>` — 누를 때 포커스가 편집표였거나 마지막 편집표
      입력이 5초 안이면, 앱 회차가 끝나고 새 data 가 오거나 0.4초가 지날 때까지, 최대 `BUSY_MS`). 붙들지 않으면 확인
      없이 옮기고 편집이 말없이 사라졌다(E2E 결함). 편집표는 glide 격자(`stDataFrame`)와 칸 편집기 틀(`gdg-clip-region`)로
      알아본다 — 탭 줄 밖의 떠나기(테마 단추)는 이 붙들기를 지나지 않는다.
    - 탭 줄은 페이지보다 먼저 그리므로 「이번 회차에 그 편집표를 그리는가」 를 위젯 값으로 미리 본다 — 작은 편집표는 바깥 탭이
      ① 이고 표 고르기(`equipment_data_workspace.MASTER_TABLE_KEY`)가 그 표일 때만 센다. 고르기를 바꾼 회차에는 편집표 위젯
      상태가 회차 끝까지 세션에 남아, 그대로 세면 이미 사라진 편집에 「사라집니다 — 떠날까요?」 를 한 회차 동안 물었다.
      편집표를 숨기는 고르기를 새로 두면 판정에 그 고르기를 같이 넣는다.
  - 기록 한 칸(`page_tabs.js` 의 순수 구획 `<tabs-history>`, `tests/test_page_tabs_assets.py` 가 node 로 돌린다) — 문서의
    `history.pushState` 를 한 번 감싸(`window.__capaHistoryGuard`) 지금 경로와 같은 경로의 쌓기를 **늘** 칸
    바꾸기(`replaceState`)로 돌린다. Streamlit 1.63 프런트는 서버의 주소 인자 바꾸기(`page_info_changed`)마다 지금 경로로
    한 칸 쌓는다 — `st.switch_page` 가 떠나는 화면 경로로 먼저 쌓는 한 칸, 링크 인자를 받아 지우는 화면이 인자 달린 칸
    뒤에 또 쌓는 칸(뒤로가기로 인자 달린 칸에 닿으면 다시 지우며 또 쌓아 그 화면을 떠나지 못했다). 걸고 풀지 않는다.
    `st.switch_page` 의 첫 쌓기는 떠나는 칸 주소를 옮길 화면 인자로 바꾸므로(HOME 칸 → `/?process=…&from=home`), 인자를
    지우지 않은 칸 바꾸기 뒤 `LEAVE_MS`(1초) 안에 같은 인자로 다른 경로를 쌓으면 떠나는 칸을 원래 주소로 되돌리고 쌓는다 —
    남겨 두면 뒤로가기로 돌아온 그 칸에서 사이드바로 옮길 때 그 인자가 따라가 링크처럼 적용됐다. 인자를 지운 칸 바꾸기는
    되돌리지 않는다.
  - 화면을 옮기는 누름(다른 탭 고르기·지금 탭 ×)은 트리거를 보내기 **전에** 누름 기다림을 건다(순수 구획 `<tabs-queue>`).
    한 번에 하나 — 옮긴 화면의 탭 줄(지금 탭이 바뀐 data)이 오고 그 회차가 다 돌기(Streamlit 뿌리 `stApp` 의
    `data-test-script-state`) 전에 누른 탭은 보내지 않고 마지막 하나만 기다렸다 보낸다(`BUSY_MS` 가 지나면 그때 보낸다).
    옮기기 전에 보낸 누름은 프런트가 아직 떠나는 화면에 있다고 믿고 그 화면 주소로 회차를 청했고, 옮긴 화면이 도는 동안
    보낸 누름은 그 화면 부품들의 회차 요청과 서버에서 합쳐지며 트리거 값이 떨어졌다(1.63 `_coalesce_widget_states` 는
    단추 트리거만 남기고 컴포넌트 트리거는 새 요청 값으로 덮는다). 다른 탭 닫기·고정은 기다리지 않는다.
  - 상한(10개) — JS 가 사이드바·본문 화면 링크(`stPageLink-NavLink`) 누름을 문서 capture 단계에서 먼저 받아, 열린 탭이
    아닌 화면이면 막고 그 자리에서 알린다(data 의 `max`·`pages` — 모든 화면의 주소 → 탭 이름). 그래도 들어온 이동(뒤로·
    앞으로가기 — Streamlit 의 `popstate` 처리기가 먼저 돌아 막지 못한다)은 `route_page_tabs` 가 직전 화면으로 되돌리고
    HOME 칸 전달 칸을 버린 뒤 탭 줄 아래에 알린다. 이 되돌림은 기록을 쌓으므로 정상 길로 쓰지 않는다. 탭 데이터에는
    2단계(떠 있는 창) 대비로 화면 주소(`href`)를 싣는다.
  - 핀 단추 이름은 고정 여부와 상관없이 「… 고정」 하나이고 상태는 `aria-pressed` 가 말한다. 지금 탭이 아닌 고정 안 한 탭의
    핀은 가리킬 때만 보이고 숨은 동안 누름을 받지 않는다(`pointer-events: none` — 터치로 탭 이름 오른쪽을 누르면 고정이
    됐다). 가리킬 수 없는 기기(`hover: none`)에서는 그 핀을 두지 않는다.
- `src/capa_simulation/components/theme_toggle.py` — 헤더 툴바 슬롯에 밝게/어둡게 버튼을 얹고, 툴바·사이드바
  머리칸에 단추를 다는 다른 스크립트(Guide·Print·사이드바 라벨·터치 스크롤)를 같은 iframe 에 싣는다(`extra_scripts`).
  - 앱 안 테마 전환 API 가 없어 `localStorage` 테마 키를 적고 새로고침한다. 정본은 앱 키 `capa-theme`
    (`THEME_APP_KEY`), 규칙은 `THEME_RULE_SCRIPT`(`capaTheme`) 한 벌이고 다른 스크립트는 이것만 부른다.
  - 열릴 때의 새로고침(키를 고쳐 적었거나 `?theme` 이 다를 때 — `reloadOnOpen`)은 **문서를 연 주소**에서 빠진 인자를
    되살린다(`<theme-reopen>`, 연 주소는 `performance` 탐색 항목 — `history.replaceState` 로 바뀌지 않는다). 버려지는 첫
    세션도 링크 인자를 받아 주소에서 지우므로(Space `?layer=short…`·공정 Capa 상세 `?process=…`·제약 시뮬레이션), 지금
    주소에 테마만 붙이면 그 지우기가 먼저 닿은 때 새 세션이 링크 없이 열렸다(E2E 결함 — 사본 CPU 6배 느리게 9번 중 8번).
    같은 출처·경로일 때 빠진 이름만 싣고 지금 주소의 값은 그대로 둔다. 단추를 눌러 바꿀 때(`syncParam`)는 지금 주소
    그대로다. node 로 스크립트 셋을 가짜 부모 창에서 돌리는 시험이 `tests/test_theme_reopen_link.py` 다.
  - 툴바 차례는 `TOOLBAR_BUTTON_ORDER` 한 벌, 선택자 상수(`TOOLBAR_SLOT`·`THEME_BUTTON_ID`·
    `SIDEBAR_HEADER_SLOT`)는 이 모듈 한 곳이다. iframe 내용은 회차마다 같아야 한다(`tests/test_theme_toggle.py`).
  - 툴바에 단추를 더하거나 바꾸면 `TOOLBAR_BUTTON_ORDER`(와 `check_deploy_screens.TOOLBAR_LABELS`)에 넣고, `app_header`
    의 오른쪽 비움 폭(`_NARROW_HEADER_RULES` 포함)과 진행 막대 자리(`_status_slot_css`)를 다시 잰다 — 셋 다 지금 툴바를
    잰 값이다.
  - 전환은 새 세션이라 미저장 시나리오·설비 편집이 있으면 `confirm` 으로 묻는다(표지 `unsaved_edits_marker`).
    시나리오 밖의 것 — 설비 편집본·Space FAB 전체 배치 대기분(설비 편집본 세대 밖)·Space 층 사용 편집 초안·적용 전
    편집(편집표·붙여넣기 대기)·Past Data 초안·시나리오 관리 표 초안 — 은 `app.py` 가 같은 회차의 탭 점
    판정(`page_tabs.page_unsaved_marks`)으로 넣는다.
- `src/capa_simulation/components/page_guide.py` — 헤더 툴바 맨 왼쪽 `Guide` 버튼과 화면별 사용 안내
  대화상자다. 원문은 패키지 안 `guides/<페이지 파일 이름>.md` 다.
  - 툴바 버튼이 본문의 숨은 버튼(`page_guide_trigger`)을 대신 누르고 파이썬이 `st.dialog` 로 연다.
    `render_page_guide` 를 부른 화면에만 버튼이 보인다.
  - 따라하기 가이드를 단 화면(`render_page_guide(..., howto=<가이드>)` — 지금은 HOME 의 `lob`)은 `find_howto_guide`
    가 사내판 `static/guides/local/<가이드>.html`(git 무시) → 예시판 `static/guides/howto/<가이드>.html`(추적) → md
    대화상자 차례로 고른다. 고른 주소(문서 기준 상대 `app/static/guides/…` — WebIDE `/proxy/<포트>/` 접두에서도 맞다)를
    버튼 규칙의 CSS 변수(`GUIDE_HREF_VARIABLE`)로 싣고, 툴바 버튼이 누르는 순간 그 주소로 이름 붙은 좁은 옆 창
    (`capa-guide`, 폭 520)을 연다 — 파이썬 회차를 거치면 사용자 몸짓이 사라져 팝업 막이에 걸린다. 이미 열린 창은
    다시 읽지 않고 앞으로 부르며, 창을 못 열면 대화상자로 물러선다. md 원문은 창 머리 「설정 사전」 단추가
    `window.opener` 의 숨은 버튼을 눌러 앱 창에 연다(선택자 사본은 틀 `template.html`, `tests/test_page_guide.py`).
- `src/capa_simulation/guides/howto/` — 따라하기 가이드 뼈대(사외 정본): 원고 `<가이드>/content.json` · 촬영 계획
  `plan.json` · ID 장부 `ids.json` · 형식 `schema/*.json` · 틀 `template.html` · 사내가 찍지 않는 상태의 합성 예시 그림
  `<가이드>/example/`(WebP · `shots.json`). 사내는 `review/guide/` 의 글 덮어쓰기 · 매개값만 얹는다(git 무시).
  - 결과 자리: 합성 예시판 `static/guides/howto/<가이드>.html`(추적, 공개 저장소 — 그림 밖 글에 실 담당 조직 · 문의처
    · 이메일이 없음을 `tests/test_page_guide.py` 가 본다)과 사내판 `static/guides/local/<가이드>.html`(git 무시, 사내가
    저장소 밖 결과를 손으로 복사). 둘 다 Streamlit 정적 서빙으로 `app/static/…` 에 서고 1.63 은 `.html` 을
    `text/html` 로 내보낸다. 원고 판(`version`)을 올리면 예시판과 `example/` 을 같은 변경에서 다시 만든다. 틀만 고쳐도
    예시판을 다시 조립한다(`--example --assemble-only`, 작업 폴더가 없으면 촬영부터) — 데이터 자리 밖이 틀과 같은지와 창이
    앱 테마 값(`capa-theme` 의 `"Dark"`·`"Light"`)을 대소문자 없이 따르는지를 `tests/test_page_guide_theme.py` 가 본다.
  - 생성기 `scripts/build_page_guide.py` 가 앱 사본을 띄워 찍고(`page_guide_capture.py` + 페이지 도우미
    `page_guide_helpers.js`, Playwright 는 저장소 밖) 조립한다(`page_guide_core.py` — 자르기 · 상자 % · 덮어쓰기 ·
    매개값 · 리뷰 한 줄). `--example` 은 `git archive` 사본 + 합성 시드(`scripts/guide_example_seed.py`), `--internal` 은
    런북 6-3 사본 트리에서만 돈다. 결과는 늘 저장소 밖(`--dist`)에 쓰고, 예시판은 사람이 정본 자리로 복사해 커밋한다.
  - 사내 1단계는 쓰기 등급(`writes`)이 사슬에 `db` · `shared` 인 상태를 건너뛰고 예시 그림으로 대신하며, 사본 두 DB 의
    크기 · sha256 이 앞뒤로 같아야 한다. 「앞」은 그 `--work` 의 첫 촬영 앞에 적은 기준 지문(`db_baseline.json`)이고, 같은
    `--work` 로 다시 돌 때도(`--states` 여부와 상관없이) 그것과 견줘 사본이 이미 다르면 앱을 띄우지 않고 멈춘다 — 바뀐 DB 를
    새 기준으로 삼지 않는다. 앱 오류 · 예외로 멈출 때도 판정을 `run.json` 에 적는다. 점검기 `scripts/check_page_guide.py` 가
    같은 리뷰 한 줄을 다시 낸다.
- `src/capa_simulation/components/print_button.py` — 헤더 툴바의 `Print` 버튼 스크립트다(감춘 ⋮ 메뉴의 인쇄를
  대신). 실행 중이면 멈출 때까지 기다렸다 인쇄하고, 어두운 테마면 `DARK_PRINT_CONFIRM` 으로 먼저 묻는다.
- `src/capa_simulation/components/plotly_touch_scroll.py` — 칸 선택(`on_select`)을 켠 Plotly 그림 위에서 시작한
  터치가 화면을 스크롤하게 하는 스크립트다. 대상 key 는 `app.py` 의 `CELL_SELECT_CHART_KEYS` 다.
- `src/capa_simulation/components/intro_overlay.py` — 탭을 처음 연 사용자의 첫 로딩을 덮는 입장 화면이다. 다
  그려지면 `Detail`(원래 화면)·`Summary`(최신 공식버전 여섯 달 요약)로 들이고 같은 탭에서는 다시 띄우지 않는다.
  Summary 머리 줄 Detail 왼쪽의 ← 가 입장 화면(커버)으로 되돌린다 — 장면 메시지 `summary-off` 가 차트를 걷고 웨이퍼
  색·그늘을 입장 모습으로 돌리며, 다시 보낼 자리에서 `summary-on` 을 대신한다. 커버 셋째 단추 `Introduce` 는 40초
  티저(`intro_overlay_assets/capa-teaser.html`, `INTRODUCE_TEASER_PATH`)를 오버레이 안 전체 화면 틀(blob 주소)에 띄운다
  — 단추에서 원이 퍼지고 ←·Esc 는 그 단추로 접히며, 티저 머리 `Detail` 은 곧장 앱이다. 셋 모두 티저의 `TEASER.pause()`
  로 재생을 멈춘다 — 티저는 재생 때 남은 소리를 미리 잡아 두므로 층만 숨기면 40초 끝까지 소리가 난다. 다시 열면 멈춘 자리에
  서 있고 티저 안 `Space` 로 잇는다. 티저가 덮은 동안 장면 워커는 쉬고, Summary 처럼 들어갈 준비가 끝나면 선다. 루트
  `index.html`(GitHub Pages 발표 덱)은 앱이 쓰지 않는다.
  - Components v2 하나이고 자산은 `intro_overlay_assets/`(`intro.html`·`intro.css`·`intro.js`)다. 움직임은 워커
    OffscreenCanvas 에서 돈다 — 워커로 가는 `scene()`·`summaryGrid()` 는 그 파일의 다른 이름을 쓰지 않는다.
  - 등록 JS·`data` 는 회차마다 같고 색은 테마와 무관한 `tokens.INTRO_PALETTE` 다. 파이썬으로 가는 길은
    `intro_summary` 의 trigger 둘뿐이다 — 「준비 중」 GAP 다시 받기(`refresh`)와 Introduce 티저 받기(`teaser`).
  - 부분 글꼴 둘(`archivo-capa.woff2`·`archivo-capa-number.woff2`, `OFL.txt`)에 없는 글자를 쓰면
    `FONT_SUBSET_TEXT` 를 고치고 다시 만든다. 심볼 넷(`static/icons/capa_mark.svg` 포함)은 `test_intro_overlay` 가 맞춘다.
- `src/capa_simulation/components/intro_summary.py` — 입장 화면 Summary 의 값(최신 공식버전 요약 + 토글 셋
  `toggles`)과 Introduce 티저 칸(`teaser`)을 `capa_intro_summary` 로 보내고 사이드바 앱 이름 라벨을 세운다. 계산은
  `services/official_summary.py`.
  - 티저 본문(약 1MB)은 입장 화면이 `teaser` trigger 로 달라고 한 회차에만 읽어 싣는다(`teaser_payload`) — 받은 값
    JS 가 `teaser` 를 떼어 따로 넘기므로 워커로 가는 요약에는 티저가 없다. Streamlit 정적 경로는 HTML 을 글자로 보내
    쓸 수 없어 이 길이다.
  - 모든 페이지 앞에서 돌므로 어떤 예외도 내보내지 않는다(`available: false` 와 까닭). 공식 리비전의 결정적
    키로 HOME 과 같은 캐시를 쓰고, 판정 기준은 공용 프로필(`load_global_securement_threshold`)이다.
  - 서버 캐시는 요약(`get_intro_summary_payload`)과 토글 몫(`simulation_cache.shared_intro_toggle_store`) 둘이다.
    GAP 몫이 없으면 「준비 중」으로 보내고 페이지 뒤 `warm_intro_summary` 가 만든다.
  - 확인 주기는 `RECHECK_SECONDS` 이고 무효화는 `forget_intro_summary_check`(`tests/test_summary_recheck_paths.py`)다.
    확인 때 본 `latest_official_revision` 을 머리 띠가 읽는다(이름까지 든 같은 값 `latest_official_identity` 는 HOME 공식
    칩). 라벨 id 는 `intro_overlay.SUMMARY_LABEL_ID` 하나다.
- `src/capa_simulation/services/official_summary.py` — Summary 가 그리는 공식버전 6개월 요약(생산계획·B/N·부족
  대수·제품 비중)의 순수 계산이다. HOME 토글 기본값과 같은 화면이고 B/N 은 HOME 과 같은 순위 함수다.
  부족 대수는 B/N 공정이 그 달 실효 경고 기준까지 모자란 정수 대수다(6장 「경고 기준 필요대수」와 같은 식).
  - 토글 값은 `build_advance_summary`(HOME 「선행 B/O」와 같은 차례)·`build_comparison_summary`(선행 전 − 비교)다.
- `src/capa_simulation/services/plan_gap.py` — 계획 증감 글자(선행 B/O 전후·비교 GAP)의 형식과 0 근처를 적지
  않는 규칙(`GAP_EPSILON`·`visible_gap`·`format_gap`)이다. HOME `home_lob_figures` 와 Summary 가 함께 쓴다.
- `src/capa_simulation/components/admin_dialog.py` — Admin Area 편집 탭들이 함께 쓰는 팝업 칸
  (`admin_area_open_dialog`) 하나를 여닫는 콜백이다. 탭마다 칸을 두면 한 회차에 팝업이 둘 뜰 수 있다.
- `src/capa_simulation/components/app_header.py` — 맨 위 띠에 이 세션의 적용 시나리오 두 줄과 진행 막대 자리를
  싣고, 껍데기 스타일(⋮ 메뉴·Deploy·제목 링크 감춤, 사이드바 접기 버튼, 인쇄 규칙)을 보낸다.
  - 두 줄은 `stHeader` 가상요소의 글자다. 회차마다 DB 를 보지 않고 세션에 떠 둔 `active_scenario_label`·
    `intro_summary.latest_official_revision` 만 읽는다(`tests/test_app_navigation.py`). 사용자 글은 `css_string` 으로
    이스케이프한다. 설비 시나리오를 읽는 화면은 아랫줄 끝에 「설비 시나리오 · 운영 일정 · r12 · 공식 v3」(상태 차례는 사이드바
    배지와 같다 — 「가정 배치」 포함)을 단다 — 꼬리는 페이지가 정해 `refresh_equipment_header` 로 그 회차에 한 번 더 보낸다(9장).
  - `app.py` 가 입장 화면 요약 뒤에 한 번 부르고, 껍데기 스타일(`render_shell_style()`)은 부트스트랩 앞에서
    보낸다. 인쇄 규칙은 그 안 `@media print` 한 덩어리다(탭 줄도 뺀다). 화면 덩어리(`@media screen`)는 둘이다 — 화면
    탭 줄을 머리 띠 밑에 붙이는 sticky(`PAGE_TABS_SELECTOR`, z-index 100 — 펼침 목록·팝업 아래)와 큰 제목 칸 sr-only
    (`PAGE_TITLE_SELECTOR`). 인쇄에는 제목이 보인다.
  - 툴바 비움 폭과 진행 막대 자리(`_status_slot_css`)는 툴바 실측값이다(`tests/test_app_header.py`).
  - 회차마다 소켓으로 다시 가는 스타일이라 CSS 안에 주석을 두지 않는다 — 규칙 설명은 그 조각 바로 위 파이썬 주석이다
    (9장 「스크립트와 컴포넌트」).
- `src/capa_simulation/components/typography.py` — 본문의 페이지 제목·상자 제목·큰 숫자에만
  `tokens.FONT_FAMILY_DISPLAY`(`CapaDisplay`)를 거는 앱 전체 서체 스타일이다(자리 표 `docs/design_system.md` 1-1).
  - 글꼴(`static/fonts/archivo-700.woff2`·`archivo-800.woff2`)은 정적 서빙(`config.toml`)의 상대 경로로 받는다 —
    `static/` 밖이면 404 다. 색 없는 고정 문자열이라 부트스트랩 앞에서 매 회차 보낸다(`tests/test_typography.py`).
- `src/capa_simulation/components/accent_button_style.py` — 강조색으로 칠한 Streamlit 단추(`kind="primary"`·
  `"primaryFormSubmit"`, 잠긴 단추 빼고)와 `st.multiselect` 고른 칩(`[data-tag]`, 잠긴 상자 빼고)의 글자색을 그 회차
  테마의 `tokens.ACCENT_TEXT` 로 다시 건다(`docs/design_system.md` 2-2).
  - Streamlit 1.63 은 칠한 단추·칩 글자를 늘 흰색으로 쓰고 그 색을 정하는 테마 칸이 없다 — 어두운 테마의 밝은 강조색
    (`#2DD4BF`) 위 흰 글자는 1.86:1 이었다(표준 목표 「가용설비 붙여넣기」, 2026-10-25 E2E · 표준 대비 재공 현황 조회
    조건 칩, 2026-10-26 E2E r3). 밝은 테마는 흰 글자 그대로다. 잠긴 multiselect 는 콤보상자 뿌리(`stMultiSelect`
    바로 아래 칸)에 `data-disabled` 가 서고 칩이 흐린 바탕·흐린 글자라 고르지 않는다.
  - 테마 토큰이라 `app.py` 가 `theme.begin_run()` 뒤·부트스트랩 앞에서 매 회차 보낸다(`tests/test_accent_button_style.py`·
    `tests/test_app_navigation.py`). HOME 칠한 주요 Case 칩의 같은 색 규칙(`home_main_case_chips.chip_style`)은 칩 모양
    규칙과 함께 그대로 둔다.
- `src/capa_simulation/components/app_credits.py` — 앱 이름·버전·빌드일과 개발 팀·문의처 두 줄을 모든 화면
  사이드바 바닥 카드(`APP_CREDITS_KEY`)로 보인다. 값의 근거는 `settings.py` 다.
  - 그리는 것은 캡션뿐이고 자리·바닥 고정·면은 `sidebar_style.py` 가 건다. key 는 조건 카드 접두어를 품지 않는다.
- `src/capa_simulation/components/sidebar_style.py` — 탐색 그룹·활성 경로·`Support` 상자 key 와 현재 테마로
  사이드바 스타일 문자열을 만든다. 위젯 생성·HTML 주입은 하지 않는다.
  - 접두어·구역 제목 선택자는 선언 모듈(`sidebar_status`·`navigation.SIDEBAR_SECTIONS`)에서 읽는다 — 빌더에 필수
    인자를 더하지 않는다(`tests/test_sidebar_stylesheet.py`). 선택자가 1.63 DOM 에 기댄다.
  - 화면을 옮길 때마다 소켓으로 가는 시트라 CSS 주석을 싣지 않는다(설명은 파이썬 주석, 9장 「스크립트와 컴포넌트」).
- `src/capa_simulation/components/column_filter.py` — 분류 컬럼별 다중선택 필터와 초기화 버튼이다. 거른
  프레임을 돌려준다.
  - `value_labels` 는 표시만 바꾸고 값·세션 저장값은 원본이다. 표시명 칸은 `ProcessLabels.unique_format_func` 로
    가르고 `prune_list_selection` 으로 되쓴다. 카드가 없는 회차에는 `apply_column_filters` 가 세션 선택만 읽는다.
  - 걸러도 모든 행이 남으면(「Select all」 로 다 고른 중간 상태) 원본 사본을 돌려준다. `.loc` 는 모두 참인 마스크에도
    `RangeIndex` 를 일반 `Index` 로 바꾸는데, `st.data_editor` 신원이 인덱스 꼴을 품어 새 위젯으로 서고 표 전체를 다시
    보낸다(`tests/test_column_filter.py`).
- `src/capa_simulation/components/process_labels.py` — 원본 공정명을 화면 표시명으로 바꾸는 유일한 지점이다
  (규칙은 8장 「화면은 표시명, 파일은 원본」).
  - `ProcessLabels.frame` 은 화면용 복사본, `series` 는 행마다 바꾼 것과 같은 값·dtype 이다
    (`tests/test_process_label_series.py`). CSV 로 내보낼 프레임에는 쓰지 않는다.
  - `unique_format_func` 는 선택 상자 하나의 `format_func` 로 겹친 글자를 「표시명 (원본)」·「 (2)」로 가른다.
  - `category_axis` 는 공정을 범주 축에 늘어놓는 그림의 범주 값(원본)과 눈금·hover 글자(표시명)다(8장 ③).
    `ProcessLabelFormatter` 는 값을 글자로 주고받지 않는 자리(버튼·Figure)용이다.
  - `ProcessLabels.version` 은 HOME Figure 캐시 키 원소이고 계산 캐시 키·`content_token` 에는 넣지 않는다.
- `src/capa_simulation/components/process_rename_management.py` — Admin Area `Proc Rename` 탭. 공용 공정 표시명의
  CSV·Excel 붙여넣기·직접 편집과 저장이다. 저장은 공용 프로필 교체이고 리비전을 만들지 않는다.
  - 직접 편집 저장은 버전 대조(`BASE_VERSION_KEY` → `expected_version`, 어긋나면 `ProfileVersionConflict`)다.
- `src/capa_simulation/components/display_order_management.py` — Admin Area `표시순서 관리` 탭. 공용 표시순서
  규칙의 검증·CSV·붙여넣기·범위별 직접 편집과 원자 교체다. 저장은 공용 프로필 교체이고 리비전을 만들지 않는다.
- `src/capa_simulation/components/scenario_edit_bar.py` — 편집 화면 원본의 토큰(`source_token` — 기준정보 버전·
  리비전·조회기간·줄 차례 지문)과 원본이 바뀌면 편집기를 비우는 `reset_editors_on_source_change` 다. 생산 계획·기준 정보가 쓴다.
  - 줄 차례 지문만 바뀌어 적용 전 편집을 버린 회차는 결과(`SourceReset.row_order_dropped`)를 화면이 탭 묶음 위 알림 칸에
    한 번 알린다(`show_row_order_reset`). 앞 토큰이 없으면(첫 회차·시나리오 전환이 지운 뒤) 알리지 않는다. 줄 위치로 남지
    않는 상태(PKG PLAN 붙여넣기 대기와 그 표 위의 편집, 기준 정보 STEP 상자)는 `order_free_keys` 로 넘겨 차례만 바뀐 회차에 남긴다.
  - 화면이 스스로 적용한 편집은 `mark_own_change` 로 적어 그 적용이 건드린 편집표만 비운다. 편집 되돌리기는
    `components/scenario_status.py` 의 팝업이 맡는다.
  - `register_pending_edits` 로 화면이 제 편집표·붙여넣기 대기를 적고 사이드바가 `pending_edit_labels` 로 앞 회차
    목록을 읽는다. `page` 는 파일 이름 리터럴이다(`tests/test_pending_edit_registry.py`). 화면 탭 줄은 같은 규칙의
    화면별 판(`pending_edit_pages` — 편집표 몫·붙여넣기 대기 몫)으로 점과 떠날 때 물을 것을 정한다.
- `src/capa_simulation/components/roadmap_panel.py` — 업무 활용 목적·부서별 Action Item·로드맵을 기본 닫힌
  상자로 그린다(지금은 실행 관리 머리).
- `src/capa_simulation/components/page_link.py` — 다른 화면으로 건너가는 링크다. `st.navigation` 이 없는 단독
  실행(테스트)에서는 문구로 물러선다(`fallback` 으로 그 글을 줄 수 있다 — 「도면에서 보기」). `disabled`·`help` 는
  `st.page_link` 그대로다 — 꺼진 링크가 자리를 지키고 풍선이 까닭을 말한다(공정 Capa 상세 머리 「이 공정 제약 시뮬레이션」).
- `src/capa_simulation/services/product_type.py` — 제품타입(HBM·EDP-TSV)이 가르는 `WF 구분` 규칙의 단일 근거다.
  두 값 집합을 일부러 따로 선언하고 EDP-TSV 의 `Top` 을 `Top_e` 로 가르는 `apply_edp_wf_division` 을 갖는다.
  - 변환 지점은 `core_data_derivation.build_q_core_data` 한 곳이다 — 두 층에서 바꾸면 조인 한쪽만 바뀐다.
    입력·DB 에는 `Top_e` 가 없어 표시순서 규칙은 `display_order._with_edp_top_rule` 이 파생한다.
  - 원천 표기는 대문자 `TOP` 이다 — 값 대조는 `frame_contracts.match_key` 로 하고 저장·화면에는 원천 표기를 쓴다.
- `src/capa_simulation/services/performance_actuals.py` — 효율·UPEH·수율 세 실적 화면이 공유하는 Gap·우선순위
  계산과 합성 데모다(규칙은 6장). Gap 의 뜻은 `MetricSpec` 이 갖고 데모는 `dynamic_capacity.DEMO_PROFILES` 다.
- `src/capa_simulation/services/legacy_comparison.py` — 원천에 보존된 기존 결과와 신규 계산을 같은 단위로
  대조한다(실행 `scripts/compare_legacy_results.py`).
  - 기존 컬럼은 계획 한 줄 × `WF 구분` 에서 접은 뒤 대조 키로 합산한다 — 대조 키에서 접으면 서로 다른 계획
    줄이 뭉개진다. 정식 대조 `COMPARISONS` 는 Wafer·Density·Chip(계획 줄 키) 셋이다.
  - 사내 실데이터는 분포·개수로만 가른다(`difference_distribution`·`ratio_groups`·`scaling_check`·
    `fold_route_cells` 등 → `scripts/inspect_real_data_checks.py`).
  - 지표를 더하면 두 스크립트의 계산 사전(`LOAD_BUILDERS`)도 더하고, 산식이 바뀌면 `FORMULA_INPUTS` 도 고친다.
    환산 UPEH 는 `hourly_rate` 가 `unit_capacity.converted_upeh` 를 부르고, `time_agreement`(UPEH × ST ÷ 60)는
    그 모듈의 `ST_MINUTES_PER_HOUR` 를 쓴다 — 식을 복제하지 않는다.
- `src/capa_simulation/components/tab_state.py` — 열린 탭을 서버가 알게 하는 `stateful_tabs` 와 판정
  `tab_is_hidden` 이다. 차트가 든 탭은 반드시 이것으로 만든다 — 숨은 탭의 Plotly 표는 글자 폭이 0 으로 재진다.
  다른 화면에서 그 화면의 탭 하나로 보낼 때는 기억 칸만 적는다(`remember_open_tab` — 위젯 키는 쓰지 않는다. 안쪽 탭이면
  바깥·안쪽 기억 칸을 함께 적는다). 탭 안의 탭은 바깥 본문 안에서 늘 부르므로 바깥이 숨어도 안쪽 고른 탭의 `open` 이 참이다 —
  본문 갈래는 둘을 합친 `NestedTab` 으로 판정한다(가용설비 현황 Summary).
- `src/capa_simulation/components/editor_state.py` — 편집표에 고친 것이 남았는가(`editor_has_edits`)와 편집을
  브라우저까지 버리는 초기화(`discard_editor`)다.
  - 키가 있는 편집표는 모두 세대 번호를 붙인 `editor_widget_key` 로 그리고, 버릴 때 세션을 `pop` 하지 않고
    `discard_editor` 를 부른다 — 세션만 지우면 브라우저가 옛 편집을 다음 회차에 되보낸다.
- `src/capa_simulation/components/pick_edit_table.py` — 고름 하나와 이름(·순서) 칸을 바로 고치는 편집표(시나리오 관리
  목록·리비전 표)의 미저장 초안(`TableDraft` — 이름·이름 기준·화면 차례·차례 기준·고른 행, 모두 행 id)과 접기·위젯
  key 다. 이름 기준(`name_base`)은 그 칸을 처음 고친 편집이 붙은 표가 보인 저장 이름이고(`ShownTable.names`),
  `changed_names` 가 그것을 비교 후 쓰기의 대상으로 돌려준다.
  - 그리기 **전에** `settle_table` 이 지난 회차에 그린 차례(`ShownTable`)로 브라우저 편집을 id 로 접고, 지금 저장된 행에
    맞추고(`reconcile`), 두 줄이 골라지거나 순서 칸이 바뀌면 초안을 먼저 적고 세대를 올려 새 위젯으로 세운다 — 본문
    `st.rerun()` 이 없다. 위젯 key 에 행 차례 지문을 실어 차례가 바뀌면 옛 위치 편집이 다른 행에 붙지 않는다(9장).
  - 순서 칸 숫자는 그 자리로 끼워 넣기(`move_row`)라 칸은 늘 1..n 이다. 단추 콜백은 `peek_table`(쓰지 않는 접기)로
    누른 회차의 편집까지 읽는다. `table_has_edits` 는 초안에 이름·순서 편집이 남았는가(세션만 — 화면 탭 줄의 점)다.
- `src/capa_simulation/components/tab_marks.py` — 적용하지 않은 편집이 남은 탭 이름 옆 점(`mark_pending_tabs`,
  판정 `editor_has_edits`, 색 `PENDING_MARK`)이다. 비공식 선택자라 판올림에서 바뀌면 점만 안 보인다.
- `src/capa_simulation/components/status_metric.py` — 조치가 필요한 지표에 상태색 왼쪽 띠를 붙인 metric
  카드다(`tone="neutral"` 이면 기존 카드). `metric_row` 는 카드를 같은 폭·높이로 세우고 모자라면 줄을 접는다. 둘 다
  서식을 스타일만 든 `st.html`(이벤트 칸)로 보내는데, 팝업 본문처럼 이벤트 칸 자리 수가 갈래마다 같아야 하는 곳은
  `emit_style=False` 로 부르고 `metric_row_style`·`status_metric_style` 을 보이는 HTML 과 한 `st.html` 에 싣는다.
- `src/capa_simulation/components/table_toolbar.py` — 표 제목·부가 설명·CSV 내보내기 한 줄과 표 도구 막대 앞 띄움
  (`toolbar_clearance()` — 숫자는 `TABLE_TOOLBAR_CLEARANCE` 하나, 다른 이름은 그 별칭)이다. `st.download_button` 은
  여기서만 부르고 라벨에 아이콘을 섞지 않는다(테스트가 잡는다, 9장 「표 도구 막대」).
- `src/capa_simulation/components/monthly_table_base.py` — 두 월별 Plotly 표가 공유하는 상수·텍스트 폭·분류 폭
  (`classification_widths`)과 `go.Table` 두 벌 조립(`build_split_table_figures`)이다. 행 모델·면색만 표마다 다르다.
  - 머리글 글자는 `go.Table` 밖 글자 trace(data[1], `plotly_layout.table_text_layer`)이고 띠는 `table_header_band`
    도형이다 — `go.Table` 머리글은 값 `""`·면 투명이다. 표 칸에 마크업(`<`·`&`·`>`)을 두지 않는다: 마크업 칸은 Plotly 가
    칸마다 그린 뒤 재서 옮겨 열 수만큼 브라우저 스타일 계산이 돈다(합성 표본 표준 목표 131주 표 long task 1.6s 의 대부분,
    `tests/test_plotly_fast_path.py::test_table_cells_carry_no_markup`). 월 면색은 한 열 `[month_row_colors]` 다(Plotly
    가 마지막 열을 되풀이한다). 분류 Figure 폭은 `column_widths` 합(px)으로 본다.
  - spec 은 `plotly_layout.figure_from_spec` 이 검증 없이 세우므로 Plotly 정규형 dict 다
    (`tests/test_plotly_fast_path.py`). 격자 도우미는 `append_layout_items` 에 모으기만 하고 표 모듈이
    `flush_layout_items` 한 번으로 반영한다(`tests/test_monthly_table_grid.py`).
- `src/capa_simulation/components/scroll_shell.py` — 월별 표·HOME·재공 현황이 함께 쓰는 가로 스크롤 상자와 고정 폭
  캔버스, 분류 칸 폭을 px 로 못박는 `split_scroll_columns_style` 이다. key 를 바꾸면 CSS 가 끊어진다. 폭을 못박지 않는
  변형(`min_width_scroll_rules` · `min_width_scroll_canvas` — 캔버스에 가장 좁은 폭만 걸어 넓으면 칸을 채우고 좁을 때만
  스크롤, 규칙은 호출자 `<style>` 에 섞는다)은 제약 시뮬레이션 그래프가 쓴다. 셸 CSS(`overflow-x: auto`)를 다른 모듈에
  손으로 적지 않는다(`tests/test_scroll_shell.py`).
- `src/capa_simulation/components/month_editor.py` — 월별 Wide 기준정보를 탭 안에서 편집하는 `data_editor` 와 표
  위 작업 줄(적용·Excel 붙여넣기 팝업·편집 취소·변경 개수)이다.
  - 필터(사이드바 `표 조건` 카드)는 보기만 좁히고 저장은 전체다 — 편집값은 `merge_edited_months` 로 전체 표에
    되머지하고 붙여넣기 팝업(`render_reference_clipboard_form`)·왕복 CSV 에도 필터 이전 전체 표를 넘긴다.
  - 적용 안 한 편집이 있는 표는 탭이 닫혀도 그리고 필터를 잠근다. 그릴지와 양식을 만들지는 `editor_will_render`
    하나가 정한다. 결과·오류는 버튼 아래 `editor_notice` 자리에 쓴다(페이지 `reference_data.py` 가 받아 쓴다).
  - 큰 표(`CLASSIFICATION_STYLE_MAX_CELLS` 초과)는 되풀이되는 글자 분류 컬럼만 화면 사본에서 category 로 보내고
    (`_compact_dimensions`), 편집표가 돌려준 표에는 원본 분류 컬럼을 다시 끼운 뒤(`_restore_dimensions`) 되머지한다.
    되머지 키(`astype(str)`)는 원본 dtype 으로 만든다 — category 결측은 `'nan'`, StringDtype 결측은 `'<NA>'` 라 섞으면
    편집이 버려진다.
  - `process_labels` 를 import 하지 않는다(표시명은 `value_labels=`). 분류 칸 회색 배경은 `classification_styled`
    하나가 칸 수 상한까지만 입히고 `load_conversion.py`·`reference_data.py` 도 쓴다(`tests/test_classification_style.py`).
- `src/capa_simulation/services/revision_compatibility.py` — 저장된 리비전이 현재 계산 계약으로 쓸 수 있는지
  **불러오기 전에** 판정한다(활성화 뒤에 죽으면 되돌릴 길이 없다).
  - 지금 막는 것은 `STEP_SEQ`·`MCP_SEQ` 가 빈 저장분이다. 값을 추정해 채우지 않는다.
- `src/capa_simulation/services/past_data.py` — 적재 시점 이전 과거 구간 입력의 정규화·검증과 계산 결과 병합이다.
  산출하지 않는다 — Capa 는 확보율에서 곧장 나오고 B/N 순위는 확보율 오름차순이다.
  - 같은 달이 양쪽에 있으면 계산이 이긴다. `display_month_range` 는 HOME 계산 캐시 키의 달이라 HOME 과
    필요 단축 일정이 같은 함수를 쓴다. 빈칸을 0 으로 삼키지 않는다(`_BLANK_AS_ZERO` 가 칸별 규칙).
- `src/capa_simulation/components/past_data_management.py` — HOME `Past Data` 탭. 한 버전을 공유하는 세 표를
  붙여넣기 팝업(`PAST_DIALOG_KEY`)으로 세션에 모았다가 한 번에 저장한다(부분 저장 없음).
  - 저장은 저장된 표를 통째로 바꾼다 — 그 경고(`PAST_REPLACE_NOTICE`)는 팝업·버튼 툴팁·캡션에 남긴다.
- `src/capa_simulation/services/process_selection.py` — B/N 집계에 포함할 공정을 저장값·현재 옵션·이 세션이 아는
  공정에서 정한다.
  - 기준 없는 첫 렌더(`seen=None`)는 저장된 포함 목록을 그대로 믿는다(`seen=[]` 와 다르다). 아는 공정은
    쌓이고(`remember_known_processes`), 선택지에 없는 공정은 포함 목록에서 지우지 않는다(`visible_processes`).
- `src/capa_simulation/services/process_picker.py` — 조회기간 최종 확보율을 공정별 최소값·최초 동률 월·유효 월
  수로 요약해 미달·충족·판정 없음 구역을 정한다(입력 순서·원본 키 보존).
  - 경계는 HOME 과 같은 `SecurementThresholds.status` 이고 충족은 유효한 모든 달이 확보일 때다. 소요·가용대수로
    확보율을 다시 계산하지 않는다.
- `src/capa_simulation/components/process_picker.py` — 위 요약을 세 구역의 공정 버튼으로 그린다(긴 표시명은
  한 줄 말줄임, 자동 갱신이 뺀 공정은 `marks` 표지).
  - 콜백·위젯 키에는 원본 공정명을 쓴다. 설명 풍선은 `help` 가 아니라 순번 칸(`home_bn_tile_<i>`)의 CSS `:hover` 다.
- `src/capa_simulation/services/month_columns.py` — 월 축과 연간 Total 열의 규칙이다. Total 은 1~12월이 모두
  조회범위 안인 해만 갖고 그 해 12월 바로 뒤에 들어간다.
  - 축은 하나다 — 표·차트·스크롤 폭이 같은 라벨 목록을 본다. 월 칸 표기 `YY.MM` 은 `month_label` 한 벌이다.
    `leading_past_column_count` 는 과거 구간의 연속된 앞머리만 센다(`build_past_month_labels` 와 함께 면색·스크롤 근거).

- `src/capa_simulation/components/home_preference.py` — HOME `LOB 표시 조건` 카드·`Capa LOB 현황` 제목 줄과 `Preference`
  편집기 여덟을 그려 공용 프로필에 저장한다. 「비교 시나리오」 바로 아래에 「주요 Case」 상자(`home_main_cases`)를 세운다.
  - 토글은 모두 여기서 `value=` 없이 만들고 기본값은 칸이 없을 때만 심는다(`tests/test_scenario_activation.py`).
  - 저장은 **버전 대조**이고 월별 값은 보이는 달만 갈아 끼운다(`services/monthly_amount.py`). 주요공정 프리셋은 묶음
    전체 교체라 편집 카드(프래그먼트)가 회차마다 캐시에서 다시 읽는다(`tests/test_home_key_process_fragment.py`).
    프리셋 「기본으로」·「삭제」 의 알림은 빠른 둘째 누름(잠긴 단추에 닿아 아무것도 하지 않는 회차)에도 다시 선다
    (쓰기 직후 `write_guard.note_notice` 로 적고 `flash.render_flash` 가 다시 그린다, `tests/test_key_process_preset_messages.py`).
  - `Past Data 포함` 을 끄면 과거 세 표를 행만 비운 사본(version 0)으로 바꾼다 — 끈 분기를 곳곳에 심지 않는다.
- `src/capa_simulation/components/home_main_cases.py` — HOME `Preference` 의 「주요 Case」 상자(2026-10-23 사용자 요청).
  HOME 슬롯은 셋 고정이고 슬롯 1 은 지금 최신 공식버전이라 상자 첫 줄에 글로만 보인다(공식 지정은 시나리오 관리). Case1·
  Case2 마다 「시나리오」·「리비전」 상자를 두고(넓으면 두 칸, 좁으면 위아래) 고르는 것이 곧 저장이다(공용 프로필 `0036`).
  - **공용 프로필이 정본이고 상자는 거울이다.** 비교 시나리오(세션 우선)와 달리 회차마다 프로필 값을 위젯 앞에서 상자에
    적는다 — 남의 지정·이름 바꾸기가 다음 회차에 보이고 브라우저가 옛 글자를 되보내도 지정이 바뀌지 않는다(9장).
  - 시나리오 콜백은 그 시나리오 첫 리비전과 **짝으로** 저장한다(위젯 기본값은 `on_change` 를 부르지 않는다). Case 하나만
    바꾸고 다른 Case 는 같은 쓰기 트랜잭션에서 옮겨 적는다. 같은 짝·라벨 글자는 쓰지 않는다.
  - 리비전 콜백은 그 Case 의 지금 시나리오가 화면이 본 시나리오일 때만 쓴다(`expected_scenario_id` — 같은 쓰기
    트랜잭션에서 대조). 낡은 화면이 짝을 통째 써서 남의 시나리오 고름을 알림 없이 되돌리지 않게 하고, 어긋나면 알린다.
  - 본문의 쓰기는 둘뿐이다 — 목록에 없는 시나리오를 가리키는 Case 비우기(조건부 UPDATE, 한 번 알림 + 출처 칸에 까닭),
    그 시나리오 것이 아닌 리비전 칸을 첫 리비전으로 메우기(본 version 대조). 둘 다 프로필만 보고 정해져 세션끼리
    뒤집지 않는다.
  - **숨은 `Preference` 회차는 DB 를 읽지도 쓰지도 않는다**(`owner_tab`) — 마지막으로 보인 화면 재료
    (`MAIN_CASE_VIEW_KEY`)로 위젯을 그대로 그린다(탭을 누른 순간 보이는 것이 그 화면). 세션 첫 회차가 숨은 탭이면 한
    번만 읽고 쓰지 않는다. 위 두 쓰기와 그 알림·콜백 실패 알림은 보이는 회차로 미룬다.
  - 비운 Case 는 세션 API 로 `None` 을 적어 브라우저가 자리표시를 띄우므로 `placeholder` 를 비우기 선택지 글자로 준다
    (주지 않으면 영문 「Choose an option」). 그 글자는 같은 이름의 시나리오가 있으면 「지정 안 함 (비움)」 으로
    비켜 선다(`unset_choice_label` — 1.63 은 같은 글자를 첫 선택지로 읽어 그 Case 를 비울 수 없었다).
  - Case1·Case2 가 같은 짝, Case 가 공식버전과 같은 리비전이면 저장하고 캡션으로 알린다(`main_case_overlap_notes`).
    HOME 제목 줄에서 슬롯을 고르는 칩은 `home_main_case_chips` 다(같은 `services/main_cases.main_case_slots` 를 쓴다).
- `src/capa_simulation/components/home_main_case_chips.py` — HOME 제목 줄 끝의 주요 Case 칩 셋(2026-10-23 사용자 결정 —
  시안 C · 동작 (가)). 칩 글자는 `공식 vN`·`Case1`·`Case2` 뿐이고 시나리오·리비전은 단추 `help` 풍선이 말한다(사람 글은
  `literal_markdown`). 지금 적용된 시나리오는 머리 띠가 말하므로 칩 옆에 적지 않는다.
  - **누르면 사이드바에서 그 리비전을 불러온 것과 똑같다** — `scenario_status.load_saved_revision` 을 **콜백**에서
    부른다(본문 `st.rerun()` 은 그 회차에 안 그린 위젯 값을 버린다 — 9장). 저장하지 않은 편집·적용 전 편집이 있으면
    곧바로 올리지 않고 사이드바 팝업을 그 짝으로 연다(`open_scenario_dialog_on` — 같은 확인 칸·같은 단추).
  - **콜백은 누르는 순간 슬롯을 다시 푼다** — 콜백 인자는 그린 회차의 값이라, 그사이 다른 세션이 Case 를 다시
    지정하거나 가리키던 시나리오를 보관하면 낡은 칩이 예전 Case·사이드바가 고를 수 없는 보관 시나리오를 올렸다. 칩은
    (슬롯 차례, 그린 짝)만 넘기고 콜백이 그리기와 같은 `_slot_chips_now` 로 지금 짝을 풀어 다르면 아무것도 올리지 않고
    제목 밑 칸에 알린다(`changed_slot_notice`).
  - 칠하기(primary)는 세션 활성 시나리오·**리비전까지** 같은 칩만이고, 저장하지 않은 편집이 있으면 칠하지 않는다(머리
    띠·사이드바 배지처럼 「미저장」이 먼저 — `painting_reference`). 칠한 칩을 편집 없이 다시 누르면 아무것도 하지
    않는다. 칠한 칩 글자색은 `tokens.ACCENT_TEXT` 다(어두운 테마 강조색 위 흰 글자는 1.9:1). 어느 칩도 칠하지 않으면
    칩 줄 **앞**에 회색 「슬롯 밖」 한 마디(풍선 없음) — 늘 그리고 슬롯 안이면 `visibility: hidden` 으로 감춰 자리를
    잡아 둔다(나타나고 사라질 때 칩이 밀리거나 칩 줄이 접히지 않는다). 칩 줄은 한 줄(`nowrap`)이다.
  - 미지정 Case 는 점선 칩이고 누르면 `Preference` 탭(탭 key 를 콜백에서 적는다). 가리키던 시나리오를 보관·영구 삭제하면
    저장소가 그 Case 를 비우므로 점선 칩이 된다. 잠금은 목록에서 찾지 못하는 짝(저장소 밖에서 고친 DB 등)과 공식버전
    없음뿐이다(풍선이 까닭).
  - 회차마다 DB 를 보지 않는다 — 공식은 `intro_summary.latest_official_identity`(머리 띠와 같은 세션 값), Case 는 주요
    Case 쓰기 세대를 키로 한 캐시 `persistence/cache.load_main_case_targets` 다. `tests/test_home_main_case_chips.py`,
    실제 `app.py` 배선과 둘째 회차 읽기 0 은 `tests/test_app_navigation.py`.
- `src/capa_simulation/services/main_cases.py` — 주요 Case 슬롯 셋(공식버전·Case1·Case2)을 (글자, 시나리오 id, 리비전 id,
  상태 `ok`·`unset`(미지정)·`missing`(사라짐))으로 내는 `main_case_slots` 와 겹침 안내 줄. Streamlit·DB·모델을 모르고
  읽기 전용 Protocol 로 필드만 받는다. 리비전은 `scenario_id` 로 그 시나리오 것인지 견준다.
- `src/capa_simulation/components/profile_caption.py` — 공용 프로필 버전 캡션 한 줄을 저장 화면 여덟에 한 규칙으로
  만든다. 모델을 import 하지 않고 읽기 전용 `@property` Protocol 로 세 필드만 요구한다.
- `src/capa_simulation/services/advance_load.py` — 선행 B/O 정규화와 월별 변동률(`기존 계획 ÷ 선행 반영 계획`)·역산.
  - 변동률을 확보율에 곱하고 Wafer 는 나눠 Capa·B/N 순위가 그대로다. 선행을 넣은 달 가운데 선행 반영 계획이 0 이하인
    달만 미적용으로 알린다.
- `src/capa_simulation/services/advance_shipment.py` — 선행 입고 실적 정규화·편집 병합과 LOB 칸 글자
  (`advance_shipment_notes`). 계산에 들지 않는 표시값이다.
- `src/capa_simulation/services/monthly_amount.py` — 월별 억Gb 한 칸 공용 프로필(선행 B/O·선행 입고 실적)의 정규화·보인
  달만 갈아 끼우는 병합·`{YYYYMM: 값}` 사전. 두 편집기가 같은 입력을 같게 저장하도록 규칙을 한 곳에 둔다.
- `src/capa_simulation/services/execution_capacity.py` — 확보율 보정(`execution`)의 정규화와 적용
  (`기준 확보율 + 증감/100`, %p).
  - 조정이 없어도 세 컬럼(`기준 확보율`·`확보율 증감`·`실행 비고`)을 늘 만든다. 음수는 0 에서 자르고
    (`clamped_execution_adjustments`) 짝 없는 행은 알리기만 한다(`unmatched_execution_adjustments`).
- `src/capa_simulation/services/top5_band.py` — B/N Top 5 막대의 값 대역(기본 50%~200%) 검증과 자르기. 대역은 확보율과
  떼어 공용 프로필에 둔다(달마다 같은 눈금).
- `src/capa_simulation/services/voc_board.py` — VOC 글·답글의 분류(`VOC_CATEGORIES`, 넷 고정)와 입력 검증.
  계산·시나리오에 매이지 않고, 인증이 없어 작성자는 직접 적는 이름이다.
- `src/capa_simulation/services/wd_window.py` — 공정별 Cut-off 로 한 달이 잡는 W/D 구간
  `(전월 말일 − cutoff, 당월 말일 − cutoff]` 를 만든다.
  - 반열린 구간·소수 Cut-off 내림·달력일 분모다 — 열두 구간이 한 해를 빈틈·겹침 없이 덮는 것이 유일한 안전장치다
    (`RUN_DAY` 를 쓰면 설비 DB 가 시뮬레이션 DB 를 읽는다).
- `src/capa_simulation/services/process_cutoff.py` — 공정별 Cut-off 입력 표의 계약·검증과 조회 사전(`cutoff_lookup`).
  없는 공정과 0 은 다르다 — 0 은 달력 월 그대로, 없으면 산출에서 빠지므로 화면이 `missing_cutoff_processes` 로 드러낸다.
- `src/capa_simulation/services/qual_deadline.py` — Qual 마감 계산기(2026-10-22, 10-07 계산기 한 장을 옮김)의 계산과
  화면·복사 글자. Cut-off·연도·직전 달 가용대수·월별 목표·신규 호기로 호기마다 Qual 완료 마감을 낸다. 어느 DB 도 열지 않는다.
  - 구간은 `wd_window` 그대로, 몫은 완료 다음 날부터다. 모자람 ≥ 1 이면 마감 = 구간 앞 경계(몫 1), < 1 이면 모자란 날 수만큼
    구간 끝에서 당긴 날(몫 = 일수 / 길이). 적은 차례로 꺼내고 남는 호기는 다음 달로, 목표를 비운 달은 판정하지 않는다.
  - 숫자 글자는 JavaScript `toFixed`·`Math.round` 와 같게 만든다(`to_fixed`·`js_round` — 0.125 → 「0.13」). 붙여넣기 칸은
    원본 `bulk-apply` 그대로다 — 공백뿐인 줄은 건너뛰고 앞 12줄, 첫 칸은 목표, 둘째 칸부터는 띄어쓰기로 이은 호기(`js_trim`).
    `tests/test_qual_deadline.py` 가 원본 스크립트를 node 로 돌린 값과 칸 글자까지 맞댄다(시험은 node 없이 돈다).
- `src/capa_simulation/services/shortening_filter_profile.py` — 필요 단축 일정 공용 조회 조건(설비 DB `0019`) 모델
  `ShorteningFilterProfile` 과 정규화·심기·`merge_filter_processes` 규칙. Streamlit·DB 를 모르고 값은 원본 공정명이다.
  `effective_filter_months`·`filter_month_window` 는 필요 단축 일정 시작·끝 월 칸의 심기를 **읽기만** 해 같은 달을 낸다(Space
  필요 단축 보기 — 세션 값은 인자로 받는다).
- `src/capa_simulation/services/floor_state.py` — Space 동·층 사용 상태(설비 DB `0029`, 2026-10-24 결정 S1~S6) 모델
  `FloorStates`(비활성 층만의 (동, 층, 사유 코드) 행 — `UNUSED` 사용 안 함·`NOT_LINE` 생산라인 아님)와 규칙. 저장 입구
  `prepare_floor_states`(30개 층·사유 둘만, 빈 값 = 사용)만 엄격하고 읽기는 관용이다(모르는 사유는 `inactive_label` 이
  「비활성」). 동 머리(`building_state`·`with_building`), 끄기 확인 대상(`newly_inactive` — 사유만 바꾼 층은 아님)과 층별 설비
  대수(`floor_unit_counts` — 도면 이탈 제외·레이아웃 Y/N 모두·설비키), 층 고르기 거르기(`selectable_floor_keys` — 연 층은
  남김, 설비 마스터 탭 칸 단위 `master_location_options` — 표에 있는 값은 남김, 짝 단위 `floors_by_building` — 표 `층` 칸
  정의의 `optionsBy` 로 실려 `grid.js` `choiceOptions` 가 그 줄의 동으로 좁힌다), 저장 미리보기 경고
  `inactive_floor_warnings`(막지 않음). Streamlit·DB 를 모른다. **설비 마스터 저장 검사(C1~C5·1F~6F)는 그대로다**(S5).
- `src/capa_simulation/services/shortening_baseline.py` — 필요 단축 일정 기준선(설비 DB `0021`) 모델과 규칙. 기준선은
  저장한 그때 계획을 얼린 고칠 수 없는 기록이다(`freeze_plan` → `ShorteningBaselineDraft`, `normalize_baseline_name`·
  `baseline_label`·`normalize_baseline_units`).
  - 설비 쪽 출처(`ShorteningEquipmentBasis` — 공통 rN · 설비 시나리오 이름 · 일정 rN · 공식 vN, 설비 `0027` 의 가리키는 칸
    넷)도 기준선에 싣는다. 기준선은 세션이 **공식 발행 쌍**일 때만 저장한다(E5 — 거부 까닭은 「가정 설비 시나리오」 와
    「발행하지 않은 리비전」 둘, `equipment_scenario_status.baseline_equipment_refusal`).
- `src/capa_simulation/services/shortening_progress.py` — 기준선과 지금 계획의 같은 목표 호기 표를 짝지어 시점·단축일수
  변동과 상태를 낸다(`compare_progress`·`summarize_progress`·`progress_export_frame`).
  - 짝짓기는 공정 안에서만 — 당긴 호기는 설비명끼리, 「추가N」은 차례끼리다. 지금 범위에 없는 기준선 공정은
    `지금 범위 밖`(해소 아님), 오늘보다 앞선 과거 필요 시점은 `필요 시점 지남` 으로 양쪽 증감에서 뺀다.
- `src/capa_simulation/services/shortening_watch.py` — 필요 단축 일정의 공정 진척 보드(`process_board`)·카드 차례
  (`board_order`)·기한 임박(`imminent_units`)·이행 지연(`delayed_units`)과 설비키마다 Qual 실적·상태·담당자
  (`unit_qual_status` — 캐시 래퍼 `get_unit_qual_status`). Streamlit·DB 를 모르고 쓰지 않는다.
  - 이행 지연 = 기준선 목표 Qual(과거 필요 시점) < 오늘인데 마스터 Qual실적이 비었거나 Qual상태가 「완료」 아닌 당긴 호기
    (모듈 하나라도 미완료면 미완료, 마스터에 없으면 지연). 가상 호기는 보지 않는다.
- `src/capa_simulation/services/monthly_equipment_availability.py` — 호기 생애주기 구간을 W/D 구간에 일수로 안분해
  월별·공정별·분류별 기여 대수를 만든다. 어느 DB 도 열지 않는다.
  - 상태는 바뀐 다음 날부터 기여하고 정지·반출/이설로 가용을 잃는 날만 당일부터 빠진다. 가용 소계는 `기존보유`·`가용`
    둘뿐이고(분류는 `집계분류`), `span_date_range` 는 첫 구간의 앞 경계부터 준다.
  - 대수 표와 호기 목록(`build_monthly_equipment_contributions`)은 같은 기여 줄(`_raw_rows`)에서 나온다.
- `src/capa_simulation/services/securement_cross_check.py` — 같은 소요대수에 Static(`RQ_EQP_AVBL`)과 설비 일정 기준
  가용대수를 각각 나눠 확보율 두 벌을 낸다(화면은 `cross_check_from_monthly`).
  - `calculate_securement_rate` 를 고치지 않고 가용대수 프레임만 바꿔 두 번 부른다. 설비 일정 쪽에 공정 자체가 없을 때만
    Static 으로 채워 `fallback_processes` 로 알린다. HOME·B/N 은 여전히 Static 을 본다.
- `src/capa_simulation/services/required_shortening.py` — 일정 기준 가용이 소요대수 × 목표 확보율에 모자란 공정·월마다
  신규 호기 Qual 을 며칠 당길지, 당길 호기가 없으면 가상 호기 「추가N」의 Qual 기한을 낸다. 어느 DB 도 열지 않는다.
  - 가용은 Static 대비 일정과 같은 길(`build_monthly_equipment_availability`), 소요는 `calculate_securement_rate` 다.
    같은 이름 공정만 맞대고 나머지는 목록(`required_only`·`missing_cutoff` 등)으로 돌려준다.
  - 늘어나는 몫은 엔진을 다시 돌리지 않고 기여일로 센다. 후보를 바닥 `max(구간 앞, 오늘)` 뒤에서 모자란 만큼만 당기고,
    한 달 상한을 넘은 가상 호기는 모두 걷는다(남기면 뒤 달 부족을 가린다).
  - 목표는 스칼라 또는 `MonthlyTarget` 이고 한 길로 계산한다(`tests/test_required_shortening_monthly_target.py`).
- `src/capa_simulation/services/upeh_assumption.py` — UPEH 가정(`UpehAssumption`·캐시 키 토큰 `UpehToken`)과 소요대수 ÷f
  사후 배수(`scale_required_equipment`·`scale_securement_rate` — 같은 확보율 함수로 다시 낸다), 닫힌 식 역산 둘
  (구간 안 단축 0·확보기준 미달 0, 80~150 밖은 갈래), 효과 한 줄(`effect_text` — 정수가 그대로면 「덜 당김」)을 낸다.
  - 선형 전제는 `tests/test_upeh_assumption.py` 가 `RQ_UPEH` 를 고쳐 다시 계산한 결과와 맞대어 지킨다.
- `src/capa_simulation/services/process_equipment_timeline.py` — 공정 Capa 상세의 설비 일정(참고)을 생산월 좌표로
  정리하는 순수 함수(`build_process_equipment_timeline`·`unit_events`·`dynamic_readiness`). DB·오늘을 보지 않는다.
  - 비가동 손실은 반사실(비가동을 비운 구간과의 차이)이라 경계 규칙이 엔진 그대로다. 시험 불변식:
    `기존보유 + 호기 가용 = 필요 단축 일정 계획의 가용대수`.
- `src/capa_simulation/services/availability_gap.py` — Static 과 설비 일정 기준 분류 행을 한 표로 맞대는 순수 함수(행
  머리는 상수로 읽는다). 두 DB 공정명을 맞추는 장치가 없어 한쪽에만 있는 공정을 `dynamic_only`·`static_only` 로 낸다.
- `src/capa_simulation/services/availability_sheet.py` — `분류별 내역` 9행 비교 시트(`static:`·`sched:`·`gap:` ×
  `owned|lent|available`)와 호기 분해(`build_availability_sheet` → `sheet_view`·`unit_availability_breakdown`).
  - 설비 일정 기준은 반사실이다(보유 = 기존보유 + 비가동만 비운 구간의 가용, 대여 = 가용 − 보유). 「—」 칸은 까닭
    (`REASON_*`)을 갖고 값은 반올림하지 않는다.
- `src/capa_simulation/services/key_process.py` — HOME 주요공정 히트맵의 공정 상한(`KEY_PROCESS_LIMIT`)·프리셋 규칙
  (`normalize_key_process_presets`·`resolve_preset_name`). 고른 차례가 곧 행 순서다(빈 목록 = 고르지 않음).
- `src/capa_simulation/components/revision_label.py` — 리비전을 가리키는 글자 「r{번호} · {리비전명}」 한 곳(시나리오 관리
  공식 지정 팝업·알림·사이드바 팝업·HOME 비교 리비전·파생 원본·월 머지 표). 리비전명은 고칠 수 있어 이 글자를 선택지로
  쓰는 상자는 매 회차 고른 id 를 되쓴다(9장). 마크다운 자리에는 부르는 쪽이 `literal_markdown` 으로 감싼다.
- `src/capa_simulation/components/flash.py` — 동작 결과 알림의 담기·꺼내 그리기 한 길. `queue_flash(key, 글, *, kind,
  icon)`(kind 는 success·info·warning·error, 아이콘 없는 성공은 글만 담는다)로 세션에 담고, 다음 실행에서
  `render_flash(*keys)` 가 알림이 있든 없든 `st.container()` 한 칸을 세워 담긴 알림을 차례대로 한 번 그리고 그 칸을
  돌려준다 — 뒤 형제 자리가 알림 유무로 밀리지 않고 같은 동작의 실패 문구도 그 칸에 쓴다(`st.success` 바로 뒤
  `st.rerun()` 이면 문구가 그려지지 않는다). 이 모듈 밖에서 알림 칸을 꺼내는 꼴은 `tests/test_flash_messages.py` 의
  AST 그물 둘이 막는다 — 이름에 FLASH·NOTICE 가 든 칸을 비우는(`pop`·`del`) 자리와, 이름과 상관없이 꺼낸 칸(`pop`,
  같은 블록의 `get`·`[]` 뒤 `del`)의 값이 알림 요소(`success`·`info`·`warning`·`error`·`toast`)에 드는 자리. 수명이
  다른 칸만 (파일, 함수, 칸) 으로 까닭과 함께 허용 목록에 둔다(9장 「조건부 알림」).
  담아 둔 알림이 없는 칸은 쓰기 직후 적어 둔 알림(`write_guard.note_notice`)이 `TRAILING_PRESS_SECONDS` 안이면
  `write_guard.held_notice` 로 그 글을 성공으로 다시 그린다 — 아주 빠른 둘째 누름의 회차가 앞 회차의 알림을 지우지 않게
  모든 칸이 이 길을 받는다(적지 않은 칸은 그대로 한 번만 그린다, 9장).
- `src/capa_simulation/components/write_guard.py` — 쓰기 콜백의 key 세대 거름(`write_once`·`current_generation`). 세대 비교와
  쓰기를 프로세스 잠금 하나 안에서 하고 「이 세대는 썼다」 를 세션의 dict 표지(`WRITE_MARKS_KEY`)에 적어, 두 회차에 겹쳐
  온 같은 세대의 누름(더블클릭)도 세대마다 한 번만 쓴다(9장, `tests/test_voc_page.py`). `write_once` 는 지금 VOC 만 쓴다.
  버전 대조 저장의 제 저장 표지(`profile_save_marks`·`is_own_profile_save`)는 Proc Rename 직접 편집·판정 기준·확보율
  보정이 써서 빠른 두 번 누름의 둘째 거부를 「다른 사용자가 먼저 저장」으로 알리지 않는다. 거꾸로 남의 저장에 거부된
  누름의 둘째 누름은 충돌 표지(`profile_conflict_marks`·`held_profile_conflict`)로 저장하지 않고 그 거부를 다시
  알린다 — 위 셋과 자동 갱신 설정. 쓰지 않고 끝나는 아주 빠른 둘째 누름이 앞 회차의 성공 알림을 지우지 않게 하는
  알림 표지(`notice_marks`·`note_notice`·`held_notice`)는 VOC 글 삭제와 HOME 주요공정 프리셋 「기본으로」·「삭제」 가
  적고, 다시 그리기는 `flash.render_flash` 가 모든 칸에 한다(9장).
- `src/capa_simulation/components/loading_progress.py` — 오래 걸리는 페이지의 진행 막대(`st.progress`, 자리는 머리 띠).
  단계(`LoadingStage`)를 선언하고 호출부는 `advance()` 만 부르며, 퍼센트는 잰 소요 시간 비율이다.
- `src/capa_simulation/components/equipment_explorer.py` — 가용설비 현황 Main 의 질문·표현·공정·날짜 선택과 결과 하나를
  그린다. 산식을 화면에 복제하지 않는다.
  - 판정·구간은 `simulation_cache` 내용 지문 키 래퍼로 받고 표시명·거르기는 캐시 결과의 복사본 위에서 한다.
  - `표현`(차트·표)과 결과 상자는 「본문 프래그먼트」다(`tests/test_explorer_expression_fragment.py`).
    `render_equipment_period` 는 숨은 `owner_tab` 이면 조회를 건너뛴다.
- `src/capa_simulation/components/equipment_data_workspace.py` — 가용설비 현황 ① 「설비 마스터」 탭의 편집본 경계·작은 편집표
  둘(`render_small_editor`)·저장 이력(`_render_history`)·현재 데이터 내려받기 단추·붙여넣기 미리보기 재료(`build_import_review`·
  `ImportReview`)·저장(세 표 리비전 저장 `save_equipment_buffer`). 옛 폼(입력·직접 편집·저장 이력 — 설비 마스터 편집표·안쪽 탭·
  폼 제출 단추·칸 설정 도움말)은 개편 B1 로 화면에서 빠졌고 개편 D 에서 걷었다 — 파일은 쪼개지 않았다(사양 D16). 탭 본문은
  `equipment_master_tab.py`, 엑셀·CSV 팝업은 `equipment_import_dialog.py`.
  - Space 편집기와 함께 쓰는 편집본 경계다 — 버퍼는 `replace_equipment_buffer` 또는 설비 마스터 표 전용
    `apply_master_grid_result`(같은 세대 규칙 — 내용이 그대로면 세대를 올리지 않는다)로만 갈고 `BUFFER_GENERATION_KEY` 세대를
    올린다(이름 바꿈 `PENDING_RENAMES_KEY`). 「내용이 그대로」 는 `same_frame_content` 로 본다 — 저장본 사본(DuckDB)의 날짜 칸은
    `datetime64[us]`, 엑셀·CSV 넣기의 병합 결과는 `[ns]` 라 `DataFrame.equals` 만으로는 바뀐 것 없는 넣기가 「미저장 변경」 을
    남긴다(낡은 세션의 비가동 붙여넣기 거절 `stale_paste_refusal` 도 같은 견줌). 저장은 `save_equipment_buffer` 한 곳이다.
  - **설비 마스터 표의 세션 칸**(개편 B1): 칸 초안 `GRID_OVERLAY_KEY`(못 읽은 글 — 편집본 밖)·되돌리기 `GRID_UNDO_KEY`(기본형 —
    `equipment_grid.undo_to_state`)·마운트별 토스트 `GRID_TOAST_KEY`(번호 `GRID_TOAST_SEQ_KEY` 는 비우지 않는다)·회차 메모
    `GRID_MEMO_KEY` 는 편집본을 다시 세움(`ensure_equipment_drafts`)·저장·모두 버리기(`reset_equipment_drafts`) 때 함께 비우고,
    불러온 목록 `GRID_LOADED_KEY`·상세 id `GRID_DETAIL_KEY` 는 남긴다. 남의 저장으로 다시 세울 때 그 저장이 이름을 바꾼 저장본
    호기는 옛·새 저장본의 호기 키로 이어 두 칸의 id 를 `s:새` 로 옮긴다(`equipment_grid.renamed_saved_ids` — 행 id 가 저장본
    설비명이라 옮기지 않으면 살아 있는 호기가 말없이 빠졌다, E2E eq-flows). 자기 저장 뒤는 설비 마스터 탭 저장 길이 `save_id_map`
    으로 옮긴다. `apply_master_grid_result` 는 **내용이 바뀐 표의 편집표만**
    버리고(오른쪽 칸 출납이 작은 편집표의 적용 전 편집을 지우지 않게) 되돌리기 목록은 결과의 것을 쓴다. 표 밖 길
    (`_remember_edits` — Space 적용·작은 편집표 적용·엑셀·CSV 넣기)이 편집본 내용을 바꾸면 표 되돌리기를 비우고 토스트로 알린다
    (역 patch 는 그 위에서 맞지 않는다). `follow_unit_renames` 는 행 조각 단계(와 그 앞 단계)를 버린다(`after_row_steps`).
  - **칸 초안이 남으면 어느 저장 길도 저장하지 않는다**(`save_equipment_buffer` 첫머리 — `unsaved_grid_drafts`, 살아 있는 행의
    초안만 센다). 초안은 편집본 밖이라 사이드바 팝업·Space 「배치 저장」 이 모른 채 저장하면 저장 성공이 초안을 지워 친 글이
    사라진다. FAB 대기분만 쓰는 길(`frames is None`)은 막지 않는다.
  - 작은 편집표(`render_small_editor` — 기존 보유대수·비가동 일정, 개편 명세 4-7)는 **폼 밖**이고(명세의 「작은 폼」 에서 바꿈 —
    폼 안 편집은 제출 전까지 서버에 오지 않아 탭 점·떠나기 확인이 볼 수 없었다, 리뷰 rs-b1y) 보기 설정·고르기 칸·일괄 삭제·
    「편집본에 적용」(`_remember_edits`)이고 단추는 보통 단추다(`_selection_buttons`·`_render_bulk_delete_status`). 일괄 삭제
    확인 글(`_deletion_message`)은 기존 보유대수·비가동 일정 둘만이다 — 호기 지우기는 표 출납(`delete`)이다. 칸을 고칠 때마다
    회차가 돌지만 편집표는 「보기
    적용」 으로 확정한 보기를 그려 편집이 남는다. 제출 처리는 돌려준 함수로 화면이 모든 위젯을 그린 뒤 부른다(`st.rerun()` 으로
    끝난다). `small_editor_edits` 가 적용 전 편집을 알린다(탭 ① 점·화면 탭 줄 떠나기 확인). 시험 대역 `BrowserTables(forms=True)`
    는 브라우저처럼 폼 안 편집을 제출 전에 보내지 않는다.
  - **배치 편집 판정은 세션 메모다**(`buffer_has_layout_edits` — 열쇠 = 편집본 세대·편집본 출발 토큰·저장본 사본 토큰·이름 지도,
    `LAYOUT_EDITS_MEMO_KEY`). 역할이 찍힌 세션은 회차마다 `live_layout_role` 이 부르므로 편집본 전체 `layout_edits`(합성 3천 대에
    0.13~0.17 s)를 회차마다 돌리면 8장 예산을 넘었다. 표 출납이 배치에 닿지 않는 op(칸 고침·값 넣기·붙여넣기·날짜 밀기 — 배치·설비명·
    Main 설비 칸이 아닐 때)만이면 얹기 전 판정을 새 세대로 옮긴다(`layout_memo_mark`·`carry_layout_memo`).
    `buffer_base` 는 편집본 출발점 표지(저장본 쌍 토큰 + 씨뿌린 세대 — 표 출납 `base` 와 「리비전 저장」 두 번 누름 잣대). 층 대기분은 캔버스·요소·Main
    설비명 위치(`PENDING_GROUP_LABELS_KEY`) 셋이고 첫 대기분이 본 저장값(`PENDING_BASES_KEY`)을 함께 쓴다.
  - 설비 마스터를 쓰는 모든 저장(설비 마스터 탭 「리비전 저장」 — 표·붙여넣기·CSV·작은 편집표 —, Space 배치 저장, 사이드바
    팝업 저장)은 `_save_equipment_frames` 에서 모듈 묶음 좌표·크기 검사(`saved_master_violations` — 저장본 사본
    `EQUIPMENT_DRAFT_KEY` 와 견준다)를 지나고, 걸리면 `ValueError` 로 거부한다. 배치 편집기가 적용한 묶음의 모양은
    `EDITOR_MODULE_LAYOUTS_KEY`(편집본과 함께 버려짐)에 두어 통과시킨다. 같은 판정을 설비 마스터 탭 「저장 전 변경」 고칠 것 한
    줄(`equipment_master_tab._table_errors`)이 저장 전에 보이고 「리비전 저장」 을 막는다. 표의 모듈 묶음(모듈 둘 이상) 좌표·크기
    칸은 잠기고 그 까닭(`equipment_grid.MODULE_LOCK_REASON`)이 「Space 배치 편집기에서」 를 말한다(사양 D9) — 그런 편집은 붙여넣기
    같은 표 밖 길로만 든다.
  - `ImportReview` 는 「편집본에 넣기」 때 입력·등록할 표·편집본이 달라졌으면 넣지 않고 미리보기를 다시 만든다(마스터 입력
    `read_equipment_update`, `equipment_csv.py`). 일괄 삭제의 `선택` 칸은 편집기 밖으로 나가지 않는다.
  - CSV 업로드 칸은 칸 고유 상한 `CSV_UPLOAD_LIMIT_MB`(50MB — 칸 안내 「50MB per file」, 넘는 파일은 브라우저가
    올리기 전에 막는다)를 쓴다. 서버 전체 상한(`config.toml` `maxUploadSize`)을 낮추지 않는다 — 다른 올리기 칸까지 묶인다.
  - 편집본은 세션의 **설비 시나리오 한 벌**이다(5장 32). `revision_token` 은 (공통, 일정) 쌍 토큰이고 저장본 사본과 함께
    그 쌍의 일정 없음(`DRAFT_UNSCHEDULED_KEY`)을 적는다. 계산 화면은 `calculation_drafts()`(일정 없음 호기와 그 비가동을 뺀
    셋)를 읽고, 편집 대조·`_saved_master()` 는 39칸 전부를 본다. 저장은 `save_equipment(EquipmentSaveRequest)` 로 간다 —
    출발점 칸(`_BASE_KEY` — 공통·일정·시나리오 id)과 이름 지도(`PendingRenames.units`)·저장 칸 값(`equipment_save_fields.py`).
    결과 알림은 공통 rN·시나리오 rN·함께 넣은 목록·발행·「지운 호기 n대는 모든 설비 시나리오에서 빠졌습니다」 를 적는다.
  - **이름 바꾸기는 같은 호기다**(G4·R2). `follow_unit_renames` 가 이름을 기억한 설비 마스터 탭 칸 — 비가동 일정 작은 편집표의
    선택·삭제 확인 대기의 키, 그 표 목록 필터(`설비명`, 위젯을 그리기 전에만 고칠 수 있어 `FOLLOWED_FILTERS_KEY` 에 모았다가
    `render_small_editor` 가 얹는다 — 자기 저장 뒤에도 남기고 버리기·남의 저장에는 버린다), 「새 호기」 칸 함께 넣기 고름 — 를 새
    이름으로 옮기고 `방금 삭제 되돌리기` 와 표 되돌리기의 행 조각 단계는 버린다(Main 설비 이름만 바꿔도). 저장 안 한 이름 바꿈은 Space 상자와
    설비 마스터 탭 알림 칸이 같은 `render_name_changes`(「이름 바꿈 n건」·`NAME_CHANGES_CAPTION`)로 보인다. 설비 마스터 표 호기
    상세의 설비명 칸 확정이 같은 호기 이름 바꿈이다(행 id 로 짝을 알아 공용 넷 — `equipment_grid._rename`). 붙여넣기·CSV 는
    설비명으로 맞대므로 바꾼 이름은 새 호기다(지운 + 새 호기 저장 결과 꼬리 `RENAME_INSTEAD_HINT` — 「설비 마스터 호기 상세의
    설비명 칸이나 Space 편집기 「이름 바꾸기」」).
  - **다른 설비 시나리오에 일정이 있는 호기를 지우는 저장**(설계 11-2 6단계)은 확인 체크 뒤에만 간다. `removals_elsewhere`
    (저장본 이름 − 편집본 − 이름 바꿈으로 비운 이름 → 호기 키 `DRAFT_UNIT_KEYS_KEY` → `load_units_scheduled_elsewhere`)가
    설비 마스터 탭 저장 칸 아래 경고·체크(`REMOVAL_CONFIRM_KEY` — 꼬리 `RemovalElsewhere.token` 은 (호기, 그 일정이 든 시나리오들)의
    지문이라 글이 바뀌면 체크가 풀린 새 칸)를 세우고, `_save_equipment_frames` 가 다시 센 삭제를 체크로 본 것
    (`removal_confirmed` — 그 글의 `RemovalElsewhere`)이 덮지 않으면(`covered_by` — 확인 안 한 호기, 본 뒤 그 호기 일정이 든
    시나리오가 늚) 거부한다 — 체크가 없는 자리(Space 「배치 저장」·팝업)도 같은 판정으로 막힌다.
  - **배치 일곱 칸은 Space 와 같은 판정**(설비 시나리오 2단계 S3 — 페이지가 `space_edit_mode(...)` 를 설비 마스터 탭
    `render_equipment_master_tab(layout_mode=)` 에 넘긴다). "official" 은 공식 배치(공통 대장), "overlay" 는 그 가정 설비
    시나리오의 배치 차이다(공식은 바뀌지 않는다 — 새 호기는 공통에 자리 없이, Q1·Q2, 캡션 한 줄). 배치 칸을 바꾼 적용(표 출납·
    「편집본에 넣기」·「호기 추가」)은 그때의 역할을 찍는다(`stamp_layout_role`). "locked"(잠긴 회차)는 저장하면 저장본 호기
    키를 잇는 행(`layout_lock_origins` — `inherited_unit_names`)의 배치 일곱 칸을 표가 잠그고(`GridContext.layout_lock` — 출납도
    파이썬이 버린다) 새 호기는 자리 없이 맞추며(`LayoutLock.place` — `layout_overlay.hypothetical_common_places` 한 규칙),
    붙여넣기는 미리보기 전에 막는다(`layout_paste_refusal`). 저장본과 달라진 칸 판정·되돌림 재료는 `layout_edits`(`LayoutLock.
    restore`)다. 칸 머리 도움말 셋째 묶음 「배치 — …」(`services/equipment_grid.LAYOUT_COLUMN_HELP`)와 범례가 같은 뜻이다.
  - **붙여넣기·CSV 의 배치 칸**(Q2): 가정 세션은 「배치 칸도 붙여넣기」(`PASTE_LAYOUT_KEY`, 기본 끔 — 「현재 데이터」 CSV 는
    합친 값이라 공식 CSV 를 올리면 배치안이 공식 자리로 돌아간다)를 두고, 끄면 있던 호기의 배치 칸은 지금 값을 둔다(새 호기의
    배치 칸은 받는다). 켜면 「가정 배치 n대가 바뀝니다(그 가운데 m대는 공식 자리로 돌아가 차이가 지워집니다)」, 공식 세션은
    「공식 배치 k칸(호기 n대)이 바뀝니다」 경고. 미리보기 요약은 「배치 칸 k(호기 n대)」 를 따로 센다(`paste_split_summary`).
    미리본 뒤 체크를 바꾸면 후보를 다시 만든다(`ImportReview.layout_pasted`). 「현재 데이터」 꼴 CSV 이름의 시나리오가 세션과
    다르면 경고 한 줄(`_csv_scenario_mismatch`).
  - **저장의 대조 역할**(`_layout_role_of` — 설계 6-2): 찍힌 역할(`LAYOUT_ROLE_KEY`, 배치를 바꾼 적용마다 — Space 적용·이
    탭 배치 칸)을, 없으면 편집본에 배치 편집이나 층 값 대기분이 있을 때 지금 세션의 역할을 `expected_layout_role` 로 넘긴다.
    그 사이 남의 발행으로 역할이 바뀌었으면 저장소가 `EquipmentLayoutRoleChanged` 로 막는다. 찍힌 역할은 편집본을 다시
    세우거나·저장하거나·「배치 변경만 버리기」 하면 지우고, 남은 배치 편집이 없으면 `live_layout_role` 이 지운다(남은 찍힘이
    역할이 바뀐 뒤의 새 편집을 잠그지 않게). 편집본을 세울 때는 찍지 않는다(검토 M3).
  - **남의 공통 저장 뒤 가정 배치 편집 다시 얹기**(S4 — 설계 9장·검토 M4). 남이 공통을 저장해 편집본을 다시 세울 때(토큰의
    일정 쪽 그대로) 가정 역할로 찍힌 배치 편집이 있으면 옛 저장본 사본이 바뀌기 **전**에 재료(옛 사본·편집본·저장의 호기 키
    규칙 `layout_lock_origins`·옛 호기 키 쌍)를 들고, 새 저장본 위에 있던 호기의 배치 일곱 칸을 호기 키로 다시 얹는다
    (`ensure_equipment_drafts` → `layout_overlay.reapply_layout_edits` — 남이 그 사이 이름을 바꾼 호기도 따라가고, 지운 호기는
    빼고 알림에 이름). 다시 얹었으면 찍힌 역할을 남기고 세대를 한 칸 올린다(저장 안 한 편집). 배치 편집기가 적용한 묶음 모양
    승인(`stage_editor_module_layouts`)도 재료에 들고, 다시 얹은 결과에서 그 모양 그대로인 묶음만 새 저장본 이름으로 옮겨 다시
    둔다 — 버리면 편집기만 낼 수 있는 묶음(숨은 모듈이 있는 묶음 보내기 등)이 저장에서 「설비 마스터 표로 바꾼 값」 으로 막힌다(S4
    리뷰). 공통·일정 칸 편집·새 호기·층 요소·이름표 대기분은 지금처럼 버리고, 공식 역할 편집·다른 리비전(일정 쪽이 바뀜)은 다시
    얹지 않는다. 알림(`discarded_notice`)이 다시 얹은 설비 수(묶음 1대)와 버린 것을 따로 적는다. 모양 검사·끝 확인은 저장이 다시
    본다.
  - 세션이 **낡음**이면 설비 마스터 탭 맨 위에 그 알림을 세우고 표의 시나리오 일곱 칸(잠금 갈래 `stale`)·비가동 일정 작은
    편집표를 잠그며 새 호기·저장본 호기 지우기를 막고(`newRowsLocked`·`deleteLock`), 붙여넣기 미리보기는 일정 칸 변경·새 행·
    비가동을 그 까닭으로 거부한다(`stale_paste_refusal`) — 공통 칸은 그대로 편집·저장된다. 칸 머리 풍선 첫 마디가 「공통 — …」/
    「공통 — 공식 일정 기준」(상태 둘)/「시나리오 — 「셋업 실무」 에만 저장」(`equipment_grid.scenario_column_help`)이고 표 범례가
    같은 뜻이다.
  - 저장 이력은 고른 설비 시나리오의 일정 리비전(번호·저장자·출처·공통 rN)이고 조회는 `load_saved_pair`(저장 때의 짝)다.
    「현재 데이터」 CSV 이름은 `equipment_master_<시나리오>_r{no}_c{공통no}_<날짜>.csv` 다. 가정 시나리오의 일정 확인(「일정 확인
    필요」·표 풍선)은 공식 일정 + 편집본 공통 칸이다(`official_confirmation_master` — 세션 칸 한 벌).
- `src/capa_simulation/components/equipment_scenario_status.py` — 사이드바 조건 패널의 「설비 시나리오」 줄과 팝업, 그리고 설비
  화면들이 함께 쓰는 설비 시나리오 문구(일정 없음·설정 팝업 Cut-off 잠금·옛 배포 흔적 경고와 그 옆 「시나리오 관리에서 이어 쓰기」 단추·기준선 거부·설비 출처 띠).
  - 줄은 **페이지가** `resolve_equipment_session` 뒤에 `app.py` 가 세운 칸에 그린다(9장 「사이드바·조건 카드·본문」). 값 칸은
    「운영 일정 · r12」(긴 이름은 `app_header.short_scenario_name` 으로 줄여 「 · rN」 이 늘 보인다 — 값 칸은 한 줄
    말줄임. 머리 띠 꼬리도 같은 이름), 배지는 `미저장 변경` → `일정 없이 엶`(옛 배포 흔적이 공식과도 합쳐지지 않은 회차) →
    `공식 vN`(공식 발행 쌍이면 낡아도 이것이 먼저) → `최신 rM 있음` → `가정 배치`(그리는 리비전의 배치가 공식과 다름 —
    `EquipmentSession.layout_differs`, 라벨 dict 의 기본형이라 그리는 동안 저장소 호출 0) → `저장된 리비전` 차례. 잠근
    꼴(팝업 없음)은 값 칸 끝 「(고정)」 — 공정 Capa 상세 HOME 방문뿐이다(그 까닭 `HOME_VISIT_LOCK_REASON` 은 줄 아래 한 줄 —
    꺼진 단추라 풍선이 없다). Space 현황은 고를 수 있는 줄이다(S3).
  - 팝업은 `app.py` 의 `render_condition_dialogs` 셋째 갈래다. 「불러오기」(시나리오 → 리비전 라디오, 공식 발행 리비전에
    표지, 미저장이면 「변경을 버리고 불러오기」)와 「저장」 — 저장 구획은 편집본을 세우는 가용설비 현황·필요 단축 일정에만
    선다(`SAVE_PAGES`). 저장소는 팝업을 연 동안에만 읽는다(5장 23).
- `src/capa_simulation/components/equipment_save_fields.py` — 설비 마스터 저장 칸(변경 메모 옆 저장자·함께 넣기 두 체크·공식 발행
  체크)과 저장 출발점 값(`EquipmentSaveBasis`). 설비 마스터 탭 「저장 전 변경」 의 「리비전 저장」(콜백 — `save_fields_from_state`,
  저장자 칸은 `persist_saved_by` — 탭 ① 은 숨은 회차에 그리지 않는다)·사이드바 팝업 「저장」·Space 「배치 저장」(팝오버, 콜백이
  `save_fields_from_state` 로 읽음) 세 자리가 같은 부품을 쓴다(개편 B 전에는 옛 폼 두 저장까지 네 자리). 설비 마스터 탭과
  사이드바 팝업은 가정 설비 시나리오에서도 발행 체크를 그린다 — 가정 세션 저장도 함께 넣기로 공식 시나리오에 새 리비전을 만들면
  공식 발행까지 가므로 끌 수 있어야 한다(G1). 세 자리 모두 저장 칸 아래에 「새 호기」 칸 고름 한 줄
  (`equipment_data_workspace.new_unit_choice_line` — 그 칸에서 넣은 호기는 그 칸의 체크가 저장 칸 체크를 이긴다, D8)을 둔다.
  - 기본값 상수 셋(`DEFAULT_PUBLISH_OFFICIAL`·`DEFAULT_PROPAGATE_NEW_UNITS`·`DEFAULT_PROPAGATE_NEW_DOWNTIME`)이 늘 켬이다
    (G1 — 2026-10-24 결정 판 「권장대로」·F6·F2 — 바꾸려면 여기 하나만 바꾼다). 함께 넣을 후보 수(`counts` — 「· 후보 n대」)는 사이드바 팝업만 적고, 설비
    마스터 탭 저장 구획·Space 「저장 칸」 은 체크만 세운다 — 실제로 퍼진 수·목록과 발행 여부는 저장 결과 알림이 적는다.
  - **가정 세션의 Space 「배치 저장」**(`assumption=True` — 설비 시나리오 2단계 Q1)은 「새 호기를 다른 설비 시나리오에도
    넣기」 가 기본 끔(`DEFAULT_ASSUMPTION_PROPAGATE_NEW_UNITS`)이고, 켜면 공식 가용대수에 센다는 경고와 그때만 「함께 넣은 공식
    리비전 발행」 체크가 선다(key 꼬리 `_assumption` 으로 공식 자리와 가른다). 설비 마스터 탭 저장 칸은 1단계 F6 그대로 켬이다.
- `src/capa_simulation/components/equipment_scenario_management.py` — 시나리오 관리 「설비 시나리오」 구획(1단계 몫 + E7 —
  2026-10-24 가용설비 현황의 탭에서 옮김). 구획 진입(`render_equipment_scenario_section` — 설비 DB 는 이 안에서만 연다, 머리
  「이 세션: …」 한 줄·세션 알림)과 다른 화면에서 이 구획으로 옮기는 길(`open_equipment_scenario_management` — 탭 상한을 먼저
  보고 전환 칸·탭 기억 칸을 적은 뒤 본문에서 `st.switch_page`, 설비 화면 옛 배포 흔적 경고 옆 「시나리오 관리에서 이어
  쓰기」)도 둔다. 시나리오
  표(공식/활성·최신 rN·리비전 수·저장된 배치 차이)와 고른 시나리오의 「시나리오 이름 바꾸기」(가정 시나리오 최신에 배치 차이가
  있으면 「배치 차이 모두 지우기」 도), 리비전 표(리비전명·출처 `이관/저장/복제/함께 넣기/되돌리기/배치 차이 정리`·공통 rN·행
  수·배치)와 고른 리비전의 작업 다섯 — 「이 리비전 불러오기」·「이 리비전으로 되돌리기」·「여기서 새
  시나리오」·「리비전명」·「공식으로 발행…」(지금 공식 → 새 공식, 최신이 아니면 그 사실, 발행 번호 대조) — 과 옛 배포 흔적이
  있을 때만 「이대로 이어 쓰기」. 구획 본문은 DB 경로와 그 회차 세션만 받아 따로 선다.
  - 쓰기는 저장소가 하고 그 뒤 이 화면이 `clear_equipment_scenario_cache()` 를 부른다(저장소는 캐시 경계를 import 하지
    않는다). 「설비 시나리오」 쪽을 고른 회차에만 목록을 읽는다. 그 사이 남의 쓰기로 거절된 작업(되돌리기의 최신·공통·발행 대조, 리비전명·시나리오 이름 비교 후
    쓰기)은 `_refused` 가 공통 최신·목록을 비우고 입력 칸 세대를 올려(옛 확인 체크로 다시 누르지 않게) 맨 위에 알린다.
  - **되돌리기**(E7)는 고른 리비전이 최신이 아닐 때만 확인 글을 세운다 — 새 번호, 바뀌는 호기 수·비가동 행 수·일정 없음,
    「rK 뒤에 공통 대장에 든 호기(지금 n대)는 rK 에 일정이 없어 「일정 없음」 이 됩니다」(늘 수와 함께 — 0대면 「없습니다(0대)」),
    공통 대장·다른 시나리오는 그대로, 공식 시나리오면 발행 체크(기본 켬). 확인 체크(바뀌는 수를 적는다)를 켜야 단추가 선다. 이
    세션이 그 시나리오를 보고 저장 안 한 설비 편집이 없으면 세션을 새 리비전으로 옮기고(`select_equipment_scenario`), 편집이
    있으면 두고 낡음 잠금에 맡긴다. 탭의 리비전 상자도 다음 회차에 새 리비전으로 옮긴다(`PENDING_REVISION_KEY` — 위젯을 그리기
    전에 적는다).
  - **확인 체크는 본 확인 글에 묶는다.** Streamlit 1.63 체크박스는 key 가 같으면 글이 바뀌어도 값을 지킨다. 그래서 체크 key 꼬리는
    확인 글을 정한 값 다섯(`restore_seen_token` — 시나리오·고른 리비전·그 시나리오 최신·공통 최신·공식 발행 번호)이고 입력 칸
    (새 리비전명·메모·저장자·발행 체크) key 꼬리는 고른 리비전이다. 저장소에 넘기는 대조값도 그 회차에 그 꼬리를 만든 같은 값이다
    — 다른 리비전을 고르거나 확인 뒤 남의 저장·발행으로 값이 바뀐 회차에는 체크가 풀린 새 칸이 서고 단추가 잠긴다. 잠가 그린
    단추의 클릭은 서버가 버리므로(9장 「잠긴(disabled) 위젯」) 단추는 「확인 체크 뒤에만 선다」 대로 잠그되, 체크가 켜진 회차의
    값을 `RESTORE_AGREED_KEY` 에 적어 두고 같은 리비전에서 값만 바뀐 회차에 체크를 풀었다고 알린다 — 누른 회차에 버려진 클릭도
    그 알림으로 까닭이 보인다. 단추 처리도 체크를 다시 본다(`not clicked or not agreed`). 값이 그대로인데 캐시가
    늦어 저장소가 그 사이 쓰기를 보면 `EquipmentRevisionConflict`·`EquipmentReleaseMoved` 로 거절한다(`_refused`).
  - **여기서 새 시나리오**는 1단계 복제(만들기는 복제로만)의 출처를 고른 리비전으로 넓힌 것이다 — 안내가 새 시나리오의 일정
    없음 수와 그 리비전 뒤에 든 호기 수를 적는다. 확인 재료는 둘 다 `load_schedule_restore_preview`(불변 리비전 id 셋 + 층 현행값
    쓰기 세대 키) 한 칸.
  - **리비전명**은 칸을 세울 때 본 이름을 따로 들고(`…__seen`) 그 이름으로 비교 후 쓰기를 한다 — 칸이 고치지 않은 채면 남이
    바꾼 이름으로 다시 선다. 비우면 지운다. **시나리오 이름 바꾸기**도 같은 꼴이다 — 팝오버 안 칸은 매 회차 그려져 key 가
    남으므로 그 회차 목록 이름을 `expected_name` 으로 넘기면 대조가 늘 통과해 남의 이름 바꿈을 말없이 덮는다(2026-10-26 E2E).
    두 칸 모두 고치지 않은 칸은 **매 회차** 지금 이름을 다시 적는다(`_settle_compare_field`) — 닫힌 팝오버 안 칸은 브라우저에
    마운트되지 않아 나중에 열 때 마지막 회차가 실어 보낸 값으로만 서므로, 처음 세운 회차에만 적으면 한 회차 뒤에 연 칸이 빈
    칸으로 서고 그대로 누른 「리비전명 저장」 이 이름을 지웠다(2026-10-26 E2E 3회차, 9장 「닫힌 팝업 안」).
  - **공식으로 발행**은 확인 글을 그린 회차의 {고른 리비전, 공식 번호}를 `PUBLISH_SEEN_KEY` 에 남기고, 단추를 누른 회차에 그
    번호가 지금과 다르면(그 사이 남이 발행) 쓰지 않고 `_refused` 로 까닭을 알린다(`publish_seen_refusal`) — 누른 회차에는 확인
    글이 이미 새 목록으로 다시 그려져, 지금 번호로만 대조하면 「v1 → v2」 를 본 사람이 말없이 v3 을 낸다. 저장소 대조값도 그 번호다.
    그 시나리오 최신(id·번호)도 함께 남겨(`publish_seen_token` — 「rN은 … 의 최신(rM)이 아닙니다」·배치 줄을 정하는 값) 그 사이 남이
    같은 시나리오에 새 리비전을 저장했으면 같은 길로 거절한다 — 그 줄을 본 적 없는 사람이 최신이 아닌 리비전을 말없이 냈다
    (2026-10-26 E2E 3회차). 최신 대조는 화면 몫이다(저장소는 공식 번호만 대조 — 최신이 아닌 리비전 발행은 원래 된다).
    확인 글 「지금 공식 vN · 「…」 rK」 의 rK 는 그 시나리오 최신·세션 스냅샷·공식 시나리오 리비전 목록(`publish_preview` 의
    `official_revisions` — 리비전 표와 같은 캐시) 차례로 찾는다 — 앞 둘만 보면 공식이 그 시나리오 최신이 아니고 세션이 그것을
    들고 있지 않을 때 번호가 빠져 지금 공식이 최신처럼 읽혔다(2026-10-26 E2E 3회차). 목록 한도 밖이면 번호를 뺀다.
  - **팝오버·알림 자리**(2026-10-25 E2E). 맨 위 작업 알림·거절 알림, 옛 배포 흔적 구획, 옛 판 흔적 줄·경고, 구획 머리의
    세션 이동 알림은 생기거나 빠져도 뒤 형제의 자리가 그대로이게 늘 서 있는 `st.container()` 칸 안에 그린다(9장 「key 가
    있어도 자리는 고정한다」 — 알림이 빠지는 회차에 key 없던 팝오버 줄이 한 칸 당겨져 다시 서며, 알림 뒤 처음 누른 확인
    체크·Tab·Enter 가 열린 팝오버를 닫았다). 팝오버 일곱의 key 꼬리는 팝오버 세대(`POPOVER_GENERATION_KEY`)다 — 한 번뿐인
    알림을 그리는 회차에만 올라 작업을 마친 팝오버는 그 회차에 닫힌 채 다시 선다(전과 같다). 리비전 표 앞 띄움
    (`REVISION_TABLE_TOOLBAR_CLEARANCE` 24px)은 표 오른쪽 위로 솟는 도구 막대가 바로 위 줄 맨 오른쪽 팝오버 단추(「시나리오
    이름 바꾸기」·「배치 차이 모두 지우기」)를 덮어 누름을 가로채지 않게 한다(9장 「표 도구 막대」).
  - **이대로 이어 쓰기** 확인 체크 key 꼬리는 체크 글을 정하는 값 셋(흔적 수·옛 배포 리비전 번호·빠지는 호기 수 —
    `continue_confirm_key`)이다(되돌리기 체크와 같은 까닭). 발행 번호 0 은 「v0」 이 아니라 「발행 없음」(`release_words`)이다.
  - **배치 차이(설비 0031 — S4)**. 시나리오 표 「저장된 배치 차이」 는 최신의 **저장된** 행(원시 — 「호기 3행·요소 1개」 ·
    `EquipmentScenarioSummary.latest_layout_rows`), 리비전 표 「배치」 는 그 리비전의 저장된 행이다(목록에는 실효를 셀 재료가 없다
    — 설계 8-2). 옛 판(0031 을 모르는 배포)이 차이 있는 리비전 뒤에 저장한 리비전(옛 코드 흔적 — 목록 셈 `layout_trace_count` 와
    같은 규칙 `layout_trace_sources`)은 「옛 판 저장 — rN 배치 빠짐」 이고 표 위에 「rT 은 옛 판이 저장해 rN 의 가정 배치가
    빠졌습니다 — rN 으로 되돌리기」 경고, 시나리오 표 아래에 흔적이 있는 시나리오 한 줄. 저장은 막지 않는다(설계 14장).
    「배치 차이 모두 지우기」(`clearable_layout` — 가정 시나리오 최신에 차이가 있을 때만)는 확인 체크 key 꼬리가 (시나리오, 최신
    id)라 남의 저장 뒤 체크가 풀리고, `clear_layout_overlay(expected_latest_schedule_revision_id=)` 뒤 이 세션이 그 시나리오를
    보고 저장 안 한 편집이 없으면 새 리비전으로 옮긴다(되돌리기와 같다). 「공식으로 발행」 은 발행 쓰기와 **같은 판정**
    (`equipment_repository._layout_publish_preview` → `load_layout_publish_preview` — 불변 id 셋 + 층 현행값 세대 키)을 미리 읽어
    막히면 단추를 끄고 막힘 글(`layout_publish_blocked_words` — 발행 쓰기 거부와 같은 한 곳)을 적으며, 공식과 같아진 차이만
    남았으면 「… m행을 정리한 rN+1 로 발행합니다」 를 적는다(머리 「배치는 공식과 같습니다」 와 발행 거부가 함께 뜨지 않게 —
    검토 F4). 막힘 글은 까닭 셋으로 갈린다 — 고른 리비전에 공식과 다른 배치(「실효 … — 저장된 차이 m행」, 최신이면 공식에서
    옮기기·「배치 차이 모두 지우기」, 옛 리비전이면 그것으로는 풀리지 않아 「이 리비전으로 되돌리기」 뒤 지우고 발행), 옛 리비전에
    남은 행이 지금 공식과 같음(「공식과 다른 배치」 라 하지 않고 되돌린 뒤 발행 — 정리 발행은 최신만), 고른 리비전에는 없고 최신에
    행이 남음(실효가 있으면 그 수, 없으면 「지금 공식과 같음」 과 최신 발행). 공통 대장에서 지운 호기의 저장된 행
    (`LayoutPublishPreview.orphan_units`·`newest_orphan_units` → `PublishBlock.orphan_rows`)은 「공식과 같아진」 행이 아니라
    버린 행이라 정리·막힘·발행 뒤 글이 「지운 호기의 배치 차이 n행」 으로 따로 말한다(`layout_overlay.cleaned_layout_words`·
    `settled_layout_reason`, E2E r3) — Space 머리 첫 줄의 「공식과 같아진 것은 … 정리됩니다」 꼬리도 그 행(`layout_orphans`)을
    빼고 센다(둘째 줄 「지운 호기의 배치 차이 n행은 버렸습니다」 가 말한다). 정리 발행 뒤에는 「배치 차이 모두 지우기」 처럼 리비전
    상자와 그 시나리오를 보던 세션을 새 리비전으로 옮긴다(`_follow_new_revision` — 저장 안 한 편집이 있으면 남김, S4 리뷰).
    되돌리기 확인 글은 되살리는 가정 배치에서 그때와 자리가 다른 손대지 않은 호기 수(`layout_moved_since` — 이력
    「그때 그대로」 와 다름, 검토 F21)를 덧붙인다.
- `src/capa_simulation/components/qual_deadline_calculator.py` — 필요 단축 일정 머리 「Qual 마감 계산기」 팝업의 본문
  (2026-10-24 — 가용설비 현황의 탭에서 옮김). 숫자 칸 넷·12개월 편집표를 받아 KPI 넷·호기별 표·월 점검 표(판정 칸·지난 마감
  칸은 상태색 면, 고정 uuid Styler)와 CSV 둘을 그린다.
  - **이벤트 칸에 아무것도 쓰지 않는다** — 두 칸 배치·지표 줄·상태색 띠의 서식은 맨 위 안내 한 줄과 한 `st.html`
    (`calculator_style_markup`)에 싣는다(9장 「팝업 본문은 이벤트 칸에 같은 수만」). 그래서 `status_metric` 의 `metric_row`·
    `render_status_metric` 을 `emit_style=False` 로 부른다. 팝업 머리가 제목이라 본문에 제목을 다시 적지 않는다.
  - 팝업 폭은 이 팝업만 넓힌다 — Streamlit 1.63 큰 팝업은 1120px 에서 멈춰 두 칸이 늘 위아래로 쌓였다(1280·1600·1920 창
    실측). 같은 서식 덩이에 팝업 상자(`stDialog` 안 `div:has(> [role="dialog"] .st-key-<배치 key>)` — 폭은 `role="dialog"`
    의 부모가 쥔다) 폭을 창 폭 − 48px, 최대 1400px 로 싣는다(`_DIALOG_MAX_PX`) — 1280px 창부터 개편 전 탭처럼 입력 칸 옆에 결과가
    선다(호기별 표 가로 넘김 없음). 팝업 DOM 이 바뀌면 넓히지 못할 뿐 쌓여 그대로 쓴다.
  - 입력은 세션에만 둔다 — 숫자·날짜 칸은 `persist_state`, 편집표는 `on_change` 콜백이 원본 표(`MONTHS_KEY`)에 옮긴다
    (팝업을 닫았다 열어도 남는다). 「예시로 되돌리기」·「모두 비우기」 는 콜백이 칸을 적고 `discard_editor` 한다.
  - 엑셀 여러 칸은 원본처럼 「엑셀에서 한 번에 붙여넣기」(`remembered_expander` 안 폼의 글 칸 + 「표에 넣기」 콜백,
    규칙은 `qual_deadline.parse_pasted_months`)로 받는다 — 편집표 붙여넣기는 브라우저 클립보드 읽기라 보안 문맥이 아닌
    주소에서 막히고 신규 호기 칸 뒤를 버린다. 목표 칸에는 `step` 을 주지 않는다 — Streamlit 1.63 편집표 `NumberColumn` 은
    `step` 의 소수 자릿수에서 값을 잘라 저장한다(19.3456 → 19.34). 계산이 가벼워 캐시하지 않는다.
  - 원본은 입력을 브라우저 저장소에 남겼고 앱은 세션에만 둔다 — 메우지 않는다(`docs/TODO.md` 3장 결정 기록 「화면」).
  - 배치는 원본처럼 넓으면 입력 칸(420px) 옆에 결과 칸, 두 칸을 담은 줄이 결과 칸이 호기별 표를 다 담지 못할 만큼
    좁으면 위아래로 쌓는다(`layout_style` — 줄 폭 컨테이너 질의, flex 항목은 `stLayoutWrapper`). 창 폭이 아니라 줄
    폭으로 가르는 것은 사이드바가 본문 폭을 바꾸기 때문이다. Streamlit 격자는 칸 폭의 합이 표보다 좁으면 남는 폭을
    붙박지 않은 칸에 고루 붙이고 넓으면 가로로 넘기므로, 편집표 세 칸 폭의 합은 입력 칸 안에 두고(넘치면 `신규 호기`
    를 고칠 때 `월` 칸이 가려진다) 호기별 표 `메모` 칸에는 메모 한 가지가 다 보이는 폭을 준다.
- `src/capa_simulation/components/cutoff_management.py` — 가용설비 현황 「설정」 팝업(개편 전 `Preference` 탭)의 Cut-off
  편집표·저장·CSV 왕복과 빠진 공정 안내. 초안이 아니라 저장된 값을 돌려준다(Static 대비 일정은 그 값을 받지 않고 캐시
  경계에서 직접 읽는다). 스타일만 든 `st.html`·토스트를 쓰지 않는다(팝업 본문).
- `src/capa_simulation/components/equipment_settings_dialog.py` — 가용설비 현황 제목 줄 끝 「설정」 단추와 그 팝업(묶음 머리
  「공정별 Cut-off」 하나 — 나중 설정 자리, D14)의 열림 칸(`available_equipment_open_dialog`, 값 `settings`)·여는 콜백
  (`forget_page_dialogs()` 부터)·호스트(이벤트 칸 늘 한 자리). 저장·채우기 뒤에도 팝업을 열어 둔다(9장 「팝업과 콜백」 예외 —
  앱 범위 `st.rerun()` 이라 바깥 화면도 새 값이고 flash 가 누른 단추 아래에 선다). 닫으면 제출하지 않은 표 편집은 사라진다.
  - 저장은 초안 지문 대조다(`process_cutoff_fingerprint` → `ProcessCutoffConflict`) — 표 전체 교체라 옛 초안이 남의
    공정을 지운다. 원본 공정명 원장이라 편집표·경고·`process_cutoff.csv` 는 원본이다.
- `src/capa_simulation/components/availability_gap_panel.py` — `Static 대비 일정` 의 `조회 결과` 하나(`가용대수 비교`·
  `분류별 내역`·`확보율 교차검증`)를 그린다. DB 는 페이지가 읽어 넘기고 계산은 `simulation_cache` 래퍼
  (`get_availability_sheet` 등)로 받아 고르기만 한다.
  - 칸 누름 → 근거 카드(`pick_gap_sheet_cell`)는 같은 칸 다시 누름이 유일한 닫기이고 세대(`GAP_SHEET_GENERATION_KEY`)를
    `layout.meta` 에 싣는다. 시트·근거 카드는 키 붙은 프래그먼트다(`tests/test_availability_sheet_panel.py`).
  - 호기 필터가 걸리면 Static·GAP 행은 「—」 다. 시트·호기 목록 CSV 와 공정명 불일치 문구는 원본이다.
- `src/capa_simulation/components/required_shortening_panel.py` — `필요 단축 일정` 화면(조건 카드, 머리 `목표 확보율`·
  `진척 비교`, KPI·`계획 · LOB 요약`·공정 카드·CSV 세 벌). 수요·달(Cut-off 빔 포함)·공용 조건 물러서기·계획 꺼내기는
  `components/shortening_source.py` 로 옮겼다(Space 필요 단축 보기와 한 길 — 세 세션 칸도 거기서 다시 내보낸다). 표시명·맞대지 못함·
  UPEH 가정 몫은 패널에 남는다.
- `src/capa_simulation/components/shortening_source.py` — 필요 단축 일정 화면과 Space 필요 단축 보기가 **같은 함수·같은 키·같은
  캐시 칸**으로 계획을 꺼내는 길(`load_shortening_demand`·`shortening_month_options`·`shortening_filter_profile_or_default`·
  `shortening_frames`·`load_official_shortening`·`ShorteningStop`). 캐시 데코레이터가 없고(경계는 `simulation_cache`), 아래 부름은
  모듈 속성으로 한다(시험이 센다). 공정 표시명을 읽지 않는다.
- `src/capa_simulation/components/space_shortening_view.py` — Space 현황 「필요 단축」 보기의 그리기 — 본문 조작 줄(목표·흐리게)·
  기준 캡션·못 읽음 알림·FAB 요약·층 보기 칸·누른 호기 상세, 링크 도착(`consume_layer_link`)과 상세 단추 이동
  (`switch_to_queued_shortening` — 강조 칸·목표 칸 둘만 적음). 공정 표시명을 읽지 않는다(원본 공정소분류 — 결정 D10).
  - 공정을 비우면 목표 미달 공정 전체다. 조건 셋은 공용 프로필(`0019`)이라 세션이 비었을 때만 심고 `on_change` 에서만
    쓴다.
  - `계획 · LOB 요약` 은 HOME 과 같은 키(`build_home_simulation_cache_key`)로 캐시를 나누고 CSV 도 캐시에서 고른다.
  - 머리·본문은 「본문 프래그먼트」다 — 기준선·판정 기준은 회차마다 다시 읽고 기준선 쓰기 표지를 보면
    `st.rerun(scope="app")` 한다(`tests/test_shortening_view_fragment.py`·`tests/fragment_browser.py`).
  - 계획은 `_Plan.official`(키와 한 묶음)이고, UPEH 가정 계획은 `_Plan.assumed` 로더로 「UPEH 가정 비교」 보기에서만
    꺼낸다(공식 부족 ∪ 가정 부족, 「가정으로 해소」, 역산 「이 값으로」 — 앱 전체 회차로 올린다, 표·CSV 첫 열 표지).
  - 강조 공정(`shortening_board.SHORTENING_HIGHLIGHT_KEY`)은 세 보기 모두 카드 맨 앞이다(테두리·배지). 공용 설정 공정
    밖이면 「KPI·CSV 에 들지 않음」 을 적고, 맞대지 못한 공정이면 카드 대신 그 말이다. 카드 class 는 그대로 `shk-card` 다.
- `src/capa_simulation/components/shortening_board.py` — 필요 단축 일정의 공정 진척 보드(`st.dataframe` 한 줄 고르기 →
  그 카드 강조, 표 key 세대를 올려 고른 줄을 남기지 않는다)·카드 차례·기한 임박 날수(세션 값, 선택지 고정)·기한 임박/이행
  지연 상자·강조 공정 칸·카드의 상세 근거 링크(`st.page_link` + 주소 인자)·「도면에서 보기」(`space_link_params` 순수 +
  `render_space_link`).
  - 강조 공정 칸은 `(원본 공정명, 출처)` 튜플이다 — 공정 Capa 상세 이동(`detail`)·보드 줄 고르기(`board`)·Space 필요 단축 보기의
  「필요 단축 일정에서 이 공정 보기」(`space`)만 적는다(출처마다 배지 글이 있어야 `current_highlight` 가 받는다).
    공정 필터·공용 프로필(0019)·기준선(0021)에는 닿지 않는다(`tests/test_required_shortening_tab.py`).
- `src/capa_simulation/components/upeh_assumption_controls.py` — 두 화면 조건 카드 끝 「이 세션만」 UPEH 가정 묶음(% 칸
  80~150·1 단위·곧바로 반영, 「UPEH 적용 시작/끝」, 「100% 로」)과 배지·역산 한 줄·「이 값으로」. 구간 선택지는
  `assumption_month_options`(조회기간 ∩ 이번 달 이후) 하나이고, 세 칸 모두 위젯 앞에서 `carry_shared_widget_value` 를
  부른다(`tests/test_upeh_assumption_controls.py` — 앱 전체로 페이지를 옮긴 첫 회차까지).
- `src/capa_simulation/components/preset_number_field.py` — 미리 정한 값 버튼(`st.pills`, `required=True`)과 늘 지금 값을
  보이는 직접 입력 숫자 칸을 **정본 한 칸**(위젯 아닌 세션 칸)으로 묶는다(제약 시뮬레이션 D10). 두 위젯 칸은 위젯 앞에서 매
  회차 정본에서 다시 서되 **다를 때만** 적고(같은 값을 적으면 `set_value` 가 회차마다 가서 치다 만 숫자를 덮는다), 콜백이 정본을
  적는다. 버튼 콜백은 숫자 칸 세대도 올려 칸을 **새 key** 로 다시 세운다 — 1.63 숫자 칸은 범위 밖 글(301)을 확정하지 않은 채
  쥐고 그동안 서버 값을 무시하므로, 같은 key 로는 버튼 값이 칸에 서지 않고 빨간 표시가 남는다. 칸에 치고 Enter 없이 버튼을
  누르면 칸 확정과 버튼 누름이 한 회차에 들어 두 콜백이 함께 도는데, **어느 차례든 버튼이 이긴다** — 숫자 칸 콜백은 자기 key 가
  지금 세대 key 와 다르면(버튼 콜백이 먼저 세대를 올렸으면) 적지 않는다(1.63 은 버튼 콜백이 먼저라 친 값이 덮었다, 2026-10-26
  E2E). `None` 버튼(「HOME 기준」)은 버튼 칸에 글자 표지(`NONE_OPTION`)로 든다. `persist_state` 를 주지 않는다. 켜진 버튼
  주의 색(`tone="warning"`)은 1.63 pills 의 켜진 단추 `button[role="radio"][aria-checked="true"]`(`ACTIVE_PILL_SELECTOR` — 옛
  `stBaseButton-pillsActive` testid 는 그리지 않는다)에 걸고, 면색 위 글자는 `TEXT` 다.
- `src/capa_simulation/components/constraint_simulation_figures.py` — 제약 시뮬레이션의 월별 확보율 그래프(수 축 — 개조
  비가동 막대를 W/D 구간 날짜 비례로 놓는다, 표적 막대가 달 누름을 받는다)와 월별 계산표(`month_sheet_canvas` 엔진)를 계산
  결과에서 만드는 순수 함수. 새 색 토큰 없이 기존 토큰에 도형 `opacity` 를 준다(제약 기간 칠·고른 달 띠). 주의 색
  (`STATUS_WARNING`)은 면색이라 글자에 쓰지 않는다 — 오른쪽 끝 「제약 n%」 는 `TEXT`, 제약 제품 점은 `LINE` 테두리. 오른쪽
  끝 두 글(「기준 …」 · 「제약 n%」)은 같은 x 라, 그림 칸이 가장 낮을 때(`END_LABEL_MIN_PLOT_PX` — 범례 줄 수로 칸 높이가
  바뀐다) 두 선이 글 한 줄보다 가까우면 큰 값은 선 위·작은 값은 선 아래로 비킨다(`end_label_anchors` — 같으면 「제약」 이
  위, 2026-10-25 E2E 에서 7px 포개짐·한 글 숨음). 그림 모양을 바꾸면 `CONSTRAINT_FIGURE_SCHEMA_VERSION` 을 올린다.
- `src/capa_simulation/components/constraint_simulation_view.py` — 제약 시뮬레이션 본문 프래그먼트(`constraint_sim_view` —
  비중 토글·그래프·계산표·고른 달 계산 다섯 단계·개조 일정·가용이 모자란 달)와 요약 넷. 달 누름은 두 그림의 `on_select`
  **콜백**이 한 칸(`CONSTRAINT_MONTH_KEY`)에 적고 세대 한 칸을 두 그림이 나눠 써 마지막 누름이 이긴다. 다섯 단계의 식(1단계
  「소요 = 기존 + 제약」·2단계 「소요 × % = 곱」·4단계 「가용 − 개조 중 − 배정 = 기존 가용」·5단계 「가용 ÷ 소요 = 확보율」)은
  **적힌 수로 다시 셈해도 적힌 결과**가 나와야 한다 — 둘째 자리로 깎은 인수로 어긋나면 그 식의 인수만 한 자리씩 더
  적고(`_consistent_digits`, 여섯째 자리까지), 그래도 못 맞추면 둘째 자리로 적고 등호를 「≈」 로 둔다. 그림은 세션 memo(4칸 —
  키는 계산 결과 값·화면 글자·고른 달·토글·세대·테마)다. 위 줄(그래프 카드 + 고른 달 계산 카드)은 가로 컨테이너 하나(3 : 2)이고
  줄이 `TOP_ROW_STACK_BELOW_PX`(900px)보다 좁으면 컨테이너 질의로 위아래로 쌓는다(`top_row_style` — 사이드바를 편 900px 창에서
  3 : 2 그대로면 그래프 그림 칸이 169px 로 줄어 달 누름이 어려웠다). 그래프는 카드 안 스크롤 상자 → 캔버스에 서고 캔버스는
  폭을 고정하지 않고 가장 좁은 폭만 건다(`chart_min_width_px` — 좌우 여백 + 달 수 × 세운 달 한 칸 `MONTH_SLOT_PX` 13px) —
  카드가 그보다 좁으면(390px 창) 상자가 가로로 스크롤한다(그림 칸이 199px 로 줄어 세운 달 눈금 30개가 포개졌다, 2026-10-25
  E2E). 눈금은 솎지 않는다 — 서버는 칸 폭을 모른다. 규칙은 위 줄 배치와 같은 스타일 칸(`top_row_style(달 수)`)이라 이벤트 칸은
  스타일만 든 `st.html` 넷(위 줄 배치 + 공정 Capa 상세와 같은 계산표 틀 셋) 그대로다.
- `src/capa_simulation/components/shortening_progress_panel.py` — 필요 단축 일정 진척 비교의 기준선 고르기·저장·지우기와
  요약·두 줄 카드(`required_shortening_panel` 이 부른다).
  - 「비교 안 함」 은 센티널 `NO_COMPARISON` 이다(pop 금지). 저장 성공 때 이름 칸·폼·팝오버 key 세대를 함께 올리고
    콜백은 그린 회차의 세대가 다르면 쓰지 않는다(빠른 두 번 누름). 샘플·미저장 시나리오 편집은 저장을 거절한다.
  - 쓰기에 성공한 콜백은 표지를 남기고 `consume_baseline_write` 가 거둔다. 카드는 달 축 하나를 같이 쓴다.
- `src/capa_simulation/components/shortening_timeline.py` — 필요 단축 일정 타임라인의 달 축·위치·격자선·날짜 글자
  (`month_day`, 올해가 아니면 `YY.MM.DD`)를 공정 카드와 진척 비교(`timeline_months_covering`)가 함께 쓴다.
- `src/capa_simulation/components/availability_gap_figure.py` — Static 대 설비 일정 기준 월별 비교 Figure(환산 축,
  입력은 시트의 `SheetView`). 그림은 비교, 분해는 시트가 맡고 GAP 글자·색은 시트와 같은 함수(`gap_text_color`)다.
- `src/capa_simulation/components/plotly_layout.py` — 제목 주석·외곽 테두리·분기 경계·고정 행과 `hover_chart_config`·
  `static_chart_config` 등 Figure 공통 유틸리티.
  - 도형·주석은 `append_layout_items` 로 모아 Figure 를 돌려주는 쪽이 `flush_layout_items` 를 한 번 부른다(빠뜨리면
    테두리·라벨이 사라진다, `tests/test_plotly_layout.py`). flush·`figure_from_spec` 의 빠른 경로는 비공개 `_validate`
    라 `plotly>=5.24,<7` 에 기댄다(`tests/test_plotly_fast_path.py`).
  - 표 칸 글자를 표 밖에서 그리는 도우미 — `table_text_layer`(`TableText` 벌마다 글자 trace 와 숨긴 축. 넘칠 수 있는
    글자(`table_text_max_width_px`)만 그 열을 덮는 축 `xaxis2`… 에 얹어 `go.Table` 처럼 열 경계 ±1px 에서 자른다.
    자르는 축이 있으면 `plot_bgcolor` 는 투명이다 — 겹치는 축 바탕이 `layer: below` 도형을 덮는다), `table_text_y`
    (마크업 칸 기준선 = cellPad + 1.08em, 맑은 고딕 어센트), `table_header_band`. `figure_from_spec` 빠른 경로는
    table·scatter trace 와 번호 붙은 축을 받는다(`tests/test_table_text_layer.py`).
- `src/capa_simulation/components/home_figures.py`, `home_figure_common.py`, `home_lob_figures.py`,
  `home_plan_detail_figures.py`, `home_key_process_figures.py`, `home_bottleneck_figures.py`, `home_rendering.py`,
  `home_dimensions.py` — HOME Figure 가족 넷·공통 조각·캐시와 렌더링·픽셀 치수.
  - `home_figures.py` 는 코드 없는 import 파사드다(새 공개 이름은 `__all__`·재수출을 같이, `capacity_status` 는
    `services/securement_threshold.py` 의 것).
  - 캐시는 세션 칸 → 공용 저장소, 묶음 넷이다. 묶음 키는 `home_rendering` 의존 표가 정본이라 조건을 더하면
    `tests/test_home_figure_cache.py` 의 `EXPECTED_DEPENDENTS` 도 고친다(`tests/test_home_figure_cache_equivalence.py`·
    `tests/test_home_hidden_main_figures.py`). 그림 모양을 바꾸면 `HOME_FIGURE_SCHEMA_VERSION` 을 올린다.
  - 계획 세부수량은 `go.Table` 없이 면색 도형 + 글자 trace(data[0] 머리글, data[1] 값, 그 뒤 자르는 trace)다. 긴
    제품명·거래선은 제 칸 경계에서 잘린다. 머리글 띠 도형은 `plotly_layout.table_header_band` 하나다.
- `src/capa_simulation/components/month_sheet_canvas.py` — 월 시트 캔버스 엔진(라벨·월 Figure 한 쌍의 `Row`·
  `Cell`·글자·표적·서식·`canvas_point`). 공정 Capa 상세·비교 시트·제약 시뮬레이션 계산표 셋이 훅(`row_hook` 등)으로 쓰는
  순수 함수다.
  - 풍선 글이 빈 칸은 둘째 표적 trace(`hoverinfo: "none"`)다 — 풍선 상자 없이 누르면 골라진다. `Row.label_hover` 를
    준 행만 라벨 Figure 에 줄 이름 칸 풍선 표적이 서고, 없으면 라벨 Figure 에 trace 가 없다.
- `src/capa_simulation/components/availability_sheet_canvas.py` — 비교 시트 9행(`SheetView`)을 엔진으로 그리는 순수
  함수. GAP 은 면 없이 글자색만 쓰고(상태 3색 아님) 「—」 칸은 풍선 까닭(`REASON_TEXTS`)을 단다.
- `src/capa_simulation/components/availability_sheet_keys.py` — 비교 시트 key(`GAP_SHEET_CHART_KEY` 등)를 가벼운 모듈에
  둔다 — `app.py` 가 패널·서비스를 import 하지 않고 터치 스크롤 막이(`components/plotly_touch_scroll.py`)에 넣게.
- `src/capa_simulation/components/process_capa_canvas.py` — `공정 Capa 상세` 결합 월 캔버스(① 공식 요약 ② 설비 일정 기준
  가용 ③ 신규 호기 ④ 비가동)의 순수 그림 함수 `build_process_capa_canvas`. 세션·캐시·DB 를 보지 않는다.
  - 라벨·월 Figure 한 쌍이라 부족 띠·보는 달 열이 구획을 넘고 칸 선택이 그림 하나에서 온다. 판정색은 요약 프레임 `판정`
    한 길이다. 칸은 `base` 막대 + 표적 막대(`HIT_TARGET`)이고 엔진 상수·`canvas_point` 를 이 모듈 이름으로도 내보낸다.
  - 접힌 구획(`collapsed`, id `SECTION_IDS`)은 제목 줄(▸)만 남는다 — 판정·원인은 요약에서 내 ① 을 접어도 부족 띠·판정
    대조가 같다. 호기 라벨에 「N모듈」 을 적지 않고 풍선(「· 모듈 N」, ④ 는 줄마다 모듈 설비명)에 둔다.
  - ③ 호기 풍선은 세 줄(호기 · −N일 · Model / Qual → 목표 · 기여 / 해소 · ⚠ — UPEH 가정 계획만 넷째 줄)이고 그
    호기 그림이 걸친 달 칸(`_unit_marks` → `_unit_span`, 그림과 한 자리 — 표지는 반지름까지, 붙은 글자는 어림 폭의
    `_SPAN_TEXT_SHARE` 몫까지)과 줄 이름 칸에서만 뜬다. 빈 달 칸은 풍선 없이 누르면 그 달이다. 해소 기여 월은 해소
    눈금이 서는 줄(단축 · 추가N)만 적는다. 라벨 Figure 는 그 풍선이 있을 때만 hover 를 켠다(`process_capa_view`).
  - `assumption`(UPEH 가정)이면 ① 끝에 세 줄(구간 달만 값)이 서고 부족 띠·② 판정 대조는 가정 요약의 판정이다. 표지는
    바뀌는 행의 라벨·풍선에만(② 가용·전월 대비·④ 제외, 제목 줄 높이 그대로), 공식에서만 당긴 호기는 ③ 흐린 줄이다.
- `src/capa_simulation/components/process_capa_view.py` — `공정 Capa 상세` 의 「본문 프래그먼트」
  (`render_process_detail_view`)와 KPI·정리 줄. `ProcessDetailView` 하나를 받아 지금 보는 달에 닿는 것만 그린다.
  - 칸 누름·◀▶ 콜백은 `PROCESS_DETAIL_MONTH_KEY` 를 적고 `sidebar_status.rerun_app_unless_alone` 으로 끝낸다
    (`tests/test_app_navigation.py`·`tests/test_process_capa_detail_page.py`).
  - 그림은 세션 칸(`CANVAS_MEMO_KEY`)에 기억한다(새 `st.cache_data` 없음). 근거 카드 식은 검산되어야 하고(어긋나면 `≈`)
    목표는 `target_label`(「110% (1.095)」)로 적는다.
  - 「구획」 칩(`st.pills`)은 선택지 넷을 늘 고정하고 칸이 없으면 넷 모두로 심는다(`seed_sections`). 접힘은 그림 기억
    키에 들고, 접힌 ③·④ 의 「더 보기」 는 숨는다. 화면을 옮기는 다음 화면 단추는 본문에서 옮긴다(프래그먼트 콜백 금지).
  - UPEH 가정 토큰도 그림 기억 키에 든다. KPI 는 가정 요약 값에 회색 줄 「공식 n」, 근거 카드 ① 은 구간 달에 가정 한 줄,
    ③ 은 구간 달이면 머리 식·판정·원인을 가정 요약으로 내고(식 첫 줄 「소요 = 공식 ÷ f」) 공식 판정은 회색 「공식: …」 한
    줄이다 — 같은 패널의 다음 화면 줄과 같은 기준.
- `src/capa_simulation/components/scenario_management.py`, `bigdataquery_registration.py`, `auto_official_update_tab.py`
  — 시나리오 관리 페이지의 세 탭 UI.
  - 저장 폼 칸은 성공한 회차에만 key 세대를 올린다. 원본 리비전 메모(`SOURCE_MEMO_KEY`)는 목록 요약이 같을 때만 쓴다.
  - 리비전명 변경은 `save_revision_names`(카드 리비전 표, 한 건은 `save_revision_name`)를 거친다 — 저장소의 비교 후
    쓰기(`rename_revisions`·`rename_revision`, 다른 사용자가 먼저 바꿨으면 `BatchEditRefused`·`RevisionNameMoved`) 뒤
    스냅샷 캐시·파생 원본 메모를 비우고 이 세션 이름표만 고친다(활성화하지 않는다).
    시나리오 「최근 수정」·공식 이력·비교 프로필은 건드리지 않는다(`tests/test_revision_rename.py`).
  - 맨 위 알림·두 건 체크 경고는 늘 서 있는 칸 안에 그린다 — 보관함 상자(key 있음) 앞 순번이 알림 때문에 밀리면
    본문 `st.rerun()` 뒤 흐린 사본이 남았다(9장 「key 가 있어도 자리는 고정한다」).
  - 파생·월 머지·연도 이동은 화면(`components/scenario_transform.py`·`components/scenario_month_merge.py`·
    `components/scenario_year_shift.py`)과 규칙(`services/scenario_transform.py`·`services/scenario_month_merge.py`·
    `services/scenario_year_shift.py`·`services/scenario_virtual_products.py`)으로 나뉜다.
  - `auto_official_update_tab.py` 설정은 버전 대조(칸에 key 없음), `bigdataquery_registration.py` 목록은 `st.form`
    밖·등록 폼 위의 `st.dataframe(on_select="rerun")` 이다. 등록 폼 글자 칸은 입력 초안이라 `persist_state` 가 없어
    그리지 않은 회차에 버려진다 — 목록 선택(위젯 아닌 칸)만 남았으면 위젯 앞 `_restore_dropped_prefill` 이 그 선택의
    값으로 다시 채운다(날짜 두 칸은 세션에 남으므로 건드리지 않는다).

### 영속성 모듈

- `src/capa_simulation/persistence/snapshot_export.py` — DuckDB 스냅샷 내보내기와 받은 스냅샷 검증·설치. 라이브
  `.duckdb` 를 바이트로 읽지 않고(COMMIT 이 `.wal` 에만 있을 수 있다) `ATTACH` + `_sql_helpers.copy_database()` 를 쓴다
  (구조는 `COPY FROM DATABASE … (SCHEMA)`, 데이터는 외래 키 부모 표부터 — `scripts/compact_duckdb.py` 와 같은 길).
- `src/capa_simulation/persistence/sync_state.py` — DB 옆 `.sync.json` 사이드카에 원격 세대·미반영 변경을 기록한다(DB
  안은 순환, 메모리는 죽으면 사라진다). `enable()` 전에는 파일을 만들지 않고 못 읽는 사이드카는 「변경 있음」 이다.
- `src/capa_simulation/persistence/repository.py` — `DuckDBScenarioRepository` 의 입력 검증·연결·쓰기 잠금·트랜잭션
  경계. 커밋과 변경 신호는 Repository 만 갖고 store 는 열린 연결을 받는다.
  - 교체 실패 시 행·버전을 복구하고 신호를 내지 않는다. 바뀐 것이 없는 쓰기(`initialize_global_display_order` 등)는
    트랜잭션을 열지 않는다. `load_revision_table` 은 확인·읽기를 한 트랜잭션에서 하고 없으면 `KeyError` 다.
- `src/capa_simulation/persistence/models.py` — Repository 가 주고받는 타입.
- `src/capa_simulation/persistence/display_order_store.py` — 공용 표시순서 프로필의 검증·이관·저장.
- `src/capa_simulation/persistence/process_rename_store.py` — 공용 공정 표시명 프로필의 조회·교체 SQL.
- `src/capa_simulation/persistence/advance_load_store.py` — 공용 선행 B/O 프로필(`0018`)의 조회·교체 SQL.
- `src/capa_simulation/persistence/advance_shipment_store.py` — 공용 선행 입고 실적 프로필(`0031`)의 조회·교체 SQL.
- `src/capa_simulation/persistence/securement_threshold_store.py` — 공용 확보율 판정 기준 프로필(`0029`)의 조회·교체
  SQL과 버전 대조(`SecurementThresholdConflict`). 미저장일 때의 기본값은 Repository 가 정한다.
- `src/capa_simulation/persistence/auto_official_update_store.py` — 공식버전 자동 갱신(`0035`)의 설정(버전 대조)·변경
  기록·실행 기록·자동 off 기록 SQL. `run_key` 유일이 회차 선점이고, 소유 컬럼이 없어 시나리오를 지워도 남는다.
- `src/capa_simulation/persistence/execution_capacity_store.py` — 공용 확보율 보정 프로필의 조회·교체 SQL.
- `src/capa_simulation/persistence/key_process_store.py` — 공용 주요공정 프리셋 프로필(`0024`·`0028`)의 조회·교체 SQL.
  맨 앞 프리셋이 기본, 공정 차례가 행 순서다.
- `src/capa_simulation/persistence/home_profile_store.py` — HOME 공용 Top5 구간·공지·GAP 비교 대상(`0020`)·주요
  Case(`0036`)의 조회·교체·해제 SQL.
  - 주요 Case 는 한 행에 Case 마다 칸 둘(`case1_scenario_id`…)이다. 칸 이름이 `scenario_id` 가 아니라 `_owned_tables`
    자동 발견에 걸리지 않고, 보관·영구 삭제는 그 시나리오를 가리키는 Case 만 비우며 출처 칸에 까닭을 적는다
    (`clear_global_main_cases` — 「Case2 지정 비움 — 시나리오 보관」). 가리키는 시나리오·리비전의 이름 바꾸기는
    version 만 올린다(`touch_global_main_cases`·`touch_global_main_cases_revision` — 슬롯 글자가 둘 다 싣는다). Case
    하나 교체는 다른 Case 를 같은 트랜잭션에서 옮겨 적는다.
- `src/capa_simulation/persistence/voc_store.py` — VOC 게시판 글·답글의 조회·삽입·삭제 SQL.
- `src/capa_simulation/persistence/shortening_baseline_store.py` — 필요 단축 일정 기준선(설비 DB `0021`)의
  넣기·목록·읽기·지우기 SQL(UPDATE 없음)과 칸 매핑(`BASELINE_UNIT_DB_COLUMNS`). 설비 쪽 출처 칸 넷(`0027` —
  `equipment_schedule_revision_ref`·`_no`·`equipment_scenario_name`·`equipment_release_no`)은 가리키기만 한다.
- `src/capa_simulation/persistence/floor_state_store.py` — Space 동·층 사용 상태(설비 DB `0029` — 머리
  `floor_state_profile`, 층 `floor_state` 행 = 비활성 층·PK (동, 층))의 읽기·쓰기 SQL. 쓰기는 같은 트랜잭션에서 읽은 저장본과
  견줘 **바뀐 층만** 고친다(다시 켠 층 DELETE · 사유만 바꾼 층 키 아닌 칸 UPDATE · 새로 끈 층 INSERT — 같은 키를 지웠다 넣지
  않는다). 읽기는 30개 층 밖 행을 버리고 머리 없는 층 행은 version 0 으로 싣는다.
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
- `src/capa_simulation/persistence/preset_store.py` — 리비전이 소유한 조회·판정 프리셋의 저장·복원.
- `src/capa_simulation/persistence/source_data_store.py` — 데이터셋이 소유한 원천 Core Data raw 와 컬럼 프로파일 저장.
- `src/capa_simulation/persistence/summaries.py` — 조회 행을 요약 모델로 바꾸고, 요약 SELECT 투영
  (`SCENARIO_SUMMARY_SELECT` 등)을 매퍼 옆에 두어 열 순서와 row 인덱스가 짝을 이룬다.
- `src/capa_simulation/persistence/_sql_helpers.py` — 프레임 저장·조회·값 변환과 트랜잭션 경계 공용 헬퍼. 두 Repository
  와 `_migration_core` 가 `transaction()` 한 벌을 쓰고, 공용 프로필 버전 대조 `require_profile_version()`
  (`ProfileVersionConflict` — 기본 스키마 `app_meta`, 설비 DB 층 사용 상태는 `schema="equipment_ops"`)과 감사 해시 `hash_frame()`(`tests/test_sql_helpers.py`)이 여기 있다. DB 통째 복사
  `copy_database()`(외래 키 부모 표부터)도 여기 있어 스냅샷 내보내기와 `scripts/compact_duckdb.py` 가 함께 쓴다.
- `src/capa_simulation/persistence/_migration_core.py` — 두 DuckDB 가 함께 쓰는 마이그레이션 적용 엔진(버전 순
  읽기·체크섬 대조·건별 트랜잭션).
  - DB 가 코드보다 새 것이면(옛 배포 ZIP 으로 되돌림) 막지 않고 `MigrationOutcome.schema_ahead`(`SchemaAheadOfCode`)로
    알린다. 최고 번호끼리만 견주어 결번 2·3 은 알리지 않는다. 화면 경고(`page_bootstrap.render_schema_ahead_warning`)는
    시뮬레이션 DB 는 `app.py`, 설비 DB 는 그 DB 를 여는 화면이 세운다.
- `src/capa_simulation/persistence/migration_runner.py`, `equipment_migration_runner.py` — 각 DB 를 엔진에 묶는 진입점.
- `src/capa_simulation/persistence/cache.py`, `equipment_cache.py` — 불변 리비전 스냅샷·공용 프로필 열두 종과 설비
  스냅샷·층/FAB 도면·설비 마스터 탭 이력·필요 단축 일정 조건·기준선의 Streamlit 캐시 경계.
  - 키는 불변 id 나 DB 경로이고 저장 길이 맞는 `clear_*` 를 부른다(판정 기준은 공식버전 지정 때도,
    `clear_floor_layout_cache` 는 층과 FAB 를 함께).
  - 덮어쓰거나 지울 수 있는 값을 담는 캐시(시뮬레이션 공용 프로필·리비전 스냅샷·비교 계획, 설비 최신 id·Cut-off·
    주차별 가용대수·층/FAB 도면·층 사용 상태·필요 단축 일정 조건·기준선)는 키에 쓰기 세대(`WriteGeneration`)를 두고 `clear_*` 가
    `.clear()` 앞에서 그 종류의 세대를 올린다. `.clear()` 는 진행 중인 캐시 미스를 막지 못해, 저장 직전에 시작된 다른
    세션의 읽기가 비운 뒤 옛 값을 다시 심는다(TTL 없는 프로필은 다음 저장·재시작까지 남는다). 새 캐시도 같은 세대를 쓴다.
  - 「지금 저장된 값」 읽기(`latest_equipment_revision_id`·`load_process_cutoff`·`load_standard_target_availability`·
    `load_floor_states`)는 (DB 경로, DB·WAL stat, 쓰기 세대) 키에 TTL 15초다. 층 사용 상태(`0029`, 세대 `"floor_state"`)는
    다른 PC·동기화로 받은 DB 의 변경도 회차 안에 보여야 하는 공용 설정이라 이 꼴이고, 도면 캐시와 묶지 않는다 — 저장 길(Space
    층 목록 저장 콜백)이 `clear_floor_state_cache()` 를 부르고 `clear_equipment_repository()` 도 부른다. 1차 장치는 비우기라 새 쓰기 길을 더하면 같은 비우기를 부른다.
  - 설비 쪽은 **리비전 내용(불변)과 바뀔 수 있는 것**을 나눈다. 합친 본문 `_load_merged_payload`(공개
    `load_merged_equipment_snapshot`)는 (DB, 공통 id, 일정 id) **쌍 키**에 세대가 없다(`MERGED_SNAPSHOT_CACHE_ENTRIES` 16칸).
    설비 시나리오 목록(`load_equipment_scenario_catalog` — 시나리오·각 최신·리비전 수·최신 발행·흔적 수)과 시나리오 리비전
    목록(`load_equipment_schedule_revisions`)은 (DB, stat, 세대 `"equipment_scenario"`) 키에 TTL 15초, 8칸이다. 공식 스냅샷
    (`load_official_equipment_snapshot`)은 공통 최신 id + 목록의 최신 발행 → 합친 본문이라 발행만 바뀌어도 다른 쌍 키로 간다.
    CSV 바이트도 쌍 키다. 이름·리비전명·발행·복제·되돌리기·이어 쓰기 뒤에는 `clear_equipment_scenario_cache()` 만, 설비 마스터
    저장 뒤에는 `clear_equipment_snapshot_cache()`(앞의 것까지 부른다) — 호출부가 비운다. 「다른 ACTIVE 시나리오 최신에 일정이
    있는 호기 키」(`load_units_scheduled_elsewhere` — 설비 마스터 탭 호기 삭제 확인 재료, 지운 호기가 있는 회차에만 읽는다)도 목록과
    같은 세 장치(세대 `"equipment_scenario"`·stat·TTL)다(배치 차이 행만 있는 호기도 든다). Space 층 사용 끄기 확인의 덧줄
    재료 `load_layout_overlay_floor_counts`(층마다 — ACTIVE 가정 시나리오 최신의 그 층 차이 호기 행 수)도 같은 세 장치이고, 층
    캔버스 팝업 미리 보임 `load_layout_overlay_extent`(층마다 — 캔버스 저장이 보는 리비전의 차이 요소 범위·차이 호기 상자,
    S4)는 그 세 장치에 층 현행값 세대 `"floor_layout"` 을 더한다. 공식 발행 확인의 배치 판정 `load_layout_publish_preview`(S4 —
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
  - 복제(`clone_equipment_scenario` — 출처는 그 시나리오의 **어느 일정 리비전이든**(E7 「여기서 새 시나리오」), SQL 사본이
    아니라 지금 공통과 합친 읽기 길로 읽은 일곱 칸·비가동을 새 두 표에, `origin='clone'`. 지금 공통과 합쳐지지 않는 옛 리비전은
    `EquipmentScenarioIncompatible`. 출처 리비전의 배치 차이도 지금 공식으로 정규화해 옮긴다)·이름(`rename_equipment_scenario` — 보관본까지 중복 금지, `expected_name` 대조 →
    `EquipmentScenarioNameMoved`)·발행(`publish_equipment_release` — append-only)·이어 쓰기(`acknowledge_legacy_trace` — 흔적 수
    대조 뒤 경계 행 하나)가 1단계 관리 쓰기다.
  - **E7 리비전 도구**: 리비전명(`rename_schedule_revision` — 이름표 한 칸만 UPDATE, 비우면 NULL, 비교 후 쓰기 →
    `EquipmentScheduleRevisionNameMoved`, 같은 이름이면 쓰지 않음, 보관 시나리오 거절)과 되돌리기(`restore_schedule_revision` —
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
  - **발행이 하나도 없으면** 일정 리비전을 만드는 첫 저장이 「공식으로 발행」 체크와 무관하게 공식 v1 이다(저장 칸은 체크 대신
    그 한 줄 — `render_equipment_save_fields(release_exists=False)`).
  - **호환 래퍼**(시험·스크립트용 — 화면·캐시는 부르지 않는다): `save_snapshot`·`save_space_layout` 은 공식 시나리오에 늘
    공통 v4 와 일정 리비전을 함께 써 같은 트랜잭션에서 발행한다(래퍼만 쓰면 공통 rN 과 운영 일정 rN 이 같은 번호로 오른다).
    `load_snapshot(공통 id)` 은 그 공통을 `common_revision_id` 로 가진 공식 시나리오 일정 리비전 마지막 것과의 짝이고, 짝이
    없으면 최신 공식 발행 일정이다. `list_revisions()` 는 공통 대장 이력이고 v4 공통의 비가동 행 수는 0 이다(비가동은 일정
    리비전 요약이 센다).
  - 최신 리비전·캔버스·요소는 쓰기 잠금 안에서 읽고 출발 리비전·`floor_layout_bases`·FAB `base` 가 다르면 거부한다. 안 쓴
    저장은 dirty 를 세우지 않는다.
  - 층 Main 설비명 위치(`floor_layout_group_label`, `0025`)는 `floor_group_labels`(층마다 전체)로 같은 트랜잭션에 쓰고
    층 대조(`floor_layout_bases`)가 요소와 함께 본다. 영역 테두리 모양·이름표 정렬은 두 요소 표의 `border_style`·
    `label_align`(`0025`, 영역 아닌 요소는 NULL)이다.
  - 캔버스를 바꾸는 길은 모두 요소가 새 캔버스 안인지 본다(`_require_marks_fit`). 네 진입점(설비 저장의 캔버스·
    `save_floor_layout_canvas`·`save_floor_layout_image`·`delete_floor_layout_profile`)은 각 ACTIVE 설비 시나리오 최신·최신 공식
    발행의 **가정 요소**(`set`)도 본다(`_require_overlay_marks_fit` → `EquipmentLayoutOverflow`). 가정 차이 호기는 막지 않는다 —
    공식 호기처럼 그 시나리오의 다음 저장만 막힌다. 기준선(`0021`)은 갈아 쓰지 않는다. FAB
    도면은 `fab_layout_profile`·`fab_layout_mark`(`0013`)다.
  - 층 사용 상태(`load_floor_states`·`save_floor_states`, `0029`)는 리비전을 만들지 않는 공용 현행값이다 — 쓰기 잠금 안에서
    `require_profile_version(schema="equipment_ops")` 로 화면이 본 version 을 먼저 대조하고(내용이 같아도 version 이 다르면
    충돌), 같은 내용이면 쓰지 않는다(`wrote=False` — version·dirty 그대로). 설비 시나리오·리비전·공식 발행·옛 배포 흔적 잠금과
    무관하다.

### 저장소 루트의 발표 자료

- `index.html` — 이 저장소의 **유일한** 발표 자료(대표 발표 자료 한 파일, 지금은 혁신대회 덱). 외부 요청 없는 단일
  파일이라 사내 GitHub Pages·배포 ZIP 에 실리고 숫자는 합성 샘플이다. 앱은 이 파일을 쓰지 않는다.
- `src/capa_simulation/components/intro_overlay_assets/capa-teaser.html` — 입장 화면 `Introduce` 가 띄우는 40초 티저
  (2026-10-19 사용자 결정). 원본은 쇼케이스 `contest/dist/capa-teaser.html` 이고 `index.html` 과 같은 규칙으로 CR 을
  빼 복사한다. 외부 요청 없는 한 파일이어야 사내 오프라인에서 선다.
  - 원본·빌드·자료는 저장소 밖 `~/projects/capa-simulation-showcase`(덱 `contest`·바이블 `bible`·중간 보고
    `build`·Learning Champion 초안)가 그 폴더의 `CLAUDE.md`·메모리·세션으로 맡는다. 다른 발표 파일은 여기 넣지 않는다.
  - 원본은 쇼케이스의 `contest/dist/capa-contest.html` 이고 `capa-contest.artifact.html`(아티팩트용 변형)은 쓰지 않는다.
  - 두 폴더는 서로 읽되 쓰지 않는다. `index.html` 을 바꿀 때만 이 저장소 세션이 CR 을 빼 복사해
    (`tr -d '\r' < ~/projects/capa-simulation-showcase/contest/dist/capa-contest.html > index.html`) 커밋한다. 저장소는
    `.gitattributes` 로 LF, dist 는 CRLF 라 견줄 때도 CR 을 뺀 뒤 견준다.
  - 발표자 실명은 그대로 둔다 — 다시 묻지 않는다.

## 4. 기준정보 테이블 계약

Excel Table 이름, Power Query 결과명과 코드의 키는 `RQ_` 접두사를 사용한다.

### 활성 시나리오에서 수정 가능한 테이블

```text
RQ_PKG_PLAN
RQ_YLD
RQ_UPEH
RQ_RUN_RATE
RQ_VITAL
RQ_RUN_DAY
RQ_LOT_RATIO
RQ_WF_RATIO
RQ_REQB
RQ_EQP_OWN
RQ_EQP_LENT
RQ_EQP_AVBL
RQ_CHIP_QTY
RQ_CHIP_EQ
```

`RQ_PKG_PLAN` 업무 키는 계약 `derived_keys` 의 8키다 — 7키에 `Pack Code` 가 더해진다.
같은 7키 안에서 생산수량을 가르는 값이라 **저장과 편집은 행을 나누고, 합산은 계산 계층이**
한다. 부하량·소요대수·HOME 은 Pack Code 없는 키로 `groupby` 하고, PKG 환산은
`_prepare_pkg_plan_for_equivalent` 가 7키 합계로 접는다. 변환기나 `validated_distinct` 에서
합산하지 않는다 — 거기서 접으면 편집 왕복에서 Pack Code 별 수량을 되살릴 수 없다.

웹 수정은 반드시 `apply_month_updates()`를 통해 반영한다. 페이지 전용 DataFrame만
수정하고 끝내면 다른 페이지와 계산 캐시에 변경이 전달되지 않는다. 월 축(`생산계획년월`)이
없는 `RQ_CHIP_QTY`·`RQ_CHIP_EQ`는 `apply_table_updates()`로 통째로 교체한다 —
`apply_month_updates()`에 넘기면 `생산계획년월 컬럼이 없습니다`로 거부된다. 적용에 넘기는 월 창은 편집표를 자른
월 창과 같아야 한다 — 다르면 적용이 화면에 없던 월을 지운다(기준 정보는 선택기간 ∩ 활성 리비전 UPEH 범위).

빈 `설비대여평가`(`RQ_EQP_LENT`)는 등록 때 **0 대**로 적고, 그래서 빈 가용대수(`RQ_EQP_AVBL`)는 `보유 − 0` 으로
채운다(설비대수 편집기의 「빈칸은 0 대」와 같은 규칙, 빈 보유대수는 빈 값 그대로). 이 보정과 `RQ_REQB` 경로 중복
접기(6장)는 XLSB Power Query 결과와 일부러 다르며, Power Query 대조 스크립트는 같은 보정을 건 뒤 견준다.

### 읽기 전용 참조 테이블

```text
RQ_DISPLAY_ORDER
RQ_MODULE
```

`RQ_DISPLAY_ORDER`는 계산 페이지에서 읽기 전용이지만 `표시순서 관리`에서는 시나리오와
분리된 공용 DB 프로필을 수정한다.

**저장 위치가 둘로 갈린다.** 위 수정 가능한 14개는 리비전(`rev_data`)에만, 이 두 표는
데이터셋(`ref_data`)에만 산다(`repository.REVISION_TABLES`·`DATASET_TABLES`). 시나리오를 만들
때 14개를 데이터셋에 한 번 더 적던 사본은 2026-10-06 사용자 결정(B3)으로 없앴다 — 그 전에 만든
데이터셋의 사본은 리비전 1 과 행 단위로 같으면 마이그레이션 `0033` 이 지우고(2026-10-10 사용자 승인),
리비전 1 과 다른 사본만 남는다. 남은 사본을 읽는 코드는 없다(`docs/data_model.md`).

나머지 테이블을 웹에서 수정할 필요가 생기면 단순히 session state에 별도 복사하지 말고 활성
시나리오의 editable table 계약과 저장 정책을 함께 변경한다.

## 5. 상태와 캐시 불변조건

1. **기준정보를 페이지별로 다시 읽지 않는다.** 모든 계산 페이지는
   `get_effective_reference_tables()`를 사용해 활성 DuckDB 리비전만 읽는다.
2. **서버 공통 데이터와 사용자 데이터를 구분한다.** 불변 DuckDB 리비전과 동일 입력 계산
   결과는 서버 캐시, 웹 편집값은 `st.session_state`의 활성 시나리오다.
3. **편집 적용마다 `revision`을 올리고 `content_token`을 재발급한다.** 편집 UI(위젯 초기화·
   미저장 감지)는 `revision`을, 계산·Figure 캐시 키는 `content_token`을 본다 — `revision`
   번호는 내용이 달라도 겹칠 수 있다(세션 편집 0,1,2… 와 저장 리비전 번호). 편집 없는
   상태(리비전 활성화·원본 초기화)는 리비전에서 나온 고정 토큰이라 세션끼리 캐시를 나눈다
   — 리비전 **내용**은 append-only 라(이름표인 리비전명만 고칠 수 있다, 아래 8) 같은 리비전이면 내용이 같다. 모듈수(`RQ_MODULE`)는 리비전이
   아니라 시나리오 dataset 에서 오지만, dataset 은 시나리오를 만들 때 한 번 쓰이고 그 뒤로는
   앱 시작 때의 마이그레이션만 고치므로 같은 전제가 선다. 계산 캐시는 **시나리오 전체 기간**
   단위이고 조회기간은 그 결과를 자른다. **큰 DataFrame 을 `st.cache_data` 의 해시 인자로 넘기지 않는다** —
   Streamlit 1.63 은 5만 행 넘는 DataFrame 인자를 1만 행 표본(`df.sample(10_000)`)으로만 해시해, 표본 밖 한 행
   편집이 옛 결과에 적중한다. 그런 프레임은 `_` 인자로 넘기고 키에는 그 내용을 정하는 `content_token`(시나리오
   키)이나 `frame_digest` 를 싣는다.
4. **계산 함수는 가능한 순수 함수로 유지한다.** 서비스 함수 내부에 UI 상태 접근을 넣지
   않는다. Streamlit 캐시는 정해진 경계 모듈에만 둔다 — `services/simulation_cache.py`,
   `persistence/cache.py`·`equipment_cache.py`(불변 리비전 스냅샷과 공용 표시순서·설비
   스냅샷), 그리고 `components/` 의 `display_order_management.py`·
   `process_rename_management.py` 다. 뒤의 둘은 탭 국소 예외로, 공용 프로필 `version` 만
   키로 쓰고 DB 를 읽지 않는 CSV 직렬화다(항상 그리는 탭이라 그 비용이 모든 rerun 에
   실린다). 그 밖의 모듈에 `@st.cache_data`·`@st.cache_resource` 를 새로 두지 않으며,
   이 예외를 늘리려면 여기 목록을 같이 고친다(`tests/test_cache_boundaries.py` 가 경계 밖 캐시와 3 의 새 DataFrame
   해시 인자를 막으므로 그 시험의 목록도 함께). `persistence/` 는 이 경계 밖에서 Streamlit 을 부르지 않는다 —
   화면에 알릴 DB 상태(`schema_ahead` 등)는 저장소 속성으로 두고 화면 쪽(`page_bootstrap`)이 그린다. 직전 회차
   결과를 세션 칸에 기억해 다시 쓰는 장치(`components/wip_status_dashboard.py`)는 Streamlit 캐시가 아니라 경계 밖이고,
   입력이 같은지는 `DataFrame.equals` 로 본다 — 해시 지문은 object 칸의 `1`·`'1'` 을 같게 본다.
   **배경 스레드는 공식버전 자동 갱신 예약(`auto_update_scheduler.py`) 하나뿐**이고 캐시 경계가 아니다 —
   `st.cache_resource` 없이 스레드 이름으로 프로세스에 하나를 지키고, 스레드 안에서는 `st.*`·세션·`st.cache_data`
   래퍼를 부르지 않으며 전역 범위 `st.cache_data` 의 `.clear()` 만 부른다(9장 「배경 스레드」).
5. **공식버전은 append-only다.** 특정 시나리오·리비전을 새 공식버전으로 발행하며 과거
   공식 이력을 갱신하지 않는다. 최신 공식 시나리오는 다른 공식 발행 전 삭제하지 않는다.
   그 외 시나리오는 삭제할 수 있고, 그때 그 시나리오의 공식 발행 이력도 함께 사라진다.
6. **미저장 편집과 저장 리비전을 구분한다.** 미저장 편집은 세션 종료 후 사라지며,
   `시나리오 관리`에서 저장한 리비전만 DuckDB에 영구 보존된다.
7. **완성 Figure 캐시 키에는 출력에 영향을 주는 모든 조건을 포함한다.**
   `ActiveScenario.content_token`, reference version, 조회기간, B/N 공정 선택, 임계값, 상세
   토글 상태와 Figure schema version을 누락하지 않는다. HOME 처럼 묶음별로 키를 가르면 묶음
   키는 **그 묶음의 그림에 닿는 조건 전부**다 — 빼는 근거는 코드로 따라간 의존 표이고,
   확신이 서지 않으면 넓게 둔다(틀린 그림이 느린 그림보다 나쁘다). Plotly 는 색을 Figure 에 구워 넣으므로
   Figure 캐시는 **테마로 가른다** — 칸 이름에 테마를 넣고(`home_rendering._themed_key`) 테마가 바뀌어도 캐시를
   비우지 않는다. 비우는 방식은 `st.context.theme` 이 틀리는 순간(첫 로드·전환 직후)에 잘못 읽은 테마의 그림을 눌러앉힌다.
8. **시뮬레이션 DB 의 과거 리비전 내용을 갱신하지 않는다.** 표 14·프리셋·가상 제품 이력·입력 해시·번호·부모·저장
   시각·메모는 그대로다 — 변경은 새 전체 리비전으로만 저장하고, 과거 리비전에서 저장하면 해당 리비전을 부모로 갖는 새
   분기를 만든다. 예외는 **이름표인 리비전명** 하나다(2026-10-22 사용자 결정 — `rename_revision`·`rename_revisions`,
   비교 후 쓰기, 이력 없음, 시나리오 「최근 수정」 그대로). 계산 캐시 키·공식 발행 행(공식버전명)은 리비전명을 싣지 않아
   이름을 바꿔도 계산이 다시 돌지 않는다. 메모는 시스템 출처 기록(상세 조회기간·월 머지·연도 Shift 출처)이 들어 고치지
   않는다. 설비 DB 리비전은 이 예외가 없다 — **공통 대장 리비전**(`equipment_ops.revision`, 번호 전역)·**설비 시나리오 일정
   리비전**(번호는 시나리오마다 r1 부터)·**공식 발행**(`release_no` 전역)이 모두 append-only 이고, 고칠 수 있는 것은 설비
   시나리오 **이름**과 설비 시나리오 일정 리비전의 **리비전명**(`revision_name`, E7 — 2026-10-24 「권장대로」) 둘이다.
   리비전명은 시뮬레이션과 같은 이름표 예외다 — `rename_schedule_revision`(비교 후 쓰기, 비우면 지움, 이력 없음)이 그 한 칸만
   고치고 공식 발행 행·계산 캐시 키는 이름을 싣지 않는다. 설비 캐시는 리비전 id 키 본문이 불변이라는 전제에 서므로 **이름을 불변
   본문 캐시에 싣지 않고**(합친 본문의 `schedule.revision_name` 은 늘 None) 리비전 목록 캐시가 쓰기 세대(`"equipment_scenario"`)로
   새 이름을 읽는다 — 이름을 바꾼 화면이 `clear_equipment_scenario_cache()` 를 부른다. 「이 리비전으로 되돌리기」 는 옛 리비전을
   고치지 않고 그 일정을 새 리비전으로 다시 저장한다. 설비 `0027` 뒤 첫 저장은 무엇을 바꾸든 계약 v4 공통 한 벌을 쓴다(32).
   가정 설비 시나리오의 **배치 차이**(설비 `0031`)도 일정 리비전 내용이다 — 넣기만 하고 고치지 않는다(UPDATE·DELETE 없음,
   I1). 그래서 합친 본문 캐시의 (공통, 일정) 쌍 키가 그대로 맞고, 배치안의 이력·되돌리기·여기서 새 시나리오가 리비전으로 선다.
9. **설비 운영 이력은 시나리오와 물리적으로 분리한다.** 가용설비 현황은 전용 DuckDB,
   전용 마이그레이션·Repository·캐시와 페이지 전용 조회기간을 사용하고 저장마다 바뀐 쪽(공통 대장·설비 시나리오 일정)의
   새 전체 스냅샷을 만든다. 설비 시나리오는 설비 DB 안의 독립 시나리오이고 시뮬레이션 시나리오와 짝짓지 않는다(E1 — HOME·
   Static 확보율 `RQ_EQP_AVBL` 계산에 들지 않는다). `Summary` › `Static 대비 일정` 탭과 `필요 단축 일정` 화면과 **`Space 현황` 의
   색 기준 `필요 단축` 을 켠 동안**만 시뮬레이션 기준정보·소요대수를 읽어
   비교하며(공용 조회 조건 프로필은 설비 DB `0019`, 진척 비교 기준선은 설비 DB `0021` 이다) 설비 운영
   저장과 Main·설정·입력 화면은 시뮬레이션 DB 의 계산 데이터에 의존하지 않는다. 예외는 화면 라벨인
   공용 공정 표시명 하나다(2026-10-10 사용자 결정 — 설비 마스터 탭을 뺀 탭과 「설정」 팝업 표 보기 필터의 보이는 글자).
   페이지가 회차마다
   시뮬레이션 DB 의 그 프로필을 읽고(앱에서는 부트스트랩이 연 캐시), 못 읽으면 원본 공정명으로 그려
   설비 화면을 막지 않는다. 두 탭의
   비싼 계산(생애주기 구간 → 월별 일정 기준 가용 → Static 비교, 필요 단축 일정 계획·CSV)은
   `simulation_cache` 의 내용 지문 키 래퍼로만 부른다 — 키는 그 함수의 **실제 입력 전부**(마스터·
   비가동·기존보유·Cut-off·Static·구간의 `frame_digest`, 구간 범위, 달, 환산비 지문, 필요 단축 일정은
   시나리오 키와 오늘, 진척 비교는 그 계획 키 + 기준선 id + 목표)다. 코드 상수는 넣지 않는다(아래 15
   「키 방침」). 입력을 하나라도 빼면 낡은 값이 나오므로 새 입력을 더하면 키도 더한다
   (`tests/test_equipment_view_cache.py` 가 입력마다 키가 갈리고 캐시 결과 = 새 계산인지 본다).
   **설비 운영 스냅샷을 읽는 시뮬레이션 쪽 페이지**도 있다 — `공정 Capa 상세` 는 설비 DB 의 설비 시나리오 스냅샷(방문
   기준 — HOME 칸으로 들어온 방문은 그 방문 동안 공식, 그 밖은 세션 설비 시나리오, 32)·Cut-off 를 **읽기만** 해(쓰지 않는다,
   `PageSpec.uses_equipment_db`) 공정 하나의 소요대수와
   맞댄다(설비 일정 기준 가용·신규 설비·비가동, 참고). 계획·설비 일정은 같은 키 방침(15)의
   `simulation_cache` 래퍼(`get_required_shortening_for_target` — UPEH 가정이면 그 가정 칸, 31 —·
   `get_process_equipment_timeline`)로만 부르고,
   필요 단축 일정 화면의 공용 조회 조건(`0019`)·기준선(`0021`)·세션 칸은 읽지도 쓰지도 않는다 — 필요 단축 일정 카드에서
   들어온 방문은 **주소 인자로 받은 출처 값만 적는다**(그 카드의 목표·기간·대수). 거꾸로 공정 Capa 상세가 필요 단축
   일정으로 옮길 때 적는 것은 그 화면의 「강조 공정」 세션 칸 하나다 — 공정 필터 칸(0019 세션 값)을 심으면 사용자가 그
   [공정] 을 지울 때 빈 선택이 공용 프로필에 저장된다(2026-10-22 결함). `제약 시뮬레이션` 도 같은 예외다 — 설비 DB 의
   설비 시나리오 스냅샷(늘 세션 설비 시나리오 — HOME 방문 잠금 없음)·Cut-off 를 **읽기만** 해 공정 하나의 소요대수(제품정보로
   나눔)와 맞댄다. 계획은 공정 Capa 상세와 같은 칸(`get_required_shortening_for_target` — **공식 칸만**, UPEH 가정 토큰
   없음)으로만 부르고, `0019`·`0021`·세션 칸은 읽지도 쓰지도 않으며 **어느 DB 에도 쓰지 않는다**(시뮬레이션·설비 둘 다 —
   `tests/test_constraint_simulation_page.py` 가 두 저장소의 쓰기를 터지는 대역으로 바꿔 본다). 설비 DB 를 여는
   시뮬레이션 쪽 페이지는 다섯이다 — 표준 목표(Static, 주차별 가용대수 입력)와 공정 Capa 상세(실행 관리,
   읽기만), 제약 시뮬레이션(실행 관리, 읽기만 — 공정 Capa 상세와 같은 계획 칸, 쓰기 없음), 표준 대비 재공 현황(Dynamic,
   표준 목표의 주차별 가용대수를 읽기만), 시나리오 관리(「관리할 시나리오」 의
   「설비 시나리오」 구획을 고른 회차에만 — 설비 시나리오 목록·리비전·복제·이름·발행·이어 쓰기, 2026-10-24). 실행 관리 머리는 첫 판에서
   어느 DB 도 열지 않는다. **Space 층 사용 상태**(설비 `0029`)는 설비 시나리오·설비 리비전과 무관한 공용 현행값이다 —
   소유 칸이 없어 복제·보관·영구 삭제가 건드리지 않고, 설비 마스터의 동·층 값과 저장 검사(C1~C5·1F~6F)는 그대로다.
   **Space 현황 「필요 단축」 보기**(2026-10-24 사용자 결정)는 설비 화면이 시뮬레이션을 읽는 셋째 자리다 — **켠 동안만** 읽는다
   (끈 회차는 시뮬레이션 쪽을 한 번도 부르지 않는다 — `tests/test_space_shortening_layer_page.py` T-P1 이 모듈 속성 자리에서 센다).
   계획은 `components/shortening_source.load_official_shortening` 한 길(필요 단축 일정과 **같은 함수·같은 공식 칸·같은 키**)이고,
   설비 쪽은 Space 가 그리는 세션 설비 시나리오의 계산 세 표(설비 시나리오 2단계 LY6 — 두 화면이 늘 같은 시나리오를 따라 같은
   칸을 쓴다), 시뮬레이션 쪽은 세션 활성 시나리오·사이드바 조회기간(켠 동안 사이드바에 그 두 줄이 선다)이다. 못 읽으면 보기 안
   알림 한 줄이고 Space(도면·배치 편집·다른 색 기준)는 그대로다. 공정 표시명은 쓰지 않는다(원본 공정소분류). 필요 단축 일정
   세션 칸을 **읽고 적는 것**이 공정 Capa 상세와 다르다 — Space 는 그 화면의 시작·끝 월·목표·기한 임박 날수 칸을 **읽고**(달은
   세션 칸 → 공용 프로필 `0019` 심기를 읽기만), 「필요 단축 일정에서 이 공정 보기」 에서 강조 공정 칸과 목표 칸 **둘을 적는다**
   (공정 필터 칸·`0019`·`0021` 은 읽지도 쓰지도 않는다). 공정 Capa 상세는 위 문장대로 그 칸들을 읽지도 쓰지 않고 강조 칸 하나만
   적는다 — 둘을 서로에게 맞추지 않는다.
10. **실적 이력을 시나리오에 복제하지 않는다.** 표준 Capa는 시나리오·리비전별로 보존하고,
    실적 효율과 생산실적은 원천 갱신 주기별 배치와 등록시각을 가진 누적 이력으로 관리한다.
    분석 시 선택한 표준 리비전과 조회 시점의 실적 이력을 연결한다.
11. **내장 시드는 빈 저장소에만 쓴다.** 공식버전 또는 사용자 시나리오가 있으면 자동
    부트스트랩이 새 시나리오를 만들거나 기존 상태를 변경하지 않는다. 내장 시드는 합성
    데모이며 운영 시나리오로 간주하지 않는다.
12. **공용 필터 기본값과 개인 조회를 분리한다.** 표준 목표 Capa 공정 기본값과
    「조회·집계 설정」(시작일·종료일·상세 토글·제품 분류 수준·출력 지표)은 불변
    리비전 프리셋에 저장하고, 페이지에서 바꾼 값은 현재 세션에만 둔다. 신규 리비전 저장
    시점에만 현재 세션 선택을 다음 공용 기본값으로 캡처한다. 조회 설정은 편집 14표의
    내용이 아니므로 `content_token` 을 재발급하지 않는다. 저장된 조회일이 현재 조회기간
    밖이거나 앞뒤가 뒤집혀 있어도 예외를 던지지 않고 범위 안으로 맞춰 리비전을 연다. 새 원천 시나리오
    (BigDataQuery 등록·CSV 적재)의 초기 프리셋은 현재 화면의 필터를 복사하지 않는다 — 전체 생산계획년월과
    전체 B/N 공정을 켜고 표준 목표 공정 목록과 「조회·집계 설정」을 비워, 새 원천이 남의 조회일을 물려받지 않게 한다.
13. **표시순서는 시나리오에 종속시키지 않는다.** 공용 표시순서는 별도 DB 프로필에서
    읽고 Excel 표 붙여넣기 또는 직접 편집으로 원자 교체한다. 시나리오 전환·신규 생성 시에는
    항상 현재 공용 프로필을 적용하며 표시순서 변경만으로 리비전을 만들지 않는다.
14. **공정 표시명은 화면 표기 전용이다.** 공용 프로필(`app_meta.global_process_rename*`)
    에 저장하고 원본 `공정` 값은 데이터·저장·왕복 CSV 어디에서도 바꾸지 않는다. 라벨은
    계산 입력이 아니므로 `content_token` 을 재발급하지 않고, 프로필 버전 정수를 HOME
    Figure 캐시 키 원소로 넣어 버전이 바뀔 때만 Figure 를 무효화한다. 계산 캐시
    (`build_home_simulation_cache_key`)에는 넣지 않는다.
15. **키 방침.** 계산 캐시 래퍼(`simulation_cache`)의 키는 그 함수의 실제 입력 전부(내용 지문·범위·날짜·선택값)를
    싣고 코드 상수(사용기준 규칙 `COUNTED_USAGE_BASIS`·분류 표 등)는 싣지 않는다 — 상수는 배포로 프로세스가 새로
    뜰 때 캐시와 함께 바뀐다. 이 캐시는 프로세스 전역이라 같은 키로 다른 결과를 기대하는 화면 테스트
    (`tests/test_standard_target_capa_page.py` 등)는 테스트마다 비운다.
16. **그림 모양을 바꾸면 그림 모양 버전을 올린다** — 키 방침의 예외다. Figure 에 구워지는 것(묶음 구조·막대 폭·
    둥근 머리·`customdata` 꼬리)이나 공용 칸 저장 형식을 바꾸면 `HOME_FIGURE_SCHEMA_VERSION`(공정 Capa 상세는
    `canvas_memo_key` 의 모양 버전)을 올린다 — 떠 있는 서버는 고친 코드를 다시 읽지만 세션 공용 칸에는 옛 그림이 남는다.
17. **표시순서는 `reference_version` 을 바꾸지 않고 바뀐다.** 표시순서로 정렬한 결과를 캐시하는 래퍼는
    `display_order_digest(reference_tables["RQ_DISPLAY_ORDER"])` 를 키에 함께 넣는다(HOME
    `build_home_simulation_cache_key`·기준 정보 편집표가 이 한 함수를 쓴다). **표시순서 지문은 편집 화면
    `source_token` 에도 든다**(`row_order=` — 기준 정보·생산 계획). 편집표 편집은 줄 위치로 남아 지문이 빠지면 적용 전
    편집이 다른 공정 줄에 붙은 채 적용된다 — 바뀐 회차에 편집을 비우고 한 번 알린다(9장 「편집표와 내려받기」). 표시순서로
    줄을 세우는 편집 화면을 새로 만들면 같은 지문을 그 화면 토큰에 넣는다.
18. **페이지는 큰 계산 프레임을 풀지 않는다.** 탭이 쓰는 작은 표는 시나리오 키(정렬이 들면 표시순서 지문까지)로
    갈린 키 전용 캐시(`get_scenario_securement_rate`·`get_required_month_table` 등)에서 꺼내고, 대당 Capa·소요대수
    프레임은 그 캐시가 빗나갈 때만 캐시 안에서 로더로 받는다.
19. **화면끼리 같은 계산을 나눠 쓰려면 같은 함수로 키를 낸다.** `HomeSimulationCacheKey` 앞 네 칸은
    `ScenarioCacheKey` 와 같은 자리라 HOME 이 제 키의 앞 네 칸(`cache_key[:4]`)으로 Static Capa 화면들·공정 Capa
    상세와 한 칸을 쓴다 — 순서를 바꾸면 말없이 따로 계산한다. HOME 계산을 빌리는 화면은 달 범위도 HOME 과 같은 함수(`past_data.display_month_range`)로 낸다.
20. **세션끼리 나누는 캐시 칸은 받은 쪽이 고쳐도 다른 세션에 닿지 않게 둔다.** 리비전 스냅샷처럼
    `st.cache_resource` 에 한 벌만 두는 값(개수·수명 `SNAPSHOT_RESOURCE_*`)은 바이트(pickle·JSON)로 두거나, 살아 있는
    프레임이면 읽기 전용으로 잠그고 부를 때마다 축까지 새로 만든 깊은 사본을 넘긴다(`persistence/cache._private_copy`
    — `copy(deep=True)` 만으로는 열 이름 배열을 공유한다).
21. **`persistence/models.py` 의 모델 인스턴스(`ScenarioSnapshot`·`GlobalDisplayOrder` 등)를 Streamlit 캐시에 넣지
    않는다** — 코드
    핫리로드 뒤 pickle 클래스 식별자가 달라질 수 있다. 기본형 메타데이터와 DataFrame 을 캐시하고 꺼낼 때 현재 모델로
    다시 만들므로, 캐시되는 모델에 필드를 더하면 기본값을 둔다(옛 payload 를 `**payload` 로 다시 만들 수 있게).
22. **캐시 무효화는 DB 를 바꾼 호출부 몫이다.** 공용 프로필 캐시는 DB 경로 키라 `version` 이 올라도 비지 않는다
    — 표시순서 교체는 `clear_global_display_order_cache()`, 시나리오 이름 변경·보관·복원·삭제는
    `clear_scenario_snapshot_cache()`, 공용 비교 대상·주요 Case 를 비우거나 version 을 올리는 이름 변경·보관·삭제는
    `clear_global_comparison_scenario_cache()`·`clear_global_main_cases_cache()`(리비전명 변경도 — 주요 Case 슬롯
    글자가 리비전명을 싣는다) 까지 부른다(`tests/test_scenario_management_page.py`·`test_revision_rename.py` 가 지킨다).
    입장 화면 Summary 가 읽는 공용 프로필·시나리오를 바꾸는 저장 길은
    `intro_summary.forget_intro_summary_check` 도 부른다(새 길은 `tests/test_summary_recheck_paths.py` 에 더한다).
23. **모든 화면에서 회차마다 그리는 공통 요소는 DB 를 읽지 않는다.** 머리 띠·사이드바 조건 줄은 활성화·확인 때
    세션에 떠 둔 값(`scenario_activation.active_scenario_label`·`intro_summary.latest_official_revision`)만 읽고
    저장소는 팝업을 연 동안에만 읽는다 — `tests/test_app_navigation.py` 가 그리는 동안 저장소·연결 호출 0 을 지킨다.
    HOME 제목 줄 주요 Case 칩도 같다 — 공식은 `intro_summary.latest_official_identity`, Case 는 주요 Case 쓰기 세대를
    키로 한 캐시(`load_main_case_targets` — `clear_global_main_cases_cache()` 가 함께 비운다)다. 같은 시험이 칩도 감싸
    첫 회차만 읽고 둘째 회차는 0 인 것을 지킨다. 사이드바 「설비 시나리오」 줄은 이 규칙의 예외가 아니다 — `app.py` 는 칸만
    세우고 **페이지가** `resolve_equipment_session`(캐시) 뒤에 그 칸에 그리며, 머리 띠 끝 「설비 시나리오 · …」 은 페이지가
    남긴 라벨 칸(`equipment_scenario_label_v1`)만 읽는다(9장).
24. **공용 프로필에는 모두가 함께 쓰는 설정(비교 대상·판정 기준 등)만 담는다** — 켜고 끄는 보기 토글을 담으면 남의
    화면까지 켜진다. 바뀐 것이 없는 쓰기는 쓰지 않는다 — 설비 DB 의 필요 단축 일정 공용 조회 조건
    (`save_shortening_filter_months`·`_processes`)은 저장소가 쓰기 트랜잭션 안에서 견주어 같으면 version 도 동기화 dirty
    도 올리지 않는다(`_WriteOutcome(wrote=False)`). 층 사용 상태(`save_floor_states`, `0029`)도 같다. 시뮬레이션 DB 공용
    프로필 저장소는 늘 version 을 올리므로 화면이 값이 실제로 바뀐 때만 저장한다(9장 「공용 프로필을 기본값으로 심는 조회
    위젯」).
25. **버전 대조.** 편집표로 고치는 공용 프로필은 편집을 시작할 때 본 `version`(표 전체 교체 초안이면 내용 지문)을
    넘기고, 저장소는 쓰기 잠금 안에서 저장본과 다르면 거부한다 — 옛 초안이 그 사이 남의 저장을 덮지 않게. 공정
    표시명·확보율 보정은 `require_profile_version` → `ProfileVersionConflict`, 판정 기준은
    `SecurementThresholdConflict`, 자동 갱신 설정은 자체 대조, 설비 Cut-off 는 초안 지문(`process_cutoff_fingerprint`)
    이다. Space 층 사용 설정(설비 `0029`)은 `require_profile_version(schema="equipment_ops")` 다. 새 편집 프로필은
    `require_profile_version` 을 쓴다. 충돌이면 최신 저장본으로 초안을 다시 세운다. 「현재 전체 교체」를
    확인받는 붙여넣기는 대조하지 않고, 저장본을 보여 주는 숫자 칸에는 key 를 두지 않는다.
26. **보이지 않는 저장값은 남긴다.** 공용 프로필 편집기는 지금 화면(조회기간·시나리오·맞댄 공정)에 보이는 칸만
    갈아 끼우고 보이지 않는 달·공정은 그대로 둔다 — 범위를 좁힌 채 저장한 사람이 모르는 새 남의 값을 날리지 않게.
    「모두 비움」처럼 전체의 뜻을 바꾸는 선택만 보이는 대로 저장한다.
27. **리비전을 쓰기 전에 계산을 한 번 돌린다.** 저장·복제·월 머지/연도 Shift 저장·공식 발행·자동 갱신 발행은
    `capacity_gate` 로 시나리오 전체 기간의 대당 Capa·소요대수와 HOME Density 환산(`density_error`)을 먼저 본다.
    편집이 새로 깨뜨렸으면 저장하지 않고, 편집 전부터 계산되지 않던 리비전은 경고하며 저장을 허락하되(오류를 하나씩
    고칠 수 있게) 공식버전으로는 지정할 수 없다. 예외는 BigDataQuery 등록·내장 시드뿐이고(들어온 원천을 앱 안에서
    고칠 길을 막지 않는다), 새 쓰기 경로는 `tests/test_capacity_gate.py` 목록에 더한다.
28. **계산 계약을 바꿔 옛 리비전을 쓸 수 없게 되면 `revision_compatibility` 에 판정을 더한다.** 불러오기 **전에**
    막고 이유를 알린다 — 활성화한 뒤 계산이 멈추면 활성 시나리오가 이미 바뀌어 화면에서 되돌릴 길이 없다. 빠진 값을
    추정해 채우지 않는다(지어내면 오류 대신 조용히 틀린 Capa 가 나온다). 지금 막는 `STEP_SEQ`·`MCP_SEQ` 빈
    저장분은 같은 원천 코드를 다시 등록해 새 시나리오로 저장한다.
29. **시나리오에 딸린 새 표는 소유 컬럼(`scenario_id`·`dataset_id`·`revision_id`) 가운데 하나를 갖는다** — 영구
    삭제가 `information_schema` 에서 그 컬럼으로 지울 표를 찾으므로 없으면 시나리오를 지워도 행이 남는다.
30. **리비전 프리셋의 확보·경고 기준은 레거시다.** 판정은 공용 판정 기준 프로필만 보고, 프리셋 값은 그 프로필이
    한 번도 저장되지 않았을 때 기본값을 정하는 데만 최신 공식버전에서 읽는다. 세션 키 `dashboard_*_threshold_percent`
    는 다음 리비전 저장에 실어 보내는 운반용이고, 자동 갱신은 직전 공식버전 프리셋 값을 실어 간다(코드 기본값을
    실으면 발행 순간 모든 화면의 기준이 바뀐다).
31. **UPEH 가정은 계획 키 안의 토큰으로만 계산에 든다.** `RQ_UPEH`·`content_token`·전체 기간 계산 캐시·
    `ScenarioCacheKey` 는 건드리지 않는다. 필요 단축 일정 계획 키(`RequiredShorteningCacheKey`) 끝 칸이 토큰
    (`(%, 건 달)`, 공식은 `()`)이고, 가정 계획 칸(`get_assumed_required_shortening`·`_for_target`, 작은 LRU)은 **원 로더와
    그 키**를 받아 안에서 ÷f 로더를 만든다 — 밖에서 만든 가정 로더를 넘기는 길이 없다. 공식 칸은 가정 키를, 가정 칸은
    공식 키를 받지 않는다(`ValueError`). 키 전용 CSV·진척 캐시는 계획을 키와 한 묶음(`KeyedShorteningPlan`)으로만 받고
    짝이 다르면 멈추며, 진척 비교는 공식 키만 받는다. 가정을 건 프레임은 시나리오 키 전용 칸
    (`get_securement_rate`·`get_scenario_securement_rate` — HOME 과 같은 칸)에 넘기지 않는다 — 공정 Capa 상세는 이미 받은
    작은 확보율 프레임에 캐시 밖에서 건다. 설비 일정 키(`process_timeline_key_from_shortening`)는 토큰을 싣지 않는다.
    `tests/test_upeh_assumption_cache.py` 가 짝 어긋남과 「가정을 돌린 뒤에도 공식 칸·HOME 확보율이 공식 그대로」를 본다.
32. **설비 시나리오는 (공통, 일정) 쌍으로만 읽는다**(설비 `0027`, 2026-10-24 결정 E1~E9·F1~F7). 설비 마스터는 공통 호기 대장
    (호기 정보·Space 실물·실적·상태·이력·메모·기존 보유대수 — 시나리오와 무관하게 늘 최신)과 설비 시나리오 일정(날짜 여섯 +
    `시나리오 메모` + 비가동 일정 전체)으로 갈리고, 일정·비가동은 설비명이 아니라 **호기 키**에 매달린다.
    - **세션은 (시나리오, 일정 리비전) 하나를 고정해 든다.** 새 세션 = 최신 공식 발행(E5). 편집본 토큰·계산 사본·Space
      편집기 epoch 는 쌍 토큰(`EquipmentSnapshot.token`)이고, 계산 캐시 키는 지금처럼 내용 지문이라 바뀐 것이 없다
      (`시나리오 메모` 만 바꿔도 마스터 지문이 바뀌어 다시 계산하는 것은 받아들인다). 세션이 공식 발행 쌍이면 공식 스냅샷과
      같은 쌍 키라 같은 본문 칸을 쓴다.
    - **낡음 잠금**: 남이 내 시나리오에 일정을 저장해(함께 넣기 포함) 세션 리비전 ≠ 그 시나리오 최신이면 **편집하기 전에**
      사이드바 배지를 「최신 r14 있음」 으로, 설비 마스터 탭 맨 위에 「「운영 일정」 r14 가 더 새롭습니다 — … 사이드바 「설비 시나리오」
      에서 최신 r14 를 불러오세요」 를 세우고 일정 여섯·시나리오 메모 칸과 비가동 표·행 추가를 잠근다(막힌 뒤에 버리는 일이
      없게 — 붙여넣기 미리보기도 `stale_paste_refusal`). 공통 칸은 그대로 저장된다. 남이 공통을 저장하면 지금처럼 편집본을 다시 세우고 「공통 대장
      rN」 으로 알린다(일정 쪽 편집을 새 공통 위로 옮기는 것은 2단계).
    - **교차 검증**(3장 `equipment_repository`)이 각 시나리오 최신과 최신 공식 발행을 늘 합쳐지게 지킨다. 그 밖의 옛
      리비전은 막힐 수 있고, 세션이 그런 쌍을 들면 `resolve_equipment_session` 이 시나리오 최신 → 공식으로 옮기고 알린다.
    - **일정 없음** 호기(그 시나리오에 일정 행이 없는 호기 — 함께 넣기를 끄고 넣은 호기)는 그 시나리오 계산·Space 에서
      뺀다(`calculation_frames`, G2 결정). 편집·설비 마스터 탭·CSV 의 39칸 프레임에는 그대로 든다.
    - **어느 캐시도 호환 래퍼를 부르지 않는다**(3장 `equipment_cache`). 바뀐 것 없는 설비 저장은 리비전을 만들지 않는다
      (`wrote=False` — dirty 도 없다). 새 쓰기는 모두 `_write_transaction(outcome)` 을 지난다.
    - 새 표 여섯에는 **외래 키가 없다** — DuckDB 1.5.5 가 FK 부모의 한 트랜잭션 삭제·UNIQUE 칸 UPDATE(이름)를 막아서다.
      소유·정합은 저장소가 같은 트랜잭션에서 지킨다(`docs/data_model.md`). `copy_database` 차례에 더한 것이 없다.
    - **공식 판정은 저장소와 같은 규칙**이다 — 최신 발행의 시나리오, 발행이 없으면 「운영 일정」(있으면), 그것도 없으면 목록
      첫 시나리오. 세션·화면은 `EquipmentScenarioCatalog.effective_official_scenario_id` 하나로 본다(`EquipmentSession.
      official_scenario_id`·새 세션 기본 선택·저장 이력 시나리오) — 목록 차례를 바꾼 빈 발행 DB 에서 화면의 「공식」 과 저장의
      역할이 갈리지 않게(설계 검토 L13).
    - **이름 바꾸기는 같은 호기다**(G4·R2, 2026-10-24 사용자 결정 「나」). 호기 키가 그대로라 모든 시나리오의 일정·비가동·
      이력이 새 이름을 따라간다. 이름 바꾸는 자리는 `space_layout_edit` 의 공용 넷(3장)만 쓴다. 붙여넣기·CSV 는 설비명이 키라
      이름 바꾸기를 나타낼 수 없다(없는 이름이면 새 호기 — 지우지 않는다).
    - **가정 설비 시나리오는 배치 차이를 일정 리비전에 든다**(설비 `0031`, 2026-10-24 결정 LY1~LY6·Q1~Q5, 설비 시나리오 2단계
      S2 — 저장소·읽기). 시나리오마다 따로인 것은 호기 위치 일곱 칸·층 도면 요소·Main 설비명 위치이고, 공통은 FAB 전체·층 사용·
      층 캔버스·배경 도면이다. 가정 시나리오는 **공식과 다른 것만** 갖고(손대지 않은 호기·요소는 공식을 따라간다), 합친 본문이
      그 차이를 얹어 낸다(`docs/data_model.md` 「가정 설비 시나리오의 배치 차이」). 저장은 역할로 가른다(3장
      `equipment_repository`) — 공식 대상은 공통·층 현행값에, 가정 대상은 그 시나리오 새 리비전의 차이로. **공식 설비 시나리오의
      최신·최신 발행에는 차이 행이 없다**(I2) — 배치 차이가 있는 시나리오는 공식으로 발행하지 않는다(Q4). E7 되돌리기·여기서 새
      시나리오는 차이도 옮긴다. 위치는 가용대수·확보율 계산 입력이 아니지만 계산 프레임은 얹은 그대로라 배치만 바꾼 가정
      시나리오도 계산 칸을 따로 쓴다(값은 같다 — LY6, 계산 키 방침 「실제 입력 전부」 그대로).
    - **Space 는 세션 설비 시나리오의 배치를 그리고 역할대로 고친다**(S3 — LY3·LY4, 1단계 E5 「Space 는 늘 공식」 을 바꿈).
      공식 배치는 공식 설비 시나리오에서만, 가정 배치는 그 시나리오에서만 고치고(`space_edit_mode` 한 판정 — 설비 마스터 탭
      배치 칸·붙여넣기도), FAB 전체·층 캔버스·배경 도면·층 사용은 공식에서만이다(G5·Q3). 배치 편집은 적용할 때 역할을 찍고
      저장소가 쓰기 잠금 안에서 대조한다(6-2). 가정 세션에서 넣은 새 호기는 공통 배치가 비어(Q1) 공식에서 「동·층 미정」 이고
      자리는 그 시나리오의 배치 차이에 든다 — Space 저장 상자의 「다른 설비 시나리오에도 넣기」 는 기본 끔이다.
    - **S4 — 견주기·관리 보강**. 「공식과 견주기」 는 그리는 스냅샷의 호기 차이를 점선으로 보일 뿐 쓰지 않는다(뷰어 payload 는
      epoch 밖). 차이를 지우는 길은 시나리오 관리 › 설비 시나리오 「배치 차이 모두 지우기」(새 리비전 — 지운 리비전은 남아 되돌리기로
      되살아난다)이고, 발행 확인 팝업은 발행 쓰기와 같은 판정을 미리 읽는다(판정 한 곳 `_layout_publish_preview`). 남이 공통을
      저장해 편집본을 다시 세울 때 가정 역할 배치 일곱 칸 편집은 다시 얹는다(일곱 칸 절댓값이라 새 공통 위에서도 뜻이 같다 —
      설계 9장). 층 캔버스 팝업은 캔버스를 바꾸는 저장이 보는 가정 배치를 미리 말한다.
33. **화면 탭은 세션 칸이고 화면을 살려 두지 않는다**(2026-10-24 사용자 결정). 탭 목록·고정·이동 대기는
    `page_tabs_state` 의 세션 칸이라 이 접속에만 산다 — 새로고침·테마 바꾸기는 HOME(고정)과 지금 화면만 남긴다. 탭을 누르는 것은
    사이드바 링크와 같은 페이지 바꾸기라, 돌아왔을 때 남는 것은 `persist_state="session"` 위젯과 위젯이 아닌 세션 칸뿐이다
    (편집표의 적용 전 편집·폼 초안·팝업·접힌 상자·스크롤은 처음으로 간다). 탭을 닫아도 그 화면의 보기 조건·세션 편집은
    지우지 않는다. 탭 줄은 23번처럼 DB 를 읽지 않는다 — `tests/test_page_tabs.py` 가 그리는 동안 저장소·연결 호출 0 을
    지킨다. 탭 목록은 `scenario_activation._STALE_UI_KEYS` 에 넣지 않는다(무엇을 보고 있는지라 시나리오를 바꿔도 남는다).

## 6. 핵심 계산 규칙

### 부하량 단위

- PKG: Kea
- Chip: Kea
- Wafer: 매
- Density: 억Gb

### 부하량

```text
Chip = 생산수량 × 구분_Chip ÷ BE_수율

Wafer = 생산수량 × 1,000 × 구분_Chip
        ÷ EDS_수율 ÷ BE_수율 ÷ Net Die

Density = 생산수량 × 구분_Chip × 구분_EQ ÷ 100,000
```

Dummy는 Chip과 Wafer의 추가 적용 항이 다르다. Wafer는 위 일반식에 `(1 - EDS_수율)`만
곱하지만, Chip은 일반식에 없는 `÷ EDS_수율`까지 함께 적용한다.

```text
Dummy Chip  = 생산수량 × 구분_Chip ÷ EDS_수율 ÷ BE_수율 × (1 - EDS_수율)

Dummy Wafer = 생산수량 × 1,000 × 구분_Chip
              ÷ EDS_수율 ÷ BE_수율 ÷ Net Die × (1 - EDS_수율)
```

Dummy 판별은 `WF 구분` 이름 단독이 아니라 **`(제품타입, WF 구분)` 게이트**다. 목록은
`product_type.py`의 `DUMMY_DIVISIONS_BY_PRODUCT_TYPE`이 선언하고 적용은
`load_calculator.py`의 `_dummy_mask`가 한다. HBM은 `Dummy` 하나이고 EDP-TSV는 목록이 비어
있어 `WF 구분`이 `Dummy`여도 Dummy 산식을 받지 않는다. `제품타입` 컬럼이 없는 레거시
프레임과 그 값이 빈 행(0013 이 NULL 로 남긴 제품·원천 `prod_knd` NULL)에서만 두 목록을 합쳐
이름으로 판정한다 — 두 제품군의 `WF 구분` 집합이 겹치지 않아 결과가 HBM 규칙과 같다. 이름
비교는 기존 리비전과 BigDataQuery의 표기 차이를 흡수하도록 대소문자와 앞뒤 공백에 의존하지
않는다. 정확한 현재 구현은 두 모듈과 `docs/TODO.md`를 기준으로 한다.

### 대당 Capa

```text
대당 Capa
= 환산_UPEH × 24 × 효율 ÷ 여유율
  × 모듈수 × 가동일수 ÷ Lot측정률 ÷ WF측정률
```

- `Area_Name = Main`: `UPEH`
- `Area_Name = MI`: `60 / ST`
  - **`RQ_UPEH` 의 `ST` 는 한 개당 분(min/unit)으로 입력한다**(정의, 2026-10-22 사용자 결정). 값 크기로 단위를
    가르거나 갈래를 두지 않는다. 근거: 사내 8-2 의 기존÷신규 ≈60 무리(13,077키)가 모두 MI 경로·60 ±0.1% 였다.
    식은 `unit_capacity.converted_upeh` 한 곳이고 기존 결과 대조(`legacy_comparison.hourly_rate`)도 그것을 부른다.
- 소요기준 `CHIP`·`PKG` 는 위 값을 다시 1,000 으로 나눈다(부하량이 K개).
- UPEH·Lot/WF 측정률과 `RQ_REQB`의 `Area_Name`은 Core Data 변환 및 기존 리비전의
  런타임 소요대수 연결에서 대소문자와 앞뒤 공백을 정규화해 `Main`·`MI`로 통일한다.
  Lot/WF 측정률의 빈 값과 **`0`**과 **행 부재**는 모두 측정 대상이 아닌 경로로 보고
  `1.0`을 적용하되, 숫자가 아닌 값은 오류로 처리한다. `0`을 빈 값과 같이 보는 것은 원천이
  두 표기를 섞어 쓰기 때문이다 — 분모라서 그대로 두면 나눌 수 없고, 예전에는 이 행을 통째로
  뺐다. **행 부재를 같은 선 안에 들인 것은 2026-09-24 이다.** 그 전에는 하드 오류였고, 빈
  UPEH 를 채우면 측정률 짝이 없어 HOME 이 통째로 서는 일이 사내에서 실제로 났다.
  - **메운 건수는 반드시 화면에 닿아야 한다**(`components/capacity_assumption_notice.py`).
    측정률은 분모라 실제가 1 보다 작으면 대당 Capa 과소 → 소요대수 과대 → **확보율 과소**(보수
    쪽)이고, 1 보다 큰 경로에서만 확보율 과대다. 세지 않고 메우면 완화가 곧 조용한 오류다.
  - **중립값이 있는 표에만 적용한다.** 가동률·편중률·모듈수·가동일수의 행 부재는 그대로
    하드 오류다 — `1.0`이 「가동률 100%」 같은 거짓 주장이 되고, 기준정보가 통째로 빠진
    배포에서도 숫자가 나와 버린다. 갈림은 `_join_reference` 의 `missing_value_default`
    선언 유무 하나다.
  - 새 경로를 만드는 **편집 쪽**은 별도로 막는다(`services/reference_consistency.py`).
    계산의 완화는 이미 그렇게 저장된 리비전과 UI 로 만들 수 없는 새 경로를 위한 것이고,
    평소에는 저장할 때 측정률 행을 함께 채우는 쪽이 옳다.
- `소요기준 = PKG 또는 CHIP`: UPEH를 Kea 기준으로 `/ 1000`
- Lot 측정률·WF측정률이 **음수**인 행과 대당 Capa 0 이하인 행은 제외 행으로 남기고 계산에서
  제외한다. 두 측정률은 같은 규칙을 쓰며 `WF측정률 음수`·`Lot 측정률 음수` 사유를 붙인다.
  한 행이 둘 다에 걸리면 WF측정률 사유로 한 번만 남는다. 우선순위는 별도 분기가 아니라
  `NEGATIVE_EXCLUDED_COLUMNS`의 나열 순서다 — 순서를 뒤집으면 규칙이 조용히 바뀐다.
  0을 1.0으로 올리는 것이 제외 판정보다 **먼저**다. 뒤에 두면 이미 뺀 행을 되살릴 수 없다.
- **라인 전체가 서는 날은 `RQ_RUN_DAY` 를 줄여서만 적는다**(2026-10-06 사용자 결정). 라인
  점검·공사로 라인이 통째로 쉬는 날은 그 달·공정의 가동일수를 그만큼 줄인다. 설비 하나하나의
  일(개발대여·공사·고장·이설 등)은 가용설비 현황의 **비가동 일정**에 적는다. 같은 정지를 두 곳에
  적으면 **이중 계상**이다 — 가동일수가 줄어 대당 Capa 가 작아지고(소요대수 증가) 비가동으로
  가용대수도 줄어 확보율이 양쪽에서 깎인다. 비가동 일정의 유형 `공사` 는 그 호기만의 공사다.
  코드가 두 입력을 맞대어 막지는 않는다(가동일수는 월·공정별 개수라 어느 날인지 모른다) — 이
  규칙은 기준 정보 `일수` 탭과 가용설비 비가동 일정 Guide 가 사용자에게 알린다.
- 계산 대상 행을 먼저 확정한 뒤 편중률·모듈수·`RUN_DAY`의 0 이하 검증을 남은 행에만 돌린다.
  어차피 제외될 행의 기준값이 화면 전체를 멈추면 그 값을 고칠 편집기조차 열 수 없다.
  이 세 검증은 실패 시 위반 건수와 문제 업무 키·값 예시 5건을 메시지에 싣는다.
  기준정보 값의 빈 값·숫자 아님 검사도 같은 까닭으로 **붙인 뒤 붙은 행에만** 한다
  (`_join_reference`). BOX·PCB 공정이나 UPEH 가 없는 달의 행은 어느 경로에도 붙지 않아 비어 있어도
  계산을 멈추지 않는다. 붙은 행이 걸리면 빈 값과 숫자가 아닌 값을 갈라 건수·키 예시를 싣는다.
  **범위:** 이 검사는 붙일 때 돌아 계산 대상 행을 확정(UPEH·`CAPA_RUN_RATE` 0 이하, 측정률 음수를
  제외)하기 **전**이다. 그래서 뒤에서 제외될 경로에만 붙은 행의 빈 값·숫자 아님은 행 없음(「연결값이
  없는」)과 같이 계산을 멈춘다 — 같은 칸이 0 이면 제외 뒤의 `_assert_positive` 라 통과하는 것과
  다르다. 제외 마스크 뒤로 옮길지는 정하지 않았다(`docs/TODO.md`).
- 제외 행은 사유 컬럼과 함께 `CAPACITY_EXCLUSIONS_ATTR`로 전달되고 산출 결과의 대당 Capa·
  확보율 화면이 건수·상세 표·CSV 내려받기로 보여 준다
- BOX·PCB는 산식 확정 전까지 계산에서 제외한다(제외가 아니라 `추가 예정` 이다 — 11장 참조)
- 기본 화면용 공정별 대당 Capa는 STEP으로 중복된 수요를 한 번만 센 원수요 부하량을
  STEP별 소요대수 합계로 나눠 `원수요 부하량 ÷ Σ(STEP별 부하량 ÷ STEP별 대당 Capa)`로
  집계한다. 동일한 대당 Capa의 STEP이 늘면 공정별 대당 Capa는 그 수에 반비례해 감소한다.
- 화면 집계 수준은 `공정 → 양산구분 → 제품정보 → Stack → WF 구분`이며 소요기준은
  공정별 `RQ_REQB` 값을 따른다. STEP별 상세 대당 Capa를 별도로 제공하며 화면용 유효
  Capa를 소요대수·확보율 계산에 재사용하지 않는다.
- `RQ_UPEH`·`RQ_LOT_RATIO`·`RQ_WF_RATIO`의 경로 식별 키는 생산계획년월·Area·공정·
  `STEP_SEQ`·`MCP_SEQ`·양산구분·제품정보·Stack·WF 구분이다. 세 기준정보와
  `RQ_REQB`는 Area·STEP·MCP를 포함해 정확히 일치하는 경로끼리 연결한다.
- STEP 수는 생산계획년월·Area·공정·양산·제품·Stack·WF·소요기준 안의
  `(MCP_SEQ, STEP_SEQ)` 고유 조합 수로 계산하며 Capa Code·Customer·CS 행 수는 중복
  계수하지 않는다. STEP 추가는 선택한 원본 경로의 모든 수요 변형에 기본 일괄 적용한다.

### 표준 목표 Capa

```text
대당 일 Capa = 월간 공정별 대당 Capa ÷ RUN_DAY
주차별 일 표준 가능량 = 대당 일 Capa × 주차별 가용대수
```

- `RQ_RUN_DAY` 는 소요대수가 있는 (월, 공정)에 붙인 **뒤** 붙은 칸만 검사한다
  (`standard_target_capacity._attach_run_day`). 기준 정보 적용 검사는 UPEH 경로가 쓰지 않는 칸의 0 을
  허락하므로 그 0 이 표준 목표·재공 현황을 멈추면 안 된다. 붙은 칸의 행 없음·빈 값·숫자 아님·0 이하는
  각각 다른 문장에 (월, 공정) 예시를 실어 멈춘다.

- 제품 Mix 가중은 공정별 대당 Capa와 동일하게 중복되지 않은 원수요 부하량을 분자로,
  STEP별 소요대수 합을 분모로 사용한다.
- PKG 기준 일 표준 가능량은 `일 표준 가능량 × 동일 Mix의 중복 없는 PKG PLAN ÷ 원수요
  부하량`으로 역산한다. PKG 소요기준은 환산계수가 1이며 WF·CHIP은 현재 수율과 Chip 구성
  기준이 반영된 원수요 부하량을 통해 PKG Kea로 변환한다.
- 로직 분석의 제품·WF 속성별 분류 유효 Capa를 `C_i`, 부하량 비중을 `w_i`라 하면 공정
  유효 Capa는 `1 / Σ(w_i / C_i)`이며, 이는 `전체 원수요 부하량 / 전체 STEP 소요대수`와
  같다. 로직 분석은 필터로 확정된 공정·주차 한 건만 계산한다.
- 양산구분 `ER`은 제품 Mix 분자·분모를 만들기 전에 항상 제외한다. 상세 OFF는 공정별
  단일 유효 Capa, 상세 ON은 사용자가 선택한 제품·Stack·WF 속성 수준으로 표시한다.
- `Pre B/D`는 예외적으로 `WF 구분 = Dummy`인 부하량과 STEP 소요대수를 제품 Mix 분자·
  분모에서 모두 제외한다. 이 규칙은 표준 목표 Capa와 그 로직 분석에만 적용하며 부하량·
  소요대수·확보율 원본 계산은 변경하지 않는다.
- 주차는 월요일 시작 ISO Weeknum(`YY-W##`)이며 월 경계 주차는 **그 주에 더 많은 날이
  들어간 달**의 월간 Capa와 `RUN_DAY`를 적용한다(2026-09-05 확정). 7일은 4:3 으로만
  갈리므로 동수가 없다. 판정은 `services/iso_week_calendar.owning_month` 하나가 한다.
- 현재 수동 입력 표 계약은 `공정 + Weeknum + 가용대수`이고 공정·Weeknum은 유일해야 하며
  가용대수는 0 이상이어야 한다.
- 붙여넣은 수동 입력 표는 설비 DuckDB의 비버전 최신값으로 공정·Weeknum 단위 갱신한다.
  일부 공정 입력은 다른 공정 값을 보존하고 명시적 초기화만 전체를 삭제한다. 가용설비 운영 DB
  연결 전환 시 계산 서비스는 유지하고 입력 공급자만 교체한다.

### 소요대수와 확보율

```text
소요대수 = 부하량 ÷ 대당 Capa
확보율   = RQ_EQP_AVBL 가용대수 ÷ 공정별 소요대수
```

소요대수 계산 전에는 Capa Code, Customer, CS를 포함한 상세 부하량으로 `RQ_REQB`에
연결한다. 화면용 그룹 합산 데이터를 조인 원본으로 재사용하면 안 된다.
동일 공정·제품에 STEP 행이 여러 개면 같은 부하량을 각 STEP의 대당 Capa로 각각 나누고
STEP별 소요대수를 합산한다. 소요대수 상세 화면은 STEP·MCP를 식별 컬럼으로 유지하되
확보율과 HOME은 공정 수준으로 합산한다.

**UPEH 가정(세션)은 소요대수 ÷f 사후다.** 대당 Capa 는 환산 UPEH 에 선형이고 소요대수는 올림이 없으므로 「구간 달의
계획 UPEH 가 p%」는 그 달 대당 Capa ×f, 소요대수 ÷f(f = p/100)와 같다 — +10% 는 소요 −9.09% 다. 확보율은 같은
`calculate_securement_rate` 로 다시 내고 과부족·판정은 다시 올림한다(정수 단계라 110% 여도 대수가 그대로인 경우가 흔하다
— 효과 줄이 단축일 합계·월 최대 환산 부족 같은 연속값을 함께 적는다). 필요 단축 일정은 비선형이라 ÷f 소요로 계획을 다시
세운다. 식에 상한·하한·반올림이 들어오면 사후 배수가 틀리므로 `tests/test_upeh_assumption.py` 의 선형 대조(내장 시드의
`RQ_UPEH` 를 고쳐 다시 계산한 결과 = 사후 배수)가 깨진다 — 그때는 가정을 기준정보 쪽으로 옮긴다. 두 화면은 소요대수만
같다(공정 Capa 상세는 확보기준 월별·`RQ_REQB` 기간, 필요 단축 일정은 목표 스칼라·카드 기간 — 2026-10-22 맞추지 않기로).

**소요대수에 들지 않은 수요는 0 으로 접되 반드시 센다.** 계산을 멈추지 않고 이어 가는 대신 그
수요는 어느 공정의 소요대수에도 들지 않아 확보율이 그만큼 높게 나온다. 넷이다.

- 부하량에서 빠진 계획 — `RQ_CHIP_QTY`·`RQ_YLD` 가 없거나 값이 빈 계획 행(환산의 제외 목록과 같은
  레코드). 결과 attrs `REQUIRED_LOAD_EXCLUSIONS_ATTR`.
- 생산수량이 빈 계획 — **빈 값은 「계획 없음(0)」 한 규칙이다**(편집 격자·환산·소요대수 모두). 숫자가
  아닌 글자만 키 예시와 함께 멈춘다 — 환산·소요대수·표준 목표 PKG 환산이 `load_calculator.plan_quantities`
  하나로 숫자화해 같은 문구다. 같은 목록에 사유 `RQ_PKG_PLAN 생산수량 빈 값` 으로 남긴다.
- 경로 없는 계획 — 부하량은 났는데 같은 소요기준의 `RQ_REQB` 경로 키(PKG 는 WF 구분 없이 Buffer
  경로)에 하나도 닿지 않은 부하. attrs `UNROUTED_LOADS_ATTR`. 계획 총 부하 = 경로에 붙은 부하 + 이
  목록이 부하량 키 단위로 맞는다. **사유가 셋이고 앞의 둘만 센다**(`제외사유`).
  - `경로 키 어긋남` — 같은 (소요기준, 제품정보, Stack, 연결용 WF 구분) 경로가 다른 달·양산구분·Capa
    Code·Customer·CS 에는 있다. 계획 편집·연도 이동·월 병합이 만든다.
  - `RQ_REQB 에 없는 제품` — 그 제품정보·Stack 의 경로가 소요기준과 무관하게 하나도 없다(BOX·PCB 경로도
    있는 것으로 본다).
  - `그 소요기준·WF 구분 경로 없음`(세지 않음) — 제품은 있는데 그 조합의 경로가 아예 없다. 부하량은
    계획 전 행에 소요기준마다 만들어지므로(PKG 는 REQB 어딘가에 PKG 행만 있으면 모든 계획에) EDP-TSV 의
    PKG(사내 실데이터는 PKG 경로가 HBM 에만 있고 모두 BUFFER), Buffer 외 PKG 경로뿐인 제품, 경로 없는
    WF 구분의 Chip 부하가 늘 여기 온다. 경로 쪽 `PKG 기준은 Buffer 로만 계수` 처럼 목록에는 남기되 세지
    않고 산출 결과 목록에도 싣지 않는다 — 세면 HOME·저장·발행 경고가 모두에게 늘 뜬다
    (`counted_unrouted_loads`).
- 부하가 붙었는데 대당 Capa 가 없거나 0 이하라 뺀 경로 — 기존 경로 쪽 제외 목록 가운데 부하 0 초과.
  부하 0 인 경로와 PKG 의 Buffer 외 행은 소요대수를 줄이지 않으므로 세지 않는다.

건수는 `required_equipment.required_exclusion_counts` 하나가 세고, HOME(조회기간 기준 한 줄)·산출
결과 소요대수 탭(목록·CSV)·리비전 저장·공식 발행 검사(허락하면서 경고, 시나리오 전체 기간)·공식버전
자동 갱신 발행(막지 않고 실행 기록 사유에 붙임)이 같은 셈을 쓴다(`components/required_exclusion_notice.py`).

소요기준은 대소문자를 정규화하며 `WAFER`는 `WF`로 통일한다. 현재 지원 값은 `PKG`,
`CHIP`, `WF`다. 정규화하면 같아지는 `RQ_REQB` 경로 행(`WF`·`Wafer`, `Main`·`MAIN`, 앞뒤 공백)은
한 행으로 접는다 — 접지 않으면 같은 부하량·대당 Capa 를 두 번 받아 소요대수가 두 배다. 등록은
`frame_contracts.duplicate_route_rows` 로 접고, 계산(`_prepare_reqb`)은 같은 정규화를 이미 거친 표를
`duplicated` 로 접는다 — 남는 행이 같다(`tests/test_required_equipment.py` 가 대조). `WF 구분` 의 대소문자는
두 접기 모두 두고, 등록이 원천 한 벌 안에서 표기를 맞춘다(`unify_case_variants`). 그래서 이미 `Buffer`·`BUFFER` 처럼
두 표기로 저장된 옛 리비전은 두 행이 다 계산된다 — PKG Buffer 는 `WF 구분` 없이 부하량이 붙어 그 경로의 소요대수가
두 배이고, CHIP·WF 는 부하량도 두 표기로 날 때(Chip 구성·수율도 두 표기) 두 배다. 경고·목록에 남지 않으므로 `scripts/inspect_revision_calculations.py`
의 「겹친 경로 키」(`WF 구분` 대소문자 무시)가 그 수를 세고 사내 런북 6-3 a 가 잰다. 계산은 이 행을 접지 않는다 — 접으면
옛 리비전 결과가 바뀌므로 사내가 잰 수를 보고 정한다.

**소요기준 `PKG` 는 Buffer 로만 센다**(2026-09-28 사용자 설명). PKG 공정은 Buffer 위에
Core·Top·Dummy 를 쌓고(스택) Mold·MPGA Saw 로 PKG Chip 단위까지 자른 **뒤의** 공정이라
Wafer 가 아니라 PKG Chip 을 투입한다.

- 부하량에 수율을 걸지 않는다. EDS·BE 불량 Die 는 이미 걸러졌다 — 부하량은 생산수량 그대로다.
- 스택된 Chip 은 Buffer 에 쌓여 있으므로 `RQ_REQB` PKG 행 가운데 WF 구분이 Buffer 인 행에만
  부하량을 붙인다. Core·Top·Dummy 등 다른 행은 계산에서 빼고 `PKG 기준은 Buffer 로만 계수`
  사유로 제외 목록에 남긴다 — 조용히 0 으로 두면 「계획이 없어 0」과 갈리지 않는다.
- PKG 부하량에는 WF 구분이 없어 `RQ_REQB` 와 WF 구분 없이 잇는다(`_attach_loads`). 예전에는
  부하량에 `WF 구분 = "PKG"` 를 얹어 이었는데 실제 `RQ_REQB` 의 PKG 행은 `BUFFER` 같은 실제
  분류값을 실어 연결이 늘 실패했고, PKG 기준 소요대수가 **말없이 0** 이었다(사내 버그 보고
  2026-09-28). 픽스처가 REQB·대당 Capa 를 모두 `"PKG"` 로 맞춰 그 가정을 가렸으므로
  테스트 픽스처의 PKG 행 WF 구분은 실데이터처럼 `BUFFER` 로 둔다.
- Buffer 판정은 이름만 본다. `RQ_REQB` 에는 제품타입이 없고 `Buffer` 는 HBM 에만 있는 이름이라
  `Top` 처럼 두 제품군에 걸리지 않는다. 대소문자는 가리지 않는다.
- 이 규칙은 **Stack 이후 Wafer 단위 공정(WF 기준, Mold Wafer 등)에 Buffer 만 들어온다**는
  2026-09-05 설명과 같은 배경이다. 그쪽은 `RQ_REQB` 에 Buffer 행만 있어 산식을 바꿀 것이
  없었고(일반 Wafer 식, 수율 적용), PKG 쪽은 부하량 쪽이 WF 구분을 잘못 달고 있었다.
- 환산 탭(`load_calculator.build_monthly_volume`)의 `WF 구분 = "PKG"` 는 표시용 분류
  라벨이라 `RQ_REQB` 와 잇지 않는다. 그대로 둔다.

Static Capa의 설비 부족 현황은 소요대수 자체는 실수로 유지하되 실제 추가 설비는 정수로
올림한다.

```text
경고 기준 필요대수 = ceil(max(round(소요대수 × 경고 기준 - 가용대수, 9), 0))
확보목표 총 필요대수 = ceil(max(round(소요대수 × 확보 기준 - 가용대수, 9), 0))
확보 기준 추가대수 = 확보목표 총 필요대수 - 경고 기준 필요대수
```

**올림 전에 소수점 9자리로 반올림한다.** 차이가 정확히 0 이어야 할 때도 0 이 되지 않기
때문이다 — 가용 55·소요 50·기준 1.1 이면 `50 × 1.1 = 55.00000000000001` 이라 1e-14 가
남고 올림이 그것을 **설비 1대**로 키운다. 대수는 정수 단위라 그 1대가 곧 투자 판단 1대다.
대수가 보통 1e2 이하라 1e-9 공차는 업무상 의미 있는 차이를 삼키지 않는다.

경고 기준 미달 행의 두 단계 추가대수 합은 확보 기준을 충족하기 위한 최소 대수와 같아야
한다. 월별 부족대수는 동일 설비의 기간 중복을 피하기 위해 전체 기간을 단순 합산하지 않고
월별 상세와 월 최대치로 표시한다.

**입장 화면 Summary 의 「부족 N대」도 이 경고 기준 필요대수다**(2026-10-22 사용자 결정). 그 달 B/N 공정의
`소요대수 × 그 달 실효 경고 기준 − 가용대수` 를 같은 올림(`securement_rate.warning_need_units` → `_ceil_positive`)으로
센다 — 막대 색(판정)과 같은 기준이라 경고 기준을 100% 넘게 둔 달도 「부족」이면 대수가 선다. 확보율 100% 기준
(`ceil(소요 − 가용)`)으로 세지 않는다. 막대 말풍선은 소요·보유 옆에 그 달 경고 기준 이름표를 함께 적는다.

**확보기준 과부족은 부호 있는 정수다**(2026-10-15 사용자 결정, `securement_rate.securement_balance`).

```text
판정 = thresholds.status(가용대수 ÷ 소요대수, 달)        (소요 0 이면 판정 없음)
판정이 확보가 아니면  과부족 = −확보목표 총 필요대수       (위 식 그대로 — 같은 _ceil_positive)
그 밖이면            과부족 = +floor(round(가용대수 − 소요대수 × 확보 기준, 9))
부족 원인 = thresholds.status(총보유대수 ÷ 소요대수, 달) 가 확보가 아니면 「보유로도 부족」,
            아니면 「대여 영향」 (판정이 확보가 아닌 달만, 판정과 같은 길 — 반올림하지 않는다)
```

원인을 판정과 같은 비율로 가르므로 총보유 = 가용(대여 0)인 달은 칠한 판정이 곧 「보유로도 부족」이다.
`securement_balance` 는 대여대수를 모르므로 「대여 영향」은 가용 = 총보유 − 대여를 전제한다. 대여를 아는
공정 Capa 상세 요약(`build_process_capa_summary`)은 `가용 불일치` 인 달에서 총보유 − 대여로도 확보면
「가용 불일치」로 다시 가른다(대여 0 인데 가용만 낮춘 달 — 대책이 대여로 향하지 않게).

칠하기는 판정 한 길(확보율 칸과 과부족 칸이 같은 판정)이고 숫자는 Static Capa 와 같은 올림이다.
판정은 반올림하지 않은 확보율을 보므로 부동소수 잡음 경계(차이 1e-9 안)에서는 경고·부족으로 칠한
칸에 0 이 찍힐 수 있다 — 소요 10.000000000000002 · 가용 10.95 · 확보 기준 1.095 가 그렇다
(`tests/test_securement_balance.py` 가 고정한다).

**확보율 산식은 `calculate_securement_rate` 한 함수다.** 설비 일정 기준 가용대수로 견줄 때도 가용대수 프레임만 바꿔
같은 함수를 부르고 산식을 복제하지 않는다 — 두 숫자가 같은 잣대여야 한다(`securement_cross_check`·`required_shortening`).

**판정은 `SecurementThresholds.status` 한 길이다.** 부등호(`capacity_status` — 확보·경고 모두 기준 **이상**)는
`services/securement_threshold.py` 에만 있고, 판정하거나 구간을 칠하고 이름 붙이는 곳(HOME 결론·B/N 공정 선택·히트맵)은
행·칸의 달을 넘겨 그 달의 실효 기준을 쓸 뿐 경계를 다시 적지 않는다 — 경계가 갈리면 한 화면이 「경고」로 칠한 칸을 다른
화면이 「부족」이라 부른다. 기준은 공용 판정 기준 프로필(`load_global_securement_threshold`)에서 읽고 값은 모두 비율이다
(109.5% → 1.095).

### Dynamic Capa 프로토타입

```text
표준 Capa
→ 실적 효율 / 표준 효율 반영
→ 실적 UPEH / 표준 UPEH 반영 = 실효 Capa
→ 실가동시간 / (실가동시간 + Rundown시간) 반영 = 모델 실적 Capa
→ 생산실적 DB의 실제 실적
```

- `Capa 실현률 = 실제 실적 ÷ 표준 Capa`
- `설비 성능 실현률 = 실효 Capa ÷ 표준 Capa`
- `가용 Capa 활용률 = 실제 실적 ÷ 실효 Capa`
- `효율 Gap = 실적 효율 - 표준 효율`, `UPEH Gap = 실적 UPEH ÷ 표준 UPEH - 1`
- `기타 정합성 Gap = 모델 실적 Capa - 실제 실적`이며 원인이 확정된 손실로 보지 않고
  실제 DB 연결 후 수율·데이터 시점·미분류 Loss 등으로 분해할 잔차로 관리한다.
- 공정·제품·Stack·WF 속성 상세는 합산하지 않고 유지한다. Capa 수량은 합계, 효율은
  계획시간, UPEH는 실가동시간 가중평균을 사용하며 비율은 집계된 분자·분모로 다시 계산한다.
- Rundown·실가동·설비 Down의 실제 컬럼 정의는 실적효율 DB 연결 시 확정한다.
- 데모 상태 판정은 Capa 실현률 90% 이상 정상, 80% 이상 관찰, 80% 미만 개선 필요이며
  실제 운영 임계값은 데이터 분포와 관리 정책을 확인한 뒤 확정한다.

효율·UPEH·수율 세 실적 화면(실행 관리 하위)은 같은 계산을 지표만 바꿔 쓴다
(`services/performance_actuals.py`).

- **Gap 의 뜻이 지표마다 다르다.** 효율·수율은 비율 그 자체라 `실적 − 기준` 을 `%p` 로,
  UPEH 는 절대 수량이라 `실적 ÷ 기준 − 1` 을 `%` 로 읽는다. 둘을 섞으면 UPEH 2,400 과
  2,050 의 차이가 `-350%p` 로 적힌다. 이 선택은 화면이 아니라 `MetricSpec` 이 갖는다.
- **상태는 지금을 말한다.** 기간 평균 Gap 이 아니라 **마지막 달 기준 연속 미달 개월**로
  판정한다(0 정상 · 1~2 관찰 · 3 이상 개선 필요). 평균으로 판정하면 회복한 공정이 반년
  전의 미달 때문에 계속 관찰에 남아 우선순위 표가 옛날 이야기를 한다.
- **우선순위 = 미달폭 × 영향 비중 × 연속 미달 가중.** 미달폭만 보면 물량이 작은 공정이
  1위로 올라온다. 영향 비중의 분모가 되는 생산수량은 **공통 환산 물량**이어야 한다 —
  WF 매와 CHIP Kea 를 그대로 더하면 단위 차이가 순위로 둔갑한다. 실제 DB 연결 때도 같은
  환산 물량을 함께 받아야 한다.
- 비율 집계는 월별 비율의 단순 평균이 아니라 생산수량 가중으로 분자·분모를 다시 만든다.

### 표준 대비 재공 현황 프로토타입

- 차트 조회기간은 서버 오늘 날짜 기준 -7일~+3일의 11일이며, 미래 3일도 실제 DB 연결
  전까지는 전망이 아닌 화면 검토용 샘플로 명시한다.
- 각 공정·제품·STEP 차트는 보유 재공·유입·Flow 세로 막대와 제품별 일 표준 가능량
  점선을 함께 표시한다. Flow가 표준 이상이면 충족, 미달이면 부족으로 색을 구분한다.
- 제품별 표준 가능량은 기존 표준 목표 Capa와 동일하게 원수요 부하량 합을 STEP 소요대수
  합으로 나눈 공정별 대당 Capa에 RUN_DAY와 주차별 가용대수를 적용한다. 여러 양산구분은
  원수요 부하량과 STEP 소요대수를 각각 합친 뒤 비율을 다시 계산한다.
- 공정 소요기준에 따라 단위는 PKG·CHIP의 Kea 또는 WF의 매를 유지하고 서로 합산하지 않는다.
- STEP 정렬은 코드 끝의 `P###`, `P###-###`, `T###`, `T###-###`를 인식해 P 전체 다음 T를
  배치하고 각 숫자 구간을 오름차순으로 정렬한다. 인식할 수 없는 코드는 그 뒤에 둔다.
- 주차별 가용대수가 없으면 기준선을 임의 생성하지 않고 `표준 미설정`으로 표시한다.
  설비 DB 에 가용대수가 한 건도 없으면 빈 표를 계산에 넣지 않고 `st.warning` 안내 후
  멈춘다. 예외(빨간 오류)가 아니라 사용자가 채워야 할 입력이라 경고이고, 같은 화면에서
  「일부만 없다」를 알리는 자리와 같은 색이다.

### B/N

- 월별 유효 확보율이 가장 낮은 공정이 B/N Top 1이다.
- 동률이면 공정명 오름차순 첫 공정을 사용한다.
- `B/N Density Capa = Density 부하량 × 확보율`
- `Wafer Capa = Wafer 부하량 × 확보율`

### 설비 운영 주차 집계

- **위치는 계산 입력이 아니다**(LY6, 2026-10-24) — 동·층·X·Y·크기·레이아웃표시는 가용대수·확보율에 들지 않는다. 그래서 배치만
  바꾼 가정 설비 시나리오(설비 `0031`)도 일정이 공식과 같으면 계산 값이 같다(마스터 지문이 달라 캐시 칸만 따로).
- 기존 보유대수는 모든 주차에서 총대수와 가용대수에 포함한다.
- 신규 호기는 반입일정이 속한 주부터 총대수에 포함한다.
- 신규 호기는 Qual일정이 속한 주부터 가용대수에 포함한다.
- 신규 호기의 반입·Qual 일정은 **비워도 저장된다**(2026-10-06 사용자 결정). 반입이 비면
  「입고 예정」, 반입만 있고 Qual 이 비면 「셋업 진행중」에 머물러 날짜가 들어올 때까지 총대수·
  가용대수에 들지 않는다(반입이 빈 호기는 총대수에도 없다). 일정 순서는 있는 날짜끼리 보고, 반입이
  없는 신규 호기에는 정지·반출/이설일정을 넣을 수 없다. 그런 호기의 대수는 일정 기준 가용을 읽는 자리(Main `가용대수`·`호기 현황`, Static 대비 일정,
  필요 단축 일정 — 여기서는 Qual 일정이 없는 몫이 단축 후보도 아님을 덧붙인다)가 「일정 미정 N대」 한 줄로 알린다(`services/undated_equipment.py`).
- 단일 Qual상태(옛 확정상태)는 Qual 일정의 계획·확정·완료·지연을 관리하는 값이며 가용대수 산식에는
  사용하지 않는다. **Qual일정이 있는 신규 호기에만 필수**다 — Qual일정이 없으면(보관·기존설비
  포함) 비워 둘 수 있다. 반입상태는 같은 네 값이고 비워도 된다.
- 반입실적·Qual실적은 **Space 실물 판정과 알림에만** 쓴다(2026-10-16 사용자 결정). 주차·월별
  설비 일정 기준 가용·필요 단축 일정·공정 Capa 상세는 일정 기준 그대로다 — Space 는 실물, 집계는 계획이다. 실적은
  저장할 때 오늘보다 늦을 수 없고 반입실적 ≤ Qual실적이어야 한다. 미확인(상태 계획·확정 + 실적 공백 +
  일정 < 오늘)·실적 누락·상태 갱신 필요는 저장을 막지 않는 알림이다(`services/schedule_confirmation.py`) —
  설비 마스터 탭 편집표 위 한 줄·접힌 목록(편집본 기준)과 Main `호기 현황` 머리 줄 아래 미확인 한 줄(저장본 기준).
  **미확인은 공식 설비 시나리오 일정 기준이다** — 세션이 공식 시나리오면 자기 일정 그대로, 가정 설비 시나리오면 Main 은
  공식 스냅샷의 미확인을 화면 호기로 좁혀 쓰고(합치지 않는다 — 공통은 늘 최신이라 공식 스냅샷의 공통이 곧 지금 공통)
  꼬리표 「공식 일정 기준」 을 달며, 설비 마스터 탭 확인 목록은 공식 일정 + 편집본 공통 칸으로 센다. 상태 둘(반입상태·Qual상태)은
  공통 칸이고 칸 머리가 「공통 — 공식 일정 기준」 이다.
- **설비 시나리오에 일정이 없는 호기는 그 시나리오에 없는 호기와 같다**(F4 — 2026-10-24 결정, 질문 2 권장안). 그 시나리오의
  주차·월별 가용·Static 대비 일정·필요 단축 일정·공정 Capa 상세·「일정 미정 N대」 셈에서 빠지고(기존설비 Y·보관 Y 도),
  화면은 「이 설비 시나리오에 일정이 없는 호기 n대 — …」 한 줄로 알린다. Space 도 세션 설비 시나리오를 그려 같은 호기를 그리지
  않는다 — 알림은 공식 발행 쌍이면 「공식 일정 없음 n대」, 아니면 「이 설비 시나리오에 일정이 없는 호기 n대」 다
  (`unscheduled_notice(official=…)`). 이관·복제로 만든 시나리오는 모든 호기에 일정 행이 있어 해당하는 것은 함께 넣기를 끄고 넣은
  호기뿐이다.
- 입고 후 Qual 전인 호기는 셋업중대수와 비가동 호기 목록에 포함한다.
- Qual 완료 또는 기존설비에 활성화된 개발대여·공사·고장·이설 등의 운영 비가동 일정이 있으면
  가용대수에서 제외한다. 같은 호기의 중복 비가동 일정은 한 대로 집계한다.
- 비가동 일정은 **호기 단위의 일**만 적는다. 라인 점검·공사로 라인 전체가 서는 날은 비가동이
  아니라 기준정보 `RQ_RUN_DAY`(가동일수)를 줄여서 적는다 — 둘 다 적으면 이중 계상이다(2026-10-06
  사용자 결정, 6장 대당 Capa).
- 보관유무 Y는 전 기간 보유대수에는 포함하되 가용대수에서는 제외하고, 기존설비 Y는
  입고·Qual 일정 없이 전 기간 보유·가용대수에 포함한다.
- 정지·반출/이설 예정은 실행일 전까지 계획 상태로 표시하되 기존 보유·가용 판정을 유지한다.
  **집계 이탈일 = min(정지일정, 반출/이설일정)** 부터 보유·가용에서 제외하고, **도면 이탈일 =
  반출/이설일정(없으면 정지일정)** 부터 레이아웃에서 제외한다(2026-10-16 사용자 결정 — 정지한 뒤 자리를
  비우기 전까지 도면에 남는다). 두 날짜는 함께 적을 수 있고 정지 ≤ 반출/이설이다. 개편 전에는 함께 적을
  수 없어 기존 행의 숫자·도면은 그대로다. **대수는 이름이 아니라 가용 판정(`집계분류`)으로
  센다** — 실행일 전날까지 가용인 예정 호기는 주차·월별 가용대수에 들고, 셋업 중·비가동·보관인 예정
  호기는 들지 않는다(2026-10-07 사용자 결정, 이름으로 세던 결함을 고쳤다). 월별 일할(일정 기준 가용)도
  **실행일 당일은 기여하지 않는다** — 다른 변화는 다음 날부터지만 정지·반출/이설만 그날부터다(2026-10-08
  사용자 결정).
- **가용대수는 사용기준이 HBM·EDP 인 호기만 센다**(2026-10-08 사용자 결정, `equipment_contract.
  counts_for_capacity` — 앞뒤 공백·대소문자를 무시한 완전 일치, 두 값을 한 가용대수로 함께 센다). 주차 집계의 총대수·가용대수·비가동대수·
  분류 칸, 월별 일정 기준 가용(분류 행·소계·환산 소계), 교차검증, 필요 단축 일정(가용·후보), 일정 미정 알림이 이
  규칙을 본다. Space 배치·호기 현황·비가동 호기·설비 마스터 탭은 보지 않는다. 기존 보유대수는 사용기준이 없어
  모두 센다. 뺀 대수는 가용대수를 보이는 자리마다 한 줄로 알린다(`services/usage_basis.py`).
- 주차는 월요일 시작·일요일 종료의 ISO Weeknum(`YY-W##`) 기준이며, 조회기간은
  Main의 기간 조회와 Static 대비 일정이 공유하는 시작일·종료일로 시뮬레이션과 독립적으로
  설정한다. 비가동 호기·호기 상태·Qual 조회는 별도로 고른 기준일의 스냅샷이다.
- Space는 입고 예정·셋업 진행중·가용·정지 예정·반출/이설 예정·보관 설비·운영 비가동·정지
  상태를 색으로 구분하며 레이아웃표시 Y이고 도면 이탈일(반출/이설일정, 없으면 정지일정) 전인 호기만
  X좌표·Y좌표·Xsize·Ysize로 배치한다.
- 설비 일정 기준 가용대수는 별도 확정 전까지 `RQ_EQP_AVBL` 기반 Capa·확보율 계산을 대체하지 않는다
  (실행 관리의 비교·이행 측정에만 쓴다).
  설비 마스터 정리가 끝날 때까지 이 분리를 유지한다(2026-10-06 사용자 결정).
- 설비 DB가 비어 있으면 기존 보유대수·설비 마스터·비가동 일정의 편집본을 모두 비운다.
  개발용 Core Data 샘플의 공정별 보유대수는 샘플 조회에만 사용하며 `분류=전체`로 둔다.
  샘플은 편집본과 리비전 저장 후보에 넣지 않는다.
- 설비 마스터가 비어 있으면 현재 날짜 기준의 생애주기·가용·운영 비가동 상태별 임시
  호기를 가용설비와 Space 대시보드에만 표시한다. 합성 fleet은 `equipment_samples.py`에서
  만들며 표본의 호기 수를 운영 계약으로 고정하지 않는다. 편집 원본과 DuckDB에는 넣지 않고
  실제 호기가 하나라도 저장되면 샘플을 사용하지 않는다.
- **월별 설비 일정 기준 가용은 공정별 W/D 구간에 일할한다.** 한 달의 구간은 `(전월 말일 − cutoff, 당월 말일 − cutoff]`
  (반열린, 소수 Cut-off 는 내림, 분모는 달력일)이고 열두 구간이 한 해를 빈틈·겹침 없이 덮어야 한다 — 어긋나도 오류가
  뜨지 않는다(`services/wd_window.py`). 호기 구간은 첫 구간의 앞 경계부터 만들고(`span_date_range`), Cut-off 가 없는
  공정은 산출에서 빠지므로(0 은 「달력 월 그대로」) 화면이 드러낸다.
- 월별 가용 소계에 드는 분류는 `기존보유`·`가용` 둘뿐이고 나머지 분류 행은 못 쓰는 까닭을 보이는 참고 행이다 — 상태가
  배타적이라 모두 더하면 보유 호기-일수가 된다.
- **대수와 환산대수는 다른 축이다.** `대수` 는 설비를 센 것(기여 비율 × 설비지분)이고 주차 집계가 이 축이다.
  설비지분은 모듈 행(`Main 설비` 로 묶음)마다 그 시점 보유 중인 형제 수로 1 을 나눠(`services/equipment_units.py`)
  대수가 소수일 수 있고 정수로 자르지 않는다. `환산대수` 는 기여 비율에 호기별 `환산비` 를 곱한 것으로 월 Total Capa
  에만 쓴다.
- **`Static 대비 일정` 의 GAP 은 환산 축이다** — 설비 일정 기준(환산대수) − Static(기준정보 대수). 그래서 그림·비교
  시트·확보율 교차검증·필요 단축 일정·공정 Capa 상세의 설비 일정 기준 가용이 같은 값이고, 대수(몇 대) 축은 「호기 목록」의
  `대수` 칸에 남는다.

### 제약 시뮬레이션

공정 하나에 미래 구간 제약(특정 제품만 쓸 수 있게 개조·전용해야 하는 설비)이 생기면 기존 제품 확보율이 언제부터 얼마나
떨어지는지 그때그때 보는 계산이다(2026-10-24 사용자 결정 — 저장하지 않는다). 순수 계산은
`services/constraint_simulation.py` 하나다.

- **입력.** 달마다 R(공정 소요대수 — 활성 시나리오, 필요 단축 일정 계획의 `소요대수` 와 같은 값), Rc(제약 제품 = `제품정보`
  하나의 모든 양산구분 소요 — 제품별 소요대수 표에서, 합 보존), A(설비 일정 기준 가용 — 계획의 단축 전 `가용대수`, 환산
  대수), G(m)(기준 확보율 — 기본은 HOME 공용 판정 기준의 그 달 확보 기준). 그래서 「개조 n대」·「배정 n대」 도 환산 대수다.
- **일곱 가정**(사용자 「권장대로」). `in(m)` = 제약 시작 ≤ m ≤ 제약 끝, 「앞 달」 = 보이는 차례의 바로 앞 달이고 그 달도
  기간 안일 때만 잇는다.
  1. `need = ceil(Rc'·T − 1e-9)`(기간 안·Rc' > 0, T = 제약 확보율 50~300%).
  2. 늘어난 대수만 그 달 앞에 새로 개조한다 — `inc = pool − pool(앞 달)`, 0 보다 크면 개조 창 하나.
  3. 기간 안에서는 줄이지 않는다 — 개조 켬 `pool = max(pool(앞 달), need)`, 개조 끔 `pool = need`(설비가 서로 바뀐다).
  4. 기간 밖 `pool = 0` — 원복 개조 없음.
  5. 개조 비가동 창 = `[W/D(m) 첫날 − 개조 일수, W/D(m) 첫날)`(W/D 첫날 = 그 달 1일 − Cut-off). 달 j 의 비가동 =
     Σ 대수 × 겹친 일수 ÷ W/D(j) 일수 — **달력 월이 아니라 W/D 구간 일할**이다(D1). 가용 A 가 그 구간에 일할된 값이라 같은
     좌표에서 빼야 맞고, 개조 일수 ≤ 앞 달 W/D 일수면 비가동은 앞 달 한 칸에 다 든다(「제약은 6월부터지만 5월부터 준다」).
     보이지 않는 달에 든 비가동은 버리고, 첫 창이 첫 보이는 달 W/D 첫날보다 앞이면 `starts_before_range` 로 알린다.
  6. `usable = A − 비가동`(음수면 0 + `overdrawn` — 이 공정 설비로는 그 개조가 서지 않는다), `allocated = min(pool,
     floor(usable + 1e-9))`, 기존 몫 = usable − allocated(소수 그대로). `allocated < pool` 이면 「가용이 모자란 달」.
  7. 기간 밖 제약 제품 소요는 기존 제품에 합친다 — `Rc' = in(m) ? Rc : 0`, `Re = R − Rc'`.
- **확보율과 판정.** 제약 없을 때 A ÷ R, 기존 제품 기존 몫 ÷ Re, 제약 제품 allocated ÷ Rc'(분모 0 이면 없음 — 판정·최저·
  미달 셈에서 빠진다). 기준 판정은 `capacity_status` 한 길(허용치 없는 「이상」 — HOME 과 같은 칠하기, 41.8 ÷ 38 같은 경계
  잡음 달도 HOME 처럼 미달)이고 기준(G)은 범위로 막지 않는다(HOME 월별 예외는 50~200% 밖일 수 있다). 제약 충족은
  `allocated >= need` **정수 비교**다 — need 가 T 를 맞추는 가장 작은 정수라 「제약 % ≥ T」 와 같은 답이고 잡음이 없다.
- **요약 넷.** 제약 충족 달 수 / 기간 안 Rc' > 0 달 수, 기존 최저 확보율과 그 달(같으면 이른 달)·그 달 제약 없을 때,
  기준 미달 달·그중 제약 없었다면 기준 이상이던 「새로 미달」·「영향 시작」(기존이 제약 없을 때보다 0.05%p 넘게 낮은 첫
  달 — 판정이 아니라 표시 문턱 `IMPACT_TOLERANCE`), 개조 대수(가장 큰 pool — 개조 끔이면 없음)·창 수·첫 비가동 날. 창이
  0 이면(기간에 제약 소요가 없어 pool 0) 화면 넷째 칸은 「0대」 에 회색 줄 「개조할 대수가 없습니다」 다(「0번에 나눠 개조」 가 아니다).
- **「소요 비중대로 나눴을 때」 견주기.** 개조 비가동 없이 기간 안 R > 0 달만 `제약 몫 = floor(A × Rc' ÷ R + 0.5)`(사사오입 —
  파이썬 `round` 의 은행가 반올림이 아니다, D15), 기존 몫 = A − 제약 몫. 제약 몫은 `floor(A + 1e-9)` 를 넘지 않는다 — A 가
  소수(환산 대수)라 Rc' 가 R 에 가까운 달에 사사오입이 A 를 넘어 기존 몫·확보율이 음수가 되지 않게(우선 배정과 같은 내림).
- **허용치 셋**은 판정 경계가 아니다 — `NEED_TOLERANCE` 1e-9(올림·내림 전 잡음), `IMPACT_TOLERANCE` 0.0005(영향 표시
  문턱), `SUM_TOLERANCE` 1e-6 × max(1, R)(어댑터의 제품별 합 대조). 어댑터는 `R < Rc ≤ R + 1e-9` 와 「다른 제품 소요가 0 인
  달」 의 Rc 를 R 로 접는다 — 합하는 차례만 다른 두 근거의 잡음이 Re 에 남아 기존 확보율이 터지지 않게.
- 어느 호기를 개조하는지 정하지 않는 대수 모델이다 — 실제 호기의 비가동·Qual 일정과 겹치면 이중 차감될 수 있다.

### 계산 기간과 멈춤

- **어느 달이든 기준정보 오류가 있으면 조회기간과 상관없이 계산 페이지가 멈춘다** — 보지 않는 달의 오류가 숨으면 조치가
  늦어진다. 오류가 조회기간 안에도 있으면 원문 그대로, 밖에만 있으면 「조회기간 밖」이라고 말한다
  (`get_period_capacity_error`). 실패도 결과(`CapacityOutcome`)로 캐시하되 `ValueError`(계약 위반)만 담고 그 밖의 예외는
  결함이라 그대로 올린다.
- 대당 Capa·소요대수는 전체 기간으로 한 번 계산해 조회기간으로 자른다 — 자른 결과는 그 기간만 계산한 결과와 행
  차례까지 같아야 한다(5장 3). 월끼리 섞이는 계산(누적·이월·보간)은 이 전제를 깨므로 넣어야 하면
  `get_full_capacity_outcome`·`slice_capacity_months` 부터 고친다. 월 컬럼이 있는 `attrs` 는 같이 자르고 측정률 가정
  건수·달은 전체 값을 둔다.

### HOME 얹기 — EDP·확보율 보정·선행 B/O·GAP

HOME 은 원데이터 계산 위에 화면 조건을 얹는다. 순서는 원데이터 확보율 → 확보율 보정 → 선행 B/O 이고, 공정 Capa 상세의
HOME 표시 확보율 줄도 같은 함수(`home_display_rates`)를 쓴다.

- **`EDP 포함` 끄기는 LOB 값에만 건다.** `확보율 × 부하량` 꼴 값(Density·Wafer 계획·Wafer Capa·B/N Capa·Top 5)과
  계획 세부수량만 EDP 를 빼고, 소요대수·확보율·B/N 공정 순위는 EDP 를 포함한 전체 계획 그대로다 — 설비가 받는 부하는
  전체 계획이다.
- **확보율 보정은 퍼센트포인트 덧셈이고 선행 B/O 보다 먼저다.** `조정 확보율 = 기준 확보율 + 증감/100`(105% 에 −10
  이면 95%, 음수는 0 에서 자른다)이고 선행 B/O 변동률은 그 위에 곱하며 `기준 확보율` 도 같은 변동률로 곱한다. B/N 순위는
  조정된 확보율로 다시 매기고 가용·소요대수는 그대로라 `확보율 = 가용 ÷ 소요` 항등식은 깨진다(차이는 hover 가 밝힌다).
  계산 결과에 짝이 없는 보정 행은 막지 않고 알린다(공용 프로필이라 다른 시나리오에서는 맞을 수 있다).
- **선행 B/O 는 월 총량(Density·Wafer·확보율)에만 걸고 Capa 를 바꾸지 않는다.** `변동률 = 기존 계획 ÷ 선행 반영 계획`
  을 확보율에 곱하고 Wafer 는 나눠 `계획 × 확보율` 인 Capa 가 그대로이고, 한 달의 모든 공정에 같은 수라 B/N 순위도
  그대로다. 계획 세부수량에는 걸지 않아 둘의 합이 어긋나는 것이 맞는 상태다. 변동률은 화면이 지금 쓰는 계획(EDP 를 뺀
  화면이면 뺀 계획) 기준이고, 선행을 넣은 달 가운데 선행 반영 계획이 0 이하인 달만 미적용으로 두고 알린다(부하량 0 인
  달이라도 넣지 않았으면 알리지 않는다). `선행 입고` 는 계산을 바꾸지 않고 값 옆에 적기만 한다.
- 과거 구간(Past Data) 달에는 EDP 제외와 비교 GAP 이 걸리지 않는다 — 입력값 하나뿐이라 EDP 를 뗄 수도, 비교할 계획도
  없다. 확보율 보정과 선행 B/O 는 계산 구간 달처럼 걸린다 — 보정은 과거 확보율 행을 합친(`merge_past_frame`) 뒤에 얹고,
  Preference 의 입력 표 년월에도 과거 달이 든다(`tests/test_home_page.py` 가 화면 칸 값과 짝 없는 행 안내로 묶는다).
- **비교 GAP 은 선행 전 원데이터끼리 잰다**(`baseline_lob_summary`). 비교 리비전에서는 계획 한 장만 읽고 환산 표(수율·
  Chip)는 현재 것을 쓴다 — 기준정보 변화는 계획 변동이 아니다. 비교 시나리오에만 있는 분류 조합도 행으로 남긴다.
- **HOME 과 입장 화면 Summary 는 같은 함수로 같은 말을 한다.** Summary 의 B/N 순위·선행 B/O 반영·GAP·증감 글자·판정은
  HOME 과 같은 함수(`official_summary` 의 순위·`apply_advance_to_*`, `plan_gap`, `SecurementThresholds.status`,
  `simulation_cache.get_home_comparison_plan`)로 낸다 — HOME 쪽 규칙을 바꾸면 Summary 도 함께 본다.

## 7. 조인과 데이터 검증 규칙

- 월은 내부적으로 유효한 정수 `YYYYMM`으로 정규화한다.
- 텍스트 키는 `string → strip` 후 사용한다. 원천 값을 상수와 대조할 때는 `.eq(상수)` 가 아니라
  `frame_contracts.match_key`(공백 제거 + casefold)를 지난다 — 원천 `WF 구분` 은 대문자 `TOP` 인데 합성 표본만 `Top`
  이라, 글자 그대로 대조한 코드가 검사는 통과하고 운영 데이터에서는 한 번도 돌지 않았다. 저장·화면에는 원천 표기를 쓴다.
- 계산 전에 필수 컬럼, 필수 키 누락, 숫자 변환, 값 범위를 검증한다.
- 가능한 모든 `merge`에 `validate="many_to_one"`, `"one_to_one"` 등 기대 관계를
  명시한다.
- 조인이 실패하면 누락 키 예시를 최대 몇 건 포함한 한국어 오류를 제공한다.
- 무의식적인 `many_to_many` 조인과 조인 후 행 증가를 허용하지 않는다. 제품을 WF
  속성별로 의도적으로 확장하는 경우만 예외다.
- 수율은 0 초과 1 이하, Net Die는 0 초과, Chip 구성 수는 계산 규칙에 맞는 범위를
  유지한다.
- 계산에서 제외하는 값과 치명적 입력 오류를 구분한다. 제외 행은 DataFrame `attrs`로
  진단 화면에 전달하는 기존 패턴을 따른다.
- **검사는 계산이 멈추는 조건과 같게 둔다.** 편집 적용 검사가 계산보다 느슨하면 적용은 성공으로 알리고 계산 전체가
  멈춘다. 편집이 새로 만든 경로는 그 (월, 키)의 측정률·효율·여유율·일수 행이 있어야 하고, 경로가 쓰는 효율·여유율·
  일수 칸을 비우거나 여유율·일수·UPEH MI 행 ST 를 0 이하로 만드는 편집은 적용 전에 막는다(효율 0 은 그 경로만 제외
  목록으로 빠져 막지 않는다 — `services/reference_consistency.py`).
- 편집 검증은 **이번 편집이 새로 만든 위반만** 막는다 — 쓰지 않는 칸과 원래부터 그렇던 칸은 그대로 둔다. 이미 저장된
  위반까지 막으면 상관없는 칸을 고치려던 사람이 되돌릴 길까지 잃는다(기준정보 짝 결손, MI 행 ST 0 이하, 붙여넣기 범위
  검사의 양식 값, 기준정보 붙여넣기 숫자 검사의 양식 `inf`).
- 저장 전에 띄우는 경고 검사는 저장소 검증과 **같은 행 집합**으로 한다 — 화면 필터·표시 플래그로 가린 행을 빼고 재면
  경고 없이 통과한 뒤 다음 저장이 통째로 막힌다.
- **저장본을 다시 여는 검증은 조이지 않는다.** 리비전을 읽을 때도 도는 검증(`prepare_*`)에 오늘에 따라 답이 바뀌는
  검사나 새 금지를 넣으면 저장 때 통과한 리비전이 나중에 열리지 않는다. 날짜에 기대는 검사는 저장할 때만 `today=` 로
  넘기거나 막지 않는 알림으로 두고, 새 규칙은 기존 저장본이 새로 막히지 않게 건다.
- 설비 마스터 칸 검증은 **규칙 표 하나**(`equipment_validation.MASTER_RULES`)다 — 저장 거부(처음 걸린 규칙)·칸 단위 결과
  (`equipment_master_issues`)·칸 다듬기(`coerce_master_cell`)가 같은 표, 같은 문구 글자를 본다. 새 규칙은 표에 한 줄을 더하고
  문구는 규칙 문구 함수에서만 가져온다(화면에서 복사하지 않는다). 표 차례를 바꾸면 저장이 던지는 문구가 바뀐다.
- 숫자 입력은 **빈 칸과 못 읽는 값을 가른다.** `to_numeric(coerce)` 한 번으로 둘을 NaN 으로 묶으면 오타(`1,5`·`12m`·
  `180,000`·`105%`)가 조용히 기본값·0·미배치·행 삭제로 내려앉는다. 빈 칸의 뜻은 표마다 정하고(설비대수 편집표 0 대,
  Capa 기준정보 Wide 표 「행 없음」, 주차별 가용대수 붙여넣기 「그대로 둠」, 환산비 1.0, 합계가 같은 세부 수량만 0) 못
  읽는 글자는 행 예시와 함께 막는다(천 단위 쉼표도 받지 않는다). 모든 칸이 빈 행만 떨구고, 읽은 행이 0 인 붙여넣기는
  막는다 — 표를 비우는 경로가 되지 않게. `to_numeric` 은 `inf`·`Infinity` 를 무한으로 읽고 「0 이상」 검사를 지나므로
  붙여넣기·CSV 입구는 무한도 못 읽는 값으로 막는다(기준정보 붙여넣기, 주차별 가용대수 붙여넣기, 기존 보유대수
  붙여넣기·CSV). 되읽기 경로는 바로 위 규칙대로 막지 않는다. 다만 주차별 가용대수 붙여넣기와 기존 보유대수
  붙여넣기·CSV 는 양식에 남은 저장 무한도 그 칸을 짚어 막는다 — 빈칸(주차별)이나 행 빼기(보유대수)로 저장값을 그대로
  둘 수 있어 되돌릴 길이 남기 때문이다. 양식과 같은 무한을 넘기는 것은 기준정보 붙여넣기뿐이다.
- 편집표 왕복은 고친 칸만 원본 위에 덮는다 — 안 고친 컬럼, 값이 빈 실재 행, 원본 표기(`MAIN` 등)를 지킨다. 표기를
  정규화해 저장하면 정확 일치로 잇는 다른 표(`RQ_REQB`)와의 연결이 끊긴다.
- 전체 교체로 저장하는 목록 입력(층·FAB 도면 요소, Space 편집기 적용값)은 어긋난 항목 하나를 조용히 버리지 않고
  통째로 `ValueError` 로 거부한다 — 하나를 버리면 그 항목이 저장에서 지워진다.
- 컬럼 계약 정확 일치 검사는 `frame_contracts.require_exact_columns` 로만 한다 — 손으로 다시 쓰지 않는다. 저장 경계·
  Core Data 78컬럼은 이름 집합만, 붙여넣기·CSV 입력은 `check_order=True, strip=True` 로 차례·머리글 공백까지 본다(문구는
  `tests/test_exact_column_contracts.py` 가 바이트 단위로 고정한다).
- 설비 컬럼 이름과 정지·반출/이설 상태 이름 넷은 문자열로 다시 적지 않고 `services/equipment_contract.py` 의
  상수(`EQUIPMENT_ID_COLUMN`·`STATUS_*` 등)를 쓴다. 파일 입구는 컬럼 차례가 아니라 이름으로 고른다.
- **두 DB 의 공정명은 이름이 같을 때만 맞댄다.** 기준정보와 설비 DB 의 공정명이 같은 이름 공간이라는 강제가 없으므로,
  맞대는 함수는 한쪽에만 있는 공정을 목록(`static_only`·`dynamic_only`·`required_only`·`missing_cutoff`)으로 돌려주고
  화면이 드러낸다 — 조용히 떨어지면 GAP·부족이 이유 없이 커 보인다.
- CS → 양산구분 규칙은 `core_data_derivation.CS_PRODUCTION_CLASSES` 한 곳이다(MP·CS·CB → 양산, ER → ER, 앞뒤 공백 제거·
  대문자로 맞춘 뒤 매핑). 규칙 밖 코드는 등록을 막는다 — 새 코드를 어느 쪽으로 셀지는 업무 결정이다. 양산구분은
  `양산`·`ER` 두 값만 둔다(HOME 은 `양산` 만 넣고 표준 목표·프리셋은 `ER` 만 빼서 세 번째 값은 화면끼리 어긋난다).
- 원천 `제품정보` 는 typed raw 에 그대로 두고, RQ 변환(`core_data_derivation`)에서 BigDataQuery 가 공백 대신 돌려주는
  언더바(`_`)를 공백으로 바꾼 뒤 연속 공백을 하나로 줄인다.
- **RQ 업무 키의 값 충돌은 멈추지 않고 「값이 있는 첫 값」을 임시로 쓴다**(`reference_transformer`·
  `reference_conflicts`). 숫자 `0` 과 빈 글자는 값 없음이라 형제 행에 실제 값이 있으면 그 값이 저장된다(모두 `0` 이면
  `0`). BigDataQuery 등록 화면은 표별 충돌 건수·임시 제외 행 수와 충돌 CSV 를 준다. 원천 정합성 확인용 임시 정책이며
  실제 집계 규칙을 대신하지 않는다. `RQ_PKG_PLAN` 의 Pack Code 별 수량은 충돌이 아니라 별도 행이다(4장).

## 8. 표시·정렬 규칙

- 내부 컬럼명은 Excel 계약과 일치시킨다. 화면 라벨 변경을 이유로 원본 컬럼명을
  바꾸지 않는다.
- 화면 표의 행 정렬은 가능한 `RQ_DISPLAY_ORDER`를 사용한다.
- 런타임 `RQ_DISPLAY_ORDER`는 `app_meta.global_display_order*`의 공용 프로필이며
  시나리오 리비전에 저장된 과거 복사본보다 우선한다.
- 적용 범위는 `페이지 구분 + 탭 구분`이다. 구분자는 리터럴로 적지 않고 `services/display_order_scopes.py` 의 상수만
  쓴다 — 화면 이름이 바뀌어 어긋나도 오류 없이 정렬만 조용히 기본값으로 돌아간다. `표준 목표` 는 `표준 대비 재공 현황`
  과 규칙 한 벌을 함께 쓴다(같은 목표 Capa 축).
- `정렬우선순위`는 행 정렬 키와 화면의 왼쪽 분류컬럼 배치 순서에 함께 적용하고,
  `값표시순서`는 사용자 지정 값 순서다.
- 경로 상세가 있는 대당 Capa·UPEH·Lot/WF측정률·소요대수 표는 `STEP_SEQ → MCP_SEQ`를
  항상 마지막 분류 계층으로 둔다. 기존 공용 프로필에 두 규칙이 없으면 Repository가
  해당 페이지·탭 범위의 마지막 우선순위로 자동 보강한다.
- 지원 정렬방식은 `사용자지정`, `오름차순`, `내림차순`이다.
- `사용자지정` 분류값의 중복은 **저장과 적용이 같은 키**로 판정한다 — `frame_contracts.match_key`
  (앞뒤 공백·대소문자 무시)로 같은 페이지·탭·분류컬럼 안의 **활성(`활성여부 = Y`) 규칙**끼리 겹치면
  중복이다(적용도 활성 규칙만 본다. 글자까지 같은 중복은 꺼 둔 규칙도 예전처럼 막는다). 저장·
  가져오기(범위 직접 편집·Excel 붙여넣기·CSV·`replace_global_display_order`)는 모두
  `display_order_editor.validate_display_order` 한 관문을 지나 `DisplayOrderValueClashError` 로
  막히고, 오류문은 겹친 값을 적은 표기 그대로 범위마다 적는다(앞 5개, 나머지는 「외 N건」).
  - 프로필 전체를 바꾸는 저장(붙여넣기·CSV)은 어디에든 겹침이 있으면 막는다. **범위 하나를 고치는
    직접 편집**은 고른 페이지·탭 안의 겹침(남겨 둔 것이든 새로 만든 것이든)만 막고, 다른 범위에
    **이미 있던** 겹침은 넘긴다(`clashes_outside_scope` → `tolerated_clashes` 를 화면 저장·
    `replace_global_display_order`·`prepare_global_display_order_rules` 까지 넘긴다). 프로필
    전체를 다시 검사하면 두 범위에 예전 겹침이 있을 때 어느 범위를 고쳐도 다른 범위 때문에 막혀
    고칠 길이 없었다(2026-10-07 리뷰 재현).
  - 이 검사 전에 저장된 프로필은 **읽는 길만** 견딘다(`allow_value_clashes=True` — 기동 때 경로 식별
    컬럼 보강·첫 이관·로컬 시드 `data/input/RQ_DISPLAY_ORDER.csv` 읽기, Admin `표시순서 관리` 탭
    열기·내려받기). 기동 보강은 그 프로필을 그대로 두고 미루며, Admin 탭은 겹친 범위를 적고 범위마다
    고치거나 내려받아 고친 뒤 붙여넣는 길을 경고로 알린다. 그 범위를 쓰는 화면은 정렬만 멈추는 것이
    아니라 적용의 ValueError 로 그 부분에 오류를 띄운다. 고쳐 저장하면 그 저장이 보강까지 한다.
  - `data/input` Core Data 경로의 `RQ_DISPLAY_ORDER`(`reference_transformer` →
    `transform_display_order`)는 이 검증을 지나지 않는다(전부터 그렇다).
- 공정 표시명(Proc Rename) 규칙은 한 문장이다 — **화면은 표시명, 파일은 원본.**
  화면에서 사람이 읽는 공정명은 빠짐없이 표시명이고, 적용 계층은 여섯이다.
  ① 월별 표의 분류 값(`value_labels=`, 치환은 `components/` 안에서만 한다),
  ② `multiselect`·`selectbox` 의 `format_func=`(값은 절대 바꾸지 않는다). 표시명을 쓰는 화면의 공정
  선택 상자는 모두(Space 현황·가용설비 현황 설비 마스터 탭은 원본 이름이라 해당 없음) `ProcessLabels.
  unique_format_func` 로 보이는 글자가 겹치지 않게 하고 위젯 앞에서 매 회차 잡은 값을 다시 적는다 — 같은
  글자면 다른 값이 돌아오고, 글자가 바뀌면 브라우저가 옛 글자로 다른 값을 되살린다(9장).
  자리: 가용설비 현황 Main `공정소분류`·Static 대비 일정 `공정`·필요 단축 일정 `공정`·「설정」 팝업 `표 보기 설정`
  공정 필터, 산출 결과 대당 Capa 공정 필터, `column_filter` 의 공정 칸(산출 결과 소요대수·확보율, 기준
  정보 설비대수, 월별 편집기 필터), 표준 목표 공정 필터·로직 분석 `공정`, 표준 대비 재공 `공정`, Dynamic
  Capa 상위 `공정`, 실적 세 화면(효율·UPEH·수율) `공정`, HOME Preference 주요공정 프리셋 `공정`(key 없는
  상자 — 아래 9장), 기준 정보 STEP 복제·삭제 대상(`capacity_step_route` — 글자에 경로 키 전부·MCP/STEP 을
  싣고 공정은 갈라, 같은 글자가 남으면 「 #n」; 값은 행 위치가 아니라 경로 키),
  ③ Figure 라벨(LOB 공정명 annotation·hover, 상세 B/N 이름·hover, 재공 격자 제목,
  Dynamic Capa 공정 비교 막대의 y축, 실적 세 화면 공정 우선순위 막대·월 × 공정 Gap 격자의 y축, 가용설비 현황 Main
  생애주기 Gantt 의 hover). 공정을 **범주 축 값**으로 늘어놓는 그림은 축 값을 원본 공정으로 두고 눈금(`ticktext`)과
  hover(customdata)만 표시명이다(`ProcessLabels.category_axis`) — Plotly 범주 축은 같은 글자를 한 줄로 합쳐, 표시명을
  축 값으로 쓰면 표시명이 다른 공정의 원본과 같을 때 두 막대가 한 줄에 겹쳐 값이 가려지고 순위 차례가 틀렸다
  (2026-10-25 E2E). 겹친 두 공정은 같은 글자의 두 줄로 보인다,
  ④ `st.dataframe` 조회 표(제외·누락 안내 목록, STEP 구성 요약, 설비대수 표시 표,
  예외 처리 공정 안내, Dynamic Capa 관리 우선순위, 가용설비 현황 Main 의 `공정소분류` 칸 — 공정별
  내역·비가동 호기·호기 목록·Qual 호기 목록·전환 일정 목록 — 과 Static 대비 일정의 칸 호기·호기 목록·
  확보율 교차검증 표, Capa Chatbot 근거 표)와 화면용 안내 문구(Main 의 걸린 조건 줄, Capa Chatbot 대본의 결론·질문·
  조건 — 대본 함수가 페이지가 넘긴 `ProcessLabels.label` 로 적는다),
  ⑤ `st.data_editor` 분류 컬럼의 `st.column_config.SelectboxColumn(format_func=)` 라벨.
  월별 편집기의 분류 컬럼은 언제나 한 컬럼이고 표시용 컬럼을 따로 두지 않는다. 편집표는 ② 의 「같은
  글자면 다른 값」 결함이 없다 — 칸은 옵션 `value` 로 찾아 `label` 을 그리고, 고르기·붙여넣기·복사가 모두
  `value` 로 오가며, 브라우저가 보내는 편집은 「행 위치·컬럼·새 값」이다(2026-10-10 Streamlit 1.63 프런트
  번들·AppTest·실제 브라우저로 잼). 그래서 월별 편집기의 읽기 전용 분류 칸은 그대로 두고(표와 같은 갈래 —
  겹친 두 공정이 같은 글자로 보인다), 사용자가 목록에서 고르는 칸(HOME 확보율 보정의 `공정`)만 목록에서
  가려 고르도록 `unique_format_func` 로 글자를 가른다.
  ⑥ 버튼 라벨·`help`(HOME 의 B/N 공정 선택 바둑판). 글자와 도움말만 표시명이고 콜백
  인자(`args=`)·위젯 키·적용 때 되쓰는 값은 원본 `공정` 이다. 버튼은 값을 글자로 주고받지 않아 ② 의
  결함이 없고 글자를 가르지 않는다(겹친 두 공정은 같은 글자의 바둑판 두 칸으로 보인다).
- ④ 에서 CSV 출구가 있는 표는 **화면 프레임과 CSV 프레임을 나눈다.** 화면 복사본에만
  표시명을 입히고 내보내는 프레임은 원본 그대로다(`components/exclusion_table.py`,
  `app_pages/static_capa.py`, 가용설비 현황 Static 대비 일정의 호기 목록이 그 모양이다 —
  복사본은 `ProcessLabels.frame`). 계산 결과의 `attrs` 유래 프레임은
  `@st.cache_data` 가 들고 있으므로 반드시 복사본에 입힌다.
- ⑤ 에서 **분류 컬럼의 값은 언제나 원본이다.** `SelectboxColumn` 은 옵션의 `value` 와
  `label` 을 나눠 갖고 편집 결과·복사 데이터로는 `value` 를 돌려주므로 셀에 보이는 글자만
  바뀐다. 값 자체를 표시명으로 갈면 `merge_edited_months` 의 되머지 키가 어긋나 편집이
  조용히 버려지고, 필터를 걸지 않은 단축 반환 경로에서는 표시명이 그대로 `RQ_*` 저장값이
  된다. 옵션에는 그 표의 값 전체를 넣는다 — 옵션에 없는 값은 셀이 빈칸으로 그려진다.
- 표시명이 닿으면 안 되는 곳은 다섯 갈래다. ① 왕복 CSV·클립보드 양식(기준정보 월별
  편집기, 설비대수, 주차별 가용대수, 표시순서, Proc Rename 규칙 자체), ② 보고용 CSV
  전부(월별 표 CSV, 제외 목록 CSV, Static Capa 부족 현황 CSV, 필요 단축 일정 CSV 세 벌, Static 대비 일정
  호기 목록 CSV, Cut-off CSV) — 그대로 옮겨 쓰는 파일이다, ③ 원본 키를 편집·확인하는 화면(표시순서
  관리의 `분류값`, Proc Rename 탭의 `보유 공정` 목록, 필요 단축 일정 「맞대지 못한 공정」, Static 대비 일정 의
  「두 쪽의 공정명이 맞지 않는 자리」 경고와 한쪽에만 있는 공정의 까닭 문구, 「설정」 팝업 Cut-off 편집표의
  `공정` 칸과 「Cut-off 를 적지 않은 공정」 경고, 설비 마스터 탭 입력 전부), ④ `services/` 의 예외 메시지(원본을
  고치라는 안내다)와 프리셋·세션 저장값, ⑤ 설비 DB 의 `공정대분류`·`공정소분류`(필요 단축 일정 공용 조회
  조건의 공정 목록도 원본이다).
  경계는 `services/` 가
  `components/process_labels.py` 를 import 하지 않는 것으로 강제하고
  `tests/test_process_label_boundaries.py`·`tests/test_process_rename.py` 가 검사한다.
- `st.dataframe` 그리드 우상단의 내장 `Download as CSV`·복사는 화면 프레임을 그대로
  내보내므로 표시명이 들어간다. 끄는 인자가 없다. 원본이 필요한 사용자는 표 위의 CSV
  버튼(`components/table_toolbar.py`)이나 왕복 CSV 양식을 쓴다.
- 표시명을 적어 붙여넣는 실수는 입력 경계에서 막는다. 주차별 가용대수 붙여넣기는
  `services/weekly_availability_input.py` 의 준비 함수가 `known_processes` 로 받은 보유
  공정 목록 밖의 이름을 한국어 `ValueError` 로 거절한다. 목록은 화면이 소유하므로
  페이지가 넘기고, 저장된 값을 되읽는 경로와 계산 경로는 목록 없이 부른다.
- 월별 편집기의 왕복 CSV 는 필터 이전의 전체 표이고 언제나 원본 공정명이다. 화면이
  표시명일 때는 편집기 아래에 그 사실과 양식을 보라는 안내를 함께 그린다. 표시명 조회는
  페이지가 하고 `components/month_editor.py` 는 받은 매핑으로 필터 옵션과 분류 컬럼
  라벨만 만든다.
- 매핑에 없는 공정은 원본 공정명을 그대로 표시하고, 보유하지 않은 원본에 지정된
  표시명은 오류가 아니라 무시한다. 표시명이 짧아지면 상세 B/N 의 글자 축소·말줄임이
  자연히 걸리지 않는다 — 축소 로직을 새로 넣지 않는다.
- 월별 컬럼은 선택한 유효 조회기간만 전개한다. **월 표기와 월 축은 한 벌이다** — 조회기간·시나리오 월 `YYYY-MM` 은
  `settings.format_month`, 표의 월 칸 `YY.MM` 은 `month_columns.month_label` 이고 화면 모듈이 사본을 두지 않는다. 표·
  차트·스크롤 폭은 `month_columns` 가 만든 라벨 목록 하나를 보고, 연간 Total 은 1~12월이 모두 조회범위 안인 해에만 둔다.
- 연간 Total 칸에는 물량(Density·Wafer 계획·계획 세부수량)만 합계를 적고 Capa·확보율·B/N 칸은 비운다 — 월별 Capa 의
  단순 합은 연간 Capa 가 아니라 그 해 투입 가능량으로 잘못 읽힌다.
- 주요 표의 분류 컬럼은 고정하고 월 컬럼은 필요할 때 가로 스크롤한다.
- **판정 기준 표시.** 확보·경고 기준(기본 109.5%·99.5%)을 화면에 **적는** 곳은 모두
  `services/threshold_label.threshold_percent_label` 로 사사오입한 정수 퍼센트를 쓴다 —
  109.5 → `110%`, 99.5 → `100%`. 업무의 원래 기준은 110%·100% 이고, 반 칸 낮춘 것은 아슬아슬하게
  모자란 공정도 기준을 채운 것으로 넣으려는 장치다(2026-10-03 사용자 결정). 지금 적는 곳은 HOME
  공정 필터 팝업의 기간 줄(기본값 + 「월별 예외 N개월」), Static Capa 판정 기준 카드, 입장 화면
  Summary 의 기준선 이름표(달마다 — 값이 바뀌는 구간마다 하나)다. **범례에는 숫자를 적지 않는다** —
  HOME(`home_preference.status_legend_markup`)·Summary 범례 모두 「확보 · 경고 · 부족」 세 이름뿐이고
  과거 구간 칩도 없다(2026-10-06 사용자 결정 — 기준이 달마다 다를 수 있어 숫자
  한 짝은 예외 달에서 거짓이 된다). **바꾸지 않는 것**: 판정(`capacity_status`·
  `securement_rate`·`process_picker` — 정확한 기준), 저장값(공용 판정 기준 프로필의 비율), 기준을 고치는
  `number_input`(정확한 값을 보여야 고친다), 차트 기준선의 **자리**(109.7% 확보 막대가 선 위에
  선다), 입력 오류 안내(「경고 기준이 확보 기준보다 큰 달이 있습니다: 26.07(경고 X% > 확보 Y%)」 — 입력값을 그대로 말해야
  고칠 수 있고, 반올림하면 「110% 가 110% 보다 크다」가 된다). 새로 기준 숫자를 적는 화면도
  같은 함수를 쓴다.
- **분류 셀 글자는 `classification_cell_text()` 를 거쳐야 한다**(`components/monthly_table_base.py`). Plotly `go.Table`
  칸 글자에 `&`·`<`·`>` 가 있으면(`&amp;` 도) HTML 경로로 넘어가 그 행만 높이가 커지고 격자선·월 Figure 와 어긋나며
  마지막 행이 잘린다. 그래서 전각(`＆＜＞`)·`U+00A0` 으로 바꾸고 CSV 는 `restore_cell_text()` 로 원본을 돌려준다.
- **파이썬 코드에 색 리터럴(`#RRGGBB`·`rgb()`·`rgba()`)을 쓰지 않는다.** 색·서체·표 치수는 `design/tokens.py` 의 역할 이름으로 쓰고(규칙
  `docs/design_system.md`), 새 색은 두 팔레트(`_LIGHT`·`_DARK`)에 같은 이름으로 함께 더한다 — 한쪽에만 있으면 그 테마에서
  화면이 그 자리에서 죽는다(`tests/test_design_tokens.py`).
- 상태색 `STATUS_*` 는 면색이다 — 강조 칸 바탕에 깔고 그 위 글자는 `TEXT` 로 둔다(글자색으로 쓰면 어두운 테마에서 대비가
  무너진다). 늘고 준 차이(증감)는 상태색이 아니라 `DELTA_*` 로 칠하고(증감은 좋고 나쁨이 아니다) 글자 크기는 화면
  어디서나 `tokens.DELTA_FONT_SIZE_PX` 하나다 — 크기가 갈리면 같은 뜻의 표기가 위계처럼 읽힌다.
- 색만으로 뜻을 나르지 않는다 — 등급·상태·값은 글자(등급 글자·hover·칸 안 숫자)로도 적는다.
- **판정할 값이 없으면 0 으로 그리지 않는다.** 확보율이 없는 공정·달은 0% 가 아니라 「판정 없음」이다(`process_picker` 의
  판정 없음 구역) — 0 으로 그리면 없는 부족이 생긴다.
- **화면 숫자는 검산되어야 한다.** 줄을 더해 칸이 되는 표·CSV 는 값을 반올림하지 않고 표시 서식만 자릿수를 정한다(0 아닌
  값이 0 으로 적히면 자릿수를 늘린다). 식을 적는 근거 카드는 적은 자릿수로 다시 셈한 값이 결과와 다르면 `=` 대신 `≈` 를
  쓴다. 숫자 글자는 말줄임으로 반만 자르지 않는다 — 잘린 「4」가 411대를 4대로 읽힌다. 넘치면 숫자 전체를 숨기고
  풍선에 둔다.
- 범위가 다른 같은 이름의 숫자(배치된 설비만 센 「가용」과 설비 마스터 전체의 「가용」)를 두 화면에 세우지 않는다 — 그
  숫자는 정의하는 화면 한 곳에만 둔다.
- 조건부 안내·경고는 건수가 0 이면 아무것도 그리지 않는다 — 없는 날 자리를 차지하면 있는 날에도 읽히지 않는다(자리
  고정이 필요하면 늘 서 있는 빈 `st.container()` 칸만 둔다, 9장).
- **값 뒤 조사는 `services/korean_particle.py` 만 — 앱 코드는 시험이 지킨다.** f-string·`str.format`·`%s` 틀에 끼운 값(시나리오명·
  공식버전명·리비전 번호·공정·호기·칸 이름·숫자·날짜를 넣는 알림·오류·로그·스크립트 출력) 바로 뒤에 조사를 못박지 않고
  `with_object_particle`·`with_topic_particle`·`with_subject_particle`·`with_direction_particle`(조사만 따로 쓸 때
  `*_particle`)로 붙여 쓴다 — 값과 조사 사이를 띄우지 않는다(「r1을」). 손으로 박은 갈래 꼴(「{x}은(는)」)도 쓰지 않는다 —
  도우미가 읽지 못하는 끝(영문)에서 같은 꼴을 낸다. 앱이 늘 끼우는 고정 어휘의 영문 끝(층 이름의 `F`·`DB`·`size`·`Capa`·단위
  `Kea`)는 도우미의 읽기 표 `_LATIN_TAIL_FINAL` 이 읽는다 — 새 고정 어휘가 갈래 꼴로 떨어지면 거기에 더하고(JS `withJosa` 표도),
  사람이 붙인 이름의 영문 끝은 더하지 않는다. `tests/test_particle_sites.py` 가 `app.py`·`app_pages`·`src` 를 AST 로
  훑어 붙은 꼴·띄운 꼴·갈래 꼴과 `{…}`·`%s` 틀 뒤 고정 조사(값을 감싼 따옴표·낫표 뒤, 괄호를 사이에 둔 꼴 포함)를
  막는다 — `scripts/` 는 훑지 않으므로 스크립트 출력은 리뷰 몫이다(패키지를 import 하지 않는 `apply_deploy_package.py` 는
  고정 명사를 사이에 둔다). 배치 편집기 JS 의 `${…}` 뒤는 `editor.js` 의
  `withJosa`(같은 표 — 같은 시험이 node 로 파이썬과 대조한다)로 고른다. 굵게 감싼 이름은 닫는 `**` 와 조사 사이를 한 칸
  띄운다(`**{x}** {subject_particle(x)}` — 붙이면 `)` 로 끝나는 이름에서 굵게가 풀린다). ALL_CAPS 상수 뒤에는 고정 조사를
  둘 수 있고, 시험이 그 상수의 실제 글(서식 지정까지)로 견준다 — 끝이 영문이면 시험의 읽기 표(`_READINGS`)에 읽기를
  적는다. 괄호 뒤 조사는 괄호 앞 낱말에 붙는다 — 그 낱말이 고정 글이면(「최신(r6)이」) 그대로 두고, 끼운 값이면 그 값으로
  고른다(「{mark_id}({name}){subject_particle(mark_id)}」 — 괄호째 `with_*` 에 넘기면 도우미가 닫는 괄호를 건너뛰어 괄호 안
  끝소리를 읽는다). 한 칸 띄운 「이」는 지시어(「{x} 이
  시나리오」)와 갈리지 않아 시험이 보지 않는다 — 리뷰 몫이다. 고르기 어려우면 고정 명사를 사이에 둔다(「「…」 공정은」·
  「{label} 값은」). 한 라벨에만 쓰는 고정 문구(값을 끼우지 않는 글)는 그 라벨에 맞춘 조사를 그대로 둔다.
- **화면 사용 설명은 본문이 아니라 Guide 에 둔다.** 원문은 패키지 안 `guides/<페이지 파일 이름>.md` 이고 화면이
  `page_guide.render_page_guide` 를 진행 막대 자리(`render_page_header_with_status`)보다 먼저 부른다. 옮긴 핵심 문구는 화면
  테스트(`test_*_guide_carries_*`)가 대조한다. 누르기 전에 알아야 하는 경고(되돌릴 수 없는 저장)는 버튼 곁에 남긴다.
  따라하기 가이드(`guides/howto/`)가 있는 화면의 Guide 는 앱을 덮지 않는 옆 창을 열고, md 원문은 그 창의 「설정 사전」이
  된다(3장 `page_guide.py`) — md 를 지우지 않는다.
- **사이드바 상자는 한 모양이고 오른쪽 끝 표식으로 용도를 가른다.** 목록 상자와 조건 카드는 같은 서식의 `st.expander`
  이고, 다른 화면으로 가는 링크는 `arrow_forward`, 그 자리에서 펼치는 패널은 `expand_more`, 팝업이 뜨는 값 칸은
  `unfold_more` 다. `›` 는 Streamlit hover 글리프라 쓰지 않고 서식 예외 상자를 만들지 않는다.
- 조회기간 줄의 적용 기간 글자는 셋이다 — `app.py` 가 모든 페이지에 먼저 쓰는 「선택 · 범위」, 조회기간을 실제로 읽은
  화면이 덮는 「✓ 적용 · 범위」, 그 뒤 Capa 계산이 멈추면 덮는 「계산 멈춤」. 「✓ 적용」과 본문 「계산을 멈췄습니다」가
  함께 뜨면 안 된다.

## 9. Streamlit 구현 규칙

- 페이지 간 공유 위젯은 `app.py`에서 `navigation.run()` 전에 만든다.
- **외부 네트워크 자원을 쓰지 않는다.** 사내망에서는 CDN·Google Fonts 가 닿지 않는다. 글꼴·
  스크립트는 저장소에 두고 등록 때 싣는다(`components/intro_overlay.py` 의 부분 글꼴).
- **「실행이 끝났다」를 `navigation.run()` 뒤의 요소로 알리지 않는다.** 페이지가 `st.stop()`
  하면 그 뒤로는 `finally` 에서 그린 요소도 브라우저에 닿지 않는다. 브라우저 쪽에서 실행 상태를
  본다(`components/intro_overlay.py`). 모든 화면이 브라우저로 꼭 보내야 하는 값(입장 화면 요약)도
  같은 까닭으로 `navigation.run()` **앞**에서 보낸다(`components/intro_summary.py`).
- 페이지 전용 위젯에는 고유 `key`를 부여한다.
- 페이지 이동 후에도 유지해야 하는 위젯은 현재 Streamlit 버전의
  `persist_state="session"` 패턴을 따른다. 이동 길은 사이드바와 화면 탭 줄 둘이고 위젯 정리는 같다(탭 줄도
  `st.switch_page` 다). **보기 조건 위젯에는 `"page"` 를 쓰지 않는다** — 하위 보기 전환(산출 결과 「표시 방식」)도
  보기 조건이라 탭으로 다른 화면에 갔다 오면 돌아가 같은 카드의 다른 칸과 어긋난다. 남길 탭 묶음은
  `stateful_tabs` 로 만든다(시나리오 관리 세 탭 — 폼 입력을 지키려 세 탭을 다 그린다).
- **같은 key 의 위젯을 둘 이상의 페이지가 그리면 `persist_state` 만으로는 부족하다.** 위젯 id 에
  페이지가 들어가 넘어온 첫 회차의 위젯이 기본값으로 선다. 위젯을 만들기 전에
  `shared_widget_state.carry_shared_widget_value` 를 부른다. 이것이 위 「`app.py` 에서만」 규칙의 예외다 — 판정 기준
  두 칸, 「샘플 데이터」 스위치, UPEH 가정 세 칸(공정 Capa 상세·필요 단축 일정)이 그렇다. 두 화면의 선택지는 한 함수로
  내야 옮긴 회차에 「선택지 밖 → 새 값」이 말없이 일어나지 않는다. 위젯을 그리지 않는 자리(시나리오 전환)가 그 값을
  새로 적으면 주인 칸(`shared_widget_owner_key`)도 지운다.
- **선택지가 바뀌어 세션 값을 버려야 할 때는 `pop` 하지 말고 새 값을 적는다.** 지우기만 하면
  서버는 기본값을 쓰지만 브라우저는 그 사실을 듣지 못해 옛 선택을 계속 보여 준다(HOME
  Preference 비교 리비전, 2026-10-05 E2E). 보여 주기만 하는 데서 그치지 않는다 — 브라우저는 그
  옛 값을 다음 조작에 되보내 서버 값까지 되살린다(시나리오 전환의 HOME 토글, 2026-10-08 안정화
  점검 B1). Streamlit 은 세션 API 로 **새로 적힌** 위젯 값만 브라우저에 보내고(`set_value`),
  `st.rerun()` 으로 이어진 회차는 세션을 다지지 않아 앞 회차에 적은 값이 그대로 「새 값」이다.
  위젯 앞에서 칸이 없을 때 기본값을 심는 쪽(HOME 카드 토글)도 그 회차에 새로 적은 값이라 같은
  효과를 낸다 — 지운 칸을 다음 회차의 심기가 메워 주므로, 「적는다」를 검사할 때는 심기를 거치지
  않는 자리에서 본다(`test_scenario_activation`). 폼 안 입력을 성공 뒤 비울 때도 같다 — 위젯을 그린
  **뒤**에는 적을 수 없으므로 표지를 남겨 다음 회차 위젯 앞에서 빈 값을 적거나 key 세대를 바꾼다
  (`clear_on_submit` 은 쓰지 않는다 — 거절된 제출에도 적은 글을 지운다).
  **닫힌 팝업 안처럼 브라우저에 마운트되지 않은 위젯은 적은 값도 받지 못한다** — 그때는 key
  세대를 바꾼다(사이드바 저장 폼, 2026-10-08). 나중에 열려 마운트되는 칸은 **마지막 회차가 실어
  보낸 값**(`set_value`)으로 서고, 없으면 빈 기본값으로 선다 — 비우는 칸이 아니라 지금 값으로 세워
  둘 칸(설비 시나리오 구획의 리비전명·시나리오 이름)은 한 회차만 적지 말고 고치지 않은 동안 **매
  회차** 다시 적는다(2026-10-26 E2E — 한 회차 뒤에 연 칸이 빈 칸으로 서 그대로 저장하면 이름이
  지워졌다, `tests/test_equipment_scenario_name_fields.py`). 글 칸은 Enter·포커스 빼기에 확정되어 그 회차의 칸 값이
  이미 친 글이므로 같은 값을 매 회차 적어도 치던 글을 덮지 않는다 — 범위 밖 글을 확정하지 않고 쥐는 숫자 칸은 **다를 때만**
  적는다(`preset_number_field`). **세션 키로 여는 팝업의 초안**(사이드바 시나리오
  팝업의 시나리오·리비전 선택)은 여는 콜백이 위젯이 만들어지기 전에 올라와 있는 값으로 **적는다** —
  다시 마운트되는 위젯이라 그 값에서 선다.
- **선택 상자의 `format_func` 라벨에 회차마다 바뀌는 상태(활성 표시·개수 등)를 넣지 않는다.**
  Streamlit 1.63 선택 상자는 고른 항목의 라벨 글자를 주고받는다. 값은 그대로인데 라벨만 바뀌면
  브라우저가 옛 라벨을 되보내고, 서버는 그것을 바뀐 값으로 읽어 `on_change` 를 부르고 앱 전체를
  다시 돌린다(HOME 비교 리비전, 2026-10-08). 바뀌는 상태는 상자 밖 캡션에 적는다(HOME 비교
  선택의 `_comparison_active_note`, 주요공정 「고칠 프리셋」의 기본 프리셋 캡션). 글자가 바뀌는 것을
  피할 수 없는 상자(공정 표시명의 「표시명 (원본)」 가르기 — `ProcessLabels.unique_format_func`, 다른
  세션의 이름 바꾸기로 바뀌는 시나리오 이름 — HOME 비교 시나리오·주요 Case 시나리오·파생 시나리오 원본 상자·사이드바
  시나리오 팝업의 시나리오 상자, 리비전명 변경으로 바뀌는 「r{번호} · {리비전명}」 — HOME 비교 리비전·주요 Case
  리비전·파생 원본 리비전·사이드바 팝업 리비전 radio)는 위젯 앞에서 매 회차 잡은 값을 세션에 다시
  적어(`prune_choice`·`prune_list_selection`) 브라우저에 새 글자를 보낸다. 적지 않으면 브라우저가 옛 글자를
  되보내 다음 회차에 그 글자가 id 자리에 들어가거나, 선택이 빈 값으로 풀리거나, **예외 없이 첫 항목으로
  조용히 바뀐다**(옛 시나리오 관리 카드 리비전 상자에서 r2 를 고르고 누른 「시나리오 불러오기」가 최신 r3 을 올렸다 —
  2026-10-22 AppTest 실측). 시나리오 관리 목록 관리(C안)의 두 편집표는 고름을 글자가 아니라 행 id 초안으로 들어
  (`components/pick_edit_table.py`) 이 목록에 들지 않는다. 그래서 시험은 「예외 없음」이 아니라 **누른 회차에 실제로 걸린
  대상 id** 로 잰다. 일반 `AppTest.run()` 은 회차마다
  세션 값으로 글자를 다시 만들어 이 결함을 보지 못한다 — 브라우저처럼 글자를 들고 다니는
  `tests/widget_browser.py` 의 `BrowserChoice`(selectbox·multiselect·radio)로 잰다.
  AppTest 의 `select`·`set_value` 는 **값**을 받아 `format_func` 로 글자를 만든다 — 보이는 글자(「가공」)를
  넘기면 선택지 밖 값으로 걷힌다. 사용자가 보이는 글자를 고르는 것을 재려면 `BrowserChoice.pick` 을 쓴다.
  **key 없는 상자**(HOME 주요공정 프리셋 `공정` — `default=` 로 프리셋 값을 받는다)는 위젯 id 에 보이는
  글자가 들어가 글자가 바뀌면 새 위젯으로 선다. 옛 글자가 되돌아올 자리가 없어 다시 적을 칸도 까닭도
  없고 글자만 가른다.
- **세션에 값을 적는 위젯에는 `value=`(`default=`·`expanded=`) 기본값을 주지 않는다.** 둘을 함께
  주면 Streamlit 이 「기본값과 세션 API 를 함께 썼다」고 경고한다(기본값이 `False`·첫 항목이면
  조용하다). 기본값은 위젯 앞에서 칸이 없을 때만 세션에 심는다(HOME 토글 — `render_home_view_card`,
  사이드바 상자 — `sidebar_status._remembered_box`).
- **조회 조건은 시나리오를 바꿔도 살아남아야 한다 — 데이터만 바뀐다.** 불러오기는
  `st.rerun()` 을 부르고 그 호출이 그 자리에서 실행을 끊는다. 사이드바 시나리오 팝업 안의
  불러오기는 브라우저에서 프래그먼트 실행이라 페이지 위젯을 건드리지 않지만, 시나리오 관리 화면의
  불러오기처럼 앱 전체 실행 한가운데서 끊는 경로는 그 회차에 페이지 본문(의 나머지)이 돌지 않아
  Streamlit 이 만들어지지 않은 위젯의 값을 버린다 — 필터·토글·탭이 통째로 초기값으로 돌아간다.
  AppTest 는 팝업 안 클릭도 앱 전체 실행으로 돌려 이 거친 조건을 재현한다. 새 필터·분류 수준·표시
  토글에는 `persist_state="session"` 을 **반드시** 준다. 선택지가 달라져도 안전하다 — 없어진 값은
  multiselect 가 걷어 내고 selectbox 는 첫 항목으로 돌아간다.
- **확인용 체크박스와 입력 초안에는 `persist_state` 를 주지 않는다.** 「정말 지울까요」가
  살아남으면 다음 화면이 이미 체크된 채로 뜬다. 초안이 사라지는 회차에는 그 초안에서 나온 위젯 아닌
  칸(미리보기)도 함께 거둔다 — 설비 마스터 탭 입력은 페이지에 새로 들어온 회차(`page_bootstrap.page_visit`,
  `app.py` 가 페이지가 바뀐 회차에 올린다)에 미리보기를 버린다. 「입력 칸이 세션에 없으면 거둔다」로
  가르지 않는다 — 같은 페이지의 `st.rerun()` 도 서버에서는 칸이 비지만 브라우저가 입력을 다시 보낸다. 화면 탭 줄로
  오가는 왕복에도 초안은 남기지 않는다(같은 규칙 — 제출 전 폼 글은 서버에 없다).
- 탭은 `components/tab_state.py` 의 `stateful_tabs` 가 열린 탭을 위젯 아닌 칸에 적어 두고
  위젯 값이 사라졌을 때만 되돌린다. **`st.tabs` 의 `default` 인자는 쓰지 않는다** — 그 값이
  위젯 id 계산에 들어가 탭을 옮길 때마다 위젯이 새로 만들어지고 선택이 또 사라진다.
- `scenario_activation._STALE_UI_KEYS` 는 **앞 시나리오의 값이 담긴 칸과 HOME 토글**을
  담는다. 토글은 값에 닿으므로(얹거나 뺀다) 시나리오를 바꾸면 풀어야 하고, **탭과 조회
  조건은 담지 않는다** — 그것들은 무엇을 보고 있는지일 뿐이라 지우면 시나리오를 바꿀 때마다
  보던 자리를 다시 찾아야 한다. 값에 닿는가로 가른다. 값 칸은 지우고 토글 칸은 **기본값을
  적는다**(위 「pop 하지 말고 새 값을 적는다」). 토글을 푸는 것은 **보는 내용이 바뀔 때**뿐이다 —
  활성 시나리오의 새 리비전 저장(`activate_saved_revision`)은 방금 보던 내용을 적은 것이라
  토글을 그대로 둔다.
- 비싼 계산을 탭 내부에서 직접 반복하지 않는다. 먼저 캐시된 결과를 만들고 탭은 표시만
  담당하게 한다. 접힌 `st.expander` 의 본문도 매 회차 실행된다 — 비싼 Figure 는 캐시 쪽에서 만들어 넘기고 그리는
  함수는 받은 그림만 그린다.
- **배경 스레드에는 Streamlit 실행 문맥(ScriptRunContext)이 없다.** 그런 스레드는 공식버전 자동 갱신
  예약(`auto_update_scheduler.py`) 하나이고, 실행 줄 허락(`CAPA_AUTO_OFFICIAL_UPDATE=1`)이 있는 프로세스에만
  선다. 그 안에서 `st.*` 화면 명령·`st.session_state`·`st.cache_data`/`st.cache_resource` 래퍼를 부르지
  않는다 — 계산은 순수 코어(`simulation_cache.full_capacity_outcome`·`calculate_securement_rate`), 등록은
  세션 없는 `scenario_registration` 이다. 캐시 정리는 전역 범위 `st.cache_data` 함수의 `.clear()` 처럼
  문맥을 찾지 않는 것만 쓴다. 새 스레드를 세우지 않는다 — 예약이 더 필요하면 이 모듈에 더한다.
- **DuckDB 연결 핀.** 앱은 rerun 한 번을 `pinned_connections` 로 감싼다(게으른 핀 — 첫 연결 뒤에 잡고 가장 바깥 블록이
  끝날 때 닫는다). 설비 DB 를 rerun 한 번에 **여러 번** 여는 화면만 `navigation.PageSpec.uses_equipment_db` 를 선언해 같은
  핀을 받는다. 위젯 콜백(본문 전)과 팝업 본문 프래그먼트는 실행 핀 밖에서 돌므로 DB 를 여러 번 여는 콜백·팝업은 스스로
  `pinned_connections` 를 잡는다(`home_preference._replace_comparison_profile`, `scenario_status` 팝업).
- **(2026-10-01 브라우저 E2E 점검에서 나온 규칙)**
  - **`st.rerun()` 은 그 화면의 모든 편집표를 그린 뒤에만 부른다.** Streamlit 은 `st.rerun()` 으로
    끝난 회차를 정상 완료로 보고 그 회차에 등록되지 않은 위젯 상태를 서버에서 지운다 — PKG PLAN
    적용이 수율 편집표보다 먼저 rerun 해 수율의 적용하지 않은 편집이 목록에서 사라졌다.
  - **잠긴(disabled) 위젯으로 온 조작은 서버가 버려 코드가 알 수 없다.** 보여 준 회차와 누른
    회차에 잠금 조건이 달라질 수 있는 제출 버튼은 잠그지 말고 누른 회차에 판정해 알린다.
  - **편집표에 빈칸이 있으면 `placeholder=""` 를 넘긴다.** 기본값은 결측 칸에 `None` 글자를 쓴다
    (`tests/test_data_editor_placeholder.py` 가 소스 전체를 훑는다).
  - **조건부 알림(flash·오류) 뒤에 오는 key 없는 탭·확장 패널은 알림이 생기거나 사라질 때 위치가
    밀려 새로 만들어지고 선택·펼침을 잃는다.** 본문의 펼침·탭은 key 로 고정한다. 한 회차라도
    그려지지 않는 자리(닫힌 탭 안, 모드 전환)에 있으면 key 만으로는 잃으므로
    `sidebar_status.remembered_expander`(상태 위젯 + 기억 칸, 여닫으면 빈 프래그먼트만 돈다)를
    쓴다. 라벨에 개수 같은 바뀌는 값을 넣은 key 없는 확장 패널도 같은 이유로 접힌다.
    key 없는 팝오버도 같다 — 알림이 빠지는 다음 회차에 한 칸 당겨져 다시 서며 닫히므로, 알림 뒤 처음 누른 팝오버 안
    확인 체크·Enter 가 팝오버를 닫았다(2026-10-25 E2E, 설비 시나리오 구획). 알림은 늘 서 있는 칸에 두고, 작업을 마친
    팝오버를 닫으려면 key 꼬리에 세대를 붙여 그 알림을 그리는 회차에만 바꾼다(3장 `equipment_scenario_management.py`).
    **모든 팝오버는 key 를 받고, 라벨이 글자 그대로가 아닌(개수·이름이 드는) 확장 패널도 key 를 받는다** — Space 저장 안
    한 배치 상자의 「저장 칸」·「버리기」 팝오버가 상자 안 저장 오류 한 줄에 밀려 닫히던 자리를 이것으로 막았다
    (`tests/test_popover_keys.py` 가 소스를 훑고, 오류가 서는 회차에도 블록 id 가 같은지 본다).
  - **알림 칸은 `components/flash.py` 한 길이다.** 콜백·본문의 결과는 `queue_flash` 로 담고 그 칸은 `render_flash` 로
    그린다 — 칸마다 `session_state.pop` 해 `st.success` 따위로 그리는 길을 따로 두면 끊긴 회차·자리 밀림 고침이 그
    칸에만 가지 않는다(2026-10-26 리팩토링 — 칸 열여섯을 옮겼고, 리뷰 뒤 설비 마스터 탭 저장 결과·VOC 머리 알림과 글
    쓰기·글 상자 실패·Space 설비 시나리오 바꾸기 실패를 더 옮겼다). 실패만 내는 칸도 같다(`kind="error"`).
    `render_flash` 는 알림이 없어도 칸 하나를 세워 이 절의 「늘 서 있는 한 칸」 을 저절로 지키고, 돌려받은 칸에 실패
    문구나 같은 동작의 경고 여러 줄(표시순서 저장의 표시명 경고)을 쓴다. 다음 동작까지 남아야 하는 칸(VOC 지운 글의
    적어 둔 답변, 필요 단축 일정 기준선 shown 칸), 매 회차 비우고 보이는 탭에서만 그리는 칸(기준정보 STEP), 페이지가
    같은 `st.empty` 자리에 오류를 덮어 쓰는 칸(월 편집표), 회차의 상자 유무로 두 자리 가운데 하나에 서는 칸(Space 배치
    저장 실패)은 `tests/test_flash_messages.py` 의 허용 목록에 까닭과 함께 둔다. 그물은 이름(FLASH·NOTICE)만 보지 않고
    꺼낸 값이 알림 요소에 드는지를 본다 — ERROR·RESULT·WARNINGS 이름 칸이나 `get` 뒤 `del` 로 되돌린 꼴도 잡는다.
  - **key 가 있어도 자리는 고정한다(2026-10-05 E2E).** 저장 회차(알림 없음)를 `st.rerun()` 으로
    끊고 다음 회차(알림 있음)에서 key 있는 탭 묶음이 한 칸 밀리면, 옛 자리에 회색 사본이 남아
    새로고침 전까지 다른 페이지까지 따라왔다(설비 마스터 탭(옛 RawData) 두 번째 저장). 수가 바뀌는 알림은
    `st.container()` 한 칸 안에 그려 그 아래 형제의 자리를 고정한다. VOC 도 같다 — 답변 0 인 글에
    첫 답변을 남기면 맨 위 알림과 첫 답글이 함께 생겨, 적은 답변이 든 옛 글 상자가 회색 사본으로
    남았다. 맨 위 알림과 상자 안 답글 목록을 각각 늘 서 있는 한 칸에 둔다. 시나리오 관리도 같다 — 보관함에서
    「되돌리기」를 누르면 다음 회차 맨 위 알림이 key 있는 보관함 상자를 한 칸 밀어, 옛 자리에 흐린 상자 둘이 모드를
    바꿔도 남았다(2026-10-22 사본 앱 이분 탐색: 알림·상자 key·본문 `st.rerun()` 가운데 하나만 빼도 사라졌다). Components v2 컴포넌트 앞에서는 특히
    그렇다 — 순번이 밀리면 컴포넌트가 다시 마운트되어 브라우저에 둔 상태(배율·서랍)를 잃고 스크롤이 튀므로, 그 앞의
    생겼다 사라지는 상자·경고는 늘 서 있는 `st.container()` 칸 안에 그린다. 표준 목표 결과 상자의 가용대수 누락 경고·
    「누락 공정·주차 확인」(`availability_notice_slot`)과 공용 계층 월 표의 행 페이지 줄(`page_slot`)이 그 예다 — 없을
    때는 표시 항목을 바꾸거나 상세를 켜면 주차·월 표의 가로 스크롤이 처음으로 돌아갔다.
  - 헤더 툴바처럼 React 밖에서 숨은 Streamlit 버튼을 JS 로 눌러 연 대화상자는 포커스가 body 에
    남아 Esc 가 닿지 않는다 — 열리면 포커스를 대화상자 안으로 옮긴다(`page_guide.py`).
  - 월 입력 컴포넌트(`components/month_range_picker.py`)는 칸 값을 초안으로 두고 「적용」·Enter 때만 칸의 지금 값과
    누름을 한 트리거로 보낸다 — 값과 누름을 따로 보내면 키보드로 고친 직후 누른 「적용」이 옛 값으로 닫힌다. 온전하지
    않은 월·범위 밖 월·시작 > 끝은 보내지 않고 단추 옆에 까닭을 적는다. `min`·`max` 는 값이 바뀔 때만 다시 넣는다
    (같은 값이라도 넣으면 Chrome 이 두 자리 월 입력을 끊는다).
- 숨은 탭에서 위젯을 그리지 않으면 Streamlit 이 그 값을 버린다. 본문에 남은 입력 위젯은
  숨은 탭에서도 그리고 계산·표·차트만 건너뛴다. 공용 프로필을 그대로 비추는 상자(HOME `Preference` 의 주요 Case)는
  숨은 회차에 DB 를 읽지 않고 마지막으로 보인 화면 재료로 위젯을 그린다(`home_main_cases`). **조건 카드로 옮긴 위젯**은 열린 탭에서만
  그리므로(사이드바 = 지금 화면의 조건) 반드시 `persist_state` 를 준다 — 그것이 닫힌 동안의
  값을 지킨다(`산출 결과`·`기준 정보`·`생산 계획`).
  - **예외 — 가용설비 현황 탭 ① 「설비 마스터」 는 열린 회차에만 그린다**(개편 B1, 사양 D11). 표 편집은 세션 칸(편집본·출납
    기억)에 살아 숨은 회차에 그릴 까닭이 없고, 탭 모듈이 표 컴포넌트를 등록하므로 열린 회차에만 불러온다. 대가로 버려지는 것:
    작은 편집표 둘의 적용 전 편집(화면 탭 줄 떠나기 확인·탭 점이 `small_editor_edits` 로 알린다 — 같은 화면 안 탭 옮김에는
    묻지 않고 표 아래 한 줄이 「적용 뒤 옮깁니다」 를 말한다), 변경 메모(입력 초안), 저장 칸 체크(기본값이 늘 같다). 저장자는
    `persist_state` 로 지키고 표 고르기·오른쪽 칸 고르기·이력 「조회 리비전」·보기 설정은 `persist_state` 다.
- 위젯 없는 읽기 전용 표·정적 설명만 든 탭은 닫혀 있으면 통째로 건너뛴다(Admin `원천 품질`·Dynamic `산식 가이드`).
  대가는 다시 열 때 표가 새로 마운트되어 정렬·열 너비·스크롤이 처음으로 돌아가고, 여는 회차에 잠깐 빈 패널이 서는
  것이다(합성 표본 130~230ms). 건너뛸 표가 폼·입력 위젯 **위**에 있고 기본 상태에서 보이면 건너뛰지 않는다 — 여는
  회차에 늦게 붙어 입력을 밀어 내린다(설비 마스터 탭(옛 RawData)의 일정 확인 상자를 펴 둔 채 다녀오면 폼이 207px 밀렸다).
- **옵션을 계산 결과에서 얻는 위젯**은 닫힌 탭에서 옵션을 만들 수 없다. 이때 옵션을 빈
  리스트로 두면 위젯을 그려도 선택값이 버려지므로, 계산을 건너뛴 렌더에서는 **현재 선택값을
  그대로 옵션으로 둔다**(공정 필터 `unit_capacity_process_filter` 가 그 방식이다).
- 편집 탭의 분류 필터 상태는 `f"{editor_key}_filter_{column}"` 로 갈린다. 효율과 여유율은
  `dimensions` 가 완전히 같아 이 key 가 유일한 분리 장치다 — 새 편집 탭에 `editor_key` 를
  재사용하지 않는다.
- **`components/month_editor.py` 가 붙여넣기 팝업(`render_reference_clipboard_form`)에 넘기는 첫 인자와
  `key_columns` 는 반드시 필터 이전의 전체 표다.** 필터된 프레임을 넘기면 양식 CSV 가 부분
  표가 되고, 그 부분 표는 `services/reference_csv.py` 의 행 집합 검증을 통과해 조회기간의
  나머지 공정을 지운다. `tests/test_month_editor_filter.py` 가 다운로드 바이트를 실제로
  디코드해 이 계약을 고정한다.
- **가로 컨테이너 안의 제목은 `h1` 의 위아래 여백을 잃는다.** `st.container(horizontal=True)`
  에 `st.title` 을 넣으면 Streamlit 이 `padding: 0` 을 걸어 그 페이지만 제목이 위로
  올라붙고 앱 헤더에 닿는다. 제목 옆에 무언가를 두려면 `st.columns(...)` 를 쓴다 — 컬럼은
  여백을 그대로 둬서 제목 줄 높이가 다른 페이지와 같다. **이때 컬럼에 `wrap=False` 는
  걸지 않는다.** 가로 flex 블록의 `wrap=False` 는 `overflow-x: auto` 를 부르고, CSS 가
  반대 축의 `visible` 을 `auto` 로 올려 제목 줄에 세로 스크롤바를 남긴다. 제목을 한 줄로
  묶는 것은 `st.title(..., wrap=False)` 의 몫이다 (`components/page_header.py`).
- 여러 필터가 같은 결과를 바꾸면 `st.form`으로 묶어 중간 입력마다 전체 재실행하지 않는다. 다만 다른 위젯의 잠금·
  표시를 바꾸는 위젯(확인 체크·보기 설정)과 선택 이벤트를 받는 `st.dataframe(on_select=...)` 은 폼 밖에 둔다 — 폼 안
  에서는 제출 전까지 회차도 선택도 서버에 오지 않아 예외 없이 조용히 실패한다(제출 회차에도 확인을 다시 본다). 그
  선택으로 다른 위젯의 세션 값을 채우면 표를 그 위젯보다 위에 그린다(위젯을 만든 뒤 대입하면 `StreamlitAPIException`).
- `use_container_width`를 새로 사용하지 말고 `width="stretch"` 또는
  `width="content"`를 사용한다.
- 단순 UI 그룹은 네이티브 `st.container(border=True)`를 우선한다.
- 복잡한 Plotly UI를 변경할 때는 월별 고정 열 너비, 좌측 라벨 Figure, 공통 가로
  스크롤 정렬을 함께 검증한다.
- **paper 좌표는 픽셀에서 낸다.** Plotly 의 paper `y` 는 여백을 뺀 **그림 영역** 기준이라
  `-0.28` 같은 비율을 손으로 적어 두면 행 높이를 한 번 올릴 때마다 같은 비율이 다른
  자리를 가리킨다. 캔버스 밖으로 밀린 테두리는 오류 없이 잘려 사라진다 — LOB 패널 아래
  테두리가 그렇게 사라졌다. `LOB_PANEL_BOTTOM_Y` 처럼 여백·높이 상수에서 계산한다.
- HOME Plotly shape·annotation을 반복해서 추가하지 않는다. 레이아웃에 일괄 주입해
  Figure 생성 시간이 선형에 가깝게 유지되도록 한다. 칸마다 반복되는 값은 shape·
  annotation 이 아니라 배열 `text`·`customdata` 를 실은 trace 하나로 그린다. 격자 선·shape 는
  `plotly_layout.append_layout_items` 에 모아 `flush_layout_items` 한 번으로 반영하고, `figure_from_spec` 에 넘기는
  spec 은 검증 없이 세우므로 Plotly 정규형(`{"fill": {"color": …}}` 같은 중첩 dict)으로 쓴다 — 밑줄 줄임 키
  (`fill_color`)는 검증 생성자로 넘어가 느려진다(`tests/test_plotly_fast_path.py`).
- hover 가 필요한 Figure 만 `staticPlot` 을 끄고 같은 캔버스의 다른 Figure 설정은
  건드리지 않는다. 끄면 `displayModeBar`·`doubleClick`·`showAxisDragHandles` 가
  기본값으로 돌아가므로 셋을 직접 끄고, 드래그 확대는 축 양쪽 `fixedrange` 로 막는다.
  그 세 키는 `components/plotly_layout.hover_chart_config()` 가 돌려주고, 조작이 아예 없는
  그림은 `static_chart_config()` 를 쓴다.
- 칸마다 표적을 둔 그림에서 **풍선이 없어야 할 칸**은 빈 글을 `hovertemplate` 에 넣지 않는다 — 빈 상자(16px)가
  뜬다. `hoverinfo: "none"`·`hovertemplate` 없는 trace 로 가른다(누름은 그대로다). 한 trace 안의 점별 `hoverinfo`
  (`"none"`·`"skip"`)는 `hovertemplate` 에 진다(`month_sheet_canvas` — 2026-10-24 브라우저 확인).
- **칸 선택(`on_select`)을 켠 Plotly 그림**은 모든 trace 에 `unselected` 불투명도 1 을 주고
  (`home_figure_common.keep_unselected_opaque`) 차트 key 를 `app.py` 의 `CELL_SELECT_CHART_KEYS` 에 더한다 — Streamlit 이
  `dragmode=False` 를 `pan` 으로 덮어 그 위 터치 스크롤이 막히므로 `components/plotly_touch_scroll.py` 가 그 묶음만 풀어
  준다. `go.Table`·`go.Heatmap` 은 점 선택이 없어 칸은 `base` 막대 + 표적 막대(`HIT_TARGET`)로 그린다. 그런 그림은 HOME 두
  월 그림·공정 Capa 상세 결합 캔버스·가용설비 비교 시트·제약 시뮬레이션 그래프와 계산표(`constraint_simulation_state` 의
  key 둘 — 앱 진입점이 컴포넌트를 부르지 않게 상태 모듈에 둔다)다. **두 그림이 한 「고른 달」 을 나눠 쓰면** 회차마다 두
  그림의 선택 상태를 읽지 말고 `on_select` 콜백이 그 칸을 적는다 — 브라우저에 남은 다른 그림의 옛 선택이 마지막 누름을 덮는다.
  세대 번호도 한 칸을 나눠 써 어느 쪽을 눌러도 두 그림이 함께 새 요소가 된다(제약 시뮬레이션).
- Streamlit 1.63 의 키 붙은 `plotly_chart` 도 요소 id 를 그림 spec 으로 만든다 — 고른 칸 테두리로 그림이 바뀌면 새 요소가
  되어 같은 칸을 다시 눌러도 빈 선택이 아니라 같은 점이 오고, 같은 그림으로 돌아오면 브라우저에 남은 선택이 첫 클릭을
  삼킨다. 누를 때마다 세대 번호를 그림 `layout.meta` 에 실어 늘 새 요소로 만든다(`availability_gap_panel`).
- 「26.07」 같은 월 라벨을 Plotly 축에 쓰면 축을 범주로 둔다 — 숫자로 읽혀 실수 축에 눌려 붙는다.

### 사이드바·조건 카드·본문

- **사이드바 = 보는 조건.** 사이드바 「조회 조건」은 지금 화면이 실제로 읽는 조건만 모으는 한 곳이다. 화면 고유의 거르는
  조건은 조건 카드(`sidebar_status.condition_card`·`table_card`)에 두고, 탭에 딸린 카드는 그 탭이 열렸을 때만(한 회차에
  카드 하나) 기본 접힘으로 선다(예외 하나 — HOME `LOB 표시 조건` 은 계산이 멈춘 회차에도 선다, 3장 `home.py`). 쓰기
  작업(붙여넣기·등록)은 카드에 넣지 않고 표 위 작업 줄의 버튼·팝업으로 둔다. 본문에는 결과·그에 대한 행동·상태 알림만
  남기고 설명은 Guide 로 옮긴다(8장).
- **하위 보기 전환은 본문이다.** 탭 안에서 무엇을 볼지 고르는 전환(보기·표현·표시 방식·표시 항목)은 하위 탭과 같은 것이라
  본문에 두고, 카드에는 거르는 조건(공정·기간·기준일·분류·호기 필터)만 둔다. 행을 펼치는 「상세」 토글은 카드 자리이고,
  공정 Capa 상세의 「제품별 소요대수」·「분류」·「구획」(①~④ 접기, 2026-10-22 「소요대수처럼」)만 사용자 요청에 따른
  예외로 본문 표 도구 줄이다. Space 「필요 단축」 보기의 목표 확보율·「단축 없는 호기 흐리게」 도 이 규칙대로 도면 위 본문 조작
  줄이다(2026-10-24 결정 D6 — 「색 기준」 라디오만 사이드바 카드).
- **계산 가정 칸(세션 전용)은 조건 카드 끝 「이 세션만」 묶음이다** — 거르는 조건이 아니지만 계산 입력이라 카드에 둔다
  (예외). UPEH 가정이 그렇다(2026-10-22). 묶음 앞에 `:material/person:` 「이 세션만」 캡션을 두어 카드 머리의 「공용 설정」
  안내와 가르고, 켜진 동안은 카드가 접혀 있어도 보이게 머리 배지·효과 한 줄·CSV 표지로 알린다. 제약 시뮬레이션의
  확보율·개조 묶음도 이 꼴이다(조건 전체가 저장하지 않는 가정이라 머리 한 줄이 늘 조건을 말한다).
- **버튼 + 직접 입력은 정본 한 칸 + 매 회차 다시 서는 위젯 둘이다**(`components/preset_number_field.py`). 정본은 위젯 아닌
  세션 칸이고 버튼(`st.pills`, `required=True` — 고른 버튼을 다시 눌러도 풀리지 않는다)·숫자 칸 key 는 위젯 앞에서 정본에서
  내되 **다를 때만** 적는다. 콜백이 정본을 적고, 버튼 콜백은 숫자 칸을 새 key 로 다시 세운다(범위 밖 글을 쥔 칸은 서버
  값을 무시한다). 친 글의 확정과 버튼 누름이 한 회차에 겹치면 버튼이 이긴다(옛 세대 key 의 숫자 칸 콜백은 적지 않는다). 「맞춤 값일 때만 보이는 빈 글자 칸」 은 `value=None` 과 세션 심기를 함께
  써야 해 두지 않는다 — 숫자 칸은 늘 지금 값을 보인다(D10).
- **공통 줄은 그 화면이 읽을 때만 선다.** 새 화면은 `navigation.PageSpec` 의 `reads_scenario`·`reads_period`(일부 탭만
  읽으면 `condition_tabs`)에 코드가 실제로 읽는 것을 선언하고 `app.py` 가 그대로 따른다. 세우지 않은 줄의 값은 세션에
  그대로 남는다. `ConditionTabs` 는 탭 말고 **보기 값**으로도 가른다 — Space 현황은 색 기준 라디오(`space_color_basis`)가
  `필요 단축` 일 때만 시나리오·조회기간 줄이 선다(2026-10-24 결정 D4 — 그 보기만 시뮬레이션을 읽는다). 링크로 도착한 회차는
  페이지가 그 값을 적고 한 번 더 돌아 사이드바를 맞춘다. 호기가 없는 화면(설비 저장본 없음 + 샘플 끔 — 색 기준 라디오가 서지
  않는다)에 그 값이 남아 있으면 페이지가 기본 값으로 적고 회차 끝에 한 번 더 돌아 줄을 걷는다(끌 길이 없는 줄을 남기지 않는다).
  **한계**: 배치 편집 중(보기가 쉬는 회차)에도 줄은 선다 — `app.py` 는 페이지보다 먼저 그려 편집 가능 여부(설비 DB·편집 권한)를
  모르고, 편집을 끄면 그 값으로 바로 다시 읽으므로 그대로 둔다(줄의 값은 편집 뒤 보기가 쓴다).
- **설비 시나리오 줄은 페이지가 그린다.** `PageSpec.equipment_scenario`(`"session"` — 가용설비 현황·필요 단축 일정·공정 Capa
  상세·제약 시뮬레이션·Space 현황)와 `equipment_scenario_tabs`(설비 데이터를 읽지 않는 탭이 있는 화면만 — 지금은 없다)를 선언하면
  `app.py` 조건 패널이 「적용 전 편집 → 시나리오 → 조회기간 → **설비 시나리오 칸** → 페이지 칸」 차례로 빈 블록 칸
  (`sidebar_status` 에 등록 · 꺼내기 함수)을 세우고, 페이지가 `resolve_equipment_session` 뒤에 그 칸에 줄을 그린다 — 부트스트랩
  오류는 페이지의 오류 처리 안에서 나고, 배지는 그 회차 목록으로 맞으며(한 회차 늦지 않음), `app.py` 는 설비 DB 를 읽지 않는다.
  값 칸 단추는 위젯 상태가 없고 값은 세션 칸에만 있어 페이지가 그려도 화면 사이에 잃을 것이 없다. 팝업은
  `render_condition_dialogs` 의 셋째 갈래다(한 실행에 팝업 하나).
- **머리 띠 끝 「설비 시나리오 · …」** 은 설비 시나리오를 선언한 화면의 아랫줄 끝에 선다(Space 도 같은 꼬리 — S3). 머리 띠는
  `app.py` 가 페이지보다 먼저 그리므로 라벨 칸만으로는 한 회차 늦다 — 그래서 **설비 화면에서는 페이지가 회차마다 머리 띠를 한
  번 더 보낸다**(`refresh_equipment_header` — 같은 글이어도. 바뀐 회차에만 보내면 이벤트 칸 자리가 회차마다 밀려 그 뒤 알림 칸
  시험이 깨진다. 같은 글은 메시지 캐시로 해시만 간다). 페이지는 그 꼬리를 페이지 몫으로 세션 칸(`app_header_equipment_label_v1`
  — 페이지 스크립트 해시째)에 남기고, `app.py` 는 다음 회차에 그 글로 먼저 그려 둔다(다른 페이지의 꼬리는 읽지 않는다).
  1280px 보다 좁은 창에서는 아랫줄을 꼬리 먼저로 바꿔 적는다(`_header_css(narrow_bottom=)` 의 미디어 규칙) — 끝에 두면 말줄임이
  꼬리를 통째로 지운다(사이드바를 연 900px 창 자리 355px · 꼬리 포함 필요 526px — 2026-10-24 E2E).
- **여닫을 때 본문을 다시 돌리지 않는다.** 사이드바 상자 전부(페이지 그룹·`sidebar_expander`·조건 카드)의 `on_change` 는
  `sidebar_status.on_box_toggle` 이다 — 기억 칸을 적고 `app.py` 맨 위의 빈 프래그먼트(`SIDEBAR_TOGGLE_FRAGMENT_KEY`)만
  다시 돌린다. 같은 페이지의 끝까지 돈 실행 뒤(`begin_app_run` 의 `AppRun` 표지)이고 다른 위젯이 함께 바뀌지 않았을
  때만 그렇게 하고(`fragment_rerun_is_safe`), 아니면 앱 전체를 다시 돌린다.
- 회차마다 페이지가 다시 채우는 자리표시자(사이드바 페이지 칸 등)는 `st.empty` 가 아니라 `st.container` 로 둔다 —
  `st.empty` 칸은 회차가 시작되자마자 앞 회차 내용을 지워 계산 동안 화면이 튀고, 블록은 페이지가 다시 보낼 때까지 앞
  내용을 남긴다. 빈 컨테이너는 그려지지 않아 높이가 없으므로 그런 칸에 `border`·`height` 를 주지 않는다.
  `tests/test_page_placeholder_slots.py` 가 `app_pages/` 의 `<이름> = st.empty()` 대입을 막는다 — 조건이 맞을 때만
  채워 회차 시작에 비워야 하는 알림 자리만 그 허용 목록에 둔다.
- `with` 컨테이너 안에서는 평범한 `st.*` 로 그린다 — `st.sidebar.*` 는 `with` 를 따르지 않아 요소가 컨테이너 밖으로 샌다.
- 탭 이름 앞에는 탭이 하는 일을 말하는 `:material/…:` 아이콘을 달고, 적용하지 않은 편집이 남은 탭의 주황 점은 라벨이
  아니라 CSS 로 찍는다(`components/tab_marks.py`) — 라벨은 `st.tabs` 위젯 id 에 들어가 붙였다 떼면 열린 탭 기억이
  흔들린다. 탭 묶음은 `tabs[N]` 이 아니라 이름 붙은 변수로 받는다(위치 언패킹이면 `TAB_NAMES` 와 함께 고친다) — 순서를
  바꿀 때 하나를 놓쳐도 예외 없이 표가 다른 탭에 그려진다.
- **CSS 로 고르는 컨테이너 key 는 계약이다.** key 는 `.st-key-<key>` 클래스가 되므로 이름을 바꾸면 CSS 도 함께 고친다.
  클래스는 영문·숫자 밖을 `-` 로 바꿔 한글 key 끼리 겹칠 수 있으므로, 공정명 같은 값을 넣은 key 를 CSS 로 고르지 않고
  순번 칸(`home_bn_tile_<i>`)으로 감싼다.
- 세션 키 리터럴은 그것을 쓰는 페이지가 소유하고, 공용 헬퍼(`page_bootstrap.prune_choice`·`prune_list_selection`,
  `scenario_edit_bar` 의 원본 토큰 키)는 키를 인자로 받는다.

### 프래그먼트·이벤트 칸·토스트

- **본문 프래그먼트.** 조건 카드에 설 위젯을 바꾸지 않는 본문 조작만 `st.fragment` 로 좁혀 앱 전체 회차의 고정비(DB 핀·
  저장본 사본·계산 확인·다른 탭)를 지나지 않게 한다. 카드에 무엇이 설지 정하는 전환은 앱 전체 회차로 둔다. 프래그먼트
  회차는 직전 앱 전체 회차의 인자(오늘 날짜·공정 표시명·Cut-off·계획·고른 조건)를 그대로 쓰므로 다른 세션의 변경은 다음
  앱 전체 회차에 보인다. AppTest 는 프래그먼트 회차도 앱 전체로 돌리므로 `tests/fragment_browser.py` 대역과 실제
  브라우저로 잰다.
- 프래그먼트 안 위젯의 콜백은 `rerun_fragment_if_alone` 이 아니라 `sidebar_status.rerun_app_unless_alone` 을 부른다
  (판정이 거짓일 때만 앱 전체로 올린다). 저장·불러오기·「적용」처럼 앱 전체 재실행으로 끝날 수 있는 프래그먼트 본문은
  `sidebar_status.keeps_app_run_open` 으로 감싸고 그 데코레이터는 `@st.fragment` 안쪽에 둔다.
- **프래그먼트 회차는 `app.py` 머리를 지나지 않고 새 스레드에서 돈다** — 스레드에 담은 값(테마)은 비어 있다. 회차
  머리에서 정하는 값은 세션에도 적고 프래그먼트 회차는 세션에서 잇는다(`design/theme.py`). 같은 까닭으로 세션마다 다른
  값(테마·조건 패널 칸·자리표시자)을 모듈 전역에 두지 않는다 — 세션마다 다른 스레드에서 도는 스크립트가 동시에 그 값을
  바꾼다. 실행 단위 값은 스레드 칸, 세션 단위 값은 `st.session_state` 에 둔다.
- **본문 프래그먼트·팝업 본문은 이벤트 칸에 갈래와 상관없이 같은 수만 쓴다.** 스타일만 든 `st.html`·`st.toast`·
  `st.dialog` 는 본문 밖 이벤트 칸으로 가고, 프래그먼트 회차는 그 쓰기 위치를 프래그먼트를 부른 자리로 되돌려 받은
  자리만 갈아 끼우므로 더 쓰면 뒤 페이지 요소를 덮고 덜 쓰면 낡은 요소가 남는다. 서식은 표시 HTML 과 한 `st.html` 에
  실어 본문 칸으로 보내고, 꼭 이벤트 칸에 써야 하면 빈 `st.html("<style></style>")` 로 수를 맞춘다(조건 팝업 호스트는
  어느 갈래든 정확히 한 자리).
- **토스트는 자리가 곧 이름이다.** Streamlit 1.63 은 토스트를 쓴 자리(`delta_path`)로 가려 같은 자리의 토스트가 떠
  있으면 새 토스트를 띄우지 않고, 이벤트 칸 요소를 지울 때 토스트만 남겨 앞 자리가 비면 뒤 토스트가 당겨져 다시 뜬다.
  잇단 알림을 내는 곳은 알림 자리를 여럿 늘 같은 수로 두고(`components/shortening_progress_panel.py`) 첫 자리 토스트가
  떠 있을 때만 다음 자리로 비키며, 그 프래그먼트를 그리지 않는 앱 전체 회차에도 같은 자리를 채운다. 콜백이 남기는 알림은
  덮어쓰지 않고 쌓는다.

### 팝업과 콜백

- **세션 키로 여는 팝업.** 한 실행에 팝업은 하나뿐이다 — 둘이면 `StreamlitInvalidLayoutContextError`. 그래서 팝업
  (`st.dialog`) 열림 상태는 페이지에 한 칸(`<페이지>_open_dialog`, `page_bootstrap.PAGE_DIALOG_SUFFIX`)만 두고 열림 키가
  있는 동안 매 회차 그 함수를 부른다(탭은 닫혀도 매 회차 그리므로 탭마다 칸을 두면 둘이 뜰 수 있다). 여는 버튼은
  `on_click` 콜백이고 콜백마다 `forget_page_dialogs()` 로 다른 열림 키부터 비운다. 페이지가 바뀐 회차에는 `app.py` 가
  열림 키를 버린다. 시나리오 관리 공식 지정 확인 팝업(`scenario_official_open_dialog`)은 팝업이 보인 「지금 공식」 번호를
  저장소에 넘겨(`expected_latest_release_no`) 팝업이 열린 사이 남이 먼저 지정했으면 쓰지 않는다 — 팝업 안 조작은
  프래그먼트 회차라 마지막 전체 회차에 읽어 보인 값이 그대로 인자다.
- 팝업 닫기는 `on_dismiss` 가 맡는다. 팝업 안 저장·삭제가 성공하면 열림 키를 직접 지우고 `st.rerun()` 으로 앱 전체를
  다시 돌린다 — 팝업은 프래그먼트라 그대로 두면 바깥 화면이 옛 값이고, `st.rerun()` 은 `on_dismiss` 를 거치지 않는다.
  예외 하나 — 가용설비 현황 「설정」 팝업(공정별 Cut-off, `equipment_settings_dialog`)은 저장·「설비 공정으로 채우기」 뒤에도
  열림 키를 남긴다. 앱 범위 `st.rerun()` 이라 바깥 화면(Static 대비 일정)도 그 회차에 새 Cut-off 로 다시 그려지고, 저장 결과
  (flash)가 누른 단추 바로 아래에 선다 — 닫으면 그 결과를 볼 자리가 「설정」 단추 옆밖에 없다. 그 팝업 안 편집표의 제출 전
  편집은 닫으면 사라진다(Guide 「닫기 전에 저장합니다」).
- **세션 상태를 바꾸는 조작은 콜백(`on_click`·`on_change`·컴포넌트 `on_*_change`)으로 한다.** 콜백은 본문보다 먼저 돌아
  재실행이 한 번이고, 본문에서 바꾸고 `st.rerun()` 하면 한 번 누를 때 화면이 두 번 돌며 그 회차에 아직 그리지 않은
  위젯의 상태를 버린다(팝업 본문 프래그먼트의 저장 성공 처리는 바로 위의 예외다).
- **쓰기 콜백은 빠른 두 번 누름을 거른다.** Streamlit 1.63 은 지나간 위젯의 콜백 정보를 지우지 않아 옛 화면의 누름도
  콜백에 닿는다. 공용 기록을 쓰는 단추는 그린 회차의 key 세대를 콜백 인자로 받아 지금 세대와 다르면 쓰지도 알리지도
  않고, 폼·팝오버 key 에도 같은 세대를 붙인다(같은 key 면 옛 누름이 새 폼의 인자로 콜백된다).
  - 세션 칸 비교만으로는 **겹쳐 오는** 두 누름을 막지 못한다. 브라우저 더블클릭은 둘째 누름이 닿는 순간
    `runner.fastReruns`(기본 켜짐)가 돌던 회차에 멈춤을 걸고 새 회차를 세워, 두 콜백이 다른 스레드에서 수 ms 차이로 같은
    세대를 보고 둘 다 쓴다 — 세션 칸 잠금(`SafeSessionState`)이 회차마다 따로다. 멈춤을 받은 첫 콜백은 쓴 뒤 다음 세션 칸
    접근에서 `StopException` 으로 끊겨 세대도 못 올린다(2026-10-25 E2E, VOC 글·답변 두 건). 그래서 비교와 쓰기는
    `components/write_guard.write_once` 가 프로세스 잠금 안에서 하고, 「이 세대는 썼다」 는 끊기지 않는 세션 dict 표지에
    적는다. 입력은 부르기 전에 읽고(세션 칸 접근도 끊기는 자리다) 세대 올리기는 뒷정리의 맨 끝에 둔다. 시험은 둘째 회차를
    다른 스레드의 `app._run` 으로 세운다(`tests/test_voc_page.py` 의 `_race`).
  - **느린** 두 번 누름(0.15~0.3초)은 둘째 누름이 첫 쓰기 뒤 새로 그린 **빈** 폼의 단추에 닿아 세대가 같다 — 정상 제출로
    보면 빈 입력 거절(「제목을 입력하세요.」)이 방금 성공한 자리에 남았다(2026-10-26 E2E). `write_once` 는 쓴 시각도 적고,
    입력이 모두 빈 제출이 `write_guard.TRAILING_PRESS_SECONDS`(1초) 안에 오면(`just_written`) 쓰지 않고 방금 성공을 다시
    알린다. 적은 것이 하나라도 있거나 창이 지나면 정상 제출이다(VOC 새 글·답변, `tests/test_voc_page.py`).
  - 본문에서 저장하고 `st.rerun()` 하는 **버전 대조 저장**(Proc Rename 직접 편집·판정 기준·확보율 보정)은 둘째 누름의
    회차가 rerun 회차를 끊으면 편집 시작 version 이 저장 전 그대로라 저장소가 거부하고, 방금 한 제 저장을 「다른 사용자가
    먼저 저장」이라 알렸다(2026-10-26 E2E). 저장 전에 `write_guard.profile_save_marks()` 로 받은 dict 에 성공한
    `(편집 시작, 저장된)` version 짝을 적고, `ProfileVersionConflict` 의 `expected`·`stored` 가 그 짝이면
    (`is_own_profile_save`) 거부 대신 저장 성공을 다시 알린다. 그 사이 남이 저장했으면 지금 version 이 짝과 달라 거부를
    그대로 알린다(`tests/test_threshold_editor.py`·`tests/test_execution_capacity.py`·`tests/test_admin_area_page.py`).
  - 거꾸로 **남의 저장에 거부된** 누름의 둘째 누름 — 거부한 회차는 최신 저장본을 그리며 편집 시작 version 을 그
    version 으로 올리거나(판정 기준·자동 갱신 설정) 지운다(Proc Rename·확보율 보정). 사용자가 새 화면을 보기 전에 닿은
    둘째 누름이 옛 화면의 입력을 든 채 그 version 으로 대조를 지나, 거부 알림이 「저장했습니다」로 바뀌고 입력은 말없이
    버려지거나 남의 새 저장을 덮었다(2026-10-26 E2E). 저장 전에 `write_guard.profile_conflict_marks()` 로 받은 dict 에
    거부 알림과 시각을 곧바로 적고(`note_profile_conflict`), `TRAILING_PRESS_SECONDS` 안의 다음 제출은 저장하지 않고 그
    거부를 다시 알린다(`held_profile_conflict`). 창이 지나면 새 화면을 보고 다시 누른 저장이라 평소대로 대조한다 —
    거부 뒤 곧바로 다시 누르는 AppTest 는 창을 0 으로 둔다(위 세 시험·`tests/test_auto_official_update_tab.py`).
  - **아주 빠른** 두 번 누름(0.05~0.15초)은 둘째 누름이 아직 옛 화면의 단추에 닿아 그 회차가 쓰지 않고 끝난다(지나간
    세대·이미 지운 글·고칠 대상이 바뀌어 잠긴 단추 — 잠긴 단추의 누름은 Streamlit 이 버린다). 첫 쓰기의 성공 알림은 앞
    회차가 이미 꺼내 그렸으므로 그 회차가 화면을 다시 그리며 알림을 지워, 한 건 쓰였는데 아무 알림도 남지 않았다
    (2026-10-26 E2E — VOC 글 올리기·Preference 프리셋 삭제). 세대 쓰기는 지나간 세대의 누름이 `just_written` 창 안이면
    성공을 다시 알리고(VOC 새 글·답변), 세대가 없는 쓰기는 쓰기 전에 받은 `write_guard.notice_marks()` dict 에 알림과
    시각을 적어(`note_notice`) 그 창 안의 회차가 `held_notice` 로 다시 그린다(VOC 글 삭제·HOME 주요공정 프리셋
    「기본으로」·「삭제」). 다시 그리기는 `flash.render_flash` 한 길이라 알림을 적는 칸이면 어디든 받는다 — 칸마다
    `held_notice` 를 따로 부르지 않는다(VOC 머리 칸도 `render_flash` 칸이다). 창이 지난 옛 화면의 누름은
    전처럼 알리지 않는다(`tests/test_voc_page.py`·`tests/test_key_process_preset_messages.py`·
    `tests/test_flash_messages.py` 의 끊긴 회차 시험).
- **저장 성공 문구는 flash 로 낸다.** `st.success(...)` 바로 뒤의 `st.rerun()` 은 그 문구를 한 번도 그리지 않는다.
  `components/flash.py` 로 세션에 담아 다음 회차에 그 버튼과 같은 상자 안에 그린다 — 실패도 그 자리에 떠 성공과 실패가
  같은 자리에서 답한다(`tests/test_flash_messages.py` 의 AST 그물이 같은 함정을 소스에서 찾는다).
- **공용 프로필을 기본값으로 심는 조회 위젯**은 세션에 값이 없을 때만 심고(`index=`·`default=` 없이) 프로필 저장은 그
  위젯의 `on_change` 에서, 값이 실제로 바뀐 때만 한다. 심기·가지치기·조회기간 변경으로 옮긴 값을 쓰면 공용 행이라 남이
  고른 값을 되쓰고(핑퐁), 선택지 밖 글자(브라우저가 되보낸 옛 라벨)가 섞인 콜백 값은 쓰지 않는다.
- 활성 리비전을 씨앗으로 쓰는 위젯은 「무엇으로 씨앗을 넣었나」를 함께 적어 두고 활성 리비전이 바뀌면 다시 적는다
  (`components/scenario_management.py` 의 `REVISION_SEED_KEY` — 리비전 표의 고름을 `repick_table` 로 옮긴다,
  `components/scenario_transform.py` 의 원본 리비전 상자) — 칸이 없을 때만 넣으면 사이드바 팝업에서 불러온 뒤에도 옛
  리비전을 고른 채 남아 다음 동작이 엉뚱한 리비전에 걸린다. 선택 상자라면 씨앗 처리 뒤에도 **매 회차** 고른 id 를
  되쓴다 — 선택지 글자의 리비전명이 바뀔 수 있다(위 「글자가 바뀌는 것을 피할 수 없는 상자」).
- `st.query_params` 는 자기 키만 넣고 `del` 한다. `st.query_params.clear()` 는 쓰지 않는다 — 테마 인자
  (`design/theme.THEME_QUERY_PARAM`)까지 지워 첫 방문으로 보고 다시 새로고침한다. 키 둘 이상을 지울 때는 `del` 을 되풀이하지
  않고 남길 인자를 `get_all` 로 다시 실어 `st.query_params.from_dict` 한 번으로 바꾼다 — 1.63 은 바꿀 때마다 주소 메시지를
  보내고 브라우저는 메시지마다 기록을 하나씩 쌓아, 뒤로를 눌러도 같은 화면이 키 수만큼 이어진다
  (`process_detail_state.resolve_process_and_month`). `st.switch_page(…, query_params=…)` 는
  주소를 통째로 바꾸므로 지금 테마 인자를 함께 싣는다. `st.switch_page` 는 위젯 콜백이 아니라 회차 본문에서 부른다 — 1.63 은
  끝에 `st.empty()` 를 그려, 프래그먼트 안 위젯의 콜백에서 부르면 「A fragment rerun was triggered with a callback that
  displays one or more elements」 경고를 남긴다. 콜백은 대기 칸만 적고 프래그먼트 본문 첫 줄이 옮긴다
  (`process_detail_state.switch_to_queued_process_detail`). 화면 탭 줄도 같다 — 트리거 콜백은 목록·대기 칸만 적고
  `app.py` 의 `st.navigation()` 바로 뒤 본문이 옮긴다(`page_tabs_state.switch_to_queued_tab`). AppTest 에는 등록된 페이지가
  없어 `st.switch_page` 대역으로 시험한다(이동이 콜백 밖인지는 `tests/fragment_browser.py` 로 본다). `app.py` 를 연
  AppTest 는 진짜로 옮기지만 회차 안의 이동을 다음 `run()` 의 화면으로 기억하지 않는다(`tests/test_page_tabs.py`).
  다른 화면으로 옮기는 도우미는 전달 칸을 적고 `st.switch_page` 하기 **전에** `page_tabs_state.refused_at_tab_limit(대상)`
  을 부른다 — 화면 탭 10개에서 그 화면 탭이 없으면 알림을 남기고 앱 전체를 다시 돌린다. 옮긴 뒤 되돌리면 브라우저 기록에
  두 화면이 쌓여 뒤로가기가 갇힌다(3장 `page_tabs_state.py`). **값이 남는 위젯**(그림 선택 등)의 콜백이 이동을 청하면 그
  거름은 본문이 아니라 **콜백 안에서** 한다(`process_detail_state.queue_home_cell`) — 본문의 `st.rerun()` 은 그 위젯을 다시
  그리기 전에 회차를 끊어 Streamlit 이 값을 「그리지 않은 위젯」으로 걷는데, 브라우저는 값을 들고 있다가 다음 조작마다 되보내
  콜백이 「바뀐 값」으로 다시 불린다(거절한 HOME 칸이 탭 하나를 닫는 순간 열렸다). 콜백 안의 `st.rerun()` 은 본문 전에 끊어
  위젯 값을 걷지 않는다. 단추(트리거)는 값이 남지 않아 본문 거름으로 된다.

### 편집표와 내려받기

- **표 도구 막대는 표 위로 솟는다.** `st.dataframe`·`st.data_editor` 에 마우스를 올리면 오른쪽 위에 도구 막대(열 보기·
  내려받기·찾기·전체 화면, 1500px 창에서 92×41px)가 표 머리 위 37px 까지 떠, 표에 바로 붙은 위 줄 오른쪽 끝의 단추·팝오버를
  덮고 표에서 그 단추로 옮긴 누름을 가로챈다(2026-10-25 E2E — 설비 시나리오 구획 「시나리오 이름 바꾸기」). 표 바로 위 줄
  오른쪽 끝에 누를 것을 두면 표 앞에 띄움(`st.space`, 막대가 그 줄에 닿지 않을 만큼 — 설비 시나리오 구획은 24px)을 둔다.
  띄움은 `table_toolbar.toolbar_clearance()`(`TABLE_TOOLBAR_CLEARANCE` 24px — 숫자는 이 하나, 설비 시나리오
  `REVISION_TABLE_TOOLBAR_CLEARANCE`·Qual 계산기 `EDITOR_TOOLBAR_CLEARANCE_PX` 는 그 별칭)로 둔다 — Space 층 목록 머리의
  `사용 편집` 토글·층 상세 표 머리의 「층 전체 보기」 가 그 자리다(2026-10-26 E2E). 날짜 칸의 지우기(✕)도 같다 — Qual
  마감 계산기 월 편집표 앞 띄움(터치 창은 막대가 늘 떠 있어 띄움이 없으면 「오늘」 칸을 ✕ 로 지울 수 없다). 오른쪽 끝까지
  늘어나는 입력 칸(Admin 공용 표시순서·Proc Rename 의 「변경 메모」)과 바로 위 CSV 단추(Cut-off 잠긴 보기·제외 목록)도
  같은 띄움을 둔다. `tests/test_table_toolbar.py` 가 `st.dataframe`·`st.data_editor` 문장의 바로 앞 형제(그리지 않는
  대입은 건너뛴다)가 입력·단추·팝오버·토글·날짜 칸을 품으면 띄움을 요구하고, 띄움 숫자 정의가 이 모듈 하나인지 본다.
- **키가 있는 모든 편집표는 `editor_state.editor_widget_key(키)` 로 그리고, 버릴 때 세션을 `pop` 하지 않고
  `discard_editor` 를 부른다** — 세션 칸만 지우면 브라우저가 옛 편집을 다음 회차에 되보내 취소한 편집이 되살아난다. 원본을
  갈아 끼울 때(Import 저장·편집 버퍼 교체)도 같다 — 옛 delta 가 새 프레임에 얹혀 Import 가 조용히 되돌려진다. 「변경사항
  적용」은 고친 것이 있을 때만 연다(같은 값 적용도 리비전을 올려 `미저장 변경` 을 켠다).
- **`st.data_editor` 의 편집은 행 위치로 기록된다.** 보이는 행 집합이 바뀌면 남은 편집이 다른 행에 붙으므로, 적용하지
  않은 편집이 있으면 필터를 잠그고, 필터 선택이 바뀌면 편집표를 만들기 전에 편집을 버려(key 세대를 올려) 새 위젯으로
  세운다(처음 그리는 회차는 올리지 않는다). 필터는 보기만 좁힌다 — 편집기가 돌려주는 표는 원본과 행 수·순서가 같은 전체
  표다(`merge_edited_months` 되머지). `editor_key` 에는 필터를 섞지 않는다 — `reset_editors_on_source_change`·
  `register_pending_edits` 가 고정 키 목록으로 편집표를 찾으므로 키가 바뀌면 청소와 「적용 전 편집」 표시가 그 편집을
  놓친다.
- **공용 표시순서로 줄을 세우는 편집표는 원본 토큰에 그 지문을 싣는다**(`scenario_edit_bar.source_token(...,
  row_order=display_order_digest(...))`). 차례가 바뀐 회차에는 줄 위치로 남는 적용 전 편집을 비우고 탭 묶음 위에 늘 서 있는
  알림 칸에 한 번 알린다 — 틀린 줄에 저장하는 대신 적용 전 편집만 잃는다. 제 줄 차례를 들고 있는 붙여넣기 대기 표·그 표를
  원본으로 그린 편집표·키로 고르는 상자는 `order_free_keys` 로 남긴다(버릴 까닭이 없다). 그 회차에 함께 온 「적용」 클릭은
  따로 막지 않는다 — 단추를 `disabled=not pending` 으로 그리면 Streamlit 1.63 이 잠겨 그린 위젯의 값을 서버에서 버린다
  (`tests/test_editor_row_order_guard.py` 가 그 전제를 지킨다).
- **뜻이 걸리는 `NumberColumn` 에 `step` 을 두지 않는다.** Streamlit 1.63 은 `step` 의 소수 자릿수 아래를 반올림하지 않고
  **버린다**(보이는 값·칸 복사·손 입력·칸 붙여넣기 — 0.001 이면 98.75% 가 98.7%, 0.01 이면 0.333 대가 0.33). `format` 만 두면
  보이는 자리만 반올림하고 값은 적은 그대로다(`percent` 는 소수 0~2자리). `step` 이 없으면 **정수 dtype 칸에 증분 1 이 스스로
  걸리므로** 정수로 올 수 있는 표는 실수로 바꿔 그린다(`month_editor.float_month_columns`). 그 단위로 충분한 칸(일수 1일·
  Cut-off·PKG PLAN 등)만 `step` 을 둔다.
- **키가 있는 `num_rows="fixed"` 편집표의 정체는 키 + 데이터 서명이다**(Streamlit 1.63 — 칸 이름·Arrow 타입·data kind·
  행 수·잠근 칸). 값만 바뀌면 같은 위젯이라 남은 칸 편집·스크롤·초점이 그대로이고, 서명이 바뀌면 새 위젯이 서서 셋 다
  사라진다. None 만 든 칸은 Arrow `null` 이라 첫 값이 들어오는 회차에 `string` 으로 바뀐다 — 비거나 찰 수 있는 글 칸은
  `astype("string")` 으로 고정한다(`space_floor_list._render_editor` 의 `사유`). 칸 편집을 초안에 접고 접은 초안을 다시
  그리는 표는 다시 세울지를 「접은 값을 그린 위에 남은 편집을 얹어 보일 값」 이 접은 값과 다를 때만 정한다(접기 전 값과
  견주면 거의 모든 편집이 다시 세우기가 된다).
- 편집표에서 고른 행은 행 번호가 아니라 업무 키로 기억한다 — 편집본은 제출마다 다시 만들어지고 행을 지우면 번호가 다시
  매겨진다. 되살린 행은 지우기 전 자리로 넣는다(맨 뒤에 붙이면 순서만 다른 리비전이 생긴다).
- **다른 세션이 행 차례를 바꿀 수 있는 편집표**(시나리오 관리 목록·리비전 표 — 남의 저장·이름 변경이 차례를 바꾼다)는
  `components/pick_edit_table.py` 를 쓴다: 고친 값·고른 행을 회차마다 행 id 초안으로 접고, 위젯 key 에 행 차례 지문을
  실어 차례가 바뀌면 새 위젯으로 세운다. 「고름 하나」는 두 줄이 골라진 회차에 초안을 먼저 적고 세대를 올린다 —
  `discard_editor` 만 부르면 같은 표의 이름·순서 편집까지 사라진다. 접기와 다시 세우기는 그리기 **전에** 하므로 본문
  `st.rerun()` 이 없다. 시험은 `tests/widget_browser.py` 의 `BrowserTables` 로 브라우저처럼 칸 편집을 보내 잰다
  (`AppTest.run()` 은 편집표 상태를 보내지 않는다).
  - 그런 표의 비교 후 쓰기 기준은 사용자가 **본** 값이다(초안에 함께 적는다) — 저장 콜백이 받는 「지난 회차에 읽은
    값」은 남의 변경 뒤 회차가 한 번만 돌아도 남의 값이 된다. 시험은 남의 변경을 클릭 직전에만 끼우지 말고, 그 뒤
    회차를 한 번 이상(다른 행 고르기 등) 돌린 꼴도 둔다.
- **편집 화면의 적용·저장 버튼과 변경 메모는 편집표 위에 둔다** — 표가 높으면 아래 버튼이 화면 밖이라 적용을 건너뛴다
  (버튼을 먼저 만들어도 누른 회차에 편집값이 들어온다). 적용 결과·오류는 누른 버튼 바로 아래 자리에 쓴다.
- pandas Styler 표의 분류 칸 회색 배경은 Styler 를 직접 만들지 말고 `month_editor.classification_styled` 를 거친다 —
  Streamlit 이 rerun 마다 모든 칸을 번역하므로 칸 수 상한을 넘으면 칠하지 않는다. `st.dataframe` 으로 그리는 Styler
  표에는 표마다 다른 고정 `uuid=` 를 준다(무작위 uuid 면 회차마다 표를 다시 보낸다).
- **큰 조회 표의 화면 사본은 되풀이 글자 열을 category 로, 수를 좁은 정수로 보낼 수 있다**(STEP 구성 요약
  `reference_data._compact_step_summary`). `st.dataframe` 조회 표의 조건 셋: ① category 글자 열은
  `st.column_config.TextColumn()` 으로 못 박는다 — 두지 않으면 1.63 프런트가 선택 칸 꼴로 그려 글자 자리가 어긋난다.
  ② `lazy=False` 를 준다 — 자동 lazy(15만 행 초과, `lazy_df_source.AUTO_LAZY_ROW_THRESHOLD`)의 서버 정렬은 category
  열에서 「Failed to load data」 가 된다. ③ 그보다 긴 표는 줄이지 않고 `lazy=None` 으로 맡긴다 — 한꺼번에 받은 표가
  15만 행을 넘으면 프런트가 정렬을 끈다(끝 값은 `tests/test_reference_data_perf.py` 가 Streamlit 상수와 견준다).
  표시명은 줄이기 **전**에 입힌다(category 값이 곧 보이는 글자다). 편집표(`month_editor._compact_dimensions`)는 ①·②
  가 걸리지 않는다 — `st.data_editor` 에는 lazy 가 없고, 분류 열 설정은 `_dimension_column_config`(표시명 열은
  `SelectboxColumn`, 나머지 `TextColumn`)를 그대로 쓴다. category 와 함께여도 화면이 같다(표시명 열에 `TextColumn` 을
  못 박으면 표시명이 원본 값으로 돌아간다).
- **`st.download_button` 은 `components/table_toolbar.py` 에서만 부른다**(라벨에 아이콘을 섞지 않는다). 내려받기 CSV
  바이트는 매 회차 다시 만들지 않고 내용 지문 키 캐시(`simulation_cache.get_export_csv` 등)로 받으며 콜러블 지연 생성은
  쓰지 않는다 — 빗나간 회차에는 바로 만들어 오류가 그 자리에 드러나게 한다.
- 사람이 적은 자유 글(게시판 본문·답글·메모)은 `st.markdown` 으로 그리지 않는다 — `#`·`-`·`*` 가 제목·목록으로 바뀌고
  빈 줄에서 HTML 블록이 끊겨 적은 사람이 보던 글과 달라진다. 글만이면 `st.text`, HTML 로 감싸야 하면 `html.escape` 한
  뒤 `st.html` 로 넘긴다. 제목·이름처럼 마크다운으로 그려지는 자리(`st.expander` 라벨·`st.caption`·`st.markdown`·
  알림 상자)에 넣는 사람 글과 주소 인자 글(공정 Capa 상세의 `?process=` — 누구나 링크로 적어 보낸다)은
  `literal_markdown` 으로 감싼다 — 그대로면 「A~B~C」의 물결표는 취소선으로, 「$…$」는 수식으로 사라지고 `![x](주소)` 는
  보는 사람마다 그 주소를 부르는 이미지가 된다. 조사 도우미는 escape 의 `\` 를 건너뛰므로 감싼 뒤의 글로 골라도
  escape 하기 전과 같은 조사다(「WB\(2\)」→「는」, `tests/test_korean_particle.py`) — 감싸는 차례에 매이지 않는다.
- 앱이 지은 거부·안내 문구를 알림 상자(`st.error`·`st.warning`·`st.info`·`st.success`)에 넣을 때 그 문구가 범위 물결표(「동은
  C1~C5, 층은 1F~6F」)를 품을 수 있으면 `literal_markdown.markdown_safe_tildes` 로 감싼다 — 물결표 둘이면 가운데가 지움선이 된다.
  구두점 전부가 아니라 `~` 만 막아 문구에 일부러 넣은 굵게·코드는 산다. 문구 바이트는 규칙 시험이 고정하므로 상수는 그대로 둔다
  (`tests/test_equipment_master_tab.py`). 저장소 예외 글(`str(exc)`·`bootstrap_error_message(exc)`)도 같다 — 날 이름(남이 먼저 바꾼
  설비 시나리오 이름·리비전명, 「「…」 r2를 저장해」)을 담으므로 그 글을 넣는 알림 상자는 감싼다(시나리오 관리 설비 시나리오 구획의
  거절 알림 `REFUSED_KEY` 는 그리는 자리 한 곳에서, 사이드바 설비 시나리오 팝업 저장 실패도). 설비 시나리오 이름을 싣는 잠금·빨리
  감기 글(`space_edit_mode`)·머리 알림 줄·저장 결과도 그리는 자리에서 막고, rerun 건너 그리는 성공 글(`queue_flash`)은 Space 가
  담을 때 막는다(`_queue_space_flash` — `tests/test_space_layout_overlay_page.py`, E2E r3). 사이드바 설비 시나리오 줄 아래 팝업
  저장 알림(`save_result_message`)·세션 이동 알림(`EquipmentSession.notice` — 사이드바 줄·시나리오 관리 구획)과 Space 층 끄기
  확인의 가정 배치 덧줄도 그리는 자리에서 막는다(`tests/test_equipment_scenario_layout_management.py`). Guide 원문(`guides/*.md`)은
  `st.markdown` 으로 그대로 가므로 원문에서 `\~` 로 막는다
  (`tests/test_page_guide.py` 가 모든 Guide 를 본다).

### 스크립트와 컴포넌트

- **브라우저에 싣는 스크립트·컴포넌트 내용은 회차마다 같아야 한다.** 툴바 iframe 과 입장 화면의 등록 JS·`data` 는 상수만
  든 고정 문자열로 보낸다 — 바뀌면 Streamlit 이 iframe 을 새로 만들어 옛 단추의 `onclick` 이 죽고 큰 메시지를 다시
  보낸다. 회차마다 달라지는 값(테마 등)은 브라우저 쪽에서 읽는다(`capaTheme.resolve`).
- 스크립트를 싣는 칸은 `st.iframe` 이다 — `st.html` 은 스크립트를 실행하지 않고 `components.v1.html` 은 회차마다 폐기
  예고를 찍는다. 헤더 툴바·사이드바 머리칸에 단추를 다는 스크립트는 iframe 을 따로 두지 않고 테마 버튼 iframe 의
  `extra_scripts` 로 싣는다(접은 iframe 도 본문 맨 위에 요소 간격 한 칸을 먹는다).
- **모든 화면에 걸친 컴포넌트(화면 탭 줄)는 `app.py` 에서 고정 key 로, 앞에 조건부 칸 없이 그린다.**
  `navigation.run()` 밖이라 요소 id 에 주 스크립트 해시가 들어가 화면을 옮겨도 같은 요소다 — 페이지 안에서 그리면
  화면마다 다시 마운트된다. 그 앞 본문에 생겼다 사라지는 칸(스키마 경고 등)을 두면 순번이 밀려 다시 마운트된다
  (`tests/test_page_tabs.py` 자리 시험). **프래그먼트로 감싸지 않는다** — 프래그먼트 안의 트리거는 돌고 있는 앱 전체
  실행을 끊지 못해 무거운 회차 중에 누른 탭이 그 계산을 기다린다. 탭 패널이 없는 이동 목록에는 탭 역할(ARIA)을 쓰지
  않는다 — `check_deploy_screens` 의 `get_by_role("tab")` 이 그림자 DOM 을 뚫어 본문 탭보다 먼저 잡는다.
- **팝업(`st.dialog`) 안에 마운트하는 Components v2 컴포넌트는 그림자 DOM 에 가두지 않는다**(`isolate_styles=False`) —
  팝업의 포커스 순서가 그림자 DOM 안을 보지 못해 Tab 이 닫기 단추로 가 고친 값을 버린다. 서식은 고유 클래스 접두어로만
  건다(월 입력 컴포넌트는 위 「월 입력」 항목).
- **Space 층 뷰어의 기준일 고정**(`asOfPinned` — 「필요 단축」 보기): data 에 그 칸이 실린 회차만 페이더 대신 같은 높이의 고정
  줄이 서고(`is-pinned`, 같은 `!important` + 더 높은 선택자로 보기의 편집 전용 숨김을 이긴다) 기준일은 받은 날(오늘)이다. 그 보기에
  표시된 호기(`layer`)는 겹친 반입 예정으로 숨기지 않는다(`coveredBy` — 단축 후보는 대개 기존 자리에 들어올 반입 전 호기다). 배지만
  바뀐 같은 epoch 회차는 호기 값이 그대로라 배지 지문(`S.badgeKey`)으로 다시 그린다.
- **편집본을 바꾸는 Components v2 조작은 트리거가 아니라 상태 값 하나(출납 `outbox`)로 보낸다.** 1.63 의 위젯 상태 합치기는
  단추 트리거만 앞 값을 살리고 CCv2 `json_trigger_value` 는 살리지 않아, 실행 중 회차가 있으면 잇단 트리거가 앞 것을 덮는다.
  상태 값은 「가장 새 값」 이 이기므로 늘 **반영되지 않은 조작 전부**(마운트 id·seq·브라우저 시각 `at`)를 싣고, 파이썬은 마운트별
  마지막 seq 기억으로 seq 가 큰 것만 `(at, mount, seq)` 차례로 한 번 반영한 뒤 그 마운트의 `ack` 를 data 에 실어 돌려준다(설비 마스터
  표 — `services/equipment_grid.pending_ops`·`apply_ops`). 편집본 출발점(`base`)이 달라진 op 는 반영하지 않고 버린다. 브라우저는
  300ms 조용하면 보내고, 초점이 컴포넌트 밖으로 나가거나 창이 숨으면 바로 보낸다 — 보낼 것이 있을 때만(빈 값을 다시 적으면 회차만
  는다). 잃어도 되는 화면 조작(열기·목록에서 빼기)만 트리거다. 편집본을 **바꾸지 않는** 둘째 상태 값은 이 규약 밖이다 — 설비 마스터
  「새 호기」 초안 `draft` 는 확정마다 번호를 올린 초안 전부를 보내(앱 회차 하나) 늦게 온 옛 값을 번호로 거르고, 그 초안을 넣는
  「호기 추가」 는 출납 op `add`(번호 `draftSeq` 가 세션 초안보다 작으면 버림)다.
- Components v2 의 브라우저 전용 보기 상태(높이·배율·서랍 열림)는 컴포넌트 안이나 localStorage(읽기·쓰기 모두
  try/catch)에 두고 `setStateValue`·Streamlit 위젯으로 보내지 않는다 — 보내면 앱 전체가 다시 돈다. 브라우저 안에서 끝낼
  수 있는 일(페이더를 끄는 동안 칠하기)은 컴포넌트 안에서 끝낸다 — 놓은 뒤 한 회차 시간은 대부분 프런트엔드가 페이지를
  다시 그리는 시간이라 프래그먼트로 감싸도 크게 줄지 않는다.
- **회차마다 소켓으로 다시 가는 스타일 문자열에는 CSS 주석(`/* */`)을 싣지 않는다** — 사이드바 시트·머리 띠·껍데기
  스타일·HOME 제목 줄·공지 상자·공정 필터 풍선이 그렇다. 설명은 그 조각 바로 위 파이썬 `#` 주석에 두고 문자열을 규칙
  단위 조각으로 나눠 괄호 안에서 잇는다. 사용자 글을 넣은 뒤의 CSS 에 정규식으로 주석을 걷지 않는다(`css_string` 이
  `/*` 를 이스케이프하지 않는다). `..._carry_no_css_comments` 테스트가 지킨다.
- **브라우저 ForwardMsg 캐시는 `.streamlit/config.toml` `[global]` 의 나이 20·문턱 1,000B 다**(기본 2·10,000B). 문턱
  이상인 요소는 같은 내용이면 해시 참조(약 75B)로 간다 — 머리 띠·HOME 제목 줄·공지 상자가 문턱 이상인지는
  `tests/test_app_header.py` 가 config 를 읽어 지킨다. 나이 2 에서는 사이드바 상자를 두세 번 여닫거나(빈 프래그먼트
  회차도 나이를 먹는다) 화면 둘을 거쳐 HOME 에 오면 그림을 통째로 다시 받았다(합성 표본 약 1MB). 「Cached ForwardMsg
  MISS」 연결 오류 창은 Streamlit 프런트 경합(빈 프래그먼트 회차의 script_finished 를 앱 전체 회차로 읽음)이라 줄일
  뿐 막지 못한다 — F5 로 풀린다. 회차 끝 강제 GC(`runner.postScriptGC`)는 끄지 않고(세션 순환 soak 에서 RSS 가 높은
  채 머묾) `gc.freeze()` 도 쓰지 않는다(얼린 순간 살아 있던 세션이 닫혀도 걷히지 않는다).

## 10. 로컬 파일과 보안

다음 파일은 Git에 커밋하지 않는다.

- `*.xls`, `*.xlsx`, `*.xlsm`, `*.xlsb`
- `data/*.db` 및 SQLite 보조 파일
- `data/*.duckdb` 및 DuckDB 보조 파일
- `.env`, `.streamlit/secrets.toml`
- `data/input`, `data/output`, `data/temp`의 실제 데이터
- 로그와 가상환경

`templates/structure_template.xlsb`, `data/capa_simulation.db`,
`data/capa_simulation.duckdb`, `data/equipment_availability.duckdb`는 로컬 실행 자산이다.
테스트나 문서에서 실제 사내 데이터 값을 노출하지 않는다.
`config/bootstrap_display_order.json`과 `builtin_seed.py`에는 합성 `DEMO_*` 값만 두며 실제
제품·고객·공정·설비 식별값을 시드로 추가하지 않는다. 실제 표시순서 CSV는
`data/input/RQ_DISPLAY_ORDER.csv`에 두고 Git에 커밋하지 않는다.

앱 코드의 `subprocess` 는 `io/object_storage.py` 한 곳에만 둔다(명령 실행기를 주입받아 시험한다). C-DEP CD 시작
스크립트(`scripts/container_start.py`)의 pip·import 확인은 앱이 서기 전 `scripts/` 몫이라 이 규칙 밖이고, 앱 쪽(어댑터·
Admin)은 그 결과 파일만 읽는다. 커밋되는
`config/object_storage.json` 의 `mode` 는 반드시 `local` 이다. 그 자리도 `subprocess.run` 기본(`close_fds=True` — Windows 에서
핸들을 물려주지 않는다)으로 부르고 `close_fds=False`·`os.system`·`os.spawn*` 은 쓰지 않는다 — Streamlit 1.63 은 듣는 소켓을
상속 가능으로 열어(`starlette_server._bind_socket` 의 `set_inheritable(True)`), 핸들을 물려받은 자식은 앱을 끈 뒤에도 8501 을
쥔다(런북 4-2 「접속이 안 되면」).

## 10-1. 로컬 데이터는 합성 표본이다 — 관측을 업무 사실로 적지 않는다

`data/input/Core_Data.csv` 와 거기서 적재된 `data/capa_simulation.duckdb` 는 **실제 운영
데이터가 아니라 합성 데모 표본**이다. 공정 목록·소요기준(WF/CHIP)·성능·수율은
`scripts/generate_sample_core_data.py` 의 `PROCESS_SPECS` 리터럴에 사람이 써 넣은 값이고,
행의 팬아웃(계획 1행 × 전 공정)도 `process_rows()` 가 계획 행을 전 공정에 복제해서
생기는 구조적 산물이다. `equipment_samples.py`, `dynamic_capacity.py` 의 `DemoProfile`,
`builtin_seed.py` 도 같다.

따라서 다음을 지킨다.

- **로컬 DB·CSV 를 쿼리해 나온 값으로 업무 구조를 판단하거나 설계를 바꾸지 않는다.**
  쿼리는 코드 경로가 도는지 확인하는 용도다. 「데이터가 이러하니 업무가 이러할 것」은
  표본 생성기 저자의 선택을 업무 사실로 착각하는 것이다.
- **`실측` 이라는 말은 데이터와 무관한 측정에만 쓴다** — 브라우저 픽셀 폭, Streamlit
  위젯 동작, 소요시간 같은 것. 데이터를 집계해 얻은 수치는 `샘플 관측` 이라고 적고
  출처(어느 파일의 어느 리터럴에서 나온 값인지)를 함께 남긴다.
- **표본 고유 수치를 계약처럼 적지 않는다.** 「키 하나에 31행」, 「WF 기준 공정 6개」,
  「소요대수는 전부 NULL」 같은 문장은 공정 수와 생성기 설정이 바뀌면 전부 달라진다.
  코드가 그런 수치에 의존하면 그것은 결함이다.
- 근거가 사내 실데이터에서 온 것이면 **그렇다고 명시한다**. 예: `Pack Code` 충돌과
  `MPGA TEST` 의 소수 `모듈수` 는 사내 BigDataQuery 관측이라 근거가 있다.
- **실데이터로만 답이 나오는 질문은 사내에서 잰다.** `scripts/inspect_real_data_checks.py` 가 두 DB 를
  `read_only` 로 열어(저장소 `initialize()` 는 마이그레이션을 걸어 쓰므로 부르지 않는다) 기존 결과 대조
  분포(ST 정의 대조 UPEH × ST ÷ 60·소요대수 ≈60 배 무리 가르기 포함)·원천 `RQ_REQB` 소요기준·설비 DB·
  BigDataQuery·HOME 월 축(양산 Density 가 있는 달)에서 빠지는 계획 달 수(8-9 — 2026-10-22 결정 A: 월 축은 그대로 두고 0 이면 그 결정 대기를 닫는다)와
  「지금대로」 로 정한 결정마다 그 꼴이 저장 리비전에 몇 개 있는지(8-10 센서스 — 기본은 활성·공식버전 대상 리비전, `--census-all-revisions`
  면 전부. 줄마다 근거가 되는 `docs/TODO.md` 결정 번호와 그 가운데 잰 부분을 꼬리표로 단다 — 수는 근거일 뿐이라 0 이어도 결정을
  닫지 않고 사외가 사용자에게 묻는다. BigDataQuery 가 있어야 답이 나는 것은 넣지 않는다)를 재고,
  **개수·비율·dtype·초만** Markdown 블록으로 찍는다 — 이름·코드·키별 값·합계 물량·파일 경로·예외 문구를
  찍지 않는다(이 앱의 오류 문구에는 식별값이 실린다). 값 이름은 계약 어휘(소요기준·Main/MI·`WF 구분` 선언
  목록)만 찍고 그 밖은 종류 수로 센다. 자동 판정(통과·실패·결론)은 넣지 않는다 — 넣으면 재검증이 갈래마다
  반례를 낸다. 사실만 찍고 결론은 사외가 사용자와 낸다. 사내 런북(`docs/internal_update_runbook.md`) 8장이 배포마다 부르고
  결과는 리뷰 문서로 돌아온다. 사내 리뷰는 사람이 손으로 옮겨 적으므로(2026-10-22) 출력 끝에 `### 전송용 요약`(돈 블록마다 짧은 키와
  수만 실은 한 줄 · 합이 서는 수는 줄 안 `합 = 항 + 항` · 줄 끝에 그 줄의 수로 셈한 확인 코드 `#NN`, 8-10 은 0 이 아닌 키만 — 블록 출력은
  그대로)을 찍고, 사내는 그 줄을 코드째 리뷰 압축본에 옮긴다(런북 5장 · 8-6). 키의 뜻은 런북 8-6 범례 한 곳에 두고 요약에 안내문을 두지
  않는다. 사외는 받은 압축본에 `--check-summary <파일>`(DB 를 열지 않음)을 돌려 한 자리 오타 · 자리바꿈 · 빠진 8-10 줄을 잡는다. 블록이
  요약 줄을 `Session.notes` 에 쌓고 끝에 한 번 찍는다 — `Ctrl+C` 로 멈춘 실행도 「(중단 — 여기까지)」 와 함께 찍고(센서스는 센 줄까지),
  요약 줄 조립은 `_noted` 로 감싸 실패해도 블록 출력을 잃지 않는다. 블록을 더하면 그 요약 줄과 범례 한 줄도 더한다. 블록을 더할 때는
  `tests/test_inspect_real_data_checks.py` 의 표지값(`ZZSENTINEL…`) 검사를 함께 늘리고, 출력·요약이 런북 5장 자가 점검 그물(대소문자
  무시)에 걸리는 줄이 8-4 사용기준 한 줄뿐인지 보는 시험(그물은 런북에서 읽는다)이 그 블록도 덮게 한다. 앱은 rerun 동안만 DB 를 쥐어 쉬는 앱은 잠금에 안 잡히므로,
  운영 DB 를 열 때는 화면 확인 스크립트의 `running_app_count` 로 앱 프로세스를 먼저 보고 보이면 DB 를 열지
  않고 종료 1 로 멈춘다. 살피지 못하면 잠금만 보고 그 사실을 한 줄 찍는다. 사본만 열거나 BigDataQuery
  블록뿐이면 보지 않는다. 같은 8장 뒤에 도는 `inspect_wf_division.py` 도 같은 판정으로 멈추고, `--database <사본>` 을 주면(운영
  DB 자리가 아니면) 앱 프로세스를 보지 않는다. 운영 DB 자리 판정은 `settings.is_operational_database_place` 한 벌이다 — 같은 파일
  (하드링크 · Windows 긴 경로 접두 · UNC 공유처럼 글자가 달라도 장치 · 파일 번호로), 운영 `data/` 그 자체나 그 아래, git 저장소
  안(사본은 저장소 밖 — 사본 트리의 스크립트가 다른 저장소의 `data/` 를 못 가리는 것도 이것이 막는다). 경로 글자만 견주지 않는다.
  설비 DB 는 **공식 설비 시나리오**(공통 최신 + 최신 공식 발행)를 앱과 같은 읽기 길(`equipment_repository.read_official_pair`·
  `read_merged` — 3장)로 한 번 읽어 8-1·8-4 가 나눈다. 공통 칸 수는 공통 최신 SQL, 일정 칸 수(Q 자리표·개편 전 두 날짜·일정
  미정·정지+반출·비가동 행)는 공식 일정 리비전으로 센다 — Q 자리표는 레거시 원천 행만 센다(새 일정 표에는 자리표가 없다).
  8-4 요약 키의 `r` 은 공식 일정 리비전 번호라 일정은 그대로 두고 공통만 v4 로 저장해도 8-1·8-4 키가 그대로다(시험). 이관 확인
  줄(설비 `0027` — 시나리오 수·이관 리비전/이관 전 리비전·공식·옛 배포 흔적·일정 없음·고아 일정 행, 설비 `0031` 뒤 끝에 가정
  배치 차이 호기 행 `Y` — S4)은 요약 키 `8-4s` 로 따로 지어 8-4 줄이 멈춰도 남는다. 시나리오 이름은 값이라 찍지 않는다. 같은 표의
  「가정 배치 차이」(ACTIVE 시나리오 최신의 저장된 행: 시나리오 / 호기 / 요소 / 이름표)·「배치 옛 코드 흔적」(0 이어야 함) 두 줄은
  앱 목록 투영(`equipment_scenario_store.scenario_rows`)을 그대로 읽는다. `--check-summary` 는 수만 셈하므로 `Y` 없는 옛 8-4s 도
  받는다.
- **배포마다 바뀌는 사내 화면 확인(런북 7장)은 `scripts/check_deploy_screens.py` 가 맡는다.** 별도 포트에 띄운
  앱을 저장소 밖에 깐 Playwright(깔린 Chrome, headless)로 보고, 결과 칸에는 개수·있음/없음·같음/다름·px 만
  둔다 — 화면에서 읽은 이름은 판정에만 쓰고 옮기지 않는다. 항목은 공통 뼈대(`Screen`)만 쓰는 함수 하나와
  `ITEMS` 한 줄이고, DB 에 쓰는 항목은 `writes=True` 로 두어 `--allow-writes` 없이는 「안 함(허락 없음)」이다
  (저장 뒤 지워 되돌리는 것만 둔다). 앱은 rerun 동안만 DB 를 쥐므로(`pinned_connections`) 떠 있는 사용자 앱은
  DB 잠금만으로 못 가린다 — 프로세스 명령줄(`streamlit run … app.py`)을 먼저 보고, 살피지 못하면 미룬다.
  잠금은 DuckDB 고정 문구·쥔 PID·Windows 공유 위반(그 파일을 직접 열어 32·33)만이고 깨진 파일·액세스
  거부는 「DB 를 열지 못했습니다」다. 종료 코드는 0 끝까지 돎 · 2 준비 안 됨·멈춤 · 3 미룸이다(1 은 강제
  종료·처리 안 된 예외와 겹쳐 쓰지 않는다). `--output` 은 경로 검사를 지나면 「확인 시작」으로 덮어쓰고 일찍
  끝나면 「미룸 — …」·「멈춤 — …」 한 줄만 남긴다 — 사전 확인 전의 전체 머리(「DB 잠금 없음」)는 거짓이다.
  경로 옵션은 parse 직후 한 번 `expanduser().resolve()` 해 검사와 쓰기가 같은 값을 쓴다(장치·UNC·스트림·
  하드 링크 꼴은 거절). 기다리는 동안 `page.url` 을 읽지 않는다 — Playwright 가 이동 사건으로 고쳐 두는 값이라
  `time.sleep` 사이에는 옛 주소에 머문다. 도착은 페이지에 물어(`Screen.path`) 본다. 글자가 「다 보임」 인지는 칸 상자끼리
  견주고 끝내지 않고 글자 잉크가 자르는 조상들의 안쪽 선 안에 드는지까지 본다(`_WHOLE_LINE_JS` 의 `inked`). 항목은 기다림
  앞에 `screen.step("<고정 글자>")` 를 두어 미기록 칸이 어느 단계에서 멈췄는지 말하게 하고, 쓰지 않는 항목이 첫 판에
  `TimeoutError`(이 파일의 것이든 Playwright 의 같은 이름이든)면 `run_items` 가 한 번 더 돌려 칸 끝에 첫 판 줄을 남긴다.
  꺼질 수 있는 단추(페이더가 오늘일 때의 「오늘」 처럼 `disabled`)는 켜졌을 때만 누른다 — 꺼진 단추를 누르면 Playwright 가
  켜지기를 30초 기다리다 `TimeoutError` 로 끝나 앞의 결과를 가린다. Space 두 항목은 `Screen.open_space_overview` 로
  FAB 전체에서 시작한다 — 연 층은 위젯이 아니라 세션 값이라 앞 항목(`space_drawer`)이 연 층이 페이지를 다시 열어도
  남고, 그 층 상세에는 층 목록 표가 없다(사내 리뷰 202610200720 발견 1). 확인용 앱은
  `127.0.0.1` 에서만 듣고, 자식의
  `PYTHONPATH` 맨 앞에 이 저장소의 `src` 를 두며, 스크립트가 강제로 끝나도 남지 않게 Windows Job Object
  (Linux `PR_SET_PDEATHSIG`)로 묶는다. `tests/test_check_deploy_screens.py` 는 Playwright 없이 뼈대(경로
  거절·사전 확인·앱 수명·항목 실행·결과 꼴·main 흐름)를 보고, 항목이 찾는 선택자·화면 글자 가운데 일부
  (입장 화면 호스트·사이드바 라벨 id, Space 서랍 클래스, 항목이 찾는 라벨 글자)가 앱 코드·자산에 그대로
  있는지만 대조한다 — 화면에서의 동작은 대조하지 않는다(사외 브라우저 실측과 사내 실행이 본다).
- **사용자 앱을 끄지 않는 실데이터 확인은 실 DB 사본으로 한다**(사내 런북 6-3 — `.wal` 이 없을 때 복사, `git archive`
  사본 트리, `127.0.0.1` 별도 포트). 전 리비전 계산은 `scripts/inspect_revision_calculations.py` 가 맡는다 — 모든 리비전을
  앱과 같은 길(`repository._load_reference_frame`)로 읽어 대당 Capa → 소요대수 → 확보율을 돌리고, 상태(됨·멈춤·확보율
  멈춤·불러오기 막힘·읽지 못함)와 개수(소요대수에 닿지 않은 계획 줄·겹친 경로 키(`WF 구분` 대소문자 무시)·제외 행)만 찍는다.
  소요대수까지 서면 저장·발행 검사의 Density 환산(`capacity_gate.density_error` 그대로 — 시나리오 전체 기간·EDP 계획)도 돌려 `계산` 칸과 따로
  `Density` 칸·「Density 멈춤」 수로 적는다(확보율과 서로 가리지 않는다). 공식버전 줄은 판정값인 최신 공식의 상태·`Density`
  칸을 앞에 두고, 이력이 가리키는 모든 리비전의 수는 `지난 공식버전 포함 Density 멈춤` 으로 따로(0 이어도) 적는다. 최신 공식의
  Density 칸이 됨이어야 한다 — 아니면 거기서 이어 저장하는 리비전마다 경고가 붙고 발행이 거절되므로 런북 6-3 이 본다. 지난
  공식버전의 Density 멈춤은 그 시나리오를 다시 열어 저장할 때만 경고가 붙는다(발견에 수만 옮긴다). `capacity_gate` 는
  Streamlit 캐시 래퍼를 함께 불러와 실행 문맥 밖 경고가 수십 줄 찍히므로 불러오는 동안만 로그를 끈다. 시나리오·리비전은
  이름 대신 차례 번호, 예외는 종류와 문구 속 계약 표 이름(`RQ_*`)만이다. `--database` 는 기본값이 없다 — 앱은 연산마다
  연결을 열고 닫아 쉬는 동안 운영 DB 도 열리지만, 스크립트가 쥐는 동안 사용자 앱의 연결이 막힌다. 그래서 운영 DB 자리
  (`settings.is_operational_database_place` — 같은 파일 · 운영 `data/` 아래 · git 저장소 안)는 열기 전에 거절하고(종료 2), 런북 6-3 a 는 저장소에서
  `uv run --no-sync python scripts/inspect_revision_calculations.py --database <사본>` 꼴로 부른다 — 이 거절과 고정한 꼴이 권한
  템플릿에 allow 를 줄 전제다(`docs/TODO.md` 결정 12). HOME 시간은
  `scripts/benchmark_home.py --data-dir <사본 폴더> --output <파일>`(같은 판정으로 저장소 안은 거절, 입력 없는 토글은 `skipped`)로
  잰다. UPEH 가정 계획 1회 시간(`scripts/benchmark_upeh_assumption.py --data-dir <사본 폴더> --output <파일>`)도 같은 판정으로
  저장소 안을 거절한다. 사본 모드는 실패해도 HOME 의 문구를 찍지 않고 같은 규칙(단계·예외 종류·계약 표 이름)의 한 줄만 찍으며, 재는
  동안 Streamlit 로그를 끈다(잡히지 않은 예외는 그 로그가 문구째 찍는다). 두 스크립트의 출력은 UTF-8 이다 — 사내 Windows 파이프는
  cp949 라 그대로 두면 「—」에서 멈춘다. 벤치마크는 화면 모듈을 **첫 AppTest 실행 안에서** 처음 불러온다 — 먼저 불러오면
  Components v2 가 실행 밖에 등록돼 HOME 이 「Component … is not registered」로 멈춘다(`tests/test_benchmark_home.py`).
  두 스크립트의 테스트가 표지값·첫 실행 전 모듈·cp949 파이프를, `tests/test_runbook_copy_e2e.py` 가 런북 6-3 의 명령과 두
  스크립트 인자 계약을 본다.
- **사내가 정해진 확인 밖의 질문을 실데이터로 좇는 길은 런북 9장(사내 탐색) 하나다**(2026-10-22 사용자 답). 실 DB 사본(6-3 의
  사본 만들기, `read_only` 기본)만 열고, 도움 코드·출력은 저장소 밖 고정 폴더 하나, 반출은 개수·가명·합성(`DEMO_*`) 재현
  스케치뿐이다. 즉석 코드는 몸통을 예외 틀로 감싸 예외 종류만 찍는다(런북 9-1 — 트레이스백 문구에 값 · 셀렉터가 실린다). 실적·
  재공·수율 같은 다른 원천 DB 는 할 때마다 사용자에게 다시 확인한 뒤 구조 정보만 본다. 사외가 사내에 묻는
  질문은 런북 7장·`docs/TODO.md` 에 사내가 그대로 좇을 수 있는 한 구절로 적는다. 7장 B(손 확인) 가운데 사본 앱 + 헤드리스로 셀
  수 있는 칸(개수·있음/없음)은 사내 에이전트가 먼저 채우므로(런북 6-3 「B 대행」 — 사용자가 앱을 쓰지 않을 때만), 7장 B 를 쓸 때
  사용자 몫(인쇄·소리·사용자 Chrome·사람 판단)을 칸마다 갈라 두고, 「결과 꼴」 에 기대값을 먼저 적는다(압축본의 `ok` 는 그 기대값이
  다 맞았다는 뜻이다). 압축본은 B 를 사용자 · 대행으로 갈라 세고 사용자 몫이 모두 미기록인 항목은 기록에 넣지 않는다(런북
  5장). 6-3 의 a·b·c 가운데 무엇을 할지는 배포마다 7-0 이 정한다. 사내 절차는 사용자 한 사람과 사내 에이전트 하나를 기준으로
  쓴다(동료 분담 문구를 두지 않는다).
- **사내 리뷰는 두 파일이고, 사외에는 압축본만 사람이 손으로 옮겨 적어 온다**(2026-10-22 사용자 결정 「최대한 짧게 압축」 ·
  같은 날 답 「손 전사」). 압축본 `review/<stamp>.md` 는 판정 줄이 먼저인 키 · 값 줄(약속어 `ok` · `ng` · `na` · `=<stamp>` · `n/N`,
  기대대로인 것은 수로 접고 스크립트 블록은 머리 수와 `ok` 가 아닌 줄만, 목표 20줄 안팎)이고, 전문 `review/<stamp>.full.md` 가
  블록 · 표 · 7장 요청 응답 표 · 탐색 절을 사내 커밋으로만 남긴다(적는 꼴의 정본은 런북 5장, 양식은 `docs/dual_env_workflow.md`
  4장). 손 전사라 숫자 묶음에는 검산이 남아야 한다 — 에이전트가 센 묶음과 스크립트 블록 머리의 수 묶음은 줄 안 `합 = 항 + 항` 식,
  8장 요약 줄은 확인 코드 `#NN`(`--check-summary` 가 둘 다 다시 센다). 결정 대기의 근거 줄은 판정 · B · A 바로 아래에 두어 다 옮기지
  못해도 남게 한다.
  그래서 사내 확인(7장 결과 꼴·8장 블록)을 설계할 때 옮겨 적을 수가 적고 블록 안에서 합이 맞는 칸을 두어, 압축본의 수만으로 판정이
  서고 식과 코드로 오타가 잡히게 한다. 맞지 않으면 그 줄만 다시 옮겨 달라고 한다. 직전과 같은 줄은 `=<stamp>` 로 접히므로(사외가 받은
  압축본에 그 줄이 값으로 있을 때만), 같아도 값으로 받아야 하는 칸(첫 배포 확인 · 블록 꼴이 바뀐 배포)은 7장에 「값으로」 라고
  적는다. 새 스크립트가 압축본에 옮길 수를 찍으면 확인 코드나 합이 서는 식을 함께 찍게 한다.
- **코드 밖 산출물은 사외가 뼈대, 사내가 완성이다**(2026-10-22 사용자 결정 — `docs/dual_env_workflow.md` 1-1). 코드 정본은 사외
  그대로이고, 실데이터 화면이나 사내 사정이 있어야 끝나는 산출물(첫 대상은 화면 따라하기 가이드)은 사외가 생성기 · 틀 · 스키마 ·
  안정 ID 원고 · 점검기 · 합성 예시판을 보내고, 사내는 안정 ID 에 붙는 덮어쓰기와 매개값만 고쳐 실 DB 사본에서 완성한다. 사내 작업
  자리 `review/<산출물>/` 과 사내판 `static/<산출물>/local/`(사용자가 복사 — 사내 에이전트는 `static/` 에 쓰지 않는다)은 git 이
  무시하고, 완성본은 사내 밖으로 나가지 않는다(리뷰에는 개수 · ID · 고정 라벨만). 실화면 그림 검수는 사용자 몫이다 — 사내
  에이전트는 그림 · 결과 HTML 을 열지 않고 스크립트가 찍은 ID · 개수만 쓴다(런북 0장 · 10-4). 뼈대에 모자란 것은 리뷰 「사외 요청」 으로 받아
  다음 뼈대에 넣는다. 한 번 쓴 안정 ID 는 바꾸지 않는다 — 바꾸면 사내 덮어쓰기가 모두 고아가 된다. 사내 절차는 런북 10장 「코드 밖 산출물 만들기(따라하기 가이드)」 다(9장은 사내 탐색).

실제로 이 규칙이 없어서, 표본의 `Mold` 소요기준이 `CHIP` 인 것을 근거로 사용자의 공정
설명이 데이터와 충돌한다고 보고한 적이 있다. 충돌 상대는 실데이터가 아니라 생성기였다.

## 11. 현재 미구현 및 주의 사항

- SQLite는 실제 런타임 Repository가 아니다.
- 실행 결과 스냅샷과 사용자 권한은 미구현이다.
- 설비 운영 이력의 등록자 식별·승인 및 Capa 계산 입력 전환은 미구현이다. 설비 리비전마다 「저장자」 를 선택 입력으로
  남길 뿐 누구나 저장한다(E9 — 권한은 사내 로그인 기능 때).
- Dynamic Capa는 현재 데모 프로토타입이며 실적효율·생산실적 DB 조회, 원천 컬럼 매핑,
  누적 이력 저장소와 표준 Capa 리비전 연결은 미구현이다.
- 원천이 붙지 않은 화면은 **샘플 스위치**(`components/sample_data.py`)를 갖는다. 기본은
  켜짐이고 켜져 있는 동안 화면 맨 위에 합성 샘플이라고 적는다. 끄면 그 화면이 무엇을
  기다리는지만 남는다. 세션 키 하나(`dynamic_capa_sample_data`)를 그룹 전체가 공유한다.
  **새 미연결 화면을 만들면 이 스위치를 붙인다** — 빈 껍데기는 만들 가치를 설명하지 못하고,
  표식 없는 합성 표본은 실적처럼 읽힌다. 입력이 없는 결정론적 데모(Dynamic Capa 데모 행·Chatbot 대본)는 세션에 한
  번만 만들고 사본을 쓰며(Chatbot 대본은 공정 표시명을 글자에 담아 그 프로필 버전마다), 실DB 를 붙이면 그 세션 칸의
  키에 원천 적재 시각 같은 입력을 넣는다.
- 표준 대비 재공 현황은 결정론적 샘플을 사용하며 실제 재공 DB의 보유 재공·유입·Flow
  시점 정의, 공정·STEP·제품 매핑, 미래 3일의 계획/전망 데이터 공급 규칙은 미확정이다.
- DuckDB 쓰기 직렬화는 단일 Streamlit 서버 프로세스 범위다. 다중 서버 프로세스로
  확장할 때는 별도 쓰기 서비스 또는 서버형 DB로 전환한다.
- 증감 표기색은 **글자색**(`DELTA_INCREASE`·`DELTA_DECREASE`)과 **면색**
  (`DELTA_AREA_INCREASE`·`DELTA_AREA_DECREASE`)이 다르다. 앞은 값 위에 작게 적는 선행 B/O
  증감이고 뒤는 확보율 보정 **구간 자체**를 칠한다. Density 칸 오른쪽 끝, 값과 같은 높이(값이 길면
  겹칠 수 있음 — 2026-10-07 사용자 결정)의 선행 입고 실적 글자는 따로 `ADVANCE_SHIPMENT_TEXT`(밝게 검정·
  어둡게 본문 글자색)이다 — 값과는 크기·자리로만 갈리고 증감 띠에 서지 않는다. 면색으로 글자색을 쓰면 막대 안에서
  글자보다 무거워진다. 휘도 단조 검사는 `STATUS_*` 셋만 보므로 이 둘은 그 검사 대상이
  아니지만, 막대 트랙·확보 막대에서 떨어지는지는 토큰 주석의 대비값으로 확인한다.
- BOX·PCB 는 산식 확정 전까지 대당 Capa·소요대수 계산에서 빼 두었다. **제외가 아니라
  `추가 예정` 이다**(2026-09-05 확정). `PCB수(K매)` 의 원천 공식 또는 PCB당 Unit·수율·보정
  기준이 확정되면 넣는다. 경계는 `frame_contracts.DEMAND_BASES` 와
  `frame_contracts.UNIMPLEMENTED_BASES` 다. 뒤의 것은 대당 Capa·소요대수·기준정보 적용 검사가
  모두 import 하는 한 벌이다 — 넣을 때 한 곳만 고치면 세 경로가 같은 행을 본다.
- `MCP_Chip_Ratio` 보정식은 미확정이다.
- BigDataQuery 실제 SQL과 컬럼 매핑은 `company_bigdataquery_adapter.py`에 커밋을 마쳤고
  `is_bigdataquery_adapter_configured()`도 참이며 사내에서 약 3만 행 조회와 시나리오 저장까지
  확인했다. 남은 것은 상세 조회 창의 결정과 사내 런북 8장의 실데이터 대조 결과이고, 반환 DataFrame은 구현된 `CoreDataProvider` 공통 처리·DuckDB 저장 경로를
  그대로 사용한다. DataLake·Impala를 별도 원천 어댑터로 붙이는 경로는 아직 없다.
- `app_pages/home.py`는 UI 코드가 크다. 대시보드 기능을 추가할 때 계산 로직을 더 넣지
  말고 Figure 생성기 또는 서비스 모듈 분리를 우선 검토한다.
- Capa Chatbot 은 실제 데이터로 만든 대본을 보이는 화면이고 LLM API·권한·대화 이력은 연결하지 않았다.
- 실행 관리 머리의 이행 현황판 숫자(미이행 공정·달, 일정 미확인, 단축 필요 호기)는 미구현이다. 약속 기준선을 어느
  공식버전으로 볼지, 지난 달 이행을 실적 가용으로 볼지는 그 기능을 설계할 때 사용자에게 묻는다.
- 선행 B/O 는 원래 S.PKG FRONT 공정(B/O 까지)에만 걸려야 하지만 공정 분류가 아직 없어 모든 공정에 건다
  (`services/advance_load.py`).
- `Static 대비 일정`·필요 단축 일정에서 계산이 멈추면 「Static 가용대수를 읽지 못해 설비 일정 기준만 표시합니다」 경고가
  뜨지만 이미 읽은 Static 은 비교에 그대로 쓴다. 문구와 맞지 않는 이 동작은 `tests/test_equipment_scenario_demand.py` 가
  고정하고, 고칠지는 결정 대기다.
- 사용기준을 비워 둔 옛 리비전의 호기는 설비 일정 기준 가용대수에서 빠진다 — 배포마다 사내 런북 8-4 가 HBM·EDP 행 수를
  따로 센다.
- 공식버전 자동 갱신 예약 스레드는 **첫 접속 때 선다** — Streamlit 은 세션이 붙어야 `app.py` 를 돌리므로 앱을 다시 띄운
  뒤 누군가 한 번 들어와야 예약이 시작되고, 그 전에 지정 시각이 지나면 그날은 돌지 않는다(사내 런북 4-4 가 탭 하나를
  열어 두게 한다). 코드를 고치면 앱을 다시 띄워야 스레드가 새 코드로 돈다.
- 앱은 로깅을 설정하지 않아 INFO 는 어디에도 나오지 않는다. 남겨야 할 드문 사건은 WARNING 으로 남기고, 되풀이되는
  실패는 처음과 회복 때만 남긴다(주기마다 쌓지 않는다).
- **DB 가 코드보다 새 것이면 막지 않고 알린다.** 적용된 마이그레이션 최고 번호가 코드보다 높으면(옛 배포 ZIP 으로 되돌린
  상태) 앱은 그대로 뜨고 화면 맨 위에 경고만 선다(`MigrationOutcome.schema_ahead`) — 막으면 DB 를 복원하기 전에는 되돌릴
  수 없다.
- **설비 `0027` 을 실은 배포부터 옛 배포 ZIP 으로 되돌리지 않는다**(사내 런북 4-2 끝) — 새 판에서 한 번이라도 저장한 뒤의
  옛 판은 설비 마스터를 빈 표로 읽는다(첫 저장이 계약 v4 공통이라). 옛 판에서 저장한 흔적(경계 뒤 계약 v3 공통)이 있으면
  새 판이 설비 마스터 저장을 막고(`EquipmentLegacyTraceError`) 설비 화면 맨 위에 경고를 세운다. 빠져나가는 길은 백업 복원과
  시나리오 관리 › 설비 시나리오의 「이대로 이어 쓰기」 둘이다(설비 화면 맨 위 경고 옆 「시나리오 관리에서 이어 쓰기」 단추가 그리로 옮긴다).
- **설비 시나리오 2단계는 아직 없다**(1단계 = 구조·이관·고르기·두 쪽 저장·발행·복제·이름·화면 최소·사내 이관 확인, 그 위에
  E7 리비전명·되돌리기·여기서 새 시나리오):
  시나리오끼리 일정 비교(F7), 보관·되살리기·영구 삭제·순서·공통 대장 이력 표(E8 나머지), 남의 공통 저장 때 일정 편집 다시 얹기(rebase),
  일정 없음
  호기를 「이 시나리오에 넣기」, 운영 변경 끌어오기(함께 넣기 행 단위 고르기는 개편 C 의 「새 호기」 칸 — 그 칸에서 넣은 호기만). 스키마는 1단계 그대로 받는다. 지금은 단일 사용자 전제라 여러 세션이
  함께 쓰면 함께 넣기·남의 공통 저장이 낡음·버림을 자주 만든다.
- 시나리오 보관은 파일 크기를 줄이지 않는다 — DuckDB 용량 회수는 영구 삭제 뒤 `scripts/compact_duckdb.py` 재구축뿐이다.
- 브라우저 뒤로/앞으로는 페이지 안 상태 이동이 아니다 — Streamlit 1.63 은 그 재실행에 브라우저 주소가 아니라 파이썬이
  마지막으로 쓴 조회 문자열을 보내 주소 표시줄만 바뀐다. 주소 인자는 새로고침 복원용으로만 쓰고 이동은 화면 안 길(경로
  줄·목록)로 한다. 파이썬이 주소를 바꿀 때마다 기록이 하나 쌓이므로 여러 키는 한 번에 바꾼다(9장 `st.query_params`).
- **Streamlit·Plotly 판을 올리기 전에 내부 동작에 기대는 자리를 다시 본다** — 비공식 DOM·저장 키(`data-testid` 선택자·
  1.63 DOM 구조·프런트엔드 `localStorage` 테마 키·`data-test-script-state`: 헤더 툴바·머리 띠·입장 화면·사이드바 서식·탭
  점·metric 줄·인쇄 규칙), 프래그먼트 러너 대역(`tests/fragment_browser.py`·AppTest `fragment_id_queue`), 프래그먼트의
  바깥 컨테이너 쓰기, 선택을 켠 그림의 `dragmode` 덮기, 지나간 위젯의 콜백, `st.switch_page` 끝의 `st.empty()`(콜백
  밖에서 옮기는 까닭 — 9장), Plotly 비공개 `_validate` 빠른 경로(`plotly>=5.24,<7`)와 번호 축을 알아보는
  `Layout._subplotid_prop_re`, 표 칸 글자 층이 기대는 plotly.js 동작(겹친 축 영역의 바탕을 그 축 층 맨 아래 — `layer: below`
  도형 위 — 에 깔기, `go.Table` 열 자르기 ±1px — `tests/test_table_text_layer.py` 가 먼저 깨진다), `.streamlit/config.toml` 의 숨은
  옵션 `global.maxCachedMessageAge`·`global.minCachedMessageSize`(이름이 사라지면 조용히 무시된다 — `tests/test_settings.py`
  가 이름을 본다)와 그 MISS 경합이 고쳐졌는지(고쳐졌으면 나이를 기본값으로 되돌릴지 다시 본다). 선택자 문자열은 한 모듈에 상수로
  두고 다른 스크립트는 자리 인자로 받아(`theme_toggle.TOOLBAR_SLOT`) 고칠 곳을 하나로 둔다.

## 12. 변경 작업 체크리스트

### 입력 테이블 또는 컬럼 변경

1. `config/data_contract.json`과 사내 DB 컬럼 매핑 확인
2. 서비스 필수 컬럼과 키 갱신
3. 활성 시나리오 editable 여부 결정
4. 월 필터와 화면 편집 Long/Wide 변환 확인
5. 누락·중복·범위 테스트 추가
6. README, AGENTS, TODO 갱신

### 계산식 변경

1. 계산 단위와 조인 키를 먼저 확정
2. `services/`의 순수 계산 함수 수정
3. `simulation_cache.py` 입력 계약 확인
4. 제외/오류 정책 확인
5. 정상·경계·누락 테스트 추가
6. 부하량부터 HOME까지 연쇄 결과 검증

### Streamlit 입력 변경

1. 편집 결과를 원본 Long Data로 복원
2. `apply_month_updates()`로 활성 시나리오 갱신
3. `revision` 증가와 `content_token` 재발급 확인
4. 다른 페이지에서 수정값 반영 확인
5. 페이지 왕복 후 입력값 유지 확인
6. **시나리오를 불러온 뒤에도 보던 탭과 조회 조건이 그대로인지 확인** — 사이드바의
   `st.rerun()` 이 페이지 본문을 건너뛰므로 `persist_state` 가 없는 위젯은 값을 잃는다
7. **새 보기 위젯은 다른 화면에 갔다가 화면 탭으로 돌아와도 남는가**(`persist_state="session"`) — 확인 체크·초안은
   남기지 않는다
8. **다른 화면으로 옮기는 새 단추·도우미는 전달 칸을 적기 전에 `refused_at_tab_limit` 을 부르는가**(9장 「팝업과
   콜백」) — 화면 링크는 `st.page_link` 로 두면 탭 줄 JS 가 막는다
9. 서버 재시작 후 유지 여부를 사용자 기대와 구분해 설명

## 13. 문서 우선순위

- 실제 동작: 현재 코드와 테스트
- 확정된 업무 결정 및 향후 항목: `docs/TODO.md`
- 사용자 설치·운영 안내: `README.md`
- 개발 구조와 에이전트 작업 규칙: `AGENTS.md`
- 직전 세션 인수인계 스냅샷: `HANDOFF.md`. 정본이 아니라 그 시점 상태의 기록이므로 위 네
  항목과 어긋나면 위를 따른다.

문서와 코드가 다르면 코드만 따라가고 끝내지 말고, 차이의 원인을 확인한 후 관련 문서를
함께 수정한다.

## 14. 병행 개발 규칙 (에이전트 둘 이상이 동시에 일할 때)

이 저장소는 한동안 **에이전트 하나가 교대로 이어받는 것**을 전제로 쓰여 왔다(「직전 세션」·
「이어받는다」 같은 표현이 그 흔적이다). 둘 이상이 **동시에** 일하면 그 전제가 깨진다. 이
장은 그때만 적용된다.

**처음 들어오는 에이전트는 [`docs/parallel_agent_briefing.md`](docs/parallel_agent_briefing.md)
를 먼저 읽는다** — 시작하는 법과 하루의 흐름이 거기 있다. 이 장은 규칙의 정본이다.

가장 위험한 것은 git 이 충돌을 알려 주는 자리가 아니라 **깨끗이 합쳐진 뒤에 깨지는** 자리다.
그런 자리는 사후 수습이 불가능하거나 매우 비싸므로 **미리 나눠 갖는 규칙으로만** 막는다.
각 규칙 끝에 그것을 잡아 주는 검사를 적었다 — **「검사 없음」이면 글로만 있는 규칙이라
사람이 지켜야 한다.**

### 14-1. 자기 작업 폴더 밖을 건드리지 않는다

각 에이전트는 `git worktree` 로 만든 자기 폴더 안에서만 일한다. 통합용 `main` 폴더에는
들어가지 않는다.

**폴더는 `scripts/new_worktree.ps1` 로 만든다.** 브랜치·`uv sync`·격리 확인을 한 번에 하고,
격리가 깨지면 폴더를 지우지 않고 멈춘다.

```powershell
./scripts/new_worktree.ps1 -Branch cand/<과제>/<에이전트> -Port 8502
```

이 스크립트와 아래 `run.ps1` 은 Windows(PowerShell) 전용이다. 사외 개발이 데스크탑 WSL 하나가 된
뒤(2026-10-13) **WSL 에서 병행 작업 폴더를 어디에 둘지(사용자 결정 대기, `docs/wsl_dev_environment.md`
6장)와 `run.ps1` 없이 포트를 어떻게 고정할지는 아직 정하지 않았다** — 그때까지 이 장의 폴더·포트
절차는 Windows 기준이다.

- **`.venv` 를 공유하지 않는다.** editable 설치가 `__editable__.capa_simulation-0.1.0.pth` 에
  **절대경로**를 박아 두어, 남의 `.venv` 를 쓰면 화면은 내 코드인데 `import capa_simulation`
  은 남의 `src/` 를 읽고 **남의 DuckDB 를 연다.** 그런데 `pytest` 는 `pythonpath = ["src"]`
  로 자기 폴더를 보므로 **검증 4종이 전부 초록이다.** 아무 신호도 뜨지 않는 사고다.
  폴더마다 `uv sync` 로 제 `.venv` 를 만든다.

  **이것만은 기계가 잡는다** — `scripts/check_worktree_isolation.py` 가 가상환경·editable
  경로·실제 import 되는 패키지·DuckDB 경로 넷을 보고 하나라도 폴더 밖이면 0 이 아닌 값으로
  끝난다. 일을 시작하기 전과 올리기 전에 한 번씩 돌린다.

  Windows(PowerShell):

  ```powershell
  .\.venv\Scripts\python.exe scripts\check_worktree_isolation.py
  ```

  WSL(bash):

  ```bash
  .venv/bin/python scripts/check_worktree_isolation.py
  ```

  **`pytest` 로 만들지 않은 이유**가 이 규칙의 핵심이다. 남의 `.venv` 를 쓴 상태에서 실제로
  재 보면 격리 검사는 네 줄 모두 `!!` 로 종료코드 1 을 내는데 **같은 상태에서 `pytest` 는
  14개 전부 통과하고 종료코드 0** 이다 — 테스트는 `pythonpath = ["src"]` 로 제 폴더를 보기
  때문이다. 검사하려는 바로 그 상황을 테스트가 못 본다. 경로 주입이 없는 맨 인터프리터로
  돌려야 한다.
- **포트는 에이전트마다 고정이다.** main 8501 · claude 8502 · codex 8503. 빠뜨리면 두 번째
  인스턴스가 찬 8501 을 피해 다음 번호(8502·8503 — 남의 예약 포트)로 **알리지 않고** 옮겨 서고,
  늘 여는 8501 은 그대로 첫 프로세스 화면이다 — 「띄웠는데 왜 내 수정이 안 보이지」가 되고 화면에
  경고가 없다. 포트를 적었는데 차 있으면 「Port N is not available」 로 멈춘다(Streamlit 1.63,
  Windows 도 같다 — `docs/internal_update_runbook.md` 4-2. 같은 8501 에 함께 붙던 것은 1.60 때
  관측이다 — `docs/TODO.md` 결정 기록, 옛 3-6).

  **손으로 지키지 않는다.** `new_worktree.ps1` 이 브랜치 마지막 조각(= 에이전트 이름)에서
  포트를 정해 `run.ps1` 에 박아 두므로, 그 폴더에서는 `./run.ps1` 한 줄이면 된다. 모르는
  이름이면 **아무것도 만들지 않고 멈춘다.** 이름을 늘리려면 스크립트의 `$AGENT_PORTS` 에
  더한다.

  `run.ps1` 은 `.gitignore` 가 무시한다 — 커밋되면 그 포트가 다른 폴더와 사내까지 따라간다.
  같은 이유로 `.streamlit/config.toml` 에 포트를 적지 않는다(그 파일은 추적 대상이고 배포
  ZIP 에 실린다).

  **8501~8503 은 예약이다. 다른 용도로 쓰지 않는다.** 무언가를 재려고 시험용 앱·데모·
  샘플을 띄울 때는 **8510 이상**을 쓴다. 이 셋에 얹으면 먼저 뜬 쪽이 그 포트를 쥔다. 뒤에
  포트를 적고 띄운 앱은 「Port N is not available」 로 멈추고, 포트를 빠뜨린 앱은 다음
  번호(남의 예약 포트)로 말없이 옮겨 앉는다. 그래서 사용자가 8501 에서 보는 화면, 다른
  에이전트가 8502·8503 에서 보는 화면, 띄운 줄 알고 연 시험 화면이 **말없이 남의 것**이 된다.
- **`git stash` 를 쓰지 않는다.** 스태시·태그·브랜치는 세 폴더가 **공유**한다. 한쪽의
  스태시가 다른 쪽에 보인다.
- **배포 ZIP 은 `main` 폴더에서만 만든다.** 빌더는 자기 위치의 작업트리를 읽고 그 HEAD 에
  태그를 박는다. 후보 브랜치에서 만들면 미채택 코드가 사내 정본으로 나가고 태그가 엉뚱한
  커밋에 박힌다. 빌더는 HEAD 가 `origin/main` 과 다르거나 추적 파일에 커밋하지 않은 수정이
  있으면 멈추므로(2026-10-13, `--no-tag` 시험 빌드는 알리기만 한다) 후보 브랜치의 커밋으로는
  태그를 단 배포 ZIP 이 만들어지지 않는다.

`scripts/check_worktree_isolation.py` 가 **`.venv` 공유**를, `new_worktree.ps1`+`run.ps1` 이
**포트**를, 빌더가 **배포 ZIP 의 출처**를 잡는다. 남은 하나(스태시)는 사람이 지킨다.

### 14-2. 브랜치·저작자·충돌

- 브랜치 이름은 `cand/<과제>/<에이전트>` 다 — 예: `cand/home-legend/claude`.
  사람이 만든 `feat/`·`fix/` 와 목록에서 갈린다.
- **커밋 `author` 를 바꾸지 않는다.** 세 폴더가 같은 `.git/config` 를 공유해 한쪽에서
  `git config user.name` 을 바꾸면 다른 폴더까지 바뀐다. 누가 했는지는 이미 쓰고 있는
  **트레일러**(`Co-Authored-By:`)로 가른다.
- **충돌은 에이전트가 흡수한다.** 사용자에게 `<<<<<<<` 를 내밀지 않는다. 합치는 쪽이 양쪽
  의도를 읽고 푼 뒤, **무엇을 어떻게 골랐는지 한 줄로 보고**한다.

검사 없음.

### 14-3. 공유 문서는 끝에 붙이지 않는다

`AGENTS.md` 는 코드 커밋의 약 43%, `docs/TODO.md` 는 약 34% 가 함께 바뀐다. 13장이 요구하는
「같은 변경에서 문서도 갱신한다」를 둘이 동시에 지키면 **매번 충돌한다.**

- **`HANDOFF.md` 는 병행 중 편집하지 않는다.** 한 시점의 세션 스냅샷이라 둘이 쓰면 뜻이
  없어진다. 합친 뒤 통합하는 쪽이 한 번만 쓴다.
- `docs/TODO.md`·`AGENTS.md` 는 **절 단위로 소유를 나눠** 받는다. 과제를 낼 때 어느 절을
  누가 건드리는지 정한다. 문서 **끝에 새 절을 덧붙이는 것**이 가장 자주 충돌하므로, 번호를
  미리 배정받지 않았으면 새 절을 만들지 않는다.
- `README.md` 는 사용자용이라 병행 중에는 통합하는 쪽만 고친다.

`tests/test_repository_hygiene.py`·`tests/test_source_metadata.py` 가 **문서와 코드가
어긋나는 것**은 잡지만, **누가 어디를 고쳤는지**는 잡지 못한다.

### 14-4. 마이그레이션 번호는 홀짝으로 가른다

둘이 각각 `0026` 을 만들면 **git 은 깨끗이 합치고, 그다음에 앱이 시작조차 못 한다.** 적용된
마이그레이션은 버전 번호로 체크섬을 대조하므로 나중에 번호를 바꿀 수도 없다.

- 한 에이전트는 **홀수**, 다른 하나는 **짝수**만 쓴다. **배정은 브랜치 이름에서 나온다** —
  규약이 `cand/<과제>/<에이전트>` 이므로 마지막 조각이 곧 에이전트이고, 그 에이전트의 홀짝은
  `config/parallel_agents.json` 이 갖는다(포트를 정하는 것과 **같은 파일**이다. 두 곳에 각자
  적으면 에이전트를 더할 때 한쪽만 고치게 된다).
- `tests/test_migration_parity.py` 가 후보 브랜치에서 **`main` 에 없는 마이그레이션**의
  번호를 보고 배정 밖이면 실패한다. 두 마이그레이션 디렉터리는 번호가 독립이라 따로 본다.
  `main` 이나 `feat/`·`fix/` 에서는 배정 대상이 아니라 건너뛴다. 후보 폴더·`cand/**` 푸시와
  후보 PR에서 검사한다. GitHub Actions의 detached HEAD에서는 `GITHUB_HEAD_REF` 또는
  `GITHUB_REF_NAME`으로 후보를 식별하며 로컬 실행은 Git 브랜치만 본다. 비교 기준은
  `main`, 없으면 `origin/main`이다. CI 체크아웃은 **`fetch-depth: 0`**이어야 하고,
  후보 CI에서 기준이나 diff를 읽지 못하면 검증 누락을 숨기지 않고 실패한다.
- **가능하면 한 주기에 한 에이전트만 마이그레이션을 만든다.** 홀짝은 그래도 겹칠 때를 위한
  안전장치이지 권장 상태가 아니다.
- 채택되지 않은 브랜치가 번호를 이미 썼으면 **그 번호를 영구 결번으로 등록한다** — 5장의
  결번 규칙과 같은 자리에 적는다. 되돌리는 다른 방법이 없다.

`tests/test_migration_parity.py` 가 홀짝을, `tests/test_migration_numbering.py` 가 결번
재사용과 번호 중복을 잡는다.

`tests/test_migration_numbering.py` 가 번호 재사용과 결번 침범을 잡는다. **다만 두 브랜치가
각자 다른 파일에 같은 번호를 쓴 상태는 합쳐지기 전에는 잡히지 않는다.** 두 브랜치가 같은 DB 에
마이그레이션을 더했으면 둘 다 `tests/test_migration_checksums.py` 체크섬 표 끝에 줄을 더하므로 합칠
때 git 이 거기서 충돌을 낸다 — 번호가 같으면 거기서 드러나고, 다르면 두 줄을 번호 순으로 남긴다.

### 14-5. 단일 선언 지점은 한 주기에 한 에이전트만

이 저장소는 「한 곳에서만 선언한다」가 많다. 병행에서는 그 미덕이 그대로 충돌면이 된다.

- `src/capa_simulation/navigation.py` 의 `SIDEBAR_GROUPS` — 새 화면을 만들면 **반드시** 여기서
  만난다.
- `src/capa_simulation/design/tokens.py`
- `config/data_contract.json`
- `src/capa_simulation/services/frame_contracts.py`
- `tests/test_repository_hygiene.py` 의 `ALLOWED_TOP_LEVEL`

**세션 상태·위젯 `key` 는 네임스페이스가 없고, 겹쳐도 예외가 나지 않는다** — 화면 사이로
상태가 조용히 샌다. 한쪽에서 고른 값이 다른 화면에 나타나거나, 한쪽이 위젯을 만들면서
다른 쪽이 넣어 둔 값을 덮는다.

**이제 기계가 잡는다.** `tests/test_session_key_collisions.py` 가 키를 만드는 자리 셋을
모두 보고, 같은 값을 두 모듈이 만들면 실패한다.

1. 위젯의 `key="..."`
2. `*_KEY` 로 끝나는 모듈 최상위 문자열 상수 — 이 저장소가 **공유 키를 선언하는 방식**이다
3. `st.session_state["..."] = ...` 와 `.setdefault("...", ...)` — 위젯이 없어 충돌해도
   경고할 상대조차 없는 자리다

읽기는 보지 않는다. 남이 만든 키를 읽는 것은 충돌이 아니라 공유 상수가 있는 이유다.
f-string 키는 넘겨받은 기준 키에서 파생되므로 그 기준 키가 대신 갈린다.

키를 **공유해야 하면** 소유한 모듈에 `*_KEY` 상수를 두고 나머지는 import 한다. 문자열을
두 곳에 적는 것이 곧 겹침이다.

접두(`<페이지명>__`)는 **권고**다. 겹침을 애초에 쓰지 않게 하고 키를 읽기 쉽게 하지만,
지금 저장소의 키 163개가 그 꼴이 아니고 검사도 강제하지 않는다 — 강제하는 것은 위 겹침
검사다.

앞의 다섯 파일은 텍스트 충돌이라 git 이 알려 준다.

### 14-6. 올리기 전과 합친 뒤, 두 번 검증한다

- 후보 브랜치를 올리기 전에 **자기 폴더에서** 검증 4종을 돌린다.
- 합친 뒤 **통합 폴더에서 한 번 더** 돌린다. 각 브랜치에서는 초록인데 합치면 빨개지는
  자리가 있다 — 위생 검사 3종이 대표적이다(한쪽이 문서를 지우고 다른 쪽이 그것을 가리키는
  링크를 더하면 둘 다 자기 브랜치에서는 통과한다).
- 에이전트의 **「검증 통과했습니다」를 그대로 믿지 않는다.** CI 가 붙어 있으면 PR 의 체크
  표시가 근거이고, 없으면 통합하는 쪽이 직접 돌린 결과가 근거다.

`.github/workflows/ci.yml` 이 **후보 브랜치(`cand/**`) 푸시**·PR·`main` 푸시에서 검증 4종을
돌린다. 후보를 올리는 즉시 도므로 PR 을 열기 전에도 초록·빨강이 보인다. **저장소는
public 이고(2026-10-03 유지 결정) `main` 에 브랜치 보호를 걸지 않아 「통과해야만 병합」은 강제되지
않는다** — 빨간 것은 합치지 않는다는 규칙을 사람이 지킨다.
