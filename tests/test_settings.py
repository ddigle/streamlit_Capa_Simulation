# Purpose: 앱 공통 설정 상수를 검증한다.

from capa_simulation.settings import APP_NAME


def test_app_name_has_no_emoji() -> None:
    """탭 아이콘은 `page_icon` 이 그린다. 이름에 이모지를 섞으면 두 번 나온다."""
    assert APP_NAME == "S.PKG Capa Simulation"


def test_favicon_is_a_local_svg_sent_as_a_data_uri() -> None:
    """탭 아이콘은 외부 주소(fonts.gstatic.com)도 URL 경로 접두도 타지 않는 data URI 여야 한다.

    Streamlit 은 `.svg` 로 끝나는 파일을 읽어 내용이 `<svg` 로 시작할 때만 data URI 로 싣는다.
    파일 맨 앞에 주석이나 BOM 을 두면 그 판정이 빗나가 경로 문자열이 그대로 브라우저로 간다.
    """
    from streamlit.commands.page_config import _get_favicon_string

    from capa_simulation.settings import FAVICON_PATH

    assert FAVICON_PATH.is_file()
    assert (FAVICON_PATH.parent / "LICENSE-Apache-2.0.txt").is_file()
    assert _get_favicon_string(str(FAVICON_PATH)).startswith("data:image/svg+xml;base64,")
