"""Session-only scenario selector demo with no repository or calculation effects."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

ACTIVE_SCENARIO_KEY = "scenario_selector_demo_active_scenario_id"
ACTIVE_REVISION_KEY = "scenario_selector_demo_active_revision_id"
CANDIDATE_SCENARIO_KEY = "scenario_selector_demo_candidate_scenario_id"
CANDIDATE_REVISION_KEY = "scenario_selector_demo_candidate_revision_id"
FLASH_KEY = "scenario_selector_demo_flash"


@dataclass(frozen=True)
class DemoRevision:
    revision_id: str
    revision_no: int
    revision_name: str
    saved_at: str


@dataclass(frozen=True)
class DemoScenario:
    scenario_id: str
    scenario_name: str
    simulation_code: str
    revisions: tuple[DemoRevision, ...]


DEMO_SCENARIOS = (
    DemoScenario(
        scenario_id="demo-operations",
        scenario_name="운영 기준안",
        simulation_code="SIM-1024",
        revisions=(
            DemoRevision("demo-operations-r3", 3, "효율 보정", "2026-08-27"),
            DemoRevision("demo-operations-r2", 2, "생산계획 변경", "2026-08-25"),
            DemoRevision("demo-operations-r1", 1, "초기 리비전", "2026-08-20"),
        ),
    ),
    DemoScenario(
        scenario_id="demo-expansion",
        scenario_name="증설 검토안",
        simulation_code="SIM-1024",
        revisions=(
            DemoRevision("demo-expansion-r2", 2, "설비 증설 반영", "2026-08-26"),
            DemoRevision("demo-expansion-r1", 1, "초기 리비전", "2026-08-22"),
        ),
    ),
    DemoScenario(
        scenario_id="demo-new-product",
        scenario_name="신규 제품 반영",
        simulation_code="SIM-1050",
        revisions=(DemoRevision("demo-new-product-r1", 1, "초기 리비전", "2026-08-24"),),
    ),
)

_SCENARIO_BY_ID = {scenario.scenario_id: scenario for scenario in DEMO_SCENARIOS}


def render_scenario_selector_demo() -> None:
    """Render a working selector whose state is intentionally disconnected from data."""
    _initialize_demo_state()
    active_scenario = _scenario(st.session_state[ACTIVE_SCENARIO_KEY])
    active_revision = _revision(active_scenario, st.session_state[ACTIVE_REVISION_KEY])

    with st.sidebar.container(border=True):
        st.markdown("#### :material/science: 활성 시나리오")
        st.caption("인터페이스 데모 · DB/RQ/계산 미연결")
        st.markdown(f"**{active_scenario.scenario_name}** · `{active_scenario.simulation_code}`")
        st.caption(f"r{active_revision.revision_no} · {active_revision.revision_name}")

        flash = st.session_state.pop(FLASH_KEY, None)
        if isinstance(flash, str):
            st.success(flash)

        candidate_scenario_id = st.selectbox(
            "시나리오",
            options=[scenario.scenario_id for scenario in DEMO_SCENARIOS],
            format_func=_scenario_label,
            key=CANDIDATE_SCENARIO_KEY,
            on_change=_reset_candidate_revision,
            persist_state="session",
        )
        candidate_scenario = _scenario(candidate_scenario_id)
        candidate_revision_id = st.selectbox(
            "리비전",
            options=[revision.revision_id for revision in candidate_scenario.revisions],
            format_func=lambda revision_id: _revision_label(
                candidate_scenario,
                revision_id,
            ),
            key=CANDIDATE_REVISION_KEY,
            persist_state="session",
        )
        unchanged = (
            candidate_scenario_id == active_scenario.scenario_id
            and candidate_revision_id == active_revision.revision_id
        )
        if st.button(
            "선택한 리비전 불러오기",
            icon=":material/download:",
            type="primary",
            width="stretch",
            disabled=unchanged,
            key="scenario_selector_demo_apply",
        ):
            selected_revision = _revision(candidate_scenario, candidate_revision_id)
            st.session_state[ACTIVE_SCENARIO_KEY] = candidate_scenario_id
            st.session_state[ACTIVE_REVISION_KEY] = candidate_revision_id
            st.session_state[FLASH_KEY] = (
                f"{candidate_scenario.scenario_name} r{selected_revision.revision_no} 선택 완료"
            )
            st.rerun()


def _initialize_demo_state() -> None:
    default_scenario = DEMO_SCENARIOS[0]
    active_scenario_id = st.session_state.get(ACTIVE_SCENARIO_KEY)
    if not isinstance(active_scenario_id, str) or active_scenario_id not in _SCENARIO_BY_ID:
        active_scenario_id = default_scenario.scenario_id
        st.session_state[ACTIVE_SCENARIO_KEY] = active_scenario_id
    active_scenario = _scenario(active_scenario_id)
    active_revision_id = st.session_state.get(ACTIVE_REVISION_KEY)
    if not _has_revision(active_scenario, active_revision_id):
        st.session_state[ACTIVE_REVISION_KEY] = active_scenario.revisions[0].revision_id

    candidate_scenario_id = st.session_state.get(CANDIDATE_SCENARIO_KEY)
    if not isinstance(candidate_scenario_id, str) or candidate_scenario_id not in _SCENARIO_BY_ID:
        candidate_scenario_id = active_scenario_id
        st.session_state[CANDIDATE_SCENARIO_KEY] = candidate_scenario_id
    candidate_scenario = _scenario(candidate_scenario_id)
    candidate_revision_id = st.session_state.get(CANDIDATE_REVISION_KEY)
    if not _has_revision(candidate_scenario, candidate_revision_id):
        st.session_state[CANDIDATE_REVISION_KEY] = candidate_scenario.revisions[0].revision_id


def _reset_candidate_revision() -> None:
    scenario_id = st.session_state.get(CANDIDATE_SCENARIO_KEY)
    scenario = _SCENARIO_BY_ID.get(scenario_id) if isinstance(scenario_id, str) else None
    if scenario is not None:
        st.session_state[CANDIDATE_REVISION_KEY] = scenario.revisions[0].revision_id


def _scenario(scenario_id: object) -> DemoScenario:
    if not isinstance(scenario_id, str) or scenario_id not in _SCENARIO_BY_ID:
        raise ValueError("시나리오 선택 데모 상태가 올바르지 않습니다.")
    return _SCENARIO_BY_ID[scenario_id]


def _revision(scenario: DemoScenario, revision_id: object) -> DemoRevision:
    if isinstance(revision_id, str):
        for revision in scenario.revisions:
            if revision.revision_id == revision_id:
                return revision
    raise ValueError("리비전 선택 데모 상태가 올바르지 않습니다.")


def _has_revision(scenario: DemoScenario, revision_id: object) -> bool:
    return isinstance(revision_id, str) and any(
        revision.revision_id == revision_id for revision in scenario.revisions
    )


def _scenario_label(scenario_id: str) -> str:
    scenario = _scenario(scenario_id)
    return (
        f"{scenario.scenario_name} · {scenario.simulation_code} "
        f"· 최신 r{scenario.revisions[0].revision_no}"
    )


def _revision_label(scenario: DemoScenario, revision_id: str) -> str:
    revision = _revision(scenario, revision_id)
    return f"r{revision.revision_no} · {revision.revision_name} · {revision.saved_at}"
