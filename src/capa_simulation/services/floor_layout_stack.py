# Purpose: Space 층 도면의 겹친 순서(호기 차례 · 호기 위 올림)의 계약 · 검증 · 줄 세우기를 정의한다.

"""Space 층 도면의 겹친 순서(설비 `0034` — 2026-11-12 Space 요청 7-2 범위 답 「전부」 의 둘째
몫).

도면은 세 겹이다 — 호기 아래(영역 · 도형), 호기, 호기 위(글자 · 동선 · 발자국 · 베이 · 반입구 ·
문 · 기둥). 같은 겹 안 도면 요소의 차례는 요소 표의 그리는 순서(`source_row_no`)이고, 이 모듈은
그 밖의 둘을 맡는다.

- **호기끼리 차례**(`FloorStack.units`) — 아래 → 위. 저장 꼴은 호기 키(이름을 바꿔도 따라간다)이고
  화면 · 대기분 꼴은 설비명이다(`stack_names` · `stack_keys` 가 옮긴다). 모듈은 묶음째 움직인다
  (설계 A (가)).
- **호기 위로 올린 영역 · 도형**(`FloorStack.raised`) — 요소 id 모음. 위 겹 안 차례는 요소 표
  차례 그대로다.

층 현행값이고 **공식에서만** 쓴다(가정 설비 시나리오의 배치 차이에 들지 않는다 — 가정 세션은 공식
순서를 읽기만 한다). 읽기 규칙(`ordered_ids`): 순서에 적힌 호기를 적힌 차례로 먼저, 적히지 않은
호기(새 호기 · 옮겨 온 호기)는 그 위에 지금 규칙(받은 차례 — 설비 마스터 행 차례, 옮겨 온 것 맨
위)으로 그린다. 적혔지만 지금 없는 호기 · 요소는 건너뛴다. 순서가 비면 받은 차례 그대로다. UI
상태를 모른다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, TypeVar

from capa_simulation.services.floor_layout_mark import (
    MARKS_PER_FLOOR_MAX,
    FloorLayoutMark,
)

STACK_UNIT: Final = "unit"
STACK_RAISED: Final = "raised"
STACK_KINDS: Final = (STACK_UNIT, STACK_RAISED)
# 호기 위로 올릴 수 있는 종류 — 나머지 위 겹 종류는 늘 호기 위이고 호기 아래로 내리지 않는다.
RAISABLE_KINDS: Final = frozenset({"zone", "shape"})
# 한 층에 적을 호기 수의 상한 — 층 하나의 호기보다 넉넉한 값이다(잘못 보낸 적용이 끝없는 목록을
# 쓰지 않게). 올림은 요소 상한과 같다.
STACK_UNITS_MAX: Final = 5000

_T = TypeVar("_T")


@dataclass(frozen=True)
class FloorStack:
    """한 층의 겹친 순서 — 호기 차례(아래 → 위)와 호기 위로 올린 영역 · 도형 id. 저장소가 낼
    때는 호기 키, 화면 · 대기분은 설비명이다. 둘 다 비면 거짓이다(지금과 같이 그린다)."""

    units: tuple[str, ...] = ()
    raised: frozenset[str] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.units or self.raised)


EMPTY_STACK: Final = FloorStack()


def stack_payload(stack: FloorStack) -> dict[str, list[str]]:
    """지문 · 비교의 정규 꼴 — 호기는 적힌 차례, 올림은 이름 차례."""
    return {"units": list(stack.units), "raised": sorted(stack.raised)}


def stack_fingerprint(stack: FloorStack) -> str:
    """순서 한 벌의 지문. 빈 순서는 빈 글이다."""
    if not stack:
        return ""
    text = json.dumps(stack_payload(stack), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _id_list(raw: object, what: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list | tuple):
        raise ValueError(f"겹친 순서의 {what} 목록을 읽지 못했습니다.")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"겹친 순서의 {what} id 가 맞지 않습니다: {item!r}")
        out.append(item.strip())
    return out


def prepare_floor_stack(
    raw: object,
    *,
    unit_ids: Collection[str],
    marks: Sequence[FloorLayoutMark],
) -> FloorStack:
    """편집기 적용의 `stack`({units: [설비명…], raised: [요소 id…]})을 검증해 `FloorStack` 으로.

    하나라도 어긋나면 `ValueError` 다 — 모르는 호기(`unit_ids` 밖), 같은 id 두 번, 영역 · 도형이
    아닌 올림, 상한을 넘은 목록. 호기는 보낸 차례 그대로다."""
    if not isinstance(raw, Mapping):
        raise ValueError("겹친 순서를 읽지 못했습니다.")
    units = _id_list(raw.get("units"), "호기")
    raised = _id_list(raw.get("raised"), "올림")
    if len(units) > STACK_UNITS_MAX:
        raise ValueError(f"한 층의 겹친 순서는 호기 {STACK_UNITS_MAX}대까지입니다: {len(units)}대")
    if len(raised) > MARKS_PER_FLOOR_MAX:
        raise ValueError(
            f"호기 위로 올린 요소는 {MARKS_PER_FLOOR_MAX}개까지입니다: {len(raised)}개"
        )
    known = set(unit_ids)
    seen: set[str] = set()
    for unit in units:
        if unit not in known:
            raise ValueError(f"이 편집기에 없는 호기의 순서가 왔습니다: {unit}")
        if unit in seen:
            raise ValueError(f"겹친 순서에 같은 호기가 두 번 왔습니다: {unit}")
        seen.add(unit)
    kinds = {mark.mark_id: mark.kind for mark in marks}
    for mark_id in raised:
        kind = kinds.get(mark_id)
        if kind is None:
            raise ValueError(f"이 층에 없는 요소를 호기 위로 올렸습니다: {mark_id}")
        if kind not in RAISABLE_KINDS:
            raise ValueError(f"호기 위로 올리는 것은 영역 · 도형뿐입니다: {mark_id}")
    if len(set(raised)) != len(raised):
        raise ValueError("호기 위로 올린 요소에 같은 id 가 두 번 왔습니다.")
    return FloorStack(units=tuple(units), raised=frozenset(raised))


def ordered_ids(
    ids: Sequence[str],
    groups: Mapping[str, str | None],
    units: Sequence[str],
) -> list[str]:
    """받은 차례(`ids` — 지금 규칙)를 겹친 순서(`units` — 아래 → 위)로 줄 세운 차례.

    - 순서가 비면 받은 차례 그대로다(행이 없는 층은 지금과 같이 그린다).
    - 모듈은 묶음째다 — 같은 Main 설비(`groups`)의 호기가 한 덩이로 붙는다. 덩이 자리는 적힌
      형제 가운데 가장 아래 것의 자리이고, 덩이 안은 적힌 차례 다음 적히지 않은 모듈의 받은
      차례다.
    - 적힌 덩이를 적힌 차례로 먼저, 적힌 형제가 없는 덩이(새 호기 · 옮겨 온 호기)는 그 위에 받은
      차례로 둔다.
    - 적혔지만 `ids` 에 없는 호기는 건너뛴다.
    """
    if not units:
        return list(ids)
    rank: dict[str, int] = {}
    for k, unit in enumerate(units):
        rank.setdefault(unit, k)
    blocks: dict[str, list[str]] = {}
    first: dict[str, int] = {}
    for k, unit_id in enumerate(ids):
        group = groups.get(unit_id)
        block = f"g:{group}" if group else f"u:{unit_id}"
        blocks.setdefault(block, []).append(unit_id)
        first.setdefault(block, k)

    def block_order(block: str) -> tuple[int, int]:
        listed = [rank[member] for member in blocks[block] if member in rank]
        return (0, min(listed)) if listed else (1, first[block])

    out: list[str] = []
    for block in sorted(blocks, key=block_order):
        members = blocks[block]
        out += sorted((m for m in members if m in rank), key=rank.__getitem__)
        out += [m for m in members if m not in rank]
    return out


def ordered_items(
    items: Sequence[_T],
    stack: FloorStack,
    *,
    id_of: Callable[[_T], str] | None = None,
    group_of: Callable[[_T], str | None] | None = None,
) -> list[_T]:
    """편집기 · 보기 호기 payload(`{"id", "group", …}`)를 `ordered_ids` 차례로. 순서가 비면
    그대로다."""
    if not stack.units:
        return list(items)
    get_id = id_of or _item_id
    get_group = group_of or _item_group
    by_id: dict[str, _T] = {}
    ids: list[str] = []
    groups: dict[str, str | None] = {}
    for item in items:
        unit_id = get_id(item)
        if unit_id in by_id:
            continue
        by_id[unit_id] = item
        ids.append(unit_id)
        groups[unit_id] = get_group(item)
    return [by_id[unit_id] for unit_id in ordered_ids(ids, groups, stack.units)]


def _item_id(item: Any) -> str:
    return str(item["id"])


def _item_group(item: Any) -> str | None:
    group = item.get("group")
    return str(group) if group else None


def raised_ids(stack: FloorStack, marks: Iterable[FloorLayoutMark]) -> frozenset[str]:
    """이 층 요소 가운데 실제로 호기 위에 그릴 영역 · 도형 id — 지운 요소 · 다른 종류의 행은
    건너뛴다."""
    return frozenset(
        mark.mark_id
        for mark in marks
        if mark.kind in RAISABLE_KINDS and mark.mark_id in stack.raised
    )


def stack_names(stack: FloorStack, names: Mapping[str, str]) -> FloorStack:
    """호기 키 꼴 순서를 설비명 꼴로(`names` — 키 → 지금 설비명). 이름을 모르는 키는 건너뛴다."""
    return FloorStack(
        units=tuple(names[key] for key in stack.units if key in names), raised=stack.raised
    )


def stack_keys(stack: FloorStack, keys: Mapping[str, str]) -> FloorStack:
    """설비명 꼴 순서를 호기 키 꼴로(`keys` — 설비명 → 키). 키를 모르는 설비명(지운 호기)은
    건너뛴다."""
    return FloorStack(
        units=tuple(keys[name] for name in stack.units if name in keys), raised=stack.raised
    )


def renamed_stack(stack: FloorStack, renames: Mapping[str, str]) -> FloorStack:
    """설비명 꼴 순서가 이름 바꿈(옛 이름 → 새 이름)을 따라간다."""
    if not renames:
        return stack
    return FloorStack(
        units=tuple(renames.get(name, name) for name in stack.units), raised=stack.raised
    )


def staged_stack(
    applied: FloorStack,
    *,
    base: FloorStack,
    ids: Sequence[str],
    groups: Mapping[str, str | None],
    marks: Sequence[FloorLayoutMark],
) -> FloorStack:
    """편집기가 보낸 순서(`applied` — 편집기에 실린 설비명)를 대기분으로 둘 꼴로 좁힌다.

    비교는 보낸 호기 가운데서 본 줄 세운 차례로 한다(`ids` — 받은 차례, 편집기에 실린 설비명 +
    이번 적용의 새 호기).

    - 호기 차례가 빈 순서의 차례(지금 규칙)와 같으면 호기 행을 두지 않는다 — 올림만 바꾼 적용이
      층의 호기 차례를 굳히지 않는다.
    - 호기 차례가 지금 순서(`base` — 대기분 또는 저장값)의 차례와 같으면 그 호기 행을 그대로
      둔다.
    - 올림은 이 층 영역 · 도형 가운데 보낸 것이다.
    """
    sent = set(applied.units)

    def drawn(units: Sequence[str]) -> list[str]:
        return [unit_id for unit_id in ordered_ids(ids, groups, units) if unit_id in sent]

    order = drawn(applied.units)
    if order == drawn(()):
        units: tuple[str, ...] = ()
    elif order == drawn(base.units):
        units = base.units
    else:
        units = applied.units
    return FloorStack(units=units, raised=raised_ids(applied, marks))


def same_stack(
    left: FloorStack,
    right: FloorStack,
    *,
    ids: Sequence[str],
    groups: Mapping[str, str | None],
    marks: Sequence[FloorLayoutMark],
) -> bool:
    """두 순서가 이 층에서 같은 그림을 내나 — 줄 세운 호기 차례와 실제 올림이 같은가."""
    return ordered_ids(ids, groups, left.units) == ordered_ids(
        ids, groups, right.units
    ) and raised_ids(left, marks) == raised_ids(right, marks)
