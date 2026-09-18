# Purpose: Session activation boundary for immutable DuckDB reference snapshots.

"""Session activation boundary for immutable DuckDB reference snapshots."""

import pandas as pd
import streamlit as st

SESSION_REFERENCE_TABLES_KEY = "persisted_reference_tables"
SESSION_REFERENCE_VERSION_KEY = "persisted_reference_version"
# HOME Figure 캐시 칸의 이름. **이 모듈이 소유한다** — 쓰는 곳이 셋인데(여기,
# `scenario_activation._STALE_UI_KEYS`, `components/home_rendering`) `scenario_activation`
# 은 `components` 를 import 할 수 없다(그 방향은 이미 반대로 나 있어 순환이 된다).
# 이 파일은 pandas·streamlit 만 보는 잎이라 셋 다 여기서 가져올 수 있다.
#
# 리터럴을 세 곳에 따로 적으면 이름을 바꿀 때 한 곳만 고쳐지고, 그러면 시나리오를 바꿔도
# 옛 칸이 남아 **남의 시나리오 그림이 그대로 뜬다.**
HOME_FIGURE_CACHE_KEY = "home_dashboard_figure_cache"


def get_effective_reference_tables() -> dict[str, pd.DataFrame]:
    """Return the DuckDB revision activated in this browser session."""
    saved = st.session_state.get(SESSION_REFERENCE_TABLES_KEY)
    if (
        isinstance(saved, dict)
        and saved
        and all(isinstance(frame, pd.DataFrame) for frame in saved.values())
    ):
        return saved
    raise RuntimeError(
        "활성 DuckDB 시나리오가 없습니다. 시나리오 페이지에서 공식버전을 지정하거나 "
        "저장된 리비전을 불러오세요."
    )


def get_effective_reference_version() -> int:
    saved = st.session_state.get(SESSION_REFERENCE_VERSION_KEY)
    if isinstance(saved, int) and not isinstance(saved, bool):
        return saved
    raise RuntimeError("활성 DuckDB 리비전 버전이 없습니다.")


def activate_persisted_reference_tables(
    reference_tables: dict[str, pd.DataFrame],
    revision_id: str,
) -> int:
    """Publish one immutable DB snapshot as this browser session's reference source."""
    if not reference_tables or not all(
        isinstance(frame, pd.DataFrame) for frame in reference_tables.values()
    ):
        raise ValueError("활성화할 DuckDB 기준정보가 올바르지 않습니다.")
    version = int(revision_id.replace("-", "")[:15], 16)
    st.session_state[SESSION_REFERENCE_TABLES_KEY] = reference_tables
    st.session_state[SESSION_REFERENCE_VERSION_KEY] = version
    return version


def apply_global_display_order(display_order: pd.DataFrame) -> None:
    """Replace only the shared UI order in the current session without resetting edits."""
    saved = st.session_state.get(SESSION_REFERENCE_TABLES_KEY)
    if not isinstance(saved, dict) or not saved:
        raise RuntimeError("공용 표시순서를 적용할 활성 시나리오가 없습니다.")
    revised = dict(saved)
    revised["RQ_DISPLAY_ORDER"] = display_order.copy(deep=True)
    st.session_state[SESSION_REFERENCE_TABLES_KEY] = revised
    st.session_state.pop(HOME_FIGURE_CACHE_KEY, None)


def clear_persisted_reference_tables() -> None:
    st.session_state.pop(SESSION_REFERENCE_TABLES_KEY, None)
    st.session_state.pop(SESSION_REFERENCE_VERSION_KEY, None)
