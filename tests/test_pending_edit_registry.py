# Purpose: 적용하지 않은 편집 목록이 지금 화면 편집표와 붙여넣기 대기분을 세는지 검사한다.

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from capa_simulation.components import editor_state, scenario_edit_bar

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EDIT = {"edited_rows": {0: {"202608": 1.0}}, "added_rows": [], "deleted_rows": []}


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    fake = SimpleNamespace(session_state={})
    monkeypatch.setattr(scenario_edit_bar, "st", fake)
    monkeypatch.setattr(editor_state, "st", fake)
    return fake


def _register(session: SimpleNamespace) -> None:
    scenario_edit_bar.register_pending_edits(
        "reference_data.py", "기준 정보", {"upeh_editor": "UPEH", "run_day_editor": "일수"}
    )
    scenario_edit_bar.register_pending_edits(
        "load_conversion.py",
        "생산 계획",
        {"plan_editor": "PKG PLAN"},
        staged={"plan_staged": "PKG PLAN 붙여넣기"},
    )


def test_only_the_edited_tables_of_the_current_page_are_named(session: SimpleNamespace) -> None:
    _register(session)
    session.session_state["upeh_editor"] = EDIT
    session.session_state["plan_editor"] = EDIT

    assert scenario_edit_bar.pending_edit_labels("reference_data.py") == ["기준 정보 · UPEH"]


def test_another_pages_editor_does_not_count(session: SimpleNamespace) -> None:
    """편집표의 편집은 위젯 상태라 화면을 옮기면 버려진다 — 다른 화면의 것은 세지 않는다."""
    _register(session)
    session.session_state["plan_editor"] = EDIT

    assert scenario_edit_bar.pending_edit_labels("home.py") == []


def test_a_staged_paste_counts_on_every_page(session: SimpleNamespace) -> None:
    """붙여넣기 대기분은 위젯이 아닌 세션 칸이라 화면을 옮겨도 남는다. 어디서나 센다."""
    _register(session)
    session.session_state["plan_staged"] = object()

    assert scenario_edit_bar.pending_edit_labels("home.py") == ["생산 계획 · PKG PLAN 붙여넣기"]


def test_a_discarded_editor_no_longer_counts(session: SimpleNamespace) -> None:
    """편집 취소는 위젯 키를 바꾼다. 새 키에는 편집이 없다."""
    _register(session)
    session.session_state["upeh_editor"] = EDIT
    editor_state.discard_editor("upeh_editor")

    assert scenario_edit_bar.pending_edit_labels("reference_data.py") == []


def test_the_table_the_page_just_applied_is_not_named(session: SimpleNamespace) -> None:
    """적용한 회차 다음 회차에는 사이드바가 **페이지보다 먼저** 돈다(2026-10-01 브라우저 E2E).

    그때는 방금 적용한 편집표가 아직 버려지지 않아 옛 편집이 세션에 남아 있다. 그것을 「적용 전
    편집」으로 세면 저장 팝업이 버릴 것도 없는 확인 체크를 요구하며 저장을 잠갔다. 페이지가
    `mark_own_change` 로 적어 둔 표와 붙여넣기 대기는 빼고, 다른 표의 적용 전 편집은 그대로 센다.
    """
    scenario_edit_bar.register_pending_edits(
        "reference_data.py",
        "기준 정보",
        {"upeh_editor": "UPEH", "run_day_editor": "일수"},
        own_change_key="reference_own_change",
    )
    scenario_edit_bar.register_pending_edits(
        "load_conversion.py",
        "생산 계획",
        {"plan_editor": "PKG PLAN"},
        staged={"plan_staged": "PKG PLAN 붙여넣기"},
        own_change_key="plan_own_change",
    )
    session.session_state["upeh_editor"] = EDIT
    session.session_state["run_day_editor"] = EDIT
    session.session_state["plan_staged"] = object()
    scenario_edit_bar.mark_own_change("reference_own_change", ("upeh_editor",))
    scenario_edit_bar.mark_own_change("plan_own_change", ("plan_editor", "plan_staged"))

    assert scenario_edit_bar.pending_edit_labels("reference_data.py") == ["기준 정보 · 일수"]
    assert scenario_edit_bar.pending_edit_labels("home.py") == []

    # 페이지가 그 적용을 처리하면(표를 버리고 표시를 지우면) 다시 평소대로 센다.
    scenario_edit_bar.reset_editors_on_source_change(
        "reference_token",
        "new",
        ("upeh_editor", "run_day_editor"),
        own_change_key="reference_own_change",
    )
    session.session_state["upeh_editor__g1"] = EDIT

    assert scenario_edit_bar.pending_edit_labels("reference_data.py") == [
        "기준 정보 · UPEH",
        "기준 정보 · 일수",
    ]


def test_a_record_written_before_own_change_keys_still_reads(session: SimpleNamespace) -> None:
    """서버를 띄운 채 코드를 바꾸면 세션에 옛 세 칸짜리 기록이 남는다. 사이드바는 멈추지 않는다."""
    session.session_state["scenario_pending_edit_registry"] = {
        "reference_data.py": ("기준 정보", {"upeh_editor": "UPEH"}, {}),
    }
    session.session_state["upeh_editor"] = EDIT

    assert scenario_edit_bar.pending_edit_labels("reference_data.py") == ["기준 정보 · UPEH"]


def test_each_page_registers_under_its_own_file_name() -> None:
    """사이드바는 지금 화면의 파일 이름으로 찾는다. 페이지가 다른 이름으로 적으면 조용히 꺼진다."""
    found = {}
    for path in (PROJECT_ROOT / "app_pages").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "register_pending_edits"
            ):
                first = node.args[0]
                assert isinstance(first, ast.Constant), path.name
                found[path.name] = first.value

    assert found == {
        "reference_data.py": "reference_data.py",
        "load_conversion.py": "load_conversion.py",
    }
