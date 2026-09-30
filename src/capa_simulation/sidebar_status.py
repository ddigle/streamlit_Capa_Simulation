# Purpose: 사이드바의 구역 제목·적용 월 범위 표시와, 접힘 상태를 기억하는 상자·조건 카드를 만든다.

import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.errors import StreamlitAPIException

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

# 화면 조건 카드의 key 접두어. `sidebar_style.py` 가 이 접두어 하나로 모든 카드에 조건 상자
# 서식을 건다 — 페이지가 카드를 더할 때 서식 쪽에 적을 것이 없다.
CONDITION_CARD_PREFIX = "condition_card_"
# 표를 보는 조건(필터·상세·집계 수준)을 모으는 카드의 이름과 아이콘. 탭이 여럿인 화면은 모든
# 탭이 **한 카드**를 쓰고 안의 내용만 열린 탭 것으로 바뀐다 — 한 번 편 카드는 탭을 옮겨도 편
# 채로 남는다(2026-09-28 사용자 결정).
TABLE_CARD_LABEL = "표 조건"
TABLE_CARD_ICON = ":material/filter_alt:"


# **상자를 접고 펼 때는 본문을 다시 돌리지 않는다**(2026-09-30 사용자 지적 — 접고 펼 때마다 본문이
# 로딩됐다). 상자는 서버가 펼침 상태를 알아야 해서(현재 페이지 그룹 자동 펼침·배지가 바뀌어도
# 펼침 유지·조건 카드의 탭·페이지 왕복 기억) 상태를 추적하는 위젯이고, Streamlit 1.63 에서 상태를
# 추적하는 확장 패널은 여닫을 때마다 앱 전체를 다시 돌린다. 그래서 여닫기 콜백이
# `st.rerun(<프래그먼트 key>)` 로 **아무것도 그리지 않는 이 프래그먼트만** 다시 돌려 앱 전체
# 재실행을 대신한다(위젯 콜백에서만 쓰는 공식 API). 펼침 값은 그대로 세션에 들어온다.
SIDEBAR_TOGGLE_FRAGMENT_KEY = "sidebar_box_toggle"
# 그 프래그먼트를 담는 본문 컨테이너. 빈 칸이 본문 간격을 먹지 않게 CSS 가 숨긴다.
SIDEBAR_TOGGLE_SINK_KEY = "sidebar_box_toggle_sink"
# 이번 전체 실행이 끝까지 돌았는가. 실행 도중에 상자를 누르면 그 요청이 진행 중인 실행을 끊고
# 프래그먼트 재실행으로 바뀌어 본문이 반쯤 그려진 채 남는다(실측). 끝나지 않은 실행 뒤에는
# 콜백이 물러나 평소처럼 앱 전체를 다시 돌린다. **세션 대입이 아니라 이 dict 를 고친다** —
# `st.stop()` 이 걸린 동안의 세션 대입은 다시 멈춤 예외를 낸다(실측).
APP_RUN_STATE_KEY = "sidebar_app_run_state"


def begin_app_run() -> dict[str, bool]:
    """앱 실행 맨 앞에서 「이번 실행은 아직 끝나지 않았다」로 표시하고 그 표지를 돌려준다."""
    state = st.session_state.get(APP_RUN_STATE_KEY)
    if not isinstance(state, dict):
        state = {}
        st.session_state[APP_RUN_STATE_KEY] = state
    state["complete"] = False
    return state


@st.fragment(key=SIDEBAR_TOGGLE_FRAGMENT_KEY)
def render_box_toggle_sink() -> None:
    """상자 여닫기 콜백이 다시 돌리는 빈 프래그먼트. 매 실행 **`st.stop()` 이 걸릴 수 있는 곳보다
    앞에서** 불러야 한다 — 이번 실행에 등록되지 않은 프래그먼트는 겨눌 수 없다."""


def on_box_toggle(key: str | None = None, label: str | None = None) -> None:
    """상자 여닫기 콜백. 기억 칸을 적고, 할 수 있으면 빈 프래그먼트만 다시 돌린다.

    프래그먼트만 도는 회차에는 `sidebar_expander` 본체가 돌지 않으므로 `(펼침, 라벨)` 기억 칸을
    여기서 적는다 — 적지 않으면 여닫은 뒤 페이지를 옮기거나 배지가 바뀔 때 옛 상태로 돌아간다.
    직전 실행이 끝나지 않았거나 프래그먼트를 찾지 못하면(AppTest 는 실행마다 프래그먼트 저장소가
    새로 생긴다) 그냥 돌아가 앱 전체 재실행으로 둔다. `st.rerun` 이 던지는 재실행 예외는 잡지
    않는다.
    """
    if key is not None and label is not None:
        st.session_state[remembered_box_key(key)] = (bool(st.session_state.get(key)), label)
    state = st.session_state.get(APP_RUN_STATE_KEY)
    if not isinstance(state, dict) or not state.get("complete"):
        return
    try:
        st.rerun(SIDEBAR_TOGGLE_FRAGMENT_KEY)
    except StreamlitAPIException:
        return


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

    `key` 와 상태를 추적하는 `on_change` 를 함께 줘야 확장 패널이 위젯이 되어 서버가
    `st.session_state[key]` 로 펼침 상태를 읽고 쓸 수 있다(실측). `on_change` 는 `"rerun"` 이
    아니라 `on_box_toggle` 콜백이다 — 여닫을 때 본문을 다시 돌리지 않는다(2026-09-30).
    `expanded=` 는 주지 않는다 — 세션 값과 둘을 같이 주면 Streamlit 이 경고를 남긴다.

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
    box = st.sidebar.expander(label, key=key, icon=icon, on_change=on_box_toggle, args=(key, label))
    st.session_state[memory] = (bool(st.session_state[key]), label)
    return box


def condition_card(label: str, *, name: str, icon: str = ":material/tune:") -> DeltaGenerator:
    """그 화면이 **실제로 읽는 고유 조건**을 모으는 사이드바 상자(2026-09-28 사용자 결정).

    사이드바 「조회 조건」 구역은 지금 화면의 조건을 모으는 한 곳이다. 공통 조건(시나리오·
    리비전, 조회기간) 아래에 그 화면만의 설정(소요기준·상세 같은 것)이 이 카드로 선다.
    본문에는 결과와 그 결과에 대한 행동만 남는다.

    **기본은 접힘이고, 한 번 편 카드는 탭·페이지를 오가도 편 채로 남는다.** 탭에 딸린 카드는
    그 탭이 열렸을 때만 그려지는데, 안 그려진 회차에는 위젯 값이 버려지므로
    `sidebar_expander` 의 기억 칸이 되돌린다. 페이지가 그리는 요소라 파이썬 차례로는
    `Support` 뒤에 붙지만 CSS 의 `order` 가 `Support` 를 맨 아래로 민다.
    """
    return sidebar_expander(label, key=f"{CONDITION_CARD_PREFIX}{name}", icon=icon)


def table_card(name: str) -> DeltaGenerator:
    """표 조건 카드(`표 조건`). `name` 은 화면마다 하나다."""
    return condition_card(TABLE_CARD_LABEL, name=name, icon=TABLE_CARD_ICON)


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


def forget_month_range_placeholder() -> None:
    """조회기간 상자를 세우지 않는 화면에서 앞 화면이 등록한 자리표시자를 지운다."""
    st.session_state.pop(PLACEHOLDER_STATE_KEY, None)


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
