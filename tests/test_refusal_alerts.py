# Purpose: 남의 저장에 진 거부는 곁과 알림창 · Alarm 으로, 입력 탓 거부는 곁만 가는지 고정한다.

"""거부 알림의 두 갈래(2026-11-08 사용자 답 a1 「곁 + 알림창 · Alarm 으로 맞춘다 — 입력 탓
거부는 곁만 그대로」).

- **남의 저장에 진 거부** — 저장 자리는 `write_guard.note_profile_conflict` 로 충돌 표지를 적고 같은
  글을 `queue_refusal` 로 다음 회차의 곁 칸에 담는다. `queue_refusal` 이 그 글을 오류 사건(`FL-04`)
  으로도 담아 팝업을 닫아도 Alarm 에 기록이 남는다. 같은 거부의 둘째 누름(표지 그대로)은 다시 담지
  않는다.
- **곁만인 답** — 충돌 표지가 없는 글(입력 탓 거부 · 본 값 없음 · 「바뀐 것이 없습니다」)은 사건으로
  가지 않는다.
- **그물** — `queue_refusal` 을 부르는 함수는 같은 저장 이름으로 `note_profile_conflict` 도 부르거나
  (남의 저장 거부가 이 길을 탄다), 곁만인 답의 이름을 아래 허용 목록에 까닭과 함께 적는다. 새 저장
  자리가 충돌 표지 없이 거부를 담으면 그 거부는 알림창에 가지 않는다.
- **주요공정 프리셋** — `queue_refusal` 을 지나지 않는 저장이라 남의 저장 거부를 `queue_flash(kind=
  "error")` 로 담아 카드 알림 칸이 곁 + 알림창으로 낸다.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import capa_simulation.components.write_guard as write_guard
from capa_simulation import alerts
from capa_simulation.components.write_guard import (
    REFUSAL_ALERT_CODE,
    SEEN_MISSING_MESSAGE,
    note_profile_conflict,
    profile_conflict_marks,
    queue_refusal,
    take_refusal,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES = (PROJECT_ROOT / "src" / "capa_simulation", PROJECT_ROOT / "app_pages")
CONFLICT = (
    "다른 사용자가 먼저 판정 기준을 저장해 이번 저장은 반영하지 않았습니다(편집 시작 v1 · 지금 v2)."
)

# 충돌 표지 없이 `queue_refusal` 로 곁 칸에만 넘기는 답 — (파일, 함수, 저장 이름 인자) → 까닭.
BESIDE_ONLY: dict[tuple[str, str, str], str] = {
    (
        "src/capa_simulation/components/cutoff_management.py",
        "render_cutoff_management",
        "_REJECTED_NAME",
    ): "표 값 검증 거부(입력 탓) — 고칠 칸이 곁에 있어 곁만이다.",
    (
        "src/capa_simulation/components/cutoff_management.py",
        "render_cutoff_management",
        "_UNCHANGED_NAME",
    ): "「바뀐 것이 없습니다」 안내 — 거부가 아니다.",
}


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """두 모듈이 같은 세션 칸을 본다 — `write_guard.st` · `alerts.st` 대역."""
    state: dict[str, Any] = {}
    fake = SimpleNamespace(session_state=state)
    monkeypatch.setattr(write_guard, "st", fake)
    monkeypatch.setattr(alerts, "st", fake)
    return state


def _events(state: dict[str, Any]) -> list[dict[str, Any]]:
    outbox = state.get(alerts.OUTBOX_KEY)
    return [dict(note) for note in outbox] if isinstance(outbox, list) else []


def test_a_refusal_lost_to_another_save_goes_beside_and_to_the_alarm(
    session: dict[str, Any],
) -> None:
    """곁 칸 글은 그대로 남고, 같은 글이 오류 사건으로 담긴다(다음 앱 전체 회차의 알림 칸이
    보낸다)."""
    note_profile_conflict(profile_conflict_marks(), "threshold", CONFLICT)
    queue_refusal("threshold", CONFLICT)

    events = _events(session)
    assert [(note["code"], note["full"]) for note in events] == [(REFUSAL_ALERT_CODE, CONFLICT)]
    assert events[0]["level"] == "error"
    assert take_refusal("threshold") == CONFLICT


def test_the_second_press_of_the_same_refusal_does_not_alert_again(
    session: dict[str, Any],
) -> None:
    """같은 거부의 둘째 누름은 거부 글을 다시 담지만(곁) 사건은 첫 거부의 것 하나다. 새 충돌이면
    다시 보낸다."""
    marks = profile_conflict_marks()
    note_profile_conflict(marks, "threshold", CONFLICT)
    queue_refusal("threshold", CONFLICT)
    queue_refusal("threshold", CONFLICT)
    assert len(_events(session)) == 1

    marks["threshold"] = (CONFLICT, marks["threshold"][1] + 5.0)
    queue_refusal("threshold", CONFLICT)
    assert len(_events(session)) == 2


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("threshold", SEEN_MISSING_MESSAGE),
        ("equipment_process_cutoff_rejected", "Cutoff일수는 0 이상이어야 합니다."),
        ("equipment_process_cutoff_unchanged", "바뀐 것이 없어 저장하지 않았습니다."),
    ],
    ids=["본 값 없음", "입력 탓", "바뀐 것 없음"],
)
def test_refusals_without_a_conflict_mark_stay_beside_only(
    session: dict[str, Any], name: str, message: str
) -> None:
    """충돌 표지가 없거나 글이 다르면 사건으로 가지 않는다 — 곁 칸 글만 담긴다."""
    note_profile_conflict(profile_conflict_marks(), "threshold", CONFLICT)
    queue_refusal(name, message)

    assert _events(session) == []
    assert take_refusal(name) == message


def _calls(function: ast.AST, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    ]


def _refusal_sites() -> list[tuple[str, str, str, set[str]]]:
    """`queue_refusal(이름, 글)` 을 부르는 함수마다 (파일, 함수, 이름 인자 글, 그 함수가 충돌 표지를
    적는 이름 인자 글들). 글이 `SEEN_MISSING_MESSAGE` 인 부름은 뺀다(본 값 없음 — 곁만)."""
    found: list[tuple[str, str, str, set[str]]] = []
    for root in SOURCES:
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            if relative.endswith("components/write_guard.py"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for function in ast.walk(tree):
                if not isinstance(function, ast.FunctionDef):
                    continue
                refusals = _calls(function, "queue_refusal")
                if not refusals:
                    continue
                noted = {
                    ast.unparse(call.args[1])
                    for call in _calls(function, "note_profile_conflict")
                    if len(call.args) >= 3
                }
                for call in refusals:
                    if len(call.args) < 2 or ast.unparse(call.args[1]) == "SEEN_MISSING_MESSAGE":
                        continue
                    found.append((relative, function.name, ast.unparse(call.args[0]), noted))
    return found


def test_every_queued_refusal_rides_the_conflict_mark_or_is_listed_beside_only() -> None:
    """남의 저장 거부는 충돌 표지를 적은 같은 이름으로 담는다 — 그래야 `queue_refusal` 이 알림창 ·
    Alarm 으로 보낸다. 곁만인 답은 허용 목록에 까닭과 함께 적는다."""
    sites = _refusal_sites()
    assert sites, "queue_refusal 부름을 하나도 찾지 못했다 — 이 시험이 아무것도 보지 않는다"
    stray = [
        (path, function, name)
        for path, function, name, noted in sites
        if name not in noted and (path, function, name) not in BESIDE_ONLY
    ]
    assert stray == []


def test_every_beside_only_entry_is_still_there() -> None:
    """허용 목록의 자리가 사라졌으면 목록에서도 지운다."""
    present = {(path, function, name) for path, function, name, _noted in _refusal_sites()}
    assert set(BESIDE_ONLY) <= present
    assert all(reason.strip() for reason in BESIDE_ONLY.values())


def test_the_preset_refusal_lost_to_another_save_is_queued_as_an_error_flash() -> None:
    """주요공정 프리셋은 `queue_refusal` 을 지나지 않는다 — 남의 저장 거부(버전 충돌 갈래)는 곁에
    바로 그리지 않고 `queue_flash(…, kind="error")` 로 담아 앱 전체를 다시 돌린다(카드 알림 칸이
    곁 + 알림창으로 낸다). 이름 거부(입력 탓)는 곁에 바로 그린다."""
    path = PROJECT_ROOT / "src/capa_simulation/components/home_preference.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_reject_key_process_write"
    )
    conflict = next(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.If) and "ProfileVersionConflict" in ast.unparse(node.test)
    )
    body = "\n".join(ast.unparse(statement) for statement in conflict.body)
    assert "queue_flash(KEY_PROCESS_FLASH_KEY, message, kind='error')" in body
    assert "notice.error(message)" not in body
    assert "st.rerun(scope='app')" in body
    rest = "\n".join(ast.unparse(statement) for statement in function.body)
    assert "notice.error(_key_process_error_message(exc))" in rest
