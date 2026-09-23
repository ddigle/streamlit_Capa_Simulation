# Purpose: 설비 탐색기의 질문별 단일 결과와 선택일·필터·탭 왕복 동작을 검증한다.

from datetime import date

from streamlit.testing.v1 import AppTest

from capa_simulation.components.equipment_explorer import (
    AS_OF_KEY,
    INACTIVE_VIEW_KEY,
    QUESTION_KEY,
    SMALL_PROCESS_KEY,
)


def _render_fixture() -> None:
    from datetime import date

    import pandas as pd

    from capa_simulation.components.equipment_explorer import render_equipment_explorer
    from capa_simulation.components.tab_state import stateful_tabs
    from capa_simulation.services.equipment_contract import (
        empty_downtime_schedule,
        empty_equipment_master,
    )

    equipment = empty_equipment_master()
    for index, unit in enumerate(("EQ-REPAIR", "EQ-READY", "EQ-QUAL", "EQ-OTHER")):
        equipment.loc[index] = {column: None for column in equipment.columns}
        equipment.loc[index, "호기"] = unit
        equipment.loc[index, "공정소분류"] = "Other" if unit == "EQ-OTHER" else "Die Attach"
        equipment.loc[index, "라인구분"] = "Line-A"
        equipment.loc[index, "활용구분"] = "양산"
        equipment.loc[index, "공정대분류"] = "조립"
        equipment.loc[index, "장기보관여부"] = "N"
        equipment.loc[index, "기존설비여부"] = "Y"
        equipment.loc[index, "레이아웃표시"] = "N"
    equipment.loc[2, "기존설비여부"] = "N"
    equipment.loc[2, "입고일정"] = date(2026, 10, 1)
    equipment.loc[2, "Qual일정"] = date(2026, 10, 10)
    equipment.loc[2, "확정상태"] = "계획"
    downtime = empty_downtime_schedule()
    downtime.loc[0] = {column: None for column in downtime.columns}
    downtime.loc[0, "호기"] = "EQ-REPAIR"
    downtime.loc[0, "비가동유형"] = "고장"
    downtime.loc[0, "시작일"] = date(2026, 10, 5)
    downtime.loc[0, "종료일"] = date(2026, 10, 7)
    baseline = pd.DataFrame(
        {"공정": ["Die Attach"], "분류": ["기존"], "기존보유대수": [5.0], "비고": [""]}
    )
    main_tab, _ = stateful_tabs(["Main", "Settings"], key="equipment_explorer_test_tab")
    with main_tab:
        render_equipment_explorer(
            baseline=baseline,
            equipment=equipment,
            downtime=downtime,
            today=date(2026, 10, 6),
            owner_tab=main_tab,
        )


def _app() -> AppTest:
    return AppTest.from_function(_render_fixture, default_timeout=30).run()


def _assert_one_result(app: AppTest) -> None:
    assert not app.exception
    assert not app.error
    assert (
        len(app.dataframe) + len(app.get("vega_lite_chart")) + len(app.get("plotly_chart"))
    ) == 1


def test_inactive_units_follow_the_chosen_day_not_the_week_end() -> None:
    """10월 6일 고장은 7일까지이고 Qual은 10일이다. 같은 주 안에서도 답이 달라진다."""
    app = _app()
    app.segmented_control(QUESTION_KEY).set_value("비가동 호기").run()
    app.multiselect(SMALL_PROCESS_KEY).set_value(["Die Attach"]).run()

    _assert_one_result(app)
    assert set(app.dataframe[0].value["호기"]) == {"EQ-REPAIR", "EQ-QUAL"}
    assert any("2026-10-06" in item.value for item in app.markdown)

    app.date_input(AS_OF_KEY).set_value(date(2026, 10, 8)).run()

    _assert_one_result(app)
    assert app.dataframe[0].value["호기"].tolist() == ["EQ-QUAL"]

    app.date_input(AS_OF_KEY).set_value(date(2026, 10, 11)).run()

    assert not app.exception
    assert not app.dataframe
    assert any("비가동 호기가 없습니다" in item.value for item in app.success)


def test_each_question_and_representation_replaces_the_previous_result() -> None:
    app = _app()
    _assert_one_result(app)
    assert not app.dataframe

    app.segmented_control("equipment_explorer_expression_주차별 추이").set_value("표").run()
    _assert_one_result(app)
    assert "Weeknum" in app.dataframe[0].value.columns

    app.selectbox("equipment_explorer_availability_view").set_value("공정별 내역").run()
    _assert_one_result(app)
    assert "기존보유대수" in app.dataframe[0].value.columns

    app.segmented_control(QUESTION_KEY).set_value("호기 현황").run()
    _assert_one_result(app)
    assert not app.dataframe
    app.selectbox("equipment_explorer_unit_view").set_value("호기 목록").run()
    _assert_one_result(app)
    assert set(app.dataframe[0].value["호기"]) == {"EQ-REPAIR", "EQ-READY", "EQ-QUAL", "EQ-OTHER"}
    # 집계형 보유대수 5대는 호기 목록에 가상의 행으로 들어가지 않는다.
    assert len(app.dataframe[0].value) == 4

    app.selectbox("equipment_explorer_unit_view").set_value("생애주기 일정").run()
    _assert_one_result(app)
    assert len(app.get("plotly_chart")) == 1

    app.segmented_control(QUESTION_KEY).set_value("Qual 일정").run()
    _assert_one_result(app)
    assert app.dataframe[0].value["호기"].tolist() == ["EQ-QUAL"]
    app.selectbox("equipment_explorer_qual_view").set_value("확정상태 분포").run()
    _assert_one_result(app)
    app.segmented_control("equipment_explorer_expression_확정상태 분포").set_value("표").run()
    _assert_one_result(app)
    counts = app.dataframe[0].value.set_index("확정상태")["호기대수"]
    assert counts["계획"] == 1
    assert counts.sum() == 1


def test_hidden_main_preserves_the_question_date_and_process_selection() -> None:
    app = _app()
    app.segmented_control(QUESTION_KEY).set_value("비가동 호기").run()
    app.multiselect(SMALL_PROCESS_KEY).set_value(["Die Attach"]).run()
    app.date_input(AS_OF_KEY).set_value(date(2026, 10, 8)).run()
    app.session_state["equipment_explorer_test_tab"] = "Settings"
    app.run()

    assert not app.exception
    assert not app.dataframe
    assert not app.get("vega_lite_chart")
    assert not app.get("plotly_chart")

    app.session_state["equipment_explorer_test_tab"] = "Main"
    app.run()

    _assert_one_result(app)
    assert app.segmented_control(QUESTION_KEY).value == "비가동 호기"
    assert app.multiselect(SMALL_PROCESS_KEY).value == ["Die Attach"]
    assert app.date_input(AS_OF_KEY).value == date(2026, 10, 8)
    assert app.dataframe[0].value["호기"].tolist() == ["EQ-QUAL"]


def test_the_month_view_catches_what_the_chosen_day_misses() -> None:
    """10월 11일에는 비가동 호기가 하나도 없지만, 10월 안에는 둘이 있었다.

    「그 달 전체」는 기준일이 든 달을 본다. 기준 월을 따로 고르는 위젯을 만들지 않는다 —
    조회 축이 둘이 되면 화면이 어느 쪽을 답하는지 알 수 없어진다.
    """
    app = _app()
    app.segmented_control(QUESTION_KEY).set_value("비가동 호기").run()

    assert app.selectbox(INACTIVE_VIEW_KEY).value == "기준일 시점"

    app.date_input(AS_OF_KEY).set_value(date(2026, 10, 11)).run()

    assert not app.dataframe
    assert any("비가동 호기가 없습니다" in item.value for item in app.success)

    app.selectbox(INACTIVE_VIEW_KEY).set_value("그 달 전체").run()

    _assert_one_result(app)
    assert set(app.dataframe[0].value["호기"]) == {"EQ-REPAIR", "EQ-QUAL"}
    assert list(app.dataframe[0].value.columns[:3]) == ["호기", "비가동 시작", "비가동 종료"]
    assert any("2026-10 달 전체" in item.value for item in app.markdown)
    assert app.date_input(AS_OF_KEY).value == date(2026, 10, 11)


def test_hidden_main_preserves_the_inactive_view_selection() -> None:
    app = _app()
    app.segmented_control(QUESTION_KEY).set_value("비가동 호기").run()
    app.selectbox(INACTIVE_VIEW_KEY).set_value("그 달 전체").run()
    app.session_state["equipment_explorer_test_tab"] = "Settings"
    app.run()

    assert not app.exception
    assert not app.dataframe

    app.session_state["equipment_explorer_test_tab"] = "Main"
    app.run()

    _assert_one_result(app)
    assert app.selectbox(INACTIVE_VIEW_KEY).value == "그 달 전체"
    assert "비가동 시작" in app.dataframe[0].value.columns
