# Purpose: 「Qual 마감 계산기」 탭이 서고 예시·비우기·편집·탭 왕복이 원본대로 도는지 검사한다.

"""Qual 마감 계산기 탭(`components/qual_deadline_calculator.py`).

계산 글자가 원본과 같은지는 `test_qual_deadline.py` 가 본다. 여기서는 화면이 그 결과를 그리는지,
「모두 비우기」·「예시로 되돌리기」·「표에 넣기」(엑셀 붙여넣기 칸)가 원본 규칙대로 칸을
바꾸는지, 목표 칸이 소수를 자르지 않는지, 편집표 편집이 닫힌 탭을 지나도 남는지, 이 탭이 설비
DB 를 열지 않고 페이지의 다른 탭과 key 가 겹치지 않는지를 본다. AppTest 는
편집표 칸을 고칠 수 없어 브라우저가 보내는 델타 꼴을 세션에 넣는다(`test_month_editor_filter` 와
같다).
"""

from __future__ import annotations

import ast
import json
import math
from datetime import date
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _page_script

from capa_simulation.components.qual_deadline_calculator import (
    BASE_KEY,
    CUTOFF_KEY,
    EDITOR_KEY,
    MONTHS_KEY,
    PASTE_APPLY_KEY,
    PASTE_TEXT_KEY,
    TARGET_COLUMN,
    TODAY_KEY,
    UNITS_COLUMN,
    YEAR_KEY,
)
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
from capa_simulation.navigation import EQUIPMENT_TAB_KEY
from capa_simulation.services.qual_deadline import EMPTY_UNITS_MESSAGE, NO_PASTED_LINES_MESSAGE
from capa_simulation.sidebar_status import CONDITION_CARD_PREFIX

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
TAB_LABEL = ":material/calculate: Qual 마감 계산기"
TODAY = date(2026, 10, 7)

# 설비 DB·시뮬레이션 DB 를 여는 길(`duckdb.connect`)을 막고 탭 본문만 그린다. 세션 칸
# `hide_calculator` 가 참이면 닫힌 탭처럼 그리지 않는다 — 페이지의 `tab_is_hidden` 갈래와 같다.
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


def test_the_tab_sits_after_the_viewing_tabs_and_before_the_input_forms(tmp_path: Path) -> None:
    app = _page(tmp_path)

    assert [tab.label for tab in app.tabs[:5]] == [
        ":material/dashboard: Main",
        ":material/compare_arrows: Static 대비 일정",
        TAB_LABEL,
        ":material/tune: Preference",
        ":material/table_rows: RawData",
    ]
    # 닫혀 있으면 그리지 않는다.
    assert not any(element.value.endswith("Qual 마감 계산기") for element in app.markdown)


def test_the_open_tab_draws_without_cards_samples_or_key_clashes(tmp_path: Path) -> None:
    """빈 설비 DB(샘플 조회) 페이지에서 이 탭을 연다. Preference·RawData 의 입력 폼도 같은 회차에
    그려지므로 key 가 겹치면 여기서 예외가 난다."""
    app = _page(tmp_path)
    app.session_state[EQUIPMENT_TAB_KEY] = TAB_LABEL
    app.run()

    assert not app.exception, [element.message for element in app.exception]
    assert _metrics(app)["마감 낸 호기"] == "9대"
    assert app.date_input(key=TODAY_KEY).value == date.today()
    # 설비 조회 조건 카드와 샘플 스위치는 보는 탭(Main·Static 대비 일정)에만 선다.
    assert not _has_key(app, f"{CONDITION_CARD_PREFIX}equipment")
    assert not _has_key(app, SAMPLE_TOGGLE_KEY)

    app.session_state[EQUIPMENT_TAB_KEY] = ":material/dashboard: Main"
    app.run()
    assert _has_key(app, f"{CONDITION_CARD_PREFIX}equipment")
    assert _has_key(app, SAMPLE_TOGGLE_KEY)


def test_inputs_survive_a_round_trip_through_another_tab(tmp_path: Path) -> None:
    app = _page(tmp_path)
    app.session_state[EQUIPMENT_TAB_KEY] = TAB_LABEL
    app.run()
    app.number_input(key=CUTOFF_KEY).set_value(15).run()
    app.number_input(key=BASE_KEY).set_value(17.5).run()
    first = _metrics(app)

    app.session_state[EQUIPMENT_TAB_KEY] = ":material/tune: Preference"
    app.run()
    assert not app.exception
    assert not [widget for widget in app.number_input if widget.key == CUTOFF_KEY]
    app.session_state[EQUIPMENT_TAB_KEY] = TAB_LABEL
    app.run()

    assert not app.exception
    assert app.number_input(key=CUTOFF_KEY).value == 15
    assert app.number_input(key=BASE_KEY).value == 17.5
    assert _metrics(app) == first
