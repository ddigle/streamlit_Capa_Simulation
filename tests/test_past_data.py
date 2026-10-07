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
    display_month_range,
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
    assert merged.loc[0, "25.12"] == 5.0
    assert merged.loc[0, "26.01"] == 10.0


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


# 붙여넣기의 빈칸·못 읽는 글자(2026-09-29 빈칸 횡전개). 이전에는 값 칸을
# `to_numeric(errors="coerce")` 뒤 0 으로 채우고 년월은 못 읽으면 말없이 떨궜다. 저장은 그 표를
# 지우고 다시 넣으므로 떨어진 행은 저장하는 순간 사라지고, 0 이 된 값은 B/N 을 비관 쪽으로
# 틀리게 했다. 컬럼마다 빈칸 규칙이 다르다 — 계획 세부수량의 `생산수량` 만 빈칸 = 0 이다.

_SECUREMENT_HEADER = "생산계획년월\t공정\t확보율\n"
_MONTH_HEADER = "생산계획년월\tDensity\tWafer Total\n"
_DETAIL_HEADER = "생산계획년월\t제품정보\tStack\tCustomer\t생산수량\n"


def test_a_blank_or_percent_securement_is_refused_with_the_row_it_came_from() -> None:
    """확보율 빈칸·`105%` 가 0 이 되면 그 공정이 그 달 B/N 1위가 되고 B/N Capa 가 0 이 된다.

    어느 행인지(년월 · 공정) 적어야 사용자가 Excel 에서 찾아 고친다.
    """
    content = _SECUREMENT_HEADER + "202511\tP-A\t1.05\n202512\tP-A\t\n202512\tP-B\t105%\n"

    with pytest.raises(ValueError) as caught:
        past_table_from_clipboard(content, PAST_SECUREMENT_COLUMNS)

    message = str(caught.value)
    assert "202512 · P-A → 빈칸" in message
    assert "202512 · P-B → '105%'" in message
    assert "B/N 1위" in message
    assert "`1.05`" in message


def test_a_blank_securement_cannot_reach_the_store_through_the_repository(
    tmp_path: Path,
) -> None:
    """붙여넣기만이 아니라 저장 경로도 같은 규칙이다. 0019 의 `확보율` 은 NOT NULL 이다."""
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    stored = repository.replace_global_past_data(_stored_profile_tables(), source="기존")

    with pytest.raises(ValueError, match="빈칸"):
        repository.replace_global_past_data(
            {
                **_stored_profile_tables(),
                "확보율": pd.DataFrame(
                    {"생산계획년월": [202511], "공정": ["DEMO-P"], "확보율": [float("nan")]}
                ),
            },
            source="빈칸",
        )

    kept = repository.load_global_past_data()
    assert kept.version == stored.version
    pd.testing.assert_frame_equal(kept.securement, stored.securement)


@pytest.mark.parametrize(
    ("row", "column", "shown"),
    [
        ("202511\t\t180000", "Density", "202511 → 빈칸"),
        ("202511\t8.0\t", "Wafer Total", "202511 → 빈칸"),
        ("202511\t8.0\t180,000", "Wafer Total", "202511 → '180,000'"),
    ],
)
def test_a_blank_or_comma_formatted_monthly_value_is_refused(
    row: str, column: str, shown: str
) -> None:
    """Density·Wafer Total 이 0 이 되면 그 달 B/N Capa·Wafer Capa 가 0 이 된다.

    천 단위 쉼표는 기준정보 붙여넣기와 같은 까닭으로 받지 않는다 — 쉼표가 천 단위인지
    소수점인지는 지역 설정이 정한다(`test_reference_csv.py` 의
    `test_excel_thousand_separators_are_refused_rather_than_guessed`).
    """
    with pytest.raises(ValueError) as caught:
        past_table_from_clipboard(_MONTH_HEADER + row + "\n", PAST_MONTH_COLUMNS)

    message = str(caught.value)
    assert f"{column} 칸" in message
    assert shown in message
    if "," in row:
        assert "쉼표 없이" in message
    else:
        assert "빈칸은 0 으로 읽지 않습니다" in message


_MISFORMATTED_MONTH_ROWS = {
    "확보율": (PAST_SECUREMENT_COLUMNS, _SECUREMENT_HEADER, "\tP-A\t1.05"),
    "월별": (PAST_MONTH_COLUMNS, _MONTH_HEADER, "\t8.0\t180000"),
    "계획": (PAST_DETAIL_COLUMNS, _DETAIL_HEADER, "\tDEMO-A\t12H\tC1\t100"),
}


@pytest.mark.parametrize("table", sorted(_MISFORMATTED_MONTH_ROWS))
@pytest.mark.parametrize("month", ["2025-11", "2025/11", "2025-11-01", "25.11"])
def test_a_month_written_in_another_format_is_refused_rather_than_dropped(
    table: str, month: str
) -> None:
    """년월로 못 읽는 행이 말없이 떨어지면 저장하는 순간 그 표에서 사라진다.

    이전에는 `2025-11` 은 떨어지고(0행이 되어도 오류 없음) `25.11` 만 YYYYMM 오류로 막혀 규칙이
    일관되지 않았다. 이제 원문이 비어 있지 않은데 년월로 못 읽으면 모두 원문과 함께 막는다.
    """
    columns, header, rest = _MISFORMATTED_MONTH_ROWS[table]
    content = header + "202512" + rest + "\n" + month + rest + "\n"

    with pytest.raises(ValueError, match="YYYYMM") as caught:
        past_table_from_clipboard(content, columns)

    assert f"'{month}'" in str(caught.value)


def test_only_a_row_blank_in_every_cell_is_left_out() -> None:
    """**모든 칸이 빈** 행만 떨군다. 공백만 든 칸도 빈칸이다."""
    content = _SECUREMENT_HEADER + "202511\tP-A\t1.05\n \t \t \n202512\tP-A\t 1.10 \n"

    parsed = past_table_from_clipboard(content, PAST_SECUREMENT_COLUMNS)

    assert parsed["생산계획년월"].tolist() == [202511, 202512]
    # 앞뒤 공백은 지우고 읽는다 — 글자로 막을 까닭이 없다.
    assert parsed["확보율"].tolist() == pytest.approx([1.05, 1.10])


# Excel 에서 년월 셀을 병합한 표(2026-09-29 리뷰). 첫 행에만 년월이 있고 이어진 행은 빈칸이다 —
# 이전에는 이어진 행을 말없이 떨궈 「1행을 읽었습니다」 뒤 저장이 그 행을 표에서 지웠다.
_MERGED_MONTH_ROWS = {
    "확보율": (
        PAST_SECUREMENT_COLUMNS,
        _SECUREMENT_HEADER + "202511\tP-A\t1.05\n\tP-B\t0.90\n\tP-C\t1.20\n",
        ["빈칸 · P-B · 0.90", "빈칸 · P-C · 1.20"],
    ),
    "월별": (
        PAST_MONTH_COLUMNS,
        _MONTH_HEADER + "202511\t8.0\t180000\n\t9.0\t\n",
        ["빈칸 · 9.0 · 빈칸"],
    ),
    "계획": (
        PAST_DETAIL_COLUMNS,
        # 값이 빈칸이어도 분류가 찼으면 막는다 — 계획 세부수량의 빈칸 = 0 규칙과 별개다.
        _DETAIL_HEADER + "202511\tDEMO-A\t12H\tC1\t100\n\tDEMO-A\t12H\tC2\t\n",
        ["빈칸 · DEMO-A · 12H · C2 · 빈칸"],
    ),
}


@pytest.mark.parametrize("table", sorted(_MERGED_MONTH_ROWS))
def test_a_row_with_only_its_month_blank_is_refused_with_the_row_it_came_from(
    table: str,
) -> None:
    columns, content, shown = _MERGED_MONTH_ROWS[table]

    with pytest.raises(ValueError) as caught:
        past_table_from_clipboard(content, columns)

    message = str(caught.value)
    assert f"생산계획년월이 빈 행이 {len(shown)}개" in message
    for example in shown:
        assert example in message
    assert "병합을 풀고 모든 행에 년월을 채워" in message


def test_a_blank_month_row_with_values_cannot_reach_the_store_through_the_repository(
    tmp_path: Path,
) -> None:
    """저장 경로도 같은 규칙이다 — 년월이 빈 행을 떨군 채 표를 통째로 바꾸지 않는다."""
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    stored = repository.replace_global_past_data(_stored_profile_tables(), source="기존")

    with pytest.raises(ValueError, match="생산계획년월이 빈 행"):
        repository.replace_global_past_data(
            {
                **_stored_profile_tables(),
                "확보율": pd.DataFrame(
                    {
                        "생산계획년월": [202511, None],
                        "공정": ["DEMO-P", "DEMO-Q"],
                        "확보율": [1.02, 0.5],
                    }
                ),
            },
            source="병합 셀",
        )

    kept = repository.load_global_past_data()
    assert kept.version == stored.version
    pd.testing.assert_frame_equal(kept.securement, stored.securement)


@pytest.mark.parametrize(
    "content",
    [_SECUREMENT_HEADER, _SECUREMENT_HEADER + " \t \t \n"],
    ids=["header-only", "blank-rows-only"],
)
def test_a_paste_that_reads_no_rows_is_refused(content: str) -> None:
    """0행을 대기로 쌓으면 저장 한 번에 그 표가 통째로 비워진다(되돌릴 수 없음)."""
    with pytest.raises(ValueError, match="읽은 행이 없습니다"):
        past_table_from_clipboard(content, PAST_SECUREMENT_COLUMNS)


def test_a_blank_plan_quantity_reads_as_zero_but_a_comma_is_refused() -> None:
    """계획 세부수량은 빈칸 = 0 을 유지한다 — 거래선을 합쳐 접을 때 합계가 같다.

    못 읽는 글자(`1,200`)만 막는다. 0 이 되면 그 거래선 수량이 말없이 빠진다.
    """
    blank = _DETAIL_HEADER + "202511\tDEMO-A\t12H\tC1\t\n202511\tDEMO-A\t12H\tC2\t800\n"

    parsed = past_table_from_clipboard(blank, PAST_DETAIL_COLUMNS)

    assert parsed["생산수량"].tolist() == pytest.approx([0.0, 800.0])

    comma = _DETAIL_HEADER + "202511\tDEMO-A\t12H\tC1\t1,200\n"
    with pytest.raises(ValueError) as caught:
        past_table_from_clipboard(comma, PAST_DETAIL_COLUMNS)

    message = str(caught.value)
    assert "202511 · DEMO-A · 12H · C1 → '1,200'" in message
    assert "쉼표 없이" in message


_PAST_COMPONENT_SCRIPT = """
from capa_simulation.components.past_data_management import render_past_data_management
from capa_simulation.persistence.cache import load_global_past_data

database_path = r"__DATABASE__"
render_past_data_management(database_path, load_global_past_data(database_path))
"""


@pytest.mark.parametrize(
    ("pasted", "shown"),
    [
        (_SECUREMENT_HEADER + "2025-11\tDEMO-P\t1.05\n2025-12\tDEMO-P\t0.98\n", "'2025-11'"),
        (_SECUREMENT_HEADER + "202511\tDEMO-P\t\n202512\tDEMO-P\t0.98\n", "202511 · DEMO-P"),
        # 년월 셀을 병합한 표 — 이어진 행이 떨어져 저장이 그 공정을 지웠다(2026-09-29 리뷰).
        (
            _SECUREMENT_HEADER + "202511\tDEMO-P\t1.05\n\tDEMO-Q\t0.90\n",
            "빈칸 · DEMO-Q · 0.90",
        ),
        # 년월 열이 모두 빈 표·머리글만 — 0행 대기가 저장을 켜 표를 비웠다.
        (_SECUREMENT_HEADER + "\tDEMO-P\t1.05\n\tDEMO-Q\t0.90\n", "빈 행이 2개"),
        (_SECUREMENT_HEADER, "읽은 행이 없습니다"),
    ],
    ids=["dashed-month", "blank-value", "merged-month", "all-months-blank", "header-only"],
)
def test_a_paste_the_dialog_cannot_read_queues_nothing_so_save_cannot_wipe_the_table(
    tmp_path: Path, pasted: str, shown: str
) -> None:
    """못 읽는 붙여넣기는 팝업에 행 예시와 함께 오류로 남고 대기에 들어가지 않는다.

    이전에는 `2025-11` 행이 모두 떨어져 「0행을 읽었습니다」가 대기로 쌓였고, 그대로 저장하면
    저장된 확보율 표가 통째로 비워졌다(되돌릴 수 없음).
    """
    from streamlit.testing.v1 import AppTest

    from capa_simulation.components.past_data_management import PAST_DRAFT_KEY

    database_path = tmp_path / "past.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    stored = repository.replace_global_past_data(_stored_profile_tables(), source="기존")
    app = AppTest.from_string(
        _PAST_COMPONENT_SCRIPT.replace("__DATABASE__", str(database_path))
    ).run(timeout=60)
    assert not list(app.exception), [element.message for element in app.exception]

    app.button(key="home_past_clipboard_확보율_open").click().run(timeout=60)
    app.text_area(key="home_past_clipboard_확보율").set_value(pasted)
    next(button for button in app.button if button.label == "붙여넣기 읽기").click()
    app.run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    errors = [element.value for element in app.error]
    assert any(shown in message for message in errors), errors
    assert "확보율" not in app.session_state[PAST_DRAFT_KEY]
    save = next(button for button in app.button if button.label == "과거 구간 저장")
    assert save.disabled
    kept = repository.load_global_past_data()
    assert kept.version == stored.version
    pd.testing.assert_frame_equal(kept.securement, stored.securement)


def test_the_display_range_reaches_back_to_the_past_months() -> None:
    """HOME 이 그리는 달(= HOME 캐시 키의 달). 과거 구간이 원천 범위를 넓히고 조회기간이 자른다."""
    widened = display_month_range((202501, 202812), (202607, 202812), [202601, 202602])
    assert (widened.available_start, widened.available_end) == (202601, 202812)
    assert (widened.start, widened.end, widened.empty) == (202601, 202812, False)

    plain = display_month_range((202501, 202812), (202607, 202812), [])
    assert (plain.start, plain.end) == (202607, 202812)

    outside = display_month_range((202501, 202512), (202607, 202812), [])
    assert outside.empty
