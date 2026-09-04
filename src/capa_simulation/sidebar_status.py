# Purpose: 공통 사이드바에 실제 계산에 적용된 생산계획년월 범위를 표시한다.

from streamlit.delta_generator import DeltaGenerator

_month_range_placeholder: DeltaGenerator | None = None


def register_month_range_placeholder(placeholder: DeltaGenerator) -> None:
    global _month_range_placeholder
    _month_range_placeholder = placeholder


def show_applied_month_range(start_month: int, end_month: int) -> None:
    """계산에 실제로 쓰인 월 범위를 사이드바에 알린다.

    사용자가 고른 범위에 데이터가 없으면 `resolve_effective_months` 가 범위를 좁힌다.
    좁혀졌다는 사실을 알리지 않으면 화면 숫자가 왜 다른지 알 수 없다.
    """
    if _month_range_placeholder is None:
        return
    _month_range_placeholder.caption(
        f":material/check_circle: 적용 · "
        f"{_format_short_month(start_month)}–{_format_short_month(end_month)}"
    )


def _format_short_month(month: int) -> str:
    return f"{month // 100 % 100:02d}.{month % 100:02d}"
