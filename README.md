# Capa Simulation

Excel 2021 `.xlsb` 기준정보를 읽어 HBM PKG 라인의 월별 부하량, 대당 Capa,
소요대수, 확보율과 Bottleneck 공정을 계산하는 Streamlit 프로젝트입니다.

현재 프로토타입은 Excel을 입력 원본으로 사용하지만, 서버 실행 중에는 기준정보를
공통 캐시에 한 번만 적재합니다. 웹에서 수정한 계획·수율·Capa 기준정보는 사용자별
활성 시나리오에 반영되며, 연결된 모든 페이지의 산출 결과에 즉시 적용됩니다.

## 현재 구현 범위

- PKG·Chip·Wafer·Density 월별 부하량 환산
- PKG PLAN 및 EDS·BE 수율 웹 편집
- UPEH·ST·효율·여유율·가동일수·측정률 기반 대당 Capa 산출
- `RQ_REQB` 공정 경로별 소요대수 산출
- 보유·대여·가용 설비대수 조회
- 공정별 확보율 및 월별 B/N 공정 산출
- Density·Wafer Capa·B/N Top 5·10 HOME 대시보드
- Excel 기준정보 공통 캐시와 사용자별 활성 시나리오

`B/N 분석`과 `시나리오 및 결과` 페이지는 현재 확장용 빈 페이지입니다.

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
src/capa_simulation/io/        Excel 로더와 기준정보 캐시
src/capa_simulation/services/  계산·정렬·표 변환 로직
src/capa_simulation/scenario_state.py
                               사용자별 활성 시나리오
templates/                     로컬 XLSB 입력 파일 위치
scripts/                       샘플 생성 및 SQLite 이관 도구
tests/                         계산·캐시·시나리오 테스트
docs/TODO.md                   결정 이력과 작업 목록
AGENTS.md                      개발 에이전트용 구조·규칙 문서
```

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
- 동일 입력의 부하량·Capa·소요대수·확보율 계산 결과도 재사용됩니다.
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
```

## 현재 주요 미구현 항목

- 시나리오 영구 저장·불러오기 및 사용자 권한
- DataLake·BigDataQuery 실제 연결
- BOX·PCB 부하량과 Capa 산식
- `MCP_Chip_Ratio` 소요대수 보정
- B/N 분석 상세 화면
- 결과 다운로드 및 실행 이력
