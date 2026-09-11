# Capa Simulation 개발 에이전트 가이드

이 문서는 저장소 전체에 적용되는 개발 인수인계 문서다. 작업을 시작하기 전에
`README.md`, 이 문서, `docs/TODO.md`를 읽고 실제 코드와 함께 현재 상태를 확인한다.
구조나 핵심 계산 규칙을 변경하면 이 문서와 README도 같은 변경에서 갱신한다.

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
매핑도 커밋을 마쳤다. 남은 것은 사내 환경에서의 접속·조회 검증이다.

GitHub 소스만 있는 빈 환경에서는 `config/bootstrap_display_order.json`과 코드로 생성한
비민감 `DEMO_*` Core Data를 공통 변환 파이프라인에 넣어 초기 시나리오·리비전·공식버전을
자동 생성한다. 기존 시나리오나 공식버전은 자동 시드가 변경하지 않으며 내장 시드는 운영
기준정보가 아니다. 실제 표시순서는 시나리오와 분리된 공용 DB 프로필이며, 선택적 로컬
`data/input/RQ_DISPLAY_ORDER.csv` 또는 웹 Excel 표 붙여넣기로 초기화할 수 있다.

## 2. 실행환경과 검증 기준

- 운영 호환 Python: **3.10.11 64-bit**
- UI: Streamlit 멀티페이지 앱
- 데이터 처리: pandas
- 차트: Plotly
- 초기 이관·병행 검증용 Excel 읽기: xlwings, Workbook 숨김·읽기 전용
- 타입 검사: mypy strict
- 린트/포맷: Ruff, target Python 3.10
- 테스트: pytest

변경 후 기본 검증 명령:

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest
```

`mypy`는 `pyproject.toml`의 `files` 설정에 따라 `app.py`·`app_pages/`·
`src/capa_simulation/`만 검사한다. `tests/`와 `scripts/`는 타입 검사 범위 밖이다.

Codex에서 `.venv\Scripts\python.exe`를 샌드박스 안에서 실행하면 가상환경이 참조하는
사용자 프로필의 Python 3.10 실행 파일 접근이 차단되어 `Unable to create process` 또는
`Access is denied`가 발생할 수 있다. 이는 가상환경 손상이 아니므로 `.venv`를 재생성하지
말고 동일한 명령을 `require_escalated`로 다시 실행한다. Streamlit 버전별 스킬 탐색기도
프로젝트 `.venv`와 탐색기 스크립트의 정확한 조합으로 승인된 샌드박스 외 실행을 사용한다.

Streamlit 페이지나 상태를 변경했다면 `streamlit.testing.v1.AppTest` 또는 실제 브라우저로
해당 페이지 진입, 수정, 페이지 왕복과 예외 여부를 추가 검증한다.

## 3. 파일별 책임

### 실행과 UI

- `app.py`
  - 유일한 실행 진입점이다.
  - `st.navigation` 페이지 목록을 독립 `Capa Chatbot`·`시나리오 관리`, `Static Capa`와
    `Dynamic Capa` 상위 영역으로 구분하고 공통 사이드바와 조회기간을 관리한다.
  - `시나리오 관리`는 Capa Chatbot과 Static Capa 사이의 독립 사이드바 그룹에 배치한다.
  - 모든 페이지에 필요한 전역 위젯은 `navigation.run()`보다 앞에 둔다.
  - 새 세션은 최신 공식 리비전을 전역 위젯 생성 전에 활성화하고, 사이드바에는 시나리오·
    리비전 선택, 명시적 불러오기, 현재 편집본의 신규 리비전 저장과 활성·공식·미저장 상태를
    제공한다. 이름 변경·공식 발행·삭제·신규 시나리오 생성은 독립 관리 페이지에 둔다.
  - 시나리오 저장소가 완전히 비어 있으면 최신 공식 리비전 활성화 전에 내장 합성 시드를
    생성·공식 발행한다.
- `app_pages/home.py`
  - 전체 계산 결과를 조합하는 HOME 대시보드다.
  - Plotly Figure 묶음을 사용자 세션에 캐시하고 렌더링은 fragment로 분리한다.
  - 본문은 `Main`·`Preference` 두 탭이다. `Main` 이 계획·LOB·B/N Figure 여섯 개를 그리고
    `Preference` 가 표시 기준(EDP 포함 여부·선행 투입 물량)을 받는다. 요약만 그리는 경로는
    없다 — 여섯 개를 항상 만든다.
  - **두 토글의 값은 계산보다 먼저 필요하고 위젯은 계산 뒤에 그려진다.** 페이지가
    `components/home_preference.py` 의 세션 키를 직접 읽고 위젯은 같은 키로 만든다. 키
    문자열을 두 곳에서 따로 적으면 조용히 끊어지므로 상수로 내보낸다.
  - `EDP 포함` 을 끄면 **LOB 로 표현되는 값만** EDP 를 뺀다. `확보율 × 부하량` 꼴로 나오는
    값(Density·Wafer 계획·Wafer Capa·B/N Capa 막대·Top 5·상세 B/N 의 Wafer Capa)과 계획
    세부수량 행이 대상이다. 소요대수·확보율·B/N 공정 순위는 **바뀌지 않는다** — 설비가 받는
    부하는 EDP 를 포함한 전체 계획이다. 그래서 설비 수요를 다시 돌리지 않고
    `get_home_lob_without_edp` 로 부하량 쪽만 다시 만든다.
  - `계획 세부수량 상세` 를 켜면 제품·Stack 아래에 `Customer` 를 분류로 더한다. `Customer`
    는 `RQ_PKG_PLAN` 의 1급 컬럼이라 조인이 아니라 묶는 키 하나가 늘어나는 것뿐이다.
    머리글과 칸 폭은 `DETAIL_DIMENSION_HEADERS`·`DETAIL_DIMENSION_WIDTHS` 에서 끌어오므로
    분류가 늘어도 Figure 에서 다시 적을 것이 없다. 기본 조합이 아닌 경우에만
    `get_home_plan_detail` 이 돌아 토글을 건드린 사람만 계산을 치른다.
  - `GAP` 을 켜면 Preference 에서 고른 비교 시나리오 대비 증감을 Density·Wafer 계획·계획
    세부수량 값 **아래**에 적는다(선행 증감은 값 **위**). 비교 대상은 시나리오와 리비전을
    함께 골라 정하고, 그 리비전에서 **계획만** 가져오고 환산에 쓰는 표는 현재 것을 쓴다 — 수율·Chip 기준정보가
    바뀐 것은 계획 변동이 아니다. 비교 시나리오에만 있는 분류 조합도 행으로 남긴다.
  - 위아래 GAP 이 함께 붙는 칸만 값 글자를 한 단계 더 줄인다. 행 높이는 어느 경우에도
    바꾸지 않는다 — 행마다 높이가 달라지면 왼쪽 라벨 칸과 월 칸의 행이 어긋난다.
  - `선행` 을 켜면 공용 선행 물량으로 변동률을 내 계획·확보율에 건다. 변동률은 **화면이
    지금 쓰는 계획** 기준이다(EDP 를 뺀 화면이면 뺀 계획). 그래야 어느 상태에서든 Capa 가
    그대로이고 Density 증감이 입력값과 정확히 같다.
  - 제목 아래 설명 문구, `계획·B/N 상세표 표시` 토글, `계획 세부수량 CSV` 는 탭이 그 자리를
    쓰면서 없앴다.
  - 본문 맨 위, 탭 위에 `LoadingProgress` 막대를 둔다. 계산 단계마다 `advance()` 하고
    끝나면 `close()` 한다. **모든 종료 경로가 `close()` 를 지나야 한다** — 오류로 멈추면
    멈춰 선 막대가 오류 문구 위에 남는다. Figure 캐시 적중 경로는 건너뛴 단계 수만큼
    `advance()` 를 더 불러 두 경로의 단계 수를 맞춘다.
  - B/N 임계값과 포함 공정은 사이드바 form 제출 시 한 번에 적용하고, 성능 진단 토글은
    단계별 시간과 Figure 캐시 적중 여부만 표시한다.
- `app_pages/load_conversion.py`
  - `환산`, `PKG PLAN`, `수율`, `제품 등록` 탭을 제공한다. 제품 등록은 기존 제품의 기준정보 8표를
    새 제품 키로 복제하는 가상 제품 등록이다(`services/virtual_product.py`).
  - 계획과 수율 편집값을 활성 시나리오에 반영한다.
  - PKG PLAN과 수율의 현재 월별 Wide 표를 CSV로 내려받아 값만 일괄 수정·적용한다.
- `app_pages/capacity_standards.py`
  - 기본 `공정 유효 Capa`는 중복되지 않은 원수요 부하량을 STEP별 소요대수 합계로 나눈
    화면용 결과이며, STEP별 상세 대당 Capa와 공정 필터도 제공한다. `공정 유효 Capa`는
    집계값이라 공정 미선택이면 전체를 그린다.
  - `STEP별 대당 Capa`는 **공정을 선택해야 그린다.** 미선택이면 표·CSV·안내 문구를 모두
    감추고 공정을 고르라는 안내만 남긴다 — 경로 하나하나가 행이라 전 공정을 그리면 표 생성·
    정렬·CSV 인코딩·Plotly 조립이 모두 행 수에 비례해 커진다. 그래서 필터를 앞으로 당기는
    것이 아니라 그 계산 자체를 타지 않는다. 공정 필터 placeholder 도 뷰에 따라 달라진다.
  - `STEP 구성`은 선택한 경로를 실제 MCP·STEP 식별값으로 복제하거나 삭제하고 연결된
    모든 Capa Code·Customer·CS 변형을 `RQ_REQB`·UPEH·Lot/WF 측정률에 함께 반영한다.
  - 확보율 계산용 상세 대당 Capa는 변경하지 않고 UPEH·효율·여유율·측정률·일수 편집 탭을 제공한다.
  - 편집 탭 여섯 개에는 그 탭의 분류 컬럼 필터가 붙는다. **필터는 보기만 좁히고 적용은 표
    전체를 저장한다** — 자세한 계약은 `components/month_editor.py` 항목에 있다.
  - 대형 월별 편집기는 상태 추적 탭으로 구성해 선택된 탭만 렌더링하며, 탭 전환 시 rerun한다.
- `app_pages/process_securement.py`
  - `확보율`, `소요대수`, `설비대수` 탭을 제공한다.
  - 설비대수 탭에서 보유·대여·가용 RQ를 각각 월별 Wide CSV로 내려받고 활성 시나리오에
    일괄 적용한다.
- `app_pages/capa_chatbot.py`
  - 활성 시나리오의 Capa 데이터 조회와 부족 공정 분석을 위한 대화형 화면 초안이다.
  - LLM API·업무 데이터·권한·대화 이력은 연결하지 않고 추천 질문, 채팅 입력, 답변 범위와
    근거 표시 구조만 제공한다.
- `app_pages/static_capa.py`
  - `Static Capa` 상위 페이지이며 경고·확보 기준별 월간 설비 부족대수 현황을 제공하고
    부하량·공정별 Capa·공정별 확보율·표준 목표 Capa 하위 기능은 사이드바 탐색으로만
    제공한다.
  - 경고 기준 미달 행은 경고 기준까지 필요한 대수와 확보 기준까지의 추가 대수를 함께
    표시하고, 경고 이상·확보 기준 미달 행은 확보 기준 추가대수로 별도 관리한다.
  - 상단 안내는 기준정보 기반 부족대수를 Total 설비 부족 투자(GO팀)와 투자 후 가용 일정
    미확보에 대한 Setup 단축·생산성 향상(기술팀)으로 분기하는 업무 로드맵을 설명한다.
- `app_pages/reference_integrity.py`
  - `Dynamic Capa (구현중)` 상위 페이지이며 전체 공정 실현률·관리 우선순위를 요약하고 공정·제품·
    Stack·WF 속성 필터로 표준/실효/실적 Capa와 손실 원인을 비교하는 프로토타입을 제공한다.
  - 상단 용어 가이드는 표준·효율 반영·실효·모델 실적 Capa 단계, 실현률·활용률과
    효율·UPEH·기타 정합성 Gap의 산식과 부호 해석을 제공한다.
  - 상단 업무 안내는 Rundown 감소·재공운영(제조팀)과 UPEH·효율 실적 개선(기술팀)으로
    이어지는 Dynamic Capa 활용 로드맵을 설명한다.
  - 현재 수치는 결정론적 데모다. 가용설비 현황·효율 실적·UPEH 실적·Space 현황은 본문
    바로가기를 두지 않고 사이드바의 `Dynamic Capa` 하위 페이지로만 제공한다.
- `app_pages/available_equipment_status.py`
  - `대시보드`, `설비 데이터·이력 관리` 탭을 제공한다.
  - 기존 보유대수, Qual 확정상태를 포함한 30컬럼 호기 마스터와 운영 비가동 일정을 DuckDB 불변 리비전으로
    저장하고 공정소분류별 주차 단위 총대수·가용대수·비가동대수와 상태를 집계한다.
  - 대시보드 조회 조건은 라인구분·활용구분·공정대분류·공정소분류 순으로 제공하며,
    집계형 기존 보유대수에는 공정소분류 조건만 적용한다.
  - 세 표 모두 CSV 양식 내려받기와 Excel 붙여넣기 Import를 지원한다. 기존 보유대수는
    공정·분류, 호기 마스터는 호기, 비가동 일정은 호기·유형·시작일 자연키로 Import하며
    신규·대체·변경 컬럼 미리보기와 편집본 적용 확인 후 별도로 리비전을 저장한다.
  - 세 입력 표는 각자 draft 세션키를 갖고, 대시보드도 저장본이 아니라 draft 를 본다.
    씨뿌리기는 `DRAFT_REVISION_KEY` 가 활성 리비전과 다를 때만 세 키를 한꺼번에 채우므로,
    **표를 더하면서 그 키 이름을 올리지 않으면** 이미 열려 있던 세션이 블록을 건너뛰고
    새 draft 키 첨자 접근에서 `KeyError` 로 죽는다. 입력 표를 더하면 키 이름을 올린다.
  - Import 확정 시에는 해당 `*_EDITOR_KEY` 를 반드시 `pop` 한다. `st.data_editor` 의 세션
    상태는 값이 아니라 **행 인덱스 기준 delta** 라, 남은 옛 delta 가 새 프레임 위에 다시
    얹히면 Import 가 조용히 되돌려진다.
  - 데이터·이력 관리 탭의 접힌 운영 지침에서 기존 보유대수·호기 마스터·비가동 일정의
    역할 구분, Import부터 리비전 저장까지의 절차와 적용 제한을 안내한다.
  - 시뮬레이션 DB, 활성 시나리오, `RQ_*` 기준정보와 공통 시뮬레이션 조회기간을 읽지 않는다.
- `app_pages/actual_efficiency.py`, `app_pages/actual_upeh.py`
  - Dynamic Capa의 실적 비교·개선관리 하위 페이지다.
  - 분석 현황, 기준 대비 Gap, 공정·제품 개선 우선순위와 개선과제 관리 화면 초안을 제공한다.
  - 실제 생산이력 DB와 `RQ_RUN_RATE`·`RQ_UPEH` 기준정보 연결은 아직 구현하지 않는다.
- `app_pages/wip_status.py`
  - Dynamic Capa의 `표준 대비 재공 현황` 하위 페이지다.
  - 오늘 기준 -7일~+3일의 공정·제품·STEP별 보유 재공·유입·Flow 샘플과 제품별 일 표준
    가능량을 비교하며, 공정·제품 필터와 STEP 열·제품 행 Plotly 격자를 제공한다.
  - 재공 값은 결정론적 데모이고 실제 재공 실적 DB 조회·원천 컬럼 매핑은 아직 구현하지 않는다.
- `app_pages/space_status.py`
  - Dynamic Capa의 Space 현황 페이지다.
  - `FAB 전체(C5 독립, C1~C4 연결) → 동별 층 → 층 상세 배치`의 3단계 Plotly 클릭 탐색을 제공한다.
  - 가용설비 현황의 최신 호기 리비전을 사용하고 설비별 X/Y 좌표와 X/Y 크기로 배치한다.
  - 기준일의 생애주기 상태와 운영 비가동을 색으로 구분한다. 실제 층 이미지와 Space
    Capa 연결은 미구현이다.
  - 지정 기간의 단계 완료일을 호기별 전환 이벤트로 펼쳐 완료·예정 건수, 이전·전환 단계,
    전환일과 기준일 대비 일수를 조회하는 실행관리 현황을 제공한다.
- `app_pages/admin_area.py`
  - 사이드바 맨 아래 자기 박스에 있는 관리 화면이다. 화면 표기·정렬순서 같은 운영 관리
    설정을 탭으로 모은다. `Proc Rename` 과 `표시순서 관리` 두 탭이다.
  - 거래선 정렬은 따로 만들지 않는다. `표시순서 관리` 에 `분류컬럼 = Customer` 규칙을
    `부하량`·`PKG PLAN` 범위로 넣으면 걸린다 — `apply_display_order` 는 데이터에 없는
    분류컬럼 규칙을 건너뛰므로 같은 규칙이 `계획 세부수량 상세` 를 끈 화면에서는 아무
    일도 하지 않는다.
    조회 컨트롤과 떨어뜨린 관리 기능이지만 이미 쓰는 화면이라 `(구현중)` 을 달지 않으며,
    그룹 제목이 아니므로 사이드바 글꼴도 하위 페이지와 같다.
  - `load_page_context()` 를 부르지 않는다. 계산이 없어 표시순서 준비·활성 시나리오
    물질화 비용과 부작용을 지불할 이유가 없고 조회기간도 쓰지 않는다. 저장소만 확보한다.
  - 보유 공정 목록은 안내·편집 보조라 활성 시나리오가 없으면 빈 목록으로 낮추고
    화면을 멈추지 않는다. 공용 표시명 저장 자체는 시나리오와 무관하다.
  - 나중에 관리자 권한으로만 열도록 제한할 자리다. 지금은 숨김 플래그를 두지 않는다.
- `app_pages/scenario_management.py`
  - `시나리오 관리`·`BigDataQuery 등록` 두 탭을 제공한다. `표시순서 관리` 는 운영 관리
    설정이라 Admin Area 로 옮겼다. 두 탭은 항상 그린다(열린 탭만 그리면 다른 탭을 여는 순간 form 입력값이 사라진다). `BigDataQuery
    등록` 탭에 시뮬레이션 코드 목록 표가 생겼지만 그 표는 세션에 담긴 조회 결과를 표시만
    하고 사내 DB 조회는 버튼 제출로만 돈다 — 다시 드는 비용이 좁힌 뷰의 직렬화뿐이라
    탭 전환에 rerun 을 걸지 않는다.
  - `BigDataQuery 등록` 은 ① 기간으로 시뮬레이션 코드 목록 조회 → ② 목록에서 한 행 선택
    → ③ 자동 입력된 등록 폼 확인·저장의 2단계다.
  - 작업은 「목록 관리」·「현재 활성 RQ 복제」·「리비전 저장」 셋이다.
  - 「목록 관리」가 시나리오를 다루는 단일 입구다. 누적 목록 표에서 한 건을 체크한 뒤
    불러오기·이름 수정·공식버전 지정·삭제를 그 한 건에 대해 수행한다. 표의 `순서` 칸을
    고쳐 저장하면 누적 순서를 다시 매긴다(`scenario.list_order`). 두 건 이상 체크하면
    작업 칸을 열지 않는다.
  - 시나리오 삭제는 물리 삭제다. 목록에서만 숨기는 보관 상태는 없다. 지울 표는
    `information_schema` 에서 소유 컬럼(`scenario_id`·`dataset_id`·`revision_id`)으로
    찾으므로 새 표가 생겨도 목록을 고칠 필요가 없다. 되돌릴 수 없으니 시나리오명을 그대로
    입력해야 실행 버튼이 열린다.
  - 신규 시나리오는 현재 활성 RQ 16개를 독립 데이터셋으로 복제해 만든다. 개발용 Core Data
    CSV 를 원천으로 삼는 저장은 `BigDataQuery 등록` 이 대체했다.
  - BigDataQuery로 새 원천 시나리오를 만들 때 초기 프리셋은 원천의 전체
    생산계획년월, 전체 B/N 공정과 전체 표준 목표 Capa 공정을 기본 조회 범위로 사용한다.
    현재 활성 화면의 축소 조회기간이나 공정 제외 상태, 표준 목표 Capa 조회·집계 설정을
    새 원천에 복사하지 않는다.
  - 새 리비전은 편집 가능한 14개 RQ와 사이드바 프리셋의 전체 스냅샷을 저장한다.
  - 표시순서는 시나리오와 분리된 공용 DB 프로필로 저장하며 전체 CSV 양식 다운로드·
    Excel 표 붙여넣기와 페이지·탭 범위별 직접 편집·충돌 검증을 제공한다.
- `app_pages/standard_target_capa.py`
  - Static Capa 하위에서 월간 공정 유효 Capa를 일 단위로 환산하고 주차별 가용대수를
    적용한 일 표준 가능량을 제공한다.
  - 조회일·공정 필터·상세 토글, 수동 가용대수 CSV 양식 다운로드·Excel 표 붙여넣기와
    `일 표준 가능량`·`대당 일 Capa`·`가용대수` 전환 Plotly 표를 제공한다. `로직 분석`은
    Weeknum·공정·소요기준·양산·제품·Stack·WF 속성을 모두 선택한 경우에만 공정·주차
    한 건을 계산하고 제품·WF 속성별 부하량 비중·소요대수 비중과 조화가중 근거를 표시한다. ER은 항상
    제외하고 상세 OFF는 제품 Mix를 반영한 공정 단일값, ON은 선택한 제품 분류를 표시한다.
  - `일 표준 가능량`의 `PKG 기준` 토글은 동일 Mix의 중복 없는 PKG PLAN 합계와 원수요
    투입 Unit 부하량 비율로 결과를 PKG Kea로 역산하며 화면 표와 CSV에 함께 적용한다.
  - 공정 필터와 「조회·집계 설정」(시작일·종료일·상세 토글·제품 분류 수준·출력 지표)은
    리비전에 공용 기본값으로 저장하되 페이지 변경은 사용자 세션에만 적용한다.
    현재 선택을 신규 리비전으로 저장하면 다음 공용 기본값이 되며 빈 목록은 전체 공정이다.
    저장된 조회일이 현재 사이드바 조회기간 밖이면 오류 대신 범위 안으로 맞추고 한 줄 알린다.
    상세 토글이 꺼져 제품 분류 수준 위젯이 화면에 없어도 마지막 선택을 그대로 저장한다.
  - 수동 가용대수는 설비 DuckDB에 공정·Weeknum 최신값으로 즉시 저장하되 리비전을
    만들지 않으며, 향후 가용설비 현황 DuckDB 산출 조회로 입력 경계를 교체한다.
  - 페이지 하단의 접힌 `예외 처리 공정`에는 표준 목표 Capa에만 적용되는 공정별 제외
    조건과 현재 조회범위에서 제외된 상세 행 수를 표시한다.
- `src/capa_simulation/components/reference_csv_tools.py`
  - 입력 RQ 월별 Wide 표의 UTF-8 CSV 양식 다운로드·Excel 표 붙여넣기 폼과 적용 결과
    알림을 공통 제공한다.
- `src/capa_simulation/components/horizontal_scrollbar.py`
  - HOME 월별 영역과 동기화되는 픽셀 단위 커스텀 가로 스크롤바를 제공한다.
  - 네이티브 스크롤바가 아닌 Streamlit Custom Components v2로 구현한다.
- `src/capa_simulation/components/month_range_picker.py`
  - 공통 사이드바의 시작·종료 월 선택기를 제공한다.
  - 브라우저 네이티브 `input[type="month"]`를 Streamlit Custom Components v2로 연결한다.
  - 출력은 기존 전역 상태 계약인 `production_month_range_v2 = (YYYY-MM, YYYY-MM)`에 반영한다.
- `src/capa_simulation/components/scenario_status.py`
  - 모든 페이지에 공통인 사이드바 시나리오·리비전 선택, 명시적 불러오기와 현재 활성
    편집본의 신규 리비전 저장을 제공한다. 드롭다운 선택만으로 계산 상태를 바꾸지 않으며,
    미저장 편집을 버리는 불러오기는 확인 입력을 요구한다. 이름 변경·공식 발행·삭제·신규
    시나리오 생성은 독립 `시나리오 관리` 페이지에서 수행한다.
- `src/capa_simulation/components/space_layout.py`
  - FAB 동·층 정의, 설치 단계·양산·운영 비가동 집계와 3단계 Plotly Figure를 생성한다.
  - 층 상세 캔버스는 층마다 다르다. `equipment_ops.floor_layout_profile` 에 저장된
    폭·높이를 쓰고, 프로필이 없는 층만 기본값 100×60 이다. 배경 도면은
    `background_image` 인자로 받아 `add_layout_image` 로 깐다.
  - `invalid_equipment_rows` 도 같은 층 캔버스를 기준으로 이탈을 판정한다. 상수를
    다시 박으면 도면 비율을 바꾼 순간 멀쩡한 호기가 오류로 찍힌다.
- `src/capa_simulation/components/floor_layout_upload.py`
  - Space 현황의 동·층별 배경 도면 업로드·삭제와 캔버스 치수 조정 UI.
    도면 없이 캔버스만 저장할 수도 있다. 캔버스를 줄여 이탈 호기가 생기면 확인
    체크박스를 통과해야 저장한다 — 이탈이 있으면 `save_snapshot` 이 마스터 프레임
    전체를 거부해 무관한 동·층 편집까지 막히기 때문이다.
- `src/capa_simulation/components/dynamic_capacity_dashboard.py`
  - Dynamic Capa 전체 공정 비교, Capa 손실 Waterfall과 일별 표준·실효·실적 추이 Figure를
    생성한다. 공정 간 단위가 다르면 수량을 합산하지 않고 비율만 비교한다.
- `src/capa_simulation/components/wip_status_dashboard.py`
  - 제품을 행, `P → T`와 숫자 구간 오름차순 STEP·공정을 열로 두는 고정 셀 크기의
    Plotly 재공 격자를 생성한다. 보유 재공·유입·Flow 막대와 표준 가능량 기준선을 표시한다.
- `src/capa_simulation/components/grouped_monthly_table.py`
  - 환산 결과처럼 편집하지 않는 월별 표를 Plotly의 고정 분류 영역과 스크롤 월 영역으로 렌더링한다.
  - 정렬된 분류 컬럼을 계층적으로 그룹화하고 제품·양산구분별 Total을 그룹 하단에, 전체 합계를 첫 데이터 행에 삽입한다.
  - 제품·양산구분 그룹의 음영과 경계는 계산 원본을 변경하지 않고 동적으로 계산한다.
  - 화면과 같은 분류·부분합 구조를 유지하는 CSV 다운로드용 DataFrame을 생성한다.
- `src/capa_simulation/components/hierarchical_monthly_table.py`
  - 대당 Capa·확보율·소요대수처럼 합계행이 없는 월별 결과를 고정 분류 영역과 스크롤 월 영역으로 렌더링한다.
  - 반복 분류값 생략, 계층별 행 경계, 월·분기별 열 경계와 외곽 테두리를 동적으로 적용한다.
  - 숫자와 퍼센트 표시 모드를 지원하되 계산 원본 값은 변경하지 않는다.
  - 대용량 상세표는 페이지 단위 렌더링으로 브라우저 부하를 제한한다.
  - 화면과 같은 반복값 생략·표시 라벨·월 표기를 유지하는 CSV 다운로드용 DataFrame을 생성한다.

페이지 파일은 직접 실행되는 Streamlit 스크립트 형태를 유지한다. 복잡한 계산을 페이지에
추가하지 말고 `src/capa_simulation/services/`로 옮긴다.

### 입력과 상태

- `src/capa_simulation/application_bootstrap.py`
  - 공식버전이 있으면 그대로 사용하고, 완전히 빈 시나리오 저장소에만 내장 시드를 생성한다.
  - 내장 시나리오 생성 뒤 공식 발행 전에 중단된 상태는 다음 시작에서 발행만 복구하며,
    공식버전 없는 사용자 시나리오는 임의 발행하지 않는다.
- `src/capa_simulation/services/builtin_seed.py`, `config/bootstrap_display_order.json`
  - GitHub 독립 실행용 78컬럼 합성 Core Data와 비민감 최소 표시순서를 제공한다.
  - `data/input/RQ_DISPLAY_ORDER.csv`가 있으면 최초 공용 표시순서 이관에 우선 사용하되
    해당 로컬 CSV는 Git과 일반 배포 소스에 포함하지 않는다.
  - CSV·BigDataQuery와 같은 정규화·RQ 16개 변환·typed raw 저장 경로를 사용하며 모든
    업무 식별값은 `DEMO_*`로 명확히 구분한다.

- `src/capa_simulation/io/excel_reader.py`
  - 초기 이관·병행 검증 도구에서 16개 `RQ_*` Excel Table을 DataFrame으로 읽는다.
  - 앱 런타임에서는 사용하지 않으며 Power Query도 새로고침하지 않는다.
- `src/capa_simulation/io/core_data_source.py`
  - CSV와 사내 DB 조회 결과가 공유하는 78컬럼 DataFrame 계약, nullable 타입 정규화,
    원천·행·스키마 해시와 컬럼 프로파일을 제공한다.
  - CSV 어댑터는 외부 개발 전용이며 사내 조회 구현은 `CoreDataProvider` 계약을 따른다.
    웹 화면에는 CSV 원천 저장 입구가 없다. 쓰는 곳은 부트스트랩·검증 스크립트뿐이다.
- `src/capa_simulation/io/company_bigdataquery_adapter.py`
  - 사내 SQL과 DB 컬럼 매핑을 넣는 전용 접속부다. `bigdataquery`를 지연 import하고 반환
    DataFrame을 CSV로 저장하지 않고 공통 78컬럼 파이프라인에 전달한다.
  - 조회 기간은 호출자가 `QueryWindow` 로 준다. 종료일은 화면 라벨과 같이 포함이며
    `sql_bounds()` 가 배타 상한을 하루 밀어 흡수한다 — 포함/배타 차이를 다루는 자리는
    여기 한 곳이다. 상세 창은 목록 창으로 **좁히지 않고**(`resolve_detail_window`) 기본
    90일 창과 합집합을 쓴다. 좁히면 그 코드의 원천 행이 잘린 시나리오가 조용히 저장된다.
  - 0행 결과는 `rename` 이전에 막는다. 뒤에 두면 MPGA TEST 예외가 `KeyError` 로 먼저 터진다.
- `src/capa_simulation/io/object_storage.py`
  - 사내 S3 호환 오브젝트 스토리지(Dell ECS 추정)에 `aws` CLI 로 붙는 유일한 경계다.
    앱 코드에서 `subprocess` 를 쓰는 유일한 자리이고(테스트에는 별도로 있다), 명령 실행기를
    주입받아 `aws` 가 없는 개발 PC 에서도 조립된 인자 배열을 테스트한다.
  - **모든 명령에 `--profile` 을 붙인다.** 네임스페이스가 프로필에 매여 있어 빠지면 다른
    네임스페이스를 본다. 조립 자리는 `_argv()` 하나뿐이다. 경로 스타일 주소와 체크섬
    옵트아웃(AWS CLI 2.23+ × ECS 비호환, Dell KB 000299507)을 환경변수로 강제한다.
  - 프로필·버킷·엔드포인트는 `CAPA_S3_*` 환경변수 > `config/object_storage.json` > 모듈 상수
    순으로 정한다. 커밋되는 설정의 `mode` 는 반드시 `local` 이다.
- `src/capa_simulation/io/bigdataquery_catalog.py`
  - 기간 내 시뮬레이션 코드 목록만 조회한다. 상세 SQL 과 한 파일에 섞지 않는다 — 상세
    SQL 은 78별칭을 계약과 순서까지 대조받고 `build_query` 가 `{simulation_code}` 자리를
    필수로 요구한다. 결과 5컬럼을 `CoreDataBatch`·정규화 경로에 넣지 않는다.
- `src/capa_simulation/io/reference_cache.py`
  - 현재 브라우저 세션에 활성화된 DuckDB 리비전의 테이블과 공용 표시순서를 반환한다.
  - 활성 리비전이 없으면 XLSB로 대체하지 않고 명확한 오류를 반환한다.
- `src/capa_simulation/persistence/`
  - 시뮬레이션과 설비 운영의 DuckDB 마이그레이션·Repository·캐시를 서로 독립된 모듈과
    물리 DB 파일로 관리한다.
  - 설비 운영 데이터는 전용 DB의 `equipment_meta`, `equipment_ops` 스키마에서 전체
    스냅샷 리비전으로 보존한다.
  - 쓰기는 프로세스 잠금과 단일 트랜잭션으로 직렬화하고, 읽기는 작업별 연결을 사용한다.
    `app.py` 는 rerun 한 번을 `pinned_connections(DUCKDB_PATH)` 로 감싸 작업별 연결이
    인스턴스를 다시 만들지 않게 한다(연결당 48ms → 0.2ms). rerun 이 끝나면 풀리는 핀이지
    상시 앵커가 아니다 — 배치가 DB 파일을 갱신하는 환경을 위해 일부러 그렇게 둔다.
  - 불변 `revision_id`의 전체 스냅샷과 공용 표시순서 프로필을 `st.cache_data`로 여러 세션에
    공유한다. 표시순서는 교체 시 `clear_global_display_order_cache()`로 명시 무효화한다
    (스냅샷 payload 에 현재 표시순서가 `RQ_DISPLAY_ORDER`로 들어가므로 두 캐시를 함께 비운다).
    시나리오·리비전 **목록**은 캐시하지 않는다. 사용자 정의 `ScenarioSnapshot`·
    `GlobalDisplayOrder` 인스턴스는 코드 핫리로드 후 pickle 클래스 식별자가 달라질 수
    있으므로 캐시에 직접 넣지 않고 기본형 메타데이터와 DataFrame payload를 캐시한 뒤
    현재 모델 인스턴스로 재구성한다.
  - 설비 운영 스냅샷도 revision ID별 기본형 메타데이터와 DataFrame payload를 캐시하고,
    최신 ID와 변경 가능한 이력 목록은 매번 저장소에서 확인한다.
  - 시나리오 생성 시 typed Core Data raw, 컬럼 프로파일, RQ 16개, 초기 리비전과
    프리셋을 한 트랜잭션으로 저장한다.
  - `app_meta.global_display_order*`는 시나리오와 독립된 단일 공용 프로필이며 최초 생성 시
    기존 리비전 또는 로컬 CSV/내장 시드에서 이관한다. 교체 시 현재본만 남기고 `version` 번호를
    올리며 이전 규칙은 보존하지 않는다 — 교체 전 CSV 다운로드가 유일한 되돌리기다.
  - 프리셋은 조회기간·B/N 포함 공정·표준 목표 Capa 공정 기본값·확보/경고 기준과
    표준 목표 Capa 「조회·집계 설정」(시작일·종료일·상세 토글·제품 분류 수준·출력 지표)을
    소유한다. 조회·집계 설정 컬럼이 없던 과거 리비전은 NULL 로 읽혀 기본값으로 열린다.
  - 공식버전은 불변 리비전을 가리키는 append-only 발행 이력이며 최신 발행이 새 세션의
    기본 리비전이 된다.
  - 표준 목표 Capa의 수동 주차별 가용대수만 설비 DB의 비버전 최신값 테이블에
    공정·Weeknum 기준으로 갱신한다.
- `src/capa_simulation/scenario_state.py`
  - 사용자 세션별 활성 시나리오와 `revision`(편집 카운터)·`content_token`(내용 토큰)을 관리한다.
    편집을 적용할 때마다 둘 다 갱신되며, 캐시 키에는 `content_token`만 쓴다.
  - 선택한 월 범위만 원자적으로 교체한다.
  - HOME처럼 계산용 월 범위만 필요한 경로는 전체 시나리오 복사 없이 선택 행만 복사한다.
- `src/capa_simulation/scenario_activation.py`, `scenario_preset_state.py`
  - 저장된 리비전의 16개 테이블과 편집 상태를 현재 세션에 원자적으로 활성화한다.
  - 조회기간·B/N 포함 공정·표준 목표 Capa 공정 기본값·확보/경고 기준과 표준 목표 Capa
    「조회·집계 설정」은 공통 위젯 생성 전에 대기 프리셋으로 복원한다. 세션 키 문자열과
    조회·집계 설정 기본값의 선언 자리는 `scenario_preset_state.py`·
    `persistence/models.py` 이며 페이지는 import 해서 쓴다.
  - 새 세션에서는 최신 공식 리비전을 한 번 자동 활성화한다.
- `src/capa_simulation/sync_boot.py`
  - `mode` 가 managed 일 때만 `sync_state` 에 두 DB 경로를 등록한다. 설정을 읽지 못하면
    조용히 끈다 — 동기화 표시 때문에 앱이 뜨지 못하는 일은 없어야 한다.
- `src/capa_simulation/performance.py`
  - HOME 단계별 소요시간을 측정하며 업무 데이터는 기록하지 않는다.
- `src/capa_simulation/services/simulation_cache.py`
  - 주요 계산 함수의 content-addressed `st.cache_data` 래퍼다.
  - HOME 전체 계산 그래프는 reference version·`content_token`·조회기간·표시순서 해시의 명시적 경량 키로 조회해 warm
    rerun의 대형 DataFrame 해싱을 피하고, 하위 계산 캐시는 다른 페이지와 계속 공유한다.

### 계산 서비스

- `load_calculator.py`: 계획/수율 편집 변환과 PKG·Chip·Wafer·Density 부하량. HOME의
  Chip·Wafer 부하량은 공통 전처리를 한 번만 수행한다.
- `unit_capacity.py`: Main/MI 환산 UPEH와 대당 Capa
- `weighted_unit_capacity.py`: 중복되지 않은 원수요 부하량과 STEP별 소요대수 합으로
  공정 유효 Capa를 만들며 기존 부하량 가중평균 조회 함수도 호환용으로 유지
- `standard_target_capacity.py`: ER 제외 월간 공정 유효 Capa의 일 환산, ISO 주차 캘린더,
  수동 가용대수 표 계약과 주차별 일 표준 가능량
- `route_step_editor.py`: MCP·STEP 고유 조합 수와 네 경로 테이블의 일괄 복제·삭제
- `process_rename.py`: 공용 공정 표시명의 값 정규화(앞뒤 공백·U+00A0), 1:1 검증과
  CSV·붙여넣기 직렬화. **치환은 여기 없다** — 표시명을 실제로 갈아 끼우는 헬퍼는
  `components/process_labels.py` 에만 둔다.
- `required_equipment.py`: RQ_REQB 경로 연결과 소요대수
- `securement_rate.py`: 공정별 확보율과 경고·확보 기준별 최소 정수 추가 필요대수
- `equipment_count.py`: 보유·대여·가용 설비대수 표
- `equipment_availability.py`: 기존 보유대수, 30컬럼 호기 일정과 운영 비가동 검증,
  월요일 시작 주차별 총대수·가용대수·비가동대수, 비가동 호기, Space 단계와 기간별 단계
  전환 이벤트 원천. 설비 DB가 비어 있을 때 사용하는 개발용 Core Data 기반 30개 공정
  보유대수 샘플과 호기 마스터가 비었을 때만 대시보드에 표시하는 단계별 임시 호기 샘플을
  제공한다. 임시 호기와 비가동 샘플은 DB에 저장하지 않는다.
  주차 집계는 정규화한 설비·비가동 입력을 전체 기간에 재사용하고 주차별 공정 집계를
  `groupby`·`crosstab`으로 한 번에 만든다.
- `equipment_csv.py`: 기존 보유대수·호기 마스터·비가동 일정 **세 표 모두**의 CSV 양식
  생성, Excel 붙여넣기 표 검증·자연키 기준 병합. 호기 마스터 양식은 두 양식이 공유하는
  호기로 2행에 전체 입력 예시를 채우고, 3행부터는 호기를 비운 채 활용구분·확정상태의
  허용값과 라인구분·투자기준의 기재 예시를 나열한다. 호기가 빈 안내 행은 붙여넣기·업로드
  때 버려진다. 기존 보유대수 양식에는 그 안내 행을 두지 않는다 — `분류` 에 허용값 목록이
  없고, `equipment_validation.py` 의 `_drop_blank_rows` 가 공정·분류·기존보유대수 중
  하나라도 값이 있으면 행을 남기므로 안내 행이 그대로 누락값 오류가 된다. 양식 예시의 비고
  상수는 `SAMPLE_BASELINE_TEMPLATE_NOTE` 다. `equipment_samples.py` 의
  `SAMPLE_BASELINE_NOTE` 는 저장 가드가 보는 개발 샘플 표식이라 이름을 나눈다.
- `dashboard.py`: HOME 월별 집계, B/N 단일 월별 순위에서 파생하는 Top 1·Top 5·순위 상한을
  인자로 받는 상세, Wafer Capa
- `dynamic_capacity.py`: 표준 Capa에 실적 효율·UPEH·Rundown·생산실적을 순차 반영하는
  Dynamic Capa 손실 분석, 시간 가중 집계, 필터와 미연결 화면용 결정론적 데모 데이터
- `wip_status.py`: 재공 DB 연결용 일자·공정·STEP·제품·보유재공·유입·Flow 계약,
  STEP 코드 정렬, 제품별 표준 가능량 일 전개와 미연결 화면용 결정론적 재공 샘플
- `display_order.py`: `RQ_DISPLAY_ORDER` 기반 동적 행 정렬
- `month_filter.py`: YYYYMM 검증과 조회기간 필터
- `capacity_reference_editor.py`: Capa 기준정보 Long/Wide 편집 변환
- `clipboard_table.py`, `reference_csv.py`: Excel에서 복사한 헤더 포함 TSV 표 파싱과
  입력 RQ Wide 표의 컬럼·분류행 동일성 검증. 다운로드 양식은 UTF-8 CSV로 유지한다.
- `reference_transformer.py`: XLSB의 `Q_Core_Data`와 15개 Core 파생 Power Query를
  pandas로 대체하고, 수동 입력 `RQ_DISPLAY_ORDER`를 검증한다. Core 파생 RQ의 동일
  업무 키 값 충돌은 원천 첫 행을 임시 적용해 전체 변환을 계속하며 테이블·업무 키·후보값·
  선택값·원천행 번호가 포함된 충돌 보고서를 함께 반환한다.
  `제품정보`의 원천값은 raw에 보존하고 RQ 파생 전 모든 언더바를 공백으로 바꾼 뒤 연속
  공백을 하나로 축약하여 BigDataQuery와 기존 화면 분류 키를 통일한다.
- `core_data_pipeline.py`: CSV·BigDataQuery 공급자 결과를 동일한 정규화·RQ 변환
  파이프라인으로 연결한다.

- `object_storage_manifest.py`: 원격 스냅샷의 키 계약과 pull·push 판정을 담는 순수 계층.
  가변 포인터(`current.json`)를 쓰지 않는다 — 그것이 유일한 read-modify-write 지점이고 앞사람
  저장이 사라지는 경로가 거기서만 생긴다. 포인터를 내림차순 불변 키의 시퀀스로 두면 같은
  seq 에 포인터가 둘인 것 자체가 분기의 물증이 된다. 판정을 `scripts/` 가 아니라 여기 두는
  이유는 `scripts/` 가 mypy strict 검사 밖이기 때문이다.

- `bigdataquery_catalog_view.py`: 시뮬레이션 코드 목록을 표시·검색용으로 정리하고 등록 폼
  기본값을 만든다. Streamlit 을 import 하지 않는 순수 계층이다. 코드·PLAN 조합당 한 행만
  남기고(적재시각이 행마다 다르면 코드 하나가 수천 행이 된다), 숫자형 등록시각은 버린다
  (`pd.to_datetime` 이 정수를 나노초로 읽어 1970년이 조용히 저장된다).

- `core_data_derivation.py`: 원천 78컬럼에서 RQ 파생에 쓰는 정규화된 작업 프레임을
  만든다. 제품정보 언더바 정규화와 Area·소요기준 별칭 정리가 이 경계에서 끝난다.
- `reference_conflicts.py`: 동일 업무 키의 값 충돌을 수집하고 테이블·키·후보값·선택값·
  원천행 번호가 담긴 보고서를 만든다.
- `frame_contracts.py`: 여러 서비스가 공유하는 필수 컬럼 검증과 업무 키 정규화를 단일
  정의한다. 소요기준(`WAFER`→`WF`)·Area_Name(`Main`·`MI`)·월(`YYYYMM`) 규칙이 여기 있다.
  계약이 서로 다른 것은 합치지 않는다.
- `virtual_product.py`: 기존 제품의 기준정보를 새 제품 키로 복제해 가상 제품을 등록한다.
  제품 키(`제품정보`+`Stack`)를 가진 8개 테이블만 복제하고 공정 기준 테이블은 건드리지
  않는다. 계획 수량은 0으로 시작한다. 원본 계획을 복제하면 총 수요가 조용히 두 배가 된다.
- `iso_week_calendar.py`: ISO 주차 캘린더와 `YY-W##` 주차 코드 파싱
- `weekly_availability_input.py`: 표준 목표 Capa 수동 가용대수 입력 표 계약. 계산 서비스가
  아니라 입력 계약이므로 설비 Repository 도 여기를 참조한다.
- `standard_target_logic.py`: 단일 공정·주차를 제품·WF 속성 Mix 로 분해하는 로직 분석
- `equipment_contract.py`: 설비 세 입력의 컬럼 계약과 허용값. 기존 보유대수의 자연키는
  `BASELINE_KEY_COLUMNS = ("공정", "분류")` 다. 주차 집계는 `공정` 하나로 합산하지만
  중복 판정과 Import 병합·미리보기는 두 컬럼 조합을 쓴다 — 같은 공정을 분류로 나눠
  여러 줄 적는 것이 정상 입력이기 때문이다.
- `equipment_validation.py`: 설비 마스터·기존 보유대수·비가동 일정 입력 검증
- `equipment_samples.py`: 설비 DB 가 비어 있을 때만 쓰는 비영속 화면 샘플. 실제 DB 연결이
  끝나면 이 파일만 삭제한다.
- `floor_layout_profile.py`: 층 배경 도면의 순수 계층. PNG·JPEG 헤더를 직접 읽어 픽셀
  치수를 얻고(새 의존성 없이), 캔버스 기본값을 폭 100 고정·높이 100×h/w 로 만든다.
  상한은 층당 2MB(`MAX_FLOOR_LAYOUT_BYTES`)와 전 층 합계 30MB(`MAX_TOTAL_LAYOUT_BYTES`)
  이고 둘 다 이 파일에만 둔다. 파일 시그니처와 확장자가 다르면 거부한다 — data URI 의
  MIME 이 내용과 어긋나면 배경이 조용히 안 그려진다.
- `display_order_editor.py`, `display_order_csv.py`: 웹 편집 표시순서 규칙의 검증·범위
  교체·CSV 직렬화와 수동 입력 `RQ_DISPLAY_ORDER` 변환

### 화면 공통 계층

- `src/capa_simulation/navigation.py`
  - 사이드바 페이지 목록을 `PageSpec` 선언으로 관리하고 `st.Page` 묶음을 만든다.
  - 페이지 추가·제목 변경은 여기서만 한다. 미구현 표기는 `IMPLEMENTING_SUFFIX` 하나를 쓴다.
- `src/capa_simulation/page_bootstrap.py`
  - 계산 페이지 공통 진입 절차다. 활성 리비전·표시순서·활성 시나리오·조회기간을 준비하고
    원천과 겹치는 유효 구간을 확정한다. 페이지는 `BOOTSTRAP_ERRORS` 를 잡는다.
- `src/capa_simulation/settings.py`, `sidebar_status.py`
  - 앱 이름·경로·조회기간 상수와 사이드바의 적용 조회기간 표시.
- `src/capa_simulation/design/tokens.py`
  - 색·서체·표 치수를 역할 이름으로 단일 정의한다. 파이썬 코드에 색 리터럴을 쓰지
    않는다. 규칙은 `docs/design_system.md` 를 따른다. Figure 공통 유틸리티는 여기가 아니라
    `components/plotly_layout.py` 에 있다.
- `src/capa_simulation/components/page_header.py`
  - 모든 페이지의 제목·설명·상태 배지. `(구현중)` 은 제목에서 떼어 배지로 보여준다.
    사이드바 라벨과 같은 문자열을 써야 하며 어긋나면 테스트가 잡는다.
- `src/capa_simulation/components/app_header.py`
  - 화면 맨 위 띠의 면을 칠하고 앱 이름·버전·개발자·인증 정보를 모든 페이지에 표시한다.
    Streamlit 이 헤더에 위젯을 넣는 API 를 주지 않아 `stHeader`·`stSidebarHeader` 의
    가상요소에 글을 얹는다(글자만 가능, 링크·버튼 불가). 값은 `settings.py` 가 단일 근거이고
    ⋮ 메뉴의 About 과 같은 상수를 본다. `app.py` 에서 한 번만 부른다.
- `src/capa_simulation/components/column_filter.py`
  - 분류 컬럼별 다중선택 필터와 초기화 버튼. 선택값으로 거른 프레임을 돌려준다.
    `value_labels` 는 `format_func` 로 표시만 바꾼다. 옵션 값과 세션 저장값은 원본이다.
- `src/capa_simulation/components/process_labels.py`
  - 원본 공정명을 화면 표시명으로 바꾸는 **유일한 지점**이다. `공정` 은 1급 조인 키라
    데이터에서 바꾸지 않고 표시 직전에만 라벨을 갈아 끼운다. `services/` 는 이 모듈을
    import 하지 않는다 — 그 금지가 왕복 CSV·클립보드, 표시순서 `분류값`, 예외 메시지,
    프리셋·세션 저장값, 설비 DB 공정명에 표시명이 닿지 않게 하는 경계다.
  - `ProcessLabels.version` 은 HOME Figure 캐시 키 원소로 쓴다. 계산 캐시 키와
    `content_token` 은 건드리지 않는다.
- `src/capa_simulation/components/process_rename_management.py`
  - Admin Area 의 `Proc Rename` 탭. 공용 공정 표시명의 CSV 다운로드·Excel 붙여넣기·
    직접 편집과 저장을 담당한다. 저장은 공용 프로필 교체이며 리비전을 만들지 않는다.
- `src/capa_simulation/components/scenario_edit_bar.py`
  - 편집 페이지 상단의 "활성 시나리오 · 수정본 N" 과 원본 초기화 버튼.
    초기화할 때 함께 비울 세션 키는 페이지가 넘긴다.
- `src/capa_simulation/components/roadmap_panel.py`
  - 업무 활용 목적·담당 부서별 Action Item·로드맵 한 줄을 카드로 그린다.
    Static Capa 와 Dynamic Capa 가 공유한다.
- `src/capa_simulation/services/product_type.py`
  - 제품타입(HBM·EDP-TSV)이 가르는 규칙의 단일 근거. `WF 구분` 값 집합 두 개를 **일부러
    따로** 선언하고(공통 부분을 뽑아 공유하지 않는다), EDP-TSV 의 `Top` 을 `Top_e` 로 가르는
    `apply_edp_wf_division` 을 갖는다.
  - **변환 지점은 `core_data_derivation.build_q_core_data` 한 곳이다.** 원천 78컬럼이 작업
    프레임이 되는 경계이고, 거기서 한 번 바꾸면 16개 RQ 표·부하량·소요대수·화면이 전부 같은
    값을 본다. 두 층에서 따로 바꾸면 조인 한쪽만 바뀌어 수율·Chip 이 조용히 안 붙는다.
  - 입력은 그대로 받는다. Capa 기준정보 DB·실적 DB 어디에도 `Top_e` 는 없고
    `raw_data.core_data` 도 `Top` 그대로다. 표시순서 규칙도 입력에는 `Top` 뿐이라
    `display_order._with_edp_top_rule` 이 적용 시점에 `Top_e` 규칙을 파생한다 — 없으면
    화면 맨 뒤로 조용히 밀린다.
- `src/capa_simulation/services/legacy_comparison.py`
  - 원천에 보존된 기존 결과와 신규 계산을 같은 단위로 대조한다. 기존 컬럼은 **계획 한 줄
    (`RQ_PKG_PLAN` 업무 키) × `WF 구분`** 안에서 경로 행마다 반복되므로, 그 단위에서 접은
    뒤 대조 키로 **합산**한다. 접는 층을 대조 키에서 잡으면 서로 다른 계획 줄까지 뭉개져
    대조가 조용히 절반으로 줄어든다 — 실제로 그렇게 만들었다가 270키 중 121키만 보고
    "완전 일치" 라고 보고했다. 실행은 `scripts/compare_legacy_results.py`.
- `src/capa_simulation/components/tab_state.py`
  - 열린 탭을 서버가 알게 하는 `stateful_tabs` 와 판정용 `tab_is_hidden`. 차트가 든 탭은
    반드시 이것으로 만든다. 숨겨진 탭 안에서 Plotly 표를 그리면 글자 폭 측정이 0 이라
    헤더가 셀 가운데를 벗어난다. 어기면 테스트가 잡는다.
- `src/capa_simulation/components/status_metric.py`
  - 조치가 필요한 지표에 상태색 왼쪽 띠를 붙인 metric 카드. 색은 확보 상태색 토큰을
    그대로 쓴다. 색을 붙일 근거가 없으면 `tone="neutral"` 로 두어 기존 카드와 같게 둔다.
- `src/capa_simulation/components/table_toolbar.py`
  - 표 제목·부가 설명·CSV 내보내기 한 줄. `st.download_button` 은 여기서만 부른다.
    라벨에 아이콘을 섞지 않고 `label` 인자를 쓴다. 어기면 테스트가 잡는다.
- `src/capa_simulation/components/monthly_table_base.py`
  - 두 월별 표가 공유하는 상수·텍스트 폭 계산과 고정 분류 + 스크롤 월 껍데기.
- `src/capa_simulation/components/scroll_shell.py`
  - 가로 스크롤 상자와 그 안의 고정 폭 캔버스. 월별 표·HOME·재공 현황이 함께 쓴다.
    컨테이너 key 가 `.st-key-<key>` 클래스가 되므로 이름을 바꾸면 CSS 가 끊어진다.
    분류 컬럼 폭을 px 로 못박는 `split_scroll_columns_style` 도 여기 있다. `st.columns`
    인자는 비율이라 창이 좁으면 분류 이름이 잘렸다.
- `src/capa_simulation/components/month_editor.py`
  - 월별 Wide 기준정보를 탭 안에서 편집하는 `data_editor` 와 분류 컬럼 표시 라벨.
  - **필터는 보기만 좁히고 저장은 전체다.** 분류 컬럼 필터(`render_column_filters`)는 화면에
    그릴 행만 줄이고, 돌려주는 표는 언제나 원본과 행 수·행 순서가 같은 전체 표다. 편집값은
    `merge_edited_months` 가 그 탭의 `dimensions` 를 키로 원본에 되머지한다. 되머지를 지우고
    걸러진 표를 그대로 돌려주면 `replace_month_range` 가 조회기간의 행을 편집값으로 통째로
    갈아끼우므로 **화면에서 걸러진 공정이 그 기간에서 조용히 삭제된다.** 되머지가 정확한
    근거는 `num_rows="fixed"` 와 `disabled=dimensions` 다 — 행 추가·삭제와 분류 컬럼 편집이
    막혀 있어 바뀔 수 있는 것은 월 컬럼 숫자뿐이다.
  - `data_editor` 의 편집 델타는 **행 위치**로 기록된다. 보이는 행 집합이 바뀌면 남은 편집이
    다른 행에 붙으므로, 필터 선택이 달라지면 `data_editor` 를 만들기 전에 `editor_key` 를
    세션에서 버린다. `editor_key` 자체에 필터를 섞지 않는다 — 페이지가 고정 키 목록으로
    세션을 청소하는 경로가 그 키를 못 찾는다.
  - 왕복 CSV·붙여넣기(`render_reference_clipboard_tools`)에는 **필터 이전의 전체 표**를
    넘긴다. 양식이 부분 표가 되면 그 부분 표가 행 집합 검증을 통과해 나머지 공정을 지운다.
  - 공정 표시명은 페이지가 조회해 `value_labels=` 로 넘기고 필터 옵션 표기에만 쓴다. 이
    모듈은 `process_labels` 를 import 하지 않는다.
- `src/capa_simulation/components/home_preference.py`
  - HOME `Preference` 탭과 `Capa LOB 현황` 제목 줄. 제목은 Plotly 주석이 아니라 여기서
    그린다 — 주석 안에는 위젯을 놓을 수 없어 「선행」 토글을 제목 옆에 둘 수 없었다.
  - 선행 물량 저장은 **표에 보이는 달만** 갈아 끼운다(`merge_advance_load_edits`). 조회기간을
    좁힌 채 저장한 사람이 보이지 않는 달의 입력을 모르는 새 날리면 안 된다.
- `src/capa_simulation/services/advance_load.py`
  - 선행 투입 물량 정규화와 월별 Capa 부하 변동률. `변동률 = 기존 계획 ÷ 선행 반영 계획`
    이고 확보율에 곱하고 Wafer 는 나눈다. 그래서 `계획 × 확보율` 인 Capa 가 **정확히
    그대로**다 — 선행 투입은 물량을 앞으로 옮긴 것이지 설비를 늘린 것이 아니다.
  - 한 달 안에서는 모든 공정에 같은 수를 곱하므로 **B/N 공정 순위가 바뀌지 않는다.**
  - 선행 반영 계획이 0 이하가 되는 달은 변동률을 낼 수 없다. 그 달만 미적용으로 두고
    화면이 알린다 — 한 달의 과한 입력으로 대시보드 전체가 사라지면 어디가 잘못됐는지
    볼 수 없다.
- `src/capa_simulation/components/loading_progress.py`
  - 계산이 오래 걸리는 페이지가 본문 맨 위에 띄우는 진행 막대다. 단계 목록
    (`LoadingStage`)을 미리 선언하고 호출부는 `advance()` 만 부른다 — 호출부가 퍼센트를
    직접 적으면 단계를 더하고 뺄 때 누적값이 어긋나고 화면에서만 드러난다.
  - 누적 퍼센트는 단계 수 균등 분할이 아니라 **측정한 소요 시간 비율**로 정한다. HOME 은
    차트 생성이 대부분을 쓴다(`HOME_LOADING_STAGES`).
- `src/capa_simulation/components/plotly_layout.py`
  - 제목 주석·외곽 테두리·분기 경계·고정 행 등 Figure 그리기 공통 유틸리티.
- `src/capa_simulation/components/home_figures.py`, `home_rendering.py`, `home_dimensions.py`
  - HOME 의 Figure 생성기 3종, 세션 Figure 캐시와 렌더링, LOB·상세 B/N 픽셀 치수.
  - 상세 B/N 은 `go.Table` 이 아니라 카테시안 xy 다. 월 오프셋은 `go.Bar` 의 `base`
    로 주고, hover 표적 막대·트랙 막대·확보율 막대·공정명 텍스트 trace 네 개만 쓴다.
    hover 표적은 `HIT_TARGET` 색으로 행 전체 높이를 덮어 칸 어디서나 툴팁이 뜨게 하고,
    보이는 막대는 전부 `hoverinfo="skip"` 이다. 공정명은 월 칸 폭에 맞춰 글자 크기를
    줄이고 그래도 넘치면 말줄임하며, 전체 이름은 hover 의 `customdata` 에만 있다.
    순위 상한 `BOTTLENECK_DETAIL_RANK_LIMIT` 은 여기서 정하고 서비스에 인자로 넘긴다.
    자르는 곳은 서비스 한 곳이고 Figure 는 받은 프레임을 다시 자르지 않는다.
- `src/capa_simulation/components/scenario_management.py`,
  `display_order_management.py`, `bigdataquery_registration.py`
  - 시나리오 관리 페이지의 세 탭 UI.
  - `bigdataquery_registration.py` 는 2단계다. 목록 위젯은 반드시 `st.form` 밖의
    `st.dataframe(on_select="rerun", selection_mode="single-row")` 이고(폼 안에서는 제출
    전까지 선택이 서버에 오지 않아 예외 없이 조용히 실패한다), 목록을 등록 폼보다 **위**에
    그려 프리필의 세션 대입이 위젯 생성 전이 되게 한다. 순서를 바꾸면 행을 고를 때마다
    `StreamlitAPIException` 으로 페이지가 죽는다.

### 영속성 모듈

- `src/capa_simulation/persistence/snapshot_export.py`
  - 라이브 `.duckdb` 파일을 바이트로 읽지 않는다. 연결이 하나라도 열려 있으면 같은
    프로세스에서도 `PermissionError` 이고, 핀이 열린 동안 COMMIT 은 `.wal` 에만 있어 그
    파일을 올리면 방금 저장한 리비전이 빠진다. `ATTACH` + `COPY FROM DATABASE` 로 DuckDB
    자신이 만든 스냅샷을 쓴다(실측 67.4 MB → 21.5 MB, 2.1초). 설치할 때는 고아 `.wal` 을
    먼저 치우고 기존 파일을 백업으로 옮긴다.
- `src/capa_simulation/persistence/sync_state.py`
  - DB 파일 옆 `.sync.json` 사이드카에 원격 세대와 미반영 변경을 기록한다. 상태를 DuckDB
    안에 두지 않는 이유는 그 파일 자체가 동기화 대상이라 순환이 되기 때문이고, 메모리에
    두지 않는 이유는 프로세스가 죽으면 표시가 사라져 다음 pull 이 로컬 전용 리비전을 덮기
    때문이다. `enable()` 전에는 파일을 하나도 만들지 않는다(개발 PC·CI 무영향). 읽지 못하는
    사이드카는 "변경 있음" 으로 본다.

- `persistence/repository.py`: `DuckDBScenarioRepository` 와 쓰기 잠금·트랜잭션 경계
- `persistence/models.py`: Repository 가 주고받는 타입
- `persistence/display_order_store.py`: 공용 표시순서 프로필의 검증·이관·저장
- `persistence/process_rename_store.py`: 공용 공정 표시명 프로필의 조회·삽입 SQL
- `persistence/advance_load_store.py`: 공용 선행 투입 물량 프로필의 조회·삽입 SQL
- `persistence/preset_store.py`: 리비전 프리셋 저장·복원
- `persistence/source_data_store.py`: 원천 Core Data raw 와 컬럼 프로파일
- `persistence/summaries.py`: 조회 행을 요약 모델로 변환
- `persistence/_sql_helpers.py`: 프레임 저장·조회와 값 변환 공용 헬퍼
- `persistence/migration_runner.py`, `equipment_migration_runner.py`: 체크섬 기반 SQL 적용
- `persistence/cache.py`, `equipment_cache.py`: 불변 리비전 스냅샷과 공용 표시순서의 Streamlit 캐시 경계
- `persistence/equipment_repository.py`: 설비 운영 입력의 불변 전체 스냅샷 저장소

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

웹 수정은 반드시 `apply_month_updates()`를 통해 반영한다. 페이지 전용 DataFrame만
수정하고 끝내면 다른 페이지와 계산 캐시에 변경이 전달되지 않는다. 월 축(`생산계획년월`)이
없는 `RQ_CHIP_QTY`·`RQ_CHIP_EQ`는 `apply_table_updates()`로 통째로 교체한다 —
`apply_month_updates()`에 넘기면 `생산계획년월 컬럼이 없습니다`로 거부된다.

### 읽기 전용 참조 테이블

```text
RQ_DISPLAY_ORDER
RQ_MODULE
```

`RQ_DISPLAY_ORDER`는 계산 페이지에서 읽기 전용이지만 `표시순서 관리`에서는 시나리오와
분리된 공용 DB 프로필을 수정한다. 나머지 테이블을 웹에서 수정할 필요가 생기면 단순히
session state에 별도 복사하지 말고 활성 시나리오의 editable table 계약과 저장 정책을
함께 변경한다.

## 5. 상태와 캐시 불변조건

1. **기준정보를 페이지별로 다시 읽지 않는다.** 모든 계산 페이지는
   `get_effective_reference_tables()`를 사용해 활성 DuckDB 리비전만 읽는다.
2. **서버 공통 데이터와 사용자 데이터를 구분한다.** 불변 DuckDB 리비전과 동일 입력 계산
   결과는 서버 캐시, 웹 편집값은 `st.session_state`의 활성 시나리오다.
3. **편집 적용마다 `revision`을 올리고 `content_token`을 재발급한다.** 편집 UI(위젯 초기화·
   미저장 감지)는 `revision`을, 계산·Figure 캐시 키는 `content_token`을 본다 — `revision`
   번호는 내용이 달라도 겹칠 수 있다(세션 편집 0,1,2… 와 저장 리비전 번호).
4. **계산 함수는 가능한 순수 함수로 유지한다.** Streamlit 캐시는 `simulation_cache.py`
   래퍼에 두고 서비스 함수 내부에 UI 상태 접근을 넣지 않는다.
5. **공식버전은 append-only다.** 특정 시나리오·리비전을 새 공식버전으로 발행하며 과거
   공식 이력을 갱신하지 않는다. 최신 공식 시나리오는 다른 공식 발행 전 삭제하지 않는다.
   그 외 시나리오는 삭제할 수 있고, 그때 그 시나리오의 공식 발행 이력도 함께 사라진다.
6. **미저장 편집과 저장 리비전을 구분한다.** 미저장 편집은 세션 종료 후 사라지며,
   `시나리오 관리`에서 저장한 리비전만 DuckDB에 영구 보존된다.
7. **완성 Figure 캐시 키에는 출력에 영향을 주는 모든 조건을 포함한다.**
   `ActiveScenario.content_token`, reference version, 조회기간, B/N 공정 선택, 임계값, 상세
   토글 상태와 Figure schema version을 누락하지 않는다.
8. **과거 리비전을 갱신하지 않는다.** 변경은 새 전체 리비전으로만 저장하고, 과거
   리비전에서 저장하면 해당 리비전을 부모로 갖는 새 분기를 만든다.
9. **설비 운영 이력은 시나리오와 물리적으로 분리한다.** 가용설비 현황은 전용 DuckDB,
   전용 마이그레이션·Repository·캐시와 페이지 전용 조회기간만 사용한다. 시뮬레이션 DB나
   `RQ_*`를 읽지 않으며 저장마다 새 전체 스냅샷을 만든다.
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
    밖이거나 앞뒤가 뒤집혀 있어도 예외를 던지지 않고 범위 안으로 맞춰 리비전을 연다.
13. **표시순서는 시나리오에 종속시키지 않는다.** 공용 표시순서는 별도 DB 프로필에서
    읽고 Excel 표 붙여넣기 또는 직접 편집으로 원자 교체한다. 시나리오 전환·신규 생성 시에는
    항상 현재 공용 프로필을 적용하며 표시순서 변경만으로 리비전을 만들지 않는다.
14. **공정 표시명은 화면 표기 전용이다.** 공용 프로필(`app_meta.global_process_rename*`)
    에 저장하고 원본 `공정` 값은 데이터·저장·왕복 CSV 어디에서도 바꾸지 않는다. 라벨은
    계산 입력이 아니므로 `content_token` 을 재발급하지 않고, 프로필 버전 정수를 HOME
    Figure 캐시 키 원소로 넣어 버전이 바뀔 때만 Figure 를 무효화한다. 계산 캐시
    (`build_home_simulation_cache_key`)에는 넣지 않는다.

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
프레임에서만 두 목록을 합쳐 이름으로 판정한다. 이름 비교는 기존 리비전과 BigDataQuery의
표기 차이를 흡수하도록 대소문자와 앞뒤 공백에 의존하지 않는다. 정확한 현재 구현은 두
모듈과 `docs/TODO.md`를 기준으로 한다.

### 대당 Capa

```text
대당 Capa
= 환산_UPEH × 24 × 효율 ÷ 여유율
  × 모듈수 × 가동일수 ÷ Lot측정률 ÷ WF측정률
```

- `Area_Name = Main`: `UPEH`
- `Area_Name = MI`: `3600 / ST`
- UPEH·Lot/WF 측정률과 `RQ_REQB`의 `Area_Name`은 Core Data 변환 및 기존 리비전의
  런타임 소요대수 연결에서 대소문자와 앞뒤 공백을 정규화해 `Main`·`MI`로 통일한다.
  Lot/WF 측정률의 빈 값은 측정 대상이 아닌 경로로 보고 `1.0`을 적용하되, 숫자가 아닌
  값은 오류로 처리한다.
- `소요기준 = PKG 또는 CHIP`: UPEH를 Kea 기준으로 `/ 1000`
- Lot 측정률·WF측정률이 0 이하인 행과 대당 Capa 0 이하인 행은 제외 행으로 남기고 계산에서
  제외한다. 두 측정률은 같은 규칙을 쓰며 `WF측정률 0 이하`·`Lot 측정률 0 이하` 사유를 붙인다.
  한 행이 둘 다에 걸리면 WF측정률 사유로 한 번만 남는다.
- 계산 대상 행을 먼저 확정한 뒤 편중률·모듈수·`RUN_DAY`의 0 이하 검증을 남은 행에만 돌린다.
  어차피 제외될 행의 기준값이 화면 전체를 멈추면 그 값을 고칠 편집기조차 열 수 없다.
  이 세 검증은 실패 시 위반 건수와 문제 업무 키·값 예시 5건을 메시지에 싣는다.
- 제외 행은 사유 컬럼과 함께 `CAPACITY_EXCLUSIONS_ATTR`로 전달되고 공정별 Capa·공정별
  확보율 화면이 건수·상세 표·CSV 내려받기로 보여 준다
- BOX·PCB는 산식 구현 전까지 제외
- 기본 화면용 공정 유효 Capa는 STEP으로 중복된 수요를 한 번만 센 원수요 부하량을
  STEP별 소요대수 합계로 나눠 `원수요 부하량 ÷ Σ(STEP별 부하량 ÷ STEP별 대당 Capa)`로
  집계한다. 동일한 대당 Capa의 STEP이 늘면 공정 유효 Capa는 그 수에 반비례해 감소한다.
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
대당 일 Capa = 월간 공정 유효 Capa ÷ RUN_DAY
주차별 일 표준 가능량 = 대당 일 Capa × 주차별 가용대수
```

- 제품 Mix 가중은 공정 유효 Capa와 동일하게 중복되지 않은 원수요 부하량을 분자로,
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

소요기준은 대소문자를 정규화하며 `WAFER`는 `WF`로 통일한다. 현재 지원 값은 `PKG`,
`CHIP`, `WF`다.

Static Capa의 설비 부족 현황은 소요대수 자체는 실수로 유지하되 실제 추가 설비는 정수로
올림한다.

```text
경고 기준 필요대수 = ceil(max(소요대수 × 경고 기준 - 가용대수, 0))
확보목표 총 필요대수 = ceil(max(소요대수 × 확보 기준 - 가용대수, 0))
확보 기준 추가대수 = 확보목표 총 필요대수 - 경고 기준 필요대수
```

경고 기준 미달 행의 두 단계 추가대수 합은 확보 기준을 충족하기 위한 최소 대수와 같아야
한다. 월별 부족대수는 동일 설비의 기간 중복을 피하기 위해 전체 기간을 단순 합산하지 않고
월별 상세와 월 최대치로 표시한다.

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

### 표준 대비 재공 현황 프로토타입

- 차트 조회기간은 서버 오늘 날짜 기준 -7일~+3일의 11일이며, 미래 3일도 실제 DB 연결
  전까지는 전망이 아닌 화면 검토용 샘플로 명시한다.
- 각 공정·제품·STEP 차트는 보유 재공·유입·Flow 세로 막대와 제품별 일 표준 가능량
  점선을 함께 표시한다. Flow가 표준 이상이면 충족, 미달이면 부족으로 색을 구분한다.
- 제품별 표준 가능량은 기존 표준 목표 Capa와 동일하게 원수요 부하량 합을 STEP 소요대수
  합으로 나눈 공정 유효 Capa에 RUN_DAY와 주차별 가용대수를 적용한다. 여러 양산구분은
  원수요 부하량과 STEP 소요대수를 각각 합친 뒤 비율을 다시 계산한다.
- 공정 소요기준에 따라 단위는 PKG·CHIP의 Kea 또는 WF의 매를 유지하고 서로 합산하지 않는다.
- STEP 정렬은 코드 끝의 `P###`, `P###-###`, `T###`, `T###-###`를 인식해 P 전체 다음 T를
  배치하고 각 숫자 구간을 오름차순으로 정렬한다. 인식할 수 없는 코드는 그 뒤에 둔다.
- 주차별 가용대수가 없으면 기준선을 임의 생성하지 않고 `표준 미설정`으로 표시한다.
  설비 DB 에 가용대수가 한 건도 없으면 빈 표를 계산에 넣지 않고 `st.info` 안내 후 멈춘다.

### B/N

- 월별 유효 확보율이 가장 낮은 공정이 B/N Top 1이다.
- 동률이면 공정명 오름차순 첫 공정을 사용한다.
- `B/N Density Capa = Density 부하량 × 확보율`
- `Wafer Capa = Wafer 부하량 × 확보율`

### 설비 운영 주차 집계

- 기존 보유대수는 모든 주차에서 총대수와 가용대수에 포함한다.
- 신규 호기는 입고일정이 속한 주부터 총대수에 포함한다.
- 신규 호기는 Qual일정이 속한 주부터 가용대수에 포함한다.
- 단일 확정상태는 Qual 일정의 계획·확정·완료·지연 실행관리 용도이며 가용대수 산식에는
  사용하지 않는다. 장기보관·기존설비처럼 Qual일정이 없으면 비워 둘 수 있다.
- 입고 후 Qual 전인 호기는 셋업중대수와 비가동 호기 목록에 포함한다.
- Qual 완료 또는 기존설비에 활성화된 개발대여·공사·고장·이설 등의 운영 비가동 일정이 있으면
  가용대수에서 제외한다. 같은 호기의 중복 비가동 일정은 한 대로 집계한다.
- 장기보관 Y는 전 기간 보유대수에는 포함하되 가용대수에서는 제외하고, 기존설비 Y는
  입고·Qual 일정 없이 전 기간 보유·가용대수에 포함한다.
- 반출·이설 예정은 실행일 전까지 계획 상태로 표시하되 기존 보유·가용 판정을 유지하고,
  실행일부터 보유·가용·레이아웃에서 제외한다.
- 주차는 월요일 시작·일요일 종료의 ISO Weeknum(`YY-W##`) 기준이며, 조회기간은
  가용설비 현황 페이지 상단에서 시뮬레이션과 독립적으로 설정한다.
- Space는 입고 예정·셋업 진행중·가용·반출 예정·이설 예정·보관 설비·운영 비가동
  상태를 색으로 구분하며 레이아웃표시 Y이고 반출·이설 실행 전인 호기만
  X좌표·Y좌표·Xsize·Ysize로 배치한다.
- 운영 가용대수는 별도 확정 전까지 `RQ_EQP_AVBL` 기반 Capa·확보율 계산을 대체하지 않는다.
- 설비 DB가 비어 있을 때만 개발용 Core Data 샘플의 공정별 보유대수를 편집 초기값으로
  표시한다. 원본에 2차 분류가 없으므로 `분류=전체`로 두며, 사용자가 저장하기 전에는
  설비 DB에 쓰지 않는다.
- 호기 마스터가 비어 있으면 현재 날짜 기준의 생애주기·가용·운영 비가동 상태별 임시
  호기 7대를 가용설비와 Space 대시보드에만 표시한다. 편집 원본과 DuckDB에는 넣지 않고
  실제 호기가 하나라도 저장되면 샘플을 사용하지 않는다.

## 7. 조인과 데이터 검증 규칙

- 월은 내부적으로 유효한 정수 `YYYYMM`으로 정규화한다.
- 텍스트 키는 `string → strip` 후 사용한다.
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

## 8. 표시·정렬 규칙

- 내부 컬럼명은 Excel 계약과 일치시킨다. 화면 라벨 변경을 이유로 원본 컬럼명을
  바꾸지 않는다.
- 화면 표의 행 정렬은 가능한 `RQ_DISPLAY_ORDER`를 사용한다.
- 런타임 `RQ_DISPLAY_ORDER`는 `app_meta.global_display_order*`의 공용 프로필이며
  시나리오 리비전에 저장된 과거 복사본보다 우선한다.
- 적용 범위는 `페이지 구분 + 탭 구분`이다.
- `정렬우선순위`는 행 정렬 키와 화면의 왼쪽 분류컬럼 배치 순서에 함께 적용하고,
  `값표시순서`는 사용자 지정 값 순서다.
- 경로 상세가 있는 대당 Capa·UPEH·Lot/WF측정률·소요대수 표는 `STEP_SEQ → MCP_SEQ`를
  항상 마지막 분류 계층으로 둔다. 기존 공용 프로필에 두 규칙이 없으면 Repository가
  해당 페이지·탭 범위의 마지막 우선순위로 자동 보강한다.
- 지원 정렬방식은 `사용자지정`, `오름차순`, `내림차순`이다.
- 공정 표시명(Proc Rename) 규칙은 한 문장이다 — **화면은 표시명, 파일은 원본.**
  화면에서 사람이 읽는 공정명은 빠짐없이 표시명이고, 적용 계층은 다섯이다.
  ① 월별 표의 분류 값(`value_labels=`, 치환은 `components/` 안에서만 한다),
  ② `multiselect`·`selectbox` 의 `format_func=`(값은 절대 바꾸지 않는다),
  ③ Figure 라벨(LOB 공정명 annotation·hover, 상세 B/N 이름·hover, 재공 격자 제목,
  Dynamic Capa 공정 비교 막대의 y축),
  ④ `st.dataframe` 조회 표(제외·누락 안내 목록, STEP 구성 요약, 설비대수 표시 표,
  예외 처리 공정 안내, Dynamic Capa 관리 우선순위)와 화면용 안내 문구,
  ⑤ `st.data_editor` 분류 컬럼의 `st.column_config.SelectboxColumn(format_func=)` 라벨.
  편집기 두 벌(월별 편집기, HOME 의 B/N 공정 선택)의 표기는 같다 — 분류 컬럼은 언제나
  한 컬럼이고 표시용 컬럼을 따로 두지 않는다. HOME 이 적용 시 되쓰는 값도 원본 `공정` 이다.
- ④ 에서 CSV 출구가 있는 표는 **화면 프레임과 CSV 프레임을 나눈다.** 화면 복사본에만
  표시명을 입히고 내보내는 프레임은 원본 그대로다(`components/exclusion_table.py`,
  `app_pages/static_capa.py` 가 그 모양이다). 계산 결과의 `attrs` 유래 프레임은
  `@st.cache_data` 가 들고 있으므로 반드시 복사본에 입힌다.
- ⑤ 에서 **분류 컬럼의 값은 언제나 원본이다.** `SelectboxColumn` 은 옵션의 `value` 와
  `label` 을 나눠 갖고 편집 결과·복사 데이터로는 `value` 를 돌려주므로 셀에 보이는 글자만
  바뀐다. 값 자체를 표시명으로 갈면 `merge_edited_months` 의 되머지 키가 어긋나 편집이
  조용히 버려지고, 필터를 걸지 않은 단축 반환 경로에서는 표시명이 그대로 `RQ_*` 저장값이
  된다. 옵션에는 그 표의 값 전체를 넣는다 — 옵션에 없는 값은 셀이 빈칸으로 그려진다.
- 표시명이 닿으면 안 되는 곳은 다섯 갈래다. ① 왕복 CSV·클립보드 양식(기준정보 월별
  편집기, 설비대수, 주차별 가용대수, 표시순서, Proc Rename 규칙 자체), ② 보고용 CSV
  전부(월별 표 CSV, 제외 목록 CSV, Static Capa 부족 현황 CSV) — 그대로 옮겨 쓰는
  파일이다, ③ 원본 키를 편집·확인하는 화면(표시순서 관리의 `분류값`, Proc Rename 탭의
  `보유 공정` 목록), ④ `services/` 의 예외 메시지(원본을 고치라는 안내다)와 프리셋·세션
  저장값, ⑤ 설비 DB 의 `공정대분류`·`공정소분류`. 경계는 `services/` 가
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
- 월별 컬럼은 선택한 유효 조회기간만 전개한다.
- 주요 표의 분류 컬럼은 고정하고 월 컬럼은 필요할 때 가로 스크롤한다.

## 9. Streamlit 구현 규칙

- 페이지 간 공유 위젯은 `app.py`에서 `navigation.run()` 전에 만든다.
- 페이지 전용 위젯에는 고유 `key`를 부여한다.
- 페이지 이동 후에도 유지해야 하는 위젯은 현재 Streamlit 버전의
  `persist_state="session"` 패턴을 따른다.
- 비싼 계산을 탭 내부에서 직접 반복하지 않는다. 먼저 캐시된 결과를 만들고 탭은 표시만
  담당하게 한다.
- 숨은 탭에서도 입력 위젯은 항상 그리고 계산·표·차트만 건너뛴다. 본문을 `st.stop()` 으로
  통째로 접으면 Streamlit 이 그려지지 않은 위젯의 값을 버린다. `app_pages/capacity_standards.py`
  의 대당 Capa 탭이 `capacity_ready` 플래그로 이 둘을 가른다.
- **옵션을 계산 결과에서 얻는 위젯**은 닫힌 탭에서 옵션을 만들 수 없다. 이때 옵션을 빈
  리스트로 두면 위젯을 그려도 선택값이 버려지므로, 계산을 건너뛴 렌더에서는 **현재 선택값을
  그대로 옵션으로 둔다**(공정 필터 `unit_capacity_process_filter` 가 그 방식이다).
- 편집 탭의 분류 필터 상태는 `f"{editor_key}_filter_{column}"` 로 갈린다. 효율과 여유율은
  `dimensions` 가 완전히 같아 이 key 가 유일한 분리 장치다 — 새 편집 탭에 `editor_key` 를
  재사용하지 않는다.
- **`components/month_editor.py` 가 `render_reference_clipboard_tools` 에 넘기는 첫 인자와
  `key_columns` 는 반드시 필터 이전의 전체 표다.** 필터된 프레임을 넘기면 양식 CSV 가 부분
  표가 되고, 그 부분 표는 `services/reference_csv.py` 의 행 집합 검증을 통과해 조회기간의
  나머지 공정을 지운다. `tests/test_month_editor_filter.py` 가 다운로드 바이트를 실제로
  디코드해 이 계약을 고정한다.
- HOME 상세표 토글은 켜진 상태로 시작한다. 토글을 끄면 상세 Figure 를 만들지 않으며, 상세
  Figure 는 요약과 별도 캐시다.
- 여러 필터가 같은 결과를 바꾸면 `st.form`으로 묶어 중간 입력마다 전체 재실행하지 않는다.
- `use_container_width`를 새로 사용하지 말고 `width="stretch"` 또는
  `width="content"`를 사용한다.
- 단순 UI 그룹은 네이티브 `st.container(border=True)`를 우선한다.
- 복잡한 Plotly UI를 변경할 때는 월별 고정 열 너비, 좌측 라벨 Figure, 공통 가로
  스크롤 정렬을 함께 검증한다.
- HOME Plotly shape·annotation을 반복해서 추가하지 않는다. 레이아웃에 일괄 주입해
  Figure 생성 시간이 선형에 가깝게 유지되도록 한다. 칸마다 반복되는 값은 shape·
  annotation 이 아니라 배열 `text`·`customdata` 를 실은 trace 하나로 그린다.
- hover 가 필요한 Figure 만 `staticPlot` 을 끄고 같은 캔버스의 다른 Figure 설정은
  건드리지 않는다. 끄면 `displayModeBar`·`doubleClick`·`showAxisDragHandles` 가
  기본값으로 돌아가므로 셋을 직접 끄고, 드래그 확대는 축 양쪽 `fixedrange` 로 막는다.

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

## 10-1. 로컬 데이터는 합성 표본이다 — 관측을 업무 사실로 적지 않는다

`data/input/Core_Data.csv` 와 거기서 적재된 `data/capa_simulation.duckdb` 는 **실제 운영
데이터가 아니라 합성 데모 표본**이다. 공정 목록·소요기준(WF/CHIP)·성능·수율은
`scripts/generate_sample_core_data.py` 의 `PROCESS_SPECS` 리터럴에 사람이 써 넣은 값이고,
행의 팬아웃(계획 1행 × 공정 30행)도 `process_rows()` 가 계획 행을 전 공정에 복제해서
생기는 구조적 산물이다. `equipment_samples.py`, `dynamic_capacity.py` 의 `_DemoProfile`,
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

실제로 이 규칙이 없어서, 표본의 `Mold` 소요기준이 `CHIP` 인 것을 근거로 사용자의 공정
설명이 데이터와 충돌한다고 보고한 적이 있다. 충돌 상대는 실데이터가 아니라 생성기였다.

## 11. 현재 미구현 및 주의 사항

- 편집 탭의 분류 필터 선택은 탭을 옮기면 초기화된다. 페이지가 닫힌 탭의 `default_*_table` 을
  만들지 않아 `render_month_editor` 가 조기 반환하고, 그려지지 않은 위젯의 상태를 Streamlit 이
  버리기 때문이다. 화면 안내는 `month_editor.FILTER_NOTICE` 가 담당한다.

- SQLite는 실제 런타임 Repository가 아니다.
- 실행 결과 스냅샷과 사용자 권한은 미구현이다.
- 설비 운영 이력의 등록자 식별·승인 및 Capa 계산 입력 전환은 미구현이다.
- Dynamic Capa는 현재 데모 프로토타입이며 실적효율·생산실적 DB 조회, 원천 컬럼 매핑,
  누적 이력 저장소와 표준 Capa 리비전 연결은 미구현이다.
- 표준 대비 재공 현황은 결정론적 샘플을 사용하며 실제 재공 DB의 보유 재공·유입·Flow
  시점 정의, 공정·STEP·제품 매핑, 미래 3일의 계획/전망 데이터 공급 규칙은 미확정이다.
- DuckDB 쓰기 직렬화는 단일 Streamlit 서버 프로세스 범위다. 다중 서버 프로세스로
  확장할 때는 별도 쓰기 서비스 또는 서버형 DB로 전환한다.
- BOX·PCB 계산은 제외 상태다.
- `MCP_Chip_Ratio` 보정식은 미확정이다.
- BigDataQuery 실제 SQL과 컬럼 매핑은 `company_bigdataquery_adapter.py`에 커밋을 마쳤고
  `is_bigdataquery_adapter_configured()`도 참이다. 남은 것은 사내 환경에서의 접속·조회
  검증이며, 반환 DataFrame은 구현된 `CoreDataProvider` 공통 처리·DuckDB 저장 경로를
  그대로 사용한다. DataLake·Impala를 별도 원천 어댑터로 붙이는 경로는 아직 없다.
- `app_pages/home.py`는 UI 코드가 크다. 대시보드 기능을 추가할 때 계산 로직을 더 넣지
  말고 Figure 생성기 또는 서비스 모듈 분리를 우선 검토한다.

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
6. 서버 재시작 후 유지 여부를 사용자 기대와 구분해 설명

## 13. 문서 우선순위

- 실제 동작: 현재 코드와 테스트
- 확정된 업무 결정 및 향후 항목: `docs/TODO.md`
- 사용자 설치·운영 안내: `README.md`
- 개발 구조와 에이전트 작업 규칙: `AGENTS.md`
- 직전 세션 인수인계 스냅샷: `HANDOFF.md`. 정본이 아니라 그 시점 상태의 기록이므로 위 네
  항목과 어긋나면 위를 따른다.

문서와 코드가 다르면 코드만 따라가고 끝내지 말고, 차이의 원인을 확인한 후 관련 문서를
함께 수정한다.
