# Purpose: 제품별 비중이 부품이 둘 이상인 제품만 부품마다 가르는지 본다

"""제품별 비중 — 부품(`CUSTOM`) 갈라 보임(2026-11-23 보드 답 D1 (가) · D2 (가)).

부품이 둘 이상인 제품만 부품마다 조각 · 칸 · 범례 이름표(「제품 (부품)」)를 받고, 숫자는 지금 합을
나눈 것이라 조각 합이 그 달 `Wafer 계획` 이다. 한 제품에 CUSTOM 이 한 값인 데이터(내장 시드 · 새
등록)는 CUSTOM 칸을 뗀 결과와 칸 · 색 · 차례가 같다. 견본은 `custom_key_tables.two_part_tables`(내장
시드의 한 제품을 두 부품으로 가른 RQ 표 — 부품마다 수율이 달라 Wafer 가 갈린다)다.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

import pandas as pd
import plotly.graph_objects as go
import pytest
from custom_key_tables import (
    PART_A,
    PART_B,
    TWO_PART_PRODUCT,
    custom_keyed_tables,
    two_part_tables,
)
from home_two_part_app import home_script, publish_two_part_revision
from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_figure_common import _text_width_units
from capa_simulation.components.home_lob_figures import (
    _legend_name_budget_units,
    _product_share_label_annotations,
    product_share_legend,
    product_share_traces,
)
from capa_simulation.components.intro_summary import summary_payload
from capa_simulation.home_state import PRODUCT_SHARE_BASIS_KEY
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import MONTH_RANGE_KEY
from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.dashboard import home_aggregation_wafer_load
from capa_simulation.services.load_calculator import calculate_chip_and_wafer_loads
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.official_summary import build_official_summary
from capa_simulation.services.past_data import PAST_SECUREMENT_COLUMNS, empty_past_table
from capa_simulation.services.product_share import (
    OTHER_PRODUCT_LABEL,
    PRODUCT_SHARE_BASIS_PKG,
    PRODUCT_SHARE_SLOT_COUNT,
    ProductShareCell,
    ProductShareSlice,
    assign_product_slots,
    build_product_share_cells,
    build_product_volume,
    combine_product_volume,
    past_product_volume,
)
from capa_simulation.services.route_load_exceptions import NO_ROUTE_LOAD_EXCEPTIONS
from capa_simulation.services.securement_threshold import SecurementThresholds

# 보드 답 D1 (가) 의 꼴 그대로 적는다 — 이름표 도우미로 지으면 꼴을 되돌려도 기대가 함께 바뀐다.
LABEL_A = "DEMO PRODUCT A (DEMO_CUSTOM_A)"
LABEL_B = "DEMO PRODUCT A (DEMO_CUSTOM_B)"


def _months(tables: Mapping[str, pd.DataFrame]) -> list[int]:
    return sorted({int(month) for month in pd.to_numeric(tables["RQ_PKG_PLAN"]["생산계획년월"])})


def _home(
    tables: Mapping[str, pd.DataFrame], *, start: int | None = None, end: int | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """HOME 캐시 두 함수의 (월 Wafer, 제품별 수량 EDP 포함, EDP 뺀 제품별 수량).

    캐시는 프로세스 전역이라 부를 때마다 토큰을 새로 짓는다."""
    months = _months(tables)
    display_order = tables["RQ_DISPLAY_ORDER"]
    key = sc.build_home_simulation_cache_key(
        reference_version=1,
        scenario_token=f"product-share-parts-{uuid4().hex}",
        start_month=start if start is not None else months[0],
        end_month=end if end is not None else months[-1],
        display_order=display_order,
        route_exceptions=NO_ROUTE_LOAD_EXCEPTIONS,
    )
    simulation = sc.get_home_simulation(key, tables, display_order, tables)
    without_edp = sc.get_home_lob_without_edp(key, tables, display_order)
    return simulation[2], simulation[5], without_edp[3]


def _labels(tables: Mapping[str, pd.DataFrame]) -> list[str]:
    return [month_label(month) for month in _months(tables)]


# ---------------------------------------------------------------- 칸 · 차례 · 숫자


def test_two_parts_get_their_own_slots_next_to_each_other() -> None:
    tables = two_part_tables()
    _, volume, _ = _home(tables)

    slots = assign_product_slots(volume, tables["RQ_DISPLAY_ORDER"])

    assert slots.order.index(LABEL_B) == slots.order.index(LABEL_A) + 1
    assert slots.slot[LABEL_A] != slots.slot[LABEL_B]
    assert TWO_PART_PRODUCT not in slots.order
    # 부품이 하나뿐인 제품은 지금처럼 제품 이름만이다.
    assert all(" (" not in name for name in slots.order if not name.startswith(TWO_PART_PRODUCT))


def test_each_months_slices_add_up_to_the_wafer_plan() -> None:
    """부품 조각은 지금 합을 나눈 것이다 — 달마다 조각 합 = 분모 = HOME `Wafer 계획`."""
    tables = two_part_tables()
    monthly_wafer, volume, _ = _home(tables)
    slots = assign_product_slots(volume, tables["RQ_DISPLAY_ORDER"])

    cells = build_product_share_cells(volume, "Wafer", slots, month_labels=_labels(tables))

    plan = dict(
        zip(
            [month_label(int(month)) for month in monthly_wafer["생산계획년월"]],
            monthly_wafer["Wafer 부하량"].astype("float64"),
            strict=True,
        )
    )
    assert cells and set(cells) == set(plan)
    for label, cell in cells.items():
        assert sum(piece.value for piece in cell.slices) == pytest.approx(cell.total)
        assert cell.total == pytest.approx(plan[label])
        parts = {piece.product: piece.value for piece in cell.slices}
        assert parts[LABEL_A] > 0 and parts[LABEL_B] > 0
        assert parts[LABEL_A] != pytest.approx(parts[LABEL_B])


def test_the_two_parts_add_up_to_the_product_of_an_unsplit_seed() -> None:
    """B 를 바꾸지 않으면 두 부품의 합이 시드 한 제품과 같다(PKG · Wafer)."""
    seed = build_builtin_seed_dataset().reference_tables
    _, seed_volume, _ = _home(seed)
    _, even_volume, _ = _home(two_part_tables(vary_b=False))

    seed_rows = seed_volume.loc[seed_volume["제품정보"].eq(TWO_PART_PRODUCT)]
    even_rows = even_volume.loc[even_volume["제품정보"].eq(TWO_PART_PRODUCT)]
    assert set(even_rows["CUSTOM"]) == {PART_A, PART_B}
    for column in ("Wafer 부하량", "생산수량"):
        summed = even_rows.groupby("생산계획년월")[column].sum().sort_index()
        assert summed.to_numpy() == pytest.approx(
            seed_rows.set_index("생산계획년월")[column].sort_index().to_numpy()
        )


def test_the_judgement_does_not_move_with_the_month_range_or_edp() -> None:
    """이름표는 리비전 계획 전체로 판정한다 — 조회기간에 한 부품만 남아도, EDP 를 빼도 그 제품은
    부품 이름으로 선다(UI-PRF-03). B 부품을 마지막 달에만 두고 그 앞까지 보므로, 기간 · EDP 로 거른
    계획으로 판정하면 부품이 하나라 접힌 제품 이름(빈 부품)이 된다."""
    tables = two_part_tables()
    plan = tables["RQ_PKG_PLAN"]
    months = _months(tables)
    late = pd.to_numeric(plan["생산계획년월"]).ge(months[-1])
    tables["RQ_PKG_PLAN"] = plan.loc[plan["CUSTOM"].ne(PART_B) | late].reset_index(drop=True)
    _, volume, without_edp = _home(tables, end=months[-2])
    _, one_month, one_month_without_edp = _home(tables, start=months[3], end=months[3])

    for frame in (volume, without_edp, one_month, one_month_without_edp):
        rows = frame.loc[frame["제품정보"].eq(TWO_PART_PRODUCT)]
        assert not rows.empty
        assert set(rows["CUSTOM"]) == {PART_A}


# ---------------------------------------------------------------- 한 값 데이터는 그대로


def _plan_and_wafer(tables: Mapping[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    plan = tables["RQ_PKG_PLAN"]
    _, wafer = calculate_chip_and_wafer_loads(plan, tables["RQ_YLD"], tables["RQ_CHIP_QTY"])
    return plan, home_aggregation_wafer_load(wafer)


def _cell_view(cells: Mapping[str, ProductShareCell]) -> dict[str, list[tuple[object, ...]]]:
    return {
        label: [(piece.product, piece.value, piece.share, piece.slot) for piece in cell.slices]
        for label, cell in cells.items()
    }


@pytest.mark.parametrize("variant", ["seed", "one_real_part"])
def test_one_value_data_gives_the_slots_colors_and_order_of_the_frame_without_custom(
    variant: str,
) -> None:
    seed = build_builtin_seed_dataset().reference_tables
    tables = {name: frame.copy() for name, frame in seed.items()}
    if variant == "one_real_part":
        # 계획만이 아니라 CUSTOM 키 표 모두에 같은 실값을 싣는다 — 계획에만 실으면 수율 · Chip 수
        # 조인이 비어 Wafer 쪽 견줌이 빈 칸끼리가 된다.
        products = sorted(tables["RQ_PKG_PLAN"]["제품정보"].astype(str).unique())
        parts = {product: f"DEMO_CUSTOM_{index}" for index, product in enumerate(products)}
        for name in custom_keyed_tables():
            frame = tables[name]
            frame["CUSTOM"] = frame["제품정보"].astype(str).map(parts)
    plan, wafer = _plan_and_wafer(tables)
    _, judged, _ = _home(tables)

    bare = build_product_volume(
        plan.drop(columns=["CUSTOM"]), wafer.drop(columns=["CUSTOM"], errors="ignore")
    )
    labels = _labels(tables)
    display_order = tables["RQ_DISPLAY_ORDER"]
    bare_slots = assign_product_slots(bare.drop(columns=["CUSTOM"]), display_order)
    judged_slots = assign_product_slots(judged, display_order)

    assert judged_slots == bare_slots
    assert float(judged["Wafer 부하량"].sum()) > 0
    for basis in ("Wafer", "PKG"):
        assert _cell_view(
            build_product_share_cells(judged, basis, judged_slots, month_labels=labels)
        ) == _cell_view(
            build_product_share_cells(
                bare.drop(columns=["CUSTOM"]), basis, bare_slots, month_labels=labels
            )
        )


# ---------------------------------------------------------------- 과거 구간


def test_the_past_marker_slice_never_pushes_the_calculated_colors() -> None:
    """과거 입력에는 부품이 없어 「제품 (-)」 조각이다. 과거 전용 이름이라 계산 구간 제품의 칸
    배정을 마친 뒤에 그 제품 첫 부품의 색 칸을 빌린다(그림 보드 3 답 q7-past-slice (나)) — Past
    Data 를 켜도 부품 조각의 색이 그대로이고 새 칸이 서지 않는다."""
    tables = two_part_tables()
    months = _months(tables)
    _, volume, _ = _home(tables)
    past = pd.DataFrame(
        {
            "생산계획년월": [months[0] - 100] * 2,
            "제품정보": [TWO_PART_PRODUCT, "DEMO PRODUCT B"],
            "Stack": ["12H", "12H"],
            "Customer": ["DEMO-CUST", "DEMO-CUST"],
            "생산수량": [30.0, 10.0],
        }
    )
    past_volume = past_product_volume(
        past,
        start_month=months[0] - 100,
        end_month=months[-1],
        exclude_months=set(months),
        multi_part=frozenset({TWO_PART_PRODUCT}),
    )
    display_order = tables["RQ_DISPLAY_ORDER"]

    without_past = assign_product_slots(volume, display_order)
    with_past = assign_product_slots(volume, display_order, past_volume=past_volume)

    marker = "DEMO PRODUCT A (-)"
    assert with_past.order == without_past.order
    assert {name: with_past.slot[name] for name in without_past.order} == dict(without_past.slot)
    lender = next(name for name in without_past.order if name.startswith(f"{TWO_PART_PRODUCT} ("))
    assert dict(with_past.lenders) == {marker: lender}
    assert with_past.slot[marker] == with_past.slot[lender]
    # 지금 규칙이면 계산 구간 뒤 남는 칸을 받았다 — 그 칸은 비워 두고 겹칠 때만 쓴다.
    assert dict(with_past.fallback) == {marker: len(without_past.order)}
    cells = build_product_share_cells(
        combine_product_volume(volume, past_volume),
        "PKG",
        with_past,
        month_labels=[month_label(months[0] - 100), *_labels(tables)],
    )
    past_cell = cells[month_label(months[0] - 100)]
    assert past_cell.past
    assert {piece.product for piece in past_cell.slices} == {marker, "DEMO PRODUCT B"}
    borrowed = next(piece for piece in past_cell.slices if piece.product == marker)
    assert borrowed.slot == with_past.slot[lender] and borrowed.lender == lender


MARKER = "DEMO_PART (-)"


def _slot_volumes(
    calculated: list[tuple[str, str, float]], past: list[tuple[str, float]]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """계산 달(202609)의 (제품, 부품, 수량)과 과거 달(202608)의 (제품, 수량) — DEMO_PART 만 부품을
    가른다."""
    plan = pd.DataFrame(
        [(202609, name, part, value) for name, part, value in calculated],
        columns=["생산계획년월", "제품정보", "CUSTOM", "생산수량"],
    )
    volume = build_product_volume(
        plan, plan.rename(columns={"생산수량": "물량"}), multi_part=frozenset({"DEMO_PART"})
    )
    past_frame = pd.DataFrame(
        {
            "생산계획년월": [202608] * len(past),
            "제품정보": [name for name, _ in past],
            "Stack": ["12H"] * len(past),
            "Customer": ["DEMO-CUST"] * len(past),
            "생산수량": [value for _, value in past],
        }
    )
    past_volume = past_product_volume(
        past_frame,
        start_month=202608,
        end_month=202609,
        exclude_months={202609},
        multi_part=frozenset({"DEMO_PART"}),
    )
    return volume, past_volume


def _full_slots() -> tuple[pd.DataFrame, pd.DataFrame]:
    """계산 달 이름 여섯이 칸을 다 써 과거 전용 이름에 남는 칸이 없는 견본(그림 보드 3 의 꼴)."""
    others = [
        (f"DEMO_{index}", "-", 100.0 + index) for index in range(PRODUCT_SHARE_SLOT_COUNT - 2)
    ]
    return _slot_volumes(
        [*others, ("DEMO_PART", PART_A, 500.0), ("DEMO_PART", PART_B, 20.0)],
        [("DEMO_PART", 300.0), ("DEMO_PAST", 50.0), ("DEMO_0", 10.0)],
    )


def test_a_past_marker_borrows_the_first_named_part_slot_when_no_slot_is_left() -> None:
    """칸이 모자라 지금 규칙이면 과거 「DEMO_PART (-)」 가 `기타` 로 접히는 견본 — 그 제품의 부품
    가운데 이름 있는 칸을 받은 첫 부품(칸 차례로 가장 앞)의 색 칸을 빌린다(그림 보드 3 답
    q7-past-slice (나)). 칸 수 · 다른 제품의 칸 · `기타` 접힘(과거 전용 DEMO_PAST)은 빌리지 않은
    배정과 같고, 풍선 이름은 「DEMO_PART (-)」 그대로다."""
    volume, past_volume = _full_slots()
    without_past = assign_product_slots(volume)

    slots = assign_product_slots(volume, past_volume=past_volume)

    part_a, part_b = f"DEMO_PART ({PART_A})", f"DEMO_PART ({PART_B})"
    assert slots.order == without_past.order
    assert len(slots.order) == PRODUCT_SHARE_SLOT_COUNT
    assert slots.slot[part_a] < slots.slot[part_b]
    assert dict(slots.lenders) == {MARKER: part_a}
    assert slots.slot[MARKER] == slots.slot[part_a]
    assert {name: slots.slot[name] for name in slots.order} == dict(without_past.slot)
    assert slots.folded == frozenset({"DEMO_PAST"})
    assert dict(slots.fallback) == {MARKER: None}

    cells = build_product_share_cells(
        combine_product_volume(volume, past_volume),
        PRODUCT_SHARE_BASIS_PKG,
        slots,
        month_labels=["26.08", "26.09"],
    )
    past_cell = cells["26.08"]
    borrowed = next(piece for piece in past_cell.slices if piece.product == MARKER)
    assert borrowed.slot == slots.slot[part_a] and borrowed.lender == part_a
    other = next(piece for piece in past_cell.slices if piece.product == OTHER_PRODUCT_LABEL)
    assert [name for name, _ in other.members] == ["DEMO_PAST"]
    assert sum(piece.share for piece in past_cell.slices) == pytest.approx(1.0)
    hover = product_share_traces(
        cells, ["26.08", "26.09"], basis="PKG", year_totals=(), past_month_labels={"26.08"}
    )[0].hovertext
    assert any(str(text).startswith(f"26.08 · {MARKER} ") for text in hover)


def test_the_legend_keeps_one_line_per_slot_when_a_marker_borrows() -> None:
    """범례는 칸마다 한 줄이다 — 빌린 칸은 빌려 준 부품 이름표 줄 하나이고 「DEMO_PART (-)」 줄을
    더하지 않는다. 빌려 준 부품이 그려지지 않은 화면(과거 달만)에서는 그 칸 줄이 빌린 이름이다."""
    volume, past_volume = _full_slots()
    slots = assign_product_slots(volume, past_volume=past_volume)
    cells = build_product_share_cells(
        combine_product_volume(volume, past_volume),
        PRODUCT_SHARE_BASIS_PKG,
        slots,
        month_labels=["26.08", "26.09"],
    )

    entries = product_share_legend(cells)
    past_only = product_share_legend({"26.08": cells["26.08"]})

    named = [(name, slot) for name, slot in entries if slot is not None]
    assert len({slot for _, slot in named}) == len(named) == PRODUCT_SHARE_SLOT_COUNT
    assert (f"DEMO_PART ({PART_A})", slots.slot[f"DEMO_PART ({PART_A})"]) in entries
    assert MARKER not in {name for name, _ in entries}
    assert (MARKER, slots.slot[MARKER]) in past_only


def test_a_past_marker_keeps_the_old_rule_when_every_part_is_folded() -> None:
    """그 제품의 부품이 모두 `기타` 로 접혔으면 빌릴 칸이 없다 — 과거 「DEMO_PART (-)」 는 지금
    규칙(남는 칸이 있을 때만 받음) 그대로라 이 견본에서는 `기타` 다."""
    others = [(f"DEMO_{index}", "-", 100.0 + index) for index in range(PRODUCT_SHARE_SLOT_COUNT)]
    volume, past_volume = _slot_volumes(
        [*others, ("DEMO_PART", PART_A, 2.0), ("DEMO_PART", PART_B, 1.0)],
        [("DEMO_PART", 300.0), ("DEMO_0", 10.0)],
    )

    slots = assign_product_slots(volume, past_volume=past_volume)

    assert {f"DEMO_PART ({PART_A})", f"DEMO_PART ({PART_B})"} <= slots.folded
    assert MARKER in slots.folded
    assert not slots.lenders and MARKER not in slots.slot


def test_a_past_marker_with_room_borrows_and_leaves_its_own_slot_empty() -> None:
    """남는 칸이 있어 지금 규칙이면 제 칸을 받았을 「DEMO_PART (-)」 도 첫 부품의 칸을 빌린다 — 그
    칸은 비워 두어 뒤의 과거 전용 제품(DEMO_R)의 칸 · 색이 빌리지 않은 배정과 같다."""
    volume, past_volume = _slot_volumes(
        [("DEMO_PART", PART_A, 300.0), ("DEMO_PART", PART_B, 200.0), ("DEMO_Q", "-", 100.0)],
        [("DEMO_PART", 300.0), ("DEMO_R", 50.0)],
    )

    slots = assign_product_slots(volume, past_volume=past_volume)

    part_a = f"DEMO_PART ({PART_A})"
    assert slots.order == (part_a, f"DEMO_PART ({PART_B})", "DEMO_Q", "DEMO_R")
    assert slots.slot["DEMO_R"] == 4
    assert slots.slot[MARKER] == slots.slot[part_a] == 0
    assert dict(slots.fallback) == {MARKER: 3}
    assert not slots.folded


def test_a_calculated_marker_part_is_not_a_borrower() -> None:
    """표지 `-` 를 부품 하나로 든 제품(계산 구간에 「DEMO_PART (-)」 가 있는 제품)의 「(-)」 는 과거
    전용이 아니라 제 칸을 받는다 — 이름 끝 「(-)」 로 빌릴 이름을 고르지 않는다."""
    volume, past_volume = _slot_volumes(
        [("DEMO_PART", PART_A, 300.0), ("DEMO_PART", "-", 200.0), ("DEMO_Q", "-", 100.0)],
        [("DEMO_PART", 300.0)],
    )

    slots = assign_product_slots(volume, past_volume=past_volume)

    assert MARKER in slots.order
    assert not slots.lenders
    assert slots.slot[MARKER] != slots.slot[f"DEMO_PART ({PART_A})"]


@pytest.mark.parametrize("with_room", [False, True])
def test_a_marker_sharing_a_donut_with_its_lender_does_not_borrow_there(with_room: bool) -> None:
    """한 도넛(한 칸 · 한 달)에 빌려 준 부품 조각과 「DEMO_PART (-)」 조각이 함께 서면 그 칸에서는
    빌리지 않고 지금 규칙(제 칸 · 없으면 `기타`)을 쓴다 — 같은 색 두 조각이 서지 않는다. 화면의
    수량은 달마다 계산 · 과거 가운데 하나지만, 함께 오는 값도 칸이 막는다. 과거 달만 선 칸은
    그대로 빌린다."""
    if with_room:
        volume, past_volume = _slot_volumes(
            [("DEMO_PART", PART_A, 300.0), ("DEMO_PART", PART_B, 200.0), ("DEMO_Q", "-", 100.0)],
            [("DEMO_PART", 300.0), ("DEMO_R", 50.0)],
        )
    else:
        volume, past_volume = _full_slots()
    slots = assign_product_slots(volume, past_volume=past_volume)
    part_a = f"DEMO_PART ({PART_A})"
    mixed = combine_product_volume(
        volume, past_volume, past_volume.assign(생산계획년월=202609, 과거=False)
    )

    cells = build_product_share_cells(
        mixed, PRODUCT_SHARE_BASIS_PKG, slots, month_labels=["26.08", "26.09"]
    )

    shared = cells["26.09"]
    drawn = [piece.slot for piece in shared.slices if piece.slot is not None]
    assert len(drawn) == len(set(drawn))
    assert {piece.product for piece in shared.slices} >= {part_a}
    marker_pieces = [piece for piece in shared.slices if piece.product == MARKER]
    if with_room:
        assert [piece.slot for piece in marker_pieces] == [slots.fallback[MARKER]]
        assert marker_pieces[0].lender == ""
    else:
        assert not marker_pieces
        other = next(piece for piece in shared.slices if piece.product == OTHER_PRODUCT_LABEL)
        assert MARKER in {name for name, _ in other.members}
    assert sum(piece.share for piece in shared.slices) == pytest.approx(1.0)
    alone = next(piece for piece in cells["26.08"].slices if piece.product == MARKER)
    assert alone.slot == slots.slot[part_a] and alone.lender == part_a


# ---------------------------------------------------------------- 칸이 넘칠 때 — 부품 단위 기타


def test_parts_fold_into_other_one_by_one_beyond_the_slot_count() -> None:
    """칸이 넘치면 부품 하나를 제품 하나처럼 물량 순으로 `기타` 에 접는다(D2 (가)) — 한 제품의
    부품이 이름 있는 칸과 `기타` 에 걸칠 수 있다."""
    others = [f"DEMO_{index}" for index in range(PRODUCT_SHARE_SLOT_COUNT - 1)]
    rows = [(202609, name, "-", 100.0 + index) for index, name in enumerate(others)]
    rows += [(202609, "DEMO_PART", PART_A, 500.0), (202609, "DEMO_PART", PART_B, 1.0)]
    plan = pd.DataFrame(rows, columns=["생산계획년월", "제품정보", "CUSTOM", "생산수량"])
    wafer = plan.rename(columns={"생산수량": "물량"})
    volume = build_product_volume(plan, wafer, multi_part=frozenset({"DEMO_PART"}))

    slots = assign_product_slots(volume)
    cells = build_product_share_cells(volume, "Wafer", slots, month_labels=["26.09"])

    assert len(slots.order) == PRODUCT_SHARE_SLOT_COUNT - 1
    assert "DEMO_PART (DEMO_CUSTOM_A)" in slots.order
    assert "DEMO_PART (DEMO_CUSTOM_B)" in slots.folded
    pieces = cells["26.09"].slices
    assert pieces[-1].product == OTHER_PRODUCT_LABEL
    assert "DEMO_PART (DEMO_CUSTOM_B)" in {name for name, _ in pieces[-1].members}
    assert sum(piece.value for piece in pieces) == pytest.approx(float(plan["생산수량"].sum()))


def _folded_part_cell(names: list[str]) -> ProductShareCell:
    """칸이 넘쳐 부품 하나(「DEMO_PART (DEMO_CUSTOM_B)」)가 `기타` 에 접힌 칸 — 함께 접히는 제품
    `names` 는 그 부품보다 작아 풍선에서 부품 뒤에 선다."""
    others = [f"DEMO_{index}" for index in range(PRODUCT_SHARE_SLOT_COUNT - 1)]
    rows = [(202609, name, "-", 100.0 + index) for index, name in enumerate(others)]
    rows += [(202609, name, "-", 0.5 + 0.1 * index) for index, name in enumerate(names)]
    rows += [(202609, "DEMO_PART", PART_A, 500.0), (202609, "DEMO_PART", PART_B, 2.0)]
    plan = pd.DataFrame(rows, columns=["생산계획년월", "제품정보", "CUSTOM", "생산수량"])
    volume = build_product_volume(
        plan, plan.rename(columns={"생산수량": "물량"}), multi_part=frozenset({"DEMO_PART"})
    )
    return build_product_share_cells(
        volume, "Wafer", assign_product_slots(volume), month_labels=["26.09"]
    )["26.09"]


def _other_hover(cell: ProductShareCell) -> list[str]:
    traces = product_share_traces(
        {"26.09": cell}, ["26.09"], basis="Wafer", year_totals=(), past_month_labels=None
    )
    hover = next(text for text in traces[0].hovertext if f" · {OTHER_PRODUCT_LABEL} " in text)
    return str(hover).split("<br>")


def test_an_other_hover_naming_a_part_carries_the_amounts_on_its_first_line() -> None:
    """부품 이름표가 낀 `기타` 풍선은 수량을 첫 줄로 올리고 둘째 줄에 접힌 이름만 싣는다 — 이름표가
    길어 수량과 이름을 한 줄에 이으면 풍선이 넓어져 왼쪽 고정 구분 칸 밑으로 앞머리가
    잘렸다(2026-11-24 그림 확인). 두 줄 그대로이고 접힌 이름 · 「외 N」 은 그대로 다 싣는다. 부품이
    없는 `기타` 풍선도 같은 꼴이다(아래 시험)."""
    cell = _folded_part_cell(["DEMO_X", "DEMO_Y", "DEMO_Z"])

    first, second = _other_hover(cell)

    assert first.startswith(f"26.09 · {OTHER_PRODUCT_LABEL} ")
    assert " · Wafer " in first and " / " in first
    assert " / " not in second
    assert f"DEMO_PART ({PART_B})" in second
    assert " 외 " in second
    # 옛 꼴의 둘째 줄은 「수량 · 이름들」 — 새 꼴의 가장 넓은 줄이 그보다 좁아야 풍선이 준다.
    amounts = first[first.index(" · Wafer ") + len(" · ") :]
    old_widest = _text_width_units(f"{amounts} · {second}")
    assert max(_text_width_units(first), _text_width_units(second)) < old_widest


def test_an_other_hover_without_a_part_takes_the_same_two_lines() -> None:
    """부품 이름표가 없는 `기타` 풍선도 같은 꼴이다 — 첫 줄 「달 · 기타 비중 · 수량」, 둘째 줄 접힌
    이름만(2026-11-24 그림 보드 3 답 q7-other-hover (나)). 글은 옛 꼴(둘째 줄에 수량 · 이름)과 같고
    줄만 바뀐다 — 이름은 줄이지 않는다."""
    others = [f"DEMO_{index}" for index in range(PRODUCT_SHARE_SLOT_COUNT + 2)]
    plan = pd.DataFrame(
        [(202609, name, "-", 10.0 * (index + 1)) for index, name in enumerate(others)],
        columns=["생산계획년월", "제품정보", "CUSTOM", "생산수량"],
    )
    volume = build_product_volume(plan, plan.rename(columns={"생산수량": "물량"}))
    cell = build_product_share_cells(
        volume, "Wafer", assign_product_slots(volume), month_labels=["26.09"]
    )["26.09"]

    first, second = _other_hover(cell)

    other = cell.slices[-1]
    head = f"26.09 · {OTHER_PRODUCT_LABEL} {other.share:.1%}"
    amounts = f"Wafer {other.value / 1000:,.1f}K / {cell.total / 1000:,.1f}K"
    names = ", ".join(f"{name} {value / cell.total:.1%}" for name, value in other.members[:3])
    rest = len(other.members) - 3
    names += f" 외 {rest}" if rest > 0 else ""
    # 글은 옛 꼴(「head」 · 「수량 · 이름들」)과 같고 수량이 첫 줄로 올라왔을 뿐이다.
    assert first == f"{head} · {amounts}"
    assert second == names


def test_a_past_pkg_other_hover_takes_the_same_two_lines() -> None:
    """과거 달(PKG) 도넛의 `기타` 풍선도 같은 꼴이다 — 첫 줄 「달 · 기타 비중 · 수량 · 과거
    입력값」, 둘째 줄 접힌 이름만(그림 보드 3 답 q7-other-hover (나) — 과거 달 도넛도 같은
    그리기)."""
    past = pd.DataFrame(
        {
            "생산계획년월": [202510] * (PRODUCT_SHARE_SLOT_COUNT + 2),
            "제품정보": [f"DEMO_{index}" for index in range(PRODUCT_SHARE_SLOT_COUNT + 2)],
            "Stack": ["12H"] * (PRODUCT_SHARE_SLOT_COUNT + 2),
            "Customer": ["DEMO-CUST"] * (PRODUCT_SHARE_SLOT_COUNT + 2),
            "생산수량": [10.0 * (index + 1) for index in range(PRODUCT_SHARE_SLOT_COUNT + 2)],
        }
    )
    past_volume = past_product_volume(
        past, start_month=202510, end_month=202512, exclude_months=set()
    )
    slots = assign_product_slots(past_volume.iloc[0:0], past_volume=past_volume)
    cell = build_product_share_cells(
        past_volume, PRODUCT_SHARE_BASIS_PKG, slots, month_labels=["25.10"]
    )["25.10"]
    traces = product_share_traces(
        {"25.10": cell},
        ["25.10"],
        basis=PRODUCT_SHARE_BASIS_PKG,
        year_totals=(),
        past_month_labels={"25.10"},
    )
    hover = next(text for text in traces[0].hovertext if f" · {OTHER_PRODUCT_LABEL} " in text)
    first, second = str(hover).split("<br>")

    assert cell.past
    assert first.startswith(f"25.10 · {OTHER_PRODUCT_LABEL} ")
    assert f" · {PRODUCT_SHARE_BASIS_PKG} " in first and first.endswith(" · 과거 입력값")
    assert " / " not in second and "과거 입력값" not in second
    assert second.startswith("DEMO_")


# ---------------------------------------------------------------- 범례 · 풍선


def _two_part_cells() -> dict[str, ProductShareCell]:
    tables = two_part_tables()
    _, volume, _ = _home(tables)
    slots = assign_product_slots(volume, tables["RQ_DISPLAY_ORDER"])
    return build_product_share_cells(volume, "Wafer", slots, month_labels=_labels(tables))


def test_a_narrow_legend_still_tells_the_parts_apart() -> None:
    """범례 한 칸은 부품 이름만으로도 넘친다 — 부품의 구별되는 끝을 남기고, 풍선에 전체 이름표."""
    cells = _two_part_cells()
    budget = _legend_name_budget_units()

    annotations = _product_share_label_annotations(cells, "Wafer", row_top=0.3)

    by_name = {
        entry["hovertext"]: entry["text"].rsplit("</span> ", 1)[1]
        for entry in annotations[1:]
        if entry.get("hovertext") in (LABEL_A, LABEL_B)
    }
    assert set(by_name) == {LABEL_A, LABEL_B}
    assert by_name[LABEL_A] != by_name[LABEL_B]
    for label, fitted in by_name.items():
        assert fitted.endswith(f"{label[-2]})")
        assert _text_width_units(fitted) <= budget
    assert [name for name, _ in product_share_legend(cells)][:2] == [LABEL_A, LABEL_B]


# 같은 제품의 두 부품이 끝 글자를 길게 같이 쓴다 — 끝을 남기는 줄임만으로는 둘이 같은 글이 된다.
TAIL_SHARING_PARTS = ("DEMO_P1_CUSTOM_KIT", "DEMO_P2_CUSTOM_KIT")


def test_a_narrow_legend_tells_apart_parts_that_share_their_end() -> None:
    """범례 한 칸에서 끝을 같이 쓰는 두 부품은 끝에서부터 처음 갈리는 글자부터 남긴다 — 서로 다른
    글이고 칸 폭 안이다. 끝이 다른 부품(「DEMO_CUSTOM_A」 · 「DEMO_CUSTOM_B」)은 지금 꼴
    그대로다."""
    labels = [f"{TWO_PART_PRODUCT} ({part})" for part in TAIL_SHARING_PARTS]
    cell = ProductShareCell(
        label="26.09",
        total=2.0,
        slices=tuple(
            ProductShareSlice(label, 1.0, 0.5, slot, base_product=TWO_PART_PRODUCT, part=part)
            for slot, (label, part) in enumerate(zip(labels, TAIL_SHARING_PARTS, strict=True))
        ),
    )
    budget = _legend_name_budget_units()

    annotations = _product_share_label_annotations({"26.09": cell}, "Wafer", row_top=0.3)

    fitted = {
        entry["hovertext"]: entry["text"].rsplit("</span> ", 1)[1]
        for entry in annotations[1:]
        if entry.get("hovertext") in labels
    }
    assert set(fitted) == set(labels)
    assert len(set(fitted.values())) == 2
    for label, part in zip(labels, TAIL_SHARING_PARTS, strict=True):
        assert part[6] in fitted[label]  # 「P1」 · 「P2」 의 갈리는 글자
        assert _text_width_units(fitted[label]) <= budget


def test_the_hover_stays_two_lines_and_names_the_part() -> None:
    cells = _two_part_cells()
    labels = list(cells)

    traces = product_share_traces(
        cells, labels, basis="Wafer", year_totals=(), past_month_labels=None
    )

    first = traces[0]
    hovers = list(first.hovertext)
    names = list(first.labels)
    assert LABEL_A in names and LABEL_B in names
    for name, hover in zip(names, hovers, strict=True):
        assert hover.count("<br>") == 1
        assert f" · {name} " in hover


# ---------------------------------------------------------------- 입장 화면 Summary


def test_the_summary_donut_names_each_part_and_still_sums_to_one() -> None:
    tables = two_part_tables()
    months = _months(tables)
    monthly_wafer, slot_volume, without_edp = _home(tables)
    density = pd.DataFrame({"생산계획년월": months, "부하량": [10.0] * len(months)})
    securement = pd.DataFrame(
        [(month, "P-A", 1.2, 30.0, 25.0) for month in months],
        columns=["생산계획년월", "공정", "확보율", "가용대수", "소요대수"],
    )
    thresholds = SecurementThresholds(1.095, 0.995)

    summary = build_official_summary(
        months=months,
        monthly_density=density,
        monthly_wafer=monthly_wafer,
        securement_rate=securement,
        product_volume=without_edp,
        slot_volume=slot_volume,
        display_order=tables["RQ_DISPLAY_ORDER"],
        included_processes=["P-A"],
        thresholds=thresholds,
    )
    payload = summary_payload(
        summary,
        release_name="공식 v1",
        scenario_name="DEMO",
        thresholds=thresholds,
        process_label=str,
    )

    names = [entry["name"] for entry in payload["products"]]
    assert names.index(LABEL_B) == names.index(LABEL_A) + 1
    for month in payload["mix"]:
        assert sum(share for _, share in month) == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------- HOME 진입


# 부품을 가른 제품의 과거 달 조각 이름(과거 입력에는 부품이 없다).
PAST_MARKER = "DEMO PRODUCT A (-)"


def _store_past_plan(database_path: Path) -> None:
    """두 달 과거 구간(제품별 PKG — 부품 없음)을 공용 과거 구간 프로필에 넣는다."""
    past_months = [202511, 202512]
    DuckDBScenarioRepository(database_path).replace_global_past_data(
        {
            "월별": pd.DataFrame(
                {
                    "생산계획년월": past_months,
                    "Density": [8.0, 9.0],
                    "Wafer Total": [100_000.0, 110_000.0],
                }
            ),
            "계획": pd.DataFrame(
                {
                    "생산계획년월": [month for month in past_months for _ in range(2)],
                    "제품정보": [TWO_PART_PRODUCT, "DEMO PRODUCT B"] * 2,
                    "Stack": ["12H"] * 4,
                    "Customer": ["DEMO-CUST"] * 4,
                    "생산수량": [100.0, 50.0, 120.0, 60.0],
                }
            ),
            "확보율": empty_past_table(PAST_SECUREMENT_COLUMNS),
        },
        source="시험",
    )


def _home_with_past_months(database_path: Path) -> AppTest:
    """HOME 을 열고 조회기간을 과거 달까지 넓혀 PKG 단위로 다시 그린 AppTest.

    첫 회차가 리비전 프리셋의 조회기간(계획 달)을 건다 — 과거 달까지 넓힌다. 과거 구간은 제품별
    PKG 만 있어 Wafer 단위면 과거 달 도넛이 서지 않는다."""
    app = AppTest.from_string(home_script(database_path), default_timeout=300).run()
    app.session_state[MONTH_RANGE_KEY] = ("2025-11", "2026-12")
    app.session_state[PRODUCT_SHARE_BASIS_KEY] = PRODUCT_SHARE_BASIS_PKG
    return app.run()


def _month_pie_labels(app: AppTest) -> set[str]:
    return {
        str(label)
        for trace in app.session_state["spy_figures"]["production_lob_months"].data
        if isinstance(trace, go.Pie)
        for label in trace.labels
    }


def test_home_draws_one_donut_slice_and_legend_entry_per_part(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario.duckdb"
    publish_two_part_revision(database_path)

    app = AppTest.from_string(home_script(database_path), default_timeout=300).run()

    assert not list(app.exception)
    figures = app.session_state["spy_figures"]
    month_figure = figures["production_lob_months"]
    pies = [trace for trace in month_figure.data if isinstance(trace, go.Pie)]
    assert pies
    assert all({LABEL_A, LABEL_B} <= set(pie.labels) for pie in pies)
    legend = [
        str(entry.hovertext or entry.text)
        for entry in figures["production_lob_labels"].layout.annotations
    ]
    assert any(LABEL_A in text for text in legend)
    assert any(LABEL_B in text for text in legend)


def test_home_names_the_past_of_a_split_product_with_the_marker(tmp_path: Path) -> None:
    """Past Data 를 켠 HOME 은 부품을 가르는 제품의 과거 달을 「제품 (-)」 조각 · 줄로 그린다 —
    페이지가 리비전 계획 전체로 낸 판정을 과거 조각(`past_product_volume`)과 계획 세부수량 과거
    열(`past_plan_detail_to_wide`)에 넘기는지 본다. 판정이 비면 과거가 접힌 제품 이름(그 제품
    전체처럼 읽히는 줄 · 새 색 칸)으로 선다."""
    database_path = tmp_path / "scenario.duckdb"
    publish_two_part_revision(database_path)
    _store_past_plan(database_path)

    app = _home_with_past_months(database_path)

    assert not list(app.exception)
    figures = app.session_state["spy_figures"]
    marker = PAST_MARKER
    pie_labels = _month_pie_labels(app)
    assert marker in pie_labels
    assert TWO_PART_PRODUCT not in pie_labels
    # 과거 달 「(-)」 조각은 그 제품 첫 부품의 색을 빌린다(그림 보드 3 답 q7-past-slice) — 다른
    # 제품의 색과는 겹치지 않는다.
    colors: dict[str, set[str]] = {}
    for trace in figures["production_lob_months"].data:
        if isinstance(trace, go.Pie):
            for label, color in zip(trace.labels, trace.marker.colors, strict=True):
                colors.setdefault(str(label), set()).add(str(color))
    assert len(colors[marker]) == 1
    sharing = {label for label, found in colors.items() if found & colors[marker]} - {marker}
    assert len(sharing) == 1
    assert next(iter(sharing)).startswith(f"{TWO_PART_PRODUCT} (")
    # 계획 세부수량 제품 칸은 부품 이름표에 맞춰 넓어져(그림 보드 3 답 q7-narrow-label) 「(-)」 줄
    # 이름이 칸에 다 들면 풍선 없이 칸 글로 선다 — 칸 글과 풍선을 함께 본다.
    named = {
        str(name).replace("<br>", " ")
        for trace in figures["production_detail_labels"].data
        if trace.type in {"bar", "scatter"}
        for name in (trace.hovertext if trace.type == "bar" else trace.text)
    }
    assert marker in named
    assert TWO_PART_PRODUCT not in named


def test_home_judges_the_past_parts_again_after_an_edit_in_the_same_scenario(
    tmp_path: Path,
) -> None:
    """과거 열 · 조각의 부품 판정 메모(`home._remembered("product_parts", …)`)는 HOME 계산 키의 계산
    토큰으로 갈린다. 시나리오를 바꾸면 메모 칸이 지워지지만(`_STALE_VALUE_KEYS`), 같은 시나리오에서
    편집을 적용하면 내용 토큰만 바뀌고 메모 칸은 남는다 — 그때 앞 판정이 남으면 둘째 부품을 넣은
    제품의 과거 달이 「제품 (-)」 가 아니라 접힌 제품 이름(그 제품 전체처럼 읽히는 조각 · 새 색
    칸)으로 선다. 한 값 시드로 메모를 채운 뒤 같은 시나리오에 두 부품 표를 적용해 다시 그린다."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario
    from capa_simulation.persistence.cache import get_scenario_repository
    from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY

    database_path = tmp_path / "scenario.duckdb"
    ensure_initial_scenario(get_scenario_repository(str(database_path)))
    _store_past_plan(database_path)

    app = _home_with_past_months(database_path)
    assert not list(app.exception)
    before = _month_pie_labels(app)
    assert TWO_PART_PRODUCT in before
    assert PAST_MARKER not in before

    # 편집 적용(`scenario_state.apply_table_updates`)과 같은 꼴 — 같은 시나리오 · 다음 revision · 새
    # 내용 토큰 · 표만 갈아끼움. 시나리오를 바꾸는 길이 아니라 세션 칸은 지우지 않는다. 세션 표는
    # DB 를 지난 꼴(칸 dtype)이라 편집 화면이 세션 표에서 짓는 편집본처럼 두 부품 표도 그 꼴로
    # 맞춘다.
    active = app.session_state[ACTIVE_SCENARIO_KEY]
    split = two_part_tables()
    tables = dict(active["tables"])
    tables.update(
        {
            name: split[name].astype(tables[name].dtypes.to_dict())
            for name in tables
            if name in split
        }
    )
    app.session_state[ACTIVE_SCENARIO_KEY] = {
        "reference_version": active["reference_version"],
        "revision": active["revision"] + 1,
        "content_token": uuid4().hex,
        "tables": tables,
    }
    app.run()

    assert not list(app.exception)
    after = _month_pie_labels(app)
    assert {LABEL_A, LABEL_B, PAST_MARKER} <= after
    assert TWO_PART_PRODUCT not in after
