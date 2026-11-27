# Purpose: 동기화 도구의 어느 출력에도 주소 · 버킷 · 프로필 · 작성자 원값과 내 PC 홈이 없는지 본다.

"""사내 리뷰 202611131000 — 이관 때 `doctor` 의 값 줄과 실패한 aws 명령 줄이 그대로 사내 에이전트
대화에 붙었다. 이 파일은 값을 **환경변수로 넣고 스크립트의 설정 읽기를 그대로 태운다**(왕복 시험의
틀은 설정 · 클라이언트를 통째로 갈아끼워 가림이 지나는 길을 못 덮는다). aws 만 가짜 저장소다.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from object_store_fakes import Failure, FakeStore, add_row, seed_pair

from capa_simulation import settings as app_settings
from capa_simulation.io import object_storage
from capa_simulation.io.object_storage import ObjectStorageClient, StorageSettings
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
    # 감사 조각 작업 파일(gettempdir()/capa-audit-tool)을 basetemp 안에 둔다.
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
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


def _probe_on_the_fake_store(rig: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """`probe` 는 조건부 쓰기를 볼 클라이언트를 `build_client` 를 거치지 않고 따로 만든다 — 그것도
    가짜 저장소에 붙인다(설정은 스크립트가 읽은 그대로)."""
    store = rig.store

    def client(*, settings: StorageSettings) -> ObjectStorageClient:
        return ObjectStorageClient(settings=settings, runner=store, sleep=lambda _s: None)

    monkeypatch.setattr(rig.script, "ObjectStorageClient", client)


def test_probe_prints_tags_in_place_of_the_values_and_the_author(
    rig: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`probe` 의 결과 JSON 은 확인자를 이름표로 찍고, `--write` 로 쓰는 능력 기록은 원값을 그대로
    둔다. 그 기록 파일 경로의 내 PC 홈은 「기록」 줄에 `%USERPROFILE%` 로 찍히고 파일은 실제 경로에
    선다. 거절된 조건부 쓰기 줄과 첫 쓰기의 `[중단]` 줄도 같은 가림을 지난다."""
    _probe_on_the_fake_store(rig, monkeypatch)
    record = tmp_path / "capabilities.json"
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    code, printed = _run(rig, "probe", "--write", str(record))

    assert code == 0, printed
    _assert_hidden(printed, "probe")
    assert '"_확인자": "<작성자>"' in printed
    assert f"기록          : {Path(HOME_TAG) / record.name}\n" in printed, printed
    assert str(tmp_path) not in printed
    assert json.loads(record.read_text(encoding="utf-8"))["_확인자"] == AUTHOR

    def fail_the_conditional_put(operation: str, _key: str) -> None:
        if operation == "put-object" and "--if-none-match" in rig.store.calls[-1]:
            _fail(rig, "put-object")

    rig.store.before = fail_the_conditional_put
    code, printed = _run(rig, "probe")
    rig.store.before = None

    assert code == 0, printed
    assert "조건부 쓰기   : 거부됨 — " in printed
    assert '"conditional_put_if_none_match_star": false' in printed
    _assert_hidden(printed, "probe 조건부 쓰기")
    _assert_tagged(printed, "probe 조건부 쓰기")

    _fail(rig, "put-object", "_probe/")
    code, printed = _run(rig, "probe")

    assert code == 1
    assert printed.startswith("[중단] ")
    _assert_hidden(printed, "probe 멈춤")
    _assert_tagged(printed, "probe 멈춤")
    assert printed.splitlines()[-1].startswith("전송용 요약: probe 멈춤 저장소가 거절; 종료 1")


def test_the_other_failure_line_hides_the_values(
    rig: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """aws 경계 밖의 실패(`BOOTSTRAP_ERRORS` — DuckDB · 파일 · 스냅샷 오류)의 `[중단]` 줄도 같은
    가림을 지난다."""

    def fail_carrying_the_values(_client: object, **_options: object) -> object:
        raise RuntimeError(SERVER_TEXT.strip())

    monkeypatch.setattr(rig.script.engine, "list_generations", fail_carrying_the_values)

    code, printed = _run(rig, "generations")

    assert code == 1
    assert printed.startswith("[중단] ")
    _assert_hidden(printed, "generations")
    assert '"<주소>/<버킷>" via <주소> with profile (<프로필>)' in printed
    assert printed.splitlines()[-1] == "전송용 요약: generations 멈춤 그 밖의 실패; 종료 1"


def _settings_file_not_in_utf8(monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
    """사내 PC 에서 메모장 · PowerShell `Out-File` 로 고쳐 저장한 꼴(cp949)."""
    record = folder / "object_storage_capabilities.json"
    record.write_bytes('{"메모": "사내에서 고침"}'.encode("cp949"))
    monkeypatch.setattr(object_storage, "CAPABILITIES_PATH", record)


def _settings_file_refused(monkeypatch: pytest.MonkeyPatch, _folder: Path) -> None:
    def refuse(*, environ: Mapping[str, str] | None = None) -> StorageSettings:
        raise PermissionError(13, "Permission denied", "object_storage.json")

    monkeypatch.setattr(object_storage, "load_settings", refuse)


@pytest.mark.parametrize(
    "break_settings",
    [_settings_file_not_in_utf8, _settings_file_refused],
    ids=["not-utf8", "permission"],
)
def test_settings_the_script_cannot_read_still_end_on_its_own_lines(
    rig: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    break_settings: Callable[[pytest.MonkeyPatch, Path], None],
) -> None:
    """가릴 값을 못 읽어도 명령은 제 자리에서 멈춘다 — `[중단]` 과 전송용 요약, `boot-pull` 은 시작
    스크립트가 읽는 한 줄. 가림 준비가 그 앞에서 새면 트레이스백만 남는다."""
    break_settings(monkeypatch, tmp_path)

    code, printed = _run(rig, "doctor")

    assert code == 1
    assert printed.startswith("[중단] ")
    assert printed.splitlines()[-1] == "전송용 요약: doctor 멈춤 그 밖의 실패; 종료 1"

    code, printed = _run(rig, "boot-pull")

    assert code == 1
    assert json.loads(printed.splitlines()[-1])["kind"] == manifest.FAILURE_OTHER


# --- 내 PC 경로(물음 보드 「정한 것」 10) -----------------------------------------------------

HOME_TAG = "%USERPROFILE%"


C_HOME = "C:\\Users\\demo.hidden"
D_HOME = "D:\\Profiles\\demo.hidden"


@pytest.mark.parametrize(
    ("home", "text", "shown"),
    [
        (
            C_HOME,
            "--body 'C:\\Users\\demo.hidden\\AppData\\Local\\Temp\\capa\\a.zst'",
            "--body '%USERPROFILE%\\AppData\\Local\\Temp\\capa\\a.zst'",
        ),
        (
            C_HOME,
            "받음 : seq 2 · C:\\Users\\DEMO.HIDDEN\\copy",
            "받음 : seq 2 · %USERPROFILE%\\copy",
        ),
        (C_HOME, "c:/users/demo.hidden/AppData/x", "%USERPROFILE%/AppData/x"),
        (C_HOME, "C:\\Users\\DEMOHI~1\\AppData\\Local\\x", "%USERPROFILE%\\AppData\\Local\\x"),
        (C_HOME, "C:\\Users\\demo hidden two\\x.duckdb", "%USERPROFILE%\\x.duckdb"),
        (C_HOME, "C:\\Users\\demo.hiddenmore\\x", "%USERPROFILE%\\x"),
        (C_HOME, "(이전 파일 백업 C:\\Users\\demo.hidden)", "(이전 파일 백업 %USERPROFILE%)"),
        (
            D_HOME,
            "D:\\Profiles\\demo.hidden\\x · d:/profiles/DEMO.HIDDEN/y",
            "%USERPROFILE%\\x · %USERPROFILE%/y",
        ),
        (C_HOME, "D:\\data\\capa\\x.duckdb", "D:\\data\\capa\\x.duckdb"),
        (
            C_HOME,
            "[Errno 13] Permission denied: 'C:\\\\Users\\\\demo.hidden\\\\AppData\\\\x'",
            "[Errno 13] Permission denied: '%USERPROFILE%\\\\AppData\\\\x'",
        ),
        (
            D_HOME,
            "'C:\\\\Users\\\\DEMOHI~1\\\\x' · 'D:\\\\Profiles\\\\demo.hidden\\\\y'",
            "'%USERPROFILE%\\\\x' · '%USERPROFILE%\\\\y'",
        ),
        (C_HOME, "https://users/demo.hidden/x", "https://users/demo.hidden/x"),
    ],
)
def test_the_home_folder_is_shown_as_userprofile_in_every_form(
    monkeypatch: pytest.MonkeyPatch, home: str, text: str, shown: str
) -> None:
    """홈 값 그대로 · 대소문자 · `/` 구분자 · 짧은 8.3 이름 · 빈칸 든 계정 · 다른 계정 · 드라이브가
    다른 홈 · 오류 글의 겹 구분자(`repr`) 모두 `%USERPROFILE%` 로 — 그 뒤 경로는 그대로, 홈 밖
    경로와 주소(`https://users/…`)는 건드리지 않는다."""
    script = _load_script()
    monkeypatch.setenv("USERPROFILE", home)

    assert script.masked(text) == shown


def test_the_four_places_that_print_a_pc_path_show_userprofile(
    rig: SimpleNamespace,
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """사내 PC 경로가 찍히던 자리 넷 — 실패한 aws 명령 줄의 `--body` · 받을 경로, `fetch-copy` 의
    받은 폴더, `init` 의 「로컬 DB 가 없습니다」, `pull` 의 백업 경로 — 가 홈을 이름표로 찍는다.
    출력만 가린다: 받은 폴더 · 백업은 실제 경로에 그대로 있다(리뷰 202611131000 sync not_done 1).

    홈은 이 시험의 임시 뿌리다 — 운영 DB 자리(`tmp_path`)와 받을 폴더(그 곁)가 함께 그 아래에 든다.
    """
    home = str(tmp_path_factory.getbasetemp())
    assert str(tmp_path).startswith(home)
    monkeypatch.setenv("USERPROFILE", home)

    def assert_home_hidden(printed: str, where: str) -> None:
        assert home not in printed, (where, printed)
        assert HOME_TAG in printed, (where, printed)

    database = rig.paths.databases["simulation"]
    parked = database.with_suffix(".parked")
    database.rename(parked)
    code, printed = _run(rig, "init", "--keep-writer")
    database = parked.rename(database)
    assert code == 1
    assert f"[중단] 시뮬레이션 로컬 DB 가 없습니다: {HOME_TAG}" in printed
    assert_home_hidden(printed, "init 로컬 DB 없음")

    _fail(rig, "put-object", "/snapshots/")
    code, printed = _run(rig, "init", "--keep-writer")
    assert code == 1
    # Windows 경로는 `\` 가 있어 aws 인자가 따옴표로 싸인다 — 따옴표가 있든 없든.
    assert re.search(r"--body '?%USERPROFILE%", printed), printed
    assert_home_hidden(printed, "init --body")
    rig.store.failures.clear()

    assert _run(rig, "init", "--keep-writer")[0] == 0
    _fail(rig, "get-object")
    code, printed = _run(rig, "fetch-copy", "--to", str(tmp_path_factory.mktemp("copy") / "failed"))
    assert code == 1
    assert re.search(r" '?%USERPROFILE%", printed.split("실행한 명령: ", 1)[1]), printed
    assert_home_hidden(printed, "fetch-copy 받을 경로")
    rig.store.failures.clear()

    folder = tmp_path_factory.mktemp("copy") / "fetched"
    code, printed = _run(rig, "fetch-copy", "--to", str(folder))
    assert code == 0
    assert f"받음 : seq 1 · {HOME_TAG}" in printed
    assert_home_hidden(printed, "fetch-copy 받음")
    assert any(folder.iterdir()), "받은 폴더는 실제 경로에 있다"

    _mark_a_save(rig)
    assert _run(rig, "push")[0] == 0
    assert _run(rig, "rollback", "--to", "1", "--yes")[0] == 0
    code, printed = _run(rig, "pull")
    assert code == 0, printed
    installs = [line for line in printed.splitlines() if " 설치 : seq " in line]
    assert len(installs) == 2, printed
    for line in installs:
        assert f"(이전 파일 백업 {HOME_TAG}" in line, line
    assert_home_hidden(printed, "pull 백업")
    assert any(snapshot_export.backup_dir().iterdir()), "백업은 실제 경로에 있다"


def test_a_state_file_another_program_holds_stops_with_the_home_hidden(
    rig: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    r"""상태 파일 바꿔치기(`os.replace`)가 Windows 에서 남이 쥔 파일 때문에 거절되면 그 실패는
    일부러 그대로 올라가 `[중단]` 줄에 선다(`BOOTSTRAP_ERRORS` 갈래). 그 글은 거절된 두 경로를
    싣는다 — 둘 다 홈(`C:\Users\<계정>`)이 이름표로 바뀌고 홈 뒤 경로와 전송용 요약은 그대로다.
    홈 값(`USERPROFILE`)은 바꾸지 않는다 — 그 꼴의 경로는 이 PC 의 홈이 아니어도 가린다."""
    held = sync_state.generation_path(rig.paths.databases["simulation"]).name
    real_replace = os.replace

    def held_by_another_program(source: str, target: str) -> None:
        if Path(target).name == held:
            raise PermissionError(
                13,
                "Permission denied",
                f"{C_HOME}\\capa\\data\\{held}.tmp",
                None,
                f"{C_HOME}\\capa\\data\\{held}",
            )
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", held_by_another_program)

    code, printed = _run(rig, "init", "--keep-writer")

    assert code == 1
    stop = next(line for line in printed.splitlines() if line.startswith("[중단] "))
    assert "demo.hidden" not in printed, printed
    assert f"'{HOME_TAG}\\\\capa\\\\data\\\\{held}.tmp'" in stop, stop
    assert f"'{HOME_TAG}\\\\capa\\\\data\\\\{held}'" in stop, stop
    summary = printed.splitlines()[-1]
    assert summary.startswith("전송용 요약: init 멈춤 그 밖의 실패; 종료 1"), summary


# --- 닫힌 주소 · 표준 오류(E2E D-16) ---------------------------------------------------------
#
# 사내 PC 처럼 스크립트를 따로 띄운다 — 같은 프로세스에서 `main()` 을 부르면 pytest 가 뿌리
# 로거에 제 처리기를 달아 로거 글이 표준 오류로 가지 않는다(그 길이 샌 곳이다). `aws` 자리만
# 바꾼다: 주소에 실제로 붙어 보고, 닫혀 있으면 `aws` 1.46.3 이 찍는 꼴로 실패한다.

CHILD_DRIVER = r"""
import logging, os, runpy, socket, sys, time
from urllib.parse import urlsplit

from pathlib import Path

time.sleep = lambda _seconds: None  # 재시도 물러남만 건너뛴다
from capa_simulation import object_sync_engine, settings
from capa_simulation.io import object_storage

# 저장소 `data/` 를 건드리지 않는다 — 운영 DB 자리 · 작업 폴더를 시험 뿌리로.
settings.DATA_DIR = Path(os.environ["CHILD_DATA_DIR"])
settings.DUCKDB_PATH = settings.DATA_DIR / "capa_simulation.duckdb"
settings.EQUIPMENT_DUCKDB_PATH = settings.DATA_DIR / "equipment_availability.duckdb"

script, mode, *argv = sys.argv[1:]


def closed(self, args, env, *, timeout_seconds):
    args = list(args)
    endpoint = args[args.index("--endpoint-url") + 1]
    bucket = args[args.index("--bucket") + 1]
    key = args[args.index("--key") + 1] if "--key" in args else ""
    if mode == "log-argv":
        # 어느 모듈의 로거든 원값을 실을 수 있다 — 도구는 그 글도 가려야 한다.
        logging.getLogger("capa_simulation.io.object_storage").warning("aws %s", " ".join(args))
    parts = urlsplit(endpoint)
    try:
        socket.create_connection((parts.hostname, parts.port), timeout=2).close()
    except OSError:
        text = f'\nCould not connect to the endpoint URL: "{endpoint}/{bucket}/{key}"\n'
        return object_storage.CommandResult(tuple(args), 255, "", text, 0.0)
    raise SystemExit("주소가 열려 있다 — 시험 전제가 틀렸다")


def crash(*_args, **_kwargs):
    names = ("CAPA_S3_ENDPOINT_URL", "CAPA_S3_BUCKET", "CAPA_S3_PROFILE")
    values = [os.environ[name] for name in names]
    values.append(os.path.join(os.environ["USERPROFILE"], "x"))
    raise IndexError("코드 결함 " + " ".join(values))


object_storage.SubprocessCommandRunner.run = closed
if mode == "crash":
    object_sync_engine.fetch_copy = crash
sys.argv = [script, *argv]
runpy.run_path(script, run_name="__main__")
"""


def _closed_endpoint() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def _run_child(home: Path, endpoint: str, mode: str, *argv: str) -> tuple[int, str, str]:
    temp = home / "AppData" / "Local" / "Temp"
    temp.mkdir(parents=True, exist_ok=True)
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CAPA_", "AWS_", "PYTHON"))
    }
    env.update(
        {
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
            "CHILD_DATA_DIR": str(home.parent / "data"),
            "CAPA_S3_ENDPOINT_URL": endpoint,
            "CAPA_S3_BUCKET": BUCKET,
            "CAPA_S3_PROFILE": PROFILE,
            "USERPROFILE": str(home),
            "TMPDIR": str(temp),
            "TEMP": str(temp),
            "TMP": str(temp),
        }
    )
    done = subprocess.run(
        [sys.executable, "-c", CHILD_DRIVER, str(SCRIPT_PATH), mode, *argv],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
        check=False,
    )
    return done.returncode, done.stdout, done.stderr


def _assert_no_value(stream: str, where: str, endpoint: str, home: Path) -> None:
    raw = (endpoint, endpoint.removeprefix("http://"), BUCKET, PROFILE, str(home))
    left = [value for value in raw if value.lower() in stream.lower()]
    assert left == [], (where, left, stream)


AUDITED_ON_A_CLOSED_ADDRESS = (("fetch-copy", "--to", "{copy}"), ("rollback", "--to", "1", "--yes"))


@pytest.mark.parametrize("argv", AUDITED_ON_A_CLOSED_ADDRESS, ids=["fetch-copy", "rollback"])
def test_a_closed_address_leaves_no_value_on_either_stream(
    tmp_path: Path, argv: tuple[str, ...]
) -> None:
    """감사 대상 명령이 닫힌 주소에 멈추면 감사 조각 올리기도 실패한다. 그 경고는 갈래 낱말 한 줄
    이고 트레이스백 · 실패 글(주소 · 버킷 · 프로필 · `--body` 의 내 PC 임시 경로)을 싣지 않는다."""
    endpoint = _closed_endpoint()
    home = tmp_path / "home"
    copy = str(home / "copy")

    code, out, err = _run_child(home, endpoint, "plain", *(part.format(copy=copy) for part in argv))

    assert code == 1, (out, err)
    _assert_no_value(out, "stdout", endpoint, home)
    _assert_no_value(err, "stderr", endpoint, home)
    assert "Traceback" not in err, err
    assert "감사 조각을 올리지 못했습니다 — unreachable" in err.splitlines(), err
    assert "[경고] 감사 기록 조각을 올리지 못했습니다 — 명령의 결과는 그대로입니다." in out
    assert out.splitlines()[-1].startswith(f"전송용 요약: {argv[0]} 멈춤 "), out


def test_any_logger_line_passes_the_mask(tmp_path: Path) -> None:
    """도구가 도는 동안 어느 로거의 글이든 표준 오류에 닿기 전에 가림을 지난다."""
    endpoint = _closed_endpoint()
    home = tmp_path / "home"

    code, out, err = _run_child(home, endpoint, "log-argv", "fetch-copy", "--to", str(home / "c"))

    assert code == 1, (out, err)
    assert "aws s3api put-object --bucket <버킷> --endpoint-url <주소> --profile <프로필>" in err, (
        err
    )
    assert f"--body {HOME_TAG}" in err, err
    _assert_no_value(out, "stdout", endpoint, home)
    _assert_no_value(err, "stderr", endpoint, home)


def test_an_unexpected_error_prints_a_masked_traceback(tmp_path: Path) -> None:
    """예상 밖의 예외(코드 결함)는 그대로 트레이스백 · 종료 1 로 끝나되, 그 글도 가림을 지난다."""
    endpoint = _closed_endpoint()
    home = tmp_path / "home"

    code, out, err = _run_child(home, endpoint, "crash", "fetch-copy", "--to", str(home / "c"))

    assert code == 1, (out, err)
    assert "Traceback" in err and "IndexError: 코드 결함 <주소> <버킷> <프로필>" in err, err
    _assert_no_value(out, "stdout", endpoint, home)
    _assert_no_value(err, "stderr", endpoint, home)
