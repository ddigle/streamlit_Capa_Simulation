# Purpose: 공정 그룹 편집 카드의 줄 · 칸 · 등급 꼴과 버전 대조 저장 흐름을 AppTest 로 본다.

"""공정 그룹 편집 카드(`components/process_group_editor.py`).

- 줄은 받은 공정 목록(한 열쇠 한 줄) 다음에 목록에 없는 저장 공정이 「· 이 화면에 없음」 을 달고
  선다. 「공정」 칸은 잠겼고 값은 원본 · 글자는 표시명이다. 「공정 그룹」 칸의 선택지는
  `PROCESS_GROUPS` 차례다.
- 저장은 버전 대조다 — 그룹을 고른 저장은 새 버전이고 목록 밖 저장 공정이 남는다. 바꾼 것 없는
  저장은 새 버전을 만들지 않는다(v0 의 첫 저장은 쓴다). 남의 저장 뒤 옛 화면의 저장은 거부되고 옛
  편집은 버려진다. 느린 둘째 누름은 방금 성공을 다시 알린다. 빠른 두 번 누름 · 넘어온 거부 글은
  `tests/test_write_guard_cas.py` 가 본다.
- 선택지가 비면 캡션 한 줄이고 표가 없다. 값만 보기는 표가 잠기고 저장 줄이 없다. 읽기 실패는 카드
  자리에 「데이터 Error」 마크다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alert_marks import data_error_marks, infos, place_errors, successes
from streamlit.testing.v1 import AppTest

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.process_group_editor import (
    ABSENT_MARK,
    NO_PROCESS_CAPTION,
    PROCESS_GROUP_NOTE_KEY,
    PROCESS_GROUP_SAVE_LABEL,
    PROCESS_GROUP_SAVED_MESSAGE,
    PROCESS_GROUP_UNCHANGED_MESSAGE,
    _save_error_message,
    process_group_editor_key,
)
from capa_simulation.persistence.cache import clear_global_process_group_cache
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.process_group import (
    PROCESS_GROUP_LABEL,
    PROCESS_GROUPS,
    ProcessGroupDuplicateError,
)

NBSP_DA = "DEMO DA"
OPTIONS = (NBSP_DA, "DEMO_WB", "DEMO DA ")


@pytest.fixture
def repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[DuckDBScenarioRepository]:
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    store = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    store.initialize()
    clear_global_process_group_cache()
    yield store
    clear_global_process_group_cache()


def _script(
    repository: DuckDBScenarioRepository,
    options: Sequence[str] = OPTIONS,
    *,
    read_only: bool = False,
    failing: bool = False,
) -> str:
    failure = (
        "editor.load_global_process_group = lambda path: (_ for _ in ()).throw("
        "OSError('DEMO 읽기 실패'))\n"
        if failing
        else ""
    )
    return f"""
import pandas as pd

import capa_simulation.components.process_group_editor as editor
from capa_simulation.components.process_labels import process_labels_from_rules

{failure}editor.render_process_group_editor(
    process_options={list(options)!r},
    process_labels=process_labels_from_rules(
        pd.DataFrame({{"공정": ["DEMO_WB"], "표시명": ["DEMO 와이어"]}})
    ),
    database_path={str(repository.database_path)!r},
    read_only={read_only!r},
    save_help="DEMO 풍선",
)
"""


def _app(repository: DuckDBScenarioRepository, **kwargs: Any) -> AppTest:
    app = AppTest.from_string(_script(repository, **kwargs), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _seed(repository: DuckDBScenarioRepository, pairs: list[tuple[str, str]]) -> None:
    repository.replace_global_process_group(pairs, source="처음 저장")
    clear_global_process_group_cache()


def _columns(app: AppTest) -> dict[str, Any]:
    (editor,) = app.dataframe
    return dict(json.loads(editor.proto.columns))


def _rows(app: AppTest) -> list[tuple[str, str | None]]:
    (editor,) = app.dataframe
    frame = editor.value
    return [
        (str(process), None if group is None or pd.isna(group) else str(group))
        for process, group in zip(frame["공정"], frame["공정그룹"], strict=True)
    ]


def _edit(app: AppTest, version: int, edits: dict[int, dict[str, object]]) -> None:
    """지금 줄(그린 표의 공정 차례)의 편집 표 칸을 고친 것처럼 채운다(다음 회차가 보낸다)."""
    processes = [process for process, _group in _rows(app)]
    app.session_state[process_group_editor_key(version, processes)] = {
        "edited_rows": edits,
        "added_rows": [],
        "deleted_rows": [],
    }


def _press(app: AppTest) -> AppTest:
    next(button for button in app.button if button.label == PROCESS_GROUP_SAVE_LABEL).click()
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _texts(items: Iterable[Any]) -> list[str]:
    return [str(item.value) for item in items]


def test_rows_are_the_options_then_the_stored_processes_off_this_screen(
    repository: DuckDBScenarioRepository,
) -> None:
    """열쇠가 같은 선택지(U+00A0 · 끝 공백만 다름)는 처음 나온 원본 한 줄이다. 저장 공정이 목록에
    없으면 뒤에 붙고 「· 이 화면에 없음」 을 단다 — 칸 풍선은 그 줄이 있을 때만이다."""
    _seed(repository, [("DEMO DA", "FRONT"), ("DEMO_GONE", "pkg")])
    app = _app(repository)

    assert _rows(app) == [(NBSP_DA, "FRONT"), ("DEMO_WB", None), ("DEMO_GONE", "PKG")]
    columns = _columns(app)
    process = columns["공정"]
    assert process["disabled"] is True
    assert process["type_config"]["options"] == [
        {"value": NBSP_DA, "label": NBSP_DA},
        {"value": "DEMO_WB", "label": "DEMO 와이어"},
        {"value": "DEMO_GONE", "label": f"DEMO_GONE{ABSENT_MARK}"},
    ]
    assert process["help"]
    group = columns["공정그룹"]
    assert group["label"] == PROCESS_GROUP_LABEL
    assert group["type_config"]["options"] == list(PROCESS_GROUPS)
    assert not group.get("required")
    assert [button.label for button in app.button] == [PROCESS_GROUP_SAVE_LABEL]
    assert [field.label for field in app.text_input] == ["변경 메모"]
    assert any("공용 버전 v1" in caption for caption in _texts(app.caption))

    every_row_here = _app(repository, options=("DEMO_GONE", "DEMO DA"))
    assert _rows(every_row_here) == [("DEMO_GONE", "PKG"), ("DEMO DA", "FRONT")]
    assert not _columns(every_row_here)["공정"].get("help")


def test_an_untouched_save_makes_no_new_version_but_the_first_save_writes(
    repository: DuckDBScenarioRepository,
) -> None:
    """저장본이 없는 v0 의 첫 저장은 손대지 않아도 쓴다(0행). 그 뒤 손대지 않은 저장은 새 버전 없이
    「바뀐 것이 없습니다」 이고, 메모만 적어도 같다."""
    app = _app(repository)
    assert _rows(app) == [(NBSP_DA, None), ("DEMO_WB", None)]

    app = _press(app)
    assert _texts(successes(app)) == [PROCESS_GROUP_SAVED_MESSAGE]
    profile = repository.load_global_process_group()
    assert (profile.version, profile.assignments) == (1, ())

    app = _press(app)
    assert _texts(infos(app)) == [PROCESS_GROUP_UNCHANGED_MESSAGE]
    assert not successes(app) and not place_errors(app), place_errors(app)

    app.text_input(key=PROCESS_GROUP_NOTE_KEY).set_value("메모만 적음")
    app = _press(app)
    assert _texts(infos(app)) == [PROCESS_GROUP_UNCHANGED_MESSAGE]
    assert repository.load_global_process_group().version == 1


def test_a_chosen_group_saves_and_keeps_the_stored_processes_off_this_screen(
    repository: DuckDBScenarioRepository,
) -> None:
    """그룹을 고른 저장은 새 버전이고 원본 공정명으로 저장한다. 목록에 없는 저장 공정은 손대지
    않으면 그대로 남고(통째 교체가 남의 값을 지우지 않음), 그룹 칸을 비우면 빠진다."""
    _seed(repository, [("DEMO DA", "FRONT"), ("DEMO_GONE", "PKG")])
    app = _app(repository)

    _edit(app, 1, {1: {"공정그룹": "MI"}})
    app.text_input(key=PROCESS_GROUP_NOTE_KEY).set_value("DEMO_WB 를 MI 로")
    app = _press(app)

    assert not infos(app) and not place_errors(app), place_errors(app)
    assert _texts(successes(app)) == [PROCESS_GROUP_SAVED_MESSAGE]
    profile = repository.load_global_process_group()
    assert (profile.version, profile.source) == (2, "DEMO_WB 를 MI 로")
    assert profile.assignments == (
        ("DEMO DA", "FRONT"),
        ("DEMO_GONE", "PKG"),
        ("DEMO_WB", "MI"),
    )
    assert _rows(app) == [(NBSP_DA, "FRONT"), ("DEMO_WB", "MI"), ("DEMO_GONE", "PKG")]
    assert app.text_input(key=PROCESS_GROUP_NOTE_KEY).value == ""

    _edit(app, 2, {2: {"공정그룹": None}})
    app = _press(app)
    profile = repository.load_global_process_group()
    assert profile.version == 3
    assert profile.assignments == (("DEMO DA", "FRONT"), ("DEMO_WB", "MI"))
    assert profile.source == "웹 직접 편집"


def test_a_save_on_a_screen_older_than_another_save_is_refused_and_its_edits_dropped(
    repository: DuckDBScenarioRepository,
) -> None:
    """남이 먼저 저장한 뒤 옛 화면의 저장 — 표 key 가 저장본 version 을 따라 바뀌어 옛 편집은
    버려지고 표가 새 저장본으로 선다. 저장소의 버전 대조가 거부하고 아무것도 쓰지 않는다. 새 화면을
    보고 다시 누른 저장은 지난다."""
    _seed(repository, [("DEMO DA", "FRONT")])
    app = _app(repository)
    repository.replace_global_process_group(
        [("DEMO DA", "FRONT"), ("DEMO_WB", "TEST")], source="다른 세션", expected_version=1
    )
    clear_global_process_group_cache()

    _edit(app, 1, {1: {"공정그룹": "PKG"}})
    app = _press(app)

    errors = _texts(app.error)
    assert len(errors) == 1 and "다른 사용자가 먼저" in errors[0], errors
    assert not successes(app)
    profile = repository.load_global_process_group()
    assert (profile.version, profile.source) == (2, "다른 세션")
    assert _rows(app) == [(NBSP_DA, "FRONT"), ("DEMO_WB", "TEST")]

    _edit(app, 2, {1: {"공정그룹": "PKG"}})
    app = _press(app)
    assert not place_errors(app), place_errors(app)
    assert _texts(successes(app)) == [PROCESS_GROUP_SAVED_MESSAGE]
    profile = repository.load_global_process_group()
    assert profile.version == 3
    assert profile.assignments == (("DEMO DA", "FRONT"), ("DEMO_WB", "PKG"))


def test_a_slow_second_press_repeats_the_success(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """느린 둘째 누름(첫 저장 뒤 새로 그린 표에 닿음 — 같은 표라 바뀐 것이 없다)은 「바뀐 것이
    없습니다」 로 방금 성공을 덮지 않는다(write_guard.held_notice 창 안)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    _seed(repository, [("DEMO DA", "FRONT")])
    app = _app(repository)
    _edit(app, 1, {1: {"공정그룹": "FDY"}})
    app = _press(app)
    assert repository.load_global_process_group().version == 2

    app = _press(app)

    assert not infos(app) and not place_errors(app), place_errors(app)
    assert _texts(successes(app)) == [PROCESS_GROUP_SAVED_MESSAGE]
    assert repository.load_global_process_group().version == 2


def test_no_options_draw_one_caption_and_no_table(repository: DuckDBScenarioRepository) -> None:
    _seed(repository, [("DEMO DA", "FRONT")])
    app = _app(repository, options=())

    assert _texts(app.caption)[-1] == NO_PROCESS_CAPTION
    assert not app.dataframe
    assert not app.button and not app.text_input


def test_below_the_manager_the_card_shows_values_only(repository: DuckDBScenarioRepository) -> None:
    """값만 보기 — 표는 잠기고(줄 더하기 없음) 저장 단추 · 메모 칸이 없다. 값과 「이 화면에 없음」
    줄은 그대로 보인다."""
    _seed(repository, [("DEMO DA", "FRONT"), ("DEMO_GONE", "PKG")])
    app = _app(repository, read_only=True)

    (editor,) = app.dataframe
    assert editor.proto.disabled is True
    assert _rows(app) == [(NBSP_DA, "FRONT"), ("DEMO_WB", None), ("DEMO_GONE", "PKG")]
    assert not app.button and not app.text_input
    assert any("공용 버전 v1" in caption for caption in _texts(app.caption))


def test_a_read_failure_is_a_data_error_mark_on_the_card(
    repository: DuckDBScenarioRepository,
) -> None:
    app = _app(repository, failing=True)

    assert data_error_marks(app) == 1
    assert not app.dataframe and not app.button
    assert not app.error


def test_the_editor_key_follows_the_saved_version_and_the_rows() -> None:
    """편집은 줄 위치로 남는다 — 저장본 version 이나 줄(차례 포함)이 바뀌면 key 가 바뀐다."""
    rows = ["DEMO_A", "DEMO_B"]
    key = process_group_editor_key(3, rows)
    assert key == process_group_editor_key(3, list(rows))
    assert key != process_group_editor_key(4, rows)
    assert key != process_group_editor_key(3, list(reversed(rows)))
    assert key != process_group_editor_key(3, [*rows, "DEMO_C"])


def test_a_duplicate_save_error_keeps_the_names_as_typed() -> None:
    """같은 공정 두 줄 오류는 이름(사람 글)을 막아 마크다운에서 글자 그대로 보이게 다시 짓는다."""
    message = _save_error_message(ProcessGroupDuplicateError(["DEMO*A*", "DEMO_B"]))
    assert message.startswith("같은 공정이 두 줄입니다: ")
    assert "DEMO*A*" not in message
