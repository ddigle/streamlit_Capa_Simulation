# Purpose: 새 코드가 세션 칸을 읽고 쓰는 한 창구 — 칸 이름 · 꼴 · 처음 값을 선언 한 줄로 묶는다.

"""세션 칸 창구(AGENTS.md 5장 42).

세션 상태(`st.session_state`)를 바로 읽고 쓰는 자리는 화면 코드 곳곳으로 퍼졌다 — 세는 법과
기준선은 `tests/test_session_state_sites.py` · `tests/session_state_baseline.py` 다. 한 번에 다
옮기지 않는다.
**새 코드는 칸을 `SessionSlot` 으로 선언하고 그 메서드로만 읽고 쓴다** — 바로 쓰는 자리가 기준선보다
늘면 그 시험이 실패한다. 옛 자리를 고칠 때 이 창구로 옮기면 기준선을 낮춘다.

- 칸 이름은 소유 모듈의 `*_KEY` 상수로 둔다 — 키 겹침 그물(`tests/test_session_key_collisions.py`,
  AGENTS 14-5)이 그 상수를 본다. 다른 모듈은 그 `SessionSlot` 을 import 한다(이름을 두 곳에 적지
  않는다).
- `get` 은 칸이 비었거나 선언한 꼴이 아닌 값(앞 판이 남긴 다른 꼴)이면 처음 값을 돌려주고 칸에 적지
  않는다. 바뀌는 그릇(dict · list)을 제자리에서 고치려면 `setdefault` 로 칸에 든 것을 받는다.
- 「있거나 없음」 칸(받은 파일 · 메모처럼 처음 값을 지을 수 없는 칸)은 처음 값 없이 선언하고 `peek`
  로 읽는다 — 비었거나 꼴이 다르면 None 이다. 그 칸의 `get` · `setdefault` 는 `LookupError` 다.
- 위젯 key 칸도 같은 창구다 — 위젯을 만들기 **전에** `set` 한다(만든 뒤에 쓰면 Streamlit 이 예외를
  낸다, 9장).
- 큰 표 · 화면 조각을 칸에 두는 규칙(5장 20 · 33 등)은 그대로다 — 이 창구는 읽고 쓰는 자리를 한
  꼴로 모을 뿐 무엇을 둘지는 정하지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

import streamlit as st

T = TypeVar("T")


@dataclass(frozen=True)
class SessionSlot(Generic[T]):
    """세션 칸 하나 — 이름(`key`) · 꼴(`kind`, `isinstance` 로 본다) · 처음 값을 짓는 함수(없으면
    「있거나 없음」 칸 — `peek` 로 읽는다)."""

    key: str
    kind: type[T]
    initial: Callable[[], T] | None = None

    def get(self) -> T:
        """칸의 값. 비었거나 꼴이 다르면 처음 값(칸에 적지 않는다)."""
        value = self.peek()
        return value if value is not None else self._initial()

    def peek(self) -> T | None:
        """칸의 값 — 비었거나 꼴이 다르면 None(처음 값을 짓지 않는다)."""
        value = st.session_state.get(self.key)
        return value if isinstance(value, self.kind) else None

    def setdefault(self) -> T:
        """칸의 값 — 비었거나 꼴이 다르면 처음 값을 적고 그것을 돌려준다(제자리에서 고칠 그릇)."""
        value = self.peek()
        if value is not None:
            return value
        fresh = self._initial()
        st.session_state[self.key] = fresh
        return fresh

    def set(self, value: T) -> None:
        st.session_state[self.key] = value

    def clear(self) -> None:
        """칸을 지운다 — 없으면 그대로."""
        st.session_state.pop(self.key, None)

    def exists(self) -> bool:
        return self.key in st.session_state

    def _initial(self) -> T:
        if self.initial is None:
            raise LookupError(f"세션 칸 {self.key} 은 처음 값이 없습니다 — peek 로 읽습니다")
        return self.initial()
