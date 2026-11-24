# Purpose: HOME 제품별 비중 행의 제품×월 수량·색 칸 배정·칸별 비중을 계산한다.

"""제품별 비중.

HOME `Capa LOB 현황` 맨 아래 행은 칸마다 제품별 비중을 도넛 하나로 그린다. 단위는 둘이다.

- **Wafer**: 분모는 같은 표의 `Wafer 계획` 행 값이다. 그 행은 양산구분을 가리지 않은 전체
  계획의 Wafer 부하량이므로, 제품별 Wafer 부하량(양산+ER 합산)을 더하면 정확히 그 값이 된다.
  EDP 포함 여부·선행 반영도 그 행과 같은 것을 받는다. Dummy 계열(`Dummy` · `Top_Dummy`)을
  뺀 HOME 집계 기준도 같다 — 두 쪽이 같은 거른 상세 프레임
  (`dashboard.home_aggregation_wafer_load`)에서 묶인다.
- **PKG**: 분모는 그 달의 PKG 생산수량 전체다(양산+ER 합산, EDP 는 같은 토글).

**양산구분을 나누지 않는다.** 같은 제품의 양산과 ER 을 더한 뒤 비중을 낸다(사용자 지정).

색은 **제품을 따라간다.** 칸 배정은 화면 전체에서 한 번 정하고 달·단위·EDP 토글·Past Data
토글이 바뀌어도 같은 제품은 같은 칸(=같은 색)이다. 그래서 칸을 정하는 제품 목록은 EDP 를
**포함한** 계산 구간 계획이고, 과거 구간에만 있는 제품은 **그 뒤**에 칸을 받는다 — EDP 를 끄거나
Past Data 를 켜고 꺼도 계산 구간 제품의 색이 앞뒤로 밀리지 않는다.

**부품(`CUSTOM`)이 둘 이상인 제품은 부품마다 조각이다**(`services/product_parts` — 2026-11-23 보드
답 D1 (가) · D2 (가)). 조각 · 칸의 열쇠는 이름표 글(「DEMO_A (DEMO_CUSTOM_A)」, 부품이 하나뿐인
제품은 제품 이름)이고 부품은 다른 제품처럼 제 색 칸을 받는다 — 같은 제품의 부품은 차례로만 이웃이고,
칸이 넘치면 부품 단위로 `기타` 에 접힌다. 판정은 활성 리비전 계획 전체로 하고 수량 프레임의 `CUSTOM`
칸에 접힌 값으로 싣는다. `CUSTOM` 칸이 없는 수량 프레임은 모두 접힌 것으로 읽는다.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite
from typing import NamedTuple

import pandas as pd

from capa_simulation.services.display_order import DisplayOrderInput
from capa_simulation.services.display_order_scopes import PAGE_PLAN, TAB_PKG_PLAN
from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.product_parts import (
    PART_COLUMN,
    PART_NOT_SPLIT,
    apply_part_display_order,
    part_order_key,
    product_part_label,
    split_product_parts,
)

PRODUCT_SHARE_BASIS_WAFER = "Wafer"
PRODUCT_SHARE_BASIS_PKG = "PKG"
PRODUCT_SHARE_BASES = (PRODUCT_SHARE_BASIS_WAFER, PRODUCT_SHARE_BASIS_PKG)

# 단위마다 읽는 컬럼. 둘 다 원본 계약 이름이다 — `Wafer 부하량` 은 `Wafer 계획` 행이 읽는
# 컬럼과 같아 선행 반영 함수(`apply_advance_to_wafer`)를 그대로 쓸 수 있다.
PRODUCT_SHARE_VALUE_COLUMNS: Mapping[str, str] = {
    PRODUCT_SHARE_BASIS_WAFER: "Wafer 부하량",
    PRODUCT_SHARE_BASIS_PKG: "생산수량",
}
# `과거` 는 Past Data 로 채운 달의 행이다. 그 달의 PKG 는 `과거 계획 세부수량` 입력 그대로라 계산
# 구간(양산+ER)과 정의가 같다고 보장할 수 없다 — 칸에 표시하고 두 정의를 더하지 않는다. `CUSTOM` 은
# 화면 단위로 접은 부품이다(부품이 하나뿐인 제품은 빈 글자 — `product_parts.split_product_parts`).
PRODUCT_VOLUME_COLUMNS = (
    "생산계획년월",
    "제품정보",
    "Wafer 부하량",
    "생산수량",
    "과거",
    PART_COLUMN,
)

# 한 도넛이 갖는 조각 수의 상한이자 색 칸 수. 도넛은 6조각을 넘으면 비중이 읽히지 않고,
# 범례도 구분 칸(260×100px)에 두 줄 세 칸까지만 들어간다. 제품이 이보다 많으면 물량이 작은
# 제품을 `기타` 하나로 접어 **이름 있는 칸을 하나 줄인다**(5 + 기타).
PRODUCT_SHARE_SLOT_COUNT = 6
OTHER_PRODUCT_LABEL = "기타"
# 도넛 조각 안에 비중(%)을 적는 경계(2026-11-04 사용자 검수 home-28 — 「비중이 20% 가 넘는 영역은
# 퍼센트 표기」). 적는 글자(사사오입 정수 %)가 이 값을 넘는 조각만 적는다 — 글자로 「20%」 인 조각은
# 적지 않아 보이는 숫자가 늘 경계를 넘는다. 그보다 작은 조각은 지름 80px 도넛의 고리(약 17px)에
# 글자가 들어가지 않고, 정확한 비중은 hover 가 적는다.
SHARE_LABEL_MIN_PERCENT = 20


class ProductSlots(NamedTuple):
    """화면 전체에서 한 번 정한 제품 차례와 색 칸.

    `order` 는 조각·범례 차례(표시순서)이고 `slot` 은 색 칸 번호다. `기타` 로 접힌 제품은
    `folded` 에만 있다. 제품 이름은 이름표(`product_parts.product_part_label`)다 — 부품을 가른
    제품은 부품마다 하나다.
    """

    order: tuple[str, ...]
    slot: Mapping[str, int]
    folded: frozenset[str]

    def key_of(self, product: str) -> str:
        """조각 이름. 접힌 제품은 `기타` 로 모인다."""
        return OTHER_PRODUCT_LABEL if product in self.folded else product


class ProductShareSlice(NamedTuple):
    """도넛 조각 하나. `members` 는 `기타` 조각에 든 제품과 각 수량이다.

    `product` 는 이름표이고, `base_product` · `part` 는 그 이름표를 지은 제품정보 · 접힌
    부품이다(좁은 범례 칸에서 부품을 남기고 줄이는 데 쓴다 — `home_figure_common._fit_part_label`).
    `기타` 조각은 빈 글자다.
    """

    product: str
    value: float
    share: float
    slot: int | None
    members: tuple[tuple[str, float], ...] = ()
    base_product: str = ""
    part: str = PART_NOT_SPLIT


class ProductShareCell(NamedTuple):
    """월 축 칸 하나의 도넛. `total` 이 비중의 분모다. `past` 는 Past Data 로 그린 칸이다."""

    label: str
    total: float
    slices: tuple[ProductShareSlice, ...]
    past: bool = False


def share_percent(share: float) -> int:
    """비중(0.355)을 사사오입 정수 퍼센트(36)로 — 판정 기준 글자와 같은 반 올림(`threshold_label`).

    파이썬 `round`·서식 `:.0%` 는 반을 짝수 쪽으로 가른다(0.125 → 12%). `Decimal(repr())` 로 사람이
    읽는 십진 값 그대로 올린다. 값이 아니면(NaN·무한) 0 이다 — 그리는 화면이 조각 하나로 멈추지
    않는다.
    """
    value = float(share)
    if not isfinite(value):
        return 0
    return int((Decimal(repr(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def share_label(share: float) -> str:
    """도넛 조각 안 글자 — 사사오입 정수 % 가 경계(`SHARE_LABEL_MIN_PERCENT`)를 넘으면 「36%」.

    넘지 않으면 빈 글이다(그 조각에는 글자를 적지 않는다).
    """
    percent = share_percent(share)
    return f"{percent}%" if percent > SHARE_LABEL_MIN_PERCENT else ""


def empty_product_volume() -> pd.DataFrame:
    """제품이 하나도 없을 때의 정상 모양."""
    return pd.DataFrame(
        {
            "생산계획년월": pd.Series(dtype="Int64"),
            "제품정보": pd.Series(dtype="string"),
            "Wafer 부하량": pd.Series(dtype="float64"),
            "생산수량": pd.Series(dtype="float64"),
            "과거": pd.Series(dtype="bool"),
            PART_COLUMN: pd.Series(dtype="string"),
        }
    )


def _normalized(
    frame: pd.DataFrame, value_column: str, multi_part: Collection[str]
) -> pd.DataFrame:
    """달 · 제품정보 · 접힌 부품 · 값 네 칸. 부품은 `split_product_parts` 가 판정대로 접는다."""
    parts = split_product_parts(frame, multi_part)
    result = pd.DataFrame(
        {
            "생산계획년월": pd.to_numeric(frame["생산계획년월"], errors="coerce").astype("Int64"),
            "제품정보": frame["제품정보"].astype("string").str.strip(),
            PART_COLUMN: parts[PART_COLUMN].astype("string"),
            value_column: pd.to_numeric(frame[value_column], errors="coerce").astype("float64"),
        }
    )
    return result.dropna(subset=["생산계획년월", "제품정보"])


def build_product_volume(
    plan: pd.DataFrame,
    wafer_load: pd.DataFrame,
    *,
    multi_part: Collection[str] = frozenset(),
) -> pd.DataFrame:
    """제품×월 Wafer 부하량과 PKG 생산수량. **양산구분을 나누지 않고 더한다.**

    Wafer 는 `Wafer 계획` 행과 같은 상세 환산 결과(`물량`, HOME 은 Dummy 계열을 뺀 것)에서
    묶는다. 그래야 제품별 합이 그 행의 값과 한 치도 다르지 않다 — 기준정보가 없어 환산에서
    빠진 계획 행은 두 쪽 모두에서 빠진다. PKG 는 계획의 `생산수량` 을 그대로 묶는다.

    `multi_part` 는 부품을 가를 제품(`product_parts.multi_part_products` — 활성 리비전 계획 전체로
    판정)이다. 그 제품은 (달, 제품, 부품)마다, 나머지는 부품을 접어 (달, 제품)마다 한 줄이다 — 비어
    있으면 모두 접혀 부품을 싣기 전과 같다. 나누기만 하므로 달 합은 그대로다.
    """
    require_columns(plan, ["생산계획년월", "제품정보", "생산수량"], "RQ_PKG_PLAN")
    require_columns(wafer_load, ["생산계획년월", "제품정보", "물량"], "Wafer 부하량")
    wafer = _normalized(
        wafer_load.rename(columns={"물량": "Wafer 부하량"}), "Wafer 부하량", multi_part
    )
    pkg = _normalized(plan, "생산수량", multi_part)
    keys = ["생산계획년월", "제품정보", PART_COLUMN]
    grouped_wafer = wafer.groupby(keys, as_index=False)["Wafer 부하량"].sum()
    grouped_pkg = pkg.groupby(keys, as_index=False)["생산수량"].sum()
    if grouped_wafer.empty and grouped_pkg.empty:
        return empty_product_volume()
    merged = grouped_pkg.merge(grouped_wafer, on=keys, how="outer")
    # 환산에서 빠진 제품은 Wafer 가 **0** 이다(결측이 아니다). `Wafer 계획` 행도 그 제품을
    # 더하지 않았으므로 비중 칸도 그 제품을 조각으로 두지 않는 것이 같은 뜻이다.
    merged["Wafer 부하량"] = merged["Wafer 부하량"].fillna(0.0)
    merged["생산수량"] = merged["생산수량"].fillna(0.0)
    merged["과거"] = False
    result: pd.DataFrame = merged[list(PRODUCT_VOLUME_COLUMNS)].sort_values(keys)
    return result.reset_index(drop=True)


def past_product_volume(
    past_detail: pd.DataFrame,
    *,
    start_month: int,
    end_month: int,
    exclude_months: Collection[int],
    multi_part: Collection[str] = frozenset(),
) -> pd.DataFrame:
    """과거 구간의 제품×월 PKG 생산수량. **Wafer 는 결측이다.**

    과거 입력은 월별 `Wafer Total` 하나뿐이라 제품별 Wafer 를 알 수 없다. 0 으로 두면
    「그 달에 Wafer 가 없었다」로 읽히므로 결측으로 두고, Wafer 단위 도넛은 그 달을 비운다.
    DB 계산 결과가 있는 달(`exclude_months`)은 계산이 이긴다 — 다른 과거 병합과 같은 규칙이다.

    과거 입력에는 부품이 없다. 부품을 가르는 제품(`multi_part`)의 과거 조각은 「DEMO_A (-)」
    하나이고 과거 전용 이름이라 계산 구간 제품 뒤에서 칸을 받는다(`assign_product_slots`).
    """
    if past_detail.empty:
        return empty_product_volume()
    frame = _normalized(past_detail, "생산수량", multi_part)
    months = frame["생산계획년월"].astype("int64")
    frame = frame.loc[months.between(start_month, end_month) & ~months.isin(list(exclude_months))]
    if frame.empty:
        return empty_product_volume()
    grouped = frame.groupby(["생산계획년월", "제품정보", PART_COLUMN], as_index=False)[
        ["생산수량"]
    ].sum()
    grouped["Wafer 부하량"] = float("nan")
    grouped["과거"] = True
    return grouped[list(PRODUCT_VOLUME_COLUMNS)].reset_index(drop=True)


_LABEL = "__product_part_label"


def _labelled(volume: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, tuple[str, str]]]:
    """이름표 칸(`_LABEL`)을 붙인 사본과 이름표 → (제품정보, 접힌 부품).

    `CUSTOM` 칸이 없거나 빈 값이면 접힌 것으로 읽는다 — 부품을 싣기 전 프레임(입장 화면 시험 표
    등)은 제품 이름이 그대로 이름표다.
    """
    products = [str(product) for product in volume["제품정보"]]
    if PART_COLUMN in volume.columns:
        parts = [part if isinstance(part, str) else PART_NOT_SPLIT for part in volume[PART_COLUMN]]
    else:
        parts = [PART_NOT_SPLIT] * len(products)
    labels = [
        product_part_label(product, part) for product, part in zip(products, parts, strict=True)
    ]
    mapping = dict(zip(labels, zip(products, parts, strict=True), strict=True))
    return volume.assign(**{_LABEL: labels}), mapping


def _positive_totals(
    volume: pd.DataFrame | None,
) -> tuple[pd.Series, dict[str, tuple[str, str]]]:
    """이름표별 PKG 생산수량 합(0 이하는 뺀다)과 이름표 → (제품정보, 접힌 부품)."""
    if volume is None or volume.empty:
        return pd.Series(dtype="float64"), {}
    require_columns(volume, ["제품정보", "생산수량"], "제품별 수량")
    labelled, parts = _labelled(volume)
    totals = (
        labelled.assign(생산수량=pd.to_numeric(labelled["생산수량"], errors="coerce").fillna(0.0))
        .groupby(_LABEL)["생산수량"]
        .sum()
    )
    return totals.loc[totals > 0], parts


def _display_ordered(
    labels: Collection[str],
    parts: Mapping[str, tuple[str, str]],
    display_order: DisplayOrderInput,
) -> list[str]:
    """`계획 세부수량` 표와 같은 차례 — (제품명, 부품 차례)로 세운 뒤 공용 표시순서를 얹는다.

    표시순서는 계획 세부수량과 같은 `apply_part_display_order` 로 건다 — 부품 차례(범위의 `CUSTOM`
    규칙 → `part_order_key`, 접힌 값 먼저 · 표지 `-` 끝)와 한 제품의 부품이 이웃하는 것이 그 표와
    같다. 규칙이 없어 표를 그대로 돌려줄 때는 미리 세운 차례가 답이다.
    """
    pairs = sorted(
        (parts[str(label)] for label in labels),
        key=lambda pair: (pair[0], part_order_key(pair[1])),
    )
    if not pairs:
        return []
    ordered = apply_part_display_order(
        pd.DataFrame(
            {
                "제품정보": [product for product, _ in pairs],
                PART_COLUMN: [part for _, part in pairs],
            }
        ),
        display_order,
        PAGE_PLAN,
        TAB_PKG_PLAN,
    )
    return [
        product_part_label(str(product), str(part))
        for product, part in zip(ordered["제품정보"], ordered[PART_COLUMN], strict=True)
    ]


def _largest(products: list[str], totals: pd.Series, count: int) -> set[str]:
    """물량이 큰 `count` 개. 같은 물량이면 차례가 앞선 쪽이 남는다(동률에서 흔들리지 않게)."""
    rank = {product: index for index, product in enumerate(products)}
    return set(sorted(products, key=lambda name: (-float(totals[name]), rank[name]))[:count])


def assign_product_slots(
    volume: pd.DataFrame,
    display_order: DisplayOrderInput = None,
    *,
    past_volume: pd.DataFrame | None = None,
    slot_count: int = PRODUCT_SHARE_SLOT_COUNT,
) -> ProductSlots:
    """제품 차례와 색 칸을 정한다.

    `volume` 은 화면에 보이는 기간 **계산 구간**의 EDP 포함 수량이다(모듈 설명 참고). 그 제품들이
    먼저 `계획 세부수량` 표와 같은 차례로 칸을 받고, `past_volume`(과거 구간)에**만** 있는 제품은
    남은 칸을 그 뒤에서 받는다. 과거 제품을 한 목록에 섞어 세우면 표시순서가 앞선 과거 제품이
    끼어들어 Past Data 를 켜는 순간 계산 구간 제품의 색이 한 칸씩 밀린다.

    칸 수를 넘으면 **PKG 생산수량이 작은 제품부터** `기타` 로 접는다(이름 있는 칸 하나를
    `기타` 에 내준다). 과거 전용 제품은 계산 구간 제품이 칸을 다 쓰면 모두 `기타` 다. 물량 순위는
    단위와 무관한 PKG 로 매긴다 — 단위를 바꿀 때 접히는 제품이 달라지면 색이 따라 바뀐다.

    부품을 가른 제품은 부품 하나가 제품 하나처럼 칸을 받고 접힌다(2026-11-23 보드 답 D2 (가)) —
    한 제품의 부품이 이름 있는 칸과 `기타` 에 걸칠 수 있다.
    """
    totals, parts = _positive_totals(volume)
    past_totals, past_parts = _positive_totals(past_volume)
    primary = _display_ordered(totals.index, parts, display_order)
    past_only_totals = past_totals.drop(labels=list(totals.index), errors="ignore")
    past_only = _display_ordered(past_only_totals.index, past_parts, display_order)
    if len(primary) > slot_count:
        kept = _largest(primary, totals, slot_count - 1)
        named = [product for product in primary if product in kept]
    else:
        named = list(primary)
        if len(primary) + len(past_only) <= slot_count:
            named.extend(past_only)
        else:
            # `기타` 에 한 칸을 남긴다. 계산 구간 제품이 이미 다 차 있으면 남는 칸이 없다.
            room = slot_count - 1 - len(primary)
            if room > 0:
                kept_past = _largest(past_only, past_only_totals, room)
                named.extend(product for product in past_only if product in kept_past)
    folded = frozenset([*primary, *past_only]) - frozenset(named)
    return ProductSlots(
        order=tuple(named),
        slot={product: index for index, product in enumerate(named)},
        folded=folded,
    )


def _cell(
    label: str,
    values: pd.Series,
    slots: ProductSlots,
    *,
    parts: Mapping[str, tuple[str, str]],
    past: bool = False,
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
        ProductShareSlice(
            product,
            named[product],
            named[product] / total,
            slots.slot[product],
            base_product=parts.get(product, (product, PART_NOT_SPLIT))[0],
            part=parts.get(product, (product, PART_NOT_SPLIT))[1],
        )
        for product in slots.order
        if product in named
    ]
    if members:
        other = sum(value for _, value in members)
        ordered = tuple(sorted(members, key=lambda item: -item[1]))
        slices.append(ProductShareSlice(OTHER_PRODUCT_LABEL, other, other / total, None, ordered))
    return ProductShareCell(label=label, total=total, slices=tuple(slices), past=past)


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
    과거 달과 계산 달이 **섞인 해**도 비운다 — 과거 PKG 는 `과거 계획 세부수량` 입력 그대로라
    (그 표는 계산 구간에서 양산만 담는다) 양산+ER 을 더한 계산 달과 더하면 두 정의가 섞인다.
    """
    if basis not in PRODUCT_SHARE_VALUE_COLUMNS:
        raise ValueError(f"제품별 비중 단위가 올바르지 않습니다: {basis}")
    column = PRODUCT_SHARE_VALUE_COLUMNS[basis]
    require_columns(volume, ["생산계획년월", "제품정보", column], "제품별 수량")
    frame, parts = _labelled(volume.loc[volume[column].notna()])
    frame["년월"] = [month_label(int(value)) for value in frame["생산계획년월"]]
    past_flags = (
        frame["과거"].astype(bool)
        if "과거" in frame.columns
        else pd.Series(False, index=frame.index)
    )
    past_labels = set(frame.loc[past_flags, "년월"])
    by_label = {
        str(label): group.groupby(_LABEL)[column].sum()
        for label, group in frame.groupby("년월", sort=False)
    }
    totals = set(year_total_labels)
    cells: dict[str, ProductShareCell] = {}
    for label in month_labels:
        if label in totals or label not in by_label:
            continue
        cell = _cell(label, by_label[label], slots, parts=parts, past=label in past_labels)
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
        kinds = {cells[label].past for label in members}
        if len(kinds) > 1:
            continue
        year_values = pd.concat([by_label[label] for label in members]).groupby(level=0).sum()
        cell = _cell(total_label, year_values, slots, parts=parts, past=kinds == {True})
        if cell is not None:
            cells[total_label] = cell
    return cells


def combine_product_volume(*frames: pd.DataFrame) -> pd.DataFrame:
    """계산 구간과 과거 구간의 제품별 수량을 잇는다. 빈 프레임은 건너뛴다.

    빈 프레임까지 `concat` 에 넣으면 pandas 가 결과 dtype 을 정하는 규칙이 바뀐다는 경고를
    낸다. 비어 있는 쪽은 더할 행이 없으므로 빼도 결과가 같다. `CUSTOM` 칸이 없는 프레임은 접힌
    부품(빈 글자)으로 채운다 — 다른 칸(과거 Wafer 결측 등)은 그대로다.
    """
    present = [
        _with_part_column(frame)[list(PRODUCT_VOLUME_COLUMNS)]
        for frame in frames
        if not frame.empty
    ]
    if not present:
        return empty_product_volume()
    if len(present) == 1:
        return present[0].reset_index(drop=True)
    return pd.concat(present, ignore_index=True)


def _with_part_column(frame: pd.DataFrame) -> pd.DataFrame:
    """`CUSTOM` 칸이 없으면 접힌 부품으로 채운 사본, 있으면 그대로."""
    if PART_COLUMN in frame.columns:
        return frame
    return frame.assign(**{PART_COLUMN: PART_NOT_SPLIT})
