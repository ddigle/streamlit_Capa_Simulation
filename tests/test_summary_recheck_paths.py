# Purpose: Summary 가 쓰는 공용 프로필을 저장하는 길마다 그 세션의 요약 확인을 비우는지 검증한다.

"""저장 뒤 곧바로 다시 확인해야 Summary 가 새 값을 싣는다.

요약은 세션에 `RECHECK_SECONDS` 동안 들고 있는 값을 보낸다. 판정 기준·선행 B/O·선행 입고 실적·비교
대상을 저장하거나 비교 대상이 걸린 시나리오를 보관·삭제·이름 변경하면 그 세션의 확인을 비워
(`forget_intro_summary_check`) 다음 회차가 새 값을 보게 한다. 저장 콜백을 직접 불러 세션 칸
(`intro_summary._SESSION_KEY`)이 비었는지 본다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
import streamlit as st

from capa_simulation.components import home_preference, intro_summary, scenario_management
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


def test_choosing_a_comparison_rechecks_the_summary(
    session: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Repo()
    monkeypatch.setattr(home_preference, "get_scenario_repository", lambda path: repo)
    session[home_preference.COMPARISON_SCENARIO_KEY] = "S"
    session[home_preference.COMPARISON_REVISION_KEY] = "R"
    home_preference._save_comparison_choice(DB)
    assert repo.calls == ["replace_global_comparison_scenario"] and _forgotten(session)


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
    with pytest.raises(_Rerun):
        scenario_management._render_archive(repo, SUMMARY)  # type: ignore[arg-type]
    assert repo.calls == ["archive_scenario"] and _forgotten(scenario_ui)


def test_deleting_a_scenario_rechecks_the_summary(
    scenario_ui: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Repo()
    monkeypatch.setattr(st, "text_input", lambda *args, **kwargs: SUMMARY.scenario_name)
    monkeypatch.setattr(repo, "count_official_releases", lambda scenario_id: 0, raising=False)
    with pytest.raises(_Rerun):
        scenario_management._render_delete(repo, SUMMARY)  # type: ignore[arg-type]
    assert "delete_scenario" in repo.calls and _forgotten(scenario_ui)


def test_renaming_a_scenario_rechecks_the_summary(
    scenario_ui: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """비교 대상의 이름이 바뀌면 GAP 풍선의 이름도 바뀌어야 한다(저장소가 비교 프로필 version 을
    올리고, 이 세션은 곧바로 다시 확인한다)."""
    repo = _Repo()
    monkeypatch.setattr(st, "text_input", lambda *args, **kwargs: "새 이름")
    with pytest.raises(_Rerun):
        scenario_management._render_rename(repo, SUMMARY)  # type: ignore[arg-type]
    assert repo.calls == ["rename_scenario"] and _forgotten(scenario_ui)
