# Purpose: 기준정보 편집이 계산에 필요한 다른 표의 행·값을 깨뜨리면 적용 전에 걸리는지 검증한다.

"""**저장은 되는데 화면에서 터지는 일**을 저장 경계에서 막는지 본다.

사내에서 실제로 겪은 순서가 이랬다(2026-09-23). `RQ_UPEH` 의 빈 월 칸에 값을 넣고 적용
→ 정상 완료 → Capa LOB Summary 로 가니 「RQ_LOT_RATIO 연결값이 없는 대당 Capa 기준이
있습니다」. 빈 칸을 채우는 것은 값 수정이 아니라 **경로를 하나 더 만드는 일**인데, 저장
경계에 표 사이 정합성을 보는 검사가 없었다.

여기서 고정하는 것은 셋이다 — 새 조합을 찾는가, 측정률 두 표를 **함께** 보는가,
**이미 어긋나 있던 것은 건드리지 않는가.**
"""

from __future__ import annotations

import pandas as pd

from capa_simulation.services.reference_consistency import (
    added_performance_keys,
    cleared_keys_in_use,
    describe_cleared_keys_in_use,
    describe_missing_path_rows,
    describe_missing_ratio_rows,
    describe_nonpositive_keys_in_use,
    missing_ratio_rows,
    missing_required_rows,
    nonpositive_keys_in_use,
)
from capa_simulation.services.unit_capacity import PERFORMANCE_KEYS


def _row(month: int, process: str = "Process-A", stack: str = "8") -> dict[str, object]:
    return {
        "생산계획년월": month,
        "Area_Name": "Main",
        "공정": process,
        "STEP_SEQ": 10,
        "MCP_SEQ": 1,
        "양산구분": "양산",
        "제품정보": "DEMO-A",
        "Stack": stack,
        "WF 구분": "Top",
    }


def _upeh(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["소요기준"] = "WF"
    frame["UPEH"] = 100.0
    frame["ST"] = 0.0
    return frame


def _ratio(rows: list[dict[str, object]], value_column: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows) if rows else pd.DataFrame(columns=PERFORMANCE_KEYS)
    frame[value_column] = 1.0
    return frame


def _tables(lot_rows: list[dict[str, object]], wf_rows: list[dict[str, object]]) -> dict:
    return {
        "RQ_LOT_RATIO": _ratio(lot_rows, "Lot 측정률"),
        "RQ_WF_RATIO": _ratio(wf_rows, "WF측정률"),
    }


def test_filling_an_empty_month_is_reported_as_a_new_path() -> None:
    """빈 칸 채우기는 값 수정이 아니라 행 추가다. 그것이 이 검사의 출발점이다."""
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])

    added = added_performance_keys(before, after)

    assert len(added) == 1
    assert int(added.loc[0, "생산계획년월"]) == 202609


def test_both_ratio_tables_are_reported_at_once() -> None:
    """Lot 만 채우면 다음 조인에서 WF 로 같은 문구가 이어진다. 한 번에 알린다."""
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    added = added_performance_keys(before, after)

    missing = missing_ratio_rows(added, _tables([_row(202608)], [_row(202608)]))

    assert set(missing) == {"RQ_LOT_RATIO", "RQ_WF_RATIO"}
    message = describe_missing_ratio_rows(missing)
    assert "Lot측정률" in message and "WF측정률" in message
    # 어느 달 어느 경로인지 말해 줘야 그 칸을 찾을 수 있다.
    assert "202609" in message and "Process-A" in message


def test_a_path_that_already_has_ratio_rows_passes() -> None:
    """측정률이 갖춰진 경로를 채우는 것은 막을 이유가 없다."""
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    added = added_performance_keys(before, after)

    missing = missing_ratio_rows(
        added, _tables([_row(202608), _row(202609)], [_row(202608), _row(202609)])
    )

    assert missing == {}


def test_a_pre_existing_gap_does_not_block_an_unrelated_edit() -> None:
    """**이미 어긋나 있던 것은 건드리지 않는다.**

    막으면 상관없는 칸 하나를 고치려던 사람이 자기가 만들지 않은 문제에 걸려 아무것도
    못 한다. 되돌릴 길까지 막는 셈이다.
    """
    # 202608 은 처음부터 측정률이 없다. 편집은 그 행을 건드리지 않았다.
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608)])

    added = added_performance_keys(before, after)

    assert added.empty
    assert missing_ratio_rows(added, _tables([], [])) == {}


def test_only_one_side_missing_is_reported_alone() -> None:
    """Lot 은 있고 WF 만 없으면 WF 만 말한다."""
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    added = added_performance_keys(before, after)

    missing = missing_ratio_rows(added, _tables([_row(202608), _row(202609)], [_row(202608)]))

    assert set(missing) == {"RQ_WF_RATIO"}


def test_whitespace_and_month_shape_do_not_create_false_gaps() -> None:
    """조인과 **같은 규칙으로** 줄여야 없는 결손을 있다고 하지 않는다.

    `_join_reference` 는 월 정규화·공백 제거·`Area_Name` 정규화를 거쳐 맞댄다.
    """
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    ratio_row = _row(202609)
    ratio_row["공정"] = " Process-A "
    ratio_row["Area_Name"] = "main"
    lot = [_row(202608), ratio_row]

    added = added_performance_keys(before, after)
    missing = missing_ratio_rows(added, _tables(lot, [_row(202608), _row(202609)]))

    assert missing == {}


def test_the_missing_ratio_message_matches_the_one_point_zero_assumption() -> None:
    """측정률 행이 없으면 계산은 멈추지 않고 1.0 으로 가정한다(40a09b8).

    그 뒤로도 문구가 「계산 화면을 열 때 … 멈춥니다」였다. 막는 것은 정책으로 남기되(새 경로는
    측정률을 먼저 갖춘다) 이유는 지금 동작대로 말한다.
    """
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    missing = missing_ratio_rows(
        added_performance_keys(before, after), _tables([_row(202608)], [_row(202608)])
    )

    message = describe_missing_ratio_rows(missing)

    assert "멈춥니다" not in message
    assert "1.0 으로 가정" in message


def _run_rate(values: dict[tuple[int, str], float | None]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"생산계획년월": month, "공정": process, "양산구분": "양산", "CAPA_RUN_RATE": value}
            for (month, process), value in values.items()
        ]
    )


def test_clearing_a_cell_an_upeh_path_uses_is_reported() -> None:
    """효율·여유율·일수는 중립값이 없어, 경로가 쓰는 칸을 비우면 계산 전체가 멈춘다(결함 4).

    **쓰는 경로가 없는 칸을 비우는 것은 막지 않는다.** 처음부터 비어 있던 칸도 이번 편집이 만든
    문제가 아니라 세지 않는다.
    """
    before = _run_rate(
        {
            (202608, "Process-A"): 0.9,
            (202609, "Process-A"): 0.9,
            (202608, "Process-B"): 0.9,
            (202609, "Process-B"): None,
        }
    )
    # A 의 202609 와 B 의 202608 을 비웠다. B 의 202609 는 처음부터 비어 있었다.
    after = _run_rate({(202608, "Process-A"): 0.9})
    upeh = _upeh([_row(202608), _row(202609), _row(202609, "Process-B")])

    cleared = cleared_keys_in_use("RQ_RUN_RATE", before, after, "CAPA_RUN_RATE", upeh)

    assert cleared.to_dict("records") == [
        {"생산계획년월": 202609, "공정": "Process-A", "양산구분": "양산"}
    ]
    message = describe_cleared_keys_in_use("효율", "RQ_RUN_RATE", cleared)
    assert "「효율」 표에서 값을 지운 칸 1개" in message
    assert "202609 · 공정=Process-A / 양산구분=양산" in message
    assert "RQ_RUN_RATE 연결값이 없는 대당 Capa 기준" in message


def test_a_path_the_calculation_skips_does_not_hold_a_cell() -> None:
    """BOX·PCB 소요기준 행은 조인 전에 빠진다. 그 행만 쓰는 칸은 비워도 계산이 멈추지 않는다."""
    before = _run_rate({(202608, "Process-A"): 0.9})
    after = before.head(0)
    upeh = _upeh([_row(202608)])
    upeh["소요기준"] = " box "

    assert cleared_keys_in_use("RQ_RUN_RATE", before, after, "CAPA_RUN_RATE", upeh).empty


def test_the_cleared_message_asks_for_a_value_above_zero() -> None:
    """「그 칸에 값을 넣거나」로는 0 을 넣어도 되는 줄 안다. 여유율·일수의 0 도 계산을 멈춘다."""
    cleared = pd.DataFrame([{"생산계획년월": 202608, "공정": "Process-A"}])

    message = describe_cleared_keys_in_use("일수", "RQ_RUN_DAY", cleared)

    assert "0보다 큰 값을 넣거나" in message


# ---------------------------- 2026-09-29 2차 리뷰: 새 경로의 효율·여유율·일수, 쓰는 칸의 0


def _required_tables(
    run_rate: dict[int, float | None],
    vital: dict[int, float | None],
    run_day: dict[int, float | None],
) -> dict[str, pd.DataFrame]:
    """Process-A·양산 한 경로가 쓰는 세 표. 값이 `None` 인 달은 행이 없다."""

    def frame(values: dict[int, float | None], value_column: str, mass: bool) -> pd.DataFrame:
        rows = [
            {
                "생산계획년월": month,
                "공정": "Process-A",
                **({"양산구분": "양산"} if mass else {}),
                value_column: value,
            }
            for month, value in values.items()
            if value is not None
        ]
        columns = ["생산계획년월", "공정", *(["양산구분"] if mass else []), value_column]
        return pd.DataFrame(rows, columns=columns)

    return {
        "RQ_RUN_RATE": frame(run_rate, "CAPA_RUN_RATE", True),
        "RQ_VITAL": frame(vital, "편중률", True),
        "RQ_RUN_DAY": frame(run_day, "RUN_DAY", False),
    }


def _calculation_halts(upeh: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> bool:
    """그 표들로 대당 Capa 를 돌리면 멈추는가. 측정률은 비워 1.0 가정으로 둔다."""
    from capa_simulation.services.unit_capacity import calculate_unit_capacity

    ratio = pd.DataFrame(columns=PERFORMANCE_KEYS)
    try:
        calculate_unit_capacity(
            upeh,
            tables["RQ_RUN_RATE"],
            tables["RQ_VITAL"],
            pd.DataFrame({"공정": ["Process-A"], "모듈수": [1.0]}),
            tables["RQ_RUN_DAY"],
            ratio.assign(**{"Lot 측정률": pd.Series(dtype="float64")}),
            ratio.assign(**{"WF측정률": pd.Series(dtype="float64")}),
        )
    except ValueError:
        return True
    return False


def test_filling_a_month_without_a_run_rate_row_is_reported_with_the_tab_and_key() -> None:
    """측정률만 보던 검사가 효율을 보지 않아, 효율 행이 없는 달을 채우면 계산 전체가 멈췄다.

    막을 때는 어느 탭 어느 (월, 키)인지와 멈추는 까닭을 말한다. 측정률 결손이 없으면 「1.0 으로
    가정」 문구는 나오지 않는다 — 효율에는 중립값이 없다.
    """
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    tables = _required_tables(
        run_rate={202608: 0.9},
        vital={202608: 1.0, 202609: 1.0},
        run_day={202608: 30.0, 202609: 30.0},
    )

    missing = missing_required_rows(before, after, tables)

    assert list(missing) == ["RQ_RUN_RATE"]
    assert missing["RQ_RUN_RATE"][["생산계획년월", "공정", "양산구분"]].to_dict("records") == [
        {"생산계획년월": 202609, "공정": "Process-A", "양산구분": "양산"}
    ]
    message = describe_missing_path_rows({}, missing)
    assert "「효율」 탭에 1건 — 202609 · 공정=Process-A / 양산구분=양산" in message
    assert "RQ_RUN_RATE 연결값이 없는 대당 Capa 기준이 있습니다" in message
    assert "1.0 으로 가정" not in message
    # 막지 않았다면 계산이 정말 멈췄다 — 검사가 계산과 같은 것을 본다.
    assert _calculation_halts(after, tables)


def test_the_check_mirrors_which_values_stop_the_calculation() -> None:
    """여유율·일수 0 은 계산을 멈추고(없는 것과 같다), 효율 0 은 그 경로만 제외한다(있는 것)."""
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    cases = {
        "vital zero": ({202608: 0.9, 202609: 0.9}, {202608: 1.0, 202609: 0.0}, None, "RQ_VITAL"),
        "run day zero": ({202608: 0.9, 202609: 0.9}, {202608: 1.0, 202609: 1.0}, 0.0, "RQ_RUN_DAY"),
        "run rate zero": ({202608: 0.9, 202609: 0.0}, {202608: 1.0, 202609: 1.0}, None, None),
        "all present": ({202608: 0.9, 202609: 0.9}, {202608: 1.0, 202609: 1.0}, None, None),
    }
    for name, (run_rate, vital, run_day_0609, reported) in cases.items():
        tables = _required_tables(
            run_rate, vital, {202608: 30.0, 202609: 30.0 if run_day_0609 is None else run_day_0609}
        )

        missing = missing_required_rows(before, after, tables)

        assert list(missing) == ([reported] if reported else []), name
        assert _calculation_halts(after, tables) is bool(reported), name
    tables = _required_tables(
        {202608: 0.9, 202609: 0.9}, {202608: 1.0, 202609: 0.0}, {202608: 30.0, 202609: 30.0}
    )
    message = describe_missing_path_rows({}, missing_required_rows(before, after, tables))
    assert "(지금 값 0)" in message
    assert "RQ_VITAL의 편중률 값은 0보다 커야 합니다" in message


def test_ratio_and_required_gaps_come_in_one_message() -> None:
    """측정률과 효율이 함께 빠졌으면 한 오류문이다. 따로 알리면 하나를 채운 뒤 또 막힌다."""
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    tables = _required_tables(
        run_rate={202608: 0.9}, vital={202608: 1.0}, run_day={202608: 30.0, 202609: 30.0}
    )
    ratio = missing_ratio_rows(
        added_performance_keys(before, after), _tables([_row(202608)], [_row(202608)])
    )

    message = describe_missing_path_rows(ratio, missing_required_rows(before, after, tables))

    for label in ("「효율」", "「여유율」", "「Lot측정률」", "「WF측정률」"):
        assert label in message, label
    assert "「일수」" not in message
    assert "측정률은 `1` 이 중립값" in message


def test_ratio_only_gaps_keep_the_ratio_message() -> None:
    """효율·여유율·일수가 갖춰졌으면 문구는 예전 측정률 문구 그대로다."""
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    ratio = missing_ratio_rows(
        added_performance_keys(before, after), _tables([_row(202608)], [_row(202608)])
    )

    assert describe_missing_path_rows(ratio, {}) == describe_missing_ratio_rows(ratio)


def test_required_rows_skip_box_paths_and_pre_existing_gaps() -> None:
    """계산이 쓰지 않는 BOX 경로와, 이번 편집이 만들지 않은 결손은 막지 않는다."""
    before = _upeh([_row(202608)])
    tables = _required_tables(run_rate={}, vital={}, run_day={})

    box = _upeh([_row(202608), _row(202609)])
    box.loc[1, "소요기준"] = " box "
    assert missing_required_rows(before, box, tables) == {}
    # 202608 은 처음부터 세 표 모두 없었다. 편집은 그 경로를 새로 만들지 않았다.
    assert missing_required_rows(before, before.copy(), tables) == {}


def _vital(values: dict[tuple[int, str], float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"생산계획년월": month, "공정": process, "양산구분": "양산", "편중률": value}
            for (month, process), value in values.items()
        ]
    )


def test_a_zero_in_a_cell_an_upeh_path_uses_is_reported() -> None:
    """여유율·일수의 0 은 비움과 같이 계산 전체를 멈춘다. 쓰는 칸만, 이번 편집이 만든 것만 센다."""
    before = _vital(
        {(202608, "Process-A"): 1.0, (202608, "Process-B"): 1.0, (202609, "Process-A"): 0.0}
    )
    # A·B 의 202608 을 0 으로 했다. B 는 쓰는 UPEH 경로가 없고, A 의 202609 는 원래 0 이었다.
    after = _vital(
        {(202608, "Process-A"): 0.0, (202608, "Process-B"): 0.0, (202609, "Process-A"): 0.0}
    )
    upeh = _upeh([_row(202608), _row(202609)])

    found = nonpositive_keys_in_use("RQ_VITAL", before, after, "편중률", upeh)

    assert found.to_dict("records") == [
        {"생산계획년월": 202608, "공정": "Process-A", "양산구분": "양산", "편중률": 0.0}
    ]
    message = describe_nonpositive_keys_in_use("여유율", "RQ_VITAL", "편중률", found)
    assert "「여유율」 표에 0 이하 값을 넣은 칸 1개" in message
    assert "202608 · 공정=Process-A / 양산구분=양산 (넣은 값 0)" in message
    assert "RQ_VITAL의 편중률 값은 0보다 커야 합니다" in message
    # 음수도 같다(붙여넣기는 편집기의 하한을 지나지 않는다).
    negative = _vital({(202608, "Process-A"): -1.0})
    assert not nonpositive_keys_in_use("RQ_VITAL", before, negative, "편중률", upeh).empty
