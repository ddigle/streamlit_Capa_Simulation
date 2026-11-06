# Purpose: 시작 스크립트의 임시 응답 · 프로필 · 점검 · 두 DB 받기 차례와 결과 칸을 고정한다.

"""시작 스크립트의 동기화 몫(`scripts/container_start.py`).

앱이 뜨는 길이 둘로 갈린다 — `managed` 는 「이번 실행의 `boot-pull` 이 종료 코드 0」 한 길뿐이고,
그 밖은 어떤 실패에도 뜬다. 하위 프로세스 · `exec` · 임시 응답은 가짜다. 임시 응답 자체는
`test_container_stage.py` 가, 실제 `aws` 왕복은 `test_object_storage_real_aws.py` 가 본다. 값은 모두
합성이다.
"""

from __future__ import annotations

import configparser
import json
import os
import signal
import socket
import stat
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from types import FrameType, SimpleNamespace

import pytest

import capa_simulation.settings as settings
from capa_simulation.auth import names as sso_names
from capa_simulation.components import container_start_check as start_check
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.io import object_storage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import container_stage  # noqa: E402
import container_start  # noqa: E402
from s3_mock_store import MockStore, start_mock  # noqa: E402

FAKE_ACCESS_KEY = "FAKE-s3-access-key-0001"
FAKE_SECRET_KEY = "FAKE-s3-secret-key-0123456789-abcdefghij"
FAKE_BUCKET = "Demo_ops_bucket"
FAKE_ARTIFACTORY_TOKEN = "FAKE-artifactory-token-0000"
FAKE_BDQ_TOKEN = "FAKE-bdq-login-token-0000"
CLOSED_ENDPOINT = "http://127.0.0.1:9"
POINTER_KEY = "generations/heads/999999999999__s000000000001__e000000000001__0123abcd.json"
DOWNLOADED = {
    "kind": None,
    "action": "downloaded",
    "seq": 7,
    "previous_upload_utc": "2026-11-07T00:00:00Z",
    "total_bytes": 2048,
    "seconds": 2.5,
}

Answer = subprocess.CompletedProcess[str] | BaseException


def _line(stdout: str = "", code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr="")


def _boot(payload: Mapping[str, object], code: int = 0) -> subprocess.CompletedProcess[str]:
    noise = "import 잡음\n"
    return _line(noise + json.dumps(payload, ensure_ascii=False) + "\n", code)


def _failed(kind: str) -> subprocess.CompletedProcess[str]:
    return _boot({"kind": kind, "action": None, "seq": None}, code=1)


def _is_boot_pull(args: Sequence[str]) -> bool:
    return "boot-pull" in args


class Runner:
    """하위 프로세스 대역. 부른 차례를 `log` 에 남긴다."""

    def __init__(
        self,
        log: list[str],
        boot: Sequence[Answer] = (),
        *,
        aws: Callable[[Sequence[str]], Answer] | None = None,
    ) -> None:
        self.log = log
        self.boot = list(boot)
        self.aws = aws or (lambda args: _line(f"aws-cli/{report_contract.AWS_CLI_VERSION} Python"))
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str]] = []

    def __call__(
        self, args: Sequence[str], *, timeout: float, env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        self.envs.append(dict(env))
        if args[0] == "aws":
            self.log.append("aws")
            return _raise_or_give(self.aws(args))
        if _is_boot_pull(args):
            self.log.append("boot-pull")
            return _raise_or_give(self.boot.pop(0))
        code = args[2]
        if container_start.PROBE_MARKER in code:
            self.log.append("설치 확인")
            return _line(f"{container_start.PROBE_MARKER} ok 9.9.9\n")
        return _line(f"{container_start._DUCKDB_PROBE_MARKER} 800.0 MiB | 2\n")

    @property
    def boot_calls(self) -> int:
        return sum(1 for call in self.calls if _is_boot_pull(call))


def _raise_or_give(answer: Answer) -> subprocess.CompletedProcess[str]:
    if isinstance(answer, BaseException):
        raise answer
    return answer


class FakeStage(container_stage.Stage):
    def __init__(self, log: list[str]) -> None:
        super().__init__(None)
        self.log = log
        self.shown: list[tuple[bool, int, str | None]] = []
        self.log.append("임시 응답")

    def show(self, *, pulling: bool, attempts: int = 0, kind: str | None = None) -> None:
        self.shown.append((pulling, attempts, kind))

    def close(self) -> None:
        if "닫기" not in self.log:
            self.log.append("닫기")


class Stay(Exception):
    """물러나는 차례를 끊는 시험 표지 — 실제로는 영원히 되풀이한다."""


@pytest.fixture
def box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    monkeypatch.setattr(
        settings, "CONTAINER_START_REPORT_PATH", tmp_path / "temp" / "container_start.json"
    )
    monkeypatch.setattr(
        object_storage,
        "CAPABILITIES_PATH",
        PROJECT_ROOT / "config" / "object_storage_capabilities.json",
    )
    log: list[str] = []
    stages: list[FakeStage] = []

    def open_stage(port: int, *, base_path: str = "/") -> container_stage.Stage:
        stage = FakeStage(log)
        stages.append(stage)
        return stage

    monkeypatch.setattr(container_stage, "open_stage", open_stage)
    home = tmp_path / "home"
    home.mkdir()
    previous = Path.cwd()
    yield SimpleNamespace(folder=tmp_path, home=home, log=log, stages=stages, slept=[])
    os.chdir(previous)


def _environ(box: SimpleNamespace, **extra: str) -> dict[str, str]:
    return {
        "HOME": str(box.home),
        "PATH": "/usr/bin",
        "HOSTNAME": "demo-pod-0",
        sso_names.ENV_S3_ACCESS_KEY: FAKE_ACCESS_KEY,
        sso_names.ENV_S3_SECRET_KEY: FAKE_SECRET_KEY,
        sso_names.ENV_S3_BUCKET: FAKE_BUCKET,
        sso_names.ENV_S3_ENDPOINT: CLOSED_ENDPOINT,
        "CAPA_ARTIFACTORY_TOKEN": FAKE_ARTIFACTORY_TOKEN,
        "CAPA_BDQ_TOKEN": FAKE_BDQ_TOKEN,
        **extra,
    }


def _managed(box: SimpleNamespace, **extra: str) -> dict[str, str]:
    return _environ(box, CAPA_S3_SYNC_MODE="managed", **extra)


def _start(
    box: SimpleNamespace,
    environ: Mapping[str, str],
    runner: Runner,
    *,
    stay_after: int | None = None,
) -> list[tuple[str, list[str], dict[str, str]]]:
    """시작 스크립트를 돌린다. `stay_after` 번 물러나면 끊는다 — 앱이 뜨지 않았는지 보려고."""
    launched: list[tuple[str, list[str], dict[str, str]]] = []

    def exec_app(file: str, args: list[str], env: dict[str, str]) -> None:
        box.log.append("앱")
        launched.append((file, list(args), dict(env)))

    def sleep(seconds: float) -> None:
        box.slept.append(seconds)
        if stay_after is not None and len(box.slept) >= stay_after:
            raise Stay

    container_start.main(
        ["--credential-dir", str(box.folder / "credential")],
        environ=dict(environ),
        runner=runner,
        exec_app=exec_app,
        sleep=sleep,
    )
    return launched


def _report() -> dict[str, object]:
    written = json.loads(settings.CONTAINER_START_REPORT_PATH.read_text(encoding="utf-8"))
    assert isinstance(written, dict)
    return written


def _sync() -> dict[str, object]:
    sync = _report()["sync"]
    assert isinstance(sync, dict)
    return sync


def _step(name: str) -> dict[str, str]:
    steps = _sync()["steps"]
    assert isinstance(steps, dict)
    step = steps[name]
    assert isinstance(step, dict)
    return step


# --------------------------------------------------------------------------- 차례
def test_the_stage_comes_first_and_the_app_only_after_the_pull(box: SimpleNamespace) -> None:
    runner = Runner(box.log, [_boot(DOWNLOADED)])

    launched = _start(box, _managed(box), runner)

    assert len(launched) == 1
    assert box.log[0] == "임시 응답"
    assert box.log.index("aws") < box.log.index("설치 확인") < box.log.index("boot-pull")
    assert box.log[-3:] == ["boot-pull", "닫기", "앱"]


def test_the_stage_says_data_is_coming_from_the_start_when_managed(box: SimpleNamespace) -> None:
    _start(box, _managed(box), Runner(box.log, [_boot(DOWNLOADED)]))

    assert box.stages[0].shown[0] == (True, 0, None)


def test_a_local_server_does_as_before_apart_from_the_stage(box: SimpleNamespace) -> None:
    """키도 모드도 없으면 프로필 · 점검 · 받기를 건너뛴다. 설치 240초는 임시 응답이 덮는다."""
    environ = {"HOME": str(box.home), "PATH": "/usr/bin"}
    runner = Runner(box.log)

    launched = _start(box, environ, runner)

    assert len(launched) == 1
    assert box.log == ["임시 응답", "설치 확인", "닫기", "앱"]
    assert not (box.home / ".aws").exists()
    assert "sync" not in _report()
    assert box.stages[0].shown == [(False, 0, None)]


def test_keys_without_the_mode_check_the_way_but_do_not_pull(box: SimpleNamespace) -> None:
    """첫 CI/CD 로 aws 판 · 연결을 보는 판 — 앱은 빈 디스크로 뜬다."""
    runner = Runner(box.log)

    launched = _start(box, _environ(box), runner)

    assert len(launched) == 1
    assert runner.boot_calls == 0
    assert (box.home / ".aws" / "credentials").is_file()
    assert _step(report_contract.SYNC_STEP_PULL)["status"] == report_contract.STATUS_SKIPPED
    assert _step(report_contract.SYNC_STEP_CLI)["status"] == report_contract.STATUS_OK


def _bucket_with(*keys: str) -> Callable[[Sequence[str]], Answer]:
    """목록에 포인터가 있는 버킷을 답하는 aws 대역."""

    def answer(args: Sequence[str]) -> Answer:
        if "list-objects-v2" in args:
            return _line(json.dumps({"Contents": [{"Key": key} for key in keys]}))
        return _line(f"aws-cli/{report_contract.AWS_CLI_VERSION} Python")

    return answer


def _reachable_ecs(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = container_start.StepResult(report_contract.STATUS_OK, "닿음")
    monkeypatch.setattr(container_start, "ecs_step", lambda _url: ok)


def test_a_forgotten_mode_over_a_bucket_with_generations_leaves_a_mark(
    box: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """모드 칸을 빠뜨린 CI/CD — 알리지 않으면 빈 시드 앱에 저장한 것이 다음 CI/CD 에 사라진다."""
    _reachable_ecs(monkeypatch)
    runner = Runner(box.log, aws=_bucket_with(POINTER_KEY))

    launched = _start(box, _environ(box), runner)

    assert len(launched) == 1
    assert _sync()["head_ignored"] is True
    assert "버킷의 정본을 받지 않음" in _step(report_contract.SYNC_STEP_PULL)["reason"]


@pytest.mark.parametrize(
    ("keys", "extra"),
    [
        ((), {}),
        ((POINTER_KEY,), {"CAPA_S3_SYNC_MODE": "local"}),
    ],
    ids=["empty-bucket", "local-on-purpose"],
)
def test_no_mark_without_a_forgotten_mode(
    box: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    keys: tuple[str, ...],
    extra: dict[str, str],
) -> None:
    """이관 전의 첫 CI/CD · 일부러 `local` 을 넣은 서버는 알릴 것이 없다."""
    _reachable_ecs(monkeypatch)

    _start(box, _environ(box, **extra), Runner(box.log, aws=_bucket_with(*keys)))

    assert _step(report_contract.SYNC_STEP_BUCKET)["status"] == report_contract.STATUS_OK
    assert not _sync().get("head_ignored")


def test_a_mistyped_mode_does_not_pull_and_the_app_still_starts(box: SimpleNamespace) -> None:
    """2026-10-22 결정 (다) — 앱은 뜨고 `SY-01` 이 알린다. 올리지도 않으니 정본을 덮지 않는다."""
    runner = Runner(box.log)

    launched = _start(box, _environ(box, CAPA_S3_SYNC_MODE="Managed"), runner)

    assert len(launched) == 1
    assert runner.boot_calls == 0
    assert _step(report_contract.SYNC_STEP_PULL)["status"] == report_contract.STATUS_SKIPPED


def test_a_broken_config_with_the_mode_set_stays_rather_than_start_empty(
    box: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """모드는 환경변수에 있다 — 설정 파일이 깨졌다고 `local` 로 내려앉아 빈 DB 로 뜨면 안 된다."""
    broken = tmp_path / "object_storage.json"
    broken.write_text("{", encoding="utf-8")
    monkeypatch.setattr(object_storage, "CONFIG_PATH", broken)
    runner = Runner(box.log, [_failed("config")])

    with pytest.raises(Stay):
        _start(box, _managed(box), runner, stay_after=1)

    assert runner.boot_calls == 1
    assert "앱" not in box.log


def test_a_broken_config_without_the_mode_still_starts_the_app(
    box: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = tmp_path / "object_storage.json"
    broken.write_text("{", encoding="utf-8")
    monkeypatch.setattr(object_storage, "CONFIG_PATH", broken)

    launched = _start(box, {"HOME": str(box.home)}, Runner(box.log))

    assert len(launched) == 1


# --------------------------------------------------------------------------- 받기
def test_a_failed_pull_backs_off_and_only_success_starts_the_app(box: SimpleNamespace) -> None:
    runner = Runner(
        box.log, [_failed("unreachable"), _failed("timeout"), _failed("denied"), _boot(DOWNLOADED)]
    )

    launched = _start(box, _managed(box), runner)

    assert box.slept == [5, 10, 20]
    assert len(launched) == 1
    assert runner.boot_calls == 4
    assert box.stages[0].shown[1:] == [
        (True, 1, "unreachable"),
        (True, 2, "timeout"),
        (True, 3, "denied"),
    ]
    assert _sync()["pull_attempts"] == 4


def test_an_empty_remote_keeps_waiting_and_never_starts_the_app(box: SimpleNamespace) -> None:
    """이관 전이다. 빈 DB 로 떠서 정본을 덮는 길을 막는다."""
    runner = Runner(box.log, [_failed("remote_empty")] * 8)

    with pytest.raises(Stay):
        _start(box, _managed(box), runner, stay_after=8)

    assert runner.boot_calls == 8
    assert "앱" not in box.log
    assert box.slept == [5, 10, 20, 40, 60, 60, 60, 60]


@pytest.mark.parametrize("kind", ["forked", "diverged", "schema_newer"])
def test_what_only_a_person_can_fix_is_not_hurried(box: SimpleNamespace, kind: str) -> None:
    runner = Runner(box.log, [_failed(kind)])

    with pytest.raises(Stay):
        _start(box, _managed(box), runner, stay_after=1)

    assert box.slept == [300]


@pytest.mark.parametrize("name", list(container_start.SYNC_REQUIRED_ENVIRONMENT))
def test_a_missing_bucket_or_key_is_not_pulled_at_all(box: SimpleNamespace, name: str) -> None:
    """버킷이 없을 때 config 기본(개발 버킷)으로 가면 운영 저장이 개발 버킷에 간다."""
    environ = _managed(box)
    del environ[name]
    runner = Runner(box.log)

    with pytest.raises(Stay):
        _start(box, environ, runner, stay_after=2)

    assert runner.boot_calls == 0
    assert box.stages[0].shown[-1] == (True, 2, "config")
    assert "앱" not in box.log


@pytest.mark.parametrize(
    "answer",
    [
        _line("", 0),
        _line("끝줄이 JSON 아님\n", 0),
        _boot({**DOWNLOADED, "kind": "denied"}, code=0),
        _boot({**DOWNLOADED, "action": None}, code=0),
        _boot({**DOWNLOADED, "seq": None}, code=0),
        _boot(DOWNLOADED, code=1),
        _line("", -9),
        OSError("실행 실패"),
        subprocess.TimeoutExpired(["boot-pull"], 1),
    ],
    ids=[
        "빈 출력",
        "JSON 아님",
        "성공 코드에 실패 갈래",
        "동작 없음",
        "세대 없음",
        "실패 코드에 성공 글",
        "죽임",
        "실행 실패",
        "시간 초과",
    ],
)
def test_only_exit_zero_with_a_good_line_starts_the_app(
    box: SimpleNamespace, answer: Answer
) -> None:
    runner = Runner(box.log, [answer])

    with pytest.raises(Stay):
        _start(box, _managed(box), runner, stay_after=1)

    assert "앱" not in box.log


def test_an_unexpected_exception_in_the_pull_keeps_trying(
    box: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`check_and_record` 의 「예외에도 앱은 뜬다」 가 여기에는 없다 — 예외가 곧 빈 앱이 된다."""

    def explode(runner: object, env: object) -> container_start.BootPull:
        raise RuntimeError("예상 못 한 실패")

    monkeypatch.setattr(container_start, "boot_pull_once", explode)

    with pytest.raises(Stay):
        _start(box, _managed(box), Runner(box.log), stay_after=3)

    assert "앱" not in box.log
    assert box.stages[0].shown[-1] == (True, 3, "other")


def test_failed_checks_do_not_stand_in_for_the_pull(box: SimpleNamespace) -> None:
    """앞 점검이 다 실패해도 판정은 받기가 한다 — `HOME` 이 없어도 받으면 뜬다."""
    environ = _managed(box)
    del environ["HOME"]
    runner = Runner(box.log, [_boot(DOWNLOADED)], aws=lambda _a: FileNotFoundError("aws"))

    launched = _start(box, environ, runner)

    assert len(launched) == 1
    assert _step(report_contract.SYNC_STEP_PROFILE)["status"] == report_contract.STATUS_FAILED


def test_sigterm_is_handled_all_the_way_through_the_pull(box: SimpleNamespace) -> None:
    """처리기가 없는 PID 1 은 SIGTERM 을 흘린다 — 멈추지 못한 컨테이너가 된다."""
    outer = signal.getsignal(signal.SIGTERM)

    runner = Runner(box.log, [_failed("unreachable"), _boot(DOWNLOADED)])
    seen: list[object] = []

    def exec_app(file: str, args: list[str], env: dict[str, str]) -> None:
        seen.append(signal.getsignal(signal.SIGTERM))

    def sleep(_seconds: float) -> None:
        seen.append(signal.getsignal(signal.SIGTERM))

    container_start.main(
        ["--credential-dir", str(box.folder / "credential")],
        environ=_managed(box),
        runner=runner,
        exec_app=exec_app,
        sleep=sleep,
    )

    assert seen == [container_start._exit_on_sigterm, container_start._exit_on_sigterm]
    assert signal.getsignal(signal.SIGTERM) is outer


def test_a_sigterm_during_the_wait_ends_the_script_without_the_app(box: SimpleNamespace) -> None:
    def interrupted(_seconds: float) -> None:
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        frame: FrameType | None = None
        handler(signal.SIGTERM, frame)

    launched: list[str] = []

    with pytest.raises(SystemExit) as caught:
        container_start.main(
            ["--credential-dir", str(box.folder / "credential")],
            environ=_managed(box),
            runner=Runner(box.log, [_failed("unreachable")]),
            exec_app=lambda file, args, env: launched.append(file),
            sleep=interrupted,
        )

    assert caught.value.code == 128 + signal.SIGTERM
    assert launched == []
    assert box.log[-1] == "닫기", "소켓을 닫고 끝난다"


# --------------------------------------------------------------------------- 프로필
def test_the_profile_is_private_and_says_what_the_profile_command_prints(
    box: SimpleNamespace,
) -> None:
    _start(box, _environ(box), Runner(box.log))

    folder = box.home / ".aws"
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    for name in ("credentials", "config"):
        assert stat.S_IMODE((folder / name).stat().st_mode) == 0o600
    storage = object_storage.load_settings(
        environ={sso_names.ENV_S3_ENDPOINT: CLOSED_ENDPOINT, sso_names.ENV_S3_BUCKET: FAKE_BUCKET}
    )
    keys = configparser.ConfigParser()
    keys.read(folder / "credentials", encoding="utf-8")
    assert keys[storage.profile]["aws_access_key_id"] == FAKE_ACCESS_KEY
    assert keys[storage.profile]["aws_secret_access_key"] == FAKE_SECRET_KEY
    config = configparser.ConfigParser()
    config.read(folder / "config", encoding="utf-8")
    section = config[f"profile {storage.profile}"]
    for name, value in object_storage.profile_settings(storage):
        parent, dot, leaf = name.partition(".")
        if dot:
            assert f"{leaf} = {value}" in section[parent]
        else:
            assert section[name] == value


def test_no_key_is_left_in_the_report_the_log_or_a_child(
    box: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """키는 `~/.aws` 에만 있다. aws 실패 글에 키가 들어 있어도 갈래 낱말만 남는다."""

    def aws(args: Sequence[str]) -> Answer:
        if "--version" in args:
            return _line(f"aws-cli/{report_contract.AWS_CLI_VERSION}")
        leaked = f"An error occurred (403) {FAKE_ACCESS_KEY} {FAKE_SECRET_KEY} {FAKE_BUCKET}"
        return subprocess.CompletedProcess([], 254, stdout="", stderr=leaked)

    runner = Runner(box.log, [_boot(DOWNLOADED)], aws=aws)
    environ = _managed(box)

    launched = _start(box, environ, runner)

    written = capsys.readouterr().out + json.dumps(_report(), ensure_ascii=False)
    for secret in (FAKE_ACCESS_KEY, FAKE_SECRET_KEY, FAKE_ARTIFACTORY_TOKEN, FAKE_BDQ_TOKEN):
        assert secret not in written
    assert FAKE_BUCKET not in written
    assert CLOSED_ENDPOINT not in written
    for env in runner.envs:
        for name in container_start.CHILD_WITHHELD_ENVIRONMENT:
            assert name not in env
    [(_file, _args, app_env)] = launched
    assert "CAPA_ARTIFACTORY_TOKEN" not in app_env and "CAPA_BDQ_TOKEN" not in app_env
    assert app_env[sso_names.ENV_S3_SECRET_KEY] == FAKE_SECRET_KEY, "앱이 읽고 지운다"


def test_a_key_with_a_line_break_cannot_add_lines_to_the_file(box: SimpleNamespace) -> None:
    environ = _environ(box)
    environ[sso_names.ENV_S3_SECRET_KEY] = "demo\n[other]"

    _start(box, environ, Runner(box.log))

    assert _step(report_contract.SYNC_STEP_PROFILE)["status"] == report_contract.STATUS_FAILED
    assert not (box.home / ".aws").exists()


def test_a_profile_name_cannot_break_the_section_header(box: SimpleNamespace) -> None:
    _start(box, _environ(box, CAPA_S3_PROFILE="demo]\n[evil"), Runner(box.log))

    assert _step(report_contract.SYNC_STEP_PROFILE)["status"] == report_contract.STATUS_FAILED


def test_an_unwritable_home_is_a_failed_line_not_a_stopped_start(box: SimpleNamespace) -> None:
    (box.home / ".aws").write_text("폴더 자리에 파일", encoding="utf-8")

    launched = _start(box, _environ(box), Runner(box.log))

    assert len(launched) == 1
    assert _step(report_contract.SYNC_STEP_PROFILE)["status"] == report_contract.STATUS_FAILED


# --------------------------------------------------------------------------- 점검 줄
@pytest.mark.parametrize(
    ("answer", "status", "reason"),
    [
        (_line("aws-cli/1.46.3 Python/3.10.11 Linux"), "ok", "1.46.3"),
        (_line("aws-cli/2.36.8 Python/3.14"), "failed", "판 다름 2.36.8"),
        (FileNotFoundError("aws"), "failed", "명령 없음"),
        (_line("", 1), "failed", "실행 실패"),
        (_line("찍힌 것이 판이 아님", 0), "failed", "실행 실패"),
        (subprocess.TimeoutExpired(["aws"], 1), "failed", "실행 실패"),
        (PermissionError("aws"), "failed", "실행 실패"),
    ],
    ids=["같음", "판 다름", "명령 없음", "실패 코드", "못 읽음", "시간 초과", "권한"],
)
def test_the_aws_line_tells_three_failures_apart(
    box: SimpleNamespace, answer: Answer, status: str, reason: str
) -> None:
    _start(box, _environ(box), Runner(box.log, aws=lambda _a: answer))

    assert _step(report_contract.SYNC_STEP_CLI) == {"status": status, "reason": reason}


def test_an_aws_line_on_stderr_is_read_as_well(box: SimpleNamespace) -> None:
    """옛 판은 `--version` 을 표준 오류로 찍는다."""
    answer = subprocess.CompletedProcess([], 0, stdout="", stderr="aws-cli/1.46.3 Python")

    _start(box, _environ(box), Runner(box.log, aws=lambda _a: answer))

    assert _sync()["aws_version"] == "1.46.3"


@pytest.fixture
def mock_store() -> Iterator[tuple[MockStore, str]]:
    store = MockStore()
    server, endpoint = start_mock(store)
    yield store, endpoint
    server.shutdown()
    server.server_close()


def test_a_403_from_the_store_means_it_was_reached(mock_store: tuple[MockStore, str]) -> None:
    """인증 없는 요청이라 403 이 정상이다."""
    _store, endpoint = mock_store

    result = container_start.ecs_step(endpoint)

    assert result == container_start.StepResult("ok", "HTTP 403 닿음")


def test_a_server_error_is_not_reached(mock_store: tuple[MockStore, str]) -> None:
    store, endpoint = mock_store
    store.force["GET"] = (503, "SlowDown")

    assert container_start.ecs_step(endpoint).status == "failed"


def test_a_closed_port_reads_as_refused() -> None:
    assert container_start.ecs_step(CLOSED_ENDPOINT).reason == "연결 거부"


def test_an_unknown_name_reads_as_not_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_name(*_args: object, **_kwargs: object) -> list[object]:
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", no_name)

    assert container_start.ecs_step("http://store.example.invalid:9020").reason == "이름 못 풂"


def test_a_silent_port_reads_as_timed_out() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen()
        port = silent.getsockname()[1]

        result = container_start.ecs_step(f"http://127.0.0.1:{port}", timeout=0.2)

    assert result.reason == "시간 초과"


def test_a_strange_address_is_refused_without_opening_it() -> None:
    assert container_start.ecs_step("file:///etc/passwd").reason == "주소 꼴이 틀림"


@pytest.mark.parametrize(
    ("stderr", "reason"),
    [
        ("An error occurred (AccessDenied) when calling", "저장소가 거절"),
        ("An error occurred (NoSuchBucket) when calling", "버킷 없음"),
        ("Could not connect to the endpoint URL", "저장소에 닿지 못함"),
    ],
)
def test_the_bucket_line_gives_the_word_not_the_message(
    box: SimpleNamespace, mock_store: tuple[MockStore, str], stderr: str, reason: str
) -> None:
    _store, endpoint = mock_store

    def aws(args: Sequence[str]) -> Answer:
        if "--version" in args:
            return _line(f"aws-cli/{report_contract.AWS_CLI_VERSION}")
        return subprocess.CompletedProcess([], 254, stdout="", stderr=f"{stderr} {endpoint}")

    environ = _environ(box)
    environ[sso_names.ENV_S3_ENDPOINT] = endpoint
    _start(box, environ, Runner(box.log, aws=aws))

    assert _step(report_contract.SYNC_STEP_BUCKET)["reason"] == reason
    assert endpoint not in json.dumps(_report(), ensure_ascii=False)


def test_the_bucket_is_not_listed_when_the_store_was_not_reached(box: SimpleNamespace) -> None:
    runner = Runner(box.log)

    _start(box, _environ(box), runner)

    assert _step(report_contract.SYNC_STEP_BUCKET)["status"] == report_contract.STATUS_SKIPPED
    aws_calls = [call for call in runner.calls if call[0] == "aws"]
    assert [call[1] for call in aws_calls] == ["--version"]


def test_the_children_find_aws_on_the_path_they_were_given(box: SimpleNamespace) -> None:
    runner = Runner(box.log)

    _start(box, _environ(box), runner)

    [env] = [env for call, env in zip(runner.calls, runner.envs, strict=True) if call[0] == "aws"]
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == str(box.home)
    assert env["AWS_REQUEST_CHECKSUM_CALCULATION"] == "when_required"


def test_the_duckdb_probe_really_runs() -> None:
    """이 컨테이너가 고른 한도 · 스레드. 코드 글자가 틀리면 빈 값이 되어 조용히 사라진다."""
    environ = {**os.environ}

    facts = container_start.duckdb_defaults(container_start.run_command, environ)

    assert facts["duckdb_memory_limit"]
    assert str(facts["duckdb_threads"]).isdecimal()


@pytest.mark.parametrize(
    ("files", "memory", "cpu"),
    [
        ({"memory.max": "1073741824\n", "cpu.max": "200000 100000\n"}, 1 << 30, 2.0),
        ({"memory.max": "max\n", "cpu.max": "max 100000\n"}, None, None),
        (
            {
                "memory/memory.limit_in_bytes": "2147483648\n",
                "cpu/cpu.cfs_quota_us": "150000\n",
                "cpu/cpu.cfs_period_us": "100000\n",
            },
            1 << 31,
            1.5,
        ),
        (
            {
                "memory/memory.limit_in_bytes": "9223372036854771712\n",
                "cpu/cpu.cfs_quota_us": "-1\n",
                "cpu/cpu.cfs_period_us": "100000\n",
            },
            None,
            None,
        ),
        ({}, None, None),
    ],
    ids=["v2 제한", "v2 없음", "v1 제한", "v1 없음", "못 읽음"],
)
def test_cgroup_limits_are_read_from_both_layouts(
    tmp_path: Path, files: dict[str, str], memory: int | None, cpu: float | None
) -> None:
    for name, text in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    facts = container_start.machine_facts({"HOSTNAME": "demo-pod-0"}, cgroup_root=tmp_path)

    assert facts["memory_limit_bytes"] == memory
    assert facts["cpu_limit"] == cpu
    assert facts["pod"] == "demo-pod-0"
    assert isinstance(facts["disk_free_bytes"], int)


# --------------------------------------------------------------------------- 결과 칸
def test_the_report_carries_the_pull_and_the_machine(box: SimpleNamespace) -> None:
    _start(box, _managed(box), Runner(box.log, [_boot(DOWNLOADED)]))

    parsed = report_contract.read_container_start_report()

    assert parsed is not None and parsed.sync is not None
    sync = parsed.sync
    assert sync.steps[report_contract.SYNC_STEP_PULL] == report_contract.StartStep(
        "ok", "세대 7 · 받음"
    )
    assert sync.pull_seconds == 2.5
    assert sync.pull_attempts == 1
    assert sync.previous_upload_utc == "2026-11-07T00:00:00Z"
    assert sync.pod == "demo-pod-0"
    assert sync.started_at_utc is not None
    assert sync.duckdb_memory_limit == "800.0 MiB"
    assert sync.duckdb_threads == "2"
    assert sync.disk_total_bytes is not None
    assert sync.logical_cores is not None


def test_a_pull_that_kept_the_disk_says_so(box: SimpleNamespace) -> None:
    kept = {**DOWNLOADED, "action": "kept"}

    _start(box, _managed(box), Runner(box.log, [_boot(kept)]))

    assert _step(report_contract.SYNC_STEP_PULL)["reason"] == "세대 7 · 그대로"


def test_the_check_table_and_lines_show_the_new_values(box: SimpleNamespace) -> None:
    _start(box, _managed(box), Runner(box.log, [_boot(DOWNLOADED)]))
    parsed = report_contract.read_container_start_report()
    assert parsed is not None and parsed.sync is not None

    rows = start_check.sync_rows(parsed)
    lines = start_check.sync_fact_lines(parsed, "2026-11-07T00:01:40Z")

    assert [row[0] for row in rows] == list(report_contract.SYNC_STEP_LABELS.values())
    joined = "\n".join(lines)
    assert "/project 디스크: 여유 " in joined
    assert "pod: demo" in joined
    assert "DuckDB 기본값: memory_limit" in joined
    assert "받기 2.5초" in joined
    assert "앞 pod 마지막 올림 → 이번 앱 준비: 100초" in joined


def test_the_app_response_is_measured_from_the_start_of_the_script() -> None:
    sync = report_contract.SyncStart(
        steps={},
        started_at_utc="2026-11-07T00:00:00Z",
        pull_seconds=30.25,
        previous_upload_utc="2026-11-06T23:59:00Z",
    )
    report = report_contract.ContainerStartReport(
        written_at="",
        steps={},
        bigdataquery_version=None,
        token_file_exists=None,
        token_file_modified_at=None,
        user_name_masked=None,
        missing_environment=(),
        pip_tail=(),
        sync=sync,
    )

    lines = start_check.sync_fact_lines(report, "2026-11-07T00:00:45Z")

    assert lines == ["받기 30.2초 · 앱 응답까지 45초", "앞 pod 마지막 올림 → 이번 앱 준비: 105초"]


def test_lines_with_nothing_to_show_are_left_out() -> None:
    report = report_contract.ContainerStartReport(
        written_at="",
        steps={},
        bigdataquery_version=None,
        token_file_exists=None,
        token_file_modified_at=None,
        user_name_masked=None,
        missing_environment=(),
        pip_tail=(),
        sync=report_contract.SyncStart(steps={}),
    )

    assert start_check.sync_fact_lines(report, None) == []
    assert start_check.sync_rows(report) == []


def test_an_old_report_has_no_sync_and_no_new_lines(box: SimpleNamespace) -> None:
    _start(box, {"HOME": str(box.home)}, Runner(box.log))
    parsed = report_contract.read_container_start_report()

    assert parsed is not None and parsed.sync is None
    assert start_check.sync_rows(parsed) == []
    assert start_check.sync_fact_lines(parsed, None) == []


@pytest.mark.parametrize(
    "broken",
    [
        {"steps": "아님"},
        {"steps": {"aws_cli": {"status": "모름", "reason": "x"}}},
        {"steps": {"aws_cli": "아님"}, "pull_seconds": "느림", "pull_attempts": True},
        {"disk_free_bytes": "많음", "logical_cores": 1.5, "cpu_limit": "많음"},
    ],
)
def test_a_broken_sync_part_does_not_lose_the_rest(
    box: SimpleNamespace, broken: dict[str, object]
) -> None:
    _start(box, {"HOME": str(box.home)}, Runner(box.log))
    data = {**_report(), "sync": broken}

    parsed = report_contract.parse_report(data)

    assert parsed is not None and parsed.sync is not None
    assert parsed.sync.steps == {}
    assert parsed.sync.pull_seconds is None
    assert parsed.sync.disk_free_bytes is None


def test_a_failed_sync_line_turns_the_title_to_failed(box: SimpleNamespace) -> None:
    runner = Runner(box.log, aws=lambda _a: FileNotFoundError("aws"))
    _start(box, _environ(box), runner)
    parsed = report_contract.read_container_start_report()

    assert parsed is not None
    assert report_contract.report_verdict(parsed) == "실패 있음"


def test_the_app_notes_when_it_was_ready_only_once(box: SimpleNamespace) -> None:
    _start(box, {"HOME": str(box.home)}, Runner(box.log))

    report_contract.note_app_ready()
    first = report_contract.read_app_ready()
    report_contract.app_ready_path().write_text(
        json.dumps({"ready_at_utc": "2026-11-07T00:00:00Z"}), encoding="utf-8"
    )
    report_contract.note_app_ready()

    assert first is not None
    assert report_contract.read_app_ready() == "2026-11-07T00:00:00Z"


def test_a_new_start_forgets_the_last_ready_time(box: SimpleNamespace) -> None:
    _start(box, {"HOME": str(box.home)}, Runner(box.log))
    report_contract.note_app_ready()

    _start(box, {"HOME": str(box.home)}, Runner(box.log))

    assert report_contract.read_app_ready() is None


def test_a_place_the_script_never_ran_gets_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """개발 · 사내 PC 는 `capa_server.py` 로 띄워도 파일을 늘리지 않는다."""
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "container_start.json")

    report_contract.note_app_ready()

    assert list(tmp_path.iterdir()) == []


def test_the_server_entry_notes_readiness_after_building_the_app() -> None:
    source = (PROJECT_ROOT / "capa_server.py").read_text(encoding="utf-8")

    assert source.index("app = st.App(") < source.index("note_app_ready()\n")


@pytest.mark.parametrize(
    ("earlier", "later", "seconds"),
    [
        ("2026-11-07T00:00:00Z", "2026-11-07T00:01:00Z", 60.0),
        (None, "2026-11-07T00:01:00Z", None),
        ("2026-11-07T00:00:00Z", None, None),
        ("어제", "2026-11-07T00:01:00Z", None),
        ("2026-11-07T00:00:00", "2026-11-07T00:01:00Z", None),
    ],
)
def test_seconds_between_refuses_what_it_cannot_read(
    earlier: str | None, later: str | None, seconds: float | None
) -> None:
    assert report_contract.seconds_between(earlier, later) == seconds


def test_the_image_pins_aws_on_its_own_line_with_the_checked_version() -> None:
    dockerfile = (PROJECT_ROOT / "docker" / "Dockerfile-prod").read_text(encoding="utf-8")
    lines = [line.strip() for line in dockerfile.splitlines()]
    expected = f"RUN pip install awscli=={report_contract.AWS_CLI_VERSION} --no-cache-dir"

    assert expected in lines
    assert lines.index(expected) > next(
        index for index, line in enumerate(lines) if "/project/requirements.txt" in line
    )


def test_a_key_in_the_build_context_stays_out_of_the_image() -> None:
    ignored = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert "**/.aws/" in ignored


def test_the_wrong_mode_does_not_block_the_stage_or_the_report(box: SimpleNamespace) -> None:
    """모드가 틀려도 점검 값은 남는다 — 그래서 고칠 줄을 Admin 에서 본다."""
    _start(box, _environ(box, CAPA_S3_SYNC_MODE="틀린값"), Runner(box.log))

    assert _step(report_contract.SYNC_STEP_CLI)["status"] == report_contract.STATUS_OK


def test_an_unexpected_failure_in_the_checks_does_not_stop_the_pull(
    box: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("점검이 깨짐")

    monkeypatch.setattr(container_start, "prepare_sync", explode)

    launched = _start(box, _managed(box), Runner(box.log, [_boot(DOWNLOADED)]))

    assert len(launched) == 1
    assert _step(report_contract.SYNC_STEP_PULL)["status"] == report_contract.STATUS_OK


def test_a_failed_stage_does_not_stop_the_start(
    box: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(port: int, *, base_path: str = "/") -> container_stage.Stage:
        raise OSError("못 잡음")

    monkeypatch.setattr(container_stage, "open_stage", explode)

    launched = _start(box, {"HOME": str(box.home)}, Runner(box.log))

    assert len(launched) == 1
