# Purpose: CUSTOM 원천 표 붙이기의 멈춤 · 대조 계약(못 찾음 · 둘 이상 · 빈 값 · 행 수)을 고정한다.

"""CUSTOM 원천 표 붙이기 — `services/custom_source_check.py`.

본 표의 CUSTOM 칸은 CUSTOM 원천 표의 값으로 Capa Code 마다 덮인다. 그대로 등록하면 부품이 다른
부품과 「구분 없음」 으로 합쳐지거나 달마다 다른 제품으로 갈리는 경우(못 찾음 · 둘 이상 · 빈 값)는
멈추고, 두 표의 (Capa Code, 생산계획년월) 칸 행 수가 어긋나는 것은 알리고 붙인다. 값은 모두 합성
`DEMO_*` 이고 빈 값 표지는 상수(`CUSTOM_BLANK`)로만 본다.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pytest

from capa_simulation import alerts
from capa_simulation.services.core_data_derivation import CUSTOM_BLANK
from capa_simulation.services.custom_source_check import (
    CELL_COLUMNS,
    CUSTOM_EXAMPLE_LIMIT,
    CUSTOM_ROWS_COLUMN,
    CUSTOM_SOURCE_COLUMNS,
    FILE_WORDS,
    MAIN_ROWS_COLUMN,
    SWITCHED_OFF_NOTICE,
    TABLE_WORDS,
    CustomSourceCheck,
    CustomSourceWords,
    attach_custom_values,
    blank_custom_values,
    check_custom_rows,
    custom_rows_of,
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


@pytest.mark.parametrize(
    ("mismatch", "one_side"), [(1, 0), (2, 1), (9_999, 9_999)], ids=["하나", "둘 셋", "네 자리"]
)
def test_the_notice_short_text_leads_with_the_cell_counts(mismatch: int, one_side: int) -> None:
    """알림창 짧은 글(60자에서 자름)만 읽어도 어긋난 칸 수와 두 갈래 수가 보인다(설계 규칙
    UI-NTF-06 — 무엇을 · 건수). 칸마다 네 자리 수까지다."""
    check = CustomSourceCheck(
        main_rows=1,
        main_distinct_rows=1,
        custom_rows=1,
        kinds=1,
        one_side_cells=one_side,
        count_mismatch_cells=mismatch,
        cells=pd.DataFrame(columns=list(CELL_COLUMNS)),
    )

    short = alerts.short_text(check.notice())

    assert short.startswith(
        f"CUSTOM 원천 대조 어긋난 칸 {mismatch + one_side:,}개(행 수 다른 칸 {mismatch:,} · "
        f"한쪽에만 있는 칸 {one_side:,}"
    )


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


def test_a_switched_off_check_says_so_in_memo_and_notice_and_has_no_cells() -> None:
    """끄개로 CUSTOM 원천 표를 묻지 않은 등록(`blank_custom_values`)은 본 표 CUSTOM 칸을 모두 빈 값
    표지로 덮고(조회문 상수 그대로가 아니다) 행 수 · 차례 · index · 다른 칸을 그대로 둔다. 대조는
    「붙이지 않음」 — 대조 칸이 없고 종류는 구분 없음 하나이며, 알릴 것이 늘 있어 메모 · 알림이 그
    사실을 말한다(메모에는 끄개 이름을 싣지 않는다). 맞댈 칸(Capa Code · 생산계획년월)이 없는 본
    표도 멈추지 않고, 글자 dtype CUSTOM 칸은 그 dtype 을 지킨다."""
    main = _main([(PART_A, 202611, "Y"), (PART_B, 202612, "N"), (PART_B, 202612, "N")])
    main.index = pd.Index([7, 3, 3])

    blanked, check = blank_custom_values(main)

    assert blanked["CUSTOM"].tolist() == [CUSTOM_BLANK] * 3
    pd.testing.assert_frame_equal(blanked.drop(columns="CUSTOM"), main.drop(columns="CUSTOM"))
    assert main["CUSTOM"].eq(QUERY_CONSTANT).all()
    assert not check.attached and check.warns
    assert (check.main_rows, check.main_distinct_rows, check.custom_rows, check.kinds) == (
        3,
        2,
        0,
        1,
    )
    assert (check.one_side_cells, check.count_mismatch_cells) == (0, 0)
    assert check.cells.empty and list(check.cells.columns) == list(CELL_COLUMNS)
    assert check.memo() == f"CUSTOM 원천 붙이지 않음 — 부품 구분 없음({CUSTOM_BLANK})"
    assert "CAPA_" not in check.memo()
    assert check.notice() == SWITCHED_OFF_NOTICE
    assert alerts.short_text(check.notice()).startswith(
        "CUSTOM 원천 끄개로 부품 구분 없이 등록했습니다"
    )
    assert check == CustomSourceCheck.switched_off(blanked)
    typed = main.astype({"CUSTOM": "string"})
    assert blank_custom_values(typed)[0]["CUSTOM"].dtype == typed["CUSTOM"].dtype
    bare = main.drop(columns=["Capa Code", "생산계획년월", "CUSTOM"])
    assert blank_custom_values(bare)[0]["CUSTOM"].tolist() == [CUSTOM_BLANK] * 3
    custom = _custom([(PART_A, 202611, CUSTOM_A, 1), (PART_B, 202612, CUSTOM_B, 2)])
    assert attach_custom_values(main, custom)[1].attached


def _file(rows: list[tuple[object, object, object]]) -> pd.DataFrame:
    """원천 CSV 에서 읽은 본 표 — (Capa Code, 생산계획년월, CUSTOM) 행마다 CUSTOM 이 파일 값이다.
    글자 칸은 글자 dtype 이고 빈 칸은 NA, 생산계획년월은 pandas 가 고른 수 dtype(빈 칸이 있으면
    실수)이다 — `io/source_csv.read_source_csv_rows` 가 내는 꼴."""
    return pd.DataFrame(
        {
            "Capa Code": pd.array([row[0] for row in rows], dtype="string"),
            "생산계획년월": [row[1] for row in rows],
            "CUSTOM": pd.array([row[2] for row in rows], dtype="string"),
            "계획기초정보여부": pd.array(["Y"] * len(rows), dtype="string"),
            "생산수량": [1.0] * len(rows),
        }
    )


def _stop_text(call: Callable[[], object]) -> str:
    with pytest.raises(ValueError) as stopped:
        call()
    return str(stopped.value)


def _attach_from_file(frame: pd.DataFrame) -> tuple[pd.DataFrame, CustomSourceCheck]:
    """원천 CSV 길 — 파일 행에서 센 답을 같은 붙이기에 파일 낱말로 넣는다."""
    return attach_custom_values(frame, custom_rows_of(frame), words=FILE_WORDS)


@pytest.mark.parametrize("words", [{}, {"words": TABLE_WORDS}], ids=["낱말 없음", "TABLE_WORDS"])
def test_table_words_are_the_default_and_keep_the_stop_texts(
    words: dict[str, CustomSourceWords],
) -> None:
    """낱말을 주지 않은 둘째 표 길(어댑터 · 자동 갱신)의 멈춤 글 셋은 원천 낱말이 생기기 전 글과
    한 글자도 다르지 않고, `TABLE_WORDS` 를 준 것과 같다."""
    several = _custom([(PART_A, 202611, CUSTOM_A, 1), (PART_A, 202612, CUSTOM_B, 1)])
    blank = _custom([(PART_A, 202611, CUSTOM_A, 1), (PART_B, 202611, None, 1)])
    gone = "DEMO_CAPA_GONE"
    missing_main = _main([(PART_A, 202611, "Y"), (gone, 202611, "Y")])
    missing_custom = _custom([(PART_A, 202611, CUSTOM_A, 1)])
    merged = f"그대로 등록하면 그 부품은 구분 없음({CUSTOM_BLANK})으로 합쳐집니다."
    expected = {
        "several": (
            "CUSTOM 원천 표에서 한 Capa Code 에 CUSTOM 이 둘 이상이라 등록하지 않았습니다: "
            f"`{PART_A}`(`{CUSTOM_A}` 202611 / `{CUSTOM_B}` 202612). 한 부품(Capa Code)의 "
            "CUSTOM 은 달마다 같아야 합니다 — CUSTOM 원천 표를 바로잡은 뒤 다시 등록하세요."
        ),
        "blank": (
            "CUSTOM 원천 표에 CUSTOM 이 빈 Capa Code 가 있어 등록하지 않았습니다: "
            f"`{PART_B}` 202611 — {merged}"
        ),
        "missing": (
            "CUSTOM 원천 표에 없는 Capa Code 가 있어 등록하지 않았습니다: "
            f"`{gone}` 1행(계획 1행) 202611 — {merged} CUSTOM 원천 표에 그 부품이 적재됐는지 "
            "확인한 뒤 다시 등록하세요."
        ),
    }
    main = _main([(PART_A, 202611, "Y")])

    assert _stop_text(lambda: check_custom_rows(several, **words)) == expected["several"]
    assert _stop_text(lambda: attach_custom_values(main, several, **words)) == expected["several"]
    assert _stop_text(lambda: check_custom_rows(blank, **words)) == expected["blank"]
    missing = _stop_text(lambda: attach_custom_values(missing_main, missing_custom, **words))
    assert missing == expected["missing"]


def test_file_words_name_the_csv_file_in_the_several_values_stop() -> None:
    """원천 CSV 길에서 한 부품의 CUSTOM 이 달마다 다르면 같은 규칙으로 멈추고, 글은 「CSV 파일」 을
    자리로 원천에서 다시 받으라고 말한다(둘째 표 낱말은 싣지 않는다). 답을 같은 표에서 세어 닿지
    않는 못 찾음도 닿으면 같은 낱말이다."""
    frame = _file(
        [
            (PART_A, 202611, CUSTOM_A),
            (PART_A, 202612, CUSTOM_B),
            (PART_B, 202611, CUSTOM_B),
        ]
    )

    message = _stop_text(lambda: _attach_from_file(frame))

    assert message == (
        "CSV 파일에서 한 Capa Code 에 CUSTOM 이 둘 이상이라 등록하지 않았습니다: "
        f"`{PART_A}`(`{CUSTOM_A}` 202611 / `{CUSTOM_B}` 202612). 한 부품(Capa Code)의 CUSTOM 은 "
        "달마다 같아야 합니다 — 원천에서 바로잡아 CSV 를 다시 받은 뒤 올리세요."
    )
    assert "CUSTOM 원천 표" not in message
    unlisted = _file([(PART_A, 202611, CUSTOM_A), (PART_B, 202611, CUSTOM_B)])
    answer = custom_rows_of(unlisted.iloc[:1])
    missing = _stop_text(lambda: attach_custom_values(unlisted, answer, words=FILE_WORDS))
    assert missing.startswith("CSV 파일에 없는 Capa Code 가 있어 등록하지 않았습니다: ")
    assert missing.endswith(f" {FILE_WORDS.missing_fix}")
    assert "CUSTOM 원천 표" not in missing


def test_custom_rows_of_keeps_blank_custom_and_blank_month_rows() -> None:
    """파일 행에서 센 답은 (Capa Code, 생산계획년월, CUSTOM) 마다 한 줄이고 빈 CUSTOM 줄 · 빈 달
    줄을 버리지 않는다 — 빈 CUSTOM(NA · 빈 글자)은 빈 글자 한 줄로 모이고, 행수 합이 파일 행 수다.
    값이 다 찬 파일이면 붙인 뒤 두 표 칸이 늘 맞는다(어긋난 칸 0)."""
    frame = _file(
        [
            (PART_A, 202611, CUSTOM_A),
            (PART_A, 202611, CUSTOM_A),
            (PART_A, None, CUSTOM_A),
            (PART_B, 202611, None),
            (PART_B, 202611, ""),
            (None, 202612, None),
        ]
    )

    answer = custom_rows_of(frame)

    assert answer.columns.tolist() == list(CUSTOM_SOURCE_COLUMNS)
    assert int(answer["행수"].sum()) == len(frame)
    months = ["(빈 달)" if pd.isna(month) else f"{int(month)}" for month in answer["생산계획년월"]]
    assert list(
        zip(answer["Capa Code"], months, answer["CUSTOM"], answer["행수"], strict=True)
    ) == [
        (PART_A, "202611", CUSTOM_A, 2),
        (PART_A, "(빈 달)", CUSTOM_A, 1),
        (PART_B, "202611", "", 2),
        ("", "202612", "", 1),
    ]

    filled = frame.iloc[:3]
    attached, check = _attach_from_file(filled)

    assert attached["CUSTOM"].tolist() == [CUSTOM_A] * 3
    assert check.custom_rows == check.main_rows == 3
    assert (check.one_side_cells, check.count_mismatch_cells) == (0, 0)
    assert not check.warns and check.cells.empty


def test_a_part_with_filled_and_blank_custom_rows_stops_with_file_words() -> None:
    """한 부품에 CUSTOM 이 든 줄과 빈 줄(NA · 공백뿐)이 섞이면 빈 줄을 그 값으로 채우지 않고 멈춘다
    — 둘째 표의 빈 CUSTOM 과 같은 규칙이고 자리는 「CSV 파일」 이다."""
    frame = _file(
        [
            (PART_A, 202611, CUSTOM_A),
            (PART_A, 202612, None),
            (PART_A, 202701, "  "),
            (PART_B, 202611, CUSTOM_B),
        ]
    )

    message = _stop_text(lambda: _attach_from_file(frame))

    assert message == (
        "CSV 파일에 CUSTOM 이 빈 Capa Code 가 있어 등록하지 않았습니다: "
        f"`{PART_A}` 202612 · 202701 — 그대로 등록하면 그 부품은 구분 없음({CUSTOM_BLANK})으로 "
        "합쳐집니다."
    )


def test_a_part_with_only_blank_custom_rows_stops_as_blank_not_missing() -> None:
    """빈 CUSTOM 줄만 있는 부품도 같은 빈 값 글로 멈춘다 — 답에서 그 부품이 빠져 「없는 Capa
    Code … 적재됐는지 확인」 이라는 틀린 글로 멈추지 않는다."""
    frame = _file(
        [
            (PART_A, 202611, CUSTOM_A),
            (PART_B, 202611, None),
            (PART_B, 202612, None),
        ]
    )

    message = _stop_text(lambda: _attach_from_file(frame))

    assert message.startswith("CSV 파일에 CUSTOM 이 빈 Capa Code 가 있어 등록하지 않았습니다: ")
    assert f"`{PART_B}` 202611 · 202612" in message
    assert f"`{PART_A}`" not in message
    assert "없는 Capa Code" not in message
    assert "적재됐는지" not in message


def test_rows_without_capa_code_get_the_blank_marker_from_file_counts() -> None:
    """Capa Code 가 빈 파일 행은 짝짓지 않는다 — 파일 CUSTOM 이 무엇이든 빈 값 표지이고 멈춤 ·
    칸 대조 · 종류에서 빠진다(둘째 표 길의 빈 Capa Code 행과 같다). 답의 행수는 그 행도 센다."""
    frame = _file(
        [
            (PART_A, 202611, CUSTOM_A),
            (None, 202611, None),
            ("  ", 202612, "DEMO_CUSTOM_STRAY"),
            (PART_A, 202612, CUSTOM_A),
        ]
    )

    attached, check = _attach_from_file(frame)

    assert attached["CUSTOM"].tolist() == [CUSTOM_A, CUSTOM_BLANK, CUSTOM_BLANK, CUSTOM_A]
    assert check.kinds == 1
    assert check.custom_rows == 4
    assert not check.warns
    assert check.cells.empty


def test_case_variants_in_the_file_become_one_spelling() -> None:
    """파일 안에서 앞뒤 공백 · 대소문자만 다른 CUSTOM 은 한 값이다 — 멈추지 않고 둘째 표 길과 같은
    한 표기(답 줄에서 가장 많이 쓰인 것)로 붙고, 글자 dtype 칸은 그 dtype 을 지킨다."""
    frame = _file(
        [
            (PART_A, 202611, CUSTOM_A),
            (PART_A, 202612, f"  {CUSTOM_A.lower()} "),
            (PART_B, 202611, CUSTOM_A),
            (PART_B, 202612, CUSTOM_A),
        ]
    )

    attached, check = _attach_from_file(frame)

    assert custom_rows_of(frame)["CUSTOM"].nunique() == 2
    assert attached["CUSTOM"].tolist() == [CUSTOM_A] * 4
    assert attached["CUSTOM"].dtype == frame["CUSTOM"].dtype
    assert check.kinds == 1
    assert not check.warns
