# Purpose: 공통 사이드바에 실제 계산에 적용된 생산계획년월 범위를 표시한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

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
