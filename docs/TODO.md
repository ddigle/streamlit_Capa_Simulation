# Capa Simulation TODO

마지막 정리일: 2026-08-24

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

- [~] `structure_template.xlsb`에 최종 입력 구조와 참조 쿼리를 구성 중이다. 부하량·Capa·설비·소요대수 산출에 필요한 현재 `RQ_*` 테이블 구성을 완료했으며 BOX·PCB 및 후속 기준정보는 추가 예정이다.
- [~] Core Data를 가져오는 Power Query 원본 쿼리와 기준정보별 참조 쿼리를 작성 중이다.
- [x] 원본 쿼리 `Q_Core_Data`는 워크시트에 중복 적재하지 않고 `연결만 만들기`로 운영하기로 확정했다. 프로그램 입력용 `RQ_*` 쿼리만 Excel Table로 로드한다.
- [x] 현재 프로그램 입력용 참조 쿼리를 일반 Long Excel Table로 로드하고 쿼리·시트·Excel Table 이름을 동일한 `RQ_*` 이름으로 구성했다.
- [ ] 최종 파일명, 시트명, Power Query명, Excel Table명을 정한다.
- [ ] M365에서 작성한 파일을 실제 Excel 2021 환경에서 열기·새로고침·저장 검증한다.
- [x] 사내 PC의 Excel 2021 실행환경에서 현재 requirements 설치 호환성과 xlwings 기반 XLSB 로드를 확인했다.

### 우선 작성할 참조 쿼리

- [x] `RQ_PKG_PLAN`: 월별 PKG 생산계획 Long Data를 생성하고 동일 이름의 시트·Excel Table로 로드했다.
- [x] `RQ_CHIP_QTY`: 제품별 Chip 수와 Net Die Long Data를 생성하고 동일 이름의 시트·Excel Table로 로드했다.
- [x] `RQ_YLD`: 생산계획년월·제품·Chip 속성별 수율 Long Data를 생성하고 동일 이름의 시트·Excel Table로 로드했다.
- [x] `RQ_CHIP_EQ`: `제품정보 + Stack + WF 구분`별 용량 발생 Chip 수 `구분_Chip`과 Chip당 용량 `구분_EQ`를 구성했다.
- [x] `RQ_DISPLAY_ORDER`: 화면·컬럼별 사용자지정/오름차순/내림차순 정렬 규칙을 수동 설정 테이블에서 생성하고 동일 이름의 Excel Table로 로드했다.
- [x] Net Die는 별도 쿼리로 분리하지 않고 `RQ_CHIP_QTY`에 포함하기로 했다.
- [x] `RQ_PRODUCT_MASTER`는 불필요한 것으로 결정했다. 현재 참조 쿼리 구조에서 PKG Part No만으로 제품정보를 별도 조회하지 않는다.

### Capa 단계에서 작성할 참조 쿼리

- [x] `RQ_REQB`: 월·Area·공정·제품·Capa Code·Customer·CS·WF 구분·공정 순서·소요기준별 적용 경로를 구성했다.
- [x] `RQ_UPEH`: 대당 Capa 최소 산출 기준으로 UPEH·ST·Area_Name·소요기준을 구성했다.
- [x] `RQ_RUN_RATE`, `RQ_VITAL`, `RQ_MODULE`, `RQ_RUN_DAY`, `RQ_LOT_RATIO`, `RQ_WF_RATIO`: 효율·여유율·모듈·가동일수·측정률 기준정보를 구성했다.
- [x] `RQ_EQP_OWN`, `RQ_EQP_LENT`, `RQ_EQP_AVBL`: 월·공정별 보유·대여·가용대수를 구성했다.
- [x] 별도 `RQ_ST`는 사용하지 않고 ST와 Area_Name을 `RQ_UPEH`에 포함하기로 했다.
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
- [x] 제품별 Buffer·Core·Top Chip 수는 `RQ_CHIP_QTY`로 제공한다.
- [x] Dummy 구성 수는 1로 적용하기로 결정했다.
- [x] Dummy Wafer 계산에 사용할 Dummy Net Die를 `RQ_CHIP_QTY`에서 연결하고 Dummy 환산 로직에 반영했다.
- [x] `BE_수율`은 계산에서 사용하는 PKG 수율과 동일한 값으로 확정했다.
- [x] Net Die는 현재 `제품정보 + WF 구분`으로 구분되고 PKG Part No별 차이는 없다고 확인했다.
- [x] 수율의 고유 키를 `생산계획년월 + 제품정보 + Stack + WF 구분`으로 확정했다.
- [x] Chip 구성 수 컬럼명은 `구분_Chip`으로 확정하고 `WF 구분`별 Chip·Wafer 부하량 산출에 반영했다. `CHIP`와 `Chip수`는 동일한 원천 값이며 `Chip수`는 쿼리에서 비활성화했다. `구분EQ`는 Core·Top·Master·Slave 등 용량이 발생하는 `WF 구분`에 대한 Chip당 용량으로 사용한다.
- [~] 공정별 사용 부하 Unit은 `RQ_REQB.소요기준`으로 제공한다. 현재 `PKG`, `CHIP`, `WF`를 구현했으며 `BOX`, `PCB`는 산출 대상에서 제외한다.
- [ ] Mold Wafer 부하는 독립 계산하지 않고 Buffer Wafer 부하를 어떤 공정에 매핑할지 확인한다.
- [ ] `PCB수(K매)`의 원천 공식 또는 PCB당 Unit·수율·보정 기준을 확인한다.

### 컬럼별 조사 항목

- [ ] `Pack Code`의 의미와 용도를 확인한다.
- [x] `생산수량`과 `계획(K개)`는 동일한 값으로 확인했다. `생산수량`을 사용하고 `계획(K개)`는 쿼리에서 비활성화했다.
- [x] `Chip수`와 `CHIP`는 동일한 값으로 확인했다. `Chip수`는 쿼리에서 비활성화하고 부하량 산출에는 쿼리 결과 컬럼 `구분_Chip`을 사용한다.
- [x] `메이커`, `모델명`은 두 컬럼 모두 데이터가 없어 쿼리에서 비활성화했다.
- [x] `FAB`는 `계획기초정보여부 = N`인 공정 데이터 행에서 `PKG` 값으로 반영되어 있다. 다른 기준으로 대체 가능하므로 쿼리에서 비활성화했다.
- [x] `MCP_Chip_Ratio`는 소요대수 산출 보정치 요소 중 하나로 확인했다. 컬럼을 활성화하고 향후 소요대수 계산에 반영한다.
- [x] 현재 `누락여부 = Y`로 반영된 공정은 없다. 해당 컬럼은 쿼리에서 비활성화했다.
- [x] `설비보유HCB`, `CUSTOM`, `BONDING`은 모두 활용할 데이터가 없어 쿼리에서 비활성화했다.
- [ ] 상세 조사 결과를 이 문서의 해당 항목에 직접 기록한다.

### Capa 산출 기준 확인

- [x] `구분EQ`는 제품의 `WF 구분`에 따라 용량이 발생하는 속성일 때 적용하는 Chip당 용량 값으로 확정했다.
- [x] `D_EQ`는 `제품정보 + Stack`별로 해당 제품이 보유하는 총 용량 값으로 확정했다.
- [x] `EQ(억Gb)`는 용량이 발생하는 `WF 구분`에 대해 `구분_Chip × 구분EQ × 생산수량 ÷ 100,000`으로 계산한 Total 용량이며, 나눗셈 `100,000`은 억Gb 단위 환산에 사용한다.
- [ ] `MCP_Chip_Ratio`를 적용할 공정·제품 범위, 연결 키와 소요대수 보정 수식을 확정한다.
- [x] 효율은 `생산계획년월 + 공정 + 양산구분` 키의 `CAPA_RUN_RATE`로 적용한다.
- [x] 여유율은 `생산계획년월 + 공정 + 양산구분` 키의 `편중률`로 적용한다.
- [x] Lot·WF 측정률은 `생산계획년월 + 공정 + 양산구분 + 제품정보 + Stack + WF 구분` 키로 각각 나누어 적용한다.
- [ ] `CAPA_RUN_RATE`, `Side반영률`, `편중률`, `Para`, `Step수`의 공식 적용 여부를 확인한다.
- [x] 확보율 계산의 가용대수는 `RQ_EQP_AVBL.가용대수`를 사용한다. 보유·대여 값은 설비대수 상세 화면에 별도 표시한다.
- [ ] 소요대수의 실수값과 올림값 중 확보율 및 B/N 판정 기준을 확정한다.
- [x] 홈페이지 월별 B/N은 유효한 확보율이 가장 낮은 공정 1개로 표시한다. 동률이면 공정명 오름차순 첫 공정을 사용한다.

### Git 및 프로젝트 운영

- [x] Git for Windows 설치 후 Git 명령 실행을 확인했다.
- [x] `C:\Dev\Streamlit_Project`에서 Git 저장소를 초기화하고 `.git` 생성을 확인했다.
- [x] 개인 GitHub 계정에 Private 저장소 `streamlit_Capa_Simulation`을 생성했다.
- [x] 생성한 원격 저장소를 확인하고 로컬 저장소와 연결했다.
- [x] Git 커밋 작성자 정보는 이름 `ddigle`, 이메일 `alibalipeec@gmail.com`을 사용하기로 했다.
- [x] `Core_Data.csv`와 `Core_Data.xlsx`를 프로젝트 외부로 이동했다.
- [x] `structure_template.xlsb`는 `.gitignore`의 `*.xlsb` 규칙으로 Git 추적에서 제외했다.
- [x] `git status`로 실제 Excel 파일과 민감정보가 커밋 대상에서 제외되는 것을 검증했다.

## 2. Codex 구현 사항

### Excel 입력 계층

- [ ] `config/excel_sources.yaml`을 추가해 파일·시트·Excel Table명을 설정으로 관리한다.
- [x] `src/capa_simulation/io/excel_reader.py`에 부하량·Capa·설비·경로·정렬용 `RQ_*` 테이블의 xlwings 기반 XLSB 로더를 구현했다.
- [x] Workbook을 숨김·읽기 전용으로 열고 예외 발생 시에도 Workbook과 Excel 프로세스를 종료하도록 구현했다.
- [x] 페이지별 Excel 로더를 공통 서버 캐시로 통합해 서버 시작 후 XLSB를 최초 한 번만 읽도록 변경했다. 파일 수정시간으로 자동 재로딩하지 않으며, 사이드바의 `기준정보 새로고침` 또는 서버 재시작 시에만 다시 읽는다.
- [x] 대당 Capa·부하량·소요대수·확보율·홈 대시보드 산출을 입력값 기반 공통 계산 캐시로 통합했다. 동일 입력의 페이지 이동은 계산 결과를 재사용하고 계획·수율·Capa 기준정보 편집값은 브라우저 세션에서 유지한다.
- [~] 기존 Excel 앱을 유지한 채 병행 검증용 `data/capa_simulation.db`를 생성했다. 현재 16개 RQ 테이블 884행을 이관하고 SQLite 무결성·행 수·열 수를 검증했으며, 다음 단계에서 Excel/SQLite 계산 결과를 비교한다.
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
- [x] `RQ_CHIP_EQ`를 연결해 Density를 `생산수량 × 구분_Chip × 구분_EQ ÷ 100,000`으로 계산하고 억Gb 단위로 집계한다.
- [ ] 기존 `Plan_Chip`, `GOOD_DIE`, `WF수`와 신규 계산값의 차이를 비교한다.
- [ ] PCB 산식이 확정되면 PCB 부하량 계산을 구현한다.
- [~] EQ 부하량 산식은 `구분_Chip × 구분EQ × 생산수량 ÷ 100,000`으로 확정했다. 적용 공정·경로 연결 기준을 확정한 뒤 Python 계산을 구현한다.

### Capa 및 B/N 계산

- [x] 상세 부하량의 `생산계획년월 + 양산구분 + 제품정보 + Stack + Capa Code + Customer + CS + WF 구분 + 소요기준`을 `RQ_REQB`에 연결한다.
- [x] 대당 Capa를 `OR(UPEH, 3600/ST) × 24 × 효율 ÷ 여유율 × 모듈 × 일수 ÷ Lot측정률 ÷ WF측정률`로 계산한다. Main은 UPEH, MI는 ST를 사용하고 CHIP·PKG UPEH는 Kea로 환산한다.
- [x] 제품·속성별 소요대수를 `부하량 ÷ 대당 Capa`로 먼저 계산하고 공정별로 합산한다.
- [x] `RQ_EQP_AVBL` 가용대수를 공정별 소요대수로 나누어 월별 확보율을 계산한다. 소요대수 0은 빈값으로 처리한다.
- [x] 월별 유효 확보율 최저 공정 1개를 홈페이지 Bottleneck으로 선정한다.
- [x] `BOX`, `PCB` 소요기준은 산식 구현 전까지 RQ_UPEH 대당 Capa와 RQ_REQB 소요대수 계산 대상에서 모두 제외한다.
- [ ] 기존 소요대수와 신규 소요대수를 비교하는 검증 결과를 만든다.

### Streamlit 화면

- [x] 사이드바의 기준정보 파일 경로 입력을 제거하고 프로젝트의 `templates/structure_template.xlsb`를 고정 기본 파일로 사용한다.
- [x] 공통 사이드바 조회기간을 시작·종료 월을 각각 선택하는 월 캘린더로 구성하고 기존 전역 조회기간 상태와 연결했다.
- [x] `st.navigation` 기반 멀티페이지 구조를 도입했다. 사이드바에 `Home`, `부하량`, `공정별 Capa`, `공정별 확보율`, `B/N 분석`, `시나리오 및 결과` 6개 페이지를 구성했다.
- [x] `PKG PLAN` 탭을 월별 물량 탭 앞에 추가하고 `RQ_PKG_PLAN`을 초기 기본값으로 불러오도록 구현했다.
- [x] PKG PLAN의 생산계획년월을 열로 펼치고 나머지 분류를 행으로 유지한 편집 테이블을 구현했다.
- [x] 월별 생산수량만 편집 가능하게 하고 분류 컬럼은 읽기 전용으로 설정했다.
- [x] 웹에서 수정한 계획을 Long Data로 복원해 PKG·Chip·Wafer 환산 물량에 즉시 적용하도록 구현했다.
- [x] `수율` 탭을 추가해 `RQ_YLD`의 생산계획년월을 열로 펼치고 `제품정보 + Stack + WF 구분 + 수율 구분`을 행으로 유지한 편집 테이블을 구현했다. 웹에서 수정한 EDS·BE 수율을 Long Data로 복원해 Chip·Wafer 환산에 즉시 적용한다.
- [ ] 웹에서 수정한 계획의 저장·불러오기 및 시나리오 영구 보관 방식을 결정한다. 현재 수정값은 브라우저 세션에서만 유지되고 XLSB는 변경하지 않는다.
- [ ] 입력 데이터 검증 결과와 누락 기준정보 화면을 구현한다.
- [ ] 계산 조건과 시나리오 선택 UI를 구현한다.
- [x] 기존 부하량 기능을 `부하량` 페이지로 분리하고 탭 순서를 `환산 → PKG PLAN → 수율`로 구성했다. PKG/Chip/Wafer/Density 소요기준 드롭다운과 `양산구분 + 제품정보 + Stack`별 월 물량 표를 제공한다.
- [x] 환산 결과 표를 Plotly 기반 고정 분류 영역·가로 스크롤 월 영역으로 분리하고, 정렬된 구분 컬럼의 계층적 그룹화와 제품 그룹·분기 경계를 동적으로 적용했다.
- [x] 환산 결과 표의 각 제품 아래에 `Total`, 각 양산구분 아래에 양산구분 Total을 표시하고 전체 합계는 2행에 배치한다.
- [x] 환산 탭의 현재 소요기준·상세 여부·조회기간 및 부분합이 반영된 결과를 CSV로 내려받는다.
- [x] `월별 물량` 소요기준에 Density를 추가하고 기본·`WF 구분` 상세 결과를 억Gb 단위로 표시한다.
- [x] 월별 물량 표 위에 `상세` 토글을 추가했다. 활성화 시 분류에 `WF 구분`을 추가하며 PKG는 `PKG`, Chip·Wafer·Density는 원본 WF 구분으로 표시한다.
- [x] 부하량 페이지의 분류 컬럼 표시 순서를 조정하고 화면 라벨을 `양산`, `제품`, `PKG Code`, `거래선`, `구분`, `속성`으로 통일했다. 쿼리와 계산에 사용하는 원본 컬럼명은 변경하지 않는다.
- [x] `RQ_DISPLAY_ORDER`의 활성 규칙을 주요 표에 가변 적용한다. `정렬우선순위`로 행 정렬 키 우선순위를, `값표시순서`로 사용자지정 값 순서를 관리한다.
- [x] `공정별 Capa` 페이지에 대당 Capa Output과 UPEH·효율·여유율·Lot/WF측정률·일수 Input 편집 탭을 구현했다.
- [x] `공정별 확보율` 페이지에 확보율·소요대수 Output과 설비대수 탭을 구현했다. 소요대수와 설비대수에는 상세 토글 및 가변 다중 필터를 제공한다.
- [x] 소요대수는 RQ_REQB 상세 행에서 계산한 뒤 화면에서 Area·공정·양산·제품·Stack·속성·소요기준으로 합산하고, 요약 모드에서는 Area·공정으로 합산한다.
- [x] 설비대수 기본 모드는 가용대수, 상세 모드는 보유·대여·가용을 월별로 표시한다.
- [x] 월별·공정별 확보율 요약표와 공정 필터를 구현했다.
- [x] 홈페이지 생산계획 현황에 Density 월별 추이 차트와 `제품정보 + Stack` 세부수량 표를 구현했다.
- [x] 홈페이지 생산계획 현황 하단의 계획 세부수량을 상단 생산계획 시트·차트와 동일한 월별 세로 영역에 맞춰 배치했다. 제품·Stack은 왼쪽에 고정하고, 월별 값은 양산 PKG PLAN 생산수량을 합산해 `###K` 형식으로 표시한다. 행 정렬은 부하량 페이지의 PKG PLAN과 동일한 `RQ_DISPLAY_ORDER` 규칙을 사용하며, 월별 열은 상단과 동일한 100px 너비 및 공통 가로 스크롤 영역에 배치했다.
- [x] 계획 세부수량 아래에 `상세 B/N 공정` 시트를 월별 열에 맞춰 배치했다. `B/N` 열에는 확보율 하위 1~10 순번을 크게 표시하고, 각 월에 `확보율`, `공정명`, `가용대수`, `필요대수`, `Wafer Capa`를 순서대로 표시한다. 가용·필요대수는 `0.0대`, Wafer Capa는 `###K` 형식이며 긴 공정명은 월 열 너비에 맞춰 글자 크기를 자동 축소한다.
- [x] 홈페이지의 별도 `주요공정 확보율 현황` 영역을 제거하고, 관련 정보는 Capa LOB의 B/N 차트와 월별 `상세 B/N 공정` Top 1~10 시트로 통합했다.
- [x] HOME 계산 경로를 상위 캐시로 묶어 warm rerun의 중복 DataFrame 해싱을 줄이고, Chip·Wafer 공통 전처리와 월별 B/N 순위 계산을 각각 한 번만 수행하도록 통합했다.
- [x] HOME 기본 진입은 Density·Wafer Capa 요약 Figure만 생성하고 계획·B/N 상세표는 `계획·B/N 상세표 표시` 토글에서 지연 생성·별도 캐시하도록 변경했다.
- [x] B/N 임계값과 포함 공정 입력을 form 제출로 일괄 적용하고, HOME Plotly shape·annotation을 레이아웃에 일괄 주입하도록 변경했다.
- [x] 데이터 값을 기록하지 않는 HOME 단계별 성능 진단과 AppTest 기반 `scripts/benchmark_home.py`를 추가했다.
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
- [x] 제품 분류별로 수요가 없는 월의 PKG PLAN 빈 셀을 0으로 표시하고 계산 Long Data에서는 제외하도록 구현했다. 희소 월 계획 테스트를 추가해 pytest 4개가 통과했다.
- [x] `RQ_CHIP_EQ` 기반 Density 기본·상세 집계 테스트를 추가해 pytest 5개가 통과했다.
- [x] 수율 Wide 편집·Long 복원·Chip 부하량 재계산 테스트를 추가해 pytest 6개가 통과했다. 실제 XLSB 기반 Streamlit 테스트 세션에서 탭 순서와 실행 예외 없음도 검증했다.
- [x] 사용자지정·오름차순 정렬 테스트를 추가해 pytest 7개가 통과했다. 실제 XLSB의 `RQ_DISPLAY_ORDER` 93행을 로드해 PKG PLAN·수율·환산 정렬과 페이지 실행을 검증했다.
- [x] 로컬 `templates/structure_template.xlsb`에 `RQ_CHIP_EQ` Excel Table을 반영하고 Density 통합 계산을 검증했다. `RQ_CHIP_EQ` 8행을 읽어 월별 Density 5행을 생성했으며 합계는 202608 `11.5724832억Gb`, 202609 `14.3973696억Gb`이다.
- [x] 실제 XLSB 계획 한 셀을 100 Kea 증가시켜 PKG·Chip·Wafer 합계가 모두 재산출됨을 검증했다.
- [x] 프로그램 입력은 PivotTable보다 기준정보별 Long Excel Table을 우선 사용하기로 했다.
- [x] 기준정보별 고유 키는 동일하게 강제하지 않고 실제 값이 달라지는 최소 단위로 정의하기로 했다.
- [x] 기준정보년월은 계산 키로 사용하지 않고 Core Data 전체 새로고침 방식으로 운영하기로 했다.
- [x] 기준정보년월 대신 생산계획년월을 월별 계획·수율 연결에 사용하기로 했다.
- [x] 컬럼 조사 체크리스트를 이 TODO 문서에 통합했다.

## 4. 현재 권장 진행 순서

1. 실제 사내 데이터로 대당 Capa·소요대수·확보율 결과를 기존 결과와 비교 검증한다.
2. `MCP_Chip_Ratio` 적용 공정·연결 키·보정 수식을 확정하고 소요대수에 반영한다.
3. BOX·PCB 부하량 및 대당 Capa 산식을 확정해 현재 제외 로직을 실제 계산으로 전환한다.
4. 확보율 히트맵·공정별 월 추이·부하 기여도 상세 화면을 구현한다.
5. 입력 검증·누락 기준정보 화면과 결과 Excel 다운로드를 구현한다.
6. 시나리오 저장·불러오기 및 실행 이력 관리 방식을 확정한다.
