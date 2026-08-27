# Capa Simulation

Excel 2021 `.xlsb` 기준정보를 읽어 HBM PKG 라인의 월별 부하량, 대당 Capa,
소요대수, 확보율과 Bottleneck 공정을 계산하는 Streamlit 프로젝트입니다.

현재 기본 입력은 Excel이지만, 저장한 시나리오는 로컬 DuckDB에서 다시 불러옵니다.
서버 실행 중 기준정보는 공통 캐시에 한 번만 적재하고, 웹에서 수정한 계획·수율·Capa
기준정보는 사용자별 활성 시나리오에 반영되어 연결된 모든 페이지의 결과를 다시 계산합니다.

## 현재 구현 범위

- PKG·Chip·Wafer·Density 월별 부하량 환산
- PKG PLAN 및 EDS·BE 수율 웹 편집
- UPEH·ST·효율·여유율·가동일수·측정률 기반 상세 대당 Capa 산출과 공정별 부하량 가중평균 조회
- `RQ_REQB` 공정 경로별 소요대수 산출
- 보유·대여·가용 설비대수 조회
- 공정별 확보율 및 월별 B/N 공정 산출
- Density·Wafer Capa 요약과 선택형 계획·B/N 상세 HOME 대시보드
- Excel 기준정보 공통 캐시와 사용자별 활성 시나리오
- Core Data 78컬럼 계약, pandas Power Query 대체 변환과 typed DuckDB raw 적재
- DuckDB 기반 시나리오·불변 리비전·조회/판정 프리셋 저장 및 복원
- 사이드바 샘플 시나리오·리비전 선택 인터페이스 데모
- 호기별 입고·셋업 일정과 기존 보유대수의 DuckDB 이력 저장
- 공정·분류별 주차 단위 총대수·가용대수·비가동대수 대시보드
- HOME 하단 독립 메뉴의 `Capa Chatbot` 대화형 분석 화면 초안
- `Static Capa` 아래 부하량·공정별 Capa·공정별 확보율·B/N 분석·시나리오 및 결과 페이지
- `Dynamic Capa` 아래 가용설비 현황·실적 효율·UPEH 실적·Space 현황 페이지

`실적 효율`과 `UPEH 실적`은 기준 대비 Gap, 공정·제품 개선 우선순위와 개선과제 관리
구조까지 화면 초안으로 구현했으며 실제 생산이력 DB와 Capa 기준정보 연결은 후속 단계입니다.
`Capa Chatbot`은 추천 질문, 대화 영역, 연결 상태와 답변 근거 표시 구조만 구현했으며
LLM API·Capa 데이터·권한 및 대화 이력은 아직 연결하지 않습니다.
`Space 현황`은 `FAB 전체 → 동별 층 → 층 상세 배치`의 3단계 클릭 탐색과 설비별
`X·Y·너비·높이·상태` 편집 초안까지 구현했습니다. 현재 수량·좌표는 데모이며 층별
레이아웃 이미지, 실제 설비 배치와 Space Capa 데이터 연결은 후속 단계입니다.
`B/N 분석`은 현재 확장용 화면입니다.

## 구조 요약

```text
templates/structure_template.xlsb
        ↓ xlwings
공통 기준정보 캐시 (서버)
        ↔ 사용자별 활성 시나리오 (세션)
        ↕ 저장/불러오기
data/input/Core_Data.csv ── pandas 변환 ──┐
                                         ↓
data/capa_simulation.duckdb
        ├─ 시나리오별 Core Data 78컬럼 raw 스냅샷
        ├─ 시나리오별 독립 RQ 16개 데이터셋
        └─ 리비전별 편집 테이블·표시순서·프리셋
                ↓ 활성 리비전
부하량 → 대당 Capa → 소요대수 → 확보율 → B/N
                ↓
Streamlit 페이지 및 HOME 대시보드

data/equipment_availability.duckdb
        └─ 설비 기존 보유대수·호기 일정의 불변 저장 이력
                ↓
가용설비 현황 전용 주차 집계·대시보드
```

주요 디렉터리:

```text
app.py                         Streamlit 실행 진입점과 공통 사이드바
app_pages/                     페이지별 UI
src/capa_simulation/components/ Streamlit 커스텀 UI 컴포넌트
src/capa_simulation/io/        Excel 로더, Core Data 어댑터와 기준정보 캐시
src/capa_simulation/persistence/
                               DuckDB 마이그레이션·Repository·데이터 모델
src/capa_simulation/services/  계산·정렬·표 변환 로직
src/capa_simulation/scenario_state.py
                               사용자별 활성 시나리오
src/capa_simulation/scenario_activation.py
                               저장 리비전의 테이블·프리셋 활성화
src/capa_simulation/performance.py
                               HOME 단계별 성능 계측
templates/                     로컬 XLSB 입력 파일 위치
scripts/                       통합 검증·SQLite 이관·HOME 벤치마크 도구
tests/                         계산·캐시·시나리오 테스트
docs/TODO.md                   결정 이력과 작업 목록
AGENTS.md                      개발 에이전트용 구조·규칙 문서
```

공통 사이드바의 조회기간은 시작 월과 종료 월을 각각 선택하는 월 캘린더로 제공되며,
선택한 범위는 모든 페이지의 월별 조회와 계산에 동일하게 적용됩니다.
부하량 페이지의 환산 결과는 고정된 분류 영역과 가로 스크롤되는 월별 영역으로 나누어
표시하며, 동일 분류값은 정렬 결과에 따라 계층적으로 그룹화됩니다. 각 제품 아래에는
`Total`, 각 양산구분 아래에는 양산구분 Total이 배치되고 전체 합계는 헤더 바로 아래 2행에 표시됩니다.
현재 소요기준·상세 여부·조회기간이 반영된 환산 결과는 UTF-8 CSV로 내려받을 수 있습니다.
대당 Capa, 확보율과 소요대수 결과도 현재 집계 수준·공정 및 분류 필터·상세 여부·조회기간을
반영한 UTF-8 CSV로 내려받을 수 있습니다.

자세한 개발 구조와 변경 규칙은 [AGENTS.md](AGENTS.md), 확정사항과 향후 계획은
[docs/TODO.md](docs/TODO.md)를 참고합니다.

## 입력 데이터

실행 파일은 다음 고정 경로를 사용합니다.

```text
templates/structure_template.xlsb
```

Workbook에는 다음 이름의 Excel Table이 필요합니다.

```text
RQ_PKG_PLAN        RQ_YLD           RQ_CHIP_QTY
RQ_CHIP_EQ         RQ_DISPLAY_ORDER RQ_REQB
RQ_UPEH            RQ_RUN_RATE      RQ_VITAL
RQ_MODULE          RQ_RUN_DAY       RQ_LOT_RATIO
RQ_WF_RATIO        RQ_EQP_OWN       RQ_EQP_LENT
RQ_EQP_AVBL
```

Python은 Power Query를 직접 새로고침하지 않고 Workbook에 마지막으로 저장된
Excel Table 값을 읽습니다. 원본 데이터를 변경할 때는 다음 순서를 사용합니다.

1. Excel에서 Power Query를 새로고침합니다.
2. `structure_template.xlsb`를 저장하고 닫습니다.
3. Streamlit 사이드바에서 `기준정보 새로고침`을 실행합니다.

신규 시나리오의 원천 적재 개발 검증에는 다음 파일을 사용합니다.

```text
data/input/Core_Data.csv
```

`시나리오 및 결과 → 신규 저장 → Core Data CSV`를 선택하면 cp949 CSV를 pandas로 읽어
78개 컬럼 타입과 월 형식을 검증하고, XLSB Power Query와 동일한 규칙으로 RQ 16개를
생성합니다. 원천 행·컬럼 프로파일·RQ 기본 스냅샷·초기 리비전·화면 프리셋은 하나의
DuckDB 트랜잭션으로 저장됩니다. `RQ_DISPLAY_ORDER`는 Core Data에서 만들지 않는 수동
관리 기준이므로 현재 XLSB 테이블을 입력으로 사용합니다. 사내 운영에서는 CSV 어댑터만
BigDataQuery DataFrame 어댑터로 교체하고 이후 파이프라인은 그대로 사용합니다.

XLSB, SQLite 및 DuckDB 파일은 로컬 데이터이므로 Git에 포함되지 않습니다. 시뮬레이션
DuckDB는 `data/capa_simulation.duckdb`, 설비 운영 전용 DuckDB는
`data/equipment_availability.duckdb`를 사용합니다.

## 캐시와 시나리오

- 사이드바의 `활성 시나리오` 선택기는 현재 UI 검토용 샘플이다. 선택 완료 상태만 브라우저
  세션에 저장하며 DuckDB, RQ 기준정보, 조회기간 프리셋과 계산 결과에는 적용하지 않는다.

- Excel 기준정보는 서버 프로세스에서 공통으로 캐시됩니다.
- 동일 입력의 부하량·Capa·소요대수·확보율과 HOME 전체 계산 그래프를 재사용합니다.
- HOME은 기본 진입 시 요약 Figure만 만들고, `계획·B/N 상세표 표시`를 켰을 때 상세
  Figure를 별도 생성·캐시합니다.
- B/N 임계값과 포함 공정은 폼의 `조건 적용`을 누를 때 한 번에 반영됩니다.
- `HOME 성능 진단`을 켜면 데이터 노출 없이 단계별 소요시간과 Figure 캐시 적중 여부를
  확인할 수 있습니다.
- 저장하지 않은 웹 편집값은 브라우저 세션별 활성 시나리오에만 존재합니다.
- 페이지를 이동해도 편집값은 유지되고 다른 산출 페이지에 반영됩니다.
- `시나리오 및 결과`에서 신규 시나리오 또는 리비전으로 저장하면 서버 재시작 후에도
  DuckDB에서 다시 불러올 수 있습니다.
- 동일 시뮬레이션 코드는 원천 내용이 바뀌지 않는 불변 데이터로 취급합니다. 동일한 raw
  스냅샷의 새 시나리오 물리 복제는 허용하지만 내용이 다르면 등록을 거부하고 기존
  시나리오의 새 리비전으로 관리합니다.
- 리비전은 편집 가능한 8개 RQ 테이블과 `RQ_DISPLAY_ORDER`, 조회기간·포함 공정·확보율
  판정 기준의 전체 스냅샷입니다. 과거 리비전은 변경하지 않으며 과거 시점에서 분기할 수 있습니다.
- 시나리오 보관은 논리 상태 변경이며 데이터를 물리 삭제하지 않습니다.
- `기준정보 새로고침`은 저장 데이터를 삭제하지 않고 Excel·계산·현재 활성 시나리오
  캐시만 초기화하여 XLSB 기준으로 돌아갑니다.

## 가용설비 현황 관리

- 설비 전용 DB가 비어 있으면 개발용 Core Data 샘플의 30개 공정별 `설비보유` 값을
  기존 보유대수 초기 샘플로 표시합니다. 원본에 2차 분류가 없어 `분류=전체`로 표시하며,
  사용자가 첫 이력을 저장하기 전에는 DB에 기록하지 않습니다.
- 기존 보유대수와 공정명은 설비 전용 입력표에서 직접 등록합니다.
- 기존 보유대수는 전체 조회기간에 즉시 가용한 기준 대수입니다.
- 신규 호기는 입고일이 포함된 주부터 총대수에, 셋업완료일이 포함된 주부터 가용대수에
  반영됩니다. 입고 후 셋업완료 전까지는 비가동대수입니다.
- 주차는 월요일부터 일요일까지의 ISO Weeknum(`YY-W##`)으로 표시하며, 가용설비
  페이지 상단에서 시뮬레이션과 독립된 조회기간을 설정합니다.
- 일정 저장은 현재 데이터를 덮어쓰지 않고 DuckDB에 전체 스냅샷 리비전을 추가합니다.
  과거 리비전의 기존 보유대수와 호기별 일정을 화면에서 다시 확인할 수 있습니다.
- 이 대시보드의 운영 가용대수는 현재 `RQ_EQP_AVBL`을 사용하는 Capa·확보율 계산을
  대체하지 않습니다.
- 설비 페이지는 시뮬레이션 시나리오 DB, 활성 리비전, `RQ_*` 기준정보와 Capa 계산 캐시를
  읽지 않습니다. 향후 정합성 검증이 끝난 뒤 별도 연결 계층에서 공정명을 키로 연계합니다.

현재 `data/capa_simulation.db`는 과거 Excel/SQLite 병행 검증용이며 앱에서 읽지 않습니다.
두 DuckDB 파일은 서로 독립된 로컬 저장소이며, 단일 Streamlit 서버 프로세스 안에서 각
Repository의 쓰기를 별도 잠금과 DB 트랜잭션으로 직렬화합니다. 상세 모델은
[docs/data_model.md](docs/data_model.md)를 참고합니다.

## 권장 실행 환경

- Windows 10/11
- Microsoft Excel 2021 또는 Microsoft 365 Desktop
- Python 3.10.11 64-bit
- Git for Windows

## 초기 설정

```powershell
py -3.10 --version
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-dev.txt
```

PowerShell에서 가상환경 활성화 스크립트가 차단되면 조직 보안 정책에 맞게 실행
정책을 확인합니다. 활성화하지 않고도 `.venv`의 실행 파일을 직접 사용할 수 있습니다.

## 실행

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## 검증

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe scripts\benchmark_home.py
.\.venv\Scripts\python.exe scripts\validate_duckdb_persistence.py
```

## 현재 주요 미구현 항목

- DataLake·BigDataQuery 실제 조회 어댑터와 원천 등록시각 연결
- `RQ_DISPLAY_ORDER` 웹 관리 화면과 사용자 권한
- BOX·PCB 부하량과 Capa 산식
- `MCP_Chip_Ratio` 소요대수 보정
- B/N 분석 상세 화면
- 결과 다운로드 및 실행 이력
