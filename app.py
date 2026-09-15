# Purpose: Streamlit 앱의 공식 시나리오 활성화, 공통 사이드바·조회기간과 페이지 탐색을 구성한다.

import streamlit as st

from capa_simulation.components.app_header import render_app_header
from capa_simulation.components.month_range_picker import render_month_range_picker
from capa_simulation.components.scenario_status import (
    SCENARIO_BOX_KEY,
    render_scenario_controls,
)
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

# 사이드바 박스 CSS 훅. 여백을 좁히는 규칙과 Admin 의 `order` 가 이 key 를 읽는다.
MONTH_BOX_KEY = "sidebar_month_box"
ADMIN_BOX_KEY = "sidebar_admin_box"

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
    # 지금 어느 페이지에 있는지는 **파이썬에서** 가른다. 활성 링크에 `aria-current` 도
    # 안정적인 클래스도 없고(emotion 해시뿐) CSS 만으로는 판정할 수 없다. `st.navigation()`
    # 이 이번 rerun 에 그릴 페이지를 그대로 돌려주므로 그 주소로 선택자를 만든다.
    #
    # `href` 가 곧 `url_path` 다. HOME 은 기본 페이지라 늘 빈 문자열이고, 그것도 이 한
    # 페이지만 가리키므로 선택자로 쓸 수 있다.
    active_href = navigation.url_path

    # 선택자도 같은 선언에서 낸다. 손으로 적으면 그룹을 더할 때 한쪽만 고치게 된다.
    group_title_selectors = _SELECTOR_JOINER.join(
        f".st-key-{group.slug}_navigation a p" for group in pages.groups
    )
    subpage_slugs = [group.slug for group in pages.groups if group.subpages]
    subpage_selectors = _SELECTOR_JOINER.join(
        f'.st-key-{slug}_subpages [data-testid="stPageLink-NavLink"]' for slug in subpage_slugs
    )
    # 그룹 박스와 하위 묶음 선택자도 같은 선언에서 낸다.
    group_box_selectors = _SELECTOR_JOINER.join(
        f".st-key-{group.slug}_box" for group in pages.groups
    )
    # 링크가 하나뿐인 박스. 같은 여백을 줘도 안에 든 것이 한 줄뿐이라 위아래가 헐렁하다.
    solo_box_selectors = _SELECTOR_JOINER.join(
        f".st-key-{group.slug}_box" for group in pages.groups if not group.subpages
    )
    subpage_box_selectors = _SELECTOR_JOINER.join(
        f".st-key-{slug}_subpages" for slug in subpage_slugs
    )
    # 사이드바 안의 페이지 링크 전부. 본문에도 `stPageLink` 가 있을 수 있어 사이드바로 좁힌다.
    NAV_LINK = '[data-testid="stSidebarContent"] [data-testid="stPageLink-NavLink"]'
    # 활성 링크 하나. `href` 는 `url_path` 그대로라 페이지마다 유일하다.
    active_link = f'{NAV_LINK}[href="{active_href}"]'
    # **`:hover`·`:focus-visible` 을 같은 묶음에 반드시 함께 적는다.** Streamlit 은 emotion
    # 으로 `.st-emotion-cache-XXXX:hover` 배경을 깔고, 그 특정도 (0,2,0) 가 속성 선택자
    # 없는 우리 규칙을 이긴다. 의사클래스를 붙이면 우리가 이기므로 `!important` 는 필요 없다.
    #
    # 떠 있는 상태를 hover 에서도 그대로 **유지**한다. 활성 링크가 마우스에 반응해 더
    # 움직이면 "지금 여기" 가 아니라 "누를 수 있는 것" 으로 읽힌다.
    active_nav_style = f"""
        {active_link},
        {active_link}:hover,
        {active_link}:focus-visible {{
            background-color: {tokens.SURFACE};
            border-color: {tokens.BORDER};
            transform: translateY(-1px);
            box-shadow:
                0 0 0 3px {tokens.NAV_ACTIVE_RING},
                0 4px 10px {tokens.NAV_SHADOW};
        }}
        {active_link} p {{
            color: {tokens.ACCENT};
        }}
        /* 헤더 두 글줄이 이미 3px ACCENT 막대를 쓴다. 같은 막대를 지금 있는 자리에도
           세우면 헤더와 사이드바가 한 언어를 쓴다. 여백은 **모든 링크**에 주고 막대만
           활성에 켠다 — 활성에만 주면 라벨 시작 위치가 들쭉날쭉해진다. */
        {active_link}::before {{
            content: "";
            position: absolute;
            left: 0.28rem;
            top: 0.34rem;
            bottom: 0.34rem;
            width: 3px;
            border-radius: 2px;
            background-color: {tokens.ACCENT};
        }}"""
    st.html(
        f"""
        <style>
        /* **위쪽 여백은 줄이지 않는다.** 장식이 아니라 겹쳐 있는 헤더 띠(실측 56px)를
           피하는 자리다 — 브라우저에서 재니 2.25rem 에서 제목 줄상자가 띠 안으로 8.8px
           들어가고 2.75rem 에서도 1.3px 겹친다. 3rem 이 글자 윗선과 띠 사이에 12px 을
           남기는 최소값이다. 좌우만 줄인다 — 표와 차트가 가로로 길어 0.25rem 을 덜어도
           읽는 데 지장이 없고, 사이드바를 좁힌 만큼 본문이 그 폭을 가져간다. */
        [data-testid="stMainBlockContainer"] {{
            padding-left: 1.25rem !important;
            padding-right: 1.25rem !important;
            padding-top: 3rem !important;
        }}

        .st-key-home_navigation a,
        .st-key-home_navigation a p {{
            font-size: 1.5rem;
            font-weight: 700;
        }}
        /* HOME 은 누르지 않았을 때도 보여야 한다. 다른 항목처럼 납작하게 두면 글자만
           클 뿐 "여기로 돌아온다" 가 읽히지 않는다. 옅은 틴트와 ACCENT 테두리로 윤곽선
           버튼을 만들고, 지금 HOME 에 있으면 아래 융기 규칙이 그 위에 얹혀 채워진 모양이
           된다 — 윤곽선에서 채움으로 가는 단계라 둘이 경쟁하지 않는다.

           `:hover` 를 같이 적는 이유는 아래 활성 규칙과 같다. Streamlit 의 emotion
           `:hover` (0,2,0) 가 클래스 하나뿐인 선택자를 이긴다. */
        .st-key-home_navigation a,
        .st-key-home_navigation a:hover,
        .st-key-home_navigation a:focus-visible {{
            justify-content: center;
            border-color: {tokens.ACCENT};
            /* 단색 틴트는 「누를 수 있는 것」에서 멈춘다. 위가 진하고 아래가 밝으면 맨
               위 칸이 「돌아오는 자리」로 읽힌다. */
            background: linear-gradient(
                180deg,
                {tokens.NAV_HOME_TINT_STRONG} 0%,
                {tokens.SURFACE} 100%
            );
        }}
        .st-key-home_navigation a p {{
            text-align: center;
            color: {tokens.ACCENT};
        }}
        /* 아이콘을 더하기 전에는 전 페이지 중 HOME 만 아이콘이 없어 맨 위가 비어 보였다. */
        .st-key-home_navigation a [data-testid="stIconMaterial"] {{
            color: {tokens.ACCENT};
        }}

        /* 지금 보고 있는 페이지를 **융기**로 알린다. Streamlit 이 주는 활성 표시는 알파
           0.15 의 흐린 회색 하나뿐이라 사실상 보이지 않는다.

           이 앱에는 그림자가 이 규칙 말고 한 군데도 없다. 그래서 사이드바에서만 쓰면
           장식이 아니라 신호가 된다 — 떠 있는 것이 지금 있는 곳이다. */
        {NAV_LINK} {{
            border: 1px solid transparent;
            /* 활성 막대가 설 자리. 막대가 없는 링크도 같은 여백을 가져야 라벨이 한 줄로
               선다. 네 변을 모두 적는다 — 세 변만 적으면 나머지 한 변이 Streamlit 기본값
               으로 남아 좌우가 어긋난다. */
            position: relative;
            padding: 0.2rem 0.5rem 0.2rem 0.75rem;
            transition:
                transform 140ms ease,
                box-shadow 140ms ease,
                background-color 140ms ease;
        }}
        {NAV_LINK}:hover {{
            transform: translateY(-1px);
            box-shadow: 0 2px 6px {tokens.NAV_SHADOW};
        }}
{active_nav_style}

        {group_title_selectors} {{
            font-size: 1.15rem;
            font-weight: 700;
        }}

        /* 여백만으로는 어디까지가 하위인지 보이지 않는다. 하위가 여섯인 그룹에서 특히
           그렇다. 들여쓰기 1rem 을 **컨테이너와 링크가 나눠 갖고** 그 경계에 선을 긋는다.
           한쪽만 고치면 두 번 들여써져 오른쪽이 잘리므로 두 규칙을 함께 본다. */
        {subpage_box_selectors} {{
            border-left: 1px solid {tokens.BORDER};
            margin-left: 0.5rem;
            padding-left: 0.5rem;
            /* 왼쪽으로 민 만큼 폭에서 빼지 않으면 오른쪽이 상자 안쪽 선을 넘어간다. */
            width: calc(100% - 0.5rem);
        }}
        {subpage_selectors} {{
            margin-left: 0;
            width: 100%;
        }}

        /* 박스 위쪽만 한 단계 눌러 칠한다. 제목이 앉은 자리가 「머리칸」으로 읽혀 박스가
           단순한 테두리가 아니라 카드가 된다. 배경은 테두리를 그리는 요소 자신에게 주므로
           둥근 모서리에서 잘린다. */
        {group_box_selectors} {{
            background: linear-gradient(
                180deg,
                {tokens.SURFACE_PAGE} 0,
                {tokens.SURFACE} 2.1rem
            );
        }}

        /* 사이드바를 촘촘하게. 기본 세로 간격은 본문 기준이라 박스가 예닐곱 개 쌓이는
           사이드바에서는 스크롤만 길어진다. */
        [data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] {{
            gap: 0.42rem;
        }}
        /* 세로를 반으로 줄이면 가로도 같은 비율로 줄여야 상자가 납작해 보이지 않는다.
           다만 1:1 로 맞추지는 않는다 — 글은 가로로 읽으므로 좌우에 조금 더 남긴다.
           기본 16px 대비 세로 0.52배, 가로 0.66배다. */
        {group_box_selectors},
        .st-key-{SCENARIO_BOX_KEY},
        .st-key-{MONTH_BOX_KEY},
        .st-key-{ADMIN_BOX_KEY} {{
            padding: 0.55rem 0.7rem;
        }}
        /* 링크가 하나뿐인 박스는 세로 여백을 더 줄인다. 여러 줄이 쌓인 박스에서 숨통이
           되던 여백이, 한 줄짜리 박스에서는 그냥 빈자리로 남는다. 좌우는 그대로 둬야
           모든 박스의 글자가 한 세로선에 선다. */
        {solo_box_selectors} {{
            padding-top: 0.3rem;
            padding-bottom: 0.3rem;
        }}
        /* HOME 과 첫 그룹 박스 사이만 한 칸 더 띄운다. HOME 은 상자가 아니라 「돌아오는
           자리」라 아래 목록과 같은 간격으로 붙어 있으면 목록의 첫 항목처럼 읽힌다. */
        [data-testid="stLayoutWrapper"]:has(> .st-key-home_navigation) {{
            margin-bottom: 0.45rem;
        }}
        /* HOME 만 상자가 없어 테두리가 바깥 끝에 붙었다. 다른 링크의 테두리는 상자 안쪽
           여백만큼 들어와 있어, 같은 링크인데 HOME 만 혼자 넓어 보였다. 같은 만큼 들여
           모든 링크 테두리를 한 선에 세운다. */
        /* HOME 은 상자 안에 든 링크가 아니라 **상자 자리에 선 링크**다. 그래서 폭을
           맞출 상대는 상자 안쪽 링크가 아니라 아래 그룹 상자들의 테두리다 — 들여쓰면
           맨 위 칸만 혼자 짧아 보인다. 여백을 주지 않아 상자와 같은 20~300 을 쓴다. */
        .st-key-home_navigation {{
            padding-left: 0;
            padding-right: 0;
        }}

        /* Admin Area 는 **언제나 맨 아래**다. 페이지가 자기 사이드바 요소를 그리는 것은
           `navigation.run()` 안이라 파이썬 차례로는 뒤에 둘 수 없다 — HOME 의 「B/N 집계
           공정」 상자가 그래서 Admin 아래에 붙었다. 세로 흐름에서 자리만 마지막으로 민다.
           `order` 는 **flex 항목**이 받아야 한다. `.st-key-*` 는 그 한 겹 안쪽이라 거기에
           주면 아무 일도 일어나지 않는다(형제가 자기 자신뿐이다). */
        [data-testid="stLayoutWrapper"]:has(> .st-key-{ADMIN_BOX_KEY}) {{
            order: 99;
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
        with st.sidebar.container(border=True, key=f"{group.slug}_box"):
            with st.container(key=f"{group.slug}_navigation"):
                st.page_link(group.main, width="stretch")
            if not group.subpages:
                continue
            with st.container(key=f"{group.slug}_subpages"):
                for page in group.subpages:
                    st.page_link(page, width="stretch")

    render_scenario_controls()

    with st.sidebar.container(border=True, key=MONTH_BOX_KEY):
        # 적용 범위는 제목 **옆**이다. 아래에 한 줄로 두면 두 칸짜리 피커 밑에 글줄이
        # 하나 더 붙어 상자가 세 줄이 된다. 자리는 여기서 잡고, 값은 페이지가 계산을
        # 끝낸 뒤 `show_applied_month_range` 가 채운다 — 좁혀진 범위는 그때 정해진다.
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            # 다른 화면과 같은 낱말을 쓴다. 여기만 "조회 기간" 으로 띄어져 있었다.
            st.markdown("#### :material/date_range: 조회기간", width="content")
            register_month_range_placeholder(st.empty())
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
        show_applied_month_range(
            int(selected_start_label.replace("-", "")),
            int(selected_end_label.replace("-", "")),
        )

    # 관리 기능이라 조회 컨트롤보다 아래, 사이드바에서 가장 먼 곳에 둔다. 페이지가 자기
    # 사이드바 요소를 더하는 것은 `navigation.run()` 안이라 파이썬 차례로는 뒤에 둘 수
    # 없다 — 맨 아래를 지키는 것은 위 CSS 의 `order` 다.
    with st.sidebar.container(border=True, key=ADMIN_BOX_KEY):
        with st.container(key="admin_area_navigation"):
            st.page_link(pages.admin_area, width="stretch")
            # VOC 는 계산 화면이 아니라 사람이 쓰는 자리다. 계산 그룹 어디에도 속하지 않아
            # 이 상자에 함께 세운다 — 「말할 곳」을 찾는 사람은 맨 아래를 본다. **하위가
            # 아니라 같은 층위**다. 관리 화면과 게시판은 서로를 포함하지 않으므로 들여쓰기도
            # 계층선도 두지 않는다.
            for page in pages.admin_box_pages:
                st.page_link(page, width="stretch")

    navigation.run()
