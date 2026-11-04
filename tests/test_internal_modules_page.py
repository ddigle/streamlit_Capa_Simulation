# Purpose: 모듈 색인 화면이 켜진 모듈과 화면 링크·꺼짐 실패 수를 보이고 단독으로도 서는지 본다.

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation import module_registry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "internal_modules.py"
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "modules"


def test_without_modules_the_index_says_so_in_one_line() -> None:
    app = AppTest.from_file(str(PAGE)).run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    assert [title.value for title in app.title] == ["모듈"]
    assert not app.info
    assert "켜진 모듈이 없습니다." in [caption.value for caption in app.caption]
    assert not any("꺼짐" in caption.value for caption in app.caption)


def test_the_index_lists_switched_on_modules_and_counts_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """단독 실행(내비게이션 없음)에서도 선다 — 링크는 `render_page_link` 가 글로 물러선다
    (`st.page_link` 였으면 `StreamlitPageNotFoundError` 로 화면 전체가 죽는다)."""
    monkeypatch.setenv(module_registry.ROOT_ENV_VAR, str(FIXTURES))

    app = AppTest.from_file(str(PAGE)).run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not app.info
    heads = [str(markdown.value) for markdown in app.markdown if "담당" in str(markdown.value)]
    assert [head.split(" · ")[0] for head in heads] == [
        "**데모 모듈**",
        "**데모 고장**",
        "**데모 키**",
    ]
    assert "L0 Lab" in heads[0]
    captions = [caption.value for caption in app.caption]
    assert "사이드바에서 데모 화면 (구현중)" in captions
    assert "사이드바에서 키 데모 (구현중)" in captions
    # 수만 자리에 두고 까닭을 보는 곳은 풍선이다 — 길 안내 꼬리가 없다(설계 규칙 UI-TXT-03).
    (counts,) = [caption for caption in app.caption if caption.value.startswith("꺼짐 ")]
    assert counts.value == "꺼짐 1 · 실패 2"
    assert "「모듈 상태」" in str(counts.proto.help)
