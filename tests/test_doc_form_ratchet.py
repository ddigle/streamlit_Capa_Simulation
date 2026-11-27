# Purpose: 규칙 · 파일 서술 · 열린 일 문서의 날짜 · 경과 표기가 늘지 않게 막는 형식 래칫이다.

"""형식 래칫 — 「늘지 않기」.

규칙(`docs/rules/`) · 파일 서술(`docs/reference/files/`) · 열린 일(`docs/TODO.md`)은
지금 규칙을 적는 곳이고, 날짜 · 누가 언제 정했나 · 가지 이름 · 보드 답 표기는 경과라
결정 기록(`docs/records/decisions.md`)과 커밋 메시지 몫이다. 옮겨 온 글에 그런 표기가
정당하게 남아 있어 금지로 걸면 첫날 깨지므로, 파일마다 지금 수를 기준으로 두고 늘면
실패한다. 다듬기로 줄면 같은 변경에서 기준도 내린다(줄었는데 그대로면 실패).
규칙집(`docs/design_rules.md`)은 근거 칸에 날짜를 두는 꼴이라 크기 래칫만 건다
(`tests/test_doc_budget.py`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

FORMS: dict[str, re.Pattern[str]] = {
    "날짜": re.compile(r"\b20\d\d-\d\d-\d\d\b"),
    "사용자 결정": re.compile(r"사용자\s*(?:결정|요청|답)"),
    "가지 이름": re.compile(
        r"\b(?:lanes|integ|cand|feat|impr|custom|next|docs|rr\d{4})[/-][\w./-]*\d{4}\b"
    ),
    "보드 답": re.compile(r"보드\s*답|보드\s*\d|\bQ\d+\s*\((?:가|나|다|라)\)"),
}

# 파일 → 꼴 → 기준 수. 줄면 같은 변경에서 내린다. 올리는 것은 사용자 승인 거리다.
BASELINE: dict[str, dict[str, int]] = {
    "docs/rules/00-purpose-header.md": {"날짜": 0, "사용자 결정": 0, "가지 이름": 0, "보드 답": 0},
    "docs/rules/01-goals-and-boundaries.md": {
        "날짜": 25,
        "사용자 결정": 8,
        "가지 이름": 0,
        "보드 답": 0,
    },
    "docs/rules/02-runtime-and-verification.md": {
        "날짜": 9,
        "사용자 결정": 4,
        "가지 이름": 0,
        "보드 답": 0,
    },
    "docs/rules/04-reference-table-contract.md": {
        "날짜": 2,
        "사용자 결정": 2,
        "가지 이름": 0,
        "보드 답": 0,
    },
    "docs/rules/05-state-cache-invariants.md": {
        "날짜": 39,
        "사용자 결정": 7,
        "가지 이름": 0,
        "보드 답": 3,
    },
    "docs/rules/06-core-calculation.md": {
        "날짜": 61,
        "사용자 결정": 41,
        "가지 이름": 0,
        "보드 답": 7,
    },
    "docs/rules/07-join-validation.md": {
        "날짜": 14,
        "사용자 결정": 9,
        "가지 이름": 0,
        "보드 답": 4,
    },
    "docs/rules/08-display-sorting.md": {
        "날짜": 30,
        "사용자 결정": 8,
        "가지 이름": 0,
        "보드 답": 7,
    },
    "docs/rules/09-streamlit-implementation.md": {
        "날짜": 148,
        "사용자 결정": 10,
        "가지 이름": 0,
        "보드 답": 4,
    },
    "docs/rules/10-1-synthetic-local-data.md": {
        "날짜": 22,
        "사용자 결정": 9,
        "가지 이름": 0,
        "보드 답": 0,
    },
    "docs/rules/10-local-files-security.md": {
        "날짜": 10,
        "사용자 결정": 7,
        "가지 이름": 0,
        "보드 답": 1,
    },
    "docs/rules/11-unimplemented-caveats.md": {
        "날짜": 6,
        "사용자 결정": 2,
        "가지 이름": 0,
        "보드 답": 0,
    },
    "docs/rules/12-change-checklist.md": {
        "날짜": 2,
        "사용자 결정": 0,
        "가지 이름": 0,
        "보드 답": 0,
    },
    "docs/rules/13-document-priority.md": {
        "날짜": 0,
        "사용자 결정": 0,
        "가지 이름": 0,
        "보드 답": 0,
    },
    "docs/rules/14-parallel-development.md": {
        "날짜": 3,
        "사용자 결정": 0,
        "가지 이름": 0,
        "보드 답": 0,
    },
    "docs/rules/15-runbook-writing.md": {"날짜": 7, "사용자 결정": 1, "가지 이름": 0, "보드 답": 0},
    "docs/rules/16-layers-and-boundaries.md": {
        "날짜": 5,
        "사용자 결정": 0,
        "가지 이름": 0,
        "보드 답": 0,
    },
    "docs/reference/files/app-and-ui.md": {
        "날짜": 202,
        "사용자 결정": 37,
        "가지 이름": 0,
        "보드 답": 29,
    },
    "docs/reference/files/components.md": {
        "날짜": 260,
        "사용자 결정": 42,
        "가지 이름": 0,
        "보드 답": 15,
    },
    "docs/reference/files/input-and-state.md": {
        "날짜": 42,
        "사용자 결정": 12,
        "가지 이름": 0,
        "보드 답": 2,
    },
    "docs/reference/files/persistence.md": {
        "날짜": 1,
        "사용자 결정": 0,
        "가지 이름": 0,
        "보드 답": 0,
    },
    "docs/reference/files/services.md": {
        "날짜": 29,
        "사용자 결정": 10,
        "가지 이름": 0,
        "보드 답": 8,
    },
    "docs/TODO.md": {"날짜": 693, "사용자 결정": 81, "가지 이름": 80, "보드 답": 86},
}

GROWN = (
    "{path} 의 「{form}」 표기가 {base} → {now} 로 늘었다. "
    "날짜 · 경과 · 「사용자 결정」 · 보드 답 원문은 결정 기록(docs/records/decisions.md)과 "
    "커밋 메시지에 두고 규칙은 규칙 글만 쓴다."
)
SHRUNK = (
    "{path} 의 「{form}」 표기가 {now} 로 줄었다 — "
    "tests/test_doc_form_ratchet.py 기준을 {now} 로 내린다."
)


def _files() -> list[str]:
    found = [
        *sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "docs/rules").glob("*.md")),
        *sorted(
            p.relative_to(ROOT).as_posix() for p in (ROOT / "docs/reference/files").glob("*.md")
        ),
        "docs/TODO.md",
    ]
    return found


@pytest.mark.parametrize("path", sorted(BASELINE))
def test_dated_forms_do_not_grow(path: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for form, pattern in FORMS.items():
        now = len(pattern.findall(text))
        base = BASELINE[path][form]
        assert now <= base, GROWN.format(path=path, form=form, base=base, now=now)
        assert now == base, SHRUNK.format(path=path, form=form, now=now)


def test_every_rules_reference_and_todo_file_has_a_baseline() -> None:
    files = _files()
    assert files, "규칙 · 파일 서술 문서를 하나도 찾지 못했다"
    missing = [path for path in files if path not in BASELINE]
    stale = [path for path in BASELINE if not (ROOT / path).is_file()]
    assert not missing, f"기준이 없는 문서 — 새 파일이면 지금 수로 기준을 더한다: {missing}"
    assert not stale, f"없는 문서의 기준: {stale}"
    assert all(set(counts) == set(FORMS) for counts in BASELINE.values())
