# Purpose: 계산에서 제외된 기준정보 목록을 화면은 표시명, CSV 는 원본으로 나눠 렌더링한다.

"""제외 기준정보 안내 표의 단일 렌더러.

`산출 결과` 의 제외 목록은 본문이 아니라 Alarm 줄의 표다(대당 Capa `제외 기준정보` 2026-11-03,
소요대수 탭 목록 셋 2026-11-05) — 내보내기 프레임(`exclusion_export`)을 알림에 싣는다
(`components/state_alerts.alert_table`). 이 렌더러는 표가 알림에 싣기에 커서
(`alerts.TABLE_ROW_LIMIT`) 본문에 남은 목록을 그린다.

**화면은 표시명, 파일은 원본이다.** `st.dataframe` 에는 표시명을 입힌 복사본을 주고
`render_csv_download` 에는 원본 공정명 프레임을 그대로 준다. 이 표의 CSV 는 `Core_Data` 나
왕복 양식에서 원본을 찾아 고치는 데 쓰기 때문이다.

입력 프레임은 `@st.cache_data` 가 들고 있는 계산 결과의 `attrs` 유래다. 제자리에서 고치면
캐시가 오염되므로 반드시 복사본에만 표시명을 입힌다.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import streamlit as st

from capa_simulation.components.process_labels import PROCESS_COLUMN, ProcessLabels
from capa_simulation.components.table_toolbar import render_csv_download, toolbar_clearance
from capa_simulation.services.display_order import DisplayOrderInput, reorder_display_columns


def exclusion_export(
    exclusions: pd.DataFrame,
    *,
    dimensions: tuple[str, ...] | list[str],
    display_order: DisplayOrderInput,
    page: str,
    tab: str,
) -> pd.DataFrame:
    """제외 목록의 내보내기 프레임(원본 공정명) — 분류 칸을 공용 표시순서의 칸 차례로 세운다. 본문
    표 · CSV 와 알림에 딸린 표(`state_alerts.alert_table`)가 같은 프레임을 쓴다."""
    exported, _ = reorder_display_columns(
        exclusions,
        [column for column in dimensions if column in exclusions.columns],
        display_order,
        page,
        tab,
    )
    return exported


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
    column_help: Mapping[str, str] | None = None,
) -> None:
    """제외 목록 하나를 표시명 표와 원본 CSV 로 그린다. `column_help` 는 칸 머리 풍선(칸 이름 →
    글)이다 — 그 칸의 값을 어디서 고치는지는 목록 곁 자리 글이 아니라 칸 머리 풍선이 말한다(설계
    규칙 UI-TXT-02 · 03)."""
    exported = exclusion_export(
        exclusions, dimensions=dimensions, display_order=display_order, page=page, tab=tab
    )
    displayed = exported.copy()
    if PROCESS_COLUMN in displayed.columns:
        displayed[PROCESS_COLUMN] = labels.series(displayed[PROCESS_COLUMN])
    render_csv_download(
        data=exported.to_csv(index=False).encode("utf-8-sig"),
        file_name=file_name,
        key=key,
    )
    # 표 도구 막대가 바로 위 CSV 단추에 닿지 않게 띄운다(AGENTS 9장 「표 도구 막대」).
    toolbar_clearance()
    st.dataframe(
        displayed,
        hide_index=True,
        width="stretch",
        column_config={
            column: st.column_config.Column(help=text)
            for column, text in (column_help or {}).items()
            if column in displayed.columns
        },
    )
