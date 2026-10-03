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

    **Figure 캐시를 비우지 않는다.** 색을 구워 넣은 그림이 테마를 넘나들면 안 되는 것은
    맞지만, 그것은 `home_rendering` 이 캔 이름 앞에 테마를 붙여 가른다. 비우는 방식은
    `st.context.theme.type` 이 틀리는 순간에 오히려 해롭다 — 그때 잘못 읽은 테마로 만든
    그림이 캐시에 눌러앉고, 값이 바로잡혀도 칸 이름이 같아 그대로 나온다.
    """
    resolved = _read_client_mode()
    _LOCAL.mode = resolved
    return resolved


def current_mode() -> Mode:
    """지금 실행이 쓰는 테마. `begin_run()` 이 아직 안 불렸으면 밝게."""
    mode: Mode | None = getattr(_LOCAL, "mode", None)
    return mode or "light"


# 테마 선택을 싣는 조회 인자. **`st.context.theme.type` 을 믿지 않는 이유가 여기 있다.**
# 그 값은 Streamlit 이 앱 배경색에서 추론하는 것이고, 공식 문서가 「세션에서 앱이 처음
# 로드될 때」와 「테마를 바꾼 직후」에는 틀릴 수 있다고 적는다(streamlit#11920). 게다가
# rerun 요청에 실려 오지 않으면 직전 값이 그대로 남는다. 그래서 밝은 테마로 쓰는 동안
# 파이썬만 어둡다고 믿는 일이 실제로 일어났다 — 화면은 흰데 Plotly 만 검게 그려졌다.
#
# 버튼이 고른 값을 URL 에 실으면 매 실행에서 같은 답이 나온다. 새로고침에도 남는다. 인자는
# 브라우저에 저장된 앱 테마(`theme_toggle` 의 키 규칙)를 따라 적는 **사본**이라, 저장된 값과 다른
# 인자로 열면 그 스크립트가 저장된 값으로 고쳐 쓰고 새로고침한다 — 즐겨찾기로 테마를 고정하지는
# 못한다. 앱 안에서 페이지를 옮기면 Streamlit 이 인자를 주소에서 빼므로 그 뒤 실행은 아래
# `st.context.theme` 으로 떨어진다(브라우저가 보낸 rerun 이라 그때 값은 맞다).
THEME_QUERY_PARAM = "theme"


def _read_client_mode() -> Mode:
    """이 실행이 쓸 테마. 조회 인자가 있으면 그것이 답이다."""
    try:
        chosen = str(st.query_params.get(THEME_QUERY_PARAM, "")).strip().lower()
    except Exception:  # 런타임 밖에서는 조회 인자가 없다
        chosen = ""
    if chosen in ("light", "dark"):
        return "dark" if chosen == "dark" else "light"
    # 인자가 없으면(첫 방문·직접 연 URL) 클라이언트 추론값으로 떨어진다. 틀릴 수 있지만
    # 버튼을 한 번 누르면 그 뒤로는 인자가 답을 정한다.
    try:
        value = st.context.theme.type
    except Exception:  # 런타임 밖·컨텍스트 없음 전부 밝게로 떨어뜨린다
        return "light"
    return "dark" if value == "dark" else "light"
