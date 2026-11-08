# Purpose: 바꾼 화면 이름의 옛 꼴이 화면 글 · Guide · README 에 남지 않았는지 훑는다.

"""한 개념 한 이름(UI-CON-02) — 이름을 바꾸면 화면 글 · Guide · 안내 글을 같은 변경에서 바꾼다.

소스는 사용자에게 갈 수 있는 글(문자열 상수 · f-string 의 글 조각, docstring 은 빼고)만 본다.
칸 이름 계약(`확보기준` · `확보기준 과부족` · `경고기준 필요대수` 등)은 코드 이름이라 뺀다.
필요 단축 일정 글은 사용자 문구 전달 때 함께 고친다(TODO 2장) — 그 글만 `WAITING` 으로 비켜 둔다.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "src" / "capa_simulation" / "guides"

# 옛 이름 → 지금 이름.
RENAMED: Final[dict[str, str]] = {
    "한꺼번에 넣기": "엑셀·CSV로 한꺼번에",
    "Summary 공지": "공지",
    "Summary 저장": "공지 저장",
    "이 실행에서는": "이 서버에서는",
    "붙여넣기 일괄 적용": "붙여넣기 적용 · 붙여넣기 올리기",
    "공식으로 발행": "공식으로 지정",
    "발행 이력": "공식 이력",
    "확보기준": "확보 기준",
}
# 칸 이름 계약 — 문자열 전체가 이것이면 화면 글이 아니다(표 머리는 `column_config` 라벨이 말한다).
COLUMN_NAMES: Final = frozenset({"확보기준", "확보기준 과부족", "확보기준 추가대수"})
# 필요 단축 일정 글 — 사용자 문구 전달 때 함께 고친다.
WAITING: Final[dict[str, frozenset[str]]] = {
    "required_shortening.md": frozenset({"확보기준", "공식으로 발행"}),
    "equipment_scenario_status.py": frozenset({"공식으로 발행"}),
}


def _texts(path: Path) -> Iterator[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docs.add(id(first.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            yield node.lineno, node.value


def _folded(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _stale(name: str, text: str) -> list[str]:
    return [old for old in RENAMED if old in text and old not in WAITING.get(name, frozenset())]


def test_screen_texts_use_the_current_names() -> None:
    """소스의 글에 옛 이름이 남지 않았다. 칸 이름 계약은 문자열 전체가 그 이름일 때만 놓아준다."""
    files = [
        ROOT / "app.py",
        *(ROOT / "app_pages").rglob("*.py"),
        *(ROOT / "src").rglob("*.py"),
    ]
    stale = [
        f"{path.relative_to(ROOT)}:{line}: {old} → {RENAMED[old]}"
        for path in sorted(files)
        for line, text in _texts(path)
        if text not in COLUMN_NAMES
        for old in _stale(path.name, _folded(text))
    ]
    assert stale == []


def test_guides_and_readme_use_the_current_names() -> None:
    """Guide · README 도 같다 — 줄이 바뀐 이름도 잡도록 공백을 접어 본다."""
    files = [*sorted(GUIDES.glob("*.md")), ROOT / "README.md"]
    stale = [
        f"{path.name}: {old} → {RENAMED[old]}"
        for path in files
        for old in _stale(path.name, _folded(path.read_text(encoding="utf-8")))
    ]
    assert stale == []


def test_the_mode_keeps_its_name_and_no_section_takes_it() -> None:
    """모드 「개조 일정」 은 그대로다. 제약 영향 본문에는 개조 창 구획이 없다(2026-11-08 사용자
    그림 메모 g12) — 본문 구획 제목에 「개조 일정」 이 서지 않는다."""
    from capa_simulation.components import constraint_simulation_view
    from capa_simulation.modification_schedule_state import MODE_LABELS

    assert "개조 일정" in MODE_LABELS.values()
    assert not hasattr(constraint_simulation_view, "SCHEDULE_CARD_TITLE")
    view = (ROOT / "src/capa_simulation/components/constraint_simulation_view.py").read_text(
        encoding="utf-8"
    )
    assert "**개조 일정**" not in view
