# Purpose: 부대공정 S3 Drive 원천(낱장 CSV 여섯)을 가짜 S3 로 받고 · 머리 보고 · 놓는 중 · 빠짐 ·
# 상한 · 실패와 한 판으로 묶은 바이트를 본다.

"""S3 Drive 가져오기 원천(`extra_process_drive.DriveSource` — 2026-11-20 보드 결정-2 (가)).

가짜 S3(`scripts/s3_mock_store.py`)에 견본 여섯 장(`tests/fixtures/extra_process/`)을 놓고 받는다.
놓인 시각은 저장소 시각으로 2분 넘게 앞이어야 받는다(놓는 중 판정) — 시험은 놓인 시각을 한 시간
앞으로 고쳐 둔다(`MockStore.modified`).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from extra_process_fixtures import BOND, bump_version, edited, set_cell, template_files

import capa_simulation.extra_process_drive as drive
from capa_simulation.extra_process_drive import (
    DRIVE_FILES,
    DRIVE_KEYS,
    DRIVE_PREFIX,
    ETAG_UNKNOWN,
    MISSING_WORD,
    PLACING_WORD,
    TOO_LARGE,
    UNAVAILABLE,
    DriveSource,
    set_etag,
)
from capa_simulation.extra_process_intake import (
    SourceFailure,
    SourceNotReady,
    installed_source,
    stage_pack,
)
from capa_simulation.io import s3_small
from capa_simulation.io.s3_small import S3Target
from capa_simulation.persistence.models import EXTRA_KIND_APPLY, ExtraProcessState
from capa_simulation.persistence.models import ExtraProcessVersion as Version
from capa_simulation.services.extra_process_pack import (
    JUDGE_APPLY,
    JUDGE_BACKWARD,
    NOT_UTF8_HINT,
    bundle_pack_files,
    pack_sha256,
    pack_to_zip,
    read_pack_zip,
    template_zip,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from s3_mock_store import MockStore, etag_of, start_mock  # noqa: E402

LONG_AGO = timedelta(hours=1)


@pytest.fixture()
def mock_s3() -> Iterator[tuple[MockStore, str]]:
    store = MockStore()
    server, endpoint = start_mock(store)
    yield store, endpoint
    server.shutdown()
    server.server_close()


def _target(store: MockStore, endpoint: str, *, secret: str | None = None) -> S3Target:
    return S3Target(
        endpoint_url=endpoint,
        bucket=store.bucket,
        region=store.region,
        access_key=store.access_key,
        secret_key=store.secret_key if secret is None else secret,
    )


def _place(store: MockStore, files: dict[str, bytes], *, age: timedelta = LONG_AGO) -> None:
    """여섯(또는 일부)을 놓고 놓인 시각을 `age` 만큼 앞으로 둔다."""
    for name, data in files.items():
        key = f"{DRIVE_PREFIX}{name}"
        store.put(key, data)
        store.modified[key] = datetime.now(timezone.utc) - age


def _source(store: MockStore, endpoint: str, **kwargs: str) -> DriveSource:
    target = _target(store, endpoint, **kwargs)
    return DriveSource(lambda: target)


def test_the_six_names_are_the_template_files() -> None:
    assert DRIVE_FILES == tuple(sorted(template_files()))
    assert all(key.startswith("extra_process/") for key in DRIVE_KEYS)


def test_bundling_the_downloaded_template_gives_the_same_bytes() -> None:
    """양식 내려받기(`pack_to_zip`)를 풀어 그대로 놓은 여섯 장은 그 판과 같은 바이트(sha)다 —
    「새 판으로」 판을 사람이 놓았을 때 「같음」 으로 읽히는 바탕(표준 라이브러리 deflate 가 같은
    동안)."""
    import io
    import zipfile

    pack = read_pack_zip(bundle_pack_files(template_files())).pack
    assert pack is not None
    written = pack_to_zip(pack)
    with zipfile.ZipFile(io.BytesIO(written)) as archive:
        members = {info.filename: archive.read(info) for info in archive.infolist()}
    assert bundle_pack_files(members) == written
    with zipfile.ZipFile(io.BytesIO(template_zip())) as archive:
        blank = {info.filename: archive.read(info) for info in archive.infolist()}
    assert bundle_pack_files(blank) == template_zip()
    with pytest.raises(ValueError):
        bundle_pack_files({"01_Process.csv": b""})


def test_six_settled_files_are_fetched_as_one_pack(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    files = template_files()
    _place(store, files)

    fetched = _source(store, endpoint).fetch()

    assert fetched.data == bundle_pack_files(files)
    reading = read_pack_zip(fetched.data)
    assert reading.accepted and reading.sha256 == pack_sha256(fetched.data)
    assert (fetched.place, fetched.key) == ("S3 Drive", DRIVE_PREFIX)
    expected = set_etag({name: etag_of(files[name]) for name in DRIVE_FILES})
    assert fetched.etag == expected and str(expected).startswith("set-")
    assert fetched.last_modified is not None
    # 머리 보기는 받기와 같은 ETag 다(새 파일 감지가 받은 파일을 「새 파일」 로 보지 않는다).
    assert _source(store, endpoint).head().etag == expected


def test_nothing_on_the_drive_is_not_ready_not_a_failure(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3

    with pytest.raises(SourceNotReady) as caught:
        _source(store, endpoint).fetch()

    assert caught.value.word == MISSING_WORD
    assert _source(store, endpoint).head().etag is None


def test_a_missing_file_goes_to_the_rejection_table(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    files = template_files()
    files.pop("04_equipment_days.csv")
    _place(store, files)
    # 이름이 다른 파일은 정해진 이름의 장이 아니다 — 받지 않아 그 장은 「파일 없음」 이다.
    _place(store, {"04_Equipment_Days.csv": template_files()["04_equipment_days.csv"]})

    fetched = _source(store, endpoint).fetch()

    reading = read_pack_zip(fetched.data)
    assert not reading.accepted
    assert [(item.file, item.reason) for item in reading.problems] == [
        ("04_equipment_days.csv", "파일 없음")
    ]


def test_a_freshly_placed_file_waits_until_placing_settles(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    files = template_files()
    _place(store, files)
    _place(store, {"03_productivity.csv": files["03_productivity.csv"]}, age=timedelta(seconds=10))

    with pytest.raises(SourceNotReady) as caught:
        _source(store, endpoint).fetch()
    assert caught.value.word == PLACING_WORD

    store.modified[f"{DRIVE_PREFIX}03_productivity.csv"] -= timedelta(minutes=3)
    assert _source(store, endpoint).fetch().data == bundle_pack_files(files)


def test_a_file_replaced_while_fetching_is_placing(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """받은 뒤 다시 본 머리가 받은 것과 다르면(받는 동안 사람이 한 장을 바꿈) 「놓는 중」 이다 —
    놓인 시각이 오래돼 보여도 섞인 판을 넘기지 않는다."""
    store, endpoint = mock_s3
    files = template_files()
    _place(store, files)
    real_head = s3_small.head_meta
    swapped: list[str] = []

    def head_after_swap(
        target: S3Target,
        key: str,
        *,
        moment: float | None = None,
        deadline_seconds: float | None = None,
    ) -> s3_small.S3Head | None:
        if not swapped:
            changed = edited(files, "03_productivity.csv", lambda rows: rows[:-1])
            _place(store, {"03_productivity.csv": changed["03_productivity.csv"]})
            swapped.append(key)
        return real_head(target, key, moment=moment, deadline_seconds=deadline_seconds)

    monkeypatch.setattr(s3_small, "head_meta", head_after_swap)

    with pytest.raises(SourceNotReady) as caught:
        _source(store, endpoint).fetch()
    assert caught.value.word == PLACING_WORD


def test_the_total_size_is_capped(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    _place(store, template_files())
    monkeypatch.setattr(drive, "PACK_MAX_BYTES", 300)

    with pytest.raises(SourceFailure) as caught:
        _source(store, endpoint).fetch()

    assert caught.value.reason == TOO_LARGE


def test_a_refused_key_stops_at_the_first_file(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    _place(store, template_files())

    with pytest.raises(SourceFailure) as caught:
        _source(store, endpoint, secret="wrong-secret").fetch()

    assert caught.value.reason == "인증 거절"
    assert len(store.requests) == 1
    store.requests.clear()
    with pytest.raises(SourceFailure):
        _source(store, endpoint, secret="wrong-secret").head()
    assert len(store.requests) == 1


def test_an_unreachable_store_stops_at_the_first_request() -> None:
    store = MockStore()
    server, endpoint = start_mock(store)
    server.shutdown()
    server.server_close()

    with pytest.raises(SourceFailure) as caught:
        _source(store, endpoint).head()

    assert caught.value.reason == "주소에 닿지 못함"


def test_without_a_target_the_source_is_unavailable() -> None:
    source = DriveSource(lambda: None)

    with pytest.raises(SourceFailure) as caught:
        source.fetch()
    assert caught.value.reason == UNAVAILABLE
    # 개발 실행(`app.py` — 동기화 managed 아님)에는 닿을 곳이 없고 원천도 꽂히지 않는다.
    assert drive.app_target() is None
    assert installed_source() is None


def test_an_etag_the_store_does_not_give_is_unknown(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    _place(store, template_files())
    store.omit_etag = True

    assert _source(store, endpoint).fetch().etag is None
    with pytest.raises(SourceFailure) as caught:
        _source(store, endpoint).head()
    assert caught.value.reason == ETAG_UNKNOWN


def test_a_file_that_does_not_read_as_utf8_points_at_notepad(
    mock_s3: tuple[MockStore, str],
) -> None:
    """Excel 로 저장해 사용자 PC 에서 DRM 머리가 붙은 장 꼴(UTF-8 로 읽히지 않는 바이트) — 거절
    까닭이 메모장 「UTF-8」 저장을 가리킨다(DRM 의 첫 바이트 값은 사내 답에 없어 UTF-8 해독 실패로만
    가른다)."""
    store, endpoint = mock_s3
    files = template_files()
    files["01_process.csv"] = b"\x80\x81\xff\xfe" + files["01_process.csv"]
    _place(store, files)

    reading = read_pack_zip(_source(store, endpoint).fetch().data)

    assert not reading.accepted
    (problem,) = reading.problems
    assert problem.file == "01_process.csv" and NOT_UTF8_HINT in problem.reason


def test_a_sheet_csv_cannot_read_is_rejected_not_raised(mock_s3: tuple[MockStore, str]) -> None:
    """NUL 이 든 장(DRM · 저장 도구가 붙인 머리 꼴 — UTF-8 · CP949 로는 읽힘)과 칸 하나가 csv
    상한보다 큰 장은 예외가 아니라 V-01 거절이고 까닭이 메모장 「UTF-8」 저장을 가리킨다(검토
    extra-2)."""
    store, endpoint = mock_s3
    files = template_files()
    files["01_process.csv"] = files["01_process.csv"] + b"\x00\r\n"
    files["02_route.csv"] = files["02_route.csv"] + b"x" * 200_000 + b"\r\n"
    _place(store, files)

    reading = read_pack_zip(_source(store, endpoint).fetch().data)

    assert not reading.accepted
    reasons = {problem.file: problem.reason for problem in reading.problems}
    assert set(reasons) == {"01_process.csv", "02_route.csv"}
    assert reasons["01_process.csv"].startswith("NUL 글자가 들어 있음")
    assert reasons["02_route.csv"].startswith("CSV 로 읽히지 않음")
    assert all(NOT_UTF8_HINT in reason for reason in reasons.values())


def _applied(sha: str, version_no: int) -> ExtraProcessState:
    return ExtraProcessState(
        (
            Version(
                seq=1,
                kind=EXTRA_KIND_APPLY,
                version_no=version_no,
                sha256=sha,
                created_at=datetime(2026, 11, 20, 9, 0),
                s3_etag="set-old",
            ),
        )
    )


def test_changing_some_files_needs_the_version_raised(mock_s3: tuple[MockStore, str]) -> None:
    """여섯 가운데 일부만 바꾸고 `00_info.csv` 의 판을 올리지 않으면 판 번호 규칙이 거절한다 —
    올리면 새 판이다(나머지 장은 앞 판 그대로 한 판으로 읽는다)."""
    store, endpoint = mock_s3
    files = template_files()
    state = _applied(pack_sha256(bundle_pack_files(files)), 1)
    changed = edited(
        files,
        "03_productivity.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == BOND, "UPEH", "123"),
    )
    _place(store, changed)

    staged = stage_pack(state, _source(store, endpoint).fetch(), now=datetime(2026, 11, 20))
    assert staged.judgement is not None and staged.judgement.verdict == JUDGE_BACKWARD
    assert "00_info.csv 의 판 번호를 올려" in staged.judgement.reason

    _place(store, bump_version(changed, 2))
    staged = stage_pack(state, _source(store, endpoint).fetch(), now=datetime(2026, 11, 20))
    assert staged.judgement is not None and staged.judgement.verdict == JUDGE_APPLY
    assert staged.changes is not None and staged.changes.changed_cells > 0


def _admin_script(database: Path, store: MockStore, endpoint: str) -> str:
    return f"""
from pathlib import Path

import capa_simulation.components.extra_process_admin as admin
import capa_simulation.settings as settings
from capa_simulation.extra_process_drive import DriveSource
from capa_simulation.extra_process_intake import install_source
from capa_simulation.io.s3_small import S3Target
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.scenario_activation import bootstrap_latest_official_scenario

target = S3Target(
    endpoint_url={endpoint!r},
    bucket={store.bucket!r},
    region={store.region!r},
    access_key={store.access_key!r},
    secret_key={store.secret_key!r},
)
original_path = settings.DUCKDB_PATH
original_lock = admin.write_lock_reason
settings.DUCKDB_PATH = Path({str(database)!r})
admin.write_lock_reason = lambda: None
install_source(DriveSource(lambda: target))
try:
    bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    repository = get_scenario_repository(str(settings.DUCKDB_PATH))
    admin.render_extra_process_admin(repository, alert_tab="부대공정")
finally:
    install_source(None)
    admin.write_lock_reason = original_lock
    settings.DUCKDB_PATH = original_path
"""


def test_the_admin_tab_imports_and_applies_the_six_files_end_to_end(
    mock_s3: tuple[MockStore, str], tmp_path: Path
) -> None:
    """가짜 S3 에 놓인 여섯 장 → Admin 「부대공정」 「S3 Drive 에서 가져오기」 → 적용 — 판 이력에
    묶은 ETag · `extra_process/` 가 남고, 다음 회차의 새 파일 감지(원천 머리 보기)가 그 파일을
    「같음」 으로 본다."""
    from alert_marks import active_state
    from streamlit.testing.v1 import AppTest

    from capa_simulation.components.extra_process_admin import (
        APPLY_BUTTON_KEY,
        IMPORT_BUTTON_KEY,
    )
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    store, endpoint = mock_s3
    files = template_files()
    _place(store, files)
    database = tmp_path / "drive_admin.duckdb"
    app = AppTest.from_string(_admin_script(database, store, endpoint), default_timeout=120)
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert active_state(app, "EP-02") is not None

    app.button(key=IMPORT_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert any("S3 Drive 적용 전 판 1" in str(item.value) for item in app.caption)

    app.button(key=APPLY_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    state = DuckDBScenarioRepository(database).load_extra_process_state()
    active = state.active
    assert active is not None and active.version_no == 1
    assert active.s3_key == DRIVE_PREFIX
    assert active.s3_etag == set_etag({name: etag_of(files[name]) for name in DRIVE_FILES})
    assert active.sha256 == pack_sha256(bundle_pack_files(files))
    assert active_state(app, "EP-02") is None
    assert any("S3 Drive 같음" in str(item.value) for item in app.caption)


def test_the_admin_tab_shows_a_nul_sheet_in_the_rejection_table(
    mock_s3: tuple[MockStore, str], tmp_path: Path
) -> None:
    """NUL 이 든 장을 놓고 Admin 「부대공정」 「S3 Drive 에서 가져오기」 를 누르면 탭이 예외로
    멈추지 않고 거절 표(V-01)와 상태 줄 「거절」 이 선다(검토 extra-2)."""
    from alert_marks import flashed
    from streamlit.testing.v1 import AppTest

    from capa_simulation.components.extra_process_admin import IMPORT_BUTTON_KEY

    store, endpoint = mock_s3
    files = template_files()
    files["01_process.csv"] = files["01_process.csv"] + b"\x00\r\n"
    _place(store, files)
    app = AppTest.from_string(
        _admin_script(tmp_path / "drive_nul.duckdb", store, endpoint), default_timeout=120
    )
    app.run()
    assert not app.exception, [item.message for item in app.exception]

    app.button(key=IMPORT_BUTTON_KEY).click().run()

    assert not app.exception, [item.message for item in app.exception]
    table = next(frame.value for frame in app.dataframe if "까닭" in frame.value)
    assert list(table["규칙"]) == ["V-01"] and list(table["파일"]) == ["01_process.csv"]
    assert NOT_UTF8_HINT in str(table.loc[0, "까닭"])
    assert any("S3 Drive 거절" in str(item.value) for item in app.caption)
    assert not [note for note in flashed(app, "error") if "가져오지 못했습니다" in str(note.value)]


def test_on_a_managed_server_the_default_source_reaches_the_started_keys(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-DEP 꼴(동기화 `managed` + 기동 때 읽은 S3 명단 키)에서는 꽂힌 기본 원천이 닿을 곳을 스스로
    고른다 — 시험이 닿을 곳을 주지 않아도 받는다."""
    from capa_simulation.auth import names, runtime
    from capa_simulation.io import object_storage

    store, endpoint = mock_s3
    for name, value in {
        names.ENV_S3_ACCESS_KEY: store.access_key,
        names.ENV_S3_SECRET_KEY: store.secret_key,
        names.ENV_S3_ENDPOINT: endpoint,
        names.ENV_S3_BUCKET: store.bucket,
        names.ENV_S3_REGION: store.region,
        object_storage.MODE_ENV: object_storage.MODE_MANAGED,
    }.items():
        monkeypatch.setenv(name, value)
    runtime.reset()
    try:
        files = template_files()
        _place(store, files)
        target = drive.app_target()
        assert target is not None and target.bucket == store.bucket
        assert DriveSource().fetch().data == bundle_pack_files(files)
        monkeypatch.setenv(object_storage.MODE_ENV, "local")
        assert drive.app_target() is None
    finally:
        runtime.reset()


def test_the_production_entry_installs_the_drive_source() -> None:
    """C-DEP 진입 파일(`capa_server.py`)을 그대로 import 하면 S3 Drive 원천이 꽂힌다 — 런타임 전
    길이라 하위 프로세스에서 본다(통합인증 · 명단 환경변수는 빼서 꺼짐 기동)."""
    import json
    import os
    import subprocess

    script = (
        "import json, capa_server\n"
        "from capa_simulation.extra_process_intake import installed_source\n"
        "print(json.dumps(type(installed_source()).__name__))\n"
    )
    env = {
        key: value for key, value in os.environ.items() if not key.startswith(("CAPA_", "ADFS_"))
    }
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    done = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=PROJECT_ROOT,
        timeout=120,
        check=True,
    )
    assert json.loads(done.stdout.strip().splitlines()[-1]) == "DriveSource"
