# Purpose: Streamlit 앱의 공식 시나리오 활성화, 공통 사이드바·조회기간과 페이지 탐색을 구성한다.

import streamlit as st

from capa_simulation.components.app_header import render_app_header
from capa_simulation.components.month_range_picker import render_month_range_picker
from capa_simulation.components.scenario_status import (
    SCENARIO_BOX_KEY,
    render_scenario_controls,
)
from capa_simulation.components.theme_toggle import render_theme_toggle
from capa_simulation.design import theme, tokens
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
    BOTTLENECK_BOX_KEY,
    register_month_range_placeholder,
    show_applied_month_range,
)
from capa_simulation.sync_boot import enable_sync_state_if_managed, heartbeat_if_managed

# CSS 선택자 여러 개를 한 규칙에 묶을 때 쓰는 구분자. 규칙 안 들여쓰기까지 붙여 둔다.
_SELECTOR_JOINER = ",\n        "

# 사이드바 박스 CSS 훅. 여백을 좁히는 규칙과 Admin 의 `order` 가 이 key 를 읽는다.
MONTH_BOX_KEY = "sidebar_month_box"
# 그룹 상자 **안**에서 그 그룹의 대표 페이지를 부르는 이름. 머리글이 이미 그룹 이름을
# 말하므로 안에서까지 되풀이하지 않고 그 그룹 안에서의 자리로 부른다.
GROUP_MAIN_LABEL = "현황 요약"
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
# 이 실행이 쓸 테마를 먼저 정한다. **토큰을 하나라도 읽기 전**이어야 한다 — 색을 읽는
# 쪽은 여기서 담아 둔 값을 본다. 바뀌었으면 그 세션의 Figure 캐시도 여기서 비운다.
theme.begin_run()

# managed 모드에서만 동기화 표시를 켠다. local 모드(개발 PC·기본값)에서는 아무 일도 하지
# 않으므로 이 호출이 있어도 동작이 바뀌지 않는다.
enable_sync_state_if_managed()
# 앱이 이 PC 에서 돌고 있다는 표시. DuckDB 는 프로세스 배타 잠금이라 앱이 떠 있는 동안
# 동기화 스크립트는 DB 를 열지 못한다 — 그 사실을 사람 말로 알릴 근거가 이 기록이다.
# 10초에 한 번만 실제로 쓴다.
heartbeat_if_managed()

# rerun 한 번 동안 시나리오 DB 인스턴스를 잡아 둔다. 사이드바가 rerun 마다 여는 연결 3개가
# 각자 인스턴스를 다시 만들지 않게 하는 것이 전부이고, rerun 이 끝나면 풀린다.
with pinned_connections(DUCKDB_PATH):
    try:
        bootstrap_latest_official_scenario(str(DUCKDB_PATH.resolve()))
    except Exception as exc:  # 어떤 실패든 원인을 읽을 수 있게 바꿔야 한다
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
    # **하위가 있는 그룹만 상자를 갖는다.** 나머지는 평평한 링크라 걸 것이 없다.
    boxed_groups = [group for group in pages.groups if group.subpages]
    # 링크 하나만 든 상자. 확장 패널과 달리 제 여백을 갖지 않으므로 아래 여백 규칙이
    # 필요하고, 한 줄뿐이라 세로는 한 번 더 줄인다.
    solo_box_selectors = _SELECTOR_JOINER.join(
        f".st-key-{group.slug}_box" for group in pages.groups if not group.subpages
    )
    solo_title_selectors = _SELECTOR_JOINER.join(
        f".st-key-{group.slug}_box a p" for group in pages.groups if not group.subpages
    )
    # 상자 머리글. 전에는 상자 안 첫 링크가 그룹 이름을 달았고 지금은 확장 패널의 요약
    # 줄이 단다. 자리는 바뀌었어도 옆 상자의 제목과 같은 무게로 읽혀야 한다.
    #
    # **글자는 `summary` 가 아니라 그 안의 `p` 가 정한다.** 요약 줄에 크기를 줘 봐야
    # 안쪽 마크다운 문단이 제 값(0.875rem)으로 덮는다 — 실제로 그렇게 두었더니 그룹
    # 이름만 12.25px 로 작고 가늘게 남았다.
    group_title_selectors = _SELECTOR_JOINER.join(
        f'.st-key-{group.slug}_box summary [data-testid="stMarkdownContainer"] p'
        for group in boxed_groups
    )
    # 제목을 가진 조회 상자 셋. 상자마다 제목 `h4` 는 하나뿐이라 안쪽을 더 좁히지 않는다.
    # 뒤에 붙일 부분까지 **선택자마다** 넣어 잇는다 — 목록을 먼저 잇고 뒤에 `h4` 를 붙이면
    # `A, B h4` 가 되어 마지막 하나에만 걸린다.
    _TITLED_BOXES = (SCENARIO_BOX_KEY, MONTH_BOX_KEY, BOTTLENECK_BOX_KEY)

    def _box_title(tail: str) -> str:
        return _SELECTOR_JOINER.join(f".st-key-{key} {tail}" for key in _TITLED_BOXES)

    box_headings = _box_title("h4")
    box_heading_wrappers = _box_title('[data-testid="stMarkdownContainer"]:has(> h4)')
    # 사이드바 안의 페이지 링크 전부. 본문에도 `stPageLink` 가 있을 수 있어 사이드바로 좁힌다.
    NAV_LINK = '[data-testid="stSidebarContent"] [data-testid="stPageLink-NavLink"]'
    # HOME 링크 하나. **활성 규칙보다 특정도가 높아야** 한다 — HOME 에 있을 때 활성 규칙의
    # `border-color`·`background-color` 가 그라데이션 테두리를 불투명하게 덮기 때문이다.
    # 활성 선택자가 속성 셋(0,3,0)이라 여기에 요소 하나를 더해 (0,3,1) 로 올린다.
    HOME_LINK = (
        '[data-testid="stSidebarContent"] .st-key-home_navigation'
        ' a[data-testid="stPageLink-NavLink"]'
    )
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
        }}
        {HOME_LINK}::before {{
            content: none;
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
            /* 1.5rem 은 이 칸만 52px 로 키워 아래 상자들(35px)보다 한 뼘 높았다. 「돌아오는
               자리」라는 것은 그라데이션 테두리가 이미 말하므로 크기까지 들 필요가 없다. */
            font-size: 1.15rem;
            font-weight: 700;
            line-height: 1.3;
        }}
        /* 글자를 줄인 만큼 칸도 납작해져 아래 상자들보다 오히려 작아졌다. 여백으로 다시
           키우되 상자(35px)보다 한 뼘만 높은 40px 에 세운다 — 「돌아오는 자리」는 남기고
           예전의 52px 처럼 혼자 솟지는 않는다. */
        {HOME_LINK} {{
            padding-top: 0.5rem;
            padding-bottom: 0.5rem;
        }}
        /* HOME 은 누르지 않았을 때도 보여야 한다. 다른 항목처럼 납작하게 두면 글자만
           클 뿐 "여기로 돌아온다" 가 읽히지 않는다.

           테두리에만 그라데이션을 남긴다. 한 요소에 배경 두 겹을 깔고 하나는 `padding-box`
           로 면을, 하나는 `border-box` 로 테두리를 맡기는 방식이다 — `border-color` 로는
           그라데이션을 줄 수 없어서 테두리를 투명하게 두고 그 자리에 두 번째 배경이
           비치게 한다. 두 배경의 차례를 바꾸면 면이 테두리를 덮는다.

           `:hover` 를 같이 적는 이유는 아래 활성 규칙과 같다. Streamlit 의 emotion
           `:hover` (0,2,0) 가 클래스 하나뿐인 선택자를 이긴다. */
        {HOME_LINK},
        {HOME_LINK}:hover,
        {HOME_LINK}:focus-visible {{
            position: relative;
            overflow: hidden;
            justify-content: center;
            border: 2px solid transparent;
            background:
                linear-gradient({tokens.SURFACE_PAGE}, {tokens.SURFACE_PAGE}) padding-box,
                linear-gradient(
                    100deg,
                    {tokens.ACCENT},
                    {tokens.BORDER} 45%,
                    {tokens.ACCENT}
                ) border-box;
        }}
        {HOME_LINK} p {{
            text-align: center;
            color: {tokens.ACCENT};
        }}
        /* 마우스가 스칠 때 광택 띠가 한 번 지나간다. 평소에는 왼쪽 밖에 세워 두므로
           가만히 있는 화면에서는 아무것도 움직이지 않는다. */
        {HOME_LINK}::after {{
            content: "";
            position: absolute;
            inset: 0;
            transform: translateX(-120%);
            background: linear-gradient(
                100deg,
                transparent 0%,
                {tokens.NAV_HOME_SHEEN} 50%,
                transparent 100%
            );
        }}
        {HOME_LINK}:hover::after {{
            animation: capa-home-sheen 900ms ease-out 1;
        }}
        @keyframes capa-home-sheen {{
            to {{
                transform: translateX(120%);
            }}
        }}
        /* 움직임을 줄여 달라고 한 사용자에게는 띠를 보내지 않는다. */
        @media (prefers-reduced-motion: reduce) {{
            {HOME_LINK}:hover::after {{
                animation: none;
            }}
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

        /* 그룹 이름을 옆 상자의 제목(h4·1rem·700)과 같은 선에 세운다. */
        {group_title_selectors} {{
            font-size: 1rem;
            font-weight: 700;
        }}
        /* **펼친 요약 줄의 면색은 덮지 못한다 — 시도했고 안 됐다.** Streamlit 이 펼침
           상태에만 붙이는 클래스로 흰 면을 아주 살짝 눌러 칠하는데, 선택자 특정도를 올려도
           `!important` 를 붙여도, 브라우저에서 같은 선택자를 직접 주입해도 계산값이
           바뀌지 않았다. 흰 면 위 1% 남짓의 차이라 접힌 그룹·다른 상자와 나란히 두면
           거의 보이지 않는다. 여기 적어 두는 것은 **다음 사람이 같은 길을 다시 파지
           않게** 하기 위해서다. 없애야 한다면 Streamlit 쪽 판올림을 기다리는 편이 낫다. */

        /* 하위를 가르던 세로선은 없앴다. 그 일을 이제 **확장 패널 자신이** 한다 —
           펼친 것과 접힌 것이 경계를 대신 말하므로, 선을 더 그으면 안쪽이 두 번
           들여써진다. */

        /* 그룹 상자에는 배경을 칠하지 않는다. 상자였을 때는 제목 자리를 「머리칸」으로
           읽히게 하려고 위쪽만 한 단계 눌러 칠했는데, 지금은 그 자리가 **확장 패널의
           `summary`** 이고 Streamlit 이 이미 한 단계 눌러 칠한다. 덧칠하면 테두리를 가진
           확장 패널 **바깥** 래퍼에 얹혀, 모서리가 각진 띠가 한 겹 더 둘러진다. */

        /* 사이드바를 촘촘하게. 기본 세로 간격은 본문 기준이라 박스가 예닐곱 개 쌓이는
           사이드바에서는 스크롤만 길어진다. */
        [data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] {{
            gap: 0.42rem;
        }}
        /* 세로를 반으로 줄이면 가로도 같은 비율로 줄여야 상자가 납작해 보이지 않는다.
           다만 1:1 로 맞추지는 않는다 — 글은 가로로 읽으므로 좌우에 조금 더 남긴다.
           기본 16px 대비 세로 0.52배, 가로 0.66배다. */
        {solo_box_selectors},
        .st-key-{SCENARIO_BOX_KEY},
        .st-key-{MONTH_BOX_KEY},
        .st-key-{BOTTLENECK_BOX_KEY},
        .st-key-{ADMIN_BOX_KEY} {{
            padding: 0.55rem 0.7rem;
        }}
        /* 링크 하나뿐인 상자는 **좌우 여백을 주지 않는다.** 그룹 상자는 안쪽 확장 패널이
           제 들여쓰기를 갖는데 이쪽은 링크가 바로 들어가서, 상자에까지 여백을 주면 글자가
           그룹 제목보다 10px 오른쪽으로 밀린다(실측 아이콘 42 대 32). 세로는 줄여 접힌
           그룹과 같은 높이로 맞춘다. */
        {solo_box_selectors} {{
            /* 세로 0.15rem 이 접힌 그룹 상자와 같은 35px 을 만든다(실측). */
            padding: 0.15rem 0;
        }}
        /* 그 링크는 그룹 제목과 **같은 층위**다. 하위 페이지가 아니라 최상위 항목이므로
           옆 상자의 제목과 같은 무게로 읽혀야 한다. */
        {solo_title_selectors} {{
            font-size: 1rem;
            font-weight: 700;
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

        /* 제목 옆에 붙인 표기(공식버전 배지·적용기간 안내)가 제목보다 위에 떠 있었다.
           `vertical_alignment="center"` 는 제대로 걸려 있다 — 어긋난 것은 제목 쪽이다.
           Streamlit 의 제목은 **두 값이 짝을 이룬다**: `h4` 가 `padding: 7.5px 0 15px`
           이고 감싸는 `stMarkdownContainer` 가 `margin-bottom: -15px` 로 그만큼 도로
           당긴다. 세로로 쌓을 때는 서로 상쇄되지만, flex 가 가운데 맞추는 것은 **패딩까지
           포함한 상자**라 글자만 아래로 (15-7.5)/2 만큼 밀렸다.
           한쪽만 풀면 상자가 18-15=3px 로 찌부러져 더 어긋난다. 둘을 함께 풀어야 상자가
           곧 글줄이 되어 두 글자가 같은 높이에 선다. 박스 안 제목에만 걸고 본문 `h4` 의
           여백은 그대로 둔다.

           옆에 표기가 없는 B/N 집계 공정 제목도 같은 규칙을 받는다. 세로로 쌓일 때 두 값은
           서로 상쇄되지만 **위쪽 7.5px 은 남아** 그 상자만 제목이 아래로 처져 있었다. */
        {box_headings} {{
            padding-top: 0;
            padding-bottom: 0;
        }}
        {box_heading_wrappers} {{
            margin-bottom: 0;
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
    # 헤더 오른쪽 Deploy 왼쪽 자리에 밝게/어둡게 버튼을 얹는다. Streamlit 이 테마를
    # 기억하는 자리를 그대로 쓰므로 위젯과 우리 Figure 가 함께 바뀐다.
    render_theme_toggle()
    with st.sidebar.container(key="home_navigation"):
        st.page_link(pages.home, width="stretch")

    # 박스 목록은 `navigation.SIDEBAR_GROUPS` 하나에서 나온다. 위 CSS 선택자도 같은 선언을
    # 읽으므로, 그룹을 더할 때 이 파일에서 고칠 것이 없다.
    for group in pages.groups:
        # 하위가 없어도 **상자에 넣는다.** 묶을 것이 없으니 테두리가 필요 없다고 봤는데,
        # 사이드바에 상자가 다섯이고 이 둘만 맨몸으로 서니 목록이 두 층으로 읽혔다.
        # 테두리는 「묶음」만 뜻하는 것이 아니라 **한 칸**이라는 뜻이기도 하다.
        if not group.subpages:
            with st.sidebar.container(border=True, key=f"{group.slug}_box"):
                st.page_link(group.main, width="stretch")
            continue
        # 지금 보고 있는 페이지가 든 그룹만 편다. `url_path` 는 `st.navigation()` 이
        # 돌아야 채워지므로(그 전에는 `AttributeError`) 이 자리가 반드시 그 뒤여야 한다.
        group_paths = {page.url_path for page in (group.main, *group.subpages)}
        with st.sidebar.expander(
            group.main.title,
            expanded=navigation.url_path in group_paths,
            icon=group.main.icon,
            # `key` 는 곧 `st-key-…` 클래스다. 상자였을 때 걸어 둔 CSS 훅이 그대로 산다.
            key=f"{group.slug}_box",
        ):
            st.page_link(group.main, label=GROUP_MAIN_LABEL, width="stretch")
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
    # **테두리를 두르지 않는다.** 관리는 계산 흐름 밖이라 다른 상자와 나란히 서면 같은
    # 층위로 읽힌다. 캡션 한 줄이 「여기부터는 성격이 다르다」를 대신 말한다.
    with st.sidebar.container(key=ADMIN_BOX_KEY):
        st.caption("관리")
        with st.container(key="admin_area_navigation"):
            st.page_link(pages.admin_area, width="stretch")
            # VOC 는 계산 화면이 아니라 사람이 쓰는 자리다. 계산 그룹 어디에도 속하지 않아
            # 이 상자에 함께 세운다 — 「말할 곳」을 찾는 사람은 맨 아래를 본다. **하위가
            # 아니라 같은 층위**다. 관리 화면과 게시판은 서로를 포함하지 않으므로 들여쓰기도
            # 계층선도 두지 않는다.
            for page in pages.admin_box_pages:
                st.page_link(page, width="stretch")

    navigation.run()
