# Purpose: Daily WIP history contract and standard-Capa comparison helpers.

"""Daily WIP history contract and standard-Capa comparison helpers."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import cast

import pandas as pd

from capa_simulation.services.frame_contracts import (
    assert_one_demand_basis_per_process,
    normalize_demand_basis,
)

WIP_ROUTE_COLUMNS = ["공정", "STEP_SEQ", "제품정보", "소요기준"]
WIP_HISTORY_COLUMNS = [
    "일자",
    *WIP_ROUTE_COLUMNS,
    "보유 재공",
    "유입량",
    "Flow량",
    "일 표준 가능량",
    "표준 대비 Gap",
    "Flow 충족률",
    "상태",
    "시점",
]
DAILY_STANDARD_COLUMNS = [
    "일자",
    "공정",
    "소요기준",
    "제품정보",
    "일 표준 가능량",
]
# 누락 검사는 반드시 텍스트 연결 키에만 적용한다. 수치 컬럼까지 함께 검사하면
# 가용대수·일 표준 가능량이 비어 있는 주차가 `표준 미설정`이 아니라 예외로 죽는다.
WEEKLY_TARGET_TEXT_KEYS = ["Weeknum", "공정", "소요기준", "제품정보"]
DAILY_STANDARD_TEXT_KEYS = ["공정", "소요기준", "제품정보"]

_STEP_PATTERN = re.compile(r"(?:^|[^A-Z0-9])(?P<prefix>[PT])(?P<major>\d+)(?:-(?P<minor>\d+))?$")


def step_sort_key(value: object) -> tuple[int, int, int, int, str]:
    """Sort route codes by P then T and by every numeric segment."""
    normalized = str(value).strip().upper()
    matched = _STEP_PATTERN.search(normalized)
    if matched is None:
        return (2, 0, 0, 0, normalized)
    prefix_order = 0 if matched.group("prefix") == "P" else 1
    major = int(matched.group("major"))
    minor_text = matched.group("minor")
    has_minor = 1 if minor_text is not None else 0
    minor = int(minor_text) if minor_text is not None else -1
    return (prefix_order, major, has_minor, minor, normalized)


def build_wip_route_scope(required_equipment: pd.DataFrame) -> pd.DataFrame:
    """Return unique process/STEP/product routes suitable for WIP DB queries."""
    missing = [column for column in WIP_ROUTE_COLUMNS if column not in required_equipment.columns]
    if missing:
        raise ValueError(f"재공 경로 필수 컬럼이 없습니다: {', '.join(missing)}")

    result = required_equipment[WIP_ROUTE_COLUMNS].copy()
    for column in WIP_ROUTE_COLUMNS:
        result[column] = result[column].astype("string").str.strip()
    result["소요기준"] = normalize_demand_basis(result["소요기준"])
    if any(
        result[column].isna().any() or result[column].eq("").any() for column in WIP_ROUTE_COLUMNS
    ):
        raise ValueError("재공 경로의 공정·STEP·제품·소요기준에는 누락값이 없어야 합니다.")

    assert_one_demand_basis_per_process(result, "재공 경로")

    result = result.drop_duplicates().reset_index(drop=True)
    result["__step_sort"] = result["STEP_SEQ"].map(step_sort_key)
    return result.sort_values(
        ["__step_sort", "공정", "제품정보"],
        kind="stable",
        ignore_index=True,
    ).drop(columns="__step_sort")


def processes_in_step_order(routes: pd.DataFrame) -> list[str]:
    """Return process filter options ordered by their earliest route STEP."""
    prepared = build_wip_route_scope(routes)
    return prepared["공정"].drop_duplicates().astype(str).tolist()


def aggregate_weekly_product_standard(weekly_target: pd.DataFrame) -> pd.DataFrame:
    """Collapse production types into one process/product standard using the existing formula."""
    required = [
        "Weeknum",
        "주차시작일",
        "주차종료일",
        "생산계획년월",
        "공정",
        "소요기준",
        "제품정보",
        "원수요_부하량",
        "STEP_소요대수",
        "RUN_DAY",
        "가용대수",
    ]
    missing = [column for column in required if column not in weekly_target.columns]
    if missing:
        raise ValueError(f"표준 목표 Capa 필수 컬럼이 없습니다: {', '.join(missing)}")
    if weekly_target.empty:
        return pd.DataFrame(
            columns=[
                *required[:7],
                "원수요_부하량",
                "STEP_소요대수",
                "공정 유효 Capa",
                "RUN_DAY",
                "가용대수",
                "일 표준 가능량",
            ]
        )

    result = weekly_target[required].copy()
    for column in ("Weeknum", "공정", "소요기준", "제품정보"):
        result[column] = result[column].astype("string").str.strip()
    result["소요기준"] = normalize_demand_basis(result["소요기준"])
    if any(
        result[column].isna().any() or result[column].eq("").any()
        for column in WEEKLY_TARGET_TEXT_KEYS
    ):
        raise ValueError("표준 목표 Capa의 주차·공정·제품 연결 키에 누락값이 있습니다.")

    for column in ("원수요_부하량", "STEP_소요대수", "RUN_DAY"):
        numeric = pd.to_numeric(result[column], errors="coerce")
        if numeric.isna().any():
            raise ValueError(f"표준 목표 Capa의 {column}에 숫자가 아닌 값이 있습니다.")
        result[column] = numeric.astype("float64")
    if result["원수요_부하량"].lt(0).any() or result["STEP_소요대수"].lt(0).any():
        raise ValueError("표준 목표 Capa의 부하량과 소요대수는 0 이상이어야 합니다.")
    if result["RUN_DAY"].le(0).any():
        raise ValueError("표준 목표 Capa의 RUN_DAY는 0보다 커야 합니다.")

    raw_availability = result["가용대수"]
    availability = pd.to_numeric(raw_availability, errors="coerce")
    invalid_availability = raw_availability.notna() & availability.isna()
    if invalid_availability.any() or availability.dropna().lt(0).any():
        raise ValueError("표준 목표 Capa의 가용대수는 0 이상의 숫자 또는 빈값이어야 합니다.")
    result["가용대수"] = availability.astype("float64")

    group_keys = [
        "Weeknum",
        "주차시작일",
        "주차종료일",
        "생산계획년월",
        "공정",
        "소요기준",
        "제품정보",
    ]
    for column in ("RUN_DAY", "가용대수"):
        counts = result.groupby(group_keys, dropna=False)[column].nunique(dropna=True)
        if counts.gt(1).any():
            examples = counts.loc[counts.gt(1)].index.tolist()[:5]
            raise ValueError(f"제품 표준 Capa의 {column} 연결값이 서로 다릅니다: {examples}")

    grouped = result.groupby(group_keys, as_index=False, dropna=False).agg(
        원수요_부하량=("원수요_부하량", "sum"),
        STEP_소요대수=("STEP_소요대수", "sum"),
        RUN_DAY=("RUN_DAY", "first"),
        가용대수=("가용대수", "first"),
    )
    grouped["공정 유효 Capa"] = grouped["원수요_부하량"].div(
        grouped["STEP_소요대수"].where(grouped["STEP_소요대수"].gt(0))
    )
    grouped["일 표준 가능량"] = (
        grouped["공정 유효 Capa"].div(grouped["RUN_DAY"]) * grouped["가용대수"]
    )
    return grouped[
        [
            *group_keys,
            "원수요_부하량",
            "STEP_소요대수",
            "공정 유효 Capa",
            "RUN_DAY",
            "가용대수",
            "일 표준 가능량",
        ]
    ].sort_values(["주차시작일", "공정", "제품정보"], ignore_index=True)


def expand_weekly_product_standard_to_daily(
    weekly_target: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Expand weekly standards across the exact requested date window, day by day."""
    if start_date > end_date:
        raise ValueError("조회 시작일은 종료일보다 늦을 수 없습니다.")
    weekly = aggregate_weekly_product_standard(weekly_target)
    if weekly.empty:
        return pd.DataFrame(columns=DAILY_STANDARD_COLUMNS)

    calendar = pd.DataFrame({"일자": pd.date_range(start_date, end_date, freq="D")})
    iso = calendar["일자"].dt.isocalendar()
    calendar["Weeknum"] = (
        iso["year"].mod(100).astype("int64").astype(str).str.zfill(2)
        + "-W"
        + iso["week"].astype("int64").astype(str).str.zfill(2)
    )
    # Weeknum 하나에 귀속 달은 하나뿐이므로 `생산계획년월` 은 `weekly` 쪽에서 따라온다.
    # 여기서 달을 다시 만들면 폐기된 「월요일이 속한 달」 규칙을 재구현하게 되고, 정본
    # (`iso_week_calendar.owning_month`, 일수가 더 많은 달)과 갈리는 연 5주는 INNER 조인이
    # 통째로 버린다. 그 7일은 화면에 `표준 미설정` 으로 남아 가용대수 탓으로 오지목된다.
    expanded = calendar.merge(
        weekly,
        on="Weeknum",
        how="inner",
        validate="many_to_many",
    )
    expanded["일자"] = expanded["일자"].dt.date
    return expanded[DAILY_STANDARD_COLUMNS].sort_values(
        ["일자", "공정", "제품정보"],
        ignore_index=True,
    )


def build_wip_history_demo(
    routes: pd.DataFrame,
    daily_standard: pd.DataFrame,
    start_date: date,
    end_date: date,
    *,
    today: date | None = None,
) -> pd.DataFrame:
    """Build deterministic demo WIP until a production history provider is connected."""
    if start_date > end_date:
        raise ValueError("조회 시작일은 종료일보다 늦을 수 없습니다.")
    prepared_routes = build_wip_route_scope(routes)
    standards = _prepare_daily_standard(daily_standard)
    standard_map = {
        (
            cast(date, row["일자"]),
            str(row["공정"]),
            str(row["제품정보"]),
            str(row["소요기준"]),
        ): float(cast(float, row["일 표준 가능량"]))
        for row in cast(list[dict[str, object]], standards.to_dict("records"))
    }
    reference_day = today or date.today()
    rows: list[dict[str, object]] = []
    dates = [timestamp.date() for timestamp in pd.date_range(start_date, end_date, freq="D")]

    for route in cast(list[dict[str, object]], prepared_routes.to_dict("records")):
        process = str(route["공정"])
        step = str(route["STEP_SEQ"])
        product = str(route["제품정보"])
        basis = str(route["소요기준"])
        route_token = f"{process}|{step}|{product}|{basis}"
        first_standard = next(
            (
                value
                for key, value in standard_map.items()
                if key[1:] == (process, product, basis) and pd.notna(value) and value > 0
            ),
            80.0 + 120.0 * _stable_ratio(route_token, 0),
        )
        held_wip = first_standard * (0.65 + 0.75 * _stable_ratio(route_token, 2))

        for day_index, current_date in enumerate(dates):
            token = f"{route_token}|{current_date.isoformat()}"
            standard = standard_map.get((current_date, process, product, basis), float("nan"))
            scale = standard if pd.notna(standard) and standard > 0 else first_standard
            inflow = scale * (0.72 + 0.54 * _stable_ratio(token, 0))
            flow = scale * (0.70 + 0.48 * _stable_ratio(token, 2))
            if day_index > 0:
                held_wip = max(held_wip + inflow - flow, 0.0)

            if pd.isna(standard) or standard <= 0:
                status = "표준 미설정"
                gap = float("nan")
                realization = float("nan")
            else:
                gap = flow - standard
                realization = flow / standard
                status = "충족" if flow >= standard else "부족"
            rows.append(
                {
                    "일자": current_date,
                    "공정": process,
                    "STEP_SEQ": step,
                    "제품정보": product,
                    "소요기준": basis,
                    "보유 재공": round(held_wip, 2),
                    "유입량": round(inflow, 2),
                    "Flow량": round(flow, 2),
                    "일 표준 가능량": round(standard, 2) if pd.notna(standard) else float("nan"),
                    "표준 대비 Gap": round(gap, 2) if pd.notna(gap) else float("nan"),
                    "Flow 충족률": round(realization, 4) if pd.notna(realization) else float("nan"),
                    "상태": status,
                    "시점": "실적 샘플" if current_date <= reference_day else "전망 샘플",
                }
            )
    return pd.DataFrame(rows, columns=WIP_HISTORY_COLUMNS)


def _prepare_daily_standard(data: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in DAILY_STANDARD_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"일 표준 가능량 필수 컬럼이 없습니다: {', '.join(missing)}")
    result = data[DAILY_STANDARD_COLUMNS].copy()
    if result.empty:
        return result
    parsed_dates = pd.to_datetime(result["일자"], errors="coerce")
    if parsed_dates.isna().any():
        raise ValueError("일 표준 가능량의 일자는 유효한 날짜여야 합니다.")
    result["일자"] = parsed_dates.dt.date
    for column in ("공정", "소요기준", "제품정보"):
        result[column] = result[column].astype("string").str.strip()
    result["소요기준"] = normalize_demand_basis(result["소요기준"])
    if any(
        result[column].isna().any() or result[column].eq("").any()
        for column in DAILY_STANDARD_TEXT_KEYS
    ):
        raise ValueError("일 표준 가능량의 공정·제품·소요기준에는 누락값이 없어야 합니다.")
    raw_standard = result["일 표준 가능량"]
    numeric = pd.to_numeric(raw_standard, errors="coerce")
    invalid = raw_standard.notna() & numeric.isna()
    if invalid.any() or numeric.dropna().lt(0).any():
        raise ValueError("일 표준 가능량은 0 이상의 숫자 또는 빈값이어야 합니다.")
    result["일 표준 가능량"] = numeric.astype("float64")
    keys = ["일자", "공정", "제품정보", "소요기준"]
    duplicated = result.duplicated(keys, keep=False)
    if duplicated.any():
        examples = result.loc[duplicated, keys].drop_duplicates().head(5).to_dict("records")
        raise ValueError(f"일 표준 가능량의 연결 키가 중복되었습니다: {examples}")
    return result


def _stable_ratio(token: str, offset: int) -> float:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    value = int.from_bytes(digest[offset : offset + 2], byteorder="big", signed=False)
    return value / 65_535.0
