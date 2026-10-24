# Purpose: CD 컨테이너 시작 스크립트의 설치·토큰 파일·결과 기록·비밀값 가림·실행 인자를 고정한다.

"""컨테이너 시작 스크립트(`scripts/container_start.py`).

CD 서버에는 셸이 없고 시작 명령도 바꿀 수 없다 — 이 스크립트가 런타임 환경변수만으로 사내
`bigdataquery` 설치·로그인 토큰 파일·요청자 계정을 갖추고, 결과를 파일로 남긴 뒤 지금과 같은
`streamlit run` 줄로 바뀐다. pip·하위 프로세스·`exec` 는 모두 가짜로 바꿔 부른다.

여기 쓰는 계정·토큰은 **분명한 가짜 문자열**이다. 저장소가 공개라 실제 값을 넣지 않는다.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
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


class FakeRunner:
    """하위 프로세스 대역. `python -c` 는 import 확인, 그 밖은 pip 다(pip 의 `-c` 는 제약 파일)."""

    def __init__(
        self,
        probes: Sequence[str],
        pip: subprocess.CompletedProcess[str] | BaseException | None = None,
    ) -> None:
        self.probes = list(probes)
        self.pip = pip
        self.calls: list[list[str]] = []
        self.timeouts: list[float] = []

    def __call__(self, args: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        self.timeouts.append(timeout)
        if _is_probe(args):
            return subprocess.CompletedProcess(list(args), 0, stdout=self.probes.pop(0), stderr="")
        if isinstance(self.pip, BaseException):
            raise self.pip
        assert self.pip is not None, "pip 를 부르지 않아야 하는 시험에서 pip 를 불렀다"
        return self.pip

    @property
    def pip_calls(self) -> list[list[str]]:
        return [call for call in self.calls if not _is_probe(call)]


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


def test_a_missing_package_is_installed_from_the_company_index_with_os_certificates(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """판·인덱스는 `requirements-company.txt` 에서 읽고 추가 인덱스(자격증명은 URL 인코딩)로 넣는다.
    앱 판 고정(`requirements.txt`)을 제약으로 걸어 사내 패키지가 앱 의존성을 바꾸지 못하게 한다."""
    pip_output = (
        f"Looking in indexes: https://mirror.example.invalid/simple, "
        f"https://{urllib.parse.quote(FAKE_ART_USER, safe='')}:****@index.example.invalid/simple\n"
        "Successfully installed bigdataquery-9.9.9\n"
    )
    runner = FakeRunner(
        [_probe("missing"), _probe("ok", "9.9.9")],
        subprocess.CompletedProcess([], 0, stdout=pip_output, stderr=""),
    )

    report, fake_exec = _main(place, ALL_ENVIRONMENT, runner)

    [pip] = runner.pip_calls
    assert pip[:4] == [sys.executable, "-m", "pip", "install"]
    assert "--user" in pip
    assert pip[-1] == FAKE_PIN
    url = pip[pip.index("--extra-index-url") + 1]
    expected_user = urllib.parse.quote(FAKE_ART_USER, safe="")
    expected_token = urllib.parse.quote(FAKE_ART_TOKEN, safe="")
    assert url == (
        f"https://{expected_user}:{expected_token}@index.example.invalid"
        "/repository/fake-pypi/simple"
    )
    assert pip[pip.index("--cert") + 1] == str(place / "ca-certificates.crt")
    assert pip[pip.index("-c") + 1] == str(place / "requirements.txt")
    assert runner.timeouts[1] == container_start.INSTALL_TIMEOUT_SECONDS
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


def test_inside_a_virtualenv_the_install_does_not_ask_for_the_user_site() -> None:
    """가상환경에서 `--user` 는 pip 가 거절한다. 이미지에는 가상환경이 없지만 갈래를 고정한다."""
    requirement = container_start.CompanyRequirement(pins=(FAKE_PIN,), index_url=FAKE_INDEX)
    command = container_start.pip_install_command(
        requirement, "https://x", user_site=False, cert=None, constraints=None
    )
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
    assert isinstance(tail, list) and tail and len(tail) <= container_start.PIP_TAIL_LINES
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
            self, args: Sequence[str], *, timeout: float
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
            self, args: Sequence[str], *, timeout: float
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
    missing = container_start.probe_bigdataquery(container_start.run_command)
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
    found = container_start.probe_bigdataquery(container_start.run_command)

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

    ignored = [
        line.strip()
        for line in (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert not any(
        "scripts" in line or "requirements-company" in line or "src" in line for line in ignored
    )


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
