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


# 이 세션에 불러온 리비전이 없을 때의 글 셋 — 오류가 아니라 볼 것이 없는 빈 상태다. 계산 화면은
# 「데이터 Error」 마크 대신 회색 한 줄을 세우고(`components/data_error_mark`) 이 글을 그 화면의
# 확인 단계 알림 전문으로 낸다. 어느 글인지는 오류를 글로 바꾸는
# 쪽(`page_bootstrap.no_revision_message`)이 저장소를 보고 고른다 — 이 잎 모듈은 저장소를 읽지
# 않는다. 화면이 글 앞에 머리를 붙여도 이 글이 그대로 들어 있어 가를 수 있게 고정 글이다.
NO_OFFICIAL_MESSAGE = (
    "공식버전이 없어 불러온 시나리오가 없습니다 — 시나리오 관리 › Capa 시나리오 › 목록 관리에서 "
    "리비전 하나를 「공식으로 지정…」 하면 새 세션이 그 공식버전을 불러옵니다."
)
ARCHIVED_ONLY_MESSAGE = (
    "보관본만 있어 불러올 시나리오가 없습니다 — 시나리오 관리 › Capa 시나리오 › 목록 관리의 "
    "「보관함」 에서 「되돌리기」 한 뒤 불러오세요."
)
NOT_LOADED_MESSAGE = (
    "이 세션에 불러온 시나리오가 없습니다 — 공식버전은 있으니 새로고침하면 불러옵니다(사이드바 "
    "「시나리오」 에서 골라 불러와도 됩니다)."
)


class NoActiveRevision(RuntimeError):
    """이 세션에 불러온 리비전이 없다 — 첫 접속에 불러올 공식버전이 없었거나 아직 고르지 않았다.

    글은 기본 `NO_OFFICIAL_MESSAGE` 다. 저장소를 보고 셋 가운데 맞는 글을 고르는 것은
    `page_bootstrap.bootstrap_error_message` 다.
    """


def get_effective_reference_tables() -> dict[str, pd.DataFrame]:
    """Return the DuckDB revision activated in this browser session."""
    saved = st.session_state.get(SESSION_REFERENCE_TABLES_KEY)
    if (
        isinstance(saved, dict)
        and saved
        and all(isinstance(frame, pd.DataFrame) for frame in saved.values())
    ):
        return saved
    raise NoActiveRevision(NO_OFFICIAL_MESSAGE)


def get_effective_reference_version() -> int:
    saved = st.session_state.get(SESSION_REFERENCE_VERSION_KEY)
    if isinstance(saved, int) and not isinstance(saved, bool):
        return saved
    raise NoActiveRevision(NO_OFFICIAL_MESSAGE)


def reference_version_for_revision(revision_id: str) -> int:
    """리비전 ID 에서 나오는 기준정보 버전. 계산 캐시 키의 첫 칸이다.

    세션 활성화와 공식 발행 검사가 같은 값을 써야 검사가 데운 캐시를 HOME 이 그대로 쓴다.
    """
    return int(revision_id.replace("-", "")[:15], 16)


def activate_persisted_reference_tables(
    reference_tables: dict[str, pd.DataFrame],
    revision_id: str,
) -> int:
    """Publish one immutable DB snapshot as this browser session's reference source."""
    if not reference_tables or not all(
        isinstance(frame, pd.DataFrame) for frame in reference_tables.values()
    ):
        raise ValueError("활성화할 DuckDB 기준정보가 올바르지 않습니다.")
    version = reference_version_for_revision(revision_id)
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
