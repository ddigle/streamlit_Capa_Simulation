# Purpose: Admin Area 「공지」 탭 — 서 있는 공지 카드 · 거두기 · 글 · 끝 시각 · 확인 팝업 보내기.

"""Admin Area 맨 끝 안쪽 탭 「공지」(2026-11-17 공지 보드 답 decided 1 ~ 6).

**쓰는 사람.** 탭은 Admin Area 를 여는 사람에게 선다 — 운영 서버는 관리자뿐이고(페이지 앞머리의
잠금), 개발 PC · WebIDE 는 Admin Area 를 여는 사람이다. 보내는 순간 · 거두는 순간 다시
판정한다(`sso_identity.admin_area_locked` — 페이지 잠금과 같은 판정, 붙여넣기 팝업과 같은 꼴). 팝업
안의 누름은 팝업만 다시 돌아 앞머리 잠금을 지나지 않고, 거두기 콜백은 그린 회차의 단추에서 온다.

**탭 안 차례.** 서 있는 공지 카드(글 · 값 줄 `관리자 · 17:40 보냄 · 18:20 까지` · 「거두기」 — 서
있을 때만) → 글 상자(라벨 접음 · 자리표 「공지 글」 · 300자) → 끝 시각(시각만 · 10분 걸음 — 기본은
지금 + 1시간을 10분 단위로 올림, 세션에 한 번 심는다) · 「보내기」. 화면에 설명 문장을 두지 않는다
(설명은 Guide 「공지」).

**보내기.** 「보내기」 콜백이 글 · 끝 시각을 보고(빈 글 · 300자 넘음은 단추 아래 거부 한 줄 — 고칠
입력이 그 자리에 있다) 팝업을 연 순간의 값(글 · 끝 · 그때 서 있던 공지 id)을 세션에 쥐고 확인 팝업
「공지 보내기」 를 연다 — 값 한 줄 `끝 18:20`(다음 날이면 `끝 내일 18:20`) · 서 있었으면 ` · 서 있는
공지 바뀜`, 「보내기」(primary · 확성기) · 「취소」. 팝업의 「보내기」 는 쥔 값을 그대로 보낸다(다시
계산하지 않는다). 팝업이 열린 사이 남이 보냄 · 거둠 · 끝 시각으로 서 있는 공지가 바뀌었으면 보내지
않고 팝업을 닫아 바뀐 카드를 다시 보인다(`notice_board.NoticeChanged` — 대조는 저장 잠금 안). 결과는
알림창이다(`queue_flash` — 성공은 알림창으로만, 막힘 · 바뀜도 그 자리에 고칠 입력이 없어 알림창 ·
Alarm 만). 같은 내용의 두 번 누름은 한 번이다(저장이 같은 공지를 돌려주고, 같은 세션의 겹친 누름은
`write_guard.save_once`).

**감사 기록.** 운영 서버(기록기가 켜진 기동)는 「공지 보냄」 · 「공지 거둠」 을 남긴다 — 대상은 공지
id, 상세는 결과 · 끝 시각뿐이고 글은 싣지 않는다(감사 불변조건 — 값 원문 없음). 누가는 기록기가 지금
쿠키로 정한다. 개발 PC · WebIDE 는 기록기가 꺼져 있어 아무것도 남지 않는다.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Final, TypedDict

import streamlit as st

from capa_simulation import notice_board
from capa_simulation.audit import recorder as audit_recorder
from capa_simulation.components import write_guard
from capa_simulation.components.admin_dialog import (
    admin_dialog_is_open,
    close_admin_dialog,
    open_admin_dialog,
)
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.sso_identity import admin_area_locked

DIALOG: Final = "notice_send"
FLASH_KEY: Final = "notice_admin_flash"
CARD_KEY: Final = "notice_admin_card"
TEXT_KEY: Final = "notice_admin_text"
UNTIL_KEY: Final = "notice_admin_until"
SEND_KEY: Final = "notice_admin_send"
WITHDRAW_KEY: Final = "notice_admin_withdraw"
CONFIRM_KEY: Final = "notice_admin_confirm"
CANCEL_KEY: Final = "notice_admin_cancel"
# 팝업을 연 순간의 값(`Pending`) · 보낸 뒤 다음 앱 전체 회차가 글 상자 · 끝 시각을 비우라는 표지.
PENDING_KEY: Final = "notice_admin_pending"
CLEAR_KEY: Final = "notice_admin_clear"
SEND_GUARD: Final = "notice_admin_send_guard"
WITHDRAW_GUARD: Final = "notice_admin_withdraw_guard"

TEXT_LABEL: Final = "공지 글"
UNTIL_LABEL: Final = "끝 시각"
SEND_LABEL: Final = "보내기"
WITHDRAW_LABEL: Final = "거두기"
CONFIRM_TITLE: Final = "공지 보내기"
CANCEL_LABEL: Final = "취소"
SEND_ICON: Final = ":material/campaign:"
WITHDRAW_ICON: Final = ":material/notifications_off:"
UNTIL_STEP: Final = timedelta(minutes=notice_board.ROUND_MINUTES)
UNTIL_WIDTH: Final = 150
REPLACES_SUFFIX: Final = " · 서 있는 공지 바뀜"
NEXT_DAY_WORD: Final = "내일 "

SENT_MESSAGE: Final = "공지 보냄 · {until} 까지"
WITHDRAWN_MESSAGE: Final = "공지 거둠"
NOT_ADMIN_MESSAGE: Final = "관리자만 공지를 보내고 거둘 수 있습니다"
CHANGED_MESSAGE: Final = "다른 관리자가 공지를 바꿨습니다 — 서 있는 공지를 보고 다시 보내세요"
GONE_MESSAGE: Final = "서 있는 공지가 바뀌어 거두지 않았습니다"

AUDIT_SEND: Final = "admin_notice_send"
AUDIT_WITHDRAW: Final = "admin_notice_withdraw"


class Pending(TypedDict):
    """확인 팝업을 연 순간의 값 — 다듬은 글 · 끝 시각(ISO) · 그때 서 있던 공지 id(없으면 빈 글)."""

    text: str
    until: str
    expected: str


def confirm_line(until: datetime, *, replaces: bool, now: datetime | None = None) -> str:
    """확인 팝업 값 한 줄 — `끝 18:20`(다음 날이면 `끝 내일 18:20`), 서 있던 공지가 있으면 그것이
    바뀐다는 꼬리."""
    day = NEXT_DAY_WORD if notice_board.is_next_day(until, now) else ""
    line = f"끝 {day}{notice_board.clock_text(until)}"
    return line + (REPLACES_SUFFIX if replaces else "")


def _target(notice_id: str) -> dict[str, str]:
    return {"type": "notice", "id": notice_id}


def _pending() -> Pending | None:
    value = st.session_state.get(PENDING_KEY)
    if not isinstance(value, dict):
        return None
    text, until, expected = value.get("text"), value.get("until"), value.get("expected")
    if not (isinstance(text, str) and isinstance(until, str) and isinstance(expected, str)):
        return None
    return Pending(text=text, until=until, expected=expected)


def _close_confirm() -> None:
    """팝업을 닫는다(닫기 ✕ · 취소 · 보낸 뒤) — 쥔 값도 버린다."""
    st.session_state.pop(PENDING_KEY, None)
    close_admin_dialog()


def _open_confirm() -> None:
    """「보내기」 콜백 — 다시 판정하고 글 · 끝 시각을 본 뒤 그 순간의 값을 쥐고 팝업을 연다."""
    if admin_area_locked():
        queue_flash(FLASH_KEY, NOT_ADMIN_MESSAGE, kind="error", popup_only=True)
        return
    moment = notice_board.now_kst()
    raw = st.session_state.get(TEXT_KEY)
    chosen = st.session_state.get(UNTIL_KEY)
    clock = chosen if isinstance(chosen, time) else notice_board.default_until(moment).time()
    until = notice_board.until_from_time(clock, moment)
    try:
        text = notice_board.check(raw if isinstance(raw, str) else "", until, now=moment)
    except ValueError as exc:
        write_guard.queue_refusal(SEND_GUARD, str(exc))
        return
    standing = notice_board.current(moment)
    st.session_state[PENDING_KEY] = Pending(
        text=text, until=until.isoformat(), expected="" if standing is None else standing.id
    )
    open_admin_dialog(DIALOG)


def submit_notice(pending: Pending) -> None:
    """팝업의 「보내기」 한 번 — 다시 판정하고 쥔 값을 그대로 보낸다. 결과는 알림 칸에 담는다."""
    if admin_area_locked():
        audit_recorder.record(AUDIT_SEND, out="denied", det={"result": "not_admin"})
        queue_flash(FLASH_KEY, NOT_ADMIN_MESSAGE, kind="error", popup_only=True)
        return
    until = datetime.fromisoformat(pending["until"])
    before = notice_board.current()
    sent: list[notice_board.Notice] = []

    def attempt() -> notice_board.Notice:
        notice = notice_board.send(pending["text"], until, expected=pending["expected"])
        sent.append(notice)
        return notice

    start = (pending["text"], pending["until"], pending["expected"])
    try:
        notice = write_guard.save_once(SEND_GUARD, start, attempt, wrote=lambda _: True)
    except notice_board.NoticeChanged:
        audit_recorder.record(AUDIT_SEND, out="fail", det={"result": "changed"})
        queue_flash(FLASH_KEY, CHANGED_MESSAGE, kind="warning", popup_only=True)
        return
    except ValueError as exc:
        audit_recorder.record(AUDIT_SEND, out="fail", det={"result": "invalid"})
        queue_flash(FLASH_KEY, str(exc), kind="error", popup_only=True)
        return
    if sent and (before is None or before.id != notice.id):
        audit_recorder.record(
            AUDIT_SEND,
            tgt=_target(notice.id),
            det={"result": "sent", "until": notice.until.isoformat(timespec="minutes")},
        )
    st.session_state[CLEAR_KEY] = True
    queue_flash(FLASH_KEY, SENT_MESSAGE.format(until=notice_board.clock_text(notice.until)))


def withdraw_notice(notice_id: str) -> None:
    """「거두기」 콜백 — 다시 판정하고 그린 회차의 공지가 아직 서 있을 때만 걷는다."""
    if admin_area_locked():
        audit_recorder.record(
            AUDIT_WITHDRAW, out="denied", tgt=_target(notice_id), det={"result": "not_admin"}
        )
        queue_flash(FLASH_KEY, NOT_ADMIN_MESSAGE, kind="error", popup_only=True)
        return
    ran: list[bool] = []

    def attempt() -> bool:
        ran.append(True)
        return notice_board.withdraw(notice_id)

    done = write_guard.save_once(WITHDRAW_GUARD, notice_id, attempt, wrote=bool)
    if not done:
        audit_recorder.record(
            AUDIT_WITHDRAW, out="fail", tgt=_target(notice_id), det={"result": "changed"}
        )
        queue_flash(FLASH_KEY, GONE_MESSAGE, kind="warning", popup_only=True)
        return
    if ran:
        audit_recorder.record(AUDIT_WITHDRAW, tgt=_target(notice_id), det={"result": "withdrawn"})
    queue_flash(FLASH_KEY, WITHDRAWN_MESSAGE)


@st.dialog(CONFIRM_TITLE, on_dismiss=_close_confirm)
def _confirm_dialog() -> None:
    pending = _pending()
    if pending is None:
        _close_confirm()
        st.rerun()
    until = datetime.fromisoformat(pending["until"])
    st.caption(confirm_line(until, replaces=bool(pending["expected"])))
    with st.container(horizontal=True, gap="small"):
        send = st.button(SEND_LABEL, type="primary", icon=SEND_ICON, key=CONFIRM_KEY)
        cancel = st.button(CANCEL_LABEL, key=CANCEL_KEY)
    if send:
        submit_notice(pending)
    if send or cancel:
        _close_confirm()
        st.rerun()


def _render_standing(notice: notice_board.Notice) -> None:
    """서 있는 공지 카드 — 글(평문 그대로) · 값 줄 · 「거두기」."""
    with st.container(border=True, key=CARD_KEY):
        st.text(notice.text)
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.caption(notice_board.stamp_line(notice))
            st.button(
                WITHDRAW_LABEL,
                icon=WITHDRAW_ICON,
                key=WITHDRAW_KEY,
                on_click=withdraw_notice,
                args=(notice.id,),
            )


def render_notice_admin() -> None:
    """Admin Area 「공지」 탭 몸. 입력 탭이라 닫혀 있어도 늘 그린다(위젯 값 보존)."""
    moment = notice_board.now_kst()
    if st.session_state.pop(CLEAR_KEY, False):
        st.session_state.pop(TEXT_KEY, None)
        st.session_state.pop(UNTIL_KEY, None)
    if UNTIL_KEY not in st.session_state:
        st.session_state[UNTIL_KEY] = notice_board.default_until(moment).time()
    render_flash(FLASH_KEY)
    standing = notice_board.current(moment)
    if standing is not None:
        _render_standing(standing)
    st.text_area(
        TEXT_LABEL,
        key=TEXT_KEY,
        max_chars=notice_board.TEXT_LIMIT,
        placeholder=TEXT_LABEL,
        label_visibility="collapsed",
    )
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        st.time_input(UNTIL_LABEL, key=UNTIL_KEY, step=UNTIL_STEP, width=UNTIL_WIDTH)
        st.button(SEND_LABEL, icon=SEND_ICON, key=SEND_KEY, on_click=_open_confirm)
    refusal = write_guard.take_refusal(SEND_GUARD)
    if refusal is not None:
        st.error(refusal, icon=":material/block:")
    if admin_dialog_is_open(DIALOG):
        _confirm_dialog()
