# Purpose: 오브젝트 스토리지 운영 스크립트의 인자 처리와 설정 우선순위를 검증한다.

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator, Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from object_store_fakes import FakeStore, add_row, fake_client, fake_settings, seed_pair

from capa_simulation import settings as app_settings
from capa_simulation.audit import events, layout
from capa_simulation.io.object_storage import CommandResult, StorageSettings
from capa_simulation.persistence import sync_state
from capa_simulation.persistence._sql_helpers import connect
from capa_simulation.services import object_storage_manifest as manifest

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
        "audit-list",
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
    assert "엔드포인트    : 없음" in doctor
    assert "버킷          : De … et · 15자" in doctor
    assert "프로필        : 없음" in doctor
    assert "Demo_env_bucket" not in doctor
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
        lines = printed.splitlines()
        assert lines[0].startswith("[중단] "), command
        assert lines[1:] == (
            [] if command == "profile" else [f"전송용 요약: {command} 멈춤 설정 값 꼴 틀림; 종료 1"]
        ), command
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


def test_no_line_carries_an_in_house_value_when_aws_fails(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """aws 실패 글 · 「실행한 명령」 줄은 진단 경계(`explain_failure`)가 값째 만든다. 스크립트가
    받아 찍는 자리에서 이름표로 바꿔 어느 줄에도 원값이 없다 — 끝의 전송용 요약 꼴은 그대로다."""
    values = ("http://S3.Demo.invalid:9020", "Demo_secret_bucket", "demo-secret-profile")
    monkeypatch.setenv("CAPA_S3_ENDPOINT_URL", values[0])
    monkeypatch.setenv("CAPA_S3_BUCKET", values[1])
    monkeypatch.setenv("CAPA_S3_PROFILE", values[2])
    monkeypatch.setattr(script.sync_state, "enable", lambda _paths: None)

    def unreachable(
        _runner: object, argv: Sequence[str], _env: object, *, timeout_seconds: float
    ) -> CommandResult:
        # 서버 글은 호스트를 소문자로 찍는다.
        url = f"{values[0].lower()}/{values[1]}"
        text = f'Could not connect to the endpoint URL: "{url}" ({values[2]})'
        return CommandResult(tuple(argv), 255, "", text, 0.1)

    real_client = script.build_client
    monkeypatch.setattr(script.object_storage.SubprocessCommandRunner, "run", unreachable)
    monkeypatch.setattr(
        script, "build_client", lambda args: replace(real_client(args), sleep=lambda _s: None)
    )

    for command in ("doctor", "status", "generations"):
        assert script.main([command]) == 1, command
        printed = capsys.readouterr().out
        lines = printed.splitlines()
        assert lines[-1] == f"전송용 요약: {command} 멈춤 저장소에 닿지 못함; 종료 1", command
        assert not [value for value in values if value.lower() in printed.lower()], command
        assert "s3.demo.invalid" not in printed.lower(), command
        assert '"<주소>/<버킷>" (<프로필>)' in printed, command
        # doctor 는 `aws --version` 에서 먼저 멈춘다 — 그 명령 줄에는 값이 없다.
        if command != "doctor":
            assert "--bucket <버킷> --endpoint-url <주소> --profile <프로필>" in printed, command


def test_doctor_shows_the_bucket_as_its_ends_and_length_and_the_rest_as_present(
    script: ModuleType,
) -> None:
    """C-DEP 표 값과 앞 두 글자 · 뒤 두 글자 · 글자 수를 맞대 본다. 넷 이하면 앞뒤가 값 전부라
    글자 수만."""
    assert script.bucket_shape("Demo_env_bucket") == "De … et · 15자"
    assert script.bucket_shape("abcde") == "ab … de · 5자"
    assert script.bucket_shape("abcd") == "4자"
    assert script.bucket_shape("") == "없음"
    assert (script.presence("x"), script.presence("")) == ("있음", "없음")


def test_the_redaction_catches_every_form_of_the_endpoint_and_overlapping_values(
    script: ModuleType,
) -> None:
    """서버 글은 주소를 호스트 · `호스트:포트` · 소문자로도 찍는다. 버킷이 주소 뒤에 붙어 있어도
    긴 값부터 가린다."""
    redaction = script._Redaction()
    redaction.load(
        StorageSettings(
            mode="local",
            endpoint_url="https://S3.Demo.invalid:9021/",
            bucket="Demo_bucket",
            profile="demo-profile",
            region="us-east-1",
            capabilities={},
        )
    )
    text = (
        "https://s3.demo.invalid:9021/Demo_bucket?list-type=2 · "
        "HTTPSConnectionPool(host='s3.demo.invalid', port=9021) · s3.demo.invalid:9021 · "
        "config profile (demo-profile) could not be found · demo_bucket"
    )

    assert redaction.apply(text) == (
        "<주소><버킷>?list-type=2 · HTTPSConnectionPool(host='<주소>', port=9021) · <주소> · "
        "config profile (<프로필>) could not be found · <버킷>"
    )
    assert script.endpoint_forms("s3.demo.invalid:9021") == (
        "s3.demo.invalid:9021",
        "s3.demo.invalid",
    )
    redaction.clear()
    assert redaction.apply(text) == text


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


# --------------------------------------------------------------------------- 세대 지킴
@pytest.fixture()
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    """스크립트를 임시 두 DB 와 가짜 저장소에 붙인다 — 감사 조각도 그 저장소로 간다."""
    sync_state.clear_all()
    spec = importlib.util.spec_from_file_location("sync_object_storage_keep", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_object_storage_keep"] = module
    spec.loader.exec_module(module)
    paths = seed_pair(tmp_path)
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(module, "DATASET_PATHS", dict(paths.databases))
    store = FakeStore()
    monkeypatch.setattr(module, "build_settings", lambda _args: fake_settings())
    monkeypatch.setattr(module, "build_client", lambda _args: fake_client(store))
    yield SimpleNamespace(script=module, store=store, paths=paths)
    sync_state.clear_all()


def _main(rig: SimpleNamespace, capsys: pytest.CaptureFixture[str], *argv: str) -> list[str]:
    """명령 하나를 돌려 찍힌 줄을 돌려준다. 끝 줄은 늘 전송용 요약이다."""
    capsys.readouterr()
    code = rig.script.main(list(argv))
    lines: list[str] = capsys.readouterr().out.splitlines()
    assert lines[-1].startswith("전송용 요약: ") and f"; 종료 {code}" in lines[-1], lines
    return lines


def _generations(rig: SimpleNamespace, capsys: pytest.CaptureFixture[str], saves: int) -> None:
    """이관 + 저장 `saves` 번 — seq 1 부터 `saves + 1` 까지."""
    _main(rig, capsys, "init", "--keep-writer")
    database = rig.paths.databases["simulation"]
    for value in range(saves):
        add_row(database, value)
        sync_state.mark_dirty(database)
        assert rig.script.main(["push"]) == 0


def _tool_lines(rig: SimpleNamespace, event: str) -> list[dict[str, Any]]:
    keys = sorted(key for key in rig.store.objects if key.startswith(layout.TOOL_PREFIX))
    lines = [line for key in keys for line in layout.decode_lines(rig.store.objects[key])]
    return [line for line in lines if line["ev"] == event]


def _utc_today() -> datetime:
    return datetime.now(timezone.utc)


def test_keep_and_unkeep_are_wired_to_their_audit_events(script: ModuleType) -> None:
    """도구 명령마다 감사 사건이 목록에 있고, 그 사건이 받는 상세 키만 채운다."""
    assert {"keep", "unkeep"} <= set(script.COMMANDS)
    assert script.AUDITED_COMMANDS["keep"] == "admin_sync_keep"
    assert script.AUDITED_COMMANDS["unkeep"] == "admin_sync_unkeep"
    for event in script.AUDITED_COMMANDS.values():
        assert events.spec_of(event) is not None, event
    keep = events.spec_of("admin_sync_keep")
    unkeep = events.spec_of("admin_sync_unkeep")
    assert keep is not None and keep.det_keys == {"seq_to", "keep_until", "result"}
    assert unkeep is not None and unkeep.det_keys == {"seq_to", "result"}
    with pytest.raises(SystemExit):
        script.parse_args(["keep"])
    with pytest.raises(SystemExit):
        script.parse_args(["keep", "--head", "--seq", "3"])
    assert script.parse_args(["keep", "--head"]).days == 30
    assert script.parse_args(["unkeep", "--seq", "3"]).yes is False


def test_keep_head_summary_carries_seq_versions_and_expiry_only(
    rig: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """끝 줄은 지킨 seq · 두 멤버의 세대 · 마이그레이션 판 · 기한뿐이다 — 메모 · 버킷 · 주소 ·
    프로필 · 작성자는 어느 줄에도 없다. 포인터는 그대로이고 표지 하나만 는다."""
    _generations(rig, capsys, 0)
    database = rig.paths.databases["simulation"]
    with connect(database) as connection:
        connection.execute("INSERT INTO app_meta.schema_migration VALUES (7, 'demo', 'x')")
    sync_state.mark_dirty(database)
    assert rig.script.main(["push"]) == 0
    pointers = rig.store.pointer_keys()
    before = _utc_today().date()

    lines = _main(rig, capsys, "keep", "--head", "--note", "DEMO_SECRET_NOTE")

    after = _utc_today().date()
    expected = {
        "전송용 요약: keep 통과; 종료 0; 지킴 seq 2; 멤버 S2 E1; 판 S7 E1; "
        f"기한 {(day + timedelta(days=30)).isoformat()}"
        for day in (before, after)
    }
    assert lines[-1] in expected, lines[-1]
    assert lines[0].startswith("지킴 : seq 2 · 기한 ~")
    assert lines[1] == "멤버 : 시뮬레이션 2(판 7) · 가용설비 1(판 1)"
    printed = "\n".join(lines)
    for value in ("DEMO_SECRET_NOTE", "Demo_bucket", "fake:9020", "demo-org-team", "@"):
        assert value not in printed, value
    assert rig.store.pointer_keys() == pointers
    (marker,) = rig.store.keys(manifest.KEEP_PREFIX)
    assert manifest.parse_pin_marker_key(marker).seq == 2
    assert "DEMO_SECRET_NOTE" in rig.store.objects[marker].decode("utf-8")


def test_keep_rejects_days_out_of_range_before_aws(
    rig: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """범위 밖 일수는 aws 를 한 번도 부르지 않고 멈춘다 — 감사 조각도 올리지 않는다."""
    for days in ("0", "91", "-3"):
        rig.store.calls.clear()

        lines = _main(rig, capsys, "keep", "--head", "--days", days)

        assert lines[0] == "[중단] --days 는 1 ~ 90 입니다 — aws 를 부르지 않았습니다.", days
        assert lines[-1] == "전송용 요약: keep 멈춤 요청 거절; 종료 1", days
        assert rig.store.calls == [], days
    assert not rig.store.objects


def test_keep_stops_on_a_generation_it_cannot_find(
    rig: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """없는 세대는 `[중단]` 이고 표지를 두지 않는다. 실패도 감사 조각 한 줄로 남는다."""
    _generations(rig, capsys, 0)

    lines = _main(rig, capsys, "keep", "--seq", "9")

    assert lines[0].startswith("[중단] 세대 seq 9를 원격에서 찾지 못했습니다")
    assert lines[-1] == "전송용 요약: keep 멈춤 요청 거절; 종료 1"
    assert not rig.store.keys(manifest.KEEP_PREFIX)
    (line,) = _tool_lines(rig, "admin_sync_keep")
    assert (line["out"], line["det"]) == ("fail", {"result": "fail"})


def test_keep_and_unkeep_leave_audit_pieces(
    rig: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """지킴 · 풀기는 정리가 지울 세대를 바꾸는 손 동작이라 도구 조각을 하나씩 남긴다(메모 없음)."""
    _generations(rig, capsys, 1)

    kept = _main(rig, capsys, "keep", "--seq", "1", "--days", "10", "--note", "DEMO_SECRET_NOTE")
    released = _main(rig, capsys, "unkeep", "--seq", "1", "--yes")

    until = kept[-1].rsplit("기한 ", 1)[1]
    (keep_line,) = _tool_lines(rig, "admin_sync_keep")
    assert (keep_line["out"], keep_line["env"], keep_line["verified"]) == ("success", "tool", False)
    assert keep_line["det"] == {"seq_to": 1, "keep_until": until, "result": "ok"}
    assert "DEMO_SECRET_NOTE" not in str(keep_line)
    assert released[0] == "풀림 : seq 1 · 표지 1"
    assert released[-1] == "전송용 요약: unkeep 통과; 종료 0; 풀림 seq 1 · 표지 1"
    (unkeep_line,) = _tool_lines(rig, "admin_sync_unkeep")
    assert (unkeep_line["out"], unkeep_line["det"]) == ("success", {"seq_to": 1, "result": "ok"})
    assert not rig.store.keys(manifest.KEEP_PREFIX)


def test_unkeep_without_yes_skips(rig: SimpleNamespace, capsys: pytest.CaptureFixture[str]) -> None:
    """풀기는 `--yes` 없이 aws 를 부르지 않는다. 표지가 없는 세대를 풀면 할 일이 없어 조각도
    없다."""
    _generations(rig, capsys, 0)
    _main(rig, capsys, "keep", "--head")
    (marker,) = rig.store.keys(manifest.KEEP_PREFIX)
    rig.store.calls.clear()

    skipped = _main(rig, capsys, "unkeep", "--seq", "1")

    assert skipped[0] == "[건너뜀] seq 1 의 지킴 표지를 풀려면 --yes 를 함께 주세요."
    assert skipped[-1] == "전송용 요약: unkeep 통과; 종료 0; 건너뜀 --yes 없음"
    assert rig.store.calls == []
    nothing = _main(rig, capsys, "unkeep", "--seq", "5", "--yes")
    assert nothing[0] == "[건너뜀] seq 5 에는 지킴 표지가 없습니다."
    assert nothing[-1] == "전송용 요약: unkeep 통과; 종료 0; 건너뜀 표지 없음"
    dry = _main(rig, capsys, "--dry-run", "unkeep", "--seq", "1", "--yes")
    assert dry[0] == "[건너뜀] --dry-run 이라 표지를 풀지 않습니다."
    assert rig.store.keys(manifest.KEEP_PREFIX) == [marker]
    assert _tool_lines(rig, "admin_sync_unkeep") == []


def test_keep_dry_run_places_no_marker(
    rig: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--dry-run` 이면 HEAD 든 seq 든 표지를 두지 않는다 — aws 를 부르지 않고 감사 조각도 없다."""
    _generations(rig, capsys, 1)
    rig.store.calls.clear()

    for target in (("--head",), ("--seq", "1")):
        lines = _main(rig, capsys, "--dry-run", "keep", *target)

        assert lines[0] == "[건너뜀] --dry-run 이라 표지를 두지 않습니다.", target
        assert lines[-1] == "전송용 요약: keep 통과; 종료 0; 건너뜀 dry-run", target
    assert rig.store.calls == []
    assert not rig.store.keys(manifest.KEEP_PREFIX)
    assert _tool_lines(rig, "admin_sync_keep") == []


def test_generations_marks_pinned_rows_beyond_limit(
    rig: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """지킨 세대는 줄 끝에 기한을 단다. `--limit` 밖이어도 끝에 따로 찍고, 정리가 붙잡지 않는 지난
    표지는 「지킴 지남」, 포인터 없는 표지는 한 줄이다. 여전히 GET 없이 목록만 읽는다."""
    _generations(rig, capsys, 3)
    _main(rig, capsys, "keep", "--seq", "1")
    expired = manifest.pin_marker_key(3, until=datetime(2026, 11, 1).date(), token="0000abcd")
    orphan = manifest.pin_marker_key(99, until=datetime(2027, 1, 1).date(), token="0000abcd")
    rig.store.objects[expired] = b"{}"
    rig.store.objects[orphan] = b"{}"
    rig.store.calls.clear()

    lines = _main(rig, capsys, "generations", "--limit", "2")

    markers = manifest.read_pin_markers(rig.store.keys(manifest.KEEP_PREFIX))
    (kept,) = [marker for marker in markers if marker.seq == 1]
    assert lines[0].startswith("seq 4 · ") and lines[0].endswith(" · HEAD")
    assert lines[1].startswith("seq 3 · ") and lines[1].endswith(" · 지킴 지남 ~2026-11-01")
    assert lines[2] == "… 2개 더 있습니다(--limit 로 늘립니다)."
    assert lines[3].startswith("seq 1 · ") and lines[3].endswith(f" · 지킴 ~{kept.until}")
    assert lines[4] == "지킴 표지 seq 99 — 세대 없음"
    assert lines[5] == "전송용 요약: generations 통과; 종료 0; 세대 4; HEAD seq 4; 지킴 1"
    assert len(lines) == 6
    assert {op for op, _key in rig.store.operations()} == {"list-objects-v2"}
