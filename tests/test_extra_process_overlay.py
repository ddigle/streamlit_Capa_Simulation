# Purpose: 「부대공정 얹기」 가 옛 판 행을 걷고 새 판으로 새 시나리오를 만들며 파생 저장이 판 출처를
# 잇는지 본다.

"""「부대공정 얹기」(`components/scenario_extra_overlay.py` · `extra_process_merge.overlay_*` —
설계 4-8 · D19 · A13)와 파생 저장의 출처 잇기(D18).

판 1 을 적용해 등록한 시나리오(부대공정 둘이 합쳐짐)를 바탕으로, 판 2(`DEMO_New_Bond` 의 202607 부터
UPEH 58000 → 60000)를 얹는다. 걷지 않으면 R-01 이 판 1 의 행을 BDQ 행으로 잘못 보고 건너뛴다.
"""

from __future__ import annotations

import json
from dataclasses import replace
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
from capa_simulation.persistence.models import ScenarioCreate, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_registration import load_active_extra_pack
from capa_simulation.services.extra_process_merge import (
    MIXED_REASON,
    OUTCOME_DROPPED,
    OUTCOME_GRADUATED,
    OUTCOME_MERGED,
    fold_outcomes,
    merge_extra_processes,
    overlay_extra_processes,
    overlay_included_processes,
    split_previous,
    strip_extra_processes,
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

    # 바탕에서 끈 P2 와, 바탕에서 꺼 둔 옛 판 AOI 는 다시 켜지지 않는다 — 켜 둔 BOND 만 새 판으로
    # 다시 든다.
    assert included == ("P1", BOND)
    # 바탕에 없던 새 부대공정은 더한다.
    assert overlay_included_processes(("P1",), (), report) == ("P1", BOND, AOI)


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


# ------------------------------------------------------------------ 월 머지 뒤 판 · BDQ 행 섞임


def _derived(
    repository: DuckDBScenarioRepository,
    base: ScenarioSnapshot,
    name: str,
    provenance: tuple[object, ...] | None = None,
    *,
    graduated: tuple[str, ...] = (),
) -> ScenarioSnapshot:
    """바탕 표로 새 시나리오 — 출처 줄은 바탕 것을 그대로(`graduated` 공정은 BDQ 에 생김으로 바꿔).
    BDQ 가 그 공정을 스스로 가진 원본의 출처 꼴이다(표는 같아도 출처만 본다)."""
    records = tuple(
        replace(record, outcome=OUTCOME_GRADUATED, rule="R-01", row_counts=None)
        if record.process_name in graduated
        else record
        for record in repository.load_scenario_extra_process(base.scenario.scenario_id)
    )
    created = ScenarioCreate(
        scenario_name=name,
        source_simulation_code=f"TEST-{name}",
        source_simulation_name=base.scenario.scenario_name,
        source_type="SCENARIO_MONTH_MERGE",
        pipeline_version="test",
    )
    return repository.create_scenario(
        created,
        base.tables,
        base.preset,
        extra_process=provenance if provenance is not None else records,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("bdq_first", [False, True], ids=["판-베이스", "BDQ-베이스"])
def test_a_month_merge_of_merged_and_graduated_sources_is_not_stripped(
    based: tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot], bdq_first: bool
) -> None:
    """월 머지 두 차례 — 한 원본은 판으로 BOND 를 합쳤고(MERGED) 다른 원본은 BDQ 가 BOND 를 스스로
    가졌다(GRADUATED, 같은 판 차례). 출처 표는 (공정, 판 차례)가 키라 두 줄이 겹친다 — 어느 차례로
    머지해도 한 줄을 잃지 않고 섞임 뺌 줄 하나로 접고, 얹기는 BOND 를 걷지 않는다(걷으면 BDQ 달의
    BOND 행까지 지운다). 섞이지 않은 AOI 는 그대로 걷는다."""
    from capa_simulation.components.scenario_transform import carried_extra_process

    repository, _, merged_source = based
    bdq_source = _derived(repository, merged_source, "BDQ 원본", graduated=(BOND,))
    first, second = (bdq_source, merged_source) if bdq_first else (merged_source, bdq_source)

    carried = carried_extra_process(
        repository, ((first, "월 머지 베이스"), (second, "월 머지 덧붙임"))
    )
    month_merged = _derived(repository, first, "월 머지", provenance=carried)

    saved = repository.load_scenario_extra_process(month_merged.scenario.scenario_id)
    bond = [item for item in saved if item.process_name == BOND]
    assert [(item.outcome, item.reason) for item in bond] == [(OUTCOME_DROPPED, MIXED_REASON)]
    assert bond[0].note == "월 머지 베이스 / 월 머지 덧붙임"
    extras = split_previous(saved)
    assert extras.stripped == (AOI,) and extras.mixed == (BOND,)


def test_a_second_month_merge_keeps_the_mixed_mark(
    based: tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot],
) -> None:
    """섞임으로 접은 월 머지 결과를 판으로 합친 원본과 다시 월 머지해도(같은 판 차례로 겹침) 섞임은
    합침으로 접히지 않는다 — 그 이름의 행은 여전히 섞여 있다."""
    from capa_simulation.components.scenario_transform import carried_extra_process

    repository, _, merged_source = based
    bdq_source = _derived(repository, merged_source, "BDQ 원본", graduated=(BOND,))
    carried = carried_extra_process(
        repository, ((merged_source, "월 머지 베이스"), (bdq_source, "월 머지 덧붙임"))
    )
    month_merged = _derived(repository, merged_source, "월 머지", provenance=carried)

    again = carried_extra_process(
        repository, ((month_merged, "월 머지 베이스"), (merged_source, "월 머지 덧붙임"))
    )

    bond = [item for item in again if item.process_name == BOND]
    assert [(item.outcome, item.reason) for item in bond] == [(OUTCOME_DROPPED, MIXED_REASON)]
    assert split_previous(again).mixed == (BOND,)


def test_merged_and_graduated_rows_of_different_versions_are_mixed_too() -> None:
    """판 차례가 달라 두 줄이 다 남은 출처(판 v1 합침 · 판 v2 BDQ 에 생김)도 섞임이다. 합침 · 뺌만
    있는 공정은 걷는다(뺀 원본에는 그 행이 없다)."""
    from capa_simulation.persistence.models import ExtraProcessProvenance

    def row(name: str, seq: int, outcome: str) -> ExtraProcessProvenance:
        return ExtraProcessProvenance(name, seq, seq, "0" * 64, outcome)

    extras = split_previous(
        [
            row(BOND, 1, OUTCOME_MERGED),
            row(BOND, 2, OUTCOME_GRADUATED),
            row(AOI, 1, OUTCOME_MERGED),
            row(AOI, 2, OUTCOME_DROPPED),
            row("DEMO_Only_BDQ", 2, OUTCOME_GRADUATED),
        ]
    )
    assert extras.stripped == (AOI,) and extras.mixed == (BOND,)
    assert fold_outcomes([OUTCOME_DROPPED, OUTCOME_MERGED]) == (OUTCOME_MERGED, False)
    assert fold_outcomes([OUTCOME_GRADUATED, OUTCOME_DROPPED]) == (OUTCOME_GRADUATED, False)
    assert fold_outcomes([OUTCOME_GRADUATED, OUTCOME_MERGED]) == (OUTCOME_DROPPED, True)


def test_stripping_by_name_would_remove_the_bdq_rows_of_a_mixed_process(
    based: tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot],
) -> None:
    """걷기는 이름으로 모든 달을 지운다 — 섞인 공정을 걷을 목록에 넣으면 BDQ 공정 행까지 사라진다
    (그래서 섞임은 걷지 않는다). BDQ 공정 이름 하나를 넣으면 그 행이 0 이 되는 것으로 본다."""
    _, _, base = based
    reqb = base.tables["RQ_REQB"]
    bdq_name = next(name for name in reqb["공정"].astype(str).unique() if name not in {BOND, AOI})

    stripped = strip_extra_processes(base.tables, (BOND, AOI, bdq_name))

    assert stripped["RQ_REQB"]["공정"].eq(bdq_name).sum() == 0
    assert reqb["공정"].eq(bdq_name).sum() > 0


@pytest.mark.parametrize("shifted_first", [False, True], ids=["Shift-덧붙임", "Shift-베이스"])
def test_a_month_merge_with_a_year_shifted_source_keeps_the_shift_mark(
    based: tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot], shifted_first: bool
) -> None:
    """연도 Shift 한 사본을 월 머지의 어느 쪽에 두어도(같은 판이라 출처 줄이 한 줄로 접힘) 「연도
    Shift」 메모가 남아 「이 리비전 값을 새 판으로」 가 거절된다(설계 G4) — 접기가 첫 줄 메모만
    남기면 덧붙일 쪽의 Shift 표지가 사라져 연도를 옮긴 행 값이 다음 판에 든다."""
    from capa_simulation.components.scenario_transform import carried_extra_process
    from capa_simulation.services.extra_process_revision import revision_refusal

    repository, _, base = based
    shifted = _derived(
        repository,
        base,
        "연도 Shift",
        provenance=carried_extra_process(repository, ((base, "연도 Shift +1년"),)),
    )
    first, second = (shifted, base) if shifted_first else (base, shifted)

    carried = carried_extra_process(
        repository, ((first, "월 머지 베이스"), (second, "월 머지 덧붙임 202701~202712"))
    )
    month_merged = _derived(repository, first, "월 머지", provenance=carried)
    saved = repository.load_scenario_extra_process(month_merged.scenario.scenario_id)

    assert {item.process_name for item in saved} == {BOND, AOI} and len(saved) == 2
    assert all("연도 Shift +1년" in (item.note or "") for item in saved)
    # 리비전의 판(sha)을 활성 판으로 준다 — 다른 판 갈래가 아니라 연도 Shift 갈래로 거절되는지 본다.
    refusal = revision_refusal(
        off=False, active_sha=saved[0].sha256, active_version_no=1, records=saved
    )
    assert refusal is not None and "연도 Shift" in refusal

    plain = carried_extra_process(
        repository, ((base, "월 머지 베이스"), (base, "월 머지 덧붙임 202701~202712"))
    )
    assert (
        revision_refusal(off=False, active_sha=plain[0].sha256, active_version_no=1, records=plain)
        is None
    )
    assert plain[0].note == "월 머지 베이스 / 월 머지 덧붙임 202701~202712"


def test_the_overlay_screen_refuses_a_base_with_mixed_rows(
    based: tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot],
) -> None:
    """섞인 공정이 있는 바탕 — 거부 한 줄과 그 공정 표만 서고 합치기 · 저장 칸이 서지 않는다."""
    from capa_simulation.components.scenario_transform import carried_extra_process

    repository, database, merged_source = based
    bdq_source = _derived(repository, merged_source, "BDQ 원본", graduated=(BOND,))
    carried = carried_extra_process(
        repository, ((merged_source, "월 머지 베이스"), (bdq_source, "월 머지 덧붙임"))
    )
    month_merged = _derived(repository, merged_source, "월 머지", provenance=carried)
    app = _overlay_app(database)

    app.selectbox(key="extra_source_scenario").set_value(month_merged.scenario.scenario_id).run()

    assert not app.exception, [item.message for item in app.exception]
    (error,) = [str(item.value) for item in app.error]
    assert error == "판 · BDQ 행이 섞인 부대공정 1개 — 이 바탕에는 얹지 않습니다"
    (frame,) = [item.value for item in app.dataframe]
    assert list(frame["공정"]) == [BOND] and list(frame["결과"]) == ["섞임"]
    assert not [button for button in app.button if button.label == "새 시나리오로 저장"]


# ------------------------------------------------------- 월 머지 섞임을 결과 달로 가름(A14)


def _no_provenance(
    repository: DuckDBScenarioRepository, base: ScenarioSnapshot, name: str
) -> ScenarioSnapshot:
    """출처 줄이 아예 없는 원본 — 판 없이 등록해 BDQ 가 그 공정을 스스로 가진 꼴(표는 같다)."""
    return _derived(repository, base, name, provenance=())


def test_month_merge_mixing_finds_bdq_rows_from_a_source_without_provenance(
    based: tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot],
) -> None:
    """한 원본에 출처 줄이 아예 없으면(판 없이 등록) 출처만으로는 섞임을 모른다 — 결과의 그 원본
    달에 같은 이름 행이 있으면 BDQ 행으로 보고 섞임으로 가르며, 파생 저장은 그 공정을 섞임 뺌 줄로
    접어 얹기가 걷지 않는다(`docs/TODO.md` 부대공정 ④)."""
    from capa_simulation.components.scenario_transform import carried_extra_process
    from capa_simulation.services.extra_process_merge import month_merge_mixing

    repository, _, merged_source = based
    bdq_source = _no_provenance(repository, merged_source, "BDQ 원본")
    reqb = merged_source.tables["RQ_REQB"]
    months = sorted(int(month) for month in reqb["생산계획년월"].unique())
    origin = {month: ("베이스" if month < 202607 else "덧붙일 쪽") for month in months}
    provenance = {
        "베이스": repository.load_scenario_extra_process(bdq_source.scenario.scenario_id),
        "덧붙일 쪽": repository.load_scenario_extra_process(merged_source.scenario.scenario_id),
    }

    mixing = month_merge_mixing(reqb, origin, provenance)

    assert set(mixing.bdq) == {BOND, AOI} and mixing.versions == ()
    carried = carried_extra_process(
        repository,
        ((bdq_source, "월 머지 베이스"), (merged_source, "월 머지 덧붙임 202607~202612")),
        mixed=mixing.bdq,
    )
    assert {(item.process_name, item.reason) for item in carried} == {
        (BOND, MIXED_REASON),
        (AOI, MIXED_REASON),
    }
    assert split_previous(carried).stripped == ()


def test_month_merge_mixing_tells_two_versions_apart_from_one(
    based: tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot],
) -> None:
    """두 원본이 다른 판을 실으면 「판 섞임」(얹기로 다시 맞춘다), 같은 판이면 섞임이 아니다. 한
    원본의 달에 그 공정 행이 없으면 그 원본은 세지 않는다."""
    from capa_simulation.persistence.models import ExtraProcessProvenance
    from capa_simulation.services.extra_process_merge import month_merge_mixing

    _, _, base = based
    reqb = base.tables["RQ_REQB"]
    origin = {
        int(month): ("베이스" if int(month) < 202607 else "덧붙일 쪽")
        for month in reqb["생산계획년월"].unique()
    }

    def merged(sha: str) -> list[ExtraProcessProvenance]:
        return [ExtraProcessProvenance(BOND, 1, 1, sha, OUTCOME_MERGED)]

    two = month_merge_mixing(
        reqb, origin, {"베이스": merged("a" * 64), "덧붙일 쪽": merged("b" * 64)}
    )
    one = month_merge_mixing(
        reqb, origin, {"베이스": merged("a" * 64), "덧붙일 쪽": merged("a" * 64)}
    )
    later_only = {month: "덧붙일 쪽" for month in origin}
    absent = month_merge_mixing(
        reqb, later_only, {"베이스": merged("a" * 64), "덧붙일 쪽": merged("b" * 64)}
    )

    assert two.versions == (BOND,) and two.bdq == ()
    assert (one.versions, one.bdq) == ((), ()) and absent.versions == ()
