# Purpose: `aws s3api` 를 메모리로 흉내 내는 실행기와 두 DB 합성 묶음을 동기화 시험에 나눠 준다.

"""동기화 시험의 공용 부품.

`FakeStore` 는 `ObjectStorageClient` 가 조립한 인자 배열을 그대로 해석한다. 실제 클라이언트 · 엔진 ·
스크립트 본체를 태우는 것이 목적이고, `aws` 없이 돈다. 실패 흉내는 `Failure` 하나다 — 특히
`stored=True` 는 **저장은 하고 답만 끊는** 꼴이다. 저장 전 실패만 흉내 내면 「포인터는 들어갔는데
실패로 끝남」 을 시험하지 못한다.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from capa_simulation.io.object_storage import (
    CommandResult,
    ObjectStorageClient,
    StorageSettings,
)
from capa_simulation.object_sync_engine import SyncPaths
from capa_simulation.persistence._sql_helpers import connect
from capa_simulation.services.object_storage_manifest import HEAD_PREFIX, DatasetName

TIMEOUT_TEXT = "Read timeout on endpoint URL: http://fake:9020/\n"
CONNECT_TEXT = 'Could not connect to the endpoint URL: "http://fake:9020/"\n'


@dataclass
class Failure:
    """이 동작 · 키 조각이 맞는 호출을 실패시킨다. `times` 는 남은 횟수다(재시도까지 센다)."""

    operation: str
    key_part: str = ""
    stored: bool = False
    times: int = 3
    stderr: str = TIMEOUT_TEXT
    returncode: int = 255


@dataclass
class FakeStore:
    """`aws s3api` 를 흉내 내는 실행기. 객체를 메모리에 담는다."""

    objects: dict[str, bytes] = field(default_factory=dict)
    modified: dict[str, str] = field(default_factory=dict)
    calls: list[tuple[str, ...]] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)
    # 동작 앞에 부른다. 차례 사이에 남의 게시를 끼워 넣는 자리다.
    before: Callable[[str, str], None] | None = None
    now: str = "2026-11-07T00:00:00+00:00"

    def run(
        self, argv: Sequence[str], env: Mapping[str, str], *, timeout_seconds: float
    ) -> CommandResult:
        self.calls.append(tuple(argv))
        args = list(argv)
        if args[:2] == ["aws", "--version"]:
            return self._ok("aws-cli/1.46.3 (fake)")
        if args[:3] == ["aws", "configure", "get"]:
            return self._ok("path")
        assert args[1] == "s3api", args
        operation = args[2]
        options = self._options(args)
        key = options.get("--key") or options.get("--prefix", "")
        if self.before is not None:
            self.before(operation, key)
        handler = {
            "list-objects-v2": self._list,
            "head-object": self._head,
            "get-object": self._get,
            "put-object": self._put,
            "delete-object": self._delete,
        }[operation]
        for failure in self.failures:
            if failure.times > 0 and failure.operation == operation and failure.key_part in key:
                failure.times -= 1
                if failure.stored:
                    handler(options, args)
                return CommandResult(tuple(args), failure.returncode, "", failure.stderr, 0.0)
        return handler(options, args)

    # ------------------------------------------------------------------ 볼 것
    def keys(self, prefix: str = "") -> list[str]:
        return sorted(key for key in self.objects if key.startswith(prefix))

    def pointer_keys(self) -> list[str]:
        return self.keys(HEAD_PREFIX)

    def puts(self, part: str = "") -> list[str]:
        return [
            self._options(list(call))["--key"]
            for call in self.calls
            if call[2:3] == ("put-object",) and part in self._options(list(call))["--key"]
        ]

    def operations(self) -> list[tuple[str, str]]:
        found = []
        for call in self.calls:
            if call[1] != "s3api":
                continue
            options = self._options(list(call))
            found.append((call[2], options.get("--key") or options.get("--prefix", "")))
        return found

    def head_pointer(self) -> dict[str, object]:
        return dict(json.loads(self.objects[self.pointer_keys()[0]].decode("utf-8")))

    # ------------------------------------------------------------------ 동작
    def _list(self, options: dict[str, str], args: list[str]) -> CommandResult:
        prefix = options.get("--prefix", "")
        names = self.keys(prefix)
        token = options.get("--continuation-token")
        start = int(token) if token else 0
        size = int(options.get("--max-keys", "1000"))
        page = names[start : start + size]
        contents = [
            {
                "Key": key,
                "Size": len(self.objects[key]),
                "ETag": f'"{hashlib.md5(self.objects[key], usedforsecurity=False).hexdigest()}"',
                "LastModified": self.modified.get(key, self.now),
            }
            for key in page
        ]
        payload: dict[str, object] = {"Contents": contents} if contents else {}
        if start + size < len(names):
            payload["IsTruncated"] = True
            payload["NextContinuationToken"] = str(start + size)
        return self._ok(json.dumps(payload))

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
                    "LastModified": self.modified.get(key, self.now),
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
        self.modified[key] = self.now
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


def fake_settings() -> StorageSettings:
    return StorageSettings(
        mode="managed",
        endpoint_url="http://fake:9020",
        bucket="Demo_bucket",
        profile="demo-org-team",
        region="us-east-1",
        capabilities={},
    )


def fake_client(store: FakeStore) -> ObjectStorageClient:
    return ObjectStorageClient(settings=fake_settings(), runner=store, sleep=lambda _s: None)


MIGRATION_TABLES: dict[DatasetName, str] = {
    "simulation": "app_meta",
    "equipment": "equipment_meta",
}


def seed_database(path: Path, dataset: DatasetName, *, rows: int, version: int = 1) -> None:
    schema = MIGRATION_TABLES[dataset]
    with connect(path) as connection:
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        connection.execute(
            f"CREATE TABLE IF NOT EXISTS {schema}.schema_migration "
            "(version INTEGER PRIMARY KEY, name TEXT, checksum TEXT)"
        )
        connection.execute(
            f"INSERT INTO {schema}.schema_migration VALUES (?, '0001', 'x')", [version]
        )
        connection.execute("CREATE TABLE demo AS SELECT range AS id FROM range(?)", [rows])


def add_row(path: Path, value: int = 321) -> None:
    with connect(path) as connection:
        connection.execute("INSERT INTO demo VALUES (?)", [value])


def row_count(path: Path) -> int:
    with connect(path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM demo").fetchone()
    assert row is not None
    return int(row[0])


def seed_pair(folder: Path, *, rows: int = 10) -> SyncPaths:
    """합성 두 DB. 이름은 운영과 같게 둔다 — 코드가 이름으로 어느 DB 인지 가른다."""
    databases: dict[DatasetName, Path] = {
        "simulation": folder / "capa_simulation.duckdb",
        "equipment": folder / "equipment_availability.duckdb",
    }
    for name, path in databases.items():
        seed_database(path, name, rows=rows)
    return SyncPaths(databases)
