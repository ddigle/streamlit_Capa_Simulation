# Purpose: 세션 상태를 바로 쓰는 자리 수의 기준선 — 줄면 낮추고 늘리지 않는다.

"""`tests/test_session_state_sites.py` 의 기준선(AGENTS.md 5장 42).

값은 화면 코드(`app.py` · `app_pages/` · `src/capa_simulation/`)에서 `.session_state` 속성
자리 수다(그 시험의 `session_state_sites` 가 센다). 늘리지 않는다 — 새 칸은
`session_slot.SessionSlot` 창구로 쓴다. 옛 자리를 창구로 옮겨 줄었으면 그 시험이 알려 주는 수로
낮춘다.
"""

SESSION_STATE_SITES = 1477
