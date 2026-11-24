# Purpose: CUSTOM 원천 표 붙이기의 멈춤 · 대조 계약(못 찾음 · 둘 이상 · 빈 값 · 행 수)을 고정한다.

"""CUSTOM 원천 표 붙이기 — `services/custom_source_check.py`.

본 표의 CUSTOM 칸은 CUSTOM 원천 표의 값으로 Capa Code 마다 덮인다. 그대로 등록하면 부품이 다른
부품과 「구분 없음」 으로 합쳐지거나 달마다 다른 제품으로 갈리는 경우(못 찾음 · 둘 이상 · 빈 값)는
멈추고, 두 표의 (Capa Code, 생산계획년월) 칸 행 수가 어긋나는 것은 알리고 붙인다. 값은 모두 합성
`DEMO_*` 이고 빈 값 표지는 상수(`CUSTOM_BLANK`)로만 본다.
"""

from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.services.core_data_derivation import CUSTOM_BLANK
from capa_simulation.services.custom_source_check import (
    CELL_COLUMNS,
    CUSTOM_EXAMPLE_LIMIT,
    CUSTOM_ROWS_COLUMN,
    CUSTOM_SOURCE_COLUMNS,
    MAIN_ROWS_COLUMN,
    attach_custom_values,
    check_custom_rows,
)

PART_A = "DEMO_CAPA_A"
PART_B = "DEMO_CAPA_B"
CUSTOM_A = "DEMO_CUSTOM_A"
CUSTOM_B = "DEMO_CUSTOM_B"
# 본 조회문이 싣는 상수 자리 — 붙이기가 덮어야 하는 값이다.
QUERY_CONSTANT = "DEMO_CONSTANT"


def _main(rows: list[tuple[object, object, str]]) -> pd.DataFrame:
    """본 표 — (Capa Code, 생산계획년월, 계획기초정보여부) 행마다 상수 CUSTOM 과 같은 값 칸
    하나(같은 행이 두 번 오면 완전 중복이다)."""
    return pd.DataFrame(
        {
            "Capa Code": [row[0] for row in rows],
            "생산계획년월": [row[1] for row in rows],
            "CUSTOM": [QUERY_CONSTANT] * len(rows),
            "계획기초정보여부": [row[2] for row in rows],
            "생산수량": [1.0] * len(rows),
        }
    )


def _custom(rows: list[tuple[object, object, object, int]]) -> pd.DataFrame:
    """CUSTOM 원천 표 조회 결과 — (Capa Code, 생산계획년월, CUSTOM, 행수)."""
    return pd.DataFrame(rows, columns=list(CUSTOM_SOURCE_COLUMNS))


def test_custom_is_attached_by_capa_code_and_rows_are_not_multiplied() -> None:
    """CUSTOM 원천 표가 부품마다 여러 달 줄이어도 본 표 행 수 · 차례 · index · 다른 칸이 그대로다.

    CUSTOM 칸만 그 부품의 값으로 바뀐다(merge 로 붙이면 달 수만큼 행이 불어난다). 본 표 index 가
    겹쳐도 차례로 맞댄다.
    """
    main = _main(
        [
            (PART_A, 202611, "Y"),
            (PART_B, 202611, "Y"),
            (PART_A, 202612, "N"),
            (PART_B, 202612, "N"),
        ]
    )
    main.index = pd.Index([7, 7, 3, 3])
    custom = _custom(
        [
            (PART_A, 202611, CUSTOM_A, 1),
            (PART_A, 202612, CUSTOM_A, 1),
            (PART_B, 202611, CUSTOM_B, 1),
            (PART_B, 202612, CUSTOM_B, 1),
        ]
    )

    attached, check = attach_custom_values(main, custom)

    assert attached.index.tolist() == [7, 7, 3, 3]
    assert attached.columns.tolist() == main.columns.tolist()
    assert attached["CUSTOM"].tolist() == [CUSTOM_A, CUSTOM_B, CUSTOM_A, CUSTOM_B]
    assert attached["CUSTOM"].dtype == main["CUSTOM"].dtype
    pd.testing.assert_frame_equal(attached.drop(columns="CUSTOM"), main.drop(columns="CUSTOM"))
    assert main["CUSTOM"].eq(QUERY_CONSTANT).all()
    assert (check.main_rows, check.custom_rows, check.kinds) == (4, 4, 2)
    assert not check.warns


def test_one_capa_code_with_two_custom_values_stops_with_examples() -> None:
    """한 부품의 CUSTOM 이 달마다 다르면 멈추고 어느 부품 · 어느 값 · 어느 달인지 싣는다.

    부품이 `CUSTOM_EXAMPLE_LIMIT` 보다 많으면 그만큼만 싣고 나머지는 「외 n종」 이다. 본 조회
    앞(`check_custom_rows`)과 붙이기(`attach_custom_values`)가 같은 글로 멈춘다.
    """
    custom = _custom(
        [
            (PART_A, 202611, CUSTOM_A, 1),
            (PART_A, 202612, CUSTOM_B, 1),
            (PART_B, 202611, CUSTOM_B, 1),
        ]
    )

    with pytest.raises(ValueError, match="CUSTOM 이 둘 이상") as stopped:
        check_custom_rows(custom)

    message = str(stopped.value)
    assert f"`{PART_A}`(`{CUSTOM_A}` 202611 / `{CUSTOM_B}` 202612)" in message
    assert PART_B not in message
    with pytest.raises(ValueError, match="CUSTOM 이 둘 이상"):
        attach_custom_values(_main([(PART_A, 202611, "Y")]), custom)

    many = _custom(
        [
            (f"DEMO_CAPA_{index:02d}", month, value, 1)
            for index in range(CUSTOM_EXAMPLE_LIMIT + 2)
            for month, value in ((202611, CUSTOM_A), (202612, CUSTOM_B))
        ]
    )
    with pytest.raises(ValueError) as crowded:
        check_custom_rows(many)

    text = str(crowded.value)
    assert text.count("`DEMO_CAPA_") == CUSTOM_EXAMPLE_LIMIT
    assert "외 2종" in text


def test_case_and_space_only_differences_are_one_value() -> None:
    """앞뒤 공백 · 대소문자만 다른 CUSTOM 은 한 값이다 — 멈추지 않고 한 표기로 붙는다."""
    custom = _custom(
        [
            (PART_A, 202611, CUSTOM_A, 2),
            (PART_A, 202612, f"  {CUSTOM_A.lower()} ", 1),
            (PART_B, 202611, CUSTOM_A, 1),
        ]
    )

    checked = check_custom_rows(custom)
    attached, check = attach_custom_values(
        _main([(PART_A, 202611, "Y"), (PART_A, 202612, "N"), (PART_B, 202611, "Y")]), custom
    )

    assert checked["CUSTOM"].tolist() == [CUSTOM_A] * 3
    assert attached["CUSTOM"].tolist() == [CUSTOM_A] * 3
    assert check.kinds == 1
    pd.testing.assert_frame_equal(check_custom_rows(checked), checked)


def test_a_capa_code_missing_from_the_custom_table_stops() -> None:
    """본 표의 Capa Code 가 CUSTOM 원천 표에 없으면 멈추고 부품 · 행 · 계획 행 · 달을 싣는다.

    행이 많은 부품이 앞이고, 달은 `_MONTH_EXAMPLE_LIMIT` 개까지 싣고 나머지는 「외 n개월」 이다.
    그대로 등록하면 구분 없음으로 합쳐진다는 까닭도 싣는다.
    """
    missing_one = "DEMO_CAPA_GONE_1"
    missing_two = "DEMO_CAPA_GONE_2"
    main = _main(
        [
            (PART_A, 202611, "Y"),
            (missing_one, 202611, "Y"),
            (missing_two, 202611, "Y"),
            (missing_two, 202612, "N"),
            (missing_two, 202701, "N"),
            (missing_two, 202702, "N"),
        ]
    )
    custom = _custom([(PART_A, 202611, CUSTOM_A, 1)])

    with pytest.raises(ValueError, match="CUSTOM 원천 표에 없는 Capa Code") as stopped:
        attach_custom_values(main, custom)

    message = str(stopped.value)
    assert f"`{missing_two}` 4행(계획 1행) 202611 · 202612 · 202701 외 1개월" in message
    assert f"`{missing_one}` 1행(계획 1행) 202611" in message
    assert message.index(missing_two) < message.index(missing_one)
    assert f"`{PART_A}`" not in message
    assert f"구분 없음({CUSTOM_BLANK})" in message

    crowded = _main([(f"DEMO_CAPA_{index:02d}", 202611, "N") for index in range(12)])
    with pytest.raises(ValueError) as many:
        attach_custom_values(crowded, custom)
    assert "외 2종" in str(many.value)


@pytest.mark.parametrize("blank", [None, "", "   ", CUSTOM_BLANK])
def test_a_blank_custom_for_a_listed_capa_code_stops(blank: object) -> None:
    """줄은 있는데 CUSTOM 이 빈 부품은 멈춘다 — 빈 값 표지 글자 그대로인 값도 같다.

    「-」(구분 없음)로 받으면 같은 제품의 다른 빈 부품과 합쳐지기 때문이다(Q2 (가) 와 같은 뜻).
    """
    custom = _custom(
        [
            (PART_A, 202611, CUSTOM_A, 1),
            (PART_B, 202611, blank, 1),
            (PART_B, 202612, blank, 1),
        ]
    )

    with pytest.raises(ValueError, match="CUSTOM 이 빈 Capa Code") as stopped:
        check_custom_rows(custom)

    message = str(stopped.value)
    assert f"`{PART_B}` 202611 · 202612" in message
    assert f"`{PART_A}`" not in message
    assert f"구분 없음({CUSTOM_BLANK})" in message


def test_one_side_cells_and_row_count_differences_warn_but_attach() -> None:
    """한쪽에만 있는 칸 · 행 수가 다른 칸은 멈추지 않는다 — 붙이고 그 칸을 표로 남긴다.

    본 표 수는 받은 행 그대로다(완전 중복 행도 센다). 없는 쪽은 0행이다.
    """
    main = _main(
        [
            (PART_A, 202611, "Y"),
            (PART_A, 202611, "Y"),
            (PART_A, 202612, "N"),
            (PART_B, 202611, "Y"),
        ]
    )
    custom = _custom(
        [
            (PART_A, 202611, CUSTOM_A, 1),
            (PART_B, 202611, CUSTOM_B, 1),
            (PART_B, 202612, CUSTOM_B, 3),
        ]
    )

    attached, check = attach_custom_values(main, custom)

    assert attached["CUSTOM"].tolist() == [CUSTOM_A, CUSTOM_A, CUSTOM_A, CUSTOM_B]
    assert check.warns
    assert (check.main_rows, check.main_distinct_rows, check.custom_rows) == (4, 3, 5)
    assert (check.count_mismatch_cells, check.one_side_cells) == (1, 2)
    assert check.cells.columns.tolist() == list(CELL_COLUMNS)
    assert check.cells.to_dict("records") == [
        {"Capa Code": PART_A, "생산계획년월": "202611", MAIN_ROWS_COLUMN: 2, CUSTOM_ROWS_COLUMN: 1},
        {"Capa Code": PART_A, "생산계획년월": "202612", MAIN_ROWS_COLUMN: 1, CUSTOM_ROWS_COLUMN: 0},
        {"Capa Code": PART_B, "생산계획년월": "202612", MAIN_ROWS_COLUMN: 0, CUSTOM_ROWS_COLUMN: 3},
    ]


def test_blank_capa_code_rows_keep_the_blank_marker_and_are_not_counted_missing() -> None:
    """Capa Code 가 빈 본 표 행은 짝짓지 않는다 — CUSTOM 은 빈 값 표지이고 못 찾음 · 칸 대조 ·
    종류에서 빠진다. CUSTOM 원천 표의 빈 Capa Code 줄도 짝짓지 않는다(빈 CUSTOM 이어도 멈추지
    않는다)."""
    main = _main([(PART_A, 202611, "Y"), (None, 202611, "Y"), ("  ", 202612, "N")])
    custom = _custom([(PART_A, 202611, CUSTOM_A, 1), (None, 202611, None, 2)])

    attached, check = attach_custom_values(main, custom)

    assert attached["CUSTOM"].tolist() == [CUSTOM_A, CUSTOM_BLANK, CUSTOM_BLANK]
    assert check.kinds == 1
    assert not check.warns
    assert check.cells.empty
    assert check.custom_rows == 3


def test_months_match_as_text_whether_numbers_or_strings() -> None:
    """생산계획년월은 정수 · 실수 · 앞뒤 공백 글자 어느 꼴이어도 같은 6자리 글자로 맞댄다."""
    main = _main([(PART_A, 202611, "Y"), (PART_A, " 202612 ", "N"), (PART_A, 202701.0, "N")])
    custom = _custom(
        [
            (PART_A, "202611", CUSTOM_A, 1),
            (PART_A, 202612.0, CUSTOM_A, 1),
            (PART_A, 202701, CUSTOM_A, 1),
        ]
    )

    _, check = attach_custom_values(main, custom)
    checked = check_custom_rows(custom)

    assert checked["생산계획년월"].tolist() == ["202611", "202612", "202701"]
    assert not check.warns
    assert check.cells.empty

    nullable = main.assign(생산계획년월=pd.array([202611, 202612, 202701], dtype="Int64"))
    _, again = attach_custom_values(nullable, custom)
    assert not again.warns


def test_memo_always_names_kinds_and_notice_only_on_mismatch() -> None:
    """메모는 늘 「종류 · 행 수 다른 칸 · 한쪽에만 있는 칸」 을 싣고, 알림은 어긋난 칸이 있을
    때만이다."""
    custom = _custom([(PART_A, 202611, CUSTOM_A, 1), (PART_B, 202611, CUSTOM_B, 1)])
    matched = _main([(PART_A, 202611, "Y"), (PART_B, 202611, "Y")])

    _, clean = attach_custom_values(matched, custom)
    _, uneven = attach_custom_values(matched.iloc[[0, 0, 1]], custom)

    assert clean.memo() == "CUSTOM 원천 대조 — 종류 2 · 행 수 다른 칸 0 · 한쪽에만 있는 칸 0"
    assert clean.notice() == ""
    assert uneven.memo() == "CUSTOM 원천 대조 — 종류 2 · 행 수 다른 칸 1 · 한쪽에만 있는 칸 0"
    assert "행 수 다른 칸 1 · 한쪽에만 있는 칸 0" in uneven.notice()
    assert "등록했습니다" in uneven.notice()


def test_missing_columns_in_the_custom_answer_stop_with_column_names() -> None:
    """칸이 모자란 답은 모자란 칸 이름을 싣고 멈춘다. 0행 답 · 행수가 숫자가 아닌 답도 멈춘다."""
    answer = _custom([(PART_A, 202611, CUSTOM_A, 1)]).drop(columns=["CUSTOM", "행수"])

    with pytest.raises(ValueError, match="필요한 칸이 없습니다: CUSTOM, 행수"):
        check_custom_rows(answer)
    with pytest.raises(ValueError, match="필요한 칸이 없습니다: CUSTOM, 행수"):
        attach_custom_values(_main([(PART_A, 202611, "Y")]), answer)
    with pytest.raises(ValueError, match="0행"):
        check_custom_rows(pd.DataFrame())
    with pytest.raises(ValueError, match="0행"):
        check_custom_rows(_custom([]))
    with pytest.raises(ValueError, match="행수 칸에 숫자가 아닌 값"):
        check_custom_rows(_custom([(PART_A, 202611, CUSTOM_A, 1)]).assign(행수=["많음"]))
