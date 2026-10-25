# Purpose: 팝오버·라벨이 바뀌는 확장 패널이 key 로 고정돼 위 알림이 오가도 닫히지 않는지 본다.

"""key 없는 팝오버·확장 패널은 **자리 순번**으로 같은 블록인지 가린다(AGENTS 9장 「조건부 알림」).

위에 조건부 알림(작업 알림·저장 오류)이 생기거나 빠지는 회차에 순번이 한 칸 밀려, 열어 둔 팝오버가
새 블록으로 서며 닫혔다 — 설비 시나리오 구획(2026-10-25 E2E)에서 알림 뒤 처음 누른 팝오버 안 확인
체크·Enter 가 팝오버를 닫았고, Space 저장 칸·버리기 팝오버도 저장 오류 아래에서 같은 꼴이었다.
라벨에 개수처럼 바뀌는 값을 넣은 확장 패널은 라벨이 바뀌는 회차에 새로 서며 접혔다.

모든 팝오버와 라벨이 글자 그대로가 아닌 확장 패널은 key 를 받는다. 브라우저의 펼침 상태는 AppTest 가
보지 못하므로 재현 시험은 블록 id(`st-key-…` — 브라우저가 같은 블록으로 잇는 이름)가 순번이 밀린
회차에도 같은지 본다.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from streamlit.proto.Block_pb2 import Block as BlockProto
from streamlit.testing.v1 import AppTest
from test_space_layout_editor_page import FAKE_APPLY_KEY, _open_editor

from capa_simulation.components import space_layout_editor
from capa_simulation.persistence.equipment_cache import clear_equipment_repository

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _sources() -> list[Path]:
    return [
        PROJECT_ROOT / "app.py",
        *sorted((PROJECT_ROOT / "app_pages").glob("*.py")),
        *sorted((PROJECT_ROOT / "src").rglob("*.py")),
    ]


def _calls(attr: str) -> Iterator[tuple[str, int, ast.Call]]:
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == attr
            ):
                yield path.relative_to(PROJECT_ROOT).as_posix(), node.lineno, node


def _has_key(call: ast.Call) -> bool:
    return any(keyword.arg == "key" for keyword in call.keywords)


def test_every_popover_has_a_key() -> None:
    """팝오버는 라벨이 같아도 자리로 이어진다 — 위 알림 하나에 열어 둔 팝오버가 닫힌다."""
    offenders = [f"{path}:{line}" for path, line, call in _calls("popover") if not _has_key(call)]

    assert not offenders, f"팝오버에 고정 key 를 주세요(AGENTS 9장 「조건부 알림」): {offenders}"


def test_every_expander_with_a_computed_label_has_a_key() -> None:
    """라벨이 글자 그대로가 아닌(개수·이름이 드는) 확장 패널은 라벨이 바뀌는 회차에 새로 서며
    접힌다."""
    offenders = []
    for path, line, call in _calls("expander"):
        label = call.args[0] if call.args else None
        if label is None:
            label = next((kw.value for kw in call.keywords if kw.arg == "label"), None)
        constant = isinstance(label, ast.Constant) and isinstance(label.value, str)
        if not constant and not _has_key(call):
            offenders.append(f"{path}:{line}")

    assert not offenders, f"라벨이 바뀌는 확장 패널에 key 를 주세요: {offenders}"


@pytest.fixture
def editor_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """브라우저 배치 편집기 대역(`tests/test_space_layout_editor_page.py` 와 같은 꼴)."""
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        calls.append(kwargs["data"])
        return SimpleNamespace(apply=st.session_state.pop(FAKE_APPLY_KEY, None))

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


def _popovers(app: AppTest) -> dict[str, tuple[str, tuple[int, ...]]]:
    """본문 팝오버 라벨 → (블록 id, 자리 순번 경로)."""
    found: dict[str, tuple[str, tuple[int, ...]]] = {}

    def walk(node: Any, path: tuple[int, ...]) -> None:
        proto = getattr(node, "proto", None)
        if isinstance(proto, BlockProto) and proto.HasField("popover"):
            found[proto.popover.label] = (proto.id, path)
        for index, child in getattr(node, "children", {}).items():
            walk(child, (*path, index))

    walk(app.main, ())
    return found


def test_the_space_save_popovers_survive_a_save_error_above_them(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """저장 안 한 배치 상자의 「저장 칸」·「버리기」 팝오버는 저장 오류가 위에 생기고 빠져도 같은
    블록이다.

    오류 한 줄이 상자 안 저장 줄을 한 칸 민다 — key 가 없으면 그 회차에 두 팝오버가 새로 서며
    닫혔다.
    """
    app, _ = _open_editor(tmp_path)
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [{"id": "EQ-01", "placed": True, "x": 40, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": None,
    }
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    before = _popovers(app)
    assert {"저장 칸", "버리기"} <= set(before)

    app.session_state["space_layout_save_error"] = "다른 사용자가 먼저 저장했습니다."
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert any("저장하지 못했습니다" in str(item.value) for item in app.error)
    shown = _popovers(app)

    app.run()
    assert not app.exception, [item.message for item in app.exception]
    after = _popovers(app)

    for label in ("저장 칸", "버리기"):
        block_id, path = before[label]
        assert block_id and block_id.endswith(
            {"저장 칸": "space_layout_fields_popover", "버리기": "space_layout_discard_popover"}[
                label
            ]
        )
        # 오류가 선 회차에는 자리가 밀린다 — 그래도 같은 id 라 브라우저가 같은 팝오버로 잇는다.
        assert shown[label][1] != path
        assert shown[label][0] == after[label][0] == block_id
    clear_equipment_repository()
