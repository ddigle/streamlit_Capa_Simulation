# Purpose: 가용설비 현황 「Static 대비 일정」 9행 비교 시트를 화면 서식 그대로 엑셀 통으로 짓는다.

"""「Static 대비 일정」 시트 엑셀.

화면 시트가 그리는 **같은 행 모델**(`availability_sheet_canvas.build_availability_sheet_rows`)을
읽어 공정 Capa 상세 시트 엑셀과 같은 길(`process_capa_workbook.month_rows_sheet`)로 칸 하나하나
옮긴다 — 칸 글 · GAP 증감 글자색 · Static 묶음 면 · 「—」 흐린 글자 · ⚠ 표지를 다시 셈하지 않는다
(화면과 갈리면 안 된다). 그래서 공정(하나 또는 전체 합계) · 조회기간의 달 · 호기 필터(설비 일정
기준만, Static · GAP 은 「—」) · 입력 비가동 반영이 화면 그대로 선다.

- **서식** — 밝은 테마 토큰(엑셀은 흰 바탕 — `theme.pinned_mode`). 고른 칸 테두리 · 굵은 글자는 화면
  조작 표지라 옮기지 않는다(공정 Capa 상세의 지금 보는 달 테두리와 같다). 「—」 칸의 까닭은 화면
  풍선이라 엑셀에는 「—」 만 선다.
- **숫자는 숫자 셀** — 칸 글(소수 2자리 · 부호 · U+2212 · 「 ⚠」)을 같은 글로 보이는 숫자 꼴로
  되읽는다(`process_capa_workbook.screen_number`).

순수 함수다 — Streamlit 을 import 하지 않고 세션 · 캐시를 읽지 않는다. 화면은 그 바이트를 조건
키로 세션에 기억한다(`availability_gap_panel.render_sheet_downloads` —
`sheet_download.remembered_bytes`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from capa_simulation.components.availability_sheet_canvas import build_availability_sheet_rows
from capa_simulation.components.process_capa_workbook import month_rows_sheet
from capa_simulation.design import theme
from capa_simulation.io.xlsx_small import workbook_bytes
from capa_simulation.services.availability_sheet import SheetView

__all__ = [
    "GAP_SHEET_NAME",
    "GapWorkbookRequest",
    "availability_sheet_workbook",
]

GAP_SHEET_NAME: Final = "Static 대비 일정"
TITLE: Final = "Static 대비 일정 · 분류별 내역"


@dataclass(frozen=True, eq=False)
class GapWorkbookRequest:
    """엑셀 한 벌의 재료 — 화면 회차가 값으로 잡아 넘긴다. 시트 인자는 화면 시트와 같고(고른 칸만
    없음), `heading` 은 맨 위 (이름, 값) 줄이다(공정 · 조회기간 · 설비 시나리오 · 호기 필터)."""

    view: SheetView
    process_label: str
    schedule_detail: str
    heading: Sequence[tuple[str, str]]


def availability_sheet_workbook(request: GapWorkbookRequest) -> bytes:
    """엑셀 통 바이트 — 시트 「Static 대비 일정」 한 장."""
    with theme.pinned_mode("light"):
        rows = build_availability_sheet_rows(
            view=request.view,
            process_label=request.process_label,
            schedule_detail=request.schedule_detail,
        )
        sheet = month_rows_sheet(
            name=GAP_SHEET_NAME,
            title=TITLE,
            rows=rows,
            axis=[int(month) for month in request.view.months],
            heading=request.heading,
        )
    return workbook_bytes([sheet])
