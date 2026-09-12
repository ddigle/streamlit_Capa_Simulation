# Purpose: 선행 투입 물량 정규화와 Capa 부하 변동률 산출의 계약을 고정한다.

from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.advance_load import (
    apply_advance_to_density,
    apply_advance_to_securement,
    apply_advance_to_wafer,
    build_advance_load_ratio,
    empty_advance_load,
    merge_advance_load_edits,
    prepare_advance_load,
    unapplicable_advance_months,
)

MONTHS = [202601, 202602, 202603]


def _monthly_density() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "년월": ["26.01", "26.02", "26.03"],
            "부하량": [10.0, 20.0, 40.0],
        }
    )


def _advance() -> pd.DataFrame:
    # 1월에 2 앞당겨 넣고, 그만큼 3월 물량이 줄어든다.
    return pd.DataFrame({"생산계획년월": [202601, 202603], "선행 물량": [2.0, -2.0]})


def test_zero_and_blank_months_are_dropped_because_they_mean_nothing_was_entered() -> None:
    prepared = prepare_advance_load(
        pd.DataFrame(
            {
                "생산계획년월": [202601, 202602, 202603],
                "선행 물량": [2.0, 0.0, None],
            }
        )
    )

    assert prepared["생산계획년월"].tolist() == [202601]
    assert prepared["선행 물량"].tolist() == [2.0]


def test_a_repeated_month_is_rejected_before_it_reaches_the_primary_key() -> None:
    with pytest.raises(ValueError, match="같은 달이 두 번"):
        prepare_advance_load(
            pd.DataFrame({"생산계획년월": [202601, 202601], "선행 물량": [1.0, 2.0]})
        )


def test_a_month_outside_yyyymm_is_rejected() -> None:
    with pytest.raises(ValueError, match="YYYYMM"):
        prepare_advance_load(pd.DataFrame({"생산계획년월": [202613], "선행 물량": [1.0]}))


def test_capacity_is_unchanged_because_plan_and_rate_move_inversely() -> None:
    """선행 투입은 물량을 앞으로 옮긴 것이지 설비를 늘린 것이 아니다.

    `계획 × 확보율` 이 정확히 그대로여야 한다. 이 성질이 깨지면 선행을 켤 때마다 Capa
    막대가 움직여 무엇이 늘었는지 읽을 수 없다.
    """
    density = _monthly_density()
    ratio = build_advance_load_ratio(density, _advance())
    securement = pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "공정": ["Process-A"] * 3,
            "확보율": [1.2, 1.0, 0.8],
        }
    )

    adjusted_density = apply_advance_to_density(density, ratio)
    adjusted_securement = apply_advance_to_securement(securement, ratio)

    before = density["부하량"].to_numpy() * securement["확보율"].to_numpy()
    after = adjusted_density["부하량"].to_numpy() * adjusted_securement["확보율"].to_numpy()
    assert after == pytest.approx(before)
    # 계획은 입력한 만큼 정확히 움직인다. 화면 GAP 이 입력값과 같아야 확인이 된다.
    assert adjusted_density["부하량"].tolist() == [12.0, 20.0, 38.0]


def test_wafer_plan_moves_with_the_same_ratio_as_density() -> None:
    density = _monthly_density()
    ratio = build_advance_load_ratio(density, _advance())
    wafer = pd.DataFrame({"생산계획년월": MONTHS, "Wafer 부하량": [1_000.0, 2_000.0, 4_000.0]})

    adjusted = apply_advance_to_wafer(wafer, ratio)

    assert adjusted["Wafer 부하량"].to_numpy() == pytest.approx([1_200.0, 2_000.0, 3_800.0])


def test_every_process_in_a_month_gets_the_same_factor_so_the_ranking_holds() -> None:
    """한 달 안에서 같은 수를 곱하므로 B/N 공정이 선행 입력으로 바뀌면 안 된다."""
    density = _monthly_density()
    ratio = build_advance_load_ratio(density, _advance())
    securement = pd.DataFrame(
        {
            "생산계획년월": [202601, 202601, 202601],
            "공정": ["A", "B", "C"],
            "확보율": [1.5, 0.9, 1.1],
        }
    )

    adjusted = apply_advance_to_securement(securement, ratio)

    assert adjusted["확보율"].rank().tolist() == securement["확보율"].rank().tolist()
    assert adjusted["확보율"].to_numpy() == pytest.approx(
        [1.5 * 10 / 12, 0.9 * 10 / 12, 1.1 * 10 / 12]
    )


def test_a_month_driven_to_zero_is_left_unapplied_instead_of_dividing_by_zero() -> None:
    """한 달의 과한 입력 때문에 대시보드 전체가 사라지면 어디가 잘못됐는지 볼 수 없다."""
    density = _monthly_density()
    ratio = build_advance_load_ratio(
        density,
        pd.DataFrame({"생산계획년월": [202602], "선행 물량": [-20.0]}),
    )

    assert unapplicable_advance_months(ratio) == [202602]
    assert ratio["변동률"].tolist() == [1.0, 1.0, 1.0]
    assert apply_advance_to_density(density, ratio)["부하량"].tolist() == [10.0, 20.0, 40.0]


def test_an_empty_profile_changes_nothing() -> None:
    density = _monthly_density()
    ratio = build_advance_load_ratio(density, empty_advance_load())

    assert ratio["변동률"].tolist() == [1.0, 1.0, 1.0]
    assert unapplicable_advance_months(ratio) == []


def test_the_shared_profile_round_trips_and_bumps_its_version(tmp_path: Path) -> None:
    """표시명 프로필과 같은 결이다 — 현재본만 남기고 교체마다 version 이 오른다."""
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    assert repository.load_global_advance_load().version == 0

    saved = repository.replace_global_advance_load(_advance(), source="웹 직접 편집")

    assert saved.version == 1
    assert saved.rows["생산계획년월"].tolist() == [202601, 202603]
    assert saved.rows["선행 물량"].tolist() == [2.0, -2.0]

    cleared = repository.replace_global_advance_load(empty_advance_load(), source="전체 해제")

    # 0건 저장도 정상이며 캐시 키가 version 을 보므로 번호는 올라야 한다.
    assert cleared.version == 2
    assert cleared.rows.empty


def test_editing_a_narrow_view_keeps_the_months_it_could_not_show() -> None:
    """조회기간을 좁힌 채 저장한 사람이 다른 달의 입력을 모르는 새 날리면 안 된다."""
    stored = pd.DataFrame({"생산계획년월": [202601, 202605], "선행 물량": [2.0, -2.0]})

    merged = merge_advance_load_edits(stored, [202601, 202602], [3.0, 1.5])

    assert merged["생산계획년월"].tolist() == [202601, 202602, 202605]
    assert merged["선행 물량"].tolist() == [3.0, 1.5, -2.0]


def test_clearing_a_visible_month_to_zero_removes_only_that_month() -> None:
    stored = pd.DataFrame({"생산계획년월": [202601, 202605], "선행 물량": [2.0, -2.0]})

    merged = merge_advance_load_edits(stored, [202601], [0.0])

    assert merged["생산계획년월"].tolist() == [202605]


def test_a_negative_entry_survives_the_editor_round_trip(tmp_path: Path) -> None:
    """기투입 차감은 음수로 넣는다. 부호가 도중에 잘리면 선행 기능의 반쪽이 사라진다."""
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    merged = merge_advance_load_edits(empty_advance_load(), [202601, 202603], [2.5, -2.5])
    saved = repository.replace_global_advance_load(merged, source="테스트")

    assert saved.rows["선행 물량"].tolist() == [2.5, -2.5]


def test_a_month_outside_the_ratio_keeps_its_own_values() -> None:
    """변동률 표에 없는 달은 손대지 않는다.

    변동률은 월별 부하량에서 만드는데 확보율·Wafer 는 거기 없는 달을 가질 수 있다 — 과거
    구간을 공정별 확보율에만 넣고 월별 실적에는 넣지 않으면 그렇다. 없는 달을 결측으로
    곱하면 그 달이 오류도 경고도 없이 빈칸이 된다.
    """
    monthly_density = pd.DataFrame({"생산계획년월": [202601, 202603], "부하량": [50.0, 80.0]})
    ratio = build_advance_load_ratio(
        monthly_density, pd.DataFrame({"생산계획년월": [202601], "선행 물량": [10.0]})
    )

    securement = pd.DataFrame(
        {
            "생산계획년월": [202601, 202602, 202603],
            "공정": ["A", "A", "A"],
            "확보율": [1.5, 1.4, 1.2],
        }
    )
    applied = apply_advance_to_securement(securement, ratio)
    assert not applied["확보율"].isna().any()
    # 202602 는 변동률 표에 없으므로 그대로다.
    assert float(applied.loc[applied["생산계획년월"].eq(202602), "확보율"].iloc[0]) == 1.4

    wafer = pd.DataFrame({"생산계획년월": [202601, 202602], "Wafer 부하량": [1000.0, 2000.0]})
    applied_wafer = apply_advance_to_wafer(wafer, ratio)
    assert not applied_wafer["Wafer 부하량"].isna().any()
    assert (
        float(applied_wafer.loc[applied_wafer["생산계획년월"].eq(202602), "Wafer 부하량"].iloc[0])
        == 2000.0
    )
