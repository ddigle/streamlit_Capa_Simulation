# Purpose: Admin Area 「알림 모음」 — 활성 시나리오의 계산 알림을 전체 기간으로 한곳에 모은다.

"""Admin Area 「알림 모음」 탭.

HOME 위에 줄줄이 달리던 경고를 HOME 에서 걷고 여기 모은다(2026-10-19 사용자 요청 — 경고가 HOME 에
주렁주렁 달려 읽히지 않았다). 리비전 저장·공식 발행 검사와 같은 **시나리오 전체 기간** 계산
(`simulation_cache.get_full_capacity_outcome` — 같은 캐시)을 읽으므로 문장도 그 검사와 같다. 알림은
셋이다.

- **계산 멈춤** — 어느 달이든 기준정보 오류가 있으면 조회기간과 상관없이 계산 화면이 멈춘다. Capa
  계산이 지나면 HOME 의 Density 환산도 본다(`capacity_gate.density_error`).
- **소요대수에 들지 않은 수요** — `required_exclusion_message`. 목록은 산출 결과 → 소요대수 탭이다.
- **측정률 가정** — 측정률 행이 없어 중립값 1.0 으로 계산한 경로(`assumption_message`).

계산이 멈추면 뒤의 둘은 셀 수 없다고 적는다. 탭이 열린 회차에만 그린다(`app_pages/admin_area.py`) —
처음 여는 회차는 전체 기간 계산 한 번(캐시가 빗나갈 때)이 든다.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

import streamlit as st

from capa_simulation.components.capacity_assumption_notice import assumption_message
from capa_simulation.components.capacity_gate import density_error
from capa_simulation.components.page_link import render_page_link
from capa_simulation.components.required_exclusion_notice import (
    FULL_SCOPE,
    required_exclusion_message,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    load_page_context,
)
from capa_simulation.services.required_equipment import required_exclusion_counts
from capa_simulation.services.simulation_cache import CapacityOutcome, get_full_capacity_outcome
from capa_simulation.services.unit_capacity import capacity_assumptions

AlertLevel = Literal["error", "warning", "ok", "unknown"]
CALCULATION_RESULT_PAGE = "app_pages/calculation_result.py"
_STOPPED_NOTE = "계산이 멈춰 셀 수 없습니다 — 위 「계산 멈춤」을 먼저 고칩니다."


class Alert(NamedTuple):
    """알림 한 칸. `ok` 는 「없음」, `unknown` 은 앞 단계가 멈춰 셀 수 없는 칸이다."""

    title: str
    level: AlertLevel
    message: str


def collect_alerts(outcome: CapacityOutcome, density: str | None) -> list[Alert]:
    """전체 기간 계산 결과와 Density 환산 오류로 알림 셋을 늘 같은 차례로 낸다.

    없는 알림도 칸은 둔다 — 「없음」 이 보여야 그 알림을 확인했다는 것을 안다.
    """
    stopped = outcome.error or density
    if stopped is not None:
        return [
            Alert(
                "계산 멈춤",
                "error",
                f"{stopped} — 조회기간과 상관없이 계산 화면이 멈춥니다. `기준 정보` 화면은 "
                "열리므로 그 달을 고쳐 새 리비전으로 저장하면 풀립니다.",
            ),
            Alert("소요대수에 들지 않은 수요", "unknown", _STOPPED_NOTE),
            Alert("측정률 가정", "unknown", _STOPPED_NOTE),
        ]
    assert outcome.required_equipment is not None and outcome.unit_capacity is not None
    demand = required_exclusion_message(
        required_exclusion_counts(outcome.required_equipment), scope=FULL_SCOPE
    )
    assumed = capacity_assumptions(outcome.unit_capacity)
    assumption = assumption_message(assumed.counts, assumed.months)
    return [
        Alert("계산 멈춤", "ok", "없음"),
        Alert("소요대수에 들지 않은 수요", "warning" if demand else "ok", demand or "없음"),
        Alert("측정률 가정", "warning" if assumption else "ok", assumption or "없음"),
    ]


def render_alert_board() -> None:
    """활성 시나리오의 알림 셋. 준비 단계에서 멈추면(활성 시나리오 없음 등) 그 까닭만 남긴다."""
    st.caption(
        "활성 시나리오의 계산 알림을 시나리오 전체 기간으로 모읍니다 — HOME 에는 띄우지 "
        "않습니다. 리비전 저장·공식 발행 검사와 같은 셈입니다."
    )
    try:
        context = load_page_context()
        scenario = context.active_scenario
        outcome = get_full_capacity_outcome(
            (context.reference_version, str(scenario["content_token"])),
            _scenario_tables=scenario["tables"],
            _reference_tables=context.reference_tables,
        )
    except BOOTSTRAP_ERRORS as exc:
        st.info(bootstrap_error_message(exc))
        return
    density = density_error(scenario["tables"]) if outcome.error is None else None
    alerts = collect_alerts(outcome, density)
    open_count = sum(alert.level in ("error", "warning") for alert in alerts)
    if open_count:
        st.markdown(f"**알림 {open_count}건**")
    else:
        st.success("알림이 없습니다.", icon=":material/check_circle:")
    for alert in alerts:
        with st.container(border=True):
            st.markdown(f"**{alert.title}**")
            if alert.level == "error":
                st.error(alert.message, icon=":material/block:")
            elif alert.level == "warning":
                st.warning(alert.message, icon=":material/warning:")
            else:
                st.caption(alert.message)
    render_page_link(
        CALCULATION_RESULT_PAGE,
        label="산출 결과 — 계산에서 뺀 목록·CSV",
        icon=":material/monitoring:",
    )
