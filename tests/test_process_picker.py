# Purpose: 공정 선택 요약의 최소값·판정 경계·결측·원본 키·순서와 계산 밖 단추 글을 검증한다.

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.process_picker import tile_rate_text, tile_tooltip_text
from capa_simulation.services.process_picker import (
    ProcessPickerItem,
    build_process_picker_summary,
    shortfall_order,
)
from capa_simulation.services.securement_threshold import SecurementThresholds


def _frame(rows: list[tuple[int, str, float | None]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["생산계획년월", "공정", "확보율"])


def _summary(
    frame: pd.DataFrame, options: list[str], threshold: float = 1.0
) -> tuple[ProcessPickerItem, ...]:
    return build_process_picker_summary(
        frame,
        options,
        start_month=202601,
        end_month=202603,
        thresholds=SecurementThresholds(threshold, min(threshold, 0.9)),
    )


def test_valid_minimum_uses_earliest_tied_month_and_excludes_outside_range() -> None:
    frame = _frame(
        [
            (202512, "원본 공정", 0.1),
            (202603, "원본 공정", 0.8),
            (202602, "원본 공정", 0.8),
            (202601, "원본 공정", 1.2),
            (202604, "원본 공정", 0.0),
        ]
    )

    assert _summary(frame, ["원본 공정"]) == (
        ProcessPickerItem("원본 공정", 0.8, 202602, 3, "shortfall"),
    )


def test_summary_preserves_input_original_keys_and_requested_order() -> None:
    frame = _frame([(202601, "Z 원본", 0.9), (202601, "A 원본", 1.2), (202601, "목록 밖", 0.1)])
    before = frame.copy(deep=True)
    options = ["A 원본", "데이터 없는 원본", "Z 원본"]

    items = _summary(frame, options)

    assert [item.process for item in items] == options
    assert [item.group for item in items] == ["sufficient", "unavailable", "shortfall"]
    pd.testing.assert_frame_equal(frame, before)
    assert options == ["A 원본", "데이터 없는 원본", "Z 원본"]
    with pytest.raises(FrozenInstanceError):
        items[0].minimum_rate = 0.0  # type: ignore[misc]


def test_nan_infinite_and_absent_months_do_not_become_zero_or_shortfall() -> None:
    frame = _frame(
        [
            (202601, "일부 결측", None),
            (202602, "일부 결측", 0.7),
            (202603, "일부 결측", float("inf")),
            (202601, "전부 결측", None),
            (202602, "전부 결측", float("nan")),
            (202601, "무한대", float("inf")),
            (202602, "무한대", float("-inf")),
            (202512, "기간 밖", 0.2),
            (202601, "실제 영", 0.0),
        ]
    )

    assert _summary(
        frame, ["일부 결측", "전부 결측", "무한대", "기간 밖", "없는 공정", "실제 영"]
    ) == (
        ProcessPickerItem("일부 결측", 0.7, 202602, 1, "shortfall"),
        ProcessPickerItem("전부 결측", None, None, 0, "unavailable"),
        ProcessPickerItem("무한대", None, None, 0, "unavailable"),
        ProcessPickerItem("기간 밖", None, None, 0, "unavailable"),
        ProcessPickerItem("없는 공정", None, None, 0, "unavailable"),
        ProcessPickerItem("실제 영", 0.0, 202601, 1, "shortfall"),
    )


@pytest.mark.parametrize("threshold", [0.0, 1.0, 1.095])
def test_equal_threshold_is_sufficient_like_home_and_only_lower_is_shortfall(
    threshold: float,
) -> None:
    """HOME 은 기준과 같은 확보율을 확보로 센다(2026-10-06 사용자 결정). 선택 화면도 같아야 한다."""
    frame = _frame(
        [
            (202601, "동일", threshold),
            (202601, "초과", threshold + 0.01),
            (202601, "미만", threshold - 0.01),
        ]
    )

    assert [item.group for item in _summary(frame, ["동일", "초과", "미만"], threshold)] == [
        "sufficient",
        "sufficient",
        "shortfall",
    ]


@pytest.mark.parametrize("rate,expected", [(0.9, "shortfall"), (1.1, "sufficient")])
def test_all_or_none_are_shortfall_without_reordering_options(rate: float, expected: str) -> None:
    frame = _frame([(202601, "B", rate), (202601, "A", rate)])

    items = _summary(frame, ["A", "B"])

    assert [item.process for item in items] == ["A", "B"]
    assert [item.group for item in items] == [expected, expected]


def test_final_rate_is_used_without_recalculating_baseline_or_equipment_ratio() -> None:
    frame = _frame([(202601, "OFF인 공정도 포함", 0.8)])
    frame["기준 확보율"] = 1.5
    frame["가용대수"] = 30.0
    frame["소요대수"] = 10.0

    assert _summary(frame, ["OFF인 공정도 포함"])[0].minimum_rate == 0.8


def test_valid_month_count_counts_months_instead_of_rows() -> None:
    frame = _frame([(202601, "A", 0.8), (202601, "A", 0.9), (202602, "A", 1.1)])

    assert _summary(frame, ["A"])[0].valid_month_count == 2


def test_empty_frame_and_options_remain_available_as_empty_states() -> None:
    frame = _frame([])

    assert _summary(frame, []) == ()
    assert _summary(frame, ["A"]) == (ProcessPickerItem("A", None, None, 0, "unavailable"),)


def test_required_columns_are_validated() -> None:
    with pytest.raises(ValueError, match="필수 컬럼.*확보율"):
        _summary(pd.DataFrame({"생산계획년월": [202601], "공정": ["A"]}), ["A"])


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), -0.1])
def test_invalid_threshold_is_rejected(threshold: float) -> None:
    with pytest.raises(ValueError, match="확보 기준"):
        _summary(_frame([]), [], threshold)


@pytest.mark.parametrize("start,end", [(202600, 202603), (202603, 202601)])
def test_invalid_query_bounds_are_rejected(start: int, end: int) -> None:
    with pytest.raises(ValueError):
        build_process_picker_summary(
            _frame([]),
            [],
            start_month=start,
            end_month=end,
            thresholds=SecurementThresholds(1.0, 0.9),
        )


def test_a_month_with_a_higher_threshold_can_make_a_process_fall_short() -> None:
    """충족은 **모든 유효한 달이 그 달 기준 이상일 때**다.

    최저 달이 아닌 달이 더 높은 기준에 걸릴 수 있다.
    """
    frame = _frame([(202601, "A", 1.12), (202602, "A", 1.15)])
    thresholds = SecurementThresholds(1.095, 0.995, monthly=((202602, 1.195, None),))

    (item,) = build_process_picker_summary(
        frame, ["A"], start_month=202601, end_month=202603, thresholds=thresholds
    )

    assert (item.minimum_rate, item.minimum_month) == (1.12, 202601)
    assert item.group == "shortfall"
    # 예외가 없으면 같은 값이 충족이다.
    (plain,) = build_process_picker_summary(
        frame,
        ["A"],
        start_month=202601,
        end_month=202603,
        thresholds=SecurementThresholds(1.095, 0.995),
    )
    assert plain.group == "sufficient"


def test_the_shortfall_order_keeps_only_shortfall_processes_lowest_rate_first() -> None:
    """공정 Capa 상세 ◀▶ 차례 — 미달 공정만, 최저 확보율이 낮은 차례, 같으면 입력(표시순서) 차례."""
    items = (
        ProcessPickerItem("DEMO-A", 0.95, 202602, 3, "shortfall"),
        ProcessPickerItem("DEMO-B", None, None, 0, "unavailable"),
        ProcessPickerItem("DEMO-C", 0.90, 202601, 3, "shortfall"),
        ProcessPickerItem("DEMO-D", 0.80, 202603, 3, "sufficient"),
        ProcessPickerItem("DEMO-E", 0.90, 202603, 3, "shortfall"),
    )

    assert [item.process for item in shortfall_order(items)] == ["DEMO-C", "DEMO-E", "DEMO-A"]
    assert shortfall_order(()) == ()


NO_RATE = "조회기간에 유효한 확보율이 없어 판정하지 않습니다."
OUTSIDE_BOX = "소요기준 BOX — 산식이 정해질 때까지 계산 밖입니다(추가 예정)."


def test_only_an_unavailable_outside_tile_swaps_its_rate_and_reason() -> None:
    """「확보율 없음」 구역의 계산 밖 공정만 단추 끝 글이 「계산 밖」 이고 풍선의 확보율 없음 줄이
    그 소요기준 까닭이다(정식판 1.0 마감 2번 C). 유효한 확보율이 있는 단추(과거 구간 달 등)는
    소요기준 글을 받아도 「97%」 · 확보율 줄 그대로다 — 판정이 그 값으로 선다."""
    unavailable = ProcessPickerItem("DEMO_BOX", None, None, 0, "unavailable")
    shortfall = ProcessPickerItem("DEMO_BOX", 0.965, 202601, 1, "shortfall")
    sufficient = ProcessPickerItem("DEMO_BOX", 1.2, 202601, 1, "sufficient")

    assert tile_rate_text(unavailable, outside="BOX") == "계산 밖"
    assert tile_rate_text(unavailable) is None
    assert tile_rate_text(shortfall, outside="BOX") == "97%"
    assert tile_rate_text(sufficient, outside="BOX") is None

    lines = tile_tooltip_text(unavailable, "포장", enabled=True, outside="BOX").split("\n")
    assert lines == ["포장", "원본 공정: DEMO_BOX", OUTSIDE_BOX, "ON · 누르면 제외"]
    assert NO_RATE in tile_tooltip_text(unavailable, "포장", enabled=True)
    assert "소요기준 BOX · PCB — 산식이" in tile_tooltip_text(
        unavailable, "포장", enabled=False, outside="BOX · PCB"
    )
    kept = tile_tooltip_text(shortfall, "포장", enabled=True, outside="BOX")
    assert "기간 최저 96.5%" in kept and "계산 밖" not in kept


def test_an_outside_calculation_tile_says_so_in_the_unavailable_group() -> None:
    """HOME 공정 필터 팝업 — 「확보율 없음」 구역에 선 계산 밖 공정 단추는 이름 오른쪽에 「계산 밖」
    이 붙고(최저 확보율과 같은 `::after` 자리) 풍선이 그 소요기준 까닭을 말한다. 단추 라벨은 표시명,
    소요기준 글의 키 · 콜백은 원본 공정이다. 같은 구역의 다른 공정 · 다른 구역은 그대로다."""

    def script() -> None:
        import streamlit as st

        from capa_simulation.components.process_picker import render_process_picker
        from capa_simulation.services.process_picker import ProcessPickerItem

        render_process_picker(
            [
                ProcessPickerItem("DEMO_A", 0.965, 202601, 3, "shortfall"),
                ProcessPickerItem("DEMO_BOX", None, None, 0, "unavailable"),
                ProcessPickerItem("DEMO_C", None, None, 0, "unavailable"),
            ],
            {"DEMO_BOX"},
            format_func=lambda process: {"DEMO_A": "몰드", "DEMO_BOX": "포장", "DEMO_C": "검사"}[
                process
            ],
            on_toggle=lambda process: st.session_state.update(toggled=process),
            outside={"DEMO_BOX": "BOX"},
        )

    app = AppTest.from_function(script).run()

    assert not app.exception, [item.message for item in app.exception]
    assert [button.label for button in app.button] == ["몰드", "포장", "검사"]
    body = " ".join(str(element.proto.body) for element in app.get("html"))
    assert '.st-key-home_bn_tile_0 button::after { content: "97%"; }' in body
    assert '.st-key-home_bn_tile_1 button::after { content: "계산 밖"; }' in body
    assert "home_bn_tile_2 button::after" not in body
    assert f"원본 공정: DEMO_BOX\\A {OUTSIDE_BOX}\\A ON · 누르면 제외" in body
    assert f"원본 공정: DEMO_C\\A {NO_RATE}" in body
    assert "**확보율 없음 · 2**" in [str(item.value) for item in app.markdown]

    app.button(key="home_bn_process_tile_DEMO_BOX").click().run()
    assert app.session_state["toggled"] == "DEMO_BOX"
