# Purpose: 환산 「집계 기준」 의 전환 · 잠금 · 왕복과 제목 글 · CSV 이름 · 분류 칸을 고정한다.

"""환산 탭 「산출 기준 총량 | HOME 집계 기준」.

- 칸은 환산 조건 카드의 소요기준 바로 밑 segmented_control 이고 기본은 산출 기준 총량이다.
- 두 기준의 값이 같은 소요기준(PKG · Density)에서는 숨기지 않고 잠그고 까닭은 칸 풍선이다(설계
  규칙 UI-INP-07). 잠긴 동안 계산 · 제목 · CSV 이름은 늘 총량이고, 고른 값은 칸에 남는다.
- Chip · Wafer 제목 기준 글은 「단위 · 집계 기준」 이고 HOME 집계 기준일 때만 풍선(뺀 이름)이 선다.
  CSV 는 같은 표이고 HOME 집계 기준일 때만 파일 이름 꼬리 `_HOME` 이 붙는다.
- 내장 시드는 `WF 구분` 이 Core · Base 뿐이라 Dummy 계열 행을 넣은 Chip 표를 끼워 차이를 본다.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from test_load_conversion_plan_apply import (  # noqa: F401
    _fake_grids,
    _isolated_custom_renderers,
    _script,
)

import capa_simulation.services.load_calculator as load_calculator
from capa_simulation.components import table_toolbar
from capa_simulation.services import simulation_cache
from capa_simulation.services.load_calculator import (
    MONTHLY_AGGREGATION_HOME,
    MONTHLY_AGGREGATION_TOTAL,
    load_exclusions,
)
from capa_simulation.services.product_type import (
    DUMMY_SERIES_DIVISIONS_BY_PRODUCT_TYPE,
    HBM_PRODUCT_TYPE,
    PRODUCT_TYPE_COLUMN,
)

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "app_pages" / "load_conversion.py"
BASIS_KEY = "monthly_volume_basis"
AGGREGATION_KEY = "monthly_volume_aggregation"
TAB_KEY = "load_conversion_active_tab"
CONVERSION_TAB = ":material/calculate: 환산"
PLAN_TAB = ":material/edit_calendar: PKG PLAN"
DUMMY_PRODUCT = "DEMO PRODUCT A"


@pytest.fixture(scope="module")
def database(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    yield tmp_path_factory.mktemp("load_conversion_aggregation") / "scenario.duckdb"


class Seen:
    """환산 탭이 그린 것 — 월 환산 호출(집계 기준 · 소요기준 · 결과)과 표 제목 줄 인자."""

    def __init__(self) -> None:
        self.volumes: list[tuple[str, str, pd.DataFrame]] = []
        self.headings: list[dict[str, Any]] = []

    def last_volume(self) -> tuple[str, str, pd.DataFrame]:
        return self.volumes[-1]

    def last_heading(self) -> dict[str, Any]:
        return self.headings[-1]


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> Seen:
    record = Seen()
    original_volume = simulation_cache.get_monthly_volume
    original_heading = table_toolbar.render_table_heading

    def volume(**kwargs: Any) -> pd.DataFrame:
        frame = original_volume(**kwargs)
        record.volumes.append((kwargs["aggregation"], kwargs["demand_basis"], frame))
        return frame

    def heading(title: str, **kwargs: Any) -> None:
        if title == "환산":
            record.headings.append(kwargs)
        original_heading(title, **kwargs)

    monkeypatch.setattr(simulation_cache, "get_monthly_volume", volume)
    monkeypatch.setattr(table_toolbar, "render_table_heading", heading)
    return record


def _app(database: Path) -> AppTest:
    app = AppTest.from_string(_script(database), default_timeout=300).run()
    assert not list(app.exception)
    return app


def _choose(app: AppTest, *, basis: str | None = None, aggregation: str | None = None) -> None:
    """사람이 누르는 차례 그대로 — 소요기준을 바꾼 회차가 칸의 잠금을 정한 뒤 집계 기준을 누른다."""
    if basis is not None:
        app.selectbox(key=BASIS_KEY).set_value(basis).run()
        assert not list(app.exception)
    if aggregation is not None:
        app.segmented_control(key=AGGREGATION_KEY).set_value(aggregation).run()
        assert not list(app.exception)


def _with_dummy_series(app: AppTest) -> None:
    """한 제품을 HBM 으로 두고 Dummy 계열 경로(공용 목록의 이름 그대로)를 더해 끼운다 — 시드
    제품타입은 `DEMO` 라 게이트에 걸리지 않는다. Chip 구성과 수율 둘 다 `WF 구분` 이 키라 두 표에
    같은 이름 행을 함께 넣는다(원천이 그렇게 들어온 세션)."""
    names = [name for group in DUMMY_SERIES_DIVISIONS_BY_PRODUCT_TYPE.values() for name in group]
    assert names
    scenario = app.session_state["active_scenario"]
    tables = dict(scenario["tables"])
    plan = pd.DataFrame(tables["RQ_PKG_PLAN"]).copy(deep=True)  # 세션 표는 잠긴 배열이다
    plan.loc[plan["제품정보"].eq(DUMMY_PRODUCT), PRODUCT_TYPE_COLUMN] = HBM_PRODUCT_TYPE
    tables["RQ_PKG_PLAN"] = plan
    for table, column, value in (("RQ_CHIP_QTY", "구분_Chip", 1.0), ("RQ_YLD", "EDS_수율", 0.8)):
        frame = pd.DataFrame(tables[table])
        source = frame.loc[frame["제품정보"].eq(DUMMY_PRODUCT)]
        source = source.loc[source["WF 구분"].eq(source["WF 구분"].iloc[0])]
        added = []
        for name in names:
            row = source.copy()
            row["WF 구분"] = name
            row[column] = value
            added.append(row)
        tables[table] = pd.concat([frame, *added], ignore_index=True)
    app.session_state["active_scenario"] = {
        **scenario,
        "tables": tables,
        "revision": scenario["revision"] + 1,
        "content_token": "dummy-series",
    }
    app.run()
    assert not list(app.exception)


def _month_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if str(column).isdigit()]


def _file_name(heading: dict[str, Any]) -> str:
    return str(heading["file_name"])


def test_the_switch_stands_under_the_demand_basis_and_starts_locked_on_pkg(
    database: Path, seen: Seen
) -> None:
    """기본 소요기준 PKG 에서 칸은 서 있되 잠겨 있고 까닭은 칸 풍선이다. 값은 총량이다."""
    app = _app(database)
    control = app.segmented_control(key=AGGREGATION_KEY)
    assert control.value == MONTHLY_AGGREGATION_TOTAL
    assert control.proto.disabled
    assert "PKG · Density" in control.proto.help
    assert seen.last_volume()[:2] == (MONTHLY_AGGREGATION_TOTAL, "PKG")
    heading = seen.last_heading()
    assert heading["caption"] == "단위: Kea" and heading["caption_help"] is None
    assert _file_name(heading).startswith("Capa_Conversion_PKG_")

    # 소요기준 바로 밑 — 카드 안 차례는 소요기준 → 집계 기준 → 상세 · EDP 다.
    calls = [
        (node, node.func.attr)
        for node in ast.walk(ast.parse(PAGE.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    lines = {
        name: min(
            node.lineno
            for node, attr in calls
            if attr == widget
            and any(
                keyword.arg == "key" and ast.unparse(keyword.value) == name
                for keyword in node.keywords
            )
        )
        for widget, name in (
            ("selectbox", "'monthly_volume_basis'"),
            ("segmented_control", "AGGREGATION_KEY"),
            ("toggle", "'monthly_volume_detail'"),
        )
    }
    assert (
        lines["'monthly_volume_basis'"]
        < lines["AGGREGATION_KEY"]
        < lines["'monthly_volume_detail'"]
    )


def test_wafer_opens_the_switch_and_home_retitles_and_renames_the_csv(
    database: Path, seen: Seen
) -> None:
    app = _app(database)
    _choose(app, basis="Wafer")
    control = app.segmented_control(key=AGGREGATION_KEY)
    assert not control.proto.disabled
    assert "산출 기준 총량" in control.proto.help and "HOME 집계 기준" in control.proto.help
    heading = seen.last_heading()
    assert heading["caption"] == "단위: 매 · 산출 기준 총량"
    assert heading["caption_help"] is None
    total_name = _file_name(heading)
    assert total_name.startswith("Capa_Conversion_Wafer_2")

    _choose(app, aggregation=MONTHLY_AGGREGATION_HOME)
    assert seen.last_volume()[:2] == (MONTHLY_AGGREGATION_HOME, "Wafer")
    heading = seen.last_heading()
    assert heading["caption"] == "단위: 매 · HOME 집계 기준"
    for names in DUMMY_SERIES_DIVISIONS_BY_PRODUCT_TYPE.values():
        for name in names:
            assert name in heading["caption_help"]
    assert _file_name(heading) == total_name.replace(
        "Capa_Conversion_Wafer_", "Capa_Conversion_Wafer_HOME_"
    )
    # 기준 글은 화면에도 같은 글 · 같은 풍선으로 선다.
    captions = {str(item.value): str(item.proto.help) for item in app.caption}
    assert captions["단위: 매 · HOME 집계 기준"] == heading["caption_help"]

    _choose(app, basis="Chip")
    assert seen.last_volume()[:2] == (MONTHLY_AGGREGATION_HOME, "Chip")
    assert seen.last_heading()["caption"] == "단위: Kea · HOME 집계 기준"
    assert _file_name(seen.last_heading()).startswith("Capa_Conversion_Chip_HOME_")


def test_the_home_basis_drops_dummy_series_rows_and_keeps_the_exclusions(
    database: Path, seen: Seen
) -> None:
    """HOME 집계 기준은 Dummy 계열 행을 표에서 뺀다 — 빠진 계획 목록(`ST-05`)은 두 기준이 같다."""
    app = _app(database)
    _with_dummy_series(app)
    app.toggle(key="monthly_volume_detail").set_value(True)
    _choose(app, basis="Wafer")
    _, _, total = seen.last_volume()
    dummy_names = {
        name.casefold()
        for names in DUMMY_SERIES_DIVISIONS_BY_PRODUCT_TYPE.values()
        for name in names
    }
    total_divisions = {str(value).casefold() for value in total["WF 구분"]}
    assert dummy_names <= total_divisions

    _choose(app, aggregation=MONTHLY_AGGREGATION_HOME)
    _, _, home = seen.last_volume()
    assert not dummy_names & {str(value).casefold() for value in home["WF 구분"]}
    dummy_rows = total["WF 구분"].astype(str).str.casefold().isin(dummy_names)
    months = _month_columns(total)
    assert months
    assert home[months].sum().tolist() == pytest.approx(
        total.loc[~dummy_rows, months].sum().tolist()
    )
    pd.testing.assert_frame_equal(load_exclusions(total), load_exclusions(home))
    # 상세의 `WF 구분` 은 CSV 에도 공용 표시명으로 남는다 — 같은 표를 내보낸다.
    header = seen.last_heading()["csv"].decode("utf-8-sig").splitlines()[0]
    assert "속성" in header.split(",")


def test_a_locked_basis_keeps_the_choice_but_counts_and_names_as_the_total(
    database: Path, seen: Seen
) -> None:
    """Wafer 에서 HOME 집계 기준을 고른 뒤 PKG · Density 로 가면 칸은 잠긴 채 그 값을 지니고, 계산 ·
    제목 · CSV 이름은 총량이다. Wafer 로 돌아오면 다시 HOME 집계 기준이다."""
    app = _app(database)
    _choose(app, basis="Wafer", aggregation=MONTHLY_AGGREGATION_HOME)
    for basis, unit in (("PKG", "Kea"), ("Density", "억Gb")):
        _choose(app, basis=basis)
        control = app.segmented_control(key=AGGREGATION_KEY)
        assert control.proto.disabled and control.value == MONTHLY_AGGREGATION_HOME
        assert seen.last_volume()[:2] == (MONTHLY_AGGREGATION_TOTAL, basis)
        heading = seen.last_heading()
        assert heading["caption"] == f"단위: {unit}" and heading["caption_help"] is None
        assert "_HOME" not in _file_name(heading)
        assert _file_name(heading).startswith(f"Capa_Conversion_{basis}_")

    _choose(app, basis="Wafer")
    assert not app.segmented_control(key=AGGREGATION_KEY).proto.disabled
    assert seen.last_volume()[:2] == (MONTHLY_AGGREGATION_HOME, "Wafer")
    assert "_HOME_" in _file_name(seen.last_heading())


def test_the_choice_survives_a_round_trip_through_another_tab(database: Path, seen: Seen) -> None:
    """다른 탭에서는 카드가 서지 않아도 고른 기준은 남는다(`persist_state`)."""
    app = _app(database)
    _choose(app, basis="Wafer", aggregation=MONTHLY_AGGREGATION_HOME)
    app.session_state[TAB_KEY] = PLAN_TAB
    app.run()
    assert not list(app.exception)
    assert AGGREGATION_KEY not in {widget.key for widget in app.sidebar.segmented_control}

    app.session_state[TAB_KEY] = CONVERSION_TAB
    app.run()
    assert not list(app.exception)
    assert app.segmented_control(key=AGGREGATION_KEY).value == MONTHLY_AGGREGATION_HOME
    assert seen.last_volume()[:2] == (MONTHLY_AGGREGATION_HOME, "Wafer")

    _choose(app, aggregation=MONTHLY_AGGREGATION_TOTAL)
    assert seen.last_heading()["caption"] == "단위: 매 · 산출 기준 총량"
    assert "_HOME" not in _file_name(seen.last_heading())


@pytest.fixture
def _fresh_cache() -> Iterator[None]:
    """분류 상수를 바꾼 계산이 다른 시험의 캐시 칸에 남지 않게 앞뒤로 비운다."""
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def test_the_classification_columns_follow_the_calculation_constant(
    database: Path, seen: Seen, monkeypatch: pytest.MonkeyPatch, _fresh_cache: None
) -> None:
    """표 · CSV 분류 칸은 환산이 묶는 칸(`CLASSIFICATION_COLUMNS`)에서 나온다 — 계산이 분류 칸을
    더하면 화면이 저절로 따라간다(머리글은 공용 표시명)."""
    monkeypatch.setattr(
        load_calculator,
        "CLASSIFICATION_COLUMNS",
        [*load_calculator.CLASSIFICATION_COLUMNS, "Capa Code"],
    )
    app = _app(database)
    header = seen.last_heading()["csv"].decode("utf-8-sig").splitlines()[0]
    assert "PKG Code" in header.split(",")
    assert "Capa Code" in seen.last_volume()[2].columns
    assert not list(app.exception)
