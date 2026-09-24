# Purpose: 측정률을 1.0 으로 메운 사실이 화면 문구까지 닿는지 검증한다.

"""**메운 것을 말하지 않으면 완화가 곧 조용한 오류다.**

측정률 행이 없을 때 계산을 멈추는 대신 중립값 1.0 으로 이어 가기로 했다. 그 대가로
오차가 한 방향으로만 난다 — 측정률은 대당 Capa 의 분모라 실제가 1 보다 작으면 대당 Capa
과대 → 소요대수 과소 → **확보율 과대**다. 여유 있어 보이는 쪽으로만 틀린다.

그래서 이 문구는 장식이 아니라 완화의 **조건**이다. 문구가 사라지면 완화는 「경고하고
계속」이 아니라 「조용히 계속」이 된다.
"""

from __future__ import annotations

from capa_simulation.components.capacity_assumption_notice import assumption_message


def test_the_message_names_the_tab_the_user_must_open() -> None:
    """개수만 말하면 「그래서 뭘 하라는 것인가」가 남는다."""
    message = assumption_message({"RQ_LOT_RATIO": 12, "RQ_WF_RATIO": 3})

    assert "Lot측정률 12건" in message
    assert "WF측정률 3건" in message


def test_the_message_says_which_way_the_number_is_wrong() -> None:
    """방향을 말하지 않으면 보는 사람이 그대로 낙관으로 기운다."""
    message = assumption_message({"RQ_LOT_RATIO": 1})

    assert "확보율이 실제보다 높게" in message


def test_nothing_assumed_draws_nothing() -> None:
    """없는 날에 자리를 차지하면 다음에는 아무도 안 읽는다."""
    assert assumption_message({}) == ""
    assert assumption_message({"RQ_LOT_RATIO": 0, "RQ_WF_RATIO": 0}) == ""
