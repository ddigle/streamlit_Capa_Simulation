# Purpose: 사용기준 HBM 호기만 Dynamic 가용대수·단축 후보·일정 미정에 세는 규칙과 알림을 검증한다.

"""사용기준 HBM 규칙(2026-10-07 사용자 결정).

「사용기준이 HBM 인 호기만 Dynamic 가용대수로 센다. 배치는 그대로 둔다.」 규칙은
`equipment_contract.counts_for_capacity` 한 곳이고, 세는 자리(주차·월별 대수, 교차검증이 쓰는 환산
소계, 필요단축일정 후보, 일정 미정 알림)는 모두 그것을 본다. 기존 보유대수 표는 사용기준이 없어
지금처럼 센다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_equipment_status_as_of,
    build_space_equipment_status,
    build_weekly_equipment_availability,
)
from capa_simulation.services.equipment_contract import (
    COUNTED_COLUMN,
    COUNTED_USAGE_BASIS,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    counts_for_capacity,
)
from capa_simulation.services.equipment_samples import sample_equipment_master
from capa_simulation.services.monthly_equipment_availability import (
    available_subtotal,
    build_monthly_equipment_availability,
    build_monthly_equipment_contributions,
)
from capa_simulation.services.required_shortening import shortening_candidates
from capa_simulation.services.securement_cross_check import dynamic_available_equipment
from capa_simulation.services.undated_equipment import undated_equipment
from capa_simulation.services.usage_basis import (
    usage_excluded_count,
    usage_excluded_equipment,
    usage_exclusion_notice,
)

PROCESS = "DEMO_HBM"
OTHER = "DEMO_OTHER"


def _unit(name: str, basis: object, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = dict.fromkeys(EQUIPMENT_COLUMNS)
    row.update(
        {
            "설비명": name,
            "공정소분류": PROCESS,
            "공정대분류": "B/N",
            "사용기준": basis,
            "반입일정": "2025-10-01",
            "Qual일정": "2025-10-20",
            "확정상태": "완료",
            "보관유무": "N",
            "기존설비여부": "N",
            "레이아웃표시": "N",
        }
    )
    row.update(overrides)
    return row


def _master(*rows: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=list(EQUIPMENT_COLUMNS))


def _no_downtime() -> pd.DataFrame:
    return pd.DataFrame(columns=list(DOWNTIME_COLUMNS))


def _baseline(count: float = 3.0) -> pd.DataFrame:
    return pd.DataFrame(
        {"공정": [PROCESS], "분류": ["전체"], "기존보유대수": [count], "비고": [None]}
    )


def _cutoff_zero() -> pd.DataFrame:
    return pd.DataFrame({"공정": [PROCESS], "제품구분": ["*"], "Cutoff일수": [0]})


def _spans(equipment: pd.DataFrame) -> pd.DataFrame:
    return build_equipment_lifecycle_spans(
        equipment,
        _no_downtime(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        with_unit_share=True,
    )


def _weekly(equipment: pd.DataFrame, baseline: pd.DataFrame | None = None) -> pd.Series:
    """2026-03-02 주 한 줄."""
    weekly = build_weekly_equipment_availability(
        baseline if baseline is not None else _baseline(0.0).iloc[0:0],
        equipment,
        _no_downtime(),
        start_date=date(2026, 3, 2),
        end_date=date(2026, 3, 8),
    )
    return weekly.loc[weekly["공정소분류"].eq(PROCESS)].iloc[0]


# ------------------------------------------------------------------- 규칙


@pytest.mark.parametrize(
    ("basis", "counted"),
    [
        ("HBM", True),
        ("hbm", True),
        (" HBM ", True),
        ("\tHbm\n", True),
        ("HBM3E", False),
        ("HBM 양산", False),
        ("범용", False),
        ("", False),
        ("   ", False),
        (None, False),
        (pd.NA, False),
    ],
)
def test_only_an_exact_hbm_counts_ignoring_case_and_spaces(basis: object, counted: bool) -> None:
    frame = pd.DataFrame({"사용기준": [basis]})

    assert counts_for_capacity(frame).tolist() == [counted]


def test_the_counted_basis_is_declared_once() -> None:
    assert COUNTED_USAGE_BASIS == ("HBM",)


def test_a_frame_without_the_column_counts_nothing() -> None:
    assert counts_for_capacity(pd.DataFrame({"설비명": ["EQ-1"]})).tolist() == [False]


def test_the_status_frame_carries_the_flag_but_keeps_every_unit() -> None:
    """상태 판정은 호기를 빼지 않는다 — Space·호기 목록·상태 분포가 같은 판정을 본다."""
    equipment = _master(_unit("HBM-1", "HBM"), _unit("OTH-1", "범용"))

    status = build_equipment_status_as_of(equipment, _no_downtime(), as_of=date(2026, 3, 1))
    space = build_space_equipment_status(equipment, _no_downtime(), as_of=date(2026, 3, 1))

    assert status["설비명"].tolist() == ["HBM-1", "OTH-1"]
    assert status["상태"].tolist() == ["가용", "가용"]
    assert status[COUNTED_COLUMN].tolist() == [True, False]
    assert space["설비명"].tolist() == ["HBM-1", "OTH-1"]
    assert space["단계"].tolist() == ["가용", "가용"]


# ------------------------------------------------------------------- 주차·월별


def test_the_weekly_count_leaves_out_non_hbm_units_entirely() -> None:
    """HBM 이 아닌 호기는 가용뿐 아니라 총대수·비가동·분류 칸에서도 빠진다 — 가용만 빼면 그
    호기가 모두 비가동으로 세어진다. 기존 보유대수는 사용기준이 없어 그대로 센다.
    """
    equipment = _master(
        _unit("HBM-1", "HBM"),
        _unit("HBM-2", " hbm "),
        _unit("OTH-1", "HBM3E"),
        _unit("BLK-1", None),
        _unit("SET-1", "범용", **{"Qual일정": None, "확정상태": None}),
    )

    row = _weekly(equipment, _baseline(3.0))

    assert row["기존보유대수"] == 3.0
    assert row["추가설비대수"] == 2.0
    assert row["총대수"] == 5.0
    assert row["가용대수"] == 5.0
    assert row["비가동대수"] == 0.0
    assert row["가용호기대수"] == 2.0
    assert row["셋업중대수"] == 0.0


def test_the_monthly_table_counts_only_hbm_on_both_axes() -> None:
    """대수와 환산대수 둘 다 HBM 만 센다 — 교차검증·필요단축일정이 쓰는 환산 소계도 같다."""
    equipment = _master(
        _unit("HBM-1", "HBM", 환산비=1.5),
        _unit("OTH-1", "범용", 환산비=2.0),
        _unit("BLK-1", None),
        _unit("SET-1", "범용", **{"Qual일정": None, "확정상태": None}),
    )
    spans = _spans(equipment)
    ratios = {"HBM-1": 1.5, "OTH-1": 2.0}

    monthly = build_monthly_equipment_availability(
        spans, _baseline(3.0), _cutoff_zero(), [202602], conversion_ratios=ratios
    )
    contributions = build_monthly_equipment_contributions(
        spans, _baseline(3.0), _cutoff_zero(), [202602], conversion_ratios=ratios
    )

    assert monthly.set_index("분류")["대수"].to_dict() == {"기존보유": 3.0, "가용": 1.0}
    subtotal = available_subtotal(monthly).iloc[0]
    assert subtotal["Dynamic가용대수"] == pytest.approx(4.0)
    assert subtotal["Dynamic가용환산대수"] == pytest.approx(4.5)
    assert set(contributions["설비명"].dropna()) == {"HBM-1"}
    cross = dynamic_available_equipment(monthly)
    assert cross["가용대수"].tolist() == pytest.approx([4.5])


def test_the_baseline_still_counts_when_no_unit_is_hbm() -> None:
    """호기가 모두 HBM 이 아니어도 기존보유는 센다. 구간은 남아 공정이 숨지 않는다."""
    equipment = _master(_unit("OTH-1", "범용"))
    spans = _spans(equipment)

    monthly = build_monthly_equipment_availability(spans, _baseline(2.0), _cutoff_zero(), [202602])

    assert set(spans["설비명"]) == {"OTH-1"}
    assert monthly.set_index("분류")["대수"].to_dict() == {"기존보유": 2.0}


def test_a_module_group_counts_the_share_of_its_hbm_rows() -> None:
    """사용기준은 행마다 본다. 모듈 넷이 모두 HBM 이면 한 대, 둘만이면 0.5대, 하나도 아니면 0."""

    def modules(parent: str, bases: tuple[object, ...]) -> list[dict[str, Any]]:
        return [
            _unit(f"{parent}{tag}", basis, **{"Main 설비": parent, "환산비": 0.25})
            for tag, basis in zip("ABCD", bases, strict=True)
        ]

    equipment = _master(
        *modules("ALL", ("HBM", "HBM", "HBM", "HBM")),
        *modules("HALF", ("HBM", "HBM", "범용", None)),
        *modules("NONE", ("범용", "범용", "범용", "범용")),
    )

    weekly = _weekly(equipment)
    monthly = build_monthly_equipment_contributions(
        _spans(equipment), _baseline(0.0).iloc[0:0], _cutoff_zero(), [202602]
    )

    assert weekly["가용대수"] == pytest.approx(1.5)
    assert weekly["총대수"] == pytest.approx(1.5)
    by_unit = monthly.groupby("설비키")["대수"].sum().to_dict()
    assert by_unit == pytest.approx({"ALL": 1.0, "HALF": 0.5})


# ------------------------------------------------------------------- 후보·일정 미정


def test_shortening_never_pulls_a_non_hbm_unit() -> None:
    """HBM 이 아닌 호기는 당겨도 가용대수가 늘지 않는다 — 후보가 아니다. 섞인 묶음은 HBM 모듈만."""
    future = {"Qual일정": "2026-08-01", "확정상태": "계획"}
    equipment = _master(
        _unit("HBM-1", "HBM", **future),
        _unit("OTH-1", "범용", **future),
        _unit("BLK-1", None, **future),
        _unit("MIX-A", "HBM", **future, **{"Main 설비": "MIX"}),
        _unit("MIX-B", "범용", **future, **{"Main 설비": "MIX"}),
    )

    candidates = shortening_candidates(equipment, _no_downtime())

    assert {unit.unit for unit in candidates} == {"HBM-1", "MIX"}
    mixed = next(unit for unit in candidates if unit.unit == "MIX")
    assert [module.equipment_id for module in mixed.modules] == ["MIX-A"]


def test_undated_notice_counts_only_hbm_units() -> None:
    """날짜를 채워도 가용대수에 들지 않는 호기는 일정 미정으로 알리지 않는다."""
    no_qual = {"Qual일정": None, "확정상태": None}
    equipment = _master(
        _unit("HBM-1", "HBM", **no_qual),
        _unit("OTH-1", "범용", **no_qual),
        _unit("BLK-1", None, **no_qual),
    )

    assert undated_equipment(equipment)["설비명"].tolist() == ["HBM-1"]


def test_undated_module_shares_are_set_before_the_usage_filter() -> None:
    """반입 안 된 모듈 넷 중 둘만 HBM 이면 Dynamic 의 입고 예정이 0.5대이고, 일정 미정도 0.5대다."""
    unarrived = {"반입일정": None, "Qual일정": None, "확정상태": None, "Main 설비": "MOD"}
    equipment = _master(
        _unit("MOD-A", "HBM", **unarrived),
        _unit("MOD-B", "HBM", **unarrived),
        _unit("MOD-C", "범용", **unarrived),
        _unit("MOD-D", None, **unarrived),
    )

    rows = undated_equipment(equipment)

    assert rows["설비명"].tolist() == ["MOD-A", "MOD-B"]
    assert float(rows["설비지분"].sum()) == pytest.approx(0.5)


# ------------------------------------------------------------------- 제외 알림


def test_the_exclusion_notice_counts_units_and_disappears_at_zero() -> None:
    equipment = _master(
        _unit("HBM-1", "HBM"),
        _unit("OTH-1", "범용"),
        _unit("BLK-1", None, 공정소분류=OTHER),
        _unit("MIX-A", "HBM", **{"Main 설비": "MIX"}),
        _unit("MIX-B", "HBM3E", **{"Main 설비": "MIX"}),
    )

    excluded = usage_excluded_equipment(equipment)

    assert excluded["설비명"].tolist() == ["OTH-1", "BLK-1", "MIX-B"]
    assert usage_excluded_count(excluded) == pytest.approx(2.5)
    assert usage_excluded_count(excluded, processes={PROCESS}) == pytest.approx(1.5)
    assert usage_excluded_count(excluded, unit_ids={"MIX-B"}) == pytest.approx(0.5)
    notice = usage_exclusion_notice(excluded, processes={PROCESS})
    assert notice == (
        "사용기준이 HBM 이 아닌 1.5대(호기 마스터 기준)는 가용대수에서 뺐습니다 — "
        "배치·호기 목록에는 그대로 있습니다."
    )
    assert usage_exclusion_notice(excluded, unit_ids={"HBM-1"}) is None
    assert usage_exclusion_notice(usage_excluded_equipment(_master(_unit("HBM-1", "HBM")))) is None


def test_the_sample_fleet_is_mostly_hbm_with_a_few_exclusions() -> None:
    """빈 DB 의 샘플은 사용기준이 비면 가용대수가 통째로 빈다. 대부분 HBM 이고 몇 대만 뺀다."""
    sample = sample_equipment_master(anchor_date=date(2026, 10, 7))
    counted = counts_for_capacity(sample)

    assert counted.mean() > 0.9
    assert 0 < int((~counted).sum()) <= 3
