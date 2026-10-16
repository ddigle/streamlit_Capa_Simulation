# Purpose: Space 기준일 페이더가 세션 기준일·범례·FAB 도구 줄과 맞물리고 사이드바 기준일·단계가
# 없는지 검사한다.

"""층 상세 도면 맨 위의 기준일 페이더(2026-10-16 사용자 결정 5).

브라우저 편집기(JS)는 AppTest 가 돌리지 못한다. `_EDITOR` 를 대역으로 바꿔 받은 data 를 적어 두고,
세션에 「놓을 날」(`RELEASE_KEY`)을 넣은 회차에는 브라우저가 상태 값 `asOf` 를 보낸 것처럼 컴포넌트
상태에 넣고 `on_asOf_change` 콜백을 부른다. 실제로는 콜백이 다음 회차의 본문보다 먼저 돌지만 대역은
그리는 자리에서 부르므로, 범례·요약은 그다음 회차에 맞춰진 것을 본다.
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
from capa_simulation.services.space_unit_state import as_of_range

PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
AS_OF_KEY = "space_status_as_of"
RELEASE_KEY = "test_fader_release"
FLOOR_VIEWER_KEY = "space_layout_viewer_C1_1F"


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """`_EDITOR` 대역. 받은 key·data·콜백 이름을 적고, `RELEASE_KEY` 가 있으면 `asOf` 를 보낸다."""
    recorded: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> None:
        import streamlit as st

        recorded.append(
            {
                **kwargs["data"],
                "key": kwargs["key"],
                "callbacks": sorted(name for name in kwargs if name.startswith("on_")),
            }
        )
        released = st.session_state.get(RELEASE_KEY)
        callback = kwargs.get("on_asOf_change")
        if released is not None and callback is not None:
            del st.session_state[RELEASE_KEY]
            st.session_state[kwargs["key"]] = {"asOf": released}
            callback()

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return recorded


def _existing(name: str, x: float, **values: object) -> dict[str, object]:
    """일정 없는 기존 호기 한 행(C1 1F, Process-B) — 반출/이설일정을 반입과 상관없이 둘 수 있다."""
    row: dict[str, object] = {str(key): value for key, value in _equipment().iloc[0].items()}
    row.update(
        {
            "설비명": name,
            "공정소분류": "Process-B",
            "X좌표": x,
            "기존설비여부": "Y",
            "제진대일정": None,
            "물류일정": None,
            "반입일정": None,
            "Qual일정": None,
            "Qual상태": None,
        }
    )
    row.update(values)
    return row


def _open(tmp_path: Path, *, floor: bool = True) -> tuple[AppTest, date]:
    """C1 1F — EQ-01(PKG)·EQ-02(MI, 60일 뒤 반출/이설 예정), 20일 전 반출/이설을 마친 GONE(페이더
    범위 안), 400일 전에 마친 LONG_GONE(범위 밖). EQ-01·EQ-02 는 Qual상태 확정에 Qual 실적이 비어
    오늘 기준 미확인이다."""
    today = date.today()
    equipment = _equipment()
    equipment["공정구분"] = ["PKG", "MI"]
    equipment["반출/이설일정"] = [None, (today + timedelta(days=60)).isoformat()]
    gone = (today - timedelta(days=20)).isoformat()
    long_gone = (today - timedelta(days=400)).isoformat()
    extra = pd.DataFrame(
        [
            _existing("GONE", 50, **{"반출/이설일정": gone}),
            _existing("LONG_GONE", 70, **{"반출/이설일정": long_gone}),
        ],
        columns=equipment.columns,
    )
    database = tmp_path / "space_fader.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(
        _baseline(), pd.concat([equipment, extra], ignore_index=True), _downtime()
    )
    clear_equipment_repository()
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=60)
    if floor:
        app.query_params["floor"] = "C1-1F"
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app, today


def _last(calls: list[dict[str, Any]], scope: str) -> dict[str, Any]:
    found = [call for call in calls if call.get("scope") == scope and call.get("mode") == "view"]
    assert found, scope
    return found[-1]


def _legend(app: AppTest) -> str:
    return next(element.value for element in app.markdown if "기준 " in element.value)


def test_the_sidebar_has_no_as_of_date_and_no_stage_filter(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """사이드바에는 기준일 칸도 「단계」 필터도 없다 — 기준일은 도면 위 페이더다. 세션에 든
    `space_status_stage_filter` 값은 읽지 않는다(그리는 호기가 그대로다)."""
    app, _ = _open(tmp_path)
    before = [item["id"] for item in _last(calls, "floor")["items"]]

    assert not app.sidebar.date_input
    assert [widget.label for widget in app.sidebar.multiselect] == ["공정소분류"]
    app.session_state["space_status_stage_filter"] = ["가용"]
    app.run()
    assert not app.exception
    assert [item["id"] for item in _last(calls, "floor")["items"]] == before
    clear_equipment_repository()


def test_releasing_the_fader_moves_the_session_date_and_the_legend_but_not_the_epoch(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """놓을 때 한 번 오는 `asOf` 가 세션 기준일을 바꾸고, 그 회차부터 범례·요약·호기 표가 그
    날이다. 날짜는 epoch 에 없다 — 같은 epoch 라 브라우저가 보던 배율을 지킨다. 그리는 호기 목록도
    그대로다."""
    app, today = _open(tmp_path)
    first = _last(calls, "floor")
    start, end = as_of_range(today)

    assert (first["asOf"], first["today"]) == (today.isoformat(), today.isoformat())
    assert (first["asOfMin"], first["asOfMax"]) == (start.isoformat(), end.isoformat())
    assert today.isoformat() not in first["epoch"]
    assert "on_asOf_change" in first["callbacks"] and first["key"] == FLOOR_VIEWER_KEY
    legend = _legend(app)
    assert "PKG 1대" in legend and "MI 1대" in legend and f"기준 {today.isoformat()}" in legend
    assert "배치 2대" in first["summary"]

    later = today + timedelta(days=61)
    app.session_state[RELEASE_KEY] = later.isoformat()
    app.run()
    assert not app.exception
    assert app.session_state[AS_OF_KEY] == later
    app.run()
    moved = _last(calls, "floor")

    assert not app.exception
    assert moved["asOf"] == later.isoformat()
    assert moved["epoch"] == first["epoch"]
    assert [item["id"] for item in moved["items"]] == [item["id"] for item in first["items"]]
    legend = _legend(app)
    # EQ-02 는 반출/이설일정(60일 뒤)이 지나 도면에서 빠졌다.
    assert f"기준 {later.isoformat()}" in legend and "PKG 1대" in legend and "MI" not in legend
    assert "배치 1대" in moved["summary"]
    clear_equipment_repository()


def test_the_roster_is_the_union_over_the_fader_range(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """그리는 호기는 범위(오늘 ±12개월) 어딘가에서 도면에 서는 호기의 합집합이다 — 20일 전
    반출/이설을 마친 GONE 은 들고(브라우저가 기준일과 견주어 숨긴다), 범위 시작 전에 마친
    LONG_GONE 은 없다.
    기준일을 범위 끝까지 옮겨도 목록·epoch 가 같다."""
    app, today = _open(tmp_path)
    first = _last(calls, "floor")
    by_id = {item["id"]: item for item in first["items"]}

    assert sorted(by_id) == ["EQ-01", "EQ-02", "GONE"]
    assert by_id["GONE"]["exitOn"] == (today - timedelta(days=20)).isoformat()
    for moment in as_of_range(today):
        app.session_state[AS_OF_KEY] = moment
        app.run()
        view = _last(calls, "floor")
        assert not app.exception
        assert view["asOf"] == moment.isoformat()
        assert view["epoch"] == first["epoch"]
        assert [item["id"] for item in view["items"]] == [item["id"] for item in first["items"]]
    clear_equipment_repository()


def test_an_out_of_range_session_date_is_moved_to_the_nearest_end(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """날이 지나 세션 기준일이 범위를 벗어나면 가까운 끝으로 맞춘다. 페이더가 보낸 날도 같다."""
    app, today = _open(tmp_path)
    start, end = as_of_range(today)

    app.session_state[AS_OF_KEY] = today - timedelta(days=800)
    app.run()
    assert not app.exception
    assert app.session_state[AS_OF_KEY] == start
    assert _last(calls, "floor")["asOf"] == start.isoformat()
    assert f"기준 {start.isoformat()}" in _legend(app)

    app.session_state[RELEASE_KEY] = "2999-01-01"
    app.run()
    assert app.session_state[AS_OF_KEY] == end
    # 날짜가 아닌 값은 버린다.
    app.session_state[RELEASE_KEY] = "내일"
    app.run()
    assert not app.exception
    assert app.session_state[AS_OF_KEY] == end
    clear_equipment_repository()


def test_the_fab_toolbar_gets_the_as_of_date_and_the_unconfirmed_count(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """FAB 전체에는 페이더가 없고 도구 줄에 기준일·「오늘로」·미확인 대수가 선다. 미확인은 오늘 기준
    설비 수(EQ-01·EQ-02)다. 「오늘로」는 같은 `asOf` 길로 세션 기준일을 오늘로 돌린다."""
    app, today = _open(tmp_path, floor=False)
    fab = _last(calls, "fab")

    assert fab["asOf"] == today.isoformat() and fab["today"] == today.isoformat()
    assert fab["unconfirmed"] == 2
    assert str(fab["summary"]).startswith("배치 ")
    assert "on_asOf_change" in fab["callbacks"]

    app.session_state[AS_OF_KEY] = today + timedelta(days=30)
    app.run()
    assert _last(calls, "fab")["asOf"] == (today + timedelta(days=30)).isoformat()
    app.session_state[RELEASE_KEY] = today.isoformat()
    app.run()
    app.run()
    assert not app.exception
    assert app.session_state[AS_OF_KEY] == today
    assert _last(calls, "fab")["asOf"] == today.isoformat()
    # 공정소분류 필터 밖이면 세지 않는다(미확인 두 대는 Process-A).
    app.sidebar.multiselect(key="space_status_process_filter").set_value(["Process-B"]).run()
    assert not app.exception
    assert _last(calls, "fab")["unconfirmed"] == 0
    clear_equipment_repository()


def test_the_layout_editor_gets_the_pinned_date_and_no_fader(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """배치 편집 중에는 기준일이 고정이다 — 편집기는 세션 기준일을 받아 「편집 중 고정」 줄에 쓰고,
    기준일을 보낼 길(`on_asOf_change`)이 없다."""
    app, today = _open(tmp_path)
    later = today + timedelta(days=10)
    app.session_state[AS_OF_KEY] = later
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    editor = calls[-1]

    assert not app.exception
    assert editor.get("mode") is None and editor["scope"] == "floor"
    assert editor["asOf"] == later.isoformat()
    assert "on_asOf_change" not in editor["callbacks"]
    assert any(later.isoformat() in item.value for item in app.caption)
    clear_equipment_repository()
