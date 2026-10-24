# Purpose: 세션의 설비 시나리오(시나리오·일정 리비전)를 세우고 옮기며 판정 셋·낡음·라벨을 낸다.

"""설비 시나리오 세션 — 시뮬레이션 `scenario_activation.py` 의 짝(설계 4-2).

- **세션은 (시나리오, 일정 리비전) 하나를 고정해 든다.** 새 세션은 최신 공식 발행으로 연다(E5). 공통
  대장은 시나리오와 무관하게 늘 최신이다(E2) — 세션이 보는 한 벌은 (공통 최신, 고른 일정 리비전)
  쌍을 합친 스냅샷이다.
- **페이지 진입 = `resolve_equipment_session`.** 설비 화면이 각자 `BOOTSTRAP_ERRORS` 처리 아래에서
  부른다 — 마이그레이션·DB 오류는 그 화면의 「준비하지 못했습니다」 로 선다. `app.py` 는 설비 DB 를
  열지 않고, 사이드바 설비 시나리오 줄도 페이지가 이 함수 뒤에 그린다(같은 회차 목록으로 맞다).
- **판정 셋**(검토 2-4 — 「공식」 하나로 셋을 가르지 않는다): 공식 시나리오(설정 팝업 Cut-off
  편집·미확인은 자기 일정), 공식 발행 쌍(기준선 저장·Space 배치 편집), 가정 시나리오(공식 시나리오가
  아님). 따로 **낡음**(세션 리비전 ≠ 그 시나리오 최신 — 일정 칸·행 추가 잠금).
- 세션 칸에는 기본형만 둔다(AGENTS 5장 21).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st

from capa_simulation.components.equipment_data_workspace import (
    has_unsaved_equipment_edits,
    pop_saved_schedule,
    reset_equipment_drafts,
)
from capa_simulation.components.equipment_save_fields import EquipmentSaveBasis
from capa_simulation.persistence.equipment_cache import (
    latest_equipment_revision_id,
    load_equipment_scenario_catalog,
    load_merged_equipment_snapshot,
    load_official_equipment_snapshot,
)
from capa_simulation.persistence.equipment_repository import (
    EquipmentScenarioCatalog,
    EquipmentScenarioIncompatible,
    EquipmentScenarioSummary,
    EquipmentSnapshot,
)
from capa_simulation.services.korean_particle import object_particle, with_direction_particle

# {"scenario_id": str, "schedule_revision_id": str | None} — 세션이 고정해 든 쌍의 일정 쪽.
SELECTION_KEY = "equipment_scenario_selection_v1"
# 머리 띠·사이드바 줄 글자 재료(시나리오명·rN·공식 vN·최신 rM·판정 셋). 페이지가 그 회차 목록을 읽은
# 뒤 적는다 — 머리 띠는 세션만 읽는다.
LABEL_KEY = "equipment_scenario_label_v1"


@dataclass(frozen=True)
class EquipmentSession:
    """이번 회차의 설비 시나리오 세션 — 고른 쌍의 합친 스냅샷과 그 회차 목록."""

    catalog: EquipmentScenarioCatalog
    scenario: EquipmentScenarioSummary | None = None
    schedule_revision_id: str | None = None
    # (공통 최신, 고른 일정 리비전) 합친 스냅샷. 공통 리비전이 없으면 None.
    snapshot: EquipmentSnapshot | None = None
    # 이번 회차에 「합칠 수 없음」 으로 다른 리비전으로 옮겼으면 그 알림.
    notice: str | None = None
    # 옛 배포 흔적(경계 뒤 계약 v3 공통)이 어느 일정과도 합쳐지지 않아 공통만 읽은 회차 — 일정 없이
    # 연 것이다(`snapshot.schedule` 이 None, 모든 호기가 일정 없음). 공식 발행 쌍이 아니고 저장도
    # 막혀 있다(흔적). 빠져나갈 길은 백업 복원뿐이다(이어 쓰기는 같은 까닭으로 거절된다).
    unmerged: bool = False

    @property
    def scenario_id(self) -> str | None:
        return self.scenario.equipment_scenario_id if self.scenario is not None else None

    @property
    def scenario_name(self) -> str | None:
        return self.scenario.scenario_name if self.scenario is not None else None

    @property
    def revision_no(self) -> int | None:
        """세션이 든 일정 리비전 번호(그 시나리오 안의 rN). 리비전이 없거나 일정 없이 열었으면
        None."""
        if self.unmerged:
            return None
        if self.snapshot is not None and self.snapshot.schedule is not None:
            return self.snapshot.schedule.revision_no
        if self.scenario is not None and self.schedule_revision_id is not None:
            if self.schedule_revision_id == self.scenario.latest_schedule_revision_id:
                return self.scenario.latest_revision_no
        return None

    @property
    def latest_revision_no(self) -> int | None:
        return self.scenario.latest_revision_no if self.scenario is not None else None

    @property
    def release_no(self) -> int | None:
        """최신 공식 번호(「공식 vN」). 발행이 없으면 None."""
        return self.catalog.release_no

    @property
    def official_scenario_id(self) -> str | None:
        """공식 설비 시나리오 — 최신 발행의 시나리오. 발행이 없으면 목록 첫 시나리오(이관이 넣은
        「운영 일정」 이 맨 앞이다)."""
        if self.catalog.official_scenario_id is not None:
            return self.catalog.official_scenario_id
        return self.catalog.scenarios[0].equipment_scenario_id if self.catalog.scenarios else None

    @property
    def is_official_scenario(self) -> bool:
        """세션 시나리오 = 공식 시나리오(E3 설정 팝업 Cut-off 편집, 미확인은 세션 자기 일정)."""
        return self.scenario_id is not None and self.scenario_id == self.official_scenario_id

    @property
    def is_official_pair(self) -> bool:
        """세션 (시나리오, 리비전) = 최신 공식 발행(E5 기준선 저장, Space 배치 편집 — 질문 3).

        발행이 하나도 없으면(빈 저장소) 공식 시나리오의 최신을 공식 자리로 본다. 일정 없이 연 회차
        (`unmerged`)는 그 쌍을 읽지 못한 것이라 아니다.
        """
        if self.unmerged:
            return False
        release = self.catalog.latest_release
        if release is None:
            return self.is_official_scenario and not self.stale
        return (
            self.scenario_id == release.equipment_scenario_id
            and self.schedule_revision_id == release.schedule_revision_id
        )

    @property
    def is_assumption(self) -> bool:
        """가정 시나리오 — 공식 시나리오가 아님(설정 팝업 Cut-off 읽기 전용, 미확인은 공식 기준)."""
        return self.scenario is not None and not self.is_official_scenario

    @property
    def stale(self) -> bool:
        """세션 리비전이 그 시나리오 최신이 아님 — 일정 칸·행 추가를 잠근다."""
        if self.scenario is None or self.scenario.latest_schedule_revision_id is None:
            return False
        return self.schedule_revision_id != self.scenario.latest_schedule_revision_id

    @property
    def legacy_trace_count(self) -> int:
        return self.catalog.legacy_trace_count

    def save_basis(self) -> EquipmentSaveBasis | None:
        """저장 요청의 출발점(저장할 시나리오·화면이 본 공식 번호·낡음). 시나리오가 없으면 None."""
        if self.scenario is None:
            return None
        return EquipmentSaveBasis(
            equipment_scenario_id=self.scenario.equipment_scenario_id,
            scenario_name=self.scenario.scenario_name,
            release_no=self.release_no or 0,
            stale=self.stale,
            revision_no=self.revision_no,
            latest_revision_no=self.latest_revision_no,
            official_scenario=self.is_official_scenario,
        )

    def label(self) -> dict[str, Any]:
        """머리 띠·사이드바 줄 재료(기본형만)."""
        return {
            "scenario_name": self.scenario_name,
            "revision_no": self.revision_no,
            "latest_revision_no": self.latest_revision_no,
            "release_no": self.release_no,
            "official_scenario": self.is_official_scenario,
            "official_pair": self.is_official_pair,
            "stale": self.stale,
            "unmerged": self.unmerged,
        }


def space_editing_allowed(session: EquipmentSession) -> bool:
    """Space 배치 편집을 열어도 되는가 — 세션이 공식 발행 쌍일 때만(질문 3 권장안의 한 곳).

    Space 보기는 늘 공식이다(E5). 가정 시나리오 편집본을 공식 일정 색 위에서 고치면 새 호기 날짜·
    색·겹침 경고가 서로 다른 일정을 보게 된다.
    """
    return session.snapshot is not None and session.is_official_pair


def official_snapshot_for(
    database_path: str, session: EquipmentSession
) -> EquipmentSnapshot | None:
    """화면이 「공식」 으로 그릴 스냅샷 — 공통 최신 + 최신 공식 발행(공식 스냅샷 캐시).

    일정 없이 연 회차(`unmerged` — 옛 배포 흔적이 공식과도 합쳐지지 않음)는 공식을 읽으면 같은
    까닭으로 멈추므로 세션이 읽은 공통만의 한 벌을 그대로 쓴다(알림은 세션이 낸다).
    """
    if session.unmerged:
        return session.snapshot
    return load_official_equipment_snapshot(database_path)


def official_session(
    session: EquipmentSession, official_snapshot: EquipmentSnapshot | None
) -> EquipmentSession:
    """같은 회차 목록으로 본 **공식** 쪽 — Space 의 잠근 줄처럼 세션과 무관하게 공식을 보일 때.

    `official_snapshot` 은 공식 스냅샷(`load_official_equipment_snapshot`)이다. 세션이 이미 공식
    발행 쌍이면 그대로 돌려준다. 세션 칸은 건드리지 않는다.
    """
    if session.is_official_pair or session.unmerged:
        return session
    selection = _default_selection(session.catalog)
    if selection is None:
        return EquipmentSession(catalog=session.catalog)
    return EquipmentSession(
        catalog=session.catalog,
        scenario=session.catalog.scenario(selection[0]),
        schedule_revision_id=selection[1],
        snapshot=official_snapshot,
    )


def current_selection() -> tuple[str, str | None] | None:
    """세션 칸의 (시나리오 id, 일정 리비전 id). 없거나 꼴이 어긋나면 None."""
    value = st.session_state.get(SELECTION_KEY)
    if not isinstance(value, dict):
        return None
    scenario = value.get("scenario_id")
    schedule = value.get("schedule_revision_id")
    if not isinstance(scenario, str):
        return None
    return scenario, schedule if isinstance(schedule, str) else None


def _write_selection(scenario_id: str, schedule_revision_id: str | None) -> None:
    st.session_state[SELECTION_KEY] = {
        "scenario_id": scenario_id,
        "schedule_revision_id": schedule_revision_id,
    }


def _default_selection(catalog: EquipmentScenarioCatalog) -> tuple[str, str | None] | None:
    """새 세션 = 최신 공식 발행 → 없으면 목록 첫 시나리오의 최신 → 시나리오가 없으면 None."""
    release = catalog.latest_release
    if release is not None and catalog.scenario(release.equipment_scenario_id) is not None:
        return release.equipment_scenario_id, release.schedule_revision_id
    if not catalog.scenarios:
        return None
    first = catalog.scenarios[0]
    return first.equipment_scenario_id, first.latest_schedule_revision_id


def _settled_selection(catalog: EquipmentScenarioCatalog) -> tuple[str, str | None] | None:
    """이번 회차의 선택 — 세션 칸이 목록에 맞으면 그대로, 아니면 공식으로.

    - 자기 저장이 이 시나리오에 새 일정 리비전을 만들었으면 그 리비전으로 옮긴다(공통만 쓴 저장은
      그대로).
    - 고른 시나리오에 리비전이 없던 선택(None)은 그 사이 생긴 최신을 받는다 — 고정할 것이 없었다.
    """
    saved = pop_saved_schedule()
    selection = current_selection()
    if saved is not None and (selection is None or selection[0] == saved[0]):
        selection = saved
    if selection is not None:
        scenario = catalog.scenario(selection[0])
        if scenario is not None:
            if selection[1] is None:
                return scenario.equipment_scenario_id, scenario.latest_schedule_revision_id
            return selection
    return _default_selection(catalog)


def resolve_equipment_session(database_path: str) -> EquipmentSession:
    """설비 화면 진입 — 세션 선택을 세우고(없으면 공식) 그 쌍의 합친 스냅샷을 돌려준다.

    목록·공통 최신 id·합친 본문은 모두 캐시에서 받는다 — 바뀐 것이 없는 회차는 DB 를 열지 않는다.
    고정한 쌍을 지금 공통 대장과 합칠 수 없으면(`EquipmentScenarioIncompatible` — 남이 공통을 고쳐
    옛 리비전과 부딪침) 그 시나리오 최신으로, 그것도 안 되면 공식으로 옮기고 편집본을 다시 세운 뒤
    한 번 알린다(검토 2-12). 각 시나리오 최신과 최신 공식 발행은 저장 때의 교차 검증이 늘 합쳐지게
    지키므로 공식에서도 막히면 그 예외를 그대로 낸다(화면의 「준비하지 못했습니다」).

    예외 하나 — **옛 배포 흔적**(경계 뒤 계약 v3 공통)은 교차 검증 없이 공통 최신이 된다. 그것이
    공식과도 합쳐지지 않으면 공통만 읽어 **일정 없이** 연다(`unmerged`, 선택 칸은 그대로). 멈추면
    설비 화면 어디에서도 흔적 경고와 시나리오 관리 「설비 시나리오」 구획(백업 복원 안내)에 닿을 수
    없다.
    """
    catalog = load_equipment_scenario_catalog(database_path)
    selection = _settled_selection(catalog)
    if selection is None:
        st.session_state.pop(SELECTION_KEY, None)
        session = EquipmentSession(catalog=catalog)
        st.session_state[LABEL_KEY] = session.label()
        return session
    scenario = catalog.scenario(selection[0])
    schedule_id = selection[1]
    common_id = latest_equipment_revision_id(database_path)
    snapshot: EquipmentSnapshot | None = None
    notice: str | None = None
    unmerged = False
    if common_id is not None:
        try:
            snapshot = load_merged_equipment_snapshot(database_path, common_id, schedule_id)
        except (EquipmentScenarioIncompatible, KeyError) as error:
            try:
                scenario, schedule_id, snapshot, notice = _move_after_incompatible(
                    database_path, catalog, common_id, scenario, schedule_id, error
                )
            except EquipmentScenarioIncompatible as last:
                if not catalog.legacy_trace_count:
                    raise
                snapshot = load_merged_equipment_snapshot(database_path, common_id, None)
                notice = unmerged_trace_notice(last)
                unmerged = True
    assert scenario is not None
    if not unmerged:
        _write_selection(scenario.equipment_scenario_id, schedule_id)
    session = EquipmentSession(
        catalog=catalog,
        scenario=scenario,
        schedule_revision_id=schedule_id,
        snapshot=snapshot,
        notice=notice,
        unmerged=unmerged,
    )
    st.session_state[LABEL_KEY] = session.label()
    return session


def unmerged_trace_notice(error: EquipmentScenarioIncompatible) -> str:
    """옛 배포 흔적이 공식과도 합쳐지지 않아 일정 없이 연 회차의 알림."""
    return (
        "옛 배포로 저장한 공통 대장이 설비 시나리오 일정과 합쳐지지 않아 일정 없이 열었습니다(모든 "
        f"호기가 일정 없음) — 「{error.scenario_name}」 r{error.revision_no} 일정과 합치면 "
        f"{error.reason} 설비 저장은 막혀 있고 「이대로 이어 쓰기」 도 같은 까닭으로 되지 "
        "않습니다. 런북 4-2 대로 백업을 복원하세요."
    )


def _move_after_incompatible(
    database_path: str,
    catalog: EquipmentScenarioCatalog,
    common_id: str,
    scenario: EquipmentScenarioSummary | None,
    schedule_id: str | None,
    error: Exception,
) -> tuple[EquipmentScenarioSummary, str | None, EquipmentSnapshot, str]:
    """고정 쌍이 막혔을 때 옮길 곳 — 그 시나리오 최신 → 공식. 공식도 막히면 예외를 낸다."""
    candidates: list[tuple[str, str | None]] = []
    if scenario is not None and scenario.latest_schedule_revision_id not in (None, schedule_id):
        candidates.append((scenario.equipment_scenario_id, scenario.latest_schedule_revision_id))
    official = _default_selection(catalog)
    if official is not None and official not in candidates and official[1] != schedule_id:
        candidates.append(official)
    last: Exception = error
    for candidate_scenario, candidate_schedule in candidates:
        target = catalog.scenario(candidate_scenario)
        if target is None:
            continue
        try:
            snapshot = load_merged_equipment_snapshot(database_path, common_id, candidate_schedule)
        except (EquipmentScenarioIncompatible, KeyError) as next_error:
            last = next_error
            continue
        discarded = has_unsaved_equipment_edits()
        reset_equipment_drafts(keep_fab=True)
        if isinstance(error, EquipmentScenarioIncompatible):
            before = f"「{error.scenario_name}」 r{error.revision_no}"
            reason = error.reason
        else:
            before = "고른 설비 시나리오 리비전"
            reason = "그 리비전을 찾을 수 없습니다"
        after = (
            f"「{target.scenario_name}」 r{snapshot.schedule.revision_no}"
            if snapshot.schedule is not None
            else f"「{target.scenario_name}」"
        )
        message = (
            f"{before}{object_particle(before)} 지금 공통 대장과 합칠 수 없어 "
            f"{with_direction_particle(after)} 열었습니다 — {reason}"
        )
        if discarded:
            message += " 저장하지 않은 설비 편집은 버렸습니다."
        return target, candidate_schedule, snapshot, message
    raise last


def select_equipment_scenario(
    database_path: str,
    scenario_id: str,
    schedule_revision_id: str | None,
    *,
    discard: bool,
) -> str | None:
    """팝업 「불러오기」 — 세션을 그 시나리오·리비전으로 옮긴다. 못 옮겼으면 까닭 한 줄을 돌려준다.

    저장 안 한 설비 편집이 있으면 「변경을 버리고 불러오기」(`discard`)를 체크해야 한다(결정).
    먼저 합친 스냅샷을 읽어 검증하고, 통과해야 편집본을 비우고 선택을 적는다 — 비운 뒤라 다음
    `ensure_equipment_drafts` 는 「처음 세움」 이고 「다른 사용자가 저장」 알림이 뜨지 않는다.
    미저장 FAB 전체 배치는 시나리오와 무관해 남긴다.
    """
    if has_unsaved_equipment_edits() and not discard:
        return (
            "저장하지 않은 설비 편집이 있습니다 — 「변경을 버리고 불러오기」 를 체크한 뒤 "
            "불러오세요."
        )
    catalog = load_equipment_scenario_catalog(database_path)
    target = catalog.scenario(scenario_id)
    if target is None:
        return "그 설비 시나리오를 찾을 수 없습니다 — 목록을 다시 보세요."
    common_id = latest_equipment_revision_id(database_path)
    if common_id is not None:
        try:
            load_merged_equipment_snapshot(database_path, common_id, schedule_revision_id)
        except EquipmentScenarioIncompatible as error:
            return str(error)
        except KeyError:
            return "그 리비전을 찾을 수 없습니다 — 목록을 다시 보세요."
    reset_equipment_drafts(keep_fab=True)
    _write_selection(scenario_id, schedule_revision_id)
    return None
