# Purpose: 공정 선택 요약의 기간 최소값·판정 경계·결측 처리와 원본 키·순서 보존을 검증한다.

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from capa_simulation.services.process_picker import ProcessPickerItem, build_process_picker_summary


def _frame(rows: list[tuple[int, str, float | None]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["생산계획년월", "공정", "확보율"])


def _summary(frame: pd.DataFrame, options: list[str], threshold: float = 1.0):
    return build_process_picker_summary(
        frame, options, start_month=202601, end_month=202603, secure_threshold=threshold
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
        items[0].minimum_rate = 0.0


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
def test_equal_threshold_is_shortfall_like_home_and_only_strictly_higher_is_sufficient(
    threshold,
) -> None:
    """HOME 은 기준과 같은 확보율을 경고(기준 미달)로 센다. 선택 화면도 같아야 한다."""
    frame = _frame(
        [
            (202601, "동일", threshold),
            (202601, "초과", threshold + 0.01),
            (202601, "미만", threshold - 0.01),
        ]
    )

    assert [item.group for item in _summary(frame, ["동일", "초과", "미만"], threshold)] == [
        "shortfall",
        "sufficient",
        "shortfall",
    ]


@pytest.mark.parametrize("rate,expected", [(0.9, "shortfall"), (1.1, "sufficient")])
def test_all_or_none_are_shortfall_without_reordering_options(rate, expected) -> None:
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
def test_invalid_threshold_is_rejected(threshold) -> None:
    with pytest.raises(ValueError, match="확보 기준"):
        _summary(_frame([]), [], threshold)


@pytest.mark.parametrize("start,end", [(202600, 202603), (202603, 202601)])
def test_invalid_query_bounds_are_rejected(start, end) -> None:
    with pytest.raises(ValueError):
        build_process_picker_summary(
            _frame([]), [], start_month=start, end_month=end, secure_threshold=1.0
        )
