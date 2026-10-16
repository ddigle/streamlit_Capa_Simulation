# Purpose: Space 층 상세의 색 기준·그룹 체크가 도면 epoch 를 지키며 색·범례만 바꾸는지 검사한다.

"""사이드바 `Space 조건` 의 「색 기준」(공정구분 | 투자Capa)과 그룹 체크(2026-10-16 사용자 결정).

브라우저 편집기(JS)는 AppTest 가 돌리지 못한다. `_EDITOR` 를 대역으로 바꿔 받은 data 를 적어 두고,
체크·기준을 바꾼 회차에 epoch 가 그대로이고(보던 배율을 지킨다) 호기마다의 `fill`·`ink` 만
바뀌는지, 머리 줄 범례가 기준일 대수를 다는지 본다.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_pages import PROJECT_ROOT, _page_script

from capa_simulation.components import space_layout_editor
from capa_simulation.design import tokens
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


def _open_floor(tmp_path: Path) -> AppTest:
    """C1 1F 에 PKG(322K)·MI(180K) 두 호기. MI 는 반출/이설 예정이다."""
    equipment = _equipment()
    equipment["공정구분"] = ["PKG", " mi "]
    equipment["투자Capa"] = ["322K", "180K"]
    equipment["반출/이설일정"] = [None, (date.today() + timedelta(days=60)).isoformat()]
    database = tmp_path / "space_color.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), equipment, _downtime())
    clear_equipment_repository()
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=60)
    app.query_params["floor"] = "C1-1F"
    app.run()
    assert not app.exception
    return app


def _floor_view(calls: list[dict[str, Any]]) -> dict[str, Any]:
    view = calls[-1]
    assert view["mode"] == "view" and view["scope"] == "floor"
    return view


def _fills(view: dict[str, Any]) -> dict[str, tuple[str, str]]:
    return {item["id"]: (item["fill"], item["ink"]) for item in view["items"]}


def _legend(app: AppTest) -> str:
    return next(element.value for element in app.markdown if "기준 " in element.value)


def test_checks_and_the_colour_basis_repaint_without_a_new_epoch(
    tmp_path: Path, viewer_calls: list[dict[str, Any]]
) -> None:
    app = _open_floor(tmp_path)
    first = _floor_view(viewer_calls)

    # 처음에는 공정구분 기준·여섯 그룹 모두 켬. 공정구분은 앞뒤 공백·대소문자를 무시해 맞춘다.
    assert app.sidebar.radio(key="space_color_basis").value == "공정구분"
    assert _fills(first) == {
        "EQ-01": (tokens.SPACE_LINE_TYPE_FILLS["PKG"], tokens.SPACE_LINE_TYPE_INKS["PKG"]),
        "EQ-02": (tokens.SPACE_LINE_TYPE_FILLS["MI"], tokens.SPACE_LINE_TYPE_INKS["MI"]),
    }
    assert first["asOf"] == date.today().isoformat()
    by_id = {item["id"]: item for item in first["items"]}
    assert by_id["EQ-02"]["exitOn"] is not None and by_id["EQ-01"]["exitOn"] is None

    # 그룹 체크를 끄면 그 그룹은 기본 회색이다 — epoch 는 그대로라 브라우저가 배율을 지킨 채 칠한다.
    app.sidebar.checkbox(key="space_color_line_MI").uncheck().run()
    unchecked = _floor_view(viewer_calls)
    assert not app.exception
    assert unchecked["epoch"] == first["epoch"]
    assert _fills(unchecked)["EQ-02"] == (
        tokens.SPACE_UNIT_DEFAULT_FILL,
        tokens.SPACE_UNIT_DEFAULT_INK,
    )
    assert _fills(unchecked)["EQ-01"] == _fills(first)["EQ-01"]

    # 투자Capa 기준은 숫자 차례의 청록 단이다(작은 수부터 1단·2단). 체크 key 는 기준마다 따로다.
    app.sidebar.radio(key="space_color_basis").set_value("투자Capa").run()
    capa = _floor_view(viewer_calls)
    assert not app.exception
    assert capa["epoch"] == first["epoch"]
    assert _fills(capa) == {
        "EQ-01": (tokens.SPACE_CAPA_RAMP[1], tokens.SPACE_CAPA_RAMP_INKS[1]),
        "EQ-02": (tokens.SPACE_CAPA_RAMP[0], tokens.SPACE_CAPA_RAMP_INKS[0]),
    }
    assert [box.label for box in app.sidebar.checkbox] == ["180K", "322K"]
    clear_equipment_repository()


def test_the_floor_legend_counts_the_as_of_meanings(
    tmp_path: Path, viewer_calls: list[dict[str, Any]]
) -> None:
    """머리 줄 범례는 체크한 그룹 색·테·덧표시별 기준일 대수와 기준일이다. 이 둘은 Qual상태 확정에
    Qual 실적이 비고 일정이 지나 미확인이다(오늘 기준 설비 수)."""
    app = _open_floor(tmp_path)

    legend = _legend(app)
    assert "PKG 1대" in legend and "MI 1대" in legend
    assert "반출/이설 예정 1대" in legend and "미확인 2대" in legend
    assert "반입 전" not in legend and "TEST" not in legend
    assert f"기준 {date.today().isoformat()}" in legend
    assert all(item["flag"] for item in _floor_view(viewer_calls)["items"])

    app.sidebar.checkbox(key="space_color_line_PKG").uncheck().run()
    legend = _legend(app)
    assert "PKG" not in legend and "그 밖 1대" in legend
    clear_equipment_repository()


def test_the_layout_editor_gets_the_fills_and_the_as_of_date_and_keeps_its_epoch_on_a_check(
    tmp_path: Path, viewer_calls: list[dict[str, Any]]
) -> None:
    """배치 편집기도 보기와 같은 채우기다 — data 에 기준일(`asOf`, epoch 밖)과 호기마다의
    `fill`·`ink` 가 가고, 편집 중에 그룹 체크를 바꿔도 편집기 epoch 는 그대로다(보던 배율·적용하지
    않은 편집을 지킨다). 머리 줄 범례는 채우기 뜻만 보이고 대수를 달지 않는다."""
    app = _open_floor(tmp_path)
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    assert not app.exception
    editor = viewer_calls[-1]
    assert editor.get("mode") is None and editor["scope"] == "floor"
    assert editor["asOf"] == date.today().isoformat()
    assert _fills(editor) == {
        "EQ-01": (tokens.SPACE_LINE_TYPE_FILLS["PKG"], tokens.SPACE_LINE_TYPE_INKS["PKG"]),
        "EQ-02": (tokens.SPACE_LINE_TYPE_FILLS["MI"], tokens.SPACE_LINE_TYPE_INKS["MI"]),
    }
    by_id = {item["id"]: item for item in editor["items"]}
    assert by_id["EQ-02"]["exitOn"] is not None and by_id["EQ-01"]["flag"] is True
    assert not any("기준 " in element.value for element in app.markdown)

    app.sidebar.checkbox(key="space_color_line_PKG").uncheck().run()
    unchecked = viewer_calls[-1]
    assert not app.exception
    assert unchecked.get("mode") is None
    assert unchecked["epoch"] == editor["epoch"]
    assert _fills(unchecked)["EQ-01"] == (
        tokens.SPACE_UNIT_DEFAULT_FILL,
        tokens.SPACE_UNIT_DEFAULT_INK,
    )
    assert _fills(unchecked)["EQ-02"] == _fills(editor)["EQ-02"]
    clear_equipment_repository()


def test_the_floor_reads_an_old_revision_without_the_actual_columns(
    tmp_path: Path, viewer_calls: list[dict[str, Any]]
) -> None:
    """실적 칸이 빈 저장본도 일정으로 판정한다 — 반입일정이 지난 신규 호기는 실물이다."""
    _open_floor(tmp_path)

    items = _floor_view(viewer_calls)["items"]
    assert [item["realFrom"] for item in items] == ["2026-08-04", "2026-08-11"]
    assert all(item["delays"] == [] and item["storage"] is False for item in items)
    clear_equipment_repository()
