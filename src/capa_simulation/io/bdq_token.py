# Purpose: BigDataQuery 로그인 토큰 파일 자리 · 쓰기 · 넣기 판정 · 만료 읽기를 한 곳에 둔다.

"""BigDataQuery 로그인 토큰 파일.

패키지(`bdq.login()` · `getData()`)는 조회마다 토큰을 다시 읽는다 — 프로세스 환경변수
`BIGDATAQUERY_LOGIN_TOKEN` 이 있으면 그것을, 없으면
`/config/.credential/bigdataquery.token.<계정>` 파일을(2026-11-12 담당자 답). C-DEP CD 시작
스크립트(`scripts/container_start.py`)가 CD 환경변수 `CAPA_BDQ_TOKEN` 을 그 파일로 쓰고,
Admin 「토큰 넣기」(`components/bdq_token_admin.py`)가 관리자가 넣은 토큰을 같은 파일로
쓴다 — 쓰는 길은 이 모듈 하나다. 다음 조회부터 패키지가 새 파일을 읽는다.

**자리마다.** C-DEP 컨테이너의 디스크는 다시 띄우면 처음으로 돌아가고, 시작 스크립트가
그때마다 CD 환경변수 값으로 파일을 다시 쓴다 — Admin 에서 넣은 토큰은 다음 CI/CD ·
재시작까지만 남는다. WebIDE 는 `bdq.login()` 이 같은 파일을 쓰고, 사내 PC(Windows)는
패키지가 Windows 로그인으로 찾는다 — 둘 다 통합인증이 꺼져 Admin 「토큰 넣기」 가 서지
않는다. 토큰을 `data/` 아래에 두지 않는다 — `managed` 서버는 `data/` 를 버킷으로 올린다.

**비밀.** 토큰 글자와 그 길이(비밀에서 나온 수)를 어떤 글(까닭 · 예외 · 로그)에도 싣지
않는다. 쓰기는 같은 폴더의 임시 파일에 다 쓴 뒤 바꿔 끼워 반쯤 쓴 토큰을 남기지 않고,
파일은 0600 · 폴더는 0700 이다. 만료 시각만 기억하고(`_EXPIRY_MEMO` — 파일의 수정 시각 ·
크기가 열쇠) 토큰 글은 붙들지 않는다.

**만료 시각.** 토큰의 꼴을 아직 모른다(WebIDE 실측 35바이트 — 점 셋 JWT 는 아니다). 지금
읽는 꼴은 JWT 의 `exp` 하나뿐이고 그 밖은 「모름」 이다 — 실제 토큰의 꼴은 사내 확인
거리다(`docs/TODO.md`). 모르면 만료 전 알림이 서지 않고, 조회 실패 알림(`AD-10`)이
뒷벽이다.

시작 스크립트가 앱 의존성보다 먼저 읽으므로 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import stat
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Literal

from capa_simulation.io.container_start_report import BDQ_USER_NAME_ENV

# 패키지(`bdq.login()`·`getData()`)가 토큰을 찾는 자리. 패키지가 이 자리만 보므로 옮기지
# 않는다. 시험은 이 이름을 바꿔 끼운다 — 부를 때마다 읽는다(`credential_dir`).
CREDENTIAL_DIR = Path("/config/.credential")
TOKEN_FILE_PREFIX: Final = "bigdataquery.token."
# 이보다 짧은 토큰 값(푼 내용, 앞뒤 공백 뺌)은 토큰이 아닌 값으로 보고 쓰지 않는다. 사내 실제 토큰의
# 바이트 수를 아직 모르니 진짜 토큰을 막지 않는 쪽으로 낮게 둔다: 발급 토큰은 128비트 난수만 담아도
# 16바이트 아래로 내려가지 않는다. 자리표시 · 잘못 붙인 몇 글자만 걸린다.
MIN_TOKEN_BYTES: Final = 16
# 패키지가 파일보다 먼저 읽는 환경변수(2026-11-12 담당자 답). 이 앱은 쓰지 않고, 프로세스에 있으면
# 파일에 넣어도 패키지가 보지 않는다.
LOGIN_TOKEN_ENV: Final = "BIGDATAQUERY_LOGIN_TOKEN"
BASE64_PREFIX: Final = "base64:"
# 만료 전 관리자 알림을 세우는 앞당김(2026-11-12 사용자 결정 「만료 1시간 전」).
EXPIRY_WARNING_SECONDS: Final = 3600

_WRITE_LOCK: Final = threading.Lock()


def credential_dir() -> Path:
    """토큰 폴더. 부를 때마다 모듈 이름을 읽는다 — 시험이 tmp 로 옮긴다."""
    return CREDENTIAL_DIR


def decode_token(value: str) -> bytes:
    """`base64:` 로 시작하면 풀고, 아니면 글자 그대로. 풀 수 없으면 `ValueError`."""
    if not value.startswith(BASE64_PREFIX):
        return value.encode("utf-8")
    body = "".join(value.removeprefix(BASE64_PREFIX).split())
    try:
        return base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("base64 값이 아니다") from error


def token_file_path(folder: Path, account: str) -> Path | None:
    """계정 이름이 폴더 밖을 가리키면(`/`·`..`) `None`."""
    if not account or account in (".", "..") or "/" in account or "\\" in account:
        return None
    return folder / f"{TOKEN_FILE_PREFIX}{account}"


def tighten(path: Path, mode: int) -> None:
    """권한이 `mode` 와 다르면(그룹·다른 사람이 읽을 수 있는 0644 등) `mode` 로 맞춘다."""
    if stat.S_IMODE(path.stat().st_mode) != mode:
        os.chmod(path, mode)


def tighten_folder(folder: Path) -> None:
    """이미 있던 토큰 폴더도 0700 으로 좁힌다(`mkdir` 의 mode 는 새로 만들 때만 먹는다). 남의
    폴더라 못 좁혀도 토큰 파일은 0600 이라 실패로 보지 않는다."""
    try:
        tighten(folder, 0o700)
    except OSError:
        pass


def write_private(target: Path, content: bytes) -> None:
    """0600 파일로 쓴다. 같은 폴더의 임시 파일에 다 쓴 뒤 바꿔 끼워 반쯤 쓴 토큰을 남기지 않는다.
    임시 파일 이름에 프로세스 · 스레드를 실어 한 앱의 두 세션이 겹쳐 써도 서로의 임시 파일을 덮지
    않는다."""
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tighten_folder(target.parent)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def holds_same(target: Path, content: bytes) -> bool:
    """`target` 이 이미 `content` 그대로인가. 읽지 못하면 아니다."""
    try:
        return target.is_file() and target.read_bytes() == content
    except OSError:
        return False


# --- Admin 「토큰 넣기」 ------------------------------------------------------------

InstallStatus = Literal["written", "same", "refused"]


@dataclass(frozen=True)
class InstallOutcome:
    """넣기 한 번의 결과. `reason` 은 거절 까닭이고 토큰 글 · 길이를 싣지 않는다."""

    status: InstallStatus
    reason: str = ""


def blocked_reason(environ: Mapping[str, str] | None = None) -> str | None:
    """이 프로세스에서 넣기를 할 수 없는 까닭(값을 보기 전에 정해지는 것). 할 수 있으면 `None`."""
    env = os.environ if environ is None else environ
    if env.get(LOGIN_TOKEN_ENV, "").strip():
        return (
            f"환경변수 {LOGIN_TOKEN_ENV} 가 있어 패키지가 토큰 파일보다 그 값을 먼저 읽습니다 — "
            "CD 환경변수 표에서 그 key 를 빼야 넣은 토큰이 쓰입니다"
        )
    account = env.get(BDQ_USER_NAME_ENV, "").strip()
    if not account:
        return f"{BDQ_USER_NAME_ENV} 가 없어 토큰 파일 이름을 정할 수 없습니다"
    if token_file_path(credential_dir(), account) is None:
        return f"{BDQ_USER_NAME_ENV} 에 파일 이름으로 못 쓰는 글자가 있습니다"
    return None


def install_token(raw: str, environ: Mapping[str, str] | None = None) -> InstallOutcome:
    """관리자가 넣은 토큰을 패키지가 다음 조회부터 읽는 파일로 쓴다. 같은 내용이면 쓰지 않는다.

    `base64:` 로 시작하면 CD 환경변수 값과 같이 풀어서 쓴다. 비었거나 `MIN_TOKEN_BYTES` 보다 짧으면
    쓰지 않는다(길이는 알리지 않는다). 쓰기 실패는 예외 종류 이름만 싣는다.
    """
    blocked = blocked_reason(environ)
    if blocked is not None:
        return InstallOutcome("refused", blocked)
    value = raw.strip()
    if not value:
        return InstallOutcome("refused", "토큰이 비었습니다")
    try:
        content = decode_token(value)
    except ValueError:
        return InstallOutcome("refused", f"{BASE64_PREFIX} 값을 풀지 못했습니다")
    if not content.strip():
        return InstallOutcome("refused", "푼 내용이 비었습니다")
    if len(content.strip()) < MIN_TOKEN_BYTES:
        return InstallOutcome(
            "refused", f"{MIN_TOKEN_BYTES}바이트보다 짧아 토큰이 아닌 값으로 봅니다"
        )
    env = os.environ if environ is None else environ
    target = token_file_path(credential_dir(), env.get(BDQ_USER_NAME_ENV, "").strip())
    if target is None:  # blocked_reason 이 먼저 거른다 — 타입을 좁힌다
        return InstallOutcome("refused", f"{BDQ_USER_NAME_ENV} 를 읽지 못했습니다")
    with _WRITE_LOCK:
        if holds_same(target, content):
            return InstallOutcome("same")
        try:
            write_private(target, content)
        except OSError as error:
            return InstallOutcome("refused", f"토큰 파일을 쓰지 못했습니다({type(error).__name__})")
    return InstallOutcome("written")


# --- 지금 토큰 · 만료 ---------------------------------------------------------------

TokenSource = Literal["environment", "file", "missing", "unknown"]


@dataclass(frozen=True)
class TokenState:
    """패키지가 다음 조회에 읽을 토큰의 바깥 사실 — 어디서 · 언제 바뀜 · 만료. 토큰 글은 없다.

    `source` — `environment`(프로세스 `BIGDATAQUERY_LOGIN_TOKEN`) · `file`(토큰 파일) ·
    `missing`(파일 없음) · `unknown`(계정을 몰라 파일 이름을 못 정함 · 읽지 못함)."""

    source: TokenSource
    modified_at: datetime | None = None
    expires_at: datetime | None = None


# 파일 (자리, 수정 시각 ns, 크기) → 만료 시각. 한 칸만 둔다 — 파일이 바뀌면 열쇠가 바뀐다.
_EXPIRY_MEMO: dict[tuple[str, int, int], datetime | None] = {}
_EXPIRY_LOCK: Final = threading.Lock()


def _base64url(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def token_expiry(content: bytes) -> datetime | None:
    """토큰에서 읽은 만료 시각(UTC). 지금 아는 꼴은 JWT(`머리.몸.서명`)의 `exp`(초) 하나다 — 그 밖은
    `None`(모름). 꼴을 짐작해 늘리지 않는다 — 실제 꼴은 사내 확인 거리다(모듈 설명)."""
    try:
        text = content.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    parts = text.split(".")
    if len(parts) != 3 or not all(parts):
        return None
    try:
        claims = json.loads(_base64url(parts[1]))
    except (binascii.Error, ValueError):
        return None
    expires = claims.get("exp") if isinstance(claims, dict) else None
    if isinstance(expires, bool) or not isinstance(expires, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(expires, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _file_expiry(target: Path, info: os.stat_result) -> datetime | None:
    key = (str(target), info.st_mtime_ns, info.st_size)
    with _EXPIRY_LOCK:
        if key in _EXPIRY_MEMO:
            return _EXPIRY_MEMO[key]
    try:
        expires = token_expiry(target.read_bytes())
    except OSError:
        expires = None
    with _EXPIRY_LOCK:
        _EXPIRY_MEMO.clear()
        _EXPIRY_MEMO[key] = expires
    return expires


def current_token(environ: Mapping[str, str] | None = None) -> TokenState:
    """패키지가 다음 조회에 읽을 토큰의 상태. 회차마다 불러도 된다 — 파일은 수정 시각 · 크기가 바뀔
    때만 다시 읽는다."""
    env = os.environ if environ is None else environ
    value = env.get(LOGIN_TOKEN_ENV, "").strip()
    if value:
        return TokenState("environment", expires_at=token_expiry(value.encode("utf-8")))
    target = token_file_path(credential_dir(), env.get(BDQ_USER_NAME_ENV, "").strip())
    if target is None:
        return TokenState("unknown")
    try:
        info = target.stat()
    except FileNotFoundError:
        return TokenState("missing")
    except OSError:
        return TokenState("unknown")
    if not stat.S_ISREG(info.st_mode):
        return TokenState("unknown")
    modified = datetime.fromtimestamp(info.st_mtime, tz=timezone.utc)
    return TokenState("file", modified_at=modified, expires_at=_file_expiry(target, info))


def expiry_is_near(state: TokenState, now: datetime | None = None) -> bool:
    """만료 시각을 알고, 지금이 그 `EXPIRY_WARNING_SECONDS` 앞 이후인가(지난 것 포함)."""
    if state.expires_at is None:
        return False
    moment = datetime.now(timezone.utc) if now is None else now
    return (state.expires_at - moment).total_seconds() <= EXPIRY_WARNING_SECONDS


def forget_expiry_memo() -> None:
    """시험 전용 — 기억한 만료 시각을 지운다."""
    with _EXPIRY_LOCK:
        _EXPIRY_MEMO.clear()
