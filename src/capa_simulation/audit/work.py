# Purpose: 저장소 쓰기 함수에 다는 감사 표지 — 끝난 뒤(COMMIT 뒤) 한 줄, 예외면 실패 한 줄.

"""데이터 작업 감사 표지(표준 라이브러리만).

`@audited("data_scenario_delete", describe)` 를 저장소 쓰기 함수에 단다. 함수가 돌아온 뒤 —
쓰기 트랜잭션이 COMMIT 하고 연결을 닫은 뒤 — 한 줄을 넣고, 예외가 나면 `out=fail` 한 줄을 넣고
예외를 그대로 올린다. 행위자는 기록기가 그 순간 정한다(스크립트 스레드면 쿠키를 다시 검증한
loginid, 예약 · 일꾼 스레드면 `system:*`).

- 기록기가 꺼진 프로세스는 첫 줄에서 원래 함수만 부른다(인자 묶기도 하지 않는다).
- 표지를 단 함수가 표지를 단 다른 함수를 부르면 바깥 한 줄만 남긴다(한 동작 = 한 줄).
- `describe(인자, 결과)` 는 대상 id · 이름표 · 상세(값 원문 없이)를 짓는다. 실패 줄에서는 결과가
  `None` 이다. `describe` 가 실패해도 저장을 막지 않는다(대상 없는 줄로 남긴다).
"""

from __future__ import annotations

import functools
import inspect
import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar

from capa_simulation.audit import recorder

_LOGGER = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

EVENT_ATTRIBUTE = "__audit_event__"


@dataclass(frozen=True)
class WorkNote:
    """작업 한 줄의 대상 · 상세 · 손입력 이름(인증 신원과 다를 때만 남는다)."""

    tgt: Mapping[str, object] | None = None
    det: Mapping[str, object] | None = None
    claimed: str | None = None


Describe = Callable[[Mapping[str, Any], Any], WorkNote]

_DEPTH = threading.local()


def _note(
    ev: str,
    describe: Describe | None,
    signature: inspect.Signature,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    result: Any,
    *,
    out: str,
    why: str | None = None,
) -> None:
    note = WorkNote()
    if describe is not None:
        try:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            note = describe(dict(bound.arguments), result)
        except Exception:  # noqa: BLE001 — 기록 꼴 때문에 저장을 막지 않는다
            _LOGGER.exception("감사 작업 줄을 짓지 못했습니다: %s", ev)
    recorder.note_work(ev, out=out, tgt=note.tgt, det=note.det, claimed=note.claimed, why=why)


def audited(
    ev: str, describe: Describe | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """저장소 쓰기 함수에 감사 줄 하나를 단다(모듈 설명)."""

    def wrap(function: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(function)

        @functools.wraps(function)
        def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            if not recorder.enabled() or getattr(_DEPTH, "inside", False):
                return function(*args, **kwargs)
            _DEPTH.inside = True
            try:
                result = function(*args, **kwargs)
            except Exception as exc:
                _note(
                    ev, describe, signature, args, kwargs, None, out="fail", why=type(exc).__name__
                )
                raise
            finally:
                _DEPTH.inside = False
            _note(ev, describe, signature, args, kwargs, result, out="success")
            return result

        setattr(inner, EVENT_ATTRIBUTE, ev)
        return inner

    return wrap
