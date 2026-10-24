# Purpose: 「Qual 마감 계산기」 팝업이 서고 예시·비우기·편집·팝업 왕복이 원본대로 도는지 검사한다.

"""Qual 마감 계산기 팝업(`components/qual_deadline_calculator.py`) — 필요 단축 일정 머리 단추가 연다
(2026-10-24 사용자 결정, 그 전에는 가용설비 현황의 탭).

계산 글자가 원본과 같은지는 `test_qual_deadline.py` 가 본다. 여기서는 화면이 그 결과를 그리는지,
「모두 비우기」·「예시로 되돌리기」·「표에 넣기」(엑셀 붙여넣기 칸)가 원본 규칙대로 칸을
바꾸는지, 목표 칸이 소수를 자르지 않는지, 편집표 편집이 닫힌 팝업을 지나도 남는지, 계산기가 설비
DB 를 열지 않고 호기가 없어도 열리며, 팝업을 여닫아도 이벤트 칸 자리 수가 같은지를 본다. AppTest 는
편집표 칸을 고칠 수 없어 브라우저가 보내는 델타 꼴을 세션에 넣는다(`test_month_editor_filter` 와
같다).
"""

from __future__ import annotations

import ast
import json
import math
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from fragment_browser import install_fragment_browser
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _page_script

from capa_simulation.components import qual_deadline_calculator as calculator
from capa_simulation.components.qual_deadline_calculator import (
    BASE_KEY,
    CUTOFF_KEY,
    EDITOR_KEY,
    MONTH_COLUMN,
    MONTHS_KEY,
    PASTE_APPLY_KEY,
    PASTE_TEXT_KEY,
    TARGET_COLUMN,
    TODAY_KEY,
    UNITS_COLUMN,
    YEAR_KEY,
    calculator_style_markup,
    layout_style,
)
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
from capa_simulation.services.qual_deadline import (
    EMPTY_UNITS_MESSAGE,
    NO_PASTED_LINES_MESSAGE,
    UNIT_TABLE_COLUMNS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = PROJECT_ROOT / "app_pages" / "required_shortening.py"
# 필요 단축 일정 화면의 팝업 칸·여는 단추(`app_pages/required_shortening.py`).
DIALOG_KEY = "required_shortening_open_dialog"
OPEN_BUTTON_KEY = "required_shortening_qual_calculator_v1"
TODAY = date(2026, 10, 7)

# 설비 DB·시뮬레이션 DB 를 여는 길(`duckdb.connect`)을 막고 팝업 본문만 그린다. 세션 칸
# `hide_calculator` 가 참이면 닫힌 팝업처럼 그리지 않는다 — 페이지의 팝업 호스트 갈래와 같다.
# `merge_editor` 가 참이면 Streamlit 이 편집표 `on_change` 를 부르는 자리(본문 앞)에서 그 콜백을
# 부른다 — AppTest 는 세션에 넣은 델타로 콜백을 부르지 않는다.
COMPONENT_SCRIPT = f"""
from datetime import date

import duckdb
import streamlit as st


from capa_simulation.components import qual_deadline_calculator as calculator
from capa_simulation.components.editor_state import editor_widget_key


def _blocked(*args, **kwargs):
    raise RuntimeError("Qual 마감 계산기가 DB 를 열었다")


# AppTest 는 한 프로세스에서 돈다 — 막은 것을 되돌려야 뒤 시험이 DB 를 연다.
original_connect = duckdb.connect
duckdb.connect = _blocked
try:
    if st.session_state.pop("merge_editor", False):
        calculator._keep_editor_edits(editor_widget_key(calculator.EDITOR_KEY))
    if not st.session_state.get("hide_calculator", False):
        calculator.render_qual_deadline_calculator(
            today=date({TODAY.year}, {TODAY.month}, {TODAY.day})
        )
finally:
    duckdb.connect = original_connect
"""


def _component() -> AppTest:
    app = AppTest.from_string(COMPONENT_SCRIPT, default_timeout=30).run()
    assert not app.exception, [element.message for element in app.exception]
    return app


def _metrics(app: AppTest) -> dict[str, str]:
    return {metric.label: metric.value for metric in app.metric}


def _example_badge(app: AppTest) -> bool:
    return any("지금 값은 예시입니다" in element.value for element in app.markdown)


def _editor_key(app: AppTest) -> str:
    generation_key = f"{EDITOR_KEY}__generation"
    generation = app.session_state[generation_key] if generation_key in app.session_state else 0
    return EDITOR_KEY if not generation else f"{EDITOR_KEY}__g{generation}"


def _edit(app: AppTest, row: int, column: str, value: object) -> None:
    """편집표 칸 하나를 고친 델타 — 브라우저가 보내는 꼴(행 위치 · 칸 이름 · 값)."""
    app.session_state[_editor_key(app)] = {
        "edited_rows": {row: {column: value}},
        "added_rows": [],
        "deleted_rows": [],
    }


def _units_table(app: AppTest) -> pd.DataFrame:
    """호기별 표. 화면 차례는 편집표 · 호기별 표 · 월 점검 표다."""
    frame = app.dataframe[1].value
    assert isinstance(frame, pd.DataFrame)
    return frame


def test_the_example_draws_the_original_results() -> None:
    app = _component()

    assert _metrics(app) == {
        "마감 낸 호기": "9대",
        "가장 이른 마감": "01.21",
        "이미 지난 마감": "0대",
        "목표 대비 부족 달": "0개월",
    }
    assert _example_badge(app)
    assert [(widget.label, widget.value) for widget in app.number_input] == [
        ("Cut-off (일)", 10),
        ("연도", 2027),
        ("직전 달(전년 12월) 가용대수", 18.0),
    ]
    assert app.date_input(key=TODAY_KEY).value == TODAY
    units = _units_table(app)
    assert units["호기"].tolist()[:3] == ["U21", "U22", "U23"]
    assert units.loc[2, "Qual 완료 마감"] == "2027-04-05"
    checks = app.dataframe[2].value
    assert checks["판정"].tolist() == ["충족"] * 12
    labels = {getattr(button, "label", None) for button in app.main.get("download_button")}
    assert labels == {"호기별 결과 CSV", "월 점검 CSV"}


def test_clear_keeps_cutoff_year_and_today_and_reset_brings_the_example_back() -> None:
    app = _component()
    app.button(key="equipment_qualcalc_clear_v1").click().run()

    assert not app.exception
    assert app.number_input(key=CUTOFF_KEY).value == 10
    assert app.number_input(key=YEAR_KEY).value == 2027
    assert app.number_input(key=BASE_KEY).value is None
    assert app.date_input(key=TODAY_KEY).value == TODAY
    assert _metrics(app)["마감 낸 호기"] == "0대"
    assert _metrics(app)["가장 이른 마감"] == "—"
    assert EMPTY_UNITS_MESSAGE in [element.value for element in app.caption]
    assert app.dataframe[1].value["판정"].tolist() == ["목표 없음"] * 12
    assert not _example_badge(app)

    app.button(key="equipment_qualcalc_reset_v1").click().run()

    assert not app.exception
    assert app.number_input(key=BASE_KEY).value == 18.0
    assert _metrics(app)["마감 낸 호기"] == "9대"
    assert _example_badge(app)


def test_a_changed_number_or_today_recomputes_and_hides_the_example_badge() -> None:
    app = _component()
    app.date_input(key=TODAY_KEY).set_value(date(2027, 3, 1)).run()

    assert _metrics(app)["이미 지난 마감"] == "2대"
    assert not _example_badge(app)
    memo = _units_table(app).set_index("호기")["메모"]
    assert memo["U22"] == "마감이 이미 지남"

    app.number_input(key=BASE_KEY).set_value(16.0).run()
    assert _metrics(app)["목표 대비 부족 달"] == "12개월"


def test_an_editor_edit_recomputes_and_survives_a_hidden_tab() -> None:
    app = _component()
    _edit(app, 0, UNITS_COLUMN, "U20")
    app.run()

    units = _units_table(app)
    assert units.loc[0, "호기"] == "U20"
    assert units.loc[0, "메모"] == "1월에 적은 호기 — 2월에 처음 필요"
    assert not _example_badge(app)

    # 칸을 고치고 곧바로 다른 탭을 누른 회차 — 편집과 탭 전환이 한 회차에 와서 편집표를 그리지
    # 않는다. 콜백이 본문 앞에서 편집을 원본 표에 옮겨 두므로 다시 열어도 남는다. (AppTest 는 그리지
    # 않은 편집표의 델타를 다음 회차에 들고 가지 않아, 델타를 넣는 회차와 콜백 회차를 하나로 둔다.)
    _edit(app, 0, UNITS_COLUMN, "U20")
    app.session_state["merge_editor"] = True
    app.session_state["hide_calculator"] = True
    app.run()
    stored = app.session_state[MONTHS_KEY]
    assert stored.loc[0, UNITS_COLUMN] == "U20"
    app.session_state["hide_calculator"] = False
    app.run()

    assert not app.exception
    assert _units_table(app).loc[0, "호기"] == "U20"


def test_a_cleared_target_cell_skips_that_month() -> None:
    app = _component()
    _edit(app, 3, TARGET_COLUMN, None)
    app.run()

    checks = app.dataframe[2].value
    assert checks.loc[3, "목표"] == "—"
    assert checks.loc[3, "판정"] == "목표 없음"
    # 4월에 적은 U23 은 5월로 넘어가 쓰인다.
    units = _units_table(app).set_index("호기")
    assert units.loc["U23", "쓰이는 달"] == "5월"


def test_reset_discards_the_editor_edits() -> None:
    """되돌리기는 편집표를 새 위젯으로 세운다 — 옛 델타가 예시 위에 다시 얹히지 않는다."""
    app = _component()
    _edit(app, 1, TARGET_COLUMN, 30.0)
    app.run()
    assert _metrics(app)["목표 대비 부족 달"] != "0개월"

    app.button(key="equipment_qualcalc_reset_v1").click().run()

    assert _metrics(app)["목표 대비 부족 달"] == "0개월"
    assert _editor_key(app) != EDITOR_KEY
    assert _example_badge(app)


def test_the_target_column_keeps_every_decimal() -> None:
    """목표 칸에 `step` 을 주지 않는다 — Streamlit 1.63 편집표는 `step` 의 소수 자릿수에서 값을 잘라
    저장한다(19.3456 → 19.34, 원본은 그대로 계산). `format` 도 없어 적은 값이 그대로 보인다."""
    app = _component()
    config = json.loads(app.dataframe[0].proto.columns)[TARGET_COLUMN]
    assert config["type_config"] == {"type": "number"}

    _edit(app, 0, TARGET_COLUMN, 19.3456)
    app.run()
    # 잘렸다면 「19.34」·「부족 1.34대」 다.
    january = app.dataframe[2].value.loc[0]
    assert (january["목표"], january["판정"]) == ("19.35", "부족 1.35대")


def _column_widths(app: AppTest, index: int) -> dict[str, object]:
    config = json.loads(app.dataframe[index].proto.columns)
    return {name: spec.get("width") for name, spec in config.items() if name != "_index"}


def test_the_month_editor_fits_inside_the_input_box() -> None:
    """편집표 세 칸 폭의 합이 입력 칸 안에 든다. 넘으면 표가 칸 안에서 가로로 넘어, 「신규 호기」
    칸을 고칠 때 표가 오른쪽으로 밀려 「월」 칸이 가려진다(`large` 일 때 1600px 창에서 105px
    넘쳤다)."""
    widths = _column_widths(_component(), 0)

    assert list(widths) == [MONTH_COLUMN, TARGET_COLUMN, UNITS_COLUMN]
    assert all(isinstance(width, int) for width in widths.values())
    total = sum(int(str(width)) for width in widths.values())
    assert total <= calculator._INPUTS_BOX_PX - calculator._BOX_CHROME_PX


def test_the_unit_table_gives_the_memo_room_and_fits_the_side_by_side_results_box() -> None:
    """호기별 표 칸마다 폭이 있고 `메모` 칸이 원본 메모 한 가지를 다 담는다(폭을 주지 않으면 머리 글
    폭에 고른 몫만 붙어 1600px 창에서 90px 안팎으로 잘렸다). 결과 칸이 옆에 설 때의 가장 좁은 폭은
    이 표를 가로 넘김 없이 담는 폭이다."""
    widths = _column_widths(_component(), 1)

    assert list(widths) == list(UNIT_TABLE_COLUMNS)
    assert all(isinstance(width, int) for width in widths.values())
    assert int(str(widths["메모"])) >= 240
    total = sum(int(str(width)) for width in widths.values())
    assert calculator._RESULTS_MIN_PX == total + calculator._BOX_CHROME_PX


def test_the_two_boxes_stack_when_the_row_cannot_hold_both() -> None:
    """원본처럼 좁으면 위아래로 — 두 칸을 담은 줄의 폭으로 가른다(사이드바가 본문 폭을 바꾼다).
    가르는 폭은 입력 칸 · 틈 · 결과 칸의 가장 좁은 폭의 합이고, 900px 창(사이드바 열림, 줄
    565px)은 쌓이고 1600px 창(줄 1265px)은 나란히 선다."""
    app = _component()
    style = layout_style()

    assert any(style in str(element.proto.body) for element in app.get("html"))
    assert calculator._STACK_BELOW_PX == (
        calculator._INPUTS_BOX_PX + calculator._LAYOUT_GAP_PX + calculator._RESULTS_MIN_PX
    )
    assert 565 < calculator._STACK_BELOW_PX < 1265
    layout_key = calculator._LAYOUT_KEY
    assert f".st-key-{layout_key} {{ container: capa-qualcalc / inline-size; }}" in style
    assert f"@container capa-qualcalc (width < {calculator._STACK_BELOW_PX}px)" in style
    # 가로 컨테이너의 flex 항목은 키 붙은 칸을 감싼 `stLayoutWrapper` 다.
    for key in (calculator._INPUTS_BOX_KEY, calculator._RESULTS_BOX_KEY):
        assert f'[data-testid="stLayoutWrapper"]:has(> .st-key-{key})' in style
        assert _has_key(app, key)
    assert f"flex: 0 0 {calculator._INPUTS_BOX_PX}px" in style


def _paste(app: AppTest, text: str) -> None:
    app.text_area(key=PASTE_TEXT_KEY).set_value(text)
    app.button(key=PASTE_APPLY_KEY).click().run()
    assert not app.exception, [element.message for element in app.exception]


def test_the_paste_box_fills_months_from_january_like_the_original() -> None:
    """원본 「엑셀에서 한 번에 붙여넣기」 — 둘째 칸부터 끝까지가 호기, 붙여 넣은 줄 뒤 달은
    그대로."""
    app = _component()
    _paste(app, "19.3456\tU1\tU2")

    assert [element.value for element in app.success] == ["1개월을 넣었습니다."]
    units = _units_table(app)
    assert units.loc[:2, ["호기", "그 달 기여", "Qual 완료 마감"]].values.tolist() == [
        ["U1", "1.00", "2026-12-21"],
        ["U2", "0.35", "2027-01-10"],
        ["U21", "0.50", "2027-04-05"],
    ]
    stored = app.session_state[MONTHS_KEY]
    assert stored.loc[0, TARGET_COLUMN] == 19.3456
    assert stored[UNITS_COLUMN].tolist()[:3] == ["U1 U2", "U21", "U22"]
    assert not _example_badge(app)

    # 알림은 한 번만 — 다음 회차에는 없다.
    app.run()
    assert not app.success


def test_pasting_replaces_editor_edits_of_those_months() -> None:
    """편집표 델타는 행 위치라 그대로 두면 붙여 넣은 값을 다시 덮는다 — 넣으면 편집표를 새로
    세운다."""
    app = _component()
    _edit(app, 0, UNITS_COLUMN, "U20")
    app.run()
    assert _units_table(app).loc[0, "호기"] == "U20"

    _paste(app, "18\tU9\n\t\n19")

    assert _editor_key(app) != EDITOR_KEY
    assert [element.value for element in app.success] == ["2개월을 넣었습니다."]
    stored = app.session_state[MONTHS_KEY]
    # 두 칸 다 빈 줄 「\t」 은 건너뛰어 「19」 가 2월로 간다(원본대로). 2월 호기 글은 비워진다.
    assert stored.loc[:1, [TARGET_COLUMN, UNITS_COLUMN]].values.tolist() == [
        [18.0, "U9"],
        [19.0, ""],
    ]
    assert _units_table(app).loc[0, "호기"] == "U9"


def test_an_empty_paste_changes_nothing() -> None:
    app = _component()
    _paste(app, " \n\t\n")

    assert [element.value for element in app.info] == [NO_PASTED_LINES_MESSAGE]
    assert _editor_key(app) == EDITOR_KEY
    assert _example_badge(app)
    assert not math.isnan(app.session_state[MONTHS_KEY].loc[0, TARGET_COLUMN])


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_the_calculator_reads_no_other_data() -> None:
    """다른 데이터와 잇지 않는다(2026-10-22 사용자 요청) — DB·캐시·설정·시나리오 모듈을 들이지
    않는다."""
    forbidden = (
        "persistence",
        "duckdb",
        "settings",
        "simulation_cache",
        "page_bootstrap",
        "capa_simulation.io",
    )
    for relative in (
        "src/capa_simulation/components/qual_deadline_calculator.py",
        "src/capa_simulation/services/qual_deadline.py",
    ):
        imported = _imported_modules(PROJECT_ROOT / relative)
        offenders = sorted(name for name in imported if any(part in name for part in forbidden))
        assert not offenders, f"{relative}: {offenders}"


def _has_key(app: AppTest, key: str) -> bool:
    try:
        app.get_by_key(key)
    except KeyError:
        return False
    return True


def _page(tmp_path: Path) -> AppTest:
    app = AppTest.from_string(
        _page_script(PAGE_PATH, tmp_path / "qual_calculator.duckdb"), default_timeout=60
    ).run()
    assert not app.exception, [element.message for element in app.exception]
    return app


def _open(app: AppTest) -> AppTest:
    app.button(key=OPEN_BUTTON_KEY).click().run()
    assert not app.exception, [element.message for element in app.exception]
    return app


def test_the_header_button_opens_the_calculator_in_a_dialog(tmp_path: Path) -> None:
    """필요 단축 일정 머리 끝의 단추가 팝업을 연다. 닫혀 있으면 계산기를 그리지 않는다. 팝업 안에는
    본문 제목을 다시 적지 않는다(팝업 머리가 제목이다)."""
    app = _page(tmp_path)
    assert not _has_key(app, CUTOFF_KEY)
    assert DIALOG_KEY not in app.session_state

    _open(app)

    assert app.session_state[DIALOG_KEY] == "qual_calculator"
    assert _metrics(app)["마감 낸 호기"] == "9대"
    assert app.date_input(key=TODAY_KEY).value == date.today()
    assert not any(element.value.endswith("Qual 마감 계산기") for element in app.markdown)
    # 화면 탭 묶음이 아니다 — 필요 단축 일정에는 여전히 탭이 없다.
    assert not app.tabs


def test_the_calculator_opens_even_when_the_screen_has_no_units(tmp_path: Path) -> None:
    """호기가 없어 화면이 멈춰도(`st.stop`) 계산기는 열린다 — 설비 데이터와 잇지 않는다."""
    app = _page(tmp_path)
    app.session_state[SAMPLE_TOGGLE_KEY] = False
    app.run()
    assert any("등록된 호기가 없습니다" in element.value for element in app.info)

    _open(app)

    assert _metrics(app)["마감 낸 호기"] == "9대"


def test_inputs_survive_closing_and_reopening_the_dialog(tmp_path: Path) -> None:
    app = _open(_page(tmp_path))
    app.number_input(key=CUTOFF_KEY).set_value(15).run()
    app.number_input(key=BASE_KEY).set_value(17.5).run()
    first = _metrics(app)

    # 닫기(`on_dismiss`)는 열림 칸을 지운다.
    del app.session_state[DIALOG_KEY]
    app.run()
    assert not app.exception
    assert not _has_key(app, CUTOFF_KEY)
    _open(app)

    assert app.number_input(key=CUTOFF_KEY).value == 15
    assert app.number_input(key=BASE_KEY).value == 17.5
    assert _metrics(app) == first


def _event_slot_count(messages: Sequence[ForwardMsg]) -> int:
    """앱 전체 회차가 이벤트 칸(본문 밖 최상위 칸)에 쓴 자리 수."""
    count = 0
    for message in messages:
        if message.WhichOneof("type") != "delta":
            continue
        path = list(message.metadata.delta_path)
        if len(path) == 2 and path[0] == RootContainer.EVENT:
            count = max(count, path[1] + 1)
    return count


def test_opening_the_dialog_keeps_the_event_slot_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """팝업을 연 회차와 닫은 회차가 이벤트 칸에 같은 수의 자리를 쓴다. 다르면 그 뒤 기준선 알림
    토스트 자리가 밀려 지난 알림이 다시 뜬다(`shortening_progress_panel`). 계산기 서식은 안내 줄과
    한 `st.html` 에 실려 본문 칸으로 간다 — 지난 마감·부족 달이 생겨 띠 색이 붙어도 같다."""
    browser = install_fragment_browser(monkeypatch)
    app = _page(tmp_path)
    closed = _event_slot_count(browser.messages)

    assert closed > 0
    _open(app)
    opened = _event_slot_count(browser.messages)
    assert opened == closed
    # 띠 색이 붙는 갈래(지난 마감 — 오늘을 아주 뒤로).
    app.date_input(key=TODAY_KEY).set_value(date(2099, 1, 1)).run()
    assert not app.exception
    assert _metrics(app)["이미 지난 마감"] != "0대"
    assert _event_slot_count(browser.messages) == closed
    markup = calculator_style_markup()
    assert any(markup in str(element.proto.body) for element in app.get("html"))
