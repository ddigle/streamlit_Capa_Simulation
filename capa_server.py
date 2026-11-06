# Purpose: C-DEP 운영 진입점 — app.py 를 st.App 으로 감싸 통합인증 경로·문지기를 붙인다.

"""운영 진입 파일(`streamlit run capa_server.py --server.port 8080`).

- **왜 저장소 루트인가** — Streamlit 은 `.streamlit/config.toml` 과 정적 서빙 `static/` 을 진입
  스크립트와 같은 폴더에서 찾는다. `app.py` 옆에 두어야 두 실행(`app.py` · 이 파일)이 같은 설정 ·
  글꼴 · 페이지를 본다.
- **왜 모듈 수준 리터럴 대입인가** — `streamlit run` 은 이 파일을 실행하지 않고 AST 로
  `app = st.App(...)` 대입만 찾아 uvicorn 에 넘긴다. 함수가 만들어 돌려준 App 은 오류 없이
  **빈 화면**이 된다(실측). 이 파일에는 다른 `st.App` · `Starlette` 호출을 두지 않는다.
- 개발 PC · 사내 WebIDE · 시험 · 화면 확인은 지금처럼 `streamlit run app.py` 다. 그때 통합인증은
  꺼짐이거나, 켜진 설정이면 `app.py` 가 「문지기 없이 시작됨」 으로 멈춘다.
- 꺼짐 모드(`ADFS_CLIENT_ID` 없음)에서도 이 파일로 뜬다 — 경로 다섯은 404, 문지기는 모두 통과.
"""

from pathlib import Path

import streamlit as st

from capa_simulation.auth.server import sso_middleware, sso_routes, start_sso
from capa_simulation.io.container_start_report import note_app_ready
from capa_simulation.object_sync_worker import start_object_sync

# 환경변수를 한 번 읽어 검증하고 로그 처리기를 단 뒤 비밀값 · 접속 명단을 `os.environ` 에서 뺀다.
start_sso()
# 정본 버킷 동기화 일꾼. 시작 받기가 성공한 `managed` 서버에만 선다 — 첫 접속을 기다리지 않는다.
start_object_sync()

app = st.App(
    Path(__file__).with_name("app.py"),
    routes=sso_routes(),
    middleware=sso_middleware(),
)

# 「앱 응답까지 n초」 의 끝. 이 뒤로 uvicorn 이 받는다 — 첫 접속을 기다리면 몇 시간이 될 수 있다.
note_app_ready()
