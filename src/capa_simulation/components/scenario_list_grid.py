# Purpose: 시나리오 목록 관리 브라우저 표 Components v2 를 세 자리에 그리고 오른쪽 칸 스펙을 둔다.

"""시나리오 관리 › Capa 시나리오 › 목록 관리의 표(설계 규칙 UI-CON-04 — 칸 조각은 설비 마스터 표와
공용).

**한 번 등록하고 세 자리에 다른 key 로 마운트한다** — 시나리오 표(`TABLE_KEY`) · 리비전 표
(`REVISIONS_KEY`) · 저장 전 변경(`CHANGES_KEY`). 브라우저 → 서버는 **상태 값 `outbox` 하나**이고
트리거는 없다(`STATE_NAMES` · `TRIGGER_NAMES`) — 트리거는 다음 트리거에 덮여 잃을 수 있어, 줄을
눌러 고르는 것도 출납으로 보낸다. 받은 값을 판정하는 것은 `services/scenario_list_edits.py` 다.

브라우저 쪽(HTML·CSS·JS)은 `scenario_list_grid_assets/` 의 파일이고 등록 글은 표 공용
조각(`grid_shared`) 뒤에 잇는다. 모듈을 읽을 때 등록하므로 이 모듈은 「목록 관리」 를 그리는
회차에서만 불러온다 — 시험은 `tests/conftest.py` 의 대역이 바꾼다. 세션 칸 · 탭 줄 판정은 등록이
없는 `scenario_list_state` 다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

import streamlit as st

from capa_simulation.components import grid_shared, scenario_list_state, side_panel

_ASSETS = Path(__file__).with_name("scenario_list_grid_assets")

TABLE_KEY: Final = scenario_list_state.TABLE_KEY
REVISIONS_KEY: Final = scenario_list_state.REVISIONS_KEY
CHANGES_KEY: Final = scenario_list_state.CHANGES_KEY

# 브라우저가 보내는 상태 값·트리거 이름(자산 시험이 JS 글자와 대조한다).
STATE_NAMES: Final = frozenset({"outbox"})
TRIGGER_NAMES: Final = frozenset[str]()

# 처음 폭은 줄의 40%(옛 시제품 측정 — 리비전 표 세 칸이 346px 에서 밀리고 416px 이면 든다). 한계는
# 설비 마스터와 같다.
LIST_SIDE: Final = side_panel.named_side_panel(
    "scenario_list",
    store="capa-scenario-list-side-v1",
    css_name="sls",
    default_share=0.4,
    default_offset_px=0,
)


def registered_js() -> str:
    """등록 JS — 표 공용 조각 뒤에 이 표의 파일."""
    return grid_shared.joined_assets(grid_shared.SHARED_JS, [_ASSETS / "list.js"])


def registered_css() -> str:
    """등록 CSS — 표 공용 조각 뒤에 이 표의 파일(같은 특이도면 뒤가 이긴다)."""
    return grid_shared.joined_assets(grid_shared.SHARED_CSS, [_ASSETS / "list.css"])


_GRID = st.components.v2.component(
    "capa_scenario_list_grid",
    html=(_ASSETS / "grid.html").read_text(encoding="utf-8"),
    css=registered_css(),
    js=registered_js(),
)


def render_list_mount(key: str, data: Mapping[str, Any], *, on_outbox: Callable[[], None]) -> None:
    """세 자리 가운데 하나를 그린다. 색은 등록 CSS 에 적지 않고 회차마다 팔레트로 넘긴다."""
    _GRID(
        key=key,
        data={**data, "palette": grid_shared.grid_palette()},
        on_outbox_change=on_outbox,
        width="stretch",
    )
