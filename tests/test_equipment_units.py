# Purpose: 모체호기로 묶은 모듈 행이 대수 축에서 설비 한 대로 세어지는지 고정한다.

"""모듈 행 넷 = 설비 한 대.

CoW Bonder 처럼 모듈로 관리하는 공정은 설비 한 대(APW01)를 모듈 행 넷(APW01A~D)으로 적고
`모체호기` 로 묶는다. 대수 축(「몇 대인가」)은 묶음을 한 대로 세고, 능력 축(「몇 대 몫을
하나」)은 모듈 행의 환산비(0.25)를 더한다. 비모듈 행은 지금까지와 똑같이 행 하나가 한 대다.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.components.equipment_explorer import _rows_label
from capa_simulation.components.space_layout import equipment_unit_total, stage_counts
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_equipment_status_as_of,
    build_inactive_equipment,
    build_milestone_transition_events,
    build_weekly_equipment_availability,
)
from capa_simulation.services.equipment_contract import (
    BASELINE_COLUMNS,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    PARENT_EQUIPMENT_COLUMN,
)
from capa_simulation.services.equipment_csv import (
    equipment_csv_bytes,
    read_equipment_clipboard,
    read_equipment_csv,
)
from capa_simulation.services.equipment_units import (
    UNIT_KEY_COLUMN,
    UNIT_SHARE_COLUMN,
    format_unit_count,
    held_unit_shares,
    module_group_warnings,
    placed_unit_rows,
    static_unit_shares,
    unit_keys,
    unit_transitions,
)
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.monthly_equipment_availability import (
    available_subtotal,
    build_monthly_equipment_availability,
)

PROCESS = "DEMO_Bonder"


def _row(
    unit: str,
    parent: str | None,
    ratio: float,
    *,
    arrival: str = "2026-01-05",
    qual: str = "2026-01-20",
    removal: str | None = None,
    building: str = "C1",
) -> dict[str, object]:
    row: dict[str, object] = {column: None for column in EQUIPMENT_COLUMNS}
    row.update(
        {
            "호기": unit,
            "공정소분류": PROCESS,
            "공정대분류": "B/N",
            "라인구분": "L1",
            "활용구분": "양산",
            "동": building,
            "층": "1F",
            "입고일정": arrival,
            "Qual일정": qual,
            "확정상태": "완료",
            "반출일정": removal,
            "장기보관여부": "N",
            "기존설비여부": "N",
            "레이아웃표시": "N",
            "환산비": ratio,
            PARENT_EQUIPMENT_COLUMN: parent,
        }
    )
    return row


def _modules(**overrides: dict[str, object]) -> pd.DataFrame:
    """APW01 의 모듈 넷(환산비 0.25) + 비모듈 설비 DA01(환산비 1.2)."""
    rows = [_row(f"APW01{suffix}", "APW01", 0.25) for suffix in "ABCD"]
    rows.append(_row("DA01", None, 1.2))
    for row in rows:
        row.update(overrides.get(str(row["호기"]), {}))
    return pd.DataFrame(rows, columns=list(EQUIPMENT_COLUMNS))


def _pm(unit: str = "APW01B") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "호기": unit,
                "비가동유형": "고장",
                "시작일": "2026-03-01",
                "종료일": "2026-03-31",
                "상세사유": "PM",
                "비고": None,
            }
        ],
        columns=list(DOWNTIME_COLUMNS),
    )


def _no_downtime() -> pd.DataFrame:
    return pd.DataFrame(columns=list(DOWNTIME_COLUMNS))


def _no_baseline() -> pd.DataFrame:
    return pd.DataFrame(columns=list(BASELINE_COLUMNS))


# ------------------------------------------------------------------- 설비키·지분


def test_the_key_is_the_parent_when_given_and_the_unit_otherwise() -> None:
    frame = pd.DataFrame({"호기": ["A1", "A2", "B1"], PARENT_EQUIPMENT_COLUMN: ["A", "  ", None]})

    assert unit_keys(frame).tolist() == ["A", "A2", "B1"]
    # 컬럼이 없던 표(옛 리비전·옛 양식)는 행 하나가 한 대다.
    assert unit_keys(frame.drop(columns=[PARENT_EQUIPMENT_COLUMN])).tolist() == ["A1", "A2", "B1"]


def test_held_shares_split_one_among_the_modules_held_at_that_moment() -> None:
    keys = pd.Series(["A", "A", "A", "A", "B"])

    # 넷 다 보유 → 0.25 씩.
    all_held = held_unit_shares(keys, pd.Series([True, True, True, True, True]))
    assert all_held.tolist() == [0.25, 0.25, 0.25, 0.25, 1.0]
    # 하나를 반출하면 남은 셋이 한 대를 채우고, 반출된 모듈은 0 이다.
    one_out = held_unit_shares(keys, pd.Series([True, True, True, False, True]))
    assert one_out.tolist() == pytest.approx([1 / 3, 1 / 3, 1 / 3, 0.0, 1.0])
    # 아무것도 보유 중이 아니면(입고 전) 행 수로 나눈다 — 「입고 예정 1대」.
    none_held = held_unit_shares(keys, pd.Series([False, False, False, False, False]))
    assert none_held.tolist() == [0.25, 0.25, 0.25, 0.25, 1.0]
    for shares in (all_held, one_out, none_held):
        assert shares.groupby(keys).sum().tolist() == pytest.approx([1.0, 1.0])


def test_static_shares_ignore_holding() -> None:
    keys = pd.Series(["A", "A", "B"])

    assert static_unit_shares(keys).tolist() == [0.5, 0.5, 1.0]


def test_fractional_counts_are_written_without_trailing_zeros() -> None:
    assert format_unit_count(3.0) == "3"
    assert format_unit_count(0.25) == "0.25"
    assert format_unit_count(0.75) == "0.75"
    assert format_unit_count(1 / 3) == "0.33"
    assert format_unit_count(1234.5) == "1,234.5"
    assert format_unit_count(0.999999999) == "1"


# ----------------------------------------------------------------------- 검증


def test_the_parent_is_normalized_and_old_frames_without_it_still_pass() -> None:
    frame = _modules(APW01A={PARENT_EQUIPMENT_COLUMN: "  APW01 "}, DA01={"모체호기": "  "})

    prepared = prepare_equipment_master(frame)

    assert prepared[PARENT_EQUIPMENT_COLUMN].tolist()[:1] == ["APW01"]
    assert pd.isna(prepared.loc[prepared["호기"].eq("DA01"), PARENT_EQUIPMENT_COLUMN].item())
    legacy = prepare_equipment_master(frame.drop(columns=[PARENT_EQUIPMENT_COLUMN]))
    assert legacy[PARENT_EQUIPMENT_COLUMN].isna().all()


def test_a_parent_that_is_also_a_standalone_unit_is_rejected() -> None:
    """APW01 을 설비 행으로도, 모듈 묶음으로도 두면 같은 설비를 두 번 센다."""
    frame = pd.concat(
        [_modules(), pd.DataFrame([_row("APW01", None, 1.0)], columns=list(EQUIPMENT_COLUMNS))],
        ignore_index=True,
    )

    with pytest.raises(ValueError, match="모체호기"):
        prepare_equipment_master(frame)


@pytest.mark.parametrize("column", ["동", "공정소분류", "활용구분"])
def test_modules_of_one_unit_must_agree_on_filter_columns(column: str) -> None:
    """필터가 설비 하나를 쪼개면 지분 합이 1 이 아니게 된다."""
    value = "C2" if column == "동" else "OTHER"
    frame = _modules(APW01D={column: value})

    with pytest.raises(ValueError, match="모체호기"):
        prepare_equipment_master(frame)


def test_modules_whose_ratios_were_left_at_one_are_flagged() -> None:
    inflated = prepare_equipment_master(
        _modules(**{f"APW01{suffix}": {"환산비": 1.0} for suffix in "ABCD"})
    )

    assert module_group_warnings(inflated)
    assert "APW01" in module_group_warnings(inflated)[0]
    assert module_group_warnings(prepare_equipment_master(_modules())) == []


# ---------------------------------------------------------------------- 대수 축


def test_one_module_down_is_a_quarter_of_a_unit_in_the_weekly_count() -> None:
    weekly = build_weekly_equipment_availability(
        _no_baseline(),
        _modules(),
        _pm(),
        start_date=date(2026, 3, 9),
        end_date=date(2026, 3, 15),
    )

    row = weekly.loc[weekly["공정소분류"].eq(PROCESS)].iloc[0]
    # APW01 한 대 + DA01 한 대. 모듈 넷이 넷으로 세어지면 5가 된다.
    assert row["총대수"] == 2.0
    assert row["가용대수"] == 1.75
    assert row["비가동대수"] == 0.25
    assert row["운영비가동대수"] == 0.25


def test_removing_one_module_leaves_the_unit_whole() -> None:
    frame = _modules(APW01D={"반출일정": "2026-05-10"})

    status = build_equipment_status_as_of(frame, _no_downtime(), as_of=date(2026, 6, 15))
    shares = status.set_index("호기")[UNIT_SHARE_COLUMN]

    assert shares["APW01D"] == 0.0
    assert shares[["APW01A", "APW01B", "APW01C"]].sum() == pytest.approx(1.0)
    assert status.groupby(UNIT_KEY_COLUMN)[UNIT_SHARE_COLUMN].sum().round(9).eq(1.0).all()


def test_a_unit_not_yet_arrived_is_one_planned_unit() -> None:
    frame = _modules(
        **{f"APW01{s}": {"입고일정": "2026-09-01", "Qual일정": "2026-09-20"} for s in "ABCD"}
    )

    status = build_equipment_status_as_of(frame, _no_downtime(), as_of=date(2026, 6, 15))
    planned = status.loc[status["상태"].eq("입고 예정"), UNIT_SHARE_COLUMN].sum()

    assert planned == pytest.approx(1.0)


def test_spans_split_where_a_sibling_changes_the_share_only_when_asked() -> None:
    frame = _modules(APW01D={"반출일정": "2026-05-10"})
    kwargs = {"start_date": date(2026, 4, 1), "end_date": date(2026, 6, 30)}

    plain = build_equipment_lifecycle_spans(frame, _no_downtime(), **kwargs)
    shared = build_equipment_lifecycle_spans(frame, _no_downtime(), with_unit_share=True, **kwargs)

    # Gantt 가 보는 구간은 그대로다 — APW01A 는 석 달 내내 「가용」 한 구간.
    assert UNIT_SHARE_COLUMN not in plain.columns
    assert len(plain.loc[plain["호기"].eq("APW01A")]) == 1
    # 대수를 셀 구간은 D 가 빠지는 날 끊긴다(0.25 → 1/3).
    module_a = shared.loc[shared["호기"].eq("APW01A")]
    assert module_a[UNIT_SHARE_COLUMN].round(6).tolist() == [0.25, round(1 / 3, 6)]
    assert module_a["상태"].unique().tolist() == ["가용"]


def test_monthly_counts_units_while_the_converted_count_sums_ratios() -> None:
    frame = _modules()
    spans = build_equipment_lifecycle_spans(
        frame,
        _no_downtime(),
        start_date=date(2025, 12, 1),
        end_date=date(2026, 7, 31),
        with_unit_share=True,
    )
    cutoff = pd.DataFrame({"공정": [PROCESS], "제품구분": ["*"], "Cutoff일수": [0]})

    monthly = build_monthly_equipment_availability(
        spans,
        _no_baseline(),
        cutoff,
        [202606],
        conversion_ratios=dict(zip(frame["호기"], frame["환산비"], strict=True)),
    )
    subtotal = available_subtotal(monthly).iloc[0]

    # 대수: APW01 1대 + DA01 1대. 능력: 0.25 × 4 + 1.2.
    assert subtotal["Dynamic가용대수"] == pytest.approx(2.0)
    assert subtotal["Dynamic가용환산대수"] == pytest.approx(2.2)


def test_transition_events_carry_the_unit_key() -> None:
    events = build_milestone_transition_events(
        _modules(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        as_of=date(2026, 1, 31),
    )

    arrivals = events.loc[events["전환단계"].eq("입고")]
    assert len(arrivals) == 5
    assert arrivals.drop_duplicates([UNIT_KEY_COLUMN, "전환단계", "전환일"]).shape[0] == 2


# ------------------------------------------------------------------ 입력·저장


def test_a_paste_without_the_parent_column_is_still_accepted() -> None:
    """모체호기가 생기기 전의 31열 표도 그대로 읽힌다."""
    frame = _modules().drop(columns=[PARENT_EQUIPMENT_COLUMN])
    content = frame.to_csv(sep="\t", index=False)

    result = read_equipment_clipboard(content)

    assert result[PARENT_EQUIPMENT_COLUMN].isna().all()
    assert len(result) == 5


def test_the_parent_survives_a_csv_round_trip() -> None:
    prepared = prepare_equipment_master(_modules())

    result = read_equipment_csv(equipment_csv_bytes(prepared))

    assert result[PARENT_EQUIPMENT_COLUMN].tolist()[:4] == ["APW01"] * 4
    assert result["환산비"].tolist()[:4] == [0.25] * 4


def test_the_parent_survives_a_save_and_load(tmp_path: Path) -> None:
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()
    prepared = prepare_equipment_master(_modules())

    saved = repository.save_snapshot(_no_baseline(), prepared, _no_downtime(), note="모듈")
    loaded = repository.load_snapshot(saved.revision.revision_id).equipment

    assert loaded[PARENT_EQUIPMENT_COLUMN].isna().tolist() == [False] * 4 + [True]
    assert loaded[PARENT_EQUIPMENT_COLUMN].dropna().tolist() == ["APW01"] * 4
    assert loaded["환산비"].tolist() == [0.25, 0.25, 0.25, 0.25, 1.2]


# ------------------------------------------------------------------ 표기·화면 집계


def test_a_zero_never_prints_with_a_minus_sign() -> None:
    assert format_unit_count(-0.0) == "0"
    assert format_unit_count(-0.000001) == "0"


def _one_removed_one_down() -> pd.DataFrame:
    """D 를 반출해 남은 셋이 1/3 씩, 그중 B 가 PM. 1/3 짜리 합끼리 빼면 -0.0 이 남는다."""
    frame = _modules(APW01D={"반출일정": "2026-02-01"})
    return build_equipment_status_as_of(
        frame, _pm("APW01B").assign(시작일="2026-03-01"), as_of=date(2026, 3, 15)
    )


def test_space_counts_add_up_without_a_negative_zero() -> None:
    counts = stage_counts(_one_removed_one_down())

    assert counts == pytest.approx({"가용": 1 + 2 / 3, "운영 비가동": 1 / 3}, abs=1e-6)
    # 반출해 지분이 0 인 모듈은 범례에 「반출 완료 0대」로 서지 않는다. 음수 0 도 남지 않는다.
    assert "반출 완료" not in counts
    assert all(math.copysign(1.0, value) == 1.0 for value in counts.values())


def test_one_placed_module_places_the_whole_unit() -> None:
    """상자는 모듈 한 행에만 그린다. 그래도 설비는 통째로 배치된 것이다."""
    status = build_equipment_status_as_of(_modules(), _no_downtime(), as_of=date(2026, 3, 15))
    placed = status.loc[status["호기"].isin(["APW01A", "DA01"])]

    counted = placed_unit_rows(status, placed)

    assert stage_counts(counted) == {"가용": 2.0}
    assert equipment_unit_total(counted) == 2.0
    assert len(counted) == 5


def test_one_down_module_per_unit_is_not_read_as_whole_units() -> None:
    """설비마다 모듈 하나씩 멈추면 행 수와 설비 수가 같다 — 그래도 「2대」가 아니다."""
    frame = pd.concat(
        [
            _modules(),
            pd.DataFrame(
                [_row(f"APW02{suffix}", "APW02", 0.25) for suffix in "ABCD"],
                columns=list(EQUIPMENT_COLUMNS),
            ),
        ],
        ignore_index=True,
    )
    downtime = pd.concat([_pm("APW01B"), _pm("APW02C")], ignore_index=True)

    inactive = build_inactive_equipment(frame, downtime, as_of=date(2026, 3, 15))

    assert _rows_label(inactive, partial=True) == "호기 행 2 · 설비 2대에 걸침"
    # 비모듈 행만 있으면 지금까지와 같다.
    only_da = build_inactive_equipment(frame, _pm("DA01"), as_of=date(2026, 3, 15))
    assert _rows_label(only_da, partial=True) == "1대"


def test_a_unit_transition_is_confirmed_when_any_module_is() -> None:
    """확정상태가 모듈마다 다르면 정렬 순서가 답을 정하면 안 된다."""
    frame = _modules(APW01A={"확정상태": "계획"}, APW01C={"확정상태": "계획"})
    frame.loc[frame["호기"].eq("APW01D"), "확정상태"] = "계획"
    events = build_milestone_transition_events(
        frame,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        as_of=date(2026, 1, 31),
    )

    qual = unit_transitions(events).loc[lambda table: table["전환단계"].eq("Qual")]

    # APW01B 하나만 완료 — 설비 APW01 의 Qual 은 확정·완료로 센다. DA01 도 완료다.
    assert qual.set_index(UNIT_KEY_COLUMN)["Qual확정"].to_dict() == {"APW01": True, "DA01": True}


@pytest.mark.parametrize("header", ["모체 호기", "모체호기(선택)"])
def test_a_misspelled_parent_header_is_rejected_not_blanked(header: str) -> None:
    content = (
        _modules().rename(columns={PARENT_EQUIPMENT_COLUMN: header}).to_csv(sep="\t", index=False)
    )

    with pytest.raises(ValueError, match="모체호기 열 이름이 다릅니다"):
        read_equipment_clipboard(content)


def test_a_csv_header_with_a_trailing_space_is_still_the_parent() -> None:
    prepared = prepare_equipment_master(_modules())
    payload = equipment_csv_bytes(prepared).decode("utf-8-sig").replace("모체호기", "모체호기 ", 1)

    result = read_equipment_csv(payload.encode("utf-8-sig"))

    assert result[PARENT_EQUIPMENT_COLUMN].tolist()[:4] == ["APW01"] * 4
