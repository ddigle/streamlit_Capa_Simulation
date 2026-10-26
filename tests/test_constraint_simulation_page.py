# Purpose: 제약 시뮬레이션 화면의 진입·주소 인자·조건 카드·까닭 카드·캐시 공유·쓰기 없음·달 고르기를
# 본다.

"""제약 시뮬레이션 화면(AppTest).

페이지만 띄운다(`tests/test_process_capa_detail_page.py` 와 같은 하네스 — 내장 시드를 임시 DuckDB 에
부트스트랩). 설비 일정은 시드 공정 하나(`DEMO_Chip_Attach`)에 기존보유 4대 + Qual 끝난 신규
8대·Cut-off 7 을 넣은 따로 된 하네스로 본다. 내장 시드는 소요가 작아 확보율이 수천 % 다 — 숫자는
손계산 시험 (`tests/test_constraint_simulation.py`·`tests/test_constraint_simulation_figures.py`)이
보고, 여기서는 화면의 갈래·상태·캐시·쓰기를 본다.

- 칸 누름은 AppTest 가 재현하지 못하므로 콜백이 적는 세션 달을 넣고 **진짜 프래그먼트 회차**
  (`tests/fragment_browser.py`)로 본문 프래그먼트만 도는지, 이벤트 칸 수가 같은지 본다.
- 제약 시작·끝 상자는 브라우저처럼 글자를 들고 다니는 `tests/widget_browser.py` 의 `BrowserChoice`
  로, 버튼·숫자 칸은 AppTest `button_group`·`number_input` 으로 잰다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fragment_browser import install_fragment_browser
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ButtonGroup
from test_required_shortening import _cutoff, _downtime, _master, _unit
from widget_browser import BrowserChoice

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.preset_number_field import CUSTOM_OPTION
from capa_simulation.constraint_simulation_state import (
    CONSTRAINT_CHART_KEY,
    CONSTRAINT_GENERAL_INPUT_KEY,
    CONSTRAINT_GENERAL_KEY,
    CONSTRAINT_GENERAL_PILLS_KEY,
    CONSTRAINT_MOD_DAYS_INPUT_KEY,
    CONSTRAINT_MOD_DAYS_KEY,
    CONSTRAINT_MOD_DAYS_PILLS_KEY,
    CONSTRAINT_MODIFY_KEY,
    CONSTRAINT_MONTH_KEY,
    CONSTRAINT_PERIOD_END_KEY,
    CONSTRAINT_PERIOD_START_KEY,
    CONSTRAINT_PROCESS_KEY,
    CONSTRAINT_PRODUCT_KEY,
    CONSTRAINT_PROPORTIONAL_KEY,
    CONSTRAINT_SHEET_KEY,
    CONSTRAINT_TARGET_INPUT_KEY,
    CONSTRAINT_TARGET_KEY,
    CONSTRAINT_TARGET_PILLS_KEY,
    CONSTRAINT_VIEW_FRAGMENT_KEY,
)
from capa_simulation.navigation import CONSTRAINT_SIMULATION, PROCESS_CAPA_DETAIL
from capa_simulation.persistence.cache import clear_global_securement_threshold_cache
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import MONTH_RANGE_KEY
from capa_simulation.services.required_shortening import ShorteningPlan, plan_required_shortening

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / CONSTRAINT_SIMULATION.path
DETAIL_PAGE = PROJECT_ROOT / PROCESS_CAPA_DETAIL.path
DYNAMIC_PROCESS = "DEMO_Chip_Attach"
OTHER_PROCESS = "DEMO_Final_Test"
FIRST_PRODUCT = "DEMO PRODUCT A"


def _page_script(database_path: Path, equipment_path: Path) -> str:
    """세션 `_test_page` 가 「detail」 이면 공정 Capa 상세, 「away」 면 다른 화면(빈 글), 아니면 이
    화면."""
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.month_range_picker as month_range_picker
import capa_simulation.settings as settings

original_database_path = settings.DUCKDB_PATH
original_equipment_path = settings.EQUIPMENT_DUCKDB_PATH
original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
original_month_picker = month_range_picker.render_month_range_apply
original_page_link = st.page_link

settings.DUCKDB_PATH = Path({str(database_path)!r})
settings.EQUIPMENT_DUCKDB_PATH = Path({str(equipment_path)!r})
horizontal_scrollbar.render_horizontal_scrollbar = lambda *args, **kwargs: None
month_range_picker.render_month_range_apply = (
    lambda *, start, end, min_month, max_month, key: None
)


def _recording_page_link(page, *args, **kwargs):
    st.session_state.setdefault("captured_page_links", []).append({{"page": str(page), **kwargs}})
    return original_page_link(page, *args, **kwargs)


st.page_link = _recording_page_link
try:
    from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
    from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

    bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    apply_pending_scenario_preset()
    st.session_state["captured_page_links"] = []
    choice = st.session_state.get("_test_page", "constraint")
    if choice == "away":
        st.write("다른 화면")
    else:
        source = Path({str(DETAIL_PAGE)!r}) if choice == "detail" else Path({str(PAGE)!r})
        exec(
            compile(source.read_text(encoding="utf-8"), str(source), "exec"),
            {{"__name__": "__main__"}},
        )
finally:
    settings.DUCKDB_PATH = original_database_path
    settings.EQUIPMENT_DUCKDB_PATH = original_equipment_path
    horizontal_scrollbar.render_horizontal_scrollbar = original_scrollbar
    month_range_picker.render_month_range_apply = original_month_picker
    st.page_link = original_page_link
"""


def _equipment_database(path: Path) -> Path:
    """시드 공정 하나에 기존보유 4대 + Qual 끝난 신규 8대·Cut-off 7 — 모든 달 설비 일정 기준 가용
    12."""
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    master = _master(
        [
            _unit(
                f"CA-{index:02d}",
                date(2025, 1, 10),
                process=DYNAMIC_PROCESS,
                arrival=date(2024, 12, 1),
            )
            for index in range(1, 9)
        ]
    )
    baseline = pd.DataFrame(
        {"공정": [DYNAMIC_PROCESS], "분류": ["전체"], "기존보유대수": [4.0], "비고": [None]}
    )
    repository.save_snapshot(baseline, master, _downtime([]))
    repository.save_process_cutoff(_cutoff(7, DYNAMIC_PROCESS))
    return path


@pytest.fixture(scope="module")
def databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """설비 DB 가 빈 하네스 — 까닭 카드 갈래."""
    root = tmp_path_factory.mktemp("constraint_simulation_empty")
    return root / "scenario.duckdb", root / "equipment.duckdb"


@pytest.fixture(scope="module")
def dynamic_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("constraint_simulation_dynamic")
    return root / "scenario.duckdb", _equipment_database(root / "equipment.duckdb")


@pytest.fixture()
def own_databases(tmp_path: Path) -> tuple[Path, Path]:
    """공용 판정 기준을 고치는 시험의 따로 된 DB 한 벌(모듈 DB 를 더럽히지 않게)."""
    return tmp_path / "scenario.duckdb", _equipment_database(tmp_path / "equipment.duckdb")


def _app(databases: tuple[Path, Path]) -> AppTest:
    return AppTest.from_string(_page_script(*databases), default_timeout=300)


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [element.message for element in app.exception]
    return app


def _opened(databases: tuple[Path, Path], process: str = DYNAMIC_PROCESS) -> AppTest:
    app = _app(databases)
    app.query_params["process"] = process
    return _ok(app.run())


def _chart_ids(app: AppTest) -> list[str]:
    return [str(chart.proto.id) for chart in app.get("plotly_chart")]


def _has_chart(app: AppTest, key: str) -> bool:
    return any(chart_id.endswith(f"-{key}") for chart_id in _chart_ids(app))


def _chart_spec(app: AppTest, key: str) -> dict[str, Any]:
    for chart in app.get("plotly_chart"):
        if str(chart.proto.id).endswith(f"-{key}"):
            spec: dict[str, Any] = json.loads(chart.proto.spec)
            return spec
    raise AssertionError(f"{key} 그림이 없다")


def _metric(app: AppTest, label: str) -> str:
    for metric in app.metric:
        if metric.label == label:
            return str(metric.value)
    raise AssertionError(f"{label} 지표가 없다: {[item.label for item in app.metric]}")


def _markdown(app: AppTest) -> list[str]:
    return [str(element.value) for element in app.markdown]


def _captions(app: AppTest) -> str:
    return " ".join(str(element.value) for element in app.caption)


def _metric_caption(app: AppTest, label: str) -> str:
    """지표 카드 값 아래 회색 줄(`delta` 자리)."""
    for metric in app.metric:
        if metric.label == label:
            return str(metric.proto.delta)
    raise AssertionError(f"{label} 지표가 없다")


def _plain(text: str) -> str:
    """마크다운 escape(`literal_markdown`)를 걷은 글."""
    return re.sub(r"\\(.)", r"\1", text)


def _header_line(app: AppTest) -> str:
    """머리 한 줄(escape 를 걷은 글)."""
    lines = [_plain(text) for text in _markdown(app) if " · 제약 " in text and "기준 " in text]
    assert len(lines) == 1, _markdown(app)
    return lines[0]


# ------------------------------------------------------------------ 진입·갈래


def test_a_fractional_cutoff_is_named_as_the_floored_days_it_counts(tmp_path: Path) -> None:
    """「설정」 팝업에 7.5 를 적으면 계산은 7일 창을 쓴다(`wd_window` 내림). 조건 줄이 「Cut-off
    7일 — 「설정」 팝업의 공정별 값」 이라 팝업의 7.5 와 어긋나 보였다(2026-10-26 E2E) — 내림을
    함께 적는다."""
    databases = (tmp_path / "scenario.duckdb", _equipment_database(tmp_path / "equipment.duckdb"))
    DuckDBEquipmentRepository(databases[1]).save_process_cutoff(_cutoff(7.5, DYNAMIC_PROCESS))
    app = _opened(databases)

    assert "Cut-off 7일(7.5일 내림) — 가용설비 현황 「설정」 팝업의 공정별 값" in _captions(app)


def test_an_empty_equipment_database_stands_the_card_and_one_reason_card(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    assert app.selectbox(key=CONSTRAINT_PROCESS_KEY).value is not None
    markdown = " ".join(_markdown(app))
    assert "설비 일정 없음: 저장본 없음" in markdown
    assert not app.metric
    assert not _has_chart(app, CONSTRAINT_CHART_KEY)


def test_a_process_with_equipment_shows_kpis_figures_steps_and_schedule(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _opened(dynamic_databases)
    assert app.selectbox(key=CONSTRAINT_PROCESS_KEY).value == DYNAMIC_PROCESS
    assert app.selectbox(key=CONSTRAINT_PRODUCT_KEY).value == FIRST_PRODUCT
    labels = [metric.label for metric in app.metric]
    assert labels == [
        "제약 제품 확보율 충족",
        "기존 제품 최저 확보율",
        "기준 미달 달 (기존 제품)",
        "개조 대수",
    ]
    assert _has_chart(app, CONSTRAINT_CHART_KEY)
    assert _has_chart(app, CONSTRAINT_SHEET_KEY)
    steps = [text for text in _markdown(app) if text[:4] in {f"**{n}*" for n in range(1, 6)}]
    assert len(steps) == 5
    assert "**개조 일정**" in _markdown(app)
    # 머리 한 줄 — 기본값(D8): 제약 120% · 기준 HOME · 개조 30일.
    header = _header_line(app)
    assert "제약 120%" in header and "기준 HOME" in header and "개조 30일" in header
    assert "저장하지 않는 시뮬레이션입니다" in _captions(app)
    assert "가용 = 설비 일정 기준" in _captions(app)
    # 머리 「← 공정 Capa 상세」 는 그 공정으로 돌아간다(테마 인자 없음).
    links = app.session_state["captured_page_links"]
    back = [link for link in links if link["page"] == PROCESS_CAPA_DETAIL.path]
    assert back and back[0]["query_params"] == {"process": DYNAMIC_PROCESS}


def test_the_process_param_is_taken_once_and_the_theme_stays(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _app(dynamic_databases)
    app.session_state[CONSTRAINT_PROCESS_KEY] = OTHER_PROCESS
    app.query_params["process"] = DYNAMIC_PROCESS
    app.query_params["theme"] = "dark"
    _ok(app.run())
    assert app.selectbox(key=CONSTRAINT_PROCESS_KEY).value == DYNAMIC_PROCESS
    assert "process" not in app.query_params
    assert app.query_params["theme"] in ("dark", ["dark"])
    links = app.session_state["captured_page_links"]
    back = [link for link in links if link["page"] == PROCESS_CAPA_DETAIL.path]
    assert back[0]["query_params"] == {"process": DYNAMIC_PROCESS, "theme": "dark"}


def test_an_unknown_process_param_warns_and_opens_the_first_process(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _app(dynamic_databases)
    app.query_params["process"] = "없는_공정"
    _ok(app.run())
    warnings = " ".join(str(item.value) for item in app.warning)
    assert "넘겨받은 공정" in warnings and "없는\\_공정" in warnings
    assert (
        app.selectbox(key=CONSTRAINT_PROCESS_KEY).value
        == app.selectbox(key=CONSTRAINT_PROCESS_KEY).options[0]
    )


def test_a_process_without_equipment_stops_with_its_reason(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _opened(dynamic_databases, OTHER_PROCESS)
    assert "설비 일정 없음: 설비 없음" in " ".join(_markdown(app))
    assert not app.metric


# ------------------------------------------------------------------ 버튼 + 직접 입력


def test_the_target_buttons_and_the_typed_value_share_one_value(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _opened(dynamic_databases)
    assert app.session_state[CONSTRAINT_TARGET_KEY] == 120
    assert app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).value == 120
    assert app.number_input(key=CONSTRAINT_TARGET_INPUT_KEY).value == 120

    app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).set_value(130)
    _ok(app.run())
    assert app.session_state[CONSTRAINT_TARGET_KEY] == 130
    assert app.number_input(key=_target_input_key(app)).value == 130
    assert "제약 130%" in _header_line(app)
    assert "130% 를 맞춥니다" in _metric_caption(app, "제약 제품 확보율 충족")

    # 버튼에 없는 값을 적으면 보이는 버튼이 모두 꺼진다(숨은 맞춤 버튼이 켜진 꼴).
    app.number_input(key=_target_input_key(app)).set_value(125)
    _ok(app.run())
    assert app.session_state[CONSTRAINT_TARGET_KEY] == 125
    assert app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).value == CUSTOM_OPTION
    assert "제약 125%" in _header_line(app)

    # 켜진 버튼을 다시 누르면 프런트가 풀어 `None` 이 온다 — 값은 그대로이고 버튼은 다시 켜진다.
    app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).set_value(140)
    _ok(app.run())
    _press_lit(app, CONSTRAINT_TARGET_PILLS_KEY)
    _ok(app.run())
    assert app.session_state[CONSTRAINT_TARGET_KEY] == 140
    assert app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).value == 140


class _ReleasedButtonGroup(ButtonGroup[object]):
    """켜진 버튼을 다시 눌러 프런트가 푼 버튼 칸 — 빈 선택을 보낸다. AppTest 의 `set_value(None)` 은
    「바꾸지 않음」(세션 값을 그대로 보냄)이라 빈 선택을 싣지 못한다."""

    @property
    def _widget_state(self) -> WidgetState:
        state = WidgetState()
        state.id = self.id
        state.string_array_value.SetInParent()
        return state


def _press_lit(app: AppTest, key: str) -> None:
    """켜진 버튼 다시 누름 — 다음 `run()` 에 그 버튼 칸의 빈 선택이 간다."""
    group = app.button_group(key=key)
    assert group.value is not None
    group.__class__ = _ReleasedButtonGroup


def _target_input_key(app: AppTest) -> str:
    """제약 확보율 숫자 칸이 지금 선 key — 버튼을 누를 때마다 새 key 로 선다."""
    (key,) = _typed_field_keys(app, "제약 확보율 직접 입력")
    return key


def _typed_field_keys(app: AppTest, label: str) -> list[str]:
    return [str(field.key) for field in app.number_input if field.label == label]


def test_a_preset_button_redraws_the_typed_field_under_a_new_key(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """버튼을 누르면 숫자 칸이 새 key 로 선다 — 브라우저 칸이 쥔 범위 밖 글(301)을 버리게.

    1.63 숫자 칸은 범위 밖 글을 확정하지 않은 채 쥐고 그동안 서버가 보낸 새 값을 무시한다. 같은 key
    로는 버튼 값이 칸에 서지 않으므로 key 가 바뀌어야 한다. 숫자 칸을 직접 칠 때는 key 가 그대로다.
    """
    app = _opened(dynamic_databases)
    before = _typed_field_keys(app, "제약 확보율 직접 입력")
    assert before == [CONSTRAINT_TARGET_INPUT_KEY]

    app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).set_value(110)
    _ok(app.run())
    after = _typed_field_keys(app, "제약 확보율 직접 입력")
    assert len(after) == 1 and after != before
    assert app.number_input(key=after[0]).value == 110
    assert "제약 110%" in _header_line(app)

    app.number_input(key=after[0]).set_value(125)
    _ok(app.run())
    assert _typed_field_keys(app, "제약 확보율 직접 입력") == after
    assert app.session_state[CONSTRAINT_TARGET_KEY] == 125

    app.button_group(key=CONSTRAINT_MOD_DAYS_PILLS_KEY).set_value(90)
    _ok(app.run())
    assert _typed_field_keys(app, "개조 기간 직접 입력") != [CONSTRAINT_MOD_DAYS_INPUT_KEY]


@pytest.mark.parametrize(
    ("label", "pills_key", "value_key", "first", "typed", "pressed", "header"),
    [
        (
            "제약 확보율",
            CONSTRAINT_TARGET_PILLS_KEY,
            CONSTRAINT_TARGET_KEY,
            130,
            175,
            140,
            "제약 140%",
        ),
        (
            "기준 확보율",
            CONSTRAINT_GENERAL_PILLS_KEY,
            CONSTRAINT_GENERAL_KEY,
            100,
            112.0,
            105,
            "기준 105%",
        ),
        (
            "개조 기간",
            CONSTRAINT_MOD_DAYS_PILLS_KEY,
            CONSTRAINT_MOD_DAYS_KEY,
            60,
            50,
            45,
            "개조 45일",
        ),
    ],
)
def test_a_button_pressed_right_after_typing_wins_over_the_typed_value(
    dynamic_databases: tuple[Path, Path],
    label: str,
    pills_key: str,
    value_key: str,
    first: int,
    typed: float,
    pressed: int,
    header: str,
) -> None:
    """칸에 치고 Enter 없이 버튼을 누르면 칸 확정과 버튼 누름이 한 회차에 든다 — 마지막에 누른
    버튼이 정본이고, 버튼이 켜지고, 칸도 그 값을 보인다(2026-10-26 E2E — 친 값이 버튼을 덮었다).

    AppTest 는 바뀐 두 위젯을 한 회차로 보내고 그린 차례(버튼 → 숫자 칸)대로 콜백을 부른다 —
    브라우저에서 합쳐진 회차와 같은 차례다. 버튼을 한 번 누른 뒤의 세대 key 에서 친다.
    """
    app = _opened(dynamic_databases)
    field = f"{label} 직접 입력"
    app.button_group(key=pills_key).set_value(first)
    _ok(app.run())
    assert app.session_state[value_key] == first

    (typed_key,) = _typed_field_keys(app, field)
    app.number_input(key=typed_key).set_value(typed)
    app.button_group(key=pills_key).set_value(pressed)
    _ok(app.run())
    assert app.session_state[value_key] == pressed
    assert app.button_group(key=pills_key).value == pressed
    (shown_key,) = _typed_field_keys(app, field)
    assert shown_key != typed_key
    assert app.number_input(key=shown_key).value == pressed
    assert header in _header_line(app)

    # 대조 — 친 값만 확정하면(버튼을 누르지 않음) 친 값이 정본이고 보이는 버튼이 모두 꺼진다.
    app.number_input(key=shown_key).set_value(typed)
    _ok(app.run())
    assert app.session_state[value_key] == typed
    assert app.button_group(key=pills_key).value == CUSTOM_OPTION


@pytest.mark.parametrize(
    ("label", "pills_key", "value_key", "lit", "typed", "header"),
    [
        ("제약 확보율", CONSTRAINT_TARGET_PILLS_KEY, CONSTRAINT_TARGET_KEY, 120, 166, "제약 120%"),
        (
            "기준 확보율",
            CONSTRAINT_GENERAL_PILLS_KEY,
            CONSTRAINT_GENERAL_KEY,
            None,
            112.0,
            "기준 HOME",
        ),
        ("개조 기간", CONSTRAINT_MOD_DAYS_PILLS_KEY, CONSTRAINT_MOD_DAYS_KEY, 30, 50, "개조 30일"),
    ],
)
def test_pressing_the_lit_button_right_after_typing_keeps_the_button_value(
    dynamic_databases: tuple[Path, Path],
    label: str,
    pills_key: str,
    value_key: str,
    lit: int | None,
    typed: float,
    header: str,
) -> None:
    """칸에 치고 Enter 없이 **이미 켜진** 버튼을 눌러도 버튼이 이긴다 — 켜진 버튼 누름은 프런트가
    그 버튼을 풀어(`None`) 보내고, 콜백이 마지막으로 켠 버튼으로 되돌린다(2026-10-26 E2E —
    `required=True` 는 그 누름을 삼켜 친 166 이 적혔다). 정본·버튼·칸 모두 버튼 값이다."""
    app = _opened(dynamic_databases)
    field = f"{label} 직접 입력"
    assert app.session_state[value_key] == lit
    shown_option = "__none__" if lit is None else lit
    assert app.button_group(key=pills_key).value == shown_option

    (typed_key,) = _typed_field_keys(app, field)
    app.number_input(key=typed_key).set_value(typed)
    _press_lit(app, pills_key)
    _ok(app.run())
    assert app.session_state[value_key] == lit
    assert app.button_group(key=pills_key).value == shown_option
    (shown_key,) = _typed_field_keys(app, field)
    assert shown_key != typed_key
    assert app.number_input(key=shown_key).value != typed
    assert header in _header_line(app)


@pytest.mark.parametrize(
    ("label", "pills_key", "value_key", "lit", "typed", "header"),
    [
        ("제약 확보율", CONSTRAINT_TARGET_PILLS_KEY, CONSTRAINT_TARGET_KEY, 120, 166, "제약 120%"),
        (
            "기준 확보율",
            CONSTRAINT_GENERAL_PILLS_KEY,
            CONSTRAINT_GENERAL_KEY,
            None,
            112.0,
            "기준 HOME",
        ),
        ("개조 기간", CONSTRAINT_MOD_DAYS_PILLS_KEY, CONSTRAINT_MOD_DAYS_KEY, 30, 50, "개조 30일"),
    ],
)
def test_the_lit_button_wins_even_when_the_typed_value_ran_its_own_rerun_first(
    dynamic_databases: tuple[Path, Path],
    label: str,
    pills_key: str,
    value_key: str,
    lit: int | None,
    typed: float,
    header: str,
) -> None:
    """사람 손 빠르기로 누르면 칸 확정이 먼저 한 회차를 돌리고(정본이 친 값, 버튼은 숨은 맞춤
    버튼), 그 회차를 아직 받지 못한 브라우저는 켜진 채 보이던 버튼을 풀어 `None` 을 보낸다 — 그래도
    버튼 값이 이긴다(2026-10-26 사본 앱 — 0.15초 누름에서 친 값이 이겼다). 맞춤 값의 버튼 칸이
    `None` 이면 이 `None` 이 바뀜이 아니라 콜백이 없다."""
    app = _opened(dynamic_databases)
    field = f"{label} 직접 입력"
    (typed_key,) = _typed_field_keys(app, field)
    app.number_input(key=typed_key).set_value(typed)
    _ok(app.run())
    assert app.session_state[value_key] == typed
    assert app.button_group(key=pills_key).value == CUSTOM_OPTION

    _press_lit(app, pills_key)
    _ok(app.run())
    assert app.session_state[value_key] == lit
    assert app.button_group(key=pills_key).value == ("__none__" if lit is None else lit)
    assert header in _header_line(app)


@pytest.mark.parametrize(
    ("label", "pills_key", "value_key", "custom", "pressed", "header"),
    [
        ("제약 확보율", CONSTRAINT_TARGET_PILLS_KEY, CONSTRAINT_TARGET_KEY, 188, 130, "제약 130%"),
        (
            "기준 확보율",
            CONSTRAINT_GENERAL_PILLS_KEY,
            CONSTRAINT_GENERAL_KEY,
            112.5,
            105,
            "기준 105%",
        ),
        ("개조 기간", CONSTRAINT_MOD_DAYS_PILLS_KEY, CONSTRAINT_MOD_DAYS_KEY, 50, 45, "개조 45일"),
    ],
)
def test_a_new_typed_field_that_reaches_the_browser_without_its_value_stands_at_the_value(
    dynamic_databases: tuple[Path, Path],
    label: str,
    pills_key: str,
    value_key: str,
    custom: float,
    pressed: int,
    header: str,
) -> None:
    """켜진 버튼을 다시 누르면 숫자 칸이 새 key 로 서고, 그 key 를 처음 적은 회차가 `set_value` 로
    값을 싣는다. 그 회차가 보내기 전에 다음 누름(더블클릭의 둘째)에 끊기면 다음 회차는 같은 값이라
    적지 않아 칸이 `set_value` 없이 브라우저에 처음 닿는다 — 그때 칸의 기본값이 최소값(50)이면
    브라우저가 50 으로 세우고 다음 조작에 되보내 정본이 50 이 됐다(2026-10-27 E2E). 적지 않은
    회차의 칸은 늘 지금 값을 기본값으로 싣는다."""
    app = _opened(dynamic_databases)
    field = f"{label} 직접 입력"
    (typed_key,) = _typed_field_keys(app, field)
    app.number_input(key=typed_key).set_value(custom)
    _ok(app.run())
    app.button_group(key=pills_key).set_value(pressed)
    _ok(app.run())
    # 켜진 버튼 다시 누름 — 값은 그대로이고 숫자 칸 세대가 올라 새 key 로 선다(이 회차가 적는다).
    (before,) = _typed_field_keys(app, field)
    _press_lit(app, pills_key)
    _ok(app.run())
    (fresh,) = _typed_field_keys(app, field)
    assert fresh != before
    assert app.number_input(key=fresh).proto.set_value

    # 앞 회차의 칸이 브라우저에 닿지 못했다면 이 회차가 그 key 를 처음 싣는다 — 값을 적지 않는다.
    _ok(app.run())
    assert _typed_field_keys(app, field) == [fresh]
    shown = app.number_input(key=fresh).proto
    assert not shown.set_value
    assert shown.default == pytest.approx(pressed)
    assert app.session_state[value_key] == pressed
    assert header in _header_line(app)


def test_the_general_target_takes_half_percent_and_home(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _opened(dynamic_databases)
    assert app.session_state[CONSTRAINT_GENERAL_KEY] is None
    # HOME 일 때 숫자 칸은 HOME 기본 확보 기준(%)을 보인다.
    shown = app.number_input(key=CONSTRAINT_GENERAL_INPUT_KEY).value
    assert shown == pytest.approx(109.5)
    app.number_input(key=CONSTRAINT_GENERAL_INPUT_KEY).set_value(107.5)
    _ok(app.run())
    assert app.session_state[CONSTRAINT_GENERAL_KEY] == pytest.approx(107.5)
    assert "기준 107.5%" in _header_line(app)
    app.button_group(key=CONSTRAINT_GENERAL_PILLS_KEY).set_value("__none__")
    _ok(app.run())
    assert app.session_state[CONSTRAINT_GENERAL_KEY] is None
    assert "기준 HOME" in _header_line(app)


def test_turning_modification_off_locks_the_days_and_blanks_the_fourth_kpi(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _opened(dynamic_databases)
    assert app.toggle(key=CONSTRAINT_MODIFY_KEY).value is True
    assert _metric(app, "개조 대수") != "—"
    app.toggle(key=CONSTRAINT_MODIFY_KEY).set_value(False)
    _ok(app.run())
    assert app.number_input(key=CONSTRAINT_MOD_DAYS_INPUT_KEY).disabled
    assert app.button_group(key=CONSTRAINT_MOD_DAYS_PILLS_KEY).disabled
    assert _metric(app, "개조 대수") == "—"
    assert "개조 없음" in _header_line(app)
    assert "개조를 켜면 제약 제품에 떼어 줄 대수만큼" in _captions(app)
    app.toggle(key=CONSTRAINT_MODIFY_KEY).set_value(True)
    _ok(app.run())


def test_home_thresholds_follow_the_shared_profile_even_outside_the_input_range(
    own_databases: tuple[Path, Path],
) -> None:
    """「HOME 기준」 은 공용 판정 기준을 달마다 쓴다 — 기준을 올리면 미달 셈이 따라가고, 월별 예외가
    입력 칸 범위(50~200%) 밖이어도 예외 없이 그 달이 판정된다(명세 2-7·6-2 ⑦⑰)."""
    app = _opened(own_databases)
    assert _metric(app, "기준 미달 달 (기존 제품)") == "없음"
    repository = DuckDBScenarioRepository(own_databases[0])
    threshold = repository.load_global_securement_threshold()
    repository.replace_global_securement_threshold(
        1.095,
        1.0,
        pd.DataFrame({"생산계획년월": [202603], "확보 기준": [100_000.0], "경고 기준": [90_000.0]}),
        source="시험",
        expected_version=threshold.version,
    )
    clear_global_securement_threshold_cache()
    _ok(app.run())
    assert _metric(app, "기준 미달 달 (기존 제품)") == "1개월"
    assert "HOME(월별)" in _header_line(app)


# ------------------------------------------------------------------ 제약 기간 상자 둘


def test_the_period_boxes_follow_each_other_like_the_mock(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _opened(dynamic_databases)
    assert app.session_state[CONSTRAINT_PERIOD_START_KEY] == 202601
    assert app.session_state[CONSTRAINT_PERIOD_END_KEY] == 202612
    app.selectbox(key=CONSTRAINT_PERIOD_END_KEY).set_value(202605)
    _ok(app.run())
    # 시작을 끝 뒤로 고르면 끝이 시작으로 따라온다.
    app.selectbox(key=CONSTRAINT_PERIOD_START_KEY).set_value(202608)
    _ok(app.run())
    assert app.session_state[CONSTRAINT_PERIOD_START_KEY] == 202608
    assert app.session_state[CONSTRAINT_PERIOD_END_KEY] == 202608
    # 끝을 시작 앞으로 고르면 시작이 끝으로 따라온다.
    app.selectbox(key=CONSTRAINT_PERIOD_END_KEY).set_value(202603)
    _ok(app.run())
    assert app.session_state[CONSTRAINT_PERIOD_START_KEY] == 202603
    assert app.session_state[CONSTRAINT_PERIOD_END_KEY] == 202603
    assert "26.03 ·" in _header_line(app)


def test_the_period_boxes_keep_their_months_when_other_widgets_rerun(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """범위 슬라이더가 튜플을 잃던 함정의 되풀이 막기 — 상자 글자를 브라우저처럼 들고 다른 위젯을
    만진다."""
    app = _app(dynamic_databases)
    app.query_params["process"] = DYNAMIC_PROCESS
    start = BrowserChoice(app, "selectbox", CONSTRAINT_PERIOD_START_KEY)
    _ok(start.start())
    start.pick("26.04")
    _ok(start.run())
    assert app.session_state[CONSTRAINT_PERIOD_START_KEY] == 202604
    app.toggle(key=CONSTRAINT_PROPORTIONAL_KEY).set_value(False)
    _ok(start.run())
    app.toggle(key=CONSTRAINT_MODIFY_KEY).set_value(False)
    _ok(start.run())
    assert app.session_state[CONSTRAINT_PERIOD_START_KEY] == 202604
    assert app.session_state[CONSTRAINT_PERIOD_END_KEY] == 202612


def test_a_narrower_period_rewrites_the_constraint_months_with_a_note(
    dynamic_databases: tuple[Path, Path],
) -> None:
    app = _opened(dynamic_databases)
    app.session_state[MONTH_RANGE_KEY] = ("2026-03", "2026-06")
    _ok(app.run())
    assert app.session_state[CONSTRAINT_PERIOD_START_KEY] == 202603
    assert app.session_state[CONSTRAINT_PERIOD_END_KEY] == 202606
    assert any("제약 기간을 보이는 달로 옮겼습니다" in str(item.value) for item in app.info)
    app.session_state[MONTH_RANGE_KEY] = ("2026-01", "2026-12")
    _ok(app.run())


# ------------------------------------------------------------------ 상태 수명


def test_conditions_and_the_picked_month_survive_a_round_trip_and_get_pruned(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _opened(dynamic_databases)
    app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).set_value(110)
    app.selectbox(key=CONSTRAINT_PRODUCT_KEY).set_value("DEMO PRODUCT B")
    _ok(app.run())
    app.session_state[CONSTRAINT_MONTH_KEY] = 202604
    _ok(app.run())

    app.session_state["_test_page"] = "away"
    _ok(app.run())
    app.session_state["_test_page"] = "constraint"
    _ok(app.run())
    assert app.session_state[CONSTRAINT_TARGET_KEY] == 110
    assert app.selectbox(key=CONSTRAINT_PRODUCT_KEY).value == "DEMO PRODUCT B"
    assert app.session_state[CONSTRAINT_MONTH_KEY] == 202604
    assert any("**26.04 · " in text for text in _markdown(app))

    # 고른 제품이 선택지에서 빠지면(시나리오를 바꾼 뒤) 첫 제품으로 적는다(pop 하지 않는다).
    original = simulation_cache.get_process_product_demand

    def without_b(*args: Any, **kwargs: Any) -> pd.DataFrame:
        table = original(*args, **kwargs)
        return table.loc[table["제품정보"].ne("DEMO PRODUCT B")].reset_index(drop=True)

    monkeypatch.setattr(simulation_cache, "get_process_product_demand", without_b)
    app.run()
    assert app.selectbox(key=CONSTRAINT_PRODUCT_KEY).value == FIRST_PRODUCT
    assert app.session_state[CONSTRAINT_PRODUCT_KEY] == FIRST_PRODUCT


# ------------------------------------------------------------------ 오류 갈래


def test_a_sum_mismatch_is_a_constraint_error_not_an_equipment_error(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """어댑터 「제품별 소요 합이 공정 소요와 다릅니다」 가 「설비 일정을 계산하지 못했습니다」 로
    둔갑하지 않는다."""
    original = simulation_cache.get_process_product_demand

    def tampered(*args: Any, **kwargs: Any) -> pd.DataFrame:
        table = original(*args, **kwargs).copy()
        table.loc[table.index[0], "202603"] = float(table.loc[table.index[0], "202603"]) + 1.0
        return table

    monkeypatch.setattr(simulation_cache, "get_process_product_demand", tampered)
    app = _opened(dynamic_databases)
    errors = " ".join(str(item.value) for item in app.error)
    assert "제약 시뮬레이션을 계산하지 못했습니다 — 제품별 소요 합이 공정 소요와 다릅니다" in errors
    assert "설비 일정을 계산하지 못했습니다" not in errors


def test_a_ready_process_missing_from_the_plan_stops_with_a_reason_card(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = simulation_cache.load_required_shortening_for_target

    def without_process(*args: Any, **kwargs: Any) -> ShorteningPlan:
        plan = original(*args, **kwargs)
        return ShorteningPlan(
            months=plan.months,
            today=plan.today,
            processes=tuple(name for name in plan.processes if name != DYNAMIC_PROCESS),
            cutoff_days=plan.cutoff_days,
            levels=plan.levels,
            required_only=(*plan.required_only, DYNAMIC_PROCESS),
        )

    monkeypatch.setattr(simulation_cache, "load_required_shortening_for_target", without_process)
    app = _opened(dynamic_databases)
    assert "설비 일정 없음: 계획에 공정 없음" in " ".join(_markdown(app))
    assert not app.error
    assert not app.metric


# ------------------------------------------------------------------ 캐시 공유·쓰기 없음


def test_the_detail_page_and_this_page_share_one_plan(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """공정 Capa 상세 → 이 화면(같은 세션·같은 날): 계획 계산은 상세에서만 돈다(같은 키 —
    명세 R1)."""
    calls: list[int] = []
    original = plan_required_shortening

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(simulation_cache, "plan_required_shortening", counting)
    simulation_cache.get_required_shortening_for_target.clear()
    app = _app(dynamic_databases)
    app.session_state["_test_page"] = "detail"
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    detail_calls = len(calls)
    assert detail_calls >= 1
    # 상세 머리의 「이 공정 제약 시뮬레이션」 — 그 공정·주소 인자만, 설비 일정이 서므로 켜져 있다.
    links = app.session_state["captured_page_links"]
    constraint = [link for link in links if link["page"] == CONSTRAINT_SIMULATION.path]
    assert constraint and constraint[0]["query_params"] == {"process": DYNAMIC_PROCESS}
    assert constraint[0]["disabled"] is False

    app.session_state["_test_page"] = "constraint"
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    assert app.metric
    assert len(calls) == detail_calls


def test_the_page_writes_nothing_and_skips_the_shortening_profile_and_baselines(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _opened(dynamic_databases)
    reads: list[str] = []

    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("쓰기")

    def counting(name: str) -> Any:
        original = getattr(DuckDBEquipmentRepository, name)

        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            reads.append(name)
            return original(self, *args, **kwargs)

        return wrapper

    for repository in (DuckDBEquipmentRepository, DuckDBScenarioRepository):
        monkeypatch.setattr(repository, "_write_transaction", explode)
    for name in (
        "load_shortening_filter_profile",
        "list_shortening_baselines",
        "load_shortening_baseline",
    ):
        monkeypatch.setattr(DuckDBEquipmentRepository, name, counting(name))
    app = _opened(dynamic_databases)
    app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).set_value(130)
    _ok(app.run())
    app.toggle(key=CONSTRAINT_MODIFY_KEY).set_value(False)
    _ok(app.run())
    assert app.metric
    assert reads == []


# ------------------------------------------------------------------ 달 고르기(프래그먼트)


def _event_slots(messages: list[Any]) -> dict[int, str]:
    slots: dict[int, str] = {}
    for message in messages:
        if message.WhichOneof("type") != "delta":
            continue
        path = list(message.metadata.delta_path)
        if len(path) != 2 or path[0] != RootContainer.EVENT:
            continue
        slots[path[1]] = str(message.delta.fragment_id)
    return slots


def test_a_picked_month_reruns_only_the_view_fragment_with_the_same_event_slots(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda **_: None)
    browser = install_fragment_browser(monkeypatch)
    app = _opened(dynamic_databases)
    view = browser.fragment_keyed(CONSTRAINT_VIEW_FRAGMENT_KEY)
    full_slots = {slot for slot, owner in _event_slots(browser.messages).items() if owner == view}
    # 스타일만 든 `st.html` 넷 — 위 줄 배치 · 계산표 두 컬럼 폭 · 라벨 칸 위 여백 · 스크롤 상자.
    assert len(full_slots) == 4

    browser.fragment_queue = [view]
    app.session_state[CONSTRAINT_MONTH_KEY] = 202609
    _ok(app.run())
    assert browser.started == [[view]]
    assert set(_event_slots(browser.messages)) == full_slots
    assert any("**26.09 · " in text for text in _markdown(app))
    in_fragment = json.dumps(_chart_spec(app, CONSTRAINT_CHART_KEY)["layout"]["shapes"])

    # 비중 토글도 프래그먼트 회차다.
    browser.fragment_queue = [view]
    app.toggle(key=CONSTRAINT_PROPORTIONAL_KEY).set_value(False)
    _ok(app.run())
    assert browser.started[-1] in ([view], [])
    assert app.session_state[CONSTRAINT_PROPORTIONAL_KEY] is False

    # 같은 달·같은 토글의 앱 전체 회차 — 고른 달 띠가 같다.
    browser.fragment_queue = []
    app.toggle(key=CONSTRAINT_PROPORTIONAL_KEY).set_value(True)
    _ok(app.run())
    assert json.dumps(_chart_spec(app, CONSTRAINT_CHART_KEY)["layout"]["shapes"]) == in_fragment
    assert _has_chart(app, CONSTRAINT_SHEET_KEY)


def _pick_script() -> None:
    """두 그림 콜백을 앱 회차에서 직접 부른다(AppTest 는 Plotly 칸 누름을 못 낸다 — 공정 Capa 상세
    `pick_canvas_month` 시험과 같은 꼴). 부른 뒤 지금 세대로 두 그림을 만들어 세대를 적어 둔다."""
    from datetime import date

    import streamlit as st
    from test_constraint_simulation import _run

    from capa_simulation.components.constraint_simulation_figures import ConstraintLabels
    from capa_simulation.components.constraint_simulation_view import (
        ConstraintView,
        pick_chart_month,
        pick_sheet_month,
        remembered_figures,
    )
    from capa_simulation.constraint_simulation_state import (
        CONSTRAINT_CHART_KEY,
        CONSTRAINT_MONTH_KEY,
        CONSTRAINT_SELECT_GENERATION_KEY,
        CONSTRAINT_SHEET_KEY,
    )

    result = _run()
    months = tuple(row.month for row in result.months)
    st.session_state.setdefault(CONSTRAINT_MONTH_KEY, 202705)
    action = st.session_state.pop("action", None)
    if action == "chart":
        st.session_state[CONSTRAINT_CHART_KEY] = st.session_state.pop("selection")
        pick_chart_month(months)
    elif action == "sheet":
        st.session_state[CONSTRAINT_SHEET_KEY] = st.session_state.pop("selection")
        pick_sheet_month(months)
    generation = st.session_state.get(CONSTRAINT_SELECT_GENERATION_KEY, 0)
    view = ConstraintView(
        result=result,
        labels=ConstraintLabels("TC Bonding", "TC Bonding", "HBM라E", 120, None),
        today=date(2027, 1, 1),
    )
    chart, sheet = remembered_figures(
        view,
        month=st.session_state[CONSTRAINT_MONTH_KEY],
        show_proportional=True,
        generation=generation,
    )
    st.session_state["drawn"] = (
        chart.layout.meta["generation"],
        sheet.months.layout.meta["generation"],
    )


def _chart_pick(month: int) -> dict[str, Any]:
    return {"selection": {"points": [{"customdata": [month, "풍선"]}]}}


def _sheet_pick(month: int, row: str = "existing_rate") -> dict[str, Any]:
    return {"selection": {"points": [{"customdata": [month, row, "풍선"]}]}}


def test_the_chart_and_sheet_callbacks_write_the_month_and_bump_one_shared_generation() -> None:
    """그래프 칸·계산표 칸 콜백(D9·R-12) — 누른 칸의 달을 적고(계산표는 행과 상관없이 그 열), 두
    그림이 한 세대 칸을 함께 올려 둘 다 새 요소가 된다. 마지막 누름이 이긴다. 빈 선택(같은 칸 다시
    누름)·축 밖 점은 보던 달 그대로지만 세대는 오른다 — 두 그림의 옛 선택이 함께 비워진다."""
    app = AppTest.from_function(_pick_script, default_timeout=60).run()
    _ok(app)
    assert app.session_state[CONSTRAINT_MONTH_KEY] == 202705
    assert app.session_state["drawn"] == (0, 0)

    steps: list[tuple[str, dict[str, Any], int, int]] = [
        ("chart", _chart_pick(202709), 202709, 1),
        # 계산표는 (달, 행 id) 차례다 — 어느 행을 눌러도 그 열의 달.
        ("sheet", _sheet_pick(202712, "constrained_need"), 202712, 2),
        ("chart", _chart_pick(202801), 202801, 3),
        ("sheet", {"selection": {"points": []}}, 202801, 4),
        ("chart", _chart_pick(199001), 202801, 5),
        ("sheet", _sheet_pick(202707), 202707, 6),
    ]
    for action, selection, month, generation in steps:
        app.session_state["action"] = action
        app.session_state["selection"] = selection
        _ok(app.run())
        assert app.session_state[CONSTRAINT_MONTH_KEY] == month, (action, selection)
        assert app.session_state["constraint_sim_select_generation"] == generation
        # 어느 쪽을 눌러도 두 그림이 같은 세대로 다시 선다.
        assert app.session_state["drawn"] == (generation, generation)


def test_both_figures_wire_their_cell_clicks_to_the_month_callbacks(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """두 그림은 칸 누름(`selection_mode="points"`)을 켜고 `on_select` 가 달 콜백이다 — 위 콜백
    시험이 도는 것과 화면이 그 콜백을 거는 것을 함께 지킨다."""
    import streamlit as st

    from capa_simulation.components.constraint_simulation_view import (
        pick_chart_month,
        pick_sheet_month,
    )

    seen: dict[str, Any] = {}
    original = st.plotly_chart

    def recording(figure: Any, *args: Any, **kwargs: Any) -> Any:
        seen[str(kwargs.get("key"))] = kwargs
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(st, "plotly_chart", recording)
    _opened(dynamic_databases)
    for key, callback in (
        (CONSTRAINT_CHART_KEY, pick_chart_month),
        (CONSTRAINT_SHEET_KEY, pick_sheet_month),
    ):
        kwargs = seen[key]
        assert kwargs["selection_mode"] == "points"
        assert kwargs["on_select"].func is callback
        # 콜백이 받는 달은 화면의 달 축 그대로다(조회기간 26.01~26.12).
        assert kwargs["on_select"].args == (tuple(range(202601, 202613)),)


def test_a_product_read_error_says_so_instead_of_no_products(
    dynamic_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """제품별 소요를 읽다 실패하면 본문이 그 오류 글을 싣는다 — 「소요가 있는 제품이 없어」 안내로
    까닭을 바꾸지 않는다(카드 캡션 「제품을 읽지 못했습니다」 와 같은 까닭)."""

    def broken(*args: Any, **kwargs: Any) -> pd.DataFrame:
        raise ValueError("시험 — 제품별 소요 표를 만들지 못했습니다")

    monkeypatch.setattr(simulation_cache, "get_process_product_demand", broken)
    app = _opened(dynamic_databases)
    errors = " ".join(str(item.value) for item in app.error)
    assert "제품별 소요를 읽지 못했습니다 — 시험 — 제품별 소요 표를 만들지 못했습니다" in errors
    assert not any("소요가 있는 제품이 없어" in str(item.value) for item in app.info)
    assert "제품을 읽지 못했습니다." in _captions(app)
    assert not app.metric


def test_a_stale_process_param_does_not_overwrite_a_later_pick(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """링크로 들어와 곧바로 공정을 바꿨는데, 지운 `?process=` 가 브라우저에 닿기 전이라 옛 주소를
    실은 회차가 오면 — 그 값은 이미 적용했으므로 다시 적용하지 않는다(공정 Capa 상세의 「적용한
    묶음」 막이와 같다). 인자가 걷힌 회차가 지나면 같은 링크로 다시 들어올 때 다시 적용한다."""
    app = _opened(dynamic_databases)
    assert app.selectbox(key=CONSTRAINT_PROCESS_KEY).value == DYNAMIC_PROCESS

    app.selectbox(key=CONSTRAINT_PROCESS_KEY).set_value(OTHER_PROCESS)
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    assert app.selectbox(key=CONSTRAINT_PROCESS_KEY).value == OTHER_PROCESS
    assert "process" not in app.query_params

    # 인자 없는 회차 → 같은 링크로 다시 들어오면 그 공정이다.
    _ok(app.run())
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    assert app.selectbox(key=CONSTRAINT_PROCESS_KEY).value == DYNAMIC_PROCESS


def test_the_chart_and_steps_row_stacks_below_the_narrow_width(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """그래프 카드와 고른 달 계산 카드는 한 가로 컨테이너에 서고(3 : 2), 줄이
    `TOP_ROW_STACK_BELOW_PX` 보다 좁으면 위아래로 쌓인다 — 사이드바를 편 900px 창에서 3 : 2 그대로면
    그래프 그림 칸이 169px(달 한 칸 14px)로 줄어 칸 누름이 어려웠다(2026-10-25 리뷰). 쌓이는 폭은
    1280px 창 · 사이드바 펼침(줄 약 930px)보다 좁고 900px 창 · 사이드바 펼침(약 550px)보다 넓다."""
    from capa_simulation.components.constraint_simulation_view import (
        CHART_CARD_KEY,
        STEPS_CARD_KEY,
        TOP_ROW_KEY,
        TOP_ROW_STACK_BELOW_PX,
        top_row_style,
    )

    assert 550 < TOP_ROW_STACK_BELOW_PX < 930
    app = _opened(dynamic_databases)
    style = top_row_style(
        len(_chart_spec(app, CONSTRAINT_CHART_KEY)["layout"]["xaxis"]["tickvals"])
    )
    assert f".st-key-{TOP_ROW_KEY} {{ container: " in style
    assert f"(width < {TOP_ROW_STACK_BELOW_PX}px)" in style
    for key in (CHART_CARD_KEY, STEPS_CARD_KEY):
        assert f'[data-testid="stLayoutWrapper"]:has(> .st-key-{key})' in style
    assert any(str(element.proto.body) == style for element in app.get("html"))

    def keyed(node: Any) -> Iterator[Any]:
        if getattr(node, "key", None):
            yield node
        children = getattr(node, "children", None)
        for child in children.values() if isinstance(children, dict) else ():
            yield from keyed(child)

    (row,) = [node for node in keyed(app._tree) if node.key == TOP_ROW_KEY]
    container = row.proto.flex_container
    assert container.direction == container.HORIZONTAL and container.wrap
    assert [child.key for child in row.children.values()] == [CHART_CARD_KEY, STEPS_CARD_KEY]


def _keyed(node: Any) -> Iterator[Any]:
    if getattr(node, "key", None):
        yield node
    children = getattr(node, "children", None)
    for child in children.values() if isinstance(children, dict) else ():
        yield from _keyed(child)


def test_the_rate_chart_keeps_a_minimum_width_and_scrolls_inside_a_narrow_card(
    dynamic_databases: tuple[Path, Path],
) -> None:
    """390px 창에서 그래프 그림 칸이 199px 로 줄어 세운 달 눈금 30개(글자 폭 12px)가 6.6px 간격으로
    포개져 검은 띠가 됐다(2026-10-25 E2E). 그래프는 카드 안 스크롤 상자 → 캔버스(가장 좁은 폭
    `chart_min_width_px`) 안에 서고, 카드가 그보다 좁으면 상자가 가로로 스크롤한다. 폭은 고정하지
    않아 넓은 창에서는 카드를 채운다 — 사본 앱 1280px 창 · 사이드바 펼침의 30개월 그림(522px)은
    가장 좁은 폭보다 넓어 스크롤이 생기지 않는다."""
    from capa_simulation.components.constraint_simulation_figures import (
        MONTH_SLOT_PX,
        chart_min_width_px,
    )
    from capa_simulation.components.constraint_simulation_view import (
        CHART_CARD_KEY,
        CHART_SCROLL_PREFIX,
        top_row_style,
    )
    from capa_simulation.components.scroll_shell import min_width_scroll_rules

    # 세운 달 글자 폭(사본 앱 12px)보다 한 칸이 넓다 — 가장 좁은 폭에서도 이웃 글자와 떨어진다.
    assert MONTH_SLOT_PX > 12
    assert chart_min_width_px(30) <= 522

    app = _opened(dynamic_databases)
    spec = _chart_spec(app, CONSTRAINT_CHART_KEY)
    margin = spec["layout"]["margin"]
    count = len(spec["layout"]["xaxis"]["tickvals"])
    assert chart_min_width_px(count) == margin["l"] + margin["r"] + count * MONTH_SLOT_PX
    style = top_row_style(count)
    rules = min_width_scroll_rules(CHART_SCROLL_PREFIX, min_width_px=chart_min_width_px(count))
    assert rules in style
    assert any(str(element.proto.body) == style for element in app.get("html"))

    (card,) = [node for node in _keyed(app._tree) if node.key == CHART_CARD_KEY]
    (scroll,) = [node for node in _keyed(card) if node.key == f"{CHART_SCROLL_PREFIX}_scroll"]
    (canvas,) = [node for node in _keyed(scroll) if node.key == f"{CHART_SCROLL_PREFIX}_canvas"]
    charts = [
        node
        for node in _keyed(canvas)
        if str(getattr(getattr(node, "proto", None), "id", "")).endswith(f"-{CONSTRAINT_CHART_KEY}")
    ]
    assert len(charts) == 1
