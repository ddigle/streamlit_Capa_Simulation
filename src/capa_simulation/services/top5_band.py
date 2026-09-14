# Purpose: B/N Top5 막대 높이가 표현하는 확보율 구간의 기본값과 검증을 담당한다.

"""B/N Top5 막대의 확보율 밴드.

Top5 막대의 높이는 `B/N Capa = 부하량 × 확보율` 이다. 한 달 안에서 부하량이 같으므로
**높이가 곧 확보율에 비례**하고, 한 달의 확보율이 크면 그 달 막대가 다른 달을 눈동자로
만든다. 밴드는 그 비례를 끊어 막대 길이를 읽을 수 있는 구간에 묶는다.

    밴드 아래 → 막대 0
    밴드 위   → 막대가 축 끝까지

**상세 B/N 가로막대의 80~150% 와는 다른 설정이다.** 그쪽은 `BOTTLENECK_BAR_MIN_RATE`·
`BOTTLENECK_BAR_MAX_RATE` 가 정하고 여기서 건드리지 않는다 — 두 차트는 쓰임이 달라 같은
구간을 강요하면 한쪽이 읽히지 않는다.

hover 에 뜨는 Capa 숫자는 **자르지 않은 실제 값**이다. 자르는 것은 막대 길이뿐이다.
"""

from __future__ import annotations

# 화면 기본값. 확보율은 비율이므로 0.5 = 50% 다.
DEFAULT_TOP5_MIN_RATE = 0.50
DEFAULT_TOP5_MAX_RATE = 2.00

# 입력이 견딜 수 있는 바깥 한계. 음수 확보율은 막대 길이가 의미를 잃고, 상한이 하한보다
# 작거나 같으면 나눌 구간이 없다.
TOP5_RATE_FLOOR = 0.0
TOP5_RATE_CEILING = 100.0


def validate_top5_band(min_rate: float, max_rate: float) -> tuple[float, float]:
    """저장·적용 공용 검증. 잘못된 구간은 화면이 잡아 사용자에게 되돌린다."""
    low = float(min_rate)
    high = float(max_rate)
    if low < TOP5_RATE_FLOOR or high < TOP5_RATE_FLOOR:
        raise ValueError("확보율 구간은 0% 이상이어야 합니다.")
    if high > TOP5_RATE_CEILING:
        raise ValueError(f"확보율 상한은 {TOP5_RATE_CEILING:.0%} 이하여야 합니다.")
    if low >= high:
        raise ValueError("확보율 상한은 하한보다 커야 합니다.")
    return low, high


def clamp_rate(rate: float, band: tuple[float, float]) -> float:
    """막대 길이에 쓸 확보율. 밴드 밖은 끝에서 자른다."""
    low, high = band
    return min(max(rate, low), high)
