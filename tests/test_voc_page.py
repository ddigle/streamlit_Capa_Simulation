# Purpose: VOC 화면이 작성자 이름을 화면 이동 뒤에도 지키는지 검증한다.

"""VOC 화면에서 사용자가 해 둔 것이 사라지지 않는다(2026-10-01 브라우저 점검).

- 작성자 칸은 다른 화면에 갔다 와도 남는다. Streamlit 은 그리지 않은 회차의 위젯 값을 버리므로
  `persist_state` 가 없으면 돌아왔을 때 빈 칸이고, 글을 올리면 「작성자를 입력하세요.」로 막혔다.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

VOC_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "voc.py"
ON_VOC = "test_on_voc"
AUTHOR_KEY = "voc_author"


def _script(database_path: Path) -> str:
    """VOC 한 화면과 「다른 화면」을 세션 칸 하나로 오간다(사이드바 페이지 이동의 대역)."""
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

if st.session_state.get({ON_VOC!r}, True):
    page = Path({str(VOC_PAGE)!r})
    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"), {{"__name__": "__main__"}})
else:
    st.write("다른 화면")
"""


def _app(database_path: Path) -> AppTest:
    app = AppTest.from_string(_script(database_path), default_timeout=60).run()
    assert not app.exception
    return app


def test_the_author_survives_a_trip_to_another_screen(tmp_path: Path) -> None:
    app = _app(tmp_path / "scenario.duckdb")
    app.text_input(key=AUTHOR_KEY).input("검증자A").run()

    app.session_state[ON_VOC] = False
    app.run()
    app.session_state[ON_VOC] = True
    app.run()

    assert not app.exception
    assert app.text_input(key=AUTHOR_KEY).value == "검증자A"
