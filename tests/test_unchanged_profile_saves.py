# Purpose: 바꾼 것 없는 공용 저장의 「그대로」 알림과 쓰지 않은 저장 회차의 안내 줄을 잰다.

"""표시순서 직접 편집·확보율 보정·공지·Top5 구간·주요공정 프리셋·선행 B/O·선행 입고 실적·
공정별 Cut-off.

2026-11-01 사용자 답(개선 I5 를 일곱 자리로 넓힘). I5 가 Proc Rename·판정 기준에 둔 꼴과 같다 — 최신
저장본을 보고 누른 저장의 값이 그 저장본과 같으면 저장소에 가지 않고 그 폼 알림 칸에 「바뀐 것이
없습니다 — …」 를 적는다. 변경 메모만 적은 저장도 같고, 값을 고치면 평소대로 쓴다. 저장본이 없는
v0 의 첫 저장은 쓴다. 느린 둘째 누름(새로 그린 화면에 닿은 같은 값)은 창 안이면 방금 성공을 다시
낸다(`write_guard.held_notice`).

AppTest 회차 사이 시간이 들쭉날쭉해 둘째 누름의 창(`TRAILING_PRESS_SECONDS`)은 시험이 정한다 —
「바뀐 것이 없습니다」 를 보는 시험은 0, 느린 둘째 누름 시험은 길게.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alert_marks import infos, place_errors, successes
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import TextInput

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.cutoff_management import (
    CUTOFF_DRAFT_KEY,
    CUTOFF_UNCHANGED_MESSAGE,
)
from capa_simulation.components.display_order_management import (
    DISPLAY_ORDER_EDITOR_KEY,
    DISPLAY_ORDER_SAVED_MESSAGE,
    DISPLAY_ORDER_UNCHANGED_MESSAGE,
)
from capa_simulation.components.home_preference import (
    ADVANCE_EDITOR_KEY,
    ADVANCE_NOTE_KEY,
    ADVANCE_SHIPMENT_EDITOR_KEY,
    EXECUTION_BASE_VERSION_KEY,
    EXECUTION_EDITOR_KEY,
    EXECUTION_NOTE_KEY,
    EXECUTION_SAVED_MESSAGE,
    EXECUTION_UNCHANGED_MESSAGE,
    KEY_PROCESS_UNCHANGED_MESSAGE,
    SUMMARY_UNCHANGED_MESSAGE,
    TOP5_SAVED_MESSAGE,
    TOP5_UNCHANGED_MESSAGE,
)
from capa_simulation.persistence.cache import (
    clear_global_advance_load_cache,
    clear_global_advance_shipment_cache,
    clear_global_display_order_cache,
    clear_global_execution_capacity_cache,
    clear_global_key_process_cache,
    clear_global_summary_note_cache,
    clear_global_top5_band_cache,
    clear_scenario_repository,
)
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_process_cutoff_cache,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.monthly_amount import same_monthly_amounts

ADVANCE_LOAD_SAVED = "선행 B/O 를 공용 설정으로 저장했습니다."
ADVANCE_LOAD_UNCHANGED = (
    "바뀐 것이 없습니다 — 보이는 달의 값이 지금 선행 B/O 그대로라 새 버전을 만들지 않았습니다."
)
ADVANCE_SHIPMENT_SAVED = "선행 입고 실적을 공용 설정으로 저장했습니다."
ADVANCE_SHIPMENT_UNCHANGED = (
    "바뀐 것이 없습니다 — 보이는 달의 값이 지금 선행 입고 실적 그대로라 새 버전을 만들지 "
    "않았습니다."
)


def _clear_caches() -> None:
    for clear in (
        clear_global_display_order_cache,
        clear_global_execution_capacity_cache,
        clear_global_summary_note_cache,
        clear_global_top5_band_cache,
        clear_global_key_process_cache,
        clear_global_advance_load_cache,
        clear_global_advance_shipment_cache,
        clear_scenario_repository,
    ):
        clear()


@pytest.fixture
def repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[DuckDBScenarioRepository]:
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    store = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    store.initialize()
    _clear_caches()
    yield store
    _clear_caches()


def _app(repository: DuckDBScenarioRepository, body: str) -> AppTest:
    script = f"""
import pandas as pd
import streamlit as st

from capa_simulation.components import home_preference as preference
from capa_simulation.components.process_labels import process_labels_from_rules
from capa_simulation.persistence.cache import (
    get_scenario_repository,
    load_global_advance_load,
    load_global_advance_shipment,
    load_global_execution_capacity,
    load_global_summary_note,
    load_global_top5_band,
)

database_path = {str(repository.database_path)!r}
{body}
"""
    app = AppTest.from_string(script, default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _press(app: AppTest, label: str) -> AppTest:
    next(button for button in app.button if button.label == label).click()
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _pressed_states(app: AppTest, label: str) -> WidgetStates:
    """`label` 저장 단추를 누른 화면의 위젯 값(느린 둘째 누름이 그대로 다시 보낸다)."""
    next(button for button in app.button if button.label == label).click()
    return app._tree.get_widget_states()


def _infos(app: AppTest) -> list[str]:
    return [str(item.value) for item in infos(app)]


def _successes(app: AppTest) -> list[str]:
    return [str(item.value) for item in successes(app)]


def _errors(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.error]


def _memo(app: AppTest) -> TextInput:
    """변경 메모 칸 — 화면마다 key 가 달라 라벨로 찾는다."""
    return next(field for field in app.text_input if field.label == "변경 메모")


def _edit_cells(app: AppTest, key: str, edits: dict[int, dict[str, object]]) -> None:
    """편집표 `key` 의 칸을 고친 것처럼 채운다(다음 회차가 그 편집을 보낸다)."""
    app.session_state[key] = {"edited_rows": edits, "added_rows": [], "deleted_rows": []}


# ----------------------------------------------------------------------- 표시순서 직접 편집

_DISPLAY_ORDER = """
from pathlib import Path

from capa_simulation.components.display_order_management import render_display_order_management

repository = get_scenario_repository(database_path)
render_display_order_management(repository)
"""


def _seed_display_order(repository: DuckDBScenarioRepository) -> None:
    repository.initialize_global_display_order(
        pd.DataFrame(
            {
                "페이지 구분": ["생산 계획"] * 3,
                "탭 구분": ["수율"] * 3,
                "정렬우선순위": [1, 1, 1],
                "분류컬럼": ["제품정보"] * 3,
                "정렬방식": ["사용자지정"] * 3,
                "분류값": ["DEMO_A", "DEMO_B", "DEMO_C"],
                "값표시순서": [1, 2, 3],
                "활성여부": ["Y", "Y", "Y"],
            }
        )
    )
    clear_global_display_order_cache()


def test_a_display_order_save_without_changes_makes_no_new_version(
    repository: DuckDBScenarioRepository,
) -> None:
    """고친 칸 없이 누른 「공용 표시순서 저장」 은 새 버전 없이 머리 알림 칸에 「바뀐 것이
    없습니다」 를 띄운다. 변경 메모만 적어도 같고, 칸을 고치면 평소대로 저장한다."""
    _seed_display_order(repository)
    app = _app(repository, _DISPLAY_ORDER)
    assert repository.load_global_display_order().version == 1

    app = _press(app, "공용 표시순서 저장")
    assert _infos(app) == [DISPLAY_ORDER_UNCHANGED_MESSAGE]
    assert not successes(app) and not place_errors(app), _errors(app)
    assert repository.load_global_display_order().version == 1

    app.text_input(key="display_order_note").set_value("메모만 적음")
    app = _press(app, "공용 표시순서 저장")
    assert _infos(app) == [DISPLAY_ORDER_UNCHANGED_MESSAGE]
    assert repository.load_global_display_order().version == 1

    _edit_cells(app, f"{DISPLAY_ORDER_EDITOR_KEY}::생산 계획::수율", {1: {"값표시순서": 9}})
    app = _press(app, "공용 표시순서 저장")
    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == [DISPLAY_ORDER_SAVED_MESSAGE]
    stored = repository.load_global_display_order()
    assert stored.version == 2
    assert stored.rules.loc[stored.rules["분류값"].eq("DEMO_B"), "값표시순서"].tolist() == [9]


def test_a_saved_display_order_note_is_not_carried_into_the_next_save(
    repository: DuckDBScenarioRepository,
) -> None:
    """저장에 성공하면 변경 메모 칸이 빈다 — 다시 적지 않은 메모가 값만 고친 다음 저장의 기록에
    실렸다(2026-11-08 점검 u3-m2). 바꾼 것 없는 저장은 쓰지 않아 칸을 지킨다."""
    _seed_display_order(repository)
    app = _app(repository, _DISPLAY_ORDER)
    editor = f"{DISPLAY_ORDER_EDITOR_KEY}::생산 계획::수율"

    _memo(app).set_value("메모만 적음")
    app = _press(app, "공용 표시순서 저장")
    assert _infos(app) == [DISPLAY_ORDER_UNCHANGED_MESSAGE]
    assert _memo(app).value == "메모만 적음"

    _edit_cells(app, editor, {1: {"값표시순서": 9}})
    _memo(app).set_value("첫 메모")
    app = _press(app, "공용 표시순서 저장")
    assert _memo(app).value == ""
    stored = repository.load_global_display_order()
    assert (stored.version, stored.source) == (2, "첫 메모")

    _edit_cells(app, editor, {1: {"값표시순서": 8}})
    app = _press(app, "공용 표시순서 저장")
    assert _memo(app).value == ""
    stored = repository.load_global_display_order()
    assert stored.version == 3
    assert stored.source == "웹 직접 편집 · 생산 계획/수율"


def test_a_slow_second_press_of_the_display_order_save_repeats_the_success(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """느린 두 번 누름(둘째 누름이 첫 저장 뒤 새로 그린 표에 닿는다 — 같은 표라 바뀐 것이 없다)은
    「바뀐 것이 없습니다」 로 방금 성공을 덮지 않는다(write_guard.held_notice 창 안)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    _seed_display_order(repository)
    app = _app(repository, _DISPLAY_ORDER)
    _edit_cells(app, f"{DISPLAY_ORDER_EDITOR_KEY}::생산 계획::수율", {1: {"값표시순서": 9}})
    app = _press(app, "공용 표시순서 저장")
    assert repository.load_global_display_order().version == 2

    app = _press(app, "공용 표시순서 저장")

    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == [DISPLAY_ORDER_SAVED_MESSAGE]
    assert repository.load_global_display_order().version == 2


# ----------------------------------------------------------------------------- 확보율 보정

_EXECUTION = """
preference._render_execution_editor(
    months=[202607, 202608],
    execution_profile=load_global_execution_capacity(database_path),
    process_options=["DEMO_A", "DEMO_B"],
    process_labels=process_labels_from_rules(pd.DataFrame()),
    unmatched=pd.DataFrame({"생산계획년월": [202609], "공정": ["DEMO_Z"]}),
    clamped=pd.DataFrame(),
    database_path=database_path,
)
"""


def _execution_rows(records: list[tuple[int, str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=["생산계획년월", "공정", "증감 확보율", "비고"])


def test_an_execution_capacity_save_without_changes_makes_no_new_version(
    repository: DuckDBScenarioRepository,
) -> None:
    """고친 칸 없이 누른 「확보율 보정 저장」 은 새 버전 없이 「바뀐 것이 없습니다」 를 띄우고,
    누르지 않은 회차가 그리던 짝 없는 행 안내도 그대로 선다. 메모만 적어도 같고, 칸을 고치면
    저장한다."""
    repository.replace_global_execution_capacity(
        _execution_rows([(202607, "DEMO_A", -10.0, "셋업")]), source="처음 저장"
    )
    clear_global_execution_capacity_cache()
    app = _app(repository, _EXECUTION)
    assert any("짝이 없어" in str(item.value) for item in app.warning)

    app = _press(app, "확보율 보정 저장")
    assert _infos(app) == [EXECUTION_UNCHANGED_MESSAGE]
    assert not successes(app) and not place_errors(app), _errors(app)
    assert any("짝이 없어" in str(item.value) for item in app.warning)

    app.text_input(key=EXECUTION_NOTE_KEY).set_value("메모만 적음")
    app = _press(app, "확보율 보정 저장")
    assert _infos(app) == [EXECUTION_UNCHANGED_MESSAGE]
    profile = repository.load_global_execution_capacity()
    assert (profile.version, profile.source) == (1, "처음 저장")

    _edit_cells(app, EXECUTION_EDITOR_KEY, {0: {"증감 확보율": -12.5}})
    app = _press(app, "확보율 보정 저장")
    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == [EXECUTION_SAVED_MESSAGE]
    profile = repository.load_global_execution_capacity()
    assert profile.version == 2
    assert profile.rows["증감 확보율"].tolist() == [-12.5]


def test_a_saved_execution_note_is_not_carried_into_the_next_save(
    repository: DuckDBScenarioRepository,
) -> None:
    """저장에 성공하면 변경 메모 칸이 빈다 — 다시 적지 않은 메모가 값만 고친 다음 저장의 기록에
    실렸다(2026-11-08 점검 u3-02). 바꾼 것 없는 저장은 쓰지 않아 칸을 지킨다."""
    repository.replace_global_execution_capacity(
        _execution_rows([(202607, "DEMO_A", -10.0, "")]), source="처음 저장"
    )
    clear_global_execution_capacity_cache()
    app = _app(repository, _EXECUTION)

    _memo(app).set_value("메모만 적음")
    app = _press(app, "확보율 보정 저장")
    assert _infos(app) == [EXECUTION_UNCHANGED_MESSAGE]
    assert _memo(app).value == "메모만 적음"

    _edit_cells(app, EXECUTION_EDITOR_KEY, {0: {"증감 확보율": -12.5}})
    _memo(app).set_value("첫 메모")
    app = _press(app, "확보율 보정 저장")
    assert _memo(app).value == ""
    profile = repository.load_global_execution_capacity()
    assert (profile.version, profile.source) == (2, "첫 메모")

    _edit_cells(app, EXECUTION_EDITOR_KEY, {0: {"증감 확보율": -13.5}})
    app = _press(app, "확보율 보정 저장")
    assert _memo(app).value == ""
    profile = repository.load_global_execution_capacity()
    assert (profile.version, profile.source) == (3, "웹 직접 편집")


def test_a_refused_execution_save_keeps_the_typed_note(
    repository: DuckDBScenarioRepository,
) -> None:
    """남의 저장에 거부된 저장은 적은 메모를 지우지 않는다."""
    repository.replace_global_execution_capacity(
        _execution_rows([(202607, "DEMO_A", -10.0, "")]), source="처음 저장"
    )
    clear_global_execution_capacity_cache()
    app = _app(repository, _EXECUTION)
    repository.replace_global_execution_capacity(
        _execution_rows([(202607, "DEMO_A", -11.0, "")]), source="다른 세션", expected_version=1
    )
    clear_global_execution_capacity_cache()

    _edit_cells(app, EXECUTION_EDITOR_KEY, {0: {"증감 확보율": -12.5}})
    _memo(app).set_value("거부될 메모")
    app = _press(app, "확보율 보정 저장")

    assert any("다른 사용자가 먼저" in text for text in _errors(app)), _errors(app)
    assert _memo(app).value == "거부될 메모"


def test_a_double_press_of_the_execution_save_that_cut_the_first_run_still_empties_the_note(
    repository: DuckDBScenarioRepository,
) -> None:
    """둘째 누름이 첫 저장의 뒷정리를 끊으면 칸을 비울 표지가 없다 — 제 저장임을 알아본 둘째 회차가
    칸을 비운다. AppTest 는 두 요청을 겹칠 수 없어 누른 화면의 위젯 값과 끊긴 회차가 남긴 본
    version 을 되살려 한 번 더 보낸다."""
    repository.replace_global_execution_capacity(
        _execution_rows([(202607, "DEMO_A", -10.0, "")]), source="처음 저장"
    )
    clear_global_execution_capacity_cache()
    app = _app(repository, _EXECUTION)
    _edit_cells(app, EXECUTION_EDITOR_KEY, {0: {"증감 확보율": -12.5}})
    _memo(app).set_value("첫 메모")
    pressed = _pressed_states(app, "확보율 보정 저장")
    app.run()
    assert repository.load_global_execution_capacity().version == 2

    app.session_state[EXECUTION_BASE_VERSION_KEY] = 1
    app._run(widget_state=pressed)

    assert not app.exception, [item.message for item in app.exception]
    assert _successes(app) == [EXECUTION_SAVED_MESSAGE]
    assert _memo(app).value == ""
    profile = repository.load_global_execution_capacity()
    assert (profile.version, profile.source) == (2, "첫 메모")


def test_a_second_press_of_the_execution_save_keeps_the_note_it_did_not_save(
    repository: DuckDBScenarioRepository,
) -> None:
    """앞 회차가 끝나기 전에 온 다른 메모의 둘째 누름은 제 저장으로 판정되어 쓰이지 않는다 — 그
    메모는 칸에 남긴다(판정 기준과 같은 꼴)."""
    repository.replace_global_execution_capacity(
        _execution_rows([(202607, "DEMO_A", -10.0, "")]), source="처음 저장"
    )
    clear_global_execution_capacity_cache()
    app = _app(repository, _EXECUTION)
    _edit_cells(app, EXECUTION_EDITOR_KEY, {0: {"증감 확보율": -12.5}})
    _memo(app).set_value("첫 메모")
    app = _press(app, "확보율 보정 저장")
    assert _memo(app).value == ""

    app.session_state[EXECUTION_BASE_VERSION_KEY] = 1
    _edit_cells(app, EXECUTION_EDITOR_KEY, {0: {"증감 확보율": -13.5}})
    _memo(app).set_value("둘째 메모")
    app = _press(app, "확보율 보정 저장")

    assert _successes(app) == [EXECUTION_SAVED_MESSAGE]
    assert _memo(app).value == "둘째 메모"
    profile = repository.load_global_execution_capacity()
    assert (profile.version, profile.source) == (2, "첫 메모")


def test_a_slow_second_press_of_the_execution_save_repeats_the_success(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """느린 두 번 누름은 「바뀐 것이 없습니다」 로 방금 성공을 덮지 않는다
    (write_guard.held_notice)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository.replace_global_execution_capacity(
        _execution_rows([(202607, "DEMO_A", -10.0, "")]), source="처음 저장"
    )
    clear_global_execution_capacity_cache()
    app = _app(repository, _EXECUTION)
    _edit_cells(app, EXECUTION_EDITOR_KEY, {0: {"증감 확보율": -3.0}})
    app = _press(app, "확보율 보정 저장")
    assert repository.load_global_execution_capacity().version == 2

    app = _press(app, "확보율 보정 저장")

    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == [EXECUTION_SAVED_MESSAGE]
    assert repository.load_global_execution_capacity().version == 2


# ---------------------------------------------------------------------------- 공지

_SUMMARY = """
preference._render_summary_note_editor(
    summary_profile=load_global_summary_note(database_path), database_path=database_path
)
"""


def test_a_summary_note_save_without_changes_makes_no_new_version(
    repository: DuckDBScenarioRepository,
) -> None:
    """지금 공지 그대로 누른 「공지 저장」 은 새 버전 없이 「바뀐 것이 없습니다」 다. 글을 고치면
    저장한다."""
    repository.replace_global_summary_note("DEMO 잠정 계획", source="처음 저장")
    clear_global_summary_note_cache()
    app = _app(repository, _SUMMARY)

    app = _press(app, "공지 저장")
    assert _infos(app) == [SUMMARY_UNCHANGED_MESSAGE]
    assert not successes(app) and not place_errors(app), _errors(app)
    stored = repository.load_global_summary_note()
    assert (stored.version, stored.source) == (1, "처음 저장")

    app.text_area[0].set_value("DEMO 확정 계획")
    app = _press(app, "공지 저장")
    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == ["공지를 저장했습니다."]
    stored = repository.load_global_summary_note()
    assert (stored.version, stored.note) == (2, "DEMO 확정 계획")


def test_a_slow_second_press_of_the_summary_note_repeats_the_success(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """느린 두 번 누름(둘째 누름이 누른 화면의 글을 한 번 더 보낸다)은 새로 그린 저장본과 같아 바뀐
    것이 없지만, 창 안이라 방금 성공을 그대로 둔다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository.replace_global_summary_note("DEMO 잠정 계획", source="처음 저장")
    clear_global_summary_note_cache()
    app = _app(repository, _SUMMARY)
    app.text_area[0].set_value("DEMO 확정 계획")
    pressed = _pressed_states(app, "공지 저장")
    app.run()
    assert repository.load_global_summary_note().version == 2

    app._run(widget_state=pressed)

    assert not app.exception, [item.message for item in app.exception]
    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == ["공지를 저장했습니다."]
    assert repository.load_global_summary_note().version == 2


# ------------------------------------------------------------------------------ Top5 구간

_TOP5 = """
preference._render_top5_band_editor(
    top5_band_profile=load_global_top5_band(database_path), database_path=database_path
)
"""


def test_a_top5_band_save_without_changes_makes_no_new_version(
    repository: DuckDBScenarioRepository,
) -> None:
    """지금 구간 그대로 누른 「확보율 구간 저장」 은 새 버전 없이 「바뀐 것이 없습니다」 다 — 퍼센트
    칸을 오간 끝자리(0.7 → 70.0 → 0.7000…01)는 바뀐 것이 아니다. 하한을 고치면 저장한다."""
    repository.replace_global_top5_band(0.7, 1.3, source="처음 저장")
    clear_global_top5_band_cache()
    app = _app(repository, _TOP5)
    assert app.number_input[0].value == pytest.approx(70.0)

    app = _press(app, "확보율 구간 저장")
    assert _infos(app) == [TOP5_UNCHANGED_MESSAGE]
    assert not successes(app) and not place_errors(app), _errors(app)
    stored = repository.load_global_top5_band()
    assert (stored.version, stored.source) == (1, "처음 저장")

    app.number_input[0].set_value(60.0)
    app = _press(app, "확보율 구간 저장")
    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == [TOP5_SAVED_MESSAGE]
    stored = repository.load_global_top5_band()
    assert stored.version == 2
    assert stored.min_rate == pytest.approx(0.6)


def test_a_slow_second_press_of_the_top5_band_repeats_the_success(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """느린 두 번 누름(둘째 누름이 누른 화면의 구간을 한 번 더 보낸다)은 새로 그린 저장본과 같아
    바뀐 것이 없지만, 창 안이라 방금 성공을 그대로 둔다(write_guard.held_notice — 공지와
    같다)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository.replace_global_top5_band(0.7, 1.3, source="처음 저장")
    clear_global_top5_band_cache()
    app = _app(repository, _TOP5)
    app.number_input[0].set_value(60.0)
    pressed = _pressed_states(app, "확보율 구간 저장")
    app.run()
    assert repository.load_global_top5_band().version == 2

    app._run(widget_state=pressed)

    assert not app.exception, [item.message for item in app.exception]
    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == [TOP5_SAVED_MESSAGE]
    assert repository.load_global_top5_band().version == 2


# ------------------------------------------------------------------------- 주요공정 프리셋

_KEY_PROCESS = """
preference._render_key_process_editor(
    process_options=["DEMO-A", "DEMO-B"],
    process_labels=process_labels_from_rules(pd.DataFrame()),
    database_path=database_path,
)
"""


def test_a_key_process_preset_save_without_changes_makes_no_new_version(
    repository: DuckDBScenarioRepository,
) -> None:
    """고칠 프리셋의 이름·공정 그대로 누른 「프리셋 저장」 은 새 버전 없이 「바뀐 것이 없습니다」
    다. 공정 차례만 바꿔도 바뀐 것이다(고른 차례가 행 순서) — 저장한다."""
    repository.replace_global_key_process_presets(
        [("A 그룹", ("DEMO-A", "DEMO-B"))], source="처음 저장"
    )
    clear_global_key_process_cache()
    app = _app(repository, _KEY_PROCESS)

    app = _press(app, "프리셋 저장")
    assert _infos(app) == [KEY_PROCESS_UNCHANGED_MESSAGE]
    assert not successes(app) and not place_errors(app), _errors(app)
    stored = repository.load_global_key_process()
    assert (stored.version, stored.source) == (1, "처음 저장")

    app.multiselect[0].set_value(["DEMO-B", "DEMO-A"])
    app = _press(app, "프리셋 저장")
    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == ["프리셋 「A 그룹」을 저장했습니다."]
    stored = repository.load_global_key_process()
    assert stored.version == 2
    assert stored.presets == (("A 그룹", ("DEMO-B", "DEMO-A")),)


def test_a_slow_second_press_of_a_preset_save_repeats_the_success(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """고친 프리셋 저장의 느린 두 번 누름은 새로 그린 저장본과 같아 바뀐 것이 없지만, 창 안이라 방금
    성공(이름 있는 알림)을 그대로 둔다(write_guard.held_notice)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository.replace_global_key_process_presets([("A 그룹", ("DEMO-A",))], source="처음 저장")
    clear_global_key_process_cache()
    app = _app(repository, _KEY_PROCESS)
    app.multiselect[0].set_value(["DEMO-A", "DEMO-B"])
    pressed = _pressed_states(app, "프리셋 저장")
    app.run()
    assert repository.load_global_key_process().version == 2

    app._run(widget_state=pressed)

    assert not app.exception, [item.message for item in app.exception]
    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == ["프리셋 「A 그룹」을 저장했습니다."]
    assert repository.load_global_key_process().version == 2


def test_an_unchanged_preset_save_right_after_a_promotion_still_says_so(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「기본으로」·「삭제」 는 프리셋 저장과 같은 알림 칸에 적는다. 그 직후(느린 둘째 누름의 창
    안) 고치지 않고 누른 「프리셋 저장」 은 방금 저장의 둘째 누름이 아니다 — 「기본으로」 알림을
    다시 그리지 않고 「바뀐 것이 없습니다」 를 세운다(2026-11-01 리뷰 — 칸 이름만 보면 그 알림을
    방금 저장의 성공으로 읽어 아무것도 알리지 않았다)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository.replace_global_key_process_presets(
        [("A 그룹", ("DEMO-A",)), ("B 그룹", ("DEMO-B",))], source="처음 저장"
    )
    clear_global_key_process_cache()
    app = _app(repository, _KEY_PROCESS)
    app.selectbox[0].set_value("B 그룹").run()
    app.button(key="home_key_process_preset_default").click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert _successes(app) == ["「B 그룹」을 기본 프리셋으로 옮겼습니다."]
    assert repository.load_global_key_process().version == 2

    app = _press(app, "프리셋 저장")

    assert _infos(app) == [KEY_PROCESS_UNCHANGED_MESSAGE]
    assert not successes(app) and not place_errors(app), _successes(app) + _errors(app)
    stored = repository.load_global_key_process()
    assert (stored.version, stored.preset_names) == (2, ("B 그룹", "A 그룹"))


def test_a_new_preset_is_never_an_unchanged_save(repository: DuckDBScenarioRepository) -> None:
    """「＋ 새 프리셋」 은 늘 새로 넣는 저장이라 견주지 않는다 — 저장본 없는 v0 의 첫 프리셋도
    쓴다."""
    app = _app(repository, _KEY_PROCESS)
    app.text_input[0].set_value("B 그룹")
    app.multiselect[0].set_value(["DEMO-A"])

    app = _press(app, "프리셋 저장")

    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    stored = repository.load_global_key_process()
    assert (stored.version, stored.preset_names) == (1, ("B 그룹",))


# ------------------------------------------------------------------- 선행 B/O · 선행 입고 실적

_ADVANCE_LOAD = """
preference._render_advance_editor(
    months=[202610, 202611],
    month_labels=["26.10", "26.11"],
    advance_profile=load_global_advance_load(database_path),
    database_path=database_path,
)
"""
_ADVANCE_SHIPMENT = """
preference.render_advance_shipment_editor(
    months=[202610, 202611],
    month_labels=["26.10", "26.11"],
    advance_shipment_profile=load_global_advance_shipment(database_path),
    database_path=database_path,
)
"""


def _outside_marks(app: AppTest) -> list[tuple[str, str]]:
    """조회기간 밖 저장분의 칸 머리 표지(배지)와 그 풍선. 표 밑 안내 글은 없다(설계 규칙
    UI-TXT-01 · AMB-02 — 숨은 데이터 안내는 칸 머리 표지 + 풍선, 2026-11-04)."""
    assert not [caption.value for caption in app.caption if "조회기간 밖" in caption.value]
    return [
        (str(item.value), str(item.proto.help))
        for item in app.markdown
        if "조회기간 밖" in str(item.value)
    ]


def test_an_advance_load_save_without_changes_makes_no_new_version(
    repository: DuckDBScenarioRepository,
) -> None:
    """보이는 달의 값 그대로 누른 「선행 B/O 저장」 은 새 버전 없이 「바뀐 것이 없습니다」 를
    띄우고, 조회기간 밖 저장분 표지도 누르지 않은 회차처럼 선다. 메모만 적어도 같고, 칸을 고치면
    저장한다."""
    repository.replace_global_advance_load(
        pd.DataFrame({"생산계획년월": [202610, 202612], "선행 물량": [1.25, 3.0]}),
        source="처음 저장",
    )
    clear_global_advance_load_cache()
    app = _app(repository, _ADVANCE_LOAD)
    shown = _outside_marks(app)
    assert shown == [
        (
            ":gray-badge[:material/visibility_off: 조회기간 밖 1개월]",
            "26.12 — 표에 보이지 않지만 그대로 남고, 이 표를 저장해도 지워지지 않습니다.",
        )
    ], shown

    app = _press(app, "선행 B/O 저장")
    assert _infos(app) == [ADVANCE_LOAD_UNCHANGED]
    assert not successes(app) and not place_errors(app), _errors(app)
    assert _outside_marks(app) == shown

    app.text_input(key=ADVANCE_NOTE_KEY).set_value("메모만 적음")
    app = _press(app, "선행 B/O 저장")
    assert _infos(app) == [ADVANCE_LOAD_UNCHANGED]
    stored = repository.load_global_advance_load()
    assert (stored.version, stored.source) == (1, "처음 저장")

    _edit_cells(app, ADVANCE_EDITOR_KEY, {0: {"26.11": 2.0}})
    app = _press(app, "선행 B/O 저장")
    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == [ADVANCE_LOAD_SAVED]
    stored = repository.load_global_advance_load()
    assert stored.version == 2
    assert stored.rows["생산계획년월"].tolist() == [202610, 202611, 202612]


def test_an_advance_shipment_save_without_changes_makes_no_new_version(
    repository: DuckDBScenarioRepository,
) -> None:
    """선행 입고 실적도 선행 B/O 와 같은 규칙이다 — 그대로 누르면 새 버전 없이 「바뀐 것이
    없습니다」, 칸을 고치면 저장한다."""
    repository.replace_global_advance_shipment(
        pd.DataFrame({"생산계획년월": [202611], "선행 입고": [-0.5]}), source="처음 저장"
    )
    clear_global_advance_shipment_cache()
    app = _app(repository, _ADVANCE_SHIPMENT)

    app = _press(app, "선행 입고 저장")
    assert _infos(app) == [ADVANCE_SHIPMENT_UNCHANGED]
    assert not successes(app) and not place_errors(app), _errors(app)
    stored = repository.load_global_advance_shipment()
    assert (stored.version, stored.source) == (1, "처음 저장")

    _edit_cells(app, ADVANCE_SHIPMENT_EDITOR_KEY, {0: {"26.10": 1.5}})
    app = _press(app, "선행 입고 저장")
    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == [ADVANCE_SHIPMENT_SAVED]
    stored = repository.load_global_advance_shipment()
    assert stored.version == 2
    assert stored.rows["생산계획년월"].tolist() == [202610, 202611]


def test_a_slow_second_press_of_the_advance_load_repeats_the_success(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """느린 두 번 누름은 「바뀐 것이 없습니다」 로 방금 성공을 덮지 않는다
    (write_guard.held_notice)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository.replace_global_advance_load(
        pd.DataFrame({"생산계획년월": [202610], "선행 물량": [1.0]}), source="처음 저장"
    )
    clear_global_advance_load_cache()
    app = _app(repository, _ADVANCE_LOAD)
    _edit_cells(app, ADVANCE_EDITOR_KEY, {0: {"26.10": 2.0}})
    pressed = _pressed_states(app, "선행 B/O 저장")
    app.run()
    assert repository.load_global_advance_load().version == 2

    app._run(widget_state=pressed)

    assert not app.exception, [item.message for item in app.exception]
    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert _successes(app) == [ADVANCE_LOAD_SAVED]
    assert repository.load_global_advance_load().version == 2


_MONTHLY_EDITORS = pytest.mark.parametrize(
    ("body", "label", "editor_key", "write", "value_column"),
    [
        (
            _ADVANCE_LOAD,
            "선행 B/O 저장",
            ADVANCE_EDITOR_KEY,
            "replace_global_advance_load",
            "선행 물량",
        ),
        (
            _ADVANCE_SHIPMENT,
            "선행 입고 저장",
            ADVANCE_SHIPMENT_EDITOR_KEY,
            "replace_global_advance_shipment",
            "선행 입고",
        ),
    ],
    ids=["advance-load", "advance-shipment"],
)


@_MONTHLY_EDITORS
def test_a_saved_monthly_amount_note_is_not_carried_into_the_next_save(
    repository: DuckDBScenarioRepository,
    body: str,
    label: str,
    editor_key: str,
    write: str,
    value_column: str,
) -> None:
    """저장에 성공하면 변경 메모 칸이 빈다 — 다시 적지 않은 메모가 값만 고친 다음 저장의 기록에
    실렸다(2026-11-08 점검 u3-02). 바꾼 것 없는 저장은 쓰지 않아 칸을 지킨다."""
    load = getattr(repository, write.replace("replace_", "load_"))
    getattr(repository, write)(
        pd.DataFrame({"생산계획년월": [202610], value_column: [1.25]}), source="처음 저장"
    )
    _clear_caches()
    app = _app(repository, body)

    _memo(app).set_value("메모만 적음")
    app = _press(app, label)
    assert len(_infos(app)) == 1 and _infos(app)[0].startswith("바뀐 것이 없습니다")
    assert _memo(app).value == "메모만 적음"

    _edit_cells(app, editor_key, {0: {"26.11": 2.0}})
    _memo(app).set_value("첫 메모")
    app = _press(app, label)
    assert _memo(app).value == ""
    assert (load().version, load().source) == (2, "첫 메모")

    _edit_cells(app, editor_key, {0: {"26.11": 3.0}})
    app = _press(app, label)
    assert _memo(app).value == ""
    assert (load().version, load().source) == (3, "웹 직접 편집")


@_MONTHLY_EDITORS
def test_a_failed_monthly_amount_save_keeps_the_typed_memo(
    repository: DuckDBScenarioRepository,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    label: str,
    editor_key: str,
    write: str,
    value_column: str,
) -> None:
    """저장이 오류로 끝난 회차는 적은 메모를 지우지 않는다 — 다시 누르면 그 메모가 실린다."""
    getattr(repository, write)(
        pd.DataFrame({"생산계획년월": [202610], value_column: [1.25]}), source="처음 저장"
    )
    _clear_caches()
    app = _app(repository, body)

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("디스크에 쓸 수 없습니다")

    monkeypatch.setattr(DuckDBScenarioRepository, write, refuse)
    _edit_cells(app, editor_key, {0: {"26.11": 2.0}})
    _memo(app).set_value("실패할 메모")
    app = _press(app, label)

    assert len(_errors(app)) == 1, _errors(app)
    assert _memo(app).value == "실패할 메모"


@_MONTHLY_EDITORS
def test_a_failed_monthly_amount_save_keeps_the_note_on_months_outside_the_view(
    repository: DuckDBScenarioRepository,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    label: str,
    editor_key: str,
    write: str,
    value_column: str,
) -> None:
    """저장이 오류(`BOOTSTRAP_ERRORS` — DB 잠김 · 디스크 등)로 끝난 회차도 쓰지 않아 다시 돌지
    않는다 — 누르지 않은 회차와 같은 화면이게 조회기간 밖 저장분 표지가 오류와 함께 그대로 선다(판정
    기준과 같다). 오류 글은 숨은 달을 말하지 않는다."""
    getattr(repository, write)(
        pd.DataFrame({"생산계획년월": [202610, 202612], value_column: [1.25, 3.0]}),
        source="처음 저장",
    )
    _clear_caches()
    app = _app(repository, body)
    shown = _outside_marks(app)
    assert len(shown) == 1 and shown[0][1].startswith("26.12 — "), shown

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("디스크에 쓸 수 없습니다")

    monkeypatch.setattr(DuckDBScenarioRepository, write, refuse)
    _edit_cells(app, editor_key, {0: {"26.11": 2.0}})
    app = _press(app, label)

    errors = _errors(app)
    assert len(errors) == 1 and "디스크에 쓸 수 없습니다" in errors[0], errors
    assert "26.12" not in errors[0]
    assert _outside_marks(app) == shown
    stored = getattr(repository, write.replace("replace_", "load_"))()
    assert (stored.version, stored.source) == (1, "처음 저장")


# --------------------------------------------------------------------- 저장본 없는 v0 첫 저장


# ------------------------------------------------------------------- 공정별 Cut-off

_CUTOFF = """
from pathlib import Path

from capa_simulation.components.cutoff_management import render_cutoff_management
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

render_cutoff_management(
    DuckDBEquipmentRepository(Path({path!r})),
    equipment_processes=["Process-A"],
)
"""


@pytest.fixture
def cutoff_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[DuckDBEquipmentRepository]:
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    store = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    store.initialize()
    store.save_process_cutoff(pd.DataFrame({"공정": ["Process-A"], "Cutoff일수": [10.0]}))
    clear_process_cutoff_cache()
    yield store
    clear_process_cutoff_cache()
    clear_equipment_repository()


def _cutoff_app(store: DuckDBEquipmentRepository) -> AppTest:
    app = AppTest.from_string(
        _CUTOFF.format(path=str(store.database_path)), default_timeout=60
    ).run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _edit_cutoff(app: AppTest, days: float) -> None:
    draft = app.session_state[CUTOFF_DRAFT_KEY].copy()
    draft["Cutoff일수"] = days
    app.session_state[CUTOFF_DRAFT_KEY] = draft


def _cutoff_writes(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """저장소 쓰기를 센다 — 같은 내용을 다시 쓰면 managed 서버에서 세대가 하나 는다."""
    writes: list[int] = []
    original = DuckDBEquipmentRepository.save_process_cutoff

    def counted(self: DuckDBEquipmentRepository, *args: Any, **kwargs: Any) -> pd.DataFrame:
        writes.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(DuckDBEquipmentRepository, "save_process_cutoff", counted)
    return writes


def test_a_cutoff_save_without_changes_writes_nothing(
    cutoff_store: DuckDBEquipmentRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    writes = _cutoff_writes(monkeypatch)
    app = _press(_cutoff_app(cutoff_store), "Cut-off 저장")

    assert _infos(app) == [CUTOFF_UNCHANGED_MESSAGE]
    assert not _successes(app)
    assert not writes

    app = _cutoff_app(cutoff_store)
    _edit_cutoff(app, 12.0)
    app = _press(app, "Cut-off 저장")

    assert _successes(app) == ["공정별 Cut-off 1건을 저장했습니다."]
    assert len(writes) == 1
    assert cutoff_store.load_process_cutoff()["Cutoff일수"].tolist() == [12.0]


def test_a_slow_second_press_of_the_cutoff_save_repeats_the_success(
    cutoff_store: DuckDBEquipmentRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """새로 그린 같은 표에 닿은 둘째 누름 — 창 안이면 쓰지 않고 방금 성공을 다시 낸다."""
    app = _cutoff_app(cutoff_store)
    _edit_cutoff(app, 12.0)
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 60.0)
    app = _press(app, "Cut-off 저장")
    writes = _cutoff_writes(monkeypatch)
    app = _press(app, "Cut-off 저장")

    assert _successes(app) == ["공정별 Cut-off 1건을 저장했습니다."]
    assert CUTOFF_UNCHANGED_MESSAGE not in _infos(app)
    assert not writes


def test_an_old_screen_still_reaches_the_cutoff_conflict(
    cutoff_store: DuckDBEquipmentRepository,
) -> None:
    """남의 저장 뒤 옛 화면의 누름은 견주지 않는다 — 「바뀐 것이 없습니다」 가 충돌을 덮지
    않는다."""
    app = _cutoff_app(cutoff_store)
    cutoff_store.save_process_cutoff(pd.DataFrame({"공정": ["Process-A"], "Cutoff일수": [7.0]}))
    clear_process_cutoff_cache()

    app = _press(app, "Cut-off 저장")

    assert CUTOFF_UNCHANGED_MESSAGE not in _infos(app)
    assert any("다른 사용자" in text for text in [str(item.value) for item in app.warning])
    assert cutoff_store.load_process_cutoff()["Cutoff일수"].tolist() == [7.0]


@pytest.mark.parametrize(
    ("body", "label", "load"),
    [
        (_EXECUTION, "확보율 보정 저장", "load_global_execution_capacity"),
        (_SUMMARY, "공지 저장", "load_global_summary_note"),
        (_TOP5, "확보율 구간 저장", "load_global_top5_band"),
        (_ADVANCE_LOAD, "선행 B/O 저장", "load_global_advance_load"),
        (_ADVANCE_SHIPMENT, "선행 입고 저장", "load_global_advance_shipment"),
    ],
    ids=["execution", "summary", "top5", "advance-load", "advance-shipment"],
)
def test_the_first_save_of_an_unsaved_profile_still_writes(
    repository: DuckDBScenarioRepository, body: str, label: str, load: str
) -> None:
    """저장본이 없으면(v0) 고치지 않은 첫 저장도 쓴다 — 판정 기준·Proc Rename(개선 I5)과 같은
    규칙."""
    app = _app(repository, body)

    app = _press(app, label)

    assert not infos(app) and not place_errors(app), _infos(app) + _errors(app)
    assert getattr(repository, load)().version == 1


# ------------------------------------------------------------------------------- 순수 견주기


def test_same_monthly_amounts_folds_order_zeros_and_last_digits() -> None:
    """선행 B/O·선행 입고의 견주기는 정규화한 달·값끼리다 — 차례·0 달·끝자리는 같은 값이다."""
    stored = pd.DataFrame({"생산계획년월": [202611, 202610], "선행 물량": [2.0, 0.1 + 0.2]})
    same = pd.DataFrame({"생산계획년월": [202610, 202611, 202612], "선행 물량": [0.3, 2.0, 0.0]})
    moved = pd.DataFrame({"생산계획년월": [202610, 202612], "선행 물량": [0.3, 2.0]})

    assert same_monthly_amounts(same, stored, value_column="선행 물량")
    assert not same_monthly_amounts(moved, stored, value_column="선행 물량")
