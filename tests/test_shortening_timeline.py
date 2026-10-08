# Purpose: 진척 비교 카드의 달 축이 두 시점 날짜를 덮도록 넓어지고 공정 카드 축은 그대로인지 본다.

"""진척 비교의 넓힌 달 축(2026-10-08 사용자 결정 「넓히기」).

진척 비교 카드는 지금 조회 달 위에 기준선(과거)과 지금(현재) 두 줄을 그린다. 조회 기간을 바꾼 뒤
기준선 날짜가 그 달 밖이면 표식이 양 끝(0%·100%)에 잘려 붙었다. 이제 비교 화면은 조회 달을 보이는
카드의 날짜가 모두 들도록 앞뒤로 넓힌 **한 축**을 모든 카드가 함께 쓴다. `비교 안 함` 의 공정 카드는
고른 달 그대로다.
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
from test_shortening_progress import _frame, _real

from capa_simulation.components.required_shortening_panel import _units_markup
from capa_simulation.components.shortening_progress_panel import (
    progress_card_markup,
    progress_view,
)
from capa_simulation.components.shortening_timeline import (
    timeline_axis,
    timeline_months_covering,
    timeline_position,
)
from capa_simulation.services.required_shortening import KIND_SHORTENED
from capa_simulation.services.shortening_progress import compare_progress

EARLY = "DEMO_EARLY"
INSIDE = "DEMO_INSIDE"
MONTHS = [202606, 202607, 202608]


def _rows(past: pd.DataFrame, current: pd.DataFrame, *, today: date) -> pd.DataFrame:
    return compare_progress(past, current, current_processes=[EARLY, INSIDE], today=today)


def _axis_labels(markup: str) -> list[str]:
    head = markup.split('<div class="shk-axis">', 1)[1].split("</div>", 1)[0]
    return re.findall(r">(\d\d\.\d\d)</span>", head)


def test_a_baseline_date_before_the_window_sits_inside_the_widened_axis() -> None:
    """기준선의 필요·확보 시점이 지금 조회 달보다 앞이면 축이 그 달까지 앞으로 넓어진다 — 표식이
    0% 에 잘려 붙지 않고 제자리에 선다. 오늘도 넓힌 축 안이면 점선이 선다(지금 조회 달 밖이어도)."""
    today = date(2026, 3, 1)
    past_need = date(2026, 3, 10)
    past = _frame([_real(EARLY, "SMP-E-01", past_need, date(2026, 4, 20))])
    current = _frame([_real(EARLY, "SMP-E-01", date(2026, 6, 10), date(2026, 7, 5))])

    view = progress_view(
        _rows(past, current, today=today),
        ordered=[EARLY, INSIDE],
        scope=[EARLY, INSIDE],
        selected=False,
        months=MONTHS,
    )

    assert view.axis_months == (202603, 202604, 202605, *MONTHS)
    axis = timeline_axis(view.axis_months)
    left = timeline_position(past_need, axis)
    assert 0 < left < 100
    markup = progress_card_markup(EARLY, EARLY, None, view, today=today)
    assert _axis_labels(markup) == ["26.03", "26.04", "26.05", "26.06", "26.07", "26.08"]
    # 과거 줄의 선은 필요 시점에서 시작한다 — 옛 축이면 0.000% 였다.
    assert f"left:{left:.3f}%;width:" in markup
    assert (
        f'<span class="shk-today" title="오늘" style="left:{timeline_position(today, axis):.3f}%">'
        in markup
    )


def test_every_card_in_the_view_shares_one_widened_axis() -> None:
    """한 공정의 날짜만 조회 달 밖이어도 모든 카드가 같은 축을 쓴다 — 카드끼리 같은 날이 같은
    자리다. 뒤로 넓히는 것도 같다(현재 확보 시점이 조회 달 뒤)."""
    today = date(2026, 1, 1)
    past = _frame(
        [
            _real(EARLY, "SMP-E-01", date(2026, 4, 2), date(2026, 6, 1)),
            _real(INSIDE, "SMP-I-01", date(2026, 6, 5), date(2026, 7, 1)),
        ]
    )
    current = _frame(
        [
            _real(EARLY, "SMP-E-01", date(2026, 6, 15), date(2026, 10, 3)),
            _real(INSIDE, "SMP-I-01", date(2026, 6, 20), date(2026, 7, 10)),
        ]
    )

    view = progress_view(
        _rows(past, current, today=today),
        ordered=[EARLY, INSIDE],
        scope=[EARLY, INSIDE],
        selected=False,
        months=MONTHS,
    )

    assert view.cards == (EARLY, INSIDE)
    assert view.axis_months == (202604, 202605, *MONTHS, 202609, 202610)
    labels = [
        _axis_labels(progress_card_markup(process, process, None, view, today=today))
        for process in view.cards
    ]
    assert labels[0] == labels[1] == ["26.04", "26.05", "26.06", "26.07", "26.08", "26.09", "26.10"]


def test_the_axis_widens_only_for_the_cards_on_screen() -> None:
    """공정을 고르면 고른 공정만 카드다 — 고르지 않은 공정의 날짜로는 축을 넓히지 않는다."""
    today = date(2026, 1, 1)
    past = _frame(
        [
            _real(EARLY, "SMP-E-01", date(2026, 2, 2), date(2026, 3, 1)),
            _real(INSIDE, "SMP-I-01", date(2026, 6, 5), date(2026, 7, 1)),
        ]
    )
    current = _frame([_real(INSIDE, "SMP-I-01", date(2026, 6, 20), date(2026, 7, 10))])

    view = progress_view(
        _rows(past, current, today=today),
        ordered=[EARLY, INSIDE],
        scope=[INSIDE],
        selected=True,
        months=MONTHS,
    )

    assert view.cards == (INSIDE,)
    assert view.axis_months == tuple(MONTHS)


def test_dates_inside_the_window_keep_the_query_months() -> None:
    """두 시점의 날짜가 모두 조회 달 안이면 축은 조회 달 그대로다 — 넓히기 전과 같은 카드다."""
    today = date(2026, 1, 1)
    past = _frame([_real(INSIDE, "SMP-I-01", date(2026, 6, 5), date(2026, 7, 1))])
    current = _frame([_real(INSIDE, "SMP-I-01", date(2026, 6, 20), date(2026, 8, 31))])

    view = progress_view(
        _rows(past, current, today=today),
        ordered=[EARLY, INSIDE],
        scope=[EARLY, INSIDE],
        selected=False,
        months=MONTHS,
    )

    assert view.axis_months == tuple(MONTHS)
    assert timeline_months_covering(MONTHS, [None, date(2026, 7, 1)]) == tuple(MONTHS)
    assert timeline_months_covering([], [date(2026, 7, 1)]) == ()


def test_the_axis_widens_across_a_year_boundary() -> None:
    assert timeline_months_covering([202601], [date(2025, 11, 30), date(2026, 2, 1)]) == (
        202511,
        202512,
        202601,
        202602,
    )


def test_the_plain_shortening_card_keeps_the_selected_months() -> None:
    """`비교 안 함` 의 공정 카드는 그대로다 — 고른 달만 축이고, 축 밖의 기존 Qual 은 끝(100%)에
    선다."""
    units = pd.DataFrame(
        [
            {
                "호기": "SMP-P-01",
                "구분": KIND_SHORTENED,
                "기존 Qual": date(2026, 11, 10),
                "목표 Qual": date(2026, 7, 10),
                "단축일수": 123,
                "늘어난 환산대수": 1.0,
                "모듈 수": 1,
                "해소 기여 월": "26.07",
            }
        ]
    )

    markup = _units_markup(units, MONTHS, today=date(2026, 1, 1), short=True)

    assert _axis_labels(markup) == ["26.06", "26.07", "26.08"]
    assert "left:calc(100.000% - " in markup
