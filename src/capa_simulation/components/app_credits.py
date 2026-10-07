# Purpose: 앱 이름·버전·빌드일과 개발 팀·문의처를 모든 화면 사이드바 맨 아래 카드로 보여 준다.

"""App name, build, developer, and contact pinned to the foot of the sidebar.

머리 띠는 이 세션에 적용 중인 시나리오를 싣는다(2026-10-06 사용자 결정, `app_header`). 앱 자체에
대한 정보의 자리는 **모든 화면의 사이드바 맨 아래**다(2026-10-07 사용자 결정). ⋮ 메뉴(About)는
감추므로 이 카드가 그 값을 보여 주는 유일한 곳이다. 값은 `settings.py` 가 단일 근거다.

**두 줄뿐이다.** 앱·버전·빌드 한 줄과 개발 팀·문의처 한 줄. 보안 등급·인증번호·취급 주의 문장은
싣지 않는다(2026-10-07 사용자 결정).

`app.py` 가 페이지보다 **먼저**(`navigation.run()` 앞) 그린다 — 페이지가 `st.stop()` 해도 카드는
남는다. 파이썬 차례로는 페이지가 더하는 조건 카드보다 앞에 서지만, 맨 아래 자리와 바닥 고정은
사이드바 CSS(`sidebar_style.build_sidebar_stylesheet`)가 이 key 로 잡는다.
"""

from __future__ import annotations

import streamlit as st

from capa_simulation.settings import (
    APP_BUILD_DATE,
    APP_CONTACT_EMAIL,
    APP_NAME,
    APP_OWNER_TEAM,
    APP_VERSION,
)

# 카드 컨테이너의 key 이자 CSS 훅(`st-key-…`). 「조회 조건」 제목을 살리는 상자로 세지 않도록
# 조건 카드 접두어(`condition_card_`)로 시작하지 않는다.
APP_CREDITS_KEY = "sidebar_app_credits"


def credit_lines() -> tuple[str, str]:
    """보여 줄 두 줄. 앱·빌드, 개발 차례다."""
    return (
        f"{APP_NAME} v{APP_VERSION} · 빌드 {APP_BUILD_DATE}",
        f"개발 {APP_OWNER_TEAM} · {APP_CONTACT_EMAIL}",
    )


def render_app_credits() -> None:
    """사이드바에 캡션 한 묶음으로 그린다. 바닥 고정·윗선·면은 사이드바 CSS 가 맡는다."""
    with st.sidebar.container(key=APP_CREDITS_KEY):
        st.caption("  \n".join(credit_lines()))
