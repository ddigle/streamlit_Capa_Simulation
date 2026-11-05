# Purpose: 통합인증 환경변수를 읽어 모드와 검증된 설정 한 벌(SsoConfig)로 만든다.

"""통합인증 설정.

`load_config` 는 순수 함수다 — 환경변수 사전과 지금 시각만 받아 불변 설정을 돌려준다. 프로세스 상태
(한 번만 읽기 · 비밀값을 `os.environ` 에서 빼기 · 로그)는 `runtime` 이 맡는다.

모드 셋:

- **꺼짐** — `ADFS_CLIENT_ID` 가 비어 있다(그리고 `CAPA_SSO` 가 비었거나 `auto`). 앱은 지금처럼
  열린다. 나머지 값은 「켜면 막힐 문제」(`readiness`)로만 미리 본다. PyJWT 는 import 하지 않는다.
- **켜짐** — client id 가 있고 필수 값이 모두 맞고 의존성이 import 된다.
- **막힘** — client id 가 있는데(또는 `CAPA_SSO=required`) 하나라도 없거나 틀리다, 또는 `CAPA_SSO`
  가 모르는 값이다. 상태 검사만 살리고 앱은 열지 않는다(설정 화면).

접속 명단(`access.py`)은 운영이거나 · 잠금이거나 · 공개 주소가 루프백이 아니거나 · 두 목록 변수
가운데 하나라도 값이 있으면 켜진다. `APP_ENV` 를 빠뜨린 실제 서버가 조용히 전부를 받지 않게 주소도
본다. 켜졌는데 읽은 관리자가 없으면 「켜면 필요한 것」 의 문제다 — 켜짐이면 막힘, 꺼짐이면 켜면 막힐
문제. 잠길 사람을 막으려는 규칙이라 빈 관리자 목록으로 앱을 열지 않는다. 인증된 사람 전부를 받는
것은 그 어느 쪽도 아닌 루프백 개발뿐이다(가짜 IdP · 시험).

S3 명단(`access_store`)은 키(`CAPA_S3_ACCESS_KEY` · `CAPA_S3_SECRET_KEY`)가 하나라도 있으면 켜진다.
그때 명단도 켜지고 `CAPA_ACCESS_USERS` 는 쓰지 않는다(알림). 키 하나 · 주소 · 버킷이 빠지거나 틀려도
막힘이 아니라 알림이다 — 앱은 뜨고 파일을 못 읽은 상태(관리자만 통과)로 선다. 읽기는 여기서 하지
않는다(`load_config` 는 순수 함수다).

화면 · 로그에 실리는 것은 환경변수 **이름과 까닭**뿐이다. 값은 싣지 않는다 — 비밀값은 「짧음」 같은
사실만, 접속 명단은 개수만.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib
import importlib.util
import ipaddress
import re
import types
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from capa_simulation.auth import names
from capa_simulation.auth.access import AccessList, build_access_list
from capa_simulation.io.s3_small import S3Target

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

# `APP_ENV` 해석. 비었거나 개발 값이면 개발, 그 밖은 전부 운영(모르는 값은 엄격한 쪽 + 알림).
PRODUCTION_VALUES = frozenset({"prod", "production"})
DEVELOPMENT_VALUES = frozenset({"", "dev", "development", "local", "test"})
SSO_FLAG_VALUES = frozenset({"", "auto", "required"})

MIN_SECRET_BYTES = 32
MIN_SECRET_DISTINCT = 10
# 짧은 글을 되풀이한 값 — 어떤 주기 p(값 길이의 절반 이하)에서 i 번째 글자가 i-p 번째와 같은 자리가
# 이 몫 이상이면 막는다. 무작위 값(hex · base64)은 한 주기에서 같을 몫이 1/16 안팎이다. 앞
# `SECRET_REPEAT_WINDOW` 글자만 본다(검사가 길이의 제곱이라 아주 긴 값에 기동이 묶이지 않게).
SECRET_REPEAT_SHARE = 0.6
SECRET_REPEAT_WINDOW = 256
# 키보드 줄 · 알파벳 · 숫자 차례(앞뒤 어느 쪽이든, 대소문자 무시)로 이어진 4글자 이상 구간이 값의
# 이 몫 이상을 덮으면 막는다. 무작위 값은 0.16 을 넘지 않았다(hex · base64 표본 각 5천 개).
SECRET_SEQUENCE_SHARE = 0.5
SECRET_SEQUENCE_MIN_RUN = 4
SECRET_SEQUENCES = (
    "abcdefghijklmnopqrstuvwxyz",
    "01234567890",
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
)
# 자리표로 보이는 값. 짧은 낱말(4글자 이하)은 무작위 값에 우연히 들어갈 수 있어 넣지 않는다.
SECRET_PLACEHOLDER_WORDS = (
    "changeme",
    "change_me",
    "change-me",
    "secret",
    "password",
    "example",
    "placeholder",
    "default",
    "dummy",
    "sample",
)
MAX_CLIENT_ID_LENGTH = 200
MAX_URL_LENGTH = 2048
MAX_SIGNING_CERTS = 3
MIN_RSA_BITS = 2048
CERT_WARNING_DAYS = 30
SESSION_HOURS_RANGE = (1, 24)
# 최대 로그인 시간의 위 한계(아래 한계는 세션 시간 — 유휴보다 짧은 최대는 뜻이 없다).
SESSION_MAX_HOURS_LIMIT = 72
_CLAIM_NAME = re.compile(r"^[\x21-\x7e]{1,200}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_PEM_BEGIN = "-----BEGIN CERTIFICATE-----"
_PEM_END = "-----END CERTIFICATE-----"

# 문제 까닭(사람 말). 코드는 로그 · 시험이 본다.
REASONS: Mapping[str, str] = types.MappingProxyType(
    {
        "missing": "값이 없음",
        "too_long": "너무 김",
        "control_chars": "제어문자가 있음",
        "bad_url": "주소 꼴이 아님",
        "not_https": "https 가 아님",
        "http_not_loopback": "http 는 루프백(localhost · 127.0.0.1 · ::1)에서만 받음",
        "has_userinfo": "주소에 사용자 정보(@)가 있음",
        "has_fragment": "주소에 # 이 있음",
        "has_query": "질의(?)를 둘 수 없음",
        "too_short": f"{MIN_SECRET_BYTES}바이트보다 짧음",
        "low_variety": f"서로 다른 글자가 {MIN_SECRET_DISTINCT}개보다 적음",
        "placeholder": "자리표 값으로 보임(changeme · secret 등)",
        "repetitive": "짧은 글을 되풀이한 값으로 보임",
        "sequential": "키보드 줄 · 알파벳 · 숫자 차례가 대부분인 값",
        "same_as_client_id": f"설정값({names.ENV_CLIENT_ID})과 같음",
        "cert_unreadable": "인증서를 읽지 못함",
        "cert_not_rsa": "RSA 공개키가 아님",
        "cert_too_small": f"RSA {MIN_RSA_BITS}비트 미만",
        "too_many": f"인증서는 {MAX_SIGNING_CERTS}개까지",
        "cert_expired": "인증서 만료일이 지남(막지 않음)",
        "cert_expiring": f"인증서 만료가 {CERT_WARNING_DAYS}일 안(막지 않음)",
        "not_integer": "정수가 아님",
        "out_of_range": f"{SESSION_HOURS_RANGE[0]}~{SESSION_HOURS_RANGE[1]} 밖",
        "max_out_of_range": (
            f"세션 시간({names.ENV_SESSION_HOURS}) 이상 {SESSION_MAX_HOURS_LIMIT} 이하가 아님"
        ),
        "unknown_value": "auto · required 가 아님",
        "unknown_app_env": "모르는 값이라 운영(prod)으로 봄",
        "no_openid": "openid 가 없음",
        "bad_claim_name": "클레임 이름 꼴이 아님(빈칸 없는 ASCII 200자)",
        "dependency_missing": "의존성 없음 — pyjwt[crypto] 를 설치해야 함",
        "off_in_production": "운영 서버인데 통합인증이 꺼져 있음",
        "no_valid_entry": "읽을 수 있는 loginid 가 하나도 없음",
        "entries_unreadable": "loginid 꼴이 아닌 항목이 있어 뺌",
        "s3_users_ignored": "S3 명단이 켜져 있어 이 목록은 쓰지 않음",
        "s3_needed": "S3 명단이 켜졌는데 값이 없음 — 관리자만 들어옴",
        "s3_bad": "S3 명단이 켜졌는데 값 꼴이 틀림 — 관리자만 들어옴",
        "s3_plain_http": "평문 http — 명단이 사내망에 그대로 흐름",
    }
)


class SsoMode(Enum):
    OFF = "off"
    ON = "on"
    BROKEN = "broken"


@dataclass(frozen=True)
class SsoProblem:
    """환경변수 하나의 문제. 값은 담지 않는다."""

    env: str
    code: str

    @property
    def reason(self) -> str:
        return REASONS.get(self.code, self.code)

    def log_text(self) -> str:
        return f"{self.env}:{self.code}"


@dataclass(frozen=True)
class SigningCert:
    """토큰 서명 인증서 하나(핀 고정). 공개키와 지문만 — 비밀이 아니다."""

    public_key: RSAPublicKey
    x5t: str
    sha256: str
    not_after: datetime
    key_bits: int

    def days_left(self, now: datetime) -> int:
        return (self.not_after - now).days


@dataclass(frozen=True)
class SsoConfig:
    """검증된 통합인증 설정 한 벌. 기동 때 한 번 만들고 바꾸지 않는다.

    `session_hours` 는 마지막 사용 뒤 유지 시간(유휴 만료 — 앱을 쓰면 갱신 경로가 늘린다),
    `session_max_hours` 는 써도 넘지 못하는 최대 시간(처음 ADFS 로그인에서)이다.
    """

    mode: SsoMode
    prod: bool
    locked: bool
    client_id: str
    authorize_url: str
    issuer: str
    issuer_candidate: str
    signing_certs: tuple[SigningCert, ...]
    public_url: str
    redirect_uri: str
    session_hours: int
    session_max_hours: int
    scope: str
    resource: str
    claim_loginid: str
    claim_username: str
    claim_deptname: str
    logout_url: str
    secure_cookies: bool
    cookie_suffix: str
    problems: tuple[SsoProblem, ...]
    readiness: tuple[SsoProblem, ...]
    notices: tuple[SsoProblem, ...]
    env_presence: Mapping[str, bool]
    # 접속 명단의 환경변수 몫. repr 에는 켜짐과 읽지 못한 수만 나온다(`AccessList` — 명단 값은 repr
    # 이 없다). S3 명단을 얹은 지금 한 벌은 `runtime.current_access` 가 준다.
    access: AccessList
    # S3 명단이 켜졌는가(키가 하나라도 있음)와 닿을 곳 한 벌(값이 다 맞을 때만 — 키는 repr 이 없다).
    access_s3_requested: bool
    access_object_key: str
    access_s3: S3Target | None = field(repr=False, compare=False)
    # 화면 · 로그 · repr 에 나오지 않는다. 세션 · 상태 토큰의 키를 여기서 파생한다(`tokens`).
    secret: bytes = field(repr=False, compare=False)

    @property
    def enabled(self) -> bool:
        return self.mode is SsoMode.ON

    @property
    def session_seconds(self) -> int:
        return self.session_hours * 3600

    @property
    def session_max_seconds(self) -> int:
        return self.session_max_hours * 3600

    def _cookie_prefix(self) -> str:
        return names.HOST_PREFIX if self.secure_cookies else ""

    @property
    def session_cookie(self) -> str:
        return f"{self._cookie_prefix()}{names.SESSION_COOKIE}{self.cookie_suffix}"

    @property
    def attempt_cookie(self) -> str:
        return f"{self._cookie_prefix()}{names.ATTEMPT_COOKIE}{self.cookie_suffix}"

    @property
    def state_cookie_prefix(self) -> str:
        base = names.STATE_COOKIE_PREFIX.rstrip("_")
        return f"{self._cookie_prefix()}{base}{self.cookie_suffix}_"

    def state_cookie(self, state: str) -> str:
        return self.state_cookie_prefix + state[:16]

    @property
    def public_origin(self) -> str:
        return url_origin(self.public_url)


def app_env_is_production(value: str | None) -> bool:
    """`APP_ENV` 가 운영을 뜻하는가. 비었거나 개발 값만 개발이고 모르는 값은 운영으로 본다."""
    return (value or "").strip().lower() not in DEVELOPMENT_VALUES


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    text = host.strip("[]").lower()
    if text == "localhost":
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def url_origin(url: str) -> str:
    """`scheme://host[:port]` — 기본 포트(https 443 · http 80)는 뗀다. 꼴이 아니면 빈 글자."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return ""
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not scheme or not host:
        return ""
    if ":" in host:
        host = f"[{host}]"
    default = {"https": 443, "http": 80}.get(scheme)
    if port is None or port == default:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def _check_url(
    name: str, raw: str, *, prod: bool, allow_query: bool
) -> tuple[str, SsoProblem | None]:
    text = raw.strip()
    if not text:
        return "", SsoProblem(name, "missing")
    if len(text) > MAX_URL_LENGTH:
        return "", SsoProblem(name, "too_long")
    if _CONTROL.search(text) or any(ch.isspace() for ch in text):
        return "", SsoProblem(name, "bad_url")
    try:
        parts = urlsplit(text)
        _ = parts.port  # 포트 꼴이 틀리면 여기서 ValueError
    except ValueError:
        return "", SsoProblem(name, "bad_url")
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        return "", SsoProblem(name, "bad_url")
    if "@" in parts.netloc:
        return "", SsoProblem(name, "has_userinfo")
    if parts.fragment or "#" in text:
        return "", SsoProblem(name, "has_fragment")
    if parts.query and not allow_query:
        return "", SsoProblem(name, "has_query")
    if scheme == "http":
        if prod:
            return "", SsoProblem(name, "not_https")
        if not is_loopback_host(parts.hostname):
            return "", SsoProblem(name, "http_not_loopback")
    return text, None


def _check_client_id(raw: str) -> tuple[str, SsoProblem | None]:
    text = raw.strip()
    if not text:
        return "", None
    if len(text) > MAX_CLIENT_ID_LENGTH:
        return text, SsoProblem(names.ENV_CLIENT_ID, "too_long")
    if _CONTROL.search(text):
        return text, SsoProblem(names.ENV_CLIENT_ID, "control_chars")
    return text, None


def secret_repeats(text: str) -> bool:
    """짧은 글을 되풀이했는가(`SECRET_REPEAT_SHARE`) — `0123456789` × 4 · `Ab3$` × 8 같은 값."""
    text = text[:SECRET_REPEAT_WINDOW]
    size = len(text)
    for period in range(1, size // 2 + 1):
        same = sum(1 for index in range(period, size) if text[index] == text[index - period])
        if same >= SECRET_REPEAT_SHARE * (size - period):
            return True
    return False


def _sequence_pairs() -> tuple[frozenset[tuple[str, str]], ...]:
    """차례마다 · 방향마다 이웃한 두 글자 묶음(앞으로 · 뒤로)."""
    found: list[frozenset[tuple[str, str]]] = []
    for sequence in SECRET_SEQUENCES:
        forward = frozenset(zip(sequence, sequence[1:], strict=False))
        found += [forward, frozenset((right, left) for left, right in forward)]
    return tuple(found)


_SEQUENCE_PAIRS = _sequence_pairs()


def secret_sequence_share(text: str) -> float:
    """한 차례 · 한 방향으로 이어진 `SECRET_SEQUENCE_MIN_RUN` 글자 이상 구간이 덮는 몫.

    차례는 키보드 줄 · 알파벳 · 숫자이고 대소문자는 가리지 않는다.
    """
    lowered = text.lower()
    size = len(lowered)
    covered = [False] * size
    for pairs in _SEQUENCE_PAIRS:
        run_start = 0
        for index in range(1, size + 1):
            if index < size and (lowered[index - 1], lowered[index]) in pairs:
                continue
            if index - run_start >= SECRET_SEQUENCE_MIN_RUN:
                covered[run_start:index] = [True] * (index - run_start)
            run_start = index
    return sum(covered) / size if size else 0.0


def _check_secret(raw: str, client_id: str) -> tuple[bytes, SsoProblem | None]:
    """세션 토큰 비밀값 검사. 이 값을 맞히는 사람은 아무 계정의 세션 토큰이든 만든다.

    길이 · 글자 가짓수 · 자리표 낱말 · 되풀이 · 키보드/알파벳/숫자 차례를 본다. 사람이 고른 낱말
    문장은 가려내지 못한다(문서는 `secrets.token_urlsafe(48)` 을 권한다).
    """
    text = raw.strip()
    if not text:
        return b"", SsoProblem(names.ENV_SECRET, "missing")
    data = text.encode("utf-8")
    if _CONTROL.search(text):
        return b"", SsoProblem(names.ENV_SECRET, "control_chars")
    if len(data) < MIN_SECRET_BYTES:
        return b"", SsoProblem(names.ENV_SECRET, "too_short")
    if client_id and text == client_id:
        return b"", SsoProblem(names.ENV_SECRET, "same_as_client_id")
    if len(set(text)) < MIN_SECRET_DISTINCT:
        return b"", SsoProblem(names.ENV_SECRET, "low_variety")
    lowered = text.lower()
    if any(word in lowered for word in SECRET_PLACEHOLDER_WORDS):
        return b"", SsoProblem(names.ENV_SECRET, "placeholder")
    if secret_repeats(text):
        return b"", SsoProblem(names.ENV_SECRET, "repetitive")
    if secret_sequence_share(text) >= SECRET_SEQUENCE_SHARE:
        return b"", SsoProblem(names.ENV_SECRET, "sequential")
    return data, None


def _check_hours(raw: str) -> tuple[int, SsoProblem | None]:
    text = raw.strip()
    if not text:
        return names.DEFAULT_SESSION_HOURS, None
    if not text.isascii() or not text.isdigit():
        return names.DEFAULT_SESSION_HOURS, SsoProblem(names.ENV_SESSION_HOURS, "not_integer")
    hours = int(text)
    low, high = SESSION_HOURS_RANGE
    if not low <= hours <= high:
        return names.DEFAULT_SESSION_HOURS, SsoProblem(names.ENV_SESSION_HOURS, "out_of_range")
    return hours, None


def _check_max_hours(raw: str, session_hours: int) -> tuple[int, SsoProblem | None]:
    """최대 로그인 시간 — 세션 시간(`_check_hours` 가 돌려준 값) 이상 72 이하.

    틀리면 기본값(24)을 돌려주고 문제를 적는다. 켜짐이면 막힘, 꺼짐이면 「켜면 막힐 문제」 다.
    """
    text = raw.strip()
    default = names.DEFAULT_SESSION_MAX_HOURS
    if not text:
        return default, None
    if not text.isascii() or not text.isdigit():
        return default, SsoProblem(names.ENV_SESSION_MAX_HOURS, "not_integer")
    hours = int(text)
    if not session_hours <= hours <= SESSION_MAX_HOURS_LIMIT:
        return default, SsoProblem(names.ENV_SESSION_MAX_HOURS, "max_out_of_range")
    return hours, None


def _check_scope(raw: str) -> tuple[str, SsoProblem | None]:
    text = " ".join(raw.split()) or names.DEFAULT_SCOPE
    if len(text) > 500:
        return names.DEFAULT_SCOPE, SsoProblem(names.ENV_SCOPE, "too_long")
    if _CONTROL.search(text) or not text.isascii():
        return names.DEFAULT_SCOPE, SsoProblem(names.ENV_SCOPE, "control_chars")
    if "openid" not in text.split(" "):
        return names.DEFAULT_SCOPE, SsoProblem(names.ENV_SCOPE, "no_openid")
    return text, None


def _check_plain(name: str, raw: str) -> tuple[str, SsoProblem | None]:
    text = raw.strip()
    if len(text) > 500:
        return "", SsoProblem(name, "too_long")
    if _CONTROL.search(text):
        return "", SsoProblem(name, "control_chars")
    return text, None


def _check_claim_name(name: str, raw: str, default: str) -> tuple[str, SsoProblem | None]:
    text = raw.strip()
    if not text:
        return default, None
    if not _CLAIM_NAME.match(text):
        return default, SsoProblem(name, "bad_claim_name")
    return text, None


def _beyond_loopback(public_url: str) -> bool:
    """검증을 지난 공개 주소가 이 PC 밖에서 열리는가. 주소가 없으면(꺼짐 · 주소 문제) 거짓이다."""
    return bool(public_url) and not is_loopback_host(urlsplit(public_url).hostname)


def _check_access(
    admins: str, users: str, *, required: bool, contact: str, s3_requested: bool
) -> tuple[AccessList, SsoProblem | None, list[SsoProblem]]:
    """접속 명단 `(명단, 문제, 알림)`. `required` 거나 두 목록 가운데 하나라도 값이 있거나 S3 명단이
    켜졌으면 켜진다.

    켜졌는데 읽은 관리자가 없으면 문제다 — 명단에 사람이 있어도 고칠 사람이 없는 앱을 열지 않는다.
    읽지 못한 항목은 막지 않는다 — 오타 하나로 모두가 잠기지 않게. 그 사람만 거절 화면을 본다. S3
    명단이 켜졌으면 사용자 목록은 쓰지 않고 알린다(한 사람을 두 곳에서 고치지 않게).
    """
    ignored = s3_requested and bool(users.strip())
    if s3_requested:
        users = ""
    enforced = required or s3_requested or bool(admins.strip()) or bool(users.strip())
    access = build_access_list(admins, users, enforced=enforced, contact=contact)
    notices = [SsoProblem(names.ENV_ACCESS_USERS, "s3_users_ignored")] if ignored else []
    notices += [
        SsoProblem(name, "entries_unreadable")
        for name, count in (
            (names.ENV_ACCESS_ADMINS, access.unreadable_admins),
            (names.ENV_ACCESS_USERS, access.unreadable_users),
        )
        if count
    ]
    if not enforced or access.admin_count:
        return access, None, notices
    code = "no_valid_entry" if admins.strip() else "missing"
    return access, SsoProblem(names.ENV_ACCESS_ADMINS, code), notices


def _check_s3_endpoint(raw: str) -> tuple[str, SsoProblem | None, SsoProblem | None]:
    """S3 주소 `(값, 문제, 알림)`. 이 주소만 운영에서도 http 를 받는다 — 저장소가 평문 포트다."""
    name = names.ENV_S3_ENDPOINT
    text = raw.strip().rstrip("/")
    if not text:
        return "", SsoProblem(name, "s3_needed"), None
    bad = SsoProblem(name, "s3_bad")
    # 비 ASCII 호스트는 `Host` 머리에 실리지 못한다 — punycode 로 적는다.
    if (
        len(text) > MAX_URL_LENGTH
        or not text.isascii()
        or _CONTROL.search(text)
        or any(ch.isspace() for ch in text)
    ):
        return "", bad, None
    try:
        parts = urlsplit(text)
        _ = parts.port
    except ValueError:
        return "", bad, None
    scheme = parts.scheme.lower()
    if (
        scheme not in ("http", "https")
        or not parts.hostname
        or "@" in parts.netloc
        or parts.path
        or parts.query
        or parts.fragment
    ):
        return "", bad, None
    plain = scheme == "http" and not is_loopback_host(parts.hostname)
    return text, None, SsoProblem(name, "s3_plain_http") if plain else None


def _check_s3_name(name: str, raw: str, *, default: str = "") -> tuple[str, SsoProblem | None]:
    """버킷 · 영역 · 객체 키 한 값. 비면 `default`(없으면 값 없음)다."""
    text = raw.strip() or default
    if not text:
        return "", SsoProblem(name, "s3_needed")
    if len(text) > 512 or _CONTROL.search(text) or text.startswith("/"):
        return "", SsoProblem(name, "s3_bad")
    return text, None


def _check_s3_header_value(name: str, text: str) -> SsoProblem | None:
    """키 · 영역 한 값 — 서명과 머리에 그대로 들어가므로 빈칸 없는 ASCII 만 받는다."""
    if not text:
        return SsoProblem(name, "s3_needed")
    if not text.isascii() or _CONTROL.search(text) or any(ch.isspace() for ch in text):
        return SsoProblem(name, "s3_bad")
    return None


def _check_access_s3(
    value: Callable[[str], str],
) -> tuple[bool, str, S3Target | None, list[SsoProblem]]:
    """S3 명단 `(켜짐, 객체 키, 닿을 곳, 알림)`. 값이 빠지거나 틀려도 막지 않는다(모듈 설명)."""
    access_key = value(names.ENV_S3_ACCESS_KEY).strip()
    secret_key = value(names.ENV_S3_SECRET_KEY).strip()
    object_key, object_problem = _check_s3_name(
        names.ENV_ACCESS_OBJECT, value(names.ENV_ACCESS_OBJECT), default=names.DEFAULT_ACCESS_OBJECT
    )
    if not access_key and not secret_key:
        return False, object_key, None, []
    endpoint, endpoint_problem, endpoint_notice = _check_s3_endpoint(value(names.ENV_S3_ENDPOINT))
    bucket, bucket_problem = _check_s3_name(names.ENV_S3_BUCKET, value(names.ENV_S3_BUCKET))
    region, region_problem = _check_s3_name(
        names.ENV_S3_REGION, value(names.ENV_S3_REGION), default=names.DEFAULT_S3_REGION
    )
    problems = [
        problem
        for problem in (
            _check_s3_header_value(names.ENV_S3_ACCESS_KEY, access_key),
            _check_s3_header_value(names.ENV_S3_SECRET_KEY, secret_key),
            endpoint_problem,
            bucket_problem,
            region_problem or _check_s3_header_value(names.ENV_S3_REGION, region),
            object_problem,
        )
        if problem is not None
    ]
    notices = [*problems, *([endpoint_notice] if endpoint_notice else [])]
    if problems:
        return True, object_key, None, notices
    target = S3Target(
        endpoint_url=endpoint,
        bucket=bucket,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
    )
    return True, object_key, target, notices


def _cert_der_values(raw: str) -> list[bytes | None]:
    """한 줄 값을 인증서 DER 목록으로. 읽지 못한 칸은 None.

    받는 꼴 셋: base64(DER) · base64(PEM 원문) · PEM 원문(한 줄로 붙였어도 된다). 여럿은 쉼표로
    잇는다.
    """
    values: list[bytes | None] = []
    for item in raw.split(","):
        text = item.strip()
        if not text:
            continue
        if text.startswith(_PEM_BEGIN):
            values.append(_pem_to_der(text))
            continue
        try:
            decoded = base64.b64decode("".join(text.split()), validate=True)
        except (binascii.Error, ValueError):
            values.append(None)
            continue
        if decoded.lstrip().startswith(_PEM_BEGIN.encode("ascii")):
            try:
                values.append(_pem_to_der(decoded.decode("ascii")))
            except UnicodeDecodeError:
                values.append(None)
            continue
        values.append(decoded)
    return values


def _pem_to_der(text: str) -> bytes | None:
    body = text.strip()
    if not body.startswith(_PEM_BEGIN) or _PEM_END not in body:
        return None
    inner = body[len(_PEM_BEGIN) : body.index(_PEM_END)]
    # 한 줄로 붙인 PEM 은 줄바꿈 자리에 `\n` 글자가 남는 일이 있다.
    inner = inner.replace("\\n", "").replace("\\r", "")
    try:
        return base64.b64decode("".join(inner.split()), validate=True)
    except (binascii.Error, ValueError):
        return None


def x5t_of(der: bytes) -> str:
    """ADFS 헤더 `x5t` 와 같은 꼴 — SHA-1(DER) 의 base64url(채움 없음)."""
    digest = hashlib.sha1(der, usedforsecurity=False).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def parse_signing_certs(
    raw: str, *, now: datetime
) -> tuple[tuple[SigningCert, ...], list[SsoProblem], list[SsoProblem]]:
    """(인증서들, 문제, 알림). 체인은 검증하지 않는다 — 핀 고정이 신뢰 기준이다."""
    name = names.ENV_SIGNING_CERT
    if not raw.strip():
        return (), [SsoProblem(name, "missing")], []
    ders = _cert_der_values(raw)
    if not ders:
        return (), [SsoProblem(name, "missing")], []
    if len(ders) > MAX_SIGNING_CERTS:
        return (), [SsoProblem(name, "too_many")], []
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
    except ImportError:
        return (), [SsoProblem(names.ENV_SIGNING_CERT, "dependency_missing")], []
    certs: list[SigningCert] = []
    problems: list[SsoProblem] = []
    notices: list[SsoProblem] = []
    for der in ders:
        if der is None:
            problems.append(SsoProblem(name, "cert_unreadable"))
            continue
        try:
            cert = x509.load_der_x509_certificate(der)
            public_key = cert.public_key()
        except ValueError:
            problems.append(SsoProblem(name, "cert_unreadable"))
            continue
        if not isinstance(public_key, RSAPublicKey):
            problems.append(SsoProblem(name, "cert_not_rsa"))
            continue
        if public_key.key_size < MIN_RSA_BITS:
            problems.append(SsoProblem(name, "cert_too_small"))
            continue
        not_after = cert.not_valid_after_utc
        certs.append(
            SigningCert(
                public_key=public_key,
                x5t=x5t_of(der),
                sha256=hashlib.sha256(der).hexdigest(),
                not_after=not_after,
                key_bits=public_key.key_size,
            )
        )
        if not_after <= now:
            notices.append(SsoProblem(name, "cert_expired"))
        elif not_after - now <= timedelta(days=CERT_WARNING_DAYS):
            notices.append(SsoProblem(name, "cert_expiring"))
    # 같은 까닭이 여럿이면 한 번만 적는다.
    return tuple(certs), list(dict.fromkeys(problems)), list(dict.fromkeys(notices))


def _dependency_problem(*, import_now: bool) -> SsoProblem | None:
    """PyJWT(와 cryptography)가 있는가. 꺼짐에서는 찾기만 하고 import 하지 않는다."""
    if import_now:
        try:
            importlib.import_module("jwt")
            importlib.import_module("cryptography.x509")
        except ImportError:
            return SsoProblem("pyjwt", "dependency_missing")
        return None
    if importlib.util.find_spec("jwt") is None or importlib.util.find_spec("cryptography") is None:
        return SsoProblem("pyjwt", "dependency_missing")
    return None


def _ordered(problems: list[SsoProblem]) -> tuple[SsoProblem, ...]:
    order = {name: index for index, name in enumerate(names.SSO_ENVIRONMENT)}
    unique = list(dict.fromkeys(problems))
    return tuple(sorted(unique, key=lambda item: order.get(item.env, len(order))))


def load_config(environ: Mapping[str, str], *, now: datetime | None = None) -> SsoConfig:
    """환경변수 → 설정 한 벌. 부수 효과가 없다(비밀값을 빼는 것은 `runtime.start`)."""
    moment = now or datetime.now(timezone.utc)

    def value(name: str) -> str:
        return environ.get(name, "") or ""

    app_env = value(names.ENV_APP_ENV).strip().lower()
    prod = app_env_is_production(app_env)
    notices: list[SsoProblem] = []
    if app_env not in PRODUCTION_VALUES | DEVELOPMENT_VALUES:
        notices.append(SsoProblem(names.ENV_APP_ENV, "unknown_app_env"))

    flag = value(names.ENV_SSO).strip().lower()
    flag_problem = None if flag in SSO_FLAG_VALUES else SsoProblem(names.ENV_SSO, "unknown_value")
    locked = flag == "required"

    client_id, client_problem = _check_client_id(value(names.ENV_CLIENT_ID))
    secret, secret_problem = _check_secret(value(names.ENV_SECRET), client_id)
    authorize_url, authorize_problem = _check_url(
        names.ENV_AUTHORIZE_URL, value(names.ENV_AUTHORIZE_URL), prod=prod, allow_query=True
    )
    issuer, issuer_problem = _check_url(
        names.ENV_ISSUER, value(names.ENV_ISSUER), prod=prod, allow_query=False
    )
    public_url, public_problem = _check_url(
        names.ENV_PUBLIC_URL, value(names.ENV_PUBLIC_URL), prod=prod, allow_query=False
    )
    public_url = public_url.rstrip("/")
    hours, hours_problem = _check_hours(value(names.ENV_SESSION_HOURS))
    max_hours, max_hours_problem = _check_max_hours(value(names.ENV_SESSION_MAX_HOURS), hours)
    scope, scope_problem = _check_scope(value(names.ENV_SCOPE))
    resource, resource_problem = _check_plain(names.ENV_RESOURCE, value(names.ENV_RESOURCE))
    claim_loginid, loginid_problem = _check_claim_name(
        names.ENV_CLAIM_LOGINID, value(names.ENV_CLAIM_LOGINID), names.DEFAULT_CLAIM_LOGINID
    )
    claim_username, username_problem = _check_claim_name(
        names.ENV_CLAIM_USERNAME, value(names.ENV_CLAIM_USERNAME), names.DEFAULT_CLAIM_USERNAME
    )
    claim_deptname, deptname_problem = _check_claim_name(
        names.ENV_CLAIM_DEPTNAME, value(names.ENV_CLAIM_DEPTNAME), names.DEFAULT_CLAIM_DEPTNAME
    )
    logout_url = ""
    logout_problem: SsoProblem | None = None
    if value(names.ENV_LOGOUT_URL).strip():
        logout_url, logout_problem = _check_url(
            names.ENV_LOGOUT_URL, value(names.ENV_LOGOUT_URL), prod=prod, allow_query=True
        )
    certs: tuple[SigningCert, ...] = ()
    cert_problems: list[SsoProblem] = []
    if value(names.ENV_SIGNING_CERT).strip():
        certs, cert_problems, cert_notices = parse_signing_certs(
            value(names.ENV_SIGNING_CERT), now=moment
        )
        notices.extend(cert_notices)
    else:
        cert_problems = [SsoProblem(names.ENV_SIGNING_CERT, "missing")]
    contact, contact_problem = _check_plain(
        names.ENV_ACCESS_CONTACT, value(names.ENV_ACCESS_CONTACT)
    )
    if contact_problem is not None:
        notices.append(contact_problem)
    s3_requested, object_key, s3_target, s3_notices = _check_access_s3(value)
    notices.extend(s3_notices)
    access, access_problem, access_notices = _check_access(
        value(names.ENV_ACCESS_ADMINS),
        value(names.ENV_ACCESS_USERS),
        required=prod or locked or _beyond_loopback(public_url),
        contact=contact,
        s3_requested=s3_requested,
    )
    notices.extend(access_notices)

    # client id 를 뺀 「켜면 필요한 것」 의 문제. 꺼짐에서는 readiness, 켜려 할 때는 problems 가
    # 된다.
    checks = [
        problem
        for problem in (
            secret_problem,
            authorize_problem,
            issuer_problem,
            public_problem,
            hours_problem,
            max_hours_problem,
            scope_problem,
            resource_problem,
            loginid_problem,
            username_problem,
            deptname_problem,
            logout_problem,
            access_problem,
        )
        if problem is not None
    ]
    checks.extend(cert_problems)

    wants_on = bool(client_id) or locked or flag_problem is not None
    dependency = _dependency_problem(import_now=wants_on)
    if dependency is not None:
        checks.append(dependency)

    problems: list[SsoProblem] = []
    readiness: list[SsoProblem] = []
    if wants_on:
        if flag_problem is not None:
            problems.append(flag_problem)
        if client_problem is not None:
            problems.append(client_problem)
        if not client_id:
            problems.append(SsoProblem(names.ENV_CLIENT_ID, "missing"))
        problems.extend(checks)
        mode = SsoMode.BROKEN if problems else SsoMode.ON
    else:
        readiness.extend(checks)
        mode = SsoMode.OFF
        if prod:
            notices.append(SsoProblem(names.ENV_CLIENT_ID, "off_in_production"))

    issuer_candidate = ""
    if authorize_url:
        host = urlsplit(authorize_url).netloc
        issuer_candidate = f"https://{host}/adfs"
    public_path = urlsplit(public_url).path if public_url else ""
    cookie_suffix = ""
    if public_path:
        cookie_suffix = "_" + hashlib.sha256(public_path.encode("utf-8")).hexdigest()[:8]
    secure_cookies = public_url.lower().startswith("https://") if public_url else prod

    return SsoConfig(
        mode=mode,
        prod=prod,
        locked=locked,
        client_id=client_id,
        authorize_url=authorize_url,
        issuer=issuer,
        issuer_candidate=issuer_candidate,
        signing_certs=certs,
        public_url=public_url,
        redirect_uri=f"{public_url}{names.CALLBACK_PATH}" if public_url else "",
        session_hours=hours,
        session_max_hours=max_hours,
        scope=scope,
        resource=resource,
        claim_loginid=claim_loginid,
        claim_username=claim_username,
        claim_deptname=claim_deptname,
        logout_url=logout_url,
        secure_cookies=secure_cookies,
        cookie_suffix=cookie_suffix,
        problems=_ordered(problems),
        readiness=_ordered(readiness),
        notices=_ordered(notices),
        env_presence=types.MappingProxyType(
            {name: bool(value(name).strip()) for name in names.SSO_ENVIRONMENT}
        ),
        access=access,
        access_s3_requested=s3_requested,
        access_object_key=object_key,
        access_s3=s3_target,
        secret=secret,
    )
