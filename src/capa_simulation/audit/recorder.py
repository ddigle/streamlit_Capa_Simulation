# Purpose: 감사 기록기 — 사건 한 줄을 다듬어 프로세스 메모리 큐에 넣는다(켜진 서버만).

"""감사 기록기(표준 라이브러리만 — Streamlit · DuckDB · PyJWT 를 import 하지 않는다).

**넣기만 한다.** 이벤트 루프(문지기 · 로그인 경로) · 스크립트 스레드(본문 · 콜백 · 저장소 쓰기) ·
예약 · 일꾼 스레드가 부르고, 잠금 하나 안의 메모리 조작뿐이라 막히지 않는다. 파일에 적는 것은
비우기(`spool.drain`)의 몫이다 — 해시 사슬의 순번 · 앞 해시도 그때 매긴다.

**켜짐은 한 곳이다.** `start` 를 부른 프로세스만 켜진다 — `capa_server.py` 가 통합인증이 켜진
기동에서 `audit/boot.py` 로 부른다. 끄는 환경변수는 없다(관리자가 자기 기록을 끌 수 없게).
꺼진 곳(사내 PC · WebIDE · 시험 · `app.py` 개발 실행)에서는 모든 공개 함수가 첫 줄에서
돌아간다.

**실패해도 앱은 멈추지 않는다.** 기록을 만들다 난 예외는 로그 한 줄로 삼킨다. 큐가 넘치면(상한
`MAX_QUEUE`) 버리고 그 수를 세어 다음 비우기 때 `sys_audit_dropped` 한 줄로 낸다. 비우기가 해시를
못 매겨 버린 줄(`note_dropped`)도 같은 수에 더한다.

**행위자는 쓰는 순간에 정한다.** 부르는 쪽이 `actor` 를 주지 않으면 스레드 이름(예약 · 일꾼 →
`system:*`)을 먼저 보고, 아니면 꽂아 둔 해석기(`set_resolver` — 스크립트 스레드의 쿠키를 지금 다시
검증)를 부른다. 이벤트 루프의 사건은 늘 `actor` 를 준다(해석기를 부르지 않는다).

**시간 묶음.** 무인증 실패 · 로그인 갱신 · 명단 밖 되풀이 · DB 올리기 성공은 사건마다가 아니라 UTC
정시 단위로 센 뒤, 정시를 넘긴 첫 비우기 때 한 줄을 낸다 — 무인증 홍수가 기록을 밀어내지 못한다.
「지금 올리기」 는 열린 묶음을 앞당겨 닫는다(`partial` — CI/CD 앞에 메모리 누계를 남긴다).
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final

from capa_simulation.audit import events, text

_LOGGER = logging.getLogger(__name__)

FORMAT_VERSION: Final = 1
MAX_QUEUE: Final = 20_000
DET_LIMIT_BYTES: Final = 1024
DET_TEXT_LIMIT: Final = 120
DET_LIST_LIMIT: Final = 20
DET_COUNTS_LIMIT: Final = 50
# 시간 묶음 건수 표가 키 글로 쓸 수 있는 바이트 — 넘는 새 키는 `other` 로 센다. 키마다 따옴표 ·
# 쌍점 · 쉼표 · 건수 자리를 `_COUNT_KEY_OVERHEAD` 로 잡아 합계 · 시간 칸과 함께 늘 1KB 안에 든다.
COUNTS_KEY_BUDGET: Final = 768
_COUNT_KEY_OVERHEAD: Final = 12
TRUNC_KEY: Final = "trunc"
OTHER_KEY: Final = "other"
PARTIAL_KEY: Final = "partial"

# 실행 문맥이 없는 배경 스레드 둘 — 이름은 `auto_update_scheduler.THREAD_NAME` ·
# `object_sync_worker.THREAD_NAME` 과 같다(시험이 맞댄다). 무거운 모듈을 import 하지 않으려
# 글로 둔다.
SYSTEM_THREADS: Final[Mapping[str, str]] = {
    "capa-auto-official-update": "system:auto_update",
    "capa-object-sync": "system:object_sync",
}
SYSTEM_SSO: Final = "system:sso"

SUMMARY_LOGIN_FAIL: Final = "authn_login_fail_summary"
SUMMARY_RENEW: Final = "session_renew_summary"
SUMMARY_DENIED: Final = "authz_fail_access_list_summary"
SUMMARY_SYNC: Final = "sys_sync_summary"
_SUMMARY_LEVELS: Final[Mapping[str, str]] = {
    SUMMARY_LOGIN_FAIL: "warn",
    SUMMARY_DENIED: "warn",
}


@dataclass(frozen=True)
class Actor:
    """행위자 — loginid(소문자) 또는 `system:*` · 빈 글(무인증), 인증 신원인가, 그때의 등급."""

    actor: str
    verified: bool
    grade: str


NOBODY: Final = Actor("", False, "none")

Resolver = Callable[[], Actor | None]
Grader = Callable[[str], str]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _Bucket:
    hour: str
    counts: dict[str, int] = field(default_factory=dict)
    # 명단 밖 — 이 시간에 첫 줄을 낸 계정(앞당겨 닫아도 그 시간 동안 남긴다)과, 이 묶음이 열린 뒤
    # 낸 첫 줄 수(묶음 한 줄의 `accounts` — 줄마다 `total - accounts` 가 되풀이 수다).
    accounts: set[str] = field(default_factory=set)
    firsts: int = 0


@dataclass
class _State:
    enabled: bool = False
    env: str = ""
    ver: str = ""
    inst: str = ""
    queue: deque[dict[str, Any]] = field(default_factory=deque)
    dropped: int = 0
    dropped_total: int = 0
    resolver: Resolver | None = None
    grader: Grader | None = None
    clock: Clock = _utc_now
    buckets: dict[str, _Bucket] = field(default_factory=dict)


_LOCK = threading.Lock()
_STATE = _State()


# ------------------------------------------------------------------ 켜기 · 끄기
def start(*, env: str, version: str, inst: str, clock: Clock | None = None) -> None:
    """이 프로세스의 기록기를 켠다(통합인증이 켜진 기동에서 한 번 — `audit/boot.py`)."""
    with _LOCK:
        _STATE.enabled = True
        _STATE.env = text.clean_text(env, 16)
        _STATE.ver = text.clean_text(version, 40)
        _STATE.inst = text.clean_text(inst, 32)
        if clock is not None:
            _STATE.clock = clock


def enabled() -> bool:
    """이 프로세스가 감사 기록을 남기는가. 프로세스 동안 바뀌지 않는다."""
    return _STATE.enabled


def instance_id() -> str:
    return _STATE.inst


def set_resolver(resolver: Resolver | None) -> None:
    """스크립트 스레드의 행위자 해석기를 꽂는다(`components/audit_actor.py`)."""
    with _LOCK:
        _STATE.resolver = resolver


def set_grader(grader: Grader | None) -> None:
    """loginid → 등급(`admin` · `user`) 판정기를 꽂는다(`audit/boot.py`)."""
    with _LOCK:
        _STATE.grader = grader


def now() -> datetime:
    return _STATE.clock()


def reset() -> None:
    """시험 전용 — 끄고 큐 · 묶음 · 해석기 · 판정기를 비운다."""
    global _STATE
    with _LOCK:
        _STATE = _State()


# ------------------------------------------------------------------ 시각
def ts_text(moment: datetime) -> str:
    """UTC ISO 8601 밀리초 + `Z`."""
    utc = moment.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def _hour_of(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


# ------------------------------------------------------------------ 행위자
def system_actor() -> Actor | None:
    """실행 문맥이 없는 배경 스레드면 그 `system:*` 행위자."""
    name = threading.current_thread().name
    actor = SYSTEM_THREADS.get(name)
    return None if actor is None else Actor(actor, False, "system")


def resolve_actor() -> Actor:
    """지금 이 스레드의 행위자. 해석기가 실패해도 빈 행위자로 남긴다."""
    found = system_actor()
    if found is not None:
        return found
    resolver = _STATE.resolver
    if resolver is None:
        return NOBODY
    try:
        resolved = resolver()
    except Exception:  # noqa: BLE001 — 기록 때문에 저장이 멈추면 안 된다
        _LOGGER.exception("감사 행위자를 정하지 못했습니다.")
        return NOBODY
    return NOBODY if resolved is None else resolved


def normalize_actor(value: str) -> str:
    cleaned = text.clean_text(value, 80)
    if cleaned in ("", "-"):
        return ""
    return cleaned if cleaned.startswith("system:") else cleaned.lower()


def grade_of(actor: str) -> str:
    if not actor:
        return "none"
    if actor.startswith("system:"):
        return "system"
    grader = _STATE.grader
    if grader is None:
        return "none"
    try:
        grade = grader(actor)
    except Exception:  # noqa: BLE001
        return "none"
    return grade if grade in events.GRADES else "none"


# ------------------------------------------------------------------ 다듬기
def _det_value(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, Mapping):
        counts: dict[str, int] = {}
        for key, count in list(value.items())[:DET_COUNTS_LIMIT]:
            if isinstance(count, int) and not isinstance(count, bool):
                counts[text.clean_text(key, 60)] = count
        return counts
    if isinstance(value, list | tuple | frozenset | set):
        items = sorted(value) if isinstance(value, frozenset | set) else list(value)
        return [text.clean_text(item, 60) for item in items[:DET_LIST_LIMIT]]
    return text.clean_text(value, DET_TEXT_LIMIT)


def clean_det(spec: events.EventSpec, det: Mapping[str, object] | None) -> dict[str, object]:
    """허용 키만, 값은 다듬어서, 정규화 1KB 안으로.

    넘치면 `trunc` 를 달고 먼저 건수 표(시간 묶음의 `counts`)를 줄인다 — 작은 건수부터 `other`
    하나로 모아 합계 · 시간 칸은 남긴다. 그래도 넘치면 정렬 끝 키부터 뺀다(`trunc` 는 빼지 않는다).
    두 고리 모두 돌 때마다 줄어 반드시 끝난다.
    """
    if not det:
        return {}
    kept = {
        key: _det_value(value)
        for key, value in det.items()
        if key in spec.det_keys and value is not None
    }
    if len(text_bytes(kept)) <= DET_LIMIT_BYTES:
        return kept
    kept[TRUNC_KEY] = True
    for key in sorted(name for name, value in kept.items() if isinstance(value, dict)):
        _shrink_counts(kept, key)
    while len(text_bytes(kept)) > DET_LIMIT_BYTES:
        victims = sorted(name for name in kept if name != TRUNC_KEY)
        if not victims:
            break
        kept.pop(victims[-1])
    return kept


def _shrink_counts(kept: dict[str, object], key: str) -> None:
    """`kept[key]` 건수 표의 작은 건수부터 `other` 로 모은다.

    1KB 안에 들거나 `other` 만 남을 때까지 — 돌 때마다 키 하나가 줄어 끝난다.
    """
    raw = kept[key]
    counts: dict[str, int] = dict(raw) if isinstance(raw, dict) else {}
    kept[key] = counts
    while len(text_bytes(kept)) > DET_LIMIT_BYTES:
        names = [name for name in counts if name != OTHER_KEY]
        if not names:
            return
        smallest = min(names, key=lambda name: (counts[name], name))
        counts[OTHER_KEY] = counts.get(OTHER_KEY, 0) + counts.pop(smallest)


def text_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _clean_target(tgt: Mapping[str, object] | None) -> dict[str, str] | None:
    if not tgt:
        return None
    cleaned: dict[str, str] = {}
    for key, limit in (("type", 40), ("id", 120), ("label", text.LABEL_LIMIT)):
        value = tgt.get(key)
        if value is not None and str(value).strip():
            cleaned[key] = text.clean_text(value, limit)
    return cleaned or None


def build_line(
    ev: str,
    *,
    out: str,
    who: Actor,
    tgt: Mapping[str, object] | None = None,
    det: Mapping[str, object] | None = None,
    why: str | None = None,
    name: str | None = None,
    claimed: str | None = None,
    sid8: str | None = None,
    tab8: str | None = None,
    page: str | None = None,
    ip: str | None = None,
    lvl: str | None = None,
    moment: datetime | None = None,
    env: str | None = None,
    ver: str | None = None,
    inst: str | None = None,
) -> dict[str, Any]:
    """한 줄(사슬 칸 `seq` · `prev` · `h` 없이). 목록 밖 사건은 `sys_audit_bad_event` 로 바꾼다."""
    spec = events.spec_of(ev)
    if spec is None:
        det = {"name": ev}
        spec = events.SPEC_BY_NAME[events.BAD_EVENT]
        out = "unknown"
    outcome = out if out in events.OUTCOMES else "unknown"
    level = lvl if lvl in events.LEVELS else None
    if level is None:
        level = spec.lvl if outcome in ("success", "unknown") else max(spec.lvl, "warn", key=_rank)
    actor = normalize_actor(who.actor)
    line: dict[str, Any] = {
        "v": FORMAT_VERSION,
        "ts": ts_text(moment or now()),
        "inst": _STATE.inst if inst is None else inst,
        "env": _STATE.env if env is None else env,
        "ver": _STATE.ver if ver is None else ver,
        "ev": spec.name,
        "cat": spec.cat,
        "out": outcome,
        "lvl": level,
        "actor": actor,
        "verified": bool(who.verified and actor),
        "grade": who.grade if who.grade in events.GRADES else "none",
    }
    if name and spec.name == "authn_login_success":
        line["name"] = text.clean_text(name, text.LABEL_LIMIT)
    if claimed:
        claimed_text = text.clean_text(claimed, text.CLAIMED_LIMIT)
        if claimed_text and claimed_text.lower() != actor:
            line["claimed"] = claimed_text
    for key, value, limit in (("sid8", sid8, 8), ("tab8", tab8, 8), ("page", page, 80)):
        if value:
            line[key] = text.clean_text(value, limit)
    if ip is not None:
        line["ip"] = text.clean_text(ip, 64)
    target = _clean_target(tgt)
    if target is not None:
        line["tgt"] = target
    detail = clean_det(spec, det)
    if detail:
        line["det"] = detail
    if why:
        line["why"] = text.clean_text(why, 40)
    return line


def _rank(level: str) -> int:
    return events.LEVELS.index(level) if level in events.LEVELS else 0


# ------------------------------------------------------------------ 넣기
def _enqueue(line: dict[str, Any]) -> None:
    with _LOCK:
        if len(_STATE.queue) >= MAX_QUEUE:
            _STATE.dropped += 1
            _STATE.dropped_total += 1
            return
        _STATE.queue.append(line)


def record(
    ev: str,
    *,
    out: str = "success",
    actor: str | None = None,
    verified: bool | None = None,
    tgt: Mapping[str, object] | None = None,
    det: Mapping[str, object] | None = None,
    why: str | None = None,
    name: str | None = None,
    claimed: str | None = None,
    sid8: str | None = None,
    tab8: str | None = None,
    page: str | None = None,
    ip: str | None = None,
    lvl: str | None = None,
) -> None:
    """사건 한 줄을 큐에 넣는다. 꺼진 프로세스면 아무것도 하지 않는다. 예외를 올리지 않는다.

    `actor` 를 주면 그 값(이벤트 루프 · 시스템 사건), 주지 않으면 지금 스레드의 행위자다.
    """
    if not _STATE.enabled:
        return
    try:
        if actor is None:
            who = resolve_actor()
        else:
            normalized = normalize_actor(actor)
            who = Actor(normalized, bool(verified), grade_of(normalized))
        line = build_line(
            ev,
            out=out,
            who=who,
            tgt=tgt,
            det=det,
            why=why,
            name=name,
            claimed=claimed,
            sid8=sid8,
            tab8=tab8,
            page=page,
            ip=ip,
            lvl=lvl,
        )
    except Exception:  # noqa: BLE001 — 기록 실패가 앱을 멈추지 않는다
        _LOGGER.exception("감사 기록 한 줄을 만들지 못했습니다.")
        return
    _enqueue(line)


def note_work(
    ev: str,
    *,
    out: str = "success",
    tgt: Mapping[str, object] | None = None,
    det: Mapping[str, object] | None = None,
    claimed: str | None = None,
    why: str | None = None,
) -> None:
    """데이터 작업 한 줄 — 행위자는 지금 스레드의 것이다(`record` 의 짧은 꼴)."""
    record(ev, out=out, tgt=tgt, det=det, claimed=claimed, why=why)


# ------------------------------------------------------------------ 시간 묶음
def count(summary: str, code: str) -> None:
    """시간 묶음 사건 하나를 센다(`SUMMARY_*`)."""
    if not _STATE.enabled:
        return
    try:
        moment = now()
        hour = _hour_of(moment)
        key = text.clean_text(code, 60) or "-"
        closed = None
        with _LOCK:
            bucket = _STATE.buckets.get(summary)
            if bucket is not None and bucket.hour != hour:
                closed = _STATE.buckets.pop(summary)
                bucket = None
            if bucket is None:
                bucket = _STATE.buckets.setdefault(summary, _Bucket(hour))
            if key in bucket.counts or _room_for(bucket, key):
                bucket.counts[key] = bucket.counts.get(key, 0) + 1
            else:
                bucket.counts[OTHER_KEY] = bucket.counts.get(OTHER_KEY, 0) + 1
        if closed is not None:
            _close_bucket(summary, closed)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("감사 시간 묶음을 세지 못했습니다.")


def _room_for(bucket: _Bucket, key: str) -> bool:
    """새 키를 건수 표에 따로 둘 자리가 있나 — 키 수 상한과 키 글 바이트 상한을 함께 본다.

    무인증 요청이 고른 사유 코드가 키가 되므로, 키 수만 막으면 긴 코드 몇십 개로 한 줄이 1KB 를
    넘는다. `other` 자리는 늘 남겨 둔다.
    """
    if len(bucket.counts) >= DET_COUNTS_LIMIT - 1:
        return False
    used = sum(len(name.encode("utf-8")) + _COUNT_KEY_OVERHEAD for name in bucket.counts)
    wanted = len(key.encode("utf-8")) + _COUNT_KEY_OVERHEAD
    return used + wanted + len(OTHER_KEY) + _COUNT_KEY_OVERHEAD <= COUNTS_KEY_BUDGET


def note_denied(loginid: str, reason: str) -> None:
    """명단 밖 접속 — 계정마다 그 시간의 첫 건만 한 줄, 나머지는 시간 묶음 건수."""
    if not _STATE.enabled:
        return
    actor = normalize_actor(loginid)
    hour = _hour_of(now())
    first = False
    closed = None
    with _LOCK:
        bucket = _STATE.buckets.get(SUMMARY_DENIED)
        if bucket is not None and bucket.hour != hour:
            closed = _STATE.buckets.pop(SUMMARY_DENIED)
            bucket = None
        if bucket is None:
            bucket = _STATE.buckets.setdefault(SUMMARY_DENIED, _Bucket(hour))
        bucket.counts["total"] = bucket.counts.get("total", 0) + 1
        if actor not in bucket.accounts and len(bucket.accounts) < MAX_QUEUE:
            bucket.accounts.add(actor)
            bucket.firsts += 1
            first = True
    if closed is not None:
        _close_bucket(SUMMARY_DENIED, closed)
    if first:
        record(
            "authz_fail_access_list",
            out="denied",
            actor=actor,
            verified=True,
            why=reason,
            det={"reason": reason},
        )


def _yields_line(summary: str, bucket: _Bucket) -> bool:
    """닫으면 한 줄이 나오는 묶음인가 — 명단 밖은 되풀이가 있을 때만(첫 건은 이미 줄이 있다)."""
    if summary == SUMMARY_DENIED:
        return bucket.counts.get("total", 0) > bucket.firsts
    return bool(bucket.counts)


def _close_bucket(summary: str, bucket: _Bucket, *, partial: bool = False) -> None:
    """닫힌 시간 묶음을 한 줄로. `partial` 은 정시 전에 앞당겨 닫은 줄(같은 시간에 줄이 더 온다)."""
    if not _yields_line(summary, bucket):
        return
    if summary == SUMMARY_DENIED:
        det: dict[str, object] = {
            "total": bucket.counts.get("total", 0),
            "accounts": bucket.firsts,
            "hour": bucket.hour,
        }
    else:
        det = {
            "counts": dict(bucket.counts),
            "total": sum(bucket.counts.values()),
            "hour": bucket.hour,
        }
    if partial:
        det[PARTIAL_KEY] = True
    record(summary, actor="", det=det, lvl=_SUMMARY_LEVELS.get(summary))


def close_finished_buckets() -> None:
    """정시를 넘긴 묶음을 한 줄씩 낸다(비우기가 맨 앞에서 부른다)."""
    hour = _hour_of(now())
    with _LOCK:
        finished = [
            (name, bucket) for name, bucket in _STATE.buckets.items() if bucket.hour != hour
        ]
        for name, _ in finished:
            del _STATE.buckets[name]
    for name, bucket in finished:
        _close_bucket(name, bucket)


def close_open_buckets() -> None:
    """아직 열린 이 시간 묶음까지 지금 한 줄씩 낸다(`partial`) — 「지금 올리기」 가 부른다.

    CI/CD 로 pod 이 바뀌면 메모리 누계가 사라지므로 올리기 바로 앞에 앞당겨 닫는다. 같은 시간의
    나머지는 새 묶음으로 세어 정시 뒤 한 줄이 더 나온다(화면은 줄마다 더한다). 명단 밖은 그 시간에
    첫 줄을 낸 계정을 그대로 기억해 같은 계정의 첫 줄을 다시 내지 않는다.
    """
    if not _STATE.enabled:
        return
    close_finished_buckets()
    with _LOCK:
        opened = list(_STATE.buckets.items())
        for name, bucket in opened:
            if name == SUMMARY_DENIED:
                _STATE.buckets[name] = _Bucket(bucket.hour, accounts=bucket.accounts)
            else:
                del _STATE.buckets[name]
    for name, bucket in opened:
        _close_bucket(name, bucket, partial=True)


def open_summary_lines() -> int:
    """열린 시간 묶음 가운데 닫으면 한 줄이 나오는 수 — 「감사 미전송」 에 더한다(메모리만)."""
    with _LOCK:
        return sum(1 for name, bucket in _STATE.buckets.items() if _yields_line(name, bucket))


# ------------------------------------------------------------------ 꺼내기
def take_pending() -> list[dict[str, Any]]:
    """큐를 비워 돌려준다(비우기 잠금 안에서 `spool.drain` 만 부른다).

    버린 수가 있으면 끝에 한 줄을 더한다.
    """
    if not _STATE.enabled:
        return []
    close_finished_buckets()
    with _LOCK:
        dropped = _STATE.dropped
        _STATE.dropped = 0
    if dropped:
        line = build_line(
            "sys_audit_dropped",
            out="fail",
            who=Actor("", False, "none"),
            det={"count": dropped},
        )
        with _LOCK:
            _STATE.queue.append(line)
    with _LOCK:
        taken = list(_STATE.queue)
        _STATE.queue.clear()
    return taken


def requeue_front(lines: list[dict[str, Any]]) -> None:
    """스풀에 적지 못한 줄을 큐 앞에 돌려놓는다(다음 비우기가 같은 차례로 다시 적는다)."""
    with _LOCK:
        _STATE.queue.extendleft(reversed(lines))
        while len(_STATE.queue) > MAX_QUEUE:
            _STATE.queue.pop()
            _STATE.dropped += 1
            _STATE.dropped_total += 1


def note_dropped(count: int) -> None:
    """비우기가 꺼냈지만 적을 수 없어 버린 줄 — 다음 비우기의 `sys_audit_dropped` 에 더한다."""
    if count <= 0:
        return
    with _LOCK:
        _STATE.dropped += count
        _STATE.dropped_total += count


def pending_count() -> int:
    with _LOCK:
        return len(_STATE.queue)


def dropped_total() -> int:
    """기동 뒤 기록하지 못하고 버린 줄 누계 — 큐 넘침과 해시를 못 매긴 줄을 같이 센다(`AD-12`
    「기록 못 한 줄 n」)."""
    with _LOCK:
        return _STATE.dropped_total


# ------------------------------------------------------------------ 통합인증 사건 대응표
_SESSION_CLOSED: Final[Mapping[str, tuple[str, str]]] = {
    "expired": ("session_expired", "success"),
    "revoked": ("session_revoked", "success"),
    "denied": ("authz_fail_session", "denied"),
    "invalid": ("session_invalid", "fail"),
}


def _field(fields: Mapping[str, str], key: str) -> str:
    value = fields.get(key, "")
    return "" if value in ("", "-") else value


def _number(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def from_sso_event(
    event: str, fields: Mapping[str, str], extra: Mapping[str, str] | None = None
) -> None:
    """통합인증 사건(`auth/runtime.record_event`) → 감사 줄. 대응표 밖 사건은 남기지 않는다.

    이벤트 루프에서도 불린다 — 해석기를 부르지 않고 사건의 loginid 를 행위자로 쓴다(서명이 통과한
    토큰 · 우리 쿠키에서 온 값이라 `verified`). 예외를 올리지 않는다.
    """
    if not _STATE.enabled:
        return
    try:
        _map_sso(event, fields, extra or {})
    except Exception:  # noqa: BLE001
        _LOGGER.exception("통합인증 사건을 감사 기록으로 옮기지 못했습니다.")


def _map_sso(event: str, fields: Mapping[str, str], extra: Mapping[str, str]) -> None:
    loginid = _field(fields, "loginid")
    reason = _field(fields, "reason")
    if event == "login_ok":
        record(
            "authn_login_success",
            actor=loginid,
            verified=True,
            sid8=_field(fields, "sid"),
            name=extra.get("name") or None,
            ip="",
            det={
                "hours": _number(_field(fields, "hours")),
                "max_hours": _number(_field(fields, "max_hours")),
            },
        )
    elif event == "login_fail" and loginid:
        record(
            "authn_login_fail",
            out="fail",
            actor=loginid,
            verified=True,
            why=reason,
            det={"reason": reason},
        )
    elif event in ("login_fail", "idp_error"):
        code = reason or _field(fields, "error") or "-"
        count(SUMMARY_LOGIN_FAIL, f"{event}:{code}")
    elif event == "login_denied":
        note_denied(loginid, reason)
    elif event == "username_missing":
        record("authn_username_missing", out="fail", actor=loginid, verified=True)
    elif event == "logout":
        record("session_logout", actor=loginid, verified=True, sid8=_field(fields, "sid"))
    elif event == "session_closed":
        mapped = _SESSION_CLOSED.get(reason)
        if mapped is None or not loginid:
            count(SUMMARY_LOGIN_FAIL, f"session:{reason or '-'}")
            return
        name, outcome = mapped
        det: dict[str, object] = {"reason": reason}
        if name == "session_expired":
            det = {"end": _field(fields, "end") or "-"}
        record(name, out=outcome, actor=loginid, verified=True, why=reason, det=det)
    elif event == "cert_expiring":
        record("sys_cert_expiring", actor=SYSTEM_SSO, det={"days": _number(_field(fields, "days"))})
    elif event == "access_read" and reason:
        record(
            "sys_access_read_fail",
            out="fail",
            actor=SYSTEM_SSO,
            why=reason,
            det={"reason": reason, "status": _field(fields, "status") or None},
        )
    elif event in ("access_save_failed", "access_seed_mark_failed"):
        code = reason if event == "access_save_failed" else f"seed_mark:{reason}"
        record(
            "sys_access_save_fail",
            out="fail",
            actor=loginid or SYSTEM_SSO,
            verified=bool(loginid),
            why=reason,
            det={"reason": code, "status": _field(fields, "status") or None},
        )
