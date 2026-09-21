# Purpose: HOME Figure 캐시의 내용·테마·스키마 분리와 최근 사용 순서·튜플 호환성을 검증한다.

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
