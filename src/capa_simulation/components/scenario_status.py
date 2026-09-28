# Purpose: Sidebar controls for loading and revising persisted scenarios.

"""Sidebar controls for loading and revising persisted scenarios."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components.capacity_gate import revision_save_verdict
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
from capa_simulation.persistence.models import RevisionSummary, ScenarioSummary
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
from capa_simulation.sidebar_status import sidebar_expander

SIDEBAR_SCENARIO_KEY = "sidebar_scenario_id"
SIDEBAR_REVISION_KEY = "sidebar_revision_id"
SIDEBAR_SYNC_TOKEN_KEY = "sidebar_scenario_sync_token"
SIDEBAR_FLASH_KEY = "sidebar_scenario_flash"
# 성공 알림과 함께 띄울 경고. 저장은 됐지만 남은 계산 오류가 있을 때 쓴다.
SIDEBAR_FLASH_WARNING_KEY = "sidebar_scenario_flash_warning"
# 사이드바 박스 key 이자 CSS 훅. 확장 패널의 펼침 상태도 이 key 로 오간다.
SCENARIO_BOX_KEY = "sidebar_scenario_box"
SCENARIO_BOX_TITLE = "시나리오·리비전"
# `시나리오 관리` 페이지가 `:material/database:` 를 쓴다. 사이드바에 같은 아이콘이 둘
# 나란히 서면 어느 것이 페이지이고 어느 것이 컨트롤인지 갈리지 않는다. `database` 는
# 저장소(관리 페이지)를 뜻하고, 여기는 **지금 보고 있는 한 겹**이라 `layers` 다.
SCENARIO_BOX_ICON = ":material/layers:"


def render_scenario_controls(database_path: Path = DUCKDB_PATH) -> None:
    """Load a saved revision or persist the current edits from every page."""
    resolved_path = str(database_path.resolve())
    # 플래시는 상자를 세우기 **전에** 꺼낸다. 저장소를 못 읽는 회차에도 한 번 보여 주고
    # 지워야 다음 rerun 까지 남지 않는다.
    flash = st.session_state.pop(SIDEBAR_FLASH_KEY, None)
    active_scenario_id = active_persisted_scenario_id()
    active_revision_id = active_persisted_revision_id()

    try:
        repository = get_scenario_repository(resolved_path)
        scenarios = repository.list_scenarios()
        official = repository.latest_official_release()
    except BOOTSTRAP_ERRORS as exc:
        # 접힌 줄의 배지는 저장소를 읽어야 정해진다. 못 읽으면 배지 없이 제목만 세우고
        # 원인은 상자 안에서 말한다 — 상자까지 사라지면 다시 펴 볼 자리도 없어진다.
        with _scenario_box(badge=""):
            _show_flash(flash)
            st.error(f"시나리오 저장소를 읽지 못했습니다: {bootstrap_error_message(exc)}")
        return

    with _scenario_box(
        badge=_summary_badge(
            active_revision_id=active_revision_id,
            official_revision_id=official.revision_id if official is not None else None,
            official_release_no=official.release_no if official is not None else None,
        )
    ):
        _show_flash(flash)

        if not scenarios:
            st.info("저장된 활성 시나리오가 없습니다.")
            st.caption("시나리오 관리 페이지에서 신규 시나리오를 등록하세요.")
            return

        scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
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
            st.info("선택한 시나리오에 저장된 리비전이 없습니다.")
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
        # 배지는 선택 상자가 말하지 않는 것(공식 발행본인지·미저장인지)만 말한다. 그 자리는
        # 이제 **요약 줄**이다 — 상자를 접어도 지금 무엇이 올라와 있는지가 남아야 한다.
        if not selection_is_active:
            st.caption("선택값은 아직 계산에 적용되지 않았습니다.")

        discard_changes = True
        if has_unsaved_scenario_changes():
            # 같은 배지를 요약 줄이 이미 달고 있다. 본문에 한 번 더 적으면 한 상자 안에
            # 같은 문구가 두 번 나온다.
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
                revision_by_id,
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


def _show_flash(flash: object) -> None:
    if isinstance(flash, str):
        st.success(flash)
    warning = st.session_state.pop(SIDEBAR_FLASH_WARNING_KEY, None)
    if isinstance(warning, str):
        st.warning(warning, icon=":material/warning:")


def _scenario_box(*, badge: str) -> DeltaGenerator:
    """접히는 시나리오 상자. 요약 줄에는 제목과 상태 배지 하나만 남는다.

    확장 패널의 제목은 **문자열 하나**라 `st.empty()` 자리에 나중에 다시 그릴 수 없다.
    그래서 배지는 상자를 세우기 전에 저장소를 읽어 정한다. 오른쪽 끝으로 미는 것은
    `components/sidebar_style.py` 의 CSS 다 — 라벨 안에서는 좌우로 밀 수 없다.
    """
    label = f"{SCENARIO_BOX_TITLE} {badge}" if badge else SCENARIO_BOX_TITLE
    return sidebar_expander(label, key=SCENARIO_BOX_KEY, icon=SCENARIO_BOX_ICON)


def _summary_badge(
    *,
    active_revision_id: str | None,
    official_revision_id: str | None,
    official_release_no: int | None,
) -> str:
    """요약 줄에 다는 배지. 접힌 줄이 말할 수 있는 것은 이 한 조각뿐이다.

    미저장 변경은 본문이 아니라 여기서 알린다. 접힌 상태에서는 본문의 주황 배지가 보이지
    않아, 저장하지 않은 편집을 안은 채로 다른 화면을 도는 일이 생긴다.
    """
    if has_unsaved_scenario_changes():
        return ":orange-badge[미저장 변경]"
    return _status_badge(
        active_revision_id=active_revision_id,
        official_revision_id=official_revision_id,
        official_release_no=official_release_no,
    )


def _render_revision_save(
    repository: DuckDBScenarioRepository,
    scenario_by_id: dict[str, ScenarioSummary],
    revision_by_id: dict[str, RevisionSummary],
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
            # 여기서 「불러오기」를 권하면 안 된다. 저장하려던 편집이 바로 그 불러오기에
            # 덮여 사라진다. 저장 대상이 무엇이고 무엇을 되돌리면 되는지만 말한다.
            active_summary = scenario_by_id.get(active_scenario_id)
            target_name = (
                active_summary.scenario_name if active_summary is not None else "활성 시나리오"
            )
            # 시나리오는 그대로고 리비전만 다르게 고른 흔한 경우, 이름만 적으면 지금 고른
            # 것과 글자가 같아 어디로 되돌려야 하는지 알 수 없다. 그 경우에만 번호를 짚어
            # 준다 — `revision_by_id` 는 고른 시나리오의 목록이라 그때만 활성본을 갖는다.
            active_revision = revision_by_id.get(active_revision_id)
            target = (
                f"「{target_name}」 r{active_revision.revision_no}"
                if active_revision is not None
                else f"「{target_name}」"
            )
            warning = (
                "「불러오기」를 누르면 저장하지 않은 편집이 사라집니다. "
                if has_unsaved_scenario_changes()
                else ""
            )
            st.info(
                f"저장 대상은 지금 계산에 올라와 있는 {target} 리비전입니다. "
                f"{warning}"
                "위 선택 상자를 그 시나리오·리비전으로 되돌리면 저장할 수 있습니다."
            )
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
            # `REVISION_TABLES` 14개를 통째로 새 리비전으로 적는다(표시순서·모듈수는
            # 시나리오에 종속되지 않는 공용 프로필이라 빠진다). 표가 크면 몇 초가 걸리고
            # 그동안 popover 는 아무 반응이 없어 두 번 누르게 된다.
            with st.spinner("현재 편집본을 새 리비전으로 저장하는 중입니다..."):
                reference_version = get_effective_reference_version()
                reference_tables = get_effective_reference_tables()
                active_scenario = ensure_active_scenario(reference_tables, reference_version)
                verdict = revision_save_verdict(
                    reference_version, active_scenario, reference_tables
                )
                if not verdict.allowed:
                    st.error(verdict.message)
                    return
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
            if verdict.message:
                st.session_state[SIDEBAR_FLASH_WARNING_KEY] = verdict.message
            st.rerun()


def _status_badge(
    *,
    active_revision_id: str | None,
    official_revision_id: str | None,
    official_release_no: int | None,
) -> str:
    """활성 리비전의 상태 배지를 고른다.

    미저장 변경이 있으면 빈 문자열을 준다. 그 상태는 요약 줄이 `미저장 변경` 으로 이미
    알리고 있어서, 본문 아래쪽 활성 상태 안내에서 또 적으면 같은 상자 안에 같은 문구가
    두 번 나온다.
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
