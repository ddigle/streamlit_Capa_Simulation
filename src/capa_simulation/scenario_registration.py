# Purpose: BigDataQuery 로 받은 원천을 세션 없이 시나리오(리비전 1)로 저장하는 등록 경로를 제공한다.

"""BigDataQuery 원천 → 시나리오 저장. 화면 등록과 공식버전 자동 갱신이 같은 길을 지난다.

화면(`components/bigdataquery_registration.py`)은 폼 값을 읽고 조회 중 안내를 그리고 저장한 뒤 그
세션에서 새 리비전을 활성화한다. 자동 갱신은 세션이 없는 배경 작업이다. 둘 다 저장 자체 — 원천
메타데이터·파이프라인 버전·리비전 메모의 상세 조회기간과 CS 가 비어 뺀 행 수, 저장 전에 한 번 돌려
본 대당 Capa 의 멈춤(`RegistrationCapacityCheck`) — 는 여기 한 곳에서 정한다. 그래서 자동으로 받은
시나리오와 손으로 받은 시나리오가 같은 꼴로 남는다.

Streamlit 을 import 하지 않고 세션을 읽지 않는다. 프리셋은 부르는 쪽이 만든다 — 화면은 세션의 레거시
확보·경고 값을 실은 `capture_full_data_scenario_preset`, 자동 갱신은 세션 없는
`full_data_scenario_preset` 이다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import pandas as pd

from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.core_data_pipeline import PreparedCoreDataset
from capa_simulation.services.korean_particle import with_topic_particle
from capa_simulation.services.unit_capacity import (
    JOIN_BLANK_VALUE,
    JOIN_NO_MATCH,
    JOIN_NOT_NUMERIC,
    ReferenceJoinError,
    ReferenceJoinProblem,
    calculate_unit_capacity,
)

BIGDATAQUERY_PIPELINE_VERSION: Final = "bigdataquery-core-data-v6"

# 대당 Capa 를 멈춘 표 → 기준 정보 화면의 탭(낫표까지 — 앱이 지은 이름이다). 모듈수(`RQ_MODULE`)는
# 편집·리비전 대상이 아니다.
_EDIT_TABS: Final = {
    "RQ_UPEH": "「UPEH」",
    "RQ_RUN_RATE": "「효율」",
    "RQ_VITAL": "「여유율」",
    "RQ_RUN_DAY": "「일수」",
    "RQ_LOT_RATIO": "「Lot측정률」",
    "RQ_WF_RATIO": "「WF측정률」",
}
# 편집표에서 그 칸을 채우면 풀리는 꼴. 나머지 꼴(컬럼·월 형식·연결 키)은 표 자체가 깨져 편집표가
# 서지 않는다.
_CELL_SHAPES: Final = frozenset({JOIN_BLANK_VALUE, JOIN_NOT_NUMERIC, JOIN_NO_MATCH})
# 기준정보 연결 오류가 아닌 멈춤 가운데 칸 하나를 채우거나 고치면 풀리는 글 — 0 이하
# (`unit_capacity._assert_positive`, MI 행 ST)와 UPEH·ST 누락(`_prepare_performance`). 그 밖의
# 글(컬럼 없음·월 형식·연결 키 누락·Area_Name·키 중복)은 표 자체가 깨진 꼴이다.
_CELL_MESSAGE_MARKERS: Final = ("0보다 커야 합니다", "누락값 또는 숫자가 아닌 값")
_TABLE_NAME = re.compile(r"^(RQ_[A-Z_]+)")


@dataclass(frozen=True)
class RegistrationCapacityCheck:
    """저장 전에 등록할 원천으로 대당 Capa 를 한 번 돌려 본 결과(2026-11-01 사용자 결정 — 알리기만).

    멈춰도 **저장은 한다.** 막으면 원천을 다시 받아야만 풀리지만, 기준 정보 편집에서 그 칸을 채워 새
    리비전으로 저장하면 서는 꼴이 많다(사내 리뷰 202610271800 발견 1 — S27 r1 은 등록은 됐고 계산할
    때 처음 멈췄다). 그래서 등록한 사람에게 무엇이 멈췄고 어떻게 푸는지 알린다 — 화면 등록은 저장
    알림 밑 경고 띠, 자동 갱신은 실행 기록 사유 — 와 리비전 메모의 꼴·개수.

    `error` 는 계산 페이지와 같은 글(키 예시를 싣는다), `problem` 은 기준정보 연결 오류의 꼴·개수(값
    없음)다. 멈추지 않았으면 둘 다 None 이다.
    """

    error: str | None = None
    problem: ReferenceJoinProblem | None = None

    @property
    def stopped(self) -> bool:
        return self.error is not None

    @property
    def table(self) -> str | None:
        """멈춘 표 이름. 기준정보 연결 오류가 아니면 글 머리의 표 이름이다."""
        if self.problem is not None:
            return self.problem.table
        if self.error is None:
            return None
        match = _TABLE_NAME.match(self.error)
        return match.group(1) if match else None

    def memo(self) -> str:
        """리비전 메모 끝에 붙이는 조각 — 꼴과 개수만(값·이름 없음). 멈추지 않았으면 빈 글."""
        if not self.stopped:
            return ""
        if self.problem is not None:
            return f"대당 Capa 계산 멈춤({self.problem.table} {self.problem.summary()})"
        return f"대당 Capa 계산 멈춤({self.table or '기준정보'})"

    def fix_hint(self, revision_no: int) -> str:
        """어떻게 푸는지 — 고칠 탭과 다음 리비전 번호."""
        table = self.table
        if table == "RQ_MODULE":
            return (
                "모듈수(RQ_MODULE)는 앱에서 고칠 수 없어 새 리비전으로는 풀리지 않습니다 — 원천을 "
                "고쳐 다시 등록하세요."
            )
        if not self._cell_fixable():
            return (
                "표 자체가 깨진 꼴(컬럼 · 월 형식 · 연결 키)이라 기준 정보 화면에서는 고칠 수 "
                "없습니다 — 원천을 고쳐 다시 등록하세요."
            )
        tab = _EDIT_TABS.get(table or "")
        where = f"기준 정보 화면 {tab} 탭" if tab else "기준 정보 화면"
        return (
            f"{where}에서 그 칸에 0보다 큰 값을 넣고 「변경사항 적용」 뒤 새 리비전으로 저장하면 "
            f"r{revision_no + 1}부터 계산이 섭니다."
        )

    def _cell_fixable(self) -> bool:
        """기준 정보 편집표의 칸을 채우거나 고쳐 풀리는 꼴인가."""
        if self.problem is not None:
            return self.problem.shape in _CELL_SHAPES
        return any(marker in (self.error or "") for marker in _CELL_MESSAGE_MARKERS)

    def notice(self, revision_no: int) -> str:
        """화면 등록의 경고 띠 — 저장은 됐고 그 리비전의 계산이 멈춘다. 멈추지 않았으면 빈 글."""
        if self.error is None:
            return ""
        revision = with_topic_particle(f"r{revision_no}")
        # 「…합니다.」 로 끝나는 글도 있다 — 마침표를 겹치지 않는다.
        error = self.error.rstrip().rstrip(".")
        return (
            f"저장은 했지만 {revision} 대당 Capa 계산이 멈춥니다 — {error}. "
            f"{self.fix_hint(revision_no)}"
        )


def check_registration_capacity(tables: Mapping[str, pd.DataFrame]) -> RegistrationCapacityCheck:
    """등록할 기준정보 표로 대당 Capa 를 한 번 계산해 본다 — 계산 페이지가 처음 멈출 자리를 미리
    본다.

    소요대수까지 가지 않는다 — 원천에서 바로 고칠 수 있는 기준정보 연결 오류를 보려는 것이고, 한
    번에 합성 표본 약 0.2초다(샘플 관측). 기준정보 계약 위반(`ValueError`)만 결과로 담고, 다른
    예외는 코드 결함이라 그대로 올린다(`simulation_cache._capacity_outcome` 과 같은 갈래).
    """
    try:
        calculate_unit_capacity(
            upeh=tables["RQ_UPEH"],
            run_rate=tables["RQ_RUN_RATE"],
            vital=tables["RQ_VITAL"],
            module=tables["RQ_MODULE"],
            run_day=tables["RQ_RUN_DAY"],
            lot_ratio=tables["RQ_LOT_RATIO"],
            wf_ratio=tables["RQ_WF_RATIO"],
        )
    except ReferenceJoinError as exc:
        return RegistrationCapacityCheck(str(exc), exc.problem)
    except ValueError as exc:
        return RegistrationCapacityCheck(str(exc))
    return RegistrationCapacityCheck()


@dataclass(frozen=True)
class BigDataQueryRegistration:
    """등록 한 번의 결과 — 저장한 리비전 1 과 저장 전에 돌려 본 대당 Capa."""

    snapshot: ScenarioSnapshot
    capacity: RegistrationCapacityCheck


def registration_note(note: str, window: QueryWindow) -> str:
    """리비전 1 메모 — 적은 메모 뒤에 실제로 조회한 상세 기간을 붙인다.

    기간을 넓혀 다시 받은 리비전과 기본 창으로 받은 리비전이 어떻게 다른지 나중에 알 수 있어야 한다.
    """
    return " · ".join(part for part in (note.strip(), f"상세 조회기간 {window.label()}") if part)


def save_bigdataquery_scenario(
    repository: DuckDBScenarioRepository,
    prepared: PreparedCoreDataset,
    preset: ScenarioPreset,
    *,
    scenario_name: str,
    revision_name: str,
    note: str,
) -> BigDataQueryRegistration:
    """조회·변환을 마친 원천을 새 시나리오와 리비전 1 로 저장한다. 세션을 활성화하지 않는다.

    저장하기 **전에** 대당 Capa 를 한 번 돌려 보고(`check_registration_capacity`) 멈춰도 저장한다 —
    부르는 쪽이 결과의 `capacity` 로 등록한 사람에게 알린다. CS 가 비어 표에서 뺀 행 수
    (`BlankCsDrop.memo`)와 대당 Capa 멈춤의 꼴·개수(`RegistrationCapacityCheck.memo`)는 리비전 메모
    끝에 붙인다 — 저장한 리비전에 남는 기록이다. 이름 중복(보관본 포함)·원천 코드 불변 검사는
    저장소가 쓰기 트랜잭션 안에서 한다.
    """
    capacity = check_registration_capacity(prepared.reference_tables)
    memos = [memo for memo in (prepared.blank_cs.memo(), capacity.memo()) if memo]
    if memos:
        note = " · ".join(part for part in (note.strip(), *memos) if part)
    snapshot = repository.create_scenario(
        ScenarioCreate(
            scenario_name=scenario_name,
            source_simulation_code=prepared.batch.simulation_code,
            source_simulation_name=prepared.batch.simulation_name,
            source_type=prepared.batch.source_type,
            pipeline_version=BIGDATAQUERY_PIPELINE_VERSION,
            source_registered_at=prepared.batch.source_registered_at,
        ),
        prepared.reference_tables,
        preset,
        source_data=prepared.source_data,
        revision_name=revision_name,
        note=note,
    )
    return BigDataQueryRegistration(snapshot, capacity)
