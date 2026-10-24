# Purpose: CD 컨테이너 시작 때 환경변수로 BDQ 설치·토큰 파일을 갖추고 결과를 남긴 뒤 앱이 된다.
"""C-DEP CD 컨테이너 시작 스크립트.

C-DEP 의 CD 는 시작 명령을 바꿀 수 없고(CI/CD 단추 → 통과하면 바로 실행·접속 링크만 준다) 서버
셸에도 들어갈 수 없다. 넣을 수 있는 것은 배포 설정의 **환경변수 표(key·value)** 뿐이다. 그래서
이미지의 `CMD` 가 이 스크립트를 부르고, 스크립트가 그 환경변수만으로 BigDataQuery 의 세 관문
(`docs/bigdataquery_webide_setup.md`)을 푼 뒤 지금과 같은 `streamlit run` 줄로 바뀐다.

0. 설치 — `bigdataquery` 가 없고 `CAPA_ARTIFACTORY_USER`·`CAPA_ARTIFACTORY_TOKEN` 이 있으면
   `requirements-company.txt` 의 판 고정 줄을 그 파일의 인덱스로 **추가 인덱스** 삼아 pip 로 깐다.
   이미지가 `PIP_INDEX_URL` 을 공개 미러로 고정해 `--index-url` 이 지기 때문이다. 앱 판 고정
   (`requirements.txt`)을 제약으로 걸어 사내 패키지가 앱 의존성을 바꾸지 못하게 한다.
1. 로그인 토큰 — `CAPA_BDQ_TOKEN` 과 `CAPA_BDQ_USER_NAME` 이 있으면 패키지가 보는 자리
   (`/config/.credential/bigdataquery.token.<계정>`)에 그 값을 쓴다(`base64:` 로 시작하면 풀어서).
2. 요청자 계정 — `CAPA_BDQ_USER_NAME` 은 앱이 그대로 읽는다. 있는지만 적는다.

결과는 `settings.CONTAINER_START_REPORT_PATH` 에 남고 앱 화면(Admin Area 「서버 시작 점검」)이
읽는다. **비밀값은 어디에도 남기지 않는다** — pip 출력·예외 문구의 토큰과 URL 자격증명을 가리고
계정은 앞 두 글자만 둔다. 어느 단계가 실패해도 앱은 띄운다. 앱은 `os.execvpe` 로 이 프로세스를
갈아 끼워 신호·종료 동작이 옛 `CMD` 와 같고, 실행 줄의 두 비밀값은 앱에 넘기지 않는다.

개발·사내 PC 에서는 부르지 않는다. 시험만 쓰는 내부 인자(`--credential-dir`·`--port`)가 있고, 운영
자리는 고정이다.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import signal
import subprocess
import sys
import urllib.parse
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Protocol

from capa_simulation import settings
from capa_simulation.io.container_start_report import (
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
INSTALL_TIMEOUT_SECONDS = 300
PROBE_TIMEOUT_SECONDS = 120
# 사내 CA 는 OS 인증서 묶음에 있다(WebIDE 에서 `curl` 이 OS 인증서로 통과했다). 있는 첫 묶음을
# pip 에 준다.
CA_BUNDLES: tuple[Path, ...] = (
    Path("/etc/ssl/certs/ca-certificates.crt"),
    Path("/etc/pki/tls/certs/ca-bundle.crt"),
)
PIP_TAIL_LINES = 8
PROBE_MARKER = "capa-bdq-probe"
# 앱에 넘기지 않는 실행 줄 값. 앱은 요청자 계정만 읽는다.
SECRET_ENVIRONMENT = (ARTIFACTORY_TOKEN_ENV, BDQ_TOKEN_ENV)
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
        self, args: Sequence[str], *, timeout: float
    ) -> subprocess.CompletedProcess[str]: ...


ExecApp = Callable[[str, list[str], dict[str, str]], object]


def run_command(args: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    """하위 프로세스 한 번. 입력을 닫아 대화형 질문에 걸려 멈추지 않게 한다."""
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=timeout,
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


def extra_index_url(index_url: str, user: str, token: str) -> str:
    """인덱스 주소에 자격증명을 넣는다. 계정·토큰의 `@`·`/`·`:` 가 주소를 깨지 않게 인코딩한다."""
    parts = urllib.parse.urlsplit(index_url)
    host = parts.netloc.rsplit("@", 1)[-1]
    credentials = f"{urllib.parse.quote(user, safe='')}:{urllib.parse.quote(token, safe='')}"
    return urllib.parse.urlunsplit(
        (parts.scheme, f"{credentials}@{host}", parts.path, parts.query, parts.fragment)
    )


def pip_install_command(
    requirement: CompanyRequirement,
    extra_url: str,
    *,
    user_site: bool,
    cert: Path | None,
    constraints: Path | None,
) -> list[str]:
    command = [sys.executable, "-m", "pip", "install"]
    if user_site:
        command.append("--user")
    command += [
        "--disable-pip-version-check",
        "--no-input",
        "--no-cache-dir",
        "--extra-index-url",
        extra_url,
    ]
    if cert is not None:
        command += ["--cert", str(cert)]
    if constraints is not None:
        command += ["-c", str(constraints)]
    return [*command, *requirement.pins]


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
    return {value, urllib.parse.quote(value, safe=""), urllib.parse.quote_plus(value)}


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


def probe_bigdataquery(runner: Runner) -> Probe:
    """`bigdataquery` 를 하위 프로세스에서 불러 본다 — 이 프로세스에 반쯤 불러온 모듈을 남기지
    않는다."""
    try:
        completed = runner([sys.executable, "-c", _PROBE_CODE], timeout=PROBE_TIMEOUT_SECONDS)
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


def install_step(environ: Mapping[str, str], runner: Runner, redactor: Redactor) -> InstallOutcome:
    probe = probe_bigdataquery(runner)
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
    command = pip_install_command(
        requirement,
        extra_index_url(requirement.index_url, user, token),
        user_site=not inside_virtualenv(),
        cert=next((bundle for bundle in CA_BUNDLES if bundle.is_file()), None),
        constraints=APP_REQUIREMENTS if APP_REQUIREMENTS.is_file() else None,
    )
    try:
        completed = runner(command, timeout=INSTALL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        tail = _pip_tail(error.output, error.stderr, redactor)
        reason = f"설치 시도 실패 — 제한시간 {INSTALL_TIMEOUT_SECONDS}초 넘김"
        return InstallOutcome(StepResult(STATUS_FAILED, reason), None, tail)
    except OSError as error:
        reason = f"설치 시도 실패 — pip 를 실행하지 못함({type(error).__name__})"
        return InstallOutcome(StepResult(STATUS_FAILED, reason), None, [redactor(str(error))])
    tail = _pip_tail(completed.stdout, completed.stderr, redactor)
    if completed.returncode != 0:
        reason = f"설치 시도 실패 — pip 종료 코드 {completed.returncode}"
        return InstallOutcome(StepResult(STATUS_FAILED, reason), None, tail)
    after = probe_bigdataquery(runner)
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
    try:
        if target.is_file() and target.read_bytes() == content:
            return StepResult(STATUS_OK, "같은 내용의 토큰 파일이 이미 있어 다시 쓰지 않음")
    except OSError:
        pass
    try:
        _write_private(target, content)
    except OSError as error:
        return StepResult(STATUS_FAILED, f"{credential_dir} 에 쓰지 못함({type(error).__name__})")
    return StepResult(STATUS_OK, "토큰 파일을 씀")


def _write_private(target: Path, content: bytes) -> None:
    """0600 파일로 쓴다. 같은 폴더의 임시 파일에 다 쓴 뒤 바꿔 끼워 반쯤 쓴 토큰을 남기지 않는다."""
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
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
            "exists": None if target is None else target.is_file(),
            "modified_at": None if target is None else _modified_at(target),
        },
        "user_name": {
            "present": bool(account),
            "masked": mask_account(account) if account else None,
        },
        "missing_environment": [
            name for name in CD_ENVIRONMENT if not environ.get(name, "").strip()
        ],
        "pip_tail": [redactor(line) for line in install.pip_tail],
    }


def write_report(report: Mapping[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def app_command(port: str) -> list[str]:
    """옛 `CMD` 와 같은 줄. `WORKDIR /project` 에서 `app.py` 를 찾는다."""
    return ["streamlit", "run", "app.py", "--server.port", port]


def app_environment(environ: Mapping[str, str]) -> dict[str, str]:
    return {name: value for name, value in environ.items() if name not in SECRET_ENVIRONMENT}


def _echo(text: str) -> None:
    print(f"[container_start] {text}", flush=True)


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
    redactor = Redactor.from_environ(env)
    previous = signal.getsignal(signal.SIGTERM)
    try:
        signal.signal(signal.SIGTERM, _exit_on_sigterm)
        installed = True
    except ValueError:
        installed = False
    try:
        report = collect_report(
            env,
            credential_dir=args.credential_dir,
            runner=runner,
            redactor=redactor,
            echo=lambda text: _echo(redactor(text)),
        )
        write_report(report, settings.CONTAINER_START_REPORT_PATH)
        _echo(f"결과 → {settings.CONTAINER_START_REPORT_PATH}")
    except Exception as error:
        _echo(redactor(f"결과를 남기지 못함 — {type(error).__name__}: {error}"))
    finally:
        if installed:
            signal.signal(signal.SIGTERM, signal.SIG_DFL if previous is None else previous)
    command = app_command(str(args.port))
    _echo("앱 시작: " + " ".join(command))
    os.chdir(PROJECT_ROOT)
    sys.stdout.flush()
    sys.stderr.flush()
    exec_app(command[0], command, app_environment(env))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
