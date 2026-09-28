# Purpose: 사이드바의 구역 제목·적용 월 범위 표시와, 접힘 상태를 기억하는 상자를 만든다.

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.navigation import SidebarSectionSpec
from capa_simulation.services.month_columns import month_label

# 자리표시자는 **세션 상태**에 둔다. 모듈 전역에 두면 같은 서버 프로세스의 모든 세션이
# 하나를 공유해, 두 번째 사용자가 접속하는 순간 첫 사용자의 자리표시자가 교체된다.
# 그러면 한쪽의 "적용 · 범위" 가 다른 쪽 사이드바에 쓰이거나, 사라진 컨테이너에 써서
# 아무 데도 나타나지 않는다.
PLACEHOLDER_STATE_KEY = "sidebar_month_range_placeholder"

# HOME 이 그리는 B/N 집계 공정 상자. `app.py` 의 CSS 규칙이 이 key 를 읽는다 —
# 상자를 그리는 쪽과 서식을 주는 쪽이 갈려 있어 이름을 한 곳에 둔다.
BOTTLENECK_BOX_KEY = "sidebar_bottleneck_box"


def remembered_box_key(key: str) -> str:
    """상자 위젯 키에 딸린 **위젯이 아닌** 기억 칸의 이름."""
    return f"{key}__remembered"


def sidebar_expander(
    label: str,
    *,
    key: str,
    icon: str | None = None,
    default: bool = False,
) -> DeltaGenerator:
    """페이지 그룹과 같은 양식으로 접히는 사이드바 상자. 펼침 상태를 세션 동안 기억한다.

    `key` 와 `on_change="rerun"` 을 함께 줘야 확장 패널이 위젯이 되어 서버가
    `st.session_state[key]` 로 펼침 상태를 읽고 쓸 수 있다(실측). `expanded=` 는 주지
    않는다 — 세션 값과 둘을 같이 주면 Streamlit 이 경고를 남긴다.

    **위젯 값만으로는 모자라는 자리가 둘이다.** 하나는 HOME 만 그리는 B/N 상자다.
    다른 페이지에 갔다 오면 그 회차에 만들어지지 않은 위젯이라 값이 버려진다. 다른
    하나는 라벨에 배지를 단 시나리오 상자다 — **라벨이 위젯 id 계산에 들어가서**
    배지가 바뀌는 순간(미저장 편집이 생기거나 리비전을 불러올 때) 위젯이 통째로 새로
    만들어지고 펼침 상태가 기본값으로 돌아간다. 둘 다 실측으로 확인했다.

    그래서 위젯이 아닌 칸에 `(펼침, 라벨)` 을 적어 두고 **값이 사라졌거나 라벨이 바뀐
    회차에만** 되돌려 놓는다. 매 회차 덮어쓰면 방금 누른 사용자의 클릭을 지운다.
    """
    memory = remembered_box_key(key)
    remembered = st.session_state.get(memory)
    expanded, remembered_label = (
        (bool(remembered[0]), str(remembered[1]))
        if isinstance(remembered, tuple) and len(remembered) == 2
        else (default, label)
    )
    if key not in st.session_state or remembered_label != label:
        st.session_state[key] = expanded
    box = st.sidebar.expander(label, key=key, icon=icon, on_change="rerun")
    st.session_state[memory] = (bool(st.session_state[key]), label)
    return box


def render_sidebar_section(section: SidebarSectionSpec) -> None:
    """상자 무리 위에 구역 제목 한 줄을 세운다. 제목은 왼쪽, 뜻풀이는 오른쪽 끝이다.

    컨테이너가 돌려준 부모에 **직접** 쓴다. `st.sidebar.*` 는 `with` 문맥을 따르지 않아
    `with` 로 감싼 채 `st.sidebar.caption` 을 부르면 글자가 컨테이너 밖으로 새고, 빈
    컨테이너는 화면에 그려지지도 않는다. 서식은 `sidebar_style.py` 가 `section.key` 로 건다.
    """
    heading = st.sidebar.container(
        key=section.key,
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="bottom",
    )
    heading.caption(section.title, width="content")
    if section.hint:
        heading.caption(section.hint, width="content")


def register_month_range_placeholder(placeholder: DeltaGenerator) -> None:
    st.session_state[PLACEHOLDER_STATE_KEY] = placeholder


def _placeholder() -> DeltaGenerator | None:
    registered = st.session_state.get(PLACEHOLDER_STATE_KEY)
    if isinstance(registered, DeltaGenerator):
        return registered
    return None


def show_selected_month_range(start_month: int, end_month: int) -> None:
    """고른 범위를 **중립 문구**로 알린다. 이 화면이 그 범위를 읽었다는 뜻이 아니다.

    공통 사이드바가 모든 페이지에서 먼저 쓴다. 조회기간을 실제로 읽는 화면만 그 뒤에
    `show_applied_month_range` 로 「✓ 적용」을 덮는다. 전에는 여기서도 「✓ 적용」을 써서
    조회기간과 무관한 화면(Admin Area·VOC·Capa Chatbot 등)에서도 「적용」이 떴다.
    """
    placeholder = _placeholder()
    if placeholder is None:
        return
    placeholder.caption(f"선택 · {month_label(start_month)}–{month_label(end_month)}")


def show_applied_month_range(start_month: int, end_month: int) -> None:
    """**이 화면이 이 범위를 읽었다**고 알린다. 계산에 실제로 쓰인 월 범위다.

    사용자가 고른 범위에 데이터가 없으면 `resolve_effective_months` 가 범위를 좁힌다.
    좁혀졌다는 사실을 알리지 않으면 화면 숫자가 왜 다른지 알 수 없다. 범위를 읽은 뒤
    계산이 멈추면 `show_calculation_stopped` 가 이 표시를 거둔다.
    """
    placeholder = _placeholder()
    if placeholder is None:
        return
    placeholder.caption(
        f":material/check_circle: 적용 · {month_label(start_month)}–{month_label(end_month)}"
    )


def show_past_months_outside_range(first_past_month: int) -> None:
    """넣어 둔 과거 구간이 조회기간 밖이라 화면에 없다는 사실을 알린다.

    볼 수 있는 범위는 과거 구간만큼 자동으로 넓어지지만 **고른 범위는 그대로다**. 그래서
    과거를 저장해도 조회기간 시작월을 내리지 않으면 그 달이 표에 나타나지 않는데, 화면만
    보면 넣은 값이 사라진 것처럼 보인다. 어디까지 내려야 하는지 함께 적는다.

    **이 줄이 서는 자리는 상자 제목 줄 위 한 줄이다.** 폭이 제목과 펼침 표식 사이뿐(실측
    107px)이라 긴 문장은 말줄임으로 잘린다. 화면에는 짧은 쪽만 낸다 — 이 글자 칸은 클릭을
    요약 줄로 통과시키므로(`sidebar_style.py`) `help` 툴팁을 달아도 마우스가 닿지 못한다.
    어디까지 내려야 하는지는 짧은 문구가 이미 말한다(실측 95px).
    """
    placeholder = _placeholder()
    if placeholder is None:
        return
    placeholder.caption(f":material/info: 과거 밖 · {month_label(first_past_month)}부터")


def show_calculation_stopped() -> None:
    """범위는 읽었지만 계산이 멈췄다고 같은 자리에 알린다. 「✓ 적용」을 거둔다.

    Capa 는 시나리오 전체 기간을 한 번에 계산하므로 **조회기간 밖의 달**의 기준정보
    오류로도 멈춘다(`simulation_cache.get_scenario_capacity_and_demand`). 그때 사이드바가
    「✓ 적용」인 채 본문이 「계산을 멈췄습니다」를 말하면 둘이 어긋난다. 까닭은 본문 오류가
    말한다 — 자리가 107px 뿐이라 여기는 멈췄다는 사실만 적는다.
    """
    placeholder = _placeholder()
    if placeholder is None:
        return
    placeholder.caption(":material/block: 계산 멈춤")


def show_month_range_unavailable() -> None:
    """선택 범위에 데이터가 없어 계산이 서지 않았음을 같은 자리에 알린다.

    자리표시자는 rerun 을 넘어 남는다. 실패한 rerun 에서 아무것도 쓰지 않으면 직전에 성공한
    범위가 "적용" 으로 계속 보여 본문 오류와 어긋난다. 글자는 짧게 둔다 — 자리가 107px 뿐이라
    전에 쓰던 「적용 안 됨 · 선택 범위에 데이터 없음」은 반도 보이지 않았다. 적용되지 않았다는
    것은 아이콘이, 어느 범위에 데이터가 있는지는 본문 오류가 말한다.
    """
    placeholder = _placeholder()
    if placeholder is None:
        return
    placeholder.caption(":material/block: 데이터 없음")
