# Purpose: HOME Figure 캐시의 내용·테마·스키마 분리, 최근 사용 순서와 세션 공유를 검증한다.

import pickle

import plotly.graph_objects as go
import pytest

from capa_simulation.components import home_rendering
from capa_simulation.components.home_rendering import (
    HOME_FIGURE_CACHE_MAX_ENTRIES,
    HOME_FIGURE_SCHEMA_VERSION,
    HomeFigureCacheKey,
    HomeFigureSet,
    home_figure_cache,
    store_home_figures,
    take_home_figures,
)
from capa_simulation.services.simulation_cache import SharedBlobStore


@pytest.fixture
def cache_key(monkeypatch: pytest.MonkeyPatch) -> HomeFigureCacheKey:
    monkeypatch.setattr(home_rendering.st, "session_state", {})
    monkeypatch.setattr(home_rendering.theme, "current_mode", lambda: "light")
    return HomeFigureCacheKey(
        schema_version=HOME_FIGURE_SCHEMA_VERSION,
        process_label_version=2,
        reference_version=3,
        content_token="content-a",
        start_month=202601,
        end_month=202612,
        display_order_digest="display-order",
        included_processes=("DEMO_A", "DEMO_B"),
        secure_threshold_percent=109.5,
        warning_threshold_percent=99.5,
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
    )


@pytest.fixture
def figures() -> HomeFigureSet:
    return HomeFigureSet(
        lob_labels=go.Figure(),
        lob_months=go.Figure(),
        plan_detail_labels=go.Figure(),
        plan_detail_months=go.Figure(),
        key_process_labels=go.Figure(),
        key_process_months=go.Figure(),
        bottleneck_labels=go.Figure(),
        bottleneck_months=go.Figure(),
    )


def test_named_cache_key_preserves_the_existing_tuple_contract(
    cache_key: HomeFigureCacheKey,
) -> None:
    legacy_key = (
        HOME_FIGURE_SCHEMA_VERSION,
        2,
        3,
        "content-a",
        202601,
        202612,
        "display-order",
        ("DEMO_A", "DEMO_B"),
        109.5,
        99.5,
        False,
        True,
        "comparison-revision",
        True,
        4,
        True,
        5,
        6,
        0.9,
        1.2,
        7,
        ("DEMO_B", "DEMO_A"),
        8,
        "Wafer",
    )

    assert cache_key == legacy_key
    assert hash(cache_key) == hash(legacy_key)


def test_figure_cache_keeps_each_theme_separate(
    cache_key: HomeFigureCacheKey,
    figures: HomeFigureSet,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_home_figures(cache_key, figures)
    monkeypatch.setattr(home_rendering.theme, "current_mode", lambda: "dark")
    assert take_home_figures(cache_key) is None

    dark_figures = figures._replace(lob_months=go.Figure())
    store_home_figures(cache_key, dark_figures)
    assert take_home_figures(cache_key) is dark_figures
    monkeypatch.setattr(home_rendering.theme, "current_mode", lambda: "light")
    assert take_home_figures(cache_key) is figures


def test_figure_cache_does_not_reuse_another_content_or_profile_order(
    cache_key: HomeFigureCacheKey,
    figures: HomeFigureSet,
) -> None:
    store_home_figures(cache_key, figures)

    assert take_home_figures(cache_key._replace(content_token="content-b")) is None
    assert take_home_figures(cache_key._replace(key_processes=("DEMO_A", "DEMO_B"))) is None
    assert take_home_figures(cache_key._replace(comparison_revision_id="")) is None
    assert take_home_figures(cache_key) is figures


def test_old_plain_figure_tuples_are_invalidated_by_the_new_schema(
    cache_key: HomeFigureCacheKey,
    figures: HomeFigureSet,
) -> None:
    # 실행 중인 브라우저 세션은 코드가 바뀌어도 옛 dict·일반 tuple 을 가지고 있을 수 있다.
    old_key = tuple(cache_key._replace(schema_version=41))
    home_figure_cache()[("light", old_key)] = tuple(figures)

    assert HOME_FIGURE_SCHEMA_VERSION > 41
    assert take_home_figures(cache_key) is None
    store_home_figures(cache_key, figures)
    assert take_home_figures(cache_key) is figures


def test_figure_cache_evicts_the_least_recently_read_entry(
    cache_key: HomeFigureCacheKey,
    figures: HomeFigureSet,
) -> None:
    keys = [
        cache_key._replace(content_token=f"content-{index}")
        for index in range(HOME_FIGURE_CACHE_MAX_ENTRIES + 1)
    ]
    for key in keys[:-1]:
        store_home_figures(key, figures)
    assert take_home_figures(keys[0]) is figures

    store_home_figures(keys[-1], figures)

    assert len(home_figure_cache()) == HOME_FIGURE_CACHE_MAX_ENTRIES
    assert take_home_figures(keys[1]) is None
    assert take_home_figures(keys[0]) is figures
    assert take_home_figures(keys[-1]) is figures


@pytest.fixture
def shared_store(monkeypatch: pytest.MonkeyPatch) -> SharedBlobStore:
    store = SharedBlobStore(4)
    monkeypatch.setattr(home_rendering, "shared_home_figure_store", lambda: store)
    return store


def _new_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(home_rendering.st, "session_state", {})


def test_a_new_session_reuses_the_figures_drawn_for_the_same_revision(
    cache_key: HomeFigureCacheKey,
    figures: HomeFigureSet,
    shared_store: SharedBlobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """새로고침은 새 세션이다. 같은 리비전이면 그림을 다시 만들지 않는다."""
    pristine = cache_key._replace(content_token="pristine-3")
    store_home_figures(pristine, figures)

    _new_session(monkeypatch)
    recalled = take_home_figures(pristine)

    assert recalled is not None
    assert len(recalled) == len(figures)
    assert pristine in {key for _, key in home_figure_cache()}


def test_an_edited_session_keeps_its_figures_to_itself(
    cache_key: HomeFigureCacheKey,
    figures: HomeFigureSet,
    shared_store: SharedBlobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """편집 토큰의 그림은 남이 쓸 일이 없다. 공용 칸에 넣으면 남의 칸만 밀어낸다."""
    store_home_figures(cache_key, figures)

    _new_session(monkeypatch)

    assert len(shared_store) == 0
    assert take_home_figures(cache_key) is None


def test_a_shared_recall_is_a_copy_that_cannot_repaint_another_session(
    cache_key: HomeFigureCacheKey,
    figures: HomeFigureSet,
    shared_store: SharedBlobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pristine = cache_key._replace(content_token="pristine-3")
    store_home_figures(pristine, figures)
    _new_session(monkeypatch)
    first = take_home_figures(pristine)
    assert first is not None
    first.lob_labels.update_layout(title_text="이 세션만 고친 제목")

    _new_session(monkeypatch)
    second = take_home_figures(pristine)

    assert second is not None
    assert second.lob_labels.layout.title.text is None


def test_a_shared_recall_rebuilds_the_same_figure_from_plain_specs(
    cache_key: HomeFigureCacheKey,
    figures: HomeFigureSet,
    shared_store: SharedBlobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """공용 칸은 Figure 가 아니라 `to_dict()` 목록을 담고, 꺼낼 때 같은 그림을 다시 세운다.

    빈 Figure 만으로는 저장 형식이 Figure 통째 pickle 로 돌아가도 드러나지 않는다. 막대와
    축 제목이 있는 그림으로 왕복하고, Plotly 비공개 인자 `_validate` 가 사라지면 복원이
    `TypeError` 로 깨져 여기서 먼저 드러난다.
    """
    drawn = go.Figure(
        go.Bar(x=["DEMO_A", "DEMO_B"], y=[1.5, 2.0], marker={"color": "#336699"}),
        layout={"xaxis": {"title": {"text": "공정"}}, "height": 120},
    )
    pristine = cache_key._replace(content_token="pristine-3")
    store_home_figures(pristine, figures._replace(bottleneck_months=drawn))

    blob = shared_store.get(("light", pristine))
    assert blob is not None
    specs = pickle.loads(blob)
    assert isinstance(specs, list)
    assert len(specs) == len(HomeFigureSet._fields)
    assert all(type(spec) is dict for spec in specs)

    _new_session(monkeypatch)
    recalled = take_home_figures(pristine)

    assert recalled is not None
    assert all(isinstance(figure, go.Figure) for figure in recalled)
    assert recalled.bottleneck_months is not drawn
    assert recalled.bottleneck_months.to_dict() == drawn.to_dict()
    assert recalled.lob_labels.to_dict() == figures.lob_labels.to_dict()
