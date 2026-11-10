# Purpose: 가짜 오브젝트 스토리지로 init·push·pull 왕복 전체를 aws 없이 검증한다.

"""사내에서 처음 누르기 전에 왕복 경로를 여기서 돌려 본다.

`aws s3api` 인자 배열을 해석하는 가짜 실행기를 두어, 실제 `ObjectStorageClient` 와 운영
스크립트의 명령 본체를 그대로 태운다. 단위 테스트가 각 조각을 지켰다면 이 파일은
**조각들이 이어졌을 때** 를 지킨다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from object_store_fakes import (
    Failure,
    FakeStore,
    add_row,
    fake_client,
    fake_settings,
    row_count,
    seed_pair,
)

from capa_simulation import settings as app_settings
from capa_simulation.io.object_storage import CommandResult
from capa_simulation.persistence import snapshot_export, sync_state
from capa_simulation.services import object_storage_manifest as manifest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "sync_object_storage.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sync_object_storage_rt", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_object_storage_rt"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """스크립트를 임시 경로와 가짜 스토리지에 붙인다."""
    sync_state.clear_all()
    script = _load_script()
    paths = seed_pair(tmp_path)

    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(script, "DATASET_PATHS", dict(paths.databases))

    store = FakeStore()
    monkeypatch.setattr(script, "build_settings", lambda _args: fake_settings())
    monkeypatch.setattr(script, "build_client", lambda _args: fake_client(store))
    return SimpleNamespace(
        script=script,
        store=store,
        paths=paths,
        database=paths.databases["simulation"],
        equipment=paths.databases["equipment"],
        tmp_path=tmp_path,
    )


def _run(harness: SimpleNamespace, *argv: str) -> int:
    status: int = harness.script.main(list(argv))
    return status


def _init(harness: SimpleNamespace) -> None:
    """개발 버킷 시험처럼 이 PC 를 쓰는 쪽으로 남겨 둔다."""
    assert _run(harness, "init", "--keep-writer") == 0


def test_init_uploads_both_snapshots_and_publishes_one_pointer(harness: SimpleNamespace) -> None:
    assert _run(harness, "init") == 0

    assert len(harness.store.keys("simulation/snapshots/")) == 1
    assert len(harness.store.keys("equipment/snapshots/")) == 1
    assert len(harness.store.pointer_keys()) == 1
    assert harness.store.head_pointer()["origin"] == "init"


def test_init_is_idempotent(harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]) -> None:
    _init(harness)
    before = dict(harness.store.objects)
    capsys.readouterr()

    assert _run(harness, "init") == 0

    assert harness.store.objects == before
    assert "[건너뜀] 원격에 이미 seq 1이 있습니다." in capsys.readouterr().out


def test_init_hands_the_pc_over_unless_told_to_keep_writing(harness: SimpleNamespace) -> None:
    """이관 뒤 그 PC 는 쓰는 쪽이 아니다. 개발 버킷 시험만 `--keep-writer` 로 남긴다."""
    assert _run(harness, "init") == 0
    state = sync_state.read_generation(harness.paths.generation)
    assert state.handed_over_utc is not None

    add_row(harness.database)
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)

    assert _run(harness, "push") == 1
    assert len(harness.store.pointer_keys()) == 1

    assert _run(harness, "--override-writer", "push") == 0
    assert len(harness.store.pointer_keys()) == 2


def test_push_after_a_local_change_creates_the_next_generation(harness: SimpleNamespace) -> None:
    _init(harness)
    add_row(harness.database)
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)

    assert _run(harness, "push", "--note", "두 번째") == 0

    head = harness.store.head_pointer()
    assert head["seq"] == 2
    assert head["origin"] == "manual"
    assert head["note"] == "두 번째"


def test_push_is_skipped_when_nothing_changed(harness: SimpleNamespace) -> None:
    _init(harness)
    before = len(harness.store.objects)

    assert _run(harness, "push") == 0

    assert len(harness.store.objects) == before


def test_a_pc_refuses_to_push_once_the_app_has_taken_over(harness: SimpleNamespace) -> None:
    """운영 앱의 포인터(`boot` · `app`)가 HEAD 면, 넘긴 표지가 없어도 사내 PC 는 쓰지 못한다."""
    _init(harness)
    outcome = harness.script.engine.boot_pull(fake_client(harness.store), harness.paths)
    assert outcome.ok
    add_row(harness.database)
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)

    assert _run(harness, "push") == 1
    assert _run(harness, "--override-writer", "push") == 0


def test_pull_restores_both_databases_from_the_remote(harness: SimpleNamespace) -> None:
    _init(harness)
    before = row_count(harness.equipment)
    harness.database.unlink()
    harness.equipment.unlink()
    sync_state.sidecar_path(harness.database).unlink()
    sync_state.sidecar_path(harness.equipment).unlink()

    assert _run(harness, "pull") == 0

    assert row_count(harness.database) == 10
    assert row_count(harness.equipment) == before


def test_pull_refuses_to_overwrite_local_only_changes(harness: SimpleNamespace) -> None:
    _init(harness)
    add_row(harness.database)
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)

    assert _run(harness, "pull") == 1

    assert row_count(harness.database) == 11


def test_status_runs_against_an_empty_remote(harness: SimpleNamespace) -> None:
    assert _run(harness, "status") == 0


def test_status_filters_the_display_by_dataset(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(harness, "--dataset", "equipment", "status") == 0

    printed = capsys.readouterr().out
    assert "가용설비 변경" in printed
    assert "시뮬레이션 변경" not in printed


def test_doctor_reports_without_touching_the_databases(harness: SimpleNamespace) -> None:
    assert _run(harness, "doctor") == 0


def test_doctor_no_longer_warns_about_plain_http(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """폐쇄망 http 9020 은 결정됐다(https 는 서버 TLS 문제로 쓰지 않는다)."""
    assert _run(harness, "doctor") == 0

    assert "평문" not in capsys.readouterr().out


def test_dry_run_uploads_nothing(harness: SimpleNamespace) -> None:
    assert _run(harness, "--dry-run", "init") == 0

    assert harness.store.objects == {}


def test_dry_run_push_only_says_a_pointer_is_left(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """앞 회차가 남긴 포인터를 `--dry-run` 이 내면 안 된다. 있다는 사실만 찍고 끝난다."""
    _init(harness)
    add_row(harness.database)
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)
    harness.store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=False))
    assert _run(harness, "push") == 1
    pending = sync_state.read_generation(harness.paths.generation).pending
    assert pending is not None
    capsys.readouterr()

    assert _run(harness, "--dry-run", "push") == 0

    out = capsys.readouterr().out
    assert pending.pointer_key in out
    assert "마무리했습니다" not in out
    assert "예정 seq" not in out
    assert len(harness.store.pointer_keys()) == 1
    assert sync_state.read_generation(harness.paths.generation).pending == pending


def test_every_call_carries_the_profile(harness: SimpleNamespace) -> None:
    """프로필이 빠지면 다른 네임스페이스를 본다. 왕복 전체에서 빠진 호출이 없어야 한다."""
    _init(harness)

    s3_calls = [call for call in harness.store.calls if call[1] == "s3api"]

    assert s3_calls
    for call in s3_calls:
        assert call[call.index("--profile") + 1] == "demo-org-team"


def test_uploaded_snapshot_opens_as_a_valid_database(harness: SimpleNamespace) -> None:
    _init(harness)
    key = harness.store.keys("simulation/snapshots/")[0]
    local = harness.tmp_path / "from-remote.duckdb"
    local.write_bytes(harness.store.objects[key])

    assert row_count(local) == 10


def test_pointer_json_records_the_parent_chain(harness: SimpleNamespace) -> None:
    _init(harness)
    first = harness.store.pointer_keys()[0]
    add_row(harness.database)
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)
    _run(harness, "push")

    newest = harness.store.head_pointer()

    assert newest["seq"] == 2
    assert newest["parent_seq"] == 1
    assert newest["parent_pointer_key"] == first
    assert newest["created_at_utc"].endswith("Z")
    assert datetime.now(timezone.utc).year >= 2026


def _park_a_generation(harness: SimpleNamespace, reason: str = "moved") -> None:
    """올렸는데 게시하지 못한 세대를 상태 파일에 남긴다."""
    state = sync_state.read_generation(harness.paths.generation)
    assert state.base_pointer_json is not None
    sync_state.write_generation(
        harness.paths.generation,
        type(state)(
            **{
                **state.__dict__,
                "unpublished": sync_state.UnpublishedGeneration(
                    pointer_json=state.base_pointer_json, reason=reason, observed={}
                ),
            }
        ),
    )


def test_resolve_promotes_an_unpublished_generation_with_usable_members(
    harness: SimpleNamespace,
) -> None:
    """승격한 포인터의 멤버가 그대로여야 나중에 받기가 그 세대를 받는다."""
    _init(harness)
    _park_a_generation(harness)

    assert _run(harness, "resolve", "--keep", "mine") == 0

    promoted = harness.store.head_pointer()
    assert promoted["seq"] == 2
    assert promoted["members"]["simulation"]["size_bytes"] > 0
    assert sync_state.read_generation(harness.paths.generation).unpublished is None


def test_resolve_keep_remote_drops_the_local_claim(harness: SimpleNamespace) -> None:
    _init(harness)
    _park_a_generation(harness)

    assert _run(harness, "resolve", "--keep", "remote") == 0

    assert sync_state.read_generation(harness.paths.generation).unpublished is None
    assert len(harness.store.pointer_keys()) == 1


def test_resolve_without_anything_to_do_says_so(harness: SimpleNamespace) -> None:
    _init(harness)

    assert _run(harness, "resolve", "--keep", "mine") == 0


def test_adopt_local_marks_both_databases_for_the_next_push(harness: SimpleNamespace) -> None:
    """세대를 모르는 DB 는 HEAD 를 덮지 못한다. 사람이 기준을 정하면 그때 올라간다."""
    _init(harness)
    sync_state.write_generation(harness.paths.generation, sync_state.GenerationState())
    add_row(harness.database)
    sync_state.enable(harness.paths.registry)
    sync_state.mark_dirty(harness.database)

    assert _run(harness, "push") == 1
    assert _run(harness, "adopt", "--source", "local") == 0
    assert _run(harness, "push") == 0

    assert harness.store.head_pointer()["seq"] == 2


def test_a_failed_snapshot_upload_publishes_no_pointer(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-04-12 에 만든 스냅샷 키에는 "412" 가 든다. 연결 오류 URL 의 그 숫자를 선점 실패로 읽으면
    업로드가 빠진 채 포인터가 게시되고, 다른 PC 의 pull 이 없는 스냅샷을 찾다 멈춘다."""
    monkeypatch.setattr(snapshot_export, "utc_timestamp", lambda: "2026-04-12T10:15:00Z")
    store_run = harness.store.run

    def unreachable_for_snapshots(
        argv: Sequence[str], env: Mapping[str, str], *, timeout_seconds: float
    ) -> CommandResult:
        args = list(argv)
        key = args[args.index("--key") + 1] if "--key" in args else ""
        if args[2:3] == ["put-object"] and "/snapshots/" in key:
            harness.store.calls.append(tuple(argv))
            url = f"http://fake:9020/Demo_bucket/{key}"
            return CommandResult(
                tuple(argv), 255, "", f'\nCould not connect to the endpoint URL: "{url}"\n', 0.0
            )
        result: CommandResult = store_run(argv, env, timeout_seconds=timeout_seconds)
        return result

    monkeypatch.setattr(harness.store, "run", unreachable_for_snapshots)

    assert _run(harness, "init") == 1

    snapshot_puts = [
        call
        for call in harness.store.calls
        if call[2] == "put-object" and "20260412T" in " ".join(call)
    ]
    assert len(snapshot_puts) == 3
    assert harness.store.pointer_keys() == []
    assert sync_state.read_generation(harness.paths.generation).base_seq is None


def test_a_locked_database_is_explained_in_korean(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """앱을 켜 둔 채 돌리면 나올 첫 실패다. `duckdb.Error` 는 RuntimeError 가 아니라서
    잡지 않으면 원문 트레이스백이 한글 깨진 채로 나온다."""
    import duckdb

    def locked(*_args: object, **_kwargs: object) -> None:
        raise duckdb.IOException("Could not set lock on file")

    # 손으로 되돌리면 안 된다. `harness.script.snapshot_export` 는 이 모듈과 같은 객체라
    # 되돌릴 때 이미 갈아끼운 값을 다시 넣게 되고, 뒤따르는 테스트가 전부 깨진다.
    monkeypatch.setattr(snapshot_export, "export_snapshot", locked)

    assert _run(harness, "init") == 1


def test_failure_messages_name_the_command_that_failed(harness: SimpleNamespace) -> None:
    """사내에서 원격으로 진단할 때 실행한 명령 한 줄이 있고 없고가 크다."""
    from capa_simulation.io import object_storage as boundary

    result = boundary.CommandResult(
        ("aws", "s3api", "put-object", "--bucket", "Demo_bucket"),
        254,
        "",
        "An error occurred (AccessDenied)",
        0.0,
    )

    message = boundary.explain_failure(result)

    assert "실행한 명령" in message
    assert "s3api put-object" in message
    assert "Demo_bucket" in message


def test_fetch_copy_writes_two_databases_and_the_generation_outside_data(
    harness: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """사내 PC 가 런북 8장을 돌릴 사본. `data/` 를 건드리지 않아 앱이 떠 있어도 된다."""
    _init(harness)
    folder = tmp_path_factory.mktemp("copy") / "fetched"

    assert _run(harness, "fetch-copy", "--to", str(folder)) == 0

    assert row_count(folder / harness.database.name) == 10
    assert row_count(folder / harness.equipment.name) == 10
    assert json.loads((folder / "generation.json").read_text(encoding="utf-8"))["seq"] == 1
    assert not (folder / ".fetch").exists()


def test_fetch_copy_refuses_the_operating_place(harness: SimpleNamespace) -> None:
    _init(harness)

    assert _run(harness, "fetch-copy", "--to", str(harness.tmp_path)) == 1


def test_fetch_copy_can_take_an_older_generation(
    harness: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory
) -> None:
    _init(harness)
    add_row(harness.database)
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)
    assert _run(harness, "push") == 0
    folder = tmp_path_factory.mktemp("older")

    assert _run(harness, "fetch-copy", "--to", str(folder), "--seq", "1") == 0

    assert row_count(folder / harness.database.name) == 10


def test_rollback_needs_yes_and_then_moves_the_head_forward(harness: SimpleNamespace) -> None:
    """지우지 않고 앞으로만 간다. 멤버는 그 세대 그대로다."""
    _init(harness)
    first = harness.store.head_pointer()
    add_row(harness.database)
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)
    assert _run(harness, "push") == 0

    assert _run(harness, "rollback", "--to", "1") == 0
    assert harness.store.head_pointer()["seq"] == 2

    assert _run(harness, "rollback", "--to", "1", "--yes") == 0
    head = harness.store.head_pointer()
    assert head["seq"] == 3
    assert head["origin"] == "rollback"
    assert head["members"] == first["members"]


def _push_a_save(harness: SimpleNamespace) -> None:
    add_row(harness.database)
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)
    assert _run(harness, "push") == 0


def test_a_pc_without_a_mark_refuses_to_push_after_a_rollback(harness: SimpleNamespace) -> None:
    """되돌린 뒤 다음 시작의 펜스가 서기 전 틈 — 표지 없는 PC 의 DB 가 HEAD 가 되면 안 된다."""
    _init(harness)
    harness.script.engine.boot_pull(fake_client(harness.store), harness.paths)
    assert _run(harness, "rollback", "--to", "1", "--yes") == 0

    assert _run(harness, "adopt", "--source", "local") == 1
    assert _run(harness, "--override-writer", "adopt", "--source", "local") == 0
    assert _run(harness, "push") == 1


def test_generations_show_member_numbers_without_reading_pointers(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """펜스는 같은 멤버로 쌓인다. 바로 앞 세대가 깨진 멤버를 그대로 가리킬 수 있어 번호로 고른다."""
    _init(harness)
    _push_a_save(harness)
    harness.script.engine.boot_pull(fake_client(harness.store), harness.paths)
    harness.store.calls.clear()
    capsys.readouterr()

    assert _run(harness, "generations") == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("seq 3 · 시뮬레이션 2 · 가용설비 1")
    assert "HEAD" in lines[0]
    assert lines[1].startswith("seq 2 · 시뮬레이션 2 · 가용설비 1")
    assert lines[2].startswith("seq 1 · 시뮬레이션 1 · 가용설비 1")
    assert not any(operation == "get-object" for operation, _key in harness.store.operations())


def test_generations_cuts_a_long_list(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(harness)
    for _ in range(3):
        _push_a_save(harness)
    capsys.readouterr()

    assert _run(harness, "generations", "--limit", "2") == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3
    assert "2" in lines[2] and "더" in lines[2]


def test_generations_on_an_empty_remote_says_so(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(harness, "generations") == 0

    assert "비어 있음" in capsys.readouterr().out


def test_status_on_a_pc_that_handed_over_points_at_a_copy_not_resolve(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """이관 뒤에는 시작마다 세대가 늘어 늘 이 꼴이다. `resolve` 는 할 일이 없다."""
    assert _run(harness, "init") == 0
    state = sync_state.read_generation(harness.paths.generation)
    harness.script.engine.boot_pull(fake_client(harness.store), harness.paths)
    sync_state.write_generation(harness.paths.generation, state)
    capsys.readouterr()

    assert _run(harness, "status") == 0

    printed = capsys.readouterr().out
    assert "fetch-copy" in printed
    assert "resolve" not in printed


def test_resolve_refuses_a_generation_whose_snapshot_is_gone(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(harness)
    _park_a_generation(harness)
    for key in harness.store.keys("simulation/snapshots/"):
        del harness.store.objects[key]

    assert _run(harness, "resolve", "--keep", "mine") == 1

    assert "[중단]" in capsys.readouterr().out
    assert sync_state.read_generation(harness.paths.generation).unpublished is not None
    assert len(harness.store.pointer_keys()) == 1


def _move_the_head_with_a_newer_equipment(harness: SimpleNamespace) -> None:
    """남이 설비 DB 를 올려 HEAD 를 옮긴다."""
    head = harness.script.engine.read_pointer(
        fake_client(harness.store), harness.store.pointer_keys()[0]
    )
    body = b"newer equipment"
    member = manifest.Member(
        seq=head.seq + 1,
        snapshot_key=manifest.snapshot_key(
            "equipment", head.seq + 1, created_at_utc="2026-11-07T00:00:00Z", sha256="ab" * 32
        ),
        sha256="ab" * 32,
        md5_base64="",
        size_bytes=len(body),
        source_db_bytes=len(body),
        migration_version=1,
    )
    harness.store.objects[member.snapshot_key] = body
    pointer = manifest.next_pointer(
        head,
        members={**head.members, "equipment": member},
        origin="app",
        token="abcdef02",
        app_version="demo",
        author="demo@other",
        created_at_utc="2026-11-07T00:00:00Z",
        note="",
    )
    harness.store.objects[pointer.pointer_key] = manifest.pointer_to_json(pointer).encode("utf-8")


def _another_pod_republishes(harness: SimpleNamespace) -> None:
    """남이 같은 멤버로 세대를 낸다 — 받으면 첫 세대 파일이 그대로 돌아온다."""
    head = harness.script.engine.read_pointer(
        fake_client(harness.store), harness.store.pointer_keys()[0]
    )
    pointer = manifest.next_pointer(
        head,
        members=dict(head.members),
        origin="app",
        token="abcdef03",
        app_version="demo",
        author="demo@other",
        created_at_utc="2026-11-07T00:00:00Z",
        note="",
    )
    harness.store.objects[pointer.pointer_key] = manifest.pointer_to_json(pointer).encode("utf-8")


def _park_behind(harness: SimpleNamespace, move_the_head: Callable[[], None]) -> None:
    """이 PC 의 저장을 올리는 도중 HEAD 가 움직여 세대가 미게시로 남는다."""
    _init(harness)
    add_row(harness.database)
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)
    moved: list[str] = []

    def move_after_snapshot(operation: str, key: str) -> None:
        uploaded = harness.store.puts("simulation/snapshots/000000000002")
        if operation == "list-objects-v2" and uploaded and not moved:
            moved.append(key)
            move_the_head()

    harness.store.before = move_after_snapshot
    assert _run(harness, "push") == 1
    harness.store.before = None


def test_resolve_says_to_pull_when_a_member_came_from_the_remote(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """새 HEAD 의 멤버 하나가 이 PC 의 파일이 아니다. 말하지 않으면 옛 파일로 계속 일한다."""
    _park_behind(harness, lambda: _move_the_head_with_a_newer_equipment(harness))
    capsys.readouterr()

    assert _run(harness, "--override-writer", "resolve", "--keep", "mine") == 0

    assert "pull" in capsys.readouterr().out


def test_resolve_keep_remote_leads_to_a_pull_and_keeps_the_old_file(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """버리기로 했으면 안내대로 `pull` 이 받아야 한다. 표시가 남으면 `pull` · `push` · `resolve` 가
    서로를 가리키는 막다른 길이다. 옛 파일은 지우지 않고 백업으로 물러난다."""
    _park_behind(harness, lambda: _another_pod_republishes(harness))
    rows = row_count(harness.database)
    capsys.readouterr()

    assert _run(harness, "resolve", "--keep", "remote") == 0
    assert "pull" in capsys.readouterr().out

    assert _run(harness, "pull") == 0

    out = capsys.readouterr().out
    assert "이전 파일 백업" in out
    state = sync_state.read_generation(harness.paths.generation)
    assert state.base_seq == 2 and state.unpublished is None
    assert not sync_state.treat_as_dirty(harness.database)
    assert row_count(harness.database) == rows - 1
    backups = [
        path
        for path in snapshot_export.backup_dir().iterdir()
        if path.name.startswith(harness.database.name)
    ]
    assert [row_count(path) for path in backups] == [rows]


def test_a_dry_run_resolve_keep_remote_drops_nothing(harness: SimpleNamespace) -> None:
    _park_behind(harness, lambda: _another_pod_republishes(harness))

    assert _run(harness, "--dry-run", "resolve", "--keep", "remote") == 0

    assert sync_state.read_generation(harness.paths.generation).unpublished is not None
    assert sync_state.treat_as_dirty(harness.database)


def test_resolve_keep_remote_waits_for_the_app_to_stop(
    harness: SimpleNamespace,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """표시는 앱이 쓰는 파일이다. 떠 있는 앱의 표시를 지우면 그 저장이 올라가지 않는다."""
    _park_behind(harness, lambda: _another_pod_republishes(harness))
    monkeypatch.setattr(sync_state, "live_instance", lambda _path: "demo-app")
    capsys.readouterr()

    assert _run(harness, "resolve", "--keep", "remote") == 1

    assert "앱이 이 PC 에서 실행 중" in capsys.readouterr().out
    assert sync_state.read_generation(harness.paths.generation).unpublished is not None
    assert sync_state.treat_as_dirty(harness.database)


def test_prune_lists_candidates_and_deletes_only_with_yes(harness: SimpleNamespace) -> None:
    _init(harness)
    for value in range(7):
        add_row(harness.database, value)
        sync_state.enable({harness.database: "simulation"})
        sync_state.mark_dirty(harness.database)
        assert _run(harness, "push") == 0
    oldest = harness.store.pointer_keys()[-1]
    harness.store.modified[oldest] = "2026-10-01T00:00:00+00:00"
    for key in harness.store.keys("simulation/snapshots/000000000001"):
        harness.store.modified[key] = "2026-10-01T00:00:00+00:00"

    assert _run(harness, "prune", "--keep-days", "1") == 0
    assert oldest in harness.store.objects

    assert _run(harness, "prune", "--keep-days", "1", "--yes") == 0
    assert oldest not in harness.store.objects
    # 설비 스냅샷은 세대 1 것이 이어 적혀 남은 세대가 아직 가리킨다.
    assert harness.store.keys("equipment/snapshots/")


def test_a_rollback_during_the_prune_is_reported_as_a_stop(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """손으로 돌린 정리가 HEAD 가 움직여 멈추면 다 지운 것처럼 끝내지 않는다."""
    _init(harness)
    for value in range(7):
        add_row(harness.database, value)
        sync_state.enable({harness.database: "simulation"})
        sync_state.mark_dirty(harness.database)
        assert _run(harness, "push") == 0
    head = harness.store.pointer_keys()[0]
    for key in harness.store.keys():
        harness.store.modified[key] = "2026-10-01T00:00:00+00:00"
    harness.store.modified[head] = harness.store.now
    moved: list[str] = []

    def move_on_first_delete(operation: str, key: str) -> None:
        if operation == "delete-object" and not moved:
            moved.append(key)
            _another_pod_republishes(harness)

    harness.store.before = move_on_first_delete
    capsys.readouterr()

    assert _run(harness, "prune", "--keep-days", "1", "--yes") == 1

    out = capsys.readouterr().out
    assert "1개를 지웠습니다" in out
    assert "[중단]" in out


def test_a_rollback_with_a_lost_member_tells_the_head_went_out(
    harness: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(harness)
    add_row(harness.database)
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)
    assert _run(harness, "push") == 0
    member = harness.store.keys("simulation/snapshots/000000000001")[0]

    def lose_the_member(operation: str, key: str) -> None:
        if operation == "put-object" and key.startswith(manifest.HEAD_PREFIX):
            harness.store.objects.pop(member, None)

    harness.store.before = lose_the_member
    capsys.readouterr()

    assert _run(harness, "rollback", "--to", "1", "--yes") == 1

    assert "다른 세대로 다시 rollback" in capsys.readouterr().out


def test_boot_pull_prints_a_line_without_values(
    harness: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """시작 스크립트가 읽는 한 줄. 주소 · 버킷 · 키가 실리지 않는다."""
    _init(harness)
    capsys.readouterr()
    monkeypatch.setenv("CAPA_S3_BUCKET", "Demo_ops")

    assert _run(harness, "boot-pull") == 0

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["kind"] is None
    assert line["action"] == "kept"
    assert line["seq"] == 2


def test_boot_pull_without_the_bucket_variable_stays(
    harness: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """없을 때 config 기본(개발 버킷)으로 가면 운영 저장이 개발 버킷에 간다."""
    monkeypatch.delenv("CAPA_S3_BUCKET", raising=False)

    assert _run(harness, "boot-pull") == 1

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["kind"] == "config"
    assert harness.store.calls == []


def test_boot_pull_failure_leaves_no_boot_record(
    harness: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """원격이 비었으면(이관 전) 앱을 띄우지 않는다. 기록이 없어야 일꾼도 서지 않는다."""
    monkeypatch.setenv("CAPA_S3_BUCKET", "Demo_ops")

    assert _run(harness, "boot-pull") == 1

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["kind"] == "remote_empty"
    from capa_simulation import sync_boot

    assert sync_boot.read_boot_record() is None


def test_boot_pull_fails_when_the_boot_record_cannot_be_written(
    harness: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """기록을 못 쓰면 일꾼이 안 선다. 그 앱의 저장은 어디에도 안 올라가니 띄우지 않는다."""
    _init(harness)
    monkeypatch.setenv("CAPA_S3_BUCKET", "Demo_ops")

    def refuse(_record: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(harness.script.sync_boot, "write_boot_record", refuse)

    assert _run(harness, "boot-pull") == 1

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["kind"] == "other"
