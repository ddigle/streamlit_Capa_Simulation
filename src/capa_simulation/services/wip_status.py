# Purpose: Daily WIP history contract and standard-Capa comparison helpers.

"""Daily WIP history contract and standard-Capa comparison helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import date
from typing import cast

import pandas as pd

from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.display_order_scopes import (
    PAGE_STANDARD_TARGET,
    TAB_TARGET_CAPACITY,
)
from capa_simulation.services.frame_checks import assert_unique_keys
from capa_simulation.services.frame_contracts import (
    assert_one_demand_basis_per_process,
    normalize_demand_basis,
    require_columns,
)
from capa_simulation.services.standard_target_capacity import (
    prepare_standard_target_required_equipment,
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
    require_columns(required_equipment, WIP_ROUTE_COLUMNS, "재공 경로")

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


def products_in_display_order(routes: pd.DataFrame, display_order: pd.DataFrame) -> list[str]:
    """경로의 제품을 표준 목표와 같은 공용 표시순서(`표준 목표 › 목표 Capa`)로 늘어놓는다."""
    products = routes[["제품정보"]].drop_duplicates().reset_index(drop=True)
    ordered = apply_display_order(
        products, display_order, PAGE_STANDARD_TARGET, TAB_TARGET_CAPACITY
    )
    return ordered["제품정보"].astype(str).tolist()


@dataclass(frozen=True)
class WipRouteChoices:
    """시나리오 소요대수에서만 나오는 재공 화면 준비물 — 표준 목표 규칙을 적용한 소요대수, 경로
    범위, 공정·제품 선택지(경로가 없으면 둘 다 빈 값)."""

    required_equipment: pd.DataFrame
    routes: pd.DataFrame
    processes: tuple[str, ...]
    products: tuple[str, ...]

    def copy(self) -> WipRouteChoices:
        """표 사본을 든 새 묶음. 기억해 둔 묶음을 받은 쪽이 고쳐도 다음 회차가 오염되지 않는다."""
        return replace(
            self, required_equipment=self.required_equipment.copy(), routes=self.routes.copy()
        )


def prepare_wip_route_choices(
    required_equipment: pd.DataFrame, display_order: pd.DataFrame
) -> WipRouteChoices:
    """재공 화면이 시나리오 소요대수와 공용 표시순서에서만 만드는 준비물. 입력 둘이 같으면 결과도
    같다(오늘 날짜·가용대수·재공 실적은 읽지 않는다)."""
    prepared = prepare_standard_target_required_equipment(required_equipment)
    routes = build_wip_route_scope(prepared)
    if routes.empty:
        return WipRouteChoices(prepared, routes, (), ())
    return WipRouteChoices(
        prepared,
        routes,
        tuple(processes_in_step_order(routes)),
        tuple(products_in_display_order(routes, display_order)),
    )


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
    require_columns(weekly_target, required, "표준 목표 Capa")
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
    require_columns(data, DAILY_STANDARD_COLUMNS, "일 표준 가능량")
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
    assert_unique_keys(result, keys, "일 표준 가능량의 연결 키가")
    return result


def _stable_ratio(token: str, offset: int) -> float:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    value = int.from_bytes(digest[offset : offset + 2], byteorder="big", signed=False)
    return value / 65_535.0
