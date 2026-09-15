# Purpose: HOME 주요공정 히트맵의 공용 프로필 왕복과 격자 계약을 검증한다.

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.components.home_dimensions import (
    KEY_PROCESS_HEADER_HEIGHT_PX,
    KEY_PROCESS_ROW_HEIGHT_PX,
)
from capa_simulation.components.home_figures import (
    KEY_PROCESS_EMPTY_NOTICE,
    build_key_process_heatmap_figures,
)
from capa_simulation.design import tokens
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.key_process import (
    KEY_PROCESS_LIMIT,
    normalize_key_processes,
)

MONTH_LABELS = ["26.01", "26.02", "26년", "27.01"]
YEAR_TOTAL_LABELS = ["26년"]


def _securement_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [202601, 202602, 202701, 202601, 202602],
            "공정": ["DEMO-A", "DEMO-A", "DEMO-A", "DEMO-B", "DEMO-B"],
            "확보율": [1.30, 0.80, 1.05, 1.02, 1.20],
            "가용대수": [10.0, 10.0, 12.0, 8.0, 8.0],
            "소요대수": [7.7, 12.5, 11.4, 7.8, 6.7],
        }
    )


def _figures(processes: list[str]) -> tuple[object, object]:
    return build_key_process_heatmap_figures(
        securement_rate=_securement_frame(),
        key_processes=processes,
        month_labels=list(MONTH_LABELS),
        secure_threshold=1.095,
        warning_threshold=0.995,
        year_total_labels=YEAR_TOTAL_LABELS,
    )


def test_normalize_keeps_the_chosen_order_and_drops_duplicates() -> None:
    """고른 차례가 곧 행 순서다. 정렬하면 매달 행이 뛰어다녀 가로로 읽을 수 없다."""
    assert normalize_key_processes([" B ", "A", "B", "", "C"]) == ("B", "A", "C")


def test_normalize_rejects_more_than_the_limit() -> None:
    with pytest.raises(ValueError, match="최대"):
        normalize_key_processes([f"P{index}" for index in range(KEY_PROCESS_LIMIT + 1)])


def test_row_order_follows_the_selection_not_the_rate() -> None:
    """확보율이 더 낮은 `DEMO-B` 를 나중에 골랐으면 그대로 둘째 줄이다."""
    label_figure, _ = _figures(["DEMO-A", "DEMO-B"])
    names = [
        annotation.text
        for annotation in label_figure.layout.annotations
        if annotation.text in {"DEMO-A", "DEMO-B"}
    ]

    assert names == ["DEMO-A", "DEMO-B"]


def test_the_two_figures_share_one_height() -> None:
    """1px 이라도 다르면 그 아래 구획이 통째로 어긋난다."""
    label_figure, month_figure = _figures(["DEMO-A", "DEMO-B"])
    expected = KEY_PROCESS_HEADER_HEIGHT_PX + 2 * KEY_PROCESS_ROW_HEIGHT_PX

    assert label_figure.layout.height == month_figure.layout.height == expected


def test_the_year_total_column_gets_a_surface_but_no_cell() -> None:
    """확보율은 합산도 평균도 못 한다. 합계 열은 면색만 깔고 칸을 그리지 않는다."""
    _, month_figure = _figures(["DEMO-A"])
    year_total_index = MONTH_LABELS.index("26년")
    cell_bar = month_figure.data[1]
    month_count = len(MONTH_LABELS)

    assert all(int(base) != year_total_index for base in cell_bar.base)
    assert any(
        shape.fillcolor == tokens.SURFACE_YEAR_TOTAL
        and abs(shape.x0 - year_total_index / month_count) < 1e-9
        for shape in month_figure.layout.shapes
    )


def test_cell_colors_come_from_the_shared_judgment() -> None:
    """확보·경고·부족 판정은 `_capacity_color` 하나에서 나온다. 색 체계가 둘이면 같은
    확보율이 화면마다 다른 색으로 보인다."""
    _, month_figure = _figures(["DEMO-A"])
    colors = dict(zip(month_figure.data[2].text, month_figure.data[1].marker.color, strict=True))

    assert colors["130%"] == tokens.STATUS_SECURE
    assert colors["105%"] == tokens.STATUS_WARNING
    assert colors["80%"] == tokens.STATUS_SHORTAGE


def test_every_cell_carries_its_rate_as_text() -> None:
    """색만으로 뜻을 나르지 않는다. 색각이상·흑백에서도 숫자가 읽혀야 한다."""
    _, month_figure = _figures(["DEMO-A", "DEMO-B"])

    assert set(month_figure.data[2].text) == {"130%", "80%", "105%", "102%", "120%"}


def test_an_empty_selection_still_draws_one_row_with_a_notice() -> None:
    """Figure 를 빼면 두 칸의 자식 수가 갈라져 정렬 규칙이 두 벌이 된다."""
    label_figure, month_figure = _figures([])
    expected = KEY_PROCESS_HEADER_HEIGHT_PX + KEY_PROCESS_ROW_HEIGHT_PX

    assert label_figure.layout.height == month_figure.layout.height == expected
    assert any(
        annotation.text == KEY_PROCESS_EMPTY_NOTICE
        for annotation in label_figure.layout.annotations
    )
    assert len(month_figure.data[1].base) == 0


def test_a_process_missing_from_the_scenario_is_skipped_without_failing() -> None:
    """공용 설정이라 다른 시나리오에는 그 공정이 있다. 여기서는 건너뛰기만 한다."""
    label_figure, month_figure = _figures(["DEMO-A", "DEMO-MISSING"])

    assert label_figure.layout.height == (
        KEY_PROCESS_HEADER_HEIGHT_PX + 2 * KEY_PROCESS_ROW_HEIGHT_PX
    )
    assert set(month_figure.data[2].text) == {"130%", "80%", "105%"}


def test_the_profile_round_trips_and_an_empty_save_still_bumps_the_version(
    tmp_path: Path,
) -> None:
    """0건(전체 해제)도 정상 저장이다. 버전이 올라야 다른 세션의 캐시가 풀린다."""
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    assert repository.load_global_key_process().version == 0

    saved = repository.replace_global_key_process(["DEMO-B", "DEMO-A"], source="테스트")
    assert saved.processes == ("DEMO-B", "DEMO-A")
    assert saved.version == 1

    cleared = repository.replace_global_key_process([], source="테스트")
    assert cleared.processes == ()
    assert cleared.version == 2


def test_migration_is_registered() -> None:
    """0024 가 카탈로그에 등재돼 있어야 한다. 기존 SQL 은 한 글자도 고치지 않는다."""
    root = Path(__file__).resolve().parents[1]
    catalog = (root / "docs/migration_catalog.md").read_text(encoding="utf-8")

    assert "0024_global_key_process.sql" in catalog
