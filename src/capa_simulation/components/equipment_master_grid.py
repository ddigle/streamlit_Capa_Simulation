# Purpose: 설비 마스터 표 Components v2 를 세 자리에 그리고 받은 출납·트리거를 처리 함수에 넘긴다.

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
