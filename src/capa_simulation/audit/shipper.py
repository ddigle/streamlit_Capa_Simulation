# Purpose: 감사 스풀을 버킷 새 객체로 올리고 지난 날짜를 일별로 묶으며 보기 범위를 미러로 받는다.

"""감사 기록의 버킷 쪽(동기화 일꾼이 부른다 — 새 스레드를 세우지 않는다).

- **올리기(`ship`)** — 스풀의 아직 올리지 않은 줄을 `audit/v1/seg/…` 새 객체로 올리고 올림 표지를
  적는다. 조건부 쓰기(`If-None-Match: *`)를 쓰고, 지원이 확인되지 않은 버킷은 HEAD 로 없음을 본
  뒤 쓴다(키에 inst · seq 가 들어 있어 겹치는 경우는 같은 내용의 재시도뿐이다). 다른 인스턴스의
  남은 스풀도 함께 올린다.
- **일별 묶음(`compact`)** — 최근 14일의 지난 UTC 날짜마다 어느 manifest 에도 없는 조각을 모아
  `daily/…p<n>.jsonl.gz` · `.manifest.json` 을 새로 쓴다. manifest 는 바로 앞 manifest 의 sha256 을
  잇는다(같은 날짜면 앞 판, p0 이면 앞 날짜의 마지막 판). 이미 쓴 파일은 고치지 않는다.
- **미러(`mirror`)** — 보기 범위(400일)의 일별 파일과, 일별 파일이 아직 없는 최근 날짜의 조각을
  로컬로 받고, 일별 파일이 든 날짜의 다 올린 스풀을 지운다.

DB 올리기 판정 · `SY-03` 막힘과 상관없이 돈다. 실패는 여기서 삼키고 `sys_audit_ship_fail` 로
남긴다 — DB 동기화의 실패 수(`SY-02`)를 건드리지 않는다. 기록을 고치거나 지우는 기능은 없다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final, Protocol
from uuid import uuid4

from capa_simulation.audit import chain, layout, recorder, spool
from capa_simulation.io.object_storage import (
    ObjectRecord,
    ObjectStorageClient,
    classify_failure,
)

_LOGGER = logging.getLogger(__name__)

DRAIN_SECONDS: Final = 10.0
SHIP_EVERY_SECONDS: Final = 300.0
SHIP_LINES: Final = 200
SEGMENT_LINES: Final = 5_000
COMPACT_FIRST_SECONDS: Final = 600.0
COMPACT_EVERY_SECONDS: Final = 86_400.0
MIRROR_FIRST_SECONDS: Final = 60.0
SHIP_BACKOFF_SECONDS: Final = (60.0, 120.0, 300.0)
LATE_DAYS: Final = 14
MIRROR_DAYS: Final = 400
SKEW_LIMIT_SECONDS: Final = 60.0
OVERDUE_SECONDS: Final = 1_800.0

# 버킷 호출 하나 앞에 부른다 — 일꾼이 그 회차의 마감을 늘리고, 참을 돌려주면 「DB 올리기에
# 자리를 내줄 때」 다(정리의 `_prune_step` 과 같은 꼴). 일별 묶음 · 미러는 그때 멈추고 다음
# 고리에 잇는다.
Step = Callable[[], bool]


def _no_step() -> bool:
    return False


class _Yield(Exception):
    """일별 묶음 · 미러가 DB 올리기에 자리를 내주려 멈춘다(실패가 아니다)."""


def _pause_point(step: Step) -> None:
    if step():
        raise _Yield


class AuditBucket(Protocol):
    """감사 기록이 쓰는 버킷 동작 넷 — 목록 · 새 객체로만 쓰기 · 받기 · 객체 시각."""

    def records(self, prefix: str) -> tuple[ObjectRecord, ...]: ...

    def put_new(self, key: str, body: bytes) -> bool: ...

    def get(self, key: str) -> bytes: ...

    def modified(self, key: str) -> datetime | None: ...


@dataclass(frozen=True)
class ClientBucket:
    """`ObjectStorageClient` 위의 버킷. 작업 파일은 `scratch` 에 잠깐 두고 지운다."""

    client: ObjectStorageClient
    scratch: Path

    def records(self, prefix: str) -> tuple[ObjectRecord, ...]:
        return self.client.list_all_objects(prefix)

    def _temporary(self) -> Path:
        self.scratch.mkdir(parents=True, exist_ok=True)
        return self.scratch / f"audit-{uuid4().hex[:12]}.bin"

    def put_new(self, key: str, body: bytes) -> bool:
        """새 객체로 쓴다. 이미 있으면 `False`(쓰지 않음)."""
        source = self._temporary()
        source.write_bytes(body)
        digest = base64.b64encode(hashlib.md5(body, usedforsecurity=False).digest()).decode()
        try:
            if self.client.supports_conditional_put():
                outcome = self.client.put_file(
                    key, source, content_md5_base64=digest, if_none_match=True
                )
                return not outcome.precondition_failed
            if self.client.head(key) is not None:
                return False
            self.client.put_file(key, source, content_md5_base64=digest)
            return True
        finally:
            source.unlink(missing_ok=True)

    def get(self, key: str) -> bytes:
        destination = self._temporary()
        try:
            self.client.get_file(key, destination)
            return destination.read_bytes()
        finally:
            destination.unlink(missing_ok=True)

    def modified(self, key: str) -> datetime | None:
        record = self.client.head(key)
        return None if record is None else record.last_modified


# ------------------------------------------------------------------ 상태
@dataclass(frozen=True)
class AuditHealth:
    """감사 올리기 상태 — 화면(「감사 미전송」 · `AD-12` · `AD-13`)이 읽는 불변 사본."""

    worker: bool = False
    last_ship_utc: str | None = None
    failures: int = 0
    failure_kind: str | None = None
    unshipped_since: float | None = None
    skew_seconds: float | None = None
    late_keys: tuple[str, ...] = ()


_HEALTH_LOCK = threading.Lock()
_HEALTH = AuditHealth()


def health() -> AuditHealth:
    with _HEALTH_LOCK:
        return _HEALTH


def _note(**changes: Any) -> None:
    global _HEALTH
    with _HEALTH_LOCK:
        _HEALTH = replace(_HEALTH, **changes)


def reset() -> None:
    """시험 전용."""
    global _HEALTH
    with _HEALTH_LOCK:
        _HEALTH = AuditHealth()


def keeping_problems(*, managed: bool, now: float | None = None) -> tuple[str, ...]:
    """`AD-12` 의 까닭들 — 동기화 아님 · 큐 넘침 · 올리기 30분 넘게 밀림 · 시계 차이."""
    state = health()
    moment = time.monotonic() if now is None else now
    reasons: list[str] = []
    if not managed:
        reasons.append("동기화 아님")
    if recorder.dropped_total():
        reasons.append("큐 넘침")
    if state.unshipped_since is not None and moment - state.unshipped_since > OVERDUE_SECONDS:
        reasons.append("올리기 밀림")
    if state.skew_seconds is not None and abs(state.skew_seconds) > SKEW_LIMIT_SECONDS:
        reasons.append("시계 차이")
    return tuple(reasons)


def chain_problems() -> tuple[str, ...]:
    """`AD-13` 의 까닭 — 1판은 너무 늦게 온 조각(14일 넘음)."""
    return health().late_keys


# ------------------------------------------------------------------ 올리기
@dataclass(frozen=True)
class ShipOutcome:
    lines: int = 0
    keys: tuple[str, ...] = ()
    late: tuple[str, ...] = ()


def _chunks(lines: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(lines), size):
        yield lines[start : start + size]


def ship(
    bucket: AuditBucket,
    *,
    today: date,
    base: Path | None = None,
    step: Step = _no_step,
) -> ShipOutcome:
    """스풀의 아직 올리지 않은 줄을 새 조각으로 올린다(어느 인스턴스의 스풀이든)."""
    keys: list[str] = []
    late: list[str] = []
    count = 0
    oldest = (today - timedelta(days=LATE_DAYS)).isoformat()
    for path in spool.spool_files(base):
        parsed = spool.parse_spool_name(path)
        if parsed is None:
            continue
        day, inst = parsed
        for chunk in _chunks(spool.unshipped_lines(path), SEGMENT_LINES):
            first, last = _seq(chunk[0]), _seq(chunk[-1])
            key = layout.piece_key("seg", day, inst, first, last)
            step()
            bucket.put_new(key, layout.encode_lines(chunk))
            spool.mark_shipped(path, last)
            keys.append(key)
            count += len(chunk)
            if day < oldest:
                late.append(key)
    return ShipOutcome(count, tuple(keys), tuple(late))


def previous_tail(
    bucket: AuditBucket,
    *,
    own_inst: str,
    today: date,
    base: Path | None = None,
    step: Step = _no_step,
) -> dict[str, Any] | None:
    """앞 인스턴스의 마지막 줄 — 남은 스풀이 있으면 그것, 없으면 최근 이틀 조각 중 가장 늦은 것.

    순번이 정수가 아닌 줄은 끝 줄로 쓰지 않는다. 고른 조각이 깨졌거나 쓸 줄이 없으면 `None`(앞
    끝을 모름 — `end_mark none`)이다. 깨진 조각 하나가 새 인스턴스의 올리기를 막지 않게 한다.
    """
    tails: list[dict[str, Any]] = []
    for path in spool.spool_files(base):
        parsed = spool.parse_spool_name(path)
        if parsed is None or parsed[1] == own_inst:
            continue
        last_line = _last_numbered(spool.read_lines(path))
        if last_line is not None:
            tails.append(last_line)
    if tails:
        return max(tails, key=lambda line: (str(line.get("ts", "")), _seq(line)))
    candidates: list[ObjectRecord] = []
    for day in (today, today - timedelta(days=1)):
        step()
        for record in bucket.records(layout.piece_prefix("seg", day.isoformat())):
            parsed_piece = layout.parse_piece(record.key)
            if parsed_piece is not None and parsed_piece[2] != own_inst:
                candidates.append(record)
        if candidates:
            break
    if not candidates:
        return None
    latest = max(
        candidates,
        key=lambda item: (
            item.last_modified or datetime.min.replace(tzinfo=timezone.utc),
            item.key,
        ),
    )
    step()
    lines = layout.decode_or_none(bucket.get(latest.key))
    return None if lines is None else _last_numbered(lines)


def _seq(line: Mapping[str, Any]) -> int:
    """순번을 고른 줄(`chain.seq_of` 가 `None` 이 아닌 줄)의 순번."""
    return chain.seq_of(line) or 0


def _last_numbered(lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    """순번이 정수인 마지막 줄."""
    for line in reversed(lines):
        if chain.seq_of(line) is not None:
            return line
    return None


def note_chain_link(tail: Mapping[str, Any] | None) -> None:
    """새 인스턴스가 앞 인스턴스 끝 해시를 잇는 줄(`audit_chain_link`)."""
    seq = None if tail is None else chain.seq_of(tail)
    if tail is None or seq is None:
        recorder.record("audit_chain_link", actor="system:object_sync", det={"end_mark": "none"})
        return
    recorder.record(
        "audit_chain_link",
        actor="system:object_sync",
        det={
            "prev_inst": str(tail.get("inst", "")),
            "prev_seq": seq,
            "prev_h": str(tail.get("h", "")),
            "end_mark": "shutdown" if tail.get("ev") == "sys_shutdown" else "none",
        },
    )


# ------------------------------------------------------------------ 일별 묶음
@dataclass(frozen=True)
class CompactOutcome:
    written: tuple[str, ...] = ()
    interrupted: bool = False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compact(bucket: AuditBucket, *, today: date, step: Step = _no_step) -> CompactOutcome:
    """최근 14일의 지난 날짜마다 어느 manifest 에도 없는 조각을 새 판으로 묶는다(오래된 날부터).

    새 판 번호는 그 날짜에 있는 일별 파일 · manifest 가운데 가장 큰 번호 다음이다 — 일별 파일만
    들어가고 manifest 를 못 쓴 판이 남아도 그 번호를 다시 쓰지 않는다(남은 일별 파일은 미러 ·
    화면이 그대로 읽고 같은 (inst, seq) 는 하나만 쓴다). DB 올리기에 자리를 내줘야 하면 판 사이에서
    멈춘다(`interrupted`) — 다음 고리가 남은 날짜를 잇는다.
    """
    written: list[str] = []
    try:
        _pause_point(step)
        daily = [layout.parse_daily(record.key) for record in bucket.records(layout.DAILY_PREFIX)]
        manifests: dict[str, list[int]] = {}
        used: dict[str, int] = {}
        for parsed in daily:
            if parsed is None:
                continue
            used[parsed[0]] = max(used.get(parsed[0], -1), parsed[1])
            if parsed[2] == "manifest.json":
                manifests.setdefault(parsed[0], []).append(parsed[1])
        cache: dict[str, bytes] = {}

        def manifest_bytes(day: str, part: int) -> bytes:
            key = layout.manifest_key(day, part)
            if key not in cache:
                _pause_point(step)
                cache[key] = bucket.get(key)
            return cache[key]

        def latest_before(day: str) -> tuple[str, int] | None:
            earlier = [found for found in manifests if found < day]
            if not earlier:
                return None
            last_day = max(earlier)
            return last_day, max(manifests[last_day])

        for back in range(LATE_DAYS, 0, -1):
            day = (today - timedelta(days=back)).isoformat()
            pieces: list[str] = []
            for kind in ("seg", "tool"):
                _pause_point(step)
                pieces.extend(
                    record.key
                    for record in bucket.records(layout.piece_prefix(kind, day))
                    if layout.parse_piece(record.key) is not None
                )
            if not pieces:
                continue
            parts = sorted(manifests.get(day, []))
            covered: set[str] = set()
            for part in parts:
                covered.update(_segments_of(manifest_bytes(day, part)))
            fresh = sorted(set(pieces) - covered)
            if not fresh:
                continue
            lines: dict[tuple[str, int], dict[str, Any]] = {}
            readable: list[str] = []
            for key in fresh:
                _pause_point(step)
                decoded = layout.decode_or_none(bucket.get(key))
                if decoded is None:
                    # 압축이 깨진 조각은 판에 싣지 않는다 — 버킷에 남고 다음 묶음이 다시 본다.
                    _LOGGER.warning("감사 조각을 읽지 못해 일별 묶음에서 뺍니다: %s", key)
                    continue
                readable.append(key)
                for line in decoded:
                    seq = chain.seq_of(line)
                    if seq is not None:
                        lines.setdefault((str(line.get("inst", "")), seq), line)
            if not readable:
                continue
            fresh = readable
            ordered = [lines[key] for key in sorted(lines)]
            body = layout.encode_lines(ordered)
            part = used.get(day, -1) + 1
            previous: tuple[str, int] | None = (day, parts[-1]) if parts else latest_before(day)
            manifest = {
                "v": 1,
                "date": day,
                "part": part,
                "segments": fresh,
                "lines": len(ordered),
                "instances": _instances(ordered),
                "sha256": _sha256(body),
                "prev_manifest": None if previous is None else _sha256(manifest_bytes(*previous)),
            }
            manifest_body = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
            _pause_point(step)
            if not bucket.put_new(layout.daily_key(day, part), body):
                # 그 번호를 그 사이 누가 썼다 — 이번 판은 접고 다음 묶음이 새 번호로 다시 본다.
                used[day] = part
                continue
            used[day] = part
            step()
            if not bucket.put_new(layout.manifest_key(day, part), manifest_body):
                continue
            cache[layout.manifest_key(day, part)] = manifest_body
            manifests.setdefault(day, []).append(part)
            written.append(layout.daily_key(day, part))
    except _Yield:
        return CompactOutcome(tuple(written), interrupted=True)
    return CompactOutcome(tuple(written))


def _segments_of(manifest: bytes) -> set[str]:
    """manifest 가 덮은 조각 키. 읽지 못하는 manifest 는 빈 집합이다 — 그 조각들은 다음 판이 한 번
    더 묶는다(같은 (inst, seq) 는 화면이 하나만 쓴다)."""
    try:
        payload = json.loads(manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return set()
    segments = payload.get("segments") if isinstance(payload, dict) else None
    return {str(key) for key in segments} if isinstance(segments, list) else set()


def _instances(lines: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, object]]:
    """인스턴스마다 첫 · 끝 seq 와 끝 해시(순번을 고른 줄만 받는다)."""
    first: dict[str, int] = {}
    last: dict[str, tuple[int, object]] = {}
    for line in lines:
        inst = str(line.get("inst", ""))
        seq = _seq(line)
        first[inst] = min(first.get(inst, seq), seq)
        if inst not in last or seq >= last[inst][0]:
            last[inst] = (seq, line.get("h", ""))
    return {
        inst: {"first": first[inst], "last": last[inst][0], "last_h": last[inst][1]}
        for inst in first
    }


# ------------------------------------------------------------------ 미러
@dataclass(frozen=True)
class MirrorOutcome:
    downloaded: tuple[str, ...] = ()
    pruned: tuple[Path, ...] = ()
    interrupted: bool = False


def _fetch(bucket: AuditBucket, base: Path, record: ObjectRecord, step: Step) -> bool:
    target = layout.mirror_path(base, record.key)
    try:
        if target.stat().st_size == record.size_bytes:
            return False
    except OSError:
        pass
    _pause_point(step)
    data = bucket.get(record.key)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    temporary.write_bytes(data)
    temporary.replace(target)
    return True


def mirror(
    bucket: AuditBucket,
    *,
    today: date,
    base: Path | None = None,
    step: Step = _no_step,
) -> MirrorOutcome:
    """보기 범위의 일별 파일 · 일별 파일이 없는 최근 날짜의 조각을 받고 스풀을 정리한다.

    manifest 는 받지 않는다(화면이 읽지 않는다). 받은 파일은 다시 받지 않으므로 DB 올리기에 자리를
    내주려 멈춰도(`interrupted` — 빈 디스크로 뜬 서버의 첫 미러) 다음 고리가 남은 것만 잇는다.
    멈춘 회차에는 스풀을 지우지 않는다.
    """
    root = spool.root() if base is None else base
    oldest = (today - timedelta(days=MIRROR_DAYS)).isoformat()
    downloaded: list[str] = []
    daily_dates: set[str] = set()
    try:
        _pause_point(step)
        for record in bucket.records(layout.DAILY_PREFIX):
            parsed = layout.parse_daily(record.key)
            if parsed is None or parsed[0] < oldest or parsed[2] != "jsonl.gz":
                continue
            if _fetch(bucket, root, record, step):
                downloaded.append(record.key)
            daily_dates.add(parsed[0])
        for back in range(0, LATE_DAYS + 1):
            day = (today - timedelta(days=back)).isoformat()
            if day in daily_dates:
                continue
            for kind in ("seg", "tool"):
                _pause_point(step)
                for record in bucket.records(layout.piece_prefix(kind, day)):
                    if layout.parse_piece(record.key) is None:
                        continue
                    if _fetch(bucket, root, record, step):
                        downloaded.append(record.key)
    except _Yield:
        return MirrorOutcome(tuple(downloaded), interrupted=True)
    pruned = spool.prune(daily_dates, root)
    return MirrorOutcome(tuple(downloaded), tuple(pruned))


# ------------------------------------------------------------------ 일꾼의 할 일
def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AuditTasks:
    """동기화 일꾼이 고리마다 묻는 감사 할 일 — 비우기 · 올리기 · 일별 묶음 · 미러.

    시계는 일꾼과 같은 단조 시계다. 모든 실패를 여기서 삼킨다(일꾼의 DB 실패 수를 건드리지 않는다).
    """

    bucket: AuditBucket
    clock: Callable[[], float] = time.monotonic
    today: Callable[[], date] = _utc_today
    wall: Callable[[], datetime] = _utc_now
    base: Path | None = None
    _drain_at: float = field(default=0.0, init=False)
    _ship_at: float = field(default=0.0, init=False)
    _retry_at: float = field(default=0.0, init=False)
    _compact_at: float = field(default=0.0, init=False)
    _mirror_at: float = field(default=0.0, init=False)
    _failures: int = field(default=0, init=False)
    _linked: bool = field(default=False, init=False)
    _skew_checked: bool = field(default=False, init=False)
    _leftover: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        started = self.clock()
        self._drain_at = started
        self._ship_at = started
        self._retry_at = started
        self._compact_at = started + COMPACT_FIRST_SECONDS
        self._mirror_at = started + MIRROR_FIRST_SECONDS
        own = recorder.instance_id()
        self._leftover = any(
            (spool.parse_spool_name(path) or ("", own))[1] != own
            and bool(spool.unshipped_lines(path))
            for path in spool.spool_files(self.base)
        )
        _note(worker=True)

    # --------------------------------------------------------------- 때
    def drain(self, now: float) -> None:
        self._drain_at = now + DRAIN_SECONDS
        try:
            spool.drain()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("감사 기록을 스풀에 비우지 못했습니다.")
        pending = spool.unshipped_count()
        state = health()
        if pending and state.unshipped_since is None:
            _note(unshipped_since=now)
        elif not pending and state.unshipped_since is not None:
            _note(unshipped_since=None)

    def ship_due(self, now: float) -> bool:
        if now < self._retry_at:
            return False
        if self._leftover:
            return True
        pending = spool.unshipped_count()
        return pending >= SHIP_LINES or (pending > 0 and now >= self._ship_at)

    def compact_due(self, now: float) -> bool:
        return now >= self._compact_at

    def mirror_due(self, now: float) -> bool:
        return now >= self._mirror_at

    def next_due(self, now: float) -> float:
        moments = [self._drain_at, self._compact_at, self._mirror_at]
        if self._leftover or spool.unshipped_count():
            moments.append(max(self._ship_at, self._retry_at))
        return min(moments)

    # --------------------------------------------------------------- 일
    def run_ship(self, now: float, step: Step = _no_step) -> None:
        """올리기 한 번. 처음이면 앞 인스턴스와 사슬을 먼저 잇는다."""
        try:
            if not self._linked:
                note_chain_link(
                    previous_tail(
                        self.bucket,
                        own_inst=recorder.instance_id(),
                        today=self.today(),
                        base=self.base,
                        step=step,
                    )
                )
                self._linked = True
                spool.drain()
            outcome = ship(self.bucket, today=self.today(), base=self.base, step=step)
            for key in outcome.late:
                parsed = layout.parse_piece(key)
                recorder.record(
                    "audit_late_segment",
                    out="unknown",
                    actor="system:object_sync",
                    det={"date": "" if parsed is None else parsed[1], "key": key},
                )
            if outcome.late:
                _note(late_keys=(*health().late_keys, *outcome.late))
            if outcome.keys and not self._skew_checked:
                self._check_skew(outcome.keys[-1], step)
        except Exception as exc:  # noqa: BLE001 — 감사 실패가 DB 동기화를 멈추지 않는다
            self._fail(now, exc)
            return
        self._failures = 0
        self._leftover = False
        self._ship_at = now + SHIP_EVERY_SECONDS
        self._retry_at = now
        _note(
            failures=0,
            failure_kind=None,
            last_ship_utc=recorder.ts_text(self.wall()),
            unshipped_since=None if not spool.unshipped_count() else health().unshipped_since,
        )

    def run_compact(self, now: float, step: Step = _no_step) -> None:
        """일별 묶음 한 번. DB 올리기에 자리를 내주려 멈췄으면 다음 고리에 잇는다."""
        self._compact_at = now + COMPACT_EVERY_SECONDS
        try:
            outcome = compact(self.bucket, today=self.today(), step=step)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("감사 기록 일별 묶음이 실패했습니다.")
            return
        if outcome.interrupted:
            self._compact_at = now
            return
        self._mirror_at = now

    def run_mirror(self, now: float, step: Step = _no_step) -> None:
        """미러 한 번. 멈췄으면 다음 고리에 남은 것만 받는다."""
        self._mirror_at = now + COMPACT_EVERY_SECONDS
        try:
            outcome = mirror(self.bucket, today=self.today(), base=self.base, step=step)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("감사 기록 미러를 받지 못했습니다.")
            return
        if outcome.interrupted:
            self._mirror_at = now

    def _check_skew(self, key: str, step: Step) -> None:
        sent = self.wall()
        step()
        stored = self.bucket.modified(key)
        self._skew_checked = True
        if stored is None:
            return
        seconds = (sent - stored).total_seconds()
        _note(skew_seconds=seconds)
        if abs(seconds) > SKEW_LIMIT_SECONDS:
            recorder.record(
                "sys_clock_skew",
                out="fail",
                actor="system:object_sync",
                det={"seconds": round(seconds, 1)},
            )

    def _fail(self, now: float, exc: BaseException) -> None:
        self._failures += 1
        steps = SHIP_BACKOFF_SECONDS
        self._retry_at = now + steps[min(self._failures, len(steps)) - 1]
        kind = classify_failure(exc)
        _LOGGER.warning("감사 기록 올리기 실패 — %s", kind)
        _note(failures=self._failures, failure_kind=kind)
        recorder.record(
            "sys_audit_ship_fail",
            out="fail",
            actor="system:object_sync",
            det={"kind": kind, "failures": self._failures},
        )


def build_tasks(client: ObjectStorageClient) -> AuditTasks | None:
    """일꾼이 쓸 감사 할 일. 기록기가 꺼진 프로세스면 `None`(일꾼이 감사를 부르지 않는다)."""
    if not recorder.enabled():
        return None
    return AuditTasks(ClientBucket(client, spool.root() / "tmp"))
