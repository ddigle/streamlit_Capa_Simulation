# Purpose: 목록 관리에서 어긋난 때 닿은 저장 · 불러오기 · 공식 지정 · 보관 · 모두 버리기를 잰다.

"""시나리오 관리 › 목록 관리에서 화면이 지금 저장본 · 연 시나리오와 어긋난 채 닿은 누름.

브라우저는 회차가 돌아오기 전의 화면을 들고 있고, 표 고침은 300ms 묶음이라 콜백이 본문보다 먼저
돈다. 그래서 「그 회차에 그린 것」 과 「누른 때의 저장본」 이 다를 수 있다. 어느 쪽이든 하지 않은
일을 했다고 알리거나, 알리지 않고 고침을 지우거나, 엉뚱한 대상을 움직이지 않는다.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alert_marks import flashed, infos, successes
from scenario_list_fake import Calls, ListBrowser, install_fake_list_grid, last
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script
from test_scenario_management_page import (
    PAGE_PATH,
    _check_row,
    _clone_official,
    _draft,
    _fill_clone,
    _list_app,
    _save,
    _three_scenarios,
)
from test_scenario_save_double_press import _first_callback

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.scenario_list_grid import (
    CHANGES_KEY,
    REVISIONS_KEY,
    TABLE_KEY,
)
from capa_simulation.components.scenario_list_state import DRAFT_KEY
from capa_simulation.components.scenario_management import (
    ACTION_KEY,
    ARCHIVE_GONE_MESSAGE,
    CARD_LOAD_KEY,
    CARD_NOTICE_KEY,
    CARD_OFFICIAL_KEY,
    CLONE_MODE,
    DISCARD_CONFIRM_KEY,
    MODE_KEY,
    OFFICIAL_DIALOG_KEY,
    OPENED_MOVED_MESSAGE,
    SIDE_DETAIL,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import ACTIVE_PERSISTED_REVISION_ID_KEY
from capa_simulation.services.scenario_list_edits import ListDraft, draft_base


def _name_op(row_id: str, text: str, seen: str) -> dict[str, Any]:
    return {"op": "name", "kind": "scenario", "id": row_id, "text": text, "seen": seen}


def _names(repository: DuckDBScenarioRepository) -> dict[str, str]:
    return {item.scenario_id: item.scenario_name for item in repository.list_scenarios()}


def _errors(app: AppTest) -> list[str]:
    return [str(item.value) for item in flashed(app, "error")]


def _warnings(app: AppTest) -> list[str]:
    return [str(item.value) for item in flashed(app, "warning")]


def _success_texts(app: AppTest) -> list[str]:
    return [str(item.value) for item in successes(app)]


def test_saving_again_over_a_cut_own_save_keeps_the_other_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """첫 저장이 쓴 뒤 끊기고, 같은 세대로 그 이름을 다시 고친 op 와 다른 줄 고침이 함께 접혔다.
    고친 새 이름은 지금 이름이 아니므로 제 저장이 아니다 — 성공을 알리거나 초안을 비우지 않는다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    app, browser, _ = _list_app(script, monkeypatch)
    browser.rename_scenario(ids[0], "첫 저장 이름")
    _first_callback(
        app,
        monkeypatch,
        "_save_list_edits",
        cut_after=(DuckDBScenarioRepository, "apply_scenario_list_edits"),
    )
    assert _names(repository)[ids[0]] == "첫 저장 이름"

    browser.prepared(
        TABLE_KEY,
        _name_op(ids[0], "다시 고친 이름", names[0]),
        _name_op(ids[1], "다른 줄 고침", names[1]),
    )
    app.button(key="scenario_list_save").click().run()
    assert not app.exception

    assert not any("저장했습니다" in text for text in _success_texts(app))
    assert any("먼저 이름을 바꿨습니다" in text for text in _errors(app))
    stored = _names(repository)
    assert (stored[ids[0]], stored[ids[1]]) == ("첫 저장 이름", names[1])
    draft = _draft(app)
    assert set(draft.scenarios) == {ids[1]} and draft.scenarios[ids[1]].text == "다른 줄 고침"

    _save(app)
    assert "시나리오명 1건을 저장했습니다." in _success_texts(app)
    assert _names(repository)[ids[1]] == "다른 줄 고침"


def test_a_name_put_back_by_another_session_is_not_taken_for_an_own_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이 세션이 A → B 를 저장한 뒤 남이 되돌렸고, 이 세션이 A → C 를 고치는 사이 남이 다시 B 로
    바꿨다. 짝 (A, B) 는 이 세션 표지와 같지만 고친 것은 C 다 — 거부이고 다른 줄 고침은 남는다."""
    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    app, browser, _ = _list_app(script, monkeypatch)
    browser.rename_scenario(ids[0], "남과 겹친 이름")
    _save(app)
    repository.rename_scenario(ids[0], names[0])
    browser.run()
    browser.rename_scenario(ids[0], "이 세션 새 이름", seen=names[0])
    browser.rename_scenario(ids[1], "다른 줄 고침")
    repository.rename_scenario(ids[0], "남과 겹친 이름")

    _save(app)

    assert not any("저장했습니다" in text for text in _success_texts(app))
    assert any("먼저 이름을 바꿨습니다" in text for text in _errors(app))
    assert _names(repository)[ids[0]] == "남과 겹친 이름"
    assert _names(repository)[ids[1]] == names[1]
    assert set(_draft(app).scenarios) == {ids[1]}


@pytest.mark.parametrize("other_row", [True, False])
def test_a_save_press_tells_the_edits_of_rows_gone_since_the_last_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, other_row: bool
) -> None:
    """화면이 쉬는 동안 남이 고친 줄을 보관하고 회차 없이 「변경 저장」 을 눌렀다 — 콜백이 본문보다
    먼저 돌아 본문 맞추기는 빈 초안만 본다. 저장 콜백이 그 고침을 뺀 사실을 알린다. 그것뿐이면
    「고친 것이 없습니다」 는 맞지 않는 말이다."""
    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    victim, kept = [item for item in ids if item != release.scenario_id]
    app, browser, _ = _list_app(script, monkeypatch)
    browser.rename_scenario(victim, "남이 보관할 줄")
    if other_row:
        browser.rename_scenario(kept, "남는 줄 고침")

    repository.archive_scenario(victim)
    _save(app)

    assert any("고침 1건을 버렸습니다" in text for text in _warnings(app))
    assert not any("고친 것이 없습니다" in str(item.value) for item in infos(app))
    assert ("시나리오명 1건을 저장했습니다." in _success_texts(app)) is other_row
    assert _names(repository)[kept] == ("남는 줄 고침" if other_row else names[ids.index(kept)])
    assert _draft(app).scenarios == {}


def test_a_cut_save_hands_the_gone_edits_to_the_second_press(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """남이 고친 줄을 보관한 뒤 「변경 저장」 을 빠르게 두 번 누른다. 첫 콜백이 쓴 뒤 그 경고를 담기
    전에 끊기면 둘째 콜백은 저장을 다시 돌지 않고 첫 결과를 받아 초안을 비운다 — 본문 맞추기가 셀
    것도 남지 않으므로 경고는 그 결과로 잇는다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    script, database_path, ids, names = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    victim, kept = [item for item in ids if item != release.scenario_id]
    app, browser, _ = _list_app(script, monkeypatch)
    browser.rename_scenario(victim, "남이 보관할 줄")
    browser.rename_scenario(kept, "남는 줄 고침")
    repository.archive_scenario(victim)
    app.button(key="scenario_list_save").click()
    pressed = app._tree.get_widget_states()
    _first_callback(
        app,
        monkeypatch,
        "_save_list_edits",
        cut_after=(DuckDBScenarioRepository, "apply_scenario_list_edits"),
    )
    assert _names(repository)[kept] == "남는 줄 고침"

    app._run(widget_state=pressed)

    assert not app.exception
    assert any("고침 1건을 버렸습니다" in text for text in _warnings(app))
    assert "시나리오명 1건을 저장했습니다." in _success_texts(app)
    assert _draft(app).scenarios == {}


def test_the_archive_check_does_not_follow_to_another_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 의 보관 칸에서 켠 체크를 브라우저가 내리기 전에 B 의 「보관…」 을 눌러도 B 칸의 체크는
    꺼진 채 선다 — 칸 key 에 시나리오를 싣는다(가상 제품 확인 체크와 같은 꼴)."""
    script, database_path, ids, _ = _three_scenarios(tmp_path)
    release = DuckDBScenarioRepository(database_path).latest_official_release()
    assert release is not None
    first, second = [item for item in ids if item != release.scenario_id]
    app, browser, _ = _list_app(script, monkeypatch, side=SIDE_DETAIL)
    browser.open(first)
    app.button(key=f"{ACTION_KEY}_archive").click().run()
    assert not app.exception
    next(widget for widget in app.checkbox if "보관합니다" in widget.label).check()
    held = list(app._tree.get_widget_states().widgets)
    app.run()
    assert not app.exception

    browser.open(second)
    app.button(key=f"{ACTION_KEY}_archive").click()
    states = app._tree.get_widget_states()
    known = {item.id for item in states.widgets}
    states.widgets.extend(item for item in held if item.id not in known)
    app._run(widget_state=states)
    assert not app.exception

    shown = [widget for widget in app.checkbox if "보관합니다" in widget.label]
    assert len(shown) == 1 and shown[0].value is False
    assert next(button for button in app.button if button.label == "보관 실행").disabled


def test_the_load_button_refuses_a_revision_of_another_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 의 옛 줄 누름이 지금 연 B 의 owner 를 달고 닿았다 — 고름이 B 소속이 아니면 올리지
    않는다."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    first = _clone_official(database_path, "옛 줄 시나리오", "OWNER-A")
    second = _clone_official(database_path, "지금 연 시나리오", "OWNER-B")

    calls = install_fake_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120)
    browser = ListBrowser(app, calls)
    _check_row(app, second.scenario.scenario_id)
    browser.run()
    active = app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY]
    browser.prepared(
        REVISIONS_KEY,
        {"op": "pick", "owner": second.scenario.scenario_id, "id": first.revision.revision_id},
    )
    app.button(key=f"{CARD_LOAD_KEY}_{second.scenario.scenario_id}").click()
    browser.run()

    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == active
    assert OPENED_MOVED_MESSAGE in _errors(app)


def _old_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AppTest, ListBrowser, Calls, DuckDBScenarioRepository, str]:
    """시나리오 하나를 연 화면과 그 시나리오 — 남이 보관하면 이 카드가 옛 카드다."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    target = _clone_official(database_path, "남이 보관할 시나리오", "OLD-CARD").scenario.scenario_id
    calls = install_fake_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120)
    browser = ListBrowser(app, calls)
    _check_row(app, target)
    browser.run()
    return app, browser, calls, DuckDBScenarioRepository(database_path), target


def test_an_old_load_press_does_not_raise_a_scenario_archived_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """남이 보관한 시나리오를 옛 카드에서 불러오면 목록에 없는 보관본이 사이드바에 올라왔다."""
    app, browser, _, repository, target = _old_card(tmp_path, monkeypatch)
    active = app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY]

    repository.archive_scenario(target)
    app.button(key=f"{CARD_LOAD_KEY}_{target}").click()
    browser.run()

    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == active
    assert ARCHIVE_GONE_MESSAGE in _errors(app)


def test_an_old_official_press_is_told_when_the_card_moved_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """남이 보관한 시나리오를 옛 카드에서 「공식으로 지정…」 하면 본문이 연 줄을 옮기며 팝업 칸을
    말없이 지웠다 — 팝업도 알림도 없이 표만 바뀌지 않게 그 회차에 알린다."""
    app, browser, _, repository, target = _old_card(tmp_path, monkeypatch)

    repository.archive_scenario(target)
    app.button(key=f"{CARD_OFFICIAL_KEY}_{target}").click()
    browser.run()

    assert OFFICIAL_DIALOG_KEY not in app.session_state
    assert _draft(app).opened != target
    assert OPENED_MOVED_MESSAGE in _errors(app)
    assert CARD_NOTICE_KEY not in app.session_state


def test_discard_all_with_nothing_to_discard_says_so_and_keeps_the_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """고친 것이 없는 「모두 버리기」 — 일어나지 않은 일을 알리지 않고(UI-DAT-11) 세대를 올리지
    않는다(막 보내던 고침이 옛 세대로 버려진다). 팝오버를 잠그지 않는 것은 「변경 저장」 과 같다 —
    출납이 묶음이라 잠금 판정이 브라우저보다 늦다(UI-INP-07)."""
    script, _, _, _ = _three_scenarios(tmp_path)
    app, _, _ = _list_app(script, monkeypatch)
    base = draft_base(_draft(app))

    app.button(key=DISCARD_CONFIRM_KEY).click().run()
    assert not app.exception

    assert "버릴 것이 없습니다." in [str(item.value) for item in infos(app)]
    assert not any("모두 버렸습니다" in str(item.value) for item in infos(app))
    assert draft_base(_draft(app)) == base


def _ordered_edits(app: AppTest, browser: ListBrowser, ids: list[str]) -> None:
    browser.rename_scenario(ids[1], "복제 뒤 저장할 이름")
    browser.move(ids[2], ids[0], order=tuple(ids))
    assert _draft(app).order is not None


def test_a_clone_made_here_does_not_block_the_unsaved_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """미저장 순서를 둔 채 이 세션이 복제하면 「다른 곳에서 시나리오가 더해지거나 …」 로 막혔는데
    거짓이다 — 본 차례를 새 줄이 더해진 차례로 옮기고, 저장은 순서 · 이름을 함께 쓴다."""
    script, database_path, ids, _ = _three_scenarios(tmp_path)
    repository = DuckDBScenarioRepository(database_path)
    app, browser, calls = _list_app(script, monkeypatch)
    _ordered_edits(app, browser, ids)

    app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run()
    assert not app.exception
    _fill_clone(app, "이 세션 복제", "CLONE-HERE")
    app.segmented_control(key=MODE_KEY).set_value("목록 관리").run()
    assert not app.exception
    browser.run()

    assert last(calls, CHANGES_KEY)["order"].get("problem") is None
    _save(app)
    assert any("누적 순서" in text for text in _success_texts(app))
    stored = repository.list_scenarios()
    assert [item.scenario_id for item in stored][:3] == [ids[2], ids[0], ids[1]]
    assert stored[2].scenario_name == "복제 뒤 저장할 이름"
    assert stored[3].scenario_name == "이 세션 복제"


def test_following_a_created_scenario_moves_the_base_only_when_it_is_the_only_change() -> None:
    """이 세션이 더한 줄만 다른 차례일 때만 본 차례를 옮긴다 — 남이 바꾼 차례는 그대로 막힌다."""
    from capa_simulation.services.scenario_list_edits import rebased_for_created

    draft = ListDraft(order=("b", "a"), order_base=("a", "b"))

    assert rebased_for_created(draft, ("new", "a", "b"), "new").order_base == ("new", "a", "b")
    assert rebased_for_created(draft, ("a", "b", "new"), "new").order_base == ("a", "b", "new")
    assert rebased_for_created(draft, ("b", "a", "new"), "new") == draft
    assert rebased_for_created(draft, ("a", "c", "b", "new"), "new") == draft
    assert rebased_for_created(replace(draft, order=None), ("a", "new"), "new").order is None


def test_following_a_created_scenario_without_a_draft_makes_no_draft(tmp_path: Path) -> None:
    """목록 관리를 연 적 없는 세션의 복제 — 초안 칸을 만들지 않고, 저장소를 더 읽지 않는다."""
    script = f"""
import streamlit as st

from capa_simulation.components.scenario_list_state import DRAFT_KEY, follow_created_scenario


class Refusing:
    def list_scenarios(self):
        raise AssertionError("초안이 없으면 읽지 않는다")


follow_created_scenario(Refusing(), {uuid4().hex!r})
st.session_state["__has_draft__"] = DRAFT_KEY in st.session_state
"""
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    assert app.session_state["__has_draft__"] is False
    assert DRAFT_KEY not in app.session_state
