# Purpose: CSV 내보내기 버튼·표 제목 줄·표 도구 막대 앞 띄움이 한 곳에서만 만들어지는지 지킨다.

"""내보내기 버튼 표기가 갈라지지 않게 막는다.

예전에는 13곳이 각자 `st.download_button` 을 불렀고 표기가 두 갈래였다. 라벨에
`:material/download:` 를 적은 것과 `icon=` 인자를 쓴 것이라 아이콘 간격이 달랐고,
`mime` 도 `text/csv` 와 `text/csv;charset=utf-8` 이 섞여 있었으며, 일부는
`on_click="ignore"` 가 빠져 내려받을 때마다 페이지가 통째로 다시 계산됐다.
"""

import ast
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


def _tables_after_pressables() -> tuple[list[tuple[str, str, int]], int]:
    """(위 형제가 누를 것을 품는데 띄움이 없는 표 (파일, 함수, 줄)), 띄움을 둔 표의 수."""
    missing: list[tuple[str, str, int]] = []
    cleared = 0
    for path in [*_sources(), OWNER]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        owners: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for inner in ast.walk(node):
                    owners.setdefault(id(inner), node.name)
        for node in ast.walk(tree):
            for field in ("body", "orelse", "finalbody"):
                body = getattr(node, field, None)
                if not isinstance(body, list):
                    continue
                for index, stmt in enumerate(body):
                    if not (isinstance(stmt, ast.stmt) and _is_table(stmt)):
                        continue
                    before = index - 1
                    while (
                        before >= 0
                        and isinstance(body[before], (ast.Assign, ast.AnnAssign, ast.AugAssign))
                        and not _draws(body[before])
                    ):
                        before -= 1
                    if before < 0:
                        continue
                    previous = body[before]
                    if _is_clearance(previous):
                        cleared += 1
                    elif _called_names(previous) & PRESSABLE:
                        missing.append(
                            (
                                path.relative_to(PROJECT_ROOT).as_posix(),
                                owners.get(id(stmt), ""),
                                stmt.lineno,
                            )
                        )
    return missing, cleared


def test_a_table_under_a_pressable_row_keeps_the_toolbar_clearance() -> None:
    """표 도구 막대(열 보기·내려받기·찾기·전체 화면)는 표 머리 위 37px 까지 솟는다(AGENTS 9장).

    표 바로 위 형제가 입력·단추·팝오버·토글·날짜 칸을 품으면 그 사이에 `toolbar_clearance()` 를
    둔다 — 없으면 막대가 위 줄 오른쪽 끝의 단추·지우기(✕)를 덮어 표에서 그리로 옮긴 누름을
    가로챈다(2026-10-25·26 E2E — 설비 시나리오 리비전 표·Qual 마감 계산기 월 편집표·Space).
    """
    missing, cleared = _tables_after_pressables()
    offenders = [
        f"{path}:{line} ({function})"
        for path, function, line in missing
        if (path, function) not in CLEARANCE_ALLOWED
    ]

    assert not offenders, (
        "표 바로 위 형제에 누를 것이 있습니다 — 표 앞에 `table_toolbar.toolbar_clearance()` 를 "
        "두세요(띄움이 필요 없으면 CLEARANCE_ALLOWED 에 까닭과 함께):\n" + "\n".join(offenders)
    )
    # 그물이 표를 보고 있는지 — 띄움을 둔 표가 하나도 안 잡히면 탐색이 망가진 것이다.
    assert cleared >= 6


def test_every_allowed_table_still_needs_its_exception() -> None:
    missing, _ = _tables_after_pressables()
    stale = sorted(set(CLEARANCE_ALLOWED) - {(path, function) for path, function, _ in missing})

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
