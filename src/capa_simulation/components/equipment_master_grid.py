# Purpose: 설비 마스터 표·오른쪽 칸 칸막이 Components v2 를 그리고 받은 출납·트리거를 넘긴다.

"""가용설비 현황 「설비 마스터」 탭 표의 그리기와 받기(개편 명세 6장).

**한 번 등록하고 세 자리에 다른 key 로 마운트한다** — 불러오기(`LOADER_KEY`)·표(`GRID_KEY`)·오른쪽
칸 (`side_key(panel)` — 호기 상세·새 호기·저장 전 변경, 한 회차에 하나). key 가 요소의 정체라
data 가 바뀌어도 다시 마운트되지 않는다. 다만 그 앞 형제의 순번이 밀리면 다시 마운트되어 보내지 않은
출납·고름을 잃으므로, 탭 본문은 마운트 앞의 생겼다 사라지는 칸을 늘 서 있는 칸 안에 그린다(명세
2-3).

- **data** 는 `services/equipment_grid` 가 만든 dict 에 팔레트(`_palette`)만 더한다. 색은 등록 CSS
  에 적지 않고 회차마다 토큰으로 넘긴다 — 등록 CSS 는 테마를 따라오지 않는다.
- **편집본을 바꾸는 조작은 상태 값 `outbox`** 다(``{"mount", "ops": [...]}`` — 반영되지 않은 조작
  전부 — 「새 호기」 칸의 「호기 추가」 도 `add` op 다). 트리거는 다음 트리거에 덮여 잃을 수
  있어(1.63 의 위젯 상태 합치기는 CCv2 트리거의 앞 값을 살리지 않는다) 잃어도 되는 화면 조작만
  트리거로 둔다: 불러오기 `load`·`clear`·`new`·`dialog`, 표 `open`·`unload`, 오른쪽 칸 `open`·
  `goto`·`copy`(가져오기·「이 호기로 새 호기 만들기」).
- **「새 호기」 초안은 상태 값 `draft`** 다(``{"seq", "values": 39칸 글, "propagate"}`` — 칸을
  확정할 때마다 전부). 파이썬이 세션 초안으로 적고 그 초안으로 체크 상자·칸 오류를 다시 낸다.
  편집본을 바꾸지 않으므로 잃어도 다음 확정이 덮는다.
- **받기** 는 `on_<이름>_change` 콜백이다(본문보다 먼저 돈다). 콜백은 그 key 의 세션 값을 읽어 꼴을
  거른 뒤 화면 쪽이 넘긴 처리 함수를 부른다. 표가 그린 회차의 `view` 와 다른 트리거(목록이 다시 선
  뒤 누른 옛 줄)는 버린다. 출납은 두 마운트(표·오른쪽 칸)가 함께 보낼 수 있어 처리 함수가
  `outbox_value` 로 두 key 를 다 읽어 한 번에 반영한다(`equipment_grid.pending_ops` 가 `(at, mount,
  seq)` 로 늘어놓는다). 콜백 안에서는 `st.rerun()`·`st.switch_page` 를 부르지 않는다.
- **그림자 DOM**(`isolate_styles` 기본값) — 팝업 안에 마운트하지 않는다(AGENTS 9장 「스크립트와
  컴포넌트」).

**두 칸 배치**(왼쪽 표 · 오른쪽 칸)는 테두리 하나의 key 칸(`FRAME_KEY`) 안 key 가로 칸(`SPLIT_KEY` ›
`LEFT_KEY`·`RIGHT_KEY`)이고 서식은 페이지 CSS 한 덩이(`side_layout_style`)다 — 오른쪽 칸은 편집기
영역 안의 서브페이지다. 오른쪽 칸 맨 앞의 작은 별도 등록 `capa_equipment_side_splitter`
(`render_side_splitter`)가 칸막이와 칸 머리의 접기 단추, 접었을 때 편집기 영역 오른쪽 위에 떠 있는
단추를 그린다 — 끌어 폭 바꾸기(최소·최대 한계 `SIDE_*`), 접기·펴기. 폭·접힘은 브라우저 저장소와
`<html>` 의 CSS 변수(`--emd-side-w`·`--emd-top`)·속성(`data-emd-side`)에만 두고 파이썬으로 보내지
않는다(AGENTS 9장 「브라우저 전용 보기 상태」). 오른쪽 칸 본문(`SIDE_BODY_KEY` — 고르기 아래
전부)은 창 높이로 정한 상한 안에서 스크롤한다.

브라우저 쪽(HTML·CSS·JS)은 `equipment_master_grid_assets/` 의 파일이다. 모듈을 읽을 때 등록하므로 이
모듈은 탭 본문(그 탭이 열린 회차)에서만 불러온다 — 시험은 `tests/conftest.py` 의 대역이 바꾼다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Final, Literal

import streamlit as st

from capa_simulation.design import tokens
from capa_simulation.page_tabs_state import PAGE_TABS_COMPONENT_KEY

_ASSETS = Path(__file__).with_name("equipment_master_grid_assets")

LOADER_KEY: Final = "equipment_grid_loader"
GRID_KEY: Final = "equipment_grid_table"
SIDE_KEY_PREFIX: Final = "equipment_grid_side"

SidePanel = Literal["detail", "new", "changes"]
SIDE_PANELS: Final[tuple[SidePanel, ...]] = ("detail", "new", "changes")

# 불러오기 트리거의 갈래(설비명·공정·조건·일정 확인·전체). 「전체」 는 id 를 싣지 않는다 — 파이썬이
# 상한과 설비명 자연 차례로 고른다(`equipment_grid.all_load_ids`).
LOAD_KINDS: Final = frozenset({"names", "process", "conditions", "alerts", "all"})
# 트리거에 실린 못 찾은 낱말·꼬리표 글의 상한(브라우저가 이미 자르지만 서버도 자른다).
_MISSING_LIMIT = 50
_LABEL_LIMIT = 120
_DIALOGS = frozenset({"import"})
_GOTO_TABLES = frozenset({"비가동 일정", "기존 보유대수"})

_GRID = st.components.v2.component(
    "capa_equipment_master_grid",
    html=(_ASSETS / "grid.html").read_text(encoding="utf-8"),
    css=(_ASSETS / "grid.css").read_text(encoding="utf-8"),
    js=(_ASSETS / "grid.js").read_text(encoding="utf-8"),
)
# 오른쪽 칸 칸막이 — 표와 따로 등록한다(data 가 작고 거의 늘 같아 표 등록 JS 를 다시 싣지 않는다).
_SPLITTER = st.components.v2.component(
    "capa_equipment_side_splitter",
    html='<div class="ess"></div>',
    css=(_ASSETS / "splitter.css").read_text(encoding="utf-8"),
    js=(_ASSETS / "splitter.js").read_text(encoding="utf-8"),
)


def side_key(panel: SidePanel) -> str:
    """오른쪽 칸 마운트 key — 칸(호기 상세·저장 전 변경)마다 따로다."""
    return f"{SIDE_KEY_PREFIX}_{panel}"


def _palette() -> dict[str, str]:
    """색은 회차마다 토큰에서 읽는다 — 테마를 바꾸면 같은 표가 새 색을 받는다(CSS
    `var(--emg-*)`)."""
    return {
        "font": tokens.FONT_FAMILY,
        "text": tokens.TEXT,
        "muted": tokens.TEXT_MUTED,
        "surface": tokens.SURFACE,
        "subtle": tokens.SURFACE_SUBTLE,
        "header": tokens.HEADER_BACKGROUND,
        "border": tokens.BORDER,
        "border-strong": tokens.BORDER_STRONG,
        "accent": tokens.ACCENT,
        "on-accent": tokens.ACCENT_TEXT,
        "changed-fill": tokens.GRID_CHANGED_FILL,
        "changed-mark": tokens.GRID_CHANGED_MARK,
        "error-fill": tokens.GRID_ERROR_FILL,
        "error-line": tokens.GRID_ERROR_LINE,
        "warn-line": tokens.GRID_WARN_LINE,
        "lock-fill": tokens.GRID_LOCK_FILL,
        "scenario-head": tokens.GRID_SCENARIO_HEAD,
        "layout-head": tokens.GRID_LAYOUT_HEAD,
        "selected-fill": tokens.GRID_SELECTED_FILL,
        "new-fill": tokens.GRID_NEW_FILL,
    }


def _with_palette(data: Mapping[str, Any]) -> dict[str, Any]:
    return {**data, "palette": _palette()}


# ------------------------------------------------------------------ 받은 값 읽기


def _state_value(key: str, name: str) -> object:
    """`st.session_state[key]` 의 `name` — 결과 객체는 매핑으로도 속성으로도 온다(대역은 속성)."""
    state = st.session_state.get(key)
    if isinstance(state, Mapping):
        return state.get(name)
    return getattr(state, name, None)


def outbox_value(key: str) -> object:
    """그 마운트의 상태 값 `outbox`(없으면 None). 처리 함수가 두 마운트를 함께 읽는다."""
    return _state_value(key, "outbox")


def outbox_mount(value: object) -> str | None:
    """출납의 마운트 id(꼴이 다르면 None) — 그 key 의 `ack` 를 그 마운트에 단다."""
    if isinstance(value, Mapping) and isinstance(value.get("mount"), str):
        return str(value["mount"])
    return None


def _texts(value: object, limit: int | None = None) -> list[str]:
    if not isinstance(value, list):
        return []
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return items[:limit] if limit is not None else items


@dataclass(frozen=True)
class LoadRequest:
    """불러오기 한 번 — 갈래, 브라우저가 찾은 행 id, 못 찾은 낱말, 토스트 머리 글."""

    kind: str
    ids: tuple[str, ...]
    missing: tuple[str, ...]
    label: str


def load_request(payload: object) -> LoadRequest | None:
    """`load` 트리거 값을 거른다(모르는 갈래면 None). 행 id 가 실제로 있는지는 받는 쪽이 본다."""
    if not isinstance(payload, Mapping) or payload.get("kind") not in LOAD_KINDS:
        return None
    label = payload.get("label")
    return LoadRequest(
        kind=str(payload["kind"]),
        ids=tuple(_texts(payload.get("ids"))),
        missing=tuple(_texts(payload.get("missing"), _MISSING_LIMIT)),
        label=label.strip()[:_LABEL_LIMIT] if isinstance(label, str) and label.strip() else "",
    )


def _dispatch_load(key: str, handler: Callable[[LoadRequest], None]) -> None:
    request = load_request(_state_value(key, "load"))
    if request is not None:
        handler(request)


def _dispatch_signal(key: str, name: str, handler: Callable[[], None] | None) -> None:
    """값이 dict 인 트리거(목록 비우기·새 호기)를 받으면 부른다."""
    if handler is not None and isinstance(_state_value(key, name), Mapping):
        handler()


def _dispatch_dialog(key: str, handler: Callable[[str], None]) -> None:
    payload = _state_value(key, "dialog")
    if isinstance(payload, Mapping) and payload.get("name") in _DIALOGS:
        handler(str(payload["name"]))


def _dispatch_open(key: str, view: str | None, handler: Callable[[str], None]) -> None:
    """`open`(``{"view"?, "id"}``). 표는 그린 회차의 `view` 와 같을 때만, 오른쪽 칸은 view 없이
    받는다."""
    payload = _state_value(key, "open")
    if not isinstance(payload, Mapping):
        return
    if view is not None and payload.get("view") != view:
        return
    row_id = payload.get("id")
    if isinstance(row_id, str) and row_id.strip():
        handler(row_id.strip())


def _dispatch_unload(key: str, view: str, handler: Callable[[list[str]], None]) -> None:
    payload = _state_value(key, "unload")
    if isinstance(payload, Mapping) and payload.get("view") == view:
        ids = _texts(payload.get("ids"))
        if ids:
            handler(ids)


@dataclass(frozen=True)
class DraftValue:
    """「새 호기」 칸이 보낸 초안 — 번호(브라우저가 확정마다 올린다), 39칸 글, 함께 넣기."""

    seq: int
    values: tuple[str, ...]
    propagate: bool


def draft_value(payload: object, size: int) -> DraftValue | None:
    """`draft` 상태 값(``{"seq", "values", "propagate"}``)을 거른다 — 꼴이 다르면 None."""
    if not isinstance(payload, Mapping):
        return None
    seq, values = payload.get("seq"), payload.get("values")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        return None
    if not isinstance(values, list) or len(values) != size:
        return None
    if not all(isinstance(item, str) for item in values):
        return None
    return DraftValue(seq, tuple(values), payload.get("propagate") is True)


@dataclass(frozen=True)
class CopyRequest:
    """가져오기 한 번 — 「이 호기로 새 호기 만들기」(`row_id`) 또는 「비슷한 호기에서 값
    가져오기」(`query` — 그때 브라우저 초안 `draft` 위에 얹는다)."""

    row_id: str | None = None
    query: str = ""
    draft: DraftValue | None = None


def copy_request(payload: object, size: int) -> CopyRequest | None:
    """`copy` 트리거 값을 거른다(``{"id"}`` 또는 ``{"query", "draft": {...}}``)."""
    if not isinstance(payload, Mapping):
        return None
    row_id = payload.get("id")
    if isinstance(row_id, str) and row_id.strip():
        return CopyRequest(row_id=row_id.strip())
    query = payload.get("query")
    if isinstance(query, str) and query.strip():
        return CopyRequest(
            query=query.strip()[:_LABEL_LIMIT], draft=draft_value(payload.get("draft"), size)
        )
    return None


def _dispatch_draft(key: str, size: int, handler: Callable[[DraftValue], None] | None) -> None:
    value = draft_value(_state_value(key, "draft"), size)
    if handler is not None and value is not None:
        handler(value)


def _dispatch_copy(key: str, size: int, handler: Callable[[CopyRequest], None] | None) -> None:
    request = copy_request(_state_value(key, "copy"), size)
    if handler is not None and request is not None:
        handler(request)


def _dispatch_goto(key: str, handler: Callable[[str, str], None]) -> None:
    """`goto`(``{"table", "unit"}``) — 표 고르기를 그 표로, 그 표 설비명 거르기를 그 이름으로."""
    payload = _state_value(key, "goto")
    if not isinstance(payload, Mapping) or payload.get("table") not in _GOTO_TABLES:
        return
    unit = payload.get("unit")
    handler(str(payload["table"]), unit.strip() if isinstance(unit, str) else "")


# ------------------------------------------------------------------ 그리기


def render_grid_loader(
    data: Mapping[str, Any],
    *,
    on_load: Callable[[LoadRequest], None],
    on_clear: Callable[[], None],
    on_dialog: Callable[[str], None],
    on_new: Callable[[], None] | None = None,
    key: str = LOADER_KEY,
) -> None:
    """불러오기 자리 — 설비명 찾기(부분 일치·목록)·공정·조건(사용자 R1)·일정 확인 필요·전체
    불러오기, 「엑셀·CSV로 한꺼번에」 팝업 열기, 불러온 수·못 찾은 설비명. 목록이 비면 빈 안내와
    단추가 선다."""
    _GRID(
        key=key,
        data=_with_palette(data),
        on_load_change=partial(_dispatch_load, key, on_load),
        on_clear_change=partial(_dispatch_signal, key, "clear", on_clear),
        on_new_change=partial(_dispatch_signal, key, "new", on_new),
        on_dialog_change=partial(_dispatch_dialog, key, on_dialog),
        width="stretch",
    )


def render_grid_table(
    data: Mapping[str, Any],
    *,
    on_outbox: Callable[[], None],
    on_open: Callable[[str], None],
    on_unload: Callable[[list[str]], None],
    key: str = GRID_KEY,
) -> None:
    """표 자리 — 칸 묶음·정렬(브라우저 몫), 칸 고치기·엑셀 여러 칸 붙여넣기·고르기·한꺼번에 고치기·
    지우기·되살리기·토스트 되돌리기(출납), 설비명 누름(`open`)·목록에서 빼기(`unload`)."""
    view = str(data.get("view") or "")
    _GRID(
        key=key,
        data=_with_palette(data),
        on_outbox_change=on_outbox,
        on_open_change=partial(_dispatch_open, key, view, on_open),
        on_unload_change=partial(_dispatch_unload, key, view, on_unload),
        width="stretch",
    )


def render_grid_side(
    panel: SidePanel,
    data: Mapping[str, Any],
    *,
    on_outbox: Callable[[], None],
    on_open: Callable[[str], None],
    on_goto: Callable[[str, str], None],
    on_draft: Callable[[DraftValue], None] | None = None,
    on_copy: Callable[[CopyRequest], None] | None = None,
    columns: int = 39,
) -> None:
    """오른쪽 칸 — 「호기 상세」(묶음 다섯·그 호기 비가동·지우기/되살리기·「이 호기로 새 호기
    만들기」), 「새 호기」(체크 상자·가져오기·한 장 칸·「호기 추가」) 또는 「저장 전 변경」(수 넷·
    고칠 것·호기별 변경과 칸/호기 되돌리기). 고침·「호기 추가」 는 표와 같은 출납이고, 고칠 것 줄·
    호기 이름 누름은 `open`, 「비가동 일정 표에서 고치기」 는 `goto`, 가져오기는 `copy`, 새 호기
    초안은 상태 값 `draft` 다(`columns` 는 초안 칸 수 — 계약 39칸)."""
    key = side_key(panel)
    _GRID(
        key=key,
        data=_with_palette(data),
        on_outbox_change=on_outbox,
        on_open_change=partial(_dispatch_open, key, None, on_open),
        on_goto_change=partial(_dispatch_goto, key, on_goto),
        on_draft_change=partial(_dispatch_draft, key, columns, on_draft),
        on_copy_change=partial(_dispatch_copy, key, columns, on_copy),
        width="stretch",
    )


# 브라우저가 보내는 상태 값·트리거 이름(자산 시험이 JS 글자와 대조한다).
STATE_NAMES: Final = frozenset({"outbox", "draft"})
TRIGGER_NAMES: Final = frozenset(
    {"load", "clear", "new", "dialog", "open", "unload", "goto", "copy"}
)


# ------------------------------------------------------------------ 두 칸 배치 · 오른쪽 칸 폭

# 편집기 영역(테두리 칸)과 그 안 두 칸 줄(가로 칸)·두 칸, 표 위 작업 줄, 오른쪽 칸 고르기, 오른쪽 칸
# 본문(고르기 아래 전부 — 패널·저장 구획·저장 이력), 칸막이 마운트.
FRAME_KEY: Final = "equipment_master_frame"
SPLIT_KEY: Final = "equipment_master_split"
LEFT_KEY: Final = "equipment_master_left"
RIGHT_KEY: Final = "equipment_master_right"
TOOLS_KEY: Final = "equipment_master_tools"
SIDE_CHOICE_KEY: Final = "equipment_master_side_v1"
SIDE_BODY_KEY: Final = "equipment_master_side_body"
SPLITTER_KEY: Final = "equipment_master_side_splitter"

# 오른쪽 칸 폭 한계(2026-11-02 사용자 결정 「너비에 한계를 두고」 — 명세 15-2). 최소 360px
# 는 칸 머리 한 줄(「오른쪽 칸」 고르기 넷의 자연 폭 310px + 사이 6 + 접기 단추 28)에 칸막이 곁
# 여백 14 를 더한 값, 최대 760px 은 표에 줄의 40% 이상을 남기는 몫 60% 와 함께 건다. 좁은 줄에서는
# 몫(최소 40%)이 이긴다. 처음 폭은 옛 7:3 두 칸의 오른쪽 폭(30% − 28px)이다.
SIDE_MIN_PX: Final = 360
SIDE_MIN_SHARE: Final = 0.4
SIDE_MAX_PX: Final = 760
SIDE_MAX_SHARE: Final = 0.6
SIDE_DEFAULT_SHARE: Final = 0.3
SIDE_DEFAULT_OFFSET_PX: Final = 28
# 본문 높이 상한 = max(360px, 창 높이 − 붙는 높이 − 200px). 200px = 고르기 42 + 간격 16 +
# Streamlit 본문 아래 여백 약 140(1500×950 측정). 붙는 높이(`--emd-top`)는 칸막이가 화면 탭
# 줄이 붙었을 때의 아래 끝 + 8px 로 잰다(1.63 — 탭 줄 sticky top 52.5 + 높이 36 → 97px).
# 재기 전에는 그 측정값을 쓴다. 오른쪽 칸은 내용이 짧아도 머리(고르기 28 + 간격 14) + 이 상한만큼
# 높이를 잡는다 — 칸을 바꿔도 영역 높이가 뛰지 않고 칸막이를 경계선을 따라 잡을 수 있다.
SIDE_BODY_MIN_PX: Final = 360
SIDE_BODY_RESERVE_PX: Final = 200
SIDE_TOP_FALLBACK_PX: Final = 97
SIDE_HEAD_PX: Final = 42
# 칸막이를 잡는 폭 — 두 칸 경계선이 그 한가운데다. 표·오른쪽 칸은 경계선에서 각각 이만큼 띄운다.
SIDE_GUTTER_PX: Final = 16
SIDE_INSET_PX: Final = 14
# 본문 칸 스크롤 막대 자리(`scrollbar-gutter: stable`, 1.63 측정) — 편집기 영역 안쪽 여백(13px)으로
# 내보내 본문 내용의 오른쪽 끝이 칸 머리 접기 단추의 오른쪽 끝과 맞는다.
SIDE_SCROLLBAR_PX: Final = 10
# 칸 머리 접기 단추(고르기와 같은 높이)와 고르기 사이 간격 — 고르기 칸이 이만큼 자리를 비운다.
SIDE_TOGGLE_PX: Final = 28
SIDE_TOGGLE_GAP_PX: Final = 6
# 접은 동안 표 위 작업 줄이 비우는 오른쪽 자리 — 떠 있는 단추(가장 긴 칸 이름 「저장 전 변경」 89px,
# 측정)가 「내려받기」 를 덮지 않게.
SIDE_REOPEN_RESERVE_PX: Final = 112
# 떠 있는 단추를 품은 오른쪽 칸 감싸개의 쌓임 차례 — 표 머리(`.emg-head` 6) 위, 고치는 칸(8)·목록
# (9·30) 아래.
SIDE_REOPEN_Z_INDEX: Final = 7
# 이 창 폭 이하에서는 두 칸을 위아래로 쌓는다(옛 `st.columns` 와 같은 640px) — 칸막이·접기는 없다.
SIDE_STACK_MAX_PX: Final = 640


def side_bounds() -> dict[str, float]:
    """칸막이 data 의 폭 한계 — JS `clampWidth` 가 페이지 CSS clamp 와 같은 식으로 쓴다."""
    return {
        "minPx": SIDE_MIN_PX,
        "minShare": SIDE_MIN_SHARE,
        "maxPx": SIDE_MAX_PX,
        "maxShare": SIDE_MAX_SHARE,
        "defaultShare": SIDE_DEFAULT_SHARE,
        "defaultOffset": SIDE_DEFAULT_OFFSET_PX,
    }


def _percent(share: float) -> str:
    return f"{share * 100:g}%"


def side_width_rule() -> str:
    """오른쪽 칸 감싸개의 폭 — 창 폭이 바뀌어도 JS 없이 한계를 지킨다(칸막이는 `--emd-side-w`
    만 바꾼다)."""
    low = f"min({SIDE_MIN_PX}px, {_percent(SIDE_MIN_SHARE)})"
    default = f"calc({_percent(SIDE_DEFAULT_SHARE)} - {SIDE_DEFAULT_OFFSET_PX}px)"
    high = f"min({SIDE_MAX_PX}px, {_percent(SIDE_MAX_SHARE)})"
    return f"clamp({low}, var(--emd-side-w, {default}), {high})"


def side_layout_style() -> str:
    """두 칸 배치 CSS — 탭 본문이 회차마다 같은 글로 한 번 그린다(스타일만 든 `st.html` 이라
    이벤트 칸 한 자리).

    가로 칸의 flex 항목은 key 칸이 아니라 그것을 한 번 감싼 `stLayoutWrapper` 다(1.63 — Qual
    계산기와 같은 꼴). `:has()` 는 한 겹만 쓴다(겹치면 규칙 전체가 버려진다). `wrap=False` 가로
    칸은 스크롤 칸이 되어 sticky 가 줄 기준으로 잡히므로 줄에 `overflow: visible` 을 건다.
    테두리는 바깥 칸(`FRAME_KEY`) 하나이고 두 칸 경계선은 왼쪽 감싸개의 오른쪽 테두리다 — 왼쪽은 줄
    높이로 늘어나 경계선이 영역 끝까지 간다. 칸막이 마운트는 붙는(sticky) 오른쪽 감싸개를 기준으로
    경계선부터 칸 오른쪽 끝까지 덮는 절대 위치(흐름 높이 0)이고, 눌림은 칸막이·접기 단추만 받는다
    (`pointer-events`). 접힘(`data-emd-side="min"`)은 넓은 화면에서만 — 칸 자리가 0 이 되어 표가
    줄을 다 쓰고 떠 있는 단추만 남는다. 좁은 화면(쌓임)과 인쇄는 펼친 꼴이다.
    """
    wrapper = '[data-testid="stLayoutWrapper"]'
    left = f".st-key-{LEFT_KEY}"
    right = f".st-key-{RIGHT_KEY}"
    left_item = f"{wrapper}:has(> {left})"
    right_item = f"{wrapper}:has(> {right})"
    splitter = f".st-key-{SPLITTER_KEY}"
    choice = f".st-key-{SIDE_CHOICE_KEY}"
    tools = f".st-key-{TOOLS_KEY}"
    body = f".st-key-{SIDE_BODY_KEY}"
    folded = 'html[data-emd-side="min"]'
    top = f"var(--emd-top, {SIDE_TOP_FALLBACK_PX}px)"
    line = f"1px solid {tokens.BORDER}"
    half = SIDE_GUTTER_PX // 2
    body_cap = f"max({SIDE_BODY_MIN_PX}px, calc(100vh - {top} - {SIDE_BODY_RESERVE_PX}px))"
    return "".join(
        [
            "<style>",
            f".st-key-{SPLIT_KEY} {{ align-items: flex-start; overflow: visible; }}",
            f"{left} {{ flex: 1 1 0; min-width: 0; }}",
            (
                f"{left_item} {{ flex: 1 1 0; min-width: 0; align-self: stretch; "
                f"padding-right: {SIDE_INSET_PX}px; border-right: {line}; }}"
            ),
            (
                f"{right_item} {{ flex: 0 0 {side_width_rule()}; min-width: 0; "
                f"padding-left: {SIDE_INSET_PX}px; "
                f"position: sticky; top: {top}; align-self: flex-start; }}"
            ),
            f"{right} {{ min-height: calc({body_cap} + {SIDE_HEAD_PX}px); }}",
            (
                f"{splitter} {{ position: absolute; top: 0; bottom: 0; left: -{half}px; right: 0; "
                "width: auto; min-width: 0; max-width: none; z-index: 2; pointer-events: none; }"
            ),
            f"{choice} {{ padding-right: {SIDE_TOGGLE_PX + SIDE_TOGGLE_GAP_PX}px; }}",
            (
                f"{body} {{ width: calc(100% + {SIDE_SCROLLBAR_PX}px); max-width: none; "
                f"max-height: {body_cap}; "
                "overflow-y: auto; overflow-x: hidden; scrollbar-gutter: stable; }"
            ),
            f"@media screen and (width > {SIDE_STACK_MAX_PX}px) {{ ",
            f"{folded} {left_item} {{ padding-right: 0; border-right: none; }} ",
            (
                f"{folded} {right_item} {{ flex-basis: 0; width: 0; padding-left: 0; "
                f"z-index: {SIDE_REOPEN_Z_INDEX}; }} "
            ),
            f"{folded} {right} {{ min-height: 0; }} ",
            f"{folded} {right} > :not({splitter}) {{ display: none; }} ",
            f"{folded} {splitter} {{ left: auto; bottom: auto; width: 0; height: 0; }} ",
            f"{folded} {tools} {{ padding-right: {SIDE_REOPEN_RESERVE_PX}px; }} ",
            "}",
            f"@media (width <= {SIDE_STACK_MAX_PX}px) {{ ",
            f".st-key-{SPLIT_KEY} {{ flex-wrap: wrap; }} ",
            (
                f"{left_item} {{ flex: 1 1 100%; position: static; "
                "padding-right: 0; border-right: none; } "
            ),
            (
                f"{right_item} {{ flex: 1 1 100%; position: static; padding-left: 0; "
                f"padding-top: {SIDE_INSET_PX}px; border-top: {line}; }} "
            ),
            f"{right} {{ min-height: 0; }} ",
            f"{splitter} {{ display: none; }} ",
            f"{choice} {{ padding-right: 0; }} ",
            "}",
            "@media print { ",
            f"{right_item} {{ position: static; }} ",
            f"{right} {{ min-height: 0; }} ",
            f"{body} {{ width: 100%; max-height: none; overflow: visible; }} ",
            f"{splitter} {{ display: none; }} ",
            f"{choice} {{ padding-right: 0; }} ",
            "}",
            "</style>",
        ]
    )


def _splitter_palette() -> dict[str, str]:
    """칸막이 색 — 표와 같은 토큰(CSS `var(--ess-*)`). 등록 CSS 에는 색을 적지 않는다."""
    return {
        "font": tokens.FONT_FAMILY,
        "text": tokens.TEXT,
        "muted": tokens.TEXT_MUTED,
        "surface": tokens.SURFACE,
        "border": tokens.BORDER,
        "accent": tokens.ACCENT,
    }


def render_side_splitter(label: str, reveal: int) -> None:
    """오른쪽 칸 맨 앞의 칸막이 — 오른쪽 칸 왼쪽 끝을 끌어 폭을 바꾸고(두 번 누르면 처음 폭,
    키보드 ←·→·Home·End), 칸 머리의 › 로 접고 편집기 영역 오른쪽 위에 떠 있는 단추(지금 칸 이름
    `label`)를 눌러 편다. 받는 값이
    없다(상태 값·트리거 없음 — 회차를 부르지 않는다). `reveal` 은 표·오른쪽 칸이 오른쪽 칸을 연
    수(`equipment_master_tab._switch_side`) — 늘면 접힌 칸을 펴고 본문 칸(`SIDE_BODY_KEY`)을 맨
    위로 올린다(key 칸이라 다른 호기를 그려도 스크롤 자리가 남는다)."""
    _SPLITTER(
        key=SPLITTER_KEY,
        data={
            "palette": _splitter_palette(),
            "label": label,
            "reveal": reveal,
            "bounds": side_bounds(),
            "keys": {"row": SPLIT_KEY, "right": RIGHT_KEY, "body": SIDE_BODY_KEY},
            "cover": f".st-key-{PAGE_TABS_COMPONENT_KEY}",
        },
        width="stretch",
    )
