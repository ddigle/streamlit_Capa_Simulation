# Purpose: Sidebar controls for loading and revising persisted scenarios.

"""Sidebar controls for loading and revising persisted scenarios."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components.scenario_management import revision_tables_for_save
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import (
    get_scenario_repository,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import ScenarioSummary
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import (
    activate_persisted_snapshot,
    active_persisted_revision_id,
    active_persisted_scenario_id,
    has_unsaved_scenario_changes,
)
from capa_simulation.scenario_preset_state import capture_scenario_preset
from capa_simulation.scenario_state import ensure_active_scenario
from capa_simulation.settings import DUCKDB_PATH

SIDEBAR_SCENARIO_KEY = "sidebar_scenario_id"
SIDEBAR_REVISION_KEY = "sidebar_revision_id"
SIDEBAR_SYNC_TOKEN_KEY = "sidebar_scenario_sync_token"
SIDEBAR_FLASH_KEY = "sidebar_scenario_flash"
# 사이드바 박스 CSS 훅. 여백을 좁히는 규칙이 `app.py` 에서 이 key 를 읽는다.
SCENARIO_BOX_KEY = "sidebar_scenario_box"


def render_scenario_controls(database_path: Path = DUCKDB_PATH) -> None:
    """Load a saved revision or persist the current edits from every page."""
    resolved_path = str(database_path.resolve())
    with st.sidebar.container(border=True, key=SCENARIO_BOX_KEY):
        # 제목 줄을 먼저 **자리만** 잡는다. 공식버전 배지는 아래에서 저장소를 읽어야
        # 알 수 있는데, 배지 한 칸 때문에 제목을 뒤로 미루면 저장소가 죽었을 때 오류
        # 문구 위에 제목이 없어진다.
        title_row = st.empty()
        _render_title_row(title_row, badge="")
        flash = st.session_state.pop(SIDEBAR_FLASH_KEY, None)
        if isinstance(flash, str):
            st.success(flash)

        try:
            repository = get_scenario_repository(resolved_path)
            scenarios = repository.list_scenarios()
            official = repository.latest_official_release()
        except BOOTSTRAP_ERRORS as exc:
            st.error(f"시나리오 저장소를 읽지 못했습니다: {bootstrap_error_message(exc)}")
            return

        if not scenarios:
            st.info("저장된 활성 시나리오가 없습니다.")
            st.caption("시나리오 관리 페이지에서 신규 시나리오를 등록하세요.")
            return

        scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
        active_scenario_id = active_persisted_scenario_id()
        active_revision_id = active_persisted_revision_id()
        _synchronize_active_selection(
            scenario_by_id,
            active_scenario_id=active_scenario_id,
            active_revision_id=active_revision_id,
        )

        # 칸 위 글자를 접는다. 박스 제목이 이미 `시나리오·리비전` 이라 두 선택 상자
        # 위에 같은 낱말을 한 번 더 적으면 세로만 먹고 새로 알려 주는 것이 없다.
        # `collapsed` 는 글자를 감출 뿐 접근성 이름은 남긴다.
        selected_scenario_id = st.selectbox(
            "시나리오",
            label_visibility="collapsed",
            options=list(scenario_by_id),
            format_func=lambda value: _scenario_label(scenario_by_id[value]),
            key=SIDEBAR_SCENARIO_KEY,
            persist_state="session",
        )
        revisions = repository.list_revisions(selected_scenario_id)
        revision_by_id = {revision.revision_id: revision for revision in revisions}
        if not revision_by_id:
            st.warning("선택한 시나리오에 저장된 리비전이 없습니다.")
            return

        _ensure_revision_selection(
            scenario_by_id[selected_scenario_id],
            revision_by_id,
            active_scenario_id=active_scenario_id,
            active_revision_id=active_revision_id,
        )
        selected_revision_id = st.selectbox(
            "리비전",
            label_visibility="collapsed",
            options=list(revision_by_id),
            format_func=lambda value: (
                f"r{revision_by_id[value].revision_no} · {revision_by_id[value].revision_name}"
            ),
            key=SIDEBAR_REVISION_KEY,
            persist_state="session",
        )

        selection_is_active = (
            selected_scenario_id == active_scenario_id
            and selected_revision_id == active_revision_id
        )
        # 배지는 선택 상자가 말하지 않는 것(공식 발행본인지)만 말한다. 그래서 본문에
        # 한 줄을 따로 쓰지 않고 **제목 옆**에 붙인다 — 한 줄이 통째로 줄어든다.
        if selection_is_active:
            _render_title_row(
                title_row,
                badge=_status_badge(
                    active_revision_id=active_revision_id,
                    official_revision_id=official.revision_id if official is not None else None,
                    official_release_no=official.release_no if official is not None else None,
                ),
            )
        else:
            st.caption("선택값은 아직 계산에 적용되지 않았습니다.")

        discard_changes = True
        if has_unsaved_scenario_changes():
            st.markdown(":orange-badge[저장하지 않은 변경 있음]")
            discard_changes = st.checkbox(
                "변경을 버리고 불러오기",
                key="sidebar_discard_unsaved_changes",
            )

        # 두 동작을 한 줄에 반씩 놓는다. 세로로 쌓으면 사이드바에서 두 줄을 먹는데,
        # 둘은 같은 층위의 동작이라 나란히 서는 것이 뜻에도 맞는다. 라벨을 짧게 줄인 것도
        # 반 폭에 들어가야 하기 때문이다 — 무엇을 불러오고 무엇을 저장하는지는 바로 위
        # 두 선택 상자가 말한다.
        load_column, save_column = st.columns(2, gap="small")
        with load_column:
            load_clicked = st.button(
                "불러오기",
                icon=":material/download:",
                type="primary",
                disabled=not discard_changes,
                width="stretch",
                key="sidebar_load_revision",
            )
        with save_column:
            _render_revision_save(
                repository,
                scenario_by_id,
                selected_scenario_id=selected_scenario_id,
                selected_revision_id=selected_revision_id,
                active_scenario_id=active_scenario_id,
                active_revision_id=active_revision_id,
            )
        if load_clicked:
            try:
                snapshot = load_scenario_snapshot(resolved_path, selected_revision_id)
                activate_persisted_snapshot(snapshot)
            except BOOTSTRAP_ERRORS as exc:
                st.error(f"리비전을 불러오지 못했습니다: {bootstrap_error_message(exc)}")
            else:
                st.session_state[SIDEBAR_FLASH_KEY] = (
                    f"{snapshot.scenario.scenario_name} "
                    f"r{snapshot.revision.revision_no}을 불러왔습니다."
                )
                st.rerun()
        if not selection_is_active:
            # 고른 것과 올라와 있는 것이 다를 때만 "지금 무엇이 올라와 있는지" 를 적는다.
            _render_active_status(
                scenario_by_id,
                active_scenario_id=active_scenario_id,
                active_revision_id=active_revision_id,
                official_revision_id=official.revision_id if official is not None else None,
                official_release_no=official.release_no if official is not None else None,
            )


def _render_title_row(slot: DeltaGenerator, *, badge: str) -> None:
    """상자 제목과 그 옆 공식버전 배지. 배지가 없으면 제목만 그린다.

    `st.empty()` 자리에 다시 그리는 것은 배지 값이 저장소를 읽은 **뒤에야** 정해지기
    때문이다. 제목을 그때까지 미루면 저장소가 죽었을 때 오류 문구 위에 제목이 없다.
    """
    with slot.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown("#### :material/database: 시나리오·리비전", width="content")
        if badge:
            st.markdown(badge, width="content")


def _render_revision_save(
    repository: DuckDBScenarioRepository,
    scenario_by_id: dict[str, ScenarioSummary],
    *,
    selected_scenario_id: str,
    selected_revision_id: str,
    active_scenario_id: str | None,
    active_revision_id: str | None,
) -> None:
    # `st.expander` 가 아니라 `st.popover` 다. expander 는 폭을 통째로 먹는 줄이라 옆
    # 버튼과 나란히 설 수 없고, 펴면 그 아래 조회기간 상자를 밀어낸다. popover 는 버튼
    # 모양으로 서고 내용은 띄워 올린다.
    with st.popover("저장", icon=":material/save_as:", width="stretch"):
        if active_scenario_id is None or active_revision_id is None:
            st.info("먼저 저장된 리비전을 불러오세요.")
            return
        if selected_scenario_id != active_scenario_id or selected_revision_id != active_revision_id:
            st.info("위에서 선택한 리비전을 먼저 불러온 뒤 저장하세요.")
            return

        active_summary = scenario_by_id.get(active_scenario_id)
        if active_summary is None:
            st.warning("현재 활성 시나리오 정보를 찾지 못했습니다.")
            return
        st.caption(f"저장 대상 · {active_summary.scenario_name}")
        with st.form("sidebar_revision_save_form", clear_on_submit=True):
            revision_name = st.text_input(
                "새 리비전명",
                placeholder="예: 공정 조건 변경안",
                key="sidebar_revision_name",
            )
            note = st.text_area(
                "변경 메모",
                height=80,
                key="sidebar_revision_note",
            )
            submitted = st.form_submit_button(
                "신규 리비전 저장",
                icon=":material/save_as:",
                width="stretch",
            )
        if not submitted:
            return

        try:
            reference_version = get_effective_reference_version()
            reference_tables = get_effective_reference_tables()
            active_scenario = ensure_active_scenario(reference_tables, reference_version)
            revision_tables = revision_tables_for_save(active_scenario, reference_tables)
            snapshot = repository.save_revision(
                active_scenario_id,
                revision_tables,
                capture_scenario_preset(
                    {**reference_tables, "RQ_REQB": revision_tables["RQ_REQB"]}
                ),
                revision_name=revision_name,
                parent_revision_id=active_revision_id,
                note=note.strip() or None,
            )
            activate_persisted_snapshot(snapshot)
        except BOOTSTRAP_ERRORS as exc:
            st.error(f"신규 리비전을 저장하지 못했습니다: {bootstrap_error_message(exc)}")
        else:
            st.session_state[SIDEBAR_FLASH_KEY] = (
                f"신규 리비전 r{snapshot.revision.revision_no}을 저장했습니다."
            )
            st.rerun()


def _status_badge(
    *,
    active_revision_id: str | None,
    official_revision_id: str | None,
    official_release_no: int | None,
) -> str:
    """활성 리비전의 상태 배지를 고른다.

    미저장 변경이 있으면 빈 문자열을 준다. 그 상태는 바로 아래 "변경을 버리고 불러오기"
    체크박스 위에서 이미 같은 배지로 알리고 있어서, 여기서 또 적으면 같은 문구가 한 상자
    안에 두 번 나온다.
    """
    if has_unsaved_scenario_changes():
        return ""
    if official_revision_id == active_revision_id and official_release_no is not None:
        return f":green-badge[공식 v{official_release_no}]"
    return ":gray-badge[저장된 리비전]"


def _render_active_status(
    scenario_by_id: dict[str, ScenarioSummary],
    *,
    active_scenario_id: str | None,
    active_revision_id: str | None,
    official_revision_id: str | None,
    official_release_no: int | None,
) -> None:
    if active_scenario_id is None or active_revision_id is None:
        st.warning("활성화된 시나리오·리비전이 없습니다.")
        return
    scenario = scenario_by_id.get(active_scenario_id)
    if scenario is None:
        st.warning("현재 활성 시나리오 정보를 조회하지 못했습니다.")
        return
    st.divider()
    st.caption(f"활성 · {scenario.scenario_name} · {scenario.source_simulation_code}")
    badge = _status_badge(
        active_revision_id=active_revision_id,
        official_revision_id=official_revision_id,
        official_release_no=official_release_no,
    )
    if badge:
        st.markdown(badge)


def _synchronize_active_selection(
    scenario_by_id: dict[str, ScenarioSummary],
    *,
    active_scenario_id: str | None,
    active_revision_id: str | None,
) -> None:
    active_token = (active_scenario_id, active_revision_id)
    previous_token = st.session_state.get(SIDEBAR_SYNC_TOKEN_KEY)
    if previous_token != active_token and active_scenario_id in scenario_by_id:
        st.session_state[SIDEBAR_SCENARIO_KEY] = active_scenario_id
        st.session_state[SIDEBAR_REVISION_KEY] = active_revision_id
    st.session_state[SIDEBAR_SYNC_TOKEN_KEY] = active_token

    selected = st.session_state.get(SIDEBAR_SCENARIO_KEY)
    if selected not in scenario_by_id:
        st.session_state[SIDEBAR_SCENARIO_KEY] = next(iter(scenario_by_id))


def _ensure_revision_selection(
    scenario: ScenarioSummary,
    revision_by_id: Mapping[str, object],
    *,
    active_scenario_id: str | None,
    active_revision_id: str | None,
) -> None:
    selected = st.session_state.get(SIDEBAR_REVISION_KEY)
    if selected in revision_by_id:
        return
    preferred = (
        active_revision_id
        if scenario.scenario_id == active_scenario_id
        else scenario.active_revision_id
    )
    st.session_state[SIDEBAR_REVISION_KEY] = (
        preferred if preferred in revision_by_id else next(iter(revision_by_id))
    )


def _scenario_label(summary: ScenarioSummary) -> str:
    return f"{summary.scenario_name} · {summary.source_simulation_code}"
