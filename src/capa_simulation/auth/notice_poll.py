# Purpose: 운영 서버의 공지 물음 경로 — 프로세스 메모리의 공지 꼴을 저장하지 않는 JSON 으로 낸다.

"""공지 물음 경로 `GET /capa/notice`(2026-11-17 공지 보드 답 q-speed — 운영 서버는 10초마다 묻기).

`capa_server.py` 로 뜬 서버(문지기 있음)의 열린 탭은 툴바 iframe
스크립트(`components/sso_reconnect.py` — 연결 표지를 1초마다 읽는 그 틱)가 붙어 있는 동안 10초마다
이 경로를 묻고, 판이 바뀌었으면 알림 칸 입구(`window.__capaAlerts.notice`)에 넘긴다. Streamlit
회차 · GC · 브라우저 메시지 캐시에 닿지 않는다.

- **문지기를 거친다.** 이 경로는 공개 목록(`names.SSO_PATHS`)에 없다 — 켜짐이면 문지기가 세션 쿠키를
  검증해 신원이 있는 요청만 넘긴다(없으면 fetch 401 + 까닭 머리, 탐색은 IdP). 막힘이면 문지기가 503
  을 낸다. 처리기는 쿠키를 다시 보지 않는다.
- **모드는 처리기가 스스로 본다**(`web.mode_guard` 와 같은 자리). 꺼짐이면 문지기가 모두 넘기는데
  그때 앱 자체가 누구에게나 열려 있어 공지도 같이 낸다 — 꺼짐 서버를 `capa_server.py` 로 띄운 개발
  PC · WebIDE 도 10초 물음을 쓴다(보드 decided-9 의 사내 확인 거리). 켜짐인데 문지기가 없으면(진입
  파일 밖에서 경로만 붙음) 쿠키를 보지 않은 요청이라 내지 않는다(503). 막힘은 문지기보다 늦게 닿을
  일이 없지만 같은 503 을 낸다.
- **이벤트 루프에서 돈다 — 메모리만 읽는다.** 응답은 `notice_board.payload()` 그대로(프로세스 표지 ·
  판 · 공지 · 상태 표지 — 알림 칸 data 의 공지 칸과 같은 꼴)이고 `Cache-Control: no-store` 다.
  사건 · 누계 · 로그를 남기지 않는다(탭마다 10초에 한 줄은 소음이다). 이 모듈을 import 해도
  Streamlit 이 딸려 오지 않는다 — `payload` 가 부를 때 알림 등록부를 들인다(앱 프로세스에는 이미
  있다).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from capa_simulation import notice_board
from capa_simulation.auth import runtime
from capa_simulation.auth.config import SsoMode
from capa_simulation.auth.web import text_response

# 응답 머리 — 앞단 · 브라우저가 담아 두지 않고, 사람이 쓴 글이 든 JSON 을 다른 꼴로 읽지 않게.
RESPONSE_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
UNAVAILABLE = "notice unavailable"


async def notice(request: Request) -> Response:
    """`GET /capa/notice` — 지금 공지 꼴(`notice_board.payload`)을 JSON 으로 낸다."""
    del request
    cfg = runtime.config()
    if cfg.mode is SsoMode.BROKEN:
        return text_response(UNAVAILABLE, 503)
    if cfg.mode is SsoMode.ON and not runtime.gate_installed():
        return text_response(UNAVAILABLE, 503)
    return JSONResponse(notice_board.payload(), headers=RESPONSE_HEADERS)
