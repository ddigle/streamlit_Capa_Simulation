# Purpose: 필요 단축 일정 · Space 필요 단축 보기의 현재 일정 기준 전환과 그 글자를 둔다.

"""현재 일정 기준 전환 — 「Static | 설비 마스터」(2026-11-20 보드 답 Static-0 · Q01 · Q02 · Q03).

필요 단축 일정의 「현재 일정」 을 무엇으로 잡나 고르는 두 칸 전환이다. **필요 단축 일정** 조건 카드
맨 위와 **Space 「필요 단축」 보기**의 `Space 조건` 카드 「색 기준」 밑(필요 단축 기준 묶음)에 같은
꼴로 서고 같은 세션 칸(`shortening_source.SHORTENING_BASIS_KEY`)을 쓴다 — 두 화면이 늘 같은 호기를
말한다. 처음은 Static 이고 이 창(세션)에만 산다(공용 설정에 쓰지 않는다 — 목표 확보율과 같은 보관).

꼴은 제약 시뮬레이션 모드 전환(「제약 영향 | 개조 일정」)과 같다 — 라벨을 숨긴 `segmented_control`
이고 뜻은 같은 줄 끝 ⓘ 하나다(설계 규칙 UI-CON-03 · UI-TXT-02, 2026-11-10 보드 Q-8). 바꾸면 계산
입력이 바뀌므로 앱 전체가 한 번 다시 돈다(설계 규칙 UI-PRF-01 — 두 기준의 계획은 따로 캐시돼 왕복은
다시 계산하지 않는다).

화면 글자(Q02 (가)) — 호기 줄은 두 기준 모두 「현재 MM.DD → 단축 MM.DD」, 기준 값 글은
`supply_label` 이다(한 개념 한 이름 — 설계 규칙 UI-CON-02: 「설비 일정 기준 가용」 은 설비 마스터
기준에만).
"""

from __future__ import annotations

from typing import Final

import streamlit as st

from capa_simulation.components.shortening_source import SHORTENING_BASIS_KEY, settle_basis
from capa_simulation.services.static_qual_schedule import (
    BASES,
    BASIS_MASTER,
    BASIS_STATIC,
    DEFAULT_BASIS,
)

__all__ = [
    "BASIS_SWITCH_HELP",
    "BASIS_SWITCH_LABEL",
    "other_basis",
    "other_mark_label",
    "render_basis_switch",
    "supply_label",
]

BASIS_SWITCH_LABEL: Final = "현재 일정 기준"
BASIS_SWITCH_HELP: Final = (
    "현재 일정을 무엇으로 잡나 — **Static**: 기준정보 월별 가용대수 · Cut-off · Qual 순서로 늦어도 "
    "언제 Qual 해야 하는지 역산 / **설비 마스터**: 설비 마스터 Qual일정. 단축(◀)은 고른 기준에서 "
    "당길 몫이고, 고르지 않은 기준의 일정은 호기 줄에 흐린 ○ 로 함께 보입니다. 이 창에만 남습니다."
)
_SUPPLY_LABELS: Final = {
    BASIS_STATIC: "Static 역산 가용(환산)",
    BASIS_MASTER: "설비 일정 기준 가용(환산)",
}
_OTHER_MARK_LABELS: Final = {
    BASIS_STATIC: "설비 마스터 Qual",
    BASIS_MASTER: "Static 역산",
}


def supply_label(basis: str) -> str:
    """기준 값 글의 앞머리 — 단축 전 가용이 무엇인가(Q02 (가))."""
    return _SUPPLY_LABELS.get(basis, _SUPPLY_LABELS[BASIS_MASTER])


def other_basis(basis: str) -> str:
    """고르지 않은 기준 — 호기 줄의 흐린 표지가 그 일정이다."""
    return BASIS_MASTER if basis == BASIS_STATIC else BASIS_STATIC


def other_mark_label(basis: str) -> str:
    """흐린 표지(○)의 이름 — Static 기준이면 설비 마스터 Qual, 설비 마스터 기준이면 Static 역산."""
    return _OTHER_MARK_LABELS.get(basis, _OTHER_MARK_LABELS[BASIS_MASTER])


def render_basis_switch() -> str:
    """「Static | 설비 마스터」 전환 — 부르는 자리(조건 카드 안)에 그리고 고른 기준을 돌려준다.

    세션 칸을 위젯 앞에서 잡는다(`settle_basis` — 없거나 모르는 값이면 Static). 위젯 풍선은 라벨
    줄과 함께 숨으므로 두지 않고 뜻은 같은 줄 끝 ⓘ 하나다(설계 규칙 UI-TXT-02)."""
    settle_basis()
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        value = st.segmented_control(
            BASIS_SWITCH_LABEL,
            BASES,
            key=SHORTENING_BASIS_KEY,
            persist_state="session",
            required=True,
            label_visibility="collapsed",
        )
        st.caption("", help=BASIS_SWITCH_HELP, width="content")
    return str(value) if value in BASES else DEFAULT_BASIS
