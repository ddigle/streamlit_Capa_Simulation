# Purpose: 동기화 도구 · 일꾼이 버킷의 비밀 자리(`secrets/`)에 닿지 않음을 가짜 S3 로 고정한다.

"""BigDataQuery 자동 로그인 계정 객체(`io/bdq_login_store.OBJECT_KEY`)는 두 DB 정본과
같은 버킷에 산다(2026-11-16 사용자 결정 D2). 세대 · 사본 · 되돌리기 · 정리는 그 객체를
모르고 지나가야 한다 — 정리가 나이로 지우거나 사본이 사내 PC 로 옮기면 비밀이 새거나
계정이 사라진다.

실제 클라이언트 · 엔진 · 스크립트 본체를 태우고, 요청은 서명까지 검사하는 가짜 S3
(`scripts/s3_mock_store.py`)가 받는다. 판정은 저장소가 받은 요청 목록(`MockStore.requests`)
으로 한다 — 목록 요청의 접두는 질의 글에 인코딩돼 오므로 풀어서 본다. 검사기가 비밀에
닿는 요청을 정말 잡는지는 따로 본다(`test_the_checker_flags_every_way_to_the_secret`).
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.parse import parse_qsl, unquote, urlsplit

import pytest
from object_store_fakes import add_row, seed_pair
from s3_mock_runner import MockStoreRunner, mock_client

from capa_simulation import object_sync_engine as engine
from capa_simulation import settings as app_settings
from capa_simulation.io import bdq_login_store as store
from capa_simulation.object_sync_worker import StorageEngine
from capa_simulation.persistence import sync_state
from capa_simulation.services import object_storage_manifest as manifest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "sync_object_storage.py"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from s3_mock_store import MockStore, start_mock  # noqa: E402

# 합성 본문 — 풀 수 없는 글자다. 바이트가 그대로인지(지우거나 덮지 않음) · 사본에 없는지를 본다.
SECRET_BODY = b'{"v": 1, "cipher": "CANARY-cipher-not-a-real-token", "state": "ok"}'
LONG_AGO = timedelta(days=30)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sync_object_storage_secret_edge", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_object_storage_secret_edge"] = module
    spec.loader.exec_module(module)
    return module


def _key_of(raw: str) -> str:
    """요청 경로의 객체 키(버킷 뒤). 목록 요청은 빈 글자다."""
    return unquote(urlsplit(raw).path).lstrip("/").partition("/")[2]


def _prefix_of(raw: str) -> str:
    return dict(parse_qsl(urlsplit(raw).query, keep_blank_values=True)).get("prefix", "")


def secret_requests(mock: MockStore, since: int = 0) -> list[tuple[str, str]]:
    """저장소가 받은 요청 가운데 비밀 객체에 닿을 수 있는 것.

    객체 요청은 키가 `secrets/` 로 시작하면, 목록 요청은 접두가 비었거나(버킷 전체) 비밀
    키를 덮으면(`secrets/` 의 앞 조각 · `secrets/` 아래) 닿는 것으로 본다.
    """
    found: list[tuple[str, str]] = []
    for method, raw in mock.requests[since:]:
        key = _key_of(raw)
        if key:
            if key.startswith(store.SECRETS_PREFIX):
                found.append((method, raw))
            continue
        prefix = _prefix_of(raw)
        if (
            not prefix
            or store.OBJECT_KEY.startswith(prefix)
            or prefix.startswith(store.SECRETS_PREFIX)
        ):
            found.append((method, raw))
    return found


@pytest.fixture()
def rig(
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Iterator[SimpleNamespace]:
    sync_state.clear_all()
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(app_settings, "DATA_DIR", data)
    paths = seed_pair(data)
    script = _load_script()
    monkeypatch.setattr(script, "DATASET_PATHS", dict(paths.databases))
    mock = MockStore()
    server, endpoint = start_mock(mock)
    runner = MockStoreRunner(endpoint, mock.bucket, mock.region, mock.access_key, mock.secret_key)
    client = mock_client(runner)
    # 설정 읽기는 스크립트 그대로(값이 비면 aws 앞에서 멈춘다) — 클라이언트만 가짜 저장소 위로.
    monkeypatch.setenv("CAPA_S3_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("CAPA_S3_BUCKET", mock.bucket)
    monkeypatch.setenv("CAPA_S3_PROFILE", "demo-profile")
    monkeypatch.setattr(script, "build_client", lambda _args: client)
    mock.put(store.OBJECT_KEY, SECRET_BODY)
    yield SimpleNamespace(
        script=script,
        mock=mock,
        client=client,
        paths=paths,
        capsys=capsys,
        copies=tmp_path_factory,
    )
    server.shutdown()
    server.server_close()
    sync_state.clear_all()


def _run(rig: SimpleNamespace, *argv: str) -> str:
    """스크립트 명령 하나 — 종료 코드 0 · 저장소에 닿음 · 비밀에 닿지 않음 · 비밀 그대로."""
    before = len(rig.mock.requests)
    code = rig.script.main(list(argv))
    printed: str = rig.capsys.readouterr().out
    assert code == 0, (argv, printed)
    assert len(rig.mock.requests) > before, argv
    _untouched(rig, before, argv[0])
    return printed


def _untouched(rig: SimpleNamespace, since: int, where: str) -> None:
    assert secret_requests(rig.mock, since) == [], where
    assert rig.mock.objects.get(store.OBJECT_KEY) == SECRET_BODY, where


def _save(rig: SimpleNamespace, value: int) -> None:
    database = rig.paths.databases["simulation"]
    add_row(database, value)
    sync_state.enable(rig.paths.registry)
    sync_state.mark_dirty(database)


def _wipe_disk(rig: SimpleNamespace) -> None:
    for path in rig.paths.databases.values():
        path.unlink()
        sync_state.sidecar_path(path).unlink(missing_ok=True)
    rig.paths.generation.unlink(missing_ok=True)


def _age_all_but_the_head(rig: SimpleNamespace) -> None:
    """HEAD 포인터 밖 모든 객체(비밀 포함)를 30일 전 것으로 돌린다 — 나이로 고르는 정리가
    비밀을 고를 틈을 준다."""
    head = min(key for key in rig.mock.objects if key.startswith(manifest.HEAD_PREFIX))
    old = datetime.now(timezone.utc) - LONG_AGO
    for key in list(rig.mock.objects):
        if key != head:
            rig.mock.modified[key] = old


def _holds_the_secret(folder: Path) -> bool:
    return any(SECRET_BODY in path.read_bytes() for path in folder.rglob("*") if path.is_file())


def test_the_sync_tool_commands_never_list_copy_or_delete_the_secret(rig: SimpleNamespace) -> None:
    """사내 PC 의 이관 · 사본 · 세대 · 되돌리기 · 정리와 컨테이너의 `boot-pull`. 비밀이 버킷에
    먼저 있어도 `init` 은 빈 원격으로 보고 첫 세대를 낸다(빈 원격 판정은 세대 포인터만 본다)."""
    printed = _run(rig, "init", "--keep-writer")
    assert any(key.startswith(manifest.HEAD_PREFIX) for key in rig.mock.objects), printed

    _save(rig, 501)
    _run(rig, "push")
    _run(rig, "status")
    listed = _run(rig, "generations")
    assert "seq 2" in listed and "seq 1" in listed

    folder = rig.copies.mktemp("copy") / "fetched"
    _run(rig, "fetch-copy", "--to", str(folder))
    assert sorted(path.name for path in folder.rglob("*")) == [
        "capa_simulation.duckdb",
        "equipment_availability.duckdb",
        "generation.json",
    ]
    assert not _holds_the_secret(folder)

    _run(rig, "rollback", "--to", "1", "--yes")
    _wipe_disk(rig)
    booted = _run(rig, "boot-pull")
    assert '"action": "downloaded"' in booted, booted
    assert not _holds_the_secret(app_settings.DATA_DIR)

    _age_all_but_the_head(rig)
    before = len(rig.mock.requests)
    pruned = _run(rig, "prune", "--keep-last", "1", "--include-orphans", "--yes")
    assert "개를 지웠습니다" in pruned and " 0개를 지웠습니다" not in pruned, pruned
    deletes = [raw for method, raw in rig.mock.requests[before:] if method == "DELETE"]
    assert deletes, "정리가 실제로 지웠다 — 비밀만 피해 갔다"


def test_the_worker_upload_watch_and_daily_prune_never_reach_the_secret(
    rig: SimpleNamespace,
) -> None:
    """운영 앱의 동기화 일꾼이 부르는 차례 셋(`StorageEngine` — 세대 올리기 · HEAD 보기 ·
    하루 한 번 정리)을 기본 보존값 그대로 돌린다. 세대 여덟을 낸 뒤 HEAD 밖을 모두 30일
    전으로 돌려 정리가 지울 것이 있게 한다."""
    worker = StorageEngine(rig.client, rig.paths, engine.offline_exporter(rig.paths))
    _run(rig, "init", "--keep-writer")
    start = len(rig.mock.requests)
    for value in range(8):
        _save(rig, 600 + value)
        assert worker.upload().published, value
    assert worker.watch().head_seq == 9
    _untouched(rig, start, "upload · watch")

    _age_all_but_the_head(rig)
    before = len(rig.mock.requests)
    outcome = worker.prune(lambda: False)
    assert outcome.deleted > 0 and not outcome.interrupted, outcome
    _untouched(rig, before, "prune")
    lists = {
        _prefix_of(raw)
        for method, raw in rig.mock.requests[before:]
        if method == "GET" and not _key_of(raw)
    }
    assert lists == {*manifest.PRUNE_PREFIXES, manifest.KEEP_PREFIX}, lists


def test_the_checker_flags_every_way_to_the_secret(rig: SimpleNamespace, tmp_path: Path) -> None:
    """검사기가 헛돌지 않는다 — 버킷 전체 목록 · 비밀 접두 목록 · 비밀 키의 머리 · 받기 ·
    지우기를 모두 잡고, 세대 접두 목록은 잡지 않는다."""
    attempts: tuple[Callable[[], object], ...] = (
        lambda: rig.client.list_all_objects(""),
        lambda: rig.client.list_objects(store.SECRETS_PREFIX),
        lambda: rig.client.list_objects("sec"),
        lambda: rig.client.head(store.OBJECT_KEY),
        lambda: rig.client.get_file(store.OBJECT_KEY, tmp_path / "taken.json"),
        lambda: rig.client.delete(store.OBJECT_KEY),
    )
    for attempt in attempts:
        before = len(rig.mock.requests)
        attempt()
        assert len(secret_requests(rig.mock, before)) == 1
    assert store.OBJECT_KEY not in rig.mock.objects

    before = len(rig.mock.requests)
    rig.client.list_objects(manifest.HEAD_PREFIX)
    rig.client.list_all_objects(manifest.snapshot_prefix("simulation"))
    rig.client.head("simulation/snapshots/none.duckdb")
    assert secret_requests(rig.mock, before) == []
