# Purpose: 제외 목록 알림 표 기억(`remembered_alert_table`)의 키 · 사본 · 칸 수 규칙을 고정한다.

"""산출 결과 제외 목록의 알림 표는 (부르는 쪽 키, 목록 이름, 파일 이름, 공정 표시명 판)으로 이
세션에 기억한다(다시 도는 범위 C3). 키가 없으면 늘 짓고, 꺼낸 표는 겉 dict 를 새로 내며, 너무 커서
표가 없는(None) 목록도 기억한다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pandas as pd
import pytest
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.required_exclusion_notice import (
    EXCLUSION_MEMO_KEY,
    EXCLUSION_MEMO_LIMIT,
    remembered_alert_table,
)
from capa_simulation.components.state_alerts import alert_table

FRAME = pd.DataFrame({"공정": ["Process-A", "Process-B"], "부하량": [1.0, 2.0]})


@pytest.fixture(autouse=True)
def _clean_session() -> Iterator[None]:
    yield
    st.session_state.clear()


def _builder(
    built: list[int], frame: pd.DataFrame = FRAME
) -> Callable[[], alerts.AlertTable | None]:
    def build() -> alerts.AlertTable | None:
        built.append(1)
        return alert_table(frame, title="목록", file_name="list.csv")

    return build


def test_the_same_key_builds_once_and_hands_out_a_fresh_dict() -> None:
    built: list[int] = []
    first = remembered_alert_table(
        ("결과", "지문"),
        title="목록",
        file_name="list.csv",
        labels=ProcessLabels(),
        build=_builder(built),
    )
    assert first is not None
    first["csv"] = False

    again = remembered_alert_table(
        ("결과", "지문"),
        title="목록",
        file_name="list.csv",
        labels=ProcessLabels(),
        build=_builder(built),
    )

    assert built == [1]
    assert again is not None and "csv" not in again
    assert again == alert_table(FRAME, title="목록", file_name="list.csv")


@pytest.mark.parametrize(
    "change",
    [
        {"memo": ("결과2", "지문")},
        {"title": "다른 목록"},
        {"file_name": "list_(수정).csv"},
        {"labels": ProcessLabels(version=3, labels={"Process-A": "가공"})},
    ],
    ids=["memo", "title", "file", "labels"],
)
def test_each_key_part_builds_again(change: dict[str, object]) -> None:
    built: list[int] = []
    base: dict[str, object] = {
        "memo": ("결과", "지문"),
        "title": "목록",
        "file_name": "list.csv",
        "labels": ProcessLabels(),
    }
    for arguments in (base, {**base, **change}):
        remembered_alert_table(
            arguments["memo"],
            title=str(arguments["title"]),
            file_name=str(arguments["file_name"]),
            labels=arguments["labels"],  # type: ignore[arg-type]
            build=_builder(built),
        )
    assert built == [1, 1]


def test_without_a_key_it_always_builds_and_keeps_nothing() -> None:
    built: list[int] = []
    for _ in range(2):
        remembered_alert_table(
            None, title="목록", file_name="list.csv", labels=ProcessLabels(), build=_builder(built)
        )
    assert built == [1, 1]
    assert EXCLUSION_MEMO_KEY not in st.session_state


def test_a_list_too_large_for_the_alarm_is_remembered_as_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(alerts, "TABLE_ROW_LIMIT", 0)
    built: list[int] = []
    for _ in range(2):
        assert (
            remembered_alert_table(
                ("결과",),
                title="목록",
                file_name="list.csv",
                labels=ProcessLabels(),
                build=_builder(built),
            )
            is None
        )
    assert built == [1]


def test_the_memo_keeps_at_most_its_limit_and_drops_the_oldest() -> None:
    built: list[int] = []
    for index in range(EXCLUSION_MEMO_LIMIT + 1):
        remembered_alert_table(
            ("결과", index),
            title="목록",
            file_name="list.csv",
            labels=ProcessLabels(),
            build=_builder(built),
        )
    held = st.session_state[EXCLUSION_MEMO_KEY]
    assert len(held) == EXCLUSION_MEMO_LIMIT
    assert (("결과", 0), "목록", "list.csv", 0) not in held
    assert (("결과", EXCLUSION_MEMO_LIMIT), "목록", "list.csv", 0) in held
