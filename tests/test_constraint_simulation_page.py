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
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fragment_browser import install_fragment_browser
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.testing.v1 import AppTest
from test_required_shortening import _cutoff, _downtime, _master, _unit
from widget_browser import BrowserChoice

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.constraint_simulation_state import (
    CONSTRAINT_CHART_KEY,
    CONSTRAINT_GENERAL_INPUT_KEY,
    CONSTRAINT_GENERAL_KEY,
    CONSTRAINT_GENERAL_PILLS_KEY,
    CONSTRAINT_MOD_DAYS_INPUT_KEY,
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
    assert app.number_input(key=CONSTRAINT_TARGET_INPUT_KEY).value == 130
    assert "제약 130%" in _header_line(app)
    assert "130% 를 맞춥니다" in _metric_caption(app, "제약 제품 확보율 충족")

    # 버튼에 없는 값을 적으면 버튼이 모두 꺼진다.
    app.number_input(key=CONSTRAINT_TARGET_INPUT_KEY).set_value(125)
    _ok(app.run())
    assert app.session_state[CONSTRAINT_TARGET_KEY] == 125
    assert app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).value is None
    assert "제약 125%" in _header_line(app)

    # 같은 버튼을 다시 눌러도(`required=True`) 값이 그대로다.
    app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).set_value(140)
    _ok(app.run())
    app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).set_value(140)
    _ok(app.run())
    assert app.session_state[CONSTRAINT_TARGET_KEY] == 140
    assert app.button_group(key=CONSTRAINT_TARGET_PILLS_KEY).value == 140


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
    # 스타일만 든 `st.html` 셋 — 두 컬럼 폭 · 라벨 칸 위 여백 · 스크롤 상자.
    assert len(full_slots) == 3

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
