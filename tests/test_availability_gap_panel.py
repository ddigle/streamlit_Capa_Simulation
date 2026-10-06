# Purpose: 비교 패널의 결과 선택·공정 필터·숨은 탭 복귀와 기존 수치 및 누락 안내를 검사한다.

from __future__ import annotations

import json

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.availability_gap_panel import (
    DETAIL_CATEGORY_KEY,
    DETAIL_MODE_KEY,
    PROCESS_FILTER_KEY,
    RESULT_VIEW_KEY,
    matrix_table_key,
)
from capa_simulation.services.availability_gap import (
    DYNAMIC_SUBTOTAL_ROW,
    DYNAMIC_WEIGHTED_ROW,
    GAP_ROW,
    STATIC_ROW,
)


def _panel_app() -> None:
    """DB 없이 호기·기준정보·소요대수 입력을 교체할 수 있는 패널 호스트."""
    from datetime import date
    from types import SimpleNamespace

    import pandas as pd
    import streamlit as st

    from capa_simulation.components.availability_gap_panel import render_availability_gap_panel
    from capa_simulation.services.process_cutoff import prepare_process_cutoff

    spans = pd.DataFrame(
        {
            "설비명": ["EQ-1", "EQ-2"],
            "공정소분류": ["Die Attach", "Etch"],
            "상태": ["가용", "가용"],
            "시작일": [date(2020, 1, 1)] * 2,
            "종료일": [date(2030, 1, 1)] * 2,
        }
    )
    baseline = pd.DataFrame({"공정": ["Die Attach", "Etch"], "기존보유대수": [3.0, 5.0]})
    cutoff = prepare_process_cutoff(
        pd.DataFrame(
            {"공정": ["Die Attach", "Etch"], "Cutoff일수": [15.0, 15.0], "비고": [None, None]}
        )
    )
    static = pd.DataFrame(
        {
            "생산계획년월": [202610] * 3,
            "공정": ["Die Attach", "Etch", "Probe"],
            "가용대수": [6.0, 8.0, 20.0],
        }
    )
    required = pd.DataFrame(
        {
            "생산계획년월": [202610] * 3,
            "공정": ["Die Attach", "Etch", "Probe"],
            "소요대수": [10.0, 20.0, 40.0],
        }
    )
    if st.session_state.get("wire_bond_units", False):
        # 설비에만 있는 공정 — 기준정보(Static)·소요대수에 `Wire Bond` 가 없다.
        spans = pd.concat(
            [
                spans,
                pd.DataFrame(
                    {
                        "설비명": ["EQ-9"],
                        "공정소분류": ["Wire Bond"],
                        "상태": ["가용"],
                        "시작일": [date(2020, 1, 1)],
                        "종료일": [date(2030, 1, 1)],
                    }
                ),
            ],
            ignore_index=True,
        )
        cutoff = prepare_process_cutoff(
            pd.DataFrame(
                {
                    "공정": ["Die Attach", "Etch", "Wire Bond"],
                    "Cutoff일수": [15.0, 15.0, 15.0],
                    "비고": [None, None, None],
                }
            )
        )
    if st.session_state.get("omit_etch", False):
        spans = spans.loc[spans["공정소분류"] != "Etch"]
        baseline = baseline.loc[baseline["공정"] != "Etch"]
        cutoff = cutoff.loc[cutoff["공정"] != "Etch"]
        static = static.loc[static["공정"] != "Etch"]
        required = required.loc[required["공정"] != "Etch"]

    units = None
    if st.session_state.get("undated_units", False):
        from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS

        # 날짜가 빈 신규 호기 둘(Die Attach 반입 미정, Etch Qual 미정)과 일정이 다 있는 EQ-1.
        rows = [
            ("EQ-1", "Die Attach", date(2020, 1, 1), date(2020, 1, 5), "완료"),
            ("EQ-NEW", "Die Attach", None, None, None),
            ("EQ-ETCH", "Etch", date(2026, 9, 1), None, None),
        ]
        units = pd.DataFrame(
            [
                {
                    **{column: None for column in EQUIPMENT_COLUMNS},
                    "설비명": unit,
                    "공정소분류": process,
                    "반입일정": arrival,
                    "Qual일정": qual,
                    "확정상태": confirm,
                    "보관유무": "N",
                    "기존설비여부": "N",
                    "레이아웃표시": "N",
                }
                for unit, process, arrival, qual, confirm in rows
            ],
            columns=EQUIPMENT_COLUMNS,
        )

    is_open = st.toggle("비교 탭 열기", value=True, key="test_gap_panel_open")
    render_availability_gap_panel(
        spans=spans,
        baseline=baseline,
        cutoff=cutoff.iloc[:0] if st.session_state.get("empty_cutoff", False) else cutoff,
        months=[] if st.session_state.get("empty_months", False) else [202610],
        static_availability=None if st.session_state.get("missing_static", False) else static,
        static_error="테스트 조회 실패" if st.session_state.get("missing_static", False) else None,
        span_bounds=(date(2026, 10, 1), date(2026, 10, 31))
        if st.session_state.get("short_span", False)
        else (date(2026, 9, 1), date(2026, 10, 31)),
        conversion_ratios={"EQ-1": 1.5},
        required_equipment=None if st.session_state.get("missing_required", False) else required,
        owner_tab=SimpleNamespace(open=is_open),
        units=units,
    )


def _run(**state: bool) -> AppTest:
    app = AppTest.from_function(_panel_app, default_timeout=30)
    for key, value in state.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    return app


def _select_view(app: AppTest, value: str) -> None:
    app.segmented_control(key=RESULT_VIEW_KEY).set_value(value).run()
    assert not app.exception


def test_only_the_selected_result_is_drawn_and_counts_keep_their_axes() -> None:
    app = _run()
    assert app.segmented_control(key=RESULT_VIEW_KEY).value == "가용대수 비교"
    assert len(app.get("plotly_chart")) == 1
    assert not app.dataframe

    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    chart = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert {trace["name"]: trace["y"] for trace in chart["data"]} == {
        "기존보유": [3.0],
        "가용(일할)": [1.0],
        "Static(기준정보)": [6.0],
    }
    assert chart["layout"]["annotations"][0]["text"] == "-2.00"

    _select_view(app, "분류별 내역")
    assert not app.get("plotly_chart")
    assert len(app.dataframe) == 1
    matrix = app.dataframe[0].value
    assert matrix.loc[DYNAMIC_SUBTOTAL_ROW, "26.10"] == 4.0
    assert matrix.loc[STATIC_ROW, "26.10"] == 6.0
    assert matrix.loc[GAP_ROW, "26.10"] == -2.0
    assert matrix.loc[DYNAMIC_WEIGHTED_ROW, "26.10"] == 4.5

    _select_view(app, "확보율 교차검증")
    assert not app.get("plotly_chart")
    assert len(app.dataframe) == 1
    row = app.dataframe[0].value.iloc[0]
    assert row["공정"] == "Die Attach"
    assert row["소요대수"] == 10.0
    assert row["Static가용대수"] == 6.0
    assert row["Dynamic가용대수"] == 4.5
    assert row["Static확보율"] == 0.6
    assert row["Dynamic확보율"] == 0.45
    assert row["확보율차이"] == -0.15

    _select_view(app, "가용대수 비교")
    assert len(app.get("plotly_chart")) == 1
    assert not app.dataframe
    assert app.selectbox(key=PROCESS_FILTER_KEY).value == "Die Attach"


def test_unmatched_processes_stay_out_of_totals_and_fallback_rows() -> None:
    app = _run()
    _select_view(app, "분류별 내역")
    matrix = app.dataframe[0].value
    assert matrix.loc[DYNAMIC_SUBTOTAL_ROW, "26.10"] == 10.0
    assert matrix.loc[STATIC_ROW, "26.10"] == 14.0
    assert matrix.loc[GAP_ROW, "26.10"] == -4.0
    assert "Probe" in " ".join(item.value for item in app.warning)
    assert "한쪽에만 있는 공정 1개" in " ".join(item.value for item in app.caption)

    _select_view(app, "확보율 교차검증")
    assert set(app.dataframe[0].value["공정"]) == {"Die Attach", "Etch"}
    assert "Static 값으로 채운 공정 1개" in " ".join(item.value for item in app.caption)
    assert "Probe" in " ".join(item.value for item in app.warning)

    app.selectbox(key=PROCESS_FILTER_KEY).select("Probe").run()
    assert not app.exception
    assert not app.dataframe
    assert "아직 맞대어 볼 수 있는 공정이 없습니다" in " ".join(item.value for item in app.info)


def test_hidden_tab_skips_output_and_preserves_both_selections() -> None:
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Etch").run()
    _select_view(app, "분류별 내역")

    app.toggle(key="test_gap_panel_open").set_value(False).run()
    assert not app.exception
    assert not app.selectbox
    assert not app.segmented_control
    assert not app.get("plotly_chart")
    assert not app.dataframe
    assert app.session_state[PROCESS_FILTER_KEY] == "Etch"
    assert app.session_state[RESULT_VIEW_KEY] == "분류별 내역"

    app.toggle(key="test_gap_panel_open").set_value(True).run()
    assert not app.exception
    assert app.selectbox(key=PROCESS_FILTER_KEY).value == "Etch"
    assert app.segmented_control(key=RESULT_VIEW_KEY).value == "분류별 내역"
    assert app.dataframe[0].value.loc[DYNAMIC_SUBTOTAL_ROW, "26.10"] == 6.0


def test_missing_static_keeps_dynamic_detail_and_explains_cross_check_limit() -> None:
    app = _run(missing_static=True)
    assert "테스트 조회 실패" in " ".join(item.value for item in app.warning)
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    _select_view(app, "분류별 내역")
    assert app.dataframe[0].value.loc[DYNAMIC_SUBTOTAL_ROW, "26.10"] == 4.0

    _select_view(app, "확보율 교차검증")
    assert not app.dataframe
    assert not app.get("plotly_chart")
    assert "Static 가용대수가 없어" in " ".join(item.value for item in app.info)
    assert "테스트 조회 실패" in " ".join(item.value for item in app.warning)


def test_missing_demand_only_blocks_the_cross_check() -> None:
    app = _run(missing_required=True)
    assert len(app.get("plotly_chart")) == 1
    _select_view(app, "확보율 교차검증")
    assert not app.dataframe
    assert not app.get("plotly_chart")
    assert "소요대수를 읽지 못해" in " ".join(item.value for item in app.info)


@pytest.mark.parametrize(
    ("state_key", "notice"),
    [("empty_cutoff", "공정별 Cut-off 를 먼저"), ("empty_months", "조회기간에 월이 없습니다")],
)
def test_missing_input_is_explained_before_any_result(state_key: str, notice: str) -> None:
    app = _run(**{state_key: True})
    assert not app.dataframe
    assert not app.get("plotly_chart")
    assert notice in " ".join(item.value for item in app.info)


def test_period_notices_do_not_direct_users_to_the_old_preference_tab() -> None:
    app = _run(short_span=True)
    assert "Cut-off 때문에" in " ".join(item.value for item in app.warning)
    _select_view(app, "확보율 교차검증")
    notices = " ".join(item.value for item in [*app.caption, *app.warning])
    assert "조회기간을 넓히면" in notices
    assert "Preference" not in notices


def test_removed_process_returns_to_total_without_losing_the_result_choice() -> None:
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Etch").run()
    _select_view(app, "분류별 내역")

    app.session_state["omit_etch"] = True
    app.run()
    assert not app.exception
    assert app.selectbox(key=PROCESS_FILTER_KEY).value == "전체 합계"
    assert app.segmented_control(key=RESULT_VIEW_KEY).value == "분류별 내역"
    assert app.dataframe[0].value.loc[DYNAMIC_SUBTOTAL_ROW, "26.10"] == 4.0


# ------------------------------------------------------------------ 호기 목록


def test_the_unit_list_shows_every_contribution_behind_the_counts() -> None:
    """「호기 목록」은 대수 표의 칸을 이루는 호기별 기여다. 같은 칸을 더하면 표의 값이다."""
    app = _run()
    _select_view(app, "분류별 내역")
    matrix = app.dataframe[0].value
    assert app.segmented_control(key=DETAIL_MODE_KEY).value == "대수"

    app.segmented_control(key=DETAIL_MODE_KEY).set_value("호기 목록").run()
    assert not app.exception
    units = app.dataframe[0].value
    # Probe 는 한쪽에만 있어 표에서 빠진다 — 목록도 같은 범위다.
    assert set(units["공정"]) == {"Die Attach", "Etch"}
    assert {"월", "분류", "설비명", "기여일수", "대수", "환산대수"} <= set(units.columns)
    assert set(units.loc[units["분류"].eq("기존보유"), "설비명"]) == {"기존보유 · 전체"}
    for category in ("기존보유", "가용"):
        listed = units.loc[units["분류"].eq(category), "대수"].sum()
        assert listed == pytest.approx(matrix.loc[category, "26.10"])
    assert any(button.label == "CSV 다운로드" for button in app.download_button)

    app.multiselect(key=DETAIL_CATEGORY_KEY).set_value(["가용"]).run()
    assert set(app.dataframe[0].value["분류"]) == {"가용"}


def test_a_clicked_cell_lists_its_units_and_adds_up_to_the_cell() -> None:
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    _select_view(app, "분류별 내역")
    rows = list(app.dataframe[0].value.index)
    key = matrix_table_key("Die Attach", [202610], rows)

    app.session_state[key] = {
        "selection": {"rows": [], "columns": [], "cells": [[rows.index("가용"), "26.10"]]}
    }
    app.run()
    assert not app.exception
    assert len(app.dataframe) == 2
    cell = app.dataframe[1].value
    assert cell["설비명"].tolist() == ["EQ-1"]
    assert cell["대수"].sum() == pytest.approx(app.dataframe[0].value.loc["가용", "26.10"])

    # 소계 칸은 소계에 드는 분류(기존보유·가용)를 모아 보인다.
    app.session_state[key] = {
        "selection": {
            "rows": [],
            "columns": [],
            "cells": [[rows.index(DYNAMIC_SUBTOTAL_ROW), "26.10"]],
        }
    }
    app.run()
    subtotal = app.dataframe[1].value
    assert set(subtotal["분류"]) == {"기존보유", "가용"}
    assert subtotal["대수"].sum() == pytest.approx(4.0)

    # Static·GAP 은 기준정보라 목록 대신 안내가 뜬다.
    app.session_state[key] = {
        "selection": {"rows": [], "columns": [], "cells": [[rows.index(STATIC_ROW), "26.10"]]}
    }
    app.run()
    assert len(app.dataframe) == 1
    assert "호기 목록이 없습니다" in " ".join(item.value for item in app.info)


def test_a_click_does_not_follow_the_table_into_another_scope() -> None:
    """선택은 (행 위치, 열 이름)으로 남는다. 공정을 바꾸면 같은 위치가 다른 분류다.

    범위마다 표의 키가 달라 전에 누른 칸이 새 표로 따라오지 않는다(브라우저 실측: 따라오면
    누르지 않은 분류의 호기가 떴다).
    """
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    _select_view(app, "분류별 내역")
    rows = list(app.dataframe[0].value.index)
    die_attach = matrix_table_key("Die Attach", [202610], rows)
    app.session_state[die_attach] = {
        "selection": {"rows": [], "columns": [], "cells": [[rows.index("가용"), "26.10"]]}
    }
    app.run()
    assert len(app.dataframe) == 2

    app.selectbox(key=PROCESS_FILTER_KEY).select("Etch").run()
    assert not app.exception
    etch_rows = list(app.dataframe[0].value.index)
    assert matrix_table_key("Etch", [202610], etch_rows) != die_attach
    assert len(app.dataframe) == 1


def test_the_unit_list_keeps_full_precision_so_thirds_add_up_to_one() -> None:
    """모듈 셋이 1/3 씩이면 0.333 으로 잘라 더해 0.999 가 되면 안 된다. 표시만 세 자리다."""
    from io import StringIO

    import pandas as pd

    from capa_simulation.components.availability_gap_panel import _unit_table

    thirds = pd.DataFrame(
        {
            "생산계획년월": [202610] * 3,
            "공정": ["Bonder"] * 3,
            "분류": ["가용"] * 3,
            "설비명": ["APW01A", "APW01B", "APW01C"],
            "설비키": ["APW01"] * 3,
            "기존보유분류": pd.Series([pd.NA] * 3, dtype="string"),
            "기여일수": [31] * 3,
            "구간일수": [31] * 3,
            "대수": [1 / 3] * 3,
            "환산대수": [1 / 3] * 3,
        }
    )

    table = _unit_table(thirds, with_month=True)

    assert table["대수"].sum() == pytest.approx(1.0, abs=1e-12)
    exported = pd.read_csv(StringIO(table.to_csv(index=False)))
    assert exported["대수"].sum() == pytest.approx(1.0, abs=1e-12)
    assert "설비" in table.columns


# ------------------------------------------------------------------ 한쪽에만 있는 공정


def test_a_process_only_in_the_equipment_side_shows_no_gap_and_says_why() -> None:
    """기준정보에 없는 공정을 골라도 GAP 을 「+Dynamic」으로 내지 않는다(2026-10-01 결정).

    전체 합계·호기 필터가 이미 그렇게 한다. 없는 쪽을 0 으로 보면 공정명 불일치가 「그만큼
    넘친다」로 읽혔다(브라우저 재현: Die Attach 의 GAP 이 Dynamic 소계와 같았다).
    """
    app = _run(wire_bond_units=True)
    assert "Wire Bond" in " ".join(item.value for item in app.warning)
    app.selectbox(key=PROCESS_FILTER_KEY).select("Wire Bond").run()
    assert not app.exception
    # 그림은 Static 과 Dynamic 을 맞대는 자리라 그리지 않고 까닭을 말한다.
    assert not app.get("plotly_chart")
    infos = " ".join(item.value for item in app.info)
    assert "「Wire Bond」 공정은 기준정보(Static)에 없어 GAP 을 내지 않습니다" in infos

    _select_view(app, "분류별 내역")
    matrix = app.dataframe[0].value
    assert matrix.loc[DYNAMIC_SUBTOTAL_ROW, "26.10"] == 1.0
    assert GAP_ROW not in matrix.index
    assert STATIC_ROW not in matrix.index
    assert "GAP 을 내지 않습니다" in " ".join(item.value for item in app.caption)


def test_a_process_only_in_the_reference_side_shows_its_static_without_gap() -> None:
    app = _run()
    app.selectbox(key=PROCESS_FILTER_KEY).select("Probe").run()
    assert not app.get("plotly_chart")
    assert "「Probe」 공정은 Dynamic 이 나오지 않아" in " ".join(item.value for item in app.info)

    _select_view(app, "분류별 내역")
    matrix = app.dataframe[0].value
    assert matrix.loc[STATIC_ROW, "26.10"] == 20.0
    assert GAP_ROW not in matrix.index


def test_the_cross_check_leaves_out_a_process_missing_from_the_reference() -> None:
    """기준정보에 없는 공정은 확보율 표에 빈 행으로 실리지 않고, 비교한 공정 수에도 없다."""
    app = _run(wire_bond_units=True)
    _select_view(app, "확보율 교차검증")
    assert set(app.dataframe[0].value["공정"]) == {"Die Attach", "Etch"}
    captions = " ".join(item.value for item in app.caption)
    assert "실제로 비교한 공정은 2개입니다" in captions
    assert "기준정보(Static)에 없는 공정 1개는" in captions

    app.selectbox(key=PROCESS_FILTER_KEY).select("Wire Bond").run()
    assert not app.exception
    assert not app.dataframe
    infos = " ".join(item.value for item in app.info)
    assert "「Wire Bond」 공정은 기준정보(Static)에 없어 확보율을 맞대지 않습니다" in infos

    # 맞댈 공정이 없을 때 이름이 어긋난 공정이 있으면 이름도 까닭으로 든다.
    app.selectbox(key=PROCESS_FILTER_KEY).select("Probe").run()
    infos = " ".join(item.value for item in app.info)
    assert "공정명을 기준정보와 맞추면" in infos


def _undated_captions(app: AppTest) -> list[str]:
    return [caption.value for caption in app.caption if "일정 미정" in caption.value]


def test_undated_units_are_named_in_the_scope_the_counts_use() -> None:
    """날짜가 빈 신규 호기는 Dynamic 에 들지 않는다 — 둘러싼 대수와 같은 범위로 한 줄 알린다."""
    app = _run(undated_units=True)

    assert _undated_captions(app) == [
        ":material/event_busy: 일정 미정 2대 (반입 미정 1 · Qual 미정 1) — 날짜가 들어올 때까지 "
        "가용대수에 세지 않습니다."
    ]

    app.selectbox(key=PROCESS_FILTER_KEY).set_value("Die Attach").run()
    assert [text.split(" — ")[0] for text in _undated_captions(app)] == [
        ":material/event_busy: 일정 미정 1대 (반입 미정 1)"
    ]

    for view in ("분류별 내역", "확보율 교차검증"):
        _select_view(app, view)
        assert len(_undated_captions(app)) == 1, view


def test_no_undated_line_without_undated_units() -> None:
    assert _undated_captions(_run()) == []
