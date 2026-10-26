# Purpose: CSV 내보내기 버튼·표 제목 줄·표 도구 막대 앞 띄움이 한 곳에서만 만들어지는지 지킨다.

"""내보내기 버튼 표기가 갈라지지 않게 막는다.

예전에는 13곳이 각자 `st.download_button` 을 불렀고 표기가 두 갈래였다. 라벨에
`:material/download:` 를 적은 것과 `icon=` 인자를 쓴 것이라 아이콘 간격이 달랐고,
`mime` 도 `text/csv` 와 `text/csv;charset=utf-8` 이 섞여 있었으며, 일부는
`on_click="ignore"` 가 빠져 내려받을 때마다 페이지가 통째로 다시 계산됐다.
"""

import ast
import functools
import re
from pathlib import Path

from capa_simulation.components.table_toolbar import (
    CSV_MIME,
    DOWNLOAD_ICON,
    TABLE_TOOLBAR_CLEARANCE,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OWNER = PROJECT_ROOT / "src/capa_simulation/components/table_toolbar.py"


def _sources() -> list[Path]:
    return [
        path
        for path in [
            *(PROJECT_ROOT / "app_pages").glob("*.py"),
            *(PROJECT_ROOT / "src/capa_simulation").rglob("*.py"),
        ]
        if path != OWNER
    ]


def test_download_button_is_created_in_one_place() -> None:
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in _sources()
        if "st.download_button(" in path.read_text(encoding="utf-8")
    ]

    assert not offenders, f"table_toolbar.render_csv_download 를 쓰세요: {offenders}"


def test_download_icon_is_not_inlined_in_labels() -> None:
    """라벨 문자열에 아이콘을 섞으면 `icon=` 을 쓴 버튼과 간격이 달라진다."""
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in _sources()
        if f"{DOWNLOAD_ICON} " in path.read_text(encoding="utf-8")
    ]

    assert not offenders, f"라벨 대신 render_csv_download 의 label 을 쓰세요: {offenders}"


def test_csv_mime_declares_the_charset() -> None:
    """내보내는 바이트는 전부 `utf-8-sig` 다. charset 을 빼면 Excel 밖에서 한글이 깨진다."""
    assert CSV_MIME == "text/csv;charset=utf-8"


BUTTON_LABEL_ICON = re.compile(
    r"st\.(?:button|form_submit_button)\(\s*\"?:material/",
    re.MULTILINE,
)


def test_button_icons_use_the_icon_argument() -> None:
    """버튼 라벨에 아이콘을 섞으면 `icon=` 을 쓴 버튼과 간격·크기가 달라진다.

    라벨에 넣은 것은 본문 글자와 같은 흐름으로 그려지고, `icon=` 은 별도 아이콘 자리에
    놓인다. 두 표기가 섞여 있어 같은 화면의 버튼끼리 아이콘 위치가 어긋났다.
    `st.tabs` 처럼 `icon=` 이 없는 위젯은 라벨에 넣는 수밖에 없으므로 검사하지 않는다.
    """
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in [*_sources(), OWNER]
        if BUTTON_LABEL_ICON.search(path.read_text(encoding="utf-8"))
    ]

    assert not offenders, f"라벨 대신 st.button(icon=...) 을 쓰세요: {offenders}"


# 표 바로 위 형제가 품으면 도구 막대가 덮을 수 있는 것 — 입력·단추·팝오버·토글·날짜 칸(오른쪽 끝의
# 지우기 ✕ 와 펼침 화살표 포함).
PRESSABLE = frozenset(
    {
        "button",
        "checkbox",
        "date_input",
        "download_button",
        "form_submit_button",
        "multiselect",
        "number_input",
        "pills",
        "popover",
        "radio",
        "render_csv_download",
        "segmented_control",
        "selectbox",
        "text_area",
        "text_input",
        "time_input",
        "toggle",
    }
)
TABLES = frozenset({"dataframe", "data_editor"})
# 위 형제가 누를 것을 품어도 띄움 없이 두는 표 (파일, 함수) → 까닭.
CLEARANCE_ALLOWED: dict[tuple[str, str], str] = {
    ("src/capa_simulation/components/availability_gap_panel.py", "_render_unit_list"): (
        "위 형제 `with controls:` 는 다른 자리(조건 카드)에 그려 둔 칸이다 — 표 바로 위 줄이 아니다"
    ),
}

# 펼침 블록의 첫 표인데 띄움이 없는 다른 영역 자리 (파일, 함수) → 까닭. 그물을 펼침 머리까지 넓힌 날
# (2026-10-27 E2E 6회차 Space)에 이미 있던 자리다 — 같은 결함(머리 오른쪽 끝을 막대가 덮어 접기
# 누름이 내려받기에 먹힘)이지만 그 영역의 고침에서 띄움을 두고 여기서 지운다(docs/TODO.md). 새
# 자리는 받지 않는다.
EXPANDER_CLEARANCE_PENDING: dict[tuple[str, str], str] = {
    (path, function): "펼침 첫 표 — 그 영역 고침 대기(2026-10-27 그물 넓힘)"
    for path, function in (
        ("app_pages/standard_target_capa.py", "_render_standard_target_exceptions"),
        ("app_pages/load_conversion.py", "_render_locked_yield_rows"),
        ("app_pages/load_conversion.py", ""),
        ("src/capa_simulation/components/equipment_data_workspace.py", "_render_history"),
        ("src/capa_simulation/components/scenario_year_shift.py", "_render_shift"),
        ("src/capa_simulation/components/process_rename_management.py", "_render_direct_editor"),
        ("src/capa_simulation/components/scenario_transform.py", "render_derived_save"),
        ("src/capa_simulation/components/auto_official_update_tab.py", "_render_run_history"),
        ("src/capa_simulation/components/past_data_management.py", "_render_table_editor"),
        ("src/capa_simulation/components/scenario_month_merge.py", "_render_merge"),
    )
}


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Call):
            if isinstance(item.func, ast.Attribute):
                names.add(item.func.attr)
            elif isinstance(item.func, ast.Name):
                names.add(item.func.id)
    return names


def _draws(node: ast.AST) -> bool:
    """`st.…` 를 부르는가 — 부르지 않는 대입은 화면에서 표와 위 형제 사이에 서지 않는다."""
    return any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Attribute)
        and isinstance(item.func.value, ast.Name)
        and item.func.value.id == "st"
        for item in ast.walk(node)
    )


def _is_table(stmt: ast.stmt) -> bool:
    value = stmt.value if isinstance(stmt, (ast.Expr, ast.Assign, ast.AnnAssign)) else None
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr in TABLES
    )


def _is_clearance(stmt: ast.stmt) -> bool:
    if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
        return False
    call = stmt.value
    called = ast.unparse(call.func)
    if called.endswith("toolbar_clearance"):
        return True
    return called == "st.space" and any(
        "TOOLBAR_CLEARANCE" in ast.unparse(arg) for arg in call.args
    )


SOURCE_ROOT = PROJECT_ROOT / "src"
_Function = ast.FunctionDef | ast.AsyncFunctionDef


@functools.cache
def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


@functools.cache
def _definitions(path: Path) -> dict[str, list[_Function]]:
    """파일 안의 함수 정의(이름 → 정의들) — 안쪽 함수까지."""
    found: dict[str, list[_Function]] = {}
    for node in ast.walk(_tree(path)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.setdefault(node.name, []).append(node)
    return found


def _module_path(module: str) -> Path | None:
    base = SOURCE_ROOT.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.exists():
            return candidate
    return None


@functools.cache
def _imported(path: Path) -> dict[str, tuple[Path, str]]:
    """`from capa_simulation… import 이름` 으로 들여온 이름 → (정의한 파일, 원래 이름)."""
    found: dict[str, tuple[Path, str]] = {}
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("capa_simulation"):
            source = _module_path(str(node.module))
            if source is not None:
                for alias in node.names:
                    found[alias.asname or alias.name] = (source, alias.name)
    return found


def _bare_calls(node: ast.AST) -> set[str]:
    """`이름(…)` 꼴로 부르는 이름 — 도우미 함수를 따라갈 후보다(`x.이름(…)` 은 따라가지 않는다)."""
    return {
        item.func.id
        for item in ast.walk(node)
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Name)
    }


def _is_dialog(function: _Function) -> bool:
    """`@st.dialog` 함수는 대화상자 안에 그린다 — 표 위 줄에 서지 않는다."""
    return any(
        ast.unparse(decorator).startswith("st.dialog") for decorator in function.decorator_list
    )


def _reach(path: Path, stmt: ast.stmt) -> tuple[set[str], bool]:
    """문장이 부르는 이름과 `st.…` 를 부르는지 — 같은 파일의 도우미 함수와 `capa_simulation` 에서
    들여온 도우미 함수 안까지 따라간다(2026-10-26 E2E — 보드 표 위 줄 `_render_controls()` 가 품은
    숫자 칸을 그물이 못 봤다)."""
    names = _called_names(stmt)
    draws = _draws(stmt)
    pending = [(path, name) for name in _bare_calls(stmt)]
    seen: set[tuple[Path, str]] = set()
    while pending:
        where, name = pending.pop()
        if (where, name) in seen:
            continue
        seen.add((where, name))
        local = _definitions(where).get(name)
        if local is None:
            target = _imported(where).get(name)
            if target is not None:
                pending.append(target)
            continue
        for function in local:
            if _is_dialog(function):
                continue
            for inner in function.body:
                names |= _called_names(inner)
                draws = draws or _draws(inner)
                pending.extend((where, called) for called in _bare_calls(inner))
    return names, draws


def _opens_expander(node: ast.AST) -> bool:
    """`with st.expander(…):` 블록인가 — 펼침 머리(누르면 접힌다)가 블록 첫 표 바로 위 줄이다."""
    return isinstance(node, ast.With) and any(
        isinstance(item.context_expr, ast.Call)
        and isinstance(item.context_expr.func, ast.Attribute)
        and item.context_expr.func.attr == "expander"
        for item in node.items
    )


def _tables_after_pressables() -> tuple[list[tuple[str, str, int]], int]:
    """(위 형제가 누를 것을 품는데 띄움이 없는 표 (파일, 함수, 줄)), 띄움을 둔 표의 수.

    위 형제는 그리지 않는 대입을 건너뛴 바로 앞 문장이고, 표가 `if` 의 첫 문장이면 그 `if` 앞
    문장이다. 형제가 부르는 도우미 함수 안까지 본다(`_reach`). 표가 `with st.expander(…):` 의 첫
    문장이면 위 줄은 펼침 머리다 — 머리 오른쪽 끝(펼침 화살표 자리)을 막대가 덮어 접기 누름이
    「Download as CSV」 에 먹혔다(2026-10-27 E2E — Space 「바뀐 호기 n건」).
    """
    missing: list[tuple[str, str, int]] = []
    cleared = 0
    for path in [*_sources(), OWNER]:
        tree = _tree(path)
        owners: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for inner in ast.walk(node):
                    owners.setdefault(id(inner), node.name)
        # 문장 → (그 문장을 품은 노드, 그 노드의 문장 목록, 목록 안 자리).
        places: dict[int, tuple[ast.AST, list[ast.stmt], int]] = {}
        for node in ast.walk(tree):
            for field in ("body", "orelse", "finalbody"):
                body = getattr(node, field, None)
                if isinstance(body, list):
                    for index, stmt in enumerate(body):
                        if isinstance(stmt, ast.stmt):
                            places[id(stmt)] = (node, body, index)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.stmt) and _is_table(node)):
                continue
            previous = _previous_sibling(path, node, places)
            if previous is None:
                if _first_in_expander(path, node, places):
                    missing.append(
                        (
                            path.relative_to(PROJECT_ROOT).as_posix(),
                            owners.get(id(node), ""),
                            node.lineno,
                        )
                    )
                continue
            if _is_clearance(previous):
                cleared += 1
            elif _reach(path, previous)[0] & PRESSABLE:
                missing.append(
                    (
                        path.relative_to(PROJECT_ROOT).as_posix(),
                        owners.get(id(node), ""),
                        node.lineno,
                    )
                )
    return missing, cleared


def _previous_sibling(
    path: Path,
    stmt: ast.stmt,
    places: dict[int, tuple[ast.AST, list[ast.stmt], int]],
) -> ast.stmt | None:
    """화면에서 표 바로 위에 서는 문장 — 그리지 않는 대입은 건너뛰고, `if` 의 첫 문장이면 그 앞."""
    current: ast.stmt = stmt
    while id(current) in places:
        owner, body, index = places[id(current)]
        before = index - 1
        while (
            before >= 0
            and isinstance(body[before], (ast.Assign, ast.AnnAssign, ast.AugAssign))
            and not _reach(path, body[before])[1]
        ):
            before -= 1
        if before >= 0:
            return body[before]
        if not isinstance(owner, ast.If):
            return None
        current = owner
    return None


def _first_in_expander(
    path: Path,
    stmt: ast.stmt,
    places: dict[int, tuple[ast.AST, list[ast.stmt], int]],
) -> bool:
    """표 앞에 그리는 형제가 없고 그 블록(`if` 를 지나 올라간)이 `with st.expander(…):` 인가."""
    current: ast.stmt = stmt
    while id(current) in places:
        owner, body, index = places[id(current)]
        if any(_reach(path, earlier)[1] for earlier in body[:index]):
            return False
        if _opens_expander(owner):
            return True
        if not isinstance(owner, ast.If):
            return False
        current = owner
    return False


def test_a_table_under_a_pressable_row_keeps_the_toolbar_clearance() -> None:
    """표 도구 막대(열 보기·내려받기·찾기·전체 화면)는 표 머리 위 37px 까지 솟는다(AGENTS 9장).

    표 바로 위 형제가 입력·단추·팝오버·토글·날짜 칸을 품거나 표가 펼침 블록의 첫 요소면(머리가 바로
    위 줄) 그 사이에 `toolbar_clearance()` 를
    둔다 — 없으면 막대가 위 줄 오른쪽 끝의 단추·지우기(✕)를 덮어 표에서 그리로 옮긴 누름을
    가로챈다(2026-10-25·26 E2E — 설비 시나리오 리비전 표·Qual 마감 계산기 월 편집표·Space).
    """
    missing, cleared = _tables_after_pressables()
    offenders = [
        f"{path}:{line} ({function})"
        for path, function, line in missing
        if (path, function) not in CLEARANCE_ALLOWED
        and (path, function) not in EXPANDER_CLEARANCE_PENDING
    ]

    assert not offenders, (
        "표 바로 위 형제에 누를 것이 있습니다 — 표 앞에 `table_toolbar.toolbar_clearance()` 를 "
        "두세요(띄움이 필요 없으면 CLEARANCE_ALLOWED 에 까닭과 함께):\n" + "\n".join(offenders)
    )
    # 그물이 표를 보고 있는지 — 띄움을 둔 표가 하나도 안 잡히면 탐색이 망가진 것이다.
    assert cleared >= 6


def test_every_allowed_table_still_needs_its_exception() -> None:
    missing, _ = _tables_after_pressables()
    listed = {*CLEARANCE_ALLOWED, *EXPANDER_CLEARANCE_PENDING}
    stale = sorted(listed - {(path, function) for path, function, _ in missing})

    assert not stale, f"사라진 자리입니다 — CLEARANCE_ALLOWED 에서 지우세요: {stale}"


CLEARANCE_DEFINITION = re.compile(r"^\s*([A-Z_]*TOOLBAR_CLEARANCE[A-Z_]*)\s*(?::[^=]+)?=\s*(.+)$")


def test_the_toolbar_clearance_number_lives_in_table_toolbar_only() -> None:
    """띄움 숫자가 셋으로 갈라졌었다(공용 값·설비 시나리오 리비전 표·Qual 계산기 별칭). 다른 이름은
    공용 값을 가리키는 별칭이어야 한 곳을 고치면 모든 표가 따라간다."""
    numbers: list[str] = []
    for path in [*_sources(), OWNER]:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            matched = CLEARANCE_DEFINITION.match(line)
            if matched and re.fullmatch(r"[\d.]+", matched.group(2).strip()):
                numbers.append(f"{path.relative_to(PROJECT_ROOT).as_posix()}:{line_no}")

    assert numbers == ["src/capa_simulation/components/table_toolbar.py:" + _owner_line()]
    assert TABLE_TOOLBAR_CLEARANCE >= 20


def _owner_line() -> str:
    for line_no, line in enumerate(OWNER.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("TABLE_TOOLBAR_CLEARANCE ="):
            return str(line_no)
    raise AssertionError("table_toolbar.py 에 TABLE_TOOLBAR_CLEARANCE 정의가 없다")
