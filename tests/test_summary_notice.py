# Purpose: HOME Summary 공지의 공용 프로필 저장·표시 규칙을 고정한다.

"""Summary 공지 계약.

시나리오와 분리된 공용 프로필이다. 여러 사람이 같은 문구를 보고, 시나리오를 바꿔도
그대로 남는다. 계산에는 들어가지 않는 **화면 문구**라 Figure 캐시 키에도 없다.

**빈 문구와 미저장은 다르다.** 빈 문구는 「공지를 내렸다」는 결정이고 미저장은 아직
아무도 손대지 않은 상태다. 화면은 둘 다 아무것도 띄우지 않지만 저장 화면은 구분해야
하고, 내리는 것도 version 이 올라야 다른 세션의 캐시가 풀린다.
"""

from __future__ import annotations

import html
from collections.abc import Iterator
from pathlib import Path

import pytest
import streamlit as st

from capa_simulation.components.home_rendering import render_summary_notice
from capa_simulation.persistence.repository import DuckDBScenarioRepository


def _repository(path: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(path)
    assert repository.initialize()
    return repository


def test_an_unsaved_profile_reads_as_an_empty_notice(tmp_path: Path) -> None:
    """한 번도 저장하지 않은 상태가 정상이다. 여기서 죽으면 첫 저장 전까지 HOME 이 안 열린다."""
    profile = _repository(tmp_path / "scenario.duckdb").load_global_summary_note()

    assert (profile.version, profile.note, profile.updated_at) == (0, "", None)
    assert not profile.is_visible


def test_saving_a_notice_bumps_the_version(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "scenario.duckdb")

    first = repository.replace_global_summary_note("9월 물량 확정 전", source="웹 직접 편집")
    second = repository.replace_global_summary_note("10월 물량 확정", source="웹 직접 편집")

    assert (first.version, second.version) == (1, 2)
    assert second.note == "10월 물량 확정"
    assert repository.load_global_summary_note().note == "10월 물량 확정"


def test_taking_the_notice_down_is_itself_a_saved_decision(tmp_path: Path) -> None:
    """빈 문구를 막으면 공지를 내릴 방법이 없다. version 도 올라야 캐시가 풀린다."""
    repository = _repository(tmp_path / "scenario.duckdb")
    repository.replace_global_summary_note("임시 공지", source="웹 직접 편집")

    taken_down = repository.replace_global_summary_note("", source="웹 직접 편집")

    assert taken_down.version == 2
    assert taken_down.note == ""
    assert not taken_down.is_visible


def test_a_blank_only_notice_is_not_shown(tmp_path: Path) -> None:
    """공백만 남은 글은 화면에서 빈 상자가 된다. 저장은 되지만 띄우지는 않는다."""
    repository = _repository(tmp_path / "scenario.duckdb")

    saved = repository.replace_global_summary_note("   \n  ", source="웹 직접 편집")

    assert saved.version == 1
    assert not saved.is_visible


# ------------------------------------------------------------------ 화면 표시


def test_an_empty_notice_draws_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """내용이 없으면 상자 자체를 그리지 않는다. 늘 비어 있는 `Summary` 는 잡음이다."""
    drawn: list[str] = []
    _stub_streamlit(monkeypatch, drawn)

    render_summary_notice("")
    render_summary_notice("   ")

    assert drawn == []


def test_a_notice_is_collapsed_by_default_and_keeps_the_text_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """펼친 채로 뜨면 긴 글 하나가 대시보드를 화면 밖으로 민다.

    글은 원문 그대로다 — 마크다운으로 넘기면 줄 앞의 `#` 이 제목이 되어 적은 사람이
    보던 글과 달라지고, 태그를 적으면 그대로 실행된다.
    """
    drawn: list[str] = []
    expanded: list[bool] = []
    _stub_streamlit(monkeypatch, drawn, expanded)

    render_summary_notice("# 9월 계획\n<b>확정 전</b>")

    assert expanded == [False]
    body = "\n".join(drawn)
    assert html.escape("<b>확정 전</b>") in body
    assert "<b>확정 전</b>" not in body.replace(html.escape("<b>확정 전</b>"), "")
    # 줄바꿈과 들여쓰기는 CSS 가 살린다. `<br>` 로 바꾸면 공백 들여쓰기가 사라진다.
    assert "white-space: pre-wrap" in body


def _stub_streamlit(
    monkeypatch: pytest.MonkeyPatch, drawn: list[str], expanded: list[bool] | None = None
) -> None:
    """`render_summary_notice` 가 부르는 Streamlit 조각만 가로챈다."""
    from contextlib import contextmanager

    @contextmanager
    def fake_expander(label: str, *, expanded: bool = False) -> Iterator[None]:
        assert label == "Summary"
        if expanded_log is not None:
            expanded_log.append(expanded)
        yield

    @contextmanager
    def fake_container(**_: object) -> Iterator[None]:
        yield

    expanded_log = expanded
    monkeypatch.setattr(st, "html", drawn.append)
    monkeypatch.setattr(st, "markdown", lambda text, **_: drawn.append(text))
    monkeypatch.setattr(st, "expander", fake_expander)
    monkeypatch.setattr(st, "container", fake_container)
