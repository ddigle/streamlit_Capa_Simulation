# Purpose: 마크다운 자리로 가는 예외 글·「이름」 이 막는 길만 지나는지 AST 로 지킨다.

"""마크다운 자리 그물(AST).

이름이 마크다운 자리(알림 상자·캡션·`st.markdown`·토스트·펼침/팝오버 라벨)로 들어오는 길은 셋이다 —
문구에 바로 끼우는 이름, 저장소·서비스 예외 글(`str(exc)`), 문구를 짓는 함수. 그리는 자리마다 막을
것을 고르면 한 자리를 고칠 때 옆 자리가 남는다(2026-10-26 E2E 1~3회차 — 「E2E~가정~A」 가 지움선).
그래서 길마다 막는 함수 하나를 두고 이 시험이 지킨다.

- 예외 글: `except … as exc` 안에서 예외를 글로 바꾸는 꼴(`str(exc)`·`f"{exc}"`·
  `"…".format(exc)`·`"…%s" % exc`)은 **어디에 쓰든**(마크다운 자리 인자·대입·도우미 인자·세션 칸·
  돌려주는 값) 실패한다. 마크다운 자리 인자에 `exc` 를 그대로 넘겨도 실패한다. 지나가는 것은
  막는 함수 안(`page_bootstrap.bootstrap_error_message(exc)` — DuckDB 가 아닌 예외는 물결표를 막은
  원문 — 와 `literal_markdown`·`markdown_safe_tildes`·`quoted`), `raise` 로 다시 던지는 글(받는
  쪽이 막는다), 로그, 평문 자리(`st.code`·`st.text`·`st.json`·`html.escape`), 까닭 가르기
  (`"lock" in str(exc)`) 뿐이다. 마크다운이 아닌 곳으로만 가는 글을 짓는 함수는
  `PLAIN_EXCEPTION_TEXT` 에 까닭과 함께 적는다.
- 막은 글을 다시 감싸지 않는다: `markdown_safe_tildes`·`literal_markdown`·`quoted` 안에
  `bootstrap_error_message` 를 넣지 않는다 — 앞의 것은 같은 값이라 길이 둘로 보이고(DuckDB 글의
  코드 칸 경로 물결표는 `\\~` 로 보인다), 뒤의 둘은 막은 `\\~` 의 `\\` 를 다시 막아 글자로 보인다.
- 이름: UI 모듈 f-string 의 `「{식}」` 에서 식은 `quoted`·`literal_markdown`·`markdown_safe_tildes`
  (또는 숫자 서식·대문자 상수·앱이 지은 라벨 함수)여야 한다 — 보통은 `「{name}」` 대신
  `{quoted(name)}`.

평문 자리(표 칸·JS 격자·편집기·조사 고르기)로도 가는 글은 짓는 곳에서 막으면 `\\~` 가 글자로
보인다. 그런 글은 `PLAIN_TEXT_BUILDERS` 에 까닭과 함께 적고, 마크다운으로 그리는 자리에서
`markdown_safe_tildes` 로 막는다(화면 그물 `tests/test_tilde_names_pages.py`).

**이 그물이 보지 못하는 것** — 예외의 속성(`exc.reason`), 서비스 계층이 예외를 받아 지어 돌려준
글(`CapacityOutcome.error`), 낫표 밖에 날로 끼운 이름(`f"… · {label}"`), 이름을 담은 변수를 거쳐
가는 글. 이것은 그리는 자리에서 막고 화면 그물과 리뷰가 본다.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "capa_simulation"

# 화면을 그리는 모듈 — 페이지·화면 조각과 화면 상태·글을 짓는 꼭대기 모듈(`process_detail_state`
# 의 출처 띠·`equipment_scenario_activation` 의 세션 알림 등). 서비스·저장소 계층은 보지 않는다.
UI_MODULES: tuple[Path, ...] = (
    ROOT / "app.py",
    *sorted((ROOT / "app_pages").glob("*.py")),
    *sorted((SRC / "components").glob("*.py")),
    *sorted(SRC.glob("*.py")),
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
# 글을 글자 그대로 그리거나 HTML 로 막는 호출 — 이 안의 예외 글은 마크다운이 아니다.
PLAIN_SINKS = frozenset({"code", "text", "json", "escape", "_escape"})

# 막는 길. 이 호출 안의 글은 이미 막혔다고 본다.
GUARDS = frozenset(
    {"bootstrap_error_message", "markdown_safe_tildes", "literal_markdown", "quoted"}
)

# 앱이 지은 라벨을 돌려주는 함수 — 사람 글이 들지 않아 「」 안에 그대로 끼워도 된다.
APP_LABELS: dict[str, str] = {
    "confirm_label": "지워질 일정의 시나리오·호기 수만 세는 확인 칸 이름(equipment_data_workspace)",
}

# 예외 글을 마크다운이 아닌 곳으로만 보내는 함수 — 이 함수 안의 except 는 예외 글 그물을 비킨다.
PLAIN_EXCEPTION_TEXT: dict[tuple[str, str], str] = {
    ("src/capa_simulation/components/capacity_gate.py", "density_error"): (
        "판정 글 — 자동 갱신 기록 표 칸(평문)에도 남는다. 알림 상자는 그리는 자리(capacity_gate·"
        "alert_board.collect_alerts)에서 markdown_safe_tildes"
    ),
    ("src/capa_simulation/components/capacity_gate.py", "_capacity_error"): (
        "판정 글 — density_error 와 같은 길(그리는 자리에서 markdown_safe_tildes)"
    ),
    ("src/capa_simulation/components/equipment_data_workspace.py", "save_equipment_buffer"): (
        "FAB 저장 거부 글 — 늘 다시 던지는 ValueError 에 담겨 받는 쪽이 bootstrap_error_message"
    ),
    ("src/capa_simulation/components/equipment_master_tab.py", "_table_errors"): (
        "설비 마스터 표(JS) 「저장하기 전에 고칠 것」 줄 — 평문으로 그린다"
    ),
    ("src/capa_simulation/components/intro_summary.py", "_guarded"): (
        "입장 화면 Summary 데이터(JSON) — 브라우저 스크립트가 글자로 그린다"
    ),
    ("src/capa_simulation/components/intro_summary.py", "_build_or_unavailable"): (
        "입장 화면 Summary 데이터(JSON) — 브라우저 스크립트가 글자로 그린다"
    ),
    ("src/capa_simulation/components/intro_summary.py", "_look_up"): (
        "입장 화면 Summary 데이터(JSON) — 브라우저 스크립트가 글자로 그린다"
    ),
    ("src/capa_simulation/components/intro_summary.py", "official_summary_data"): (
        "입장 화면 Summary 데이터(JSON) — 브라우저 스크립트가 글자로 그린다"
    ),
    ("src/capa_simulation/components/required_shortening_panel.py", "_lob_rows"): (
        "LOB 칸 HTML — 그리는 자리가 html.escape(_escape)"
    ),
}

# 평문 자리로도 가는 글을 짓는 함수 — 짓는 곳에서 막지 않고 마크다운으로 그리는 자리에서 막는다.
PLAIN_TEXT_BUILDERS: dict[tuple[str, str], str] = {
    ("src/capa_simulation/auto_official_update_runner.py", "finish"): (
        "자동 갱신 회차 사유 — 회차 기록(기록 표 칸 — 평문)에 남는다. 「지금 실행」 결과 알림은 "
        "그리는 자리(auto_official_update_tab._render_run_result)에서 markdown_safe_tildes"
    ),
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


def _is_log_call(call: ast.Call) -> bool:
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in NOT_STREAMLIT
    )


def _markdown_sink_arguments(call: ast.Call) -> list[ast.expr]:
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in MARKDOWN_SINKS:
        return []
    if _is_log_call(call):
        return []
    return [*call.args, *(kw.value for kw in call.keywords if kw.arg in MARKDOWN_KEYWORDS)]


def _is_name(expr: ast.AST, name: str) -> bool:
    return isinstance(expr, ast.Name) and expr.id == name


def _bare_sink_references(expr: ast.expr, name: str) -> Iterator[ast.expr]:
    """마크다운 자리 인자 `expr` 가 예외 변수 `name` 을 글로 바꾸지 않고 그대로 담는 자리 — 이름
    자체와 조건식의 두 갈래(`st.error(exc)` 는 Streamlit 이 `str` 로 바꿔 그린다). 글로 바꾼 꼴
    (`str`·f-string·`%`)은 `_exception_text` 가 본다."""
    if _is_name(expr, name):
        yield expr
    elif isinstance(expr, ast.IfExp):
        yield from _bare_sink_references(expr.body, name)
        yield from _bare_sink_references(expr.orelse, name)


def _exception_text(node: ast.AST, name: str) -> Iterator[ast.AST]:
    """`node` 안에서 예외 변수 `name` 을 막지 않고 글로 바꾸는 자리. 다시 던지는 글·견줌·막는
    함수·평문 자리·로그 안은 보지 않는다."""
    if isinstance(node, (ast.Raise, ast.Compare)):
        return
    if isinstance(node, ast.Call):
        called = _call_name(node.func)
        if called in GUARDS or called in PLAIN_SINKS or _is_log_call(node):
            return
        for argument in _markdown_sink_arguments(node):
            yield from _bare_sink_references(argument, name)
        arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
        if called in ("str", "format") and any(_is_name(item, name) for item in arguments):
            yield node
            return
    elif isinstance(node, ast.FormattedValue) and _is_name(node.value, name):
        yield node
        return
    elif (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Mod)
        and isinstance(node.left, (ast.Constant, ast.JoinedStr))
        and any(_is_name(item, name) for item in ast.walk(node.right))
    ):
        yield node
        return
    for child in ast.iter_child_nodes(node):
        yield from _exception_text(child, name)


class _Scanner(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = _relative(path)
        self.source = path.read_text(encoding="utf-8")
        self.functions: list[str] = []
        self.exception_findings: list[Finding] = []
        self.double_findings: list[Finding] = []
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

    def _finding(self, node: ast.AST) -> Finding:
        return Finding(
            self.path,
            getattr(node, "lineno", 0),
            self.function,
            ast.get_source_segment(self.source, node) or "",
        )

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            for statement in node.body:
                for reference in _exception_text(statement, node.name):
                    self.exception_findings.append(self._finding(reference))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func) in GUARDS - {"bootstrap_error_message"} and any(
            isinstance(inner, ast.Call) and _call_name(inner.func) == "bootstrap_error_message"
            for argument in node.args
            for inner in ast.walk(argument)
        ):
            self.double_findings.append(self._finding(node))
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
    findings = [
        str(item)
        for scanner in _scan()
        for item in scanner.exception_findings
        if (item.path, item.function) not in PLAIN_EXCEPTION_TEXT
    ]

    assert not findings, (
        "예외 글을 막지 않고 글로 바꿨습니다 — bootstrap_error_message(exc) 로 바꾸세요 "
        "(저장소 예외 글은 사람이 지은 이름을 날로 담아 물결표가 지움선이 됩니다). 마크다운이 "
        "아닌 곳으로만 가는 글이면 PLAIN_EXCEPTION_TEXT 에 까닭을 적습니다:\n" + "\n".join(findings)
    )


def test_every_plain_exception_text_function_still_turns_an_exception_into_text() -> None:
    """적어 둔 예외가 낡지 않는다 — 함수가 사라졌거나 이제 막는 길을 타면 목록에서 뺀다."""
    used = {
        (item.path, item.function) for scanner in _scan() for item in scanner.exception_findings
    }

    assert not set(PLAIN_EXCEPTION_TEXT) - used


def test_blocked_exception_text_is_not_blocked_again() -> None:
    findings = [str(item) for scanner in _scan() for item in scanner.double_findings]

    assert not findings, (
        "bootstrap_error_message 가 돌려준 글을 다시 감쌌습니다 — 이미 막힌 글입니다:\n"
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


def _sample_scanner(source: str) -> _Scanner:
    path = ROOT / "tests" / "_markdown_sink_guard_sample.py"
    scanner = _Scanner.__new__(_Scanner)
    scanner.path = _relative(path)
    scanner.source = source
    scanner.functions = []
    scanner.exception_findings = []
    scanner.double_findings = []
    scanner.name_findings = []
    scanner.visit(ast.parse(source))
    return scanner


def test_the_guard_catches_raw_exception_text_and_bare_names() -> None:
    """그물이 실제로 걸리는지 — 막지 않은 꼴은 잡고 막은 꼴은 지나간다."""
    scanner = _sample_scanner("""
def render(name):
    try:
        pass
    except ValueError as exc:
        st.error(str(exc))
        notice.warning(f"저장하지 못했습니다 — {exc}")
        st.caption("까닭: " + str(exc))
        st.error(exc)
        st.error(bootstrap_error_message(exc))
        st.error(f"못 했습니다: {bootstrap_error_message(exc)}")
        logger.warning("%s", exc)
    st.success(f"「{name}」 저장")
    st.success(f"{quoted(name)} 저장 · 「{literal_markdown(name)}」 · 「{COUNT:,}」 · 「{LABEL}」")
""")

    assert [item.line for item in scanner.exception_findings] == [6, 7, 8, 9]
    assert [item.text for item in scanner.name_findings] == ["「{name}」"]


def test_the_guard_follows_exception_text_off_the_markdown_call() -> None:
    """예외 글은 마크다운 자리 밖에서 지어도 걸린다 — 대입·도우미 인자·세션 칸·돌려주는 값·
    `.format`·`%`. 다시 던지는 글·견줌·평문 자리·막는 함수 안은 지나간다(2026-10-26 리뷰 — 그리는
    자리 인자만 보던 그물은 이 꼴로 되돌린 자리를 몰랐다)."""
    scanner = _sample_scanner("""
def render():
    try:
        pass
    except ValueError as exc:
        message = str(exc)
        _notice("warning", f"기준선을 저장하지 않았습니다 — {exc}")
        st.session_state[KEY] = (str(exc), "본문")
        st.error("오류: {}".format(exc))
        st.error("오류: %s" % exc)
        return str(exc)
    except KeyError as error:
        if "lock" in str(error):
            raise ValueError(f"다시 던짐 — {error}") from error
        st.code(f"{type(error).__name__}: {error}")
        _refused(literal_markdown(str(error)))
        _refused(f"바꾸지 않았습니다 — {bootstrap_error_message(error)}")
        st.html(f"<p>{html.escape(str(error))}</p>")
""")

    assert [item.line for item in scanner.exception_findings] == [6, 7, 8, 9, 10, 11]


def test_the_guard_catches_a_blocked_message_blocked_again() -> None:
    scanner = _sample_scanner("""
st.error(markdown_safe_tildes(f"못 했습니다: {bootstrap_error_message(exc)}"))
st.error(literal_markdown(bootstrap_error_message(exc)))
st.error(markdown_safe_tildes(refused))
st.error(f"못 했습니다: {bootstrap_error_message(exc)}")
""")

    assert [item.line for item in scanner.double_findings] == [2, 3]
