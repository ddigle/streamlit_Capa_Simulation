# Purpose: 확보기준 과부족(부호 있는 정수)·판정·부족 원인이 Static Capa 와 같은 규칙인지 본다.

"""`securement_balance` 의 계약.

- 모자란 쪽 크기는 Static Capa 의 「확보목표 총 필요대수」(`_ceil_positive`)와 **같은 정수**다.
- 판정은 `thresholds.status` 한 길이다 — 확보율 칸과 과부족 칸이 같은 판정으로 칠해진다.
- 부동소수 잡음 경계에서는 경고로 칠한 칸에 0 이 찍힌다. 그것을 그대로 고정한다.
"""

from __future__ import annotations

import random

import pandas as pd
import pytest

from capa_simulation.services.securement_rate import (
    BALANCE_COLUMN,
    CAUSE_COLUMN,
    CAUSE_OWNED_SHORT,
    CAUSE_RENTAL,
    STATUS_COLUMN,
    WARNING_NEED_COLUMN,
    build_securement_shortfall_tables,
    securement_balance,
)
from capa_simulation.services.securement_threshold import SecurementThresholds


def _frame(rows: list[tuple[int, str, float, float, float]]) -> pd.DataFrame:
    """(달, 공정, 총보유, 가용, 소요) 목록."""
    return pd.DataFrame(
        {
            "생산계획년월": [row[0] for row in rows],
            "공정": [row[1] for row in rows],
            "총보유대수": [row[2] for row in rows],
            "가용대수": [row[3] for row in rows],
            "소요대수": [row[4] for row in rows],
        }
    )


def test_shortage_is_negative_ceiling_and_surplus_is_positive_floor() -> None:
    balance = securement_balance(
        _frame(
            [
                (202601, "Short", 10.0, 8.0, 10.0),
                (202601, "Surplus", 15.0, 13.7, 10.0),
                (202601, "OnThreshold", 55.0, 55.0, 50.0),
                (202601, "NoDemand", 4.0, 3.6, 0.0),
            ]
        ),
        thresholds=SecurementThresholds(1.1, 0.9),
    )

    # 11 − 8 = 3 모자람 → −3. 13.7 − 11 = 2.7 남음 → +2. 50 × 1.1 = 55.00000000000001 은 0.
    assert balance[BALANCE_COLUMN].tolist() == [-3, 2, 0, 3]
    assert balance[STATUS_COLUMN].tolist() == ["shortage", "secure", "secure", None]
    assert balance[WARNING_NEED_COLUMN].tolist() == [1, 0, 0, 0]
    assert str(balance[BALANCE_COLUMN].dtype) == "int64"


def test_the_noise_boundary_paints_warning_but_counts_zero() -> None:
    """판정은 반올림하지 않은 확보율, 과부족은 9자리 반올림이다 — 경계에서 둘이 갈린다.

    소요 10.000000000000002 · 가용 10.95 · 확보기준 1.095 이면 확보율이 1.0949999999999998 이라
    경고로 칠하지만 `소요 × 기준 − 가용` 은 2.7e-15 라 0 대다. Static Capa 도 같은 행을 확보 미달로
    고르고 「확보목표 총 필요대수」 0 을 적는다. 칠한 칸에 0 이 찍히는 것이 맞는 동작이다.
    """
    frame = _frame([(202601, "Edge", 10.95, 10.95, 10.000000000000002)])
    thresholds = SecurementThresholds(1.095, 0.995)
    assert 10.95 / 10.000000000000002 < 1.095

    balance = securement_balance(frame, thresholds=thresholds)
    _, secure_rows = build_securement_shortfall_tables(
        frame.assign(확보율=frame["가용대수"] / frame["소요대수"]), thresholds=thresholds
    )

    assert balance[STATUS_COLUMN].tolist() == ["warning"]
    assert balance[BALANCE_COLUMN].tolist() == [0]
    assert secure_rows["확보목표 총 필요대수"].tolist() == [0]


def test_cause_separates_owned_shortage_from_rental() -> None:
    balance = securement_balance(
        _frame(
            [
                (202601, "OwnedShort", 10.0, 8.0, 10.0),
                (202601, "Rental", 12.0, 8.0, 10.0),
                (202601, "OwnedExact", 11.0, 9.0, 10.0),
                (202601, "Secure", 12.0, 12.0, 10.0),
            ]
        ),
        thresholds=SecurementThresholds(1.1, 0.9),
    )

    assert balance[CAUSE_COLUMN].tolist() == [CAUSE_OWNED_SHORT, CAUSE_RENTAL, CAUSE_RENTAL, ""]


def test_monthly_exceptions_set_the_threshold_of_each_row() -> None:
    thresholds = SecurementThresholds(1.1, 0.9, ((202602, 1.3, None),))
    balance = securement_balance(
        _frame([(202601, "P", 12.0, 12.0, 10.0), (202602, "P", 12.0, 12.0, 10.0)]),
        thresholds=thresholds,
    )

    assert balance["확보기준"].tolist() == [1.1, 1.3]
    assert balance["경고기준"].tolist() == [0.9, 0.9]
    assert balance[STATUS_COLUMN].tolist() == ["secure", "warning"]
    assert balance[BALANCE_COLUMN].tolist() == [1, -1]


def _random_rows(seed: int, count: int) -> pd.DataFrame:
    rng = random.Random(seed)
    rows: list[tuple[int, str, float, float, float]] = []
    for index in range(count):
        month = 202601 + rng.randrange(12)
        demand = rng.choice([0.0, rng.uniform(0.05, 40.0), float(rng.randint(1, 40))])
        available = rng.choice(
            [rng.uniform(0.0, 50.0), demand * 1.095, demand * 1.1, demand * 0.995, demand]
        )
        owned = available + rng.choice([0.0, rng.uniform(0.0, 6.0)])
        rows.append((month, f"P{index:03d}", owned, available, demand))
    return _frame(rows)


@pytest.mark.parametrize("seed", [7, 2026, 31337])
def test_shortage_size_equals_static_capa_secure_target(seed: int) -> None:
    """모자란 쪽 크기 ≡ Static Capa 「확보목표 총 필요대수」, 판정 ≡ 두 목록의 구획.

    Static Capa 는 경고 미달(부족)과 확보 미달(경고)을 두 목록으로 가른다. 같은 확보율·같은 달
    기준으로 가르므로 판정이 부족인 행은 앞 목록에, 경고인 행은 뒤 목록에 있고, 확보인 행은
    어디에도 없다.
    """
    frame = _random_rows(seed, 300)
    thresholds = SecurementThresholds(
        1.095, 0.995, ((202603, 1.2, None), (202605, None, 0.9), (202607, 1.0, 0.8))
    )

    balance = securement_balance(frame, thresholds=thresholds)
    warning_rows, secure_rows = build_securement_shortfall_tables(
        frame.assign(확보율=frame["가용대수"] / frame["소요대수"]), thresholds=thresholds
    )
    listed = {
        str(row["공정"]): (status, int(row["확보목표 총 필요대수"]), int(row["경고기준 필요대수"]))
        for status, rows in (("shortage", warning_rows), ("warning", secure_rows))
        for row in rows.to_dict("records")
    }
    assert listed, "표본에 확보 미달 행이 있어야 동치를 본다"

    for row in balance.to_dict("records"):
        process = str(row["공정"])
        status = row[STATUS_COLUMN]
        signed = int(row[BALANCE_COLUMN])
        if process in listed:
            listed_status, secure_need, warning_need = listed[process]
            assert status == listed_status
            assert -signed == secure_need
            assert int(row[WARNING_NEED_COLUMN]) == warning_need
        else:
            assert status in ("secure", None)
            assert signed >= 0
        demand = float(row["소요대수"])
        month = int(row["생산계획년월"])
        expected = (
            None if demand <= 0 else thresholds.status(float(row["가용대수"]) / demand, month)
        )
        assert status == expected


def test_owned_column_is_required() -> None:
    frame = _frame([(202601, "P", 1.0, 1.0, 1.0)]).drop(columns="총보유대수")

    with pytest.raises(ValueError, match="총보유대수"):
        securement_balance(frame, thresholds=SecurementThresholds(1.1, 0.9))
