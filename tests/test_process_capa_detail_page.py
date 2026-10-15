# Purpose: 공정 Capa 상세가 내장 시드로 열리고 공정 선택·주소 인자·HOME 전달 칸으로 들어오는지 본다.

"""공정 Capa 상세의 진입·선택 흐름(화면 조립 전 골격).

페이지만 띄운다(`test_all_pages_render` 와 같은 하네스 — 내장 시드를 임시 DuckDB 에 부트스트랩).
HOME 칸 클릭 자체는 AppTest 가 재현하지 못하므로 콜백이 남기는 것(전달 칸·주소 인자)을 넣고 돌린다
(`tests/test_process_detail_state.py` 가 콜백 쪽을 본다).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.navigation import PROCESS_CAPA_DETAIL
from capa_simulation.process_detail_state import (
    HOME_BOTTLENECK_SECTION,
    PROCESS_DETAIL_MONTH_KEY,
    PROCESS_DETAIL_PROCESS_KEY,
    PROCESS_DETAIL_REQUEST_KEY,
    ProcessDetailRequest,
)
from capa_simulation.services.month_columns import month_label

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / PROCESS_CAPA_DETAIL.path
ASSEMBLY_NOTICE = "화면 조립 중"


def _page_script(database_path: Path, equipment_path: Path) -> str:
    return f"""
from pathlib import Path

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

    source = Path({str(PAGE)!r})
    exec(
        compile(source.read_text(encoding="utf-8"), str(source), "exec"),
        {{"__name__": "__main__"}},
    )
finally:
    settings.DUCKDB_PATH = original_database_path
    settings.EQUIPMENT_DUCKDB_PATH = original_equipment_path
    horizontal_scrollbar.render_horizontal_scrollbar = original_scrollbar
    month_range_picker.render_month_range_apply = original_month_picker
"""


@pytest.fixture(scope="module")
def databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """내장 시드 부트스트랩은 멱등이라 모듈 안에서 DuckDB 두 개를 다시 쓴다."""
    root = tmp_path_factory.mktemp("process_capa_detail")
    return root / "scenario.duckdb", root / "equipment.duckdb"


def _app(databases: tuple[Path, Path]) -> AppTest:
    return AppTest.from_string(_page_script(*databases), default_timeout=300)


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [element.message for element in app.exception]
    return app


def _shown(app: AppTest) -> str:
    """골격이 지금 공정·달을 적는 한 줄(`**공정** · YY.MM`)."""
    lines = [str(element.value) for element in app.markdown if " · " in str(element.value)]
    assert lines, [str(element.value) for element in app.markdown]
    return lines[-1]


def test_the_page_opens_with_a_process_and_a_month_and_the_assembly_notice(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())

    process_box = app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY)
    assert process_box.value in process_box.options
    month = app.session_state[PROCESS_DETAIL_MONTH_KEY]
    assert isinstance(month, int)
    assert _shown(app) == f"**{process_box.value}** · {month_label(month)}"
    assert any(ASSEMBLY_NOTICE in str(element.value) for element in app.caption)
    # HOME 에서 오지 않았으므로 출처 띠가 없다.
    assert not any("칸에서 열었습니다" in str(element.value) for element in app.info)


def test_a_chosen_process_survives_reruns(databases: tuple[Path, Path]) -> None:
    app = _ok(_app(databases).run())
    process_box = app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY)
    other = next(option for option in process_box.options if option != process_box.value)

    process_box.set_value(other)
    _ok(app.run())
    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == other
    _ok(app.run())
    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == other
    assert _shown(app).startswith(f"**{other}**")


def test_the_address_opens_that_process_and_month(databases: tuple[Path, Path]) -> None:
    app = _ok(_app(databases).run())
    options = list(app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).options)
    first_month = app.session_state[PROCESS_DETAIL_MONTH_KEY]
    target = options[-1]

    app.query_params.update({"process": target, "month": str(first_month), "from": "home"})
    app.query_params["theme"] = "dark"
    _ok(app.run())

    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == target
    assert app.session_state[PROCESS_DETAIL_MONTH_KEY] == first_month
    # 읽은 키만 지운다 — 테마 인자는 남는다.
    assert dict(app.query_params) == {"theme": ["dark"]}


def test_the_home_transfer_slot_opens_the_cell_and_shows_the_origin_band(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    target = list(app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).options)[0]
    month = app.session_state[PROCESS_DETAIL_MONTH_KEY]
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process=target,
        month=month,
        section=HOME_BOTTLENECK_SECTION,
        displayed_rate=1.03,
        raw_rate=0.98,
        execution_delta=5.0,
    )
    _ok(app.run())

    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == target
    bands = [
        str(element.value) for element in app.info if "칸에서 열었습니다" in str(element.value)
    ]
    assert bands == [
        f"HOME 상세 B/N 공정 · {month_label(month)} 칸에서 열었습니다 · 표시 103% = 원 확보율 98% "
        "+ 실행 Capa +5.0%p · 아래는 원 확보율"
    ]


def test_a_month_outside_the_page_axis_opens_the_default_month_with_a_notice(
    databases: tuple[Path, Path],
) -> None:
    app = _ok(_app(databases).run())
    target = list(app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).options)[0]
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process=target, month=199001
    )
    _ok(app.run())

    assert isinstance(app.session_state[PROCESS_DETAIL_MONTH_KEY], int)
    assert any(
        "90.01" in str(element.value) and "밖이라" in str(element.value) for element in app.info
    )
