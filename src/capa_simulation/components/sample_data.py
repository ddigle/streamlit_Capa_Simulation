# Purpose: 아직 원천이 붙지 않은 화면에서 샘플 데이터 표시를 켜고 끄는 공통 스위치를 제공한다.

"""샘플 데이터 스위치.

아직 실적 DB 가 붙지 않은 화면들은 지금 **빈 껍데기**다. 조회 조건은 `disabled` 이고
표는 컬럼만 있다. 그래서 「연결되면 무엇을 얻는가」가 화면에 없다 — 만들 가치를 화면이
스스로 설명하지 못한다.

반대로 합성 표본으로 채우기만 하면 그 화면이 **실적처럼 읽힌다.** 그것이 지금까지
수율 실적 화면을 비워 둔 이유였다.

스위치가 두 요구를 한자리에서 만족시킨다. 켜면 「연결 후」가 보이고, 끄면 「연결 전」이
보인다. 같은 자리에서 둘을 비교할 수 있으니 무엇이 채워질 자리인지도 함께 드러난다.
**기본은 켜짐**이다 — 처음 들어온 사람에게 빈 화면보다 채워진 화면이 더 많은 것을
말한다. 대신 켜져 있는 동안에는 화면 맨 위에 샘플이라고 적는다.

**세션 키 하나를 그룹 전체가 공유한다.** 페이지를 옮길 때마다 다시 켜야 한다면 스위치가
아니라 방해물이다. Streamlit 은 한 번에 한 페이지만 돌리므로 같은 키의 위젯이 여러
페이지에 있어도 충돌하지 않는다. 다만 `persist_state="session"` 이 없으면 위젯이 화면에서
사라지는 순간 값이 버려지고, 있어도 다른 페이지로 넘어온 첫 회차에는 위젯이 기본값으로
선다 — 그 회차에는 `carry_shared_widget_value` 가 값을 다시 적는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from capa_simulation.shared_widget_state import carry_shared_widget_value

SAMPLE_TOGGLE_KEY = "dynamic_capa_sample_data"
SAMPLE_TOGGLE_LABEL = "샘플 데이터"


def render_sample_switch(*, key: str, source: str) -> bool:
    """스위치 한 줄. `source` 는 연결되면 이 자리를 채울 원천의 이름이다.

    `key` 는 화면마다 다르므로 그리는 자리의 이름으로도 쓴다. 다른 화면에서 넘어온 회차에
    값을 다시 적지 않으면 그 회차의 스위치가 기본값(꺼짐)으로 선다(`shared_widget_state`).
    """
    carry_shared_widget_value(SAMPLE_TOGGLE_KEY, default=True, owner=key)
    with st.container(border=True, key=key):
        with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
            enabled = st.toggle(
                SAMPLE_TOGGLE_LABEL,
                key=SAMPLE_TOGGLE_KEY,
                persist_state="session",
                width="content",
                help=(
                    "켜면 연결 후 모습을 합성 데이터로 보여 주고, 끄면 지금 상태(빈 화면과 "
                    f"{source} 연결 대기)를 그대로 보여 줍니다. 이 스위치는 이 화면 하나가 "
                    "아니라 샘플을 쓰는 모든 화면에 함께 걸립니다 — Dynamic Capa 하위 화면들과 "
                    "Capa Chatbot 이 같이 바뀝니다."
                ),
            )
            if enabled:
                st.markdown(
                    ":orange-badge[:material/science: 합성 샘플] "
                    f"화면의 모든 수치는 **실적이 아닙니다.** {source} 가 붙으면 같은 자리에 "
                    "실데이터가 들어옵니다."
                )
            else:
                st.markdown(
                    f":blue-badge[:material/database: {source} 미연결] "
                    "지금 상태입니다. 스위치를 켜면 연결 후 모습을 볼 수 있습니다."
                )
    return bool(enabled)


def render_pending_source(
    *,
    subject: str,
    expects: Sequence[str],
    source: str,
) -> None:
    """스위치를 껐을 때의 자리표시자. 무엇이 이 자리를 채우는지 적는다.

    빈 화면에 「데이터 연결 후 표시됩니다」한 줄만 두면 그 자리에 무엇이 오는지 알 수
    없다. 들어올 값의 이름을 적어 두면 연결 협의에서 그대로 요구사항이 된다.
    """
    with st.container(border=True):
        st.markdown(f"#### :material/pending: {subject}")
        st.caption(f"{source} 가 붙으면 아래 값이 이 자리에 들어옵니다.")
        st.markdown("\n".join(f"- {item}" for item in expects))
