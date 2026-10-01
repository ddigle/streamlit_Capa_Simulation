# Purpose: 헤더 툴바 iframe 의 내용이 회차·테마와 무관하게 같아 주입한 버튼이 살아 있는지 고정한다.

import pytest
from streamlit.elements.html import _html_only_style_tags

from capa_simulation.components import theme_toggle
from capa_simulation.components.page_guide import guide_toolbar_script
from capa_simulation.design import theme


def _render(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[object], list[str]]:
    """`st.iframe`·`st.html` 호출을 가로채 내용·높이·스타일을 모은다."""
    frames: list[str] = []
    heights: list[object] = []
    styles: list[str] = []

    def fake_iframe(src: str, **kwargs: object) -> None:
        frames.append(src)
        heights.append(kwargs.get("height"))

    monkeypatch.setattr(theme_toggle.st, "iframe", fake_iframe)
    monkeypatch.setattr(theme_toggle.st, "html", lambda body, **_kwargs: styles.append(body))
    return frames, heights, styles


def test_toolbar_iframe_is_identical_whatever_theme_python_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """내용이 바뀌면 Streamlit 이 iframe 을 새로 만들고, 옛 iframe 이 만든 테마·Guide 버튼의
    `onclick` 은 떨어져 나간 문서의 함수라 브라우저가 부르지 않는다(2026-10-01 브라우저 실측).
    파이썬이 푼 테마는 화면 이동 뒤 조회 인자가 빠지면 바뀔 수 있으므로 내용에 싣지 않는다.
    """
    # 테마는 스레드에 담긴다. 끝나면 되돌려 뒤 테스트의 색이 어두워지지 않게 한다.
    monkeypatch.setattr(theme._LOCAL, "mode", "light", raising=False)
    frames, _, _ = _render(monkeypatch)

    for mode in ("light", "dark"):
        monkeypatch.setattr(theme, "_read_client_mode", lambda mode=mode: mode)
        theme.begin_run()
        theme_toggle.render_theme_toggle(extra_scripts=(guide_toolbar_script(),))

    assert len(frames) == 2
    assert frames[0] == frames[1]


def test_toolbar_iframe_is_collapsed_to_zero_without_the_deprecated_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`st.iframe` 은 높이 0 을 오류로 막는다 — 1px 로 띄우고 CSS 로 접는다.

    폐기 예고가 회차마다 터미널에 찍히던 `components.v1.html` 로 돌아가지 않는다. 접는 규칙은
    스타일만 든 `st.html` 이라 본문 자리를 먹지 않고, iframe 내용에 든 버튼 id 로 그 iframe 만
    고른다 — id 를 바꾸고 규칙을 놓치면 본문이 1px 내려간다.
    """
    frames, heights, styles = _render(monkeypatch)

    theme_toggle.render_theme_toggle(extra_scripts=(guide_toolbar_script(),))

    assert heights == [theme_toggle._FRAME_HEIGHT_PX]
    assert isinstance(heights[0], int) and heights[0] > 0
    assert styles == [theme_toggle._COLLAPSE_STYLE]
    assert _html_only_style_tags(styles[0])
    assert f'srcdoc*="{theme_toggle._BUTTON_ID}"' in styles[0]
    assert theme_toggle._BUTTON_ID in frames[0]
    assert "components" not in vars(theme_toggle)
