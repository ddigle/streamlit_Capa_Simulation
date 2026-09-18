# Purpose: 저장했다는 말이 rerun 을 건너 화면에 실제로 남는지 고정한다.

"""`st.success` 바로 뒤에 `st.rerun()` 을 부르면 그 문구는 **한 번도 그려지지 않는다.**

`rerun` 이 그 자리에서 실행을 끊고 화면을 처음부터 다시 그리기 때문이다. 사용자에게는
화면이 한 번 깜빡이고 제자리로 돌아온 것으로 보여서, 저장이 됐는지 알 수 없어 다시 누른다.
공용 프로필 편집기 열한 자리가 그 모양이었다.

아래 검사는 규칙이 아니라 **실제 Streamlit 실행**으로 본다 — 이 결함의 원인이 프레임워크의
실행 순서라 코드를 읽어서는 드러나지 않는다.
"""

import ast
from pathlib import Path

from streamlit.testing.v1 import AppTest

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
            for first, second in zip(body, body[1:]):
                if not (isinstance(first, ast.Expr) and isinstance(second, ast.Expr)):
                    continue
                head, tail = ast.unparse(first.value), ast.unparse(second.value)
                if head.startswith("st.success(") and tail.startswith("st.rerun("):
                    offenders.append(f"{path.name}:{first.lineno}")

    assert not offenders, (
        "성공 문구 바로 뒤에 rerun 이 있습니다 — 그 문구는 화면에 뜨지 않습니다. "
        "`components/flash.py` 의 `queue_flash` 로 옮기세요:\n" + "\n".join(offenders)
    )
