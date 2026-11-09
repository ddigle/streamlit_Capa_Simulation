# Purpose: 변경 메모 · 저장자 칸이 이름 줄 없이 칸 안 안내 글로 이름을 말하는지 본다.

"""변경 메모 · 저장자 칸 그물(설계 규칙 UI-CON-03 · PRC-01 — 2026-11-09 상단 띠 재고 · 사용자 지시).

저장 줄 · 저장 칸의 「변경 메모」 · 「저장자(선택)」 칸은 이름 줄(24.5px)을 걷고(`label_visibility=
"collapsed"` — 접근성 이름으로 남는다) 칸 안 흐린 글 「변경 메모 · 예: …」 · 「저장자(선택) · 예:
홍길동」 이 이름과 예를 함께 말한다(`saved_note.note_placeholder` · `equipment_save_fields.
SAVED_BY_PLACEHOLDER`). 화면 코드에서 라벨이 그 이름인 `text_input` · `text_area` 를 모두 찾아 이름
줄이 걷혔고 안내 글이 있는지 본다.

남긴 자리(`KEPT` — 까닭과 함께, 목록에 있어도 걷혀 있으면 통과한다):

- 사이드바 시나리오 팝업 「신규 리비전 저장」 폼의 변경 메모 — 이름 칸 「새 리비전명」 과 세로로
  짝을 이룬 팝업 폼이라 한 칸만 걷으면 꼴이 갈린다(페이지 상단 띠가 아니다).
- 시나리오 관리 설비 시나리오 탭 확인 창 둘(되돌리기 · 배치 차이 지우기)의 저장자 — 리비전명 ·
  「변경 메모(선택)」 칸과 세로 짝인 확인 창이다(그 화면 묶음 몫).
- Admin 표시순서 · Proc Rename 의 변경 메모 — 그 화면 묶음이 같은 꼴(「변경 메모 · 예: …」)로
  맞춘다.
"""

from __future__ import annotations

import ast

from source_sites import screen_calls, screen_files

from capa_simulation.components.equipment_save_fields import (
    SAVED_BY_LABEL,
    SAVED_BY_PLACEHOLDER,
)
from capa_simulation.components.saved_note import NOTE_LABEL, note_placeholder

KEPT: dict[tuple[str, str], str] = {
    ("src/capa_simulation/components/scenario_status.py", "_render_revision_save"): (
        "팝업 폼 — 「새 리비전명」 과 세로 짝"
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_restore"): (
        "설비 시나리오 확인 창 — 리비전명 · 메모 칸과 세로 짝"
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_clear_layout"): (
        "설비 시나리오 확인 창 — 메모 칸과 세로 짝"
    ),
    ("src/capa_simulation/components/display_order_management.py", "_render_direct_editor"): (
        "Admin 표시순서 — 그 화면 묶음이 같은 꼴로 맞춘다"
    ),
    ("src/capa_simulation/components/process_rename_management.py", "_render_direct_editor"): (
        "Admin Proc Rename — 그 화면 묶음이 같은 꼴로 맞춘다"
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
    assert SAVED_BY_PLACEHOLDER == "저장자(선택) · 예: 홍길동"


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
        elif isinstance(placeholder, ast.Constant) and not str(placeholder.value).startswith(
            f"{label} · 예: "
        ):
            wrong.append(f"{path}::{outer} {label} — 안내 글 꼴 {placeholder.value!r}")
    assert not wrong, wrong


def test_the_kept_sites_still_exist() -> None:
    """남긴 자리가 옮겨지면 목록도 고친다(목록에 있어도 걷혀 있으면 통과)."""
    seen = {(path, outer) for path, outer, _, _ in _sites()}
    assert set(KEPT) <= seen, set(KEPT) - seen
