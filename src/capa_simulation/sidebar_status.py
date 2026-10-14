# Purpose: 사이드바 구역 제목·조건 패널 칸·적용 기간 표시와 펼침을 기억하는 상자·조건 카드를 만든다.

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.errors import StreamlitAPIException
from streamlit.runtime.scriptrunner import get_script_run_ctx

from capa_simulation.navigation import SidebarSectionSpec
from capa_simulation.services.month_columns import month_label

# 자리표시자는 **세션 상태**에 둔다. 모듈 전역에 두면 같은 서버 프로세스의 모든 세션이
# 하나를 공유해, 두 번째 사용자가 접속하는 순간 첫 사용자의 자리표시자가 교체된다.
# 그러면 한쪽의 "적용 · 범위" 가 다른 쪽 사이드바에 쓰이거나, 사라진 컨테이너에 써서
# 아무 데도 나타나지 않는다.
PLACEHOLDER_STATE_KEY = "sidebar_month_range_placeholder"

# 사이드바 「조회 조건」 **통합 패널**(2026-10-10 사용자 결정 — 늘 펼친 패널 하나). `app.py` 가 매
# 회차 같은 순번에 세우는 테두리 상자이고, 안의 줄(시나리오·조회기간, 그리고 페이지가 채우는 칸)은
# `components/condition_field.py` 의 필드 양식이다. 그리는 쪽(`app.py`)과 서식을 주는 쪽
# (`sidebar_style.py`)과 테스트가 같은 이름을 보도록 여기 한 곳에 둔다.
CONDITIONS_BOX_KEY = "sidebar_conditions_box"
# 패널 안에서 **페이지가 나중에 채우는 칸**의 수. 시나리오·조회기간은 `app.py` 가 페이지보다 먼저
# 그리지만, HOME 의 공정 필터·주요공정 히트맵은 계산 뒤에야 값이 정해져 페이지가 그린다. 그래서
# `app.py` 가 빈 칸(블록 — `st.container`)을 미리 세워 등록하고 페이지가 채운다(적용 기간
# 자리표시자와 같은 방식). 칸 수를 화면마다 바꾸지 않는다 — 빈 칸은 그려지지 않아 높이·간격이
# 없고(1.63 `st.container()` 는 `allow_empty=False` 라 빈 블록을 프런트엔드가 그리지 않는다 — 칸에
# `border`·`height` 를 주면 `allow_empty` 가 켜져 빈 칸이 그려진다), 늘 같은 수라 패널 안 순번도
# 화면마다 같다.
PAGE_CONDITION_SLOT_COUNT = 2
# 칸도 **세션 상태**에 둔다(아래 자리표시자와 같은 까닭 — 모듈 전역이면 세션끼리 칸을 나눠 쓴다).
PAGE_SLOT_STATE_KEY = "sidebar_page_condition_slots"

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
# `st.stop()` 이 걸린 동안의 세션 대입은 다시 멈춤 예외를 낸다(실측). 칸은 셋이다 — `complete`
# (끝까지 돌았나), `run`(가장 늦게 시작한 실행의 표지), `page`(끝까지 돈 실행의 페이지).
APP_RUN_STATE_KEY = "sidebar_app_run_state"

# 조건 패널의 시나리오·조회기간 팝업을 여닫는 **키 붙은 호스트 프래그먼트**(`app.py`). 값 칸을
# 누르거나 팝업을 닫을 때(X·바깥·Esc) 페이지 계산까지 앱 전체를 다시 돌리지 않고 이 프래그먼트만
# 돈다 — 여닫는 회차에 바뀌는 것은 열림 키와 팝업 초안뿐이고 계산 입력(활성 리비전·`content_token`·
# 조회기간·미저장 편집)은 그대로다. 원본을 바꾸는 동작(불러오기·저장·되돌리기·조회기간 「적용」)은
# 팝업 본문이 `st.rerun()` 으로 앱 전체를 다시 돌린다. 여는 콜백은 상자 여닫기와 같은 판정
# (`rerun_fragment_if_alone`)을 거치고, 못 넘으면 앱 전체 재실행으로 물러난다.
CONDITION_DIALOG_FRAGMENT_KEY = "sidebar_condition_dialog_host"
# 그 프래그먼트를 담는 본문 컨테이너. 팝업은 본문 밖(이벤트 칸)에 서므로 이 칸은 늘 비어 있고, 빈
# 칸이 본문 간격을 먹지 않게 상자 여닫기 칸과 같이 CSS 가 숨긴다.
CONDITION_DIALOG_SINK_KEY = "sidebar_condition_dialog_sink"


@dataclass(frozen=True, eq=False)
class AppRun:
    """전체 실행 하나의 표지. `begin_app_run` 이 만들고 `finish`·`finish_stopped` 가 닫는다.

    `state` 는 세션의 `APP_RUN_STATE_KEY` 칸(dict)이고 `token` 은 이 실행만의 표다. 같은 세션의
    실행은 겹칠 수 있다 — 새 상호작용이 들어오면 Streamlit 은 돌던 실행에 멈춤만 걸고 새 실행을 따로
    띄운다(`runner.fastReruns`, 기본값). 그래서 닫을 때 이 실행이 아직 가장 늦게 시작한 실행인지
    본다.
    """

    state: dict[str, object]
    token: object

    def finish(self) -> None:
        """끝까지 돈 실행. 뒤에 시작한 실행이 없을 때만 「끝났다」와 이 실행의 페이지를 적는다."""
        if self.state.get("run") is not self.token:
            return
        self.state["page"] = _current_page_hash()
        self.state["complete"] = True

    def finish_stopped(self, stop: BaseException) -> None:
        """멈춤 예외로 끝난 실행. 페이지가 스스로 멈춘 것(`st.stop()`)만 끝까지 돈 것이다.

        페이지가 `st.stop()` 으로 멈춘 화면은 멈춘 자리까지가 전부다. 새 상호작용이 끊은 실행도 같은
        멈춤 예외로 끝나지만 본문이 반쯤 그려진 채라 끝나지 않은 실행으로 둔다.
        """
        if _raised_by_st_stop(stop):
            self.finish()


def begin_app_run() -> AppRun:
    """앱 실행 맨 앞에서 「이번 실행은 아직 끝나지 않았다」로 표시하고 그 표지를 돌려준다.

    **메시지를 보내는 첫 Streamlit 호출보다 앞에서** 부른다. 그런 호출은 다른 요청이 이 실행을
    끊는 자리라, 그 앞에서 끊긴 실행이 앞 실행의 「끝났다」를 남겨 두지 않게 한다.
    """
    state = st.session_state.get(APP_RUN_STATE_KEY)
    if not isinstance(state, dict):
        state = {}
        st.session_state[APP_RUN_STATE_KEY] = state
    token = object()
    state["run"] = token
    state["complete"] = False
    return AppRun(state, token)


def _current_page_hash() -> str | None:
    """지금 실행의 페이지 표(`page_script_hash`). 실행 문맥이 없으면 None 이다."""
    ctx = get_script_run_ctx(suppress_warning=True)
    return None if ctx is None else ctx.page_script_hash


def _raised_by_st_stop(stop: BaseException) -> bool:
    """멈춤 예외가 `st.stop()` 안에서 났는가. 판정하지 못하면 False(끝나지 않은 실행 쪽)다.

    `st.stop()` 과 Streamlit 이 새 상호작용 때문에 실행을 끊는 멈춤은 같은 예외(`StopException`)라,
    예외가 `st.stop()` 함수 안을 지나왔는지로만 갈린다(버전은 `streamlit==1.63.0` 고정).
    """
    try:
        stop_code = inspect.unwrap(st.stop).__code__
    except (AttributeError, ValueError):
        return False
    frame = stop.__traceback__
    while frame is not None:
        if frame.tb_frame.f_code is stop_code:
            return True
        frame = frame.tb_next
    return False


@st.fragment(key=SIDEBAR_TOGGLE_FRAGMENT_KEY)
def render_box_toggle_sink() -> None:
    """상자 여닫기 콜백이 다시 돌리는 빈 프래그먼트. 매 실행 **`st.stop()` 이 걸릴 수 있는 곳보다
    앞에서** 불러야 한다 — 이번 실행에 등록되지 않은 프래그먼트는 겨눌 수 없다."""


def on_box_toggle(key: str, label: str | None = None) -> None:
    """상자 여닫기 콜백. 기억 칸을 적고, 할 수 있으면 빈 프래그먼트만 다시 돌린다.

    프래그먼트만 도는 회차에는 `sidebar_expander` 본체가 돌지 않으므로 `(펼침, 라벨)` 기억 칸을
    여기서 적는다 — 적지 않으면 여닫은 뒤 페이지를 옮기거나 배지가 바뀔 때 옛 상태로 돌아간다
    (라벨이 없는 페이지 그룹은 기억 칸을 쓰지 않는다). 앱 전체 재실행으로 물러나는 경우는
    `rerun_fragment_if_alone` 이 가른다.
    """
    if label is not None:
        st.session_state[remembered_box_key(key)] = (bool(st.session_state.get(key)), label)
    rerun_fragment_if_alone(SIDEBAR_TOGGLE_FRAGMENT_KEY, key)


def rerun_fragment_if_alone(fragment_key: str, widget_key: str) -> None:
    """위젯 콜백의 **마지막 줄**에서 부른다. 할 수 있으면 `fragment_key` 프래그먼트만 다시 돌린다.

    `st.rerun(<key>)` 는 재실행 예외로 콜백을 그 자리에서 끊으므로 콜백이 할 일을 다 한 뒤에 부른다.
    아래 경우에는 그냥 돌아가 앱 전체 재실행(콜백 위젯의 기본 동작)으로 둔다.

    - 직전 전체 실행이 끝까지 돌지 않았을 때(`AppRun` — 끊긴 실행·아직 도는 실행).
    - 이번 실행의 페이지가 끝까지 돈 실행의 페이지와 다를 때(페이지를 옮기는 실행이 본문 전에
      끊긴 경우).
    - **이번 상호작용에서 `widget_key` 말고 다른 위젯도 바뀌었을 때**.
    - 프래그먼트를 찾지 못할 때(이번 실행에 등록되지 않았거나, AppTest 처럼 실행마다 프래그먼트
      저장소가 새로 생길 때). `st.rerun` 이 던지는 재실행 예외는 잡지 않는다.
    """
    state = st.session_state.get(APP_RUN_STATE_KEY)
    if not isinstance(state, dict) or not state.get("complete"):
        return
    page = _current_page_hash()
    if page is None or state.get("page") != page:
        return
    if not _only_this_widget_changed(widget_key):
        return
    try:
        st.rerun(fragment_key)
    except StreamlitAPIException:
        return


def _only_this_widget_changed(key: str) -> bool:
    """이번 상호작용에서 값이 바뀐 위젯이 `key` 하나뿐인가. 판정하지 못하면 False 다.

    입력칸에 글을 쓰다 사이드바 상자를 누르면 입력칸의 값과 상자의 여닫기가 **한 상호작용으로
    합쳐져** 도착한다. 그때 프래그먼트만 다시 돌리면 입력칸 값은 세션에 들어가지만 본문은 그 값으로
    다시 그려지지 않는다 — 탭을 누르고 30ms 안에 상자를 누르면 탭만 바뀌고 본문이 빈 채 남았다
    (2026-09-30 브라우저 실측). Streamlit 은 이것을 공개 API 로 알려 주지 않아 세션 상태 내부
    (`_widget_changed`)를 읽는다 — 버전은 `streamlit==1.63.0` 으로 고정돼 있고, 내부가 바뀌어 읽지
    못하면 앱 전체 재실행(지금까지의 동작)으로 물러난다.
    """
    try:
        from streamlit.runtime.state.session_state_proxy import get_session_state

        session = get_session_state()._state
        own = session._get_widget_id(key)
        changed = {wid for wid in session._new_widget_state if session._widget_changed(wid)}
    except Exception:  # noqa: BLE001 — 내부가 바뀌면 안전한 쪽(앱 전체 재실행)으로 물러난다
        return False
    return changed == {own}


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

    **위젯 값만으로는 모자라는 자리가 둘이다.** 하나는 탭·페이지에 딸린 조건 카드다(HOME
    `LOB 표시 조건` 은 Main 탭에서만 선다). 다른 탭·페이지에 갔다 오면 그 회차에 만들어지지 않은
    위젯이라 값이 버려진다. 다른 하나는 라벨이 바뀌는 상자다 — **라벨이 위젯 id 계산에 들어가서**
    라벨이 바뀌는 순간 위젯이 통째로 새로 만들어지고 펼침 상태가 기본값으로 돌아간다(본문 VOC 글의
    「답변 N」). 둘 다 실측으로 확인했다.

    그래서 위젯이 아닌 칸에 `(펼침, 라벨)` 을 적어 두고 **값이 사라졌거나 라벨이 바뀐
    회차에만** 되돌려 놓는다. 매 회차 덮어쓰면 방금 누른 사용자의 클릭을 지운다.
    """
    return _remembered_box(st.sidebar.expander, label, key=key, icon=icon, default=default)


def remembered_expander(
    label: str,
    *,
    key: str,
    icon: str | None = None,
    default: bool = False,
) -> DeltaGenerator:
    """본문(지금 컨테이너)에 여는 같은 기억 상자(2026-10-01 브라우저 점검).

    `key` 없는 본문 `st.expander` 도 사이드바 상자와 같은 두 자리에서 편 상태를 잃었다. 닫힌 탭의
    본문을 건너뛰는 화면(산출 결과 확보율 탭의 히트맵)은 다른 탭에 갔다 오면 상자가 새로 만들어져
    접혔고, 라벨에 「답변 N」이 든 VOC 글은 답변을 남기면 접혔다. 규칙은 `sidebar_expander` 와
    같다 — 여닫을 때 본문을 다시 돌리지 않는 것도 같다.
    """
    return _remembered_box(st.expander, label, key=key, icon=icon, default=default)


def _remembered_box(
    open_box: Callable[..., DeltaGenerator],
    label: str,
    *,
    key: str,
    icon: str | None,
    default: bool,
) -> DeltaGenerator:
    """`(펼침, 라벨)` 기억 칸을 **값이 사라졌거나 라벨이 바뀐 회차에만** 되돌리고 상자를 연다."""
    memory = remembered_box_key(key)
    remembered = st.session_state.get(memory)
    expanded, remembered_label = (
        (bool(remembered[0]), str(remembered[1]))
        if isinstance(remembered, tuple) and len(remembered) == 2
        else (default, label)
    )
    if key not in st.session_state or remembered_label != label:
        st.session_state[key] = expanded
    box = open_box(label, key=key, icon=icon, on_change=on_box_toggle, args=(key, label))
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


def register_page_condition_slots(slots: Sequence[DeltaGenerator]) -> None:
    """`app.py` 가 패널 안에 세운 빈 칸들을 이번 회차의 페이지 몫으로 등록한다."""
    st.session_state[PAGE_SLOT_STATE_KEY] = tuple(slots)


def forget_page_condition_slots() -> None:
    """패널을 세우지 않은 회차에 부른다. 앞 회차의 칸에 페이지가 쓰지 않게 한다."""
    st.session_state.pop(PAGE_SLOT_STATE_KEY, None)


def page_condition_slot(index: int) -> DeltaGenerator:
    """페이지가 채울 패널 칸 하나. `with page_condition_slot(0).container():` 로 쓴다.

    등록된 칸이 없으면(패널이 서지 않은 회차, `app.py` 없이 페이지만 띄운 테스트 하네스) 사이드바
    자체를 돌려준다 — 줄은 패널 밖 맨 아래에라도 선다. 한 칸은 한 회차에 **한 번만** 채운다 —
    칸은 블록이라 두 번 쓰면 두 줄이 쌓인다. 블록이라 다시 도는 동안 앞 회차의 줄이 그 자리에
    남아 패널이 흔들리지 않는다(`st.empty` 는 회차 시작에 비웠다).
    """
    registered = st.session_state.get(PAGE_SLOT_STATE_KEY)
    if isinstance(registered, tuple) and 0 <= index < len(registered):
        slot = registered[index]
        if isinstance(slot, DeltaGenerator):
            return slot
    return st.sidebar


def register_month_range_placeholder(placeholder: DeltaGenerator) -> None:
    st.session_state[PLACEHOLDER_STATE_KEY] = placeholder


def forget_month_range_placeholder() -> None:
    """조회기간 줄을 세우지 않는 화면에서 앞 화면이 등록한 자리표시자를 지운다."""
    st.session_state.pop(PLACEHOLDER_STATE_KEY, None)


def _placeholder() -> DeltaGenerator | None:
    registered = st.session_state.get(PLACEHOLDER_STATE_KEY)
    if isinstance(registered, DeltaGenerator):
        return registered
    return None


def _show_range_status(text: str) -> None:
    """조회기간 이름 줄 오른쪽 칸에 적는다. 글자 폭만큼만 차지해 오른쪽 끝에 붙는다.

    칸은 패널의 일반 흐름 안에 선다(전에는 접힌 상자 요약 줄 위에 107px 절대좌표로 얹었다).
    이름 줄 폭(실측 약 150px)을 넘는 글은 CSS 가 한 줄로 말줄임한다(`sidebar_style`). 까닭이
    긴 상태(어느 범위에 데이터가 있는지 등)는 본문 오류가 말하고 여기는 짧게 둔다.
    """
    placeholder = _placeholder()
    if placeholder is None:
        return
    placeholder.caption(text, width="content")


def show_selected_month_range(start_month: int, end_month: int) -> None:
    """고른 범위를 **중립 문구**로 알린다. 이 화면이 그 범위를 읽었다는 뜻이 아니다.

    공통 사이드바가 모든 페이지에서 먼저 쓴다. 조회기간을 실제로 읽는 화면만 그 뒤에
    `show_applied_month_range` 로 「✓ 적용」을 덮는다. 전에는 여기서도 「✓ 적용」을 써서
    조회기간과 무관한 화면(Admin Area·VOC·Capa Chatbot 등)에서도 「적용」이 떴다.
    """
    _show_range_status(f"선택 · {month_label(start_month)}–{month_label(end_month)}")


def show_applied_month_range(start_month: int, end_month: int) -> None:
    """**이 화면이 이 범위를 읽었다**고 알린다. 계산에 실제로 쓰인 월 범위다.

    사용자가 고른 범위에 데이터가 없으면 `resolve_effective_months` 가 범위를 좁힌다.
    좁혀졌다는 사실을 알리지 않으면 화면 숫자가 왜 다른지 알 수 없다. 범위를 읽은 뒤
    계산이 멈추면 `show_calculation_stopped` 가 이 표시를 거둔다.
    """
    _show_range_status(
        f":material/check_circle: 적용 · {month_label(start_month)}–{month_label(end_month)}"
    )


def show_past_months_outside_range(first_past_month: int) -> None:
    """넣어 둔 과거 구간이 조회기간 밖이라 화면에 없다는 사실을 알린다.

    볼 수 있는 범위는 과거 구간만큼 자동으로 넓어지지만 **고른 범위는 그대로다**. 그래서
    과거를 저장해도 조회기간 시작월을 내리지 않으면 그 달이 표에 나타나지 않는데, 화면만
    보면 넣은 값이 사라진 것처럼 보인다. 어디까지 내려야 하는지 함께 적는다 — 이름 줄 오른쪽
    한 칸이라 짧은 쪽만 낸다(실측 95px).
    """
    _show_range_status(f":material/info: 과거 밖 · {month_label(first_past_month)}부터")


def show_calculation_stopped() -> None:
    """범위는 읽었지만 계산이 멈췄다고 같은 자리에 알린다. 「✓ 적용」을 거둔다.

    Capa 는 시나리오 전체 기간을 한 번에 계산하므로 **조회기간 밖의 달**의 기준정보
    오류로도 멈춘다(`simulation_cache.get_scenario_capacity_and_demand`). 그때 사이드바가
    「✓ 적용」인 채 본문이 「계산을 멈췄습니다」를 말하면 둘이 어긋난다. 까닭은 본문 오류가
    말한다 — 여기는 멈췄다는 사실만 적는다.
    """
    _show_range_status(":material/block: 계산 멈춤")


def show_month_range_unavailable() -> None:
    """선택 범위에 데이터가 없어 계산이 서지 않았음을 같은 자리에 알린다.

    자리표시자는 rerun 을 넘어 남는다. 실패한 rerun 에서 아무것도 쓰지 않으면 직전에 성공한
    범위가 "적용" 으로 계속 보여 본문 오류와 어긋난다. 글자는 짧게 둔다 — 적용되지 않았다는
    것은 아이콘이, 어느 범위에 데이터가 있는지는 본문 오류가 말한다.
    """
    _show_range_status(":material/block: 데이터 없음")
