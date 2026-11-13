# Purpose: BigDataQuery 로그인 토큰 자동 갱신의 교환 한 곳 · 상태 · 갱신 때 · 고리 막기를 둔다.

"""BigDataQuery 로그인 토큰 자동 갱신(2026-11-14 사용자 결정 — 갱신 토큰은 C-DEP 환경변수 표, 갱신은
「발급 6시간 뒤」 사람 손 · CI/CD · 재시작 없이).

**교환 한 곳(`exchange`).** 갱신 토큰(3개월 비밀)을 새 로그인 토큰으로 바꾸는 요청의 꼴(주소 ·
방법 · 갱신 토큰을 넣는 자리 · 응답 칸)은 아직 모른다 — 담당자 답 대기. 그래서 지금 `exchange` 는
`RefreshNotConfigured` 를 내고 곁의 `REQUEST_SHAPE_KNOWN` 은 거짓이다. 답이 오면 그 몸만 채우고
표지를 참으로 바꾼다. 이 함수 밖의 모든 것은 시험이 가짜 교환으로 돌린다.

**상태**(`status`) — `off`(꺼짐: 갱신 토큰 파일 없음 · 계정 없음 · 패키지가 먼저 읽는 환경변수
토큰) · `ready`(준비: 갱신 토큰은 있는데 요청 꼴 미정) · `on`(켜짐) · `halted`(멈춤 — 아래 고리
막기).
**준비에서는 아무것도 바꾸지 않는다** — 잠금 · 표지 · 파일 쓰기 전에 돌아서고 조회 · 시작은 갱신
토큰이 없을 때와 똑같이 돈다.

**갱신 토큰 자리.** 시작 스크립트(`scripts/container_start.py`)가 CD 환경변수
`CAPA_BDQ_REFRESH_TOKEN` 을 `/config/.credential/capa-bdq-refresh.<계정>`(0600, 폴더 0700)으로 쓰고
앱 프로세스 환경에는 넘기지 않는다. 패키지 자리 접두(`bigdataquery.token.`)를 쓰지 않는다.

**언제 갱신하나 — 조회 길 한 곳.** 새 배경 스레드를 세우지 않는다(AGENTS 9장 — 배경 스레드는 예약 ·
동기화 일꾼 둘뿐). 어댑터(`company_bigdataquery_adapter._get_data_once`)가 `getData` 바로 앞에서
`before_query` 를 부르고 — 넣은 때(`bdq_token` 넣은 때 표지)부터 `REFRESH_AFTER`(6시간)가 지났거나
만료를 읽었고 1시간 안이거나 토큰이 없으면 먼저 갱신한다 — 조회가 토큰 갈래로 실패하면
`after_token_failure` 로 한 번 갱신하고 새 토큰이면 조회를 한 번만 다시 한다. 조회 길은 공식버전
자동 갱신 예약 스레드에서도 돈다 — 이 모듈은 Streamlit 을 import 하지 않는다.

**죽이기 고리 막기.** 계정당 최신 토큰 하나만 살아 있다(교환 하나가 앞 토큰을 죽이고, 같은 계정의
WebIDE 로그인이 운영 토큰을 죽인다 — 2026-11-12 담당자 답).
- 교환 + 넣기는 스레드 잠금과 자격 폴더의 파일 잠금 안에서만 한다(`getData` 는 잠금 밖).
- 잠금을 잡은 뒤 넣은 때 표지를 다시 읽어, 결정한 때와 다르면(다른 스레드 · 프로세스가 넣음)
  교환하지 않는다 — 실패 뒤라면 그 새 토큰으로 한 번 다시 한다.
- 시도 사이 최소 `MIN_ATTEMPT_GAP`(5분) — 성공 · 실패 모두.
- 갱신으로 넣은 서로 다른 토큰이 `LOOP_WINDOW`(1시간) 안에 `LOOP_LIMIT`(둘) 번 토큰 실패를 내면
  멈춘다(까닭 「같은 계정이 다른 곳에서 로그인했을 수 있음」 — 관리자 알림 `AD-17`). 사람이 넣은
  토큰(Admin 「토큰 넣기」 · 시작 스크립트)이 멈춘 뒤 들어오거나 앱을 다시 띄우면 풀린다.
- 미리 볼 것(넣기 막힘 · 계정 · 갱신 토큰 읽기)은 교환 **전에** 본다 — 받은 토큰을 못 넣으면 앞
  토큰만 죽인 셈이다.

**비밀.** 토큰 · 갱신 토큰의 글자 · 길이를 어떤 글(상태 까닭 · 알림 · 로그 · 예외)에도 싣지 않는다.
교환이 낸 예외는 종류 이름만 남긴다 — 그 문구에 요청 · 응답이 실려 올 수 있다. `Exchanged.token` 은
`repr` 에서 뺀다.

**갱신 토큰의 나이.** 3개월 유효 — 이 서버가 그 갱신 토큰 파일을 처음 쓴 때(파일 수정 시각 — 시작
스크립트는 같은 내용이면 다시 쓰지 않는다)부터 `REFRESH_TOKEN_WARNING_AGE`(80일)이면 관리자
알림(`AD-18`). 컨테이너 디스크가 다시 띄울 때 처음으로 돌아가면 그때마다 다시 센다(사내 확인 거리).

시작 스크립트가 앱 의존성보다 먼저 읽으므로 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final, Literal

from capa_simulation.io import bdq_token
from capa_simulation.io.container_start_report import BDQ_USER_NAME_ENV

if sys.platform != "win32":
    import fcntl

# --- 교환 한 곳 -----------------------------------------------------------------------

# 갱신 요청의 꼴을 아는가 — 「준비」 와 「켜짐」 을 가른다(교환을 부르지 않고 안다). `exchange` 의
# 몸을 채울 때 참으로 바꾼다.
REQUEST_SHAPE_KNOWN: bool = False


class RefreshNotConfigured(RuntimeError):
    """갱신 요청 꼴(주소 · 방법 · 갱신 토큰을 넣는 자리 · 응답 칸)을 아직 모른다(담당자 답 대기)."""


@dataclass(frozen=True)
class Exchanged:
    """교환 한 번의 결과 — 새 로그인 토큰(패키지가 읽는 파일에 그대로 쓸 바이트)과 응답이 알려 준
    만료 시각(UTC, 모르면 `None`). 토큰은 `repr` 에 싣지 않는다."""

    token: bytes = field(repr=False)
    expires_at: datetime | None = None


def exchange(refresh_token: bytes, account: str) -> Exchanged:
    """갱신 토큰으로 새 로그인 토큰을 받는다. **담당자 답이 오면 이 몸만 채운다**(그리고
    `REQUEST_SHAPE_KNOWN` 을 참으로).

    채울 때 지킬 것: 표준 라이브러리(`urllib.request`)만 · 시간 제한 · 사내 CA 는 OS 인증서 묶음 ·
    갱신 토큰은 명령줄 · 주소 쿼리에 싣지 않음 · 실패는 예외로(문구에 비밀이 실려도 부르는 쪽은
    종류 이름만 남긴다). 응답이 갱신 토큰도 새로 주면 `Exchanged` 에 칸을 더해 갱신 토큰 파일을
    바꿔 쓴다.
    """
    del refresh_token, account
    raise RefreshNotConfigured("갱신 요청 꼴 미정")


# --- 자리 · 값 --------------------------------------------------------------------------

REFRESH_FILE_PREFIX: Final = "capa-bdq-refresh."
LOCK_SUFFIX: Final = ".lock"
# 넣은 때부터 이만큼 지나면 미리 갱신한다(2026-11-14 사용자 요청 「발급 6시간 뒤」 — 서버 수명
# 8시간).
REFRESH_AFTER: Final = timedelta(hours=6)
# 토큰에서 만료를 읽었으면 이만큼 앞부터 갱신한다(만료 전 관리자 알림 `AD-11` 과 같은 앞당김).
EXPIRY_LEAD: Final = timedelta(seconds=bdq_token.EXPIRY_WARNING_SECONDS)
MIN_ATTEMPT_GAP: Final = timedelta(minutes=5)
LOOP_WINDOW: Final = timedelta(hours=1)
LOOP_LIMIT: Final = 2
# 갱신 토큰(3개월 유효)을 바꿀 때를 알리는 나이.
REFRESH_TOKEN_WARNING_AGE: Final = timedelta(days=80)
# 넣은 때 표지가 지금보다 이만큼 넘게 앞이면(시계가 뒤로 감) 믿지 않는다. 토큰 파일이 표지보다
# 이만큼 넘게 새로우면 밖에서 바꾼 것이다(표지는 토큰을 쓴 뒤에 초 단위로 쓴다).
CLOCK_SLACK: Final = timedelta(minutes=5)
MARK_LAG: Final = timedelta(seconds=2)

Mode = Literal["off", "ready", "on", "halted"]
MODE_LABELS: Final[Mapping[Mode, str]] = {
    "off": "꺼짐",
    "ready": "준비",
    "on": "켜짐",
    "halted": "멈춤",
}
NO_REFRESH_TOKEN: Final = "갱신 토큰 없음"
SHAPE_UNKNOWN: Final = "요청 꼴 미정"
HALT_ELSEWHERE: Final = "같은 계정이 다른 곳에서 로그인했을 수 있음"

_LOGGER = logging.getLogger(__name__)


def _system_clock() -> datetime:
    return datetime.now(timezone.utc)


# 지금 시각(UTC). 시험이 바꿔 끼운다 — 잠들지 않고 시각을 옮긴다.
clock: Callable[[], datetime] = _system_clock


def refresh_token_path(folder: Path, account: str) -> Path | None:
    """계정의 갱신 토큰 파일 자리. 계정 이름이 폴더 밖을 가리키면 `None`."""
    if bdq_token.token_file_path(folder, account) is None:
        return None
    return folder / f"{REFRESH_FILE_PREFIX}{account}"


def _modified(path: Path | None) -> datetime | None:
    if path is None:
        return None
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    try:
        return datetime.fromtimestamp(stamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


@dataclass(frozen=True)
class _Place:
    folder: Path
    account: str
    refresh_file: Path


def _place(environ: Mapping[str, str] | None, folder: Path | None) -> tuple[_Place | None, str]:
    """갱신할 자리 또는 (없음, 꺼짐 까닭). 까닭은 값 낱말이고 비밀이 없다."""
    env = os.environ if environ is None else environ
    if bdq_token.environment_token_set(env):
        return None, f"{bdq_token.LOGIN_TOKEN_ENV} 있음"
    account = env.get(BDQ_USER_NAME_ENV, "").strip()
    if not account:
        return None, f"{BDQ_USER_NAME_ENV} 없음"
    base = bdq_token.credential_dir() if folder is None else folder
    path = refresh_token_path(base, account)
    if path is None:
        return None, f"{BDQ_USER_NAME_ENV} 을 파일 이름으로 못 씀"
    try:
        present = path.is_file()
    except OSError:
        present = False
    if not present:
        return None, NO_REFRESH_TOKEN
    return _Place(base, account, path), ""


# --- 프로세스 상태 ---------------------------------------------------------------------


@dataclass
class _Process:
    """이 프로세스의 갱신 기록 — 시각 · 갈래 낱말뿐이다(비밀 없음)."""

    last_attempt_at: datetime | None = None
    last_failure: str = ""
    last_failure_at: datetime | None = None
    shape_unknown: bool = False
    halted_at: datetime | None = None
    # 갱신으로 넣은 토큰(넣은 때로 가른다) → 그 토큰이 토큰 실패를 낸 첫 시각.
    deaths: dict[datetime, datetime] = field(default_factory=dict)


_STATE = _Process()
_STATE_LOCK: Final = threading.Lock()
# 교환 + 넣기를 한 프로세스 안에서 하나씩.
_EXCHANGE_LOCK: Final = threading.Lock()


def forget_state() -> None:
    """시험 전용 — 이 프로세스의 갱신 기록을 비운다."""
    global _STATE
    with _STATE_LOCK:
        _STATE = _Process()


def _exchange_known() -> bool:
    with _STATE_LOCK:
        return REQUEST_SHAPE_KNOWN and not _STATE.shape_unknown


def _release_halt(mark: bdq_token.InstalledMark | None) -> None:
    """멈춘 뒤 사람이 넣은 토큰(Admin · 시작)이 들어왔으면 푼다. `_STATE_LOCK` 안에서 부른다."""
    halted = _STATE.halted_at
    if halted is None or mark is None or mark.source == "refresh":
        return
    if mark.installed_at > halted:
        _STATE.halted_at = None
        _STATE.deaths.clear()


def _note_failure(kind: str, now: datetime) -> None:
    with _STATE_LOCK:
        _STATE.last_failure = kind
        _STATE.last_failure_at = now
    _LOGGER.warning("BigDataQuery 자동 갱신 실패: %s", kind)


# --- 상태 -------------------------------------------------------------------------------


@dataclass(frozen=True)
class RefreshStatus:
    """자동 갱신의 지금 — 화면 표 줄 · 알림이 읽는다. 값은 시각과 갈래 낱말뿐이다.

    `reason` 은 꺼짐 · 준비 · 멈춤의 까닭 낱말, `last_refreshed_at` 은 갱신으로 넣은 토큰의 넣은
    때(넣은 때 표지), `last_failure` 는 이 프로세스의 마지막 시도 실패 갈래(성공하면 비운다),
    `refresh_token_since` 는 이 서버가 갱신 토큰 파일을 쓴 때다."""

    mode: Mode
    reason: str = ""
    last_refreshed_at: datetime | None = None
    last_failure: str = ""
    last_failure_at: datetime | None = None
    refresh_token_since: datetime | None = None

    @property
    def label(self) -> str:
        return MODE_LABELS[self.mode]


def status(environ: Mapping[str, str] | None = None) -> RefreshStatus:
    """지금 자동 갱신 상태. 회차마다 불러도 된다(작은 파일 둘의 stat · 표지 읽기). 예외를 내지
    않는다 — 읽다 무엇이 나도 꺼짐으로 물러선다."""
    try:
        place, off = _place(environ, None)
        if place is None:
            return RefreshStatus("off", off)
        mark = bdq_token.read_installed_mark(place.folder, place.account)
        refreshed = mark.installed_at if mark is not None and mark.source == "refresh" else None
        since = _modified(place.refresh_file)
        with _STATE_LOCK:
            _release_halt(mark)
            halted = _STATE.halted_at is not None
            failure, failed_at = _STATE.last_failure, _STATE.last_failure_at
            known = REQUEST_SHAPE_KNOWN and not _STATE.shape_unknown
        if not known:
            return RefreshStatus("ready", SHAPE_UNKNOWN, refresh_token_since=since)
        return RefreshStatus(
            "halted" if halted else "on",
            HALT_ELSEWHERE if halted else "",
            last_refreshed_at=refreshed,
            last_failure=failure,
            last_failure_at=failed_at,
            refresh_token_since=since,
        )
    except Exception as error:
        _LOGGER.warning("BigDataQuery 자동 갱신 상태를 읽지 못함: %s", type(error).__name__)
        return RefreshStatus("off", "확인하지 못함")


def refresh_token_aging(state: RefreshStatus, now: datetime | None = None) -> bool:
    """갱신 토큰을 바꿀 때인가 — 갱신 토큰이 있고(꺼짐이 아님) 처음 쓴 때부터 80일."""
    if state.mode == "off" or state.refresh_token_since is None:
        return False
    moment = clock() if now is None else now
    return moment - state.refresh_token_since >= REFRESH_TOKEN_WARNING_AGE


# --- 조회 길 ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Ticket:
    """조회 한 번이 `getData` 를 부른 때의 넣은 때 표지 — 실패 뒤 「그 사이 다른 쪽이 넣었나」 와
    「죽은 토큰이 갱신으로 넣은 것인가」 를 가른다. `active` 가 거짓이면(꺼짐 · 준비) 실패 뒤에도
    아무것도 하지 않는다."""

    active: bool
    mark: bdq_token.InstalledMark | None = None


_INACTIVE: Final = Ticket(False)


def _token_issued_at(
    place: _Place, mark: bdq_token.InstalledMark | None, now: datetime
) -> datetime | None:
    """지금 토큰을 넣은 때 — 표지가 믿을 만하면 그것, 아니면 토큰 파일 수정 시각. 토큰 파일이 없으면
    `None`(곧 갱신할 때)."""
    target = bdq_token.token_file_path(place.folder, place.account)
    written = _modified(target)
    if written is None:
        return None
    if mark is not None and mark.installed_at <= now + CLOCK_SLACK:
        if written <= mark.installed_at + MARK_LAG:
            return mark.installed_at
    return min(written, now)


def _due(
    place: _Place, mark: bdq_token.InstalledMark | None, now: datetime, env: Mapping[str, str]
) -> bool:
    """갱신할 때인가 — 넣은 때부터 6시간 · 토큰 없음 · 만료 1시간 안. 만료는 토큰에서 읽은 것
    (JWT `exp`) 또는 그 토큰을 넣은 갱신 응답이 알려 준 것(넣은 때 표지)이다."""
    issued = _token_issued_at(place, mark, now)
    if issued is None or now - issued >= REFRESH_AFTER:
        return True
    expires = bdq_token.current_token(env).expires_at
    if expires is None and mark is not None and issued == mark.installed_at:
        expires = mark.expires_at
    return expires is not None and expires - now <= EXPIRY_LEAD


def before_query(environ: Mapping[str, str] | None = None) -> Ticket:
    """`getData` 바로 앞 — 켜짐이고 갱신할 때면 먼저 갱신한다. 예외를 내지 않는다 — 미리 한 갱신이
    실패해도 조회는 지금 토큰으로 그대로 간다. 꺼짐 · 준비는 아무것도 하지 않는다."""
    try:
        place, _ = _place(environ, None)
        if place is None or not _exchange_known():
            return _INACTIVE
        env = os.environ if environ is None else environ
        mark = bdq_token.read_installed_mark(place.folder, place.account)
        now = clock()
        if _due(place, mark, now, env):
            _attempt(place, env, mark, now)
        return Ticket(True, bdq_token.read_installed_mark(place.folder, place.account))
    except Exception as error:
        _LOGGER.warning("BigDataQuery 자동 갱신을 건너뜀: %s", type(error).__name__)
        return _INACTIVE


def after_token_failure(ticket: Ticket, *, refresh: bool = True) -> Ticket | None:
    """조회가 토큰 갈래로 실패한 뒤 — 죽은 토큰이 갱신으로 넣은 것이면 고리 기록에 올리고, `refresh`
    면 한 번 갱신한다. 조회를 다시 할 만하면(새 토큰이 들어옴) 그때의 `Ticket`, 아니면 `None`.
    예외를 내지 않는다."""
    if not ticket.active:
        return None
    try:
        place, _ = _place(None, None)
        if place is None or not _exchange_known():
            return None
        now = clock()
        # 죽은 토큰이 아직 들어 있는 토큰일 때만 센다 — 조회가 도는 사이 이 프로세스의 미리 한
        # 갱신이 바꿔 끼운 토큰의 실패는 그 교환이 죽인 것이지 다른 곳의 로그인이 아니다.
        if bdq_token.read_installed_mark(place.folder, place.account) == ticket.mark:
            _note_death(ticket.mark, now)
        if not refresh:
            return None
        env = os.environ
        result = _attempt(place, env, ticket.mark, now)
        if result not in ("installed", "other"):
            return None
        return Ticket(True, bdq_token.read_installed_mark(place.folder, place.account))
    except Exception as error:
        _LOGGER.warning("BigDataQuery 자동 갱신을 건너뜀: %s", type(error).__name__)
        return None


def _note_death(mark: bdq_token.InstalledMark | None, now: datetime) -> None:
    """갱신으로 넣은 토큰이 토큰 실패를 냈다 — 서로 다른 토큰이 `LOOP_WINDOW` 안에 `LOOP_LIMIT`
    번이면 멈춘다. 같은 토큰의 겹친 실패(동시 조회)는 한 번으로 센다."""
    if mark is None or mark.source != "refresh":
        return
    with _STATE_LOCK:
        if _STATE.halted_at is not None:
            return
        _STATE.deaths.setdefault(mark.installed_at, now)
        recent = {token: died for token, died in _STATE.deaths.items() if now - died <= LOOP_WINDOW}
        _STATE.deaths = recent
        if len(recent) < LOOP_LIMIT:
            return
        _STATE.halted_at = now
    _LOGGER.warning("BigDataQuery 자동 갱신 멈춤: %s", HALT_ELSEWHERE)


AttemptResult = Literal["installed", "other", "skipped", "failed", "not_configured"]


@contextmanager
def _folder_lock(place: _Place) -> Iterator[None]:
    """자격 폴더의 파일 잠금 — 시작 스크립트 · 앱 두 프로세스 사이. 잠금 파일을 열지 못하면(폴더
    없음 · 권한) 스레드 잠금만으로 간다. Windows 는 스레드 잠금만 — 거기선 갱신 토큰이 없다."""
    if sys.platform == "win32":
        yield
        return
    path = place.folder / f"{REFRESH_FILE_PREFIX}{place.account}{LOCK_SUFFIX}"
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        yield
        return
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _attempt(
    place: _Place,
    env: Mapping[str, str],
    seen: bdq_token.InstalledMark | None,
    now: datetime,
) -> AttemptResult:
    """교환 + 넣기 한 번 — 잠금 안. `seen` 은 결정한 때의 넣은 때 표지다."""
    with _EXCHANGE_LOCK, _folder_lock(place):
        current = bdq_token.read_installed_mark(place.folder, place.account)
        if current != seen:
            return "other"
        with _STATE_LOCK:
            _release_halt(current)
            if _STATE.halted_at is not None:
                return "skipped"
            last = _STATE.last_attempt_at
            if last is not None and now - last < MIN_ATTEMPT_GAP:
                return "skipped"
            _STATE.last_attempt_at = now
        blocked = bdq_token.blocked_reason(env)
        if blocked is not None:
            _note_failure("넣기 막힘", now)
            return "failed"
        try:
            secret = place.refresh_file.read_bytes()
        except OSError as error:
            _note_failure(f"갱신 토큰을 읽지 못함({type(error).__name__})", now)
            return "failed"
        if not secret.strip():
            _note_failure("갱신 토큰이 비었음", now)
            return "failed"
        try:
            got = exchange(secret, place.account)
        except RefreshNotConfigured:
            with _STATE_LOCK:
                _STATE.shape_unknown = True
            return "not_configured"
        except Exception as error:
            _note_failure(f"교환 실패({type(error).__name__})", now)
            return "failed"
        if not isinstance(got, Exchanged) or not isinstance(got.token, bytes):
            _note_failure("교환 응답 꼴이 다름", now)
            return "failed"
        expires = got.expires_at if isinstance(got.expires_at, datetime) else None
        outcome = bdq_token.install_content(
            got.token, "refresh", env, folder=place.folder, at=clock(), expires_at=expires
        )
        if outcome.status == "refused":
            _note_failure(f"받은 토큰을 넣지 못함 — {outcome.reason}", now)
            return "failed"
        if outcome.status == "same":
            bdq_token.write_installed_mark(place.folder, place.account, "refresh", clock(), expires)
        with _STATE_LOCK:
            _STATE.last_failure = ""
            _STATE.last_failure_at = None
        _LOGGER.info("BigDataQuery 자동 갱신: 새 토큰을 넣음")
        return "installed"


# --- 시작 스크립트 -----------------------------------------------------------------------


@dataclass(frozen=True)
class StartRefresh:
    """시작 때 자동 갱신 한 번의 결과 — 결과 파일 `refresh` 칸. `installed` 면 시작 스크립트가
    `CAPA_BDQ_TOKEN` 을 쓰지 않는다."""

    mode: Mode
    reason: str
    installed: bool = False
    failed: bool = False

    def as_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "installed": self.installed,
            "failed": self.failed,
        }


def refresh_at_start(environ: Mapping[str, str], folder: Path) -> StartRefresh:
    """시작 스크립트가 갱신 토큰 파일을 쓴 뒤 부른다 — 켜짐이면 바로 갱신해 받은 토큰을 쓴다. 꺼짐 ·
    준비는 아무것도 하지 않는다(지금 길 그대로)."""
    place, off = _place(environ, folder)
    if place is None:
        return StartRefresh("off", off)
    if not _exchange_known():
        return StartRefresh("ready", SHAPE_UNKNOWN)
    seen = bdq_token.read_installed_mark(place.folder, place.account)
    result = _attempt(place, environ, seen, clock())
    if result == "installed":
        return StartRefresh("on", "갱신해 받은 토큰을 씀", installed=True)
    if result == "not_configured":
        return StartRefresh("ready", SHAPE_UNKNOWN)
    with _STATE_LOCK:
        failure = _STATE.last_failure or "건너뜀"
    return StartRefresh("on", f"시작 때 갱신 실패 — {failure}", failed=True)
