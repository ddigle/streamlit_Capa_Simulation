# Purpose: 시트의 호기 필터가 걸린 호기만 더하고 Static·GAP 을 비우며 전환은 본문인지 본다.

from __future__ import annotations

import pytest
from sheet_reader import sheet_hovers, sheet_value
from streamlit.testing.v1 import AppTest
from test_availability_gap_panel import _descendants, switch_row_end

from capa_simulation.components.availability_gap_panel import (
    DETAIL_MODE_KEY,
    PROCESS_FILTER_KEY,
    RESULT_VIEW_KEY,
    UNIT_FILTER_COLUMNS_KEY,
    UNIT_FILTER_HELP,
    UNIT_FILTER_MARK,
    unit_filter_key,
)
from capa_simulation.services.availability_sheet import (
    GAP_ROWS,
    ROW_SCHEDULE_AVAILABLE,
    ROW_SCHEDULE_OWNED,
    ROW_STATIC_AVAILABLE,
    STATIC_ROWS,
)

MONTH = 202610


@pytest.fixture(autouse=True)
def _no_scrollbar_component(monkeypatch: pytest.MonkeyPatch) -> None:
    """시트 위 가로 스크롤바(Components v2)는 AppTest 에서 등록되지 않는다 — 시험 동안만 뺀다."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar

    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda **_: None)


def _filter_app() -> None:
    """호기 셋(두 공정, 두 라인)과 기존보유·Static 을 가진 패널 호스트. 조건은 사이드바에 그린다."""
    from datetime import date
    from types import SimpleNamespace

    import pandas as pd
    import streamlit as st

    from capa_simulation.components.availability_gap_panel import render_availability_gap_panel
    from capa_simulation.services.manual_downtime import ManualDowntime
    from capa_simulation.services.process_cutoff import prepare_process_cutoff

    # `line_a` 는 첫 라인 이름을 갈아 낀다 — 물결표 이름 시험용.
    line_a = str(st.session_state.get("line_a", "Line-A"))
    units = pd.DataFrame(
        {
            "설비명": ["EQ-1", "EQ-2", "EQ-3"],
            "공정소분류": ["Die Attach", "Die Attach", "Etch"],
            "공정구분": [line_a, "Line-B", line_a],
            "Model": ["M-1", "M-2", " "],
        }
    )
    spans = pd.DataFrame(
        {
            "설비명": units["설비명"],
            "공정소분류": units["공정소분류"],
            "상태": ["가용"] * 3,
            "시작일": [date(2020, 1, 1)] * 3,
            "종료일": [date(2030, 1, 1)] * 3,
        }
    )
    baseline = pd.DataFrame({"공정": ["Die Attach", "Etch"], "기존보유대수": [3.0, 5.0]})
    cutoff = prepare_process_cutoff(
        pd.DataFrame(
            {"공정": ["Die Attach", "Etch"], "Cutoff일수": [15.0, 15.0], "비고": [None, None]}
        )
    )
    static = pd.DataFrame(
        {"생산계획년월": [202610] * 2, "공정": ["Die Attach", "Etch"], "가용대수": [6.0, 8.0]}
    )
    render_availability_gap_panel(
        spans=spans,
        baseline=baseline,
        cutoff=cutoff,
        months=[202610],
        static_availability=static,
        owner_tab=SimpleNamespace(open=True),
        conditions=st.sidebar.container(),
        units=units,
        manual_downtime=ManualDowntime(rows=tuple(st.session_state.get("manual_rows", ()))),
    )


def _run(**state: object) -> AppTest:
    app = AppTest.from_function(_filter_app, default_timeout=30)
    for key, value in state.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    app.segmented_control(key=RESULT_VIEW_KEY).set_value("분류별 내역").run()
    assert not app.exception
    return app


def _available(app: AppTest) -> float | None:
    """시트의 설비 일정 기준 가용."""
    return sheet_value(app, MONTH, ROW_SCHEDULE_AVAILABLE)


def _filter(app: AppTest, column: str, values: list[str]) -> None:
    app.multiselect(key=UNIT_FILTER_COLUMNS_KEY).set_value([column]).run()
    assert not app.exception
    app.multiselect(key=unit_filter_key(column)).set_value(values).run()
    assert not app.exception


def test_view_switches_stay_in_the_body_and_filters_go_to_the_card() -> None:
    """무엇을 볼지 고르는 전환(조회 결과·표시)은 본문, 거르는 조건(공정·호기 필터)은 카드다.

    탭 안의 하위 탭과 같은 전환을 카드에 넣으면 지금 무엇을 보는지 본문에서 사라진다
    (2026-09-29 사용자 결정).
    """
    app = _run()

    main_keys = {widget.key for widget in app.main.segmented_control}
    assert {RESULT_VIEW_KEY, DETAIL_MODE_KEY} <= main_keys
    assert not app.sidebar.segmented_control
    assert [widget.key for widget in app.sidebar.selectbox] == [PROCESS_FILTER_KEY]
    assert [widget.key for widget in app.sidebar.multiselect] == [UNIT_FILTER_COLUMNS_KEY]


def test_unit_filter_sums_only_the_chosen_units_and_blanks_static_and_gap() -> None:
    app = _run()
    # 필터 없이는 기존보유(3 + 5)와 가용 호기 셋이 모두 더해진다.
    assert _available(app) == 11.0
    assert sheet_value(app, MONTH, ROW_STATIC_AVAILABLE) == 14.0

    _filter(app, "공정구분", ["Line-A"])
    # Line-A 는 EQ-1(Die Attach)·EQ-3(Etch) 둘. 기존보유는 호기 속성이 없어 빠진다.
    assert _available(app) == 2.0
    assert sheet_value(app, MONTH, ROW_SCHEDULE_OWNED) == 2.0
    # 걸러진 설비 일정을 거르지 않은 Static 과 맞대지 않는다 — 9행은 그대로, 칸이 「—」 다.
    hovers = sheet_hovers(app)
    for row in (*STATIC_ROWS, *GAP_ROWS):
        assert sheet_value(app, MONTH, row) is None
        assert "호기 필터 중에는" in hovers[(MONTH, row)]
    assert any("호기 필터" in caption.value for caption in app.caption)

    # 공정과 함께 걸린다.
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    assert _available(app) == 1.0

    # 호기 목록도 같은 호기만 본다.
    app.segmented_control(key=DETAIL_MODE_KEY).set_value("호기 목록").run()
    assert not app.exception
    units = app.dataframe[0].value
    assert units["설비명"].tolist() == ["EQ-1"]


def test_removing_a_column_releases_its_values() -> None:
    """컬럼을 빼면 그 값 선택도 풀린다. 남기면 다시 고를 때 잊은 조건이 되살아난다."""
    app = _run()
    _filter(app, "공정구분", ["Line-B"])
    assert _available(app) == 1.0

    app.multiselect(key=UNIT_FILTER_COLUMNS_KEY).set_value([]).run()
    assert not app.exception
    assert app.session_state[unit_filter_key("공정구분")] == []
    assert _available(app) == 11.0

    app.multiselect(key=UNIT_FILTER_COLUMNS_KEY).set_value(["공정구분"]).run()
    assert app.multiselect(key=unit_filter_key("공정구분")).value == []


def test_blank_values_are_not_offered_and_a_chosen_column_with_no_value_filters_nothing() -> None:
    app = _run()
    app.multiselect(key=UNIT_FILTER_COLUMNS_KEY).set_value(["Model"]).run()
    assert not app.exception
    # 빈 칸(공백만 있는 값)은 고를 값이 아니다.
    assert app.multiselect(key=unit_filter_key("Model")).options == ["M-1", "M-2"]
    # 컬럼만 고르고 값을 안 고르면 아무것도 거르지 않는다.
    assert _available(app) == 11.0


def test_the_caption_counts_only_the_units_inside_the_chosen_process() -> None:
    """표지 풍선의 호기 수는 시트에 실제로 더해진 호기 수다.

    Line-A 는 EQ-1(Die Attach)·EQ-3(Etch) 둘인데, 공정을 Die Attach 로 고르면 더해지는 것은
    EQ-1 하나다. 범위 밖 호기까지 세면 「호기 2개」로 적혀 표와 어긋났다(2026-10-01 재현: 동=C1
    18대 중 Die Attach 3대).
    """
    app = _run()
    _filter(app, "공정구분", ["Line-A"])
    # 자리에는 짧은 표지만 — 고른 값 · 호기 수와 무엇이 빠지는지(기존보유 · 입력 비가동 · Static ·
    # GAP)는 그 표지의 풍선이다(2026-11-11 보드 D2 (나) — e4-1 과 같은 꼴).
    (band,) = [caption for caption in app.caption if caption.value == UNIT_FILTER_MARK]
    assert band.proto.help.startswith("공정구분: Line\\-A — 호기 2개만 더합니다.")
    assert UNIT_FILTER_HELP in band.proto.help
    captions = " ".join(caption.value for caption in app.caption)
    assert "개만 더합니다" not in captions and "호기 속성이 없어" not in captions
    # 그 표지는 혼자 한 줄을 세우지 않고 「조회 결과 · 표시」 전환 줄 오른쪽 끝 칸의 작은 글이다 —
    # 「내려받기 ▾」 메뉴 앞(2026-11-11 보드 D2 — e4-1 과 같은 꼴).
    assert all(child is not band for child in app.main.children.values())
    end = switch_row_end(app)
    assert band in _descendants(end)
    assert list(end.children.values())[0] is band

    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    assert not app.exception
    (band,) = [caption for caption in app.caption if caption.value == UNIT_FILTER_MARK]
    assert "호기 1개만 더합니다" in band.proto.help
    assert _available(app) == 1.0


def test_the_filter_caption_blocks_the_tildes_of_the_chosen_values() -> None:
    """본문 「호기 필터」 표지 풍선의 「공정구분: …」(마크다운)은 고른 값을 날로 실으면 「L~A~X」
    의 가운데가 지움선이 된다(2026-10-26 E2E r5 와 같은 결함류 — Summary 걸린 조건 줄). 물결표를
    막는다."""
    app = _run(line_a="L~A~X")
    _filter(app, "공정구분", ["L~A~X"])

    helps = [str(item.proto.help) for item in app.caption if item.value == UNIT_FILTER_MARK]
    assert helps and all(text.startswith("공정구분: L\\~A\\~X —") for text in helps)


def test_the_filter_caption_keeps_the_stars_of_the_chosen_values() -> None:
    """물결표만 막으면 「L*A*X」 의 별표 짝이 기울임이 되어 「LAX」 로 보인다 — 고른 값은 이름마다
    막는다(개선 거리 I11)."""
    app = _run(line_a="L*A*X")
    _filter(app, "공정구분", ["L*A*X"])

    helps = [str(item.proto.help) for item in app.caption if item.value == UNIT_FILTER_MARK]
    assert helps and all(text.startswith("공정구분: L\\*A\\*X —") for text in helps)
