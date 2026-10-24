# Purpose: 네비게이션이 없는 단독 실행에서도 죽지 않는 페이지 링크를 공용으로 제공한다.

"""막힌 화면에서 다음 화면으로 건너가는 링크.

`st.page_link` 는 `st.navigation` 에 등록된 페이지만 받는다. 페이지를 단독 실행하는
테스트에는 네비게이션이 없어 그대로 두면 화면 전체가 예외로 죽는다. 링크가 없다고 화면이
멎을 이유는 없으므로 문구로 물러선다.

라벨을 인자로 받는 것은 이 링크가 카드 안뿐 아니라 안내문 뒤에도 놓이기 때문이다. 카드
안에서는 제목이 목적지를 말해 주므로 「열기」로 충분하지만, 문단 뒤에서는 그것만으로 어디를
여는지 알 수 없다.
"""

from __future__ import annotations

from collections.abc import Mapping

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError


def render_page_link(
    page_path: str,
    *,
    label: str,
    icon: str | None = None,
    query_params: Mapping[str, str] | None = None,
    disabled: bool = False,
    help: str | None = None,
) -> None:
    """`query_params` 를 주면 그 인자를 실은 주소로 연다 — 받는 페이지가 그 인자만 읽는다.

    `disabled` 면 링크가 꺼진 채 자리를 지키고(생겼다 사라지지 않는다), `help` 가 그 까닭을 풍선으로
    말한다(`st.page_link` 가 받는 인자 그대로).
    """
    try:
        if query_params is None:
            st.page_link(page_path, label=label, icon=icon, disabled=disabled, help=help)
        else:
            st.page_link(
                page_path,
                label=label,
                icon=icon,
                query_params=dict(query_params),
                disabled=disabled,
                help=help,
            )
    except StreamlitPageNotFoundError:
        st.caption(f"사이드바에서 {label}")
