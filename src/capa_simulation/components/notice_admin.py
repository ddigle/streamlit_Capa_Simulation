# Purpose: Admin Area 「공지」 탭 — 서 있는 공지 카드 · 거두기 · 글 · 끝 시각 · 확인 팝업 보내기.

"""Admin Area 맨 끝 안쪽 탭 「공지」(2026-11-17 공지 보드 답 decided 1 ~ 6).

**쓰는 사람.** 탭은 Admin Area 를 여는 사람에게 선다 — 운영 서버는 관리자뿐이고(페이지 앞머리의
잠금), 개발 PC · WebIDE 는 Admin Area 를 여는 사람이다. 보내는 순간 · 거두는 순간 다시
판정한다(`sso_identity.admin_area_locked` — 페이지 잠금과 같은 판정, 붙여넣기 팝업과 같은 꼴). 팝업
안의 누름은 팝업만 다시 돌아 앞머리 잠금을 지나지 않고, 거두기 콜백은 그린 회차의 단추에서 온다.

**탭 안 차례.** 서 있는 공지 카드(글 · 값 줄 `관리자 · 17:40 보냄 · 18:20 까지` · 「거두기」 — 서
있을 때만) → 글 상자(라벨 접음 · 자리표 「공지 글」 · 300자) → 끝 시각(시각만 · 10분 걸음 — 기본은
지금 + 1시간을 10분 단위로 올림) · 「보내기」. 화면에 설명 문장을 두지 않는다(설명은 Guide
「공지」).

**끝 시각 기본값.** 탭을 그릴 때 끝 시각 칸이 없으면(Admin Area 를 처음 열 때 · 다른 화면에 다녀와
위젯 값이 걷힌 뒤) 기본값을 심고, 심은 순간의 끝(날짜까지)을 따로 적어 둔다(`SEEDED_KEY`). 사람이
손대지 않은 기본값이 지나면(Admin Area 에 오래 머묾) 그리기 앞과 「보내기」 콜백에서 새 기본값으로
간다 — 그대로 두면 지난 시각이라 「내일 그 시각」(거의 하루짜리 공지)이 된다. 사람이 고른 시각은
지났어도 그대로 「내일 그 시각」 이다(확인 팝업 값 줄이 「내일」 을 단다).

**보내기.** 「보내기」 콜백이 글 · 끝 시각을 보고(빈 글 · 300자 넘음은 단추 아래 거부 한 줄 — 고칠
입력이 그 자리에 있다) 팝업을 연 순간의 값(글 · 끝 · 그때 서 있던 공지 id)을 세션에 쥐고 확인 팝업
「공지 보내기」 를 연다 — 값 한 줄 `끝 18:20`(다음 날이면 `끝 내일 18:20`) · 서 있었으면 ` · 서 있는
공지 바뀜`, 「보내기」(primary · 확성기) · 「취소」. 팝업의 「보내기」 는 쥔 값을 그대로 보낸다(다시
계산하지 않는다). 팝업이 열린 사이 서 있는 공지가 바뀌었으면(갈음 · 거둠 · 끝 시각으로 걷힘) 보내지
않고 팝업을 닫아 바뀐 카드를 다시 보인다(`notice_board.NoticeChanged` — 대조는 저장 잠금 안). 알림
글은 까닭 둘(서 있던 공지가 없어짐 · 다른 공지가 섬)로 가르고 누가 했는지 지목하지 않는다 — 같은
관리자의 다른 탭 · 끝 시각일 수도 있다. 결과는
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
from capa_simulation.components.sso_identity import developer_wall_locked

DIALOG: Final = "notice_send"
FLASH_KEY: Final = "notice_admin_flash"
CARD_KEY: Final = "notice_admin_card"
TEXT_KEY: Final = "notice_admin_text"
UNTIL_KEY: Final = "notice_admin_until"
# 끝 시각 칸에 심은 기본값의 끝(KST ISO — 날짜까지). 위젯 키가 아니라 화면을 떠나도 남는다.
SEEDED_KEY: Final = "notice_admin_until_seeded"
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
NOT_ADMIN_MESSAGE: Final = "개발자만 공지를 보내고 거둘 수 있습니다"
CHANGED_MESSAGE: Final = "서 있는 공지가 바뀌었습니다 — 서 있는 공지를 보고 다시 보내세요"
ENDED_MESSAGE: Final = "서 있던 공지가 끝났거나 거둬졌습니다 — 다시 보내세요"
GONE_MESSAGE: Final = "서 있는 공지가 바뀌어 거두지 않았습니다"
ALREADY_GONE_MESSAGE: Final = "서 있던 공지는 이미 끝났거나 거둬졌습니다"

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


def _seed_until(moment: datetime) -> time:
    """끝 시각 칸에 기본값을 심고 그 끝(날짜까지)을 적어 둔다 — 위젯이 서기 전 · 콜백에서만
    부른다."""
    target = notice_board.default_until(moment)
    st.session_state[UNTIL_KEY] = target.time()
    st.session_state[SEEDED_KEY] = target.isoformat()
    return target.time()


def stale_seed(chosen: object, seeded: object, moment: datetime) -> bool:
    """끝 시각 칸이 손대지 않은 기본값 그대로이고 그 기본값이 지났나 — 그러면 새 기본값으로 간다.
    사람이 고른 값(심은 시각과 다름)은 지났어도 거짓이다."""
    if not isinstance(chosen, time) or not isinstance(seeded, str):
        return False
    try:
        target = datetime.fromisoformat(seeded)
    except ValueError:
        return False
    if target.utcoffset() is None:
        return False
    return chosen == target.time() and target <= moment


def _close_confirm() -> None:
    """팝업을 닫는다(닫기 ✕ · 취소 · 보낸 뒤) — 쥔 값도 버린다."""
    st.session_state.pop(PENDING_KEY, None)
    close_admin_dialog()


def _open_confirm() -> None:
    """「보내기」 콜백 — 다시 판정하고 글 · 끝 시각을 본 뒤 그 순간의 값을 쥐고 팝업을 연다."""
    if developer_wall_locked():
        queue_flash(FLASH_KEY, NOT_ADMIN_MESSAGE, kind="error", popup_only=True)
        return
    moment = notice_board.now_kst()
    raw = st.session_state.get(TEXT_KEY)
    chosen = st.session_state.get(UNTIL_KEY)
    if not isinstance(chosen, time) or stale_seed(chosen, st.session_state.get(SEEDED_KEY), moment):
        chosen = _seed_until(moment)
    until = notice_board.until_from_time(chosen, moment)
    try:
        text = notice_board.check(raw if isinstance(raw, str) else "", until, now=moment)
    except notice_board.NoticeInvalid as exc:
        write_guard.queue_refusal(SEND_GUARD, exc.message)
        return
    standing = notice_board.current(moment)
    st.session_state[PENDING_KEY] = Pending(
        text=text, until=until.isoformat(), expected="" if standing is None else standing.id
    )
    open_admin_dialog(DIALOG)


def submit_notice(pending: Pending) -> None:
    """팝업의 「보내기」 한 번 — 다시 판정하고 쥔 값을 그대로 보낸다. 결과는 알림 칸에 담는다."""
    if developer_wall_locked():
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
    except notice_board.NoticeChanged as exc:
        result, message = ("ended", ENDED_MESSAGE) if exc.ended else ("changed", CHANGED_MESSAGE)
        audit_recorder.record(AUDIT_SEND, out="fail", det={"result": result})
        queue_flash(FLASH_KEY, message, kind="warning", popup_only=True)
        return
    except notice_board.NoticeInvalid as exc:
        audit_recorder.record(AUDIT_SEND, out="fail", det={"result": "invalid"})
        queue_flash(FLASH_KEY, exc.message, kind="error", popup_only=True)
        return
    if sent and (before is None or before.id != notice.id):
        audit_recorder.record(
            AUDIT_SEND,
            tgt=_target(notice.id),
            det={"result": "sent", "until": notice.until.isoformat(timespec="minutes")},
        )
    st.session_state[CLEAR_KEY] = True
    queue_flash(FLASH_KEY, SENT_MESSAGE.format(until=notice_board.until_text(notice)))


def withdraw_notice(notice_id: str) -> None:
    """「거두기」 콜백 — 다시 판정하고 그린 회차의 공지가 아직 서 있을 때만 걷는다."""
    if developer_wall_locked():
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
        # 카드는 그린 회차의 것이다 — 그 사이 끝 시각으로 걷혔거나 거둬졌으면(지금 공지 없음)
        # 「바뀜」 이 아니다.
        ended = notice_board.current() is None
        audit_recorder.record(
            AUDIT_WITHDRAW,
            out="fail",
            tgt=_target(notice_id),
            det={"result": "ended" if ended else "changed"},
        )
        message = ALREADY_GONE_MESSAGE if ended else GONE_MESSAGE
        queue_flash(FLASH_KEY, message, kind="warning", popup_only=True)
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
    # 보낸 뒤 첫 앱 전체 회차 — 위젯이 서기 전에 글 상자를 비우고 끝 시각을 새 기본값으로 둔다. 칸이
    # 없거나(처음 · 다녀온 뒤) 손대지 않은 기본값이 지났어도 새 기본값이다(모듈 설명 「끝 시각
    # 기본값」).
    if st.session_state.get(CLEAR_KEY):
        st.session_state[CLEAR_KEY] = False
        st.session_state[TEXT_KEY] = ""
        _seed_until(moment)
    elif UNTIL_KEY not in st.session_state or stale_seed(
        st.session_state.get(UNTIL_KEY), st.session_state.get(SEEDED_KEY), moment
    ):
        _seed_until(moment)
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
