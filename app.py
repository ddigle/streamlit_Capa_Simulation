# Purpose: Streamlit 앱의 공식 시나리오 활성화, 공통 사이드바·조회기간과 페이지 탐색을 구성한다.

import streamlit as st

from capa_simulation.components.app_header import render_app_header
from capa_simulation.components.month_range_picker import render_month_range_picker
from capa_simulation.components.scenario_status import render_scenario_controls
from capa_simulation.design import tokens
from capa_simulation.navigation import build_navigation_pages
from capa_simulation.page_bootstrap import bootstrap_error_message
from capa_simulation.persistence._sql_helpers import pinned_connections
from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import (
    MONTH_PICKER_KEY,
    MONTH_RANGE_KEY,
    apply_pending_scenario_preset,
)
from capa_simulation.settings import (
    APP_ABOUT,
    APP_BUG_REPORT_URL,
    APP_HELP_URL,
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
from capa_simulation.sync_boot import enable_sync_state_if_managed

# CSS 선택자 여러 개를 한 규칙에 묶을 때 쓰는 구분자. 규칙 안 들여쓰기까지 붙여 둔다.
_SELECTOR_JOINER = ",\n        "

st.set_page_config(
    page_title=APP_NAME,
    page_icon=":material/factory:",
    layout="wide",
    # 헤더에 직접 글을 넣는 공식 API 는 없다. 개발자·인증 정보는 ⋮ 메뉴의 About 에 싣는다.
    menu_items={
        "Get help": APP_HELP_URL,
        "Report a bug": APP_BUG_REPORT_URL,
        "About": APP_ABOUT,
    },
)
# managed 모드에서만 동기화 표시를 켠다. local 모드(개발 PC·기본값)에서는 아무 일도 하지
# 않으므로 이 호출이 있어도 동작이 바뀌지 않는다.
enable_sync_state_if_managed()

# rerun 한 번 동안 시나리오 DB 인스턴스를 잡아 둔다. 사이드바가 rerun 마다 여는 연결 3개가
# 각자 인스턴스를 다시 만들지 않게 하는 것이 전부이고, rerun 이 끝나면 풀린다.
with pinned_connections(DUCKDB_PATH):
    try:
        bootstrap_latest_official_scenario(str(DUCKDB_PATH.resolve()))
    except Exception as exc:  # noqa: BLE001 - 어떤 실패든 원인을 읽을 수 있게 바꿔야 한다
        # DuckDB 파일은 프로세스 배타 잠금이다. 서버가 이미 떠 있는데 한 번 더 실행하면
        # 화면이 한 줄도 그려지기 전에 예외가 그대로 노출되고, Windows 로캘 탓에 원본
        # 메시지의 한글이 깨져 나온다. 사용자가 원인을 알 방법이 없어 안내로 바꾼다.
        st.error(bootstrap_error_message(exc), icon=":material/database_off:")
        with st.expander("원본 오류"):
            st.code(f"{type(exc).__name__}: {exc}")
        st.stop()
    apply_pending_scenario_preset()

    pages = build_navigation_pages()
    navigation = st.navigation(pages.ordered, position="hidden")
    # 지금 HOME 에 있는지는 **파이썬에서** 가른다. 활성 링크에 `aria-current` 도 안정적인
    # 클래스도 없고(emotion 해시뿐) CSS 만으로는 판정할 수 없다. `st.navigation()` 이
    # 이번 rerun 에 그릴 페이지를 그대로 돌려주므로 그 주소를 HOME 과 맞춰 본다.
    is_home = navigation.url_path == pages.home.url_path

    # 선택자도 같은 선언에서 낸다. 손으로 적으면 그룹을 더할 때 한쪽만 고치게 된다.
    group_title_selectors = _SELECTOR_JOINER.join(
        f".st-key-{group.slug}_navigation a p" for group in pages.groups
    )
    subpage_selectors = _SELECTOR_JOINER.join(
        f'.st-key-{group.slug}_subpages [data-testid="stPageLink-NavLink"]'
        for group in pages.groups
        if group.subpages
    )
    # 지금 보고 있는 페이지가 HOME 일 때만 면을 한 단계 누르고 글자를 ACCENT 로 올린다.
    # Streamlit 이 주는 활성 표시는 알파 0.15 의 흐린 회색 하나뿐이라 사실상 보이지 않는다.
    #
    # **`:hover`·`:focus-visible` 을 같은 묶음에 반드시 함께 적는다.** Streamlit 은 emotion
    # 으로 `.st-emotion-cache-XXXX:hover {{ background-color: ... }}` 를 깔고, 그 특정도
    # (0,2,0) 가 우리 `.st-key-home_navigation a` (0,1,1) 를 이긴다. 의사클래스를 붙이면
    # 우리가 (0,2,1) 이 되어 이기므로 `!important` 는 필요 없다.
    home_active_style = (
        f"""
        .st-key-home_navigation a,
        .st-key-home_navigation a:hover,
        .st-key-home_navigation a:focus-visible {{
            background: {tokens.SURFACE_PAGE};
        }}
        .st-key-home_navigation a p {{
            color: {tokens.ACCENT};
        }}"""
        if is_home
        else ""
    )
    st.html(
        f"""
        <style>
        [data-testid="stMainBlockContainer"] {{
            padding-left: 1.5rem !important;
            padding-right: 1.5rem !important;
            padding-top: 3rem !important;
        }}

        .st-key-home_navigation a,
        .st-key-home_navigation a p {{
            font-size: 1.5rem;
            font-weight: 700;
        }}
        /* 이 앱의 강조 문법은 ACCENT 왼쪽 세로 막대 하나다(앱 헤더 3px·metric 카드 4px).
           HOME 에도 같은 막대를 써서 새 어휘를 늘리지 않는다. 왼쪽 모서리만 각을 세워야
           Streamlit 이 건 radius 10px 에 막대가 휘지 않는다. */
        .st-key-home_navigation a {{
            justify-content: center;
            border-left: 4px solid {tokens.ACCENT};
            border-top-left-radius: 0;
            border-bottom-left-radius: 0;
        }}
        .st-key-home_navigation a p {{
            text-align: center;
        }}
{home_active_style}

        {group_title_selectors} {{
            font-size: 1.15rem;
            font-weight: 700;
        }}

        {subpage_selectors} {{
            margin-left: 1rem;
            width: calc(100% - 1rem);
        }}
        </style>
        """
    )
    render_app_header()
    with st.sidebar.container(key="home_navigation"):
        st.page_link(pages.home, width="stretch")

    # 박스 목록은 `navigation.SIDEBAR_GROUPS` 하나에서 나온다. 위 CSS 선택자도 같은 선언을
    # 읽으므로, 그룹을 더할 때 이 파일에서 고칠 것이 없다.
    for group in pages.groups:
        with st.sidebar.container(border=True):
            with st.container(key=f"{group.slug}_navigation"):
                st.page_link(group.main, width="stretch")
            if not group.subpages:
                continue
            with st.container(key=f"{group.slug}_subpages"):
                for page in group.subpages:
                    st.page_link(page, width="stretch")

    render_scenario_controls()

    with st.sidebar.container(border=True):
        # 다른 화면과 같은 낱말을 쓴다. 여기만 "조회 기간" 으로 띄어져 있었다.
        st.markdown("#### :material/date_range: 조회기간")
        default_month_range = (
            format_month(MONTH_SELECTION_START),
            format_month(MONTH_SELECTION_END),
        )
        current_month_range = st.session_state.get(MONTH_RANGE_KEY, default_month_range)
        if not isinstance(current_month_range, (list, tuple)) or len(current_month_range) != 2:
            current_month_range = default_month_range
        selected_start_label, selected_end_label = render_month_range_picker(
            start=str(current_month_range[0]),
            end=str(current_month_range[1]),
            min_month=default_month_range[0],
            max_month=default_month_range[1],
            key=MONTH_PICKER_KEY,
        )
        st.session_state[MONTH_RANGE_KEY] = (
            selected_start_label,
            selected_end_label,
        )
        register_month_range_placeholder(st.empty())
        show_applied_month_range(
            int(selected_start_label.replace("-", "")),
            int(selected_end_label.replace("-", "")),
        )

    # 관리 기능이라 조회 컨트롤보다 아래, 사이드바에서 가장 먼 곳에 둔다.
    with st.sidebar.container(border=True):
        with st.container(key="admin_area_navigation"):
            st.page_link(pages.admin_area, width="stretch")

    navigation.run()
