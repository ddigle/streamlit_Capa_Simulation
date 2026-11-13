# Purpose: 오브젝트 스토리지 운영 스크립트의 인자 처리와 설정 우선순위를 검증한다.

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "sync_object_storage.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sync_object_storage", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_object_storage"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return _load_script()


def test_every_subcommand_is_wired(script: ModuleType) -> None:
    """도움말에만 있고 구현이 없는 명령이 생기면 사내에서 처음 눌렀을 때 죽는다."""
    expected = {
        "profile",
        "doctor",
        "probe",
        "init",
        "status",
        "pull",
        "push",
        "resolve",
        "adopt",
        "prune",
        "fetch-copy",
        "rollback",
        "generations",
        "boot-pull",
    }

    assert set(script.COMMANDS) == expected


def test_command_line_profile_overrides_the_configured_one(script: ModuleType) -> None:
    """WebIDE 로 옮기면 프로필명이 바뀐다. 손으로 덮어쓸 수 있어야 한다."""
    args = script.parse_args(["--profile", "other-profile", "status"])

    settings = script.build_settings(args)

    assert settings.profile == "other-profile"


def test_in_house_values_come_only_from_the_environment_or_arguments(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """주소 · 버킷 · 프로필은 사내 값이라 저장소에 기본값이 없다 — 환경변수 · 인자로만 온다."""
    args = script.parse_args(["status"])

    empty = script.build_settings(args)

    assert (empty.endpoint_url, empty.bucket, empty.profile) == ("", "", "")
    # 커밋된 설정은 local 이어야 한다. 개발 PC 가 사내 스토리지를 건드리면 안 된다.
    assert empty.mode == "local"

    monkeypatch.setenv("CAPA_S3_ENDPOINT_URL", "http://s3.demo.invalid:9020")
    monkeypatch.setenv("CAPA_S3_BUCKET", "Demo_env_bucket")
    monkeypatch.setenv("CAPA_S3_PROFILE", "demo-env-profile")

    filled = script.build_settings(script.parse_args(["--bucket", "Demo_arg_bucket", "status"]))

    assert filled.endpoint_url == "http://s3.demo.invalid:9020"
    assert filled.bucket == "Demo_arg_bucket"
    assert filled.profile == "demo-env-profile"


def test_commands_stop_with_the_names_to_set_before_calling_aws(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """값이 비면 aws 를 부르지 않고 넣을 환경변수 이름 한 줄로 멈춘다 — 엉뚱한 곳에 가지 않는다."""
    monkeypatch.setenv("CAPA_S3_BUCKET", "Demo_env_bucket")

    def no_aws(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("빈 사내 값으로 aws 를 부르면 안 된다")

    monkeypatch.setattr(script.ObjectStorageClient, "_run", no_aws)
    monkeypatch.setattr(script.ObjectStorageClient, "cli_version", no_aws)
    # 저장소의 진짜 DB 자리를 이 프로세스의 등록에 남기지 않는다.
    monkeypatch.setattr(script.sync_state, "enable", lambda _paths: None)
    monkeypatch.setattr(script, "_blocked_by_running_app", lambda *_args: False)

    for command in ("status", "fetch-copy", "init", "generations"):
        argv = [command, "--to", "demo-copy"] if command == "fetch-copy" else [command]
        assert script.main(argv) == 1, command
        printed = capsys.readouterr().out
        first = printed.splitlines()[0]
        assert first.startswith("[중단] "), command
        assert first.endswith("CAPA_S3_ENDPOINT_URL · CAPA_S3_PROFILE"), command
        assert "--endpoint-url · --bucket · --profile" in printed

    assert script.command_doctor(script.parse_args(["doctor"])) == 1
    doctor = capsys.readouterr().out
    assert "엔드포인트    : (없음)" in doctor
    assert "버킷          : Demo_env_bucket" in doctor
    assert "[중단] " in doctor and "CAPA_S3_PROFILE" in doctor

    assert script.command_profile(script.parse_args(["profile"])) == 1
    profile = capsys.readouterr().out
    assert "aws configure set" not in profile
    assert "CAPA_S3_ENDPOINT_URL · CAPA_S3_PROFILE" in profile


def test_values_with_angle_brackets_spaces_or_quotes_stop_before_aws_and_name_only_the_source(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """꺾쇠 자리표째 넣은 버킷(`$b = "<…>"` 의 안쪽만 바꾼 꼴), 묻는 줄이 뒤 명령 줄을 먹은
    값(공백), 따옴표째 붙인 주소는 aws 를 부르기 전에 멈춘다. 값이 온 자리(인자 · 환경변수 이름)만
    대고 값은 어디에도 찍지 않는다 — doctor 의 값 줄도 찍기 전이다."""
    endpoint = "\u201chttp://s3.demo.invalid:9020\u201d"
    profile = "uv run --no-sync python scripts/sync_object_storage.py --bucket $b doctor"
    bucket = "<Demo_typed_bucket>"
    monkeypatch.setenv("CAPA_S3_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("CAPA_S3_PROFILE", profile)

    def no_aws(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("꼴이 틀린 사내 값으로 aws 를 부르면 안 된다")

    monkeypatch.setattr(script.object_storage.SubprocessCommandRunner, "run", no_aws)
    monkeypatch.setattr(script.sync_state, "enable", lambda _paths: None)
    monkeypatch.setattr(script, "_blocked_by_running_app", lambda *_args: False)

    for command in ("doctor", "status", "fetch-copy", "generations", "init", "profile"):
        extra = ["--to", "demo-copy"] if command == "fetch-copy" else []
        assert script.main(["--bucket", bucket, command, *extra]) == 1, command
        printed = capsys.readouterr().out
        assert printed.startswith("[중단] "), command
        assert len(printed.splitlines()) == 1, command
        assert "CAPA_S3_ENDPOINT_URL · --bucket · CAPA_S3_PROFILE" in printed, command
        for value in ("Demo_typed_bucket", "s3.demo.invalid", "sync_object_storage.py"):
            assert value not in printed, (command, value)

    monkeypatch.setenv("CAPA_S3_ENDPOINT_URL", "http://s3.demo.invalid:9020")
    monkeypatch.setenv("CAPA_S3_PROFILE", "demo-env-profile")
    monkeypatch.setenv("CAPA_S3_BUCKET", "'Demo_env_bucket'")
    assert script.main(["status"]) == 1
    printed = capsys.readouterr().out
    assert printed.startswith("[중단] ") and "— CAPA_S3_BUCKET." in printed
    assert "Demo_env_bucket" not in printed


def test_the_container_boot_pull_keeps_its_values_to_aws(script: ModuleType) -> None:
    """`boot-pull` 은 C-DEP 환경변수 표의 값이다 — 꼴을 가르지 않아 시작 스크립트가 읽는 갈래가
    그대로다."""
    args = script.parse_args(["--bucket", "<Demo_bucket>", "boot-pull"])

    assert script.build_settings(args).bucket == "<Demo_bucket>"
    assert script.malformed_sources(args, script.build_settings(args)) == ("--bucket",)


def test_dataset_selection_defaults_to_both_databases(script: ModuleType) -> None:
    assert script.datasets(script.parse_args(["status"])) == ["simulation", "equipment"]
    assert script.datasets(script.parse_args(["--dataset", "equipment", "status"])) == ["equipment"]


def test_prune_requires_an_explicit_yes(script: ModuleType) -> None:
    """정리는 되돌릴 수 없다. 확인 없이 지우지 않는다."""
    args = script.parse_args(["prune"])

    assert args.yes is False
    assert args.include_orphans is False
    assert args.keep_last == 5
    assert args.keep_days == 7


def test_rollback_requires_a_target(script: ModuleType) -> None:
    with pytest.raises(SystemExit):
        script.parse_args(["rollback"])

    assert script.parse_args(["rollback", "--to", "3"]).yes is False


def test_resolve_requires_choosing_a_side(script: ModuleType) -> None:
    with pytest.raises(SystemExit):
        script.parse_args(["resolve"])

    assert script.parse_args(["resolve", "--keep", "mine"]).keep == "mine"


def test_dataset_paths_cover_both_databases(script: ModuleType) -> None:
    assert set(script.DATASET_PATHS) == {"simulation", "equipment"}
    assert script.DATASET_PATHS["simulation"].name.endswith(".duckdb")


def test_profile_command_prints_a_ready_to_paste_block(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """사내 PC 에서 손으로 옮겨 적다가 오타 나는 일을 없앤다. 주소 · 프로필은 환경변수에서 온다."""
    monkeypatch.setenv("CAPA_S3_ENDPOINT_URL", "http://s3.demo.invalid:9020")
    monkeypatch.setenv("CAPA_S3_PROFILE", "demo-org-team")

    assert script.command_profile(script.parse_args(["profile"])) == 0

    printed = capsys.readouterr().out

    assert '$PROF = "demo-org-team"' in printed
    assert "--profile $PROF" in printed
    assert "aws configure set endpoint_url http://s3.demo.invalid:9020 --profile $PROF" in printed
    assert "s3.addressing_style path" in printed
    assert "request_checksum_calculation when_required" in printed
    assert "네임스페이스는 프로필(자격증명)에 매여" in printed


def test_profile_block_has_no_placeholder_and_asks_for_the_keys_on_its_last_line(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """블록째 붙여 넣는다 — 꺾쇠 자리표는 PowerShell 이 그 줄에서 멈추고, 묻는 줄이 중간에 있으면
    뒤에 붙은 줄을 키 값으로 먹는다. 키는 맨 끝 한 줄이 차례로 묻는다."""
    monkeypatch.setenv("CAPA_S3_ENDPOINT_URL", "http://s3.demo.invalid:9020")
    monkeypatch.setenv("CAPA_S3_PROFILE", "demo-org-team")

    assert script.command_profile(script.parse_args(["profile"])) == 0

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]

    assert not [line for line in lines if "<" in line or ">" in line]
    asking = [index for index, line in enumerate(lines) if "Read-Host" in line]
    assert asking == [len(lines) - 1]
    assert lines[-1].count("Read-Host") == 2
    assert "aws_access_key_id" in lines[-1] and "aws_secret_access_key" in lines[-1]
