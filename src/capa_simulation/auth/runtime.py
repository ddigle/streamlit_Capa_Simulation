# Purpose: 통합인증 프로세스 상태 — 설정·문지기 표지·폐기 목록·진단·사건·로거.

"""통합인증 프로세스 상태.

모두 프로세스 메모리이고(replica 1 전제) 재시작하면 비워진다 — 로그아웃 폐기 목록이 사라지면 지운
쿠키를 다시 넣은 탭이 만료까지 살아나지만, 쿠키 자체는 지웠으므로 받아들인다. DB 에는 아무것도 쓰지
않는다. 세션 상태(`st.session_state`)도 아니다 — 문지기는 Streamlit 바깥의 이벤트 루프에서 돈다.

배경 스레드를 세우지 않는다(AGENTS 9장 「배경 스레드」 는 자동 갱신 예약 하나). 만료된 항목은 읽거나
쓸 때 치운다. 모든 읽기 · 쓰기는 잠금 하나로 묶는다 — 문지기(이벤트 루프)와 앱 스크립트 스레드가
함께 본다.
"""

from __future__ import annotations

import logging
import os
import secrets
import sys
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field

from capa_simulation.auth import names
from capa_simulation.auth.config import SsoConfig, SsoMode, load_config

LOGGER = logging.getLogger(names.LOGGER_NAME)
MAX_EVENTS = 50
# 로그인하지 않은 누구나 남길 수 있는 사건(콜백 · 로그인 시작의 실패). 따로 둔 고리에만 쌓고
# 사유별로 센다 — 한 고리에 두면 무인증 요청 수십 번으로 실제 로그인 · 로그아웃 · 설정 기록이
# 밀려난다(C-DEP 에는 로그 창구가 없어 이 고리가 운영자가 보는 유일한 감사 창이다).
ANONYMOUS_EVENTS = frozenset({"login_fail", "idp_error"})
MAX_DIAGNOSTICS = 100
DIAGNOSTIC_TTL = 600
MAX_REVOKED = 10_000
MAX_USED_STATES = 10_000
_FIELD_LIMIT = 200


@dataclass(frozen=True)
class SsoEvent:
    """사건 한 줄. 값은 이미 다듬어져 있다(공백 · 제어문자 없음)."""

    at: int
    event: str
    fields: tuple[tuple[str, str], ...]
    # 기동 뒤 몇 번째 사건인가 — 두 고리를 합칠 때 같은 초 안의 차례를 지킨다.
    seq: int = 0

    def value(self, key: str) -> str:
        return dict(self.fields).get(key, "")


@dataclass
class _State:
    config: SsoConfig | None = None
    started: bool = False
    gate_installed: bool = False
    revoked: dict[str, int] = field(default_factory=dict)
    used_states: dict[str, int] = field(default_factory=dict)
    diagnostics: OrderedDict[str, tuple[int, dict[str, str]]] = field(default_factory=OrderedDict)
    events: deque[SsoEvent] = field(default_factory=lambda: deque(maxlen=MAX_EVENTS))
    anonymous_events: deque[SsoEvent] = field(default_factory=lambda: deque(maxlen=MAX_EVENTS))
    anonymous_counts: dict[str, int] = field(default_factory=dict)
    event_seq: int = 0


_LOCK = threading.Lock()
_STATE = _State()
_HANDLER_MARK = "_capa_sso_stdout"


def _now() -> int:
    return int(time.time())


def _install_stdout_handler() -> None:
    """코어에는 로깅 설정이 없어 INFO 가 버려진다 — 진입 파일로 뜰 때만 stdout 처리기를 단다."""
    if any(getattr(handler, _HANDLER_MARK, False) for handler in LOGGER.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    setattr(handler, _HANDLER_MARK, True)
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def _announce(cfg: SsoConfig) -> None:
    problems = ",".join(problem.log_text() for problem in cfg.problems) or "-"
    level = logging.INFO
    if cfg.mode is SsoMode.BROKEN:
        level = logging.ERROR
    elif cfg.mode is SsoMode.OFF and cfg.prod:
        level = logging.WARNING
    record_event(
        "config",
        level=level,
        mode=cfg.mode.value,
        prod="1" if cfg.prod else "0",
        locked="1" if cfg.locked else "0",
        problems=problems,
    )
    now = time.time()
    for cert in cfg.signing_certs:
        days = int((cert.not_after.timestamp() - now) // 86400)
        if days <= 30:
            record_event("cert_expiring", level=logging.WARNING, days=str(days), x5t=cert.x5t[:16])


def start(environ: MutableMapping[str, str]) -> SsoConfig:
    """진입 파일이 기동 때 한 번 부른다 — 설정을 읽고 비밀값을 환경에서 빼고 로그를 단다.

    두 번째 부름은 처음 읽은 설정을 그대로 돌려준다(비밀값을 이미 뺐으므로 다시 읽으면 안 된다).
    """
    with _LOCK:
        if _STATE.started and _STATE.config is not None:
            return _STATE.config
        cfg = load_config(environ)
        # 앱이 띄우는 하위 프로세스가 물려받지 않게 · `os.environ` 덤프에 실리지 않게. 막는 범위는
        # 여기까지다 — 커널은 기동 때의 환경 사본을 `/proc/<pid>/environ` 에 남겨 같은 사용자의
        # 프로세스가 읽을 수 있고, 같은 프로세스 코드(사내 모듈 포함)는 메모리에 닿는다.
        environ.pop(names.ENV_SECRET, None)
        _STATE.config = cfg
        _STATE.started = True
    _install_stdout_handler()
    _announce(cfg)
    return cfg


def config() -> SsoConfig:
    """지금 설정.

    `start` 없이 뜬 프로세스(개발의 `streamlit run app.py`)는 처음 부를 때 환경에서 읽는다.
    """
    with _LOCK:
        if _STATE.config is None:
            _STATE.config = load_config(os.environ)
        return _STATE.config


def started() -> bool:
    with _LOCK:
        return _STATE.started


def mark_gate_installed() -> None:
    with _LOCK:
        _STATE.gate_installed = True


def gate_installed() -> bool:
    with _LOCK:
        return _STATE.gate_installed


def _prune(table: dict[str, int], now: int) -> None:
    for key in [key for key, expires in table.items() if expires < now]:
        del table[key]


def revoke(jti: str, exp: int) -> None:
    """로그아웃한 세션 토큰을 만료까지 막는다(다른 탭의 재연결 · 새로고침도)."""
    now = _now()
    with _LOCK:
        _prune(_STATE.revoked, now)
        if len(_STATE.revoked) >= MAX_REVOKED:
            oldest = min(_STATE.revoked, key=_STATE.revoked.__getitem__)
            del _STATE.revoked[oldest]
        _STATE.revoked[jti] = exp


def is_revoked(jti: str) -> bool:
    now = _now()
    with _LOCK:
        expires = _STATE.revoked.get(jti)
        if expires is None:
            return False
        if expires < now:
            del _STATE.revoked[jti]
            return False
        return True


def remember_used_state(digest: str, exp: int) -> bool:
    """콜백이 쓴 state 를 만료까지 기억한다. 처음이면 True, 이미 쓴 것이면 False(재사용)."""
    now = _now()
    with _LOCK:
        _prune(_STATE.used_states, now)
        if digest in _STATE.used_states:
            return False
        if len(_STATE.used_states) >= MAX_USED_STATES:
            oldest = min(_STATE.used_states, key=_STATE.used_states.__getitem__)
            del _STATE.used_states[oldest]
        _STATE.used_states[digest] = exp
        return True


def keep_diagnostic(record: Mapping[str, str]) -> str:
    """오류 화면(PRG)이 다시 읽을 진단을 10분 둔다. 꺼낼 id 를 돌려준다."""
    now = _now()
    diagnostic_id = secrets.token_urlsafe(12)
    with _LOCK:
        for key in [key for key, (expires, _) in _STATE.diagnostics.items() if expires < now]:
            del _STATE.diagnostics[key]
        while len(_STATE.diagnostics) >= MAX_DIAGNOSTICS:
            _STATE.diagnostics.popitem(last=False)
        _STATE.diagnostics[diagnostic_id] = (now + DIAGNOSTIC_TTL, dict(record))
    return diagnostic_id


def get_diagnostic(diagnostic_id: str) -> dict[str, str] | None:
    """보관한 진단(지우지 않는다 — 오류 화면 새로고침도 같은 것을 본다). 없거나 지났으면 None."""
    now = _now()
    with _LOCK:
        entry = _STATE.diagnostics.get(diagnostic_id)
        if entry is None:
            return None
        expires, record = entry
        if expires < now:
            del _STATE.diagnostics[diagnostic_id]
            return None
        return dict(record)


def _clean_field(value: object) -> str:
    text = str(value)
    cleaned = "".join(
        "_" if (ch.isspace() or ch == "=" or ord(ch) < 32 or ord(ch) == 127) else ch for ch in text
    )
    return cleaned[:_FIELD_LIMIT] or "-"


def is_anonymous(item: SsoEvent) -> bool:
    """로그인하지 않은 누구나 남길 수 있는 사건인가 — 서명이 통과하기 전의 실패(계정 없음)."""
    return item.event in ANONYMOUS_EVENTS and item.value("loginid") in ("", "-")


def _anonymous_key(item: SsoEvent) -> str:
    code = item.value("reason") or item.value("error") or "-"
    return f"{item.event}:{code}"


def record_event(event: str, *, level: int = logging.INFO, **fields: str) -> None:
    """사건 한 줄 — 서버 로그(`sso event=… key=value`)와 최근 사건 고리(각 최대 50).

    무인증 실패(`is_anonymous`)는 따로 둔 고리에 쌓고 사유별로 센다 — 다른 사건(설정 · 로그인 ·
    로그아웃 · 연결 닫음 · 서명이 통과한 뒤의 실패)을 밀어내지 못한다. 토큰 · state · nonce · 쿠키 ·
    비밀값 · 이름 · 부서는 넘기지 않는다(부르는 쪽 규칙).
    """
    cleaned = tuple((key, _clean_field(value)) for key, value in fields.items())
    line = f"sso event={_clean_field(event)}" + "".join(f" {key}={value}" for key, value in cleaned)
    LOGGER.log(level, line)
    with _LOCK:
        _STATE.event_seq += 1
        item = SsoEvent(at=_now(), event=_clean_field(event), fields=cleaned, seq=_STATE.event_seq)
        if is_anonymous(item):
            _STATE.anonymous_events.append(item)
            key = _anonymous_key(item)
            if key in _STATE.anonymous_counts or len(_STATE.anonymous_counts) < MAX_EVENTS:
                _STATE.anonymous_counts[key] = _STATE.anonymous_counts.get(key, 0) + 1
            else:
                other = f"{item.event}:other"
                _STATE.anonymous_counts[other] = _STATE.anonymous_counts.get(other, 0) + 1
        else:
            _STATE.events.append(item)


def recent_events(limit: int = MAX_EVENTS, *, anonymous: bool | None = None) -> list[SsoEvent]:
    """최근 사건, 새것 먼저. `anonymous` 가 `False` 면 무인증 실패를 뺀 것, `True` 면 그것만,
    `None` 이면 두 고리를 시각 차례로 합친 것."""
    with _LOCK:
        if anonymous is None:
            pool = sorted(
                [*_STATE.events, *_STATE.anonymous_events],
                key=lambda item: item.seq,
                reverse=True,
            )
        elif anonymous:
            pool = list(reversed(_STATE.anonymous_events))
        else:
            pool = list(reversed(_STATE.events))
    return pool[:limit]


def anonymous_failure_counts() -> dict[str, int]:
    """기동 뒤 무인증 실패 누계 — `사건:사유` 별, 많은 것 먼저. 고리에서 밀려난 것도 센다."""
    with _LOCK:
        counts = dict(_STATE.anonymous_counts)
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def reset() -> None:
    """시험 전용 — 설정 · 표지 · 폐기 목록 · state · 진단 · 사건을 비우고 stdout 처리기를 뗀다."""
    global _STATE
    with _LOCK:
        _STATE = _State()
    for handler in [item for item in LOGGER.handlers if getattr(item, _HANDLER_MARK, False)]:
        LOGGER.removeHandler(handler)
    LOGGER.setLevel(logging.NOTSET)
    LOGGER.propagate = True
