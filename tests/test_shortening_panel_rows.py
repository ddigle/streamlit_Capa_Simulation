# Purpose: 필요 단축 일정 B/N 줄과 공정 차례가 고치기 전 식과 같고 표시순서 규칙을 따르는지 본다.

"""필요 단축 일정 패널의 회차마다 도는 두 조각(점검 EQ-9).

- B/N 줄: 달마다 표를 거르던 것을 한 번에 고른다. 고르는 규칙(numpy `argmin` — 동점은 앞 행, NaN 이
  있으면 첫 NaN)이 그대로인지 옛 식과 견준다.
- 공정 차례: `load_page_context` 가 준비해 둔 표시순서를 그대로 쓴다. 날표로 다시 준비한 것과 같은
  차례이고, 규칙을 바꾸면 따라 바뀐다.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import capa_simulation.services.display_order as display_order_module
from capa_simulation.components.required_shortening_panel import (
    _LABEL_COLUMN_PX,
    _MONTH_COLUMN_MIN_PX,
    _UNIT_NAME_PX,
    _UNIT_RESULT_PX,
    _UNIT_STICKY_MIN_PX,
    _bottlenecks,
    _ordered_processes,
    _style,
)
from capa_simulation.components.shortening_progress_panel import (
    _NAME_PX,
    _RESULT_PX,
    _STICKY_MIN_PX,
    UNITS_CONTAINER,
    progress_style,
)
from capa_simulation.page_bootstrap import PageContext
from capa_simulation.services.display_order import apply_display_order, prepare_display_order
from capa_simulation.services.display_order_scopes import PAGE_CALCULATION, TAB_SECUREMENT
from capa_simulation.services.required_shortening import ShorteningPlan


def _old_bottleneck(frame: pd.DataFrame, month: int, column: str) -> tuple[float, str] | None:
    """고치기 전 식 그대로 — 달마다 표를 거르고 numpy argmin 으로 고른다."""
    rows = frame.loc[frame["생산계획년월"].eq(month) & frame["소요대수"].gt(0)]
    if rows.empty:
        return None
    rates = rows[column] / rows["소요대수"]
    position = int(rates.to_numpy().argmin())
    return float(rates.iloc[position]), str(rows["공정"].iloc[position])


def _same(left: tuple[float, str] | None, right: tuple[float, str] | None) -> bool:
    if left is None or right is None:
        return left is right
    both_nan = left[0] != left[0] and right[0] != right[0]
    return left[1] == right[1] and (both_nan or left[0] == right[0])


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # 동점: 앞 행(P-B)이 고른다
            (202610, "P-A", 10.0, 5.0, 8.0),
            (202610, "P-B", 10.0, 4.0, 9.0),
            (202610, "P-C", 5.0, 2.0, 4.5),
            # 가용 NaN: 그 달의 첫 NaN 행
            (202611, "P-A", 10.0, 3.0, 3.0),
            (202611, "P-B", 10.0, float("nan"), 2.0),
            (202611, "P-C", 10.0, float("nan"), 1.0),
            # 소요대수 0·음수는 보지 않는다
            (202612, "P-A", 0.0, 0.0, 0.0),
            (202612, "P-B", -1.0, 0.0, 0.0),
            (202612, "P-C", 4.0, 3.0, 5.0),
            # 소요대수 0 행만 있는 달
            (202701, "P-A", 0.0, 1.0, 1.0),
            # 0 과 -0.0 은 같은 값 — 앞 행
            (202702, "P-B", 3.0, -0.0, 1.0),
            (202702, "P-A", 3.0, 0.0, 1.0),
        ],
        columns=["생산계획년월", "공정", "소요대수", "가용대수", "단축후가용대수"],
    )


MONTHS = [202609, 202610, 202611, 202612, 202701, 202702]


@pytest.mark.parametrize("column", ["가용대수", "단축후가용대수"])
def test_the_bottleneck_row_matches_the_per_month_argmin(column: str) -> None:
    """동점·NaN·소요대수 0 이하·그런 행만 있는 달·표에 없는 달에서 옛 식과 같다."""
    frame = _frame()

    found = _bottlenecks(frame, MONTHS, column)

    for month in MONTHS:
        assert _same(found.get(month), _old_bottleneck(frame, month, column)), month


def test_the_bottleneck_picks_what_the_rule_says() -> None:
    found = _bottlenecks(_frame(), MONTHS, "가용대수")

    assert found[202610] == (0.4, "P-B")
    assert found[202611][1] == "P-B"
    assert found[202612] == (0.75, "P-C")
    assert 202609 not in found and 202701 not in found
    # 고른 달만 본다.
    assert set(_bottlenecks(_frame(), [202611], "가용대수")) == {202611}
    assert _bottlenecks(_frame().iloc[0:0], MONTHS, "가용대수") == {}


def _display_order(first: str) -> pd.DataFrame:
    """산출 결과 › 확보율 의 공정 사용자지정 차례 — `first` 를 맨 앞에 둔다."""
    rest = [name for name in ("P-A", "P-B", "P-C") if name != first]
    return pd.DataFrame(
        {
            "페이지 구분": ["산출 결과"] * 3,
            "탭 구분": ["확보율"] * 3,
            "정렬우선순위": [1, 1, 1],
            "분류컬럼": ["공정"] * 3,
            "정렬방식": ["사용자지정"] * 3,
            "분류값": [first, *rest],
            "값표시순서": [1, 2, 3],
            "활성여부": ["Y"] * 3,
        }
    )


def _context_with(display_order: pd.DataFrame) -> PageContext:
    return PageContext(
        reference_version=1,
        reference_tables={"RQ_DISPLAY_ORDER": display_order},
        display_order=prepare_display_order(display_order),
        active_scenario={
            "reference_version": 1,
            "revision": 0,
            "content_token": "display-order-test",
            "tables": {},
        },
        selected_start_month=202610,
        selected_end_month=202612,
    )


@pytest.mark.parametrize("first", ["P-A", "P-C"])
def test_process_order_uses_the_prepared_rules_and_follows_them(
    first: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """차례는 날표로 다시 준비한 것과 같고, 규칙(공용 표시순서)을 바꾸면 따라 바뀐다. 회차마다
    규칙을 다시 준비하지 않는다 — `load_page_context` 가 준비해 둔 것을 쓴다."""
    plan = ShorteningPlan(
        months=(202610,),
        today=date(2026, 10, 13),
        processes=("P-A", "P-B", "P-C"),
        cutoff_days={},
        levels=(),
    )
    context = _context_with(_display_order(first))
    expected = apply_display_order(
        pd.DataFrame({"공정": list(plan.processes)}),
        context.reference_tables["RQ_DISPLAY_ORDER"],
        PAGE_CALCULATION,
        TAB_SECUREMENT,
    )["공정"].tolist()

    def refuse(_frame: pd.DataFrame) -> pd.DataFrame:
        raise AssertionError("준비해 둔 표시순서 규칙을 다시 준비했다")

    monkeypatch.setattr(display_order_module, "_prepare_display_order", refuse)
    ordered = _ordered_processes(plan, context)

    assert ordered == expected
    assert ordered[0] == first


def test_the_tables_keep_their_row_names_and_fit_fourteen_months() -> None:
    """가로로 흐르는 표의 줄 이름 칸은 붙박이고(`position:sticky`), 기준 창(1600 · 사이드바 펼침) 표
    폭 1227px 에 14달이 스크롤 막대 자리까지 남기고 든다 — 끝 달이 숫자 중간에서 잘려 보이지
    않는다. 카드 표의 좌우 틈은 스크롤 상자 밖 여백이다(안쪽 여백이면 붙박인 칸 왼쪽으로 달 칸이
    비친다)."""
    assert _LABEL_COLUMN_PX + 14 * _MONTH_COLUMN_MIN_PX + 15 <= 1227
    style = _style()
    for selector in (".shk-grid > div.shk-row, .shk-grid > div.shk-row-muted", ".shk-unit-label"):
        rule = style.split(selector + " {", 1)[1].split("}", 1)[0]
        assert "position:sticky" in rule and "left:0" in rule and "background:" in rule
    rule = progress_style().split(".shk-prog-label {", 1)[1].split("}", 1)[0]
    assert "position:sticky" in rule and "left:0" in rule and "background:" in rule
    assert "padding:8px 0 4px" in style.split(".shk-card-body {", 1)[1].split("}", 1)[0]


@pytest.mark.parametrize(
    ("style", "label", "name_px", "result_px", "threshold"),
    [
        (_style(), ".shk-unit-label", _UNIT_NAME_PX, _UNIT_RESULT_PX, _UNIT_STICKY_MIN_PX),
        (progress_style(), ".shk-prog-label", _NAME_PX, _RESULT_PX, _STICKY_MIN_PX),
    ],
)
def test_narrow_unit_rows_let_the_row_name_scroll_away(
    style: str, label: str, name_px: int, result_px: int, threshold: int
) -> None:
    """호기 줄 묶음이 붙박인 이름 칸과 결과 칸을 나란히 담지 못할 만큼 좁으면(폰 폭 · 사이드바를 편
    좁은 창) 이름 칸을 붙박지 않는다 — 붙박으면 끝까지 굴려도 결과 칸 앞쪽이 이름 칸 밑에 가려 끝내
    못 읽는다. 갈림은 창이 아니라 묶음 폭의 컨테이너 질의다(사이드바를 펴도 따라간다)."""
    units = _style().split(".shk-units {", 1)[1].split("}", 1)[0]
    assert f"container:{UNITS_CONTAINER} / inline-size" in units
    query = f"@container {UNITS_CONTAINER} (width < {threshold}px) {{"
    assert query in style
    body = style.split(query, 1)[1].split("}", 1)[0]
    assert label in body and "position:static" in body
    # 이름 칸 + 칸 사이 + 결과 칸 + 줄 안쪽 여백 · 테 — 이보다 넓어야 굴린 끝에서 결과 칸이 다
    # 보인다.
    assert threshold >= name_px + result_px + 10 + 11
