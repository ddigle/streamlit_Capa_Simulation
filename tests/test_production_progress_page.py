# Purpose: 생산 진도 머리 화면이 데이터를 읽지 않고 모듈 화면 자리 하나만 그리는지 본다.

"""생산 진도 머리 — 보일 내용은 모듈이 맡는다(2026-11-03 사용자 「생산 진도 화면에는 일단 모듈에
스크립트를 넣으면 반영될 페이지 영역만 표시해둬」).

화면을 단독으로 띄워 DB 연결을 막은 채 머리말 아래에 점선 테두리 「모듈 화면 자리」 하나만 서는지,
옛 「준비 중」 한 줄이 없는지, 자리 색이 밝게·어둡게 테마 토큰을 따르는지 본다. 사이드바 상자 ·
조건 줄은 `tests/test_app_navigation.py` 가 본다.
"""

from pathlib import Path
from typing import Any

import duckdb
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.design import theme, tokens
from capa_simulation.navigation import PRODUCTION_PROGRESS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / PRODUCTION_PROGRESS.path
SLOT_TITLE = "모듈 화면 자리"
SLOT_TEXT = "모듈에 스크립트를 넣으면 이 자리에 표시됩니다."


def _run_without_databases(monkeypatch: pytest.MonkeyPatch) -> tuple[AppTest, list[Any]]:
    opened: list[Any] = []

    def refuse(*args: Any, **kwargs: Any) -> Any:
        opened.append(args)
        raise AssertionError("생산 진도 머리는 DB 를 열지 않는다")

    monkeypatch.setattr(duckdb, "connect", refuse)
    return AppTest.from_file(str(PAGE), default_timeout=60).run(), opened


def _slot_bodies(app: AppTest) -> list[str]:
    return [str(element.proto.body) for element in app.get("html")]


def test_the_head_draws_one_module_slot_without_opening_any_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, opened = _run_without_databases(monkeypatch)

    assert not app.exception, [element.message for element in app.exception]
    assert opened == []
    assert [title.value for title in app.title] == [PRODUCTION_PROGRESS.title]
    # 데이터를 읽지 않는 화면이다 — 위젯도 알림도 없고 자리 하나만 선다.
    assert not app.button and not app.selectbox and not app.toggle
    assert not app.info and not app.warning and not app.error
    bodies = _slot_bodies(app)
    assert len(bodies) == 1
    body = bodies[0]
    assert 'class="pp-module-slot"' in body
    assert f'aria-label="{SLOT_TITLE}"' in body
    assert f"<strong>{SLOT_TITLE}</strong>" in body
    assert f"<span>{SLOT_TEXT}</span>" in body
    assert "border:2px dashed" in body
    # 옛 빈 화면의 한 줄은 걷혔다.
    page_text = " ".join(
        [*(str(caption.value) for caption in app.caption), *(str(md.value) for md in app.markdown)]
    )
    assert "준비 중" not in page_text and "준비 중" not in body


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_slot_colours_follow_the_theme_tokens(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """자리 테두리 · 면 · 글 색은 그 회차 테마의 토큰이다 — 색 글자를 적지 않는다."""
    monkeypatch.setattr(theme, "current_mode", lambda: mode)
    app = AppTest.from_file(str(PAGE), default_timeout=60).run()

    assert not app.exception, [element.message for element in app.exception]
    (body,) = _slot_bodies(app)
    palette = tokens._PALETTES[mode]
    for name in ("BORDER_STRONG", "SURFACE_SUBTLE", "TEXT_MUTED", "TEXT"):
        assert str(palette[name]) in body, (mode, name)
