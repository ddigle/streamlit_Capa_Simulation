# Purpose: 설비 화면 지문 세션 메모가 편집본 · 저장본이 바뀌는 길마다 새 지문으로 바뀌는지 지킨다.

"""설비 화면이 캐시 키에 넘기는 내용 지문의 세션 메모(`equipment_data_workspace.remembered_digest`).

메모는 출처(저장본 쌍 토큰 + 역할) · 편집본 출발점 · 편집본 세대마다 한 번 지문을 낸다. 지키는 것:

- **늘 같은 값** — 메모가 돌려준 지문은 그 회차의 표를 새로 해시한 `frame_digest` 와 같다(지문을
  넘기지 않는 화면과 같은 캐시 칸). 표 출납 · 붙여넣기 · 모두 버리기 · 저장 · 남의 저장 · 샘플
  스위치를 지나며 매번 본다.
- **세대 · 출발점이 오른다** — 편집본을 바꾸는 길(출납 · 붙여넣기 · 버리기 · 저장 · 불러오기)은 모두
  (출발점, 세대) 쌍을 바꾼다. 쌍이 그대로인데 편집본이 바뀌면 메모가 옛 값을 낸다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from grid_fake import Calls, install_fake_grid, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_master_tab import _app, _import, _rows

from capa_simulation.components import equipment_data_workspace as workspace
from capa_simulation.components.equipment_data_workspace import (
    BASELINE_DRAFT_KEY,
    BUFFER_KEY,
    DIGEST_MEMO_KEY,
    DOWNTIME_DRAFT_KEY,
    DRAFT_REVISION_KEY,
    DRAFT_UNSCHEDULED_KEY,
    EQUIPMENT_DRAFT_KEY,
)
from capa_simulation.components.equipment_master_tab import (
    DISCARD_CONFIRM_KEY,
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_KEY,
)
from capa_simulation.navigation import (
    EQUIPMENT_MASTER_TAB,
    EQUIPMENT_SUMMARY_TAB,
    EQUIPMENT_TAB_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_scenario import calculation_frames
from capa_simulation.services.simulation_cache import frame_digest


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


def _session(app: AppTest, key: str) -> Any:
    return app.session_state[key] if key in app.session_state else None


def _calculation_master(app: AppTest) -> pd.DataFrame:
    """그 회차의 `calculation_drafts()[1]` — 세션 저장본 사본에서 새로 세운다."""
    unscheduled = _session(app, DRAFT_UNSCHEDULED_KEY)
    return calculation_frames(
        app.session_state[BASELINE_DRAFT_KEY].copy(),
        app.session_state[EQUIPMENT_DRAFT_KEY].copy(),
        app.session_state[DOWNTIME_DRAFT_KEY].copy(),
        unscheduled if isinstance(unscheduled, frozenset) else frozenset(),
    )[1]


def _memo_entries(app: AppTest) -> dict[tuple[str, ...], str]:
    memo = _session(app, DIGEST_MEMO_KEY)
    if not isinstance(memo, dict):
        return {}
    return {source: digest for source, (digest, _) in memo.get("digests", {}).items()}


def _assert_calculation_memo_is_fresh(app: AppTest) -> None:
    """메모의 계산 사본 지문이 그 회차 표의 새 지문과 같다(지금 토큰의 것만 있다)."""
    entries = {
        source: digest for source, digest in _memo_entries(app).items() if source[0] == "calculation"
    }
    token = app.session_state[DRAFT_REVISION_KEY]
    assert list(entries) == [("calculation", "equipment", token)]
    assert entries[("calculation", "equipment", token)] == frame_digest(_calculation_master(app))


def _summary(app: AppTest) -> AppTest:
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SUMMARY_TAB
    app.run()
    assert not app.exception, app.exception
    return app


def _master(app: AppTest) -> AppTest:
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.run()
    assert not app.exception, app.exception
    return app


def _pair(app: AppTest) -> tuple[object, object]:
    """(편집본 출발점, 편집본 세대) — 메모 열쇠의 앞머리."""
    memo = _session(app, DIGEST_MEMO_KEY)
    assert isinstance(memo, dict)
    return tuple(memo["prefix"])  # type: ignore[return-value]


def test_the_memo_follows_every_path_that_changes_the_buffer_or_the_saved_pair(
    tmp_path: Path, grid: Calls
) -> None:
    database = tmp_path / "equipment.duckdb"
    app = _app(database)
    _import(app, _rows("DA-01", "DA-02", "DA-03"))
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()
    assert not app.exception, app.exception
    _assert_calculation_memo_is_fresh(_summary(app))
    seen = {_pair(app)}

    # 표 출납 — 편집본만 바뀌고 저장본 사본(계산)은 그대로다. 쌍은 바뀐다.
    _master(app)
    send_ops(app, grid, {"op": "cell", "id": "s:DA-01", "col": "담당자", "text": "홍길동"})
    _assert_calculation_memo_is_fresh(_summary(app))
    assert _pair(app) not in seen
    seen.add(_pair(app))

    # 붙여넣기(「엑셀·CSV로 한꺼번에」 넣기).
    _master(app)
    edited = app.session_state[BUFFER_KEY][1].copy()
    edited.loc[edited["설비명"].eq("DA-02"), "메모1"] = "붙여넣기"
    _import(app, edited.to_csv(sep="\t", index=False))
    _assert_calculation_memo_is_fresh(_summary(app))
    assert _pair(app) not in seen
    seen.add(_pair(app))

    # 모두 버리기 — 편집본을 저장본으로 다시 세운다.
    _master(app)
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=DISCARD_CONFIRM_KEY).click().run()
    assert not app.exception, app.exception
    _assert_calculation_memo_is_fresh(_summary(app))
    assert _pair(app) not in seen
    seen.add(_pair(app))

    # 저장 — 새 저장본 쌍 토큰(계산 사본 내용이 바뀐다).
    _master(app)
    send_ops(app, grid, {"op": "cell", "id": "s:DA-03", "col": "담당자", "text": "새 담당"})
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    before = app.session_state[DRAFT_REVISION_KEY]
    app.button(key=SAVE_BUTTON_KEY).click().run()
    assert not app.exception, app.exception
    _summary(app)
    assert app.session_state[DRAFT_REVISION_KEY] != before
    _assert_calculation_memo_is_fresh(app)
    assert _pair(app) not in seen
    seen.add(_pair(app))

    # 남의 저장 — 이 세션은 다음 회차에 새 저장본으로 다시 세운다(불러오기와 같은 길).
    repository = DuckDBEquipmentRepository(database)
    latest = repository.load_official_snapshot()
    assert latest is not None
    other = latest.equipment.copy()
    other.loc[other["설비명"].eq("DA-02"), "메모2"] = "남의 저장"
    repository.save_snapshot(latest.baseline, other, latest.downtime, note="남의 저장")
    clear_equipment_repository()
    _summary(app)
    _assert_calculation_memo_is_fresh(app)
    assert _pair(app) not in seen


def test_the_sample_fleet_is_not_remembered_and_the_empty_fleet_is(tmp_path: Path) -> None:
    """샘플 fleet(오늘마다 다른 합성 표)은 메모에 넣지 않는다. 샘플을 끄면 빈 계산 사본의 지문이다."""
    app = _app(tmp_path / "equipment.duckdb")
    _summary(app)
    assert not [source for source in _memo_entries(app) if source[0] == "calculation"]
    app.toggle(key="dynamic_capa_sample_data").set_value(False).run()
    assert not app.exception, app.exception
    _assert_calculation_memo_is_fresh(app)


def test_the_memo_returns_the_frame_digest_and_recomputes_on_a_new_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """메모 자체 — 같은 (출발점, 세대, 출처)면 다시 해시하지 않고, 하나라도 바뀌거나 꼴 표지가
    다르면 다시 낸다. 돌려주는 값은 늘 `frame_digest` 다."""
    state: dict[str, object] = {}
    monkeypatch.setattr(workspace.st, "session_state", state)
    pair = ["base-1", 3]
    monkeypatch.setattr(workspace, "buffer_base", lambda: pair[0])
    monkeypatch.setattr(workspace, "equipment_buffer_generation", lambda: pair[1])
    calls: list[int] = []

    def counted(frame: pd.DataFrame) -> str:
        calls.append(len(frame))
        return frame_digest(frame)

    monkeypatch.setattr(workspace, "frame_digest", counted)
    frame = pd.DataFrame({"설비명": ["A", "B"], "값": [1.0, 2.0]})
    source = ("snapshot", "calculation", "r1|s1")
    assert workspace.remembered_digest(frame, source=source) == frame_digest(frame)
    assert workspace.remembered_digest(frame, source=source) == frame_digest(frame)
    assert calls == [2]
    pair[1] = 4
    workspace.remembered_digest(frame, source=source)
    assert calls == [2, 2]
    pair[0] = "base-2"
    workspace.remembered_digest(frame, source=source)
    assert calls == [2, 2, 2]
    # 같은 출처에 꼴이 다른 표가 오면(출처를 잘못 붙인 표) 다시 낸다.
    shorter = frame.iloc[:1]
    assert workspace.remembered_digest(shorter, source=source) == frame_digest(shorter)
    assert calls == [2, 2, 2, 1]
    # 다른 출처는 따로 기억한다.
    workspace.remembered_digest(frame, source=("snapshot", "equipment", "r1|s1"))
    workspace.remembered_digest(frame, source=("snapshot", "equipment", "r1|s1"))
    assert calls == [2, 2, 2, 1, 2]


def test_space_remembers_the_snapshot_master_it_draws(tmp_path: Path) -> None:
    """Space 는 스냅샷 계산 프레임의 지문을 쌍 토큰마다 한 번 낸다 — 메모 값은 그 표의 새 지문이다.
    기준일 페이더 회차는 다시 내지 않는다(같은 쌍 · 같은 출처)."""
    from test_equipment_pages import _page_script, _wide_floor_with_hidden_units

    database = tmp_path / "space_digest.duckdb"
    _wide_floor_with_hidden_units(database)
    page = Path(__file__).resolve().parents[1] / "app_pages" / "space_status.py"
    app = AppTest.from_string(_page_script(page, database), default_timeout=120).run()
    assert not app.exception, app.exception
    latest = DuckDBEquipmentRepository(database).load_official_snapshot()
    assert latest is not None
    source = ("snapshot", "calculation", latest.token)
    entries = _memo_entries(app)
    assert entries[source] == frame_digest(latest.calculation_frames()[1])
    pair = _pair(app)
    app.run()
    assert not app.exception, app.exception
    assert _pair(app) == pair
    assert _memo_entries(app)[source] == entries[source]
