# C-DEP WebIDE BigDataQuery 설정 가이드

C-DEP WebIDE(서버 환경)에서 `bigdataquery` 로 DB 를 조회할 때 막히는 자리와 푸는 절차.
사내에서 실제로 끝까지 해 보고 적은 것이고, 리뷰 `202609201104` 로 사외에 들어왔다.

**막히는 자리가 셋이고 서로 다른 것이다.** 하나를 풀어도 다음에서 다시 막히므로 순서대로
간다 — 설치(0) → 로그인(1) → 요청자 계정(2).

## 전제

- C-DEP WebIDE 접속 가능(사내망)
- 저장소를 받아 `uv sync` 까지 끝난 상태

## 0. 설치 — 사내 인덱스에 닿게 한다

`uv pip install -r requirements-company.txt` 가 `not found in the package registry` 로
실패한다면 자격증명 문제가 아니다. 이 WebIDE 이미지가 두 가지를 미리 정해 두었기 때문이다.

1. 환경변수 `UV_DEFAULT_INDEX`(와 `PIP_INDEX_URL`)가 **공개 PyPI 미러**로 고정돼 있고,
   이것이 `--index-url` 옵션보다 먼저 이긴다. `bigdataquery` 는 사내 전용이라 공개 미러에
   없으므로 항상 실패한다.
2. uv 는 제 내장 인증서만 믿어 사내 CA 를 모른다 — 서버에 닿아도
   `invalid peer certificate: UnknownIssuer` 가 난다. (`curl` 이 통과하는 것은 그쪽이 OS
   인증서를 쓰기 때문이고, 그래서 "네트워크는 멀쩡한데 uv 만 안 되는" 모양이 된다.)

추가 인덱스로 넣고 시스템 인증서를 쓰게 한다. 묻는 「사내 Artifactory 주소」 는 사내 패키지 저장소 주소(사내 PC 사용자 환경변수 ·
C-DEP 환경변수 표의 `CAPA_COMPANY_INDEX_URL` 값 — README 4단계)에서 `https://` 를 뗀 나머지다(사내 값이라 이 문서에도
`requirements-company.txt` 에도 적지 않는다 — 공개 저장소. 그 파일의 `--index-url` 줄은 그 환경변수를 가리킨다).
첫 펜스는 한 줄이고 셋을 차례로 묻는다(토큰은 화면에 보이지 않는다) — 그 줄만 붙여 넣고 묻는 자리마다 값을 넣은 뒤 둘째 펜스를 친다.

```bash
read -rp "AD 계정: " u; read -rsp "Artifactory API 토큰: " t; echo; read -rp "사내 Artifactory 주소(https:// 뺀 나머지): " h
```

```bash
export UV_EXTRA_INDEX_URL="https://$u:$t@$h"
uv pip install bigdataquery==2.5.0 --system-certs
```

## 1. 로그인 — AD 토큰을 받는다

토큰이 없으면 조회할 때 이렇게 뜬다.

```
TokenNotFoundException
There is no bigdataquery token issued for AD user '...' at '/config/.credential/' on 'Linux'.
```

WebIDE 터미널에서:

```bash
uv run --no-sync python -c "import bigdataquery as bdq; bdq.login()"
```

프롬프트에 차례로 넣는다.

1. `>> Enter User ID (ssoid):` → 사내 AD ID
2. `>> Engter AD Password:` → 사내 AD 비밀번호 (패키지의 오타를 그대로 옮긴 것이다)

토큰은 `/config/.credential/bigdataquery.token.<AD 계정>` 에 저장되고 이후 `getData()` 가
자동으로 쓴다. **주기적으로 만료되므로** 같은 예외가 다시 뜨면 이 단계를 다시 하면 된다. 앱 화면의 조회 실패
안내도 WebIDE(서버 시작 기록이 없는 곳)에서는 「BigDataQuery 로그인을 다시 하세요」 로 끝난다 — C-DEP 는 토큰을
관리자가 넣으므로 「관리자에게」 다(아래 「C-DEP CD」).

## 2. 요청자 계정 — `user_name` 을 채운다

**로그인과 토큰이 모두 정상인데도** 조회하면 이렇게 뜬다.

```
Parameter user_name is necessary.
```

로그인 토큰과 `user_name` 전달은 **별개**다. 서버(Linux) 환경에는 Windows 처럼 요청자를
자동으로 알아낼 경로가 없다 — 이 컨테이너에서 `echo $USERNAME` 은 비어 있다.

환경변수에 본인 AD 계정을 넣는다 — 이 한 줄만 붙여 넣고 묻는 자리에 계정을 넣는다.

```bash
read -rp "AD 계정: " CAPA_BDQ_USER_NAME; export CAPA_BDQ_USER_NAME
```

값을 넣으면 앱이 `getData(user_name=...)` 로 실어 보낸다. **값이 없으면 인자를 아예 넘기지
않는다** — Windows 에서 패키지가 로그인 이름으로 스스로 식별하는 경로를 깨지 않기 위해서다.
그 상태로 서버에서 거부당하면 앱이 위 문구 대신 이 환경변수를 채우라고 알려 준다.

계정 값은 사람마다 다르므로 **저장소와 배포 ZIP 에 넣지 않는다.** 셸에서만 넣는다.

## 3. 앱 실행

```bash
uv run --no-sync python -m streamlit run app.py --server.port 8501
```

포트를 적는 까닭 — 빼면 8501 이 막혔을 때 **알리지 않고** 다음 번호로 옮겨 서고, 적으면 「Port 8501 is not available」
을 찍고 멈춘다([`internal_update_runbook.md`](internal_update_runbook.md) 4-2).

## C-DEP CD(배포 서버)

CD 로 띄운 서버에는 셸이 없고 시작 명령도 바꿀 수 없다(CI/CD 단추 → 통과하면 바로 실행되고 접속 링크만 준다).
넣을 수 있는 것은 **배포 설정의 환경변수 표(key·value)** 뿐이다. 그래서 이미지(`docker/Dockerfile-prod`)의 `CMD` 가
시작 스크립트 `scripts/container_start.py` 를 부르고, 스크립트가 아래 환경변수만으로 위 0·1·2 를 푼 뒤
`streamlit run capa_server.py --server.port 8080` 으로 바뀐다(`capa_server.py` 는 `app.py` 를 감싸 통합인증 경로·문지기를
붙인 진입점 — [`sso_setup.md`](sso_setup.md)). 어느 단계가 실패해도 앱은 뜬다(`CAPA_S3_SYNC_MODE=managed` 의 DB 받기만 예외 — [`objectstore_setup.md`](objectstore_setup.md) 3장). 설치가 도는 동안은 시작 스크립트가 같은 포트로 상태 검사에 답한다.
모듈이 있는 사내 main 은 누른 때 그대로 빌드된다 — CI/CD 단추는 앱 관리자만,
런북 4-5 모듈 점검을 본 뒤에 누른다(`docs/module_guide.md` 8장).

### 넣을 환경변수

| key | value | 푸는 단계 |
|---|---|---|
| `CAPA_ARTIFACTORY_USER` | 사내 Artifactory 계정(`<AD 계정>`) | 0. 설치 |
| `CAPA_ARTIFACTORY_TOKEN` | Artifactory API 토큰(읽기 전용으로 발급한 것) | 0. 설치 |
| `CAPA_COMPANY_INDEX_URL` | 사내 Artifactory 인덱스 주소(`https://…/simple` 통째 — 자격증명 없이, 사내 PC 와 같은 값). 사내 값이라 저장소에 없다. **이 이름을 읽는 판을 싣는 CI/CD 전에 넣는다** — 없으면 설치를 건너뛰어 BigDataQuery 조회가 멈춘다. 이 키를 모르는 앞 배포에 먼저 넣어도 해가 없다 | 0. 설치 |
| `CAPA_BDQ_TOKEN` | WebIDE 에서 로그인해 만든 토큰 파일의 **내용**(아래) | 1. 로그인 |
| `CAPA_BDQ_USER_NAME` | 본인 AD 계정(`<AD 계정>`) — 토큰 파일 이름과 `getData(user_name=…)` 에 함께 쓴다 | 1·2 |
| `CAPA_BDQ_SECRET_KEY` | (자동 로그인을 쓸 때만) Fernet 키 44글자 — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 출력. 동기화 모드가 `managed` 인 서버에서만 쓰인다 | 1. 로그인(자동) |

- 설치는 `bigdataquery` 가 없을 때만 하고, 판과 인덱스는 `requirements-company.txt` 를 읽는다 — 인덱스 줄의
  `${CAPA_COMPANY_INDEX_URL}` 을 pip · uv 와 같은 꼴로 펼치고, 그 값이 비면 설치를 건너뛰며(`CD 환경변수 … 없음`) `https://주소`
  꼴이 아니거나(평문 `http` 포함) 계정·토큰이 들어 있으면 pip 를 부르지 않고 실패로 적는다(값은 싣지 않는다). pip 를 두 번 부른다. 둘째 pip 는 앱 판 고정
  (`requirements.txt`)을 제약으로 걸므로, 그 판이 `bigdataquery` 의 요구 범위(pandas · numpy 위 끝)를 벗어나면 설치가 「실패」 로 남는다 —
  `pyproject.toml` 이 같은 범위로 묶어 둔 까닭이다. 점검 칸의 `Artifactory 인덱스에서 bigdataquery — pip 종료 코드 n` 은 첫 pip 실패라 판 범위와 상관없다 — 펼침의 pip 출력 끝으로 가른다.
  - **패키지 자신은 사내 인덱스 하나만** 보고 의존성 없이 깐다(`--no-deps`). WebIDE 처럼 공개 미러에 사내 인덱스를
    **추가**로 붙이면 pip 는 두 곳을 같이 보고 더 맞는 파일을 고른다 — 공개 쪽에 같은 이름·판이 올라오면 그것이 깔린다
    (의존성 혼동. uv 는 먼저 찾은 인덱스만 써서 WebIDE 의 uv 꼴은 괜찮다). 자격증명은 명령줄이 아니라 그 pip 의
    환경변수(`PIP_INDEX_URL`)로만 주고 pip 설정 파일은 끈다 — 명령줄은 같은 서버의 누구나 `ps` 로 본다. OS 인증서
    묶음이 있으면 `--cert` 로 준다(사내 CA). sdist 라면 이미지의 setuptools 로 빌드한다(`--no-build-isolation`).
  - **의존성은 이미지의 기본 인덱스**로 채운다. 앱 판 고정(`requirements.txt`)을 제약으로 걸어 사내 패키지가 앱
    의존성을 바꾸지 못하게 한다. 이 pip 에는 자격증명이 없다. 사내에만 있는 의존성이 따로 있으면 여기서 실패한다 —
    그때는 「서버 시작 점검」 의 pip 출력 끝을 알려 준다.
  - 앱 포트는 시작 점검이 끝난 뒤에 열리므로 짧게 잡았다 — 두 pip 를 합쳐 240초, import 확인은 60초, pip 는 연결마다
    15초·재시도 2번에 포기한다.
- **자동 로그인**(`CAPA_BDQ_SECRET_KEY` 가 있고 `managed` 인 서버 — 2026-11-16 사용자 결정 D1 ~ D11) — 계정 · 비밀번호는
  환경변수 표에 두지 않고 Admin Area 「BDQ 자동 로그인」 에서 관리자만 넣는다. 그 키로 감싸 버킷 `secrets/bdq_login.json` 에 두고,
  시작 스크립트가 시작마다 그 계정으로 한 번 로그인한다(성공하면 `CAPA_BDQ_TOKEN` 은 쓰지 않는다 — 실패 · 닿지 못함이면 아래처럼
  그 값을 예비로 쓴다). 저장된 계정이 있으면 토큰 파일 이름과 조회 계정은 그 ID 다(`CAPA_BDQ_USER_NAME` 보다 앞).
  1. **키 만들기** — 사용자가 자기 창(사내 PC PowerShell 또는 WebIDE 터미널)에서 한 줄을 치고, 찍힌 44글자를 C-DEP 환경변수 표의
     `CAPA_BDQ_SECRET_KEY` 값에만 넣는다(파일 · 메일 · 리뷰 · 에이전트 대화에 옮기지 않는다). 그다음 CI/CD.

     ```
     uv run --no-sync python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```

  2. **계정 넣기** — 관리자가 Admin Area 「BDQ 자동 로그인」 펼침에서 계정 · 비밀번호를 넣고 「넣기」 를 누른다. 그 자리에서 한 번
     로그인해 보고 **성공했을 때만** 저장한다 — 실패면 저장하지 않고 폼 아래 한 줄만 보이며 앞서 저장된 계정은 그대로다. 성공 판정은
     로그인 앞뒤 토큰 파일 내용이 바뀌었는지이고, 남은 시간은 패키지의 `getTokenTime`(서버에 묻는 것으로 보인다 — 추정)으로 잰다.
     펼침에는 상태(없음 · 정상 · 멈춤과 까닭) · 마지막 결과와 남은 시간 · 넣은 관리자 앱 ID 앞 두 글자와 시각만 보이고 BDQ 계정
     ID 는 보이지 않는다. 바꾸는 길은 다시 넣기, 없애는 길은 「지우기」 하나다.
  3. **조회 중** — 토큰이 만료 · 무효라 조회가 패키지의 토큰 예외(`bigdataquery.exceptions` 의 종류 — 지금은 토큰 파일 없음
     하나, 무효 · 만료의 종류는 사내 확인 거리)로 실패하면 다시 로그인해 같은 조회를 한 번만 다시 한다. 패키지가 조회마다 토큰
     파일을 다시 읽으므로 앱을 다시 띄우지 않는다. 문구만 토큰처럼 보이는 실패 · 서버 혼잡(`queue full`)은 다시 로그인하지 않는다.
  4. **멈춤** — 로그인이 거절되거나 다시 한 조회도 토큰 오류면 다시 시도하지 않고 멈추며(관리자 알림 `AD-23`), 멈춤을 객체에 적어
     다시 띄워도 그대로다 — Admin Area 에서 계정을 다시 넣어 성공하면 풀린다. 서버에 닿지 못한 실패(연결 · 시간 초과)는 멈추지 않고
     다음 토큰 오류 · 재시작 때 다시 한다. 그 밖의 애매한 실패는 모두 멈춤이다 — 틀린 비밀번호로 거듭 로그인해 계정이 잠기는 것을
     막는 것이 먼저다(폼 한 번에 시도 한 번 · 자동 시도 연속 3번 상한 · 닿지 못함 뒤 5분 쉼).
  5. **예비 길** — 자동 로그인이 멈췄거나 계정이 없거나 닿지 못하면 지금까지처럼 `CAPA_BDQ_TOKEN`(시작 때) · 「토큰 넣기」(떠 있는
     동안)로 넣은 토큰을 쓴다. 키도 저장된 계정도 없는 서버는 지금과 같다.
  6. **WebIDE 와 같은 계정** — WebIDE(사내 PC)도 이 계정으로 시험 삼아 로그인할 수 있다. 운영 서버가 로그인하면 WebIDE 의 토큰이
     초기화될 수 있고(감수한다), 반대로 WebIDE 로그인이 운영 토큰을 죽이면 운영은 3 의 다시 로그인으로 돌아온다(D11).
  - 키를 바꾸거나 잃으면 저장된 계정을 풀 수 없어 「계정 없음」 이 된다 — Admin Area 에서 다시 넣는다. 「서버 시작 점검」 표의
    「BDQ 자동 로그인」 줄이 시작 때 결과다.
- 토큰은 `/config/.credential/bigdataquery.token.<CAPA_BDQ_USER_NAME>` 에 0600(폴더 0700)으로 쓴다(같은 내용이면
  다시 쓰지 않고 권한만 맞춘다). 패키지가 그 자리만 보므로 `/config` 에 못 쓰면 다른 곳에 쓰지 않고 실패로 적는다.
  앱은 `$DSUSER` 로 돌아 `/` 에 폴더를 만들 수 없으므로 이미지가 `/config/.credential` 을 미리 만들어 넘긴다.
  `base64:` 를 푼 내용이 비거나 문턱(`scripts/container_start.py` 의 `MIN_TOKEN_BYTES`)보다 짧으면(자리표시 · 잘못 붙인 몇 글자)
  토큰이 아닌 값으로 보고 쓰지 않고 실패로 적는다. 문턱은 진짜 토큰을 막지 않게 낮게 둔 값이다.
- 하위 프로세스(import 확인·pip)와 앱 프로세스에는 두 토큰을 넘기지 않는다 — 깔린 패키지의 import 코드가 그 값을 읽지 못하게
  한다. 앞 틀의 `CAPA_BDQ_REFRESH_TOKEN` 은 넣지 않는다(있으면 표에서 뺀다) — 남아 있어도 앱은 읽지 않고, 비밀이라 앱 · 하위 프로세스에 넘기지 않고 출력에서 가린다.

**통합인증(SSO) 칸** — 같은 환경변수 표에 넣는다. 이름과 뜻만 적는다(값 · 첫 배포 순서는 [`sso_setup.md`](sso_setup.md) 2 · 5장).

| key | 뜻 |
|---|---|
| `ADFS_CLIENT_ID` | 켜는 스위치 — 포털 승인 메일의 Client ID. 비면 통합인증 꺼짐(지금처럼 열림) |
| `JWT_SECRET_KEY` | 로그인 세션 토큰의 비밀값(32바이트 이상 고정값) |
| `APP_ENV` | `prod` 면 운영 규칙(https 만 · 꺼짐 경고) |
| `ADFS_AUTHORIZE_URL` · `ADFS_ISSUER` · `ADFS_SIGNING_CERT` | ADFS authorize 주소 · id_token 의 iss · 토큰 서명 인증서(한 줄) |
| `CAPA_PUBLIC_URL` | 브라우저가 여는 앱 주소(포털 Endpoint URL 은 이 값 + `/auth/callback`) |
| `CAPA_SSO_SESSION_HOURS` · `CAPA_SSO_SESSION_MAX_HOURS` | 선택 — 로그인 유지 시간(마지막 사용 뒤, 기본 6) · 써도 넘지 못하는 최대 시간(기본 24) |
| `CAPA_SSO` · `ADFS_SCOPE` · `ADFS_RESOURCE` · `ADFS_CLAIM_*` · `ADFS_LOGOUT_URL` | 선택 |
| `CAPA_ACCESS_ADMINS` | 접속 명단의 관리자 loginid 목록(쉼표 · 세미콜론 · 공백). **운영 필수** — 없으면 앱을 열지 않는다. 이 키를 모르는 앞 배포에 먼저 넣어도 해가 없다 |
| `CAPA_ACCESS_USERS` · `CAPA_ACCESS_CONTACT` | 선택 — 접속 명단의 사용자 loginid 목록(S3 명단을 켜면 파일이 없는 동안만 첫 판으로 쓴다) · 문의 줄의 창구 글(거절 화면 · 앱 안 로그인 멈춤 판 · 시작 임시 화면에 실린다 — 로그인 없이 누구나 본다, 사람 loginid 를 넣지 않는다 — `sso_setup.md` 2장) |
| `CAPA_S3_ACCESS_KEY` · `CAPA_S3_SECRET_KEY` | S3 명단용 앱 키 한 쌍(**비밀**) — 있으면 S3 명단이 켜져 사용자를 재시작 없이 Admin 에서 넣고 뺀다. 비면 환경변수 명단 그대로 |
| `CAPA_S3_ENDPOINT_URL` · `CAPA_S3_BUCKET` | S3 명단을 켜면 필수 — 주소 · 버킷 |
| `CAPA_S3_REGION` · `CAPA_ACCESS_S3_OBJECT` | 선택 — 서명 영역(기본 `us-east-1`) · 명단 파일 객체 키(기본 `access/access_list.json`) |

시작 스크립트는 이 값들을 앱에 넘기고(앱이 검증한다) 결과 파일에는 이름(있음/없음)만 남긴다. `JWT_SECRET_KEY` · S3 키 둘은 하위 프로세스에
넘기지 않고, 앱이 기동 때 읽은 뒤 프로세스 환경에서 지운다.

**앱 칸** — 같은 표에 넣는다. 선택이다.

| key | 뜻 |
|---|---|
| `CAPA_APP_CONTACT_EMAIL` | 사이드바 앱 정보 카드의 문의처 메일(사람을 가리키는 사내 값 — 저장소에 없다). 같은 메일이 앱 안 멈춤 판 셋(앱 시작 실패 · 접속 멈춤 · 한 화면 오류)과 앱 밖 화면(로그인 · 거절 · 설정 막힘)의 문의 줄에도 붙는다. 비었거나 메일 꼴이 아니면 카드 둘째 줄은 팀 이름만이고 문의 줄은 창구 글만(둘 다 없으면 줄 없음). 사내 PC 앱은 사용자 환경변수로 같은 값을 넣는다. 이 키를 모르는 앞 배포에 먼저 넣어도 해가 없다 |

시작 스크립트는 이 값을 그대로 앱에 넘긴다(결과 파일에는 남기지 않는다).

### 토큰 값 얻는 법

1. WebIDE 에서 위 1단계(로그인)를 한다 — `bdq.login()` 이 `/config/.credential/bigdataquery.token.<AD 계정>` 을 만든다.
2. 그 파일 내용을 `CAPA_BDQ_TOKEN` 값으로 넣는다. **줄바꿈이 있으면** value 칸에 그대로 못 넣으니 `base64:` 를
   앞에 붙인 한 줄로 넣는다 — WebIDE 터미널의 `base64 -w0 "/config/.credential/bigdataquery.token.$CAPA_BDQ_USER_NAME"` 출력이다(2단계의 계정 변수 —
   그 창에 없으면 파일을 찾지 못하고 멈춘다).
3. 토큰은 **주기적으로 만료된다.** 조회가 토큰 오류로 막히면 WebIDE 에서 다시 로그인해 새 토큰을 받는다. 바로 쓰려면
   관리자가 Admin Area 「서버 시작 점검」 의 **토큰 넣기** 에 그 내용(또는 위 `base64:` 한 줄)을 넣는다 — 시작 스크립트와 같은
   파일에 쓰고 패키지가 다음 조회부터 읽으며(조회마다 토큰을 다시 읽는다), CI/CD 를 누르지 않는다. 컨테이너를 다시 띄우면
   (CI/CD · 재시작) 시작 스크립트가 `CAPA_BDQ_TOKEN` 값으로 파일을 다시 쓰므로 그 값도 새 토큰으로 바꿔 둔다(다음 CI/CD 부터 쓰인다).
   - 넣기 칸은 비밀 칸이고 값은 화면 · 알림 · 로그 어디에도 남지 않는다. 비었거나 문턱보다 짧으면 넣지 않는다(시작 스크립트와 같은 판정).
   - 패키지는 프로세스 환경변수 `BIGDATAQUERY_LOGIN_TOKEN` 이 있으면 파일보다 그것을 먼저 읽는다 — 그 key 가 환경변수 표에 있으면
     넣기가 잠긴다(까닭 풍선). 계정(`CAPA_BDQ_USER_NAME`)이 없어도 파일 이름을 몰라 잠긴다.
   - WebIDE · 사내 PC 에는 넣기가 없다(통합인증이 꺼져 관리자가 없다) — WebIDE 는 위 1단계 로그인이 같은 파일을 쓴다.

### 결과 보는 곳

로그를 볼 수 없다고 보고 결과를 **앱 화면**에 둔다. 시작 스크립트는 `data/temp/container_start.json` 에 단계마다
`정상`·`건너뜀(까닭)`·`실패(까닭)`, 깔린 `bigdataquery` 판, 토큰 파일 있음/없음·수정 시각·자리, `CAPA_BDQ_USER_NAME`
있음/없음, 컨테이너의 실행 사용자·HOME, pip 출력 끝을 남긴다(계정 값은 모두 앞 두 글자만). 시작 점검이 도중에
예상하지 못하게 멈춰도 세 단계를 「도중에 멈춤」 실패로 적은 파일을 남기고 앱은 뜬다.

- **Admin Area 「서버 시작 점검」** — 탭 위 펼침 하나다. 파일이 있을 때만 선다(개발·사내 PC 에는 없다). 표 넷째 줄
  「통합인증」 은 결과 파일이 아니라 앱의 지금 설정에서 판정한다(정상 · 건너뜀(`ADFS_CLIENT_ID` 없음) · 실패(문제 이름)) — 시작
  때 있던 통합인증 환경변수 이름도 한 줄 붙는다.
- **Admin Area 「통합인증 점검」** — 바로 아래 펼침. 판정 · 환경변수 이름별 상태와 까닭 · 계산한 redirect_uri · 서명 인증서
  지문과 만료일 · 로그인 유지 시간과 「로그인 갱신」 누계 · 최근 로그인 사건. 꺼짐이고 운영(`APP_ENV=prod`)이 아니면 서지
  않는다([`sso_setup.md`](sso_setup.md) 7장).
- **BigDataQuery 안내** — 「패키지가 없습니다」·로그인 토큰 오류·`user_name` 안내 뒤에 그 단계의 결과 한 줄과 넣을
  환경변수 이름이 붙는다.
- **펼침이 「결과 없음」 이면** — CD 환경변수(`CAPA_ARTIFACTORY_*`·`CAPA_BDQ_TOKEN`)는 앱에 들어왔는데 결과 파일이
  없다는 뜻이다. 두 토큰이 앱에 그대로 있다고 나오면 시작 스크립트가 **돌지 않은** 것이다(스크립트는 그 값들을 앱에
  넘기지 않는다) — C-DEP 이 이미지 `CMD` 대신 다른 시작 명령을 쓴 것이라 이 길로는 풀 수 없으니 그 문구를 알려 준다.
  계정만 있다고 나오면 돌지 않았는지 `data/temp/` 에 쓰지 못했는지 가를 수 없다. 개발·사내 PC 처럼 CD 환경변수가
  없으면 펼침 자체가 없다.
- **펼침이 「결과 파일을 읽지 못함」 이면** — 결과 파일(`data/temp/container_start.json`)은 있는데 비었거나 JSON 이
  아니거나 앱이 모르는 꼴이다. 스크립트는 돌았다 — 쓰다 끊겼거나 이미지의 앱과 판이 다를 수 있으니 CI/CD 를 다시
  돌리고, 그래도 같으면 그 문구를 알려 준다. CD 환경변수가 없어도 파일이 있으면 선다.
- **토큰 실패 알림** — C-DEP 에서 조회가 토큰 갈래로 실패했거나(「조회가 실패했습니다(토큰)」) 시작 점검 토큰 줄이 「실패」 면
  관리자의 Alarm 에 `AD-10` 이 선다. 시작 점검 토큰 줄의 까닭대로 고쳐 CI/CD 를 다시 누르거나(시작 점검 실패), 「토큰 넣기」 로 새 토큰을
  넣은 뒤(조회 실패) 조회가 성공하면 풀린다 — 만료 전에 미리 갱신하지 않는다(자동 로그인이 서 있으면 조회 중 다시 로그인이 먼저 —
  위 「자동 로그인」 3). 패키지가 환경변수
  `BIGDATAQUERY_LOGIN_TOKEN` 을 읽는 서버는 넣기가 잠기니 알림도 그 값을 새 토큰으로 바꾸고 CI/CD 를 누르라고 한다. 실패한 조회가
  페이지 안이면 알림은 다음 회차부터 선다.
- **토큰 만료 알림** — 「서버 시작 점검」 의 「지금 토큰」 줄이 패키지가 지금 읽을 토큰의 자리 · 파일 수정 시각 · 만료 시각을 보인다.
  토큰에서 만료 시각을 읽을 수 있으면 만료 1시간 전부터(지난 뒤에도) 관리자의 Alarm 에 `AD-11` 이 서고 새 토큰을 넣으면 풀린다. 지금
  읽는 꼴은 JWT 의 `exp` 하나뿐이다 — 실제 토큰(WebIDE 실측 35바이트)의 꼴은 사내 확인 거리라, 읽지 못하면 줄이 `만료 모름` 이고 알림은
  서지 않는다(실패 뒤의 `AD-10` 이 뒷벽). 9999-12-31 같은 「만료 없음」 자리표시도 `만료 모름` 이다.
- **토큰 파일은 「정상」 인데 조회가 토큰 오류면** — 원문의 `AD user '…' at '…'` 가 펼침의 토큰 파일 자리와 같은지
  먼저 본다. 다르면 패키지가 다른 이름(실행 사용자 등)이나 자리(HOME 기준 등)를 보는 것이니 펼침의 실행 사용자·HOME 과
  함께 알려 준다. 같다면 토큰 만료다(위 3).

**비밀값(Artifactory 토큰·BDQ 토큰·표에 남은 옛 갱신 토큰·주소 안의 자격증명)은 파일·화면·표준 출력 어디에도 남기지 않는다** —
실행 줄의 세 토큰 값은 앱 프로세스에도 넘기지 않는다.

### 주의

- C-DEP 의 환경변수 표는 **그 프로젝트 사람에게 보일 수 있다.** Artifactory 토큰은 읽기 전용으로 발급하고,
  BDQ 토큰으로 하는 조회는 **넣은 사람 본인 권한**으로 나간다 — 그 서버로 조회하는 모든 사용자가 그 사람 이름으로
  조회한다는 뜻이다.
- 값은 사람마다 다르고 비밀이라 저장소·배포 ZIP 에 넣지 않는다(예시도 `<AD 계정>` 꼴로만 적는다).
- **환경변수 표를 본 사람은 `JWT_SECRET_KEY` 로 로그인 토큰을 만들 수 있다** — 통합인증을 켜면 그 표를 볼 수 있는 사람을 좁힌다.
- **환경변수 표를 본 사람은 S3 키와 `CAPA_BDQ_SECRET_KEY` 를 함께 쥔다** — 버킷의 `secrets/bdq_login.json` 을 받아 저장된
  BigDataQuery 계정 · 비밀번호를 풀 수 있다. 그 표를 볼 수 있는 사람을 좁히고, 키가 샜다고 보면 키를 새로 만들어 넣고 계정을 다시 넣는다.

## 참고

- 로컬 PC(Windows)에서는 `USERNAME` 환경변수와 Windows API 로 요청자가 자동 식별되어
  `login()` 도 `CAPA_BDQ_USER_NAME` 도 필요 없다.
- `setServerContext()` 는 C-DEP WebIDE 가 이미 서버로 감지되므로 호출할 필요가 없다.
- `getData(user_name=...)` 는 "다른 사용자 컨텍스트로 조회할 때만" 쓰는 것이 아니다 —
  **이 서버 환경에서는 항상 필요하다.** 예전 판에 그렇게 적혀 있었고, 그 문장 때문에 원인을
  찾는 데 두 세션이 걸렸다.
- 이 문서가 푸는 것은 조회 경로뿐이다. 배포 적용 절차 전체는
  [`internal_update_runbook.md`](internal_update_runbook.md) 에 있다.
