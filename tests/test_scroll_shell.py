# Purpose: 가로 스크롤 셸이 세 화면의 기존 CSS 규칙을 그대로 만들어내는지 고정한다.

import re
from pathlib import Path

from capa_simulation.components.scroll_shell import scroll_shell_style

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _rules(css: str) -> list[str]:
    return [line.strip() for line in re.sub(r"<[^>]+>", "", css).split("\n") if line.strip()]


def test_hidden_scrollbar_shell_matches_the_table_components() -> None:
    """월별 표 2종이 쓰던 규칙. 네이티브 스크롤바를 숨기고 커스텀 스크롤바로 대체한다."""
    assert _rules(
        scroll_shell_style("demo_month", content_width_px=700, hide_native_scrollbar=True)
    ) == _rules(
        """
        .st-key-demo_month_scroll {
            overflow-x: auto;
            overflow-y: hidden;
            scrollbar-width: none !important;
            -ms-overflow-style: none;
        }
        .st-key-demo_month_scroll::-webkit-scrollbar {
            width: 0 !important;
            height: 0 !important;
            display: none !important;
        }
        .st-key-demo_month_canvas {
            width: 700px !important;
            min-width: 700px !important;
            max-width: none !important;
        }
        """
    )


def test_native_scrollbar_shell_matches_wip_status() -> None:
    """재공 현황만 네이티브 스크롤바를 그대로 쓴다. 숨김 규칙이 붙으면 안 된다."""
    css = scroll_shell_style(
        "wip_status_grid",
        content_width_px=430,
        hide_native_scrollbar=False,
        padding_bottom="0.5rem",
    )

    assert "webkit-scrollbar" not in css
    assert _rules(css) == _rules(
        """
        .st-key-wip_status_grid_scroll {
            overflow-x: auto;
            overflow-y: hidden;
            padding-bottom: 0.5rem;
        }
        .st-key-wip_status_grid_canvas {
            width: 430px !important;
            min-width: 430px !important;
            max-width: none !important;
        }
        """
    )


def test_padding_bottom_is_omitted_when_not_requested() -> None:
    """월별 표는 아래 여백이 없었다. 기본값으로 0 을 넣으면 화면이 달라진다."""
    assert "padding-bottom" not in scroll_shell_style(
        "demo_month", content_width_px=700, hide_native_scrollbar=True
    )


def _without_comments(source: str) -> str:
    """줄 끝 `#` 주석을 걷어낸 소스.

    이 규칙이 막는 것은 셸 CSS 를 손으로 복제하는 일이지, 왜 그러면 안 되는지 주석에
    적는 일이 아니다. 문자열 안의 `#` 는 색 리터럴뿐인데 그건 별도 규칙이 따로 막는다.
    """
    lines = [line.split("#", 1)[0] for line in source.splitlines()]
    return "\n".join(lines)


def test_scroll_shell_css_is_not_duplicated_in_pages_or_components() -> None:
    """셸 CSS 가 다시 복제되면 걸린다. 앞서 네 벌이 서로 갈라져 있었다."""
    owner = PROJECT_ROOT / "src/capa_simulation/components/scroll_shell.py"
    sources = [
        path
        for path in [
            *(PROJECT_ROOT / "app_pages").glob("*.py"),
            *(PROJECT_ROOT / "src/capa_simulation").rglob("*.py"),
        ]
        if path != owner
    ]

    # 주석은 뺀다. 이 규칙이 막는 것은 셸 CSS 를 손으로 복제하는 일이지, 왜 그러면 안
    # 되는지 주석에 적는 일이 아니다.
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sources
        if "overflow-x: auto" in _without_comments(path.read_text(encoding="utf-8"))
    ]

    assert not offenders, f"scroll_shell.horizontal_scroll_canvas 를 쓰세요: {offenders}"
