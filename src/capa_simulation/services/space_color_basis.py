# Purpose: Space 도면 「색 기준」(공정구분·투자Capa·필요 단축)의 그룹을 정하고 호기의 그룹을 고른다.

"""Space 층 도면의 색 기준(2026-10-16 사용자 결정 — 질문 7·8 권장안).

색 기준은 하나만 고른다 — **공정구분**(물류·FRONT·PKG·MI·TEST·FDY 여섯) 또는 **투자Capa**(숫자
차례의 청록 7단). 고른 기준의 그룹마다 체크를 두고, 체크한 그룹의 호기만 그 그룹 색으로 칠한다.
그룹이 없거나 체크를 끈 호기는 기본 회색이다. 색 값은 화면
몫(`components/space_layout`·`design/tokens`)이고 여기는 **어느 호기가 어느 그룹인가**만 정한다.

- 공정구분은 `equipment_contract.line_type_group` 이다 — 앞뒤 공백·대소문자를 무시한 완전 일치이고
  목록 밖·빈 칸은 그룹이 없다. 「MI」는 Area Code 에도 있지만 공정구분만 본다.
- 투자Capa 는 자유 글이라 **숫자로 읽히는 값만** 그룹이 된다(`322K`·`322 k`·`322,000`·`1.5M` — K
  는 천, M 은 백만). 숫자로 못 읽는 값과 빈 칸은 기본 회색이다. 같은 수로 읽히는 글자는 한
  그룹이고 이름은 가장 많이 쓴 글자다. 종류가 7을 넘으면 작은 수부터 차례로 7구간에 고르게 나눠
  묶는다(「280K~319K」). 단(청록 7단의 칸)은 **숫자 차례**다 — 가장 작은 그룹이 가장 옅은 1단이고
  하나씩 짙어진다(시안 `capaLevel` 과 같다). 그룹이 7보다 적으면 짙은 단 쪽이 남는다.
- **필요 단축**(셋째 값, 2026-10-24 사용자 결정)은 그룹이 없다 — 체크 칸이 비고 모든 호기의 그룹이
  결측이다. 색은 필요 단축 일정 계획의 단축 일수 구간(`services/space_shortening_layer`)이 정한다.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd

from capa_simulation.services.equipment_contract import (
    INVESTMENT_CAPA_COLUMN,
    LINE_TYPE_COLUMN,
    LINE_TYPE_GROUPS,
    line_type_group,
)

# 화면의 「색 기준」 세 값. 라디오가 이 글자를 보이고 그대로 값으로 쓴다. 셋째 값의 글자는
# `navigation.SPACE_SHORTENING_BASIS` 와 같다(사이드바가 그 값일 때만 시나리오·조회기간 줄을 세운다
# — 시험이 두 글자를 묶는다).
COLOR_BASIS_LINE_TYPE: Final = LINE_TYPE_COLUMN
COLOR_BASIS_CAPA: Final = INVESTMENT_CAPA_COLUMN
COLOR_BASIS_SHORTENING: Final = "필요 단축"
COLOR_BASES: Final = (COLOR_BASIS_LINE_TYPE, COLOR_BASIS_CAPA, COLOR_BASIS_SHORTENING)
# 투자Capa 단의 수(청록 7단). 그룹이 이보다 많으면 구간으로 묶는다.
CAPA_LEVELS: Final = 7

_CAPA_NUMBER = re.compile(r"^([0-9][0-9,]*(?:\.[0-9]+)?)\s*([KkMm]?)$")
_CAPA_UNITS: Final = {"": 1.0, "k": 1_000.0, "m": 1_000_000.0}


@dataclass(frozen=True)
class CapaGroup:
    """투자Capa 그룹 하나.

    `low`~`high` 는 그 그룹에 드는 수(양 끝 포함), `level` 은 청록 단(0~6, 그룹 차례)이다.
    """

    label: str
    low: float
    high: float
    level: int


def capa_number(value: object) -> float | None:
    """투자Capa 글자 하나를 수로 읽는다(`322K` → 322000). 못 읽으면 None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    match = _CAPA_NUMBER.match(str(value).strip())
    if match is None:
        return None
    return float(match.group(1).replace(",", "")) * _CAPA_UNITS[match.group(2).casefold()]


def capa_numbers(values: pd.Series) -> pd.Series:
    """행마다 투자Capa 의 수(float). 못 읽는 값·빈 칸은 결측이다."""
    return pd.Series([capa_number(value) for value in values], index=values.index, dtype="float64")


def capa_groups(values: pd.Series) -> tuple[CapaGroup, ...]:
    """설비 마스터의 투자Capa 값에서 그룹을 만든다(작은 수부터).

    같은 수로 읽히는 글자는 한 그룹이고, 이름은 가장 많이 쓴 글자(같으면 글자 차례로 앞)다. 종류가
    `CAPA_LEVELS` 를 넘으면 작은 수부터 차례로 그만큼의 구간에 고르게 나눠 「앞 이름~뒤 이름」으로
    묶는다. 단(`level`)은 그룹 차례 그대로(0 이 가장 옅은 단)다.
    """
    texts = values.astype("string").str.strip()
    numbers = capa_numbers(values)
    readable = numbers.notna()
    if not readable.any():
        return ()
    frame = pd.DataFrame({"text": texts[readable], "number": numbers[readable]})
    names: dict[float, str] = {}
    for number in sorted(set(frame["number"].tolist())):
        counts = frame.loc[frame["number"].eq(number), "text"].value_counts()
        top = counts.loc[counts.eq(counts.max())].index
        names[float(number)] = str(sorted(str(name) for name in top)[0])
    distinct = sorted(names)
    if len(distinct) <= CAPA_LEVELS:
        chunks = [[number] for number in distinct]
    else:
        size, extra = divmod(len(distinct), CAPA_LEVELS)
        chunks, start = [], 0
        for index in range(CAPA_LEVELS):
            stop = start + size + (1 if index < extra else 0)
            chunks.append(distinct[start:stop])
            start = stop
    return tuple(
        CapaGroup(
            label=names[chunk[0]] if len(chunk) == 1 else f"{names[chunk[0]]}~{names[chunk[-1]]}",
            low=chunk[0],
            high=chunk[-1],
            level=level,
        )
        for level, chunk in enumerate(chunks)
    )


def capa_group_of(values: pd.Series, groups: Sequence[CapaGroup]) -> pd.Series:
    """행마다 투자Capa 그룹 이름. 숫자로 못 읽거나 어느 그룹에도 들지 않으면 결측이다."""
    numbers = capa_numbers(values)
    result = pd.Series(pd.NA, index=values.index, dtype="string")
    for group in groups:
        inside = numbers.ge(group.low) & numbers.le(group.high)
        result = result.mask(inside.fillna(False).astype(bool), group.label)
    return result


def color_basis_groups(basis: str, capa: Sequence[CapaGroup]) -> tuple[str, ...]:
    """그 기준의 그룹 이름(체크박스 차례). 필요 단축은 그룹이 없다."""
    if basis == COLOR_BASIS_CAPA:
        return tuple(group.label for group in capa)
    if basis == COLOR_BASIS_SHORTENING:
        return ()
    return LINE_TYPE_GROUPS


def color_groups(equipment: pd.DataFrame, basis: str, capa: Sequence[CapaGroup]) -> pd.Series:
    """행마다 그 기준의 그룹 이름(없으면 결측). 칸이 없는 표와 필요 단축 기준은 모두 결측이다."""
    if basis == COLOR_BASIS_SHORTENING:
        return pd.Series(pd.NA, index=equipment.index, dtype="string")
    column = COLOR_BASIS_CAPA if basis == COLOR_BASIS_CAPA else COLOR_BASIS_LINE_TYPE
    if column not in equipment.columns:
        return pd.Series(pd.NA, index=equipment.index, dtype="string")
    if basis == COLOR_BASIS_CAPA:
        return capa_group_of(equipment[column], capa)
    return line_type_group(equipment[column])
