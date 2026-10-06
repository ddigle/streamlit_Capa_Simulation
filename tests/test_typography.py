# Purpose: 앱 서체 스타일이 부분 글꼴을 정적 서빙 상대 경로로만 부르고 정한 자리에만 거는지 본다.

from __future__ import annotations

import re
from pathlib import Path

import capa_simulation.components.typography as typography
from capa_simulation.design import tokens

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = PROJECT_ROOT / typography.FONT_DIR
STYLE = typography.TYPOGRAPHY_STYLE


def test_subset_fonts_are_woff2_in_the_static_folder_with_their_license() -> None:
    """사내 PC 는 외부 글꼴 서버에 못 나간다. 글꼴은 `app.py` 옆 `static/` 에 있어야 서빙된다."""
    assert FONT_DIR.parent == PROJECT_ROOT / "static"
    assert (PROJECT_ROOT / "app.py").is_file()
    for name in typography.FONT_FILES.values():
        data = (FONT_DIR / name).read_bytes()
        assert data[:4] == b"wOF2", name
        # 인쇄 가능한 ASCII 부분 글꼴은 수 KB 다. 커졌으면 전체 글꼴을 잘못 받은 것이다.
        assert len(data) < 32_000, (name, len(data))
    license_text = (FONT_DIR / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL Open Font License, Version 1.1" in license_text
    assert "Reserved Font Name" not in license_text.splitlines()[0]


def test_subset_is_printable_ascii_and_matches_the_unicode_range() -> None:
    assert typography.FONT_SUBSET_TEXT == "".join(chr(code) for code in range(0x20, 0x7F))
    match = re.fullmatch(r"U\+([0-9A-F]+)-([0-9A-F]+)", typography.UNICODE_RANGE)
    assert match
    low, high = match.groups()
    assert (chr(int(low, 16)), chr(int(high, 16))) == (" ", "~")
    # 페이지 제목에 쓰는 영문·숫자가 다 들어 있다(한글은 스택의 다음 글꼴로 떨어진다).
    assert set("Capa LOB Summary Static Dynamic 0123456789.%") <= set(typography.FONT_SUBSET_TEXT)


def test_fonts_load_only_from_the_relative_static_path() -> None:
    """외부 글꼴 서버를 부르지 않는다. 주소는 상대 경로라 접두 경로(사내 WebIDE
    `/proxy/<포트>/`)에서도 맞는다."""
    urls = re.findall(r'url\("([^"]+)"\)', STYLE)

    assert urls == [typography.FONT_URL_PREFIX + name for name in typography.FONT_FILES.values()]
    for url in urls:
        assert url.startswith("app/static/fonts/"), url
        assert not url.startswith(("/", "http:", "https:", "//", "data:")), url
    for banned in ("googleapis", "gstatic", "@import", "http"):
        assert banned not in STYLE, banned
    assert STYLE.count("font-display: swap") == len(typography.FONT_FILES)
    assert STYLE.count(f"unicode-range: {typography.UNICODE_RANGE}") == len(typography.FONT_FILES)


def test_static_serving_is_enabled_in_the_app_config() -> None:
    """끄면 `app/static/…` 이 404 라 세 자리가 시스템 글꼴로 떨어진다(화면은 선다)."""
    text = (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    server = re.search(r"^\[server\]\n(.*?)(?=^\[)", text, flags=re.MULTILINE | re.DOTALL)

    assert server, "config.toml 에 [server] 블록이 없습니다."
    assert re.search(r"^enableStaticServing = true$", server.group(1), flags=re.MULTILINE)
    assert "googleapis" not in text


def test_family_name_is_its_own_and_the_stack_falls_back_to_the_body_font() -> None:
    """입장 화면 JS 가 등록하는 이름과 섞이면 굵기·폭이 다른 두 벌이 한 이름 아래 겹친다."""
    assert typography.DISPLAY_FAMILY not in ("CapaIntroDisplay", "CapaIntroNumber")
    assert tokens.FONT_FAMILY_DISPLAY == f"{typography.DISPLAY_FAMILY}, {tokens.FONT_FAMILY}"
    # 인라인 `style="..."` 에 넣을 수 있게 큰따옴표가 없다.
    assert '"' not in tokens.FONT_FAMILY_DISPLAY


def _rule(selector_part: str) -> str:
    """선택자에 `selector_part` 가 든 규칙의 본문."""
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", STYLE):
        if selector_part in selectors and "@font-face" not in selectors:
            return str(body)
    raise AssertionError(selector_part)


def test_rules_reach_only_the_three_places_inside_the_main_area() -> None:
    """페이지 제목 800, 상자 제목 700, 큰 숫자 700 + 숫자 폭 고정. 사이드바·표·차트는 그대로다."""
    title = _rule('[data-testid="stMain"] h1')
    assert "font-weight: 800" in title and tokens.FONT_FAMILY_DISPLAY in title

    box = _rule('[data-testid="stMain"] h4')
    assert "font-weight: 700" in box
    assert '[role="heading"][aria-level="2"]' in STYLE

    figure = _rule('[data-testid="stMetricValue"]')
    assert "font-weight: 700" in figure and "tabular-nums" in figure
    assert f".{typography.FIGURE_CLASS}" in STYLE

    for selectors, _body in re.findall(r"([^{}]+)\{([^{}]*)\}", STYLE):
        if "@font-face" in selectors:
            continue
        for selector in selectors.split(","):
            selector = selector.strip().removeprefix("<style>").strip()
            assert selector.startswith('[data-testid="stMain"]'), selector
    for untouched in ("stSidebar", "stDataFrame", "stPlotlyChart", "stTable", "capa-intro-host"):
        assert untouched not in STYLE, untouched


def test_style_is_theme_free_and_identical_every_time() -> None:
    """색이 없는 고정 문자열이라 테마와 무관하고 회차마다 같다."""
    assert not re.search(r"#[0-9A-Fa-f]{6}\b|\brgba?\(", STYLE)
    assert STYLE.startswith("<style>") and STYLE.endswith("</style>")
