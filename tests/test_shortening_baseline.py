# Purpose: 필요단축일정 기준선의 얼리기·이름 규칙과 설비 DB 0021 저장·목록·읽기·지우기를 검사한다.

"""필요단축일정 기준선(`services/shortening_baseline.py`, 설비 DB 0021).

기준선은 그때 계획을 얼린 고칠 수 없는 공용 기록이다. 계획은 `test_required_shortening` 의 손으로
셀 수 있는 예(Cut-off 10, 2026-05 W/D 구간 31일)를 그대로 쓴다.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest
from test_required_shortening import MAY, _plan, _unit

from capa_simulation.persistence._sql_helpers import connect
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    load_shortening_baseline,
    load_shortening_baselines,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    LEVEL_COLUMN,
    ShorteningPlan,
)
from capa_simulation.services.shortening_baseline import (
    BASELINE_UNIT_COLUMNS,
    BaselineProvenance,
    ShorteningBaselineDraft,
    baseline_label,
    default_baseline_name,
    freeze_plan,
    normalize_baseline_name,
    normalize_saved_by,
)

TABLES = ("shortening_baseline", "shortening_baseline_process", "shortening_baseline_unit")


def _bundle_plan() -> ShorteningPlan:
    """A1 하나와 모듈 묶음 G9(M1·M2, 환산비 0.5+0.7) — 5월 소요 14 는 둘을 당겨도 모자라 추가N 이
    선다."""
    return _plan(
        [
            _unit("A1", date(2026, 5, 1)),
            _unit("M1", date(2026, 6, 10), ratio=0.5, parent="G9"),
            _unit("M2", date(2026, 7, 5), ratio=0.7, parent="G9"),
        ],
        {MAY: 14.0},
    )


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def _counts(path: Path) -> dict[str, int]:
    with connect(path) as connection:
        counts: dict[str, int] = {}
        for table in TABLES:
            row = connection.execute(f"SELECT COUNT(*) FROM equipment_ops.{table}").fetchone()
            assert row is not None
            counts[table] = int(row[0])
        return counts


def test_the_names_default_to_the_day_and_reject_blanks() -> None:
    assert default_baseline_name(date(2026, 10, 8)) == "2026-10-08 기준선"
    assert normalize_baseline_name("  9월 정기  ") == "9월 정기"
    for blank in ("", "   ", None):
        with pytest.raises(ValueError, match="이름을 적어"):
            normalize_baseline_name(blank)
    with pytest.raises(ValueError, match="60자"):
        normalize_baseline_name("가" * 61)
    assert normalize_saved_by("  ") is None
    assert normalize_saved_by(" 홍길동 ") == "홍길동"


def test_freezing_a_plan_keeps_every_level_with_the_bundle_and_virtual_units() -> None:
    plan = _bundle_plan()

    draft = freeze_plan(plan, name=" 9월 정기 ", provenance=BaselineProvenance(saved_by="나"))

    assert draft.name == "9월 정기"
    assert (draft.plan_today, draft.start_month, draft.end_month) == (plan.today, MAY, MAY)
    assert draft.processes == plan.processes
    assert draft.cutoff_days == {"Die Attach": 10}
    units = draft.units
    assert list(units.columns) == list(BASELINE_UNIT_COLUMNS)
    # 다섯 목표의 결과가 모두 실린다 — 목표마다 계획의 호기 표와 줄 수가 같다.
    for level_plan in plan.levels:
        block = units.loc[units[LEVEL_COLUMN].eq(round(level_plan.level * 100))]
        assert list(block["호기"]) == list(level_plan.units["호기"])
    level = units.loc[units[LEVEL_COLUMN].eq(100)].set_index("호기")
    # 모듈 묶음은 설비키(Main 설비) 한 줄이고 설비명은 모듈 행을 잇는다. 환산비는 합이다.
    assert level.at["G9", "구분"] == KIND_SHORTENED
    assert level.at["G9", "설비명"] == "M1, M2"
    assert level.at["G9", "모듈 수"] == 2
    assert level.at["G9", "환산비"] == pytest.approx(1.2)
    assert level.at["G9", "기존 Qual"] == date(2026, 7, 5)
    assert isinstance(level.at["G9", "목표 Qual"], date)
    # 가상 호기는 마스터에 없어 설비명·환산비·기존 Qual·단축일수가 빈칸이다.
    virtual = level.loc[level["구분"].eq(KIND_NEW)]
    assert list(virtual.index) == ["추가1", "추가2"]
    assert virtual["설비명"].isna().all() and virtual["환산비"].isna().all()
    assert virtual["기존 Qual"].isna().all() and virtual["단축일수"].isna().all()


def test_a_plan_without_months_cannot_be_frozen() -> None:
    plan = _bundle_plan()
    empty = ShorteningPlan(
        months=(), today=plan.today, processes=(), cutoff_days={}, levels=plan.levels
    )
    with pytest.raises(ValueError, match="조회 달이 없어"):
        freeze_plan(empty, name="x")


def test_migration_0021_creates_three_empty_tables(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    _repository(path)

    assert _counts(path) == dict.fromkeys(TABLES, 0)


def test_a_saved_baseline_round_trips_and_is_listed_newest_first(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    plan = _bundle_plan()
    provenance = BaselineProvenance(
        saved_by="홍길동",
        equipment_revision_id="rev-1",
        equipment_revision_no=12,
        reference_version=int("f" * 15, 16),
        scenario_id="s-1",
        scenario_name="9월 계획",
        scenario_revision_id="r-3",
        scenario_revision_no=3,
        scenario_content_token="pristine-7",
    )
    first = repository.save_shortening_baseline(
        freeze_plan(plan, name="9월 정기", provenance=provenance),
        saved_at=datetime(2026, 9, 30, 9, 15, 30, 999),
    )
    second = repository.save_shortening_baseline(
        freeze_plan(plan, name="10월 정기"), saved_at=datetime(2026, 10, 8, 11, 0)
    )

    assert first.saved_at == datetime(2026, 9, 30, 9, 15, 30)
    assert baseline_label(first) == "9월 정기 · 2026-09-30"
    listed = repository.list_shortening_baselines()
    assert [summary.name for summary in listed] == ["10월 정기", "9월 정기"]
    assert listed[1] == first
    assert listed[0] == second and second.saved_by is None

    loaded = repository.load_shortening_baseline(first.baseline_id)
    assert loaded.summary == first
    assert loaded.processes == plan.processes
    assert loaded.cutoff_days == {"Die Attach": 10}
    expected = freeze_plan(plan, name="x").units
    pd.testing.assert_frame_equal(loaded.units, expected)
    # 고른 목표의 표는 목표 칸 없이 그 목표의 계획 호기 표와 같은 호기·날짜다.
    at_100 = loaded.units_at(1.0)
    assert LEVEL_COLUMN not in at_100.columns
    assert list(at_100["호기"]) == list(plan.at(1.0).units["호기"])
    assert list(at_100["목표 Qual"]) == list(plan.at(1.0).units["목표 Qual"])


def test_a_duplicate_or_blank_name_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    plan = _bundle_plan()
    repository.save_shortening_baseline(freeze_plan(plan, name="9월 정기"))
    before = _counts(path)

    with pytest.raises(ValueError, match="같은 이름의 기준선이 이미 있습니다: 9월 정기"):
        repository.save_shortening_baseline(freeze_plan(plan, name=" 9월 정기 "))
    with pytest.raises(ValueError, match="이름을 적어"):
        freeze_plan(plan, name="  ")

    assert _counts(path) == before


def test_a_baseline_cannot_be_edited_only_deleted(tmp_path: Path) -> None:
    """고칠 길이 없다 — Repository 에 갈아 쓰는 메서드가 없고, 지우기는 세 표를 함께 지운다."""
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    plan = _bundle_plan()
    kept = repository.save_shortening_baseline(freeze_plan(plan, name="남길 것"))
    gone = repository.save_shortening_baseline(freeze_plan(plan, name="지울 것"))
    writers = [name for name in dir(repository) if "shortening_baseline" in name]
    assert sorted(writers) == [
        "delete_shortening_baseline",
        "list_shortening_baselines",
        "load_shortening_baseline",
        "save_shortening_baseline",
    ]

    assert repository.delete_shortening_baseline(gone.baseline_id) is True
    assert repository.delete_shortening_baseline(gone.baseline_id) is False

    assert [summary.name for summary in repository.list_shortening_baselines()] == ["남길 것"]
    with pytest.raises(ValueError, match="기준선을 찾지 못했습니다"):
        repository.load_shortening_baseline(gone.baseline_id)
    with connect(path) as connection:
        for table in TABLES:
            row = connection.execute(
                f"SELECT COUNT(*) FROM equipment_ops.{table} WHERE baseline_id = ?",
                [gone.baseline_id],
            ).fetchone()
            assert row == (0,), table
    assert repository.load_shortening_baseline(kept.baseline_id).summary == kept


def test_a_real_unit_named_like_a_virtual_unit_saves_beside_it(tmp_path: Path) -> None:
    """마스터에 「추가1」 이라는 실제 호기가 있어도 가상 호기 「추가1」 과 한 기준선에 함께
    들어간다 — 진척 비교가 둘을 따로 짝짓듯 저장 키도 구분(`단축`/`신규`)을 싣는다."""
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    plan = _plan(
        [
            _unit("추가1", date(2026, 5, 1)),
            _unit("M1", date(2026, 6, 10), ratio=0.5, parent="G9"),
            _unit("M2", date(2026, 7, 5), ratio=0.7, parent="G9"),
        ],
        {MAY: 14.0},
    )
    units = plan.at(1.0).units
    assert set(units.loc[units["호기"].eq("추가1"), "구분"]) == {KIND_SHORTENED, KIND_NEW}

    summary = repository.save_shortening_baseline(freeze_plan(plan, name="같은 이름"))

    loaded = repository.load_shortening_baseline(summary.baseline_id).units_at(1.0)
    same = loaded.loc[loaded["호기"].eq("추가1")]
    assert sorted(same["구분"]) == sorted([KIND_SHORTENED, KIND_NEW])


def test_an_empty_plan_level_set_still_saves_its_processes(tmp_path: Path) -> None:
    """단축할 호기가 하나도 없던 계획도 기준선이 된다 — 그때 맞댄 공정은 남는다."""
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    plan = _plan([_unit("A1", date(2026, 5, 1))], {MAY: 1.0})
    assert all(level.units.empty for level in plan.levels)

    summary = repository.save_shortening_baseline(
        ShorteningBaselineDraft(
            name="충족",
            plan_today=plan.today,
            start_month=MAY,
            end_month=MAY,
            processes=plan.processes,
            cutoff_days={"Die Attach": 10},
            units=freeze_plan(plan, name="x").units,
        )
    )

    loaded = repository.load_shortening_baseline(summary.baseline_id)
    assert loaded.processes == ("Die Attach",)
    assert loaded.units.empty and list(loaded.units.columns) == list(BASELINE_UNIT_COLUMNS)


def test_the_cache_lists_and_loads_and_is_cleared_by_the_writer(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    clear_equipment_repository()
    repository = _repository(path)
    plan = _bundle_plan()
    assert load_shortening_baselines(str(path)) == ()
    saved = repository.save_shortening_baseline(freeze_plan(plan, name="캐시"))
    # 캐시는 저장 쪽(화면 콜백)이 비운다 — 여기서는 비우지 않아 옛 목록이 남는다.
    assert load_shortening_baselines(str(path)) == ()

    clear_equipment_repository()
    assert [summary.name for summary in load_shortening_baselines(str(path))] == ["캐시"]
    loaded = load_shortening_baseline(str(path), saved.baseline_id)
    assert loaded.summary == saved
    pd.testing.assert_frame_equal(loaded.units, freeze_plan(plan, name="x").units)
    with pytest.raises(ValueError, match="찾지 못했습니다"):
        load_shortening_baseline(str(path), "missing")
    clear_equipment_repository()
