# Purpose: 감사 기록 해시 사슬이 고침 · 빠짐 · 순서 바뀜 · 잘못된 첫 줄을 알아채는지 본다.

from __future__ import annotations

import json
from typing import Any

from capa_simulation.audit import chain


def _chain(count: int, inst: str = "abc123def456") -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    prev = chain.GENESIS
    for seq in range(1, count + 1):
        line = chain.seal(
            {"v": 1, "inst": inst, "ev": "session_created", "n": seq}, seq=seq, prev=prev
        )
        prev = line["h"]
        lines.append(line)
    return lines


def test_an_untouched_chain_has_no_problems() -> None:
    lines = _chain(5)

    assert chain.verify(lines) == ()
    assert lines[0]["prev"] == chain.GENESIS
    assert all(lines[i]["prev"] == lines[i - 1]["h"] for i in range(1, 5))


def test_a_changed_field_breaks_its_hash() -> None:
    lines = _chain(4)
    lines[2] = {**lines[2], "ev": "session_logout"}

    assert [(p.seq, p.kind) for p in chain.verify(lines)] == [(3, "hash")]


def test_a_resealed_line_breaks_the_link_to_the_next() -> None:
    lines = _chain(4)
    lines[1] = chain.seal({**lines[1], "ev": "x"}, seq=2, prev=lines[0]["h"])

    assert [(p.seq, p.kind) for p in chain.verify(lines)] == [(3, "link")]


def test_a_missing_line_is_a_gap() -> None:
    lines = _chain(5)
    del lines[2]

    assert [(p.seq, p.kind) for p in chain.verify(lines)] == [(4, "gap")]


def test_swapped_lines_are_out_of_order() -> None:
    lines = _chain(4)
    lines[1], lines[2] = lines[2], lines[1]

    kinds = {p.kind for p in chain.verify(lines)}
    assert "order" in kinds


def test_a_first_line_that_does_not_start_from_genesis() -> None:
    line = chain.seal({"v": 1, "inst": "i"}, seq=1, prev="1" * 64)

    assert [p.kind for p in chain.verify([line])] == ["start"]


def test_two_instances_are_checked_apart_and_a_known_tail_joins_a_range() -> None:
    first = _chain(3, inst="aaaaaaaaaaaa")
    second = _chain(3, inst="bbbbbbbbbbbb")
    mixed = [first[0], second[0], first[1], second[1], first[2], second[2]]

    assert chain.verify(mixed) == ()
    tail = first[2:]
    assert chain.verify(tail, known={"aaaaaaaaaaaa": (2, first[1]["h"])}) == ()
    assert [p.kind for p in chain.verify(tail, known={"aaaaaaaaaaaa": (2, "f" * 64)})] == ["link"]


def test_the_dumped_line_reads_back_the_same_on_one_line() -> None:
    line = _chain(1)[0]
    dumped = chain.dump(line)

    assert json.loads(dumped) == line
    assert "\n" not in dumped
    assert chain.line_hash(line["prev"], json.loads(dumped)) == line["h"]
