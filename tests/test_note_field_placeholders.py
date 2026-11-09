# Purpose: 변경 메모 · 저장자 칸이 이름 줄 없이 칸 안 안내 글로 이름을 말하는지 본다.

"""변경 메모 · 저장자 칸 그물(설계 규칙 UI-TXT-01 예외 · PRC-01 — 2026-11-09 상단 띠 재고).

저장 줄 · 저장 칸의 「변경 메모」 · 「저장자(선택)」 칸은 이름 줄(24.5px)을 걷고
(`label_visibility="collapsed"` — 접근성 이름으로 남는다) 칸 안 흐린 글 「변경 메모 · 예: …」 ·
「저장자 · 예: 홍길동」 이 이름과 예를 함께 말한다 — 꼴은 「<칸 이름> · 예: <예>」 하나이고 한
함수가 짓는다(`saved_note.field_placeholder` — `note_placeholder` ·
`equipment_save_fields.SAVED_BY_PLACEHOLDER`).
화면 코드에서 라벨이 그 이름인 `text_input` · `text_area` 를 모두 찾아 이름 줄이 걷혔고 안내 글이
있는지, 안내 글을 글 상수로 손수 짓지 않는지 본다.

남긴 자리(`KEPT` — 까닭과 함께, 목록에 있어도 걷혀 있으면 통과한다):

- 사이드바 시나리오 팝업 「신규 리비전 저장」 폼의 변경 메모 — 이름 칸 「새 리비전명」 과 세로로
  짝을 이룬 팝업 폼이라 한 칸만 걷으면 꼴이 갈린다(페이지 상단 띠가 아니다). 따라하기 가이드 원고
  `guides/howto/lob/plan.json` 이 이 칸을 보이는 라벨 「변경 메모」 로 찾아 채운다(`fill label` ·
  `named:WIDGET(변경 메모)` — `scripts/page_guide_helpers.js` 는 보이는 `stWidgetLabel` 글로
  찾는다) — 걷으려면 원고의 찾기를 aria-label · key 로 바꾸는 일을 같은 변경에 둔다.
- 시나리오 관리 설비 시나리오 탭 확인 창 둘(되돌리기 · 배치 차이 지우기)의 저장자 — 리비전명 ·
  「변경 메모(선택)」 칸과 세로 짝인 확인 창이다.
"""

from __future__ import annotations

import ast

from source_sites import screen_calls, screen_files

from capa_simulation.components.equipment_save_fields import (
    SAVED_BY_LABEL,
    SAVED_BY_PLACEHOLDER,
)
from capa_simulation.components.saved_note import NOTE_LABEL, field_placeholder, note_placeholder

KEPT: dict[tuple[str, str], str] = {
    ("src/capa_simulation/components/scenario_status.py", "_render_revision_save"): (
        "팝업 폼 — 「새 리비전명」 과 세로 짝 · 따라하기 가이드 lob 원고가 보이는 라벨로 채움"
        "(걷으려면 plan.json · page_guide_helpers.js 를 함께)"
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_restore"): (
        "설비 시나리오 확인 창 — 리비전명 · 메모 칸과 세로 짝"
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_clear_layout"): (
        "설비 시나리오 확인 창 — 메모 칸과 세로 짝"
    ),
}


def _label(call: ast.Call) -> str | None:
    """첫 인자가 글 상수 「변경 메모」 · 「저장자(선택)」 이거나 그 이름 상수면 그 글."""
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and first.value in (NOTE_LABEL, SAVED_BY_LABEL):
        return str(first.value)
    if isinstance(first, ast.Name) and first.id in ("NOTE_LABEL", "SAVED_BY_LABEL"):
        return NOTE_LABEL if first.id == "NOTE_LABEL" else SAVED_BY_LABEL
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def _sites() -> list[tuple[str, str, ast.Call, str]]:
    found = []
    for path, outer, _, _, call in screen_calls(screen_files()):
        if not isinstance(call.func, ast.Attribute) or call.func.attr not in (
            "text_input",
            "text_area",
        ):
            continue
        label = _label(call)
        if label is not None:
            found.append((path, outer, call, label))
    return found


def test_the_placeholders_name_the_field_and_give_an_example() -> None:
    assert note_placeholder("26.07 PM 반영") == "변경 메모 · 예: 26.07 PM 반영"
    assert SAVED_BY_PLACEHOLDER == "저장자 · 예: 홍길동" == field_placeholder("저장자", "홍길동")


def test_every_memo_and_saver_field_has_no_label_row_and_names_itself_inside() -> None:
    sites = _sites()
    # HOME 설정 셋 · 과거 구간 · 설비 마스터 저장 · 사이드바 설비 팝업 저장 · Space 배치 저장 · 입력
    # 비가동 둘 · 저장자 부품 둘(설비 저장 세 자리가 같이 쓴다)이 적어도 선다.
    assert len(sites) >= 10, sites
    wrong = []
    for path, outer, call, label in sites:
        if (path, outer) in KEPT:
            continue
        hidden = _keyword(call, "label_visibility")
        placeholder = _keyword(call, "placeholder")
        if not (isinstance(hidden, ast.Constant) and hidden.value == "collapsed"):
            wrong.append(f"{path}::{outer} {label} — 이름 줄")
        if placeholder is None:
            wrong.append(f"{path}::{outer} {label} — 안내 글 없음")
        elif isinstance(placeholder, ast.Constant):
            wrong.append(f"{path}::{outer} {label} — 안내 글을 손수 지음 {placeholder.value!r}")
    assert not wrong, wrong


def test_the_kept_sites_still_exist() -> None:
    """남긴 자리가 옮겨지면 목록도 고친다(목록에 있어도 걷혀 있으면 통과)."""
    seen = {(path, outer) for path, outer, _, _ in _sites()}
    assert set(KEPT) <= seen, set(KEPT) - seen


def test_the_memo_the_guide_fills_by_its_label_keeps_the_label_row() -> None:
    """따라하기 가이드 lob 원고가 보이는 라벨 「변경 메모」 로 찾아 채우는 칸(사이드바 「신규 리비전
    저장」 팝업)은 이름 줄을 남긴다 — 걷으면 가이드 생성이 그 칸을 찾지 못한다. 원고가 그 찾기를
    다른 것(aria-label · key)으로 바꾸면 이 시험도 함께 고친다."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    plan = (root / "src/capa_simulation/guides/howto/lob/plan.json").read_text(encoding="utf-8")
    assert f'"label": "{NOTE_LABEL}"' in plan
    site = ("src/capa_simulation/components/scenario_status.py", "_render_revision_save")
    calls = [call for path, outer, call, _ in _sites() if (path, outer) == site]
    assert calls
    for call in calls:
        hidden = _keyword(call, "label_visibility")
        assert not (isinstance(hidden, ast.Constant) and hidden.value == "collapsed")
