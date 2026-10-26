# Purpose: 사이드바 그룹·활성 페이지와 테마 토큰을 HTML 스타일시트 문자열로 조립한다.

from __future__ import annotations

from collections.abc import Sequence

from capa_simulation.components.app_credits import APP_CREDITS_KEY
from capa_simulation.components.condition_field import (
    FIELD_KEY_PREFIX,
    NAME_ROW_KEY_PREFIX,
    PENDING_SUFFIX,
)
from capa_simulation.design import tokens
from capa_simulation.navigation import (
    CONDITIONS_SECTION,
    SIDEBAR_SECTIONS,
    SidebarGroup,
    SidebarGroupSpec,
)
from capa_simulation.sidebar_status import (
    CONDITION_CARD_PREFIX,
    CONDITION_DIALOG_SINK_KEY,
    CONDITIONS_BOX_KEY,
    SIDEBAR_TOGGLE_SINK_KEY,
)

# 규칙 안 들여쓰기도 선택자 사이에 유지한다.
_SELECTOR_JOINER = ",\n        "
# 화면 조건 카드 전부. 페이지마다 카드 이름이 달라 key 를 인자로 받을 수 없으므로 접두어로
# 고른다 — Streamlit 은 `key` 를 `st-key-<key>` 클래스로 단다.
_CONDITION_CARDS = f'[class*="st-key-{CONDITION_CARD_PREFIX}"]'

# 사이드바 세로 블록의 칸 사이.
_SIDEBAR_BLOCK_GAP = "0.42rem"
# 조건 패널(`CONDITIONS_BOX_KEY`)과 그 안의 필드. 패널 안 줄 사이는 칸 사이보다 한 뼘 넓고, 한 필드
# 안(이름 줄 → 값 칸)은 바짝 붙인다 — 이름이 어느 칸의 것인지 자리로 읽힌다.
_CONDITIONS_PANEL = f".st-key-{CONDITIONS_BOX_KEY}"
_CONDITION_FIELDS = f'[class*="st-key-{FIELD_KEY_PREFIX}"]'
_CONDITION_NAME_ROWS = f'[class*="st-key-{NAME_ROW_KEY_PREFIX}"]'
_PANEL_ROW_GAP = "0.6rem"
_FIELD_INNER_GAP = "0.2rem"
# **상자 오른쪽 끝의 표식.** 누르면 무슨 일이 일어나는지를 오른쪽 끝 기호가 늘 보이게 말한다.
# 곧바로 다른 화면으로 가는 링크 상자는 `→`(`arrow_forward`), 이 자리에서 펼쳐지는 확장 패널은
# `⌄`(`expand_more`, 펴면 뒤집힌다), 이 자리에서 **팝업이 뜨는** 조건 칸은 `⇕`(`unfold_more`,
# 고르는 칸의 관례 — 2026-10-10 사용자 결정). `›` 는 Streamlit 이 hover 때 쓰는 글리프라 쓰지
# 않는다. 이 Streamlit 의 확장 패널은 제 아이콘을 **제목 왼쪽**에만 그리고 오른쪽은 비워 둔다(실측
# `stExpanderIcon` 32–46). 기호는 Streamlit 이 이미 불러 둔 Material Symbols 합자로 그린다.
_MARKER_FONT = '"Material Symbols Rounded"'
_LINK_MARKER_SIZE = "16px"
_SUMMARY_MARKER_SIZE = "18px"
_SUMMARY_MARKER_GAP = "0.25rem"
# 실행이 시작된 뒤 본문을 흐리기까지 기다리는 시간. 사이드바 상자 여닫기(빈 프래그먼트만 도는
# 실행)의 흐림 구간이 클릭 뒤 60~290ms 였다(실측) — 그보다 길게, 계산이 걸리는 재실행의 로딩
# 표시는 늦지 않게.
STALE_DIM_DELAY = "0.3s"
# 앱 정보 카드(`components/app_credits.py`)의 flex `order`. `Support`(99)보다 뒤라야 사이드바 맨
# 아래다. 카드 면을 좌우 여백까지 펴는 그림자 폭 — 스크롤 칸이 제 안쪽 여백 끝에서 잘라 주므로
# 그 여백(실측 17.5px)보다 넉넉하면 된다.
APP_CREDITS_ORDER = 100
_APP_CREDITS_BLEED = "3rem"


def lone_conditions_heading_selector() -> str:
    """「조회 조건」 제목 아래에 설 상자가 사이드바에 **하나도 없을 때만** 제목을 고르는 선택자.

    제목은 `app.py` 가 페이지보다 먼저, 늘 같은 자리에 세운다. 자기 조건 카드만 세우는 화면(VOC·
    Space 현황·가용설비 Main)이 카드를 그리기 전에 멈추는 드문 오류 경로(게시판·설비 DB 를 못
    읽음)에서는 제목만 덩그러니 남는데, 그것을 파이썬이 아니라 CSS 가 감춘다. 파이썬으로 제목을
    미뤘다 채우면(빈 칸 → 첫 카드가 채움) rerun 마다 그 사이 제목이 사라지고 아래 상자가 한 줄
    올라갔다 내려왔다(8543 실측 — Space·가용설비 rerun 마다 65~90ms, 카드가 26px 위아래로 튐).
    CSS 는 rerun 동안 지난 회차의 카드가 그대로 남아 있으므로 제목이 흔들리지 않고, 회차가 끝나
    카드가 정말 없을 때만 감춘다.

    제목 아래 상자는 통합 조건 패널(`CONDITIONS_BOX_KEY`)과 조건 카드 전부다. Streamlit 은 `key` 를
    `st-key-<key>` 클래스로 달고, 제목 컨테이너는 사이드바 세로 블록의 `stLayoutWrapper` 안에 서므로
    그 겉 칸째 감춰 간격도 남기지 않는다(겉 칸 구조가 바뀌어도 글자는 감추도록 제목 컨테이너 자신도
    함께 고른다).
    """
    content = ", ".join((_CONDITIONS_PANEL, _CONDITION_CARDS))
    root = f'[data-testid="stSidebarUserContent"]:not(:has({content}))'
    heading = f".st-key-{CONDITIONS_SECTION.key}"
    return _SELECTOR_JOINER.join(
        (f'{root} [data-testid="stLayoutWrapper"]:has(> {heading})', f"{root} {heading}")
    )


def build_sidebar_stylesheet(
    groups: Sequence[SidebarGroup | SidebarGroupSpec],
    active_href: str,
    *,
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
    # 확장 패널의 요약 줄이 단다. 페이지 그룹·`Support`·조건 카드가 한 양식이라 같은 규칙
    # 하나를 본다 — 무게가 갈리면 통일한 뜻이 없어진다.
    #
    # **글자는 `summary` 가 아니라 그 안의 `p` 가 정한다.** 요약 줄에 크기를 줘 봐야
    # 안쪽 마크다운 문단이 제 값(0.875rem)으로 덮는다 — 실제로 그렇게 두었더니 그룹
    # 이름만 12.25px 로 작고 가늘게 남았다.
    summary_box_keys = (
        *(f"{group.slug}_box" for group in boxed_groups),
        admin_box_key,
    )
    # 조건 카드도 같은 양식이다. key 대신 접두어 선택자 하나로 모든 카드를 부른다.
    summary_roots = (*(f".st-key-{key}" for key in summary_box_keys), _CONDITION_CARDS)
    group_title_selectors = _SELECTOR_JOINER.join(
        f'{root} summary [data-testid="stMarkdownContainer"] p' for root in summary_roots
    )
    # 페이지 그룹 상자의 제목만 한 줄로 두고 넘치면 말줄임한다. 조건 카드·`Support` 는 그대로
    # 접는다 — 조건 이름은 잘리면 어느 조건인지 못 읽는다.
    group_title_shells = [
        f'.st-key-{group.slug}_box summary [data-testid="stMarkdownContainer"]'
        for group in boxed_groups
    ]
    group_title_shell_selectors = _SELECTOR_JOINER.join(group_title_shells)
    group_title_line_selectors = _SELECTOR_JOINER.join(f"{shell} p" for shell in group_title_shells)
    # 구역 제목 줄. 선택자는 `navigation.SIDEBAR_SECTIONS` 선언에서 나온다 — 인자로 받지
    # 않는다. 제목을 그리는 쪽(`sidebar_status.render_sidebar_section`)도 같은 선언을 본다.
    section_selectors = _SELECTOR_JOINER.join(
        f".st-key-{section.key}" for section in SIDEBAR_SECTIONS
    )
    section_text_selectors = _SELECTOR_JOINER.join(
        f'.st-key-{section.key} [data-testid="stCaptionContainer"] p'
        for section in SIDEBAR_SECTIONS
    )
    section_title_selectors = _SELECTOR_JOINER.join(
        f'.st-key-{section.key} > [data-testid="stElementContainer"]:first-child'
        ' [data-testid="stCaptionContainer"] p'
        for section in SIDEBAR_SECTIONS
    )
    lone_conditions_heading_selectors = lone_conditions_heading_selector()
    # 곧바로 이동하는 링크 상자의 `→`. **그 상자 key 로 좁힌다** — 사이드바 링크 전체에 걸면
    # HOME 링크가 `::after` 로 그리는 광택 띠를 덮는다.
    solo_link_markers = [
        f'.st-key-{group.slug}_box a[data-testid="stPageLink-NavLink"]'
        for group in groups
        if not group.subpages
    ]
    solo_link_marker_selectors = _SELECTOR_JOINER.join(
        f"{link}::after" for link in solo_link_markers
    )
    # 지금 보고 있는 단독 링크에는 `→` 를 달지 않는다 — 가는 곳이 바로 여기다. 이것도 상자
    # key 로 좁힌다. HOME 의 `href` 는 빈 문자열이라 넓게 쓰면 HOME 에서 광택 띠를 지운다.
    solo_link_active_selectors = _SELECTOR_JOINER.join(
        f'{link}[href="{active_href}"]::after' for link in solo_link_markers
    )
    # 이 자리에서 펼쳐지는 상자 전부의 `⌄`. 페이지 그룹이든 조회 조건이든 `Support` 든 눌러서
    # 일어나는 일이 같으므로 같은 표식이다.
    summary_marker_selectors = _SELECTOR_JOINER.join(
        f"{root} details > summary::after" for root in summary_roots
    )
    summary_marker_open_selectors = _SELECTOR_JOINER.join(
        f"{root} details[open] > summary::after" for root in summary_roots
    )
    # 지금 화면이 읽는 조건 카드(접히는 상자). 구역 제목 아래, 통합 패널 밑에 서고 아이콘을
    # `ACCENT` 로 칠한다. 통합 패널은 상자가 아니라 필드라 아래 따로 서식을 준다.
    condition_roots = (_CONDITION_CARDS,)
    condition_icon_selectors = _SELECTOR_JOINER.join(
        f'{root} summary [data-testid="stExpanderIcon"]' for root in condition_roots
    )
    # 면은 **안쪽 확장 패널**에 칠한다. 바깥 `.st-key-*` 래퍼에 칠하면 모서리가 각진 띠가
    # 한 겹 더 둘러진다(아래 「그룹 상자에는 배경을 칠하지 않는다」).
    condition_face_selectors = _SELECTOR_JOINER.join(f"{root} details" for root in condition_roots)
    condition_summary_selectors = _SELECTOR_JOINER.join(
        f"{root} details > summary:not(:hover):not(:focus-visible)" for root in condition_roots
    )
    condition_alert_selectors = _SELECTOR_JOINER.join(
        (
            *(f'{root} details [data-testid="stAlert"]' for root in condition_roots),
            f'{_CONDITIONS_PANEL} [data-testid="stAlert"]',
        )
    )
    # 꺼진 스위치의 트랙. 숨긴 `input` 을 품은 `span` 바로 뒤의 `div` 다(1.63 DOM 실측).
    condition_switch_off_selectors = _SELECTOR_JOINER.join(
        f'{root} details label:has(> span > input[role="switch"]:not(:checked)) > span + div'
        for root in condition_roots
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
    active_nav_style = (
        f"""
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
        }}"""
        # 키보드 초점은 위 묶음과 **따로** 그린다. 묶음의 `:focus-visible` 은 emotion 의 초점 배경을
        # 덮으려는 것이라 평소와 같은 그림이고, Streamlit 은 `:focus` 에 `outline: none` 을 둬 대신
        # 그려지는 윤곽도 없다 — Tab 으로 지금 화면 링크에 와도 그림이 바뀌지 않았다(2026-10-26
        # E2E). 조건 값 칸과 같은 2px `ACCENT` 윤곽을 2px 띄워 두른다(design_system 3-2).
        f"""
        {active_link}:focus-visible {{
            outline: 2px solid {tokens.ACCENT};
            outline-offset: 2px;
        }}"""
        # 헤더 두 글줄이 이미 3px ACCENT 막대를 쓴다. 같은 막대를 지금 있는 자리에도 세우면 헤더와
        # 사이드바가 한 언어를 쓴다. 여백은 **모든 링크**에 주고 막대만 활성에 켠다 — 활성에만 주면
        # 라벨 시작 위치가 들쭉날쭉해진다.
        f"""
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
    )
    conditions_panel_style = _conditions_panel_style()
    # 규칙마다 설명은 바로 위 파이썬 주석에 둔다 — 이 시트는 화면을 옮길 때마다 소켓으로 다시 가므로
    # CSS 주석을 실으면 그만큼이 매번 함께 간다.
    return (
        # **위쪽 여백은 줄이지 않는다.** 장식이 아니라 겹쳐 있는 헤더 띠(실측 56px)를 피하는
        # 자리다 — 브라우저에서 재니 2.25rem 에서 제목 줄상자가 띠 안으로 8.8px 들어가고 2.75rem
        # 에서도 1.3px 겹친다. 3rem 이 글자 윗선과 띠 사이에 12px 을 남기는 최소값이다. 좌우만
        # 줄인다 — 표와 차트가 가로로 길어 0.25rem 을 덜어도 읽는 데 지장이 없고, 사이드바를 좁힌
        # 만큼 본문이 그 폭을 가져간다.
        """
        <style>
        [data-testid="stMainBlockContainer"] {
            padding-left: 1.25rem !important;
            padding-right: 1.25rem !important;
            padding-top: 3rem !important;
        }
"""
        # 「돌아오는 자리」는 그라데이션 테두리가 말하고 글자는 그 위에 한 단계만 올라선다. 상자
        # 머리글(1rem)의 1.38배다. **`a` 와 `a p` 를 함께 적는다** — 요약 줄과 같은 이유로, 안쪽
        # 마크다운 문단이 제 값으로 덮는다.
        """
        .st-key-home_navigation a,
        .st-key-home_navigation a p {
            font-size: 1.38rem;
            font-weight: 700;
            line-height: 1.3;
        }"""
        # 위아래 여백은 `rem` 이라 글자 크기를 따라가지 않는다 — 글자만 키워도 이 값은 그대로다.
        # 접힌 상자보다 한 뼘 높은 칸을 만드는 자리다.
        f"""
        {HOME_LINK} {{
            padding-top: 0.5rem;
            padding-bottom: 0.5rem;
        }}"""
        # HOME 은 누르지 않았을 때도 보여야 한다. 다른 항목처럼 납작하게 두면 글자만 클 뿐 "여기로
        # 돌아온다" 가 읽히지 않는다.
        #
        # 테두리에만 그라데이션을 남긴다. 한 요소에 배경 두 겹을 깔고 하나는 `padding-box` 로 면을,
        # 하나는 `border-box` 로 테두리를 맡기는 방식이다 — `border-color` 로는 그라데이션을 줄 수
        # 없어서 테두리를 투명하게 두고 그 자리에 두 번째 배경이 비치게 한다. 두 배경의 차례를
        # 바꾸면 면이 테두리를 덮는다.
        #
        # `:hover` 를 같이 적는 이유는 아래 활성 규칙과 같다. Streamlit 의 emotion `:hover` (0,2,0)
        # 가 클래스 하나뿐인 선택자를 이긴다.
        f"""
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
        }}"""
        # 키보드 초점은 활성 링크와 같은 까닭으로 따로 윤곽을 두른다 — 위 묶음의 `:focus-visible` 은
        # 평소와 같은 면이라 HOME 링크에 초점이 와도 그림이 그대로였다.
        f"""
        {HOME_LINK}:focus-visible {{
            outline: 2px solid {tokens.ACCENT};
            outline-offset: 2px;
        }}"""
        # 마우스가 스칠 때 광택 띠가 한 번 지나간다. 평소에는 왼쪽 밖에 세워 두므로 가만히 있는
        # 화면에서는 아무것도 움직이지 않는다.
        f"""
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
        }}"""
        # 움직임을 줄여 달라고 한 사용자에게는 띠를 보내지 않는다.
        f"""
        @media (prefers-reduced-motion: reduce) {{
            {HOME_LINK}:hover::after {{
                animation: none;
            }}
        }}
"""
        # 지금 보고 있는 페이지를 **융기**로 알린다. Streamlit 이 주는 활성 표시는 알파 0.15 의 흐린
        # 회색 하나뿐이라 사실상 보이지 않는다.
        #
        # 이 앱에는 그림자가 이 규칙 말고 한 군데도 없다. 그래서 사이드바에서만 쓰면 장식이 아니라
        # 신호가 된다 — 떠 있는 것이 지금 있는 곳이다.
        #
        # 링크의 `position`·`padding` 은 활성 막대가 설 자리다. 막대가 없는 링크도 같은 여백을
        # 가져야 라벨이 한 줄로 선다. 네 변을 모두 적는다 — 세 변만 적으면 나머지 한 변이 Streamlit
        # 기본값으로 남아 좌우가 어긋난다.
        f"""
        {NAV_LINK} {{
            border: 1px solid transparent;
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
"""
        # 그룹 이름을 옆 상자의 제목(h4·1rem·700)과 같은 선에 세운다. 접히는 제목(조건
        # 카드·`Support`)은 한글 낱말의 음절 사이가 아니라 띄어쓰기에서 접는다 — 좁은 사이드바에서
        # 「LOB 표시 조 / 건」 으로 끊겼다. 띄어쓰기 없이 칸보다 긴 낱말만 아무 데서나 끊는다.
        f"""
        {group_title_selectors} {{
            font-size: 1rem;
            font-weight: 700;
            word-break: keep-all;
            overflow-wrap: anywhere;
        }}"""
        # 그룹 상자 제목은 **한 줄**이고 넘치면 말줄임이다. 기본 폭(300px)에서는 가장 긴 「Dynamic
        # Capa」 도 한 줄이고, 사이드바를 약 205px 보다 좁게 끌면 말줄임으로 준다. 이 규칙이 없으면
        # 좁은 사이드바에서 긴 제목이 두 줄로 접히고 칸보다 긴 낱말은 가운데서 끊긴다(위
        # `overflow-wrap: anywhere`). 말줄임을 거는 것은 문단의 세 줄이다. 1.63 은 마크다운 칸(flex
        # 항목)에 `max-width: 100%` 를 걸어 칸이 이미 부모 폭 아래로 준다 — `min-width: 0` 은
        # 판올림에서 그 값이 빠져도 칸이 글 폭에 묶이지 않게 하는 보험이다(둘 다 없으면 말줄임 없이
        # 잘린다. 1.63 DOM: 요약 줄 → span → div (overflow hidden) → 마크다운 칸 → 문단).
        f"""
        {group_title_shell_selectors} {{
            min-width: 0;
        }}
        {group_title_line_selectors} {{
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}"""
        # 사이드바 페이지 링크 글자(단독 상자·하위 화면)도 넘치면 말줄임이다. 1.63 은 바깥 라벨
        # `span` 에 한 줄·말줄임을 걸지만 넘치는 것은 그 안 마크다운 칸의 문단이라(`text-overflow`
        # 는 물려받지 않는다) 좁은 사이드바에서 글자가 반쯤 잘려 보였다(「Capa Chatbc」).
        f"""
        {NAV_LINK} [data-testid="stMarkdownContainer"] p {{
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}"""
        # 구역 제목은 상자가 아니라 **경계 표시**다. 위 목록과는 한 뼘 떼고 아래 상자에는 붙여,
        # 제목이 어느 무리의 것인지 자리로 읽히게 한다. 글자는 상자 제목(1rem)보다 한참 작은
        # 보조색이라 상자와 무게를 다투지 않는다. 좌우 0.3rem 은 상자 테두리 안쪽에 글자를 세우는
        # 값이다.
        f"""
        {section_selectors} {{
            margin-top: 0.55rem;
            margin-bottom: -0.12rem;
            padding: 0 0.3rem;
        }}
        {section_text_selectors} {{
            font-size: 0.75rem;
            line-height: 1.25;
            color: {tokens.TEXT_MUTED};
        }}
        {section_title_selectors} {{
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }}"""
        # 홀로 남은 「조회 조건」 제목. 제목은 페이지보다 먼저 늘 같은 자리에 서고, 그 아래에 설
        # 상자가 사이드바에 하나도 없을 때만 감춘다(`lone_conditions_heading_selector`).
        f"""
        {lone_conditions_heading_selectors} {{
            display: none;
        }}"""
        # **펼친 요약 줄의 면색은 덮을 수 있다.** Streamlit 이 펼침 상태에만 붙이는 클래스로 요약
        # 줄에 면을 아주 살짝 눌러 칠한다(실측 RGB 밝게 251·252·253, 어둡게 24·24·28).
        # `.st-key-* details[open] > summary` 하나로 `!important` 없이도 바뀐다(Streamlit 1.63, 두
        # 테마 실측).
        #
        # 전에 이 자리에 「덮지 못한다」고 적었던 것은 **잰 방법이 틀려서**였다. 요약 줄에
        # `background-color 0.15s` 전환이 걸려 있어, 규칙을 넣자마자 계산값을 읽으면 전환의 시작값인
        # 옛 색이 나온다. 면색을 재는 검증은 전환이 끝난 뒤(0.4초 뒤) 읽는다.
        #
        # 하위를 가르던 세로선은 없앴다. 그 일을 이제 **확장 패널 자신이** 한다 — 펼친 것과 접힌
        # 것이 경계를 대신 말하므로, 선을 더 그으면 안쪽이 두 번 들여써진다.
        #
        # 그룹 상자에는 배경을 칠하지 않는다. 상자였을 때는 제목 자리를 「머리칸」으로 읽히게 하려고
        # 위쪽만 한 단계 눌러 칠했는데, 지금은 그 자리가 **확장 패널의 `summary`** 이고 Streamlit 이
        # 이미 한 단계 눌러 칠한다. 덧칠하면 테두리를 가진 확장 패널 **바깥** 래퍼에 얹혀, 모서리가
        # 각진 띠가 한 겹 더 둘러진다.
        #
        # 사이드바를 촘촘하게. 기본 세로 간격은 본문 기준이라 박스가 예닐곱 개 쌓이는 사이드바에서는
        # 스크롤만 길어진다.
        f"""
        [data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] {{
            gap: {_SIDEBAR_BLOCK_GAP};
        }}"""
        # 조회 컨트롤 넷에 주던 `padding: 0.55rem 0.7rem` 은 없앴다. 상자였을 때는 안쪽 위젯을
        # 들여놓는 여백이었는데, 확장 패널은 제 여백을 갖는다 — 남겨 두면 그 여백이 **요약 줄과
        # 테두리까지** 밀어 접힌 줄이 그룹 상자보다 안쪽으로 들어간다.
        #
        # 링크 하나뿐인 상자는 **좌우 여백을 주지 않는다.** 그룹 상자는 확장 패널이 제 들여쓰기를
        # 갖는데 이쪽은 링크가 바로 들어가서, 상자에까지 여백을 주면 글자가 그룹 제목보다 10px
        # 오른쪽으로 밀린다(실측 아이콘 42 대 32). 세로는 줄여 접힌 그룹과 같은 높이로 맞춘다 — 세로
        # 0.15rem 이 접힌 그룹 상자와 같은 35px 을 만든다(실측).
        f"""
        {solo_box_selectors} {{
            padding: 0.15rem 0;
        }}"""
        # 그 링크는 그룹 제목과 **같은 층위**다. 하위 페이지가 아니라 최상위 항목이므로 옆 상자의
        # 제목과 같은 무게로 읽혀야 한다.
        f"""
        {solo_title_selectors} {{
            font-size: 1rem;
            font-weight: 700;
        }}
"""
        # **누르면 무슨 일이 일어나는지를 오른쪽 끝 표식이 늘 말한다.** 상자는 모두 한 모양이라
        # 모양으로는 가를 수 없다. `→` 는 곧바로 다른 화면으로 간다, `⌄` 는 이 자리에서
        # 펼쳐진다(펴면 뒤집힌다). 마우스를 올려야 보이는 신호는 신호가 아니다.
        #
        # `content` 는 두 번 적는다. 뒤의 것은 대체 텍스트를 비운 판이라 스크린리더가 합자
        # 이름(「expand_more」)을 링크 이름에 섞어 읽지 않는다. 그 문법을 모르는 브라우저는 뒤의
        # 선언을 버리고 앞의 것을 쓴다.
        f"""
        {solo_link_marker_selectors} {{
            content: "arrow_forward";
            content: "arrow_forward" / "";
            font-family: {_MARKER_FONT};
            font-size: {_LINK_MARKER_SIZE};
            font-weight: 400;
            line-height: 1;
            margin-left: auto;
            padding-left: 0.3rem;
            color: {tokens.TEXT_MUTED};
        }}
        {solo_link_active_selectors} {{
            content: none;
        }}
        {summary_marker_selectors} {{
            content: "expand_more";
            content: "expand_more" / "";
            font-family: {_MARKER_FONT};
            font-size: {_SUMMARY_MARKER_SIZE};
            font-weight: 400;
            line-height: 1;
            margin-left: auto;
            padding-left: {_SUMMARY_MARKER_GAP};
            color: {tokens.TEXT_MUTED};
            transition: transform 150ms ease;
        }}
        {summary_marker_open_selectors} {{
            transform: rotate(180deg);
        }}
        @media (prefers-reduced-motion: reduce) {{
            {summary_marker_selectors} {{
                transition: none;
            }}
        }}"""
        # 계산에 걸리는 조건 카드는 왼쪽 아이콘이 `ACCENT` 다. 위 목록 상자와 같은 모양으로 서되,
        # 눌러서 바꾸는 것이 화면이 아니라 **지금 화면의 계산 조건**이라는 표시다. 통합 조건 패널의
        # 면·아이콘은 따로 건다(`_conditions_panel_style`).
        f"""
        {condition_icon_selectors} {{
            color: {tokens.ACCENT};
        }}"""
        # 조건 카드에 옅은 `ACCENT` 면을 깐다. 요약 줄과 펼친 몸이 **한 장의 면**으로 읽히도록,
        # Streamlit 이 펼친 요약 줄에 까는 제 면은 걷는다(덮이는 것을 실측했다 — 위 「펼친 요약 줄의
        # 면색은 덮을 수 있다」). 마우스를 올리거나 키보드로 닿았을 때는 걷지 않는다 — 그 순간 면이
        # 바뀌는 것이 「누를 수 있다」는 신호다.
        f"""
        {condition_face_selectors} {{
            background-color: {tokens.NAV_CONTROL_TINT};
        }}
        {condition_summary_selectors} {{
            background-color: transparent;
        }}"""
        # 상자 안 알림(저장 검사 오류·경고 등)은 제 면이 반투명이라 청록과 섞인다. 오류 글자 대비가
        # 밝게 4.57 → 3.89, 어둡게 4.51 → 3.71 로 떨어졌다(실측). 알림 밑에 `SURFACE` 를 한 장 깔아
        # 면 밖과 같은 색으로 읽히게 한다. 모서리는 알림 면의 모서리(실측 10px)와 같게 둔다.
        f"""
        {condition_alert_selectors} {{
            background-color: {tokens.SURFACE};
            border-radius: 10px;
        }}"""
        # 꺼진 스위치의 트랙은 Streamlit 기본 면(밝은 회색)이라 청록 면 위에서 1.03:1 로 사라지고 흰
        # 손잡이만 남았다(2026-10-05 E2E). 1px 윤곽을 `TEXT_MUTED` 로 둘러 면에서 떼어 낸다(밝게
        # 4.6:1). 켜진 스위치는 강조색이라 건드리지 않는다.
        f"""
        {condition_switch_off_selectors} {{
            box-shadow: inset 0 0 0 1px {tokens.TEXT_MUTED};
        }}"""
        # HOME 과 첫 그룹 박스 사이만 한 칸 더 띄운다. HOME 은 상자가 아니라 「돌아오는 자리」라
        # 아래 목록과 같은 간격으로 붙어 있으면 목록의 첫 항목처럼 읽힌다.
        """
        [data-testid="stLayoutWrapper"]:has(> .st-key-home_navigation) {
            margin-bottom: 0.45rem;
        }"""
        # HOME 만 상자가 없어 테두리가 바깥 끝에 붙었다. 다른 링크의 테두리는 상자 안쪽 여백만큼
        # 들어와 있어, 같은 링크인데 HOME 만 혼자 넓어 보였다. 같은 만큼 들여 모든 링크 테두리를 한
        # 선에 세운다.
        #
        # HOME 은 상자 안에 든 링크가 아니라 **상자 자리에 선 링크**다. 그래서 폭을 맞출 상대는 상자
        # 안쪽 링크가 아니라 아래 그룹 상자들의 테두리다 — 들여쓰면 맨 위 칸만 혼자 짧아 보인다.
        # 여백을 주지 않아 상자와 같은 20~300 을 쓴다.
        f"""
        .st-key-home_navigation {{
            padding-left: 0;
            padding-right: 0;
        }}

{conditions_panel_style}
"""
        # `Support` 상자에 서식 예외를 두지 않는다. 테두리도 요약 줄 글자도 다른 상자와 같다 — 계산
        # 흐름 밖이라는 것은 서식이 아니라 **맨 아래라는 자리와 앞 간격**이 말한다(바로 아래 규칙).
        # 면이나 글자를 달리하면 그 자리가 뜻을 잃는다.
        #
        # `Support` 는 **언제나 맨 아래**다. 페이지가 자기 사이드바 요소를 그리는 것은
        # `navigation.run()` 안이라 파이썬 차례로는 뒤에 둘 수 없다 — HOME 의 「LOB 표시 조건」
        # 카드가 그래서 이 상자 아래에 붙었다. 세로 흐름에서 자리만 마지막으로 민다. `order` 는
        # **flex 항목**이 받아야 한다. 상자(`st.container`)였을 때는 `.st-key-*` 가 그 한 겹
        # 안쪽이라 바깥 래퍼에 줘야 했는데, **확장 패널은 `.st-key-*` 요소 자신이 flex
        # 항목**이다(프런트엔드가 확장 패널일 때만 래퍼에 그 클래스를 붙인다). 둘 다 적어 둔다 —
        # 맞는 쪽이 걸리고 나머지는 헛돌 뿐이다.
        #
        # **앞에 한 뼘을 띄운다.** 위의 「조회 조건」 구역은 계산 조건이고 `Support` 는 다시 다른
        # 화면으로 가는 목록이다. 제목을 하나 더 세우는 대신 간격으로 구역을 닫는다 — 간격이 없으면
        # `Support` 가 조건 구역의 네 번째 상자로 읽힌다(제안서 시안에서 확인).
        f"""
        [data-testid="stLayoutWrapper"]:has(> .st-key-{admin_box_key}),
        .st-key-{admin_box_key} {{
            order: 99;
            margin-top: 0.9rem;
        }}"""
        # **앱 정보 카드는 사이드바 바닥에 고정한다**(2026-10-07 사용자 결정). 목록·조건 카드가
        # 길어지면 그 밑으로 지나가 가려진다 — 카드가 밀려 내려가지도, 목록이 카드를 덮지도 않는다.
        # 짧으면 마지막 상자 바로 아래가 아니라 사이드바 바닥에 선다.
        #
        # 짧을 때 바닥에 세우려면 맨 위 세로 블록이 스크롤 칸 높이를 다 채워야 카드의
        # `margin-top: auto` 가 남는 높이를 가져간다. 스크롤 칸(`stSidebarContent`)부터 그 세로
        # 블록까지 세로 flex 로 잇고 늘린다. `>` 로만 잇는다 — 상자 안의 세로 블록까지 늘리면 상자가
        # 부푼다.
        # 모두 **줄어들지 않게** 둔다. Streamlit 이 머리칸·사용자 칸에 `min-height: 0` 을 걸어 두어,
        # 줄어들 수 있으면 목록이 길 때 스크롤 대신 눌린다 — 머리칸이 넘친 만큼 눌려(실측 52.5 →
        # 34px) 앱 이름 라벨이 HOME 위에 겹쳤다.
        # 사용자 칸의 아래 여백(Streamlit 84px)은 걷는다. 남겨 두면 끝까지 내렸을 때 카드가 바닥에서
        # 그만큼 떠 있다.
        """
        [data-testid="stSidebarContent"] {
            display: flex;
            flex-direction: column;
        }
        [data-testid="stSidebarHeader"] {
            flex-shrink: 0;
        }
        [data-testid="stSidebarUserContent"] {
            flex: 1 0 auto;
            display: flex;
            flex-direction: column;
            padding-bottom: 0;
        }
        [data-testid="stSidebarUserContent"] > div {
            flex: 1 0 auto;
            display: flex;
            flex-direction: column;
        }
        [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {
            flex: 1 0 auto;
        }"""
        # 카드(`st.container`)는 바깥 래퍼가 flex 항목이다. `order` 가 페이지가 더하는 조건 카드와
        # `Support` 뒤로 밀고, `sticky` 가 스크롤 칸 바닥에 붙인다. `fixed` 는 쓰지 않는다 — 접고
        # 펴는 동안의 `transform` 과 끌어서 바꾸는 폭을 따라가지 못한다.
        # 면은 사이드바 면(`SURFACE`)이라 밑으로 지나가는 목록을 가리고, 윗선이 경계를 말한다.
        # `z-index` 는 사이드바 머리칸(Streamlit 11)보다 아래다.
        # 면을 좌우 여백까지 펴는 것은 **그림자**다. 폭을 늘리면 스크롤 칸에 가로 스크롤이 생기지만
        # 그림자는 스크롤 넓이에 들지 않는다. 위아래로 번지지 않게 `clip-path` 로 잘라 낸다.
        f"""
        [data-testid="stLayoutWrapper"]:has(> .st-key-{APP_CREDITS_KEY}) {{
            order: {APP_CREDITS_ORDER};
            margin-top: auto;
            position: sticky;
            bottom: 0;
            z-index: 3;
            padding: 0.45rem 0 0.6rem;
            background-color: {tokens.SURFACE};
            border-top: 1px solid {tokens.BORDER};
            box-shadow: 0 0 0 {_APP_CREDITS_BLEED} {tokens.SURFACE};
            clip-path: inset(0 -{_APP_CREDITS_BLEED});
        }}"""
        # 작은 글 두 줄 — 크기는 구역 제목의 설명 글(0.75rem)과 같다. 좁은 사이드바에서는 줄이
        # 접히고, 띄어 쓸 곳이 없는 메일 주소도 칸 안에서 끊는다. Streamlit 은 캡션 칸에 아래 음수
        # 여백(-1rem)을 걸어 다음 요소에 붙이는데, 여기서는 그만큼 글이 카드 밖으로 흘러 바닥 아래로
        # 잘린다(실측 14px) — 걷는다.
        f"""
        .st-key-{APP_CREDITS_KEY} [data-testid="stCaptionContainer"] {{
            margin-bottom: 0;
        }}
        .st-key-{APP_CREDITS_KEY} [data-testid="stCaptionContainer"] p {{
            margin: 0;
            font-size: 0.75rem;
            line-height: 1.45;
            color: {tokens.TEXT_MUTED};
            overflow-wrap: anywhere;
        }}"""
        # 문의처는 마크다운이 메일 링크로 만든다. 누를 수 있는 곳이라 `ACCENT` 다 — 그대로 두면
        # 어두운 테마에서 Streamlit 기본 링크색(거의 흰색)으로 떠 작은 글 가운데 혼자 튄다.
        f"""
        .st-key-{APP_CREDITS_KEY} [data-testid="stCaptionContainer"] a {{
            color: {tokens.ACCENT};
        }}"""
        # 상자 여닫기 콜백이 다시 돌리는 빈 프래그먼트와 조건 패널 팝업 호스트 프래그먼트의 본문 칸.
        # 아무것도 그리지 않지만(팝업은 본문 밖에 선다) 칸이 서면 본문에 간격이 하나
        # 생긴다(`sidebar_status.SIDEBAR_TOGGLE_SINK_KEY`·`CONDITION_DIALOG_SINK_KEY`).
        f"""
        [data-testid="stLayoutWrapper"]:has(> .st-key-{SIDEBAR_TOGGLE_SINK_KEY}),
        .st-key-{SIDEBAR_TOGGLE_SINK_KEY},
        [data-testid="stLayoutWrapper"]:has(> .st-key-{CONDITION_DIALOG_SINK_KEY}),
        .st-key-{CONDITION_DIALOG_SINK_KEY} {{
            display: none !important;
        }}"""
        # **짧은 실행은 본문을 흐리지 않는다.** Streamlit 은 실행이 시작되면 본문 요소에
        # `data-stale` 를 달아 즉시 불투명도 0.33 으로 흐린다(전환 없음, 실측). 상자 여닫기는 본문을
        # 다시 돌리지 않는데도, 콜백이 프래그먼트로 바꾸기 전에 앱 실행이 잠깐 시작돼 본문이
        # 40~120ms 깜빡였다(실측). 흐림을 `STALE_DIM_DELAY` 늦춰 그 안에 끝나는 실행은 흐리지 않고,
        # 정말 계산하는 재실행은 그 뒤부터 전처럼 흐린다. 흐림이 풀릴 때는 이 규칙이 떨어져 곧바로
        # 돌아온다.
        f"""
        [data-stale="true"] {{
            transition: opacity 0s linear {STALE_DIM_DELAY} !important;
        }}
        </style>
        """
    )


def _conditions_panel_style() -> str:
    """통합 조건 패널(`CONDITIONS_BOX_KEY`)과 그 안 필드의 서식. 색은 모두 토큰이다.

    패널은 옅은 `ACCENT` 면(`NAV_CONTROL_TINT`) — 접히는 조건 카드와 같은 면이라 「지금 화면의 계산
    조건」으로 한 무리로 읽힌다. 그 위의 값 칸은 흰 필드(`SURFACE`·`BORDER` 1px·모서리 8px)이고
    모든 줄·화면에서 같은 결이다. 그림자는 쓰지 않는다(사이드바 내비 전용) — 마우스를 올리면
    테두리가 `ACCENT` 로, 키보드로 닿으면 2px 띄운 2px `ACCENT` 윤곽이 선다.

    값 칸의 모양(왼쪽 정렬·오른쪽 끝 표식)은 1.63 `st.button` 의 DOM(버튼 안 마크다운 칸)에 기댄다.
    Streamlit 을 올리면 브라우저에서 다시 본다.
    """
    panel = _CONDITIONS_PANEL
    sidebar = '[data-testid="stSidebarContent"]'
    field_button = f'{panel} {_CONDITION_FIELDS} [data-testid="stButton"] button'
    pending_button = (
        f'{panel} {_CONDITION_FIELDS}[class*="{PENDING_SUFFIX}"] [data-testid="stButton"] button'
    )
    name_row = f"{panel} {_CONDITION_NAME_ROWS}"
    notice = (
        f'{panel} > [data-testid="stLayoutWrapper"]:first-child'
        ' [data-testid="stCaptionContainer"] p'
    )
    return (
        # 패널 면과 줄 사이. 사이드바 세로 블록의 촘촘한 간격(위 규칙)보다 뒤라야 이긴다 — 같은
        # 특정도라 차례가 정한다.
        f"""
        {sidebar} {panel} {{
            background-color: {tokens.NAV_CONTROL_TINT};
            border-radius: 10px;
            gap: {_PANEL_ROW_GAP};
            padding: 0.65rem 0.7rem 0.75rem;
        }}
        {sidebar} {panel} {_CONDITION_FIELDS} {{
            gap: {_FIELD_INNER_GAP};
        }}"""
        # 패널 맨 위 「적용 전 편집」 한 줄은 이름 줄과 같은 작은 글이다.
        f"""
        {notice} {{
            font-size: 0.75rem;
            line-height: 1.35;
        }}"""
        # 이름 줄 — 이름은 왼쪽, 상태는 오른쪽 끝. 상태가 길면 한 줄로 말줄임한다(이름은 줄지
        # 않는다). Streamlit 이 캡션 칸에 거는 아래 음수 여백은 걷는다 — 남기면 값 칸이 이름 줄 위로
        # 올라붙는다.
        f"""
        {name_row} {{
            min-height: 1.15rem;
            flex-wrap: nowrap;
        }}
        {name_row} [data-testid="stCaptionContainer"] {{
            margin-bottom: 0;
        }}
        {name_row} [data-testid="stCaptionContainer"] p {{
            margin: 0;
            font-size: 0.75rem;
            line-height: 1.25;
            color: {tokens.TEXT_MUTED};
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        {name_row} > [data-testid="stElementContainer"]:first-child {{
            flex: 0 0 auto;
        }}
        {name_row} > [data-testid="stElementContainer"]:first-child p {{
            font-weight: 600;
        }}
        {name_row} > [data-testid="stElementContainer"]:not(:first-child) {{
            flex: 0 1 auto;
            min-width: 0;
            overflow: hidden;
        }}"""
        # 면 위에서는 배지의 경계가 흐려진다. 1px 윤곽으로 배지를 세운다.
        f"""
        {name_row} .stMarkdownBadge {{
            outline: 1px solid {tokens.BORDER};
            outline-offset: -1px;
        }}"""
        # 값 칸. 흰 필드, 글은 왼쪽 정렬, 오른쪽 끝에 고르는 칸 표식.
        f"""
        {field_button} {{
            justify-content: flex-start;
            gap: 0.45rem;
            min-height: 2.25rem;
            padding: 0.25rem 0.55rem 0.25rem 0.6rem;
            background-color: {tokens.SURFACE};
            border: 1px solid {tokens.BORDER};
            border-radius: 8px;
            color: {tokens.TEXT};
            text-align: left;
        }}
        {field_button}:hover,
        {field_button}:active {{
            background-color: {tokens.SURFACE};
            border-color: {tokens.ACCENT};
            color: {tokens.TEXT};
        }}"""
        # 키보드 포커스는 hover(테두리만 `ACCENT`)와 달라 보여야 한다. 옅은 `NAV_ACTIVE_RING` 윤곽은
        # 같은 강조색 면 위에서 거의 보이지 않았다(2026-10-11 병합 전 리뷰) — 입장 화면 단추와 같은
        # 2px `ACCENT` 윤곽을 2px 띄워 두른다.
        f"""
        {field_button}:focus-visible {{
            border-color: {tokens.ACCENT};
            outline: 2px solid {tokens.ACCENT};
            outline-offset: 2px;
            box-shadow: none;
        }}
        {field_button} [data-testid="stIconMaterial"] {{
            color: {tokens.ACCENT};
        }}"""
        # 버튼 안 두 겹(제목 풍선을 단 칸 → 아이콘·글 묶음)이 가운데 정렬이다. 둘 다 왼쪽으로 붙이고
        # 남는 폭을 채워 오른쪽 표식을 끝으로 민다(1.63 DOM 실측).
        f"""
        {field_button} > div,
        {field_button} > div > span {{
            flex: 1 1 auto;
            min-width: 0;
            justify-content: flex-start;
        }}
        {field_button} [data-testid="stMarkdownContainer"] {{
            flex: 1 1 auto;
            min-width: 0;
        }}
        {field_button} [data-testid="stMarkdownContainer"] p {{
            font-size: 0.875rem;
            font-weight: 600;
            text-align: left;
        }}
        {field_button}::after {{
            content: "unfold_more";
            content: "unfold_more" / "";
            flex: 0 0 auto;
            margin-left: auto;
            font-family: {_MARKER_FONT};
            font-size: {_SUMMARY_MARKER_SIZE};
            font-weight: 400;
            line-height: 1;
            color: {tokens.TEXT_MUTED};
        }}
        {field_button}:disabled {{
            color: {tokens.TEXT_MUTED};
        }}
        {field_button}:disabled::after {{
            content: none;
        }}"""
        # 저장하지 않은 편집이 있는 칸 — 왼쪽 3px 주황 띠(`PENDING_MARK`, 미저장 전용 색).
        f"""
        {pending_button} {{
            box-shadow: inset 3px 0 0 {tokens.PENDING_MARK};
        }}"""
    )
