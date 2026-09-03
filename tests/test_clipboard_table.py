# Purpose: clipboard table 관련 정상·예외·회귀 동작을 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.clipboard_table import parse_clipboard_table


def test_parse_clipboard_table_reads_excel_tab_separated_text() -> None:
    result = parse_clipboard_table(
        "공정\t생산계획년월\t값\r\nProcess-A\t202608\t1.5\r\nProcess-B\t202609\t\r\n",
        "테스트 표",
    )

    assert result.columns.tolist() == ["공정", "생산계획년월", "값"]
    assert result["공정"].tolist() == ["Process-A", "Process-B"]
    assert pd.isna(result.loc[1, "값"])


@pytest.mark.parametrize("content", ["", "   ", "공정\nProcess-A"])
def test_parse_clipboard_table_rejects_non_table_content(content: str) -> None:
    with pytest.raises(ValueError, match="붙여넣기|여러 셀"):
        parse_clipboard_table(content, "테스트 표")


def test_parse_clipboard_table_rejects_duplicate_headers() -> None:
    with pytest.raises(ValueError, match="중복"):
        parse_clipboard_table("공정\t공정\nA\tB", "테스트 표")
