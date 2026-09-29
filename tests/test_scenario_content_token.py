# Purpose: 편집 없는 저장 리비전은 세션이 달라도 같은 계산 캐시 토큰을 쓰는지 검증한다.

"""**새로고침할 때마다 HOME 계산이 처음부터 다시 돌았다.**

`content_token` 은 계산 캐시 키의 일부다. 예전에는 저장 리비전을 올릴 때마다 uuid 를 새로
발급해서, 같은 공식버전을 여는데도 새 세션(새로고침·다른 사용자)마다 캐시가 빗나갔다.
70공정 합성 표본에서 새로고침 6.2초 중 4.1초가 그 재계산이었다(샘플 관측).

리비전은 append-only 라 편집 전 내용은 리비전 하나로 정해진다. 그래서 그 상태만 고정
토큰을 쓰고, 편집이 들어가는 순간 지금처럼 새 토큰으로 갈라진다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from capa_simulation import scenario_state

TABLES = {
    name: pd.DataFrame({"생산계획년월": [202601], "값": [1.0]})
    for name in scenario_state.EDITABLE_SCENARIO_TABLES
}


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    fake = SimpleNamespace(session_state={})
    monkeypatch.setattr(scenario_state, "st", fake)
    return fake


def _activate(reference_version: int) -> scenario_state.ActiveScenario:
    return scenario_state.activate_scenario_tables(
        TABLES, reference_version=reference_version, revision=3
    )


def test_the_same_revision_shares_one_token_across_sessions(session: SimpleNamespace) -> None:
    first = _activate(7)["content_token"]
    session.session_state.clear()  # 다른 브라우저 세션

    assert _activate(7)["content_token"] == first
    assert _activate(8)["content_token"] != first


def test_an_edit_leaves_the_shared_token_and_a_reset_returns_to_it(
    session: SimpleNamespace,
) -> None:
    pristine = _activate(7)

    edited = scenario_state.apply_table_updates(pristine, {"RQ_CHIP_QTY": TABLES["RQ_CHIP_QTY"]})
    reset = scenario_state.reset_active_scenario(TABLES, 7)

    assert edited["content_token"] != pristine["content_token"]
    assert reset["content_token"] == pristine["content_token"]


def test_the_shared_token_cannot_collide_with_an_edit_token(session: SimpleNamespace) -> None:
    """편집 토큰은 uuid hex 다. 고정 토큰이 그 모양이면 편집본과 캐시 칸이 섞일 수 있다."""
    pristine = _activate(7)["content_token"]

    assert not all(character in "0123456789abcdef" for character in pristine)


def test_discarding_edits_leaves_nothing_unsaved(
    session: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """사이드바 「편집 되돌리기」 뒤에는 미저장이 아니다(2026-09-29 2차 리뷰에서 재현한 결함).

    되돌리기는 표를 올라와 있는 리비전의 표로 갈아 끼우면서 `revision` 을 올린다. 그 번호를 저장
    표시에 적지 않으면 내용이 저장본과 같은데도 미저장으로 읽혀 버튼·배지·불러오기 잠금이 남는다.
    """
    from capa_simulation import scenario_activation

    monkeypatch.setattr(scenario_activation, "st", session)
    pristine = _activate(7)
    session.session_state[scenario_activation.ACTIVE_PERSISTED_SESSION_REVISION_KEY] = pristine[
        "revision"
    ]
    scenario_state.apply_table_updates(pristine, {"RQ_CHIP_QTY": TABLES["RQ_CHIP_QTY"]})
    assert scenario_activation.has_unsaved_scenario_changes()

    reset = scenario_activation.discard_unsaved_scenario_changes(TABLES, 7)

    assert not scenario_activation.has_unsaved_scenario_changes()
    assert reset["content_token"] == pristine["content_token"]
    # 편집 UI 는 번호로 새로 선다 — 되돌리기가 번호를 되감지는 않는다.
    assert reset["revision"] > pristine["revision"]


def test_discarding_without_a_saved_revision_invents_no_saved_mark(
    session: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """저장본이 없는 세션(내장 시드)에는 되돌아갈 저장본이 없다. 저장 표시를 새로 만들지 않는다."""
    from capa_simulation import scenario_activation

    monkeypatch.setattr(scenario_activation, "st", session)
    _activate(7)

    scenario_activation.discard_unsaved_scenario_changes(TABLES, 7)

    assert scenario_activation.ACTIVE_PERSISTED_SESSION_REVISION_KEY not in session.session_state
