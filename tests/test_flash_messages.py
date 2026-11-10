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
from collections.abc import Mapping
from pathlib import Path

import pytest
from alert_marks import alert_notes, flashed, successes, texts
from streamlit.testing.v1 import AppTest

import capa_simulation.components.write_guard as write_guard
from capa_simulation import alerts

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
    """화면에 그린 성공 글과 알림창 표지에 실린 성공 결과 알림(D3 — 성공은 알림창으로만 낸다)."""
    app = AppTest.from_string(script)
    app.run()
    app.session_state["go"] = True
    app.run()
    assert not app.exception
    return texts(successes(app))


def test_a_success_message_before_rerun_never_reaches_the_screen() -> None:
    """이 검사가 깨지면 Streamlit 이 동작을 바꾼 것이다 — 그때는 우회가 필요 없어진다."""
    assert _messages(DIRECT) == []


def test_a_queued_flash_survives_the_rerun() -> None:
    assert _messages(QUEUED) == ["저장했습니다."]


def test_a_flash_is_drawn_once_and_then_gone() -> None:
    """비우지 않으면 그 뒤 모든 rerun 에 남아 방금 저장한 것인지 알 수 없게 된다. 다음 회차가 같은
    id 로 한 번 더 보내는 표지(`again` — 끊긴 회차를 덮는다)는 브라우저가 다시 띄우지 않는다."""
    app = AppTest.from_string(QUEUED)
    app.run()
    app.session_state["go"] = True
    app.run()
    assert texts(successes(app)) == ["저장했습니다."]
    (first,) = alert_notes(app)

    app.run()
    assert texts(successes(app)) == []
    (again,) = alert_notes(app, again=True)
    assert again["again"] is True and again["id"] == first["id"]


def test_a_success_is_sent_to_the_alert_popup_and_not_drawn_beside_the_button() -> None:
    """D3 (가) — 성공 · 안내는 알림창 하나로 낸다. 버튼 곁 칸에는 그리지 않는다(같은 글이 두 번
    보이지 않게). 표지는 종류별 기본 코드 · 화면 · 담은 칸 이름을 싣는다."""
    app = AppTest.from_string(QUEUED)
    app.run()
    app.session_state["go"] = True
    app.run()
    assert not app.success
    (note,) = alert_notes(app)
    assert note["code"] == alerts.FLASH_CODES["success"] == "FL-01"
    assert note["kind"] == "event" and note["level"] == "info"
    assert note["flash"] == "success" and note["origin"] == "demo_flash"
    assert note["short"] == note["full"] == "저장했습니다."
    assert isinstance(note["id"], str) and note["id"]


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
    # 경고는 버튼 곁에도, 안내는 알림창으로만(D3).
    assert [element.value for element in app.warning] == ["다시 넣으세요."]
    assert app.warning[0].proto.icon == ":material/warning:"
    assert not app.info
    assert texts(flashed(app)) == ["다시 넣으세요.", "바뀐 것이 없습니다."]

    app.run()
    assert (len(app.main.children), _after_index(app)) == empty
    assert not app.warning and not app.info and not flashed(app)


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
    """경고 · 오류는 그 요소로 버튼 곁에 그리고(D3 — 오류 · 거부만), 넷 모두 알림창 표지에 종류별
    기본 코드 · 단계로 싣는다. 아이콘 없는 성공은 글만 담는다 — 그 칸을 글로 읽는 도우미가 있다."""
    app = AppTest.from_string(KINDS).run()
    assert not app.exception
    assert not app.success and not app.info
    assert [element.value for element in app.warning] == ["warning 알림"]
    assert [element.proto.icon for element in app.warning] == [":material/info:"]
    assert [element.value for element in app.error] == ["error 알림"]
    assert [(item.value, item.code, item.note and item.note["level"]) for item in flashed(app)] == [
        ("success 알림", "FL-01", "info"),
        ("info 알림", "FL-02", "info"),
        ("warning 알림", "FL-03", "check"),
        ("error 알림", "FL-04", "error"),
        ("글만 담은 성공", "FL-01", "info"),
    ]
    assert app.session_state["plain_shape"] == "글만 담은 성공"


def test_a_popup_only_warning_goes_to_the_alert_popup_and_not_beside_the_button() -> None:
    """`popup_only` 경고는 버튼 곁에 그리지 않고 알림창 표지로만 보낸다 — 동작은 끝났고 그 자리에
    고칠 입력이 없는 경고(사이드바 리비전 저장 뒤 소요대수에 들지 않은 수요 — 2026-11-04 검수 의견
    home-18). 단계는 경고 기본(`FL-03` 확인 필요)이다."""
    script = """
from capa_simulation.components.flash import queue_flash, render_flash

queue_flash(
    "demo_flash", "빠진 수요 2건", kind="warning", icon=":material/warning:", popup_only=True
)
render_flash("demo_flash")
"""
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert not app.warning
    assert [(item.value, item.code, item.note and item.note["level"]) for item in flashed(app)] == [
        ("빠진 수요 2건", "FL-03", "check")
    ]


def test_a_flash_can_point_its_goto_at_another_screen_and_tab() -> None:
    """목록이 다른 화면에 있는 결과 알림은 `goto` 로 그 화면 · 탭을 싣는다 — 줄의 「그 화면으로」 가
    낸 화면 대신 그 탭을 연다(u3-04 — 소요대수에 들지 않은 수요 → 산출 결과 › 소요대수). 탭 없는
    두 칸 꼴도 받고, 주지 않으면 낸 화면(`note_page`)이다. 세션 칸은 튜플이라 코드를 다시 읽은
    서버도 그대로 읽는다."""
    script = """
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.flash import queue_flash, render_flash

alerts.note_page("시나리오 관리", "scenario_management")
queue_flash(
    "with_tab",
    "빠진 수요 2건",
    kind="warning",
    popup_only=True,
    goto=("산출 결과", "calculation_result", "소요대수"),
)
queue_flash("no_tab", "다른 화면 성공", goto=("기준 정보", "reference_data"))
queue_flash("here", "제자리 경고", kind="warning", popup_only=True)
st.session_state["shape"] = st.session_state["no_tab"]
st.session_state["old"] = ("warning", "옛 칸", None, None, True, (), ["깨진", "화면"])
render_flash("with_tab", "no_tab", "here", "old")
"""
    app = AppTest.from_string(script).run()
    assert not app.exception
    pages = [
        (item.value, item.note["page"], item.note["href"], item.note.get("tab", ""))
        for item in flashed(app)
        if item.note is not None
    ]
    assert pages == [
        ("빠진 수요 2건", "산출 결과", "calculation_result", "소요대수"),
        ("다른 화면 성공", "기준 정보", "reference_data", ""),
        ("제자리 경고", "시나리오 관리", "scenario_management", ""),
        ("옛 칸", "시나리오 관리", "scenario_management", ""),
    ]
    # 화면을 실은 성공은 글만 담는 꼴이 아니다 — 화면 칸을 잃지 않는다.
    assert isinstance(app.session_state["shape"], tuple)


def test_render_flash_writes_exactly_one_event_slot_with_or_without_alerts() -> None:
    """표지는 부를 때마다 이벤트 칸에 정확히 한 자리다 — 알림이 없으면 빈 스타일. 프래그먼트 · 팝업
    본문의 이벤트 칸 자리 수가 갈래와 상관없이 같아야 한다(AGENTS 9장)."""
    app = AppTest.from_string(SLOT).run()
    quiet = [element.proto.body for element in app.get("html")]
    assert quiet == ["<style></style>"]
    app.session_state["go"] = True
    app.run()
    loud = [element.proto.body for element in app.get("html")]
    assert len(loud) == 1 and loud[0].startswith(f"<style {alerts.MARKER_ATTRIBUTE}=")


def test_emit_flash_sends_to_the_alert_popup_without_a_slot_in_one_event_slot() -> None:
    """칸이 서지 않는 자리(닫힌 팝업의 호스트)의 알림은 표지로만 나가고 비워진다. 경고도 곁에
    그리지 않고, 칸을 세우지 않으며, 알릴 것이 없어도 이벤트 칸은 빈 스타일 한 자리다."""
    script = """
import streamlit as st

from capa_simulation.components.flash import emit_flash, queue_flash

if st.session_state.pop("queue", False):
    queue_flash("demo_flash", "거절됐습니다", kind="warning")
emit_flash("demo_flash")
"""
    app = AppTest.from_string(script, default_timeout=30)
    app.session_state["queue"] = True
    app.run()
    assert not app.exception
    assert [note["full"] for note in alert_notes(app)] == ["거절됐습니다"]
    assert not app.warning
    assert not app.get("container")
    assert len(app.get("html")) == 1
    assert "demo_flash" not in app.session_state

    app.run()
    assert not app.exception
    assert not app.warning
    assert len(app.get("html")) == 1


def test_a_queued_alert_code_must_be_a_registered_event_code() -> None:
    """칸마다 코드를 따로 두면 등록부의 사건 코드여야 한다 — 상태 코드 · 없는 코드는 담지 않는다."""
    script = """
from capa_simulation.components.flash import queue_flash, render_flash

queue_flash("demo_flash", "탭은 열 개까지", kind="warning", alert="TAB-01")
render_flash("demo_flash")
"""
    app = AppTest.from_string(script).run()
    assert not app.exception
    (item,) = flashed(app)
    assert item.code == "TAB-01" and item.note is not None and item.note["level"] == "action"
    refused = AppTest.from_string(
        "from capa_simulation.components.flash import queue_flash\n"
        'queue_flash("k", "글", alert="NO-99")'
    ).run()
    assert refused.exception


def test_an_unknown_kind_is_refused() -> None:
    script = """
from capa_simulation.components.flash import queue_flash

queue_flash("demo_flash", "글", kind="notice")
"""
    app = AppTest.from_string(script).run()
    assert app.exception and "알 수 없는 알림 종류" in app.exception[0].message


# flash.py 밖에서 알림 칸을 꺼내는 자리 가운데 이 모듈을 지나지 않는 것과 그 까닭.
# (파일, 함수 — 모듈 본문은 "", 꺼내는 칸의 식) → 까닭. 함수까지 적어 같은 이름의 흔한 변수(`key`)를
# 꺼내는 새 자리가 다른 함수에서 허용을 빌리지 못하게 한다. 자리가 사라지면 여기서도 지운다
# (`test_every_allowed_pop_is_still_there`).
FLASH_POP_ALLOWED: dict[tuple[str, str, str], str] = {
    ("app_pages/reference_data.py", "", "'capacity_step_flash'"): (
        "매 회차 비우고 STEP 탭을 그리는 회차에만 알림창 표지로 보낸다(`alerts.emit` — 성공이라"
        " 버튼 곁에는 그리지 않는다, D3) — 숨은 회차에 남은 알림을 나중에 띄우지 않는다"
        "(`tests/test_reference_data_perf.py`)"
    ),
    (
        "src/capa_simulation/components/equipment_scenario_management.py",
        "render_equipment_scenario_management",
        "CLEAR_LAYOUT_AGREED_KEY",
    ): (
        "알림 칸이 아니라 앞 회차에 켠 「배치 차이 모두 지우기」 확인 체크의 값(시나리오·최신"
        " id·번호 — 되돌리기 `RESTORE_AGREED_KEY` 와 같은 꼴)이다. 회차마다 꺼내 지금 최신과"
        " 견주고, 체크가 풀렸으면 그 까닭(「r2 → 지금 r3」)을 같은 회차에 체크 칸 위나 단추가"
        " 사라진 자리에 그린다"
    ),
    (
        "src/capa_simulation/components/shortening_board.py",
        "render_highlight_notice",
        "_REVEAL_NONCE_KEY",
    ): (
        "알림 칸이 아니라 보드 줄을 고른 회차의 카드 굴림 표지다 — 글이 없고 그 회차에 한 번 꺼내"
        " 스크롤 컴포넌트에 넘긴다. 함수 이름의 notice 는 카드 위 강조 줄을 가리킨다"
    ),
    ("app_pages/space_status.py", "_render_unsaved_layout_panel", "SAVE_ERROR_KEY"): (
        "배치 저장 실패는 회차의 상자 유무로 두 자리 가운데 하나에 선다 — 저장 안 한 상자가"
        " 서면 상자 안(상자 꼴마다 머리 글이 「배치를 저장하지 못했습니다」·「저장하지"
        " 못했습니다」 로 다르다), 없으면 잠금 줄 칸이다. 버리기 콜백이 남은 실패를 비운다"
    ),
    ("app_pages/space_status.py", "", "SAVE_ERROR_KEY"): (
        "같은 배치 저장 실패의 둘째 자리 — 저장 안 한 상자가 없는 회차에만 잠금 줄 칸(늘 서 있는"
        " `space_edit_lock_slot`)에서 꺼낸다"
    ),
    (
        "src/capa_simulation/components/equipment_data_workspace.py",
        "dismiss_discarded_notice",
        "DISCARDED_NOTICE_KEY",
    ): (
        "닫을 때까지 남는 꼴 — 남의 저장이 내 편집을 버렸다는 경고는 「알림 닫기」 를 누를 때까지"
        " 선다(한 회차만 서면 늦게 본 사람이 까닭을 모른다, E2E #66). 그리기는 늘 서 있는"
        " `render_reopen_notices` 칸이고 읽기만 한다 — 이 닫기 콜백만 비운다"
    ),
    (
        "src/capa_simulation/components/display_order_management.py",
        "_render_label_warnings",
        "LABEL_WARNINGS_KEY",
    ): (
        "한 저장의 표시명 실수 여러 줄(dict) — 알림 하나가 아니다. 저장 성공 칸"
        '(`render_flash("display_order_flash")` 가 돌려준 칸) 안에 그려 자리는 그 칸이 고정한다'
    ),
}
FLASH_OWNER = COMPONENTS / "flash.py"
# 알림을 그리는 요소. 로거의 `error`·`warning` 은 화면이 아니다.
_ALERTS = frozenset({"success", "info", "warning", "error", "exception", "toast"})
_LOGGERS = frozenset({"logger", "logging", "log"})
_BLOCK_FIELDS = ("body", "orelse", "finalbody", "handlers", "cases")


def _is_state(expr: ast.expr) -> bool:
    return ast.unparse(expr).endswith("session_state")


def _read_key(node: ast.AST) -> str | None:
    """세션 칸을 읽는 식(`session_state.pop/get(칸)`·`session_state[칸]`)이면 그 칸의 식."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("pop", "get")
        and _is_state(node.func.value)
        and node.args
    ):
        return ast.unparse(node.args[0])
    if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) and _is_state(node.value):
        return ast.unparse(node.slice)
    return None


def _cleared_keys(node: ast.AST) -> list[str]:
    """세션 칸을 비우는 식(`session_state.pop(칸)`·`del session_state[칸]`)이 비우는 칸들."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "pop"
        and _is_state(node.func.value)
        and node.args
    ):
        return [ast.unparse(node.args[0])]
    if isinstance(node, ast.Delete):
        return [
            ast.unparse(target.slice)
            for target in node.targets
            if isinstance(target, ast.Subscript) and _is_state(target.value)
        ]
    return []


def _scope_nodes(scope: ast.AST) -> list[ast.AST]:
    """`scope` 안의 노드 — 안쪽 함수는 제 스코프라 넣지 않는다."""
    found: list[ast.AST] = []
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        found.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return found


def _level_nodes(statement: ast.stmt) -> list[ast.AST]:
    """문장의 제 단 노드 — 복합 문장(`if`·`with`·`for` …)은 머리 식만이다(안쪽 블록은 제 단)."""
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return []
    nodes: list[ast.AST] = [statement]
    for field, value in ast.iter_fields(statement):
        if field in _BLOCK_FIELDS:
            continue
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, ast.AST):
                nodes.extend(ast.walk(item))
    return nodes


def _blocks(scope: ast.AST, nodes: list[ast.AST]) -> list[list[ast.AST]]:
    """스코프의 블록(본문·갈래·`with`·`for` 안 …)마다 그 단의 노드(`_level_nodes`)."""
    blocks: list[list[ast.stmt]] = [getattr(scope, "body", [])]
    for node in nodes:
        for field in _BLOCK_FIELDS:
            block = getattr(node, field, None)
            if isinstance(block, list):
                blocks.append([item for item in block if isinstance(item, ast.stmt)])
    return [[node for statement in block for node in _level_nodes(statement)] for block in blocks]


def _reads(nodes: list[ast.AST]) -> dict[int, tuple[str, int]]:
    """세션 칸을 읽는 식 (노드 id → (칸, 줄)) — `pop`·`get`·`[]`."""
    reads: dict[int, tuple[str, int]] = {}
    for node in nodes:
        key = _read_key(node)
        if key is not None and isinstance(node, (ast.Call, ast.Subscript)):
            reads[id(node)] = (key, node.lineno)
    return reads


def _taken(blocks: list[list[ast.AST]]) -> dict[int, tuple[str, int]]:
    """스코프에서 칸을 **꺼내는** 읽기 (노드 id → (칸, 줄)).

    `pop` 은 늘 꺼내기다. `get`·`[]` 읽기는 같은 단(한 블록)에서 그 칸을 비울 때만 꺼내기다 —
    `get` 뒤 `del` 로 되돌린 옛 꼴은 잡고, 고른 값을 읽다가 맞지 않을 때만 갈래 안에서 비우는
    칸(선택 주소·확인 대기)은 꺼내기가 아니다. 바깥에서 읽어 두고 갈래 안에서 비우며 그 자리에서
    그리는 꼴은 `_cleared_and_drawn` 이 본다.
    """
    taken: dict[int, tuple[str, int]] = {}
    for level in blocks:
        cleared = {key for node in level for key in _cleared_keys(node)}
        for node in level:
            key = _read_key(node)
            if key is None or not isinstance(node, (ast.Call, ast.Subscript)):
                continue
            popped = (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "pop"
            )
            if popped or key in cleared:
                taken[id(node)] = (key, node.lineno)
    return taken


def _sources(
    expr: ast.AST, taken: dict[int, tuple[str, int]], carried: dict[str, set[tuple[str, int]]]
) -> set[tuple[str, int]]:
    """`expr` 에 든 꺼낸 칸 (칸, 꺼낸 줄) — 꺼내는 식 그 자체와 그 값을 이어 받은 이름."""
    keys: set[tuple[str, int]] = set()
    for sub in ast.walk(expr):
        if id(sub) in taken:
            keys.add(taken[id(sub)])
        elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            keys |= carried.get(sub.id, set())
    return keys


def _carried(
    nodes: list[ast.AST], taken: dict[int, tuple[str, int]]
) -> dict[str, set[tuple[str, int]]]:
    """꺼낸 칸의 값을 이어 받은 이름(대입·풀어 받기·`for` 줄기) → 그 칸들. 더 늘지 않을 때까지."""
    carried: dict[str, set[tuple[str, int]]] = {}
    changed = True
    while changed:
        changed = False
        for node in nodes:
            pairs: list[tuple[ast.AST, ast.AST]] = []
            if isinstance(node, ast.Assign):
                pairs = [(target, node.value) for target in node.targets]
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
                if node.value is not None:
                    pairs = [(node.target, node.value)]
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                pairs = [(node.target, node.iter)]
            for target, value in pairs:
                keys = _sources(value, taken, carried)
                for stored in ast.walk(target):
                    if not (isinstance(stored, ast.Name) and isinstance(stored.ctx, ast.Store)):
                        continue
                    if not keys <= carried.get(stored.id, set()):
                        carried[stored.id] = carried.get(stored.id, set()) | keys
                        changed = True
    return carried


def _alert_arguments(node: ast.AST) -> list[ast.expr]:
    """알림 요소(로거가 아닌 `success`·`info`·`warning`·`error`·`exception`·`toast`) 부름의 인자."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _ALERTS
        and ast.unparse(node.func.value).split(".")[-1].lower() not in _LOGGERS
    ):
        return []
    return [*node.args, *(keyword.value for keyword in node.keywords)]


def _drawn(nodes: list[ast.AST], taken: dict[int, tuple[str, int]]) -> dict[str, int]:
    """꺼낸 칸의 값이 알림 요소에 들어가는 칸 → 꺼낸 줄."""
    carried = _carried(nodes, taken)
    drawn: dict[str, int] = {}
    for node in nodes:
        for argument in _alert_arguments(node):
            for key, line in _sources(argument, taken, carried):
                drawn.setdefault(key, line)
    return drawn


def _cleared_and_drawn(nodes: list[ast.AST], blocks: list[list[ast.AST]]) -> dict[str, int]:
    """한 블록이 칸을 비우고 **같은 블록에서** 그 칸의 값을 알림 요소로 그리는 칸 → 비운 줄.

    값은 어디서 읽어 두었든(바깥 블록의 `get` 과 그 값을 이어 받은 이름까지) 본다 —
    `flash = get(칸)` 뒤 `if flash:` 갈래 안에서 `del` 하고 그리는 옛 꼴을 잡는다. 비우는 갈래와
    그리는 갈래가 다르면(확인 대기 칸 — 맞지 않을 때만 비우고 다른 갈래에서 묻는다) 잡지 않는다.
    """
    reads = _reads(nodes)
    carried = _carried(nodes, reads)
    found: dict[str, int] = {}
    for level in blocks:
        cleared = {key: getattr(node, "lineno", 0) for node in level for key in _cleared_keys(node)}
        if not cleared:
            continue
        for node in level:
            for argument in _alert_arguments(node):
                for key, _line in _sources(argument, reads, carried):
                    if key in cleared:
                        found.setdefault(key, cleared[key])
    return found


def _notice_sites(tree: ast.Module) -> dict[tuple[str, str], int]:
    """flash.py 밖에서 알림 칸을 꺼내는 자리 (함수 — 모듈 본문은 "", 칸의 식) → 줄. 그물이 둘이다.

    - **이름 그물** — 이름에 FLASH·NOTICE 가 든 칸을 비우는(`pop`·`del`) 자리, 또는 이름에
      flash·notice 가 든 함수가 칸을 비우는 자리. 꺼내 넘겨 다른 곳이 그리는 꼴(옛
      `pop_discarded_notice`)도 잡는다.
    - **그리기 그물** — 한 스코프에서 꺼낸 칸의 값(그 값에서 이름 붙여 이어 받은 값까지)이 알림 요소
      (`success`·`info`·`warning`·`error`·`exception`·`toast`)에 들어가는 자리. 칸 이름(ERROR·
      RESULT·WARNINGS …)과 꺼내는 꼴(`pop`, `get` 뒤 `del`)을 가리지 않는다. 바깥 블록에서 읽어
      두고 한 갈래 안에서 비우며 그 갈래에서 그리는 꼴도 같다(`_cleared_and_drawn`).
    """
    scopes: list[tuple[str, ast.AST]] = [("", tree)]
    scopes += [
        (node.name, node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    found: dict[tuple[str, str], int] = {}
    for name, scope in scopes:
        nodes = _scope_nodes(scope)
        for node in nodes:
            for key in _cleared_keys(node):
                named = any(word in key.upper() for word in ("FLASH", "NOTICE"))
                if named or any(word in name.lower() for word in ("flash", "notice")):
                    found.setdefault((name, key), getattr(node, "lineno", 0))
        blocks = _blocks(scope, nodes)
        taken = _taken(blocks)
        for key, line in (_drawn(nodes, taken) if taken else {}).items():
            found.setdefault((name, key), line)
        for key, line in _cleared_and_drawn(nodes, blocks).items():
            found.setdefault((name, key), line)
    return found


def _app_sources() -> list[Path]:
    """앱 코드 — 진입점 · 페이지 · 패키지."""
    return [
        PROJECT_ROOT / "app.py",
        *sorted((PROJECT_ROOT / "app_pages").glob("*.py")),
        *sorted((PROJECT_ROOT / "src").rglob("*.py")),
    ]


def _flash_pops() -> dict[tuple[str, str, str], int]:
    """flash.py 밖에서 알림 칸을 꺼내는 자리 (파일, 함수, 칸의 식) → 줄."""
    found: dict[tuple[str, str, str], int] = {}
    for path in _app_sources():
        if path == FLASH_OWNER:
            continue
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for (scope, key), line in _notice_sites(tree).items():
            found[(relative, scope, key)] = line
    return found


def test_notice_slots_are_popped_and_drawn_only_through_flash() -> None:
    """알림 칸을 칸마다 꺼내 그리면 끊긴 회차·자리 밀림 고침이 그 칸에 가지 않는다.

    flash.py 밖에서 알림 칸을 꺼내는 자리를 두 그물로 찾는다(`_notice_sites`) — 이름에 FLASH·NOTICE
    가 든 칸을 비우는 자리와, 이름과 상관없이 꺼낸 칸의 값을 알림 요소로 그리는 자리. 꺼내 그리는
    것도, 꺼내 넘겨 다른 곳이 그리는 것(옛 `pop_discarded_notice`)도 같다. 담기는 `queue_flash`,
    그리기는 `render_flash` 다. 수명이 다른 칸만 까닭을 적어 허용한다.
    """
    offenders = [
        f"{path}:{line} ({scope or '모듈 본문'} · {key})"
        for (path, scope, key), line in sorted(_flash_pops().items())
        if (path, scope, key) not in FLASH_POP_ALLOWED
    ]

    assert not offenders, (
        "알림 칸을 flash.py 밖에서 꺼냅니다 — `queue_flash` 로 담고 `render_flash` 로 그리세요"
        "(수명이 다르면 FLASH_POP_ALLOWED 에 까닭과 함께):\n" + "\n".join(offenders)
    )


def test_every_allowed_pop_is_still_there() -> None:
    """허용 목록이 옮긴 자리를 붙들고 있으면 같은 꼴이 그 이름으로 되돌아와도 그물을 지난다."""
    stale = sorted(set(FLASH_POP_ALLOWED) - set(_flash_pops()))

    assert not stale, f"사라진 자리입니다 — FLASH_POP_ALLOWED 에서 지우세요: {stale}"


# 알림 칸을 읽기만 하는 함수. 칸 이름이 이 함수들의 인자로만 쓰이면 그 칸은 아무도 담지 않는다.
_SLOT_READERS = frozenset(
    {"render_flash", "emit_flash", "pending_flash", "send_to_popup", "held_flash", "held_notice"}
)


def _module_name(path: Path) -> str:
    parts = path.relative_to(PROJECT_ROOT).with_suffix("").parts
    return ".".join(parts[1:] if parts[0] == "src" else parts)


def _unwritten_slots(modules: Mapping[str, ast.Module]) -> dict[tuple[str, str], list[str]]:
    """읽는 함수(`_SLOT_READERS`)에만 넘기고 다른 데서는 한 번도 쓰지 않는 대문자 칸 이름
    (정의한 모듈, 이름) → 읽는 자리(모듈:줄).

    같은 이름(`FLASH_KEY` 등)이 모듈마다 있어 이름은 정의한 모듈까지 푼다 — `from … import` 로
    들인 이름은 그 모듈로(함수 · 갈래 안에서 늦게 들인 것도 — 그 모듈 어디서 쓰든 같은 이름으로
    본다), 모듈 속성은 그 모듈로(`import … as` 별칭이든 `from 패키지 import 모듈`(as …)이든 — 들인
    것이 훑는 모듈일 때만, 클래스 따위의 속성은 쓴 글자 그대로), 나머지는 쓴 모듈로.
    담기(`queue_flash`)·넘기기(도우미 인자 · `*튜플`)·비교 모두 「쓰임」 이다 — 읽기 밖의 쓰임이
    하나라도 있으면 담는 쪽이 있다고 본다(놓치는 쪽으로 너그럽다).

    보는 칸은 이름(대문자 상수 · 그 모듈 속성)으로 넘긴 것뿐이다 — 글자 그대로(`render_flash("…")`)
    나 f-string 으로 넘긴 칸은 보지 않는다(담는 쪽이 f-string 으로 같은 글자를 지으면 글자끼리 맞대
    풀 수 없다).
    """
    reads: dict[tuple[str, str], list[str]] = {}
    used: set[tuple[str, str]] = set()
    for module, tree in modules.items():
        names: dict[str, tuple[str, str]] = {}
        aliases: dict[str, str] = {}
        for statement in ast.walk(tree):
            if isinstance(statement, ast.ImportFrom) and statement.module:
                for alias in statement.names:
                    names[alias.asname or alias.name] = (statement.module, alias.name)
            elif isinstance(statement, ast.Import):
                for alias in statement.names:
                    aliases[alias.asname or alias.name] = alias.name

        def resolve(
            expr: ast.expr,
            module: str = module,
            names: dict[str, tuple[str, str]] = names,
            aliases: dict[str, str] = aliases,
        ) -> tuple[str, str] | None:
            if isinstance(expr, ast.Name):
                return names.get(expr.id, (module, expr.id))
            if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
                base = expr.value.id
                if base in names and ".".join(names[base]) in modules:
                    return (".".join(names[base]), expr.attr)
                return (aliases.get(base, base), expr.attr)
            return None

        read_nodes: set[int] = set()
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and ast.unparse(node.func).split(".")[-1] in _SLOT_READERS
            ):
                continue
            for argument in node.args:
                slot = resolve(argument)
                if slot is not None and slot[1].isupper():
                    reads.setdefault(slot, []).append(f"{module}:{node.lineno}")
                    read_nodes.add(id(argument))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Name | ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and id(node) not in read_nodes
            ):
                slot = resolve(node)
                if slot is not None:
                    used.add(slot)
    return {slot: sites for slot, sites in sorted(reads.items()) if slot not in used}


def test_every_notice_slot_that_is_read_is_also_filled() -> None:
    """읽기만 하는 알림 칸은 죽은 칸이다 — 담는 쪽이 걷히고 읽는 쪽만 남으면(옛
    `equipment_data_workspace.FLASH_KEY` 「equipment_status_flash」) 그 칸은 늘 비어 있는데 읽는
    자리는 무언가를 알리는 것처럼 읽힌다. 칸을 지우고 읽는 자리는 늘 서 있는 칸만 남긴다."""
    modules = {
        _module_name(path): ast.parse(path.read_text(encoding="utf-8")) for path in _app_sources()
    }
    dead = _unwritten_slots(modules)

    assert not dead, f"담는 곳이 없는 알림 칸입니다 — 칸과 읽는 자리를 걷으세요: {dead}"


def test_the_unwritten_slot_net_resolves_the_defining_module() -> None:
    """같은 이름의 칸이 다른 모듈에서 담겨도 그 모듈의 칸을 읽는 자리는 죽은 칸으로 잡는다 —
    별칭 속성 · 도우미 인자 · `*튜플` 은 쓰임으로 본다."""
    modules = {
        "pkg.voc": ast.parse(
            'FLASH_KEY = "v"\nqueue_flash(FLASH_KEY, "x")\nrender_flash(FLASH_KEY)'
        ),
        "pkg.workspace": ast.parse('FLASH_KEY = "w"\nKEYS = ("a",)\nHELPER_KEY = "h"'),
        "pkg.page": ast.parse(
            "from pkg.workspace import FLASH_KEY, HELPER_KEY, KEYS\n"
            "import pkg.workspace as ws\n"
            "slot = render_flash(FLASH_KEY)\n"
            "render_flash(ws.FLASH_KEY, *KEYS)\n"
            "pending_flash(HELPER_KEY)\n"
            "carry(HELPER_KEY)"
        ),
        "pkg.late": ast.parse(
            "def draw():\n    from pkg.voc import FLASH_KEY\n    render_flash(FLASH_KEY)"
        ),
    }

    assert _unwritten_slots(modules) == {
        ("pkg.workspace", "FLASH_KEY"): ["pkg.page:3", "pkg.page:4"]
    }


@pytest.mark.parametrize(
    ("importing", "name"), [("from pkg import ws", "ws"), ("from pkg import ws as w", "w")]
)
def test_the_unwritten_slot_net_resolves_a_module_imported_from_its_package(
    importing: str, name: str
) -> None:
    """`from 패키지 import 모듈`(as …)로 들인 모듈의 속성도 그 모듈의 칸이다 — 그 모듈이 담으면
    지나고(담는 쪽이 같은 꼴로 들여 담아도), 아무도 담지 않으면 그 모듈의 칸으로 잡는다."""
    page = ast.parse(f"{importing}\nrender_flash({name}.FLASH_KEY)")
    unfilled = ast.parse('FLASH_KEY = "w"')

    assert not _unwritten_slots(
        {"pkg.ws": ast.parse('FLASH_KEY = "w"\nqueue_flash(FLASH_KEY, "x")'), "pkg.page": page}
    )
    assert not _unwritten_slots(
        {
            "pkg.ws": unfilled,
            "pkg.page": page,
            "pkg.writer": ast.parse(f'{importing}\nqueue_flash({name}.FLASH_KEY, "x")'),
        }
    )
    assert _unwritten_slots({"pkg.ws": unfilled, "pkg.page": page}) == {
        ("pkg.ws", "FLASH_KEY"): ["pkg.page:2"]
    }


def test_the_unwritten_slot_net_keeps_class_attributes_as_written() -> None:
    """들인 것이 모듈이 아니면(클래스 따위) 속성은 쓴 글자 그대로 본다 — 정의한 모듈 안의
    `Holder.KEY` 와 같은 이름이라 담는 쪽이 있는 칸을 죽은 칸으로 잡지 않는다."""
    modules = {
        "pkg.ws": ast.parse('class Holder:\n    KEY = "k"\nqueue_flash(Holder.KEY, "x")'),
        "pkg.page": ast.parse("from pkg.ws import Holder\nrender_flash(Holder.KEY)"),
    }

    assert not _unwritten_slots(modules)


NET_CAUGHT = {
    "pop 해 그리기": """
import streamlit as st
message = st.session_state.pop(SAVE_RESULT_KEY, None)
if isinstance(message, str):
    st.success(message)
""",
    "get 뒤 del 로 되돌린 옛 꼴(이름에 FLASH)": """
import streamlit as st
flash = st.session_state.get(SIDEBAR_FLASH_KEY)
del st.session_state[SIDEBAR_FLASH_KEY]
st.success(flash)
""",
    "get 뒤 del — 이름이 ERROR": """
import streamlit as st

def draw():
    if SAVE_ERROR_KEY in st.session_state:
        failure = st.session_state[SAVE_ERROR_KEY]
        del st.session_state[SAVE_ERROR_KEY]
        st.error(f"저장하지 못했습니다: {failure}")
""",
    "꺼낸 dict 를 풀어 여러 줄로 그리기": """
import streamlit as st

def warnings(slot):
    mistakes = st.session_state.pop(LABEL_WARNINGS_KEY, None) or {}
    for typed, column in mistakes.items():
        slot.warning(f"{typed} → {column}")
""",
    "꺼내며 곧바로 그리기": """
import streamlit as st
st.error(st.session_state.pop(POST_ERROR_KEY, ""))
""",
    "바깥에서 get, 갈래 안에서 del 뒤 그리기 — 이름이 RESULT": """
import streamlit as st

def draw():
    result = st.session_state.get(SAVE_RESULT_KEY)
    if isinstance(result, str):
        del st.session_state[SAVE_RESULT_KEY]
        st.info(result)
""",
}

NET_PASSED = {
    "flash 한 길": """
import streamlit as st
from capa_simulation.components.flash import queue_flash, render_flash
render_flash(SAVE_RESULT_KEY)
queue_flash(SAVE_RESULT_KEY, "저장했습니다.", kind="info")
""",
    "그리지 않고 비우기만(버리기 콜백)": """
import streamlit as st

def discard():
    st.session_state.pop(SAVE_ERROR_KEY, None)
""",
    "고른 값을 읽다가 맞지 않을 때만 비우기": """
import streamlit as st
held = st.session_state.get(CONFIRM_KEY)
if held is None:
    st.session_state.pop(CONFIRM_KEY, None)
else:
    st.warning(f"{held} 를 끕니다")
""",
    "로거": """
import logging
import streamlit as st
logger = logging.getLogger(__name__)
logger.error(st.session_state.pop(TRACE_KEY, ""))
""",
}


@pytest.mark.parametrize("label", sorted(NET_CAUGHT))
def test_the_net_catches_a_notice_slot_in_any_shape(label: str) -> None:
    """옛 꼴로 되돌린 알림 칸을 이름(FLASH·NOTICE)만 보지 않고 잡는다 — `pop` 대신 `get` + `del`,
    ERROR·RESULT·WARNINGS 이름, 꺼낸 값을 풀어 그리는 꼴."""
    assert _notice_sites(ast.parse(NET_CAUGHT[label]))


@pytest.mark.parametrize("label", sorted(NET_PASSED))
def test_the_net_passes_what_is_not_a_notice_slot(label: str) -> None:
    assert not _notice_sites(ast.parse(NET_PASSED[label]))


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
    assert texts(successes(app)) == ["지웠습니다."]
    (first,) = alert_notes(app)

    app._run(widget_state=pressed)

    assert not app.exception, [element.message for element in app.exception]
    assert app.session_state["deleted"] == 1
    assert texts(successes(app)) == (["지웠습니다."] if kept else [])
    # 다시 낸 알림은 첫 알림과 같은 id 다 — 브라우저가 알림창을 두 번 띄우지 않는다.
    assert [note["id"] for note in alert_notes(app, again=True)] == [first["id"]]


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
    assert texts(successes(app)) == (["지웠습니다."] if kept else [])
