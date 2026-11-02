# Purpose: 줄 차례가 바뀐 편집표의 적용 전 편집 비움·알림과 숫자 칸 증분 버림 없앰을 검사한다.

"""편집표 줄 차례 지키기 · 숫자 칸 `step` 버림 없애기(2026-10-24 사용자 결정 「권장대로」).

- **줄 차례.** `st.data_editor` 의 편집은 줄 위치로 남는다. 생산 계획 2표는 공용 표시순서로 줄을
  세우는데 표시순서는 기준정보 버전·리비전을 바꾸지 않고 바뀐다. 원본 토큰(`source_token`)에 줄 차례
  지문이 없으면 적용 전 편집이 다른 공정 줄에 붙은 채 「적용」이 그대로 저장한다. 이제 지문이 바뀌면
  편집을 비우고 한 번 알린다 — 틀린 저장이 없고 적용 전 편집만 잃는다. 안 바뀐 회차에는 편집이
  그대로 남는다. 기준 정보 9표는 범용 편집 그리드라 초안이 업무 키 — 차례가 바뀌어도 제 줄에 남고
  알리지 않는다(2026-11-02 편집 표 횡전개).
- **증분 버림.** Streamlit 1.63 `NumberColumn` 은 `step` 의 소수 자릿수 아래를 반올림하지 않고
  버린다. 뜻이 걸리는 칸(효율·여유율·Lot·WF 측정률·수율·설비대수·기존 보유대수)은 `step` 없이
  `format` 만 둔다.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from edit_grid_fake import Calls, install_fake_edit_grid, last
from streamlit.testing.v1 import AppTest
from test_reference_data_page import (
    DATASET,
    DISPLAY_ORDER_SWAP_TEST_SCRIPT,
    TEST_SCRIPT,
    TWO_PROCESS_TEST_SCRIPT,
    _grid_write,
    _visible_keys,
)

from capa_simulation.components import (
    editor_state,
    month_editor,
    scenario_edit_bar,
    widget_generation,
    write_guard,
)
from capa_simulation.reference_grid_keys import DATASET_KEY, GRID_HOST, cells_key
from capa_simulation.scenario_state import ActiveScenario

ROOT = Path(__file__).resolve().parents[1]
MONTH = "202608"
NOTICE_HEAD = "공용 표시순서가 바뀌어 표의 줄 차례가 달라졌습니다."


def _is_editor(proto_id: str, editor_key: str) -> bool:
    """그 편집표의 위젯 id 인가 — 편집을 버릴 때마다 key 에 세대 꼬리(`__g1`)가 붙는다."""
    return re.search(rf"-{re.escape(editor_key)}(__g\d+)?$", proto_id) is not None


def _edit(column: str, value: float) -> dict[str, Any]:
    return {"edited_rows": {0: {column: value}}, "added_rows": [], "deleted_rows": []}


def _active(revision: int) -> ActiveScenario:
    return {"reference_version": 1, "revision": revision, "content_token": "t", "tables": {}}


# ------------------------------------------------------------------ 원본 토큰 · 비우기 (단위)


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    fake = SimpleNamespace(session_state={})
    monkeypatch.setattr(scenario_edit_bar, "st", fake)
    monkeypatch.setattr(editor_state, "st", fake)
    # 편집표 key 세대는 `widget_generation`(세대 읽기는 `write_guard`)이 짓는다.
    monkeypatch.setattr(widget_generation, "st", fake)
    monkeypatch.setattr(write_guard, "st", fake)
    return fake


def _token(order: str, *, revision: int = 1) -> str:
    return scenario_edit_bar.source_token(1, _active(revision), 202608, 202612, row_order=order)


def _generation(session: SimpleNamespace, key: str) -> int:
    return int(session.session_state.get(f"{key}__generation", 0))


NAMES = {"upeh": "UPEH", "run_day": "일수", "staged": "PKG PLAN 붙여넣기"}


def _reset(
    session: SimpleNamespace, token: str, *, own_change_key: str | None = None
) -> scenario_edit_bar.SourceReset:
    return scenario_edit_bar.reset_editors_on_source_change(
        "token",
        token,
        ("upeh", "run_day"),
        other_keys=("staged",),
        own_change_key=own_change_key,
        names=NAMES,
    )


def test_the_source_token_changes_with_the_row_order_alone() -> None:
    """기준정보 버전·리비전·기간이 같아도 줄 차례 지문이 다르면 다른 원본이다."""
    assert _token("a") != _token("b")
    assert _token("a") == _token("a")


def test_a_row_order_change_drops_the_pending_edits_and_names_them(
    session: SimpleNamespace,
) -> None:
    session.session_state["token"] = _token("a")
    session.session_state["upeh"] = _edit(MONTH, 1.0)
    session.session_state["staged"] = object()

    reset = _reset(session, _token("b"))

    assert reset.changed
    # 고친 것이 남아 있던 것만 이름이 실린다 — 일수 표는 고친 것이 없었다.
    assert reset.row_order_dropped == ("UPEH", "PKG PLAN 붙여넣기")
    assert _generation(session, "upeh") == 1
    assert _generation(session, "run_day") == 1
    assert "staged" not in session.session_state
    assert session.session_state["token"] == _token("b")


def test_an_unchanged_row_order_keeps_the_edits(session: SimpleNamespace) -> None:
    """표시순서가 안 바뀐 회차에는 아무것도 비우지 않는다(회귀)."""
    session.session_state["token"] = _token("a")
    session.session_state["upeh"] = _edit(MONTH, 1.0)

    reset = _reset(session, _token("a"))

    assert reset == scenario_edit_bar.SourceReset(changed=False)
    assert editor_state.editor_has_edits("upeh")
    assert _generation(session, "upeh") == 0


@pytest.mark.parametrize("previous", [None, "duckdb:1:1:202608:202612"])
def test_a_first_or_cleared_token_drops_without_a_row_order_notice(
    session: SimpleNamespace, previous: str | None
) -> None:
    """앞 토큰이 없으면(첫 회차·불러오기가 지운 뒤·옛 형식) 줄 차례를 견줄 수 없어 알리지 않는다.

    불러오기·저장은 적용 전 편집을 버린다고 사이드바 팝업이 먼저 확인받는다.
    """
    if previous is not None:
        session.session_state["token"] = previous
    session.session_state["upeh"] = _edit(MONTH, 1.0)

    reset = _reset(session, _token("b"))

    assert reset.changed
    assert reset.row_order_dropped == ()
    assert _generation(session, "upeh") == 1


def test_a_content_change_alone_drops_silently(session: SimpleNamespace) -> None:
    """리비전만 바뀐 것은 지금까지처럼 조용히 비운다 — 알림은 줄 차례가 바뀐 회차의 것이다."""
    session.session_state["token"] = _token("a", revision=1)
    session.session_state["upeh"] = _edit(MONTH, 1.0)

    reset = _reset(session, _token("a", revision=2))

    assert reset.changed
    assert reset.row_order_dropped == ()


def test_an_own_apply_keeps_the_other_tables_while_the_order_holds(
    session: SimpleNamespace,
) -> None:
    session.session_state["token"] = _token("a", revision=1)
    session.session_state["upeh"] = _edit(MONTH, 1.0)
    session.session_state["run_day"] = _edit(MONTH, 20.0)
    scenario_edit_bar.mark_own_change("own", ("upeh",))

    reset = _reset(session, _token("a", revision=2), own_change_key="own")

    assert reset == scenario_edit_bar.SourceReset(changed=True)
    assert _generation(session, "upeh") == 1
    assert editor_state.editor_has_edits("run_day")


def test_an_own_apply_does_not_shield_the_other_tables_when_the_order_changes(
    session: SimpleNamespace,
) -> None:
    """방금 적용한 회차에 줄 차례까지 바뀌면 남겨 둔 다른 표의 편집이 다른 줄에 붙는다 — 다 비운다.

    방금 적용한 표는 잃은 편집이 아니라 알림에서 뺀다.
    """
    session.session_state["token"] = _token("a", revision=1)
    session.session_state["upeh"] = _edit(MONTH, 1.0)
    session.session_state["run_day"] = _edit(MONTH, 20.0)
    scenario_edit_bar.mark_own_change("own", ("upeh",))

    reset = _reset(session, _token("b", revision=2), own_change_key="own")

    assert _generation(session, "upeh") == 1
    assert _generation(session, "run_day") == 1
    assert reset.row_order_dropped == ("일수",)
    assert "own" not in session.session_state


def _reset_with_order_free(
    session: SimpleNamespace, token: str, *, own_change_key: str | None = None
) -> scenario_edit_bar.SourceReset:
    """붙여넣기 대기(`staged`)와 그 표를 원본으로 그린 편집표(`upeh`)가 줄 차례와 상관없는 화면."""
    return scenario_edit_bar.reset_editors_on_source_change(
        "token",
        token,
        ("upeh", "run_day"),
        other_keys=("staged",),
        own_change_key=own_change_key,
        names=NAMES,
        order_free_keys=("staged", "upeh"),
    )


def test_order_free_state_survives_a_row_order_change_and_is_not_named(
    session: SimpleNamespace,
) -> None:
    """제 줄 차례를 들고 있는 상태는 차례만 바뀐 회차에 버릴 까닭이 없다.

    남기고 알림에도 싣지 않는다. 줄 위치로 남는 편집(일수)만 버리고 그 이름을 싣는다.
    """
    session.session_state["token"] = _token("a")
    session.session_state["upeh"] = _edit(MONTH, 1.0)
    session.session_state["run_day"] = _edit(MONTH, 20.0)
    staged = object()
    session.session_state["staged"] = staged

    reset = _reset_with_order_free(session, _token("b"))

    assert reset.changed
    assert reset.row_order_dropped == ("일수",)
    assert session.session_state["staged"] is staged
    assert editor_state.editor_has_edits("upeh")
    assert _generation(session, "upeh") == 0
    assert _generation(session, "run_day") == 1
    assert session.session_state["token"] == _token("b")


def test_order_free_state_still_drops_when_the_source_changes_too(
    session: SimpleNamespace,
) -> None:
    """리비전·기간이 함께 바뀌면 행·월 구성이 달라져 모두 버린다.

    차례 탓에 잃은 것이 아니라 알리지 않는다(기간 변경과 같다).
    """
    session.session_state["token"] = _token("a", revision=1)
    session.session_state["upeh"] = _edit(MONTH, 1.0)
    session.session_state["run_day"] = _edit(MONTH, 20.0)
    session.session_state["staged"] = object()

    reset = _reset_with_order_free(session, _token("b", revision=2))

    assert reset == scenario_edit_bar.SourceReset(changed=True)
    assert "staged" not in session.session_state
    assert _generation(session, "upeh") == 1
    assert _generation(session, "run_day") == 1


def test_an_own_apply_with_an_order_change_keeps_the_order_free_state(
    session: SimpleNamespace,
) -> None:
    """방금 적용한 표는 버리고, 남은 것 가운데 줄 위치로 남는 편집만 차례 탓에 버린다."""
    session.session_state["token"] = _token("a", revision=1)
    session.session_state["upeh"] = _edit(MONTH, 1.0)
    session.session_state["run_day"] = _edit(MONTH, 20.0)
    staged = object()
    session.session_state["staged"] = staged
    scenario_edit_bar.mark_own_change("own", ("upeh",))

    reset = _reset_with_order_free(session, _token("b", revision=2), own_change_key="own")

    assert reset.row_order_dropped == ("일수",)
    assert _generation(session, "upeh") == 1
    assert _generation(session, "run_day") == 1
    assert session.session_state["staged"] is staged


def test_the_notice_names_what_was_dropped() -> None:
    message = scenario_edit_bar.row_order_reset_message(("효율", "설비대수 보유"))
    assert message.startswith(NOTICE_HEAD)
    assert "(효율 · 설비대수 보유)을" in message
    assert message.endswith("다시 입력하세요.")


# ------------------------------------------------------------------ 기준 정보 (AppTest)


def editor_widget_key_in(app: AppTest, key: str) -> str:
    """앱이 지금 편집표를 그리는 위젯 키(`editor_state.editor_widget_key` 와 같은 규칙) — 필터가
    바뀌거나 편집을 버리면 새 세대 키로 선다. 브라우저는 그 키로 편집을 보내므로 시험도 같은 키에
    넣는다."""
    generation_key = f"{key}__generation"
    generation = app.session_state[generation_key] if generation_key in app.session_state else 0
    return key if not generation else f"{key}__g{generation}"


@pytest.fixture
def grid_calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """기준 정보 편집 그리드 대역 — 받은 (key, data) 를 적는다(`tests/edit_grid_fake.py`)."""
    return install_fake_edit_grid(monkeypatch)


def _notices(app: AppTest) -> list[str]:
    return [str(warning.value) for warning in app.warning if NOTICE_HEAD in str(warning.value)]


def _generation_in(app: AppTest, key: str) -> int:
    slot = f"{key}__generation"
    return int(app.session_state[slot]) if slot in app.session_state else 0


def _apply_disabled(app: AppTest, button_key: str) -> bool:
    return bool(next(button for button in app.button if button.key == button_key).disabled)


def test_a_display_order_change_keeps_the_reference_draft_on_its_business_key(
    grid_calls: Calls,
) -> None:
    """효율 표 첫 줄(Process-A)을 고친 채 표시순서가 뒤집힌 회차에 「변경사항 적용」을 누른다.

    옛 편집표는 줄 위치라 그 회차에 편집을 비우고 알렸다(틀린 저장을 막으려고). 그리드 초안은 업무
    키라 차례가 바뀌어도 고친 줄(Process-A)에 남고, 함께 온 클릭도 그 줄에 적용한다 — 알림이 없다.
    """
    app = AppTest.from_string(DISPLAY_ORDER_SWAP_TEST_SCRIPT, default_timeout=60)
    app.session_state[DATASET_KEY] = DATASET["효율"]
    app.run()
    assert not app.exception
    assert [key.split("\x1f")[0] for key in _visible_keys(grid_calls)] == ["Process-A", "Process-B"]
    app = _grid_write(app, grid_calls, "Process-A\x1f양산", MONTH, "0.5")
    assert not _apply_disabled(app, "capa_run_rate_editor_apply")

    app.session_state["test_display_order_descending"] = True
    next(button for button in app.button if button.key == "capa_run_rate_editor_apply").click()
    app.run()

    assert not app.exception
    assert not _notices(app)
    saved = app.session_state["test_month_updates"]["RQ_RUN_RATE"]
    assert dict(zip(saved["공정"], saved["CAPA_RUN_RATE"], strict=True)) == {
        "Process-A": 0.5,
        "Process-B": 0.9,
    }


def test_an_unchanged_display_order_keeps_the_reference_edit_and_applies_it_to_its_row(
    grid_calls: Calls,
) -> None:
    """표시순서가 그대로인 회차에는 편집이 남고 적용은 고친 줄에 든다(회귀)."""
    app = AppTest.from_string(DISPLAY_ORDER_SWAP_TEST_SCRIPT, default_timeout=60)
    app.session_state[DATASET_KEY] = DATASET["효율"]
    app.run()
    app = _grid_write(app, grid_calls, "Process-A\x1f양산", MONTH, "0.5")
    next(button for button in app.button if button.key == "capa_run_rate_editor_apply").click()
    app.run()

    assert not app.exception
    assert not _notices(app)
    saved = app.session_state["test_month_updates"]["RQ_RUN_RATE"]
    assert dict(zip(saved["공정"], saved["CAPA_RUN_RATE"], strict=True)) == {
        "Process-A": 0.5,
        "Process-B": 0.9,
    }


def test_a_display_order_change_keeps_an_equipment_count_draft_too(grid_calls: Calls) -> None:
    """설비대수 세 표도 같은 표시순서로 줄을 세운다 — 차례가 바뀌어도 초안은 제 공정에 남고 알리지
    않는다."""
    app = AppTest.from_string(DISPLAY_ORDER_SWAP_TEST_SCRIPT, default_timeout=60)
    app.session_state[DATASET_KEY] = DATASET["설비대수 보유"]
    app.run()
    assert not app.exception
    app = _grid_write(app, grid_calls, "Process-A", MONTH, "0.333")

    app.session_state["test_display_order_descending"] = True
    app.run()

    assert not app.exception
    assert not _notices(app)
    assert app.session_state[cells_key("RQ_EQP_OWN")] == {
        "cells": {"Process-A": {MONTH: 0.333}},
        "bad": {},
    }


# ------------------------------------------------------------------ 생산 계획 (AppTest)

# PKG PLAN·수율에 제품을 하나 더 두고, 두 화면 범위의 `제품정보` 규칙을 세션 상태 하나로 뒤집는다.
_PLAN_ORDER_SWAP = """
from capa_simulation.services import display_order_scopes as _scopes

for _name in ("RQ_PKG_PLAN", "RQ_YLD"):
    _second = tables[_name].iloc[0].to_dict()
    _second["제품정보"] = "Product-B"
    tables[_name] = pd.concat([tables[_name], pd.DataFrame([_second])], ignore_index=True)

_order_mode = "내림차순" if st.session_state.get("test_display_order_descending") else "오름차순"
tables["RQ_DISPLAY_ORDER"] = pd.DataFrame(
    [
        {
            "페이지 구분": _scopes.PAGE_PLAN,
            "탭 구분": _scope_tab,
            "정렬우선순위": 1,
            "분류컬럼": "제품정보",
            "정렬방식": _order_mode,
            "분류값": "",
            "값표시순서": None,
            "활성여부": "Y",
        }
        for _scope_tab in (_scopes.TAB_PKG_PLAN, _scopes.TAB_YIELD)
    ]
)
"""
PLAN_ORDER_SWAP_TEST_SCRIPT = (
    TEST_SCRIPT.replace('PAGE_NAME = "reference_data.py"', 'PAGE_NAME = "load_conversion.py"')
    .replace("\nactive = {", _PLAN_ORDER_SWAP + "\nactive = {", 1)
    .replace('"test-capacity-standards-page"', '"test-plan-display-order-swap"')
)
assert PLAN_ORDER_SWAP_TEST_SCRIPT.count("test-plan-display-order-swap") == 1
PLAN_TAB = ":material/edit_calendar: PKG PLAN"


def _plan_products(app: AppTest) -> list[str]:
    editor = next(frame for frame in app.dataframe if _is_editor(frame.proto.id, "pkg_plan_editor"))
    return [str(value) for value in editor.value["제품정보"]]


@pytest.mark.parametrize("descending", [True, False], ids=["order-changed", "order-held"])
def test_the_plan_editor_drops_an_unapplied_edit_only_when_the_order_changes(
    descending: bool,
) -> None:
    """PKG PLAN 첫 줄(Product-A)을 고친 채 「PKG PLAN 변경사항 적용」을 누른다.

    표시순서가 뒤집힌 회차면 편집을 비우고 알리며 적용하지 않는다(전에는 Product-B 계획에 저장했다).
    그대로인 회차면 편집이 남아 Product-A 에 적용된다.
    """
    editor_key = "pkg_plan_editor"
    app = AppTest.from_string(PLAN_ORDER_SWAP_TEST_SCRIPT, default_timeout=60)
    app.session_state["load_conversion_active_tab"] = PLAN_TAB
    app.run()
    assert not app.exception
    assert _plan_products(app) == ["Product-A", "Product-B"]
    edit = _edit(MONTH, 555.0)
    app.session_state[editor_widget_key_in(app, editor_key)] = edit
    app.run()
    assert not app.exception
    assert not _apply_disabled(app, "apply_pkg_plan_changes")

    app.session_state["test_display_order_descending"] = descending
    app.session_state[editor_widget_key_in(app, editor_key)] = edit
    app.button(key="apply_pkg_plan_changes").click()
    app.run()

    assert not app.exception
    if descending:
        assert _plan_products(app) == ["Product-B", "Product-A"]
        assert "test_month_updates" not in app.session_state
        notices = _notices(app)
        assert len(notices) == 1
        assert "(PKG PLAN)" in notices[0]
        app.run()
        assert not _notices(app)
    else:
        assert not _notices(app)
        saved = app.session_state["test_month_updates"]["RQ_PKG_PLAN"]
        assert dict(zip(saved["제품정보"], saved["생산수량"], strict=True)) == {
            "Product-A": 555.0,
            "Product-B": 100.0,
        }


PLAN_STAGED_KEY = "pkg_plan_staged_paste"


def _stage_plan_paste(app: AppTest, product_a_quantity: float) -> pd.DataFrame:
    """PKG PLAN 「Excel 붙여넣기」 가 남기는 대기 표.

    지금 편집표 그대로에서 Product-A 칸만 바꾼다.
    """
    editor = next(frame for frame in app.dataframe if _is_editor(frame.proto.id, "pkg_plan_editor"))
    staged = pd.DataFrame(editor.value).copy()
    staged.loc[staged["제품정보"] == "Product-A", MONTH] = product_a_quantity
    app.session_state[PLAN_STAGED_KEY] = staged
    return staged


@pytest.mark.parametrize("edit_on_top", [False, True], ids=["staged-only", "edit-on-staged"])
def test_a_staged_plan_paste_survives_a_display_order_change(edit_on_top: bool) -> None:
    """붙여넣기 대기 표는 붙여넣은 차례 그대로 편집 원본이 되고 키로 적용된다 — 표시순서와 상관없다.

    전에는 차례가 바뀐 회차에 대기 표까지 버리고 「…(PKG PLAN 붙여넣기)을 다른 줄에 붙지 않게
    버렸습니다」라고 알렸다(2026-10-24 브라우저 E2E — 같은 세션에서 붙여넣기 → Admin 표시순서
    저장 → 생산 계획 복귀). 이제 대기 표와 그 위의 편집(대기 표 둘째 줄 Product-B)이 남고 알림이
    없으며, 적용은 제 제품에 든다.
    """
    editor_key = "pkg_plan_editor"
    second_row_edit = {"edited_rows": {1: {MONTH: 555.0}}, "added_rows": [], "deleted_rows": []}

    def resend_edit() -> None:
        # AppTest 는 세션에 넣은 편집표 값을 한 회차만 들고 있다 — 브라우저처럼 조작마다
        # 다시 보낸다.
        if edit_on_top:
            app.session_state[editor_widget_key_in(app, editor_key)] = second_row_edit

    app = AppTest.from_string(PLAN_ORDER_SWAP_TEST_SCRIPT, default_timeout=60)
    app.session_state["load_conversion_active_tab"] = PLAN_TAB
    app.run()
    assert not app.exception
    staged = _stage_plan_paste(app, 777.0)
    app.run()
    assert not app.exception
    resend_edit()
    app.run()
    assert not app.exception
    assert not _apply_disabled(app, "apply_pkg_plan_changes")
    before = _generation_in(app, editor_key)

    app.session_state["test_display_order_descending"] = True
    resend_edit()
    app.run()

    assert not app.exception
    assert not _notices(app)
    assert app.session_state[PLAN_STAGED_KEY] is staged
    # 편집표는 대기 표의 차례(붙여넣은 차례) 그대로다.
    assert _plan_products(app) == ["Product-A", "Product-B"]
    assert _generation_in(app, editor_key) == before
    assert not _apply_disabled(app, "apply_pkg_plan_changes")

    resend_edit()
    app.button(key="apply_pkg_plan_changes").click()
    app.run()

    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_PKG_PLAN"]
    assert dict(zip(saved["제품정보"], saved["생산수량"], strict=True)) == {
        "Product-A": 777.0,
        "Product-B": 555.0 if edit_on_top else 100.0,
    }


YIELD_TAB = ":material/percent: 수율"


def _yield_rows(app: AppTest) -> list[tuple[str, str]]:
    editor = next(
        frame
        for frame in app.dataframe
        if frame.proto.editing_mode and _is_editor(frame.proto.id, "yield_editor")
    )
    return [
        (str(product), str(kind))
        for product, kind in zip(editor.value["제품정보"], editor.value["수율 구분"], strict=True)
    ]


@pytest.mark.parametrize("descending", [True, False], ids=["order-changed", "order-held"])
def test_the_yield_editor_drops_an_unapplied_edit_only_when_the_order_changes(
    descending: bool,
) -> None:
    """수율 첫 줄(Product-A · BE)을 고친 채 「수율 변경사항 적용」을 누른다.

    표시순서가 뒤집힌 회차면 첫 줄이 Product-B 가 되므로 편집을 비우고 「…(수율)…」을 한 번
    알리며 적용하지 않는다. 그대로인 회차면 편집이 남아 Product-A 의 BE 수율에 든다.
    """
    editor_key = "yield_editor"
    app = AppTest.from_string(PLAN_ORDER_SWAP_TEST_SCRIPT, default_timeout=60)
    app.session_state["load_conversion_active_tab"] = YIELD_TAB
    app.run()
    assert not app.exception
    assert _yield_rows(app)[0] == ("Product-A", "BE")
    edit = _edit(MONTH, 0.5)
    app.session_state[editor_widget_key_in(app, editor_key)] = edit
    app.run()
    assert not app.exception
    assert not _apply_disabled(app, "apply_yield_changes")
    before = _generation_in(app, editor_key)

    app.session_state["test_display_order_descending"] = descending
    app.session_state[editor_widget_key_in(app, editor_key)] = edit
    app.button(key="apply_yield_changes").click()
    app.run()

    assert not app.exception
    if descending:
        assert _yield_rows(app)[0][0] == "Product-B"
        assert "test_month_updates" not in app.session_state
        assert _generation_in(app, editor_key) == before + 1
        assert _apply_disabled(app, "apply_yield_changes")
        notices = _notices(app)
        assert len(notices) == 1
        assert "(수율)" in notices[0]
        app.run()
        assert not _notices(app)
    else:
        assert not _notices(app)
        saved = app.session_state["test_month_updates"]["RQ_YLD"]
        assert dict(zip(saved["제품정보"], saved["BE_수율"], strict=True)) == {
            "Product-A": 0.5,
            "Product-B": 1.0,
        }


# 회차마다 `test_lock` 으로 잠글지를 정하는 단추 하나.
_DISABLED_BUTTON_SCRIPT = """
import streamlit as st

clicked = st.button("적용", key="apply", disabled=bool(st.session_state.get("test_lock")))
st.session_state["test_clicks"] = st.session_state.get("test_clicks", 0) + int(clicked)
"""


def test_streamlit_discards_a_click_on_a_button_drawn_disabled_in_that_run() -> None:
    """편집을 버린 회차에 함께 온 「적용」 클릭을 페이지가 따로 막지 않는 전제다.

    클릭은 단추가 열려 있던 화면에서 눌렸고, 그 회차에 페이지는 편집을 버려 단추를 잠가 그린다
    (`disabled=not pending`). Streamlit 1.63 은 잠겨 그린 위젯의 값을 서버에서 버린다. 이
    전제가 깨지면(Streamlit 판올림) 버린 편집 대신 원본을 「적용」해 리비전만 오른다 — 그때는
    페이지가 막아야 한다.
    """
    app = AppTest.from_string(_DISABLED_BUTTON_SCRIPT, default_timeout=30)
    app.run()
    app.button(key="apply").click()
    app.run()
    assert app.session_state["test_clicks"] == 1

    app.button(key="apply").click()
    app.session_state["test_lock"] = True
    app.run()

    assert not app.exception
    assert app.session_state["test_clicks"] == 1


# ------------------------------------------------------------------ 숫자 칸 증분


def _month_configs(app: AppTest, editor_key: str) -> dict[str, dict[str, Any]]:
    editor = next(
        frame
        for frame in app.dataframe
        if frame.proto.editing_mode and _is_editor(frame.proto.id, editor_key)
    )
    columns: dict[str, dict[str, Any]] = json.loads(editor.proto.columns)
    return {name: config for name, config in columns.items() if name.isdigit()}


# 기준 정보 그리드 표의 값 형식(껍데기 `fmt`) — (종류, 소수 자리, 상한). 증분(step)이 없어 값을
# 자르지 않는다 — 보이는 자리만 반올림하고 값은 적은 그대로다.
REFERENCE_FORMATS = {
    "효율": ("percent", 2, 1.0),
    "여유율": ("percent", 2, None),
    "Lot측정률": ("percent", 2, 1.0),
    "WF측정률": ("percent", 2, 1.0),
}
EQUIPMENT_TABLES = {"보유": "RQ_EQP_OWN", "대여": "RQ_EQP_LENT", "가용": "RQ_EQP_AVBL"}


@pytest.mark.parametrize("tab_name", list(REFERENCE_FORMATS))
def test_ratio_grids_keep_the_percent_format_and_take_fractions_as_written(
    tab_name: str, grid_calls: Calls
) -> None:
    kind, digits, top = REFERENCE_FORMATS[tab_name]
    app = AppTest.from_string(TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state[DATASET_KEY] = DATASET[tab_name]
    app.run()
    assert not app.exception

    fmt = last(grid_calls, GRID_HOST)["fmt"]
    assert (fmt["kind"], fmt["digits"], fmt["max"]) == (kind, digits, top)
    key = _visible_keys(grid_calls)[0]
    app = _grid_write(app, grid_calls, key, MONTH, "0.9875")
    table = DATASET[tab_name]
    assert app.session_state[cells_key(table)]["cells"] == {key: {MONTH: 0.9875}}


@pytest.mark.parametrize("tab_name", list(EQUIPMENT_TABLES))
def test_equipment_count_grids_keep_two_decimals_and_a_third_of_a_module(
    tab_name: str, grid_calls: Calls
) -> None:
    app = AppTest.from_string(TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state[DATASET_KEY] = DATASET[f"설비대수 {tab_name}"]
    app.run()
    assert not app.exception

    fmt = last(grid_calls, GRID_HOST)["fmt"]
    assert (fmt["kind"], fmt["digits"], fmt["blankZero"]) == ("fixed", 2, True)
    app = _grid_write(app, grid_calls, "Process-A", MONTH, "0.333")
    assert app.session_state[cells_key(EQUIPMENT_TABLES[tab_name])]["cells"] == {
        "Process-A": {MONTH: 0.333}
    }


def test_the_run_day_grid_takes_whole_days_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """일수는 새 편집 그리드에서 정수만 받는다(옛 편집표는 1일 증분으로 소수를 말없이 버렸다 — 이제
    소수는 칸 오류다). 표시는 천 단위 + 소수 없음."""
    calls = install_fake_edit_grid(monkeypatch)
    app = AppTest.from_string(TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state[DATASET_KEY] = DATASET["일수"]
    app.run()
    assert not app.exception
    shell = last(calls, GRID_HOST)
    assert shell["table"] == "RQ_RUN_DAY"
    assert (shell["fmt"]["kind"], shell["fmt"]["digits"], shell["fmt"]["int"]) == ("fixed", 0, True)
    assert not any(widget.key == "capa_run_day_editor" for widget in app.dataframe)


def test_the_yield_and_plan_editors_keep_their_formats() -> None:
    """수율은 증분 없이 `percent`, PKG PLAN 은 그 단위로 충분해 0.01 증분 그대로다."""
    script = TEST_SCRIPT.replace(
        'PAGE_NAME = "reference_data.py"', 'PAGE_NAME = "load_conversion.py"'
    )
    app = AppTest.from_string(script, default_timeout=60)
    app.session_state["load_conversion_active_tab"] = PLAN_TAB
    app.run()
    assert not app.exception

    yield_configs = _month_configs(app, "yield_editor")
    assert yield_configs
    for config in yield_configs.values():
        assert "step" not in config["type_config"], config
        assert config["type_config"]["format"] == "percent"
    plan_configs = _month_configs(app, "pkg_plan_editor")
    assert plan_configs
    assert all(config["type_config"]["step"] == 0.01 for config in plan_configs.values())


def test_an_all_integer_month_table_takes_a_fraction_on_the_grid(grid_calls: Calls) -> None:
    """정수만 붙여넣어 정수 dtype 이 된 표도 소수를 받는다 — 그리드는 값 칸을 실수 행렬로 다루고
    증분이 없어 0.333 대가 그대로 적용된다."""
    script = TWO_PROCESS_TEST_SCRIPT.replace(
        '{"생산계획년월": [202608], "공정": ["Process-A"], "설비보유": [2.0]}',
        '{"생산계획년월": [202608], "공정": ["Process-A"], "설비보유": [2]}',
        1,
    )
    assert script != TWO_PROCESS_TEST_SCRIPT
    app = AppTest.from_string(script, default_timeout=60)
    app.session_state[DATASET_KEY] = DATASET["설비대수 보유"]
    app.run()
    assert not app.exception

    app = _grid_write(app, grid_calls, "Process-A", MONTH, "0.333")
    app.button(key="capa_eqp_own_editor_apply").click().run()
    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_EQP_OWN"]
    assert dict(zip(saved["공정"], saved["설비보유"], strict=True))["Process-A"] == 0.333


def test_float_month_columns_only_touches_integer_month_columns() -> None:
    table = pd.DataFrame(
        {
            "공정": ["A", "B"],
            "202608": [1, 2],
            "202609": pd.array([1, None], dtype="Int64"),
            "202610": [0.5, 1.0],
        }
    )

    result = month_editor.float_month_columns(table, ["202608", "202609", "202610"])

    assert result["202608"].dtype == "float64"
    assert result["202609"].dtype == "float64"
    assert pd.isna(result.loc[1, "202609"])
    assert result["공정"].dtype == table["공정"].dtype
    same = pd.DataFrame({"202610": [0.5]})
    assert month_editor.float_month_columns(same, ["202610"]) is same


def test_the_equipment_baseline_count_column_carries_no_step() -> None:
    """설비 기존 보유대수 칸은 1/3 모듈(0.333…)도 그대로 받는다 — 보이는 자리만 소수 둘째 자리다."""
    source = (ROOT / "src/capa_simulation/components/equipment_data_workspace.py").read_text(
        encoding="utf-8"
    )
    configs = [
        value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(key, ast.Constant)
        and key.value == "기존보유대수"
        and isinstance(value, ast.Call)
    ]
    assert configs, (
        "기존 보유대수 칸 설정을 찾지 못했습니다 — 화면 구조가 바뀌었으면 이 검사부터 고칩니다."
    )
    for call in configs:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        assert "step" not in keywords
        fmt = keywords["format"]
        assert isinstance(fmt, ast.Constant) and fmt.value == "%.2f 대"
