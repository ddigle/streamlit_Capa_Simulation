# Purpose: 부대공정 판을 내장 합성 시드 16표에 펼쳐 합치는 규칙 R-01 ~ R-07 과 옛 판 걷기를 본다.

"""부대공정 합치기(`services/extra_process_merge.py`).

견본 판(`DEMO_New_Bond` 따라가기 꼴 · `DEMO_New_AOI` 지정 꼴)을 내장 합성 시드(공정 셋 · 제품 둘 ·
2026년 12달 — `services/builtin_seed.py` 의 리터럴)에 합친다. 시드에는 PKG · Buffer 경로가 없어 G6
(Q6 「경로 표」) 시험은 시드 `RQ_REQB` 에 PKG 줄을 더한 사본으로 본다. R-07 의 하나씩 더하기는 멈춤
판정을 갈아 끼워(가짜) 본다 — 검사를 지난 판은 실제 계산을 좀처럼 멈추게 하지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import pytest
from extra_process_fixtures import AOI, BOND, edited, set_cell, template_files

from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.extra_process_merge import (
    OUTCOME_DROPPED,
    OUTCOME_GRADUATED,
    OUTCOME_MERGED,
    PROCESS_TABLES,
    RULE_DUPLICATE,
    RULE_PRODUCT,
    RULE_REFERENCE,
    RULE_STOP,
    ActiveExtraPack,
    CapacityCheck,
    ExtraPackVersion,
    capacity_stop,
    load_lines,
    merge_extra_processes,
    process_rows_frame,
    strip_extra_processes,
)
from capa_simulation.services.extra_process_pack import read_pack_files

Tables = dict[str, pd.DataFrame]
Files = dict[str, bytes]


def _seed() -> Tables:
    return {
        name: frame.copy() for name, frame in build_builtin_seed_dataset().reference_tables.items()
    }


def _active(files: Files | None = None, *, version_no: int = 1, seq: int = 1) -> ActiveExtraPack:
    reading = read_pack_files(template_files() if files is None else files)
    assert reading.pack is not None, [problem.text() for problem in reading.problems]
    return ActiveExtraPack(ExtraPackVersion(seq, version_no, reading.sha256), reading.pack)


def _rows(tables: Mapping[str, pd.DataFrame], name: str, process: str) -> pd.DataFrame:
    frame = tables[name]
    return frame.loc[frame["공정"].eq(process)]


def _never_stops(tables: Mapping[str, pd.DataFrame]) -> str | None:
    del tables
    return None


def test_the_template_merges_both_processes_into_the_seed_with_the_same_columns() -> None:
    seed = _seed()

    result = merge_extra_processes(seed, _active())

    report = result.report
    assert [item.outcome for item in report.outcomes] == [OUTCOME_MERGED, OUTCOME_MERGED]
    assert report.memo() == "부대공정 판 1 · 2 합침"
    assert report.flash_text() == "부대공정 2 합침"
    for name, frame in result.tables.items():
        assert list(frame.columns) == list(seed[name].columns), name
        assert frame.dtypes.to_dict() == seed[name].dtypes.to_dict(), name
    upeh = _rows(result.tables, "RQ_UPEH", BOND)
    assert len(result.tables["RQ_UPEH"].columns) == 12
    assert set(upeh["소요기준"]) == {"CHIP"}
    assert set(_rows(result.tables, "RQ_UPEH", AOI)["소요기준"]) == {"WF"}
    # 따라가기 꼴은 참조 공정을 지나는 계획 변형 모두 — 12달 × 제품 둘.
    assert len(_rows(result.tables, "RQ_REQB", BOND)) == 24
    # 지정 꼴은 202603 부터 — 10달 × 제품 둘, WF 구분은 데이터 쪽 글자.
    aoi = _rows(result.tables, "RQ_REQB", AOI)
    assert len(aoi) == 20 and int(aoi["생산계획년월"].min()) == 202603
    assert set(aoi["WF 구분"]) == {"Core", "Base"}
    # 기간 행 — 202607 부터 UPEH · 보유대수가 바뀐다, 가용 = 보유 − 대여.
    assert set(upeh.loc[upeh["생산계획년월"].lt(202607), "UPEH"]) == {54000.0}
    assert set(upeh.loc[upeh["생산계획년월"].ge(202607), "UPEH"]) == {58000.0}
    assert set(_rows(result.tables, "RQ_EQP_AVBL", AOI)["가용대수"]) == {2.5}
    # 달력 = 그 달 날수, 측정률 빈칸 = 1.0.
    days = _rows(result.tables, "RQ_RUN_DAY", BOND)
    assert int(days.loc[days["생산계획년월"].eq(202602), "RUN_DAY"].iloc[0]) == 28
    assert set(_rows(result.tables, "RQ_WF_RATIO", AOI)["WF측정률"]) == {1.0}
    assert capacity_stop(result.tables) is None


def test_the_preview_counts_routes_and_monthly_rates_for_the_merged_processes() -> None:
    result = merge_extra_processes(_seed(), _active())

    frame = process_rows_frame(result.tables, (BOND, AOI))
    lines = load_lines(result.tables, (BOND, AOI))

    assert set(frame["공정"]) == {BOND, AOI}
    assert frame["확보율"].gt(0).all()
    assert lines == {BOND: (24, 0), AOI: (20, 0)}


def test_a_zero_measurement_ratio_is_kept_zero_and_a_blank_becomes_one() -> None:
    files = edited(
        template_files(),
        "03_productivity.csv",
        lambda rows: set_cell(
            rows, lambda row: row[0] == BOND and row[7] == "202607", "WF측정률", "0"
        ),
    )

    result = merge_extra_processes(_seed(), _active(files))

    ratio = _rows(result.tables, "RQ_WF_RATIO", BOND)
    assert set(ratio.loc[ratio["생산계획년월"].ge(202607), "WF측정률"]) == {0.0}
    assert capacity_stop(result.tables) is None


def test_a_process_with_a_bdq_name_graduates_without_rows() -> None:
    files = template_files()
    for name in (
        "01_process.csv",
        "02_route.csv",
        "03_productivity.csv",
        "04_equipment_days.csv",
        "05_rate_vital.csv",
    ):
        files = edited(
            files,
            name,
            lambda rows: set_cell(rows, lambda row: row[0] == AOI, "공정", "demo_final_test"),
        )

    result = merge_extra_processes(_seed(), _active(files))

    outcomes = {item.process: item for item in result.report.outcomes}
    assert outcomes["demo_final_test"].outcome == OUTCOME_GRADUATED
    assert result.report.graduated and "1 BDQ 에 생김" in result.report.memo()
    assert _rows(result.tables, "RQ_REQB", "demo_final_test").empty
    assert len(result.tables["RQ_MODULE"]) == 4


def test_following_a_process_with_two_steps_folds_the_plan_variants_once() -> None:
    seed = _seed()
    chip = seed["RQ_REQB"].loc[seed["RQ_REQB"]["공정"].eq("DEMO_Chip_Attach")]
    seed["RQ_REQB"] = pd.concat(
        [seed["RQ_REQB"], chip.assign(STEP_SEQ="DEMO-P101")], ignore_index=True
    )

    result = merge_extra_processes(seed, _active(), check=_never_stops)

    assert len(_rows(result.tables, "RQ_REQB", BOND)) == 24


def test_a_missing_or_different_reference_drops_only_that_process() -> None:
    missing = edited(
        template_files(),
        "02_route.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == BOND, "참조공정", "DEMO_Nowhere"),
    )
    different = edited(
        template_files(),
        "02_route.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == BOND, "참조공정", "DEMO_Wafer_Inspect"),
    )

    for files in (missing, different):
        result = merge_extra_processes(_seed(), _active(files))
        outcomes = {item.process: item for item in result.report.outcomes}
        assert (outcomes[BOND].outcome, outcomes[BOND].rule) == (OUTCOME_DROPPED, RULE_REFERENCE)
        assert outcomes[AOI].outcome == OUTCOME_MERGED
        assert _rows(result.tables, "RQ_MODULE", BOND).empty
        assert result.report.flash_text() == "부대공정 1 합침 · 1 뺌"


def test_a_product_outside_the_plan_is_a_zero_line_and_all_zero_drops_the_process() -> None:
    partly = edited(
        template_files(),
        "02_route.csv",
        lambda rows: set_cell(
            rows, lambda row: "DEMO PRODUCT B" in row, "제품정보", "DEMO PRODUCT Z"
        ),
    )
    partly = edited(
        partly,
        "03_productivity.csv",
        lambda rows: set_cell(
            rows, lambda row: "DEMO PRODUCT B" in row, "제품정보", "DEMO PRODUCT Z"
        ),
    )
    result = merge_extra_processes(_seed(), _active(partly))
    aoi = {item.process: item for item in result.report.outcomes}[AOI]
    assert (aoi.outcome, aoi.zero_lines) == (OUTCOME_MERGED, 1)
    assert set(_rows(result.tables, "RQ_REQB", AOI)["제품정보"]) == {"DEMO PRODUCT A"}

    nowhere = partly
    for name in ("02_route.csv", "03_productivity.csv"):
        nowhere = edited(
            nowhere,
            name,
            lambda rows: set_cell(
                rows, lambda row: "DEMO PRODUCT A" in row, "제품정보", "DEMO PRODUCT Y"
            ),
        )
    dropped = merge_extra_processes(_seed(), _active(nowhere))
    aoi = {item.process: item for item in dropped.report.outcomes}[AOI]
    assert (aoi.outcome, aoi.rule, aoi.zero_lines) == (OUTCOME_DROPPED, RULE_PRODUCT, 2)


def _with_pkg_buffer_for_product_a(seed: Tables) -> Tables:
    """시드 `RQ_REQB` 에 PKG 공정 줄을 더한다 — 제품 A 는 Buffer, 제품 B 는 Base(Buffer 밖)."""
    chip = seed["RQ_REQB"].loc[seed["RQ_REQB"]["공정"].eq("DEMO_Chip_Attach")]
    pkg = chip.assign(공정="DEMO_Pack", 소요기준="PKG", STEP_SEQ="DEMO-P400")
    pkg.loc[pkg["제품정보"].eq("DEMO PRODUCT A"), "WF 구분"] = "BUFFER"
    tables = dict(seed)
    tables["RQ_REQB"] = pd.concat([seed["RQ_REQB"], pkg], ignore_index=True)
    return tables


def _aoi_as_pkg_buffer(files: Files) -> Files:
    files = edited(
        files,
        "01_process.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == AOI, "소요기준", "PKG"),
    )
    for name in ("02_route.csv", "03_productivity.csv"):
        files = edited(
            files, name, lambda rows: set_cell(rows, lambda row: row[0] == AOI, "WF 구분", "Buffer")
        )
    return files


def test_a_pkg_extra_process_only_hangs_on_products_with_a_buffer_route() -> None:
    tables = _with_pkg_buffer_for_product_a(_seed())

    result = merge_extra_processes(
        tables, _active(_aoi_as_pkg_buffer(template_files())), check=_never_stops
    )

    aoi = {item.process: item for item in result.report.outcomes}[AOI]
    assert (aoi.outcome, aoi.zero_lines) == (OUTCOME_MERGED, 1)
    rows = _rows(result.tables, "RQ_REQB", AOI)
    assert set(rows["제품정보"]) == {"DEMO PRODUCT A"}
    # WF 구분은 데이터 쪽 글자(`BUFFER`)로 맞춘다.
    assert set(rows["WF 구분"]) == {"BUFFER"}


def test_a_pkg_extra_process_without_any_buffer_product_is_dropped() -> None:
    result = merge_extra_processes(
        _seed(), _active(_aoi_as_pkg_buffer(template_files())), check=_never_stops
    )

    aoi = {item.process: item for item in result.report.outcomes}[AOI]
    assert (aoi.outcome, aoi.rule) == (OUTCOME_DROPPED, RULE_PRODUCT)


def test_following_a_pkg_process_counts_the_inherited_rows_outside_buffer() -> None:
    tables = _with_pkg_buffer_for_product_a(_seed())
    files = edited(
        template_files(),
        "01_process.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == BOND, "소요기준", "PKG"),
    )
    files = edited(
        files,
        "02_route.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == BOND, "참조공정", "DEMO_Pack"),
    )

    result = merge_extra_processes(tables, _active(files), check=_never_stops)

    bond = {item.process: item for item in result.report.outcomes}[BOND]
    assert bond.outcome == OUTCOME_MERGED
    # 제품 B 의 Base 줄 12달은 이어받아도 PKG 셈에 들지 않는다.
    assert bond.inherited_uncounted == 12


def test_the_same_path_written_twice_is_refused_by_r06() -> None:
    def add_specified_bond(rows: list[list[str]]) -> list[list[str]]:
        return [
            *rows,
            [BOND, "", "DEMO PRODUCT A", "8H", "Core", "DEMO-P150", "DEMO-1A", "202601", ""],
        ]

    files = edited(template_files(), "02_route.csv", add_specified_bond)

    result = merge_extra_processes(_seed(), _active(files))

    bond = {item.process: item for item in result.report.outcomes}[BOND]
    assert (bond.outcome, bond.rule) == (OUTCOME_DROPPED, RULE_DUPLICATE)


def test_months_are_cut_to_the_plan_axis() -> None:
    seed = _seed()
    plan = seed["RQ_PKG_PLAN"]
    seed["RQ_PKG_PLAN"] = plan.loc[plan["생산계획년월"].between(202605, 202608)].reset_index(
        drop=True
    )

    result = merge_extra_processes(seed, _active(), check=_never_stops)

    months = set(_rows(result.tables, "RQ_REQB", BOND)["생산계획년월"].astype(int))
    assert months == {202605, 202606, 202607, 202608}
    assert set(_rows(result.tables, "RQ_EQP_OWN", BOND)["생산계획년월"].astype(int)) == months


def _stops_when(*processes: str) -> CapacityCheck:
    def check(tables: Mapping[str, pd.DataFrame]) -> str | None:
        present = set(tables["RQ_REQB"]["공정"].astype(str))
        return "멈춤(가짜)" if set(processes) <= present else None

    return check


def test_r07_drops_only_the_process_that_stops_the_calculation() -> None:
    result = merge_extra_processes(_seed(), _active(), check=_stops_when(BOND))

    outcomes = {item.process: item for item in result.report.outcomes}
    assert (outcomes[BOND].outcome, outcomes[BOND].rule) == (OUTCOME_DROPPED, RULE_STOP)
    assert outcomes[AOI].outcome == OUTCOME_MERGED
    assert _rows(result.tables, "RQ_REQB", BOND).empty
    assert not _rows(result.tables, "RQ_REQB", AOI).empty


def test_r07_drops_the_later_one_when_two_processes_only_stop_together() -> None:
    result = merge_extra_processes(_seed(), _active(), check=_stops_when(BOND, AOI))

    outcomes = {item.process: item for item in result.report.outcomes}
    assert outcomes[BOND].outcome == OUTCOME_MERGED
    assert (outcomes[AOI].outcome, outcomes[AOI].rule) == (OUTCOME_DROPPED, RULE_STOP)


def test_r07_leaves_the_extras_when_bdq_alone_already_stops() -> None:
    result = merge_extra_processes(_seed(), _active(), check=_stops_when("DEMO_Chip_Attach"))

    assert result.report.base_stop == "멈춤(가짜)"
    assert [item.outcome for item in result.report.outcomes] == [OUTCOME_MERGED, OUTCOME_MERGED]


def test_without_an_active_pack_the_tables_are_untouched() -> None:
    seed = _seed()

    result = merge_extra_processes(seed, None)

    assert result.report.memo() == "" and result.report.outcomes == ()
    for name, frame in seed.items():
        pd.testing.assert_frame_equal(result.tables[name], frame)


def test_strip_removes_every_row_of_the_named_processes() -> None:
    merged = merge_extra_processes(_seed(), _active()).tables
    # 사람이 리비전에서 STEP 을 더한 줄도 이름으로 걷힌다.
    extra = _rows(merged, "RQ_REQB", BOND).assign(STEP_SEQ="DEMO-P151")
    merged["RQ_REQB"] = pd.concat([merged["RQ_REQB"], extra], ignore_index=True)

    stripped = strip_extra_processes(merged, (BOND, AOI))

    for name in PROCESS_TABLES:
        assert not stripped[name]["공정"].isin([BOND, AOI]).any(), name
    seed = _seed()
    for name in PROCESS_TABLES:
        assert len(stripped[name]) == len(seed[name]), name


@pytest.mark.parametrize("version_no", [1, 7])
def test_the_report_memo_names_the_version(version_no: int) -> None:
    result = merge_extra_processes(_seed(), _active(version_no=version_no), check=_never_stops)

    assert result.report.memo().startswith(f"부대공정 판 {version_no} · ")
