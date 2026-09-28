# Purpose: 적용하지 않은 편집이 남은 탭에 점을 찍는 CSS 와 편집 판정을 검증한다.

from __future__ import annotations

import pytest
import streamlit as st

from capa_simulation.components.tab_marks import editor_has_edits, pending_tabs_style

LABELS = (
    ":material/calculate: 환산",
    ":material/edit_calendar: PKG PLAN",
    ":material/percent: 수율",
)


def test_no_pending_tab_means_no_rule() -> None:
    assert pending_tabs_style("plan_tabs", LABELS, set()) == ""


def test_the_dot_goes_on_the_pending_tab_position_only() -> None:
    style = pending_tabs_style("plan_tabs", LABELS, {LABELS[1], LABELS[2]})

    assert '.st-key-plan_tabs [data-testid="stTab"]:nth-child(2)' in style
    assert '.st-key-plan_tabs [data-testid="stTab"]:nth-child(3)' in style
    assert ":nth-child(1)" not in style
    # 탭 안의 탭(안쪽 탭 본문 아래 단추)은 고르지 않는다.
    assert ':not(.st-key-plan_tabs [data-testid="stTabPanel"] *)' in style


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (None, False),
        ({"edited_rows": {}, "added_rows": [], "deleted_rows": []}, False),
        ({"edited_rows": {0: {"2026-01": 1.0}}, "added_rows": [], "deleted_rows": []}, True),
        ({"edited_rows": {}, "added_rows": [{"공정": "A"}], "deleted_rows": []}, True),
        ({"edited_rows": {}, "added_rows": [], "deleted_rows": [3]}, True),
    ],
)
def test_an_editor_has_edits_only_when_a_change_is_recorded(
    state: dict[str, object] | None, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_state: dict[str, object] = {} if state is None else {"sheet": state}
    monkeypatch.setattr(st, "session_state", fake_state)
    assert editor_has_edits("sheet") is expected
