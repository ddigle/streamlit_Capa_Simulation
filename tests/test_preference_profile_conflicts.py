# Purpose: HOME Preference 의 공지·Top5 구간·주요공정 프리셋 저장이 남의 저장을 덮지 않는지 본다.

"""세 편집기는 칸에 고정 key 가 없다(숨은 탭의 첫 값이 세션에 박히지 않게 — Top5 두 칸은 key 끝에
저장본 version 을, 주요공정 프리셋 이름·공정 두 칸은 고칠 프리셋 저장본의 지문을 붙여 함께 다시
선다). 그래서 남이 먼저 저장하면 옛 화면의 제출 회차에 칸이 새 저장본으로 서서 이 화면의 입력이
버려진다. 대조가 없으면 그 값을 version 만 올려 다시 쓰고 「저장했습니다」 를 띄웠다(2026-10-26
E2E — 두 문맥에서 세 칸 모두 재현). 판정 기준·확보율 보정과 같은 버전 대조로 거부하고, 이 세션의
빠른 두 번 누름은 거부가 아니라 저장으로 알린다(`write_guard.is_own_profile_save`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alert_marks import infos, successes
from streamlit.testing.v1 import AppTest

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.home_preference import (
    KEY_PROCESS_SEEN_KEY,
    KEY_PROCESS_UNCHANGED_MESSAGE,
    SUMMARY_BASE_VERSION_KEY,
    SUMMARY_UNCHANGED_MESSAGE,
    TOP5_BASE_VERSION_KEY,
    TOP5_UNCHANGED_MESSAGE,
)
from capa_simulation.persistence.cache import (
    clear_global_key_process_cache,
    clear_global_summary_note_cache,
    clear_global_top5_band_cache,
    clear_scenario_repository,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

PROCESSES = ("DEMO_Chip_Attach", "DEMO_Final_Test", "DEMO_Wafer_Inspect")


def _script(database: Path) -> str:
    return f"""
from capa_simulation.components.home_preference import (
    _render_key_process_editor,
    _render_summary_note_editor,
    _render_top5_band_editor,
)
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.persistence.cache import (
    load_global_summary_note,
    load_global_top5_band,
)

database = {str(database)!r}
_render_summary_note_editor(
    summary_profile=load_global_summary_note(database), database_path=database
)
_render_top5_band_editor(
    top5_band_profile=load_global_top5_band(database), database_path=database
)
_render_key_process_editor(
    process_options=list({PROCESSES!r}),
    process_labels=ProcessLabels(),
    database_path=database,
)
"""


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    repository.replace_global_key_process_presets(
        [("기본", PROCESSES[:2]), ("뒤 묶음", PROCESSES[2:])], source="시험"
    )
    return path


@pytest.fixture(autouse=True)
def _forget_profile_caches() -> None:
    """공용 프로필 캐시는 프로세스 전역이다. 앞 시험의 값이 첫 회차에 섞이지 않게 비운다."""
    clear_scenario_repository()
    clear_global_summary_note_cache()
    clear_global_top5_band_cache()
    clear_global_key_process_cache()


def _app(database: Path) -> AppTest:
    app = AppTest.from_string(_script(database), default_timeout=60).run()
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def _press(app: AppTest, label: str) -> AppTest:
    next(button for button in app.button if button.label == label).click()
    return app.run()


def _successes(app: AppTest) -> list[str]:
    return [str(element.value) for element in successes(app)]


def _errors(app: AppTest) -> list[str]:
    return [str(element.value) for element in app.error]


def _infos(app: AppTest) -> list[str]:
    return [str(element.value) for element in infos(app)]


def test_a_summary_save_from_a_stale_screen_is_rejected_not_reported_as_saved(
    database: Path,
) -> None:
    app = _app(database)
    # 이 화면이 v0 을 보는 사이 다른 세션이 먼저 공지를 올린다.
    DuckDBScenarioRepository(database).replace_global_summary_note(
        "B 공지 — 먼저 저장", source="다른 세션", expected_version=0
    )
    clear_global_summary_note_cache()
    app.text_area[0].input("A 공지 — 옛 화면에서 저장")
    app = _press(app, "Summary 저장")

    assert not list(app.exception)
    assert not _successes(app)
    assert any("다른 사용자가 먼저 Summary 공지를 저장" in message for message in _errors(app))
    profile = DuckDBScenarioRepository(database).load_global_summary_note()
    assert (profile.version, profile.note, profile.source) == (1, "B 공지 — 먼저 저장", "다른 세션")
    # 칸은 최신 저장본으로 다시 섰다 — 다음 저장은 그 version 에서 출발한다.
    assert app.text_area[0].value == "B 공지 — 먼저 저장"
    assert app.session_state[SUMMARY_BASE_VERSION_KEY] == 1


def test_a_top5_band_save_from_a_stale_screen_is_rejected(database: Path) -> None:
    app = _app(database)
    DuckDBScenarioRepository(database).replace_global_top5_band(
        0.5, 1.5, source="다른 세션", expected_version=0
    )
    clear_global_top5_band_cache()
    app.number_input[1].set_value(180.0)
    app = _press(app, "확보율 구간 저장")

    assert not list(app.exception)
    assert not _successes(app)
    assert any("다른 사용자가 먼저 Top5 확보율 구간을 저장" in message for message in _errors(app))
    profile = DuckDBScenarioRepository(database).load_global_top5_band()
    assert (profile.version, profile.min_rate, profile.max_rate) == (1, 0.5, 1.5)


@pytest.mark.parametrize(
    ("other", "expected"),
    [((0.8, 2.0), [80.0, 200.0]), ((0.5, 1.6), [50.0, 160.0]), ((0.6, 1.4), [60.0, 140.0])],
    ids=["하한만", "상한만", "둘 다"],
)
def test_after_a_refused_top5_save_both_boxes_show_the_latest_save(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    other: tuple[float, float],
    expected: list[float],
) -> None:
    """남의 저장에 거부된 뒤 두 칸이 **둘 다** 최신 저장본이다 — 남이 바꾼 칸만 새로 서고 안 바꾼
    칸은 이 화면이 친 값이 남아 아무도 정하지 않은 구간(하한 80 · 상한 180)이 섞여 보였고, 다시
    누르면 그대로 저장됐다(2026-10-27 표적 E2E)."""
    app = _app(database)
    assert [box.value for box in app.number_input] == [50.0, 200.0]
    DuckDBScenarioRepository(database).replace_global_top5_band(
        *other, source="다른 세션", expected_version=0
    )
    clear_global_top5_band_cache()
    app.number_input[0].set_value(70.0)
    app.number_input[1].set_value(180.0)
    app = _press(app, "확보율 구간 저장")

    assert any("다른 사용자가 먼저 Top5 확보율 구간을 저장" in message for message in _errors(app))
    assert [box.value for box in app.number_input] == expected
    assert app.session_state[TOP5_BASE_VERSION_KEY] == 1

    # 거부 창(`TRAILING_PRESS_SECONDS`)이 지난 뒤 다시 누르면 실제로 대조한다 — 두 칸이 최신
    # 저장본 그대로라 바뀐 것이 없어 새 버전을 만들지 않는다(2026-11-01 개선 I5 넓힘). 섞인 구간이면
    # 바뀐 것이라 그 구간이 v2 로 섰다(창 안의 누름은 쓰지 않아 이 대조가 되지 않는다).
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app = _press(app, "확보율 구간 저장")
    assert _infos(app) == [TOP5_UNCHANGED_MESSAGE]
    assert not _errors(app), _errors(app)
    profile = DuckDBScenarioRepository(database).load_global_top5_band()
    assert profile.version == 1
    assert [profile.min_rate * 100, profile.max_rate * 100] == pytest.approx(expected)


def test_a_preset_save_from_a_stale_screen_is_rejected(database: Path) -> None:
    app = _app(database)
    # 다른 세션이 「기본」 에서 공정 하나를 뺀다(v2).
    DuckDBScenarioRepository(database).replace_global_key_process_presets(
        [("기본", PROCESSES[:1]), ("뒤 묶음", PROCESSES[2:])],
        source="다른 세션",
        expected_version=1,
    )
    clear_global_key_process_cache()
    app.text_input[0].input("A 이름")
    app = _press(app, "프리셋 저장")

    assert not list(app.exception)
    assert not _successes(app)
    assert any("다른 사용자가 먼저 주요공정 프리셋을 저장" in message for message in _errors(app))
    profile = DuckDBScenarioRepository(database).load_global_key_process()
    assert profile.version == 2
    assert profile.presets == (("기본", PROCESSES[:1]), ("뒤 묶음", PROCESSES[2:]))


@pytest.mark.parametrize(
    ("other", "expected"),
    [
        ((("기본", PROCESSES[:1]), ("뒤 묶음", PROCESSES[2:])), ("기본", PROCESSES[:1])),
        ((("새 기본", PROCESSES[:2]), ("뒤 묶음", PROCESSES[2:])), ("새 기본", PROCESSES[:2])),
        ((("새 기본", PROCESSES[1:2]), ("뒤 묶음", PROCESSES[2:])), ("새 기본", PROCESSES[1:2])),
    ],
    ids=["공정만", "이름만", "둘 다"],
)
def test_after_a_refused_preset_save_name_and_processes_show_the_latest_save(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    other: tuple[tuple[str, tuple[str, ...]], ...],
    expected: tuple[str, tuple[str, ...]],
) -> None:
    """남의 저장에 거부된 뒤 이름·공정 두 칸이 **둘 다** 고칠 프리셋의 최신 저장본이다(Top5 구간과
    같은 꼴, 2026-11-01 결정 N7-preset). 칸에 key 가 없으면 위젯 id 가 값을 따라 남이 바꾼 칸만 새로
    섰다 — 공정만 바뀌면 이름 칸에 이 화면이 친 이름이, 맨 앞 프리셋 이름만 바뀌면 공정 칸에 이
    화면이 고른 공정이 남아 아무도 정하지 않은 프리셋이 보였고, 다시 누르면 그대로 저장됐다."""
    app = _app(database)
    assert (app.text_input[0].value, app.multiselect[0].value) == ("기본", list(PROCESSES[:2]))
    DuckDBScenarioRepository(database).replace_global_key_process_presets(
        list(other), source="다른 세션", expected_version=1
    )
    clear_global_key_process_cache()
    app.text_input[0].input("A 이름")
    app.multiselect[0].set_value([PROCESSES[2]])
    app = _press(app, "프리셋 저장")

    assert not _successes(app)
    assert any("다른 사용자가 먼저 주요공정 프리셋을 저장" in message for message in _errors(app))
    assert (app.text_input[0].value, app.multiselect[0].value) == (expected[0], list(expected[1]))
    assert app.session_state[KEY_PROCESS_SEEN_KEY] == (2, expected[0], expected[1])

    # 거부 창이 지난 뒤 다시 누르면 실제로 대조한다 — 두 칸이 고칠 프리셋의 최신 저장본 그대로라
    # 바뀐 것이 없어 새 버전을 만들지 않는다(2026-11-01 개선 I5 넓힘 — Top5 구간과 같은 꼴).
    # 섞인 프리셋이면 바뀐 것이라 그 프리셋이 v3 으로 섰다(창 안의 누름은 쓰지 않아 이 대조가
    # 되지 않는다).
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app = _press(app, "프리셋 저장")
    assert not _errors(app), _errors(app)
    assert _infos(app) == [KEY_PROCESS_UNCHANGED_MESSAGE]
    profile = DuckDBScenarioRepository(database).load_global_key_process()
    assert profile.version == 2
    assert profile.presets == (expected, ("뒤 묶음", PROCESSES[2:]))


def test_switching_the_preset_to_edit_still_shows_each_saved_preset(database: Path) -> None:
    """두 칸의 key 는 고칠 프리셋 저장본을 따른다 — 다른 프리셋으로 옮기면 그 프리셋의 저장본이
    서고, 돌아오면 친 값이 아니라 저장본이다(key 가 없던 때와 같다)."""
    app = _app(database)
    app.text_input[0].input("치다 만 이름")
    app.multiselect[0].set_value([PROCESSES[2]])
    app.selectbox[0].set_value("뒤 묶음")
    app = app.run()
    assert (app.text_input[0].value, app.multiselect[0].value) == ("뒤 묶음", list(PROCESSES[2:]))
    app.selectbox[0].set_value("기본")
    app = app.run()
    assert (app.text_input[0].value, app.multiselect[0].value) == ("기본", list(PROCESSES[:2]))
    assert not _errors(app)


def test_a_changed_process_label_still_restores_the_saved_processes(database: Path) -> None:
    """공정 칸 key 에는 보이는 글자도 든다 — key 가 붙은 multiselect 는 위젯 id 에 선택지 글자가
    들지 않아, 빼 두면 공정 목록이 바뀐 회차(이 화면에 없는 공정이 생김)에 고르던 값이 저장본
    대신 남는다. key 가 없던 때처럼 저장본으로 다시 선다."""
    script = _script(database).replace(
        f"process_options=list({PROCESSES!r}),",
        f"process_options=st.session_state.get('test_options', list({PROCESSES!r})),",
    )
    app = AppTest.from_string("import streamlit as st\n" + script, default_timeout=60).run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.multiselect[0].set_value([PROCESSES[2]])
    app = app.run()
    assert app.multiselect[0].value == [PROCESSES[2]]
    app.session_state["test_options"] = list(PROCESSES[1:])
    app = app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.multiselect[0].value == list(PROCESSES[:2])
    assert app.text_input[0].value == "기본"


def test_a_preset_renamed_by_someone_else_is_not_saved_over_another_preset(
    database: Path,
) -> None:
    """고칠 프리셋의 이름이 바뀌면 「고칠 프리셋」 이 맨 앞 프리셋으로 넘어간다 — 그 회차의
    제출을 쓰면 맨 앞 프리셋을 그대로 다시 쓰고 「저장했습니다」 를 띄웠다."""
    app = _app(database)
    app.selectbox[0].set_value("뒤 묶음")
    app = app.run()
    DuckDBScenarioRepository(database).replace_global_key_process_presets(
        [("기본", PROCESSES[:2]), ("새 이름", PROCESSES[2:])],
        source="다른 세션",
        expected_version=1,
    )
    clear_global_key_process_cache()
    app.text_input[0].input("A 가 고친 이름")
    app = _press(app, "프리셋 저장")

    assert not _successes(app)
    assert any("다른 사용자가 먼저" in message for message in _errors(app))
    profile = DuckDBScenarioRepository(database).load_global_key_process()
    assert (profile.version, profile.preset_names) == (2, ("기본", "새 이름"))


def test_another_preset_changed_meanwhile_still_lets_this_preset_save(database: Path) -> None:
    """다른 프리셋을 남이 고친 것은 거부하지 않는다 — 다시 읽은 묶음에 이 프리셋만 갈아 끼운다."""
    app = _app(database)
    DuckDBScenarioRepository(database).replace_global_key_process_presets(
        [("기본", PROCESSES[:2]), ("뒤 묶음", PROCESSES[1:])],
        source="다른 세션",
        expected_version=1,
    )
    clear_global_key_process_cache()
    app.text_input[0].input("앞 묶음")
    app = _press(app, "프리셋 저장")

    assert not _errors(app), _errors(app)
    assert _successes(app) == ["프리셋 「앞 묶음」을 저장했습니다."]
    profile = DuckDBScenarioRepository(database).load_global_key_process()
    assert profile.presets == (("앞 묶음", PROCESSES[:2]), ("뒤 묶음", PROCESSES[1:]))


def test_make_default_on_a_stale_screen_is_rejected(database: Path) -> None:
    app = _app(database)
    app.selectbox[0].set_value("뒤 묶음")
    app = app.run()
    assert app.session_state[KEY_PROCESS_SEEN_KEY] == (1, "뒤 묶음", PROCESSES[2:])
    DuckDBScenarioRepository(database).replace_global_key_process_presets(
        [("기본", PROCESSES[:2]), ("뒤 묶음", PROCESSES[1:])],
        source="다른 세션",
        expected_version=1,
    )
    clear_global_key_process_cache()
    app.button(key="home_key_process_preset_default").click()
    app = app.run()

    assert not list(app.exception)
    assert not _successes(app)
    assert any("다른 사용자가 먼저" in message for message in _errors(app))
    profile = DuckDBScenarioRepository(database).load_global_key_process()
    assert profile.version == 2
    assert profile.preset_names == ("기본", "뒤 묶음")


def test_a_save_on_a_fresh_screen_still_saves(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """새 화면에서 고친 세 저장은 저장한다. 앞 저장의 성공 알림은 느린 둘째 누름의 창 안 회차에 다시
    서므로(write_guard.held_notice) 창은 시험이 0 으로 정한다 — 저장마다 그 알림 하나만 본다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app = _app(database)
    app.text_area[0].input("새 공지")
    app = _press(app, "Summary 저장")
    assert _successes(app) == ["Summary 공지를 저장했습니다."]
    app.number_input[1].set_value(170.0)
    app = _press(app, "확보율 구간 저장")
    assert _successes(app) == ["B/N Top5 확보율 구간을 저장했습니다."]
    app.text_input[0].input("새 기본")
    app = _press(app, "프리셋 저장")
    assert _successes(app) == ["프리셋 「새 기본」을 저장했습니다."]

    assert not _errors(app)
    repository = DuckDBScenarioRepository(database)
    assert repository.load_global_summary_note().note == "새 공지"
    assert repository.load_global_top5_band().max_rate == pytest.approx(1.7)
    assert repository.load_global_key_process().preset_names == ("새 기본", "뒤 묶음")


@pytest.mark.parametrize(
    ("label", "base_key", "saved_message"),
    [
        ("Summary 저장", SUMMARY_BASE_VERSION_KEY, "Summary 공지를 저장했습니다."),
        ("확보율 구간 저장", TOP5_BASE_VERSION_KEY, "B/N Top5 확보율 구간을 저장했습니다."),
        ("프리셋 저장", KEY_PROCESS_SEEN_KEY, "주요공정 히트맵 프리셋을 저장했습니다."),
    ],
)
def test_a_double_press_reports_the_save_not_a_conflict(
    database: Path, label: str, base_key: str, saved_message: str
) -> None:
    """판정 기준과 같은 흉내다 — 누른 화면의 위젯 값과 끊긴 회차가 남긴 편집 시작 version 을 되살려
    한 번 더 보낸다(`tests/test_threshold_editor.py`)."""
    app = _app(database)
    base = app.session_state[base_key]
    app.text_area[0].input("두 번 누른 공지")
    app.number_input[1].set_value(160.0)
    app.text_input[0].input("두 번 누른 이름")
    next(button for button in app.button if button.label == label).click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert not _errors(app)

    app.session_state[base_key] = base
    app._run(widget_state=pressed)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not _errors(app), _errors(app)
    assert _successes(app) == [saved_message]


def _other_session_saves(database: Path, editor: str) -> None:
    """다른 세션이 먼저 저장한다 — 이 화면이 그린 저장본을 낡게 만든다."""
    repository = DuckDBScenarioRepository(database)
    if editor == "summary":
        repository.replace_global_summary_note("B 공지", source="다른 세션", expected_version=0)
        clear_global_summary_note_cache()
    elif editor == "top5":
        repository.replace_global_top5_band(0.5, 1.5, source="다른 세션", expected_version=0)
        clear_global_top5_band_cache()
    else:
        repository.replace_global_key_process_presets(
            [("기본", PROCESSES[:1]), ("뒤 묶음", PROCESSES[1:])],
            source="다른 세션",
            expected_version=1,
        )
        clear_global_key_process_cache()


def _stored_version(database: Path, editor: str) -> int:
    repository = DuckDBScenarioRepository(database)
    if editor == "summary":
        return repository.load_global_summary_note().version
    if editor == "top5":
        return repository.load_global_top5_band().version
    return repository.load_global_key_process().version


@pytest.mark.parametrize(("window", "trailing"), [(3600.0, True), (0.0, False)])
@pytest.mark.parametrize(
    ("editor", "label", "first_version"),
    [
        ("summary", "Summary 저장", 1),
        ("top5", "확보율 구간 저장", 1),
        ("key_process", "프리셋 저장", 2),
        ("key_process_default", "기본으로", 2),
    ],
)
def test_a_double_press_after_another_session_saved_keeps_the_refusal(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    editor: str,
    label: str,
    first_version: int,
    window: float,
    trailing: bool,
) -> None:
    """B 가 먼저 저장한 뒤 A 가 옛 화면에서 저장을 빠르게 두 번 누른다(판정 기준과 같은 꼴 —
    `tests/test_threshold_editor.py`).

    첫 누름은 거부되지만 그 회차가 편집 시작 version(프리셋은 본 고칠 프리셋)을 최신으로 올려, 둘째
    누름이 옛 화면의 입력을 든 채 대조를 지나 저장하고 「저장했습니다」 를 띄웠다 — key 없는 칸이 새
    저장본으로 서서 A 의 입력은 버려진다. 거부 직후(`TRAILING_PRESS_SECONDS`)의 둘째 누름은 저장하지
    않고 그 거부를 다시 알린다. 창이 지난 누름은 새 화면을 보고 다시 누른 저장이라 평소대로
    대조한다 — 공지·구간·프리셋은 그 화면이 B 의 값을 그렸고(새로 선 칸 — 프리셋 두 칸의 key 는
    고칠 프리셋 저장본의 지문을 든다, N7-preset) 그대로 누른 것이라 바뀐 것이 없어 새 버전을 만들지
    않는다(2026-11-01 개선 I5 넓힘). 「기본으로」 는 바뀐 것 판정이 없어 쓴다.
    """
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    app = _app(database)
    if editor == "key_process_default":
        app.selectbox[0].set_value("뒤 묶음")
        app = app.run()
    _other_session_saves(database, editor.removesuffix("_default"))
    app.text_area[0].input("A 공지 — 옛 화면")
    app.number_input[1].set_value(180.0)
    app.text_input[0].input("A 이름")
    next(button for button in app.button if button.label == label).click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert any("다른 사용자가 먼저" in message for message in _errors(app)), _errors(app)

    app._run(widget_state=pressed)

    assert not list(app.exception), [element.message for element in app.exception]
    stored = _stored_version(database, editor.removesuffix("_default"))
    if trailing:
        errors = _errors(app)
        assert len(errors) == 1 and "다른 사용자가 먼저" in errors[0], errors
        assert not _successes(app)
        assert stored == first_version
    elif editor == "summary":
        assert not _errors(app), _errors(app)
        assert _infos(app) == [SUMMARY_UNCHANGED_MESSAGE]
        assert stored == first_version
    elif editor == "top5":
        assert not _errors(app), _errors(app)
        assert _infos(app) == [TOP5_UNCHANGED_MESSAGE]
        assert stored == first_version
    elif editor == "key_process":
        assert not _errors(app), _errors(app)
        assert _infos(app) == [KEY_PROCESS_UNCHANGED_MESSAGE]
        assert stored == first_version
    else:
        assert not _errors(app), _errors(app)
        assert stored == first_version + 1
