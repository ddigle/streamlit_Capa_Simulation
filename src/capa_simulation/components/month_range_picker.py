# Purpose: 조회기간 팝업의 해 넘김 · 달 격자 · 빠른 선택 · 「적용」을 한 컴포넌트로 묶는다.

"""조회기간 팝업(`components/period_field.py`)의 달 고르기.

2026-11-04 검수 의견 home-19 — 월 입력 두 칸을 걷었다.

머리 줄 `‹ 2026년 ›` 이 해를 넘기고, 열두 달 격자(세 칸 네 줄 — 한 줄이 한 분기)에서 시작 달 → 끝
달을 차례로 누르면 범위가 띠로 칠해진다. 아래 빠른 선택(이번 달부터 6 · 12 · 24개월, 지난달부터
6개월, 전체)이 한 번에 범위를 놓고, 맨 아래 줄이 고른 범위 · 개월 수와(지금 기간과 다르면) 「지금
…」 을 적는다. 고를 수 없는 달은 흐리게 잠긴다. 키보드는 방향키(한 달 · 한 분기) ·
PageUp/PageDown(한 해) · Home/End · Enter.

**「적용」은 컴포넌트 안이다**(2026-10-11 병합 전 리뷰부터). 초안 범위와 누름을 한 트리거(`apply`)로
한 회차에 보낸다 — 값을 따로 보내면 고친 직후 누른 「적용」이 옛 값으로 닫혔다. 끝 달을 아직 고르지
않았거나 초안이 지금 기간과 같으면 단추가 잠긴다(설명 글 대신 단추 상태와 「지금 …」 줄이 「적용
전에는 화면이 그대로」 임을 말한다). 고르는 동안의 값은 서버에 오지 않는다(초안).

화면 조각은 `month_range_picker_assets/` 의 세 파일이다. 판정 구획(`// <month-range-core>`)은 DOM 을
모르는 순수 함수라 node 로 떼어 시험한다(`tests/test_month_range_picker.py`).
"""

from collections.abc import Mapping
from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).with_name("month_range_picker_assets")
MONTH_RANGE_HTML = (_ASSETS / "month_range.html").read_text(encoding="utf-8")
MONTH_RANGE_CSS = (_ASSETS / "month_range.css").read_text(encoding="utf-8")
MONTH_RANGE_JS = (_ASSETS / "month_range.js").read_text(encoding="utf-8")

# **그림자 DOM 으로 가두지 않는다**(`isolate_styles=False`). 팝업(`st.dialog`)은 포커스를 팝업
# 안에서 돌리는데 그 순서는 그림자 DOM 안을 보지 못한다 — 가둔 채로는 칸에서 Tab 을 누르면 다음 칸 ·
# 「적용」이 아니라 팝업의 닫기 단추로 가서, Tab · Enter 가 고친 기간을 버리고 팝업을
# 닫았다(2026-10-11 브라우저 실측). 서식은 `capa-month-*` 클래스로만 걸어 앱의 다른 요소에 새지
# 않는다.
_MONTH_RANGE_APPLY = st.components.v2.component(
    "capa_month_range_apply",
    html=MONTH_RANGE_HTML,
    css=MONTH_RANGE_CSS,
    js=MONTH_RANGE_JS,
    isolate_styles=False,
)


def _valid_month(value: object, minimum: str, maximum: str) -> str | None:
    if not isinstance(value, str):
        return None
    parts = value.split("-")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    year, month = (int(part) for part in parts)
    normalized = f"{year:04d}-{month:02d}"
    if month < 1 or month > 12 or normalized < minimum or normalized > maximum:
        return None
    return normalized


def clamp_month_range(start: str, end: str, min_month: str, max_month: str) -> tuple[str, str]:
    """고를 수 있는 범위 밖·깨진 값을 범위 끝으로 끼운다. 시작 > 끝이면 끝을 시작에 맞춘다."""
    clamped_start = _valid_month(start, min_month, max_month) or min_month
    clamped_end = _valid_month(end, min_month, max_month) or max_month
    if clamped_start > clamped_end:
        clamped_end = clamped_start
    return clamped_start, clamped_end


def render_month_range_apply(
    *,
    start: str,
    end: str,
    min_month: str,
    max_month: str,
    key: str,
    this_month: str | None = None,
) -> tuple[str, str] | None:
    """달 고르기와 「적용」. 「적용」을 누른 회차에만 검증한 `(YYYY-MM, YYYY-MM)` 를 돌려준다.

    그 밖의 회차는 `None` 이다 — 격자에서 고르는 동안의 값은 서버에 오지 않는다(초안). `this_month`
    (`YYYY-MM`)는 빠른 선택 「이번 달부터 · 지난달부터」 의 기준 달과 격자의 이번 달 고리다 — 없으면
    그 단추가 잠긴다.
    """
    shown_start, shown_end = clamp_month_range(start, end, min_month, max_month)
    result = _MONTH_RANGE_APPLY(
        key=key,
        data={
            "start": shown_start,
            "end": shown_end,
            "minMonth": min_month,
            "maxMonth": max_month,
            "thisMonth": _valid_month(this_month, "0000-01", "9999-12"),
        },
        on_apply_change=lambda: None,
        width="stretch",
    )
    applied = getattr(result, "apply", None)
    if not isinstance(applied, Mapping):
        return None
    applied_start = _valid_month(applied.get("start"), min_month, max_month)
    applied_end = _valid_month(applied.get("end"), min_month, max_month)
    if applied_start is None or applied_end is None or applied_start > applied_end:
        return None
    return applied_start, applied_end
