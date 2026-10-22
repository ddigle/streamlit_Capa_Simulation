# Purpose: 월별 목표 가용대수·신규 호기로 호기마다 Qual 완료 마감을 내고 그 글자를 만든다.

"""Qual 마감 계산기 — 「이 호기는 언제까지 Qual 을 끝내야 하나」.

2026-10-07 에 따로 만든 계산기(HTML 한 장)를 가용설비 현황의 탭으로 옮긴 것이다(2026-10-22 사용자
요청 — **다른 데이터와 잇지 않고 같은 방식으로**). 원본의 `compute()` 와 화면 글자를 그대로 옮겼고,
`tests/test_qual_deadline.py` 가 원본 스크립트를 node 로 돌린 값과 글자 하나까지 맞댄다. 어느 DB 도
열지 않고 Streamlit 도 모른다.

규칙은 설비 일정 기준 가용대수와 같다.

- 그 달 W/D 구간은 `(전월 말일 − Cut-off, 당월 말일 − Cut-off]` 다 — 구간은 `services/wd_window.py`
  하나로 만든다(앱의 월별 가용과 같은 함수).
- 설비는 Qual 완료 **다음 날부터** 기여한다. 완료일이 `D` 인 호기가 한 달에 보태는 몫은
  `max(0, 구간 끝 − max(D, 구간 앞)) / 구간 길이` 다.
- 달마다 「직전 달 가용대수 + 앞 달까지 쓰인 호기의 이 달 몫」이 목표에 모자라면, 그 달까지
  적은 신규 호기를 **적은 차례대로** 꺼내 채운다. 모자람이 1 이상이면 마감은 구간 앞 경계(몫 1),
  1 보다 작으면 모자란 날 수만큼만 구간 끝에서 당긴 날(몫 = 그 날 수 / 구간 길이)이다. 남는 호기는
  다음 달로 넘어간다.
- 목표를 비운 달은 판정하지 않는다(그 달에 적은 호기는 다음 달로 넘어간다).

숫자 글자는 원본이 쓰던 JavaScript `toFixed` 와 같게 만든다(`to_fixed`) — 파이썬 `format` 은 정확히
반에 걸린 값(0.125 등)을 짝수 쪽으로 보내 「0.12」 가 되지만 원본은 「0.13」 이다.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from capa_simulation.services.wd_window import WdWindow, wd_window

__all__ = [
    "CHECK_TABLE_COLUMNS",
    "DEFAULT_YEAR",
    "EMPTY_UNITS_MESSAGE",
    "EXAMPLE_BASE_UNITS",
    "EXAMPLE_CUTOFF_DAYS",
    "EXAMPLE_MONTHS",
    "EXAMPLE_YEAR",
    "LEFTOVER_MEMO",
    "MONTHS_PER_YEAR",
    "MONTH_CHECK_HEADER",
    "NO_PASTED_LINES_MESSAGE",
    "PASTE_HINT",
    "UNIT_RESULT_HEADER",
    "UNIT_TABLE_COLUMNS",
    "AssignedUnit",
    "CheckTableRow",
    "LeftoverUnit",
    "MonthCheck",
    "PastedMonths",
    "QualDeadlineInput",
    "QualDeadlineKpis",
    "QualDeadlineResult",
    "QualMonthInput",
    "UnitTableRow",
    "VerdictTone",
    "check_table_rows",
    "cleared_input",
    "compute_qual_deadlines",
    "example_input",
    "format_day",
    "format_short_day",
    "is_example",
    "js_round",
    "js_trim",
    "month_check_rows",
    "parse_number",
    "parse_pasted_months",
    "split_unit_names",
    "tab_separated_text",
    "to_fixed",
    "unit_memo",
    "unit_result_rows",
    "unit_table_rows",
    "verdict",
    "window_label",
]

MONTHS_PER_YEAR = 12
# 연도를 비우면 원본이 쓰던 해다.
DEFAULT_YEAR = 2027
# 모자람이 이보다 크면 호기를 더 꺼낸다(원본 `EPS`). 부족 판정은 아래 `_SHORT_EPS` 로 따로 한다.
_EPS = 1e-9
_SHORT_EPS = 1e-6
_ONE_DAY = timedelta(days=1)

# JavaScript 정규식 `\s` 가 고르는 글자. 파이썬 `\s` 는 `\x1c`~`\x1f`·`\x85` 를 더 고르고 `﻿` 를
# 빠뜨려, 원본과 같은 글을 다르게 자를 수 있다.
_JS_SPACE = "\t\n\v\f\r    -     　﻿"
_UNIT_SEPARATOR = re.compile(f"[{_JS_SPACE},;]+")
_LEADING_SPACE = re.compile(f"^[{_JS_SPACE}]+")
_SPACE_CHARACTER = re.compile(f"[{_JS_SPACE}]")
# 원본 붙여넣기 칸의 줄 나눔(`split(/\r?\n/)`).
_LINE_BREAK = re.compile(r"\r?\n")
# JavaScript `parseFloat` 가 읽는 앞머리 — 부호, `Infinity` 또는 십진수(지수 포함).
_FLOAT_PREFIX = re.compile(r"[+-]?(?:Infinity|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")

VerdictTone = Literal["ok", "warn", "bad"]
CheckState = Literal["skip", "short", "ok"]

# 복사(내려받기) 표의 머리 — 원본의 「호기별 결과 복사」·「월 점검 복사」 첫 줄 그대로다.
UNIT_RESULT_HEADER = ("호기", "쓰이는 달", "그 달 기여", "Qual 완료 마감", "기여 시작")
MONTH_CHECK_HEADER = (
    "월",
    "W/D 시작(다음 날부터)",
    "W/D 끝",
    "목표",
    "기존+앞달",
    "이 달 채움",
    "부족",
)
# 화면 표의 머리 — 원본 표 머리 그대로다.
UNIT_TABLE_COLUMNS = ("호기", "쓰이는 달", "그 달 기여", "Qual 완료 마감", "기여 시작", "메모")
CHECK_TABLE_COLUMNS = (
    "월",
    "W/D 구간",
    "목표",
    "기존 + 앞달 호기",
    "이 달 호기로 채움",
    "판정",
)
EMPTY_UNITS_MESSAGE = "신규 호기를 적으면 여기에 호기별 Qual 마감이 나옵니다."
LEFTOVER_MEMO = "목표를 채우는 데 쓰이지 않음(이 해 목표가 이미 채워짐)"
# 원본 「엑셀에서 한 번에 붙여넣기」 칸의 안내와 「표에 넣기」 알림 글.
PASTE_HINT = "한 줄에 한 달: `목표 가용대수 [탭] 호기들` — 1월부터 12줄. 호기 칸은 비워도 됩니다."
NO_PASTED_LINES_MESSAGE = "붙여넣은 줄이 없습니다."


@dataclass(frozen=True)
class QualMonthInput:
    """한 달의 입력 — 목표 가용대수(비우면 `None`)와 그 달에 새로 붙는 호기 글."""

    target: float | None = None
    units_text: str = ""


@dataclass(frozen=True)
class QualDeadlineInput:
    """계산기 입력 전부. 숫자 칸은 비울 수 있다(`None`) — 원본처럼 Cut-off 는 0, 연도는
    `DEFAULT_YEAR`, 직전 달 가용대수는 0 으로 읽는다. 달은 1월부터이고 12개보다 적으면 나머지는
    빈 달이다."""

    cutoff_days: float | None
    year: float | None
    base_units: float | None
    today: date | None
    months: tuple[QualMonthInput, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AssignedUnit:
    """목표를 채우는 데 쓰인 호기 하나."""

    name: str
    listed_month: int
    """호기를 적은 달."""
    month: int
    """처음 쓰이는 달 — 적은 달이거나 그 뒤다."""
    deadline: date
    """Qual 완료 마감. 이 날 끝내면 다음 날부터 기여한다."""
    part: float
    """쓰이는 달에 보태는 몫(0~1). 1 보다 작으면 그 달 구간 일부만 채우고 다음 달부터 1대다."""

    @property
    def contribution_start(self) -> date:
        """기여를 시작하는 날 — 마감 다음 날."""
        return self.deadline + _ONE_DAY


@dataclass(frozen=True)
class LeftoverUnit:
    """적었지만 그 해 목표를 채우는 데 쓰이지 않은 호기."""

    name: str
    listed_month: int


@dataclass(frozen=True)
class MonthCheck:
    """한 달의 점검 — 목표, 기존 + 앞 달 호기, 이 달 호기로 채운 몫, 남은 부족."""

    month: int
    window: WdWindow
    target: float | None
    carried: float
    """직전 달 가용대수 + 앞 달까지 쓰인 호기의 이 달 몫."""
    added: float
    """이 달에 꺼낸 호기의 몫 합."""
    shortfall: float
    """채우고도 남은 부족(없으면 0). 목표를 비운 달도 0 이다."""
    state: CheckState


@dataclass(frozen=True)
class QualDeadlineKpis:
    """결과 머리의 지표 넷."""

    unit_count: int
    earliest_deadline: date | None
    past_count: int
    short_months: int


@dataclass(frozen=True)
class QualDeadlineResult:
    """계산 결과. 입력을 읽은 값(`cutoff_days` 등)을 함께 둔다 — 글자 서식이 그 값을 쓴다."""

    cutoff_days: int
    year: int
    base_units: float
    today: date | None
    assigned: tuple[AssignedUnit, ...]
    leftover: tuple[LeftoverUnit, ...]
    checks: tuple[MonthCheck, ...]

    def is_past(self, unit: AssignedUnit) -> bool:
        """오늘보다 앞선 마감인가 — 오늘을 비우면 늘 아니다."""
        return self.today is not None and unit.deadline < self.today

    @property
    def kpis(self) -> QualDeadlineKpis:
        return QualDeadlineKpis(
            unit_count=len(self.assigned),
            earliest_deadline=min((unit.deadline for unit in self.assigned), default=None),
            past_count=sum(1 for unit in self.assigned if self.is_past(unit)),
            short_months=sum(1 for check in self.checks if check.state == "short"),
        )


# 원본 예시(2026-10-07 계산기의 `EXAMPLE`). 「예시로 되돌리기」가 이 값으로 돌아간다.
EXAMPLE_CUTOFF_DAYS = 10
EXAMPLE_YEAR = 2027
EXAMPLE_BASE_UNITS = 18.0
EXAMPLE_MONTHS: tuple[QualMonthInput, ...] = (
    QualMonthInput(18.0, ""),
    QualMonthInput(19.0, "U21"),
    QualMonthInput(20.0, "U22"),
    QualMonthInput(20.5, "U23"),
    QualMonthInput(22.0, "U24"),
    QualMonthInput(22.0, ""),
    QualMonthInput(24.0, "U25, U26"),
    QualMonthInput(24.0, ""),
    QualMonthInput(25.0, "U27"),
    QualMonthInput(26.0, "U28"),
    QualMonthInput(26.0, ""),
    QualMonthInput(27.0, "U29"),
)


def example_input(today: date | None) -> QualDeadlineInput:
    """예시 입력. 원본은 만든 날(2026-10-07)을 오늘로 박았고, 앱은 그 자리에 실제 오늘을 넣는다."""
    return QualDeadlineInput(
        cutoff_days=EXAMPLE_CUTOFF_DAYS,
        year=EXAMPLE_YEAR,
        base_units=EXAMPLE_BASE_UNITS,
        today=today,
        months=EXAMPLE_MONTHS,
    )


def cleared_input(current: QualDeadlineInput) -> QualDeadlineInput:
    """「모두 비우기」 — Cut-off·연도·오늘은 두고 직전 달 가용대수와 열두 달을 비운다(원본대로)."""
    return QualDeadlineInput(
        cutoff_days=current.cutoff_days,
        year=current.year,
        base_units=None,
        today=current.today,
        months=tuple(QualMonthInput() for _ in range(MONTHS_PER_YEAR)),
    )


def _padded_months(months: Sequence[QualMonthInput]) -> tuple[QualMonthInput, ...]:
    filled = tuple(months[:MONTHS_PER_YEAR])
    return filled + tuple(QualMonthInput() for _ in range(MONTHS_PER_YEAR - len(filled)))


def _same_number(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is right
    return float(left) == float(right)


def is_example(inputs: QualDeadlineInput, example_today: date | None) -> bool:
    """지금 입력이 예시 그대로인가(「지금 값은 예시입니다」 표지). 오늘은 `example_today` 와
    견준다."""
    example = example_input(example_today)
    return (
        _same_number(inputs.cutoff_days, example.cutoff_days)
        and _same_number(inputs.year, example.year)
        and _same_number(inputs.base_units, example.base_units)
        and inputs.today == example.today
        and all(
            _same_number(mine.target, theirs.target) and mine.units_text == theirs.units_text
            for mine, theirs in zip(
                _padded_months(inputs.months), _padded_months(example.months), strict=True
            )
        )
    )


def split_unit_names(text: str | None) -> list[str]:
    """신규 호기 글을 호기 이름으로 나눈다 — 쉼표·세미콜론·띄어쓰기·줄바꿈(원본 `units`)."""
    return [name for name in _UNIT_SEPARATOR.split(text or "") if name]


def parse_number(value: object) -> float | None:
    """원본 `num` — 숫자면 그대로, 글이면 첫 쉼표 하나를 지우고 JavaScript `parseFloat` 처럼
    앞머리를 읽는다. 못 읽거나 유한하지 않으면 `None`."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    text = _LEADING_SPACE.sub("", str(value).replace(",", "", 1))
    match = _FLOAT_PREFIX.match(text)
    if match is None or "Infinity" in match.group(0):
        return None
    number = float(match.group(0))
    return number if math.isfinite(number) else None


def js_trim(text: str) -> str:
    """JavaScript `String.prototype.trim` — 앞뒤의 `\\s` 글자를 지운다. 파이썬 `strip` 은 고르는
    글자가 달라(`\\x1c`~`\\x1f` 를 지우고 `﻿` 는 남긴다) 원본과 다른 글을 남길 수 있다."""
    text = _LEADING_SPACE.sub("", text)
    end = len(text)
    while end and _SPACE_CHARACTER.fullmatch(text[end - 1]):
        end -= 1
    return text[:end]


@dataclass(frozen=True)
class PastedMonths:
    """붙여넣기 칸을 읽은 결과 — 1월부터 차례로 갈 달(최대 열두 달)과 공백 아닌 줄 수."""

    months: tuple[QualMonthInput, ...]
    line_count: int

    @property
    def message(self) -> str:
        """「표에 넣기」 알림 — 원본 토스트 글자 그대로다."""
        if not self.line_count:
            return NO_PASTED_LINES_MESSAGE
        return f"{min(MONTHS_PER_YEAR, self.line_count)}개월을 넣었습니다."


def parse_pasted_months(text: str | None) -> PastedMonths:
    """원본 「표에 넣기」 — 엑셀에서 복사한 글을 1월부터 한 줄에 한 달로 읽는다.

    공백뿐인 줄은 건너뛰고(엑셀의 두 칸이 다 빈 줄도 — 그 아래 달이 당겨진다) 앞 12줄만 쓴다.
    줄을 탭으로 나눠 첫 칸은 목표 가용대수(`parse_number` — 못 읽으면 비운 달), 둘째 칸부터
    끝까지는 띄어쓰기로 이어 신규 호기 글로 읽는다. 줄이 없는 달은 이 결과에 없다 — 부르는 쪽이
    그 달을 그대로 둔다.
    """
    lines = [line for line in _LINE_BREAK.split(text or "") if js_trim(line)]
    months: list[QualMonthInput] = []
    for line in lines[:MONTHS_PER_YEAR]:
        target, *units = line.split("\t")
        months.append(QualMonthInput(parse_number(js_trim(target)), js_trim(" ".join(units))))
    return PastedMonths(tuple(months), len(lines))


def js_round(value: float) -> int:
    """JavaScript `Math.round` — 반은 양의 무한 쪽으로 올린다(파이썬 `round` 는 짝수 쪽)."""
    floor = math.floor(value)
    return int(floor + 1 if value - floor >= 0.5 else floor)


def to_fixed(value: float, digits: int = 2) -> str:
    """JavaScript `Number.prototype.toFixed` — 이진 값 그대로에서 반은 0 에서 먼 쪽으로 올린다."""
    if value == 0:
        value = 0.0
    quantum = Decimal(1).scaleb(-digits)
    return str(Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP))


def _share(window: WdWindow, deadline: date) -> float:
    """Qual 완료일이 `deadline` 인 호기가 이 구간에 보태는 몫. 다음 날부터 센다."""
    days = (window.boundary_end - max(deadline, window.boundary_start)).days
    return max(0, days) / window.days


@dataclass
class _Queued:
    name: str
    listed_month: int


def compute_qual_deadlines(inputs: QualDeadlineInput) -> QualDeadlineResult:
    """원본 `compute()` 를 그대로 옮긴 계산."""
    cutoff_days = max(0, js_round(inputs.cutoff_days if inputs.cutoff_days is not None else 0))
    year = js_round(inputs.year if inputs.year is not None else DEFAULT_YEAR)
    base_units = float(inputs.base_units) if inputs.base_units is not None else 0.0
    months = _padded_months(inputs.months)

    assigned: list[AssignedUnit] = []
    queue: list[_Queued] = []
    checks: list[MonthCheck] = []
    for month in range(1, MONTHS_PER_YEAR + 1):
        row = months[month - 1]
        window = wd_window(year * 100 + month, cutoff_days)
        queue.extend(_Queued(name, month) for name in split_unit_names(row.units_text))
        # 원본 `reduce` 와 같은 차례로 더한다 — 0 에서 몫을 쌓고 마지막에 직전 달 대수를 더한다.
        carried_shares = 0.0
        for unit in assigned:
            carried_shares += _share(window, unit.deadline)
        carried = base_units + carried_shares
        if row.target is None:
            checks.append(MonthCheck(month, window, None, carried, 0.0, 0.0, "skip"))
            continue
        need = row.target - carried
        added = 0.0
        while need > _EPS and queue:
            queued = queue.pop(0)
            if need >= 1 - _EPS:
                deadline = window.boundary_start
                part = 1.0
            else:
                days = math.ceil(need * window.days - _EPS)
                deadline = window.boundary_end - timedelta(days=days)
                part = days / window.days
            assigned.append(AssignedUnit(queued.name, queued.listed_month, month, deadline, part))
            added += part
            need -= part
        short = need > _SHORT_EPS
        checks.append(
            MonthCheck(
                month,
                window,
                row.target,
                carried,
                added,
                need if short else 0.0,
                "short" if short else "ok",
            )
        )
    return QualDeadlineResult(
        cutoff_days=cutoff_days,
        year=year,
        base_units=base_units,
        today=inputs.today,
        assigned=tuple(assigned),
        leftover=tuple(LeftoverUnit(queued.name, queued.listed_month) for queued in queue),
        checks=tuple(checks),
    )


def format_day(day: date) -> str:
    """`YYYY-MM-DD`."""
    return f"{day.year}-{day.month:02d}-{day.day:02d}"


def format_short_day(day: date) -> str:
    """`MM.DD` — 가장 이른 마감·W/D 구간 글자."""
    return f"{day.month:02d}.{day.day:02d}"


def window_label(window: WdWindow) -> str:
    """`(MM.DD, MM.DD] N일` — 앞 경계는 그 달에 들지 않는다."""
    return (
        f"({format_short_day(window.boundary_start)}, {format_short_day(window.boundary_end)}] "
        f"{window.days}일"
    )


def unit_memo(unit: AssignedUnit, *, past: bool) -> str:
    """호기별 표의 메모 — 일부만 채움 · 적은 달과 쓰인 달이 다름 · 마감이 지남."""
    notes: list[str] = []
    if unit.part < 1 - _EPS:
        notes.append("그 달 일부만 채움, 다음 달부터 1대")
    if unit.listed_month != unit.month:
        notes.append(f"{unit.listed_month}월에 적은 호기 — {unit.month}월에 처음 필요")
    if past:
        notes.append("마감이 이미 지남")
    return " · ".join(notes)


def verdict(check: MonthCheck) -> tuple[str, VerdictTone]:
    """월 점검 판정 칩의 글자와 색 갈래 — 충족(여유)·부족·목표 없음."""
    if check.state == "skip":
        return "목표 없음", "warn"
    if check.state == "short":
        return f"부족 {to_fixed(check.shortfall)}대", "bad"
    assert check.target is not None
    if check.target < check.carried - _SHORT_EPS:
        return f"충족(여유 {to_fixed(check.carried - check.target)})", "ok"
    return "충족", "ok"


@dataclass(frozen=True)
class UnitTableRow:
    """호기별 표 한 줄 — 칸 글자(`UNIT_TABLE_COLUMNS` 차례)와 칠할 갈래."""

    cells: tuple[str, ...]
    past: bool = False
    leftover: bool = False


@dataclass(frozen=True)
class CheckTableRow:
    """월 점검 표 한 줄 — 칸 글자(`CHECK_TABLE_COLUMNS` 차례)와 판정 칩의 색 갈래."""

    cells: tuple[str, ...]
    tone: VerdictTone


def unit_table_rows(result: QualDeadlineResult) -> list[UnitTableRow]:
    """화면의 호기별 표 — 쓰인 호기, 그 뒤 남은 호기. 둘 다 없으면 빈 목록이다(화면이 안내 한
    줄을 쓴다)."""
    rows = [
        UnitTableRow(
            cells=(
                unit.name,
                f"{unit.month}월",
                to_fixed(unit.part),
                format_day(unit.deadline),
                format_day(unit.contribution_start),
                unit_memo(unit, past=result.is_past(unit)),
            ),
            past=result.is_past(unit),
        )
        for unit in result.assigned
    ]
    rows.extend(
        UnitTableRow(
            cells=(unit.name, f"{unit.listed_month}월에 적음", "—", "—", "—", LEFTOVER_MEMO),
            leftover=True,
        )
        for unit in result.leftover
    )
    return rows


def check_table_rows(result: QualDeadlineResult) -> list[CheckTableRow]:
    """화면의 월 점검 표 — 열두 달."""
    rows: list[CheckTableRow] = []
    for check in result.checks:
        text, tone = verdict(check)
        rows.append(
            CheckTableRow(
                cells=(
                    f"{check.month}월",
                    window_label(check.window),
                    "—" if check.target is None else to_fixed(check.target),
                    to_fixed(check.carried),
                    f"+{to_fixed(check.added)}" if check.added else "—",
                    text,
                ),
                tone=tone,
            )
        )
    return rows


def unit_result_rows(result: QualDeadlineResult) -> list[list[str]]:
    """「호기별 결과」 복사 표 — 머리 한 줄 + 쓰인 호기마다 한 줄. 남은 호기는 싣지 않는다
    (원본대로)."""
    rows = [list(UNIT_RESULT_HEADER)]
    rows.extend(
        [
            unit.name,
            f"{result.year}-{unit.month:02d}",
            to_fixed(unit.part),
            format_day(unit.deadline),
            format_day(unit.contribution_start),
        ]
        for unit in result.assigned
    )
    return rows


def month_check_rows(result: QualDeadlineResult) -> list[list[str]]:
    """「월 점검」 복사 표 — 머리 한 줄 + 열두 달. 목표를 비운 달의 목표 칸은 빈칸이다."""
    rows = [list(MONTH_CHECK_HEADER)]
    rows.extend(
        [
            f"{result.year}-{check.month:02d}",
            format_day(check.window.boundary_start),
            format_day(check.window.boundary_end),
            "" if check.target is None else to_fixed(check.target),
            to_fixed(check.carried),
            to_fixed(check.added),
            to_fixed(check.shortfall) if check.shortfall else "0.00",
        ]
        for check in result.checks
    )
    return rows


def tab_separated_text(rows: Sequence[Sequence[str]]) -> str:
    """엑셀에 붙여 넣는 글 — 칸은 탭, 줄은 줄바꿈(원본의 복사 글)."""
    return "\n".join("\t".join(row) for row in rows)
