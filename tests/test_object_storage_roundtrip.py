# Purpose: 가짜 오브젝트 스토리지로 init·push·pull 왕복 전체를 aws 없이 검증한다.

"""사내에서 처음 누르기 전에 왕복 경로를 여기서 돌려 본다.

`aws s3api` 인자 배열을 해석하는 가짜 실행기를 두어, 실제 `ObjectStorageClient` 와 운영
스크립트의 명령 본체를 그대로 태운다. 단위 테스트가 각 조각을 지켰다면 이 파일은
**조각들이 이어졌을 때** 를 지킨다.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from capa_simulation import settings as app_settings
from capa_simulation.io.object_storage import CommandResult, StorageSettings
from capa_simulation.persistence import snapshot_export, sync_state
from capa_simulation.persistence._sql_helpers import connect

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "sync_object_storage.py"


@dataclass
class FakeStore:
    """`aws s3api` 를 흉내 내는 실행기. 객체를 메모리에 담는다."""

    objects: dict[str, bytes] = field(default_factory=dict)
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self, argv: Sequence[str], env: Mapping[str, str], *, timeout_seconds: float
    ) -> CommandResult:
        self.calls.append(tuple(argv))
        args = list(argv)
        if args[:2] == ["aws", "--version"]:
            return self._ok("aws-cli/2.36.8 (fake)")
        if args[:3] == ["aws", "configure", "get"]:
            return self._ok("path")
        assert args[1] == "s3api", args
        operation = args[2]
        options = self._options(args)
        handler = {
            "list-objects-v2": self._list,
            "head-object": self._head,
            "get-object": self._get,
            "put-object": self._put,
            "delete-object": self._delete,
        }[operation]
        return handler(options, args)

    # ------------------------------------------------------------------ 동작
    def _list(self, options: dict[str, str], args: list[str]) -> CommandResult:
        prefix = options.get("--prefix", "")
        contents = [
            {
                "Key": key,
                "Size": len(payload),
                "ETag": f'"{hashlib.md5(payload, usedforsecurity=False).hexdigest()}"',
                "LastModified": "2026-09-08T09:15:00+00:00",
            }
            for key, payload in sorted(self.objects.items())
            if key.startswith(prefix)
        ]
        return self._ok(json.dumps({"Contents": contents} if contents else {}))

    def _head(self, options: dict[str, str], args: list[str]) -> CommandResult:
        key = options["--key"]
        payload = self.objects.get(key)
        if payload is None:
            return CommandResult(tuple(args), 254, "", "An error occurred (404)", 0.0)
        return self._ok(
            json.dumps(
                {
                    "ContentLength": len(payload),
                    "ETag": f'"{hashlib.md5(payload, usedforsecurity=False).hexdigest()}"',
                    "LastModified": "2026-09-08T09:15:00+00:00",
                }
            )
        )

    def _get(self, options: dict[str, str], args: list[str]) -> CommandResult:
        key = options["--key"]
        payload = self.objects.get(key)
        if payload is None:
            return CommandResult(tuple(args), 254, "", "An error occurred (NoSuchKey)", 0.0)
        Path(args[-1]).write_bytes(payload)
        return self._ok(json.dumps({"ContentLength": len(payload)}))

    def _put(self, options: dict[str, str], args: list[str]) -> CommandResult:
        key = options["--key"]
        if "--if-none-match" in args and key in self.objects:
            return CommandResult(
                tuple(args), 254, "", "An error occurred (PreconditionFailed)", 0.0
            )
        payload = Path(options["--body"]).read_bytes()
        expected = options.get("--content-md5")
        digest = base64.b64encode(hashlib.md5(payload, usedforsecurity=False).digest()).decode()
        if expected is not None and expected != digest:
            return CommandResult(tuple(args), 254, "", "An error occurred (BadDigest)", 0.0)
        self.objects[key] = payload
        return self._ok(
            json.dumps({"ETag": f'"{hashlib.md5(payload, usedforsecurity=False).hexdigest()}"'})
        )

    def _delete(self, options: dict[str, str], args: list[str]) -> CommandResult:
        self.objects.pop(options["--key"], None)
        return self._ok("{}")

    # ------------------------------------------------------------------ 도우미
    @staticmethod
    def _options(args: list[str]) -> dict[str, str]:
        options: dict[str, str] = {}
        for index, token in enumerate(args):
            if token.startswith("--") and index + 1 < len(args):
                options[token] = args[index + 1]
        return options

    @staticmethod
    def _ok(stdout: str) -> CommandResult:
        return CommandResult((), 0, stdout, "", 0.0)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sync_object_storage_rt", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_object_storage_rt"] = module
    spec.loader.exec_module(module)
    return module


def _seed(path: Path, rows: int) -> None:
    with connect(path) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS app_meta")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS app_meta.schema_migration "
            "(version INTEGER PRIMARY KEY, name TEXT, checksum TEXT)"
        )
        connection.execute("INSERT INTO app_meta.schema_migration VALUES (1, '0001', 'x')")
        connection.execute("CREATE TABLE demo AS SELECT range AS id FROM range(?)", [rows])


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """스크립트를 임시 경로와 가짜 스토리지에 붙인다."""
    sync_state.clear_all()
    script = _load_script()
    database = tmp_path / "capa_simulation.duckdb"
    _seed(database, rows=10)

    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(script, "DATASET_PATHS", {"simulation": database})

    store = FakeStore()
    settings = StorageSettings(
        mode="managed",
        endpoint_url="http://fake:9020",
        bucket="Capa_simulation_project",
        profile="demo-org-team",
        region="us-east-1",
        capabilities={},
    )
    monkeypatch.setattr(script, "build_settings", lambda _args: settings)
    monkeypatch.setattr(
        script,
        "build_client",
        lambda _args: script.ObjectStorageClient(
            settings=settings, runner=store, sleep=lambda _s: None
        ),
    )
    return SimpleNamespace(script=script, store=store, database=database, tmp_path=tmp_path)


def _run(harness: SimpleNamespace, *argv: str) -> int:
    status: int = harness.script.main(["--dataset", "simulation", *argv])
    return status


def test_init_uploads_a_snapshot_and_publishes_a_pointer(harness: SimpleNamespace) -> None:
    assert _run(harness, "init", "--note", "최초 이관") == 0

    keys = sorted(harness.store.objects)
    assert any(key.startswith("simulation/snapshots/000000000001__") for key in keys)
    assert any(key.startswith("simulation/heads/") for key in keys)

    state = sync_state.read_state(harness.database)
    assert state is not None
    assert state.base_seq == 1
    assert state.dirty is False


def test_init_is_idempotent(harness: SimpleNamespace) -> None:
    _run(harness, "init")
    before = dict(harness.store.objects)

    assert _run(harness, "init") == 0
    assert harness.store.objects.keys() == before.keys()


def test_push_after_a_local_change_creates_the_next_generation(harness: SimpleNamespace) -> None:
    _run(harness, "init")
    with connect(harness.database) as connection:
        connection.execute("INSERT INTO demo VALUES (999)")
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)
    sync_state.clear_all()

    assert _run(harness, "push", "--note", "왕복 확인") == 0

    snapshots = [k for k in harness.store.objects if k.startswith("simulation/snapshots/")]
    assert len(snapshots) == 2
    state = sync_state.read_state(harness.database)
    assert state is not None and state.base_seq == 2


def test_push_is_skipped_when_nothing_changed(harness: SimpleNamespace) -> None:
    _run(harness, "init")
    before = len(harness.store.objects)

    assert _run(harness, "push") == 0
    assert len(harness.store.objects) == before


def test_pull_restores_the_database_from_the_remote(harness: SimpleNamespace) -> None:
    _run(harness, "init")
    # 로컬을 다른 내용으로 바꾸고 세대를 원격보다 뒤로 돌린다.
    with connect(harness.database) as connection:
        connection.execute("INSERT INTO demo VALUES (777)")
    state = sync_state.read_state(harness.database)
    assert state is not None
    sync_state.write_state(
        harness.database,
        type(state)(**{**state.__dict__, "base_sha256": "0" * 64, "dirty": False}),
    )

    assert _run(harness, "pull") == 0

    with connect(harness.database) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM demo WHERE id = 777").fetchone()
    assert rows is not None and int(rows[0]) == 0


def test_pull_refuses_to_overwrite_local_only_changes(harness: SimpleNamespace) -> None:
    """이 거부가 없으면 이 PC 에만 있는 리비전이 조용히 사라진다."""
    _run(harness, "init")
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)
    sync_state.clear_all()
    state = sync_state.read_state(harness.database)
    assert state is not None
    sync_state.write_state(
        harness.database, type(state)(**{**state.__dict__, "base_sha256": "0" * 64})
    )

    assert _run(harness, "pull") == 1


def test_status_runs_against_an_empty_remote(harness: SimpleNamespace) -> None:
    assert _run(harness, "status") == 0


def test_doctor_reports_without_touching_the_databases(harness: SimpleNamespace) -> None:
    assert _run(harness, "doctor") == 0
    assert all("s3api" not in call or "put-object" not in call for call in harness.store.calls)


def test_dry_run_uploads_nothing(harness: SimpleNamespace) -> None:
    assert harness.script.main(["--dataset", "simulation", "--dry-run", "init"]) == 0

    assert harness.store.objects == {}


def test_every_call_carries_the_profile(harness: SimpleNamespace) -> None:
    """왕복 전체에서 한 번이라도 빠지면 다른 네임스페이스를 건드린다."""
    _run(harness, "init")

    s3api_calls = [call for call in harness.store.calls if len(call) > 1 and call[1] == "s3api"]
    assert s3api_calls
    for call in s3api_calls:
        assert "--profile" in call
        assert call[call.index("--profile") + 1] == "demo-org-team"


def test_uploaded_snapshot_opens_as_a_valid_database(harness: SimpleNamespace) -> None:
    """올라간 바이트가 실제로 열리는 DuckDB 인지 확인한다."""
    _run(harness, "init")
    key = next(k for k in harness.store.objects if k.startswith("simulation/snapshots/"))
    restored = harness.tmp_path / "restored.duckdb"
    restored.write_bytes(harness.store.objects[key])

    with connect(restored) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM demo").fetchone()

    assert rows is not None and int(rows[0]) == 10


def test_pointer_json_records_the_parent_chain(harness: SimpleNamespace) -> None:
    _run(harness, "init")
    with connect(harness.database) as connection:
        connection.execute("INSERT INTO demo VALUES (5)")
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)
    sync_state.clear_all()
    _run(harness, "push")

    pointers = sorted(k for k in harness.store.objects if k.startswith("simulation/heads/"))
    newest = json.loads(harness.store.objects[pointers[0]].decode("utf-8"))

    assert newest["seq"] == 2
    assert newest["parent_seq"] == 1
    assert len(newest["parent_sha256"]) == 64
    assert newest["created_at_utc"].endswith("Z")
    assert datetime.now(timezone.utc).year >= 2026


def test_resolve_promotes_an_unpublished_snapshot_with_a_usable_size(
    harness: SimpleNamespace,
) -> None:
    """승격한 포인터의 크기가 0 이면 나중에 pull 이 그 세대를 거부한다."""
    _run(harness, "init")
    key = next(k for k in harness.store.objects if k.startswith("simulation/snapshots/"))
    state = sync_state.read_state(harness.database)
    assert state is not None
    sync_state.write_state(
        harness.database,
        type(state)(
            **{
                **state.__dict__,
                "unpublished_snapshot_key": key,
                "unpublished_sha256": state.base_sha256,
                "unpublished_reason": "테스트",
            }
        ),
    )

    assert _run(harness, "resolve", "--keep", "mine") == 0

    pointers = sorted(k for k in harness.store.objects if k.startswith("simulation/heads/"))
    promoted = json.loads(harness.store.objects[pointers[0]].decode("utf-8"))
    assert promoted["seq"] == 2
    assert promoted["snapshot_key"] == key
    assert promoted["size_bytes"] > 0


def test_resolve_keep_remote_drops_the_local_claim(harness: SimpleNamespace) -> None:
    _run(harness, "init")
    state = sync_state.read_state(harness.database)
    assert state is not None
    sync_state.write_state(
        harness.database,
        type(state)(
            **{
                **state.__dict__,
                "unpublished_snapshot_key": "simulation/snapshots/whatever",
                "unpublished_reason": "테스트",
            }
        ),
    )

    assert _run(harness, "resolve", "--keep", "remote") == 0

    after = sync_state.read_state(harness.database)
    assert after is not None and after.unpublished_snapshot_key is None


def test_a_lost_race_records_the_orphan_snapshot_key(harness: SimpleNamespace) -> None:
    """경합에서 지면 복구 수단은 그 스냅샷 키뿐이다. 기록이 빠지면 복구할 수 없다."""
    _run(harness, "init")
    with connect(harness.database) as connection:
        connection.execute("INSERT INTO demo VALUES (321)")
    sync_state.enable({harness.database: "simulation"})
    sync_state.mark_dirty(harness.database)

    original_head = harness.script.read_head

    def head_moves_after_upload(client, dataset):  # type: ignore[no-untyped-def]
        pointer = original_head(client, dataset)
        if pointer is not None and any(
            call[2] == "put-object" and "simulation/snapshots/000000000002" in " ".join(call)
            for call in harness.store.calls
        ):
            # 업로드 뒤 다시 물었을 때 남이 앞선 것처럼 보이게 한다.
            return type(pointer)(**{**pointer.__dict__, "sha256": "f" * 64})
        return pointer

    harness.script.read_head = head_moves_after_upload
    try:
        assert _run(harness, "push") == 1
    finally:
        harness.script.read_head = original_head

    state = sync_state.read_state(harness.database)
    assert state is not None
    assert state.unpublished_snapshot_key is not None
    # 스냅샷 자체는 원격에 남아 있어야 한다 — 유실 불가의 근거다.
    assert state.unpublished_snapshot_key in harness.store.objects


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
        ("aws", "s3api", "put-object", "--bucket", "Capa_simulation_project"),
        254,
        "",
        "An error occurred (AccessDenied)",
        0.0,
    )

    message = boundary.explain_failure(result)

    assert "실행한 명령" in message
    assert "s3api put-object" in message
    assert "Capa_simulation_project" in message
