# Purpose: 감사 기록의 버킷 키 · 로컬 미러 자리 · 압축 꼴을 한곳에 둔다(표준 라이브러리만).

"""감사 기록 자리 이름.

버킷 `audit/v1/` 아래 셋이다. 모두 새 객체로만 쓰고 고치거나 지우지 않는다.

- `seg/YYYY/MM/DD/<inst>__<첫 seq>-<끝 seq>.jsonl.gz` — 동기화 일꾼이 스풀을 올린 줄 묶음.
- `tool/YYYY/MM/DD/<inst>__<첫 seq>-<끝 seq>.jsonl.gz` — 사내 PC 도구(`sync_object_storage.py`)가
  명령마다 올리는 한 줄.
- `daily/YYYY/MM/DD.p<n>.jsonl.gz` · `.p<n>.manifest.json` — 일꾼이 지난 날짜를 합친 일별 묶음.

날짜는 사건의 UTC 날짜다. 로컬 미러는 같은 키를 `<스풀 뿌리>/mirror/` 아래에 그대로 둔다.
"""

from __future__ import annotations

import gzip
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

from capa_simulation.audit import chain

PREFIX: Final = "audit/v1/"
SEG_PREFIX: Final = f"{PREFIX}seg/"
TOOL_PREFIX: Final = f"{PREFIX}tool/"
DAILY_PREFIX: Final = f"{PREFIX}daily/"
MIRROR_DIR: Final = "mirror"

_DATE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PIECE: Final = re.compile(
    r"^audit/v1/(?P<kind>seg|tool)/(?P<y>\d{4})/(?P<m>\d{2})/(?P<d>\d{2})/"
    r"(?P<inst>[0-9a-z]{1,32})__(?P<first>\d{10})-(?P<last>\d{10})\.jsonl\.gz$"
)
_DAILY: Final = re.compile(
    r"^audit/v1/daily/(?P<y>\d{4})/(?P<m>\d{2})/(?P<d>\d{2})\.p(?P<part>\d+)"
    r"\.(?P<kind>jsonl\.gz|manifest\.json)$"
)


def _day(date: str) -> str:
    if not _DATE.match(date):
        raise ValueError(f"UTC 날짜 꼴이 아닙니다: {date!r}")
    return date.replace("-", "/")


def piece_key(kind: str, date: str, inst: str, first: int, last: int) -> str:
    """`seg` · `tool` 조각 키."""
    if kind not in ("seg", "tool"):
        raise ValueError(kind)
    return f"{PREFIX}{kind}/{_day(date)}/{inst}__{first:010d}-{last:010d}.jsonl.gz"


def piece_prefix(kind: str, date: str) -> str:
    return f"{PREFIX}{kind}/{_day(date)}/"


def daily_key(date: str, part: int) -> str:
    return f"{DAILY_PREFIX}{_day(date)}.p{part}.jsonl.gz"


def manifest_key(date: str, part: int) -> str:
    return f"{DAILY_PREFIX}{_day(date)}.p{part}.manifest.json"


def daily_month_prefix(date: str) -> str:
    return f"{DAILY_PREFIX}{_day(date)[:7]}/"


def parse_piece(key: str) -> tuple[str, str, str, int, int] | None:
    """조각 키 → (갈래, 날짜, inst, 첫 seq, 끝 seq). 꼴이 아니면 `None`."""
    found = _PIECE.match(key)
    if found is None:
        return None
    date = f"{found['y']}-{found['m']}-{found['d']}"
    return found["kind"], date, found["inst"], int(found["first"]), int(found["last"])


def parse_daily(key: str) -> tuple[str, int, str] | None:
    """일별 키 → (날짜, 판 번호, `jsonl.gz` | `manifest.json`). 꼴이 아니면 `None`."""
    found = _DAILY.match(key)
    if found is None:
        return None
    return f"{found['y']}-{found['m']}-{found['d']}", int(found["part"]), found["kind"]


def mirror_path(root: Path, key: str) -> Path:
    """버킷 키의 로컬 미러 자리."""
    if not key.startswith(PREFIX) or ".." in key.split("/"):
        raise ValueError(f"감사 키가 아닙니다: {key!r}")
    return root / MIRROR_DIR / Path(*key.split("/"))


def encode_lines(lines: Iterable[Mapping[str, Any]]) -> bytes:
    """줄들 → gzip 바이트(같은 줄이면 같은 바이트 — 시각 칸 0)."""
    body = "".join(chain.dump(line) + "\n" for line in lines).encode("utf-8")
    return gzip.compress(body, mtime=0)


def decode_lines(data: bytes) -> list[dict[str, Any]]:
    """gzip 바이트 → 줄들. 읽지 못한 줄은 건너뛴다."""
    return parse_text(gzip.decompress(data).decode("utf-8", errors="replace"))


def parse_text(text: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            lines.append(parsed)
    return lines
