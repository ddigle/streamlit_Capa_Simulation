# Purpose: 공용 표시순서 준비 결과 캐시가 직접 준비한 값과 같고 내용이 바뀌면 다시 준비하는지 본다.

"""`simulation_cache.get_prepared_display_order` 의 회귀 검사.

계산 화면 공통 진입(`load_page_context`)이 회차마다 표시순서 규칙을 다시 검증·파생하던 것을 내용
지문 키 캐시로 바꿨다. 키가 `reference_version` 이 아니라 **내용**이어야 Admin 의 표시순서 교체
(버전은 그대로)를 놓치지 않는다.
"""

from __future__ import annotations

import uuid

import pandas as pd
import pytest

import capa_simulation.services.display_order as display_order_module
from capa_simulation.services.display_order import (
    PreparedDisplayOrder,
    apply_display_order,
    prepare_display_order,
)
from capa_simulation.services.simulation_cache import get_prepared_display_order

PAGE = "기준 정보"
TAB = "UPEH"


def _rules(mode: str = "오름차순", *, tag: str | None = None) -> pd.DataFrame:
    """공정 정렬 하나와 `WF 구분` 사용자지정(Top·Buffer — 앱이 `Top_e` 를 파생한다).

    캐시는 프로세스 전역이라 테스트마다 다른 내용(`tag`)으로 가른다.
    """
    marker = tag or uuid.uuid4().hex
    return pd.DataFrame(
        [
            (PAGE, TAB, 1, "공정", mode, "", None, "Y"),
            (PAGE, TAB, 2, "WF 구분", "사용자지정", "Top", 1, "Y"),
            (PAGE, TAB, 2, "WF 구분", "사용자지정", "Buffer", 2, "Y"),
            (PAGE, f"미사용-{marker}", 1, "공정", "오름차순", "", None, "N"),
        ],
        columns=[
            "페이지 구분",
            "탭 구분",
            "정렬우선순위",
            "분류컬럼",
            "정렬방식",
            "분류값",
            "값표시순서",
            "활성여부",
        ],
    ).astype({"값표시순서": "Int64"})


def _data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["P-B", "P-A", "P-B", "P-A"],
            "WF 구분": ["Buffer", "Top_e", "Top", "Buffer"],
            "값": [1, 2, 3, 4],
        }
    )


def _same(left: PreparedDisplayOrder | None, right: PreparedDisplayOrder | None) -> None:
    assert left is not None and right is not None
    pd.testing.assert_frame_equal(left.rules, right.rules)
    pd.testing.assert_frame_equal(left.derived_rules, right.derived_rules)


def test_the_cached_preparation_equals_a_direct_preparation() -> None:
    rules = _rules()
    cached = get_prepared_display_order(rules)
    _same(cached, prepare_display_order(rules))
    # 두 번째(적중)도 같은 값이고, 앱이 파생한 `Top_e` 규칙이 들어 있다.
    again = get_prepared_display_order(rules.copy())
    _same(again, prepare_display_order(rules))
    assert again is not None
    assert "Top_e" in set(again.derived_rules["분류값"])
    pd.testing.assert_frame_equal(
        apply_display_order(_data(), again, PAGE, TAB),
        apply_display_order(_data(), rules, PAGE, TAB),
    )


def test_a_content_change_prepares_again() -> None:
    """버전은 그대로 두고 내용만 바꿔도(Admin 교체) 새로 준비한다. 되돌리면 처음 값이다."""
    tag = uuid.uuid4().hex
    ascending = get_prepared_display_order(_rules("오름차순", tag=tag))
    descending = get_prepared_display_order(_rules("내림차순", tag=tag))
    _same(descending, prepare_display_order(_rules("내림차순", tag=tag)))
    assert ascending is not None and descending is not None
    assert apply_display_order(_data(), ascending, PAGE, TAB)["공정"].tolist()[:2] == ["P-A"] * 2
    assert apply_display_order(_data(), descending, PAGE, TAB)["공정"].tolist()[:2] == ["P-B"] * 2
    _same(get_prepared_display_order(_rules("오름차순", tag=tag)), ascending)


def test_a_hit_skips_the_preparation(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    original = display_order_module._prepare_display_order

    def counted(frame: pd.DataFrame) -> pd.DataFrame:
        calls.append(len(frame))
        return original(frame)

    monkeypatch.setattr(display_order_module, "_prepare_display_order", counted)
    tag = uuid.uuid4().hex
    get_prepared_display_order(_rules(tag=tag))
    get_prepared_display_order(_rules(tag=tag))
    assert len(calls) == 1
    get_prepared_display_order(_rules("내림차순", tag=tag))
    assert len(calls) == 2


def test_each_caller_gets_its_own_copy() -> None:
    """꺼낸 규칙을 고쳐도 다음 회차는 원래 값을 받는다."""
    rules = _rules()
    first = get_prepared_display_order(rules)
    assert first is not None
    first.derived_rules.loc[:, "정렬방식"] = "망가뜨림"
    _same(get_prepared_display_order(rules), prepare_display_order(rules))


def test_an_invalid_profile_raises_every_time() -> None:
    """검증 예외는 캐시하지 않는다 — 고칠 때까지 매번 같은 오류다."""
    broken = _rules().drop(columns="활성여부")
    for _ in range(2):
        with pytest.raises(ValueError, match="활성여부"):
            get_prepared_display_order(broken)
