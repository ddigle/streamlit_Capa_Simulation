# Purpose: 계산 멈춤 글 속 예시 키를 화면 꼴로 바꾸는 조각과 그 조각을 부르는 자리를 검증한다.

"""계산 멈춤 글의 예시 행(2026-11-11 입력 점검 검토 보드 F7 (나) — `components/stop_examples.py`).

서비스 글은 걸린 키를 dict 꼴로 싣고, 화면 글만 「YY.MM 공정 표시명 양산구분」 으로 바꾼다. 아래
그물은 그 꼴과 읽지 못한 예시를 그대로 두는 것, 그리고 계산 멈춤을 그리는 자리가 화면의 표시명을
넘기는지를 본다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.components.process_labels import process_labels_from_rules
from capa_simulation.components.stop_examples import examples_text, readable_examples
from capa_simulation.services.process_rename import PROCESS_RENAME_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LABELS = process_labels_from_rules(
    pd.DataFrame([("DEMO-SAW", "절단"), ("DEMO-A", "DEMO-B")], columns=list(PROCESS_RENAME_COLUMNS))
)
HEAD = "RQ_RUN_RATE의 CAPA_RUN_RATE 값이 빈 대당 Capa 기준이 있습니다: 2건, "


def test_an_example_reads_month_process_and_mass_type_in_that_order() -> None:
    """월은 `YY.MM`, 공정 · 양산구분이 차례로 앞이고 서비스 글의 키 차례는 따지지 않는다."""
    text = (
        HEAD + "예시 [{'양산구분': 'ER', '공정': 'DEMO-SAW', '생산계획년월': 202704}, "
        "{'생산계획년월': 202801, '공정': 'DEMO-SAW', '양산구분': '양산'}]"
    )

    assert readable_examples(text) == HEAD + "예시 27.04 DEMO-SAW ER · 28.01 DEMO-SAW 양산"
    assert readable_examples(text, LABELS) == HEAD + "예시 27.04 절단 ER · 28.01 절단 양산"


def test_a_display_name_equal_to_another_example_splits_with_the_original() -> None:
    """같은 예시 묶음의 다른 공정 원본과 표시명이 겹치면 「표시명 (원본)」 이다(공용 정책)."""
    records = [
        {"생산계획년월": 202601, "공정": "DEMO-A", "양산구분": "양산"},
        {"생산계획년월": 202601, "공정": "DEMO-B", "양산구분": "양산"},
    ]

    assert examples_text(records, LABELS) == "26.01 DEMO-B (DEMO-A) 양산 · 26.01 DEMO-B 양산"
    assert examples_text(records[:1], LABELS) == "26.01 DEMO-B 양산"


def test_other_keys_and_the_value_follow_in_service_order() -> None:
    """월 · 공정 · 양산구분 밖의 칸(제품정보 · 걸린 값)은 서비스 글 차례대로 값만 뒤에 잇는다.
    정수인 실수는 소수점 없이, 빈 값(None)은 건너뛴다. 공정만 든 예시(모듈수)는 공정 하나다."""
    text = (
        "예시 [{'생산계획년월': 202601, 'Area_Name': 'Main', '공정': 'DEMO-SAW', "
        "'STEP_SEQ': 10, '양산구분': '양산', '제품정보': 'DEMO-P', 'Stack': None, "
        "'편중률': 0.0}] / 예시 [{'공정': 'DEMO-A'}] / 예시 [{'생산계획년월': 202601, "
        "'공정': 'DEMO-SAW', 'CAPA_RUN_RATE': 'abc'}]"
    )

    assert readable_examples(text, LABELS) == (
        "예시 26.01 절단 양산 Main 10 DEMO-P 0 / 예시 DEMO-B / 예시 26.01 절단 abc"
    )


@pytest.mark.parametrize(
    "tail",
    [
        "예시 []",
        "예시 [202704]",
        "예시 ['P~Q~R']",
        "예시 [{'공정': nan}]",
        "예시 [{'공정': 'DEMO-A'}",
        "예시 없음",
    ],
    ids=["empty", "numbers", "names", "nan", "unclosed", "no-list"],
)
def test_an_example_it_cannot_read_stays_as_written(tail: str) -> None:
    """dict 목록으로 읽지 못하면 그 자리는 원문 그대로다 — 화면 글을 짓다 멈추지 않는다."""
    assert readable_examples(HEAD + tail, LABELS) == HEAD + tail


def test_a_bracket_inside_a_name_does_not_end_the_list_and_the_tail_stays() -> None:
    """이름 안의 `]` 는 목록의 끝이 아니다. 목록 뒤의 글(중복 키의 「— 그 가운데 …」)은 남는다."""
    text = (
        "RQ_VITAL의 연결 키가 중복되었습니다: 1건, 예시 [{'생산계획년월': 202601, "
        "'공정': 'A]B', '양산구분': '양산'}] — 그 가운데 1건은 원래 글자에서 앞뒤 공백만 다른 행"
    )

    assert readable_examples(text) == (
        "RQ_VITAL의 연결 키가 중복되었습니다: 1건, 예시 26.01 A]B 양산 — 그 가운데 1건은 원래 "
        "글자에서 앞뒤 공백만 다른 행"
    )


def test_a_month_that_is_not_yyyymm_keeps_its_digits() -> None:
    """월 형식 오류의 예시는 그 값 그대로다 — 고칠 칸을 가리킨다."""
    text = "예시 [{'생산계획년월': 2026131, '공정': 'DEMO-A'}, {'생산계획년월': 202613}]"

    assert readable_examples(text) == "예시 2026131 DEMO-A · 202613"


def test_every_list_in_a_save_warning_is_read_on_its_own() -> None:
    """저장 경고는 편집 뒤 · 편집 전 두 오류를 한 글에 싣는다 — 목록마다 따로 바꾼다."""
    text = (
        "편집 뒤 오류: " + HEAD + "예시 [{'생산계획년월': 202601, '공정': 'DEMO-A'}] / 편집 전 "
        "오류: " + HEAD + "예시 [{'생산계획년월': 202602, '공정': 'DEMO-B'}]"
    )

    assert readable_examples(text, LABELS) == (
        "편집 뒤 오류: " + HEAD + "예시 26.01 DEMO-B / 편집 전 오류: " + HEAD + "예시 26.02 DEMO-B"
    )


# ------------------------------------------------------------------ 부르는 자리


def _calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""


def _keywords(call: ast.Call) -> set[str]:
    return {keyword.arg for keyword in call.keywords if keyword.arg is not None}


def test_every_stopped_screen_passes_its_display_names() -> None:
    """계산 멈춤 알림을 그리는 화면(HOME · Static Capa · 산출 결과 · 표준 목표)은 그 화면의 표시명을
    알림과 나머지 멈춤 글(`bootstrap_error_message(labels=)`)에 함께 넘긴다 — 빠뜨리면 예시 행이
    원본 이름으로 남는다."""
    pages: dict[str, int] = {}
    for path in sorted((PROJECT_ROOT / "app_pages").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _name(node) == "calculation_stop_notice":
                assert "labels" in _keywords(node), f"{path.name}:{node.lineno}"
                pages[path.name] = pages.get(path.name, 0) + 1
            # `bootstrap_error_message(exc) if stop is None else stop.message` — 멈춘 화면의
            # 나머지 글.
            if (
                isinstance(node, ast.IfExp)
                and isinstance(node.orelse, ast.Attribute)
                and node.orelse.attr == "message"
                and isinstance(node.body, ast.Call)
                and _name(node.body) == "bootstrap_error_message"
            ):
                assert "labels" in _keywords(node.body), f"{path.name}:{node.lineno}"
    assert pages == {
        "calculation_result.py": 1,
        "home.py": 1,
        "standard_target_capa.py": 1,
        "static_capa.py": 1,
    }


def test_every_save_check_passes_display_names_to_its_warning() -> None:
    """저장 · 복제 · 공식 지정 · 월 머지 · 연도 Shift 경고는 화면의 표시명을 넘긴다."""
    verdicts = {"revision_save_verdict", "official_publish_verdict", "derived_save_verdict"}
    seen: dict[str, int] = {}
    for path in sorted((PROJECT_ROOT / "src/capa_simulation/components").glob("*.py")):
        if path.name == "capacity_gate.py":
            continue
        for call in _calls(path):
            if _name(call) in verdicts:
                assert "labels" in _keywords(call), f"{path.name}:{call.lineno}"
                seen[_name(call)] = seen.get(_name(call), 0) + 1
    assert seen == {
        "revision_save_verdict": 2,
        "official_publish_verdict": 1,
        "derived_save_verdict": 1,
    }
