# Purpose: 서버 값을 브라우저가 든 위젯에 닿게 하는 key 세대와 쓰기 단추 세대를 한 곳에서 짓는다.

"""위젯 key 세대 — 브라우저가 든 위젯에 서버 값을 닿게 하는 길과 쓰기 단추의 세대.

**세션 칸에 값을 적는 것만으로는 브라우저가 든 위젯이 바뀌지 않을 때가 있다**(AGENTS 9장).

- 브라우저는 위젯마다 제 값을 쥐고 다음 조작에 되보낸다. 서버가 그 칸을 지우거나(`pop`)
  그린 **뒤**에 적은 값은 브라우저에 닿지 않는다. 그때 위젯을 정말로 버리는 길은 **key 를
  바꾸는 것**이다 — 세대 칸(`counter_key`)의 번호를 key 꼬리에 붙이고(`widget_key`)
  올리면(`bump`) 브라우저에게는 처음 보는 위젯이라 쥔 값을 보낼 곳이 없다(편집표 편집
  버리기·저장에 성공한 폼 비우기·범위 밖 글을 쥔 숫자 칸).
- **닫힌 팝오버·다이얼로그 안 칸**은 브라우저에 마운트되지 않는다. 나중에 열려 마운트될 때
  브라우저는 **마지막 회차가 실어 보낸 값**(`set_value`)으로 칸을 세우고, 없으면 빈
  기본값으로 세운다. 처음 그린 회차에 한 번 적은 값은 한 회차만 지나도 닿지 않는다
  (2026-10-26 E2E — 설비 시나리오 「리비전명」 칸이 빈 칸으로 서고 그대로 누른 저장이
  리비전명을 지웠다). 그런 칸은 `seed_field` 로 세운다 — 고치지 않은 동안 **매 회차** 서버
  값을 다시 적어 늘 실어 보낸다. key 세대만 바꾼 새 칸도 같다 — 새 칸은 빈 기본값으로
  서므로 비울 때는 `bump` 하나로 되지만, 서버 값으로 채우려면 실어 보내야 한다.

쓰기 단추도 같은 세대를 쓴다. 그린 회차의 세대(`generation`)와 그 쓰기의 입력 지문
(`fingerprint`)을 쓰기에 넘기면 `write_guard.write_once` 가 지나간 화면의 누름과 겹쳐 온 두 번
누름을 같은 입력마다 한 번으로 거른다. 겹쳐 온 둘째 회차는 쓰지 않고 끊긴 첫 회차의 뒷정리를
잇는데, 뒷정리가 쓰기의 결과(새 리비전·시나리오)를 써야 하면 그 결과를 `write_once_value` 가
세대·지문과 함께 든다. 끊긴 쓰기 뒤 다른 내용을 적어 누른 저장은 지문이 달라 새로 쓴다.

key 꼴은 넷이다. 옛 key 글자를 바이트까지 지킨다 — 바뀌면 배포 직후 열려 있던 세션의 칸이
한 번 비거나 새로 선다. `style` 이 꼬리 앞 글자이고, `bare_zero` 면 세대 0 은 바탕 key
그대로다.

=========  =====================  ==============================================
 style      세대 0 / 1             쓰는 곳
=========  =====================  ==============================================
 ``__g``    ``x`` / ``x__g1``      편집표·저장 폼 칸·VOC 폼·기준선 폼
 ``__g``    ``x__g0`` / ``x__g1``  기준선 저장 팝오버(``bare_zero=False``)
 ``_g``     ``x_g0`` / ``x_g1``    시나리오 관리 복제 폼 칸(``bare_zero=False``)
 ``__``     ``x`` / ``x__1``       버튼 + 직접 입력 숫자 칸
 ``__p``    ``x__p0`` / ``x__p1``  설비 시나리오 구획 팝오버(``bare_zero=False``)
=========  =====================  ==============================================

이 모듈 밖에서 세대 꼬리 글자를 손으로 짓지 않는다(`tests/test_widget_generation.py` 의 AST
그물).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar, cast

import streamlit as st

from capa_simulation.components.write_guard import current_generation, write_once

__all__ = [
    "KeyStyle",
    "SeededField",
    "Written",
    "bump",
    "generation",
    "seed_field",
    "widget_key",
    "write_once_value",
]

KeyStyle = Literal["__g", "_g", "__", "__p"]

T = TypeVar("T")

# 쓰기 결과(세대 칸 이름 → (그 세대, 입력 지문, 결과)). 세션마다 하나이고 `write_once_value` 가 쓰기
# **전에** 받아 둔다 — dict 칸 쓰기는 둘째 누름의 회차가 멈춤을 건 자리에서도 끊기지 않는다
# (`write_guard` 의 표지와 같은 까닭).
WRITE_RESULTS_KEY = "widget_generation_write_results"

# 처음 쓰는 두 회차가 결과 dict 를 따로 만들어 한쪽이 지워지지 않게 하는 잠금. 잠그는 동안
# 하는 일은 세션 칸 하나를 읽고 적는 것이다.
_RESULTS_LOCK = threading.Lock()


def generation(counter_key: str) -> int:
    """세대 칸의 지금 번호(없거나 정수가 아니면 0). 쓰기 거름(`write_once`)과 같은 읽기다."""
    return current_generation(counter_key)


def widget_key(
    base: str, counter_key: str, *, style: KeyStyle = "__g", bare_zero: bool = True
) -> str:
    """세대 칸 `counter_key` 의 지금 번호를 꼬리로 단 위젯 key.

    `bare_zero` 면 세대 0 은 `base` 그대로다 — 처음 그린 화면의 key 가 바뀌지 않는다. 꼴은
    모듈 머리말의 표.
    """
    number = generation(counter_key)
    if bare_zero and number <= 0:
        return base
    return f"{base}{style}{number}"


def bump(counter_key: str) -> int:
    """세대를 하나 올리고 새 번호를 돌려준다 — 다음 회차에 그 세대의 key 로 새 위젯이 선다.

    쓰기 뒷정리에서는 **맨 끝**에 부른다. 그 앞에서 끊기면 겹쳐 온 둘째 누름이 같은 세대로
    뒷정리를 잇는다.
    """
    number = generation(counter_key) + 1
    st.session_state[counter_key] = number
    return number


@dataclass(frozen=True)
class SeededField:
    """`seed_field` 가 세운 칸 — 그릴 위젯 key 와, 칸을 세울 때 본 값을 든 세션 칸 이름."""

    key: str
    seen_key: str


def seed_field(
    counter_key: str,
    base: str,
    value: object,
    *,
    suffix: str = "",
    style: KeyStyle = "__g",
    bare_zero: bool = True,
) -> SeededField:
    """닫힌 팝오버·다이얼로그 안 칸을 서버 값(`value`)으로 세운다 — 그런 칸을 채우는 유일한 길.

    칸 key 는 `widget_key(base, counter_key) + suffix` 다. 칸이 없거나 고치지 않은 동안(칸 값
    = 본 값) **매 회차** `value` 를 다시 적고 본 값(`seen_key`)도 그 값으로 둔다. 닫힌 칸은
    마지막 회차가 실어 보낸 값으로만 서므로(모듈 머리말) 한 회차라도 빼면 빈 칸으로 선다. 남이
    바꾼 값으로 다시 서는 것도 이 덕이다. 고치던 칸은 그대로 두고 본 값도 그대로다 — 비교 후
    쓰기는 그 본 값과 대조해 그 사이 남의 바꿈을 거절한다. 위젯을 그리기 **전**에 부른다.
    """
    key = widget_key(base, counter_key, style=style, bare_zero=bare_zero) + suffix
    seen_key = f"{key}__seen"
    if key not in st.session_state or st.session_state.get(key) == st.session_state.get(seen_key):
        st.session_state[key] = value
        st.session_state[seen_key] = value
    return SeededField(key=key, seen_key=seen_key)


@dataclass(frozen=True)
class Written(Generic[T]):
    """`write_once_value` 가 이 세대의 쓰기를 마쳤을 때의 답.

    `value` 는 그 쓰기의 결과다 — 이 누름이 썼든, 겹쳐 온 같은 누름(같은 세대·같은 지문)이 쓰고
    뒷정리 전에 끊겼든. 결과를 들지 못했으면(같은 세대 칸을 나눠 쓰는 다른 쓰기가 표지를 남겼다)
    `None` 이다. 뒷정리를 마친 뒤 `release()` 로 든 결과를 놓는다 — 큰 스냅샷을 세션에 붙잡아 두지
    않게. 놓지 못하고 끝난 결과(끊긴 회차·쓴 뒤 뒷정리 실패)는 그 세대 칸의 다음 쓰기가 바꿔 든다 —
    세대 칸마다 하나만 남는다.
    """

    value: T | None
    _results: dict[str, object] = field(repr=False, compare=False)
    _counter_key: str = field(repr=False, compare=False)
    _mark: tuple[int, Hashable] = field(repr=False, compare=False)

    def release(self) -> None:
        """든 결과를 놓는다 — dict 칸 지우기라 끊기지 않는다. 세대 올리기(`bump`) 뒤에 부른다.

        그 사이 다른 입력의 쓰기가 같은 칸에 든 결과는 놓지 않는다.
        """
        held = self._results.get(self._counter_key)
        if isinstance(held, tuple) and held[:2] == self._mark:
            self._results.pop(self._counter_key, None)


def _write_results() -> dict[str, object]:
    with _RESULTS_LOCK:
        results = st.session_state.get(WRITE_RESULTS_KEY)
        if not isinstance(results, dict):
            results = {}
            st.session_state[WRITE_RESULTS_KEY] = results
        return results


def write_once_value(
    counter_key: str,
    generation: int,
    write: Callable[[], T],
    *,
    fingerprint: Hashable,
) -> Written[T] | None:
    """`write_guard.write_once` 로 `write` 를 같은 입력마다 한 번 부르고 결과를 세대·지문과 든다.

    `fingerprint` 는 그 쓰기의 입력이다(`write_guard.write_once`) — 적은 이름·메모·붙여넣은 글과
    쓰는 대상(시나리오·리비전 id, 편집본 `content_token`)을 부르기 전에 읽어 짓는다. 시각·난수처럼
    회차마다 바뀌는 값은 넣지 않는다.

    - `None` — 지나간 화면의 누름이다(지금 세대가 다르다). 쓰지 않았다. 부르는 쪽은 알리지
      않는다.
    - `Written` — 이 세대의 이 입력 쓰기가 끝났다. 부르는 쪽은 `value` 로 뒷정리를 하고 **세대
      올리기를 맨 끝**에 둔다. 그 앞에서 끊기면 같은 입력의 다음 누름이 같은 결과로 뒷정리를 잇고,
      다른 입력의 누름은 새로 쓴다.

    `write` 안에서 세션 칸을 읽지 않는다 — 입력은 부르기 전에 읽어 둔다. `write` 가 던진 예외는
    그대로 나가고 표지를 남기지 않으므로 다시 누르면 다시 쓴다.
    """
    results = _write_results()

    def run() -> None:
        results[counter_key] = (generation, fingerprint, write())

    if not write_once(counter_key, generation, run, fingerprint=fingerprint):
        return None
    held = results.get(counter_key)
    value: T | None = None
    if (
        isinstance(held, tuple)
        and len(held) == 3
        and held[0] == generation
        and held[1] == fingerprint
    ):
        value = cast("T", held[2])
    return Written(
        value=value,
        _results=results,
        _counter_key=counter_key,
        _mark=(generation, fingerprint),
    )
