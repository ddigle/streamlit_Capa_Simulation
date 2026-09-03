# Purpose: 앱 공통 설정 상수를 검증한다.

from capa_simulation.settings import APP_NAME


def test_app_name() -> None:
    assert APP_NAME == "🏭S.PKG Capa Simulation"
