# Purpose: 범용 편집 그리드 두 등록(껍데기·feed)을 그리고 출납을 세션 inbox 로 받아 초안에 반영한다.

"""범용 편집 그리드의 그리기와 받기(편집 표 횡전개 명세 2·4·6장).

**두 등록으로 나눠 보낸다.** CCv2 는 data 가 바뀐 회차마다 등록 JS·CSS 를 요소와 함께 다시 보낸다.
표 본문과 JS 를 실은 무거운 요소(`capa_edit_grid` — 「껍데기」)는 표가 같으면 회차마다 같은 dict 라
ForwardMsg 해시 참조(약 75 B)로 가고, 편집 회차마다 바뀌는 초안·오류·ack 는 작은
요소(`capa_edit_grid_feed` — JS 3 KB 이하)에 싣는다. 둘은 같은 문서의 `window.__capaEditGrid[host]`
칸과 `window` 이벤트 `capa-edit-grid` 로 잇는다(화면 탭 줄의 `window.__capaHistoryGuard` 선례 —
비공식). 무거운 JS 는 차례에 기대지 않는다 — feed 의 `baseKey` 가 껍데기와 다르면 칸에 둔 채
껍데기가 오면 그때 쓴다. feed 요소 칸은 페이지 CSS(이벤트 칸 `st.html`)로 숨긴다.

- **등록 JS 는 기능별 파일을 이어 붙인다**(`JS_PARTS` 차례 — 주석만 든 줄을 걷는다). 순수 구획 표지
  `// <eg-…>` 는 저장소 파일에 남아 node 시험이 읽는다. 색은 등록 CSS 에 적지 않고 회차마다
  팔레트(`palette`)로 넘긴다 — 등록 CSS 는 테마를 따라오지 않는다.
- **편집은 상태 값 `outbox` 하나**(``{"mount", "ops"}`` — 반영 안 된 op 전부, op 마다
  seq·at·table·gen). 트리거는 없다. 콜백(`collect_outbox`)은 새 op 만 세션 inbox 에 쌓고 마운트별
  seq 를 올린다 — 반영(`apply_inbox`)은 본문에서 한다. 콜백 안에서 `st.rerun()`·`st.switch_page` 를
  부르지 않고 무거운 일(양식 만들기)도 하지 않는다. 회차가 끊겨도 inbox 가 세션에 남아 다음 회차
  본문이 반영한다(같은 seq 는 다시 쌓이지 않는다).
- **그림자 DOM**(`isolate_styles` 기본값) — 팝업(`st.dialog`) 안에 마운트하지 않는다(AGENTS 9장).
  전체 화면은 그림자 DOM 안 `<dialog>.showModal()` 이다.
- **늘 같은 자리에서 부른다** — feed 요소, 그다음 무거운 요소(이 차례 고정, 둘 다 key 고정). 앞 형제
  순번이 밀리면 다시 마운트되어 보내지 않은 출납을 잃는다.

이 모듈은 읽을 때 두 컴포넌트를 등록한다 — 페이지 대본이 늘 import 해 첫 AppTest 실행에서 등록되게
한다. 시험은 `tests/conftest.py` 의 대역(`_GRID`·`_FEED`)이 바꾼다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import streamlit as st

from capa_simulation.design import tokens
from capa_simulation.services.edit_grid import (
    DROPPED_TOAST,
    PASTE_CELL_LIMIT,
    DraftState,
    GridIndex,
    GridSpec,
    HistoryState,
    Op,
    apply_ops,
    change_counts,
    draft_from,
    format_value,
    history_from,
    new_history,
    new_ops,
)
from capa_simulation.services.edit_grid_payload import (
    EditGridBase,
    empty_base,
    encode_base,
    encode_feed,
)
from capa_simulation.services.korean_particle import with_subject_particle

_ASSETS: Final = Path(__file__).with_name("edit_grid_assets")
GRID_COMPONENT: Final = "capa_edit_grid"
FEED_COMPONENT: Final = "capa_edit_grid_feed"
# 등록 때 이 차례로 잇는다 — 기능 파일의 최상위 `feature({...})` 가 읽을 때 차례로 돌고 eg_core 가
# 마운트 때 부른다.
JS_PARTS: Final = ("eg_pure.js", "eg_select.js", "eg_fill.js", "eg_toolbar.js", "eg_core.js")
CSS_PARTS: Final = ("eg_core.css", "eg_select.css", "eg_fill.css", "eg_toolbar.css")
FEED_JS: Final = "feed.js"
# 브라우저가 보내는 상태 값·트리거 이름(자산 시험이 JS 글자와 대조한다).
STATE_NAMES: Final = ("outbox",)
TRIGGER_NAMES: Final[tuple[str, ...]] = ()
HOST_PATTERN: Final = re.compile(r"[A-Za-z0-9_-]+")
_COMMENT_LINE: Final = re.compile(r"^\s*//")


def _joined(parts: Sequence[str], *, drop_comments: bool) -> str:
    texts = []
    for name in parts:
        text = (_ASSETS / name).read_text(encoding="utf-8")
        if drop_comments:
            text = "\n".join(line for line in text.splitlines() if not _COMMENT_LINE.match(line))
        texts.append(text.strip("\n"))
    return "\n".join(text for text in texts if text) + "\n"


def registered_js() -> str:
    """등록 JS — `JS_PARTS` 를 잇고 주석만 든 줄을 걷는다(줄 끝 주석·문자열 안 `//` 는 그대로)."""
    return _joined(JS_PARTS, drop_comments=True)


def registered_css() -> str:
    """등록 CSS — `CSS_PARTS` 를 잇는다(CSS 파일에는 주석을 적지 않는다 — 자산 시험)."""
    return _joined(CSS_PARTS, drop_comments=False)


def feed_js() -> str:
    return _joined((FEED_JS,), drop_comments=True)


_GRID = st.components.v2.component(
    GRID_COMPONENT,
    html=(_ASSETS / "grid.html").read_text(encoding="utf-8"),
    css=registered_css(),
    js=registered_js(),
)
_FEED = st.components.v2.component(FEED_COMPONENT, js=feed_js())


def feed_key(host: str) -> str:
    """feed 요소 key — 호스트 key 뒤에 `-feed` 를 붙인다(CCv2 key 에는 `__` 를 쓸 수 없다 — 트리거
    id 구분자라 1.63 이 `BidiComponentInvalidIdError` 로 멈춘다)."""
    return f"{_check_host(host)}-feed"


def _check_host(host: str) -> str:
    """호스트 key 는 영문·숫자·`_`·`-` 만, `__` 없이(CCv2 트리거 id 구분자)."""
    if not HOST_PATTERN.fullmatch(host) or "__" in host:
        raise ValueError(f"그리드 호스트 key 는 영문·숫자·_·- 만, __ 없이 씁니다: {host!r}")
    return host


def palette() -> dict[str, str]:
    """색은 회차마다 토큰에서 읽는다 — 테마를 바꾸면 같은 표가 새 색을 받는다(CSS `var(--eg-*)`)."""
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
        "selected-fill": tokens.GRID_SELECTED_FILL,
        "match-fill": tokens.GRID_MATCH_FILL,
        "pending": tokens.PENDING_MARK,
    }


def _bound_text(value: float | None, spec: GridSpec) -> str:
    return format_value(value, spec.fmt) if value is not None else ""


def texts(spec: GridSpec, *, changes_label: str) -> dict[str, Any]:
    """그리드 글(한국어) — 껍데기에 싣는다. 오류 문구의 하한·상한은 그 표의 형식으로 채운다."""
    fmt = spec.fmt
    maximum = f"{_bound_text(fmt.max_value, spec)} 이하로 적습니다"
    if fmt.kind == "percent":
        maximum += " — 85% 는 0.85 또는 85% 로 적습니다"
    return {
        "toolbar": f"{spec.title} 표 도구",
        "find": "찾기",
        "findCount": "{i}/{n}",
        "findNone": "없음",
        "undo": "되돌리기",
        "redo": "다시 실행",
        "fit": "칸 폭 맞춤",
        "changes": changes_label,
        "full": "전체 화면",
        "fullExit": "전체 화면 닫기 (Esc)",
        "summary": "개수 {count} · 합계 {sum} · 평균 {avg}",
        "summaryCells": "칸 {n}개",
        "summaryCount": "개수 {count}",
        "findHint": "표에서 찾기 (Ctrl+F) — Enter 다음 · Shift+Enter 이전 · Esc 지움",
        "findPrev": "이전 일치 (Shift+Enter)",
        "findNext": "다음 일치 (Enter)",
        "undoHint": "되돌리기 (Ctrl+Z)",
        "redoHint": "다시 실행 (Ctrl+Y)",
        "fitHint": (
            "모든 칸 폭을 글에 맞춥니다 — 머리 경계를 끌면 그 칸 폭, 두 번 누르면 그 칸만 맞춤"
        ),
        "fitDone": "칸 폭 맞춤 — {n}칸",
        "resizeHint": "끌어 칸 폭 바꾸기 · 두 번 눌러 맞춤",
        "widthDone": "칸 폭 {width}px",
        "changesTitle": "{label} {n}칸",
        "changesEmpty": f"{with_subject_particle(changes_label)} 없습니다",
        "changesMore": "외 {n}개 — 목록은 앞 500개만 보입니다",
        "changesHidden": "지금 보기(필터)에 없는 줄입니다 — 표 조건을 풀면 보입니다",
        "changesBlank": "빈칸",
        "changesClose": "닫기",
        "revertHint": "{where} 되돌리기",
        "fullLabel": f"{spec.title} 전체 화면",
        "fullClosed": "전체 화면 닫음",
        "errors": {
            "num": "숫자가 아닙니다",
            "finite": "유한한 숫자가 아닙니다",
            "min": f"{_bound_text(fmt.min_value, spec)} 이상으로 적습니다",
            "max": maximum,
            "int": "정수로 적습니다 — 소수는 받지 않습니다",
        },
        "pasteLimit": (
            f"한 번에 붙여넣을 수 있는 칸은 {PASTE_CELL_LIMIT:,}칸입니다"
            " — 큰 표는 「Excel 붙여넣기」 를 쓰세요"
        ),
        "clipped": "표 끝을 넘은 {n}칸은 버렸습니다",
        "copied": "{n}칸 복사함 — 붙여넣을 칸에서 Ctrl+V",
        "cleared": "{n}칸 비움",
        "pasted": "{n}칸 붙여넣음",
        "pasteSkipped": "분류 칸 {n}칸은 건너뛰었습니다",
        "pasteTiled": "고른 범위에 되풀이",
        "filled": "{n}칸 채움",
        "filledAll": "{n}칸에 같은 값을 넣음",
        "fillNoSource": (
            "채울 원본이 없습니다 — 두 줄(칸) 이상 고르거나, 바로 위(Ctrl+D)·왼쪽(Ctrl+R)에 값"
            " 칸이 있어야 합니다"
        ),
        "fillHandle": "끌어서 채우기 — 고른 값을 되풀이합니다 (Ctrl+D 아래 · Ctrl+R 오른쪽)",
        "locked": "분류 칸은 고칠 수 없습니다",
        "cut": "잘라내기는 없습니다 — 복사(Ctrl+C) 뒤 Delete 로 지우세요",
        "blankZero": "빈칸 = 0",
        "revert": "되돌리기",
        "empty": "이 기간에 행이 없습니다",
        "sortHint": "눌러서 정렬",
        "sortedAsc": "오름차순 정렬",
        "sortedDesc": "내림차순 정렬",
        "sortCleared": "정렬 풂",
        "undone": "되돌림",
        "redone": "다시 실행함",
        "undoEmpty": "되돌릴 편집이 없습니다",
        "redoEmpty": "다시 실행할 편집이 없습니다",
        "waiting": "표를 받는 중입니다 — 잠시 뒤 다시 고쳐 주세요",
        "outboxFull": (
            "보낼 고침이 너무 많습니다 — 잠시 뒤 다시 하거나 「Excel 붙여넣기」 를 쓰세요"
        ),
        "badHidden": "(못 읽은 값)",
        "helpTitle": "값 칸 도움말",
    }


# ------------------------------------------------------------------ 세션(부르는 쪽이 칸 이름을
# 정한다)


@dataclass(frozen=True)
class GridKeys:
    """한 그리드 호스트의 세션 칸 — 콜백이 쌓은 op(inbox), 마운트별 마지막 seq(applied), 마지막
    토스트, 일부러 버린 이력의 `gen`(discarded — 주면 「편집 취소」 직전에 보낸 op 를 알림 없이
    버린다).
    """

    inbox: str
    applied: str
    toast: str
    discarded: str | None = None


# 일부러 버린 이력 `gen` 을 몇 개까지 기억하는가(표마다 하나씩 쌓인다 — 늦게 온 op 도 덮는다).
DISCARDED_GENS = 16


@dataclass(frozen=True)
class TableSlot:
    """op 를 받을 표 하나 — 양식 색인(캐시)·규격과 그 표 초안·이력 세션 칸."""

    index: GridIndex
    spec: GridSpec
    cells_key: str
    history_key: str


def _state_value(key: str, name: str) -> object:
    """`st.session_state[key]` 의 `name` — 결과 객체는 매핑으로도 속성으로도 온다(대역은 속성)."""
    state = st.session_state.get(key)
    if isinstance(state, Mapping):
        return state.get(name)
    return getattr(state, name, None)


def outbox_value(host: str) -> object:
    """그리드 마운트의 상태 값 `outbox`(없으면 None)."""
    return _state_value(host, "outbox")


def collect_outbox(host: str, keys: GridKeys) -> None:
    """출납 콜백 몸통 — 새 op 만 inbox 에 덧붙이고 마운트별 seq 를 올린다(반영은 본문
    `apply_inbox`)."""
    applied = st.session_state.get(keys.applied)
    ops, memory = new_ops({host: outbox_value(host)}, applied if isinstance(applied, dict) else {})
    st.session_state[keys.applied] = memory
    if ops:
        inbox = st.session_state.get(keys.inbox)
        st.session_state[keys.inbox] = [*(inbox if isinstance(inbox, list) else []), *ops]


def history_of(history_key: str) -> HistoryState:
    """그 표의 이력 — 없으면 새 `gen` 으로 세운다(초안을 버리면 이력도 지워 다음 `gen` 은 다른
    값이다).
    """
    history = history_from(st.session_state.get(history_key))
    if history is None:
        history = new_history()
        st.session_state[history_key] = history
    return history


def draft_of(cells_key: str) -> DraftState | None:
    return draft_from(st.session_state.get(cells_key))


def draft_pending(cells_key: str) -> bool:
    """그 표에 적용하지 않은 초안이 있는가(「변경사항 적용」 을 켜는 조건)."""
    return change_counts(draft_of(cells_key))[0] > 0


def post_toast(keys: GridKeys, lines: Sequence[str]) -> None:
    """feed 로 갈 토스트 — 번호를 올려 브라우저가 새 것만 띄운다."""
    if not lines:
        return
    previous = st.session_state.get(keys.toast)
    number = previous.get("id", 0) if isinstance(previous, Mapping) else 0
    st.session_state[keys.toast] = {
        "id": (number if isinstance(number, int) else 0) + 1,
        "text": " · ".join(lines),
    }


def apply_inbox(keys: GridKeys, slots: Mapping[str, TableSlot]) -> bool:
    """inbox 의 op 를 표별로 나눠 그 표 초안·이력에 반영한다(지금 그리지 않는 표도 op 의 `table`
    로).
    받을 표가 없는 op 는 버리고 수를 알린다. 토스트를 남기고, 초안이 바뀌었으면 참."""
    pending = st.session_state.pop(keys.inbox, None)
    ops = [op for op in pending if isinstance(op, Op)] if isinstance(pending, list) else []
    # 사용자가 「편집 취소」 로 버린 이력의 op(누름 직전 출납 묶음 안에 남았던 편집)는 알리지 않고
    # 버린다 — 일부러 버린 편집을 「다시 고쳐 주세요」 라고 하지 않는다.
    quiet = _discarded_gens(keys)
    for op in [op for op in ops if op.gen in quiet]:
        slot = slots.get(op.table)
        # 출납 콜백이 둔 빈 초안 자리(`{"cells": {}, "bad": {}}`)는 걷는다 — 남으면 사이드바가
        # 「적용 전 편집」 으로 센다(반영 길은 결과 초안 None 을 적어 같은 일을 한다).
        if slot is not None and draft_of(slot.cells_key) is None:
            st.session_state[slot.cells_key] = None
    ops = [op for op in ops if op.gen not in quiet]
    if not ops:
        return False
    by_table: dict[str, list[Op]] = {}
    dropped = 0
    for op in ops:
        if op.table in slots:
            by_table.setdefault(op.table, []).append(op)
        else:
            dropped += 1
    lines: list[str] = []
    changed = False
    for table, table_ops in by_table.items():
        slot = slots[table]
        result = apply_ops(
            slot.index, slot.spec, draft_of(slot.cells_key), history_of(slot.history_key), table_ops
        )
        st.session_state[slot.cells_key] = result.draft
        st.session_state[slot.history_key] = result.history
        lines.extend(result.toasts)
        changed = changed or result.changed
    if dropped:
        lines.insert(0, DROPPED_TOAST.format(n=f"{dropped:,}"))
    post_toast(keys, lines)
    return changed


def _discarded_gens(keys: GridKeys) -> set[str]:
    if keys.discarded is None:
        return set()
    saved = st.session_state.get(keys.discarded)
    return {gen for gen in saved if isinstance(gen, str)} if isinstance(saved, list) else set()


def discard_table(slot_keys: tuple[str, str], keys: GridKeys | None = None) -> None:
    """그 표의 초안·이력을 지운다(적용·「편집 취소」·원본이 바뀜). 다음 회차에 새 `gen` 이 선다.

    `keys`(그 칸 `discarded` 가 있을 때)를 주면 사용자가 **일부러** 버린 것이다 — 버린 이력의
    `gen` 을 적어 두어, 버리기 직전에 보낸 op(300ms 출납 묶음 안의 편집 — 「편집 취소」 를 누른
    focusout 이 보낸다)를 `apply_inbox` 가 「표가 바뀌기 전에 보낸 편집 … 다시 고쳐 주세요」
    토스트 없이 버린다.
    """
    if keys is not None and keys.discarded is not None:
        history = history_from(st.session_state.get(slot_keys[1]))
        if history is not None:
            saved = st.session_state.get(keys.discarded)
            gens = [gen for gen in saved if isinstance(gen, str)] if isinstance(saved, list) else []
            st.session_state[keys.discarded] = [*gens, history["gen"]][-DISCARDED_GENS:]
    for key in slot_keys:
        st.session_state.pop(key, None)


# ------------------------------------------------------------------ data 짓기·그리기


def shell_data(
    host: str,
    base: EditGridBase | None,
    spec: GridSpec | None,
    *,
    base_key: str,
    changes_label: str,
) -> dict[str, Any]:
    """껍데기 — 표가 없으면(읽기 보기) 표 없는 껍데기라 마운트는 그대로 남는다."""
    _check_host(host)
    if base is None or spec is None:
        return empty_base(
            host=host, texts=texts_for_empty(changes_label=changes_label), palette=palette()
        )
    return encode_base(
        base.body,
        host=host,
        base_key=base_key,
        texts=texts(spec, changes_label=changes_label),
        palette=palette(),
        row_height=tokens.MONTH_GRID_ROW_HEIGHT_PX,
    )


def texts_for_empty(*, changes_label: str) -> dict[str, Any]:
    """표 없는 껍데기의 글(머리 글만 쓰인다)."""
    return {"changes": changes_label, "empty": "이 기간에 행이 없습니다"}


def feed_data(
    host: str,
    slot: TableSlot | None,
    keys: GridKeys,
    *,
    base_key: str,
    filters: Mapping[int, Sequence[int]] | None = None,
) -> dict[str, Any]:
    """feed — 그 표의 초안·이력과 마운트별 ack(반영한 마지막 seq)·마지막 토스트·필터."""
    _check_host(host)
    applied = st.session_state.get(keys.applied)
    acks = applied if isinstance(applied, Mapping) else {}
    toast = st.session_state.get(keys.toast)
    toast_value = toast if isinstance(toast, Mapping) else None
    if slot is None:
        return encode_feed(
            None, None, None, host=host, base_key=base_key, acks=acks, toast=toast_value
        )
    return encode_feed(
        slot.index,
        draft_of(slot.cells_key),
        history_of(slot.history_key),
        host=host,
        base_key=base_key,
        acks=acks,
        toast=toast_value,
        filters=filters,
    )


def hide_feed_style(host: str) -> str:
    """feed 요소 칸을 숨기는 페이지 CSS(스타일만이라 `st.html` 이 이벤트 칸으로 보낸다 — 자리를 먹지
    않는다)."""
    return f"<style>.st-key-{feed_key(_check_host(host))}{{display:none}}</style>"


def render_edit_grid(
    host: str,
    shell: Mapping[str, Any],
    feed: Mapping[str, Any],
    *,
    on_outbox: Callable[[], None],
) -> None:
    """늘 같은 자리에서 부른다 — feed 요소, 그다음 무거운 요소(이 차례 고정). 둘 다 key 가
    고정이다."""
    _check_host(host)
    st.html(hide_feed_style(host))
    _FEED(key=feed_key(host), data=dict(feed), width="stretch")
    _GRID(key=host, data=dict(shell), on_outbox_change=on_outbox, width="stretch")
