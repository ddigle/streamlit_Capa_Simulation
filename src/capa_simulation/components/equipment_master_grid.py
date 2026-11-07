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
- **「새 호기」 초안은 상태 값 `draft`** 다(``{"seq", "values": 39칸 글}`` — 칸을 확정할 때마다
  전부). 파이썬이 세션 초안으로 적고 그 초안으로 체크 상자·칸 오류를 다시 낸다.
  편집본을 바꾸지 않으므로 잃어도 다음 확정이 덮는다.
- **받기** 는 `on_<이름>_change` 콜백이다(본문보다 먼저 돈다). 콜백은 그 key 의 세션 값을 읽어 꼴을
  거른 뒤 화면 쪽이 넘긴 처리 함수를 부른다. 표가 그린 회차의 `view` 와 다른 트리거(목록이 다시 선
  뒤 누른 옛 줄)는 버린다. 출납은 두 마운트(표·오른쪽 칸)가 함께 보낼 수 있어 처리 함수가
  `outbox_value` 로 두 key 를 다 읽어 한 번에 반영한다(`equipment_grid.pending_ops` 가 `(at, mount,
  seq)` 로 늘어놓는다). 콜백 안에서는 `st.rerun()`·`st.switch_page` 를 부르지 않는다.
- **그림자 DOM**(`isolate_styles` 기본값) — 팝업 안에 마운트하지 않는다(AGENTS 9장 「스크립트와
  컴포넌트」).

**두 칸 배치**(왼쪽 표 · 오른쪽 칸 — 칸막이 · 접기 · 폭 기억 · 서식)는 시나리오 목록 관리와 함께
쓰는 `components/side_panel.py` 이고 이 화면의 스펙이 `MASTER_SIDE` 다(저장소
`capa-equipment-side-v1`, `<html>` 의 `--emd-side-w` · `--emd-top` · `data-emd-side`).

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

from capa_simulation.components import grid_shared, side_panel
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


def registered_js() -> str:
    """등록 JS — 표 공용 조각(`grid_shared_assets/`) 뒤에 이 표의 파일."""
    return grid_shared.joined_assets(grid_shared.SHARED_JS, [_ASSETS / "grid.js"])


def registered_css() -> str:
    """등록 CSS — 표 공용 조각 뒤에 이 표의 파일(같은 특이도면 뒤가 이긴다)."""
    return grid_shared.joined_assets(grid_shared.SHARED_CSS, [_ASSETS / "grid.css"])


_GRID = st.components.v2.component(
    "capa_equipment_master_grid",
    html=(_ASSETS / "grid.html").read_text(encoding="utf-8"),
    css=registered_css(),
    js=registered_js(),
)


def side_key(panel: SidePanel) -> str:
    """오른쪽 칸 마운트 key — 칸(호기 상세·저장 전 변경)마다 따로다."""
    return f"{SIDE_KEY_PREFIX}_{panel}"


_palette = grid_shared.grid_palette


def _with_palette(data: Mapping[str, Any]) -> dict[str, Any]:
    return {**data, "palette": _palette()}


# ------------------------------------------------------------------ 받은 값 읽기


_state_value = grid_shared.state_value
outbox_value = grid_shared.outbox_value
outbox_mount = grid_shared.outbox_mount


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
    """「새 호기」 칸이 보낸 초안 — 번호(브라우저가 확정마다 올린다), 39칸 글."""

    seq: int
    values: tuple[str, ...]


def draft_value(payload: object, size: int) -> DraftValue | None:
    """`draft` 상태 값(``{"seq", "values"}``)을 거른다 — 꼴이 다르면 None. 그 밖의 칸은 보지
    않는다."""
    if not isinstance(payload, Mapping):
        return None
    seq, values = payload.get("seq"), payload.get("values")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        return None
    if not isinstance(values, list) or len(values) != size:
        return None
    if not all(isinstance(item, str) for item in values):
        return None
    return DraftValue(seq, tuple(values))


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
    """불러오기 자리 — 설비명 찾기(부분 일치·목록)·공정별·조건별(사용자 R1)·일정 확인·전체
    불러오기, 불러온 수·못 찾은 설비명. 목록이 비면 빈 안내와 단추가 서고, 저장된 데이터가 없는 첫
    화면에는 「엑셀·CSV로 한꺼번에」 팝업 열기 · 「+ 새 호기」 도 선다(`on_dialog` · `on_new`)."""
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

# 처음 폭은 옛 7:3 두 칸의 오른쪽 폭(30% − 28px)이다.
MASTER_SIDE: Final = side_panel.named_side_panel(
    "equipment_master",
    store="capa-equipment-side-v1",
    css_name="emd",
    default_share=0.3,
    default_offset_px=28,
)
# 편집기 영역(테두리 칸)과 그 안 두 칸 줄(가로 칸)·두 칸, 표 위 작업 줄, 오른쪽 칸 고르기, 오른쪽 칸
# 본문(고르기 아래 전부 — 패널·저장 구획·저장 이력), 칸막이 마운트.
FRAME_KEY: Final = MASTER_SIDE.frame_key
SPLIT_KEY: Final = MASTER_SIDE.split_key
LEFT_KEY: Final = MASTER_SIDE.left_key
RIGHT_KEY: Final = MASTER_SIDE.right_key
TOOLS_KEY: Final = MASTER_SIDE.tools_key
# 메뉴 「엑셀·CSV」 단추 — 곁 `.emg-btn` 과 같은 높이 · 안쪽 여백 · 글자와 꺾쇠 사이, 찾기 칸(42px)
# 줄 가운데, 곁 단추와 같은 간격. 폭은 글자 54.4 + 사이 6 + 꺾쇠 14 + 양옆 13 · 13 의 올림이다(1.63
# 측정).
TOOLS_MENU_WIDTH_PX: Final = 101
TOOLS_MENU_HEIGHT_PX: Final = 34
TOOLS_MENU_TOP_PX: Final = 4
TOOLS_MENU_GAP_PX: Final = 8
TOOLS_MENU_CARET_GAP_PX: Final = 6
# 메뉴가 찾기 칸과 한 줄에 못 들면 불러오기 줄이 이만큼 내려가 메뉴가 제 줄에 선다 — 찾기 칸 높이.
TOOLS_MENU_ROW_PX: Final = 42
SIDE_CHOICE_KEY: Final = MASTER_SIDE.choice_key
SIDE_BODY_KEY: Final = MASTER_SIDE.body_key
SPLITTER_KEY: Final = MASTER_SIDE.splitter_key


def side_bounds() -> dict[str, float]:
    """칸막이 data 의 폭 한계."""
    return side_panel.side_bounds(MASTER_SIDE)


def side_width_rule() -> str:
    """오른쪽 칸 감싸개의 폭."""
    return side_panel.side_width_rule(MASTER_SIDE)


def side_layout_style() -> str:
    """두 칸 배치 CSS 한 덩이."""
    return side_panel.side_layout_style(MASTER_SIDE)


def tools_menu_style() -> str:
    """메뉴 「엑셀·CSV」(작업 줄 칸 `TOOLS_KEY`)를 불러오기 줄 첫 줄 오른쪽 끝에 얹는 CSS 한 덩이.

    불러오기 줄은 그림자 DOM 컴포넌트, 메뉴는 Streamlit 팝오버(내려받기 단추가 파이썬 위젯이라)라
    한 flex 줄에 넣지 못한다. 불러오기 마운트 전체와 나란히 두면 값 줄 · 첫 화면 안내까지 눌리므로
    메뉴를 왼쪽 칸 기준 절대 위치로 띄우고(흐름 높이 0 — 가로 칸의 flex 항목은 `stLayoutWrapper`
    다, `side_layout_style` 과 같은 1.63 꼴) 불러오기 줄만 CSS 변수 `--emd-tools-reserve`(그림자
    경계를 넘어 상속된다)로 그만큼 비운다. 값 줄 · 빈 안내는 폭을 그대로 쓰고, 좁아지면 줄이
    바뀌어도 메뉴는 첫 줄 끝이다. 접은 동안은 떠 있는 단추 자리(`side_panel` 의 작업 줄 칸 오른쪽
    여백)만큼 더 비운다. 폭은 팝오버 `width` 로 고정이라 글꼴이 달라도 비움과 어긋나지 않는다.

    왼쪽 칸이 찾기 칸 한 줄 + 비움보다 좁으면 메뉴가 찾기 칸을 누르지 않고 불러오기 줄이 제 몫
    `--emd-tools-drop` 만큼 내려간다 — 메뉴는 같은 자리에 혼자 서고 찾기 칸은 칸 폭을 다 쓴다.
    갈림은 불러오기 JS 의 `ResizeObserver` 가 마운트의 `data-lb` 로 고른다(`loaderFit`, 파이썬 회차
    없음 — UI-PRF-04). `container-type` 은 쓰지 않는다 — 그 칸의 쌓임 문맥과 fixed 기준이 바뀐다.
    """
    item = f'[data-testid="stLayoutWrapper"]:has(> .st-key-{TOOLS_KEY})'
    button = f'.st-key-{TOOLS_KEY} [data-testid="stPopoverButton"]'
    loader = f".st-key-{LOADER_KEY}"
    folded = f'html[data-{MASTER_SIDE.css_name}-side="min"]'
    room = TOOLS_MENU_WIDTH_PX + TOOLS_MENU_GAP_PX
    drop = TOOLS_MENU_ROW_PX
    return "".join(
        [
            "<style>",
            f".st-key-{LEFT_KEY} {{ position: relative; }}",
            f"{item} {{ position: absolute; top: {TOOLS_MENU_TOP_PX}px; right: 0; width: auto; }}",
            f"{loader} {{ --emd-tools-reserve: {room}px; --emd-tools-drop: {drop}px; }}",
            (
                f"{button} {{ height: {TOOLS_MENU_HEIGHT_PX}px; "
                f"min-height: {TOOLS_MENU_HEIGHT_PX}px; padding: 0 12px; border-radius: 6px; "
                f"border-color: {tokens.BORDER_STRONG}; background: {tokens.SURFACE}; "
                f"color: {tokens.TEXT}; }}"
            ),
            f"{button}:hover {{ background: {tokens.SURFACE_SUBTLE}; }}",
            (
                f"{button}:focus-visible {{ outline: 2px solid {tokens.ACCENT}; "
                "outline-offset: -2px; box-shadow: none; }"
            ),
            f"{button} > div {{ gap: {TOOLS_MENU_CARET_GAP_PX}px; margin-right: 0; }}",
            f"{button} p {{ font: 400 13px/1.45 {tokens.FONT_FAMILY}; }}",
            f"@media screen and (width > {side_panel.SIDE_STACK_MAX_PX}px) {{ ",
            f"{folded} {loader} {{ ",
            f"--emd-tools-reserve: {room + side_panel.SIDE_REOPEN_RESERVE_PX}px; }} ",
            "}",
            "</style>",
        ]
    )
