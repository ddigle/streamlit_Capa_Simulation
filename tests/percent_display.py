# Purpose: AppTest 가 그린 표에서 칸의 보이는 글(Styler 표시 글)과 칸 설정 꼴을 읽는 시험 도우미다.

"""표의 % 칸 읽기(시험 도우미).

% 칸은 `components/percent_cells.percent_table` 이 Styler 표시 글(소수 둘째 자리 고정)을 걸고 칸
설정의 `format` 을 뺀다 — 보이는 글은 `proto.arrow_data.styler.display_values` 에, 원값은
`Dataframe.value` 에 있다. 칸 설정은 `proto.columns`(JSON)다.
"""

from __future__ import annotations

import json
from typing import Any

from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df


def shown_texts(frame: Any, column: str) -> list[str]:
    """`column` 칸의 보이는 글(줄 차례). Styler 를 걸지 않은 표면 빈 목록이다."""
    values = frame.proto.arrow_data.styler.display_values
    if not values:
        return []
    table = convert_arrow_bytes_to_pandas_df(values)
    return [str(value) for value in table[column]]


def column_formats(frame: Any) -> dict[str, object]:
    """칸 이름 → 칸 설정의 `format`(없으면 None)."""
    config = json.loads(frame.proto.columns or "{}")
    return {
        name: (settings.get("type_config") or {}).get("format") for name, settings in config.items()
    }
