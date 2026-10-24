# Purpose: CD 컨테이너 시작 때 환경변수로 BDQ 설치·토큰 파일을 갖추고 결과를 남긴 뒤 앱이 된다.
"""C-DEP CD 컨테이너 시작 스크립트.

C-DEP 의 CD 는 시작 명령을 바꿀 수 없고(CI/CD 단추 → 통과하면 바로 실행·접속 링크만 준다) 서버
셸에도 들어갈 수 없다. 넣을 수 있는 것은 배포 설정의 **환경변수 표(key·value)** 뿐이다. 그래서
이미지의 `CMD` 가 이 스크립트를 부르고, 스크립트가 그 환경변수만으로 BigDataQuery 의 세 관문
(`docs/bigdataquery_webide_setup.md`)을 푼 뒤 지금과 같은 `streamlit run` 줄로 바뀐다.

0. 설치 — `bigdataquery` 가 없고 `CAPA_ARTIFACTORY_USER`·`CAPA_ARTIFACTORY_TOKEN` 이 있으면 pip 를
   두 번 부른다. 판·인덱스는 `requirements-company.txt` 가 정본이다.
   - 패키지 자신은 **사내 인덱스 하나만** 보고 의존성 없이 깐다(`--no-deps`). 공개 미러를 함께 보면
     같은 이름·판의 공개 패키지가 이길 수 있다(의존성 혼동 — pip 는 인덱스를 차례로 고르지 않는다).
     자격증명은 명령줄이 아니라 그 pip 의 환경(`PIP_INDEX_URL`)으로 준다 — 명령줄은 `ps` 로 누구나
     본다. pip 설정 파일은 끈다(`PIP_CONFIG_FILE=os.devnull`) — 그 안의 추가 인덱스도 막는다.
   - 의존성은 이미지의 기본 인덱스로 채운다. 앱 판 고정(`requirements.txt`)을 제약으로 걸어 사내
     패키지가 앱 의존성을 바꾸지 못하게 한다. 이 pip 에는 자격증명이 하나도 없다.
1. 로그인 토큰 — `CAPA_BDQ_TOKEN` 과 `CAPA_BDQ_USER_NAME` 이 있으면 패키지가 보는 자리
   (`/config/.credential/bigdataquery.token.<계정>`)에 그 값을 쓴다(`base64:` 로 시작하면 풀어서).
2. 요청자 계정 — `CAPA_BDQ_USER_NAME` 은 앱이 그대로 읽는다. 있는지만 적는다.

결과는 `settings.CONTAINER_START_REPORT_PATH` 에 남고 앱 화면(Admin Area 「서버 시작 점검」)이
읽는다. **비밀값은 어디에도 남기지 않는다** — pip 출력·예외 문구의 토큰과 URL 자격증명을 가리고
계정은 앞 두 글자만 둔다. 하위 프로세스(import 확인·pip)에도 두 비밀값을 넘기지 않는다 — 깔린
패키지의 import 코드가 그 값을 읽지 못하게 한다. 어느 단계가 실패해도, 이 스크립트에서 예상하지
못한 예외가 나도 앱은 띄운다. 앱은 `os.execvpe` 로 이 프로세스를 갈아 끼워 신호·종료 동작이 옛
`CMD` 와 같고, 실행 줄의 두 비밀값은 앱에 넘기지 않는다.

개발·사내 PC 에서는 부르지 않는다. 시험만 쓰는 내부 인자(`--credential-dir`·`--port`)가 있고, 운영
자리는 고정이다.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import getpass
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
import urllib.parse
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Protocol

from capa_simulation import settings
from capa_simulation.io.container_start_report import (
    APP_WITHHELD_ENVIRONMENT,
    ARTIFACTORY_TOKEN_ENV,
    ARTIFACTORY_USER_ENV,
    BDQ_TOKEN_ENV,
    BDQ_USER_NAME_ENV,
    CD_ENVIRONMENT,
    REPORT_VERSION,
    STATUS_FAILED,
    STATUS_LABELS,
    STATUS_OK,
    STATUS_SKIPPED,
    STEP_INSTALL,
    STEP_LABELS,
    STEP_TOKEN,
    STEP_USER_NAME,
    mask_account,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPANY_REQUIREMENTS = PROJECT_ROOT / "requirements-company.txt"
APP_REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
# 패키지(`bdq.login()`·`getData()`)가 토큰을 찾는 자리. 패키지가 이 자리만 보므로 옮기지 않는다.
CREDENTIAL_DIR = Path("/config/.credential")
TOKEN_FILE_PREFIX = "bigdataquery.token."
APP_PORT = "8080"
# 앱 포트는 이 단계들이 끝난 뒤에야 열린다 — CD 의 상태 검사가 그 사이 컨테이너를 죽이지 않게
# 짧게 잡는다. 설치 제한은 두 pip 를 합친 것이고, pip 자신도 연결마다 짧게 포기한다.
INSTALL_TIMEOUT_SECONDS = 240
PROBE_TIMEOUT_SECONDS = 60
PIP_NETWORK_OPTIONS = ("--timeout", "15", "--retries", "2")
# 사내 인덱스만 보게 할 때 지우는 pip 환경변수 — 다른 출처를 더하는 것들이다.
PIP_OTHER_SOURCES_ENV = ("PIP_EXTRA_INDEX_URL", "PIP_FIND_LINKS", "PIP_NO_INDEX")
# 사내 CA 는 OS 인증서 묶음에 있다(WebIDE 에서 `curl` 이 OS 인증서로 통과했다). 있는 첫 묶음을
# pip 에 준다.
CA_BUNDLES: tuple[Path, ...] = (
    Path("/etc/ssl/certs/ca-certificates.crt"),
    Path("/etc/pki/tls/certs/ca-bundle.crt"),
)
PIP_TAIL_LINES = 8
PROBE_MARKER = "capa-bdq-probe"
# 앱과 하위 프로세스에 넘기지 않는 실행 줄 값. 앱은 요청자 계정만 읽는다. 앱 쪽 「결과 없음」
# 안내가 같은 이름으로 스크립트가 돌았는지 가른다.
SECRET_ENVIRONMENT = APP_WITHHELD_ENVIRONMENT
_PROBE_CODE = f"""
import importlib, importlib.metadata
try:
    importlib.import_module("bigdataquery")
except ModuleNotFoundError as error:
    if error.name in (None, "bigdataquery"):
        print("{PROBE_MARKER} missing", flush=True)
    else:
        print("{PROBE_MARKER} broken ModuleNotFoundError", flush=True)
except Exception as error:
    print("{PROBE_MARKER} broken " + type(error).__name__, flush=True)
else:
    try:
        version = importlib.metadata.version("bigdataquery")
    except Exception:
        version = "?"
    print("{PROBE_MARKER} ok " + version, flush=True)
"""
# 주소의 자격증명 칸 — 계정에 `@` 가 들어 있어도 경로(`/`) 앞의 마지막 `@` 까지 가린다.
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)[^\s/]+@")
_COMMENT = re.compile(r"(^|\s)#.*$")


class Runner(Protocol):
    def __call__(
        self, args: Sequence[str], *, timeout: float, env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]: ...


ExecApp = Callable[[str, list[str], dict[str, str]], object]


def run_command(
    args: Sequence[str], *, timeout: float, env: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    """하위 프로세스 한 번. 환경은 부르는 쪽이 고른 것만 넘기고, 입력을 닫아 대화형 질문에 걸려
    멈추지 않게 한다."""
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        env=dict(env),
        check=False,
    )


def inside_virtualenv() -> bool:
    """가상환경에서는 pip 가 `--user` 를 거절한다. 이미지에는 가상환경이 없다."""
    return sys.prefix != sys.base_prefix


@dataclass(frozen=True)
class CompanyRequirement:
    pins: tuple[str, ...]
    index_url: str


def read_company_requirement(path: Path | None = None) -> CompanyRequirement:
    """`requirements-company.txt` 의 판 고정 줄과 `--index-url`. 판·인덱스의 정본은 그 파일이다."""
    text = (COMPANY_REQUIREMENTS if path is None else path).read_text(encoding="utf-8")
    pins: list[str] = []
    index_url: str | None = None
    for raw in text.splitlines():
        line = _COMMENT.sub("", raw).strip()
        if not line:
            continue
        if line.startswith(("--index-url", "-i ")):
            value = line.split("=", 1)[1] if line.startswith("--index-url=") else line.split()[-1]
            index_url = value.strip()
        elif not line.startswith("-"):
            pins.append(line)
    if index_url is None or not pins:
        raise ValueError("판 고정 줄 또는 --index-url 이 없다")
    return CompanyRequirement(pins=tuple(pins), index_url=index_url)


def _quote(value: str) -> str:
    # 환경변수의 깨진 바이트는 surrogate 로 들어온다 — 원래 바이트대로 `%XX` 로 옮긴다.
    return urllib.parse.quote(value, safe="", errors="surrogateescape")


def index_url_with_credentials(index_url: str, user: str, token: str) -> str:
    """인덱스 주소에 자격증명을 넣는다. 계정·토큰의 `@`·`/`·`:` 가 주소를 깨지 않게 인코딩한다.
    이 주소는 pip 의 환경으로만 넘긴다 — 명령줄에 싣지 않는다."""
    parts = urllib.parse.urlsplit(index_url)
    host = parts.netloc.rsplit("@", 1)[-1]
    credentials = f"{_quote(user)}:{_quote(token)}"
    return urllib.parse.urlunsplit(
        (parts.scheme, f"{credentials}@{host}", parts.path, parts.query, parts.fragment)
    )


def _pip_base(user_site: bool) -> list[str]:
    command = [sys.executable, "-m", "pip", "install"]
    if user_site:
        command.append("--user")
    return [
        *command,
        "--disable-pip-version-check",
        "--no-input",
        "--no-cache-dir",
        *PIP_NETWORK_OPTIONS,
    ]


def company_pip_command(
    requirement: CompanyRequirement, *, user_site: bool, cert: Path | None
) -> list[str]:
    """사내 패키지 자신만 까는 pip. 인덱스는 환경(`company_pip_environment`)이 준다.

    `--no-deps` — 이 pip 는 사내 인덱스 하나만 보므로 공개 의존성은 다음 pip 몫이다.
    `--no-build-isolation` — sdist 를 빌드할 때 pip 가 띄우는 하위 pip 는 인덱스 주소(자격증명
    포함)를 명령줄로 받는다. 이미지에 깔린 setuptools 로 빌드해 그 하위 pip 를 띄우지 않는다.
    """
    command = [*_pip_base(user_site), "--no-deps", "--no-build-isolation"]
    if cert is not None:
        command += ["--cert", str(cert)]
    return [*command, *requirement.pins]


def dependency_pip_command(
    requirement: CompanyRequirement, *, user_site: bool, constraints: Path | None
) -> list[str]:
    """깔린 사내 패키지의 의존성을 이미지 기본 인덱스로 채우는 pip. 사내 패키지는 이미 깔려 있어
    다시 받지 않는다. 앱 판 고정을 제약으로 건다."""
    command = _pip_base(user_site)
    if constraints is not None:
        command += ["-c", str(constraints)]
    return [*command, *requirement.pins]


def child_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """하위 프로세스(import 확인·pip)에 넘기는 환경 — 두 비밀값을 뺀다."""
    return {name: value for name, value in environ.items() if name not in SECRET_ENVIRONMENT}


def company_pip_environment(environ: Mapping[str, str], index_url: str) -> dict[str, str]:
    """사내 인덱스 하나만 보는 pip 의 환경. 명령줄의 `--index-url` 이 환경을 이기므로 명령줄에는
    인덱스를 싣지 않고, 다른 출처(추가 인덱스·find-links·설정 파일)는 모두 지운다."""
    env = child_environment(environ)
    for name in PIP_OTHER_SOURCES_ENV:
        env.pop(name, None)
    env["PIP_INDEX_URL"] = index_url
    env["PIP_CONFIG_FILE"] = os.devnull
    return env


class Redactor:
    """비밀값을 `***` 로, URL 자격증명을 `***@` 로, 계정을 앞 두 글자로 바꾼다."""

    def __init__(self, secrets: Iterable[str], accounts: Iterable[str]) -> None:
        self._secrets = sorted(
            {form for value in secrets if value for form in _forms(value)}, key=len, reverse=True
        )
        self._accounts = sorted(
            {form for value in accounts if value for form in _forms(value)}, key=len, reverse=True
        )

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> Redactor:
        token = environ.get(BDQ_TOKEN_ENV, "").strip()
        secrets = [environ.get(ARTIFACTORY_TOKEN_ENV, "").strip(), token]
        if token.startswith("base64:"):
            secrets.append(token.removeprefix("base64:").strip())
            try:
                decoded = _decode_token(token).decode("utf-8", errors="replace")
            except ValueError:
                decoded = ""
            # 푼 내용의 줄 조각도 가린다. 너무 짧은 조각(`{`·`}`)까지 가리면 출력이 뭉개진다.
            pieces = [decoded.strip(), *(line.strip() for line in decoded.splitlines())]
            secrets += [piece for piece in pieces if len(piece) >= 8]
        accounts = [
            environ.get(ARTIFACTORY_USER_ENV, "").strip(),
            environ.get(BDQ_USER_NAME_ENV, "").strip(),
        ]
        return cls(secrets, accounts)

    def __call__(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        text = _URL_CREDENTIALS.sub(r"\g<scheme>***@", text)
        for account in self._accounts:
            text = text.replace(account, mask_account(account))
        return text


def _forms(value: str) -> set[str]:
    plus = urllib.parse.quote_plus(value, safe="", errors="surrogateescape")
    return {value, _quote(value), plus}


@dataclass(frozen=True)
class StepResult:
    status: str
    reason: str

    def as_json(self) -> dict[str, str]:
        return {"status": self.status, "reason": self.reason}


@dataclass(frozen=True)
class Probe:
    """`ok`(판)·`missing`(패키지 없음)·`broken`(있는데 불러오다 깨짐)·`unknown`(확인 실패)."""

    state: str
    version: str | None
    detail: str


def probe_bigdataquery(runner: Runner, env: Mapping[str, str]) -> Probe:
    """`bigdataquery` 를 하위 프로세스에서 불러 본다 — 이 프로세스에 반쯤 불러온 모듈을 남기지
    않는다. `env` 에는 비밀값이 없어야 한다(`child_environment`) — 패키지 import 코드가 돈다."""
    try:
        completed = runner(
            [sys.executable, "-c", _PROBE_CODE], timeout=PROBE_TIMEOUT_SECONDS, env=env
        )
    except subprocess.TimeoutExpired:
        return Probe("unknown", None, f"확인이 제한시간 {PROBE_TIMEOUT_SECONDS}초를 넘김")
    except OSError as error:
        return Probe("unknown", None, f"확인을 실행하지 못함({type(error).__name__})")
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(PROBE_MARKER + " "):
            state, _, detail = line[len(PROBE_MARKER) + 1 :].strip().partition(" ")
            if state == "ok":
                return Probe("ok", detail.strip() or "?", "")
            if state in ("missing", "broken"):
                return Probe(state, None, detail.strip())
    return Probe("unknown", None, f"확인 결과를 읽지 못함(종료 코드 {completed.returncode})")


def _pip_tail(stdout: object, stderr: object, redactor: Redactor) -> list[str]:
    lines: list[str] = []
    for chunk in (stdout, stderr):
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", errors="replace")
        if isinstance(chunk, str):
            lines += [line.rstrip() for line in chunk.splitlines() if line.strip()]
    return [redactor(line) for line in lines[-PIP_TAIL_LINES:]]


@dataclass(frozen=True)
class InstallOutcome:
    result: StepResult
    version: str | None
    pip_tail: list[str]


@dataclass(frozen=True)
class PipRun:
    """pip 한 번의 결과. `failure` 는 실패했을 때의 짧은 까닭(성공이면 `None`)."""

    failure: str | None
    tail: list[str]


def run_pip(
    runner: Runner,
    command: Sequence[str],
    env: Mapping[str, str],
    *,
    title: str,
    timeout: float,
    redactor: Redactor,
) -> PipRun:
    heading = f"── {title}"
    if timeout <= 0:
        return PipRun(f"설치 제한시간 {INSTALL_TIMEOUT_SECONDS}초를 다 써 {title} 를 하지 못함", [])
    try:
        completed = runner(command, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as error:
        tail = [heading, *_pip_tail(error.output, error.stderr, redactor)]
        return PipRun(f"{title} — 설치 제한시간 {INSTALL_TIMEOUT_SECONDS}초 넘김", tail)
    except OSError as error:
        reason = f"{title} — pip 를 실행하지 못함({type(error).__name__})"
        return PipRun(reason, [heading, redactor(str(error))])
    tail = [heading, *_pip_tail(completed.stdout, completed.stderr, redactor)]
    if completed.returncode != 0:
        return PipRun(f"{title} — pip 종료 코드 {completed.returncode}", tail)
    return PipRun(None, tail)


def install_step(
    environ: Mapping[str, str],
    runner: Runner,
    redactor: Redactor,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> InstallOutcome:
    child_env = child_environment(environ)
    probe = probe_bigdataquery(runner, child_env)
    if probe.state == "ok":
        return InstallOutcome(
            StepResult(STATUS_OK, f"이미 있음 — bigdataquery {probe.version}"), probe.version, []
        )
    if probe.state == "broken":
        reason = f"패키지는 있지만 불러오지 못함({probe.detail})"
        return InstallOutcome(StepResult(STATUS_FAILED, redactor(reason)), None, [])
    if probe.state == "unknown":
        reason = f"패키지가 있는지 확인하지 못함 — {probe.detail}"
        return InstallOutcome(StepResult(STATUS_FAILED, redactor(reason)), None, [])
    user = environ.get(ARTIFACTORY_USER_ENV, "").strip()
    token = environ.get(ARTIFACTORY_TOKEN_ENV, "").strip()
    missing = [
        name
        for name, value in ((ARTIFACTORY_USER_ENV, user), (ARTIFACTORY_TOKEN_ENV, token))
        if not value
    ]
    if missing:
        reason = f"CD 환경변수 {'·'.join(missing)} 없음 — 설치하지 않음"
        return InstallOutcome(StepResult(STATUS_SKIPPED, reason), None, [])
    try:
        requirement = read_company_requirement()
    except (OSError, ValueError) as error:
        reason = f"requirements-company.txt 에서 판·인덱스를 읽지 못함({type(error).__name__})"
        return InstallOutcome(StepResult(STATUS_FAILED, reason), None, [])
    user_site = not inside_virtualenv()
    deadline = clock() + INSTALL_TIMEOUT_SECONDS
    company = run_pip(
        runner,
        company_pip_command(
            requirement,
            user_site=user_site,
            cert=next((bundle for bundle in CA_BUNDLES if bundle.is_file()), None),
        ),
        company_pip_environment(
            environ, index_url_with_credentials(requirement.index_url, user, token)
        ),
        title="사내 인덱스에서 bigdataquery",
        timeout=deadline - clock(),
        redactor=redactor,
    )
    if company.failure is not None:
        reason = f"설치 시도 실패 — {company.failure}"
        return InstallOutcome(StepResult(STATUS_FAILED, reason), None, company.tail)
    dependencies = run_pip(
        runner,
        dependency_pip_command(
            requirement,
            user_site=user_site,
            constraints=APP_REQUIREMENTS if APP_REQUIREMENTS.is_file() else None,
        ),
        child_env,
        title="기본 인덱스에서 의존성",
        timeout=deadline - clock(),
        redactor=redactor,
    )
    tail = company.tail + dependencies.tail
    if dependencies.failure is not None:
        reason = f"설치 시도 실패 — bigdataquery 는 깔았지만 {dependencies.failure}"
        return InstallOutcome(StepResult(STATUS_FAILED, reason), None, tail)
    after = probe_bigdataquery(runner, child_env)
    if after.state != "ok":
        detail = after.detail or "패키지를 찾지 못함"
        reason = redactor(f"pip 는 끝났지만 불러오지 못함({detail})")
        return InstallOutcome(StepResult(STATUS_FAILED, reason), None, tail)
    return InstallOutcome(
        StepResult(STATUS_OK, f"설치함 — bigdataquery {after.version}"), after.version, tail
    )


def _decode_token(value: str) -> bytes:
    """`base64:` 로 시작하면 풀고, 아니면 글자 그대로. 풀 수 없으면 `ValueError`."""
    if not value.startswith("base64:"):
        return value.encode("utf-8")
    body = "".join(value.removeprefix("base64:").split())
    try:
        return base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("base64 값이 아니다") from error


def token_file_path(credential_dir: Path, account: str) -> Path | None:
    """계정 이름이 폴더 밖을 가리키면(`/`·`..`) `None`."""
    if not account or account in (".", "..") or "/" in account or "\\" in account:
        return None
    return credential_dir / f"{TOKEN_FILE_PREFIX}{account}"


def token_step(environ: Mapping[str, str], credential_dir: Path) -> StepResult:
    raw = environ.get(BDQ_TOKEN_ENV, "").strip()
    if not raw:
        return StepResult(STATUS_SKIPPED, f"CD 환경변수 {BDQ_TOKEN_ENV} 없음 — 만들지 않음")
    account = environ.get(BDQ_USER_NAME_ENV, "").strip()
    if not account:
        return StepResult(
            STATUS_FAILED, f"CD 환경변수 {BDQ_USER_NAME_ENV} 없음 — 토큰 파일 이름을 못 정함"
        )
    target = token_file_path(credential_dir, account)
    if target is None:
        return StepResult(STATUS_FAILED, "계정 이름에 파일 이름으로 못 쓰는 글자가 있음")
    try:
        content = _decode_token(raw)
    except ValueError:
        return StepResult(STATUS_FAILED, f"{BDQ_TOKEN_ENV} 의 base64: 값을 풀지 못함")
    if not content.strip():
        # `base64:` 만 넣었거나 빈 출력을 붙여 넣은 값 — 빈 파일은 「정상」 이 아니다.
        return StepResult(STATUS_FAILED, f"{BDQ_TOKEN_ENV} 를 푼 내용이 비었음 — 파일을 쓰지 않음")
    try:
        same = target.is_file() and target.read_bytes() == content
    except OSError:
        same = False
    if same:
        try:
            _tighten(target, 0o600)
        except OSError as error:
            reason = f"같은 내용의 토큰 파일 권한을 0600 으로 맞추지 못함({type(error).__name__})"
            return StepResult(STATUS_FAILED, reason)
        _tighten_folder(target.parent)
        return StepResult(STATUS_OK, "같은 내용의 토큰 파일이 이미 있어 다시 쓰지 않음")
    try:
        _write_private(target, content)
    except OSError as error:
        return StepResult(STATUS_FAILED, f"{credential_dir} 에 쓰지 못함({type(error).__name__})")
    return StepResult(STATUS_OK, "토큰 파일을 씀")


def _tighten(path: Path, mode: int) -> None:
    """권한이 `mode` 와 다르면(그룹·다른 사람이 읽을 수 있는 0644 등) `mode` 로 맞춘다."""
    if stat.S_IMODE(path.stat().st_mode) != mode:
        os.chmod(path, mode)


def _tighten_folder(folder: Path) -> None:
    """이미 있던 토큰 폴더도 0700 으로 좁힌다(`mkdir` 의 mode 는 새로 만들 때만 먹는다). 남의
    폴더라 못 좁혀도 토큰 파일은 0600 이라 단계를 실패로 보지 않는다."""
    try:
        _tighten(folder, 0o700)
    except OSError:
        pass


def _write_private(target: Path, content: bytes) -> None:
    """0600 파일로 쓴다. 같은 폴더의 임시 파일에 다 쓴 뒤 바꿔 끼워 반쯤 쓴 토큰을 남기지 않는다."""
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _tighten_folder(target.parent)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def user_name_step(environ: Mapping[str, str]) -> StepResult:
    if environ.get(BDQ_USER_NAME_ENV, "").strip():
        return StepResult(STATUS_OK, "있음")
    return StepResult(
        STATUS_SKIPPED, f"CD 환경변수 {BDQ_USER_NAME_ENV} 없음 — 조회가 user_name 으로 거부됨"
    )


def _guarded(action: Callable[[], StepResult], redactor: Redactor) -> StepResult:
    """예상하지 못한 실패도 그 단계의 실패로만 적는다 — 다음 단계와 앱 띄우기는 이어간다."""
    try:
        result = action()
    except Exception as error:
        result = StepResult(STATUS_FAILED, f"예상하지 못한 실패({type(error).__name__}: {error})")
    return StepResult(result.status, redactor(result.reason))


def _modified_at(path: Path) -> str | None:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(stamp).astimezone().isoformat(timespec="seconds")


def _file_state(path: Path) -> bool | None:
    """있으면 `True`, 없으면 `False`, 들어가 볼 수 없으면 `None`. 3.10 의 `Path.is_file()` 은
    권한 오류(EACCES)를 삼키지 않고 올린다 — 그러면 결과 파일이 통째로 사라진다."""
    try:
        return stat.S_ISREG(path.stat().st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return None


def runtime_facts(environ: Mapping[str, str], redactor: Redactor) -> dict[str, object]:
    """컨테이너의 실행 사용자·HOME(가린 꼴). 패키지가 토큰 파일 이름·자리를 계정 값이 아니라 이
    둘로 정한다면 화면에서 어긋남을 가를 수 있게 싣는다."""
    try:
        os_user = getpass.getuser().strip()
    except Exception:
        os_user = ""
    account = environ.get(BDQ_USER_NAME_ENV, "").strip()
    home = environ.get("HOME", "").strip()
    if home and os_user:
        home = "/".join(mask_account(part) if part == os_user else part for part in home.split("/"))
    return {
        "os_user": mask_account(os_user) if os_user else None,
        "os_user_is_bdq_user": (os_user == account) if os_user and account else None,
        "home": redactor(home) if home else None,
    }


def collect_report(
    environ: Mapping[str, str],
    *,
    credential_dir: Path,
    runner: Runner,
    redactor: Redactor,
    echo: Callable[[str], None],
) -> dict[str, object]:
    """세 단계를 차례로 돌려 결과 파일에 쓸 내용을 만든다. 값은 모두 가린 꼴이다."""
    echo(f"{STEP_LABELS[STEP_INSTALL]} 확인")
    install = InstallOutcome(StepResult(STATUS_FAILED, ""), None, [])

    def run_install() -> StepResult:
        nonlocal install
        install = install_step(environ, runner, redactor)
        return install.result

    steps = {
        STEP_INSTALL: _guarded(run_install, redactor),
        STEP_TOKEN: _guarded(lambda: token_step(environ, credential_dir), redactor),
        STEP_USER_NAME: _guarded(lambda: user_name_step(environ), redactor),
    }
    for name, result in steps.items():
        echo(f"{STEP_LABELS[name]} — {STATUS_LABELS[result.status]}: {result.reason}")
    account = environ.get(BDQ_USER_NAME_ENV, "").strip()
    target = token_file_path(credential_dir, account) if account else None
    return {
        "version": REPORT_VERSION,
        "written_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "steps": {name: result.as_json() for name, result in steps.items()},
        "bigdataquery_version": install.version,
        "token_file": {
            "exists": None if target is None else _file_state(target),
            "modified_at": None if target is None else _modified_at(target),
            "path": None if target is None else redactor(str(target)),
        },
        "runtime": runtime_facts(environ, redactor),
        "user_name": {
            "present": bool(account),
            "masked": mask_account(account) if account else None,
        },
        "missing_environment": [
            name for name in CD_ENVIRONMENT if not environ.get(name, "").strip()
        ],
        "pip_tail": [redactor(line) for line in install.pip_tail],
    }


def fallback_report(environ: Mapping[str, str], error_name: str) -> dict[str, object]:
    """시작 점검이 도중에 예상하지 못하게 멈췄을 때 남기는 꼴 — 화면이 「결과 없음」 대신 멈춘 것을
    알린다. 값에서 나온 글은 싣지 않는다(가리기 전에 멈췄을 수 있다)."""
    reason = f"시작 점검이 도중에 멈춤({error_name}) — 이 단계의 결과를 모름"
    return {
        "version": REPORT_VERSION,
        "written_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "steps": {name: StepResult(STATUS_FAILED, reason).as_json() for name in STEP_LABELS},
        "bigdataquery_version": None,
        "token_file": {"exists": None, "modified_at": None, "path": None},
        "missing_environment": [
            name for name in CD_ENVIRONMENT if not environ.get(name, "").strip()
        ],
        "pip_tail": [],
    }


def write_report(report: Mapping[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    # 환경변수의 깨진 바이트(surrogate)가 가린 글에 남아도 쓰기가 깨지지 않게 한다.
    text = json.dumps(report, ensure_ascii=False, indent=2)
    temporary.write_text(text, encoding="utf-8", errors="replace")
    os.replace(temporary, path)


def app_command(port: str) -> list[str]:
    """옛 `CMD` 와 같은 줄. `WORKDIR /project` 에서 `app.py` 를 찾는다."""
    return ["streamlit", "run", "app.py", "--server.port", port]


def app_environment(environ: Mapping[str, str]) -> dict[str, str]:
    return {name: value for name, value in environ.items() if name not in SECRET_ENVIRONMENT}


def _echo(text: str) -> None:
    """진행 한 줄. 표준 출력이 UTF-8 이 아니거나 닫혀 있어도 예외를 내지 않는다 — 이 출력 하나가
    앱 띄우기를 막으면 안 된다."""
    line = f"[container_start] {text}\n"
    stream = sys.stdout
    try:
        stream.write(line)
        stream.flush()
    except UnicodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        try:
            stream.write(line.encode(encoding, errors="replace").decode(encoding))
            stream.flush()
        except Exception:
            pass
    except Exception:
        pass


def _exit_on_sigterm(signum: int, frame: FrameType | None) -> None:
    """설치를 기다리는 동안 컨테이너를 멈추면 바로 끝낸다 — PID 1 은 처리기가 없으면 SIGTERM 을
    흘린다. `subprocess.run` 은 예외에 자식(pip)을 죽이고 올린다."""
    raise SystemExit(128 + signum)


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="C-DEP CD 컨테이너 시작 스크립트")
    parser.add_argument(
        "--credential-dir", type=Path, default=CREDENTIAL_DIR, help=argparse.SUPPRESS
    )
    parser.add_argument("--port", default=APP_PORT, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    runner: Runner = run_command,
    exec_app: ExecApp = os.execvpe,
) -> int:
    args = _parse(argv)
    env = dict(os.environ if environ is None else environ)
    previous = signal.getsignal(signal.SIGTERM)
    try:
        signal.signal(signal.SIGTERM, _exit_on_sigterm)
        installed = True
    except ValueError:
        installed = False
    try:
        check_and_record(env, credential_dir=args.credential_dir, runner=runner)
    finally:
        if installed:
            signal.signal(signal.SIGTERM, signal.SIG_DFL if previous is None else previous)
    command = app_command(str(args.port))
    _echo("앱 시작: " + " ".join(command))
    os.chdir(PROJECT_ROOT)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    exec_app(command[0], command, app_environment(env))
    return 0


def check_and_record(environ: Mapping[str, str], *, credential_dir: Path, runner: Runner) -> None:
    """세 단계를 돌려 결과 파일을 남긴다. 여기서 난 어떤 `Exception` 도 앱 띄우기를 막지 않는다 —
    가리개를 만들기 전에 멈췄으면 종류 이름만 찍는다(값이 든 문구를 가릴 수 없다)."""
    redactor: Redactor | None = None
    report: Mapping[str, object]
    try:
        active = Redactor.from_environ(environ)
        redactor = active
        report = collect_report(
            environ,
            credential_dir=credential_dir,
            runner=runner,
            redactor=active,
            echo=lambda text: _echo(active(text)),
        )
    except Exception as error:
        detail = (
            type(error).__name__
            if redactor is None
            else redactor(f"{type(error).__name__}: {error}")
        )
        _echo(f"시작 점검이 도중에 멈춤 — {detail}")
        report = fallback_report(environ, type(error).__name__)
    try:
        write_report(report, settings.CONTAINER_START_REPORT_PATH)
        _echo(f"결과 → {settings.CONTAINER_START_REPORT_PATH}")
    except Exception as error:
        detail = type(error).__name__
        if redactor is not None:
            detail = redactor(f"{detail}: {error}")
        _echo(f"결과를 남기지 못함 — {detail}")


if __name__ == "__main__":
    raise SystemExit(main())
