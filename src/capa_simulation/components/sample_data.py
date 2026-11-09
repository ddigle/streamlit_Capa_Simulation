# Purpose: 원천 없는 화면의 샘플 스위치(패널 줄 · 본문 상자) · 연결 전 자리 · 호기 없음 표지를 둔다.

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

**구현 중 화면(실적 셋 · Dynamic Capa · 재공 · Chatbot)의 스위치는 사이드바 조회 조건 패널의
줄이다**(`render_sample_row` — 2026-11-09 보드 T8, 페이지 상단 문구 · 여백 최소화). 그 화면들은
본문 머리에 배지 줄도 「합성 샘플 실적 아님」 상자도 두지 않는다 — 구현 중이라는 것은 화면 탭
이름 곁 표지가, 합성 샘플을 보는 중이라는 것은 머리 띠 표지가 말하고 둘 다 이 스위치의 세션
값(`sample_switch_on`)을 읽는다. 끈 동안은 연결 전 자리의 표지 「… 연결 대기」 가 무엇을
기다리는지 말한다. 설비 화면(가용설비 현황 · 필요 단축 일정 · Space 현황)은 아직 본문
상자(`render_sample_switch`)다.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from capa_simulation.components.condition_field import FIELD_KEY_PREFIX, condition_name_row
from capa_simulation.components.module_slot import slot_html
from capa_simulation.services.korean_particle import with_subject_particle
from capa_simulation.shared_widget_state import carry_shared_widget_value
from capa_simulation.sidebar_status import page_condition_slot

SAMPLE_TOGGLE_KEY = "dynamic_capa_sample_data"
SAMPLE_TOGGLE_LABEL = "샘플 데이터"
# 사이드바 조회 조건 패널의 「샘플 데이터」 줄(`render_sample_row`) — 필드 컨테이너 · 이름 줄
# key 의 꼬리.
SAMPLE_FIELD_SLUG = "sample_data"
SAMPLE_FIELD_KEY = f"{FIELD_KEY_PREFIX}{SAMPLE_FIELD_SLUG}"
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
    """이 회차의 「샘플 데이터」 스위치 값 — 스위치를 그리기 전(머리 띠 표지 · 설비 표본)에 읽는다.
    스위치를 누른 회차에도 세션 값이 이미 새 값이다. 처음 연 세션은 켜짐(`render_sample_switch` 의
    기본값)이다."""
    return bool(st.session_state.get(SAMPLE_TOGGLE_KEY, True))


def sample_switch_help(source: str) -> str:
    """스위치 풍선 — 켬 · 끔이 무엇을 보이는지와 모든 샘플 화면에 함께 걸린다는 것. 켠 동안의 수치가
    실적이 아니라는 말도 여기다 — 화면의 표지는 머리 띠다."""
    return (
        "켜면 연결 후 모습을 합성 데이터로 보여 줍니다 — 화면의 수치는 실적이 아닙니다. 끄면 지금 "
        f"상태(빈 화면과 {source} 연결 대기)를 그대로 보여 줍니다. 이 스위치는 이 화면 하나가 "
        "아니라 샘플을 쓰는 모든 화면에 함께 걸립니다 — 가용설비·Space·실적 화면과 "
        "Dynamic Capa·재공 현황, Capa Chatbot 이 같이 바뀝니다."
    )


def render_sample_row(*, key: str, source: str) -> bool:
    """사이드바 조회 조건 패널의 「샘플 데이터」 줄 — 이름은 왼쪽, 스위치는 오른쪽 끝(다른 패널 줄의
    이름 줄과 같은 꼴, 뜻은 이름 풍선). 그 화면의 패널 칸(`page_condition_slot(0)`)에 그리고 켬 ·
    끔을 돌려준다.

    공통 줄이 없는 화면은 이 줄이 패널을 세우므로(`sidebar_status.defer_page_condition_slots`) 조건
    카드보다 **먼저** 부른다. `key` 는 화면마다 다른 이름이다 — 다른 화면에서 넘어온 회차에 공유
    값을 다시 적는 자리로 쓴다(`carry_shared_widget_value`)."""
    carry_shared_widget_value(SAMPLE_TOGGLE_KEY, default=True, owner=key)
    with (
        page_condition_slot(0).container(),
        st.container(key=SAMPLE_FIELD_KEY, gap=None),
    ):
        row = condition_name_row(
            SAMPLE_TOGGLE_LABEL, slug=SAMPLE_FIELD_SLUG, help=sample_switch_help(source)
        )
        enabled = row.toggle(
            SAMPLE_TOGGLE_LABEL,
            key=SAMPLE_TOGGLE_KEY,
            persist_state="session",
            label_visibility="collapsed",
            width="content",
        )
    return bool(enabled)


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
