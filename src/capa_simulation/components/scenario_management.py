# Purpose: 시나리오 목록 관리, 활성 RQ 복제 저장, 리비전 저장 UI를 한 곳에서 그린다.

"""시나리오 목록 관리·복제 저장·리비전 저장 화면.

「목록 관리」가 시나리오를 다루는 단일 입구다. 불러오기 화면 안에 이름 수정·공식 지정·
보관이 각자 접힌 칸으로 흩어져 있으면 무엇을 고르고 무엇을 누르는지가 칸마다 달라진다.
표에서 한 건을 고른 뒤 그 한 건에 대해 네 가지 작업을 누르는 한 가지 모양만 쓴다.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pandas as pd
import streamlit as st

from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import (
    clear_scenario_snapshot_cache,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset, ScenarioSummary
from capa_simulation.persistence.repository import (
    REVISION_TABLES,
    DuckDBScenarioRepository,
)
from capa_simulation.scenario_activation import (
    activate_persisted_snapshot,
    active_persisted_revision_id,
    active_persisted_scenario_id,
    clear_persisted_scenario_activation,
    has_unsaved_scenario_changes,
)
from capa_simulation.scenario_preset_state import capture_scenario_preset
from capa_simulation.scenario_state import (
    ActiveScenario,
    ensure_active_scenario,
    session_virtual_products,
)
from capa_simulation.services.builtin_seed import BUILTIN_SEED_SOURCE_CODE
from capa_simulation.services.virtual_product import VirtualProductRecord

CLONE_PIPELINE_VERSION = "duckdb-rq-snapshot-v3"
FLASH_KEY = "scenario_management_flash"
MODE_KEY = "scenario_page_mode"
MODES = ("목록 관리", "현재 활성 RQ 복제", "리비전 저장")
LIST_EDITOR_KEY = "scenario_list_editor"
ACTION_KEY = "scenario_list_action"
ACTION_OWNER_KEY = "scenario_list_action_owner"
DELETE_CONFIRM_KEY = "scenario_list_delete_confirm"
SELECT_COLUMN = "선택"
ORDER_COLUMN = "순서"


def render_scenario_management(
    repository: DuckDBScenarioRepository,
    database_path: str,
) -> None:
    scenarios = repository.list_scenarios()
    _render_store_status(repository, scenarios)
    # 작업 이름이 바뀌었으므로 예전 세션에 남은 값은 위젯이 만들어지기 전에 버린다.
    # 옵션에 없는 값이 그대로 오면 Streamlit 이 선택을 잃고 필수 선택에서 막힌다.
    if st.session_state.get(MODE_KEY) not in MODES:
        st.session_state.pop(MODE_KEY, None)
    mode = st.segmented_control(
        "시나리오 작업",
        list(MODES),
        default=MODES[0],
        key=MODE_KEY,
        persist_state="session",
        # 선택 해제를 허용하면 mode가 None이 되어 아래 분기가 파괴적인
        # `리비전 저장`으로 떨어진다.
        required=True,
    )
    if mode == "목록 관리":
        _render_list_management(repository, database_path, scenarios)
    elif mode == "현재 활성 RQ 복제":
        _render_clone(repository)
    elif mode == "리비전 저장":
        _render_revision_save(repository)


def _render_store_status(
    repository: DuckDBScenarioRepository,
    scenarios: list[ScenarioSummary],
) -> None:
    flash = st.session_state.pop(FLASH_KEY, None)
    if isinstance(flash, str):
        st.success(flash)
    official = repository.latest_official_release()
    with st.container(border=True):
        st.markdown("#### :material/database: 저장소 상태")
        active_id = active_persisted_scenario_id()
        active_revision_id = active_persisted_revision_id()
        if active_id and active_revision_id:
            st.write(_active_scenario_line(repository, scenarios, active_id, active_revision_id))
            # UUID 는 사람이 읽을 것이 아니라 장애를 신고할 때 적어 보낼 값이다. 상태 줄에
            # 그대로 두면 정작 어느 시나리오인지가 안 읽혀 접어 둔다.
            with st.expander("식별자", icon=":material/tag:"):
                st.caption(f"시나리오 ID `{active_id}`")
                st.caption(f"리비전 ID `{active_revision_id}`")
        else:
            st.write("현재 활성화된 DuckDB 리비전이 없습니다.")
        if official is None:
            st.warning("공식버전이 없습니다. 새 웹 세션에서 자동으로 불러올 기준이 없습니다.")
        else:
            st.success(
                f"최신 공식 v{official.release_no} · {official.scenario_name} "
                f"r{official.revision_no} · {official.release_name}"
            )
            if official.source_simulation_code == BUILTIN_SEED_SOURCE_CODE:
                st.info(
                    "현재 공식버전은 GitHub 독립 실행용 합성 DEMO 데이터입니다. "
                    "운영 전 BigDataQuery 등록으로 실제 시나리오를 만들어 새 공식버전으로 "
                    "지정하세요."
                )


def _active_scenario_line(
    repository: DuckDBScenarioRepository,
    scenarios: list[ScenarioSummary],
    active_id: str,
    active_revision_id: str,
) -> str:
    """활성 시나리오·리비전을 사람이 읽는 이름으로 적는다. 이름을 못 찾으면 ID 로 적는다."""
    scenario = next((item for item in scenarios if item.scenario_id == active_id), None)
    scenario_label = scenario.scenario_name if scenario is not None else active_id
    revision_label = active_revision_id
    if scenario is not None:
        revision = next(
            (
                item
                for item in repository.list_revisions(active_id)
                if item.revision_id == active_revision_id
            ),
            None,
        )
        if revision is not None:
            revision_label = f"r{revision.revision_no} · {revision.revision_name}"
    dirty = " · :orange-badge[저장하지 않은 변경 있음]" if has_unsaved_scenario_changes() else ""
    return f"**{scenario_label}** · {revision_label}{dirty}"


def _render_list_management(
    repository: DuckDBScenarioRepository,
    database_path: str,
    scenarios: list[ScenarioSummary],
) -> None:
    if not scenarios:
        st.info("저장된 시나리오가 없습니다. 초기 이관 또는 신규 등록이 필요합니다.")
        return
    edited = _render_scenario_list_editor(repository, scenarios)
    selected_id = _resolve_selected_scenario(edited)
    if selected_id is None:
        st.caption(
            "표에서 시나리오 한 건을 선택하면 불러오기·이름 수정·공식버전 지정·삭제를 "
            "할 수 있습니다."
        )
        return
    scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
    _render_scenario_actions(repository, database_path, scenario_by_id[selected_id])


def _render_scenario_list_editor(
    repository: DuckDBScenarioRepository,
    scenarios: list[ScenarioSummary],
) -> pd.DataFrame:
    """누적 목록 표. 체크박스와 순서만 편집할 수 있고 나머지는 읽기 전용이다."""
    # 발행 이력은 최신 번호가 먼저 온다. 시나리오마다 첫 번째가 그 시나리오의 최신 공식이다.
    releases = repository.list_official_releases()
    official_by_scenario: dict[str, int] = {}
    for release in releases:
        official_by_scenario.setdefault(release.scenario_id, release.release_no)
    # 최신 공식 시나리오는 기본 진입점이라 삭제가 막힌다. 눌러 보고 알게 하지 않는다.
    latest_official_scenario = releases[0].scenario_id if releases else None
    table = pd.DataFrame(
        {
            SELECT_COLUMN: False,
            ORDER_COLUMN: range(1, len(scenarios) + 1),
            "시나리오명": [scenario.scenario_name for scenario in scenarios],
            "원천 코드": [scenario.source_simulation_code for scenario in scenarios],
            "활성 리비전": [f"r{scenario.active_revision_no}" for scenario in scenarios],
            "공식버전": [
                _official_label(
                    scenario.scenario_id, official_by_scenario, latest_official_scenario
                )
                for scenario in scenarios
            ],
            "최근 수정": [scenario.updated_at for scenario in scenarios],
        },
        index=pd.Index([scenario.scenario_id for scenario in scenarios], name="scenario_id"),
    )
    edited = st.data_editor(
        table,
        key=LIST_EDITOR_KEY,
        num_rows="fixed",
        hide_index=True,
        width="stretch",
        # 체크박스 한 칸, 두 자리 숫자, `r12` 는 `small` 로도 필요 이상 넓다. 남는 폭은
        # 실제로 길어질 수 있는 시나리오명·원천 코드가 가져가는 편이 읽기 좋다.
        #
        # 픽셀 값은 **최소 폭이 아니라 비율**이다. 합이 표 폭보다 작으면 Streamlit 이
        # 남는 폭을 비례로 나눠 준다. 그래서 좁힐 칸만 줄이면 소용이 없고 넓힐 칸을 함께
        # 키워야 비율이 바뀐다.
        column_config={
            SELECT_COLUMN: st.column_config.CheckboxColumn(SELECT_COLUMN, width=44),
            ORDER_COLUMN: st.column_config.NumberColumn(
                ORDER_COLUMN, min_value=1, step=1, required=True, width=44
            ),
            "시나리오명": st.column_config.TextColumn("시나리오명", width=300),
            "원천 코드": st.column_config.TextColumn("원천 코드", width=240),
            "활성 리비전": st.column_config.TextColumn("활성 리비전", width=70),
            "공식버전": st.column_config.TextColumn("공식버전", width=90),
            "최근 수정": st.column_config.DatetimeColumn(
                "최근 수정", format="YYYY-MM-DD HH:mm", width=140
            ),
        },
        disabled=["시나리오명", "원천 코드", "활성 리비전", "공식버전", "최근 수정"],
    )
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("순서 저장", icon=":material/swap_vert:"):
            _save_list_order(repository, edited)
        st.caption(
            f"`{ORDER_COLUMN}` 숫자를 고쳐 누적 순서를 바꿉니다. 저장하면 표에 보이는 "
            "차례대로 1번부터 다시 매깁니다."
        )
    return edited


def _official_label(
    scenario_id: str,
    official_by_scenario: dict[str, int],
    latest_official_scenario: str | None,
) -> str:
    """그 시나리오의 최신 공식버전 번호. 저장소 전체의 최신이면 그 사실을 함께 적는다."""
    release_no = official_by_scenario.get(scenario_id)
    if release_no is None:
        return ""
    if scenario_id == latest_official_scenario:
        return f"v{release_no} · 최신"
    return f"v{release_no}"


def _save_list_order(repository: DuckDBScenarioRepository, edited: pd.DataFrame) -> None:
    # 같은 숫자를 적어도 막지 않는다. 안정 정렬이라 지금 보이는 차례가 그대로 유지된다.
    ordered = edited.sort_values(ORDER_COLUMN, kind="stable").index.tolist()
    try:
        repository.reorder_scenarios([str(scenario_id) for scenario_id in ordered])
    except (KeyError, ValueError) as exc:
        st.error(str(exc))
        return
    st.session_state[FLASH_KEY] = "시나리오 누적 순서를 저장했습니다."
    st.session_state.pop(LIST_EDITOR_KEY, None)
    st.rerun()


def _resolve_selected_scenario(edited: pd.DataFrame) -> str | None:
    """체크한 시나리오 하나. 두 건 이상이면 고른 것이 없는 것으로 본다."""
    checked = [
        str(scenario_id)
        for scenario_id, selected in zip(edited.index, edited[SELECT_COLUMN], strict=True)
        if bool(selected)
    ]
    if len(checked) > 1:
        st.warning("시나리오는 한 번에 한 건만 선택할 수 있습니다. 체크를 하나만 남기세요.")
        return None
    return checked[0] if checked else None


def _render_scenario_actions(
    repository: DuckDBScenarioRepository,
    database_path: str,
    summary: ScenarioSummary,
) -> None:
    # 고른 시나리오가 바뀌면 열려 있던 작업 칸을 닫는다. 이름 수정 칸을 열어 둔 채로 다른
    # 시나리오를 고르면 어느 쪽을 고치는 중인지 알 수 없다.
    if st.session_state.get(ACTION_OWNER_KEY) != summary.scenario_id:
        st.session_state[ACTION_OWNER_KEY] = summary.scenario_id
        st.session_state.pop(ACTION_KEY, None)
        st.session_state.pop(DELETE_CONFIRM_KEY, None)
    with st.container(border=True):
        st.markdown(f"#### :material/check_box: {summary.scenario_name}")
        revisions = repository.list_revisions(summary.scenario_id)
        revision_by_id = {revision.revision_id: revision for revision in revisions}
        selected_revision_id = st.selectbox(
            "리비전",
            options=list(revision_by_id),
            format_func=lambda value: (
                f"r{revision_by_id[value].revision_no} · {revision_by_id[value].revision_name}"
            ),
            key="scenario_list_revision_id",
        )
        discard_changes = True
        if has_unsaved_scenario_changes():
            st.warning("현재 활성 시나리오에 저장하지 않은 편집값이 있습니다.")
            discard_changes = st.checkbox(
                "저장하지 않은 변경을 버리고 불러오기",
                key="scenario_discard_unsaved_changes",
            )
        load_column, rename_column, official_column, delete_column = st.columns(4)
        with load_column:
            if st.button(
                "시나리오 불러오기",
                icon=":material/download:",
                type="primary",
                disabled=not discard_changes,
                width="stretch",
            ):
                _load_revision(database_path, selected_revision_id)
        with rename_column:
            _action_button("시나리오명 수정", "rename", ":material/edit:")
        with official_column:
            _action_button("공식버전 지정", "official", ":material/verified:")
        with delete_column:
            _action_button("시나리오 삭제", "delete", ":material/delete_forever:")
        action = st.session_state.get(ACTION_KEY)
        if action == "rename":
            _render_rename(repository, summary)
        elif action == "official":
            _render_official(repository, summary, selected_revision_id)
        elif action == "delete":
            _render_delete(repository, summary)


def _action_button(label: str, action: str, icon: str) -> None:
    if st.button(label, icon=icon, width="stretch", key=f"scenario_list_action_{action}"):
        st.session_state[ACTION_KEY] = action
        st.rerun()


def _load_revision(database_path: str, revision_id: str) -> None:
    snapshot = load_scenario_snapshot(database_path, revision_id)
    activate_persisted_snapshot(snapshot)
    st.session_state[FLASH_KEY] = (
        f"{snapshot.scenario.scenario_name} r{snapshot.revision.revision_no}을 불러왔습니다."
    )
    st.rerun()


def _render_rename(repository: DuckDBScenarioRepository, summary: ScenarioSummary) -> None:
    with st.form("scenario_rename_form"):
        renamed = st.text_input("새 시나리오명", value=summary.scenario_name)
        rename_submitted = st.form_submit_button("이름 저장", width="stretch")
    if not rename_submitted:
        return
    try:
        renamed_summary = repository.rename_scenario(summary.scenario_id, renamed)
    except (KeyError, ValueError) as exc:
        st.error(str(exc))
        return
    st.session_state[FLASH_KEY] = f"시나리오명을 {renamed_summary.scenario_name} 으로 변경했습니다."
    st.session_state.pop(ACTION_KEY, None)
    st.rerun()


def _render_official(
    repository: DuckDBScenarioRepository,
    summary: ScenarioSummary,
    revision_id: str,
) -> None:
    st.caption("공식 지정은 기존 리비전을 변경하지 않고 발행 이력을 새로 추가합니다.")
    with st.form("scenario_official_form"):
        release_name = st.text_input("공식버전명", value=f"{summary.scenario_name} 공식안")
        release_note = st.text_area("공식 지정 메모", height=80)
        official_submitted = st.form_submit_button(
            "선택 리비전을 공식버전으로 지정",
            icon=":material/publish:",
            type="primary",
            width="stretch",
        )
    if official_submitted:
        try:
            release = repository.publish_official_revision(
                summary.scenario_id,
                revision_id,
                release_name=release_name,
                note=release_note,
            )
        except (KeyError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.session_state[FLASH_KEY] = (
                f"공식 v{release.release_no} · {release.release_name}을 지정했습니다."
            )
            st.session_state.pop(ACTION_KEY, None)
            st.rerun()
    releases = repository.list_official_releases(limit=10)
    if releases:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "공식버전": f"v{release.release_no}",
                        "시나리오": release.scenario_name,
                        "리비전": f"r{release.revision_no}",
                        "공식버전명": release.release_name,
                        "지정시각": release.published_at,
                    }
                    for release in releases
                ]
            ),
            hide_index=True,
            width="stretch",
        )


def _render_delete(repository: DuckDBScenarioRepository, summary: ScenarioSummary) -> None:
    st.warning(
        "삭제하면 그 시나리오의 리비전·원천 데이터·프리셋이 DuckDB 에서 사라지고 되돌릴 수 "
        "없습니다. 목록에서만 숨기는 보관 상태는 없습니다."
    )
    release_count = repository.count_official_releases(summary.scenario_id)
    if release_count:
        st.warning(f"이 시나리오의 공식 발행 이력 {release_count}건도 함께 사라집니다.")
    st.caption(
        "DuckDB 는 지운 페이지를 파일에 되돌려주지 않습니다. 행은 사라져도 파일 크기는 "
        "줄지 않고 삭제 기록만큼 오히려 조금 늘어납니다."
    )
    typed = st.text_input(
        "확인을 위해 시나리오명을 그대로 입력하세요",
        key=DELETE_CONFIRM_KEY,
        placeholder=summary.scenario_name,
    )
    if not st.button(
        "삭제 실행",
        icon=":material/delete_forever:",
        type="primary",
        disabled=typed.strip() != summary.scenario_name,
        width="stretch",
    ):
        return
    try:
        repository.delete_scenario(summary.scenario_id)
    except (KeyError, ValueError) as exc:
        st.error(str(exc))
        return
    clear_scenario_snapshot_cache()
    if summary.scenario_id == active_persisted_scenario_id():
        clear_persisted_scenario_activation()
    st.session_state[FLASH_KEY] = f"{summary.scenario_name} 을 삭제했습니다."
    for key in (LIST_EDITOR_KEY, ACTION_KEY, ACTION_OWNER_KEY, DELETE_CONFIRM_KEY):
        st.session_state.pop(key, None)
    st.rerun()


def _render_clone(repository: DuckDBScenarioRepository) -> None:
    try:
        reference_tables, active_scenario = _current_reference_context()
    except Exception as exc:
        st.error(f"신규 시나리오의 기준 표시순서를 준비하지 못했습니다: {exc}")
        return
    st.info("현재 활성 RQ 16개와 프리셋을 독립 데이터셋으로 물리 복제합니다.")
    with st.form("scenario_create_form"):
        scenario_name = st.text_input("시나리오명")
        source_code = st.text_input("원천 시뮬레이션 코드")
        source_name = st.text_input("원천 시뮬레이션명")
        revision_name = st.text_input("초기 리비전명", value="초기 리비전")
        note = st.text_area("메모", height=100)
        create_submitted = st.form_submit_button(
            "신규 시나리오 저장",
            icon=":material/save:",
            type="primary",
            width="stretch",
        )
    if not create_submitted:
        return
    try:
        revision_source = revision_tables_for_save(active_scenario, reference_tables)
        preset = _compatible_preset(capture_scenario_preset(revision_source), revision_source)
        snapshot = repository.create_scenario(
            ScenarioCreate(
                scenario_name=scenario_name,
                source_simulation_code=source_code,
                source_simulation_name=source_name,
                source_type="DUCKDB_SCENARIO_CLONE",
                pipeline_version=CLONE_PIPELINE_VERSION,
                source_registered_at=None,
            ),
            reference_tables,
            preset,
            source_data=None,
            revision_tables=revision_source,
            revision_name=revision_name,
            note=note.strip() or None,
        )
    except (FileNotFoundError, KeyError, RuntimeError, TypeError, ValueError) as exc:
        st.error(str(exc))
    else:
        activate_persisted_snapshot(snapshot)
        st.session_state[FLASH_KEY] = f"{snapshot.scenario.scenario_name}을 저장했습니다."
        st.rerun()


def _render_revision_save(repository: DuckDBScenarioRepository) -> None:
    scenario_id = active_persisted_scenario_id()
    if scenario_id is None:
        st.info("먼저 저장된 시나리오를 불러오거나 신규 시나리오를 저장하세요.")
        return
    try:
        reference_tables, active_scenario = _current_reference_context()
    except Exception as exc:
        st.error(f"리비전 기준정보를 불러오지 못했습니다: {exc}")
        return
    with st.form("scenario_revision_form"):
        revision_name = st.text_input("새 리비전명")
        note = st.text_area("변경 메모", height=100)
        revision_submitted = st.form_submit_button(
            "새 리비전 저장",
            icon=":material/save_as:",
            type="primary",
            width="stretch",
        )
    if not revision_submitted:
        return
    try:
        revision_tables = revision_tables_for_save(active_scenario, reference_tables)
        preset = capture_scenario_preset(
            {**reference_tables, "RQ_REQB": revision_tables["RQ_REQB"]}
        )
        snapshot = repository.save_revision(
            scenario_id,
            revision_tables,
            preset,
            revision_name=revision_name,
            parent_revision_id=active_persisted_revision_id(),
            note=note.strip() or None,
            virtual_products=[
                {
                    "product": record.product,
                    "stack": record.stack,
                    "source_product": record.source_product,
                    "source_stack": record.source_stack,
                }
                for record in cast(tuple[VirtualProductRecord, ...], session_virtual_products())
            ],
        )
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
    else:
        virtual_count = len(session_virtual_products())
        activate_persisted_snapshot(snapshot)
        message = f"새 리비전 r{snapshot.revision.revision_no}을 저장했습니다."
        if virtual_count:
            message += (
                f" 가상 제품 {virtual_count}건이 포함되어 있습니다. "
                "실적과 대조할 수 없으므로 공식버전으로 발행하기 전에 확인하세요."
            )
        st.session_state[FLASH_KEY] = message
        st.rerun()


def revision_tables_for_save(
    active_scenario: ActiveScenario,
    _reference_tables: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    return {
        name: active_scenario["tables"][name]
        for name in REVISION_TABLES
        if name in active_scenario["tables"]
    }


def _current_reference_context() -> tuple[dict[str, pd.DataFrame], ActiveScenario]:
    reference_version = get_effective_reference_version()
    reference_tables = get_effective_reference_tables()
    return reference_tables, ensure_active_scenario(reference_tables, reference_version)


def _compatible_preset(
    preset: ScenarioPreset,
    reference_tables: dict[str, pd.DataFrame],
) -> ScenarioPreset:
    available = set(
        reference_tables["RQ_REQB"]["공정"].astype("string").str.strip().dropna().tolist()
    )
    return replace(
        preset,
        included_processes=tuple(
            process for process in preset.included_processes if process in available
        ),
    )
