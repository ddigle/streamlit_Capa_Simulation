# Purpose: 사내에 가는 문서가 일하는 쪽을 「사외」 꼴로 다시 부르지 않는지 지킨다.

"""사내에 가는 문서에서 일하는 쪽은 「정본 개발 에이전트」 로 쓴다.

2026-11-17 사용자 결정 — 「앞으로 사내 에이전트에게 전달하는 런북이나 가이드문서 등에서 활용되는
사외 에이전트라는 표현은 정본 개발 에이전트 라는 표현으로 우회하도록 반영해」, 범위는 「일하는 쪽
뜻만」(`docs/TODO.md` 3장 「운영·배포」 같은 날). 개발하고 배포를 만들고 리뷰를 받아 고치는 쪽을
가리키는 「사외」 만 바꿨다. 장소 · 환경 뜻(사외 저장소 · 사외(`origin/main`) · 사외 합성 표본),
도구가 찍는 글을 옮긴 것(「사외에서 지워진 파일」), 리뷰 칸 이름(「사외 요청」 · `사외요청`)은
그대로다.

그래서 「사외」 낱말을 통째로 막지 않는다. 바꾼 뒤 사내에 가는 문서(`INTERNAL_DOCUMENTS` — 런북 · 두
환경 절차 · 모듈 지침서 · 동료 안내서 · `CLAUDE.md` 와 그 절이 있는 장 파일, 담당자가 첫 지시를
복사해 가는 안내서 HTML 판)에서 0 번이 된 일하는 쪽 꼴만 막는다.
「사외가」 도 첫 지시 5번 세 곳을 함께 바꿔 0 번이 되어 막는다 — 적용기가 찍는 「사외가 추가하게
한다」 는 `.py` 안에만 남고 문서는 그 글을 옮기지 않는다. 문서는 줄을 접으므로 꼴 안의 띄어쓰기는
줄바꿈 · 들여쓰기도 받는다. 검사는 글을 받아 어긋남 목록을 내는 함수(`violations`) 하나다 — 지금
여섯 문서가 빈 목록이고, 옛 꼴을 끼워 넣으면 잡힌다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 사내에 가는 문서 — 사내 배포 에이전트 · 모듈 담당자 에이전트 · 담당자가 읽는다. 안내서 HTML 판은
# 담당자가 첫 지시를 복사해 가는 자리다.
INTERNAL_DOCUMENTS = (
    "docs/internal_update_runbook.md",
    "docs/dual_env_workflow.md",
    "docs/module_guide.md",
    "docs/module_colleague_guide.md",
    "CLAUDE.md",
    # CLAUDE.md 의 명령 · 아키텍처 · 상태·캐시 · SQL · 발표 자료 절이 있는 장 파일 —
    # 사내 세션도 그 절을 읽는다.
    "docs/rules/00-purpose-header.md",
    "docs/rules/02-runtime-and-verification.md",
    "docs/rules/05-state-cache-invariants.md",
    "docs/rules/10-local-files-security.md",
    "docs/rules/16-layers-and-boundaries.md",
    "site/module-guide/index.html",
)
NEW_TERM = "정본 개발 에이전트"
# 일하는 쪽을 가리키던 꼴. 2026-11-17 에 바꿔 여섯 문서에서 0 번이 된 것과 처음부터 0 번인
# 「사외 에이전트」 · 「사외에게」 · 「사외로 내(낸 · 내는)」 이다. 장소 뜻이 걸리면 「사외 저장소」
# 처럼 장소를 밝혀 쓴다.
WORKER_FORMS = (
    "사외 에이전트",
    "사외 세션",
    "사외가",
    "사외는",
    "사외에게",
    "사외도",
    "사외만",
    "사외로는",
    "사외로 내",
    "사외로 옮긴",
    "사외에 알린",
    "사외 몫",
    "사외 메모",
    "사외 대화",
    "사외 리뷰",
    "사외 판단",
)
_WORKER_PATTERNS = tuple(
    (form, re.compile(r"\s+".join(re.escape(word) for word in form.split(" "))))
    for form in WORKER_FORMS
)


def violations(name: str, text: str) -> list[str]:
    """`text` 에서 일하는 쪽 꼴이 걸린 자리를 `<파일>:<줄>: …` 한 줄씩 낸다(줄 차례)."""
    found: list[tuple[int, str]] = []
    for form, pattern in _WORKER_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            found.append((line, form))
    return [f"{name}:{line}: 「{form}」 → 「{NEW_TERM}」 로 쓴다" for line, form in sorted(found)]


@pytest.mark.parametrize("document", INTERNAL_DOCUMENTS)
def test_internal_documents_name_the_working_side_as_the_new_term(document: str) -> None:
    text = (PROJECT_ROOT / document).read_text(encoding="utf-8")

    found = violations(document, text)

    assert not found, (
        f"사내에 가는 문서가 일하는 쪽을 「사외」 로 부릅니다. 「{NEW_TERM}」 로 씁니다"
        " — 장소 뜻이면 「사외 저장소」 처럼 장소를 밝히고, 리뷰 칸 「사외 요청」 ·"
        " 도구 출력은 그대로 둡니다:\n" + "\n".join(found)
    )


@pytest.mark.parametrize("form", WORKER_FORMS)
def test_each_worker_form_is_caught_with_its_line(form: str) -> None:
    text = f"머리\n\n앞 {form} 뒤\n"

    assert violations("doc.md", text) == [f"doc.md:3: 「{form}」 → 「{NEW_TERM}」 로 쓴다"]


@pytest.mark.parametrize("form", [form for form in WORKER_FORMS if " " in form])
def test_a_worker_form_folded_across_lines_is_caught_on_its_first_line(form: str) -> None:
    folded = form.replace(" ", "\n  ", 1)
    text = f"머리\n앞 {folded} 뒤\n"

    assert violations("doc.md", text) == [f"doc.md:2: 「{form}」 → 「{NEW_TERM}」 로 쓴다"]


def test_place_tool_and_review_field_forms_are_not_caught() -> None:
    text = "\n".join(
        (
            "이 저장소는 사외(개발 PC)와 사내(WebIDE) 두 곳에서 열린다.",
            "코어의 정본은 사외(`origin/main`)이고 사외 저장소에는 `modules/` 가 없다.",
            "고쳐야 할 것은 리뷰 「사외 요청」 으로 낸다 — 압축본 키는 `사외요청` 이다.",
            "적용기는 「사외에서 지워진 파일」 을 지운다.",
            "사외 합성 표본으로 잰 수이고, 사외에는 합성 표본밖에 없다.",
            "사내 DB 를 사외로 보내는 길은 없다 — 사외와 같은 화면이다.",
            f"{NEW_TERM}가 고치고, {NEW_TERM}에게 알린다.",
        )
    )

    assert violations("doc.md", text) == []
