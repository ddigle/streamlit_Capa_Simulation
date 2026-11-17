# Purpose: 화면에 닿는 글 · 통합인증 안내서의 「관리자」 가 새 뜻 허용 꼴뿐인지 본다.

"""「관리자」 뜻 뒤집힘 그물(2026-11-18 접속 등급 결정 1 — 허용 목록 방식).

옛 뜻 「관리자」(Admin Area 쪽 · 「관리자만 여는 화면」 · 「관리자로」 · 「관리자(환경변수)」 ·
「관리자가
넣음」 · 공지 보낸 이 · 「관리자용 진단」 · 「관리자에게 알려 주세요」 등)는 「개발자」 로 바꿨다.
이
그물은 화면 · 문서에 닿는 글(문자열 상수 · f-string 글 조각 · md 본문 · JS 글)의 「관리자」 가 허용
꼴
(`tests/grade_words.py`) 가운데 하나인지 본다. 주석 · 식별자 · docstring 은 그물 밖이다.

범위는 core 몫 — 모듈 파일(`module_*.py` · `components/module_*.py` ·
`app_pages/internal_modules.py` ·
`scripts/new_module.py` · `scripts/module_check_rules.py`)을 뺀 앱 · 페이지 · 부품 · `auth` ·
`scripts`
의 `.py` 와 부품 JS 자산, 그리고 `docs/sso_setup.md`. Guide · 런북 · 모듈 지침서 · 모듈 파일은
modules_docs 그물(`tests/test_grade_name_net_docs.py`)이 같은 허용 목록으로 본다.
"""

from __future__ import annotations

import ast
import re
import warnings
from pathlib import Path

from grade_words import LABEL_TABLE_FILES, stray_manager_words, stray_old_grade_words

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "capa_simulation"
SSO_SETUP = ROOT / "docs" / "sso_setup.md"
MODULE_FILES = (
    "app_pages/internal_modules.py",
    "scripts/new_module.py",
    "scripts/module_check_rules.py",
)
_DOCUMENTED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
# 발표 자료 티저(쇼케이스 원본의 복사본 — 저장소 규칙상 손대지 않는다)는 앱 글이 아니다.
_ASSET_SKIP = ("intro_overlay_assets/capa-teaser.html",)


def _is_module_file(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel in MODULE_FILES or name.startswith("module_")


def screen_python_files() -> list[Path]:
    roots = [ROOT / "app.py", ROOT / "capa_server.py"]
    for folder in (ROOT / "app_pages", PACKAGE, ROOT / "scripts"):
        roots.extend(sorted(folder.rglob("*.py")))
    return [path for path in roots if not _is_module_file(path.relative_to(ROOT).as_posix())]


def _docstring_ids(tree: ast.Module) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, _DOCUMENTED) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                found.add(id(first.value))
    return found


def screen_strings(path: Path) -> list[tuple[int, str]]:
    """그 파일의 화면에 닿는 글 — docstring 을 뺀 문자열 상수(f-string 글 조각 포함)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(path.read_text(encoding="utf-8"))
    skipped = _docstring_ids(tree)
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skipped
        and "관리자" in node.value
    ]


def test_screen_strings_use_the_manager_word_only_in_the_new_sense() -> None:
    stray: list[str] = []
    for path in screen_python_files():
        rel = path.relative_to(ROOT).as_posix()
        for line, text in screen_strings(path):
            if rel in LABEL_TABLE_FILES and text == "관리자":
                continue
            for found in stray_manager_words(text):
                stray.append(f"{rel}:{line}: {found}")
    assert not stray, (
        "옛 뜻 「관리자」 가 남았다 — 「개발자」 로 바꾸거나 허용 꼴로:\n" + "\n".join(stray)
    )


def test_asset_texts_use_the_manager_word_only_in_the_new_sense() -> None:
    """부품 JS · HTML 자산의 글(주석 줄 빼고)."""
    stray: list[str] = []
    for path in sorted((PACKAGE / "components").rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix not in (".js", ".html") or rel.endswith(_ASSET_SKIP):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.strip()
            if code.startswith(("//", "/*", "*", "<!--")):
                continue
            for found in stray_manager_words(re.sub(r"//.*$", "", code)):
                stray.append(f"{rel}:{number}: {found}")
    assert not stray, "\n".join(stray)


def test_the_sso_setup_guide_uses_the_manager_word_only_in_the_new_sense() -> None:
    stray = stray_manager_words(SSO_SETUP.read_text(encoding="utf-8"))
    assert not stray, "\n".join(stray)


def test_screen_strings_and_the_sso_guide_never_use_the_old_grade_word() -> None:
    """옛 두 등급의 「일반」 이 등급 자리에 남지 않는다(「일반 등급」 · 「개발자 n · 일반 n」 ·
    「등급을 일반으로」) — 등급은 넷이고 신청은 열람이다. 옛 기록 표시 「일반(옛 기록)」 · 되돌림
    설명의 옛 「일반」 은 지나간다."""
    stray = [
        f"{path.relative_to(ROOT).as_posix()}:{line}: {found}"
        for path in screen_python_files()
        for line, text in _all_strings(path)
        for found in stray_old_grade_words(text)
    ]
    stray += [
        f"docs/sso_setup.md: {found}" for found in stray_old_grade_words(SSO_SETUP.read_text())
    ]
    assert not stray, "옛 등급 낱말 「일반」 이 남았다:\n" + "\n".join(stray)
    for old in ("S3 명단에 **일반 등급**으로", "개발자 3 · 일반 40", "등급을 일반으로 읽음 2"):
        assert stray_old_grade_words(old), old
    for allowed in (
        "일반 설비와 같습니다",
        "일반(옛 기록)",
        "모두 옛 「일반」 이다",
        "일반 사용자",
    ):
        assert not stray_old_grade_words(allowed), allowed


def _all_strings(path: Path) -> list[tuple[int, str]]:
    """그 파일의 화면에 닿는 글 전부(docstring 뺌 — `screen_strings` 는 「관리자」 든 글만)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(path.read_text(encoding="utf-8"))
    skipped = _docstring_ids(tree)
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skipped
    ]


def test_the_net_catches_the_old_sense_and_lets_the_allowed_forms_through() -> None:
    """그물이 헛돌지 않는다 — 옛 꼴은 잡고 허용 꼴 · 다른 뜻은 지나간다."""
    for old in (
        "관리자만 여는 화면입니다",
        "관리자로",
        "관리자(환경변수)",
        "관리자가 넣음",
        "관리자 몫 알림이 서지 않습니다",
        "관리자 화면입니다",
        "관리자까지만 보입니다",
    ):
        assert stray_manager_words(old), old
    for allowed in (
        "앱 관리자(개발자)에게 알려 주세요",
        "저장소 관리자 · 보안 담당",
        "관리자부터 공식 지정을 할 수 있습니다",
        "열람 · 실무자 · 관리자 · 개발자",
        "브라우저 개발자 도구",
        "기록 열람",
        "Capa 공식 지정 · 설비 저장은 관리자 몫(등급)이고",
        "통합인증이 꺼진 운영 서버는 관리자 몫까지 됩니다(개발자 몫만 막힘).",
        "운영 서버에서 관리자 아래 등급에게는 값만 보입니다",
    ):
        assert not stray_manager_words(allowed), allowed
    # 문맥 꼴은 문장마다 본다 — 앞 문장의 등급 낱말이 다음 문장의 옛 꼴을 덮지 않는다.
    assert stray_manager_words("실무자부터 저장합니다. 관리자 몫 알림이 섭니다.")
    assert screen_python_files(), "훑을 파일이 있어야 한다"
    assert not any(
        _is_module_file(path.relative_to(ROOT).as_posix()) for path in screen_python_files()
    )
