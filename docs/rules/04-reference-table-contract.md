# AGENTS 4장 — 기준정보 테이블 계약

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

`RQ_PKG_PLAN` 업무 키는 계약 `derived_keys` 의 9키다 — 계획 줄 8키(CUSTOM 포함)에 `Pack Code` 가 더해진다.
`Pack Code` 는 같은 8키 안에서 생산수량을 가르는 값이라 **저장과 편집은 행을 나누고, 합산은 계산 계층이**
한다. 부하량·소요대수·HOME 은 Pack Code 없는 키로 `groupby` 하고, PKG 환산은
`_prepare_pkg_plan_for_equivalent` 가 8키 합계로 접는다. 변환기나 `validated_distinct` 에서
합산하지 않는다 — 거기서 접으면 편집 왕복에서 Pack Code 별 수량을 되살릴 수 없다.
표준 목표 계획과 소요대수 상세를 잇는 키 `standard_target_capacity.PKG_PLAN_KEYS` 에는 Pack Code 를 넣지 않는다 — 연결 상대인 원수요 키 `DEMAND_ID_COLUMNS` 에 그 칸이 없어 넣으면 `KeyError` 다. 표준 목표 화면 집계 차원에도 Pack Code 를 넣지 않는다.

**`CUSTOM` 은 제품을 가르는 업무 키다**(사용자 결정 「CUSTOM 이 다르면 다른 제품」 — 시뮬레이션 `0039`). 제품정보가 든
8표(`RQ_PKG_PLAN` · `RQ_YLD` · `RQ_CHIP_QTY` · `RQ_CHIP_EQ` · `RQ_UPEH` · `RQ_LOT_RATIO` · `RQ_WF_RATIO` · `RQ_REQB`)의
`derived_keys` 끝에 있고 표 칸도 끝이다(DDL 차례). Pack Code 와 달리 **합산하지 않고 조인 키로 끝까지 간다** — 수율 ·
Chip 구성 · UPEH · 측정률 · 경로가 부품(CUSTOM 값)마다 붙고 대당 Capa · 소요대수도 부품마다 난다. 계산 키 상수는
Stack 뒤에 둔다(3장 각 모듈). 빈 값은 표지 `"-"`(`core_data_derivation.CUSTOM_BLANK`) 하나이고, 0039 전에 저장한
리비전 · 데이터셋 표는 모두 표지다(원천에서 되채우지 않음). 한 키라도 빠뜨리면 두 부품이 말없이 한 줄로 접히거나 부하가
두 배가 되므로, 키를 손으로 적은 조인을 두지 않고 상수에서 낸다(12장 「새 업무 키」). 합쳐 보는 화면(HOME 도넛 · 제품별
비중 · HOME 상세 · 공정 Capa 상세 「제품별 소요대수」 · 제약 시뮬레이션)은 부품이 둘 이상인 제품만 부품마다 가르고 부품이
하나뿐인 제품은 제품으로 합친다(`services/product_parts.py` 한 벌 — 8장 「합쳐 보는 화면의 부품 이름표」). 산출 결과 소요대수 「상세」 표와
그 제외 목록은 대당 Capa STEP별 표처럼 부품마다 한 줄이다(`required_equipment.RESULT_DIMENSIONS` — 공정 합은 같다).
이미 등록한 원천 코드는 보관본까지 다시 받지 않으므로 부품마다 갈린 수율 · UPEH 는 0039 뒤 새로 등록한(또는 자동 갱신이 받은) 리비전부터 숫자에 들고, 그 값을 쓰려면 그 리비전을 공식 · HOME 주요 Case 로 다시 지정한다(옛 코드를 지우고 다시 등록하는 길은 최신 공식이면 지울 수 없고 이력 · HOME 지정도 함께 사라진다).

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

**부대공정 판은 같은 표에 행으로 든다.** BDQ 에 없는 공정은 양식 ZIP(`services/extra_process_pack.py`)으로 받아 등록
이음매에서 `RQ_REQB` · `RQ_UPEH` · 측정률 둘 · `RQ_RUN_RATE` · `RQ_VITAL` · `RQ_RUN_DAY` · `RQ_EQP_*` 셋 · `RQ_MODULE` 에 BDQ 와 같은 칸 ·
형식으로 덧붙인다(6장 「부대공정」). 원천(`raw_data`)과 계획 · 수율 · Chip 표는 그대로라 부대공정은 계획에 이미 있는 제품에만
걸린다. 모듈수는 데이터셋 표라 앱에서 고치지 않는다 — 판을 고쳐 다시 얹는다.

나머지 테이블을 웹에서 수정할 필요가 생기면 단순히 session state에 별도 복사하지 말고 활성
시나리오의 editable table 계약과 저장 정책을 함께 변경한다.
