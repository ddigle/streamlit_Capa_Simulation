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

현재 런타임 원본은 `templates/structure_template.xlsb`다. SQLite 파일은 병행 검증용이며
앱에서 읽지 않는다. DataLake·BigDataQuery 연동과 시나리오 영구 저장은 아직 구현되지
않았다.

## 2. 실행환경과 검증 기준

- 운영 호환 Python: **3.10.11 64-bit**
- UI: Streamlit 멀티페이지 앱
- 데이터 처리: pandas
- 차트: Plotly
- Excel 읽기: xlwings, Workbook 숨김·읽기 전용
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

Streamlit 페이지나 상태를 변경했다면 `streamlit.testing.v1.AppTest` 또는 실제 브라우저로
해당 페이지 진입, 수정, 페이지 왕복과 예외 여부를 추가 검증한다.

## 3. 파일별 책임

### 실행과 UI

- `app.py`
  - 유일한 실행 진입점이다.
  - `st.navigation` 페이지 목록, 공통 사이드바, 조회기간, 기준정보 새로고침을 관리한다.
  - 모든 페이지에 필요한 전역 위젯은 `navigation.run()`보다 앞에 둔다.
- `app_pages/home.py`
  - 전체 계산 결과를 조합하는 HOME 대시보드다.
  - Plotly Figure 묶음을 사용자 세션에 캐시하고 렌더링은 fragment로 분리한다.
- `app_pages/load_conversion.py`
  - `환산`, `PKG PLAN`, `수율` 탭을 제공한다.
  - 계획과 수율 편집값을 활성 시나리오에 반영한다.
- `app_pages/capacity_standards.py`
  - `대당 Capa` 결과와 UPEH·효율·여유율·측정률·일수 편집 탭을 제공한다.
- `app_pages/process_securement.py`
  - `확보율`, `소요대수`, `설비대수` 탭을 제공한다.
- `app_pages/bottleneck_analysis.py`, `app_pages/scenarios.py`
  - 현재 제목만 있는 확장용 페이지다.

페이지 파일은 직접 실행되는 Streamlit 스크립트 형태를 유지한다. 복잡한 계산을 페이지에
추가하지 말고 `src/capa_simulation/services/`로 옮긴다.

### 입력과 상태

- `src/capa_simulation/io/excel_reader.py`
  - 16개 `RQ_*` Excel Table을 DataFrame으로 읽는다.
  - Power Query를 새로고침하지 않는다. 저장된 Table 결과만 읽는다.
- `src/capa_simulation/io/reference_cache.py`
  - Excel 전체를 `st.cache_data`로 서버 공통 캐시한다.
  - 명시적 새로고침 세대를 `reference_version`으로 관리한다.
- `src/capa_simulation/scenario_state.py`
  - 사용자 세션별 활성 시나리오와 `revision`을 관리한다.
  - 선택한 월 범위만 원자적으로 교체한다.
- `src/capa_simulation/services/simulation_cache.py`
  - 주요 계산 함수의 content-addressed `st.cache_data` 래퍼다.

### 계산 서비스

- `load_calculator.py`: 계획/수율 편집 변환과 PKG·Chip·Wafer·Density 부하량
- `unit_capacity.py`: Main/MI 환산 UPEH와 대당 Capa
- `required_equipment.py`: RQ_REQB 경로 연결과 소요대수
- `securement_rate.py`: 공정별 확보율
- `equipment_count.py`: 보유·대여·가용 설비대수 표
- `dashboard.py`: HOME 월별 집계, B/N Top 1·5·10, Wafer Capa
- `display_order.py`: `RQ_DISPLAY_ORDER` 기반 동적 행 정렬
- `month_filter.py`: YYYYMM 검증과 조회기간 필터
- `capacity_reference_editor.py`: Capa 기준정보 Long/Wide 편집 변환

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
```

웹 수정은 반드시 `apply_month_updates()`를 통해 반영한다. 페이지 전용 DataFrame만
수정하고 끝내면 다른 페이지와 계산 캐시에 변경이 전달되지 않는다.

### 읽기 전용 참조 테이블

```text
RQ_CHIP_QTY
RQ_CHIP_EQ
RQ_DISPLAY_ORDER
RQ_MODULE
RQ_REQB
RQ_EQP_OWN
RQ_EQP_LENT
RQ_EQP_AVBL
```

이 테이블을 웹에서 수정할 필요가 생기면 단순히 session state에 별도 복사하지 말고,
활성 시나리오의 editable table 계약과 새로고침/저장 정책을 함께 변경한다.

## 5. 상태와 캐시 불변조건

1. **Excel을 페이지별로 다시 읽지 않는다.** 모든 페이지는 `get_reference_tables()`를
   사용한다.
2. **서버 공통 데이터와 사용자 데이터를 구분한다.** Excel 및 동일 입력 계산 결과는
   서버 캐시, 웹 편집값은 `st.session_state`의 활성 시나리오다.
3. **편집 적용마다 revision을 증가시킨다.** 다른 페이지는 revision 변경으로 편집 UI와
   결과를 갱신한다.
4. **계산 함수는 가능한 순수 함수로 유지한다.** Streamlit 캐시는 `simulation_cache.py`
   래퍼에 두고 서비스 함수 내부에 UI 상태 접근을 넣지 않는다.
5. **기준정보 새로고침은 전체 연쇄를 초기화한다.** Excel 캐시, 계산 캐시, 활성
   시나리오와 완성 Figure 캐시를 함께 제거한다.
6. **세션 시나리오는 영구 저장이 아니다.** 탭 종료 또는 서버 재시작 후 유지된다고
   가정하지 않는다.
7. **완성 Figure 캐시 키에는 출력에 영향을 주는 모든 조건을 포함한다.** 시나리오
   revision, reference version, 조회기간, B/N 공정 선택, 임계값과 Figure schema version을
   누락하지 않는다.

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

Dummy Chip/Wafer는 `(1 - EDS_수율)`을 추가 적용한다. 정확한 현재 구현은
`load_calculator.py`와 `docs/TODO.md`를 기준으로 한다.

### 대당 Capa

```text
대당 Capa
= 환산_UPEH × 24 × 효율 ÷ 여유율
  × 모듈수 × 가동일수 ÷ Lot측정률 ÷ WF측정률
```

- `Area_Name = Main`: `UPEH`
- `Area_Name = MI`: `3600 / ST`
- `소요기준 = PKG 또는 CHIP`: UPEH를 Kea 기준으로 `/ 1000`
- WF측정률 0 이하 및 대당 Capa 0 이하는 제외 행으로 남기고 계산에서 제외
- BOX·PCB는 산식 구현 전까지 제외

### 소요대수와 확보율

```text
소요대수 = 부하량 ÷ 대당 Capa
확보율   = RQ_EQP_AVBL 가용대수 ÷ 공정별 소요대수
```

소요대수 계산 전에는 Capa Code, Customer, CS를 포함한 상세 부하량으로 `RQ_REQB`에
연결한다. 화면용 그룹 합산 데이터를 조인 원본으로 재사용하면 안 된다.

소요기준은 대소문자를 정규화하며 `WAFER`는 `WF`로 통일한다. 현재 지원 값은 `PKG`,
`CHIP`, `WF`다.

### B/N

- 월별 유효 확보율이 가장 낮은 공정이 B/N Top 1이다.
- 동률이면 공정명 오름차순 첫 공정을 사용한다.
- `B/N Density Capa = Density 부하량 × 확보율`
- `Wafer Capa = Wafer 부하량 × 확보율`

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
- 적용 범위는 `페이지 구분 + 탭 구분`이다.
- `정렬우선순위`는 정렬 컬럼의 우선순위, `값표시순서`는 사용자 지정 값 순서다.
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
- `use_container_width`를 새로 사용하지 말고 `width="stretch"` 또는
  `width="content"`를 사용한다.
- 단순 UI 그룹은 네이티브 `st.container(border=True)`를 우선한다.
- 복잡한 Plotly UI를 변경할 때는 월별 고정 열 너비, 좌측 라벨 Figure, 공통 가로
  스크롤 정렬을 함께 검증한다.
- HOME Plotly annotation을 반복해서 `add_annotation()`하지 않는다. 레이아웃에 일괄
  주입해 Figure 생성 시간이 선형에 가깝게 유지되도록 한다.

## 10. 로컬 파일과 보안

다음 파일은 Git에 커밋하지 않는다.

- `*.xls`, `*.xlsx`, `*.xlsm`, `*.xlsb`
- `data/*.db` 및 SQLite 보조 파일
- `.env`, `.streamlit/secrets.toml`
- `data/input`, `data/output`, `data/temp`의 실제 데이터
- 로그와 가상환경

`templates/structure_template.xlsb`와 `data/capa_simulation.db`는 로컬 실행 자산이다.
테스트나 문서에서 실제 사내 데이터 값을 노출하지 않는다.

## 11. 현재 미구현 및 주의 사항

- SQLite는 실제 런타임 Repository가 아니다.
- `B/N 분석`, `시나리오 및 결과` 페이지는 미구현이다.
- 시나리오 저장, 이력, 권한, 동시 수정 제어가 없다.
- BOX·PCB 계산은 제외 상태다.
- `MCP_Chip_Ratio` 보정식은 미확정이다.
- DataLake·Impala·BigDataQuery 연결은 외부 PC에서 구현하지 않는다. Repository
  인터페이스와 샘플 데이터 기반 처리 구조를 외부에서 개발하고 사내에서 접속부를
  구현하는 방향이다.
- `app_pages/home.py`는 UI 코드가 크다. 대시보드 기능을 추가할 때 계산 로직을 더 넣지
  말고 Figure 생성기 또는 서비스 모듈 분리를 우선 검토한다.

## 12. 변경 작업 체크리스트

### 입력 테이블 또는 컬럼 변경

1. `excel_reader.py`의 로딩 계약 확인
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
