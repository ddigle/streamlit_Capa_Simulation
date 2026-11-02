# Purpose: 앱 화면 글(앱 안 Guide · 통합인증 화면)에 「사내」 가 없는지 지킨다.

"""앱 화면 글에는 「사내」 를 쓰지 않는다.

2026-11-03 사용자 결정 — 회사 안에서 쓰는 것이 기본이라 어색하다. 개발 · 배포 문서와 주석 ·
docstring 의 사내/사외 환경 구분은 그대로 둔다 — 여기서는 사용자가 화면에서 읽는 글만 본다.
앱 안 Guide 마크다운(`guides/*.md`)은 통째로, 통합인증 화면 모듈은 docstring 을 뺀 문자열
상수를 본다(HTML 화면 · 표 · 경고 · 띠 글이 모두 상수로 들어 있다). 담당자가 읽는 모듈
지침서 · 안내서는 `test_module_guide_sync.py` 가 따로 본다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "capa_simulation"
WORD = "사내"

# 통합인증이 화면에 내는 글을 가진 모듈 — 로그인 · 오류 · 설정 HTML 화면, 멈춤 화면 · 카드
# 셋째 줄, 「다시 로그인」 띠, Admin 「통합인증 점검」 · 「서버 시작 점검」(시작 스크립트가 결과
# 파일에 남긴 단계 까닭 · pip 출력 머리도 그 펼침에 그대로 선다).
SSO_SCREEN_MODULES = (
    PACKAGE / "auth" / "web.py",
    PACKAGE / "components" / "sso_identity.py",
    PACKAGE / "components" / "sso_reconnect.py",
    PACKAGE / "components" / "sso_status.py",
    PACKAGE / "components" / "container_start_check.py",
    PACKAGE / "io" / "container_start_report.py",
    ROOT / "scripts" / "container_start.py",
)
_DOCUMENTED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def screen_strings(source: str) -> list[str]:
    """docstring 을 뺀 문자열 상수(f-string 조각 포함)를 나온 차례로."""
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, _DOCUMENTED) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]
    return [str(node.value) for node in sorted(found, key=lambda node: node.lineno)]


def test_the_docstring_filter_keeps_plain_constants() -> None:
    source = (
        '"""모듈 설명 사내."""\n\nLABEL = "사내 화면"\n\n\n'
        'def f() -> str:\n    """함수 설명 사내."""\n    return f"보이는 {LABEL}"\n'
    )
    assert screen_strings(source) == ["사내 화면", "보이는 "]


def test_the_sso_screen_modules_are_listed_where_they_live() -> None:
    assert all(path.is_file() for path in SSO_SCREEN_MODULES)


@pytest.mark.parametrize("path", SSO_SCREEN_MODULES, ids=lambda path: path.name)
def test_sso_screen_text_does_not_say_sanae(path: Path) -> None:
    hits = [text for text in screen_strings(path.read_text(encoding="utf-8")) if WORD in text]
    assert hits == [], f"{path.relative_to(ROOT)} 의 화면 글에 「{WORD}」"


def test_in_app_guides_do_not_say_sanae() -> None:
    guides = sorted((PACKAGE / "guides").glob("*.md"))
    assert guides, "앱 안 Guide 마크다운을 찾지 못했다"
    hits = [path.name for path in guides if WORD in path.read_text(encoding="utf-8")]
    assert hits == []
