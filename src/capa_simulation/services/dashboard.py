# Purpose: HOME의 생산계획·Wafer 부하량·Bottleneck 순위와 Capa 요약 데이터를 집계한다.

import pandas as pd

from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.load_calculator import (
    calculate_density_load,
    calculate_wafer_load,
)

PRODUCTION_DETAIL_DIMENSIONS = ["제품정보", "Stack"]


def build_production_dashboard(
    plan: pd.DataFrame,
    density_data: pd.DataFrame,
    display_order: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build mass-production Density totals and product/stack PKG Plan detail."""
    density = calculate_density_load(plan, density_data)
    production_class = density["양산구분"].astype("string").str.strip()
    density = density.loc[production_class.eq("양산")].copy()
    if density.empty:
        return (
            pd.DataFrame(columns=["생산계획년월", "부하량", "년월"]),
            pd.DataFrame(columns=PRODUCTION_DETAIL_DIMENSIONS),
        )
    monthly = (
        density.groupby("생산계획년월", as_index=False, dropna=False)[["물량"]]
        .sum()
        .rename(columns={"물량": "부하량"})
        .sort_values("생산계획년월")
        .reset_index(drop=True)
    )
    monthly["년월"] = monthly["생산계획년월"].map(_month_label)

    production_plan = plan.copy()
    production_plan["양산구분"] = production_plan["양산구분"].astype("string").str.strip()
    for column in PRODUCTION_DETAIL_DIMENSIONS:
        production_plan[column] = production_plan[column].astype("string").str.strip()
    production_plan["생산계획년월"] = pd.to_numeric(
        production_plan["생산계획년월"], errors="coerce"
    ).astype("Int64")
    production_plan["생산수량"] = pd.to_numeric(
        production_plan["생산수량"], errors="coerce"
    ).fillna(0.0)
    production_plan = production_plan.loc[production_plan["양산구분"].eq("양산")]
    grouped_detail = production_plan.groupby(
        ["생산계획년월", *PRODUCTION_DETAIL_DIMENSIONS],
        as_index=False,
        dropna=False,
    )["생산수량"].sum()
    detail = grouped_detail.pivot(
        index=PRODUCTION_DETAIL_DIMENSIONS,
        columns="생산계획년월",
        values="생산수량",
    ).reset_index()
    detail.columns.name = None
    raw_month_columns = [
        column for column in detail.columns if column not in PRODUCTION_DETAIL_DIMENSIONS
    ]
    detail = detail.rename(columns={month: _month_label(int(month)) for month in raw_month_columns})
    month_columns = [_month_label(int(month)) for month in sorted(raw_month_columns)]
    detail = detail[[*PRODUCTION_DETAIL_DIMENSIONS, *month_columns]]
    detail = apply_display_order(detail, display_order, "부하량", "PKG PLAN")
    return monthly, detail


def build_monthly_wafer_load(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> pd.DataFrame:
    """Build monthly Wafer load in sheets for the complete production plan."""
    if plan.empty:
        return pd.DataFrame(columns=["생산계획년월", "Wafer 부하량", "년월"])
    return build_monthly_wafer_load_from_load(calculate_wafer_load(plan, yield_data, chip_qty))


def build_monthly_wafer_load_from_load(wafer: pd.DataFrame) -> pd.DataFrame:
    """Aggregate a precomputed detailed Wafer load by month."""
    required = ["생산계획년월", "물량"]
    missing = [column for column in required if column not in wafer.columns]
    if missing:
        raise ValueError(f"Wafer 부하량 필수 컬럼이 없습니다: {', '.join(missing)}")
    if wafer.empty:
        return pd.DataFrame(columns=["생산계획년월", "Wafer 부하량", "년월"])
    monthly = (
        wafer.groupby("생산계획년월", as_index=False, dropna=False)[["물량"]]
        .sum()
        .rename(columns={"물량": "Wafer 부하량"})
        .sort_values("생산계획년월")
        .reset_index(drop=True)
    )
    monthly["년월"] = monthly["생산계획년월"].map(_month_label)
    return monthly


def build_production_lob_summary(
    monthly_density: pd.DataFrame,
    monthly_wafer: pd.DataFrame,
    monthly_bottlenecks: pd.DataFrame,
) -> pd.DataFrame:
    """Combine Density, Wafer load, and bottleneck-adjusted Wafer capacity."""
    result = monthly_density[["생산계획년월", "년월", "부하량"]].merge(
        monthly_wafer[["생산계획년월", "Wafer 부하량"]],
        on="생산계획년월",
        how="left",
        validate="one_to_one",
    )
    result = result.merge(
        monthly_bottlenecks[["생산계획년월", "확보율"]],
        on="생산계획년월",
        how="left",
        validate="one_to_one",
    )
    result["Wafer Capa"] = result["Wafer 부하량"] * result["확보율"]
    return result


def build_monthly_bottlenecks(
    securement_rate: pd.DataFrame,
    included_processes: list[str] | None = None,
) -> pd.DataFrame:
    """Select the lowest valid securement-rate process for every month."""
    ranking = build_monthly_bottleneck_ranking(securement_rate, included_processes)
    return build_monthly_bottlenecks_from_ranking(ranking)


def build_monthly_bottleneck_ranking(
    securement_rate: pd.DataFrame,
    included_processes: list[str] | None = None,
) -> pd.DataFrame:
    """Normalize and rank each month's valid processes once for all HOME views."""
    required = ["생산계획년월", "공정", "확보율"]
    missing = [column for column in required if column not in securement_rate.columns]
    if missing:
        raise ValueError(f"확보율 필수 컬럼이 없습니다: {', '.join(missing)}")
    detail_columns = [
        column for column in ("가용대수", "소요대수") if column in securement_rate.columns
    ]
    prepared = securement_rate[[*required, *detail_columns]].copy()
    for column in ["확보율", *detail_columns]:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    prepared["공정"] = prepared["공정"].astype("string").str.strip()
    prepared = prepared.dropna(subset=["생산계획년월", "공정", "확보율"])
    if included_processes is not None:
        prepared = prepared.loc[prepared["공정"].isin(included_processes)]
    prepared = prepared.sort_values(["생산계획년월", "확보율", "공정"], kind="stable").reset_index(
        drop=True
    )
    prepared["순위"] = prepared.groupby("생산계획년월").cumcount() + 1
    return prepared


def build_monthly_bottlenecks_from_ranking(ranking: pd.DataFrame) -> pd.DataFrame:
    """Select monthly Top 1 from an already normalized bottleneck ranking."""
    required = ["생산계획년월", "공정", "확보율", "순위"]
    missing = [column for column in required if column not in ranking.columns]
    if missing:
        raise ValueError(f"B/N 순위 필수 컬럼이 없습니다: {', '.join(missing)}")
    prepared = ranking.loc[ranking["순위"].eq(1), required[:-1]].copy().reset_index(drop=True)
    prepared["년월"] = prepared["생산계획년월"].map(_month_label).astype("string")
    prepared["축레이블"] = prepared["년월"].str.cat(prepared["공정"], sep="<br>")
    return prepared


def build_bottleneck_capacity(
    monthly_density: pd.DataFrame,
    monthly_bottlenecks: pd.DataFrame,
) -> pd.DataFrame:
    """Convert monthly bottleneck securement rates to Density capacity."""
    density_required = ["생산계획년월", "부하량", "년월"]
    bottleneck_required = ["생산계획년월", "공정", "확보율"]
    for data, required, label in (
        (monthly_density, density_required, "월별 부하량"),
        (monthly_bottlenecks, bottleneck_required, "월별 B/N"),
    ):
        missing = [column for column in required if column not in data.columns]
        if missing:
            raise ValueError(f"{label} 필수 컬럼이 없습니다: {', '.join(missing)}")

    result = monthly_density[density_required].merge(
        monthly_bottlenecks[bottleneck_required],
        on="생산계획년월",
        how="left",
        validate="one_to_one",
    )
    result["B/N Capa"] = result["부하량"] * result["확보율"]
    return result


def build_monthly_bottleneck_top5(
    securement_rate: pd.DataFrame,
    monthly_density: pd.DataFrame,
    included_processes: list[str] | None = None,
    monthly_wafer: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return each month's five lowest-rate processes and converted capacity."""
    ranking = build_monthly_bottleneck_ranking(securement_rate, included_processes)
    return build_monthly_bottleneck_top5_from_ranking(
        ranking,
        monthly_density,
        monthly_wafer=monthly_wafer,
    )


def build_monthly_bottleneck_top5_from_ranking(
    ranking: pd.DataFrame,
    monthly_density: pd.DataFrame,
    monthly_wafer: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build Top 5 capacity output from one shared monthly ranking."""
    required = ["생산계획년월", "공정", "확보율", "순위"]
    missing = [column for column in required if column not in ranking.columns]
    if missing:
        raise ValueError(f"B/N 순위 필수 컬럼이 없습니다: {', '.join(missing)}")
    prepared = ranking.loc[ranking["순위"].le(5), required].copy()
    density = monthly_density[["생산계획년월", "부하량"]].copy()
    result = prepared.merge(
        density,
        on="생산계획년월",
        how="inner",
        validate="many_to_one",
    )
    result["B/N Capa"] = result["부하량"] * result["확보율"]
    if monthly_wafer is not None:
        wafer_required = ["생산계획년월", "Wafer 부하량"]
        wafer_missing = [column for column in wafer_required if column not in monthly_wafer.columns]
        if wafer_missing:
            raise ValueError(f"월별 Wafer 필수 컬럼이 없습니다: {', '.join(wafer_missing)}")
        result = result.merge(
            monthly_wafer[wafer_required],
            on="생산계획년월",
            how="left",
            validate="many_to_one",
        )
        result["Wafer Capa"] = result["Wafer 부하량"] * result["확보율"]
    result["년월"] = result["생산계획년월"].map(_month_label)
    return result.reset_index(drop=True)


def build_monthly_bottleneck_details(
    securement_rate: pd.DataFrame,
    monthly_wafer: pd.DataFrame,
    included_processes: list[str] | None = None,
    *,
    rank_limit: int,
) -> pd.DataFrame:
    """Return each month's lowest-rate processes with equipment and Wafer Capa."""
    required = ["생산계획년월", "공정", "가용대수", "소요대수", "확보율"]
    missing = [column for column in required if column not in securement_rate.columns]
    if missing:
        raise ValueError(f"확보율 필수 컬럼이 없습니다: {', '.join(missing)}")
    ranking = build_monthly_bottleneck_ranking(securement_rate, included_processes)
    return build_monthly_bottleneck_details_from_ranking(
        ranking,
        monthly_wafer,
        rank_limit=rank_limit,
    )


def build_monthly_bottleneck_details_from_ranking(
    ranking: pd.DataFrame,
    monthly_wafer: pd.DataFrame,
    *,
    rank_limit: int,
) -> pd.DataFrame:
    """Build the lowest-rate equipment details from one shared monthly ranking.

    `rank_limit`은 화면이 보여줄 순위 상한이다. 그 달의 유효 공정이 상한보다 적으면
    있는 만큼만 나온다.
    """
    if rank_limit < 1:
        raise ValueError("B/N 상세 순위 상한은 1 이상이어야 합니다.")
    required = ["생산계획년월", "공정", "가용대수", "소요대수", "확보율", "순위"]
    missing = [column for column in required if column not in ranking.columns]
    if missing:
        raise ValueError(f"B/N 순위 필수 컬럼이 없습니다: {', '.join(missing)}")
    prepared = ranking.loc[ranking["순위"].le(rank_limit), required].copy()

    wafer_required = ["생산계획년월", "Wafer 부하량"]
    wafer_missing = [column for column in wafer_required if column not in monthly_wafer.columns]
    if wafer_missing:
        raise ValueError(f"월별 Wafer 필수 컬럼이 없습니다: {', '.join(wafer_missing)}")
    result = prepared.merge(
        monthly_wafer[wafer_required],
        on="생산계획년월",
        how="left",
        validate="many_to_one",
    )
    result["Wafer Capa"] = result["Wafer 부하량"] * result["확보율"]
    result["년월"] = result["생산계획년월"].map(_month_label)
    return result.reset_index(drop=True)


def _month_label(month: int | float) -> str:
    numeric_month = int(month)
    return f"{numeric_month // 100 % 100:02d}.{numeric_month % 100:02d}"
