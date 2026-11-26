# Purpose: 늘 읽는 문서의 글자 수가 상한을 넘거나, 줄었는데 상한이 그대로인 것을 막는 크기 래칫이다.

"""문서 크기 래칫.

늘 읽는 문서는 커지기만 해 왔다 — 덧붙이는 대신 맡은 파일 한 곳에서 고쳐 쓰게 하려고
상한을 둔다. 상한은 지금 크기에서 시작하고, 줄면 같은 변경에서 상한도 내린다(아래
``SLACK`` 보다 많이 줄었는데 그대로면 실패한다). 상한을 올리는 것은 사용자 승인 거리다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# 파일 → 글자 수 상한(str 길이 — 바이트가 아니다). 대상은 늘 읽는 문서 — 진입점 · 색인 · 규칙 장
# · 파일 서술 ·
# 열린 일 · 규칙집 · README 다. 기록(`docs/records/`)과 런북은 뺀다.
BUDGETS: dict[str, int] = {
    "AGENTS.md": 4_024,
    "CLAUDE.md": 4_953,
    "README.md": 65_682,
    "docs/TODO.md": 247_298,
    "docs/design_rules.md": 164_473,
    "docs/reference/files/app-and-ui.md": 206_911,
    "docs/reference/files/components.md": 277_840,
    "docs/reference/files/input-and-state.md": 62_931,
    "docs/reference/files/persistence.md": 27_004,
    "docs/reference/files/services.md": 64_489,
    "docs/rules/00-purpose-header.md": 1_952,
    "docs/rules/01-goals-and-boundaries.md": 9_744,
    "docs/rules/02-runtime-and-verification.md": 16_031,
    "docs/rules/04-reference-table-contract.md": 3_354,
    "docs/rules/05-state-cache-invariants.md": 52_012,
    "docs/rules/06-core-calculation.md": 55_246,
    "docs/rules/07-join-validation.md": 12_808,
    "docs/rules/08-display-sorting.md": 29_444,
    "docs/rules/09-streamlit-implementation.md": 137_694,
    "docs/rules/10-1-synthetic-local-data.md": 20_548,
    "docs/rules/10-local-files-security.md": 8_431,
    "docs/rules/11-unimplemented-caveats.md": 6_686,
    "docs/rules/12-change-checklist.md": 5_182,
    "docs/rules/13-document-priority.md": 617,
    "docs/rules/14-parallel-development.md": 8_862,
    "docs/rules/15-runbook-writing.md": 3_375,
    "docs/rules/16-layers-and-boundaries.md": 6_299,
}

# 진입점 · 색인의 굳은 천장 — 상한을 올려도 이 값은 넘지 않는다(올리려면 사용자 승인).
CEILINGS: dict[str, int] = {"CLAUDE.md": 6_000, "AGENTS.md": 8_000}

# 이만큼보다 더 줄었는데 상한을 그대로 두면 실패한다 — 줄어든 만큼 상한도 내려 다시 커지지 않게
# 한다.
SLACK = 1_000

GROWN = (
    "{path} 가 상한 {limit:,}자를 넘었다(지금 {size:,}자). "
    "덧붙이지 말고 그 규칙을 맡은 파일 한 곳에서 고쳐 쓴다. "
    "그래도 넘으면 줄이거나 기록으로 옮기지 말고 결과에 보고한다(총괄이 판단). "
    "상한 올리기는 사용자 승인."
)
SHRUNK = (
    "{path} 가 {size:,}자로 줄었다 — "
    "상한 {limit:,}자를 {size:,} 으로 내린다(tests/test_doc_budget.py)."
)


@pytest.mark.parametrize("path", sorted(BUDGETS))
def test_document_stays_within_its_budget(path: str) -> None:
    size = len((ROOT / path).read_text(encoding="utf-8"))
    limit = BUDGETS[path]
    assert size <= limit, GROWN.format(path=path, limit=limit, size=size)
    assert limit - size <= SLACK, SHRUNK.format(path=path, limit=limit, size=size)


def test_every_budgeted_document_exists() -> None:
    missing = [path for path in BUDGETS if not (ROOT / path).is_file()]
    assert not missing, missing


def test_every_rules_and_reference_file_has_a_budget() -> None:
    files = sorted(
        p.relative_to(ROOT).as_posix()
        for folder in ("docs/rules", "docs/reference/files")
        for p in (ROOT / folder).glob("*.md")
    )
    assert files, "규칙 · 파일 서술 문서를 하나도 찾지 못했다"
    missing = [path for path in files if path not in BUDGETS]
    assert not missing, f"상한이 없는 문서 — 새 파일이면 지금 크기로 상한을 더한다: {missing}"


def test_entry_and_index_budgets_stay_under_their_ceilings() -> None:
    over = {path: BUDGETS[path] for path, ceiling in CEILINGS.items() if BUDGETS[path] > ceiling}
    assert not over, f"진입점 · 색인 상한이 굳은 천장을 넘었다(사용자 승인 거리): {over}"
