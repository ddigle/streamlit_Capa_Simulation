# Purpose: 원천 78컬럼 품질 표의 등급 판정과 정렬을 검증한다.

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from capa_simulation.components.source_quality import (
    DISTINCT_COLUMN,
    GRADE_COLUMN,
    MISSING_RATE_COLUMN,
    TABLE_FULL_ROWS,
    TABLE_MAX_HEIGHT_PX,
    build_source_quality_table,
    render_source_quality,
    source_quality_warning,
)


def _profile(rows: list[tuple[str, int, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ordinal_position": index,
                "column_name": name,
                "source_dtype": "object",
                "nullable_dtype": "string",
                "null_count": nulls,
                "unique_count": uniques,
            }
            for index, (name, nulls, uniques) in enumerate(rows, start=1)
        ]
    )


def test_grades_split_empty_sparse_constant_and_normal() -> None:
    table = build_source_quality_table(
        _profile([("정상", 0, 40), ("상수", 0, 1), ("절반결측", 60, 12), ("빈컬럼", 100, 0)]),
        source_rows=100,
    )

    grades = dict(zip(table["컬럼"], table[GRADE_COLUMN], strict=True))
    assert grades == {
        "정상": "정상",
        "상수": "상수",
        "절반결측": "절반 이상 결측",
        "빈컬럼": "비어 있음",
    }


def test_worst_columns_come_first() -> None:
    """새 데이터셋을 받았을 때 스크롤 없이 문제부터 보여야 한다."""
    table = build_source_quality_table(
        _profile([("정상", 0, 40), ("빈컬럼", 100, 0), ("절반결측", 60, 12)]),
        source_rows=100,
    )

    assert list(table["컬럼"]) == ["빈컬럼", "절반결측", "정상"]


def test_zero_row_source_leaves_the_missing_rate_empty() -> None:
    """행이 없으면 나눌 수 없다. 0 으로 두면 `전부 채워졌다` 로 읽힌다."""
    table = build_source_quality_table(_profile([("컬럼A", 0, 0)]), source_rows=0)

    assert table[MISSING_RATE_COLUMN].isna().all()
    assert int(table[DISTINCT_COLUMN].iloc[0]) == 0


def test_empty_profile_returns_the_display_columns() -> None:
    table = build_source_quality_table(pd.DataFrame(), source_rows=10)

    assert table.empty
    assert MISSING_RATE_COLUMN in table.columns


def test_the_warning_counts_each_problem_grade_on_its_own() -> None:
    """수와 문구가 맞아야 한다 — 「절반 이상 결측」 을 「비어 있거나 상수」 수에 넣지 않는다
    (E2E r1)."""
    table = build_source_quality_table(
        _profile(
            [
                ("정상", 0, 40),
                ("상수1", 0, 1),
                ("상수2", 0, 1),
                ("절반결측", 60, 12),
                ("빈컬럼", 100, 0),
            ]
        ),
        source_rows=100,
    )

    warning = source_quality_warning(table)

    assert warning is not None
    assert warning.startswith("5개 컬럼 중 4개가 정상이 아닙니다 — ")
    assert "비어 있음 1개 · 절반 이상 결측 1개 · 상수 2개." in warning
    assert "비어 있거나 상수" not in warning


def test_the_warning_leaves_out_grades_with_no_columns_and_is_none_when_all_normal() -> None:
    only_constant = build_source_quality_table(
        _profile([("정상", 0, 40), ("상수", 0, 1)]), source_rows=100
    )
    all_normal = build_source_quality_table(_profile([("정상", 0, 40)]), source_rows=100)

    # 결론에 설명 문장을 붙이지 않는다 — 계산에 쓰는 컬럼이면 어디에 나타나는지는 Guide 몫이다.
    assert source_quality_warning(only_constant) == (
        "2개 컬럼 중 1개가 정상이 아닙니다 — 상수 1개."
    )
    assert source_quality_warning(all_normal) is None


def _problem_verdict_app() -> None:
    import pandas as pd

    from capa_simulation.components.source_quality import render_source_quality

    profile = pd.DataFrame(
        {
            "ordinal_position": [1, 2],
            "column_name": ["가", "나"],
            "source_dtype": ["object", "object"],
            "nullable_dtype": ["string", "string"],
            "null_count": [10, 0],
            "unique_count": [0, 4],
        }
    )
    render_source_quality(profile, 10)


def test_a_problem_verdict_is_one_plain_line_like_the_all_normal_one() -> None:
    """문제가 있어도 점검 결론은 상자 없는 평문 한 줄이다 — 모두 정상일 때와 같은 꼴이고 등급은
    표가 말한다(설계 규칙 UI-TXT-04, 사용자 답 place-box)."""
    app = AppTest.from_function(_problem_verdict_app, default_timeout=60).run()

    assert not app.exception, [item.message for item in app.exception]
    assert not app.warning and not app.success
    assert app.caption[0].value == "2개 컬럼 중 1개가 정상이 아닙니다 — 비어 있음 1개."


def test_a_short_table_stands_at_its_content_height_and_a_long_one_keeps_the_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """높이 셈이 줄 높이보다 크면 표 아래에 값 없는 빈 줄이 선다 — 짧은 표는 내용 높이이고, 긴 표만
    상한 안에서 스크롤한다(후보 g7-08 곁 · 샘플 관측 줄 높이 31px)."""
    heights: list[object] = []
    monkeypatch.setattr(st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "dataframe", lambda *args, **kwargs: heights.append(kwargs["height"]))

    for rows in (TABLE_FULL_ROWS, TABLE_FULL_ROWS + 1):
        render_source_quality(_profile([(f"칸{at}", 0, 4) for at in range(rows)]), 100)

    assert heights == ["content", TABLE_MAX_HEIGHT_PX]
