# Purpose: 브라우저 표의 출납(반영되지 않은 조작 전부)에서 아직 반영하지 않은 op 만 골라 늘어놓는다.

"""설비 마스터 표와 시나리오 목록 표가 함께 쓰는 출납 규약(AGENTS 9장).

브라우저는 상태 값 `outbox`(``{"mount", "ops": [...]}``)로 반영되지 않은 조작을 **전부** 보낸다.
같은 출납이 여러 회차에 다시 와도 마운트 → 마지막으로 반영한 seq 기억으로 한 번만 반영하고, 어느
콜백이 먼저 불려도 `(at, mount, seq)` 같은 차례다. op 의 뜻과 `base` 대조는 부르는 쪽 몫이다.

두 표의 `base` 는 `세션 표지:나머지` 꼴이다. 세션이 바뀐 뒤 브라우저가 다시 보낸 앞 세션의 출납은
고른 쪽이 말없이 뺀다(`this_session`) — 그 손실은 재시작 · 세션 만료 알림이 이미 알렸다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

# 출납 반영 기억의 마운트 수. 넘으면 오래 안 보낸 마운트부터 잊는다.
MOUNT_LIMIT: Final = 20


def op_seq(value: object) -> int | None:
    """op 의 번호 — 1 이상의 정수가 아니면 None."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _session_part(base: object) -> str | None:
    """`base` 의 세션 표지 — `세션 표지:나머지` 꼴이 아니면 None."""
    if not isinstance(base, str) or ":" not in base:
        return None
    return base.partition(":")[0]


def this_session(ops: Iterable[dict[str, Any]], base: str) -> list[dict[str, Any]]:
    """지금 `base` 와 세션 표지가 같은 op 만 남긴다. 표지가 없는 쪽은 가르지 못해 남긴다."""
    session = _session_part(base)
    if session is None:
        return list(ops)
    return [op for op in ops if _session_part(op.get("base")) in (session, None)]


def pending_ops(
    outboxes: Iterable[object], applied: Mapping[str, int]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """마운트들의 출납에서 아직 반영하지 않은 op 만 `(at, mount, seq)` 차례로 고른다.

    `outboxes` 는 마운트마다의 상태 값 `outbox`(``{"mount", "ops": [...]}``) — 꼴이 다른 것은
    버린다. `applied` 는 마운트 → 마지막으로 반영한 seq 다. 같은 출납이 여러 회차에 다시 와도 한
    번이고, 어느 콜백이 먼저 불려도 같은 차례다. 돌려준 기억은 이번에 본 마운트를 맨 뒤로 옮기고
    `MOUNT_LIMIT` 을 넘으면 오래된 것부터 잊는다. op 에는 `mount` 를 붙여 돌려준다."""
    memory = dict(applied)
    picked: list[dict[str, Any]] = []
    for outbox in outboxes:
        if not isinstance(outbox, Mapping):
            continue
        mount = outbox.get("mount")
        ops = outbox.get("ops")
        if not isinstance(mount, str) or not mount or not isinstance(ops, list):
            continue
        last = memory.get(mount, 0)
        newest = last
        for op in ops:
            if not isinstance(op, Mapping):
                continue
            seq = op_seq(op.get("seq"))
            if seq is None or seq <= last:
                continue
            picked.append({**op, "mount": mount})
            newest = max(newest, seq)
        memory.pop(mount, None)
        memory[mount] = newest
    while len(memory) > MOUNT_LIMIT:
        memory.pop(next(iter(memory)))

    def order(op: Mapping[str, Any]) -> tuple[float, str, int]:
        at = op.get("at")
        moment = float(at) if isinstance(at, (int, float)) and not isinstance(at, bool) else 0.0
        return (moment, str(op["mount"]), int(op["seq"]))

    picked.sort(key=order)
    return picked, memory
