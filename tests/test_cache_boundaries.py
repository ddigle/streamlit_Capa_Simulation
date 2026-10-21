# Purpose: Streamlit 캐시를 경계 모듈에만 두고 큰 표를 해시 인자로 받지 않는지 소스로 지킨다.

"""캐시 경계 계약(AGENTS.md 5장 3·4)의 정적 검사.

- 5장 4: `@st.cache_data`·`@st.cache_resource` 는 경계 모듈 다섯에만 둔다. 경계 밖
  캐시는 쓰기 세대·`clear_*_cache()` 장치에서 빠져 저장 뒤에도 옛 값을 낼 수 있다.
- 5장 3: 큰 DataFrame 을 해시 인자로 넘기지 않는다. Streamlit 1.63 은 5만 행 넘는
  DataFrame·Series 를 1만 행 표본으로만 해시해(`runtime/caching/hashing.py`), 표본 밖
  한 칸만 고친 편집이 옛 결과에 적중한다. 행 수는 소스로 알 수 없으므로, 해시되는 프레임
  인자를 허용 목록과 맞대어 새 인자가 생기면 멈추게 한다.

주석 글은 AST 에 없으므로 규칙을 설명하는 docstring·주석은 걸리지 않는다. 인자 주석의
이름은 형 별칭과 클래스 필드(`PreparedDisplayOrder.rules` 같은)까지 풀어 보며,
`capa_simulation` 안에서 import 한 이름도 따라간다.
"""

import ast
import functools
import warnings
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCANNED_ROOTS = ("app.py", "app_pages", "src", "scripts")
PACKAGE = "capa_simulation"

SIMULATION_CACHE = "src/capa_simulation/services/simulation_cache.py"
CACHE_BOUNDARY_MODULES = frozenset(
    {
        SIMULATION_CACHE,
        "src/capa_simulation/persistence/cache.py",
        "src/capa_simulation/persistence/equipment_cache.py",
        "src/capa_simulation/components/display_order_management.py",
        "src/capa_simulation/components/process_rename_management.py",
    }
)
CACHE_NAMES = frozenset({"cache_data", "cache_resource"})
# 해시가 표본으로 줄어드는 형(DataFrame·Series 5만 행, ndarray 50만 칸 이상)과, 무엇이 올지 주석이
# 말해 주지 않는 형. 주석이 없는 인자도 같게 본다.
SAMPLED_OR_OPAQUE_TYPES = frozenset({"DataFrame", "Series", "ndarray", "Any", "object"})
MISSING_ANNOTATION = "Any"

BOUNDARY_RULE = (
    "AGENTS.md 5장 4 — Streamlit 캐시는 경계 모듈에만 둡니다. 경계를 늘리려면 AGENTS 목록과 "
    "이 시험의 CACHE_BOUNDARY_MODULES 를 함께 고칩니다."
)
HASHED_FRAME_RULE = (
    "AGENTS.md 5장 3 — 큰 DataFrame 은 `_` 인자로 넘기고 키에는 content_token·frame_digest 를 "
    "싣습니다. 작은 표임을 확인했다면 이 시험의 HASHED_FRAME_ARGUMENTS 에 까닭과 함께 더합니다."
)

# (모듈, 함수, 인자) — 내용째 해시해도 되는 작은 표. 사내 행 수 확인은 docs/TODO.md 2장
# 「화면 조작마다 도는 계산·로딩 줄이기 후속」 의 하지 않은 것 ⑧.
HASHED_FRAME_ARGUMENTS = frozenset(
    {
        # 분류 한 컬럼의 고유값 표(필터 선택지) — 행 수가 공정·분류값 수다.
        (SIMULATION_CACHE, "get_display_ordered_values", "values"),
        # 부하 환산 화면의 월 계획과 그 기준 표(수율·칩 수량·칩 등가·표시순서).
        # 소요대수·REQB 같은 큰 표가 아니다.
        (SIMULATION_CACHE, "get_monthly_volume", "plan"),
        (SIMULATION_CACHE, "get_monthly_volume", "yield_data"),
        (SIMULATION_CACHE, "get_monthly_volume", "chip_qty"),
        (SIMULATION_CACHE, "get_monthly_volume", "density_data"),
        (SIMULATION_CACHE, "get_monthly_volume", "display_order"),
        # HOME 생산 대시보드 — 위와 같은 월 계획·칩 등가·표시순서.
        (SIMULATION_CACHE, "get_production_dashboard", "plan"),
        (SIMULATION_CACHE, "get_production_dashboard", "density_data"),
        (SIMULATION_CACHE, "get_production_dashboard", "display_order"),
        # 가용설비 주차 집계 — 리비전·필터를 거친 기존 보유대수·설비 마스터·비가동(호기 수 규모).
        (SIMULATION_CACHE, "get_weekly_equipment_availability", "baseline"),
        (SIMULATION_CACHE, "get_weekly_equipment_availability", "equipment"),
        (SIMULATION_CACHE, "get_weekly_equipment_availability", "downtime"),
        # 설비 마스터 한 벌(호기 수 규모).
        (SIMULATION_CACHE, "get_undated_equipment", "equipment"),
        (SIMULATION_CACHE, "get_usage_excluded_equipment", "equipment"),
    }
)

Location = tuple[str, int, str]
HashedArgument = tuple[str, str, str]


@dataclass(frozen=True)
class ModuleTypes:
    """한 모듈의 형 정의(별칭 값·클래스 필드 주석)와 패키지 안 import.

    `imports` 는 지역 이름 → (모듈, 원래 이름) 이다.
    """

    definitions: dict[str, list[ast.expr]]
    imports: dict[str, tuple[str, str]]


# 모듈 이름 → 그 모듈의 형 정의(패키지 밖이거나 없으면 None).
TypeLookup = Callable[[str], ModuleTypes | None]


@functools.cache
def _source_paths() -> tuple[str, ...]:
    paths: list[str] = []
    for name in SCANNED_ROOTS:
        root = PROJECT_ROOT / name
        for path in [root] if root.is_file() else sorted(root.rglob("*.py")):
            paths.append(path.relative_to(PROJECT_ROOT).as_posix())
    return tuple(paths)


@functools.cache
def _tree(relative: str) -> ast.Module:
    # docstring 의 Windows 경로(`.\.venv`) 같은 escape 경고는 이 검사의 몫이 아니다.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        warnings.simplefilter("ignore", SyntaxWarning)
        source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        return ast.parse(source, filename=relative)


def _module_name(relative: str) -> str:
    parts = relative.removeprefix("src/").removesuffix(".py").split("/")
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


@functools.cache
def _project_module_types(module: str) -> ModuleTypes | None:
    """`capa_simulation` 모듈의 형 정의 — 해시 인자 주석이 닿는 모듈만 그때 읽는다."""
    if module != PACKAGE and not module.startswith(f"{PACKAGE}."):
        return None
    base = PROJECT_ROOT / "src" / module.replace(".", "/")
    for path in (base.with_suffix(".py"), base / "__init__.py"):
        if path.is_file():
            return _module_types(_tree(path.relative_to(PROJECT_ROOT).as_posix()))
    return None


def _module_types(tree: ast.Module) -> ModuleTypes:
    definitions: dict[str, list[ast.expr]] = {}
    imports: dict[str, tuple[str, str]] = {}
    # `if TYPE_CHECKING:` 아래 import 도 모듈 머리로 본다.
    statements = [
        *tree.body,
        *(item for node in tree.body if isinstance(node, ast.If) for item in node.body),
    ]
    for node in statements:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                definitions[target.id] = [node.value]
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
            and ast.unparse(node.annotation).endswith("TypeAlias")
        ):
            definitions[node.target.id] = [node.value]
        elif isinstance(node, ast.ClassDef):
            definitions[node.name] = [
                item.annotation for item in node.body if isinstance(item, ast.AnnAssign)
            ]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                imports[alias.asname or alias.name] = (node.module, alias.name)
    return ModuleTypes(definitions, imports)


def _clear_receivers(tree: ast.AST) -> set[int]:
    """`st.cache_data.clear()` 처럼 캐시를 비우기만 하는 자리의 노드 id."""
    return {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "clear"
    }


def _cache_references(tree: ast.AST) -> Iterator[ast.AST]:
    """캐시 이름(`st.cache_data`·`from streamlit import cache_resource`)을 낸다.

    `st.cache_data.clear()` 처럼 비우기만 하는 자리는 뺀다.
    """
    skipped = _clear_receivers(tree)
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.Attribute) and node.attr in CACHE_NAMES:
            yield node
        elif isinstance(node, ast.Name) and node.id in CACHE_NAMES:
            yield node
        elif isinstance(node, ast.ImportFrom) and any(
            alias.name in CACHE_NAMES for alias in node.names
        ):
            yield node


def _cached_functions(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and any(
            any(True for _ in _cache_references(decorator)) for decorator in node.decorator_list
        ):
            yield node


def _non_decorator_cache_references(tree: ast.AST) -> list[int]:
    """데코레이터가 아닌 꼴(`st.cache_data(fn)`·별칭)로 캐시를 거는 자리의 줄."""
    decorated = {
        id(reference)
        for function in _cached_functions(tree)
        for decorator in function.decorator_list
        for reference in _cache_references(decorator)
    }
    return sorted(
        getattr(node, "lineno", 0) for node in _cache_references(tree) if id(node) not in decorated
    )


def _annotation_type_names(
    annotation: ast.expr | None,
    module: str,
    lookup: TypeLookup,
    seen: frozenset[tuple[str, str]] = frozenset(),
) -> set[str]:
    """주석이 닿는 형 이름 — 같은 모듈·패키지 안 import 의 별칭과 클래스 필드까지 푼다."""
    if annotation is None:
        return {MISSING_ANNOTATION}
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        annotation = ast.parse(annotation.value, mode="eval").body
    names: set[str] = set()
    for node in ast.walk(annotation):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
            owner, name = module, node.id
            types = lookup(owner)
            followed: set[tuple[str, str]] = set()
            while (
                types is not None
                and name not in types.definitions
                and name in types.imports
                and (owner, name) not in followed
            ):
                followed.add((owner, name))
                owner, name = types.imports[name]
                types = lookup(owner)
            if types is None or name not in types.definitions or (owner, name) in seen:
                continue
            for expanded in types.definitions[name]:
                names |= _annotation_type_names(expanded, owner, lookup, seen | {(owner, name)})
    return names


def _hashed_frame_arguments(
    relative: str, tree: ast.Module, lookup: TypeLookup
) -> set[HashedArgument]:
    """캐시 함수의 해시되는(`_` 로 시작하지 않는) 인자 가운데 표본 해시·불투명 형인 것."""
    module = _module_name(relative)
    found: set[HashedArgument] = set()
    for function in _cached_functions(tree):
        arguments = function.args
        candidates = [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            *(item for item in (arguments.vararg, arguments.kwarg) if item is not None),
        ]
        for argument in candidates:
            if argument.arg.startswith("_"):
                continue
            names = _annotation_type_names(argument.annotation, module, lookup)
            if names & SAMPLED_OR_OPAQUE_TYPES:
                found.add((relative, function.name, argument.arg))
    return found


def test_streamlit_cache_lives_only_in_boundary_modules() -> None:
    sources = _source_paths()
    assert CACHE_BOUNDARY_MODULES <= set(sources), BOUNDARY_RULE

    outside: list[Location] = []
    for relative in sources:
        if relative in CACHE_BOUNDARY_MODULES:
            continue
        # 이름이 글자로도 없으면 AST 에도 없다 — 파싱은 글자가 있는 파일만 한다.
        text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        if not any(name in text for name in CACHE_NAMES):
            continue
        outside.extend(
            (relative, getattr(node, "lineno", 0), ast.unparse(node))
            for node in _cache_references(_tree(relative))
        )
    assert not outside, f"{BOUNDARY_RULE} 경계 밖: {sorted(outside)}"

    # 목록의 모듈이 캐시를 더는 두지 않으면 AGENTS 목록이 낡은 것이다.
    empty = sorted(
        relative
        for relative in CACHE_BOUNDARY_MODULES
        if not any(True for _ in _cached_functions(_tree(relative)))
    )
    assert not empty, f"{BOUNDARY_RULE} 캐시가 없는 경계 모듈: {empty}"


def test_boundary_modules_attach_caches_only_as_decorators() -> None:
    """부름 꼴(`st.cache_data(fn)`)로 건 캐시는 아래 해시 인자 검사가 인자를 보지 못한다."""
    calls = {
        relative: lines
        for relative in sorted(CACHE_BOUNDARY_MODULES)
        if (lines := _non_decorator_cache_references(_tree(relative)))
    }
    assert not calls, f"캐시는 데코레이터로만 겁니다(해시 인자 검사가 보도록): {calls}"


def test_only_known_small_frames_are_hashed_cache_arguments() -> None:
    found: set[HashedArgument] = set()
    for relative in CACHE_BOUNDARY_MODULES:
        found |= _hashed_frame_arguments(relative, _tree(relative), _project_module_types)

    assert found == HASHED_FRAME_ARGUMENTS, (
        f"{HASHED_FRAME_RULE} 새로 생김: {sorted(found - HASHED_FRAME_ARGUMENTS)}, "
        f"사라짐: {sorted(HASHED_FRAME_ARGUMENTS - found)}"
    )


# ------------------------------------------------------- 검사기 자체


PLANTED_TYPES = """
import pandas as pd


class Prepared:
    rules: pd.DataFrame


Choice = str
"""

PLANTED_MODULE = """
from typing import NamedTuple
import pandas as pd
import streamlit as st
from capa_simulation.planted_types import Choice, Prepared as Rules

Frames = dict[str, pd.DataFrame]


class FrameKey(NamedTuple):
    token: str
    frame: pd.DataFrame


@st.cache_data(show_spinner=False)
def plain(requirements: pd.DataFrame, _detail: pd.DataFrame, token: str) -> int:
    return 0


@st.cache_resource
def aliased(tables: Frames, *, key: FrameKey, months: tuple[int, ...]) -> int:
    return 0


@st.cache_data
def imported(rules: Rules, choice: Choice, _rules: Rules) -> int:
    return 0


@st.cache_data
def untyped(value, _hidden, note: "pd.Series") -> int:
    return 0


def not_cached(requirements: pd.DataFrame) -> int:
    return 0
"""


def test_scanners_find_planted_hashed_frames_through_aliases_imports_and_fields() -> None:
    relative = "src/capa_simulation/planted.py"
    tree = ast.parse(PLANTED_MODULE)
    modules = {
        "capa_simulation.planted": _module_types(tree),
        "capa_simulation.planted_types": _module_types(ast.parse(PLANTED_TYPES)),
    }

    assert _hashed_frame_arguments(relative, tree, modules.get) == {
        (relative, "plain", "requirements"),
        (relative, "aliased", "tables"),
        (relative, "aliased", "key"),
        (relative, "imported", "rules"),
        (relative, "untyped", "value"),
        (relative, "untyped", "note"),
    }
    assert _non_decorator_cache_references(tree) == []


def test_scanners_find_cache_calls_and_imports_but_not_clears() -> None:
    decorated = ast.parse("import streamlit as st\n@st.cache_data\ndef f() -> int:\n    return 0\n")
    imported = ast.parse("from streamlit import cache_resource\n")
    wrapped = ast.parse("import streamlit as st\ng = st.cache_data(show_spinner=False)(len)\n")
    cleared = ast.parse(
        "import streamlit as st\nst.cache_data.clear()\nst.cache_resource.clear()\n"
    )

    assert [ast.unparse(node) for node in _cache_references(decorated)] == ["st.cache_data"]
    assert len(list(_cache_references(imported))) == 1
    assert _non_decorator_cache_references(wrapped) == [2]
    assert list(_cache_references(cleared)) == []
