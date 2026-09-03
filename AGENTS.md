# Capa Simulation 개발 에이전트 가이드

이 문서는 저장소 전체에 적용되는 개발 인수인계 문서다. 작업을 시작하기 전에
`README.md`, 이 문서, `docs/TODO.md`를 읽고 실제 코드와 함께 현재 상태를 확인한다.
구조나 핵심 계산 규칙을 변경하면 이 문서와 README도 같은 변경에서 갱신한다.

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
적재와 pandas 기반 16개 RQ 변환은 구현되었고, DataLake·BigDataQuery 실제 조회
어댑터만 사내 환경에서 연결해야 한다.

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
    제공한다. 이름 변경·공식 발행·보관·신규 시나리오 생성은 독립 관리 페이지에 둔다.
  - 시나리오 저장소가 완전히 비어 있으면 최신 공식 리비전 활성화 전에 내장 합성 시드를
    생성·공식 발행한다.
- `app_pages/home.py`
  - 전체 계산 결과를 조합하는 HOME 대시보드다.
  - Plotly Figure 묶음을 사용자 세션에 캐시하고 렌더링은 fragment로 분리한다.
  - 기본 진입은 Density·Wafer Capa 요약만 만들며 계획·B/N 상세표는 사용자 선택 시 지연 생성한다.
  - B/N 임계값과 포함 공정은 사이드바 form 제출 시 한 번에 적용하고, 성능 진단 토글은
    단계별 시간과 Figure 캐시 적중 여부만 표시한다.
- `app_pages/load_conversion.py`
  - `환산`, `PKG PLAN`, `수율` 탭을 제공한다.
  - 계획과 수율 편집값을 활성 시나리오에 반영한다.
  - PKG PLAN과 수율의 현재 월별 Wide 표를 CSV로 내려받아 값만 일괄 수정·적용한다.
- `app_pages/capacity_standards.py`
  - 기본 `공정 유효 Capa`는 중복되지 않은 원수요 부하량을 STEP별 소요대수 합계로 나눈
    화면용 결과이며, STEP별 상세 대당 Capa와 공정 필터도 제공한다.
  - `STEP 구성`은 선택한 경로를 실제 MCP·STEP 식별값으로 복제하거나 삭제하고 연결된
    모든 Capa Code·Customer·CS 변형을 `RQ_REQB`·UPEH·Lot/WF 측정률에 함께 반영한다.
  - 확보율 계산용 상세 대당 Capa는 변경하지 않고 UPEH·효율·여유율·측정률·일수 편집 탭을 제공한다.
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
  - 호기 마스터는 호기, 비가동 일정은 호기·유형·시작일 자연키로 Import하며
    신규·대체·변경 컬럼 미리보기와 편집본 적용 확인 후 별도로 리비전을 저장한다.
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
- `app_pages/scenario_management.py`
  - `시나리오 관리`, `BigDataQuery 등록`, `표시순서 관리` 탭을 제공한다.
  - DuckDB 시나리오·리비전 선택, 이름 수정, 공식버전 발행, 불러오기와 논리 보관을 제공한다.
  - 신규 시나리오는 개발용 Core Data CSV를 pandas 변환해 typed raw와 RQ 16개를 함께
    저장하거나 현재 RQ 16개를 독립 데이터셋으로 복제한다.
  - Core Data CSV·BigDataQuery로 새 원천 시나리오를 만들 때 초기 프리셋은 원천의 전체
    생산계획년월, 전체 B/N 공정과 전체 표준 목표 Capa 공정을 기본 조회 범위로 사용한다.
    현재 활성 화면의 축소 조회기간이나 공정 제외 상태를 새 원천에 복사하지 않는다.
  - 새 리비전은 편집 가능한 12개 RQ와 사이드바 프리셋의 전체 스냅샷을 저장한다.
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
  - 공정 필터는 리비전에 공용 기본값으로 저장하되 페이지 변경은 사용자 세션에만 적용한다.
    현재 선택을 신규 리비전으로 저장하면 다음 공용 기본값이 되며 빈 목록은 전체 공정이다.
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
    미저장 편집을 버리는 불러오기는 확인 입력을 요구한다. 이름 변경·공식 발행·보관·신규
    시나리오 생성은 독립 `시나리오 관리` 페이지에서 수행한다.
- `src/capa_simulation/components/space_layout.py`
  - FAB 동·층 정의, 설치 단계·양산·운영 비가동 집계와 3단계 Plotly Figure를 생성한다.
  - 층 상세를 100×60 논리 좌표계로 렌더링하며, 향후 실제 레이아웃 이미지를 배경으로
    주입할 수 있는 `background_image` 경계를 제공한다.
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
- `src/capa_simulation/io/company_bigdataquery_adapter.py`
  - 사내 SQL과 DB 컬럼 매핑을 넣는 전용 접속부다. `bigdataquery`를 지연 import하고 반환
    DataFrame을 CSV로 저장하지 않고 공통 78컬럼 파이프라인에 전달한다.
- `src/capa_simulation/io/reference_cache.py`
  - 현재 브라우저 세션에 활성화된 DuckDB 리비전의 테이블과 공용 표시순서를 반환한다.
  - 활성 리비전이 없으면 XLSB로 대체하지 않고 명확한 오류를 반환한다.
- `src/capa_simulation/persistence/`
  - 시뮬레이션과 설비 운영의 DuckDB 마이그레이션·Repository·캐시를 서로 독립된 모듈과
    물리 DB 파일로 관리한다.
  - 설비 운영 데이터는 전용 DB의 `equipment_meta`, `equipment_ops` 스키마에서 전체
    스냅샷 리비전으로 보존한다.
  - 쓰기는 프로세스 잠금과 단일 트랜잭션으로 직렬화하고, 읽기는 작업별 연결을 사용한다.
  - 불변 `revision_id`의 전체 스냅샷만 `st.cache_data`로 여러 세션에 공유하며 목록과
    변경 가능한 메타데이터는 캐시하지 않는다.
  - 시나리오 생성 시 typed Core Data raw, 컬럼 프로파일, RQ 16개, 초기 리비전과
    프리셋을 한 트랜잭션으로 저장한다.
  - `app_meta.global_display_order*`는 시나리오와 독립된 단일 공용 프로필이며 최초 생성 시
    기존 리비전 또는 로컬 CSV/내장 시드에서 이관하고 이후 전체 교체 이력을 버전으로 관리한다.
  - 프리셋은 조회기간·B/N 포함 공정·표준 목표 Capa 공정 기본값·확보/경고 기준을 소유한다.
  - 공식버전은 불변 리비전을 가리키는 append-only 발행 이력이며 최신 발행이 새 세션의
    기본 리비전이 된다.
  - 표준 목표 Capa의 수동 주차별 가용대수만 설비 DB의 비버전 최신값 테이블에
    공정·Weeknum 기준으로 갱신한다.
- `src/capa_simulation/scenario_state.py`
  - 사용자 세션별 활성 시나리오와 `revision`을 관리한다.
  - 선택한 월 범위만 원자적으로 교체한다.
  - HOME처럼 계산용 월 범위만 필요한 경로는 전체 시나리오 복사 없이 선택 행만 복사한다.
- `src/capa_simulation/scenario_activation.py`, `scenario_preset_state.py`
  - 저장된 리비전의 16개 테이블과 편집 상태를 현재 세션에 원자적으로 활성화한다.
  - 조회기간·B/N 포함 공정·표준 목표 Capa 공정 기본값·확보/경고 기준은 공통 위젯 생성
    전에 대기 프리셋으로 복원한다.
  - 새 세션에서는 최신 공식 리비전을 한 번 자동 활성화한다.
- `src/capa_simulation/performance.py`
  - HOME 단계별 소요시간을 측정하며 업무 데이터는 기록하지 않는다.
- `src/capa_simulation/services/simulation_cache.py`
  - 주요 계산 함수의 content-addressed `st.cache_data` 래퍼다.
  - HOME 전체 계산 그래프를 상위 캐시로 감싸 warm rerun의 중복 DataFrame 해싱을 줄이고,
    하위 계산 캐시는 다른 페이지와 계속 공유한다.

### 계산 서비스

- `load_calculator.py`: 계획/수율 편집 변환과 PKG·Chip·Wafer·Density 부하량. HOME의
  Chip·Wafer 부하량은 공통 전처리를 한 번만 수행한다.
- `unit_capacity.py`: Main/MI 환산 UPEH와 대당 Capa
- `weighted_unit_capacity.py`: 중복되지 않은 원수요 부하량과 STEP별 소요대수 합으로
  공정 유효 Capa를 만들며 기존 부하량 가중평균 조회 함수도 호환용으로 유지
- `standard_target_capacity.py`: ER 제외 월간 공정 유효 Capa의 일 환산, ISO 주차 캘린더,
  수동 가용대수 표 계약과 주차별 일 표준 가능량
- `route_step_editor.py`: MCP·STEP 고유 조합 수와 네 경로 테이블의 일괄 복제·삭제
- `required_equipment.py`: RQ_REQB 경로 연결과 소요대수
- `securement_rate.py`: 공정별 확보율과 경고·확보 기준별 최소 정수 추가 필요대수
- `equipment_count.py`: 보유·대여·가용 설비대수 표
- `equipment_availability.py`: 기존 보유대수, 30컬럼 호기 일정과 운영 비가동 검증,
  월요일 시작 주차별 총대수·가용대수·비가동대수, 비가동 호기, Space 단계와 기간별 단계
  전환 이벤트 원천. 설비 DB가 비어 있을 때 사용하는 개발용 Core Data 기반 30개 공정
  보유대수 샘플과 호기 마스터가 비었을 때만 대시보드에 표시하는 단계별 임시 호기 샘플을
  제공한다. 임시 호기와 비가동 샘플은 DB에 저장하지 않는다.
- `equipment_csv.py`: 호기 마스터와 비가동 일정의 CSV 양식 생성, Excel 붙여넣기 표
  검증·자연키 기준 병합. 다운로드 양식은 2행에 서로 연결되는 입력 예시를 포함하고
  비고에 샘플 행 삭제 안내를 둔다.
- `dashboard.py`: HOME 월별 집계, B/N 단일 월별 순위에서 파생하는 Top 1·5·10, Wafer Capa
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
```

웹 수정은 반드시 `apply_month_updates()`를 통해 반영한다. 페이지 전용 DataFrame만
수정하고 끝내면 다른 페이지와 계산 캐시에 변경이 전달되지 않는다.

### 읽기 전용 참조 테이블

```text
RQ_CHIP_QTY
RQ_CHIP_EQ
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
3. **편집 적용마다 revision을 증가시킨다.** 다른 페이지는 revision 변경으로 편집 UI와
   결과를 갱신한다.
4. **계산 함수는 가능한 순수 함수로 유지한다.** Streamlit 캐시는 `simulation_cache.py`
   래퍼에 두고 서비스 함수 내부에 UI 상태 접근을 넣지 않는다.
5. **공식버전은 append-only다.** 특정 시나리오·리비전을 새 공식버전으로 발행하며 과거
   공식 이력을 갱신하지 않는다. 최신 공식 시나리오는 다른 공식 발행 전 보관하지 않는다.
6. **미저장 편집과 저장 리비전을 구분한다.** 미저장 편집은 세션 종료 후 사라지며,
   `시나리오 관리`에서 저장한 리비전만 DuckDB에 영구 보존된다.
7. **완성 Figure 캐시 키에는 출력에 영향을 주는 모든 조건을 포함한다.** 시나리오
   revision, reference version, 조회기간, B/N 공정 선택, 임계값과 Figure schema version을
   누락하지 않는다.
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
12. **공용 필터 기본값과 개인 조회를 분리한다.** 표준 목표 Capa 공정 기본값은 불변
    리비전 프리셋에 저장하고, 페이지에서 바꾼 값은 현재 세션에만 둔다. 신규 리비전 저장
    시점에만 현재 세션 선택을 다음 공용 기본값으로 캡처한다.
13. **표시순서는 시나리오에 종속시키지 않는다.** 공용 표시순서는 별도 DB 프로필에서
    읽고 Excel 표 붙여넣기 또는 직접 편집으로 원자 교체한다. 시나리오 전환·신규 생성 시에는
    항상 현재 공용 프로필을 적용하며 표시순서 변경만으로 리비전을 만들지 않는다.

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

Dummy Chip/Wafer는 `(1 - EDS_수율)`을 추가 적용한다. `WF 구분`의 Dummy 판별은 기존
리비전과 BigDataQuery의 표기 차이를 흡수하도록 대소문자와 앞뒤 공백에 의존하지 않는다.
정확한 현재 구현은 `load_calculator.py`와 `docs/TODO.md`를 기준으로 한다.

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
- WF측정률 0 이하 및 대당 Capa 0 이하는 제외 행으로 남기고 계산에서 제외
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
- 주차는 월요일 시작 ISO Weeknum(`YY-W##`)이며 월 경계 주차에는 월요일이 속한 달의
  월간 Capa와 `RUN_DAY`를 적용한다.
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
- 월별 컬럼은 선택한 유효 조회기간만 전개한다.
- 주요 표의 분류 컬럼은 고정하고 월 컬럼은 필요할 때 가로 스크롤한다.

## 9. Streamlit 구현 규칙

- 페이지 간 공유 위젯은 `app.py`에서 `navigation.run()` 전에 만든다.
- 페이지 전용 위젯에는 고유 `key`를 부여한다.
- 페이지 이동 후에도 유지해야 하는 위젯은 현재 Streamlit 버전의
  `persist_state="session"` 패턴을 따른다.
- 비싼 계산을 탭 내부에서 직접 반복하지 않는다. 먼저 캐시된 결과를 만들고 탭은 표시만
  담당하게 한다.
- HOME 기본 경로에는 요약 Figure만 두고 큰 계획·B/N 표는 명시적 상세 토글 뒤에서 생성한다.
- 여러 필터가 같은 결과를 바꾸면 `st.form`으로 묶어 중간 입력마다 전체 재실행하지 않는다.
- `use_container_width`를 새로 사용하지 말고 `width="stretch"` 또는
  `width="content"`를 사용한다.
- 단순 UI 그룹은 네이티브 `st.container(border=True)`를 우선한다.
- 복잡한 Plotly UI를 변경할 때는 월별 고정 열 너비, 좌측 라벨 Figure, 공통 가로
  스크롤 정렬을 함께 검증한다.
- HOME Plotly shape·annotation을 반복해서 추가하지 않는다. 레이아웃에 일괄 주입해
  Figure 생성 시간이 선형에 가깝게 유지되도록 한다.

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

## 11. 현재 미구현 및 주의 사항

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
- DataLake·Impala·BigDataQuery 실제 SQL과 컬럼 매핑은 외부 PC에서 확정하지 않는다.
  `company_bigdataquery_adapter.py`의 설정 영역만 사내에서 채우고, 반환 DataFrame은 구현된
  `CoreDataProvider` 공통 처리·DuckDB 저장 경로를 그대로 사용한다.
- `app_pages/home.py`는 UI 코드가 크다. 대시보드 기능을 추가할 때 계산 로직을 더 넣지
  말고 Figure 생성기 또는 서비스 모듈 분리를 우선 검토한다.

## 12. 변경 작업 체크리스트

### 입력 테이블 또는 컬럼 변경

1. `config/data_contract.yaml`과 사내 DB 컬럼 매핑 확인
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
3. revision 증가 확인
4. 다른 페이지에서 수정값 반영 확인
5. 페이지 왕복 후 입력값 유지 확인
6. 서버 재시작 후 유지 여부를 사용자 기대와 구분해 설명

## 13. 문서 우선순위

- 실제 동작: 현재 코드와 테스트
- 확정된 업무 결정 및 향후 항목: `docs/TODO.md`
- 사용자 설치·운영 안내: `README.md`
- 개발 구조와 에이전트 작업 규칙: `AGENTS.md`

문서와 코드가 다르면 코드만 따라가고 끝내지 말고, 차이의 원인을 확인한 후 관련 문서를
함께 수정한다.
