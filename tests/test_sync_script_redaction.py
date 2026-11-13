# Purpose: 동기화 도구의 어느 출력에도 주소 · 버킷 · 프로필 · 작성자 원값이 없는지 검증한다.

"""사내 리뷰 202611131000 — 이관 때 `doctor` 의 값 줄과 실패한 aws 명령 줄이 그대로 사내 에이전트
대화에 붙었다. 이 파일은 값을 **환경변수로 넣고 스크립트의 설정 읽기를 그대로 태운다**(왕복 시험의
틀은 설정 · 클라이언트를 통째로 갈아끼워 가림이 지나는 길을 못 덮는다). aws 만 가짜 저장소다.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from object_store_fakes import Failure, FakeStore, add_row, seed_pair

from capa_simulation import settings as app_settings
from capa_simulation.persistence import snapshot_export, sync_state
from capa_simulation.services import object_storage_manifest as manifest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "sync_object_storage.py"

ENDPOINT = "https://S3.Demo-Hidden.invalid:9021"
HOST = "s3.demo-hidden.invalid"
BUCKET = "Demo_hidden_bucket"
PROFILE = "demo-hidden-profile"
AUTHOR = "demo-hidden-user@DEMO-HIDDEN-PC"
RAW = (ENDPOINT, HOST, BUCKET, PROFILE, "demo-hidden-user", "DEMO-HIDDEN-PC")
# 서버 글 — 소문자 호스트 · 주소와 버킷이 붙은 꼴 · 프로필을 함께 싣는다. 거절이라 다시 걸지 않는다.
SERVER_TEXT = (
    f'An error occurred (AccessDenied): Access Denied for "{ENDPOINT.lower()}/{BUCKET}" '
    f"via {HOST}:9021 with profile ({PROFILE})\n"
)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sync_object_storage_redaction", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_object_storage_redaction"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def rig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Iterator[SimpleNamespace]:
    sync_state.clear_all()
    script = _load_script()
    paths = seed_pair(tmp_path)
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(script, "DATASET_PATHS", dict(paths.databases))
    monkeypatch.setenv("CAPA_S3_ENDPOINT_URL", ENDPOINT)
    monkeypatch.setenv("CAPA_S3_BUCKET", BUCKET)
    monkeypatch.setenv("CAPA_S3_PROFILE", PROFILE)
    monkeypatch.setattr(snapshot_export, "author_label", lambda: AUTHOR)
    store = FakeStore()
    real_client = script.build_client

    def client_on_the_fake_store(args: object) -> object:
        # 설정은 스크립트가 환경변수에서 읽은 그대로 — 실행기와 물러남만 바꾼다.
        return dataclasses.replace(real_client(args), runner=store, sleep=lambda _s: None)

    monkeypatch.setattr(script, "build_client", client_on_the_fake_store)
    yield SimpleNamespace(script=script, store=store, paths=paths, capsys=capsys)
    sync_state.clear_all()


def _run(rig: SimpleNamespace, *argv: str) -> tuple[int, str]:
    code: int = rig.script.main(list(argv))
    return code, rig.capsys.readouterr().out


def _assert_hidden(printed: str, where: str) -> None:
    left = [value for value in RAW if value.lower() in printed.lower()]
    assert left == [], (where, left, printed)


def _assert_tagged(printed: str, where: str) -> None:
    """실패 글은 값 자리에 이름표가 선다 — 지운 것이 아니라 바꾼 것이다."""
    assert "--bucket <버킷> --endpoint-url <주소> --profile <프로필>" in printed, (where, printed)
    assert '"<주소>/<버킷>" via <주소> with profile (<프로필>)' in printed, (where, printed)


def _fail(rig: SimpleNamespace, operation: str, key_part: str = "") -> None:
    rig.store.failures.append(
        Failure(operation, key_part=key_part, times=1, stderr=SERVER_TEXT, returncode=254)
    )


def _mark_a_save(rig: SimpleNamespace) -> None:
    database = rig.paths.databases["simulation"]
    add_row(database)
    sync_state.enable({database: "simulation"})
    sync_state.mark_dirty(database)


def test_successful_runs_print_no_in_house_value(
    rig: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory
) -> None:
    code, doctor = _run(rig, "doctor")
    assert code == 0
    assert "엔드포인트    : 있음" in doctor
    assert "버킷          : De … et · 18자" in doctor
    assert "프로필        : 있음" in doctor
    _assert_hidden(doctor, "doctor")

    assert _run(rig, "init", "--keep-writer")[0] == 0
    _mark_a_save(rig)
    folder = tmp_path_factory.mktemp("copy") / "fetched"
    runs = [
        ("doctor",),
        ("status",),
        ("push",),
        ("generations",),
        ("fetch-copy", "--to", str(folder)),
        ("rollback", "--to", "1", "--yes"),
        ("init",),
    ]
    for argv in runs:
        code, printed = _run(rig, *argv)
        assert code == 0, (argv, printed)
        _assert_hidden(printed, argv[0])
        assert printed.splitlines()[-1].startswith(f"전송용 요약: {argv[0]} 통과; 종료 0"), argv

    _, doctor = _run(rig, "doctor")
    assert "원격 세대     : seq 3 · rollback · <작성자>" in doctor


def test_aws_failures_print_tags_in_place_of_the_values(
    rig: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory
) -> None:
    for command in ("doctor", "status", "generations"):
        _fail(rig, "list-objects-v2")
        code, printed = _run(rig, command)
        assert code == 1, command
        _assert_hidden(printed, command)
        _assert_tagged(printed, command)
        last = printed.splitlines()[-1]
        assert last.startswith(f"전송용 요약: {command} 멈춤 저장소가 거절; 종료 1"), last

    _fail(rig, "put-object", "/snapshots/")
    code, printed = _run(rig, "init", "--keep-writer")
    assert code == 1
    _assert_hidden(printed, "init")
    _assert_tagged(printed, "init")
    rig.store.failures.clear()

    assert _run(rig, "init", "--keep-writer")[0] == 0
    _mark_a_save(rig)
    _fail(rig, "put-object", "/snapshots/")
    code, printed = _run(rig, "push")
    assert code == 1
    _assert_hidden(printed, "push")
    _assert_tagged(printed, "push")
    rig.store.failures.clear()

    _fail(rig, "get-object")
    code, printed = _run(rig, "fetch-copy", "--to", str(tmp_path_factory.mktemp("copy") / "f"))
    assert code == 1
    _assert_hidden(printed, "fetch-copy")
    _assert_tagged(printed, "fetch-copy")


def test_a_rollback_whose_members_vanish_after_the_pointer_hides_the_wrapped_aws_text(
    rig: SimpleNamespace,
) -> None:
    """포인터를 낸 뒤 멤버 확인이 aws 실패로 끝나면 엔진이 그 진단 글을 감싼 `ValueError` 로 올린다
    — 스크립트의 「요청 거절」 자리도 같은 가림을 지난다."""
    assert _run(rig, "init", "--keep-writer")[0] == 0
    _mark_a_save(rig)
    assert _run(rig, "push")[0] == 0

    def fail_heads_after_the_pointer(operation: str, key: str) -> None:
        if operation == "put-object" and key.startswith(manifest.HEAD_PREFIX):
            _fail(rig, "head-object")

    rig.store.before = fail_heads_after_the_pointer

    code, printed = _run(rig, "rollback", "--to", "1", "--yes")

    assert code == 1
    assert printed.startswith("[중단] 새 HEAD 는 나갔지만")
    _assert_hidden(printed, "rollback")
    _assert_tagged(printed, "rollback")
    assert printed.splitlines()[-1] == "전송용 요약: rollback 멈춤 요청 거절; 종료 1"
