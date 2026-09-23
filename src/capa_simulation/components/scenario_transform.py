# Purpose: 파생 시나리오의 저장 리비전 선택과 원본을 유지하는 신규 저장 폼을 제공한다.

from dataclasses import replace
from uuid import uuid4

import pandas as pd
import streamlit as st

from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import load_scenario_snapshot
from capa_simulation.persistence.models import ScenarioCreate, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import (
    active_persisted_revision_id,
    active_persisted_scenario_id,
)
from capa_simulation.services.revision_compatibility import revision_block_reason
from capa_simulation.services.scenario_transform import (
    MONTHLY_TABLES,
    format_month_range,
    month_axis,
    scenario_months,
)


def render_source_selector(
    repository: DuckDBScenarioRepository, database_path: str, *, label: str, key: str
) -> ScenarioSnapshot | None:
    """미저장 편집본 대신 사용자가 고른 불변 리비전의 원본 16표를 읽는다."""
    scenarios = {item.scenario_id: item for item in repository.list_scenarios()}
    selected = st.selectbox(
        f"{label} 시나리오",
        options=list(scenarios),
        index=None,
        placeholder="저장된 시나리오 선택",
        format_func=lambda value: scenarios[value].scenario_name,
        key=f"{key}_scenario",
        persist_state="session",
    )
    if selected is None:
        return None
    revisions = {item.revision_id: item for item in repository.list_revisions(selected)}
    revision_key = f"{key}_revision_{selected}"
    active_revision = active_persisted_revision_id()
    if (
        revision_key not in st.session_state
        and selected == active_persisted_scenario_id()
        and active_revision in revisions
    ):
        st.session_state[revision_key] = active_revision
    revision_id = st.selectbox(
        f"{label} 리비전",
        options=list(revisions),
        format_func=lambda value: (
            f"r{revisions[value].revision_no} · {revisions[value].revision_name}"
        ),
        key=revision_key,
        persist_state="session",
        help=(
            "현재 활성 시나리오는 활성 리비전, 나머지는 최신 리비전을 먼저 고릅니다. "
            "현재 화면의 미저장 편집은 포함하지 않습니다."
        ),
    )
    if revision_id is None:
        st.info("선택할 저장 리비전이 없습니다.")
        return None
    return load_scenario_snapshot(database_path, revision_id, apply_global_display_order=False)


def source_description(snapshot: ScenarioSnapshot) -> str:
    return (
        f"{snapshot.scenario.scenario_name} [시나리오 {snapshot.scenario.scenario_id}] / "
        f"r{snapshot.revision.revision_no} {snapshot.revision.revision_name} "
        f"[리비전 {snapshot.revision.revision_id}]"
    )


def month_table_summary(tables: dict[str, pd.DataFrame], *, label: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "표": name,
                f"{label} 월 범위": format_month_range(month_axis(tables[name])),
                f"{label} 월 수": len(month_axis(tables[name])),
                f"{label} 행 수": len(tables[name]),
            }
            for name in MONTHLY_TABLES
        ]
    )


def render_derived_save(
    repository: DuckDBScenarioRepository,
    *,
    tables: dict[str, pd.DataFrame],
    source: ScenarioSnapshot,
    operation: str,
    provenance: str,
    default_name: str,
    key: str,
    request: tuple[str, ...],
) -> None:
    """저장 성공을 세션에 남기고 같은 제출의 중복 저장과 활성 편집본 교체를 피한다."""
    blocked = revision_block_reason(tables)
    if blocked:
        st.error(blocked)
        return
    months = scenario_months(tables)
    if not months:
        st.error("저장할 월 데이터가 없습니다.")
        return
    saved_key = f"{key}_saved"
    saved = st.session_state.get(saved_key)
    already_saved = isinstance(saved, dict) and saved.get("request") == request
    if already_saved and isinstance(saved, dict):
        st.success(
            f"새 시나리오 ‘{saved['name']}’를 저장했습니다. 목록 관리에서 불러올 수 있습니다."
        )
    st.caption(
        "현재 활성 편집본과 원본 시나리오는 유지합니다. 새 시나리오의 조회기간·포함공정은 "
        "결과 전체이며, 확보·경고 기준은 원본(머지는 베이스)을 따릅니다."
    )
    with st.expander("저장될 출처 메모"):
        st.text(provenance)
    with st.form(f"{key}_save_form"):
        name = st.text_input("새 시나리오 이름", value=default_name, key=f"{key}_name")
        note = st.text_area("추가 메모", key=f"{key}_note", height=80)
        submitted = st.form_submit_button(
            "새 시나리오로 저장", type="primary", disabled=already_saved
        )
    if not submitted or already_saved:
        return
    preset = replace(
        source.preset,
        start_month=months[0],
        end_month=months[-1],
        included_processes=tuple(sorted(tables["RQ_REQB"]["공정"].dropna().astype(str).unique())),
        standard_target_processes=(),
        standard_target_start_date=None,
        standard_target_end_date=None,
        standard_target_show_detail=False,
    )
    try:
        snapshot = repository.create_scenario(
            ScenarioCreate(
                scenario_name=name,
                source_simulation_code=f"{operation}-{uuid4().hex[:12]}",
                source_simulation_name=source.scenario.scenario_name,
                source_type=operation,
                pipeline_version="scenario-transform-v1",
            ),
            tables,
            preset,
            revision_name="초기 리비전",
            note=provenance + (f"\n사용자 메모: {note.strip()}" if note.strip() else ""),
        )
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    st.session_state[saved_key] = {"request": request, "name": snapshot.scenario.scenario_name}
    st.rerun()
