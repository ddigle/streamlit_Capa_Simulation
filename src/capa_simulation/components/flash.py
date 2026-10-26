# Purpose: rerun 을 건너 살아남는 알림을 세션에 담았다가 다음 실행에서 늘 서 있는 한 칸에 그린다.

"""동작의 결과 알림이 화면에 남게 하고, 그 알림이 뒤 형제의 자리를 밀지 않게 한다.

`st.success(...)` 바로 뒤에 `st.rerun()` 을 부르면 **그 문구는 한 번도 그려지지 않는다.**
`rerun` 이 그 자리에서 실행을 끊고 화면을 처음부터 다시 그리기 때문이다. 사용자에게는
화면이 한 번 깜빡이고 제자리로 돌아온 것으로 보여서, 저장이 됐는지 알 수 없어 다시 누른다.
위젯 콜백이 낸 결과도 같다 — 콜백은 본문보다 먼저 돌아 그 자리에 그릴 수 없다.

그래서 알림을 세션에 담아 두고(`queue_flash`) **다음 실행에서** 꺼내 그린다(`render_flash`).
알림 칸은 모두 이 두 함수를 지난다 — 칸마다 꺼내 그리는 길을 따로 두면 끊긴 회차·자리 밀림 같은
고침이 한 칸에만 가고 다른 칸에는 가지 않는다(`tests/test_flash_messages.py` 의 AST 그물이 이
모듈 밖에서 알림 칸을 꺼내 그리는 꼴을 찾는다).

**그리는 칸은 늘 선다.** `render_flash` 는 알림이 있든 없든 `st.container()` 한 칸을 세우고 그 칸을
돌려준다. 알림이 생기고 사라질 때 뒤 형제의 순번이 밀리면 key 없는 팝오버·탭·확장 패널이 새로
서며 닫히고, key 있는 블록은 끊긴 회차의 옛 자리에 흐린 사본을 남긴다(AGENTS 9장 「조건부 알림」).
빈 칸은 높이가 없다. 같은 동작의 실패 문구는 돌려받은 칸에 쓴다 — 성공과 실패가 같은 자리에서
답한다.

**그리는 자리는 버튼과 같은 상자 안이다.** 성공만 화면 맨 위에 뜨면 어느 동작의 결과인지 사용자가
되짚어야 한다.

**끊긴 회차에도 남는다.** 아주 빠른 두 번 누름은 둘째 누름이 옛 화면의 단추에 닿아 그 회차가
쓰지 않고 끝나는데, 첫 쓰기의 알림은 앞 회차가 이미 꺼내 그려 둘째 회차가 화면을 다시 그리며
지웠다(2026-10-26 E2E — VOC 글 삭제·Preference 프리셋 삭제). 쓰기 전에
`write_guard.notice_marks()` 로 받은 dict 에 알림과 시각(과 아이콘)을 적은
칸(`write_guard.note_notice`)은 담아 둔 알림이 없는 회차에도 `TRAILING_PRESS_SECONDS` 안이면
`render_flash` 가 그 글을 같은 아이콘으로 다시 그린다(`write_guard.held_flash`) — 칸마다 따로 짓지
않고 모든 칸이 이 길을 받는다. 적지 않은 칸은 그대로 한 번만 그린다.

**한 번만 그린다.** 꺼낸 알림은 비운다. 비우지 않으면 그 뒤 모든 rerun 에 같은 문구가 남아, 사용자가
방금 저장한 것인지 아까 저장한 것인지 알 수 없게 된다. 다음 동작까지 남아야 하는 칸(VOC 지운 글의
적어 둔 답변처럼 알림이 아니라 되살릴 입력을 든 칸, 같은 기준선 알림을 한 번만 세는 칸)은 이 모듈을
지나지 않고 그 까닭을 AST 그물의 허용 목록에 적는다.
"""

from __future__ import annotations

from typing import Literal, NamedTuple, get_args

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components.write_guard import held_flash

FlashKind = Literal["success", "info", "warning", "error"]
_KINDS: frozenset[str] = frozenset(get_args(FlashKind))


class FlashNote(NamedTuple):
    """담아 둔 알림 하나 — 종류(`st.success`·`info`·`warning`·`error`), 글, 아이콘.

    세션에는 튜플로 남는다 — 코드를 다시 읽은 서버에서도 그대로 읽힌다. 아이콘 없는 성공 알림은
    글만 담는다(`queue_flash`).
    """

    kind: FlashKind
    message: str
    icon: str | None = None


def queue_flash(
    key: str,
    message: str,
    *,
    kind: FlashKind = "success",
    icon: str | None = None,
) -> None:
    """동작 직후(콜백·본문)에 부른다. 곧바로 `st.rerun()` 을 불러도 알림이 살아남는다.

    같은 칸에 다시 담으면 앞 알림을 바꾼다. 아이콘 없는 성공 알림은 글만 담는다 — 그 칸을 글로
    읽는 시험·도우미가 그대로 읽는다.
    """
    if kind not in _KINDS:
        raise ValueError(f"알 수 없는 알림 종류입니다: {kind}")
    st.session_state[key] = (
        message if kind == "success" and icon is None else FlashNote(kind, message, icon)
    )


def render_flash(*keys: str) -> DeltaGenerator:
    """늘 서 있는 한 칸을 세우고, `keys` 에 담아 둔 알림을 그 차례대로 그 안에 그리고 비운다.

    칸은 알림이 없어도 선다 — 뒤 형제의 순번이 알림 유무로 밀리지 않는다. 돌려받은 칸에 같은
    동작의 실패 문구나 그 자리에 함께 설 알림을 더 쓸 수 있다. 담아 둔 알림이 없는 칸은 쓰기 직후
    적어 둔 알림(`write_guard.held_flash`)이 창 안이면 그 글을 적어 둔 아이콘·종류(보통 성공)로 다시
    그린다.
    """
    slot = st.container()
    for key in keys:
        note = _note(st.session_state.pop(key, None))
        if note is None:
            held = held_flash(key)
            note = None if held is None else _note((held[2], held[0], held[1]))
        if note is not None:
            _draw(slot, note)
    return slot


def pending_flash(key: str) -> FlashNote | None:
    """`key` 칸에 담아 둔 알림(비우지 않는다). 없으면 None.

    그 칸이 이번 회차에 그릴 것이 있는지 먼저 보아야 하는 자리(끊긴 회차의 결과를 기록에서 되찾을지
    가르는 「지금 실행」)와 시험이 쓴다. 그리기는 늘 `render_flash` 다.
    """
    return _note(st.session_state.get(key))


def _note(value: object) -> FlashNote | None:
    """세션 값을 알림으로 읽는다. 글이면 성공, (종류, 글[, 아이콘]) 튜플이면 그 종류다."""
    if isinstance(value, str):
        return FlashNote("success", value) if value else None
    if not (isinstance(value, tuple) and len(value) in (2, 3)):
        return None
    kind, message, *rest = value
    icon = rest[0] if rest else None
    if kind not in _KINDS or not isinstance(message, str) or not message:
        return None
    if icon is not None and not isinstance(icon, str):
        return None
    return FlashNote(kind, message, icon)


def _draw(slot: DeltaGenerator, note: FlashNote) -> None:
    if note.kind == "success":
        slot.success(note.message, icon=note.icon)
    elif note.kind == "warning":
        slot.warning(note.message, icon=note.icon)
    elif note.kind == "error":
        slot.error(note.message, icon=note.icon)
    else:
        slot.info(note.message, icon=note.icon)
