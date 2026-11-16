# Purpose: 저장된 계정의 BigDataQuery 하위 프로세스 로그인 · 결과 갈래 · 잠김 방지 · 다시 로그인.

"""BigDataQuery 자동 로그인 실행기.

C-DEP(`managed`)에서 BDQ 토큰이 만료 · 무효가 되면 앱이 저장된 계정(`io/bdq_login_store`)으로 스스로
다시 로그인한다. 길은 셋이다 — 시작(`start_login` — 시작 스크립트가 부른다), 조회 중 토큰 예외
(`run_with_relogin` · `recover_after_token_failure` — 어댑터가 부른다), Admin 폼 제출
(`login_from_form`).

**로그인 한 번**(`attempt_login`)은 `sys.executable` 하위 프로세스(`io/bdq_login_child.py`)다.
계정 · 비밀번호는 표준 입력으로만 넘기고 명령줄 · 환경변수에 없다. 하위 환경은 비밀
이름(시작 스크립트가 앱에 넘기지 않는 것 · 통합인증 비밀 · `CAPA_BDQ_SECRET_KEY` · `CAPA_S3_*` ·
`AWS_*`)을 뺀 것이다(`child_environment`). 하위 출력(패키지 배너 포함)은 버리고 표지 한 줄만
읽는다. 시간 제한이 있고, tty 가 있는 자리에서도 비밀번호를 표준 입력으로 읽게 새 세션으로
띄운다(제어 터미널 없음).

**판정.** 로그인 전후 토큰 파일(`io/bdq_token` 의 자리) 내용의 다이제스트가 바뀌었으면 성공이다 —
로그인이 받아들여진 것이라 잠김 걱정이 없다. 하위 프로세스가 시간을 넘겼거나 남은 시간을 못 쟀어도
바뀌었으면 성공이다. 남은 분이 `REMAINING_WARNING_MINUTES` 이하거나 모르면 성공 + 경고일 뿐이다.
그대로(또는 파일 없음)면 표지로 가른다 — 패키지를 못 불러옴은 `unavailable`(시도 없음), 연결 ·
시간 초과 종류의 양의 증거나 하위 프로세스 시간 초과는 `unreached`, 그 밖은 모두 `rejected`
다(애매한 실패도 — 계정 잠김 방지가 불변식). 로그인 동안 토큰 파일을 치우지 않는다.

**잠김 방지.** 폼 제출 한 번에 시도 한 번. `rejected` 는 다시 시도하지 않고 멈춘다 — 프로세스 안에
곧바로 적고(그 `cipher` 의 한 벌은 자동 시도 없음) 객체에 멈춤 표시를 쓴다(재시작마다 다시 시도하지
않게). 관리자가 폼에서 다시 넣어 성공하면 풀린다. 자동 시도는 프로세스 안에서 연달아
`AUTO_ATTEMPT_LIMIT` 번까지(하위 프로세스를 띄운 수 — 성공에만 0 으로)이고, `unreached` ·
`unavailable` 뒤에는 `UNREACHED_PAUSE_SECONDS` 동안 쉰다.

**동시성.** 로그인은 프로세스 잠금 하나로 줄 세운다. 토큰 예외를 본 조회는 그 조회 앞의 토큰
다이제스트를 들고 잠금을 기다리고, 잠금을 얻었을 때 다이제스트가 바뀌었으면(누가 이미 다시 로그인)
로그인하지 않고 바로 다시 조회한다. 공식버전 자동 갱신 스레드도 어댑터를 부르므로 Streamlit 을
import 하지 않는다. 새 배경 스레드를 세우지 않는다.

**다시 로그인의 문.** `bigdataquery.exceptions` 의 토큰 예외 종류(`RELOGIN_EXCEPTIONS` — 한 줄로
더한다)에서만 다시 로그인한다. 문구 낱말만 맞은 토큰 갈래는 알림만이다(어댑터 몫).

**비밀.** 결과 · 로그 · 예외에 계정 · 비밀번호 · 예외 문구 · 하위 출력이 없다 — 예외 종류의
`모듈.이름` 과 짧은 영문 까닭 코드만. 토큰 다이제스트도 밖으로 내지 않는다(지문이다).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, TypeVar

from capa_simulation.auth import names as sso_names
from capa_simulation.io import bdq_login_store as store
from capa_simulation.io import bdq_token
from capa_simulation.io.bdq_login_child import MARKER
from capa_simulation.io.bdq_login_store import LoadResult, LoginSecret, StoredLogin
from capa_simulation.io.container_start_report import APP_WITHHELD_ENVIRONMENT

if TYPE_CHECKING:
    from capa_simulation.io.s3_small import S3Target

T = TypeVar("T")

# 하위 프로세스 하나의 시간 제한(패키지 import · 로그인 · 남은 시간 재기까지).
LOGIN_TIMEOUT_SECONDS: Final = 60.0
# 프로세스 안 연속 자동 시도 상한 — 하위 프로세스를 띄운 수, 성공에만 0 으로.
AUTO_ATTEMPT_LIMIT: Final = 3
# `unreached` · `unavailable` 뒤 자동 시도를 쉬는 초.
UNREACHED_PAUSE_SECONDS: Final = 300.0
# 이 분 이하로 남았으면 성공 + 경고(수명 8시간 — 막 받은 토큰은 7시간 넘게 남는다).
REMAINING_WARNING_MINUTES: Final = 7 * 60
# 다시 로그인을 거는 예외 종류(`모듈.이름`). 사슬의 어느 고리든 그 종류(또는 하위 종류)면 건다.
# 무효 · 만료 토큰의 종류를 알게 되면 이 한 줄에 더한다.
RELOGIN_EXCEPTIONS: Final[tuple[str, ...]] = ("bigdataquery.exceptions.TokenNotFoundException",)

Outcome = Literal["ok", "rejected", "unreached", "unavailable"]
OUTCOME_OK: Final = "ok"
OUTCOME_REJECTED: Final = "rejected"
OUTCOME_UNREACHED: Final = "unreached"
OUTCOME_UNAVAILABLE: Final = "unavailable"

# 까닭 코드 — 짧은 영문(멈춤 표시 `stop_reason` 에도 그대로 들어간다).
REASON_TOKEN_UNCHANGED: Final = "token_unchanged"
REASON_LOGIN_RAISED: Final = "login_raised"
REASON_NO_MARKER: Final = "no_marker"
REASON_TIMEOUT: Final = "timeout"
REASON_CONNECTION: Final = "connection"
REASON_IMPORT_FAILED: Final = "import_failed"
REASON_NO_INPUT: Final = "no_input"
REASON_SPAWN_FAILED: Final = "spawn_failed"
REASON_BAD_INPUT: Final = "bad_input"
REASON_BAD_ACCOUNT: Final = "bad_account"
REASON_ENV_TOKEN: Final = "env_token"
REASON_TOKEN_AFTER_LOGIN: Final = "token_after_login"

WARNING_REMAINING_SHORT: Final = "remaining_short"
WARNING_REMAINING_UNKNOWN: Final = "remaining_unknown"

# 자동 시도를 건너뛴 까닭.
SKIP_STOPPED: Final = "stopped"
SKIP_ATTEMPT_LIMIT: Final = "attempt_limit"
SKIP_PAUSED: Final = "paused"

# 조회 중 회복에서 로그인 없이 끝난 까닭.
RECOVERY_NO_LOGIN: Final = "no_login"
RECOVERY_RENEWED: Final = "renewed"

# 하위 프로세스에 넘기지 않는 이름 · 접두. 시작 스크립트가 앱에 넘기지 않는 비밀 · 통합인증 비밀과
# 명단 · 이 기능의 키 · S3 · AWS 전부.
CHILD_WITHHELD_ENVIRONMENT: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        (
            *APP_WITHHELD_ENVIRONMENT,
            *sso_names.SECRET_ENVIRONMENT,
            *sso_names.WITHHELD_ENVIRONMENT,
            store.SECRET_KEY_ENV,
        )
    )
)
CHILD_WITHHELD_PREFIXES: Final[tuple[str, ...]] = ("CAPA_S3_", "AWS_")

CHILD_SCRIPT: Final = Path(__file__).with_name("bdq_login_child.py")
# 하위 프로세스 본문을 그 폴더를 `sys.path` 에 넣지 않고 돌린다. 앱 패키지 경로 · 사용자 site 는
# 그대로 둔다(`-I` 를 쓰지 않는다 — 사내 패키지가 사용자 site 에 있을 수 있다).
_LAUNCH: Final = "import runpy, sys; runpy.run_path(sys.argv[1], run_name='__main__')"
_NAME: Final = r"[A-Za-z_][A-Za-z0-9_.]{0,199}"
_MARKER_LINE: Final = re.compile(
    rf"{re.escape(MARKER)} stage=(input|import|login|done) error=(-|{_NAME}) net=([01]) "
    rf"minutes=(-|[0-9]{{1,7}}) time_error=(-|{_NAME})"
)
# 원인을 따라가는 깊이.
_CHAIN_LIMIT: Final = 5

_LOGGER = logging.getLogger("capa_simulation.bdq_login")


# --- 결과 꼴 ----------------------------------------------------------------------------


@dataclass(frozen=True)
class LoginResult:
    """로그인 한 번(또는 시도 전 거절)의 결과. 비밀 · 예외 문구 · 하위 출력이 없다.

    `reason` 은 짧은 영문 까닭 코드, `error_kind` 는 예외 종류의 `모듈.이름`, `remaining_minutes` 는
    로그인 뒤 잰 남은 분(모르면 `None`), `warning` 은 성공의 덧붙임(`WARNING_*`)이다."""

    outcome: Outcome
    reason: str = ""
    error_kind: str = ""
    remaining_minutes: int | None = None
    warning: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome == OUTCOME_OK


@dataclass(frozen=True)
class Attempt:
    """자동 시도 한 번 — 건너뛰었으면 `result` 가 `None` 이고 `skipped` 가 까닭. `rejected` 의 멈춤
    표시를 객체에 쓰지 못했으면 `stop_write` 가 그 까닭이다(프로세스 안 멈춤은 그대로 선다)."""

    result: LoginResult | None
    skipped: str = ""
    stop_write: str = ""


@dataclass(frozen=True)
class Recovery:
    """조회 중 토큰 예외 뒤의 회복. `retry` 면 같은 조회를 한 번 다시 한다. `logged_in` 은 이 회복이
    스스로 로그인해 성공한 것(다시 한 조회가 또 토큰 오류면 멈춘다)."""

    retry: bool
    logged_in: bool = False
    attempt: Attempt | None = None
    reason: str = ""
    stored: StoredLogin | None = field(default=None, repr=False)


@dataclass(frozen=True)
class FormResult:
    """폼 제출 한 번. 로그인이 성공하고 저장까지 되면 `saved`. 로그인은 됐는데 저장하지 못했으면
    `save_failure` 가 그 까닭이다(앞서 저장된 계정 · 상태는 그대로)."""

    result: LoginResult
    saved: bool = False
    save_failure: str = ""


StartStatus = Literal["off", "absent", "stopped", "ok", "rejected", "unreached", "unavailable"]


@dataclass(frozen=True)
class StartLogin:
    """시작 때 로그인 단계. `off` — 기능이 서지 않음, `absent` — 저장된 계정 없음(지금 길),
    `stopped` — 멈춤이라 로그인 없음, 그 밖은 로그인 결과 갈래. `stored` 는 토큰 파일 이름에 쓸
    계정을 가진 한 벌이다(repr 에 나오지 않는다)."""

    status: StartStatus
    reason: str = ""
    failure_kind: str = ""
    result: LoginResult | None = None
    stop_write: str = ""
    stored: StoredLogin | None = field(default=None, repr=False)


@dataclass(frozen=True)
class LastAttempt:
    """마지막 시도 — KST 시각 · 자동인가 · 결과."""

    at: str
    auto: bool
    result: LoginResult


@dataclass(frozen=True)
class LoginStatus:
    """화면 · 알림이 읽는 한 벌. `state` — `none`(저장된 계정 없음) · `ok` · `stopped`."""

    load: LoadResult
    last: LastAttempt | None
    streak: int
    paused: bool
    stopped_in_process: bool

    @property
    def state(self) -> Literal["none", "ok", "stopped"]:
        stored = self.load.stored
        if stored is None:
            return "none"
        return "stopped" if stored.stopped or self.stopped_in_process else "ok"

    @property
    def active(self) -> bool:
        """자동 로그인이 서 있나(저장된 계정이 있고 멈춤이 아님)."""
        return self.state == "ok"

    @property
    def stop_reason(self) -> str:
        stored = self.load.stored
        if stored is not None and stored.stop_reason:
            return stored.stop_reason
        if self.stopped_in_process and self.last is not None:
            return self.last.result.reason
        return ""


@dataclass(frozen=True)
class Marker:
    """하위 프로세스 표지 한 줄을 푼 것."""

    stage: str
    error: str
    net: bool
    minutes: int | None
    time_error: str


# --- 프로세스 상태 ------------------------------------------------------------------------


@dataclass
class _Process:
    streak: int = 0
    paused_until: float = 0.0
    stopped_cipher: str = field(default="", repr=False)
    last: LastAttempt | None = None


_STATE = _Process()
_STATE_LOCK: Final = threading.Lock()
# 로그인을 줄 세우는 잠금 — 자동 · 폼 · 시작 모두.
_LOGIN_LOCK: Final = threading.Lock()
# 시험이 바꿔 끼우는 시계(쉬는 시간).
_monotonic: Callable[[], float] = time.monotonic


def forget_state() -> None:
    """시험 전용 — 프로세스 상태(연속 시도 · 쉬는 시간 · 멈춤 · 마지막 시도)와 저장 객체 기억을
    지운다."""
    with _STATE_LOCK:
        _STATE.streak = 0
        _STATE.paused_until = 0.0
        _STATE.stopped_cipher = ""
        _STATE.last = None
    store.forget_state()


def _reset_after_success() -> None:
    with _STATE_LOCK:
        _STATE.streak = 0
        _STATE.paused_until = 0.0
        _STATE.stopped_cipher = ""


def _note_last(result: LoginResult, *, auto: bool) -> None:
    with _STATE_LOCK:
        _STATE.last = LastAttempt(store.kst_text(), auto, result)


def status() -> LoginStatus:
    """지금 상태(저장 객체 기억은 처음이면 읽는다)."""
    loaded = store.load_state()
    with _STATE_LOCK:
        stored = loaded.stored
        stopped_here = stored is not None and _STATE.stopped_cipher == stored.cipher
        return LoginStatus(
            load=loaded,
            last=_STATE.last,
            streak=_STATE.streak,
            paused=_monotonic() < _STATE.paused_until,
            stopped_in_process=stopped_here,
        )


def auto_login_active() -> bool:
    """자동 로그인이 서 있나 — 만료 전 알림(`AD-11`)을 내지 않을지 가른다."""
    return status().active


# --- 하위 프로세스 ------------------------------------------------------------------------


def child_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """로그인 하위 프로세스의 환경 — 비밀 이름 · 접두를 빼고 표준 입출력을 UTF-8 로."""
    env = {
        name: value
        for name, value in environ.items()
        if name not in CHILD_WITHHELD_ENVIRONMENT and not name.startswith(CHILD_WITHHELD_PREFIXES)
    }
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def login_command() -> list[str]:
    """하위 프로세스 명령줄 — 계정 · 비밀번호가 없다."""
    return [sys.executable, "-c", _LAUNCH, str(CHILD_SCRIPT)]


def file_digest(path: Path) -> str | None:
    """파일 내용의 다이제스트(없거나 못 읽으면 `None`). 밖으로 내지 않는다(지문이다)."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def token_digest(account: str, folder: Path | None = None) -> str | None:
    """그 계정 토큰 파일의 다이제스트. 계정이 파일 이름으로 못 쓰는 글이면 `None`."""
    place = bdq_token.credential_dir() if folder is None else folder
    target = bdq_token.token_file_path(place, account)
    return None if target is None else file_digest(target)


def parse_marker(output: bytes) -> Marker | None:
    """하위 표준 출력에서 마지막 표지 줄을 푼다. 꼴이 어긋나면 `None`(표지 없음)."""
    text = output.decode("utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith(f"{MARKER} ")]
    if not lines:
        return None
    found = _MARKER_LINE.fullmatch(lines[-1])
    if found is None:
        return None
    stage, error, net, minutes, time_error = found.groups()
    return Marker(
        stage=stage,
        error="" if error == "-" else error,
        net=net == "1",
        minutes=None if minutes == "-" else int(minutes),
        time_error="" if time_error == "-" else time_error,
    )


def _input_problem(account: str, password: str) -> str | None:
    """표준 입력 줄 약속을 깨는 값(빈 값 · 줄바꿈)."""
    if not account or not password:
        return REASON_BAD_INPUT
    if any(mark in account or mark in password for mark in ("\n", "\r", "\0")):
        return REASON_BAD_INPUT
    if account != account.strip():
        return REASON_BAD_INPUT
    return None


def _judge(
    *,
    changed: bool,
    marker: Marker | None,
    timed_out: bool,
    spawn_failed: bool,
) -> LoginResult:
    if changed:
        minutes = marker.minutes if marker is not None and marker.stage == "done" else None
        if minutes is None:
            warning = WARNING_REMAINING_UNKNOWN
        elif minutes <= REMAINING_WARNING_MINUTES:
            warning = WARNING_REMAINING_SHORT
        else:
            warning = ""
        error_kind = marker.error if marker is not None and marker.stage == "login" else ""
        return LoginResult(OUTCOME_OK, "", error_kind, minutes, warning)
    if spawn_failed:
        return LoginResult(OUTCOME_UNAVAILABLE, REASON_SPAWN_FAILED)
    if timed_out:
        return LoginResult(OUTCOME_UNREACHED, REASON_TIMEOUT)
    if marker is None:
        return LoginResult(OUTCOME_REJECTED, REASON_NO_MARKER)
    if marker.stage == "input":
        return LoginResult(OUTCOME_UNAVAILABLE, REASON_NO_INPUT)
    if marker.stage == "import":
        return LoginResult(OUTCOME_UNAVAILABLE, REASON_IMPORT_FAILED, marker.error)
    if marker.stage == "login":
        if marker.net:
            return LoginResult(OUTCOME_UNREACHED, REASON_CONNECTION, marker.error)
        return LoginResult(OUTCOME_REJECTED, REASON_LOGIN_RAISED, marker.error)
    return LoginResult(OUTCOME_REJECTED, REASON_TOKEN_UNCHANGED)


def attempt_login(
    account: str,
    password: str,
    *,
    folder: Path | None = None,
    environ: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> LoginResult:
    """로그인 하위 프로세스 한 번 — 잠김 방지 장치 없이 그대로 한 번 띄운다(부르는 쪽이 문을
    지킨다).

    `folder` 는 토큰 폴더(기본 `bdq_token.credential_dir()`), `environ` 은 하위 환경의 바탕(기본
    프로세스 환경 — 비밀 이름은 뺀다)이다. 시도 전 거절(빈 값 · 줄바꿈 · 파일 이름으로 못 쓰는
    계정 · 패키지가 파일보다 먼저 읽는 토큰 환경변수가 있음)은 `unavailable` 이고 하위 프로세스를
    띄우지 않는다."""
    env = os.environ if environ is None else environ
    problem = _input_problem(account, password)
    if problem is not None:
        return LoginResult(OUTCOME_UNAVAILABLE, problem)
    place = bdq_token.credential_dir() if folder is None else folder
    target = bdq_token.token_file_path(place, account)
    if target is None:
        return LoginResult(OUTCOME_UNAVAILABLE, REASON_BAD_ACCOUNT)
    if bdq_token.environment_token_set(env):
        return LoginResult(OUTCOME_UNAVAILABLE, REASON_ENV_TOKEN)
    before = file_digest(target)
    limit = LOGIN_TIMEOUT_SECONDS if timeout is None else timeout
    output = b""
    timed_out = spawn_failed = False
    try:
        completed = subprocess.run(
            login_command(),
            input=f"{account}\n{account}\n{password}\n".encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=child_environment(env),
            timeout=limit,
            check=False,
            start_new_session=os.name == "posix",
        )
        output = completed.stdout or b""
    except subprocess.TimeoutExpired:
        timed_out = True
    except OSError:
        spawn_failed = True
    after = file_digest(target)
    return _judge(
        changed=after is not None and after != before,
        marker=None if timed_out or spawn_failed else parse_marker(output),
        timed_out=timed_out,
        spawn_failed=spawn_failed,
    )


def _log(result: LoginResult, *, path: str) -> None:
    detail = f" 종류={result.error_kind}" if result.error_kind else ""
    if result.warning:
        detail += f" 경고={result.warning}"
    _LOGGER.warning(
        "BigDataQuery 로그인(%s): 결과=%s 까닭=%s%s",
        path,
        result.outcome,
        result.reason or "-",
        detail,
    )


# --- 자동 시도 ----------------------------------------------------------------------------


def _resolve_target(target: S3Target | None) -> S3Target | None:
    if target is not None:
        return target
    try:
        return store.app_target()
    except Exception:  # 통합인증 설정을 읽지 못해도 멈춤 표시만 못 쓸 뿐이다
        return None


def _persist_stop(stored: StoredLogin, reason: str, target: S3Target | None) -> str:
    """객체에 멈춤 표시를 쓴다. 못 쓰면 그 까닭(빈 글이면 씀). 프로세스 안 멈춤은 먼저 선다."""
    with _STATE_LOCK:
        _STATE.stopped_cipher = stored.cipher
    resolved = _resolve_target(target)
    if resolved is None:
        return store.WRITE_UNAVAILABLE
    write = store.mark_stopped(resolved, reason, cipher=stored.cipher)
    if write.ok:
        return ""
    return f"{write.reason}:{write.failure_kind}" if write.failure_kind else write.reason


def _auto_attempt_locked(
    stored: StoredLogin,
    *,
    target: S3Target | None,
    folder: Path | None,
    environ: Mapping[str, str] | None,
    path: str,
) -> Attempt:
    """자동 시도 한 번 — `_LOGIN_LOCK` 을 쥔 채 부른다."""
    with _STATE_LOCK:
        if stored.stopped or _STATE.stopped_cipher == stored.cipher:
            return Attempt(None, SKIP_STOPPED)
        if _STATE.streak >= AUTO_ATTEMPT_LIMIT:
            return Attempt(None, SKIP_ATTEMPT_LIMIT)
        if _monotonic() < _STATE.paused_until:
            return Attempt(None, SKIP_PAUSED)
        _STATE.streak += 1
    secret = stored.secret
    result = attempt_login(secret.account, secret.password, folder=folder, environ=environ)
    _note_last(result, auto=True)
    _log(result, path=path)
    if result.ok:
        _reset_after_success()
        return Attempt(result)
    if result.outcome == OUTCOME_REJECTED:
        return Attempt(result, stop_write=_persist_stop(stored, result.reason, target))
    with _STATE_LOCK:
        _STATE.paused_until = _monotonic() + UNREACHED_PAUSE_SECONDS
    return Attempt(result)


def is_relogin_error(error: BaseException) -> bool:
    """다시 로그인을 걸 예외인가 — 사슬(`__cause__` · `__context__`)의 고리 가운데 그 종류나 상위
    종류가 `RELOGIN_EXCEPTIONS` 에 있는 것. 패키지를 import 하지 않는다. 문구는 보지 않는다."""
    seen: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in seen and len(seen) < _CHAIN_LIMIT:
        seen.append(current)
        for kind in type(current).__mro__:
            if f"{kind.__module__}.{kind.__qualname__}" in RELOGIN_EXCEPTIONS:
                return True
        current = current.__cause__ or current.__context__
    return False


def recover_after_token_failure(
    seen_digest: str | None,
    *,
    target: S3Target | None = None,
    folder: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Recovery:
    """조회가 토큰 예외를 본 뒤 — 잠금을 기다리고, 그 사이 토큰이 바뀌었으면 로그인 없이 다시 조회,
    아니면 자동 시도 한 번. `seen_digest` 는 그 조회 앞의 토큰 다이제스트(`token_digest`)다. 예외를
    내지 않는다."""
    with _LOGIN_LOCK:
        try:
            stored = store.current()
        except Exception:  # 저장 객체를 읽다 깨져도 조회 실패는 그대로 올라간다
            stored = None
        if stored is None:
            return Recovery(False, reason=RECOVERY_NO_LOGIN)
        if token_digest(stored.secret.account, folder) != seen_digest:
            return Recovery(True, reason=RECOVERY_RENEWED, stored=stored)
        attempt = _auto_attempt_locked(
            stored, target=target, folder=folder, environ=environ, path="조회"
        )
    ok = attempt.result is not None and attempt.result.ok
    return Recovery(ok, logged_in=ok, attempt=attempt, stored=stored)


def _stop_after_retry(recovery: Recovery, target: S3Target | None) -> None:
    """스스로 다시 로그인한 뒤 다시 한 조회가 또 토큰 오류 — 멈춘다(저장)."""
    stored = recovery.stored
    if stored is None:
        return
    failed = LoginResult(OUTCOME_REJECTED, REASON_TOKEN_AFTER_LOGIN)
    _note_last(failed, auto=True)
    _log(failed, path="조회")
    try:
        _persist_stop(stored, REASON_TOKEN_AFTER_LOGIN, target)
    except Exception:  # 멈춤 표시를 못 써도 프로세스 안 멈춤은 섰다
        _LOGGER.warning("BigDataQuery 로그인 멈춤 표시를 쓰지 못함")


def run_with_relogin(
    query: Callable[[], T],
    *,
    target: S3Target | None = None,
    folder: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> T:
    """조회 한 번을 돌리고, 토큰 예외(`is_relogin_error`)면 다시 로그인 → 같은 조회를 한 번 다시
    한다.

    저장된 계정이 없으면 `query()` 를 그대로 부른다(지금과 같다). 다시 한 조회의 예외는 첫 실패를
    처리하는 블록 밖에서 나므로 첫 토큰 예외가 그 사슬에 붙지 않는다. 스스로 로그인한 뒤 또 토큰
    오류면 멈춘다(저장). `query` 는 부를 때마다 계정에 딸린 인자를 다시 읽어야 한다(계정이 폼으로
    바뀌었을 수 있다)."""
    try:
        stored = store.current()
    except Exception:  # 저장 객체를 읽다 깨져도 조회는 지금처럼 돈다
        stored = None
    if stored is None:
        return query()
    seen = token_digest(stored.secret.account, folder)
    recovery: Recovery | None = None
    try:
        return query()
    except Exception as error:
        if not is_relogin_error(error):
            raise
        recovery = recover_after_token_failure(seen, target=target, folder=folder, environ=environ)
        if not recovery.retry:
            raise
    try:
        return query()
    except Exception as again:
        if recovery.logged_in and is_relogin_error(again):
            _stop_after_retry(recovery, target)
        raise


# --- 폼 · 지우기 · 시작 ---------------------------------------------------------------------


def login_from_form(
    account: str,
    password: str,
    entered_by_login_id: str,
    *,
    target: S3Target | None = None,
    key: bytes | None = None,
    folder: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> FormResult:
    """Admin 폼 제출 한 번 — 시도 한 번. 성공하면 저장(상태 `ok` — 멈춤도 풀린다), 실패면 저장하지
    않고 앞서 저장된 계정 · 상태를 그대로 둔다. 기능이 서지 않으면 시도하지 않는다."""
    off = store.availability(environ)
    if off is not None:
        return FormResult(LoginResult(OUTCOME_UNAVAILABLE, off))
    resolved_key = key if key is not None else store.secret_key(environ)
    resolved_target = _resolve_target(target)
    if resolved_key is None or resolved_target is None:
        return FormResult(LoginResult(OUTCOME_UNAVAILABLE, store.REASON_NO_TARGET))
    with _LOGIN_LOCK:
        result = attempt_login(account, password, folder=folder, environ=environ)
        _note_last(result, auto=False)
        _log(result, path="폼")
        if not result.ok:
            return FormResult(result)
        write = store.save_login(
            resolved_target, resolved_key, LoginSecret(account, password), entered_by_login_id
        )
        if not write.ok:
            failure = f"{write.reason}:{write.failure_kind}" if write.failure_kind else write.reason
            return FormResult(result, save_failure=failure)
        _reset_after_success()
    return FormResult(result, saved=True)


def forget_login(target: S3Target | None = None) -> store.WriteResult:
    """지우기 단추 — 객체를 지우고 프로세스 상태를 처음으로."""
    resolved = _resolve_target(target)
    if resolved is None:
        return store.WriteResult(False, store.WRITE_UNAVAILABLE)
    with _LOGIN_LOCK:
        write = store.delete_login(resolved)
        if write.ok:
            _reset_after_success()
    return write


def start_login(environ: Mapping[str, str], *, folder: Path | None = None) -> StartLogin:
    """시작 스크립트의 로그인 단계 — `managed` + 키 + 객체 상태 `ok` 면 로그인한다.

    `ok` 면 패키지가 새 토큰을 쓴 것이고, `rejected` 면 멈춤을 저장한다. `unreached` ·
    `unavailable` · `absent` · `stopped` · `off` 는 지금 길(`CAPA_BDQ_TOKEN`)로 간다 — 그 판단은
    부르는 쪽 몫이다."""
    off = store.availability(environ)
    if off is not None:
        return StartLogin("off", off)
    try:
        target = store.target_from_environ(environ)
    except Exception:  # 통합인증 설정을 읽다 깨져도 시작은 지금 길로 간다
        target = None
    if target is None:
        return StartLogin("off", store.REASON_NO_TARGET)
    loaded = store.load(target, store.secret_key(environ))
    stored = loaded.stored
    if stored is None:
        return StartLogin("absent", loaded.reason, loaded.failure_kind)
    store.remember(stored)
    if stored.stopped:
        return StartLogin("stopped", stored.stop_reason or "", stored=stored)
    with _LOGIN_LOCK:
        attempt = _auto_attempt_locked(
            stored, target=target, folder=folder, environ=environ, path="시작"
        )
    result = attempt.result
    if result is None:
        return StartLogin("stopped", attempt.skipped, stored=stored)
    return StartLogin(
        result.outcome, result.reason, result=result, stop_write=attempt.stop_write, stored=stored
    )
