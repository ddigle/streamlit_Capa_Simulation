# Purpose: 사용자가 지정한 연도 이동의 전후 월 범위를 비교하고 새 시나리오로 저장한다.

import streamlit as st

from capa_simulation.components.scenario_transform import (
    month_table_summary,
    render_derived_save,
    render_source_selector,
    source_description,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.scenario_transform import (
    copy_scenario_tables,
    format_month_range,
    scenario_months,
)
from capa_simulation.services.scenario_year_shift import shift_scenario_years


def render_scenario_year_shift(repository: DuckDBScenarioRepository, database_path: str) -> None:
    st.subheader("연도 Shift")
    st.caption(
        "선택한 리비전의 연도를 직접 지정한 만큼 이동합니다. 월 번호와 나머지 값은 유지합니다."
    )
    try:
        _render_shift(repository, database_path)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))


def _render_shift(repository: DuckDBScenarioRepository, database_path: str) -> None:
    source = render_source_selector(repository, database_path, label="이동할", key="shift_source")
    if source is None:
        return
    years = st.number_input(
        "이동할 연수",
        min_value=-9998,
        max_value=9998,
        value=0,
        step=1,
        help="양수는 이후 연도, 음수는 이전 연도로 이동합니다. 예: 2는 2년 뒤, -2는 2년 전.",
        key="scenario_shift_years",
    )
    original = copy_scenario_tables(source.tables)
    shifted = shift_scenario_years(original, years)
    before, after = st.columns(2)
    with before:
        st.metric("이동 전 월 범위", format_month_range(scenario_months(original)))
    with after:
        st.metric("이동 후 월 범위", format_month_range(scenario_months(shifted)))
    st.info("월 없는 RQ_CHIP_EQ · RQ_CHIP_QTY · RQ_MODULE · RQ_DISPLAY_ORDER는 그대로 복사합니다.")
    st.caption("저장된 표시순서는 보존하며, 앱에서 불러올 때에는 기존 공용 표시순서가 적용됩니다.")
    preview = month_table_summary(original, label="이동 전").merge(
        month_table_summary(shifted, label="이동 후"), on="표", validate="one_to_one"
    )
    with st.expander("12개 월표 전후 비교", expanded=True):
        st.dataframe(preview, hide_index=True, width="stretch")
    if years == 0:
        st.caption("이동할 연수를 입력하면 새 시나리오로 저장할 수 있습니다.")
        return
    provenance = (
        f"연도 Shift\n원본: {source_description(source)}\n이동 연수: {years:+d}년\n"
        f"이동 전: {format_month_range(scenario_months(original))}\n"
        f"이동 후: {format_month_range(scenario_months(shifted))}\n"
        "변경: 12개 표의 생산계획년월 연도만 이동\n월 없는 4표 및 나머지 값: 원본 유지"
    )
    render_derived_save(
        repository,
        tables=shifted,
        source=source,
        operation="SCENARIO_YEAR_SHIFT",
        provenance=provenance,
        default_name=f"{source.scenario.scenario_name} · {years:+d}년 Shift",
        key="scenario_shift",
        request=(source.revision.revision_id, str(years)),
    )
