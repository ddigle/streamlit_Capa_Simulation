# Purpose: 편집기 구역 끄개(`CAPA_EDITOR_SCOPES=off`)가 편집기 넷의 묶음 쉼을 모두
# `ORDINARY_SEND_MS` 로 두는지 본다.

"""편집기 묶음 쉼(`grid_shared.batch_ms`)과 편집기 구역 끄개(`settings.editor_scopes_enabled`).

끄개가 꺼지면 범용 편집 그리드 · 설비 마스터 표 · 시나리오 목록 · Space 「호기 정보」 창 넷의 쉼이
모두 `grid_shared.ORDINARY_SEND_MS`(0.3초 — 구역 없이 칸마다 앱 전체 회차로 돌 때의 값)다. 개발 ·
측정 사본의 실행 줄 덮어쓰기(`CAPA_DEV_BATCH_MS`)보다 먼저 본다. 켬(기본)이면 편집기마다 결정값이고
덮어쓰기도 그대로다(그 몫의 자세한 갈래는 편집기마다 시험이 본다).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from capa_simulation import settings
from capa_simulation.components import (
    edit_grid,
    grid_shared,
    scenario_list_grid,
    space_layout_editor,
)
from capa_simulation.components import equipment_master_grid as emg

SPACE_MODULE = Path(space_layout_editor.__file__).read_text(encoding="utf-8")
EDITORS = ("edit_grid", "equipment_master_grid", "scenario_list_grid", "space_layout_editor")


def _sends(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """편집기 넷이 data 로 넘기는 쉼(ms). Space 「호기 정보」 창은 편집기를 세우려면 배치 · 설비
    재료가 많이 들어, 그 data 줄이 `batch_ms(SHEET_SEND_MS)` 를 거치는지는 아래 시험이 소스로
    본다."""
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(scenario_list_grid, "_GRID", lambda **kwargs: sent.append(kwargs["data"]))
    scenario_list_grid.render_list_mount(
        scenario_list_grid.TABLE_KEY, {"mode": "scenarios"}, on_outbox=lambda: None
    )
    return {
        "edit_grid": int(edit_grid.shell_limits()["sendMs"]),
        "equipment_master_grid": int(emg._with_palette({})["sendMs"]),
        "scenario_list_grid": int(sent[-1]["sendMs"]),
        "space_layout_editor": grid_shared.batch_ms(space_layout_editor.SHEET_SEND_MS),
    }


def test_scopes_off_sends_every_editor_at_the_ordinary_pause_even_with_a_dev_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """켬(기본)이면 편집기마다 결정값이고 개발 실행 줄 덮어쓰기가 먹는다. 끄개를 끄면 넷 모두
    `ORDINARY_SEND_MS`(300)이고 덮어쓰기가 있어도 무시한다."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv(grid_shared.BATCH_OVERRIDE_ENV, raising=False)
    assert _sends(monkeypatch) == {
        "edit_grid": edit_grid.SEND_MS,
        "equipment_master_grid": emg.SEND_MS,
        "scenario_list_grid": scenario_list_grid.LIST_SEND_MS,
        "space_layout_editor": space_layout_editor.SHEET_SEND_MS,
    }
    monkeypatch.setenv(grid_shared.BATCH_OVERRIDE_ENV, "1500")
    assert _sends(monkeypatch) == dict.fromkeys(EDITORS, 1500), "켬이면 개발 덮어쓰기"

    monkeypatch.setenv(settings.EDITOR_SCOPES_ENV, " Off ")
    assert grid_shared.ORDINARY_SEND_MS == 300
    assert _sends(monkeypatch) == dict.fromkeys(EDITORS, grid_shared.ORDINARY_SEND_MS)
    monkeypatch.delenv(grid_shared.BATCH_OVERRIDE_ENV)
    assert _sends(monkeypatch) == dict.fromkeys(EDITORS, grid_shared.ORDINARY_SEND_MS)
    # Space 「호기 정보」 창 쉼도 같은 길(`batch_ms`)로 data 에 실린다.
    assert '"sheetSendMs": grid_shared.batch_ms(SHEET_SEND_MS),' in SPACE_MODULE
