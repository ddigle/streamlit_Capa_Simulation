# Purpose: 계산 멈춤 글 속 예시 키를 화면 꼴로 바꾸는 조각과 그 조각을 부르는 자리를 검증한다.

"""계산 멈춤 글의 예시 행(2026-11-11 입력 점검 검토 보드 F7 (나) — `components/stop_examples.py`).

서비스 글은 걸린 키를 dict 꼴로 싣고, 화면 글만 「YY.MM 공정 표시명 양산구분」 으로 바꾼다. 아래
그물은 그 꼴과 읽지 못한 예시를 그대로 두는 것, 그리고 계산 멈춤을 그리는 자리가 화면의 표시명을
넘기는지를 본다.
"""

from __future__ import annotations

import ast
from contextlib import nullcontext
from datetime import date, datetime
from pathlib import Path
from typing import cast

import pandas as pd
import pytest

import capa_simulation.components.auto_official_update_tab as auto_update_tab
import capa_simulation.components.process_labels as process_labels_module
import capa_simulation.components.required_shortening_panel as shortening_panel
import capa_simulation.components.shortening_source as shortening_source
import capa_simulation.components.space_shortening_view as space_shortening_view
import capa_simulation.components.stop_examples as stop_examples
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.persistence.equipment_cache as equipment_cache
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation import alerts
from capa_simulation.components.process_labels import ProcessLabels, process_labels_from_rules
from capa_simulation.components.stop_examples import (
    examples_text,
    markdown_examples,
    readable_examples,
)
from capa_simulation.page_bootstrap import PageContext
from capa_simulation.persistence.models import AutoOfficialUpdateRun
from capa_simulation.services.auto_official_update import STATUS_PUBLISH_SKIPPED
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


CLASH_RECORDS = [
    {"생산계획년월": 202601, "공정": "DEMO-A", "양산구분": "양산"},
    {"생산계획년월": 202601, "공정": "DEMO-B", "양산구분": "양산"},
]


def test_a_display_name_equal_to_another_example_splits_with_the_original() -> None:
    """같은 예시 묶음의 다른 공정 원본과 표시명이 겹치면 「표시명 (원본)」 이다(공용 정책). 실행
    문맥이 없으면(단위 시험) 보유 공정을 읽지 않아 묶음 안에서만 가른다."""
    assert examples_text(CLASH_RECORDS, LABELS) == "26.01 DEMO-B (DEMO-A) 양산 · 26.01 DEMO-B 양산"
    assert examples_text(CLASH_RECORDS[:1], LABELS) == "26.01 DEMO-B 양산"


def test_a_display_name_equal_to_an_owned_process_splits_outside_the_examples_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """표시명이 예시 묶음 밖 보유 공정(이 세션에 불러온 리비전의 `RQ_MODULE` 공정)의 원본 이름과
    겹쳐도 「표시명 (원본)」 이다 — DEMO-A → 「DEMO-B」 이고 원본 DEMO-B 가 따로 있으면 A 만 든
    예시도 「DEMO-B (DEMO-A)」(2026-11-11 다음 배포 물음 보드 「F7 뒤 ③」 (나), 선택 상자와 같은
    판정).
    겹치지 않는 표시명은 가르지 않고, 보유 공정 밖 예시 공정도 보이지 않는 글자 없이 그대로다."""
    monkeypatch.setattr(stop_examples, "_owned_processes", lambda: ("DEMO-B", "DEMO-SAW", "DEMO-C"))
    alone = CLASH_RECORDS[:1]
    others = [
        {"생산계획년월": 202704, "공정": "DEMO-SAW", "양산구분": "ER"},
        {"생산계획년월": 202704, "공정": "DEMO-OUT", "양산구분": "양산"},
    ]

    assert examples_text(alone, LABELS) == "26.01 DEMO-B (DEMO-A) 양산"
    assert (
        examples_text(alone, LABELS)
        == "26.01 " + LABELS.unique_format_func(["DEMO-A", "DEMO-B"])("DEMO-A") + " 양산"
    )
    assert examples_text(others, LABELS) == "27.04 절단 ER · 27.04 DEMO-OUT 양산"
    assert "\u2060" not in examples_text([*alone, *others], LABELS)
    assert markdown_examples(HEAD + "예시 " + repr(alone), LABELS) == (
        HEAD + "예시 26.01 DEMO\\-B \\(DEMO\\-A\\) 양산"
    )


def test_owned_processes_are_read_only_with_display_names_and_examples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """보유 공정은 표시명이 있고 예시가 있을 때만 읽는다 — 표시명이 없으면(규칙 0건 · 표시명 없이
    짓는 자리) 읽지 않고 글자도 원본 그대로다."""

    def refuse() -> tuple[str, ...]:
        raise AssertionError("보유 공정을 읽었습니다")

    monkeypatch.setattr(stop_examples, "_owned_processes", refuse)
    text = HEAD + "예시 " + repr(CLASH_RECORDS[:1])

    assert readable_examples(text) == HEAD + "예시 26.01 DEMO-A 양산"
    assert readable_examples(text, ProcessLabels()) == HEAD + "예시 26.01 DEMO-A 양산"
    assert readable_examples(HEAD + "예시 없음", LABELS) == HEAD + "예시 없음"


def test_owned_processes_come_from_the_loaded_revision_module_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """보유 공정은 이 세션에 불러온 리비전의 `RQ_MODULE` 공정이다(Admin 겹침 경고 `AD-06` 과 같은
    범위). 실행 문맥이 없거나 불러온 리비전이 없으면 빈 값이다."""
    assert stop_examples._owned_processes() == ()

    monkeypatch.setattr(stop_examples, "get_script_run_ctx", lambda **_kwargs: object())
    module = pd.DataFrame({"공정": ["DEMO-B", None, "DEMO-C", "DEMO-B"], "모듈수": [1, 1, 2, 1]})
    monkeypatch.setattr(
        reference_cache,
        "get_effective_reference_tables",
        lambda: {"RQ_MODULE": module},
    )
    assert stop_examples._owned_processes() == ("DEMO-B", "DEMO-C")

    def no_revision() -> dict[str, pd.DataFrame]:
        raise reference_cache.NoActiveRevision("없음")

    monkeypatch.setattr(reference_cache, "get_effective_reference_tables", no_revision)
    assert stop_examples._owned_processes() == ()


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


MARKED = process_labels_from_rules(
    pd.DataFrame([("DEMO-SAW", "TC~B~ *z* $x$")], columns=list(PROCESS_RENAME_COLUMNS))
)


def test_the_markdown_text_blocks_the_values_but_not_the_month() -> None:
    """마크다운 자리 글(`markdown_examples`)은 예시 칸 값 — 사람이 적은 공정 표시명 · 원본 이름 ·
    걸린 값 · 여섯 자리 달이 아닌 월 값 — 을 `literal_markdown` 으로 막는다. 표시명의 `*` · `$` 가
    기울임 · 수식이 되지 않는다(AGENTS 9장 — 표시명도 사람 글). 앱이 지은 `YY.MM` 은 막지 않고 글의
    물결표는 한 번만 막는다. 알림(평문으로 걷음)에는 적은 글자 그대로다."""
    text = (
        HEAD + "예시 [{'생산계획년월': 202704, '공정': 'DEMO-SAW', '양산구분': '양산'}, "
        "{'생산계획년월': '2026-13', '공정': 'DEMO-A', 'CAPA_RUN_RATE': 'a*b'}] — 10~12월"
    )

    shown = markdown_examples(text, MARKED)

    assert shown == (
        HEAD + "예시 27.04 TC\\~B\\~ \\*z\\* \\$x\\$ 양산 · 2026\\-13 DEMO\\-A a\\*b — 10\\~12월"
    )
    assert alerts.plain_text(shown) == (
        HEAD + "예시 27.04 TC~B~ *z* $x$ 양산 · 2026-13 DEMO-A a*b — 10~12월"
    )
    # 막지 않는 글(평문 자리)은 그대로다.
    assert readable_examples(text, MARKED) == (
        HEAD + "예시 27.04 TC~B~ *z* $x$ 양산 · 2026-13 DEMO-A a*b — 10~12월"
    )


def test_the_markdown_text_of_an_unread_example_only_blocks_tildes() -> None:
    """읽지 못한 예시는 원문 그대로이고 물결표만 막는다(바꾸기 전과 같은 꼴)."""
    assert markdown_examples(HEAD + "예시 ['P~Q~R']", MARKED) == HEAD + "예시 ['P\\~Q\\~R']"


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


# 시나리오 전체 기간 계산이 서는지 먼저 보는 호출 — 그 `try` 의 `except` 가 계산 멈춤 글을 받는다.
# 필요 단축 일정 · Space 「필요 단축」 은 수요(`load_shortening_demand`)와 달 범위
# (`get_required_month_span`)에서 멈춘다.
CAPACITY_CHECKS = frozenset(
    {
        "process_page_inputs",
        "check_scenario_capacity",
        "_route_choices",
        "load_shortening_demand",
        "get_required_month_span",
    }
)


def _labels_value(call: ast.Call) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == "labels"), None)


# 계산을 먼저 보지만 표시명을 넘기지 않는 자리 — Space 「필요 단축」 보기와 그 보기가 지나는
# 공용 길(`shortening_source`)은 원본 공정소분류만 쓴다(결정 D10 — 공정 표시명을 읽지 않는다,
# `test_process_label_boundaries`). 그 `except` 는 `labels=None` 을 밝혀 적는다. 공용 길은 원문이고
# 받는 화면이 같은 예외로 다시 짓는다 — 필요 단축 일정 패널은 표시명, Space 보기는 원본 공정명으로
# 예시 행만 화면 꼴(`example_rows=True` — 2026-11-11 다음 배포 물음 보드 「F7 뒤 ①」 (다),
# 아래 시험).
ORIGINAL_NAME_PLACES = frozenset({"shortening_source.py", "space_shortening_view.py"})
# 그 가운데 예시 행을 화면 꼴로 짓는 자리(원본 공정명).
EXAMPLE_ROW_PLACES = frozenset({"space_shortening_view.py"})


def _example_rows_value(call: ast.Call) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == "example_rows"), None)


def test_screens_that_check_the_calculation_first_pass_display_names_too() -> None:
    """계산 멈춤 알림을 쓰지 않고 멈춤 글을 그대로 싣는 화면(공정 Capa 상세 · 제약 시뮬레이션 ·
    재공 현황 · 가용설비 현황 비교 · 필요 단축 일정)도 계산을 먼저 보는 `try` 의 멈춤 글에 화면
    표시명을 넘긴다 — 예시 행이 같은 꼴이다(F7 (나) 「다른 계산 멈춤 자리도 함께」). 원문을 따로
    드는 글(알림 「원본 오류」 · 지문)은 `labels=None` 을 밝혀 적는다 — 한 `except` 에 표시명을
    넘기는 글이 적어도 하나다. Space 「필요 단축」 보기와 그 공용 길(`ORIGINAL_NAME_PLACES`)만 모든
    글이 `labels=None` 이다(결정 D10) — Space 보기(`EXAMPLE_ROW_PLACES`)는 예시 행만 화면 꼴
    (`example_rows=True`), 공용 길은 원문(받는 쪽이 `cause` 로 다시 짓는다)."""
    seen: set[str] = set()
    original: set[str] = set()
    roots = (PROJECT_ROOT / "app_pages", PROJECT_ROOT / "src/capa_simulation/components")
    for path in sorted(path for root in roots for path in root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            body = [
                call for part in node.body for call in ast.walk(part) if isinstance(call, ast.Call)
            ]
            if not any(_name(call) in CAPACITY_CHECKS for call in body):
                continue
            for handler in node.handlers:
                messages = [
                    call
                    for call in ast.walk(handler)
                    if isinstance(call, ast.Call) and _name(call) == "bootstrap_error_message"
                ]
                if not messages:
                    continue
                for call in messages:
                    assert "labels" in _keywords(call), f"{path.name}:{call.lineno}"
                if path.name in ORIGINAL_NAME_PLACES:
                    for call in messages:
                        value = _labels_value(call)
                        assert isinstance(value, ast.Constant) and value.value is None, (
                            f"{path.name}:{call.lineno}"
                        )
                        rows = _example_rows_value(call)
                        wanted = path.name in EXAMPLE_ROW_PLACES
                        assert (
                            isinstance(rows, ast.Constant) and rows.value is True
                            if wanted
                            else rows is None
                        ), f"{path.name}:{call.lineno}"
                    original.add(path.name)
                    continue
                named = [
                    call
                    for call in messages
                    if not (
                        isinstance(value := _labels_value(call), ast.Constant)
                        and value.value is None
                    )
                ]
                assert named, f"{path.name}:{handler.lineno}"
                seen.add(path.name)
    assert seen == {
        "available_equipment_status.py",
        "constraint_simulation.py",
        "process_capa_detail.py",
        "required_shortening.py",
        "wip_status.py",
    }
    assert original == ORIGINAL_NAME_PLACES


def test_the_shared_shortening_path_neither_reads_nor_takes_display_names() -> None:
    """공용 길(`shortening_source`)은 공정 표시명을 읽지도 받지도 않는다 — `labels` 라는 이름은
    멈춤 글을 원문으로 짓는 `labels=None` 한 자리뿐이다(인자 · 변수 · 다른 값의 `labels=` 가 없다).
    표시명 글은 받는 쪽이 `ShorteningStop.cause` 로 다시 짓는다(결정 D10 경계 —
    `test_process_label_boundaries` 는 표시명 모듈 이름만 본다)."""
    path = PROJECT_ROOT / "src/capa_simulation/components/shortening_source.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = [
        node.lineno
        for node in ast.walk(tree)
        if (isinstance(node, ast.arg) and node.arg == "labels")
        or (isinstance(node, ast.Name) and node.id == "labels")
    ]
    keywords = [
        keyword.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "labels"
    ]

    assert names == []
    assert len(keywords) == 1
    assert all(isinstance(value, ast.Constant) and value.value is None for value in keywords)


STOPPED_TEXT = HEAD + "예시 [{'생산계획년월': 202704, '공정': 'DEMO-SAW', '양산구분': '양산'}]"
DEMAND = shortening_source.ShorteningDemand(
    context=cast(PageContext, None), key=(1, "token", 1, 1), loader=pd.DataFrame
)
CUTOFF = pd.DataFrame({"공정": ["DEMO-SAW"]})


def _stop_the_month_range(monkeypatch: pytest.MonkeyPatch) -> None:
    def stopped(*_args: object, **_kwargs: object) -> tuple[int, int] | None:
        raise ValueError(STOPPED_TEXT)

    monkeypatch.setattr(simulation_cache, "get_required_month_span", stopped)


def _refuse_display_names(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse() -> ProcessLabels:
        raise AssertionError("Space 「필요 단축」 보기가 공정 표시명을 읽었습니다")

    monkeypatch.setattr(process_labels_module, "get_process_labels", refuse)


def test_the_month_range_stop_is_original_and_carries_its_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """달 범위를 다시 꺼내다 멈춘 글 — 공용 길은 원문으로 짓고 그 예외를 싣는다. 패널이 같은 예외로
    다시 지으면 화면 표시명 꼴(막아 실음)이다. 예외가 없는 멈춤은 그대로다."""
    _stop_the_month_range(monkeypatch)
    stop = shortening_source.shortening_month_options(DEMAND, CUTOFF)
    assert isinstance(stop, shortening_source.ShorteningStop)

    assert stop.kind == "scenario"
    assert stop.message == STOPPED_TEXT
    assert isinstance(stop.cause, ValueError) and str(stop.cause) == STOPPED_TEXT
    named = shortening_panel._named_stop(stop, LABELS)
    assert named.message == markdown_examples(STOPPED_TEXT, LABELS)
    assert "절단" in (named.message or "")
    assert (named.kind, named.reason, named.goto) == (stop.kind, stop.reason, stop.goto)
    # 다시 지은 멈춤은 본문 프래그먼트 인자로 남으므로 예외(traceback)를 쥐지 않는다.
    assert named.cause is None
    plain = shortening_source.ShorteningStop("info", "조회기간에 월이 없습니다.")
    assert shortening_panel._named_stop(plain, LABELS) is plain


def test_the_shortening_panel_names_the_month_range_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """필요 단축 일정 패널은 달 범위 멈춤 글을 그 화면의 공정 표시명으로 싣는다(F7 (나))."""
    _stop_the_month_range(monkeypatch)
    monkeypatch.setattr(process_labels_module, "get_process_labels", lambda: LABELS)
    empty = pd.DataFrame()
    stop = shortening_panel._prepare(
        equipment=empty,
        downtime=empty,
        baseline=empty,
        cutoff=CUTOFF,
        today=date(2026, 11, 11),
        context=cast(PageContext, object()),
        required_equipment=pd.DataFrame,
        required_equipment_key=(1, "token", 1, 1),
        scenario_error=None,
        controls=nullcontext(),
        database_path=None,
    )

    assert isinstance(stop, shortening_source.ShorteningStop)
    assert stop.kind == "scenario"
    assert stop.message == markdown_examples(STOPPED_TEXT, LABELS)
    assert stop.cause is None


def _space_layer_stop() -> shortening_source.ShorteningStop:
    empty = (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    stop = space_shortening_view.load_space_layer(
        saved=empty,
        sample=False,
        show_sample=False,
        has_snapshot=True,
        database_path="unused.duckdb",
        today=date(2026, 11, 11),
        level=1.1,
        unmerged=False,
    )
    assert isinstance(stop, shortening_source.ShorteningStop)
    return stop


# Space 「필요 단축」 보기의 멈춤 글 — 예시 행은 화면 꼴이고 공정은 원본 이름이다(표시명 「절단」 이
# 있어도 「DEMO-SAW」). 마크다운 글이라 칸 값은 막혀 있다.
SPACE_STOPPED_TEXT = markdown_examples(STOPPED_TEXT)


def test_the_space_shortening_demand_stop_reads_its_examples_with_original_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Space 「필요 단축」 보기의 수요 멈춤 글은 예시 행이 화면 꼴 「YY.MM 공정 양산구분」 이고
    공정은 공용 표시명이 있어도 원본 이름이다 — 그 길은 원본 공정소분류만 쓴다(결정 D10,
    2026-11-11 다음 배포 물음 보드 「F7 뒤 ①」 (다)). 표시명을 부르면 이 시험이 잡는다."""

    def stopped() -> shortening_source.ShorteningDemand:
        raise ValueError(STOPPED_TEXT)

    monkeypatch.setattr(shortening_source, "load_shortening_demand", stopped)
    _refuse_display_names(monkeypatch)
    stop = _space_layer_stop()

    assert stop.kind == "scenario"
    assert stop.message == SPACE_STOPPED_TEXT
    assert readable_examples(STOPPED_TEXT) == HEAD + "예시 27.04 DEMO-SAW 양산"
    assert stop.cause is None


def test_the_space_shortening_month_range_stop_reads_its_examples_with_original_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Space 「필요 단축」 보기의 달 범위 멈춤 글도 같은 꼴이다 — 공용 길이 원문으로 지어 실은
    예외로 다시 짓고 예외를 놓는다(필요 단축 일정 패널 `_named_stop` 과 짝 — 그 화면은 표시명)."""
    monkeypatch.setattr(shortening_source, "load_shortening_demand", lambda: DEMAND)
    monkeypatch.setattr(equipment_cache, "load_process_cutoff", lambda _path: CUTOFF)
    _stop_the_month_range(monkeypatch)
    _refuse_display_names(monkeypatch)
    stop = _space_layer_stop()

    assert stop.kind == "scenario"
    assert stop.message == SPACE_STOPPED_TEXT
    # 다시 지은 멈춤은 예외(traceback)를 쥐지 않는다.
    assert stop.cause is None
    plain = shortening_source.ShorteningStop("info", "조회기간에 월이 없습니다.")
    assert space_shortening_view._original_name_stop(plain) is plain


# 마크다운 자리(알림 전문 · 풍선 · 거부 상자 · 결과 알림)로 계산 오류 글을 싣는 함수 — 예시 행을
# `markdown_examples` 로 짓는다(칸 값을 막는다).
MARKDOWN_EXAMPLE_PLACES = {
    ("src/capa_simulation/page_bootstrap.py", "bootstrap_error_message"),
    ("src/capa_simulation/page_bootstrap.py", "calculation_stop_notice"),
    ("src/capa_simulation/components/capacity_gate.py", "_shown"),
    ("src/capa_simulation/components/scenario_input_check.py", "_subtitle"),
    ("src/capa_simulation/components/bigdataquery_registration.py", "_save_scenario"),
    ("src/capa_simulation/components/auto_official_update_tab.py", "_hold_run_result"),
}


def test_markdown_places_block_the_example_values() -> None:
    """계산 오류 글을 마크다운 자리에 싣는 함수는 `markdown_examples` 를 부른다. 막지 않는
    `readable_examples` 는 조각 자신과 평문 길(`bootstrap_error_message(markdown=False)`)뿐이다 —
    표시명의 `*` · `$` 가 꾸밈 · 수식이 되는 자리가 새로 생기지 않게."""
    bare: list[str] = []
    for path in sorted((PROJECT_ROOT / "src/capa_simulation").rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef):
                continue
            names = {_name(call) for call in ast.walk(function) if isinstance(call, ast.Call)}
            if (relative, function.name) in MARKDOWN_EXAMPLE_PLACES:
                assert "markdown_examples" in names, f"{relative}:{function.name}"
            if "readable_examples" in names and relative not in {
                "src/capa_simulation/components/stop_examples.py",
                "src/capa_simulation/page_bootstrap.py",
            }:
                bare.append(f"{relative}:{function.name}")
    assert bare == []


def _skipped_run(reason: str) -> AutoOfficialUpdateRun:
    now = datetime(2026, 11, 11, 7, 0)
    return AutoOfficialUpdateRun(
        run_id="run-stop",
        run_key="manual-stop",
        trigger_kind="MANUAL",
        run_date=now.date(),
        status=STATUS_PUBLISH_SKIPPED,
        stage="done",
        started_at=now,
        finished_at=now,
        keyword="PSM",
        threshold=0.8,
        settings_version=1,
        reason=reason,
    )


def test_the_run_now_result_reads_its_examples_with_display_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """자동 갱신 「지금 실행」 결과 알림의 사유가 계산 멈춤 글이면 예시 행은 화면 꼴(공정 표시명 —
    막아 실음)이다(F7 (나) 「다른 계산 멈춤 자리도 함께」). 회차 기록(`run.reason` — 기록 표
    「사유」 칸)은 원문이다."""
    reason = (
        "Capa 계산이 실패해 확보율을 판정하지 못했습니다 — 공식으로 지정하지 않았습니다. "
        + HEAD
        + "예시 [{'생산계획년월': 202704, '공정': 'DEMO-SAW', '양산구분': '양산'}]"
    )
    flashed: list[str] = []

    def capture(key: str, message: str, **_: object) -> None:
        flashed.append(message)

    def labels() -> ProcessLabels:
        return MARKED

    monkeypatch.setattr(auto_update_tab, "queue_flash", capture)
    monkeypatch.setattr(auto_update_tab, "get_process_labels", labels)
    run = _skipped_run(reason)

    auto_update_tab._hold_run_result(run)

    (message,) = flashed
    assert "{'" not in message
    assert message.endswith("예시 27.04 TC\\~B\\~ \\*z\\* \\$x\\$ 양산")
    assert alerts.plain_text(message).endswith("예시 27.04 TC~B~ *z* $x$ 양산")
    assert run.reason == reason


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
