# Purpose: Dynamic Capa 화면이 상수 데모와 공정 요약을 세션에 한 번만 만들고 같은 값을 쓰는지 본다.

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_reference_integrity_page import _priority_frame

from capa_simulation.services import dynamic_capacity
from capa_simulation.services.dynamic_capacity import (
    aggregate_dynamic_capacity,
    build_dynamic_capacity_demo,
)

DEMO_MEMO_KEY = "dynamic_capacity_demo_memo"

SCRIPT = r"""
from pathlib import Path

import capa_simulation
import capa_simulation.components.process_labels as process_labels_module

original_get_process_labels = process_labels_module.get_process_labels
process_labels_module.get_process_labels = lambda: process_labels_module.ProcessLabels()
try:
    page = Path(capa_simulation.__file__).resolve().parents[2] / "app_pages"
    source = page / "reference_integrity.py"
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"))
finally:
    process_labels_module.get_process_labels = original_get_process_labels
"""

# 받은 표를 고치는 화면 — 페이지를 돌린 뒤 받은 두 표에서 행을 지운다(제자리 고침).
EDITING_SCRIPT = SCRIPT.replace(
    """    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"))
""",
    """    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"))
    demo.drop(index=demo.index[:1], inplace=True)
    process_summary.drop(index=process_summary.index[:1], inplace=True)
""",
)


@pytest.fixture
def demo_builds(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def counting() -> pd.DataFrame:
        calls.append(1)
        return build_dynamic_capacity_demo()

    monkeypatch.setattr(dynamic_capacity, "build_dynamic_capacity_demo", counting)
    return calls


def _fresh() -> tuple[pd.DataFrame, pd.DataFrame]:
    demo = build_dynamic_capacity_demo()
    summary = aggregate_dynamic_capacity(demo, ["공정"]).sort_values(
        ["Capa 실현률", "공정"], kind="stable"
    )
    return demo, summary


def _run(app: AppTest, tab: str | None = None) -> AppTest:
    if tab is not None:
        app.session_state["dynamic_capa_active_tab"] = tab
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def test_the_demo_is_built_once_per_session_and_keeps_its_values(demo_builds: list[int]) -> None:
    app = _run(AppTest.from_string(SCRIPT, default_timeout=60))
    first_priority = _priority_frame(app)
    for tab in ("공정 상세", "산식 가이드", "요약"):
        _run(app, tab)
    _run(app)

    assert len(demo_builds) == 1
    # 화면을 여러 번 그린 뒤에도 기억한 표는 새로 만든 표와 같다.
    demo, summary = app.session_state[DEMO_MEMO_KEY]
    expected_demo, expected_summary = _fresh()
    pd.testing.assert_frame_equal(demo, expected_demo)
    pd.testing.assert_frame_equal(summary, expected_summary)
    pd.testing.assert_frame_equal(_priority_frame(app), first_priority)


def test_a_new_session_builds_its_own_demo(demo_builds: list[int]) -> None:
    _run(AppTest.from_string(SCRIPT, default_timeout=60))
    _run(AppTest.from_string(SCRIPT, default_timeout=60))

    assert len(demo_builds) == 2


def test_the_detail_tab_still_follows_its_filters(demo_builds: list[int]) -> None:
    """상세 집계는 기억하지 않는다 — 공정을 바꾸면 그 회차에 지표가 바뀐다."""
    app = _run(AppTest.from_string(SCRIPT, default_timeout=60), "공정 상세")
    picker = app.selectbox(key="dynamic_capacity_process_filter")
    before: dict[str, Any] = {metric.label: metric.value for metric in app.metric}
    other = next(option for option in picker.options if option != picker.value)

    picker.set_value(other)
    _run(app)

    after: dict[str, Any] = {metric.label: metric.value for metric in app.metric}
    assert after != before
    assert len(demo_builds) == 1


def test_a_caller_that_edits_the_frames_leaves_the_memo_intact(demo_builds: list[int]) -> None:
    """기억한 표는 사본으로 나간다 — 받은 쪽이 제자리에서 고쳐도 다음 회차의 데모·요약은
    그대로다."""
    assert EDITING_SCRIPT != SCRIPT
    app = _run(AppTest.from_string(EDITING_SCRIPT, default_timeout=60))
    first_priority = _priority_frame(app)
    _run(app)

    assert len(demo_builds) == 1
    demo, summary = app.session_state[DEMO_MEMO_KEY]
    expected_demo, expected_summary = _fresh()
    pd.testing.assert_frame_equal(demo, expected_demo)
    pd.testing.assert_frame_equal(summary, expected_summary)
    pd.testing.assert_frame_equal(_priority_frame(app), first_priority)
