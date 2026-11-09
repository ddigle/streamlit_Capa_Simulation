# Purpose: Admin Area 「알림 모음」 — 활성 시나리오의 계산 알림을 전체 기간으로 한곳에 모은다.

"""Admin Area 「알림 모음」 탭.

HOME 위에 줄줄이 달리던 경고를 HOME 에서 걷고 여기 모은다(2026-10-19 사용자 요청 — 경고가 HOME 에
주렁주렁 달려 읽히지 않았다). 리비전 저장·공식 발행 검사와 같은 **시나리오 전체 기간** 계산
(`simulation_cache.get_full_capacity_outcome` — 같은 캐시)을 읽으므로 문장도 그 검사와 같다. 알림은
셋이다.

- **계산 멈춤** — 어느 달이든 기준정보 오류가 있으면 조회기간과 상관없이 계산 화면이 멈춘다. Capa
  계산이 지나면 HOME 의 Density 환산도 본다(`capacity_gate.density_error`).
- **소요대수에 들지 않은 수요** — `required_exclusion_message`. 문장 끝의 목록 자리 말은 뺀다 —
  칸 글은 값이고 길 안내는 Guide 「알림 모음」 이 맡는다(설계 규칙 UI-TXT-04).
- **측정률 가정** — 측정률 행이 없어 중립값 1.0 으로 계산한 경로(`assumption_message`).

계산이 멈추면 뒤의 둘은 셀 수 없다고 적는다. 탭이 열린 회차에만 그린다(`app_pages/admin_area.py`) —
처음 여는 회차는 전체 기간 계산 한 번(캐시가 빗나갈 때)이 든다.

알림 수(오류 · 경고 칸 수)는 탭 안 머리 줄이 아니라 탭 이름 「알림 모음」 곁 수 표지다(2026-11-09
사용자 보드 T7 — `tab_marks.mark_tab_counts`, 0 이면 없음). 칸마다 「없음」 이 서므로 빈 결과 줄도
따로 두지 않는다(설계 규칙 UI-TXT-07). 수는 탭을 연 회차에 그 계산 키(기준정보 버전 · 내용 토큰)와
함께 적어 두고, 닫힌 회차에는 지금 시나리오가 같은 키일 때만 다시 쓴다(`remembered_alert_count` —
닫힌 탭에서 전체 기간 계산을 돌리지 않는다, 설계 규칙 UI-DAT-11).
"""

from __future__ import annotations

from typing import Literal, NamedTuple

import streamlit as st

from capa_simulation.components.capacity_assumption_notice import assumption_message
from capa_simulation.components.capacity_gate import density_error
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.literal_markdown import markdown_safe_tildes
from capa_simulation.components.required_exclusion_notice import (
    FULL_SCOPE,
    required_exclusion_message,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    load_page_context,
)
from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY
from capa_simulation.services.required_equipment import required_exclusion_counts
from capa_simulation.services.simulation_cache import CapacityOutcome, get_full_capacity_outcome
from capa_simulation.services.unit_capacity import capacity_assumptions

AlertLevel = Literal["error", "warning", "ok", "unknown"]
_STOPPED_NOTE = "계산이 멈춰 셀 수 없음"
# 탭 이름 곁 수 표지의 재료 — (계산 키, 오류 · 경고 칸 수, 오류가 있는가). 탭을 연 회차에 적는다.
ALERT_COUNT_KEY = "admin_alert_board_count"


class AlertCount(NamedTuple):
    """알림 수 — 오류 · 경고 칸 수와 그 가운데 오류(계산 멈춤)가 있는가."""

    count: int
    error: bool


class Alert(NamedTuple):
    """알림 한 칸. `ok` 는 「없음」, `unknown` 은 앞 단계가 멈춰 셀 수 없는 칸이다."""

    title: str
    level: AlertLevel
    message: str


def collect_alerts(outcome: CapacityOutcome, density: str | None) -> list[Alert]:
    """전체 기간 계산 결과와 Density 환산 오류로 알림 셋을 늘 같은 차례로 낸다.

    없는 알림도 칸은 둔다 — 「없음」 이 보여야 그 알림을 확인했다는 것을 안다. 계산 멈춤 글은
    계산의 `ValueError` 원문이라 걸린 칸의 제품·공정 이름을 날로 담는다 — 알림 상자(마크다운)로
    가므로 물결표를 막는다(저장·발행 검사 `capacity_gate` 와 같다).
    """
    stopped = outcome.error or density
    if stopped is not None:
        return [
            Alert(
                "계산 멈춤",
                "error",
                f"{markdown_safe_tildes(stopped)} — 조회기간과 상관없이 계산 화면이 멈춥니다. "
                "`기준 정보` 화면은 열리므로 그 달을 고쳐 새 리비전으로 저장하면 풀립니다.",
            ),
            Alert("소요대수에 들지 않은 수요", "unknown", _STOPPED_NOTE),
            Alert("측정률 가정", "unknown", _STOPPED_NOTE),
        ]
    assert outcome.required_equipment is not None and outcome.unit_capacity is not None
    demand = required_exclusion_message(
        required_exclusion_counts(outcome.required_equipment), scope=FULL_SCOPE, list_note=""
    )
    assumed = capacity_assumptions(outcome.unit_capacity)
    assumption = assumption_message(assumed.counts, assumed.months)
    return [
        Alert("계산 멈춤", "ok", "없음"),
        Alert("소요대수에 들지 않은 수요", "warning" if demand else "ok", demand or "없음"),
        Alert("측정률 가정", "warning" if assumption else "ok", assumption or "없음"),
    ]


def render_alert_board() -> None:
    """활성 시나리오의 알림 셋. 준비 단계에서 멈추면(활성 시나리오 없음 등) 그 까닭만 남긴다.

    무엇을 어느 범위로 모으는지(시나리오 전체 기간 · 리비전 저장 · 공식 발행 검사와 같은 셈)는 Guide
    「알림 모음」 이 말한다 — 탭 머리에 설명 문장을 늘 띄우지 않는다(설계 규칙 UI-TXT-01)."""
    try:
        context = load_page_context()
        scenario = context.active_scenario
        outcome = get_full_capacity_outcome(
            (context.reference_version, str(scenario["content_token"])),
            _scenario_tables=scenario["tables"],
            _reference_tables=context.reference_tables,
        )
    except BOOTSTRAP_ERRORS as exc:
        render_data_error(
            bootstrap_error_message(exc), code="AD-07", text="알림 모음을 계산하지 못했습니다"
        )
        return
    density = density_error(scenario["tables"]) if outcome.error is None else None
    alerts = collect_alerts(outcome, density)
    st.session_state[ALERT_COUNT_KEY] = (
        (context.reference_version, str(scenario["content_token"])),
        AlertCount(
            sum(alert.level in ("error", "warning") for alert in alerts),
            any(alert.level == "error" for alert in alerts),
        ),
    )
    for alert in alerts:
        with st.container(border=True):
            st.markdown(f"**{alert.title}**")
            if alert.level == "error":
                st.error(alert.message, icon=":material/block:")
            elif alert.level == "warning":
                st.warning(alert.message, icon=":material/warning:")
            else:
                st.caption(alert.message)


def remembered_alert_count() -> AlertCount | None:
    """탭을 연 회차에 적어 둔 알림 수 — 지금 활성 시나리오가 그때와 같은 계산 키(기준정보 버전 ·
    내용 토큰)일 때만. 모르면 None(표지 없음). 닫힌 탭에서 전체 기간 계산을 돌리지 않는다."""
    stored = st.session_state.get(ALERT_COUNT_KEY)
    active = st.session_state.get(ACTIVE_SCENARIO_KEY)
    if not isinstance(stored, tuple) or not isinstance(active, dict):
        return None
    key, count = stored
    current = (active.get("reference_version"), str(active.get("content_token")))
    return count if key == current and isinstance(count, AlertCount) else None
