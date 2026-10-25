# Purpose: Space 「공식과 견주기」 의 뷰어 payload·편집기 그리기 꼴·층 목록 칸·블록 풍선을 검증한다.

"""설비 시나리오 2단계 S4 — 「공식과 견주기」(설계 8-3).

- 뷰어 payload `compare` 는 epoch 밖이다 — 토글을 켜고 꺼도 epoch 가 그대로라 도면이 다시 서지
  않는다.
- 토글은 늘 선다 — 해당 없는 회차(공식 배치·배치 편집 중)에는 끈 채 잠근 다른 key 의 토글이 같은
  자리에 선다(검토 L11).
- 편집기 JS 의 순수 함수 `compareShapes`(`// <view-compare>` 구획)를 node 로 돌려 점선
  상자·선·꼬리표 꼴을 본다.
- FAB 층 목록에 「공식과 다름」 칸, 층 블록 풍선에 「가정 배치 n대 다름」 이 견주기를 켰을 때만
  선다.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_repository import OPERATIONS, _request, _session, _set
from test_space_layout_overlay_page import FAKE_APPLY_KEY, _ok, _overlay, _space, _viewer
from test_space_module_group import _node

from capa_simulation.components import space_layout_editor
from capa_simulation.components.space_layout import FloorPlacement, floor_block_stats
from capa_simulation.components.space_layout_editor import _clean_compare
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository

ASSETS = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "capa_simulation"
    / "components"
    / "space_layout_editor_assets"
)
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
COMPARE_KEY = "space_compare_official_v1"
COMPARE_LOCKED_KEY = "space_compare_official_locked_v1"


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


@pytest.fixture
def editor_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """편집기 JS 는 AppTest 가 돌리지 못해 `_EDITOR` 를 대역으로 바꿔 받은 data 를 적어 둔다."""
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        calls.append(kwargs["data"])
        return SimpleNamespace(apply=st.session_state.pop(FAKE_APPLY_KEY, None))

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


_BLOCK = re.compile(r"// <view-compare>\n(?P<body>.*?)\n\s*// </view-compare>", re.S)

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
const boxes = new Map(Object.entries(input.boxes))
const shapes = compareShapes(input.compare, (id) => boxes.get(id) || null, input.canvasH, input.fs)
process.stdout.write(JSON.stringify({ shapes }))
"""


def _shapes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    match = _BLOCK.search(JS)
    assert match, "editor.js 에 // <view-compare> 구획이 없습니다"
    result = _node(_RUNNER % match.group("body"), payload)
    shapes: list[dict[str, Any]] = result["shapes"]
    return shapes


def test_the_compare_layer_draws_boxes_lines_and_tags_in_svg_coordinates() -> None:
    """점선 상자는 기준 자리(데이터 → SVG 로 뒤집음), 꼬리표 없는 상자는 지금 상자와 가운데끼리 선,
    꼬리표 있는 상자와 들어온 호기는 왼쪽 위 꼬리표. 숫자가 아닌 상자·지금 상자 없는 선은 뺀다."""
    shapes = _shapes(
        {
            "canvasH": 60,
            "fs": 2,
            "compare": {
                "ghosts": [
                    {"id": "A", "x": 1, "y": 1, "w": 12, "h": 7, "tag": None},
                    {"id": "B", "x": 20, "y": 1, "w": 12, "h": 7, "tag": "→ C2 3F"},
                    {"id": "Z", "x": None, "y": 1, "w": 12, "h": 7, "tag": None},
                    {"id": "Q", "x": 40, "y": 1, "w": 12, "h": 7, "tag": None},
                ],
                "arrivals": [{"id": "E", "tag": "← C1 2F"}, {"id": "F", "tag": "← 없음"}],
            },
            "boxes": {
                "A": {"x": 3, "y": 20, "w": 12, "h": 7},
                "E": {"x": 30, "y": 30, "w": 10, "h": 5},
            },
        }
    )

    assert shapes == [
        {"kind": "box", "x": 1, "y": 52, "w": 12, "h": 7},
        {"kind": "line", "x1": 7, "y1": 55.5, "x2": 9, "y2": 36.5},
        {"kind": "box", "x": 20, "y": 52, "w": 12, "h": 7},
        {"kind": "tag", "x": 20, "y": 51.3, "text": "→ C2 3F"},
        {"kind": "box", "x": 40, "y": 52, "w": 12, "h": 7},
        {"kind": "tag", "x": 30, "y": 24.3, "text": "← C1 2F"},
    ]


def test_neighbouring_compare_tags_are_lifted_apart() -> None:
    """이웃한 차이 호기의 꼬리표가 서로 덮지 않게 겹치는 꼬리표를 한 줄씩 위로 올린다(S4 리뷰 —
    390px 에서 「도면 제외(가정)」 와 「→ C1 4F」 가 겹쳐 읽히지 않았다). 위에 자리가 없으면 아래로
    내리고, 겹치지 않는 꼬리표는 그대로다."""
    shapes = _shapes(
        {
            "canvasH": 60,
            "fs": 2,
            "compare": {
                "ghosts": [
                    {"id": "S1", "x": 33.5, "y": 4.5, "w": 8, "h": 6, "tag": "도면 제외(가정)"},
                    {"id": "S2", "x": 42.5, "y": 4.5, "w": 8, "h": 6, "tag": "→ C1 4F"},
                    {"id": "S3", "x": 80, "y": 4.5, "w": 8, "h": 6, "tag": "→ C2 3F"},
                ],
                "arrivals": [],
            },
            "boxes": {},
        }
    )
    tags = [shape for shape in shapes if shape["kind"] == "tag"]
    assert [tag["text"] for tag in tags] == ["도면 제외(가정)", "→ C1 4F", "→ C2 3F"]
    base = 60 - (4.5 + 6) - 2 * 0.35
    assert tags[0]["y"] == pytest.approx(base)
    assert tags[1]["y"] == pytest.approx(base - 2 * 1.25)
    assert tags[2]["y"] == pytest.approx(base)
    # 캔버스 맨 위 상자(브라우저 확인 — C2 6F 위 끝)는 위로 올릴 자리가 없어 한 줄 아래로 내린다.
    top = _shapes(
        {
            "canvasH": 62,
            "fs": 3.6,
            "compare": {
                "ghosts": [
                    {"id": "S1", "x": 33.5, "y": 48.5, "w": 8, "h": 6, "tag": "도면 제외(가정)"},
                    {"id": "S2", "x": 42.5, "y": 48.5, "w": 8, "h": 6, "tag": "→ C1 4F"},
                ],
                "arrivals": [],
            },
            "boxes": {},
        }
    )
    first, second = (shape for shape in top if shape["kind"] == "tag")
    assert first["y"] == pytest.approx(62 - 54.5 - 3.6 * 0.35)
    assert second["y"] == pytest.approx(first["y"] + 3.6 * 1.25)


def test_the_compare_layer_sits_above_the_units_and_takes_no_clicks() -> None:
    """견주기 층은 호기·요소·Main 설비명 위, 고르기 덧그림 아래이고 눌림을 받지 않는다. 그리기는
    회차마다와 배율이 바뀌는 길(`drawSelectionBox`)에서 한다."""
    assert HTML.index('class="sle-group-names"') < HTML.index('class="sle-compare"')
    assert HTML.index('class="sle-compare"') < HTML.index('class="sle-overlay"')
    css = (ASSETS / "editor.css").read_text(encoding="utf-8")
    assert ".sle-compare { pointer-events: none; }" in css
    draw = JS[JS.index("  function drawSelectionBox() {") :]
    assert "drawCompare()" in draw[: draw.index("\n  }\n")]
    assert "const COMPARE = VIEW && !FAB && data.compare" in JS


def test_the_viewer_payload_cleans_the_compare_material() -> None:
    assert _clean_compare(None) is None
    assert _clean_compare({"ghosts": [], "arrivals": []}) is None
    cleaned = _clean_compare(
        {
            "ghosts": [
                {"id": "A", "x": 1, "y": 2, "w": 3, "h": 4, "tag": ""},
                {"id": "B", "x": float("nan"), "y": 2, "w": 3, "h": 4, "tag": "→ C2 3F"},
            ],
            "arrivals": [{"id": "E", "tag": "← C1 2F"}, {"id": "F", "tag": None}],
        }
    )
    assert cleaned == {
        "ghosts": [{"id": "A", "x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0, "tag": None}],
        "arrivals": [{"id": "E", "tag": "← C1 2F"}],
    }


def test_the_block_tooltip_names_the_floors_layout_difference_only_when_asked() -> None:
    placement = FloorPlacement(("C1", "1F"), placed=2.0, unplaced=0.0, occupancy=0.1)
    plain = floor_block_stats([placement])
    assert "layout" not in plain["C1 1F"]
    compared = floor_block_stats([placement], layout_differences={("C1", "1F"): 3})
    assert compared["C1 1F"]["layout"] == "가정 배치 3대 다름"
    assert "stats.layout" in JS[JS.index("const blockTip = ") : JS.index("const hasSize = ")]


# ---------------------------------------------------------------- 화면(AppTest)


def test_an_assumption_floor_compares_with_the_official_place_outside_the_epoch(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """가정 세션 층 상세 — 토글을 켜면 payload `compare` 에 EQ-01 의 공식 자리(같은 층으로 옮김 —
    선)가 실리고 epoch 는 그대로다. 끄면 비운다."""
    _, setup = _overlay(tmp_path)
    app = _ok(_space(tmp_path, setup).run())
    before = _viewer(editor_calls)
    assert before["compare"] is None
    assert not app.toggle(key=COMPARE_KEY).value

    app.toggle(key=COMPARE_KEY).set_value(True).run()
    after = _viewer(editor_calls)

    assert after["epoch"] == before["epoch"]
    ghosts = after["compare"]["ghosts"]
    assert [(ghost["id"], ghost["tag"]) for ghost in ghosts] == [("EQ-01", None)]
    app.toggle(key=COMPARE_KEY).set_value(False).run()
    assert _viewer(editor_calls)["compare"] is None


def test_the_compare_toggle_stays_locked_off_where_nothing_differs(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """공식 세션 — 견줄 호기가 없어 끈 채 잠근 토글이 같은 자리에 선다(key 가 달라 켠 값을
    지킨다)."""

    _overlay(tmp_path)
    app = _ok(_space(tmp_path, OPERATIONS).run())

    locked = app.toggle(key=COMPARE_LOCKED_KEY)
    assert locked.disabled and not locked.value
    assert "공식 배치를 보는 중" in str(locked.help)
    assert not [toggle for toggle in app.toggle if toggle.key == COMPARE_KEY]
    assert _viewer(editor_calls)["compare"] is None


def test_editing_locks_the_compare_toggle_and_keeps_the_value_for_afterwards(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """층 배치 편집 중에는 견주지 않는다 — 켠 견주기는 다른 key 의 끈 채 잠근 토글로 바뀌고
    편집기에는 재료를 보내지 않는다. 편집을 끄면 켠 값 그대로 돌아와 다시 견준다(검토 L11 — 잠근
    토글이 켠 값을 덮지 않는다)."""
    _, setup = _overlay(tmp_path)
    app = _ok(_space(tmp_path, setup).run())
    app.toggle(key=COMPARE_KEY).set_value(True).run()
    assert _viewer(editor_calls)["compare"] is not None

    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    _ok(app)

    locked = app.toggle(key=COMPARE_LOCKED_KEY)
    assert locked.disabled and not locked.value
    assert "배치 편집 중에는 견주지 않습니다" in str(locked.help)
    assert not [toggle for toggle in app.toggle if toggle.key == COMPARE_KEY]
    assert "compare" not in editor_calls[-1] or editor_calls[-1]["compare"] is None
    assert editor_calls[-1].get("mode") != "view"

    app.toggle(key="space_layout_edit_mode").set_value(False).run()
    _ok(app)

    assert app.toggle(key=COMPARE_KEY).value
    assert _viewer(editor_calls)["compare"] is not None


def test_the_fab_floor_list_adds_the_official_difference_column_when_comparing(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """FAB 전체 — 견주기를 켜면 층 목록 표에 「공식과 다름」 칸(옮긴 층에 1)과 블록 풍선 한 줄이
    선다. 끄면 칸이 없다."""
    repository, setup = _overlay(tmp_path)
    mine = _session(repository, setup)
    repository.save_equipment(
        _request(mine, setup, equipment=_set(mine.equipment, "EQ-02", "층", "2F"))
    )
    clear_equipment_repository()
    app = _ok(_space(tmp_path, setup, floor=False).run())
    app.session_state[SELECTION_KEY] = {"scenario_id": setup, "schedule_revision_id": None}
    _ok(app.run())
    table = app.dataframe[0].value
    assert "공식과 다름" not in table.columns

    app.toggle(key=COMPARE_KEY).set_value(True).run()

    table = app.dataframe[0].value
    by_floor = {(row["동"], row["층"]): row["공식과 다름"] for _, row in table.iterrows()}
    assert by_floor[("C1", "1F")] == 2
    assert by_floor[("C1", "2F")] == 1
    fab = next(call for call in reversed(editor_calls) if call.get("scope") == "fab")
    assert fab["linkStats"]["C1 2F"]["layout"] == "가정 배치 1대 다름"


def test_the_fab_difference_column_follows_the_process_filter(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """FAB 「공식과 다름」 칸·블록 풍선도 층 상세 견주기처럼 그리는 호기(공정소분류 필터를 지난
    것)만 센다 — 필터 밖 호기가 같은 표의 배치대수와 어긋나게 「다름」 으로 셈되던 결함(S4 리뷰)."""
    repository, setup = _overlay(tmp_path)
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=_set(theirs.equipment, "EQ-02", "공정소분류", "Process-B"))
    )
    mine = _session(repository, setup)
    repository.save_equipment(
        _request(mine, setup, equipment=_set(mine.equipment, "EQ-01", "층", "2F"))
    )
    clear_equipment_repository()
    app = _ok(_space(tmp_path, setup, floor=False).run())
    app.session_state[SELECTION_KEY] = {"scenario_id": setup, "schedule_revision_id": None}
    app.session_state["space_status_process_filter"] = ["Process-B"]
    _ok(app.run())

    app.toggle(key=COMPARE_KEY).set_value(True).run()

    table = app.dataframe[0].value
    by_floor = {(row["동"], row["층"]): row["공식과 다름"] for _, row in table.iterrows()}
    assert by_floor[("C1", "1F")] == 0
    assert by_floor[("C1", "2F")] == 0
    fab = next(call for call in reversed(editor_calls) if call.get("scope") == "fab")
    assert "layout" not in fab["linkStats"]["C1 2F"]
    app.session_state["space_status_process_filter"] = ["Process-A"]
    _ok(app.run())
    table = app.dataframe[0].value
    by_floor = {(row["동"], row["층"]): row["공식과 다름"] for _, row in table.iterrows()}
    assert (by_floor[("C1", "1F")], by_floor[("C1", "2F")]) == (1, 1)


@pytest.mark.parametrize("floor", [True, False])
def test_the_compare_toggle_is_in_the_path_row_on_both_views(
    tmp_path: Path, editor_calls: list[dict[str, Any]], floor: bool
) -> None:
    """토글은 FAB·층 공통 경로 줄(`space_path`)에 선다 — 층을 오가도 같은 자리다."""
    _, setup = _overlay(tmp_path)
    app: AppTest = _ok(_space(tmp_path, setup, floor=floor).run())
    assert app.toggle(key=COMPARE_KEY).label == "공식과 견주기"
