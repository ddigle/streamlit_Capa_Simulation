# Purpose: Space 층 상세의 호기 누르기(아래 표 좁히기)와 겹친 반입 예정 숨기기를 검사한다.

"""2026-10-23 사용자 요청 3·8.

- **호기 누르기**(3): 층 상세 보기 전용 뷰어에서 호기를 누르면 브라우저가 `pick`
  (``{"epoch", "id"}``)을 보내고 `on_pick_change` 콜백이 그 층과 함께 쥔다. 아래 호기 표는
  처음엔 층 전체 21칸(`FLOOR_TABLE_COLUMNS`, 요청한 차례)이고, 누르면 그 설비 줄만(모듈이면
  그 Main 설비 줄 전부, 누른 모듈이 첫 줄), 「층 전체 보기」로 돌아간다. 층을 바꾸면(다른 층·
  FAB) 풀린다. 층 CSV 는 늘 층 전체의 모든 칸이다. 옛 epoch 값은 버린다.
- **겹친 반입 예정 숨기기**(8): 기준일에 반입 전인 호기가 그날 보이는 다른 호기(반입됐고 아직
  안 빠진)와 넓이가 0 보다 크게 겹치면 보기 화면이 그리지 않는다 — 판정은 브라우저
  (`// <view-cover>`)이고 페이더를 끄는 동안에도 바로 바뀐다. 반입 전끼리, 같은 묶음
  모듈끼리는 숨기지 않는다. 요약 줄에 「겹쳐 숨긴 반입 예정 n대」(설비지분 합)를 붙이고 범례
  대수는 그대로다. 배치 편집기는 바꾸지 않는다.

AppTest 는 JS 를 못 돌린다 — `_EDITOR` 를 대역으로 바꿔 누른 호기를 컴포넌트 상태에 넣고
`on_pick_change` 를 부른다(대역은 그리는 자리에서 부르므로 결과는 다음 회차에 본다). JS
판정은 선언을 글자 그대로 떼어 node 로 돌린다(node·bun 이 없으면 건너뛰고 CI 에서는 실패).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_space_layout_edit import AS_OF, _master
from test_space_module_group import _js_decl, _node

from capa_simulation.components import space_layout_editor, table_toolbar
from capa_simulation.components.space_layout import (
    FLOOR_TABLE_COLUMNS,
    floor_table,
    picked_unit_rows,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_availability import build_space_equipment_status
from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
PICK_KEY = "test_fake_unit_pick"
PICKED_KEY = "space_status_picked_unit"
SHOW_ALL_KEY = "space_floor_show_all_C1_1F"

_COVER = re.compile(r"// <view-cover>\n(?P<body>.*?)\n\s*// </view-cover>", re.S)


def _between(start: str, end: str) -> str:
    return JS[JS.index(start) : JS.index(end, JS.index(start))]


def _cover_block() -> str:
    match = _COVER.search(JS)
    assert match, "editor.js 에 // <view-cover> 구획이 없습니다"
    return match.group("body")


def _lines_until_blank(head: str) -> str:
    """두 줄 이상인 화살표 함수 선언(`const overlaps = …`)을 빈 줄까지 떼어 낸다."""
    start = JS.index(f"\n  {head}") + 1
    return JS[start : JS.index("\n\n", start)]


# ---------------------------------------------------------------- 겹친 반입 예정 숨기기(node)

_COVER_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const SCALE = 10
const VIEW = true
const FAB = false
const S = { items: new Map(), adjacency: null, asOf: '' }
%s
%s
for (const raw of input.items) {
  S.items.set(raw.id, { kind: 'unit', placed: true, moveTo: null, group: null,
    realFrom: '0000-01-01', exitOn: null, stopOn: null, delays: [], offline: [],
    storage: false, flag: false, share: 1, ...raw })
}
const out = {}
for (const T of input.days) {
  S.asOf = T
  out[T] = [...S.items.values()]
    .filter((m) => coveredAt(m, unitState(m, T))).map((m) => m.id).sort()
}
out.counts = input.counts.map((n) => unitCountText(n))
process.stdout.write(JSON.stringify(out))
"""

_COVER_DECLS = (
    "const roundTo = ",
    "const isUnit = ",
    "const onCanvas = ",
    "function unitState(",
    "const OVERLAP_CELL = ",
    "function overlapPairs(",
    "function coveredAt(",
)


def _run_cover(items: list[dict[str, Any]], days: list[str], counts: list[float]) -> Any:
    decls = "\n".join(_js_decl(head) for head in _COVER_DECLS)
    decls += "\n" + _lines_until_blank("const overlaps = ")
    source = _COVER_RUNNER % (_cover_block(), decls)
    return _node(source, {"items": items, "days": days, "counts": counts})


def test_a_pre_arrival_unit_hides_only_while_a_present_unit_overlaps_it() -> None:
    """OLD(처음부터 실물, 2026-12-01 에 빠짐) 자리에 NEW(2027-01-10 반입)가 겹쳐 놓였다.

    - OLD 가 있는 동안 NEW 는 숨는다. OLD 가 빠지는 날부터 NEW 는 반입 예정(보임)이고, 반입하면
      그대로 보인다.
    - 반입 전끼리(PRE-1·PRE-2)는 겹쳐도 둘 다 보인다.
    - 변만 맞닿은 EDGE(넓이 0)는 숨지 않는다.
    - 같은 묶음 모듈끼리(G-A 실물·G-B 반입 전)는 숨기지 않고, 다른 호기(STAY)가 덮은 모듈(H-A)은
      모듈 상자마다 숨는다."""
    items = [
        {"id": "OLD", "x": 10, "y": 10, "w": 12, "h": 7, "exitOn": "2026-12-01"},
        {"id": "NEW", "x": 12, "y": 11, "w": 12, "h": 7, "realFrom": "2027-01-10"},
        {"id": "EDGE", "x": 22, "y": 30, "w": 5, "h": 7, "realFrom": "2099-01-01"},
        {"id": "EDGE-BASE", "x": 10, "y": 30, "w": 12, "h": 7},
        {"id": "PRE-1", "x": 40, "y": 10, "w": 10, "h": 7, "realFrom": "2027-02-01"},
        {"id": "PRE-2", "x": 45, "y": 12, "w": 10, "h": 7, "realFrom": "2027-03-01"},
        {"id": "G-A", "x": 60, "y": 10, "w": 6, "h": 4, "group": "G"},
        {"id": "G-B", "x": 63, "y": 12, "w": 6, "h": 4, "group": "G", "realFrom": "2099-01-01"},
        {"id": "STAY", "x": 80, "y": 10, "w": 12, "h": 7},
        {"id": "H-A", "x": 85, "y": 12, "w": 6, "h": 4, "group": "H", "realFrom": "2099-01-01"},
        {"id": "H-B", "x": 100, "y": 12, "w": 6, "h": 4, "group": "H", "realFrom": "2099-01-01"},
    ]
    days = ["2026-11-01", "2026-11-30", "2026-12-01", "2027-01-10"]
    out = _run_cover(items, days, [1, 0.25, 1.5, 2.0, 1 / 3 * 3, 1234, 0.75])

    assert out["2026-11-01"] == ["H-A", "NEW"]
    assert out["2026-11-30"] == ["H-A", "NEW"]
    # OLD 가 빠진 날부터 NEW 는 반입 예정으로 보인다(반입 전이지만 덮는 호기가 없다).
    assert out["2026-12-01"] == ["H-A"]
    assert out["2027-01-10"] == ["H-A"]
    assert out["counts"] == ["1", "0.25", "1.5", "2", "1", "1,234", "0.75"]


def test_the_viewer_paints_the_cover_and_the_editor_does_not() -> None:
    """보기 화면만 숨긴다 — `paintUnit` 의 판정이 `VIEW && !FAB` 에 묶이고 숨김은 보임
    (`__visible`)에 들어 Main 설비명·겹침 꼭지가 따라간다. 숨은 상자는 visibility 로 숨어 눌리지
    않는다. 이웃의 판정이 바뀌면 그 이웃과 겹친 호기도 다시 칠한다. 겹침 짝은 상자를 칠하기 전에
    비운다."""
    paint = _between("function paintUnit(group, item) {", "function buildMark(item) {")
    assert "const covered = VIEW && !FAB && coveredAt(item, st)" in paint
    assert "group.__visible = st.visible && !covered" in paint
    assert "+covered}" in paint and "group.classList.toggle('is-covered', covered)" in paint
    assert (
        ".sle.is-view .sle-unit.is-gone, .sle.is-view .sle-unit.is-covered { visibility: hidden; }"
        in CSS
    )
    units = _between("function paintUnits(ids) {", "function paintAsOf(previous) {")
    assert "for (const other of pairs.get(id) || []) near.add(other)" in units
    assert "showSummary()" in units
    render = _between("function renderItems() {", "function repaint() {")
    assert render.index("S.adjacency = null") < render.index("buildGroup(item)")
    assert "S.covered = new Map()" in render
    # 편집기의 겹침 경고는 그대로다(보기 화면 갈래만 숨김을 본다).
    overlaps = _between("function markOverlaps(flipped) {", "function coveredAt(item, st) {")
    assert "coveredAt" not in overlaps and "is-covered" not in overlaps


def test_the_summary_adds_the_hidden_count_in_the_browser() -> None:
    """요약 줄은 파이썬 `summary` 에 숨긴 대수(설비지분 합)를 브라우저가 붙인다 — 숨김이 기준일마다
    바뀌므로. 지분은 `_clean_items` 의 `share` 가 싣고(`unitLook` 으로 읽음) 없으면 한 대다."""
    summary = _between("function showSummary() {", "function overlapPairs() {")
    assert "for (const share of S.covered.values()) hidden += share" in summary
    assert "겹쳐 숨긴 반입 예정 ${unitCountText(hidden)}대" in summary
    read = _between("const readUnit = (raw) => ({", "const readMark = (raw) => ({")
    assert "...unitLook(raw)" in read
    cleaned = space_layout_editor._clean_items(
        [
            {"id": "A", "share": 0.25},
            {"id": "B"},
            {"id": "C", "share": "x"},
            {"id": "D", "share": -1},
        ]
    )
    assert [item["share"] for item in cleaned] == [0.25, 1.0, 1.0, 1.0]


# ---------------------------------------------------------------- 호기 누르기(브라우저 쪽 글자)


def test_a_plain_click_in_the_floor_viewer_sends_the_picked_unit() -> None:
    """누르기(끌지 않음)·Esc 뒤 `notePick` — 층 상세 보기에서만(FAB·편집 아님), 호기가 아니면
    null, 같은 값은 다시 보내지 않는다. 파이썬이 쥔 값(`data.picked`)이 바뀐 회차에 도면의 고르기를
    맞추고, 새로 선 도면은 다시 고른다."""
    note = _between("function notePick() {", "function syncPick() {")
    assert "if (!PICKS) return" in note and "const PICKS = VIEW && !FAB" in JS
    assert "const id = item && isUnit(item) ? item.id : null" in note
    assert "if (id === S.pickSent) return" in note
    assert "setTriggerValue('pick', { epoch: S.epoch, id })" in note
    up = _between(
        "if (drag.mode === 'view') {\n      svg.classList.remove", "if (drag.mode === 'marquee')"
    )
    assert up.index("select(drag.id)") < up.index("notePick()")
    assert "else if (event.key === 'Escape') { select(null); notePick() }" in JS
    sync = _between("function syncPick() {", "syncPick()\n")
    assert "typeof data.picked === 'string'" in sync and "if (picked === S.pickData) return" in sync
    assert "S.pickData = undefined" in _between("if (S.epoch !== data.epoch) {", "} else {")


# ---------------------------------------------------------------- 파이썬 쪽


def test_the_pick_dispatcher_keeps_only_this_epochs_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_dispatch_pick` — 옛 epoch·글자 아닌 id 는 버리고, None 은 풀기, 글자는 앞뒤 공백을
    걷는다."""
    got: list[str | None] = []
    state: dict[str, Any] = {}
    monkeypatch.setattr(space_layout_editor, "st", SimpleNamespace(session_state=state))

    def send(payload: object) -> None:
        state["viewer"] = {"pick": payload}
        space_layout_editor._dispatch_pick("viewer", "view|1", got.append)

    send({"epoch": "view|0", "id": "EQ-01"})
    send({"epoch": "view|1", "id": 3})
    send({"epoch": "view|1", "id": "  "})
    send("EQ-01")
    assert got == []
    send({"epoch": "view|1", "id": " EQ-01 "})
    send({"epoch": "view|1", "id": None})
    assert got == ["EQ-01", None]
    space_layout_editor._dispatch_pick("viewer", "view|1", None)


def test_the_floor_table_takes_the_requested_columns_in_order() -> None:
    """21칸 — 요청한 차례이고 이름은 설비 마스터 그대로(「Qual 실적」 = `Qual실적`,
    「반입/Qual일정」 = `반입/Qual 이력`), 「단계」 는 기준일 상태(`단계`)다. Space 상태 표에 모두
    있다."""
    assert len(FLOOR_TABLE_COLUMNS) == 21
    assert FLOOR_TABLE_COLUMNS[:3] == ("Area Code", "공정소분류", "설비명")
    assert FLOOR_TABLE_COLUMNS[-3:] == ("반출/이설일정", "반입/Qual 이력", "단계")
    assert set(FLOOR_TABLE_COLUMNS) - set(EQUIPMENT_COLUMNS) == {"단계"}
    status = build_space_equipment_status(_master(), _downtime(), as_of=AS_OF)
    table = floor_table(status)
    assert list(table.columns) == list(FLOOR_TABLE_COLUMNS)
    assert table["단계"].tolist() == status["상태"].tolist()


def test_a_picked_module_brings_its_siblings_with_the_pressed_one_first() -> None:
    module = {"Main 설비": "MOD-1"}
    rows = _master(
        {**module, "설비명": "MOD-1C"},
        {**module, "설비명": "MOD-1A"},
        {**module, "설비명": "MOD-1D", "X좌표": None},
        {**module, "설비명": "MOD-1B"},
        {"설비명": " LONE "},
    )
    assert picked_unit_rows(rows, "MOD-1B")["설비명"].tolist() == [
        "MOD-1B",
        "MOD-1A",
        "MOD-1C",
        "MOD-1D",
    ]
    assert picked_unit_rows(rows, "EQ-01")["설비명"].tolist() == ["EQ-01"]
    assert picked_unit_rows(rows, "LONE")["설비명"].tolist() == [" LONE "]
    assert picked_unit_rows(rows, "GONE").empty


# ---------------------------------------------------------------- 화면(AppTest)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """`_EDITOR` 대역. 받은 data·콜백 이름을 적고, `PICK_KEY` 가 있으면 층 상세 뷰어가 `pick` 을
    보낸 것처럼 컴포넌트 상태에 넣고 `on_pick_change` 를 부른다."""
    recorded: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> None:
        import streamlit as st

        data = kwargs["data"]
        recorded.append(
            {**data, "callbacks": sorted(name for name in kwargs if name.startswith("on_"))}
        )
        payload = st.session_state.get(PICK_KEY)
        if payload is not None and data.get("scope") == "floor" and data.get("mode") == "view":
            del st.session_state[PICK_KEY]
            st.session_state[kwargs["key"]] = {"pick": payload}
            kwargs["on_pick_change"]()

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return recorded


@pytest.fixture
def downloads(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    """층 CSV 내려받기 대역 — 받은 바이트를 적는다(페이지는 회차마다 이 모듈에서 import 한다).

    `from … import render_csv_download` 로 이름을 잡는 모듈(설비 작업 공간)이 이 대역이 걸린 동안
    처음 import 되면 대역을 영영 붙든다 — 같은 프로세스의 뒤 시험에서 내려받기 단추가 사라진다.
    대역을 걸기 전에 그 모듈을 먼저 불러 둔다.
    """
    import capa_simulation.components.equipment_data_workspace  # noqa: F401

    got: list[bytes] = []

    def _record(*, data: bytes, **_: Any) -> None:
        got.append(data)

    monkeypatch.setattr(table_toolbar, "render_csv_download", _record)
    return got


def _open(tmp_path: Path, master: pd.DataFrame | None = None) -> AppTest:
    """C1 1F — EQ-01·EQ-02, Main 설비 MOD-1 모듈 넷(Process-B, 행 차례 C·A·D·B), 2F 에 UP-01."""
    module = {"Main 설비": "MOD-1", "공정소분류": "Process-B", "Xsize": 6, "Ysize": 4}
    if master is None:
        master = _master(
            {**module, "설비명": "MOD-1C", "X좌표": 60.0, "Y좌표": 10.0},
            {**module, "설비명": "MOD-1A", "X좌표": 60.0, "Y좌표": 14.0},
            {**module, "설비명": "MOD-1D", "X좌표": 66.0, "Y좌표": 10.0},
            {**module, "설비명": "MOD-1B", "X좌표": 66.0, "Y좌표": 14.0},
            {"설비명": "UP-01", "층": "2F"},
        )
    database = tmp_path / "space_pick.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), master, _downtime())
    clear_equipment_repository()
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=60)
    app.query_params["floor"] = "C1-1F"
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _viewer(calls: list[dict[str, Any]]) -> dict[str, Any]:
    found = [c for c in calls if c.get("scope") == "floor" and c.get("mode") == "view"]
    assert found
    return found[-1]


def _table(app: AppTest) -> pd.DataFrame:
    tables = [t.value for t in app.dataframe if "Area Code" in t.value.columns]
    assert len(tables) == 1
    frame: pd.DataFrame = tables[0]
    return frame


def _press(app: AppTest, calls: list[dict[str, Any]], unit: str | None, epoch: str = "") -> None:
    app.session_state[PICK_KEY] = {"epoch": epoch or _viewer(calls)["epoch"], "id": unit}
    app.run()
    app.run()
    assert not app.exception, [item.message for item in app.exception]


_FLOOR = ["EQ-01", "EQ-02", "MOD-1A", "MOD-1B", "MOD-1C", "MOD-1D"]


def test_pressing_a_unit_narrows_the_table_and_the_button_brings_the_floor_back(
    tmp_path: Path, calls: list[dict[str, Any]], downloads: list[bytes]
) -> None:
    app = _open(tmp_path)
    first = _viewer(calls)
    table = _table(app)
    assert list(table.columns) == list(FLOOR_TABLE_COLUMNS)
    assert sorted(table["설비명"]) == _FLOOR
    assert "on_pick_change" in first["callbacks"] and first["picked"] is None
    assert app.button(key=SHOW_ALL_KEY).disabled

    _press(app, calls, "EQ-01")
    assert _table(app)["설비명"].tolist() == ["EQ-01"]
    assert app.session_state[PICKED_KEY] == ("C1", "1F", "EQ-01")
    view = _viewer(calls)
    assert view["picked"] == "EQ-01" and view["epoch"] == first["epoch"]
    assert not app.button(key=SHOW_ALL_KEY).disabled
    # 설비명은 마크다운 글자 그대로다(`-` 앞에 `\\`).
    assert any("**EQ\\-01** 의 RawData 1줄" in element.value for element in app.markdown)
    # 층 CSV 는 표가 좁혀져도 층 전체·모든 칸이다.
    header, *lines = downloads[-1].decode("utf-8-sig").splitlines()
    assert "X좌표" in header.split(",") and len(lines) == len(_FLOOR)

    # 모듈을 누르면 그 Main 설비 줄 전부, 누른 모듈이 첫 줄이고 나머지는 자연 정렬이다.
    _press(app, calls, "MOD-1C")
    assert _table(app)["설비명"].tolist() == ["MOD-1C", "MOD-1A", "MOD-1B", "MOD-1D"]

    app.button(key=SHOW_ALL_KEY).click().run()
    assert not app.exception
    assert sorted(_table(app)["설비명"]) == _FLOOR
    assert PICKED_KEY not in app.session_state
    assert _viewer(calls)["picked"] is None and app.button(key=SHOW_ALL_KEY).disabled
    clear_equipment_repository()


def test_an_empty_press_or_an_old_epoch_or_another_floor_releases_or_ignores(
    tmp_path: Path, calls: list[dict[str, Any]], downloads: list[bytes]
) -> None:
    app = _open(tmp_path)
    _press(app, calls, "EQ-02", epoch="view|old")
    assert sorted(_table(app)["설비명"]) == _FLOOR and PICKED_KEY not in app.session_state

    _press(app, calls, "EQ-02")
    assert _table(app)["설비명"].tolist() == ["EQ-02"]
    # 도면 요소·빈 곳·Esc 는 id null 이다 — 층 전체로 돌아간다.
    _press(app, calls, None)
    assert sorted(_table(app)["설비명"]) == _FLOOR and PICKED_KEY not in app.session_state

    _press(app, calls, "EQ-02")
    app.session_state["space_status_selected_floor"] = "2F"
    app.run()
    assert not app.exception
    assert PICKED_KEY not in app.session_state
    assert _table(app)["설비명"].tolist() == ["UP-01"]
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()
    assert sorted(_table(app)["설비명"]) == _FLOOR

    # FAB 로 돌아가도 풀린다.
    _press(app, calls, "EQ-02")
    app.button(key="space_status_fab_breadcrumb").click().run()
    assert not app.exception and PICKED_KEY not in app.session_state
    clear_equipment_repository()


def test_a_picked_unit_filtered_out_of_the_floor_is_released(
    tmp_path: Path, calls: list[dict[str, Any]], downloads: list[bytes]
) -> None:
    """공정소분류 필터로 누른 호기가 이 층 행에서 빠지면 고른 것을 푼다(빈 표가 남지 않는다)."""
    app = _open(tmp_path)
    _press(app, calls, "MOD-1A")
    assert len(_table(app)) == 4
    app.multiselect(key="space_status_process_filter").set_value(["Process-A"]).run()
    assert not app.exception
    assert PICKED_KEY not in app.session_state
    assert sorted(_table(app)["설비명"]) == ["EQ-01", "EQ-02"]
    assert _viewer(calls)["picked"] is None
    clear_equipment_repository()


def test_the_viewer_sends_unit_shares_for_the_hidden_count(
    tmp_path: Path, calls: list[dict[str, Any]], downloads: list[bytes]
) -> None:
    """뷰어 호기마다 설비지분 — 모듈 넷은 0.25, 단독 호기는 1. 요약 줄의 「겹쳐 숨긴 반입 예정 n대」
    가 설비 대수다(범례와 같은 기준일 보유 지분)."""
    _open(tmp_path)
    shares = {item["id"]: item["share"] for item in _viewer(calls)["items"]}
    assert shares == {
        "EQ-01": 1.0,
        "EQ-02": 1.0,
        "MOD-1A": 0.25,
        "MOD-1B": 0.25,
        "MOD-1C": 0.25,
        "MOD-1D": 0.25,
    }
    clear_equipment_repository()


def test_a_partly_arrived_group_sends_the_legend_shares(
    tmp_path: Path, calls: list[dict[str, Any]], downloads: list[bytes]
) -> None:
    """일부 모듈만 반입한 Main 설비 — 지분은 범례·배치 대수와 같은 기준일 보유 지분(`설비지분`)이라
    반입한 둘이 0.5씩이고 반입 전 둘은 0 이다. 그래서 반입 전 모듈이 겹쳐 숨어도 「겹쳐 숨긴 반입
    예정」 은 범례의 반입 전 대수(0)와 어긋나지 않는다."""
    today = date.today()

    def day(days: int) -> str:
        return (today + timedelta(days=days)).isoformat()

    arrived = {
        "Main 설비": "GRP",
        "Xsize": 5,
        "Ysize": 5,
        "제진대일정": None,
        "물류일정": None,
        "반입일정": day(-90),
        "반입실적": day(-90),
        "Qual일정": day(300),
    }
    later = {**arrived, "반입일정": day(200), "반입실적": None, "Qual일정": day(230)}
    master = _master(
        {**arrived, "설비명": "G-A", "X좌표": 40.0, "Y좌표": 30.0},
        {**arrived, "설비명": "G-B", "X좌표": 45.0, "Y좌표": 30.0},
        {**later, "설비명": "G-C", "X좌표": 40.0, "Y좌표": 35.0},
        {**later, "설비명": "G-D", "X좌표": 45.0, "Y좌표": 35.0},
    )
    _open(tmp_path, master)

    shares = {item["id"]: item["share"] for item in _viewer(calls)["items"]}
    assert {key: shares[key] for key in ("G-A", "G-B", "G-C", "G-D")} == {
        "G-A": 0.5,
        "G-B": 0.5,
        "G-C": 0.0,
        "G-D": 0.0,
    }
    assert shares["EQ-01"] == 1.0
    clear_equipment_repository()


def test_the_browser_keeps_a_zero_share_and_refreshes_it_in_the_same_epoch() -> None:
    """0 은 그대로(한 대로 바꾸지 않는다), 숫자가 아니거나 음수면 한 대다. 지분은 같은 epoch
    회차에도 새로 받는다(`unitLook` · `sameLook`) — 파이썬 기준일이 바뀌면 지분도 바뀐다."""
    cleaned = space_layout_editor._clean_items([{"id": "A", "share": 0}, {"id": "B", "share": 0.5}])
    assert [item["share"] for item in cleaned] == [0.0, 0.5]
    look = _between("const unitLook = (raw) => ({", "const readUnit = (raw) => ({")
    assert "share: shareOf(raw.share)" in look
    assert "value >= 0 ? value : 1" in _js_decl("const shareOf = ")
    assert "o.share === n.share" in _lines_until_blank("const sameLook = ")


def test_the_floor_table_columns_are_the_requested_order() -> None:
    """21칸 전체 차례를 글자 그대로 고정한다(요청 순 — 칸 이름은 설비 마스터 그대로)."""
    assert FLOOR_TABLE_COLUMNS == (
        "Area Code",
        "공정소분류",
        "설비명",
        "공정구분",
        "투자Capa",
        "투자구분",
        "사용기준",
        "동",
        "층",
        "제진대일정",
        "물류일정",
        "반입일정",
        "반입실적",
        "반입상태",
        "Qual일정",
        "Qual실적",
        "Qual상태",
        "정지일정",
        "반출/이설일정",
        "반입/Qual 이력",
        "단계",
    )


def test_a_drag_in_the_floor_viewer_is_not_a_press() -> None:
    """보기 화면에서 호기 위를 눌러 문턱을 넘게 끌었다 놓으면(전체 보기라 화면이 움직이지 않아도)
    고르지도 `pick` 을 보내지도 않는다 — FAB 블록 열기와 같은 규칙(`drag.travelled`)."""
    up = _between(
        "if (drag.mode === 'view') {\n      svg.classList.remove", "if (drag.mode === 'marquee')"
    )
    assert "if (!drag.travelled) openFloor(item)" in up
    assert up.index("if (drag.travelled) return") < up.index("select(drag.id)")
    move = _between("svg.onpointermove = (event) => {", "if (event.buttons === 0)")
    assert move.index("if (far) drag.travelled = true") < move.index(
        "if (drag.mode === 'view' && S.view.z <= 1) return"
    )


def test_a_new_drawing_drops_the_copy_paste_notice() -> None:
    """복사·붙여넣기 알림(`S.flash`)은 그 도면의 것이다 — 새 epoch(적용 뒤 · 다른 층)에서 지운다."""
    fresh = _between("if (S.epoch !== data.epoch) {", "} else {")
    assert "S.flash = ''" in fresh
