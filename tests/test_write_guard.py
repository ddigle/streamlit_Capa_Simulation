# Purpose: 쓰기 거름이 같은 입력의 겹친 누름만 한 번으로 거르고 세션마다 따로 잠그는지 잰다.

"""`components/write_guard.write_once` — 입력 지문과 세션 잠금(2026-10-26 리뷰).

- **지문** — 표지는 세대와 입력 지문을 함께 든다. 쓴 뒤 둘째 누름이 아닌 조작에 끊겨 세대가
  그대로인 세션에서 다른 내용을 적어 누른 저장은 새로 쓴다. 세대만 보던 표지는 「이미 썼다」 로
  보고 쓰지 않은 채 옛 결과로 성공을 알렸다.
- **잠금** — 막을 것은 같은 세션의 겹친 두 회차뿐이다. 몇 초짜리 쓰기가 다른 세션의 쓰기를 세우지
  않는다(프로세스 잠금 하나이던 때는 다른 사용자의 VOC 글·기준선·설비 DB 쓰기까지 그 잠금에서 섰다).
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any

import pytest

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.write_guard import write_once

COUNTER = "test_write_guard_generation"


class _Sessions:
    """스레드마다 다른 세션 칸 — `write_guard.st` 대역. 스레드가 `use` 로 제 세션을 고른다."""

    def __init__(self) -> None:
        self._local = threading.local()

    def use(self, state: dict[str, Any]) -> None:
        self._local.state = state

    @property
    def session_state(self) -> dict[str, Any]:
        state = getattr(self._local, "state", None)
        assert isinstance(state, dict)
        return state


@pytest.fixture
def sessions(monkeypatch: pytest.MonkeyPatch) -> _Sessions:
    fake = _Sessions()
    monkeypatch.setattr(write_guard, "st", fake)
    return fake


def test_a_press_with_the_same_input_writes_once_and_a_different_input_writes_again(
    sessions: _Sessions,
) -> None:
    """같은 세대·같은 지문은 한 번, 지문이 다르면 같은 세대라도 다시 쓴다.

    지나간 세대는 쓰지 않는다.
    """
    sessions.use({})
    written: list[str] = []

    assert write_once(COUNTER, 0, lambda: written.append("첫"), fingerprint=("첫 저장안", None))
    # 겹쳐 온 같은 누름 — 쓰지 않고 뒷정리만 잇게 True.
    assert write_once(COUNTER, 0, lambda: written.append("또"), fingerprint=("첫 저장안", None))
    assert written == ["첫"]
    # 쓴 뒤 끊겨 세대가 그대로인 세션에서 다른 이름으로 누른 저장.
    assert write_once(COUNTER, 0, lambda: written.append("둘째"), fingerprint=("둘째 저장안", None))
    assert written == ["첫", "둘째"]
    # 세대가 오른 뒤의 옛 화면 누름.
    sessions.session_state[COUNTER] = 1
    assert not write_once(COUNTER, 0, lambda: written.append("옛"), fingerprint=("옛", None))
    assert written == ["첫", "둘째"]


def test_a_failed_write_leaves_no_mark(sessions: _Sessions) -> None:
    """쓰기 예외는 표지를 남기지 않는다 — 같은 입력으로 다시 누르면 다시 쓴다."""
    sessions.use({})
    written: list[str] = []

    def fail() -> None:
        raise RuntimeError("쓰기 실패 대역")

    with pytest.raises(RuntimeError):
        write_once(COUNTER, 0, fail, fingerprint="같은 입력")
    assert write_once(COUNTER, 0, lambda: written.append("다시"), fingerprint="같은 입력")
    assert written == ["다시"]


def test_a_long_write_holds_only_its_own_session(sessions: _Sessions) -> None:
    """한 세션의 몇 초짜리 쓰기 동안 다른 세션의 쓰기는 지나가고, 같은 세션의 겹친 회차만
    기다린다."""
    first_session: dict[str, Any] = {}
    other_session: dict[str, Any] = {}
    entered = threading.Event()
    finish = threading.Event()
    done = SimpleNamespace(other=threading.Event(), same=threading.Event())
    written: list[str] = []

    def long_write() -> None:
        written.append("긴 쓰기")
        entered.set()
        assert finish.wait(10)

    def run(state: dict[str, Any], write: Any, fingerprint: str, flag: threading.Event) -> None:
        sessions.use(state)
        write_once(COUNTER, 0, write, fingerprint=fingerprint)
        flag.set()

    long = threading.Thread(
        target=run, args=(first_session, long_write, "긴", threading.Event()), daemon=True
    )
    long.start()
    assert entered.wait(10)
    other = threading.Thread(
        target=run,
        args=(other_session, lambda: written.append("남의 쓰기"), "남", done.other),
        daemon=True,
    )
    same = threading.Thread(
        target=run,
        args=(first_session, lambda: written.append("같은 세션"), "같은", done.same),
        daemon=True,
    )
    other.start()
    same.start()
    try:
        assert done.other.wait(5), "다른 세션의 쓰기가 긴 쓰기의 잠금에서 섰다"
        assert not done.same.wait(0.3), "같은 세션의 겹친 회차가 긴 쓰기를 기다리지 않았다"
    finally:
        finish.set()
    assert done.same.wait(10)
    long.join(10)
    assert sorted(written) == sorted(["긴 쓰기", "남의 쓰기", "같은 세션"])
