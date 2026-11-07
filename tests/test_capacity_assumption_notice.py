# Purpose: 측정률을 1.0 으로 메운 사실이 화면 문구까지 닿는지 검증한다.

"""**메운 것을 말하지 않으면 완화가 곧 조용한 오류다.**

측정률 행이 없을 때 계산을 멈추는 대신 중립값 1.0 으로 이어 가기로 했다. 그 대가로
숫자가 틀린다 — 측정률은 대당 Capa 의 분모라 실제가 1 보다 작으면 대당 Capa 과소 →
소요대수 과대 → **확보율 과소**(보수 쪽)이고, 1 보다 크면 그 반대다.

그래서 이 문구는 장식이 아니라 완화의 **조건**이다. 문구가 사라지면 완화는 「경고하고
계속」이 아니라 「조용히 계속」이 된다.
"""

from __future__ import annotations

import pytest

from capa_simulation import alerts
from capa_simulation.components.capacity_assumption_notice import (
    assumption_message,
    render_capacity_assumption_notice,
)
from capa_simulation.components.state_alerts import AlertScope
from capa_simulation.navigation import REFERENCE_DATA
from capa_simulation.reference_grid_keys import DATASETS
from capa_simulation.services.unit_capacity import CapacityAssumptions


def test_the_message_names_the_tab_the_user_must_open() -> None:
    """개수만 말하면 「그래서 뭘 하라는 것인가」가 남는다."""
    message = assumption_message({"RQ_LOT_RATIO": 12, "RQ_WF_RATIO": 3})

    assert "Lot측정률 12건" in message
    assert "WF측정률 3건" in message


def test_the_message_says_which_way_the_number_is_wrong() -> None:
    """방향을 말하지 않으면 보는 사람이 숫자를 그대로 믿는다.

    예전 문구는 방향이 거꾸로였다(「1 보다 작으면 높게」). 식은 측정률로 **나누므로** 1 보다
    작은 실제값을 1.0 으로 메우면 대당 Capa 가 작아져 확보율은 낮게 나온다.
    """
    message = assumption_message({"RQ_LOT_RATIO": 1})

    assert "1 보다 작으면 **확보율이 실제보다 낮게**" in message
    assert "높게" not in message.split("1 보다 크면")[0]


def test_nothing_assumed_draws_nothing() -> None:
    """없는 날에 자리를 차지하면 다음에는 아무도 안 읽는다."""
    assert assumption_message({}) == ""
    assert assumption_message({"RQ_LOT_RATIO": 0, "RQ_WF_RATIO": 0}) == ""


def test_the_message_names_the_months_and_says_it_covers_the_scenario() -> None:
    """시나리오 전체를 한 번에 계산하므로 보는 기간 밖의 달도 센다. 달이 없으면 찾을 수 없다."""
    months = (202701, 202702, 202703, 202704, 202705, 202706, 202707, 202708)
    message = assumption_message({"RQ_LOT_RATIO": 8}, {"RQ_LOT_RATIO": months})

    assert "시나리오 전체 기준" in message
    assert "Lot측정률 8건(2027-01, 2027-02" in message
    assert "외 2개월" in message


@pytest.mark.parametrize(
    ("tab", "where"), [("", "HOME"), ("대당 Capa", "산출 결과 › 대당 Capa")], ids=["home", "tab"]
)
def test_the_alarm_line_opens_the_screen_to_fill_and_the_text_says_whose_it_is(
    monkeypatch: pytest.MonkeyPatch, tab: str, where: str
) -> None:
    """고칠 표는 기준 정보에 있다 — 줄이 그 화면을 열고(UI-NTF-02) 화면 칸이 기준 정보가 되므로 어느
    화면의 일인지는 전문 첫머리가 말한다. 이 화면 안 탭은 기준 정보의 탭이 아니라 전문에만 들고,
    줄의 탭은 고칠 표의 종류 단추다."""
    sent: dict[str, object] = {}
    page = where.split(" › ")[0]
    monkeypatch.setattr(alerts, "current_page", lambda: (page, "somewhere"))
    monkeypatch.setattr(alerts, "state", lambda code, **kwargs: sent.update(kwargs))

    render_capacity_assumption_notice(
        CapacityAssumptions({"RQ_LOT_RATIO": 3}, {"RQ_LOT_RATIO": (202601,)}),
        scope=AlertScope({"token": "t"}, "범위"),
        tab=tab,
    )

    assert sent["goto"] == ("기준 정보", REFERENCE_DATA.href)
    assert sent["tab"] == DATASETS["RQ_LOT_RATIO"]
    assert str(sent["full"]).startswith(f"{where} — 측정률 행이 없어 ")
    assert "**" not in str(sent["full"])


def test_the_alarm_line_picks_a_table_only_when_there_is_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """표가 둘이면 어느 종류 단추를 열지 정할 수 없어 기준 정보까지만 연다. 건수가 0 인 표는 세지
    않는다."""
    sent: dict[str, object] = {}
    monkeypatch.setattr(alerts, "state", lambda code, **kwargs: sent.update(kwargs))
    scope = AlertScope({"token": "t"}, "범위")

    both = {"RQ_LOT_RATIO": 3, "RQ_WF_RATIO": 2}
    render_capacity_assumption_notice(CapacityAssumptions(both, {}), scope=scope)
    assert sent["tab"] == ""

    one = {"RQ_LOT_RATIO": 0, "RQ_WF_RATIO": 2}
    render_capacity_assumption_notice(CapacityAssumptions(one, {}), scope=scope)
    assert sent["tab"] == DATASETS["RQ_WF_RATIO"]
