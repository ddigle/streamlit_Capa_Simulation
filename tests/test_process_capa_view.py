# Purpose: 공정 Capa 상세 본문(근거 카드·KPI 글·범례·그림 기억·칸 선택 콜백)의 규칙을 고정한다.

"""공정 Capa 상세 본문 프래그먼트의 순수 조각(`components/process_capa_view.py`).

화면 전체는 `tests/test_process_capa_detail_page.py` 가 본다. 여기서는 숫자를 넣은 식(근거 카드)·
KPI 글·범례·그림 기억·콜백을 하나씩 고정한다. 재료는 결합 캔버스 시험의 합성 공정
(`tests/test_process_capa_canvas.py`)이다.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_process_capa_canvas import (
    MONTHS,
    THRESHOLDS,
    TODAY,
    _assumed_summary,
    _dynamic,
    _summary,
)
from test_required_shortening import PROCESS

from capa_simulation.components.process_capa_canvas import (
    SECTION_DOWNTIME,
    SECTION_IDS,
    SECTION_SUMMARY,
    SECTION_UNITS,
    DynamicCanvasInput,
)
from capa_simulation.components.process_capa_view import (
    CANVAS_MEMO_LIMIT,
    ENTRY_SECTIONS,
    DynamicView,
    NextScreens,
    Prescription,
    ProcessDetailView,
    availability_card,
    canvas_legend_html,
    canvas_memo_key,
    cause_summary,
    contributing_units,
    demand_card,
    evidence_cards,
    evidence_cards_html,
    initial_scroll_px,
    judgement_card,
    kpi_next_screens,
    month_next_screens,
    prescription,
    prescription_text,
    production_month_example,
    schedule_short_month,
    short_target_text,
    shortening_card,
    target_text,
)
from capa_simulation.design import theme
from capa_simulation.process_detail_state import FROM_GAP, FROM_HOME, FROM_SHORTENING
from capa_simulation.services.process_capa_detail import (
    CAUSE_AVAILABILITY_MISMATCH,
    MISMATCH_COLUMN,
    ProcessCapaKpis,
    build_process_capa_summary,
)
from capa_simulation.services.process_equipment_timeline import ROW_SHORTENED, ROW_VIRTUAL
from capa_simulation.services.required_shortening import (
    STATUS_MET,
    MonthlyTarget,
)
from capa_simulation.services.securement_rate import CAUSE_COLUMN, CAUSE_OWNED_SHORT
from capa_simulation.services.securement_threshold import SecurementThresholds

MINUS = "−"


@pytest.fixture(autouse=True)
def _light_theme() -> Iterator[None]:
    theme._LOCAL.mode = "light"
    yield
    theme._LOCAL.mode = "light"


def _record(summary: pd.DataFrame, month: int) -> dict[str, object]:
    row = summary.loc[summary["생산계획년월"].eq(month)].iloc[0]
    return {str(key): value for key, value in row.items()}


def _view(dynamic: DynamicView | None = None, **changes: object) -> ProcessDetailView:
    values: dict[str, object] = {
        "process": PROCESS,
        "process_label": PROCESS,
        "months": tuple(MONTHS),
        "summary": _summary(),
        "thresholds": THRESHOLDS,
        "scenario_key": (1, "token", MONTHS[0], MONTHS[-1]),
        "display_order_key": "order",
        "scenario_tables": {},
        "reference_tables": {},
        "display_order": None,
        "dynamic": dynamic,
    }
    values.update(changes)
    return ProcessDetailView(**values)  # type: ignore[arg-type]


def _dynamic_view() -> DynamicView:
    canvas = _dynamic()
    return DynamicView(canvas=canvas, units=_plan_units(canvas), memo_key=("plan", "timeline"))


def _plan_units(canvas: DynamicCanvasInput) -> pd.DataFrame:
    events = canvas.unit_events
    kinds = {ROW_SHORTENED: "단축", ROW_VIRTUAL: "신규"}
    rows = events.loc[events["줄"].isin(list(kinds))]
    return pd.DataFrame({"공정": PROCESS, "호기": rows["호기"], "구분": rows["줄"].map(kinds)})


# ------------------------------------------------------------------ 근거 카드


def test_the_judgement_card_writes_both_formulas_with_the_month_threshold() -> None:
    summary = _summary()
    month = 202703
    record = _record(summary, month)
    card = judgement_card(record, THRESHOLDS, month)

    available, required = float(record["가용대수"]), float(record["소요대수"])  # type: ignore[arg-type]
    assert card.title == "③ 판정"
    assert (
        f"확보율 = {available:,.2f} ÷ {required:,.2f} = {available / required:.1%}" in card.formula
    )
    assert f"{required:,.2f}×1.095" in card.formula
    assert card.formula.endswith(f"{MINUS}{abs(int(record['확보기준 과부족'])):,}")  # type: ignore[call-overload]
    assert "확보기준 110% (1.095) · 경고기준 100% (0.995)" in card.notes
    assert any(note.startswith("원인: ") for note in card.notes)


def test_a_month_threshold_exception_reaches_the_card() -> None:
    thresholds = SecurementThresholds(1.095, 0.995, monthly=((202703, 1.2, 1.0),))
    summary = _summary(thresholds=thresholds)
    card = judgement_card(_record(summary, 202703), thresholds, 202703)

    assert "×1.2 " in card.formula
    assert "확보기준 120% (1.2)" in card.notes[0]


def test_a_painted_zero_on_the_noise_boundary_is_explained() -> None:
    """판정은 반올림하지 않은 확보율로, 과부족은 9자리 반올림으로 낸다 — 경계에서 칠한 칸에 0 이
    찍힐 수 있다(검증 정정 1). 카드가 그 까닭을 한 줄로 적는다."""
    thresholds = SecurementThresholds(1.095, 0.995)
    rate = pd.DataFrame(
        {
            "생산계획년월": [202611],
            "공정": [PROCESS],
            "가용대수": [10.95],
            "소요대수": [10.000000000000002],
            "확보율": [10.95 / 10.000000000000002],
        }
    )
    owned = pd.DataFrame({"생산계획년월": [202611], "공정": [PROCESS], "설비보유": [10.95]})
    lent = pd.DataFrame({"생산계획년월": [202611], "공정": [PROCESS], "설비대여평가": [0.0]})
    summary = build_process_capa_summary(
        rate, owned, lent, process=PROCESS, months=[202611], thresholds=thresholds
    )
    card = judgement_card(_record(summary, 202611), thresholds, 202611)

    assert "→ 경고" in card.formula
    assert card.formula.endswith("→ 0")
    assert any("잡음 경계" in note for note in card.notes)


@pytest.mark.parametrize(
    ("available", "required"),
    [(4.0, 2.9), (4.0, 2.8867), (4.0, 3.6544), (52.0, 52.6), (3.0, 2.8967)],
)
def test_the_judgement_formula_can_be_checked_by_hand(available: float, required: float) -> None:
    """식의 숫자는 둘째 자리다. 적은 숫자로 다시 셈한 값이 결과와 같으면 「=」, 다르면 「≈」 —
    「4.0 ÷ 3.7 = 107.0%」 처럼 검산이 어긋난 등호를 쓰지 않는다."""
    record = {
        "가용대수": available,
        "소요대수": required,
        "판정": "warning",
        "확보기준 과부족": -1,
    }
    rate_line, balance_line = judgement_card(record, THRESHOLDS, 202611).formula.split("\n")

    shown_available, shown_required = round(available, 2), round(required, 2)
    assert rate_line.startswith(f"확보율 = {shown_available:,.2f} ÷ {shown_required:,.2f} ")
    rate_text = f"{available / required:.1%}"
    exact = f"{shown_available / shown_required:.1%}" == rate_text
    assert f" {'=' if exact else '≈'} {rate_text} " in rate_line

    def signed_two(value: float) -> str:
        rounded = round(value, 2) + 0.0
        if rounded == 0:
            return "0.00"
        return f"{'+' if rounded > 0 else MINUS}{abs(rounded):,.2f}"

    raw_text = signed_two(available - required * 1.095)
    exact = signed_two(shown_available - shown_required * 1.095) == raw_text
    assert f" {'=' if exact else '≈'} {raw_text} → " in balance_line


def test_a_month_without_demand_is_not_judged() -> None:
    record = {"가용대수": 3.0, "소요대수": 0.0, "판정": None}
    card = judgement_card(record, THRESHOLDS, 202611)
    assert card.formula == "소요 없음 — 판정하지 않습니다"


def test_the_availability_card_warns_on_a_mismatch_and_adds_the_schedule_reference() -> None:
    record = _record(_summary(), 202611)
    record[MISMATCH_COLUMN] = True
    bridge = {"기존보유": 44.0, "호기 가용": 3.5, "가용대수": 47.5}
    card = availability_card(record, bridge)

    assert card.formula.startswith("보유 52.0 − 대여 4.0 = 48.0")
    assert "가용대수 48.0 (공식)" in card.formula
    assert any(note.startswith("⚠") for note in card.notes)
    assert "설비 일정 기준(참고): 기존보유 44.0 + 호기 3.5 = 47.5 (환산)" in card.notes


def test_the_demand_card_falls_back_without_a_trace() -> None:
    card = demand_card(None, _record(_summary(), 202611))
    assert "= 41.2 대" in card.formula
    assert card.notes


def test_the_shortening_card_stands_only_when_the_month_is_not_met() -> None:
    dynamic = _dynamic_view()
    months = dynamic.canvas.process_months
    states = dict(zip(months["생산계획년월"].astype(int), months["상태"], strict=True))
    met = [month for month, state in states.items() if state == STATUS_MET]
    unmet = [month for month, state in states.items() if state != STATUS_MET]
    assert met and unmet
    assert shortening_card(dynamic, met[0]) is None
    card = shortening_card(dynamic, unmet[0])
    assert card is not None and card.reference
    # 필요 단축 일정 탭의 110% 는 1.10 이다 — 이 화면은 소수를 함께 적는다.
    assert card.title == "④ 단축 근거 (설비 일정 · 목표 110% (1.095))"
    assert card.formula.startswith("목표 ")
    head = card.formula.split("\n")[0]
    assert " × 1.095" in head and ("=" in head or "≈" in head)
    assert "구간 " in card.formula and "바닥 " in card.formula
    assert "→ 단축 후 " in card.formula
    assert any(note.startswith("상태: ") for note in card.notes)


def test_contributing_units_list_the_shortened_and_new_units_of_that_month() -> None:
    events = pd.DataFrame(
        [
            {
                "줄": ROW_SHORTENED,
                "호기": "EQ-23",
                "Qual일정": date(2027, 2, 26),
                "목표 Qual": date(2027, 2, 8),
                "단축일수": 18,
                "늘어난 환산대수": 1.6,
                "월별 늘어난 환산대수": ((202702, 1.6), (202703, 0.4)),
                "대상 월": 202702,
                "해소 기여 월": (202702, 202703),
                "반입 전": False,
            },
            {
                "줄": ROW_VIRTUAL,
                "호기": "추가1",
                "Qual일정": None,
                "목표 Qual": date(2027, 2, 10),
                "단축일수": None,
                "늘어난 환산대수": 0.5,
                "월별 늘어난 환산대수": ((202702, 0.5), (202703, 1.0)),
                "대상 월": 202702,
                "해소 기여 월": (),
                "반입 전": False,
            },
            {
                "줄": ROW_SHORTENED,
                "호기": "EQ-30",
                "Qual일정": date(2027, 5, 1),
                "목표 Qual": date(2027, 4, 1),
                "단축일수": 30,
                "늘어난 환산대수": 1.0,
                "월별 늘어난 환산대수": ((202704, 1.0),),
                "대상 월": 202704,
                "해소 기여 월": (202704,),
                "반입 전": True,
            },
        ]
    )
    lines = contributing_units(events, 202702, today=TODAY)
    assert lines == [
        f"→ EQ-23 27.02.26→27.02.08 ({MINUS}18일, +1.60)",
        "→ 추가1 신규 필요 Qual 27.02.10 (+0.50)",
    ]
    assert contributing_units(events, 202704, today=date(2027, 1, 1))[0].endswith("· 반입 전")
    # 대상 월 뒤의 달은 대상 월 몫(+1.60)이 아니라 그 달 몫을 적는다.
    assert contributing_units(events, 202703, today=TODAY) == [
        f"→ EQ-23 27.02.26→27.02.08 ({MINUS}18일, +0.40)"
    ]


def test_the_shortening_card_unit_gains_add_up_to_the_month_after_shortening() -> None:
    """④ 단축 근거의 「가용 → 호기 +x … → 단축 후」 는 그 달 식이다 — 호기 줄 증분의 합이 단축 후 −
    가용과 맞아야 한다(소수 둘째 자리 반올림 차이만). 앞 달에 당겨 뒤 달을 메운 호기가 대상 월 몫을
    적으면 어긋난다(E2E 2026-10-26 — 27.01 4.00→5.50 인데 +0.05)."""
    dynamic = _dynamic_view()
    months = dynamic.canvas.process_months
    checked = 0
    for record in months.to_dict("records"):
        month = int(record["생산계획년월"])
        card = shortening_card(dynamic, month)
        if card is None:
            continue
        gains = [
            float(line.rsplit("+", 1)[1].split(")")[0])
            for line in card.formula.split("\n")
            if line.startswith("→ ") and not line.startswith("→ 단축 후")
        ]
        before, after = float(record["가용대수"]), float(record["단축후가용대수"])
        assert gains, month
        assert sum(gains) == pytest.approx(after - before, abs=0.005 * len(gains) + 1e-9), month
        checked += 1
    assert checked >= 3


def test_evidence_cards_escape_their_text() -> None:
    from capa_simulation.components.process_capa_view import EvidenceCard

    html = evidence_cards_html([EvidenceCard("① 소요", "<b>1</b>", ("A&B",), reference=True)])
    assert "&lt;b&gt;1&lt;/b&gt;" in html
    assert "A&amp;B" in html
    assert 'class="pcd-card ref"' in html
    # 서식은 표시 HTML 과 한 덩어리다 — 스타일만 든 html(이벤트 칸)이 아니다.
    assert html.startswith("<style>") and '<div class="pcd-cards">' in html


# ------------------------------------------------------------------ KPI 글


def _kpis(**changes: int) -> ProcessCapaKpis:
    values = {
        "lowest_rate": 0.98,
        "lowest_rate_month": 202703,
        "shortage_months": 5,
        "max_shortage": 6,
        "owned_short_months": 1,
        "rental_months": 4,
        "mismatch_months": 0,
    }
    values.update(changes)
    return ProcessCapaKpis(**values)  # type: ignore[arg-type]


def test_the_cause_summary_names_only_the_causes_that_occurred() -> None:
    plan = Prescription(shortened=3, new=1, unresolved_months=0, dynamic_short_months=2)
    assert cause_summary(_kpis(), plan) == "보유 1 · 대여 4 · 일정 2"
    assert cause_summary(_kpis(owned_short_months=0, rental_months=0), None) == "없음"
    assert cause_summary(_kpis(owned_short_months=0, rental_months=0, mismatch_months=2), None) == (
        "불일치 2"
    )


def _kpi_row_app() -> None:
    from test_process_capa_canvas import THRESHOLDS
    from test_process_capa_view import _kpis

    from capa_simulation.components.process_capa_view import render_process_kpis

    render_process_kpis(_kpis(), thresholds=THRESHOLDS, dynamic=None, absent_reason="일정 없음")


def test_the_shortage_caption_keeps_its_negation_in_the_help() -> None:
    """KPI 회색 줄은 좁은 창에서 끝이 말줄임으로 잘린다. 「확보기준 미달」 이 「월 최대 −6대 ·
    기간 합 아님」 이던 때 1024px 창에서 「… 기간 합…」 만 남아 기간 합으로 읽혔다 — 회색 줄은
    월 최대 대수만 두고 「기간 합이 아닙니다」 는 `?` 풍선에 둔다."""
    app = AppTest.from_function(_kpi_row_app).run()

    assert not app.exception
    shortage = next(metric for metric in app.metric if metric.label == "확보기준 미달")
    assert shortage.proto.delta == f"월 최대 {MINUS}6대"
    assert "기간 합이 아닙니다" in shortage.proto.help


def test_the_prescription_text_reads_the_plan() -> None:
    assert prescription_text(None) == "일정 없음"
    assert prescription_text(Prescription(3, 1, 0, 2)) == "단축 3대 · 신규 1대"
    assert prescription_text(Prescription(0, 0, 0, 0)) == "목표 충족"
    assert prescription_text(Prescription(0, 0, 2, 2)) == "기한 지남"


def test_the_prescription_counts_this_process_plan() -> None:
    dynamic = _dynamic_view()
    plan = prescription(dynamic)
    kinds = dynamic.units["구분"].tolist()
    assert plan.shortened == kinds.count("단축")
    assert plan.new == kinds.count("신규")
    gaps = pd.to_numeric(dynamic.canvas.process_months["과부족"]).round(9)
    assert plan.dynamic_short_months == int(gaps.lt(0).sum())


def test_the_schedule_cause_skips_months_before_today() -> None:
    """지난 달(오늘이 든 생산월 앞)은 단축으로 바꿀 수 없다 — KPI 「일정」 은 그 달을 세지
    않는다."""
    early = _dynamic_view()
    canvas = _dynamic(today=date(2027, 2, 10))
    late = DynamicView(canvas=canvas, units=_plan_units(canvas), memo_key=("plan", "late"))
    months = canvas.process_months
    gaps = pd.to_numeric(months["과부족"]).round(9)
    # Cut-off 10일 — 02.10 은 02월 생산월에 기여한다.
    current = pd.to_numeric(months["생산계획년월"]).ge(202702)
    past_short = int((gaps.lt(0) & ~current).sum())
    assert past_short > 0, "합성 계획에 오늘 앞의 미달 달이 있어야 시험이 뜻이 있다"

    assert prescription(late).dynamic_short_months == int((gaps.lt(0) & current).sum())
    assert prescription(early).dynamic_short_months > prescription(late).dynamic_short_months


def test_the_target_reads_the_preference_threshold_by_month() -> None:
    uniform = MonthlyTarget(1.095)
    assert target_text(uniform, MONTHS) == "HOME Preference 확보기준(월별) 110% (1.095)"
    assert short_target_text(uniform, MONTHS) == "110% (1.095)"
    varied = MonthlyTarget(1.095, ((202703, 1.2),))
    assert target_text(varied, MONTHS) == "HOME Preference 확보기준(월별) — 달마다 다름"
    assert short_target_text(varied, MONTHS) == "달마다 확보기준"


# ------------------------------------------------------------------ 범례·스크롤


def test_the_legend_adds_the_schedule_marks_only_with_the_schedule() -> None:
    static = canvas_legend_html(None, MONTHS)
    assert "공식 확보기준 미달 달" in static and "지금 보는 달" in static
    assert "가용을 깎은 비가동" not in static
    dynamic = canvas_legend_html(_dynamic(), MONTHS)
    for item in (
        "반입",
        "추가N(신규 필요)",
        "가용을 깎은 비가동",
        "칸 = 생산월",
        "≠ 반출/이설일정",
    ):
        assert item in dynamic
    # 서식과 표시 글이 한 덩어리 — 본문 칸으로 간다.
    assert dynamic.startswith("<style>") and '<div class="pcd-legend">' in dynamic


def test_the_production_month_example_adds_the_next_day_and_the_cutoff() -> None:
    # 11.25 Qual → 기여 11.26, Cut-off 10 → 12.06 → 12월 칸.
    assert production_month_example(10, MONTHS) == (
        "칸 = 생산월 — Cut-off 10일이면 11.25 Qual 은 12월 칸에 섭니다"
    )
    assert production_month_example(0, MONTHS).endswith("11월 칸에 섭니다")


def test_the_scroll_starts_one_column_left_of_the_opened_month() -> None:
    assert initial_scroll_px(MONTHS, MONTHS[0]) == 0
    assert initial_scroll_px(MONTHS, MONTHS[1]) == 0
    assert initial_scroll_px(MONTHS, MONTHS[4]) == 300
    assert initial_scroll_px(MONTHS, None) == 0
    assert initial_scroll_px(MONTHS, 199001) == 0


# ------------------------------------------------------------------ 그림 기억·콜백


def _key(
    view: ProcessDetailView,
    *,
    month: int = 202702,
    expanded: bool = False,
    split: str = "제품정보",
    units: bool = False,
    arrows: bool = False,
    collapsed: frozenset[str] = frozenset(),
) -> tuple[object, ...]:
    return canvas_memo_key(
        view,
        month=month,
        expanded=expanded,
        split=split,
        show_all_units=units,
        show_all_arrows=arrows,
        collapsed=collapsed,
    )


def test_the_canvas_key_moves_with_every_drawn_condition() -> None:
    view = _view(dynamic=_dynamic_view())
    key = _key(view)
    assert _key(view) == key
    assert _key(view, month=202703) != key
    assert _key(view, expanded=True) != key
    assert _key(view, units=True) != key
    assert _key(view, arrows=True) != key
    # 접힌 동안 분류는 그림에 닿지 않는다.
    assert _key(view, split="Stack") == key
    assert _key(view, expanded=True, split="Stack") != _key(view, expanded=True)
    theme._LOCAL.mode = "dark"
    assert _key(view) != key
    theme._LOCAL.mode = "light"
    assert _key(_view(dynamic=None)) != key
    assert _key(_view(home_rates={202702: 1.0})) != _key(_view())
    # 접힌 구획은 그림에 구워진다 — 차례와 상관없이 같은 집합이면 같은 키다.
    assert _key(view, collapsed=frozenset({SECTION_UNITS})) != key
    assert _key(view, collapsed=frozenset({SECTION_UNITS, SECTION_DOWNTIME})) == _key(
        view, collapsed=frozenset({SECTION_DOWNTIME, SECTION_UNITS})
    )
    # UPEH 가정 토큰(%·건 달)은 ① 끝 세 줄과 판정 기준을 바꾼다.
    assert _key(_view(upeh_token=(110, (202702,)))) != _key(_view())
    assert _key(_view(upeh_token=(110, (202702,)))) != _key(_view(upeh_token=(120, (202702,))))


def test_the_canvas_schema_version_moves_with_the_folding_and_module_labels() -> None:
    """구획 접기·모듈 라벨 제거(4), ③ 세 줄 풍선 · 풍선 없는 칸 trace · 줄 이름 칸 풍선 표적(5),
    풍선 식의 「≈」(6 — `customdata` 에 구운 풍선 글)로 그림 모양이 바뀌었다 — 세션에 남은 옛 그림을
    다시 쓰지 않게 모양 버전이 6 이다(AGENTS 5장 16)."""
    from capa_simulation.components.process_capa_view import CANVAS_SCHEMA_VERSION

    assert CANVAS_SCHEMA_VERSION == 6
    assert _key(_view())[0] == CANVAS_SCHEMA_VERSION


def _memo_script() -> None:
    import streamlit as st
    from test_process_capa_view import _view

    from capa_simulation.components.process_capa_view import CANVAS_MEMO_KEY, remembered_canvas

    view = _view()
    months = list(view.months)
    first = remembered_canvas(
        view,
        month=months[0],
        expanded=False,
        split="제품정보",
        product_demand=None,
        show_all_units=False,
        show_all_arrows=False,
    )
    again = remembered_canvas(
        view,
        month=months[0],
        expanded=False,
        split="제품정보",
        product_demand=None,
        show_all_units=False,
        show_all_arrows=False,
    )
    st.session_state["same"] = first is again
    for month in months:
        remembered_canvas(
            view,
            month=month,
            expanded=False,
            split="제품정보",
            product_demand=None,
            show_all_units=False,
            show_all_arrows=False,
        )
    st.session_state["kept"] = len(st.session_state[CANVAS_MEMO_KEY])


def test_the_canvas_is_remembered_a_few_times_in_the_session() -> None:
    app = AppTest.from_function(_memo_script, default_timeout=60).run()
    assert not app.exception, [element.message for element in app.exception]
    assert app.session_state["same"] is True
    assert app.session_state["kept"] == CANVAS_MEMO_LIMIT


def _callback_script() -> None:
    import streamlit as st

    from capa_simulation.components.process_capa_view import pick_canvas_month, step_month
    from capa_simulation.process_detail_state import (
        PROCESS_DETAIL_CANVAS_CHART_KEY,
        PROCESS_DETAIL_MONTH_KEY,
    )

    months = (202611, 202612, 202701)
    st.session_state.setdefault(PROCESS_DETAIL_MONTH_KEY, 202611)
    action = st.session_state.pop("action", None)
    if action == "pick":
        st.session_state[PROCESS_DETAIL_CANVAS_CHART_KEY] = st.session_state.pop("selection")
        pick_canvas_month(months)
    elif action == "step":
        step_month(months, int(st.session_state.pop("step")), "test_step")


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        ({"selection": {"points": [{"customdata": [202701, "rate", "풍선"]}]}}, 202701),
        # ③ 줄을 눌러도 그 열의 달이다.
        ({"selection": {"points": [{"customdata": [202612, "unit:EQ-1", "풍선"]}]}}, 202612),
        # 빈 선택(같은 칸 다시 누르기)·축 밖 점은 보던 달 그대로다.
        ({"selection": {"points": []}}, 202611),
        ({"selection": {"points": [{"customdata": [199001, "rate", "풍선"]}]}}, 202611),
    ],
)
def test_a_cell_click_writes_the_month_of_the_cell(
    selection: dict[str, object], expected: int
) -> None:
    app = AppTest.from_function(_callback_script, default_timeout=60).run()
    app.session_state["action"] = "pick"
    app.session_state["selection"] = selection
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert app.session_state["process_detail_month"] == expected


def test_the_month_steps_stop_at_the_axis_ends() -> None:
    app = AppTest.from_function(_callback_script, default_timeout=60).run()
    for step, expected in ((-1, 202611), (1, 202612), (1, 202701), (1, 202701), (-1, 202612)):
        app.session_state["action"] = "step"
        app.session_state["step"] = step
        app.run()
        assert app.session_state["process_detail_month"] == expected


# ------------------------------------------------------------------ 구획 접기


def _sections_script() -> None:
    import streamlit as st

    from capa_simulation.components.process_capa_view import reopen_entry_section, seed_sections
    from capa_simulation.process_detail_state import PROCESS_DETAIL_SECTIONS_KEY

    action = st.session_state.pop("action", None)
    if action == "seed":
        seed_sections()
    elif action == "reopen":
        reopen_entry_section(st.session_state.pop("source"))
    st.session_state["seen"] = st.session_state.get(PROCESS_DETAIL_SECTIONS_KEY)


def _sections(app: AppTest, action: str, **values: object) -> object:
    app.session_state["action"] = action
    for name, value in values.items():
        app.session_state[name] = value
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    return app.session_state["seen"]


def test_the_sections_seed_all_open_and_keep_only_known_ids() -> None:
    app = AppTest.from_function(_sections_script, default_timeout=60).run()
    assert _sections(app, "seed") == list(SECTION_IDS)
    app.session_state["process_detail_sections"] = [SECTION_UNITS, "그 밖", SECTION_SUMMARY]
    # 모르는 값은 지우지 않고 아는 값만 남긴 새 목록을 적는다(차례는 구획 차례).
    assert _sections(app, "seed") == [SECTION_SUMMARY, SECTION_UNITS]
    app.session_state["process_detail_sections"] = []
    assert _sections(app, "seed") == []


@pytest.mark.parametrize(
    ("source", "section"),
    [(FROM_HOME, SECTION_SUMMARY), (FROM_GAP, SECTION_DOWNTIME), (FROM_SHORTENING, SECTION_UNITS)],
)
def test_an_entry_reopens_only_the_section_its_path_points_at(source: str, section: str) -> None:
    assert ENTRY_SECTIONS[source] == section
    app = AppTest.from_function(_sections_script, default_timeout=60).run()
    app.session_state["process_detail_sections"] = []
    assert _sections(app, "reopen", source=source) == [section]
    # 다른 구획의 접힘은 둔다. 이미 펼쳐 있으면 그대로다.
    assert _sections(app, "reopen", source=source) == [section]


def test_an_entry_without_a_known_path_leaves_the_sections() -> None:
    app = AppTest.from_function(_sections_script, default_timeout=60).run()
    app.session_state["process_detail_sections"] = [SECTION_SUMMARY]
    assert _sections(app, "reopen", source="") == [SECTION_SUMMARY]
    assert _sections(app, "reopen", source=None) == [SECTION_SUMMARY]


# ------------------------------------------------------------------ 부족 원인의 다음 화면


def test_the_kpi_next_screens_follow_the_cause_counts() -> None:
    plan = Prescription(shortened=1, new=0, unresolved_months=0, dynamic_short_months=2)
    screens = kpi_next_screens(_kpis(owned_short_months=1, mismatch_months=3), plan)
    assert screens == NextScreens(
        owned="보유로도 부족 1개월 — 산출 결과",
        mismatch="가용 불일치 3개월 — 가용설비 현황",
        schedule="일정 2개월 — 필요 단축 일정",
    )
    # 대여 영향만 있으면(공식 기준 안의 차이) 옮겨 갈 화면이 없다.
    none = kpi_next_screens(_kpis(owned_short_months=0, rental_months=4), None)
    assert none == NextScreens() and not none.present()


def test_the_month_next_screens_read_that_month_cause_and_schedule() -> None:
    summary = _summary()
    month = 202703
    summary.loc[summary["생산계획년월"].eq(month), CAUSE_COLUMN] = CAUSE_OWNED_SHORT
    other = 202611
    summary.loc[summary["생산계획년월"].eq(other), CAUSE_COLUMN] = CAUSE_AVAILABILITY_MISMATCH
    dynamic = _dynamic_view()
    view = _view(dynamic=dynamic, summary=summary)

    owned = month_next_screens(view, month)
    assert owned.owned == "이 달 보유로도 부족 — 산출 결과" and owned.mismatch is None
    assert month_next_screens(view, other).mismatch == "이 달 가용 불일치 — 가용설비 현황"
    gaps = pd.to_numeric(dynamic.canvas.process_months["과부족"]).round(9)
    short = [
        int(m)
        for m, gap in zip(dynamic.canvas.process_months["생산계획년월"], gaps, strict=True)
        if gap < 0
    ]
    assert short, "합성 계획에 일정 미달 달이 있어야 시험이 뜻이 있다"
    assert all(schedule_short_month(dynamic, m) for m in short)
    assert month_next_screens(view, short[0]).schedule == "이 달 일정 부족 — 필요 단축 일정"
    # 설비 일정이 없으면 일정 단추가 없다.
    assert month_next_screens(_view(summary=summary), short[0]).schedule is None


@pytest.mark.parametrize(
    ("percent", "month", "head", "official", "owned_link"),
    [
        # 공식은 경고(보유로도 부족)인데 150% 면 확보 — ③ 머리도 확보, 다음 화면 줄도 없다.
        (
            150,
            202702,
            "→ 확보",
            "공식: 확보율 100.4% → 경고 · 과부족 −5 · 원인 보유로도 부족",
            None,
        ),
        # 공식은 확보인데 80% 면 부족(보유로도 부족) — ③ 머리도 부족, 다음 화면 줄도 선다.
        (
            80,
            202611,
            "→ 부족",
            "공식: 확보율 116.5% → 확보 · 과부족 +2",
            "이 달 보유로도 부족 — 산출 결과",
        ),
    ],
)
def test_the_judgement_card_and_next_screens_read_the_same_assumed_basis(
    percent: int, month: int, head: str, official: str, owned_link: str | None
) -> None:
    """UPEH 가정 구간 달의 ③ 판정 카드는 머리 식·판정·원인을 가정 요약으로 내고(소요 = 공식 ÷ f
    를 식 첫 줄에), 공식 판정은 회색 「공식: …」 한 줄로 내린다 — 같은 패널의 다음 화면 줄과 같은
    기준이다."""
    window = set(MONTHS)
    summary = _summary()
    assumed = _assumed_summary(percent, window)
    view = _view(summary=summary, assumed_summary=assumed, upeh_token=(percent, tuple(MONTHS)))

    card = evidence_cards(view, month, None)[2]
    official_required = float(_record(summary, month)["소요대수"])  # type: ignore[arg-type]
    assumed_required = float(_record(assumed, month)["소요대수"])  # type: ignore[arg-type]
    first, rate_line, _ = card.formula.split("\n")
    assert card.title == f"③ 판정 (UPEH 가정 {percent}%)"
    assert first.startswith(f"소요 = {official_required:,.2f} ÷ {percent / 100:g} ")
    assert first.endswith(f" {assumed_required:,.2f}")
    assert rate_line.endswith(head)
    assert official in card.notes
    assert card.notes[-1] == official
    cause = _record(assumed, month)[CAUSE_COLUMN]
    assert any(note.startswith("원인: ") for note in card.notes) == bool(cause)
    assert month_next_screens(view, month).owned == owned_link
    # 가정이 없으면 공식 그대로다(제목·식 두 줄, 「공식:」 줄 없음).
    plain = evidence_cards(_view(summary=summary), month, None)[2]
    assert plain.title == "③ 판정" and len(plain.formula.split("\n")) == 2
    assert not any(note.startswith("공식: ") for note in plain.notes)


def _gap_script() -> None:
    from capa_simulation.components.process_capa_view import open_availability_gap

    open_availability_gap()


def test_the_gap_link_remembers_the_static_tab_without_touching_its_widget_or_filters() -> None:
    """Static 대비 일정은 Summary 안쪽 탭이다(2026-10-24) — 바깥·안쪽 기억 칸을 함께 적는다."""
    from capa_simulation.components.tab_state import remembered_tab_key
    from capa_simulation.navigation import (
        EQUIPMENT_GAP_TAB,
        EQUIPMENT_SUMMARY_TAB,
        EQUIPMENT_SUMMARY_TAB_KEY,
        EQUIPMENT_TAB_KEY,
    )

    app = AppTest.from_function(_gap_script, default_timeout=60).run()

    assert not app.exception, [element.message for element in app.exception]
    assert app.session_state[remembered_tab_key(EQUIPMENT_TAB_KEY)] == EQUIPMENT_SUMMARY_TAB
    assert app.session_state[remembered_tab_key(EQUIPMENT_SUMMARY_TAB_KEY)] == EQUIPMENT_GAP_TAB
    assert EQUIPMENT_TAB_KEY not in app.session_state
    assert EQUIPMENT_SUMMARY_TAB_KEY not in app.session_state
