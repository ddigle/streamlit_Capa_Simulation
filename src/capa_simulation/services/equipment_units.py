# Purpose: 모듈 행을 설비 한 대로 묶는 설비키·설비지분과 소수 대수 표기를 정한다.

"""**행이 아니라 설비를 센다.**

모듈로 관리하는 공정(CoW Bonder 등)은 설비 한 대를 모듈마다 한 행으로 적는다 — 모듈마다
입고·Qual·반출 일정과 비가동이 따로 있기 때문이다(APW01 → APW01A·B·C·D). 같은 설비의 행은
`Main 설비` 에 설비 ID 를 똑같이 적어 묶는다. 비모듈 공정은 Main 설비를 비워 두고, 행 하나가
설비 한 대다.

그래서 숫자가 두 축으로 갈린다.

- **대수 축** — 「몇 대인가」. 행마다 `설비지분` 을 곱해 더한다. 설비 한 대의 행은 어느
  시점에든 지분을 합쳐 정확히 1 이다. 비모듈 행은 지분이 1 이라 지금까지와 같다.
- **능력 축** — 「몇 대 몫을 하나」. 행마다 `환산비` 를 곱해 더한다(모듈 행은 보통 0.25).

**지분은 시점마다 다시 매긴다**(`held_unit_shares`). 그 시점에 보유 중인 모듈 수로 1 을
나누고, 보유하지 않은 모듈(입고 전·반출 후)은 형제가 남아 있는 동안 0 이다. 형제가 하나도
보유 중이 아니면 행 수로 나눈다 — 입고 전 설비도 「입고 예정 1대」로 잡혀야 한다. 이렇게 하면
모듈을 영구히 떼어 반출해도 남은 모듈이 1대를 채우고, 모듈을 나중에 더해도 과거 달이 바뀌지
않는다. 모듈 하나가 PM 이면 가용 0.75, 비가동 0.25 가 된다.

Qual 계획처럼 보유와 상관없는 표는 고정 지분(`static_unit_shares`, 1 ÷ 행 수)을 쓴다.
"""

from __future__ import annotations

import pandas as pd

from capa_simulation.services.equipment_contract import (
    CONVERSION_RATIO_COLUMN,
    EQUIPMENT_ID_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
)

# 설비 한 대로 묶는 키와 그 시점의 몫. 상태 판정·생애주기 구간이 이 이름으로 붙인다.
UNIT_KEY_COLUMN = "설비키"
UNIT_SHARE_COLUMN = "설비지분"

# 대수 축 합계의 반올림 자리. 1/3 지분 셋을 더하면 0.9999999999 가 된다.
UNIT_COUNT_DECIMALS = 6


def unit_keys(equipment: pd.DataFrame) -> pd.Series:
    """행마다 설비키. Main 설비가 있으면 Main 설비, 없으면 호기 자신이다."""
    units = equipment[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    if PARENT_EQUIPMENT_COLUMN not in equipment.columns:
        return units
    parents = equipment[PARENT_EQUIPMENT_COLUMN].astype("string").str.strip()
    return parents.where(parents.notna() & parents.ne(""), units)


def static_unit_shares(keys: pd.Series) -> pd.Series:
    """1 ÷ 같은 설비키의 행 수. 보유 여부와 상관없는 표에 쓴다."""
    if keys.empty:
        return pd.Series(dtype="float64", index=keys.index)
    return 1.0 / keys.map(keys.value_counts()).astype("float64")


def held_unit_shares(keys: pd.Series, held: pd.Series) -> pd.Series:
    """그 시점의 설비지분. 보유 중인 형제 수로 1 을 나눈다.

    보유 중인 형제가 없으면 행 수로 나눈다 — 입고 전이거나 모두 반출된 설비도 합쳐 1대다.
    """
    if keys.empty:
        return pd.Series(dtype="float64", index=keys.index)
    held_flags = held.fillna(False).astype("bool")
    held_count = held_flags.groupby(keys).transform("sum").astype("float64")
    group_size = keys.map(keys.value_counts()).astype("float64")
    by_held = held_flags.astype("float64") / held_count.where(held_count > 0)
    return by_held.where(held_count > 0, 1.0 / group_size).astype("float64")


def unit_total(values: pd.Series) -> float:
    """대수 축 합계. 부동소수 끝자리를 버린다(1/3 × 3 = 1)."""
    return round(float(values.sum()), UNIT_COUNT_DECIMALS)


def format_unit_count(value: float) -> str:
    """정수면 정수로, 아니면 소수 둘째 자리까지(끝의 0 은 뗀다). 0.25 → "0.25", 3.0 → "3".

    `+ 0.0` 은 음수 0 을 지운다. 지분 합끼리 빼면 -0.0 이 나올 수 있고, 그대로 두면 「-0대」다.
    """
    rounded = round(float(value), 2) + 0.0
    if rounded.is_integer():
        return f"{rounded:,.0f}"
    return f"{rounded:,.2f}".rstrip("0").rstrip(".")


def placed_unit_rows(equipment: pd.DataFrame, placed: pd.DataFrame) -> pd.DataFrame:
    """배치된 설비의 **모든 행**. 그리는 행(`placed`)과 세는 행을 가른다.

    모듈 설비는 도면에 상자 하나로 그리므로 좌표는 모듈 한 행에만 있는 것이 자연스럽다.
    행마다 걸러 세면 그 설비가 0.25대로 잡힌다. 그래서 배치 여부는 설비 단위로 정한다 —
    한 모듈이라도 배치되면 그 설비의 행을 모두 센다. 모듈끼리는 동·층이 같도록 검증하므로
    다른 동·층으로 새지 않는다.
    """
    if UNIT_KEY_COLUMN not in equipment.columns or UNIT_KEY_COLUMN not in placed.columns:
        return placed
    return equipment.loc[equipment[UNIT_KEY_COLUMN].isin(placed[UNIT_KEY_COLUMN])]


def unit_transitions(events: pd.DataFrame) -> pd.DataFrame:
    """전환 일정을 **설비 전환 한 건씩**으로 접는다.

    모듈 행 넷이 같은 날 같은 단계로 넘어가면 설비 한 대의 전환 한 건이다. 날짜가 다르면
    따로 센다. 확정상태는 모듈 행마다 다를 수 있어, 남긴 첫 행 값을 쓰면 정렬 순서가 답을
    정한다. 그래서 `Qual확정` 은 그 전환의 모듈 하나라도 확정·완료면 참이다 — 확정상태
    필터로 거른 결과와 같은 답이다.
    """
    keys = [UNIT_KEY_COLUMN, "전환단계", "전환일"]
    confirmed = (
        events.assign(_ok=events["확정상태"].isin(["확정", "완료"]))
        .groupby(keys, observed=True, dropna=False)["_ok"]
        .transform("any")
    )
    return events.assign(Qual확정=confirmed.astype(bool)).drop_duplicates(keys)


def module_group_warnings(equipment: pd.DataFrame) -> list[str]:
    """저장은 막지 않지만 알릴 것. 검증을 통과한 호기 마스터를 받는다.

    모듈 행 여럿을 묶었는데 환산비가 모두 1 이면 능력 축이 모듈 수만큼 부풀려진다(4모듈이면
    4대 몫). 모듈 행에는 보통 1 ÷ 모듈수(0.25)를 적는다.
    """
    if equipment.empty or PARENT_EQUIPMENT_COLUMN not in equipment.columns:
        return []
    keys = unit_keys(equipment)
    grouped = equipment.assign(_key=keys).loc[keys.map(keys.value_counts()).gt(1)]
    if grouped.empty:
        return []
    ratios = pd.to_numeric(grouped[CONVERSION_RATIO_COLUMN], errors="coerce").fillna(1.0)
    all_one = ratios.eq(1.0).groupby(grouped["_key"]).all()
    suspicious = sorted(str(key) for key, flag in all_one.items() if flag)
    if not suspicious:
        return []
    return [
        "Main 설비로 묶은 모듈 행의 환산비가 모두 1 입니다 — 능력이 모듈 수만큼 부풀려집니다. "
        f"모듈 행에는 1 ÷ 모듈수(4모듈이면 0.25)를 적습니다: {suspicious[:5]}"
    ]
