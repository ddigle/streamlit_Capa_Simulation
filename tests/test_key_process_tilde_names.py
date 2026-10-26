# Purpose: 주요공정 히트맵 프리셋 이름의 물결표가 마크다운 자리에서 지움선이 되지 않는지 본다.

"""프리셋 이름은 사람이 적는 글이다. 「A~B 묶음~2」 를 사이드바 칸(버튼 라벨)·Preference 캡션·삭제
확인 체크 라벨·저장 알림·팝업 라디오에 그대로 실으면 GFM 홑물결표 짝이 「B 묶음」 을 지움선으로
그리고 물결표를 지웠다(2026-10-26 E2E). 마크다운 자리마다 `literal_markdown`·`quoted` 로 막는다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.persistence.cache import (
    clear_global_key_process_cache,
    clear_scenario_repository,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

NAME = "A~B 묶음~2"
PROCESSES = ("DEMO_Chip_Attach", "DEMO_Final_Test")
# 막지 않은 물결표 — 앞에 `\` 가 없는 `~`.
BARE_TILDE = re.compile(r"(?<!\\)~")


def _script(database: Path) -> str:
    return f"""
from capa_simulation.components.home_preference import (
    _render_key_process_editor,
    render_key_process_dialog_body,
    render_key_process_field,
)
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.persistence.cache import load_global_key_process

database = {str(database)!r}
options = list({PROCESSES!r})
profile = load_global_key_process(database)
render_key_process_field(profile, process_labels=ProcessLabels(), process_options=options)
render_key_process_dialog_body(list(profile.preset_names), ["미리보기"] * len(profile.presets))
_render_key_process_editor(
    process_options=options, process_labels=ProcessLabels(), database_path=database
)
"""


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    repository.replace_global_key_process_presets(
        [(NAME, PROCESSES), ("둘째", PROCESSES[:1])], source="시험"
    )
    clear_scenario_repository()
    clear_global_key_process_cache()
    return path


def _app(database: Path) -> AppTest:
    app = AppTest.from_string(_script(database), default_timeout=60).run()
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def _shows_name(text: str) -> bool:
    """이름이 들어 있고 그 물결표가 모두 막혔다."""
    return "A\\~B 묶음\\~2" in text and not BARE_TILDE.search(text)


def test_the_sidebar_field_caption_and_dialog_keep_the_tildes(database: Path) -> None:
    app = _app(database)

    assert _shows_name(app.button(key="home_key_process_field").label)
    assert any(_shows_name(str(caption.value)) for caption in app.caption)
    radio = app.radio(key="home_key_process_preset_pick")
    assert _shows_name(radio.options[0])
    # 값은 이름 그대로다 — 막는 것은 보이는 글뿐이다.
    assert radio.value == NAME


def test_the_delete_check_and_the_notices_keep_the_tildes(database: Path) -> None:
    app = _app(database)
    assert any(_shows_name(box.label) for box in app.checkbox)

    # 같은 이름으로 새 프리셋을 저장하면 이름 중복 거부가 그 이름을 싣는다.
    app.selectbox(key="home_key_process_preset_edit").set_value("＋ 새 프리셋").run()
    next(widget for widget in app.text_input if widget.label == "프리셋 이름").input(NAME)
    next(button for button in app.button if button.label == "프리셋 저장").click().run()
    errors = [str(element.value) for element in app.error]
    assert errors and all(not BARE_TILDE.search(message) for message in errors), errors

    app.selectbox(key="home_key_process_preset_edit").set_value("둘째").run()
    app.button(key="home_key_process_preset_default").click().run()
    app.selectbox(key="home_key_process_preset_edit").set_value(NAME).run()
    app.button(key="home_key_process_preset_default").click().run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert [str(message.value) for message in app.success] == [
        "「A\\~B 묶음\\~2」를 기본 프리셋으로 옮겼습니다."
    ]
