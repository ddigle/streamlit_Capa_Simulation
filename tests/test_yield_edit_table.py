# Purpose: 수율 편집표가 값이 잘못된 원천 행을 빼고 적용 때 되붙이는지 고정한다.

"""수율 편집표의 원천 행 보존(2026-09-29 횡전개 감사).

RQ_YLD 한 행의 EDS·BE 가 비었거나 0 이면 `yield_to_edit_table` 이 표 전체를 거부하고 생산 계획
화면이 통째로 섰다. 그런 행은 표에서 빼고(`split_editable_yield_rows`) 적용 때 원본 그대로
되붙인다(`restore_locked_yield_rows`). 빈칸으로 실으면 적용의 `dropna` 가 원천 행을 지우고, 0 을
받아 주면 수율로 나누는 계산이 깨진다.
"""

import math

import pandas as pd
import pytest

from capa_simulation.services.load_calculator import (
    YIELD_KEYS,
    YIELD_LOCK_REASON_COLUMN,
    YIELD_REQUIRED_COLUMNS,
    calculate_wafer_load,
    restore_locked_yield_rows,
    split_editable_yield_rows,
    yield_from_edit_table,
    yield_to_edit_table,
)

MONTHS = (202601, 202602, 202603)


def _source() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "생산계획년월": month,
                "제품정보": product,
                "Stack": "8H",
                "WF 구분": "Core",
                "EDS_수율": 0.9,
                "BE_수율": 0.95,
            }
            for product in ("DEMO_P1", "DEMO_P2")
            for month in MONTHS
        ]
    )


def _row(frame: pd.DataFrame, product: str, month: int) -> pd.DataFrame:
    return frame.loc[frame["제품정보"].eq(product) & frame["생산계획년월"].eq(month)]


def _broken_source() -> pd.DataFrame:
    """DEMO_P1 의 202602 는 BE 가 비고, 202603 은 EDS 가 0, DEMO_P2 의 202603 은 EDS 가 120%."""
    source = _source()
    p1 = source["제품정보"].eq("DEMO_P1")
    p2 = source["제품정보"].eq("DEMO_P2")
    source.loc[p1 & source["생산계획년월"].eq(202602), "BE_수율"] = float("nan")
    source.loc[p1 & source["생산계획년월"].eq(202603), "EDS_수율"] = 0.0
    source.loc[p2 & source["생산계획년월"].eq(202603), "EDS_수율"] = 1.2
    return source


def test_the_edit_table_used_to_reject_a_single_empty_or_zero_yield() -> None:
    """결함 재현: 값 하나 때문에 표 전체가 거부된다(화면이 이 오류로 통째로 섰다)."""
    with pytest.raises(ValueError):
        yield_to_edit_table(_broken_source())


def test_rows_with_missing_or_out_of_range_values_are_split_out_with_a_reason() -> None:
    editable, locked = split_editable_yield_rows(_broken_source())

    assert len(editable) == 3
    yield_to_edit_table(editable)  # 남은 행만으로는 표가 선다.
    reasons = {
        (row["제품정보"], row["생산계획년월"]): row[YIELD_LOCK_REASON_COLUMN]
        for _, row in locked.iterrows()
    }
    assert reasons == {
        ("DEMO_P1", 202602): "BE 값 없음",
        ("DEMO_P1", 202603): "EDS 0 이하",
        ("DEMO_P2", 202603): "EDS 100% 초과",
    }


def test_a_broken_link_key_still_stops_the_table() -> None:
    """연결 키 결측·중복은 값 하나의 문제가 아니라 표 구조의 문제라 가르지 않고 던진다."""
    missing_key = _source()
    missing_key.loc[0, "WF 구분"] = None
    with pytest.raises(ValueError, match="연결 키에 누락값"):
        split_editable_yield_rows(missing_key)

    duplicated = pd.concat([_source(), _source().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="중복"):
        split_editable_yield_rows(duplicated)


def test_an_unrelated_edit_keeps_every_locked_row_as_it_was() -> None:
    """뺀 행과 무관한 칸을 고쳐 적용해도 뺀 행은 원본 값 그대로 남고 행 수도 같다."""
    source = _broken_source()
    editable, locked = split_editable_yield_rows(source)
    grid = yield_to_edit_table(editable)
    grid.loc[grid["제품정보"].eq("DEMO_P2") & grid["수율 구분"].eq("EDS"), "202601"] = 0.5

    applied = restore_locked_yield_rows(yield_from_edit_table(grid), locked)

    assert len(applied) == len(source)
    assert not applied.duplicated(YIELD_KEYS).any()
    assert list(applied.columns) == YIELD_REQUIRED_COLUMNS
    assert math.isnan(_row(applied, "DEMO_P1", 202602)["BE_수율"].item())
    assert _row(applied, "DEMO_P1", 202603)["EDS_수율"].item() == 0.0
    assert _row(applied, "DEMO_P2", 202603)["EDS_수율"].item() == 1.2
    assert _row(applied, "DEMO_P2", 202601)["EDS_수율"].item() == 0.5


def test_filling_both_cells_of_a_locked_month_replaces_the_locked_row() -> None:
    """뺀 달의 빈칸에 EDS·BE 를 모두 넣으면 넣은 값이 이긴다 — 원본을 되붙여 키가 겹치면 안 된다."""
    editable, locked = split_editable_yield_rows(_broken_source())
    grid = yield_to_edit_table(editable)
    p2 = grid["제품정보"].eq("DEMO_P2")
    grid.loc[p2 & grid["수율 구분"].eq("EDS"), "202603"] = 0.8
    grid.loc[p2 & grid["수율 구분"].eq("BE"), "202603"] = 0.9

    applied = restore_locked_yield_rows(yield_from_edit_table(grid), locked)

    fixed = _row(applied, "DEMO_P2", 202603)
    assert len(fixed) == 1
    assert fixed[["EDS_수율", "BE_수율"]].iloc[0].tolist() == [0.8, 0.9]
    assert len(applied) == len(_source())


def test_nothing_to_restore_returns_the_edited_rows() -> None:
    editable, locked = split_editable_yield_rows(_source())
    assert locked.empty
    edited = yield_from_edit_table(yield_to_edit_table(editable))

    assert restore_locked_yield_rows(edited, locked) is edited


def test_a_space_only_yield_cell_reads_as_empty() -> None:
    """공백 한 칸(`' '`)은 빈칸과 같다 — 두 칸 다 비면 그 달 행이 빠진다.

    붙여넣기 검증은 `' '` 를 빈칸으로 통과시키는데 변환은 「숫자가 아닌 값」으로 표 전체를
    거부했고 어느 칸인지도 알리지 않았다(2026-09-29 횡전개 감사).
    """
    grid = yield_to_edit_table(_source()).astype({str(month): object for month in MONTHS})
    grid.loc[grid["제품정보"].eq("DEMO_P1"), "202602"] = " "

    applied = yield_from_edit_table(grid)

    assert len(applied) == len(_source()) - 1
    assert _row(applied, "DEMO_P1", 202602).empty


# --- 2026-09-29 리뷰: 범위 밖 수율이 계산을 멈출 때 어느 행인지 알리고, 고칠 칸이 표에 있다 ---
# 기준정보 오류는 보지 않는 달이어도 계산을 멈춘다(2026-09-28 사용자 결정). 멈추는 것은 그대로
# 두고, 오류문이 행을 가리키고 수율 표가 그 칸을 빈칸으로 실어 이 화면에서 고칠 수 있게 한다.


def _plan() -> pd.DataFrame:
    """두 제품의 세 달 계획. DEMO_P1 은 거래선이 둘이라 계산 프레임에서 수율 행이 겹친다."""
    return pd.DataFrame(
        [
            {
                "생산계획년월": month,
                "양산구분": "양산",
                "제품정보": product,
                "Stack": "8H",
                "Customer": customer,
                "생산수량": 100.0,
            }
            for product, customer in (("DEMO_P1", "C1"), ("DEMO_P1", "C2"), ("DEMO_P2", "C1"))
            for month in MONTHS
        ]
    )


def _chip_qty() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "제품정보": ["DEMO_P1", "DEMO_P2"],
            "Stack": ["8H", "8H"],
            "WF 구분": ["Core", "Core"],
            "구분_Chip": [8.0, 8.0],
            "Net Die": [1_000.0, 1_000.0],
        }
    )


def test_an_out_of_range_yield_stops_the_calculation_naming_the_row_and_the_fix() -> None:
    """예전 문구는 「RQ_YLD의 수율은 0 초과 100% 이하여야 합니다.」뿐이라 HOME·소요대수·확보율이
    멈춰도 어느 제품·달인지 알 수 없었다. 계산 프레임은 거래선마다 같은 수율 행이 겹치므로
    건수는 수율 행으로 센다."""
    source = _source()
    p1 = source["제품정보"].eq("DEMO_P1")
    p2 = source["제품정보"].eq("DEMO_P2")
    source.loc[p1 & source["생산계획년월"].eq(202603), "EDS_수율"] = 0.0
    source.loc[p2 & source["생산계획년월"].eq(202602), "BE_수율"] = 1.2

    with pytest.raises(ValueError) as caught:
        calculate_wafer_load(_plan(), source, _chip_qty())

    message = str(caught.value)
    assert "2행" in message
    assert "202603 · DEMO_P1 · 8H · Core → EDS 0(0%)" in message
    assert "202602 · DEMO_P2 · 8H · Core → BE 1.2(120%)" in message
    assert "생산 계획 → 수율 탭에서 그 달의 EDS·BE 를 둘 다 고쳐 적용하세요" in message
    assert "조회기간" in message


def test_a_missing_yield_is_still_left_out_rather_than_stopping_the_calculation() -> None:
    """값이 **빈** 수율 행은 멈추지 않고 제외 목록으로 내려간다 — 두 경우를 가르는 경계."""
    source = _source()
    p1 = source["제품정보"].eq("DEMO_P1")
    source.loc[p1 & source["생산계획년월"].eq(202603), "BE_수율"] = float("nan")

    load = calculate_wafer_load(_plan(), source, _chip_qty())

    left = load.loc[load["제품정보"].eq("DEMO_P1") & load["생산계획년월"].eq(202603)]
    assert left.empty


def _all_months_locked() -> pd.DataFrame:
    """DEMO_P2 는 모든 달의 EDS 가 0 — 편집표에서 값이 전부 빠진다."""
    source = _source()
    source.loc[source["제품정보"].eq("DEMO_P2"), "EDS_수율"] = 0.0
    return source


def test_a_product_locked_in_every_month_still_gets_blank_rows_in_the_grid() -> None:
    """예전에는 그 제품 행이 표에 없어 이 화면에서 고칠 길이 없었다."""
    editable, locked = split_editable_yield_rows(_all_months_locked())
    assert set(locked["제품정보"]) == {"DEMO_P2"}
    assert "DEMO_P2" not in set(yield_to_edit_table(editable)["제품정보"])  # 결함 재현

    grid = yield_to_edit_table(editable, locked=locked)

    p2 = grid.loc[grid["제품정보"].eq("DEMO_P2")]
    assert sorted(p2["수율 구분"]) == ["BE", "EDS"]
    assert p2[[str(month) for month in MONTHS]].isna().all(axis=None)
    # 빈칸 그대로 적용하면 잠긴 행은 원본 그대로 남는다.
    applied = restore_locked_yield_rows(yield_from_edit_table(grid), locked)
    expected = _all_months_locked()[YIELD_REQUIRED_COLUMNS]
    pd.testing.assert_frame_equal(
        applied.sort_values(YIELD_KEYS).reset_index(drop=True),
        expected.sort_values(YIELD_KEYS).reset_index(drop=True),
        check_dtype=False,
    )


def test_a_month_whose_every_row_is_locked_keeps_its_column() -> None:
    """한 달의 모든 행이 잠기면 그 달 열이 표에서 사라져 고칠 칸이 없었다."""
    source = _source()
    source.loc[source["생산계획년월"].eq(202603), "BE_수율"] = 1.5
    editable, locked = split_editable_yield_rows(source)
    assert "202603" not in yield_to_edit_table(editable).columns  # 결함 재현

    grid = yield_to_edit_table(editable, locked=locked)

    assert "202603" in grid.columns
    assert grid["202603"].isna().all()


def test_filling_every_locked_month_fixes_the_product_so_the_calculation_runs() -> None:
    """모든 달이 잠긴 제품의 빈칸에 EDS·BE 를 채워 적용하면 채운 값이 이기고 환산이 돈다."""
    editable, locked = split_editable_yield_rows(_all_months_locked())
    grid = yield_to_edit_table(editable, locked=locked)
    p2 = grid["제품정보"].eq("DEMO_P2")
    for month in MONTHS:
        grid.loc[p2 & grid["수율 구분"].eq("EDS"), str(month)] = 0.8
        grid.loc[p2 & grid["수율 구분"].eq("BE"), str(month)] = 0.9

    applied = restore_locked_yield_rows(yield_from_edit_table(grid), locked)

    assert len(applied) == len(_source())
    fixed = applied.loc[applied["제품정보"].eq("DEMO_P2"), ["EDS_수율", "BE_수율"]]
    assert fixed.to_numpy().tolist() == [[0.8, 0.9]] * len(MONTHS)
    load = calculate_wafer_load(_plan(), applied, _chip_qty())
    assert set(load["제품정보"]) == {"DEMO_P1", "DEMO_P2"}
