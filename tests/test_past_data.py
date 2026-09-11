# Purpose: 과거 구간 공용 프로필의 정규화·저장과 계산 결과 병합 규칙을 고정한다.

from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.past_data import (
    PAST_DETAIL_COLUMNS,
    PAST_MONTH_COLUMNS,
    PAST_SECUREMENT_COLUMNS,
    empty_past_table,
    merge_past_frame,
    merge_past_months,
    past_plan_detail_to_wide,
    past_table_from_clipboard,
    prepare_past_table,
)


def _past_months() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [202511, 202512, 202601],
            "Density": [8.0, 9.0, 10.0],
            "Wafer Total": [100_000.0, 110_000.0, 120_000.0],
        }
    )


def test_a_repeated_key_is_rejected_before_it_reaches_the_primary_key() -> None:
    with pytest.raises(ValueError, match="같은 키가 두 번"):
        prepare_past_table(
            pd.DataFrame(
                {
                    "생산계획년월": [202511, 202511],
                    "공정": ["A", "A"],
                    "확보율": [1.0, 1.2],
                }
            ),
            PAST_SECUREMENT_COLUMNS,
        )


def test_a_month_outside_yyyymm_is_rejected() -> None:
    with pytest.raises(ValueError, match="YYYYMM"):
        prepare_past_table(
            pd.DataFrame({"생산계획년월": [202513], "Density": [1.0], "Wafer Total": [1.0]}),
            PAST_MONTH_COLUMNS,
        )


def test_a_blank_process_is_rejected_because_it_cannot_be_a_bottleneck() -> None:
    with pytest.raises(ValueError, match="공정은 비어 있을 수 없습니다"):
        prepare_past_table(
            pd.DataFrame({"생산계획년월": [202511], "공정": [""], "확보율": [1.0]}),
            PAST_SECUREMENT_COLUMNS,
        )


def test_calculated_months_win_so_a_wider_load_needs_no_cleanup() -> None:
    """적재 범위가 뒤로 넘어가도 입력을 지울 필요가 없어야 한다."""
    calculated = pd.DataFrame(
        {"생산계획년월": [202601], "년월": ["26.01"], "부하량": [99.0]},
    )

    merged = merge_past_months(
        calculated,
        _past_months(),
        value_columns={"Density": "부하량"},
        start_month=202511,
        end_month=202612,
    )

    assert merged["생산계획년월"].tolist() == [202511, 202512, 202601]
    # 겹치는 달은 계산이 이긴다.
    assert merged.loc[merged["생산계획년월"].eq(202601), "부하량"].tolist() == [99.0]
    assert merged["년월"].tolist() == ["25.11", "25.12", "26.01"]


def test_past_months_outside_the_query_range_are_left_out() -> None:
    calculated = pd.DataFrame({"생산계획년월": [202601], "년월": ["26.01"], "부하량": [99.0]})

    merged = merge_past_months(
        calculated,
        _past_months(),
        value_columns={"Density": "부하량"},
        start_month=202512,
        end_month=202612,
    )

    assert merged["생산계획년월"].tolist() == [202512, 202601]


def test_past_securement_rows_join_the_ranking_input() -> None:
    """확보율 오름차순이 곧 B/N 순위라 공정명을 따로 받지 않는다."""
    calculated = pd.DataFrame(
        {"생산계획년월": [202601], "공정": ["P-A"], "확보율": [1.1]},
    )
    past = prepare_past_table(
        pd.DataFrame(
            {
                "생산계획년월": [202511, 202511],
                "공정": ["P-A", "P-B"],
                "확보율": [1.4, 0.9],
            }
        ),
        PAST_SECUREMENT_COLUMNS,
    )

    merged = merge_past_frame(calculated, past, start_month=202511, end_month=202612)

    assert len(merged) == 3
    lowest = merged.loc[merged["생산계획년월"].eq(202511)].sort_values("확보율")
    assert lowest["공정"].tolist() == ["P-B", "P-A"]


def test_plan_detail_folds_customers_when_the_screen_does_not_show_them() -> None:
    """화면이 제품·Stack 으로만 볼 때 거래선별 행이 남으면 같은 제품이 여러 줄로 갈린다."""
    past = pd.DataFrame(
        {
            "생산계획년월": [202511, 202511],
            "제품정보": ["A", "A"],
            "Stack": ["12H", "12H"],
            "Customer": ["C1", "C2"],
            "생산수량": [100.0, 60.0],
        }
    )

    wide = past_plan_detail_to_wide(
        past,
        ["제품정보", "Stack"],
        start_month=202511,
        end_month=202612,
        exclude_months=set(),
    )

    assert wide["25.11"].tolist() == pytest.approx([160.0])


def test_a_calculated_month_is_left_out_of_the_past_detail() -> None:
    past = pd.DataFrame(
        {
            "생산계획년월": [202511, 202601],
            "제품정보": ["A", "A"],
            "Stack": ["12H", "12H"],
            "Customer": ["C1", "C1"],
            "생산수량": [100.0, 500.0],
        }
    )

    wide = past_plan_detail_to_wide(
        past,
        ["제품정보", "Stack"],
        start_month=202511,
        end_month=202612,
        exclude_months={202601},
    )

    assert list(wide.columns) == ["제품정보", "Stack", "25.11"]


def test_clipboard_import_reads_a_header_inclusive_block() -> None:
    content = "생산계획년월\t공정\t확보율\n202511\tP-A\t1.05\n202511\tP-B\t0.92\n"

    parsed = past_table_from_clipboard(content, PAST_SECUREMENT_COLUMNS)

    assert parsed["공정"].tolist() == ["P-A", "P-B"]
    assert parsed["확보율"].tolist() == pytest.approx([1.05, 0.92])


def test_the_shared_profile_round_trips_and_bumps_its_version(tmp_path: Path) -> None:
    """세 표가 한 버전을 공유한다. 부분 저장을 허용하면 어느 표가 어느 버전인지 알 수 없다."""
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    assert repository.load_global_past_data().version == 0

    saved = repository.replace_global_past_data(
        {
            "월별": _past_months(),
            "계획": empty_past_table(PAST_DETAIL_COLUMNS),
            "확보율": pd.DataFrame({"생산계획년월": [202511], "공정": ["P-A"], "확보율": [1.05]}),
        },
        source="테스트",
    )

    assert saved.version == 1
    assert saved.monthly["생산계획년월"].tolist() == [202511, 202512, 202601]
    assert saved.plan_detail.empty
    assert saved.securement["공정"].tolist() == ["P-A"]

    cleared = repository.replace_global_past_data(
        {
            "월별": empty_past_table(PAST_MONTH_COLUMNS),
            "계획": empty_past_table(PAST_DETAIL_COLUMNS),
            "확보율": empty_past_table(PAST_SECUREMENT_COLUMNS),
        },
        source="전체 해제",
    )

    assert cleared.version == 2
    assert cleared.monthly.empty
