# Purpose: HOME 제품별 비중 행의 제품×월 수량·색 칸 배정·칸별 비중을 계산한다.

"""제품별 비중.

HOME `Capa LOB 현황` 맨 아래 행은 칸마다 제품별 비중을 도넛 하나로 그린다. 단위는 둘이다.

- **Wafer**: 분모는 같은 표의 `Wafer 계획` 행 값이다. 그 행은 양산구분을 가리지 않은 전체
  계획의 Wafer 부하량이므로, 제품별 Wafer 부하량(양산+ER 합산)을 더하면 정확히 그 값이 된다.
  EDP 포함 여부·선행 반영도 그 행과 같은 것을 받는다.
- **PKG**: 분모는 그 달의 PKG 생산수량 전체다(양산+ER 합산, EDP 는 같은 토글).

**양산구분을 나누지 않는다.** 같은 제품의 양산과 ER 을 더한 뒤 비중을 낸다(사용자 지정).

색은 **제품을 따라간다.** 칸 배정은 화면 전체에서 한 번 정하고 달·단위·EDP 토글이 바뀌어도
같은 제품은 같은 칸(=같은 색)이다. 그래서 칸을 정하는 제품 목록은 EDP 를 **포함한** 계획에서
낸다 — EDP 를 끈 화면에서 EDP 제품이 빠져도 남은 제품의 색이 앞으로 당겨지지 않는다.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import NamedTuple

import pandas as pd

from capa_simulation.services.display_order import DisplayOrderInput, apply_display_order
from capa_simulation.services.display_order_scopes import PAGE_PLAN, TAB_PKG_PLAN
from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.month_columns import month_label

PRODUCT_SHARE_BASIS_WAFER = "Wafer"
PRODUCT_SHARE_BASIS_PKG = "PKG"
PRODUCT_SHARE_BASES = (PRODUCT_SHARE_BASIS_WAFER, PRODUCT_SHARE_BASIS_PKG)

# 단위마다 읽는 컬럼. 둘 다 원본 계약 이름이다 — `Wafer 부하량` 은 `Wafer 계획` 행이 읽는
# 컬럼과 같아 선행 반영 함수(`apply_advance_to_wafer`)를 그대로 쓸 수 있다.
PRODUCT_SHARE_VALUE_COLUMNS: Mapping[str, str] = {
    PRODUCT_SHARE_BASIS_WAFER: "Wafer 부하량",
    PRODUCT_SHARE_BASIS_PKG: "생산수량",
}
PRODUCT_VOLUME_COLUMNS = ("생산계획년월", "제품정보", "Wafer 부하량", "생산수량")

# 한 도넛이 갖는 조각 수의 상한이자 색 칸 수. 도넛은 6조각을 넘으면 비중이 읽히지 않고,
# 범례도 구분 칸(260×100px)에 두 줄 세 칸까지만 들어간다. 제품이 이보다 많으면 물량이 작은
# 제품을 `기타` 하나로 접어 **이름 있는 칸을 하나 줄인다**(5 + 기타).
PRODUCT_SHARE_SLOT_COUNT = 6
OTHER_PRODUCT_LABEL = "기타"


class ProductSlots(NamedTuple):
    """화면 전체에서 한 번 정한 제품 차례와 색 칸.

    `order` 는 조각·범례 차례(표시순서)이고 `slot` 은 색 칸 번호다. `기타` 로 접힌 제품은
    `folded` 에만 있다.
    """

    order: tuple[str, ...]
    slot: Mapping[str, int]
    folded: frozenset[str]

    def key_of(self, product: str) -> str:
        """조각 이름. 접힌 제품은 `기타` 로 모인다."""
        return OTHER_PRODUCT_LABEL if product in self.folded else product


class ProductShareSlice(NamedTuple):
    """도넛 조각 하나. `members` 는 `기타` 조각에 든 제품과 각 수량이다."""

    product: str
    value: float
    share: float
    slot: int | None
    members: tuple[tuple[str, float], ...] = ()


class ProductShareCell(NamedTuple):
    """월 축 칸 하나의 도넛. `total` 이 비중의 분모다."""

    label: str
    total: float
    slices: tuple[ProductShareSlice, ...]


def empty_product_volume() -> pd.DataFrame:
    """제품이 하나도 없을 때의 정상 모양."""
    return pd.DataFrame(
        {
            "생산계획년월": pd.Series(dtype="Int64"),
            "제품정보": pd.Series(dtype="string"),
            "Wafer 부하량": pd.Series(dtype="float64"),
            "생산수량": pd.Series(dtype="float64"),
        }
    )


def _normalized(frame: pd.DataFrame, value_column: str) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "생산계획년월": pd.to_numeric(frame["생산계획년월"], errors="coerce").astype("Int64"),
            "제품정보": frame["제품정보"].astype("string").str.strip(),
            value_column: pd.to_numeric(frame[value_column], errors="coerce").astype("float64"),
        }
    )
    return result.dropna(subset=["생산계획년월", "제품정보"])


def build_product_volume(plan: pd.DataFrame, wafer_load: pd.DataFrame) -> pd.DataFrame:
    """제품×월 Wafer 부하량과 PKG 생산수량. **양산구분을 나누지 않고 더한다.**

    Wafer 는 `Wafer 계획` 행과 같은 상세 환산 결과(`물량`)에서 묶는다. 그래야 제품별 합이
    그 행의 값과 한 치도 다르지 않다 — 기준정보가 없어 환산에서 빠진 계획 행은 두 쪽 모두에서
    빠진다. PKG 는 계획의 `생산수량` 을 그대로 묶는다.
    """
    require_columns(plan, ["생산계획년월", "제품정보", "생산수량"], "RQ_PKG_PLAN")
    require_columns(wafer_load, ["생산계획년월", "제품정보", "물량"], "Wafer 부하량")
    wafer = _normalized(wafer_load.rename(columns={"물량": "Wafer 부하량"}), "Wafer 부하량")
    pkg = _normalized(plan, "생산수량")
    keys = ["생산계획년월", "제품정보"]
    grouped_wafer = wafer.groupby(keys, as_index=False)["Wafer 부하량"].sum()
    grouped_pkg = pkg.groupby(keys, as_index=False)["생산수량"].sum()
    if grouped_wafer.empty and grouped_pkg.empty:
        return empty_product_volume()
    merged = grouped_pkg.merge(grouped_wafer, on=keys, how="outer")
    # 환산에서 빠진 제품은 Wafer 가 **0** 이다(결측이 아니다). `Wafer 계획` 행도 그 제품을
    # 더하지 않았으므로 비중 칸도 그 제품을 조각으로 두지 않는 것이 같은 뜻이다.
    merged["Wafer 부하량"] = merged["Wafer 부하량"].fillna(0.0)
    merged["생산수량"] = merged["생산수량"].fillna(0.0)
    result: pd.DataFrame = merged[list(PRODUCT_VOLUME_COLUMNS)].sort_values(keys)
    return result.reset_index(drop=True)


def past_product_volume(
    past_detail: pd.DataFrame,
    *,
    start_month: int,
    end_month: int,
    exclude_months: Collection[int],
) -> pd.DataFrame:
    """과거 구간의 제품×월 PKG 생산수량. **Wafer 는 결측이다.**

    과거 입력은 월별 `Wafer Total` 하나뿐이라 제품별 Wafer 를 알 수 없다. 0 으로 두면
    「그 달에 Wafer 가 없었다」로 읽히므로 결측으로 두고, Wafer 단위 도넛은 그 달을 비운다.
    DB 계산 결과가 있는 달(`exclude_months`)은 계산이 이긴다 — 다른 과거 병합과 같은 규칙이다.
    """
    if past_detail.empty:
        return empty_product_volume()
    frame = _normalized(past_detail, "생산수량")
    months = frame["생산계획년월"].astype("int64")
    frame = frame.loc[months.between(start_month, end_month) & ~months.isin(list(exclude_months))]
    if frame.empty:
        return empty_product_volume()
    grouped = frame.groupby(["생산계획년월", "제품정보"], as_index=False)[["생산수량"]].sum()
    grouped["Wafer 부하량"] = float("nan")
    return grouped[list(PRODUCT_VOLUME_COLUMNS)].reset_index(drop=True)


def assign_product_slots(
    volume: pd.DataFrame,
    display_order: DisplayOrderInput = None,
    *,
    slot_count: int = PRODUCT_SHARE_SLOT_COUNT,
) -> ProductSlots:
    """제품 차례와 색 칸을 정한다.

    차례는 `계획 세부수량` 표와 같다 — 제품명 순으로 세운 뒤 공용 표시순서(`PKG PLAN` 탭)를
    얹는다. 칸 수를 넘으면 **PKG 생산수량이 작은 제품부터** `기타` 로 접는다. 물량 순위는
    단위와 무관한 PKG 로 매긴다 — 단위를 바꿀 때 접히는 제품이 달라지면 색이 따라 바뀐다.

    `volume` 은 화면에 보이는 기간의 **EDP 포함** 수량이어야 한다(모듈 설명 참고). 수량이 0
    인 제품은 칸을 받지 않는다.
    """
    require_columns(volume, ["제품정보", "생산수량"], "제품별 수량")
    totals = (
        volume.assign(생산수량=pd.to_numeric(volume["생산수량"], errors="coerce").fillna(0.0))
        .groupby("제품정보")["생산수량"]
        .sum()
    )
    totals = totals.loc[totals > 0]
    if totals.empty:
        return ProductSlots(order=(), slot={}, folded=frozenset())
    ordered = apply_display_order(
        pd.DataFrame({"제품정보": sorted(str(name) for name in totals.index)}),
        display_order,
        PAGE_PLAN,
        TAB_PKG_PLAN,
    )["제품정보"].astype(str)
    products = list(ordered)
    folded: frozenset[str] = frozenset()
    if len(products) > slot_count:
        # 같은 물량이면 표시순서가 앞선 쪽이 남는다 — 순위가 동률에서 흔들리지 않게 한다.
        rank = {product: index for index, product in enumerate(products)}
        kept = sorted(products, key=lambda name: (-float(totals[name]), rank[name]))[
            : slot_count - 1
        ]
        folded = frozenset(products) - frozenset(kept)
    named = [product for product in products if product not in folded]
    return ProductSlots(
        order=tuple(named),
        slot={product: index for index, product in enumerate(named)},
        folded=folded,
    )


def _cell(
    label: str,
    values: pd.Series,
    slots: ProductSlots,
) -> ProductShareCell | None:
    """제품별 값(양수만)을 칸 차례대로 조각으로 만든다. 값이 없으면 칸을 비운다."""
    positive = values.loc[values > 0]
    if positive.empty:
        return None
    total = float(positive.sum())
    named: dict[str, float] = {}
    members: list[tuple[str, float]] = []
    for product, value in positive.items():
        key = slots.key_of(str(product))
        if key == OTHER_PRODUCT_LABEL:
            members.append((str(product), float(value)))
        elif key in slots.slot:
            named[key] = named.get(key, 0.0) + float(value)
        else:
            # 칸 배정에 없던 제품(배정 목록 밖에서 온 값)도 버리지 않는다. 버리면 비중 합이
            # 100% 가 아니게 된다. `기타` 로 모은다.
            members.append((str(product), float(value)))
    slices = [
        ProductShareSlice(product, named[product], named[product] / total, slots.slot[product])
        for product in slots.order
        if product in named
    ]
    if members:
        other = sum(value for _, value in members)
        slices.append(
            ProductShareSlice(
                OTHER_PRODUCT_LABEL,
                other,
                other / total,
                None,
                tuple(sorted(members, key=lambda item: -item[1])),
            )
        )
    return ProductShareCell(label=label, total=total, slices=tuple(slices))


def build_product_share_cells(
    volume: pd.DataFrame,
    basis: str,
    slots: ProductSlots,
    *,
    month_labels: Sequence[str],
    year_total_labels: Collection[str] = (),
) -> dict[str, ProductShareCell]:
    """월 축 라벨 → 도넛 칸. 그릴 것이 없는 칸은 빠진다.

    연간 Total 칸은 **그 해의 달 칸이 모두 그려질 때만** 그해 합으로 채운다. 한 달이라도
    비면(과거 구간의 Wafer) 그 합은 위 `Wafer 계획` Total 과 분모가 달라져 거짓 비중이 된다.
    """
    if basis not in PRODUCT_SHARE_VALUE_COLUMNS:
        raise ValueError(f"제품별 비중 단위가 올바르지 않습니다: {basis}")
    column = PRODUCT_SHARE_VALUE_COLUMNS[basis]
    require_columns(volume, ["생산계획년월", "제품정보", column], "제품별 수량")
    frame = volume.loc[volume[column].notna(), ["생산계획년월", "제품정보", column]].copy()
    frame["년월"] = [month_label(int(value)) for value in frame["생산계획년월"]]
    by_label = {
        str(label): group.groupby("제품정보")[column].sum()
        for label, group in frame.groupby("년월", sort=False)
    }
    totals = set(year_total_labels)
    cells: dict[str, ProductShareCell] = {}
    for label in month_labels:
        if label in totals or label not in by_label:
            continue
        cell = _cell(label, by_label[label], slots)
        if cell is not None:
            cells[label] = cell
    for total_label in totals:
        members = [
            label
            for label in month_labels
            if label not in totals and label.startswith(f"{total_label[:2]}.")
        ]
        if not members or any(label not in cells for label in members):
            continue
        year_values = pd.concat([by_label[label] for label in members]).groupby(level=0).sum()
        cell = _cell(total_label, year_values, slots)
        if cell is not None:
            cells[total_label] = cell
    return cells


def combine_product_volume(*frames: pd.DataFrame) -> pd.DataFrame:
    """계산 구간과 과거 구간의 제품별 수량을 잇는다. 빈 프레임은 건너뛴다.

    빈 프레임까지 `concat` 에 넣으면 pandas 가 결과 dtype 을 정하는 규칙이 바뀐다는 경고를
    낸다. 비어 있는 쪽은 더할 행이 없으므로 빼도 결과가 같다.
    """
    present = [frame[list(PRODUCT_VOLUME_COLUMNS)] for frame in frames if not frame.empty]
    if not present:
        return empty_product_volume()
    if len(present) == 1:
        return present[0].reset_index(drop=True)
    return pd.concat(present, ignore_index=True)
