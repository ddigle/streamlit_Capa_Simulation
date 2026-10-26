# Purpose: 공정 Capa 상세 결합 월 캔버스 그림의 행·색·띠·칸 표적·설비 일정 표지를 고정한다.

"""공정 Capa 상세의 결합 월 캔버스(`components/process_capa_canvas.py`).

숫자는 화면 목업(2026-10-15 2차 구성안)의 예시를 그대로 쓴다 — 26.11~27.06 여덟 달, 확보기준
109.5% · 경고기준 99.5%. 설비 일정은 합성 공정 하나(`test_required_shortening` 의 도우미)로 실제
계산을 지나게 한다. 그림은 JSON 으로 읽는다(브라우저로 보내는 것과 같은 dict).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from datetime import date
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import pytest
from test_required_shortening import PROCESS, _baseline, _cutoff, _master, _required, _unit

from capa_simulation.components.home_dimensions import DASHBOARD_LABEL_COLUMN_WIDTH_PX
from capa_simulation.components.home_figure_common import _text_width_units
from capa_simulation.components.plotly_layout import plotly_validation
from capa_simulation.components.process_capa_canvas import (
    CUSTOMDATA_HOVER,
    CUSTOMDATA_MONTH,
    CUSTOMDATA_ROW,
    ROW_AVAILABLE,
    ROW_BALANCE,
    ROW_DYNAMIC_BALANCE,
    ROW_DYNAMIC_COMPARE,
    ROW_HEADER,
    ROW_HOME_RATE,
    ROW_LIMIT,
    ROW_OWNED,
    ROW_RATE,
    ROW_REQUIRED,
    ROW_THRESHOLD,
    ROW_UPEH_BALANCE,
    ROW_UPEH_RATE,
    ROW_UPEH_REQUIRED,
    SECTION_DOWNTIME,
    SECTION_DYNAMIC,
    SECTION_IDS,
    SECTION_SUMMARY,
    SECTION_UNITS,
    SUMMARY_TITLE_DETAIL,
    SUMMARY_TITLE_HEIGHT_PX,
    TITLE_HEIGHT_PX,
    UNIT_ROW_HEIGHT_PX,
    AssumptionCanvasInput,
    DynamicCanvasInput,
    ProcessCapaCanvas,
    _unit_hover,
    build_process_capa_canvas,
    canvas_point,
    title_detail_lines,
    title_row_height,
)
from capa_simulation.design import theme, tokens
from capa_simulation.services.process_capa_detail import (
    build_process_capa_summary,
    build_process_product_demand,
)
from capa_simulation.services.process_equipment_timeline import (
    ROW_NEW,
    ROW_SHORTENED,
    ROW_VIRTUAL,
    UNIT_EVENT_COLUMNS,
    build_process_equipment_timeline,
    unit_events,
)
from capa_simulation.services.required_shortening import (
    MonthlyTarget,
    plan_required_shortening,
    target_from_thresholds,
)
from capa_simulation.services.securement_threshold import SecurementThresholds

MONTHS = [202611, 202612, 202701, 202702, 202703, 202704, 202705, 202706]
OWNED = [52, 52, 54, 54, 58, 58, 58, 58]
AVAILABLE = [48, 48, 50, 50, 52, 52, 54, 54]
REQUIRED = [41.2, 44.0, 47.5, 49.8, 52.6, 50.1, 46.3, 44.9]
THRESHOLDS = SecurementThresholds(1.095, 0.995)
TODAY = date(2026, 11, 10)
SHARES = {"PRODUCT_A": 0.374, "PRODUCT_B": 0.249, "PRODUCT_C": 0.183, "PRODUCT_D": 0.194}
MINUS = "−"


@pytest.fixture(autouse=True)
def _light_theme() -> Iterator[None]:
    """테스트는 Streamlit 밖이라 밝게다. 어둡게를 켠 시험이 남긴 값을 되돌린다."""
    theme._LOCAL.mode = "light"
    yield
    theme._LOCAL.mode = "light"


def _summary(
    available: list[float] | None = None,
    required: list[float] | None = None,
    thresholds: SecurementThresholds = THRESHOLDS,
) -> pd.DataFrame:
    available = available or [float(value) for value in AVAILABLE]
    required = required or REQUIRED
    rate = pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "공정": PROCESS,
            "가용대수": available,
            "소요대수": required,
            "확보율": [a / r for a, r in zip(available, required, strict=True)],
        }
    )
    owned = pd.DataFrame({"생산계획년월": MONTHS, "공정": PROCESS, "설비보유": OWNED})
    lent = pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "공정": PROCESS,
            "설비대여평가": [o - a for o, a in zip(OWNED, AVAILABLE, strict=True)],
        }
    )
    return build_process_capa_summary(
        rate, owned, lent, process=PROCESS, months=MONTHS, thresholds=thresholds
    )


def _products() -> pd.DataFrame:
    rows = [
        {
            "생산계획년월": month,
            "공정": PROCESS,
            "양산구분": "양산",
            "제품정보": product,
            "Stack": "8H",
            "WF 구분": "DRAM",
            "소요기준": "HBM",
            "소요대수": need * share,
        }
        for month, need in zip(MONTHS, REQUIRED, strict=True)
        for product, share in SHARES.items()
    ]
    return build_process_product_demand(
        pd.DataFrame(rows), process=PROCESS, split="제품정보", months=MONTHS
    )


def _fleet() -> list[dict[str, Any]]:
    existing = [
        _unit(
            f"EQ-0{number}",
            date(2025, 6, 1),
            arrival=date(2025, 5, 1),
            existing="Y",
            confirmation="완료",
        )
        for number in range(1, 6)
    ]
    return [
        *existing,
        _unit(
            "EQ-21A",
            date(2026, 12, 20),
            arrival=date(2026, 12, 2),
            parent="EQ-21",
            confirmation="확정",
        ),
        _unit(
            "EQ-21B",
            date(2026, 12, 22),
            arrival=date(2026, 12, 2),
            parent="EQ-21",
            confirmation="확정",
        ),
        _unit("EQ-22", date(2027, 2, 6), arrival=date(2027, 1, 2)),
        _unit("EQ-23", date(2027, 2, 26), arrival=date(2027, 2, 1)),
        _unit("EQ-24", date(2027, 3, 24), arrival=date(2027, 3, 12), confirmation="확정"),
        _unit("EQ-25", date(2027, 4, 15), arrival=date(2027, 3, 25)),
        _unit("EQ-26", date(2027, 5, 12), arrival=date(2027, 4, 20), removal=date(2027, 6, 10)),
        _unit(
            "EQ-07",
            date(2025, 3, 1),
            arrival=date(2025, 2, 1),
            existing="Y",
            confirmation="완료",
            relocation=date(2027, 5, 5),
        ),
    ]


def _downtime() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("EQ-02", "정기 PM", date(2026, 10, 10), date(2026, 11, 15), None, None),
            ("EQ-03", "정기 PM", date(2026, 12, 12), date(2026, 12, 20), None, None),
            ("EQ-21A", "셋업", date(2026, 12, 3), date(2026, 12, 15), None, None),
            ("EQ-04", "고장", date(2027, 2, 3), date(2027, 2, 24), None, None),
            ("EQ-05", "개조", date(2027, 3, 10), date(2027, 4, 18), None, None),
            ("EQ-01", "이설 준비", date(2027, 5, 5), None, None, None),
        ],
        columns=["설비명", "비가동유형", "시작일", "종료일", "상세사유", "비고"],
    )


def _dynamic(*, today: date = TODAY, **changes: Any) -> DynamicCanvasInput:
    target = target_from_thresholds(THRESHOLDS, MONTHS)
    fleet = _master(_fleet())
    plan = plan_required_shortening(
        equipment=fleet,
        downtime=_downtime(),
        baseline=_baseline(44.0),
        cutoff=_cutoff(),
        required_equipment=_required(dict(zip(MONTHS, REQUIRED, strict=True))),
        months=MONTHS,
        today=today,
        levels=(target,),
    ).at(target)
    timeline = build_process_equipment_timeline(
        fleet, _downtime(), _baseline(44.0), _cutoff(), process=PROCESS, months=MONTHS
    )
    events = unit_events(timeline, plan.units)
    shown = set(events["호기"].astype(str))
    values: dict[str, Any] = {
        "cutoff_days": 10,
        "target": target,
        "today": today,
        "process_months": plan.process_months,
        "bridge": timeline.bridge,
        "unit_events": events,
        "arrows": timeline.arrows,
        "exits": timeline.exits.loc[~timeline.exits["호기"].astype(str).isin(shown)],
        "steady_units": timeline.steady_units,
        "undated_notice": "일정 미정 1대",
    }
    values.update(changes)
    return DynamicCanvasInput(**values)


def _canvas(
    *,
    selected: int | None = 202702,
    products: bool = True,
    home: bool = True,
    dynamic: DynamicCanvasInput | None = None,
    summary: pd.DataFrame | None = None,
    thresholds: SecurementThresholds = THRESHOLDS,
    collapsed: frozenset[str] = frozenset(),
) -> ProcessCapaCanvas:
    return build_process_capa_canvas(
        process_label="Die Attach",
        months=MONTHS,
        summary=_summary() if summary is None else summary,
        thresholds=thresholds,
        selected_month=selected,
        product_demand=_products() if products else None,
        home_rates=(
            {m: a / r + 0.02 for m, a, r in zip(MONTHS, AVAILABLE, REQUIRED, strict=True)}
            if home
            else None
        ),
        dynamic=dynamic,
        collapsed=collapsed,
    )


def _json(figure: go.Figure) -> Any:
    return json.loads(pio.to_json(figure, validate=False))


def _targets(canvas: ProcessCapaCanvas) -> list[Any]:
    """칸 표적 막대의 (customdata, y 가운데, 높이) — 풍선 있는 칸과 없는 칸(둘째 trace) 모두."""
    return [
        item
        for trace in _json(canvas.months)["data"]
        if trace.get("customdata")
        for item in zip(trace["customdata"], trace["y"], trace["width"], strict=True)
    ]


def _label_hovers(canvas: ProcessCapaCanvas) -> dict[str, str]:
    """줄 이름 칸 풍선 — 행 id → 풍선 글(라벨 Figure 의 표적 막대)."""
    return {
        str(row_id): str(hover)
        for trace in _json(canvas.labels)["data"]
        for row_id, hover in trace["customdata"]
    }


def _hover_months(canvas: ProcessCapaCanvas, row_id: str) -> list[int]:
    """그 행에서 풍선이 뜨는 달."""
    return sorted(
        int(data[CUSTOMDATA_MONTH])
        for data, _, _ in _targets(canvas)
        if data[CUSTOMDATA_ROW] == row_id and data[CUSTOMDATA_HOVER]
    )


def _row_center(canvas: ProcessCapaCanvas, row_id: str) -> float:
    return float(next(y for data, y, _ in _targets(canvas) if data[CUSTOMDATA_ROW] == row_id))


def _plan_values(dynamic: DynamicCanvasInput, column: str) -> dict[int, float]:
    """설비 일정 계획의 달 → 값."""
    frame = dynamic.process_months
    return {
        int(month): float(value)
        for month, value in zip(frame["생산계획년월"].tolist(), frame[column].tolist(), strict=True)
    }


def _fills(canvas: ProcessCapaCanvas) -> list[tuple[float, float, str]]:
    """칠한 칸의 (왼쪽 x, y 가운데, 색)."""
    trace = next(
        item
        for item in _json(canvas.months)["data"]
        if item["type"] == "bar" and not item.get("customdata")
    )
    return list(zip(trace["base"], trace["y"], trace["marker"]["color"], strict=True))


def _row_fills(canvas: ProcessCapaCanvas, row_id: str) -> dict[int, str]:
    """그 행의 칠한 칸 — 달 index → 색."""
    center = _row_center(canvas, row_id)
    return {int(round(base)): color for base, y, color in _fills(canvas) if math.isclose(y, center)}


def _texts(canvas: ProcessCapaCanvas) -> list[tuple[float, float, str, str]]:
    """칸 글자 (x, y, 글, 색). 표지 글자(③·④)는 빼고 칸 가운데(x = index + 0.5)에 선 것만."""
    found: list[tuple[float, float, str, str]] = []
    for trace in _json(canvas.months)["data"]:
        if trace.get("mode") != "text" or trace.get("textposition") != "middle center":
            continue
        color = trace["textfont"]["color"]
        found += [
            (x, y, text, color)
            for x, y, text in zip(trace["x"], trace["y"], trace["text"], strict=True)
        ]
    return found


def _row_texts(canvas: ProcessCapaCanvas, row_id: str) -> dict[int, tuple[str, str]]:
    center = _row_center(canvas, row_id)
    return {
        int(x): (text, color) for x, y, text, color in _texts(canvas) if math.isclose(y, center)
    }


def _shapes(figure: go.Figure) -> list[dict[str, Any]]:
    return list(_json(figure)["layout"].get("shapes", []))


def _annotations(figure: go.Figure) -> list[dict[str, Any]]:
    return list(_json(figure)["layout"].get("annotations", []))


# ---------------------------------------------------------------------- 틀


def test_the_two_figures_share_one_height_and_the_month_figure_is_100px_a_month() -> None:
    canvas = _canvas(dynamic=_dynamic())
    labels, months = _json(canvas.labels)["layout"], _json(canvas.months)["layout"]

    assert labels["height"] == months["height"] == canvas.height
    assert months["width"] == len(MONTHS) * tokens.MONTH_COLUMN_WIDTH_PX
    assert months["xaxis"]["range"] == [0, len(MONTHS)]
    assert months["yaxis"]["range"] == [0, canvas.height]
    assert months["xaxis"]["fixedrange"] and months["yaxis"]["fixedrange"]


def test_rows_stack_the_four_sections_in_the_mock_order() -> None:
    dynamic = _dynamic()
    canvas = _canvas(dynamic=dynamic)
    ids = canvas.row_ids

    summary_rows = [
        ROW_HEADER,
        "title:summary",
        ROW_OWNED,
        ROW_AVAILABLE,
        ROW_REQUIRED,
        "product:PRODUCT_A",
        "product:PRODUCT_B",
        "product:PRODUCT_C",
        "product:PRODUCT_D",
        ROW_RATE,
        ROW_BALANCE,
        ROW_THRESHOLD,
        ROW_HOME_RATE,
    ]
    assert list(ids[: len(summary_rows)]) == summary_rows
    titles = [row for row in ids if row.startswith("title:")]
    assert titles == ["title:summary", "title:dynamic", "title:units", "title:downtime"]
    dynamic_start = ids.index("title:dynamic")
    assert list(ids[dynamic_start + 1 : dynamic_start + 5]) == [
        ROW_DYNAMIC_COMPARE,
        "dynamic_available",
        "dynamic_delta",
        ROW_DYNAMIC_BALANCE,
    ]
    units = ids[ids.index("title:units") + 1 : ids.index("title:downtime")]
    # 단축 대상(계획 차례) → 나머지 신규 → 축 안 반출·이설 호기 → 추가N → 알림.
    kind_of = {
        f"unit:{unit}": kind
        for unit, kind in zip(dynamic.unit_events["호기"], dynamic.unit_events["줄"], strict=True)
    }
    order = [ROW_SHORTENED, ROW_NEW, "exit", ROW_VIRTUAL, "note"]
    kinds = [kind_of.get(row, row.split(":")[0]) for row in units]
    assert kinds == sorted(kinds, key=order.index)
    assert set(kinds) == set(order)
    assert units[-1] == "note:undated"
    assert all(row.startswith("arrow:") for row in ids[ids.index("title:downtime") + 1 :])


def test_without_schedule_or_home_rates_the_canvas_ends_at_the_reference_row() -> None:
    canvas = _canvas(products=False, home=False)

    assert canvas.row_ids == (
        ROW_HEADER,
        "title:summary",
        ROW_OWNED,
        ROW_AVAILABLE,
        ROW_REQUIRED,
        ROW_RATE,
        ROW_BALANCE,
        ROW_THRESHOLD,
    )
    required_label = next(
        item["text"] for item in _annotations(canvas.labels) if "소요대수" in item["text"]
    )
    assert "▸" in required_label
    assert "▾" in next(
        item["text"]
        for item in _annotations(_canvas(products=True).labels)
        if "소요대수" in item["text"]
    )


def _section_rows(row_ids: tuple[str, ...], section: str) -> list[str]:
    """그 구획 제목 줄 밑, 다음 제목 줄 앞까지의 행 id."""
    start = row_ids.index(f"title:{section}") + 1
    rows: list[str] = []
    for row in row_ids[start:]:
        if row.startswith("title:"):
            break
        rows.append(row)
    return rows


@pytest.mark.parametrize("section", SECTION_IDS)
def test_a_collapsed_section_keeps_only_its_title_row(section: str) -> None:
    """접힌 구획은 제목 줄(▸)만 남고, 다른 구획의 행은 그대로다. 제목 줄 높이는 같다."""
    dynamic = _dynamic()
    full = _canvas(dynamic=dynamic)
    folded = _canvas(dynamic=dynamic, collapsed=frozenset({section}))

    titles = [row for row in folded.row_ids if row.startswith("title:")]
    assert titles == [f"title:{name}" for name in SECTION_IDS]
    assert _section_rows(full.row_ids, section)
    assert _section_rows(folded.row_ids, section) == []
    for other in SECTION_IDS:
        if other != section:
            assert _section_rows(folded.row_ids, other) == _section_rows(full.row_ids, other)
    label_texts = [item["text"] for item in _annotations(folded.labels)]
    marks = {
        name: next(text for text in label_texts if text.startswith("<b>") and text[3:4] == mark)[-5]
        for name, mark in zip(SECTION_IDS, "①②③④", strict=True)
    }
    assert marks == {name: "▸" if name == section else "▾" for name in SECTION_IDS}
    assert folded.height < full.height


def test_folding_the_summary_keeps_the_shortage_band_and_the_cross_check() -> None:
    """판정·원인은 요약 프레임에서 낸다 — ① 을 접어도 부족 띠와 ② 판정 대조는 같다."""
    dynamic = _dynamic()
    full = _canvas(dynamic=dynamic)
    folded = _canvas(dynamic=dynamic, collapsed=frozenset({SECTION_SUMMARY}))

    def bands(canvas: ProcessCapaCanvas) -> list[float]:
        return sorted(
            shape["x0"]
            for shape in _shapes(canvas.months)
            if shape.get("fillcolor") == tokens.SHORTAGE_MONTH_BAND
        )

    assert bands(folded) and bands(folded) == bands(full)
    assert _row_texts(folded, ROW_DYNAMIC_COMPARE) == _row_texts(full, ROW_DYNAMIC_COMPARE)
    assert ROW_RATE not in folded.row_ids and ROW_HOME_RATE not in folded.row_ids


def test_folded_units_and_downtime_draw_no_rows_and_count_nothing_hidden() -> None:
    events = _many_new_units(ROW_LIMIT + 5)
    dynamic = _dynamic(unit_events=events, exits=pd.DataFrame())
    folded = _canvas(dynamic=dynamic, collapsed=frozenset({SECTION_UNITS, SECTION_DOWNTIME}))

    assert _canvas(dynamic=dynamic).hidden_units == 5
    assert folded.hidden_units == 0 and folded.hidden_arrow_units == 0
    assert not [row for row in folded.row_ids if row.startswith(("unit:", "arrow:", "note:"))]
    # 오늘 점선은 남은 본문(②)에만 긋는다.
    dashes = [
        shape
        for shape in _shapes(folded.months)
        if shape["type"] == "line" and shape.get("line", {}).get("dash") == "dash"
    ]
    assert len(dashes) == 1


def test_an_absent_or_unknown_section_is_ignored() -> None:
    plain = _canvas(products=False, home=False)
    ignored = _canvas(products=False, home=False, collapsed=frozenset({SECTION_DYNAMIC, "그 밖"}))

    assert ignored.row_ids == plain.row_ids
    assert ignored.height == plain.height
    # 설비 일정이 호기 없이 ② 만 서면 ② 를 접어도 ③·④ 자리의 까닭 줄은 남는다.
    baseline_only = _canvas(
        dynamic=_dynamic(has_units=False), collapsed=frozenset({SECTION_DYNAMIC})
    )
    assert _section_rows(baseline_only.row_ids, SECTION_DYNAMIC) == ["note:no_units"]


def test_section_titles_and_their_details_stand_in_the_fixed_label_column() -> None:
    """구획 제목의 출처·단위 글은 스크롤되지 않는 라벨 Figure 에 선다 — 월 Figure 에 두면 고른 달로
    밀어 연 화면에서 잘린다(브라우저 확인 결함). 월 Figure 의 제목 줄에는 글이 없다."""
    canvas = _canvas(dynamic=_dynamic())
    label_texts = [item["text"] for item in _annotations(canvas.labels)]
    month_texts = json.dumps(_annotations(canvas.months), ensure_ascii=False)
    details = [
        SUMMARY_TITLE_DETAIL,
        "참고 · 설비 DB · 환산대수 · 생산월(Cut-off 10일) · 점선은 오늘(11.10)",
        "단축 목표 110% · 호기마다 한 줄",
        "진한 화살표만 가용을 깎았습니다 · 끝은 다음 날부터 셉니다",
    ]
    for detail in details:
        lines = title_detail_lines(detail)
        assert lines and " · ".join(lines) == detail
        for line in lines:
            assert line in label_texts
            assert line not in month_texts
    for title in (
        "① 공식 기준",
        "② 설비 일정 기준 가용",
        "③ 신규 설비 일정과 단축",
        "④ 호기별 비가동",
    ):
        # 펼친 구획은 제목 끝에 ▾ 다(소요대수 줄과 같은 꼴).
        assert f"<b>{title} ▾</b>" in label_texts
        assert title not in month_texts
    # 세부 글 줄은 라벨 칸 폭(좌우 여백 뺀 240px, 11px 글자) 안이다.
    budget = (DASHBOARD_LABEL_COLUMN_WIDTH_PX - 20) / 11
    assert all(
        _text_width_units(line) <= budget
        for detail in details
        for line in title_detail_lines(detail)
    )


def test_a_title_row_grows_with_its_detail_lines() -> None:
    assert title_row_height("") == TITLE_HEIGHT_PX
    one = title_row_height(SUMMARY_TITLE_DETAIL)
    assert one == SUMMARY_TITLE_HEIGHT_PX > TITLE_HEIGHT_PX
    assert title_row_height("진한 화살표만 가용을 깎았습니다 · 끝은 다음 날부터 셉니다") > one
    # 마디 하나가 칸보다 길면 그 줄만 말줄임한다.
    (line,) = title_detail_lines("가" * 60)
    assert line.endswith("…") and len(line) < 60


def test_an_empty_or_unordered_axis_is_refused() -> None:
    with pytest.raises(ValueError, match="비었습니다"):
        build_process_capa_canvas(
            process_label="P",
            months=[],
            summary=_summary(),
            thresholds=THRESHOLDS,
            selected_month=None,
        )
    with pytest.raises(ValueError, match="오름차순"):
        build_process_capa_canvas(
            process_label="P",
            months=[202612, 202611],
            summary=_summary(),
            thresholds=THRESHOLDS,
            selected_month=None,
        )


def test_no_table_or_heatmap_and_no_trace_dims_when_a_cell_is_clicked() -> None:
    """go.Table·go.Heatmap 은 점 선택이 없어 `on_select` 가 오지 않는다. 고르지 않은 점은 흐려지지
    않아야 한다(DESELECTDIM 0.2) — 클릭은 달을 고르는 것이지 칸을 강조하는 것이 아니다."""
    canvas = _canvas(dynamic=_dynamic())
    for figure in (canvas.labels, canvas.months):
        assert {trace.type for trace in figure.data} <= {"bar", "scatter"}
    for trace in _json(canvas.months)["data"]:
        assert trace["unselected"]["marker"]["opacity"] == 1
        if trace.get("mode") == "text":
            assert trace["unselected"]["textfont"]["color"] == trace["textfont"]["color"]


# ---------------------------------------------------------------------- 칸 표적


def test_every_cell_target_carries_its_month_row_and_hover() -> None:
    """칸마다 표적 하나 — 풍선 글이 있는 칸은 첫 trace(`hovertemplate`), ③ 의 빈 달 칸은 둘째 trace
    (`hoverinfo: "none"`, 풍선 상자 없음)다. 둘 다 달·행 id 를 실어 누르면 그 달이 골라진다."""
    canvas = _canvas(dynamic=_dynamic())
    targets = _targets(canvas)
    clickable = [row for row in canvas.row_ids if not row.startswith(("title:", "note:"))]

    assert len(targets) == len(clickable) * len(MONTHS)
    assert {(data[CUSTOMDATA_MONTH], data[CUSTOMDATA_ROW]) for data, _, _ in targets} == {
        (month, row) for month in MONTHS for row in clickable
    }
    for data, _, _ in targets:
        if not data[CUSTOMDATA_HOVER]:
            assert str(data[CUSTOMDATA_ROW]).startswith(("unit:", "exit:"))
    rate_months = [
        data[CUSTOMDATA_MONTH] for data, _, _ in targets if data[CUSTOMDATA_ROW] == ROW_RATE
    ]
    assert rate_months == MONTHS
    hovered, silent = (trace for trace in canvas.months.data if trace.customdata is not None)
    assert hovered.hovertemplate == "%{customdata[2]}<extra></extra>"
    assert all(item[CUSTOMDATA_HOVER] for item in hovered.customdata)
    assert silent.hoverinfo == "none" and silent.hovertemplate is None
    assert silent.customdata and not any(item[CUSTOMDATA_HOVER] for item in silent.customdata)
    assert hovered.marker.color == silent.marker.color == tokens.HIT_TARGET


def test_canvas_point_reads_the_month_and_row_of_a_clicked_cell() -> None:
    clicked = {"selection": {"points": [{"customdata": [202702, ROW_RATE, "풍선"]}]}}

    assert canvas_point(clicked) == (202702, ROW_RATE)
    assert canvas_point({"selection": {"points": [{"customdata": [202703.0, "x", ""]}]}}) == (
        202703,
        "x",
    )
    assert canvas_point({"selection": {"points": []}}) is None
    assert canvas_point({"selection": {"points": [{"customdata": None}]}}) is None
    assert canvas_point(None) is None


# ---------------------------------------------------------------------- ① 공식 기준


def test_rate_and_balance_cells_share_one_judgement_colour() -> None:
    """확보율 칸과 (부족일 때의) 과부족 칸은 같은 판정(`summary.판정`) 하나로 칠한다."""
    summary = _summary()
    canvas = _canvas(summary=summary)
    colours = {
        "secure": tokens.STATUS_SECURE,
        "warning": tokens.STATUS_WARNING,
        "shortage": tokens.STATUS_SHORTAGE,
    }
    statuses = summary["판정"].tolist()
    rate_fills = _row_fills(canvas, ROW_RATE)
    balance_fills = _row_fills(canvas, ROW_BALANCE)

    assert rate_fills == {index: colours[status] for index, status in enumerate(statuses)}
    assert balance_fills == {
        index: colours[status]
        for index, status in enumerate(statuses)
        if status in ("warning", "shortage")
    }
    assert set(statuses) == {"secure", "warning", "shortage"}


def test_the_balance_is_a_signed_whole_number() -> None:
    canvas = _canvas()
    texts = _row_texts(canvas, ROW_BALANCE)

    expected = ["+2", f"{MINUS}1", f"{MINUS}3", f"{MINUS}5", f"{MINUS}6", f"{MINUS}3", "+3", "+4"]
    shown = [texts[index][0].replace("<b>", "").replace("</b>", "") for index in range(8)]
    assert shown == expected
    # 칠한 칸만 굵다.
    assert texts[0][0] == "+2" and texts[1][0] == f"<b>{MINUS}1</b>"


def test_a_painted_balance_can_read_zero_on_the_noise_boundary() -> None:
    """판정은 반올림하지 않은 확보율을 보고 과부족은 9자리 반올림이라, 잡음 경계에서는 경고로 칠한
    칸에 「0」이 찍힌다 — 숫자는 Static Capa 「확보목표 총 필요대수」 와 같고 색은 확보율과 같다."""
    available = [float(value) for value in AVAILABLE]
    required = list(REQUIRED)
    available[0], required[0] = 10.95, 10.000000000000002
    canvas = _canvas(summary=_summary(available, required))

    assert _row_texts(canvas, ROW_BALANCE)[0][0] == "<b>0</b>"
    assert _row_fills(canvas, ROW_BALANCE)[0] == tokens.STATUS_WARNING
    assert _row_fills(canvas, ROW_RATE)[0] == tokens.STATUS_WARNING
    # 풍선의 계산 값도 9자리 반올림 뒤라 「−0.00」 이 아니라 「0.00」 이다
    # (가용 − 소요 × 기준 ≈ −1.8e-15).
    assert "확보기준 과부족 0대 (0.00)<br>" in _balance_hovers(canvas)[202611]


def _balance_hovers(canvas: ProcessCapaCanvas) -> dict[int, str]:
    return {
        int(data[CUSTOMDATA_MONTH]): str(data[CUSTOMDATA_HOVER])
        for data, _, _ in _targets(canvas)
        if data[CUSTOMDATA_ROW] == ROW_BALANCE
    }


def test_the_balance_hover_adds_the_unrounded_value_to_two_decimals() -> None:
    """칸 글자는 정수 그대로이고, 풍선은 정수 옆에 올림·내림 전 값(가용 − 소요 × 확보기준)을 소수
    둘째 자리 부호 있는 값으로 단다 — ③ 판정 식의 결과와 같은 숫자다."""
    canvas = _canvas()
    hovers = _balance_hovers(canvas)

    expected = {
        202611: "+2대 (+2.89)",  # 48 − 41.2 × 1.095 = 2.886
        202612: f"{MINUS}1대 ({MINUS}0.18)",  # 48 − 44.0 × 1.095 = −0.18
        202701: f"{MINUS}3대 ({MINUS}2.01)",  # 50 − 47.5 × 1.095 = −2.0125
        202703: f"{MINUS}6대 ({MINUS}5.60)",  # 52 − 52.6 × 1.095 = −5.597
        202706: "+4대 (+4.83)",
    }
    for month, text in expected.items():
        assert f"확보기준 과부족 {text}<br>" in hovers[month]
    assert f"가용 48.0 {MINUS} 소요 44.0 × 1.095 (부족은 올림, 여유는 내림)" in hovers[202612]
    assert _row_texts(canvas, ROW_BALANCE)[2][0] == f"<b>{MINUS}3</b>"


def test_the_reference_threshold_row_is_muted_and_never_emphasised() -> None:
    """「기준 확보율」 은 참고 줄이다 — 달마다 확보기준 %, 회색 글자, 면색·굵기 없음."""
    thresholds = SecurementThresholds(1.095, 0.995, ((202703, 1.2, None),))
    canvas = _canvas(summary=_summary(thresholds=thresholds), thresholds=thresholds)
    texts = _row_texts(canvas, ROW_THRESHOLD)

    assert [texts[index][0] for index in range(8)] == [
        "110%",
        "110%",
        "110%",
        "110%",
        "120%",
        "110%",
        "110%",
        "110%",
    ]
    assert {color for _, color in texts.values()} == {tokens.TEXT_MUTED}
    assert _row_fills(canvas, ROW_THRESHOLD) == {}
    label = next(
        item for item in _annotations(canvas.labels) if item["text"].endswith("기준 확보율")
    )
    assert label["text"] == "기준 확보율"
    assert label["font"]["color"] == tokens.TEXT_MUTED
    # 월별 예외가 있으면 과부족 라벨은 %를 떼고, 없으면 기본 기준을 단다.
    labels = {item["text"] for item in _annotations(canvas.labels)}
    assert "<b>확보기준 과부족</b>" not in labels and "확보기준 과부족" in labels
    assert "확보기준(110%) 과부족" in {item["text"] for item in _annotations(_canvas().labels)}


def test_home_rates_are_a_muted_row_without_fill() -> None:
    canvas = _canvas()
    texts = _row_texts(canvas, ROW_HOME_RATE)

    assert {color for _, color in texts.values()} == {tokens.TEXT_MUTED}
    assert texts[0][0] == "119%"
    assert _row_fills(canvas, ROW_HOME_RATE) == {}


def test_supply_and_demand_groups_take_their_own_surfaces() -> None:
    canvas = _canvas()
    month_rects = [
        shape for shape in _shapes(canvas.months) if shape["type"] == "rect" and shape["x0"] == 0
    ]
    label_rects = [shape for shape in _shapes(canvas.labels) if shape["type"] == "rect"]

    def covering(rects: list[dict[str, Any]], y: float) -> set[str]:
        return {shape["fillcolor"] for shape in rects if shape["y0"] < y < shape["y1"]}

    height = canvas.height
    for row, surface, label in (
        (ROW_OWNED, tokens.SUMMARY_SUPPLY_SURFACE, tokens.SUMMARY_SUPPLY_CLASSIFICATION),
        (ROW_AVAILABLE, tokens.SUMMARY_SUPPLY_SURFACE, tokens.SUMMARY_SUPPLY_CLASSIFICATION),
        (ROW_REQUIRED, tokens.SUMMARY_DEMAND_SURFACE, tokens.SUMMARY_DEMAND_CLASSIFICATION),
    ):
        center = _row_center(canvas, row)
        assert surface in covering(month_rects, center)
        assert label in covering(label_rects, 1 - (height - center) / height)


def test_product_rows_stripe_and_indent_under_the_demand_row() -> None:
    canvas = _canvas()
    centers = [_row_center(canvas, f"product:{name}") for name in SHARES]
    stripes = [
        {
            shape["fillcolor"]
            for shape in _shapes(canvas.months)
            if shape["type"] == "rect" and shape["x0"] == 0 and shape["y0"] < y < shape["y1"]
        }
        for y in centers
    ]
    # 흰 면(SURFACE)은 바탕이라 칠하지 않는다 — 줄무늬 행만 SURFACE_SUBTLE 사각형이 있다.
    assert [tokens.SURFACE_SUBTLE in found for found in stripes] == [False, True, False, True]
    products = [
        item for item in _annotations(canvas.labels) if item["text"].startswith("└ PRODUCT")
    ]
    assert len(products) == len(SHARES)
    assert {item["xshift"] for item in products} == {10 + 14}
    parent = _row_texts(canvas, ROW_REQUIRED)
    for index in range(8):
        children = sum(float(_row_texts(canvas, f"product:{name}")[index][0]) for name in SHARES)
        value = float(parent[index][0].replace("<b>", "").replace("</b>", ""))
        assert children == pytest.approx(value, abs=0.25)


def test_available_cells_warn_when_owned_minus_lent_differs() -> None:
    available = [float(value) for value in AVAILABLE]
    available[2] = 49.0
    canvas = _canvas(summary=_summary(available))
    texts = _row_texts(canvas, ROW_AVAILABLE)

    assert texts[2][0] == "49.0 ⚠"
    assert texts[1][0] == "48.0"
    hover = next(
        data[CUSTOMDATA_HOVER]
        for data, _, _ in _targets(canvas)
        if data[CUSTOMDATA_ROW] == ROW_AVAILABLE and data[CUSTOMDATA_MONTH] == 202701
    )
    assert "보유 54.0 − 대여 4.0 = 50.0" in hover and "⚠" in hover


# ---------------------------------------------------------------------- 띠·지금 보는 달


def test_shortage_months_get_a_band_and_a_header_strip_and_the_chosen_month_a_border() -> None:
    summary = _summary()
    canvas = _canvas(summary=summary, dynamic=_dynamic())
    shapes = _shapes(canvas.months)
    short = [index for index, status in enumerate(summary["판정"]) if status != "secure"]
    header_bottom = canvas.height - 36

    bands = [shape for shape in shapes if shape.get("fillcolor") == tokens.SHORTAGE_MONTH_BAND]
    assert sorted(shape["x0"] for shape in bands) == short
    # 띠는 머리 아래부터 캔버스 끝(②~④ 포함)까지 이어지고, 행 면 위·칸 색 아래에 깔린다.
    assert {(shape["y0"], shape["y1"], shape["layer"]) for shape in bands} == {
        (0, header_bottom, "below")
    }
    strips = [
        shape
        for shape in shapes
        if shape.get("fillcolor") == tokens.STATUS_SHORTAGE and shape["y0"] == header_bottom
    ]
    assert sorted(round(shape["x0"]) for shape in strips) == short
    assert {shape["y1"] - shape["y0"] for shape in strips} == {4}

    accents = [shape for shape in shapes if shape.get("line", {}).get("color") == tokens.ACCENT]
    underline = next(shape for shape in accents if shape["type"] == "line")
    border = next(shape for shape in accents if shape["type"] == "rect")
    selected = MONTHS.index(202702)
    assert selected < underline["x0"] < underline["x1"] < selected + 1
    assert underline["line"]["width"] == 1.5
    assert header_bottom < underline["y0"] < canvas.height
    assert selected <= border["x0"] < border["x1"] <= selected + 1
    assert border["y1"] - border["y0"] >= canvas.height - 2


def test_no_accent_when_the_chosen_month_is_off_the_axis() -> None:
    for selected in (None, 202501):
        shapes = _shapes(_canvas(selected=selected).months)
        assert not [s for s in shapes if s.get("line", {}).get("color") == tokens.ACCENT]
        assert tokens.ACCENT not in json.dumps(_json(_canvas(selected=selected).months))


# ---------------------------------------------------------------------- ② 설비 일정 기준 가용


def test_the_cross_check_row_paints_only_when_both_bases_fall_short() -> None:
    dynamic = _dynamic()
    summary = _summary()
    canvas = _canvas(summary=summary, dynamic=dynamic)
    texts = _row_texts(canvas, ROW_DYNAMIC_COMPARE)
    fills = _row_fills(canvas, ROW_DYNAMIC_COMPARE)
    gaps = _plan_values(dynamic, "과부족")

    for index, month in enumerate(MONTHS):
        static_short = summary["판정"].iloc[index] != "secure"
        dynamic_short = round(gaps[month], 9) < 0
        if static_short and dynamic_short:
            assert texts[index] == ("<b>기준✕·일정✕</b>", tokens.TEXT)
            assert fills[index] == tokens.STATUS_SHORTAGE
        elif static_short:
            assert texts[index] == ("기준✕·일정✓", tokens.TEXT_MUTED)
            assert index not in fills
        elif dynamic_short:
            assert texts[index] == ("기준✓·일정✕", tokens.TEXT_MUTED)
        else:
            assert index not in texts and index not in fills


def test_an_owned_short_month_asks_for_investment_in_the_cross_check() -> None:
    """기준✕·일정✓ 인 달의 원인이 「보유로도 부족」이면 풍선이 투자 검토를 함께 적는다(설계
    logic_final 3절 표, Guide 판정 대조 표)."""
    summary = _summary()
    month = 202612
    assert summary.loc[summary["생산계획년월"].eq(month), "부족 원인"].item() == "대여 영향"

    def compare_hover(frame: pd.DataFrame) -> str:
        canvas = _canvas(summary=frame, dynamic=_dynamic())
        return str(
            next(
                data[CUSTOMDATA_HOVER]
                for data, _, _ in _targets(canvas)
                if data[CUSTOMDATA_ROW] == ROW_DYNAMIC_COMPARE and data[CUSTOMDATA_MONTH] == month
            )
        )

    assert "기준✕·일정✓" not in compare_hover(summary)  # 풍선에 칸 글은 없다
    assert "투자 검토" not in compare_hover(summary)
    owned_short = summary.copy()
    owned_short.loc[owned_short["생산계획년월"].eq(month), "부족 원인"] = "보유로도 부족"
    hover = compare_hover(owned_short)
    assert "공식은 부족, 설비 일정으로는 충족" in hover
    assert "원인: 보유로도 부족 — 투자 검토" in hover


def test_the_target_balance_paints_only_short_months_and_shows_the_shortened_value() -> None:
    dynamic = _dynamic()
    canvas = _canvas(dynamic=dynamic)
    fills = _row_fills(canvas, ROW_DYNAMIC_BALANCE)
    gaps = _plan_values(dynamic, "과부족")
    afters = _plan_values(dynamic, "단축후과부족")
    center = _row_center(canvas, ROW_DYNAMIC_BALANCE)
    lines = [(x, y, text) for x, y, text, _ in _texts(canvas) if abs(y - center) < 18]

    for index, month in enumerate(MONTHS):
        gap = round(gaps[month], 9)
        assert (index in fills) == (gap < 0)
        if index in fills:
            assert fills[index] == tokens.STATUS_SHORTAGE
        after = afters[month]
        second = [text for x, y, text in lines if int(x) == index and y < center]
        if abs(after - gap) > 1e-9:
            assert second and second[0].replace("<b>", "").startswith("→ ")
    # 목표는 달마다 같은 확보기준이라 라벨에 % 가 붙는다.
    assert "목표(110%) 과부족" in {item["text"] for item in _annotations(canvas.labels)}


def test_past_months_are_muted_and_unpainted_in_the_schedule_rows() -> None:
    """오늘이 든 생산월보다 앞선 달은 단축으로 바꿀 수 없다 — 「기한 지남」으로 흐리게 둔다."""
    dynamic = _dynamic(today=date(2027, 2, 10))
    canvas = _canvas(dynamic=dynamic)
    past = [index for index, month in enumerate(MONTHS) if month < 202702]

    for row in (ROW_DYNAMIC_COMPARE, "dynamic_available", "dynamic_delta", ROW_DYNAMIC_BALANCE):
        texts = _row_texts(canvas, row)
        fills = _row_fills(canvas, row)
        for index in past:
            if index in texts:
                assert texts[index][1] == tokens.TEXT_MUTED, (row, index)
            assert index not in fills, (row, index)


def test_the_today_line_runs_through_the_schedule_body_but_not_the_titles() -> None:
    canvas = _canvas(dynamic=_dynamic())
    lines = [
        shape
        for shape in _shapes(canvas.months)
        if shape["type"] == "line" and shape.get("line", {}).get("dash") == "dash"
    ]
    # ②·③·④ 본문 셋 — 제목 줄에서 끊긴다.
    assert len(lines) == 3
    assert len({shape["x0"] for shape in lines}) == 1
    assert "점선은 오늘(11.10)" in {item["text"] for item in _annotations(canvas.labels)}
    assert not [
        shape
        for shape in _shapes(_canvas(dynamic=_dynamic(today=date(2028, 1, 1))).months)
        if shape["type"] == "line" and shape.get("line", {}).get("dash") == "dash"
    ]


def test_a_baseline_only_process_shows_only_the_availability_rows() -> None:
    canvas = _canvas(dynamic=_dynamic(has_units=False))

    assert canvas.row_ids[-1] == "note:no_units"
    assert "title:units" not in canvas.row_ids and "title:downtime" not in canvas.row_ids


# ---------------------------------------------------------------------- ③ 신규 설비


def _marker_traces(canvas: ProcessCapaCanvas, symbol: str) -> list[dict[str, Any]]:
    return [
        trace
        for trace in _json(canvas.months)["data"]
        if trace.get("mode") == "markers" and trace["marker"]["symbol"] == symbol
    ]


def test_unit_rows_draw_one_line_per_unit_with_the_pull_and_its_badges() -> None:
    dynamic = _dynamic()
    canvas = _canvas(dynamic=dynamic)
    events = dynamic.unit_events
    shortened = events.loc[events["줄"].eq(ROW_SHORTENED)]
    virtual = events.loc[events["줄"].eq(ROW_VIRTUAL)]

    assert not shortened.empty and not virtual.empty
    heads = _marker_traces(canvas, "triangle-left")
    assert len(heads) == 1 and len(heads[0]["x"]) == len(shortened)
    assert sorted(heads[0]["x"]) == pytest.approx(sorted(shortened["목표 기여 위치"]))
    pulls = next(
        trace
        for trace in _json(canvas.months)["data"]
        if trace.get("mode") == "text" and trace.get("textposition") == "middle left"
    )
    assert sorted(pulls["text"]) == sorted(
        f"<b>{MINUS}{days}일</b>" for days in shortened["단축일수"]
    )
    badges = [item for item in _annotations(canvas.months) if item["text"] == "<b>반입 전</b>"]
    assert len(badges) == int(shortened["반입 전"].sum()) > 0
    assert {item["bgcolor"] for item in badges} == {tokens.STATUS_WARNING}
    circles = [shape for shape in _shapes(canvas.months) if shape["type"] == "circle"]
    assert len(circles) == len(virtual)
    assert {shape["fillcolor"] for shape in circles} == {tokens.STATUS_SHORTAGE}
    assert {shape["line"]["dash"] for shape in circles} == {"dot"}
    # 단축 줄의 둘째 줄은 「기존 → 단축」, 신규 줄은 「반입 · Qual · Qual상태」, 추가N 은
    # 「필요 · 신규」 다.
    details = [item["text"] for item in _annotations(canvas.labels)]
    assert any(text.startswith("기존 ") and "→ 단축 " in text for text in details)
    assert any(text.startswith("필요 ") and text.endswith("· 신규") for text in details)
    exits = _marker_traces(canvas, "triangle-down")
    assert exits and len(exits[0]["x"]) >= 1


def test_contribution_starts_take_the_confirmation_colour() -> None:
    dynamic = _dynamic()
    canvas = _canvas(dynamic=dynamic)
    starts = _marker_traces(canvas, "circle")[0]
    colours = tokens.QUAL_CONFIRMATION_COLORS

    assert set(starts["marker"]["color"]) <= set(colours.values())
    assert colours["확정"] in starts["marker"]["color"]
    assert colours["계획"] in starts["marker"]["color"]


def test_a_shortened_unit_hover_is_three_short_lines() -> None:
    """③ 단축 호기 풍선은 세 줄이다(2026-10-24 사용자 결정 2-1 (가) — 시안 그대로). 반입일 ·
    Qual상태 · 대상 월은 그림 표지(◆ · ● 색)와 CSV 가 말해 적지 않고, 날짜는 줄 라벨처럼
    짧게(올해 밖이면 연도) 적는다."""
    event: dict[str, Any] = dict.fromkeys(UNIT_EVENT_COLUMNS)
    event.update(
        {
            "줄": ROW_SHORTENED,
            "호기": "SMP-DAF-11",
            "Model": "DEMO-X1",
            "모듈 수": 1,
            "반입일정": date(2026, 11, 1),
            "Qual일정": date(2026, 11, 15),
            "기여 시작": date(2026, 11, 16),
            "Qual상태": "확정",
            "모듈별 Qual": (),
            "목표 Qual": date(2026, 10, 23),
            "목표 기여 시작": date(2026, 10, 24),
            "단축일수": 23,
            "늘어난 환산대수": 0.1,
            "반입 전": True,
            "대상 월": 202611,
            "해소 기여 월": (202611,),
        }
    )
    today = date(2026, 10, 24)

    assert _unit_hover(event, today).split("<br>") == [
        f"SMP-DAF-11 · {MINUS}23일 · DEMO-X1",
        "Qual 11.15 → 목표 10.23 · 10.24부터 기여 +0.10대",
        "해소 26.11 · ⚠ 반입 전",
    ]
    # 모듈 묶음이면 첫 줄 끝에 「· 모듈 N」, ⚠ 는 반입 전인 호기에만, 해소 달이 없으면 그
    # 조각이 빠진다.
    grouped = {**event, "모듈 수": 2, "반입 전": False, "해소 기여 월": ()}
    assert _unit_hover(grouped, today).split("<br>") == [
        f"SMP-DAF-11 · {MINUS}23일 · DEMO-X1 · 모듈 2",
        "Qual 11.15 → 목표 10.23 · 10.24부터 기여 +0.10대",
    ]
    # 해가 다르면 연도가 붙는다(줄 라벨과 같은 꼴).
    assert "Qual 26.11.15 → 목표 26.10.23" in _unit_hover(event, date(2027, 1, 5))


def test_a_unit_month_cell_hover_shows_that_months_gain() -> None:
    """③ 단축 · 추가N 줄의 달 칸 풍선은 그 달 몫을 적는다 — 줄 이름 칸의 「+0.03대」 는 대상 월
    구간의 몫(호기 하나의 요약)이라, 뒤 달 칸에 그대로 띄우면 그 달 증분으로 잘못 읽힌다(E2E
    2026-10-26). 그 달 몫이 없는 달 칸은 숫자를 뺀다."""
    dynamic = _dynamic()
    events = dynamic.unit_events
    event = events.loc[events["호기"].astype(str).eq("EQ-22")].iloc[0]
    shares = dict(event["월별 늘어난 환산대수"])
    target_month = int(event["대상 월"])
    later = next(month for month in sorted(shares) if month > target_month)
    canvas = _canvas(dynamic=dynamic)
    label = _label_hovers(canvas)["unit:EQ-22"]
    cells = {
        int(data[CUSTOMDATA_MONTH]): str(data[CUSTOMDATA_HOVER])
        for data, _, _ in _targets(canvas)
        if data[CUSTOMDATA_ROW] == "unit:EQ-22" and data[CUSTOMDATA_HOVER]
    }

    assert f"기여 +{float(event['늘어난 환산대수']):,.2f}대" in label
    assert f"이 달 +{shares[target_month]:,.2f}대" in cells[target_month]
    assert f"이 달 +{shares[later]:,.2f}대" in cells[later]
    assert f"+{float(event['늘어난 환산대수']):,.2f}대" not in cells[later]
    # 줄 수와 다른 줄은 줄 이름 칸 풍선과 같다.
    assert len(cells[later].split("<br>")) == len(label.split("<br>"))
    assert cells[later].split("<br>")[0] == label.split("<br>")[0]
    for month, hover in cells.items():
        if month not in shares:
            assert "이 달" not in hover and "대" not in hover.split("<br>")[1]


def test_unit_hovers_stay_within_three_lines_and_an_assumption_adds_the_fourth() -> None:
    dynamic = _dynamic()
    official = _label_hovers(_canvas(dynamic=dynamic))
    marked = DynamicCanvasInput(**{**dynamic.__dict__, "official_pulls": {"EQ-21": (45, 0)}})
    assumed = _label_hovers(_assumed_canvas(110, set(MONTHS), dynamic=marked))
    units = [row for row in official if row.startswith(("unit:", "exit:"))]

    assert len(units) >= 5 and set(units) == set(official)
    assert all(1 <= len(official[row].split("<br>")) <= 3 for row in units)
    assert all("UPEH" not in hover for hover in official.values())
    for row in (row for row in assumed if row.startswith("unit:")):
        lines = assumed[row].split("<br>")
        assert len(lines) <= 4 and lines[-1].startswith("UPEH 가정 계획")
        assert lines[:-1] == official[row].split("<br>")


def test_a_unit_hover_shows_only_on_the_months_its_drawing_spans() -> None:
    """풍선은 그 호기 그림(선 · 화살표 · 표지)이 걸친 달 칸과 줄 이름 칸에서만 뜬다. 빈 달 칸도
    표적은 있어(풍선 없는 trace) 누르면 그 달이 골라진다."""
    event: dict[str, Any] = dict.fromkeys(UNIT_EVENT_COLUMNS)
    event.update(
        {
            "줄": ROW_SHORTENED,
            "호기": "EQ-90",
            "모듈 수": 1,
            "반입일정": date(2026, 12, 5),
            "Qual일정": date(2027, 2, 10),
            "기여 시작": date(2027, 2, 11),
            "Qual상태": "계획",
            "모듈별 Qual": (),
            "목표 Qual": date(2026, 12, 20),
            "목표 기여 시작": date(2026, 12, 21),
            "단축일수": 52,
            "늘어난 환산대수": 0.5,
            "반입 전": False,
            "해소 기여 월": (202701,),
            "반입 위치": 1.48,
            "기여 시작 위치": 3.7,
            "기여 시작 축 밖": False,
            "목표 기여 위치": 1.97,
        }
    )
    events = pd.DataFrame([event], columns=list(UNIT_EVENT_COLUMNS))
    canvas = _canvas(dynamic=_dynamic(unit_events=events, exits=pd.DataFrame()))

    # ◆ 반입(12월) · ◀ 목표(12월) · ● 기여 시작(2월) — 12월~2월만.
    assert _hover_months(canvas, "unit:EQ-90") == [202612, 202701, 202702]
    assert "unit:EQ-90" in _label_hovers(canvas)
    cells = {
        int(data[CUSTOMDATA_MONTH]): data[CUSTOMDATA_HOVER]
        for data, _, _ in _targets(canvas)
        if data[CUSTOMDATA_ROW] == "unit:EQ-90"
    }
    assert sorted(cells) == MONTHS
    assert {month for month, hover in cells.items() if not hover} == set(MONTHS) - {
        202612,
        202701,
        202702,
    }
    assert canvas_point(
        {"selection": {"points": [{"customdata": [202705, "unit:EQ-90", ""]}]}}
    ) == (202705, "unit:EQ-90")

    # 「반입 전」 배지는 「−N일」 왼쪽이라 그림이 앞 달까지 걸친다.
    early = {**event, "반입 전": True, "목표 기여 위치": 1.3, "반입 위치": 1.48}
    canvas = _canvas(
        dynamic=_dynamic(
            unit_events=pd.DataFrame([early], columns=list(UNIT_EVENT_COLUMNS)),
            exits=pd.DataFrame(),
        )
    )
    assert _hover_months(canvas, "unit:EQ-90")[0] == 202611


def test_hover_months_cover_every_drawn_mark_of_the_fixture_units() -> None:
    """풍선 칸(`_unit_span`)과 그림(`_draw_unit`)은 같은 자리(`_unit_marks`)에서 나온다 — 표지가
    그려진 달(가운데 ± 반지름)은 모두 풍선 칸이고 풍선 칸은 이어진 한 덩어리다."""
    canvas = _canvas(dynamic=_dynamic())
    centers = {
        str(data[CUSTOMDATA_ROW]): y
        for data, y, _ in _targets(canvas)
        if str(data[CUSTOMDATA_ROW]).startswith(("unit:", "exit:"))
    }
    marks: dict[str, set[int]] = {row: set() for row in centers}
    for trace in _json(canvas.months)["data"]:
        if trace.get("mode") != "markers":
            continue
        half = trace["marker"]["size"] / 2 / tokens.MONTH_COLUMN_WIDTH_PX
        for x, y in zip(trace["x"], trace["y"], strict=True):
            for row, center in centers.items():
                if y == pytest.approx(center):
                    for edge in (x - half, x + half - 1e-9):
                        marks[row].add(MONTHS[min(len(MONTHS) - 1, max(0, math.floor(edge)))])
    assert any(marks.values())
    for row, months in marks.items():
        hovered = _hover_months(canvas, row)
        assert months <= set(hovered), row
        if hovered:
            first, last = MONTHS.index(hovered[0]), MONTHS.index(hovered[-1])
            assert hovered == MONTHS[first : last + 1], row


def test_a_mark_on_a_month_edge_opens_both_months() -> None:
    """달 경계에 선 표지는 앞 달 칸에도 반이 그려진다 — 그 반쪽에서도 풍선이 뜬다(10-24 리뷰). 표본
    EQ-26 의 ◆ 반입(반입 다음 날 04.21 = Cut-off 10일 생산월 202705 첫날)은 x 6.0 에 선다."""
    canvas = _canvas(dynamic=_dynamic())
    center = _row_center(canvas, "unit:EQ-26")
    diamonds = next(
        trace
        for trace in _json(canvas.months)["data"]
        if trace.get("marker", {}).get("symbol") == "diamond"
    )
    arrival = [x for x, y in zip(diamonds["x"], diamonds["y"], strict=True) if y == center]

    assert arrival == [6.0]
    assert _hover_months(canvas, "unit:EQ-26")[0] == MONTHS[5]


def test_a_text_estimate_grazing_a_month_edge_does_not_open_that_month() -> None:
    """「−N일」 · 「반입 전」 배지 폭은 넘치지 않게 잡은 어림(위 끝)이라 렌더보다 넓다. 어림만 앞 달
    경계를 넘고 그림은 그 달에 없는 줄은 앞 달에 풍선이 뜨지 않는다(10-24 리뷰 — 합성 화면
    SMP-DAF-12 「−198일 · 반입 전」: 어림 왼쪽 끝 3.9993, 렌더 4.045)."""
    event: dict[str, Any] = dict.fromkeys(UNIT_EVENT_COLUMNS)
    event.update(
        {
            "줄": ROW_SHORTENED,
            "호기": "EQ-91",
            "모듈 수": 2,
            "반입일정": date(2027, 5, 1),
            "Qual일정": date(2027, 5, 20),
            "기여 시작": date(2027, 5, 21),
            "Qual상태": "계획",
            "모듈별 Qual": (),
            "목표 Qual": date(2027, 3, 28),
            "목표 기여 시작": date(2027, 3, 29),
            "단축일수": 198,
            "늘어난 환산대수": 0.5,
            "반입 전": True,
            "해소 기여 월": (),
            "기여 시작 위치": 6.5,
            "기여 시작 축 밖": False,
            "목표 기여 위치": 4.9333,
        }
    )
    canvas = _canvas(
        dynamic=_dynamic(
            unit_events=pd.DataFrame([event], columns=list(UNIT_EVENT_COLUMNS)),
            exits=pd.DataFrame(),
        )
    )
    # 어림 그대로 세면 왼쪽 끝이 202702 칸(열 3)으로 0.07px 넘어간다.
    estimated_left = (
        4.9333
        - 0.08
        - (_text_width_units(f"{MINUS}198일") * 11 + 8 + _text_width_units("반입 전") * 10 + 4)
        / tokens.MONTH_COLUMN_WIDTH_PX
    )
    assert 3.99 < estimated_left < 4.0

    assert _hover_months(canvas, "unit:EQ-91")[0] == MONTHS[4]


def _resolved_ticks(canvas: ProcessCapaCanvas, row_id: str) -> list[float]:
    """그 줄의 해소 눈금(굵기 2 가로 도형)의 왼쪽 x."""
    center = _row_center(canvas, row_id)
    return [
        shape["x0"]
        for shape in _json(canvas.months)["layout"].get("shapes", [])
        if shape.get("type") == "line"
        and shape.get("line", {}).get("width") == 2
        and abs(shape["y0"] - center) < UNIT_ROW_HEIGHT_PX / 2
    ]


def test_a_released_unit_hover_drops_the_official_resolved_months() -> None:
    """UPEH 가정으로 단축이 필요 없어진 흐린 신규 줄은 공식 계획의 해소 기여 월을 들고 오지만 그림에
    해소 눈금이 없다 — 풍선 셋째 줄에도 「해소」 를 적지 않는다(10-24 리뷰). 단축 · 추가N 줄은
    그대로다."""
    dynamic = _dynamic()
    events = dynamic.unit_events.copy()
    released = events["호기"].astype(str).eq("EQ-24").to_numpy()
    assert events.loc[released, "해소 기여 월"].iloc[0]
    events.loc[released, "줄"] = ROW_NEW
    marked = DynamicCanvasInput(
        **{**dynamic.__dict__, "unit_events": events, "official_pulls": {"EQ-24": (62, 0)}}
    )
    canvas = _canvas(dynamic=marked)
    hovers = _label_hovers(canvas)

    assert len(_resolved_ticks(_canvas(dynamic=dynamic), "unit:EQ-24")) == 3
    assert _resolved_ticks(canvas, "unit:EQ-24") == []
    assert "해소" not in hovers["unit:EQ-24"]
    assert hovers["unit:EQ-24"].split("<br>")[-1] == f"UPEH 가정 계획 · 공식 {MINUS}62일 → 가정 0일"
    assert "해소 " in hovers["unit:EQ-25"] and "해소 " in hovers["unit:추가1"]


def _many_new_units(count: int) -> pd.DataFrame:
    rows = []
    for number in range(count):
        row: dict[str, Any] = dict.fromkeys(UNIT_EVENT_COLUMNS)
        row.update(
            {
                "줄": ROW_NEW,
                "호기": f"EQ-{number:03d}",
                "모듈 수": 1,
                "반입일정": date(2026, 12, 1),
                "Qual일정": date(2027, 1, 5),
                "기여 시작": date(2027, 1, 6),
                "Qual상태": "계획",
                "모듈별 Qual": (),
                "해소 기여 월": (),
                "반입 전": False,
                "기여 시작 축 밖": False,
                "반입 위치": 1.4,
                "기여 시작 위치": 2.5,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=list(UNIT_EVENT_COLUMNS))


def test_unit_rows_stop_at_thirty_with_a_more_line() -> None:
    events = _many_new_units(ROW_LIMIT + 5)
    capped = _canvas(dynamic=_dynamic(unit_events=events, exits=pd.DataFrame()))
    full = _canvas(dynamic=_dynamic(unit_events=events, exits=pd.DataFrame(), show_all_units=True))

    assert capped.hidden_units == 5
    assert sum(row.startswith("unit:") for row in capped.row_ids) == ROW_LIMIT
    assert "note:more_units" in capped.row_ids
    assert full.hidden_units == 0
    assert sum(row.startswith("unit:") for row in full.row_ids) == ROW_LIMIT + 5
    assert "note:more_units" not in full.row_ids
    assert full.height > capped.height


def test_an_axis_without_new_units_or_downtime_says_so_in_one_line() -> None:
    canvas = _canvas(
        dynamic=_dynamic(
            unit_events=pd.DataFrame(columns=list(UNIT_EVENT_COLUMNS)),
            exits=pd.DataFrame(),
            arrows=pd.DataFrame(),
            steady_units=0,
            undated_notice="",
        )
    )

    assert "note:no_new_units" in canvas.row_ids
    assert "note:no_downtime" in canvas.row_ids


# ---------------------------------------------------------------------- ④ 비가동


def test_arrows_are_solid_only_where_they_cut_availability() -> None:
    dynamic = _dynamic()
    canvas = _canvas(dynamic=dynamic)
    arrows = dynamic.arrows
    traces = _json(canvas.months)["data"]
    loss_colour = tokens.EQUIPMENT_STAGE_COLORS["운영 비가동"]

    solid = next(
        trace
        for trace in traces
        if trace.get("mode") == "lines" and trace["line"]["color"] == loss_colour
    )
    idle = next(
        trace
        for trace in traces
        if trace.get("mode") == "lines"
        and trace["line"]["color"] == tokens.TEXT_MUTED
        and trace["line"]["dash"] == "dot"
    )
    cutting = int(arrows["가용 감소"].sum())
    assert solid["line"]["width"] == 3
    assert len([x for x in solid["x"] if x is None]) == cutting
    assert len([x for x in idle["x"] if x is None]) == len(arrows) - cutting
    heads = _marker_traces(canvas, "triangle-right")
    assert len(heads[0]["x"]) == cutting
    words = next(
        trace
        for trace in traces
        if trace.get("mode") == "text"
        and trace["textfont"]["color"] == tokens.TEXT_MUTED
        and trace.get("textposition") == "middle right"
    )["text"]
    assert any("◂ 이전부터" in text for text in words)
    assert any("계속 ▸" in text for text in words)
    assert any(text.startswith("셋업") for text in words)


def test_arrow_rows_carry_the_month_loss_in_their_hover() -> None:
    dynamic = _dynamic()
    canvas = _canvas(dynamic=dynamic)
    first = dynamic.arrows.loc[dynamic.arrows["가용 감소"]].iloc[0]
    month, loss = first["달별 손실"][0]
    hover = next(
        data[CUSTOMDATA_HOVER]
        for data, _, _ in _targets(canvas)
        if data[CUSTOMDATA_ROW] == f"arrow:{first['설비키']}#0" and data[CUSTOMDATA_MONTH] == month
    )

    # 한 자리로 0 이 되는 손실은 두 자리로 적는다.
    digits = 1 if round(abs(loss), 1) > 0 else 2
    assert first["비가동유형"] in hover
    assert f"이 달 {MINUS}{abs(loss):.{digits}f} (환산대수)" in hover


def _row_hover(canvas: ProcessCapaCanvas, row_id: str) -> str:
    return str(
        next(
            data[CUSTOMDATA_HOVER]
            for data, _, _ in _targets(canvas)
            if data[CUSTOMDATA_ROW] == row_id and data[CUSTOMDATA_HOVER]
        )
    )


def test_unit_and_downtime_labels_leave_the_module_count_to_the_hovers() -> None:
    """라벨에는 「N모듈」 을 적지 않는다(2026-10-22 사용자 요청). 모듈 묶음은 풍선 첫 줄 「· 모듈
    N」 이고, ④ 풍선은 화살표 줄마다 그 모듈의 설비명을 앞에 적는다. 단독 호기는 모듈 글이 없다."""
    canvas = _canvas(dynamic=_dynamic())

    assert "모듈" not in json.dumps(_annotations(canvas.labels), ensure_ascii=False)
    unit_lines = _label_hovers(canvas)["unit:EQ-21"].split("<br>")
    assert unit_lines[0].endswith("EQ-21 · −1일 · 모듈 2")
    # 모듈마다 Qual 이 갈리면 셋째 줄에 그 범위만 — 모듈마다의 날짜는 가용설비 현황 Main 이 적는다.
    assert unit_lines[2].endswith("모듈 Qual 12.20~12.22")
    assert "EQ-21A" not in "".join(unit_lines)
    assert "모듈" not in _label_hovers(canvas)["unit:EQ-22"]

    first, *arrows = _row_hover(canvas, "arrow:EQ-21#0").split("<br>")
    assert first.endswith("EQ-21 · 모듈 2")
    assert arrows and all(line.startswith("EQ-21A · 셋업 · ") for line in arrows)
    single_first, *single = _row_hover(canvas, "arrow:EQ-02#0").split("<br>")
    assert "모듈" not in single_first
    assert all(line.startswith("정기 PM · ") for line in single)


def test_a_stopping_module_group_names_its_modules_in_the_hover() -> None:
    exits = pd.DataFrame(
        [
            {
                "호기": "EQ-30",
                "설비명": "EQ-30A, EQ-30B",
                "Model": "M-1",
                "모듈 수": 2,
                "기존설비여부": "Y",
                "반출이설일": date(2027, 3, 10),
                "반출이설구분": "정지",
                "반출이설 위치": 4.3,
            }
        ]
    )
    canvas = _canvas(dynamic=_dynamic(exits=exits))

    labels = [item["text"] for item in _annotations(canvas.labels)]
    assert "<b>EQ-30</b>" in labels
    assert _label_hovers(canvas)["exit:EQ-30"].split("<br>") == [
        "EQ-30 · M-1 · 모듈 2",
        "정지 27.03.10부터 가용에서 빠집니다",
    ]
    # ▼ 가 든 달 칸에만 풍선이 뜬다.
    assert _hover_months(canvas, "exit:EQ-30") == [202703]


# ---------------------------------------------------------------------- 검증 경로·테마


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_canvas_matches_the_validated_path(mode: str) -> None:
    """도형·주석은 검증 없이 넣는다(`flush_layout_items`). 전부 검증한 경로와 JSON 이 같다."""
    theme._LOCAL.mode = mode
    dynamic = _dynamic()
    with plotly_validation():
        checked = _canvas(dynamic=dynamic)
    fast = _canvas(dynamic=dynamic)

    assert _json(fast.labels) == _json(checked.labels)
    assert _json(fast.months) == _json(checked.months)


def test_the_dark_theme_paints_with_dark_tokens() -> None:
    theme._LOCAL.mode = "dark"
    canvas = _canvas(dynamic=_dynamic())
    dark = tokens._PALETTES["dark"]
    shapes = _shapes(canvas.months)

    assert dark["SHORTAGE_MONTH_BAND"] in {shape.get("fillcolor") for shape in shapes}
    assert dark["SUMMARY_SUPPLY_SURFACE"] in {shape.get("fillcolor") for shape in shapes}
    assert _json(canvas.months)["layout"]["paper_bgcolor"] == dark["CHART_CANVAS"]
    assert tokens._PALETTES["light"]["SHORTAGE_MONTH_BAND"] not in json.dumps(_json(canvas.months))


def test_a_monthly_target_names_itself_once_in_the_titles() -> None:
    target = MonthlyTarget(1.095, ((202703, 1.2),))
    canvas = _canvas(dynamic=_dynamic(target=target))
    texts = json.dumps(_annotations(canvas.labels), ensure_ascii=False)

    assert "단축 목표 = 확보기준(달마다)" in texts
    assert "목표 과부족" in {item["text"] for item in _annotations(canvas.labels)}


# ---------------------------------------------------------------------- UPEH 가정


def _assumed_summary(percent: int, months: set[int]) -> pd.DataFrame:
    """구간 달의 소요를 ÷f 한 요약 — 페이지와 같은 길(`scale_securement_rate` → 같은 요약 함수)."""
    from capa_simulation.services.upeh_assumption import scale_securement_rate

    available = [float(value) for value in AVAILABLE]
    rate = pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "공정": PROCESS,
            "가용대수": available,
            "소요대수": REQUIRED,
            "확보율": [a / r for a, r in zip(available, REQUIRED, strict=True)],
        }
    )
    scaled = scale_securement_rate(rate, (percent, tuple(sorted(months))))
    owned = pd.DataFrame({"생산계획년월": MONTHS, "공정": PROCESS, "설비보유": OWNED})
    lent = pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "공정": PROCESS,
            "설비대여평가": [o - a for o, a in zip(OWNED, AVAILABLE, strict=True)],
        }
    )
    return build_process_capa_summary(
        scaled, owned, lent, process=PROCESS, months=MONTHS, thresholds=THRESHOLDS
    )


def _assumed_canvas(
    percent: int, months: set[int], *, dynamic: DynamicCanvasInput | None = None
) -> ProcessCapaCanvas:
    return build_process_capa_canvas(
        process_label="Die Attach",
        months=MONTHS,
        summary=_summary(),
        thresholds=THRESHOLDS,
        selected_month=202702,
        dynamic=dynamic,
        assumption=AssumptionCanvasInput(
            percent=percent, months=frozenset(months), summary=_assumed_summary(percent, months)
        ),
    )


def test_three_upeh_rows_stand_at_the_end_of_the_official_section() -> None:
    """① 끝(기준 확보율 아래)에 세 줄이 서고, 확보율 줄의 세로 자리는 그대로다(배포 화면 확인
    상수)."""
    window = {202702, 202703, 202704}
    official = _canvas(products=False, home=False)
    assumed = _assumed_canvas(110, window)

    ids = list(assumed.row_ids)
    position = ids.index(ROW_THRESHOLD)
    assert ids[position + 1 : position + 4] == [ROW_UPEH_REQUIRED, ROW_UPEH_RATE, ROW_UPEH_BALANCE]
    assert _row_center(assumed, ROW_RATE) - assumed.height == pytest.approx(
        _row_center(official, ROW_RATE) - official.height
    )
    # 구간 달만 값이고, 밖은 빈칸에 「구간 밖 — 공식과 같음」 풍선이다.
    required = _row_texts(assumed, ROW_UPEH_REQUIRED)
    inside = MONTHS.index(202702)
    assert required[inside][0] == f"<b>{REQUIRED[inside] / 1.1:,.1f}</b>"
    outside_hovers = [
        str(data[CUSTOMDATA_HOVER])
        for data, _, _ in _targets(assumed)
        if data[CUSTOMDATA_ROW] == ROW_UPEH_RATE and data[CUSTOMDATA_MONTH] not in window
    ]
    assert outside_hovers and all("구간 밖 — 공식과 같음" in hover for hover in outside_hovers)
    labels = json.dumps(_annotations(assumed.labels), ensure_ascii=False)
    assert "UPEH 110% · 소요대수" in labels and "UPEH 110% · 확보기준 과부족" in labels


def test_at_100_percent_the_rows_are_the_official_rows() -> None:
    assert ROW_UPEH_REQUIRED not in _canvas().row_ids


def test_with_an_assumption_the_shortage_band_follows_the_assumed_judgement() -> None:
    """판정 기준은 하나다 — 가정이 켜지면 부족 띠는 가정 요약의 판정을 따른다(① 공식 줄은 공식
    그대로)."""

    def bands(canvas: ProcessCapaCanvas) -> list[float]:
        return sorted(
            shape["x0"]
            for shape in _shapes(canvas.months)
            if shape.get("fillcolor") == tokens.SHORTAGE_MONTH_BAND
        )

    official = _canvas(products=False, home=False)
    assumed = _assumed_canvas(150, set(MONTHS))
    assert bands(official)
    assert len(bands(assumed)) < len(bands(official))
    assert _row_texts(assumed, ROW_RATE) == _row_texts(official, ROW_RATE)


def test_the_cross_check_and_target_rows_carry_the_assumption_mark_only_on_changing_rows() -> None:
    dynamic = _dynamic()
    marked = DynamicCanvasInput(**{**dynamic.__dict__, "official_pulls": {"EQ-21": (45, 0)}})
    canvas = _assumed_canvas(110, set(MONTHS), dynamic=marked)
    labels = json.dumps(_annotations(canvas.labels), ensure_ascii=False)
    assert "판정 대조 · UPEH 가정" in labels and "과부족 · UPEH 가정" in labels
    assert "가용 (환산) · UPEH" not in labels and "전월 대비 · UPEH" not in labels
    unit_hover = _label_hovers(canvas)["unit:EQ-21"]
    assert unit_hover.split("<br>")[-1] == f"UPEH 가정 계획 · 공식 {MINUS}45일 → 가정 0일"
    cell_lines = _row_hover(canvas, "unit:EQ-21").split("<br>")
    assert cell_lines[0] == unit_hover.split("<br>")[0]
    assert cell_lines[-1] == unit_hover.split("<br>")[-1]


def _compare_hovers(canvas: ProcessCapaCanvas) -> dict[int, str]:
    return {
        int(data[CUSTOMDATA_MONTH]): str(data[CUSTOMDATA_HOVER])
        for data, _, _ in _targets(canvas)
        if data[CUSTOMDATA_ROW] == ROW_DYNAMIC_COMPARE
    }


def test_the_cross_check_hover_names_the_assumed_basis_when_an_assumption_is_on() -> None:
    """가정이 켜지면 ② 판정 대조의 「기준」 은 가정 요약의 판정이다 — 풍선이 「공식은 …」 이라고
    적으면 공식 판정처럼 읽힌다. 공식 값은 ① 공식 줄과 KPI 회색 줄에만 둔다(명세 U6)."""
    official = _compare_hovers(_canvas(dynamic=_dynamic()))
    assumed = _compare_hovers(_assumed_canvas(80, set(MONTHS), dynamic=_dynamic()))

    disagreeing = [hover for hover in official.values() if "공식은" in hover]
    assert disagreeing, official
    assert all("UPEH 가정" not in hover for hover in official.values())
    named = [hover for hover in assumed.values() if "UPEH 가정" in hover]
    assert named, assumed
    assert all("공식은" not in hover and "공식·설비" not in hover for hover in assumed.values())
    assert any(
        "UPEH 가정 기준은" in hover or "UPEH 가정·설비 일정 두 기준 모두 부족" in hover
        for hover in named
    )
