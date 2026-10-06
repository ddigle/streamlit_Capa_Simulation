# Purpose: 공정 표시명과 공용 표시순서 같은 운영 관리 기능을 탭으로 모아 제공한다.

from __future__ import annotations

import streamlit as st

from capa_simulation.components.app_credits import render_app_credits
from capa_simulation.components.display_order_management import (
    render_display_order_management,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_rename_management import (
    render_process_rename_management,
)
from capa_simulation.components.source_quality import render_source_quality
from capa_simulation.io.reference_cache import get_effective_reference_tables
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.scenario_activation import active_persisted_scenario_id
from capa_simulation.settings import DUCKDB_PATH

# 탭을 더할 자리다. 이름을 여기에 모아 두고 아래에서 같은 순서로 그린다. 차트·월별 표가
# 들어오면 그때 `tab_state.stateful_tabs` 로 바꿔 **그림만** 건너뛴다. 입력 위젯은 닫힌
# 탭에서도 항상 그린다 — 건너뛰면 Streamlit 이 그 위젯의 값을 버린다.
TAB_NAMES = (
    ":material/label: Proc Rename",
    ":material/sort: 표시순서 관리",
    ":material/fact_check: 원천 품질",
)

render_page_header("Admin Area")
render_page_guide("admin_area", title="Admin Area")

try:
    database_path = str(DUCKDB_PATH.resolve())
    repository = get_scenario_repository(database_path)
except BOOTSTRAP_ERRORS as exc:
    st.error(bootstrap_error_message(exc))
    st.stop()

# 공정 목록은 안내·편집 보조일 뿐이라 활성 시나리오가 없어도 화면을 멈추지 않는다.
# 공용 표시명 저장 자체는 시나리오와 무관하다.
try:
    reference_tables = get_effective_reference_tables()
    available_processes = sorted(
        reference_tables["RQ_MODULE"]["공정"]
        .astype("string")
        .str.strip()
        .dropna()
        .unique()
        .tolist()
    )
except BOOTSTRAP_ERRORS:
    available_processes = []

process_rename_tab, display_order_tab, source_quality_tab = st.tabs(list(TAB_NAMES))

with process_rename_tab:
    render_process_rename_management(repository, available_processes)
with display_order_tab:
    render_display_order_management(repository)
with source_quality_tab:
    # 원천이 없는 시나리오(복제본 등)가 정상이다. 그때 화면을 멈추지 않는다.
    scenario_id = active_persisted_scenario_id()
    if scenario_id is None:
        st.info("활성 시나리오가 없습니다. 시나리오를 먼저 불러오세요.")
    else:
        try:
            source_profile = repository.load_source_profile(scenario_id)
            source_rows = repository.load_source_row_count(scenario_id)
        except BOOTSTRAP_ERRORS as exc:
            st.info(bootstrap_error_message(exc))
        else:
            render_source_quality(source_profile, source_rows)

# 앱 이름·버전·개발자·인증 정보. 머리 띠는 적용 중인 시나리오를 싣고, 앱 자체의 정보는
# 여기 맨 아래다.
render_app_credits()
