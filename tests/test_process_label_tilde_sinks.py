# Purpose: 공정 표시명·원본 공정명의 물결표가 HOME 팝업·Admin 알림에서 지움선이 되지 않는지 본다.

"""공정 표시명은 Admin › Proc Rename 에서 사람이 적고 원본 공정명은 붙여넣기로 들어온다.
「CoW~검사~A」 를 HOME 공정 필터 팝업 단추·자동 갱신 줄, 주요공정 히트맵 팝업 캡션·「그리지 않는
공정」 캡션·확보율 보정 안내, Admin 「무시합니다」 안내·이름 중복 거부에 그대로 실으면 GFM 홑물결표
짝이 가운데를 지움선으로 그리고 물결표를 지웠다(2026-10-26 E2E). 마크다운 자리마다 막는다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_preference import key_process_preview
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.persistence.cache import (
    clear_global_process_rename_cache,
    clear_scenario_repository,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

LABEL = "CoW~검사~A"
LABELS = ProcessLabels(version=1, labels={"AVI-CoW": LABEL, "SAW": "S~1~2"})
# 막지 않은 물결표 — 앞에 `\` 가 없는 `~`.
BARE_TILDE = re.compile(r"(?<!\\)~")


def _escaped(text: str) -> bool:
    return "~" in text and not BARE_TILDE.search(text)


def test_the_preset_preview_caption_escapes_process_labels() -> None:
    preview = key_process_preview(["AVI-CoW", "SAW"], LABELS, ["AVI-CoW"])

    assert _escaped(preview), preview
    assert "CoW\\~검사\\~A" in preview and "S\\~1\\~2" in preview


def test_process_picker_buttons_and_auto_off_line_escape_labels() -> None:
    def script() -> None:
        from capa_simulation.components.process_labels import ProcessLabels
        from capa_simulation.components.process_picker import render_process_picker
        from capa_simulation.services.process_picker import ProcessPickerItem

        labels = ProcessLabels(version=1, labels={"AVI-CoW": "CoW~검사~A"})
        render_process_picker(
            [
                ProcessPickerItem(
                    process="AVI-CoW",
                    minimum_rate=0.5,
                    minimum_month=202603,
                    valid_month_count=3,
                    group="shortfall",
                )
            ],
            set(),
            format_func=labels.format_func(),
            on_toggle=lambda _process: None,
            marks={"AVI-CoW": "자동 off(확보율 50%, 26.03)"},
        )

    app = AppTest.from_function(script).run()

    assert not list(app.exception), [element.message for element in app.exception]
    button = app.button(key="home_bn_process_tile_AVI-CoW")
    assert _escaped(button.label), button.label
    assert any(_escaped(str(caption.value)) for caption in app.caption)
    # 풍선은 CSS `content` 라 글자 그대로다.
    assert any("CoW~검사~A" in str(element.proto.body) for element in app.get("html"))


def test_home_preference_notices_escape_labels() -> None:
    def script() -> None:
        import pandas as pd

        from capa_simulation.components.home_preference import (
            _render_execution_notices,
            _render_key_process_notice,
        )
        from capa_simulation.components.process_labels import ProcessLabels

        labels = ProcessLabels(version=1, labels={"AVI-CoW": "CoW~검사~A"})
        _render_key_process_notice(["AVI-CoW"], labels)
        _render_execution_notices(
            pd.DataFrame({"생산계획년월": [202603], "공정": ["AVI-CoW"]}),
            pd.DataFrame(),
            labels,
        )

    app = AppTest.from_function(script).run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert [_escaped(str(caption.value)) for caption in app.caption] == [True]
    assert [_escaped(str(warning.value)) for warning in app.warning] == [True]


def _admin_script(database: Path) -> str:
    return f"""
from pathlib import Path

from capa_simulation.components.process_rename_management import (
    render_process_rename_management,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

repository = DuckDBScenarioRepository(Path({str(database)!r}))
render_process_rename_management(repository, ["AVI-CoW"])
"""


def test_admin_ignored_names_and_duplicate_rejection_escape_tildes(tmp_path: Path) -> None:
    database = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame({"공정": ["AVI-CoW", "없는~공정~1"], "표시명": [LABEL, "가짜표시"]}),
        source="시험",
    )
    clear_scenario_repository()
    clear_global_process_rename_cache()
    app = AppTest.from_string(_admin_script(database), default_timeout=60).run()

    assert not list(app.exception), [element.message for element in app.exception]
    notices = [str(info.value) for info in app.info]
    assert any("없는\\~공정\\~1" in notice for notice in notices), notices
    assert all(not BARE_TILDE.search(notice) for notice in notices), notices

    # 직접 편집에서 같은 표시명을 둘 넣으면 거부 글이 그 이름을 싣는다.
    app.session_state["admin_area_process_rename_editor"] = {
        "edited_rows": {"1": {"표시명": LABEL}},
        "added_rows": [],
        "deleted_rows": [],
    }
    next(button for button in app.button if button.label == "공용 공정 표시명 저장").click()
    app.run()

    errors = [str(error.value) for error in app.error]
    assert errors and all(_escaped(message) for message in errors), errors
