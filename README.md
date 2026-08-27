# Capa Simulation

Excel 2021 `.xlsb` 기준정보를 읽어 HBM PKG 라인의 월별 부하량, 대당 Capa,
소요대수, 확보율과 Bottleneck 공정을 계산하는 Streamlit 프로젝트입니다.

현재 프로토타입은 Excel을 입력 원본으로 사용하지만, 서버 실행 중에는 기준정보를
공통 캐시에 한 번만 적재합니다. 웹에서 수정한 계획·수율·Capa 기준정보는 사용자별
활성 시나리오에 반영되며, 연결된 모든 페이지의 산출 결과에 즉시 적용됩니다.

## 현재 구현 범위

- PKG·Chip·Wafer·Density 월별 부하량 환산
- PKG PLAN 및 EDS·BE 수율 웹 편집
- UPEH·ST·효율·여유율·가동일수·측정률 기반 상세 대당 Capa 산출과 공정별 부하량 가중평균 조회
- `RQ_REQB` 공정 경로별 소요대수 산출
- 보유·대여·가용 설비대수 조회
- 공정별 확보율 및 월별 B/N 공정 산출
- Density·Wafer Capa 요약과 선택형 계획·B/N 상세 HOME 대시보드
- Excel 기준정보 공통 캐시와 사용자별 활성 시나리오
- `기준정보 정합성 관리` 아래 가용설비 현황·실적 효율·UPEH 실적 하위 페이지

`B/N 분석`, `시나리오 및 결과`와 기준정보 정합성 관리의 세 하위 페이지는 현재
확장용 화면이며, 세부 데이터 연결은 후속 단계에서 구현합니다.

## 구조 요약

```text
templates/structure_template.xlsb
        ↓ xlwings
공통 기준정보 캐시 (서버)
        ├─ 수정하지 않는 RQ 기준정보
        └─ 사용자별 활성 시나리오 (세션)
                ↓
부하량 → 대당 Capa → 소요대수 → 확보율 → B/N
                ↓
Streamlit 페이지 및 HOME 대시보드
```

주요 디렉터리:

```text
app.py                         Streamlit 실행 진입점과 공통 사이드바
app_pages/                     페이지별 UI
src/capa_simulation/components/ Streamlit 커스텀 UI 컴포넌트
src/capa_simulation/io/        Excel 로더와 기준정보 캐시
src/capa_simulation/services/  계산·정렬·표 변환 로직
src/capa_simulation/scenario_state.py
                               사용자별 활성 시나리오
src/capa_simulation/performance.py
                               HOME 단계별 성능 계측
templates/                     로컬 XLSB 입력 파일 위치
scripts/                       샘플 생성·SQLite 이관·HOME 벤치마크 도구
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

XLSB 및 SQLite 파일은 로컬 데이터이므로 Git에 포함되지 않습니다.

## 캐시와 시나리오

- Excel 기준정보는 서버 프로세스에서 공통으로 캐시됩니다.
- 동일 입력의 부하량·Capa·소요대수·확보율과 HOME 전체 계산 그래프를 재사용합니다.
- HOME은 기본 진입 시 요약 Figure만 만들고, `계획·B/N 상세표 표시`를 켰을 때 상세
  Figure를 별도 생성·캐시합니다.
- B/N 임계값과 포함 공정은 폼의 `조건 적용`을 누를 때 한 번에 반영됩니다.
- `HOME 성능 진단`을 켜면 데이터 노출 없이 단계별 소요시간과 Figure 캐시 적중 여부를
  확인할 수 있습니다.
- 웹 편집값은 브라우저 세션별 활성 시나리오에만 저장됩니다.
- 페이지를 이동해도 편집값은 유지되고 다른 산출 페이지에 반영됩니다.
- 브라우저 세션 종료 또는 서버 재시작 후에는 편집값이 유지되지 않습니다.
- `기준정보 새로고침`은 Excel·계산·활성 시나리오 캐시를 초기화합니다.

현재 `data/capa_simulation.db`는 Excel/SQLite 병행 검증용이며 앱의 실제 입력원은
아닙니다.

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
```

## 현재 주요 미구현 항목

- 시나리오 영구 저장·불러오기 및 사용자 권한
- DataLake·BigDataQuery 실제 연결
- BOX·PCB 부하량과 Capa 산식
- `MCP_Chip_Ratio` 소요대수 보정
- B/N 분석 상세 화면
- 결과 다운로드 및 실행 이력
