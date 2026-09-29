# Purpose: 시나리오를 불러와도 보던 탭과 조회 조건이 그대로 남는지 고정한다.

"""보던 자리는 그대로, 데이터만 바뀐다.

「불러오기」는 **사이드바**에 있고 `st.rerun()` 을 부른다. 그 호출은 그 자리에서 실행을
끊으므로 **페이지 본문은 그 회차에 아예 돌지 않는다.** Streamlit 은 한 회차에 만들어지지
않은 위젯의 값을 버리기 때문에, 효율 탭에서 필터를 걸어 두고 시나리오를 바꾸면 첫 탭에
기본 필터로 돌아간다. 사용자가 「처음 열었을 때로 돌아간다」고 말한 것이 이것이다.

두 가지로 막는다.

- 탭: `stateful_tabs` 가 열린 탭을 위젯이 아닌 칸에 적어 두고, 위젯 값이 사라졌을 때만
  되돌려 놓는다.
- 조회 조건: 위젯에 `persist_state="session"` 을 준다. 화면에서 사라져도 값이 남는다.

아래 검사는 그 두 장치가 **실제 Streamlit 실행에서** 듣는지 본다. 규칙이 아니라 동작이다.
"""

from streamlit.testing.v1 import AppTest

from capa_simulation.components.tab_state import remembered_tab_key

# app.py 의 순서를 그대로 흉내낸다 — 사이드바가 먼저 돌고, 그 안에서 rerun 이 걸린다.
SCRIPT = """
import streamlit as st

from capa_simulation.components.tab_state import stateful_tabs

LABELS = ("UPEH", "효율", "여유율")

with st.sidebar:
    if st.session_state.get("load_clicked") is True:
        st.session_state["load_clicked"] = False
        st.session_state["load_count"] = int(st.session_state.get("load_count", 0)) + 1
        st.rerun()

tabs = stateful_tabs(LABELS, key="page_tab")
st.multiselect("공정", ["P1", "P2", "P3"], key="page_filter", persist_state="session")
st.toggle("상세", key="page_detail", persist_state="session")
st.session_state["open_labels"] = [
    label for label, tab in zip(LABELS, tabs, strict=True) if tab.open
]
"""


def _app() -> AppTest:
    app = AppTest.from_string(SCRIPT)
    app.run()
    return app


def _state(app: AppTest, key: str) -> object:
    return app.session_state[key] if key in app.session_state else None


def test_the_open_tab_survives_a_sidebar_reload() -> None:
    app = _app()
    assert _state(app, "open_labels") == ["UPEH"]

    app.session_state["page_tab"] = "효율"
    app.run()
    assert _state(app, "open_labels") == ["효율"]

    app.session_state["load_clicked"] = True
    app.run()

    assert not app.exception
    assert _state(app, "load_count") == 1
    assert _state(app, "open_labels") == ["효율"], "불러오기가 탭을 첫 칸으로 되돌렸습니다."


def test_the_query_conditions_survive_a_sidebar_reload() -> None:
    app = _app()
    app.session_state["page_filter"] = ["P2"]
    app.session_state["page_detail"] = True
    app.run()

    app.session_state["load_clicked"] = True
    app.run()

    assert _state(app, "page_filter") == ["P2"]
    assert _state(app, "page_detail") is True


def test_the_remembered_tab_is_not_the_widget_itself() -> None:
    """기억 칸은 위젯 키와 **달라야** 한다. 같으면 위젯이 사라질 때 함께 사라진다."""
    app = _app()
    app.session_state["page_tab"] = "여유율"
    app.run()

    memory = remembered_tab_key("page_tab")
    assert memory != "page_tab"
    assert _state(app, memory) == "여유율"


def test_switching_tabs_updates_the_memory() -> None:
    """기억이 첫 선택에 박히면 그 뒤로 어느 탭을 골라도 불러오기가 그리로 되돌린다."""
    app = _app()
    memory = remembered_tab_key("page_tab")

    for label in ("효율", "여유율", "UPEH"):
        app.session_state["page_tab"] = label
        app.run()
        assert _state(app, memory) == label

        app.session_state["load_clicked"] = True
        app.run()
        assert _state(app, "open_labels") == [label]


# 토글은 반대다 — 시나리오를 바꾸면 **풀려야** 한다. 두 규칙이 한 화면에서 함께 돌므로
# 한쪽을 고칠 때 다른 쪽이 조용히 따라 바뀌지 않는지 여기서 같이 본다.
TOGGLE_SCRIPT = """
import streamlit as st

from capa_simulation.components.tab_state import stateful_tabs

LABELS = ("UPEH", "효율")

with st.sidebar:
    if st.session_state.get("load_clicked") is True:
        st.session_state["load_clicked"] = False
        # `activate_persisted_snapshot` 이 하는 일과 같다.
        for key in st.session_state.get("stale_keys", ()):
            st.session_state.pop(key, None)
        st.rerun()

stateful_tabs(LABELS, key="page_tab")
st.session_state["seen_toggle"] = st.toggle(
    "선행 전망", value=False, key="home_show_advance", persist_state="session"
)
"""


def test_a_toggle_is_released_even_though_it_persists() -> None:
    """`persist_state="session"` 이 `pop` 을 무력화하지 않는다.

    토글이 화면에서 사라져도 값이 남게 하는 것과, 시나리오를 바꿀 때 그 값을 버리는 것은
    서로 다른 장치다. 둘이 부딪히면 토글이 영영 안 꺼지므로 실제 실행으로 확인한다.
    """
    app = AppTest.from_string(TOGGLE_SCRIPT)
    app.session_state["stale_keys"] = ("home_show_advance",)
    app.run()
    app.session_state["home_show_advance"] = True
    app.run()
    assert _state(app, "seen_toggle") is True

    app.session_state["load_clicked"] = True
    app.run()

    assert not app.exception
    assert _state(app, "seen_toggle") is False, "시나리오를 바꿔도 토글이 켜진 채 남았습니다."


def test_the_tab_survives_the_same_reload_that_releases_the_toggle() -> None:
    """같은 한 번의 불러오기에서 토글은 풀리고 탭은 남아야 한다."""
    app = AppTest.from_string(TOGGLE_SCRIPT)
    app.session_state["stale_keys"] = ("home_show_advance",)
    app.run()
    app.session_state["page_tab"] = "효율"
    app.session_state["home_show_advance"] = True
    app.run()

    app.session_state["load_clicked"] = True
    app.run()

    assert _state(app, "seen_toggle") is False
    assert _state(app, remembered_tab_key("page_tab")) == "효율"
