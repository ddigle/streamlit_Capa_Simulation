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
class PageSpec:
    """사이드바에 노출할 페이지 하나의 선언."""

    path: str
    title: str
    icon: str | None = None
    default: bool = False
    # 비워 두면 주소가 파일명에서 만들어진다. 파일명과 화면 이름이 다른 페이지에만 준다.
    url_path: str | None = None

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
CAPA_CHATBOT = PageSpec(
    "app_pages/capa_chatbot.py", _implementing("Capa Chatbot"), ":material/chat:"
)
SCENARIO_MANAGEMENT = PageSpec(
    "app_pages/scenario_management.py", "시나리오 관리", ":material/database:"
)

STATIC_CAPA = PageSpec("app_pages/static_capa.py", "Static Capa", ":material/factory:")
STATIC_CAPA_SUBPAGES = (
    PageSpec("app_pages/load_conversion.py", "생산 계획", ":material/scale:"),
    PageSpec("app_pages/reference_data.py", "기준 정보", ":material/settings:"),
    PageSpec("app_pages/calculation_result.py", "산출 결과", ":material/monitoring:"),
    PageSpec("app_pages/standard_target_capa.py", "표준 목표", ":material/track_changes:"),
)

DYNAMIC_CAPA = PageSpec(
    "app_pages/reference_integrity.py",
    _implementing("Dynamic Capa"),
    ":material/sync_alt:",
    url_path="dynamic_capa",
)
# 순서는 사용자가 정한 조회 흐름이다 — 설비·공간 같은 **자원 현황**을 먼저 보고, 효율·
# UPEH·수율 **실적**을 지나, 마지막에 그 결과가 쌓인 재공을 본다.
DYNAMIC_CAPA_SUBPAGES = (
    PageSpec(
        "app_pages/available_equipment_status.py",
        _data_pending("가용설비 현황"),
        ":material/precision_manufacturing:",
    ),
    PageSpec("app_pages/space_status.py", _data_pending("Space 현황"), ":material/grid_view:"),
    PageSpec("app_pages/actual_efficiency.py", _implementing("효율 실적"), ":material/speed:"),
    PageSpec("app_pages/actual_upeh.py", _implementing("UPEH 실적"), ":material/timer:"),
    PageSpec("app_pages/yield_actual.py", _implementing("수율 실적"), ":material/percent:"),
    PageSpec(
        "app_pages/wip_status.py",
        _implementing("표준 대비 재공 현황"),
        ":material/inventory_2:",
    ),
)

# 관리 기능이라 조회 컨트롤과 떨어뜨려 사이드바 맨 아래에 자기 박스로 둔다.
ADMIN_AREA = PageSpec(
    "app_pages/admin_area.py",
    "Admin Area",
    ":material/admin_panel_settings:",
)
# VOC 는 계산 화면이 아니라 사람이 쓰는 자리라 계산 그룹 어디에도 속하지 않는다. 관리
# 상자에 **같은 층위로** 함께 세운다 — 쓰는 사람이 「여기가 말할 곳」을 찾을 때 맨 아래를
# 본다. 하위가 아닌 이유는 관리 화면과 게시판이 서로를 포함하지 않기 때문이다.
ADMIN_BOX_PAGES: tuple[PageSpec, ...] = (PageSpec("app_pages/voc.py", "VOC", ":material/forum:"),)


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
    return NavigationPages(
        home=HOME.to_page(),
        groups=tuple(
            SidebarGroup(
                slug=group.slug,
                main=group.main.to_page(),
                subpages=tuple(spec.to_page() for spec in group.subpages),
            )
            for group in SIDEBAR_GROUPS
        ),
        admin_area=ADMIN_AREA.to_page(),
        admin_box_pages=tuple(spec.to_page() for spec in ADMIN_BOX_PAGES),
    )
