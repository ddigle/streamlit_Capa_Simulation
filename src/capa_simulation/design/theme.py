# Purpose: 지금 이 세션이 보고 있는 테마(밝게/어둡게)를 한 번만 정해 두고 알려 준다.

"""테마 해석을 **실행 한 번에 한 번만** 한다.

`design/tokens.py` 의 색 이름 하나하나가 이 값을 본다. 한 rerun 에 그 접근이 414 번
일어나므로(실측), 접근마다 `st.context.theme` 을 읽으면 rerun 당 3.83ms 가 붙는다.
실행 첫머리에 한 번 읽어 두면 0.05ms 다 — 70 배 차이라 캐시가 선택이 아니다.

**모듈 전역에 담지 않고 스레드에 담는다.** Streamlit 은 세션마다 스크립트를 같은 프로세스의
다른 스레드에서 돌린다. 전역에 두면 한 사용자가 어둡게 쓰는 동안 동시에 도는 다른 세션의
화면까지 어두워진다. 이 앱은 실제로 여러 사람이 같이 쓴다.

`st.context.theme` 이 없거나 읽히지 않는 자리(테스트·스크립트·런타임 밖)에서는 밝게로
둔다. 색을 정하지 못해 화면이 못 뜨는 일은 없어야 한다.
"""

from __future__ import annotations

import threading
from typing import Literal

import streamlit as st

Mode = Literal["light", "dark"]

_LOCAL = threading.local()


def begin_run() -> Mode:
    """rerun 첫머리에서 한 번 부른다. 이 실행이 쓸 테마를 정해 스레드에 담는다.

    바뀌었으면 **그 세션의 Figure 캐시를 비운다.** Plotly Figure 는 색을 구워 넣으므로,
    캐시가 남아 있으면 테마를 바꿔도 옛 그림이 그대로 뜬다. 프로세스 전역 캐시는 비울
    것이 없다 — 전수로 확인했고 색을 들고 있는 것은 이 세션 캐시 하나뿐이다.
    """
    resolved = _read_client_mode()
    if getattr(_LOCAL, "mode", None) != resolved:
        _LOCAL.mode = resolved
        _clear_coloured_caches()
    return resolved


def current_mode() -> Mode:
    """지금 실행이 쓰는 테마. `begin_run()` 이 아직 안 불렸으면 밝게."""
    mode: Mode | None = getattr(_LOCAL, "mode", None)
    return mode or "light"


def _read_client_mode() -> Mode:
    try:
        value = st.context.theme.type
    except Exception:  # noqa: BLE001 - 런타임 밖·컨텍스트 없음 전부 밝게로 떨어뜨린다
        return "light"
    return "dark" if value == "dark" else "light"


def _clear_coloured_caches() -> None:
    # 늦게 import 한다. 이 모듈은 `tokens` 가 부르는 잎이라 컴포넌트를 먼저 끌어오면
    # 색 하나 읽으려다 화면 계층 전체가 따라 올라온다.
    from capa_simulation.io.reference_cache import HOME_FIGURE_CACHE_KEY

    try:
        st.session_state.pop(HOME_FIGURE_CACHE_KEY, None)
    except Exception:  # noqa: BLE001 - 세션이 없는 자리(스크립트·테스트)에서는 비울 것도 없다
        return
