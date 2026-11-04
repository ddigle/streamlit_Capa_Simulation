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
from capa_simulation.services.scenario_virtual_products import virtual_product_records
from capa_simulation.services.scenario_year_shift import shift_scenario_years

# 원본을 고르는 상자의 역할(`render_source_selector` 의 `key` — 원본 메모의 칸 이름이다).
SHIFT_SOURCE_ROLES = ("shift_source",)
# 이동할 연수 칸의 풍선 — 무엇을 옮기고 무엇을 그대로 두는지는 늘 띄워 두지 않고 이 칸 풍선과
# Guide 가 말한다(설계 규칙 UI-TXT-01 · UI-TXT-02).
YEARS_HELP = (
    "양수는 이후 연도, 음수는 이전 연도로 이동합니다. 예: 2는 2년 뒤, -2는 2년 전. 12개 월표의 "
    "생산계획년월 연도만 옮기고 월 번호 · 나머지 값과 월 없는 RQ_CHIP_EQ · RQ_CHIP_QTY · "
    "RQ_MODULE · RQ_DISPLAY_ORDER는 그대로 복사합니다."
)
# 이동할 연수가 0 인 회차의 잠긴 저장 단추 — 저장 칸을 숨기지 않고 잠근 채 까닭을 풍선에
# 둔다(설계 규칙 UI-INP-07).
ZERO_SHIFT_SAVE_KEY = "scenario_shift_save_locked"
ZERO_SHIFT_HELP = "이동할 연수가 0 이면 원본과 같아 저장하지 않습니다 — 연수를 넣으면 열립니다."


def render_scenario_year_shift(repository: DuckDBScenarioRepository, database_path: str) -> None:
    st.subheader("연도 Shift")
    try:
        _render_shift(repository, database_path)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))


def _render_shift(repository: DuckDBScenarioRepository, database_path: str) -> None:
    source = render_source_selector(
        repository, database_path, label="이동할", key=SHIFT_SOURCE_ROLES[0]
    )
    if source is None:
        return
    years = st.number_input(
        "이동할 연수",
        min_value=-9998,
        max_value=9998,
        value=0,
        step=1,
        help=YEARS_HELP,
        key="scenario_shift_years",
        persist_state="session",
    )
    original = copy_scenario_tables(source.tables)
    shifted = shift_scenario_years(original, years)
    before, after = st.columns(2)
    with before:
        st.metric("이동 전 월 범위", format_month_range(scenario_months(original)))
    with after:
        st.metric("이동 후 월 범위", format_month_range(scenario_months(shifted)))
    preview = month_table_summary(original, label="이동 전").merge(
        month_table_summary(shifted, label="이동 후"), on="표", validate="one_to_one"
    )
    with st.expander("12개 월표 전후 비교", expanded=True):
        st.dataframe(preview, hide_index=True, width="stretch")
    if years == 0:
        st.button(
            "새 시나리오로 저장",
            type="primary",
            disabled=True,
            key=ZERO_SHIFT_SAVE_KEY,
            help=ZERO_SHIFT_HELP,
        )
        return
    virtual_products = virtual_product_records(
        repository.list_virtual_products(source.revision.revision_id)
    )
    provenance = (
        f"연도 Shift\n원본: {source_description(source)}\n이동 연수: {years:+d}년\n"
        f"이동 전: {format_month_range(scenario_months(original))}\n"
        f"이동 후: {format_month_range(scenario_months(shifted))}\n"
        "변경: 12개 표의 생산계획년월 연도만 이동\n월 없는 4표 및 나머지 값: 원본 유지\n"
        f"가상제품 복제 이력: 원본 {len(virtual_products)}건 보존"
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
        virtual_products=virtual_products,
    )
