# Purpose: 세션 상태를 바로 쓰는 자리 수가 기준선에서 늘지도 줄지도 않았는지 지킨다(새 칸은 창구로).

"""세션 상태 늘지 않게(AGENTS.md 5장 42 · `docs/TODO.md` 2장 「Streamlit 에 남는 조건 셋」 ③).

화면 코드(`app.py` · `app_pages/` · `src/capa_simulation/` — `source_sites.screen_files`)를
AST 로 훑어 `.session_state` 속성 자리(읽기 · 쓰기 · `.get` · `in` · 지우기 모두 한 자리씩 —
받는 이름은 가리지 않는다, `st.session_state` · `ctx.session_state`)를 센다. 글 · 주석은 AST 에
없어 세지 않는다.

- **늘면 실패** — 새 칸은 `capa_simulation.session_slot.SessionSlot` 으로 선언하고 그 메서드로 쓴다.
- **줄어도 실패** — 기준선(`tests/session_state_baseline.py`)을 알려 준 수로 낮춘다. 남는 틈을
  두면 그 틈만큼 다시 늘어도 모른다.
- 이름으로 들여오기(`from streamlit import session_state`)는 속성 자리가 없어 이 셈을 빠져나가므로
  막는다.

2026-11-17 다시 판정(저장소 밖 `js-recheck-1117/answer.md`)의 「1,433곳 · 114파일」 은 다른 셈법의
값이다(그 문서도 1,433 / 1,434 / 1,450 이 셈법 차이라고 적었다) — 이 시험의 수와 견주지 않는다.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from session_state_baseline import SESSION_STATE_SITES
from source_sites import relative, screen_files

ATTRIBUTE = "session_state"
WINDOW = "capa_simulation.session_slot.SessionSlot"


def count_sites(source: str) -> int:
    """소스 하나의 `.session_state` 속성 자리 수."""
    return sum(
        1
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and node.attr == ATTRIBUTE
    )


def session_state_sites(files: list[Path]) -> Counter[str]:
    """파일(저장소 상대 경로)마다 `.session_state` 속성 자리 수 — 없는 파일은 빠진다."""
    sites: Counter[str] = Counter()
    for path in files:
        count = count_sites(path.read_text(encoding="utf-8"))
        if count:
            sites[relative(path)] = count
    return sites


def test_direct_session_state_sites_match_the_baseline() -> None:
    sites = session_state_sites(screen_files())
    total = sum(sites.values())
    busiest = ", ".join(f"{name} {count}" for name, count in sites.most_common(5))
    assert total <= SESSION_STATE_SITES, (
        f"세션 상태를 바로 쓰는 자리가 늘었습니다 — 기준선 {SESSION_STATE_SITES} → {total}"
        f"({len(sites)}파일, 많은 곳: {busiest}). 새 칸은 {WINDOW} 로 선언하고 그 메서드로 "
        "읽고 씁니다(AGENTS.md 5장 42)."
    )
    assert total >= SESSION_STATE_SITES, (
        f"세션 상태를 바로 쓰는 자리가 줄었습니다 — {SESSION_STATE_SITES} → {total}. "
        f"tests/session_state_baseline.py 의 SESSION_STATE_SITES 를 {total} 으로 낮추세요."
    )


def test_session_state_is_not_imported_by_name() -> None:
    """`from streamlit import session_state` 는 속성 자리 없이 칸을 써 위 셈을 빠져나간다."""
    found = [
        relative(path)
        for path in screen_files()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").split(".")[0] == "streamlit"
        and any(alias.name == ATTRIBUTE for alias in node.names)
    ]
    assert found == [], f"session_state 를 이름으로 들여오지 않습니다 — {WINDOW} 를 씁니다: {found}"


def test_the_counter_sees_every_kind_of_site() -> None:
    """읽기 · 쓰기 · `.get` · `in` · `del` · 받는 이름이 달라도 한 자리씩 — 글 · 주석은 안 센다."""
    source = (
        "import streamlit as st\n"
        "# st.session_state 주석은 세지 않는다\n"
        'NOTE = "st.session_state"\n'
        'st.session_state["a"] = 1\n'
        'value = st.session_state.get("a")\n'
        'present = "a" in st.session_state\n'
        'del st.session_state["a"]\n'
        "def f(ctx):\n"
        "    return ctx.session_state\n"
    )
    assert count_sites(source) == 5
