# Purpose: 과거 구간 공용 프로필의 정규화·저장과 계산 결과 병합 규칙을 고정한다.

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from capa_simulation.persistence import past_data_store, sync_state
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.past_data import (
    PAST_DETAIL_COLUMNS,
    PAST_MONTH_COLUMNS,
    PAST_SECUREMENT_COLUMNS,
    empty_past_table,
    merge_past_frame,
    merge_past_months,
    merge_past_plan_detail,
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


def test_failed_profile_replacement_restores_all_tables_before_reporting_a_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """교체 도중 실패하면 세 표·버전이 함께 복구되고 커밋된 변경만 동기화에 보인다."""
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    original = repository.replace_global_past_data(
        {
            "월별": _past_months(),
            "계획": pd.DataFrame(
                {
                    "생산계획년월": [202511],
                    "제품정보": ["A"],
                    "Stack": ["12H"],
                    "Customer": ["C1"],
                    "생산수량": [100.0],
                }
            ),
            "확보율": pd.DataFrame({"생산계획년월": [202511], "공정": ["P-A"], "확보율": [1.05]}),
        },
        source="이전 저장본",
    )
    cleared_tables = {
        "월별": empty_past_table(PAST_MONTH_COLUMNS),
        "계획": empty_past_table(PAST_DETAIL_COLUMNS),
        "확보율": empty_past_table(PAST_SECUREMENT_COLUMNS),
    }
    committed_versions: list[int] = []

    def record_committed_version(path: Path) -> None:
        assert path == repository.database_path
        committed_versions.append(repository.load_global_past_data().version)

    monkeypatch.setattr(sync_state, "mark_dirty", record_committed_version)
    insert_profile = past_data_store.insert_global_past_data

    def fail_after_insert(
        connection: duckdb.DuckDBPyConnection,
        tables: dict[str, pd.DataFrame],
        *,
        version: int,
        source: str,
    ) -> None:
        insert_profile(connection, tables, version=version, source=source)
        raise RuntimeError("저장 중 오류")

    with monkeypatch.context() as failure:
        failure.setattr(past_data_store, "insert_global_past_data", fail_after_insert)
        with pytest.raises(RuntimeError, match="저장 중 오류"):
            repository.replace_global_past_data(cleared_tables, source="실패한 교체")

    restored = repository.load_global_past_data()
    assert restored.version == original.version
    assert restored.source == original.source
    assert restored.updated_at == original.updated_at
    for field in ("monthly", "plan_detail", "securement"):
        pd.testing.assert_frame_equal(getattr(restored, field), getattr(original, field))
    assert committed_versions == []

    saved = repository.replace_global_past_data(cleared_tables, source="성공한 교체")
    assert saved.version == original.version + 1
    assert saved.monthly.empty and saved.plan_detail.empty and saved.securement.empty
    assert committed_versions == [saved.version]


def test_merging_past_detail_keeps_the_display_order() -> None:
    """과거를 붙인다고 제품 차례가 바뀌면 안 된다.

    `groupby` 의 기본값은 그룹 키로 다시 정렬한다. 들어온 표는 이미 `apply_display_order` 로
    사용자가 정한 차례를 갖고 있으므로, 그대로 두면 과거를 넣는 순간 가나다순으로 뒤집힌다.
    """
    detail = pd.DataFrame(
        {
            "제품정보": ["HBM라", "HBM다E", "HBM나"],
            "Stack": ["12H", "8H", "4H"],
            "26.01": [10.0, 20.0, 30.0],
        }
    )
    past = pd.DataFrame({"제품정보": ["HBM라"], "Stack": ["12H"], "25.12": [5.0]})

    merged = merge_past_plan_detail(detail, past, ["제품정보", "Stack"])

    assert list(merged["제품정보"]) == ["HBM라", "HBM다E", "HBM나"]
    assert float(merged.loc[0, "25.12"]) == 5.0
    assert float(merged.loc[0, "26.01"]) == 10.0


def test_a_product_only_in_the_past_lands_where_the_display_order_says() -> None:
    """과거에만 있는 분류도 표시순서를 따른다. `sort=False` 만 쓰면 맨 뒤에 붙는다."""
    detail = pd.DataFrame({"제품정보": ["B"], "Stack": ["8H"], "26.01": [10.0]})
    past = pd.DataFrame({"제품정보": ["A"], "Stack": ["4H"], "25.12": [5.0]})
    order = pd.DataFrame(
        [
            ["생산 계획", "PKG PLAN", 1, "제품정보", "오름차순", None, None, "Y"],
        ],
        columns=[
            "페이지 구분",
            "탭 구분",
            "정렬우선순위",
            "분류컬럼",
            "정렬방식",
            "분류값",
            "값표시순서",
            "활성여부",
        ],
    )

    merged = merge_past_plan_detail(detail, past, ["제품정보", "Stack"], order)

    assert list(merged["제품정보"]) == ["A", "B"]


def test_merging_without_past_rows_changes_nothing() -> None:
    """과거 입력이 없으면 원래 표를 그대로 돌려준다."""
    detail = pd.DataFrame({"제품정보": ["B", "A"], "Stack": ["8H", "4H"], "26.01": [1.0, 2.0]})

    merged = merge_past_plan_detail(
        detail, pd.DataFrame(columns=["제품정보"]), ["제품정보", "Stack"]
    )

    assert list(merged["제품정보"]) == ["B", "A"]


def _stored_profile_tables() -> dict[str, pd.DataFrame]:
    """세 표에 모두 값이 든 상태."""
    return {
        "월별": _past_months(),
        "계획": pd.DataFrame(
            {
                "생산계획년월": [202511, 202512],
                "제품정보": ["DEMO-A", "DEMO-A"],
                "Stack": ["8H", "8H"],
                "Customer": ["DEMO-C", "DEMO-C"],
                "생산수량": [1_000.0, 1_100.0],
            }
        ),
        "확보율": pd.DataFrame(
            {
                "생산계획년월": [202511, 202512],
                "공정": ["DEMO-P", "DEMO-P"],
                "확보율": [1.02, 0.98],
            }
        ),
    }


def test_saving_one_table_keeps_the_other_two_even_when_the_screen_emptied_them(
    tmp_path: Path,
) -> None:
    """`Past Data 포함` 토글을 끈 채 저장해도 저장된 과거 구간이 남아야 한다.

    HOME 은 토글이 꺼지면 **표시용으로 행을 비운** 프로필을 만든다. 저장이 화면에서 받은
    그 프로필을 「저장된 값」으로 쓰면, 붙여넣지 않은 두 표가 빈 채로 기록되어 과거 구간이
    사라진다. `replace_global_past_data` 는 지우고 다시 넣으므로 되돌릴 수 없다 — 그래서
    저장은 화면을 믿지 않고 DB 를 다시 읽는다.
    """
    from capa_simulation.components.past_data_management import merged_past_tables

    database_path = str(tmp_path / "past.duckdb")
    repository = DuckDBScenarioRepository(Path(database_path))
    repository.initialize()
    repository.replace_global_past_data(_stored_profile_tables(), source="테스트 초기값")

    # 월별만 새로 붙여넣은 상태. 나머지 둘은 손대지 않았다.
    draft = {"월별": _past_months().assign(Density=[8.5, 9.5, 10.5])}

    merged = merged_past_tables(database_path, draft)

    assert merged["월별"]["Density"].tolist() == [8.5, 9.5, 10.5]
    assert len(merged["계획"]) == 2, "붙여넣지 않은 표가 비워졌습니다 — 과거 구간 소실"
    assert len(merged["확보율"]) == 2, "붙여넣지 않은 표가 비워졌습니다 — 과거 구간 소실"


def test_the_past_tab_is_given_the_stored_profile_not_the_display_filtered_one() -> None:
    """HOME 이 관리 탭에 넘기는 것은 **저장된** 프로필이어야 한다.

    표시용으로 비운 쪽을 넘기면 화면이 「저장 0행」으로 보이고, 저장이 그 빈 값을 되쓴다.
    배선이 한 글자만 어긋나도 데이터가 사라지므로 소스에서 고정한다.
    """
    source = (Path(__file__).resolve().parents[1] / "app_pages" / "home.py").read_text(
        encoding="utf-8"
    )

    assert "render_past_data_management(str(DUCKDB_PATH.resolve()), stored_past_profile)" in source
