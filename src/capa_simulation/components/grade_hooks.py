# Purpose: 계산 화면이 접속 등급 창구(grade_ui · sso_identity · admin_view)를 부를 때 쓰는 늦게 읽는
# 얇은 대리 — 모듈을 읽는 순간의 가져오기 고리를 피한다.

"""접속 등급 창구의 늦게 읽는 대리(계산 · 시나리오 · HOME 화면 부품용).

`components/sso_identity.py` 는 모듈 머리에서 앱 머리 띠(`app_header`)를 읽고, 그 길이 입장 화면
→ HOME 그리기 → HOME 설정 부품(`home_preference` · `home_main_cases` · `past_data_management`)까지
닿는다. 그 부품이 모듈 머리에서 `grade_ui` · `sso_identity` 의 이름을 꺼내거나(`from … import`)
데코레이터로 부르면, 어느 쪽을 먼저 읽느냐에 따라 덜 읽힌 모듈을 만나 앱이 서지 못한다. 그래서 이
모듈은 머리에서 아무 화면 모듈도 읽지 않고, 부르는 순간에 진짜 창구를 읽어 넘긴다 — 동작은 창구
그대로다(`grade_ui.on_press` · `grade_ui.in_fragment` · `sso_identity.viewer_can` ·
`admin_view.diagnostic_message`).

데코레이터 이름은 창구와 같다(`on_press` · `in_fragment`) — 받는 자리 그물
(`tests/grade_support.assert_refusals_caught`)이 데코레이터 이름으로 본다. 시험이 창구 속성을 바꿔
끼우면(`monkeypatch.setattr(sso_identity, …)`) 부르는 순간 읽으므로 그대로 따른다.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])


def viewer_can(action: str) -> bool:
    """`sso_identity.viewer_can` — 화면 등급으로 그 동작을 세우나(미리 보기를 따른다)."""
    from capa_simulation.components import sso_identity

    return sso_identity.viewer_can(action)


def diagnostic_message(message: str) -> str:
    """`admin_view.diagnostic_message` — 개발자 몫이면 원문, 아니면 화면 공용 꼴."""
    from capa_simulation.components import admin_view

    return admin_view.diagnostic_message(message)


def on_press(fn: F) -> F:
    """`grade_ui.on_press` — 위젯 콜백의 등급 거절을 받아 알림을 담고 돌아온다."""

    @functools.wraps(fn)
    def inner(*args: Any, **kwargs: Any) -> Any:
        from capa_simulation.components import grade_ui

        return grade_ui.on_press(fn)(*args, **kwargs)

    return cast(F, inner)


def in_fragment(fn: F) -> F:
    """`grade_ui.in_fragment` — `@st.fragment` · `@st.dialog` 아래쪽에 단다. 본문 · 안쪽 콜백의 등급
    거절을 받아 앱 전체를 다시 그린다."""

    @functools.wraps(fn)
    def inner(*args: Any, **kwargs: Any) -> Any:
        from capa_simulation.components import grade_ui

        return grade_ui.in_fragment(fn)(*args, **kwargs)

    return cast(F, inner)
