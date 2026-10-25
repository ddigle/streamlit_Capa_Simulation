# Purpose: 마크다운 자리로 가는 예외 글·「이름」 이 막는 길만 지나는지 AST 로 지킨다.

"""마크다운 자리 그물(AST).

이름이 마크다운 자리(알림 상자·캡션·`st.markdown`·토스트·펼침/팝오버 라벨)로 들어오는 길은 셋이다 —
문구에 바로 끼우는 이름, 저장소·서비스 예외 글(`str(exc)`), 문구를 짓는 함수. 그리는 자리마다 막을
것을 고르면 한 자리를 고칠 때 옆 자리가 남는다(2026-10-26 E2E 1~3회차 — 「E2E~가정~A」 가 지움선).
그래서 길마다 막는 함수 하나를 두고 이 시험이 지킨다.

- 예외 글: `except … as exc` 안에서 마크다운 자리 인자에 `exc`·`str(exc)`·`f"{exc}"` 를 바로
  싣지 않는다 — `page_bootstrap.bootstrap_error_message(exc)` 만 된다(DuckDB 가 아닌 예외는
  물결표를 막은 원문).
- 이름: UI 모듈 f-string 의 `「{식}」` 에서 식은 `quoted`·`literal_markdown`·`markdown_safe_tildes`
  (또는 숫자 서식·대문자 상수·앱이 지은 라벨 함수)여야 한다 — 보통은 `「{name}」` 대신
  `{quoted(name)}`.

평문 자리(표 칸·JS 격자·편집기·조사 고르기)로도 가는 글은 짓는 곳에서 막으면 `\\~` 가 글자로
보인다. 그런 글은 `PLAIN_TEXT_BUILDERS` 에 까닭과 함께 적고, 마크다운으로 그리는 자리에서
`markdown_safe_tildes` 로 막는다(화면 그물 `tests/test_tilde_names_pages.py`).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "capa_simulation"

# 화면을 그리는 모듈 — 페이지·화면 조각과 화면 상태를 짓는 세 모듈.
UI_MODULES: tuple[Path, ...] = (
    ROOT / "app.py",
    *sorted((ROOT / "app_pages").glob("*.py")),
    *sorted((SRC / "components").glob("*.py")),
    SRC / "page_tabs_state.py",
    SRC / "sidebar_status.py",
    SRC / "equipment_scenario_activation.py",
)

# 글을 마크다운으로 그리는 Streamlit 호출(`st.`·`container.`·`slot.` 무엇에 달렸든). 첫 인자와
# `body`·`label`·`help` 를 본다.
MARKDOWN_SINKS = frozenset(
    {
        "error",
        "warning",
        "info",
        "success",
        "caption",
        "markdown",
        "toast",
        "write",
        "expander",
        "popover",
    }
)
MARKDOWN_KEYWORDS = frozenset({"body", "label", "help"})
# 같은 이름의 메서드를 가진 화면 밖 받는 쪽(로그) — 마크다운이 아니다.
NOT_STREAMLIT = frozenset({"logger", "logging", "LOGGER", "_LOGGER", "log", "warnings"})

# 막는 길. 이 호출 안의 글은 이미 막혔다고 본다.
GUARDS = frozenset(
    {"bootstrap_error_message", "markdown_safe_tildes", "literal_markdown", "quoted"}
)

# 앱이 지은 라벨을 돌려주는 함수 — 사람 글이 들지 않아 「」 안에 그대로 끼워도 된다.
APP_LABELS: dict[str, str] = {
    "confirm_label": "지워질 일정의 시나리오·호기 수만 세는 확인 칸 이름(equipment_data_workspace)",
}

# 평문 자리로도 가는 글을 짓는 함수 — 짓는 곳에서 막지 않고 마크다운으로 그리는 자리에서 막는다.
PLAIN_TEXT_BUILDERS: dict[tuple[str, str], str] = {
    ("src/capa_simulation/components/auto_official_update_tab.py", "run_history_frame"): (
        "자동 갱신 기록 표의 칸 글(st.dataframe — 마크다운이 아니다)"
    ),
    ("src/capa_simulation/components/equipment_master_tab.py", "_on_copy"): (
        "설비 마스터 표(JS) 토스트 — 평문으로 그린다"
    ),
    ("src/capa_simulation/components/equipment_data_workspace.py", "_stale_lock_message"): (
        "설비 마스터 표(JS) 잠금 풍선에도 간다 — 경고 상자는 그리는 자리에서 markdown_safe_tildes"
    ),
    ("src/capa_simulation/components/equipment_data_workspace.py", "stale_delete_lock"): (
        "설비 마스터 표(JS) 삭제 잠금 글에도 간다 — 단추 풍선은 그리는 자리에서 "
        "markdown_safe_tildes"
    ),
    ("src/capa_simulation/equipment_scenario_activation.py", "_quoted"): (
        "잠금 글·세션 알림 — 설비 마스터 표(JS)·배치 편집기에도 간다. 마크다운 자리(Space 잠금 줄·"
        "풍선·세션 알림 상자)는 그리는 자리에서 markdown_safe_tildes"
    ),
    ("src/capa_simulation/equipment_scenario_activation.py", "unmerged_trace_notice"): (
        "세션 알림 — 설비 마스터 표(JS) 잠금 글에도 간다. 알림 상자는 그리는 자리에서 막는다"
    ),
    ("src/capa_simulation/equipment_scenario_activation.py", "_move_after_incompatible"): (
        "세션 알림 — 설비 마스터 표(JS) 잠금 글에도 간다. 알림 상자는 그리는 자리에서 막는다"
    ),
    ("app_pages/space_status.py", "_session_place"): (
        "Space 팝오버 설명·알림 글 조각 — 그리는 자리(캡션·_queue_space_flash)에서 "
        "markdown_safe_tildes"
    ),
    ("app_pages/space_status.py", "_scenario_place"): (
        "Space 저장 안내·알림 글 조각 — 그리는 자리(캡션·_queue_space_flash)에서 "
        "markdown_safe_tildes"
    ),
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    function: str
    text: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line} ({self.function}) {self.text}"


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _markdown_sink_arguments(call: ast.Call) -> list[ast.expr]:
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in MARKDOWN_SINKS:
        return []
    if isinstance(func.value, ast.Name) and func.value.id in NOT_STREAMLIT:
        return []
    return [*call.args, *(kw.value for kw in call.keywords if kw.arg in MARKDOWN_KEYWORDS)]


def _bare_references(expr: ast.expr, name: str) -> Iterator[ast.expr]:
    """`expr` 가 `name`(예외 변수)을 막지 않고 바로 담는 자리 — 이름 자체·`str(name)`·f-string
    조각·`+` 이음·조건식. 다른 호출(막는 함수 포함) 안은 보지 않는다."""
    if isinstance(expr, ast.Name):
        if expr.id == name:
            yield expr
    elif isinstance(expr, ast.Call):
        if isinstance(expr.func, ast.Name) and expr.func.id == "str":
            for argument in expr.args:
                yield from _bare_references(argument, name)
    elif isinstance(expr, ast.JoinedStr):
        for value in expr.values:
            yield from _bare_references(value, name)
    elif isinstance(expr, ast.FormattedValue):
        yield from _bare_references(expr.value, name)
    elif isinstance(expr, ast.BinOp):
        yield from _bare_references(expr.left, name)
        yield from _bare_references(expr.right, name)
    elif isinstance(expr, ast.IfExp):
        yield from _bare_references(expr.body, name)
        yield from _bare_references(expr.orelse, name)


class _Scanner(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = _relative(path)
        self.source = path.read_text(encoding="utf-8")
        self.functions: list[str] = []
        self.exception_findings: list[Finding] = []
        self.name_findings: list[Finding] = []

    @property
    def function(self) -> str:
        return self.functions[-1] if self.functions else "<module>"

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            for statement in node.body:
                for call in ast.walk(statement):
                    if not isinstance(call, ast.Call):
                        continue
                    for argument in _markdown_sink_arguments(call):
                        for reference in _bare_references(argument, node.name):
                            self.exception_findings.append(
                                Finding(
                                    self.path,
                                    reference.lineno,
                                    self.function,
                                    ast.get_source_segment(self.source, call) or "",
                                )
                            )
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        values = node.values
        for index, value in enumerate(values):
            if not isinstance(value, ast.FormattedValue):
                continue
            before = values[index - 1] if index else None
            after = values[index + 1] if index + 1 < len(values) else None
            if not (
                isinstance(before, ast.Constant)
                and str(before.value).endswith("「")
                and isinstance(after, ast.Constant)
                and str(after.value).startswith("」")
            ):
                continue
            if _quoted_value_is_guarded(value):
                continue
            self.name_findings.append(
                Finding(
                    self.path,
                    value.lineno,
                    self.function,
                    f"「{{{ast.get_source_segment(self.source, value.value)}}}」",
                )
            )
        self.generic_visit(node)


def _is_constant_reference(expr: ast.expr) -> bool:
    """대문자 모듈 상수(`PASTE_LAYOUT_LABEL`·`GROUP_TITLES["sched"]`) — 앱이 적은 글이다."""
    while isinstance(expr, (ast.Attribute, ast.Subscript)):
        expr = expr.value
    return isinstance(expr, ast.Name) and expr.id.isupper()


def _quoted_value_is_guarded(value: ast.FormattedValue) -> bool:
    if value.format_spec is not None:
        return True
    expr = value.value
    if isinstance(expr, ast.Constant):
        return True
    if isinstance(expr, ast.Call):
        name = _call_name(expr.func)
        return name in GUARDS or name in APP_LABELS
    return _is_constant_reference(expr)


def _scan() -> list[_Scanner]:
    scanners = []
    for path in UI_MODULES:
        scanner = _Scanner(path)
        scanner.visit(ast.parse(scanner.source, filename=str(path)))
        scanners.append(scanner)
    return scanners


def test_exception_text_reaches_markdown_only_through_bootstrap_error_message() -> None:
    findings = [str(item) for scanner in _scan() for item in scanner.exception_findings]

    assert not findings, (
        "예외 글을 마크다운 자리에 바로 실었습니다 — bootstrap_error_message(exc) 로 바꾸세요 "
        "(저장소 예외 글은 사람이 지은 이름을 날로 담아 물결표가 지움선이 됩니다):\n"
        + "\n".join(findings)
    )


def test_quoted_names_in_ui_strings_go_through_quoted() -> None:
    findings = [
        str(item)
        for scanner in _scan()
        for item in scanner.name_findings
        if (item.path, item.function) not in PLAIN_TEXT_BUILDERS
    ]

    assert not findings, (
        "「{이름}」 을 막지 않고 끼웠습니다 — {quoted(이름)} 으로 바꾸세요. 평문 자리로도 가는 "
        "글이면 PLAIN_TEXT_BUILDERS 에 까닭을 적고 그리는 자리에서 markdown_safe_tildes 로 "
        "막습니다:\n" + "\n".join(findings)
    )


def test_every_plain_text_builder_still_quotes_a_name() -> None:
    """적어 둔 예외가 낡지 않는다 — 함수가 사라졌거나 이제 막는 길을 타면 목록에서 뺀다."""
    used = {(item.path, item.function) for scanner in _scan() for item in scanner.name_findings}

    assert not set(PLAIN_TEXT_BUILDERS) - used


def test_every_app_label_function_is_still_quoted_somewhere() -> None:
    sources = [path.read_text(encoding="utf-8") for path in UI_MODULES]

    for name in APP_LABELS:
        assert any(f"「{{{name}(" in source or f".{name}()}}」" in source for source in sources), (
            name
        )


def test_the_guard_catches_raw_exception_text_and_bare_names() -> None:
    """그물이 실제로 걸리는지 — 막지 않은 꼴은 잡고 막은 꼴은 지나간다."""
    source = """
def render(name):
    try:
        pass
    except ValueError as exc:
        st.error(str(exc))
        notice.warning(f"저장하지 못했습니다 — {exc}")
        st.caption("까닭: " + str(exc))
        st.error(bootstrap_error_message(exc))
        st.error(f"못 했습니다: {bootstrap_error_message(exc)}")
        logger.warning("%s", exc)
    st.success(f"「{name}」 저장")
    st.success(f"{quoted(name)} 저장 · 「{literal_markdown(name)}」 · 「{COUNT:,}」 · 「{LABEL}」")
"""
    path = ROOT / "tests" / "_markdown_sink_guard_sample.py"
    scanner = _Scanner.__new__(_Scanner)
    scanner.path = _relative(path)
    scanner.source = source
    scanner.functions = []
    scanner.exception_findings = []
    scanner.name_findings = []
    scanner.visit(ast.parse(source))

    assert [item.line for item in scanner.exception_findings] == [6, 7, 8]
    assert [item.text for item in scanner.name_findings] == ["「{name}」"]
