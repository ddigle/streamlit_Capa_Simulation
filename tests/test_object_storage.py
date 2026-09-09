# Purpose: 오브젝트 스토리지 명령 조립·설정·실패 해석을 aws 없이 검증한다.

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from capa_simulation.io import object_storage
from capa_simulation.io.object_storage import (
    CommandResult,
    ObjectStorageClient,
    ObjectStorageError,
    StorageSettings,
)

SETTINGS = StorageSettings(
    mode="managed",
    endpoint_url="http://s3.demo.invalid:9020",
    bucket="Capa_simulation_project",
    profile="demo-org-team",
    region="us-east-1",
    capabilities={},
)


@dataclass
class FakeRunner:
    """조립된 인자 배열을 그대로 기록하는 실행기. 이 PC 에는 aws 가 없다."""

    responses: list[CommandResult] = field(default_factory=list)
    calls: list[tuple[str, ...]] = field(default_factory=list)
    envs: list[Mapping[str, str]] = field(default_factory=list)

    def run(
        self, argv: Sequence[str], env: Mapping[str, str], *, timeout_seconds: float
    ) -> CommandResult:
        self.calls.append(tuple(argv))
        self.envs.append(dict(env))
        if self.responses:
            queued = self.responses.pop(0)
            return CommandResult(tuple(argv), queued.returncode, queued.stdout, queued.stderr, 0.0)
        return CommandResult(tuple(argv), 0, "{}", "", 0.0)


def _client(runner: FakeRunner, *, settings: StorageSettings = SETTINGS) -> ObjectStorageClient:
    return ObjectStorageClient(settings=settings, runner=runner, sleep=lambda _seconds: None)


def test_every_command_carries_the_profile() -> None:
    """프로필이 빠지면 다른 네임스페이스를 본다. 이 검사가 이 파일의 존재 이유다."""
    runner = FakeRunner()
    client = _client(runner)

    client.list_objects("simulation/heads/")
    client.head("simulation/heads/x.json")
    client.delete("simulation/heads/x.json")

    assert runner.calls
    for argv in runner.calls:
        assert "--profile" in argv
        assert argv[argv.index("--profile") + 1] == "demo-org-team"


def test_commands_target_the_configured_bucket_and_endpoint() -> None:
    runner = FakeRunner()

    _client(runner).list_objects("simulation/heads/")

    argv = runner.calls[0]
    assert argv[:3] == ("aws", "s3api", "list-objects-v2")
    assert argv[argv.index("--bucket") + 1] == "Capa_simulation_project"
    assert argv[argv.index("--endpoint-url") + 1] == "http://s3.demo.invalid:9020"


def test_path_addressing_and_checksum_optout_are_forced_by_environment() -> None:
    """버킷명에 대문자·언더바가 있어 경로 스타일이 아니면 서명이 어긋난다.

    체크섬 옵트아웃은 AWS CLI 2.23+ 과 ECS 의 알려진 비호환 우회다(Dell KB 000299507).
    """
    runner = FakeRunner()

    _client(runner).list_objects("simulation/heads/")

    env = runner.envs[0]
    assert env["AWS_S3_ADDRESSING_STYLE"] == "path"
    assert env["AWS_REQUEST_CHECKSUM_CALCULATION"] == "when_required"
    assert env["AWS_RESPONSE_CHECKSUM_VALIDATION"] == "when_required"
    assert env["AWS_PAGER"] == ""


def test_list_objects_parses_keys_sizes_and_etags() -> None:
    payload = {
        "Contents": [
            {
                "Key": "simulation/heads/999999999957__0000aaaa.json",
                "Size": 512,
                "ETag": '"abc123"',
                "LastModified": "2026-09-08T09:15:00+00:00",
            }
        ]
    }
    runner = FakeRunner(responses=[CommandResult((), 0, json.dumps(payload), "", 0.0)])

    records = _client(runner).list_objects("simulation/heads/")

    assert len(records) == 1
    assert records[0].size_bytes == 512
    assert records[0].etag == "abc123"
    assert records[0].last_modified is not None


def test_head_returns_none_for_a_missing_key() -> None:
    """없는 키는 예외가 아니라 None 이다. 최초 이관 전 빈 저장소가 정상 상태다."""
    runner = FakeRunner(
        responses=[CommandResult((), 254, "", "An error occurred (404) when calling", 0.0)]
    )

    assert _client(runner).head("simulation/heads/none.json") is None


def test_put_file_sends_content_md5_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "snapshot.duckdb"
    source.write_bytes(b"x")
    runner = FakeRunner()

    _client(runner).put_file(
        "simulation/snapshots/000000000001__20260908T091500Z__abcd1234.duckdb",
        source,
        content_md5_base64="bWQ1",
        metadata={"note": "리비전 저장"},
    )

    argv = runner.calls[0]
    assert argv[2] == "put-object"
    assert argv[argv.index("--content-md5") + 1] == "bWQ1"
    # 한글 메모가 그대로 들어가면 요청이 거부된다.
    assert "리비전" not in argv[argv.index("--metadata") + 1]


def test_conditional_put_is_refused_until_the_capability_is_confirmed(tmp_path: Path) -> None:
    """확인하지 못한 능력은 없는 것으로 본다. 조용히 폴백하지 않는다."""
    source = tmp_path / "pointer.json"
    source.write_text("{}", encoding="utf-8")
    runner = FakeRunner()

    with pytest.raises(ObjectStorageError, match="확인되지 않았습니다"):
        _client(runner).put_file("simulation/heads/x.json", source, if_none_match=True)

    assert runner.calls == []


def test_conditional_put_adds_the_flag_when_the_capability_is_present(tmp_path: Path) -> None:
    source = tmp_path / "pointer.json"
    source.write_text("{}", encoding="utf-8")
    runner = FakeRunner()
    settings = StorageSettings(
        mode="managed",
        endpoint_url=SETTINGS.endpoint_url,
        bucket=SETTINGS.bucket,
        profile=SETTINGS.profile,
        region=SETTINGS.region,
        capabilities={"conditional_put_if_none_match_star": True},
    )

    _client(runner, settings=settings).put_file(
        "simulation/heads/x.json", source, if_none_match=True
    )

    argv = runner.calls[0]
    assert argv[argv.index("--if-none-match") + 1] == "*"


def test_precondition_failure_is_reported_not_raised(tmp_path: Path) -> None:
    source = tmp_path / "pointer.json"
    source.write_text("{}", encoding="utf-8")
    runner = FakeRunner(
        responses=[CommandResult((), 254, "", "An error occurred (PreconditionFailed)", 0.0)]
    )
    settings = StorageSettings(
        mode="managed",
        endpoint_url=SETTINGS.endpoint_url,
        bucket=SETTINGS.bucket,
        profile=SETTINGS.profile,
        region=SETTINGS.region,
        capabilities={"conditional_put_if_none_match_star": True},
    )

    outcome = _client(runner, settings=settings).put_file(
        "simulation/heads/x.json", source, if_none_match=True
    )

    assert outcome.precondition_failed is True


def test_configuration_errors_are_not_retried() -> None:
    """자격증명·문법 오류는 몇 번을 걸어도 같다. 재시도는 시간만 태운다."""
    runner = FakeRunner(
        responses=[CommandResult((), 254, "", "An error occurred (InvalidAccessKeyId)", 0.0)]
    )

    with pytest.raises(ObjectStorageError):
        _client(runner).list_objects("simulation/heads/")

    assert len(runner.calls) == 1


def test_transient_failures_are_retried() -> None:
    runner = FakeRunner(
        responses=[
            CommandResult((), 255, "", "connection reset", 0.0),
            CommandResult((), 0, "{}", "", 0.0),
        ]
    )

    _client(runner).list_objects("simulation/heads/")

    assert len(runner.calls) == 2


def test_missing_aws_executable_is_explained_in_korean() -> None:
    result = CommandResult(("aws",), 127, "", "aws 실행 파일을 찾지 못했습니다.", 0.0)

    assert "aws 실행 파일" in object_storage.explain_failure(result)


def test_ecs_checksum_incompatibility_is_named_in_the_message() -> None:
    """이 오류를 방화벽·권한 문제로 오진하면 며칠을 태운다."""
    result = CommandResult(
        ("aws",), 254, "", "Missing required header for this request: Content-MD5", 0.0
    )

    message = object_storage.explain_failure(result)

    assert "Dell KB 000299507" in message
    assert "2.22" in message


def test_etag_mismatch_is_caught_for_single_part_uploads() -> None:
    object_storage.assert_single_put_etag("abc", local_md5_hex="ABC")

    with pytest.raises(ObjectStorageError, match="ETag"):
        object_storage.assert_single_put_etag("abc", local_md5_hex="def")


def test_multipart_etag_is_not_compared_to_md5() -> None:
    """멀티파트 ETag 는 MD5 가 아니다. 비교하면 늘 실패한다."""
    object_storage.assert_single_put_etag("abc-3", local_md5_hex="def")


def test_settings_prefer_environment_over_file_and_constants() -> None:
    settings = object_storage.load_settings(
        environ={
            "CAPA_S3_SYNC_MODE": "managed",
            "CAPA_S3_PROFILE": "other-profile",
            "CAPA_S3_BUCKET": "other-bucket",
        }
    )

    assert settings.mode == "managed"
    assert settings.profile == "other-profile"
    assert settings.bucket == "other-bucket"


def test_settings_default_to_local_mode() -> None:
    """스위치를 잊어도 사내 스토리지에 손대지 않는다."""
    settings = object_storage.load_settings(environ={})

    assert settings.mode == "local"
    assert settings.profile == object_storage.DEFAULT_PROFILE


def test_unknown_mode_is_refused() -> None:
    with pytest.raises(ObjectStorageError, match="local 또는 managed"):
        object_storage.load_settings(environ={"CAPA_S3_SYNC_MODE": "auto"})


def test_committed_config_keeps_local_mode() -> None:
    """사내 설정이 실수로 커밋되면 개발 PC 가 사내 스토리지를 건드린다."""
    if not object_storage.CONFIG_PATH.exists():
        pytest.skip("설정 파일이 아직 없습니다.")
    payload = json.loads(object_storage.CONFIG_PATH.read_text(encoding="utf-8"))

    assert payload.get("mode") == "local"


def test_transfer_timeout_grows_with_size_but_never_shrinks() -> None:
    """고정 300초는 지금 스냅샷에는 넉넉하지만 DB 가 커지면 그대로 상한이 된다.

    사내 실측(2026-09-09) 42.8 MiB 는 300초 안에 충분히 들어간다. 크기를 모르면 기본값을
    쓴다 — 짐작으로 제한시간을 줄이지 않는다.
    """
    mib = 1024 * 1024

    assert object_storage.transfer_timeout_seconds(None) == 300.0
    assert object_storage.transfer_timeout_seconds(0) == 300.0
    assert object_storage.transfer_timeout_seconds(43 * mib) == 300.0
    assert object_storage.transfer_timeout_seconds(300 * mib) > 300.0
    assert object_storage.transfer_timeout_seconds(
        600 * mib
    ) > object_storage.transfer_timeout_seconds(300 * mib)
