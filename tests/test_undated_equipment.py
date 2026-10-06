# Purpose: 일정 미정(반입·Qual 일정이 빈 신규) 설비를 설비 단위로 세는 서비스와 알림을 검증한다.

from __future__ import annotations

from typing import Any

import pandas as pd
from test_equipment_availability import _equipment

from capa_simulation.services.undated_equipment import (
    UNDATED_ARRIVAL,
    UNDATED_COLUMNS,
    UNDATED_KIND_COLUMN,
    UNDATED_QUAL,
    undated_counts,
    undated_equipment,
    undated_equipment_notice,
)


def _master(*extra: dict[str, Any]) -> pd.DataFrame:
    """EQ-01·EQ-02(일정 다 있음)와 덧붙인 행. 덧붙인 행은 EQ-01 을 바탕으로 값만 바꾼다."""
    base = _equipment()
    records = base.to_dict(orient="records")
    records += [{**records[0], **values} for values in extra]
    return pd.DataFrame(records, columns=base.columns)


_NO_DATES = {"제진대일정": None, "물류일정": None, "반입일정": None, "Qual일정": None}


def test_only_new_staying_units_with_a_blank_date_are_counted() -> None:
    master = _master(
        {"설비명": "NO-ARRIVAL", **_NO_DATES, "확정상태": None},
        {"설비명": "NO-QUAL", "Qual일정": None, "확정상태": None},
        {"설비명": "QUAL-ONLY", "반입일정": None},
        {"설비명": "EXISTING", **_NO_DATES, "기존설비여부": "Y"},
        {"설비명": "STORED", **_NO_DATES, "보관유무": "Y"},
        {"설비명": "LEAVING", "Qual일정": None, "확정상태": None, "반출일정": "2026-12-01"},
        {"설비명": "MOVING", "Qual일정": None, "확정상태": None, "이설일정": "2026-12-01"},
    )

    rows = undated_equipment(master)

    assert rows.columns.tolist() == list(UNDATED_COLUMNS)
    kinds = dict(zip(rows["설비명"], rows[UNDATED_KIND_COLUMN], strict=True))
    assert kinds == {
        "NO-ARRIVAL": UNDATED_ARRIVAL,
        "NO-QUAL": UNDATED_QUAL,
        # 반입이 비면 Qual 이 있어도 반입 미정이다 — 둘은 겹치지 않는다.
        "QUAL-ONLY": UNDATED_ARRIVAL,
    }
    assert undated_counts(rows) == {UNDATED_ARRIVAL: 2.0, UNDATED_QUAL: 1.0}
    assert undated_equipment_notice(rows) == (
        "일정 미정 3대 (반입 미정 2 · Qual 미정 1) — 날짜가 들어올 때까지 가용대수에 세지 않습니다."
    )


def test_modules_count_as_shares_of_one_unit() -> None:
    """모듈 넷 중 하나만 일정이 비면 0.25대, 넷 다 비면 1대다(행 수가 아니라 설비 수)."""
    modules = [
        {"설비명": f"M1-{tag}", "Main 설비": "M1", "X좌표": None, "Y좌표": None} for tag in "ABCD"
    ]
    modules[0].update({"Qual일정": None, "확정상태": None})
    whole = [
        {"설비명": f"M2-{tag}", "Main 설비": "M2", "X좌표": None, "Y좌표": None, **_NO_DATES}
        for tag in "ABCD"
    ]
    for row in whole:
        row["확정상태"] = None

    rows = undated_equipment(_master(*modules, *whole))

    assert undated_counts(rows) == {UNDATED_ARRIVAL: 1.0, UNDATED_QUAL: 0.25}
    assert undated_equipment_notice(rows) == (
        "일정 미정 1.25대 (반입 미정 1 · Qual 미정 0.25) — 날짜가 들어올 때까지 가용대수에 "
        "세지 않습니다."
    )


def test_nothing_to_say_when_every_new_unit_has_its_dates() -> None:
    rows = undated_equipment(_master())

    assert rows.empty and rows.columns.tolist() == list(UNDATED_COLUMNS)
    assert undated_equipment_notice(rows) is None
    assert undated_equipment_notice(undated_equipment(_equipment().iloc[0:0])) is None


def test_the_notice_follows_the_surrounding_process_and_unit_filters() -> None:
    master = _master(
        {"설비명": "A-1", "Qual일정": None, "확정상태": None},
        {"설비명": "B-1", "공정소분류": "Process-B", **_NO_DATES, "확정상태": None},
    )
    rows = undated_equipment(master)

    only_a = undated_equipment_notice(rows, processes={"Process-A"})
    only_b_unit = undated_equipment_notice(rows, unit_ids={"B-1"})

    assert only_a is not None and only_a.startswith("일정 미정 1대 (Qual 미정 1)")
    assert only_b_unit is not None and only_b_unit.startswith("일정 미정 1대 (반입 미정 1)")
    assert undated_equipment_notice(rows, processes={"Process-C"}) is None
    assert undated_equipment_notice(rows, processes={"Process-A"}, unit_ids={"B-1"}) is None
