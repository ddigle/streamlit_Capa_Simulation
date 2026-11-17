# Purpose: 관리자가 보낸 공지 하나를 프로세스 메모리에 두고 보내기 · 거두기 · 끝남과 알림 꼴을 낸다.

"""공지(2026-11-17 공지 보드 답 — q-use · q-until · decided).

**자리는 프로세스 메모리 하나다.** 서 있는 공지는 하나뿐이고(새로 보내면 갈음) 서버를 다시 시작하면
걷힌다 — 「지금 알릴 것만, 길어도 하루」(q-use). 같은 프로세스의 모든 세션 · 문지기 쪽 물음 처리기가
한 벌을 본다. 서버가 한 대(replica 1)라는 전제는 접속 명단 · 로그인 상태와 같다(`auth/runtime.py`) —
둘 이상이면 서버마다 갈린다(사내 확인 거리 — `docs/TODO.md` 2장).

- 잠금 하나(`threading.Lock`)로 보내기 · 거두기 · 읽기를 줄 세운다. `st.cache_resource` 를 쓰지
  않고(캐시 경계 규칙) 배경 스레드도 없다 — **끝 시각은 읽을 때 본다**(`current` · `revision` ·
  `payload` · `send` 가 지난 공지를 걷고 판을 올린다).
- 판(`revision`)은 보냄 · 거둠 · 끝남마다 하나 오른다. 물음 경로가 바뀜을 가르는 값이고, 프로세스
  표지 (`PROCESS_MARK`)와 짝이라 재시작 뒤 0 부터 다시 세어도 브라우저가 옛 판과 섞지 않는다.
- **이 모듈은 Streamlit 을 읽지 않는다** — 문지기 쪽 가벼운 import 로 남는다. 알림 칸 꼴의 상태
  표지는 알림 등록부(`alerts`)가 짓는데 그 모듈은 Streamlit 을 읽으므로 `payload` 가 부를 때
  들인다(앱 프로세스 에는 이미 읽혀 있다). 표지는 화면 없는 꼴(`alerts.state_note(…, pageless=True)`
  — 세션을 읽지 않음)이라 실행 문맥 밖에서도 같은 값이다.
- 글은 꾸밈 없는 평문 300자, 끝 시각은 한국 시각(KST) 분 단위 · 길어도 24시간이다. 보낸 이는 실명
  대신 「관리자」 다(누가 보냈는지는 감사 기록 — `components/notice_admin.py`).
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Final, TypedDict

from capa_simulation.korea_time import KST, kst_clock

if TYPE_CHECKING:
    from capa_simulation.alerts import AlertNote

# 알림 등록부의 공지 코드 · 상태 범위. 범위는 늘 같은 값이고 내용 지문 재료는 공지 id 다 — 새 공지는
# 「내용 바뀜」, 거둠 · 끝남 · 재시작 뒤는 「해소」 로 저절로 닫힌다.
NOTICE_CODE: Final = "GL-09"
NOTICE_SCOPE: Final = "notice"
TEXT_LIMIT: Final = 300
LONGEST: Final = timedelta(hours=24)
# 끝 시각 기본값 — 지금 + 1시간을 10분 단위로 올림.
DEFAULT_LEAD: Final = timedelta(hours=1)
ROUND_MINUTES: Final = 10
SENDER_LABEL: Final = "관리자"
CLOCK_LAYOUT: Final = "%H:%M"
# 끝 시각이 보낸 날의 다음 날이면 날짜도 싣는다 — 받는 사람은 다음 날 읽기도 해 「내일」 이 틀린다.
DATED_CLOCK_LAYOUT: Final = "%m-%d %H:%M"

EMPTY_MESSAGE: Final = "공지 글을 넣으세요"
TOO_LONG_MESSAGE: Final = f"공지 글은 {TEXT_LIMIT}자까지입니다"
PAST_MESSAGE: Final = "끝 시각이 지났습니다"
TOO_FAR_MESSAGE: Final = "끝 시각은 24시간 안이어야 합니다"

# 이 프로세스의 표지 — 재시작하면 바뀐다. 브라우저는 표지가 다르면 판과 상관없이 새 값을 받는다.
PROCESS_MARK: Final = secrets.token_hex(4)


@dataclass(frozen=True)
class Notice:
    """서 있는 공지 하나 — id(짧은 무작위) · 글 · 보낸 시각 · 끝 시각(둘 다 KST) · 보낸 이 표지."""

    id: str
    text: str
    sent_at: datetime
    until: datetime
    sender_label: str = SENDER_LABEL


class NoticeChanged(Exception):
    """확인 팝업을 연 사이 서 있는 공지가 바뀌었다 — 보내지 않는다. `ended` 는 그때 서 있던 공지가
    없어졌는가(끝 시각으로 걷힘 · 거둠 — 같은 관리자의 다른 탭일 수도 있다)이고, 거짓이면 다른
    공지가 섰다(갈음)."""

    def __init__(self, *, ended: bool) -> None:
        super().__init__("ended" if ended else "replaced")
        self.ended = ended


class NoticeInvalid(ValueError):
    """보낼 글 · 끝 시각이 검사에 걸렸다. `message` 는 미리 정한 한국어 한 줄(`*_MESSAGE`)뿐이라
    사람이 쓴 글을 담지 않는다 — 화면이 그대로 싣는다."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NoticeView(TypedDict):
    """알림 칸 data · 물음 응답의 공지 칸 — 시각은 파이썬이 지은 KST 글(끝은 보낸 날과 다르면
    날짜까지 — `until_text`)이고 끝은 epoch ms 도 싣는다(브라우저가 끝 시각 뒤에 칩을 걷는다 — 제
    시각대로 글을 짓지 않는다)."""

    id: str
    text: str
    sender: str
    sent: str
    until: str
    until_ms: int


class NoticePayload(TypedDict):
    """물음 경로 · 알림 칸이 함께 쓰는 꼴 — 프로세스 표지 · 판 · 공지(없으면 None) · 상태 표지."""

    mark: str
    rev: int
    notice: NoticeView | None
    note: AlertNote


@dataclass
class _Board:
    notice: Notice | None = None
    revision: int = 0


_LOCK = threading.Lock()
_BOARD = _Board()


def now_kst() -> datetime:
    """지금 한국 시각(시각대 붙음)."""
    return datetime.now(KST)


def _moment(now: datetime | None) -> datetime:
    if now is None:
        return now_kst()
    if now.utcoffset() is None:
        raise ValueError("시각대가 없는 시각")
    return now.astimezone(KST)


def _expire_locked(now: datetime) -> None:
    """끝 시각이 지난 공지를 걷고 판을 올린다(잠금 안에서)."""
    notice = _BOARD.notice
    if notice is not None and now >= notice.until:
        _BOARD.notice = None
        _BOARD.revision += 1


def current(now: datetime | None = None) -> Notice | None:
    """서 있는 공지 — 끝 시각이 지났으면 None(그리고 걷는다)."""
    moment = _moment(now)
    with _LOCK:
        _expire_locked(moment)
        return _BOARD.notice


def revision(now: datetime | None = None) -> int:
    """보냄 · 거둠 · 끝남마다 오르는 판."""
    moment = _moment(now)
    with _LOCK:
        _expire_locked(moment)
        return _BOARD.revision


def clean_text(text: str) -> str:
    """보낼 글 — 줄바꿈을 `\\n` 으로 맞추고 앞뒤 빈칸을 뗀다(안의 줄바꿈 · 빈칸은 그대로)."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def check(text: str, until: datetime, *, now: datetime | None = None) -> str:
    """보낼 글 · 끝 시각을 본다 — 다듬은 글을 돌려주고, 빈 글 · 300자 넘음 · 끝 ≤ 지금 · 24시간
    넘음은 `NoticeInvalid`(`ValueError` — 글은 화면에 그대로 싣는 한국어 한 줄)."""
    moment = _moment(now)
    cleaned = clean_text(text)
    if not cleaned:
        raise NoticeInvalid(EMPTY_MESSAGE)
    if len(cleaned) > TEXT_LIMIT:
        raise NoticeInvalid(TOO_LONG_MESSAGE)
    end = _moment(until)
    if end <= moment:
        raise NoticeInvalid(PAST_MESSAGE)
    if end - moment > LONGEST:
        raise NoticeInvalid(TOO_FAR_MESSAGE)
    return cleaned


def send(
    text: str,
    until: datetime,
    *,
    now: datetime | None = None,
    expected: str | None = None,
) -> Notice:
    """공지를 보낸다 — 서 있던 공지를 갈음하고 판을 올린다. 검사는 `check` 그대로(`NoticeInvalid`).

    같은 글 · 같은 끝 시각의 공지가 이미 서 있으면 그 공지를 돌려주고 판을 올리지 않는다(두 번
    누름은 한 번). `expected` 는 확인 팝업을 열 때 본 서 있는 공지 id(없었으면 빈 글)다 — 지금 서
    있는 것과 다르면 보내지 않고 `NoticeChanged`(갈음 · 거둠 · 끝 시각으로 걷힘 — `ended` 가
    가른다). None 이면 대조하지 않는다. 대조와 갈음은 한 잠금 안이다."""
    moment = _moment(now)
    cleaned = check(text, until, now=moment)
    end = _moment(until)
    with _LOCK:
        _expire_locked(moment)
        standing = _BOARD.notice
        if standing is not None and standing.text == cleaned and standing.until == end:
            return standing
        if expected is not None and expected != ("" if standing is None else standing.id):
            raise NoticeChanged(ended=standing is None)
        notice = Notice(id=secrets.token_hex(4), text=cleaned, sent_at=moment, until=end)
        _BOARD.notice = notice
        _BOARD.revision += 1
        return notice


def withdraw(notice_id: str, *, now: datetime | None = None) -> bool:
    """서 있는 공지가 그 id 일 때만 걷는다(판이 오른다). 걷었으면 참."""
    moment = _moment(now)
    with _LOCK:
        _expire_locked(moment)
        standing = _BOARD.notice
        if standing is None or standing.id != notice_id:
            return False
        _BOARD.notice = None
        _BOARD.revision += 1
        return True


def default_until(now: datetime | None = None) -> datetime:
    """끝 시각 기본값 — 지금 + 1시간을 10분 단위로 올린 KST 시각(초 0)."""
    target = _moment(now) + DEFAULT_LEAD
    floor = target.replace(
        minute=target.minute - target.minute % ROUND_MINUTES, second=0, microsecond=0
    )
    return floor if floor == target else floor + timedelta(minutes=ROUND_MINUTES)


def until_from_time(clock: time, now: datetime | None = None) -> datetime:
    """시각만 고른 끝 — 오늘 그 시각(KST, 초 0), 지금 이하이면 내일 그 시각(길어도 24시간)."""
    moment = _moment(now)
    chosen = datetime.combine(moment.date(), time(clock.hour, clock.minute), tzinfo=KST)
    return chosen if chosen > moment else chosen + timedelta(days=1)


def is_next_day(until: datetime, now: datetime | None = None) -> bool:
    """끝 시각이 지금(KST) 다음 날인가 — 확인 팝업 값 줄이 「내일」 을 단다."""
    return _moment(until).date() > _moment(now).date()


def clock_text(moment: datetime) -> str:
    """화면 · 알림의 시각 글(KST `17:40`)."""
    return kst_clock(moment, CLOCK_LAYOUT)


def until_text(notice: Notice) -> str:
    """끝 시각 글 — 보낸 날(KST)과 같은 날이면 `18:20`, 다음 날이면 `11-18 09:00`. 받는 쪽 판 ·
    알림 전문 · Admin 카드 · 보냄 알림창이 같은 글을 쓴다(브라우저가 제 시각대로 짓지 않는다)."""
    if notice.until.astimezone(KST).date() == notice.sent_at.astimezone(KST).date():
        return clock_text(notice.until)
    return kst_clock(notice.until, DATED_CLOCK_LAYOUT)


def stamp_line(notice: Notice) -> str:
    """`관리자 · 17:40 보냄 · 18:20 까지`(끝이 다음 날이면 `11-18 09:00 까지`) — Admin 카드 값 줄과
    알림 전문 끝 줄."""
    return f"{notice.sender_label} · {clock_text(notice.sent_at)} 보냄 · {until_text(notice)} 까지"


def short_line(notice: Notice) -> str:
    """알림창 짧은 글 재료 — `공지 · <글>`(넘치면 등록부가 말줄임)."""
    return f"공지 · {notice.text}"


def full_line(notice: Notice) -> str:
    """알림 전문 — 글 + 줄바꿈 + 보낸 이 · 시각 줄."""
    return f"{notice.text}\n{stamp_line(notice)}"


def view(notice: Notice) -> NoticeView:
    """알림 칸 data · 물음 응답의 공지 칸."""
    return NoticeView(
        id=notice.id,
        text=notice.text,
        sender=notice.sender_label,
        sent=clock_text(notice.sent_at),
        until=until_text(notice),
        until_ms=int(notice.until.timestamp() * 1000),
    )


def payload(now: datetime | None = None) -> NoticePayload:
    """물음 경로 · 알림 칸이 함께 쓰는 꼴 — 표지 · 판 · 공지 · 상태 표지(공지가 서 있으면 active 참,
    없으면 거짓 — 상태 알림 규칙). 표지는 화면 없는 꼴이라 세션 · 실행 문맥을 읽지 않는다."""
    # 등록부는 Streamlit 을 읽는 모듈이라 부를 때 들인다 — 이 모듈은 가벼운 import 로 남는다.
    from capa_simulation import alerts

    moment = _moment(now)
    with _LOCK:
        _expire_locked(moment)
        notice = _BOARD.notice
        rev = _BOARD.revision
    if notice is None:
        note = alerts.state_note(
            NOTICE_CODE, scope=NOTICE_SCOPE, content=None, active=False, pageless=True
        )
        return NoticePayload(mark=PROCESS_MARK, rev=rev, notice=None, note=note)
    note = alerts.state_note(
        NOTICE_CODE,
        scope=NOTICE_SCOPE,
        content=notice.id,
        active=True,
        text=short_line(notice),
        full=full_line(notice),
        pageless=True,
    )
    return NoticePayload(mark=PROCESS_MARK, rev=rev, notice=view(notice), note=note)


def reset() -> None:
    """공지를 비우고 판을 0 으로 — 시험이 프로세스 전역 값을 사이마다 되돌린다."""
    with _LOCK:
        _BOARD.notice = None
        _BOARD.revision = 0
