# Purpose: 모듈 행을 설비 한 대로 묶는 설비키·설비지분·묶음 판정·같이 쓰기 계획을 정한다.

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

**모듈 묶음**(Main 설비가 같은 행이 표 전체에서 둘 이상 — `module_group_rows`)의 판정과, 묶음 한
줄을 고칠 때 형제 줄이 같이 바뀌는 계획(`plan_group_writes`)도 여기 둔다. 계약만 import 하는 가장
낮은 층이라 표(`equipment_grid`)·Space 편집기(`space_layout_edit`)·검증이 고리 없이 부른다.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from capa_simulation.services.equipment_contract import (
    CONVERSION_RATIO_COLUMN,
    EQUIPMENT_ID_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_STATUS_COLUMN,
    UNIT_SHARED_COLUMNS,
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
    따로 센다. Qual상태는 모듈 행마다 다를 수 있어, 남긴 첫 행 값을 쓰면 정렬 순서가 답을
    정한다. 그래서 `Qual확정` 은 그 전환의 모듈 하나라도 확정·완료면 참이다 — Qual상태
    필터로 거른 결과와 같은 답이다.
    """
    keys = [UNIT_KEY_COLUMN, "전환단계", "전환일"]
    confirmed = (
        events.assign(_ok=events[QUAL_STATUS_COLUMN].isin(["확정", "완료"]))
        .groupby(keys, observed=True, dropna=False)["_ok"]
        .transform("any")
    )
    return events.assign(Qual확정=confirmed.astype(bool)).drop_duplicates(keys)


# 모듈 묶음 환산비 경고의 칸 문구. 문장 경고(`module_group_warnings`)와 칸 단위 결과
# (`equipment_validation.equipment_master_issues` 의 `module_ratio_default`)가 함께 쓴다.
MODULE_RATIO_WARNING = (
    "Main 설비로 묶은 모듈 행의 환산비가 모두 1 입니다 — 능력이 모듈 수만큼 부풀려집니다"
)


def module_ratio_warning_rows(equipment: pd.DataFrame) -> pd.Series:
    """환산비가 모두 1 인 모듈 묶음(같은 Main 설비를 적은 줄 둘 이상)의 줄 — `equipment` 와 같은
    색인의 참거짓.

    저장은 막지 않는 경고다. 모듈 행 여럿을 묶었는데 환산비가 모두 1 이면 능력 축이 모듈 수만큼
    부풀려진다(4모듈이면 4대 몫). 모듈 행에는 보통 1 ÷ 모듈수(0.25)를 적는다.

    검증 전 편집본도 받는다 — 화면은 막는 오류가 남은 편집본으로도 경고 문장을 세우고, 칸 단위
    결과(`equipment_validation` 의 `module_ratio_default`)도 막는 결과와 함께 낸다. 그래서 **Main
    설비를 적은 줄만** 묶음으로 센다 — 설비명이 겹친 줄(막는 규칙 「설비명 중복」 의 몫)은 묶음이
    아니고, 검증을 통과한 표에서는 묶음 줄이 모두 Main 설비를 적은 줄이라 결과가 같다. 설비명이 빈
    줄은 저장이 조용히 빼므로 세지 않는다. 못 읽은 환산비는 빈 칸처럼 1 로 본다.
    """
    none = pd.Series(False, index=equipment.index, dtype=bool)
    if equipment.empty or PARENT_EQUIPMENT_COLUMN not in equipment.columns:
        return none
    units = equipment[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    parents = equipment[PARENT_EQUIPMENT_COLUMN].astype("string").str.strip()
    modules = units.notna() & units.ne("") & parents.notna() & parents.ne("")
    keys = parents.where(modules.fillna(False).to_numpy(dtype=bool))
    grouped = keys.map(keys.value_counts()).gt(1).fillna(False).astype(bool)
    if not grouped.any():
        return none
    ratios = pd.to_numeric(equipment.loc[grouped, CONVERSION_RATIO_COLUMN], errors="coerce")
    all_one = ratios.fillna(1.0).eq(1.0).groupby(keys.loc[grouped]).all()
    suspicious = all_one.index[all_one.to_numpy(dtype=bool)]
    return grouped & keys.isin(suspicious).fillna(False).astype(bool)


def module_group_warnings(equipment: pd.DataFrame) -> list[str]:
    """저장은 막지 않지만 알릴 것 — `module_ratio_warning_rows` 의 묶음을 한 문장으로(검증 전
    편집본도 받는다)."""
    rows = module_ratio_warning_rows(equipment)
    if not rows.any():
        return []
    suspicious = sorted({str(key) for key in unit_keys(equipment).loc[rows]})
    return [
        f"{MODULE_RATIO_WARNING}. 모듈 행에는 1 ÷ 모듈수(4모듈이면 0.25)를 적습니다: "
        f"{suspicious[:5]}"
    ]


# ------------------------------------------------------------------ 모듈 묶음


def parent_equipment(frame: pd.DataFrame) -> pd.Series:
    """행마다 Main 설비(앞뒤 공백 제거, 비면 NA). 선택 컬럼이라 없는 표도 받는다."""
    if PARENT_EQUIPMENT_COLUMN not in frame.columns:
        return pd.Series(pd.NA, index=frame.index, dtype="string")
    parents = frame[PARENT_EQUIPMENT_COLUMN].astype("string").str.strip()
    return parents.where(parents.ne(""))


def module_group_rows(master: pd.DataFrame) -> pd.Series:
    """행마다 그 행이 든 Main 설비 모듈 묶음(Main 설비가 같은 행이 표 전체에서 둘 이상)의 Main 설비,
    묶음 밖이면 NA. 모듈 묶음 판정의 한 곳이다 — 저장 전 바둑판 검사(`space_layout_edit.
    module_layout_violations`), 가정 설비 시나리오 배치 차이의 묶음 통째 규칙(`services/
    layout_overlay.py`), 묶음 같이 쓰기 계획(`plan_group_writes`)이 같이 쓴다."""
    parents = parent_equipment(master)
    return parents.where(parents.map(parents.value_counts()).fillna(0).ge(2).astype(bool))


@dataclass(frozen=True)
class GroupWrite:
    """같이 쓸 칸 하나 — 묶음 하나 · 칸 하나 · 값 하나.

    - `group` — 형제까지 퍼지는 쓰기면 그 Main 설비, 그 줄 하나만 쓰면 None(같이 바뀌는 칸이 아님 ·
      묶음 밖 줄 · 한 번에 같은 묶음 같은 칸에 다른 값이 와 갈린 것 — `GroupPlan.split`).
    - `value` — 호출부가 `equipment_validation.coerce_master_cell` 로 다듬은 값 그대로다.
    - `rows` — 쓸 줄 자리(넘긴 표의 `iloc`, 표 차례). 고친 줄과 형제 모두다.
    - `asked` — 사용자가 직접 고친 줄 자리(넘긴 차례, 겹친 것 뺌). 나머지 `rows` 가 같이 바뀌는
      형제다.
    """

    group: str | None
    column: str
    value: object
    rows: tuple[int, ...]
    asked: tuple[int, ...]


@dataclass(frozen=True)
class GroupPlan:
    """`plan_group_writes` 의 결과 — 쓰기(처음 나온 차례)와, 한 번에 같은 (묶음, 칸)에 서로 다른
    값이 와 같이 바꾸지 않은 (Main 설비, 칸) 목록(처음 나온 차례)."""

    writes: tuple[GroupWrite, ...]
    split: tuple[tuple[str, str], ...]


def plan_group_writes(master: pd.DataFrame, cells: Sequence[tuple[int, str, object]]) -> GroupPlan:
    """고친 칸 `(줄 자리, 칸, 값)` 들을 모듈 묶음 같이 쓰기 계획으로 편다(2026-11-12 사용자 답 3-1 ·
    3-3 · 3-5).

    - 칸이 `UNIT_SHARED_COLUMNS` 이고 그 줄이 모듈 묶음(`module_group_rows` — 둘 이상)이면 묶음 모든
      줄에 쓴다. 형제는 **넘긴 표 전체**에서 찾는다 — 표에 불러오지 않은 줄 · 다른 층 · 숨은 모듈도
      든다. 묶음은 고치기 전 `master` 로 가른다.
    - 그 밖(같이 바뀌지 않는 칸 — Main 설비 · 사용기준 · 일정 등, 묶음 밖 줄, 한 줄 묶음)은 그 줄
      하나만이다(`group` None).
    - 같은 (묶음, 칸)에 온 값이 모두 같으면 쓰기 하나다. 서로 다르면 같이 바꾸지 않고 받은 칸만
      그 줄 하나씩 쓰며 `split` 에 적는다 — 어느 값이 맞는지 고르지 않는다.
    - 값 견줌은 결측 · 빈 글을 같은 빈 값으로, 나머지는 글자로 본다.

    **잠금은 보지 않고 값을 다듬지 않는다.** 잠금은 길마다 다르다(표는 칸 잠금, Space 창은 창
    잠금) — 호출부가 `rows` 가운데 하나라도 잠겼으면 그 쓰기를 통째로 거절한다. 값은 호출부가
    다듬어 넘긴다(검증이 이 파일을 import 하므로 거꾸로 부르면 고리다). 줄 자리가 표 밖이면
    `IndexError` 다.
    """
    groups = module_group_rows(master).tolist() if len(master) else []
    members: dict[str, list[int]] = {}
    for position, name in enumerate(groups):
        if isinstance(name, str):
            members.setdefault(name, []).append(position)
    slots: list[tuple[str, str] | int] = []
    buckets: dict[tuple[str, str], list[int]] = {}
    for index, (position, column, _value) in enumerate(cells):
        name = groups[position]
        if column in UNIT_SHARED_COLUMNS and isinstance(name, str):
            key = (name, column)
            if key not in buckets:
                buckets[key] = []
                slots.append(key)
            buckets[key].append(index)
        else:
            slots.append(index)
    writes: list[GroupWrite] = []
    split: list[tuple[str, str]] = []
    for slot in slots:
        if isinstance(slot, int):
            writes.append(_single_write(cells[slot]))
            continue
        picked = [cells[index] for index in buckets[slot]]
        if len({_value_key(value) for _, _, value in picked}) > 1:
            split.append(slot)
            writes.extend(_single_write(cell) for cell in picked)
            continue
        name, column = slot
        writes.append(
            GroupWrite(
                group=name,
                column=column,
                value=picked[0][2],
                rows=tuple(members[name]),
                asked=tuple(dict.fromkeys(position for position, _, _ in picked)),
            )
        )
    return GroupPlan(writes=tuple(writes), split=tuple(split))


def _single_write(cell: tuple[int, str, object]) -> GroupWrite:
    position, column, value = cell
    return GroupWrite(group=None, column=column, value=value, rows=(position,), asked=(position,))


def _value_key(value: object) -> str:
    """같이 쓸 값의 견줌 열쇠 — 결측(None · NA · NaT · NaN)은 빈 글, 나머지는 글자."""
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)
