# Purpose: Space 현황이 정지한 호기를 반출/이설일정 전까지 도면에 남기는지 검사한다.

"""Space 의 「공간에 없음」은 상태 이름이 아니라 판정의 `도면이탈여부` 를 본다
(2026-10-16 사용자 결정).

정지일정만 지난 호기는 집계에서 빠져 상태가 「정지」이지만, 반출/이설일정이 남아 있으면 자리를
비우기 전이라 도면에 그린다. 반출/이설일정이 없는 정지 호기(옛 「반출 완료」)는 지금처럼 정지일에
도면에서도 빠진다.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_pages import PROJECT_ROOT, _page_script

from capa_simulation.components import space_layout_editor
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"


@pytest.fixture
def viewer_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> None:
        calls.append(kwargs["data"])

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


def test_a_stopped_unit_stays_on_the_floor_until_its_exit_date(
    tmp_path: Path, viewer_calls: list[dict[str, Any]]
) -> None:
    today = date.today()
    equipment = _equipment()
    stopped = equipment.iloc[[0]].assign(설비명="EQ-03", X좌표=50)
    equipment = equipment.astype({"정지일정": "object", "반출/이설일정": "object"})
    equipment.loc[0, ["정지일정", "반출/이설일정"]] = [
        (today - timedelta(days=10)).isoformat(),
        (today + timedelta(days=30)).isoformat(),
    ]
    equipment.loc[1, "정지일정"] = (today - timedelta(days=10)).isoformat()
    database = tmp_path / "space_stop.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(
        _baseline(), pd.concat([equipment, stopped], ignore_index=True), _downtime()
    )
    clear_equipment_repository()
    overview = AppTest.from_string(_page_script(PAGE, database), default_timeout=60)
    detail = AppTest.from_string(_page_script(PAGE, database), default_timeout=60)
    detail.query_params["floor"] = "C1-1F"

    overview.run()
    detail.run()

    assert not overview.exception and not detail.exception
    # FAB 전체는 공간에 없는 호기를 따로 한 줄로 말한다 — 반출/이설일정 없이 정지한 EQ-02 하나다.
    captions = [element.value for element in overview.caption]
    gone = "반출/이설(없으면 정지)을 마친 1대는 공간에 없어 세지 않습니다"
    assert any(gone in text for text in captions)
    floor = viewer_calls[-1]
    assert floor["scope"] == "floor" and floor["floor"] == "C1 1F"
    # 정지했지만 반출/이설 전인 EQ-01 은 남고, 반출/이설일정 없이 정지한 EQ-02 는 빠진다.
    assert sorted(item["id"] for item in floor["items"]) == ["EQ-01", "EQ-03"]
    clear_equipment_repository()
