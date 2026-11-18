# Purpose: 저장소 쓰기 함수에 다는 감사 표지 — 쓰기 앞 등급 벽, 끝난 뒤(COMMIT 뒤) 한 줄, 예외면
# 실패 한 줄.

"""데이터 작업 감사 표지(표준 라이브러리만).

`@audited("data_scenario_delete", describe)` 를 저장소 쓰기 함수에 단다. 함수가 돌아온 뒤 —
쓰기 트랜잭션이 COMMIT 하고 연결을 닫은 뒤 — 한 줄을 넣고, 예외가 나면 `out=fail` 한 줄을 넣고
예외를 그대로 올린다. 행위자는 기록기가 그 순간 정한다(스크립트 스레드면 쿠키를 다시 검증한
loginid, 예약 · 일꾼 스레드면 `system:*`).

- **등급 벽이 맨 앞이다**(`auth/grades.py`). 바깥 쓰기(등급 깊이 0)에서만 그 사건의 바닥 동작
  (`grades.EVENT_FLOORS` — 같은 사건이 더 높은 몫이면 `action=`)을 지금 쓰는 사람의 실제 등급으로
  본다. 기록기가 꺼진 프로세스(운영 + 통합인증 꺼짐 포함)에서도 선다. 판정기가 꽂히지 않은
  프로세스(스크립트 · 저장소 시험)는 지나간다.
- 함수 안에서 난 등급 거절(설비 저장의 내용 대조)은 작업 실패 줄을 남기지 않고 그대로 나간다 —
  거절 한 번 = 감사 한 줄(`authz_fail_grade` — 판정이 남긴다).
- 기록기가 꺼진 프로세스는 벽 다음에 원래 함수만 부른다(인자 묶기도 하지 않는다).
- 표지를 단 함수가 표지를 단 다른 함수를 부르면 바깥 줄만 남긴다(한 동작 = 한 줄).
- `describe(인자, 결과)` 는 대상 id · 이름표 · 상세(값 원문 없이)를 짓는다. 실패 줄에서는 결과가
  `None` 이다. `describe` 가 실패해도 저장을 막지 않는다(대상 없는 줄로 남긴다).
- 한 번의 쓰기가 여러 대상을 고치면(목록 관리의 이름 · 순서 일괄 저장) `@audited_each` 를 단다 —
  `describe` 가 (사건, 줄) 목록을 돌려주고 대상마다 한 줄을 남긴다. 실패면 같은 목록이 모두
  `out=fail` 이다.
"""

from __future__ import annotations

import functools
import inspect
import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar

from capa_simulation.audit import recorder
from capa_simulation.auth import grades

_LOGGER = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

# 표지를 단 함수의 사건 이름(`audited_each` 는 낼 수 있는 사건 튜플) — 시험이 설계 표와 맞댄다.
EVENT_ATTRIBUTE = "__audit_event__"


@dataclass(frozen=True)
class WorkNote:
    """작업 한 줄의 대상 · 상세 · 손입력 이름(인증 신원과 다를 때만 남는다)."""

    tgt: Mapping[str, object] | None = None
    det: Mapping[str, object] | None = None
    claimed: str | None = None


Describe = Callable[[Mapping[str, Any], Any], WorkNote]
DescribeEach = Callable[[Mapping[str, Any], Any], Sequence[tuple[str, WorkNote]]]

_DEPTH = threading.local()


def _single(ev: str, describe: Describe | None) -> DescribeEach:
    def each(args: Mapping[str, Any], result: Any) -> Sequence[tuple[str, WorkNote]]:
        return [(ev, WorkNote() if describe is None else describe(args, result))]

    return each


def _notes(
    fallback: str,
    describe: DescribeEach,
    signature: inspect.Signature,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    result: Any,
) -> Sequence[tuple[str, WorkNote]]:
    try:
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        return list(describe(dict(bound.arguments), result))
    except Exception:  # noqa: BLE001 — 기록 꼴 때문에 저장을 막지 않는다
        _LOGGER.exception("감사 작업 줄을 짓지 못했습니다: %s", fallback)
        return [(fallback, WorkNote())]


def _record(notes: Sequence[tuple[str, WorkNote]], *, out: str, why: str | None = None) -> None:
    for ev, note in notes:
        recorder.note_work(ev, out=out, tgt=note.tgt, det=note.det, claimed=note.claimed, why=why)


def _wall_action(events: tuple[str, ...], action: str | None) -> str:
    """벽에 쓸 동작 — 준 `action`, 아니면 사건들의 바닥 가운데 가장 높은 것."""
    if action is not None:
        grades.need_of(action)
        return action
    chosen = grades.highest(grades.floor_of(event) for event in events)
    return grades.UNMAPPED_ACTION if chosen is None else chosen


def _wrapped(
    marker: str | tuple[str, ...], fallback: str, describe: DescribeEach, action: str
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def wrap(function: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(function)

        @functools.wraps(function)
        def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            with grades.outer_wall(action):
                if not recorder.enabled() or getattr(_DEPTH, "inside", False):
                    return function(*args, **kwargs)
                _DEPTH.inside = True
                try:
                    result = function(*args, **kwargs)
                except grades.REFUSALS:
                    raise
                except Exception as exc:
                    notes = _notes(fallback, describe, signature, args, kwargs, None)
                    _record(notes, out="fail", why=type(exc).__name__)
                    raise
                finally:
                    _DEPTH.inside = False
            _record(_notes(fallback, describe, signature, args, kwargs, result), out="success")
            return result

        setattr(inner, EVENT_ATTRIBUTE, marker)
        setattr(inner, grades.GATE_ATTRIBUTE, action)
        return inner

    return wrap


def audited(
    ev: str, describe: Describe | None = None, *, action: str | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """저장소 쓰기 함수에 등급 벽과 감사 줄 하나를 단다(모듈 설명). `action` 은 같은 사건이 바닥보다
    높은 몫일 때만 준다."""
    return _wrapped(ev, ev, _single(ev, describe), _wall_action((ev,), action))


def audited_each(
    events: tuple[str, ...], describe: DescribeEach, *, action: str | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """여러 대상을 한 번에 고치는 쓰기 함수에 등급 벽과 대상마다 한 줄을 단다(모듈 설명). `events`
    는 낼 수 있는 사건 — 첫째가 `describe` 가 실패했을 때의 대상 없는 줄이다. 벽은 사건들의 바닥
    가운데 가장 높은 것(또는 준 `action`)이다."""
    return _wrapped(events, events[0], describe, _wall_action(events, action))
