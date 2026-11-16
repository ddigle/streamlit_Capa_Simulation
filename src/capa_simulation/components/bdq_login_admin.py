# Purpose: Admin Area 「BDQ 자동 로그인」 — 관리자에게만 저장된 BigDataQuery 계정의 상태 줄 ·
# 넣기 폼 · 지우기를 그린다.

"""Admin 「BDQ 자동 로그인」(2026-11-16 사용자 결정 D1 · D2 · D5 · D7).

**자리.** 동기화 모드 `managed` 이고 키(`CAPA_BDQ_SECRET_KEY`)를 쓸 수 있는 서버의 관리자 회차에만
Admin Area 「서버 시작 점검」 펼침 바로 뒤에 펼침 하나로 선다. 문지기는 「토큰 넣기」 와 같은
`sso_identity.viewer_is_admin` 이다. 그 밖(개발 · WebIDE · 사내 PC · 키 없음 · 관리자가 아님)에는
Streamlit 호출이 하나도 없다 — 요소 순번이 그대로다. 펼침 이름은 「서버 시작 점검」 표 줄과 같은
`BDQ_LOGIN_LABEL` 하나다(설계 규칙 UI-CON-02). 자동 로그인 멈춤 알림 `AD-23` 과 계정 없음 `AD-10` 의
「그 화면으로」 가 이 펼침을 연다(`open_bdq_login` — 알림 칸 받는 쪽 `BDQ_LOGIN_TARGET_KIND`,
UI-NAV-01).

**보이는 것(D7).** 값 줄 둘 — 상태(없음 · 정상 · 멈춤과 까닭 · 확인하지 못함)와 넣은 관리자 앱
로그인 ID 앞 두 글자 · 넣은 시각(멈춤이면 멈춘 시각), 그리고 이 프로세스의 마지막 시도(시각 ·
자동/넣기 · 결과 · 남은 시간). BDQ 계정 ID 는 어디에도 보이지 않는다. 상태는 저장소
기억(`bdq_login.status` — 앱 기동 때 읽어 둔 것)에서 읽는다.

**넣기(D5).** `st.form(clear_on_submit=True)` — 계정 칸 · 비밀번호 칸(`type="password"`) · 「넣기」.
칸 라벨은 접고 자리표시 글이 그 이름이다. 「넣기」 의 콜백(`_on_submit` — 본문보다 먼저 돈다)이 두
칸의 값을 읽자마자 세션 칸을 빈 글로 바꾸고(`_take_inputs` — 그 회차의 본문 · 뒤 회차 어디에도 계정
· 비밀번호가 세션에 없다), 누른 회차의 신원을 다시 검증해 관리자일 때만 로그인 시험 한
번(`bdq_login.login_from_form`)을 한다. 로그인이 되고 저장까지 되면 결과를 알림창으로
낸다(「BigDataQuery 로그인 됨 · 남은 n시간 n분」). 그때 멈춤이 풀리고 떠 있는 앱의 계정 원천이
곧바로 새 ID 다(저장소 기억 — 조회 · 토큰 파일 · 남은 시간). 로그인이 실패하면 저장하지 않고 앞 저장
· 상태를 그대로 두며 실패 한 줄을 폼 아래에 둔다(「로그인 실패 — 저장 안 함」 · 「서버에 닿지 못함 —
저장 안 함」 · 「패키지 없음 — 저장 안 함」 — Alarm 에도 남는다). 로그인은 됐는데 저장하지 못했으면
알림창 오류다(그 자리에 고칠 입력이 없다 — UI-NTF-03). 빈 칸 · 관리자 아님은 시도 없이 폼 아래 거부
한 줄이다(`write_guard.queue_refusal` → 본문 `take_refusal`). 같은 세션의 겹쳐 온 둘째 누름은 로그인
한 번이다(`write_guard.save_once` — 계정 잠김 방지). 시도를 시작하거나 끝낸 때부터 창 안에 온 빈
제출(폼이 이미 비운 칸의 더블클릭 꼬리)은 거부를 세우지 않는다(`write_guard.just_written`).

**지우기.** 저장된 계정이 있을 때만 상태 줄 곁에 「정말 지웁니다」 확인 체크와 「지우기」 가 선다 —
페이지 안 확인 한 번(브라우저 대화상자가 아니다). 체크를 켜야 눌린다(잠긴 동안 까닭 풍선). 지우면
자동 로그인이 꺼지고 예비 길(「토큰 넣기」 · `CAPA_BDQ_TOKEN`)만 남는다 — 단추 풍선이 누르기 전에
말한다(UI-NTF-09).

**비밀.** 세션 · 알림 · 감사 줄 · 로그에 계정 · 비밀번호가 없다 — 감사 줄은 결과 · 까닭 코드만이다.

**「토큰 넣기」 와.** 「토큰 넣기」(`bdq_token_admin` — 「서버 시작 점검」 펼침 안)는 예비로 남는다.
이 펼침은 계정을, 그 단추는 토큰 값을 넣는다 — 같은 결과를 내는 단추가 아니다(UI-LAY-12)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Final

import streamlit as st

from capa_simulation import alerts
from capa_simulation.audit import recorder as audit_recorder
from capa_simulation.components import sso_identity, write_guard
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.paste_form import PASTE_CONFIRM_WHY
from capa_simulation.components.sso_status import CLOCK_FORMAT
from capa_simulation.io import bdq_login
from capa_simulation.io import bdq_login_store as login_store
from capa_simulation.io.container_start_report import (
    BDQ_LOGIN_LABEL,
    BDQ_TOKEN_ENV,
    login_reason_text,
    remaining_text,
)
from capa_simulation.korea_time import kst_clock
from capa_simulation.sidebar_status import remembered_box_key, remembered_expander

EXPANDER_KEY: Final = "admin_area_bdq_login"
FORM_KEY: Final = "admin_area_bdq_login_form"
ACCOUNT_KEY: Final = "admin_area_bdq_login_account"
PASSWORD_KEY: Final = "admin_area_bdq_login_password"
FLASH_KEY: Final = "admin_area_bdq_login_flash"
DELETE_CONFIRM_KEY: Final = "admin_area_bdq_login_delete_confirm"
DELETE_KEY: Final = "admin_area_bdq_login_delete"
# 알림의 「그 화면으로」 가 Admin Area 에 닿은 뒤 이 펼침을 여는 받는 쪽의
# 이름(`alerts.GotoTarget`).
BDQ_LOGIN_TARGET_KIND: Final = "bdq_login"
# 같은 세션의 빠른 두 번 누름을 거르는 이름(`write_guard.save_once`). 첫 시도가 끝난 뒤
# 창(`TRAILING_PRESS_SECONDS`) 안에 **같은 값**으로 닿은 둘째 누름은 시도하지 않고 첫 결과를 다시
# 알린다. 넣기의 출발점은 값의 지문(`_input_mark` — 프로세스마다 새로 만든 키로 단 HMAC, 계정 ·
# 비밀번호 글이 아니다)이고 지우기는 고정 값이다.
SUBMIT_GUARD: Final = "admin_area_bdq_login_submit_guard"
DELETE_GUARD: Final = "admin_area_bdq_login_delete_guard"
DELETE_START: Final = "delete"
_MARK_KEY: Final = secrets.token_bytes(32)

ACCOUNT_LABEL: Final = "BDQ 계정"
PASSWORD_LABEL: Final = "비밀번호"
APPLY_LABEL: Final = "넣기"
DELETE_LABEL: Final = "지우기"
DELETE_CONFIRM_LABEL: Final = "정말 지웁니다"
# 누르기 전에 알아야 할 것 — 덮어쓰기 · 실패면 저장 안 함(UI-NTF-09).
APPLY_HELP: Final = (
    "이 계정으로 BigDataQuery 에 한 번 로그인해 보고, 되면 저장합니다(앞서 저장된 계정을 바꾸고 "
    "멈춤을 풉니다). 로그인이 실패하면 저장하지 않습니다."
)
DELETE_HELP: Final = (
    "저장된 계정을 지웁니다 — 되돌릴 수 없고 자동 로그인이 꺼집니다. 조회는 예비 "
    f"토큰(「토큰 넣기」 · CD 환경변수 {BDQ_TOKEN_ENV})으로 합니다."
)

STATUS_LABEL: Final = "**상태**"
LAST_LABEL: Final = "**마지막 시도**"
NONE_WORD: Final = "없음"
OK_WORD: Final = "정상"
STOPPED_WORD: Final = "멈춤"
UNREAD_WORD: Final = "확인하지 못함"
UNKNOWN_CLOCK: Final = "시각 모름"
AUTO_WORD: Final = "자동"
FORM_WORD: Final = "넣기"

NOT_ADMIN_MESSAGE: Final = "관리자만 계정을 넣을 수 있습니다"
BLANK_MESSAGE: Final = "계정과 비밀번호를 모두 넣으세요"
NOT_SAVED: Final = "저장 안 함"
SAVE_FAILED_MESSAGE: Final = (
    "BigDataQuery 로그인은 됐지만 계정을 저장하지 못했습니다 — 앞서 저장된 계정 · 상태 그대로"
)
DELETED_MESSAGE: Final = "BigDataQuery 자동 로그인 계정을 지웠습니다"
DELETE_FAILED_MESSAGE: Final = (
    "BigDataQuery 자동 로그인 계정을 지우지 못했습니다 — 저장된 계정 그대로"
)
CONFIRM_FIRST_MESSAGE: Final = f"「{DELETE_CONFIRM_LABEL}」 를 체크한 뒤 지우세요"
NOT_ADMIN_DELETE_MESSAGE: Final = "관리자만 계정을 지울 수 있습니다"

AUDIT_SET: Final = "admin_bdq_login_set"
AUDIT_DELETE: Final = "admin_bdq_login_delete"
# 패키지 · 하위 프로세스가 서지 못한 까닭 — 결과 줄은 「패키지 없음」.
_PACKAGE_REASONS: Final = frozenset(
    {bdq_login.REASON_IMPORT_FAILED, bdq_login.REASON_SPAWN_FAILED, bdq_login.REASON_NO_INPUT}
)
# 저장소 읽기 까닭 가운데 「없음」 으로 읽는 것과 「확인하지 못함」 으로 읽는 것.
_ABSENT_REASONS: Final = frozenset({"", login_store.REASON_NO_OBJECT})
_UNREAD_REASONS: Final = frozenset(
    {login_store.REASON_UNREAD, login_store.REASON_NO_TARGET, *login_store.OFF_REASONS}
)


def form_visible() -> bool:
    """이 회차에 펼침이 서는가 — 기능이 서고(`managed` + 쓸 수 있는 키, S3 에 묻지 않는다) 관리자다.
    키는 앱이 기동 때 쥐고 환경에서 뺐으므로 환경을 넘기지 않는다."""
    try:
        if login_store.availability() is not None:
            return False
    except Exception:  # 설정을 읽다 깨져도 Admin Area 는 선다 — 펼침만 없다
        return False
    return sso_identity.viewer_is_admin()


def _clock(text: str | None) -> str:
    """저장 객체 · 시도 기록의 KST ISO 시각 → 화면 시각(`CLOCK_FORMAT`). 못 읽으면 「시각 모름」."""
    if not text:
        return UNKNOWN_CLOCK
    try:
        return kst_clock(datetime.fromisoformat(text), CLOCK_FORMAT)
    except (OverflowError, OSError, ValueError):
        return UNKNOWN_CLOCK


def status_line(status: bdq_login.LoginStatus | None) -> str:
    """「상태」 값 줄 — 상태 낱말(멈춤이면 까닭)과 넣은 사람 두 글자 · 넣은 시각(멈춤이면 멈춘
    시각). 계정 ID 는 없다. `None` 은 상태를 읽지 못한 회차다."""
    if status is None:
        return f"{STATUS_LABEL} · {UNREAD_WORD}"
    stored = status.load.stored
    if stored is None:
        reason = status.load.reason
        if reason in _ABSENT_REASONS:
            return f"{STATUS_LABEL} · {NONE_WORD}"
        word = UNREAD_WORD if reason in _UNREAD_REASONS else NONE_WORD
        return f"{STATUS_LABEL} · {word}({login_reason_text(reason)})"
    who = f"넣은 사람 {literal_markdown(stored.entered_by) or '-'} · {_clock(stored.entered_at)}"
    if status.state == "ok":
        return f"{STATUS_LABEL} · {OK_WORD} · {who}"
    reason = status.stop_reason
    detail = login_reason_text(reason) if reason else "까닭 모름"
    stopped_at = stored.stopped_at or (status.last.at if status.last is not None else "")
    return f"{STATUS_LABEL} · {STOPPED_WORD}({detail}) · {who} · 멈춘 때 {_clock(stopped_at)}"


def result_words(result: bdq_login.LoginResult) -> str:
    """로그인 결과 낱말 — 성공이면 남은 시간까지."""
    if result.ok:
        return f"로그인 됨 · {remaining_text(result.remaining_minutes)}"
    if result.outcome == bdq_login.OUTCOME_REJECTED:
        return "로그인 실패"
    if result.outcome == bdq_login.OUTCOME_UNREACHED:
        return "서버에 닿지 못함"
    if result.reason in _PACKAGE_REASONS:
        return "패키지 없음"
    return f"로그인하지 않음({login_reason_text(result.reason)})"


def last_line(status: bdq_login.LoginStatus | None) -> str | None:
    """「마지막 시도」 값 줄 — 이 프로세스의 마지막 시도가 없으면 `None`."""
    last = None if status is None else status.last
    if last is None:
        return None
    how = AUTO_WORD if last.auto else FORM_WORD
    return f"{LAST_LABEL} · {_clock(last.at)} · {how} · {result_words(last.result)}"


def failure_line(result: bdq_login.LoginResult) -> str:
    """폼 제출이 로그인에 실패한 결과 한 줄(D5) — 무엇이 실패했고 저장하지 않았다."""
    return f"{result_words(result)} — {NOT_SAVED}"


def _read_status() -> bdq_login.LoginStatus | None:
    """지금 상태 — 읽다 무엇이 나도 「확인하지 못함」(`None`)으로 물러선다."""
    try:
        return bdq_login.status()
    except Exception:
        return None


def _take_inputs() -> tuple[str, str]:
    """「넣기」 콜백 — 두 칸 값을 읽고 세션 칸을 곧바로 빈 글로 바꾼다(위젯이 서기 전이라 바꿀 수
    있다) — 거부 · 실패로 끝나도 계정 · 비밀번호가 세션에 머물지 않게. 계정은 앞뒤 공백을
    뗀다(로그인 실행기는 공백 붙은 계정을 받지 않는다)."""
    account = str(st.session_state.get(ACCOUNT_KEY, "") or "").strip()
    password = str(st.session_state.get(PASSWORD_KEY, "") or "")
    st.session_state[ACCOUNT_KEY] = ""
    st.session_state[PASSWORD_KEY] = ""
    return account, password


def _input_mark(account: str, password: str) -> str:
    """넣은 값의 지문 — 겹쳐 온 둘째 누름이 같은 값인지만 가른다. 프로세스 키로 단 HMAC 이라 세션에
    남아도 계정 · 비밀번호를 되찾을 수 없다."""
    return hmac.new(_MARK_KEY, f"{account}\0{password}".encode(), hashlib.sha256).hexdigest()


def _code(text: str) -> str:
    """감사 줄 까닭 — 짧은 영문 코드 앞마디만(`write_failed:timeout` → `write_failed`)."""
    return text.split(":", 1)[0]


def _announce(outcome: bdq_login.FormResult) -> None:
    """폼 제출 결과를 알린다 — 저장까지 되면 알림창, 로그인 실패는 폼 아래 한 줄 + Alarm, 로그인은
    됐는데 저장하지 못했으면 알림창 오류."""
    result = outcome.result
    if outcome.saved:
        audit_recorder.record(AUDIT_SET, det={"result": "saved", "reason": result.warning})
        queue_flash(FLASH_KEY, f"BigDataQuery {result_words(result)}")
        return
    if result.ok:
        audit_recorder.record(
            AUDIT_SET,
            out="fail",
            det={"result": "save_failed", "reason": _code(outcome.save_failure)},
        )
        queue_flash(FLASH_KEY, SAVE_FAILED_MESSAGE, kind="error", popup_only=True)
        return
    audit_recorder.record(
        AUDIT_SET, out="fail", det={"result": result.outcome, "reason": result.reason}
    )
    queue_flash(FLASH_KEY, failure_line(result), kind="error")


def submit_login(account: str, password: str) -> str | None:
    """넣기 한 번 — 폼 아래 거부 한 줄(시도 없음) 또는 `None`(결과는 알림 칸에 담았다). 누른 회차의
    신원을 다시 검증한다(그려진 폼을 믿지 않는다)."""
    if not sso_identity.viewer_is_admin():
        audit_recorder.record(AUDIT_SET, out="denied", det={"result": "not_admin"})
        return NOT_ADMIN_MESSAGE
    if not account and not password and write_guard.just_written(SUBMIT_GUARD):
        return None
    if not account or not password:
        return BLANK_MESSAGE
    identity = sso_identity.verified_identity()
    login_id = "" if identity is None else identity.loginid

    def attempt() -> bdq_login.FormResult:
        return bdq_login.login_from_form(account, password, login_id)

    mark = _input_mark(account, password)
    # 시도 앞뒤로 적는다 — 로그인이 도는 동안 닿은 더블클릭의 빈 꼬리도 창 안이다.
    write_guard.note_written(SUBMIT_GUARD)
    outcome = write_guard.save_once(SUBMIT_GUARD, mark, attempt, wrote=lambda _: True)
    write_guard.note_written(SUBMIT_GUARD)
    _announce(outcome)
    return None


def _on_submit() -> None:
    """「넣기」 콜백 — 칸 값을 떼고(`_take_inputs`) 넣기 한 번. 거부는 본문이 폼 아래에 그린다."""
    account, password = _take_inputs()
    refusal = submit_login(account, password)
    if refusal is not None:
        write_guard.queue_refusal(SUBMIT_GUARD, refusal)


def _delete() -> None:
    """「지우기」 콜백 — 누른 회차의 신원을 다시 검증하고 확인 체크를 본 뒤 지운다."""
    if not sso_identity.viewer_is_admin():
        audit_recorder.record(AUDIT_DELETE, out="denied", det={"result": "not_admin"})
        queue_flash(FLASH_KEY, NOT_ADMIN_DELETE_MESSAGE, kind="error", popup_only=True)
        return
    if not st.session_state.get(DELETE_CONFIRM_KEY):
        queue_flash(FLASH_KEY, CONFIRM_FIRST_MESSAGE, kind="warning")
        return
    write = write_guard.save_once(
        DELETE_GUARD, DELETE_START, bdq_login.forget_login, wrote=lambda done: done.ok
    )
    st.session_state[DELETE_CONFIRM_KEY] = False
    if write.ok:
        audit_recorder.record(AUDIT_DELETE, det={"result": "deleted"})
        queue_flash(FLASH_KEY, DELETED_MESSAGE)
        return
    audit_recorder.record(AUDIT_DELETE, out="fail", det={"result": _code(write.reason)})
    queue_flash(FLASH_KEY, DELETE_FAILED_MESSAGE, kind="error", popup_only=True)


def _render_status(status: bdq_login.LoginStatus | None) -> None:
    """상태 줄과 그 곁 지우기(저장된 계정이 있을 때만), 그 아래 마지막 시도 줄."""
    stored = None if status is None else status.load.stored
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.caption(status_line(status), width="content")
        if stored is not None:
            confirmed = st.checkbox(DELETE_CONFIRM_LABEL, key=DELETE_CONFIRM_KEY)
            st.button(
                DELETE_LABEL,
                icon=":material/delete:",
                key=DELETE_KEY,
                disabled=not confirmed,
                help=DELETE_HELP if confirmed else PASTE_CONFIRM_WHY,
                on_click=_delete,
            )
    last = last_line(status)
    if last is not None:
        st.caption(last)


def bdq_login_target() -> alerts.GotoTarget:
    """알림 「그 화면으로」 가 들고 가는 대상 — 받는 쪽이 이 펼침을 연다(나머지 칸은 쓰지
    않는다)."""
    return alerts.GotoTarget(kind=BDQ_LOGIN_TARGET_KIND, scenario="-", revision="-")


def open_bdq_login(_scenario: str, _revision: str) -> None:
    """알림 칸의 「그 화면으로」 콜백이 Admin Area 에 닿은 회차 맨 앞에서 부른다 — 「BDQ 자동
    로그인」 펼침을 연다(설계 규칙 UI-NAV-01 — 데려가면 그 자리까지 연다)."""
    st.session_state[EXPANDER_KEY] = True
    st.session_state[remembered_box_key(EXPANDER_KEY)] = (True, BDQ_LOGIN_LABEL)


def render_bdq_login_admin() -> None:
    """Admin 「BDQ 자동 로그인」 펼침. 자리가 없는 회차에는 아무것도 부르지 않는다(모듈 설명)."""
    if not form_visible():
        return
    with remembered_expander(BDQ_LOGIN_LABEL, icon=":material/passkey:", key=EXPANDER_KEY):
        # 넣기 · 지우기는 콜백이라 이 회차의 상태 줄에 이미 든다.
        _render_status(_read_status())
        with st.form(FORM_KEY, clear_on_submit=True, border=False):
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                st.text_input(
                    ACCOUNT_LABEL,
                    key=ACCOUNT_KEY,
                    placeholder=ACCOUNT_LABEL,
                    autocomplete="off",
                    label_visibility="collapsed",
                )
                st.text_input(
                    PASSWORD_LABEL,
                    key=PASSWORD_KEY,
                    type="password",
                    placeholder=PASSWORD_LABEL,
                    autocomplete="new-password",
                    label_visibility="collapsed",
                )
                st.form_submit_button(
                    APPLY_LABEL, icon=":material/login:", help=APPLY_HELP, on_click=_on_submit
                )
        refusal = write_guard.take_refusal(SUBMIT_GUARD)
        if refusal is not None:
            st.error(refusal, icon=":material/block:")
        render_flash(FLASH_KEY)
