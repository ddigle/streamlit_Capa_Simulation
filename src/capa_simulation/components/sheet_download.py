# Purpose: 「시트 엑셀」 통을 조건 키로 세션에 몇 벌 기억하고 시트 맨 위 머리 값 글을 짓는다.

"""「시트 엑셀」 의 화면 쪽 공용 몫.

**통을 만드는 때**(공정 Capa 상세가 처음 세운 길 — 2026-11-10 보드 c2-picked): 내려받기 단추는
바이트를 받아야 서므로 회차마다 통을 짓지 않게 **조건이 바뀐 뒤 처음 그리는 회차에 한 번** 지어
세션에 몇 벌 기억한다(`remembered_bytes`). 누를 때만 짓는 콜러블은 쓰지 않는다 — 실패가
「Failed to generate file for download」 한 줄로 삼켜진다(2026-09-18 결정). 새 `st.cache_*` 를 두지
않는다 — 키는 부르는 쪽이 화면 상태(내용 토큰 · 표 지문 · 보기 · 거름 · 표시명 판 · 머리 값 · 시트
꼴 판)로 짓고, 큰 표는 키에 넣지 않는다. 화면마다 세션 칸 이름이 따로다(서로의 몇 벌을 밀어내지
않게).

**머리 값 글**은 머리 띠 · 사이드바가 보이는 글자 그대로다(마크다운 막음 없이 — 엑셀 칸은 평문).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Final

import streamlit as st

from capa_simulation.components.app_header import header_lines
from capa_simulation.components.intro_summary import latest_official_revision
from capa_simulation.scenario_activation import (
    active_scenario_label,
    has_unsaved_scenario_changes,
    newer_active_revision_no,
)
from capa_simulation.services.month_columns import month_label

__all__ = [
    "SHEET_MEMO_LIMIT",
    "process_filter_text",
    "remembered_bytes",
    "scenario_period_rows",
]

# 한 화면이 세션에 두는 통 수 — 조건을 오가도(탭 둘 · 보기 둘) 다시 짓지 않을 만큼.
SHEET_MEMO_LIMIT: Final = 4
# 공정 거름이 걸리지 않은 때의 값 글(사이드바 공정 칸이 비었을 때와 같은 뜻).
ALL_PROCESSES: Final = "전체"


def remembered_bytes(
    memo_key: str,
    key: tuple[object, ...],
    build: Callable[[], bytes],
    *,
    limit: int = SHEET_MEMO_LIMIT,
) -> bytes:
    """통 바이트를 세션 칸(`memo_key`)에 `limit` 벌까지 기억한다 — 같은 조건 키면 다시 짓지 않는다.

    빗나간 회차는 이 자리에서 바로 지어 오류가 화면에 드러난다(짓다 실패하면 기억하지 않는다).
    새로 지은 것이 맨 뒤이고 넘치면 가장 오래된 것부터 버린다.
    """
    memo = st.session_state.get(memo_key)
    entries: list[tuple[tuple[object, ...], bytes]] = (
        [entry for entry in memo if isinstance(entry, tuple) and len(entry) == 2]
        if isinstance(memo, list)
        else []
    )
    for stored_key, stored in entries:
        if stored_key == key and isinstance(stored, bytes):
            return stored
    data = build()
    entries = [entry for entry in entries if entry[0] != key][-(limit - 1) :]
    st.session_state[memo_key] = [*entries, (key, data)]
    return data


def scenario_period_rows(
    *, selected: tuple[int, int], applied: tuple[int, int]
) -> tuple[tuple[str, str], ...]:
    """시트 맨 위 (이름, 값) 두 줄 — 시나리오(머리 띠 위 줄과 같은 함수 `header_lines`)와 조회기간
    (사이드바 값, 적용 범위가 다르면 「· 적용 …」). 세션만 읽는다."""
    scenario_line, _ = header_lines(
        active_scenario_label(),
        official=latest_official_revision(),
        unsaved=has_unsaved_scenario_changes(),
        newer_revision_no=newer_active_revision_no(),
    )
    chosen = f"{month_label(selected[0])}–{month_label(selected[1])}"
    effective = f"{month_label(applied[0])}–{month_label(applied[1])}"
    period = chosen if chosen == effective else f"{chosen} · 적용 {effective}"
    return (("시나리오", scenario_line), ("조회기간", period))


def process_filter_text(applied: Sequence[str], label: Callable[[str], str] = str) -> str:
    """공정 거름 값 글 — 걸리지 않았으면 「전체」, 걸렸으면 화면 글자(`label` — 표시명)를 「 · 」 로
    잇는다."""
    if not applied:
        return ALL_PROCESSES
    return " · ".join(label(process) for process in applied)
