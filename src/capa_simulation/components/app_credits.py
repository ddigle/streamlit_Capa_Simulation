# Purpose: 앱 이름·버전·적용된 배포 번호와 개발 팀·문의처를 모든 화면 사이드바 바닥 카드로 보인다.

"""App name, build, developer, and contact pinned to the foot of the sidebar.

머리 띠는 이 세션에 적용 중인 시나리오를 싣는다(2026-10-06 사용자 결정, `app_header`). 앱 자체에
대한 정보의 자리는 **모든 화면의 사이드바 맨 아래**다(2026-10-07 사용자 결정). ⋮ 메뉴(About)는
감추므로 이 카드가 그 값을 보여 주는 유일한 곳이다. 값은 `settings.py` 가 단일 근거다.

**두 줄뿐이다.** 앱·버전·배포 한 줄과 개발 팀·문의처 한 줄. 보안 등급·인증번호·취급 주의 문장은
싣지 않는다(2026-10-07 사용자 결정).

**첫 줄 끝은 적용된 배포 번호다**(2026-10-08 사용자 결정). 손으로 적던 빌드일은 배포마다 고치지
않아 낡은 날짜가 남았다. 사내에서 배포 ZIP 을 적용하면 남는 기록(`settings.DEPLOY_STATE_PATH`)의
`stamp` 를 「배포 202610081234」 로 적고, 그 기록이 없는 사외 개발 PC 는 「사외 개발」 이다. 기록은
프로세스에서 한 번만 읽는다 — 배포를 적용하려면 앱을 내려야 하므로(DuckDB 잠금) 다시 뜰 때 새 값을
읽는다.

`app.py` 가 페이지보다 **먼저**(`navigation.run()` 앞) 그린다 — 페이지가 `st.stop()` 해도 카드는
남는다. 그것도 화면마다 수가 달라지는 조회 조건 구역보다 앞(그룹 상자 바로 뒤의 `Support` 다음)
이라 어느 화면에서나 사이드바의 같은 순번이다 — 순번이 밀리면 페이지를 옮기는 동안 지난 회차의
사본이 흐리게 남아 카드가 두 벌로 보인다. 맨 아래 자리와 바닥 고정은 파이썬 차례가 아니라 사이드바
CSS(`sidebar_style.build_sidebar_stylesheet`)가 이 key 로 잡는다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import streamlit as st

from capa_simulation.settings import (
    APP_CONTACT_EMAIL,
    APP_NAME,
    APP_OWNER_TEAM,
    APP_VERSION,
    DEPLOY_STATE_PATH,
)

# 카드 컨테이너의 key 이자 CSS 훅(`st-key-…`). 「조회 조건」 제목을 살리는 상자로 세지 않도록
# 조건 카드 접두어(`condition_card_`)로 시작하지 않는다.
APP_CREDITS_KEY = "sidebar_app_credits"


# 적용 기록이 없을 때(사외 개발 PC) 첫 줄 끝에 적는 말.
OUTSIDE_BUILD_LABEL = "사외 개발"


def deployed_stamp(state_path: Path = DEPLOY_STATE_PATH) -> str | None:
    """적용 기록의 배포 번호. 기록이 없거나 읽을 수 없으면 `None`.

    카드는 모든 화면 모든 회차에 서므로 파일은 프로세스에서 한 번만 읽는다(`_read_stamp`).
    """
    return _read_stamp(str(state_path))


@lru_cache(maxsize=4)
def _read_stamp(path: str) -> str | None:
    try:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    stamp = state.get("stamp") if isinstance(state, dict) else None
    if stamp is None:
        return None
    return str(stamp).strip() or None


def credit_lines(stamp: str | None = None) -> tuple[str, str]:
    """보여 줄 두 줄. 앱·배포, 개발 차례다. `stamp` 를 주지 않으면 적용 기록에서 읽는다."""
    stamp = deployed_stamp() if stamp is None else stamp
    build = f"배포 {stamp}" if stamp else OUTSIDE_BUILD_LABEL
    return (
        f"{APP_NAME} v{APP_VERSION} · {build}",
        f"개발 {APP_OWNER_TEAM} · {APP_CONTACT_EMAIL}",
    )


def render_app_credits() -> None:
    """사이드바에 캡션 한 묶음으로 그린다. 바닥 고정·윗선·면은 사이드바 CSS 가 맡는다."""
    with st.sidebar.container(key=APP_CREDITS_KEY):
        st.caption("  \n".join(credit_lines()))
