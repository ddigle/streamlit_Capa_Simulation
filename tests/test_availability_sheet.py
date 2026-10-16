# Purpose: 비교 시트 9행의 항등식·호기 분해·「—」 규칙과 다른 화면과 같은 값인지 검사한다.

"""「Static 대비 일정」 비교 시트(`services/availability_sheet.py`).

경계 사례 픽스처(셋업 중·보관·환산비 1.5·사용기준 밖·정지/반출·모듈·달 걸침·열린 비가동·한 달 내내
비가동·셋업뿐인 공정)로 사양의 불변식을 잰다. 숫자는 손으로 만든 합성 값이다.

- 칸마다 `보유 + 대여 = 가용 = 지금의 환산 소계`.
- 셋업 중·보관 호기의 비가동은 대여에 들지 않는다(그 칸의 `운영 비가동` 과 다르다).
- 세 칸 모두 호기 줄의 합 = 칸(기존보유 줄 포함).
- 공정 Capa 상세 ②(`bridge.가용대수`)·④(손실)·필요단축일정 가용과 같은 값.
- Static 대여 부호·불일치, GAP 의 「—」 규칙.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, cast

import pandas as pd
import pytest

from capa_simulation.services.availability_sheet import (
    BREAKDOWN_LENT_COLUMN,
    GAP_ROWS,
    KIND_BASELINE_LINE,
    REASON_NO_DYNAMIC_PROCESS,
    REASON_NO_STATIC_MONTH,
    REASON_NO_STATIC_PROCESS,
    REASON_UNIT_FILTER,
    ROW_GAP_AVAILABLE,
    ROW_GAP_LENT,
    ROW_GAP_OWNED,
    ROW_SCHEDULE_AVAILABLE,
    ROW_SCHEDULE_LENT,
    ROW_SCHEDULE_OWNED,
    ROW_STATIC_AVAILABLE,
    ROW_STATIC_LENT,
    ROW_STATIC_OWNED,
    SCHEDULE_ROWS,
    SHEET_ROWS,
    STATIC_ROWS,
    AvailabilitySheet,
    SheetView,
    build_availability_sheet,
    downtime_without_loss,
    sheet_view,
    unit_availability_breakdown,
)
from capa_simulation.services.equipment_availability import build_equipment_lifecycle_spans
from capa_simulation.services.equipment_contract import DOWNTIME_COLUMNS, EQUIPMENT_COLUMNS
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_master,
)
from capa_simulation.services.monthly_equipment_availability import (
    available_subtotal,
    build_monthly_equipment_availability,
    build_monthly_equipment_contributions,
    span_date_range,
)
from capa_simulation.services.process_cutoff import prepare_process_cutoff
from capa_simulation.services.process_equipment_timeline import build_process_equipment_timeline
from capa_simulation.services.required_shortening import plan_required_shortening
from capa_simulation.services.securement_cross_check import cross_check_from_monthly

MONTHS = [202610, 202611, 202612, 202701, 202702]
KEYS = ["생산계획년월", "공정"]
T = pd.Timestamp
EXACT = 1e-12
LINES = 1e-9


def _unit(
    name: str,
    process: str,
    *,
    existing: str = "Y",
    storage: str = "N",
    basis: str = "HBM",
    ratio: float = 1.0,
    arrival: str | None = None,
    qual: str | None = None,
    qual_status: str | None = None,
    stop: str | None = None,
    relocation: str | None = None,
    parent: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {column: None for column in EQUIPMENT_COLUMNS}
    row.update(
        {
            "Area Code": "Main",
            "공정대분류": "B/N",
            "공정소분류": process,
            "Maker": "m",
            "Model": "x",
            "설비명": name,
            "공정구분": "L",
            "투자구분": "양산",
            "사용기준": basis,
            "반입일정": T(arrival) if arrival else None,
            "Qual일정": T(qual) if qual else None,
            "Qual상태": qual_status,
            "정지일정": T(stop) if stop else None,
            "반출/이설일정": T(relocation) if relocation else None,
            "보관유무": storage,
            "기존설비여부": existing,
            "레이아웃표시": "N",
            "환산비": ratio,
            "Main 설비": parent,
        }
    )
    return row


def _down(name: str, start: str, end: str | None, kind: str = "고장") -> dict[str, Any]:
    return {
        "설비명": name,
        "비가동유형": kind,
        "시작일": T(start),
        "종료일": T(end) if end else pd.NaT,
        "상세사유": "x",
        "비고": "",
    }


def _fixture() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """P_A(경계 호기 모음) · P_B(202612 내내 비가동) · P_C(셋업 호기뿐)."""
    rows = [
        _unit("A1", "P_A"),
        _unit(
            "A2", "P_A", existing="N", arrival="2026-10-01", qual="2026-11-05", qual_status="확정"
        ),
        _unit("A3", "P_A", existing="N", storage="Y"),
        _unit("A4", "P_A", ratio=1.5),
        _unit("A5", "P_A", basis="범용"),
        _unit("A6", "P_A", stop="2026-11-25"),
        _unit("A7", "P_A", relocation="2026-12-10"),
        _unit(
            "A8", "P_A", existing="N", arrival="2026-10-01", qual="2026-11-20", qual_status="계획"
        ),
        _unit("A9", "P_A"),
        *[
            _unit(
                f"M1{suffix}",
                "P_A",
                ratio=0.25,
                parent="M1",
                stop="2026-11-12" if suffix == "B" else None,
                relocation="2026-12-20" if suffix == "B" else None,
            )
            for suffix in "ABCD"
        ],
        _unit("B1", "P_B"),
        _unit(
            "C1", "P_C", existing="N", arrival="2026-09-01", qual="2027-03-01", qual_status="계획"
        ),
    ]
    downtime = [
        _down("A1", "2026-11-10", "2026-11-20"),
        _down("A2", "2026-11-01", "2026-11-10"),  # Qual(11/05) 앞에서 시작해 뒤에서 끝남
        _down("A3", "2026-11-01", "2026-11-05"),  # 보관
        _down("A4", "2026-11-20", "2026-12-05"),  # 환산비 1.5, 달 걸침
        _down("A5", "2026-11-01", "2026-11-30"),  # 사용기준 밖
        _down("A6", "2026-11-20", "2026-11-30"),  # 정지일(11/25)을 덮음
        _down("A7", "2026-12-01", "2026-12-09"),  # 반출/이설 전날에 끝남
        _down("A8", "2026-11-01", "2026-11-03"),  # Qual 전 셋업 중 비가동
        _down("A9", "2027-01-10", None),  # 열린 비가동
        _down("M1C", "2026-12-20", "2026-12-25"),
        _down("M1D", "2026-11-12", "2026-11-14"),
        _down("A1", "2026-12-28", "2027-01-02", kind="공사"),
        _down("A1", "2026-12-30", "2027-01-05", kind="이설"),  # 겹친 비가동
        _down("B1", "2026-11-25", "2027-01-05"),  # 202612 내내 비가동
    ]
    master = prepare_equipment_master(pd.DataFrame(rows, columns=list(EQUIPMENT_COLUMNS)))
    down = prepare_downtime_schedule(
        pd.DataFrame(downtime, columns=list(DOWNTIME_COLUMNS)), equipment=master
    )
    baseline = pd.DataFrame(
        {"공정": ["P_A"], "분류": ["기존"], "기존보유대수": [3.0], "비고": [""]}
    )
    cutoff = prepare_process_cutoff(
        pd.DataFrame(
            {"공정": ["P_A", "P_B", "P_C"], "Cutoff일수": [15.0, 0.0, 10.0], "비고": [pd.NA] * 3}
        )
    )
    return master, down, baseline, cutoff


def _static(
    months: Sequence[int] = MONTHS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """P_A·P_B·P_C·P_D 보유·대여·가용. P_A 의 둘째 달 가용은 보유 − 대여보다 1 크다(불일치)."""
    records = [
        (month, process, owned, lent)
        for month in months
        for process, owned, lent in (
            ("P_A", 20.0, 2.0),
            ("P_B", 2.0, 0.0),
            ("P_C", 1.0, 0.0),
            ("P_D", 5.0, 1.0),
        )
    ]
    owned = pd.DataFrame(
        [(m, p, o) for m, p, o, _ in records], columns=["생산계획년월", "공정", "설비보유"]
    )
    lent = pd.DataFrame(
        [(m, p, x) for m, p, _, x in records], columns=["생산계획년월", "공정", "설비대여평가"]
    )
    available = pd.DataFrame(
        [(m, p, o - x) for m, p, o, x in records], columns=["생산계획년월", "공정", "가용대수"]
    )
    mismatch = available["공정"].eq("P_A") & available["생산계획년월"].eq(months[1])
    available.loc[mismatch, "가용대수"] += 1.0
    return owned, lent, available


class _Built:
    """실제·반사실 구간에서 나온 월별·호기별 기여와 시트."""

    def __init__(self, months: Sequence[int] = MONTHS) -> None:
        self.master, self.downtime, self.baseline, self.cutoff = _fixture()
        self.months = list(months)
        bounds = span_date_range(self.months, self.cutoff)
        assert bounds is not None
        start, end = bounds
        self.ratios = {
            str(unit): float(ratio)
            for unit, ratio in zip(self.master["설비명"], self.master["환산비"], strict=True)
            if pd.notna(ratio)
        }
        actual = build_equipment_lifecycle_spans(
            self.master, self.downtime, start_date=start, end_date=end, with_unit_share=True
        )
        free = build_equipment_lifecycle_spans(
            self.master,
            self.downtime.iloc[0:0],
            start_date=start,
            end_date=end,
            with_unit_share=True,
        )
        self.monthly = build_monthly_equipment_availability(
            actual, self.baseline, self.cutoff, self.months, conversion_ratios=self.ratios
        )
        self.free_monthly = build_monthly_equipment_availability(
            free, self.baseline, self.cutoff, self.months, conversion_ratios=self.ratios
        )
        self.contributions = build_monthly_equipment_contributions(
            actual, self.baseline, self.cutoff, self.months, conversion_ratios=self.ratios
        )
        self.free_contributions = build_monthly_equipment_contributions(
            free, self.baseline, self.cutoff, self.months, conversion_ratios=self.ratios
        )
        self.static = _static()
        self.sheet = build_availability_sheet(
            self.monthly, self.free_monthly, *self.static, self.months
        )

    def breakdown(self) -> pd.DataFrame:
        return unit_availability_breakdown(
            self.contributions,
            self.free_contributions,
            conversion_ratios=self.ratios,
            downtime=self.downtime,
            cutoff=self.cutoff,
        )


@pytest.fixture(scope="module")
def built() -> _Built:
    return _Built()


def _f(value: object) -> float:
    """프레임 칸 하나를 실수로(판다스 칸 타입 합집합을 좁힌다)."""
    return float(cast(Any, value))


def _line(lines: pd.DataFrame, month: int, unit: str) -> dict[str, Any]:
    """호기 분해에서 (달, 호기) 한 줄."""
    chosen = lines.loc[lines["생산계획년월"].eq(month) & lines["설비명"].eq(unit)]
    assert len(chosen) == 1, (month, unit)
    return {str(key): value for key, value in chosen.iloc[0].to_dict().items()}


def _cell(sheet: AvailabilitySheet, month: int, process: str, row: str) -> float:
    rows = sheet.rows.set_index(KEYS)
    return _f(rows.at[(month, process), row])


def _view(sheet: AvailabilitySheet, *processes: str, **kwargs: Any) -> SheetView:
    return sheet_view(sheet, processes=processes, **kwargs)


# ------------------------------------------------------------------ 항등식


def test_owned_plus_lent_is_available_and_available_is_todays_converted_subtotal(
    built: _Built,
) -> None:
    rows = built.sheet.rows.set_index(KEYS)
    subtotal = available_subtotal(built.monthly).set_index(KEYS)["Dynamic가용환산대수"]
    residual = rows[ROW_SCHEDULE_OWNED] + rows[ROW_SCHEDULE_LENT] - rows[ROW_SCHEDULE_AVAILABLE]
    assert residual.abs().max() < EXACT
    joined = subtotal.reindex(rows.index).fillna(0.0)
    assert (rows[ROW_SCHEDULE_AVAILABLE] - joined).abs().max() == 0.0
    # 대여는 늘 0 이하다 — 비가동은 가용을 깎기만 한다.
    assert rows[ROW_SCHEDULE_LENT].max() <= EXACT
    # 셋업 호기뿐인 공정(P_C)은 보유·가용 모두 0 이다.
    assert rows.loc[(slice(None), "P_C"), ROW_SCHEDULE_OWNED].abs().max() == 0.0


def test_setup_and_storage_downtime_is_not_lent(built: _Built) -> None:
    """셋업 중(A8, Qual 전)·보관(A3) 호기의 비가동은 가용을 깎지 않아 대여에 들지 않는다 — 그 칸의
    호기 상태 `운영 비가동` 과 다르다."""
    lines = built.breakdown()
    november = lines.loc[lines["생산계획년월"].eq(202611) & lines["공정"].eq("P_A")]
    assert set(november.loc[november[BREAKDOWN_LENT_COLUMN].lt(-EXACT), "설비명"]) == {
        "A1",
        "A2",
        "M1D",
    }
    offline = built.contributions.loc[
        built.contributions["분류"].eq("운영 비가동")
        & built.contributions["생산계획년월"].eq(202611)
        & built.contributions["공정"].eq("P_A")
    ]
    operating = float(offline["환산대수"].sum())
    lent = _cell(built.sheet, 202611, "P_A", ROW_SCHEDULE_LENT)
    assert lent == pytest.approx(-0.4, abs=LINES)
    assert -lent < operating - 0.1  # 셋업·보관 몫만큼 작다

    idle = downtime_without_loss(built.contributions, lines)
    november_idle = idle.loc[idle["생산계획년월"].eq(202611)]
    left = dict(zip(november_idle["설비명"], november_idle["환산대수"], strict=True))
    # A8(셋업) 3일, A3(보관) 5일, A2 는 Qual 앞 4일(11/01~11/04 — 11/05 Qual 은 다음 날부터 가용).
    assert left["A8"] == pytest.approx(3 / 30, abs=LINES)
    assert left["A3"] == pytest.approx(5 / 30, abs=LINES)
    assert left["A2"] == pytest.approx(4 / 30, abs=LINES)


def test_a_conversion_ratio_stays_on_the_converted_axis(built: _Built) -> None:
    """환산비 1.5 호기(A4)는 보유·대여·가용이 모두 환산대수다 — 대수 축과 섞지 않는다."""
    a4 = _line(built.breakdown(), 202612, "A4")
    assert a4["환산비"] == 1.5
    assert a4["보유"] == pytest.approx(1.5, abs=LINES)
    assert a4[BREAKDOWN_LENT_COLUMN] == pytest.approx(-16 / 31 * 1.5, abs=LINES)
    assert a4["가용"] == pytest.approx(15 / 31 * 1.5, abs=LINES)
    assert a4["손실 기여일수"] == 16


def test_module_thirds_add_up_to_the_cell() -> None:
    """모듈 셋(환산비 1/3)의 줄 합이 칸과 1e-9 안에서 같다 — 값은 반올림하지 않는다."""
    rows = [_unit(f"T{suffix}", "P_T", ratio=1 / 3, parent="T") for suffix in "ABC"]
    master = prepare_equipment_master(pd.DataFrame(rows, columns=list(EQUIPMENT_COLUMNS)))
    down = prepare_downtime_schedule(
        pd.DataFrame([_down("TB", "2026-11-03", "2026-11-09")], columns=list(DOWNTIME_COLUMNS)),
        equipment=master,
    )
    cutoff = prepare_process_cutoff(
        pd.DataFrame({"공정": ["P_T"], "Cutoff일수": [0.0], "비고": [pd.NA]})
    )
    months = [202611]
    bounds = span_date_range(months, cutoff)
    assert bounds is not None
    ratios = {f"T{suffix}": 1 / 3 for suffix in "ABC"}
    built_spans = [
        build_equipment_lifecycle_spans(
            master, table, start_date=bounds[0], end_date=bounds[1], with_unit_share=True
        )
        for table in (down, down.iloc[0:0])
    ]
    empty = pd.DataFrame(columns=["공정", "기존보유대수"])
    monthly, free_monthly = (
        build_monthly_equipment_availability(spans, empty, cutoff, months, conversion_ratios=ratios)
        for spans in built_spans
    )
    actual, free = (
        build_monthly_equipment_contributions(
            spans, empty, cutoff, months, conversion_ratios=ratios
        )
        for spans in built_spans
    )
    sheet = build_availability_sheet(monthly, free_monthly, None, None, None, months)
    lines = unit_availability_breakdown(actual, free, conversion_ratios=ratios)
    assert _cell(sheet, 202611, "P_T", ROW_SCHEDULE_OWNED) == pytest.approx(1.0, abs=LINES)
    for row, column in (
        (ROW_SCHEDULE_OWNED, "보유"),
        (ROW_SCHEDULE_LENT, BREAKDOWN_LENT_COLUMN),
        (ROW_SCHEDULE_AVAILABLE, "가용"),
    ):
        assert float(lines[column].sum()) == pytest.approx(
            _cell(sheet, 202611, "P_T", row), abs=LINES
        )


def test_unit_lines_add_up_to_every_schedule_cell(built: _Built) -> None:
    """세 칸 모두 그 (월, 공정)의 호기 줄(기존보유 줄 포함) 합이 칸이다."""
    lines = built.breakdown()
    sums = lines.groupby(KEYS)[["보유", BREAKDOWN_LENT_COLUMN, "가용"]].sum()
    rows = built.sheet.rows.set_index(KEYS)
    aligned = sums.reindex(rows.index).fillna(0.0)
    for line, row in (
        ("보유", ROW_SCHEDULE_OWNED),
        (BREAKDOWN_LENT_COLUMN, ROW_SCHEDULE_LENT),
        ("가용", ROW_SCHEDULE_AVAILABLE),
    ):
        assert (aligned[line] - rows[row]).abs().max() < LINES, row
    baseline = lines.loc[lines["구분"].eq(KIND_BASELINE_LINE)]
    assert set(baseline["공정"]) == {"P_A"}
    assert baseline["보유"].tolist() == [3.0] * len(MONTHS)


def test_the_unit_lines_carry_day_counts_and_downtime_notes(built: _Built) -> None:
    lines = built.breakdown()
    a1 = _line(lines, 202611, "A1")
    assert (a1["구간일수"], a1["비가동 없음 기여일수"], a1["실제 기여일수"]) == (30, 30, 25)
    assert a1["손실 기여일수"] == 5
    assert a1["비가동 내역"] == "고장 11.10~11.20"
    a9 = _line(lines, 202701, "A9")
    assert a9["비가동 내역"] == "고장 01.10~계속"
    # 겹친 비가동은 하루 한 번만 손실로 센다(A1 202701 — 공사·이설이 겹친다).
    assert _line(lines, 202701, "A1")["손실 기여일수"] == 9


# ------------------------------------------------------------------ 다른 화면과 같은 값


def test_the_sheet_matches_process_capa_detail_and_required_shortening(built: _Built) -> None:
    """공정마다 설비 일정 기준 가용 = 공정 Capa 상세 `bridge.가용대수`(5e-10 — 그쪽이 9자리로
    턴다), 대여 = −Σ 손실 환산대수(손실 호기 수 × 5e-10 — 호기마다 9자리로 반올림), 필요단축일정
    가용과 같다."""
    rows = built.sheet.rows.set_index(KEYS)
    for process in ("P_A", "P_B", "P_C"):
        timeline = build_process_equipment_timeline(
            built.master,
            built.downtime,
            built.baseline,
            built.cutoff,
            process=process,
            months=built.months,
        )
        bridge = timeline.bridge.set_index("생산계획년월")
        for month in built.months:
            available = _f(rows.at[(month, process), ROW_SCHEDULE_AVAILABLE])
            assert _f(bridge.at[month, "가용대수"]) == pytest.approx(available, abs=5e-10)
            losses = timeline.unit_months.loc[
                timeline.unit_months["생산계획년월"].eq(month), "손실 환산대수"
            ]
            tolerance = max(1, int(losses.gt(0).sum())) * 5e-10
            assert -float(losses.sum()) == pytest.approx(
                _f(rows.at[(month, process), ROW_SCHEDULE_LENT]), abs=tolerance
            )

    required = built.static[2][["생산계획년월", "공정"]].assign(소요대수=1.0)
    plan = plan_required_shortening(
        equipment=built.master,
        downtime=built.downtime,
        baseline=built.baseline,
        cutoff=built.cutoff,
        required_equipment=required,
        months=built.months,
        today=date(2026, 10, 17),
        levels=(1.0,),
    )
    planned = plan.at(1.0).process_months.set_index(KEYS)["가용대수"]
    for key, value in planned.items():
        assert _f(value) == pytest.approx(_f(rows.at[key, ROW_SCHEDULE_AVAILABLE]), abs=1e-9)


def test_the_cross_check_fills_a_dynamic_process_with_zero_not_static(built: _Built) -> None:
    """교차검증 분자 = 시트 가용 — 셋업 호기뿐인 공정(P_C)과 한 달 내내 비가동인 공정(P_B 202612)도
    0 이고, Static 으로 채운 공정(「Static대체」)이 아니다. Static 으로 채우는 것은 설비 일정 기준에
    공정 자체가 없을 때(P_D)뿐이다."""
    static_available = built.static[2]
    required = static_available[["생산계획년월", "공정"]].assign(소요대수=1.0)
    check = cross_check_from_monthly(static_available, built.monthly, required)
    table = check.rows.set_index(KEYS)
    rows = built.sheet.rows.set_index(KEYS)
    for process in ("P_A", "P_B", "P_C"):
        for month in built.months:
            assert _f(table.at[(month, process), "Dynamic가용대수"]) == pytest.approx(
                _f(rows.at[(month, process), ROW_SCHEDULE_AVAILABLE]), abs=EXACT
            )
    assert _f(table.at[(202612, "P_B"), "Dynamic가용대수"]) == 0.0
    assert _f(table.at[(202611, "P_C"), "Dynamic가용대수"]) == 0.0
    assert check.fallback_processes == ["P_D"]
    assert check.compared_processes == ["P_A", "P_B", "P_C"]
    assert check.months == built.months


# ------------------------------------------------------------------ Static·GAP


def test_static_lent_is_negative_and_a_mismatch_is_flagged(built: _Built) -> None:
    view = _view(built.sheet, "P_A")
    assert view.value(ROW_STATIC_OWNED, 202610) == 20.0
    assert view.value(ROW_STATIC_LENT, 202610) == -2.0
    assert view.value(ROW_STATIC_AVAILABLE, 202610) == 18.0
    assert view.value(ROW_STATIC_AVAILABLE, 202611) == 19.0
    assert view.mismatch == frozenset({202611})
    # 불일치가 아닌 달은 GAP 가용 = GAP 보유 + GAP 대여.
    for month in (202610, 202612):
        owned, lent, available = (view.value(row, month) for row in GAP_ROWS)
        assert owned is not None and lent is not None and available is not None
        assert owned + lent == pytest.approx(available, abs=LINES)


def test_gap_is_schedule_minus_static_and_a_month_long_downtime_still_has_a_gap(
    built: _Built,
) -> None:
    view = _view(built.sheet, "P_B")
    # P_B 202612: 설비 일정 기준 가용 0(한 달 내내 비가동), Static 가용 2 → GAP −2. 「—」 가 아니다.
    assert view.value(ROW_SCHEDULE_AVAILABLE, 202612) == 0.0
    assert view.value(ROW_GAP_AVAILABLE, 202612) == -2.0
    assert view.value(ROW_GAP_OWNED, 202612) == pytest.approx(1.0 - 2.0)
    assert view.value(ROW_GAP_LENT, 202612) == pytest.approx(-1.0 - 0.0)
    assert not view.reasons


def test_one_sided_processes_blank_the_missing_side_and_the_gap(built: _Built) -> None:
    static_only = _view(built.sheet, "P_D")
    for month in MONTHS:
        for row in (*SCHEDULE_ROWS, *GAP_ROWS):
            assert static_only.value(row, month) is None
            assert static_only.reason(row, month) == REASON_NO_DYNAMIC_PROCESS
        assert static_only.value(ROW_STATIC_OWNED, month) == 5.0

    owned, lent, available = _static()
    sheet = build_availability_sheet(
        built.monthly,
        built.free_monthly,
        owned.loc[owned["공정"].ne("P_C")],
        lent.loc[lent["공정"].ne("P_C")],
        available.loc[available["공정"].ne("P_C")],
        MONTHS,
    )
    assert sheet.dynamic_only == ["P_C"]
    dynamic_only = _view(sheet, "P_C")
    for row in (*STATIC_ROWS, *GAP_ROWS):
        assert dynamic_only.reason(row, 202610) == REASON_NO_STATIC_PROCESS
    assert dynamic_only.value(ROW_SCHEDULE_AVAILABLE, 202610) == 0.0


def test_a_month_without_static_data_blanks_static_and_gap_only(built: _Built) -> None:
    """Static 에 그 달 자료가 아예 없으면 Static·GAP 이 「—」 다. 이름이 맞는 공정의 빈 달은
    0 이다."""
    owned, lent, available = _static(MONTHS[:-1])
    sheet = build_availability_sheet(
        built.monthly, built.free_monthly, owned, lent, available, MONTHS
    )
    view = _view(sheet, "P_A")
    last = MONTHS[-1]
    for row in (*STATIC_ROWS, *GAP_ROWS):
        assert view.value(row, last) is None
        assert view.reason(row, last) == REASON_NO_STATIC_MONTH
    assert view.value(ROW_SCHEDULE_AVAILABLE, last) is not None

    # P_B 의 Static 한 달을 지우면 그 달은 0 이다(다른 공정에는 자료가 있다).
    def without_first(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.loc[~(frame["공정"].eq("P_B") & frame["생산계획년월"].eq(202610))]

    owned, lent, available = _static()
    sheet = build_availability_sheet(
        built.monthly,
        built.free_monthly,
        without_first(owned),
        without_first(lent),
        without_first(available),
        MONTHS,
    )
    view = _view(sheet, "P_B")
    assert view.value(ROW_STATIC_AVAILABLE, 202610) == 0.0
    assert view.value(ROW_GAP_AVAILABLE, 202610) == view.value(ROW_SCHEDULE_AVAILABLE, 202610)


def test_the_total_adds_only_the_processes_it_is_given(built: _Built) -> None:
    total = _view(built.sheet, "P_A", "P_B", "P_C")
    parts = [_view(built.sheet, process) for process in ("P_A", "P_B", "P_C")]
    for row in SHEET_ROWS:
        for month in MONTHS:
            expected = sum(part.value(row, month) or 0.0 for part in parts)
            assert total.value(row, month) == pytest.approx(expected, abs=LINES)
    assert total.mismatch == frozenset({202611})


def test_a_unit_filter_blanks_static_and_gap_with_its_reason(built: _Built) -> None:
    view = _view(built.sheet, "P_A", static_blocked=REASON_UNIT_FILTER)
    for month in MONTHS:
        for row in (*STATIC_ROWS, *GAP_ROWS):
            assert view.value(row, month) is None
            assert view.reason(row, month) == REASON_UNIT_FILTER
        assert view.value(ROW_SCHEDULE_AVAILABLE, month) is not None
    assert view.mismatch == frozenset()


def test_without_a_counterfactual_only_available_is_filled(built: _Built) -> None:
    """반사실 없이(「가용대수 비교」 그림) 만든 시트는 가용·Static·GAP 가용만 있다."""
    sheet = build_availability_sheet(built.monthly, None, *built.static, MONTHS)
    view = _view(sheet, "P_A")
    full = _view(built.sheet, "P_A")
    for month in MONTHS:
        assert view.value(ROW_SCHEDULE_OWNED, month) is None
        assert view.value(ROW_SCHEDULE_LENT, month) is None
        assert view.reason(ROW_SCHEDULE_OWNED, month) is None
        for row in (ROW_SCHEDULE_AVAILABLE, ROW_STATIC_AVAILABLE, ROW_GAP_AVAILABLE):
            assert view.value(row, month) == full.value(row, month)
        assert view.baseline[month] == 3.0
