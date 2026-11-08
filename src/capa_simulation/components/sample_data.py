# Purpose: 원천 없는 화면의 샘플 스위치 · 연결 전 자리 · 머리 미연결 배지 · 호기 없음 표지를 둔다.

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

**머리 「… 미연결」 배지는 켠 동안만 단다**(`pending_source_badge` — 2026-11-08 아침 보드 d4). 끈
동안은 연결 전 자리의 표지 「… 연결 대기」 가 같은 말을 해 거듭 달지 않는다. 켠 동안은 합성 샘플
화면이라 머리가 원천이 아직 없다고 말한다.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from capa_simulation.components.module_slot import slot_html
from capa_simulation.components.page_header import pending_badge
from capa_simulation.services.korean_particle import with_subject_particle
from capa_simulation.shared_widget_state import carry_shared_widget_value

SAMPLE_TOGGLE_KEY = "dynamic_capa_sample_data"
SAMPLE_TOGGLE_LABEL = "샘플 데이터"
# 호기가 없고 샘플도 끈 설비 화면(가용설비 현황 · 필요 단축 일정 · Space 현황)의 값 한 마디
# (`NO_UNITS_MARK` — 조건 카드, 카드에 조회 조건이 있는 Static 대비 일정은 본문 머리)에 다는 풍선 —
# 하는 법은 자리에 적지 않는다(설계 규칙 UI-TXT-04).
# Space 현황은 이 풍선 뒤에 그 화면의 한 마디를 잇는다(`app_pages/space_status.py` 의
# `SPACE_NO_UNITS_HELP`).
NO_UNITS_MARK = "조회할 호기 없음"
NO_UNITS_HELP = (
    "가용설비 현황 「설비 마스터」 탭에서 호기를 입력하거나 「샘플 데이터」 스위치를 켜면 "
    "화면을 살펴볼 수 있습니다."
)
# 연결 전 점선 자리 — 아래로 도면이 이어지는 Space 현황에서도 쓰므로 표지 한 줄만큼만 낮게 선다.
PENDING_SLOT_CLASS = "pending-source-slot"
PENDING_SLOT_MIN_HEIGHT = "72px"


def sample_switch_on() -> bool:
    """이 회차의 「샘플 데이터」 스위치 값 — 스위치를 그리기 전(머리 배지 · 설비 표본)에 읽는다.
    스위치를 누른 회차에도 세션 값이 이미 새 값이다. 처음 연 세션은 켜짐(`render_sample_switch` 의
    기본값)이다."""
    return bool(st.session_state.get(SAMPLE_TOGGLE_KEY, True))


def pending_source_badge(source: str) -> str:
    """머리 「`source` 미연결」 배지(`page_header.pending_badge`) — 샘플을 켠 동안만. 끈 동안은 빈
    글자다 — 연결 전 자리 표지(`render_pending_source` 의 「… 연결 대기」)가 같은 말을 한다. 머리는
    스위치보다 먼저 그리므로 세션 값으로 정한다(`sample_switch_on`)."""
    return pending_badge(source) if sample_switch_on() else ""


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
                    "아니라 샘플을 쓰는 모든 화면에 함께 걸립니다 — 가용설비·Space·실적 화면과 "
                    "Dynamic Capa·재공 현황, Capa Chatbot 이 같이 바뀝니다."
                ),
            )
            # 자리에는 표지만 둔다 — 실적이 아니라는 것은 숫자를 믿기 전에 알아야 해 표지 낱말로
            # 남기고(설계 규칙 UI-NTF-05), 연결되면 무엇이 바뀌는지는 풍선이 말한다(UI-TXT-01 · 04).
            # 끈 쪽은 표지가 없다 — 비어 있다는 것은 연결 전 자리의 표지(`render_pending_source`)나
            # 호기 없음 표지가 말하고, 지금 상태의 뜻은 스위치 풍선이 말한다(UI-TXT-07).
            if enabled:
                st.markdown(
                    ":orange-badge[:material/science: 합성 샘플] **실적 아님**",
                    help=(
                        "화면의 모든 수치는 실적이 아닙니다 — "
                        f"{with_subject_particle(source)} 붙으면 같은 자리에 실데이터가 들어옵니다."
                    ),
                )
    return bool(enabled)


def render_pending_source(
    *,
    subject: str,
    expects: Sequence[str],
    source: str,
    more_help: str = "",
) -> None:
    """스위치를 껐을 때의 자리표시자 — 제목과 점선 자리 하나, 자리에는 연결 대기 표지 한 줄.

    자리에 늘 서는 글은 무엇을 기다리는지(`source`) 한 마디뿐이다(설계 규칙 UI-LAY-10 · UI-TXT-04).
    들어올 값의 이름(`expects`)은 연결 협의에서 그대로 요구사항이 되므로 지우지 않고 제목 풍선에
    옮겼고, 그 값으로 이 화면이 무엇을 하는지(`more_help`)는 그 뒤에 잇는다.
    """
    arrives = f"{with_subject_particle(source)} 붙으면 아래 값이 이 자리에 들어옵니다."
    values = "\n".join(f"- {item}" for item in expects)
    tooltip = "\n\n".join(part for part in (arrives, values, more_help) if part)
    st.markdown(f"#### :material/pending: {subject}", help=tooltip)
    st.html(
        slot_html(
            f"{source} 연결 대기",
            "",
            css_class=PENDING_SLOT_CLASS,
            min_height=PENDING_SLOT_MIN_HEIGHT,
            print_min_height=PENDING_SLOT_MIN_HEIGHT,
        )
    )
