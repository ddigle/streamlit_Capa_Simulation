# Purpose: Summary 가 쓰는 공용 프로필을 저장하는 길마다 그 세션의 요약 확인을 비우는지 검증한다.

"""저장 뒤 곧바로 다시 확인해야 Summary 가 새 값을 싣는다.

요약은 세션에 `RECHECK_SECONDS` 동안 들고 있는 값을 보낸다. 판정 기준·선행 B/O·선행 입고 실적·비교
대상·표시순서·공정 표시명을 저장하거나 비교 대상이 걸린 시나리오를 보관·삭제·이름 변경하면 그 세션의
확인을 비워(`forget_intro_summary_check`) 다음 회차가 새 값을 보게 한다. 저장 콜백을 직접 불러
세션 칸(`intro_summary._SESSION_KEY`)이 비었는지 본다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
import streamlit as st

from capa_simulation.components import (
    display_order_management,
    home_preference,
    intro_summary,
    process_rename_management,
    scenario_management,
)
from capa_simulation.services.advance_load import empty_advance_load
from capa_simulation.services.advance_shipment import empty_advance_shipment

DB = "db"


class _Repo:
    """저장 메서드는 무엇이든 받아 적기만 한다."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        def record(*args: object, **kwargs: object) -> SimpleNamespace:
            self.calls.append(name)
            return SimpleNamespace(scenario_id="S", scenario_name="새 이름")

        return record


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    state: dict[str, Any] = {intro_summary._SESSION_KEY: {"checked_at": 0.0, "data": {}}}
    monkeypatch.setattr(st, "session_state", state)
    for name in (
        "clear_global_comparison_scenario_cache",
        "clear_global_advance_load_cache",
        "clear_global_advance_shipment_cache",
        "clear_global_securement_threshold_cache",
    ):
        monkeypatch.setattr(home_preference, name, lambda: None)
    yield state


def _forgotten(state: dict[str, Any]) -> bool:
    return intro_summary._SESSION_KEY not in state


class _ComparisonRepo(_Repo):
    """비교 저장 콜백이 받은 값이 실제 id 인지 볼 때 읽는 두 목록. 읽기는 적지 않는다."""

    def list_scenarios(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(scenario_id="S")]

    def list_revisions(self, scenario_id: str) -> list[SimpleNamespace]:
        return [SimpleNamespace(revision_id="R")]


@pytest.mark.parametrize("callback", ["_save_comparison_scenario", "_save_comparison_revision"])
def test_choosing_a_comparison_rechecks_the_summary(
    session: dict[str, Any], monkeypatch: pytest.MonkeyPatch, callback: str
) -> None:
    """비교 시나리오·리비전 상자의 저장 콜백은 각자 공용 프로필을 쓰고 Summary 확인을 비운다."""
    repo = _ComparisonRepo()
    monkeypatch.setattr(home_preference, "get_scenario_repository", lambda path: repo)
    monkeypatch.setattr(
        home_preference,
        "load_global_comparison_scenario",
        lambda path: SimpleNamespace(scenario_id=None, revision_id=None),
    )
    session[home_preference.COMPARISON_SCENARIO_KEY] = "S"
    session[home_preference.COMPARISON_REVISION_KEY] = "R"
    getattr(home_preference, callback)(DB)
    assert repo.calls == ["replace_global_comparison_scenario"] and _forgotten(session)


def test_an_unchanged_comparison_choice_neither_writes_nor_rechecks(
    session: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """프로필과 같은 짝이면 쓰지 않으므로 Summary 를 다시 확인할 까닭도 없다."""
    repo = _ComparisonRepo()
    monkeypatch.setattr(home_preference, "get_scenario_repository", lambda path: repo)
    monkeypatch.setattr(
        home_preference,
        "load_global_comparison_scenario",
        lambda path: SimpleNamespace(scenario_id="S", revision_id="R"),
    )
    session[home_preference.COMPARISON_SCENARIO_KEY] = "S"
    session[home_preference.COMPARISON_REVISION_KEY] = "R"
    home_preference._save_comparison_revision(DB)
    assert repo.calls == [] and not _forgotten(session)


def test_filling_the_comparison_revision_rechecks_the_summary(
    session: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Repo()
    monkeypatch.setattr(home_preference, "get_scenario_repository", lambda path: repo)
    monkeypatch.setattr(
        home_preference,
        "load_global_comparison_scenario",
        lambda path: SimpleNamespace(scenario_id="S", revision_id=None),
    )
    session[home_preference.COMPARISON_SCENARIO_KEY] = "S"
    session[home_preference.COMPARISON_REVISION_KEY] = "R"
    home_preference._persist_comparison_choice(DB, {"R"})
    assert repo.calls == ["replace_global_comparison_scenario"] and _forgotten(session)


def test_saving_thresholds_rechecks_the_summary(
    session: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Repo()
    monkeypatch.setattr(home_preference, "get_scenario_repository", lambda path: repo)
    monkeypatch.setattr(home_preference, "_reject_hidden_reversed_months", lambda *args: None)
    home_preference._save_thresholds(
        DB,
        months=[],
        month_labels=[],
        edited=None,
        default_secure=109.5,
        default_warning=99.5,
        threshold_profile=SimpleNamespace(rows=pd.DataFrame()),  # type: ignore[arg-type]
        expected_version=1,
        source="시험",
    )
    assert repo.calls == ["replace_global_securement_threshold"] and _forgotten(session)


@pytest.mark.parametrize(
    ("render", "profile_name", "rows", "store"),
    [
        (
            "_render_advance_editor",
            "advance_profile",
            empty_advance_load(),
            "replace_global_advance_load",
        ),
        (
            "render_advance_shipment_editor",
            "advance_shipment_profile",
            empty_advance_shipment(),
            "replace_global_advance_shipment",
        ),
    ],
)
def test_saving_a_monthly_amount_profile_rechecks_the_summary(
    session: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    render: str,
    profile_name: str,
    rows: pd.DataFrame,
    store: str,
) -> None:
    repo = _Repo()
    captured: dict[str, Any] = {}
    monkeypatch.setattr(home_preference, "get_scenario_repository", lambda path: repo)
    monkeypatch.setattr(
        home_preference,
        "_render_monthly_amount_editor",
        lambda *args, **kwargs: captured.update(kwargs),
    )
    getattr(home_preference, render)(
        months=[202610],
        month_labels=["26.10"],
        database_path=DB,
        **{profile_name: SimpleNamespace(rows=rows, version=0)},
    )
    captured["save"]([1.5], "시험")
    assert repo.calls == [store] and _forgotten(session)


class _DisplayOrderRepo(_Repo):
    """표시순서 교체는 저장한 프로필을 돌려주고 화면은 그 `rules` 를 곧바로 적용한다."""

    def replace_global_display_order(self, *args: object, **kwargs: object) -> SimpleNamespace:
        self.calls.append("replace_global_display_order")
        return SimpleNamespace(rules=pd.DataFrame())


class _FailingRepo:
    """저장 메서드가 모두 실패한다."""

    def __getattr__(self, name: str) -> Any:
        def fail(*args: object, **kwargs: object) -> None:
            raise ValueError("저장 실패")

        return fail


@pytest.fixture
def admin_profile_savers(monkeypatch: pytest.MonkeyPatch) -> dict[str, Callable[[Any], None]]:
    """Admin Area 의 표시순서·공정 표시명 저장 함수. 검증·캐시·적용은 비워 저장 사슬만 남긴다."""
    monkeypatch.setattr(
        display_order_management, "validate_display_order", lambda frame, **kwargs: frame
    )
    monkeypatch.setattr(display_order_management, "clear_global_display_order_cache", lambda: None)
    monkeypatch.setattr(display_order_management, "apply_global_display_order", lambda rules: None)
    monkeypatch.setattr(
        process_rename_management, "prepare_process_rename_rules", lambda frame: frame
    )
    monkeypatch.setattr(
        process_rename_management, "clear_global_process_rename_cache", lambda: None
    )
    return {
        "replace_global_display_order": lambda repo: (
            display_order_management._save_global_display_order(repo, pd.DataFrame(), source="시험")
        ),
        "replace_global_process_rename": lambda repo: (
            process_rename_management._save_process_rename(repo, pd.DataFrame(), source="시험")
        ),
    }


ADMIN_PROFILE_STORES = ["replace_global_display_order", "replace_global_process_rename"]


@pytest.mark.parametrize("store", ADMIN_PROFILE_STORES)
def test_saving_display_order_or_process_names_rechecks_the_summary(
    session: dict[str, Any], admin_profile_savers: dict[str, Callable[[Any], None]], store: str
) -> None:
    """Summary 는 표시순서·공정 표시명 version 을 요약 키에 넣고 그 차례·표시명으로 그린다."""
    repo = _DisplayOrderRepo()
    admin_profile_savers[store](repo)
    assert repo.calls == [store] and _forgotten(session)


@pytest.mark.parametrize("store", ADMIN_PROFILE_STORES)
def test_a_failed_display_order_or_process_name_save_keeps_the_summary_check(
    session: dict[str, Any], admin_profile_savers: dict[str, Callable[[Any], None]], store: str
) -> None:
    """저장이 실패하면 바뀐 것이 없으니 들고 있는 요약을 그대로 둔다."""
    with pytest.raises(ValueError, match="저장 실패"):
        admin_profile_savers[store](_FailingRepo())
    assert not _forgotten(session)


class _Rerun(Exception):
    pass


def _raise_rerun() -> None:
    raise _Rerun


@contextmanager
def _form(*args: object, **kwargs: object) -> Iterator[None]:
    yield


@pytest.fixture
def scenario_ui(session: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """시나리오 관리 칸의 위젯을 「누름」으로 바꿔 끼운다."""
    for name in ("info", "warning", "error"):
        monkeypatch.setattr(st, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "checkbox", lambda *args, **kwargs: True)
    monkeypatch.setattr(st, "button", lambda *args, **kwargs: True)
    monkeypatch.setattr(st, "form_submit_button", lambda *args, **kwargs: True)
    monkeypatch.setattr(st, "form", _form)
    monkeypatch.setattr(st, "rerun", _raise_rerun)
    for name in (
        "clear_scenario_snapshot_cache",
        "clear_global_comparison_scenario_cache",
        "clear_global_securement_threshold_cache",
        "clear_persisted_scenario_activation",
        "discard_editor",
        "rename_active_scenario_label",
    ):
        monkeypatch.setattr(scenario_management, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(scenario_management, "active_persisted_scenario_id", lambda: None)
    return session


SUMMARY = SimpleNamespace(scenario_id="S", scenario_name="DEMO")


def test_archiving_a_scenario_rechecks_the_summary(
    scenario_ui: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Repo()
    # 최신 공식버전의 시나리오면 보관 칸이 안내만 그린다. 여기서는 보관할 수 있는 시나리오다.
    monkeypatch.setattr(repo, "latest_official_release", lambda: None, raising=False)
    with pytest.raises(_Rerun):
        scenario_management._render_archive(repo, SUMMARY)  # type: ignore[arg-type]
    assert repo.calls == ["archive_scenario"] and _forgotten(scenario_ui)


def test_deleting_a_scenario_rechecks_the_summary(
    scenario_ui: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Repo()
    monkeypatch.setattr(st, "text_input", lambda *args, **kwargs: SUMMARY.scenario_name)
    monkeypatch.setattr(repo, "count_official_releases", lambda scenario_id: 0, raising=False)
    monkeypatch.setattr(repo, "list_revisions", lambda scenario_id: [SUMMARY], raising=False)
    with pytest.raises(_Rerun):
        scenario_management._render_delete(repo, SUMMARY)  # type: ignore[arg-type]
    assert "delete_scenario" in repo.calls and _forgotten(scenario_ui)


def test_renaming_a_scenario_rechecks_the_summary(
    scenario_ui: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """비교 대상의 이름이 바뀌면 GAP 풍선의 이름도 바뀌어야 한다(저장소가 비교 프로필 version 을
    올리고, 이 세션은 곧바로 다시 확인한다). 이름은 목록 표에서 고쳐 「변경 저장」으로 쓴다."""
    from capa_simulation.components.pick_edit_table import TableDraft

    repo = _Repo()
    monkeypatch.setattr(scenario_management, "get_scenario_repository", lambda path: repo)
    monkeypatch.setattr(scenario_management, "pinned_connections", lambda path: nullcontext())
    monkeypatch.setattr(
        scenario_management, "peek_table", lambda *args: TableDraft(names={"S": "새 이름"})
    )
    monkeypatch.setattr(scenario_management, "forget_table_edits", lambda key: None)
    scenario_management._save_list_edits(DB, ("S",), {"S": SUMMARY.scenario_name})
    assert repo.calls == ["apply_scenario_list_edits"] and _forgotten(scenario_ui)
