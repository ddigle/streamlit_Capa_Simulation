# Purpose: 공통 사이드바에 실제 계산에 적용된 생산계획년월 범위를 표시한다.

from streamlit.delta_generator import DeltaGenerator

_month_range_placeholder: DeltaGenerator | None = None


def register_month_range_placeholder(placeholder: DeltaGenerator) -> None:
    global _month_range_placeholder
    _month_range_placeholder = placeholder


def show_applied_month_range(start_month: int, end_month: int) -> None:
    if _month_range_placeholder is None:
        return
    _month_range_placeholder.caption(
        f"✅ 적용 · {_format_short_month(start_month)}–{_format_short_month(end_month)}"
    )


def _format_short_month(month: int) -> str:
    return f"{month // 100 % 100:02d}.{month % 100:02d}"
