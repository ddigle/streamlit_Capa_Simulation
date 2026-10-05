# Purpose: 여러 페이지가 같은 key 로 그리는 위젯 값을 페이지를 옮긴 첫 회차에도 브라우저에 알린다.

"""페이지를 건너 공유하는 위젯 값.

HOME 과 Static Capa 의 판정 기준 두 칸, Dynamic Capa 하위 화면들의 「샘플 데이터」 스위치처럼
**같은 세션 키를 여러 페이지의 위젯이 나눠 쓰는** 자리가 있다. `persist_state="session"` 만으로는
페이지를 옮긴 **첫 회차**를 지키지 못한다(Streamlit 1.63 실측·소스 확인).

- 위젯 id 에는 지금 페이지의 스크립트 해시가 들어간다. 같은 key 라도 페이지가 다르면 id 가 다르다.
- 새 페이지의 위젯이 처음 등록되는 순간 Streamlit 은 그 **새 id** 로 값을 찾고, 앞 페이지 위젯의
  값은 그 회차가 **끝난 뒤에야** 새 id 로 옮긴다. 그래서 그 회차에는 위젯 기본값(판정 기준은
  `min_value` 인 0, 스위치는 꺼짐)으로 계산하고, 브라우저에도 기본값이 그대로 그려진다.
- 그 뒤 rerun 에서 브라우저가 그 기본값을 다시 보내 세션 값을 덮는다 — 판정 기준이 세션 내내
  0.00 으로 남은 것이 이것이다(2026-10-05 E2E).

`st.session_state[key] = 값` 으로 **위젯을 만들기 전에** 다시 적으면 Streamlit 은 그 값을 이번
회차의 값으로 쓰고 브라우저에도 알린다. 다만 매 회차 다시 적으면 폼 안에서 아직 제출하지 않은
입력을 다른 rerun 이 서버 값으로 되돌린다. 그래서 **위젯을 그린 페이지가 바뀐 회차에만** 적는다.
"""

from __future__ import annotations

import streamlit as st


def _owner_key(key: str) -> str:
    """`key` 위젯을 마지막으로 그린 자리를 적어 두는 **위젯이 아닌** 칸의 이름."""
    return f"{key}__owner"


def carry_shared_widget_value(key: str, *, default: object, owner: str) -> None:
    """위젯을 만들기 **전에** 부른다. 값이 없으면 `default` 를 심고, 그리는 자리가 바뀌었으면
    지금 값을 다시 적어 새 자리의 위젯이 그 값으로 서게 한다.

    `owner` 는 이 위젯을 그리는 자리의 이름이다(페이지·화면마다 다르게 준다). 같은 자리의 다음
    회차는 `persist_state` 가 지키므로 건드리지 않는다.
    """
    owner_key = _owner_key(key)
    if key not in st.session_state:
        st.session_state[key] = default
    elif st.session_state.get(owner_key) != owner:
        st.session_state[key] = st.session_state[key]
    st.session_state[owner_key] = owner
