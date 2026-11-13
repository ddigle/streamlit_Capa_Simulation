# Purpose: 관리자 행위의 감사 줄 — 명단 고침 · 토큰 · 지금 올리기 · 자동 갱신 · 운영 도구 조각.

from __future__ import annotations

import importlib.util
import json
import sys
import time
from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from s3_mock_runner import MockStoreRunner, mock_client
from sso_support import use_config
from streamlit.testing.v1 import AppTest

from capa_simulation.audit import layout, recorder
from capa_simulation.auth import access_store, names
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.identity import Identity
from capa_simulation.auth.tokens import issue_session
from capa_simulation.io import s3_small
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.auto_official_update import DEFAULT_CONFIG

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from s3_mock_store import MockStore, start_mock  # noqa: E402

ADMIN = "demo.admin"
USER = "demo.user"
OTHER = "demo.other"
JWT_LIKE = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJkZW1vLXRva2VuIn0.c2lnbmF0dXJlLWRlbW8tdmFsdWU"


@pytest.fixture()
def on() -> Iterator[None]:
    recorder.start(env="cdep", version="test", inst="abcabcabcabc")
    yield


@pytest.fixture()
def mock_s3() -> Iterator[tuple[MockStore, str]]:
    store = MockStore()
    server, endpoint = start_mock(store)
    yield store, endpoint
    server.shutdown()
    server.server_close()


def _started(store: MockStore, endpoint: str) -> SsoConfig:
    cfg = use_config(
        {
            names.ENV_ACCESS_ADMINS: ADMIN,
            names.ENV_ACCESS_USERS: "",
            names.ENV_S3_ACCESS_KEY: store.access_key,
            names.ENV_S3_SECRET_KEY: store.secret_key,
            names.ENV_S3_ENDPOINT: endpoint,
            names.ENV_S3_BUCKET: store.bucket,
            names.ENV_S3_REGION: store.region,
        }
    )
    access_store.read_at_start(cfg)
    return cfg


def _identity(cfg: SsoConfig, loginid: str) -> Identity:
    _, claims = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
    return Identity.from_claims(claims)


def _lines(event_prefix: str) -> list[dict[str, Any]]:
    return [line for line in recorder.take_pending() if line["ev"].startswith(event_prefix)]


def test_each_added_or_removed_person_is_one_line_with_the_target(
    on: None, mock_s3: tuple[MockStore, str]
) -> None:
    store, endpoint = mock_s3
    cfg = _started(store, endpoint)
    recorder.take_pending()

    access_store.save_changes(cfg, _identity(cfg, ADMIN), add=[USER, OTHER])
    added = _lines("user_")
    access_store.save_changes(cfg, _identity(cfg, ADMIN), remove=[USER])
    removed = _lines("user_")

    assert [(line["ev"], line.get("tgt", {}).get("id")) for line in added] == [
        ("user_created", OTHER),
        ("user_created", USER),
    ]
    created = [line for line in added if line["ev"] == "user_created"]
    assert [line["tgt"] for line in created] == [
        {"type": "loginid", "id": OTHER},
        {"type": "loginid", "id": USER},
    ]
    assert all(
        (line["actor"], line["verified"], line["out"]) == (ADMIN, True, "success")
        for line in created
    )
    assert created[0]["det"]["rev_to"] == created[0]["det"]["rev_from"] + 1
    assert [(line["ev"], line["tgt"]["id"]) for line in removed] == [("user_deleted", USER)]


def test_a_put_without_an_answer_is_an_unknown_outcome(
    on: None, mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = _started(store, endpoint)
    recorder.take_pending()
    store.answer_delay["PUT"] = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.1)

    with pytest.raises(s3_small.S3Failure):
        access_store.save_changes(cfg, _identity(cfg, ADMIN), add=[USER])

    (line,) = [line for line in recorder.take_pending() if line["ev"] == "user_created"]
    assert (line["out"], line["tgt"]["id"]) == ("unknown", USER)


TOKEN_SCRIPT = """
import streamlit as st

from capa_simulation.components import bdq_token_admin

st.session_state["refusal"] = bdq_token_admin.install_from_dialog(st.session_state["raw"])
"""


def test_the_token_line_has_the_result_and_expiry_but_never_the_token(
    on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from capa_simulation.components import bdq_token_admin, sso_identity
    from capa_simulation.io import bdq_token

    monkeypatch.setattr(sso_identity, "viewer_is_admin", lambda: True)
    outcomes = iter(
        [
            bdq_token.InstallOutcome("installed"),
            bdq_token.InstallOutcome("same"),
            bdq_token.InstallOutcome("refused", "짧음"),
        ]
    )
    monkeypatch.setattr(bdq_token, "install_token", lambda raw: next(outcomes))
    expires = datetime(2026, 11, 14, 1, 2, 3, tzinfo=timezone.utc)
    monkeypatch.setattr(
        bdq_token_admin, "read_current", lambda: SimpleNamespace(expires_at=expires)
    )

    for _ in range(3):
        app = AppTest.from_string(TOKEN_SCRIPT)
        app.session_state["raw"] = JWT_LIKE
        app.run()
        assert not list(app.exception)

    lines = [line for line in recorder.take_pending() if line["ev"] == "admin_token_set"]
    assert [(line["out"], line["det"]["result"]) for line in lines] == [
        ("success", "installed"),
        ("success", "same"),
        ("fail", "refused"),
    ]
    assert lines[0]["det"]["expires"] == "2026-11-14T01:02:03.000Z"
    payload = json.dumps(lines, ensure_ascii=False)
    assert JWT_LIKE not in payload and JWT_LIKE[:20] not in payload


UPLOAD_SCRIPT = """
from capa_simulation.components import object_sync_status

object_sync_status._upload_now()
"""


@pytest.mark.parametrize(
    ("admin", "worker", "expected"),
    [
        (False, None, ("denied", "not_admin")),
        (True, None, ("fail", "no_worker")),
        (True, SimpleNamespace(request_now=lambda: None), ("success", "requested")),
    ],
)
def test_upload_now_is_recorded_with_its_result(
    on: None,
    monkeypatch: pytest.MonkeyPatch,
    admin: bool,
    worker: object,
    expected: tuple[str, str],
) -> None:
    from capa_simulation import object_sync_worker
    from capa_simulation.components import object_sync_status

    monkeypatch.setattr(object_sync_status, "_viewer_is_admin", lambda: admin)
    monkeypatch.setattr(object_sync_worker, "running_worker", lambda: worker)

    app = AppTest.from_string(UPLOAD_SCRIPT).run()

    assert not list(app.exception)
    (line,) = [line for line in recorder.take_pending() if line["ev"] == "admin_sync_push"]
    assert (line["out"], line["det"]["result"]) == expected


def test_auto_update_settings_name_the_fields_and_versions_without_values(
    on: None, tmp_path: Path
) -> None:
    recorder.set_resolver(lambda: recorder.Actor(ADMIN, True, "admin"))
    repository = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    repository.initialize()
    changed = replace(DEFAULT_CONFIG, enabled=True, keyword="DEMO_KEYWORD")

    repository.replace_auto_official_update_settings(
        changed, expected_version=0, changed_by="손 입력 이름"
    )
    with pytest.raises(ValueError):
        repository.replace_auto_official_update_settings(changed, expected_version=0)

    lines = [line for line in recorder.take_pending() if line["ev"] == "admin_auto_update_settings"]
    assert [line["out"] for line in lines] == ["success", "fail"]
    first = lines[0]
    assert first["det"] == {"fields": ["enabled", "keyword"], "version_from": 0, "version_to": 1}
    assert first["claimed"] == "손 입력 이름"
    assert first["actor"] == ADMIN
    assert "DEMO_KEYWORD" not in json.dumps(lines, ensure_ascii=False)


# ------------------------------------------------------------------ 운영 도구
def _load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "sync_object_storage.py"
    spec = importlib.util.spec_from_file_location("sync_object_storage_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def tool(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[ModuleType, MockStore]]:
    store, endpoint = mock_s3
    script = _load_script()
    runner = MockStoreRunner(
        endpoint, store.bucket, store.region, store.access_key, store.secret_key
    )
    monkeypatch.setenv("CAPA_S3_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("CAPA_S3_BUCKET", store.bucket)
    monkeypatch.setenv("CAPA_S3_PROFILE", "demo-profile")
    monkeypatch.setattr(script, "build_client", lambda _args: mock_client(runner))
    monkeypatch.setattr(script.sync_state, "enable", lambda _paths: None)
    yield script, store


def _tool_lines(store: MockStore) -> list[dict[str, Any]]:
    keys = sorted(key for key in store.objects if key.startswith(layout.TOOL_PREFIX))
    return [line for key in keys for line in layout.decode_lines(store.objects[key])]


def test_a_rollback_leaves_one_unverified_tool_piece(
    tool: tuple[ModuleType, MockStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    script, store = tool
    monkeypatch.setattr(script.engine, "rollback", lambda *_a, **_k: SimpleNamespace(seq=7))

    assert script.main(["rollback", "--to", "5", "--yes"]) == 0

    (line,) = _tool_lines(store)
    assert (line["ev"], line["env"], line["out"], line["verified"]) == (
        "admin_sync_rollback",
        "tool",
        "success",
        False,
    )
    assert line["det"] == {"seq_from": 5, "seq_to": 7, "result": "ok"}
    assert line["actor"] and not line["actor"].startswith("system:")
    assert (line["seq"], line["prev"]) == (1, "0" * 64)
    assert not recorder.enabled(), "도구는 기록기를 켜지 않는다"


def test_a_skipped_or_failed_tool_command(
    tool: tuple[ModuleType, MockStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    script, store = tool

    assert script.main(["rollback", "--to", "5"]) == 0
    assert _tool_lines(store) == []

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise ValueError("그 세대는 없습니다")

    monkeypatch.setattr(script.engine, "rollback", refuse)
    assert script.main(["rollback", "--to", "99", "--yes"]) == 1
    (line,) = _tool_lines(store)
    assert (line["out"], line["det"]) == ("fail", {"result": "fail"})


def test_audit_list_counts_pieces_without_names(
    tool: tuple[ModuleType, MockStore], capsys: pytest.CaptureFixture[str]
) -> None:
    script, store = tool
    store.put(layout.piece_key("seg", "2026-11-13", "aaaaaaaaaaaa", 1, 5), b"x")
    store.put(layout.piece_key("tool", "2026-11-13", "bbbbbbbbbbbb", 1, 1), b"x")
    store.put(layout.daily_key("2026-11-12", 0), b"x")

    assert script.main(["audit-list", "--date", "2026-11-13"]) == 0
    printed = capsys.readouterr().out
    assert "2026-11-13 : 조각 seg 1 · tool 1 · 일별 없음" in printed
    assert "aaaaaaaaaaaa" not in printed

    assert script.main(["audit-list", "--month", "2026-11"]) == 0
    printed = capsys.readouterr().out
    assert "2026-11-12 : 조각 seg 0 · tool 0 · 일별 있음" in printed
    assert "합계 : 30일 가운데 기록 있는 날 2" in printed
