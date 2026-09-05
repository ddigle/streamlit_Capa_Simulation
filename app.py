# Purpose: Streamlit 앱의 공식 시나리오 활성화, 공통 사이드바·조회기간과 페이지 탐색을 구성한다.

import streamlit as st

from capa_simulation.components.month_range_picker import render_month_range_picker
from capa_simulation.components.scenario_status import render_scenario_controls
from capa_simulation.navigation import build_navigation_pages
from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset
from capa_simulation.settings import (
    APP_NAME,
    DUCKDB_PATH,
    MONTH_SELECTION_END,
    MONTH_SELECTION_START,
    format_month,
)
from capa_simulation.sidebar_status import (
    register_month_range_placeholder,
    show_applied_month_range,
)

st.set_page_config(page_title=APP_NAME, page_icon=":material/factory:", layout="wide")
try:
    bootstrap_latest_official_scenario(str(DUCKDB_PATH.resolve()))
except Exception as exc:  # noqa: BLE001 - 어떤 실패든 원인을 읽을 수 있게 바꿔야 한다
    # DuckDB 파일은 프로세스 배타 잠금이다. 서버가 이미 떠 있는데 한 번 더 실행하면
    # 화면이 한 줄도 그려지기 전에 예외가 그대로 노출되고, Windows 로캘 탓에 원본
    # 메시지의 한글이 깨져 나온다. 사용자가 원인을 알 방법이 없어 안내로 바꾼다.
    st.error(
        "시나리오 데이터베이스를 열지 못했습니다.\n\n"
        f"- 파일: `{DUCKDB_PATH}`\n"
        "- 이 앱이 이미 다른 창에서 실행 중이면 그 창을 닫고 다시 시작하세요. "
        "DuckDB 는 한 번에 한 프로세스만 파일을 엽니다.\n"
        "- 그래도 같은 오류가 나면 파일 권한과 경로(네트워크 드라이브 여부)를 확인하세요.",
        icon=":material/database_off:",
    )
    with st.expander("원본 오류"):
        st.code(f"{type(exc).__name__}: {exc}")
    st.stop()
apply_pending_scenario_preset()


pages = build_navigation_pages()
navigation = st.navigation(pages.ordered, position="hidden")

st.html(
    """
    <style>
    [data-testid="stMainBlockContainer"] {
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        padding-top: 3rem !important;
    }

    .st-key-home_navigation a,
    .st-key-home_navigation a p {
        font-size: 1.5rem;
        font-weight: 700;
    }
    .st-key-home_navigation a {
        justify-content: center;
    }
    .st-key-home_navigation a p {
        text-align: center;
    }

    .st-key-capa_chatbot_navigation a p,
    .st-key-scenario_management_navigation a p,
    .st-key-static_capa_navigation a p,
    .st-key-dynamic_capa_navigation a p {
        font-size: 1.15rem;
        font-weight: 700;
    }

    .st-key-static_capa_subpages [data-testid="stPageLink-NavLink"],
    .st-key-dynamic_capa_subpages [data-testid="stPageLink-NavLink"] {
        margin-left: 1rem;
        width: calc(100% - 1rem);
    }
    </style>
    """
)
with st.sidebar.container(key="home_navigation"):
    st.page_link(pages.home, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="capa_chatbot_navigation"):
        st.page_link(pages.capa_chatbot, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="scenario_management_navigation"):
        st.page_link(pages.scenario_management, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="static_capa_navigation"):
        st.page_link(pages.static_capa, width="stretch")
    with st.container(key="static_capa_subpages"):
        for page in pages.static_capa_subpages:
            st.page_link(page, width="stretch")

with st.sidebar.container(border=True):
    with st.container(key="dynamic_capa_navigation"):
        st.page_link(pages.dynamic_capa, width="stretch")
    with st.container(key="dynamic_capa_subpages"):
        for page in pages.dynamic_capa_subpages:
            st.page_link(page, width="stretch")

render_scenario_controls()

with st.sidebar.container(border=True):
    # 다른 화면과 같은 낱말을 쓴다. 여기만 "조회 기간" 으로 띄어져 있었다.
    st.markdown("#### :material/date_range: 조회기간")
    default_month_range = (
        format_month(MONTH_SELECTION_START),
        format_month(MONTH_SELECTION_END),
    )
    current_month_range = st.session_state.get("production_month_range_v2", default_month_range)
    if not isinstance(current_month_range, (list, tuple)) or len(current_month_range) != 2:
        current_month_range = default_month_range
    selected_start_label, selected_end_label = render_month_range_picker(
        start=str(current_month_range[0]),
        end=str(current_month_range[1]),
        min_month=default_month_range[0],
        max_month=default_month_range[1],
        key="production_month_picker",
    )
    st.session_state["production_month_range_v2"] = (
        selected_start_label,
        selected_end_label,
    )
    register_month_range_placeholder(st.empty())
    show_applied_month_range(
        int(selected_start_label.replace("-", "")),
        int(selected_end_label.replace("-", "")),
    )

navigation.run()
