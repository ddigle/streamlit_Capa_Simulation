# Purpose: 헤더 툴바 iframe 의 내용이 회차·테마와 무관하게 같아 주입한 버튼이 살아 있는지 고정한다.

import pytest

from capa_simulation.components import theme_toggle
from capa_simulation.components.page_guide import guide_toolbar_script
from capa_simulation.design import theme


def test_toolbar_iframe_is_identical_whatever_theme_python_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """내용이 바뀌면 Streamlit 이 iframe 을 새로 만들고, 옛 iframe 이 만든 테마·Guide 버튼의
    `onclick` 은 떨어져 나간 문서의 함수라 브라우저가 부르지 않는다(2026-10-01 브라우저 실측).
    파이썬이 푼 테마는 화면 이동 뒤 조회 인자가 빠지면 바뀔 수 있으므로 내용에 싣지 않는다.
    """
    rendered: list[str] = []
    # 테마는 스레드에 담긴다. 끝나면 되돌려 뒤 테스트의 색이 어두워지지 않게 한다.
    monkeypatch.setattr(theme._LOCAL, "mode", "light", raising=False)
    monkeypatch.setattr(
        theme_toggle.components,
        "html",
        lambda html, **_kwargs: rendered.append(html),
    )

    for mode in ("light", "dark"):
        monkeypatch.setattr(theme, "_read_client_mode", lambda mode=mode: mode)
        theme.begin_run()
        theme_toggle.render_theme_toggle(extra_scripts=(guide_toolbar_script(),))

    assert len(rendered) == 2
    assert rendered[0] == rendered[1]
