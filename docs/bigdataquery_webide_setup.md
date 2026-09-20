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
uv run --no-sync python -m streamlit run app.py
```

## 참고

- 로컬 PC(Windows)에서는 `USERNAME` 환경변수와 Windows API 로 요청자가 자동 식별되어
  `login()` 도 `CAPA_BDQ_USER_NAME` 도 필요 없다.
- `setServerContext()` 는 C-DEP WebIDE 가 이미 서버로 감지되므로 호출할 필요가 없다.
- `getData(user_name=...)` 는 "다른 사용자 컨텍스트로 조회할 때만" 쓰는 것이 아니다 —
  **이 서버 환경에서는 항상 필요하다.** 예전 판에 그렇게 적혀 있었고, 그 문장 때문에 원인을
  찾는 데 두 세션이 걸렸다.
- 이 문서가 푸는 것은 조회 경로뿐이다. 배포 적용 절차 전체는
  [`internal_update_runbook.md`](internal_update_runbook.md) 에 있다.
