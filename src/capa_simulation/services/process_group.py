# Purpose: 공용 공정 그룹 대응의 칸 계약 · 정규화 · 검증과 HOME 그룹 단추 묶음을 만든다.

"""공용 공정 그룹 — HOME 공정 필터 팝업의 그룹 단추가 쓰는 「공정 → 공정 그룹」 대응.

**계산에 들지 않는다.** 그룹 단추는 공정 필터 초안만 바꾸고, 판정에 닿는 것은 「선택 공정 적용」
으로 적용한 공정 목록이다. 그래서 시나리오에 딸리지 않는 공용 프로필이고 어느 계산 · 그림 캐시
키에도 넣지 않는다. Streamlit 과 DB 를 모른다.

열쇠는 원본 공정명이다 — 표시명은 화면 글자에만 쓴다. 맞대기는 `process_group_key`(공정 표시명과
같은 정규화: 앞뒤 공백 · U+00A0 정리, 대소문자는 가림) 하나로 하고 세 자리가 모두 이것을 양쪽에 건다
— 저장 검증의 「같은 공정 두 줄」 판정, 편집 표 줄 만들기, 그룹 단추의 공정 고르기. 어긋나면 보이는
공정이 「이 화면에 없음」 줄로 한 번 더 서거나 단추가 공정을 놓친다. 선택지 글자는 원본 그대로 두고
맞댈 때만 줄인다.

그룹 낱말은 설비 마스터 「공정구분」 그룹(`equipment_contract.LINE_TYPE_GROUPS`)의 표기를 그대로
들이고 차례만 단추 차례로 둔다. 호기 속성 「공정구분」 과 같은 낱말을 값으로 쓰지만 이것은 공정 단위
대응이라 다른 개념이다. 이 기능의 코드 이름은 늘 `process_group` 이다 — 맨 `group` 은 공정 고르기
타일의 확보 구역(`process_picker.ProcessPickerItem.group`)이 이미 쓴다.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

import pandas as pd

from capa_simulation.services.equipment_contract import LINE_TYPE_GROUPS
from capa_simulation.services.frame_contracts import require_exact_columns
from capa_simulation.services.process_rename import DUPLICATE_REPORT_LIMIT, normalize_process_text

PROCESS_GROUP_COLUMNS: Final = ("공정", "공정그룹")
PROCESS_GROUP_LABEL: Final = "공정 그룹"

# 단추 · 편집 칸 선택지 차례(casefold 낱말). 표기는 `LINE_TYPE_GROUPS` 에서 찾아 들인다.
_PROCESS_GROUP_ORDER: Final = ("front", "pkg", "mi", "test", "fdy", "물류")


def _ordered_process_groups() -> tuple[str, ...]:
    """`LINE_TYPE_GROUPS` 의 표기를 단추 차례로 늘어놓는다.

    차례에 없는 낱말은 뒤에 붙이고, 그 목록에서 빠진 낱말은 건너뛴다 — 낱말이 바뀌어도 앱은 서고,
    차례 시험(`tests/test_process_group.py`)이 잡는다.
    """
    canonical = {group.casefold(): group for group in LINE_TYPE_GROUPS}
    ordered = [canonical[key] for key in _PROCESS_GROUP_ORDER if key in canonical]
    ordered.extend(
        group for group in LINE_TYPE_GROUPS if group.casefold() not in _PROCESS_GROUP_ORDER
    )
    return tuple(ordered)


PROCESS_GROUPS: Final[tuple[str, ...]] = _ordered_process_groups()

_CANONICAL_GROUPS: Final = {group.casefold(): group for group in PROCESS_GROUPS}

Assignment = tuple[str, str]


class ProcessGroupDuplicateError(ValueError):
    """같은 공정(열쇠)이 두 줄이다.

    글은 평문이다. 겹친 공정은 사람 글이라 `names` 로도 실어, 마크다운으로 그리는 화면이 이름을 글자
    그대로 막아 `process_group_duplicate_message` 로 다시 짓게 한다.
    """

    def __init__(self, names: Sequence[str]) -> None:
        self.names = tuple(names)
        super().__init__(process_group_duplicate_message(self.names))


def process_group_duplicate_message(names: Sequence[str]) -> str:
    """같은 공정 두 줄 오류문. 이름은 앞의 `DUPLICATE_REPORT_LIMIT` 개만 적는다."""
    return f"같은 공정이 두 줄입니다: {', '.join(names[:DUPLICATE_REPORT_LIMIT])}"


def process_group_key(value: object) -> str:
    """맞대기 · 저장 열쇠 — `normalize_process_text` 그대로(대소문자는 가린다)."""
    return normalize_process_text(value)


def _known_process_group(value: object) -> str | None:
    """읽을 때 쓰는 그룹 — 목록 안이면 정본 표기, 빈 값 · 목록 밖은 None(멈추지 않는다)."""
    return _CANONICAL_GROUPS.get(normalize_process_text(value).casefold())


def canonical_process_group(value: object) -> str | None:
    """저장할 때 쓰는 그룹 — 빈 값은 None(그룹 없음), 목록 안은 정본 표기(`front` → `FRONT`).

    목록 밖 글자는 `ValueError` 다.
    """
    text = normalize_process_text(value)
    if not text:
        return None
    group = _CANONICAL_GROUPS.get(text.casefold())
    if group is None:
        raise ValueError(
            f"{PROCESS_GROUP_LABEL}은 {' · '.join(PROCESS_GROUPS)} 가운데 하나입니다: {text}"
        )
    return group


def normalize_process_groups(
    assignments: Iterable[tuple[object, object]],
) -> tuple[Assignment, ...]:
    """저장할 대응 — (열쇠 공정, 정본 그룹)을 공정 글자순으로.

    그룹이 빈 줄은 「그룹 없음」 이라 버린다(공정까지 빈 줄도 그렇다). 그룹을 준 줄의 공정이
    비었거나 같은 공정이 두 줄이면 `ValueError` 다(같은 공정은 `ProcessGroupDuplicateError`).
    목록 밖 그룹도 `ValueError` 다(`canonical_process_group`).
    """
    kept: dict[str, str] = {}
    duplicates: list[str] = []
    for process_value, group_value in assignments:
        group = canonical_process_group(group_value)
        if group is None:
            continue
        process = process_group_key(process_value)
        if not process:
            raise ValueError(f"공정이 빈 줄에는 {PROCESS_GROUP_LABEL}을 줄 수 없습니다.")
        if process in kept:
            if process not in duplicates:
                duplicates.append(process)
            continue
        kept[process] = group
    if duplicates:
        raise ProcessGroupDuplicateError(duplicates)
    return tuple(sorted(kept.items()))


def _readable_assignments(assignments: Sequence[tuple[str, str]]) -> dict[str, str | None]:
    """저장된 대응을 열쇠 → 그룹으로(목록 밖 그룹은 None). 같은 열쇠는 앞 줄이 이긴다."""
    readable: dict[str, str | None] = {}
    for process, group in assignments:
        readable.setdefault(process_group_key(process), _known_process_group(group))
    return readable


def process_group_editor_frame(
    assignments: Sequence[tuple[str, str]],
    process_options: Sequence[str],
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """편집 표와 선택지 밖 저장 공정들.

    줄은 선택지 차례(공용 표시순서로 선 원본 글자 그대로) 다음에 선택지에 없는 저장 공정(공정
    글자순)이다 — 통째 교체 저장이 화면에 안 보이는 저장값을 날리지 않게 저장된 줄을 모두 보인다.
    한 열쇠는 한 줄이다 — 열쇠가 같은 선택지는 처음 나온 원본 글자로 한 번만 선다(두 줄로 서면
    손대지 않은 표의 저장도 「같은 공정 두 줄」 로 막힌다).
    칸은 「공정」(원본) · 「공정그룹」(정본 표기, 그룹 없음 · 목록 밖 그룹은 None)이다.
    """
    stored = _readable_assignments(assignments)
    processes: list[str] = []
    option_keys: set[str] = set()
    for option in process_options:
        key = process_group_key(option)
        if key in option_keys:
            continue
        option_keys.add(key)
        processes.append(option)
    outside = tuple(sorted(key for key in stored if key and key not in option_keys))
    processes.extend(outside)
    groups = [stored.get(process_group_key(process)) for process in processes]
    frame = pd.DataFrame(
        {
            PROCESS_GROUP_COLUMNS[0]: pd.Series(processes, dtype="object"),
            PROCESS_GROUP_COLUMNS[1]: pd.Series(groups, dtype="object"),
        }
    )
    return frame, outside


def assignments_from_editor(frame: pd.DataFrame) -> tuple[Assignment, ...]:
    """편집 결과 표 → 저장할 대응(`normalize_process_groups`)."""
    require_exact_columns(frame.columns, PROCESS_GROUP_COLUMNS, f"{PROCESS_GROUP_LABEL} 컬럼")
    process_column, group_column = PROCESS_GROUP_COLUMNS
    return normalize_process_groups(
        zip(frame[process_column].tolist(), frame[group_column].tolist(), strict=True)
    )


def same_process_groups(
    left: Sequence[tuple[str, str]],
    right: Sequence[tuple[str, str]],
) -> bool:
    """두 대응이 같은가 — 차례에 기대지 않는다(SQL 정렬과 파이썬 정렬이 어긋나도 같게 본다)."""
    return dict(left) == dict(right)


def process_group_buttons(
    assignments: Sequence[tuple[str, str]],
    process_options: Sequence[str],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """그룹 단추 묶음 — (그룹, 이번 선택지 안 그 그룹 공정들).

    대응이 한 줄이라도 있는 그룹만 든다 — 쓰지 않는 그룹은 단추가 없다. 대응은 있는데 이번 선택지에
    그 그룹 공정이 없으면 공정이 빈 묶음으로 든다(화면이 그 단추를 잠근다). 목록 밖 그룹 줄은
    건너뛴다. 그룹 차례는 `PROCESS_GROUPS`, 공정 차례는 선택지 차례이고 값은 선택지의 원본
    글자다(초안 · 콜백이 쓰는 값). 대응이 없으면 빈 묶음이다.
    """
    stored = {
        key: group for key, group in _readable_assignments(assignments).items() if group is not None
    }
    members: dict[str, list[str]] = {group: [] for group in stored.values()}
    seen: set[str] = set()
    for option in process_options:
        if option in seen:
            continue
        seen.add(option)
        group = stored.get(process_group_key(option))
        if group is not None:
            members[group].append(option)
    return tuple((group, tuple(members[group])) for group in PROCESS_GROUPS if group in members)
