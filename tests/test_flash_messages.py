# Purpose: 알림이 rerun 을 건너 늘 서 있는 한 칸에 한 번 그려지고 그 길이 flash 하나인지 고정한다.

"""`st.success` 바로 뒤에 `st.rerun()` 을 부르면 그 문구는 **한 번도 그려지지 않는다.**

`rerun` 이 그 자리에서 실행을 끊고 화면을 처음부터 다시 그리기 때문이다. 사용자에게는
화면이 한 번 깜빡이고 제자리로 돌아온 것으로 보여서, 저장이 됐는지 알 수 없어 다시 누른다.
공용 프로필 편집기 열한 자리가 그 모양이었다.

아래 검사는 규칙이 아니라 **실제 Streamlit 실행**으로 본다 — 이 결함의 원인이 프레임워크의
실행 순서라 코드를 읽어서는 드러나지 않는다.

알림 칸은 모두 `components/flash.py` 를 지난다. 칸마다 꺼내 그리는 길이 따로 있으면 끊긴 회차·자리
밀림 같은 고침이 한 칸에만 가고 다른 칸에는 가지 않는다 — AST 그물이 그 꼴을 소스에서 찾는다.
"""

import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import capa_simulation.components.write_guard as write_guard

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = PROJECT_ROOT / "src" / "capa_simulation" / "components"

DIRECT = """
import streamlit as st

if st.session_state.get("go") is True:
    st.session_state["go"] = False
    st.success("저장했습니다.")
    st.rerun()
"""

QUEUED = """
import streamlit as st

from capa_simulation.components.flash import queue_flash, render_flash

render_flash("demo_flash")
if st.session_state.get("go") is True:
    st.session_state["go"] = False
    queue_flash("demo_flash", "저장했습니다.")
    st.rerun()
"""


def _messages(script: str) -> list[str]:
    app = AppTest.from_string(script)
    app.run()
    app.session_state["go"] = True
    app.run()
    assert not app.exception
    return [element.value for element in app.success]


def test_a_success_message_before_rerun_never_reaches_the_screen() -> None:
    """이 검사가 깨지면 Streamlit 이 동작을 바꾼 것이다 — 그때는 우회가 필요 없어진다."""
    assert _messages(DIRECT) == []


def test_a_queued_flash_survives_the_rerun() -> None:
    assert _messages(QUEUED) == ["저장했습니다."]


def test_a_flash_is_drawn_once_and_then_gone() -> None:
    """비우지 않으면 그 뒤 모든 rerun 에 남아 방금 저장한 것인지 알 수 없게 된다."""
    app = AppTest.from_string(QUEUED)
    app.run()
    app.session_state["go"] = True
    app.run()
    assert [element.value for element in app.success] == ["저장했습니다."]

    app.run()
    assert [element.value for element in app.success] == []


def test_no_component_announces_success_and_immediately_reruns() -> None:
    """같은 함정에 다시 빠지지 않게 한다.

    `st.success(...)` 다음 문장이 `st.rerun(...)` 인 자리를 소스에서 찾는다. 그런 자리는
    사용자가 그 문구를 볼 수 없으므로 `flash` 로 옮겨야 한다.
    """
    offenders: list[str] = []
    for path in sorted(COMPONENTS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list):
                continue
            for first, second in zip(body, body[1:], strict=False):
                if not (isinstance(first, ast.Expr) and isinstance(second, ast.Expr)):
                    continue
                head, tail = ast.unparse(first.value), ast.unparse(second.value)
                if head.startswith("st.success(") and tail.startswith("st.rerun("):
                    offenders.append(f"{path.name}:{first.lineno}")

    assert not offenders, (
        "성공 문구 바로 뒤에 rerun 이 있습니다 — 그 문구는 화면에 뜨지 않습니다. "
        "`components/flash.py` 의 `queue_flash` 로 옮기세요:\n" + "\n".join(offenders)
    )


SLOT = """
import streamlit as st

from capa_simulation.components.flash import queue_flash, render_flash

if st.session_state.get("go") is True:
    st.session_state["go"] = False
    queue_flash("demo_flash", "다시 넣으세요.", kind="warning", icon=":material/warning:")
    queue_flash("demo_flash_more", "바뀐 것이 없습니다.", kind="info")
slot = render_flash("demo_flash", "demo_flash_more")
if st.session_state.get("fail") is True:
    slot.error("같은 자리에 쓴 실패 문구")
st.button("뒤 형제", key="demo_after")
"""


def _after_index(app: AppTest) -> int:
    """`뒤 형제` 단추가 본문 몇째 자리인가."""
    (index,) = [
        index for index, node in app.main.children.items() if getattr(node, "type", "") == "button"
    ]
    return index


def test_render_flash_stands_one_slot_with_or_without_a_message() -> None:
    """알림이 있든 없든 칸 하나가 선다 — 뒤 형제의 자리가 알림 유무로 밀리지 않는다.

    밀리면 key 없는 팝오버·탭·확장 패널이 새로 서며 닫히고, key 있는 블록은 끊긴 회차의 옛 자리에
    흐린 사본을 남긴다(AGENTS 9장 「조건부 알림」).
    """
    app = AppTest.from_string(SLOT).run()
    assert not app.exception
    empty = (len(app.main.children), _after_index(app))
    assert not app.warning and not app.info

    app.session_state["go"] = True
    app.run()
    assert not app.exception
    assert (len(app.main.children), _after_index(app)) == empty
    assert [element.value for element in app.warning] == ["다시 넣으세요."]
    assert app.warning[0].proto.icon == ":material/warning:"
    assert [element.value for element in app.info] == ["바뀐 것이 없습니다."]

    app.run()
    assert (len(app.main.children), _after_index(app)) == empty
    assert not app.warning and not app.info


def test_the_returned_slot_takes_the_failure_of_the_same_action() -> None:
    """돌려받은 칸에 쓴 실패 문구는 알림과 같은 자리에 선다 — 성공과 실패가 한 자리에서 답한다."""
    empty = _after_index(AppTest.from_string(SLOT).run())
    app = AppTest.from_string(SLOT)
    app.session_state["fail"] = True
    app.run()
    assert not app.exception
    assert [element.value for element in app.error] == ["같은 자리에 쓴 실패 문구"]
    assert _after_index(app) == empty


KINDS = """
import streamlit as st

from capa_simulation.components.flash import queue_flash, render_flash

for kind in ("success", "info", "warning", "error"):
    queue_flash(f"demo_{kind}", f"{kind} 알림", kind=kind, icon=":material/info:")
queue_flash("demo_plain", "글만 담은 성공")
st.session_state["plain_shape"] = st.session_state["demo_plain"]
render_flash("demo_success", "demo_info", "demo_warning", "demo_error", "demo_plain")
"""


def test_each_kind_is_drawn_with_its_icon_and_a_plain_success_keeps_the_text_shape() -> None:
    """종류마다 그 요소로 그린다. 아이콘 없는 성공은 글만 담는다 — 그 칸을 글로 읽는 도우미가
    있다."""
    app = AppTest.from_string(KINDS).run()
    assert not app.exception
    assert [element.value for element in app.success] == ["success 알림", "글만 담은 성공"]
    assert [element.proto.icon for element in app.success] == [":material/info:", ""]
    assert [element.value for element in app.info] == ["info 알림"]
    assert [element.value for element in app.warning] == ["warning 알림"]
    assert [element.value for element in app.error] == ["error 알림"]
    assert app.session_state["plain_shape"] == "글만 담은 성공"


def test_an_unknown_kind_is_refused() -> None:
    script = """
from capa_simulation.components.flash import queue_flash

queue_flash("demo_flash", "글", kind="notice")
"""
    app = AppTest.from_string(script).run()
    assert app.exception and "알 수 없는 알림 종류" in app.exception[0].message


# flash.py 밖에서 알림 칸(이름에 FLASH·NOTICE 가 든 세션 칸, 또는 이름에 flash·notice 가 든 함수가
# 꺼내는 칸)을 꺼내는 자리 가운데 이 모듈을 지나지 않는 것과 그 까닭. (파일, 꺼내는 칸의 식) → 까닭.
# 자리가 사라지면 여기서도 지운다(`test_every_allowed_pop_is_still_there`).
FLASH_POP_ALLOWED: dict[tuple[str, str], str] = {
    ("app_pages/voc.py", "GONE_NOTICE_KEY"): (
        "다음 동작까지 남는 꼴 — 지운 글의 거절과 함께 적어 둔 답변을 되살릴 입력으로 든다"
    ),
    ("app_pages/voc.py", "FLASH_KEY"): (
        "지운 글 칸(GONE_NOTICE_KEY)과 한 알림 칸·차례이고, 빠른 두 번 누름 알림(3회차)과 위젯 세대"
        " 갈래가 이 칸을 함께 고친다 — 그 고침이 들어간 뒤 옮긴다"
    ),
    ("src/capa_simulation/components/shortening_progress_panel.py", "_BASELINE_NOTICE_KEY"): (
        "다음 동작까지 남는 꼴 — 기준선 알림은 이벤트 칸 자리 수를 고정하고 같은 알림을 한 번만"
        " 세는 shown 칸과 짝이다"
    ),
    ("app_pages/reference_data.py", "'capacity_step_flash'"): (
        "매 회차 비우고 STEP 탭을 그리는 회차에만 그린다 — 숨은 회차에 남은 알림을 나중에 띄우지"
        " 않는다(`tests/test_reference_data_perf.py`)"
    ),
    ("src/capa_simulation/components/month_editor.py", "f'{editor_key}_apply_flash'"): (
        "`st.empty` 한 자리 — 페이지가 같은 자리에 적용 오류를 덮어 쓴다(`editor_notice`)"
    ),
    ("src/capa_simulation/components/month_editor.py", "_notice_key(editor_key)"): (
        "알림이 아니라 그 자리(`st.empty`) 손잡이를 비운다"
    ),
    ("app_pages/load_conversion.py", "key"): (
        "그리는 자리가 아이콘을 정한다 — 담는 도우미(`queue_reference_import_flash`)를 기준정보"
        " 편집기와 함께 쓰고 아이콘이 다르다. 담는 쪽이 아이콘을 받게 한 뒤 옮긴다"
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "FLASH_KEY"): (
        "알림을 그리는 회차에 팝오버 세대를 함께 올린다(`POPOVER_GENERATION_KEY`) — 그린 줄 알아야"
        " 하는 칸이다"
    ),
    ("src/capa_simulation/components/equipment_scenario_status.py", "FLASH_KEY"): (
        "사이드바 설비 시나리오 줄 슬롯 안 — 저장 대조·위젯 세대 갈래가 이 파일을 함께 고친다. 그"
        " 고침이 들어간 뒤 옮긴다"
    ),
}
FLASH_OWNER = COMPONENTS / "flash.py"


def _flash_pops() -> dict[tuple[str, str], int]:
    """flash.py 밖에서 알림 칸을 꺼내는 자리 (파일, 칸의 식) → 줄."""
    sources = [
        PROJECT_ROOT / "app.py",
        *sorted((PROJECT_ROOT / "app_pages").glob("*.py")),
        *sorted((PROJECT_ROOT / "src").rglob("*.py")),
    ]
    found: dict[tuple[str, str], int] = {}
    for path in sources:
        if path == FLASH_OWNER:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scopes: list[tuple[str, ast.AST]] = [("", tree)]
        scopes += [
            (node.name, node)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for name, scope in scopes:
            for node in ast.walk(scope):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "pop"
                    and ast.unparse(node.func.value).endswith("session_state")
                    and node.args
                ):
                    continue
                key = ast.unparse(node.args[0])
                named = any(word in key.upper() for word in ("FLASH", "NOTICE"))
                in_flash_helper = any(word in name.lower() for word in ("flash", "notice"))
                if named or in_flash_helper:
                    found.setdefault((path.relative_to(PROJECT_ROOT).as_posix(), key), node.lineno)
    return found


def test_notice_slots_are_popped_and_drawn_only_through_flash() -> None:
    """알림 칸을 칸마다 꺼내 그리면 끊긴 회차·자리 밀림 고침이 그 칸에 가지 않는다.

    이름에 FLASH·NOTICE 가 든 세션 칸을 flash.py 밖에서 꺼내는(`session_state.pop`) 자리를 찾는다 —
    꺼내 그리는 것도, 꺼내 넘겨 다른 곳이 그리는 것(옛 `pop_discarded_notice`)도 같다. 담기는
    `queue_flash`, 그리기는 `render_flash` 다. 수명이 다른 칸만 까닭을 적어 허용한다.
    """
    offenders = [
        f"{path}:{line} ({key})"
        for (path, key), line in sorted(_flash_pops().items())
        if (path, key) not in FLASH_POP_ALLOWED
    ]

    assert not offenders, (
        "알림 칸을 flash.py 밖에서 꺼냅니다 — `queue_flash` 로 담고 `render_flash` 로 그리세요"
        "(수명이 다르면 FLASH_POP_ALLOWED 에 까닭과 함께):\n" + "\n".join(offenders)
    )


def test_every_allowed_pop_is_still_there() -> None:
    """허용 목록이 옮긴 자리를 붙들고 있으면 같은 꼴이 그 이름으로 되돌아와도 그물을 지난다."""
    stale = sorted(set(FLASH_POP_ALLOWED) - set(_flash_pops()))

    assert not stale, f"사라진 자리입니다 — FLASH_POP_ALLOWED 에서 지우세요: {stale}"


def test_the_slot_from_render_flash_is_not_read_as_drew_or_not() -> None:
    """`render_flash` 는 늘 칸 하나를 돌려준다 — 그 칸은 언제나 참이다.

    예전에는 그렸으면 True 를 돌려줘 `if render_flash(...)` 로 「담아 둔 알림이 없을 때만」 다른
    글을 그리는 자리가 있을 수 있었다. 지금 그렇게 쓰면 그 갈래가 소리 없이 죽는다. 그렸는지 미리
    알아야 하면 `pending_flash` 로 먼저 본다.
    """
    offenders: list[str] = []
    for path in [
        PROJECT_ROOT / "app.py",
        *sorted((PROJECT_ROOT / "app_pages").glob("*.py")),
        *sorted((PROJECT_ROOT / "src").rglob("*.py")),
    ]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            tests: list[ast.expr] = []
            if isinstance(node, (ast.If, ast.While, ast.IfExp, ast.Assert)):
                tests.append(node.test)
            elif isinstance(node, ast.BoolOp):
                tests.extend(node.values)
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                tests.append(node.operand)
            for test in tests:
                if (
                    isinstance(test, ast.Call)
                    and isinstance(test.func, ast.Name | ast.Attribute)
                    and ast.unparse(test.func).split(".")[-1] == "render_flash"
                ):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT).as_posix()}:{test.lineno}")

    assert not offenders, (
        "render_flash 의 돌려준 칸은 늘 참입니다 — 그렸는지는 pending_flash 로 먼저 보세요:\n"
        + "\n".join(offenders)
    )


HELD = """
import streamlit as st
from streamlit.runtime.scriptrunner_utils.exceptions import StopException

from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.write_guard import note_notice, notice_marks


def _delete() -> None:
    # 쓰기 전에 표지 dict 를 받고 쓰기 직후 적는다 — 그 뒤 세션 칸 쓰기는 끊길 수 있다.
    marks = notice_marks()
    st.session_state["deleted"] = st.session_state.get("deleted", 0) + 1
    note_notice(marks, "demo_flash", "지웠습니다.")
    if st.session_state.get("cut") is True:
        raise StopException()
    queue_flash("demo_flash", "지웠습니다.")


render_flash("demo_flash")
st.button(
    "지우기",
    key="demo_delete",
    on_click=_delete,
    disabled=st.session_state.get("deleted", 0) > 0,
)
"""


@pytest.mark.parametrize(("window", "kept"), [(3600.0, True), (0.0, False)])
def test_a_quick_second_press_on_a_locked_button_keeps_the_notice(
    monkeypatch: pytest.MonkeyPatch, window: float, kept: bool
) -> None:
    """아주 빠른 둘째 누름은 옛 화면의 단추에 닿는데 그 회차에는 단추가 잠겨 Streamlit 이 누름을
    버린다 — 그 회차가 앞 회차가 꺼내 그린 알림을 지웠다(2026-10-26 E2E). 쓰기 직후 적어 둔 알림은
    창(`TRAILING_PRESS_SECONDS`) 안이면 `render_flash` 가 다시 그린다. AppTest 는 누른 화면의 위젯
    값을 붙잡아 한 번 더 보낸다(창은 시험이 정한다)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    app = AppTest.from_string(HELD).run()
    app.button(key="demo_delete").click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert [element.value for element in app.success] == ["지웠습니다."]

    app._run(widget_state=pressed)

    assert not app.exception, [element.message for element in app.exception]
    assert app.session_state["deleted"] == 1
    assert [element.value for element in app.success] == (["지웠습니다."] if kept else [])


@pytest.mark.parametrize(("window", "kept"), [(3600.0, True), (0.0, False)])
def test_a_notice_noted_before_a_cut_callback_reaches_the_last_screen(
    monkeypatch: pytest.MonkeyPatch, window: float, kept: bool
) -> None:
    """첫 회차가 끊겨도 마지막 화면에 알림이 남는다 — 3회차 경합 시험(`tests/test_voc_page.py`
    `_race`)의 flash 단위 꼴.

    둘째 누름이 닿으면 Streamlit 은 돌던 회차에 멈춤을 걸고, 멈춤을 받은 첫 콜백은 쓴 뒤 다음 세션
    칸 접근에서 `StopException` 으로 끊겨 `queue_flash` 에 닿지 못한다. 쓰기 직후 dict 에 적어 둔
    알림(`note_notice`)은 끊기지 않아 둘째 회차의 `render_flash` 가 그린다.
    """
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    app = AppTest.from_string(HELD)
    app.session_state["cut"] = True
    app.run()
    app.button(key="demo_delete").click().run()
    assert app.session_state["deleted"] == 1
    assert "demo_flash" not in app.session_state

    app.run()

    assert not app.exception, [element.message for element in app.exception]
    assert app.session_state["deleted"] == 1
    assert [element.value for element in app.success] == (["지웠습니다."] if kept else [])
