# Purpose: 가용설비 현황 「설비 시나리오」 탭의 표와 불러오기·복제·이름·발행·이어 쓰기를 그린다.

"""가용설비 현황 「설비 시나리오」 탭(E8 — 1단계 몫, 설계 6-2).

- **시나리오 표**: 이름·상태(공식 vN / 활성)·최신 rN·리비전 수·최근 저장·저장자.
- **리비전 표**: 고른 시나리오의 일정 리비전(r·저장시각·저장자·출처·공통 rN·호기 행·비가동 행·메모).
- **작업 넷**(고른 리비전에): 「이 리비전 불러오기」(세션을 옮김 — 미저장이면 「변경을 버리고
  불러오기」), 「복제해 새 시나리오」(출처 = 그 시나리오 최신 / 공식 발행 리비전 — 만들기는
  복제로만), 「이름 바꾸기」, 「공식으로 발행」(지금 공식 → 새 공식을 나란히, 최신이 아니면 그
  사실도).
- **옛 배포 흔적**이 있을 때만 「이대로 이어 쓰기」(설비 저장 막기를 푼다 — 백업 복원 대신). 확인
  체크(빠지는 호기 수)를 켜야 단추가 서고, 옛 배포 리비전이 일정과 합쳐지지 않으면 단추 대신 백업
  복원 안내만 선다.

목록·리비전은 설비 시나리오 목록 캐시(세대·stat·TTL)에서 받는다 — 이 탭을 그리는 회차에만 읽는다.
쓰기(복제·이름·발행·이어 쓰기)는 저장소가 하고 그 뒤 `clear_equipment_scenario_cache()` 를 부른다
(저장소는 캐시 경계를 모른다). 2단계(보관·삭제·순서·공통 이력·되돌리기·비교)는 짓지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import streamlit as st

from capa_simulation.components.equipment_data_workspace import (
    ORIGIN_WORDS,
    has_unsaved_equipment_edits,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.equipment_scenario_activation import (
    EquipmentSession,
    select_equipment_scenario,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message, prune_choice
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_scenario_cache,
    get_equipment_repository,
    latest_equipment_revision_id,
    load_equipment_revision_summaries,
    load_equipment_schedule_revisions,
    load_legacy_trace_review,
)
from capa_simulation.persistence.equipment_repository import (
    EquipmentRelease,
    EquipmentScenarioSummary,
    EquipmentScheduleRevisionSummary,
    LegacyTraceReview,
    legacy_trace_message,
)
from capa_simulation.services.korean_particle import object_particle

__all__ = ["render_equipment_scenario_management"]

SCENARIO_KEY = "equipment_scenario_manage_scenario_v1"
REVISION_KEY = "equipment_scenario_manage_revision_v1"
DISCARD_KEY = "equipment_scenario_manage_discard_v1"
LOAD_BUTTON_KEY = "equipment_scenario_manage_load_v1"
CLONE_SOURCE_KEY = "equipment_scenario_manage_clone_source_v1"
CLONE_NAME_KEY = "equipment_scenario_manage_clone_name_v1"
CLONE_BY_KEY = "equipment_scenario_manage_clone_by_v1"
CLONE_BUTTON_KEY = "equipment_scenario_manage_clone_v1"
RENAME_KEY = "equipment_scenario_manage_rename_v1"
RENAME_BUTTON_KEY = "equipment_scenario_manage_rename_button_v1"
PUBLISH_BY_KEY = "equipment_scenario_manage_publish_by_v1"
PUBLISH_NOTE_KEY = "equipment_scenario_manage_publish_note_v1"
PUBLISH_BUTTON_KEY = "equipment_scenario_manage_publish_v1"
CONTINUE_BUTTON_KEY = "equipment_scenario_manage_continue_v1"
CONTINUE_CONFIRM_KEY = "equipment_scenario_manage_continue_confirm_v1"
# 이 탭 작업 알림 — 다음 회차에 한 번, 탭 맨 위.
FLASH_KEY = "equipment_scenario_manage_flash_v1"
# 입력 칸 세대 — 쓰기에 성공한 회차에 올라 다음 회차에 빈 칸으로 선다(옛 값을 되보내지 않게).
GENERATION_KEY = "equipment_scenario_manage_generation_v1"

_LATEST = "latest"
_OFFICIAL = "official"


def _generation() -> int:
    value = st.session_state.get(GENERATION_KEY, 0)
    return value if isinstance(value, int) else 0


def _keyed(base: str) -> str:
    generation = _generation()
    return base if generation == 0 else f"{base}__g{generation}"


def _written(message: str) -> None:
    """쓰기 뒤 — 목록 캐시를 비우고 알림을 남기고 입력 칸을 새로 세운 뒤 다시 돈다."""
    clear_equipment_scenario_cache()
    st.session_state[FLASH_KEY] = message
    st.session_state[GENERATION_KEY] = _generation() + 1
    st.rerun()


def scenario_rows(session: EquipmentSession) -> pd.DataFrame:
    """시나리오 표 — 이름·상태·최신·리비전 수. 공식은 「공식 vN」, 그 밖은 「활성」."""
    official_id = session.catalog.official_scenario_id
    release_no = session.catalog.release_no
    return pd.DataFrame(
        [
            {
                "설비 시나리오": item.scenario_name,
                "상태": (
                    f"공식 v{release_no}"
                    if item.equipment_scenario_id == official_id and release_no is not None
                    else "활성"
                ),
                "최신": f"r{item.latest_revision_no}" if item.latest_revision_no else "",
                "리비전 수": item.revision_count,
                "올라와 있음": "●" if item.equipment_scenario_id == session.scenario_id else "",
            }
            for item in session.catalog.scenarios
        ]
    )


def revision_rows(
    revisions: Sequence[EquipmentScheduleRevisionSummary],
    *,
    common_numbers: dict[str, int],
    official_id: str | None,
    official_no: int | None,
) -> pd.DataFrame:
    """리비전 표 — r·저장시각·저장자·출처·공통 rN·호기 행·비가동 행·공식·메모."""
    return pd.DataFrame(
        [
            {
                "리비전": f"r{item.revision_no}",
                "저장시각": item.created_at,
                "저장자": item.saved_by,
                "출처": ORIGIN_WORDS.get(item.origin, item.origin),
                "공통": (
                    f"r{common_numbers[item.common_revision_id]}"
                    if item.common_revision_id in common_numbers
                    else ""
                ),
                "호기행": item.unit_row_count,
                "비가동행": item.downtime_row_count,
                "공식": (
                    f"v{official_no}"
                    if official_no is not None and item.schedule_revision_id == official_id
                    else ""
                ),
                "메모": item.note,
            }
            for item in revisions
        ]
    )


def render_equipment_scenario_management(database_path: str, session: EquipmentSession) -> None:
    """탭 본문. 숨은 탭이면 부르지 않는다(페이지가 가린다) — 입력은 위젯이 세션에 지킨다."""
    flash = st.session_state.pop(FLASH_KEY, None)
    if isinstance(flash, str):
        st.success(flash)
    if session.legacy_trace_count:
        _render_legacy_trace(database_path, session.legacy_trace_count)
    scenarios = {item.equipment_scenario_id: item for item in session.catalog.scenarios}
    if not scenarios:
        st.info(
            "설비 시나리오가 없습니다. RawData 에서 첫 설비 데이터를 저장하면 「운영 일정」이 "
            "섭니다."
        )
        return
    st.caption(
        "공통 칸(호기 정보·실적·상태·Space 실물)은 모든 설비 시나리오가 함께 씁니다. 설비 "
        "시나리오는 일정 여섯·시나리오 메모·비가동만 따로 듭니다 — 만들기는 복제로만 합니다."
    )
    st.dataframe(scenario_rows(session), hide_index=True, width="stretch", placeholder="")
    default_scenario = (
        session.scenario_id if session.scenario_id in scenarios else next(iter(scenarios))
    )
    selected_id = prune_choice(SCENARIO_KEY, list(scenarios), default=default_scenario)
    st.selectbox(
        "설비 시나리오",
        options=list(scenarios),
        format_func=lambda value: scenarios[value].scenario_name,
        key=SCENARIO_KEY,
    )
    scenario = scenarios[selected_id]
    try:
        revisions = load_equipment_schedule_revisions(database_path, selected_id)
        latest_common = latest_equipment_revision_id(database_path)
        common_numbers = {
            item.revision_id: item.revision_no
            for item in load_equipment_revision_summaries(database_path, latest_common)
        }
    except BOOTSTRAP_ERRORS as exc:
        st.error(f"리비전 목록을 읽지 못했습니다: {bootstrap_error_message(exc)}")
        return
    release = session.catalog.latest_release
    official_id = release.schedule_revision_id if release is not None else None
    official_no = release.release_no if release is not None else None
    if not revisions:
        st.info("이 설비 시나리오에 저장된 리비전이 없습니다.")
        return
    st.dataframe(
        revision_rows(
            revisions,
            common_numbers=common_numbers,
            official_id=official_id,
            official_no=official_no,
        ),
        hide_index=True,
        width="stretch",
        placeholder="",
        column_config={"저장시각": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")},
    )
    by_id = {item.schedule_revision_id: item for item in revisions}
    default_revision = (
        scenario.latest_schedule_revision_id
        if scenario.latest_schedule_revision_id in by_id
        else next(iter(by_id))
    )
    chosen_id = prune_choice(REVISION_KEY, list(by_id), default=default_revision)
    st.selectbox(
        "리비전",
        options=list(by_id),
        format_func=lambda value: _revision_label(
            by_id[value], official_id=official_id, official_no=official_no
        ),
        key=REVISION_KEY,
    )
    chosen = by_id[chosen_id]
    with st.container(horizontal=True, gap="small"):
        with st.popover("이 리비전 불러오기", icon=":material/download:"):
            _render_load(database_path, scenario, chosen)
        with st.popover("복제해 새 시나리오", icon=":material/content_copy:"):
            _render_clone(database_path, scenario, release=release)
        with st.popover("이름 바꾸기", icon=":material/edit:"):
            _render_rename(database_path, scenario)
        with st.popover("공식으로 발행", icon=":material/verified:"):
            _render_publish(database_path, session, scenario, chosen)


def _revision_label(
    revision: EquipmentScheduleRevisionSummary, *, official_id: str | None, official_no: int | None
) -> str:
    parts = [f"r{revision.revision_no}", f"{revision.created_at:%y.%m.%d %H:%M}"]
    if official_no is not None and revision.schedule_revision_id == official_id:
        parts.append(f"공식 v{official_no}")
    if revision.note:
        parts.append(revision.note.replace("\n", " ")[:40])
    return " · ".join(parts)


def _render_load(
    database_path: str,
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
) -> None:
    name = literal_markdown(scenario.scenario_name)
    st.caption(f"「{name}」 r{revision.revision_no} 을 이 세션의 설비 시나리오로 올립니다.")
    discard = True
    if has_unsaved_equipment_edits():
        discard = st.checkbox("변경을 버리고 불러오기", key=DISCARD_KEY)
    if st.button(
        "불러오기", type="primary", disabled=not discard, key=LOAD_BUTTON_KEY, width="stretch"
    ):
        failure = select_equipment_scenario(
            database_path,
            scenario.equipment_scenario_id,
            revision.schedule_revision_id,
            discard=discard,
        )
        if failure is not None:
            st.error(failure)
            return
        st.session_state[FLASH_KEY] = (
            f"설비 시나리오 「{name}」 r{revision.revision_no} 을 불러왔습니다."
        )
        st.rerun()


def _render_clone(
    database_path: str,
    scenario: EquipmentScenarioSummary,
    *,
    release: EquipmentRelease | None,
) -> None:
    """복제 — 출처는 그 시나리오의 최신, 또는 그 시나리오가 공식이면 공식 발행 리비전."""
    sources: dict[str, tuple[str, str]] = {}
    if scenario.latest_schedule_revision_id is not None:
        sources[_LATEST] = (
            scenario.latest_schedule_revision_id,
            f"최신 r{scenario.latest_revision_no}",
        )
    if (
        release is not None
        and release.equipment_scenario_id == scenario.equipment_scenario_id
        and release.schedule_revision_id != scenario.latest_schedule_revision_id
    ):
        sources[_OFFICIAL] = (release.schedule_revision_id, f"공식 v{release.release_no}")
    if not sources:
        st.info("복제할 리비전이 없습니다.")
        return
    prune_choice(CLONE_SOURCE_KEY, list(sources), default=next(iter(sources)))
    source = st.radio(
        "출처",
        options=list(sources),
        format_func=lambda value: sources[value][1],
        key=CLONE_SOURCE_KEY,
        horizontal=True,
    )
    name = st.text_input(
        "새 설비 시나리오 이름", key=_keyed(CLONE_NAME_KEY), placeholder="예: 셋업 실무"
    )
    saved_by = st.text_input("만든 사람(선택)", key=_keyed(CLONE_BY_KEY))
    st.caption(
        "새 시나리오 r1 은 출처의 일정·시나리오 메모·비가동을 지금 공통 대장과 합쳐 그대로 "
        "옮깁니다."
    )
    if st.button("복제", type="primary", key=CLONE_BUTTON_KEY, width="stretch"):
        try:
            created = get_equipment_repository(database_path).clone_equipment_scenario(
                sources[str(source)][0], name=name, created_by=saved_by or None
            )
        except BOOTSTRAP_ERRORS as exc:
            st.error(f"복제하지 못했습니다: {bootstrap_error_message(exc)}")
            return
        _written(
            f"설비 시나리오 「{literal_markdown(created.scenario_name)}」 r1 을 만들었습니다 — "
            "사이드바 설비 시나리오 줄이나 이 탭의 「이 리비전 불러오기」로 올립니다."
        )


def _render_rename(database_path: str, scenario: EquipmentScenarioSummary) -> None:
    key = f"{_keyed(RENAME_KEY)}__{scenario.equipment_scenario_id}"
    if key not in st.session_state:
        st.session_state[key] = scenario.scenario_name
    name = st.text_input("이름", key=key)
    if st.button("이름 바꾸기", type="primary", key=RENAME_BUTTON_KEY, width="stretch"):
        try:
            renamed = get_equipment_repository(database_path).rename_equipment_scenario(
                scenario.equipment_scenario_id,
                name=name,
                expected_name=scenario.scenario_name,
            )
        except BOOTSTRAP_ERRORS as exc:
            st.error(f"이름을 바꾸지 못했습니다: {bootstrap_error_message(exc)}")
            return
        _written(
            f"설비 시나리오 이름을 「{literal_markdown(renamed.scenario_name)}」 으로 했습니다."
        )


def publish_preview(
    session: EquipmentSession,
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
) -> list[str]:
    """발행 전에 보일 줄 — 지금 공식 → 새 공식, 고른 리비전이 그 시나리오 최신이 아니면 그 사실."""
    release = session.catalog.latest_release
    current = "공식 발행 없음"
    if release is not None:
        official = session.catalog.scenario(release.equipment_scenario_id)
        official_name = official.scenario_name if official is not None else "?"
        official_revision = _revision_no(session, release.schedule_revision_id, official)
        current = f"지금 공식 v{release.release_no} · 「{literal_markdown(official_name)}」" + (
            f" r{official_revision}" if official_revision is not None else ""
        )
    next_no = (release.release_no if release is not None else 0) + 1
    lines = [
        f"{current} → 새 공식 v{next_no} · 「{literal_markdown(scenario.scenario_name)}」 "
        f"r{revision.revision_no}"
    ]
    if revision.schedule_revision_id != scenario.latest_schedule_revision_id:
        lines.append(
            f"r{revision.revision_no} 은 「{literal_markdown(scenario.scenario_name)}」 의 최신"
            f"(r{scenario.latest_revision_no})이 아닙니다."
        )
    if release is not None and release.schedule_revision_id == revision.schedule_revision_id:
        lines.append("이미 공식 발행인 리비전입니다 — 발행해도 바뀌지 않습니다.")
    return lines


def _revision_no(
    session: EquipmentSession,
    schedule_revision_id: str,
    scenario: EquipmentScenarioSummary | None,
) -> int | None:
    if scenario is None:
        return None
    if scenario.latest_schedule_revision_id == schedule_revision_id:
        return scenario.latest_revision_no
    if session.snapshot is not None and session.snapshot.schedule is not None:
        if session.snapshot.schedule.schedule_revision_id == schedule_revision_id:
            return session.snapshot.schedule.revision_no
    return None


def _render_publish(
    database_path: str,
    session: EquipmentSession,
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
) -> None:
    for line in publish_preview(session, scenario, revision):
        st.caption(line)
    st.caption(
        "공식은 Space·새 세션·공정 Capa 상세(HOME 칸)·진척 비교 기준선이 보는 설비 시나리오입니다. "
        "발행은 append-only 입니다."
    )
    released_by = st.text_input("발행자(선택)", key=_keyed(PUBLISH_BY_KEY))
    note = st.text_input("발행 메모(선택)", key=_keyed(PUBLISH_NOTE_KEY))
    if st.button("공식으로 발행", type="primary", key=PUBLISH_BUTTON_KEY, width="stretch"):
        try:
            published = get_equipment_repository(database_path).publish_equipment_release(
                revision.schedule_revision_id,
                released_by=released_by or None,
                note=note or None,
                expected_latest_release_no=session.catalog.release_no,
            )
        except BOOTSTRAP_ERRORS as exc:
            st.error(f"발행하지 못했습니다: {bootstrap_error_message(exc)}")
            return
        _written(
            f"공식 v{published.release_no} 으로 발행했습니다 — 「"
            f"{literal_markdown(scenario.scenario_name)}」 r{revision.revision_no}."
        )


def continue_confirm_label(review: LegacyTraceReview) -> str:
    """「이대로 이어 쓰기」 확인 체크 글 — 무엇을 잃는지 수로 적는다(설계 2-4)."""
    revision = (
        f"옛 배포 리비전 r{review.trace_revision_no}"
        if review.trace_revision_no
        else "옛 배포 리비전"
    )
    dropped = (
        f" 지금 공통 대장의 호기 {review.dropped_units:,}대가 그 리비전에 없어 모든 설비 "
        "시나리오에서 빠지고(그 일정·비가동은 고아가 됩니다),"
        if review.dropped_units
        else ""
    )
    return (
        f"{revision}{object_particle(revision)} 공통 대장 최신으로 받아들입니다 —{dropped} 옛 "
        "배포에서 고친 일정은 들어오지 않습니다. 백업 복원 대신 이대로 이어 씁니다."
    )


def _render_legacy_trace(database_path: str, count: int) -> None:
    """옛 배포 흔적 — 경고와 「이대로 이어 쓰기」(확인 체크 뒤, 흔적 수를 대조해 이관 경계를
    덧붙인다). 이어 쓰기는 append-only 라 되돌릴 수 없다 — 빠지는 호기 수를 체크 글에 적고, 옛 배포
    리비전이 어느 시나리오 일정과도 합쳐지지 않으면 단추를 끄고 백업 복원만 남긴다."""
    st.warning(legacy_trace_message(count), icon=":material/history:")
    try:
        review = load_legacy_trace_review(database_path)
    except BOOTSTRAP_ERRORS as exc:
        st.error(f"옛 배포 흔적을 읽지 못했습니다: {bootstrap_error_message(exc)}")
        return
    if review.refusal is not None:
        st.error(
            "옛 배포로 저장한 공통 대장이 설비 시나리오 일정과 합쳐지지 않아 이어 쓸 수 없습니다 — "
            f"{literal_markdown(review.refusal)} 런북 4-2 대로 백업을 복원하세요.",
            icon=":material/block:",
        )
        return
    st.caption(
        "백업을 복원할 수 있으면 복원이 먼저입니다(런북 4-2). 이어 쓰기는 되돌릴 수 없습니다."
    )
    agreed = st.checkbox(continue_confirm_label(review), key=_keyed(CONTINUE_CONFIRM_KEY))
    if st.button(
        "이대로 이어 쓰기",
        icon=":material/fast_forward:",
        key=CONTINUE_BUTTON_KEY,
        disabled=not agreed,
    ):
        try:
            get_equipment_repository(database_path).acknowledge_legacy_trace(
                expected_trace_count=count, note="이대로 이어 쓰기"
            )
        except BOOTSTRAP_ERRORS as exc:
            st.error(f"이어 쓰지 못했습니다: {bootstrap_error_message(exc)}")
            return
        _written("옛 배포 흔적을 확인했습니다 — 설비 저장을 다시 할 수 있습니다.")
