# Purpose: 앱 공통 설정 상수를 검증한다.

import base64
import importlib

from capa_simulation.design import tokens
from capa_simulation.settings import APP_NAME


def test_app_name_has_no_emoji() -> None:
    """탭 아이콘은 `page_icon` 이 그린다. 이름에 이모지를 섞으면 두 번 나온다."""
    assert APP_NAME == "S.PKG CAPA AX Management"


def test_favicon_is_a_local_svg_sent_as_a_data_uri() -> None:
    """탭 아이콘은 외부 주소(fonts.gstatic.com)도 URL 경로 접두도 타지 않는 data URI 여야 한다.

    Streamlit 은 `.svg` 로 끝나는 파일을 읽어 내용이 `<svg` 로 시작할 때만 data URI 로 싣는다.
    파일 맨 앞에 주석이나 BOM 을 두면 그 판정이 빗나가 경로 문자열이 그대로 브라우저로 간다.
    """
    from streamlit.commands.page_config import _get_favicon_string

    from capa_simulation.settings import FAVICON_PATH

    assert FAVICON_PATH.is_file()
    assert FAVICON_PATH.read_bytes().startswith(b"<svg ")
    assert _get_favicon_string(str(FAVICON_PATH)).startswith("data:image/svg+xml;base64,")


def test_favicon_is_the_main_mark_in_both_tab_colour_schemes() -> None:
    """탭 아이콘은 메인 심볼(C 링 + 3×3 다이)이다(2026-10-07 사용자 결정 — 모양 대조는
    `test_intro_overlay`). 탭 바탕이 밝든 어둡든 읽혀야 하므로 파일 안의 `<style>` 이
    `prefers-color-scheme` 에 따라 링(`TEXT`)·다이(`ACCENT`)·가운데 다이(`BRAND_DIE_WARM`)를 그
    테마의 토큰 값으로 바꾼다. Streamlit 은 파일 글자를 그대로 base64 로 실으므로 `<style>` 이
    data URI 에 남는다 — 그것을 풀어 확인한다.
    """
    from streamlit.commands.page_config import _get_favicon_string

    from capa_simulation.settings import FAVICON_PATH

    uri = _get_favicon_string(str(FAVICON_PATH))
    svg = base64.b64decode(uri.split(",", 1)[1]).decode("utf-8")
    assert svg == FAVICON_PATH.read_text(encoding="utf-8")
    style = svg[svg.index("<style>") : svg.index("</style>")]
    light = style[style.index("@media (prefers-color-scheme:light)") :]
    light = light[: light.index("}}") + 2]
    dark = style[style.index("@media (prefers-color-scheme:dark)") :]
    dark = dark[: dark.index("}}") + 2]
    assert f".ring{{stroke:{tokens.palette_value('light', 'TEXT')}}}" in light
    assert f".ring{{stroke:{tokens.palette_value('dark', 'TEXT')}}}" in dark
    assert f".die{{fill:{tokens.palette_value('dark', 'ACCENT')}}}" in dark
    assert f".core{{fill:{tokens.palette_value('dark', 'BRAND_DIE_WARM')}}}" in dark
    # 밝은 쪽 다이 색은 매체 조건 밖의 기본값이다(링 기본값은 양쪽에서 읽히는 중간 회색).
    base = style[: style.index("@media")]
    assert f".die{{fill:{tokens.palette_value('light', 'ACCENT')}}}" in base
    assert f".core{{fill:{tokens.palette_value('light', 'BRAND_DIE_WARM')}}}" in base
    assert svg.count('class="core"') == 1 and svg.count('class="die"') == 8
    assert not (FAVICON_PATH.parent / "factory.svg").exists()


def test_streamlit_config_file_parses_and_names_only_known_options() -> None:
    """`.streamlit/config.toml` 은 Streamlit 과 같은 파서(`toml`)로 읽혀야 하고, 적은 이름은 모두
    지금 Streamlit 이 아는 옵션이어야 한다.

    Streamlit 은 이 파일의 파싱 오류(같은 `[global]` 블록 둘 등)를 로그에만 남기고 파일 **전체**를
    버린다 — 테마·정적 서빙 글꼴·업로드 한도가 한꺼번에 빠지는데 화면은 그대로 선다. 다른 테스트는
    정규식으로 줄만 읽어 이를 놓친다. `[global]` 의 캐시 옵션은 문서에 없는 숨은 옵션이라 판올림 때
    이름이 사라져도 조용히 무시되므로 이름도 함께 본다.
    """
    from streamlit import config

    from capa_simulation.settings import PROJECT_ROOT

    # Streamlit 이 쓰는 파서다(`streamlit/config.py`). 타입 스텁이 없어 모듈로 불러 쓴다.
    toml = importlib.import_module("toml")
    parsed: dict[str, dict[str, object]] = toml.loads(
        (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    )
    known = set(config.get_config_options())
    unknown = [
        f"{section}.{name}"
        for section, values in parsed.items()
        if not section.startswith("theme")
        for name in values
        if f"{section}.{name}" not in known
    ]

    assert {"server", "global", "browser", "theme"} <= set(parsed)
    assert unknown == []
