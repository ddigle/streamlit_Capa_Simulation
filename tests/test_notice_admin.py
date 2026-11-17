# Purpose: Admin Area 「공지」 탭 — 확인 팝업 보내기 · 거두기 · 글 검사 · 다시 판정 · 감사 줄.

"""`components/notice_admin.py`(2026-11-17 공지 보드 답 decided 1 ~ 6). 탭 몸 하나만 그리는
스크립트로 돌린다 — 팝업 안의 누름처럼 페이지 앞머리 잠금을 거치지 않는다. 운영 서버 판정은
`tests/test_admin_area_lock.py` 와 같은 꼴(합성 `demo.*` 신원)이다."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from datetime import time as clock_time
from pathlib import Path

import pytest
from alert_marks import flashed
from sso_support import use_config
from streamlit.testing.v1 import AppTest

from capa_simulation import notice_board
from capa_simulation.audit import recorder
from capa_simulation.auth import names, runtime
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    AccessSource,
    ListDocument,
    ListEntry,
    compose_access,
)
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import audit_actor, notice_admin, sso_identity
from capa_simulation.korea_time import KST

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAB_SCRIPT = """
from capa_simulation.components.notice_admin import render_notice_admin

render_notice_admin()
"""
ADMIN = "demo.admin"
LIST_ADMIN = "demo.listadmin"
USER = "demo.user"


def _run() -> AppTest:
    return AppTest.from_string(TAB_SCRIPT).run(timeout=60)


def _ok(app: AppTest) -> AppTest:
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def _open_confirm(app: AppTest, text: str) -> AppTest:
    app.text_area(key=notice_admin.TEXT_KEY).set_value(text)
    return _ok(app.button(key=notice_admin.SEND_KEY).click().run(timeout=60))


def _confirm_open(app: AppTest) -> bool:
    return any(button.key == notice_admin.CONFIRM_KEY for button in app.button)


def _as(monkeypatch: pytest.MonkeyPatch, loginid: str) -> None:
    cfg = runtime.config()
    token, _ = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: {cfg.session_cookie: token})


def _list(*entries: ListEntry, revision: int) -> None:
    cfg = runtime.config()
    document = ListDocument(revision=revision, entries=entries)
    runtime.publish_access_source(
        AccessSource(access=compose_access(cfg.access, document), document=document)
    )


def _operational_list_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """운영 서버 — `LIST_ADMIN` 은 명단의 관리자 등급이다."""
    use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: ""})
    runtime.mark_gate_installed()
    _list(ListEntry(LIST_ADMIN, grade=GRADE_ADMIN), ListEntry(USER), revision=1)
    _as(monkeypatch, LIST_ADMIN)
    assert not sso_identity.admin_area_locked()


class _Clock:
    """`notice_board.now_kst` 자리 — 시험이 한국 시각을 손으로 옮긴다(탭 · 콜백 · 저장이 같은
    시계)."""

    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


def _clock(monkeypatch: pytest.MonkeyPatch, hour: int, minute: int = 0) -> _Clock:
    clock = _Clock(datetime(2026, 11, 17, hour, minute, tzinfo=KST))
    monkeypatch.setattr(notice_board, "now_kst", clock)
    return clock


def _at(clock: _Clock, hour: int, minute: int = 0) -> None:
    clock.moment = clock.moment.replace(hour=hour, minute=minute)


def _operational_recording_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """운영 서버 · 기록기 켜짐 — `ADMIN` 이 관리자다."""
    use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER})
    runtime.mark_gate_installed()
    recorder.start(env="cdep", version="test", inst="notenoteaaaa")
    audit_actor.install()
    _as(monkeypatch, ADMIN)


def _notice_lines() -> list[dict[str, object]]:
    return [line for line in recorder.take_pending() if str(line["ev"]).startswith("admin_notice_")]


def _demote() -> None:
    """다른 관리자가 `LIST_ADMIN` 을 일반으로 내린 뒤의 명단."""
    _list(ListEntry(LIST_ADMIN), ListEntry(USER), revision=2)
    assert sso_identity.admin_area_locked()


def test_the_tab_sends_through_the_confirm_popup_and_shows_the_standing_card() -> None:
    """개발 실행(운영 아님) — 글을 넣고 「보내기」 → 확인 팝업 「공지 보내기」 의 값 한 줄
    `끝 18:20` → 팝업 「보내기」 가 쥔 값 그대로 보낸다. 결과는 알림창(성공은 알림창으로만)이고
    서 있는 공지 카드가 서며 글 상자 · 끝 시각은 비워져 새 기본값으로 선다."""
    runtime.reset()
    app = _ok(_run())
    assert not app.text, "서 있는 공지가 없으면 카드가 없다"
    assert not any(button.key == notice_admin.WITHDRAW_KEY for button in app.button)
    area = app.text_area(key=notice_admin.TEXT_KEY)
    assert area.label == notice_admin.TEXT_LABEL
    assert area.proto.label_visibility.value == area.proto.label_visibility.COLLAPSED
    assert area.placeholder == "공지 글"
    assert area.max_chars == 300
    chosen = app.time_input(key=notice_admin.UNTIL_KEY).value
    assert chosen is not None and chosen.minute % 10 == 0 and chosen.second == 0

    app = _open_confirm(app, "  오늘 18시 서버 점검 — 저장해 두세요\n고맙습니다  ")
    assert _confirm_open(app)
    pending = app.session_state[notice_admin.PENDING_KEY]
    assert pending["text"] == "오늘 18시 서버 점검 — 저장해 두세요\n고맙습니다"
    assert pending["expected"] == ""
    lines = [caption.value for caption in app.caption]
    until_text = notice_board.clock_text(notice_board.until_from_time(chosen))
    assert any(line.startswith("끝 ") and line.endswith(until_text) for line in lines), lines
    assert not any(notice_admin.REPLACES_SUFFIX in line for line in lines)
    assert notice_board.current() is None, "팝업을 연 것만으로는 보내지 않는다"
    send = app.button(key=notice_admin.CONFIRM_KEY)
    assert (send.label, send.proto.type, send.proto.icon) == (
        "보내기",
        "primary",
        ":material/campaign:",
    )

    app = _ok(app.button(key=notice_admin.CONFIRM_KEY).click().run(timeout=60))

    standing = notice_board.current()
    assert standing is not None and standing.text == pending["text"]
    assert not _confirm_open(app)
    assert [str(note.value) for note in flashed(app, "success")] == [
        f"공지 보냄 · {notice_board.until_text(standing)} 까지"
    ]
    assert [text.value for text in app.text] == [standing.text]
    assert notice_board.stamp_line(standing) in [caption.value for caption in app.caption]
    assert app.button(key=notice_admin.WITHDRAW_KEY).label == "거두기"
    assert app.text_area(key=notice_admin.TEXT_KEY).value == ""


def test_after_a_send_the_end_goes_back_to_a_fresh_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """보낸 뒤 첫 앱 전체 회차는 글 상자를 비우고 끝 시각을 **그때의** 새 기본값으로 둔다 — 사람이
    고른 16:30 이 남지 않고, 탭을 연 때의 기본값도 아니다."""
    runtime.reset()
    clock = _clock(monkeypatch, 14)
    app = _ok(_run())
    app = _ok(app.time_input(key=notice_admin.UNTIL_KEY).set_value(clock_time(16, 30)).run())
    app = _open_confirm(app, "16시 반까지 공지")
    _at(clock, 14, 5)

    app = _ok(app.button(key=notice_admin.CONFIRM_KEY).click().run(timeout=60))

    standing = notice_board.current()
    assert standing is not None and standing.until == clock.moment.replace(hour=16, minute=30)
    assert app.text_area(key=notice_admin.TEXT_KEY).value == ""
    fresh = notice_board.default_until(clock.moment)
    assert fresh.time() == clock_time(15, 10)
    assert app.time_input(key=notice_admin.UNTIL_KEY).value == fresh.time()
    assert app.session_state[notice_admin.SEEDED_KEY] == fresh.isoformat()


def test_an_untouched_default_end_that_has_passed_moves_to_a_new_default_on_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """10:00 에 Admin Area 를 열면 끝 시각 칸에 11:00 이 심긴다. 다른 화면에 가지 않고 14:00 에 글만
    써서 「보내기」 를 누르면 — 그 사이 회차가 없었어도 — 콜백이 지난 기본값을 지금 기준 새 기본값
    (15:00)으로 바꾼다. 그대로 두면 「내일 11:00」(21시간짜리 공지)이 된다."""
    runtime.reset()
    clock = _clock(monkeypatch, 10)
    app = _ok(_run())
    assert app.time_input(key=notice_admin.UNTIL_KEY).value == clock_time(11, 0)
    _at(clock, 14)

    app = _open_confirm(app, "점검 공지")

    pending = app.session_state[notice_admin.PENDING_KEY]
    assert datetime.fromisoformat(pending["until"]) == clock.moment.replace(hour=15)
    assert "끝 15:00" in [caption.value for caption in app.caption]
    assert app.time_input(key=notice_admin.UNTIL_KEY).value == clock_time(15, 0)
    _ok(app.button(key=notice_admin.CONFIRM_KEY).click().run(timeout=60))
    standing = notice_board.current()
    assert standing is not None and standing.until - clock.moment == timedelta(hours=1)


def test_a_passed_default_is_renewed_before_the_tab_draws_but_a_chosen_end_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """회차가 도는 길도 같다 — 손대지 않은 기본값이 지났으면 위젯이 서기 전에 새 기본값이다. 사람이
    고른 시각(심은 값과 다름)은 지났어도 그대로라 「내일 그 시각」 이고 확인 팝업 · 보냄 알림창이
    다음 날을 말한다(보냄 알림창 · 판은 날짜 — 다음 날 읽혀도 맞게)."""
    runtime.reset()
    clock = _clock(monkeypatch, 10)
    app = _ok(_run())
    _at(clock, 14)
    app = _ok(app.run())
    assert app.time_input(key=notice_admin.UNTIL_KEY).value == clock_time(15, 0)

    app = _ok(app.time_input(key=notice_admin.UNTIL_KEY).set_value(clock_time(12, 30)).run())
    _at(clock, 14, 20)
    app = _ok(app.run())
    assert app.time_input(key=notice_admin.UNTIL_KEY).value == clock_time(12, 30)
    app = _open_confirm(app, "내일 낮까지")

    assert "끝 내일 12:30" in [caption.value for caption in app.caption]
    app = _ok(app.button(key=notice_admin.CONFIRM_KEY).click().run(timeout=60))
    assert [str(note.value) for note in flashed(app, "success")] == ["공지 보냄 · 11-18 12:30 까지"]


def test_the_confirm_line_names_the_next_day_and_a_standing_notice() -> None:
    now = notice_board.now_kst().replace(hour=17, minute=40)
    tomorrow = notice_board.until_from_time(now.time().replace(hour=9, minute=0), now)
    today = notice_board.until_from_time(now.time().replace(hour=18, minute=20), now)

    assert notice_admin.confirm_line(today, replaces=False, now=now) == "끝 18:20"
    assert (
        notice_admin.confirm_line(tomorrow, replaces=True, now=now)
        == "끝 내일 09:00 · 서 있는 공지 바뀜"
    )


def test_a_standing_notice_is_named_in_the_confirm_and_replaced_on_send() -> None:
    runtime.reset()
    other = notice_board.send("앞 공지", notice_board.now_kst() + timedelta(hours=2))
    app = _open_confirm(_ok(_run()), "새 공지")

    assert app.session_state[notice_admin.PENDING_KEY]["expected"] == other.id
    assert any(caption.value.endswith(notice_admin.REPLACES_SUFFIX) for caption in app.caption)

    _ok(app.button(key=notice_admin.CONFIRM_KEY).click().run(timeout=60))
    standing = notice_board.current()
    assert standing is not None and standing.text == "새 공지" and standing.id != other.id


def test_an_empty_text_is_refused_beside_the_button_without_a_popup() -> None:
    runtime.reset()
    app = _open_confirm(_ok(_run()), "   ")

    assert not _confirm_open(app)
    assert [str(error.value) for error in app.error] == [notice_board.EMPTY_MESSAGE]
    assert notice_board.current() is None


def test_cancel_closes_the_popup_without_sending() -> None:
    runtime.reset()
    app = _open_confirm(_ok(_run()), "보내지 않을 공지")

    app = _ok(app.button(key=notice_admin.CANCEL_KEY).click().run(timeout=60))

    assert not _confirm_open(app)
    assert notice_board.current() is None
    assert notice_admin.PENDING_KEY not in app.session_state
    assert app.text_area(key=notice_admin.TEXT_KEY).value == "보내지 않을 공지"


def test_a_notice_changed_while_the_popup_was_open_is_not_overwritten() -> None:
    """팝업을 연 사이 다른 관리자가 보냈으면 그대로 보내지 않는다 — 팝업을 닫아 바뀐 카드를 다시
    보이고(글 상자는 그대로) 알림창 · Alarm 에 경고 한 줄."""
    runtime.reset()
    app = _open_confirm(_ok(_run()), "내 공지")
    other = notice_board.send("남이 보낸 공지", notice_board.now_kst() + timedelta(hours=1))

    app = _ok(app.button(key=notice_admin.CONFIRM_KEY).click().run(timeout=60))

    assert notice_board.current() == other
    assert not _confirm_open(app)
    assert [str(note.value) for note in flashed(app, "warning")] == [notice_admin.CHANGED_MESSAGE]
    assert [text.value for text in app.text] == ["남이 보낸 공지"]
    assert app.text_area(key=notice_admin.TEXT_KEY).value == "내 공지"


def test_a_notice_that_ended_while_the_popup_was_open_says_so_without_blaming_anyone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """팝업을 연 사이 서 있던 공지가 끝 시각으로 걷혔으면 보내지 않는 판정은 같지만(6-33 「바뀜
    대조」) 알림 글 · 감사 결과는 「끝남 · 거둠」 이다 — 관리자 혼자인데 「다른 관리자가 바꿈」 으로
    읽히지 않게. 어느 글도 사람을 지목하지 않는다."""
    _operational_recording_admin(monkeypatch)
    clock = _clock(monkeypatch, 17)
    first = notice_board.send("17:05 에 끝나는 공지", clock.moment.replace(minute=5))
    app = _open_confirm(_ok(_run()), "새 공지")
    assert app.session_state[notice_admin.PENDING_KEY]["expected"] == first.id
    _at(clock, 17, 6)

    app = _ok(app.button(key=notice_admin.CONFIRM_KEY).click().run(timeout=60))

    assert notice_board.current() is None
    assert not _confirm_open(app)
    assert [str(note.value) for note in flashed(app, "warning")] == [notice_admin.ENDED_MESSAGE]
    assert app.text_area(key=notice_admin.TEXT_KEY).value == "새 공지"
    assert [(line["out"], line["det"]) for line in _notice_lines()] == [
        ("fail", {"result": "ended"})
    ]
    for message in (notice_admin.ENDED_MESSAGE, notice_admin.CHANGED_MESSAGE):
        assert "관리자" not in message


def test_withdraw_takes_the_standing_notice_and_tells_it() -> None:
    runtime.reset()
    notice_board.send("거둘 공지", notice_board.now_kst() + timedelta(hours=1))
    app = _ok(_run())

    app = _ok(app.button(key=notice_admin.WITHDRAW_KEY).click().run(timeout=60))

    assert notice_board.current() is None
    assert [str(note.value) for note in flashed(app, "success")] == ["공지 거둠"]
    assert not app.text
    assert not any(button.key == notice_admin.WITHDRAW_KEY for button in app.button)


@pytest.mark.parametrize("demoted", [False, True], ids=["still_admin", "demoted"])
def test_the_send_is_judged_again_at_the_moment_on_the_operational_server(
    monkeypatch: pytest.MonkeyPatch, demoted: bool
) -> None:
    """팝업을 연 뒤 관리자 등급을 잃은 사람의 「보내기」 는 보내지 않는다 — 팝업 안의 누름은 페이지
    앞머리 잠금을 지나지 않으므로 그 순간 다시 판정한다(붙여넣기 팝업과 같은 꼴). 아직 관리자면
    그대로 보낸다(빈 시험이 아님)."""
    _operational_list_admin(monkeypatch)
    app = _open_confirm(_ok(_run()), "운영 공지")
    assert _confirm_open(app)
    if demoted:
        _demote()

    app = _ok(app.button(key=notice_admin.CONFIRM_KEY).click().run(timeout=60))

    errors = [str(note.value) for note in flashed(app, "error")]
    if demoted:
        assert errors == [notice_admin.NOT_ADMIN_MESSAGE]
        assert notice_board.current() is None
    else:
        assert errors == []
        standing = notice_board.current()
        assert standing is not None and standing.text == "운영 공지"


@pytest.mark.parametrize("demoted", [False, True], ids=["still_admin", "demoted"])
def test_the_withdraw_is_judged_again_at_the_moment(
    monkeypatch: pytest.MonkeyPatch, demoted: bool
) -> None:
    _operational_list_admin(monkeypatch)
    sent = notice_board.send("운영 공지", notice_board.now_kst() + timedelta(hours=1))
    app = _ok(_run())
    if demoted:
        _demote()

    app = _ok(app.button(key=notice_admin.WITHDRAW_KEY).click().run(timeout=60))

    if demoted:
        assert notice_board.current() == sent
        assert [str(note.value) for note in flashed(app, "error")] == [
            notice_admin.NOT_ADMIN_MESSAGE
        ]
    else:
        assert notice_board.current() is None


def test_the_audit_lines_carry_the_notice_id_and_end_but_never_the_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """운영 서버의 「공지 보냄」 · 「공지 거둠」 — 대상은 공지 id, 상세는 결과 · 끝 시각뿐이다. 글은
    어느 칸에도 없다(감사 불변조건 — 값 원문 없음). 막힌 누름도 거부 한 줄을 남긴다."""
    use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER})
    runtime.mark_gate_installed()
    recorder.start(env="cdep", version="test", inst="notenoteaaaa")
    audit_actor.install()
    _as(monkeypatch, ADMIN)
    secret_text = "합성 공지 본문 — 감사 줄에 실리면 안 되는 글"

    app = _open_confirm(_ok(_run()), secret_text)
    app = _ok(app.button(key=notice_admin.CONFIRM_KEY).click().run(timeout=60))
    standing = notice_board.current()
    assert standing is not None
    app = _ok(app.button(key=notice_admin.WITHDRAW_KEY).click().run(timeout=60))
    _as(monkeypatch, USER)
    notice_board.send("다른 공지", notice_board.now_kst() + timedelta(hours=1))
    app = _ok(app.run(timeout=60))
    _ok(app.button(key=notice_admin.WITHDRAW_KEY).click().run(timeout=60))

    lines = [line for line in recorder.take_pending() if line["ev"].startswith("admin_notice_")]
    assert [(line["ev"], line["out"], line["det"]["result"]) for line in lines] == [
        ("admin_notice_send", "success", "sent"),
        ("admin_notice_withdraw", "success", "withdrawn"),
        ("admin_notice_withdraw", "denied", "not_admin"),
    ]
    sent, withdrawn, denied = lines
    assert sent["tgt"] == {"type": "notice", "id": standing.id}
    assert sent["det"]["until"] == standing.until.isoformat(timespec="minutes")
    assert sent["actor"] == ADMIN and withdrawn["actor"] == ADMIN
    assert withdrawn["tgt"] == {"type": "notice", "id": standing.id}
    assert denied["actor"] == USER
    payload = json.dumps(lines, ensure_ascii=False)
    assert secret_text not in payload and "합성 공지" not in payload


def test_the_development_server_keeps_no_audit_line() -> None:
    """개발 PC · WebIDE 는 기록기가 꺼져 있다 — 보내도 아무 줄도 없다."""
    runtime.reset()
    app = _open_confirm(_ok(_run()), "개발 공지")
    _ok(app.button(key=notice_admin.CONFIRM_KEY).click().run(timeout=60))

    assert notice_board.current() is not None
    assert not recorder.enabled()
    assert recorder.take_pending() == []
