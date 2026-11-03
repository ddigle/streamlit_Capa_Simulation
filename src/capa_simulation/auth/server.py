# Purpose: 진입 파일이 부르는 셋 — 통합인증 기동·경로 다섯·문지기 미들웨어.

"""진입 파일 창구.

`capa_server.py` 가 모듈 수준에서 `start_sso()` 를 부른 뒤 `st.App(routes=sso_routes(),
middleware=sso_middleware())` 로 감싼다. 꺼짐 모드에서도 같은 파일로 뜬다 — 경로 다섯은 404 를,
문지기는 모두 통과를 돌려준다. 갱신 경로는 POST 하나지만 GET(· HEAD)도 붙여 처리기가 답한다 —
붙이지 않으면 Streamlit 정적 마운트가 그 주소에 앱 껍데기(`index.html`, 200)를 낸다. 이 모듈은
PyJWT 를 import 하지 않는다(경로 처리기 안에서 필요할 때만).
"""

from __future__ import annotations

import os

from starlette.middleware import Middleware
from starlette.routing import BaseRoute, Route

from capa_simulation.auth import names, runtime, web
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.gate import SsoGate


def start_sso() -> SsoConfig:
    """환경변수를 한 번 읽어 검증하고 로그 처리기를 단 뒤 `JWT_SECRET_KEY` 를 환경에서 뺀다."""
    return runtime.start(os.environ)


def sso_routes() -> list[BaseRoute]:
    """우리 경로 다섯. Streamlit 의 예약 접두 · `st.login` 경로와 겹치지 않는다."""
    return [
        Route(names.CALLBACK_PATH, web.callback, methods=["GET", "POST"]),
        Route(names.LOGIN_PATH, web.login, methods=["GET"]),
        Route(names.LOGOUT_PATH, web.logout, methods=["GET"]),
        Route(names.ERROR_PATH, web.error, methods=["GET"]),
        Route(names.REFRESH_PATH, web.refresh, methods=["GET", "POST"]),
    ]


def sso_middleware() -> list[Middleware]:
    """문지기 하나 — 사용자 미들웨어는 Streamlit 미들웨어보다 바깥에서 돈다."""
    return [Middleware(SsoGate)]
