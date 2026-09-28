# Purpose: 사이드바 페이지 목록과 구역 제목을 선언형 데이터로 정의하고 st.Page 묶음을 만든다.

"""Declarative page inventory for the sidebar navigation.

페이지를 추가하거나 제목을 바꿀 때 손대는 곳을 한 군데로 모은다. `app.py`는 이 선언을
읽어 렌더링만 하고, 페이지 목록 자체는 여기서 관리한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

# 실적 DB 연결과 운영 기준 확정 전인 화면에 붙인다. 이전에는 사이드바에만
# `(구현중)`·`(구현 중)`·`(DB 셋팅중)` 세 표기가 섞여 있었고 페이지 본문 제목과도
# 달랐다. 본문이 이미 쓰고 있던 표기로 통일했다.
IMPLEMENTING_SUFFIX = "(구현중)"
# 화면은 이미 다 만들었고 **데이터만 기다리는** 페이지에 붙인다. `(구현중)` 과 갈라 둔 것은
# 둘이 사용자에게 다른 뜻이기 때문이다 — 하나는 "아직 못 만들었다", 하나는 "연결만 남았다".
DATA_PENDING_SUFFIX = "(Data확보중)"


def _implementing(title: str) -> str:
    return f"{title} {IMPLEMENTING_SUFFIX}"


def _data_pending(title: str) -> str:
    return f"{title} {DATA_PENDING_SUFFIX}"


@dataclass(frozen=True)
class ConditionTabs:
    """공통 조건(시나리오·조회기간)을 **탭 몇 개에서만** 읽는 화면의 선언.

    예: 가용설비 현황은 설비 DB 만 보는데, `Static/Dynamic` 탭만 활성 시나리오와 조회기간으로
    확보율을 맞대어 본다. 그 탭이 열렸을 때만 공통 상자를 세운다.
    """

    # 그 화면 `stateful_tabs` 의 key. 열린 탭 라벨이 세션의 이 칸에 있다.
    key: str
    # 기억이 없을 때(처음 들어온 회차) 열리는 첫 탭 라벨.
    first: str
    # 공통 조건을 읽는 탭 라벨.
    labels: frozenset[str]
    # 조건 카드를 세우는 탭 라벨. 비워 두면(`None`) 카드가 있는 화면의 모든 탭이다.
    card_labels: frozenset[str] | None = None


@dataclass(frozen=True)
class PageSpec:
    """사이드바에 노출할 페이지 하나의 선언."""

    path: str
    title: str
    icon: str | None = None
    default: bool = False
    # 비워 두면 주소가 파일명에서 만들어진다. 파일명과 화면 이름이 다른 페이지에만 준다.
    url_path: str | None = None
    # 사이드바 「조회 조건」의 공통 상자 가운데 **이 화면이 실제로 읽는 것**(2026-09-29 사용자
    # 결정). 읽지 않는 상자는 그 화면에서 세우지 않는다 — 계산에 걸리지 않는 조건이 사이드바에
    # 남아 있으면 그 조건을 바꿔도 화면이 그대로라 무엇이 이 화면의 조건인지 흐려진다.
    reads_scenario: bool = True
    reads_period: bool = True
    # 이 화면이 자기 조건 카드(`sidebar_status.condition_card`)를 세우는가. 공통 조건을 하나도
    # 읽지 않는 화면도 카드가 있으면 「조회 조건」 제목을 세워야 한다 — 제목은 `app.py` 가
    # 페이지보다 먼저 그리므로 페이지가 카드를 그릴지를 선언으로 미리 안다.
    has_condition_cards: bool = False
    # 공통 조건을 일부 탭에서만 읽으면 그 탭들. 비워 두면 `reads_*` 가 화면 전체에 걸린다.
    condition_tabs: ConditionTabs | None = None

    def reads_common_conditions_on(self, active_tab: str | None) -> bool:
        """지금 열린 탭(`None` 은 탭을 가르지 않는 화면)에서 이 화면이 공통 조건을 읽는가."""
        if self.condition_tabs is None:
            return True
        return active_tab in self.condition_tabs.labels

    def has_cards_on(self, active_tab: str | None) -> bool:
        """지금 열린 탭에서 이 화면이 조건 카드를 세우는가. 제목 줄만 남는 빈 구역을 막는다."""
        if not self.has_condition_cards:
            return False
        tabs = self.condition_tabs
        return tabs is None or tabs.card_labels is None or active_tab in tabs.card_labels

    def to_page(self) -> st.Page:
        return st.Page(
            self.path,
            title=self.title,
            icon=self.icon,
            default=self.default,
            url_path=self.url_path,
        )


# HOME 은 목록의 한 항목이 아니라 **돌아오는 자리**다. 아이콘을 빼 다른 항목과
# 같은 리듬에서 끄집어낸다 — 그 자리는 버튼 서식(그라데이션 테두리)이 맡는다.
HOME = PageSpec("app_pages/home.py", "HOME", default=True)
# 공통 조건 선언(`reads_*`)은 **그 화면 코드가 실제로 읽는 것**이다(2026-09-29 전수 조사). 준비
# 중인 화면도 사이드바는 앱 전체의 규칙이라 같이 적는다 — 데모 데이터만 그리는 화면에 시나리오·
# 조회기간 상자가 서 있으면 그것을 바꿔도 아무것도 변하지 않는다.
CAPA_CHATBOT = PageSpec(
    "app_pages/capa_chatbot.py",
    _implementing("Capa Chatbot"),
    ":material/chat:",
    reads_scenario=False,
    reads_period=False,
)
# 시나리오 관리는 활성 시나리오를 불러오고 저장하며, 복제·리비전 저장이 지금 조회기간을
# 프리셋으로 함께 담는다 — 저장되는 값이 보여야 하므로 두 상자를 다 세운다.
SCENARIO_MANAGEMENT = PageSpec(
    "app_pages/scenario_management.py", "시나리오 관리", ":material/database:"
)

STATIC_CAPA = PageSpec(
    "app_pages/static_capa.py",
    "Static Capa",
    ":material/factory:",
    has_condition_cards=True,
)
STATIC_CAPA_SUBPAGES = (
    PageSpec(
        "app_pages/load_conversion.py",
        "생산 계획",
        ":material/scale:",
        has_condition_cards=True,
    ),
    PageSpec(
        "app_pages/reference_data.py",
        "기준 정보",
        ":material/settings:",
        has_condition_cards=True,
    ),
    PageSpec(
        "app_pages/calculation_result.py",
        "산출 결과",
        ":material/monitoring:",
        has_condition_cards=True,
    ),
    PageSpec(
        "app_pages/standard_target_capa.py",
        "표준 목표",
        ":material/track_changes:",
        has_condition_cards=True,
    ),
)

DYNAMIC_CAPA = PageSpec(
    "app_pages/reference_integrity.py",
    _implementing("Dynamic Capa"),
    ":material/sync_alt:",
    url_path="dynamic_capa",
    reads_scenario=False,
    reads_period=False,
)
# 가용설비 현황의 탭. 공통 조건을 읽는 탭이 하나뿐이라 사이드바(`app.py`)가 열린 탭을 봐야 하고,
# 그래서 라벨을 여기 한 곳에 둔다 — 페이지도 이 이름을 읽는다.
EQUIPMENT_TAB_KEY = "equipment_active_tab"
EQUIPMENT_MAIN_TAB = ":material/dashboard: Main"
EQUIPMENT_GAP_TAB = ":material/compare_arrows: Static/Dynamic"
# 순서는 사용자가 정한 조회 흐름이다 — 설비·공간 같은 **자원 현황**을 먼저 보고, 효율·
# UPEH·수율 **실적**을 지나, 마지막에 그 결과가 쌓인 재공을 본다.
DYNAMIC_CAPA_SUBPAGES = (
    # 설비 DB 만 본다. `Static/Dynamic` 탭만 활성 시나리오·조회기간으로 확보율을 맞대어 본다.
    PageSpec(
        "app_pages/available_equipment_status.py",
        _data_pending("가용설비 현황"),
        ":material/precision_manufacturing:",
        condition_tabs=ConditionTabs(
            EQUIPMENT_TAB_KEY,
            first=EQUIPMENT_MAIN_TAB,
            labels=frozenset({EQUIPMENT_GAP_TAB}),
            # `설비 조회 조건` 카드는 Main·Static/Dynamic 에만 선다.
            card_labels=frozenset({EQUIPMENT_MAIN_TAB, EQUIPMENT_GAP_TAB}),
        ),
        has_condition_cards=True,
    ),
    # 설비 DB 와 자기 기준일만 본다. 기준일·필터는 자기 조건 카드(`Space 조건`)다.
    PageSpec(
        "app_pages/space_status.py",
        _data_pending("Space 현황"),
        ":material/grid_view:",
        reads_scenario=False,
        reads_period=False,
        has_condition_cards=True,
    ),
    *(
        PageSpec(path, _implementing(title), icon, reads_scenario=False, reads_period=False)
        for path, title, icon in (
            ("app_pages/actual_efficiency.py", "효율 실적", ":material/speed:"),
            ("app_pages/actual_upeh.py", "UPEH 실적", ":material/timer:"),
            ("app_pages/yield_actual.py", "수율 실적", ":material/percent:"),
        )
    ),
    # 활성 시나리오는 읽지만 기간은 오늘 기준 앞뒤 몇 달로 스스로 정한다.
    PageSpec(
        "app_pages/wip_status.py",
        _implementing("표준 대비 재공 현황"),
        ":material/inventory_2:",
        reads_period=False,
    ),
)

# 관리 기능이라 조회 컨트롤과 떨어뜨려 사이드바 맨 아래에 자기 박스로 둔다.
# 공정 목록과 원천 품질이 활성 시나리오를 읽는다. 조회기간은 읽지 않는다.
ADMIN_AREA = PageSpec(
    "app_pages/admin_area.py",
    "Admin Area",
    ":material/admin_panel_settings:",
    reads_period=False,
)
# VOC 는 계산 화면이 아니라 사람이 쓰는 자리라 계산 그룹 어디에도 속하지 않는다. 관리
# 상자에 **같은 층위로** 함께 세운다 — 쓰는 사람이 「여기가 말할 곳」을 찾을 때 맨 아래를
# 본다. 하위가 아닌 이유는 관리 화면과 게시판이 서로를 포함하지 않기 때문이다.
ADMIN_BOX_PAGES: tuple[PageSpec, ...] = (
    PageSpec(
        "app_pages/voc.py",
        "VOC",
        ":material/forum:",
        reads_scenario=False,
        reads_period=False,
    ),
)


@dataclass(frozen=True)
class SidebarGroupSpec:
    """사이드바 박스 하나의 선언. `slug` 가 컨테이너 key 와 CSS 선택자의 단일 근거다."""

    slug: str
    main: PageSpec
    subpages: tuple[PageSpec, ...] = ()


# HOME(가운데·큰 글씨)과 Admin Area(조회 컨트롤 아래)는 배치가 달라 `app.py` 가 손수 그린다.
# 나머지 박스는 여기 선언에서 나온다 — 새 그룹을 더할 때 `app.py` 를 함께 고칠 필요가 없다.
SIDEBAR_GROUPS: tuple[SidebarGroupSpec, ...] = (
    SidebarGroupSpec("capa_chatbot", CAPA_CHATBOT),
    SidebarGroupSpec("scenario_management", SCENARIO_MANAGEMENT),
    SidebarGroupSpec("static_capa", STATIC_CAPA, STATIC_CAPA_SUBPAGES),
    SidebarGroupSpec("dynamic_capa", DYNAMIC_CAPA, DYNAMIC_CAPA_SUBPAGES),
)


@dataclass(frozen=True)
class SidebarSectionSpec:
    """사이드바 구역 제목 한 줄의 선언. `slug` 가 컨테이너 key 와 CSS 선택자의 단일 근거다."""

    slug: str
    title: str
    # 제목 오른쪽의 짧은 뜻풀이. 이 구역의 상자가 **무엇에 걸리는지**를 말한다.
    hint: str = ""

    @property
    def key(self) -> str:
        return f"sidebar_section_{self.slug}"


# 상자는 모두 한 모양이라 모양으로는 용도를 가르지 못한다. 위의 그룹은 **다른 화면으로
# 가는 목록**이고, 아래 상자들(시나리오·리비전, 조회기간, 그리고 화면마다의 조건 카드 —
# HOME 의 B/N 집계 공정, 생산 계획의 환산 조건 등)은 **지금 화면이 읽는 조건**이다. 그 경계에
# 제목 한 줄을 세운다. 화면마다 카드가 달라지므로 뜻풀이는 「이 화면에 적용」이다(2026-09-28
# 사용자 결정). 맨 아래 `Support` 는 다시 목록이므로 제목 대신 앞 간격으로 이 구역과 떨어진다.
CONDITIONS_SECTION = SidebarSectionSpec("conditions", "조회 조건", "이 화면에 적용")
SIDEBAR_SECTIONS: tuple[SidebarSectionSpec, ...] = (CONDITIONS_SECTION,)

ALL_SPECS: tuple[PageSpec, ...] = (
    HOME,
    *(spec for group in SIDEBAR_GROUPS for spec in (group.main, *group.subpages)),
    ADMIN_AREA,
    *ADMIN_BOX_PAGES,
)


@dataclass(frozen=True)
class SidebarGroup:
    """`app.py` 가 사이드바 박스 하나를 그릴 때 쓰는 `st.Page` 묶음."""

    slug: str
    main: st.Page
    subpages: tuple[st.Page, ...]


@dataclass(frozen=True)
class NavigationPages:
    """`app.py`가 사이드바를 그릴 때 쓰는 `st.Page` 묶음."""

    home: st.Page
    groups: tuple[SidebarGroup, ...]
    admin_area: st.Page
    # `admin_area` 와 **같은 층위**로 한 상자에 서는 나머지 페이지들.
    admin_box_pages: tuple[st.Page, ...]
    # 페이지와 그 선언의 짝. `app.py` 가 지금 화면이 읽는 공통 조건을 여기서 찾는다.
    specs: tuple[tuple[st.Page, PageSpec], ...] = ()

    def spec_for(self, url_path: str) -> PageSpec | None:
        """주소로 선언을 찾는다. **`st.navigation()` 이 돈 뒤에만** 부른다.

        그 전에는 페이지의 `url_path` 가 채워지지 않아 `AttributeError` 다 — 파일명에서 주소를
        만드는 일을 그 호출이 한다.
        """
        return next((spec for page, spec in self.specs if page.url_path == url_path), None)

    @property
    def ordered(self) -> list[st.Page]:
        """`st.navigation`에 넘길 전체 페이지를 사이드바 표시 순서로 돌려준다."""
        return [
            self.home,
            *(page for group in self.groups for page in (group.main, *group.subpages)),
            self.admin_area,
            *self.admin_box_pages,
        ]


def build_navigation_pages() -> NavigationPages:
    """선언을 실제 `st.Page` 객체로 만든다."""
    pages: dict[PageSpec, st.Page] = {spec: spec.to_page() for spec in ALL_SPECS}
    return NavigationPages(
        home=pages[HOME],
        groups=tuple(
            SidebarGroup(
                slug=group.slug,
                main=pages[group.main],
                subpages=tuple(pages[spec] for spec in group.subpages),
            )
            for group in SIDEBAR_GROUPS
        ),
        admin_area=pages[ADMIN_AREA],
        admin_box_pages=tuple(pages[spec] for spec in ADMIN_BOX_PAGES),
        specs=tuple((page, spec) for spec, page in pages.items()),
    )
