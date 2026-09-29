# Purpose: 편집표 편집 여부 판정과 세대 키로 편집을 브라우저까지 버리는 초기화를 검증한다.

from __future__ import annotations

import pytest
import streamlit as st

from capa_simulation.components.editor_state import (
    discard_editor,
    editor_has_edits,
    editor_widget_key,
)

EDITED = {"edited_rows": {0: {"2026-01": 1.0}}, "added_rows": [], "deleted_rows": []}


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    fake: dict[str, object] = {}
    monkeypatch.setattr(st, "session_state", fake)
    return fake


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (None, False),
        ({"edited_rows": {}, "added_rows": [], "deleted_rows": []}, False),
        (EDITED, True),
        ({"edited_rows": {}, "added_rows": [{"공정": "A"}], "deleted_rows": []}, True),
        ({"edited_rows": {}, "added_rows": [], "deleted_rows": [3]}, True),
    ],
)
def test_an_editor_has_edits_only_when_a_change_is_recorded(
    state: dict[str, object] | None, expected: bool, session: dict[str, object]
) -> None:
    if state is not None:
        session["sheet"] = state
    assert editor_has_edits("sheet") is expected


def test_the_first_generation_keeps_the_plain_key(session: dict[str, object]) -> None:
    """세대 0 은 원래 키 그대로다 — 기존 세션·테스트와 맞는다."""
    assert editor_widget_key("sheet") == "sheet"


def test_discarding_moves_the_editor_to_a_new_widget(session: dict[str, object]) -> None:
    """세션 칸만 지우면 브라우저가 옛 편집을 다시 보낸다. 버리면 위젯 키 자체가 바뀐다."""
    session["sheet"] = EDITED
    discard_editor("sheet")

    assert "sheet" not in session
    assert editor_widget_key("sheet") == "sheet__g1"
    assert editor_has_edits("sheet") is False
    # 옛 키로 편집이 되돌아와도(브라우저가 다시 보낸 경우) 지금 편집표의 편집이 아니다.
    session["sheet"] = EDITED
    assert editor_has_edits("sheet") is False

    session["sheet__g1"] = EDITED
    discard_editor("sheet")
    assert "sheet__g1" not in session
    assert editor_widget_key("sheet") == "sheet__g2"
