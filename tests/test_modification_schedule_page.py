# Purpose: 제약 시뮬레이션 화면의 「개조 일정」 모드 — 모드 전환·조건 카드·본문·대안 셋·왕복·계획
# 공유· 쓰기 없음과 그 모드 그림·글 조각을 본다.

"""「개조 일정」 모드(AppTest).

제약 시뮬레이션 화면 시험(`tests/test_constraint_simulation_page.py`)과 같은 하네스다 — 내장 시드를
임시 DuckDB 에 부트스트랩하고, 설비 DB 는 시드 공정 하나(`DEMO_Chip_Attach`)에 모든 달 설비 일정
기준 가용 12대 · Cut-off 7 을 둔다. 내장 시드는 소요가 작아 확보율이 수천 % 라 예산이 넉넉하다 —
배치 숫자는 손계산 시험(`tests/test_modification_schedule.py`)이 보고 여기서는 화면 갈래·상태·쓰기를
본다.

**오늘을 박는다.** 가장 이른 시작이 「내일」 이라 결과가 실행 날짜를 따른다 — 하네스가 페이지 글의
`today = date.today()` 한 줄을 2026-01-15 로 바꿔 돌린다(시드 달 202601~202612 안). Cut-off 7 이면
202601 W/D 는 2025-12-25~2026-01-24, 202602 는 01-25~02-21 이라 4대 × 30일은 1/16~2/14 한 차수다.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from test_constraint_simulation_page import (
    DYNAMIC_PROCESS,
    OTHER_PROCESS,
    _equipment_database,
)

import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.modification_schedule_figures import (
    ScheduleLabels,
    schedule_figure,
    shortfall_lines,
)
from capa_simulation.components.modification_schedule_view import (
    DOUBLE_COUNT_NOTE,
    FELL_BACK_LABEL,
    UNITS_HELP,
    deadline_options,
)
from capa_simulation.constraint_simulation_state import (
    CONSTRAINT_CHART_KEY,
    CONSTRAINT_GENERAL_KEY,
    CONSTRAINT_GENERAL_PILLS_KEY,
    CONSTRAINT_PROCESS_KEY,
    CONSTRAINT_PRODUCT_KEY,
)
from capa_simulation.modification_schedule_state import (
    CONSTRAINT_MODE_KEY,
    SCHEDULE_CHART_KEY,
    SCHEDULE_CONCURRENT_INPUT_KEY,
    SCHEDULE_CONCURRENT_KEY,
    SCHEDULE_CONCURRENT_PILLS_KEY,
    SCHEDULE_DAYS_KEY,
    SCHEDULE_DAYS_PILLS_KEY,
    SCHEDULE_DEADLINE_KEY,
    SCHEDULE_OBJECTIVE_KEY,
    SCHEDULE_START_KEY,
    SCHEDULE_UNITS_KEY,
)
from capa_simulation.navigation import CONSTRAINT_SIMULATION
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.modification_schedule import (
    ScheduleConditions,
    ScheduleMonthInput,
    plan_modification_schedule,
)
from capa_simulation.services.required_shortening import plan_required_shortening

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / CONSTRAINT_SIMULATION.path
TODAY = date(2026, 1, 15)
TODAY_LINE = "today = date.today()"
SCHEDULE_KPIS = ["개조 완료", "최대 동시 개조", "개조 달 최저 여유", "기한"]


def _page_script(database_path: Path, equipment_path: Path) -> str:
    """세션 `_test_page` 가 「away」 면 다른 화면(빈 글), 아니면 오늘을 박은 이 화면."""
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

settings.DUCKDB_PATH = Path({str(database_path)!r})
settings.EQUIPMENT_DUCKDB_PATH = Path({str(equipment_path)!r})
horizontal_scrollbar.render_horizontal_scrollbar = lambda *args, **kwargs: None
month_range_picker.render_month_range_apply = (
    lambda *, start, end, min_month, max_month, key: None
)
try:
    from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
    from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

    bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    apply_pending_scenario_preset()
    if st.session_state.get("_test_page", "constraint") == "away":
        st.write("다른 화면")
    else:
        source = Path({str(PAGE)!r}).read_text(encoding="utf-8")
        assert source.count({TODAY_LINE!r}) == 1, "페이지의 오늘 줄이 바뀌었다"
        source = source.replace(
            {TODAY_LINE!r}, "today = date({TODAY.year}, {TODAY.month}, {TODAY.day})"
        )
        exec(compile(source, {str(PAGE)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    settings.DUCKDB_PATH = original_database_path
    settings.EQUIPMENT_DUCKDB_PATH = original_equipment_path
    horizontal_scrollbar.render_horizontal_scrollbar = original_scrollbar
    month_range_picker.render_month_range_apply = original_month_picker
"""


@pytest.fixture(scope="module")
def databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("modification_schedule_page")
    return root / "scenario.duckdb", _equipment_database(root / "equipment.duckdb")


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [element.message for element in app.exception]
    return app


def _app(databases: tuple[Path, Path]) -> AppTest:
    return AppTest.from_string(_page_script(*databases), default_timeout=300)


def _schedule(databases: tuple[Path, Path], process: str = DYNAMIC_PROCESS) -> AppTest:
    """그 공정을 넘겨받아 열고 「개조 일정」 을 누른 회차."""
    app = _app(databases)
    app.query_params["process"] = process
    _ok(app.run())
    app.button_group(key=CONSTRAINT_MODE_KEY).set_value("schedule")
    return _ok(app.run())


def _markdown(app: AppTest) -> list[str]:
    return [str(element.value) for element in app.markdown]


def _captions(app: AppTest) -> str:
    return " ".join(str(element.value) for element in app.caption)


def _metric(app: AppTest, label: str) -> tuple[str, str]:
    for metric in app.metric:
        if metric.label == label:
            return str(metric.value), str(metric.proto.delta)
    raise AssertionError(f"{label} 지표가 없다: {[item.label for item in app.metric]}")


def _chart_keys(app: AppTest) -> list[str]:
    return [str(chart.proto.id) for chart in app.get("plotly_chart")]


def _has_chart(app: AppTest, key: str) -> bool:
    return any(chart_id.endswith(f"-{key}") for chart_id in _chart_keys(app))


def _has_widget(app: AppTest, kind: str, key: str) -> bool:
    return any(getattr(element, "key", None) == key for element in app.get(kind))


def _header(app: AppTest) -> str:
    """머리 한 줄(마크다운 escape 를 걷은 글)."""
    lines = [re.sub(r"\\(.)", r"\1", text) for text in _markdown(app) if " · 개조 " in text]
    assert len(lines) == 1, _markdown(app)
    return lines[0]


# ------------------------------------------------------------------ 모드 전환·본문


def test_the_constraint_mode_is_the_default_and_the_switch_stands_on_top(
    databases: tuple[Path, Path],
) -> None:
    app = _app(databases)
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())

    switch = app.button_group(key=CONSTRAINT_MODE_KEY)
    assert switch.value == "constraint"
    assert list(switch.options) == ["제약 영향", "개조 일정"]
    assert _has_widget(app, "selectbox", CONSTRAINT_PRODUCT_KEY)
    assert not _has_widget(app, "number_input", SCHEDULE_UNITS_KEY)


def test_the_schedule_mode_draws_its_card_kpis_figure_and_list(
    databases: tuple[Path, Path],
) -> None:
    app = _schedule(databases)

    # 카드 — 제약 제품·제약 기간 칸은 서지 않고 개조 일정 칸이 선다(공정 칸은 같은 칸).
    assert app.selectbox(key=CONSTRAINT_PROCESS_KEY).value == DYNAMIC_PROCESS
    assert not _has_widget(app, "selectbox", CONSTRAINT_PRODUCT_KEY)
    assert app.number_input(key=SCHEDULE_UNITS_KEY).value == 4
    assert app.session_state[SCHEDULE_DAYS_KEY] == 30
    assert app.button_group(key=SCHEDULE_CONCURRENT_PILLS_KEY).value == "__none__"
    assert app.selectbox(key=SCHEDULE_START_KEY).value == 0
    assert app.selectbox(key=SCHEDULE_DEADLINE_KEY).value == 0
    objective = app.button_group(key=SCHEDULE_OBJECTIVE_KEY)
    assert objective.value == "earliest" and objective.disabled

    # 본문 — 요약 넷 · 그래프 · 차수 한 줄(1/16 ~ 2/14 · 4대 — 1월 W/D 9일 · 2월 W/D 21일).
    assert [metric.label for metric in app.metric] == SCHEDULE_KPIS
    assert _metric(app, "개조 완료") == ("2026-02-14", "26.02 W/D 안 · 1차수")
    assert _metric(app, "최대 동시 개조") == ("4대", "상한 없음")
    assert _metric(app, "기한")[0] == "없음"
    assert _has_chart(app, SCHEDULE_CHART_KEY)
    assert not _has_chart(app, CONSTRAINT_CHART_KEY)
    assert "**개조 일정**" in _markdown(app)
    assert "**1** · 2026-01-16 \\~ 2026-02-14 · **4대** · 26.01 9일 · 26.02 21일" in _markdown(app)
    header = _header(app)
    assert "개조 4대 × 30일" in header and "가장 빨리" in header and "동시 상한 없음" in header
    captions = _captions(app)
    assert DOUBLE_COUNT_NOTE in captions
    assert "저장하지 않는 시뮬레이션입니다" in captions
    assert "공정 소요 · 가용 = 설비 일정 기준" in captions
    assert "Cut-off 7일" in captions
    assert "**다 넣지 못했습니다 — 대안**" not in _markdown(app)


def test_the_figure_draws_one_bar_per_batch_on_the_wd_coordinate(
    databases: tuple[Path, Path],
) -> None:
    app = _schedule(databases)
    chart = next(
        item for item in app.get("plotly_chart") if str(item.proto.id).endswith(SCHEDULE_CHART_KEY)
    )
    spec = json.loads(chart.proto.spec)
    bars = [trace for trace in spec["data"] if trace.get("orientation") == "h"]
    assert len(bars) == 1
    assert bars[0]["text"] == ["4대"]
    # 1/16 은 202601 W/D(12/25~1/24, 31일)의 23번째 날 — x = 0 − 0.5 + 22/31.
    assert bars[0]["base"][0] == pytest.approx(-0.5 + 22 / 31)
    names = [trace.get("name") for trace in spec["data"]]
    assert "개조 전" in names and "개조 뒤" in names


def test_a_deadline_that_cannot_hold_the_window_reports_the_alternatives(
    databases: tuple[Path, Path],
) -> None:
    """기한 「26.02 W/D 첫날 전」 = 1/24 — 1/16 부터 9일뿐이라 30일 개조는 한 대도 못 넣는다.

    대안 셋째 줄은 원인을 가용이 아니라 짧은 창으로 짚는다.
    """
    app = _schedule(databases)
    app.selectbox(key=SCHEDULE_DEADLINE_KEY).set_value(202602)
    _ok(app.run())

    assert _metric(app, "개조 완료") == ("0 / 4대", "기한까지 넣을 수 있는 대수")
    assert _metric(app, "기한")[0] == "못 맞춤"
    markdown = " ".join(_markdown(app))
    assert "**다 넣지 못했습니다 — 대안**" in markdown
    assert "기한(2026-01-24)까지 넣을 수 있는 대수: **0 / 4대**" in markdown
    assert "기한 없이 기준을 지키면 끝나는 날: **2026-02-14** (26.02 W/D)" in markdown
    assert (
        "넣을 수 있는 첫날(2026-01-16) \\~ 기한(2026-01-24)이 9일로 개조 기간 30일보다 짧습니다"
        in markdown
    )
    assert "기준을 0% 까지 낮춰도" not in markdown
    assert "넣을 수 있는 차수가 없습니다." in _captions(app)


def test_the_deadline_offers_only_months_after_the_chosen_start(
    databases: tuple[Path, Path],
) -> None:
    """시작 「26.03 W/D 첫날(02-22)부터」 면 기한은 26.04 부터다 — 고른 기한이 시작보다 앞이 되면
    「없음」 으로 돌아간다."""
    app = _schedule(databases)
    app.selectbox(key=SCHEDULE_DEADLINE_KEY).set_value(202603)
    _ok(app.run())
    app.selectbox(key=SCHEDULE_START_KEY).set_value(202603)
    _ok(app.run())

    options = app.selectbox(key=SCHEDULE_DEADLINE_KEY).options
    assert options[0].startswith("없음") and options[1].startswith("26.04 ")
    assert app.session_state[SCHEDULE_DEADLINE_KEY] == 0


def test_deadline_options_follow_the_start() -> None:
    months = [202601, 202602, 202603, 202604]
    assert deadline_options(months, cutoff_days=7, today=TODAY) == [0, 202602, 202603, 202604]
    assert deadline_options(months, cutoff_days=7, today=TODAY, start_month=202603) == [0, 202604]
    assert deadline_options(months, cutoff_days=None, today=TODAY, start_month=202603) == [
        0,
        *months,
    ]


def _points(text: str) -> float:
    """「+94,821.1%p」 꼴 글자에서 %p 수 하나."""
    found = re.search(r"([+\u2212-]?[\d,]+\.\d)%p", text)
    assert found is not None, text
    return float(found.group(1).replace(",", "").replace("\u2212", "-"))


def test_the_even_objective_opens_only_with_a_deadline(databases: tuple[Path, Path]) -> None:
    """「가장 고르게」 는 기한이 있어야 열리고, 열리면 「가장 빨리」 보다 최저 여유가 크다 — 여유가
    큰 공정(내장 시드 확보율 수천 %)에서도 고정 위 끝(+100%p)에 멈추지 않는다."""
    app = _schedule(databases)
    app.selectbox(key=SCHEDULE_DEADLINE_KEY).set_value(202606)
    _ok(app.run())
    earliest_margin = _points(_metric(app, "개조 달 최저 여유")[0])
    objective = app.button_group(key=SCHEDULE_OBJECTIVE_KEY)
    assert not objective.disabled
    objective.set_value("even")
    _ok(app.run())

    value, caption = _metric(app, "기한")
    assert value == "맞춤" and "가장 고르게 기준 +" in caption
    applied = _points(caption)
    even_margin = _points(_metric(app, "개조 달 최저 여유")[0])
    assert applied > 100.0
    assert even_margin > earliest_margin
    assert even_margin == pytest.approx(applied, abs=0.05)
    assert "가장 고르게" in _header(app)

    # 기한을 걷으면 「가장 빨리」 로 적고 잠근다.
    app.selectbox(key=SCHEDULE_DEADLINE_KEY).set_value(0)
    _ok(app.run())
    assert app.session_state[SCHEDULE_OBJECTIVE_KEY] == "earliest"
    assert app.button_group(key=SCHEDULE_OBJECTIVE_KEY).disabled


def test_an_even_run_that_misses_the_deadline_says_it_placed_the_earliest_way(
    databases: tuple[Path, Path],
) -> None:
    """「가장 고르게」 인데 여유만으로도 기한을 못 맞추면 「가장 빨리」 로 놓았다고 머리·기한 칸이
    적는다."""
    app = _schedule(databases)
    app.selectbox(key=SCHEDULE_DEADLINE_KEY).set_value(202602)
    _ok(app.run())
    app.button_group(key=SCHEDULE_OBJECTIVE_KEY).set_value("even")
    _ok(app.run())

    assert FELL_BACK_LABEL in _header(app)
    value, caption = _metric(app, "기한")
    assert value == "못 맞춤" and "가장 빨리로 배치" in caption


def test_the_tightest_margin_kpi_reads_the_margin_first(databases: tuple[Path, Path]) -> None:
    """요약 셋째 칸은 기준 대비 여유(%p)가 값이고 그 달 확보율이 캡션이다 — HOME 기준 109.5% 에
    딱 붙은 「가장 빨리」 결과가 「기준 110%」 옆에서 미달처럼 읽히지 않게."""
    app = _schedule(databases)
    value, caption = _metric(app, "개조 달 최저 여유")
    assert value.startswith("+") and value.endswith("%p")
    assert " · 확보율 " in caption


# ------------------------------------------------------------------ 상태


def test_typing_the_shown_concurrency_value_keeps_the_cap(databases: tuple[Path, Path]) -> None:
    """동시 상한 「없음」 이면 칸이 빈다 — 4를 치면 상한 4대가 정본이 되고, 대수를 늘려도 그대로다
    (칸이 개조 대수를 보이던 때는 같은 값을 쳐도 콜백이 돌지 않아 상한이 조용히 사라졌다)."""
    app = _schedule(databases)
    assert app.number_input(key=SCHEDULE_CONCURRENT_INPUT_KEY).value is None
    app.number_input(key=SCHEDULE_CONCURRENT_INPUT_KEY).set_value(4)
    _ok(app.run())
    assert app.session_state[SCHEDULE_CONCURRENT_KEY] == 4
    app.number_input(key=SCHEDULE_UNITS_KEY).set_value(10)
    _ok(app.run())

    assert _metric(app, "최대 동시 개조")[1] == "상한 4대"
    assert "동시 4대까지" in _header(app)


def test_the_units_help_says_which_units_to_count(databases: tuple[Path, Path]) -> None:
    app = _schedule(databases)
    help_text = str(app.number_input(key=SCHEDULE_UNITS_KEY).help)
    assert help_text == UNITS_HELP
    assert "아직 개조하지 않은" in help_text and "개조된 채 들어오는 신규" in help_text


def test_schedule_conditions_and_the_mode_survive_a_round_trip(
    databases: tuple[Path, Path],
) -> None:
    app = _schedule(databases)
    app.number_input(key=SCHEDULE_UNITS_KEY).set_value(6)
    _ok(app.run())
    app.button_group(key=SCHEDULE_DAYS_PILLS_KEY).set_value(45)
    _ok(app.run())

    app.session_state["_test_page"] = "away"
    _ok(app.run())
    app.session_state["_test_page"] = "constraint"
    _ok(app.run())

    assert app.button_group(key=CONSTRAINT_MODE_KEY).value == "schedule"
    assert app.number_input(key=SCHEDULE_UNITS_KEY).value == 6
    assert app.session_state[SCHEDULE_DAYS_KEY] == 45
    assert "개조 6대 × 45일" in _header(app)


def test_the_general_target_is_one_value_for_both_modes(databases: tuple[Path, Path]) -> None:
    app = _app(databases)
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    app.button_group(key=CONSTRAINT_GENERAL_PILLS_KEY).set_value(105)
    _ok(app.run())
    app.button_group(key=CONSTRAINT_MODE_KEY).set_value("schedule")
    _ok(app.run())

    assert app.session_state[CONSTRAINT_GENERAL_KEY] == 105
    assert app.button_group(key=CONSTRAINT_GENERAL_PILLS_KEY).value == 105
    assert "기준 105%" in _header(app)

    app.button_group(key=CONSTRAINT_MODE_KEY).set_value("constraint")
    _ok(app.run())
    assert _has_widget(app, "selectbox", CONSTRAINT_PRODUCT_KEY)
    assert "제약 제품 확보율 충족" in [metric.label for metric in app.metric]


# ------------------------------------------------------------------ 갈래


def test_a_process_without_equipment_stops_with_its_reason(databases: tuple[Path, Path]) -> None:
    app = _schedule(databases, OTHER_PROCESS)

    assert "설비 일정 없음: 설비 없음" in " ".join(_markdown(app))
    assert not app.metric
    assert app.number_input(key=SCHEDULE_UNITS_KEY).value == 4


def test_a_service_error_is_a_schedule_error_not_an_equipment_error(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import capa_simulation.components.modification_schedule_view as view

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("설비 일정 기준 계획에 202601 공정 「X」 행이 없습니다.")

    monkeypatch.setattr(view, "schedule_month_inputs", broken)
    app = _schedule(databases)
    errors = " ".join(str(item.value) for item in app.error)
    assert "개조 일정을 찾지 못했습니다 — 설비 일정 기준 계획에 202601" in errors
    assert "설비 일정을 계산하지 못했습니다" not in errors
    assert not app.metric


# ------------------------------------------------------------------ 계획 공유·쓰기 없음


def test_both_modes_share_one_plan_and_the_schedule_mode_writes_nothing(
    databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    original = plan_required_shortening

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(simulation_cache, "plan_required_shortening", counting)
    simulation_cache.get_required_shortening_for_target.clear()
    app = _app(databases)
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    constraint_calls = len(calls)
    assert constraint_calls >= 1

    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("쓰기")

    for repository in (DuckDBEquipmentRepository, DuckDBScenarioRepository):
        monkeypatch.setattr(repository, "_write_transaction", explode)
    app.button_group(key=CONSTRAINT_MODE_KEY).set_value("schedule")
    _ok(app.run())
    app.number_input(key=SCHEDULE_UNITS_KEY).set_value(2)
    _ok(app.run())
    assert app.metric
    assert len(calls) == constraint_calls


# ------------------------------------------------------------------ 그림·글 조각(순수)


def _blocked_by_margin() -> Any:
    """기준 110% · 여유 3%p · 1월 개조 전 111% — 기준은 넘지만 배치 기준(113%)에는 못 미친다."""
    months = [
        ScheduleMonthInput(202701, 10.0, 11.1, 1.1),
        ScheduleMonthInput(202702, 10.0, 14.0, 1.1),
    ]
    return plan_modification_schedule(
        months,
        ScheduleConditions(units=1, days=10, cutoff_days=0, earliest=date(2027, 1, 1), margin=0.03),
    )


def test_the_month_hover_names_the_placement_threshold_when_a_margin_is_set() -> None:
    result = _blocked_by_margin()
    assert result.month(202701).blocked and result.month(202701).secure_after
    figure = schedule_figure(result, ScheduleLabels(process_label="P", general_percent=110.0))
    hovers = [row[1] for row in figure.data[0].customdata]

    assert "개조 없이도 배치 기준(기준 +3.0%p) 미달 — 넣지 않음" in hovers[0]
    assert "개조 없이도 기준 미달" not in hovers[0]


def test_shortfall_lines_name_the_concurrency_cap_and_an_unfinished_search() -> None:
    months = [ScheduleMonthInput(month, 10.0, 20.0, 1.0) for month in (202701, 202702, 202703)]
    capped = plan_modification_schedule(
        months,
        ScheduleConditions(
            units=10, days=30, cutoff_days=0, earliest=date(2027, 1, 1), concurrent=1
        ),
    )
    lines = " ".join(shortfall_lines(capped))
    assert "동시 개조 상한 1대가 막습니다" in lines
    assert "이 계산으로 찾은 범위" not in lines
