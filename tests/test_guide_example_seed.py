# Purpose: 가이드 예시판 합성 시드가 예시판 이야기 꼴(확보율·판정·B/N·이야기 칸)을 지키는지 본다.

"""가이드 예시판 합성 시드의 회귀 검사.

수는 업무 계약이 아니라 **예시판 이야기 꼴**이다(`scripts/guide_example_seed.py` 머리말).
시안 README 가 적은 꼴 — 최신 공식 확보율 94~146% · 확보 73 / 경고 21 / 부족 2 · 달별 B/N
4종 · 이야기 칸 12월 Pre B/D 96% → 가용 +2 → 102% — 이 바뀌면 촬영 계획의 매개값
기본값(고칠 칸 · 활성 시나리오)과 원고 문장이 함께 어긋나므로 여기서 먼저 걸린다. 합성 DB 는
임시 폴더에만 만든다.
"""

from __future__ import annotations

import calendar
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import guide_example_seed as seed  # noqa: E402

from capa_simulation.persistence.repository import DuckDBScenarioRepository  # noqa: E402
from capa_simulation.services import builtin_seed  # noqa: E402
from capa_simulation.services import display_order_scopes as scopes  # noqa: E402
from capa_simulation.services.securement_threshold import DEFAULT_WARNING_THRESHOLD  # noqa: E402
from capa_simulation.services.simulation_cache import get_capacity_and_demand  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> seed.GuideExampleSeed:
    return seed.build_example_seed(tmp_path_factory.mktemp("guide_seed") / "seed.duckdb")


def test_the_latest_official_keeps_the_example_shape(built: seed.GuideExampleSeed) -> None:
    latest = built.latest
    assert latest.scenario_name == seed.ACTIVE_SCENARIO_NAME
    assert round(latest.rate_min, 1) == 94.0
    assert round(latest.rate_max, 1) == 145.5
    assert dict(latest.status_counts) == {"확보": 73, "경고": 21, "부족": 2}
    assert len(latest.bottlenecks) == 12
    assert len(latest.bottleneck_processes) == 4
    by_month = {item.month: item.process for item in latest.bottlenecks}
    assert by_month[seed.STORY_MONTH] == seed.STORY_PROCESS


def test_only_the_short_cells_fall_below_the_warning_line(built: seed.GuideExampleSeed) -> None:
    rates = built.latest_rates
    cells = {
        (str(process), int(month))
        for process, month, ratio in rates[["공정", "생산계획년월", "확보율"]].itertuples(
            index=False
        )
        if float(ratio) < DEFAULT_WARNING_THRESHOLD
    }
    assert cells == set(seed.SHORT_CELLS)


def test_the_previous_official_has_no_shortage(built: seed.GuideExampleSeed) -> None:
    previous = built.shapes[0]
    assert previous.scenario_name == seed.SCENARIOS[0].scenario_name
    assert previous.status_counts["부족"] == 0


def test_the_story_cell_leaves_shortage_after_two_more_units(
    built: seed.GuideExampleSeed,
) -> None:
    story = built.story
    assert (story.process, story.month) == ("Pre B/D", 202612)
    assert story.available == 37
    assert round(story.rate_percent) == 96
    assert round(story.rate_after_percent) == 102
    assert (story.status, story.status_after) == ("shortage", "warning")


def test_mi_standard_time_is_read_in_minutes(built: seed.GuideExampleSeed) -> None:
    """30일 달의 대당 Capa 가 공정마다 목표 그대로다 — MI 공정(ST)도 Main(UPEH)과 같다.

    ST 를 초로 적으면(3600 ÷ 환산) 분 단위로 읽는 앱에서 MI 공정만 대당 Capa 가 1/60 이 된다.
    """
    tables = built.examples[-1].dataset.reference_tables
    unit_capacity, _ = get_capacity_and_demand(tables)
    month = next(
        month
        for month in built.examples[-1].months
        if calendar.monthrange(month // 100, month % 100)[1] == 30
    )
    observed = (
        unit_capacity.loc[unit_capacity["생산계획년월"].eq(month)]
        .groupby("공정")["대당 Capa"]
        .agg(["min", "max"])
    )
    for process in seed.PROCESSES:
        low, high = observed.loc[process.name]
        assert low == pytest.approx(process.target_capacity)
        assert high == pytest.approx(process.target_capacity)
    mi = {process.name for process in seed.PROCESSES if process.area == "MI"}
    assert mi == {"Wafer Saw", "Singulation"}


def test_the_database_holds_two_officials_and_the_flow_order(
    built: seed.GuideExampleSeed,
) -> None:
    repository = DuckDBScenarioRepository(built.database)
    scenarios = [summary.scenario_name for summary in repository.list_scenarios()]
    assert sorted(scenarios) == sorted(item.scenario_name for item in seed.SCENARIOS)
    assert built.scenario_count == 2
    latest = repository.latest_official_release()
    assert latest is not None
    assert latest.release_no == built.latest_release_no == 2
    assert latest.scenario_name == seed.ACTIVE_SCENARIO_NAME
    assert latest.source_simulation_code == seed.SCENARIOS[-1].simulation_code

    rules = repository.load_global_display_order().rules
    equipment = rules.loc[
        rules["페이지 구분"].eq(scopes.PAGE_REFERENCE)
        & rules["탭 구분"].eq(scopes.TAB_EQUIPMENT_COUNT)
        & rules["분류컬럼"].eq("공정")
    ].sort_values("값표시순서")
    assert set(equipment["정렬방식"]) == {"사용자지정"}
    assert tuple(equipment["분류값"]) == seed.PROCESS_NAMES

    key_process = repository.load_global_key_process()
    assert key_process.presets == ((seed.KEY_PROCESS_PRESET, seed.KEY_PROCESSES),)


def test_the_source_type_reads_as_csv(built: seed.GuideExampleSeed) -> None:
    """머리 띠가 「내장 시드」 대신 「CSV」로 적히는 원천 유형이다."""
    assert seed.SOURCE_TYPE.startswith("CSV_")
    assert {example.dataset.batch.source_type for example in built.examples} == {seed.SOURCE_TYPE}


def test_an_existing_database_is_not_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "capa_simulation.duckdb"
    target.write_bytes(b"not a seed")
    with pytest.raises(FileExistsError):
        seed.build_example_seed(target)
    assert target.read_bytes() == b"not a seed"
    assert seed.main(["--out", str(target)]) == 2
    assert target.read_bytes() == b"not a seed"


def test_the_flow_order_ignores_a_local_display_order_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """로컬 시드 CSV 가 있는 자리에서 돌려도 시드는 추적 파일의 표시순서만 쓴다."""
    local = tmp_path / "RQ_DISPLAY_ORDER.csv"
    local.write_text("이 파일은 읽히면 안 된다\n", encoding="utf-8")
    monkeypatch.setattr(builtin_seed, "LOCAL_DISPLAY_ORDER_CSV_PATH", local)
    rules = seed.display_order()
    process_rules = rules.loc[rules["분류컬럼"].eq("공정")]
    assert not process_rules.empty
    assert set(process_rules["정렬방식"]) == {"사용자지정"}
    tracked = builtin_seed.load_tracked_display_order()

    def scopes_of(frame: pd.DataFrame) -> list[tuple[str, str, str]]:
        return [
            (str(page), str(tab), str(column))
            for page, tab, column in frame[["페이지 구분", "탭 구분", "분류컬럼"]].itertuples(
                index=False
            )
        ]

    assert scopes_of(rules[rules["분류컬럼"].ne("공정")]) == scopes_of(
        tracked[tracked["분류컬럼"].ne("공정")]
    )
