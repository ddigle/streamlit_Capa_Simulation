# Purpose: 원천 등록이 저장 전 대당 Capa 를 돌려 보고 멈춰도 저장하며 알리는지 검증한다.

"""원천 등록 때 대당 Capa 미리 보기(2026-11-01 사용자 결정 A1 — 「알리기만」).

사내 S27 은 BigDataQuery 로 등록됐고 저장은 됐는데, 계산할 때 처음 멈췄다(사내 리뷰 202610271800
발견 1). 등록하는 사람이 바로 알게 저장 전에 대당 Capa 를 한 번 계산한다. 막지 않는다 — 기준 정보
편집에서 그 칸을 채워 새 리비전으로 저장하면 서는 꼴이 많고, 막으면 원천을 다시 받아야만 풀린다.
화면 등록과 공식버전 자동 갱신이 같은 길(`scenario_registration.save_bigdataquery_scenario`)을
지난다.

원천은 내장 합성 시드(`DEMO_*` — `services/builtin_seed.py` 의 리터럴)다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.io.core_data_source import CoreDataBatch
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import full_data_scenario_preset
from capa_simulation.scenario_registration import (
    RegistrationCapacityCheck,
    check_registration_capacity,
    save_bigdataquery_scenario,
)
from capa_simulation.services.builtin_seed import (
    build_builtin_seed_dataset,
    load_builtin_display_order,
)
from capa_simulation.services.core_data_pipeline import (
    PreparedCoreDataset,
    prepare_core_data_dataset,
)
from capa_simulation.services.unit_capacity import (
    JOIN_BLANK_VALUE,
    JOIN_DUPLICATE_KEY,
    ReferenceJoinProblem,
)

SEED = build_builtin_seed_dataset()
DISPLAY_ORDER = load_builtin_display_order()
PROCESS = "DEMO_Wafer_Inspect"


def _prepared(frame: pd.DataFrame) -> PreparedCoreDataset:
    return prepare_core_data_dataset(
        CoreDataBatch(
            simulation_code="SIM-W44",
            simulation_name="PSM W44",
            source_type="BIGDATAQUERY",
            frame=frame,
            source_registered_at=datetime(2026, 10, 30, 9, 0),
        ),
        DISPLAY_ORDER,
    )


def _blank_run_rate_source() -> pd.DataFrame:
    """한 공정의 한 달 효율을 모두 비운 원천 — 그 경로는 살아 있어 계산이 멈춘다."""
    frame = SEED.source_data.copy()
    month = int(frame.loc[frame["공정"].eq(PROCESS), "생산계획년월"].min())
    mask = frame["공정"].eq(PROCESS) & frame["생산계획년월"].eq(month)
    frame.loc[mask, "CAPA_RUN_RATE"] = pd.NA
    return frame


def test_a_healthy_source_has_nothing_to_say() -> None:
    check = check_registration_capacity(SEED.reference_tables)

    assert not check.stopped
    assert (check.memo(), check.notice(1)) == ("", "")


def test_a_blank_run_rate_on_a_live_route_is_caught_before_saving() -> None:
    check = check_registration_capacity(_prepared(_blank_run_rate_source()).reference_tables)

    assert check.stopped
    assert check.problem is not None
    assert (check.problem.table, check.problem.shape) == ("RQ_RUN_RATE", JOIN_BLANK_VALUE)
    assert check.memo() == f"대당 Capa 계산 멈춤(RQ_RUN_RATE {check.problem.summary()})"
    # 메모에는 값·이름이 없다 — 공정 이름은 화면 글(키 예시)에만 있다.
    assert PROCESS not in check.memo()
    notice = check.notice(1)
    assert notice.startswith("저장은 했지만 r1은 대당 Capa 계산이 멈춥니다 — RQ_RUN_RATE의 ")
    assert PROCESS in notice
    assert "기준 정보 화면 「효율」 표에서 그 칸에 0보다 큰 값을 넣고" in notice
    assert "새 리비전으로 저장하면 r2부터 계산이 섭니다." in notice


def test_a_blank_run_rate_only_on_routes_dropped_anyway_does_not_warn() -> None:
    """뒤에서 빠질 경로(Main UPEH 0)에만 붙은 빈 효율은 계산을 멈추지 않는다(A2) — 알리지 않는다."""
    frame = _blank_run_rate_source()
    month = int(frame.loc[frame["공정"].eq(PROCESS), "생산계획년월"].min())
    mask = frame["공정"].eq(PROCESS) & frame["생산계획년월"].eq(month)
    frame.loc[mask & frame["Area_Name"].eq("Main"), "UPEH"] = 0.0
    assert frame.loc[mask, "Area_Name"].eq("Main").all()

    assert not check_registration_capacity(_prepared(frame).reference_tables).stopped


def test_zero_and_blank_siblings_stand_today_but_a_revision_saved_earlier_stays_stopped() -> None:
    """형제 행이 0 과 빈 값뿐인 키 — 지금 등록은 0 을 골라 그 경로만 빠지고 계산이 선다. 0 을 먼저
    고르기 전(2026-11-01 사용자 결정 전)에 저장한 리비전은 원천 행 차례대로 빈 값일 수 있고 내용을
    고칠 수 없어 그대로 멈춘다 — 같은 원천을 다시 등록해야 풀린다(사내 리뷰 202611041000 발견 1 이
    재는 갈래 가운데 하나, 런북 8-12 `영빈`).
    """
    frame = SEED.source_data.copy()
    month = int(frame.loc[frame["공정"].eq(PROCESS), "생산계획년월"].min())
    mask = frame["공정"].eq(PROCESS) & frame["생산계획년월"].eq(month)
    siblings = frame.loc[mask].assign(**{"Capa Code": "DEMO_SIBLING"})
    frame.loc[mask, "CAPA_RUN_RATE"] = pd.NA
    siblings["CAPA_RUN_RATE"] = 0.0

    tables = _prepared(pd.concat([frame, siblings], ignore_index=True)).reference_tables

    assert not check_registration_capacity(tables).stopped
    saved = tables["RQ_RUN_RATE"].copy()
    cell = saved["공정"].eq(PROCESS) & saved["생산계획년월"].eq(month)
    assert saved.loc[cell, "CAPA_RUN_RATE"].eq(0.0).all()
    saved["CAPA_RUN_RATE"] = saved["CAPA_RUN_RATE"].astype("float64")
    saved.loc[cell, "CAPA_RUN_RATE"] = float("nan")
    earlier = check_registration_capacity({**tables, "RQ_RUN_RATE": saved})
    assert earlier.problem is not None
    assert (earlier.problem.table, earlier.problem.shape) == ("RQ_RUN_RATE", JOIN_BLANK_VALUE)


def _plan_only_source() -> pd.DataFrame:
    """계획 행만 있는 원천 — 경로 행(계획기초정보여부 N)이 하나도 없다."""
    frame = SEED.source_data
    return frame.loc[frame["계획기초정보여부"].eq("Y")].reset_index(drop=True)


def test_a_plan_only_source_is_caught_by_its_empty_route_tables() -> None:
    """경로 행이 없으면 대당 Capa 는 멈추지 않고 0행으로 끝난다 — 그 리비전을 불러온 계산 화면이
    조회기간 자리에서 처음 멈췄다(2026-11-08 사용자 결정 U3 — 등록 점검이 빈 표를 잡는다). 글은 표
    이름 대신 기준 정보 화면 이름을 쓰고, 앱에서 고칠 수 없으니 원천을 다시 등록하라고 한다."""
    tables = _prepared(_plan_only_source()).reference_tables
    assert tables["RQ_UPEH"].empty and tables["RQ_REQB"].empty and tables["RQ_EQP_AVBL"].empty

    check = check_registration_capacity(tables)

    assert check.stopped
    assert check.empty == ("RQ_UPEH", "RQ_REQB", "RQ_EQP_AVBL")
    assert check.memo() == "대당 Capa 계산 멈춤(빈 표 RQ_UPEH · RQ_REQB · RQ_EQP_AVBL)"
    notice = check.notice(1)
    assert notice == (
        "저장은 했지만 r1은 대당 Capa 계산이 멈춥니다 — 공정이 든 경로 행(계획기초정보여부 N)이 "
        "없는 원천이라 「UPEH」 · 「STEP 구성」 · 「설비대수 가용」 표가 비었습니다. 앱에서 "
        "고칠 수 없어 새 리비전으로는 풀리지 않습니다 — 원천에 경로 행을 넣어 다시 등록하세요."
    )
    assert "RQ_" not in notice


def _blank_route_cs_source() -> pd.DataFrame:
    """경로 행(계획기초정보여부 N)은 그대로 있고 그 CS 만 모두 빈 원천."""
    frame = SEED.source_data.copy()
    frame.loc[frame["계획기초정보여부"].eq("N"), "CS"] = pd.NA
    return frame


def test_route_rows_dropped_for_blank_cs_point_at_their_cs_not_at_missing_rows() -> None:
    """경로 행이 있어도 CS 가 모두 비면 등록 파생이 빼 같은 세 표가 빈다(2026-10-27 결정). 글이
    「경로 행이 없는 원천」 이라 하면 바로 앞 CS 경고(「CS 가 빈 행 …(계획 0행 · 경로 n행)는 … 빼고
    저장했습니다」)와 맞부딪치고, 이미 있는 경로 행을 다시 넣으라고 가리킨다 — 뺀 경로 행 수를
    들고 그 CS 를 채우라고 한다."""
    prepared = _prepared(_blank_route_cs_source())
    routes = prepared.blank_cs.route_rows
    assert routes > 0 and prepared.blank_cs.plan_rows == 0

    check = check_registration_capacity(prepared.reference_tables, blank_cs_routes=routes)

    assert check.empty == ("RQ_UPEH", "RQ_REQB", "RQ_EQP_AVBL")
    notice = check.notice(1)
    assert notice == (
        f"저장은 했지만 r1은 대당 Capa 계산이 멈춥니다 — CS 가 빈 경로 행 {routes:,}개를 빼자 "
        "공정이 든 행이 남지 않아 「UPEH」 · 「STEP 구성」 · 「설비대수 가용」 표가 비었습니다. "
        "앱에서 고칠 수 없어 새 리비전으로는 풀리지 않습니다 — 원천 경로 행의 CS 를 채워 다시 "
        "등록하세요."
    )
    assert "없는 원천" not in notice and "경로 행을 넣어" not in notice


def test_a_registration_carries_its_blank_cs_route_rows_into_the_check(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "registration.duckdb")
    repository.initialize()
    repository.initialize_global_display_order(DISPLAY_ORDER)
    prepared = _prepared(_blank_route_cs_source())

    registration = save_bigdataquery_scenario(
        repository,
        prepared,
        full_data_scenario_preset(prepared.reference_tables),
        scenario_name="PSM W44 (SIM-W44)",
        revision_name="초기 리비전",
        note="",
    )

    assert registration.capacity.blank_cs_routes == prepared.blank_cs.route_rows
    assert registration.capacity.notice(1).endswith("원천 경로 행의 CS 를 채워 다시 등록하세요.")
    [scenario] = repository.list_scenarios()
    saved = repository.load_revision(scenario.active_revision_id)
    assert saved.revision.note == (
        f"{prepared.blank_cs.memo()} · 대당 Capa 계산 멈춤(빈 표 RQ_UPEH · RQ_REQB · RQ_EQP_AVBL)"
    )


def _route_only_source() -> pd.DataFrame:
    """경로 행만 있는 원천 — 계획 행(계획기초정보여부 Y)이 하나도 없다."""
    frame = SEED.source_data
    return frame.loc[frame["계획기초정보여부"].eq("N")].reset_index(drop=True)


def test_a_route_only_source_is_caught_by_its_empty_plan_table() -> None:
    """반대로 경로 행만 있으면 대당 Capa 는 서지만 HOME · 생산 계획 · 표준 목표가
    「RQ_PKG_PLAN에 선택할 생산계획년월 데이터가 없습니다」 로 처음 멈췄다(검수 보드
    st-route-only — U3 와 같은 꼴). 글은 멈추는 화면과 표의 화면 이름을 쓰고, 원천에 계획 행을
    넣어 다시 등록하라고 한다."""
    tables = _prepared(_route_only_source()).reference_tables
    assert tables["RQ_PKG_PLAN"].empty and not tables["RQ_REQB"].empty

    check = check_registration_capacity(tables)

    assert check.stopped
    assert (check.empty, check.empty_plan, check.table) == ((), ("RQ_PKG_PLAN",), "RQ_PKG_PLAN")
    assert check.memo() == "HOME · 생산 계획 · 표준 목표 계산 멈춤(빈 표 RQ_PKG_PLAN)"
    notice = check.notice(1)
    assert notice == (
        "저장은 했지만 r1은 HOME · 생산 계획 · 표준 목표 계산이 멈춥니다 — 계획 행"
        "(계획기초정보여부 Y)이 없는 원천이라 「PKG PLAN」 표가 비었습니다. 앱에서 고칠 수 없어 "
        "새 리비전으로는 풀리지 않습니다 — 원천에 계획 행을 넣어 다시 등록하세요."
    )
    assert "RQ_" not in notice and "대당 Capa" not in notice


def test_one_empty_route_table_names_only_itself_without_guessing_why() -> None:
    """세 표는 파생에서 함께 빈다 — 하나만 빈 꼴은 등록 파생에서 나오지 않으니 경로 행이 없다고도,
    CS 가 비었다고도 단정하지 않는다."""
    tables = dict(SEED.reference_tables)
    tables["RQ_EQP_AVBL"] = tables["RQ_EQP_AVBL"].iloc[:0]

    for routes in (0, 3):
        check = check_registration_capacity(tables, blank_cs_routes=routes)

        assert check.empty == ("RQ_EQP_AVBL",)
        assert check.notice(1) == (
            "저장은 했지만 r1은 대당 Capa 계산이 멈춥니다 — 「설비대수 가용」 표가 비었습니다. "
            "앱에서 고칠 수 없어 새 리비전으로는 풀리지 않습니다 — 원천을 고쳐 다시 등록하세요."
        )


def test_a_plan_only_source_is_still_saved_with_its_empty_tables_in_the_memo(
    tmp_path: Path,
) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "registration.duckdb")
    repository.initialize()
    repository.initialize_global_display_order(DISPLAY_ORDER)
    prepared = _prepared(_plan_only_source())

    registration = save_bigdataquery_scenario(
        repository,
        prepared,
        full_data_scenario_preset(prepared.reference_tables),
        scenario_name="PSM W44 (SIM-W44)",
        revision_name="초기 리비전",
        note="",
    )

    assert registration.capacity.stopped
    [scenario] = repository.list_scenarios()
    saved = repository.load_revision(scenario.active_revision_id)
    assert saved.revision.note == registration.capacity.memo()


def test_a_stopping_source_is_still_saved_with_its_shape_in_the_memo(tmp_path: Path) -> None:
    repository = DuckDBScenarioRepository(tmp_path / "registration.duckdb")
    repository.initialize()
    repository.initialize_global_display_order(DISPLAY_ORDER)
    prepared = _prepared(_blank_run_rate_source())

    registration = save_bigdataquery_scenario(
        repository,
        prepared,
        full_data_scenario_preset(prepared.reference_tables),
        scenario_name="PSM W44 (SIM-W44)",
        revision_name="초기 리비전",
        note="원천 메모",
    )

    assert registration.capacity.stopped
    [scenario] = repository.list_scenarios()
    saved = repository.load_revision(scenario.active_revision_id)
    assert saved.revision.revision_no == registration.snapshot.revision.revision_no == 1
    assert saved.revision.note == f"원천 메모 · {registration.capacity.memo()}"


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        (
            RegistrationCapacityCheck(
                "RQ_VITAL의 편중률 값이 빈 대당 Capa 기준이 있습니다: 1건, 예시 []",
                ReferenceJoinProblem("RQ_VITAL", JOIN_BLANK_VALUE, keys=1, rows=1),
            ),
            "기준 정보 화면 「여유율」 표에서",
        ),
        (
            RegistrationCapacityCheck(
                "RQ_RUN_RATE의 연결 키가 중복되었습니다: 1건, 예시 []",
                ReferenceJoinProblem("RQ_RUN_RATE", JOIN_DUPLICATE_KEY, keys=1, rows=2),
            ),
            "원천을 고쳐 다시 등록하세요.",
        ),
        (
            RegistrationCapacityCheck(
                "RQ_MODULE 연결값이 없는 대당 Capa 기준이 있습니다: 1건, 예시 []",
                ReferenceJoinProblem("RQ_MODULE", "연결값 없음", keys=1, rows=1),
            ),
            "모듈수(RQ_MODULE)는 앱에서 고칠 수 없어",
        ),
        # 기준정보 연결 오류가 아닌 멈춤 — 글 머리의 표 이름으로 탭을 고른다.
        (
            RegistrationCapacityCheck(
                "RQ_UPEH의 Main 행에 UPEH 누락값 또는 숫자가 아닌 값이 있습니다."
            ),
            "기준 정보 화면 「UPEH」 표에서",
        ),
        (
            RegistrationCapacityCheck("RQ_RUN_DAY의 RUN_DAY 값은 0보다 커야 합니다: 1건, 예시 []"),
            "기준 정보 화면 「일수」 표에서",
        ),
        # 기준정보 연결 오류가 아니어도 표 자체가 깨진 꼴(키 중복 · Area_Name · 키 누락)은 칸을
        # 채워 풀리지 않는다 — 「UPEH」 탭으로 보내지 않는다.
        (
            RegistrationCapacityCheck("RQ_UPEH의 연결 키가 중복되었습니다: 1건, 예시 []"),
            "원천을 고쳐 다시 등록하세요.",
        ),
        (
            RegistrationCapacityCheck("RQ_UPEH의 Area_Name은 Main 또는 MI여야 합니다: ['X']"),
            "원천을 고쳐 다시 등록하세요.",
        ),
        (
            RegistrationCapacityCheck("RQ_UPEH의 필수 연결 키에 누락값이 있습니다."),
            "원천을 고쳐 다시 등록하세요.",
        ),
    ],
)
def test_the_fix_hint_points_to_where_the_shape_can_be_fixed(
    check: RegistrationCapacityCheck, expected: str
) -> None:
    assert expected in check.fix_hint(1)
    assert expected in check.notice(1)


def test_a_plain_stop_names_its_table_in_the_memo() -> None:
    check = RegistrationCapacityCheck("RQ_UPEH의 MI 행 ST 값은 0보다 커야 합니다.")

    assert check.table == "RQ_UPEH"
    assert check.memo() == "대당 Capa 계산 멈춤(RQ_UPEH)"


def test_a_stop_message_that_ends_with_a_period_is_not_doubled() -> None:
    notice = RegistrationCapacityCheck("RQ_UPEH의 MI 행 ST 값은 0보다 커야 합니다.").notice(1)

    assert ".." not in notice
    assert "0보다 커야 합니다. 기준 정보 화면 「UPEH」 표에서" in notice
