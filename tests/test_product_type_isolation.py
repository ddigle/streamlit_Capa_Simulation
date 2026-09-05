# Purpose: HBM 과 EDP-TSV 의 계산 규칙이 서로에게 새지 않는지 지킨다.

"""제품타입 사이의 로직 의존성을 끊어 둔다 (2026-09-05 지시).

두 제품군은 **`Top` 과 `Master` 라는 같은 이름을 공유**한다.

| 제품타입 | `WF 구분` |
|---|---|
| HBM | Buffer, Core, Top, Dummy |
| EDP-TSV | Top, Master, Slave |

그래서 `WF 구분` 만 보고 쓴 규칙은 의도와 무관하게 양쪽에 다 걸린다. 초기에는
`Master`↔`Buffer`, `Slave`↔`Core` 로 짝지어 한쪽을 다른 쪽으로 번역하려 했으나, 그렇게
묶으면 한쪽을 고칠 때 다른 쪽이 따라 움직인다. 짝짓기를 만들지 않고 규칙을
**(제품타입, WF 구분)** 으로 건다.

산식 자체는 지금 두 제품군이 동일하다. 그래서 이 테스트들은 **수치가 아니라 격리**를
본다 — 한쪽 이름에 걸린 규칙이 다른 쪽 행을 건드리지 않는지.
"""

import pandas as pd

from capa_simulation.services.load_calculator import (
    DUMMY_DIVISIONS_BY_PRODUCT_TYPE,
    EDP_PRODUCT_TYPE,
    EDP_WF_DIVISIONS,
    HBM_PRODUCT_TYPE,
    HBM_WF_DIVISIONS,
    WF_DIVISIONS_BY_PRODUCT_TYPE,
    calculate_chip_load,
)

PLAN = pd.DataFrame(
    {
        "생산계획년월": [202601, 202601],
        "양산구분": ["양산", "양산"],
        "제품정보": ["HBM-A", "EDP-A"],
        "제품타입": [HBM_PRODUCT_TYPE, EDP_PRODUCT_TYPE],
        "Stack": ["8H", "8H"],
        "Capa Code": ["C1", "C2"],
        "Customer": ["CUST", "CUST"],
        "CS": ["MP", "MP"],
        "생산수량": [100.0, 100.0],
    }
)


def _reference(division: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """두 제품이 같은 `WF 구분` 이름을 쓰는 기준정보."""
    chip = pd.DataFrame(
        {
            "제품정보": ["HBM-A", "EDP-A"],
            "Stack": ["8H", "8H"],
            "WF 구분": [division, division],
            "구분_Chip": [4.0, 4.0],
            "Net Die": [100.0, 100.0],
        }
    )
    yields = pd.DataFrame(
        {
            "생산계획년월": [202601, 202601],
            "제품정보": ["HBM-A", "EDP-A"],
            "Stack": ["8H", "8H"],
            "WF 구분": [division, division],
            "EDS_수율": [0.9, 0.9],
            "BE_수율": [0.95, 0.95],
        }
    )
    return yields, chip


def _volume_by_product(division: str) -> dict[str, float]:
    yields, chip = _reference(division)
    result = calculate_chip_load(PLAN, yields, chip)
    return dict(zip(result["제품정보"], result["물량"].astype(float), strict=True))


def test_the_hbm_dummy_rule_does_not_reach_an_edp_row() -> None:
    """`Dummy` 는 HBM 의 이름이다. 같은 이름이 EDP 행에 붙어 와도 그 산식을 태우지 않는다.

    태우면 EDP 물량이 `(1 - EDS_수율)` 만큼 줄어든다. 한쪽 제품군의 규칙이 다른 쪽 숫자를
    바꾸는 것이 정확히 이 지시가 막으려는 것이다.
    """
    volumes = _volume_by_product("Dummy")

    # HBM: 생산수량 × 구분_Chip ÷ EDS ÷ BE × (1 - EDS)
    assert volumes["HBM-A"] == 100.0 * 4.0 / 0.9 / 0.95 * (1 - 0.9)
    # EDP: 일반 산식. Dummy 라는 이름에 끌려가지 않는다.
    assert volumes["EDP-A"] == 100.0 * 4.0 / 0.95


def test_a_shared_division_name_gives_both_types_the_same_general_rule() -> None:
    """`Top` 은 두 제품군이 함께 쓰는 이름이다. 특별 규칙이 없으면 둘 다 일반 산식이다."""
    volumes = _volume_by_product("Top")

    assert volumes["HBM-A"] == volumes["EDP-A"] == 100.0 * 4.0 / 0.95


def test_the_two_division_sets_are_declared_independently() -> None:
    """한쪽을 고칠 때 다른 쪽이 따라 움직이면 안 된다. 공통 부분을 뽑아 공유하지 않는다."""
    assert HBM_WF_DIVISIONS == ("Buffer", "Core", "Top", "Dummy")
    assert EDP_WF_DIVISIONS == ("Top", "Master", "Slave")
    assert WF_DIVISIONS_BY_PRODUCT_TYPE[HBM_PRODUCT_TYPE] is HBM_WF_DIVISIONS
    assert WF_DIVISIONS_BY_PRODUCT_TYPE[EDP_PRODUCT_TYPE] is EDP_WF_DIVISIONS
    # 겹치는 이름이 실제로 있다는 것이 이 격리가 필요한 이유다.
    assert set(HBM_WF_DIVISIONS) & set(EDP_WF_DIVISIONS) == {"Top"}


def test_edp_declares_no_dummy_division() -> None:
    """EDP-TSV 의 WF 구분은 Top·Master·Slave 뿐이다. Dummy 산식을 받을 이름이 없다."""
    assert DUMMY_DIVISIONS_BY_PRODUCT_TYPE[EDP_PRODUCT_TYPE] == ()
    assert DUMMY_DIVISIONS_BY_PRODUCT_TYPE[HBM_PRODUCT_TYPE] == ("Dummy",)


def test_a_frame_without_a_product_type_keeps_the_older_behaviour() -> None:
    """제품타입 도입 이전 경로도 계속 돌아야 한다. 그때는 이름만 보고 고른다."""
    volumes_without_type = calculate_chip_load(PLAN.drop(columns="제품타입"), *_reference("Dummy"))
    by_product = dict(
        zip(
            volumes_without_type["제품정보"],
            volumes_without_type["물량"].astype(float),
            strict=True,
        )
    )

    expected = 100.0 * 4.0 / 0.9 / 0.95 * (1 - 0.9)
    assert by_product == {"HBM-A": expected, "EDP-A": expected}
