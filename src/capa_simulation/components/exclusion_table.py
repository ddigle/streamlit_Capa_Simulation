# Purpose: 계산에서 제외된 기준정보 목록을 화면은 표시명, CSV 는 원본으로 나눠 렌더링한다.

"""제외 기준정보 안내 표의 단일 렌더러.

`산출 결과` 의 두 제외 표(`제외 기준정보 확인`·`소요대수 제외 기준정보`)가 이 함수 하나로
같은 모양을 그린다.

**화면은 표시명, 파일은 원본이다.** `st.dataframe` 에는 표시명을 입힌 복사본을 주고
`render_csv_download` 에는 원본 공정명 프레임을 그대로 준다. 이 표의 CSV 는 `Core_Data` 나
왕복 양식에서 원본을 찾아 고치는 데 쓰기 때문이다.

입력 프레임은 `@st.cache_data` 가 들고 있는 계산 결과의 `attrs` 유래다. 제자리에서 고치면
캐시가 오염되므로 반드시 복사본에만 표시명을 입힌다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.process_labels import PROCESS_COLUMN, ProcessLabels
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.services.display_order import DisplayOrderInput, reorder_display_columns


def render_exclusion_table(
    exclusions: pd.DataFrame,
    *,
    dimensions: tuple[str, ...] | list[str],
    display_order: DisplayOrderInput,
    page: str,
    tab: str,
    labels: ProcessLabels,
    file_name: str,
    key: str,
) -> None:
    """제외 목록 하나를 표시명 표와 원본 CSV 로 그린다."""
    exported, _ = reorder_display_columns(
        exclusions,
        [column for column in dimensions if column in exclusions.columns],
        display_order,
        page,
        tab,
    )
    displayed = exported.copy()
    if PROCESS_COLUMN in displayed.columns:
        displayed[PROCESS_COLUMN] = labels.series(displayed[PROCESS_COLUMN])
    render_csv_download(
        data=exported.to_csv(index=False).encode("utf-8-sig"),
        file_name=file_name,
        key=key,
    )
    st.dataframe(displayed, hide_index=True, width="stretch")
