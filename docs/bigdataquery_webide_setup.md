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

추가 인덱스로 넣고 시스템 인증서를 쓰게 한다.

```bash
export UV_EXTRA_INDEX_URL="https://<AD 계정>:<Artifactory API 토큰>@artifactory.samsungds.net/repository/dataservice-devsecops-pypi/simple"
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
자동으로 쓴다. **주기적으로 만료되므로** 같은 예외가 다시 뜨면 이 단계를 다시 하면 된다.

## 2. 요청자 계정 — `user_name` 을 채운다

**로그인과 토큰이 모두 정상인데도** 조회하면 이렇게 뜬다.

```
Parameter user_name is necessary.
```

로그인 토큰과 `user_name` 전달은 **별개**다. 서버(Linux) 환경에는 Windows 처럼 요청자를
자동으로 알아낼 경로가 없다 — 이 컨테이너에서 `echo $USERNAME` 은 비어 있다.

환경변수에 본인 AD 계정을 넣는다.

```bash
export CAPA_BDQ_USER_NAME="<AD 계정>"
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
`streamlit run app.py --server.port 8080` 으로 바뀐다. 어느 단계가 실패해도 앱은 뜬다.

### 넣을 환경변수

| key | value | 푸는 단계 |
|---|---|---|
| `CAPA_ARTIFACTORY_USER` | 사내 Artifactory 계정(`<AD 계정>`) | 0. 설치 |
| `CAPA_ARTIFACTORY_TOKEN` | Artifactory API 토큰(읽기 전용으로 발급한 것) | 0. 설치 |
| `CAPA_BDQ_TOKEN` | WebIDE 에서 로그인해 만든 토큰 파일의 **내용**(아래) | 1. 로그인 |
| `CAPA_BDQ_USER_NAME` | 본인 AD 계정(`<AD 계정>`) — 토큰 파일 이름과 `getData(user_name=…)` 에 함께 쓴다 | 1·2 |

- 설치는 `bigdataquery` 가 없을 때만 하고, 판과 인덱스는 `requirements-company.txt` 를 읽는다. pip 를 두 번 부른다.
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
- 토큰은 `/config/.credential/bigdataquery.token.<CAPA_BDQ_USER_NAME>` 에 0600(폴더 0700)으로 쓴다(같은 내용이면
  다시 쓰지 않고 권한만 맞춘다). 패키지가 그 자리만 보므로 `/config` 에 못 쓰면 다른 곳에 쓰지 않고 실패로 적는다.
  앱은 `$DSUSER` 로 돌아 `/` 에 폴더를 만들 수 없으므로 이미지가 `/config/.credential` 을 미리 만들어 넘긴다.
  `base64:` 를 푼 내용이 비면 쓰지 않고 실패로 적는다.
- 하위 프로세스(import 확인·pip)와 앱 프로세스에는 두 토큰을 넘기지 않는다 — 깔린 패키지의 import 코드가 그 값을
  읽지 못하게 한다.

### 토큰 값 얻는 법

1. WebIDE 에서 위 1단계(로그인)를 한다 — `bdq.login()` 이 `/config/.credential/bigdataquery.token.<AD 계정>` 을 만든다.
2. 그 파일 내용을 `CAPA_BDQ_TOKEN` 값으로 넣는다. **줄바꿈이 있으면** value 칸에 그대로 못 넣으니 `base64:` 를
   앞에 붙인 한 줄로 넣는다 — WebIDE 터미널의 `base64 -w0 /config/.credential/bigdataquery.token.<AD 계정>` 출력이다.
3. 토큰은 **주기적으로 만료된다.** 조회가 토큰 오류로 막히면 WebIDE 에서 다시 로그인해 값을 바꾸고 CI/CD 를 다시
   돌린다(시작 스크립트는 컨테이너가 설 때만 돈다).

### 결과 보는 곳

로그를 볼 수 없다고 보고 결과를 **앱 화면**에 둔다. 시작 스크립트는 `data/temp/container_start.json` 에 단계마다
`정상`·`건너뜀(까닭)`·`실패(까닭)`, 깔린 `bigdataquery` 판, 토큰 파일 있음/없음·수정 시각·자리, `CAPA_BDQ_USER_NAME`
있음/없음, 컨테이너의 실행 사용자·HOME, pip 출력 끝을 남긴다(계정 값은 모두 앞 두 글자만). 시작 점검이 도중에
예상하지 못하게 멈춰도 세 단계를 「도중에 멈춤」 실패로 적은 파일을 남기고 앱은 뜬다.

- **Admin Area 「서버 시작 점검」** — 탭 위 펼침 하나다. 파일이 있을 때만 선다(개발·사내 PC 에는 없다).
- **BigDataQuery 안내** — 「패키지가 없습니다」·로그인 토큰 오류·`user_name` 안내 뒤에 그 단계의 결과 한 줄과 넣을
  환경변수 이름이 붙는다.
- **펼침이 「결과 없음」 이면** — CD 환경변수(`CAPA_ARTIFACTORY_*`·`CAPA_BDQ_TOKEN`)는 앱에 들어왔는데 결과 파일이
  없다는 뜻이다. 두 토큰이 앱에 그대로 있다고 나오면 시작 스크립트가 **돌지 않은** 것이다(스크립트는 그 둘을 앱에
  넘기지 않는다) — C-DEP 이 이미지 `CMD` 대신 다른 시작 명령을 쓴 것이라 이 길로는 풀 수 없으니 그 문구를 알려 준다.
  계정만 있다고 나오면 돌지 않았는지 `data/temp/` 에 쓰지 못했는지 가를 수 없다. 개발·사내 PC 처럼 CD 환경변수가
  없으면 펼침 자체가 없다.
- **토큰 파일은 「정상」 인데 조회가 토큰 오류면** — 원문의 `AD user '…' at '…'` 가 펼침의 토큰 파일 자리와 같은지
  먼저 본다. 다르면 패키지가 다른 이름(실행 사용자 등)이나 자리(HOME 기준 등)를 보는 것이니 펼침의 실행 사용자·HOME 과
  함께 알려 준다. 같다면 토큰 만료다(위 3).

**비밀값(Artifactory 토큰·BDQ 토큰·주소 안의 자격증명)은 파일·화면·표준 출력 어디에도 남기지 않는다** — 실행 줄의
두 토큰은 앱 프로세스에도 넘기지 않는다.

### 주의

- C-DEP 의 환경변수 표는 **그 프로젝트 사람에게 보일 수 있다.** Artifactory 토큰은 읽기 전용으로 발급하고,
  BDQ 토큰으로 하는 조회는 **넣은 사람 본인 권한**으로 나간다 — 그 서버로 조회하는 모든 사용자가 그 사람 이름으로
  조회한다는 뜻이다.
- 값은 사람마다 다르고 비밀이라 저장소·배포 ZIP 에 넣지 않는다(예시도 `<AD 계정>` 꼴로만 적는다).

## 참고

- 로컬 PC(Windows)에서는 `USERNAME` 환경변수와 Windows API 로 요청자가 자동 식별되어
  `login()` 도 `CAPA_BDQ_USER_NAME` 도 필요 없다.
- `setServerContext()` 는 C-DEP WebIDE 가 이미 서버로 감지되므로 호출할 필요가 없다.
- `getData(user_name=...)` 는 "다른 사용자 컨텍스트로 조회할 때만" 쓰는 것이 아니다 —
  **이 서버 환경에서는 항상 필요하다.** 예전 판에 그렇게 적혀 있었고, 그 문장 때문에 원인을
  찾는 데 두 세션이 걸렸다.
- 이 문서가 푸는 것은 조회 경로뿐이다. 배포 적용 절차 전체는
  [`internal_update_runbook.md`](internal_update_runbook.md) 에 있다.
