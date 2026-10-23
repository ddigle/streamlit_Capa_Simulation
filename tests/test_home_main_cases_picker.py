# Purpose: HOME 「주요 Case」 상자의 고르기·저장·다시 열기·지운 시나리오·이름 바꾸기·겹침을 지킨다.

"""주요 Case 상자는 공용 프로필의 거울이다(2026-10-23 사용자 요청).

고르는 것이 곧 저장이고, 시나리오를 고르면 그 시나리오 첫 리비전과 **짝으로** 저장한다(위젯
기본값은 `on_change` 를 부르지 않는다). 회차마다 프로필 값을 상자에 적으므로 다른 세션이 바꾼
지정·이름이 그대로 보이고, 브라우저가 옛 글자를 되보내도 지정이 바뀌지 않는다. 이름 바꾸기는
`BrowserChoice` 로 잰다 — 일반 `AppTest.run()` 은 글자를 회차마다 새로 만들어 그 결함을 보지 못한다.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_main_cases import (
    MAIN_CASE_NOTICE_KEY,
    main_case_revision_key,
    main_case_scenario_key,
)
from capa_simulation.persistence.cache import clear_global_main_cases_cache
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import DuckDBScenarioRepository

PICKER_SCRIPT = """
import streamlit as st

from capa_simulation.components.home_main_cases import render_main_case_picker

render_main_case_picker(st.session_state["database_path"])
"""

CASE1_SCENARIO = main_case_scenario_key(1)
CASE1_REVISION = main_case_revision_key(1)
CASE2_SCENARIO = main_case_scenario_key(2)
CASE2_REVISION = main_case_revision_key(2)


def _two_scenarios(database: Path) -> tuple[str, str, str, str, str]:
    """내장 시드(공식) S1 과 리비전이 둘인 S2. (S1, S1 공식 리비전, S2, S2 옛 리비전, S2 새 리비전).

    선택지는 리비전 번호 내림차순이라 S2 의 첫 항목은 새 리비전이다.
    """
    from capa_simulation.application_bootstrap import ensure_initial_scenario

    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    base = repository.load_revision(release.revision_id)
    tables = {name: frame.copy() for name, frame in base.tables.items()}
    second = repository.create_scenario(
        ScenarioCreate(
            scenario_name="증설안",
            source_simulation_code="CASE",
            source_simulation_name="증설안",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        tables,
        base.preset,
    )
    newer = repository.save_revision(
        second.scenario.scenario_id, tables, base.preset, revision_name="증설안 확정"
    )
    return (
        str(base.scenario.scenario_id),
        str(base.revision.revision_id),
        str(second.scenario.scenario_id),
        str(second.revision.revision_id),
        str(newer.revision.revision_id),
    )


def _profile(database: Path) -> tuple[tuple[str | None, str | None], ...]:
    profile = DuckDBScenarioRepository(database).load_global_main_cases()
    return profile.case(1), profile.case(2)


def _version(database: Path) -> int:
    return DuckDBScenarioRepository(database).load_global_main_cases().version


def _app(database: Path) -> AppTest:
    app = AppTest.from_string(PICKER_SCRIPT, default_timeout=120)
    app.session_state["database_path"] = str(database)
    return app


def _ran(app: AppTest) -> AppTest:
    assert not app.exception, [element.message for element in app.exception]
    return app


def _texts(app: AppTest) -> list[str]:
    return [str(element.value) for element in (*app.markdown, *app.caption, *app.warning)]


def test_choosing_saves_the_pair_and_a_new_session_reopens_it(tmp_path: Path) -> None:
    """시나리오를 고르면 첫 리비전과 짝으로 한 번 저장되고, 리비전을 고르면 그 리비전으로 바뀐다.

    다른 Case 는 그대로다. 새 세션(브라우저를 새로 연 것)이 같은 값으로 열리고, 아무것도 고르지 않은
    회차는 프로필을 다시 쓰지 않는다.
    """
    database = tmp_path / "scenario.duckdb"
    _s1, _s1_revision, s2, s2_older, s2_newer = _two_scenarios(database)
    clear_global_main_cases_cache()
    app = _ran(_app(database).run())
    assert app.selectbox(key=CASE1_SCENARIO).value is None
    assert any("슬롯 1 · 공식버전" in text and "공식 v1" in text for text in _texts(app))
    assert _version(database) == 0

    _ran(app.selectbox(key=CASE1_SCENARIO).set_value(s2).run())
    assert _profile(database) == ((s2, s2_newer), (None, None))
    assert _version(database) == 1
    assert app.selectbox(key=CASE1_REVISION).value == s2_newer

    _ran(app.selectbox(key=CASE1_REVISION).set_value(s2_older).run())
    assert _profile(database) == ((s2, s2_older), (None, None))
    assert _version(database) == 2

    reopened = _ran(_app(database).run())
    assert reopened.selectbox(key=CASE1_SCENARIO).value == s2
    assert reopened.selectbox(key=CASE1_REVISION).value == s2_older
    assert reopened.selectbox(key=CASE2_SCENARIO).value is None
    _ran(reopened.run())
    assert _version(database) == 2, "고르지 않았는데 공용 프로필을 다시 썼습니다."


def test_unset_clears_both_cells_of_that_case_only(tmp_path: Path) -> None:
    database = tmp_path / "scenario.duckdb"
    s1, s1_revision, s2, _s2_older, s2_newer = _two_scenarios(database)
    repository = DuckDBScenarioRepository(database)
    repository.replace_global_main_case(1, s2, s2_newer, source="테스트")
    repository.replace_global_main_case(2, s1, s1_revision, source="테스트")
    clear_global_main_cases_cache()
    app = _ran(_app(database).run())

    _ran(app.selectbox(key=CASE1_SCENARIO).set_value(None).run())

    assert _profile(database) == ((None, None), (s1, s1_revision))
    assert app.selectbox(key=CASE1_REVISION + "_idle").disabled


def test_a_removed_scenario_leaves_the_box_unset(tmp_path: Path) -> None:
    """영구 삭제는 저장소가 그 Case 를 비우고 화면이 캐시를 비운다 — 다음 회차 상자는 비어 있다."""
    database = tmp_path / "scenario.duckdb"
    _s1, _s1_revision, s2, _s2_older, s2_newer = _two_scenarios(database)
    repository = DuckDBScenarioRepository(database)
    repository.replace_global_main_case(2, s2, s2_newer, source="테스트")
    clear_global_main_cases_cache()
    app = _ran(_app(database).run())
    assert app.selectbox(key=CASE2_SCENARIO).value == s2

    repository.delete_scenario(s2)
    clear_global_main_cases_cache()
    _ran(app.run())

    assert app.selectbox(key=CASE2_SCENARIO).value is None
    assert s2 not in app.selectbox(key=CASE2_SCENARIO).options
    assert _profile(database)[1] == (None, None)


def test_a_vanished_scenario_left_in_the_profile_is_cleared_once_with_a_notice(
    tmp_path: Path,
) -> None:
    """보관·삭제 밖의 길로 남은 사라진 시나리오는 상자가 그릴 수 없다 — 비우고 한 번 알린다.

    남겨 두면 상자는 「지정 안 함」으로 보이는데 그것을 다시 골라도 값이 바뀌지 않아 지울 길이 없다.
    다른 Case 는 그대로이고, 비운 뒤의 회차는 다시 쓰지 않는다.
    """
    database = tmp_path / "scenario.duckdb"
    _s1, _s1_revision, s2, s2_older, _s2_newer = _two_scenarios(database)
    repository = DuckDBScenarioRepository(database)
    repository.replace_global_main_case(1, s2, s2_older, source="테스트")
    repository.replace_global_main_case(2, "사라진-시나리오", "사라진-리비전", source="옛 값")
    clear_global_main_cases_cache()

    app = _ran(_app(database).run())

    assert _profile(database) == ((s2, s2_older), (None, None))
    assert any("Case2 에 지정했던 시나리오가 목록에 없어" in text for text in _texts(app))
    assert app.selectbox(key=CASE2_SCENARIO).value is None
    version = _version(database)
    _ran(app.run())
    assert not any("지정했던 시나리오" in text for text in _texts(app))
    assert _version(database) == version


def test_a_blank_revision_is_filled_with_the_first_one_once(tmp_path: Path) -> None:
    """리비전 칸이 빈 짝(스크립트 등)은 상자가 서는 첫 리비전으로 메운다 — 한 번만 쓴다."""
    database = tmp_path / "scenario.duckdb"
    _s1, _s1_revision, s2, _s2_older, s2_newer = _two_scenarios(database)
    DuckDBScenarioRepository(database).replace_global_main_case(1, s2, None, source="테스트")
    clear_global_main_cases_cache()

    app = _ran(_app(database).run())

    assert _profile(database)[0] == (s2, s2_newer)
    assert app.selectbox(key=CASE1_REVISION).value == s2_newer
    version = _version(database)
    _ran(app.run())
    assert _version(database) == version


def test_another_sessions_choice_shows_on_the_next_run(tmp_path: Path) -> None:
    """공용 지정이라 남이 바꾼 값이 다음 회차 상자에 그대로 보인다(이쪽 세션 값으로 안 되쓴다)."""
    database = tmp_path / "scenario.duckdb"
    s1, s1_revision, s2, _s2_older, s2_newer = _two_scenarios(database)
    repository = DuckDBScenarioRepository(database)
    repository.replace_global_main_case(1, s2, s2_newer, source="테스트")
    clear_global_main_cases_cache()
    app = _ran(_app(database).run())

    repository.replace_global_main_case(1, s1, s1_revision, source="다른 사용자")
    clear_global_main_cases_cache()
    _ran(app.run())

    assert app.selectbox(key=CASE1_SCENARIO).value == s1
    assert app.selectbox(key=CASE1_REVISION).value == s1_revision
    assert _profile(database)[0] == (s1, s1_revision)


def test_labels_sent_back_instead_of_ids_are_not_written(tmp_path: Path) -> None:
    """브라우저가 되보낸 **라벨 글자**는 id 가 아니다 — 콜백은 쓰지 않고 상자는 프로필 값이다."""
    database = tmp_path / "scenario.duckdb"
    _s1, _s1_revision, s2, _s2_older, s2_newer = _two_scenarios(database)
    DuckDBScenarioRepository(database).replace_global_main_case(1, s2, s2_newer, source="테스트")
    clear_global_main_cases_cache()
    version = _version(database)
    script = """
import streamlit as st

import capa_simulation.components.home_main_cases as picker

getattr(picker, st.session_state["callback"])(st.session_state["database_path"], 1)
"""
    for callback, scenario_value, revision_value in (
        ("_save_case_scenario", "증설안", None),
        ("_save_case_revision", s2, "r2 · 증설안 확정"),
        ("_save_case_revision", "증설안", s2_newer),
    ):
        app = AppTest.from_string(script, default_timeout=120)
        app.session_state["database_path"] = str(database)
        app.session_state["callback"] = callback
        app.session_state[CASE1_SCENARIO] = scenario_value
        app.session_state[CASE1_REVISION] = revision_value
        _ran(app.run())
        assert MAIN_CASE_NOTICE_KEY not in app.session_state

    assert _profile(database)[0] == (s2, s2_newer)
    assert _version(database) == version


def test_a_rename_in_another_session_keeps_the_choice(tmp_path: Path) -> None:
    """다른 세션이 시나리오·리비전 이름을 바꿔도 지정은 그대로이고 상자는 새 글자를 보인다.

    상자가 고른 값을 위젯 앞에서 다시 적지 않으면 브라우저가 옛 글자를 되보내 그 글자가 id 자리에
    들어가거나 첫 리비전으로 조용히 되돌아간다. 이름 바꾸기가 올린 version 뒤로는 다시 쓰지 않는다.
    """
    from widget_browser import BrowserChoice

    database = tmp_path / "scenario.duckdb"
    _s1, _s1_revision, s2, s2_older, _s2_newer = _two_scenarios(database)
    repository = DuckDBScenarioRepository(database)
    repository.replace_global_main_case(1, s2, s2_older, source="테스트")
    clear_global_main_cases_cache()
    app = _app(database)
    scenario_box = BrowserChoice(app, "selectbox", CASE1_SCENARIO)
    _ran(scenario_box.start())
    assert scenario_box.wire == "증설안"

    repository.rename_scenario(s2, "증설안 새 이름")
    older_name = next(
        revision.revision_name
        for revision in repository.list_revisions(s2)
        if revision.revision_id == s2_older
    )
    repository.rename_revision(s2_older, "옛 리비전 새 이름", expected_name=older_name)
    clear_global_main_cases_cache()
    version = _version(database)
    for _ in range(3):
        _ran(scenario_box.run())
        assert app.session_state[CASE1_SCENARIO] == s2
        assert app.session_state[CASE1_REVISION] == s2_older

    assert scenario_box.wire == "증설안 새 이름", "상자가 옛 이름을 그대로 보입니다."
    revision_box = BrowserChoice(app, "selectbox", CASE1_REVISION)
    revision_box.sync()
    assert revision_box.wire == "r1 · 옛 리비전 새 이름"
    assert _profile(database)[0] == (s2, s2_older)
    assert _version(database) == version, "고르지 않았는데 공용 프로필을 다시 썼습니다."


def test_overlaps_are_saved_and_named_under_the_boxes(tmp_path: Path) -> None:
    """Case1·Case2 가 같은 짝이어도, Case 가 공식버전과 같은 리비전이어도 저장하고 알리기만 한다."""
    database = tmp_path / "scenario.duckdb"
    s1, s1_revision, s2, _s2_older, s2_newer = _two_scenarios(database)
    repository = DuckDBScenarioRepository(database)
    repository.replace_global_main_case(1, s2, s2_newer, source="테스트")
    clear_global_main_cases_cache()
    app = _ran(_app(database).run())
    assert not any("같은" in text for text in _texts(app))

    _ran(app.selectbox(key=CASE2_SCENARIO).set_value(s2).run())
    assert _profile(database) == ((s2, s2_newer), (s2, s2_newer))
    assert any("Case1 과 Case2 는 같은 시나리오·리비전입니다" in text for text in _texts(app))

    _ran(app.selectbox(key=CASE1_SCENARIO).set_value(s1).run())
    assert _profile(database) == ((s1, s1_revision), (s2, s2_newer))
    assert any("Case1 은 지금 공식버전과 같은 리비전입니다" in text for text in _texts(app))
    assert not any("Case1 과 Case2 는" in text for text in _texts(app))
