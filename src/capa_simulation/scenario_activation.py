# Purpose: Atomically activate a persisted scenario revision in the current browser session.

"""Atomically activate a persisted scenario revision in the current browser session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast

import pandas as pd
import streamlit as st

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.home_state import HOME_TOGGLE_DEFAULTS
from capa_simulation.io.reference_cache import (
    HOME_FIGURE_CACHE_KEY,
    activate_persisted_reference_tables,
    clear_persisted_reference_tables,
)
from capa_simulation.persistence.cache import (
    get_scenario_repository,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import ScenarioSnapshot
from capa_simulation.scenario_preset_state import queue_scenario_preset
from capa_simulation.scenario_state import (
    ACTIVE_SCENARIO_KEY,
    ActiveScenario,
    activate_scenario_tables,
    clear_active_scenario,
    reset_active_scenario,
)
from capa_simulation.services.month_filter import available_month_range

ACTIVE_PERSISTED_SCENARIO_ID_KEY = "active_persisted_scenario_id"
ACTIVE_PERSISTED_REVISION_ID_KEY = "active_persisted_revision_id"
ACTIVE_PERSISTED_SESSION_REVISION_KEY = "active_persisted_session_revision"
OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY = "official_scenario_bootstrap_attempted"
# 머리 띠가 「지금 이 세션에 적용 중인 시나리오」를 적을 값. 활성화할 때 한 번 스냅샷에서 떠 두고
# 회차마다는 이것만 읽는다 — HOME 의 회차가 DB 를 다시 보거나 캐시된 스냅샷(표 전체를 매번
# 역직렬화한다)을 꺼내지 않게 한다(2026-10-03 사용자 원칙). 핫리로드 뒤에도 읽히게 클래스가
# 아니라 평범한 dict 로 둔다.
ACTIVE_SCENARIO_LABEL_KEY = "active_scenario_label"

# HOME 토글 키와 기본값은 UI 의존성이 없는 `home_state` 에서 함께 가져온다. 화면 모듈을
# 거꾸로 import 하지 않아 순환이 없고, 키를 바꾸거나 토글을 추가해도 초기화가 함께 바뀐다.
# Figure 캐시 키도 `io/reference_cache` 의 선언 한 곳을 쓴다.
#
# 담는 것은 두 가지다.
#
# 1. **앞 시나리오의 값이 담긴 칸.** 지우지 않으면 새 시나리오 화면에 옛 수치가 그려진다.
# 2. **HOME 의 토글 전부.** 토글은 모두 기준정보 위에 무언가를 얹거나 빼는 스위치이고,
#    켠 사람은 **그 시나리오**를 보며 켰다. 켠 채로 시나리오를 바꾸면 얹힌 것이 새 계획
#    위에 그대로 남는데 — 실행 Capa 증감은 확보율을 통해 B/N 순위·Top5 막대·히트맵까지
#    바꾼다 — 화면에는 토글이 켜져 있으니 사용자는 그것을 새 시나리오의 원래 값으로 읽는다.
#    새 시나리오는 있는 그대로 먼저 보이고, 얹을 것은 사용자가 다시 켠다.
#
# 탭과 조회 조건(필터·분류 수준)은 **넣지 않는다.** 그것들은 무엇을 보고 있는지일 뿐 값에
# 닿지 않으므로, 지우면 시나리오를 바꿀 때마다 보던 자리를 다시 찾아야 한다.
#
# 「HOME 의 토글 전부」를 손으로 세지 않는다. `tests/test_scenario_activation.py` 가
# `home_preference` 의 토글 키를 훑어 빠진 것을 잡는다 — 「실행 Loss」가 나중에 추가되면서
# 목록에 들어오지 않아 이 규칙이 한동안 반쪽이었던 적이 있다.
_STALE_UI_KEYS = (
    "load_conversion_source_token",
    "reference_data_source_token",
    "load_conversion_own_change",
    "reference_data_own_change",
    HOME_FIGURE_CACHE_KEY,
    *HOME_TOGGLE_DEFAULTS,
)


@dataclass(frozen=True)
class ActiveScenarioLabel:
    """머리 띠에 적는 활성 시나리오의 이름표. 값은 활성화한 스냅샷에서 한 번 떠 둔 것이다."""

    scenario_id: str
    revision_id: str
    scenario_name: str
    simulation_code: str
    source_type: str
    # 원천 등록시점. 원천에 등록시점이 없으면(내장 시드·CSV·복제) 시나리오를 만든 시각이다.
    registered_at: datetime
    revision_no: int
    revision_name: str
    # 리비전을 저장한 시각.
    saved_at: datetime
    # 시나리오 기간 — 생산계획(`RQ_PKG_PLAN`)에 있는 첫 달·끝 달. 조회기간과 다르다.
    first_month: int | None
    last_month: int | None


def _plan_months(snapshot: ScenarioSnapshot) -> tuple[int | None, int | None]:
    plan = snapshot.tables.get("RQ_PKG_PLAN")
    if plan is None:
        return None, None
    try:
        first, last = available_month_range(plan, "RQ_PKG_PLAN")
    except (ValueError, TypeError):
        # 계획이 비었거나 월이 없는 리비전도 활성화는 된다. 머리 띠는 기간만 빼고 적는다.
        return None, None
    return first, last


def _remember_label(snapshot: ScenarioSnapshot) -> None:
    scenario = snapshot.scenario
    revision = snapshot.revision
    first, last = _plan_months(snapshot)
    st.session_state[ACTIVE_SCENARIO_LABEL_KEY] = {
        "scenario_id": scenario.scenario_id,
        "revision_id": revision.revision_id,
        "scenario_name": scenario.scenario_name,
        "simulation_code": scenario.source_simulation_code,
        "source_type": scenario.source_type,
        "registered_at": scenario.source_registered_at or scenario.created_at,
        "revision_no": revision.revision_no,
        "revision_name": revision.revision_name,
        "saved_at": revision.created_at,
        "first_month": first,
        "last_month": last,
    }


def active_scenario_label() -> ActiveScenarioLabel | None:
    """이 세션에 올라와 있는 리비전의 이름표. 아직 활성화하지 않았거나 값이 어긋나면 `None`.

    세션만 읽는다(DB·캐시를 보지 않는다). 이름표의 리비전이 지금 활성 리비전과 다르면 믿지 않는다.
    """
    held = st.session_state.get(ACTIVE_SCENARIO_LABEL_KEY)
    if not isinstance(held, dict):
        return None
    if held.get("revision_id") != active_persisted_revision_id():
        return None
    try:
        return ActiveScenarioLabel(**held)
    except TypeError:
        return None


def rename_active_scenario_label(scenario_id: str, scenario_name: str) -> None:
    """시나리오명을 바꿨을 때 그 시나리오가 올라와 있으면 이름표의 이름도 바꾼다."""
    held = st.session_state.get(ACTIVE_SCENARIO_LABEL_KEY)
    if isinstance(held, dict) and held.get("scenario_id") == scenario_id:
        st.session_state[ACTIVE_SCENARIO_LABEL_KEY] = {**held, "scenario_name": scenario_name}


def activate_persisted_snapshot(snapshot: ScenarioSnapshot) -> ActiveScenario:
    """Publish tables and queue the preset before the next app-level widget render."""
    version = activate_persisted_reference_tables(
        snapshot.tables,
        snapshot.revision.revision_id,
    )
    active = activate_scenario_tables(
        snapshot.tables,
        reference_version=version,
        revision=snapshot.revision.revision_no,
    )
    st.session_state[ACTIVE_PERSISTED_SCENARIO_ID_KEY] = snapshot.scenario.scenario_id
    st.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] = snapshot.revision.revision_id
    st.session_state[ACTIVE_PERSISTED_SESSION_REVISION_KEY] = active["revision"]
    _remember_label(snapshot)
    for key in _STALE_UI_KEYS:
        st.session_state.pop(key, None)
    queue_scenario_preset(snapshot.preset)
    return active


def bootstrap_latest_official_scenario(database_path: str) -> bool:
    """Activate the latest official revision once for a new browser session."""
    if active_persisted_revision_id() is not None:
        return False
    if st.session_state.get(OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY) is True:
        return False
    repository = get_scenario_repository(database_path)
    bootstrap = ensure_initial_scenario(repository)
    release = bootstrap.release
    if release is None:
        st.session_state[OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY] = True
        return False
    snapshot = load_scenario_snapshot(database_path, release.revision_id)
    activate_persisted_snapshot(snapshot)
    st.session_state[OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY] = True
    return True


def clear_persisted_scenario_activation() -> None:
    clear_persisted_reference_tables()
    clear_active_scenario()
    for key in (
        ACTIVE_PERSISTED_SCENARIO_ID_KEY,
        ACTIVE_PERSISTED_REVISION_ID_KEY,
        ACTIVE_PERSISTED_SESSION_REVISION_KEY,
        OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY,
        ACTIVE_SCENARIO_LABEL_KEY,
        *_STALE_UI_KEYS,
    ):
        st.session_state.pop(key, None)


def active_persisted_scenario_id() -> str | None:
    value = st.session_state.get(ACTIVE_PERSISTED_SCENARIO_ID_KEY)
    return value if isinstance(value, str) else None


def active_persisted_revision_id() -> str | None:
    value = st.session_state.get(ACTIVE_PERSISTED_REVISION_ID_KEY)
    return value if isinstance(value, str) else None


def discard_unsaved_scenario_changes(
    reference_tables: dict[str, pd.DataFrame], reference_version: int
) -> ActiveScenario:
    """저장하지 않은 편집을 버리고 올라와 있는 리비전으로 되돌린다. 되돌린 뒤에는 미저장이 아니다.

    `reset_active_scenario` 는 표를 올라와 있는 리비전의 표로 갈아 끼우되 `revision` 을 올린다 —
    편집 UI 가 그 번호로 새로 선다. 그 번호를 **저장 표시에도 적어야** 「편집 되돌리기」를 누른 뒤
    미저장 배지·버튼·불러오기 잠금이 풀린다. 적지 않으면 내용은 저장본과 같은데 번호가 달라 계속
    미저장으로 읽힌다(2026-09-29 2차 리뷰에서 재현). 저장본이 없는 세션(내장 시드)은 표시를 만들지
    않는다 — 거기엔 되돌아갈 저장본이 없다.
    """
    active = reset_active_scenario(reference_tables, reference_version)
    if isinstance(st.session_state.get(ACTIVE_PERSISTED_SESSION_REVISION_KEY), int):
        st.session_state[ACTIVE_PERSISTED_SESSION_REVISION_KEY] = active["revision"]
    return active


def has_unsaved_scenario_changes() -> bool:
    saved_revision = st.session_state.get(ACTIVE_PERSISTED_SESSION_REVISION_KEY)
    current = st.session_state.get(ACTIVE_SCENARIO_KEY)
    if not isinstance(saved_revision, int) or not isinstance(current, dict):
        return False
    scenario = cast(ActiveScenario, current)
    return scenario["revision"] != saved_revision
