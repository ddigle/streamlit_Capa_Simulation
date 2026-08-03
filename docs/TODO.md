# Capa Simulation TODO

마지막 정리일: 2026-08-03

## 관리 원칙

- 이 문서를 프로젝트의 단일 TODO 및 조사 항목 관리 문서로 사용한다.
- 사용자가 이 대화에서 진행 결과나 확정 내용을 알려주면 해당 항목의 상태와 결정 내용을 갱신한다.
- 완료된 항목은 삭제하지 않고 `[x]`로 변경하여 결정 이력을 남긴다.
- 일부만 진행된 항목은 `[~]`로 표시하고 남은 조치를 함께 기록한다.
- 새로운 확인 사항은 관련 영역에 추가한다.
- 별도의 `data_investigation.md`는 사용하지 않는다.
- 참조 쿼리와 해당 시트·Excel Table 이름은 `RQ_` 접두사로 통일한다.
- 원본 Core Data 쿼리는 `Q_Core_Data` 이름을 사용한다.

상태 표기:

- `[ ]` 예정 또는 확인 필요
- `[~]` 진행 중
- `[x]` 완료

## 1. 사용자 준비 및 확인 사항

### Core Data 및 Excel

- [~] `structure_template.xlsb`에 최종 입력 구조와 참조 쿼리를 구성 중이다. 2026-08-02 읽기 전용 확인 결과 `Q_Core_Data`, `RQ_PKG_PLAN`, `RQ_YLD`, `RQ_CHIP_QTY` 시트·쿼리·Excel Table이 존재한다.
- [ ] Core Data를 가져오는 Power Query 원본 쿼리를 구성한다.
- [ ] 원본 쿼리를 `연결만 만들기`로 둘지 최종 결정한다.
- [~] 프로그램 입력용 참조 쿼리를 일반 Long Excel Table로 로드 중이다. 현재 생성된 3개 참조 쿼리는 동일 이름의 Excel Table로 로드되어 있다.
- [ ] 최종 파일명, 시트명, Power Query명, Excel Table명을 정한다.
- [ ] M365에서 작성한 파일을 실제 Excel 2021 환경에서 열기·새로고침·저장 검증한다.
- [ ] Excel 2021 실행환경의 Office 32/64비트와 xlwings 실행 가능 여부를 확인한다.

### 우선 작성할 참조 쿼리

- [x] `RQ_PKG_PLAN`: 월별 PKG 생산계획 Long Data를 생성하고 동일 이름의 시트·Excel Table로 로드했다.
- [x] `RQ_CHIP_QTY`: 제품별 Chip 수와 Net Die Long Data를 생성하고 동일 이름의 시트·Excel Table로 로드했다.
- [x] `RQ_YLD`: 생산계획년월·제품·Chip 속성별 수율 Long Data를 생성하고 동일 이름의 시트·Excel Table로 로드했다.
- [x] Net Die는 별도 쿼리로 분리하지 않고 `RQ_CHIP_QTY`에 포함하기로 했다.
- [ ] `RQ_PRODUCT_MASTER`: PKG Part No만으로 제품정보를 조회해야 하는지 판단한 후 필요하면 만든다.

### Capa 단계에서 작성할 참조 쿼리

- [ ] `RQ_PROCESS_ROUTE`: 제품/Capa Code·Chip 속성별 적용 공정과 부하 Unit을 분리한다.
- [ ] `RQ_CAPA_STANDARD`: UPEH, 효율, 여유율, 모듈 수, 측정률 등 Capa 기준을 분리한다.
- [ ] `RQ_EQUIPMENT`: 월·공정·모델별 설비보유 및 가용대수 정보를 분리한다.
- [ ] `RQ_CALENDAR`: RUN_DAY가 다른 기준정보에 없을 경우 월별 가동일수 쿼리를 만든다.
- [ ] `RQ_LEGACY_RESULT`: 기존 WF수·PCB수·EQ·소요대수를 신규 결과와 비교할 필요가 있으면 만든다.

### 제품·부하량 기준 확인

- [x] PKG 부하량과 Chip 부하량의 단위는 `Kea`로 사용한다.
- [x] Wafer 부하량의 단위는 `매`로 사용한다. Kea에서 Wafer 매수로 환산할 때 `1,000`을 곱한다.
- [x] `RQ_YLD` 연결 키는 `생산계획년월 + 제품정보 + Stack + WF 구분`으로 확정했다.
- [x] `RQ_CHIP_QTY`의 Chip 수 및 Net Die 연결 키는 `제품정보 + Stack + WF 구분`으로 확정했다.
- [x] Buffer·Core·Top Wafer는 동일한 일반 Wafer 공식을 사용한다: `생산수량(Kea) × 1,000 × 구분_Chip ÷ EDS_수율 ÷ BE_수율 ÷ Net Die`.
- [x] Top·Core·Buffer·Slave·Master Chip 공식은 `생산수량(Kea) × 구분_Chip ÷ BE_수율`로 적용한다.
- [x] Dummy Chip 공식은 `생산수량(Kea) × 구분_Chip ÷ EDS_수율 ÷ BE_수율 × (1 - EDS_수율)`로 적용한다.
- [x] 제품타입이 `EDP-TSV`이면 원본 WF 구분 `Master`를 계산상 `Buffer`, `Slave`를 계산상 `Core`로 매핑한다. 산출 공식은 HBM의 Buffer·Core와 동일하게 적용한다.
- [x] 제품타입 분류 명칭은 `일반`이 아니라 `HBM`을 사용한다. HBM은 원본 WF 구분 Buffer·Core·Top을 그대로 사용한다.
- [x] Dummy Wafer 공식은 `생산수량(Kea) × 1,000 ÷ EDS_수율 ÷ BE_수율 × (1 - EDS_수율) ÷ Net Die × 구분_Chip`으로 적용한다.
- [x] 앞서 확정한 Dummy 발생 규칙에 따라 Dummy의 수율은 Buffer 수율을 사용하며, `EDP-TSV`에서는 Buffer에 해당하는 Master 수율을 사용한다.
- [ ] 제품별 Buffer·Core·Top Chip 수 테이블을 제공한다.
- [x] Dummy 구성 수는 1로 적용하기로 결정했다.
- [ ] Dummy Wafer 계산에 사용할 Dummy Net Die의 출처와 연결 키를 확인한다.
- [ ] `BE*수율`이 계산에서 말한 PKG 수율과 동일한지 확인한다.
- [x] Net Die는 현재 `제품정보 + WF 구분`으로 구분되고 PKG Part No별 차이는 없다고 확인했다.
- [x] 수율의 고유 키를 `생산계획년월 + 제품정보 + Stack + WF 구분`으로 확정했다.
- [ ] `WF 구분`, `구분*Chip`, `구분EQ`, `CHIP`의 정확한 정의와 관계를 확인한다.
- [ ] 공정별 사용 부하 Unit이 PKG, Chip, Wafer, PCB, EQ 중 무엇인지 정리한다.
- [ ] Mold Wafer 부하는 독립 계산하지 않고 Buffer Wafer 부하를 어떤 공정에 매핑할지 확인한다.
- [ ] `PCB수(K매)`의 원천 공식 또는 PCB당 Unit·수율·보정 기준을 확인한다.

### 컬럼별 조사 항목

- [ ] `Pack Code`의 의미와 용도를 확인한다.
- [ ] `생산수량`과 `계획(K개)`의 차이를 확인한다. 확인 전에는 생산수량을 메인 계획값으로 사용한다.
- [ ] `Chip수`와 `CHIP`의 차이를 확인한다.
- [ ] `메이커`, `모델명`의 실제 데이터 존재 여부와 분포를 확인한다.
- [ ] `FAB`의 의미와 계산·조인 용도를 확인한다.
- [ ] `MCP_Chip_Ratio`의 용도와 실제 데이터 존재 여부를 확인한다.
- [ ] `누락여부 = Y`인 행의 공정과 누락 기준정보를 확인한다.
- [ ] `설비보유HCB`, `CUSTOM`, `BONDING`의 실제 데이터 존재 여부와 용도를 확인한다.
- [ ] 상세 조사 결과를 이 문서의 해당 항목에 직접 기록한다.

### Capa 산출 기준 확인

- [ ] 효율의 고유 키와 월별 변동 여부를 확인한다.
- [ ] 여유율의 의미, 입력 형식 및 고유 키를 확인한다.
- [ ] 공정별로 Lot 측정률과 WF 측정률 중 어느 값을 적용하는지 확인한다.
- [ ] `CAPA_RUN_RATE`, `Side반영률`, `편중률`, `Para`, `Step수`의 공식 적용 여부를 확인한다.
- [ ] 가용대수에 설비대수변화·대여설비·HCB 설비를 어떻게 반영할지 정한다.
- [ ] 소요대수의 실수값과 올림값 중 확보율 및 B/N 판정 기준을 확정한다.
- [ ] 월별 B/N을 최저 확보율 1개로 표시할지 상위 N개로 표시할지 정한다.

### Git 및 프로젝트 운영

- [x] Git for Windows 설치 후 Git 명령 실행을 확인했다.
- [x] `C:\Dev\Streamlit_Project`에서 Git 저장소를 초기화하고 `.git` 생성을 확인했다.
- [x] 개인 GitHub 계정에 Private 저장소 `streamlit_Capa_Simulation`을 생성했다.
- [ ] 생성한 원격 저장소가 README·`.gitignore`·License 없이 비어 있는지 확인하고 로컬 저장소와 연결한다.
- [x] Git 커밋 작성자 정보는 이름 `ddigle`, 이메일 `alibalipeec@gmail.com`을 사용하기로 했다.
- [x] `Core_Data.csv`와 `Core_Data.xlsx`를 프로젝트 외부로 이동했다.
- [x] `structure_template.xlsb`는 `.gitignore`의 `*.xlsb` 규칙으로 Git 추적에서 제외했다.
- [ ] 실제 Excel 파일 및 민감정보가 커밋되지 않는지 `git status`로 검증한다.

## 2. Codex 구현 사항

### Excel 입력 계층

- [ ] `config/excel_sources.yaml`을 추가해 파일·시트·Excel Table명을 설정으로 관리한다.
- [x] `src/capa_simulation/io/excel_reader.py`에 `RQ_PKG_PLAN`, `RQ_YLD`, `RQ_CHIP_QTY` xlwings 기반 XLSB Table 로더를 구현했다.
- [x] Workbook을 숨김·읽기 전용으로 열고 예외 발생 시에도 Workbook과 Excel 프로세스를 종료하도록 구현했다.
- [ ] Power Query 및 PivotTable 새로고침 여부를 선택 가능하게 할지 설계한다.
- [ ] Excel 컬럼명을 Python 내부 표준 컬럼명으로 변환하는 매핑을 구현한다.

### 데이터 계약과 검증

- [ ] `config/data_contract.yaml`에 테이블별 필수 컬럼, 고유 키, 타입, 단위를 정의한다.
- [ ] `src/capa_simulation/domain/schemas.py`에 데이터 타입과 값 범위 검증을 구현한다.
- [ ] 테이블별 고유 키 중복과 동일 키 내 값 충돌 검사를 구현한다.
- [ ] 조인 시 `many-to-one` 관계를 검증하고 의도하지 않은 행 증가를 차단한다.
- [ ] 수율 0 이하·100% 초과, Net Die 0 이하, Chip 수 누락 등을 검출한다.
- [ ] `YYYYMM` 유효 월 검사 및 내부 월 타입 변환을 구현한다.
- [ ] 계산에 필요한 기준정보 누락 내역을 사용자에게 표시한다.

### 부하량 계산

- [x] `RQ_PKG_PLAN`의 각 계획 행을 `RQ_CHIP_QTY`에 존재하는 WF 구분별 행으로 생성한다.
- [x] `생산계획년월 + 제품정보 + Stack + WF 구분`으로 `RQ_YLD`의 월별 수율을 연결한다.
- [x] `제품정보 + Stack + WF 구분`으로 `RQ_CHIP_QTY`의 Chip 수와 Net Die를 연결한다.
- [x] Top·Core·Buffer·Slave·Master 및 Dummy 예상 Chip 부하량을 계산한다.
- [x] Buffer·Core·Top 및 Master·Slave별 예상 Wafer 부하량을 공통 공식으로 계산한다.
- [x] Dummy 행에 `(1 - EDS_수율)`을 추가 적용해 Dummy Wafer 부하량을 계산한다.
- [ ] 기존 `Plan_Chip`, `GOOD_DIE`, `WF수`와 신규 계산값의 차이를 비교한다.
- [ ] PCB 산식이 확정되면 PCB 부하량 계산을 구현한다.
- [ ] EQ 산식과 적용 공정이 확정되면 EQ 부하량 계산을 구현한다.

### Capa 및 B/N 계산

- [ ] 부하량을 제품·Chip 속성·부하 Unit별 공정 경로에 연결한다.
- [ ] 공정·설비·제품별 대당 Capa를 계산한다.
- [ ] 서로 다른 UPEH 제품이 혼류될 경우 제품별 소요대수를 먼저 계산한 후 공정별로 합산한다.
- [ ] 공정별 소요대수와 가용대수를 이용해 확보율을 계산한다.
- [ ] 월별·공정별 확보율을 오름차순으로 정렬해 B/N 순위를 계산한다.
- [ ] 기존 소요대수와 신규 소요대수를 비교하는 검증 결과를 만든다.

### Streamlit 화면

- [x] 기본 `structure_template.xlsb` 경로를 제공하고 로컬 XLSB 경로를 지정하는 화면을 구현했다.
- [x] `PKG PLAN` 탭을 월별 물량 탭 앞에 추가하고 `RQ_PKG_PLAN`을 초기 기본값으로 불러오도록 구현했다.
- [x] PKG PLAN의 생산계획년월을 열로 펼치고 나머지 분류를 행으로 유지한 편집 테이블을 구현했다.
- [x] 월별 생산수량만 편집 가능하게 하고 분류 컬럼은 읽기 전용으로 설정했다.
- [x] 웹에서 수정한 계획을 Long Data로 복원해 PKG·Chip·Wafer 환산 물량에 즉시 적용하도록 구현했다.
- [ ] 웹에서 수정한 계획의 저장·불러오기 및 시나리오 영구 보관 방식을 결정한다. 현재 수정값은 브라우저 세션에서만 유지되고 XLSB는 변경하지 않는다.
- [ ] 입력 데이터 검증 결과와 누락 기준정보 화면을 구현한다.
- [ ] 계산 조건과 시나리오 선택 UI를 구현한다.
- [x] `월별 물량` 탭에 PKG/Chip/Wafer 소요기준 드롭다운과 `양산구분 + 제품정보 + Stack`별 월 물량 표를 구현했다.
- [x] 월별 물량 표 위에 `상세` 토글을 추가했다. 활성화 시 분류에 `WF 구분`을 추가하며 PKG는 `PKG`, Chip·Wafer는 원본 WF 구분으로 표시한다.
- [ ] 월별·공정별 확보율 요약표와 B/N 결과를 구현한다.
- [ ] 확보율 히트맵과 공정별 월 추이 차트를 구현한다.
- [ ] 제품·Stack·PKG Part No·Chip 속성별 부하 기여도 상세 화면을 구현한다.
- [ ] 계산 결과 Excel 다운로드를 구현한다.
- [ ] 시나리오 실행 이력에 원본 파일명·수정일시·해시·실행일시를 기록한다.

### 문서 및 테스트

- [ ] `docs/data_model.md`에 테이블별 고유 키와 관계를 기록한다.
- [ ] `docs/calculation_rules.md`에 확정된 Chip/Wafer/Capa/Dummy 공식을 기록한다.
- [ ] `docs/decisions.md`에 주요 설계 결정과 변경 이력을 기록한다.
- [ ] 정상·누락·중복·0 수율·혼류 생산 테스트를 추가한다.
- [ ] 실제 Excel 2021 환경의 XLSB 통합 테스트를 수행한다.

## 3. 완료된 항목

- [x] `C:\Dev\Streamlit_Project` 프로젝트 기본 폴더 구조를 구성했다.
- [x] `.gitignore`, `pyproject.toml`, requirements 파일, Streamlit 설정을 구성했다.
- [x] 초기 개발 환경으로 Python 3.13 기반 `.venv`를 생성하고 활성화했다.
- [x] 사내 실행환경에 맞춰 Python 3.10.11 기반 `.venv`로 전환하고 프로젝트 Python/Ruff/mypy 대상 버전을 3.10으로 조정했다.
- [x] Python 3.10.11 환경에서 mypy, Ruff, pytest 3개 및 실제 XLSB Streamlit 실행 검증을 완료했다.
- [x] 개발 패키지를 설치했다.
- [x] `pytest` 스모크 테스트가 통과했다.
- [x] Streamlit 로컬 웹 실행에 성공했다.
- [x] 실제 `structure_template.xlsb`로 월별 물량 통합 계산을 검증했다: 202608 PKG 4,164.41 Kea, Wafer 161,476.828276매.
- [x] 실제 `structure_template.xlsb`로 202608 Chip 월별 물량 60,293.601713 Kea를 검증했다.
- [x] 실제 XLSB 상세 모드에서 PKG 5행, Chip 18행, Wafer 18행을 확인하고 상세 전후 월 합계가 동일함을 검증했다.
- [x] 월별 물량 구현 후 Ruff 검사와 pytest 2개가 모두 통과했다.
- [x] PKG PLAN 편집·Long 변환·재계산 테스트를 추가해 pytest 3개가 통과했다.
- [x] 실제 XLSB 계획 한 셀을 100 Kea 증가시켜 PKG·Chip·Wafer 합계가 모두 재산출됨을 검증했다.
- [x] 프로그램 입력은 PivotTable보다 기준정보별 Long Excel Table을 우선 사용하기로 했다.
- [x] 기준정보별 고유 키는 동일하게 강제하지 않고 실제 값이 달라지는 최소 단위로 정의하기로 했다.
- [x] 기준정보년월은 계산 키로 사용하지 않고 Core Data 전체 새로고침 방식으로 운영하기로 했다.
- [x] 기준정보년월 대신 생산계획년월을 월별 계획·수율 연결에 사용하기로 했다.
- [x] 컬럼 조사 체크리스트를 이 TODO 문서에 통합했다.

## 4. 현재 권장 진행 순서

1. 사용자가 소요기준별 부하량 산출 로직을 설명한다.
2. `RQ_PKG_PLAN`, `RQ_YLD`, `RQ_CHIP_QTY`의 실제 컬럼과 고유 키를 확정한다.
3. 추가로 필요한 공정·Capa·설비 참조 쿼리를 결정한다.
4. Codex가 데이터 계약과 xlwings 로더를 구현한다.
5. Chip·Wafer·Dummy 및 소요기준별 부하량을 구현하고 기존 Core Data 결과와 비교한다.
6. 계산 차이가 해결되면 공정 경로·UPEH·설비 기준정보를 연결한다.
7. 소요대수·확보율·월별 B/N을 구현한다.
8. Streamlit 화면과 결과 다운로드를 완성한다.
