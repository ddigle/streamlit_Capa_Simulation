# Purpose: UPEH 가정 사후 배수가 RQ_UPEH 를 고친 재계산과 같은지와 토큰·역산·효과를 본다.

"""UPEH 가정 — `services/upeh_assumption.py`.

**선형 대조가 이 기능의 전제다.** 가정은 기준정보를 고치지 않고 소요대수에 ÷f 를 사후로 건다. 그것이
맞는 까닭은 대당 Capa 가 환산 UPEH 에 선형이고 소요대수에 올림이 없어서다. 내장 합성 시드의
`RQ_UPEH` 를 구간 달만 고쳐(Main UPEH ×f · MI ST ÷f) 대당 Capa → 소요대수를 다시 계산한 결과와 사후
배수의 결과를 맞댄다 — 식에 상한·하한·반올림이 들어오면 이 시험이 깨진다. 합성 시드의 수치는 업무
사실이 아니다(샘플).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from test_required_shortening import PROCESS, _cutoff

from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.process_capa_detail import (
    build_process_capa_summary,
    process_capa_kpis,
)
from capa_simulation.services.required_equipment import calculate_required_equipment
from capa_simulation.services.required_shortening import (
    STATUS_EXPIRED,
    plan_from_availability,
)
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.unit_capacity import calculate_unit_capacity
from capa_simulation.services.upeh_assumption import (
    INVERSE_ABOVE,
    INVERSE_IMPOSSIBLE,
    INVERSE_MET,
    INVERSE_NO_MONTHS,
    INVERSE_OK,
    NO_ASSUMPTION,
    AssumptionEffect,
    PlanCounts,
    UpehAssumption,
    assumption_label,
    clamp_percent,
    demand_change_text,
    effect_text,
    inverse_text,
    percent_to_clear_securement,
    percent_to_clear_target,
    plan_counts,
    pull_changes,
    required_drop,
    scale_required_equipment,
    scale_securement_rate,
    token_factor,
    token_label,
    token_months,
)

JUNE, JULY, AUGUST = 202606, 202607, 202608


# ------------------------------------------------------------------ 선형 대조


def _capacity_and_demand(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    unit_capacity = calculate_unit_capacity(
        upeh=tables["RQ_UPEH"],
        run_rate=tables["RQ_RUN_RATE"],
        vital=tables["RQ_VITAL"],
        module=tables["RQ_MODULE"],
        run_day=tables["RQ_RUN_DAY"],
        lot_ratio=tables["RQ_LOT_RATIO"],
        wf_ratio=tables["RQ_WF_RATIO"],
    )
    required = calculate_required_equipment(
        reqb=tables["RQ_REQB"],
        plan=tables["RQ_PKG_PLAN"],
        yield_data=tables["RQ_YLD"],
        chip_qty=tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )
    return unit_capacity, required


def _with_upeh(tables: dict[str, pd.DataFrame], percent: int, months: set[int]) -> pd.DataFrame:
    """구간 달의 `RQ_UPEH` 를 고친 사본 — Main 은 UPEH ×f, MI 는 ST ÷f(같은 뜻)."""
    factor = percent / 100
    upeh = tables["RQ_UPEH"].copy()
    inside = pd.to_numeric(upeh["생산계획년월"], errors="coerce").isin(list(months))
    area = upeh["Area_Name"].astype("string").str.strip()
    main = (inside & area.eq("Main")).to_numpy()
    mi = (inside & area.eq("MI")).to_numpy()
    upeh["UPEH"] = pd.to_numeric(upeh["UPEH"], errors="coerce").astype("float64")
    upeh["ST"] = pd.to_numeric(upeh["ST"], errors="coerce").astype("float64")
    upeh.loc[main, "UPEH"] = upeh.loc[main, "UPEH"] * factor
    upeh.loc[mi, "ST"] = upeh.loc[mi, "ST"] / factor
    return upeh


@pytest.mark.parametrize("percent", [80, 110, 150])
def test_the_post_hoc_scale_equals_recalculating_with_edited_upeh(percent: int) -> None:
    """사후 배수(소요 ÷f, 대당 Capa ×f) = `RQ_UPEH` 를 구간 달만 고쳐 다시 계산한 결과."""
    tables = dict(build_builtin_seed_dataset().reference_tables)
    unit_capacity, required = _capacity_and_demand(tables)
    months = sorted({int(month) for month in required["생산계획년월"]})
    window = set(months[len(months) // 3 : 2 * len(months) // 3])
    # 시드에는 Main·MI 두 경로가 다 있어야 대조가 두 식을 다 덮는다(샘플 관측).
    assert set(tables["RQ_UPEH"]["Area_Name"].astype(str)) >= {"Main", "MI"}
    edited = {**tables, "RQ_UPEH": _with_upeh(tables, percent, window)}
    edited_capacity, edited_required = _capacity_and_demand(edited)

    token = UpehAssumption(percent, min(window), max(window)).token(months)
    scaled = scale_required_equipment(required, token)
    # 계산은 같은 입력 차례로 같은 행을 낸다 — 값 칸만 다르다.
    values = ["소요대수", "대당 Capa"]
    pd.testing.assert_frame_equal(
        scaled.drop(columns=values).reset_index(drop=True),
        edited_required.drop(columns=values).reset_index(drop=True),
    )
    for column in values:
        assert pd.to_numeric(scaled[column]).to_numpy(dtype="float64") == pytest.approx(
            pd.to_numeric(edited_required[column]).to_numpy(dtype="float64"), rel=1e-12
        ), column
    assert scaled["소요대수"].dtype == required["소요대수"].dtype
    # 구간 밖 달은 그대로다.
    outside = ~pd.to_numeric(required["생산계획년월"]).isin(list(window))
    assert (
        scaled.loc[outside.to_numpy(), "소요대수"].to_numpy()
        == required.loc[outside.to_numpy(), "소요대수"].to_numpy()
    ).all()
    assert len(edited_capacity) == len(unit_capacity)


def test_110_percent_cuts_demand_by_one_eleventh_not_ten_percent() -> None:
    required = pd.DataFrame(
        {"생산계획년월": [JUNE, JULY], "공정": ["A", "A"], "소요대수": [11.0, 4.0]}
    )
    scaled = scale_required_equipment(required, (110, (JUNE,)))
    assert scaled["소요대수"].tolist() == pytest.approx([10.0, 4.0])
    assert demand_change_text(110) == "소요 −9.1%"
    assert demand_change_text(90) == "소요 +11.1%"
    assert demand_change_text(100) == "소요 그대로"


def test_the_scale_never_touches_its_input() -> None:
    """로더 프레임은 같은 회차의 다른 쓰임과 같은 객체다 — 사본에만 건다."""
    required = pd.DataFrame(
        {"생산계획년월": [JUNE], "공정": ["A"], "소요대수": [11.0], "대당 Capa": [2.0]}
    )
    before = required.copy()
    scaled = scale_required_equipment(required, (110, (JUNE,)))
    pd.testing.assert_frame_equal(required, before)
    assert scaled["대당 Capa"].tolist() == pytest.approx([2.2])
    assert scale_required_equipment(required, NO_ASSUMPTION) is required


# ------------------------------------------------------------------ 토큰


def test_the_token_is_empty_at_100_percent_or_without_overlap() -> None:
    assert UpehAssumption(100, JUNE, AUGUST).token([JUNE, JULY]) == ()
    assert UpehAssumption(110, AUGUST, AUGUST).token([JUNE, JULY]) == ()
    assert UpehAssumption(110, JULY, AUGUST).token([JUNE, JULY, AUGUST, 202609]) == (
        110,
        (JULY, AUGUST),
    )
    # 시작이 끝보다 늦으면 바꿔 읽는다.
    assert UpehAssumption(120, AUGUST, JUNE).token([JULY]) == (120, (JULY,))
    assert token_factor(()) == 1.0
    assert token_factor((110, (JULY,))) == pytest.approx(1.1)
    assert token_months((110, (JULY, AUGUST))) == {JULY, AUGUST}
    with pytest.raises(ValueError):
        UpehAssumption(151, JUNE, JULY)


def test_labels_name_the_percent_and_the_span() -> None:
    assert assumption_label(UpehAssumption(110, JULY, 202612)) == "UPEH 가정 110% · 26-07–26-12"
    assert token_label((110, (JULY, AUGUST))) == "UPEH 가정 110% · 26-07–26-08"
    assert token_label(()) == ""
    assert clamp_percent(171) == 150 and clamp_percent(42) == 80 and clamp_percent(118) == 118


def test_the_securement_rate_is_recomputed_by_the_same_function() -> None:
    rate = calculate_securement_rate(
        pd.DataFrame({"생산계획년월": [JUNE, JULY], "공정": ["A", "A"], "가용대수": [10.0, 10.0]}),
        pd.DataFrame({"생산계획년월": [JUNE, JULY], "공정": ["A", "A"], "소요대수": [11.0, 11.0]}),
    )
    before = rate.copy()
    scaled = scale_securement_rate(rate, (110, (JULY,)))
    pd.testing.assert_frame_equal(rate, before)
    assert scaled.sort_values("생산계획년월")["확보율"].tolist() == pytest.approx([10 / 11, 1.0])


# ------------------------------------------------------------------ 역산


def _months_frame(
    rows: list[tuple[int, float, float]], state: str = "단축으로 해소"
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": [PROCESS] * len(rows),
            "생산계획년월": [month for month, _, _ in rows],
            "목표대수": [target for _, target, _ in rows],
            "가용대수": [available for _, _, available in rows],
            "상태": [state] * len(rows),
        }
    )


def test_the_target_inverse_is_the_smallest_whole_percent() -> None:
    frame = _months_frame([(JUNE, 11.8, 10.0), (JULY, 10.5, 10.0), (AUGUST, 30.0, 10.0)])
    inverse = percent_to_clear_target(frame, [JUNE, JULY])
    assert (inverse.status, inverse.percent) == (INVERSE_OK, 118)
    assert inverse.button_value == 118
    assert inverse_text("구간 안 단축 0", inverse) == "구간 안 단축 0 → UPEH ≥ 118%"
    # 구간 밖 달(8월)은 보지 않는다. 넣으면 300% 라 「150% 로도 못 채움」.
    above = percent_to_clear_target(frame, [AUGUST])
    assert (above.status, above.percent) == (INVERSE_ABOVE, 300)
    assert percent_to_clear_target(frame, [AUGUST]).button_value is None
    # 가용 0 인 달이 있으면 UPEH 로는 못 채운다.
    zero = _months_frame([(JUNE, 2.0, 0.0)])
    assert percent_to_clear_target(zero, [JUNE]).status == INVERSE_IMPOSSIBLE
    # 이미 넉넉하면 80% 로도 충족, 볼 달이 없으면 그 갈래.
    plenty = _months_frame([(JUNE, 5.0, 10.0)])
    assert percent_to_clear_target(plenty, [JUNE]).status == INVERSE_MET
    assert percent_to_clear_target(plenty, [JULY]).status == INVERSE_NO_MONTHS
    # 기한 지난 달은 당겨서 바꿀 수 없으니 보지 않는다.
    expired = _months_frame([(JUNE, 30.0, 10.0)], state=STATUS_EXPIRED)
    assert percent_to_clear_target(expired, [JUNE], skip_states=(STATUS_EXPIRED,)).status == (
        INVERSE_NO_MONTHS
    )


def test_a_plan_at_the_inverse_percent_needs_no_shortening_and_one_percent_less_does() -> None:
    """역산 성질 — ceil% 로 다시 세운 계획은 구간 달이 모두 충족이고, (ceil−1)% 면 부족이 하나
    이상이다."""
    months = (JUNE, JULY)
    available = pd.DataFrame(
        {"생산계획년월": list(months), "공정": [PROCESS] * 2, "가용대수": [10.0, 10.0]}
    )
    required = pd.DataFrame(
        {"생산계획년월": list(months), "공정": [PROCESS] * 2, "소요대수": [10.3, 9.7]}
    )

    def plan(demand: pd.DataFrame) -> pd.DataFrame:
        (level,) = plan_from_availability(
            available=available,
            required=demand,
            candidates=[],
            cutoff_days={PROCESS: 10.0},
            processes=[PROCESS],
            months=months,
            today=date(2026, 1, 1),
            levels=(1.1,),
        )
        return level.process_months

    official = plan(required)
    inverse = percent_to_clear_target(official, months)
    assert inverse.status == INVERSE_OK and inverse.percent is not None
    at = plan(scale_required_equipment(required, (inverse.percent, months)))
    below = plan(scale_required_equipment(required, (inverse.percent - 1, months)))
    assert (pd.to_numeric(at["과부족"]) >= 0).all()
    assert (pd.to_numeric(below["과부족"]) < 0).any()
    assert _cutoff().shape[0] == 1


def test_the_securement_inverse_turns_every_window_month_secure() -> None:
    thresholds = SecurementThresholds(1.095, 0.995)
    months = [JUNE, JULY]
    rate = calculate_securement_rate(
        pd.DataFrame({"생산계획년월": months, "공정": ["A", "A"], "가용대수": [10.0, 9.0]}),
        pd.DataFrame({"생산계획년월": months, "공정": ["A", "A"], "소요대수": [10.0, 10.0]}),
    )
    owned = pd.DataFrame({"생산계획년월": months, "공정": ["A", "A"], "설비보유": [10.0, 9.0]})
    lent = pd.DataFrame({"생산계획년월": months, "공정": ["A", "A"], "설비대여평가": [0.0, 0.0]})

    def shortage_months(percent: int) -> int:
        scaled = scale_securement_rate(rate, (percent, tuple(months)))
        summary = build_process_capa_summary(
            scaled, owned, lent, process="A", months=months, thresholds=thresholds
        )
        return process_capa_kpis(summary).shortage_months

    official = build_process_capa_summary(
        rate, owned, lent, process="A", months=months, thresholds=thresholds
    )
    inverse = percent_to_clear_securement(official, thresholds, months)
    assert inverse.status == INVERSE_OK and inverse.percent is not None
    # 7월이 결정한다 — 1.095 × 10 ÷ 9 = 1.2166… → 122%.
    assert inverse.percent == 122
    assert shortage_months(inverse.percent) == 0
    assert shortage_months(inverse.percent - 1) > 0


# ------------------------------------------------------------------ 효과


def test_the_effect_line_reads_official_to_assumed_with_continuous_values() -> None:
    effect = AssumptionEffect(
        percent=110,
        applied=True,
        required_drop=1.13,
        official=PlanCounts(shortened=3, days=45, new=2, max_gap=2.5),
        assumed=PlanCounts(shortened=2, days=12, new=0, max_gap=0.75),
        shortage_months=(4, 2),
    )
    assert effect_text(effect) == (
        "소요 −9.1%(월 최대 −1.13대) · 확보기준 미달 4→2개월 · 단축 호기 3→2 · 단축일 합계 45→12일 "
        "· "
        "신규 2→0 · 월 최대 환산 부족 2.50→0.75"
    )


def test_when_whole_counts_stay_the_effect_says_the_same_units_are_pulled_less() -> None:
    effect = AssumptionEffect(
        percent=110,
        applied=True,
        official=PlanCounts(shortened=2, days=30, new=0, max_gap=1.2),
        assumed=PlanCounts(shortened=2, days=21, new=0, max_gap=1.0),
    )
    assert effect_text(effect).endswith("부족이 남아 같은 호기를 덜 당김(−9일)")


def test_an_assumption_outside_the_screen_months_says_no_month_applies() -> None:
    assert "적용된 달 없음" in effect_text(AssumptionEffect(percent=120, applied=False))


def test_plan_counts_and_pull_changes_read_the_unit_table() -> None:
    official = pd.DataFrame(
        {
            "공정": [PROCESS, PROCESS, PROCESS, "다른 공정"],
            "호기": ["A1", "B2", "추가1", "Z9"],
            "구분": ["단축", "단축", "신규", "단축"],
            "단축일수": [45, 10, None, 3],
        }
    )
    assumed = official.iloc[[1]].assign(단축일수=[4])
    months = pd.DataFrame(
        {"공정": [PROCESS, PROCESS], "생산계획년월": [JUNE, JULY], "과부족": [-1.25, 0.5]}
    )
    assert plan_counts(official, months, [PROCESS]) == PlanCounts(2, 55, 1, 1.25)
    assert pull_changes(official, assumed, PROCESS) == {"A1": (45, 0), "B2": (10, 4)}
    official_demand = pd.DataFrame({"생산계획년월": [JUNE, JULY], "소요대수": [11.0, 4.0]})
    assumed_demand = pd.DataFrame({"생산계획년월": [JUNE, JULY], "소요대수": [10.0, 4.0]})
    assert required_drop(official_demand, assumed_demand, [JUNE]) == pytest.approx(1.0)
