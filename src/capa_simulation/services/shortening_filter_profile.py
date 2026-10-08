# Purpose: 필요단축일정 공용 조회 조건(기간·공정) 프로필의 모델·값 검증·심기·합치기 규칙을 둔다.

"""필요단축일정 탭의 공용 조회 조건 프로필(2026-10-08 사용자 요청).

저장은 설비 DB 의 `equipment_ops.shortening_filter_profile`·`shortening_filter_process`(0019)이고
SQL 은 `persistence/equipment_repository.py` 가 갖는다. 이 모듈은 Streamlit·DB 를 모르는 규칙만
둔다.

- **심기** — 세션에 값이 없을 때만 프로필로 심는다. 지금 고를 수 있는 달·공정 안의 값만 쓰고, 달이
  밖이면 코드 기본값, 공정은 밖의 것만 빼고 심는다(프로필에서 지우지는 않는다).
- **합치기** — 사용자가 공정을 바꾸면 고른 공정에 **지금 고를 수 없어 화면에 없던** 저장 공정을
  뒤에 붙여 남긴다. 다른 시나리오·호기 마스터에서는 그 공정이 있고, 보이지 않는 값을 지우면 그
  화면의 공용 조건이 말없이 바뀐다. 다만 고른 것을 모두 비우면(「미선택 = 목표 미달 공정 전체」)
  빈 목록이다 — 남은 공정만 저장하면 「전체」를 고른 사람의 뜻이 「그 공정만」으로 뒤집힌다.

값은 원본 공정명이다. 공정 표시명(Proc Rename)은 화면 라벨일 뿐이라 여기에 닿지 않는다.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "ShorteningFilterProfile",
    "absent_filter_processes",
    "merge_filter_processes",
    "normalize_filter_month",
    "normalize_filter_processes",
    "seeded_filter_month",
]


@dataclass(frozen=True)
class ShorteningFilterProfile:
    """공용 조회 조건 한 벌. `version` 0 은 한 번도 저장하지 않은 것이다.

    달은 둘 다 있거나 둘 다 없다(`None` = 기간을 저장하지 않음 → 코드 기본값). 공정이 비면
    「미선택 = 목표 미달 공정 전체」다.
    """

    start_month: int | None = None
    end_month: int | None = None
    processes: tuple[str, ...] = ()
    version: int = 0
    source: str = ""
    updated_at: datetime | None = None


def normalize_filter_month(value: object) -> int:
    """`YYYYMM` 정수로 맞춘다. 달이 1~12 가 아니거나 정수가 아니면 `ValueError`."""
    try:
        number = int(str(value).strip())
    except ValueError:
        raise ValueError(f"조회 월은 YYYYMM 정수여야 합니다: {value!r}") from None
    if isinstance(value, bool) or not 100_001 <= number <= 999_912 or not 1 <= number % 100 <= 12:
        raise ValueError(f"조회 월은 YYYYMM 정수여야 합니다: {value!r}")
    return number


def normalize_filter_processes(values: Iterable[object]) -> tuple[str, ...]:
    """앞뒤 공백을 걷고 빈 값·중복을 뺀다. 처음 나온 차례를 지킨다."""
    seen: dict[str, None] = {}
    for value in values:
        text = "" if value is None else str(value).strip()
        if text:
            seen.setdefault(text, None)
    return tuple(seen)


def seeded_filter_month(stored: int | None, options: Sequence[int], fallback: int) -> int:
    """심을 달. 저장된 달이 지금 고를 수 있는 달이면 그것, 아니면 코드 기본값이다."""
    return stored if stored is not None and stored in options else fallback


def absent_filter_processes(stored: Sequence[str], visible: Collection[str]) -> list[str]:
    """프로필에 있으나 지금 고를 수 없는 공정. 저장된 차례 그대로다."""
    return [process for process in stored if process not in visible]


def merge_filter_processes(
    stored: Sequence[str], selected: Iterable[object], visible: Collection[str]
) -> tuple[str, ...]:
    """사용자가 고른 공정을 저장할 목록으로 만든다(모듈 설명의 「합치기」).

    `visible` 은 그 위젯이 보여 준 선택지다. 고른 것이 비면 빈 목록이다.
    """
    chosen = normalize_filter_processes(selected)
    if not chosen:
        return ()
    kept = [
        process for process in absent_filter_processes(stored, visible) if process not in chosen
    ]
    return normalize_filter_processes([*chosen, *kept])
