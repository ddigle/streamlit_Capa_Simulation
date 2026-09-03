# Purpose: 선언된 모든 페이지가 내장 시드 상태에서 예외 없이 렌더링되는지 검사한다.

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.navigation import ALL_SPECS

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 개별 페이지 테스트는 화면 구성을 자세히 보지만 모든 페이지를 덮지는 못한다. 여기서는
# "열리기는 하는가"만 전수로 확인한다. 페이지를 추가하면 자동으로 포함된다.


def _page_script(page_path: str, database_path: Path, equipment_path: Path) -> str:
    source = (PROJECT_ROOT / page_path).resolve()
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.month_range_picker as month_range_picker
import capa_simulation.settings as settings

# 갈아끼운 것은 반드시 되돌린다. 모듈 속성을 영구 교체하면 같은 프로세스에서 뒤에 도는
# 테스트가 조용히 다른 것을 보게 된다.
original_database_path = settings.DUCKDB_PATH
original_equipment_path = settings.EQUIPMENT_DUCKDB_PATH
original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
original_month_picker = month_range_picker.render_month_range_picker

settings.DUCKDB_PATH = Path({str(database_path)!r})
settings.EQUIPMENT_DUCKDB_PATH = Path({str(equipment_path)!r})

# Components v2 위젯은 모듈 import 시점에 등록되어 AppTest 인스턴스마다 살아 있지 않다.
horizontal_scrollbar.render_horizontal_scrollbar = lambda *args, **kwargs: None
month_range_picker.render_month_range_picker = (
    lambda *, start, end, min_month, max_month, key: (start, end)
)

try:
    from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
    from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

    bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    apply_pending_scenario_preset()

    source = Path({str(source)!r})
    exec(
        compile(source.read_text(encoding="utf-8"), str(source), "exec"),
        {{"__name__": "__main__"}},
    )
finally:
    settings.DUCKDB_PATH = original_database_path
    settings.EQUIPMENT_DUCKDB_PATH = original_equipment_path
    horizontal_scrollbar.render_horizontal_scrollbar = original_scrollbar
    month_range_picker.render_month_range_picker = original_month_picker
"""


@pytest.fixture(scope="module")
def seeded_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """내장 시드 부트스트랩은 멱등이므로 모듈 안에서 DuckDB 두 개를 재사용한다."""
    root = tmp_path_factory.mktemp("pages")
    return root / "scenario.duckdb", root / "equipment.duckdb"


@pytest.mark.parametrize("page_path", [spec.path for spec in ALL_SPECS])
def test_page_renders_without_exceptions(
    page_path: str, seeded_databases: tuple[Path, Path]
) -> None:
    database_path, equipment_path = seeded_databases

    app = AppTest.from_string(
        _page_script(page_path, database_path, equipment_path),
        default_timeout=300,
    ).run()

    assert not list(app.exception), [element.message for element in app.exception]
