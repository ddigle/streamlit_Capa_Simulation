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


def show_past_months_outside_range(first_past_month: int) -> None:
    """넣어 둔 과거 구간이 조회기간 밖이라 화면에 없다는 사실을 알린다.

    볼 수 있는 범위는 과거 구간만큼 자동으로 넓어지지만 **고른 범위는 그대로다**. 그래서
    과거를 저장해도 조회기간 시작월을 내리지 않으면 그 달이 표에 나타나지 않는데, 화면만
    보면 넣은 값이 사라진 것처럼 보인다. 어디까지 내려야 하는지 함께 적는다.
    """
    if _month_range_placeholder is None:
        return
    _month_range_placeholder.caption(
        f":material/info: 과거 구간이 조회기간 밖에 있습니다 · 시작월을 "
        f"{month_label(first_past_month)} 로 내리면 보입니다"
    )


def show_month_range_unavailable() -> None:
    """선택 범위에 데이터가 없어 계산이 서지 않았음을 같은 자리에 알린다.

    자리표시자는 rerun 을 넘어 남는다. 실패한 rerun 에서 아무것도 쓰지 않으면 직전에 성공한
    범위가 "적용" 으로 계속 보여 본문 오류와 어긋난다.
    """
    if _month_range_placeholder is None:
        return
    _month_range_placeholder.caption(":material/block: 적용 안 됨 · 선택 범위에 데이터 없음")
