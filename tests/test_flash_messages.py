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


# flash.py 밖에서 알림 칸을 꺼내는 자리 가운데 이 모듈을 지나지 않는 것과 그 까닭.
# (파일, 함수 — 모듈 본문은 "", 꺼내는 칸의 식) → 까닭. 함수까지 적어 같은 이름의 흔한 변수(`key`)를
# 꺼내는 새 자리가 다른 함수에서 허용을 빌리지 못하게 한다. 자리가 사라지면 여기서도 지운다
# (`test_every_allowed_pop_is_still_there`).
FLASH_POP_ALLOWED: dict[tuple[str, str, str], str] = {
    ("app_pages/voc.py", "", "GONE_NOTICE_KEY"): (
        "다음 동작까지 남는 꼴 — 지운 글의 거절과 함께 적어 둔 답변을 되살릴 입력으로 든다(그리는"
        " 칸은 머리 알림 칸 `render_flash(FLASH_KEY)` 가 돌려준 칸이다)"
    ),
    (
        "src/capa_simulation/components/shortening_progress_panel.py",
        "_pop_notices",
        "_BASELINE_NOTICE_KEY",
    ): (
        "다음 동작까지 남는 꼴 — 기준선 알림은 이벤트 칸 자리 수를 고정하고 같은 알림을 한 번만"
        " 세는 shown 칸과 짝이다"
    ),
    ("app_pages/reference_data.py", "", "'capacity_step_flash'"): (
        "매 회차 비우고 STEP 탭을 그리는 회차에만 그린다 — 숨은 회차에 남은 알림을 나중에 띄우지"
        " 않는다(`tests/test_reference_data_perf.py`)"
    ),
    (
        "src/capa_simulation/components/month_editor.py",
        "render_month_editor",
        "f'{editor_key}_apply_flash'",
    ): ("`st.empty` 한 자리 — 페이지가 같은 자리에 적용 오류를 덮어 쓴다(`editor_notice`)"),
    (
        "src/capa_simulation/components/month_editor.py",
        "render_month_editor",
        "_notice_key(editor_key)",
    ): ("알림이 아니라 그 자리(`st.empty`) 손잡이를 비운다"),
    ("app_pages/load_conversion.py", "_render_flashes", "key"): (
        "그리는 자리가 아이콘을 정한다 — 담는 도우미(`queue_reference_import_flash`)를 기준정보"
        " 편집기와 함께 쓰고 아이콘이 다르다. 담는 쪽이 아이콘을 받게 한 뒤 옮긴다(그동안 그리는"
        " 칸은 늘 선다 — `tests/test_load_conversion_plan_apply.py`)"
    ),
    (
        "src/capa_simulation/components/equipment_scenario_management.py",
        "render_equipment_scenario_management",
        "FLASH_KEY",
    ): (
        "알림을 그리는 회차에 팝오버 세대를 함께 올린다(`POPOVER_GENERATION_KEY`) — 그린 줄 알아야"
        " 하는 칸이다"
    ),
    (
        "src/capa_simulation/components/equipment_scenario_management.py",
        "render_equipment_scenario_management",
        "REFUSED_KEY",
    ): (
        "거절 알림 — 작업 알림(`FLASH_KEY`)과 같은 회차에 팝오버 세대를 올리고 같은 늘 서 있는 칸에"
        " 그린다. 두 칸을 함께 옮긴다"
    ),
    (
        "src/capa_simulation/components/equipment_scenario_status.py",
        "render_equipment_scenario_row",
        "FLASH_KEY",
    ): (
        "사이드바 설비 시나리오 줄 슬롯 안 — 저장 대조·위젯 세대 갈래가 이 파일을 함께 고친다. 그"
        " 고침이 들어간 뒤 옮긴다"
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
        "src/capa_simulation/components/display_order_management.py",
        "_render_label_warnings",
        "LABEL_WARNINGS_KEY",
    ): (
        "한 저장의 표시명 실수 여러 줄(dict) — 알림 하나가 아니다. 저장 성공 칸"
        '(`render_flash("display_order_flash")` 가 돌려준 칸) 안에 그려 자리는 그 칸이 고정한다'
    ),
    (
        "src/capa_simulation/components/cutoff_management.py",
        "render_cutoff_management",
        "_CONFLICT_KEY",
    ): (
        "Cut-off 충돌 거부 — 저장 대조 갈래(`refactor/write-cas-seen-own-save`)가 이 칸을 쓰기"
        " 거부 표지(`write_guard.queue_refusal`)로 옮기며 늘 서 있는 칸에 넣는다. 그 갈래가"
        " 들어가면 지운다"
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


def _taken(scope: ast.AST, nodes: list[ast.AST]) -> dict[int, tuple[str, int]]:
    """스코프에서 칸을 **꺼내는** 읽기 (노드 id → (칸, 줄)).

    `pop` 은 늘 꺼내기다. `get`·`[]` 읽기는 같은 단(한 블록)에서 그 칸을 비울 때만 꺼내기다 —
    `get` 뒤 `del` 로 되돌린 옛 꼴은 잡고, 고른 값을 읽다가 맞지 않을 때만 갈래 안에서 비우는
    칸(선택 주소·확인 대기)은 꺼내기가 아니다.
    """
    blocks: list[list[ast.stmt]] = [getattr(scope, "body", [])]
    for node in nodes:
        for field in _BLOCK_FIELDS:
            block = getattr(node, field, None)
            if isinstance(block, list):
                blocks.append([item for item in block if isinstance(item, ast.stmt)])
    taken: dict[int, tuple[str, int]] = {}
    for block in blocks:
        levels = [_level_nodes(statement) for statement in block]
        cleared = {key for level in levels for node in level for key in _cleared_keys(node)}
        for level in levels:
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


def _drawn(nodes: list[ast.AST], taken: dict[int, tuple[str, int]]) -> dict[str, int]:
    """꺼낸 칸의 값이 알림 요소에 들어가는 칸 → 꺼낸 줄."""
    carried = _carried(nodes, taken)
    drawn: dict[str, int] = {}
    for node in nodes:
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _ALERTS
            and ast.unparse(node.func.value).split(".")[-1].lower() not in _LOGGERS
        ):
            continue
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            for key, line in _sources(argument, taken, carried):
                drawn.setdefault(key, line)
    return drawn


def _notice_sites(tree: ast.Module) -> dict[tuple[str, str], int]:
    """flash.py 밖에서 알림 칸을 꺼내는 자리 (함수 — 모듈 본문은 "", 칸의 식) → 줄. 그물이 둘이다.

    - **이름 그물** — 이름에 FLASH·NOTICE 가 든 칸을 비우는(`pop`·`del`) 자리, 또는 이름에
      flash·notice 가 든 함수가 칸을 비우는 자리. 꺼내 넘겨 다른 곳이 그리는 꼴(옛
      `pop_discarded_notice`)도 잡는다.
    - **그리기 그물** — 한 스코프에서 꺼낸 칸의 값(그 값에서 이름 붙여 이어 받은 값까지)이 알림 요소
      (`success`·`info`·`warning`·`error`·`exception`·`toast`)에 들어가는 자리. 칸 이름(ERROR·
      RESULT·WARNINGS …)과 꺼내는 꼴(`pop`, `get` 뒤 `del`)을 가리지 않는다.
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
        taken = _taken(scope, nodes)
        for key, line in (_drawn(nodes, taken) if taken else {}).items():
            found.setdefault((name, key), line)
    return found


def _flash_pops() -> dict[tuple[str, str, str], int]:
    """flash.py 밖에서 알림 칸을 꺼내는 자리 (파일, 함수, 칸의 식) → 줄."""
    sources = [
        PROJECT_ROOT / "app.py",
        *sorted((PROJECT_ROOT / "app_pages").glob("*.py")),
        *sorted((PROJECT_ROOT / "src").rglob("*.py")),
    ]
    found: dict[tuple[str, str, str], int] = {}
    for path in sources:
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
