# Purpose: 범주색이 색각이상에서도 서로 구분되는지 계산으로 고정한다.

"""색은 눈으로 보지 말고 계산한다.

설비 상태 9종과 재공 격자 5종은 **색이 상태의 유일한 채널**이다. 그런데 옛 파스텔
팔레트는 적록색약에서 두 쌍이 사실상 같은 색이었다 — `입고 예정`↔`이설 예정` ΔE 0.5,
`유입`↔`표준 미설정` ΔE 0.3. 범례가 있어도 두 칸을 가를 수 없다는 뜻이고, 눈으로 골라서는
드러나지 않는다(정상 시야에서는 구분되기 때문이다).

그래서 여기서 **잰다.** OKLab 거리와 Machado(2009) 색각이상 시뮬레이션은 dataviz 규칙이
정한 것과 같은 식이다 — 고르는 쪽과 재는 쪽이 다른 자를 쓰면 통과 여부가 갈린다.

**정상 시야 권장선(15)은 검사하지 않는다.** 9종은 색만으로 완전히 가를 수 있는 수를
넘어 그 선에 닿을 수 없고, 그것이 곧 범례·라벨이 함께 있어야 하는 이유다. 여기서 막는
것은 「색각이상에서 두 상태가 같은 색이 되는 것」 하나다.
"""

import math
from itertools import combinations

from capa_simulation.design import tokens

# Machado, Oliveira & Fernandes (2009), severity 1.0, 선형 RGB.
MACHADO = {
    "protan": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deutan": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritan": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}
# dataviz 규칙의 하한. 6~8 은 2차 인코딩이 함께 있을 때만 허용되는 구간이고,
# 이 두 팔레트는 범례와 라벨을 함께 갖는다.
CVD_FLOOR = 6.0


def _linear(hex_color: str) -> tuple[float, float, float]:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return tuple(channel(int(hex_color[i : i + 2], 16)) for i in (1, 3, 5))  # type: ignore[return-value]


def _simulate(rgb: tuple[float, float, float], kind: str) -> tuple[float, float, float]:
    matrix = MACHADO[kind]
    return tuple(  # type: ignore[return-value]
        min(1.0, max(0.0, sum(matrix[row][col] * rgb[col] for col in range(3)))) for row in range(3)
    )


def _oklab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    red, green, blue = rgb
    long = (0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue) ** (1 / 3)
    medium = (0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue) ** (1 / 3)
    short = (0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue) ** (1 / 3)
    return (
        0.2104542553 * long + 0.7936177850 * medium - 0.0040720468 * short,
        1.9779984951 * long - 2.4285922050 * medium + 0.4505937099 * short,
        0.0259040371 * long + 0.7827717662 * medium - 0.8086757660 * short,
    )


def cvd_distance(first: str, second: str) -> float:
    """색각이상 3종 중 **가장 가까워지는** 거리. 최악을 본다."""
    left, right = _linear(first), _linear(second)
    return 100 * min(
        math.dist(_oklab(_simulate(left, kind)), _oklab(_simulate(right, kind))) for kind in MACHADO
    )


def _closest(mapping: dict[str, str]) -> tuple[float, str, str]:
    names = list(mapping)
    return min((cvd_distance(mapping[a], mapping[b]), a, b) for a, b in combinations(names, 2))


def test_equipment_stage_colors_stay_apart_for_colour_blind_readers() -> None:
    distance, first, second = _closest(tokens.EQUIPMENT_STAGE_COLORS)

    assert distance >= CVD_FLOOR, (
        f"`{first}` 와 `{second}` 가 색각이상에서 ΔE {distance:.1f} 로 붙어 있습니다"
        f"(하한 {CVD_FLOOR}). 색이 상태의 유일한 채널이라 두 상태를 가를 수 없습니다."
    )


def test_wip_grid_colors_stay_apart_for_colour_blind_readers() -> None:
    grid = {
        "보유": tokens.WIP_HELD,
        "유입": tokens.WIP_INFLOW,
        "충족": tokens.WIP_FLOW_MET,
        "부족": tokens.WIP_FLOW_SHORT,
        "표준 미설정": tokens.WIP_FLOW_UNSET,
    }

    distance, first, second = _closest(grid)

    assert distance >= CVD_FLOOR, (
        f"`{first}` 와 `{second}` 가 색각이상에서 ΔE {distance:.1f} 로 붙어 있습니다"
        f"(하한 {CVD_FLOOR})."
    )


def test_qual_confirmation_colors_stay_apart() -> None:
    distance, first, second = _closest(tokens.QUAL_CONFIRMATION_COLORS)

    assert distance >= CVD_FLOOR, f"`{first}`·`{second}` ΔE {distance:.1f} < {CVD_FLOOR}"


def test_the_old_pastels_would_have_failed() -> None:
    """검사가 실제로 무언가를 막는지 확인한다.

    옛 값을 그대로 넣어 하한 아래로 떨어지는 것을 보인다. 이 단언이 깨지면 검사가
    느슨해진 것이므로 하한이 아니라 계산식을 먼저 의심한다.
    """
    old_equipment = {"입고 예정": "#93C5FD", "이설 예정": "#C4B5FD"}
    old_grid = {"유입": "#60A5FA", "표준 미설정": "#A78BFA"}

    assert _closest(old_equipment)[0] < 1.0
    assert _closest(old_grid)[0] < 1.0
