# Purpose: 설비 마스터 탭 회차 메모가 그대로인 회차에 다시 계산하지 않고 값이 새 계산과 같은지 본다.

"""설비 마스터 탭 고정비(표 단위 오류 앞 셋 · 일정 확인 · 다른 표 바뀐 행 수)의 회차 메모.

- **다시 도는 범위** — 편집본이 그대로인 회차(오른쪽 칸 바꾸기 · 그냥 다시 돌기)는 셋을 다시 내지
  않는다. 편집본이 바뀐 회차(표 출납 · 붙여넣기 · 저장)는 한 번씩 다시 낸다.
- **같은 값** — 메모 값은 그 회차의 편집본으로 새로 낸 값과 같다.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import astuple
from pathlib import Path
from typing import Any

import pytest
from grid_fake import Calls, install_fake_grid, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_master_tab import _app, _import, _rows

from capa_simulation.components import equipment_master_tab as emt
from capa_simulation.components.equipment_data_workspace import (
    BASELINE_DRAFT_KEY,
    BUFFER_KEY,
    DOWNTIME_DRAFT_KEY,
    EQUIPMENT_DRAFT_KEY,
    GRID_MEMO_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.services import equipment_grid as eg
from capa_simulation.services import equipment_validation as ev

COUNTED = ("_frame_errors", "_alert_pairs", "_changed_rows")


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """세 계산을 부른 수 — 메모가 빗나간 회차만 는다."""
    counter: Counter[str] = Counter()
    for name in COUNTED:
        original: Callable[..., Any] = getattr(emt, name)

        def counted(*args: Any, _name: str = name, _original: Any = original, **kwargs: Any) -> Any:
            counter[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(emt, name, counted)
    return counter


def _memo(app: AppTest) -> dict[str, Any]:
    memo = app.session_state[GRID_MEMO_KEY]
    assert isinstance(memo, dict)
    return memo


def _assert_memo_is_fresh(app: AppTest) -> None:
    """메모 값 = 지금 편집본 · 저장본 사본으로 새로 낸 값."""
    frames = app.session_state[BUFFER_KEY]
    saved = (
        app.session_state[BASELINE_DRAFT_KEY],
        app.session_state[EQUIPMENT_DRAFT_KEY],
        app.session_state[DOWNTIME_DRAFT_KEY],
    )
    memo = _memo(app)
    assert memo["frame_errors"] == emt._frame_errors(frames)
    assert memo["other_rows"] == (
        emt._changed_rows(saved[0], frames[0]),
        emt._changed_rows(saved[2], frames[2]),
    )
    # 칸 결과(바뀐 칸만 다시 본 것) · 글 행렬(바뀐 줄만 갈아 끼운 것) = 처음부터 낸 것.
    state = memo["issue_state"]
    assert isinstance(state, ev.MasterIssueState)
    canvases, today = state.params
    fresh = ev.equipment_master_issues(
        frames[1],
        floor_canvases=None if canvases is None else dict(canvases),  # type: ignore[call-overload]
        today=today,  # type: ignore[arg-type]
    )
    assert memo["issues"] == tuple(astuple(issue) for issue in fresh)
    assert memo["buffer_texts"] == eg.text_matrix(frames[1].reset_index(drop=True))


def test_unchanged_reruns_skip_the_fixed_costs_and_edits_redo_them_once(
    tmp_path: Path, grid: Calls, calls: Counter[str]
) -> None:
    app = _app(tmp_path / "equipment.duckdb")
    _import(app, _rows("DA-01", "DA-02"))
    _assert_memo_is_fresh(app)
    before = Counter(calls)

    # 편집본이 그대로인 회차 둘 — 셋 다 다시 내지 않는다.
    app.run()
    app.session_state[emt.SIDE_KEY] = emt.SIDE_CHANGES
    app.run()
    assert not app.exception, app.exception
    assert calls == before

    # 표 출납 한 번 — 셋을 한 번씩(다른 표 행 수는 두 표) 다시 낸다.
    send_ops(app, grid, {"op": "cell", "id": "n:DA-01", "col": "담당자", "text": "홍길동"})
    assert calls["_frame_errors"] - before["_frame_errors"] == 1
    assert calls["_alert_pairs"] - before["_alert_pairs"] == 1
    assert calls["_changed_rows"] - before["_changed_rows"] == 2
    _assert_memo_is_fresh(app)

    # 날짜 · 막는 값 · 붙여넣기도 메모 값이 처음부터 낸 값과 같다.
    send_ops(app, grid, {"op": "cell", "id": "n:DA-02", "col": "반입일정", "text": "2026-12-01"})
    _assert_memo_is_fresh(app)
    send_ops(app, grid, {"op": "cell", "id": "n:DA-01", "col": "보관유무", "text": ""})
    _assert_memo_is_fresh(app)
    _import(app, _rows("DA-01", "DA-02", "DA-03"))
    _assert_memo_is_fresh(app)
