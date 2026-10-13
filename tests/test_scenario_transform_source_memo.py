# Purpose: 파생 시나리오 원본 메모의 미리보기 동일성과 원본·이름·모드 변경 때 다시 읽기를 검증한다.

"""파생 시나리오 화면의 원본 메모(`scenario_transform.SOURCE_MEMO_KEY`) 회귀 검사.

원본 리비전을 고른 뒤 조작마다 cache_data 피클을 다시 풀던 것을, 원본을 바꿀 때만 읽게 했다. 메모한
원본으로 그린 미리보기는 저장소에서 새로 읽은 원본으로 만든 것과 같아야 하고(같은 숫자), 다른
리비전을 고르거나 다른 세션이 이름을 바꾸면 다시 읽어야 하며(무효화), 모드·페이지를 떠나면 버려야
한다(메모리).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.components.scenario_transform import SOURCE_MEMO_KEY, month_table_summary
from capa_simulation.persistence.cache import clear_scenario_snapshot_cache
from capa_simulation.persistence.models import ScenarioPreset, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.scenario_month_merge import merge_scenario_months
from capa_simulation.services.scenario_transform import MONTHLY_TABLES, copy_scenario_tables
from capa_simulation.services.scenario_year_shift import shift_scenario_years

Stores = tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot, ScenarioSnapshot]


def _monthly_tables(months: list[int]) -> dict[str, pd.DataFrame]:
    tables = _reference_tables()
    for name in MONTHLY_TABLES:
        tables[name] = pd.concat(
            [tables[name].assign(생산계획년월=month) for month in months], ignore_index=True
        )
    return tables


@pytest.fixture
def stores(tmp_path: Path) -> Stores:
    database = tmp_path / "transform-memo.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    first_tables = _monthly_tables([202701, 202712])
    second_tables = _monthly_tables([202801, 202802, 202803])
    first = repository.create_scenario(
        _metadata("원본 2027"), first_tables, ScenarioPreset(202701, 202712, ("Process-A",))
    )
    second = repository.create_scenario(
        _metadata("원본 2028"), second_tables, ScenarioPreset(202801, 202803, ("Process-A",))
    )
    repository.initialize_global_display_order(first_tables["RQ_DISPLAY_ORDER"])
    return repository, database, first, second


# 원본을 저장소에서 읽은 횟수를 세션에 적는다. 화면 모듈은 `load_scenario_snapshot` 을 모듈 속성으로
# 부르므로 그 속성을 갈아끼우면 센다.
_COUNTED = """
import streamlit as st

import capa_simulation.components.scenario_transform as _transform

_original_load = _transform.load_scenario_snapshot


def _counted_load(database_path, revision_id, **kwargs):
    st.session_state.setdefault("test_source_loads", []).append(revision_id)
    return _original_load(database_path, revision_id, **kwargs)


_transform.load_scenario_snapshot = _counted_load
try:
{body}
finally:
    _transform.load_scenario_snapshot = _original_load
"""


def _script(database: Path, body: str) -> str:
    lines = [
        "from capa_simulation.persistence.cache import get_scenario_repository",
        f"database_path = {str(database)!r}",
        "repository = get_scenario_repository(database_path)",
        *body.strip().splitlines(),
    ]
    return _COUNTED.format(body="\n".join(f"    {line}" for line in lines))


SHIFT_BODY = """
from capa_simulation.components.scenario_year_shift import render_scenario_year_shift
render_scenario_year_shift(repository, database_path)
"""
MERGE_BODY = """
from capa_simulation.components.scenario_month_merge import render_scenario_month_merge
render_scenario_month_merge(repository, database_path)
"""
MODE_BODY = """
from capa_simulation.components.scenario_management import render_scenario_management
from capa_simulation.page_bootstrap import forget_page_dialogs
if st.session_state.get("test_leave_page"):
    forget_page_dialogs()
render_scenario_management(repository, database_path)
"""


def _loads(app: AppTest) -> list[str]:
    key = "test_source_loads"
    return list(app.session_state[key]) if key in app.session_state else []


def _table_with(app: AppTest, column: str) -> pd.DataFrame:
    for element in app.dataframe:
        if column in element.value.columns:
            frame: pd.DataFrame = element.value
            return frame.reset_index(drop=True)
    raise AssertionError(f"`{column}` 표가 없습니다.")


def _provenance(app: AppTest) -> str:
    return next(
        str(item.value)
        for item in app.text
        if "원본:" in str(item.value) or "베이스:" in str(item.value)
    )


def _fresh_tables(
    repository: DuckDBScenarioRepository, snapshot: ScenarioSnapshot
) -> dict[str, pd.DataFrame]:
    """저장소에서 **새로** 읽은 원본(공용 표시순서 미적용)의 검증 사본 — 메모 없던 때의 재료."""
    fresh = repository.load_revision(
        snapshot.revision.revision_id, apply_global_display_order=False
    )
    return copy_scenario_tables(fresh.tables)


def test_a_chosen_shift_source_is_read_once_and_previews_like_a_fresh_read(stores: Stores) -> None:
    repository, database, first, _second = stores
    app = AppTest.from_string(_script(database, SHIFT_BODY), default_timeout=60).run()
    app.selectbox(key="shift_source_scenario").set_value(first.scenario.scenario_id).run()
    assert not app.exception
    assert _loads(app) == [first.revision.revision_id]

    for years in (1, -2, 1):
        app.number_input(key="scenario_shift_years").set_value(years).run()
        assert not app.exception
        original = _fresh_tables(repository, first)
        expected = month_table_summary(original, label="이동 전").merge(
            month_table_summary(shift_scenario_years(original, years), label="이동 후"),
            on="표",
            validate="one_to_one",
        )
        pd.testing.assert_frame_equal(
            _table_with(app, "이동 후 월 범위"), expected, check_dtype=False
        )
    app.run()
    # 원본을 고른 뒤 조작·재실행이 여러 번이어도 한 번만 읽었다.
    assert _loads(app) == [first.revision.revision_id]


def test_choosing_another_source_reads_it(stores: Stores) -> None:
    _repository, database, first, second = stores
    app = AppTest.from_string(_script(database, SHIFT_BODY), default_timeout=60).run()
    app.selectbox(key="shift_source_scenario").set_value(first.scenario.scenario_id).run()
    app.selectbox(key="shift_source_scenario").set_value(second.scenario.scenario_id).run()
    assert not app.exception
    assert _loads(app) == [first.revision.revision_id, second.revision.revision_id]
    assert {item.label: item.value for item in app.metric}["이동 전 월 범위"] == "2028-01 ~ 2028-03"
    # 상자를 비우면 그 역할의 원본을 버린다.
    app.selectbox(key="shift_source_scenario").set_value(None).run()
    assert SOURCE_MEMO_KEY not in app.session_state


def test_a_rename_elsewhere_rereads_the_source(stores: Stores) -> None:
    """다른 세션이 이름을 바꾸면(요약이 달라진다) 다시 읽어 저장될 출처 메모가 새 이름이다."""
    repository, database, first, _second = stores
    app = AppTest.from_string(_script(database, SHIFT_BODY), default_timeout=60).run()
    app.selectbox(key="shift_source_scenario").set_value(first.scenario.scenario_id).run()
    app.number_input(key="scenario_shift_years").set_value(1).run()
    assert "원본 2027" in _provenance(app)

    repository.rename_scenario(first.scenario.scenario_id, "새 이름 2027")
    clear_scenario_snapshot_cache()
    app.run()
    assert not app.exception
    assert _loads(app) == [first.revision.revision_id, first.revision.revision_id]
    assert "새 이름 2027" in _provenance(app)


def test_merge_reads_each_source_once_and_previews_like_a_fresh_read(stores: Stores) -> None:
    repository, database, first, second = stores
    app = AppTest.from_string(_script(database, MERGE_BODY), default_timeout=60).run()
    app.selectbox(key="merge_base_scenario").set_value(first.scenario.scenario_id).run()
    app.selectbox(key="merge_donor_scenario").set_value(second.scenario.scenario_id).run()
    assert not app.exception
    start = next(w for w in app.selectbox if w.key and w.key.startswith("merge_start_"))
    start.set_value(202802).run()
    app.run()
    assert not app.exception
    assert sorted(_loads(app)) == sorted([first.revision.revision_id, second.revision.revision_id])

    base_tables = _fresh_tables(repository, first)
    result = merge_scenario_months(base_tables, _fresh_tables(repository, second), 202802, 202803)
    expected = month_table_summary(base_tables, label="베이스").merge(
        month_table_summary(result, label="결과"), on="표", validate="one_to_one"
    )
    expected["행 수 증감"] = expected["결과 행 수"] - expected["베이스 행 수"]
    pd.testing.assert_frame_equal(_table_with(app, "행 수 증감"), expected, check_dtype=False)


def test_leaving_the_mode_or_the_page_drops_the_sources(tmp_path: Path, stores: Stores) -> None:
    _repository, database, first, _second = stores
    app = AppTest.from_string(_script(database, MODE_BODY), default_timeout=60).run()
    app.session_state["scenario_page_mode"] = "연도 Shift"
    app.run()
    app.selectbox(key="shift_source_scenario").set_value(first.scenario.scenario_id).run()
    assert not app.exception
    assert SOURCE_MEMO_KEY in app.session_state

    app.session_state["scenario_page_mode"] = "목록 관리"
    app.run()
    assert SOURCE_MEMO_KEY not in app.session_state

    app.session_state["scenario_page_mode"] = "연도 Shift"
    app.run()
    assert SOURCE_MEMO_KEY in app.session_state
    # 다른 페이지로 가는 회차에 `app.py` 가 부르는 정리가 메모를 버린다.
    app.session_state["test_leave_page"] = True
    app.session_state["scenario_page_mode"] = "목록 관리"
    app.run()
    assert SOURCE_MEMO_KEY not in app.session_state
