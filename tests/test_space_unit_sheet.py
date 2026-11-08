# Purpose: Space 「호기 정보」 창 표 재료(unit_sheet·_clean_sheet)와 층 화면 data 를 검사한다.

"""2026-11-03 사용자 요청 — 페이지 아래 호기 표(21칸)를 편집기 안 창으로 옮기고, 칸마다 필터로
맞는 호기를 도면에서 강조한다. 거르기·강조는 브라우저(`tests/test_space_unit_sheet_js.py`)이고
파이썬은 칸 꼴·값을 정리해 data `sheet`(epoch 밖)로 싣는다.

- `unit_sheet`: 있는 칸만 그 차례 + 끝 「도면」, 날짜는 「YYYY-MM-DD」, 투자Capa 는 수(못 읽는
  글은 글), 글은 앞뒤 공백을 걷고 길면 줄임, 빈 값은 None, 설비명이 빈 행은 뺌, 상한을 넘으면 자름.
- 층 보기: 이 층 행(공정 필터 뒤) 가운데 기준일에 도면에서 빠지지 않은 것 — 도면에 선 호기는
  배치, 나머지는 레이아웃표시로 미배치·레이아웃 제외. 층 미정 호기는 들지 않는다.
- 배치 편집: 편집본의 이 층 행 + 편집기 호기(층 미정 미배치 포함), 공정 필터와 상관없이.
- FAB 에는 창이 없다(`sheet` None).
- 창 「CSV」 의 도면에 선 호기(`sheet.csv` — 2026-11-04 Space 결정 보드 답, 옛 도면 아래
  내려받기를 창 안으로): 보기 · 편집 모두 같은 글이고 BOM 을 붙이면 옛 내려받기 바이트와 같다.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_process_field import share
from test_space_layout_edit import _master

from capa_simulation.components import space_layout_editor
from capa_simulation.components.space_layout import FLOOR_TABLE_COLUMNS
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.space_unit_sheet import (
    MAX_SHEET_ROWS,
    MAX_TEXT_LENGTH,
    PLACE_COLUMN,
    PLACE_EXCLUDED,
    PLACE_PLACED,
    PLACE_UNPLACED,
    floor_csv,
    unit_sheet,
)

PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"


def _frame(*rows: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def test_the_sheet_keeps_present_columns_in_order_and_appends_the_place() -> None:
    rows = _frame(
        {
            "설비명": " EQ-01 ",
            "공정소분류": " Saw ",
            "투자Capa": "1,200",
            "반입일정": pd.Timestamp("2026-11-03 10:00"),
            "Main 설비": " M-1 ",
            "레이아웃표시": "Y",
        },
        {
            "설비명": "EQ-02",
            "공정소분류": None,
            "투자Capa": "TBD",
            "반입일정": "2026-12-01",
            "Main 설비": np.nan,
            "레이아웃표시": "N",
        },
        {
            "설비명": "EQ-03",
            "공정소분류": 3.0,
            "투자Capa": np.nan,
            "반입일정": date(2027, 1, 2),
            "Main 설비": "",
            "레이아웃표시": "Y",
        },
        {
            "설비명": "  ",
            "공정소분류": "빈 이름",
            "투자Capa": 1,
            "반입일정": None,
            "Main 설비": None,
            "레이아웃표시": "Y",
        },
        {
            "설비명": "EQ-04",
            "공정소분류": "x" * (MAX_TEXT_LENGTH + 5),
            "투자Capa": float("inf"),
            "반입일정": "언젠가",
            "Main 설비": None,
            "레이아웃표시": None,
        },
    )
    sheet = unit_sheet(
        rows,
        columns=("없는 칸", "공정소분류", "설비명", "투자Capa", "반입일정"),
        place_of={"EQ-01": PLACE_PLACED},
    )
    assert sheet["columns"] == [
        {"name": "공정소분류", "type": "text"},
        {"name": "설비명", "type": "text"},
        {"name": "투자Capa", "type": "number"},
        {"name": "반입일정", "type": "date"},
        {"name": PLACE_COLUMN, "type": "text"},
    ]
    assert sheet["cut"] == 0
    assert [row["id"] for row in sheet["rows"]] == ["EQ-01", "EQ-02", "EQ-03", "EQ-04"]
    assert [row["group"] for row in sheet["rows"]] == ["M-1", None, None, None]
    first, second, third, fourth = (row["cells"] for row in sheet["rows"])
    assert first == ["Saw", "EQ-01", 1200.0, "2026-11-03", PLACE_PLACED]
    assert second == [None, "EQ-02", "TBD", "2026-12-01", PLACE_EXCLUDED]
    assert third == ["3", "EQ-03", None, "2027-01-02", PLACE_UNPLACED]
    assert fourth[0] is not None and len(fourth[0]) == MAX_TEXT_LENGTH and fourth[0].endswith("…")
    assert fourth[2:] == [None, None, PLACE_EXCLUDED]


def test_the_sheet_cuts_beyond_the_limit_and_survives_missing_ids() -> None:
    rows = _frame(*({"설비명": f"EQ-{index:03d}"} for index in range(7)))
    sheet = unit_sheet(rows, columns=FLOOR_TABLE_COLUMNS, place_of={}, limit=5)
    assert [row["id"] for row in sheet["rows"]] == [f"EQ-{index:03d}" for index in range(5)]
    assert sheet["cut"] == 2
    assert unit_sheet(_frame({"공정소분류": "A"}), columns=FLOOR_TABLE_COLUMNS, place_of={}) == {
        "columns": [],
        "rows": [],
        "cut": 0,
    }
    stamped = unit_sheet(
        _frame({"설비명": "A", "반입일정": datetime(2026, 1, 2, 3, 4)}),
        columns=("반입일정",),
        place_of={},
    )
    assert stamped["rows"][0]["cells"][0] == "2026-01-02"


def test_the_cleaner_keeps_only_well_formed_columns_rows_and_cells() -> None:
    """칸 이름이 글이고 꼴을 아는 칸만(그 칸의 값도 함께 뺀다), id 가 빈 글이 아니고 값 수가 칸 수와
    같은 줄만, 값은 글·유한한 수·None(참·거짓은 글). 상한을 넘친 줄 수는 `cut` 에 더한다."""
    clean = space_layout_editor._clean_sheet
    assert clean(None) is None
    sheet = {
        "columns": [
            {"name": "가", "type": "text"},
            {"name": 3, "type": "text"},
            {"name": "나", "type": "colour"},
            {"name": "다", "type": "number"},
        ],
        "rows": [
            {"id": " A ", "group": " G ", "cells": ["a", "x", "y", float("nan")]},
            {"id": "B", "group": 7, "cells": [True, None, None, 2]},
            {"id": "C", "cells": [{"x": 1}, None, None, float("inf")]},
            {"id": " ", "cells": ["a", "b", "c", 1]},
            {"id": "D", "cells": ["too", "short"]},
            "줄 아님",
        ],
        "cut": 4,
    }
    assert clean(sheet) == {
        "columns": [{"name": "가", "type": "text"}, {"name": "다", "type": "number"}],
        "rows": [
            {"id": "A", "group": "G", "cells": ["a", None]},
            {"id": "B", "group": None, "cells": ["True", 2.0]},
            {"id": "C", "group": None, "cells": [None, None]},
        ],
        "cut": 4,
    }
    many = {
        "columns": [{"name": "가", "type": "text"}],
        "rows": [{"id": f"U{index}", "cells": [None]} for index in range(MAX_SHEET_ROWS + 3)],
        "cut": True,
    }
    cleaned = clean(many)
    assert cleaned is not None
    assert len(cleaned["rows"]) == MAX_SHEET_ROWS and cleaned["cut"] == 3


def test_the_floor_csv_is_the_old_download_once_the_browser_adds_the_bom() -> None:
    """창 「CSV」 의 도면에 선 호기 — 글은 `to_csv(index=False)` 그대로, 파일 이름은 옛
    「space_동_층.csv」. 브라우저가 앞에 BOM 을 붙여 UTF-8 로 내려받으므로 옛 내려받기
    바이트(`encode("utf-8-sig")`)와 같다 — 쉼표 · 큰따옴표 · 줄바꿈 · 한글 칸 모두. 받는
    쪽(`_clean_sheet`)은 글 둘이 다 글일 때만 싣는다."""
    frame = _frame(
        {"설비명": "EQ-01", "공정소분류": "DAF, Attach", "메모": '따옴표 "안"', "X좌표": 1.5},
        {"설비명": "EQ-02", "공정소분류": "Saw", "메모": "줄\n바꿈", "X좌표": None},
    )
    csv = floor_csv(frame, building="C1", floor="1F")
    assert csv["file"] == "space_C1_1F.csv"
    assert ("\ufeff" + csv["text"]).encode("utf-8") == frame.to_csv(index=False).encode("utf-8-sig")
    clean = space_layout_editor._clean_sheet
    base = {"columns": [], "rows": [], "cut": 0}
    assert clean({**base, "csv": csv})["csv"] == csv  # type: ignore[index]
    for broken in ({"text": 1, "file": "a.csv"}, {"text": "a", "file": " "}, "a,b", None):
        assert "csv" not in (clean({**base, "csv": broken}) or {})


# ---------------------------------------------------------------- 화면(AppTest)


@pytest.fixture
def editor_data(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """`_EDITOR` 대역 — 받은 data 를 적는다(편집기는 적용 없음)."""
    recorded: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> None:
        recorded.append(kwargs["data"])

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return recorded


def _database(tmp_path: Path) -> Path:
    """C1 1F — EQ-01·EQ-02(배치), 모듈 MOD-1A·1B(Process-B, 배치), UNPL-1(좌표 없음 — 미배치),
    HIDE-1(레이아웃표시 N — 레이아웃 제외), 층 미정 FLOAT-1(미배치), 2F 에 UP-01."""
    module = {"Main 설비": "MOD-1", "공정소분류": "Process-B", "Xsize": 6, "Ysize": 4}
    master = _master(
        {**module, "설비명": "MOD-1A", "X좌표": 60.0, "Y좌표": 10.0},
        {**module, "설비명": "MOD-1B", "X좌표": 66.0, "Y좌표": 10.0},
        {"설비명": "UNPL-1", "X좌표": None, "Y좌표": None},
        {"설비명": "HIDE-1", "레이아웃표시": "N", "X좌표": None, "Y좌표": None},
        {"설비명": "FLOAT-1", "동": None, "층": None, "X좌표": None, "Y좌표": None},
        {"설비명": "UP-01", "층": "2F"},
    )
    database = tmp_path / "space_sheet.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), master, _downtime())
    clear_equipment_repository()
    return database


def _app(database: Path, floor: str | None = "C1-1F") -> AppTest:
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=60)
    if floor:
        app.query_params["floor"] = floor
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _floor_data(recorded: list[dict[str, Any]], *, view: bool) -> dict[str, Any]:
    found = [
        data
        for data in recorded
        if data.get("scope") == "floor" and (data.get("mode") == "view") is view
    ]
    assert found
    return found[-1]


def _places(data: dict[str, Any]) -> dict[str, Any]:
    sheet = data["sheet"]
    assert sheet is not None
    names = [column["name"] for column in sheet["columns"]]
    assert names == [*FLOOR_TABLE_COLUMNS, PLACE_COLUMN]
    return {row["id"]: row["cells"][-1] for row in sheet["rows"]}


def test_the_floor_view_sends_this_floors_rows_with_their_place(
    tmp_path: Path, editor_data: list[dict[str, Any]]
) -> None:
    app = _app(_database(tmp_path))
    view = _floor_data(editor_data, view=True)
    assert _places(view) == {
        "EQ-01": PLACE_PLACED,
        "EQ-02": PLACE_PLACED,
        "MOD-1A": PLACE_PLACED,
        "MOD-1B": PLACE_PLACED,
        "UNPL-1": PLACE_UNPLACED,
        "HIDE-1": PLACE_EXCLUDED,
    }
    groups = {row["id"]: row["group"] for row in view["sheet"]["rows"]}
    assert groups["MOD-1A"] == groups["MOD-1B"] == "MOD-1" and groups["EQ-01"] is None
    # 창 「CSV」 의 「도면에 선 호기」 는 공정 필터 뒤의 모든 칸이다 — 옛 도면 아래 내려받기와
    # 같은 줄.
    csv = view["sheet"]["csv"]
    header, *lines = csv["text"].splitlines()
    assert csv["file"] == "space_C1_1F.csv" and len(header.split(",")) > len(FLOOR_TABLE_COLUMNS)
    names = header.split(",").index("설비명")
    assert sorted(line.split(",")[names] for line in lines) == [
        "EQ-01",
        "EQ-02",
        "MOD-1A",
        "MOD-1B",
    ]
    # 공정 필터(공용 공정 칸)를 지난 행만이다(도면과 같다).
    share(app, ["Process-B"])
    app.run()
    assert not app.exception
    filtered = _floor_data(editor_data, view=True)
    assert set(_places(filtered)) == {"MOD-1A", "MOD-1B"}
    assert len(filtered["sheet"]["csv"]["text"].splitlines()) == 3
    clear_equipment_repository()


def test_the_editor_sends_the_draft_floor_and_the_tray_units(
    tmp_path: Path, editor_data: list[dict[str, Any]]
) -> None:
    """배치 편집 — 편집기 호기(층 미정 미배치 포함)는 편집기 자리(배치·미배치), 편집기 밖의 이 층
    행은 레이아웃표시로. 공정 필터와 상관없이 이 층 전부다."""
    app = _app(_database(tmp_path))
    share(app, ["Process-B"])
    app.run()
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    assert not app.exception, [item.message for item in app.exception]
    editor = _floor_data(editor_data, view=False)
    assert _places(editor) == {
        "EQ-01": PLACE_PLACED,
        "EQ-02": PLACE_PLACED,
        "MOD-1A": PLACE_PLACED,
        "MOD-1B": PLACE_PLACED,
        "UNPL-1": PLACE_UNPLACED,
        "HIDE-1": PLACE_EXCLUDED,
        "FLOAT-1": PLACE_UNPLACED,
    }
    item_ids = {item["id"] for item in editor["items"]}
    assert {"FLOAT-1", "UNPL-1"} <= item_ids and "HIDE-1" not in item_ids
    assert "pickToServer" not in editor
    # 편집기 창의 「CSV」 도면에 선 호기는 보기와 같은 저장본 글이다(공정 필터 뒤 — 옛 도면 아래
    # 줄과 같다).
    view = _floor_data(editor_data, view=True)
    assert editor["sheet"]["csv"] == view["sheet"]["csv"]
    clear_equipment_repository()


def test_the_fab_carries_no_sheet(tmp_path: Path, editor_data: list[dict[str, Any]]) -> None:
    app = _app(_database(tmp_path), floor=None)
    fab = [data for data in editor_data if data.get("scope") == "fab"]
    assert fab and all(data["sheet"] is None for data in fab)
    app.toggle(key="space_fab_edit_mode").set_value(True).run()
    assert not app.exception
    fab_edit = [d for d in editor_data if d.get("scope") == "fab" and d.get("mode") != "view"]
    assert fab_edit and fab_edit[-1]["sheet"] is None
    clear_equipment_repository()
