# Purpose: 활성 부대공정 판이 화면 등록 · 자동 갱신 길로 리비전에 들고 화면에 두 공정이 서는지 본다.

"""부대공정 등록 이음매(`core_data_pipeline.fetch_registration_dataset` — 설계 A4 · T2 1단계 몫).

판을 DB 에 적용한 뒤 가짜 BigDataQuery(내장 합성 시드 원천 — `auto_update_fakes`)로 화면 등록과 같은
길(이음매 → 프리셋 → 저장)과 자동 갱신 회차를 돈다. 내장 시드 부트스트랩은 이음매를 지나지 않는다.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest
from auto_update_fakes import (
    CHIP,
    DISPLAY_ORDER,
    FakeBigDataQuery,
    FakeProvider,
    catalog_frame,
    fixed_clock,
    new_repository,
    official_w40,
    publish_snapshot,
    source_frame,
)
from extra_process_fixtures import AOI, BOND, edited, set_cell, template_files, zip_files
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script

from capa_simulation.auto_official_update_runner import DetailRequest, run_auto_official_update
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
from capa_simulation.persistence.models import ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import full_data_scenario_preset
from capa_simulation.scenario_registration import (
    load_active_extra_pack,
    save_bigdataquery_scenario,
)
from capa_simulation.services.auto_official_update import STATUS_PUBLISHED, TRIGGER_MANUAL
from capa_simulation.services.core_data_pipeline import fetch_registration_dataset
from capa_simulation.services.dashboard import build_monthly_bottleneck_ranking
from capa_simulation.services.extra_process_merge import OUTCOME_DROPPED, OUTCOME_MERGED
from capa_simulation.services.extra_process_pack import read_pack_zip
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.simulation_cache import full_capacity_outcome


def short_files() -> dict[str, bytes]:
    """견본에서 부대설비 보유를 줄여 두 공정의 확보율이 경고 기준(100%) 아래로 가는 사본 — Static
    Capa 화면은 기준 미달 공정만 표에 세운다(합성 값 — 소요 약 0.03 · 0.09 대에 보유 0.02 ·
    0.06)."""
    files = edited(
        template_files(),
        "04_equipment_days.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == BOND, "설비보유", "0.02"),
    )
    files = edited(
        files,
        "04_equipment_days.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == AOI, "설비보유", "0.06"),
    )
    return edited(
        files,
        "04_equipment_days.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == AOI, "설비대여평가", "0"),
    )


def apply_template(
    repository: DuckDBScenarioRepository,
    *,
    expected_seq: int = 0,
    files: dict[str, bytes] | None = None,
) -> None:
    data = zip_files(template_files() if files is None else files)
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


def register(
    repository: DuckDBScenarioRepository,
    *,
    code: str = "SIM-EXTRA",
    name: str = "PSM W41",
    frame: pd.DataFrame | None = None,
) -> tuple[ScenarioSnapshot, str]:
    """화면 등록과 같은 길 — 이음매(판 합치기)를 프리셋보다 먼저 지난다. (스냅샷, 메모 조각)."""
    request = DetailRequest(
        code, name, datetime(2026, 10, 12, 9, 0), QueryWindow(date(2026, 9, 12), date(2026, 10, 12))
    )
    provider = FakeProvider(request, source_frame() if frame is None else frame)
    data = fetch_registration_dataset(
        provider, code, DISPLAY_ORDER, load_active_extra_pack(repository)
    )
    snapshot = save_bigdataquery_scenario(
        repository,
        data.prepared,
        full_data_scenario_preset(data.prepared.reference_tables),
        scenario_name=f"{name} ({code})",
        revision_name="초기 리비전",
        note="",
        extra=data.extra,
    ).snapshot
    return snapshot, data.extra.memo()


@pytest.fixture
def repository(tmp_path: Path) -> DuckDBScenarioRepository:
    return new_repository(tmp_path / "extra_registration.duckdb")


def test_registering_with_the_active_pack_brings_both_processes_into_the_revision(
    repository: DuckDBScenarioRepository,
) -> None:
    apply_template(repository)

    snapshot, memo = register(repository)

    assert memo == "부대공정 판 1 · 2 합침"
    assert snapshot.revision.note is not None and memo in snapshot.revision.note
    # 프리셋(전 공정)이 부대공정을 저절로 넣는다 — HOME LOB · B/N · Summary 의 포함 공정.
    assert {BOND, AOI} <= set(snapshot.preset.included_processes)
    outcome = full_capacity_outcome(snapshot.tables, snapshot.tables)
    assert outcome.error is None and outcome.required_equipment is not None
    securement = calculate_securement_rate(
        snapshot.tables["RQ_EQP_AVBL"], outcome.required_equipment
    )
    ranking = build_monthly_bottleneck_ranking(securement, list(snapshot.preset.included_processes))
    assert {BOND, AOI} <= set(ranking["공정"])
    # 모듈수는 데이터셋 표에 처음부터 실린다.
    assert {BOND, AOI} <= set(snapshot.tables["RQ_MODULE"]["공정"])
    provenance = repository.load_dataset_extra_process(snapshot.scenario.dataset_id)
    assert {(item.process_name, item.outcome) for item in provenance} == {
        (BOND, OUTCOME_MERGED),
        (AOI, OUTCOME_MERGED),
    }
    # 원천은 BDQ 그대로다 — 부대공정은 기준정보 표에만 더한다.
    assert (
        not repository.load_source_data(snapshot.scenario.scenario_id)["공정"]
        .isin([BOND, AOI])
        .any()
    )


def test_off_leaves_the_next_registration_without_extras_and_resume_brings_them_back(
    repository: DuckDBScenarioRepository,
) -> None:
    apply_template(repository)
    repository.turn_off_extra_process(expected_seq=1, applied_by=None)

    off, off_memo = register(repository, code="SIM-OFF")

    assert off_memo == ""
    assert not off.tables["RQ_REQB"]["공정"].isin([BOND, AOI]).any()
    assert repository.load_dataset_extra_process(off.scenario.dataset_id) == ()

    repository.resume_extra_process(expected_seq=2, applied_by=None)
    back, back_memo = register(repository, code="SIM-BACK")

    assert back_memo == "부대공정 판 1 · 2 합침"
    assert {BOND, AOI} <= set(back.tables["RQ_REQB"]["공정"])


def test_auto_update_drops_only_the_extra_process_that_does_not_mesh(
    repository: DuckDBScenarioRepository,
) -> None:
    """그날 BDQ 에 따라가는 공정이 없으면 그 부대공정만 빼고 등록 · 공식 지정한다(설계 D10)."""
    official_w40(repository)
    apply_template(repository)
    source = source_frame()
    fake = FakeBigDataQuery(
        catalog_frame(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")),
        frames={
            "SIM-W41": source.loc[~source["공정"].eq(CHIP).fillna(False)].reset_index(drop=True)
        },
    )

    result = run_auto_official_update(
        repository, trigger=TRIGGER_MANUAL, sources=fake.sources, clock=fixed_clock
    )

    run = result.run
    assert run is not None and run.status == STATUS_PUBLISHED, run
    assert run.reason is not None and "부대공정 판 1 · 1 합침 · 1 뺌" in run.reason
    assert run.created_scenario_id is not None and run.filtered_revision_id is not None
    filtered = repository.load_revision(run.filtered_revision_id)
    assert AOI in set(filtered.tables["RQ_REQB"]["공정"])
    assert BOND not in set(filtered.tables["RQ_REQB"]["공정"])
    assert AOI in filtered.preset.included_processes
    assert filtered.revision.note is not None and "부대공정 판 1" in filtered.revision.note
    # 출처는 데이터셋 단위라 리비전 2 도 같은 줄을 본다.
    provenance = {
        item.process_name: item.outcome
        for item in repository.load_dataset_extra_process(filtered.scenario.dataset_id)
    }
    assert provenance == {BOND: OUTCOME_DROPPED, AOI: OUTCOME_MERGED}


def _shown_text(app: AppTest) -> str:
    """화면에 선 표 · 그림 · 글을 한 글로(공정 이름이 어디든 서 있나 보려고)."""
    parts: list[str] = []
    for frame in app.dataframe:
        parts.append(frame.value.to_string())
    for element in app.get("plotly_chart"):
        parts.append(str(element.proto.spec))
    for kind in ("markdown", "html"):
        for element in app.get(kind):
            parts.append(str(element.proto.body))
    return "\n".join(parts)


@pytest.mark.parametrize(
    "page_path",
    ["app_pages/home.py", "app_pages/static_capa.py", "app_pages/calculation_result.py"],
)
def test_home_static_and_calculation_pages_show_both_extra_processes(
    tmp_path: Path, page_path: str
) -> None:
    database = tmp_path / "pages.duckdb"
    repository = new_repository(database)
    apply_template(repository, files=short_files())
    snapshot, _ = register(repository)
    publish_snapshot(repository, snapshot)

    app = AppTest.from_string(
        _page_script(page_path, database, tmp_path / "equipment.duckdb"), default_timeout=120
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    shown = _shown_text(app)
    assert BOND in shown and AOI in shown, page_path


def test_the_input_check_adds_an_extra_process_group_only_when_extras_were_merged(
    tmp_path: Path,
) -> None:
    """입력 점검 「부대공정」 묶음(설계 A10) — 판을 합친 리비전에만 서고 공정마다 판 · 경로 수를
    싣는다. 판 없이 등록한 리비전의 묶음 · 「확인 n」 은 그대로다."""
    from capa_simulation.components.capacity_gate import input_check_verdict
    from capa_simulation.services.revision_input_check import EXTRA_COLUMNS, GROUP_EXTRA

    database = tmp_path / "extra_check.duckdb"
    repository = new_repository(database)
    plain, _ = register(repository, code="SIM-PLAIN", name="PSM W40")
    apply_template(repository)
    merged, _ = register(repository)

    without = input_check_verdict(
        str(database), plain.scenario.scenario_id, plain.revision.revision_id
    )
    with_extra = input_check_verdict(
        str(database), merged.scenario.scenario_id, merged.revision.revision_id
    )

    assert without.group(GROUP_EXTRA) is None
    group = with_extra.group(GROUP_EXTRA)
    assert group is not None and group.title == "부대공정" and group.level == "check"
    (table,) = group.tables
    assert list(table.frame.columns) == list(EXTRA_COLUMNS)
    assert sorted(table.frame["공정"]) == sorted([BOND, AOI])
    assert set(table.frame["판"]) == {"1"}
    assert (table.frame["부하 붙은 경로"] > 0).all()
    assert group.count == 0 and not group.flagged
