# Purpose: 앱 공통 설정 상수를 검증한다.

from capa_simulation.settings import APP_NAME


def test_app_name_has_no_emoji() -> None:
    """탭 아이콘은 `page_icon` 이 그린다. 이름에 이모지를 섞으면 두 번 나온다."""
    assert APP_NAME == "S.PKG Capa Simulation"
