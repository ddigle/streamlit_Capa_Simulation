# Purpose: 메모 · 저장자 칸 안내 글 꼴을 한 곳에 두고, 저장한 메모를 칸 글이 그 글일 때만 비운다.

"""변경 메모 칸 — 칸 안 안내 글(`note_placeholder`)과 저장 뒤 비우기.

**안내 글이 칸 이름이다.** 저장 줄 · 저장 칸의 「변경 메모」 는 이름 줄을 걷고(`label_visibility=
"collapsed"` — 접근성 이름으로 남는다) 칸 안 흐린 글 「변경 메모 · 예: …」 가 이름과 예를 함께
말한다(2026-11-09 사용자 규칙 「페이지 상단 최소화」 — 꼴은 상단 띠 재고 권장, 사용자 수락 11-10
Q-12, 설계 규칙 UI-CON-03 · UI-TXT-01 예외 「사람이 쓰는 자유 글 칸의 안내 글」). 꼴은 「<칸
이름> · 예: <예>」 하나다(`field_placeholder`) — 저장자 칸
`equipment_save_fields.SAVED_BY_PLACEHOLDER` 「저장자 · 예: 홍길동」 도 같은 함수로 짓는다.

저장 뒤 비우기 — key 를 그대로 두고 다음 회차 칸 앞에서 빈 값을 적는다.

메모는 저장에 성공하면 비운다. 남으면 다시 적지 않은 메모가 값만 고친 다음 저장의 기록에 실린다.
key 세대(`widget_generation.bump`)로 비우면 칸이 새 위젯으로 갈려 다음이 깨졌다(2026-11-08 리뷰).

- 칸에서 Enter 로 저장하면 초점이 사라진다. 대화상자는 초점을 닫기 단추로 옮겨 다음 Enter 가
  대화상자를 닫고, 같은 탭 다른 폼의 저장 안 한 편집이 알림 없이 사라졌다.
- 세대는 새 세션에서 0 이라 저장을 한 번 한 탭의 칸은 서버 재시작 뒤 다른 위젯이 되어 적던 메모가
  빈다.

그래서 저장을 마친 갈래는 표지만 남기고(`mark_note_saved`) 칸은 제출이 아닌 다음 회차가 칸을 그리기
앞에 비운다(`ready_note_field`). 칸은 마운트된 채라 적은 빈 값이 브라우저에 닿는다.

**제출 회차는 칸을 건드리지 않는다.** 둘째 누름의 회차에 칸을 비우면 그 회차의 입력이 바뀌어 같은
입력의 거름(`write_guard.save_once` 지문에 메모가 든다)을 지나 한 번 더 쓴다. 그래서 저장 단추를
먼저 그린 뒤, 그 결과를 들고 칸 앞에서 부른다.

**칸 글이 저장한 글일 때만 비운다.** 앞 회차가 끝나기 전에 온 다른 입력의 둘째 누름은 제 저장으로
판정되어(`write_guard.is_own_save`) 쓰이지 않으므로, 그 글은 칸에 남겨야 한다. 끊긴 첫 회차가 표지를
남기지 못한 자리는 그 판정 갈래가 잇되(`mark_note_saved_again`), 이 글이 같은 출발점의 첫 누름 글일
때만이다. 첫 글은 쓰기 **전**인 칸 앞에서 적어 둔다 — 쓴 뒤 뒷정리는 둘째 누름의 회차에 끊길 수
있다.

**비운 직후 온 제출은 칸을 다시 맞춘다.** 칸 글은 브라우저가 들고 있어 비우는 회차는 그 사이 친
글을 모른다. 그 회차의 빈 값이 둘째 누름을 보낸 뒤에 닿으면 칸과 서버가 어긋난다 — 다른 글이면 칸은
비고 그 글은 서버에만 남았고, 첫 누름이 쓴 그 글이면 뒤따른 회차가 빈 값을 덮어 칸에 되살아났다.
그래서 그 제출 회차가 다른 글은 다시 적고 같은 글은 빈 값을 다시 적는다(이 회차의 메모도 빈다 — 첫
누름이 이미 그 메모로 썼다). 비운 지 `write_guard.TRAILING_PRESS_SECONDS` 안의 제출만 본다 — 그 뒤
같은 글을 적어 누른 것은 사람이 다시 적은 메모다. 둘째 누름 앞에 빈 값이 닿아 지워진 글은 서버가
받지 못해 살리지 못한다.
"""

from __future__ import annotations

import time

import streamlit as st

from capa_simulation.components import write_guard
from capa_simulation.components.write_guard import SeenToken

__all__ = [
    "NOTE_LABEL",
    "field_placeholder",
    "mark_note_saved",
    "mark_note_saved_again",
    "note_placeholder",
    "ready_note_field",
]

NOTE_LABEL = "변경 메모"


def field_placeholder(name: str, example: str) -> str:
    """이름 줄이 없는 칸 안 안내 글 — 「<칸 이름> · 예: <예>」(메모 · 저장자 칸 한 꼴)."""
    return f"{name} · 예: {example}"


def note_placeholder(example: str) -> str:
    """변경 메모 칸 안 안내 글 — 「변경 메모 · 예: <예>」."""
    return field_placeholder(NOTE_LABEL, example)


def _saved_key(key: str) -> str:
    return f"{key}__note_saved"


def _emptied_key(key: str) -> str:
    return f"{key}__note_emptied"


def _first_press_key(key: str) -> str:
    return f"{key}__note_first_press"


def ready_note_field(key: str, *, submitted: bool, start: SeenToken | None = None) -> None:
    """메모 칸 `key` 를 그리기 **바로 앞**, 저장 단추를 그린 **뒤**에 부른다.

    제출 회차(`submitted`)는 표지가 기다려도 칸을 비우지 않고, 대조 저장이면 그 출발점(`start` — 본
    version)의 첫 누름 글을 적는다. 앞 회차가 막 비운 칸에서 온 제출이면 칸을 다시 맞춘다(모듈
    머리말). 제출이 아닌 회차는 표지가 있고 칸 글이 그 글이면 빈 값을 적는다. 그 사이 칸 글이
    달라졌으면(다른 입력의 둘째 누름) 표지만 걷는다.
    """
    text = st.session_state.get(key)
    if submitted:
        emptied = st.session_state.pop(_emptied_key(key), None)
        if (
            text
            and isinstance(emptied, tuple)
            and time.monotonic() - emptied[1] < write_guard.TRAILING_PRESS_SECONDS
        ):
            text = "" if text == emptied[0] else text
            st.session_state[key] = text
        held = st.session_state.get(_first_press_key(key))
        fresh = not (isinstance(held, tuple) and held[0] == start)
        if start is not None and fresh:
            st.session_state[_first_press_key(key)] = (start, text)
        return
    st.session_state.pop(_emptied_key(key), None)
    saved = st.session_state.get(_saved_key(key))
    if saved is None:
        return
    if text == saved:
        st.session_state[key] = ""
        st.session_state[_emptied_key(key)] = (saved, time.monotonic())
    st.session_state.pop(_saved_key(key), None)


def mark_note_saved(key: str, text: str) -> None:
    """이 회차가 메모 `text` 로 저장을 마쳤다 — 다음 회차가 칸을 비운다."""
    if text:
        st.session_state[_saved_key(key)] = text


def mark_note_saved_again(key: str, text: str) -> None:
    """이 누름이 저장은 하지 않고 첫 누름의 저장으로 끝났다 — 글이 첫 누름 글일 때만 칸을 비운다."""
    held = st.session_state.get(_first_press_key(key))
    if isinstance(held, tuple) and held[1] == text:
        mark_note_saved(key, text)
