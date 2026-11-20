# Purpose: 목록 관리 두 칸이 오른쪽 칸 · 갈래와 상관없이 이벤트 칸에 같은 수의 자리를 쓰는지 잰다.

"""목록 관리 두 칸(`components/scenario_management._render_list_management`)의 이벤트 칸 자리 수.

구역 회차(AGENTS 9장 「구역 회차 규칙」 R5)는 이벤트 칸 쓰기 자리를 구역 자리로 되돌려 받은
자리만 갈아 끼운다 — 칸 · 갈래마다 스타일만 든 `st.html` 수가 다르면 뒤 페이지 요소(공식 지정
팝업 호스트)를 덮거나 낡은 요소가 남는다. 결과 칸(`render_flash`)이 서지 않는 갈래는 빈 스타일로
그 자리를 채운다.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from fragment_browser import install_fragment_browser
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script

from capa_simulation.components.scenario_management import SIDE_KEY, SIDES

PAGE_PATH = "app_pages/scenario_management.py"


def _event_slot_count(messages: Sequence[ForwardMsg]) -> int:
    """그 회차가 이벤트 칸(본문 밖 최상위 칸)에 쓴 자리 수."""
    count = 0
    for message in messages:
        if message.WhichOneof("type") != "delta":
            continue
        path = list(message.metadata.delta_path)
        if len(path) == 2 and path[0] == RootContainer.EVENT:
            count = max(count, path[1] + 1)
    return count


def test_every_side_writes_the_same_event_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """오른쪽 칸 다섯(상세 · 점검 · 저장 전 변경 · 공식 이력 · 보관함)이 이벤트 칸에 같은 수의
    자리를 쓴다 — 결과 칸이 없는 공식 이력 · 보관함도 빈 스타일 한 자리다."""
    browser = install_fragment_browser(monkeypatch)
    script = _page_script(PAGE_PATH, tmp_path / "scenario.duckdb", tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120)
    counts: dict[str, int] = {}
    for side in SIDES:
        app.session_state[SIDE_KEY] = side
        app.run()
        assert not app.exception, [element.message for element in app.exception]
        counts[side] = _event_slot_count(browser.messages)

    assert len(set(counts.values())) == 1, counts
