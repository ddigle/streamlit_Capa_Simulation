# Purpose: 설비 캐시 키가 넘겨받은 지문으로도 같은 칸을 쓰고 프레임을 다시 해시하지 않는지 지킨다.

"""설비 마스터 지문을 부르는 쪽이 넘기는 꼴(`equipment_digest`)과 월 부하 환산의 키 꼴.

- 넘긴 지문이 `frame_digest(equipment)` 와 같으면 키도 넘기지 않은 때와 같다 — 지문을 넘기는 화면과
  넘기지 않는 화면이 한 칸을 나눈다.
- 넘기면 그 함수는 마스터를 다시 해시하지 않는다(`frame_digest` 를 마스터에 부르지 않는다).
- 프레임은 `_` 인자라 Streamlit 이 해시하지 않는다 — 값은 원 계산과 같다.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pandas as pd
import pytest
import streamlit as st

from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.display_order_editor import DISPLAY_ORDER_COLUMNS
from capa_simulation.services.equipment_availability import (
    build_space_equipment_status,
    build_weekly_equipment_availability,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.load_calculator import build_monthly_volume
from capa_simulation.services.manual_downtime import ManualDowntime
from capa_simulation.services.schedule_confirmation import schedule_confirmation_issues
from capa_simulation.services.undated_equipment import undated_equipment
from capa_simulation.services.usage_basis import usage_excluded_equipment

ANCHOR = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def _fresh_caches() -> Iterator[None]:
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def _frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        sample_equipment_baseline(),
        sample_equipment_master(anchor_date=ANCHOR),
        sample_downtime_schedule(anchor_date=ANCHOR),
    )


class _DigestSpy:
    """`simulation_cache.frame_digest` 를 감싸 마스터(설비명 칸이 있는 표)를 해시한 수를 센다."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.master_calls = 0
        original = sc.frame_digest

        def spy(frame: pd.DataFrame) -> str:
            if "설비명" in frame.columns and "Qual일정" in frame.columns:
                self.master_calls += 1
            return original(frame)

        monkeypatch.setattr(sc, "frame_digest", spy)


def test_a_given_digest_equal_to_the_frame_digest_keeps_every_key() -> None:
    baseline, equipment, downtime = _frames()
    digest = sc.frame_digest(equipment)
    manual = ManualDowntime()
    assert sc.equipment_span_cache_key(
        equipment=equipment, downtime=downtime, start_date=ANCHOR, end_date=date(2027, 3, 31)
    ) == sc.equipment_span_cache_key(
        equipment=equipment,
        downtime=downtime,
        start_date=ANCHOR,
        end_date=date(2027, 3, 31),
        equipment_digest=digest,
    )
    assert sc.space_status_cache_key(equipment, downtime, as_of=ANCHOR) == (
        sc.space_status_cache_key(equipment, downtime, as_of=ANCHOR, equipment_digest=digest)
    )
    cutoff = pd.DataFrame({"공정": ["A"], "Cut-off": [0]})
    shortening = {
        "equipment": equipment,
        "downtime": downtime,
        "baseline": baseline,
        "cutoff": cutoff,
        "months": (202610, 202611),
        "today": ANCHOR,
        "manual_downtime": manual,
    }
    scenario_key = ("ref", "token", 202610, 202611, "order")
    assert sc.required_shortening_cache_key(scenario_key, **shortening) == (  # type: ignore[arg-type]
        sc.required_shortening_cache_key(
            scenario_key,  # type: ignore[arg-type]
            **shortening,  # type: ignore[arg-type]
            equipment_digest=digest,
        )
    )
    timeline = {
        "equipment": equipment,
        "downtime": downtime,
        "baseline": baseline,
        "cutoff": cutoff,
        "months": (202610, 202611),
        "process": "A",
        "manual_downtime": manual,
    }
    assert sc.process_equipment_timeline_cache_key(**timeline) == (  # type: ignore[arg-type]
        sc.process_equipment_timeline_cache_key(**timeline, equipment_digest=digest)  # type: ignore[arg-type]
    )


def test_a_given_digest_is_the_master_slot_of_each_key() -> None:
    _, equipment, downtime = _frames()
    span = sc.equipment_span_cache_key(
        equipment=equipment,
        downtime=downtime,
        start_date=ANCHOR,
        end_date=ANCHOR,
        equipment_digest="given",
    )
    assert span[0] == "given"
    assert span[1] == sc.frame_digest(downtime)
    status = sc.space_status_cache_key(equipment, downtime, as_of=ANCHOR, equipment_digest="given")
    assert status == ("given", sc.frame_digest(downtime), ANCHOR.isoformat())


def test_wrappers_do_not_hash_the_master_again_when_a_digest_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline, equipment, downtime = _frames()
    digest = sc.frame_digest(equipment)
    spy = _DigestSpy(monkeypatch)
    window = {"start_date": ANCHOR, "end_date": date(2026, 12, 31)}
    sc.get_undated_equipment(equipment, equipment_digest=digest)
    sc.get_usage_excluded_equipment(equipment, equipment_digest=digest)
    sc.get_weekly_equipment_availability(
        baseline, equipment, downtime, **window, equipment_digest=digest
    )
    sc.get_schedule_confirmation_issues(equipment, today=ANCHOR, equipment_digest=digest)
    sc.get_space_equipment_status(equipment, downtime, as_of=ANCHOR, equipment_digest=digest)
    assert spy.master_calls == 0
    # 넘기지 않으면 지금처럼 마스터를 해시한다(한 함수에 한 번).
    sc.get_undated_equipment(equipment)
    assert spy.master_calls == 1


def test_wrappers_return_the_direct_values_with_or_without_a_digest() -> None:
    baseline, equipment, downtime = _frames()
    digest = sc.frame_digest(equipment)
    window = {"start_date": ANCHOR, "end_date": date(2026, 12, 31)}
    for given in (None, digest):
        pd.testing.assert_frame_equal(
            sc.get_undated_equipment(equipment, equipment_digest=given),
            undated_equipment(equipment),
        )
        pd.testing.assert_frame_equal(
            sc.get_usage_excluded_equipment(equipment, equipment_digest=given),
            usage_excluded_equipment(equipment),
        )
        pd.testing.assert_frame_equal(
            sc.get_weekly_equipment_availability(
                baseline, equipment, downtime, **window, equipment_digest=given
            ),
            build_weekly_equipment_availability(baseline, equipment, downtime, **window),
        )
        pd.testing.assert_frame_equal(
            sc.get_schedule_confirmation_issues(equipment, today=ANCHOR, equipment_digest=given),
            schedule_confirmation_issues(equipment, today=ANCHOR),
        )
        pd.testing.assert_frame_equal(
            sc.get_space_equipment_status(
                equipment, downtime, as_of=ANCHOR, equipment_digest=given
            ),
            build_space_equipment_status(equipment, downtime, as_of=ANCHOR),
        )


def test_a_digest_and_no_digest_share_one_cache_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    _, equipment, _ = _frames()
    calls: list[int] = []

    def counted(frame: pd.DataFrame) -> pd.DataFrame:
        calls.append(len(frame))
        return undated_equipment(frame)

    monkeypatch.setattr(sc, "undated_equipment", counted)
    sc.get_undated_equipment(equipment)
    sc.get_undated_equipment(equipment, equipment_digest=sc.frame_digest(equipment))
    assert len(calls) == 1
    # 다른 내용은 다른 칸이다.
    sc.get_undated_equipment(equipment.iloc[:3])
    assert len(calls) == 2


def _volume_inputs() -> dict[str, pd.DataFrame]:
    return {
        "plan": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "양산구분": ["양산"],
                "제품정보": ["HBM라"],
                "Stack": ["12H"],
                "생산수량": [100.0],
            }
        ),
        "yield_data": pd.DataFrame(
            {
                "생산계획년월": [202608, 202608],
                "제품정보": ["HBM라", "HBM라"],
                "Stack": ["12H", "12H"],
                "WF 구분": ["Core", "Dummy"],
                "EDS_수율": [0.8, 0.8],
                "BE_수율": [0.9, 0.9],
            }
        ),
        "chip_qty": pd.DataFrame(
            {
                "제품정보": ["HBM라", "HBM라"],
                "Stack": ["12H", "12H"],
                "WF 구분": ["Core", "Dummy"],
                "구분_Chip": [11, 1],
                "Net Die": [500, 500],
            }
        ),
        "density_data": pd.DataFrame(),
        "display_order": pd.DataFrame(columns=list(DISPLAY_ORDER_COLUMNS)),
    }


def test_the_keyed_monthly_volume_is_the_monthly_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = _volume_inputs()
    for basis in ("PKG", "Chip", "Wafer"):
        for detailed in (False, True):
            pd.testing.assert_frame_equal(
                sc.get_monthly_volume_by_key(
                    ("scenario", basis),
                    inputs["plan"],
                    inputs["yield_data"],
                    inputs["chip_qty"],
                    inputs["density_data"],
                    inputs["display_order"],
                    basis,
                    detailed,
                ),
                sc.get_monthly_volume(
                    plan=inputs["plan"],
                    yield_data=inputs["yield_data"],
                    chip_qty=inputs["chip_qty"],
                    demand_basis=basis,
                    detailed=detailed,
                    density_data=inputs["density_data"],
                    display_order=inputs["display_order"],
                ),
            )
    calls: list[str] = []

    def counted(**kwargs: object) -> pd.DataFrame:
        calls.append(str(kwargs["demand_basis"]))
        return build_monthly_volume(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sc, "build_monthly_volume", counted)
    st.cache_data.clear()
    args = (
        inputs["plan"],
        inputs["yield_data"],
        inputs["chip_qty"],
        inputs["density_data"],
        inputs["display_order"],
    )
    sc.get_monthly_volume_by_key(("k",), *args, "PKG", False)
    # 같은 키는 다른 표를 받아도 적중한다 — 키가 내용을 대신한다(해시하지 않는다).
    sc.get_monthly_volume_by_key(("k",), inputs["plan"].iloc[0:0], *args[1:], "PKG", False)
    assert calls == ["PKG"]
    sc.get_monthly_volume_by_key(("k",), *args, "Chip", False)
    sc.get_monthly_volume_by_key(("k2",), *args, "PKG", False)
    assert calls == ["PKG", "Chip", "PKG"]
