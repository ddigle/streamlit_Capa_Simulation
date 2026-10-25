# Purpose: 파생 시나리오의 원본 리비전 선택과 계산 검사를 거치는 신규 저장 폼을 제공한다.

from collections.abc import Collection, Sequence
from dataclasses import asdict, replace
from uuid import uuid4

import pandas as pd
import streamlit as st

from capa_simulation.components.capacity_gate import derived_save_verdict
from capa_simulation.components.revision_label import revision_label
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
    prune_choice,
)
from capa_simulation.persistence.cache import load_scenario_snapshot
from capa_simulation.persistence.models import (
    RevisionSummary,
    ScenarioCreate,
    ScenarioSnapshot,
    ScenarioSummary,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import (
    active_persisted_revision_id,
    active_persisted_scenario_id,
)
from capa_simulation.services.korean_particle import object_particle
from capa_simulation.services.revision_compatibility import revision_block_reason
from capa_simulation.services.scenario_transform import (
    MONTHLY_TABLES,
    format_month_range,
    month_axis,
    scenario_months,
)
from capa_simulation.services.virtual_product import VirtualProductRecord, records_to_frame

# 고른 원본 리비전 스냅샷(저장된 원본 — 공용 표시순서 미적용)의 세션 메모. 역할(`key` —
# 베이스·덧붙일·이동할)마다 한 벌이고, 원본을 바꿀 때만 `load_scenario_snapshot` 을 부른다
# (cache_data 는 적중해도 피클을 다시 푼다). 표·프리셋은 리비전 id 에 묶여 바뀌지 않는다
# (append-only). 시나리오·리비전 요약(이름·활성 리비전 — 출처 메모·기본 이름에 쓰인다)은 바뀔 수
# 있어 회차마다 목록에서 새로 읽고, 메모를 다시 쓸지도 그 요약으로 가른다(`_source_snapshot`).
# 메모한 표는 읽기만 한다 — 화면은 `copy_scenario_tables` 사본으로 일한다.
# 메모는 리비전 하나 크기의 살아 있는 표라 세션에 오래 두지 않는다. 키 이름이
# `PAGE_DIALOG_SUFFIX` 로 끝나 `forget_page_dialogs` 를 부르는 곳 — 페이지를 떠나는 회차
# (`app.py`), 사이드바 조회기간·시나리오 팝업과 Guide 를 여는 콜백 — 에서 버린다(그 뒤 첫 회차에
# 한 번 다시 읽는다). 모드를 바꾸거나 시나리오를 지우·보관·되살리·이름 바꿀 때, 상자를 비울
# 때도 버린다(`forget_derived_sources`).
SOURCE_MEMO_KEY = f"scenario_transform_sources{PAGE_DIALOG_SUFFIX}"


# 메모 한 칸: (DB 경로, 그 회차 목록의 시나리오 요약, 리비전 요약, 돌려줄 스냅샷).
_SourceEntry = tuple[str, ScenarioSummary, RevisionSummary, ScenarioSnapshot]


def _source_memo() -> dict[str, _SourceEntry]:
    memo = st.session_state.get(SOURCE_MEMO_KEY)
    if not isinstance(memo, dict):
        memo = {}
        st.session_state[SOURCE_MEMO_KEY] = memo
    return memo


def forget_derived_sources(*, keep: Collection[str] = ()) -> None:
    """메모한 원본을 버린다. `keep` 에 든 역할만 남긴다."""
    memo = st.session_state.get(SOURCE_MEMO_KEY)
    if not isinstance(memo, dict):
        return
    kept = {role: entry for role, entry in memo.items() if role in keep}
    if kept:
        st.session_state[SOURCE_MEMO_KEY] = kept
    else:
        st.session_state.pop(SOURCE_MEMO_KEY, None)


def _source_snapshot(
    database_path: str,
    role: str,
    scenario: ScenarioSummary,
    revision: RevisionSummary,
) -> ScenarioSnapshot:
    """이 역할에 고른 리비전의 원본. 같은 DB·같은 목록 요약이면 메모를, 아니면 새로 읽는다.

    견주는 요약도, 돌려주는 스냅샷의 요약도 **그 회차 목록에서 읽은 것**이다. 프로세스 캐시
    (`load_scenario_snapshot`)가 든 요약은 이름 바꾸기·보관·되살리기·삭제 때만 비워지고
    새 리비전 저장 때는 그대로다. 그 요약으로 견주면 옛 리비전을 고른 동안 회차마다 다시 읽고
    출처 메모에 옛 요약이 든다.
    """
    memo = _source_memo()
    entry = memo.get(role)
    if entry is not None and entry[:3] == (database_path, scenario, revision):
        return entry[3]
    loaded = load_scenario_snapshot(
        database_path, revision.revision_id, apply_global_display_order=False
    )
    snapshot = replace(loaded, scenario=scenario, revision=revision)
    memo[role] = (database_path, scenario, revision, snapshot)
    return snapshot


def render_source_selector(
    repository: DuckDBScenarioRepository, database_path: str, *, label: str, key: str
) -> ScenarioSnapshot | None:
    """미저장 편집본 대신 사용자가 고른 불변 리비전의 원본 16표를 읽는다.

    `key` 는 화면 안의 역할(베이스·덧붙일·이동할)이고 메모(`SOURCE_MEMO_KEY`)의 칸 이름이다.
    돌려준 스냅샷의 표는 읽기만 한다.
    """
    scenarios = {item.scenario_id: item for item in repository.list_scenarios()}
    # 선택지 글자는 시나리오 이름이라 다른 세션의 이름 바꾸기로 바뀐다. 고른 값을 매 회차 다시
    # 적어야 브라우저가 새 글자를 받는다(AGENTS 9장 「글자가 바뀌는 것을 피할 수 없는 상자」).
    prune_choice(f"{key}_scenario", list(scenarios), default=None)
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
        forget_derived_sources(keep=set(_source_memo()) - {key})
        return None
    revisions = {item.revision_id: item for item in repository.list_revisions(selected)}
    revision_key = f"{key}_revision_{selected}"
    # 리비전 상자에 씨앗으로 넣은 활성 리비전 id 를 역할·시나리오마다 적어 두고, 활성 리비전이
    # 이것과 달라지면(사이드바 시나리오 팝업의 불러오기·저장, 같은 페이지 목록 관리의 불러오기)
    # 상자를 새 활성 리비전으로 다시 적는다 — 상자는 `persist_state` 라 칸이 없을 때만 넣으면 옛
    # 리비전에 남는다. 사용자가 일부러 고른 리비전은 활성이 그대로인 동안 남고, 활성이 다른
    # 시나리오로 가면 씨앗만 버린다(AGENTS 9장, `scenario_management.REVISION_SEED_KEY`).
    seed_key = f"{key}_revision_seed_{selected}"
    active_revision = active_persisted_revision_id()
    if selected == active_persisted_scenario_id() and active_revision in revisions:
        if (
            revision_key not in st.session_state
            or st.session_state.get(seed_key) != active_revision
        ):
            st.session_state[revision_key] = active_revision
            st.session_state[seed_key] = active_revision
    else:
        st.session_state.pop(seed_key, None)
    # 씨앗 뒤에도 **매 회차** 고른 id 를 다시 적는다. 선택지 글자의 리비전명은 다른 세션이 바꿀 수
    # 있어, 적지 않으면 브라우저가 옛 글자를 되보내 1.63 이 첫 리비전으로 조용히 되돌린다 — 준비하던
    # 원본이 알림 없이 다른 리비전으로 바뀐다(AGENTS 9장 「글자가 바뀌는 것을 피할 수 없는 상자」).
    if revisions:
        prune_choice(revision_key, list(revisions), default=next(iter(revisions)))
    revision_id = st.selectbox(
        f"{label} 리비전",
        options=list(revisions),
        format_func=lambda value: revision_label(revisions[value]),
        key=revision_key,
        persist_state="session",
        help=(
            "지금 올라와 있는 시나리오는 올라와 있는 리비전, 나머지는 최신 리비전을 먼저 "
            "고릅니다. 저장하지 않은 편집은 들어가지 않습니다."
        ),
    )
    if revision_id is None:
        forget_derived_sources(keep=set(_source_memo()) - {key})
        st.info("선택할 저장 리비전이 없습니다.")
        return None
    return _source_snapshot(database_path, key, scenarios[selected], revisions[revision_id])


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
    virtual_products: tuple[VirtualProductRecord, ...] = (),
    gate_sources: Sequence[ScenarioSnapshot] = (),
) -> None:
    """저장 성공을 세션에 남기고 같은 제출의 중복 저장과 활성 편집본 교체를 피한다.

    제출하면 결과의 Capa 계산을 먼저 검사한다(`derived_save_verdict`). 「편집 전」은 결과를 만든
    원본 리비전 전부다 — `gate_sources` 가 비면 `source` 하나다(머지는 베이스·덧붙일 쪽 둘).
    """
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
        saved_name = str(saved["name"])
        st.success(
            f"새 시나리오 ‘{saved_name}’{object_particle(saved_name)} 저장했습니다. 목록 관리에서 "
            "불러올 수 있습니다."
        )
        if isinstance(saved.get("warning"), str):
            st.warning(saved["warning"], icon=":material/warning:")
    st.caption(
        "지금 올라와 있는 편집본과 원본 시나리오는 그대로입니다. 새 시나리오의 조회기간·포함공정은 "
        "결과 전체이며, 확보·경고 기준은 원본(머지는 베이스)을 따릅니다."
    )
    if virtual_products:
        with st.expander(
            f"함께 저장할 가상제품 복제 이력 · {len(virtual_products)}건",
            key=f"{key}_virtual_products_expander",
        ):
            st.dataframe(records_to_frame(virtual_products), hide_index=True, width="stretch")
    with st.expander("저장될 출처 메모"):
        st.text(provenance)
    # key 가 있는 이름 칸은 `value=` 가 바뀌어도 처음 값을 든다. 그래서 기본 이름을 씨앗 칸에
    # 적어 두고, 칸이 없거나 서버가 아는 칸 값이 옛 씨앗 그대로이면 바뀐 기본 이름(이동 연수·
    # 원본, 머지는 베이스)으로 다시 적는다. 이름 칸은 폼 안이라 제출 전에 친 글자는 서버가 모른다
    # — 저장을 눌러 제출된 이름만 남고, 치기만 한 이름은 연수·원본을 바꾸면 새 기본 이름으로
    # 바뀐다.
    name_key, seed_key = f"{key}_name", f"{key}_name_seed"
    seed = st.session_state.get(seed_key)
    if name_key not in st.session_state or (
        seed != default_name and st.session_state[name_key] == seed
    ):
        st.session_state[name_key] = default_name
    st.session_state[seed_key] = default_name
    with st.form(f"{key}_save_form"):
        name = st.text_input("새 시나리오 이름", key=name_key)
        note = st.text_area("추가 메모", key=f"{key}_note", height=80)
        submitted = st.form_submit_button(
            "새 시나리오로 저장", type="primary", disabled=already_saved
        )
    if not submitted or already_saved:
        return
    with st.spinner("저장 전에 결과의 Capa 계산을 검사하는 중입니다..."):
        verdict = derived_save_verdict(tables, gate_sources or (source,))
    if not verdict.allowed:
        st.error(verdict.message)
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
            virtual_products=[asdict(record) for record in virtual_products],
        )
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    st.session_state[saved_key] = {
        "request": request,
        "name": snapshot.scenario.scenario_name,
        "warning": verdict.message,
    }
    st.rerun()
