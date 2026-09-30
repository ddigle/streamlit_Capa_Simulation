# Purpose: 분류별 내역의 호기 필터가 걸린 호기만 분류대로 더하고 보기 전환은 본문에 남는지 검사한다.

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from capa_simulation.components.availability_gap_panel import (
    DETAIL_MODE_KEY,
    PROCESS_FILTER_KEY,
    RESULT_VIEW_KEY,
    UNIT_FILTER_COLUMNS_KEY,
    unit_filter_key,
)
from capa_simulation.services.availability_gap import (
    DYNAMIC_SUBTOTAL_ROW,
    GAP_ROW,
    STATIC_ROW,
)


def _filter_app() -> None:
    """호기 셋(두 공정, 두 라인)과 기존보유·Static 을 가진 패널 호스트. 조건은 사이드바에 그린다."""
    from datetime import date
    from types import SimpleNamespace

    import pandas as pd
    import streamlit as st

    from capa_simulation.components.availability_gap_panel import render_availability_gap_panel
    from capa_simulation.services.process_cutoff import prepare_process_cutoff

    units = pd.DataFrame(
        {
            "호기": ["EQ-1", "EQ-2", "EQ-3"],
            "공정소분류": ["Die Attach", "Die Attach", "Etch"],
            "라인구분": ["Line-A", "Line-B", "Line-A"],
            "모델": ["M-1", "M-2", " "],
        }
    )
    spans = pd.DataFrame(
        {
            "호기": units["호기"],
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
    )


def _run() -> AppTest:
    app = AppTest.from_function(_filter_app, default_timeout=30).run()
    assert not app.exception
    app.segmented_control(key=RESULT_VIEW_KEY).set_value("분류별 내역").run()
    assert not app.exception
    return app


def _matrix(app: AppTest):  # type: ignore[no-untyped-def]
    assert len(app.dataframe) == 1
    return app.dataframe[0].value


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


def test_unit_filter_sums_only_the_chosen_units_by_category() -> None:
    app = _run()
    before = _matrix(app)
    # 필터 없이는 기존보유(3 + 5)와 가용 호기 셋이 모두 더해진다.
    assert before.loc[DYNAMIC_SUBTOTAL_ROW, "26.10"] == 11.0
    assert STATIC_ROW in before.index

    _filter(app, "라인구분", ["Line-A"])
    matrix = _matrix(app)
    # Line-A 는 EQ-1(Die Attach)·EQ-3(Etch) 둘. 기존보유는 호기 속성이 없어 빠진다.
    assert matrix.loc["가용", "26.10"] == 2.0
    assert matrix.loc[DYNAMIC_SUBTOTAL_ROW, "26.10"] == 2.0
    assert "기존보유" not in matrix.index
    # 걸러진 Dynamic 을 거르지 않은 Static 과 맞대지 않는다.
    assert STATIC_ROW not in matrix.index
    assert GAP_ROW not in matrix.index
    assert any("호기 필터" in caption.value for caption in app.caption)

    # 공정과 함께 걸린다.
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    assert _matrix(app).loc["가용", "26.10"] == 1.0

    # 호기 목록도 같은 호기만 본다 — 같은 칸을 더하면 표의 값이다.
    app.segmented_control(key=DETAIL_MODE_KEY).set_value("호기 목록").run()
    assert not app.exception
    units = _matrix(app)
    assert units["호기"].tolist() == ["EQ-1"]


def test_removing_a_column_releases_its_values() -> None:
    """컬럼을 빼면 그 값 선택도 풀린다. 남기면 다시 고를 때 잊은 조건이 되살아난다."""
    app = _run()
    _filter(app, "라인구분", ["Line-B"])
    assert _matrix(app).loc["가용", "26.10"] == 1.0

    app.multiselect(key=UNIT_FILTER_COLUMNS_KEY).set_value([]).run()
    assert not app.exception
    assert app.session_state[unit_filter_key("라인구분")] == []
    assert _matrix(app).loc[DYNAMIC_SUBTOTAL_ROW, "26.10"] == 11.0

    app.multiselect(key=UNIT_FILTER_COLUMNS_KEY).set_value(["라인구분"]).run()
    assert app.multiselect(key=unit_filter_key("라인구분")).value == []


def test_blank_values_are_not_offered_and_a_chosen_column_with_no_value_filters_nothing() -> None:
    app = _run()
    app.multiselect(key=UNIT_FILTER_COLUMNS_KEY).set_value(["모델"]).run()
    assert not app.exception
    # 빈 칸(공백만 있는 값)은 고를 값이 아니다.
    assert app.multiselect(key=unit_filter_key("모델")).options == ["M-1", "M-2"]
    # 컬럼만 고르고 값을 안 고르면 아무것도 거르지 않는다.
    assert _matrix(app).loc[DYNAMIC_SUBTOTAL_ROW, "26.10"] == 11.0


def test_the_caption_counts_only_the_units_inside_the_chosen_process() -> None:
    """캡션의 호기 수는 표에 실제로 더해진 호기 수다.

    Line-A 는 EQ-1(Die Attach)·EQ-3(Etch) 둘인데, 공정을 Die Attach 로 고르면 더해지는 것은
    EQ-1 하나다. 범위 밖 호기까지 세면 「호기 2개」로 적혀 표와 어긋났다(2026-10-01 재현: 동=C1
    18대 중 Die Attach 3대).
    """
    app = _run()
    _filter(app, "라인구분", ["Line-A"])
    captions = " ".join(caption.value for caption in app.caption)
    assert "호기 2개만 더합니다" in captions

    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    assert not app.exception
    captions = " ".join(caption.value for caption in app.caption)
    assert "호기 1개만 더합니다" in captions
    assert _matrix(app).loc["가용", "26.10"] == 1.0
