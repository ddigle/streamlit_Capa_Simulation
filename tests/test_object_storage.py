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
    bucket="Demo_dev_bucket",
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


def _ok(stdout: str) -> CommandResult:
    return CommandResult((), 0, stdout, "", 0.0)


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
    assert argv[argv.index("--bucket") + 1] == "Demo_dev_bucket"
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


CONDITIONAL_SETTINGS = StorageSettings(
    mode="managed",
    endpoint_url=SETTINGS.endpoint_url,
    bucket=SETTINGS.bucket,
    profile=SETTINGS.profile,
    region=SETTINGS.region,
    capabilities={"conditional_put_if_none_match_star": True},
)


def _endpoint_error(
    key: str, *, wording: str = "Could not connect to the endpoint URL"
) -> CommandResult:
    """botocore 의 연결 오류 꼴. 경로 스타일 URL 을 버킷·키까지 통째로 찍는다."""
    url = f"{SETTINGS.endpoint_url}/{SETTINGS.bucket}/{key}"
    return CommandResult((), 255, "", f'\n{wording}: "{url}"\n', 0.0)


def test_a_snapshot_put_whose_key_holds_412_is_retried_then_raised(tmp_path: Path) -> None:
    """2026-04-12 의 키에는 "412" 가 든다. 연결 오류를 선점 실패로 읽으면 실패한 업로드가 성공처럼
    지나가고 포인터가 없는 스냅샷을 가리키게 된다."""
    key = "simulation/snapshots/000000000012__20260412T101500Z__ab12cd34.duckdb"
    source = tmp_path / "snapshot.duckdb"
    source.write_bytes(b"x")
    runner = FakeRunner(responses=[_endpoint_error(key) for _ in range(3)])

    with pytest.raises(ObjectStorageError, match="Could not connect"):
        _client(runner).put_file(key, source, content_md5_base64="bWQ1")

    assert len(runner.calls) == 3


def test_a_conditional_put_does_not_read_a_connection_error_as_a_lost_race(
    tmp_path: Path,
) -> None:
    """seq 587 의 포인터 키는 `999999999412__…` 다. 조건부 쓰기라도 연결 오류는 오류다."""
    key = "simulation/heads/999999999412__ab12cd34.json"
    source = tmp_path / "pointer.json"
    source.write_text("{}", encoding="utf-8")
    runner = FakeRunner(responses=[_endpoint_error(key) for _ in range(3)])

    with pytest.raises(ObjectStorageError, match="Could not connect"):
        _client(runner, settings=CONDITIONAL_SETTINGS).put_file(key, source, if_none_match=True)

    assert len(runner.calls) == 3


def test_head_does_not_read_a_timeout_as_a_missing_key() -> None:
    """키에 "404" 가 든 시간 초과를 「없음」으로 읽으면 있는 스냅샷을 못 찾았다고 멈춘다."""
    key = "simulation/snapshots/000000000007__20260404T081500Z__ab12cd34.duckdb"
    runner = FakeRunner(
        responses=[_endpoint_error(key, wording="Read timeout on endpoint URL") for _ in range(3)]
    )

    with pytest.raises(ObjectStorageError, match="Read timeout"):
        _client(runner).head(key)

    assert len(runner.calls) == 3


def test_an_unconditional_put_raises_on_a_precondition_failure(tmp_path: Path) -> None:
    """조건 없이 올린 쓰기는 선점에 질 수 없다. 그 응답을 넘기면 빠진 업로드가 성공으로 남는다."""
    source = tmp_path / "snapshot.duckdb"
    source.write_bytes(b"x")
    failure = "An error occurred (PreconditionFailed) when calling the PutObject operation"
    runner = FakeRunner(responses=[CommandResult((), 254, "", failure, 0.0) for _ in range(3)])

    with pytest.raises(ObjectStorageError):
        _client(runner).put_file(
            "simulation/snapshots/000000000001__20260908T091500Z__abcd1234.duckdb", source
        )


@pytest.mark.parametrize(
    "stderr",
    [
        "An error occurred (412) when calling the PutObject operation: Precondition Failed",
        "An error occurred (PreconditionFailed) when calling the PutObject operation: "
        "At least one of the pre-conditions you specified did not hold",
    ],
)
def test_aws_precondition_errors_are_still_reported(tmp_path: Path, stderr: str) -> None:
    source = tmp_path / "pointer.json"
    source.write_text("{}", encoding="utf-8")
    runner = FakeRunner(responses=[CommandResult((), 254, "", stderr, 0.0)])

    outcome = _client(runner, settings=CONDITIONAL_SETTINGS).put_file(
        "simulation/heads/x.json", source, if_none_match=True
    )

    assert outcome.precondition_failed is True
    assert len(runner.calls) == 1


def test_aws_head_404_is_still_a_missing_key() -> None:
    runner = FakeRunner(
        responses=[
            CommandResult(
                (),
                254,
                "",
                "An error occurred (404) when calling the HeadObject operation: Not Found",
                0.0,
            )
        ]
    )

    assert _client(runner).head("simulation/heads/none.json") is None
    assert len(runner.calls) == 1


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


def test_settings_default_to_local_mode_with_no_in_house_values() -> None:
    """스위치를 잊어도 사내 스토리지에 손대지 않는다. 주소 · 버킷 · 프로필은 기본값이 없다."""
    settings = object_storage.load_settings(environ={})

    assert settings.mode == "local"
    assert (settings.endpoint_url, settings.bucket, settings.profile) == ("", "", "")
    assert settings.region == object_storage.DEFAULT_REGION
    assert object_storage.missing_environment(settings) == (
        "CAPA_S3_ENDPOINT_URL",
        "CAPA_S3_BUCKET",
        "CAPA_S3_PROFILE",
    )
    assert object_storage.missing_environment(settings, bucket=False) == (
        "CAPA_S3_ENDPOINT_URL",
        "CAPA_S3_PROFILE",
    )


def test_blank_environment_values_count_as_missing() -> None:
    """사용자 환경변수에 공백만 들어가도 값이 아니다 — 빈 값과 같은 길로 멈춘다."""
    settings = object_storage.load_settings(
        environ={"CAPA_S3_ENDPOINT_URL": " ", "CAPA_S3_BUCKET": "\t", "CAPA_S3_PROFILE": " demo "}
    )

    assert settings.profile == "demo"
    assert object_storage.missing_environment(settings) == (
        "CAPA_S3_ENDPOINT_URL",
        "CAPA_S3_BUCKET",
    )


def test_the_settings_file_cannot_supply_in_house_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """주소 · 버킷 · 프로필은 환경변수로만 받는다 — 설정 파일에 적어도 읽지 않는다(공개 저장소)."""
    config = tmp_path / "object_storage.json"
    config.write_text(
        json.dumps(
            {
                "mode": "local",
                "region": "demo-region-1",
                "endpoint_url": "http://s3.demo.invalid:9020",
                "bucket": "Demo_file_bucket",
                "profile": "demo-file-profile",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(object_storage, "CONFIG_PATH", config)

    settings = object_storage.load_settings(environ={})

    assert (settings.endpoint_url, settings.bucket, settings.profile) == ("", "", "")
    assert settings.region == "demo-region-1"


def test_no_command_is_built_while_an_in_house_value_is_missing() -> None:
    """빈 주소 · 버킷 · 프로필로 `aws` 를 부르지 않는다 — 어디로 갈지 aws 의 기본이 정하게 된다.

    넣을 환경변수 이름을 대는 한 줄로 멈추고, 실패 갈래는 `config` 다.
    """
    runner = FakeRunner()
    blank = StorageSettings(
        mode="managed",
        endpoint_url="",
        bucket="Demo_dev_bucket",
        profile="",
        region="us-east-1",
        capabilities={},
    )
    client = _client(runner, settings=blank)

    for call in (
        lambda: client.list_objects("simulation/heads/"),
        lambda: client.head("simulation/heads/x.json"),
        lambda: client.delete("simulation/heads/x.json"),
        client.check_addressing_style,
    ):
        with pytest.raises(object_storage.StorageSettingsError) as caught:
            call()
        assert caught.value.label == object_storage.SETTINGS_MISSING
        assert str(caught.value).endswith("CAPA_S3_ENDPOINT_URL · CAPA_S3_PROFILE")
        assert "\n" not in str(caught.value)
        assert object_storage.classify_failure(caught.value) == "config"
    assert runner.calls == []
    with pytest.raises(object_storage.StorageSettingsError):
        object_storage.render_profile_files(blank, access_key="k", secret_key="s")


def test_unknown_mode_is_refused() -> None:
    with pytest.raises(ObjectStorageError, match="local 또는 managed"):
        object_storage.load_settings(environ={"CAPA_S3_SYNC_MODE": "auto"})


def test_committed_config_keeps_local_mode() -> None:
    """사내 설정이 실수로 커밋되면 개발 PC 가 사내 스토리지를 건드린다. 사내 값 칸도 없다."""
    if not object_storage.CONFIG_PATH.exists():
        pytest.skip("설정 파일이 아직 없습니다.")
    payload = json.loads(object_storage.CONFIG_PATH.read_text(encoding="utf-8"))

    assert payload.get("mode") == "local"
    assert not {"endpoint_url", "bucket", "profile"} & set(payload)


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


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 자식에게 핸들을 물려주는 부름. Streamlit 1.63 은 듣는 소켓을 상속 가능으로 열어 그런 자식은
# 앱을 끈 뒤에도 8501 을 쥔다(사내 리뷰 202610200720 발견 3 · 런북 4-2 「접속이 안 되면」).
_INHERITING_CALLS = ("close_fds=False", "os.system(", "os.spawn", "os.popen(", "os.startfile(")


def test_the_app_starts_no_child_that_inherits_the_listening_socket() -> None:
    sources = [_PROJECT_ROOT / "app.py"]
    sources += sorted((_PROJECT_ROOT / "app_pages").rglob("*.py"))
    sources += sorted((_PROJECT_ROOT / "src").rglob("*.py"))
    found = [
        f"{path.relative_to(_PROJECT_ROOT)}: {call}"
        for path in sources
        for call in _INHERITING_CALLS
        if call in path.read_text(encoding="utf-8")
    ]
    assert found == []
    runner = (_PROJECT_ROOT / "src/capa_simulation/io/object_storage.py").read_text(
        encoding="utf-8"
    )
    assert "subprocess.run(" in runner and "close_fds" not in runner


def test_list_all_objects_follows_the_continuation_token() -> None:
    """한 쪽만 받으면 뒤쪽 스냅샷이 없는 것으로 보여 정리가 산 세대를 고아로 본다."""
    pages = [
        {"Contents": [{"Key": "a", "Size": 1}], "IsTruncated": True, "NextContinuationToken": "t"},
        {"Contents": [{"Key": "b", "Size": 2}]},
    ]
    runner = FakeRunner(responses=[_ok(json.dumps(page)) for page in pages])
    client = _client(runner)

    records = client.list_all_objects("simulation/snapshots/")

    assert [record.key for record in records] == ["a", "b"]
    assert "--continuation-token" in runner.calls[1]


def test_a_repeating_continuation_token_stops_instead_of_looping() -> None:
    page = {"Contents": [], "IsTruncated": True, "NextContinuationToken": "t"}
    runner = FakeRunner(responses=[_ok(json.dumps(page)) for _ in range(3)])

    with pytest.raises(ObjectStorageError, match="되풀이"):
        _client(runner).list_all_objects("x/")


@pytest.mark.parametrize(
    ("returncode", "stderr", "expected"),
    [
        (127, "aws 실행 파일을 찾지 못했습니다.", "cli_missing"),
        (124, "제한 시간을 넘겼습니다.", "timeout"),
        (255, 'Could not connect to the endpoint URL: "http://fake/"', "unreachable"),
        (255, "Read timeout on endpoint URL", "timeout"),
        (254, "An error occurred (AccessDenied) when calling", "denied"),
        (254, "An error occurred (403) when calling", "denied"),
        (254, "An error occurred (InvalidAccessKeyId) when calling", "denied"),
        (254, "An error occurred (NoSuchBucket) when calling", "no_bucket"),
        (254, "An error occurred (InternalError) when calling", "other"),
        (252, "usage: aws", "config"),
        (255, "[Errno 28] No space left on device", "disk_full"),
        (255, "The config profile (demo-org-team) could not be found", "config"),
        (255, "Unable to locate credentials. You can configure credentials", "config"),
        (
            255,
            "An error occurred while reading from response stream: ('Connection broken: "
            "IncompleteRead(3145363 bytes read, 29815149 more expected)', ...)",
            "unreachable",
        ),
    ],
)
def test_failures_become_a_fixed_word(returncode: int, stderr: str, expected: str) -> None:
    """화면에는 서버 글을 싣지 않는다 — 주소 · 버킷 이름이 든다."""
    result = CommandResult(("aws",), returncode, "", stderr, 0.0)

    assert object_storage.classify_failure(ObjectStorageError("실패", result=result)) == expected


def test_failures_outside_the_boundary_have_words_too() -> None:
    assert object_storage.classify_failure(ObjectStorageError("설정")) == "config"
    assert object_storage.classify_failure(OSError(28, "No space left")) == "disk_full"
    assert object_storage.classify_failure(RuntimeError("?")) == "other"


def test_profile_lines_are_one_set() -> None:
    """시작 스크립트와 `profile` 명령이 같은 줄을 쓴다. 체크섬 두 줄 · path 스타일이 빠지면 ECS 가
    거절한다."""
    names = [name for name, _ in object_storage.profile_settings(SETTINGS)]

    assert names == [
        "region",
        "endpoint_url",
        "request_checksum_calculation",
        "response_checksum_validation",
        "s3.addressing_style",
    ]


def test_scratch_names_differ_for_the_same_key(tmp_path: Path) -> None:
    """같은 키를 함께 받아도 서로의 작업 파일을 지우지 않는다."""
    runner = FakeRunner()
    client = _client(runner)

    for _ in range(2):
        with pytest.raises(FileNotFoundError):
            client.get_text("k", scratch_dir=tmp_path)

    names = [call[-1] for call in runner.calls]
    assert names[0] != names[1]


def test_there_is_no_default_bucket() -> None:
    """운영 · 개발 어느 버킷도 코드가 고르지 않는다 — `CAPA_S3_BUCKET` 으로만 받는다."""
    settings = object_storage.load_settings(environ={})

    assert settings.bucket == ""
    assert object_storage.load_settings(environ={"CAPA_S3_BUCKET": "Demo_ops"}).bucket == "Demo_ops"


def test_the_settings_environment_names_match_the_access_list() -> None:
    """S3 명단(`auth.names`)과 같은 이름이다 — 한쪽만 바꾸면 사내 값을 두 번 넣게 된다."""
    from capa_simulation.auth import names

    assert object_storage.ENDPOINT_ENV == names.ENV_S3_ENDPOINT
    assert object_storage.BUCKET_ENV == names.ENV_S3_BUCKET
    assert object_storage.REGION_ENV == names.ENV_S3_REGION
