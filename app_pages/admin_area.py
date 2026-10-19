# Purpose: 공정 표시명·공용 표시순서·원천 품질·알림 모음 같은 운영 관리 기능을 탭으로 모아 제공한다.

from __future__ import annotations

import streamlit as st

from capa_simulation.components.alert_board import render_alert_board
from capa_simulation.components.display_order_management import (
    render_display_order_management,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_rename_management import (
    render_process_rename_management,
)
from capa_simulation.components.source_quality import render_source_quality
from capa_simulation.components.tab_state import stateful_tabs, tab_is_hidden
from capa_simulation.io.reference_cache import get_effective_reference_tables
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.scenario_activation import active_persisted_scenario_id
from capa_simulation.settings import DUCKDB_PATH

# 탭을 더할 자리다. 이름을 여기에 모아 두고 아래에서 같은 순서로 그린다. 탭은 `stateful_tabs`
# 라 열린 탭을 서버가 안다 — 위젯이 없는 「원천 품질」·「알림 모음」 은 닫혀 있으면 건너뛴다. 입력
# 위젯이 든 탭은 닫혀 있어도 늘 그린다 — 건너뛰면 Streamlit 이 그 위젯의 값을 버린다.
TAB_NAMES = (
    ":material/label: Proc Rename",
    ":material/sort: 표시순서 관리",
    ":material/fact_check: 원천 품질",
    ":material/notifications: 알림 모음",
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
# 공용 표시명 저장 자체는 시나리오와 무관하다. 시나리오 `RQ_MODULE` 공정만 본다 — 설비 마스터의
# 공정소분류까지 보려면 이 화면이 설비 DB 를 읽어야 해서 넓히지 않는다(겹침 경고 문구에 적는다).
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

process_rename_tab, display_order_tab, source_quality_tab, alert_tab = stateful_tabs(
    TAB_NAMES, key="admin_area_active_tab"
)

with process_rename_tab:
    render_process_rename_management(repository, available_processes)
with display_order_tab:
    render_display_order_management(repository)
with source_quality_tab:
    # 위젯 없는 읽기 전용 표라 닫혀 있으면 건너뛴다. 원천 읽기는 캐시가 없고 다른 두 탭은 캐시만
    # 읽어서, 이 탭이 Admin 회차의 유일한 DB 읽기다 — 닫힌 탭이 회차마다 DuckDB 인스턴스를 열고
    # 닫게 하지 않는다.
    if not tab_is_hidden(source_quality_tab):
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
with alert_tab:
    # HOME 에서 걷은 계산 알림(소요대수에 들지 않은 수요 등)을 시나리오 전체 기간으로 모은다
    # (2026-10-19 사용자 요청). 처음 여는 회차에 전체 기간 계산이 들어 닫혀 있으면 건너뛴다.
    if not tab_is_hidden(alert_tab):
        render_alert_board()
