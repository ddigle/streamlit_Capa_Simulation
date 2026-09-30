# Purpose: 편집표가 결측 칸을 `None` 글자가 아니라 빈칸으로 그리는지 고정한다.

"""편집표의 빈칸은 빈칸으로 보여야 한다(2026-10-01 브라우저 점검).

Streamlit 1.63 `st.data_editor` 는 `placeholder` 를 주지 않으면 결측 칸에 회색 `None` 글자를
쓴다. 가이드·경고문은 그 칸을 「빈칸」이라 부르므로(비운 붙여넣기, 값이 없는 달, 편집 불가 달)
화면과 글이 어긋났다. 편집표를 새로 더할 때 인자를 빠뜨리는 것이 이 결함의 모양이라 소스 전체를
훑어 막고, 공용 월 편집기는 실제로 그린 위젯에서 한 번 더 본다.
"""

import ast
from pathlib import Path

from streamlit.testing.v1 import AppTest
from test_month_editor_filter import EDITOR_SCRIPT

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (ROOT / "app.py", ROOT / "app_pages", ROOT / "src")
# 이 파일들의 편집표는 같은 날 다른 작업 갈래가 같은 인자를 들인다. 모두 들어오면 이 목록은
# 비어야 한다 — 아래 테스트가 낡은 항목을 알린다.
FIXED_ELSEWHERE = frozenset(
    {
        "app_pages/load_conversion.py",
        "src/capa_simulation/components/equipment_data_workspace.py",
        "src/capa_simulation/components/scenario_management.py",
    }
)


def _source_files() -> list[Path]:
    files: list[Path] = []
    for entry in SOURCE_ROOTS:
        files.extend([entry] if entry.is_file() else sorted(entry.rglob("*.py")))
    return files


def _data_editor_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "data_editor"
    ]


def _passes_blank_placeholder(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg == "placeholder":
            value = keyword.value
            # 빈 문자열 리터럴이거나, 상수 이름으로 넘긴 값이다(`None` 리터럴은 기본값과 같다).
            return not (isinstance(value, ast.Constant) and value.value != "")
    return False


def _missing_by_file() -> dict[str, list[int]]:
    missing: dict[str, list[int]] = {}
    for path in _source_files():
        lines = [
            call.lineno for call in _data_editor_calls(path) if not _passes_blank_placeholder(call)
        ]
        if lines:
            missing[path.relative_to(ROOT).as_posix()] = lines
    return missing


def test_every_data_editor_draws_a_missing_value_as_a_blank_cell() -> None:
    """`st.data_editor` 호출마다 `placeholder=""` 가 있어야 한다."""
    missing = {
        name: lines for name, lines in _missing_by_file().items() if name not in FIXED_ELSEWHERE
    }
    assert not missing, missing


def test_the_list_of_editors_fixed_elsewhere_is_not_stale() -> None:
    """예외 목록의 파일이 이미 규칙을 따르면 목록에서 지운다 — 남겨 두면 퇴행을 못 잡는다."""
    missing = _missing_by_file()
    stale = sorted(
        name for name in FIXED_ELSEWHERE if (ROOT / name).exists() and name not in missing
    )
    assert not stale, stale


def test_the_month_editor_widget_carries_an_empty_placeholder() -> None:
    """기준 정보 탭들이 함께 쓰는 월 편집기가 실제로 그린 편집표에 빈 `placeholder` 가 실린다."""
    app = AppTest.from_string(EDITOR_SCRIPT, default_timeout=60).run()
    assert not app.exception

    # 읽기 전용 표(`st.dataframe`)는 `editing_mode` 가 0 이다. 편집표만 고른다.
    editors = [element.proto for element in app.dataframe if element.proto.editing_mode]
    assert editors
    for proto in editors:
        assert proto.HasField("placeholder")
        assert proto.placeholder == ""
