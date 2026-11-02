# 사내 통합인증(SSO) 연동 — 운영 · 개발 안내

C-DEP 운영 서버에서 사내 통합인증(ADFS, 포털 시스템 형식 「Legacy (OpenID)」)으로 로그인한 사람만 앱에 들어오게 한다.
**이 문서에는 사내 주소 · 인증서 · client id 를 적지 않는다** — 이 저장소는 공개다. 예시는 모두 `*.example.invalid` 이고, 실제 값은
C-DEP 배포 설정의 **환경변수 표**에만 넣는다(리뷰 압축본 · 전문에도 값을 옮기지 않는다).

코드: 진입 파일 `capa_server.py`, 꾸러미 `src/capa_simulation/auth/`, 화면 조각 `components/sso_identity.py` · `components/sso_status.py`,
가짜 IdP `scripts/sso_mock_idp.py`. 규칙은 `AGENTS.md` 3장(파일 책임) · 5장 35 · 9장(문지기) · 10장(공개 저장소).

## 1. 흐름

```text
브라우저 ──GET /──▶ 문지기(SsoGate) ── 세션 쿠키 없음 ──302──▶ ADFS authorize
                                                              (response_type=id_token, response_mode=form_post,
                                                               redirect_uri=<CAPA_PUBLIC_URL>/auth/callback, nonce, state)
ADFS ──POST /auth/callback (id_token, state)──▶ 앱
        ① state 쿠키(서명 · 10분) 대조  ② id_token 검증(RS256 · 서명 인증서 핀 · aud=ADFS_CLIENT_ID · iss=ADFS_ISSUER ·
        exp/iat · nonce)  ③ loginid · username · deptname 꺼냄  ④ 우리 세션 토큰(HS256, JWT_SECRET_KEY) 발급
        ⑤ HttpOnly 세션 쿠키 설정 ──303──▶ 처음 가려던 화면
브라우저 ──websocket /_stcore/stream (쿠키)──▶ 문지기가 쿠키 · Origin 확인 ──▶ Streamlit
app.py ── 매 회차 st.context.cookies 의 세션 쿠키를 다시 검증(만료 · 로그아웃 · 계정 바뀜) ──▶ 화면
```

- **한 프로세스다.** `capa_server.py` 가 `app.py` 를 `st.App(routes=…, middleware=…)` 으로 감싸 콜백 경로와 문지기를 같은
  프로세스에 붙인다. nginx · 사이드카는 없다. C-DEP 시작 스크립트(`scripts/container_start.py`)가
  `streamlit run capa_server.py --server.port 8080` 으로 띄운다. 개발 PC · 사내 WebIDE · 시험은 지금처럼 `app.py` 다.
- **경로 넷** — `POST /auth/callback`(포털 Endpoint URL), `GET /auth/sso/login?next=`, `GET /auth/sso/logout`,
  `GET /auth/sso/error?id=`. Streamlit 자체 `st.login`(`/auth/login` 등)은 GET 콜백이라 쓰지 않는다.
- **로그인은 쿠키로만 든다.** `?token=` 질의 인자나 세션 상태 보관은 쓰지 않는다 — 테마 단추의 새로고침이 새 세션을 만들어도
  쿠키는 남는다.
- **모드 셋** — `ADFS_CLIENT_ID` 가 비면 **꺼짐**(지금처럼 열림, 운영이면 경고), 다 맞으면 **켜짐**, client id 는 있는데 나머지가
  없거나 틀리면 **막힘**(상태 검사 `/_stcore/health` 만 살리고 `/` 는 설정 화면 — 값 없이 환경변수 이름 · 상태 · 까닭).
  `CAPA_SSO=required` 면 client id 가 지워져도 막힘이다(잠금).

## 2. 환경변수

C-DEP 배포 설정의 환경변수 표(key · value, 값은 한 줄)에 넣는다. `.env` 파일 로더는 없다 — 그 표가 그 자리다.
환경변수를 바꾸면 CI/CD 를 다시 돌려 재시작해야 반영된다.

| 이름 | 필요할 때 | 뜻 | 예시(가짜) |
|---|---|---|---|
| `ADFS_CLIENT_ID` | 켜는 스위치(비면 꺼짐) | 포털 승인 메일의 Client ID. id_token 의 `aud` 와 정확히 같아야 한다 | `00000000-0000-0000-0000-000000000000` |
| `JWT_SECRET_KEY` | 켜짐 필수 · **비밀** | 우리 세션 토큰 비밀. 32바이트 이상 · 고정값(바꾸면 모두 다시 로그인). 아래 4장 | (만든 값) |
| `APP_ENV` | 선택 | `prod` 면 운영 규칙(https 만 · `__Host-` 쿠키 · 꺼짐 경고) | `prod` |
| `ADFS_AUTHORIZE_URL` | 켜짐 필수 | ADFS authorize 엔드포인트 | `https://idp.example.invalid/adfs/oauth2/authorize/` |
| `ADFS_ISSUER` | 켜짐 필수 | id_token 의 `iss` 와 **글자 하나까지** 같은 값. 짐작하지 않는다 — 비면 막힘(설정 화면에 관례 후보만) | `https://idp.example.invalid/adfs` |
| `ADFS_SIGNING_CERT` | 켜짐 필수 | 토큰 **서명** 인증서 한 줄(base64 DER · base64 PEM · PEM). 여럿은 쉼표(교체 때). 아래 3장 | `MIIC…`(한 줄) |
| `CAPA_PUBLIC_URL` | 켜짐 필수 | 브라우저가 여는 앱 주소. redirect_uri 와 모든 이동 주소의 바탕(요청 Host 는 보지 않는다) | `https://capa.example.invalid` |
| `CAPA_SSO_SESSION_HOURS` | 선택 | 세션 시간(1~24, 기본 12) | `12` |
| `CAPA_SSO` | 선택 | `required` 면 잠금 | `required` |
| `ADFS_SCOPE` · `ADFS_RESOURCE` | 선택 | 클레임을 id_token 에 싣는 데 필요하면(기본 scope `openid`) | `openid allatclaims` |
| `ADFS_CLAIM_LOGINID` · `ADFS_CLAIM_USERNAME` · `ADFS_CLAIM_DEPTNAME` | 선택 | 클레임 이름(기본 `loginid` · `username` · `deptname`) | `loginid` |
| `ADFS_LOGOUT_URL` | 선택 | 로그아웃 화면에 「통합인증에서도 로그아웃」 링크 | `https://idp.example.invalid/adfs/oauth2/logout` |

- 포털에 등록하는 값: 서비스 URL = `CAPA_PUBLIC_URL`, Endpoint URL = `CAPA_PUBLIC_URL` + `/auth/callback`. 둘은 한 글자도
  달라선 안 된다 — Admin Area 「통합인증 점검」 · 설정 화면이 계산한 redirect_uri 를 보인다.
- 사용자 샘플은 `APP_ENV=prod` 가 ADFS 주소와 인증서 파일을 자동으로 넣었다. 이 저장소는 공개라 그 값을 둘 수 없어
  `ADFS_AUTHORIZE_URL` · `ADFS_ISSUER` · `ADFS_SIGNING_CERT` · `CAPA_PUBLIC_URL` 을 환경변수 표로 받는다. `APP_ENV=prod` 는
  「엄격하게 보라」 는 뜻만 갖는다.
- C-DEP 이 HTTPS 를 주므로 도메인 · 인증서 신청은 필요 없다. TLS 는 인그레스에서 끝나고 pod 안은 http 다 — 쿠키의 Secure 는
  요청이 아니라 `CAPA_PUBLIC_URL` 의 https 로 정한다.

## 3. 서명 인증서 넣는 법 · 교체

- 넣는 것은 ADFS 의 **토큰 서명 인증서**다(TLS 인증서가 아니다). 사내 WebIDE 터미널에서 `base64 -w0 <토큰 서명 인증서 파일>`
  출력 한 줄을 `ADFS_SIGNING_CERT` 값으로 넣는다(PEM 이면 그 파일도 같은 줄로 넣으면 된다). 인증서 파일을 저장소 · `cert/` 에
  두지 않는다 — `.gitignore` · 배포 ZIP 금지 · 감시 시험이 막는다.
- 체인 검증은 하지 않는다(핀 고정). 만료는 막지 않고 경고만 한다 — 30일 안이면 Admin Area 와 기동 로그에 알린다.
- **교체**: 새 인증서를 쉼표로 **더해** 두 값으로 두고(최대 3개), 옛 인증서가 만료된 뒤 뺀다. id_token 헤더의 지문(x5t)이 맞는
  것부터 시도한다.

## 4. 비밀값 만들기

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

- 출력을 `JWT_SECRET_KEY` 로 넣는다. 고정값이다 — 재시작해도 로그인이 유지되고, 바꾸면 모두 다시 로그인한다.
- 32바이트 미만 · 서로 다른 글자 10개 미만 · 자리표(`changeme` · `secret` 등) · client id 와 같은 값은 막힘이다.
- **환경변수 표를 본 사람은 이 값으로 로그인 토큰을 만들 수 있다.** 표를 볼 수 있는 사람을 좁힌다.
- 앱은 기동 때 이 값을 읽은 뒤 프로세스 환경에서 지운다(사내 모듈 · 하위 프로세스로 새지 않게).

## 5. 첫 배포 순서

1. 이 변경이 실린 배포를 적용한다. C-DEP 환경변수 표에 `APP_ENV=prod` · `JWT_SECRET_KEY` · `CAPA_PUBLIC_URL` ·
   `ADFS_AUTHORIZE_URL` · `ADFS_ISSUER` · `ADFS_SIGNING_CERT` 를 넣고 **client id 는 비운 채** CI/CD 를 돌린다. 앱은 지금처럼
   열리고, Admin Area 「통합인증 점검 · 꺼짐(운영)」 의 「켜면 막힐 문제: 없음」 을 확인한다(있으면 그 이름 · 까닭대로 고친다).
2. 포털 승인 메일의 Client ID 를 `ADFS_CLIENT_ID` 에 넣고 CI/CD 를 돌린다 → 로그인해 본다. 실패면 오류 화면의 사유 코드 ·
   받은 iss/aud(서명이 맞을 때만 보인다) · 받은 클레임 이름으로 값을 고친다. 설정 화면(막힘)이 뜨면 그 표대로 고친다.
3. 되면 `CAPA_SSO=required` 를 넣어 잠근다 — 실수로 client id 를 지워도 열리지 않는다.

## 6. 사용자가 보는 것

- 사이드바 앱 정보 카드 셋째 줄 「이름 · 부서 · 로그아웃」(켜짐에서만). 만료 30분 전부터 「로그인 n분 남음 — 저장해 두세요」.
- 만료 · 다른 탭에서 로그아웃 · 쿠키 없음은 화면 맨 위 경고와 「다시 로그인」(다시 로그인하면 그 탭의 저장하지 않은 편집은
  사라진다). 같은 탭이 다른 계정으로 이어지면 「새로고침하세요」.
- **로그아웃의 한계** — 이 앱의 로그인만 끝낸다. 브라우저의 통합인증(AD) 로그인은 남아 「다시 들어가기」 를 누르면 묻지 않고
  다시 들어온다. `ADFS_LOGOUT_URL` 이 있으면 「통합인증에서도 로그아웃」 링크가 붙는다(자동으로 보내지 않는다).
- **CONNECTING 에 머물면 새로고침** — 서버가 재시작됐거나 세션이 만료돼 websocket 이 거절된 것이다. 새로고침하면 로그인부터
  다시 탄다.
- 앱에 들어올 수 있는 사람의 범위는 포털이 정한다 — 앱은 인증된 사람 전부를 받는다(앱 안 권한은 아직 없다).

## 7. 진단 창구

- **Admin Area 「통합인증 점검」** — 판정(켜짐 · 꺼짐(운영) · 막힘), 환경변수 이름 | 상태 | 까닭(값 없음), 계산한 redirect_uri ·
  issuer · 서명 인증서 지문(x5t · SHA-256 앞 16자) · 만료일, 세션 시간 · 쿠키 이름 · 문지기 · 잠금, 최근 사건(재시작하면 비워진다 ·
  계정은 앞 두 글자). 꺼짐이고 운영이 아니면 펼침이 없다.
- **Admin Area 「서버 시작 점검」** 표 넷째 줄 「통합인증」 — 정상 · 건너뜀(`ADFS_CLIENT_ID` 없음) · 실패(문제 이름). 시작 스크립트가
  남긴 「시작 때 있던 통합인증 환경변수」 이름도 한 줄 붙는다.
- **설정 화면**(막힘) · **오류 화면**(로그인 실패, 새로고침해도 폼이 다시 가지 않는다) — 사유 코드와 한 줄 설명. 토큰 · state ·
  nonce · 쿠키 값 · 비밀값 · 이름 · 부서는 어디에도 보이지 않는다.
- 서버 로그(볼 수 있다면) — `sso event=config|login_ok|login_fail|logout|cert_expiring …` 한 줄씩.

## 8. 개발 — 가짜 IdP 로 끝까지 돌리기

실제 ADFS 없이 로그인 흐름을 돌린다. 가짜 IdP 는 실행 때 RSA 키를 메모리에만 만들고, `APP_ENV` 가 운영이면 · 루프백이 아닌
`--host` 면 · env 파일이 작업 트리 안이면 거절한다. 명령은 창 둘로 나눠 친다(포트는 늘 적는다).

창 1 — 가짜 IdP(그 자리에 개발용 환경변수 파일을 쓴다):

```bash
python scripts/sso_mock_idp.py --port 8591 --app-url http://localhost:8510 --env-out ~/sso-dev.env
```

창 2 — 그 파일을 읽어 진입 파일로 앱을 띄운다:

```bash
set -a; . ~/sso-dev.env; set +a
python -m streamlit run capa_server.py --server.port 8510
```

- 브라우저로 `http://localhost:8510` 을 열면 가짜 IdP 화면(클레임 표 + 「로그인」)을 거쳐 앱으로 돌아온다. `--aud` · `--omit-claim` ·
  `--error` 로 실패 화면을 볼 수 있다.
- http 루프백에서는 브라우저가 상태 쿠키(`SameSite=None; Secure`)를 받지 않을 수 있다. 확인된 길은 HTTPS(자체서명)다 — 앱은
  `--server.sslCertFile/--server.sslKeyFile`, 가짜 IdP 는 `--tls-cert/--tls-key` 로 띄우고 `--app-url` 을 https 로 준다.
- **사내 WebIDE 에서 시험할 때** — 앱 · 가짜 IdP 를 WebIDE 프록시 주소로 연다. `--app-url` 에 앱의 프록시 주소(경로 접두
  `/proxy/<포트>` 포함)를, `--public-url` 에 가짜 IdP 의 프록시 주소를 준다. 쿠키 이름에 경로 접두의 지문이 붙어 같은 호스트의
  여러 앱이 서로 덮지 않는다.
- 개발 · 시험 · 화면 확인(`scripts/check_deploy_screens.py`)은 지금처럼 `app.py` 로 띄운다 — 통합인증 환경변수가 없으면 꺼짐이고,
  켜진 설정을 `app.py` 로 띄우면 「문지기 없이 앱이 시작됐습니다」 로 멈춘다(진입 파일 없이 열리지 않게).

## 9. 사내에서 확인할 것(포털 · ADFS · C-DEP 담당)

1. issuer 의 정확한 문자열과 id_token `aud` 가 client id 문자열 하나인지(목록이면 `azp` 처리가 더 필요하다).
2. 포털 「Legacy (OpenID)」 가 `response_type=id_token` + `response_mode=form_post` 를 허용하는지.
3. loginid · username · deptname 이 **id_token** 에 실리려면 `scope`(예: `allatclaims`)나 `resource` 가 필요한지 — `ADFS_SCOPE` ·
   `ADFS_RESOURCE` 로 넣는다.
4. 클레임 이름이 그 셋 그대로인지, loginid 에 도메인 접두(`DOMAIN\`)가 붙는지(붙으면 받는 글자 집합을 넓혀야 한다).
5. 넣을 인증서가 **토큰 서명** 인증서인지, 꼴(DER/Base-64), 교체 방식 · 주기 · 공지 채널.
6. ADFS 로그아웃 주소와 로그아웃 뒤 돌아올 주소 등록이 되는지.
7. C-DEP 상태 검사 경로 · 방식(TCP · `/` · `/_stcore/health`), 환경변수 값 길이 제한(인증서 한 줄 1~2 KiB), 인그레스가 Host 를
   그대로 넘기는지, replica 수(1 전제 — 로그아웃 폐기 목록이 프로세스 메모리다).
8. 사내 이미지 빌드(pip)와 WebIDE `uv sync --inexact` 가 새 의존성 넷(pyjwt · cryptography · cffi · pycparser) 휠을 받는지.
9. 앱에 들어올 수 있는 사람의 범위를 포털이 정하는지.
10. C-DEP 환경변수 표를 볼 수 있는 사람 — `JWT_SECRET_KEY` 를 본 사람은 로그인 토큰을 만들 수 있다.
