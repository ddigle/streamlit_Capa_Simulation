# Purpose: 사이드바 그룹·활성 페이지와 테마 토큰을 HTML 스타일시트 문자열로 조립한다.

from __future__ import annotations

from collections.abc import Sequence

from capa_simulation.design import tokens
from capa_simulation.navigation import SidebarGroup, SidebarGroupSpec

# 규칙 안 들여쓰기도 선택자 사이에 유지한다.
_SELECTOR_JOINER = ",\n        "

# 사이드바 세로 블록의 칸 사이. 적용 기간 오버레이가 이 값을 그대로 상쇄해야 요약 줄
# 위에 올라앉으므로 두 곳이 같은 상수를 본다.
_SIDEBAR_BLOCK_GAP = "0.42rem"
# **적용 기간 오버레이의 좌표 네 개를 여기 모아 둔다.** 요약 줄 위에 글자를 얹는 일이라
# 브라우저에서 재서 고치게 되는데, 규칙 안에 흩어 두면 어디를 고쳐야 하는지 매번 찾는다.
# 위: 요약 줄(약 2.4rem) 안에서 글줄을 세로 가운데로. 오른쪽: 펼침 화살표를 비운 폭.
# 왼쪽: 「조회기간」 제목 뒤. 왼쪽이 있어야 긴 문구가 제목을 덮지 않고 말줄임이 된다.
_APPLIED_OVERLAY_TOP = "0.62rem"
_APPLIED_OVERLAY_RIGHT = "2.2rem"
_APPLIED_OVERLAY_LEFT = "7.5rem"


def build_sidebar_stylesheet(
    groups: Sequence[SidebarGroup | SidebarGroupSpec],
    active_href: str,
    *,
    scenario_box_key: str,
    month_box_key: str,
    month_applied_key: str,
    bottleneck_box_key: str,
    admin_box_key: str,
) -> str:
    """현재 실행의 테마를 읽어 CSS를 만든다. 위젯 생성·상태 변경·HTML 주입은 하지 않는다.

    호출부는 ``theme.begin_run()`` 뒤에 호출하며 컨테이너 키는 각 소유자가 넘긴다.
    """
    # 선택자도 같은 선언에서 낸다. 손으로 적으면 그룹을 더할 때 한쪽만 고치게 된다.
    # **하위가 있는 그룹만 상자를 갖는다.** 나머지는 평평한 링크라 걸 것이 없다.
    boxed_groups = [group for group in groups if group.subpages]
    # 링크 하나만 든 상자. 확장 패널과 달리 제 여백을 갖지 않으므로 아래 여백 규칙이
    # 필요하고, 한 줄뿐이라 세로는 한 번 더 줄인다.
    solo_box_selectors = _SELECTOR_JOINER.join(
        f".st-key-{group.slug}_box" for group in groups if not group.subpages
    )
    solo_title_selectors = _SELECTOR_JOINER.join(
        f".st-key-{group.slug}_box a p" for group in groups if not group.subpages
    )
    # 상자 머리글. 전에는 상자 안 첫 링크나 `h4` 제목이 이름을 달았고 지금은 **전부**
    # 확장 패널의 요약 줄이 단다. 페이지 그룹과 조회 컨트롤 넷이 한 양식이라 같은 규칙
    # 하나를 본다 — 무게가 갈리면 통일한 뜻이 없어진다.
    #
    # **글자는 `summary` 가 아니라 그 안의 `p` 가 정한다.** 요약 줄에 크기를 줘 봐야
    # 안쪽 마크다운 문단이 제 값(0.875rem)으로 덮는다 — 실제로 그렇게 두었더니 그룹
    # 이름만 12.25px 로 작고 가늘게 남았다.
    summary_box_keys = (
        *(f"{group.slug}_box" for group in boxed_groups),
        scenario_box_key,
        month_box_key,
        bottleneck_box_key,
        admin_box_key,
    )
    group_title_selectors = _SELECTOR_JOINER.join(
        f'.st-key-{key} summary [data-testid="stMarkdownContainer"] p' for key in summary_box_keys
    )
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
    return f"""
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
            gap: {_SIDEBAR_BLOCK_GAP};
        }}
        /* 조회 컨트롤 넷에 주던 `padding: 0.55rem 0.7rem` 은 없앴다. 상자였을 때는 안쪽
           위젯을 들여놓는 여백이었는데, 확장 패널은 제 여백을 갖는다 — 남겨 두면 그 여백이
           **요약 줄과 테두리까지** 밀어 접힌 줄이 그룹 상자보다 안쪽으로 들어간다. */
        /* 링크 하나뿐인 상자는 **좌우 여백을 주지 않는다.** 그룹 상자는 확장 패널이 제
           들여쓰기를 갖는데 이쪽은 링크가 바로 들어가서, 상자에까지 여백을 주면 글자가
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

        /* 공식버전 배지는 요약 줄의 **오른쪽 끝**이다. 제목은 다른 상자의 페이지명과 같은
           왼쪽 끝에 남는다. 확장 패널의 제목은 문자열 하나라 그 안에서 좌우로 밀 수 없어
           여기서 민다 — 요약 줄의 마크다운 문단을 flex 로 펴고 배지만 오른쪽으로 보낸다.
           제목 길이가 달라져도 배지 자리는 흔들리지 않는다. */
        .st-key-{scenario_box_key} summary [data-testid="stMarkdownContainer"] p {{
            display: flex;
            align-items: center;
            gap: 0.4rem;
        }}
        .st-key-{scenario_box_key} summary [data-testid="stMarkdownContainer"] p
            > [data-testid="stMarkdownBadge"] {{
            margin-left: auto;
        }}

        /* 적용 기간을 조회기간 상자의 **요약 줄 위로 얹는다.** 그 값은 페이지가 계산을
           끝낸 뒤에야 정해져 제목 문자열에 넣을 수 없다(`app.py` 가 이유를 적어 뒀다).
           자리표시자는 상자 **바로 앞**에 서고, 이 규칙이 그 칸의 높이를 0 으로 눌러
           세로 흐름에서 지운 뒤 글자만 요약 줄 위로 내린다. 접히든 펴지든 요약 줄은 늘
           이 칸 바로 아래라 자리가 흔들리지 않는다. 칸 사이 간격만큼 도로 당겨야 글자가
           요약 줄 한가운데에 선다. */
        [data-testid="stLayoutWrapper"]:has(> .st-key-{month_applied_key}) {{
            position: relative;
            z-index: 2;
            height: 0;
            min-height: 0;
            margin-bottom: -{_SIDEBAR_BLOCK_GAP};
            overflow: visible;
            /* 요약 줄을 누르는 일이 더 잦다. 글자 칸 말고는 클릭이 그대로 통과한다. */
            pointer-events: none;
        }}
        [data-testid="stLayoutWrapper"]:has(> .st-key-{month_applied_key})
            [data-testid="stCaptionContainer"] {{
            position: absolute;
            top: {_APPLIED_OVERLAY_TOP};
            right: {_APPLIED_OVERLAY_RIGHT};
            left: {_APPLIED_OVERLAY_LEFT};
            margin: 0;
            text-align: right;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            /* `help` 툴팁이 떠야 해서 글자 칸만 클릭을 받는다. */
            pointer-events: auto;
        }}

        /* 관리는 **계산 흐름 밖**이다. 접는 장치는 다른 상자와 같게 주되 테두리를 지우고
           요약 줄 글자를 캡션 색으로 눌러 층위를 가른다 — 캡션 한 줄이 하던 말을 이제
           테두리 없음과 글자색이 한다. */
        .st-key-{admin_box_key} details {{
            border: none;
            background: transparent;
        }}
        .st-key-{admin_box_key} summary [data-testid="stMarkdownContainer"] p {{
            color: {tokens.TEXT_MUTED};
        }}

        /* Admin Area 는 **언제나 맨 아래**다. 페이지가 자기 사이드바 요소를 그리는 것은
           `navigation.run()` 안이라 파이썬 차례로는 뒤에 둘 수 없다 — HOME 의 「B/N 집계
           공정」 상자가 그래서 Admin 아래에 붙었다. 세로 흐름에서 자리만 마지막으로 민다.
           `order` 는 **flex 항목**이 받아야 한다. 상자(`st.container`)였을 때는 `.st-key-*`
           가 그 한 겹 안쪽이라 바깥 래퍼에 줘야 했는데, **확장 패널은 `.st-key-*` 요소
           자신이 flex 항목**이다(프런트엔드가 확장 패널일 때만 래퍼에 그 클래스를 붙인다).
           둘 다 적어 둔다 — 맞는 쪽이 걸리고 나머지는 헛돌 뿐이다. */
        [data-testid="stLayoutWrapper"]:has(> .st-key-{admin_box_key}),
        .st-key-{admin_box_key} {{
            order: 99;
        }}
        </style>
        """
