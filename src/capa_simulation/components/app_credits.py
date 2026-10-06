# Purpose: 앱 이름·버전·빌드일·개발자·인증 정보를 Admin Area 맨 아래 작은 글로 보여 준다.

"""App name, build, developer, and clearance info at the foot of Admin Area.

머리 띠가 이 세션에 적용 중인 시나리오를 싣게 되면서(2026-10-06 사용자 결정, `app_header`) 앱
자체에 대한 정보는 운영 화면인 Admin Area 맨 아래로 옮겼다. ⋮ 메뉴(About)는 감추므로 이 자리가
그 값을 보여 주는 유일한 곳이다. 값은 `settings.py` 가 단일 근거다.
"""

from __future__ import annotations

import streamlit as st

from capa_simulation.settings import (
    APP_AUTH_CODE,
    APP_AUTH_EXPIRY,
    APP_BUILD_DATE,
    APP_CONTACT_EMAIL,
    APP_HANDLING_NOTE,
    APP_NAME,
    APP_OWNER_TEAM,
    APP_SECURITY_LEVEL,
    APP_VERSION,
)

# 캡션 묶음의 key 이자 CSS 훅(`st-key-…`).
APP_CREDITS_KEY = "admin_app_credits"


def credit_lines() -> tuple[str, ...]:
    """보여 줄 줄. 앱·빌드, 개발, 보안·인증 차례다."""
    return (
        f"{APP_NAME} v{APP_VERSION} · 빌드 {APP_BUILD_DATE}",
        f"개발 {APP_OWNER_TEAM} · {APP_CONTACT_EMAIL}",
        f"{APP_SECURITY_LEVEL} · 인증번호 {APP_AUTH_CODE}(유효기간 {APP_AUTH_EXPIRY})"
        f" · {APP_HANDLING_NOTE}",
    )


def render_app_credits() -> None:
    """Admin Area 맨 아래에 캡션 한 묶음으로 그린다. 탭보다 뒤, 페이지의 마지막 요소다."""
    with st.container(key=APP_CREDITS_KEY):
        st.divider()
        st.caption("  \n".join(credit_lines()))
