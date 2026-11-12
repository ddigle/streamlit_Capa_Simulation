# Purpose: 퍼센트 차이를 화면·내려받기·Guide·문서에 「%」 로 적고 「%p」 를 쓰지 않는지 고정한다.

"""퍼센트 차이도 「%」 다(2026-11-01 사용자 결정 — 「퍼센트 표기할때 %p표기하지말고 %로만
반영(p를 빼라는 의미)」).

두 겹으로 본다. ① 글자 가드 — `app.py`·`app_pages/`·`src/`·`scripts/` 의 문자열 상수(독스트링은
화면에 나가지 않아 뺀다)와 `src/capa_simulation/guides/` 의 Markdown 에 「%p」 가 없고, f-string 이
`%` 서식 바로 뒤에 「p」 를 붙이지 않는다(`f"{x:.1%}p"`). 문서(README·AGENTS·HANDOFF·CLAUDE·
`docs/` — 런북 7장도)도 본다. ② 값으로만 정해지는 글 — 실적 지표의 Gap
단위(빼는 Gap 과 비율 Gap 이 셈은 다르고 단위는 둘 다 「%」), Chatbot 대본, 개조 일정 조건 오류문.
입장 화면 티저(`intro_overlay_assets/capa-teaser.html`)는 쇼케이스 원본의 복사본이라
(CLAUDE.md 「발표 자료는 저장소 밖에서 운영한다」) 가드 밖이다 — 그 「%p」 는 화면에 그리지 않는
표본 데이터 키다.
"""

from __future__ import annotations

import ast
import warnings
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from capa_simulation.components.availability_gap_panel import _CROSS_CHECK_FORMAT
from capa_simulation.components.home_figure_common import (
    _execution_delta_note,
    _execution_hover_note,
)
from capa_simulation.services.chatbot_samples import build_sample_answers
from capa_simulation.services.modification_schedule import (
    ScheduleConditions,
    ScheduleMonthInput,
    plan_modification_schedule,
)
from capa_simulation.services.performance_actuals import (
    ALL_METRICS,
    EFFICIENCY_METRIC,
    UPEH_METRIC,
    build_improvement_actions,
    build_monthly_actual_demo,
    build_priority_table,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = ("app.py", "app_pages", "src", "scripts")
GUIDES = PROJECT_ROOT / "src" / "capa_simulation" / "guides"
DOCUMENTS = ("README.md", "AGENTS.md", "HANDOFF.md", "CLAUDE.md", "docs")
POINT = "%p"


def _python_files() -> Iterator[Path]:
    for name in SOURCE_ROOTS:
        root = PROJECT_ROOT / name
        if root.is_file():
            yield root
        else:
            yield from sorted(root.rglob("*.py"))


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """독스트링 꼴(문 하나가 문자열 상수뿐인 식) — 화면에 나가지 않는 설명이다."""
    return {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }


def _suffix_after_percent(node: ast.JoinedStr) -> bool:
    """`f"{x:.1%}p"` — `%` 로 끝나는 서식 바로 뒤 글자가 「p」 로 시작한다."""
    for before, after in zip(node.values, node.values[1:], strict=False):
        if not (isinstance(before, ast.FormattedValue) and before.format_spec is not None):
            continue
        spec = before.format_spec
        tail = spec.values[-1] if isinstance(spec, ast.JoinedStr) and spec.values else None
        if not (isinstance(tail, ast.Constant) and str(tail.value).endswith("%")):
            continue
        if isinstance(after, ast.Constant) and str(after.value).startswith("p"):
            return True
    return False


def _offenders(path: Path) -> list[str]:
    with warnings.catch_warnings():
        # 옛 독스트링의 역슬래시 경고는 이 가드의 일이 아니다.
        warnings.simplefilter("ignore")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _docstring_nodes(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr) and _suffix_after_percent(node):
            found.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} f-string 「%」 뒤 「p」")
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and POINT in node.value
            and id(node) not in docstrings
        ):
            found.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} {node.value[:60]!r}")
    return found


def test_no_screen_string_writes_a_percent_point() -> None:
    """화면·알림·내려받기 머리·숫자 꼴(`"%+.1f%%p"`)·풍선 글자에 「%p」 가 없다."""
    offenders = [line for path in _python_files() for line in _offenders(path)]
    assert offenders == []


def test_the_guard_catches_both_spellings() -> None:
    """가드 자체 — 상수 속 「%p」 와 `%` 서식 뒤 「p」 둘 다 잡고, 독스트링은 넘긴다."""
    sample = (
        '"""설명 속 %p 는 넘긴다."""\nA = "%+.1f%%p"\nB = f"{1:.1%}p 회복"\nC = f"{1:.1%} 회복"\n'
    )
    tree = ast.parse(sample)
    docstrings = _docstring_nodes(tree)
    constants = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and POINT in node.value
        and id(node) not in docstrings
    ]
    flagged = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr) and _suffix_after_percent(node)
    ]
    assert constants == ["%+.1f%%p"]
    assert flagged == ["f'{1:.1%}p 회복'"]


def test_no_guide_writes_a_percent_point() -> None:
    """화면 Guide(따라하기 원고 `howto/` 포함)에도 「%p」 가 없다."""
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)}:{number}"
        for path in sorted(GUIDES.rglob("*.md"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if POINT in line
    ]
    assert offenders == []


def _document_paths() -> Iterator[Path]:
    for name in DOCUMENTS:
        path = PROJECT_ROOT / name
        if path.is_file():
            yield path
        else:
            yield from sorted(path.rglob("*.md"))


def _document_lines(path: Path) -> Iterator[tuple[int, str]]:
    """문서의 (줄 번호, 줄) — 런북 7장도 본다(2026-11-04 `202611041000` 판부터 그 기호 없이 다시
    썼다)."""
    yield from enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)


def test_no_document_writes_a_percent_point() -> None:
    """문서(README · AGENTS · HANDOFF · CLAUDE · `docs/`)에도 「%p」 가 없다 — 사용자 규칙은
    「어디에도」 다. 기호를 말할 때는 「퍼센트 포인트 기호」 로, 사용자 메모 인용은 기호 자리만
    「[퍼센트 포인트 기호]」 로 적는다. 런북 7장은 `202610271800` 판(그 배포 화면은 그 기호로
    그렸다)의 기록이라 한동안 뺐고, `202611041000` 판이 7장을 다시 쓰며 그 기호를 걷어 이제 함께
    본다(`docs/TODO.md` 3장 2026-11-01 「퍼센트 차이도 「%」」 ②)."""
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)}:{number}"
        for path in _document_paths()
        for number, line in _document_lines(path)
        if POINT in line
    ]
    assert offenders == []


def test_both_gap_kinds_read_percent_and_keep_their_own_arithmetic() -> None:
    """효율·수율(빼기)과 UPEH(비율) 의 Gap 은 셈이 다르고 단위 글자는 둘 다 「%」 다 — 셈의 갈림은
    `gap_formula` 글이 밝힌다."""
    assert {metric.gap_unit for metric in ALL_METRICS} == {"%"}
    assert EFFICIENCY_METRIC.gap_formula == "실적 효율 − 기준 효율"
    assert UPEH_METRIC.gap_formula == "실적 UPEH ÷ 기준 UPEH − 1"
    monthly = build_monthly_actual_demo()
    for metric in ALL_METRICS:
        priority = build_priority_table(monthly, metric, ["공정"])
        effects = list(build_improvement_actions(metric, priority)["기대 효과"])
        assert effects, metric.name
        assert all(text.endswith("% 회복") for text in effects), effects


def test_the_chatbot_script_writes_gaps_in_percent() -> None:
    """결론·근거·조건·한계 어디에도 「%p」 가 없고 효율 Gap 칸 이름은 `Gap (%)` 다."""
    for answer in build_sample_answers():
        texts = [answer.question, answer.conclusion, answer.evidence_caption]
        texts += [*answer.conditions, *answer.limits]
        texts += [str(value) for value in answer.evidence.to_numpy().ravel()]
        texts += [str(item.label) for item in answer.evidence_formats.values()]
        assert not [text for text in texts if POINT in text], answer.key
    shortfall = build_sample_answers()[0]
    assert shortfall.evidence_formats["Gap"].label == "Gap (%)"


def test_the_securement_adjustment_hovers_read_percent() -> None:
    """HOME 「확보율 보정」 풍선 — 「확보율 보정 −20.0%」(「%p」 아님)."""
    assert _execution_hover_note(-20.0, "비가동 3대") == "<br>확보율 보정 -20.0%<br>비고 비가동 3대"
    assert _execution_delta_note(5.0, "") == "<b>확보율 보정 +5.0%</b>"


def test_the_cross_check_column_reads_percent() -> None:
    """가용설비 현황 확보율 교차검증 차이 칸."""
    type_config = _CROSS_CHECK_FORMAT["확보율차이"].get("type_config")
    assert isinstance(type_config, dict) and type_config.get("format") == "%+.1f%%"


def test_the_modification_margin_error_reads_percent() -> None:
    """개조 일정 조건의 안전 여유 범위 오류문 — 「0~30% 여야 합니다」."""
    month = ScheduleMonthInput(month=202701, required=10.0, available=12.0, general_target=1.095)
    conditions = ScheduleConditions(
        units=1, days=5, cutoff_days=0, earliest=date(2027, 1, 1), margin=0.5
    )
    with pytest.raises(ValueError, match=r"^안전 여유는 0~30% 여야 합니다: 0\.5$"):
        plan_modification_schedule([month], conditions)
