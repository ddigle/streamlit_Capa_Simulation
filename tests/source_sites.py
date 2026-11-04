# Purpose: 화면 코드 그물 시험이 함께 쓰는 소스 훑기(파일 · 바깥 함수 · 글 풀기 · 자리 글 까닭).

"""화면 코드 그물의 소스 훑기(설계 규칙 `docs/design_rules.md` 5-1 정적 시험).

그물 시험은 화면 코드(`app.py` · `app_pages/` · `src/capa_simulation/`)를 AST 로 훑어 어떤 호출이
(파일, 맨 바깥 함수 — 모듈 본문은 "") 마다 몇 번 서는지 세고 허용 목록과 **정확히** 맞댄다
(`tests/test_alert_sites.py` 의 꼴). 맨 바깥 함수는 모듈 맨 위의 함수 · 클래스 메서드 이름이다 —
안쪽 함수 · 콜백은 바깥 함수에 센다.

화면 글 풀기(`TextResolver`)는 호출 인자가 어떤 글인지 정적으로 짐작한다. `tails` 는 **끝
글**(모르면 None), `wholes` 는 **온 글**(모르는 조각은 빈 글)이다.

- 글 상수 · f-string(`tails` 는 끝 조각 — 끝이 `{…}` 면 그 식을 다시 푼다) · `+` 로 이은 글 · `%`
  서식(왼쪽) · `a if c else b`(둘 다) · `a or b`(둘 다).
- 이름 — 그 맨 바깥 함수 안에서 그 이름에 넣은 식 → 모듈 맨 위 상수 → `from capa_simulation… import`
  로 들여온 상수. `모듈.이름`(들여온 모듈의 상수)도 푼다.
- 부름 — `글.format(…)`(받는 글) · `"sep".join([… , 끝])`(목록 끝) · 마크다운 막기
  (`literal_markdown` · `markdown_safe_tildes` · `literal_badge` — 첫 인자), 그 밖에 이 모듈이나
  `capa_simulation` 에서 들여온 함수는 그 함수의 `return` 식을 푼다(세 겹까지). 인자로 받은
  글(매개변수)은 모른다 — 그물이 못 보는 자리다(판단 질문이 본다).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
# 로거 · 경고 모듈의 `.info(` · `.warning(` 은 화면 호출이 아니다.
LOGGERS = frozenset({"logger", "logging", "log", "LOGGER", "_LOG", "_LOGGER", "warnings"})
# 첫 인자 글을 그대로 돌려주는 마크다운 막기 — 글자는 바뀌지 않는다(구두점만 막는다).
PASS_THROUGH = frozenset({"literal_markdown", "markdown_safe_tildes", "literal_badge"})
_DEPTH = 3
# `+` 로 이은 온 글의 갈래 수 상한(갈래마다 곱해진다).
_WHOLE_LIMIT = 64

Function = ast.FunctionDef | ast.AsyncFunctionDef

# 자리 글 까닭(설계 규칙 UI-TXT-04 · AMB-02 (가)) — 화면 글 문장 그물 · 알림 꼴 그물의 허용 목록이
# 쓰는 낱말. 값 · 표지 · 빈 결과 · 입력 곁 거부 · 못 그리는 오류는 자리에 남고, 미정리는 다음 판에
# 줄일 기존 자리다(새로 쓰지 않는다 — 그물이 미정리 수를 늘리지 못하게 막는다).
VALUE = "값 — 지금 보고 있는 것(대상 · 건수 · 기준 · 상태)을 말하는 한 줄"
MARKER = "표지 — 조건이 있을 때만 서는 배지 · 아이콘 줄과 그 뜻 한 마디"
EMPTY = (
    "빈 결과 — 목록 · 보기 구획이 비었거나 점검이 끝난 결론 한 줄, 그릴 것이 없어 화면 전체가"
    " 멈추는 빈 상태 포함(AMB-02 (가) — 하는 법 · 길 안내 꼬리 없음, 오류 · 경고 상자 아님)"
)
BESIDE_INPUT = (
    "입력 곁 거부 — 폼 · 팝업 · 확인 칸에서 그 자리 입력과 짝인 거부 · 잠금 까닭 · 고쳐 읽음과,"
    " 누르기 전에 알아야 하는 되돌릴 수 없는 결과(UI-NTF-03 · UI-NTF-09)"
)
CANNOT_DRAW = "못 그리는 오류 — 화면 · 보기 하나를 그리지 못해 그 글로 끝나는 자리(UI-NTF-08)"
UNSETTLED = (
    "미정리 — 설명 · 내역 · 길 안내 · 하는 법 문장이 자리에 남은 기존 자리. 다음 판에 풍선(help=) ·"
    " Guide · 알림으로 옮겨 이 목록을 줄인다"
)
PLACE_REASONS = frozenset({VALUE, MARKER, EMPTY, BESIDE_INPUT, CANNOT_DRAW, UNSETTLED})


def relative(path: Path, root: Path = PROJECT_ROOT) -> str:
    return path.relative_to(root).as_posix()


def screen_files(*, exclude: tuple[str, ...] = ()) -> list[Path]:
    """화면 코드 파일 — `app.py` · `app_pages/` · `src/capa_simulation/`(`exclude` 상대 경로 밖)."""
    files = [PROJECT_ROOT / "app.py"]
    for base in ("app_pages", "src/capa_simulation"):
        files.extend(sorted((PROJECT_ROOT / base).rglob("*.py")))
    return [path for path in files if relative(path) not in exclude]


def calls_by_outer(tree: ast.AST) -> Iterator[tuple[str, Function | None, ast.Call]]:
    """(맨 바깥 함수 이름, 그 함수 노드, 부름) — 문서 차례. 모듈 본문은 ("", None)."""

    def visit(
        node: ast.AST, outer: str, scope: Function | None
    ) -> Iterator[tuple[str, Function | None, ast.Call]]:
        for child in ast.iter_child_nodes(node):
            name, function = outer, scope
            if not outer and isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                name, function = child.name, child
            if isinstance(child, ast.Call):
                yield outer, scope, child
            yield from visit(child, name, function)

    yield from visit(tree, "", None)


def screen_calls(
    paths: Iterable[Path], root: Path = PROJECT_ROOT
) -> Iterator[tuple[str, str, Path, Function | None, ast.Call]]:
    """(상대 경로, 맨 바깥 함수, 파일, 그 함수 노드, 부름) — 파일 차례 · 문서 차례."""
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for outer, scope, call in calls_by_outer(tree):
            yield relative(path, root), outer, path, scope, call


def method(call: ast.Call) -> str:
    """`st.sidebar.caption(…)` → `caption` — 부른 속성 이름(속성 부름이 아니면 "")."""
    return call.func.attr if isinstance(call.func, ast.Attribute) else ""


def called_name(call: ast.Call) -> str:
    """`st.dialog(…)` → `dialog`, `render_settings_box(…)` → `render_settings_box`."""
    if isinstance(call.func, ast.Name):
        return call.func.id
    return method(call)


def receiver(call: ast.Call) -> str:
    """`st.sidebar.caption(` → `sidebar` — 부른 속성 앞 마지막 이름(로거 가르기)."""
    if not isinstance(call.func, ast.Attribute):
        return ""
    return ast.unparse(call.func.value).split(".")[-1]


def first_text_argument(call: ast.Call, keyword: str = "body") -> ast.expr | None:
    """첫 위치 인자, 없으면 `keyword=` 인자."""
    if call.args:
        return call.args[0]
    return next((item.value for item in call.keywords if item.arg == keyword), None)


def _module_file(module: str) -> Path | None:
    if not module.startswith("capa_simulation"):
        return None
    base = SOURCE_ROOT.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


@dataclass
class _Module:
    constants: dict[str, ast.expr] = field(default_factory=dict)
    functions: dict[str, Function] = field(default_factory=dict)
    # 들여온 이름 → (모듈, 그 모듈 안 이름), 들여온 모듈 별명 → 모듈.
    imported: dict[str, tuple[str, str]] = field(default_factory=dict)
    modules: dict[str, str] = field(default_factory=dict)


@cache
def _module(path: Path) -> _Module:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    info = _Module()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                info.constants[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            info.constants[node.target.id] = node.value
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            info.functions[node.name] = node
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                info.imported[alias.asname or alias.name] = (node.module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    info.modules[alias.asname] = alias.name
    return info


def _local_assignments(function: Function, name: str) -> list[ast.expr]:
    found: list[ast.expr] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                found.append(node.value)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign) and node.value is not None:
            if isinstance(node.target, ast.Name) and node.target.id == name:
                found.append(node.value)
    return found


def _is_parameter(function: Function, name: str) -> bool:
    arguments = function.args
    every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    every.extend(item for item in (arguments.vararg, arguments.kwarg) if item is not None)
    return any(item.arg == name for item in every)


class TextResolver:
    """화면 글 인자의 끝 글 · 온 글을 정적으로 짐작한다(모듈 설명)."""

    def tails(self, node: ast.expr, path: Path, scope: Function | None) -> list[str | None]:
        """끝 글(들) — 모르면 None."""
        return self._resolve(node, path, scope, 0, whole=False)

    def wholes(self, node: ast.expr, path: Path, scope: Function | None) -> list[str]:
        """온 글(들) — 모르는 조각은 빈 글."""
        return [text or "" for text in self._resolve(node, path, scope, 0, whole=True)]

    def _resolve(
        self, node: ast.expr, path: Path, scope: Function | None, depth: int, *, whole: bool
    ) -> list[str | None]:
        if depth > _DEPTH:
            return [None]

        def again(value: ast.expr) -> list[str | None]:
            return self._resolve(value, path, scope, depth, whole=whole)

        if isinstance(node, ast.Constant):
            return [node.value] if isinstance(node.value, str) else [None]
        if isinstance(node, ast.JoinedStr):
            if whole:
                return ["".join(_literal_parts(node))]
            if not node.values:
                return [""]
            last = node.values[-1]
            if isinstance(last, ast.Constant):
                return [str(last.value)]
            if isinstance(last, ast.FormattedValue) and last.format_spec is None:
                return again(last.value)
            return [None]
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Add):
                if not whole:
                    return again(node.right)
                joined: list[str | None] = [
                    (left or "") + (right or "")
                    for left in again(node.left)
                    for right in again(node.right)
                ]
                return joined[:_WHOLE_LIMIT]
            if isinstance(node.op, ast.Mod):
                return again(node.left)
            return [None]
        if isinstance(node, ast.IfExp):
            return [*again(node.body), *again(node.orelse)]
        if isinstance(node, ast.BoolOp):
            return [text for value in node.values for text in again(value)]
        if isinstance(node, ast.Name):
            return self._name(node.id, path, scope, depth, whole=whole)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            module = _module(path).modules.get(node.value.id)
            target = _module_file(module) if module else None
            if target is not None and node.attr in _module(target).constants:
                value = _module(target).constants[node.attr]
                return self._resolve(value, target, None, depth + 1, whole=whole)
            return [None]
        if isinstance(node, ast.Call):
            return self._call(node, path, scope, depth, whole=whole)
        return [None]

    def _name(
        self, name: str, path: Path, scope: Function | None, depth: int, *, whole: bool
    ) -> list[str | None]:
        if scope is not None:
            if _is_parameter(scope, name):
                return [None]
            local = _local_assignments(scope, name)
            if local:
                return [
                    text
                    for value in local
                    for text in self._resolve(value, path, scope, depth, whole=whole)
                ]
        info = _module(path)
        if name in info.constants:
            return self._resolve(info.constants[name], path, None, depth + 1, whole=whole)
        if name in info.imported:
            module, original = info.imported[name]
            target = _module_file(module)
            if target is not None and original in _module(target).constants:
                value = _module(target).constants[original]
                return self._resolve(value, target, None, depth + 1, whole=whole)
        return [None]

    def _call(
        self, node: ast.Call, path: Path, scope: Function | None, depth: int, *, whole: bool
    ) -> list[str | None]:
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr == "format":
                return self._resolve(func.value, path, scope, depth, whole=whole)
            if func.attr == "join" and node.args and isinstance(node.args[0], ast.List | ast.Tuple):
                items = node.args[0].elts
                if not items:
                    return [""]
                return self._resolve(items[-1], path, scope, depth, whole=whole)
            return [None]
        if not isinstance(func, ast.Name):
            return [None]
        if func.id in PASS_THROUGH:
            argument = first_text_argument(node, "text")
            if argument is None:
                return [None]
            return self._resolve(argument, path, scope, depth, whole=whole)
        info = _module(path)
        target, function = path, info.functions.get(func.id)
        if function is None and func.id in info.imported:
            module, original = info.imported[func.id]
            found = _module_file(module)
            if found is not None:
                target, function = found, _module(found).functions.get(original)
        if function is None:
            return [None]
        returns = [
            item.value
            for item in ast.walk(function)
            if isinstance(item, ast.Return) and item.value is not None
        ]
        return [
            text
            for value in returns
            for text in self._resolve(value, target, function, depth + 1, whole=whole)
        ] or [None]


def _literal_parts(node: ast.JoinedStr) -> list[str]:
    return [str(part.value) for part in node.values if isinstance(part, ast.Constant)]


# 끝에 붙은 꾸밈 — 공백 · HTML 꼬리표 · 마크다운 강조 · 닫는 괄호 · 따옴표는 걷고 본다.
_TRAILING = re.compile(r"(?:\s+|<[^<>]*>|[*_`)\]」』\"'”’]+)$")
# 서술형 끝 — 「…니다」 · 「…세요」 · 「…십시오」 · 「…니까」 · 해요체 「…요」 · 평서형 「…다」.
_SENTENCE_END = re.compile(
    r"(?:니다|세요|십시오|니까|[어아해여]요|예요|이에요|네요|군요|죠|[가-힣]다)[.!?…]*$"
)


def bare_tail(text: str) -> str:
    """끝 꾸밈(공백 · HTML 꼬리표 · 강조 · 닫는 괄호 · 따옴표)을 걷은 글."""
    previous = None
    while previous != text:
        previous, text = text, _TRAILING.sub("", text)
    return text


def ends_as_sentence(text: str) -> bool:
    """글이 서술형 문장으로 끝나는가(끝 꾸밈을 걷고 본다)."""
    return bool(_SENTENCE_END.search(bare_tail(text)))
