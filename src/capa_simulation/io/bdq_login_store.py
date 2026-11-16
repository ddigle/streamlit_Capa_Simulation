# Purpose: BigDataQuery 자동 로그인 계정을 S3 객체 하나에 암호화해 두고 읽고 · 쓰고 · 지운다.

"""BigDataQuery 자동 로그인 계정 — 저장 객체 한 곳.

C-DEP(동기화 모드 `managed`)에서 BDQ 토큰이 죽으면 앱이 저장된 계정으로 스스로 다시 로그인한다
(`io/bdq_login.py`). 계정은 Admin Area 관리자 폼에서만 들어오고(CD 환경변수에 비밀번호를 두지
않는다) 이 모듈이 버킷 객체 하나(`OBJECT_KEY`)에 둔다 — 재시작 뒤에도 남고, 바꾸는 길은 폼에서 다시
넣기와 지우기뿐이다.

**켜짐.** 동기화 모드가 `managed` 이고 CD 환경변수 `CAPA_BDQ_SECRET_KEY`(cryptography Fernet 키)의
꼴이 맞을 때만 선다(`availability`). 키는 앱 프로세스가 저장 · 다시 로그인에 쓰므로 시작 스크립트가
앱에 넘기고, 앱은 기동 때 쥔 뒤 환경에서 뺀다(`take_secret_key`). 하위 프로세스에는 넘기지 않는다
(`io/bdq_login.child_environment` · 시작 스크립트의 하위 프로세스 환경). 키가 없으면 S3 에 한 번도
묻지 않는다.

**객체 꼴.** JSON 한 벌 — `v`(판 1) · `cipher`(계정 · 비밀번호 JSON 을 Fernet 으로 감싼 글) ·
`entered_by`(넣은 관리자 앱 로그인 ID 앞 두 글자) · `entered_at`(KST ISO) · `state`(`ok` ·
`stopped`) · `stop_reason`(짧은 영문 코드) · `stopped_at` · `misses`(성공 없이 이어진 자동 시도
가운데 닿지 못함 · 확인 못 함의 수 — 재시작을 건너 센다, 없으면 0). 멈춤 표시 · 시도 표시 · 시도
결과는 `cipher` 를 손대지 않고 메타만 고쳐 다시 쓴다(`mark_stopped` · `mark_attempting` ·
`record_outcome` — 키 없이도 된다). 자동 시도는 로그인 **앞에** 객체를 멈춤(`stop_reason`
`attempting`)으로 써 두고 결과로 고쳐 쓴다 — 결과를 적지 못하거나 프로세스가 도중에 끊기면 다음
시작이 멈춤으로 읽어 다시 로그인하지 않는다(안전한 쪽으로 닫힘). 객체는 세대(`generations/`) ·
스냅샷 · 접속 명단(`access/`) · 모듈 데이터(`modules/`) 밖의 `secrets/` 아래다 — 동기화 정리 · 이관
도구는 그 접두를 보지 않는다.

**「저장된 계정 없음」.** 키가 없거나 꼴이 틀리거나 · 객체가 없거나 · 깨졌거나 · 판이 다르거나 ·
키가 맞지 않아 풀리지 않으면 모두 없음이다 — 죽지도 멈추지도 않고 지금 길(`CAPA_BDQ_TOKEN`)로
간다. S3 를 읽지 못한 것(`REASON_UNREAD`)도 계정은 없음이지만 기억하지 않고 잠시 뒤 다시 읽는다.

**비밀.** 풀린 계정 · 비밀번호(`LoginSecret`)와 `cipher` 는 repr · str 에 나오지 않는다. 풀기 ·
읽기의 실패는 예외로 올리지 않고 까닭 코드만 돌려준다 — `json.JSONDecodeError` 의 `.doc` 은 풀린
글 전체를 든다. 로그 · 결과에 계정 · 비밀번호 · 키를 싣지 않는다.

**프로세스 기억.** 조회마다 묻는 계정 원천(`effective_account`)이 S3 에 가지 않게, 앱 프로세스는 한
번 읽은 결과를 기억하고(`current` · `load_state`) 저장 · 지우기 · 멈춤 표시가 그 기억을 바꾼다.
기억 잠금은 S3 를 기다리며 쥐지 않는다 — S3 읽기는 따로 한 번에 하나만 돌고(그동안 다른 부름은 옛
기억을 받는다 — 처음 읽기만 기다린다), 읽는 동안 기억이 바뀌었으면(세대 수) 읽은 결과를 버린다.
그래서 화면 회차마다 도는 `peek_*` 는 S3 가 느리거나 끊겨도 멎지 않는다. 시험은 `forget_state` 로
비운다. Streamlit 을 부르지 않는다 — 공식버전 자동 갱신 스레드의
조회도 이 길을 지난다.

무거운 의존성(cryptography · 설정 읽기 · 통합인증 설정)은 함수 안에서 불러온다 — 시작 스크립트가
상수만 읽을 때 딸려 오지 않게.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import threading
import time
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Final, Literal

from capa_simulation.io import s3_small
from capa_simulation.io.container_start_report import BDQ_SECRET_KEY_ENV, BDQ_USER_NAME_ENV

if TYPE_CHECKING:
    from capa_simulation.io.s3_small import S3Target

# CD 환경변수 — Fernet 키(32바이트를 URL 안전 base64 로 적은 44글자). 비밀이라 값을 어떤 글에도
# 싣지 않는다. 앱 프로세스에는 넘기고(`APP_WITHHELD_ENVIRONMENT` 에 넣지 않는다) 하위 프로세스에는
# 넘기지 않는다. 이름의 정본은 시작 스크립트와 함께 쓰는 `container_start_report` 다. 앱은 기동 때
# 한 번 읽어 쥐고 환경에서 뺀다(`take_secret_key`) — 앱이 띄우는 하위 프로세스(aws 등)가 물려받지
# 않게.
SECRET_KEY_ENV: Final = BDQ_SECRET_KEY_ENV
# 버킷 안 자리. 접두는 동기화 정리(`object_storage_manifest.PRUNE_PREFIXES`) · 모듈 데이터
# (`module_helpers.S3_KEY_PREFIX`) · 접속 명단(`access/`) 밖이다.
SECRETS_PREFIX: Final = "secrets/"
OBJECT_KEY: Final = f"{SECRETS_PREFIX}bdq_login.json"
DOCUMENT_VERSION: Final = 1

StoredState = Literal["ok", "stopped"]
STATE_OK: Final = "ok"
STATE_STOPPED: Final = "stopped"
_STATES: Final = frozenset({STATE_OK, STATE_STOPPED})

# 「저장된 계정 없음」 · 꺼짐의 까닭(짧은 영문 코드 — 화면 이름은 쓰는 쪽이 정한다).
REASON_NOT_MANAGED: Final = "not_managed"
REASON_NO_KEY: Final = "no_key"
REASON_BAD_KEY: Final = "bad_key"
REASON_NO_TARGET: Final = "no_target"
REASON_NO_OBJECT: Final = "no_object"
REASON_UNREAD: Final = "unread"
REASON_BROKEN: Final = "broken"
REASON_VERSION: Final = "version"
REASON_UNDECRYPTABLE: Final = "undecryptable"
# 꺼짐 — 기능이 서지 않는 까닭. 이 셋이면 폼 제출 · 자동 로그인이 없다.
OFF_REASONS: Final = frozenset({REASON_NOT_MANAGED, REASON_NO_KEY, REASON_BAD_KEY})

# 쓰기 · 멈춤 표시 · 지우기의 실패 까닭.
WRITE_UNAVAILABLE: Final = "unavailable"
WRITE_FAILED: Final = "write_failed"
WRITE_GONE: Final = "gone"
WRITE_CHANGED: Final = "changed"
WRITE_BAD_INPUT: Final = "bad_input"

# 자동 시도가 로그인 앞에 써 두는 멈춤 까닭 — 결과로 고쳐 쓰지 못한 채 남으면 그대로 멈춤이다.
ATTEMPTING_REASON: Final = "attempting"
# 멈춤 까닭 코드의 꼴 — 짧은 영문 소문자 · 숫자 · 밑줄.
_REASON_CODE: Final = re.compile(r"[a-z][a-z0-9_]{0,39}")
_FERNET_KEY: Final = re.compile(r"[A-Za-z0-9_-]{43}=")
# 넣은 관리자 앱 로그인 ID 에서 남기는 글자 수.
ENTERED_BY_CHARS: Final = 2
# KST — 시각대 데이터베이스 없이 고정 +9 시간.
KST: Final = timezone(timedelta(hours=9), "KST")
# S3 를 읽지 못했을 때 다시 읽기까지 기다리는 초. 조회마다 8초 마감을 물지 않게.
UNREAD_RETRY_SECONDS: Final = 60.0


def kst_text(moment: datetime | None = None) -> str:
    """KST ISO 시각(초까지, `+09:00`)."""
    value = datetime.now(KST) if moment is None else moment.astimezone(KST)
    return value.isoformat(timespec="seconds")


def entered_by_mark(login_id: str) -> str:
    """넣은 관리자의 앱 로그인 ID 앞 두 글자 — 저장 · 화면에 남는 전부다."""
    return login_id.strip()[:ENTERED_BY_CHARS]


# --- 키 ---------------------------------------------------------------------------------


def valid_key_text(text: str) -> bool:
    """Fernet 키 꼴인가 — URL 안전 base64 44글자이고 풀면 32바이트."""
    value = text.strip()
    if _FERNET_KEY.fullmatch(value) is None:
        return False
    try:
        return len(base64.urlsafe_b64decode(value)) == 32
    except (binascii.Error, ValueError):
        return False


@dataclass
class _Taken:
    """기동 때 환경에서 뺀 키 글(`take_secret_key`). 뺐으면 프로세스 환경 대신 이것을 읽는다."""

    taken: bool = False
    text: str = field(default="", repr=False)


_TAKEN = _Taken()
_TAKEN_LOCK: Final = threading.Lock()


def take_secret_key(environ: MutableMapping[str, str]) -> None:
    """앱 기동 때 한 번 — 키 글을 쥐고 `environ`(프로세스 환경)에서 뺀다. 그 뒤 `environ` 을 주지
    않은 키 읽기(`secret_key()` · `key_problem()` · `availability()`)는 쥔 글을 본다. 두 번째 부름은
    처음 쥔 글을 그대로 둔다(이미 뺐다)."""
    with _TAKEN_LOCK:
        if _TAKEN.taken:
            environ.pop(SECRET_KEY_ENV, None)
            return
        _TAKEN.text = environ.pop(SECRET_KEY_ENV, "").strip()
        _TAKEN.taken = True


def _key_text(environ: Mapping[str, str] | None) -> str:
    if environ is None:
        with _TAKEN_LOCK:
            if _TAKEN.taken:
                return _TAKEN.text
        environ = os.environ
    return environ.get(SECRET_KEY_ENV, "").strip()


def secret_key(environ: Mapping[str, str] | None = None) -> bytes | None:
    """키 바이트(꼴이 맞을 때만). 없거나 틀리면 `None`."""
    text = _key_text(environ)
    return text.encode("ascii") if text and valid_key_text(text) else None


def key_problem(environ: Mapping[str, str] | None = None) -> str | None:
    """키가 쓰일 수 없는 까닭(`REASON_NO_KEY` · `REASON_BAD_KEY`). 쓸 수 있으면 `None`."""
    text = _key_text(environ)
    if not text:
        return REASON_NO_KEY
    return None if valid_key_text(text) else REASON_BAD_KEY


def is_managed(environ: Mapping[str, str] | None = None) -> bool:
    """동기화 모드가 `managed` 인가. 설정을 읽지 못하면 아니다(기능이 서지 않는 쪽)."""
    from capa_simulation.io import object_storage

    try:
        return object_storage.load_settings(environ=environ).mode == object_storage.MODE_MANAGED
    except Exception:  # 설정 파일 · 모드 값이 깨져도 이 기능은 꺼짐으로 머문다
        return False


def availability(environ: Mapping[str, str] | None = None) -> str | None:
    """기능이 서지 않는 까닭(`OFF_REASONS` 가운데 하나). 서면 `None`. S3 에 묻지 않는다."""
    if not is_managed(environ):
        return REASON_NOT_MANAGED
    return key_problem(environ)


# --- 닿을 곳 ------------------------------------------------------------------------------


def target_from_environ(environ: Mapping[str, str]) -> S3Target | None:
    """환경변수 표에서 닿을 곳 — 시작 스크립트처럼 S3 키가 아직 환경에 있는 쪽이 쓴다. 판정은 접속
    명단과 같은 한 곳(`auth.config.load_config` 의 `access_s3`)이다. 값이 빠지거나 틀리면 `None`."""
    from capa_simulation.auth.config import load_config

    return load_config(environ).access_s3


def app_target() -> S3Target | None:
    """앱 프로세스의 닿을 곳 — 통합인증 설정이 기동 때 읽어 둔 것(`runtime.config().access_s3`).
    앱은 S3 키를 기동 때 환경에서 빼므로 환경을 다시 읽지 않는다."""
    from capa_simulation.auth import runtime

    return runtime.config().access_s3


# --- 풀린 값 · 저장된 한 벌 -----------------------------------------------------------------


@dataclass(frozen=True)
class LoginSecret:
    """풀린 BDQ 계정 · 비밀번호. 둘 다 repr · str 에 나오지 않는다(계정 ID 도 화면에 보이지
    않는다)."""

    account: str = field(repr=False)
    password: str = field(repr=False)

    def __str__(self) -> str:
        return "LoginSecret(***)"

    __repr__ = __str__


@dataclass(frozen=True)
class StoredLogin:
    """저장 객체 한 벌. `secret` · `cipher` 는 repr 에 나오지 않는다."""

    secret: LoginSecret = field(repr=False)
    cipher: str = field(repr=False)
    entered_by: str
    entered_at: str
    state: StoredState
    stop_reason: str | None = None
    stopped_at: str | None = None
    misses: int = 0

    @property
    def stopped(self) -> bool:
        return self.state == STATE_STOPPED


@dataclass(frozen=True)
class LoadResult:
    """읽기 한 번. 계정이 있으면 `stored`, 없으면 `reason`(S3 실패면 그 분류 `failure_kind` 도)."""

    stored: StoredLogin | None
    reason: str = ""
    failure_kind: str = ""


@dataclass(frozen=True)
class WriteResult:
    """쓰기 · 멈춤 표시 · 지우기 한 번. 실패면 `reason`(그리고 S3 실패면 그 분류)."""

    ok: bool
    reason: str = ""
    failure_kind: str = ""
    stored: StoredLogin | None = field(default=None, repr=False)


def encrypt_secret(secret: LoginSecret, key: bytes) -> str:
    """계정 · 비밀번호 JSON 을 Fernet 으로 감싼 글. 키 꼴이 틀리면 `ValueError`(값은 싣지
    않는다)."""
    from cryptography.fernet import Fernet

    try:
        fernet = Fernet(key)
    except (ValueError, TypeError, binascii.Error):
        fernet = None
    if fernet is None:
        raise ValueError("키 꼴이 아니다")
    plain = json.dumps({"account": secret.account, "password": secret.password}).encode("utf-8")
    return fernet.encrypt(plain).decode("ascii")


def decrypt_secret(cipher: str, key: bytes) -> LoginSecret | None:
    """`encrypt_secret` 의 거꾸로. 키가 맞지 않거나 · 감싼 글이 깨졌거나 · 풀린 꼴이 다르면 `None`.
    예외를 내지 않는다 — 풀린 글을 든 예외(`JSONDecodeError.doc` 등)를 밖으로 내보내지 않는다."""
    from cryptography.fernet import Fernet, InvalidToken

    try:
        plain = Fernet(key).decrypt(cipher.encode("ascii"))
    except (InvalidToken, ValueError, TypeError, binascii.Error, UnicodeEncodeError):
        return None
    try:
        data = json.loads(plain.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    account, password = data.get("account"), data.get("password")
    if not isinstance(account, str) or not isinstance(password, str) or not account or not password:
        return None
    return LoginSecret(account, password)


def _document(
    cipher: str,
    entered_by: str,
    entered_at: str,
    state: StoredState,
    stop_reason: str | None,
    stopped_at: str | None,
    misses: int = 0,
) -> bytes:
    data = {
        "v": DOCUMENT_VERSION,
        "cipher": cipher,
        "entered_by": entered_by,
        "entered_at": entered_at,
        "state": state,
        "stop_reason": stop_reason,
        "stopped_at": stopped_at,
        "misses": misses,
    }
    return json.dumps(data, ensure_ascii=True, sort_keys=True).encode("ascii")


@dataclass(frozen=True)
class _Meta:
    cipher: str = field(repr=False)
    entered_by: str
    entered_at: str
    state: StoredState
    stop_reason: str | None
    stopped_at: str | None
    misses: int


def _optional_text(value: object) -> tuple[bool, str | None]:
    if value is None:
        return True, None
    if isinstance(value, str):
        return True, value
    return False, None


def _parse_meta(body: bytes) -> tuple[_Meta | None, str]:
    """객체 본문 → 메타(키 없이). 깨졌으면 `(None, REASON_BROKEN)`, 판이 다르면 `REASON_VERSION`."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None, REASON_BROKEN
    if not isinstance(data, dict):
        return None, REASON_BROKEN
    version = data.get("v")
    if isinstance(version, bool) or not isinstance(version, int):
        return None, REASON_BROKEN
    if version != DOCUMENT_VERSION:
        return None, REASON_VERSION
    cipher, entered_by, entered_at = (
        data.get("cipher"),
        data.get("entered_by"),
        data.get("entered_at"),
    )
    state = data.get("state")
    reason_ok, stop_reason = _optional_text(data.get("stop_reason"))
    stopped_ok, stopped_at = _optional_text(data.get("stopped_at"))
    misses = data.get("misses", 0)
    misses_ok = isinstance(misses, int) and not isinstance(misses, bool) and misses >= 0
    if (
        not isinstance(cipher, str)
        or not cipher
        or not isinstance(entered_by, str)
        or not isinstance(entered_at, str)
        or state not in _STATES
        or not reason_ok
        or not stopped_ok
        or not misses_ok
    ):
        return None, REASON_BROKEN
    if stop_reason is not None and _REASON_CODE.fullmatch(stop_reason) is None:
        return None, REASON_BROKEN
    checked: StoredState = STATE_OK if state == STATE_OK else STATE_STOPPED
    return _Meta(
        cipher,
        entered_by[:ENTERED_BY_CHARS],
        entered_at,
        checked,
        stop_reason,
        stopped_at,
        int(misses),
    ), ""


def parse_document(body: bytes, key: bytes) -> LoadResult:
    """객체 본문 → 읽기 결과. 깨짐 · 판 다름 · 풀리지 않음은 모두 「없음」 이다."""
    meta, reason = _parse_meta(body)
    if meta is None:
        return LoadResult(None, reason)
    secret = decrypt_secret(meta.cipher, key)
    if secret is None:
        return LoadResult(None, REASON_UNDECRYPTABLE)
    return LoadResult(
        StoredLogin(
            secret=secret,
            cipher=meta.cipher,
            entered_by=meta.entered_by,
            entered_at=meta.entered_at,
            state=meta.state,
            stop_reason=meta.stop_reason,
            stopped_at=meta.stopped_at,
            misses=meta.misses,
        )
    )


# --- S3 읽기 · 쓰기 -------------------------------------------------------------------------


def load(target: S3Target, key: bytes | None) -> LoadResult:
    """객체를 받아 푼다. 키가 없으면 S3 에 묻지 않고 「없음」 이다."""
    if key is None:
        return LoadResult(None, REASON_NO_KEY)
    failure_kind = ""
    try:
        found = s3_small.get_object(target, OBJECT_KEY)
    except s3_small.S3Failure as failure:
        found, failure_kind = None, failure.kind
    if failure_kind:
        return LoadResult(None, REASON_UNREAD, failure_kind)
    if found is None:
        return LoadResult(None, REASON_NO_OBJECT)
    return parse_document(found.body, key)


def save_login(
    target: S3Target,
    key: bytes,
    secret: LoginSecret,
    entered_by_login_id: str,
    *,
    at: datetime | None = None,
) -> WriteResult:
    """계정을 상태 `ok` 로 쓴다(있으면 덮는다 — 멈춤도 풀린다). 성공하면 프로세스 기억도 바꾼다."""
    if not secret.account or not secret.password:
        return WriteResult(False, WRITE_BAD_INPUT)
    try:
        cipher = encrypt_secret(secret, key)
    except ValueError:
        cipher = ""
    if not cipher:
        return WriteResult(False, WRITE_BAD_INPUT)
    entered_by = entered_by_mark(entered_by_login_id)
    entered_at = kst_text(at)
    body = _document(cipher, entered_by, entered_at, STATE_OK, None, None)
    failure_kind = ""
    try:
        s3_small.put_object(target, OBJECT_KEY, body)
    except s3_small.S3Failure as failure:
        failure_kind = failure.kind
    if failure_kind:
        return WriteResult(False, WRITE_FAILED, failure_kind)
    stored = StoredLogin(secret, cipher, entered_by, entered_at, STATE_OK)
    remember(stored)
    return WriteResult(True, stored=stored)


def _rewrite_meta(
    target: S3Target,
    cipher: str,
    *,
    stopped: bool,
    reason: str | None,
    misses: int | None,
    remember_it: bool,
    at: datetime | None = None,
) -> WriteResult:
    """객체의 `cipher` 는 그대로 두고 상태 · 까닭 · 시각 · `misses`(`None` 이면 그대로)만 고쳐 다시
    쓴다. 키가 필요 없다.

    `cipher` 는 이 프로세스가 든 한 벌의 것이다 — 객체가 그 사이 다른 계정으로 바뀌었으면(관리자가
    다시 넣음) 새 계정을 건드리지 않고 `WRITE_CHANGED`, 없거나 깨졌으면 `WRITE_GONE` 다. 받기 →
    쓰기 틈은 replica 1 전제로 받아들인다(같은 프로세스의 쓰기는 로그인 잠금이 줄 세운다)."""
    if reason is not None and _REASON_CODE.fullmatch(reason) is None:
        return WriteResult(False, WRITE_BAD_INPUT)
    if misses is not None and misses < 0:
        return WriteResult(False, WRITE_BAD_INPUT)
    failure_kind = ""
    try:
        found = s3_small.get_object(target, OBJECT_KEY)
    except s3_small.S3Failure as failure:
        found, failure_kind = None, failure.kind
    if failure_kind:
        return WriteResult(False, WRITE_FAILED, failure_kind)
    if found is None:
        return WriteResult(False, WRITE_GONE)
    meta, _ = _parse_meta(found.body)
    if meta is None:
        return WriteResult(False, WRITE_GONE)
    if meta.cipher != cipher:
        return WriteResult(False, WRITE_CHANGED)
    state: StoredState = STATE_STOPPED if stopped else STATE_OK
    stopped_at = kst_text(at) if stopped else None
    count = meta.misses if misses is None else misses
    body = _document(
        meta.cipher,
        meta.entered_by,
        meta.entered_at,
        state,
        reason if stopped else None,
        stopped_at,
        count,
    )
    try:
        s3_small.put_object(target, OBJECT_KEY, body)
    except s3_small.S3Failure as failure:
        failure_kind = failure.kind
    if failure_kind:
        return WriteResult(False, WRITE_FAILED, failure_kind)
    if remember_it:
        _remember_meta(cipher, state, reason if stopped else None, stopped_at, count)
    return WriteResult(True)


def mark_stopped(
    target: S3Target,
    reason: str,
    *,
    cipher: str,
    at: datetime | None = None,
) -> WriteResult:
    """멈춤 표시 — 상태 · 까닭 · 시각만 고쳐 다시 쓴다(`misses` 그대로). 성공하면 기억도
    멈춤이다."""
    return _rewrite_meta(
        target, cipher, stopped=True, reason=reason, misses=None, remember_it=True, at=at
    )


def mark_attempting(target: S3Target, *, cipher: str, at: datetime | None = None) -> WriteResult:
    """자동 시도 앞의 시도 표시 — 객체를 멈춤(`ATTEMPTING_REASON`)으로 써 둔다. 이 쓰기가 실패하면
    로그인하지 않는다. 기억은 바꾸지 않는다 — 로그인이 도는 동안 이 프로세스의 화면 · 알림에
    멈춤으로 보이지 않게(결과를 적지 못하면 부르는 쪽이 프로세스 안 멈춤을 세운다)."""
    return _rewrite_meta(
        target,
        cipher,
        stopped=True,
        reason=ATTEMPTING_REASON,
        misses=None,
        remember_it=False,
        at=at,
    )


def record_outcome(
    target: S3Target,
    *,
    cipher: str,
    stopped: bool,
    reason: str | None,
    misses: int,
    at: datetime | None = None,
) -> WriteResult:
    """자동 시도의 결과를 적는다 — 상태(멈춤이면 까닭) · `misses`. 성공하면 기억도 바꾼다."""
    return _rewrite_meta(
        target,
        cipher,
        stopped=stopped,
        reason=reason,
        misses=misses,
        remember_it=True,
        at=at,
    )


def delete_login(target: S3Target) -> WriteResult:
    """객체를 지운다(없어도 성공). 성공하면 프로세스 기억도 「없음」 으로."""
    failure_kind = ""
    try:
        s3_small.delete_object(target, OBJECT_KEY)
    except s3_small.S3Failure as failure:
        failure_kind = failure.kind
    if failure_kind:
        return WriteResult(False, WRITE_FAILED, failure_kind)
    remember(None)
    return WriteResult(True)


# --- 프로세스 기억 ----------------------------------------------------------------------------


@dataclass
class _Memo:
    loaded: bool = False
    result: LoadResult = field(default_factory=lambda: LoadResult(None, ""))
    read_at: float = 0.0
    # 기억을 바꾼 수 — S3 를 읽는 동안 저장 · 지우기 · 멈춤이 기억을 바꿨으면 읽은 결과를 버린다.
    generation: int = 0


_MEMO = _Memo()
# 기억만 지킨다 — S3 를 기다리며 쥐지 않는다(화면 회차의 `peek_*` 가 멎지 않게).
_MEMO_LOCK: Final = threading.Lock()
# S3 읽기를 한 번에 하나로 — 읽는 동안 다른 부름은 옛 기억을 받는다(처음 읽기만 기다린다).
_READ_LOCK: Final = threading.Lock()


def forget_state() -> None:
    """시험 전용 — 기억한 읽기 결과와 기동 때 쥔 키를 지운다(다음 `current` 가 다시 읽는다)."""
    with _MEMO_LOCK:
        _MEMO.loaded = False
        _MEMO.result = LoadResult(None, "")
        _MEMO.read_at = 0.0
        _MEMO.generation += 1
    with _TAKEN_LOCK:
        _TAKEN.taken = False
        _TAKEN.text = ""


def peek_state() -> LoadResult | None:
    """기억한 읽기 결과를 S3 에 묻지 않고 본다 — 아직 읽지 않았으면 `None`. 화면 회차마다 도는
    자리(알림 · 지금 토큰 줄)가 쓴다. 다른 스레드가 S3 를 읽는 중이어도 기다리지 않는다."""
    with _MEMO_LOCK:
        return _MEMO.result if _MEMO.loaded else None


def peek_account(environ: Mapping[str, str] | None = None) -> str:
    """계정 원천을 S3 에 묻지 않고 — 기억한 저장된 계정이 있으면 그 ID, 없거나 아직 읽지 않았으면
    `CAPA_BDQ_USER_NAME`. 앱은 기동 때 한 번 읽어 두므로(`bdq_login.start_in_app`) 화면 회차의
    토큰 파일 자리 · 지금 토큰 줄이 이것으로 `effective_account` 와 같은 답을 얻는다."""
    loaded = peek_state()
    return account_of(None if loaded is None else loaded.stored, environ)


def remember(stored: StoredLogin | None, reason: str = REASON_NO_OBJECT) -> None:
    """기억을 바꾼다 — 저장 · 지우기 · 시작 읽기가 부른다."""
    with _MEMO_LOCK:
        _MEMO.loaded = True
        _MEMO.result = LoadResult(stored, "" if stored is not None else reason)
        _MEMO.read_at = time.monotonic()
        _MEMO.generation += 1


def _remember_meta(
    cipher: str,
    state: StoredState,
    reason: str | None,
    stopped_at: str | None,
    misses: int,
) -> None:
    """기억한 한 벌이 그 `cipher` 면 메타를 바꾼다(다른 한 벌이면 그대로). 어느 쪽이든 읽는 중인
    S3 결과는 버린다(객체를 막 고쳐 썼다)."""
    with _MEMO_LOCK:
        _MEMO.generation += 1
        stored = _MEMO.result.stored
        if stored is not None and stored.cipher == cipher:
            _MEMO.result = LoadResult(
                replace(
                    stored,
                    state=state,
                    stop_reason=reason,
                    stopped_at=stopped_at,
                    misses=misses,
                )
            )


def load_for_app() -> LoadResult:
    """앱 프로세스의 읽기 한 번 — 꺼짐이면 S3 에 묻지 않는다. 기억하지 않는다."""
    off = availability()
    if off is not None:
        return LoadResult(None, off)
    target = app_target()
    if target is None:
        return LoadResult(None, REASON_NO_TARGET)
    return load(target, secret_key())


def _fresh_locked() -> LoadResult | None:
    """`_MEMO_LOCK` 아래 — 기억이 아직 쓸 만하면 그것(S3 를 읽지 못한 결과는 `UNREAD_RETRY_SECONDS`
    까지)."""
    if not _MEMO.loaded:
        return None
    if (
        _MEMO.result.reason == REASON_UNREAD
        and time.monotonic() - _MEMO.read_at >= UNREAD_RETRY_SECONDS
    ):
        return None
    return _MEMO.result


def load_state() -> LoadResult:
    """기억한 읽기 결과(처음이면 읽는다). S3 를 읽지 못한 결과는 `UNREAD_RETRY_SECONDS` 뒤 다시
    읽는다. S3 읽기는 기억 잠금 밖에서 한 번에 하나만 돌고, 그동안 다른 부름은 옛 기억을 받는다(처음
    읽기만 기다린다). 읽는 동안 기억이 바뀌었으면 읽은 결과를 버리고 바뀐 기억을 준다."""
    with _MEMO_LOCK:
        fresh = _fresh_locked()
        if fresh is not None:
            return fresh
        stale = _MEMO.result if _MEMO.loaded else None
    if stale is not None:
        if not _READ_LOCK.acquire(blocking=False):
            return stale
    else:
        _READ_LOCK.acquire()
    try:
        with _MEMO_LOCK:
            fresh = _fresh_locked()
            if fresh is not None:
                return fresh
            generation = _MEMO.generation
        result = load_for_app()
        with _MEMO_LOCK:
            if _MEMO.generation != generation:
                return _MEMO.result
            _MEMO.loaded = True
            _MEMO.result = result
            _MEMO.read_at = time.monotonic()
            _MEMO.generation += 1
            return result
    finally:
        _READ_LOCK.release()


def current() -> StoredLogin | None:
    """지금 저장된 계정(멈춤 포함). 없으면 `None`."""
    return load_state().stored


def account_of(stored: StoredLogin | None, environ: Mapping[str, str] | None = None) -> str:
    """계정 하나의 원천 — 저장된 계정이 있으면 그 ID, 없으면 `CAPA_BDQ_USER_NAME`(앞뒤 공백 뺌)."""
    if stored is not None:
        return stored.secret.account
    env = os.environ if environ is None else environ
    return env.get(BDQ_USER_NAME_ENV, "").strip()


def effective_account(environ: Mapping[str, str] | None = None) -> str:
    """앱 프로세스의 계정 원천 — 조회(`getData` 의 `user_name`) · 토큰 파일 이름 · `getTokenTime` 이
    함께 쓴다. 폼으로 계정이 바뀌면 곧바로 새 ID 다(기억이 바뀐다). 빈 글이면 계정 없음."""
    return account_of(current(), environ)
