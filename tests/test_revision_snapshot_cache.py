# Purpose: 리비전 표 한 장 읽기·스냅샷 캐시가 전체 스냅샷과 같은 값을 내고 무효화되는지 본다.

"""리비전 표 한 장 읽기(`load_revision_table`·`load_scenario_plan`)의 동등성과 무효화.

합성 시드(`ensure_initial_scenario`) 위에 계획만 바꾼 리비전과 시나리오를 더해 쓴다. 비교 GAP 은
`RQ_PKG_PLAN` 한 장만 읽으므로, 그 한 장이 전체 스냅샷의 같은 표와 컬럼·dtype·값까지 같아야 하고,
지운 리비전에서는 빈 계획을 조용히 돌려주지 않고 전체 스냅샷과 같은 `KeyError` 를 내야 한다.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from capa_simulation.persistence import cache as scenario_cache
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import (
    REFERENCE_TABLES,
    DuckDBScenarioRepository,
)


@dataclass(frozen=True)
class _Seeded:
    database_path: Path
    official_revision_id: str
    halved_revision_id: str


def _repository(database_path: Path) -> DuckDBScenarioRepository:
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order())
    return repository


def _scaled_plan(tables: dict[str, pd.DataFrame], factor: float) -> dict[str, pd.DataFrame]:
    scaled = dict(tables)
    plan = scaled["RQ_PKG_PLAN"].copy()
    plan["생산수량"] = pd.to_numeric(plan["생산수량"], errors="coerce") * factor
    scaled["RQ_PKG_PLAN"] = plan
    return scaled


def _create_clone(
    repository: DuckDBScenarioRepository, revision_id: str, name: str, factor: float
) -> tuple[str, str]:
    base = repository.load_revision(revision_id)
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name=name,
            source_simulation_code=f"CLONE-{name}",
            source_simulation_name=name,
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        _scaled_plan(dict(base.tables), factor),
        base.preset,
    )
    return created.scenario.scenario_id, created.revision.revision_id


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> _Seeded:
    from capa_simulation.application_bootstrap import ensure_initial_scenario
    from capa_simulation.persistence.repository import REVISION_TABLES

    database_path = tmp_path_factory.mktemp("revision-snapshot") / "scenario.duckdb"
    repository = _repository(database_path)
    release = ensure_initial_scenario(repository).release
    assert release is not None
    base = repository.load_revision(release.revision_id)
    halved = repository.save_revision(
        release.scenario_id,
        _scaled_plan(
            {name: base.tables[name] for name in REVISION_TABLES if name in base.tables}, 0.5
        ),
        base.preset,
        revision_name="계획 절반",
    )
    # 공용 표시순서를 리비전에 저장된 원본과 다르게 둔다 — 같으면 공용 프로필을 얹는 경로와 얹지
    # 않는 경로가 같은 프레임을 내 어느 쪽을 읽었는지 시험이 가르지 못한다.
    repository.replace_global_display_order(_flipped_first_direction(repository), source="테스트")
    return _Seeded(database_path, release.revision_id, halved.revision.revision_id)


def _flipped_first_direction(repository: DuckDBScenarioRepository) -> pd.DataFrame:
    rules = repository.load_global_display_order().rules
    directions = rules["정렬방식"].astype("string").tolist()
    directions[0] = "내림차순" if directions[0] != "내림차순" else "오름차순"
    return rules.assign(정렬방식=directions)


@pytest.fixture(autouse=True)
def _empty_caches() -> Iterator[None]:
    scenario_cache.clear_scenario_repository()
    yield
    scenario_cache.clear_scenario_repository()


def _assert_same_frame(actual: pd.DataFrame, expected: pd.DataFrame) -> None:
    assert list(actual.columns) == list(expected.columns)
    assert actual.dtypes.astype(str).tolist() == expected.dtypes.astype(str).tolist()
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)


# --------------------------------------------------------------- 표 한 장 = 전체 스냅샷의 그 표


@pytest.mark.parametrize("logical_name", list(REFERENCE_TABLES))
@pytest.mark.parametrize("apply_global_display_order", [True, False])
def test_one_revision_table_is_the_same_frame_as_in_the_whole_snapshot(
    seeded: _Seeded, logical_name: str, apply_global_display_order: bool
) -> None:
    """리비전 표(`rev_data`)·데이터셋 표(`ref_data`)·공용 표시순서 모두 전체 읽기와 같다."""
    repository = DuckDBScenarioRepository(seeded.database_path)
    for revision_id in (seeded.official_revision_id, seeded.halved_revision_id):
        whole = repository.load_revision(
            revision_id, apply_global_display_order=apply_global_display_order
        )
        one = repository.load_revision_table(
            revision_id, logical_name, apply_global_display_order=apply_global_display_order
        )
        _assert_same_frame(one, whole.tables[logical_name])


def test_the_display_order_table_follows_the_global_profile_flag(seeded: _Seeded) -> None:
    """표시순서 한 장은 플래그대로 공용 프로필 또는 리비전에 저장된 원본이다 — 둘은 다르다."""
    repository = DuckDBScenarioRepository(seeded.database_path)
    revision_id = seeded.official_revision_id
    global_order = repository.load_revision_table(revision_id, "RQ_DISPLAY_ORDER")
    stored_order = repository.load_revision_table(
        revision_id, "RQ_DISPLAY_ORDER", apply_global_display_order=False
    )
    assert not global_order["정렬방식"].equals(stored_order["정렬방식"])
    _assert_same_frame(global_order, repository.load_global_display_order().rules)


def test_an_unknown_table_name_is_not_mistaken_for_a_missing_revision(seeded: _Seeded) -> None:
    repository = DuckDBScenarioRepository(seeded.database_path)
    with pytest.raises(ValueError, match="RQ_NOT_A_TABLE"):
        repository.load_revision_table(seeded.official_revision_id, "RQ_NOT_A_TABLE")


def test_the_cached_comparison_plan_is_the_snapshot_plan_of_that_revision(
    seeded: _Seeded,
) -> None:
    """캐시 키의 리비전 id 하나만 달라도 그 리비전의 계획이 나온다(두 계획은 수량이 다르다)."""
    repository = DuckDBScenarioRepository(seeded.database_path)
    database_path = str(seeded.database_path)
    plans = {}
    for revision_id in (seeded.official_revision_id, seeded.halved_revision_id):
        plans[revision_id] = scenario_cache.load_scenario_plan(database_path, revision_id)
        _assert_same_frame(
            plans[revision_id], repository.load_revision(revision_id).tables["RQ_PKG_PLAN"]
        )
        # 적중해도 같은 값이다.
        _assert_same_frame(
            scenario_cache.load_scenario_plan(database_path, revision_id), plans[revision_id]
        )
    official = pd.to_numeric(plans[seeded.official_revision_id]["생산수량"])
    halved = pd.to_numeric(plans[seeded.halved_revision_id]["생산수량"])
    assert not official.equals(halved)
    pd.testing.assert_series_equal(halved, official * 0.5, check_names=False)


def test_the_comparison_plan_does_not_unpack_the_whole_snapshot(
    seeded: _Seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    """비교 계획은 표 한 장만 읽는다 — 16표 스냅샷을 DB 에서 읽거나 캐시에 올리지 않는다."""

    def whole_snapshot(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("비교 계획이 리비전 16표를 읽었다")

    monkeypatch.setattr(DuckDBScenarioRepository, "load_revision", whole_snapshot)
    plan = scenario_cache.load_scenario_plan(str(seeded.database_path), seeded.halved_revision_id)
    assert not plan.empty


# --------------------------------------------------------------- 지운 리비전


def test_a_deleted_revision_raises_instead_of_reading_an_empty_plan(seeded: _Seeded) -> None:
    """확인과 읽기 사이에 다른 세션이 지운 리비전은 빈 계획(전액 감소 GAP)이 아니라 KeyError 다.

    리비전 표를 `revision_id` 로 바로 읽으면 행 0개 프레임이 예외 없이 돌아온다. 그것이 캐시에
    남으면 GAP 이 전부 감소로 그려진다. 지운 뒤 비우기(`clear_scenario_snapshot_cache`)를 거치면
    캐시된 계획도 남지 않는다.
    """
    repository = DuckDBScenarioRepository(seeded.database_path)
    database_path = str(seeded.database_path)
    scenario_id, revision_id = _create_clone(
        repository, seeded.official_revision_id, "지울 비교", 0.25
    )
    assert not scenario_cache.load_scenario_plan(database_path, revision_id).empty

    repository.delete_scenario(scenario_id)
    scenario_cache.clear_scenario_snapshot_cache()

    with pytest.raises(KeyError, match="리비전을 찾을 수 없습니다"):
        repository.load_revision(revision_id)
    with pytest.raises(KeyError, match="리비전을 찾을 수 없습니다"):
        repository.load_revision_table(revision_id, "RQ_PKG_PLAN")
    # 실패는 캐시에 남지 않는다 — 다시 불러도 빈 프레임이 아니라 같은 KeyError 다.
    for _ in range(2):
        with pytest.raises(KeyError, match="리비전을 찾을 수 없습니다"):
            scenario_cache.load_scenario_plan(database_path, revision_id)
    with pytest.raises(KeyError, match="리비전을 찾을 수 없습니다"):
        repository.load_revision_table("없는-리비전", "RQ_DISPLAY_ORDER")


@pytest.mark.parametrize("whole_snapshot", [False, True])
def test_a_revision_deleted_between_the_check_and_the_read_is_read_as_checked(
    seeded: _Seeded, monkeypatch: pytest.MonkeyPatch, whole_snapshot: bool
) -> None:
    """확인 뒤 표를 읽기 전에 다른 세션이 지워도 확인한 시점의 표가 나온다 — 행 0개 계획이 아니다.

    확인과 읽기가 따로 된 두 문이면 그 틈에 커밋된 삭제가 보여 지운 리비전의 표가 예외 없이 행
    0개로 돌아온다. 그것이 비교 계획 캐시에 들면 그 회차 GAP 이 전부 감소로 그려진다.
    """
    import capa_simulation.persistence.repository as repository_module

    repository = DuckDBScenarioRepository(seeded.database_path)
    scenario_id, revision_id = _create_clone(
        repository, seeded.official_revision_id, "읽는 중 지울 비교", 0.25
    )
    expected = repository.load_revision(revision_id).tables
    original = repository_module._load_reference_frame
    deleted: list[str] = []

    def delete_then_read(
        connection: duckdb.DuckDBPyConnection, logical_name: str, **owners: str
    ) -> pd.DataFrame:
        if not deleted:
            DuckDBScenarioRepository(seeded.database_path).delete_scenario(scenario_id)
            deleted.append(logical_name)
        return original(connection, logical_name, **owners)

    monkeypatch.setattr(repository_module, "_load_reference_frame", delete_then_read)
    if whole_snapshot:
        loaded = repository.load_revision(revision_id).tables
    else:
        loaded = {"RQ_PKG_PLAN": repository.load_revision_table(revision_id, "RQ_PKG_PLAN")}
    monkeypatch.undo()

    assert len(deleted) == 1
    assert not loaded["RQ_PKG_PLAN"].empty
    for name, frame in loaded.items():
        _assert_same_frame(frame, expected[name])
    # 삭제는 커밋됐다 — 다음 읽기는 지운 리비전으로 본다.
    with pytest.raises(KeyError, match="리비전을 찾을 수 없습니다"):
        repository.load_revision_table(revision_id, "RQ_PKG_PLAN")


# --------------------------------------------------------------- 공유 스냅샷과 호출마다 깊은 사본


def _object_column(frame: pd.DataFrame) -> str:
    return next(
        str(name) for name, dtype in frame.dtypes.items() if pd.api.types.is_object_dtype(dtype)
    )


def _numeric_column(frame: pd.DataFrame) -> str:
    return next(
        str(name) for name, dtype in frame.dtypes.items() if pd.api.types.is_float_dtype(dtype)
    )


@pytest.mark.parametrize("apply_global_display_order", [True, False])
def test_the_cached_snapshot_is_the_repository_snapshot(
    seeded: _Seeded, apply_global_display_order: bool
) -> None:
    """캐시를 거친 스냅샷(처음·적중 둘 다)이 저장소에서 바로 읽은 것과 표·메타데이터까지 같다."""
    repository = DuckDBScenarioRepository(seeded.database_path)
    for revision_id in (seeded.official_revision_id, seeded.halved_revision_id):
        expected = repository.load_revision(
            revision_id, apply_global_display_order=apply_global_display_order
        )
        for _ in range(2):
            loaded = scenario_cache.load_scenario_snapshot(
                str(seeded.database_path),
                revision_id,
                apply_global_display_order=apply_global_display_order,
            )
            assert loaded.scenario == expected.scenario
            assert loaded.revision == expected.revision
            assert loaded.preset == expected.preset
            assert list(loaded.tables) == list(expected.tables)
            for name, frame in expected.tables.items():
                _assert_same_frame(loaded.tables[name], frame)


def test_every_snapshot_call_hands_out_tables_of_its_own(seeded: _Seeded) -> None:
    """두 번 부르면 서로 다른 프레임이고, 한쪽을 고쳐도 다른 쪽·캐시·다음 호출에 보이지 않는다.

    공유 프레임을 그대로 넘기면 한 세션의 제자리 수정이 모든 세션의 숫자를 바꾼다.
    """
    database_path = str(seeded.database_path)
    revision_id = seeded.official_revision_id
    pristine = DuckDBScenarioRepository(seeded.database_path).load_revision(revision_id)
    first = scenario_cache.load_scenario_snapshot(database_path, revision_id)
    second = scenario_cache.load_scenario_snapshot(database_path, revision_id)
    shared = scenario_cache._load_scenario_snapshot_resource(database_path, revision_id)

    for name, frame in first.tables.items():
        assert frame is not second.tables[name]
        assert frame is not shared["tables"][name]
        for column in frame.columns:
            assert not np.shares_memory(
                frame[column].to_numpy(), shared["tables"][name][column].to_numpy()
            ), (name, column)

    upeh = first.tables["RQ_UPEH"]
    numeric = _numeric_column(upeh)
    text = _object_column(upeh)
    upeh.iloc[0, list(upeh.columns).index(numeric)] = -12345.0  # 같은 dtype 제자리 쓰기
    upeh[text] = "바뀐 값"  # 열 대입
    first.tables["RQ_REQB"].drop(first.tables["RQ_REQB"].index[:10], inplace=True)
    first.tables["RQ_PKG_PLAN"]["생산수량"] *= 2

    third = scenario_cache.load_scenario_snapshot(database_path, revision_id)
    for snapshot in (second, third):
        for name, frame in pristine.tables.items():
            _assert_same_frame(snapshot.tables[name], frame)
    for name, frame in pristine.tables.items():
        _assert_same_frame(shared["tables"][name], frame)


def test_the_copies_share_the_immutable_strings_of_the_shared_snapshot(seeded: _Seeded) -> None:
    """세션 사본의 객체 칸은 공유 프레임과 같은 문자열 객체를 가리킨다(세션마다 새로 만들지 않는다).

    세션마다 스냅샷을 언피클하면 같은 문자열을 세션 수만큼 따로 쥔다(합성 표본의 샘플 관측으로
    세션 하나에 RSS 140MB 넘게). 깊은 복사는 포인터 배열만 새로 만든다.
    """
    database_path = str(seeded.database_path)
    first = scenario_cache.load_scenario_snapshot(database_path, seeded.official_revision_id)
    second = scenario_cache.load_scenario_snapshot(database_path, seeded.official_revision_id)
    reqb_first = first.tables["RQ_REQB"]
    reqb_second = second.tables["RQ_REQB"]
    column = _object_column(reqb_first)
    values_first = reqb_first[column].to_numpy()
    values_second = reqb_second[column].to_numpy()
    assert not np.shares_memory(values_first, values_second)
    assert all(a is b for a, b in zip(values_first[:200], values_second[:200], strict=True))


def test_the_shared_snapshot_rejects_in_place_writes(seeded: _Seeded) -> None:
    """공유 프레임의 배열은 읽기 전용이다 — 사본 대신 그것을 고치면 조용히 퍼지지 않고 터진다."""
    shared = scenario_cache._load_scenario_snapshot_resource(
        str(seeded.database_path), seeded.official_revision_id
    )
    upeh = shared["tables"]["RQ_UPEH"]
    numeric = _numeric_column(upeh)
    before = float(upeh[numeric].iloc[0])
    with pytest.raises(ValueError, match="read-only"):
        upeh.iloc[0, list(upeh.columns).index(numeric)] = before + 1.0
    assert float(upeh[numeric].iloc[0]) == before
    for frame in shared["tables"].values():
        copy = frame.copy(deep=True)
        for column in copy.columns:
            assert copy[column].to_numpy().flags.writeable, column


def test_a_cache_hit_does_not_read_the_database(
    seeded: _Seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = str(seeded.database_path)
    expected = scenario_cache.load_scenario_snapshot(database_path, seeded.official_revision_id)

    def no_reads(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("적중한 스냅샷이 DB 를 다시 읽었다")

    monkeypatch.setattr(DuckDBScenarioRepository, "load_revision", no_reads)
    again = scenario_cache.load_scenario_snapshot(database_path, seeded.official_revision_id)
    for name, frame in expected.tables.items():
        _assert_same_frame(again.tables[name], frame)


# --------------------------------------------------------------- 무효화


def test_clearing_the_display_order_cache_reloads_the_shared_snapshot(tmp_path: Path) -> None:
    """공용 표시순서를 바꾸고 `clear_global_display_order_cache` 를 부르면 공유 스냅샷도 따른다."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario

    database_path = tmp_path / "scenario.duckdb"
    repository = _repository(database_path)
    release = ensure_initial_scenario(repository).release
    assert release is not None
    before = scenario_cache.load_scenario_snapshot(str(database_path), release.revision_id)
    rules = repository.load_global_display_order().rules
    directions = rules["정렬방식"].astype("string").tolist()
    directions[0] = "내림차순" if directions[0] != "내림차순" else "오름차순"
    repository.replace_global_display_order(rules.assign(정렬방식=directions), source="테스트")

    # 비우기 전에는 공유 칸이 그대로다(불변 리비전 키) — 비우는 것이 무효화 장치다.
    cached = scenario_cache.load_scenario_snapshot(str(database_path), release.revision_id)
    _assert_same_frame(cached.tables["RQ_DISPLAY_ORDER"], before.tables["RQ_DISPLAY_ORDER"])

    scenario_cache.clear_global_display_order_cache()
    after = scenario_cache.load_scenario_snapshot(str(database_path), release.revision_id)
    _assert_same_frame(
        after.tables["RQ_DISPLAY_ORDER"],
        repository.load_revision(release.revision_id).tables["RQ_DISPLAY_ORDER"],
    )
    assert after.tables["RQ_DISPLAY_ORDER"]["정렬방식"].astype("string").tolist() == directions
    assert not after.tables["RQ_DISPLAY_ORDER"]["정렬방식"].equals(
        before.tables["RQ_DISPLAY_ORDER"]["정렬방식"]
    )
    # 표시순서 말고는 그대로다.
    _assert_same_frame(after.tables["RQ_UPEH"], before.tables["RQ_UPEH"])


def test_clearing_the_snapshot_cache_reloads_the_scenario_name(tmp_path: Path) -> None:
    """이름을 바꾼 뒤 `clear_scenario_snapshot_cache`·`clear_scenario_repository` 가 칸을 비운다."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario

    database_path = tmp_path / "scenario.duckdb"
    repository = _repository(database_path)
    release = ensure_initial_scenario(repository).release
    assert release is not None
    path = str(database_path)
    original = scenario_cache.load_scenario_snapshot(
        path, release.revision_id
    ).scenario.scenario_name

    repository.rename_scenario(release.scenario_id, "새 이름")
    assert scenario_cache.load_scenario_snapshot(
        path, release.revision_id
    ).scenario.scenario_name == (original)
    scenario_cache.clear_scenario_snapshot_cache()
    assert (
        scenario_cache.load_scenario_snapshot(path, release.revision_id).scenario.scenario_name
        == "새 이름"
    )

    repository.rename_scenario(release.scenario_id, "또 새 이름")
    scenario_cache.clear_scenario_repository()
    assert (
        scenario_cache.load_scenario_snapshot(path, release.revision_id).scenario.scenario_name
        == "또 새 이름"
    )
