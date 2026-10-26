# Purpose: 「알림 모음」 이 계산 멈춤·소요대수 밖 수요·측정률 가정을 늘 같은 차례로 내는지 검사한다.

from __future__ import annotations

import pandas as pd

from capa_simulation.components.alert_board import collect_alerts
from capa_simulation.services.required_equipment import (
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    REQUIRED_LOAD_EXCLUSIONS_ATTR,
)
from capa_simulation.services.simulation_cache import CapacityOutcome
from capa_simulation.services.unit_capacity import (
    CAPACITY_ASSUMED_MONTHS_ATTR,
    CAPACITY_ASSUMPTIONS_ATTR,
)

TITLES = ["계산 멈춤", "소요대수에 들지 않은 수요", "측정률 가정"]


def _outcome(*, excluded_routes: int = 0, assumed: int = 0) -> CapacityOutcome:
    required = pd.DataFrame({"공정": ["DEMO_A"]})
    required.attrs[REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR] = pd.DataFrame(
        {"제외사유": ["대당 Capa 없음"] * excluded_routes, "부하량": [1.0] * excluded_routes}
    )
    required.attrs[REQUIRED_LOAD_EXCLUSIONS_ATTR] = pd.DataFrame({"누락 기준정보": []})
    unit = pd.DataFrame({"공정": ["DEMO_A"]})
    unit.attrs[CAPACITY_ASSUMPTIONS_ATTR] = {"RQ_LOT_RATIO": assumed} if assumed else {}
    unit.attrs[CAPACITY_ASSUMED_MONTHS_ATTR] = {"RQ_LOT_RATIO": (202610,)} if assumed else {}
    return CapacityOutcome(unit_capacity=unit, required_equipment=required, error=None)


def test_a_clean_scenario_still_lists_every_alert_as_none() -> None:
    """없는 알림도 칸은 둔다 — 「없음」 이 보여야 그 알림을 확인했다는 것을 안다."""
    alerts = collect_alerts(_outcome(), None)

    assert [alert.title for alert in alerts] == TITLES
    assert [alert.level for alert in alerts] == ["ok", "ok", "ok"]
    assert all(alert.message == "없음" for alert in alerts)


def test_uncounted_demand_and_assumptions_are_warnings_with_the_gate_sentences() -> None:
    """HOME 에서 걷은 두 경고는 저장·발행 검사와 같은 문장(시나리오 전체 기간)이다."""
    alerts = collect_alerts(_outcome(excluded_routes=2, assumed=3), None)

    assert [alert.level for alert in alerts] == ["ok", "warning", "warning"]
    assert alerts[1].message.startswith("소요대수에 들지 않은 수요가 있습니다")
    assert "시나리오 전체 기간" in alerts[1].message
    assert "대당 Capa 가 없어 뺀 부하 경로 2건" in alerts[1].message
    assert "Lot측정률 3건(2026-10)" in alerts[2].message


def test_a_stopped_calculation_leads_and_the_rest_cannot_be_counted() -> None:
    """어느 달이든 기준정보 오류가 있으면 계산이 멈춘다 — 뒤의 둘은 셀 수 없다고 적는다."""
    stopped = CapacityOutcome(unit_capacity=None, required_equipment=None, error="26.07 UPEH 없음")
    alerts = collect_alerts(stopped, None)

    assert [alert.title for alert in alerts] == TITLES
    assert [alert.level for alert in alerts] == ["error", "unknown", "unknown"]
    assert alerts[0].message.startswith("26.07 UPEH 없음 — 조회기간과 상관없이")


def test_a_density_error_after_a_clean_capacity_run_also_stops() -> None:
    """Capa 계산이 지나도 HOME Density 환산이 멈추면 계산 멈춤이다(저장·발행 검사와 같다)."""
    alerts = collect_alerts(_outcome(), "구분_EQ 0 이하")

    assert alerts[0].level == "error"
    assert alerts[0].message.startswith("구분_EQ 0 이하")


def test_a_stopped_calculation_blocks_the_tilde_of_the_name_it_carries() -> None:
    """계산 멈춤 글은 계산 오류 원문이라 걸린 칸의 이름을 날로 담는다 — 알림 상자에서 막는다."""
    stopped = CapacityOutcome(
        unit_capacity=None, required_equipment=None, error="26.07 「제품~가정~A」 UPEH 없음"
    )
    alerts = collect_alerts(stopped, None)

    assert alerts[0].message.startswith("26.07 「제품\\~가정\\~A」 UPEH 없음 — 조회기간과")
    assert collect_alerts(_outcome(), "「공정~표시~D」 구분_EQ 0 이하")[0].message.startswith(
        "「공정\\~표시\\~D」"
    )
