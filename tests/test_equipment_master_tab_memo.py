# Purpose: 설비 마스터 탭 회차 메모가 그대로인 회차에 다시 계산하지 않고 값이 새 계산과 같은지 본다.

"""설비 마스터 탭 고정비(표 단위 오류 앞 셋 · 일정 확인 · 다른 표 바뀐 행 수)의 회차 메모.

- **다시 도는 범위** — 편집본이 그대로인 회차(오른쪽 칸 바꾸기 · 그냥 다시 돌기)는 다시 내지
  않는다. 설비 마스터 칸 하나를 고친 회차는 다른 두 표의 일(바뀐 행 수 · 표 단위 오류)을 다시 하지
  않고(표별 세대), 일정 확인은 그 판정 칸이 바뀐 줄만 다시 본다. 다른 표 · 줄 수가 바뀐 회차(엑셀 ·
  CSV 넣기 등)는 한 번씩 다시 낸다.
- **같은 값** — 메모 값은 그 회차의 편집본으로 처음부터 새로 낸 값과 같다.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import astuple
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from grid_fake import Calls, install_fake_grid, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_master_tab import _app, _import, _rows

from capa_simulation.components import equipment_data_workspace as workspace
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
from capa_simulation.services.equipment_contract import EQUIPMENT_ID_COLUMN
from capa_simulation.services.schedule_confirmation import (
    CONFIRMATION_KIND_COLUMN,
    STAGE_COLUMN,
    schedule_confirmation_issues,
)
from capa_simulation.services.simulation_cache import frame_digest

COUNTED = ("_baseline_errors", "_downtime_errors", "row_confirmation_words", "_changed_rows")


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


def _alerts_from_scratch(master: Any, today: Any) -> dict[str, str]:
    """일정 확인 갈래 글을 통째 목록(`schedule_confirmation_issues`)에서 설비명마다 모아 낸다."""
    issues = schedule_confirmation_issues(master, today=today)
    found: dict[str, list[str]] = {}
    for name, stage, kind in zip(
        issues[EQUIPMENT_ID_COLUMN].tolist(),
        issues[STAGE_COLUMN].tolist(),
        issues[CONFIRMATION_KIND_COLUMN].tolist(),
        strict=True,
    ):
        words = found.setdefault(eg.cell_text(name), [])
        if f"{stage} {kind}" not in words:
            words.append(f"{stage} {kind}")
    return {name: " · ".join(words) for name, words in found.items() if name}


def _assert_memo_is_fresh(app: AppTest) -> None:
    """메모 값 = 지금 편집본 · 저장본 사본으로 새로 낸 값."""
    frames = app.session_state[BUFFER_KEY]
    saved = (
        app.session_state[BASELINE_DRAFT_KEY],
        app.session_state[EQUIPMENT_DRAFT_KEY],
        app.session_state[DOWNTIME_DRAFT_KEY],
    )
    memo = _memo(app)
    names = tuple(frames[1][EQUIPMENT_ID_COLUMN].astype("string").str.strip().dropna().tolist())
    assert memo["baseline_errors"] == emt._baseline_errors(frames[0])
    assert memo["downtime_errors"] == emt._downtime_errors(frames[2], names)
    assert memo["downtime_errors_key"][-1] == names
    assert memo["example_rows"] == workspace._example_row_count(frames)
    assert memo["baseline_rows"] == emt._changed_rows(saved[0], frames[0])
    assert memo["downtime_rows"] == emt._changed_rows(saved[2], frames[2])
    alerts = memo["alert_rows"]
    assert dict(alerts["pairs"]) == _alerts_from_scratch(
        frames[1], date.fromisoformat(alerts["key"][2])
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
    tmp_path: Path, grid: Calls, calls: Counter[str], monkeypatch: pytest.MonkeyPatch
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

    # 설비 마스터 칸(일정 확인 판정 밖) 하나 — 다른 두 표의 일도, 일정 확인 판정도 다시 하지 않는다.
    # 숨은 Summary 몫의 계산 사본 지문은 내지 않는다(편집본 세대가 올라도).
    digests = Counter[int]()

    def counted_digest(frame: Any) -> str:
        digests[len(frame)] += 1
        return frame_digest(frame)

    monkeypatch.setattr(workspace, "frame_digest", counted_digest)
    send_ops(app, grid, {"op": "cell", "id": "n:DA-01", "col": "담당자", "text": "홍길동"})
    assert not digests
    assert calls == before
    _assert_memo_is_fresh(app)

    # 일정 확인 판정 칸(반입일정)을 고치면 그 판정만 다시 본다 — 다른 두 표는 그대로.
    before = Counter(calls)
    send_ops(app, grid, {"op": "cell", "id": "n:DA-02", "col": "반입일정", "text": "2026-12-01"})
    assert calls["row_confirmation_words"] - before["row_confirmation_words"] == 1
    assert calls["_changed_rows"] == before["_changed_rows"]
    assert calls["_baseline_errors"] == before["_baseline_errors"]
    _assert_memo_is_fresh(app)
    # 막는 값 · 엑셀·CSV 넣기(줄 수가 바뀜)도 메모 값이 처음부터 낸 값과 같다.
    send_ops(app, grid, {"op": "cell", "id": "n:DA-01", "col": "보관유무", "text": ""})
    _assert_memo_is_fresh(app)
    _import(app, _rows("DA-01", "DA-02", "DA-03"))
    _assert_memo_is_fresh(app)
