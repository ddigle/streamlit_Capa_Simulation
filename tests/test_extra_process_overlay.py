# Purpose: 「부대공정 얹기」 가 옛 판 행을 걷고 새 판으로 새 시나리오를 만들며 파생 저장이 판 출처를
# 잇는지 본다.

"""「부대공정 얹기」(`components/scenario_extra_overlay.py` · `extra_process_merge.overlay_*` —
설계 4-8 · D19 · A13)와 파생 저장의 출처 잇기(D18).

판 1 을 적용해 등록한 시나리오(부대공정 둘이 합쳐짐)를 바탕으로, 판 2(`DEMO_New_Bond` 의 202607 부터
UPEH 58000 → 60000)를 얹는다. 걷지 않으면 R-01 이 판 1 의 행을 BDQ 행으로 잘못 보고 건너뛴다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_update_fakes import new_repository
from extra_process_fixtures import (
    AOI,
    BOND,
    bump_version,
    edited,
    set_cell,
    template_files,
    zip_files,
)
from streamlit.testing.v1 import AppTest
from test_extra_process_registration import apply_template, register

from capa_simulation.components.scenario_extra_overlay import (
    EXTRA_OVERLAY_MODE,
    OVERLAY_OPERATION,
)
from capa_simulation.persistence.models import ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_registration import load_active_extra_pack
from capa_simulation.services.extra_process_merge import (
    OUTCOME_GRADUATED,
    OUTCOME_MERGED,
    merge_extra_processes,
    overlay_extra_processes,
    overlay_included_processes,
)
from capa_simulation.services.extra_process_pack import read_pack_zip


def _second_version() -> bytes:
    files = bump_version(template_files(), 2)
    files = edited(
        files,
        "03_productivity.csv",
        lambda rows: set_cell(
            rows, lambda row: row[0] == BOND and row[7] == "202607", "UPEH", "60000"
        ),
    )
    return zip_files(files)


def _apply(repository: DuckDBScenarioRepository, data: bytes, expected_seq: int) -> None:
    reading = read_pack_zip(data)
    assert reading.pack is not None
    repository.apply_extra_process(
        data,
        sha256=reading.sha256,
        version_no=reading.pack.info.version_no,
        expected_seq=expected_seq,
        applied_by=None,
        process_count=len(reading.pack.processes),
        row_counts=json.dumps(reading.pack.row_counts()),
        source_place="test",
    )


@pytest.fixture
def based(tmp_path: Path) -> tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot]:
    database = tmp_path / "overlay.duckdb"
    repository = new_repository(database)
    apply_template(repository)
    snapshot, _ = register(repository)
    _apply(repository, _second_version(), expected_seq=1)
    return repository, database, snapshot


def test_overlay_strips_the_old_version_and_merges_the_new_one(
    based: tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot],
) -> None:
    repository, _, base = based
    active = load_active_extra_pack(repository)
    assert active is not None and active.version.version_no == 2

    # 걷지 않으면 옛 판 행을 BDQ 로 잘못 보고 건너뛴다(설계 4-8 의 까닭).
    unstripped = merge_extra_processes(base.tables, active)
    assert {item.outcome for item in unstripped.report.outcomes} == {OUTCOME_GRADUATED}

    result = overlay_extra_processes(base.tables, (BOND, AOI), active)

    assert [item.outcome for item in result.report.outcomes] == [OUTCOME_MERGED, OUTCOME_MERGED]
    upeh = result.tables["RQ_UPEH"]
    bond = upeh.loc[upeh["공정"].eq(BOND)]
    assert set(bond.loc[bond["생산계획년월"].ge(202607), "UPEH"]) == {60000.0}
    assert len(result.tables["RQ_REQB"]) == len(base.tables["RQ_REQB"])


def test_overlay_keeps_what_the_base_preset_had_switched_off() -> None:
    from capa_simulation.services.extra_process_merge import ExtraMergeReport, ProcessOutcome

    report = ExtraMergeReport(
        outcomes=(ProcessOutcome(BOND, OUTCOME_MERGED), ProcessOutcome(AOI, OUTCOME_MERGED))
    )

    included = overlay_included_processes(("P1", BOND), (BOND, AOI), report)

    # 바탕에서 끈 P2 · 걷은 AOI 는 다시 켜지지 않고, 새로 합친 둘이 든다.
    assert included == ("P1", BOND, AOI)


def _overlay_app(database: Path) -> AppTest:
    script = f"""
import streamlit as st

from capa_simulation.components.scenario_extra_overlay import render_scenario_extra_overlay
from capa_simulation.persistence.cache import get_scenario_repository

database_path = {str(database)!r}
render_scenario_extra_overlay(get_scenario_repository(database_path), database_path)
"""
    return AppTest.from_string(script, default_timeout=60).run()


def test_the_overlay_screen_saves_a_new_scenario_with_the_new_provenance(
    based: tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot],
) -> None:
    repository, database, base = based
    app = _overlay_app(database)
    app.selectbox(key="extra_source_scenario").set_value(base.scenario.scenario_id).run()
    assert not app.exception, [item.message for item in app.exception]
    outcome = next(frame.value for frame in app.dataframe if "결과" in frame.value)
    assert list(outcome["결과"]) == ["합침", "합침"]

    next(button for button in app.button if button.label == "새 시나리오로 저장").click().run()
    assert not app.exception, [item.message for item in app.exception]

    created = next(
        item for item in repository.list_scenarios() if item.source_type == OVERLAY_OPERATION
    )
    snapshot = repository.load_revision(created.active_revision_id)
    assert {BOND, AOI} <= set(snapshot.preset.included_processes)
    provenance = repository.load_dataset_extra_process(created.dataset_id)
    assert {(item.process_name, item.version_no) for item in provenance} == {(BOND, 2), (AOI, 2)}
    assert snapshot.revision.note is not None and "부대공정 판 2 · 2 합침" in snapshot.revision.note
    # 바탕 시나리오 · 그 출처는 그대로다.
    assert {
        item.version_no for item in repository.load_dataset_extra_process(base.scenario.dataset_id)
    } == {1}


def test_the_overlay_mode_only_lists_while_a_version_is_active(
    based: tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot],
) -> None:
    repository, database, _ = based
    script = f"""
import streamlit as st

from capa_simulation.components.scenario_management import _has_active_extra_process
from capa_simulation.persistence.cache import get_scenario_repository

st.write(str(_has_active_extra_process(get_scenario_repository({str(database)!r}))))
"""
    assert AppTest.from_string(script).run().markdown[0].value == "True"
    repository.turn_off_extra_process(expected_seq=2, applied_by=None)
    assert AppTest.from_string(script).run().markdown[0].value == "False"
    assert EXTRA_OVERLAY_MODE == "부대공정 얹기"


def test_year_shift_and_clone_paths_carry_the_base_provenance(
    based: tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot],
) -> None:
    from capa_simulation.components.scenario_transform import carried_extra_process

    repository, _, base = based

    carried = carried_extra_process(repository, ((base, "연도 Shift +1년"),))

    assert {(item.process_name, item.note) for item in carried} == {
        (BOND, "연도 Shift +1년"),
        (AOI, "연도 Shift +1년"),
    }
