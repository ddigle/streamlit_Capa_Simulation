# Purpose: HOME Figure 묶음별 캐시의 의존 표·테마·스키마 분리, LRU 와 세션 공유를 검증한다.

import pickle
from typing import Any, TypeVar, cast

import plotly.graph_objects as go
import pytest
import streamlit as st

from capa_simulation.components import home_rendering
from capa_simulation.components.home_rendering import (
    BOTTLENECK_FIGURES,
    HOME_FIGURE_BUNDLES,
    HOME_FIGURE_CACHE_MAX_ENTRIES,
    HOME_FIGURE_SCHEMA_VERSION,
    KEY_PROCESS_FIGURES,
    LOB_FIGURES,
    PLAN_DETAIL_FIGURES,
    BottleneckFigures,
    HomeFigureBaseKey,
    HomeFigureBundle,
    HomeFigureCacheKey,
    KeyProcessFigures,
    LobFigures,
    PlanDetailFigures,
    home_figure_cache,
    home_figure_key,
    latest_home_figure_key,
    store_home_figures,
    take_home_figures,
)
from capa_simulation.design import theme
from capa_simulation.io.reference_cache import HOME_FIGURE_CACHE_KEY
from capa_simulation.services.simulation_cache import SharedBlobStore

LOB = LOB_FIGURES.name
PLAN = PLAN_DETAIL_FIGURES.name
KEY_PROCESS = KEY_PROCESS_FIGURES.name
BOTTLENECK = BOTTLENECK_FIGURES.name
ALL = frozenset({LOB, PLAN, KEY_PROCESS, BOTTLENECK})

# 조건 하나를 바꿨을 때 키가 바뀌어야 하는 묶음. `home_rendering` 의 의존 표를 그대로 옮겨 적은
# **두 번째 사본**이다 — 표나 키 정의를 바꾸면 여기도 같이 고쳐야 통과하므로, 칸 하나를 조용히
# 빼서 옛 그림이 나오게 되는 일이 리뷰 없이 지나가지 못한다. `include_edp` 는 선행 B/O 에 따라
# 갈려 아래 테스트가 따로 본다.
EXPECTED_DEPENDENTS: dict[str, frozenset[str]] = {
    "schema_version": ALL,
    "process_label_version": frozenset({LOB, KEY_PROCESS, BOTTLENECK}),
    "reference_version": ALL,
    "content_token": ALL,
    "start_month": ALL,
    "end_month": ALL,
    "display_order_digest": ALL,
    "included_processes": frozenset({LOB, BOTTLENECK}),
    "threshold_digest": frozenset({LOB, KEY_PROCESS, BOTTLENECK}),
    "plan_detail_customer": frozenset({PLAN}),
    "comparison_revision_id": frozenset({LOB, PLAN}),
    "show_advance": frozenset({LOB, KEY_PROCESS, BOTTLENECK}),
    "advance_profile_version": frozenset({LOB, KEY_PROCESS, BOTTLENECK}),
    "show_execution": frozenset({LOB, KEY_PROCESS, BOTTLENECK}),
    "execution_profile_version": frozenset({LOB, KEY_PROCESS, BOTTLENECK}),
    "top5_band_version": frozenset({LOB}),
    "top5_min_rate": frozenset({LOB}),
    "top5_max_rate": frozenset({LOB}),
    "past_profile_version": ALL,
    "key_processes": frozenset({KEY_PROCESS}),
    "key_process_profile_version": frozenset({KEY_PROCESS}),
    "product_share_basis": frozenset({LOB}),
    "show_advance_shipment": frozenset({LOB}),
    "advance_shipment_profile_version": frozenset({LOB}),
    "key_process_empty_notice": frozenset({KEY_PROCESS}),
    "month_labels": ALL,
    "year_total_labels": ALL,
    "past_month_labels": ALL,
    "gap_month_labels": ALL,
}


@pytest.fixture
def conditions(monkeypatch: pytest.MonkeyPatch) -> HomeFigureCacheKey:
    monkeypatch.setattr(st, "session_state", {})
    monkeypatch.setattr(theme, "current_mode", lambda: "light")
    return HomeFigureCacheKey(
        schema_version=HOME_FIGURE_SCHEMA_VERSION,
        process_label_version=2,
        reference_version=3,
        content_token="content-a",
        start_month=202601,
        end_month=202612,
        display_order_digest="display-order",
        included_processes=("DEMO_A", "DEMO_B"),
        threshold_digest="threshold-digest",
        include_edp=False,
        plan_detail_customer=True,
        comparison_revision_id="comparison-revision",
        show_advance=True,
        advance_profile_version=4,
        show_execution=True,
        execution_profile_version=5,
        top5_band_version=6,
        top5_min_rate=0.9,
        top5_max_rate=1.2,
        past_profile_version=7,
        key_processes=("DEMO_B", "DEMO_A"),
        key_process_profile_version=8,
        product_share_basis="Wafer",
        show_advance_shipment=True,
        advance_shipment_profile_version=9,
        key_process_empty_notice="안내",
        month_labels=("25.12", "26.01", "26.02"),
        year_total_labels=(),
        past_month_labels=("25.12",),
        gap_month_labels=("26.01", "26.02"),
    )


FiguresT = TypeVar("FiguresT", bound=tuple[Any, ...])


def _figures(bundle: HomeFigureBundle[Any, FiguresT]) -> FiguresT:
    """그 묶음 모양의 빈 Figure 묶음. 덤벨 칸도 Figure 로 채운다."""
    fields: tuple[str, ...] = cast(Any, bundle.figures_type)._fields
    return cast(FiguresT, cast(Any, bundle.figures_type)(**{name: go.Figure() for name in fields}))


def _changed(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 0.05
    if isinstance(value, str):
        return value + "-changed"
    if isinstance(value, tuple):
        return (*value, "DEMO_NEW")
    raise TypeError(type(value))


def _dependents(before: HomeFigureCacheKey, after: HomeFigureCacheKey) -> frozenset[str]:
    return frozenset(
        bundle.name
        for bundle in HOME_FIGURE_BUNDLES
        if home_figure_key(bundle, before) != home_figure_key(bundle, after)
    )


def test_every_condition_reaches_the_bundles_the_dependency_table_names(
    conditions: HomeFigureCacheKey,
) -> None:
    """조건을 하나씩 바꿔 어느 묶음의 키가 바뀌는지가 의존 표와 같아야 한다.

    새 조건을 `HomeFigureCacheKey` 에 더하고 어느 묶음에도 넣지 않으면 그 조건을 바꿔도 옛 그림이
    나온다. 표에 없는 칸은 여기서 KeyError 로 먼저 드러난다.
    """
    for field in HomeFigureCacheKey._fields:
        if field == "include_edp":
            continue
        changed = conditions._replace(**{field: _changed(getattr(conditions, field))})
        assert _dependents(conditions, changed) == EXPECTED_DEPENDENTS[field], field


def test_edp_reaches_the_heatmap_only_through_the_advance_ratio(
    conditions: HomeFigureCacheKey,
) -> None:
    """선행 B/O 변동률은 화면 계획(EDP 를 뺀 화면이면 뺀 계획)으로 내어 확보율에 곱한다.

    그래서 선행을 켠 동안에는 EDP 가 히트맵까지 닿고, 끈 동안에는 닿지 않는다.
    """
    advance_on = conditions._replace(show_advance=True)
    assert _dependents(advance_on, advance_on._replace(include_edp=True)) == ALL

    advance_off = conditions._replace(show_advance=False, advance_profile_version=0)
    assert _dependents(advance_off, advance_off._replace(include_edp=True)) == frozenset(
        {LOB, PLAN, BOTTLENECK}
    )


def test_each_bundle_key_names_only_conditions_and_the_base_covers_the_axis() -> None:
    """묶음 키의 칸 이름은 화면 조건(또는 그 위의 접은 값)이어야 한다 — 이름으로 골라 담는다."""
    names = set(HomeFigureCacheKey._fields) | {"advance_ratio_includes_edp"}
    for bundle in HOME_FIGURE_BUNDLES:
        fields: tuple[str, ...] = bundle.key_type._fields
        assert fields[0] == "base", bundle.name
        assert set(fields[1:]) <= names, bundle.name
    assert set(HomeFigureBaseKey._fields) <= set(HomeFigureCacheKey._fields)
    assert {"month_labels", "past_month_labels", "gap_month_labels"} <= set(
        HomeFigureBaseKey._fields
    )


def test_each_bundle_keeps_each_theme_separate(
    conditions: HomeFigureCacheKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for bundle in HOME_FIGURE_BUNDLES:
        light = _figures(bundle)
        store_home_figures(bundle, conditions, light)
        monkeypatch.setattr(theme, "current_mode", lambda: "dark")
        assert take_home_figures(bundle, conditions) is None

        dark = _figures(bundle)
        store_home_figures(bundle, conditions, dark)
        assert take_home_figures(bundle, conditions) is dark
        monkeypatch.setattr(theme, "current_mode", lambda: "light")
        assert take_home_figures(bundle, conditions) is light


def test_a_toggle_only_misses_the_bundles_it_reaches(conditions: HomeFigureCacheKey) -> None:
    """선행 입고는 LOB 글자만 바꾼다. 다른 세 묶음은 그대로 꺼낸다."""
    stored = {bundle.name: _figures(bundle) for bundle in HOME_FIGURE_BUNDLES}
    for bundle in HOME_FIGURE_BUNDLES:
        store_home_figures(bundle, conditions, stored[bundle.name])

    shipment_off = conditions._replace(
        show_advance_shipment=False, advance_shipment_profile_version=0
    )

    assert take_home_figures(LOB_FIGURES, shipment_off) is None
    others: tuple[HomeFigureBundle[Any, Any], ...] = (
        PLAN_DETAIL_FIGURES,
        KEY_PROCESS_FIGURES,
        BOTTLENECK_FIGURES,
    )
    for bundle in others:
        assert take_home_figures(bundle, shipment_off) is stored[bundle.name]


def test_old_flat_session_cache_is_dropped_for_the_bundle_shape(
    conditions: HomeFigureCacheKey,
) -> None:
    """묶음을 가르기 전 모양((테마, 키) → 여덟 Figure)이 남은 세션은 통째로 버린다.

    그 칸들은 어느 묶음의 LRU 에도 들지 않아 세션이 끝날 때까지 메모리를 잡는다.
    """
    stale: dict[Any, Any] = {("light", tuple(conditions)): tuple(_figures(LOB_FIGURES))}
    st.session_state[HOME_FIGURE_CACHE_KEY] = stale

    assert take_home_figures(LOB_FIGURES, conditions) is None
    figures = _figures(LOB_FIGURES)
    store_home_figures(LOB_FIGURES, conditions, figures)

    root = st.session_state[HOME_FIGURE_CACHE_KEY]
    assert set(root) == {LOB}
    assert take_home_figures(LOB_FIGURES, conditions) is figures


def test_a_new_schema_does_not_reuse_old_figures(conditions: HomeFigureCacheKey) -> None:
    old = conditions._replace(schema_version=HOME_FIGURE_SCHEMA_VERSION - 1)
    store_home_figures(LOB_FIGURES, old, _figures(LOB_FIGURES))

    assert HOME_FIGURE_SCHEMA_VERSION >= 48
    assert take_home_figures(LOB_FIGURES, conditions) is None


def test_each_bundle_evicts_its_own_least_recently_read_entry(
    conditions: HomeFigureCacheKey,
) -> None:
    """칸 수는 묶음마다 따로다. LOB 를 넘치게 채워도 다른 묶음의 칸은 밀려나지 않는다."""
    plan_figures = _figures(PLAN_DETAIL_FIGURES)
    store_home_figures(PLAN_DETAIL_FIGURES, conditions, plan_figures)
    variants = [
        conditions._replace(product_share_basis=f"basis-{index}")
        for index in range(HOME_FIGURE_CACHE_MAX_ENTRIES + 1)
    ]
    lob_figures = _figures(LOB_FIGURES)
    for variant in variants[:-1]:
        store_home_figures(LOB_FIGURES, variant, lob_figures)
    assert take_home_figures(LOB_FIGURES, variants[0]) is lob_figures

    store_home_figures(LOB_FIGURES, variants[-1], lob_figures)

    assert len(home_figure_cache(LOB_FIGURES)) == HOME_FIGURE_CACHE_MAX_ENTRIES
    assert take_home_figures(LOB_FIGURES, variants[1]) is None
    assert take_home_figures(LOB_FIGURES, variants[0]) is lob_figures
    assert take_home_figures(LOB_FIGURES, variants[-1]) is lob_figures
    # 제품별 비중 단위는 계획 세부수량 키에 없으므로 아홉 변형 모두 같은 칸을 본다.
    assert take_home_figures(PLAN_DETAIL_FIGURES, variants[-1]) is plan_figures


def test_the_latest_key_is_the_one_drawn_this_run(conditions: HomeFigureCacheKey) -> None:
    first = conditions._replace(show_advance=False, advance_profile_version=0)
    store_home_figures(LOB_FIGURES, first, _figures(LOB_FIGURES))
    store_home_figures(LOB_FIGURES, conditions, _figures(LOB_FIGURES))
    take_home_figures(LOB_FIGURES, first)

    latest = latest_home_figure_key(st.session_state[HOME_FIGURE_CACHE_KEY], LOB_FIGURES)

    assert latest == home_figure_key(LOB_FIGURES, first)
    assert latest is not None and latest.show_advance is False
    assert latest_home_figure_key(None, LOB_FIGURES) is None


@pytest.fixture
def shared_stores(monkeypatch: pytest.MonkeyPatch) -> dict[str, SharedBlobStore]:
    stores: dict[str, SharedBlobStore] = {}

    def store_for(bundle: str) -> SharedBlobStore:
        return stores.setdefault(bundle, SharedBlobStore(4))

    monkeypatch.setattr(home_rendering, "shared_home_figure_store", store_for)
    return stores


def _new_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(st, "session_state", {})


def test_a_new_session_reuses_each_bundle_drawn_for_the_same_revision(
    conditions: HomeFigureCacheKey,
    shared_stores: dict[str, SharedBlobStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """새로고침은 새 세션이다. 같은 리비전이면 그림을 다시 만들지 않는다 — 묶음마다 따로 나눈다."""
    pristine = conditions._replace(content_token="pristine-3")
    for bundle in HOME_FIGURE_BUNDLES:
        store_home_figures(bundle, pristine, _figures(bundle))

    _new_session(monkeypatch)

    assert set(shared_stores) == ALL
    for bundle in HOME_FIGURE_BUNDLES:
        recalled = take_home_figures(bundle, pristine)
        assert recalled is not None, bundle.name
        assert type(recalled) is bundle.figures_type
        themed_keys = {key for _, key in home_figure_cache(bundle)}
        assert home_figure_key(bundle, pristine) in themed_keys


def test_an_edited_session_keeps_its_figures_to_itself(
    conditions: HomeFigureCacheKey,
    shared_stores: dict[str, SharedBlobStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """편집 토큰의 그림은 남이 쓸 일이 없다. 공용 칸에 넣으면 남의 칸만 밀어낸다."""
    for bundle in HOME_FIGURE_BUNDLES:
        store_home_figures(bundle, conditions, _figures(bundle))

    _new_session(monkeypatch)

    assert all(len(store) == 0 for store in shared_stores.values())
    for bundle in HOME_FIGURE_BUNDLES:
        assert take_home_figures(bundle, conditions) is None


def test_a_shared_recall_is_a_copy_that_cannot_repaint_another_session(
    conditions: HomeFigureCacheKey,
    shared_stores: dict[str, SharedBlobStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pristine = conditions._replace(content_token="pristine-3")
    store_home_figures(LOB_FIGURES, pristine, _figures(LOB_FIGURES))
    _new_session(monkeypatch)
    first = take_home_figures(LOB_FIGURES, pristine)
    assert first is not None
    first.labels.update_layout(title_text="이 세션만 고친 제목")

    _new_session(monkeypatch)
    second = take_home_figures(LOB_FIGURES, pristine)

    assert second is not None
    assert second.labels.layout.title.text is None


def test_a_shared_recall_rebuilds_the_same_figures_from_plain_specs(
    conditions: HomeFigureCacheKey,
    shared_stores: dict[str, SharedBlobStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """공용 칸은 Figure 가 아니라 `to_dict()` 목록을 담고, 꺼낼 때 같은 그림을 다시 세운다.

    빈 Figure 만으로는 저장 형식이 Figure 통째 pickle 로 돌아가도 드러나지 않는다. 막대와
    축 제목이 있는 그림으로 왕복하고, Plotly 비공개 인자 `_validate` 가 사라지면 복원이
    `TypeError` 로 깨져 여기서 먼저 드러난다. 비교가 없을 때의 덤벨(None)은 None 으로 돌아온다.
    """
    drawn = go.Figure(
        go.Bar(x=["DEMO_A", "DEMO_B"], y=[1.5, 2.0], marker={"color": "#336699"}),
        layout={"xaxis": {"title": {"text": "공정"}}, "height": 120},
    )
    pristine = conditions._replace(content_token="pristine-3")
    store_home_figures(
        BOTTLENECK_FIGURES, pristine, BottleneckFigures(labels=go.Figure(), months=drawn)
    )
    store_home_figures(
        PLAN_DETAIL_FIGURES,
        pristine,
        PlanDetailFigures(labels=go.Figure(), months=drawn, comparison_dumbbell=None),
    )

    blob = shared_stores[BOTTLENECK].get(("light", home_figure_key(BOTTLENECK_FIGURES, pristine)))
    assert blob is not None
    specs = pickle.loads(blob)
    assert isinstance(specs, list)
    assert len(specs) == len(BottleneckFigures._fields)
    assert all(type(spec) is dict for spec in specs)

    _new_session(monkeypatch)
    recalled = take_home_figures(BOTTLENECK_FIGURES, pristine)
    plan = take_home_figures(PLAN_DETAIL_FIGURES, pristine)

    assert recalled is not None and plan is not None
    assert isinstance(recalled.months, go.Figure)
    assert recalled.months is not drawn
    assert recalled.months.to_dict() == drawn.to_dict()
    assert recalled.labels.to_dict() == go.Figure().to_dict()
    assert plan.comparison_dumbbell is None
    assert plan.months.to_dict() == drawn.to_dict()


def test_bundle_figure_shapes() -> None:
    """네 묶음이 화면의 여덟 Figure 를 나눠 갖고, 계획 세부수량 묶음만 덤벨 칸을 더 갖는다."""
    assert LobFigures._fields == ("labels", "months")
    assert KeyProcessFigures._fields == ("labels", "months")
    assert BottleneckFigures._fields == ("labels", "months")
    assert PlanDetailFigures._fields == ("labels", "months", "comparison_dumbbell")
    assert [bundle.name for bundle in HOME_FIGURE_BUNDLES] == [LOB, PLAN, KEY_PROCESS, BOTTLENECK]
