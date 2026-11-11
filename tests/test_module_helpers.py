# Purpose: 모듈 창구 도우미(BigDataQuery 조회 · S3 올리기 · 받기)의 길 · 거절 · 쓸 수 없음을 본다.

"""창구 1.3 도우미(2026-11-12 사용자 결정 「도우미 함수로」).

S3 는 서명을 검증하는 가짜 S3(`scripts/s3_mock_store.py`)로 견본 모듈 `demo_ok` 의 데이터 자리를
왕복한다. BigDataQuery 는 사내 패키지 대신 `getData` 를 흉내 낸 대역을 끼운다. 값은 모두 합성이다.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation import module_api, module_helpers, module_registry
from capa_simulation.auth import names, runtime
from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.io import object_storage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_OK_PAGE = PROJECT_ROOT / "tests" / "fixtures" / "modules" / "demo_ok" / "demo_ok_page.py"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from s3_mock_store import MockStore, start_mock  # noqa: E402

KEY_PREFIX = "modules/demo_ok/"


@pytest.fixture()
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "module-data"
    monkeypatch.setenv(module_registry.DATA_ROOT_ENV_VAR, str(root))
    monkeypatch.delenv(module_registry.TEST_RUN_ENV_VAR, raising=False)
    monkeypatch.delenv(object_storage.MODE_ENV, raising=False)
    return root


@pytest.fixture()
def ctx(data_root: Path) -> module_api.ModuleContext:
    return module_api.context(DEMO_OK_PAGE)


@pytest.fixture()
def store(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MockStore]:
    """운영 서버 꼴 — 동기화 모드 `managed` 와 접속 명단과 같은 S3 값 한 벌(가짜 S3)."""
    mock = MockStore()
    server, endpoint = start_mock(mock)
    values = {
        names.ENV_S3_ACCESS_KEY: mock.access_key,
        names.ENV_S3_SECRET_KEY: mock.secret_key,
        names.ENV_S3_ENDPOINT: endpoint,
        names.ENV_S3_BUCKET: mock.bucket,
        names.ENV_S3_REGION: mock.region,
        object_storage.MODE_ENV: object_storage.MODE_MANAGED,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    runtime.reset()
    yield mock
    server.shutdown()
    runtime.reset()


# ------------------------------------------------------------------ S3 — 왕복


def test_a_file_goes_up_under_the_module_prefix_and_comes_back(
    ctx: module_api.ModuleContext, store: MockStore
) -> None:
    body = "월,값\n2026-01,10\n".encode()
    (ctx.data_dir / "demo.csv").write_bytes(body)
    (ctx.data_dir / "out" / "2026").mkdir(parents=True)
    (ctx.data_dir / "out" / "2026" / "rows.csv").write_bytes(b"a\n1\n")

    first = module_api.s3_upload(ctx, "demo.csv")
    second = module_api.s3_upload(ctx, "out/2026/rows.csv")

    assert first == module_api.S3Result(ok=True, size=len(body))
    assert second.ok and second.size == 4
    assert store.objects == {
        f"{KEY_PREFIX}demo.csv": body,
        f"{KEY_PREFIX}out/2026/rows.csv": b"a\n1\n",
    }

    (ctx.data_dir / "demo.csv").unlink()
    store.objects[f"{KEY_PREFIX}demo.csv"] = b"remote\n"
    (ctx.data_dir / "out" / "2026" / "rows.csv").write_bytes(b"old\n")

    assert module_api.s3_download(ctx, "demo.csv") == module_api.S3Result(ok=True, size=7)
    assert module_api.s3_download(ctx, "out/2026/rows.csv").ok
    assert (ctx.data_dir / "demo.csv").read_bytes() == b"remote\n"
    assert (ctx.data_dir / "out" / "2026" / "rows.csv").read_bytes() == b"a\n1\n"
    # 받기는 임시 파일에서 한 번에 바꾼다 — 남는 찌꺼기가 없다.
    assert sorted(path.name for path in ctx.data_dir.iterdir()) == ["demo.csv", "out"]


def test_a_download_into_a_new_folder_makes_the_folder(
    ctx: module_api.ModuleContext, store: MockStore
) -> None:
    store.objects[f"{KEY_PREFIX}backup/memo.csv"] = b"x\n"

    assert module_api.s3_download(ctx, "backup/memo.csv").ok
    assert (ctx.data_dir / "backup" / "memo.csv").read_bytes() == b"x\n"


def test_missing_files_on_either_side_are_named_and_the_local_file_stays(
    ctx: module_api.ModuleContext, store: MockStore
) -> None:
    (ctx.data_dir / "keep.csv").write_bytes(b"local\n")

    assert module_api.s3_upload(ctx, "absent.csv") == module_api.S3Result(False, "파일 없음")
    assert module_api.s3_download(ctx, "keep.csv") == module_api.S3Result(False, "파일 없음")
    assert (ctx.data_dir / "keep.csv").read_bytes() == b"local\n"


def test_a_file_over_the_limit_is_too_large_both_ways(
    ctx: module_api.ModuleContext, store: MockStore
) -> None:
    (ctx.data_dir / "big.bin").write_bytes(b"0" * (module_api.S3_MAX_BYTES + 1))
    store.objects[f"{KEY_PREFIX}huge.bin"] = b"0" * (module_api.S3_MAX_BYTES + 1)

    assert module_api.s3_upload(ctx, "big.bin").reason == "너무 큼"
    assert module_api.s3_download(ctx, "huge.bin").reason == "너무 큼"
    assert not (ctx.data_dir / "huge.bin").exists()
    assert f"{KEY_PREFIX}big.bin" not in store.objects


def test_a_refused_transfer_is_a_result_without_values(
    ctx: module_api.ModuleContext, store: MockStore, caplog: pytest.LogCaptureFixture
) -> None:
    (ctx.data_dir / "demo.csv").write_bytes(b"local\n")
    store.objects[f"{KEY_PREFIX}demo.csv"] = b"remote\n"
    store.secret_key = "demo-other-secret-key-for-the-mock"

    up = module_api.s3_upload(ctx, "demo.csv")
    down = module_api.s3_download(ctx, "demo.csv")

    assert up == module_api.S3Result(ok=False, reason="전송 실패", detail="인증 거절")
    assert down == up
    assert (ctx.data_dir / "demo.csv").read_bytes() == b"local\n"
    logged = caplog.text
    for value in (store.bucket, store.access_key, os.environ[names.ENV_S3_ENDPOINT]):
        assert value not in logged and value not in repr(up)


# ------------------------------------------------------------------ S3 — 이름 거절


@pytest.mark.parametrize(
    "name",
    [
        "",
        "../escape.csv",
        "a/../b.csv",
        "/etc/passwd",
        "C:/x.csv",
        "a\\b.csv",
        ".hidden",
        "a//b.csv",
        "a/b/c/d/e.csv",
        "x" * 201,
        "메모.csv",
        "a b.csv",
        None,
    ],
)
def test_names_outside_the_simple_shape_are_refused_before_any_request(
    ctx: module_api.ModuleContext, store: MockStore, name: Any
) -> None:
    assert module_api.s3_upload(ctx, name) == module_api.S3Result(False, "이름 거절")
    assert module_api.s3_download(ctx, name) == module_api.S3Result(False, "이름 거절")
    assert store.requests == []


@pytest.mark.skipif(sys.platform == "win32", reason="심볼릭 링크는 리눅스에서 본다")
def test_a_link_out_of_the_data_place_is_refused(
    ctx: module_api.ModuleContext, store: MockStore, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"x")
    (ctx.data_dir / "link.txt").symlink_to(outside / "secret.txt")
    (ctx.data_dir / "door").symlink_to(outside, target_is_directory=True)
    store.objects[f"{KEY_PREFIX}door/new.txt"] = b"y"

    assert module_api.s3_upload(ctx, "link.txt").reason == "이름 거절"
    assert module_api.s3_download(ctx, "door/new.txt").reason == "이름 거절"
    assert not (outside / "new.txt").exists()
    assert store.requests == []


def test_a_hand_made_context_with_a_bad_id_cannot_leave_its_prefix(
    ctx: module_api.ModuleContext, store: MockStore, data_root: Path
) -> None:
    forged = module_api.ModuleContext(
        id="../demo_other",
        name=ctx.name,
        owner=ctx.owner,
        maturity=ctx.maturity,
        folder=ctx.folder,
        api_version=ctx.api_version,
    )

    assert module_helpers.s3_upload(forged.id, ctx.data_dir, "demo.csv").reason == "이름 거절"
    # 창구는 데이터 자리(`ctx.data_dir` — 읽을 때 만든다)를 건드리기 전에 거절한다.
    assert module_api.s3_upload(forged, "demo.csv").reason == "이름 거절"
    assert module_api.s3_download(forged, "demo.csv").reason == "이름 거절"
    assert not (data_root.parent / "demo_other").exists()
    assert store.requests == []


# ------------------------------------------------------------------ S3 — 쓸 수 없음


def test_without_the_operating_server_values_it_is_unavailable(
    ctx: module_api.ModuleContext, store: MockStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    (ctx.data_dir / "demo.csv").write_bytes(b"x\n")

    monkeypatch.setenv(object_storage.MODE_ENV, "local")
    assert module_api.s3_upload(ctx, "demo.csv") == module_api.S3Result(
        False, "쓸 수 없음", "동기화 모드 managed 아님"
    )
    monkeypatch.delenv(object_storage.MODE_ENV)
    assert module_api.s3_download(ctx, "demo.csv").detail == "동기화 모드 managed 아님"

    monkeypatch.setenv(object_storage.MODE_ENV, object_storage.MODE_MANAGED)
    monkeypatch.delenv(names.ENV_S3_SECRET_KEY)
    runtime.reset()
    assert module_api.s3_upload(ctx, "demo.csv") == module_api.S3Result(
        False, "쓸 수 없음", "키 · 주소 · 버킷 없음"
    )
    monkeypatch.setenv(object_storage.MODE_ENV, "oops")
    assert module_api.s3_upload(ctx, "demo.csv").detail == "설정 읽기 실패"
    assert store.requests == []


def test_the_keys_come_from_the_started_config_not_the_environment(
    ctx: module_api.ModuleContext, store: MockStore
) -> None:
    """운영 진입 파일은 기동 때 키를 환경에서 뺀다 — 도우미는 처음 읽은 한 벌로 붙는다."""
    runtime.reset()
    runtime.start(os.environ)
    assert names.ENV_S3_SECRET_KEY not in os.environ
    (ctx.data_dir / "demo.csv").write_bytes(b"x\n")

    assert module_api.s3_upload(ctx, "demo.csv").ok


def test_inside_a_module_test_run_nothing_leaves_the_process(
    ctx: module_api.ModuleContext, store: MockStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(module_registry.TEST_RUN_ENV_VAR, "1")
    (ctx.data_dir / "demo.csv").write_bytes(b"x\n")

    assert module_api.s3_upload(ctx, "demo.csv") == module_api.S3Result(
        False, "쓸 수 없음", "모듈 시험"
    )
    assert module_api.s3_download(ctx, "demo.csv").detail == "모듈 시험"
    assert store.requests == []


# ------------------------------------------------------------------ BigDataQuery


class _FakePackage:
    """`bigdataquery` 대역 — 받은 인자를 적고 정한 답을 돌려준다."""

    def __init__(self, answer: object = None, error: BaseException | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.answer = pd.DataFrame({"값": [1]}) if answer is None else answer
        self.error = error

    def getData(self, **kwargs: object) -> object:  # noqa: N802 — 패키지 이름 그대로
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.answer


@pytest.fixture()
def package(monkeypatch: pytest.MonkeyPatch) -> _FakePackage:
    fake = _FakePackage()
    monkeypatch.setattr(adapter, "load_bigdataquery_module", lambda: fake)
    monkeypatch.delenv(module_registry.TEST_RUN_ENV_VAR, raising=False)
    monkeypatch.delenv(adapter.BDQ_USER_NAME_ENV, raising=False)
    return fake


def test_a_query_takes_the_apps_path_and_the_core_fills_the_requester(
    ctx: module_api.ModuleContext, package: _FakePackage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(adapter.BDQ_USER_NAME_ENV, "demo.requester")
    sql = "SELECT a FROM t WHERE d >= '{start_date}' AND d < '{end_date}' AND j = '{\"k\": 1}'"

    frame = module_api.query_bigdataquery(
        ctx, sql, start=date(2026, 1, 1), end=datetime(2026, 1, 31, 15, 0)
    )

    assert frame.equals(pd.DataFrame({"값": [1]}))
    [call] = package.calls
    assert call["param"] == (
        "SELECT a FROM t WHERE d >= '2026-01-01' AND d < '2026-02-01' AND j = '{\"k\": 1}'"
    )
    assert call["user_name"] == "demo.requester"
    assert call["convert_type"] is True


def test_an_empty_answer_is_an_empty_frame(
    ctx: module_api.ModuleContext, package: _FakePackage
) -> None:
    package.answer = pd.DataFrame({"값": []})

    assert module_api.query_bigdataquery(ctx, "SELECT 1").empty


@pytest.mark.parametrize(
    ("sql", "window"),
    [
        ("", {}),
        ("   ", {}),
        ("x" * (module_helpers.MAX_QUERY_CHARS + 1), {}),
        ("SELECT '{start_date}' , '{end_date}'", {}),
        ("SELECT 1", {"start": date(2026, 1, 1), "end": date(2026, 1, 2)}),
        ("SELECT '{start_date}'", {"start": date(2026, 1, 1), "end": date(2026, 1, 2)}),
        ("SELECT '{start_date}' '{end_date}'", {"start": date(2026, 1, 1)}),
        (
            "SELECT '{start_date}' '{end_date}'",
            {"start": date(2026, 2, 1), "end": date(2026, 1, 1)},
        ),
        (
            "SELECT '{start_date}' '{end_date}'",
            {"start": date(2025, 1, 1), "end": date(2026, 1, 2)},
        ),
        ("SELECT '{start_date}' '{end_date}'", {"start": "2026-01-01", "end": "2026-01-02"}),
    ],
)
def test_a_wrong_input_is_refused_before_asking(
    ctx: module_api.ModuleContext, package: _FakePackage, sql: str, window: dict[str, Any]
) -> None:
    with pytest.raises(module_api.BigDataQueryError) as caught:
        module_api.query_bigdataquery(ctx, sql, **window)

    assert caught.value.kind == "입력"
    assert package.calls == []


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (TimeoutError("read timed out"), adapter.QUERY_FAILURE_TIMEOUT),
        (ConnectionError("refused"), adapter.QUERY_FAILURE_CONNECTION),
        (RuntimeError("AnalysisException: syntax error"), adapter.QUERY_FAILURE_SQL),
        (RuntimeError("뭔지 모름"), adapter.QUERY_FAILURE_OTHER),
    ],
)
def test_a_failed_query_keeps_the_apps_failure_kind(
    ctx: module_api.ModuleContext,
    package: _FakePackage,
    caplog: pytest.LogCaptureFixture,
    error: BaseException,
    kind: str,
) -> None:
    package.error = error

    with pytest.raises(module_api.BigDataQueryError) as caught:
        module_api.query_bigdataquery(ctx, "SELECT secret_column FROM demo_table")

    assert caught.value.kind == kind
    assert f"BigDataQuery 조회가 실패했습니다({kind})" in str(caught.value)
    assert f"모듈 demo_ok BigDataQuery 실패 갈래={kind}" in caplog.text
    assert "secret_column" not in caplog.text


def test_a_missing_package_or_requester_is_unavailable(
    ctx: module_api.ModuleContext, package: _FakePackage, monkeypatch: pytest.MonkeyPatch
) -> None:
    package.error = RuntimeError("parameter user_name is necessary.")
    with pytest.raises(module_api.BigDataQueryError) as caught:
        module_api.query_bigdataquery(ctx, "SELECT 1")
    assert caught.value.kind == "쓸 수 없음"
    assert adapter.BDQ_USER_NAME_ENV in str(caught.value)

    def _absent() -> object:
        raise RuntimeError("현재 환경에 bigdataquery 패키지가 없습니다.")

    monkeypatch.setattr(adapter, "load_bigdataquery_module", _absent)
    with pytest.raises(module_api.BigDataQueryError) as missing:
        module_api.query_bigdataquery(ctx, "SELECT 1")
    assert missing.value.kind == "쓸 수 없음"


def test_a_non_frame_answer_is_the_other_kind(
    ctx: module_api.ModuleContext, package: _FakePackage
) -> None:
    package.answer = [1, 2]

    with pytest.raises(module_api.BigDataQueryError) as caught:
        module_api.query_bigdataquery(ctx, "SELECT 1")
    assert caught.value.kind == adapter.QUERY_FAILURE_OTHER


def test_inside_a_module_test_run_the_query_is_never_sent(
    ctx: module_api.ModuleContext, package: _FakePackage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(module_registry.TEST_RUN_ENV_VAR, "1")

    with pytest.raises(module_api.BigDataQueryError) as caught:
        module_api.query_bigdataquery(ctx, "SELECT 1")
    assert caught.value.kind == "쓸 수 없음"
    assert package.calls == []


# ------------------------------------------------------------------ 견본 화면


def test_the_demo_ok_buttons_report_unavailable_off_the_operating_server(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """운영 서버 밖(개발 · 시험)에서 견본 단추는 화면을 깨지 않고 「쓸 수 없음」 을 적는다."""
    monkeypatch.setenv(module_registry.TEST_RUN_ENV_VAR, "1")
    app = AppTest.from_file(str(DEMO_OK_PAGE)).run()

    app.button(key="mod_demo_ok__upload").click().run()
    assert app.session_state["mod_demo_ok__store"] == "쓸 수 없음"
    app.button(key="mod_demo_ok__ask").click().run()
    assert app.session_state["mod_demo_ok__query"] == "쓸 수 없음"
    assert not app.exception


def test_the_demo_ok_buttons_round_trip_through_the_store(
    store: MockStore, package: _FakePackage, data_root: Path
) -> None:
    app = AppTest.from_file(str(DEMO_OK_PAGE)).run()
    (data_root / "demo_ok" / "demo.csv").write_bytes(b"a\n1\n")

    app.button(key="mod_demo_ok__upload").click().run()
    assert app.session_state["mod_demo_ok__store"] == "올림"
    (data_root / "demo_ok" / "demo.csv").unlink()
    app.button(key="mod_demo_ok__download").click().run()
    assert app.session_state["mod_demo_ok__store"] == "받음"
    app.button(key="mod_demo_ok__ask").click().run()
    assert app.session_state["mod_demo_ok__query"] == "1행"

    assert not app.exception
    assert (data_root / "demo_ok" / "demo.csv").read_bytes() == b"a\n1\n"
    assert store.objects == {f"{KEY_PREFIX}demo.csv": b"a\n1\n"}
