# Purpose: 생산 진도 머리와 샘플 페이지 셋이 데이터 없이 같은 꼴의 모듈 화면 자리만 그리는지 본다.

"""생산 진도 — 보일 내용은 모듈이 맡는다(2026-11-03 사용자 「생산 진도 화면에는 일단 모듈에
스크립트를 넣으면 반영될 페이지 영역만 표시해둬」). 하위 샘플 페이지 셋은 머리 화면 그대로 이름만
다르다(2026-11-04 검수 의견 prog-02 「샘플페이지 1,2,3 화면에 이대로 임시 반영」).

화면마다 단독으로 띄워 DB 연결을 막은 채 머리말 아래에 점선 테두리 「모듈 화면 자리」 하나만 서는지,
옛 「준비 중」 한 줄과 설명 줄이 없는지, 제목이 사이드바 라벨과 같은지, 넷의 자리 · 배지가 같은지,
자리 색이 밝게·어둡게 테마 토큰을 따르는지 본다. 사이드바 상자 · 조건 줄은
`tests/test_app_navigation.py` 가 본다.
"""

from pathlib import Path
from typing import Any

import duckdb
import pytest
from alert_marks import place_errors
from streamlit.testing.v1 import AppTest

from capa_simulation.components import module_slot
from capa_simulation.design import theme, tokens
from capa_simulation.navigation import (
    PRODUCTION_PROGRESS,
    PRODUCTION_PROGRESS_SUBPAGES,
    PageSpec,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES = (PRODUCTION_PROGRESS, *PRODUCTION_PROGRESS_SUBPAGES)
SLOT_TITLE = "모듈 화면 자리"
SLOT_TEXT = "모듈에 스크립트를 넣으면 이 자리에 표시됩니다."


def _run(spec: PageSpec) -> AppTest:
    return AppTest.from_file(str(PROJECT_ROOT / spec.path), default_timeout=60).run()


def _run_without_databases(
    spec: PageSpec, monkeypatch: pytest.MonkeyPatch
) -> tuple[AppTest, list[Any]]:
    opened: list[Any] = []

    def refuse(*args: Any, **kwargs: Any) -> Any:
        opened.append(args)
        raise AssertionError("생산 진도 화면은 DB 를 열지 않는다")

    monkeypatch.setattr(duckdb, "connect", refuse)
    return _run(spec), opened


def _slot_bodies(app: AppTest) -> list[str]:
    return [str(element.proto.body) for element in app.get("html")]


def _header_text(app: AppTest) -> str:
    return " ".join(
        [*(str(caption.value) for caption in app.caption), *(str(md.value) for md in app.markdown)]
    )


def test_the_group_holds_three_sample_pages_under_the_head() -> None:
    assert [spec.title for spec in PAGES] == ["생산 진도", *(f"샘플 페이지 {n}" for n in (1, 2, 3))]


@pytest.mark.parametrize("spec", PAGES, ids=lambda spec: Path(spec.path).stem)
def test_each_page_draws_one_module_slot_without_opening_any_database(
    spec: PageSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, opened = _run_without_databases(spec, monkeypatch)

    assert not app.exception, [element.message for element in app.exception]
    assert opened == []
    # 본문 제목은 사이드바 라벨과 같다.
    assert [title.value for title in app.title] == [spec.title]
    # 데이터를 읽지 않는 화면이다 — 위젯도 알림도 없고 자리 하나만 선다.
    assert not app.button and not app.selectbox and not app.toggle
    assert not app.info and not app.warning and not place_errors(app)
    bodies = _slot_bodies(app)
    assert len(bodies) == 1
    body = bodies[0]
    assert body == module_slot.module_slot_html()
    assert 'class="pp-module-slot"' in body
    assert f'aria-label="{SLOT_TITLE}"' in body
    assert f"<strong>{SLOT_TITLE}</strong>" in body
    assert f"<span>{SLOT_TEXT}</span>" in body
    assert "border:2px dashed" in body
    # 머리에는 배지뿐이다 — 이 화면이 무엇인지는 제목과 자리 글이 말한다.
    assert not app.caption
    header = _header_text(app)
    assert "화면 초안" in header
    # 옛 빈 화면의 한 줄은 걷혔다.
    assert "준비 중" not in header and "준비 중" not in body


def test_the_sample_pages_look_exactly_like_the_head_but_for_the_name() -> None:
    """샘플 셋은 머리 화면 「이대로」 다(prog-02) — 제목을 뺀 머리말 · 자리가 넷 모두 같다."""
    shapes = []
    for spec in PAGES:
        app = _run(spec)
        assert not app.exception, [element.message for element in app.exception]
        shapes.append((_header_text(app), tuple(_slot_bodies(app))))
    assert len(set(shapes)) == 1
    # 화면 파일은 제 이름 한 줄만 넘긴다 — 꼴은 `components/module_slot.py` 한 벌이다.
    for spec in PAGES:
        source = (PROJECT_ROOT / spec.path).read_text(encoding="utf-8")
        assert f'render_module_slot_page("{spec.title}")' in source, spec.path
        assert "st.html" not in source and "render_page_header" not in source, spec.path


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_slot_colours_follow_the_theme_tokens(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """자리 테두리 · 면 · 글 색은 그 회차 테마의 토큰이다 — 색 글자를 적지 않는다."""
    monkeypatch.setattr(theme, "current_mode", lambda: mode)
    app = _run(PRODUCTION_PROGRESS_SUBPAGES[0])

    assert not app.exception, [element.message for element in app.exception]
    (body,) = _slot_bodies(app)
    palette = tokens._PALETTES[mode]
    for name in ("BORDER_STRONG", "SURFACE_SUBTLE", "TEXT_MUTED", "TEXT"):
        assert str(palette[name]) in body, (mode, name)
