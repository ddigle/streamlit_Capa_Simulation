# Purpose: 위젯 key 세대 도우미의 key 꼴 보존·닫힌 팝오버 칸 싣기와 세대 key 손짓기 그물을 본다.

"""`components/widget_generation.py` — 서버 값을 브라우저가 든 위젯에 닿게 하는 한 길.

- **key 꼴 보존** — 아홉 모듈이 따로 짓던 key 글자를 도우미가 바이트까지 그대로 낸다. 1바이트라도
  바뀌면 배포 직후 열려 있던 세션의 칸이 한 번 비거나 새로 선다.
- **닫힌 팝오버 칸** — 브라우저는 닫혀 있던 칸을 나중에 열 때 마지막 회차가 실어 보낸 값으로만
  세운다(`_late_mount`). 처음 회차에 한 번 적는 꼴은 한 회차 뒤 빈 칸으로 섰다(2026-10-26 E2E —
  설비 시나리오 「리비전명」). `seed_field` 는 고치지 않은 동안 매 회차 싣는다.
- **AST 그물** — 도우미 밖에서 세대 꼬리 글자(`__g{…}`·`_g{…}`·`__p{…}` 뒤 아무 식, `__{…}`·`_{…}`
  뒤 세대·nonce 식 — f-문자열·`+` 잇기·`.format`)를 짓거나(아직 옮기지 않은 `_{n}` 꼴 다섯 자리는
  `_REMAINING_HAND_MADE`), 팝오버 안에 그리는 입력 칸 key 에 그 함수가 세션 대입·`setdefault`·같은
  모듈 도우미로 값을 미리 적으면 실패한다. 다이얼로그는 보지
  않는다 — 다이얼로그 본문은 열린 회차에만 그려져 그 회차의 칸이 마운트된 채라 같은 회차에 적은
  값을 받는다(사이드바 팝업의 「구획」 고르기가 그렇게 선택지 밖 값을 고친다). 다이얼로그가 **닫힌**
  회차에 적은 값이 닿지 않는 것은 key 세대(`bump`)로 막는다.
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import capa_simulation.components.equipment_scenario_management as equipment_scenario_management
import capa_simulation.components.equipment_scenario_status as equipment_scenario_status
import capa_simulation.components.preset_number_field as preset_number_field
import capa_simulation.components.scenario_management as scenario_management
import capa_simulation.components.scenario_status as scenario_status
import capa_simulation.components.shortening_progress_panel as shortening_progress_panel
from capa_simulation.components.editor_state import discard_editor, editor_widget_key
from capa_simulation.components.widget_generation import (
    KeyStyle,
    bump,
    generation,
    seed_field,
    widget_key,
)

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "src" / "capa_simulation" / "components" / "widget_generation.py"


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    fake: dict[str, object] = {}
    monkeypatch.setattr(st, "session_state", fake)
    return fake


# ------------------------------------------------------------------ key 꼴 보존


@pytest.mark.parametrize(
    ("base", "style", "bare_zero", "number", "expected"),
    [
        ("x", "__g", True, 0, "x"),
        ("x", "__g", True, 1, "x__g1"),
        ("x", "__g", False, 0, "x__g0"),
        ("scenario_create_name", "_g", False, 0, "scenario_create_name_g0"),
        ("scenario_create_name", "_g", False, 1, "scenario_create_name_g1"),
        ("x", "__", True, 0, "x"),
        ("x", "__", True, 1, "x__1"),
        ("x", "__p", False, 0, "x__p0"),
        ("x", "__p", False, 2, "x__p2"),
    ],
)
def test_widget_key_keeps_the_old_key_shapes(
    session: dict[str, object],
    base: str,
    style: KeyStyle,
    bare_zero: bool,
    number: int,
    expected: str,
) -> None:
    session["counter"] = number
    assert widget_key(base, "counter", style=style, bare_zero=bare_zero) == expected


def test_a_missing_or_foreign_counter_reads_as_generation_zero(session: dict[str, object]) -> None:
    assert generation("counter") == 0
    session["counter"] = "3"
    assert generation("counter") == 0
    assert widget_key("x", "counter") == "x"
    assert bump("counter") == 1
    assert session["counter"] == 1
    assert widget_key("x", "counter") == "x__g1"


def test_the_module_keys_are_byte_for_byte_the_old_keys(session: dict[str, object]) -> None:
    """도우미로 옮긴 아홉 자리의 key 글자 — 세대 0 과 1 에서 옛 글자 그대로다."""

    def keys() -> list[str]:
        return [
            editor_widget_key("sheet"),
            scenario_status.save_field_key(scenario_status.SAVE_REVISION_NAME_KEY),
            equipment_scenario_status.save_note_key(),
            scenario_management.clone_field_key("name"),
            shortening_progress_panel._name_key(),
            shortening_progress_panel._form_key(),
            shortening_progress_panel._popover_key(),
            equipment_scenario_management._keyed(equipment_scenario_management.RENAME_KEY),
            equipment_scenario_management._popover_key(
                equipment_scenario_management.RENAME_POPOVER_KEY
            ),
            preset_number_field._input_widget_key("rate"),
        ]

    name = scenario_status.SAVE_REVISION_NAME_KEY
    note = equipment_scenario_status.SAVE_NOTE_KEY
    rename = equipment_scenario_management.RENAME_KEY
    popover = equipment_scenario_management.RENAME_POPOVER_KEY
    assert keys() == [
        "sheet",
        name,
        note,
        "scenario_create_name_g0",
        "equipment_shortening_baseline_name",
        "equipment_shortening_baseline_form",
        "equipment_shortening_baseline_popover__g0",
        rename,
        f"{popover}__p0",
        "rate",
    ]
    for counter in (
        "sheet__generation",
        scenario_status.SAVE_FORM_GENERATION_KEY,
        equipment_scenario_status.SAVE_NOTE_GENERATION_KEY,
        scenario_management.CLONE_FORM_GENERATION_KEY,
        shortening_progress_panel._BASELINE_FORM_GENERATION_KEY,
        equipment_scenario_management.GENERATION_KEY,
        equipment_scenario_management.POPOVER_GENERATION_KEY,
        "rate__generation",
    ):
        session[counter] = 1
    assert keys() == [
        "sheet__g1",
        f"{name}__g1",
        f"{note}__g1",
        "scenario_create_name_g1",
        "equipment_shortening_baseline_name__g1",
        "equipment_shortening_baseline_form__g1",
        "equipment_shortening_baseline_popover__g1",
        f"{rename}__g1",
        f"{popover}__p1",
        "rate__1",
    ]


def test_discarding_an_editor_bumps_through_the_helper(session: dict[str, object]) -> None:
    session["sheet"] = {"edited_rows": {0: {"a": 1}}}
    discard_editor("sheet")
    assert "sheet" not in session
    assert session["sheet__generation"] == 1
    assert editor_widget_key("sheet") == "sheet__g1"


# ------------------------------------------------------------------ 닫힌 팝오버 칸


def _late_mount(widget: Any) -> str:
    """닫혀 있던 팝오버를 지금 열 때 브라우저가 칸에 세울 글자 — 이번 회차가 값을 실어 보냈으면
    그 값, 아니면 빈 기본값(`tests/test_equipment_scenario_name_fields.py` 와 같은 잼)."""
    proto = widget.proto
    return str(proto.value) if proto.set_value else str(proto.default)


def _seeded_popover() -> None:
    import streamlit as st

    from capa_simulation.components.widget_generation import seed_field

    current = st.session_state.get("server_name", "u2 이름")
    with st.popover("리비전명", key="name_popover"):
        field = seed_field("name_generation", "revision_name", current, suffix="__r1")
        st.text_input("리비전명", key=field.key)
    st.button("다른 일", key="other")


def _seeded_once_popover() -> None:
    """옛 꼴 — 칸이 없을 때 한 번만 세션 대입으로 적는다(3회차가 고친 함정)."""
    import streamlit as st

    with st.popover("리비전명", key="name_popover"):
        if "revision_name__r1" not in st.session_state:
            st.session_state["revision_name__r1"] = "u2 이름"
        st.text_input("리비전명", key="revision_name__r1")
    st.button("다른 일", key="other")


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def test_a_field_seeded_once_comes_up_empty_after_another_run() -> None:
    """함정 재현 — 처음 회차에만 적은 닫힌 칸은 한 회차 뒤 열면 빈 칸으로 선다."""
    app = _ok(AppTest.from_function(_seeded_once_popover).run())
    field = app.text_input(key="revision_name__r1")
    assert _late_mount(field) == "u2 이름"
    _ok(app.run())
    assert _late_mount(app.text_input(key="revision_name__r1")) == ""


def test_a_seeded_closed_popover_field_carries_the_value_after_another_run() -> None:
    app = _ok(AppTest.from_function(_seeded_popover).run())
    assert _late_mount(app.text_input(key="revision_name__r1")) == "u2 이름"
    _ok(app.button(key="other").click().run())
    assert _late_mount(app.text_input(key="revision_name__r1")) == "u2 이름"
    _ok(app.run())
    assert _late_mount(app.text_input(key="revision_name__r1")) == "u2 이름"


def test_a_seeded_field_follows_the_server_value_while_untouched() -> None:
    app = _ok(AppTest.from_function(_seeded_popover).run())
    app.session_state["server_name"] = "남이 바꾼 이름"
    _ok(app.run())
    assert _late_mount(app.text_input(key="revision_name__r1")) == "남이 바꾼 이름"
    assert app.session_state["revision_name__r1__seen"] == "남이 바꾼 이름"


def test_an_edited_seeded_field_keeps_what_was_typed() -> None:
    app = _ok(AppTest.from_function(_seeded_popover).run())
    app.text_input(key="revision_name__r1").input("고치는 중")
    _ok(app.run())
    app.session_state["server_name"] = "남이 바꾼 이름"
    _ok(app.button(key="other").click().run())
    field = app.text_input(key="revision_name__r1")
    assert field.value == "고치는 중"
    assert not field.proto.set_value
    # 본 값은 칸을 세울 때의 값 그대로다 — 비교 후 쓰기는 이것과 대조해 남의 바꿈을 거절한다.
    assert app.session_state["revision_name__r1__seen"] == "u2 이름"


def test_bumping_the_generation_seeds_a_new_widget(session: dict[str, object]) -> None:
    """세대를 올리면 새 key 칸이 서고 seed_field 가 그 칸에 서버 값을 먼저 적는다 — 고치던 글은
    버린다."""
    first = seed_field("gen", "name", "옛 이름")
    session[first.key] = "고치던 글"
    assert seed_field("gen", "name", "새 이름").key == "name"
    assert session["name"] == "고치던 글"
    bump("gen")
    second = seed_field("gen", "name", "새 이름")
    assert second == type(second)(key="name__g1", seen_key="name__g1__seen")
    assert session["name__g1"] == "새 이름"


# ------------------------------------------------------------------ AST 그물


def _parse(path: Path) -> ast.Module:
    # 남의 파일 글자 그대로의 잘못된 escape 경고(`scripts/` 의 docstring)는 이 그물과 상관없다.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(path.read_text(encoding="utf-8"))


def _sources() -> list[Path]:
    paths = [ROOT / "app.py", *sorted((ROOT / "app_pages").glob("*.py"))]
    paths += sorted((ROOT / "src").rglob("*.py"))
    paths += sorted((ROOT / "scripts").rglob("*.py"))
    return [path for path in paths if path != HELPER]


# 세대 꼬리 — 앞 셋은 세대 말고는 쓰지 않는 글자라 뒤에 무엇이 와도 세대 key 로 본다. 뒤
# 둘(`__`·`_`)은 리비전 id·글 번호 꼬리로도 흔해, 뒤 식에 세대 칸(`generation`·`nonce`)이 들
# 때만 본다.
_STRICT_TAILS = ("__g", "_g", "__p")
_LOOSE_TAILS = ("__", "_")
_COUNTER_WORDS = ("generation", "nonce")

# 아직 옮기지 않은 세대 key — `docs/TODO.md` 코드 정리 「위젯 세대 한 길 뒤에 남은 것」 ①.
# 꼬리 `_{n}` 꼴이라 `widget_key` 의 꼴 넷 밖이다. 옮기면 이 목록에서 뺀다(남은 줄이 없으면
# 시험이 알린다).
_REMAINING_HAND_MADE = {
    ("app_pages/space_status.py", "_render_unsaved_layout_panel"),
    ("src/capa_simulation/components/equipment_data_workspace.py", "_upload_widget_key"),
    ("src/capa_simulation/components/floor_layout_upload.py", "_floor_layout_dialog"),
    ("src/capa_simulation/components/shortening_board.py", "render_progress_board"),
    ("src/capa_simulation/components/space_shortening_view.py", "render_floor_layer_panel"),
}


def _counter_like(node: ast.AST) -> bool:
    text = ast.unparse(node).lower()
    return any(word in text for word in _COUNTER_WORDS)


def _tail_then_counter(text: str, value: ast.AST) -> bool:
    return text.endswith(_STRICT_TAILS) or (text.endswith(_LOOSE_TAILS) and _counter_like(value))


def _added(node: ast.AST) -> list[ast.AST]:
    """`a + b + c` 를 펼친 항."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return [*_added(node.left), *_added(node.right)]
    return [node]


def _hand_made_generation_keys(tree: ast.AST) -> list[int]:
    """세대 꼬리 글자 바로 뒤에 세대 번호를 잇는 줄 — f-문자열·`+` 잇기·`.format` 세 꼴."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = node.values
            for before, after in zip(parts, parts[1:], strict=False):
                if (
                    isinstance(before, ast.Constant)
                    and isinstance(before.value, str)
                    and isinstance(after, ast.FormattedValue)
                    and _tail_then_counter(before.value, after.value)
                ):
                    lines.append(node.lineno)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            terms = _added(node)
            for left, right in zip(terms, terms[1:], strict=False):
                if (
                    isinstance(left, ast.Constant)
                    and isinstance(left.value, str)
                    and _tail_then_counter(left.value, right)
                ):
                    lines.append(node.lineno)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
            and isinstance(node.func.value, ast.Constant)
            and isinstance(node.func.value.value, str)
        ):
            template = node.func.value.value
            if any(f"{tail}{{" in template for tail in _STRICT_TAILS) or (
                any(f"{tail}{{" in template for tail in _LOOSE_TAILS)
                and any(_counter_like(argument) for argument in node.args)
            ):
                lines.append(node.lineno)
    return sorted(set(lines))


def _enclosing_function(tree: ast.Module, line: int) -> str:
    """`line` 을 품은 모듈 단 함수의 이름(모듈 단 줄이면 `<module>`)."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.lineno <= line <= (
            node.end_lineno or node.lineno
        ):
            return node.name
    return "<module>"


def _hand_made_sites() -> set[tuple[str, str, int]]:
    found: set[tuple[str, str, int]] = set()
    for path in _sources():
        tree = _parse(path)
        for line in _hand_made_generation_keys(tree):
            found.add((str(path.relative_to(ROOT)), _enclosing_function(tree, line), line))
    return found


def test_no_module_builds_a_generation_key_by_hand() -> None:
    found = _hand_made_sites()
    new = sorted(site for site in found if site[:2] not in _REMAINING_HAND_MADE)
    assert not new, (
        "세대 key 는 components/widget_generation.widget_key 로 짓는다(꼴은 style·bare_zero): "
        f"{new}"
    )
    moved = sorted(_REMAINING_HAND_MADE - {site[:2] for site in found})
    assert not moved, f"옮긴 자리는 남은 목록(_REMAINING_HAND_MADE)·TODO ① 에서 뺀다: {moved}"


def test_the_hand_made_key_net_catches_the_old_shapes() -> None:
    """그물이 옛 꼴 넷과 그 옆 꼴(아무 식·`.format`·`+` 잇기·nonce)을 실제로 잡는다."""
    samples = [
        'f"{key}__g{generation}"',
        'f"scenario_create_{field}_g{generation}"',
        'f"{base}__p{_popover_generation()}"',
        'f"{input_key}__{generation}"',
        'f"{key}__g{n}"',
        'f"{key}__g{gen}"',
        'f"{key}__g{st.session_state.get(C, 0)}"',
        '"{}__g{}".format(key, generation)',
        'key + "__g" + str(generation)',
        'f"{K}_{nonce}"',
        '"{}_{}".format(K, nonce)',
    ]
    for sample in samples:
        assert _hand_made_generation_keys(ast.parse(sample)), sample
    for innocent in (
        'f"{_keyed(KEY)}__{revision_id}"',
        'f"{REPLY_FORM_KEY}_{post_id}"',
        'key + "__" + scenario_id',
        '"{}_{}".format(prefix, post_id)',
    ):
        assert not _hand_made_generation_keys(ast.parse(innocent)), innocent


_INPUT_WIDGETS = frozenset(
    {
        "checkbox",
        "color_picker",
        "date_input",
        "multiselect",
        "number_input",
        "pills",
        "radio",
        "segmented_control",
        "select_slider",
        "selectbox",
        "slider",
        "text_area",
        "text_input",
        "time_input",
        "toggle",
    }
)


def _is_popover(item: ast.withitem) -> bool:
    call = item.context_expr
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "popover"
    )


def _popover_bodies(node: ast.AST) -> list[ast.stmt]:
    statements: list[ast.stmt] = []
    for child in ast.walk(node):
        if isinstance(child, ast.With) and any(_is_popover(item) for item in child.items):
            statements.extend(child.body)
    return statements


def _called_names(statements: list[ast.stmt]) -> set[str]:
    return {
        call.func.id
        for statement in statements
        for call in ast.walk(statement)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }


def _input_keys(statements: list[ast.stmt]) -> dict[str, int]:
    keys: dict[str, int] = {}
    for statement in statements:
        for call in ast.walk(statement):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr in _INPUT_WIDGETS
            ):
                continue
            for keyword in call.keywords:
                if keyword.arg == "key":
                    keys[ast.dump(keyword.value)] = call.lineno
    return keys


def _is_session_state(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "session_state"


def _session_writes(function: ast.FunctionDef) -> dict[str, int]:
    """세션 칸에 값을 적는 key 식 → 줄.

    `X.session_state[k] = …` 대입과 `X.session_state.setdefault(k, …)` 둘이다.
    """
    writes: dict[str, int] = {}
    for node in ast.walk(function):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and _is_session_state(target.value):
                    writes[ast.dump(target.slice)] = node.lineno
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setdefault"
            and _is_session_state(node.func.value)
            and node.args
        ):
            writes[ast.dump(node.args[0])] = node.lineno
    return writes


def _prefill_helpers(functions: dict[str, ast.FunctionDef]) -> dict[str, list[tuple[int, str]]]:
    """같은 모듈에서 칸 key 를 인자로 받아 그 칸에 적는 함수 → 그 인자의 (자리, 이름).

    `_prefill(key, value)` 처럼 「한 번만 적기」 를 도우미로 빼도 그물이 본다(2026-10-26 리뷰).
    """
    helpers: dict[str, list[tuple[int, str]]] = {}
    for name, function in functions.items():
        written = _session_writes(function)
        params = [
            (position, argument.arg)
            for position, argument in enumerate(
                [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
            )
            if ast.dump(ast.Name(id=argument.arg, ctx=ast.Load())) in written
        ]
        if params:
            helpers[name] = params
    return helpers


def _helper_prefills(
    function: ast.FunctionDef,
    keys: dict[str, int],
    helpers: dict[str, list[tuple[int, str]]],
) -> list[int]:
    """`function` 이 칸 key(`keys`)를 넘겨 부르는 같은 모듈 도우미 호출의 줄."""
    lines: list[int] = []
    for call in ast.walk(function):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
            continue
        for position, name in helpers.get(call.func.id, []):
            given = [
                *call.args[position : position + 1],
                *(item.value for item in call.keywords if item.arg == name),
            ]
            if any(ast.dump(value) in keys for value in given):
                lines.append(call.lineno)
    return lines


def _popup_prefills(tree: ast.Module) -> list[int]:
    """팝오버 안에 그리는 입력 칸 key 에, 그 칸을 그리는 함수가 세션에 값을 적는 줄.

    팝오버 안 함수는 같은 모듈의 `with ….popover(…)` 블록에서 부르는 함수와 그 함수들이 부르는
    함수다. 그 밖의 함수는 제 `with ….popover(…)` 블록 안 칸만 본다. 적기는 세션 대입·`setdefault`
    와, 칸 key 를 인자로 받아 그 칸에 적는 같은 모듈 도우미 한 겹이다. 다른 모듈의 도우미나 여러
    겹 도우미, 칸 key 를 다른 식으로 바꿔 쓴 적기는 보지 않는다(AGENTS 9장 「닫힌 팝업 안」).
    """
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    helpers = _prefill_helpers(functions)
    inside = _called_names(_popover_bodies(tree)) & set(functions)
    frontier = set(inside)
    while frontier:
        reached = set()
        for name in frontier:
            reached |= _called_names(functions[name].body) & set(functions)
        frontier = reached - inside
        inside |= frontier
    lines: list[int] = []
    for name, function in functions.items():
        region = function.body if name in inside else _popover_bodies(function)
        keys = _input_keys(region)
        lines.extend(line for key, line in _session_writes(function).items() if key in keys)
        lines.extend(_helper_prefills(function, keys, helpers))
    return sorted(lines)


def _ui_sources() -> list[Path]:
    paths = [ROOT / "app.py", *sorted((ROOT / "app_pages").glob("*.py"))]
    paths += sorted((ROOT / "src" / "capa_simulation" / "components").rglob("*.py"))
    return [path for path in paths if path != HELPER]


def test_no_popup_field_is_prefilled_by_a_session_assignment() -> None:
    found = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in _ui_sources()
        for line in _popup_prefills(_parse(path))
    ]
    assert not found, (
        "닫힌 팝오버 칸은 세션 대입으로 한 번 적으면 한 회차 뒤 빈 칸으로 선다 — "
        f"components/widget_generation.seed_field 로 세운다: {found}"
    )


def test_the_popup_prefill_net_catches_the_old_shape() -> None:
    sample = """
def _render_rename():
    key = f"{_keyed(RENAME_KEY)}__{scenario_id}"
    if key not in st.session_state:
        st.session_state[key] = current
    st.text_input("이름", key=key)

def _section():
    with st.popover("이름 바꾸기"):
        _render_rename()

def _toolbar():
    with st.popover("메모"):
        st.session_state["memo_text"] = ""
        st.text_area("메모", key="memo_text")
"""
    assert len(_popup_prefills(ast.parse(sample))) == 2
    # 같은 「한 번만 적기」 를 도우미로 빼거나 `setdefault` 로 써도 잡는다(2026-10-26 리뷰).
    helper = """
def _prefill(key, value):
    if key not in st.session_state:
        st.session_state[key] = value

def _render_rename():
    key = f"{_keyed(RENAME_KEY)}__{scenario_id}"
    _prefill(key, current)
    st.text_input("이름", key=key)

def _section():
    with st.popover("이름 바꾸기"):
        _render_rename()
"""
    assert _popup_prefills(ast.parse(helper)) == [8]
    setdefault = """
def _render_rename(field):
    st.session_state.setdefault(field.key, current)
    st.text_input("이름", key=field.key)

def _section():
    with st.popover("이름 바꾸기"):
        _render_rename(FIELD)
"""
    assert _popup_prefills(ast.parse(setdefault)) == [3]
    seeded = """
def _render_rename():
    field = seed_field(GENERATION_KEY, RENAME_KEY, current, suffix=suffix)
    st.text_input("이름", key=field.key)

def _section():
    with st.popover("이름 바꾸기"):
        _render_rename()
"""
    assert not _popup_prefills(ast.parse(seeded))
