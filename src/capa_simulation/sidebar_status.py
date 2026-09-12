# Purpose: 공통 사이드바에 실제 계산에 적용된 생산계획년월 범위를 표시한다.

from streamlit.delta_generator import DeltaGenerator

from capa_simulation.services.month_columns import month_label

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
        f":material/check_circle: 적용 · {month_label(start_month)}–{month_label(end_month)}"
    )


def show_month_range_unavailable() -> None:
    """선택 범위에 데이터가 없어 계산이 서지 않았음을 같은 자리에 알린다.

    자리표시자는 rerun 을 넘어 남는다. 실패한 rerun 에서 아무것도 쓰지 않으면 직전에 성공한
    범위가 "적용" 으로 계속 보여 본문 오류와 어긋난다.
    """
    if _month_range_placeholder is None:
        return
    _month_range_placeholder.caption(":material/block: 적용 안 됨 · 선택 범위에 데이터 없음")
