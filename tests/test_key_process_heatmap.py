# Purpose: HOME 주요공정 히트맵의 공용 프로필 왕복과 격자 계약을 검증한다.

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
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
    KEY_PROCESS_PRESET_LIMIT,
    normalize_key_process_presets,
    normalize_key_processes,
    resolve_preset_name,
)
from capa_simulation.services.securement_threshold import SecurementThresholds

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


def _figures(processes: list[str]) -> tuple[go.Figure, go.Figure]:
    return build_key_process_heatmap_figures(
        securement_rate=_securement_frame(),
        key_processes=processes,
        month_labels=list(MONTH_LABELS),
        thresholds=SecurementThresholds(1.095, 0.995),
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


def test_presets_round_trip_in_order_and_removing_all_still_bumps_the_version(
    tmp_path: Path,
) -> None:
    """이름 붙은 프리셋 여럿이 차례대로 돌아온다(첫 프리셋이 기본). 한 공정이 둘에 들 수 있다.

    모두 지운 저장도 정상이다 — 버전이 올라야 다른 세션의 캐시가 풀린다.
    """
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()

    assert repository.load_global_key_process().version == 0
    assert repository.load_global_key_process().presets == ()

    saved = repository.replace_global_key_process_presets(
        [("A 그룹", ["DEMO-B", "DEMO-A"]), ("B 그룹", ["DEMO-A", "DEMO-C"])], source="테스트"
    )
    assert saved.presets == (("A 그룹", ("DEMO-B", "DEMO-A")), ("B 그룹", ("DEMO-A", "DEMO-C")))
    assert saved.preset_names == ("A 그룹", "B 그룹")
    assert saved.processes_of("B 그룹") == ("DEMO-A", "DEMO-C")
    assert saved.processes_of("없는 프리셋") == ()
    assert saved.version == 1

    cleared = repository.replace_global_key_process_presets([], source="테스트")
    assert cleared.presets == ()
    assert cleared.version == 2


def test_preset_rules_refuse_duplicates_empty_presets_and_blank_names() -> None:
    with pytest.raises(ValueError, match="같은 이름"):
        normalize_key_process_presets([("A", ["P1"]), (" A ", ["P2"])])
    with pytest.raises(ValueError, match="하나 이상"):
        normalize_key_process_presets([("A", [])])
    with pytest.raises(ValueError, match="이름"):
        normalize_key_process_presets([("  ", ["P1"])])
    with pytest.raises(ValueError, match="최대"):
        normalize_key_process_presets(
            [(f"P{index}", ["X"]) for index in range(KEY_PROCESS_PRESET_LIMIT + 1)]
        )


def test_the_chosen_preset_falls_back_to_the_first_one() -> None:
    """고르지 않았거나 고른 프리셋이 지워졌으면 첫 프리셋(기본)이다."""
    assert resolve_preset_name(("A", "B"), "B") == "B"
    assert resolve_preset_name(("A", "B"), "지워진 것") == "A"
    assert resolve_preset_name(("A", "B"), None) == "A"
    assert resolve_preset_name((), "A") is None


def test_the_migration_moves_the_old_single_list_into_a_default_preset() -> None:
    """0028 은 0024 의 단일 목록을 「기본」 프리셋으로 옮긴다. 두 번 돌려도 같다."""
    import duckdb

    root = Path(__file__).resolve().parents[1] / "src/capa_simulation/persistence/migrations"
    connection = duckdb.connect()
    connection.execute("CREATE SCHEMA app_meta")
    connection.execute((root / "0024_global_key_process.sql").read_text(encoding="utf-8"))
    connection.execute(
        """
        INSERT INTO app_meta.global_key_process_item VALUES
            (1, 'DEMO-B', 0), (1, 'DEMO-A', 1)
        """
    )
    migration = (root / "0028_global_key_process_preset.sql").read_text(encoding="utf-8")
    connection.execute(migration)
    connection.execute(migration)

    presets = connection.execute(
        'SELECT "프리셋", "프리셋순서" FROM app_meta.global_key_process_preset'
    ).fetchall()
    items = connection.execute(
        'SELECT "공정" FROM app_meta.global_key_process_preset_item '
        'WHERE "프리셋" = \'기본\' ORDER BY "표시순서"'
    ).fetchall()
    assert presets == [("기본", 0)]
    assert [row[0] for row in items] == ["DEMO-B", "DEMO-A"]


def test_the_migration_makes_no_preset_from_an_empty_list() -> None:
    import duckdb

    root = Path(__file__).resolve().parents[1] / "src/capa_simulation/persistence/migrations"
    connection = duckdb.connect()
    connection.execute("CREATE SCHEMA app_meta")
    connection.execute((root / "0024_global_key_process.sql").read_text(encoding="utf-8"))
    connection.execute((root / "0028_global_key_process_preset.sql").read_text(encoding="utf-8"))

    assert connection.execute(
        "SELECT count(*) FROM app_meta.global_key_process_preset"
    ).fetchone() == (0,)


def test_migration_is_registered() -> None:
    """0024 가 카탈로그에 등재돼 있어야 한다. 기존 SQL 은 한 글자도 고치지 않는다."""
    root = Path(__file__).resolve().parents[1]
    catalog = (root / "docs/migration_catalog.md").read_text(encoding="utf-8")

    assert "0024_global_key_process.sql" in catalog
    assert "0028_global_key_process_preset.sql" in catalog
