# Purpose: Atomically activate a persisted scenario revision in the current browser session.

"""Atomically activate a persisted scenario revision in the current browser session."""

from __future__ import annotations

from typing import cast

import streamlit as st

from capa_simulation.application_bootstrap import ensure_initial_scenario
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
)

ACTIVE_PERSISTED_SCENARIO_ID_KEY = "active_persisted_scenario_id"
ACTIVE_PERSISTED_REVISION_ID_KEY = "active_persisted_revision_id"
ACTIVE_PERSISTED_SESSION_REVISION_KEY = "active_persisted_session_revision"
OFFICIAL_BOOTSTRAP_ATTEMPTED_KEY = "official_scenario_bootstrap_attempted"

# 시나리오를 바꾸면 버려야 하는 세션 값. 대부분은 화면 모듈이 소유하지만 문자열로 적는다 —
# 그 모듈들이 이 파일을 거꾸로 import 하므로 상수를 가져오면 순환이 된다.
# `tests/test_scenario_activation.py` 가 두 곳의 철자가 같은지 지킨다.
#
# Figure 캐시 칸만 상수로 받는다. 쓰는 곳이 셋이라 리터럴로 두면 이름을 바꿀 때 한 곳만
# 고쳐지고, 그러면 시나리오를 바꿔도 옛 칸이 남아 남의 시나리오 그림이 그대로 뜬다.
# `io/reference_cache` 는 pandas·streamlit 만 보는 잎이라 여기서 가져와도 순환이 없다.
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
# `home_preference` 의 토글 키를 훑어 빠진 것을 잡는다 — 「실행」이 나중에 추가되면서
# 목록에 들어오지 않아 이 규칙이 한동안 반쪽이었던 적이 있다.
_STALE_UI_KEYS = (
    "load_conversion_source_token",
    "reference_data_source_token",
    HOME_FIGURE_CACHE_KEY,
    # HOME 토글. 상수는 `components/home_preference.py` 가 소유하지만 그 모듈이 이 파일을
    # 거꾸로 import 하므로 문자열로 적는다.
    "home_show_advance",
    "home_show_execution",
    "home_show_comparison",
    "home_preference_plan_detail_customer",
    "home_preference_include_edp",
    "home_preference_include_past",
)


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
        *_STALE_UI_KEYS,
    ):
        st.session_state.pop(key, None)


def active_persisted_scenario_id() -> str | None:
    value = st.session_state.get(ACTIVE_PERSISTED_SCENARIO_ID_KEY)
    return value if isinstance(value, str) else None


def active_persisted_revision_id() -> str | None:
    value = st.session_state.get(ACTIVE_PERSISTED_REVISION_ID_KEY)
    return value if isinstance(value, str) else None


def has_unsaved_scenario_changes() -> bool:
    saved_revision = st.session_state.get(ACTIVE_PERSISTED_SESSION_REVISION_KEY)
    current = st.session_state.get(ACTIVE_SCENARIO_KEY)
    if not isinstance(saved_revision, int) or not isinstance(current, dict):
        return False
    scenario = cast(ActiveScenario, current)
    return scenario["revision"] != saved_revision
