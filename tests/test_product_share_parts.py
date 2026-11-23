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
from custom_key_tables import PART_A, PART_B, TWO_PART_PRODUCT, two_part_tables
from streamlit.testing.v1 import AppTest

from capa_simulation.components.home_figure_common import _text_width_units
from capa_simulation.components.home_lob_figures import (
    _legend_name_budget_units,
    _product_share_label_annotations,
    product_share_legend,
    product_share_traces,
)
from capa_simulation.components.intro_summary import summary_payload
from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.dashboard import home_aggregation_wafer_load
from capa_simulation.services.load_calculator import calculate_chip_and_wafer_loads
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.official_summary import build_official_summary
from capa_simulation.services.product_parts import product_part_label
from capa_simulation.services.product_share import (
    OTHER_PRODUCT_LABEL,
    PRODUCT_SHARE_SLOT_COUNT,
    ProductShareCell,
    assign_product_slots,
    build_product_share_cells,
    build_product_volume,
    combine_product_volume,
    past_product_volume,
)
from capa_simulation.services.securement_threshold import SecurementThresholds

LABEL_A = product_part_label(TWO_PART_PRODUCT, PART_A)
LABEL_B = product_part_label(TWO_PART_PRODUCT, PART_B)
HOME_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "home.py"


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
    """이름표는 리비전 계획 전체로 판정한다 — 한 달만 봐도, EDP 를 빼도 같은 이름표다."""
    tables = two_part_tables()
    months = _months(tables)
    _, volume, without_edp = _home(tables)
    _, one_month, one_month_without_edp = _home(tables, start=months[3], end=months[3])

    for frame in (volume, without_edp, one_month, one_month_without_edp):
        rows = frame.loc[frame["제품정보"].eq(TWO_PART_PRODUCT)]
        assert set(rows["CUSTOM"]) == {PART_A, PART_B}


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
        plan = tables["RQ_PKG_PLAN"]
        products = sorted(plan["제품정보"].astype(str).unique())
        plan["CUSTOM"] = plan["제품정보"].map(
            {product: f"DEMO_CUSTOM_{index}" for index, product in enumerate(products)}
        )
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
    """과거 입력에는 부품이 없어 「제품 (-)」 조각이다. 과거 전용 이름이라 계산 구간 제품 뒤에서
    칸을 받는다 — Past Data 를 켜도 부품 조각의 색이 그대로다."""
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

    marker = product_part_label(TWO_PART_PRODUCT, "-")
    assert with_past.order[: len(without_past.order)] == without_past.order
    assert {name: with_past.slot[name] for name in without_past.order} == dict(without_past.slot)
    assert with_past.order[-1] == marker
    cells = build_product_share_cells(
        combine_product_volume(volume, past_volume),
        "PKG",
        with_past,
        month_labels=[month_label(months[0] - 100), *_labels(tables)],
    )
    past_cell = cells[month_label(months[0] - 100)]
    assert past_cell.past
    assert {piece.product for piece in past_cell.slices} == {marker, "DEMO PRODUCT B"}


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
    assert product_part_label("DEMO_PART", PART_A) in slots.order
    assert product_part_label("DEMO_PART", PART_B) in slots.folded
    pieces = cells["26.09"].slices
    assert pieces[-1].product == OTHER_PRODUCT_LABEL
    assert product_part_label("DEMO_PART", PART_B) in {name for name, _ in pieces[-1].members}
    assert sum(piece.value for piece in pieces) == pytest.approx(float(plan["생산수량"].sum()))


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


def _home_script(database_path: Path) -> str:
    """app.py 의 전역 준비만 재현하고 HOME 을 돌린다 — `Capa LOB 현황` 두 그림을 key 로 남긴다.

    Components v2 가로 스크롤바는 AppTest 인스턴스마다 등록이 남지 않아 빈 스텁으로 둔다."""
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

st.session_state["spy_figures"] = {{}}
_original_plotly_chart = st.plotly_chart


def _spy_plotly_chart(figure, *args, **kwargs):
    st.session_state["spy_figures"] = {{
        **st.session_state["spy_figures"],
        kwargs.get("key"): figure,
    }}
    return _original_plotly_chart(figure, *args, **kwargs)


st.plotly_chart = _spy_plotly_chart
_original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
horizontal_scrollbar.render_horizontal_scrollbar = lambda *_args, **_kwargs: None
try:
    page_source = Path({str(HOME_PAGE)!r}).read_text(encoding="utf-8")
    exec(compile(page_source, {str(HOME_PAGE)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    st.plotly_chart = _original_plotly_chart
    horizontal_scrollbar.render_horizontal_scrollbar = _original_scrollbar
"""


def _publish_two_part_revision(database_path: Path) -> None:
    """내장 시드를 부트스트랩한 DB 에 두 부품 표를 새 공식버전으로 발행한다."""
    from capa_simulation.persistence.cache import load_scenario_snapshot
    from capa_simulation.persistence.models import ScenarioCreate
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.scenario_activation import bootstrap_latest_official_scenario

    bootstrap_latest_official_scenario(str(database_path))
    repository = DuckDBScenarioRepository(database_path)
    official = repository.latest_official_release()
    assert official is not None
    snapshot = load_scenario_snapshot(str(database_path), official.revision_id)
    tables = dict(snapshot.tables)
    split = two_part_tables()
    tables.update({name: split[name] for name in tables if name in split})
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name="두 부품 계획",
            source_simulation_code="DEMO-TWO-PART",
            source_simulation_name="두 부품 계획",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        tables,
        snapshot.preset,
    )
    repository.publish_official_revision(
        str(created.scenario.scenario_id),
        str(created.revision.revision_id),
        release_name="두 부품 계획",
    )


def test_home_draws_one_donut_slice_and_legend_entry_per_part(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario.duckdb"
    _publish_two_part_revision(database_path)

    app = AppTest.from_string(_home_script(database_path), default_timeout=300).run()

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
