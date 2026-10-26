# Purpose: 화면 식 글의 검산(적힌 수로 다시 셈)과 식 자리가 formula_text 를 거치는지를 본다.

"""화면 식 글 도우미(`components/formula_text.py`)와 그것을 쓰는 자리.

- **단위** — `equals_mark`·`consistent_digits`·`operand_text`(2회차 기대값 「5 × 120% = 6.00」·
  「42.19 ÷ 42 = 100.5%」·「2 ÷ 1.9389 = 103.2%」 그대로)·`written_value`·`parse_formula`.
- **검산 그물** — 식을 내는 함수마다 값 격자(반올림 경계 x.xx5·x.xx49, 큰 수 54,698.63, 0 근처,
  음수 과부족)로 글을 만들고 `parse_formula` 로 읽어, 적힌 수로 다시 셈한 값이 적힌 결과의
  자릿수에서 같거나 등호가 「≈」 인지 본다. 대상: 공정 Capa 상세 결합 캔버스 풍선 넷·근거 카드
  (① 가정 소요·② 가용·③ 판정·가정 소요·원인), 제약 시뮬레이션 계산표 풍선 셋·고른 달 계산
  다섯 단계, 가용설비 현황 비교 시트 풍선 셋, 표준 목표 로직 분석 식 세 줄(화면 대본 — 페이지
  파일은 import 하지 않는다).
- **AST 가드** — UI 모듈(`app_pages/`·`components/`)에서 두 끼운 값 사이에 연산(` ÷ `·` × `·
  ` − `·` + `)이 있고 등호(또는 등호 자리의 끼운 값)가 값에 붙은 f-string 은 그 함수가
  `formula_text` 를 불러야 한다. 허용 목록은 숫자 없는 식 설명과 인수가 정수라 늘 맞는 식이다.

값 격자는 서식 경계를 찌르는 합성 수다 — 업무 사실이 아니다.
"""

from __future__ import annotations

import ast
import itertools
import re
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from test_constraint_simulation import _run
from test_standard_target_capa_page import LOGIC_SELECTIONS, TEST_SCRIPT

from capa_simulation.components import formula_text
from capa_simulation.components.availability_sheet_canvas import _hover as sheet_hover
from capa_simulation.components.constraint_simulation_figures import (
    ConstraintLabels,
    _downtime_cell,
    _existing_available_cell,
    _need_cell,
    rate_text,
    units_text,
)
from capa_simulation.components.constraint_simulation_view import month_steps
from capa_simulation.components.formula_text import (
    APPROX,
    EQUALS,
    Formula,
    consistent_digits,
    consistent_places,
    equals_mark,
    operand_text,
    parse_formula,
    written_value,
)
from capa_simulation.components.process_capa_canvas import (
    _assumed_change,
    _available_hover,
    _balance_hover,
    _rate_hover,
)
from capa_simulation.components.process_capa_view import (
    _assumed_demand_note,
    _assumed_required_line,
    _cause_note,
    availability_card,
    judgement_card,
)
from capa_simulation.services.availability_sheet import (
    GAP_ROWS,
    ROW_SCHEDULE_AVAILABLE,
    ROW_SCHEDULE_OWNED,
    SHEET_ROWS,
    SheetView,
)
from capa_simulation.services.constraint_simulation import DowntimeShare
from capa_simulation.services.process_capa_detail import LENT_COLUMN
from capa_simulation.services.securement_rate import CAUSE_COLUMN, CAUSE_OWNED_SHORT, OWNED_COLUMN
from capa_simulation.services.securement_threshold import SecurementThresholds

ROOT = Path(__file__).resolve().parents[1]
MINUS = "−"
THRESHOLDS = SecurementThresholds(1.095, 0.995)
LABELS = ConstraintLabels(
    process="TC Bonding",
    process_label="TC Bonding",
    product="HBM라E",
    target_percent=120,
    general_percent=None,
)

# 반올림 경계(x.xx5 · x.xx49 · x.x5 · x.x49)·0 근처·큰 수.
VALUES = (0.0049, 0.005, 0.0151, 0.046, 0.46, 1.005, 1.0049, 2.675, 3.3549, 12.345, 12.3449, 40.24)
LARGE = (44.0, 54.04, 54698.63)
PAIRS = tuple(itertools.product((*VALUES, *LARGE), repeat=2))


def _formulas(text: str) -> list[Formula]:
    """글의 줄(`<br>`·줄바꿈)마다 식을 읽는다 — 식이 아닌 줄은 건너뛴다."""
    found: list[Formula] = []
    for line in re.split(r"<br>|\n", text):
        try:
            found.append(parse_formula(line))
        except ValueError:
            continue
    return found


def _assert_checked(text: str, expected: int) -> None:
    """식이 `expected` 개 읽히고, 모두 적힌 수로 검산되거나 등호가 「≈」 다."""
    formulas = _formulas(text)
    assert len(formulas) == expected, text
    for formula in formulas:
        assert formula.sign == APPROX or formula.holds(), (text, formula.value())


# ================================================================== 단위


def test_equals_mark_compares_the_written_texts() -> None:
    assert equals_mark("2.38", "2.38") == EQUALS == "="
    assert equals_mark("2.39", "2.38") == APPROX == "≈"


def test_consistent_digits_keeps_the_round_two_expectations() -> None:
    """2회차 기대값 그대로 — 맞으면 둘째 자리, 어긋나면 맞는 가장 적은 자릿수, 끝내 못 맞추면
    둘째 자리와 「≈」."""

    def product(value: float) -> tuple[str, str]:
        shown = f"{value * 120 / 100:.2f}"
        digits, sign = consistent_digits(lambda d: f"{round(value, d) * 120 / 100:.2f}", shown)
        return f"{operand_text(value, digits, units_text)} × 120% {sign} {shown}", sign

    assert product(5.0) == ("5 × 120% = 6.00", "=")
    assert product(0.0215)[0] == "0.021 × 120% = 0.03"

    def rate(available: float, demand: float) -> str:
        shown = rate_text(available / demand)
        digits, sign = consistent_digits(
            lambda d: rate_text(round(available, d) / round(demand, d)), shown
        )
        return (
            f"{operand_text(available, digits, units_text)} ÷ "
            f"{operand_text(demand, digits, units_text)} {sign} {shown}"
        )

    assert rate(48 - 5.806451, 42.0) == "42.19 ÷ 42 = 100.5%"
    assert rate(2.0, 1.93889) == "2 ÷ 1.9389 = 103.2%"
    assert consistent_digits(lambda _d: "1", "2") == (2, "≈")


def test_consistent_places_widens_the_fewest_digits_right_first() -> None:
    """인수마다 따로 늘린다 — 더 적는 자리 수의 합이 가장 작게, 같으면 뒤 인수 먼저(표준 목표 로직
    분석 3회차 꼴 「54,698.63 ÷ 1.49386 = 36,615.63」), 끝내 못 맞추면 처음 자리와 「≈」."""

    def recompute(places: tuple[int, ...]) -> str:
        left, right = round(54698.63, places[0]), round(1.49386, places[1])
        return f"{Decimal(str(left)) / Decimal(str(right)):,.2f}"

    shown = f"{54698.63 / 1.49386:,.2f}"
    assert consistent_places(recompute, shown, (2, 2)) == ((2, 5), "=")
    assert consistent_places(lambda places: "x", "y", (2, 1)) == ((2, 1), "≈")
    assert consistent_places(lambda places: "y" if places == (3, 1) else "x", "y", (2, 1)) == (
        (3, 1),
        "=",
    )


def test_operand_text_trims_but_keeps_the_screen_places() -> None:
    assert operand_text(1.93889, 2, units_text) == "1.94"
    assert operand_text(1.93889, 4, units_text) == "1.9389"
    assert operand_text(1.5000001, 4, units_text) == "1.50"
    assert operand_text(40.0000001, 6, units_text) == "40"
    assert operand_text(-0.0215, 4, units_text) == f"{MINUS}0.0215"
    assert operand_text(1234.56789, 3, units_text) == "1,234.568"


def test_written_value_reads_screen_numbers() -> None:
    assert written_value("1,234.5") == 1234.5
    assert written_value(f"{MINUS}0.18") == -0.18
    assert written_value("+1.13") == 1.13
    assert written_value("109%") == pytest.approx(1.09)
    assert written_value("—") is None


@pytest.mark.parametrize(
    ("text", "operands", "operators", "sign", "result"),
    [
        ("HBM라E 필요 대수 = 5 × 120% = 6.00 → **6대**", ("5", "1.2"), ("×",), "=", "6.00"),
        ("27년 6월 몫 6대 × 30/31일 = 5.81", ("6", "30", "31"), ("×", "/"), "=", "5.81"),
        ("기존 가용 = 48 − 5.81 − 6 = **36.19대**", ("48", "5.81", "6"), ("−", "−"), "=", "36.19"),
        (
            "<b>26.12</b> · 확보율 109% ≈ 가용 48.0 ÷ 소요 44.0",
            ("48.0", "44.0"),
            ("÷",),
            "≈",
            "1.09",
        ),
        (
            "과부족 = 48.00 − 44.00×1.095 = −0.18 → −1",
            ("48.00", "44.00", "1.095"),
            ("−", "×"),
            "=",
            "-0.18",
        ),
        ("소요 **142.63대** = 기존 141.26 + HBM3E 1.36", ("141.26", "1.36"), ("+",), "=", "142.63"),
        ("= 54,698.63 ÷ 1.49386 = 36,615.63", ("54698.63", "1.49386"), ("÷",), "=", "36615.63"),
    ],
)
def test_parse_formula_reads_the_screen_forms(
    text: str, operands: tuple[str, ...], operators: tuple[str, ...], sign: str, result: str
) -> None:
    formula = parse_formula(text)
    assert formula.operands == tuple(Decimal(value) for value in operands)
    assert formula.operators == tuple(MINUS if op == "−" else op for op in operators)
    assert formula.sign == sign
    assert formula.result == Decimal(result)


def test_parse_formula_catches_a_written_mismatch() -> None:
    """「3.35 − 0.97 = 2.39」 는 적힌 수로 2.38 이다 — 그물이 잡는 꼴."""
    assert not parse_formula("기존 가용 = 3.35 − 0.97 = 2.39대").holds()
    assert parse_formula("기존 가용 = 3.3549 − 0.9651 = 2.39대").holds()
    with pytest.raises(ValueError):
        parse_formula("가용대수 48.0 (공식)")


# ================================================================== 검산 그물 — 공정 Capa 상세


@pytest.mark.parametrize(("owned", "lent"), PAIRS)
def test_the_canvas_available_balloon_recomputes(owned: float, lent: float) -> None:
    _assert_checked(_available_hover("<b>26.11</b>", owned - lent, owned, lent, False), 1)


@pytest.mark.parametrize(("official", "percent"), itertools.product(VALUES + LARGE, (80, 110, 150)))
def test_the_canvas_assumed_demand_balloon_recomputes(official: float, percent: int) -> None:
    factor = percent / 100
    _assert_checked(_assumed_change(official, official / factor, factor), 1)


@pytest.mark.parametrize(("available", "demand"), PAIRS)
def test_the_canvas_rate_balloon_recomputes(available: float, demand: float) -> None:
    text = _rate_hover(
        "<b>26.11</b>", available / demand, available, demand, "secure", 1.095, 0.995
    )
    # 적힌 소요가 0.0 이면 다시 셀 수 없다 — 그때도 등호가 「≈」 다.
    if round(demand, 1) == 0:
        assert f"{APPROX} 가용" in text
        return
    _assert_checked(text, 1)


@pytest.mark.parametrize(("available", "demand"), PAIRS)
def test_the_canvas_balance_balloon_recomputes(available: float, demand: float) -> None:
    """과부족 풍선 — 첫 줄 괄호의 올림·내림 전 값을 둘째 줄 식(등호 없음)이 낸다. 적힌 수로 다시
    셈해 어긋나면 둘째 줄 앞이 「≈」 다."""
    text = _balance_hover("<b>26.11</b>", -1, available, demand, 1.095, None)
    head, formula_line = text.split("<br>")[:2]
    raw = re.search(r"\(([^)]+)\)$", head)
    assert raw is not None
    expression = formula_line.split(" (부족은")[0]
    if expression.startswith(f"{APPROX} "):
        return
    formula = parse_formula(f"{expression} = {raw.group(1)}")
    assert formula.holds(), (text, formula.value())


@pytest.mark.parametrize(("owned", "lent"), PAIRS)
def test_the_availability_card_recomputes(owned: float, lent: float) -> None:
    record = {OWNED_COLUMN: owned, LENT_COLUMN: lent, "가용대수": owned - lent}
    bridge = {"기존보유": owned, "호기 가용": lent, "가용대수": owned + lent}
    card = availability_card(record, bridge)
    _assert_checked(card.formula, 1)
    _assert_checked("\n".join(card.notes), 1)


@pytest.mark.parametrize(("available", "required"), PAIRS)
def test_the_judgement_card_recomputes(available: float, required: float) -> None:
    record: dict[str, object] = {
        "가용대수": available,
        "소요대수": required,
        "판정": "warning",
        "확보기준 과부족": -1,
        OWNED_COLUMN: available,
        CAUSE_COLUMN: CAUSE_OWNED_SHORT,
    }
    card = judgement_card(record, THRESHOLDS, 202611)
    _assert_checked(card.formula, 2)
    # 원인 줄 「총보유 a ÷ 소요 b = c%」 — 적힌 소요가 0.0 이면 다시 셀 수 없어 「≈」 다.
    cause = _cause_note(record, required)
    if round(required, 1) == 0:
        assert f" {APPROX} " in cause
    else:
        _assert_checked(cause, 1)


@pytest.mark.parametrize(("official", "percent"), itertools.product(VALUES + LARGE, (80, 110, 150)))
def test_the_assumed_demand_lines_recompute(official: float, percent: int) -> None:
    token = (percent, (202611,))
    assumed = official / (percent / 100)
    _assert_checked(_assumed_required_line(official, assumed, token), 1)
    _assert_checked(_assumed_demand_note(official, {"소요대수": assumed}, token), 1)


# ================================================================== 검산 그물 — 제약 시뮬레이션


@pytest.mark.parametrize("demand", VALUES + LARGE)
def test_the_need_balloon_recomputes(demand: float) -> None:
    row = replace(_run().month(202706), constrained_demand=demand)
    cell = _need_cell(row, 120)
    _assert_checked(cell.hover, 1)


@pytest.mark.parametrize(("units", "days", "window"), [(6, 30, 31), (2, 30, 30), (7, 3, 29)])
def test_the_downtime_balloon_has_whole_operands(units: int, days: int, window: int) -> None:
    """비가동 몫 「n대 × d/w일 = 환산」 은 인수가 정수라 늘 적힌 수로 맞는다(가드 허용 목록의
    까닭)."""
    share = DowntimeShare(source_month=202706, units=units, days=days, window_days=window)
    row = replace(_run().month(202705), downtime=share.equivalent, downtime_shares=(share,))
    _assert_checked(_downtime_cell(row).hover, 1)


@pytest.mark.parametrize(
    ("available", "downtime", "allocated"),
    [
        (available, downtime, allocated)
        for available, downtime in itertools.product((3.3549, 48.004, 12.345, 40.24), VALUES)
        if downtime <= available
        for allocated in (0, 6)
    ],
)
def test_the_existing_available_balloon_recomputes(
    available: float, downtime: float, allocated: int
) -> None:
    usable = max(0.0, available - downtime)
    allocated = min(allocated, int(usable))
    row = replace(
        _run().month(202706),
        available=available,
        downtime=downtime,
        usable=usable,
        overdrawn=available - downtime < 0,
        allocated=allocated,
        existing_available=usable - allocated,
    )
    _assert_checked(_existing_available_cell(row).hover, 1)


@pytest.mark.parametrize(("existing", "constrained"), PAIRS)
def test_the_month_steps_recompute(existing: float, constrained: float) -> None:
    """고른 달 계산 1·2·5단계 — 소요 나눔·필요 대수·기존 확보율(자릿수 늘리기 길)."""
    result = _run()
    row = replace(
        result.month(202706),
        required=existing + constrained,
        existing_demand=existing,
        constrained_demand=constrained,
        existing_rate=result.month(202706).existing_available / existing,
    )
    steps = month_steps(row, result, LABELS, show_proportional=False).steps
    _assert_checked(steps[0].body, 1)
    _assert_checked(steps[1].body, 1)
    _assert_checked(steps[4].body, 1)


@pytest.mark.parametrize(
    ("available", "downtime"),
    [
        (available, downtime)
        for available, downtime in itertools.product((3.3549, 48.004, 12.345, 40.24), VALUES)
        if downtime <= available
    ],
)
def test_the_month_step_four_recomputes(available: float, downtime: float) -> None:
    result = _run()
    usable = max(0.0, available - downtime)
    row = replace(
        result.month(202706),
        available=available,
        downtime=downtime,
        usable=usable,
        overdrawn=False,
        allocated=0,
        existing_available=usable,
    )
    _assert_checked(month_steps(row, result, LABELS, show_proportional=False).steps[3].body, 1)


# ================================================================== 검산 그물 — 가용설비 현황


def _sheet(value: float, first: float, second: float) -> SheetView:
    """한 달 시트 — 설비 일정 보유 = `value`, 기존보유 = `first`, 가용 = 보유 + 대여(`second`),
    GAP 은 설비 일정 − Static(Static 은 `first`)."""
    month = 202611
    cells = {
        "static:owned": first,
        "static:lent": -second,
        "static:available": first - second,
        ROW_SCHEDULE_OWNED: value,
        "sched:lent": -second,
        ROW_SCHEDULE_AVAILABLE: value - second,
    }
    for gap, (schedule, static) in zip(
        GAP_ROWS,
        (
            ("sched:owned", "static:owned"),
            ("sched:lent", "static:lent"),
            ("sched:available", "static:available"),
        ),
        strict=True,
    ):
        cells[gap] = cells[schedule] - cells[static]
    values = pd.DataFrame({month: [cells[row] for row in SHEET_ROWS]}, index=list(SHEET_ROWS))
    return SheetView(months=(month,), values=values, baseline=pd.Series([first], index=[month]))


@pytest.mark.parametrize(("value", "other"), PAIRS)
def test_the_sheet_balloons_recompute(value: float, other: float) -> None:
    view = _sheet(value + 0.0004, other, other / 3)
    owned = sheet_hover(view, ROW_SCHEDULE_OWNED, 202611, "<b>26.11</b>")
    # 「보유 X (환산대수)<br>= 기존보유 a + 호기 b」 — 결과가 앞 줄에 있다.
    first, second = owned.split("<br>")[:2]
    mark, expression = second.split(" ", 1)
    if mark != APPROX:
        formula = parse_formula(f"{first.split(' 보유 ')[1].split(' (')[0]} {mark} {expression}")
        assert formula.holds(), owned
    _assert_checked(sheet_hover(view, ROW_SCHEDULE_AVAILABLE, 202611, "<b>26.11</b>"), 1)
    for gap in GAP_ROWS:
        _assert_checked(sheet_hover(view, gap, 202611, "<b>26.11</b>"), 1)


# ================================================================== 검산 그물 — 표준 목표 로직 분석


@pytest.mark.parametrize(
    ("load", "required", "available"),
    [(54698.63, 1.49386, 40.0), (100.0, 1.005, 2.0), (12.3449, 0.046, 3.0), (2.675, 0.0049, 1.0)],
)
def test_the_logic_analysis_lines_recompute(load: float, required: float, available: float) -> None:
    """로직 분석 식 세 줄(대당 Capa · 대당 일 Capa · 일 표준 가능량)도 적힌 수로 검산되거나 「≈」 다
    (`standard_target_capa.logic_formula_text` — 화면 대본으로 그린다)."""
    script = (
        TEST_SCRIPT.replace('"부하량": [100.0],', f'"부하량": [{load!r}],')
        .replace('"소요대수": [1.0],', f'"소요대수": [{required!r}],')
        .replace('"가용대수": [2.0] * 5,', f'"가용대수": [{available!r}] * 5,')
    )
    # 화면의 키 전용 캐시는 프로세스 전역이고 대본은 토큰 하나라 앞 값이 적중하지 않게 비운다.
    st.cache_data.clear()
    app = AppTest.from_string(script, default_timeout=60).run()
    app = app.segmented_control(key="standard_target_output_metric").set_value("로직 분석").run()
    for key, value in LOGIC_SELECTIONS.items():
        app = app.selectbox(key=key).set_value(value).run()
    assert not app.exception
    (code,) = app.code
    _assert_checked(str(code.value), 3)
    st.cache_data.clear()


# ================================================================== AST 가드

_UI_GLOBS = ("app_pages/*.py", "src/capa_simulation/components/*.py")
# 두 끼운 값 사이의 연산(끼운 값이 없는 글자만 사이에 둔다) — 「{} ÷ {}」·「{}×{}」.
_OPERATOR = re.compile(r"\{\}[^{}]*?(?: [÷×−+] |×)[^{}]*?\{\}")
# 값에 붙은 등호 — 「= {}」·「{} =」·「≈」, 또는 등호 자리의 끼운 값(「{} {mark} {}」).
_RELATION = re.compile(r"[=≈] \{\}|\{\} [=≈]|≈|\{\} \{\} ")
_MINUS_NAMES = frozenset({"MINUS", "_MINUS"})

# (파일, 함수) → 까닭. 식 꼴이지만 검산할 숫자가 없거나 늘 맞는 자리.
ALLOWED: dict[tuple[str, str], str] = {
    ("src/capa_simulation/components/constraint_simulation_figures.py", "_downtime_cell"): (
        "인수가 정수(대수 × 겹친 일수 ÷ W/D 일수)라 늘 적힌 수로 맞는다 — 검산 그물이 본다"
    ),
}
# 다른 주제가 같은 파일을 고치는 중이라 이번에 손대지 않은 자리 — 그 병합 뒤 고친다(docs/TODO.md).
PENDING: dict[tuple[str, str], str] = {
    ("src/capa_simulation/components/availability_gap_panel.py", "_render_static_evidence"): (
        "보유 + 대여 = 합 · 기준정보 가용"
    ),
    ("src/capa_simulation/components/availability_gap_panel.py", "_render_gap_evidence"): (
        "GAP = 설비 일정 − Static = 값"
    ),
    ("src/capa_simulation/components/availability_gap_panel.py", "_render_schedule_evidence"): (
        "설비 일정 기준 가용 = 보유 + 대여(비가동)"
    ),
}


def _template(node: ast.JoinedStr) -> str:
    """f-string 의 꼴 — 끼운 값은 「{}」, 빼기 글자 상수(`MINUS`)는 「−」."""
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        elif isinstance(value, ast.FormattedValue) and (
            isinstance(value.value, ast.Name) and value.value.id in _MINUS_NAMES
        ):
            parts.append(MINUS)
        else:
            parts.append("{}")
    return "".join(parts)


def _formula_names(tree: ast.Module) -> frozenset[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == formula_text.__name__:
            names.update(alias.asname or alias.name for alias in node.names)
    return frozenset(names)


def _calls_helper(function: ast.AST, names: frozenset[str]) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in names:
            return True
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "formula_text":
                return True
    return False


def unchecked_formulas(source: str, path: str) -> list[tuple[str, str, int]]:
    """식 꼴 f-string 이 있는데 `formula_text` 를 부르지 않는 함수 — (파일, 함수, 줄)."""
    tree = ast.parse(source)
    names = _formula_names(tree)
    found: list[tuple[str, str, int]] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        inner = {
            id(node)
            for child in ast.walk(function)
            if child is not function and isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            for node in ast.walk(child)
        }
        for node in ast.walk(function):
            if id(node) in inner or not isinstance(node, ast.JoinedStr):
                continue
            template = _template(node)
            if _OPERATOR.search(template) and _RELATION.search(template):
                if not _calls_helper(function, names):
                    found.append((path, function.name, node.lineno))
                break
    return found


def _ui_findings() -> list[tuple[str, str, int]]:
    findings: list[tuple[str, str, int]] = []
    for pattern in _UI_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.name == "formula_text.py":
                continue
            relative = path.relative_to(ROOT).as_posix()
            findings += unchecked_formulas(path.read_text(encoding="utf-8"), relative)
    return findings


def test_every_screen_formula_goes_through_formula_text() -> None:
    """식 글을 짓는 함수는 `formula_text` 로 등호나 인수를 고른다 — 적힌 수로 검산되게
    (AGENTS 8장)."""
    findings = [
        finding
        for finding in _ui_findings()
        if (finding[0], finding[1]) not in ALLOWED and (finding[0], finding[1]) not in PENDING
    ]
    assert findings == []


def test_the_allow_and_pending_lists_are_not_stale() -> None:
    """허용·대기 목록의 자리는 아직 식 꼴이고 `formula_text` 를 부르지 않는다 — 고쳤으면 목록에서
    뺀다."""
    places = {(path, function) for path, function, _line in _ui_findings()}
    assert set(ALLOWED) <= places
    assert set(PENDING) <= places


def test_the_guard_flags_an_unchecked_formula() -> None:
    source = (
        "def hover(a, b):\n"
        "    return f'가용 {a:.1f} ÷ 소요 {b:.1f} = {a / b:.0%}'\n"
        "def sized(w, h):\n"
        "    return f'캔버스 {w:g} × {h:g}'\n"
        "def checked(a, b):\n"
        "    mark = equals_mark('x', 'y')\n"
        "    return f'가용 {a} − 대여 {b} {mark} {a - b}'\n"
    )
    source = "from capa_simulation.components.formula_text import equals_mark\n" + source
    assert unchecked_formulas(source, "x.py") == [("x.py", "hover", 3)]
