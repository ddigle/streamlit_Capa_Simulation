# Purpose: 머리 띠 아래 화면 탭 줄을 그리고 고르기·닫기·고정 트리거를 탭 목록·이동 대기 칸에 옮긴다.

"""이 접속에서 연 화면들의 탭 줄(2026-10-24 사용자 결정).

**`app.py` 에서만 불러온다.** 모듈을 읽을 때 Components v2 를 등록하므로, 첫 AppTest 실행보다 먼저
올라오면 실행 안에서 「미등록」이다(`tests/test_benchmark_home.py`). 상태와 규칙은
`page_tabs_state.py` 이고, 여기는 그리기와 콜백뿐이다.

- **자리.** `app.py` 가 조건 팝업 호스트 칸 바로 뒤, 페이지보다 앞에서 매 앱 전체 회차 고정 key
  (`PAGE_TABS_COMPONENT_KEY`)로 그린다. 그 앞 본문 칸은 모두 늘 서는 칸이라 순번이 회차마다 같고,
  `navigation.run()` 밖이라 요소 id 에 주 스크립트 해시가 들어가 모든 화면에서 같은 요소다 — 화면을
  옮겨도 다시 마운트되거나 깜빡이지 않는다. 프래그먼트로 감싸지 않는다 — 프래그먼트 안의 트리거는
  돌고 있는 앱 전체 실행을 끊지 못해, HOME 첫 계산 중에 누른 탭이 그 계산을 기다린다.
- **DB 를 읽지 않는다.** data 는 세션 목록·`PageSpec` 상수·세션 판정뿐이다. 회차마다 바뀌는 값(시각·
  카운터)을 싣지 않아 열기·닫기·고정·점이 바뀔 때만 data 가 달라진다.
- **콜백은 칸만 적는다.** 고르기는 이동 대기 칸, 닫기·고정은 목록 칸(지금 탭을 닫으면 이웃을
  대기 칸에도). `st.switch_page` 는 `app.py` 본문이 부른다(`page_tabs_state.switch_to_queued_tab`).
  콜백에서 토스트를 내지 않는다(토스트 자리 규칙, AGENTS 9장).
- **탭 상한은 옮기기 전에 막는다.** JS 는 본 문서에서 돈다(iframe 이 아니다). 탭이 상한이면
  사이드바·본문의 화면 링크(`stPageLink-NavLink`) 누름을 문서 capture 단계에서 Streamlit 보다
  먼저 받아, 열린 탭이 아닌 화면이면 이동을 막고 그 자리에서 알린다. 서버가 옮긴 뒤
  되돌리면(`switch_to_queued_tab`) Streamlit 프런트가 두 화면을 `pushState` 로 쌓아 뒤로가기가 그
  화면에 갇힌다. 그래서 data 에 상한과 모든 화면의 주소·이름을 싣는다. 뒤로·앞으로가기는 막지
  못한다 — Streamlit 의 `popstate` 처리기가 먼저 돈다. 탭 10개에서 닫은 탭의 기록으로 뒤로가면
  서버가 되돌리고, 탭 하나를 닫을 때까지 그 기록 앞으로 가지 못한다(README·런북 7-7).
- **화면을 옮기면 기록은 한 칸.** 서버가 주소 인자를 바꾸면(`st.query_params` 쓰기·지우기,
  `st.switch_page` 의 인자 다시 적기) 프런트가 지금 경로로 기록을 한 칸 쌓는다 — `st.switch_page` 는
  떠나는 화면 경로로 한 칸 먼저 쌓았고, 링크 인자를 받아 지우는 화면(공정 Capa 상세·Space·제약
  시뮬레이션)은 인자 달린 칸 뒤에 또 쌓아 뒤로가기가 그 화면에 갇혔다. JS 가 문서의
  `history.pushState` 를 한 번 감싸 같은 경로의 쌓기를 **늘** 칸 바꾸기로 돌린다(`<tabs-history>`) —
  탭 줄 누름뿐 아니라 본문 단추·HOME 칸·링크 모두다. 탭 줄은 앱 전체 회차마다 페이지보다 먼저
  그리므로 첫 회차 뒤로는 모든 화면이 이 처리기를 지난다.
- **탭 누름은 한 번에 하나.** 다른 탭 고르기·지금 탭 닫기는 트리거를 보내기 전에 JS 가 누름
  기다림을 건다. 옮긴 화면의 탭 줄이 오고 그 회차가 다 돌기 전에 누른 탭은 마지막 것만 기다렸다
  보낸다(`<tabs-queue>`) — 그 사이 보낸 누름은 프런트가 떠나는 화면 주소로 회차를 청하거나 옮긴 화면
  부품의 회차 요청과 서버에서 합쳐지며 트리거 값을 잃어 둘 다 먹히지 않았다.
- **그림자 DOM**(`isolate_styles` 기본값). 팝업 안이 아니라 포커스 순서 의무가 걸리지 않고, 따라하기
  가이드의 `document.querySelectorAll` 에도 걸리지 않는다. 색은 등록 CSS 의 `--st-*` 변수와 data 의
  팔레트로만 쓴다.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Any

import streamlit as st

from capa_simulation.components.equipment_data_workspace import (
    has_unsaved_equipment_edits,
    pending_fab_layout,
    small_editor_edits,
)
from capa_simulation.components.past_data_management import past_data_has_pending
from capa_simulation.components.pick_edit_table import table_has_edits
from capa_simulation.components.scenario_edit_bar import pending_edit_pages
from capa_simulation.components.scenario_management import LIST_EDITOR_KEY, REVISION_EDITOR_KEY
from capa_simulation.components.space_floor_list import floor_state_draft_pending
from capa_simulation.design import tokens
from capa_simulation.navigation import (
    ALL_SPECS,
    AVAILABLE_EQUIPMENT_STATUS,
    HOME,
    SCENARIO_MANAGEMENT,
    SPACE_STATUS,
    NavigationPages,
    PageSpec,
)
from capa_simulation.page_tabs_state import (
    LIMIT_NOTICE,
    MAX_TABS,
    PAGE_TABS_COMPONENT_KEY,
    TabStrip,
    closed,
    load_strip,
    pinned_to,
    pop_fresh_notice,
    queue_switch,
    store_strip,
    switch_to_queued_tab,
    tab_label,
    tabs_epoch,
)
from capa_simulation.process_detail_state import PROCESS_DETAIL_REQUEST_KEY

_ASSETS = Path(__file__).with_name("page_tabs_assets")

_PAGE_TABS = st.components.v2.component(
    "capa_page_tabs",
    html=(_ASSETS / "page_tabs.html").read_text(encoding="utf-8"),
    css=(_ASSETS / "page_tabs.css").read_text(encoding="utf-8"),
    js=(_ASSETS / "page_tabs.js").read_text(encoding="utf-8"),
)

# 탭 줄이 쓰는 글. `{label}`·`{list}`·`{max}` 는 JS 가 채운다. 핀 단추 이름은 고정 여부와 상관없이
# 「{label} 고정」 하나다 — 상태는 `aria-pressed` 가 말한다(이름까지 바꾸면 읽기 도구가 두 번
# 말한다).
TEXT = {
    "nav": "열린 화면",
    "close": "{label} 닫기",
    "pin": "{label} 고정",
    "dirty": "저장·적용하지 않은 것이 있습니다",
    "leave": "적용하지 않은 편집이 사라집니다 — {list}\n이 화면을 떠날까요?",
    "limit": LIMIT_NOTICE,
}
_SPECS: dict[str, PageSpec] = {spec.path: spec for spec in ALL_SPECS}
_SPACE_PAGE_FILE = Path(SPACE_STATUS.path).name
_EQUIPMENT_PAGE_FILE = Path(AVAILABLE_EQUIPMENT_STATUS.path).name
# Space 층 사용 편집 초안(`사용 편집` 토글 + 세션 초안)의 떠나기 확인 이름 — 편집표 몫과 같은
# 「제목 · 이름」 꼴이다.
FLOOR_STATE_LEAVE_LABEL = f"{SPACE_STATUS.title} · 층 사용 편집"


def tab_icon(spec: PageSpec) -> str:
    """Material 아이콘 이름(`:material/scale:` → `scale`). HOME 은 아이콘이 없어 `home` 이다."""
    if spec.icon and spec.icon.startswith(":material/") and spec.icon.endswith(":"):
        return spec.icon[len(":material/") : -1]
    return "home" if spec == HOME else ""


def _tooltip(spec: PageSpec, note: str) -> str:
    return f"{spec.title} — {note}" if note else spec.title


def _page_path(page_file: str) -> str:
    return f"app_pages/{page_file}"


def page_unsaved_marks(page_file: str | None) -> dict[str, str]:
    """점을 찍을 화면(path → 풍선 글). 세션만 읽는다 — DB·캐시·셀 비교를 하지 않는다.

    탭 줄은 페이지보다 먼저 그리므로 「앞 회차 등록부 + 지금 세션 값」으로 정한다(사이드바 「적용 전
    편집」 줄·테마 표지와 같은 때맞춤). 편집이 사는 자리에 따라 점이 갈린다.

    - 붙여넣기 대기·설비 편집본·Past Data 초안·시나리오 관리 표 초안은 세션 칸이라 탭을 옮겨도 남아
      **어느 화면에서나** 그 탭에 찍는다.
    - 편집표(`st.data_editor`)의 적용 전 편집은 위젯 상태라 화면을 떠나면 사라진다. **지금
      화면에만** 찍고, 떠날 때 묻는다(`leave_notice`).
    - Space 층 사용 편집 초안(`floor_state_draft_pending`)도 같다 — 초안은 세션 칸이지만 `사용 편집`
      토글이 위젯 상태라 화면을 떠나면 꺼진 채 돌아와 초안을 버린다. Space 가 지금 화면일 때만
      찍고 떠날 때 묻는다(테마 표지도 이 점으로 본다).
    - 가용설비 현황 설비 마스터 탭의 작은 편집표 둘(`small_editor_edits` — 기존 보유대수·비가동
      일정)도 편집표라 지금 화면일 때만 찍고 떠날 때 묻는다. 설비 마스터 **표**의 편집은 편집본(세션
      칸)이라 위 「설비 편집본」 점이다(떠나도 사라지지 않는다).
    - 설비 편집본은 가용설비 현황·Space 현황이 함께 쓰는 한 벌이라 두 탭에 함께 찍는다(세대 기준이라
      되돌린 편집에도 남는다 — 테마 표지와 같은 오탐).
    - 넣지 않는 것: 적용했지만 저장하지 않은 시나리오(머리 띠·사이드바 배지가 말한다. 어느 화면이
      적용했는지 기록도 없다), Cut-off 초안(판정 함수가 없다), Qual 계산기(저장 개념이 없다).
    """
    marks: dict[str, list[str]] = {}

    def mark(path: str, note: str) -> None:
        marks.setdefault(path, []).append(note)

    for page, edits in pending_edit_pages(page_file).items():
        mark(_page_path(page), "적용 전 편집: " + ", ".join(edits.labels))
    if has_unsaved_equipment_edits() or pending_fab_layout() is not None:
        for spec in (AVAILABLE_EQUIPMENT_STATUS, SPACE_STATUS):
            mark(spec.path, "저장하지 않은 설비 편집")
    if past_data_has_pending():
        mark(HOME.path, "저장하지 않은 Past Data")
    if table_has_edits(LIST_EDITOR_KEY) or table_has_edits(REVISION_EDITOR_KEY):
        mark(SCENARIO_MANAGEMENT.path, "저장하지 않은 목록 편집")
    if page_file == _SPACE_PAGE_FILE and floor_state_draft_pending():
        mark(SPACE_STATUS.path, "저장하지 않은 층 사용 편집")
    small = _equipment_small_editors(page_file)
    if small:
        mark(AVAILABLE_EQUIPMENT_STATUS.path, "적용 전 편집: " + ", ".join(small))
    return {path: " · ".join(notes) for path, notes in marks.items()}


def _equipment_small_editors(page_file: str | None) -> list[str]:
    """가용설비 현황 설비 마스터 탭 작은 편집표(기존 보유대수·비가동 일정)의 적용 전 편집 — 위젯
    상태라 화면을 떠나면 사라진다(지금 화면일 때만). 「제목 · 이름」 꼴."""
    if page_file != _EQUIPMENT_PAGE_FILE:
        return []
    return [f"{AVAILABLE_EQUIPMENT_STATUS.title} · {name}" for name in small_editor_edits()]


def leave_notice(page_file: str | None) -> str:
    """지금 화면을 떠나면 사라지는 편집(편집표 몫과 Space 층 사용 편집 초안)을 이은 글. 없으면 빈
    글자 — 탭 줄이 묻지 않는다.

    붙여넣기 대기·설비 편집본처럼 세션에 남는 것은 넣지 않는다(떠나도 사라지지 않는다).
    """
    if page_file is None:
        return ""
    edits = pending_edit_pages(page_file).get(page_file)
    names = [] if edits is None else list(edits.editors)
    if page_file == _SPACE_PAGE_FILE and floor_state_draft_pending():
        names.append(FLOOR_STATE_LEAVE_LABEL)
    names.extend(_equipment_small_editors(page_file))
    return ", ".join(names)


def tabs_data(
    strip: TabStrip,
    *,
    active: str | None,
    hrefs: Mapping[str, str],
    marks: Mapping[str, str],
    leave: str,
    epoch: int,
    notice: tuple[int, str] | None,
) -> dict[str, Any]:
    """탭 줄 data. 같은 목록·점이면 회차마다 같은 값이다(시각·카운터를 싣지 않는다).

    `pages` 는 등록된 모든 화면의 주소(`url_path` — HOME 은 빈 글자) → 탭 이름이다. JS 가 상한에서
    화면 링크 누름을 거를 때 아는 화면인지와 알림에 쓸 이름을 여기서 읽는다(모듈 설명).
    """
    tabs = []
    for path in strip.paths:
        spec = _SPECS.get(path)
        if spec is None:
            continue
        note = marks.get(path, "")
        tabs.append(
            {
                "id": path,
                # 2단계(떠 있는 창) 대비 — 그 화면의 주소. HOME 은 기본 페이지라 빈 글자다.
                "href": hrefs.get(path, ""),
                "label": tab_label(spec),
                "title": _tooltip(spec, note),
                "icon": tab_icon(spec),
                "pinned": strip.is_pinned(path),
                "closable": strip.closable(path),
                "dirty": bool(note),
            }
        )
    return {
        "tabs": tabs,
        "active": active or "",
        "epoch": epoch,
        "leave": leave,
        "notice": None if notice is None else {"id": notice[0], "text": notice[1]},
        "max": MAX_TABS,
        "pages": {hrefs[path]: tab_label(spec) for path, spec in _SPECS.items() if path in hrefs},
        "palette": {"pending": tokens.PENDING_MARK},
        "text": TEXT,
    }


def _payload(name: str) -> Mapping[str, Any] | None:
    """콜백 안에서 받은 트리거 값. 매핑 꼴도 속성 꼴도 받는다(`space_layout_editor` 와 같다)."""
    state = st.session_state.get(PAGE_TABS_COMPONENT_KEY)
    value = state.get(name) if isinstance(state, Mapping) else getattr(state, name, None)
    return value if isinstance(value, Mapping) else None


def _payload_id(name: str) -> str | None:
    payload = _payload(name)
    value = None if payload is None else payload.get("id")
    return value if isinstance(value, str) else None


def _on_select() -> None:
    """`select` — 열린 탭이면 이동 대기 칸에 적는다. 지금 화면이면 `app.py` 가 걸러 옮기지 않는다.

    epoch 는 보지 않는다 — id 로 정하는 멱등 동작이라 빠른 두 번 누름도 마지막 누름이 맞다. 옮기는
    동안(옮긴 화면의 탭 줄이 오고 그 회차가 다 돌기 전) 누른 탭은 JS 가 기다렸다 마지막 것만
    보낸다(`<tabs-queue>`) — 그 사이 보낸 트리거는 서버에서 다른 회차 요청과 합쳐지며 떨어지거나(이
    콜백이 값을 받지 못한다) 떠나는 화면 주소로 가 서버가 그 화면으로 되돌아갔다."""
    target = _payload_id("select")
    if target is not None and target in load_strip().paths:
        queue_switch(target)


def _on_close(active: str | None) -> None:
    """`close` — 목록에서 뺀다. 지금 탭이면 이웃을 대기 칸에. 고정·마지막 탭·없는 id 는 그대로 둔다.

    `active` 는 이 탭 줄을 그린 회차의 지금 화면이다. 빠르게 둘을 닫아도 둘 다 닫힌다(id 기준)."""
    target = _payload_id("close")
    if target is None:
        return
    strip, neighbour = closed(load_strip(), target, active)
    store_strip(strip)
    if neighbour is not None:
        queue_switch(neighbour)


def _on_pin() -> None:
    """`pin` — `{id, pinned}` 로 고정하거나 푼다. 고정 탭은 왼쪽에 모인다."""
    payload = _payload("pin")
    target = None if payload is None else payload.get("id")
    pinned = None if payload is None else payload.get("pinned")
    if isinstance(target, str) and isinstance(pinned, bool):
        store_strip(pinned_to(load_strip(), target, pinned))


def route_page_tabs(
    current: PageSpec | None, *, pages: NavigationPages, previous_url: object
) -> None:
    """탭 줄 콜백이 적어 둔 이동과 탭 상한을 처리한다. `st.navigation()` 바로 뒤에서 부른다.

    `previous_url` 은 직전 회차가 그린 화면의 주소(`app.SIDEBAR_PAGE_KEY`)다 — 상한에 걸린 이동을 그
    화면으로 되돌린다. 되돌릴 때는 HOME 칸 클릭이 공정 Capa 상세로 넘기던 전달 칸도 버린다.
    """
    previous = pages.spec_for(previous_url) if isinstance(previous_url, str) else None
    switch_to_queued_tab(
        None if current is None else current.path,
        current_title="" if current is None else tab_label(current),
        previous_path=None if previous is None else previous.path,
        handoff_keys=(PROCESS_DETAIL_REQUEST_KEY,),
    )


def render_page_tabs(
    current: PageSpec | None,
    *,
    pages: NavigationPages,
    marks: Mapping[str, str],
    leave: str = "",
) -> None:
    """탭 줄을 그린다. `st.navigation()` 뒤라야 한다 — 탭 주소(`url_path`)가 그 뒤에야 생긴다.

    `marks` 는 점을 찍을 화면(path → 풍선 글), `leave` 는 지금 화면에서 떠나면 사라지는
    편집(묻는 글)이다.
    """
    active = None if current is None else current.path
    _PAGE_TABS(
        key=PAGE_TABS_COMPONENT_KEY,
        data=tabs_data(
            load_strip(),
            active=active,
            hrefs={spec.path: page.url_path for page, spec in pages.specs},
            marks=marks,
            leave=leave,
            epoch=tabs_epoch(),
            notice=pop_fresh_notice(),
        ),
        on_select_change=_on_select,
        on_close_change=partial(_on_close, active),
        on_pin_change=_on_pin,
        width="stretch",
    )
