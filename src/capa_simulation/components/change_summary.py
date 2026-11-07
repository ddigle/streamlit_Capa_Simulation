# Purpose: 머리 변경 칩이 보일 「이 세션의 변경」 목록을 탭 점과 같은 세션 판정으로 짓는다.

"""머리 변경 요약(2026-11-03 결정 보드 D5 (가) — 검수표 home-06).

바뀐 것이 있을 때만 머리 툴바에 「● 변경 n · 맨 위 한 줄」 칩이 서고(`components/alert_center.py`),
누르면 화면별 한 줄이 묶음 셋으로 나온다.

1. **화면을 떠나면 사라짐**(`lose`) — 편집표의 적용 전 편집(지금 화면만), Space 층 사용 편집 초안,
가용설비 현황 작은
   편집표.
2. **저장 안 함**(`keep`) — 적용했지만 저장하지 않은 시나리오, 설비 편집본 · FAB 배치 대기,
기준 정보 표의 적용 전 편집(세션 칸이라 화면을 떠나도 남는다), 붙여넣기 대기, Past Data
   초안, 시나리오 관리 표 초안. 새로고침 · 시나리오 바꿈에 사라진다.
3. **가정 사용 중**(`assume`) — 공식과 다른 설비 시나리오, UPEH 가정(100% 아님). 내가 바꾼 것이지만
지우지 않아도 된다 —
   회색 점이다.

**판정은 화면 탭 줄 주황 점(`page_tabs.page_unsaved_marks`)과 같은 등록부**이고 **세션만 읽는다**(DB
· 캐시 없음 — 매 회차 페이지 앞에서 부른다). 서버가 모르는 초안(폼 안 · 브라우저 안 — Preference 폼
· Cut-off · Admin 표 · 자동 갱신 설정 · Space 적용 전 배치 · VOC 새 글)과 저장 개념이 없는 세션
조건(제약 시뮬레이션 · Qual 계산기 · 필터)은 들지 않는다(설계 5-2 「넣지 않는 것」 — 다음 판 후보).
머리 띠 위 줄의 「최신 rN 있음」 · 「공식 vN」 은 상태라 넣지 않는다.

차례(칩 맨 위 글 · 판 차례): 떠나면 사라짐(지금 화면 것) → 시나리오 미저장 → 설비 미저장 → 표 초안 ·
붙여넣기 대기 → Past Data · 목록 → 설비 가정 → UPEH 가정.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal, TypedDict

import streamlit as st

from capa_simulation.components.equipment_data_workspace import (
    has_unsaved_equipment_edits,
    pending_fab_layout,
    small_editor_edits,
)
from capa_simulation.components.past_data_management import past_data_has_pending
from capa_simulation.components.scenario_edit_bar import pending_edit_pages
from capa_simulation.components.scenario_list_state import list_has_edits
from capa_simulation.components.scenario_management_tabs import CAPA_SCENARIO_TAB_NAME
from capa_simulation.components.space_floor_list import floor_state_draft_pending
from capa_simulation.equipment_scenario_activation import remembered_equipment_label
from capa_simulation.navigation import (
    AVAILABLE_EQUIPMENT_STATUS,
    HOME,
    PROCESS_CAPA_DETAIL,
    SCENARIO_MANAGEMENT,
    SPACE_STATUS,
    PageSpec,
    runtime_specs,
)
from capa_simulation.scenario_activation import (
    active_scenario_label,
    has_unsaved_scenario_changes,
)
from capa_simulation.upeh_assumption_state import (
    UPEH_ASSUMPTION_DEFAULT_PERCENT,
    UPEH_ASSUMPTION_PERCENT_KEY,
)

Group = Literal["lose", "keep", "assume"]
# 묶음 차례와 판 머리 글.
GROUPS: tuple[tuple[Group, str], ...] = (
    ("lose", "화면을 떠나면 사라짐"),
    ("keep", "저장 안 함 — 새로고침 · 시나리오 바꿈에 사라짐"),
    ("assume", "가정 사용 중 — 공식과 다른 값으로 보는 중"),
)
# 판 한 줄 · 칩 맨 위 글이 넘으면 말줄임한다(설계 5-2 — 14자 · 9자 안팎).
_NAME_LIMIT = 16


class ChangeItem(TypedDict):
    """칩 판 한 줄 — 묶음 · 화면 이름 · 짧은 글 · 칩 맨 위 글 · 그 화면 주소(없으면 None) · 그 화면
    안 탭 이름(그 탭의 표를 가리키는 줄만 — 「그 화면으로」 가 그 탭까지 연다)."""

    group: Group
    page: str
    text: str
    top: str
    href: str | None
    tab: str


def _short(name: str, limit: int = _NAME_LIMIT) -> str:
    return name if len(name) <= limit else name[: limit - 1] + "…"


def _spec_for_file(page_file: str) -> PageSpec | None:
    for spec in runtime_specs():
        if Path(spec.path).name == page_file:
            return spec
    return None


def _strip_title(title: str, label: str) -> str:
    """등록부 글 「제목 · 이름」 에서 제목을 뗀 이름."""
    prefix = f"{title} · "
    return label[len(prefix) :] if label.startswith(prefix) else label


def _edits_text(title: str, labels: tuple[str, ...]) -> str:
    """판 한 줄 글 — 「적용 전 편집 · UPEH, 일수」."""
    names = ", ".join(_strip_title(title, label) for label in labels)
    return f"적용 전 편집 · {names}"


def session_changes(page_file: str | None, *, hrefs: Mapping[str, str]) -> list[ChangeItem]:
    """이 세션의 변경 목록(차례대로). `hrefs` 는 화면 경로(`PageSpec.path`) → 주소(`url_path`)다."""

    def item(
        group: Group, spec: PageSpec | None, page: str, text: str, top: str, *, tab: str = ""
    ) -> ChangeItem:
        href = None if spec is None else hrefs.get(spec.path)
        return ChangeItem(group=group, page=page, text=text, top=top, href=href, tab=tab)

    lose: list[ChangeItem] = []
    held: list[ChangeItem] = []
    pages = pending_edit_pages(page_file)
    for name, edits in pages.items():
        spec = _spec_for_file(name)
        title = edits.title if spec is None else spec.title
        if edits.editors:
            text = _edits_text(edits.title, edits.editors)
            lose.append(item("lose", spec, title, text, f"{title} 적용 전"))
        if edits.drafts:
            text = _edits_text(edits.title, edits.drafts)
            held.append(item("keep", spec, title, text, f"{title} 적용 전"))
        if edits.staged:
            held.append(item("keep", spec, title, "올린 붙여넣기 적용 대기", "붙여넣기 대기"))
    space_file = Path(SPACE_STATUS.path).name
    if page_file == space_file and floor_state_draft_pending():
        lose.append(
            item("lose", SPACE_STATUS, SPACE_STATUS.title, "층 사용 편집 중", "Space 편집 중")
        )
    if page_file == Path(AVAILABLE_EQUIPMENT_STATUS.path).name:
        small = small_editor_edits()
        if small:
            lose.append(
                item(
                    "lose",
                    AVAILABLE_EQUIPMENT_STATUS,
                    AVAILABLE_EQUIPMENT_STATUS.title,
                    "적용 전 편집 · " + ", ".join(small),
                    "가용설비 적용 전",
                )
            )

    keep: list[ChangeItem] = []
    if has_unsaved_scenario_changes():
        label = active_scenario_label()
        revision = "" if label is None else f" · r{label.revision_no}"
        keep.append(
            item("keep", None, "시나리오", f"적용 후 저장 안 함{revision}", "시나리오 미저장")
        )
    if has_unsaved_equipment_edits():
        keep.append(
            item(
                "keep",
                AVAILABLE_EQUIPMENT_STATUS,
                "가용설비 · Space",
                "설비 편집 저장 안 함",
                "설비 미저장",
            )
        )
    if pending_fab_layout() is not None:
        keep.append(
            item("keep", SPACE_STATUS, SPACE_STATUS.title, "FAB 배치 저장 안 함", "설비 미저장")
        )
    keep.extend(held)
    if past_data_has_pending():
        keep.append(item("keep", HOME, HOME.title, "Past Data 저장 안 함", "Past Data 미저장"))
    if list_has_edits():
        keep.append(
            item(
                "keep",
                SCENARIO_MANAGEMENT,
                SCENARIO_MANAGEMENT.title,
                "목록 편집 저장 안 함",
                "목록 미저장",
                tab=CAPA_SCENARIO_TAB_NAME,
            )
        )

    assume: list[ChangeItem] = []
    equipment = remembered_equipment_label()
    if equipment and not equipment.get("official_scenario") and not equipment.get("unmerged"):
        scenario_name = equipment.get("scenario_name")
        revision_no = equipment.get("revision_no")
        named = (
            f"「{_short(scenario_name.strip())}」"
            if isinstance(scenario_name, str) and scenario_name.strip()
            else ""
        )
        number = f" r{revision_no}" if isinstance(revision_no, int) else ""
        assume.append(
            item(
                "assume",
                AVAILABLE_EQUIPMENT_STATUS,
                "설비 시나리오",
                f"가정 {named}{number}".strip(),
                "설비 가정",
            )
        )
    percent = st.session_state.get(UPEH_ASSUMPTION_PERCENT_KEY)
    if isinstance(percent, int | float) and percent != UPEH_ASSUMPTION_DEFAULT_PERCENT:
        assume.append(
            item(
                "assume",
                PROCESS_CAPA_DETAIL,
                PROCESS_CAPA_DETAIL.title,
                f"UPEH 가정 {percent:g}%",
                "UPEH 가정",
            )
        )
    return [*lose, *keep, *assume]
