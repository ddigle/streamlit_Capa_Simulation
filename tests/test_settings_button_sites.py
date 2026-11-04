# Purpose: 「설정」 팝업을 여는 단추가 본문에 없고 사이드바 설정 상자로만 서는지 소스에서 본다.

"""본문 설정 단추 그물(설계 규칙 UI-LAY-01 — `docs/design_rules.md` 5-1).

화면 설정 묶음(여럿이 함께 쓰는 공용 값을 고치는 팝업)을 여는 단추는 페이지 본문에 두지 않고
사이드바 조회 조건 패널 바로 밑 설정 상자(`components/settings_box.py` — 상자 = 단추 → 같은 제목
팝업)로 둔다(2026-11-03 사용자 지시 · 2026-11-04 확인 보드 AMB-07 (가)). 새 화면도 같다.

- 화면 코드(`app.py` · `app_pages/` · `src/capa_simulation/`, 상자를 그리는 `settings_box.py`
  밖)의 `st.button(` · `st.popover(`(칸 · 사이드바의 같은 이름 부름 포함)를 두 길로 찾아 허용 목록과
  맞댄다.
  - **라벨** — 라벨에 「설정」 이 든 단추. 저장 · 적용 · 지우기 같은 쓰기 단추(「설정 저장」)는
    팝업을 열지 않아 뺀다. 편집표에 딸린 「표 보기 설정」 은 펼침(`st.expander`)이라 팝업 단추가
    아니다(AMB-07 (가) — 본문).
  - **여는 콜백** — 설정 상자가 부르는 여는 함수(`render_settings_box(on_click=…)` 에 준 이름 —
    `open_home_settings` · `open_equipment_settings`)를 `on_click`(이름 · `lambda` · `partial` ·
    같은 파일 함수 한 겹 안의 부름)이나 `if st.button(…):` 본문에서 부르는 단추. 아이콘만 단 단추 ·
    「설정」 이 없는 라벨(「설정에서 보기」 처럼 갈 곳을 말하는 라벨도)도 여기서 걸린다.
  라벨 · 콜백은 `for` 가 도는 묶음(`for (제목, 라벨, 콜백), key in zip(묶음, keys)` 처럼 펼친
  이름)도 푼다.
- 제목에 「설정」 이 든 팝업(`st.dialog`)은 모두 같은 제목의 사이드바 설정 상자
  (`render_settings_box`)가 연다 — 본문 단추로 여는 새 설정 팝업은 상자가 없어 실패한다.
- 라벨 · 콜백을 매개변수로 받는 단추(공용 도우미 안)는 그물 밖이다 — 판단 질문이 본다.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from source_sites import (
    PROJECT_ROOT,
    Function,
    TextResolver,
    called_name,
    first_text_argument,
    method,
    screen_calls,
    screen_files,
)

SETTINGS_WORD = "설정"
# 사이드바 설정 상자 — 이 모듈만 「… 설정」 단추를 그린다.
OWNERS = ("src/capa_simulation/components/settings_box.py",)
# 팝업을 여는 단추.
OPENERS = frozenset({"button", "popover"})
# 쓰기 단추의 낱말 — 「설정 저장」 처럼 설정 값을 쓰는 단추는 팝업을 열지 않는다.
WRITE_WORDS = ("저장", "적용", "지우", "되돌", "초기화", "버리", "내려받")
# (파일, 맨 바깥 함수) → (설정 팝업을 여는 단추 수, 까닭). 새 자리를 들이지 않는다 — 공용 값을
# 고치는 팝업은 사이드바 설정 상자로 연다.
ALLOWED: dict[tuple[str, str], tuple[int, str]] = {
    ("src/capa_simulation/components/home_main_case_chips.py", "render_main_case_chips"): (
        1,
        "UI-NAV-01 「칩 → 설정 팝업」 — 사이드바 「LOB 표시 조건」 카드의 미지정 주요 Case 칩은"
        " 불러올 리비전이 없어 HOME 설정 `비교 · 주요 Case` 탭의 그 Case 칸을 열고 짚는다(검수"
        " home-u03 · AMB-15 (가)). 칩의 일은 시나리오 불러오기다 — 설정 단추가 아니다",
    ),
}


def _opens_settings(label: str) -> bool:
    return SETTINGS_WORD in label and not any(word in label for word in WRITE_WORDS)


def _items(node: ast.expr, scope: Function | None, path: Path) -> list[ast.expr]:
    """`for` 가 도는 묶음의 칸 — 글자 그대로의 튜플 · 목록, 또는 그 맨 바깥 함수 안 지역 이름 ·
    모듈 맨 위 이름에 넣은 튜플 · 목록."""
    if isinstance(node, ast.Tuple | ast.List):
        return list(node.elts)
    if not isinstance(node, ast.Name):
        return []
    homes: list[ast.AST] = [scope] if scope is not None else []
    homes.append(ast.parse(path.read_text(encoding="utf-8")))
    for home in homes:
        for item in ast.walk(home):
            if (
                isinstance(item, ast.Assign)
                and len(item.targets) == 1
                and isinstance(item.targets[0], ast.Name)
                and item.targets[0].id == node.id
                and isinstance(item.value, ast.Tuple | ast.List)
            ):
                return list(item.value.elts)
    return []


def _unpack(target: ast.expr, value: ast.expr, name: str) -> Iterator[ast.expr]:
    if isinstance(target, ast.Name):
        if target.id == name:
            yield value
    elif isinstance(target, ast.Tuple) and isinstance(value, ast.Tuple | ast.List):
        if len(target.elts) == len(value.elts):
            for part, item in zip(target.elts, value.elts, strict=True):
                yield from _unpack(part, item, name)


def _bound(
    target: ast.expr, source: ast.expr, name: str, scope: Function | None, path: Path
) -> Iterator[ast.expr]:
    """`for target in source` 가 `name` 에 넣는 식들 — `zip(…)` 은 칸마다 짝지어 푼다."""
    if (
        isinstance(source, ast.Call)
        and called_name(source) == "zip"
        and isinstance(target, ast.Tuple)
        and len(target.elts) == len(source.args)
    ):
        for part, argument in zip(target.elts, source.args, strict=True):
            yield from _bound(part, argument, name, scope, path)
        return
    for item in _items(source, scope, path):
        yield from _unpack(target, item, name)


def loop_values(name: str, scope: Function | None, path: Path) -> list[ast.expr]:
    """맨 바깥 함수 안 `for` 가 이름 `name` 에 넣는 식들(없으면 빈 목록)."""
    if scope is None:
        return []
    return [
        value
        for node in ast.walk(scope)
        if isinstance(node, ast.For)
        for value in _bound(node.target, node.iter, name, scope, path)
    ]


def _labels(
    call: ast.Call, path: Path, scope: Function | None, resolver: TextResolver
) -> list[str]:
    label = first_text_argument(call, "label")
    if label is None:
        return []
    texts = resolver.wholes(label, path, scope)
    if isinstance(label, ast.Name):
        for value in loop_values(label.id, scope, path):
            texts.extend(resolver.wholes(value, path, scope))
    return texts


def _function_names(node: ast.expr, scope: Function | None, path: Path) -> set[str]:
    """콜백 식이 가리키는 함수 이름 — 이름 · 속성 · `lambda` 본문의 부름 · `partial(f, …)` ·
    `ctx.callback(f)` · `for` 가 넣은 이름."""
    if isinstance(node, ast.Name):
        values = loop_values(node.id, scope, path)
        if values:
            return {name for value in values for name in _function_names(value, scope, path)}
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, ast.Lambda):
        return {called_name(item) for item in ast.walk(node.body) if isinstance(item, ast.Call)}
    if isinstance(node, ast.Call) and node.args:
        return _function_names(node.args[0], scope, path)
    return set()


def settings_openers(paths: list[Path], root: Path = PROJECT_ROOT) -> frozenset[str]:
    """설정 상자가 부르는 여는 함수 — `render_settings_box(on_click=…)` 에 준 이름."""
    names: set[str] = set()
    for _relative, _outer, path, scope, call in screen_calls(paths, root):
        if called_name(call) != "render_settings_box":
            continue
        for item in call.keywords:
            if item.arg == "on_click":
                names |= _function_names(item.value, scope, path)
    return frozenset(names)


def _calls_opener(names: set[str], path: Path, openers: frozenset[str], *, depth: int = 1) -> bool:
    """이름들 가운데 여는 함수가 있거나, 같은 파일 맨 위 함수가 (한 겹 안에서) 여는 함수를
    부른다."""
    if names & openers:
        return True
    if depth <= 0:
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in names:
            called = {called_name(item) for item in ast.walk(node) if isinstance(item, ast.Call)}
            if _calls_opener(called, path, openers, depth=depth - 1):
                return True
    return False


def _guarded_openers(tree: ast.AST, openers: frozenset[str], path: Path) -> set[int]:
    """`if st.button(…):` 본문이 여는 함수를 부르는 단추 부름의 줄 번호."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        buttons = [
            item
            for item in ast.walk(node.test)
            if isinstance(item, ast.Call) and method(item) in OPENERS
        ]
        called = {
            called_name(item)
            for statement in node.body
            for item in ast.walk(statement)
            if isinstance(item, ast.Call)
        }
        if buttons and _calls_opener(called, path, openers):
            lines.update(item.lineno for item in buttons)
    return lines


def body_settings_buttons(
    paths: list[Path] | None = None, root: Path = PROJECT_ROOT
) -> dict[tuple[str, str], list[int]]:
    """(파일, 맨 바깥 함수) 마다 설정 팝업을 여는 단추(라벨에 「설정」 · 여는 콜백)의 줄 번호."""
    files = paths or screen_files(exclude=OWNERS)
    openers = settings_openers(files, root)
    resolver = TextResolver()
    guarded: dict[Path, set[int]] = {}
    found: dict[tuple[str, str], list[int]] = {}
    for relative, outer, path, scope, call in screen_calls(files, root):
        if method(call) not in OPENERS:
            continue
        if path not in guarded:
            guarded[path] = _guarded_openers(
                ast.parse(path.read_text(encoding="utf-8")), openers, path
            )
        callbacks = {
            name
            for item in call.keywords
            if item.arg == "on_click"
            for name in _function_names(item.value, scope, path)
        }
        if (
            any(_opens_settings(text) for text in _labels(call, path, scope, resolver))
            or _calls_opener(callbacks, path, openers)
            or call.lineno in guarded[path]
        ):
            found.setdefault((relative, outer), []).append(call.lineno)
    return found


def _titles(paths: list[Path], root: Path, name: str) -> dict[str, str]:
    """제목에 「설정」 이 든 `name` 부름(`st.dialog` · `render_settings_box`)의 제목 → 자리."""
    resolver = TextResolver()
    titles: dict[str, str] = {}
    for relative, outer, path, scope, call in screen_calls(paths, root):
        if called_name(call) != name:
            continue
        title = first_text_argument(call, "title")
        if title is None:
            continue
        for text in resolver.wholes(title, path, scope):
            if SETTINGS_WORD in text:
                titles[text] = f"{relative} {outer or '(본문)'}"
    return titles


def test_no_page_body_opens_a_settings_popup() -> None:
    found = body_settings_buttons()
    allowed = {site: count for site, (count, _why) in ALLOWED.items()}
    assert {site: len(lines) for site, lines in found.items()} == allowed, (
        "설정 팝업을 여는 단추(라벨에 「설정」 · 여는 콜백)가 설정 상자 밖에 있습니다(줄 번호) —"
        " 공용 값을 고치는 팝업은 사이드바 설정 상자(components/settings_box.render_settings_box)로"
        " 엽니다:\n"
        + "\n".join(f"{file} {func or '(본문)'}: {lines}" for (file, func), lines in found.items())
    )


def test_every_allowed_opener_says_why() -> None:
    assert all(count > 0 and why for count, why in ALLOWED.values())


def test_the_settings_boxes_name_their_openers() -> None:
    """여는 콜백 길은 설정 상자의 `on_click` 이름에서 나온다 — 이름을 못 읽으면 그물이 빈다."""
    assert {"open_home_settings", "open_equipment_settings"} <= settings_openers(
        screen_files(exclude=OWNERS)
    )


def test_every_settings_popup_opens_from_a_sidebar_box() -> None:
    files = screen_files()
    dialogs = _titles(files, PROJECT_ROOT, "dialog")
    boxes = _titles(files, PROJECT_ROOT, "render_settings_box")

    assert dialogs, "제목에 「설정」 이 든 팝업을 찾지 못했습니다 — 그물이 낡았습니다."
    missing = {title: place for title, place in dialogs.items() if title not in boxes}
    assert not missing, (
        "사이드바 설정 상자 없이 서는 설정 팝업입니다 — 같은 제목으로 render_settings_box 를"
        f" 부르세요: {missing}"
    )


SAMPLE_PAGE = """
import streamlit as st

from capa_simulation.components.settings_box import render_settings_box

TITLE = "가동 설정"


def open_page_settings() -> None:
    st.session_state["dialog"] = "settings"


def _jump() -> None:
    open_page_settings()


def render(slot) -> None:
    render_settings_box("화면 설정", name="page", button_key="b", on_click=open_page_settings,
                        tooltip="")
    st.button(TITLE)
    slot.popover("표 설정")
    st.button(f"{TITLE} 저장")
    st.form_submit_button("설정 적용")
    st.expander("표 보기 설정")
    st.button("열기")
    st.button(":material/settings:", on_click=open_page_settings)
    st.button("바로", on_click=_jump)
    st.button("람다", on_click=lambda: open_page_settings())
    if st.button("가기"):
        open_page_settings()
    steps = (("마스터", "붙여넣기", print), ("Cut-off", "설정에서 보기", open_page_settings))
    for (title, action, callback), key in zip(steps, ("k1", "k2"), strict=True):
        st.button(action, key=key, on_click=callback)
    for label in ("표시 설정", "닫기"):
        st.button(label)
"""


def test_the_net_finds_a_settings_opener_in_the_body(tmp_path: Path) -> None:
    """라벨에 「설정」 이 든 단추와, 설정 상자의 여는 함수를 콜백(이름 · 같은 파일 함수 한 겹 ·
    `lambda` · `for` 묶음) · `if` 본문으로 부르는 단추를 센다 — 쓰기 단추 · 펼침 · 다른 콜백은 세지
    않는다."""
    page = tmp_path / "page.py"
    page.write_text(SAMPLE_PAGE, encoding="utf-8")

    found = body_settings_buttons([page], tmp_path)

    # TITLE · 표 설정 · 아이콘 단추 · _jump · lambda · if 본문 · for 묶음(설정에서 보기 — 붙여넣기와
    # 한 부름이라 한 번) · for 라벨(표시 설정 — 닫기와 한 부름이라 한 번).
    assert {site: len(lines) for site, lines in found.items()} == {("page.py", "render"): 8}
    assert settings_openers([page], tmp_path) == {"open_page_settings"}
