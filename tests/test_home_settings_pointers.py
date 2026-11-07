# Purpose: 화면 글 · Guide 가 없어진 자리(HOME 「Preference」 탭 · 본문 오류)를 가리키는지 훑는다.

"""HOME 설정 팝업은 2026-11-04(검수 의견 home-u01)부터 쓰는 묶음 다섯 탭이다 — `Preference`
탭이 없다.

다른 화면의 「HOME 설정 → Preference」 안내를 새 탭 이름으로 바꿀 때 문자열이 「→」 뒤에서 줄이
바뀐 자리(제약 시뮬레이션 개조 일정 풍선 · 산출 결과 Guide)와 「Preference 확보 기준」 꼴(공정
Capa 상세 Guide)이 남았다(2026-11-04 재검 b-2 · c-1 · c-2). 사용자에게 보이는 글 —
Guide(`guides/*.md`)와 소스의 문자열(이어 붙인 문자열 · f-string 의 글 조각, docstring 은 빼고) —
을 공백을 접어 훑는다. 앱의 「Preference」 탭은 이제 가용설비 현황 셋째 탭(입력 비가동)뿐이고 그
글은 판정 기준을 말하지 않아 걸리지 않는다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from capa_simulation.components.equipment_settings_dialog import LOCKED_HELP
from capa_simulation.components.home_settings import STOPPED_HELP

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "src" / "capa_simulation" / "guides"

# HOME 쪽 옛 탭을 가리키는 꼴 — 「HOME 설정 → Preference」(줄이 바뀌어도) · 「Preference
# 확보기준」 · 「Preference 의 「확보율 판정 기준」」 · 「Preference 공용 판정 기준」.
STALE_POINTER = re.compile(
    r"HOME\s*설정\s*(?:팝업\s*)?(?:→|›|의)\s*`?Preference"
    r"|Preference`?\s*(?:탭\s*)?(?:의\s*)?(?:「?확보율 판정 기준|확보\s*기준|공용 판정 기준)"
)


def _folded(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _docstrings(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


def _source_texts(path: Path) -> list[tuple[int, str]]:
    """소스 한 파일의 화면에 갈 수 있는 글 — 문자열 상수(docstring 빼고)와 f-string 의 글 조각."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skipped = _docstrings(tree)
    texts: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            pieces = [part.value for part in node.values if isinstance(part, ast.Constant)]
            texts.append((node.lineno, "".join(str(piece) for piece in pieces)))
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skipped
        ):
            texts.append((node.lineno, node.value))
    return texts


def _sources() -> list[Path]:
    return sorted(
        [
            ROOT / "app.py",
            *(ROOT / "app_pages").rglob("*.py"),
            *(ROOT / "src").rglob("*.py"),
        ]
    )


def test_the_pattern_catches_the_old_pointers_and_not_the_equipment_tab() -> None:
    """그물이 옛 꼴(줄바꿈 낀 것 포함)을 잡고 가용설비 현황 Preference 탭 글은 놓아준다."""
    caught = [
        "「HOME 기준」 은 HOME 설정 → Preference 공용 판정 기준(기본 + 월별 예외)을 달마다 씁니다.",
        "판정 기준(확보·경고 %)은 HOME 설정 →\nPreference 의 「확보율 판정 기준」(공용 값)",
        "이 화면의 목표는 Preference 확보기준 110% 의 판정 경계",
        "판정 기준은 HOME 설정 → `Preference` 에서 정합니다.",
    ]
    passed = [
        "입력 비가동(가용설비 현황 › Preference)은 호기에 잇지 않은 공정 × 달 손실",
        "「HOME 기준」 은 HOME 설정 → 판정 기준 탭의 공용 판정 기준(기본 + 월별 예외)을 씁니다.",
        "전에는 HOME 의 `Preference` · `Past Data` 탭이었습니다",
    ]
    assert all(STALE_POINTER.search(_folded(text)) for text in caught)
    assert not any(STALE_POINTER.search(_folded(text)) for text in passed)


def test_guides_do_not_point_to_the_old_home_preference_tab() -> None:
    """Guide 는 판정 기준을 「HOME 설정 → 판정 기준」 으로 가리킨다."""
    stale = [
        f"{path.name}: {match.group(0)}"
        for path in sorted(GUIDES.glob("*.md"))
        for match in STALE_POINTER.finditer(_folded(path.read_text(encoding="utf-8")))
    ]
    assert stale == []


def test_screen_texts_do_not_point_to_the_old_home_preference_tab() -> None:
    """화면 글(풍선 · 캡션 · 알림 등 소스의 문자열)도 옛 탭을 가리키지 않는다."""
    stale = [
        f"{path.relative_to(ROOT)}:{line}: {match.group(0)}"
        for path in _sources()
        for line, text in _source_texts(path)
        for match in STALE_POINTER.finditer(_folded(text))
    ]
    assert stale == []


def test_locked_settings_boxes_point_to_the_alarm_not_the_body() -> None:
    """오류 글은 본문에 서지 않고 Alarm 에만 있다(UI-NTF-08) — 잠긴 상자 풍선이 없는 자리를 가리키면
    고칠 글을 찾지 못한다."""
    assert "Alarm 의 오류" in STOPPED_HELP
    assert "Alarm 의 오류" in LOCKED_HELP
    stale = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in _sources()
        for line, text in _source_texts(path)
        if "본문의 오류를" in _folded(text)
    ]
    assert stale == []
