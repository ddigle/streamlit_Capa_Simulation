# Purpose: HOME Preference 「주요 Case」 상자 — Case1·Case2 의 시나리오·리비전을 공용 지정한다.

"""HOME `Preference` 탭의 「주요 Case」 상자(2026-10-23 사용자 요청).

HOME 슬롯은 셋으로 고정이다 — 슬롯 1 은 지금 최신 공식버전(따로 지정하지 않는다 — 공식 지정은
시나리오 관리 한 곳), 슬롯 2·3 은 여기서 고르는 Case1·Case2 다. 상자 첫 줄은 슬롯 1 을 글로만
보이고, Case 마다 「시나리오」·「리비전」 두 상자를 둔다. 고르는 것이 곧 저장이고(비교 시나리오와
같다) 값은 공용 프로필 `app_meta.global_main_cases`(마이그레이션 0036)에 Case 하나씩 짝으로
들어간다. HOME Main 의 슬롯 고르기는 시안을 고른 뒤의 2단계다 — 그쪽은
`services/main_cases.main_case_slots` 와 캐시 `load_global_main_cases` 를 쓴다.

**공용 프로필이 정본이고 상자는 그 거울이다.** 비교 시나리오는 세션 값이 보는 사람의 GAP 상태라
세션을 우선하지만, 주요 Case 는 모두가 같이 쓰는 지정이라 회차마다 프로필 값을 상자 칸에 **적는다**.

- 다른 세션이 바꾼 지정·이름이 다음 회차에 그대로 보이고,
- 선택지 글자(시나리오 이름·「r{번호} · {리비전명}」)가 바뀌어도 브라우저가 새 글자를 받으며(AGENTS
  9장 「글자가 바뀌는 것을 피할 수 없는 상자」),
- 브라우저가 옛 글자를 되보내 콜백이 그 글자를 받으면 콜백은 쓰지 않고(실제 id 가 아니다) 다음
  회차에 프로필 값으로 되돌린다.

본문이 프로필에 쓰는 것은 둘뿐이고 둘 다 프로필만 보고 정해지는 값이라 세션끼리 서로 뒤집지 않는다 —
목록에서 사라진 시나리오를 가리키는 Case 비우기(조건부 UPDATE), 리비전 칸이 그 시나리오의 것이 아닐
때 그 시나리오 첫 리비전으로 메우기(본 version 대조 — 그 사이 남이 고른 값을 덮지 않는다). 선택지
라벨에는 활성 상태를 붙이지 않는다(`_comparison_active_note` 와 같은 까닭).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.profile_caption import profile_version_caption
from capa_simulation.components.revision_label import revision_label
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence._sql_helpers import pinned_connections
from capa_simulation.persistence.cache import (
    clear_global_main_cases_cache,
    get_scenario_repository,
    load_global_main_cases,
)
from capa_simulation.persistence.models import (
    GlobalMainCases,
    OfficialReleaseSummary,
    RevisionSummary,
    ScenarioSummary,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.main_cases import (
    MAIN_CASE_NUMBERS,
    case_title,
    main_case_overlap_notes,
    official_slot_label,
)

MAIN_CASE_TITLE = "주요 Case"
MAIN_CASE_SOURCE = "HOME 주요 Case 선택"
MAIN_CASE_FILL_SOURCE = "HOME 주요 Case 리비전 메움"
# 콜백이 저장하지 못했을 때 남기는 한 줄. 다음 회차 상자 안 알림 칸이 꺼내 보인다.
MAIN_CASE_NOTICE_KEY = "home_preference_main_case_notice"
OFFICIAL_POINTER = "공식 지정은 시나리오 관리"
UNSET_CHOICE = "지정 안 함"
IDLE_REVISION_CHOICE = "시나리오를 먼저 고르세요"


def main_case_scenario_key(case_no: int) -> str:
    """Case 의 「시나리오」 상자 key."""
    return f"home_preference_case{case_no}_scenario"


def main_case_revision_key(case_no: int) -> str:
    """Case 의 「리비전」 상자 key."""
    return f"home_preference_case{case_no}_revision"


def _idle_revision_key(case_no: int) -> str:
    # 시나리오를 고르지 않은 Case 의 잠긴 자리 상자. 진짜 리비전 칸과 key 를 나눠 그 값을 건드리지
    # 않는다.
    return f"home_preference_case{case_no}_revision_idle"


@dataclass(frozen=True)
class _CasePlan:
    """한 Case 를 그릴 재료 — 본문이 프로필을 메운 뒤의 짝과 그 시나리오의 리비전 목록."""

    scenario_id: str | None
    revision_id: str | None
    revisions: tuple[RevisionSummary, ...]
    error: str | None = None


def render_main_case_picker(database_path: str) -> None:
    """「주요 Case」 상자. HOME 은 `st.tabs` 라 숨은 Preference 에서도 회차마다 돈다.

    읽기는 목록 둘(최신 공식버전·시나리오)과 Case 가 가리키는 시나리오의 리비전 목록뿐이고,
    쓰기는 위 모듈 설명의 두 메우기뿐이다.
    """
    with st.container(border=True):
        st.markdown(f"#### :material/star: {MAIN_CASE_TITLE}")
        repository = get_scenario_repository(database_path)
        try:
            official = repository.latest_official_release()
            scenarios = repository.list_scenarios()
            profile = load_global_main_cases(database_path)
        except BOOTSTRAP_ERRORS as exc:
            st.error(bootstrap_error_message(exc))
            return
        st.markdown(_official_line(official))
        # 알림은 생겼다 사라진다 — 늘 서 있는 한 칸 안에 그려 아래 상자의 자리를 고정한다(AGENTS
        # 9장).
        notice_slot = st.container()
        notices: list[str] = []
        callback_notice = st.session_state.pop(MAIN_CASE_NOTICE_KEY, None)
        if isinstance(callback_notice, str):
            notices.append(callback_notice)
        scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
        profile = _drop_vanished_scenarios(
            repository, database_path, profile, scenario_by_id, notices
        )
        plans: dict[int, _CasePlan] = {}
        for case_no in MAIN_CASE_NUMBERS:
            plan, profile = _plan_case(repository, profile, case_no, scenario_by_id)
            plans[case_no] = plan
        with notice_slot:
            for notice in notices:
                st.warning(notice, icon=":material/info:")
        for case_no, column in zip(
            MAIN_CASE_NUMBERS, st.columns(len(MAIN_CASE_NUMBERS)), strict=True
        ):
            with column:
                _render_case(database_path, case_no, plans[case_no], scenario_by_id)
        notes = main_case_overlap_notes(
            official_revision_id=None if official is None else official.revision_id,
            cases=[(plans[n].scenario_id, plans[n].revision_id) for n in MAIN_CASE_NUMBERS],
        )
        with st.container():
            for note in notes:
                st.caption(note)
        st.caption(profile_version_caption(profile, empty="아직 지정한 주요 Case 가 없습니다."))


def _official_line(official: OfficialReleaseSummary | None) -> str:
    """상자 첫 줄 — 슬롯 1 은 지정하지 않고 지금 최신 공식버전을 글로만 보인다."""
    label = "아직 없음" if official is None else literal_markdown(official_slot_label(official))
    return f":material/verified: 슬롯 1 · 공식버전: **{label}** ({OFFICIAL_POINTER})"


def _drop_vanished_scenarios(
    repository: DuckDBScenarioRepository,
    database_path: str,
    profile: GlobalMainCases,
    scenario_by_id: dict[str, ScenarioSummary],
    notices: list[str],
) -> GlobalMainCases:
    """목록(보관본 빼고)에 없는 시나리오를 가리키는 Case 를 비운다.

    보관·영구 삭제는 저장소가 같은 트랜잭션에서 비우므로 여기 닿는 것은 그 밖의 길로 남은 값이다.
    상자는 그 값을 선택지에 둘 수 없어(위젯이 죽는다) 「지정 안 함」으로 보이는데, 프로필에 남겨
    두면 「지정 안 함」 을 다시 골라도 값이 바뀌지 않아 지울 길이 없다. 조건부 UPDATE 라 여러 세션이
    함께 불러도 같다.
    """
    vanished = {
        scenario_id
        for case_no in MAIN_CASE_NUMBERS
        if (scenario_id := profile.case(case_no)[0]) is not None
        and scenario_id not in scenario_by_id
    }
    if not vanished:
        return profile
    try:
        for scenario_id in sorted(vanished):
            repository.clear_global_main_case_scenario(scenario_id)
    except BOOTSTRAP_ERRORS:
        return profile
    clear_global_main_cases_cache()
    for case_no in MAIN_CASE_NUMBERS:
        if profile.case(case_no)[0] in vanished:
            notices.append(
                f"{case_title(case_no)} 에 지정했던 시나리오가 목록에 없어(보관·삭제) "
                "지정을 비웠습니다."
            )
    try:
        return load_global_main_cases(database_path)
    except BOOTSTRAP_ERRORS:
        return profile


def _plan_case(
    repository: DuckDBScenarioRepository,
    profile: GlobalMainCases,
    case_no: int,
    scenario_by_id: dict[str, ScenarioSummary],
) -> tuple[_CasePlan, GlobalMainCases]:
    """Case 하나의 리비전 목록을 읽고, 리비전 칸이 그 시나리오의 것이 아니면 첫 리비전으로 메운다.

    시나리오 상자의 콜백이 첫 리비전까지 짝으로 저장하므로 보통은 메울 것이 없다. 남는 것은 리비전
    칸이 빈 채 저장된 값(스크립트 등)과 어긋난 짝이다. **본 version 을 대조해 쓴다** — 그 사이 남이
    고른 값을 이쪽 회차가 본 옛 값으로 덮지 않는다(어긋나면 쓰지 않고 다음 회차가 새 프로필로 다시
    본다).
    """
    scenario_id, revision_id = profile.case(case_no)
    if scenario_id is None or scenario_id not in scenario_by_id:
        # 목록에 없는 시나리오(비우기가 실패한 회차)를 상자 값으로 적으면 위젯이 죽는다 — 비운
        # 것으로 그린다.
        return _CasePlan(None, None, ()), profile
    try:
        revisions = tuple(repository.list_revisions(scenario_id))
    except BOOTSTRAP_ERRORS as exc:
        return _CasePlan(scenario_id, revision_id, (), bootstrap_error_message(exc)), profile
    known = {revision.revision_id for revision in revisions}
    if not revisions or revision_id in known:
        return _CasePlan(scenario_id, revision_id, revisions), profile
    first = revisions[0].revision_id
    try:
        profile = repository.replace_global_main_case(
            case_no,
            scenario_id,
            first,
            source=MAIN_CASE_FILL_SOURCE,
            expected_version=profile.version,
        )
    except BOOTSTRAP_ERRORS:
        # 다른 세션이 먼저 썼거나 잠겼다. 이번 회차 상자는 첫 리비전을 보이고 다음 회차가 다시 본다.
        return _CasePlan(scenario_id, first, revisions), profile
    clear_global_main_cases_cache()
    return _CasePlan(scenario_id, first, revisions), profile


def _render_case(
    database_path: str,
    case_no: int,
    plan: _CasePlan,
    scenario_by_id: dict[str, ScenarioSummary],
) -> None:
    """Case 한 칸 — 머리 줄과 「시나리오」·「리비전」 두 상자.

    상자 값은 위젯 앞에서 매 회차 프로필 값으로 적는다.
    """
    st.markdown(f"**슬롯 {case_no + 1} · {case_title(case_no)}**")
    scenario_key = main_case_scenario_key(case_no)
    revision_key = main_case_revision_key(case_no)
    # 적기는 `on_change` 를 부르지 않아 프로필을 다시 쓰지 않는다. 목록에 없는 값은 앞에서 비웠다.
    st.session_state[scenario_key] = plan.scenario_id
    st.selectbox(
        "시나리오",
        options=[None, *scenario_by_id],
        format_func=lambda value: _scenario_choice_label(scenario_by_id, value),
        key=scenario_key,
        on_change=_save_case_scenario,
        args=(database_path, case_no),
    )
    if plan.scenario_id is None:
        st.session_state.pop(revision_key, None)
        st.selectbox(
            "리비전",
            options=[None],
            format_func=lambda _value: IDLE_REVISION_CHOICE,
            key=_idle_revision_key(case_no),
            disabled=True,
        )
        return
    if plan.error is not None:
        st.error(plan.error)
        return
    if not plan.revisions:
        st.session_state.pop(revision_key, None)
        st.info("고른 시나리오에 저장된 리비전이 없습니다.")
        return
    revision_by_id = {revision.revision_id: revision for revision in plan.revisions}
    st.session_state[revision_key] = plan.revision_id
    st.selectbox(
        "리비전",
        options=list(revision_by_id),
        format_func=lambda value: revision_label(revision_by_id[value]),
        key=revision_key,
        on_change=_save_case_revision,
        args=(database_path, case_no),
    )


def _scenario_choice_label(scenarios: dict[str, ScenarioSummary], value: str | None) -> str:
    """선택지 글자 — 시나리오 이름뿐이다. 활성 상태 등 회차마다 바뀌는 것은 붙이지 않는다."""
    if value is None:
        return UNSET_CHOICE
    return scenarios[value].scenario_name


def _save_case_scenario(database_path: str, case_no: int) -> None:
    """「시나리오」 상자의 콜백. 고른 시나리오를 **그 첫 리비전과 짝으로** 저장한다.

    위젯 기본값은 `on_change` 를 부르지 않는다 — 시나리오만 저장하면 뒤이어 서는 리비전 상자의
    기본값은 세션에만 들어가 프로필에 남지 않는다(비교 시나리오가 `_persist_comparison_choice` 로
    메우던 자리). 여기서 선택 상자의 첫 항목(최신 리비전)을 함께 적어 한 번에 짝을 맞춘다. 「지정 안
    함」은 두 칸을 함께 비운다.
    """
    chosen = st.session_state.get(main_case_scenario_key(case_no))
    _replace_case(database_path, case_no, lambda repository: _scenario_pair(repository, chosen))


def _save_case_revision(database_path: str, case_no: int) -> None:
    """「리비전」 상자의 콜백. 고른 리비전이 고른 시나리오의 것일 때만 저장한다."""
    scenario_id = st.session_state.get(main_case_scenario_key(case_no))
    revision_id = st.session_state.get(main_case_revision_key(case_no))
    _replace_case(
        database_path,
        case_no,
        lambda repository: _revision_pair(repository, scenario_id, revision_id),
    )


def _replace_case(
    database_path: str,
    case_no: int,
    choose: Callable[[DuckDBScenarioRepository], tuple[str | None, str | None] | None],
) -> None:
    """`choose` 가 낸 짝을 그 Case 에 쓴다. 짝이 없거나(id 가 아니다) 프로필과 같으면 쓰지 않는다.

    콜백은 `app.py` 의 실행 핀 밖(본문 전)에서 돈다 — 목록 읽기·프로필 읽기·쓰기가 연결마다 DuckDB
    인스턴스를 새로 만들지 않게 여기서 핀을 잡는다(`home_preference._replace_comparison_profile` 와
    같다). 프로필은 캐시가 아니라 DB 에서 읽어 견준다 — 같은 짝을 다시 쓰면 아무도 바꾸지 않았는데
    version 이 오른다. 저장에 실패하면 다음 회차 상자 안에 한 줄 남긴다(상자는 프로필 값으로
    돌아간다).
    """
    with pinned_connections(Path(database_path)):
        try:
            repository = get_scenario_repository(database_path)
            chosen = choose(repository)
            if chosen is None:
                return
            if repository.load_global_main_cases().case(case_no) == chosen:
                return
            repository.replace_global_main_case(case_no, *chosen, source=MAIN_CASE_SOURCE)
        except BOOTSTRAP_ERRORS as exc:
            st.session_state[MAIN_CASE_NOTICE_KEY] = (
                f"{case_title(case_no)} 지정을 저장하지 못했습니다 — {bootstrap_error_message(exc)}"
            )
            return
    clear_global_main_cases_cache()


def _scenario_pair(
    repository: DuckDBScenarioRepository, scenario_id: object
) -> tuple[str | None, str | None] | None:
    """시나리오 상자가 받은 값의 저장할 짝. 활성 시나리오 id 가 아니면(되보낸 라벨 등) `None`."""
    if scenario_id is None:
        return None, None
    chosen = str(scenario_id)
    if chosen not in {scenario.scenario_id for scenario in repository.list_scenarios()}:
        return None
    revisions = repository.list_revisions(chosen)
    return chosen, (revisions[0].revision_id if revisions else None)


def _revision_pair(
    repository: DuckDBScenarioRepository, scenario_id: object, revision_id: object
) -> tuple[str | None, str | None] | None:
    """리비전 상자가 받은 값의 저장할 짝. 고른 시나리오의 실제 리비전이 아니면 `None`."""
    if scenario_id is None or revision_id is None:
        return None
    chosen_scenario, chosen_revision = str(scenario_id), str(revision_id)
    if chosen_scenario not in {scenario.scenario_id for scenario in repository.list_scenarios()}:
        return None
    revision_ids = {revision.revision_id for revision in repository.list_revisions(chosen_scenario)}
    if chosen_revision not in revision_ids:
        return None
    return chosen_scenario, chosen_revision
