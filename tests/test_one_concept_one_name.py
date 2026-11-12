# Purpose: 바꾼 화면 이름의 옛 꼴이 화면 글 · Guide · README 에 남지 않았는지 훑는다.

"""한 개념 한 이름(UI-CON-02) — 이름을 바꾸면 화면 글 · Guide · 안내 글을 같은 변경에서 바꾼다.

소스는 사용자에게 갈 수 있는 글(문자열 상수 · f-string 의 글 조각, docstring 은 빼고)만 본다.
칸 이름 계약(`확보기준` · `확보기준 과부족` · `경고기준 필요대수` 등)은 코드 이름이라 뺀다.
필요 단축 일정 글은 사용자 문구 전달 때 함께 고친다(TODO 2장) — 그 글만 `WAITING` 으로 비켜 둔다.
여러 이름이 「대수」 하나를 나눠 쓴 구절(「총 · 가용 · 비가동 대수」)은 `SHARED` 로 비켜 둔다.
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
    # 자동 갱신이 스스로 하는 공식 지정(작은 결정 d3 — 2026-11-08). 새 회차의 사유 글도
    # 「지정」 으로 적는다(검수 보드 sc-runner-word) — 이미 저장된 옛 사유는 값이라 그대로다.
    "등록·발행": "등록·지정",
    "공식버전을 발행": "공식버전으로 지정",
    "공식버전으로 발행": "공식버전으로 지정",
    "공식버전 발행": "공식버전 지정",
    # Alarm 거르기 체크 — 해소만이 아니라 내용 바뀜 · 범위 바뀜 줄도 감춘다(지난 보드
    # a-hide-closed).
    "해소된 것 숨김": "닫힌 것 숨김",
    # 「비가동대수」 는 붙여 쓴다. 마이그레이션 SQL · migration_catalog · data_model · 날짜 붙은
    # 기록은 이 시험이 보지 않는 자리라 띄어 쓴 그대로다.
    "입력 비가동 대수": "입력 비가동대수",
    "비가동 대수": "비가동대수",
}
# 칸 이름 계약 — 문자열 전체가 이것이면 화면 글이 아니다(표 머리는 `column_config` 라벨이 말한다).
COLUMN_NAMES: Final = frozenset({"확보기준", "확보기준 과부족", "확보기준 추가대수"})
# 여러 이름이 「대수」 하나를 나눠 쓴 구절 — 「비가동 대수」 한 이름이 아니라 이 구절만 지우고 본다.
SHARED: Final = ("총 · 가용 · 비가동 대수",)
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
    folded = re.sub(r"\s+", " ", text)
    for phrase in SHARED:
        folded = folded.replace(phrase, "")
    return folded


def _stale(name: str, text: str) -> list[str]:
    """`text` 에 남은 옛 이름. 긴 옛 이름 안에만 든 짧은 옛 이름(「입력 비가동 대수」 속
    「비가동 대수」)은 한 번 더 내지 않는다 — 따로 남은 것이 있을 때만 낸다."""
    found = [old for old in RENAMED if old in text and old not in WAITING.get(name, frozenset())]
    return [
        old
        for old in found
        if text.count(old)
        > sum(text.count(longer) for longer in found if longer != old and old in longer)
    ]


def test_a_short_old_name_inside_a_long_one_is_reported_once() -> None:
    """옛 꼴 하나는 실패 줄 하나다 — 긴 이름 안의 짧은 이름은 따로 남았을 때만 따로 나온다."""
    assert _stale("x.py", "입력 비가동 대수를 읽지 못했습니다") == ["입력 비가동 대수"]
    assert _stale("x.py", "비가동 대수는 숫자여야 합니다") == ["비가동 대수"]
    assert _stale("x.py", "입력 비가동 대수 · 비가동 대수") == ["입력 비가동 대수", "비가동 대수"]
    assert _stale("x.py", _folded("총 · 가용 · 비가동 대수에서 뺌")) == []


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
