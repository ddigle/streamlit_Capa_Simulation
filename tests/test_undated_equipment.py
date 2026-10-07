# Purpose: 일정 미정(반입·Qual 일정이 빈 신규) 설비를 설비 단위로 세는 서비스와 알림을 검증한다.

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from test_equipment_availability import _equipment

from capa_simulation.services.undated_equipment import (
    UNDATED_ARRIVAL,
    UNDATED_COLUMNS,
    UNDATED_KIND_COLUMN,
    UNDATED_QUAL,
    undated_candidate_note,
    undated_counts,
    undated_equipment,
    undated_equipment_notice,
)


def _master(*extra: dict[str, Any]) -> pd.DataFrame:
    """EQ-01·EQ-02(일정 다 있음)와 덧붙인 행. 덧붙인 행은 EQ-01 을 바탕으로 값만 바꾼다."""
    base = _equipment()
    records = base.to_dict(orient="records")
    records += [records[0] | values for values in extra]
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


def _modules(unit: str, **per_tag: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for tag in "ABCD":
        row = {"설비명": f"{unit}{tag}", "Main 설비": unit, "X좌표": None, "Y좌표": None}
        row.update(per_tag.get(tag, {}))
        rows.append(row)
    return rows


def test_a_module_counts_only_what_dynamic_leaves_out() -> None:
    """A·B 가용, C 는 Qual 없음, D 는 반입 없음. Dynamic 은 들어온 셋(A·B·C)으로 1 을 나누므로
    빠지는 것은 C 의 1/3 뿐이다 — D 는 형제가 설비를 채우고 있어 몫이 0 이다."""
    rows = undated_equipment(
        _master(
            *_modules(
                "MOD01",
                C={"Qual일정": None, "확정상태": None},
                D={**_NO_DATES, "확정상태": None},
            )
        )
    )

    assert rows["설비명"].tolist() == ["MOD01C"]
    assert undated_counts(rows) == {UNDATED_ARRIVAL: 0.0, UNDATED_QUAL: pytest.approx(1 / 3)}
    assert undated_equipment_notice(rows) == (
        "일정 미정 0.33대 (Qual 미정 0.33) — 날짜가 들어올 때까지 가용대수에 세지 않습니다."
    )
    # 호기 필터가 D 하나만 골라도 셀 것이 없고, 넷을 다 고르면 같은 0.33 이다.
    assert undated_equipment_notice(rows, unit_ids={"MOD01D"}) is None
    assert undated_equipment_notice(rows, unit_ids={"MOD01A", "MOD01B", "MOD01C", "MOD01D"}) == (
        undated_equipment_notice(rows)
    )


def test_a_unit_none_of_whose_modules_arrived_counts_in_full() -> None:
    no_dates = {**_NO_DATES, "확정상태": None}
    rows = undated_equipment(_master(*_modules("MOD02", **dict.fromkeys("ABCD", no_dates))))

    assert undated_counts(rows) == {UNDATED_ARRIVAL: 1.0, UNDATED_QUAL: 0.0}
    assert undated_equipment_notice(rows) is not None
    assert undated_equipment_notice(rows).startswith("일정 미정 1대 (반입 미정 1)")  # type: ignore[union-attr]


def test_an_existing_or_stored_sibling_holds_the_unit() -> None:
    """기존설비·보관 모듈은 반입일정 없이도 보유로 친다(Dynamic 과 같다) — 형제의 반입 미정은
    없고, Qual 미정 모듈의 몫은 그 형제까지 넣어 나눈다."""
    rows = undated_equipment(
        _master(
            *_modules(
                "MOD03",
                A={**_NO_DATES, "기존설비여부": "Y", "확정상태": None},
                B={**_NO_DATES, "보관유무": "Y", "확정상태": None},
                C={"Qual일정": None, "확정상태": None},
                D={**_NO_DATES, "확정상태": None},
            )
        )
    )

    assert rows["설비명"].tolist() == ["MOD03C"]
    assert undated_counts(rows)[UNDATED_QUAL] == pytest.approx(1 / 3)


def test_the_cached_wrapper_returns_the_same_rows() -> None:
    from capa_simulation.services.simulation_cache import get_undated_equipment

    master = _master({"설비명": "A-1", "Qual일정": None, "확정상태": None})

    pd.testing.assert_frame_equal(get_undated_equipment(master), undated_equipment(master))


# 필요단축일정의 덧붙임 — 후보 조건(`shortening_candidates`)과 맞는지 함께 본다.
_ARRIVAL_ONLY = {"설비명": "ARRIVAL-ONLY", "반입일정": None, "확정상태": "계획"}
_QUAL_BLANK = {"설비명": "QUAL-BLANK", "Qual일정": None, "확정상태": None}
_BOTH_BLANK = {"설비명": "BOTH-BLANK", **_NO_DATES, "확정상태": None}


def _candidate_names(master: pd.DataFrame) -> set[str]:
    from capa_simulation.services.equipment_contract import empty_downtime_schedule
    from capa_simulation.services.required_shortening import shortening_candidates

    units = shortening_candidates(master, empty_downtime_schedule())
    return {module.equipment_id for unit in units for module in unit.modules}


@pytest.mark.parametrize(
    ("rows", "note", "candidates"),
    [
        # 반입만 비면 `반입 미정` 이지만 Qual 일정이 있어 단축 후보다 — 「후보가 아님」은 없다.
        ((_ARRIVAL_ONLY,), None, {"ARRIVAL-ONLY"}),
        ((_QUAL_BLANK,), "단축 후보에도 들지 않습니다.", set()),
        # 반입·Qual 이 다 비면 `반입 미정` 이고 후보도 아니다 — 미정구분으로 가르면 틀린다.
        ((_BOTH_BLANK,), "단축 후보에도 들지 않습니다.", set()),
        (
            (_ARRIVAL_ONLY, _QUAL_BLANK, _BOTH_BLANK),
            "그 가운데 Qual 일정이 없는 2대는 단축 후보에도 들지 않습니다.",
            {"ARRIVAL-ONLY"},
        ),
    ],
)
def test_only_units_without_a_qual_date_are_called_non_candidates(
    rows: tuple[dict[str, Any], ...], note: str | None, candidates: set[str]
) -> None:
    """「단축 후보에도 들지 않습니다」는 Qual 일정이 없는 몫에만 붙는다(2026-10-08 리뷰)."""
    master = _master(*rows)
    undated = undated_equipment(master)

    assert set(undated["설비명"]) == {row["설비명"] for row in rows}
    assert undated_candidate_note(undated) == note
    # 말과 계산이 같은 규칙이다 — 일정 미정 가운데 후보인 것은 Qual 일정이 있는 호기뿐이다.
    named = {row["설비명"] for row in rows}
    assert _candidate_names(master) & named == candidates
    # 공정이 범위 밖이면 말도 없다.
    assert undated_candidate_note(undated, processes=["다른 공정"]) is None
