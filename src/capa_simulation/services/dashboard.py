import pandas as pd

from capa_simulation.services.load_calculator import calculate_density_load

PRODUCTION_DETAIL_DIMENSIONS = ["제품정보", "Stack"]


def build_production_dashboard(
    plan: pd.DataFrame,
    density_data: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build mass-production Density totals and product/stack detail in 100M Gb."""
    density = calculate_density_load(plan, density_data)
    production_class = density["양산구분"].astype("string").str.strip()
    density = density.loc[production_class.eq("양산")].copy()
    if density.empty:
        return (
            pd.DataFrame(columns=["생산계획년월", "부하량", "년월"]),
            pd.DataFrame(columns=PRODUCTION_DETAIL_DIMENSIONS),
        )
    monthly = (
        density.groupby("생산계획년월", as_index=False, dropna=False)["물량"]
        .sum()
        .rename(columns={"물량": "부하량"})
        .sort_values("생산계획년월")
        .reset_index(drop=True)
    )
    monthly["년월"] = monthly["생산계획년월"].map(_month_label)

    grouped_detail = density.groupby(
        ["생산계획년월", *PRODUCTION_DETAIL_DIMENSIONS],
        as_index=False,
        dropna=False,
    )["물량"].sum()
    detail = grouped_detail.pivot(
        index=PRODUCTION_DETAIL_DIMENSIONS,
        columns="생산계획년월",
        values="물량",
    ).reset_index()
    detail.columns.name = None
    raw_month_columns = [
        column for column in detail.columns if column not in PRODUCTION_DETAIL_DIMENSIONS
    ]
    detail = detail.rename(columns={month: _month_label(int(month)) for month in raw_month_columns})
    month_columns = [_month_label(int(month)) for month in sorted(raw_month_columns)]
    return monthly, detail[[*PRODUCTION_DETAIL_DIMENSIONS, *month_columns]]


def build_monthly_bottlenecks(
    securement_rate: pd.DataFrame,
    included_processes: list[str] | None = None,
) -> pd.DataFrame:
    """Select the lowest valid securement-rate process for every month."""
    required = ["생산계획년월", "공정", "확보율"]
    missing = [column for column in required if column not in securement_rate.columns]
    if missing:
        raise ValueError(f"확보율 필수 컬럼이 없습니다: {', '.join(missing)}")
    prepared = securement_rate[required].copy()
    prepared["확보율"] = pd.to_numeric(prepared["확보율"], errors="coerce")
    prepared = prepared.dropna(subset=["확보율"])
    prepared["공정"] = prepared["공정"].astype("string").str.strip()
    if included_processes is not None:
        prepared = prepared.loc[prepared["공정"].isin(included_processes)]
    prepared = prepared.sort_values(
        ["생산계획년월", "확보율", "공정"], kind="stable"
    ).drop_duplicates("생산계획년월", keep="first")
    prepared = prepared.reset_index(drop=True)
    prepared["년월"] = prepared["생산계획년월"].map(_month_label)
    prepared["축레이블"] = prepared["년월"] + "<br>" + prepared["공정"]
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


def _month_label(month: int | float) -> str:
    numeric_month = int(month)
    return f"{numeric_month // 100 % 100:02d}.{numeric_month % 100:02d}"
