# Purpose: 실제 aws CLI 로 가짜 S3 에 이관·시작 받기·저장·정리·사본 받기를 끝까지 돌려 본다.

"""`CAPA_TEST_AWS_BIN` 이 있을 때만 돈다(없으면 건너뛴다).

`FakeStore` 는 인자 배열을 해석할 뿐이라 `aws` 의 실제 요청 꼴을 모른다. 여기서는 사내에서 쓰는 판
(1.46.3)이 서명 · 질의 · `Expect: 100-continue` · 메타데이터 · 목록 XML 을 가짜 S3 와 주고받는다.
의존성에 넣지 않는다 — 판 고정은 `docker/Dockerfile-prod` 한 줄이다.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from object_store_fakes import add_row, row_count, seed_pair

from capa_simulation import object_sync_engine as engine
from capa_simulation import settings as app_settings
from capa_simulation.io.object_storage import (
    ObjectStorageClient,
    ObjectStorageError,
    StorageSettings,
    classify_failure,
)
from capa_simulation.persistence import sync_state
from capa_simulation.services import object_storage_manifest as manifest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import container_start  # noqa: E402
from s3_mock_store import MockStore, start_mock  # noqa: E402

AWS_BIN = os.environ.get("CAPA_TEST_AWS_BIN", "")
pytestmark = pytest.mark.skipif(not AWS_BIN, reason="CAPA_TEST_AWS_BIN 이 없다")
PROFILE = "demo-profile"


@pytest.fixture()
def real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    sync_state.clear_all()
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    store = MockStore()
    server, endpoint = start_mock(store)
    home = tmp_path / "aws"
    home.mkdir()
    (home / "credentials").write_text(
        f"[{PROFILE}]\naws_access_key_id = {store.access_key}\n"
        f"aws_secret_access_key = {store.secret_key}\n",
        encoding="utf-8",
    )
    (home / "config").write_text(
        f"[profile {PROFILE}]\nregion = {store.region}\n", encoding="utf-8"
    )
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(home / "credentials"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(home / "config"))
    monkeypatch.setenv("PATH", f"{Path(AWS_BIN).parent}{os.pathsep}{os.environ['PATH']}")
    settings = StorageSettings(
        mode="managed",
        endpoint_url=endpoint,
        bucket=store.bucket,
        profile=PROFILE,
        region=store.region,
        capabilities={},
    )
    paths = seed_pair(tmp_path, rows=2_000)
    sync_state.enable(paths.registry)
    yield SimpleNamespace(
        store=store,
        client=ObjectStorageClient(settings=settings, sleep=lambda _s: None),
        paths=paths,
        exporter=engine.offline_exporter(paths),
        folder=tmp_path,
    )
    server.shutdown()
    server.server_close()
    sync_state.clear_all()


def _init(real: SimpleNamespace) -> None:
    outcome = engine.init_generation(
        real.client, real.paths, exporter=real.exporter, note="최초 이관", keep_writer=True
    )
    assert outcome.published


def _publish(real: SimpleNamespace) -> engine.PublishOutcome:
    return engine.publish_generation(
        real.client, real.paths, exporter=real.exporter, origin="app", note="앱 저장"
    )


def _save(real: SimpleNamespace, value: int = 321) -> None:
    path = real.paths.databases["simulation"]
    add_row(path, value)
    sync_state.mark_dirty(path)


def _wipe_disk(real: SimpleNamespace) -> None:
    for path in real.paths.databases.values():
        path.unlink()
        sync_state.sidecar_path(path).unlink(missing_ok=True)
    real.paths.generation.unlink()


def test_the_version_in_use_runs_here() -> None:
    assert "aws-cli/1.46.3" in os.popen(f"{AWS_BIN} --version").read()


def test_the_whole_way_round(
    real: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """이관 → 새 pod 받기 → 저장 → 게시 → 새 pod 받기 → 사본."""
    _init(real)
    _wipe_disk(real)

    first = engine.boot_pull(real.client, real.paths)

    assert first.ok, first.kind
    assert first.action == engine.ACTION_DOWNLOADED
    _save(real)
    published = _publish(real)
    assert published.published
    pointer = published.pointer
    assert pointer is not None
    metadata = real.store.metadata[pointer.members["simulation"].snapshot_key]
    assert metadata["sha256"] == pointer.members["simulation"].sha256

    _wipe_disk(real)
    second = engine.boot_pull(real.client, real.paths)

    assert second.ok, second.kind
    assert row_count(real.paths.databases["simulation"]) == 2_001

    folder = tmp_path_factory.mktemp("copy")
    fetched = engine.fetch_copy(real.client, real.paths, folder)
    assert row_count(fetched.files["simulation"]) == 2_001


def test_a_pointer_whose_answer_was_lost_is_recognised(real: SimpleNamespace) -> None:
    """실제 `aws` 의 재시도까지 지나도 답이 끊기면 예외로 끝난다. 다음 회차가 자기 포인터를 안다."""
    _init(real)
    _save(real)
    real.store.force_on("PUT", manifest.HEAD_PREFIX, times=20, stored=True)

    with pytest.raises(ObjectStorageError):
        _publish(real)

    real.store.faults.clear()
    outcome = _publish(real)

    assert outcome.settled is not None
    assert sync_state.read_generation(real.paths.generation).base_seq == 2


def test_prune_goes_by_the_time_the_store_gave(real: SimpleNamespace) -> None:
    _init(real)
    for value in range(6):
        _save(real, value)
        assert _publish(real).published
    newest = max(real.store.modified.values())
    old = newest - timedelta(days=30)
    for key in list(real.store.objects):
        if "__s000000000001__" in key or key.startswith("simulation/snapshots/000000000001__"):
            real.store.modified[key] = old
    for key in real.store.objects:
        if key.startswith("equipment/"):
            real.store.modified[key] = newest

    outcome = engine.prune(real.client, keep_last=1, keep_days=7)

    assert outcome.deleted == 2
    assert not [key for key in real.store.objects if "__s000000000001__" in key]


def test_rollback_reads_the_head_of_each_member(real: SimpleNamespace) -> None:
    _init(real)
    _save(real)
    assert _publish(real).published

    pointer = engine.rollback(real.client, to_seq=1, note="되돌림")

    assert pointer.seq == 3


def _start_script_client(
    real: SimpleNamespace, home: Path
) -> tuple[ObjectStorageClient, dict[str, str]]:
    """시작 스크립트가 쓴 `~/.aws` 만 보는 클라이언트 — 고정틀의 프로필 파일은 넘기지 않는다."""
    environ = {
        "HOME": str(home),
        "PATH": f"{Path(AWS_BIN).parent}{os.pathsep}{os.environ['PATH']}",
        "CAPA_S3_ACCESS_KEY": real.store.access_key,
        "CAPA_S3_SECRET_KEY": real.store.secret_key,
    }
    client = ObjectStorageClient(
        settings=real.client.settings,
        runner=container_start.AwsRunner(container_start.run_command, environ),
        sleep=lambda _s: None,
    )
    return client, environ


def test_the_profile_the_start_script_writes_is_what_the_real_cli_reads(
    real: SimpleNamespace, tmp_path: Path
) -> None:
    """셸이 없어 파일을 직접 쓴다 — 중첩 `s3` 절 · 체크섬 줄을 실제 CLI 가 읽는지가 답이다."""
    home = tmp_path / "start-home"
    home.mkdir()
    client, environ = _start_script_client(real, home)

    profile = container_start.aws_profile_step(environ, real.client.settings)
    cli, version = container_start.aws_cli_step(client)
    bucket = container_start.bucket_step(client)

    assert profile.status == "ok"
    assert (cli.status, version) == ("ok", "1.46.3")
    assert bucket == container_start.StepResult("ok", "정상")
    assert client.check_addressing_style() == "path"
    _init(real)
    assert engine.read_remote_head(client).head_seq == 1


def test_the_bucket_line_reads_a_wrong_key_as_refused(
    real: SimpleNamespace, tmp_path: Path
) -> None:
    home = tmp_path / "start-home"
    home.mkdir()
    client, environ = _start_script_client(real, home)
    environ["CAPA_S3_SECRET_KEY"] = "another-secret-for-the-demo-store"
    container_start.aws_profile_step(environ, real.client.settings)

    assert container_start.bucket_step(client).reason == "저장소가 거절"


def test_a_refused_key_reads_as_denied(real: SimpleNamespace) -> None:
    real.store.access_key = "someone-else"

    with pytest.raises(ObjectStorageError) as caught:
        engine.read_remote_head(real.client)

    assert classify_failure(caught.value) == "denied"


def test_a_missing_bucket_reads_as_no_bucket(real: SimpleNamespace) -> None:
    real.store.bucket = "Another_bucket"

    with pytest.raises(ObjectStorageError) as caught:
        engine.read_remote_head(real.client)

    assert classify_failure(caught.value) == "no_bucket"


def test_an_unreachable_store_reads_as_unreachable(real: SimpleNamespace) -> None:
    settings = real.client.settings
    closed = ObjectStorageClient(
        settings=StorageSettings(
            mode=settings.mode,
            endpoint_url="http://127.0.0.1:9",
            bucket=settings.bucket,
            profile=settings.profile,
            region=settings.region,
            capabilities={},
        ),
        sleep=lambda _s: None,
    )

    with pytest.raises(ObjectStorageError) as caught:
        engine.read_remote_head(closed)

    assert classify_failure(caught.value) == "unreachable"
