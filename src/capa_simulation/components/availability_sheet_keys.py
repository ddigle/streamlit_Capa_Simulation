# Purpose: 「Static 대비 일정」 비교 시트의 위젯·세션·컨테이너 key 를 무거운 모듈 없이 한 곳에 둔다.

"""비교 시트(`availability_gap_panel`)의 key.

`app.py` 가 칸 선택을 켠 그림의 key(`GAP_SHEET_CHART_KEY`)를 터치 스크롤 막이 묶음
(`CELL_SELECT_CHART_KEYS`)에 넣는다. 그 key 를 패널 모듈에서 읽으면 앱 진입점이 패널·서비스를 모두
import 한다 — 그래서 key 만 이 가벼운 모듈에 둔다(공정 Capa 상세의 `process_detail_state` 와 같은
까닭). 차트 key 는 고정이다 — 막이 선택자(`.st-key-<key>`)가 접두가 아니라 이름으로 고른다.
"""

from __future__ import annotations

from typing import Final

# 월 Figure(칸 선택을 켠 그림)와 라벨 Figure.
GAP_SHEET_CHART_KEY: Final = "equipment_gap_sheet_chart"
GAP_SHEET_LABEL_CHART_KEY: Final = "equipment_gap_sheet_labels"
# 시트·근거 카드를 그리는 키 붙은 프래그먼트.
GAP_SHEET_FRAGMENT_KEY: Final = "equipment_gap_sheet_fragment"
# 고른 칸(범위 지문, YYYYMM, 행 id) — 위젯이 아니라 세션 칸이다. 비면 닫힘.
GAP_SHEET_CELL_KEY: Final = "equipment_gap_sheet_cell"
# 칸 누름 세대 — 누를 때마다 하나 올라 그림 `layout.meta` 에 실린다.
GAP_SHEET_GENERATION_KEY: Final = "equipment_gap_sheet_generation"
# 직전에 만든 시트 그림 몇 벌(세션 칸).
GAP_SHEET_MEMO_KEY: Final = "equipment_gap_sheet_memo"
# 라벨 칸·월 칸·스크롤 상자·스크롤바·근거 카드·CSV 단추.
GAP_SHEET_LABEL_CANVAS_KEY: Final = "equipment_gap_sheet_label_canvas"
GAP_SHEET_MONTH_REGION_KEY: Final = "equipment_gap_sheet_month_region"
GAP_SHEET_SCROLL_KEY: Final = "equipment_gap_sheet_canvas"
GAP_SHEET_SCROLLBAR_KEY: Final = "equipment_gap_sheet_scrollbar"
GAP_SHEET_EVIDENCE_KEY: Final = "equipment_gap_sheet_evidence"
GAP_SHEET_CSV_KEY: Final = "download_equipment_gap_sheet_csv"
