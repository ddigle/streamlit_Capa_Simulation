# Purpose: 파생 시나리오 원본 메모의 미리보기 동일성과 원본·요약·모드·페이지가 바뀔 때 처리를 본다.

"""파생 시나리오 화면의 원본 메모(`scenario_transform.SOURCE_MEMO_KEY`) 회귀 검사.

원본 리비전은 원본을 바꿀 때만 읽는다. 메모한 원본으로 그린 미리보기는 저장소에서 새로 읽은 원본으로
만든 것과 같아야 하고(같은 숫자), 다른 리비전을 고르거나 목록 요약(이름·활성 리비전)이 바뀌면 다시
읽되 그 뒤로는 다시 쓰며(무효화), 출처 메모는 늘 그 회차 목록의 요약을 싣고, 모드·페이지를 떠나면
버려야 한다(메모리).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_app_navigation import _app  # noqa: F401 — 아래 앱 전체 테스트의 픽스처
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.components.scenario_transform import SOURCE_MEMO_KEY, month_table_summary
from capa_simulation.navigation import CAPA_CHATBOT, SCENARIO_MANAGEMENT
from capa_simulation.persistence.cache import clear_scenario_snapshot_cache
from capa_simulation.persistence.models import ScenarioPreset, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import ACTIVE_PERSISTED_SCENARIO_ID_KEY
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
# `test_on_another_page` 회차는 다른 페이지에 있는 회차다 — 페이지가 바뀐 회차에 `app.py` 가 부르는
# 정리(`forget_page_dialogs`)만 돌고 이 화면은 그리지 않는다. 모드는 건드리지 않으므로 모드 전환의
# 정리(`forget_derived_sources`)가 대신 지우는 일이 없다.
MODE_BODY = """
from capa_simulation.components.scenario_management import render_scenario_management
from capa_simulation.page_bootstrap import forget_page_dialogs
if st.session_state.get("test_on_another_page"):
    forget_page_dialogs()
    st.stop()
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


def test_leaving_the_mode_drops_the_sources(stores: Stores) -> None:
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
    assert _loads(app) == [first.revision.revision_id, first.revision.revision_id]


def test_leaving_the_page_drops_the_sources_and_coming_back_rereads(stores: Stores) -> None:
    """모드를 「연도 Shift」로 둔 채 다른 페이지로 가면 페이지 정리가 메모를 버린다."""
    _repository, database, first, _second = stores
    app = AppTest.from_string(_script(database, MODE_BODY), default_timeout=60).run()
    app.session_state["scenario_page_mode"] = "연도 Shift"
    app.run()
    app.selectbox(key="shift_source_scenario").set_value(first.scenario.scenario_id).run()
    assert not app.exception
    assert SOURCE_MEMO_KEY in app.session_state

    app.session_state["test_on_another_page"] = True
    app.run()
    assert not app.exception
    assert app.session_state["scenario_page_mode"] == "연도 Shift"
    assert SOURCE_MEMO_KEY not in app.session_state

    # 돌아오면 고른 원본을 한 번 다시 읽고, 미리보기는 그 원본으로 그린다.
    app.session_state["test_on_another_page"] = False
    app.run()
    assert not app.exception
    assert SOURCE_MEMO_KEY in app.session_state
    assert _loads(app) == [first.revision.revision_id, first.revision.revision_id]
    assert {item.label: item.value for item in app.metric}["이동 전 월 범위"] == "2027-01 ~ 2027-12"


def test_a_new_revision_saved_elsewhere_rereads_once_then_reuses(stores: Stores) -> None:
    """다른 세션이 원본 시나리오에 새 리비전을 저장해도(프로세스 캐시는 그대로) 한 번만 다시 읽는다.

    새 리비전 저장은 프로세스 캐시를 비우지 않아 캐시의 시나리오 요약이 옛것으로 남는다. 메모를 그
    요약으로 견주면 옛 리비전을 고른 동안 회차마다 다시 읽는다.
    """
    repository, database, first, _second = stores
    app = AppTest.from_string(_script(database, SHIFT_BODY), default_timeout=60).run()
    app.selectbox(key="shift_source_scenario").set_value(first.scenario.scenario_id).run()
    revision_key = f"shift_source_revision_{first.scenario.scenario_id}"
    assert app.selectbox(key=revision_key).value == first.revision.revision_id
    assert _loads(app) == [first.revision.revision_id]

    newer = repository.save_revision(
        first.scenario.scenario_id,
        _monthly_tables([202701, 202702]),
        ScenarioPreset(202701, 202702, ("Process-A",)),
        revision_name="r2",
        parent_revision_id=first.revision.revision_id,
    )
    assert newer.scenario.active_revision_id != first.scenario.active_revision_id
    app.run()
    assert not app.exception
    # 상자는 고른 옛 리비전을 그대로 든다. 목록 요약이 바뀌어 한 번 다시 읽는다.
    assert app.selectbox(key=revision_key).value == first.revision.revision_id
    assert _loads(app) == [first.revision.revision_id] * 2

    for years in (1, 2, 3):
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
    assert _loads(app) == [first.revision.revision_id] * 2


def test_the_provenance_names_this_runs_summary_even_with_a_stale_process_cache(
    stores: Stores,
) -> None:
    """프로세스 캐시를 비우지 않은 이름 변경도 출처 메모는 새 이름이고, 다시 읽는 것은 한 번이다."""
    repository, database, first, _second = stores
    app = AppTest.from_string(_script(database, SHIFT_BODY), default_timeout=60).run()
    app.selectbox(key="shift_source_scenario").set_value(first.scenario.scenario_id).run()
    app.number_input(key="scenario_shift_years").set_value(1).run()
    assert "원본 2027" in _provenance(app)

    repository.rename_scenario(first.scenario.scenario_id, "새 이름 2027")
    app.run()
    assert not app.exception
    assert "새 이름 2027" in _provenance(app)
    assert "원본 2027" not in _provenance(app)
    app.number_input(key="scenario_shift_years").set_value(2).run()
    assert "새 이름 2027" in _provenance(app)
    assert _loads(app) == [first.revision.revision_id] * 2


def test_a_rename_in_another_session_keeps_the_chosen_source(stores: Stores) -> None:
    """다른 세션이 원본 시나리오의 이름을 바꿔도 고른 원본·리비전 상자가 그대로 남는다.

    원본 상자의 글자는 시나리오 이름이다. 위젯 앞에서 고른 값을 다시 적지 않으면 브라우저가 옛
    이름을 되보내고, 서버는 선택지 밖 글자로 읽어 상자를 빈 선택으로 되돌린다 — 리비전 상자가
    사라지고 준비하던 월 머지 원본이 알림 없이 풀린다. 일반 `AppTest.run()` 은 글자를 새로
    만들어 보지 못해 `BrowserChoice` 로 잰다.
    """
    from widget_browser import BrowserChoice

    repository, database, first, _second = stores
    scenario_id = first.scenario.scenario_id
    app = AppTest.from_string(_script(database, MERGE_BODY), default_timeout=60)
    browser = BrowserChoice(app, "selectbox", "merge_base_scenario")
    browser.start()
    browser.pick("원본 2027")
    browser.run()
    assert not app.exception
    assert app.selectbox(key="merge_base_scenario").value == scenario_id

    repository.rename_scenario(scenario_id, "새 이름 2027")
    clear_scenario_snapshot_cache()
    for _ in range(3):
        browser.run()
        assert not app.exception
        assert app.selectbox(key="merge_base_scenario").value == scenario_id
        revision = app.selectbox(key=f"merge_base_revision_{scenario_id}")
        assert revision.value == first.revision.revision_id
    assert browser.wire == "새 이름 2027", "상자가 옛 이름을 그대로 보입니다."


def test_a_revision_renamed_in_another_session_stays_the_chosen_source(stores: Stores) -> None:
    """다른 세션이 고른 원본 리비전의 이름을 바꿔도 원본은 고른 리비전 그대로다.

    리비전 상자의 글자에는 리비전명이 든다. 위젯 앞에서 고른 값을 다시 적지 않으면 브라우저가 옛
    글자를 되보내고, Streamlit 1.63 은 그 글자를 못 찾아 **예외 없이** 첫 리비전(최신)으로 되돌린다
    — 준비하던 연도 Shift 의 원본이 알림 없이 다른 리비전이 된다. 출처 메모에 든 리비전 id 로 잰다.
    """
    from widget_browser import BrowserChoice

    repository, database, first, _second = stores
    scenario_id = first.scenario.scenario_id
    newer = repository.save_revision(
        scenario_id,
        _monthly_tables([202701, 202702]),
        ScenarioPreset(202701, 202702, ("Process-A",)),
        revision_name="새 리비전",
        parent_revision_id=first.revision.revision_id,
    )
    revision_key = f"shift_source_revision_{scenario_id}"
    app = AppTest.from_string(_script(database, SHIFT_BODY), default_timeout=60).run()
    app.selectbox(key="shift_source_scenario").set_value(scenario_id).run()
    assert not app.exception
    browser = BrowserChoice(app, "selectbox", revision_key)
    browser.sync()
    assert browser.wire == f"r2 · {newer.revision.revision_name}"
    browser.pick(f"r1 · {first.revision.revision_name}")
    browser.run()
    app.number_input(key="scenario_shift_years").set_value(1)
    browser.run()
    assert not app.exception
    assert f"[리비전 {first.revision.revision_id}]" in _provenance(app)

    repository.rename_revision(
        first.revision.revision_id, "원본 새 이름", expected_name=first.revision.revision_name
    )
    clear_scenario_snapshot_cache()
    for years in (2, 3):
        app.number_input(key="scenario_shift_years").set_value(years)
        browser.run()
        assert not app.exception
        assert app.selectbox(key=revision_key).value == first.revision.revision_id
        assert f"[리비전 {first.revision.revision_id}]" in _provenance(app)
    assert browser.wire == "r1 · 원본 새 이름", "상자가 옛 이름을 그대로 보입니다."
    assert "r1 원본 새 이름" in _provenance(app)


# ---------------------------------------------------------------- 앱 전체에서 페이지 옮기기


def test_switching_pages_in_the_app_drops_the_sources(request: pytest.FixtureRequest) -> None:
    """`app.py` 를 그대로 띄워 시나리오 관리에서 원본을 고른 뒤 다른 페이지로 가면 메모가 없다.

    빈 DB 를 내장 시드가 채운다(`test_app_navigation._app`). 지우는 것은 페이지가 바뀐 회차의
    정리(`app.py` → `forget_page_dialogs`)다 — 다른 페이지에서는 시나리오 관리 화면이 돌지 않아
    모드 전환 정리가 끼지 않는다.
    """
    app: AppTest = request.getfixturevalue("_app").run()
    assert not app.exception
    app.switch_page(SCENARIO_MANAGEMENT.path).run()
    app.session_state["scenario_page_mode"] = "연도 Shift"
    app.run()
    assert not app.exception
    scenario_id = app.session_state[ACTIVE_PERSISTED_SCENARIO_ID_KEY]
    app.selectbox(key="shift_source_scenario").set_value(scenario_id).run()
    assert not app.exception
    assert SOURCE_MEMO_KEY in app.session_state

    app.switch_page(CAPA_CHATBOT.path).run()
    assert not app.exception
    assert SOURCE_MEMO_KEY not in app.session_state

    app.switch_page(SCENARIO_MANAGEMENT.path).run()
    assert not app.exception
    assert app.session_state["scenario_page_mode"] == "연도 Shift"
    assert SOURCE_MEMO_KEY in app.session_state
