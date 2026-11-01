# Purpose: 바꾼 것 없는 신규 리비전 저장이 새 리비전을 만들지 않는 저장소 판정을 고정한다.

"""`DuckDBScenarioRepository.save_revision(..., skip_unchanged=True)` — 2026-11-01 개선 I5.

E2E #10: 사이드바 「신규 리비전 저장」 은 바뀐 것이 없어도(「저장된 리비전」 · 미저장 없음) 새
리비전 r3 을 만들었다(r1 과 같은 내용). 이제 쓰기 잠금 안에서 그 시나리오의 **최신** 리비전과 편집
14표의 내용 지문 · 프리셋 · 가상 제품 이력을 견줘 모두 같으면 쓰지 않고 `RevisionUnchanged` 를
올린다. 리비전명 · 메모는 이름표라 보지 않는다. 옛 리비전을 불러와 그대로 저장해도 최신과 내용이
다르면 새 리비전이다 (옛 내용을 최신으로 되살린다). 견주기는 화면이 켜는 길뿐이고 기본(자동 갱신 ·
시험)은 그대로다.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
from test_duckdb_repository import _reference_tables

from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset, ScenarioSnapshot
from capa_simulation.persistence.repository import (
    REVISION_TABLES,
    DuckDBScenarioRepository,
    RevisionUnchanged,
)

VIRTUAL = {
    "product": "DEMO_VIRTUAL",
    "stack": "8H",
    "source_product": "Product-A",
    "source_stack": "8H",
}


def _preset(**overrides: object) -> ScenarioPreset:
    base: dict[str, object] = {
        "start_month": 202608,
        "end_month": 202608,
        "included_processes": ("Process-A",),
    }
    base.update(overrides)
    return ScenarioPreset(**base)  # type: ignore[arg-type]


def _created(tmp_path: Path) -> tuple[DuckDBScenarioRepository, ScenarioSnapshot]:
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name="바꾼 것 없는 저장",
            source_simulation_code="DEMO-I5",
            source_simulation_name="DEMO",
            source_type="test",
            pipeline_version="test-v1",
        ),
        _reference_tables(),
        _preset(),
    )
    return repository, created


def _loaded(repository: DuckDBScenarioRepository, revision_id: str) -> dict[str, pd.DataFrame]:
    """불러온 세션의 편집 14표 — DB 에서 읽은 그대로(지문이 저장한 지문과 같아야 한다)."""
    snapshot = repository.load_revision(revision_id)
    return {name: snapshot.tables[name] for name in REVISION_TABLES}


def _count(repository: DuckDBScenarioRepository, scenario_id: str) -> int:
    return len(repository.list_revisions(scenario_id))


def test_saving_the_latest_revision_unchanged_writes_nothing(tmp_path: Path) -> None:
    repository, created = _created(tmp_path)
    scenario_id = created.scenario.scenario_id

    with pytest.raises(RevisionUnchanged) as raised:
        repository.save_revision(
            scenario_id,
            _loaded(repository, created.revision.revision_id),
            repository.load_revision_preset(created.revision.revision_id),
            revision_name="이름만 다른 저장",
            note="메모도 다르다",
            parent_revision_id=created.revision.revision_id,
            skip_unchanged=True,
        )

    assert raised.value.revision_no == 1
    assert str(raised.value) == (
        "바뀐 것이 없습니다 — 편집 표·조회기간·공정 필터가 최신 리비전 r1 그대로라 새 리비전을 "
        "만들지 않았습니다."
    )
    assert _count(repository, scenario_id) == 1
    assert repository.list_scenarios()[0].active_revision_id == created.revision.revision_id


def test_without_the_flag_the_same_content_is_still_a_new_revision(tmp_path: Path) -> None:
    """자동 갱신 · 시험처럼 화면 밖의 길은 그대로 — 견주지 않는다."""
    repository, created = _created(tmp_path)

    saved = repository.save_revision(
        created.scenario.scenario_id,
        _loaded(repository, created.revision.revision_id),
        _preset(),
        revision_name="그대로 r2",
    )

    assert saved.revision.revision_no == 2


def test_the_process_filter_order_alone_is_not_a_change(tmp_path: Path) -> None:
    """포함 공정은 필터라 차례가 뜻이 없다 — HOME 이 아는 공정을 다시 세우며 차례만 바꾼다."""
    repository, created = _created(tmp_path)
    tables = _loaded(repository, created.revision.revision_id)
    reqb = tables["RQ_REQB"]
    tables["RQ_REQB"] = pd.concat([reqb, reqb.assign(공정="Process-B")], ignore_index=True)
    two = repository.save_revision(
        created.scenario.scenario_id,
        tables,
        _preset(included_processes=("Process-A", "Process-B")),
        revision_name="두 공정",
    )

    with pytest.raises(RevisionUnchanged):
        repository.save_revision(
            created.scenario.scenario_id,
            _loaded(repository, two.revision.revision_id),
            _preset(included_processes=("Process-B", "Process-A")),
            revision_name="차례만",
            skip_unchanged=True,
        )


@pytest.mark.parametrize(
    "change",
    ["table", "period", "process_filter", "standard_target", "virtual_product"],
)
def test_any_content_change_is_still_saved(tmp_path: Path, change: str) -> None:
    repository, created = _created(tmp_path)
    tables = _loaded(repository, created.revision.revision_id)
    preset = repository.load_revision_preset(created.revision.revision_id)
    virtual: list[dict[str, str]] = []
    if change == "table":
        tables["RQ_PKG_PLAN"] = tables["RQ_PKG_PLAN"].assign(생산수량=101.0)
    elif change == "period":
        preset = replace(preset, end_month=202609)
    elif change == "process_filter":
        preset = replace(preset, included_processes=())
    elif change == "standard_target":
        preset = replace(preset, standard_target_show_detail=True)
    else:
        virtual = [VIRTUAL]

    saved = repository.save_revision(
        created.scenario.scenario_id,
        tables,
        preset,
        revision_name="바꾼 저장",
        virtual_products=virtual,
        skip_unchanged=True,
    )

    assert saved.revision.revision_no == 2


def test_the_same_virtual_product_history_is_not_a_change(tmp_path: Path) -> None:
    repository, created = _created(tmp_path)
    tables = _loaded(repository, created.revision.revision_id)
    two = repository.save_revision(
        created.scenario.scenario_id,
        tables,
        _preset(),
        revision_name="가상 제품",
        virtual_products=[VIRTUAL],
    )

    with pytest.raises(RevisionUnchanged) as raised:
        repository.save_revision(
            created.scenario.scenario_id,
            _loaded(repository, two.revision.revision_id),
            _preset(),
            revision_name="가상 제품 그대로",
            virtual_products=[dict(VIRTUAL)],
            skip_unchanged=True,
        )

    assert raised.value.revision_no == 2


def test_an_old_revision_saved_unchanged_becomes_the_latest_again(tmp_path: Path) -> None:
    """r1 을 불러와 그대로 저장하면 최신 r2 와 다르다 — r1 의 내용을 최신으로 되살리는 새
    리비전이다."""
    repository, created = _created(tmp_path)
    first = created.revision.revision_id
    edited = _loaded(repository, first)
    edited["RQ_PKG_PLAN"] = edited["RQ_PKG_PLAN"].assign(생산수량=555.0)
    repository.save_revision(
        created.scenario.scenario_id, edited, _preset(), revision_name="r2 편집"
    )

    restored = repository.save_revision(
        created.scenario.scenario_id,
        _loaded(repository, first),
        repository.load_revision_preset(first),
        revision_name="r1 되살림",
        parent_revision_id=first,
        skip_unchanged=True,
    )

    assert restored.revision.revision_no == 3
    assert restored.tables["RQ_PKG_PLAN"]["생산수량"].tolist() == [100.0]
