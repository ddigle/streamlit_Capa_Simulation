# AGENTS 3장 — 파일별 책임 > 계산 서비스

### 계산 서비스

- `src/capa_simulation/services/load_calculator.py` — 계획·수율 편집 변환과 PKG·Chip·Wafer·Density 부하량을 낸다.
  - 월 환산 `build_monthly_volume` 의 `aggregation` 은 `MonthlyAggregation`(`total` 산출 기준 총량 — 기본, `home` HOME
    집계 기준)이다. `home` 은 Chip · Wafer 를 묶기 전에 `exclude_dummy_series` 로 Dummy 계열 행을 빼고, PKG · Density 는
    보지 않으며 제외 목록은 두 기준이 같다. 캐시 래퍼 `simulation_cache.get_monthly_volume` · `get_monthly_volume_by_key`
    도 같은 인자를 받는다(`tests/test_monthly_volume_basis.py`).
  - 키 상수(`CLASSIFICATION_COLUMNS` · `PLAN_EDITOR_DIMENSIONS` · `YIELD_KEYS` · `YIELD_EDITOR_DIMENSIONS` · `CHIP_KEYS` ·
    `DENSITY_KEYS` · `LOAD_EXCLUSION_COLUMNS`)는 Stack 뒤에 `CUSTOM` 을 싣는다. Chip · Density 펼침 조인은 손으로 적은 키가
    아니라 그 키에서 `WF 구분` 만 뺀 상수(`_CHIP_EXPAND_KEYS` · `_DENSITY_EXPAND_KEYS`)로 잇는다 — 키를 손으로 적으면 업무
    키가 넓어질 때 두 부품이 서로 붙어 부하가 두 배가 된다. `LOAD_EXCLUSION_COLUMNS` 는 끝 칸(누락 기준정보) 앞이 키라
    (`[:-1]` 로 읽는다) CUSTOM 도 그 앞이다. 수율 범위 예시는 자리가 아니라 칸 이름으로 풀고, 걸린 칸에 빈 값 표지 아닌
    부품이 있을 때만 Stack 뒤에 CUSTOM 을 싣는다(두 부품의 같은 달 칸이 같은 글로 보이지 않게 — 부품이 없으면 글 그대로).
    `plan_quantities` 의 숫자 아닌 생산수량 예시(년월 · 제품 · Stack)는 처음부터 계획 키 전부가 아니라(Capa Code · Customer ·
    CS 도 없다) 그대로 둔다.
- `src/capa_simulation/services/unit_capacity.py` — Main/MI 환산 UPEH 와 경로별 대당 Capa 를 계산한다(6장).
  0 이하 멈춤 글(`_assert_positive`)의 「n건」 은 걸린 계산 행 수가 아니라 키 조합, 곧 기준정보 표에서 고칠 칸 수다(빈 값 ·
  숫자 아님 · 연결값 없음 글과 같은 셈 — 계산 멈춤 알림의 「0 이하 칸 n건」 이 그대로 쓴다). 경로 키
  `PERFORMANCE_KEYS` 와 결과 차원 `UNIT_CAPACITY_DIMENSIONS` 는 Stack 뒤에 `CUSTOM` 을 싣는다(UPEH · 측정률이 부품마다 붙는다).
- `src/capa_simulation/services/weighted_unit_capacity.py` — 원수요 부하량 ÷ STEP별 소요대수 합으로 공정별 대당 Capa 를
  만든다. 소요기준이 둘인 공정은 멈춘다. 원수요 키 `DEMAND_ID_COLUMNS` 는 `standard_target_capacity.PKG_PLAN_KEYS` 와
  **함께** CUSTOM 을 싣는다(한쪽만 넓히면 「동일 원수요 키의 부하량이 서로 다릅니다」 로 멈춘다). 집계 계층
  `WEIGHTED_CAPACITY_HIERARCHY` 에는 CUSTOM 이 없다 — 부품은 그 위에서 합친다.
- `src/capa_simulation/services/standard_target_capacity.py` — 주차별 일 표준 가능량과 PKG 기준 역산을 낸다. 표준 목표
  전용 제외(ER·`Pre B/D` DUMMY)는 `split_standard_target_required_equipment` 한 번으로 낸다. 두 계산 함수는 기본으로
  분리를 함께 하고, 이미 분리한 프레임(분리 결과 캐시 `get_standard_target_split` 와 그 행을 거른 것)은 `already_split=True`
  로 받아 다시 훑지 않는다 — `simulation_cache` 의 네 표준 목표 래퍼만 쓴다. 분리 안 한 프레임에 켜면 ER·DUMMY 가 섞인다.
- `src/capa_simulation/services/route_step_editor.py` — 네 경로 표의 MCP·STEP 일괄 복제·삭제와 고유 조합 수를 맡는다.
  요약·선택지를 함께 낼 때는 `route_step_tables` 로 `RQ_REQB` 를 한 번만 전처리한다. 경로 묶음 키(`ROUTE_GROUP_COLUMNS` ·
  `PERFORMANCE_ROUTE_COLUMNS`)는 Stack 뒤에 `CUSTOM` 을 싣고, 함께 처리하는 수요 변형은 Capa Code · Customer · CS 셋이다.
- `src/capa_simulation/services/process_rename.py` — 공용 공정 표시명의 정규화·검증·직렬화다(치환은
  `components/process_labels.py` 에만, 8장).
- `src/capa_simulation/services/required_equipment.py` — `RQ_REQB` 경로 연결·소요대수와 제외 셈을 낸다(6장).
  - `calculate_required_equipment(route_exceptions=)` 는 공정별 부하 산출 예외 선언(원본 공정명 → 산식 id)을 받는다.
    **기본값이 없다** — 호출처가 모두 넘기고 빠뜨리면 mypy 가 잡는다. 빈 선언이면 결과 · attrs 는 일반 산식 그대로다. 선언
    공정의 WF 경로가 있을 때만 부하량 표에서 바탕을 지어 `_attach_loads` 바로 뒤에 걸고, 바탕이 없어 뺀 줄은 경로 쪽 제외
    목록에 「부하 예외 바탕 없음」 으로 싣는다(6장 「공정별 부하 산출 예외」). 호출처는 지금 선언 판을 읽어 넘긴다 —
    화면은 계산 토큰에서 풀린 판, 배경 · 스크립트는 저장소 · 사본에서 읽은 판이다(5장 44 · 45).
  - 경로 · 부하 · 대당 Capa 를 잇는 키(`REQB_COLUMNS` · `LOAD_KEYS` · `CAPACITY_KEYS`)와 PKG 부하 줄을 짓는 `_build_loads` 의
    칸 목록 · 글자 다듬기 목록은 `CUSTOM` 을 싣는다 — PKG 쪽 칸 목록에서 빠지면 PKG 부하의 CUSTOM 이 비어 경로에 못 붙고
    PKG 소요대수가 말없이 0 이 된다. 경로 없는 부하의 사유를 가르는 `_ROUTE_PRODUCT_KEYS` · `_ROUTE_FAMILY_KEYS` 에는
    CUSTOM 이 **없다** — 부품만 어긋난 부하가 「경로 키 어긋남」 으로 갈린다(6장). 산출 결과 소요대수 표와 경로 쪽 제외
    목록의 분류 칸 `RESULT_DIMENSIONS` 는 Stack 뒤에 `CUSTOM` 을 싣는다 — 같은 화면 대당 Capa 표(`UNIT_CAPACITY_DIMENSIONS`)와
    같은 칸 묶음이라 「상세」 를 켜면 한 제품의 부품이 부품마다 한 줄이고, 공정 단위 합(「상세」 끔)은 그대로다.
- `src/capa_simulation/services/route_load_exceptions.py` — 공정별 부하 산출 예외의 순수 계산. 산식 id 목록
  `ROUTE_LOAD_FORMULAS`(지금 `buffer_x_core_chip` 하나), 선언 정규화(공정 이름은 `scalar_match_key` 로 견주고 모르는 산식
  id 는 멈춤), 바탕 표 `build_route_load_bases`(부하 키마다 Buffer Wafer 부하 × Core `구분_Chip`), 경로 줄에 거는
  `apply_route_load_exceptions`, 경로 추적 근거 글 `route_load_basis`, 판 지문 `route_load_declaration_digest`(정규 글
  `route_load_declaration_json` — 견줌 키 차례의 견줌 키 → 산식 id, 빈 선언은 빈 글). 입력 점검 두 묶음의 셈도 여기다 — 산식이
  부하량을 바꾼 경로 줄 `route_load_changed_rows`(근거 글이 서는 줄과 같다 — 시험이 줄마다 맞댄다)와 이번 데이터에 없는 선언 공정
  `route_load_missing_processes`(선언 원본 표기 · 차례, Admin 「(이번 데이터에 없음)」 과 같은 견줌). 공정 이름 · Streamlit · DB 를 모른다
  (`tests/test_route_load_exceptions.py` · `tests/test_route_load_exception_store.py`).
- `src/capa_simulation/services/revision_input_check.py` — 저장 리비전 하나의 입력 점검(시나리오 관리 › 목록 관리
  「점검」)을 짓는 순수 셈. 전체 기간 결과에서 빠진 행을 묶음 · 단계 · 원본 까닭별 수로 모으고 저장 · 지정 검사
  (`required_exclusion_counts`)와 같은 행을 센다. 판정 · 캐시 길은 `capacity_gate.input_check_verdict` →
  `simulation_cache.get_revision_input_check`(`tests/test_revision_input_check.py`). 그 리비전 데이터셋에 부대공정을 합쳤으면
  확인 필요 묶음 뒤에 「부대공정」(`GROUP_EXTRA` — 설계 A10)이 선다: 공정마다 판 · 부하 붙은 · 0 경로 · 이어받은 대당 Capa 결손 줄
  (R-02) · 판 섞임(월 머지)이고 수는 부하가 하나도 붙지 않은 공정 + 결손 줄 + 판 섞인 공정이다(부하 0 경로는 부제에만 — 그 달
  계획이 0 인 경로도 든다). 재료(`ExtraProcessCheck`)는 `capacity_gate._extra_check` 가 데이터셋 출처 · 판 내용 · 같은 계산
  결과로 짓는다. 부대공정이 없는 리비전의 묶음 · 「확인 n」 은 그대로다. 부하 예외 선언이 있으면 그 뒤 · 등록 때 뺀 원천 행
  앞에 확인 필요 「이번 데이터에 없는 선언 공정」(그 리비전 `RQ_REQB` 공정과 견준 수 — 공정 이름은 표 칸에만)과 알림 「부하 예외로
  바꾼 경로」(산식이 부하량을 바꾼 결과 줄 수 · `WF 구분` 마다 부제 — 표는 결과 `attrs` 를 뗀다)가 선다. 재료(`RouteExceptionCheck` ·
  `route_exception_check`)는 `capacity_gate.input_check_verdict` 가 넘긴 판으로 짓고, 선언이 빈 리비전 · 뒤 묶음을 접는 멈춘 리비전의
  묶음은 그대로다. 「그 화면으로」 는 없다(고칠 곳이 Admin 「부하 예외」).
  - 멈춘 리비전은 뒤 묶음을 세지 못해 「셀 수 없음」 한 묶음으로 접는다(등록 때 뺀 원천 행은 계산과 상관없이 센다). HOME Density 환산만 멈춘 리비전은 대당 Capa · 소요대수가 끝났으므로 「멈춤」 줄을 두고 뒤 묶음도 그대로 센다(`DENSITY_STOP_KEEPS_COUNTS`).
- `src/capa_simulation/services/securement_rate.py` — 확보율·추가 필요대수·부호 있는 과부족(`securement_balance`)을 낸다.
- `src/capa_simulation/services/process_capa_detail.py` — 공정 하나의 월별 요약·제품별 소요·경로 추적을 계산 결과에서 꺼낸다.
  - 새 계산이 없다. 대당 Capa 식을 바꾸면 `route_factor_product` 도 고친다(`tests/test_process_capa_detail.py`).
  - 경로 추적 키 `ROUTE_KEYS` 는 Stack 뒤에 `CUSTOM` 을 싣는다 — 경로 한 줄이 한 부품이고 측정률 키(`RATIO_ROUTE_KEYS`,
    `PERFORMANCE_KEYS` 에서 냄)와 맞는다.
  - 「제품별 소요대수」 의 제품 두 분류(`PRODUCT_DEMAND_SPLITS` 「제품정보」 · 「양산구분·제품」 — 이름은 그대로)는 끝에
    `CUSTOM` 을 실어 부품이 둘 이상인 제품(`build_process_product_demand(multi_part=)`)만 부품마다 한 행이다. 나머지 제품은
    접힌 값이라 행이 부품을 싣기 전과 같고 기본(빈 판정)은 모두 접는다. `분류` 글이 이름표(「양산 · 제품 (부품)」)이고
    「그 밖」 의 묶은 수 · 12행 상한은 부품 하나를 한 행으로 센다. 표시순서는 `product_parts.apply_part_display_order`(주인 =
    `CUSTOM` 앞 분류 칸)다. 근거 카드 ① 의 상위 제품 · 제품 수도 같은 판정 · 같은 이름표다(`build_process_month_trace(multi_part=)`
    — 분류 행과 어긋나지 않게, PRC-01). 판정은 두 캐시 래퍼(`get_process_product_demand` · `get_process_month_trace`)가 받은
    시나리오 계획 전체로 낸다 — 키 · 반환 꼴은 그대로다(`tests/test_process_capa_detail.py`).
  - 화면 경로 표의 「부하량 근거」 칸(`ROUTE_LOAD_BASIS_COLUMN`)은 `with_route_load_basis` 가 공정이 부하 예외 선언에 있을 때만
    「부하량」 바로 뒤에 끼운다 — 결과 프레임 칸(`ROUTE_COLUMNS`)은 그대로다(6장 「공정별 부하 산출 예외」).
- `src/capa_simulation/services/constraint_simulation.py` — 제약 시뮬레이션(2026-10-24 결정, 저장하지 않는 미래 가정)의
  순수 계산. 공정 하나의 월별 소요(R)를 제약 제품(`제품정보` 하나 또는 그 부품(`CUSTOM`) 하나 — 2026-11-23 보드 답
  D3 (나))과 기존 제품으로 나누고, 설비 일정 기준 가용(단축 전
  환산 대수)에서 개조 비가동을 빼고 제약 몫을 먼저 정수로 뗀 뒤 기존 제품 확보율·「소요 비중대로」 견주기·요약 넷을 낸다
  (`simulate_constraint`). Streamlit·세션·캐시·DB 를 모르고, pandas 는 어댑터 `constraint_month_inputs`(필요 단축 일정
  계획의 공정 x 월 표 + `build_process_product_demand(split="제품정보")` 표 → 달마다 입력 — `part=None` 이면 부품마다 선
  행도 `제품정보` 로 맞대 합치고(부품을 싣기 전과 같은 값), `part` 를 주면 그 부품 행만이다(`constraint_product_rows` —
  `CUSTOM` 칸이 없는 표에서 부품을 고르면 `ValueError`), 합이 R 과 어긋나거나 제약
  제품이 빈 이름이면 `ValueError`·계획에 공정이 없으면 `KeyError`)와 같은 표를 읽는 제약 제품 선택지
  `constraint_product_choices`(화면 값 이름표 → `ConstraintProduct`(제품정보, 부품 | None) — 부품을 가르는 제품은 이름만 쓴
  제품 전체 한 줄 뒤에 부품마다 `product_part_label` 줄, 부품이 하나뿐인 제품은 이름 한 줄, 표 차례)만 쓴다. 빈 이름을 막는
  까닭은 표가 빈 `제품정보` 를 「그 밖」 이 아닌 한 묶음 행으로 두기 때문이다(제품 선택지도 빈 이름을 뺀다). 「신규 설비는 개조 없이」 의 신규 호기는 달이
  아니라 호기 단위라 어댑터가 싣지 않고 `simulate_constraint(new_units=)` 로 따로 받는다(`NewUnit` — 기여 시작 · 환산 대수 ·
  반출). 채우는 차례는 상수 `FILL_ORDER` 하나다(지금 신규 → 보유 — 계산·화면 구성 글·계산표 두 행이 모두 따른다). 식은
  6장 「제약 시뮬레이션」.
  - 기준 판정은 `secure()` → `capacity_status` 한 길(사사오입 정수 % — 8장 「판정 기준」), 제약 충족은 `allocated >= need` 정수
    비교다 — 이 모듈에
    기준·제약 확보율을 비율과 직접 견주는 식이 없는지 `tests/test_constraint_simulation.py` 가 AST 로 본다.
- `src/capa_simulation/services/modification_schedule.py` — 제약 시뮬레이션 「개조 일정」 모드(2026-10-26 결정 3)의 순수 계산.
  N대 × D일 개조를 모든 달 기준 확보율(G 의 판정 경계 + 안전 여유)을 지키며 같은 날 개조 대수가 그 달 ⌊A⌋ 를 넘지 않게 언제 할지 찾는다
  (`plan_modification_schedule` — 이른 시작 탐욕 + 완료 달 고정 늦은 시작 탐욕 + 마디 한도 안 되짚기 완전 탐색, 「가장 고르게」 는
  δ 이분 탐색, 못 맞추면 `ScheduleShortfall` 셋과 까닭 · `exact` · 기준 칸에 칠 정수 % 낮출 폭 `relief_percent`). Streamlit·세션·캐시·DB 를 모르고 pandas 는 어댑터
  `schedule_month_inputs`(계획의 공정 x 월 표 → 달마다 R·A·G) 하나만 쓴다. 판정은 `constraint_simulation.secure` 한 길이고 이
  모듈에 기준과 비율을 직접 견주는 식이 없는지 · 완료 W/D 달 · 넣을 수 있는 대수 · 필요 완화 · 까닭 · 「가장 고르게」 δ 가 따로 짠
  작은 완전 탐색과 같은지 `tests/test_modification_schedule.py` 가 본다. 식은 6장 「개조 일정」.
- `src/capa_simulation/services/securement_threshold.py` — 공용 판정 기준(기본 + 월별 예외)의 정규화·검증, 달별 실효 기준
  (`SecurementThresholds` — 저장값을 정수 % T/100 으로 읽는다), 판정 한 길 `meets_threshold`(확보율을 사사오입한 정수 % 가 T
  이상)와 그것을 쓰는 `capacity_status`, 판정 경계 `judgment_boundary`·반올림으로만 든 확보율 `rounded_in`·기준 대비 여유
  `threshold_margin`, 받는 범위 50 ~ 300%(`THRESHOLD_RANGE` — 제약 확보율과 한 값)와 저장 직전 범위 검사(`out_of_range_thresholds` ·
  `require_threshold_range`)의 한 곳이다(6장·8장).
- `src/capa_simulation/services/threshold_label.py` — 판정 기준 비율을 사사오입 정수 %(`threshold_percent`)와 그 글자
  (`threshold_percent_label` — 「110%」, 식 줄용 판정 경계 글자 `boundary_percent_label` — 「109.5%」)로, 칸에 친 퍼센트를 사사오입
  정수 %(`whole_percent` — 109.5 → 110)로 바꾸는 한 곳이다(8장).
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
  - 편집본에 없는 설비명(새 호기)은 새 호기에 필요한 열(선택 컬럼 밖)이 붙여넣은 표에 다 있어야 한다. 하나라도 없으면 검증 앞에서 거절한다 — 반만 채운 호기를 받지 않는다.
- `src/capa_simulation/services/dashboard.py` — HOME 월별 집계와 B/N 월별 순위(Top 1·Top 5·상세)·Wafer Capa 를 낸다.
  - HOME 의 Wafer 정의는 `home_aggregation_wafer_load` 하나다 — Dummy 계열(`product_type.DUMMY_SERIES_DIVISIONS_BY_PRODUCT_TYPE`)을
    뺀 원천 집계 기준이고, 월 합과 제품별 비중 분모가 같은 거른 프레임에서 묶인다(6장 「HOME 얹기」).
  - 계획 세부수량 차원은 제품정보 → `CUSTOM` → Stack(→ Customer)이다. 부품은 칸으로 그리지 않고 그림이 제품 칸 글에 녹인다
    (`DETAIL_DIMENSION_HEADERS` · `DETAIL_DIMENSION_WIDTHS` 에 없다). `multi_part`(부품이 둘 이상인 제품)에 없는 제품은
    부품을 접어(`product_parts.split_product_parts`) 행이 부품을 싣기 전과 같다 — 기본은 모두 접힘. 표시순서는
    `product_parts.apply_part_display_order` 로 건다(세부수량 · 비교 맞춤 `align_detail_with_comparison` · 과거 합치기
    `past_data.merge_past_plan_detail` 세 곳).
  - 월 축은 양산 Density 가 있는 달이다 — 양산 없이 ER 만 있는 달은 Wafer 계획·Wafer Capa·B/N·Top5·연간 Total 에서
    빠진다. 그대로 둔다(2026-10-22 결정 A — 사내 런북 8-9 가 잰 그런 달이 리뷰마다 0 이라 닫고 그 블록은 걷었다). 넓힐 때는 이 파일의 조인 넷과
    `home.py` 축·`home_lob_figures` 위치 조회를 함께 바꾼다 — 조인만 바꾸면 B/N 그림이 `KeyError` 로 멈춘다.
- `src/capa_simulation/services/product_parts.py` — 합쳐 보는 화면(HOME 도넛 · 제품별 비중 · HOME 계획 세부수량 · 공정
  Capa 상세 제품별 나눔 · 제약 시뮬레이션)이 한 제품의 부품(`CUSTOM`)을 가를지 판정하고 이름표 · 차례 · 접기를 내는 한
  벌이다(8장 「합쳐 보는 화면의 부품 이름표」). 화면 모듈은 사본을 두지 않는다(`tests/test_documentation_inventory.py` 의
  `SHARED_HELPERS`).
  - 판정 `multi_part_products` 는 받은 계획(활성 리비전 계획 전체를 넘긴다)에서 CUSTOM 이 둘 이상인 제품정보이고, 이름표가
    다른 제품의 부품 이름표와 글자가 같은 제품도 든다(조각 · 줄이 합쳐지지 않게). `split_product_parts` 는 나머지 제품의
    CUSTOM 을 `PART_NOT_SPLIT`(빈 글자)으로 접고, CUSTOM 칸이 없는 표(Past Data)는 칸을 채운다(가르는 제품은 표지 `-`).
  - 이름표 `product_part_label`(부품 글자 `label_part`) · 칸 녹이기 `part_merged_columns`(보이는 칸에서 CUSTOM 을 빼고 제품
    칸 글을 이름표로) · 차례 `part_order_key`(접힌 값 먼저, 나머지는 `custom_sort_key` — 열쇠 함수를 두 벌 두지 않는다) ·
    모으기 `keep_parts_together` · 표시순서 `apply_part_display_order`(앞에서 섞인 제품의 부품을 부품 차례로 모으고 —
    규칙이 없을 때의 답 — `CUSTOM` 규칙을 뺀 표시순서 뒤에 `keep_parts_together`. 부품 차례는 범위의 `CUSTOM` 규칙 →
    `part_order_key` 하나이고 도넛 · 범례 차례(`product_share.assign_product_slots`)도 이 함수를 지난다). 좁은 칸 줄임은
    `home_figure_common._fit_part_label` 이다. 시험은 `tests/test_product_parts.py` · 계획 세부수량과 도넛의 부품 차례는
    `tests/test_dashboard.py`.
- `src/capa_simulation/services/dynamic_capacity.py` — 실적을 차례로 얹는 Dynamic Capa 손실 분석과 데모(`DemoProfile`)다.
- `src/capa_simulation/services/wip_status.py` — 재공 DB 연결 계약·STEP 코드 정렬·제품별 표준 가능량 일 전개와 샘플을 낸다.
- `src/capa_simulation/services/display_order_scopes.py` — 표시순서 규칙이 걸리는 페이지·탭 구분자를 한 곳에 선언한다.
  - `LEGACY_SCOPE_RENAMES` 는 `0027_display_order_scope_rename.sql`·`config/bootstrap_display_order.json` 과 같은
    대응이어야 한다(`tests/test_display_order_scopes.py`).
- `src/capa_simulation/services/display_order.py` — `RQ_DISPLAY_ORDER` 기반 행 정렬이다. `prepare_display_order` 가 회차에
  한 번 검증해 `PreparedDisplayOrder` 를 만든다. 캐시는 두지 않는다(`simulation_cache.get_prepared_display_order`).
  규칙 열쇠가 같은 행의 끝 열쇠(`_part_tie_keys`)는 규칙 칸과 `CUSTOM`(`CUSTOM_TIE_COLUMN`) 앞 글자 칸이 같고 CUSTOM 만
  다른 행 — 한 제품의 부품 — 을 그 무리가 처음 선 자리에 이웃해 부품 차례(`custom_sort_key`)로 세우고, 그 밖의 행은 원래
  행 차례다(8장).
- `src/capa_simulation/services/month_filter.py` — YYYYMM 검증과 조회기간 필터다(원천·적재·계산이 같은 달력 검증을 쓴다).
- `src/capa_simulation/services/capacity_reference_editor.py` — Capa 기준정보 Long/Wide 편집 변환이다. 빈 칸은 「행 없음」이다.
  - 편집표 한 장(`build_reference_edit_table`)은 순수 조합이고 캐시는 `simulation_cache.get_reference_edit_table` 이
    건다(`tests/test_reference_data_page.py` 가 표시순서 교체를 본다).
  - UPEH 편집 차원(`PERFORMANCE_EDITOR_DIMENSIONS`)과 측정률 화면 차원(`app_pages/reference_data.py` `RATIO_DIMENSIONS`)은
    Stack 뒤에 `CUSTOM` 을 싣는다. 붙여넣기 · CSV 양식이 차원을 따라가므로 CUSTOM 칸이 없는 옛 양식은 막힌다.
- `src/capa_simulation/services/clipboard_table.py`, `reference_csv.py` — Excel 복사 TSV 파싱과 RQ Wide 표 검증이다.
  - 빈 열은 `drop_empty_unnamed_columns` 가 빼고, 못 읽는 값·범위 밖 값(`assert_edit_value_range`)은 막고 빈 칸은 센다.
- `src/capa_simulation/services/reference_consistency.py` — 기준정보 편집이 다른 표의 행을 빠뜨렸는지 저장 전에 가린다
  (`validate_upeh_edit`·`validate_required_edit`). 줄이는 규칙은 `unit_capacity._join_reference` 와 같아야 한다.
  「경로가 쓰는 칸」 은 제외(Main UPEH 0 이하 · 효율 0 이하 · 측정률 음수) 뒤에도 남는 경로의 칸이다(`_live_upeh` — 계산과 같은
  자리에서 멈추게). 그래서 두 검증은 `RQ_UPEH` 와 효율·측정률이 든 시나리오 표 묶음을 받는다. 빠지던 경로를 살리는 편집
  (UPEH·효율 0 이하 → 0 보다 큼)은 새 경로로 센다(`revived_route_rows` — 7장 「검사는 계산이 멈추는 조건과 같게」).
  거절 글(`describe_missing_path_rows`)이 괄호에 인용하는 멈춤 글은 계산이 실제로 낼 글이다 — 결손 줄마다 행 없음 ·
  값이 빈 행 · 숫자 아님을 갈라(`_missing_required_for`, `unit_capacity._raise_on_unusable_values` 와 같은 갈래) 「… 연결값이
  없는 …」 · 「…의 {값 칸} 값이 빈 …」 · 「… 숫자가 아닌 값이 있습니다」 를 고른다(BigDataQuery 원천의 빈 값 행).
- `src/capa_simulation/services/reference_transformer.py` — XLSB `Q_Core_Data` 와 15개 Core 파생 Power Query 를 pandas 로
  대체하고 값 충돌 보고서를 함께 낸다(수동 `RQ_DISPLAY_ORDER` 는 `display_order_editor.transform_display_order`).
  - 경로 중복 접기·빈 대여 = 0 보정 때문에 `RQ_REQB`·`RQ_EQP_LENT`·`RQ_EQP_AVBL` 은 Power Query 와 일부러 다를 수
    있다 — `scripts/validate_duckdb_persistence.py` 는 같은 보정을 건 뒤 견준다. Power Query 결과에 없는 앱 전용 칸
    (`APP_ONLY_COLUMNS` — `CUSTOM`)은 그 견줌에서만 뺀다.
  - CUSTOM 키 8표(4장)의 칸 목록은 `CUSTOM` 이 **끝**이다 — DDL 차례(0039 가 칸을 끝에 붙임)라 바꾸면 리비전 왕복이
    깨진다. `RQ_REQB` 는 14칸 모두 키라 CUSTOM 도 빈 값 검사 · 표기 접기 키가 된다.
- `src/capa_simulation/services/core_data_pipeline.py` — CSV·BigDataQuery 결과를 같은 정규화·RQ 변환 길로 잇는다.
  - 등록 이음매 `fetch_registration_dataset` · `merge_registration_dataset` — 조회 · 변환(② 기준 정보 표) 뒤, 프리셋 · 저장(③) 앞에서
    DB 의 활성 부대공정 판을 16표에 합친다(원천 `source_data` · 원천 해시는 그대로). 화면 DB 등록과 공식버전 자동 갱신이 함께
    부른다 — 프리셋(전 공정)이 부대공정을 저절로 넣는다. 내장 시드 부트스트랩은 이 길을 지나지 않는다. 합치기가 예외로 끝나면
    판 없이 BDQ 만으로 등록하고 로그 · 메모 조각 「부대공정 판 n · 합치지 못함」 을 남긴다(D10 — 판 탓으로 등록이 멈추지 않게).
    활성 판 내용을 못 읽어도(`load_active_extra_pack` — 지운 sha · 꼴이 다른 값) 판을 빼고 등록한다.
- `src/capa_simulation/services/extra_process_pack.py` — 부대공정 양식(ZIP 하나 · CSV 여섯 장 `00_info` ~ `05_rate_vital`, 머리 칸은
  Core_Data 칸 이름 그대로)의 읽기 · 접수 검증 V-01 ~ V-14 · 판 번호 판정 · 양식 다시 쓰기 · 판 견주기(Streamlit 없음).
  - 받은 크기 8 MiB(`PACK_MAX_BYTES`)에 더해 풀린 크기도 장마다 8 MiB · 여섯 장 합 32 MiB 까지다(머리 값을 믿지 않고 읽는
    바이트로도 센다 — ZIP 폭탄). 넘거나 지원하지 않는 압축 방식이면 V-01 이다.
  - 폴더 이름은 무시하고 파일 이름으로 찾고, UTF-8(BOM 허용)이 안 되면 CP949 로 한 번 더 읽는다. 글자 칸은 앞뒤 공백 ·
    `="..."` 가드를 벗기고 제품정보는 원천과 같은 `core_data_derivation.normalize_product_names` 를 지난다. V-01(파일 · 인코딩 ·
    NUL 이 든 장 · csv 가 받지 않는 장 — 탭 예외가 아니라 거절 · 머리 칸 · 칸 수)이 어긋나면 뒤 검사를 하지 않는다. 측정률 빈칸 · 0 은 거절하지 않고 1.0 으로 센 칸 수만 센다(D23 (나) —
    0 은 0 그대로 싣고 계산이 1.0 으로 읽는다). `WF 구분` 은 대소문자를 무시해 덮임 · 겹침을 본다. RUN_DAY 는 `달력` 또는 정수다
    (계약 `integer` — 설계 V-11 을 좁힘).
    공정 장(`01_process.csv`)에 공정이 한 줄도 없는 판은 V-03(「공정이 하나도 없음」)으로 거절한다.
  - 판 번호 판정 `judge_pack` — 활성 판과 sha 같음 = 바뀐 것 없음, 끈 동안 마지막 판과 sha 같음 = 다시 켜기, 판 번호 > 적용한
    가장 큰 판 = 적용, 그 밖 = 뒤로 감(거절). 판을 가르는 값은 받은 본문 sha256 이다.
  - `pack_to_zip` 은 같은 판을 늘 같은 바이트로 쓴다(고정 시각 · 글자 칸 가드). `pack_changes` 는 바뀐 칸 수와 그 가운데 활성
    판의 바로 앞 판 값으로 되돌리는 칸 수(G12)를 센다.
- `src/capa_simulation/services/extra_process_merge.py` — 부대공정 판을 BDQ 16표에 펼쳐 합친다(R-01 ~ R-07 — 6장 「부대공정」).
  덧붙이는 행은 BDQ 표와 같은 칸 · 차례 · 형식이다(저장의 칸 집합 대조). 옛 판 걷기(`strip_extra_processes` — 이름으로, 사람이
  더한 STEP 까지) · 걷을 공정 가르기(`split_previous` — 출처에 합침만 있는 공정, 합침 · BDQ 에 생김이 함께거나 섞임 뺌 줄
  `MIXED_REASON` 이면 「섞임」) · 겹친 출처 줄 접기(`fold_outcomes` — 월 머지가 잇는 두 원본의 같은 (공정, 판 차례)) · 얹기
  (`overlay_extra_processes` · `overlay_included_processes`) · 미리보기 시험 계산(`process_rows_frame` · `load_lines` — 같은 표의
  전체 기간 계산 `capacity_outcome` 을 받으면 다시 돌리지 않는다. 셋 다 부하 예외 선언 칸에 기본값이 없고, 등록 R-07 판정
  `capacity_stop` 만 빈 선언으로 돈다 — 선언은 멈춤을 만들지도 풀지도 않는다, 5장 44) · 보고(`ExtraMergeReport` — 메모 · 알림 글 · 출처 줄, 합치지
  못함 `failed`)를 둔다. 표를 제자리에서 고치지 않고 더한 표만 새로 이어 붙인다(나머지 표는 받은 프레임 그대로 — 얹기 · 미리보기는
  걷기가 사본이다). 순수 함수라 자동 갱신 스레드도 부른다. 이어받은 결손 셈(`inherited_capacity_gaps` — R-02, 이미 돌린 계산의
  제외 줄에서 센다 — 등록 길에는 계산을 더하지 않는다)과 월 머지 섞임 가르기(`month_merge_mixing` — 결과 `RQ_REQB` 의 달마다 고른
  원본 · 원본마다 출처로 「판 섞임」(다른 sha)과 「판 · BDQ 행 섞임」(한 원본은 출처 줄이 아예 없는 BDQ 행)을 가른다)도 둔다.
  양식(판)에는 CUSTOM 칸이 없다 — 지정 꼴은 그 제품의 모든 부품에 같은 값으로 펼치고(`_VARIANT_KEYS` · `_PATH_KEYS` 가 CUSTOM
  을 싣는다), 따라가기 꼴은 참조 경로의 CUSTOM 을 잇는다.
- `src/capa_simulation/services/extra_process_revision.py` — 「이 리비전 값을 새 판으로」 의 거꾸로 만들기(설계 3-5 · A15, 순수
  함수). **바탕 판 줄에서 시작한다** — 값 줄(03 · 04 · 05)마다 리비전 기간(그 리비전 계획의 달) 안의 달을 리비전 값과 견주고, 같은
  뜻이면(측정률 빈칸 ≡ 1.0 · `달력` ≡ 그 달 날수 · 대여 빈칸 ≡ 0) 바탕 줄을 그대로, 다른 달이 있을 때만 값이 바뀌는 달마다
  쪼갠다(G3 — 리비전에 값이 없는 달 · 밖의 달은 바탕 값, 열린 끝은 열린 채, `모두` 줄은 갈린 구간만 양산 · ER 로). 그래서 고치지
  않은 리비전은 바뀐 칸 0 이다. 01 · 02 는 바탕 그대로(G2), 앱에서 바꾼 경로(STEP 더하기 · 빼기)는 옮기지 않고 「경로가 판과 다름」 으로
  센다(2026-11-19 사용자 답 Q1 — 리비전 표에서 그 공정을 걷고 바탕 판을 다시 펼친 경로와 맞댄다). 공통 값인데 제품마다 값이 갈린
  공정(G11) · 가용대수를 보유 − 대여와 따로 고친 공정은 옮기지 않고 까닭을 남긴다. 측정률 0 은 0 그대로(G9). 만든 판은 양식 ZIP
  바이트로 다시 접수 검증(`read_pack_zip`)을 지나고, 화면은 그 바이트를 적용까지 그대로 든다(sha 가 바뀌지 않게). 누를 수 없는
  까닭(`revision_refusal` — G4)도 둔다. 시험 `tests/test_extra_process_revision.py`. 양식에 CUSTOM 칸이 없으므로 같은 줄 키에
  부품(CUSTOM)마다 다른 값이 든 공정은 옮기지 않고 까닭 「양식에 CUSTOM 칸이 없는데 CUSTOM 마다 값이 갈림 — 옮기지 못함」
  (`SPLIT_CUSTOM_REASON`)을 남긴다 — 공통 줄을 먼저 본다. 견주는 리비전 표에는 CUSTOM 칸이 있어야 한다(0039 뒤 저장분은 늘 있다).
- `src/capa_simulation/services/object_storage_manifest.py` — 세대 포인터의 키 계약과 받기 · 올리기 · 정리 판정을 담는 순수 계층이다.
  - 가변 포인터(`current.json`) 없이 불변 키 시퀀스로 둔다. 두 DB 는 한 쌍이고 포인터 하나가 두 멤버를 가리키며 키에 멤버 세대를 싣는다(정리가 GET 없이 참조를 안다). 차례는 `object_sync_engine.py` 이고 `scripts/sync_object_storage.py` 는 인자를 읽고 찍기만 한다 — 꺾쇠 · 공백 · 따옴표가 든 주소 · 버킷 · 프로필은 `aws` 앞에서 값이 온 자리 이름만 대고 거절하고(`boot-pull` 밖 — C-DEP 표 값), 하위 명령 끝에 값 없는 「전송용 요약」 한 줄(갈래 낱말 · 세대 번호 · 크기 · 초 · 종료 코드)을 찍는다(`profile` · `boot-pull` 밖 — 셸에 붙여 넣는 블록 · 시작 스크립트가 읽는 JSON 끝줄). 그 위 출력도 주소 · 버킷 · 프로필 · 작성자를 가린다(`profile` 밖) — `doctor` 값 줄은 버킷 앞뒤 두 글자 · 글자 수와 있음/없음, 받아 찍는 진단 글 안의 값은 이름표(`masked`)이고 원값을 보는 옵션은 없다. 표준 오류도 같다 — 명령이 도는 동안 뿌리 로거에 가리는 처리기(`_masked_logging` — 감사 조각 · 사이드카 · 엔진 어느 로거든)를 달고, 잡지 못한 예외의 트레이스백도 `_masked_excepthook` 을 지난다. `page_bootstrap` 을 불러오는 동안만 WARNING 이하 로그를 모두 꺼(그 경고만 거르지 않는다 — 지금 그 사이 찍히는 것이 그 경고뿐이다) Streamlit 캐시 래퍼의 「No runtime found」 경고(수십 줄)를 결과 줄 앞에 찍지 않고, 불러온 뒤 앞 단계로 되돌린다(`inspect_revision_calculations.py` 와 같은 꼴 — 명령이 도는 동안의 로거 글 · 오류는 그대로, 2026-11-25 되돌림 연습. 되돌림은 시험이 새 프로세스에서 본다). 감사 조각을 못 올린 경고(`audit/tool.py`)는 트레이스백 없이 갈래 낱말만 싣는다(E2E D-16). 내 PC 경로가 찍히는 자리(실패한 `aws` 명령 줄의 `--body` · 받을 경로, `fetch-copy` 의 받은 폴더, `init` 의 「로컬 DB 가 없습니다」, `pull` 의 백업 경로, `probe --write` 의 기록 파일)는 홈 폴더(`USERPROFILE` 값과 `X:\Users\<계정>` 꼴 — 짧은 8.3 이름 · `/` 구분자 포함)를 `%USERPROFILE%` 로 찍는다(`mask_home` — 설정을 못 읽은 실행에서도, 출력만이고 여닫는 경로 값은 그대로). 진단 글을 값째 만드는 `io/object_storage.py` 의 `explain_failure` 는 그대로다(시작 스크립트 · 일꾼 쪽은 갈래 낱말만 싣는다).
  - 도구(`scripts/sync_object_storage.py`)와 엔진(`object_sync_engine.py`)에는 동기화 모드(`local` · `managed`)로 명령을 막는 가드를 두지 않는다. 사람이 부르는 명령이라 `local` 에서도 사이드카를 등록하고(`sync_state.enable`) 그대로 돈다(`boot-pull` 만은 시작 스크립트가 부른다). 모드로 가르는 것은 부르는 쪽이다 — 시작 스크립트는 `managed` 일 때만 `boot-pull` 을 부르고(`container_start.plan_sync`), 일꾼은 `managed` + 부트 기록일 때만 선다(`object_sync_worker.start_object_sync` — 16장 `object_sync_worker.py` 줄).
  - 정리는 낱개를 지우기 전마다 원격을 다시 보고 HEAD 가 판정 때와 다르거나 원격이 갈라졌으면 그 자리에서 멈춘다(`PrunePlan.head_key` · `PruneOutcome.interrupted` — 다음 정리가 새 HEAD 로 다시 판정하고, 대가는 낱개마다 목록 한 번이다). `resolve --keep remote` 는 변경 표시도 내리고, 앱이 떠 있으면 거절하며 `--dry-run` 이면 버리지 않는다.
  - **세대 지킴 표지**(`KEEP_PREFIX` — `generations/keep/<seq 12자리>__<기한 YYYYMMDD>__<꼬리 8자리>.json`, 2026-11-24 정식판 마감 2번 B)는 포인터 밖 객체라 HEAD 고르기 · 갈라짐 판정 · 받기가 보지 않고, 포인터 꼴 · 스키마 · origin 은 그대로라 지킴을 모르는 코드도 같은 버킷을 읽는다. `prune_generations(pins=)` 는 기한이 HEAD LastModified 의 UTC 날짜 이상인(`pin_holds`) 표지의 seq 포인터를 남김에 더하고(그 두 멤버는 지금 규칙으로 남음) 표지는 지우지 않는다 — 표지가 없으면 판정이 그대로다.
  - 엔진: `plan_prune` 이 그 접두를 목록 한 번 더 읽는다(GET 없음 — 목록이 실패하면 정리 전체가 실패해 아무것도 지우지 않음, 일꾼 · 도구는 엔진을 거쳐 따른다). `keep_generation`(seq 없으면 HEAD — 포인터를 한 번 받아 두 멤버의 세대 · 마이그레이션 판을 돌려줌, 1 ~ 90일 · 기본 30, 빈 원격 · 없는 세대 · 갈라진 세대는 거절) · `release_generation`(그 seq 표지만) · `list_pins`.
  - 도구: `keep (--head | --seq N) [--days] [--note]`(붙잡는 일이라 `--yes` 없음 · 범위 밖 일수는 `aws` 앞에서 멈춤 · 요약에 seq · 두 멤버 · 두 판 · 기한만, 메모는 싣지 않음) · `unkeep --seq N --yes` · `generations` 의 지킴 꼬리(` · 지킴 ~날짜` · ` · 지킴 지남 ~날짜` · `--limit` 밖 지킨 줄 · 세대 없는 표지 줄 · 요약 `지킴 n`). 운영 절차는 `docs/objectstore_setup.md` 3 · 7 · 8장.
- `src/capa_simulation/services/bigdataquery_catalog_view.py` — 코드 목록을 표시·검색용으로 정리하고 등록 폼 기본값을
  만드는 순수 계층이다(Streamlit import 없음). 코드·PLAN 당 한 행만 남긴다.
- `src/capa_simulation/services/source_csv_view.py` — 원천 CSV 요약(`SourceCsvSummary`)을 DB 등록 탭 「CSV 파일」 길의 값으로 바꾸는
  순수 계층이다(Streamlit import 없음). 목록 표(`build_source_csv_display_frame` — (코드, PLAN) 마다 한 행 · 등록여부 · 저장가능 ·
  행 수, DB 목록과 같은 표지), 값 줄(「**원천 CSV** · 코드 k · n행」), 처음 고른 행(코드가 하나면 첫 행), 등록 칸 처음 값
  (`source_csv_prefill` — 원천 시뮬레이션명 = 코드 · 시나리오명 「<코드> (<코드>)」 로 DB 폼이 이름 빈 행을 채우는 꼴과 같다, 원천 웹
  파일 이름에는 시뮬레이션명 · 주차가 없다 — 시나리오명 끝에 다리 꼬리 「 · CSV」(`source_bridge.BRIDGE_NAME_TAIL`), 메모는 그 코드의
  PLAN 모두), 리비전 메모(`source_csv_note` — 「CSV 파일 <이름>」 ·
  「CUSTOM 파일 값 — 종류 n」, 파일 이름은 `safe_file_name` 로 경로 · 제어 글자를 떼고 60자), 원천 등록시점 판정
  (`optional_registered_at` — DB 폼 `_optional_datetime` 과 같은 판정 · 같은 칸 정규식, 하나로 모으기는 1.0.x).
- `src/capa_simulation/services/source_bridge.py` — 원천 CSV 를 「다리」 원천으로 가리는 판정 한 곳이다(사용자 결정 Q-C1 (나) —
  2026-11-25, 7장 「원천은 두 길」). 원천 유형이 `CSV_CORE_DATA_UPLOAD` 와 글자 그대로 같을 때만 다리다(`is_bridge_source` — 초기 이관
  스크립트의 `CSV_CORE_DATA_INITIAL_*` · 복제 · 파생은 아님). 원천 코드 불변 검사가 견줄 해시(`compared_source_hashes` — 다리 아닌
  원천을 받으면 다리 원천 해시를 뺌), 「등록됨」 으로 셀 코드(`settled_source_codes` — 다리 원천 시나리오를 뺌, 자동 갱신 실행 · DB
  등록 탭 DB 목록이 부름), 원천 CSV 처음 시나리오명 꼬리(`BRIDGE_NAME_TAIL`)를 둔다. 시험 `tests/test_source_bridge.py`.
- `src/capa_simulation/services/auto_official_update.py` — 공식버전 자동 갱신의 규칙(주차·후보·판정·설정·예약·표지)을
  정하는 순수 함수다(차례·기록은 `auto_official_update_runner.py`).
  - 후보(`select_candidate`)는 키워드가 맞고 주차(`W##`)가 더 크거나 같은 주차에서 더 늦게 생긴 코드다(생긴 시각 = 가장
    이른 원천 등록시각). 판정은 공정별 최저 원 확보율이 기준 **미만**이면 off 다(`falls_below_threshold`).
    키워드는 설정 값이고 기본은 `PSM`(`DEFAULT_KEYWORD`)이다 — 시뮬레이션명에 그 글자가 들어 있고(대소문자 무시, `has_keyword`) 주차 `W##` 도 함께 든 코드만 후보다.
- `src/capa_simulation/services/core_data_derivation.py` — 원천 78컬럼에서 RQ 파생용 정규화 작업 프레임을 만든다.
  - CS → 양산구분은 `CS_PRODUCTION_CLASSES` 한 곳이고 규칙 밖 코드는 등록을 막는다(7장). CS 가 빈 행은 막지 않고
    `derive_q_core_data` 가 빼며 그 수(`BlankCsDrop` — 계획 행·경로 행·경로 일부 빠진 남은 계획 줄)를 돌려준다 —
    `build_q_core_data` 는 그 프레임만 준다. `WF 구분` 의
    표기 차이는 등록에서 한 표기로 맞추고(`unify_case_variants`) 계산 쪽 조인은 대소문자 무시로 바꾸지 않는다.
  - `공정` 은 표를 만들기 전에 앞뒤 공백을 뗀다(대소문자는 둔다). 표는 원래 글자로 접고 계산은 공백을 떼고 붙여서,
    `P1`·`P1 ` 이 두 행으로 저장되면 그 리비전의 대당 Capa 가 「연결 키가 중복되었습니다」로 늘 멈췄다.
  - 원천 `CUSTOM` 의 정규화는 여기 한 곳(`normalize_custom_values`)이다 — 앞뒤 공백을 떼고 대소문자 표기를
    `unify_case_variants` 로 모으며, 빈 값(NULL · 빈 글자 · 공백뿐)은 표지 `CUSTOM_BLANK`(`"-"`) 하나로 세운다. 붙여넣기 ·
    부대공정 양식 쪽에 따로 정규화를 두지 않는다. 표지는 편집표 붙여넣기 · CSV 왕복에서 빈 값으로 읽히지 않는다
    (`clipboard_table.TEXT_TABLE_READ_OPTIONS` 는 빈 칸만 NA). 작업 프레임의 CUSTOM 은 RQ 8표의 업무 키로 계산 끝까지
    간다(4장 「CUSTOM」). CS 빈 행 셈의 계획 줄 키(`_ROUTE_OWNER_KEYS`)도 CUSTOM 을 싣는다 — 이 길은 정규화 앞이라
    빈 값을 표지와 같게 맞댄다. 부품 차례 열쇠 `custom_sort_key`(대소문자 접은 글자 → 원문, 빈 값 · 표지는 끝 — 8장)도
    여기 하나다.
- `src/capa_simulation/services/custom_source_check.py` — BigDataQuery 본 표에 CUSTOM 원천 표의 값을 Capa Code 로 붙이고 두 표 행
  수를 대조한다(Streamlit 없음 — 원천 CSV 는 파일에서 센 답으로 같은 판정을 받는다). `check_custom_rows` 는 CUSTOM 원천 표
  답(`CUSTOM_SOURCE_COLUMNS`)을 본 조회 앞에서 검사하고, `attach_custom_values` 는 다시 검사한 뒤 본 표 CUSTOM 칸만 조회표 map
  으로 덮는다(행을 이어 붙이지 않는다 — 행 수 · 차례 · index 그대로).
  - 멈춤(2026-11-22 사용자 답 Q2 (가) · Q9 (가)): 0행 · 칸 모자람 · 한 Capa Code 에 CUSTOM 둘 이상(달마다 다른 것 포함) ·
    줄은 있는데 CUSTOM 이 빈 값(빈 값 표지 글자 그대로 포함) · 본 표 Capa Code 가 CUSTOM 원천 표에 없음. 예시는 부품 · 달로
    `CUSTOM_EXAMPLE_LIMIT` 까지다. CUSTOM 의 앞뒤 공백 · 대소문자는 `normalize_custom_values` 로 접고, Capa Code 는 앞뒤 공백만
    떼며, 생산계획년월은 양쪽을 같은 글자(`202611`)로 맞댄다. Capa Code 가 빈 행은 짝짓지 않는다(본 표는 빈 값 표지).
  - 알림만: 한쪽에만 있는 (Capa Code, 생산계획년월) 칸 · 행 수가 다른 칸(본 표는 받은 행 그대로 센다) — `CustomSourceCheck`
    의 `warns` · `notice()` · `memo()`(늘 「CUSTOM 원천 대조 — 종류 n · …」) · `cells`. 메모는 리비전 · 자동 갱신 메모
    (`scenario_registration.source_check_memo`)가, `warns` 일 때의 글 · 표(칸 `CELL_COLUMNS`)는 DB 등록 사건 알림 `SC-05` 와 그
    Alarm 줄의 표 「CUSTOM 대조」(`bigdataquery_registration._queue_custom_source_check` — 2,000행을 넘으면 표 없이 수만)가 쓴다.
  - 끄개(어댑터의 `CAPA_BDQ_CUSTOM_SOURCE=off` — 7장): `blank_custom_values` 가 본 표 CUSTOM 칸을 모두 빈 값 표지로 덮고(맞댈 칸이
    없어도 멈추지 않는다, 글자 dtype 은 `attach_custom_values` 와 같이 지킨다 — `_with_custom` 한 곳) 대조
    `CustomSourceCheck.switched_off` 를 낸다 — 끝 칸 `attached` 거짓 · 대조 칸 없음 · 종류 1 · `warns` 참. `memo()` 는
    `SWITCHED_OFF_MEMO`(「CUSTOM 원천 붙이지 않음 — 부품 구분 없음(-)」 — 변수 이름 없음, 목록 메모 칸은 모두가 본다), `notice()` 는
    `SWITCHED_OFF_NOTICE`(DB 등록 사건 알림 `SC-06` 글 — 앞 60자가 「CUSTOM 원천 끄개로 부품 구분 없이 등록했습니다」, 표 없음,
    끄개 이름 · 코드는 `_queue_custom_source_check` 가 끝에 붙인다)다. 시험 `tests/test_custom_source_check.py::test_a_switched_off_check_says_so_in_memo_and_notice_and_has_no_cells`.
  - 원천 낱말 · 파일에서 센 답: 멈춤 글 셋(둘 이상 · 빈 값 · 못 찾음)의 자리 낱말은 `CustomSourceWords`(`place` · `several_fix` ·
    `missing_fix`)이고 판정은 같다. 두 공개 함수의 `words=` 기본값 `TABLE_WORDS` 는 둘째 표 글 그대로이고(어댑터 · 자동 갱신은 낱말을
    주지 않는다), 원천 CSV 는 `FILE_WORDS`(「CSV 파일」 · 「원천에서 바로잡아 CSV 를 다시 받은 뒤 올리세요.」)다. 0행 · 칸 모자람 ·
    행수 글은 둘째 표 글 하나다. `custom_rows_of` 는 CUSTOM 이 본 표 칸에 실려 온 원천을 같은 꼴 답(`CUSTOM_SOURCE_COLUMNS`)으로
    센다 — Capa Code · CUSTOM 의 NA 는 빈 글자로 채우고 `dropna=False` 로 묶어 빈 CUSTOM 줄 · 빈 달 줄을 잃지 않는다(잃으면 한
    부품의 빈 줄이 값 든 줄로 조용히 채워지거나, 빈 줄만인 부품이 「없는 Capa Code」 라는 틀린 글로 멈춘다). 공백 · 대소문자 접기는
    검사가 둘째 표 답과 같이 한다. 시험 `tests/test_custom_source_check.py` 의 `test_table_words_are_the_default_and_keep_the_stop_texts` ·
    `test_custom_rows_of_keeps_blank_custom_and_blank_month_rows` 등 일곱.
- `src/capa_simulation/services/reference_conflicts.py` — 같은 업무 키의 값 충돌을 모아 보고서를 만들고 형제 행을 접는다.
  - 승자는 **값이 있는 칸이 많은 행**이다(숫자 `0`·빈 글자는 값 없음). 값을 지어내지 않고 그룹 자리(첫 등장 차례)를 바꾸지
    않는다.
  - 효율·UPEH(`ZERO_BEFORE_BLANK_TABLES`)만 값 개수가 같으면 **0 이 빈 값보다 먼저**다(2026-11-01 사용자 결정). 0·빈 값만
    다른 형제에만 쓴다 — 숫자 실값이 서로 다른 충돌은 건너뛴다(`_real_values_agree`).
    그 두 표 안에서는 0 칸이 많은 행, 같으면 앞 값 컬럼(표를 만드는 컬럼 차례 — `RQ_UPEH` 는 UPEH → ST)부터 0 인 행이 이기고, 충돌 보고서 「임시처리」 칸도 두 표만 「…그 둘만 다르면 0 행」(`ZERO_BEFORE_BLANK_RESOLUTION`)이다.
  - 그다음은 **원천 행 순위**(`source_row_rank`, 2026-11-22 요청 D) — 원천 작업 프레임 전체에서 한 번 만들어
    (`reference_transformer._SourceRows`) 16표가 같이 쓴다. 구분 칸(`SOURCE_ROW_CLASS_COLUMNS` — 제품정보 · Stack · CUSTOM ·
    Capa Code · Customer · CS · Pack Code)부터 `ACTIVE_CORE_COLUMNS` 나머지 차례의 사전식이고, 칸마다 실값은 작은 값부터 · 그
    뒤 0 · 빈 값(차례는 `ZERO_OVER_BLANK` — 2026-11-22 사용자 답 Q4 (가) 0 먼저. 사전식이라 그 칸보다 앞선 칸이 모두 같은 형제에만
    걸리고, 앞선 칸이 함께 갈리면 그 칸이 승자를 정한다), 글자는 앞뒤 공백 뗀 차례 · 빈 글자 끝. 조회 차례와 상관없이 같은 행이
    이긴다. 보유 · 대여 · 가용 같은 형제 표는 표마다 「값 있는 칸 수」가 같을 때만 같은 행을 고른다 — 한 형제만 대여 0 · 가용
    0 이면 그 표만 값이 있는 다른 행을 골라 `보유 − 대여 = 가용` 이 서지 않을 수 있다(늘 같은 쪽 — 맞물림은 답 대기, TODO
    2장). 순위가 원천 행 번호(index)와 어긋나면 멈춘다. `RQ_REQB` 의 표기 접기(`duplicate_route_rows`)도 이 순위 차례로 남길
    행을 고른다.
  - 값이 갈린 그룹마다 「키밖구분」 — 업무 키 밖 구분 칸 c 의 값마다 그 안에서는 갈린 칸이 하나로 맞고 c 값끼리만 다르면 c
    이름(여럿이면 ` | `), 아니면 「그 밖」(`OTHER_CONFLICT_CAUSE` — 재적재 등). 요약(`core_data_pipeline`)은 「키밖 갈림
    그룹수」 · 「그 밖 갈림 그룹수」 두 칸을 더하고, 원인 칸이 없는 옛 꼴 보고서는 두 칸을 빈 값으로 받는다.
- `src/capa_simulation/components/monthly_table_base.py` — Plotly 월별 표가 공유하는 색·치수·글자 계산이다. 분류 칸 글자는
  반드시 `classification_cell_text()` 를 거친다(8장).
- `src/capa_simulation/services/frame_contracts.py` — 서비스 공용 필수 컬럼 검증·업무 키 정규화의 단일 정의다(14-5).
  조회기간 안 계산 밖 공정(소요기준 BOX · PCB 경로가 있는 공정 — `UnimplementedProcess` 의 공정 · 빠진 소요기준 · `whole`)의
  목록도 `unimplemented_basis_processes` 하나다. 두 계산이 행을 버리는 꼴(앞뒤 공백 · 대문자 · `UNIMPLEMENTED_BASES`)로 세고 받은
  표를 고치지 않으며, 달을 못 읽는 행 · 공정이 빈 행은 세지 않아 멈춤 길을 더하지 않는다(11장).
- `src/capa_simulation/services/frame_checks.py` — 중복 키 검사(`assert_unique_keys`)·텍스트 키 strip 의 단일 정의다.
  다음 주기에 `frame_contracts.py` 로 합칠 임시 자리라 새 검증을 더 쌓지 않는다.
- `src/capa_simulation/services/virtual_product.py` — 기준정보를 새 제품 키로 복제해 가상 제품을 만든다(8표, 계획 수량 0).
  복제 단위는 제품 키(제품정보 · Stack)이고 그 제품의 모든 부품(CUSTOM)이 함께 옮겨진다. 그래서 원본 목록
  (`available_source_products`)은 어느 표에든 나온 (제품정보, Stack, CUSTOM) 묶음이 복제 표 **전부**에 있는 제품만 낸다 —
  부품 하나가 한 표에 없으면 그 제품은 빠지고, CUSTOM 칸이 없는 표면 멈춘다.
- `src/capa_simulation/services/korean_particle.py` — 값 뒤 조사(을/를·은/는·이/가·으로/로)를 끝소리로 고르는 단일
  정의다(8장 — `tests/test_particle_sites.py` 가 `scripts/` 출력까지 지킨다). 패키지를 import 하지 않는 스크립트
  (`apply_deploy_package.py` · `build_deploy_package.py` · `build_site_index.py` · `module_test_runner.py`)는 고정 명사를 사이에
  두거나 값을 끝에 둔다.
- `src/capa_simulation/services/weekly_availability_input.py` — 표준 목표 수동 가용대수 입력 표 계약이다(설비 Repository 도
  쓴다). 붙여넣기에서만 빈칸을 「그대로 둠」으로 떨어뜨리고, 보유 공정 밖 이름은 `known_processes` 로 거절한다.
- `src/capa_simulation/services/standard_target_logic.py` — 공정·주차 하나의 표준 목표를 제품·WF Mix 로 분해한다.
  소요대수는 숫자 월로 먼저 거른 뒤 공정명·소요기준을 다듬는다(고르는 행은 같고 글자 처리가 그 달 행에만 걸린다).
- `src/capa_simulation/services/equipment_contract.py` — 설비 세 입력의 컬럼 계약·허용값·상태 이름 상수를 정의한다(7장).
  - 기존 보유대수 자연키는 `BASELINE_KEY_COLUMNS`(공정, 분류)다. 옛 머리 이름은 입구에서 바꿔 읽고(`rename_legacy_headers`)
    빠진 컬럼(`OBSOLETE_EQUIPMENT_COLUMNS`)은 알림만 남긴다. 선택 컬럼은 없어도 된다 — 설비 마스터 입구
    (`read_equipment_update`)에서 새 호기는 빈 칸, 기존 호기는 저장값을 지킨다.
    옛 머리는 두 세대 — 개편 전 32열과 개편 36열(`LEGACY_EQUIPMENT_HEADER_ALIASES`) — 를 그대로 읽는다. 옛 파일을 다시 넣을 일이 드물어도 이 읽기 코드는 지우지 않는다.
  - 사용기준 규칙(`COUNTED_USAGE_BASIS`·`counts_for_capacity`)과 모듈 일치 컬럼(`UNIT_CONSISTENT_COLUMNS` — 읽기·저장 모두
    막는 여섯, `UNIT_SAVE_CONSISTENT_COLUMNS` — 저장 때만 막는 일곱 Area Code·Maker·Model·투자Capa·담당자·보관유무·기존설비여부,
    `UNIT_SHARED_COLUMNS` — 묶음 한 줄을 고치면 같이 바뀌는 14칸 = 여섯 + 일곱 + 레이아웃표시, 사용기준은 셋 어디에도 없다 —
    2026-11-12 사용자 답 3-1 · 3-3)의 단일 선언이다. 한글↔DB 칸 매핑은 공통 칸이 `equipment_repository.EQUIPMENT_MASTER_DB_COLUMNS`, 시나리오 일곱 칸이
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
  - 함께 넣기 후보: 새 호기 = 저장본 공통에 없던 키(`new_unit_keys`). 넣을 새 호기는 `propagate_new_units` 하나로 모두 또는
    아무것도다. 새 비가동(`new_downtime_rows`)은 같은 (키, 유형)
    묶음에 저장본에 없던 시작일이 생겼고 그 묶음에서 사라진 행이 없을 때만이다 — 같은 (키, 시작일) 행이 다른 유형으로
    사라졌어도 고침으로 본다(시작일·유형만 고친 비가동은 퍼지지 않는다). 쓸 일정 행은 「저장본에 일정 행이 있던 호기 ∪
    일곱 칸에 값이 있는 호기 ∪ 비가동이 있는 호기 ∪ 새 호기」 다(`select_schedule_rows`).
- `src/capa_simulation/services/equipment_units.py` — 모듈 행을 설비 한 대로 묶는 `설비키`·`설비지분`과 소수 대수 표기,
  모듈 묶음 판정(`module_group_rows` · `parent_equipment` — `space_layout_edit` 가 같은 이름으로 다시 내보낸다)과 묶음 같이 쓰기
  계획(`plan_group_writes` → `GroupPlan` — 형제는 넘긴 표 전체, 한 번에 같은 묶음 · 칸에 다른 값이 오면 같이 바꾸지 않고
  `split`, 같은 계획이 Main 설비 값을 바꾸는 줄은 같이 온 칸도 그 줄만(답 3-2 move), 잠금 · 값 다듬기는 호출부 몫)의 단일 정의다. 대수를 세는 곳은 행 수 대신 지분을 더한다. 모듈 묶음 환산비 경고는 줄 판정(`module_ratio_warning_rows`)과
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
  - 층 보기 「반입 일정」 의 재료도 여기다 — 반입 표시일(반입실적, 없으면 반입일정 — 점선 테가 실선이 되는 날과 같은 재료)과
    반입 지연(반입상태 지연 · 실적 없음)을 `boundary_payload` 가 `arrivalPlan` · `arrivalDelayed` 로 늘 싣는다(판정에는 쓰지
    않는다, 2026-11-12 Space 보드 답 1-1 · 1-5 · A1).
- `src/capa_simulation/services/space_unit_sheet.py` — Space 「호기 정보」 창(도면 위 — 2026-11-03 사용자 요청)의 표 재료
  `unit_sheet(rows, columns=, place_of=)` — 있는 칸만 그 차례 + 끝 「도면」(배치·미배치·레이아웃 제외, `place_of` 가 없으면
  레이아웃표시로), 칸 꼴(날짜 「YYYY-MM-DD」 글 · 투자Capa 는 수 — 못 읽는 글은 글 · 그 밖은 글, 200자 넘으면 줄임, 빈 값 None),
  행 `{id(설비명 앞뒤 공백 걷음), group(Main 설비), cells}`, 3000줄 상한(`cut`). 거르기·강조는 편집기 JS 이고 Streamlit·DB·색을
  모른다. `tests/test_space_unit_sheet.py`.
  - 배치 편집 창에서 고친 칸의 꼴 읽기 `parse_sheet_cells`(``[{id, col, text}]`` → `SheetCell` — 적용값 읽기
    `space_layout_edit.parse_editor_apply` 가 부르므로 판정 파일이 아니라 여기다)도 둔다.
- `src/capa_simulation/services/space_sheet_edit.py` — Space 배치 편집 「호기 정보」 창 칸 고치기(2026-11-12 시안 보드 답
  5-4 ~ 5-6)의 streamlit 없는 몫. 칸 꼴 · 고를 값은 설비 마스터 표 칸 정의(`columns_payload`), 줄마다 잠금 갈래는
  `equipment_grid.row_lock_kinds`(표 모양 · 출납 `_locked` 와 **한 벌** — 설비명으로 옮긴 것 `unit_lock_kinds`), 창에서만
  잠그는 칸은 `SHEET_FIXED_LOCKS`(설비명 · 동 · 층 · 단계 · 도면)다(data `sheet_edit_data`). 판정 `check_sheet_cells` 는
  다듬기(`coerce_master_cell`) → 묶음 같이 쓰기 계획(`equipment_units.plan_group_writes` — 계획한 줄 하나라도 잠기면 통째로
  막음 · 한 번에 다른 값이면 막음) → 받은 칸을 모두 얹은 마지막 상태와 고치기 앞의 규칙 표(`equipment_master_issues`, 표와
  같은 인자 — 캔버스 · 오늘) 차이로 **새로** 생긴 막는 결과만 그 칸에 짚는다(입력 차례를 타지 않고 다른 호기의 기존
  오류로 막히지 않는다). 편집본은 고치지 않고 얹은 새 프레임을 돌려준다. `tests/test_space_sheet_edit.py`.
- `src/capa_simulation/services/space_color_basis.py` — Space 「색 기준」 그룹(공정구분·투자Capa·필요 단축 — 셋째 값은 그룹이
  없다)을 정한다. 색 값은 모른다. 투자Capa 수 읽기 `capa_number` 는 설비 마스터 표 투자Capa 머리 정렬의 JS `capaNumber` 와 한
  읽기다 — 고치면 둘을 함께 고친다(`tests/test_equipment_master_grid_assets.py` 가 맞댄다). 꼬리 K · M 은 곱하지
  않고 지수(e3 · e6)로 붙여 한 번에 읽는다 — 같은 십진수는 꼴이 달라도(「1.005K」 · 「1,005」) 같은 수 · 같은 그룹이다.
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
    시간대가 섞인 붙여넣기가 pandas 예외 대신 그 값을 든 문구로 막힌다. 시간대 탓으로 못 읽은 값은 까닭을 말하는 문구
    (`_zoned_date_message` — 「{칸}에 붙은 시간대(+09:00·Z)는 받지 않습니다 — 날짜만 적으세요」)로 따로 낸다 — 시간 없는
    오프셋 꼴(`2026-11-05+09:00`·`2026-11-05-05:00`·`11/05/2026 -0500`·`Nov 5, 2026-05:00`·`20261105-0500`·`2026-11-05Z` —
    날짜는 연도가 앞인 꼴·월이 앞인 꼴·8자리·영문 달 꼴, 날짜 뒤 빈칸이나 `T`, 부호 뒤 `h:mm`·`hh:mm`·`hhmm`)도 이 문구다
    (`_offset_only_date` — 부호 뒤가 두 자리뿐이거나 초까지 있으면 시각인지 갈리지 않아 시각으로 읽는 지금대로 둔다).
    더하기·Z 꼴은 pandas 가 그냥 못 읽지만 빼기 꼴은 뒤를 시각 05:00 으로 읽어 받으므로 `_read_master_dates` 가 칸을 읽기
    **전에** 빼기 꼴(`_minus_offset_date`)을 못 읽은 값으로 가린다(2026-11-02 사용자 결정 「막는다」 — 칸 첫 값이어도 칸의
    날짜 꼴을 정하지 않는다). 글자 값만 보므로 저장본(DATE)을 다시 읽는 리비전은 달라지지 않는다. 시간대가 섞인 칸에서만
    가리는 `_zoned_date` 는 넓히지 않는다. 칸 결과는 줄마다,
    저장·붙여넣기 거부는 시간대 줄부터 그 값만 예시로. 표 차례가 저장 거부 문구의 계약이고, 시험이 규칙마다 거부
    문구를 글자 그대로(예시·다섯 개 제한까지) 고정한다(`tests/test_equipment_validation_issues.py`).
  - 신규 호기의 반입·Qual 은 비워도 되고 순서는 있는 날짜끼리 본다. 정지 ≤ 반출/이설이고, 실적 검사와 모듈 묶음 일곱 칸
    갈림(`unit_group_mixed_saved` — 여섯 칸 `unit_group_mixed` 바로 뒤, `_MasterFrame.saving`)은 저장할 때만 `today=` 로
    돈다 — 리비전 읽기·계산·발행·복제는 막지 않고 저장(편집본 전체)만 막는다(2026-11-12 사용자 답 3-3 (나) · P2). 그 저장 거부
    글은 예시 목록(`['…']`) 대신 끝에 고칠 곳을 쉼표 글로 짚는다(`UnitGroupSplitError` — 머리 · 칸 · 갈린 묶음 전부를 싣고, 글은
    `unit_group_split_message` 한 곳: 「… — 설비 마스터에서 {묶음, …} 묶음의 {칸} 칸을 맞춘 뒤 저장합니다」, 묶음은 앞 다섯에
    넘으면 「외 n」. Space 배치 저장 · 리비전 저장 · 사이드바 저장이 같은 글). 엑셀 · CSV 붙여넣기 미리보기는 이 예외를 잡아
    「… — 붙여넣을 표나 설비 마스터에서 … 맞춘 뒤 다시 미리봅니다」(`pasting=True`)로 다시 알린다. 여섯 칸은
    다른 거부와 같은 예시 목록 꼴(앞 다섯)이다. 환산비·좌표·크기는 빈 칸과 못 읽는 값을 가른다(`_read_number`·`_read_ratio`).
  - Space 위치: 레이아웃표시는 도면 대상인지만 가르고 좌표를 강제하지 않는다(없으면 미배치 칸). X·Y·크기는 짝으로 둔다.
  - Main 설비는 다른 행의 설비명과 같을 수 없다(`UnitGroupCollisionError`, 문구는 `unit_group_collision_message` 한 곳).
  - **칸 다듬기는 칸마다 그 칸의 입력만 보는 한 길이다**(`_read_column` — 글 단계 차례표 `_TEXT_STEPS` · 좌표 · 환산비 · 날짜) —
    처음부터 읽기와 바뀐 칸 읽기가 같은 길을 지난다. 칸 꼴 지름길: 날짜 칸이 이미 시간대 없는 날짜 dtype 이면 글자로 바꿔 다시
    읽지 않고 자정으로 맞추고(일반 길 `_read_date_values` 와 같은 값 · dtype — 편집본 · 저장본의 `datetime64[us]`), 실수 칸(좌표 ·
    크기 · 환산비)은 빈 값이 결측뿐이라 글자 비교를 건너뛰며(일반 길 `_read_number_values` · `_blank_number_values`), 글자 칸은
    `astype("string")` 사본을 덜어 낸다. 모듈 묶음 칸 갈림(읽기 · 저장 때)은 열쇠가 두 줄 이상인 묶음만 groupby 한다 — 한 줄
    열쇠는 갈릴 수 없어 찾은 것 · 차례 · 거부 글이 같다(`tests/test_equipment_validation_fast_paths.py`).
  - **바뀐 칸만 다시 보기**(`equipment_master_issues_since`): 규칙 표 줄마다 보는 칸(`MasterRule.reads` — 다듬은 값 · 못 읽은 줄
    표지 · 입력 날짜, 설비명은 늘 본다)을 적고, 앞 계산의 재료(`MasterIssueState` — 계약 39칸 사본 · 다듬은 한 벌 · 규칙별 칸
    결과)에서 바뀐 칸만 다시 다듬고 그 칸을 보는 규칙만 다시 본다. 줄 수 · 설비명 칸 · 층 캔버스 · 오늘이 다르면 처음부터다. 칸
    견줌(`same_column`)은 같은 dtype 의 글자 · 실수 · 날짜만 비트 그대로 견주고 그 밖은 늘 「바뀜」 이다. `reads` 가 None 인 규칙은
    늘 다시 본다 — **새 규칙은 `reads` 를 적는다**(칸 그물 `tests/test_equipment_master_issues_since.py` 가 규칙마다 적은 칸만 남겨도
    같은 결과인지 · 적은 칸 하나를 빼면 걸리는지 본다 — 7장).
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
    "locked"` 일 때 `master_tab_lock_reason` 을 넘긴다 — 설비 마스터 탭 자리에는 Space 와 같은 표지 「배치 잠김」
    (`equipment_master_tab.LAYOUT_LOCK_MARK`) 한 마디이고 무엇이 잠기는지 · 까닭은 풍선 `layout_lock_help` 다)는 있던 호기 배치 일곱 칸·새 호기 자리 넷을 잠그고, 이름·Main 설비·배치·행을
    바꾼 op 뒤마다 `locked_layout`(작업 공간 `layout_edits(...).apply` 와 같은 판정 — `layout_overlay.assumption_common_places`,
    시험이 대조한다)으로 맞춘다: 있는 묶음에 드는 새 호기와 동·층 미정 호기는 그 묶음의 동·층에 X·Y 비움. 맞춘 칸은 그 op 의
    되돌리기 단계에 든다. 공식(`"official"`)·가정(`"overlay"`) 편집이면 `layout_lock` 은 None 이고 배치 칸은 잠기지 않는다 — 가정
    세션의 배치 칸 고침은 그 시나리오의 배치 차이로 저장된다. 화면 쪽(B1-c)은 op 를 얹은 뒤 `layout_edits` 가 비지 않으면 그때의
    역할을 찍는다(`stamp_layout_role` — 탭 제출과 같다).
  - 행 id 는 `s:` + 저장본 설비명(이름을 바꿔도 그대로)·`n:` + 지금 이름(새 호기)이고 짝은 저장의 호기 키 규칙
    `inherited_unit_names` 그대로다(`grid_index`). 같은 이름 둘째 줄 꼬리는 설비명에 나올 수 없는 글자(`DUPLICATE_MARK`)로 붙이고
    겹치면 번호를 올린다. 저장본 호기인지는 **id 글자를 풀지 않고** `GridIndex.saved`·`saved_name`·`is_new` 로 가른다(설비명 규칙은
    「~」 를 받는다). 칸 글자 `cell_text` 가 화면 글자이자 「바뀐 칸」 견줌 글자다.
  - 글자 행렬은 바뀐 칸 · 줄만 갈아 끼워 다시 만든다(`text_matrix_since` — 직전 행렬 `TextMatrix` 와 그 재료(계약 칸 사본)에서 칸마다
    `equipment_validation.same_column` 으로 견주어 바뀐 칸만 글자로 바꾸고 글자가 달라진 줄만 새 줄로 갈아 끼운다. 줄 수 · 칸 목록이
    다르면 통째로 만들고 앞 행렬의 줄 목록은 고치지 않는다 — 통째로 만든 것과 같다).
  - `build_grid_view` 한 번에서 세 마운트 data(`grid_data`·`loader_data`·`detail_data`·`changes_data`)가 나온다 — 같은 입력이면
    같은 dict. `detail_data` 는 모듈 묶음(둘 이상) 줄에 `unit.group`(Main 설비 · 줄 수)을, 늘 `sharedCols`(같이 바뀌는 14칸 자리)를
    실어 브라우저가 그 칸 이름 곁에 「묶음」 글 표지 + 풍선을 단다(2026-11-12 답 3-5). 칸 초안이 있는 칸에는 편집본 옛 값의 규칙 결과를 싣지 않는다(초안 오류 하나). 출납을 보내는 마운트(표·오른쪽 칸 둘)
    는 저마다 제 `ack` 를 싣는다. 출납 결과 글(`GridApplied.toast`)은 띠가 아니라 알림창 · Alarm 으로만 가고(`queue_grid_result`,
    설계 규칙 UI-NTF-03 — 2026-11-07 답 undo-strip), 마운트에 싣는 `toast` 는 오른쪽 칸 자리 거부 한 줄(막힌 「호기 추가」 · 가져오기
    「찾지 못했습니다」 — `queue_grid_toast`, `toast_payload`)뿐이다. 「호기 추가」 가 넣은 회차는 그 호기를 「호기 상세」 로 연다
    (`GridApplied.added`).
    `grid_data(open_id=)` 는 상세에 연 줄의 띠다. 표 마운트 data 는 껍데기(칸 정의 · 잠금 · 불러온 줄 · 지문 `shell` —
    `shell_token`)와 feed(`GRID_FEED_FIELDS` — ack · 수 · 옮김 · 끼운 줄 · 연 줄 · 깨끗함 — 와 껍데기 뒤 바뀐 줄)로 가른다
    (`split_grid_data` — 앞 껍데기의 줄 밖 칸 · 줄 id 차례가 같고 바뀐 줄이 `GRID_PATCH_LIMIT` 이하면 그 껍데기를 그대로, 아니면 새로
    짓는다. `join_grid_data` 가 거꾸로 이은 것은 원래 data 와 같다 — 브라우저 `joinGridData` 와 같은 꼴). 불러오기 data 의 조건 칸(옛 표 보기 거르기 13칸, 사용자 R1)은 칸마다 값 번호를
    64자 고정 폭 글자로 잇는다(`encode_codes` ↔ JS `decodeCodes` — 브라우저는 고른 값을 번호가 아니라 글로 기억한다).
  - 출납: `pending_ops` 가 두 마운트의 상태 값 `outbox` 에서 반영 안 된 op 만 `(at, mount, seq)` 로 고르고, `apply_ops` 가 차례로
    얹는다 — `base` 가 다르면 버림, 잠긴 칸·지운 줄·낡은 세션의 저장본 호기 지우기는 파이썬도 막음, 칸 값은
    `coerce_master_cell`(저장 정규화와 같은 함수)로 다듬고 못 다듬은 글은 칸 초안(`overlay` — 편집본 밖)에 둔다. 칸·호기 상세·
    붙여넣기·값 넣기는 한 함수(`_write_shared`)를 지나 모듈 묶음의 같이 바뀌는 칸이면 op 하나에 계획 하나
    (`plan_group_writes`)로 형제 줄(표 전체)도 같은 값으로 쓰고 한 되돌리기 단계에 쌓는다 — 형제 하나라도 잠기면 통째로 거절해
    까닭을 알림창에, 한 번에 다른 값이면 받은 칸만, 못 다듬은 글은 그 줄 초안만, 고친 줄이 그대로여도 형제가 바뀌면 바뀐 것(같은 값
    다시 넣기로 갈린 묶음이 풀린다). 막지 않는 레이아웃표시(`_QUIET_SHARED`)만은 고친 줄 값이 실제로 바뀔 때만 퍼뜨린다(일부러 끈
    모듈이 같은 값 다시 넣기로 켜지지 않게). 불러오지 않은 형제는 고친 줄 바로 아래에 끼운다(`GridApplied.inserted` — 고친 줄이 목록에
    없으면 끼우지 않는다, 2026-11-12 답 3-4). 설비명 칸
    확정은 이름 바꿈(`check_unit_rename`·`apply_name_changes`·`compose_unit_renames` — Space 와 같은 넷, 사용자 R2·G4)이다.
    지우기는 비가동을 함께 빼고, 되살리기는 **저장본 값**을 **저장본 차례** 자리에 넣는다(차례만 다른 공통 리비전을 만들지 않음).
    칸·호기 되돌리기(`revert`)는 저장본 쪽으로 가는 길이라 낡은 세션의 시나리오 칸·가정 배치 칸 잠금을 보지 않는다(낡기 전에 고친
    일정을 되돌려야 저장이 거부되지 않는다) — 모듈 묶음 좌표·크기만 그대로 두고 알림창으로 알린다. 같이 바뀌는 칸은 지금 묶음
    형제의 그 칸도 저마다의 저장본 값으로 돌린다(새 형제는 막는 열세 칸만 되돌린 줄의 저장본 값으로 맞추고 레이아웃표시는 그대로, 호기
    되돌리기가 Main 설비도 돌려 묶음을 떠나면 같이 돌리지 않는다). `base` 가 달라 버린 op 는 부르는 쪽이 가린
    까닭의 결과 글(`apply_ops(dropped_toast=)` — 남의 저장 `FOREIGN_DROPPED_TOAST`, 그 밖 `DROPPED_TOAST`)로 알림창에 센다(제 저장
    직후 op 는 버리지 않고 화면 쪽이 저장본 위로 옮겨 얹는다 — `moved_op`).
  - 되돌리기 `UndoStep` 은 역 patch(조작 뒤 자리)라 나중 것부터만 맞는다 — 표의 조작만 쌓고 다른 길이 편집본을 바꾸면
    목록을 비운다(B1-c). 되돌리기는 「저장 전 변경」 칸의 「한 단계 되돌리기」 하나다(2026-11-07 답 undo-strip). 불러온 목록은 화면 조작으로도 바뀌므로 사진으로 되돌리지 않고
    옮긴 id(`moved` — 새 호기 이름 바꿈, 칸 초안 열쇠 옮김도 역 patch)·뺀 자리(`unloaded`)로 되돌린다(통째 단계만 사진). 출납 ·
    「한 단계 되돌리기」 결과의 `moved` · `inserted` 는 다음 표 그리기에 한 번 싣고(`equipment_master_tab.VIEW_CARRY_KEY` →
    `grid_data(moved=, inserted=)`), 브라우저는 목록 지문이 그것으로만 바뀐 회차에 고름·기준 줄·스크롤을 지킨다(`keptView` —
    설계 규칙 UI-PRF-03). 끼운 줄이 있는 그 회차에는 보던 첫 줄이 새 보이는 차례에서 옮겨 간 줄 수 × 줄 높이만큼 스크롤을
    옮긴다(`keptRowShift` — 고친 줄이 위로 굴러간 채 호기 상세에서 고쳐 형제가 그 앞에 끼워진 때도, 정렬한 칸 값이 바뀌어 줄이
    앞뒤로 옮겨 간 때도. 보던 줄이 고친 줄 자신이면 그 줄을 따라간다. 늘어난 높이를 먼저 세운다). 이름 바꿈을
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
    두 번 누른 둘째 op 가 이름 겹침으로 거부되어 첫 op 의 성공 알림을 덮지 않게, 가져오기 뒤 옛 초안이 들지 않게). 받은
    초안을 다시 보고 막히면 넣지 않고 그 까닭을 「새 호기」 칸 자리 거부 한 줄로, 아니면 편집본 설비 마스터 **끝**(행 차례는 공통 대장 내용)에 한 줄을 잇고
    불러온 목록 맨 위에 두며 되돌리기 한 단계, `GridApplied.added` 에 (행 id, 설비명, 함께 넣기)를 싣는다. 가정 편집 회차면 결과 알림에
    「공식 배치에는 자리 없이」(설계 Q1). 가져오기는 `copied_draft`(호기 정보 묶음 — 설비명·Main 설비 뺌 — 와 동·층·레이아웃표시,
    기존설비여부 N, 투자구분 기존 → 신규)·`copy_source`(같은 이름 → 앞부분 첫 줄)이고, 추가 뒤 초안은 `kept_draft`(공정소분류·동·층).
    칸 data 는 `new_unit_data`(칸 자리 번호의 오류·경고·잠금·체크 줄·초안 번호 `seq`·`checked`).
- `src/capa_simulation/services/edit_grid.py` — 범용 편집 그리드(Components v2 — 화면 공통 계층의 같은 이름 컴포넌트)의 streamlit 을
  모르는 규칙. 열 규격(`GridSpec`·`ValueFormat` — percent·fixed·sig, 정수·하한·상한·빈칸 = 0), 업무 키(`row_keys` — 분류 칸
  `astype(str)` 을 `\x1f` 로 잇고 같은 키의 둘째부터 `\x1e<n>`), 양식 색인(`build_index` — 키 → 줄, 값 float64 행렬, 월 → 칸),
  값 다듬기(`coerce`)·표시 형식(`format_value`), op 고르기(`parse_outbox`·`new_ops` — 마운트별 seq, `(at, mount, seq)` 차례,
  최근 마운트 `MOUNT_LIMIT` 8개), op 반영(`apply_ops` — 받은 초안·이력을 바꾸지 않는다), 변경 수·목록(`change_counts`·
  `change_list`)과 양식 되머지(`merge_into_template` — 업무 키로, 오류 칸이 있으면 ValueError)가 한 곳이다.
  - **초안은 업무 키 + 월**(`DraftState` = ``{"cells": {키: {월: 값|None}}, "bad": {키: {월: (적은 글, 코드)}}}`` 또는 None)이라
    줄 차례(공용 표시순서)가 바뀌어도 같은 칸에 붙는다. 양식과 같은 값이 되면 그 칸을 지운다. 세션에는 기본형만 둔다(5장 21).
  - **값 다듬기는 Python 이 정본**이고 브라우저(`eg_pure.js` `parseInput`)는 같은 규칙의 미리보기다 — 공백은 정한 글자 묶음만
    걷고(`_STRIP` — `str.strip()`·JS `trim()` 은 걷는 글자가 다르다), 수는 유한한 값만, 천 단위 쉼표는 엄격한 세 자리 묶음만,
    `percent` 표만 「85%」(소수점을 두 자리 옮긴 글로 읽는다 — 「99.99%」 → 0.9999), 하한·상한·정수 검사는 양식과 같은 값이면
    하지 않는다. 오류 코드 다섯(`num`·`finite`·`min`·`max`·`int`)이고 오류 칸은 적은 글이 그대로 남는다. 표시 형식은 이진 값
    그대로에서 반올림한다(Decimal `ROUND_HALF_UP` — JS `toFixed`·`toPrecision` 과 같다). 둘 다 `tests/fixtures/edit_grid_cases.json`
    의 같은 사례를 같은 답으로 낸다(쌍둥이 시험 `test_edit_grid_service`·`test_edit_grid_assets`).
  - **op**(`OP_NAMES`): `write`(줄 × 칸 직사각형에 값 덩어리를 `(i mod h, j mod w)` 로 되풀이 — 덩어리의 `null` 은 그 칸을 그대로
    둔다, 값 칸 `PASTE_CELL_LIMIT` 15,000 넘으면 버리고 안내)·`fill`(`src` 직사각형 + `dir` down·up·right·left — 원본에서 멀어지는
    차례 k 로 down·right 는 `k mod h`, up·left 는 `h-1-(k mod h)`, 원본 값은 서버의 지금 값(초안 ∪ 양식))·`clear`·`revert`(초안을
    지워 양식으로)·`undo`·`redo`. op 하나 = 되돌리기 한 단계(직사각형의 전·후 상태), `UNDO_LIMIT` 40 · 이력 칸 `HISTORY_CELL_LIMIT`
    200,000(넘으면 오래된 단계부터 — 맨 새 단계는 남긴다), 새 op 가 오면 다시 실행 목록을 비운다. 이력 `gen` 과 다른 op·다른 표의
    op·꼴이 틀린 op(`kind="bad"`)는 버리되 ack 는 하고 수를 토스트로 알린다. 양식에 없는 줄은 건너뛰고 센다.
  - **줄 규칙 표는 고른 표만**(2026-11-18 접속 명단 편집 표 — 지금은 `components/access_list_grid` 하나). 칸마다 형식
    (`GridSpec.column_formats` — `text` 글: 앞뒤 공백 걷음 · 제어 문자 `text` · 글자 수 `len` · `pattern` 전체 맞음 오류, `choice`
    고르기: 항목 글과 같아야 그 차례 번호 · 수는 차례 번호 그대로(채우기 원본) · 그 밖 `choice` 오류 — 값은 번호라 초안 · 이력 ·
    채우기가 수 칸과 같은 길이다), 보이는 분류 칸이 아닌 업무 키 칸(`id_column` — 명단이 다시 읽혀 차례가 바뀌어도 초안이 제 사람에게
    붙는다)과 줄 이름 칸(`label_column` — 상태 줄 · 변경 목록), 줄 규칙(`RowRules` · `LockKind` — 줄마다 잠긴 값 칸 · 까닭 · 지울 수
    없는 까닭 · 빈 새 줄)과 줄 지우기 · 되살리기 op(`row_ops` — `remove` · `restore`, 초안의 예약 칸 `ROW_REMOVED` = 1.0, 빈 새 줄의
    지우기는 그 줄 칸 비움, op 하나가 그 줄들 × 값 칸 + 표지 칸 한 단계). 잠긴 칸 · 지울 수 없는 줄은 op 반영이 건너뛰고 센다(토스트
    `LOCKED_TOAST` · `LOCKED_ROWS_TOAST` — 브라우저도 막지만 서버가 다시 본다. 붙여넣기 · 비우기 · 채우기는 브라우저가 잠긴 칸을
    미리 세어(`egRuleLocks`) 상태 줄 칸 수에서 빼고 같은 글(`lockedSkipped`)을 잇고, 모두 잠겼으면 op 를 보내지 않고 그 까닭을
    상태 줄에 둔다). 줄이 누구인지 말하는 잠긴 칸(`LockKind.anchor` —
    접속 명단은 명단 사람 줄의 「계정」)에 쓰기(`write`)가 양식과 다른 값(앞뒤 공백 · 대소문자 무시)을 실으면 그 줄은 칸을 하나도
    쓰지 않고 센다(`ANCHOR_ROWS_TOAST` — 차례가 다른 목록을 붙여 다른 사람의 등급이 들어가지 않게. 브라우저는 덩어리를 그대로 보내고
    서버가 가른다. 채우기는 보지 않는다). 글 칸 양식 값은 `GridIndex.text_values`(행렬 자리는
    NaN), 되머지는 글 칸을 글로, 지운 줄은 `removed_keys` 로 따로 읽는다. 주지 않은 표의 껍데기 · feed · op 반영은 그대로다(시험
    `tests/test_edit_grid_rows.py` · 쌍둥이 사례 `edit_grid_cases.json` 의 `kinds`).
- `src/capa_simulation/services/edit_grid_payload.py` — 범용 편집 그리드가 보내는 두 data 의 꼴(streamlit 모름). 껍데기
  본문(`encode_table` — 분류 칸 사전 `dims`·표시명 `labels`·줄마다 고정 폭 64자 코드 `codes`, 값 사전 `vals`(0 번은 빈칸)·줄마다
  (값 코드 + 길이 1글자) RLE `runs`(63 넘는 런은 나눔), 중복 키 꼬리표 `dupes`)과 색인을 한 번에 짓는다(`build_base` — 캐시
  `simulation_cache.get_edit_grid_base` 가 부른다, numpy 로 벡터화). `encode_base` 가 호스트·`baseKey`(`base_key` = 표:내용 토큰:줄
  차례 지문:표시명 지문)·글·팔레트·줄 높이·상한을 더하고, `encode_feed` 는 초안(줄마다 (코드 + 길이) RLE — 0 초안 없음 · 1 빈칸 ·
  2 못 읽음 · 3.. 값 사전 `dvals`)·오류 칸 앞 `BAD_LIMIT` 2,000개·수·되돌리기 수·ack·토스트·필터를 싣는다. 바이트 예산은
  `tests/test_edit_grid_payload.py`(합성 2,660×30 껍데기 ≤ 100,000 B, feed 1·100·15,000칸 ≤ 1·4·64 KB). 줄 규칙 표만 껍데기에
  `fmts` · `ids` · `rowLabels` · `locks`(규칙마다 잠긴 값 칸 번호 · 까닭 · 지우기 까닭 · 빈 새 줄, 줄마다 규칙 번호) · `rowOps` 를 더
  싣고 값 사전에 글이 들며(`_object_codes`), feed 에 지운 줄 `removed`(있을 때만)가 선다.
- `src/capa_simulation/services/equipment_samples.py` — 설비 DB 가 빌 때만 쓰는 비영속 샘플 fleet 이다(연결 뒤 지운다).
  - `SAMPLE_BASELINE_COUNTS` 는 생성기 `PROCESS_SPECS` 를 옮긴 것이라 함께 고친다(`tests/test_equipment_availability.py`).
  - 샘플을 그리는 동안의 화면 글 · Guide 이름은 「설비 합성 샘플」 하나다 — 옛 꼴 「설비 샘플」 · 「설비 샘플(데모)」 · 「데모 fleet」 · 「합성 fleet」 은 `tests/test_one_concept_one_name.py` 의 `RENAMED` 가 막고, 주석 · docstring 의 코드 말은 그대로 둔다.
- `src/capa_simulation/services/chatbot_samples.py` — Capa Chatbot 답변 대본(결론·근거 표·산식·한계)이다. 순위·Gap 은
  원본 공정명으로 셈하고 결론·질문·조건의 공정 이름만 부르는 쪽이 넘긴 글자 함수(`process_name`)로 적는다 — 표시명
  모듈은 import 하지 않는다(8장). 근거 표 숫자 칸의 꼴(`SampleAnswer.evidence_formats` — 실적 화면 표와 같은 퍼센트·
  `Gap (%)`)은 대본이 정하고 화면이 `st.column_config` 로 옮긴다 — 서식이 없어 Gap 이 분수(-0.1093)로 나왔다(2026-10-30
  E2E). 지표마다 단위가 다른 「왜 부족해?」 표는 미리 지은 글로 싣는다 — % 글(효율 · 수율 기준 · 실적과 세 지표 Gap)은 표의 % 칸과
  같은 소수 둘째 자리 고정(`services.edit_grid.fixed_percent_text` — 8장 「표의 % 칸」, 같은 화면 첫 답 표와 82.00% 로 같은 글)이고
  UPEH 기준 · 실적은 지표 화면의 대수 글이다. 「기준 미달」 결론은 센 기준(상태
  「개선 필요」·「관찰」 — 마지막 달까지 연속 미달)을 밝힌다.
- `src/capa_simulation/services/floor_layout_mark.py` — 층 도면 비설비 요소의 계약·검증(`prepare_floor_layout_marks`)이다.
  층 단위 전체 교체라 어긋난 항목 하나에 통째로 거부한다(7장).
  - 영역만 테두리 모양·이름표 정렬(`ZONE_BORDER_STYLES`·`ZONE_LABEL_ALIGNS`, 첫 값이 처음 값이자 옛 행의 값 —
    `zone_look`)을 갖는다. FAB 요소(`fab_layout.prepare_fab_layout_marks`)도 같은 규칙이다.
  - 요소 모양 값 `look`(설비 `0033`, 정규 JSON 글 — `mark_look`)은 종류마다 받는 키(`LOOK_KEYS` — 동선 머리·선 셋, 베이는
    + 뒤집기)만 받고 처음 값(`LOOK_DEFAULTS`)인 키는 빼며 다 처음 값이면 빈 글이다. 받지 않는 키·틀린 값은 거부, 모양 값이
    없는 종류는 보낸 값을 보지 않는다. `editor_payload` 는 빈 모양 값의 `look` 키를 싣지 않는다(요소 지문이 0033 전과 같다).
    베이(`bay`, 층만)의 이름표는 번호다(`bay_label` — 앞 B 를 떼고 10자). FAB 요소도 같은 `mark_look` 이다(동선·도형).
  - 도형(`shape`, 층·FAB)은 프리셋 `look.shape`(`SHAPE_PRESETS` 아홉 — 없으면 사각형)를 먼저 정하고 모양 조절 값 `adj` 를 그
    프리셋의 개수·범위·0.01 단위로 본다(`SHAPE_ADJUST` — 처음 값과 모두 같으면 뺀다. 두께·둥글기·머리 길이는 짧은 변
    기준 비율 — 2026-11-04 Space 결정 보드 답, 편집기 「모양 조절 값의 기준」. `SHAPE_ADJUST_BASE` 의 `min-w` · `min-h` 값은
    저장 상한이 상한 × `SHAPE_STRETCH_MAX` 다 — 그 축 길이까지 굵어질 수 있고 그릴 때 편집기가 상자로 묶는다). 채우기 불투명 `fillAlpha`(0~100 의 5 단위)·
    선 `line`(`SHAPE_LINE_KEYS` — `auto`·`none`·`ink`·영역 색, 강조색 없음)·`lineWidth`·`lineStyle`·`flip`. 채우기 색은 요소
    `color`(`shape_fill` — `SHAPE_FILL_KEYS`, 처음 파랑, `mark_color`), 빗금은 영역·도형만(`HATCH_MARK_KINDS`), 「설비 금지」는
    영역만이다. 막는 요소(`BLOCKING_MARK_KINDS`)가 아니다.
  - 발자국(`footprints`, 층·FAB — 2026-11-12 Space 시안 보드 6-1 ~ 6-6)은 선 꼴 요소다. 상자의 한 축이 길이, 다른 축이 띠
    (`FOOT_BAND` 3칸 고정 — 0·180° 는 높이, 90·270° 는 폭)이고 길이는 `FOOT_MIN_LENGTH` 3칸부터다. 어긋나면 `footprint_box` 가
    거부한다(조용히 고치지 않는다 — 띠 값은 저장 계약). 모양 값은 발 모양 `foot`(`FOOT_SHAPES` 여섯 — 처음 밑창)·간격 `gap`
    (`FOOT_GAPS` 셋 — 처음 보통)·선 색 `line`(`LINE_COLOR_KEYS` — 처음 강조색)·`flip` 이다. 막는 요소가 아니고 빗금이 없다.
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
  - 얹기 `apply_unit_overlay` 는 **예외를 내지 않는다**(I4) — 모듈 묶음(Main 설비 행 둘 이상, `equipment_units.module_group_rows`
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
    흔들리지 않는다·`effective_group_labels`·`label_changes`), 설비 단위 셈 `overlay_unit_count`(묶음은 1대)·배치 알림
    (`EQ-13`) 재료 `layout_difference`(실효 설비 수·레이아웃표시만 다른 수·일정 없어 뺀 수·저장된 행 수 — S3 가 낸다), 일정 리비전 출처
    허용값 `SCHEDULE_REVISION_ORIGINS`(+ `layout_clear`).
  - S4: 「공식과 견주기」 재료 `layout_compare`(층 하나 — 기준 쪽 점선 상자 `CompareGhost`·들어온 호기 `CompareArrival`, `shown` 은
    화면이 그리는 설비명)·`unit_differences_by_floor`(층마다 공식과 자리가 다른 설비 수 — 나간·들어온·안에서 옮긴, 묶음 1대,
    일정 없음 제외 — `shown=` 을 주면 그 설비명만), 남의 공통 저장 뒤 다시 얹기 `reapply_layout_edits(옛 저장본, 편집본, 새 저장본,
    origins=, old_keys=, new_names=, approved=)` → `ReappliedLayout`(다시 얹은 **설비 단위** 수 — 묶음 1대·빠진 호기·옮긴 편집기
    묶음 승인 — 있던 호기의 일곱 칸을 원래 칸 값 그대로), 공식 발행 막힘 글 한 곳 `layout_publish_blocked_words(PublishBlock)`(확인
    팝업·발행 쓰기 거부가 같이 쓴다).
- `src/capa_simulation/services/fab_layout.py` — FAB 동·층 정의, 층 이름·주소 인자 변환, FAB 전체 도면의 계약·검증
  (`prepare_fab_layout_marks`)을 둔다. 요소 행이 없으면 `default_fab_layout()` 기본 배치를 그린다. FAB 요소 종류는 영역·글자·
  동선·발자국·도형·층 블록(`FAB_MARK_KINDS`)이고 도형·발자국·모양 값은 층 요소와 같은 규칙이다.
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
  - 모듈 묶음 판정(Main 설비가 같은 행이 표 전체에서 둘 이상)은 `module_group_rows` 한 곳이다(정본은 `equipment_units` —
    여기는 같은 이름을 다시 내보낸다) — 저장 전 바둑판 검사와 가정 배치 차이의 묶음 통째 규칙(`layout_overlay`)·설비 마스터 표의
    묶음 같이 쓰기(`plan_group_writes`)가 같이 쓴다. `PLACE_COLUMNS` 는 계약의 배치 일곱 칸 `SCENARIO_LAYOUT_COLUMNS` 다.
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
- `src/capa_simulation/services/floor_layout_profile.py` — 층 캔버스 기본값·크기 상한과 좌표 반올림
  (`rounded_to_canvas`)의 한 곳이다(`space_layout_edit`·`fab_layout` 이 import 한다 — 거꾸로 두면 순환).
- `src/capa_simulation/services/display_order_editor.py`, `display_order_csv.py` — 웹 편집 표시순서 규칙의 검증·범위
  교체·CSV 직렬화다. 분류값 중복은 `match_key` 로 본다(8장). 공용 프로필 교체는 현재본만 남긴다 — 이전 규칙을
  보존하지 않으므로 교체 전에 CSV 를 내려받아 두는 것이 유일한 되돌리기다.
