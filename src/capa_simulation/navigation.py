# Purpose: 사이드바 페이지 목록을 선언형 데이터로 정의하고 st.Page 묶음을 만든다.

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


def _implementing(title: str) -> str:
    return f"{title} {IMPLEMENTING_SUFFIX}"


@dataclass(frozen=True)
class PageSpec:
    """사이드바에 노출할 페이지 하나의 선언."""

    path: str
    title: str
    icon: str | None = None
    default: bool = False

    def to_page(self) -> st.Page:
        return st.Page(self.path, title=self.title, icon=self.icon, default=self.default)


HOME = PageSpec("app_pages/home.py", "HOME", default=True)
CAPA_CHATBOT = PageSpec(
    "app_pages/capa_chatbot.py", _implementing("Capa Chatbot"), ":material/chat:"
)
SCENARIO_MANAGEMENT = PageSpec(
    "app_pages/scenario_management.py", "시나리오 관리", ":material/database:"
)

STATIC_CAPA = PageSpec("app_pages/static_capa.py", "Static Capa", ":material/factory:")
STATIC_CAPA_SUBPAGES = (
    PageSpec("app_pages/load_conversion.py", "부하량", ":material/scale:"),
    PageSpec("app_pages/capacity_standards.py", "공정별 Capa", ":material/settings:"),
    PageSpec("app_pages/process_securement.py", "공정별 확보율", ":material/monitoring:"),
    PageSpec("app_pages/standard_target_capa.py", "표준 목표 Capa", ":material/track_changes:"),
)

DYNAMIC_CAPA = PageSpec(
    "app_pages/reference_integrity.py", _implementing("Dynamic Capa"), ":material/sync_alt:"
)
DYNAMIC_CAPA_SUBPAGES = (
    PageSpec(
        "app_pages/wip_status.py",
        _implementing("표준 대비 재공 현황"),
        ":material/inventory_2:",
    ),
    PageSpec(
        "app_pages/available_equipment_status.py",
        _implementing("가용설비 현황"),
        ":material/precision_manufacturing:",
    ),
    PageSpec("app_pages/actual_efficiency.py", _implementing("효율 실적"), ":material/speed:"),
    PageSpec("app_pages/actual_upeh.py", _implementing("UPEH 실적"), ":material/timer:"),
    PageSpec("app_pages/space_status.py", _implementing("Space 현황"), ":material/grid_view:"),
)

# 관리 기능이라 조회 컨트롤과 떨어뜨려 사이드바 맨 아래에 자기 박스로 둔다.
ADMIN_AREA = PageSpec(
    "app_pages/admin_area.py",
    "Admin Area",
    ":material/admin_panel_settings:",
)

ALL_SPECS: tuple[PageSpec, ...] = (
    HOME,
    CAPA_CHATBOT,
    SCENARIO_MANAGEMENT,
    STATIC_CAPA,
    *STATIC_CAPA_SUBPAGES,
    DYNAMIC_CAPA,
    *DYNAMIC_CAPA_SUBPAGES,
    ADMIN_AREA,
)


@dataclass(frozen=True)
class NavigationPages:
    """`app.py`가 사이드바를 그릴 때 쓰는 `st.Page` 묶음."""

    home: st.Page
    capa_chatbot: st.Page
    scenario_management: st.Page
    static_capa: st.Page
    static_capa_subpages: list[st.Page]
    dynamic_capa: st.Page
    dynamic_capa_subpages: list[st.Page]
    admin_area: st.Page

    @property
    def ordered(self) -> list[st.Page]:
        """`st.navigation`에 넘길 전체 페이지를 사이드바 표시 순서로 돌려준다."""
        return [
            self.home,
            self.capa_chatbot,
            self.scenario_management,
            self.static_capa,
            *self.static_capa_subpages,
            self.dynamic_capa,
            *self.dynamic_capa_subpages,
            self.admin_area,
        ]


def build_navigation_pages() -> NavigationPages:
    """선언을 실제 `st.Page` 객체로 만든다."""
    return NavigationPages(
        home=HOME.to_page(),
        capa_chatbot=CAPA_CHATBOT.to_page(),
        scenario_management=SCENARIO_MANAGEMENT.to_page(),
        static_capa=STATIC_CAPA.to_page(),
        static_capa_subpages=[spec.to_page() for spec in STATIC_CAPA_SUBPAGES],
        dynamic_capa=DYNAMIC_CAPA.to_page(),
        dynamic_capa_subpages=[spec.to_page() for spec in DYNAMIC_CAPA_SUBPAGES],
        admin_area=ADMIN_AREA.to_page(),
    )
