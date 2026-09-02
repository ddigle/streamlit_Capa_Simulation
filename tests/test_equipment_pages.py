from pathlib import Path

from streamlit.testing.v1 import AppTest


def _page_script(page_path: Path, database_path: Path) -> str:
    return f"""
from pathlib import Path
import capa_simulation.settings as settings

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database_path)!r})
page_source = Path({str(page_path)!r}).read_text(encoding="utf-8")
exec(compile(page_source, {str(page_path)!r}, "exec"), {{"__name__": "__main__"}})
"""


def test_available_equipment_page_opens_with_empty_database(tmp_path: Path) -> None:
    page_path = Path("app_pages/available_equipment_status.py").resolve()
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "availability.duckdb"),
        default_timeout=60,
    ).run()

    assert not app.exception
    assert app.title[0].value == "가용설비 현황 (구현중)"
    assert [tab.label for tab in app.tabs] == ["대시보드", "설비 데이터·이력 관리"]
    assert [widget.label for widget in app.multiselect[:4]] == [
        "라인구분",
        "활용구분",
        "공정대분류",
        "공정소분류",
    ]
    assert "운영 지침" in [expandable.label for expandable in app.status]
    assert any(markdown.value == "#### Qual 확정상태 실행관리" for markdown in app.markdown)

    app.multiselect[0].set_value(["Line-A"])
    app.multiselect[1].set_value(["양산"])
    app.run()

    assert not app.exception


def test_space_page_opens_with_empty_database(tmp_path: Path) -> None:
    page_path = Path("app_pages/space_status.py").resolve()
    app = AppTest.from_string(
        _page_script(page_path, tmp_path / "space.duckdb"),
        default_timeout=60,
    ).run()

    assert not app.exception
    assert app.title[0].value == "Space 현황 (구현중)"
