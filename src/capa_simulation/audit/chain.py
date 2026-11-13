# Purpose: 감사 기록 해시 사슬 — 줄 정규화 · 해시 매김 · 고침 · 빠짐 · 순서 바뀜을 알아채는 검증.

"""해시 사슬(표준 라이브러리만).

줄마다 `h = sha256(prev + 정규화 JSON(h 를 뺀 줄))` 이다. 정규화는 키 정렬 · 공백 없음 · UTF-8 이다.
인스턴스(`inst`)마다 `seq` 가 1 부터 빈틈없이 늘고 첫 줄의 `prev` 는 `GENESIS` 다. 사슬은 「알아챔」
이지 「막음」 이 아니다 — 버킷 키를 가진 사람이 꼬리를 지우거나 통째로 다시 계산해 갈아 끼우는 것은
막지 못한다(설계서 4-5).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

GENESIS: Final = "0" * 64
HASH_KEY: Final = "h"


def canonical(line: Mapping[str, Any]) -> bytes:
    """`h` 를 뺀 줄의 정규화 바이트."""
    body = {key: value for key, value in line.items() if key != HASH_KEY}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def line_hash(prev: str, line: Mapping[str, Any]) -> str:
    return hashlib.sha256(prev.encode("ascii") + canonical(line)).hexdigest()


def seal(line: Mapping[str, Any], *, seq: int, prev: str) -> dict[str, Any]:
    """순번 · 앞 해시를 붙이고 이 줄의 해시를 매긴 새 줄."""
    sealed: dict[str, Any] = {**line, "seq": seq, "prev": prev}
    sealed[HASH_KEY] = line_hash(prev, sealed)
    return sealed


def dump(line: Mapping[str, Any]) -> str:
    """파일에 적는 한 줄(줄바꿈 없음). 사슬 해시와 같은 정규화 꼴이다."""
    return json.dumps(dict(line), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class ChainProblem:
    """끊긴 곳 하나 — 인스턴스 · 순번 · 갈래(`hash` 고침 · `link` 앞 줄과 안 이어짐 · `gap` 빠짐 ·
    `order` 순서 바뀜 · `start` 첫 줄이 GENESIS 가 아님)."""

    inst: str
    seq: int
    kind: str


def verify(
    lines: Iterable[Mapping[str, Any]],
    *,
    known: Mapping[str, tuple[int, str]] | None = None,
) -> tuple[ChainProblem, ...]:
    """주어진 차례대로 인스턴스마다 이어 본다.

    `known` 은 이 범위 앞에서 이미 확인한 인스턴스의 (끝 seq, 끝 h) — 기간 중간부터 읽을 때 쓴다.
    없고 첫 줄이 1번이 아니면 그 줄부터 잇는다(앞을 모른다). 1번 줄은 `prev` 가 `GENESIS` 여야 한다.
    """
    last: dict[str, tuple[int, str]] = dict(known or {})
    problems: list[ChainProblem] = []
    for line in lines:
        inst = str(line.get("inst", ""))
        seq = int(line.get("seq", 0))
        prev = str(line.get("prev", ""))
        stored = str(line.get(HASH_KEY, ""))
        if stored != line_hash(prev, line):
            problems.append(ChainProblem(inst, seq, "hash"))
        before = last.get(inst)
        if before is None:
            if seq == 1 and prev != GENESIS:
                problems.append(ChainProblem(inst, seq, "start"))
        else:
            before_seq, before_h = before
            if seq <= before_seq:
                problems.append(ChainProblem(inst, seq, "order"))
            elif seq != before_seq + 1:
                problems.append(ChainProblem(inst, seq, "gap"))
            elif prev != before_h:
                problems.append(ChainProblem(inst, seq, "link"))
        if before is None or seq > before[0]:
            last[inst] = (seq, stored)
    return tuple(problems)
