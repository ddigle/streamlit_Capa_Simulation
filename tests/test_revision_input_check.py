# Purpose: 입력 점검의 묶음 수 · 멈춤 판정 · 원천 행 · 캐시 길이 저장 · 지정 검사와 맞는지 검증한다.

"""**점검이 말하는 수는 검사가 경고하는 수와 같아야 한다.**

시나리오 관리 › 목록 관리 「점검」 은 저장 · 지정 검사(`capacity_gate`)가 한 줄로 경고하는
「소요대수에 들지 않은 수요」 를 묶음으로 펼친다. 두 자리의 수가 갈라지면 어느 쪽도 믿을 수
없다 — 그래서 빠짐을 만든 편집(내장 합성 시드)으로 묶음 수를 `required_exclusion_counts` 와,
멈춤을 공식 발행 검사와, 등록 때 뺀 원천 행 수를 등록 파생(`derive_q_core_data`)과 맞댄다. 표본
고유 수는 못 박지 않는다 — 0 보다 큰지 먼저 보고 두 셈이 같은지를 본다.
"""

from __future__ import annotations

import ast
import pickle
import random
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

import capa_simulation.components.capacity_gate as capacity_gate
import capa_simulation.persistence.cache as scenario_cache
import capa_simulation.services.revision_input_check as revision_input_check
from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.components.capacity_gate import (
    INPUT_CHECK_PERIOD_TABLES,
    density_error,
    input_check_verdict,
    official_publish_verdict,
)
from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset
from capa_simulation.persistence.repository import (
    REVISION_TABLES,
    SOURCE_BLANK_TEXT_PATTERN,
    DuckDBScenarioRepository,
)
from capa_simulation.services.builtin_seed import (
    BUILTIN_SEED_MONTHS,
    build_builtin_seed_dataset,
    builtin_seed_processes,
)
from capa_simulation.services.core_data_derivation import derive_q_core_data
from capa_simulation.services.load_calculator import PLAN_QUANTITY_BLANK_REASON
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.required_equipment import (
    PKG_UNCOUNTED_REASON,
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    UNROUTED_LOADS_ATTR,
    UNROUTED_UNUSED_REASON,
    required_exclusion_counts,
)
from capa_simulation.services.revision_input_check import (
    GROUP_ASSUMED,
    GROUP_CAPACITY,
    GROUP_PLANS,
    GROUP_ROUTES,
    GROUP_RULES,
    GROUP_SOURCE,
    GROUP_STOP,
    GROUP_UNCOUNTED,
    GROUP_UNROUTED,
    RevisionInputCheck,
    blocked_input_check,
    build_input_check,
    calculation_period,
    reason_label,
)
from capa_simulation.services.simulation_cache import CapacityOutcome, full_capacity_outcome
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
    RUN_RATE_EXCLUSION_REASON,
    capacity_assumptions,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
Tables = dict[str, pd.DataFrame]


@pytest.fixture(scope="module")
def tables() -> Tables:
    return dict(build_builtin_seed_dataset().reference_tables)


def _months(frame: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(frame["생산계획년월"])


def _with_every_exclusion(tables: Tables) -> Tables:
    """확인 필요 다섯 묶음이 모두 서는 편집 — 계산은 멈추지 않는다.

    한 제품 첫 달의 수율 행을 빼고(부하량에서 빠진 계획) 둘째 달 생산수량을 비우고(빈 생산수량),
    다른 제품 첫 달의 Capa Code 를 경로 밖으로(경로에 닿지 않은 부하), 마지막 공정의 UPEH 를
    빼고(대당 Capa 가 없어 뺀 경로), 첫 공정 마지막 달의 효율을 0 으로(대당 Capa 에서 뺀 기준), 둘째
    공정 마지막 달의 Lot 측정률 행을 뺀다(측정률 1.0 가정).
    """
    edited = {name: frame.copy() for name, frame in tables.items()}
    plan = edited["RQ_PKG_PLAN"]
    months = sorted(_months(plan).unique())
    products = sorted(plan["제품정보"].unique())
    first, last = products[0], products[-1]
    processes = list(dict.fromkeys(edited["RQ_UPEH"]["공정"]))

    yields = edited["RQ_YLD"]
    edited["RQ_YLD"] = yields.loc[
        ~(yields["제품정보"].eq(first) & _months(yields).eq(months[0]))
    ].reset_index(drop=True)
    plan["생산수량"] = plan["생산수량"].astype("float64")
    plan.loc[plan["제품정보"].eq(first) & _months(plan).eq(months[1]), "생산수량"] = float("nan")
    plan.loc[plan["제품정보"].eq(last) & _months(plan).eq(months[0]), "Capa Code"] = "DEMO_NO_ROUTE"

    upeh = edited["RQ_UPEH"]
    edited["RQ_UPEH"] = upeh.loc[upeh["공정"].ne(processes[-1])].reset_index(drop=True)
    run_rate = edited["RQ_RUN_RATE"]
    zero = run_rate["공정"].eq(processes[0]) & _months(run_rate).eq(months[-1])
    run_rate.loc[zero, "CAPA_RUN_RATE"] = 0.0
    lot = edited["RQ_LOT_RATIO"]
    edited["RQ_LOT_RATIO"] = lot.loc[
        ~(lot["공정"].eq(processes[1]) & _months(lot).eq(months[-1]))
    ].reset_index(drop=True)
    return edited


def _pkg_route_on_one_product(tables: Tables) -> Tables:
    """한 제품의 한 공정 경로를 소요기준 PKG · WF 구분 Core 로 — Buffer 밖이라 규칙대로 세지 않는
    경로와, 그 제품에 PKG Buffer 경로가 없어 쓰지 않는 조합이 함께 선다."""
    reqb = tables["RQ_REQB"].copy()
    upeh = tables["RQ_UPEH"].copy()
    product = reqb["제품정보"].iloc[0]
    process = reqb["공정"].iloc[-1]
    for frame in (reqb, upeh):
        rows = frame["제품정보"].eq(product) & frame["공정"].eq(process)
        frame.loc[rows, ["소요기준", "WF 구분"]] = ["PKG", "Core"]
    return {**tables, "RQ_REQB": reqb, "RQ_UPEH": upeh}


def _vital_blank(tables: Tables) -> Tables:
    """여유율 두 행을 비운다 — 대당 Capa 가 기준정보 연결 오류(`ReferenceJoinError`)로 멈춘다."""
    vital = tables["RQ_VITAL"].copy()
    vital["편중률"] = vital["편중률"].astype("object")
    vital.loc[vital.index[:2], "편중률"] = None
    return {**tables, "RQ_VITAL": vital}


def _main_upeh_blank(tables: Tables) -> Tables:
    """계산 대상 Main 행 하나의 UPEH 를 비운다 — 경로의 바탕 표(`RQ_UPEH`) 자체의 값 칸 멈춤."""
    upeh = tables["RQ_UPEH"].copy()
    upeh["UPEH"] = upeh["UPEH"].astype("float64")
    main = upeh["Area_Name"].eq("Main") & upeh["소요기준"].isin(["CHIP", "WF", "PKG"])
    upeh.loc[upeh.index[main.to_numpy().nonzero()[0][0]], "UPEH"] = float("nan")
    return {**tables, "RQ_UPEH": upeh}


def _vital_zero(tables: Tables) -> Tables:
    """여유율 한 행을 0 으로 — 연결은 되고 값 검사(`0보다 커야`)에서 멈춘다(연결 꼴 없음)."""
    vital = tables["RQ_VITAL"].copy()
    vital.loc[vital.index[0], "편중률"] = 0.0
    return {**tables, "RQ_VITAL": vital}


def _run_rate_month_missing(tables: Tables) -> Tables:
    run_rate = tables["RQ_RUN_RATE"]
    months = _months(run_rate)
    return {**tables, "RQ_RUN_RATE": run_rate.loc[months.ne(months.max())].reset_index(drop=True)}


def _density_broken(tables: Tables) -> Tables:
    """계획이 있는 제품의 `구분_EQ` 를 0 으로 — 대당 Capa · 소요대수는 지나고 Density 만 멈춘다."""
    plan = tables["RQ_PKG_PLAN"]
    planned = plan.loc[pd.to_numeric(plan["생산수량"]).gt(0)].iloc[0]
    chip_eq = tables["RQ_CHIP_EQ"].copy()
    target = chip_eq["제품정보"].eq(planned["제품정보"]) & chip_eq["Stack"].eq(planned["Stack"])
    chip_eq.loc[target, "구분_EQ"] = 0.0
    return {**tables, "RQ_CHIP_EQ": chip_eq}


def _check(tables: Tables, blank_cs: pd.DataFrame | None = None) -> RevisionInputCheck:
    """`input_check_verdict` 의 계산 몸통과 같은 차례 — DB · 캐시 없이."""
    outcome = full_capacity_outcome(tables, tables)
    density = density_error(tables) if outcome.error is None else None
    period = calculation_period(tables, INPUT_CHECK_PERIOD_TABLES)
    return build_input_check(outcome, density, blank_cs, period=period)


# ------------------------------------------------------------------ 검사와 같은 수


def test_the_four_demand_counts_are_the_gate_counts(tables: Tables) -> None:
    """부하량에서 빠진 계획 · 빈 생산수량 · 경로에 닿지 않은 부하 · 부하 붙은 경로 — 검사 경고의 네
    수가 점검 묶음에서 그대로 나온다(경로 묶음 부제 == 검사의 `excluded_routes`)."""
    edited = _with_every_exclusion(tables)
    outcome = full_capacity_outcome(edited, edited)
    assert outcome.error is None and outcome.required_equipment is not None
    counts = required_exclusion_counts(outcome.required_equipment)
    assert min(counts) > 0, counts

    check = _check(edited)

    plans = check.group(GROUP_PLANS)
    unrouted = check.group(GROUP_UNROUTED)
    routes = check.group(GROUP_ROUTES)
    assert plans is not None and unrouted is not None and routes is not None
    assert plans.count == counts.excluded_plans + counts.blank_plans
    assert dict(plans.reasons)[PLAN_QUANTITY_BLANK_REASON] == counts.blank_plans
    assert unrouted.count == counts.unrouted_loads
    assert routes.subtitle == f"그 가운데 부하가 붙은 경로 {counts.excluded_routes:,}"
    assert routes.count is not None and routes.count >= counts.excluded_routes


def test_every_check_group_is_counted_and_the_calculation_says_how_many(tables: Tables) -> None:
    """확인 필요 다섯이 모두 서면 「됨 · 확인 5」. 대당 Capa 제외 · 측정률 가정도 결과와 같은
    수다."""
    edited = _with_every_exclusion(tables)
    outcome = full_capacity_outcome(edited, edited)
    assert outcome.unit_capacity is not None
    exclusions = outcome.unit_capacity.attrs[CAPACITY_EXCLUSIONS_ATTR]
    assumed = capacity_assumptions(outcome.unit_capacity)

    check = _check(edited)

    capacity = check.group(GROUP_CAPACITY)
    assumption = check.group(GROUP_ASSUMED)
    assert capacity is not None and assumption is not None
    assert capacity.count == len(exclusions) > 0
    assert reason_label(RUN_RATE_EXCLUSION_REASON) in capacity.subtitle
    assert assumption.count == sum(assumed.counts.values()) > 0
    assert not check.stopped
    flagged = [group.key for group in check.groups if group.flagged]
    assert flagged == [GROUP_CAPACITY, GROUP_ROUTES, GROUP_PLANS, GROUP_UNROUTED, GROUP_ASSUMED]
    assert check.calculation_label == "됨 · 확인 5"
    assert check.period == (min(BUILTIN_SEED_MONTHS), max(BUILTIN_SEED_MONTHS))
    assert check.period_label.count("–") == 1


def test_an_untouched_seed_is_calculated_without_a_check(tables: Tables) -> None:
    check = _check(tables)

    assert check.calculation_label == "됨"
    stop = check.group(GROUP_STOP)
    assert stop is not None and stop.count == 0 and stop.count_text == "없음"


def test_rule_rows_are_kept_apart_and_the_groups_split_the_result_lists(tables: Tables) -> None:
    """규칙대로 뺀 것(PKG Buffer 밖 · 쓰지 않는 경로 조합)은 검사가 세지 않는 행이라 확인 묶음에
    섞이지 않는다 — 확인 묶음과 규칙 묶음을 합치면 결과의 제외 목록 둘과 같다."""
    edited = _pkg_route_on_one_product(tables)
    outcome = full_capacity_outcome(edited, edited)
    assert outcome.required_equipment is not None
    all_routes = outcome.required_equipment.attrs[REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR]
    all_unrouted = outcome.required_equipment.attrs[UNROUTED_LOADS_ATTR]

    check = _check(edited)

    rules = check.group(GROUP_RULES)
    routes = check.group(GROUP_ROUTES)
    unrouted = check.group(GROUP_UNROUTED)
    assert rules is not None and routes is not None and unrouted is not None
    pkg, unused = rules.tables
    assert len(pkg.frame) > 0 and len(unused.frame) > 0
    assert set(pkg.frame["제외사유"]) == {PKG_UNCOUNTED_REASON}
    assert set(unused.frame["제외사유"]) == {UNROUTED_UNUSED_REASON}
    assert rules.count == len(pkg.frame) + len(unused.frame)
    assert routes.count == len(all_routes) - len(pkg.frame)
    assert unrouted.count == len(all_unrouted) - len(unused.frame)
    assert not rules.flagged


# ------------------------------------------------------------------ 멈춤


def test_a_reference_join_stop_keeps_its_route_count_and_folds_the_rest(tables: Tables) -> None:
    """기준정보 연결 오류로 멈추면 그 꼴과 수(`problem`)가 결과에 남고 뒤 묶음은 「셀 수 없음」
    하나다."""
    edited = _vital_blank(tables)
    outcome = full_capacity_outcome(edited, edited)
    assert outcome.error is not None
    assert outcome.problem is not None and outcome.problem.rows > 0

    check = _check(edited)

    assert check.stopped and check.calculation_label == "멈춤"
    assert check.stop is not None and check.stop.problem == outcome.problem
    assert [group.key for group in check.groups] == [GROUP_STOP, GROUP_UNCOUNTED, GROUP_SOURCE]
    stop = check.group(GROUP_STOP)
    uncounted = check.group(GROUP_UNCOUNTED)
    assert stop is not None and stop.title == "계산 멈춤 — 대당 Capa"
    assert stop.subtitle == outcome.error
    assert uncounted is not None and uncounted.count_text == "셀 수 없음"


def test_an_upeh_table_stop_names_its_stage_and_keeps_its_route_count(tables: Tables) -> None:
    """경로의 바탕 표(`RQ_UPEH`) 자체의 멈춤도 꼴과 수를 들어 제목이 「계산 멈춤 — 대당 Capa」 다
    (사내 리뷰 202611111500 발견 3)."""
    edited = _main_upeh_blank(tables)
    outcome = full_capacity_outcome(edited, edited)
    assert outcome.problem is not None
    assert (outcome.problem.table, outcome.problem.label) == ("RQ_UPEH", "빈 값(UPEH)")
    assert outcome.problem.rows == 1

    check = _check(edited)

    stop = check.group(GROUP_STOP)
    assert check.stop is not None and check.stop.problem == outcome.problem
    assert stop is not None and stop.title == "계산 멈춤 — 대당 Capa"
    assert stop.subtitle == outcome.error


def test_a_stop_without_a_join_problem_does_not_name_a_stage(tables: Tables) -> None:
    """결과가 어느 단계의 오류인지 말하지 않으면 단계를 지어 붙이지 않는다."""
    edited = _vital_zero(tables)
    outcome = full_capacity_outcome(edited, edited)
    assert outcome.error is not None and outcome.problem is None

    check = _check(edited)

    stop = check.group(GROUP_STOP)
    assert check.stopped and stop is not None
    assert stop.title == "계산 멈춤"
    assert stop.subtitle == outcome.error


@pytest.mark.parametrize("keeps_counts", [False, True], ids=["folded", "counted"])
def test_a_density_stop_is_a_stop_and_the_switch_decides_the_groups(
    tables: Tables, monkeypatch: pytest.MonkeyPatch, keeps_counts: bool
) -> None:
    """Density 만 멈춰도 「멈춤」 이다. 스위치가 켜지면(지금 — 검토 보드 F1 (나)) 뒤 묶음을 세고,
    끄면 접는다(셀 수 없음) — 대당 Capa · 소요대수는 끝났다."""
    monkeypatch.setattr(revision_input_check, "DENSITY_STOP_KEEPS_COUNTS", keeps_counts)
    edited = _density_broken(tables)

    check = _check(edited)

    assert check.stopped and check.calculation_label == "멈춤"
    assert check.stop is not None and check.stop.kind == "density"
    stop = check.group(GROUP_STOP)
    assert stop is not None and stop.title == "계산 멈춤 — Density 환산"
    assert (check.group(GROUP_CAPACITY) is not None) is keeps_counts
    assert (check.group(GROUP_UNCOUNTED) is None) is keeps_counts
    assert check.group(GROUP_SOURCE) is not None


def test_an_old_revision_without_route_keys_stops_without_calculating(
    tables: Tables, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """경로 키가 없는 옛 리비전은 그 까닭으로 멈추고 계산을 부르지 않는다(결정 23)."""
    database, scenario_id, revision_id = _seeded(tmp_path)
    monkeypatch.setattr(capacity_gate, "revision_block_reason", lambda _tables: "옛 리비전")

    def no_calculation(*_args: object) -> CapacityOutcome:
        raise AssertionError("계산을 부르면 안 된다")

    monkeypatch.setattr(capacity_gate, "full_capacity_outcome", no_calculation)

    check = input_check_verdict(str(database), scenario_id, revision_id)

    assert check.stopped and check.stop is not None and check.stop.kind == "blocked"
    stop = check.group(GROUP_STOP)
    assert stop is not None and stop.subtitle == "옛 리비전"
    assert blocked_input_check("옛 리비전", None).calculation_label == "멈춤"


def test_the_period_covers_every_month_the_calculation_read(tables: Tables) -> None:
    """칸 머리 「전체 기간」 은 계산이 본 달 전체다 — 기준정보 달이 계획보다 넓으면 그 달까지 넓혀
    묶음 행의 달이 모두 기간 안이다(2026-11-11 검토 보드 F5 (가)). 계획 끝 달을 지우고 그 달
    효율을 0 으로 둔 리비전은 계획만 보면 끝 달이 빠지는데 뺀 기준 행은 그 끝 달이다."""
    edited = {name: frame.copy() for name, frame in tables.items()}
    plan = edited["RQ_PKG_PLAN"]
    last = int(_months(plan).max())
    edited["RQ_PKG_PLAN"] = plan.loc[_months(plan).ne(last)].reset_index(drop=True)
    run_rate = edited["RQ_RUN_RATE"]
    run_rate.loc[_months(run_rate).eq(last), "CAPA_RUN_RATE"] = 0.0
    plan_months = _months(edited["RQ_PKG_PLAN"])
    assert int(plan_months.max()) < last

    check = _check(edited)

    assert check.period == (int(plan_months.min()), last)
    start, end = check.period
    assert check.period_label == f"{month_label(start)}–{month_label(end)}"
    capacity = check.group(GROUP_CAPACITY)
    assert capacity is not None and capacity.count
    assert _months(capacity.tables[0].frame).eq(last).any()
    for group in check.groups:
        for table in group.tables:
            frame = table.frame
            if group.key == GROUP_SOURCE or frame.empty or "생산계획년월" not in frame.columns:
                continue
            assert _months(frame).between(start, end).all(), (group.key, table.title)


def test_the_period_skips_monthless_tables_and_says_nothing_without_months() -> None:
    """달 칸이 없는 표 · 없는 표는 건너뛰고, 어느 표에도 달이 없으면 기간이 없다."""
    monthless = pd.DataFrame({"제품정보": ["DEMO_A"]})
    plan = pd.DataFrame({"생산계획년월": [202602, 202603]})
    upeh = pd.DataFrame({"생산계획년월": [202601, 202604]})

    assert calculation_period({"RQ_MODULE": monthless}, ["RQ_MODULE", "RQ_UPEH"]) is None
    assert calculation_period(
        {"RQ_PKG_PLAN": plan, "RQ_UPEH": upeh, "RQ_MODULE": monthless},
        ["RQ_PKG_PLAN", "RQ_UPEH", "RQ_MODULE"],
    ) == (202601, 202604)
    assert "RQ_PKG_PLAN" in INPUT_CHECK_PERIOD_TABLES
    assert not {"RQ_MODULE", "RQ_CHIP_QTY"} & set(INPUT_CHECK_PERIOD_TABLES)


# ------------------------------------------------------------------ DB · 캐시 길


def _seeded(tmp_path: Path) -> tuple[Path, str, str]:
    database = tmp_path / "check.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    release = ensure_initial_scenario(repository).release
    assert release is not None
    snapshot = repository.load_revision(release.revision_id)
    return database, snapshot.scenario.scenario_id, release.revision_id


def _saved(database: Path, scenario_id: str, base_revision: str, edit: object, name: str) -> str:
    assert callable(edit)
    repository = DuckDBScenarioRepository(database)
    snapshot = repository.load_revision(base_revision)
    saved = repository.save_revision(
        scenario_id,
        edit({name: snapshot.tables[name] for name in REVISION_TABLES}),
        snapshot.preset,
        revision_name=name,
        parent_revision_id=base_revision,
    )
    return saved.revision.revision_id


def test_the_stop_verdict_is_the_publish_verdict_density_included(tmp_path: Path) -> None:
    """점검의 「멈춤」 은 공식 발행 검사가 막는 리비전과 같다 — Density 만 멈춘 리비전도
    멈춤이다."""
    database, scenario_id, base = _seeded(tmp_path)
    revisions = {
        "그대로": base,
        "빠짐": _saved(database, scenario_id, base, _with_every_exclusion, "빠짐"),
        "가동률 한 달 누락": _saved(
            database, scenario_id, base, _run_rate_month_missing, "가동률 한 달 누락"
        ),
        "여유율 빈 칸": _saved(database, scenario_id, base, _vital_blank, "여유율 빈 칸"),
        "구분_EQ 0": _saved(database, scenario_id, base, _density_broken, "구분_EQ 0"),
    }

    verdicts = {
        name: (
            input_check_verdict(str(database), scenario_id, revision_id).stopped,
            not official_publish_verdict(str(database), revision_id).allowed,
        )
        for name, revision_id in revisions.items()
    }

    assert all(check == publish for check, publish in verdicts.values()), verdicts
    assert [name for name, (stopped, _) in verdicts.items() if stopped] == [
        "가동률 한 달 누락",
        "여유율 빈 칸",
        "구분_EQ 0",
    ]
    # Density 만 멈춘 리비전은 멈춤 줄은 두고 뒤 묶음도 센다(2026-11-11 검토 보드 F1 (나)) —
    # 스위치를 바꾸지 않은 출하 기본값 그대로의 길이다.
    density = input_check_verdict(str(database), scenario_id, revisions["구분_EQ 0"])
    assert density.stop is not None and density.stop.kind == "density"
    assert density.group(GROUP_CAPACITY) is not None and density.group(GROUP_UNCOUNTED) is None
    assert density.calculation_label == "멈춤"


def test_the_check_keeps_only_its_summary_slot_and_reads_the_rest_uncached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """고른 리비전마다 부르는 점검은 요약 칸 하나만 쓴다 — 계산 페이지 · 저장 검사의 공유 칸(전체
    기간 결과 4칸 · 표시순서를 얹은 스냅샷 4칸)도, 표시순서 없는 스냅샷 피클 칸도 쓰지 않고
    저장소에서 캐시 없이 읽는다. 다시 부르면 요약 칸에서 나와 DB 도 읽지 않는다(결정 18 —
    2026-11-11 검토 보드 F6 (나))."""
    database, scenario_id, revision_id = _seeded(tmp_path)

    def shared_slot(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("요약 칸 밖의 캐시를 쓰면 안 된다")

    reads: list[str] = []
    load_revision = DuckDBScenarioRepository.load_revision
    load_blank = DuckDBScenarioRepository.load_source_blank_cs_rows

    def counted_revision(self: DuckDBScenarioRepository, revision: str, **kwargs: bool) -> object:
        assert kwargs == {"apply_global_display_order": False}
        reads.append("revision")
        return load_revision(self, revision, **kwargs)

    def counted_blank(self: DuckDBScenarioRepository, scenario: str) -> object:
        reads.append("source")
        return load_blank(self, scenario)

    monkeypatch.setattr(capacity_gate, "get_full_capacity_outcome", shared_slot)
    monkeypatch.setattr(capacity_gate, "load_scenario_snapshot", shared_slot)
    monkeypatch.setattr(scenario_cache, "_load_scenario_snapshot_resource", shared_slot)
    monkeypatch.setattr(scenario_cache, "_load_stored_order_snapshot_payload", shared_slot)
    monkeypatch.setattr(DuckDBScenarioRepository, "load_revision", counted_revision)
    monkeypatch.setattr(DuckDBScenarioRepository, "load_source_blank_cs_rows", counted_blank)

    first = input_check_verdict(str(database), scenario_id, revision_id)
    assert reads == ["revision", "source"]
    again = input_check_verdict(str(database), scenario_id, revision_id)

    assert reads == ["revision", "source"]
    assert first.calculation_label == again.calculation_label == "됨"
    assert not hasattr(scenario_cache, "load_source_blank_cs_rows")


def test_a_read_failure_is_raised_every_time_instead_of_being_kept(tmp_path: Path) -> None:
    """없는 리비전 · 지운 시나리오처럼 읽지 못하면 부를 때마다 화면이 받는
    예외(`BOOTSTRAP_ERRORS`)로 올라온다 — 실패가 요약 칸에 남으면 다음 회차가 옛 실패를 보거나
    고친 뒤에도 그대로다(결정 22)."""
    from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS

    database, scenario_id, _ = _seeded(tmp_path)
    missing = "00000000-0000-4000-8000-000000000000"

    for _attempt in range(2):
        with pytest.raises(BOOTSTRAP_ERRORS):
            input_check_verdict(str(database), scenario_id, missing)


def test_the_check_and_its_outcome_survive_the_cache_pickle(tables: Tables) -> None:
    """요약 칸은 `st.cache_data` 라 피클로 오간다 — 멈춤의 꼴(`problem`)도 실린다."""
    edited = _vital_blank(tables)
    outcome = full_capacity_outcome(edited, edited)
    assert outcome.problem is not None

    restored = pickle.loads(pickle.dumps(outcome))
    check = pickle.loads(pickle.dumps(_check(_with_every_exclusion(tables))))

    assert restored.problem == outcome.problem
    assert restored.error == outcome.error
    assert check.calculation_label == "됨 · 확인 5"
    capacity = check.group(GROUP_CAPACITY)
    assert capacity is not None and not capacity.tables[0].frame.empty


# ------------------------------------------------------------------ 등록 때 뺀 원천 행


# 파생이 지우는 공백 꼴 — 빈 글자 · 반각 · 탭 · 전각 공백 · NBSP · 줄 구분.
_BLANKS = (None, "", "  ", "\t", "\u3000", "\xa0 ", "\u2028")


def _blank_cs_source() -> pd.DataFrame:
    """내장 시드 원천에서 계획 행 둘과 경로 행 여럿의 CS 를 여러 꼴의 빈 값으로 — 공백이 아닌 글자는
    남긴다(` MP` 처럼 앞에 공백이 있는 값은 빈 값이 아니다). 계획 표시 하나는 ` y ` 로 적는다."""
    source = build_builtin_seed_dataset().source_data.copy()
    source["CS"] = source["CS"].astype("object")
    source["계획기초정보여부"] = source["계획기초정보여부"].astype("object")
    plans = source.index[source["계획기초정보여부"].eq("Y")]
    routes = source.index[source["계획기초정보여부"].ne("Y")]
    targets = [*plans[:2], *routes[: len(_BLANKS) - 2]]
    for row, value in zip(targets, _BLANKS, strict=True):
        source.loc[row, "CS"] = value
    source.loc[plans[0], "계획기초정보여부"] = " y "
    source.loc[routes[-1], "CS"] = " MP"
    return source


def _scenario_with_source(
    repository: DuckDBScenarioRepository, source: pd.DataFrame | None, name: str
) -> tuple[str, str]:
    """(시나리오 id, 초기 리비전 id)."""
    prepared = build_builtin_seed_dataset()
    snapshot = repository.create_scenario(
        ScenarioCreate(
            scenario_name=name,
            source_simulation_code=f"DEMO-CHECK-{random.randrange(10**9)}",
            source_simulation_name="입력 점검 합성 원천",
            source_type="TEST",
            pipeline_version="test-v1",
        ),
        prepared.reference_tables,
        ScenarioPreset(
            min(BUILTIN_SEED_MONTHS), max(BUILTIN_SEED_MONTHS), builtin_seed_processes()
        ),
        source_data=source,
    )
    return snapshot.scenario.scenario_id, snapshot.revision.revision_id


def test_the_registration_drop_is_read_back_as_the_derivation_counted_it(tmp_path: Path) -> None:
    """등록 때 뺀 원천 행을 원천에서 다시 읽은 수가 등록 파생의 `blank_cs` 와 같다 — 공백 꼴이
    여럿이어도(파이썬 `strip` 과 DuckDB 의 공백 집합 차이)."""
    database = tmp_path / "source.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    scenario_id, revision_id = _scenario_with_source(
        repository, _blank_cs_source(), "원천 있는 시나리오"
    )
    derived = derive_q_core_data(repository.load_source_data(scenario_id)).blank_cs
    assert derived.rows > 0 and derived.plan_rows > 0 and derived.route_rows > 0

    rows = repository.load_source_blank_cs_rows(scenario_id)

    assert rows is not None
    assert len(rows) == derived.rows
    assert list(rows.columns) == list(repository.load_source_data(scenario_id).columns)
    check = input_check_verdict(str(database), scenario_id, revision_id)
    source = check.group(GROUP_SOURCE)
    assert source is not None and source.count == derived.rows
    assert source.subtitle == (
        f"CS 빈 칸 — 계획 {derived.plan_rows:,} · 경로 {derived.route_rows:,}"
    )
    assert not source.flagged


def test_a_scenario_without_a_source_says_dash_instead_of_zero(tmp_path: Path) -> None:
    """복제 · 머지 · Shift 처럼 원천이 없는 시나리오는 셀 원천이 없다 — 「없음」(0)이 아니라
    「—」."""
    database = tmp_path / "nosource.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    scenario_id, revision_id = _scenario_with_source(repository, None, "원천 없는 시나리오")

    assert repository.load_source_blank_cs_rows(scenario_id) is None
    source = input_check_verdict(str(database), scenario_id, revision_id).group(GROUP_SOURCE)
    assert source is not None and source.count is None and source.count_text == "—"


def test_the_sql_blank_pattern_matches_every_character_python_strips() -> None:
    """원천 SQL 이 고르는 공백(`SOURCE_BLANK_TEXT_PATTERN`)은 파이썬 `str.strip` 이 지우는 모든
    글자를 받는다 — 하나라도 빠지면 등록 때 뺀 행을 덜 읽는다. 공백이 아닌 글자는 받지 않는다."""
    spaces = [chr(code) for code in range(sys.maxunicode + 1) if chr(code).isspace()]
    connection = duckdb.connect()

    def blank(text: str) -> bool:
        row = connection.execute(
            "SELECT regexp_full_match(?, ?)", [text, SOURCE_BLANK_TEXT_PATTERN]
        ).fetchone()
        assert row is not None
        return bool(row[0])

    try:
        missed = [hex(ord(space)) for space in spaces if not blank(space * 2)]
        taken = [text for text in (" MP", "\u200b", "0", "_") if blank(text)]
    finally:
        connection.close()

    assert not missed and not taken


# ------------------------------------------------------------------ 구조 그물


def test_the_input_check_verdict_is_inside_the_density_net() -> None:
    """점검 판정은 `capacity_gate` 의 공개 `*_verdict` 라 Density 그물
    (`tests/test_gate_density_coverage.py`)이 그 길을 본다."""
    tree = ast.parse(
        (PROJECT_ROOT / "src/capa_simulation/components/capacity_gate.py").read_text(
            encoding="utf-8"
        )
    )
    names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert "input_check_verdict" in names
