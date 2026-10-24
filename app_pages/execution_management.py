# Purpose: 실행 관리 그룹의 정의와 하위 화면 목차를 데이터를 읽지 않고 그린다.

"""실행 관리 머리 화면.

사이드바 계산 그룹은 셋이다(2026-10-17 사용자 결정) — Static Capa 는 약속, 실행 관리는 그 약속의
이행, Dynamic Capa 는 실적으로 다시 낸 Capa 다. 이 화면은 실행 관리 그룹의 입구다.

**첫 판은 데이터를 읽지 않는다.** 정의와 세 영역 비교, 하위 화면 목차(링크와 그 화면이 보는 것 한
줄), 부서별 Gap·A/Item 의 뜻만 그린다. 시나리오·설비 DB 를 열지 않으므로 사이드바 공통 조건 줄도
조건 카드도 없다(`navigation.EXECUTION_MANAGEMENT`). 이행 현황판 숫자는 다음 판에서 들어온다 —
약속 기준선을 어느 공식버전으로 볼지 같은 질문을 그 기능 설계 때 정한다.
"""

from __future__ import annotations

import streamlit as st

from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.page_link import render_page_link
from capa_simulation.components.roadmap_panel import render_roadmap_panel
from capa_simulation.navigation import (
    DYNAMIC_CAPA,
    EXECUTION_MANAGEMENT,
    EXECUTION_MANAGEMENT_SUBPAGES,
    STATIC_CAPA,
    PageSpec,
)

# 하위 화면이 **보는 것** 한 줄. 차례는 사이드바 선언(`EXECUTION_MANAGEMENT_SUBPAGES`)을 따르고,
# 선언에 화면이 늘면 이 표도 함께 고친다(`tests/test_execution_management_page.py` 가 맞댄다).
SUBPAGE_SUMMARIES: dict[str, str] = {
    "app_pages/process_capa_detail.py": (
        "어느 화면에서든 공정 하나를 눌러 바로 깊게 보는 목적지 — 공식 부족 → 메울 호기·기간"
    ),
    "app_pages/required_shortening.py": (
        "단축이 필요한 공정 전부의 진척 관리 한 페이지 — 진척 보드 · 기한 임박 · 이행 지연"
    ),
    "app_pages/constraint_simulation.py": (
        "공정 하나에 미래 제약이 생기면 — 제약 제품 먼저, 기존 제품 확보율 영향과 개조 비가동"
    ),
    "app_pages/available_equipment_status.py": (
        "설비 마스터 편집 · 설비 일정 기준 가용대수 · Static 대비 일정"
    ),
    "app_pages/space_status.py": "셋업 이행을 공간·호기로 — 반입 전·지연·미확인 표식",
    "app_pages/actual_efficiency.py": "효율 기준 대비 실적 Gap 과 개선 우선순위",
    "app_pages/actual_upeh.py": "UPEH 기준 대비 실적 Gap 과 개선 우선순위",
    "app_pages/yield_actual.py": "수율 기준(`RQ_YLD`) 대비 실적 Gap 과 개선 우선순위",
}

# 세 영역 한 줄 비교 — (머리 선언, 한 낱말, 한 줄). 이 화면 자신은 링크 대신 「지금 여기」다.
AREAS: tuple[tuple[PageSpec, str, str], ...] = (
    (
        STATIC_CAPA,
        "약속",
        "기술팀이 정한 기준정보(셋업 시점·UPEH·효율·수율)와 생산계획으로 낸 미래 Capa 입니다. "
        "자원운영팀은 그 부족대수로 투자를 정합니다.",
    ),
    (
        EXECUTION_MANAGEMENT,
        "이행",
        "약속된 Capa 가 실제로 확보되는지 공정·기간·호기로 확인합니다. 어긋나면 유관부서에 "
        "이행을 요청하고, 지킬 수 없는 약속은 Static 반영까지 추적합니다.",
    ),
    (
        DYNAMIC_CAPA,
        "실적",
        "실행 관리가 모은 실적으로 지금 실제로 낼 수 있는 Capa 를 다시 내고, 그 Capa 로 재공·"
        "단기 병목을 운영합니다.",
    ),
)
# 목차 한 줄에 놓는 카드 수. 여덟 화면이 세 줄로 선다.
COLUMNS_PER_ROW = 3


def _render_areas() -> None:
    with st.container(border=True):
        st.markdown("#### :material/account_tree: 세 영역")
        columns = st.columns(len(AREAS), gap="small")
        for column, (spec, word, line) in zip(columns, AREAS, strict=True):
            with column.container(border=True):
                st.markdown(f"**{spec.title}** · {word}")
                st.caption(line)
                if spec is EXECUTION_MANAGEMENT:
                    st.caption(":material/my_location: 지금 여기")
                else:
                    render_page_link(spec.path, label="열기", icon=spec.icon)


def _render_subpages() -> None:
    with st.container(border=True):
        st.markdown("#### :material/list_alt: 이 영역의 화면")
        st.caption("사이드바 차례 그대로입니다. 약속에 가까운 설비 이행부터 성능 실적 순입니다.")
        specs = list(EXECUTION_MANAGEMENT_SUBPAGES)
        for start in range(0, len(specs), COLUMNS_PER_ROW):
            row = specs[start : start + COLUMNS_PER_ROW]
            columns = st.columns(COLUMNS_PER_ROW, gap="small")
            for column, spec in zip(columns, row, strict=False):
                with column.container(border=True):
                    render_page_link(spec.path, label=spec.title, icon=spec.icon)
                    st.caption(SUBPAGE_SUMMARIES[spec.path])


# 사이드바 상자 라벨(`EXECUTION_MANAGEMENT.title`)과 같은 글자다 — 두 제목이 같다는 계약은
# `tests/test_app_navigation.py` 가 AST 로 첫 인자를 읽어 본다.
render_page_header(
    "실행 관리",
    description=(
        "실행 관리: 약속된 Capa(Static)가 실제로 확보되고 있는지 공정·기간·호기 단위로 확인합니다. "
        "어긋난 곳은 유관부서에 이행을 요청하고, 지킬 수 없는 약속은 Static 기준정보에 반영되도록 "
        "진척을 관리합니다."
    ),
)
render_page_guide("execution_management", title="실행 관리")
render_roadmap_panel(
    purpose=(
        "부서별 Gap · A/Item — 약속(Static) 대비 Gap 을 그 Gap 을 메울 부서의 Action Item 으로 "
        "넘깁니다. 주관은 제조팀입니다."
    ),
    owners=(
        (
            "기술팀 · 설비 일정",
            "가용 일정이 약속보다 늦으면 Setup 단축(필요 단축 일정)으로 당길 호기·기간을 정합니다.",
        ),
        (
            "기술팀 · 설비 성능",
            "효율·UPEH·수율 실적이 기준에 못 미치면 Gap 을 근거로 개선 항목을 우선 관리합니다.",
        ),
        (
            "자원운영팀 · 투자",
            "단축으로도 메우지 못하는 부족(신규 필요 대수)은 투자 검토로 넘깁니다.",
        ),
    ),
    roadmap=(
        "약속 대비 Gap 확인 → 부서별 A/Item · 이행 요청 → 진척 관리 → 지킬 수 없으면 Static 반영"
    ),
)
_render_areas()
_render_subpages()
st.caption(":material/upcoming: 다음 판에서 이 화면에 이행 현황판 숫자가 들어옵니다.")
