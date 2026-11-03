# Purpose: 동작 결과 알림을 담았다가 다음 실행에 알림창 표지로 보내고 경고·오류만 칸에 그린다.

"""동작의 결과 알림을 다음 회차에 알림 칸(오른쪽 아래 알림창 · Alarm)으로 보내고, 버튼 곁 칸이 뒤
형제의 자리를 밀지 않게 한다.

`st.success(...)` 바로 뒤에 `st.rerun()` 을 부르면 **그 문구는 한 번도 그려지지 않는다.**
`rerun` 이 그 자리에서 실행을 끊고 화면을 처음부터 다시 그리기 때문이다. 사용자에게는
화면이 한 번 깜빡이고 제자리로 돌아온 것으로 보여서, 저장이 됐는지 알 수 없어 다시 누른다.
위젯 콜백이 낸 결과도 같다 — 콜백은 본문보다 먼저 돌아 그 자리에 그릴 수 없다.

그래서 알림을 세션에 담아 두고(`queue_flash`) **다음 실행에서** 꺼낸다(`render_flash`). 알림 칸은
모두 이 두 함수를 지난다 — 칸마다 꺼내 그리는 길을 따로 두면 끊긴 회차·자리 밀림 같은 고침이 한
칸에만 가고 다른 칸에는 가지 않는다(`tests/test_flash_messages.py` 의 AST 그물이 이 모듈 밖에서 알림
칸을 꺼내 그리는 꼴을 찾는다).

**알림창 한 꼴(2026-11-03 결정 보드 D3 (가)).** 꺼낸 알림은 모두 사건 알림 표지(`alerts` — 이벤트 칸
한 자리)로 보내 오른쪽 아래 알림창에 뜨고 Alarm 에 쌓인다. 성공 · 안내(`success`·`info`)는
**알림창으로만** 내고 버튼 곁 칸에는 그리지 않는다 — 같은 글이 두 번 보이지 않게. 경고 ·
오류(`warning`·`error` — 거부 · 실패)는 고칠 입력이 그 자리에 있으므로 **버튼 곁에도** 그린다.
코드는 종류별 기본(`alerts.FLASH_CODES`)이고 칸마다 따로 두려면 `queue_flash(…, alert=…)` 로 등록부
코드를 준다. 동작은 끝났고 그 자리에 고칠 입력이 없는 경고(사이드바 리비전 저장 · 시나리오 관리
복제 · 공식 지정 뒤 「소요대수에 들지 않은 수요」 — 2026-11-04 검수 의견 home-18)는
`queue_flash(…, popup_only=True)` 로 알림창 · Alarm 에만 낸다.

**그리는 칸은 늘 선다.** `render_flash` 는 알림이 있든 없든 `st.container()` 한 칸을 세우고 그 칸을
돌려준다. 알림이 생기고 사라질 때 뒤 형제의 순번이 밀리면 key 없는 팝오버·탭·확장 패널이 새로 서며
닫히고, key 있는 블록은 끊긴 회차의 옛 자리에 흐린 사본을 남긴다(AGENTS 9장 「조건부 알림」). 빈
칸은 높이가 없다. 같은 동작의 실패 문구는 돌려받은 칸에 쓴다 — 실패는 그 자리에서 답한다. 표지는
이벤트 칸에 **부를 때마다 정확히 한 자리**를 쓴다(알림이 없으면 빈 스타일 — 프래그먼트 · 팝업 본문의
이벤트 칸 자리 수 규칙, `alerts` 모듈 설명).

**끊긴 회차에도 남는다.** 아주 빠른 두 번 누름은 둘째 누름이 옛 화면의 단추에 닿아 그 회차가 쓰지
않고 끝나는데, 첫 쓰기의 알림은 앞 회차가 이미 꺼내 그려 둘째 회차가 화면을 다시 그리며
지웠다(2026-10-26 E2E — VOC 글 삭제·Preference 프리셋 삭제). 쓰기 전에 `write_guard.notice_marks()`
로 받은 dict 에 알림과 시각(과 아이콘)을 적은 칸(`write_guard.note_notice`)은 담아 둔 알림이 없는
회차에도 `TRAILING_PRESS_SECONDS` 안이면 `render_flash` 가 그 글을 같은 아이콘으로 다시
낸다(`write_guard.held_flash` — 표지는 첫 알림과 같은 id 라 알림창이 두 번 뜨지 않는다) — 칸마다
따로 짓지 않고 모든 칸이 이 길을 받는다. 그 밖의 칸도 보낸 표지를 `alerts.RESEND_SECONDS` 안에 같은
id 로 한 번 더 보낸다(`again` — 표지를 브라우저가 훑기 전에 회차가 끊겨도 알림창이 뜬다).

**한 번만 그린다.** 꺼낸 알림은 비운다. 비우지 않으면 그 뒤 모든 rerun 에 같은 문구가 남아, 사용자가
방금 저장한 것인지 아까 저장한 것인지 알 수 없게 된다. 다음 동작까지 남아야 하는 칸(VOC 지운 글의
적어 둔 답변처럼 알림이 아니라 되살릴 입력을 든 칸, 같은 기준선 알림을 한 번만 세는 칸)은 이 모듈을
지나지 않고 그 까닭을 AST 그물의 허용 목록에 적는다.
"""

from __future__ import annotations

from typing import Literal, NamedTuple, get_args

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation import alerts
from capa_simulation.components.write_guard import held_flash

FlashKind = Literal["success", "info", "warning", "error"]
_KINDS: frozenset[str] = frozenset(get_args(FlashKind))
# 버튼 곁 칸에도 그리는 종류(D3 (가) — 오류 · 거부만). 성공 · 안내는 알림창으로만 낸다.
BESIDE_KINDS: frozenset[str] = frozenset({"warning", "error"})


class FlashNote(NamedTuple):
    """담아 둔 알림 하나 — 종류(`st.success`·`info`·`warning`·`error`), 글, 아이콘, 알림 코드,
    알림창으로만 낼지.

    세션에는 튜플로 남는다 — 코드를 다시 읽은 서버에서도 그대로 읽힌다. 아이콘 · 코드 없는 성공
    알림은 글만 담는다(`queue_flash`). `alert` 는 등록부의 사건 코드이고 None 이면 종류별
    기본(`alerts.FLASH_CODES`)이다. `popup_only` 면 경고 · 오류도 버튼 곁에 그리지 않는다.
    """

    kind: FlashKind
    message: str
    icon: str | None = None
    alert: str | None = None
    popup_only: bool = False


def queue_flash(
    key: str,
    message: str,
    *,
    kind: FlashKind = "success",
    icon: str | None = None,
    alert: str | None = None,
    popup_only: bool = False,
) -> None:
    """동작 직후(콜백·본문)에 부른다. 곧바로 `st.rerun()` 을 불러도 알림이 살아남는다.

    같은 칸에 다시 담으면 앞 알림을 바꾼다. 아이콘 · 코드 없는 성공 알림은 글만 담는다 — 그 칸을
    글로 읽는 시험·도우미가 그대로 읽는다. `alert` 는 등록부의 사건 코드(없으면 종류별 기본)다.
    `popup_only` 는 경고 · 오류도 버튼 곁에 그리지 않고 알림창 · Alarm 에만 낸다 — 동작은 끝났고 그
    자리에 고칠 입력이 없는 경고에 쓴다.
    """
    if kind not in _KINDS:
        raise ValueError(f"알 수 없는 알림 종류입니다: {kind}")
    if alert is not None and alerts.spec(alert).kind != "event":
        raise ValueError(f"버튼 곁 결과 알림은 사건 알림 코드여야 합니다: {alert}")
    st.session_state[key] = (
        message
        if kind == "success" and icon is None and alert is None and not popup_only
        else FlashNote(kind, message, icon, alert, popup_only)
    )


def render_flash(*keys: str) -> DeltaGenerator:
    """늘 서 있는 한 칸을 세우고, `keys` 에 담아 둔 알림을 그 차례대로 알림창 표지로 보내고 비운다.

    경고 · 오류는 그 칸 안에도 그린다(성공 · 안내와 `popup_only` 는 알림창으로만 — D3). 칸은 알림이
    없어도 선다 — 뒤 형제의 순번이 알림 유무로 밀리지 않는다. 돌려받은 칸에 같은 동작의 실패 문구나
    그 자리에 함께 설 알림을 더 쓸 수 있다. 담아 둔 알림이 없는 칸은 쓰기 직후 적어 둔
    알림(`write_guard.held_flash`)이 창 안이면 그 알림을 첫 알림과 같은 id 로 다시 낸다. 표지는 부를
    때마다 이벤트 칸에 정확히 한 자리다.
    """
    slot = st.container()
    sending: list[alerts.AlertNote] = []
    for key in keys:
        note = _note(st.session_state.pop(key, None))
        held = False
        if note is None:
            remembered = held_flash(key)
            note = (
                None if remembered is None else _note((remembered[2], remembered[0], remembered[1]))
            )
            held = note is not None
        if note is None:
            again = alerts.recent_again(key)
            if again is not None:
                sending.append(again)
            continue
        alert = _alert(key, note, held=held)
        alerts.remember_sent(key, alert)
        sending.append(alert)
        if note.kind in BESIDE_KINDS and not note.popup_only:
            _draw(slot, note)
    alerts.emit(sending, slot=slot)
    return slot


def _alert(key: str, note: FlashNote, *, held: bool) -> alerts.AlertNote:
    """`key` 칸 알림의 사건 표지. 다시 낸 알림(`held`)은 그 칸이 방금 보낸 같은 글의 id 를
    잇는다."""
    text = alerts.plain_text(note.message)
    previous = alerts.recent_sent(key) if held else None
    same_id = previous.get("id") if previous is not None and previous.get("full") == text else None
    alert = alerts.event_note(
        note.alert or alerts.FLASH_CODES[note.kind],
        text=text,
        full=text,
        origin=key,
        alert_id=same_id,
    )
    alert["flash"] = note.kind
    # 버튼 곁 원문(마크다운)과 아이콘 — 알림창 · 패널은 평문(`full`)을 쓰고, 시험 · 화면 확인이
    # 원문을 읽는다.
    alert["markdown"] = note.message
    if note.icon:
        alert["icon"] = note.icon
    return alert


def pending_flash(key: str) -> FlashNote | None:
    """`key` 칸에 담아 둔 알림(비우지 않는다). 없으면 None.

    그 칸이 이번 회차에 그릴 것이 있는지 먼저 보아야 하는 자리(끊긴 회차의 결과를 기록에서 되찾을지
    가르는 「지금 실행」)와 시험이 쓴다. 그리기는 늘 `render_flash` 다.
    """
    return _note(st.session_state.get(key))


def _note(value: object) -> FlashNote | None:
    """세션 값을 알림으로 읽는다. 글이면 성공, (종류, 글[, 아이콘[, 코드[, 알림창으로만]]]) 튜플이면
    그 종류다. 등록부에 없는 코드는 종류별 기본으로 읽는다(코드를 다시 읽은 서버가 옛 칸을 읽어도
    멈추지 않게)."""
    if isinstance(value, str):
        return FlashNote("success", value) if value else None
    if not (isinstance(value, tuple) and len(value) in (2, 3, 4, 5)):
        return None
    kind, message, *rest = value
    icon = rest[0] if rest else None
    code = rest[1] if len(rest) > 1 else None
    popup_only = rest[2] if len(rest) > 2 else False
    if kind not in _KINDS or not isinstance(message, str) or not message:
        return None
    if icon is not None and not isinstance(icon, str):
        return None
    if not (isinstance(code, str) and code in alerts.REGISTRY):
        code = None
    return FlashNote(kind, message, icon, code, popup_only is True)


def _draw(slot: DeltaGenerator, note: FlashNote) -> None:
    if note.kind == "success":
        slot.success(note.message, icon=note.icon)
    elif note.kind == "warning":
        slot.warning(note.message, icon=note.icon)
    elif note.kind == "error":
        slot.error(note.message, icon=note.icon)
    else:
        slot.info(note.message, icon=note.icon)
