# Purpose: Admin 「부하 예외」 탭의 잠금 · 저장 · 바뀐 것 없음 · 비움 판 · 판 충돌 · 겹친 둘째 누름
# · 「이번 데이터에 없음」 · 판 이력 표를 AppTest 로 본다.

"""Admin 「부하 예외」(`components/route_load_exception_admin.py` — AGENTS 6장 「공정별 부하 산출
예외」 (i)).

화면은 Admin Area 페이지 그대로 돌린다(탭 자리 · 닫힌 탭 그리기를 함께 본다). 저장 단추는 C-DEP 의
개발자에게만 열려 개발 자리에서는 잠긴다 — 저장을 보는 시험은 잠금 판정(`write_lock_reason`)을 바꿔
끼워 연다. 합성 공정은 내장 시드 소요기준의 공정(`seed_route_declaration`)과 `DEMO-` 이름뿐이다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alert_marks import flashed
from before_custom_copy import seed_route_declaration
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Multiselect

from capa_simulation.components import route_load_exception_admin as admin
from capa_simulation.components import write_guard
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.sso_identity import NOT_PRODUCTION_REASON
from capa_simulation.navigation import ADMIN_AREA_ROUTE_EXCEPTION_TAB, ADMIN_AREA_TAB_KEY
from capa_simulation.persistence.cache import (
    clear_global_route_load_exceptions_cache,
    load_global_route_load_exceptions,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.frame_contracts import scalar_match_key
from capa_simulation.services.route_load_exceptions import BUFFER_X_CORE_CHIP

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "admin_area.py"
OPEN_KEY = "__route_exception_open__"
PICK = admin.pick_slot(BUFFER_X_CORE_CHIP).key
# 이번 데이터(시드 소요기준)에 없는 합성 공정.
MISSING_PROCESS = "DEMO-예외 공정 없음"


def _script(database: Path) -> str:
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.route_load_exception_admin as admin
import capa_simulation.settings as settings
from capa_simulation.scenario_activation import bootstrap_latest_official_scenario

original_path = settings.DUCKDB_PATH
original_lock = admin.write_lock_reason
settings.DUCKDB_PATH = Path({str(database)!r})
if st.session_state.get({OPEN_KEY!r}):
    admin.write_lock_reason = lambda: None
try:
    bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    source = Path({str(PAGE)!r})
    exec(
        compile(source.read_text(encoding="utf-8"), str(source), "exec"),
        {{"__name__": "__main__"}},
    )
finally:
    admin.write_lock_reason = original_lock
    settings.DUCKDB_PATH = original_path
"""


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "route_exception_admin.duckdb"


def _app(database: Path, *, open_place: bool = False, opened: bool = True) -> AppTest:
    app = AppTest.from_string(_script(database), default_timeout=120)
    app.session_state[OPEN_KEY] = open_place
    if opened:
        app.session_state[ADMIN_AREA_TAB_KEY] = ADMIN_AREA_ROUTE_EXCEPTION_TAB
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _rerun(app: AppTest) -> None:
    app.run()
    assert not app.exception, [item.message for item in app.exception]


def _seed_process() -> str:
    (process,) = seed_route_declaration()
    return process


def _repository(database: Path) -> DuckDBScenarioRepository:
    return DuckDBScenarioRepository(database)


def _seq(database: Path) -> int:
    return _repository(database).load_route_load_exceptions().seq


def _captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.caption]


def _pick(app: AppTest) -> Multiselect[str]:
    return app.multiselect(key=PICK)


def _flashed(app: AppTest) -> list[str]:
    return [str(note.value) for note in flashed(app)]


def _save(app: AppTest) -> None:
    app.button(key=admin.SAVE_BUTTON_KEY).click()
    _rerun(app)


def test_the_tab_stands_and_off_the_production_server_it_is_locked(database: Path) -> None:
    app = _app(database)

    assert "부하 예외 · 선언 없음" in _captions(app)
    pick = app.multiselect(key=PICK)
    assert pick.disabled and pick.help == NOT_PRODUCTION_REASON
    assert pick.label == "Core = Buffer Wafer × Core 구분_Chip · Top_Dummy 0"
    # 선택지는 활성 리비전 소요기준 원본 공정명이다.
    assert _seed_process() in pick.options
    save = app.button(key=admin.SAVE_BUTTON_KEY)
    assert save.disabled and save.help == NOT_PRODUCTION_REASON
    # 판이 없으면 이력 표도 없다.
    assert not [frame for frame in app.dataframe if "산식" in frame.value.columns]


def test_the_lock_is_the_same_judgement_as_the_extra_process_tab() -> None:
    from capa_simulation.components import extra_process_admin

    assert admin.write_lock_reason() == NOT_PRODUCTION_REASON
    assert extra_process_admin.write_lock_reason() == NOT_PRODUCTION_REASON
    assert extra_process_admin.NOT_PRODUCTION_REASON == NOT_PRODUCTION_REASON


def test_a_save_writes_a_new_version_and_clears_the_shared_profile(database: Path) -> None:
    app = _app(database, open_place=True)
    process = _seed_process()
    # 같은 세션의 입장 Summary 확인은 저장 뒤 잊는다(다음 회차가 새 판으로 다시 만든다).
    app.session_state["intro_official_summary"] = {"checked_at": 0.0}
    _pick(app).set_value([process])
    _rerun(app)
    _save(app)

    assert _seq(database) == 1
    assert dict(_repository(database).load_route_load_exceptions().declaration) == {
        process: BUFFER_X_CORE_CHIP
    }
    assert _flashed(app) == [admin.SAVED_MESSAGE.format(seq=1)]
    assert "intro_official_summary" not in app.session_state
    # 공용 프로필을 비웠다 — 같은 회차의 상태 줄 · 다른 세션이 새 판을 읽는다.
    assert load_global_route_load_exceptions(str(database.resolve())).seq == 1
    assert any(text.startswith("부하 예외 · 판 1 · 공정 1 · ") for text in _captions(app))
    assert _pick(app).value == [process]
    history = next(frame.value for frame in app.dataframe if "산식" in frame.value.columns)
    assert list(history.columns) == list(admin.HISTORY_COLUMNS)
    assert list(history["판"]) == ["1"]
    assert list(history["공정"]) == [process]
    assert list(history["산식"]) == ["Core = Buffer Wafer × Core 구분_Chip · Top_Dummy 0"]


def test_an_unchanged_save_writes_nothing(database: Path) -> None:
    app = _app(database, open_place=True)

    _save(app)

    assert _seq(database) == 0
    assert _flashed(app) == [admin.UNCHANGED_MESSAGE]


def test_saving_with_everything_removed_is_one_empty_version(database: Path) -> None:
    app = _app(database, open_place=True)
    process = _seed_process()
    _pick(app).set_value([process])
    _rerun(app)
    _save(app)
    _pick(app).set_value([])
    _rerun(app)
    _save(app)

    state = _repository(database).load_route_load_exceptions()
    assert state.seq == 2 and state.entries == () and state.digest == ""
    assert any(text.startswith("부하 예외 · 판 2 · 공정 0 · ") for text in _captions(app))
    history = next(frame.value for frame in app.dataframe if "산식" in frame.value.columns)
    assert list(history["판"]) == ["2", "1"]
    assert list(history["공정"]) == ["", process]


def test_a_press_after_someone_else_saved_is_refused_and_reloads(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """고르기 칸을 고친 채 남이 새 판을 저장하면 그 칸은 그대로 남고, 누른 저장은 본 판이 지난
    판이라 쓰지 않는다 — 다음 회차가 새 판으로 칸을 다시 채운다(UI-STA-05)."""
    app = _app(database, open_place=True)
    process = _seed_process()
    _pick(app).set_value([process])
    _rerun(app)
    _repository(database).append_route_load_exceptions(
        expected_seq=0,
        entries={MISSING_PROCESS: BUFFER_X_CORE_CHIP},
        applied_by=None,
        source_place="test",
    )
    clear_global_route_load_exceptions_cache()
    _rerun(app)
    # 고친 칸은 남의 저장에 다시 채워지지 않는다.
    assert _pick(app).value == [process]

    _save(app)

    assert _seq(database) == 1
    assert _flashed(app) == [admin.MOVED_MESSAGE.format(seq=1)]
    # 다음 회차(지금)는 새 판으로 칸을 다시 채웠다.
    assert _pick(app).value == [MISSING_PROCESS]

    # 거부를 보기 전에 닿은 같은 단추의 둘째 누름(옛 화면의 고른 값 · 다시 채운 본 판) — 쓰지 않고
    # 그 거부를 다시 알린다(write_guard 의 창 안).
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 600.0)
    _pick(app).set_value([process])
    _save(app)

    assert _seq(database) == 1
    assert _flashed(app) == [admin.MOVED_MESSAGE.format(seq=1)]
    assert _pick(app).value == [MISSING_PROCESS]


def test_an_untouched_picker_follows_someone_elses_save(database: Path) -> None:
    app = _app(database, open_place=True)
    process = _seed_process()
    _repository(database).append_route_load_exceptions(
        expected_seq=0,
        entries={f"  {process.upper()} ": BUFFER_X_CORE_CHIP},
        applied_by=None,
        source_place="test",
    )
    clear_global_route_load_exceptions_cache()
    _rerun(app)

    # 견줌 키가 같은 이번 데이터 표기로 채운다 — 같은 공정이 선택지에 두 번 서지 않는다.
    assert _pick(app).value == [process]
    assert not any(admin.MISSING_MARK in option for option in _pick(app).options)
    # 그 판에서 고친 것 없이 누르면 바뀐 것이 없다.
    _save(app)
    assert _seq(database) == 1
    assert _flashed(app) == [admin.UNCHANGED_MESSAGE]


def test_a_second_press_of_the_same_save_reports_success_not_a_conflict(database: Path) -> None:
    """같은 단추의 빠른 두 번 누름 — 둘째 회차가 첫 저장 전의 본 판을 들고 오면 저장소가 판 대조로
    거절하지만, 제 저장 짝이 그 거절을 알아보고 성공을 다시 알린다(새 판은 하나)."""
    app = _app(database, open_place=True)
    process = _seed_process()
    _pick(app).set_value([process])
    _rerun(app)
    _save(app)
    # 첫 회차가 본 판을 옮기기 전에 끊긴 둘째 회차 — 본 판은 저장 전 그대로다.
    app.session_state[admin.SEEDED_KEY] = (0, ())
    _save(app)

    assert _seq(database) == 1
    assert _flashed(app) == [admin.SAVED_MESSAGE.format(seq=1)]
    assert _pick(app).value == [process]


def test_a_declared_process_missing_from_this_data_stays_with_a_marker(database: Path) -> None:
    _repository(database).initialize()
    _repository(database).append_route_load_exceptions(
        expected_seq=0,
        entries={MISSING_PROCESS: BUFFER_X_CORE_CHIP},
        applied_by=None,
        source_place="test",
    )
    app = _app(database)

    pick = _pick(app)
    assert pick.value == [MISSING_PROCESS]
    assert f"{MISSING_PROCESS} {admin.MISSING_MARK}" in pick.options


def test_a_closed_tab_still_draws_the_picker_but_not_the_history(database: Path) -> None:
    _repository(database).initialize()
    _repository(database).append_route_load_exceptions(
        expected_seq=0,
        entries={_seed_process(): BUFFER_X_CORE_CHIP},
        applied_by=None,
        source_place="test",
    )
    app = _app(database, opened=False)

    # 고르기 칸이 닫힌 회차에도 서야 값이 남는다(Streamlit 이 그리지 않은 위젯 값을 버린다).
    assert _pick(app).value == [_seed_process()]
    assert not [frame for frame in app.dataframe if "산식" in frame.value.columns]


def test_option_texts_show_the_display_name_with_the_original_and_stay_unique() -> None:
    labels = ProcessLabels(version=1, labels={"DEMO-A": "DEMO-B"})
    names, present = admin.option_names(["DEMO-A", "DEMO-B", " demo-b "], ["DEMO-Z"])

    assert names == ["DEMO-A", "DEMO-B", "DEMO-Z"]
    texts = admin.option_texts(names, labels=labels, present_keys=present)
    assert texts == {
        "DEMO-A": "DEMO-B (DEMO-A)",
        "DEMO-B": "DEMO-B",
        "DEMO-Z": f"DEMO-Z {admin.MISSING_MARK}",
    }
    clash = ProcessLabels(version=1, labels={"DEMO-A": "DEMO-C", "DEMO-D": "DEMO-C"})
    texts = admin.option_texts(
        ["DEMO-A", "DEMO-C (DEMO-A)"], labels=clash, present_keys=frozenset()
    )
    assert len(set(texts.values())) == 2


def test_status_line_carries_values_only() -> None:
    from datetime import datetime

    from capa_simulation.persistence.models import RouteLoadExceptionProfile

    empty = RouteLoadExceptionProfile(
        seq=0, created_at=None, applied_by=None, entries=(), digest=""
    )
    assert admin.status_line(empty) == "부하 예외 · 선언 없음"
    one = RouteLoadExceptionProfile(
        seq=3,
        created_at=datetime(2026, 11, 23, 9, 12),
        applied_by="DEMO-user",
        entries=(("DEMO-P1", BUFFER_X_CORE_CHIP), ("DEMO-P2", BUFFER_X_CORE_CHIP)),
        digest="d",
    )
    assert admin.status_line(one) == "부하 예외 · 판 3 · 공정 2 · 11-23 09:12"


def test_two_spellings_of_one_declared_process_seed_one_choice(database: Path) -> None:
    """견줌 키가 같은 두 표기로 저장된 선언(앞뒤 공백 · 대소문자만 다름)은 고르기 칸에 하나로 선다 —
    고른 값이 늘 선택지 안이라 다중 선택이 멈추지 않는다."""
    _repository(database).initialize()
    _repository(database).append_route_load_exceptions(
        expected_seq=0,
        entries={
            MISSING_PROCESS: BUFFER_X_CORE_CHIP,
            f" {MISSING_PROCESS.lower()} ": BUFFER_X_CORE_CHIP,
        },
        applied_by=None,
        source_place="test",
    )
    app = _app(database)

    (chosen,) = _pick(app).value
    assert scalar_match_key(chosen) == scalar_match_key(MISSING_PROCESS)
    assert [option for option in _pick(app).options if admin.MISSING_MARK in option] == [
        f"{chosen} {admin.MISSING_MARK}"
    ]
