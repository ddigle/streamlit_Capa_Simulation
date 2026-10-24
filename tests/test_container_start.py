# Purpose: CD 컨테이너 시작 스크립트의 설치·토큰 파일·결과 기록·비밀값 가림·실행 인자를 고정한다.

"""컨테이너 시작 스크립트(`scripts/container_start.py`).

CD 서버에는 셸이 없고 시작 명령도 바꿀 수 없다 — 이 스크립트가 런타임 환경변수만으로 사내
`bigdataquery` 설치·로그인 토큰 파일·요청자 계정을 갖추고, 결과를 파일로 남긴 뒤 지금과 같은
`streamlit run` 줄로 바뀐다. pip·하위 프로세스·`exec` 는 모두 가짜로 바꿔 부른다.

여기 쓰는 계정·토큰은 **분명한 가짜 문자열**이다. 저장소가 공개라 실제 값을 넣지 않는다.
"""

from __future__ import annotations

import base64
import fnmatch
import getpass
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import urllib.parse
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

import capa_simulation.settings as settings
from capa_simulation.io import container_start_report as report_contract

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import container_start  # noqa: E402

FAKE_ART_USER = "fake.ci-user@example"
FAKE_ART_TOKEN = "FAKE-artifactory/token+secret=="
FAKE_BDQ_USER = "fakeaccount"
FAKE_BDQ_TOKEN = "FAKE-bdq-login-token-0000"
FAKE_PIN = "bigdataquery==9.9.9"
FAKE_INDEX = "https://index.example.invalid/repository/fake-pypi/simple"

ALL_ENVIRONMENT = {
    report_contract.ARTIFACTORY_USER_ENV: FAKE_ART_USER,
    report_contract.ARTIFACTORY_TOKEN_ENV: FAKE_ART_TOKEN,
    report_contract.BDQ_TOKEN_ENV: FAKE_BDQ_TOKEN,
    report_contract.BDQ_USER_NAME_ENV: FAKE_BDQ_USER,
}

OLD_CMD = ["streamlit", "run", "app.py", "--server.port", "8080"]


def _probe(state: str, detail: str = "") -> str:
    return f"bigdataquery 이 import 때 찍는 잡음\n{container_start.PROBE_MARKER} {state} {detail}\n"


def _is_probe(args: Sequence[str]) -> bool:
    return list(args[:2]) == [sys.executable, "-c"]


PipAnswer = subprocess.CompletedProcess[str] | BaseException


class FakeRunner:
    """하위 프로세스 대역. `python -c` 는 import 확인, 그 밖은 pip 다(pip 의 `-c` 는 제약 파일).

    `pip` 가 목록이면 pip 를 부를 때마다 앞에서부터 하나씩, 하나면 늘 그것을 돌려준다. 부를 때 받은
    환경도 남긴다 — 비밀값이 하위 프로세스에 들어가지 않는지 본다."""

    def __init__(
        self,
        probes: Sequence[str],
        pip: PipAnswer | Sequence[PipAnswer] | None = None,
    ) -> None:
        self.probes = list(probes)
        self.repeat: PipAnswer | None = None
        self.answers: list[PipAnswer] = []
        if isinstance(pip, (subprocess.CompletedProcess, BaseException)):
            self.repeat = pip
        elif pip is not None:
            self.answers = list(pip)
        self.calls: list[list[str]] = []
        self.timeouts: list[float] = []
        self.envs: list[dict[str, str]] = []

    def __call__(
        self, args: Sequence[str], *, timeout: float, env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        self.timeouts.append(timeout)
        self.envs.append(dict(env))
        if _is_probe(args):
            return subprocess.CompletedProcess(list(args), 0, stdout=self.probes.pop(0), stderr="")
        answer = self.answers.pop(0) if self.answers else self.repeat
        assert answer is not None, (
            "pip 를 부르지 않아야 하는 시험에서 pip 를 불렀다(또는 더 불렀다)"
        )
        if isinstance(answer, BaseException):
            raise answer
        return answer

    @property
    def pip_calls(self) -> list[list[str]]:
        return [call for call in self.calls if not _is_probe(call)]

    @property
    def pip_envs(self) -> list[dict[str, str]]:
        return [env for call, env in zip(self.calls, self.envs, strict=True) if not _is_probe(call)]


class FakeExec:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], dict[str, str]]] = []

    def __call__(self, file: str, args: Sequence[str], env: Mapping[str, str]) -> None:
        self.calls.append((file, list(args), dict(env)))


@pytest.fixture
def place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """결과 파일·요구 파일·인증서 묶음을 tmp 로 옮긴다. 운영 자리(`/config`)는 건드리지 않는다."""
    monkeypatch.setattr(
        settings, "CONTAINER_START_REPORT_PATH", tmp_path / "data" / "temp" / "container_start.json"
    )
    company = tmp_path / "requirements-company.txt"
    company.write_text(
        "# 머리 주석 — 이 파일의 `--index-url` 은 주석 안이라 읽지 않는다\n"
        f"#     --index-url https://comment.example.invalid/simple\n\n"
        f"--index-url {FAKE_INDEX}  # 꼬리 주석\n\n{FAKE_PIN}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(container_start, "COMPANY_REQUIREMENTS", company)
    constraints = tmp_path / "requirements.txt"
    constraints.write_text("pandas==2.0.0\n", encoding="utf-8")
    monkeypatch.setattr(container_start, "APP_REQUIREMENTS", constraints)
    bundle = tmp_path / "ca-certificates.crt"
    bundle.write_text("가짜 인증서 묶음\n", encoding="utf-8")
    monkeypatch.setattr(container_start, "CA_BUNDLES", (tmp_path / "없는 묶음.crt", bundle))
    monkeypatch.setattr(container_start, "inside_virtualenv", lambda: False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _main(
    place: Path,
    environ: Mapping[str, str],
    runner: FakeRunner,
    *,
    credential_dir: Path | None = None,
) -> tuple[dict[str, object], FakeExec]:
    fake_exec = FakeExec()
    credentials = credential_dir or place / "config" / ".credential"
    container_start.main(
        ["--credential-dir", str(credentials)],
        environ=dict(environ),
        runner=runner,
        exec_app=fake_exec,
    )
    written = json.loads(settings.CONTAINER_START_REPORT_PATH.read_text(encoding="utf-8"))
    assert isinstance(written, dict)
    return written, fake_exec


def _steps(report: Mapping[str, object]) -> dict[str, dict[str, str]]:
    steps = report["steps"]
    assert isinstance(steps, dict)
    return steps


def _ok(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


def _assert_no_secret(text: str) -> None:
    for secret in (
        FAKE_ART_TOKEN,
        urllib.parse.quote(FAKE_ART_TOKEN, safe=""),
        FAKE_BDQ_TOKEN,
        FAKE_ART_USER,
        urllib.parse.quote(FAKE_ART_USER, safe=""),
        FAKE_BDQ_USER,
    ):
        assert secret not in text, f"비밀값·계정 원문이 남았다: {secret!r}"


def test_without_cd_environment_it_installs_nothing_and_starts_the_same_app(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """개발·사내 PC 처럼 CD 환경변수가 하나도 없으면 설치도 토큰도 건너뛰고 지금 CMD 그대로
    띄운다."""
    runner = FakeRunner([_probe("missing")])

    report, fake_exec = _main(place, {"PATH": "/usr/bin"}, runner)

    assert runner.pip_calls == []
    steps = _steps(report)
    assert {name: step["status"] for name, step in steps.items()} == {
        report_contract.STEP_INSTALL: report_contract.STATUS_SKIPPED,
        report_contract.STEP_TOKEN: report_contract.STATUS_SKIPPED,
        report_contract.STEP_USER_NAME: report_contract.STATUS_SKIPPED,
    }
    assert report_contract.ARTIFACTORY_USER_ENV in steps[report_contract.STEP_INSTALL]["reason"]
    assert report["missing_environment"] == list(report_contract.CD_ENVIRONMENT)
    assert not (place / "config").exists(), "토큰 값이 없으면 /config 자리를 만들지도 않는다"
    [(file, args, env)] = fake_exec.calls
    assert (file, args) == ("streamlit", OLD_CMD)
    assert env == {"PATH": "/usr/bin"}
    assert Path.cwd() == container_start.PROJECT_ROOT, "app.py 를 저장소 뿌리에서 찾게 한다"
    printed = capsys.readouterr().out
    assert "bigdataquery 설치" in printed and "streamlit run app.py" in printed


IMAGE_PIP_ENVIRONMENT = {
    "PIP_INDEX_URL": "https://mirror.example.invalid/simple",
    "PIP_EXTRA_INDEX_URL": "https://other.example.invalid/simple",
    "PIP_FIND_LINKS": "https://links.example.invalid/",
}


def test_a_missing_package_is_installed_from_the_company_index_with_os_certificates(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """사내 패키지 자신은 사내 인덱스 **하나만** 보는 pip 로 의존성 없이 깔고, 의존성은 이미지 기본
    인덱스로 앱 판 고정(`requirements.txt`)을 제약 삼아 채운다. 판·인덱스는
    `requirements-company.txt` 에서 읽는다."""
    pip_output = (
        f"Looking in indexes: "
        f"https://{urllib.parse.quote(FAKE_ART_USER, safe='')}:****@index.example.invalid/simple\n"
        "Successfully installed bigdataquery-9.9.9\n"
    )
    runner = FakeRunner(
        [_probe("missing"), _probe("ok", "9.9.9")],
        [_ok(pip_output), _ok("Requirement already satisfied: bigdataquery==9.9.9\n")],
    )

    report, fake_exec = _main(place, {**IMAGE_PIP_ENVIRONMENT, **ALL_ENVIRONMENT}, runner)

    company, dependencies = runner.pip_calls
    company_env, dependency_env = runner.pip_envs
    assert company[:4] == [sys.executable, "-m", "pip", "install"]
    assert "--user" in company and "--user" in dependencies
    assert company[-1] == FAKE_PIN and dependencies[-1] == FAKE_PIN
    # 1) 사내 패키지 — 사내 인덱스 하나, 의존성 없이, 하위 pip 를 띄우는 빌드 격리 없이.
    assert "--no-deps" in company and "--no-build-isolation" in company
    assert company[company.index("--cert") + 1] == str(place / "ca-certificates.crt")
    expected_user = urllib.parse.quote(FAKE_ART_USER, safe="")
    expected_token = urllib.parse.quote(FAKE_ART_TOKEN, safe="")
    assert company_env["PIP_INDEX_URL"] == (
        f"https://{expected_user}:{expected_token}@index.example.invalid"
        "/repository/fake-pypi/simple"
    )
    assert company_env["PIP_CONFIG_FILE"] == os.devnull, "설정 파일의 추가 인덱스도 막는다"
    assert not set(container_start.PIP_OTHER_SOURCES_ENV) & set(company_env)
    # 2) 의존성 — 이미지 기본 인덱스 그대로, 자격증명 없이, 앱 판 고정을 제약으로.
    assert dependencies[dependencies.index("-c") + 1] == str(place / "requirements.txt")
    assert "--no-deps" not in dependencies and "--cert" not in dependencies
    for name, value in IMAGE_PIP_ENVIRONMENT.items():
        assert dependency_env[name] == value
    assert "PIP_CONFIG_FILE" not in dependency_env
    # 두 pip 모두 연결마다 짧게 포기하고, 합쳐서 설치 제한시간 안에 든다.
    for command in (company, dependencies):
        options = command[command.index("--timeout") : command.index("--timeout") + 4]
        assert options == list(container_start.PIP_NETWORK_OPTIONS)
    pip_timeouts = [
        timeout
        for call, timeout in zip(runner.calls, runner.timeouts, strict=True)
        if not _is_probe(call)
    ]
    assert all(0 < timeout <= container_start.INSTALL_TIMEOUT_SECONDS for timeout in pip_timeouts)
    steps = _steps(report)
    assert steps[report_contract.STEP_INSTALL]["status"] == report_contract.STATUS_OK
    assert report["bigdataquery_version"] == "9.9.9"
    assert report["missing_environment"] == []
    text = json.dumps(report, ensure_ascii=False) + capsys.readouterr().out
    _assert_no_secret(text)
    # 실행 줄에 남은 두 비밀값은 앱에 넘기지 않는다 — 앱은 요청자 계정만 읽는다.
    [(_, args, env)] = fake_exec.calls
    assert args == OLD_CMD
    assert report_contract.ARTIFACTORY_TOKEN_ENV not in env
    assert report_contract.BDQ_TOKEN_ENV not in env
    assert env[report_contract.BDQ_USER_NAME_ENV] == FAKE_BDQ_USER


def test_no_credential_is_put_on_any_command_line(place: Path) -> None:
    """명령줄은 `ps`·`/proc/<pid>/cmdline`(누구나 읽음)·감사 로그로 보인다 — 계정·토큰은 어느 하위
    프로세스의 명령줄에도 싣지 않는다."""
    runner = FakeRunner([_probe("missing"), _probe("ok", "9.9.9")], [_ok(), _ok()])

    _main(place, ALL_ENVIRONMENT, runner)

    assert len(runner.pip_calls) == 2
    command_lines = "\n".join(" ".join(call) for call in runner.calls)
    _assert_no_secret(command_lines)
    for flag in ("--index-url", "--extra-index-url", "-i"):
        assert all(flag not in call for call in runner.pip_calls), flag


def test_no_child_process_gets_the_two_secrets(place: Path) -> None:
    """깔린 패키지의 import 코드는 import 확인 하위 프로세스에서 돈다 — 그 환경에도, 자격증명이
    필요 없는 의존성 pip 에도 두 비밀값을 넘기지 않는다. 사내 pip 는 인덱스 주소 안의 자격증명만
    받는다."""
    runner = FakeRunner([_probe("missing"), _probe("ok", "9.9.9")], [_ok(), _ok()])

    _main(place, ALL_ENVIRONMENT, runner)

    assert len(runner.envs) == 4, "확인 · 사내 pip · 의존성 pip · 다시 확인"
    for env in runner.envs:
        assert report_contract.ARTIFACTORY_TOKEN_ENV not in env
        assert report_contract.BDQ_TOKEN_ENV not in env
    company_env = runner.pip_envs[0]
    for env in runner.envs:
        if env is company_env:
            continue
        assert all(FAKE_ART_TOKEN not in value for value in env.values())
        assert all(
            urllib.parse.quote(FAKE_ART_TOKEN, safe="") not in value for value in env.values()
        )


def test_a_failed_dependency_install_is_failed_and_keeps_both_pip_tails(place: Path) -> None:
    runner = FakeRunner(
        [_probe("missing")],
        [
            _ok("Successfully installed bigdataquery-9.9.9\n"),
            subprocess.CompletedProcess(
                [], 1, stdout="", stderr="ERROR: No matching distribution found for fakedep\n"
            ),
        ],
    )

    report, fake_exec = _main(place, ALL_ENVIRONMENT, runner)

    install = _steps(report)[report_contract.STEP_INSTALL]
    assert install["status"] == report_contract.STATUS_FAILED
    assert "의존성" in install["reason"] and "1" in install["reason"]
    tail = report["pip_tail"]
    assert isinstance(tail, list)
    assert any("Successfully installed" in line for line in tail)
    assert any("fakedep" in line for line in tail)
    assert fake_exec.calls


def test_the_dependency_install_gets_only_the_time_left(place: Path) -> None:
    """두 pip 는 설치 제한시간 하나를 나눠 쓴다 — 앞 pip 가 다 쓰면 뒤 pip 는 부르지 않는다."""
    runner = FakeRunner([_probe("missing")], [_ok()])
    ticks = iter([0.0, 0.0, float(container_start.INSTALL_TIMEOUT_SECONDS) + 1])

    outcome = container_start.install_step(
        ALL_ENVIRONMENT,
        runner,
        container_start.Redactor.from_environ(ALL_ENVIRONMENT),
        clock=lambda: next(ticks),
    )

    assert len(runner.pip_calls) == 1
    assert outcome.result.status == report_contract.STATUS_FAILED
    assert "제한시간" in outcome.result.reason


def test_inside_a_virtualenv_the_install_does_not_ask_for_the_user_site() -> None:
    """가상환경에서 `--user` 는 pip 가 거절한다. 이미지에는 가상환경이 없지만 갈래를 고정한다."""
    requirement = container_start.CompanyRequirement(pins=(FAKE_PIN,), index_url=FAKE_INDEX)
    company = container_start.company_pip_command(requirement, user_site=False, cert=None)
    dependencies = container_start.dependency_pip_command(
        requirement, user_site=False, constraints=None
    )
    for command in (company, dependencies):
        assert "--user" not in command and "--cert" not in command and "-c" not in command
        assert command[-1] == FAKE_PIN


def test_a_failed_install_keeps_the_pip_tail_without_credentials(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """pip 가 자격증명이 든 URL·토큰을 그대로 찍어도 결과 파일·표준 출력에는 가린 꼴만 남는다."""
    leaked = (
        f"ERROR: Could not find a version that satisfies the requirement {FAKE_PIN}\n"
        f"WARNING: Retrying https://{FAKE_ART_USER}:{FAKE_ART_TOKEN}@index.example.invalid/x\n"
        f"WARNING: token={urllib.parse.quote(FAKE_ART_TOKEN, safe='')}\n"
    )
    runner = FakeRunner(
        [_probe("missing")], subprocess.CompletedProcess([], 1, stdout="", stderr=leaked)
    )

    report, fake_exec = _main(place, ALL_ENVIRONMENT, runner)

    install = _steps(report)[report_contract.STEP_INSTALL]
    assert install["status"] == report_contract.STATUS_FAILED
    assert "1" in install["reason"]
    tail = report["pip_tail"]
    # 끝 몇 줄과 어느 pip 인지 알리는 머리 한 줄.
    assert isinstance(tail, list) and tail and len(tail) <= container_start.PIP_TAIL_LINES + 1
    assert any("***" in line for line in tail)
    _assert_no_secret(json.dumps(report, ensure_ascii=False) + capsys.readouterr().out)
    assert fake_exec.calls and fake_exec.calls[0][1] == OLD_CMD, "실패해도 앱은 띄운다"


def test_an_install_past_the_time_limit_is_failed_and_the_app_still_starts(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    timeout = subprocess.TimeoutExpired(
        ["pip"],
        container_start.INSTALL_TIMEOUT_SECONDS,
        output=f"Looking in https://{FAKE_ART_USER}:{FAKE_ART_TOKEN}@index.example.invalid\n",
    )
    runner = FakeRunner([_probe("missing")], timeout)

    report, fake_exec = _main(place, ALL_ENVIRONMENT, runner)

    install = _steps(report)[report_contract.STEP_INSTALL]
    assert install["status"] == report_contract.STATUS_FAILED
    assert str(container_start.INSTALL_TIMEOUT_SECONDS) in install["reason"]
    _assert_no_secret(json.dumps(report, ensure_ascii=False) + capsys.readouterr().out)
    assert fake_exec.calls[0][1] == OLD_CMD


def test_an_exception_text_with_credentials_is_masked(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """pip 를 부르다 난 예외 문구도 같은 가림을 지난다."""
    runner = FakeRunner(
        [_probe("missing")],
        OSError(f"cannot reach https://{FAKE_ART_USER}:{FAKE_ART_TOKEN}@index.example.invalid"),
    )

    report, _ = _main(place, ALL_ENVIRONMENT, runner)

    assert _steps(report)[report_contract.STEP_INSTALL]["status"] == report_contract.STATUS_FAILED
    _assert_no_secret(json.dumps(report, ensure_ascii=False) + capsys.readouterr().out)


def test_an_installed_package_is_not_installed_again(place: Path) -> None:
    runner = FakeRunner([_probe("ok", "9.9.9")])

    report, _ = _main(place, ALL_ENVIRONMENT, runner)

    assert runner.pip_calls == []
    install = _steps(report)[report_contract.STEP_INSTALL]
    assert install["status"] == report_contract.STATUS_OK
    assert report["bigdataquery_version"] == "9.9.9"


def test_a_package_that_is_there_but_breaks_on_import_is_not_reinstalled(place: Path) -> None:
    """깔렸는데 불러오다 깨지면 다시 깔아도 같다 — 실패로 적고 종류 이름을 남긴다."""
    runner = FakeRunner([_probe("broken", "ImportError")])

    report, _ = _main(place, ALL_ENVIRONMENT, runner)

    assert runner.pip_calls == []
    install = _steps(report)[report_contract.STEP_INSTALL]
    assert install["status"] == report_contract.STATUS_FAILED
    assert "ImportError" in install["reason"]


def test_an_import_probe_past_its_time_limit_is_failed_without_installing(place: Path) -> None:
    class SlowProbe(FakeRunner):
        def __call__(
            self, args: Sequence[str], *, timeout: float, env: Mapping[str, str]
        ) -> subprocess.CompletedProcess[str]:
            self.calls.append(list(args))
            raise subprocess.TimeoutExpired(list(args), timeout)

    runner = SlowProbe([])
    report, fake_exec = _main(place, ALL_ENVIRONMENT, runner)

    assert runner.pip_calls == []
    install = _steps(report)[report_contract.STEP_INSTALL]
    assert install["status"] == report_contract.STATUS_FAILED
    assert str(container_start.PROBE_TIMEOUT_SECONDS) in install["reason"]
    assert "import" not in install["reason"], "확인 코드 원문을 까닭에 싣지 않는다"
    assert fake_exec.calls


def test_only_one_artifactory_variable_names_the_missing_one(place: Path) -> None:
    environ = {report_contract.ARTIFACTORY_USER_ENV: FAKE_ART_USER}
    runner = FakeRunner([_probe("missing")])

    report, _ = _main(place, environ, runner)

    install = _steps(report)[report_contract.STEP_INSTALL]
    assert install["status"] == report_contract.STATUS_SKIPPED
    assert report_contract.ARTIFACTORY_TOKEN_ENV in install["reason"]
    assert report_contract.ARTIFACTORY_USER_ENV not in install["reason"]


def test_the_login_token_is_written_where_the_package_reads_it(place: Path) -> None:
    runner = FakeRunner([_probe("ok", "9.9.9")])

    report, _ = _main(place, ALL_ENVIRONMENT, runner)

    target = place / "config" / ".credential" / f"bigdataquery.token.{FAKE_BDQ_USER}"
    assert target.read_bytes() == FAKE_BDQ_TOKEN.encode("utf-8")
    assert target.stat().st_mode & 0o777 == 0o600
    token = _steps(report)[report_contract.STEP_TOKEN]
    assert token["status"] == report_contract.STATUS_OK
    token_file = report["token_file"]
    assert isinstance(token_file, dict) and token_file["exists"] is True
    assert token_file["modified_at"]
    assert report["user_name"] == {"present": True, "masked": "fa***"}
    _assert_no_secret(json.dumps(report, ensure_ascii=False))


def test_a_base64_token_is_decoded_so_line_breaks_survive_the_value_column(place: Path) -> None:
    """key·value 칸에 줄바꿈을 못 넣을 때 `base64:` + `base64 -w0` 값을 준다."""
    content = b'{"token": "FAKE"}\nFAKE-second-line\n'
    environ = {
        **ALL_ENVIRONMENT,
        report_contract.BDQ_TOKEN_ENV: "base64:" + base64.b64encode(content).decode("ascii"),
    }

    report, _ = _main(place, environ, FakeRunner([_probe("ok", "9.9.9")]))

    target = place / "config" / ".credential" / f"bigdataquery.token.{FAKE_BDQ_USER}"
    assert target.read_bytes() == content
    assert _steps(report)[report_contract.STEP_TOKEN]["status"] == report_contract.STATUS_OK


def test_a_broken_base64_token_is_failed_without_writing(place: Path) -> None:
    environ = {**ALL_ENVIRONMENT, report_contract.BDQ_TOKEN_ENV: "base64:@@@ 풀 수 없는 값"}

    report, fake_exec = _main(place, environ, FakeRunner([_probe("ok", "9.9.9")]))

    assert _steps(report)[report_contract.STEP_TOKEN]["status"] == report_contract.STATUS_FAILED
    assert not (place / "config" / ".credential" / f"bigdataquery.token.{FAKE_BDQ_USER}").exists()
    assert fake_exec.calls


def test_the_same_token_is_not_written_again(place: Path) -> None:
    credentials = place / "config" / ".credential"
    credentials.mkdir(parents=True)
    target = credentials / f"bigdataquery.token.{FAKE_BDQ_USER}"
    target.write_bytes(FAKE_BDQ_TOKEN.encode("utf-8"))
    os.utime(target, (1_000_000_000, 1_000_000_000))

    report, _ = _main(place, ALL_ENVIRONMENT, FakeRunner([_probe("ok", "9.9.9")]))

    assert target.stat().st_mtime == 1_000_000_000
    token = _steps(report)[report_contract.STEP_TOKEN]
    assert token["status"] == report_contract.STATUS_OK
    assert "같은 내용" in token["reason"]


def test_an_unwritable_config_is_failed_and_no_other_place_is_used(place: Path) -> None:
    """패키지가 그 자리만 보므로 다른 곳에 쓰지 않는다. 부모가 파일이면 누가 돌려도 못 쓴다."""
    blocker = place / "config"
    blocker.write_text("폴더가 아니라 파일", encoding="utf-8")

    report, fake_exec = _main(
        place, ALL_ENVIRONMENT, FakeRunner([_probe("ok", "9.9.9")]), credential_dir=blocker / "x"
    )

    token = _steps(report)[report_contract.STEP_TOKEN]
    assert token["status"] == report_contract.STATUS_FAILED
    assert "쓰지 못함" in token["reason"]
    assert not any("bigdataquery.token" in path.name for path in place.rglob("*"))
    assert fake_exec.calls
    _assert_no_secret(json.dumps(report, ensure_ascii=False))


def test_a_token_without_an_account_cannot_be_named(place: Path) -> None:
    environ = {report_contract.BDQ_TOKEN_ENV: FAKE_BDQ_TOKEN}

    report, _ = _main(place, environ, FakeRunner([_probe("ok", "9.9.9")]))

    steps = _steps(report)
    assert steps[report_contract.STEP_TOKEN]["status"] == report_contract.STATUS_FAILED
    assert report_contract.BDQ_USER_NAME_ENV in steps[report_contract.STEP_TOKEN]["reason"]
    assert steps[report_contract.STEP_USER_NAME]["status"] == report_contract.STATUS_SKIPPED
    assert report["user_name"] == {"present": False, "masked": None}


@pytest.mark.parametrize("account", ["../escape", "a/b", ".", ".."])
def test_an_account_that_would_leave_the_folder_is_refused(place: Path, account: str) -> None:
    environ = {**ALL_ENVIRONMENT, report_contract.BDQ_USER_NAME_ENV: account}

    report, _ = _main(place, environ, FakeRunner([_probe("ok", "9.9.9")]))

    assert _steps(report)[report_contract.STEP_TOKEN]["status"] == report_contract.STATUS_FAILED
    assert not any("bigdataquery.token" in path.name for path in place.rglob("*"))


def test_an_unexpected_failure_in_a_step_still_writes_the_report_and_starts_the_app(
    place: Path,
) -> None:
    class Broken(FakeRunner):
        def __call__(
            self, args: Sequence[str], *, timeout: float, env: Mapping[str, str]
        ) -> subprocess.CompletedProcess[str]:
            raise RuntimeError("예상하지 못한 실패")

    report, fake_exec = _main(place, ALL_ENVIRONMENT, Broken([]))

    install = _steps(report)[report_contract.STEP_INSTALL]
    assert install["status"] == report_contract.STATUS_FAILED
    assert "RuntimeError" in install["reason"]
    assert _steps(report)[report_contract.STEP_TOKEN]["status"] == report_contract.STATUS_OK
    assert fake_exec.calls[0][1] == OLD_CMD


def test_the_report_written_by_the_script_is_read_back_by_the_app(place: Path) -> None:
    """쓰는 쪽(스크립트)과 읽는 쪽(앱)이 같은 꼴을 본다 — 화면 안내가 단계 결과를 옮긴다."""
    runner = FakeRunner(
        [_probe("missing")], subprocess.CompletedProcess([], 1, stdout="", stderr="ERROR: x\n")
    )
    _main(place, {report_contract.ARTIFACTORY_USER_ENV: FAKE_ART_USER}, runner)

    read = report_contract.read_container_start_report()
    assert read is not None
    assert read.steps[report_contract.STEP_INSTALL].status == report_contract.STATUS_SKIPPED
    assert read.missing_environment == (
        report_contract.ARTIFACTORY_TOKEN_ENV,
        report_contract.BDQ_TOKEN_ENV,
        report_contract.BDQ_USER_NAME_ENV,
    )
    hint = report_contract.start_check_hint(report_contract.STEP_INSTALL)
    assert hint is not None
    assert "서버 시작 점검" in hint and report_contract.ARTIFACTORY_TOKEN_ENV in hint
    assert report_contract.BDQ_USER_NAME_ENV not in hint, (
        "점검 스크립트가 이 이름으로 「요청자 계정 필요」 를 가른다 — 설치 안내에 섞지 않는다"
    )


def test_no_report_means_no_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "없음.json")
    assert report_contract.read_container_start_report() is None
    assert report_contract.start_check_hint(report_contract.STEP_INSTALL) is None


def test_a_broken_report_file_is_treated_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "container_start.json"
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", path)
    for body in ("{깨진 JSON", "[]", json.dumps({"version": 1, "steps": "x"})):
        path.write_text(body, encoding="utf-8")
        assert report_contract.read_container_start_report() is None


@pytest.mark.parametrize(
    ("account", "masked"), [("fakeaccount", "fa***"), ("a", "a***"), ("", "***")]
)
def test_an_account_is_kept_only_as_its_first_two_letters(account: str, masked: str) -> None:
    assert report_contract.mask_account(account) == masked


def test_the_version_and_index_are_read_from_the_company_requirements_file() -> None:
    """판·인덱스는 스크립트에 따로 적지 않는다 — 정본 `requirements-company.txt` 하나를 읽는다."""
    requirement = container_start.read_company_requirement(
        PROJECT_ROOT / "requirements-company.txt"
    )
    assert requirement.pins and all(pin.startswith("bigdataquery==") for pin in requirement.pins)
    company = (PROJECT_ROOT / "requirements-company.txt").read_text(encoding="utf-8")
    assert f"--index-url {requirement.index_url}" in company
    assert urllib.parse.urlsplit(requirement.index_url).scheme == "https"


def test_comment_lines_do_not_count_as_options(place: Path) -> None:
    requirement = container_start.read_company_requirement(container_start.COMPANY_REQUIREMENTS)
    assert requirement == container_start.CompanyRequirement(pins=(FAKE_PIN,), index_url=FAKE_INDEX)


def test_an_unreadable_requirements_file_fails_the_install_step(
    place: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (place / "requirements-company.txt").write_text("# 판도 인덱스도 없다\n", encoding="utf-8")

    report, fake_exec = _main(place, ALL_ENVIRONMENT, FakeRunner([_probe("missing")]))

    install = _steps(report)[report_contract.STEP_INSTALL]
    assert install["status"] == report_contract.STATUS_FAILED
    assert "requirements-company.txt" in install["reason"]
    assert fake_exec.calls


def test_the_import_probe_runs_in_a_child_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """확인은 하위 프로세스에서 한다 — 이 프로세스에 반쯤 불러온 패키지를 남기지 않는다."""
    if importlib.util.find_spec("bigdataquery") is not None:
        pytest.skip("이 환경에는 진짜 bigdataquery 가 있다")
    missing = container_start.probe_bigdataquery(container_start.run_command, dict(os.environ))
    assert (missing.state, missing.version) == ("missing", None)

    package = tmp_path / "bigdataquery"
    package.mkdir()
    (package / "__init__.py").write_text("print('import 잡음')\n", encoding="utf-8")
    metadata = tmp_path / "bigdataquery-9.9.9.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: bigdataquery\nVersion: 9.9.9\n", encoding="utf-8"
    )
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join([str(tmp_path), os.environ.get("PYTHONPATH", "")])
    )
    found = container_start.probe_bigdataquery(container_start.run_command, dict(os.environ))

    assert (found.state, found.version) == ("ok", "9.9.9")
    assert "bigdataquery" not in sys.modules


def test_the_script_does_not_load_the_app_stack_before_it_hands_over() -> None:
    """시작 스크립트는 표준 라이브러리와 결과 꼴 모듈만 읽는다 — 무거운 import 가 앱 시작을 늦추거나
    깨진 의존성이 앱 띄우기 전에 스크립트를 죽이지 않게 한다."""
    code = (
        "import sys; sys.path.insert(0, 'scripts'); import container_start; "
        "print(sorted(name for name in ('streamlit', 'pandas', 'duckdb', 'bigdataquery') "
        "if name in sys.modules))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
    )
    assert completed.stdout.strip() == "[]"


def test_the_image_starts_through_the_script_with_the_same_app_command() -> None:
    """CD 는 시작 명령을 못 바꾼다 — 이미지의 CMD 가 스크립트를 부르고, 스크립트가 옛 CMD 와 같은
    줄로 바뀐다. 스크립트와 `requirements-company.txt` 는 이미지에 실려야 한다."""
    dockerfile = (PROJECT_ROOT / "docker" / "Dockerfile-prod").read_text(encoding="utf-8")
    assert 'CMD ["python", "scripts/container_start.py"]' in dockerfile
    assert 'CMD ["streamlit"' not in dockerfile
    assert "WORKDIR /project" in dockerfile
    assert container_start.app_command(container_start.APP_PORT) == OLD_CMD

    patterns = _dockerignore_patterns()
    for path in IMAGE_NEEDS:
        assert (PROJECT_ROOT / path).is_file(), path
        assert not _dockerignore_excludes(path, patterns), f".dockerignore 가 {path} 를 뺀다"


# 시작 스크립트가 이미지 안에서 읽는 파일 — 하나라도 빠지면 설치 단계가 늘 실패하거나 앱이 못 뜬다.
IMAGE_NEEDS = (
    "scripts/container_start.py",
    "requirements-company.txt",
    "requirements.txt",
    "src/capa_simulation/settings.py",
    "src/capa_simulation/io/container_start_report.py",
    "app.py",
)


def _dockerignore_patterns() -> list[str]:
    text = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


def _dockerignore_excludes(path: str, patterns: Sequence[str]) -> bool:
    """Docker 의 `.dockerignore` 판정을 넉넉히 흉내 낸다 — 경로나 그 위 폴더가 패턴에 맞으면 빠지고,
    뒤의 `!` 패턴이 되살린다. `fnmatch` 의 `*` 는 `/` 도 넘으므로 Docker 보다 더 많이 빠진다고 본다
    (시험이 놓치는 쪽으로 틀리지 않는다)."""
    parts = path.split("/")
    candidates = ["/".join(parts[: index + 1]) for index in range(len(parts))]
    excluded = False
    for raw in patterns:
        negate = raw.startswith("!")
        pattern = (raw[1:] if negate else raw).strip().removeprefix("./").strip("/")
        forms = {pattern, pattern.replace("**/", "")}
        if any(fnmatch.fnmatchcase(each, form) for each in candidates for form in forms):
            excluded = not negate
    return excluded


@pytest.mark.parametrize(
    ("path", "patterns", "excluded"),
    [
        ("requirements-company.txt", ["requirements-*.txt"], True),
        ("requirements.txt", ["*.txt"], True),
        ("scripts/container_start.py", ["scripts/"], True),
        ("src/capa_simulation/settings.py", ["src"], True),
        ("src/capa_simulation/settings.py", ["**/settings.py"], True),
        ("requirements.txt", ["*.txt", "!requirements.txt"], False),
        ("scripts/container_start.py", ["**/__pycache__/", "*.pyc", "data/temp/"], False),
    ],
)
def test_the_dockerignore_check_catches_globs(
    path: str, patterns: list[str], excluded: bool
) -> None:
    """위 판정이 부분 문자열이 아니라 glob 으로 본다 — `requirements-*.txt` 한 줄도 잡는다."""
    assert _dockerignore_excludes(path, patterns) is excluded


def test_the_operational_credential_place_is_fixed() -> None:
    """패키지가 그 자리만 본다. 시험만 바꾸는 내부 인자 말고는 환경변수로도 옮기지 않는다."""
    assert Path("/config/.credential") == container_start.CREDENTIAL_DIR
    assert container_start.TOKEN_FILE_PREFIX == "bigdataquery.token."
    source = (PROJECT_ROOT / "scripts" / "container_start.py").read_text(encoding="utf-8")
    assert "CAPA_CREDENTIAL" not in source


def test_the_report_lives_in_the_ignored_temp_folder() -> None:
    """결과 파일은 git·이미지 어디에도 실리지 않는 `data/temp/` 아래다. 시험들은 이 자리를 tmp 로
    옮겨 두므로(`conftest.py`) 옮기기 전 값을 하위 프로세스에서 읽는다."""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from capa_simulation import settings; "
            "print(settings.CONTAINER_START_REPORT_PATH.relative_to(settings.PROJECT_ROOT))",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
    )
    assert Path(completed.stdout.strip()).as_posix() == "data/temp/container_start.json"
    assert "data/temp/" in (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "data/temp/container_start.json"],
        cwd=PROJECT_ROOT,
        check=False,
    )
    assert ignored.returncode == 0


def _can_be_locked_out() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() != 0


@pytest.mark.skipif(not _can_be_locked_out(), reason="root 는 권한 000 폴더에도 들어간다")
def test_a_credential_folder_that_cannot_be_entered_still_leaves_the_report(place: Path) -> None:
    """3.10 의 `Path.is_file()` 은 권한 오류(EACCES)를 올린다. 셸·로그가 없는 CD 에서 `/config`
    권한 문제를 알릴 창구는 결과 파일뿐이라, 그 경우에도 결과 파일이 남아야 한다."""
    locked = place / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        report, fake_exec = _main(
            place,
            ALL_ENVIRONMENT,
            FakeRunner([_probe("ok", "9.9.9")]),
            credential_dir=locked / ".credential",
        )
    finally:
        locked.chmod(0o700)

    token = _steps(report)[report_contract.STEP_TOKEN]
    assert token["status"] == report_contract.STATUS_FAILED
    assert "PermissionError" in token["reason"]
    token_file = report["token_file"]
    assert isinstance(token_file, dict) and token_file["exists"] is None, "들어갈 수 없으면 모름"
    assert fake_exec.calls


def test_the_same_token_with_loose_permissions_is_tightened(place: Path) -> None:
    """이미 있던 같은 내용의 토큰 파일이 0644·폴더가 0755 면 다시 쓰지는 않되 0600·0700 으로
    좁힌다."""
    credentials = place / "config" / ".credential"
    credentials.mkdir(parents=True)
    credentials.chmod(0o755)
    target = credentials / f"bigdataquery.token.{FAKE_BDQ_USER}"
    target.write_bytes(FAKE_BDQ_TOKEN.encode("utf-8"))
    target.chmod(0o644)
    os.utime(target, (1_000_000_000, 1_000_000_000))

    report, _ = _main(place, ALL_ENVIRONMENT, FakeRunner([_probe("ok", "9.9.9")]))

    token = _steps(report)[report_contract.STEP_TOKEN]
    assert token["status"] == report_contract.STATUS_OK and "같은 내용" in token["reason"]
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(credentials.stat().st_mode) == 0o700
    assert target.stat().st_mtime == 1_000_000_000, "내용은 다시 쓰지 않는다"


def test_a_newly_written_token_tightens_an_existing_open_folder(place: Path) -> None:
    credentials = place / "config" / ".credential"
    credentials.mkdir(parents=True)
    credentials.chmod(0o755)

    _main(place, ALL_ENVIRONMENT, FakeRunner([_probe("ok", "9.9.9")]))

    assert stat.S_IMODE(credentials.stat().st_mode) == 0o700


@pytest.mark.parametrize(
    "value", ["base64:", "base64:   ", "base64:" + base64.b64encode(b"\n \n").decode("ascii")]
)
def test_an_empty_base64_token_is_failed_without_writing(place: Path, value: str) -> None:
    """접두만 넣었거나 빈 출력을 붙여 넣은 값으로 빈 토큰 파일을 쓰고 「정상」 이라 하지 않는다 —
    그러면 화면이 「모두 정상」 · 만료 안내로 엉뚱한 길을 가리킨다."""
    environ = {**ALL_ENVIRONMENT, report_contract.BDQ_TOKEN_ENV: value}

    report, _ = _main(place, environ, FakeRunner([_probe("ok", "9.9.9")]))

    token = _steps(report)[report_contract.STEP_TOKEN]
    assert token["status"] == report_contract.STATUS_FAILED
    assert "비었음" in token["reason"]
    assert not (place / "config" / ".credential" / f"bigdataquery.token.{FAKE_BDQ_USER}").exists()


def test_the_report_carries_the_token_place_and_who_runs_the_container(
    place: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """패키지가 토큰을 계정 값이 아니라 실행 사용자·HOME 으로 찾을 수 있다 — 화면에서 가를 수 있게
    토큰 파일 자리와 실행 사용자·HOME 을 가린 꼴로 싣는다."""
    monkeypatch.setattr(getpass, "getuser", lambda: "fakeosuser")
    environ = {**ALL_ENVIRONMENT, "HOME": "/home/fakeosuser"}

    report, _ = _main(place, environ, FakeRunner([_probe("ok", "9.9.9")]))

    token_file = report["token_file"]
    assert isinstance(token_file, dict)
    assert str(token_file["path"]).endswith("bigdataquery.token.fa***")
    assert report["runtime"] == {
        "os_user": "fa***",
        "os_user_is_bdq_user": False,
        "home": "/home/fa***",
    }
    text = json.dumps(report, ensure_ascii=False)
    _assert_no_secret(text)
    assert "fakeosuser" not in text

    read = report_contract.read_container_start_report()
    assert read is not None
    assert (read.os_user_masked, read.os_user_is_bdq_user, read.home_masked) == (
        "fa***",
        False,
        "/home/fa***",
    )
    hint = report_contract.step_hint(read, report_contract.STEP_TOKEN)
    assert str(token_file["path"]) in hint and "다르면" in hint and "만료" in hint
    assert report_contract.BDQ_USER_NAME_ENV not in hint


def test_the_image_prepares_the_token_folder_for_the_runtime_user() -> None:
    """앱은 `$DSUSER` 로 돈다(`sudo mkdir /project` 가 그 까닭) — `/` 에 폴더를 만들 수 없으니
    이미지가 토큰 폴더를 만들어 그 사용자에게 넘긴다."""
    dockerfile = (PROJECT_ROOT / "docker" / "Dockerfile-prod").read_text(encoding="utf-8")
    assert "sudo mkdir -p /config/.credential" in dockerfile
    assert "sudo chown $DSUSER:$DSUSER /config/.credential" in dockerfile
    assert dockerfile.index("/config/.credential") < dockerfile.index("CMD [")


def test_an_undecodable_environment_value_still_starts_the_app(place: Path) -> None:
    """리눅스 환경변수의 깨진 바이트는 surrogate 로 들어온다. 그것이 가리개나 주소 만들기를 깨도
    앱은 뜨고 결과 파일은 남는다."""
    environ = {**ALL_ENVIRONMENT, report_contract.ARTIFACTORY_TOKEN_ENV: "FAKE\udcffbroken"}
    runner = FakeRunner([_probe("missing"), _probe("ok", "9.9.9")], [_ok(), _ok()])

    report, fake_exec = _main(place, environ, runner)

    assert fake_exec.calls and fake_exec.calls[0][1] == OLD_CMD
    assert _steps(report)[report_contract.STEP_INSTALL]["status"] == report_contract.STATUS_OK
    assert "%FF" in runner.pip_envs[0]["PIP_INDEX_URL"], "깨진 바이트는 원래 바이트로 옮긴다"


def test_a_non_utf8_stdout_does_not_stop_the_app(
    place: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """표준 출력이 UTF-8 이 아니면 한글 진행 줄이 깨진다 — 그래도 예외 없이 앱으로 넘어간다."""
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="ascii"))

    report, fake_exec = _main(place, {"PATH": "/usr/bin"}, FakeRunner([_probe("missing")]))

    assert fake_exec.calls and fake_exec.calls[0][1] == OLD_CMD
    assert _steps(report)[report_contract.STEP_INSTALL]["status"] == report_contract.STATUS_SKIPPED
    sys.stdout.flush()
    assert b"[container_start]" in raw.getvalue()


def test_an_unexpected_failure_while_collecting_leaves_a_failed_report(
    place: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """단계 밖에서 예상하지 못한 예외가 나도 결과 파일은 「도중에 멈춤」 으로 남고 앱은 뜬다. 예외
    문구의 비밀값은 가린다."""

    def explode(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError(f"leaked {FAKE_ART_TOKEN}")

    monkeypatch.setattr(container_start, "collect_report", explode)

    report, fake_exec = _main(place, ALL_ENVIRONMENT, FakeRunner([]))

    assert {step["status"] for step in _steps(report).values()} == {report_contract.STATUS_FAILED}
    assert all("RuntimeError" in step["reason"] for step in _steps(report).values())
    assert fake_exec.calls
    _assert_no_secret(json.dumps(report, ensure_ascii=False) + capsys.readouterr().out)
    read = report_contract.read_container_start_report()
    assert read is not None and report_contract.report_verdict(read) == "실패 있음"


def test_a_redactor_that_cannot_be_built_prints_only_the_error_kind(
    place: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(_environ: Mapping[str, str]) -> container_start.Redactor:
        raise ValueError(f"cannot mask {FAKE_ART_TOKEN}")

    monkeypatch.setattr(container_start.Redactor, "from_environ", staticmethod(explode))

    report, fake_exec = _main(place, ALL_ENVIRONMENT, FakeRunner([]))

    printed = capsys.readouterr().out
    assert "ValueError" in printed
    _assert_no_secret(printed + json.dumps(report, ensure_ascii=False))
    assert fake_exec.calls


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({report_contract.BDQ_TOKEN_ENV: FAKE_BDQ_TOKEN}, "돌지 않은 것으로"),
        ({report_contract.ARTIFACTORY_TOKEN_ENV: FAKE_ART_TOKEN}, "돌지 않은 것으로"),
        ({report_contract.ARTIFACTORY_USER_ENV: FAKE_ART_USER}, "결과를 쓰지 못했습니다"),
        ({report_contract.BDQ_USER_NAME_ENV: FAKE_BDQ_USER}, None),
        ({}, None),
    ],
)
def test_a_cd_server_without_a_report_says_so(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environ: dict[str, str],
    expected: str | None,
) -> None:
    """결과 파일이 없으면 개발 PC 와 화면이 같아 「CD 가 CMD 를 덮어써 스크립트가 안 돌았다」 를
    가를 수 없다. 스크립트는 두 비밀값을 앱에 넘기지 않으므로 그 key 가 앱에 있으면 스크립트가
    돌지 않은 것이다. 계정 하나(`CAPA_BDQ_USER_NAME`)는 WebIDE 도 쓰므로 그것만으로는 알리지
    않는다."""
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "없음.json")

    notice = report_contract.missing_report_notice(environ)
    hint = report_contract.start_check_hint(report_contract.STEP_INSTALL, environ=environ)

    if expected is None:
        assert notice is None and hint is None
        return
    assert notice is not None and expected in notice and hint == notice
    assert report_contract.BDQ_USER_NAME_ENV not in notice, "점검 스크립트의 갈래를 바꾸지 않는다"
    assert "패키지가 없습니다" not in notice
    _assert_no_secret(notice)
