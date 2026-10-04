# Purpose: 월별 출처와 겹침 처리 선택·무월 표 차이를 보여 주고 머지 결과를 신규 저장한다.

from typing import cast

import pandas as pd
import streamlit as st

from capa_simulation.components.scenario_transform import (
    month_table_summary,
    render_derived_save,
    render_source_selector,
    source_description,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.models import ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.scenario_month_merge import (
    OverlapPolicy,
    compare_non_monthly_tables,
    merge_scenario_months,
    preview_month_sources,
)
from capa_simulation.services.scenario_transform import (
    copy_scenario_tables,
    format_month_range,
    scenario_months,
)
from capa_simulation.services.scenario_virtual_products import (
    merge_virtual_product_records,
    virtual_product_records,
)
from capa_simulation.settings import format_month

OVERLAP_LABELS: dict[OverlapPolicy, str] = {
    "reject": "겹치면 저장 차단",
    "base": "겹치는 월은 베이스 사용",
    "donor": "겹치는 월은 덧붙일 쪽 사용",
}


def render_scenario_month_merge(repository: DuckDBScenarioRepository, database_path: str) -> None:
    st.subheader("월 머지")
    st.caption("베이스에 다른 시나리오의 선택한 월을 합칩니다. 겹치는 월은 사용할 쪽을 고릅니다.")
    try:
        _render_merge(repository, database_path)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))


def _render_merge(repository: DuckDBScenarioRepository, database_path: str) -> None:
    left, right = st.columns(2)
    with left:
        base = render_source_selector(repository, database_path, label="베이스", key="merge_base")
    with right:
        donor = render_source_selector(repository, database_path, label="덧붙일", key="merge_donor")
    if base is None or donor is None:
        return
    base_tables = copy_scenario_tables(base.tables)
    donor_tables = copy_scenario_tables(donor.tables)
    st.markdown("#### 월 없는 기준정보 4표")
    comparison = compare_non_monthly_tables(base_tables, donor_tables)
    st.dataframe(comparison, hide_index=True, width="stretch")
    if comparison["비교"].ne("같음").any():
        st.warning(
            "두 시나리오의 월 없는 기준정보가 다릅니다. 표시된 네 표는 베이스 값만 사용하고 "
            "덧붙일 쪽의 값은 가져오지 않습니다. Density·Chip·모듈 기준 차이를 확인하세요."
        )
    st.caption(
        "RQ_DISPLAY_ORDER는 각 리비전에 저장된 값을 비교·보존합니다. "
        "앱에서 불러올 때에는 기존 공용 표시순서가 적용됩니다."
    )
    donor_months = scenario_months(donor_tables)
    if not donor_months:
        st.error("덧붙일 시나리오에 월 데이터가 없습니다.")
        return
    st.markdown("#### 덧붙일 월 범위")
    start_column, end_column = st.columns(2)
    owner = donor.revision.revision_id
    with start_column:
        start = st.selectbox(
            "시작 월",
            donor_months,
            format_func=format_month,
            key=f"merge_start_{owner}",
            persist_state="session",
        )
    with end_column:
        end = st.selectbox(
            "종료 월",
            donor_months,
            index=len(donor_months) - 1,
            format_func=format_month,
            key=f"merge_end_{owner}",
            persist_state="session",
        )
    if start is None or end is None:
        return
    sources = preview_month_sources(base_tables, donor_tables, start, end)
    overlap = sources.loc[sources["베이스"] & sources["덧붙일 쪽"], "생산계획년월"].tolist()
    policy: OverlapPolicy = "reject"
    if overlap:
        st.warning(f"{len(overlap)}개월이 겹칩니다. 겹치는 월 전체에 같은 선택을 적용합니다.")
        st.caption("겹치는 월: " + ", ".join(format_month(month) for month in overlap))
        policy = cast(
            OverlapPolicy,
            st.segmented_control(
                "겹치는 월 처리",
                options=list(OVERLAP_LABELS),
                default="reject",
                format_func=OVERLAP_LABELS.__getitem__,
                key=f"merge_overlap_{base.revision.revision_id}_{owner}_{start}_{end}",
                help=(
                    "선택한 쪽의 월 전체를 12개 월표에 동일하게 적용합니다. "
                    "서로의 행을 섞지 않습니다."
                ),
            )
            or "reject",
        )
        if policy != "reject":
            sources = preview_month_sources(
                base_tables, donor_tables, start, end, overlap_policy=policy
            )
    source_display = _month_source_display(sources, base, donor)
    st.markdown("#### 저장 전 월별 출처")
    st.dataframe(source_display, hide_index=True, width="stretch")
    if overlap:
        st.caption("원본 리비전이나 월 범위를 바꾸면 겹침 처리를 다시 선택합니다.")
    result = merge_scenario_months(base_tables, donor_tables, start, end, overlap_policy=policy)
    st.success(f"12개 표의 월 축 일치 · {format_month_range(scenario_months(result))}")
    preview = month_table_summary(base_tables, label="베이스").merge(
        month_table_summary(result, label="결과"), on="표", validate="one_to_one"
    )
    preview["행 수 증감"] = preview["결과 행 수"] - preview["베이스 행 수"]
    with st.expander("12개 월표 미리보기", expanded=True):
        st.dataframe(preview, hide_index=True, width="stretch")
    base_history = virtual_product_records(
        repository.list_virtual_products(base.revision.revision_id)
    )
    donor_history = virtual_product_records(
        repository.list_virtual_products(donor.revision.revision_id)
    )
    if base_history or donor_history:
        st.caption(
            "가상제품 복제 이력에는 월이 없으므로 선택한 두 리비전의 전체 이력을 보존합니다. "
            "같은 제품·Stack의 복제 원본이 다르면 저장할 수 없습니다."
        )
    virtual_products = merge_virtual_product_records(base_history, donor_history)
    differences = comparison.loc[comparison["비교"].ne("같음"), "표"].tolist()
    provenance = (
        f"월 머지\n베이스: {source_description(base)}\n덧붙일 쪽: {source_description(donor)}\n"
        f"덧붙인 월 범위: {format_month(start)} ~ {format_month(end)} (양 끝 포함)\n"
        f"겹치는 월 처리: {OVERLAP_LABELS[policy]}\n"
        f"겹치는 월: {', '.join(format_month(month) for month in overlap) if overlap else '없음'}\n"
        "월별 선택 출처:\n"
        + "\n".join(
            f"{format_month(month)}: {origin}"
            for month, origin in sources[["생산계획년월", "선택 출처"]].itertuples(
                index=False, name=None
            )
        )
        + "\n월 없는 4표: 베이스 유지\n"
        f"두 원본의 무월 표 차이: {', '.join(differences) if differences else '없음'}\n"
        f"가상제품 복제 이력: {len(virtual_products)}건 보존 (동일 이력 중복 제거, 원본 충돌 차단)"
    )
    render_derived_save(
        repository,
        tables=result,
        source=base,
        operation="SCENARIO_MONTH_MERGE",
        provenance=provenance,
        default_name=f"{base.scenario.scenario_name} · 월 머지",
        key="scenario_merge",
        request=(
            base.revision.revision_id,
            donor.revision.revision_id,
            str(start),
            str(end),
            policy,
        ),
        virtual_products=virtual_products,
    )


def _month_source_display(
    sources: pd.DataFrame, base: ScenarioSnapshot, donor: ScenarioSnapshot
) -> pd.DataFrame:
    """서비스의 월 선택 결과에 원본 시나리오·리비전 표시만 덧붙인다."""
    snapshots = {"베이스": base, "덧붙일 쪽": donor}
    rows = []
    for month, in_base, in_donor, origin in sources[
        ["생산계획년월", "베이스", "덧붙일 쪽", "선택 출처"]
    ].itertuples(index=False, name=None):
        selected = snapshots.get(origin)
        rows.append(
            {
                "월": format_month(month),
                "겹침": "겹침" if in_base and in_donor else "",
                "선택 출처": origin,
                "사용할 시나리오": selected.scenario.scenario_name if selected else "선택 필요",
                "리비전": (
                    f"r{selected.revision.revision_no} · {selected.revision.revision_name}"
                    if selected
                    else "—"
                ),
            }
        )
    return pd.DataFrame(rows)
