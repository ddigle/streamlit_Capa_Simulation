# Purpose: 통합인증의 환경변수·경로·쿠키·클레임 이름을 한곳에 둔다(표준 라이브러리만).

"""통합인증 이름표.

값(사내 주소 · 인증서 · 비밀)은 여기에 두지 않는다 — 이 저장소는 공개이고, 실제 값은 C-DEP 배포
설정의 환경변수 표에서만 들어온다. 이 모듈은 표준 라이브러리도 거의 쓰지 않는다. 시작 스크립트의
보고처럼 가벼운 쪽이 이름만 필요할 때 PyJWT · cryptography · Starlette 를 끌고 오지 않게 하려는
것이다.
"""

from __future__ import annotations

# --- 환경변수 이름 ---------------------------------------------------------------------------
# 켜는 스위치. 포털 승인 메일로 받는 Client ID 이고, 비어 있으면 통합인증은 꺼짐이다.
ENV_CLIENT_ID = "ADFS_CLIENT_ID"
# 우리 세션 토큰(HS256)의 비밀값. 앱이 기동 때 읽은 뒤 `os.environ` 에서 뺀다.
ENV_SECRET = "JWT_SECRET_KEY"
# `prod` · `production` 이면 운영 규칙(https 만 · `__Host-` 쿠키 · 꺼짐 경고).
ENV_APP_ENV = "APP_ENV"
ENV_AUTHORIZE_URL = "ADFS_AUTHORIZE_URL"
ENV_ISSUER = "ADFS_ISSUER"
ENV_SIGNING_CERT = "ADFS_SIGNING_CERT"
ENV_PUBLIC_URL = "CAPA_PUBLIC_URL"
# 마지막 사용 뒤 유지 시간(유휴 만료). 앱을 쓰면 늘어난다.
ENV_SESSION_HOURS = "CAPA_SSO_SESSION_HOURS"
# 써도 넘지 못하는 최대 로그인 시간(처음 ADFS 로그인에서). 하루 한 번 ADFS 로 계정을 다시 확인한다.
ENV_SESSION_MAX_HOURS = "CAPA_SSO_SESSION_MAX_HOURS"
# 비거나 `auto` → client id 로 판정, `required` → 잠금(client id 가 지워져도 막힘).
ENV_SSO = "CAPA_SSO"
ENV_SCOPE = "ADFS_SCOPE"
ENV_RESOURCE = "ADFS_RESOURCE"
ENV_CLAIM_LOGINID = "ADFS_CLAIM_LOGINID"
ENV_CLAIM_USERNAME = "ADFS_CLAIM_USERNAME"
ENV_CLAIM_DEPTNAME = "ADFS_CLAIM_DEPTNAME"
ENV_LOGOUT_URL = "ADFS_LOGOUT_URL"

# 통합인증이 읽는 환경변수 전부. 시험의 자동 정리 · 시작 보고(있음/없음) · 앱 사본을 띄우는 보조
# 스크립트가 같은 튜플을 쓴다. 차례는 설정 화면 · 점검 표의 줄 차례다.
SSO_ENVIRONMENT: tuple[str, ...] = (
    ENV_CLIENT_ID,
    ENV_SECRET,
    ENV_APP_ENV,
    ENV_AUTHORIZE_URL,
    ENV_ISSUER,
    ENV_SIGNING_CERT,
    ENV_PUBLIC_URL,
    ENV_SESSION_HOURS,
    ENV_SESSION_MAX_HOURS,
    ENV_SSO,
    ENV_SCOPE,
    ENV_RESOURCE,
    ENV_CLAIM_LOGINID,
    ENV_CLAIM_USERNAME,
    ENV_CLAIM_DEPTNAME,
    ENV_LOGOUT_URL,
)

# 값을 화면 · 보고 · 로그에 절대 싣지 않는 이름(있음/없음 · 길이 같은 사실만).
SECRET_ENVIRONMENT: tuple[str, ...] = (ENV_SECRET,)

# --- 경로 -----------------------------------------------------------------------------------
# 포털 「Endpoint URL」 에 등록하는 콜백. IdP 가 id_token 을 form_post(POST)로 보낸다.
CALLBACK_PATH = "/auth/callback"
LOGIN_PATH = "/auth/sso/login"
LOGOUT_PATH = "/auth/sso/logout"
ERROR_PATH = "/auth/sso/error"
# 앱 화면에서 사람이 쓰는 동안 세션 쿠키를 다시 발급한다(POST · 본문 없음 · 같은 출처).
REFRESH_PATH = "/auth/sso/refresh"
SSO_PATHS: tuple[str, ...] = (CALLBACK_PATH, LOGIN_PATH, LOGOUT_PATH, ERROR_PATH, REFRESH_PATH)
# Streamlit 의 상태 검사. C-DEP 이 본다 — 막힘 모드에서도 열어 둔다.
HEALTH_PATH = "/_stcore/health"
# Streamlit 자체 `st.login` 경로. 우리 경로와 이름이 겹치지 않게 피했고, 통합인증이 켜지면 막는다.
STREAMLIT_AUTH_PATHS: tuple[str, ...] = ("/auth/login", "/auth/logout", "/oauth2callback")

# --- 갱신 요청 머리 ---------------------------------------------------------------------------
# 같은 출처 fetch 만 실을 수 있다(폼은 못 싣고 교차 출처는 사전 요청에서 막힌다). 밑줄을 쓰지
# 않는다 — nginx 계열 앞단이 밑줄 머리를 버린다.
REFRESH_HEADER = "X-Capa-Sso-Refresh"
REFRESH_HEADER_VALUE = "1"

# --- 쿠키 바탕 이름 ---------------------------------------------------------------------------
# https 공개 URL 이면 앞에 `__Host-` 를 붙인다(Secure · Path=/ · Domain 없음이 브라우저에서
# 강제된다).
# `_streamlit_` 으로 시작하지 않게 한다 — Streamlit 쿠키와 섞이지 않게.
HOST_PREFIX = "__Host-"
SESSION_COOKIE = "capa_session"
STATE_COOKIE_PREFIX = "capa_sso_state_"
ATTEMPT_COOKIE = "capa_sso_attempt"

# --- 클레임 기본 이름 -------------------------------------------------------------------------
DEFAULT_CLAIM_LOGINID = "loginid"
DEFAULT_CLAIM_USERNAME = "username"
DEFAULT_CLAIM_DEPTNAME = "deptname"

# --- 그 밖 ----------------------------------------------------------------------------------
LOGGER_NAME = "capa_simulation.sso"
DEFAULT_SESSION_HOURS = 6
DEFAULT_SESSION_MAX_HOURS = 24
DEFAULT_SCOPE = "openid"
# 문서 자리(설정 화면 · 점검이 가리킨다).
SETUP_DOC = "docs/sso_setup.md"
