# Purpose: Dummy 계열(Dummy · Top_Dummy) 행 빼기의 판별 게이트와 산식 · 소요대수 불변을 고정한다.

"""HOME 집계 기준은 Dummy 계열 행을 뺀다 — 산식 목록과 따로인 두 번째 목록이다.

- 판별은 Dummy 산식과 같은 `(제품타입, WF 구분)` 게이트다. EDP-TSV 의 이름만 `Dummy` 인 행은 빼지
  않고, 제품타입이 빈 행만 이름으로 고른다.
- `Top_Dummy` 는 빼는 목록에만 있다. 산식은 일반식 그대로다(`(1 - EDS_수율)` 을 곱하지 않는다).
- 빼는 일은 집계 쪽에서만 한다 — 소요대수가 읽는 부하량은 Dummy 계열을 그대로 품는다.
"""

from __future__ import annotations

import dummy_series_tables as demo
import pandas as pd
import pytest

from capa_simulation.services.dashboard import home_aggregation_wafer_load
from capa_simulation.services.load_calculator import (
    LOAD_EXCLUSIONS_ATTR,
    calculate_chip_and_wafer_loads,
    exclude_dummy_series,
    wf_division_mask,
)
from capa_simulation.services.product_type import (
    DUMMY_DIVISIONS_BY_PRODUCT_TYPE,
    DUMMY_SERIES_DIVISIONS_BY_PRODUCT_TYPE,
    EDP_PRODUCT_TYPE,
    HBM_PRODUCT_TYPE,
    TOP_DUMMY_DIVISION,
)


def _load(rows: list[tuple[object, str]], *, with_type: bool = True) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "생산계획년월": [202601] * len(rows),
            "제품정보": [f"DEMO-{index}" for index in range(len(rows))],
            "WF 구분": [division for _type, division in rows],
            "물량": [float(index + 1) for index in range(len(rows))],
        }
    )
    if with_type:
        frame["제품타입"] = pd.Series(
            [product_type for product_type, _division in rows], dtype="object"
        )
    return frame


def test_the_series_list_is_separate_from_the_formula_list() -> None:
    """산식 목록은 Dummy 하나 그대로이고, 빼는 목록에만 Top_Dummy 가 더해진다."""
    assert DUMMY_DIVISIONS_BY_PRODUCT_TYPE[HBM_PRODUCT_TYPE] == ("Dummy",)
    assert DUMMY_SERIES_DIVISIONS_BY_PRODUCT_TYPE[HBM_PRODUCT_TYPE] == ("Dummy", TOP_DUMMY_DIVISION)
    assert TOP_DUMMY_DIVISION == "Top_Dummy"
    assert DUMMY_SERIES_DIVISIONS_BY_PRODUCT_TYPE[EDP_PRODUCT_TYPE] == ()


def test_the_gate_drops_hbm_dummy_series_but_keeps_edp_rows_named_dummy() -> None:
    load = _load(
        [
            ("HBM", "Core"),
            ("HBM", "Buffer"),
            ("HBM", "TOP"),
            ("HBM", "Dummy"),
            ("HBM", "Top_Dummy"),
            ("EDP-TSV", "Dummy"),
            ("EDP-TSV", "Top_Dummy"),
            ("EDP-TSV", "Top_e"),
        ]
    )
    kept = exclude_dummy_series(load)
    assert list(kept["WF 구분"]) == ["Core", "Buffer", "TOP", "Dummy", "Top_Dummy", "Top_e"]
    assert list(kept["제품타입"]) == ["HBM", "HBM", "HBM", "EDP-TSV", "EDP-TSV", "EDP-TSV"]


@pytest.mark.parametrize("spelling", ["Top_Dummy", "TOP_DUMMY", " top_dummy ", "DUMMY", "dummy"])
def test_the_gate_ignores_case_and_surrounding_spaces(spelling: str) -> None:
    load = _load([("HBM", spelling), ("hbm ", spelling), ("HBM", "Core")])
    assert list(exclude_dummy_series(load)["WF 구분"]) == ["Core"]


def test_rows_without_a_product_type_are_judged_by_name() -> None:
    """제품타입이 빈 행(옛 리비전 · 원천 NULL)과 제품타입 칸이 없는 프레임은 이름만 본다."""
    blank_type = _load([("", "Top_Dummy"), (None, "Dummy"), (pd.NA, "Core")])
    assert list(exclude_dummy_series(blank_type)["WF 구분"]) == ["Core"]
    no_column = _load([("HBM", "Dummy"), ("HBM", "TOP_DUMMY"), ("HBM", "Slave")], with_type=False)
    assert list(exclude_dummy_series(no_column)["WF 구분"]) == ["Slave"]


def test_the_formula_mask_and_the_series_mask_share_one_gate() -> None:
    load = _load([("HBM", "Dummy"), ("HBM", "Top_Dummy"), ("EDP-TSV", "Dummy"), ("", "Dummy")])
    assert list(wf_division_mask(load, DUMMY_DIVISIONS_BY_PRODUCT_TYPE)) == [
        True,
        False,
        False,
        True,
    ]
    assert list(wf_division_mask(load, DUMMY_SERIES_DIVISIONS_BY_PRODUCT_TYPE)) == [
        True,
        True,
        False,
        True,
    ]


def test_exclusions_are_carried_and_the_input_is_left_alone() -> None:
    load = _load([("HBM", "Core"), ("HBM", "Dummy")])
    record = ((202601, "DEMO-X", "12H", "Core", "RQ_YLD"),)
    load.attrs[LOAD_EXCLUSIONS_ATTR] = record
    kept = exclude_dummy_series(load)
    assert kept.attrs[LOAD_EXCLUSIONS_ATTR] == record
    assert list(load["WF 구분"]) == ["Core", "Dummy"]
    assert kept is not load
    pd.testing.assert_frame_equal(home_aggregation_wafer_load(load), kept)


def test_top_dummy_keeps_the_general_formula() -> None:
    """Top_Dummy 의 Chip · Wafer 는 일반식이다 — Dummy 산식(`(1 - EDS_수율)`)을 받지 않는다."""
    chip_load, wafer_load = calculate_chip_and_wafer_loads(
        demo.plan(), demo.yields(), demo.chip_qty()
    )
    row = wafer_load.loc[
        wafer_load["제품정보"].eq(demo.HBM)
        & wafer_load["WF 구분"].eq("TOP_DUMMY")
        & wafer_load["생산계획년월"].eq(202601)
    ].iloc[0]
    assert row["물량"] == pytest.approx(100 * 1_000 * 1.0 / 0.85 / 0.95 / 800)
    chip = chip_load.loc[
        chip_load["제품정보"].eq(demo.HBM)
        & chip_load["WF 구분"].eq("TOP_DUMMY")
        & chip_load["생산계획년월"].eq(202601)
    ].iloc[0]
    assert chip["물량"] == pytest.approx(100 * 1.0 / 0.95)


def test_the_load_that_demand_reads_keeps_the_dummy_series() -> None:
    """소요대수 · 환산 탭 기본이 읽는 부하량은 Dummy 계열 행을 그대로 품는다 — 빼는 일은 집계 쪽."""
    _chip, wafer_load = calculate_chip_and_wafer_loads(demo.plan(), demo.yields(), demo.chip_qty())
    divisions = set(wafer_load["WF 구분"])
    assert {"Dummy", "TOP_DUMMY", "Top_Dummy"} <= divisions
    assert set(exclude_dummy_series(wafer_load)["WF 구분"]) == {
        "Buffer",
        "Core",
        "Top",
        "Master",
        "Slave",
        "Dummy",
    }
