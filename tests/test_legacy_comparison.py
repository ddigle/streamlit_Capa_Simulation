# Purpose: 기존 결과 대조의 집계 단위가 뒤집히지 않게 고정한다.

"""원천의 기존 결과와 신규 계산을 맞춰 보는 규칙.

**접는 층을 어디서 잡느냐가 전부다.** 원천은 경로(공정·STEP·MCP)별로 행이 펼쳐져 있고
기존 결과 컬럼은 그 경로 행마다 같은 값이 반복된다. 그래서 기존 쪽은 계획 한 줄
(`RQ_PKG_PLAN` 업무 키) × `WF 구분` 을 한 칸으로 보고 그 안의 반복만 접은 뒤 대조 키로
합산한다.

처음에는 접는 층을 한 단계 위(대조 키)에서 잡았다. 그러자 같은 대조 키에 계획 줄이
여럿인 경우 — Capa Code·Customer·CS 가 다른 줄들 — 이 "값이 갈린다" 로 분류돼 대조에서
통째로 빠졌고, 샘플에서 Wafer 270키 중 121키만 보고 "완전 일치" 라는 거짓 결론이 났다.
`test_separate_plan_rows_are_summed_not_treated_as_a_conflict` 가 그 회귀를 막는다.

`기존 0·신규 있음` 을 따로 세는 것도 같은 이유다. 기존값이 0 이면 비율을 구할 수 없는데
예전에는 `fillna(0.0)` 으로 통과 처리해 59건을 놓쳤다.
"""

import pandas as pd

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.services.legacy_comparison import (
    COMPARISON_KEYS,
    LegacyMetric,
    compare_metric,
    legacy_grain,
    summarize_comparison,
)

METRIC = LegacyMetric(label="Wafer 부하량 (매)", legacy_column="WF수(매)")
CONTRACT = load_core_data_contract()

# 대조 키 밖에 있으면서 계획 줄을 가르는 컬럼들. 이것이 다르면 서로 다른 계획이다.
_PLAN_DEFAULTS = {
    "양산구분": "양산",
    "CS": "MP",
    "Capa Code": "CAPA-1",
    "Customer": "고객가",
    "Pack Code": "PACK-1",
}


def _plan_row(value: float, *, routes: int = 31, **overrides: object) -> pd.DataFrame:
    """계획 한 줄이 경로 `routes` 개로 펼쳐진 원천 조각.

    기존 결과 컬럼은 그 경로 행마다 같은 값으로 반복된다 — 실제 원천이 그렇다.
    """
    fields: dict[str, object] = {
        "생산계획년월": 202608,
        "제품정보": "Product-A",
        "Stack": "8H",
        "WF 구분": "Core",
        **_PLAN_DEFAULTS,
        **overrides,
    }
    return pd.DataFrame(
        {**{k: [v] * routes for k, v in fields.items()}, "WF수(매)": [value] * routes}
    )


def _core(*rows: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(rows, ignore_index=True)


def _calculated(*values: float, **overrides: object) -> pd.DataFrame:
    fields: dict[str, object] = {
        "생산계획년월": 202608,
        "제품정보": "Product-A",
        "Stack": "8H",
        "WF 구분": "Core",
        **overrides,
    }
    return pd.DataFrame({**{k: [v] * len(values) for k, v in fields.items()}, "물량": list(values)})


def _compare(core: pd.DataFrame, calculated: pd.DataFrame) -> pd.DataFrame:
    return compare_metric(core, calculated, METRIC, CONTRACT)


def test_repeated_route_rows_are_folded_not_summed() -> None:
    """한 계획 줄의 경로 31행에 같은 값이 반복돼도 기존값은 그 값 하나여야 한다."""
    comparison = _compare(_core(_plan_row(100.0)), _calculated(100.0))

    assert len(comparison) == 1
    assert comparison["기존값"].iloc[0] == 100.0
    assert comparison["차이"].iloc[0] == 0.0
    assert summarize_comparison(comparison)["허용 초과"] == 0


def test_separate_plan_rows_are_summed_not_treated_as_a_conflict() -> None:
    """같은 대조 키의 서로 다른 계획 줄은 **합산**이다. 값이 갈린 것이 아니다.

    이것을 값 불일치로 처리했다가 실제로 270키 중 149키를 대조에서 빠뜨렸다.
    """
    core = _core(
        _plan_row(100.0, **{"Capa Code": "CAPA-1"}),
        _plan_row(60.0, **{"Capa Code": "CAPA-2"}),
    )

    comparison = _compare(core, _calculated(160.0))
    summary = summarize_comparison(comparison)

    assert comparison["기존값"].iloc[0] == 160.0
    assert bool(comparison["값 불일치"].iloc[0]) is False
    assert summary["대조 건수"] == 1
    assert summary["값 불일치"] == 0


def test_a_real_difference_still_shows_up() -> None:
    """집계를 고쳤다고 진짜 차이까지 가려지면 안 된다."""
    comparison = _compare(_core(_plan_row(100.0)), _calculated(110.0))

    assert comparison["차이"].iloc[0] == 10.0
    assert comparison["차이율"].iloc[0] == 0.1
    assert summarize_comparison(comparison)["허용 초과"] == 1


def test_conflict_inside_one_plan_row_is_reported_not_picked() -> None:
    """한 계획 줄의 경로 행끼리 값이 갈리면 접을 수 없다. 조용히 고르지 않는다."""
    core = _plan_row(100.0, routes=2)
    core.loc[1, "WF수(매)"] = 200.0

    comparison = _compare(core, _calculated(100.0))
    summary = summarize_comparison(comparison)

    assert pd.isna(comparison["기존값"].iloc[0])
    assert bool(comparison["값 불일치"].iloc[0]) is True
    assert summary["값 불일치"] == 1
    assert summary["대조 건수"] == 0
    # 집계 실패를 "기존이 비워 둔 자리" 로 흘려보내면 안 된다.
    assert summary["신규에만 있음"] == 0


def test_one_sided_keys_are_counted_by_direction() -> None:
    """기존이 비워 둔 자리와 신규가 놓친 자리는 뜻이 정반대다."""
    calculated = pd.concat(
        [_calculated(100.0), _calculated(50.0, 제품정보="Product-B")], ignore_index=True
    )

    summary = summarize_comparison(_compare(_core(_plan_row(100.0)), calculated))

    assert summary["대조 건수"] == 1
    assert summary["신규에만 있음"] == 1
    assert summary["기존에만 있음"] == 0


def test_zero_legacy_value_is_counted_apart_from_a_ratio_breach() -> None:
    """기존값 0 은 비율이 없다. 통과로 세면 안 되고 허용 초과와 뭉쳐도 안 된다."""
    comparison = _compare(_core(_plan_row(0.0)), _calculated(5.0))
    summary = summarize_comparison(comparison)

    assert comparison["차이"].iloc[0] == 5.0
    assert pd.isna(comparison["차이율"].iloc[0])
    assert summary["기존 0·신규 있음"] == 1
    assert summary["허용 초과"] == 0
    assert summary["최대 차이율"] is None


def test_grain_follows_the_pkg_plan_business_key() -> None:
    """기존값이 한 번 기록되는 단위는 계약의 계획 업무 키다. 키가 늘면 대조도 따라간다."""
    assert legacy_grain(CONTRACT) == [*CONTRACT.derived_keys["RQ_PKG_PLAN"], "WF 구분"]
    assert COMPARISON_KEYS == ["생산계획년월", "제품정보", "Stack", "WF 구분"]


def test_plan_rows_that_differ_only_by_pack_code_are_summed_in_the_grain() -> None:
    """Pack Code 가 업무 키가 되면 두 줄은 각각의 그레인이라 대조 키에서 더해진다.

    승격 전에는 같은 그레인 안에서 값이 갈린 것으로 보여 `값 불일치` 가 되고 기존값이
    비워졌다 — 대조에서 통째로 빠지는 자리다.
    """
    core = _core(
        _plan_row(100.0, **{"Pack Code": "PACK-1"}),
        _plan_row(60.0, **{"Pack Code": "PACK-2"}),
    )

    comparison = _compare(core, _calculated(160.0))

    assert len(comparison) == 1
    assert comparison["기존값"].iloc[0] == 160.0
    assert bool(comparison["값 불일치"].iloc[0]) is False
    assert summarize_comparison(comparison)["값 불일치"] == 0
