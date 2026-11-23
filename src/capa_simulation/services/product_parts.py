# Purpose: 합쳐 보는 화면이 제품의 부품(CUSTOM)을 가를지 판정하고 이름표 · 차례 · 접기를 낸다.

"""제품 부품(`CUSTOM`) 갈라 보이기 — 다섯 화면이 함께 쓰는 한 벌.

`CUSTOM` 은 제품 구분 키다(사용자 결정 「CUSTOM 이 다르면 다른 제품」). 계산은 부품마다 따로 나지만
합쳐 보는 화면(HOME 도넛 · 제품별 비중 · HOME 계획 세부수량 · 공정 Capa 상세 제품별 나눔 · 제약
시뮬레이션)은 제품 이름으로 그려 왔다. 그 화면들이 같은 규칙으로 부품을 가르게 판정 · 이름표 ·
차례를 여기 하나에 둔다.

- **가를 단위는 (제품정보, CUSTOM)** 이고, 가르는 제품은 **CUSTOM 이 둘 이상인 제품정보**
  (`multi_part_products`) 뿐이다. 행의 값이 표지 `-` 인지로 가르지 않는다 — 제품마다 실값
  하나인 새 등록 데이터에서 모든 이름이 길어진다. 판정 범위는 활성 리비전 계획 전체(모든 달 · EDP
  포함 · 거르기 전)라 달 · 토글 · 거르기에 따라 이름표가 흔들리지 않는다.
- 부품이 하나뿐인 제품은 CUSTOM 을 내부 값 `PART_NOT_SPLIT`(빈 글자)로 접는다
  (`split_product_parts`). 그래서 묶음과 이름이 부품을 싣기 전과 같다.
- 이름표는 접힌 제품이면 제품 이름 그대로, 가른 제품이면 「DEMO_A (DEMO_CUSTOM_A)」 다
  (`product_part_label` — 2026-11-23 보드 답 D1 (가)). 가운뎃점은 이미 「양산 · DEMO_A」 같은
  잇기 구분자라 쓰지 않는다.
- 차례는 제품 → 부품 → 그 밖의 칸(Stack 등)이다. 부품 차례는 접힌 값이 먼저이고 나머지는 표시 차례
  열쇠 `core_data_derivation.custom_sort_key` 그대로다(`part_order_key`) — 범위에 `CUSTOM` 규칙이
  있으면 그 규칙이 한 제품 안의 부품 차례만 정하고 제품 사이를 넘어 부품을 떼어 놓지 않는다. 행으로
  그리는 표와 도넛 · 범례 차례는 둘 다 공용 표시순서를 `apply_part_display_order` 로 건다.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Final

import pandas as pd

from capa_simulation.services.core_data_derivation import CUSTOM_BLANK, custom_sort_key
from capa_simulation.services.display_order import (
    DisplayOrderInput,
    PreparedDisplayOrder,
    apply_display_order,
    prepare_display_order,
)
from capa_simulation.services.frame_contracts import require_columns

PRODUCT_COLUMN: Final = "제품정보"
PART_COLUMN: Final = "CUSTOM"
# 부품이 하나뿐인 제품의 CUSTOM 을 접은 내부 값. 원천 · 표지(`CUSTOM_BLANK`)에는 나오지 않는 글자다
# — 정규화가 빈 값을 표지로 세우므로(`normalize_custom_values`) 빈 글자는 「접힘」 하나만 뜻한다.
PART_NOT_SPLIT: Final = ""


def _product_text(values: pd.Series) -> pd.Series:
    """제품정보의 비교 글자 — 앞뒤 공백을 뗀다(제품별 비중 · 계획 세부수량이 묶는 값과 같다)."""
    return values.astype("string").str.strip()


def _part_text(values: pd.Series) -> pd.Series:
    """CUSTOM 의 부품 글자 — 앞뒤 공백을 떼고, 빈 값(NA · 빈 글자)은 표지 `-` 로 세운다."""
    text = values.astype("string").str.strip()
    return text.where(text.notna() & text.ne(""), CUSTOM_BLANK).astype("string")


def product_part_label(product: str, part: str) -> str:
    """화면 이름표 — 접힌 부품(`PART_NOT_SPLIT`)이면 제품 이름, 아니면 「제품 (부품)」."""
    return product if part == PART_NOT_SPLIT else f"{product} ({part})"


def multi_part_products(plan: pd.DataFrame) -> frozenset[str]:
    """부품을 갈라 보일 제품정보(앞뒤 공백을 뗀 글자) — CUSTOM 이 둘 이상인 제품이다.

    CUSTOM 칸이 없거나 표가 비면 빈 집합이다(모두 접힘). 표지 `-` 도 부품 하나로 센다 — 계산 키에서
    `-` 는 다른 값과 다른 제품이다(Q11 「- = 구분 없음」).

    이름표가 글자 그대로 조각 · 줄의 열쇠라, 부품이 하나뿐인 제품의 이름이 가른 제품의 부품 이름표와
    같으면 (제품정보 「DEMO_A (DEMO_CUSTOM_A)」 와 「DEMO_A」 의 부품 「DEMO_CUSTOM_A」) 두 줄이 한
    조각으로 합쳐진다. 그런 제품도 부품을 붙여 보이도록 여기 함께 든다 — 붙인 이름표가 다시 겹치지
    않을 때까지 넓힌다.
    """
    if plan.empty or PART_COLUMN not in plan.columns:
        return frozenset()
    require_columns(plan, [PRODUCT_COLUMN], "RQ_PKG_PLAN")
    pairs = (
        pd.DataFrame(
            {
                PRODUCT_COLUMN: _product_text(plan[PRODUCT_COLUMN]),
                PART_COLUMN: _part_text(plan[PART_COLUMN]),
            }
        )
        .dropna(subset=[PRODUCT_COLUMN])
        .drop_duplicates()
    )
    if pairs.empty:
        return frozenset()
    counts = pairs.groupby(PRODUCT_COLUMN, sort=False)[PART_COLUMN].size()
    split = {str(product) for product, count in counts.items() if count >= 2}
    products = {str(product) for product in counts.index}
    part_pairs = [(str(product), str(part)) for product, part in pairs.itertuples(index=False)]
    while True:
        labels = {
            product_part_label(product, part) for product, part in part_pairs if product in split
        }
        clashing = {product for product in products - split if product in labels}
        if not clashing:
            return frozenset(split)
        split |= clashing


def split_product_parts(frame: pd.DataFrame, multi_part: Collection[str]) -> pd.DataFrame:
    """CUSTOM 을 화면 단위로 접은 사본 — 가르지 않는 제품은 `PART_NOT_SPLIT`, 가르는 제품은 부품.

    CUSTOM 칸이 없는 표(Past Data 계획 세부수량 · 옛 시험 표)는 칸을 끝에 붙여 채운다 — 가르지 않는
    제품은 `PART_NOT_SPLIT`, 가르는 제품은 부품을 모르므로 표지 `-` 다. 제품정보 칸은 그대로 둔다.
    """
    require_columns(frame, [PRODUCT_COLUMN], "제품 부품")
    result = frame.copy()
    split = _product_text(result[PRODUCT_COLUMN]).isin(list(multi_part)).fillna(False)
    if PART_COLUMN in result.columns:
        parts = _part_text(result[PART_COLUMN])
    else:
        parts = pd.Series(CUSTOM_BLANK, index=result.index, dtype="string")
    result[PART_COLUMN] = parts.where(split.astype("bool"), PART_NOT_SPLIT).astype("string")
    return result


def part_order_key(part: object) -> tuple[bool, tuple[bool, str, str]]:
    """부품 하나의 차례 열쇠 — 접힌 값(`PART_NOT_SPLIT`)이 먼저, 나머지는 `custom_sort_key`.

    `custom_sort_key` 는 빈 글자를 표지와 같이 끝에 두므로 접힌 값만 여기서 앞에 세운다. 파이썬 기본
    차례 · groupby 는 `-` 를 글자 앞에 두므로 부품을 세우는 자리는 이 열쇠를 쓴다.
    """
    if isinstance(part, str) and part == PART_NOT_SPLIT:
        return (False, (False, "", ""))
    return (True, custom_sort_key(part))


def _without_part_rules(display_order: DisplayOrderInput) -> PreparedDisplayOrder | None:
    """`CUSTOM` 규칙을 뺀 표시순서 — 합쳐 보는 화면의 행 차례(제품 사이 · Stack 등)를 세울 때 쓴다.

    부품은 제품 칸 글에 녹아 그 제품 곁에서만 서므로, `CUSTOM` 규칙은 한 제품 안의 부품 차례만
    정한다(`_part_ranks`). 행 전체를 그 규칙으로 세우면 다른 제품의 부품이 한 제품의 부품 사이에
    끼거나 규칙에 든 부품이 접힌 제품들 앞으로 뛰어 오른다. 규칙이 없으면 받은 것 그대로다.
    """
    prepared = prepare_display_order(display_order)
    if prepared is None:
        return None
    rules = prepared.derived_rules
    part_rules = rules["분류컬럼"].eq(PART_COLUMN).fillna(False).astype("bool")
    if not bool(part_rules.any()):
        return prepared
    kept = prepared.rules["분류컬럼"].ne(PART_COLUMN).fillna(True).astype("bool")
    return PreparedDisplayOrder(
        rules=prepared.rules.loc[kept], derived_rules=rules.loc[~part_rules]
    )


def _part_ranks(
    parts: pd.Series, display_order: DisplayOrderInput, page: str, tab: str | None
) -> list[int]:
    """행마다 부품 차례 수 — 그 범위의 `CUSTOM` 규칙(있으면) → `part_order_key`.

    부품 값마다 한 번씩, 부품 칸 하나뿐인 표에 공용 표시순서를 건다 — 다른 칸 규칙은 그 칸이 없어
    건너뛰므로 `CUSTOM` 규칙만 걸리고, 규칙이 없으면 미리 세운 `part_order_key` 차례가 답이다. 한
    제품 안의 부품 차례만 정하는 수라 다른 제품의 부품과 견주지 않는다.
    """
    codes, uniques = pd.factorize(parts, use_na_sentinel=False)
    by_key = sorted(range(len(uniques)), key=lambda code: part_order_key(uniques[code]))
    distinct = pd.DataFrame(
        {
            PART_COLUMN: pd.Series([uniques[code] for code in by_key], dtype="object"),
            "__part_code": by_key,
        }
    )
    ordered = apply_display_order(distinct, display_order, page, tab)
    rank = {int(code): position for position, code in enumerate(ordered["__part_code"])}
    return [rank[int(code)] for code in codes]


def keep_parts_together(
    frame: pd.DataFrame,
    owner_columns: Sequence[str] = (PRODUCT_COLUMN,),
    *,
    display_order: DisplayOrderInput = None,
    page: str = "",
    tab: str | None = None,
) -> pd.DataFrame:
    """이웃한 같은 제품 행 덩이 안에서 부품 차례로 한 부품의 행을 모은 사본 — 표시순서를 건 **뒤**에
    쓴다.

    `display_order.apply_display_order` 의 끝 열쇠는 규칙 열쇠가 같은 행에서만 부품을 이웃하게
    세운다. CUSTOM 뒤 칸(Stack 등)에 규칙이 걸리면 한 제품의 부품이 그 칸 값마다 번갈아
    선다(A/12H/p1, A/12H/p2, A/8H/p1 …). 부품마다 그 칸 값이 겹치지 않으면 그 칸 규칙이 부품
    차례까지 뒤집는다(A/12H/p2, A/8H/p1). 부품을 제품 칸 글에 녹여 그리는 화면은 차례가 제품 → 부품
    → 그 칸이라,
    제품(`owner_columns` 값이 같은 이웃 행) 덩이마다 부품 차례(`_part_ranks` — 범위의 `CUSTOM`
    규칙 → `part_order_key`, 도넛 · 범례와 같은 차례)로 모은다. 한 부품 안의 행 차례(Stack 등)와
    제품 덩이끼리의 차례 · 다른 제품 행은 받은 그대로다. CUSTOM 칸이 없으면 그대로 돌려준다.
    """
    if frame.empty or PART_COLUMN not in frame.columns:
        return frame
    owners = list(owner_columns)
    require_columns(frame, owners, "제품 부품")
    codes = frame.groupby(owners, dropna=False, sort=False).ngroup()
    run = codes.ne(codes.shift()).cumsum().to_numpy()
    ranks = _part_ranks(frame[PART_COLUMN], display_order, page, tab)
    keys = pd.DataFrame({"run": run, "part": ranks, "row": range(len(frame))})
    order = keys.sort_values(["run", "part", "row"], kind="stable").index
    return frame.iloc[order].reset_index(drop=True)


def _mixed_parts_first(frame: pd.DataFrame, owners: list[str], ranks: list[int]) -> pd.DataFrame:
    """부품이 둘 이상 섞인 제품(`owners` 값이 같은 행)의 행을 그 제품이 처음 선 자리로 모아 부품
    차례(`ranks` → 원래 행 차례)로 세운 사본. 부품이 하나뿐인 제품의 행은 제자리다."""
    groups = frame.groupby(owners, dropna=False, sort=False).ngroup().tolist()
    first: dict[int, int] = {}
    distinct: dict[int, set[int]] = {}
    for position, (group, rank) in enumerate(zip(groups, ranks, strict=True)):
        first.setdefault(group, position)
        distinct.setdefault(group, set()).add(rank)
    anchors = [
        first[group] if len(distinct[group]) > 1 else position
        for position, group in enumerate(groups)
    ]
    order = sorted(range(len(frame)), key=lambda row: (anchors[row], ranks[row], row))
    if order == list(range(len(frame))):
        return frame
    return frame.iloc[order].reset_index(drop=True)


def apply_part_display_order(
    frame: pd.DataFrame,
    display_order: DisplayOrderInput,
    page: str,
    tab: str,
    owner_columns: Sequence[str] = (PRODUCT_COLUMN,),
) -> pd.DataFrame:
    """공용 표시순서를 건 표 — 가른 제품의 부품 행은 한 제품 안에서 부품 차례로 모여 선다.

    차례는 제품 → 부품 → 그 밖의 칸(Stack 등)이다. 부품 차례는 `_part_ranks`(범위의 `CUSTOM`
    규칙 → `part_order_key`) 하나이고, 행 차례는 `CUSTOM` 규칙을 뺀 표시순서
    (`_without_part_rules`)가 세운다 — 같은 표를 다른 부품 차례로 두 번 세우지 않는다.

    1. 앞: 부품이 둘 이상 섞인 제품의 행을 그 제품이 처음 선 자리로 모아 부품 차례로 세운다 — 그
       범위에 규칙이 없으면 `apply_display_order` 가 받은 차례를 그대로 돌려주므로 이 차례가
       답이다(피벗 · `groupby` 는 표지 `-` 를 글자 앞에 두고 대소문자를 가려 세운다). 덧붙은
       행(비교 · 과거에만 있는 「제품 (-)」 줄)도 그 제품 곁에 선다. 부품이 하나뿐인 제품의 행은
       제자리라 지금 차례 그대로다.
    2. `apply_display_order`(`CUSTOM` 규칙을 뺀 것) — 규칙이 있으면 끝 열쇠가 한 제품의 부품을
       이웃하게 세운다.
    3. 뒤: `keep_parts_together` — CUSTOM 뒤 칸(Stack 등) 규칙이 번갈아 세우거나 부품 차례를
       뒤집은 한 제품 덩이를 부품 차례로 모은다.

    도넛 · 범례 차례(`product_share.assign_product_slots`)도 (제품, 부품) 두 칸 표로 이 함수를
    지나므로 같은 데이터 · 같은 규칙에서 계획 세부수량 띠와 부품 차례가 같다. CUSTOM 칸이 없는 표는
    `apply_display_order` 와 같다.
    """
    owners = list(owner_columns)
    if frame.empty or PART_COLUMN not in frame.columns:
        return apply_display_order(frame, display_order, page, tab)
    require_columns(frame, owners, "제품 부품")
    prepared = prepare_display_order(display_order)
    gathered = _mixed_parts_first(
        frame, owners, _part_ranks(frame[PART_COLUMN], prepared, page, tab)
    )
    ordered = apply_display_order(gathered, _without_part_rules(prepared), page, tab)
    return keep_parts_together(ordered, owners, display_order=prepared, page=page, tab=tab)


def part_merged_columns(frame: pd.DataFrame, dims: Sequence[str]) -> tuple[list[str], pd.DataFrame]:
    """CUSTOM 을 제품 칸 글에 녹인 (보이는 분류 칸, 사본) — 부품을 칸으로 그리지 않는 화면용.

    `dims` 에 제품정보와 CUSTOM 이 함께 있으면 보이는 칸은 CUSTOM 을 뺀 차례이고, 사본의 제품정보
    칸은 이름표(`product_part_label`), CUSTOM 칸은 없다. CUSTOM 값은 접힌 것
    (`split_product_parts`)을 받는다 — 빈 값은 표지 `-` 로 읽는다. 둘 중 하나라도 `dims` 에 없으면
    `dims` 와 받은 표 그대로다.
    """
    columns = list(dims)
    if PART_COLUMN not in columns or PRODUCT_COLUMN not in columns:
        return columns, frame
    visible = [column for column in columns if column != PART_COLUMN]
    if PART_COLUMN not in frame.columns:
        return visible, frame
    merged = frame.drop(columns=[PART_COLUMN])
    labels = [
        product if pd.isna(product) else product_part_label(str(product), label_part(part))
        for product, part in zip(frame[PRODUCT_COLUMN], frame[PART_COLUMN], strict=True)
    ]
    merged[PRODUCT_COLUMN] = pd.Series(labels, index=frame.index, dtype="object")
    return visible, merged


def label_part(part: object) -> str:
    """이름표에 붙일 부품 글자 — 접힌 값은 그대로, 빈 값(NA · 공백뿐)은 표지 `-`.

    `part_merged_columns` 가 이름표를 지을 때와 좁은 칸 줄임(`_fit_part_label`)에 부품을 따로 넘길
    때 같은 글자를 쓰게 한다.
    """
    if not isinstance(part, str):
        return CUSTOM_BLANK
    if part == PART_NOT_SPLIT:
        return PART_NOT_SPLIT
    return part.strip() or CUSTOM_BLANK
