# Purpose: 공지 저장(프로세스 메모리)의 갈음 · 거둠 · 끝남 · 검사 · 끝 시각 · 알림 꼴을 시험한다.

"""`capa_simulation/notice_board.py` — 2026-11-17 공지 보드 답(q-use · q-until · decided). 값은 모두
합성이다. 저장은 프로세스 전역이라 시험마다 앞뒤로 비운다(`conftest._without_notice`)."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import pytest
from child_env import narrow_child_env

from capa_simulation import alerts, notice_board
from capa_simulation.korea_time import KST

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 17, 17, 33, 20, tzinfo=KST)


def test_a_sent_notice_stands_until_its_end_and_then_is_gone_on_read() -> None:
    """끝 시각은 읽을 때 본다 — 배경 스레드 없이 끝 시각이 지난 첫 읽기가 걷고 판을 올린다."""
    until = NOW + timedelta(minutes=47)
    sent = notice_board.send("  오늘 18:20 서버 점검\n저장해 두세요  ", until, now=NOW)

    assert sent.text == "오늘 18:20 서버 점검\n저장해 두세요"
    assert sent.sender_label == "관리자"
    assert len(sent.id) == 8
    assert notice_board.current(NOW) == sent
    assert notice_board.revision(NOW) == 1
    assert notice_board.current(until - timedelta(seconds=1)) == sent
    assert notice_board.current(until) is None
    assert notice_board.revision(until) == 2, "끝남도 판을 올린다"
    assert notice_board.revision(until + timedelta(hours=1)) == 2, "한 번만"


def test_a_new_notice_replaces_the_standing_one() -> None:
    first = notice_board.send("첫 공지", NOW + timedelta(hours=1), now=NOW)
    second = notice_board.send("둘째 공지", NOW + timedelta(hours=2), now=NOW)

    assert first.id != second.id
    assert notice_board.current(NOW) == second
    assert notice_board.revision(NOW) == 2


def test_the_same_notice_sent_twice_is_one() -> None:
    """같은 글 · 같은 끝 시각을 다시 보내면(두 번 누름) 서 있는 공지를 돌려주고 판을 올리지 않는다 —
    팝업을 연 순간의 대조 값이 옛 것이어도 바뀜으로 보지 않는다."""
    until = NOW + timedelta(hours=1)
    first = notice_board.send("같은 공지", until, now=NOW, expected="")
    again = notice_board.send("같은 공지", until, now=NOW, expected="")

    assert again == first
    assert notice_board.revision(NOW) == 1


def test_a_send_with_a_stale_view_is_refused() -> None:
    """팝업을 연 사이 남이 보냄 · 거둠 — 지금 서 있는 공지가 연 순간과 다르면 보내지 않는다."""
    until = NOW + timedelta(hours=1)
    other = notice_board.send("남이 보낸 공지", until, now=NOW)

    with pytest.raises(notice_board.NoticeChanged) as replaced:
        notice_board.send("내 공지", until, now=NOW, expected="")
    assert replaced.value.ended is False, "다른 공지가 섰다(갈음)"
    assert notice_board.current(NOW) == other

    notice_board.withdraw(other.id, now=NOW)
    with pytest.raises(notice_board.NoticeChanged) as withdrawn:
        notice_board.send("내 공지", until, now=NOW, expected=other.id)
    assert withdrawn.value.ended is True, "서 있던 공지가 없어졌다(거둠)"
    assert notice_board.current(NOW) is None

    mine = notice_board.send("내 공지", until, now=NOW, expected="")
    assert notice_board.current(NOW) == mine
    assert notice_board.send("갈음", until, now=NOW, expected=mine.id).text == "갈음"


def test_a_notice_that_ended_while_the_popup_was_open_is_told_as_ended() -> None:
    """팝업을 연 사이 서 있던 공지가 끝 시각으로 걷힘 — 남이 바꾼 것이 아니라 없어진 것이다
    (`ended` 참). 보내지 않는 판정은 그대로다(6-33 「바뀜 대조」)."""
    short = notice_board.send("곧 끝나는 공지", NOW + timedelta(minutes=5), now=NOW)
    later = NOW + timedelta(minutes=6)

    with pytest.raises(notice_board.NoticeChanged) as ended:
        notice_board.send("새 공지", later + timedelta(hours=1), now=later, expected=short.id)

    assert ended.value.ended is True
    assert notice_board.current(later) is None


def test_withdraw_only_takes_the_notice_it_names() -> None:
    sent = notice_board.send("거둘 공지", NOW + timedelta(hours=1), now=NOW)

    assert not notice_board.withdraw("someother", now=NOW)
    assert notice_board.current(NOW) == sent
    assert notice_board.withdraw(sent.id, now=NOW)
    assert notice_board.current(NOW) is None
    assert notice_board.revision(NOW) == 2
    assert not notice_board.withdraw(sent.id, now=NOW), "이미 걷은 공지"
    assert notice_board.revision(NOW) == 2


@pytest.mark.parametrize(
    ("text", "until", "message"),
    [
        ("   \n ", NOW + timedelta(hours=1), notice_board.EMPTY_MESSAGE),
        ("가" * 301, NOW + timedelta(hours=1), notice_board.TOO_LONG_MESSAGE),
        ("공지", NOW, notice_board.PAST_MESSAGE),
        ("공지", NOW - timedelta(minutes=1), notice_board.PAST_MESSAGE),
        ("공지", NOW + timedelta(hours=24, seconds=1), notice_board.TOO_FAR_MESSAGE),
    ],
)
def test_the_check_refuses_empty_long_past_and_far_notices(
    text: str, until: datetime, message: str
) -> None:
    with pytest.raises(notice_board.NoticeInvalid, match=message) as refused:
        notice_board.send(text, until, now=NOW)
    assert refused.value.message == message
    assert isinstance(refused.value, ValueError)
    assert notice_board.current(NOW) is None
    assert notice_board.revision(NOW) == 0


def test_the_check_keeps_inner_lines_and_takes_three_hundred_characters() -> None:
    assert notice_board.check("가" * 300, NOW + timedelta(hours=24), now=NOW) == "가" * 300
    assert notice_board.check("a\r\nb\rc", NOW + timedelta(hours=1), now=NOW) == "a\nb\nc"


def test_a_time_without_a_zone_is_refused() -> None:
    with pytest.raises(ValueError):
        notice_board.current(datetime(2026, 11, 17, 17, 0))


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 11, 17, 17, 33, 20, tzinfo=KST), time(18, 40)),
        (datetime(2026, 11, 17, 17, 30, 0, tzinfo=KST), time(18, 30)),
        (datetime(2026, 11, 17, 17, 30, 1, tzinfo=KST), time(18, 40)),
        (datetime(2026, 11, 17, 23, 55, 0, tzinfo=KST), time(1, 0)),
    ],
)
def test_the_default_end_is_an_hour_later_rounded_up_to_ten_minutes(
    now: datetime, expected: time
) -> None:
    until = notice_board.default_until(now)

    assert until.time() == expected
    assert until.tzinfo is not None and until.utcoffset() == timedelta(hours=9)
    assert timedelta(hours=1) <= until - now < timedelta(hours=1, minutes=10)


def test_the_default_end_reads_the_utc_server_clock_as_korean_time() -> None:
    """서버 시각대가 UTC 여도 끝 시각은 한국 시각이다."""
    utc_now = datetime(2026, 11, 17, 8, 33, tzinfo=timezone.utc)

    assert notice_board.default_until(utc_now) == datetime(2026, 11, 17, 18, 40, tzinfo=KST)


def test_a_chosen_time_already_past_is_tomorrow() -> None:
    today = notice_board.until_from_time(time(18, 20), NOW)
    tomorrow = notice_board.until_from_time(time(9, 0), NOW)
    this_minute = notice_board.until_from_time(time(17, 33), NOW)

    assert today == datetime(2026, 11, 17, 18, 20, tzinfo=KST)
    assert tomorrow == datetime(2026, 11, 18, 9, 0, tzinfo=KST)
    assert this_minute == datetime(2026, 11, 18, 17, 33, tzinfo=KST)
    assert this_minute - NOW < notice_board.LONGEST
    assert not notice_board.is_next_day(today, NOW)
    assert notice_board.is_next_day(tomorrow, NOW)


def test_the_payload_carries_the_mark_revision_view_and_an_active_pageless_note() -> None:
    """알림 칸 data · 물음 응답의 꼴 — 시각은 KST 글, 상태 표지는 화면 없는 `GL-09` 이고 지문 재료는
    공지 id 다. 짧은 글은 `공지 · <글>`(60자 말줄임), 전문은 글 + 보낸 이 · 시각 줄."""
    until = datetime(2026, 11, 17, 18, 20, tzinfo=KST)
    sent = notice_board.send("오늘 18:20 서버 점검\n" + "가" * 80, until, now=NOW)

    payload = notice_board.payload(NOW)

    assert payload["mark"] == notice_board.PROCESS_MARK
    assert payload["rev"] == 1
    assert payload["notice"] == {
        "id": sent.id,
        "text": sent.text,
        "sender": "관리자",
        "sent": "17:33",
        "until": "18:20",
        "until_ms": int(until.timestamp() * 1000),
    }
    note = payload["note"]
    assert (note["code"], note["kind"], note["level"], note["active"]) == (
        "GL-09",
        "state",
        "info",
        True,
    )
    assert "page" not in note and "href" not in note, "어느 화면의 일도 아니다"
    assert note["fp"] == alerts.fingerprint("GL-09", "notice", sent.id)
    assert note["short"].startswith("공지 · 오늘 18:20 서버 점검 ")
    assert len(note["short"]) == alerts.SHORT_LIMIT and note["short"].endswith("…")
    assert note["full"] == f"{sent.text}\n관리자 · 17:33 보냄 · 18:20 까지"


def test_an_end_on_the_next_day_carries_its_date_everywhere_it_is_read() -> None:
    """끝 시각이 보낸 날(KST)의 다음 날이면 끝 글에 날짜를 싣는다 — 받는 사람이 다음 날 읽으면
    「22:00 까지」 가 이미 끝난 공지처럼 읽힌다. 판 끝 줄(`view` 의 until) · 알림 전문 · Admin 카드
    값 줄이 같은 글(`until_text`)이고 「내일」 이 아니라 날짜다. 같은 날이면 시각만이다."""
    late = datetime(2026, 11, 17, 23, 0, tzinfo=KST)
    until = datetime(2026, 11, 18, 22, 0, tzinfo=KST)
    sent = notice_board.send("밤샘 점검", until, now=late)

    assert notice_board.until_text(sent) == "11-18 22:00"
    assert notice_board.stamp_line(sent) == "관리자 · 23:00 보냄 · 11-18 22:00 까지"
    payload = notice_board.payload(late)
    assert payload["notice"] is not None and payload["notice"]["until"] == "11-18 22:00"
    assert payload["note"]["full"] == "밤샘 점검\n관리자 · 23:00 보냄 · 11-18 22:00 까지"

    notice_board.reset()
    utc_sent = notice_board.send(
        "UTC 서버 시계",
        datetime(2026, 11, 17, 15, 30, tzinfo=timezone.utc),
        now=datetime(2026, 11, 17, 14, 50, tzinfo=timezone.utc),
    )
    assert notice_board.until_text(utc_sent) == "11-18 00:30", "날은 KST 로 가른다"
    notice_board.reset()
    same_day = notice_board.send("오늘 안", datetime(2026, 11, 17, 23, 50, tzinfo=KST), now=late)
    assert notice_board.until_text(same_day) == "23:50"


def test_the_payload_note_is_the_registry_state_note_without_a_page() -> None:
    """물음 경로가 실행 문맥 없이 지은 표지와 서버 회차의 표지가 같다 — 등록부 `state_note`
    그대로."""
    sent = notice_board.send("같은 표지", NOW + timedelta(hours=1), now=NOW)

    note = notice_board.payload(NOW)["note"]

    assert note == alerts.state_note(
        "GL-09",
        scope="notice",
        content=sent.id,
        active=True,
        text=notice_board.short_line(sent),
        full=notice_board.full_line(sent),
        pageless=True,
    )
    assert alerts.spec("GL-09").level == note["level"]


def test_the_payload_without_a_notice_still_carries_a_resolving_note() -> None:
    """공지가 없어도 상태 표지는 간다(active 거짓 — 상태 알림 규칙). 범위가 같아 거둠 · 끝남 ·
    재시작 뒤 그 줄을 「해소」 로 닫는다."""
    sent = notice_board.send("곧 거둘 공지", NOW + timedelta(hours=1), now=NOW)
    standing = notice_board.payload(NOW)
    notice_board.withdraw(sent.id, now=NOW)

    gone = notice_board.payload(NOW)

    assert gone["notice"] is None
    assert gone["rev"] == 2
    assert gone["note"]["active"] is False and gone["note"]["fp"] == ""
    assert gone["note"]["scope"] == standing["note"]["scope"]
    assert notice_board.payload(NOW) == gone, "바뀐 것이 없으면 회차마다 같은 값"


def test_the_board_does_not_bring_streamlit() -> None:
    """문지기 쪽이 이 모듈을 들여도 Streamlit 이 딸려 오지 않는다 — 등록부는 `payload` 가 부를
    때만."""
    code = (
        "import sys\n"
        "import capa_simulation.notice_board\n"
        "raise SystemExit(1 if 'streamlit' in sys.modules else 0)\n"
    )
    found = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=narrow_child_env({"PYTHONPATH": str(PROJECT_ROOT / "src"), "PATH": ""}),
    )

    assert found.returncode == 0, found.stderr


def test_a_state_note_without_a_page_reads_no_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """화면 없는 상태 표지는 세션을 읽지 않는다 — 실행 문맥 없는 물음 처리기가 부를 자리다."""

    def no_session() -> tuple[str, str]:
        raise AssertionError("세션을 읽었다")

    monkeypatch.setattr(alerts, "current_page", no_session)
    note = alerts.state_note("GL-09", scope="notice", content=None, active=False, pageless=True)
    notice_board.send("세션 없이", NOW + timedelta(hours=1), now=NOW)
    assert notice_board.payload(NOW)["note"]["active"] is True

    assert "page" not in note and "href" not in note
    assert note["kind"] == "state" and note["active"] is False
