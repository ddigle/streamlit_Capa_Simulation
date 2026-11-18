# Purpose: 접속 명단 편집 표의 초안을 저장할 일(빼기 · 등급 · 넣기)과 막는 문제 수로 읽는다.

"""접속 명단 편집 표(Admin Area 「접속 명단」 — 2026-11-18 구현 확인 보드 「고칠 것」)의 저장 판.

표는 범용 편집 그리드(`services/edit_grid`)의 줄 규칙 표다 — 업무 키는 명단 사람의 loginid(견주는
꼴)
와 빈 새 줄의 `+n` 이다. 이 모듈은 Streamlit · 저장소를 모르고 초안만 읽는다(값은 어디에도 남기지
않는다 — 문제는 수로만 센다).

- **빼기** — 명단 사람 줄의 줄 지우기 표지(`edit_grid.removed_keys`).
- **등급 바꿈** — 명단 사람 줄의 「등급」 칸 초안이 지금 등급과 다른 것(지운 줄은 빼기가 이긴다).
- **넣기** — 빈 새 줄에 무엇이든 적힌 것. 「계정」 은 loginid 꼴(`access.entry_key`)이어야 하고 머리
  글(`loginid` · `계정`)이 아니며 명단 · 다른 새 줄과 겹치지 않고, 「등급」 이 있어야 한다.
  「이름」 · 「부서」 는 손으로 적은 그대로 넣는다(빈 칸은 빈 칸).
- **문제**가 하나라도 있으면 저장하지 않는다 — 칸 오류(빨간 칸) · 계정이 빔 · 계정 꼴이 아님 · 머리
  글 · 겹침 · 등급이 빔 · 잠긴 줄(나 자신 · 환경변수 개발자의 등급 · 줄 지우기, 명단 사람의 계정 ·
  이름 · 부서 · 등록일 · 등록 길 칸 초안 — 표가 잠그고 계정이 다른 붙여넣기 줄은 건너뛰지만
  다시 본다).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from capa_simulation.auth import grades
from capa_simulation.auth.access import entry_key
from capa_simulation.services.edit_grid import (
    CellValue,
    DraftState,
    change_counts,
    removed_keys,
)

ACCOUNT_COLUMN: Final = "계정"
NAME_COLUMN: Final = "이름"
DEPT_COLUMN: Final = "부서"
DATE_COLUMN: Final = "등록일"
VIA_COLUMN: Final = "등록 길"
GRADE_COLUMN: Final = "등급"
VALUE_COLUMNS: Final = (
    ACCOUNT_COLUMN,
    NAME_COLUMN,
    DEPT_COLUMN,
    DATE_COLUMN,
    VIA_COLUMN,
    GRADE_COLUMN,
)
# 명단 사람 줄에서 잠긴 칸 — 표가 잠그고 저장 판이 다시 본다(초안에 들었으면 고칠 수 없는 줄).
LISTED_LOCKED_COLUMNS: Final = (ACCOUNT_COLUMN, NAME_COLUMN, DEPT_COLUMN, DATE_COLUMN, VIA_COLUMN)
# 「등급」 고르기 칸의 항목 — 낮은 차례(열람 · 실무자 · 관리자 · 개발자). 값은 이 차례 번호다.
GRADE_OPTIONS: Final = tuple(grades.label_of(grade) for grade in grades.GRADES)
# 새 줄의 업무 키 앞글자 — loginid 꼴에 없는 글자라 사람과 겹치지 않는다.
FRESH_PREFIX: Final = "+"
# 붙여 넣은 표의 머리 줄 글 — 계정으로 넣지 않는다(그 낱말의 사람에게 접속이 열린다).
HEADER_WORDS: Final = frozenset({"loginid", "계정"})


@dataclass(frozen=True)
class NewPerson:
    """새 줄 하나 — 견주는 꼴 loginid · 이름 · 부서 · 등급(`grades.GRADES` 값) · 그 새 줄 키."""

    loginid: str
    name: str = field(default="", repr=False)
    dept: str = field(default="", repr=False)
    grade: str = grades.VIEWER
    row: str = ""


@dataclass(frozen=True)
class Problems:
    """저장을 막는 문제 수(값 없음)."""

    errors: int = 0
    no_account: int = 0
    bad_account: int = 0
    header: int = 0
    duplicate: int = 0
    no_grade: int = 0
    locked: int = 0

    @property
    def any(self) -> bool:
        return any(
            (
                self.errors,
                self.no_account,
                self.bad_account,
                self.header,
                self.duplicate,
                self.no_grade,
                self.locked,
            )
        )

    def text(self) -> str:
        """「저장하지 않았습니다 — …」 의 뒤 글(문제마다 수 한 마디)."""
        parts = [
            (self.errors, "고칠 칸 {n}개"),
            (self.no_account, "계정이 빈 새 줄 {n}개"),
            (self.bad_account, "계정 꼴이 아닌 새 줄 {n}개"),
            (self.header, "머리 글(loginid · 계정)이 든 새 줄 {n}개"),
            (self.duplicate, "이미 명단에 있거나 겹치는 계정 {n}개"),
            (self.no_grade, "등급이 빈 줄 {n}개"),
            (self.locked, "바꾸거나 지울 수 없는 줄 {n}개"),
        ]
        return " · ".join(template.format(n=f"{count:,}") for count, template in parts if count)


@dataclass(frozen=True)
class AccessPlan:
    """저장할 일 — 뺄 사람 · 바꿀 등급 · 넣을 사람(값은 저장 함수에만 간다)과 문제 수."""

    removed: tuple[str, ...] = field(default=(), repr=False)
    graded: Mapping[str, str] = field(default_factory=dict, repr=False)
    added: tuple[NewPerson, ...] = field(default=(), repr=False)
    problems: Problems = Problems()

    @property
    def empty(self) -> bool:
        return not (self.removed or self.graded or self.added)

    def added_by_grade(self) -> dict[str, tuple[NewPerson, ...]]:
        """넣을 사람을 등급마다(낮은 차례) — 저장 함수가 등급 하나씩 받는다."""
        groups: dict[str, list[NewPerson]] = {}
        for person in self.added:
            groups.setdefault(person.grade, []).append(person)
        return {grade: tuple(groups[grade]) for grade in grades.GRADES if grade in groups}


def fresh_key(number: int) -> str:
    """새 줄 `number`(1 부터)의 업무 키."""
    return f"{FRESH_PREFIX}{number}"


def is_fresh(key: str) -> bool:
    return key.startswith(FRESH_PREFIX)


def grade_at(value: CellValue) -> str | None:
    """「등급」 칸 값(차례 번호) → 등급. 빈칸 · 범위 밖은 None."""
    if not isinstance(value, float) or math.isnan(value) or value != math.floor(value):
        return None
    at = int(value)
    return grades.GRADES[at] if 0 <= at < len(grades.GRADES) else None


def _text(cells: Mapping[str, CellValue], column: str) -> str:
    value = cells.get(column)
    return value.strip() if isinstance(value, str) else ""


def plan_changes(
    draft: DraftState | None,
    *,
    listed: Mapping[str, str],
    fresh: Sequence[str],
    locked: frozenset[str] = frozenset(),
) -> AccessPlan:
    """초안 → 저장 판. `listed` 는 표에 실린 명단 사람(견주는 꼴 loginid → 지금 등급), `fresh` 는
    표의 빈 새 줄 키(차례대로), `locked` 는 등급 · 줄을 바꿀 수 없는 사람(나 자신 · 환경변수
    개발자)이다. 표에 없는 키의 초안(그 사이 명단에서 빠진 사람)은 읽지 않는다."""
    if draft is None:
        return AccessPlan()
    cells = draft["cells"]
    errors = change_counts(draft)[2]
    removed = tuple(key for key in removed_keys(draft) if key in listed)
    locked_count = sum(1 for key in removed if key in locked)
    graded: dict[str, str] = {}
    no_grade = 0
    for key, current in listed.items():
        row = cells.get(key)
        if any(
            column in book
            for book in (row or {}, draft["bad"].get(key) or {})
            for column in LISTED_LOCKED_COLUMNS
        ):
            locked_count += 1
            continue
        if key in removed or row is None or GRADE_COLUMN not in row:
            continue
        grade = grade_at(row[GRADE_COLUMN])
        if grade is None:
            no_grade += 1
        elif grade != current:
            if key in locked:
                locked_count += 1
            else:
                graded[key] = grade
    added: list[NewPerson] = []
    seen = set(listed)
    no_account = bad_account = header = duplicate = 0
    for key in fresh:
        row = cells.get(key) or {}
        if not any(value is not None for value in row.values()):
            continue
        account = _text(row, ACCOUNT_COLUMN)
        grade = grade_at(row.get(GRADE_COLUMN))
        if not account:
            no_account += 1
            continue
        loginid = entry_key(account)
        if loginid is None:
            bad_account += 1
            continue
        if loginid in HEADER_WORDS:
            header += 1
            continue
        if loginid in seen:
            duplicate += 1
            continue
        seen.add(loginid)
        if grade is None:
            no_grade += 1
            continue
        added.append(
            NewPerson(loginid, _text(row, NAME_COLUMN), _text(row, DEPT_COLUMN), grade, key)
        )
    problems = Problems(
        errors=errors,
        no_account=no_account,
        bad_account=bad_account,
        header=header,
        duplicate=duplicate,
        no_grade=no_grade,
        locked=locked_count,
    )
    return AccessPlan(
        removed=tuple(key for key in removed if key not in locked),
        graded=graded,
        added=tuple(added),
        problems=problems,
    )
