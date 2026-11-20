# Purpose: 누적 진척의 손 기록 · 최종 목표 모델과 값 규칙, 머리 한 줄 요약, 화면 합계를 둔다.

"""필요 단축 일정 「누적 진척」(2026-11-20 사용자 보드 답 누적-1 A · 누적-2 c · 누적-3 a · 누적-4
「한 줄 기록」 · 누적-5 a).

- **기록 한 줄 = ISO 주차 하나 · 단축 필요일수 하나**(`ProgressEntry`) — 사람이 적은 수다. 화면에서
  공정 · 목표 확보율을 바꿔도 선은 그대로다(기록만 잇는다). 「이번 주 값 넣기」 는 지금 화면의 단축
  필요일수 합계(`screen_shortening_days`)로 칸을 채워 줄 뿐이고 고쳐 적을 수 있다.
- **주차**는 ISO 해 · 주를 함께 든다(`ProgressWeek`) — 해 넘김(W52 → W01)의 차례가 (해, 주)로 맞고,
  글은 앱의 주차 도우미 `iso_week_calendar.weeknum_label` 의 `YY-W##` 하나다(설계 규칙 UI-CON-04).
- **최종 목표**(`ProgressGoal`)는 목표 일수와 목표 주차 하나 — 공용 값이고 처음은 비어 있다(목표선
  없음).
- **머리 한 줄**(`summarize_log`)의 「지금 일수」 · 「지난 기록 대비」 는 **기록 기준**이다 — 마지막
  기록과 그 앞 기록. 기록이 하나면 대비는 없다(0 이 아니다 — 설계 규칙 UI-DAT-06).

저장은 설비 DB `0036`(`persistence/shortening_progress_log_store.py`)이다. 이 모듈은 표준 라이브러리
· pandas 와 앱 주차 도우미만 읽는다 — 화면 상태에 닿지 않는다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from capa_simulation.services.iso_week_calendar import weeknum_label
from capa_simulation.services.required_shortening import KIND_SHORTENED

__all__ = [
    "PROGRESS_DAYS_MAX",
    "PROGRESS_RECORDED_BY_MAX_LENGTH",
    "ProgressEntry",
    "ProgressGoal",
    "ProgressGoalState",
    "ProgressHeadline",
    "ProgressLog",
    "ProgressLogConflictError",
    "ProgressLogInvalidError",
    "ProgressWeek",
    "goal_week_options",
    "normalize_progress_days",
    "normalize_recorded_by",
    "record_week_options",
    "screen_shortening_days",
    "summarize_log",
]

# 손으로 적는 단축 필요일수의 위끝 — 오타(자릿수 하나 더) 막기. 지금 화면 합계는 호기마다 수십 ~
# 수백 일을 더한 값이라 넉넉히 둔다.
PROGRESS_DAYS_MAX = 99_999
PROGRESS_RECORDED_BY_MAX_LENGTH = 40
# 기록 주차 고르기가 오늘 주에서 거슬러 보이는 주 수 — 지난 기록을 한 해 넘게 채울 수 있게.
RECORD_WEEKS_BACK = 52
# 목표 주차 고르기가 오늘 주 앞뒤로 보이는 주 수.
GOAL_WEEKS_BACK = 26
GOAL_WEEKS_AHEAD = 104

_LABEL_PATTERN = re.compile(r"^(?P<year>\d{2})-W(?P<week>\d{2})$")


class ProgressLogInvalidError(ValueError):
    """적은 값이 규칙 밖이다(빈 일수 · 음수 · 없는 주차)."""


class ProgressLogConflictError(ValueError):
    """화면이 본 값과 저장본이 다르다 — 그 사이 다른 사람이 같은 주 · 목표를 고쳤다."""


@dataclass(frozen=True, order=True)
class ProgressWeek:
    """ISO 주차 하나 — 해 · 주. 차례는 (해, 주)라 해 넘김(25-W52 → 26-W01)이 맞다."""

    year: int
    week: int

    def __post_init__(self) -> None:
        try:
            date.fromisocalendar(int(self.year), int(self.week), 1)
        except (TypeError, ValueError) as exc:
            raise ProgressLogInvalidError(
                f"없는 주차입니다: {self.year}년 {self.week}주차"
            ) from exc

    @classmethod
    def of(cls, day: date) -> ProgressWeek:
        """그 날이 든 ISO 주."""
        year, week, _ = day.isocalendar()
        return cls(int(year), int(week))

    @classmethod
    def parse(cls, text: str) -> ProgressWeek:
        """`YY-W##` 글(`weeknum_label` 의 꼴)."""
        matched = _LABEL_PATTERN.fullmatch(str(text).strip().upper())
        if matched is None:
            raise ProgressLogInvalidError(f"주차는 YY-W## 꼴이어야 합니다: {text!r}")
        return cls(2000 + int(matched.group("year")), int(matched.group("week")))

    @property
    def monday(self) -> date:
        return date.fromisocalendar(self.year, self.week, 1)

    @property
    def label(self) -> str:
        """`YY-W##` — 앱 주차 글 하나(`iso_week_calendar.weeknum_label`)."""
        return weeknum_label(self.monday)

    def shifted(self, weeks: int) -> ProgressWeek:
        return ProgressWeek.of(self.monday + timedelta(weeks=weeks))

    def weeks_until(self, other: ProgressWeek) -> int:
        """`other` 까지 몇 주 뒤인가(앞이면 음수)."""
        return (other.monday - self.monday).days // 7


@dataclass(frozen=True)
class ProgressEntry:
    """기록 한 줄 — 그 주의 단축 필요일수(사람이 적은 수)."""

    week: ProgressWeek
    days: int
    recorded_by: str = ""
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ProgressGoal:
    """최종 목표 — 목표 일수와 목표 주차 하나."""

    days: int
    week: ProgressWeek


@dataclass(frozen=True)
class ProgressGoalState:
    """최종 목표 머리 행. 한 번도 저장하지 않았으면 목표 없음 · version 0 이다."""

    goal: ProgressGoal | None = None
    version: int = 0
    saved_by: str = ""
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ProgressLog:
    """기록 전부(주차 차례 — 오래된 것이 앞)와 최종 목표."""

    entries: tuple[ProgressEntry, ...] = ()
    goal: ProgressGoalState = ProgressGoalState()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda e: e.week)))

    def days_of(self, week: ProgressWeek) -> int | None:
        """그 주의 기록 일수(없으면 None)."""
        return next((entry.days for entry in self.entries if entry.week == week), None)

    def changes(self) -> tuple[int | None, ...]:
        """기록마다 지난 기록 대비(첫 기록은 None)."""
        return tuple(
            None if index == 0 else entry.days - self.entries[index - 1].days
            for index, entry in enumerate(self.entries)
        )


@dataclass(frozen=True)
class ProgressHeadline:
    """머리 한 줄의 값 — 모두 기록 기준이다.

    `change` 는 마지막 기록 − 그 앞 기록(기록이 둘 이상일 때만). `remaining` 은 마지막 기록 − 목표
    일수(목표와 기록이 다 있을 때만, 0 이하면 도달). `progress` 는 첫 기록에서 목표까지 줄인 몫(0 ~
    1). `overdue` 는 목표 주차가 지났는데 도달하지 못한 것이다.
    """

    first: ProgressEntry | None
    latest: ProgressEntry | None
    change: int | None
    goal: ProgressGoal | None
    remaining: int | None
    progress: float | None
    overdue: bool

    @property
    def reached(self) -> bool:
        return self.remaining is not None and self.remaining <= 0


def summarize_log(log: ProgressLog, today: date) -> ProgressHeadline:
    """머리 한 줄 요약. `today` 는 목표 주차가 지났는지만 가른다."""
    entries = log.entries
    first = entries[0] if entries else None
    latest = entries[-1] if entries else None
    change = entries[-1].days - entries[-2].days if len(entries) >= 2 else None
    goal = log.goal.goal
    remaining: int | None = None
    progress: float | None = None
    overdue = False
    if goal is not None and latest is not None and first is not None:
        remaining = latest.days - goal.days
        span = first.days - goal.days
        if span > 0:
            progress = min(max((first.days - latest.days) / span, 0.0), 1.0)
        else:
            progress = 1.0 if remaining <= 0 else 0.0
        overdue = remaining > 0 and ProgressWeek.of(today) > goal.week
    return ProgressHeadline(
        first=first,
        latest=latest,
        change=change,
        goal=goal,
        remaining=remaining,
        progress=progress,
        overdue=overdue,
    )


def normalize_progress_days(value: object) -> int:
    """적은 단축 필요일수 — 0 이상 정수. 비었거나 범위 밖이면 거절한다(소수는 받지 않는다)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ProgressLogInvalidError("단축 필요일수를 적으세요.")
    try:
        number = float(str(value))
    except ValueError as exc:
        raise ProgressLogInvalidError(f"단축 필요일수는 숫자여야 합니다: {value!r}") from exc
    if not number.is_integer():
        raise ProgressLogInvalidError("단축 필요일수는 정수(일)로 적습니다.")
    days = int(number)
    if days < 0 or days > PROGRESS_DAYS_MAX:
        raise ProgressLogInvalidError(
            f"단축 필요일수는 0 ~ {PROGRESS_DAYS_MAX:,}일 사이로 적습니다."
        )
    return days


def normalize_recorded_by(value: object) -> str:
    """손입력 이름 — 앞뒤 빈칸을 걷고 길이를 자른다(선택 칸)."""
    text = "" if value is None else str(value).strip()
    return text[:PROGRESS_RECORDED_BY_MAX_LENGTH]


def record_week_options(today: date, entries: Iterable[ProgressEntry]) -> tuple[ProgressWeek, ...]:
    """기록 주차 고르기의 선택지 — 오늘 주에서 `RECORD_WEEKS_BACK` 주 거슬러, 그보다 오래된 기록
    주도 함께. 최근 주가 앞이다. 앞날의 주는 두지 않는다(그 주의 일수는 아직 없다)."""
    this_week = ProgressWeek.of(today)
    weeks = {this_week.shifted(-offset) for offset in range(RECORD_WEEKS_BACK + 1)}
    weeks.update(entry.week for entry in entries if entry.week <= this_week)
    return tuple(sorted(weeks, reverse=True))


def goal_week_options(today: date, goal: ProgressGoal | None) -> tuple[ProgressWeek, ...]:
    """목표 주차 고르기의 선택지 — 오늘 주 앞뒤로(뒤가 넓다), 저장된 목표 주가 밖이면 그 주도. 이른
    주가 앞이다."""
    this_week = ProgressWeek.of(today)
    weeks = {this_week.shifted(offset) for offset in range(-GOAL_WEEKS_BACK, GOAL_WEEKS_AHEAD + 1)}
    if goal is not None:
        weeks.add(goal.week)
    return tuple(sorted(weeks))


def screen_shortening_days(units: pd.DataFrame, processes: Sequence[str]) -> int:
    """지금 화면의 단축 필요일수 합계 — 고른 목표의 계획(`LevelPlan.units`)에서 범위 공정의 당긴
    호기(`구분` 「단축」) 단축일수 합이다(가상 호기 「추가N」 은 일수가 없다).

    「이번 주 값 넣기」 가 이 값 하나를 쓴다 — 진척 비교(기준선)와 상관없는 값이다. 진척 비교 요약의
    지금 합계(`ProgressSummary.current_days`) 는 기준선 대비 필요 시점이 지난 행과 기준이 바뀐 행(한
    시점만 남는 호기)을 따로 빼 두므로 이 값은 그 합 + `lapsed_current_days` +
    `rebased_current_days` 와 같다(시험이 맞댄다)."""
    if units.empty:
        return 0
    chosen = units.loc[units["공정"].isin(list(processes)) & units["구분"].eq(KIND_SHORTENED)]
    return int(pd.to_numeric(chosen["단축일수"], errors="coerce").fillna(0).sum())
