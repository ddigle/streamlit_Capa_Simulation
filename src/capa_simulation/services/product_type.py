# Purpose: 제품타입(HBM·EDP-TSV)별 WF 구분 규칙과 원천 값의 표시 구분 변환을 한 곳에 둔다.

"""제품타입이 가르는 규칙을 한 곳에 모은다.

두 제품군은 `WF 구분` 값 집합이 다르다.

| 제품타입 | 원천 `WF 구분` | 앱이 쓰는 `WF 구분` |
|---|---|---|
| HBM | Buffer, Core, Top, Dummy | 그대로 |
| EDP-TSV | Top, Master, Slave | **Top → `Top_e`**, 나머지 그대로 |

**`Top` 이 두 제품군에 같은 이름으로 존재하는 것이 문제였다.** `WF 구분` 만 보고 쓴 규칙은
의도와 무관하게 양쪽에 다 걸리고, 화면에서도 서로 다른 두 가지가 한 이름으로 섞여 보인다.
그래서 EDP-TSV 의 `Top` 을 앱 안에서 `Top_e` 로 갈라 부른다.

**입력은 그대로 받는다.** Capa 기준정보 DB·실적 DB 어디에도 `Top_e` 라는 값은 없다.
변환은 `core_data_derivation.build_q_core_data` **한 곳**에서만 일어난다 — 원천 78컬럼이
작업 프레임이 되는 경계다. 거기서 한 번 바꾸면 16개 RQ 표, 부하량, 소요대수, 확보율, 화면이
전부 같은 값을 보게 되어 조인이 어긋날 자리가 없다. `raw_data.core_data` 에 보존되는 원천
스냅샷은 손대지 않으므로 언제든 다시 파생할 수 있다.
"""

from __future__ import annotations

import pandas as pd

PRODUCT_TYPE_COLUMN = "제품타입"
WF_DIVISION_COLUMN = "WF 구분"

HBM_PRODUCT_TYPE = "HBM"
EDP_PRODUCT_TYPE = "EDP-TSV"

# 원천이 싣는 이름과 앱이 EDP-TSV 에 쓰는 이름.
SOURCE_TOP_DIVISION = "Top"
EDP_TOP_DIVISION = "Top_e"

# 제품타입별 `WF 구분` 값 집합 (2026-09-05 확인). **두 목록은 일부러 따로 적는다.**
# 한쪽을 고칠 때 다른 쪽이 따라 움직이면 안 되므로 공통 부분을 뽑아 공유하지 않는다.
HBM_WF_DIVISIONS = ("Buffer", "Core", "Top", "Dummy")
EDP_WF_DIVISIONS = ("Top_e", "Master", "Slave")
WF_DIVISIONS_BY_PRODUCT_TYPE = {
    HBM_PRODUCT_TYPE: HBM_WF_DIVISIONS,
    EDP_PRODUCT_TYPE: EDP_WF_DIVISIONS,
}

# Dummy 산식을 받는 `WF 구분`. EDP-TSV 에는 Dummy 가 없다.
DUMMY_DIVISIONS_BY_PRODUCT_TYPE = {
    HBM_PRODUCT_TYPE: ("Dummy",),
    EDP_PRODUCT_TYPE: (),
}


def apply_edp_wf_division(core: pd.DataFrame) -> pd.DataFrame:
    """EDP-TSV 행의 `WF 구분` `Top` 을 `Top_e` 로 바꾼다.

    제자리에서 고치고 같은 프레임을 돌려준다 — 파생 경계에서 한 번만 불리므로 사본을 더
    만들 이유가 없다. `제품타입` 이 없는 프레임은 판단 근거가 없으므로 그대로 둔다.
    """
    if PRODUCT_TYPE_COLUMN not in core.columns or WF_DIVISION_COLUMN not in core.columns:
        return core
    product_type = core[PRODUCT_TYPE_COLUMN].astype("string").str.strip()
    division = core[WF_DIVISION_COLUMN].astype("string").str.strip()
    target = product_type.eq(EDP_PRODUCT_TYPE) & division.eq(SOURCE_TOP_DIVISION)
    core[WF_DIVISION_COLUMN] = division
    core.loc[target.fillna(False), WF_DIVISION_COLUMN] = EDP_TOP_DIVISION
    return core


def product_type_of(frame: pd.DataFrame) -> pd.Series:
    """제품군을 정규화해 돌려준다. 판정을 한 곳에 모아 분기가 갈라지지 않게 한다."""
    return frame[PRODUCT_TYPE_COLUMN].astype("string").str.strip()
