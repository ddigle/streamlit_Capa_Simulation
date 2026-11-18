# Purpose: 세션 상태를 바로 쓰는 자리 수가 기준선에서 늘지도 줄지도 않았는지 지킨다(새 칸은 창구로).

"""세션 상태 늘지 않게(AGENTS.md 5장 42 · `docs/TODO.md` 2장 「Streamlit 에 남는 조건 셋」 ③).

화면 코드(`app.py` · `app_pages/` · `src/capa_simulation/` — `source_sites.screen_files`)를
AST 로 훑어 `.session_state` 속성 자리(읽기 · 쓰기 · `.get` · `in` · 지우기 모두 한 자리씩 —
받는 이름은 가리지 않는다, `st.session_state` · `ctx.session_state`)를 센다. 글 · 주석은 AST 에
없어 세지 않는다.

- **파일마다 센다** — 기준선(`tests/session_state_baseline.py`)은 파일 → 자리 수이고 거기 없는
  파일은 0곳이다. 합계 하나만 보면 한 변경 안에서 옛 자리를 걷고 새 파일에 자리를 더해도 수가 같아
  지나간다(2026-11-18 통합 검토).
- **늘면 실패** — 새 칸은 `capa_simulation.session_slot.SessionSlot` 으로 선언하고 그 메서드로 쓴다.
- **줄어도 실패** — 그 파일의 기준선을 알려 준 수로 낮춘다(0 이면 줄을 지운다). 남는 틈을 두면 그
  틈만큼 다시 늘어도 모른다.
- **세지 못하는 몫** — 키 글을 받는 도우미(`components/edit_grid` 의 `draft_of` · `discard_table` ·
  `collect_outbox` · `GridKeys`, `sidebar_status.remembered_expander` 등)에 키만 넘기는 칸은 속성
  자리가 그 도우미 안에 있어 부르는 쪽에서 세지 않는다 — `docs/TODO.md` 2장 같은 항목.
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
    grown = {
        name: (SESSION_STATE_SITES.get(name, 0), count)
        for name, count in sites.items()
        if count > SESSION_STATE_SITES.get(name, 0)
    }
    assert not grown, (
        "세션 상태를 바로 쓰는 자리가 늘었습니다(파일: 기준선 → 지금) — "
        + ", ".join(f"{name}: {before} → {now}" for name, (before, now) in sorted(grown.items()))
        + f". 새 칸은 {WINDOW} 로 선언하고 그 메서드로 읽고 씁니다(AGENTS.md 5장 42)."
    )
    shrunk = {
        name: (before, sites.get(name, 0))
        for name, before in SESSION_STATE_SITES.items()
        if sites.get(name, 0) < before
    }
    assert not shrunk, (
        "세션 상태를 바로 쓰는 자리가 줄었습니다 — tests/session_state_baseline.py 의 그 파일 줄을 "
        "지금 수로 낮추세요(0 이면 지웁니다): "
        + ", ".join(f"{name}: {before} → {now}" for name, (before, now) in sorted(shrunk.items()))
    )


def test_the_baseline_is_sorted_and_has_no_empty_line() -> None:
    """기준선은 파일 이름 차례이고 0곳 줄을 두지 않는다(없으면 0곳)."""
    assert list(SESSION_STATE_SITES) == sorted(SESSION_STATE_SITES)
    assert all(count > 0 for count in SESSION_STATE_SITES.values())


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
