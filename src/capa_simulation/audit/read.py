# Purpose: 감사 기록 읽기 — 스풀 · 미러 파일을 KST 기간으로 골라 겹침 없이 줄로 돌려준다.

"""로컬 파일만 읽는다(표준 라이브러리만). 화면 회차가 S3 를 기다리지 않는다.

UTC 날짜마다 **일별 파일(p0, p1 …)이 미러에 있으면 그것을, 없으면 그 날짜의 스풀 + 미러 조각을**
읽는다 — 아직 묶지 않은 오늘 · 어제도 빠지지 않는다. 같은 (inst, seq) 가 두 곳에 있으면 하나만
쓴다. 시각은 저장이 UTC 이고 화면은 KST(+09:00 고정 — 일광 절약 시간이 없다)다. `astimezone()` 처럼
서버 시각대에 기대는 변환은 쓰지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

from capa_simulation.audit import chain, layout, spool

KST: Final = timezone(timedelta(hours=9), "KST")
KST_FORMAT: Final = "%Y-%m-%d %H:%M:%S"


def parse_ts(value: str) -> datetime | None:
    """`2026-11-13T07:51:02.123Z` → 시각대가 붙은 UTC 시각. 시각대가 없으면 `None`(견줄 수 없다)."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return None if moment.tzinfo is None else moment


def kst_text(value: str) -> str:
    moment = parse_ts(value)
    return "" if moment is None else moment.astimezone(KST).strftime(KST_FORMAT)


def kst_today(now: datetime | None = None) -> date:
    moment = datetime.now(timezone.utc) if now is None else now
    return moment.astimezone(KST).date()


def kst_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """KST 날짜 [start, end] → UTC 시각 [처음, 끝 다음 날 0시)."""
    first = datetime(start.year, start.month, start.day, tzinfo=KST)
    after = datetime(end.year, end.month, end.day, tzinfo=KST) + timedelta(days=1)
    return first.astimezone(timezone.utc), after.astimezone(timezone.utc)


def utc_dates(start: date, end: date) -> list[str]:
    """KST 날짜 범위가 걸치는 UTC 날짜들(KST 하루는 UTC 두 날짜에 걸친다)."""
    first, after = kst_bounds(start, end)
    day = first.date()
    last = (after - timedelta(microseconds=1)).date()
    dates: list[str] = []
    while day <= last:
        dates.append(day.isoformat())
        day += timedelta(days=1)
    return dates


def files_for(base: Path, utc_date: str) -> list[Path]:
    """그 UTC 날짜를 읽을 파일들 — 일별 파일이 있으면 그것만, 없으면 스풀 + 미러 조각."""
    year, month, day = utc_date.split("-")
    daily_folder = base / layout.MIRROR_DIR / "audit" / "v1" / "daily" / year / month
    dailies = sorted(daily_folder.glob(f"{day}.p*.jsonl.gz")) if daily_folder.is_dir() else []
    if dailies:
        return dailies
    found = [
        path
        for path in spool.spool_files(base)
        if (spool.parse_spool_name(path) or ("", ""))[0] == utc_date
    ]
    for kind in ("seg", "tool"):
        folder = base / layout.MIRROR_DIR / "audit" / "v1" / kind / year / month / day
        if folder.is_dir():
            found.extend(sorted(folder.glob("*.jsonl.gz")))
    return found


def _read(path: Path) -> list[dict[str, Any]]:
    try:
        if path.name.endswith(".gz"):
            return layout.decode_lines(path.read_bytes())
        return layout.parse_text(path.read_text(encoding="utf-8", errors="replace"))
    except (*layout.UNREADABLE, ValueError):
        return []


def fingerprint(base: Path, start: date, end: date) -> tuple[object, ...]:
    """읽을 파일 목록 · 크기 · 수정 시각 · 기간 — 같으면 다시 읽지 않는다(세션 칸의 키)."""
    parts: list[object] = [start.isoformat(), end.isoformat()]
    for utc_date in utc_dates(start, end):
        for path in files_for(base, utc_date):
            try:
                stat = path.stat()
            except OSError:
                continue
            parts.append((str(path), stat.st_size, stat.st_mtime_ns))
    return tuple(parts)


def load_lines(base: Path, start: date, end: date) -> list[dict[str, Any]]:
    """KST 기간 [start, end] 의 줄들(시각 차례). 같은 (inst, seq) 는 하나만.

    시각 · 순번 꼴이 아닌 줄(바깥에서 고친 조각)은 건너뛴다 — 깨진 줄 하나가 탭을 멈추지 않게.
    """
    first, after = kst_bounds(start, end)
    seen: set[tuple[str, int]] = set()
    rows: list[tuple[datetime, str, int, dict[str, Any]]] = []
    for utc_date in utc_dates(start, end):
        for line in _lines_of(files_for(base, utc_date)):
            moment = parse_ts(str(line.get("ts", "")))
            seq = chain.seq_of(line)
            if moment is None or seq is None or not first <= moment < after:
                continue
            key = (str(line.get("inst", "")), seq)
            if key in seen:
                continue
            seen.add(key)
            rows.append((moment, key[0], key[1], line))
    rows.sort(key=lambda item: (item[0], item[1], item[2]))
    return [line for *_, line in rows]


def _lines_of(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        yield from _read(path)
