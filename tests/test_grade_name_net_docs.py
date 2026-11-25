# Purpose: Guide · 런북 · 지침서 · 사내 문서 · 모듈 파일의 「관리자」 가 새 뜻 허용 꼴뿐인지 본다.

"""「관리자」 뜻 뒤집힘 그물 — 문서 · 모듈 쪽(2026-11-18 접속 등급 결정 1 — 허용 목록 방식).

옛 뜻 「관리자」(Admin Area 쪽 · 「관리자만 여는 화면」 · 「관리자로」 · 「관리자(환경변수)」 ·
「관리자가 넣음」 · 「관리자용 진단」 · 「관리자에게 알려」 등)는 「개발자」 로, 역할 「앱
관리자」 는 「앱 관리자(개발자)」 로 바꿨다. 새 「관리자」 는 옛 공식 지정자 뜻으로만 쓴다.
core 그물(`tests/test_grade_name_net.py`)이 앱 · 페이지 · 부품 · `auth` · `scripts` 의 `.py` 화면
글과 `docs/sso_setup.md` 를 보고, 이 그물이 나머지를 같은 허용 목록(`tests/grade_words.py`)으로
본다.

- **문서** — Guide 전부 · 런북 · 모듈 지침서 · 모듈 담당자 안내서(글 원본과 GitHub Pages 판) ·
  사내에 가는 설정 문서 셋(`objectstore_setup` · `bigdataquery_webide_setup` ·
  `dual_env_workflow`) · 감사 기록 운영 문서 · README. 문서 본문 전부를 본다. 날짜 붙은 결정
  기록 인용(`docs/TODO.md` · `docs/design_rules.md` 와 기록 `docs/records/` 의 결정 · 닫힌 항목 ·
  규칙집 판 기록에 든 대화 원문)은 이 그물 밖이다.
- **모듈 파일** — core 그물이 빼는 바로 그 파일(`module_*.py` · `components/module_*.py` ·
  `app_pages/internal_modules.py` · `scripts/new_module.py` · `scripts/module_check_rules.py`)의
  화면 글(문자열 상수 · f-string 조각, docstring 빼고). 같은 뿌리에서 core 범위를 뺀 나머지라
  두 그물 사이에 빈틈이 없다.

허용 목록 밖에서 이 갈래만 더 받는 꼴(`LANE_ALLOWED`)은 둘이다 — 문서가 화면 라벨을 그대로
옮긴 **등급 이름표**(`` `관리자` `` · `**관리자**` · 표 칸 `| 관리자 |` — 화면에 그 낱말 하나로
서는 것은 새 등급 이름뿐이다)와 다른 뜻의 **`작업 관리자`**(브라우저 · Windows 의 프로그램
이름 — 런북의 메모리 재는 법).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from grade_words import stray_manager_words, stray_old_grade_words
from test_grade_name_net import ROOT, screen_python_files, screen_strings

GUIDES: Final = ROOT / "src" / "capa_simulation" / "guides"
DOCUMENTS: Final = (
    "docs/internal_update_runbook.md",
    "docs/module_guide.md",
    "docs/module_colleague_guide.md",
    "site/module-guide/index.html",
    "docs/objectstore_setup.md",
    "docs/bigdataquery_webide_setup.md",
    "docs/dual_env_workflow.md",
    "docs/audit_log_operations.md",
    "README.md",
)
# 날짜 붙은 결정 기록 인용이 남는 문서 — 그물 밖(옛 뜻의 원문을 고치지 않는다).
DATED_RECORDS: Final = (
    "docs/TODO.md",
    "docs/design_rules.md",
    "docs/records/decisions.md",
    "docs/records/closed.md",
    "docs/records/design_rules_log.md",
)
# 이 갈래만 더 받는 꼴 — 등급 이름표(화면 라벨) · 다른 뜻의 프로그램 이름.
LANE_ALLOWED: Final = (
    re.compile(r"`관리자`"),
    re.compile(r"\*\*관리자\*\*"),
    re.compile(r"(?<=\|) *관리자 *(?=\|)"),
    re.compile(r"작업 관리자"),
)


def _without_lane_allowed(text: str) -> str:
    for pattern in LANE_ALLOWED:
        text = pattern.sub(lambda match: "□" * len(match.group(0)), text)
    return text


def stray_in_document(text: str) -> list[str]:
    """문서 글에서 허용 꼴(공용 목록 + 이 갈래 꼴)을 지운 뒤 남은 「관리자」 의 앞뒤 글."""
    return stray_manager_words(_without_lane_allowed(text))


def module_python_files() -> list[Path]:
    """core 그물이 빼는 모듈 파일 — 같은 뿌리(앱 · 페이지 · 패키지 · scripts)에서 core 범위를
    뺀 나머지."""
    core = set(screen_python_files())
    roots = [ROOT / "app.py", ROOT / "capa_server.py"]
    for folder in (ROOT / "app_pages", ROOT / "src" / "capa_simulation", ROOT / "scripts"):
        roots.extend(sorted(folder.rglob("*.py")))
    return [path for path in roots if path not in core]


def test_guides_use_the_manager_word_only_in_the_new_sense() -> None:
    stray = [
        f"{path.name}: {found}"
        for path in sorted(GUIDES.glob("*.md"))
        for found in stray_in_document(path.read_text(encoding="utf-8"))
    ]
    assert not stray, (
        "옛 뜻 「관리자」 가 남았다 — 「개발자」 로 바꾸거나 허용 꼴로:\n" + "\n".join(stray)
    )


def test_internal_documents_use_the_manager_word_only_in_the_new_sense() -> None:
    stray = [
        f"{name}: {found}"
        for name in DOCUMENTS
        for found in stray_in_document((ROOT / name).read_text(encoding="utf-8"))
    ]
    assert not stray, (
        "옛 뜻 「관리자」 가 남았다 — 「개발자」 로 바꾸거나 허용 꼴로:\n" + "\n".join(stray)
    )


def test_guides_and_internal_documents_never_use_the_old_grade_word() -> None:
    """옛 두 등급의 「일반」 이 등급 자리에 남지 않는다
    (`tests/grade_words.stray_old_grade_words`)."""
    texts = [(path.name, path.read_text(encoding="utf-8")) for path in sorted(GUIDES.glob("*.md"))]
    texts += [(name, (ROOT / name).read_text(encoding="utf-8")) for name in DOCUMENTS]
    stray = [f"{name}: {found}" for name, text in texts for found in stray_old_grade_words(text)]
    assert not stray, "옛 등급 낱말 「일반」 이 남았다:\n" + "\n".join(stray)


def test_module_screen_strings_use_the_manager_word_only_in_the_new_sense() -> None:
    stray = [
        f"{path.relative_to(ROOT).as_posix()}:{line}: {found}"
        for path in module_python_files()
        for line, text in screen_strings(path)
        for found in stray_manager_words(text)
    ]
    assert not stray, "\n".join(stray)


def test_the_two_nets_split_the_python_files_without_a_gap() -> None:
    """모듈 파일이 실제로 있고(그물이 헛돌지 않음) core 범위와 겹치지 않는다."""
    modules = {path.relative_to(ROOT).as_posix() for path in module_python_files()}
    core = {path.relative_to(ROOT).as_posix() for path in screen_python_files()}

    assert {
        "src/capa_simulation/module_helpers.py",
        "src/capa_simulation/components/module_failure_card.py",
        "app_pages/internal_modules.py",
        "scripts/new_module.py",
        "scripts/module_check_rules.py",
    } <= modules
    assert not modules & core


def test_the_documents_exist_and_dated_records_stay_outside() -> None:
    for name in (*DOCUMENTS, *DATED_RECORDS):
        assert (ROOT / name).is_file(), name
    assert not set(DATED_RECORDS) & set(DOCUMENTS)
    assert sorted(GUIDES.glob("*.md")), "훑을 Guide 가 있어야 한다"


def test_the_net_catches_the_old_sense_and_lets_the_allowed_forms_through() -> None:
    """그물이 헛돌지 않는다 — 옛 꼴은 잡고 허용 꼴 · 등급 이름표 · 다른 뜻은 지나간다."""
    for old in (
        "운영 서버에서는 **관리자에게만** 열립니다",
        "주소로 열어도 「관리자만 여는 화면입니다」 와",
        "등록 길(`스스로 등록` · `관리자가 넣음`)",
        "등급(`일반` · `관리자(환경변수)`)",
        "접힌 「관리자용 진단」 을 펼친다",
        "담당자가 앱 관리자에게 알린다",
        "| 관리자로 · 일반으로 |",
    ):
        assert stray_in_document(old), old
    for allowed in (
        "앱 관리자(개발자)에게 알린다",
        "저장소 관리자에게 요청할 일",
        "관리자부터 공식 지정을 할 수 있습니다",
        "등급(`열람` · `실무자` · `관리자` · `개발자`)",
        "| 하는 일 | 열람 | 실무자 | 관리자 | 개발자 |",
        "**관리자**(+ 공식 지정)",
        "Chrome 작업 관리자(`Shift`+`Esc`)",
        "브라우저 개발자 도구",
        "기록 열람",
    ):
        assert not stray_in_document(allowed), allowed
