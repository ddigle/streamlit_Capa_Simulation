# Purpose: BDQ 자동 로그인 저장 객체(키 · 암호화 · S3 · 멈춤 표시 · 기억 · 저장 경계)를 검증한다.

"""`io/bdq_login_store.py` 시험.

S3 는 서명을 검증하는 가짜 저장소(`scripts/s3_mock_store.py`)다. 값은 모두 합성이고 비밀번호는
카나리아 글이라 객체 본문 · repr · 결과에 새는지 바로 찾는다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from bdq_login_support import (
    ACCOUNT,
    ADMIN_ID,
    OTHER_ACCOUNT,
    PASSWORD,
    new_key,
    requests_on,
    running_mock,
    switch_on,
    target_of,
)
from cryptography.fernet import Fernet
from object_store_fakes import FakeStore, fake_client
from s3_mock_store import MockStore

from capa_simulation import module_helpers
from capa_simulation import object_sync_engine as engine
from capa_simulation.audit import layout as audit_layout
from capa_simulation.io import bdq_login, s3_small
from capa_simulation.io import bdq_login_store as store
from capa_simulation.io.bdq_login_store import LoginSecret
from capa_simulation.io.container_start_report import BDQ_USER_NAME_ENV
from capa_simulation.io.s3_small import S3Target
from capa_simulation.services import object_storage_manifest as manifest

SECRET = LoginSecret(ACCOUNT, PASSWORD)


@pytest.fixture(autouse=True)
def _fresh_state() -> Iterator[None]:
    bdq_login.forget_state()
    yield
    bdq_login.forget_state()


@pytest.fixture()
def mock_s3() -> Iterator[tuple[MockStore, S3Target]]:
    with running_mock() as (mock, endpoint):
        yield mock, target_of(mock, endpoint)


def stored_document(mock: MockStore) -> dict[str, object]:
    with mock.lock:
        body = mock.objects[store.OBJECT_KEY]
    data = json.loads(body)
    assert isinstance(data, dict)
    return data


# --- 키 · 켜짐 -----------------------------------------------------------------------------


def test_a_generated_key_is_valid_and_other_text_is_not() -> None:
    assert store.valid_key_text(new_key())
    assert store.valid_key_text(f"  {new_key()}\n")
    for text in ("", "short", "A" * 44, "=" * 44, new_key()[:-1], new_key() + "A", "가" * 44):
        assert not store.valid_key_text(text), text


def test_availability_needs_managed_and_a_well_formed_key(monkeypatch: pytest.MonkeyPatch) -> None:
    assert store.availability({}) == store.REASON_NOT_MANAGED
    managed = {"CAPA_S3_SYNC_MODE": "managed"}
    assert store.availability(managed) == store.REASON_NO_KEY
    assert (
        store.availability({**managed, store.SECRET_KEY_ENV: "not-a-key"}) == store.REASON_BAD_KEY
    )
    assert store.availability({**managed, store.SECRET_KEY_ENV: new_key()}) is None
    assert store.availability({"CAPA_S3_SYNC_MODE": "bogus", store.SECRET_KEY_ENV: new_key()}) == (
        store.REASON_NOT_MANAGED
    )
    assert store.secret_key({store.SECRET_KEY_ENV: "not-a-key"}) is None
    switch_on(monkeypatch)
    assert store.availability() is None


# --- 암호화 ------------------------------------------------------------------------------


def test_encrypt_and_decrypt_go_round_and_hide_the_values() -> None:
    key = new_key().encode()
    cipher = store.encrypt_secret(SECRET, key)
    assert PASSWORD not in cipher and ACCOUNT not in cipher
    back = store.decrypt_secret(cipher, key)
    assert back == SECRET
    assert back is not None
    assert back.account == ACCOUNT and back.password == PASSWORD


def test_a_wrong_key_or_a_damaged_cipher_is_none_without_an_exception() -> None:
    key = new_key().encode()
    cipher = store.encrypt_secret(SECRET, key)
    assert store.decrypt_secret(cipher, new_key().encode()) is None
    assert store.decrypt_secret(cipher[:-4] + "AAAA", key) is None
    assert store.decrypt_secret("가나다", key) is None
    assert store.decrypt_secret("", key) is None


@pytest.mark.parametrize(
    "plain",
    [
        f"not json {PASSWORD}".encode(),
        json.dumps([ACCOUNT, PASSWORD]).encode(),
        json.dumps({"account": ACCOUNT}).encode(),
        json.dumps({"account": ACCOUNT, "password": ""}).encode(),
        json.dumps({"account": 7, "password": PASSWORD}).encode(),
        b"\xff\xfe" + PASSWORD.encode(),
    ],
)
def test_a_decrypted_body_of_another_shape_is_none(plain: bytes) -> None:
    key = new_key().encode()
    cipher = Fernet(key).encrypt(plain).decode()
    assert store.decrypt_secret(cipher, key) is None


def test_the_values_never_show_in_a_repr_or_str() -> None:
    key = new_key().encode()
    stored = store.StoredLogin(
        SECRET, store.encrypt_secret(SECRET, key), "de", store.kst_text(), store.STATE_OK
    )
    loaded = store.LoadResult(stored)
    written = store.WriteResult(True, stored=stored)
    for text in (repr(SECRET), str(SECRET), repr(stored), str(stored), repr(loaded), repr(written)):
        assert PASSWORD not in text and ACCOUNT not in text, text
        assert stored.cipher not in text


def test_kst_text_and_the_entered_by_mark() -> None:
    moment = datetime(2026, 11, 16, 1, 2, 3, tzinfo=timezone.utc)
    assert store.kst_text(moment) == "2026-11-16T10:02:03+09:00"
    assert store.entered_by_mark(f"  {ADMIN_ID} ") == ADMIN_ID[:2]
    assert store.entered_by_mark("x") == "x"


# --- S3 읽기 · 쓰기 -------------------------------------------------------------------------


def test_save_then_load_goes_round_and_the_body_holds_only_the_cipher(
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    mock, target = mock_s3
    key = new_key().encode()
    moment = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
    written = store.save_login(target, key, SECRET, ADMIN_ID, at=moment)
    assert written.ok and written.stored is not None
    with mock.lock:
        body = mock.objects[store.OBJECT_KEY]
    assert PASSWORD.encode() not in body and ACCOUNT.encode() not in body
    assert ADMIN_ID.encode() not in body
    data = stored_document(mock)
    assert data == {
        "v": 1,
        "cipher": written.stored.cipher,
        "entered_by": ADMIN_ID[:2],
        "entered_at": "2026-11-16T09:00:00+09:00",
        "state": "ok",
        "stop_reason": None,
        "stopped_at": None,
    }
    loaded = store.load(target, key)
    assert loaded.reason == "" and loaded.stored is not None
    assert loaded.stored.secret == SECRET
    assert loaded.stored.state == store.STATE_OK and not loaded.stored.stopped
    assert loaded.stored.entered_by == ADMIN_ID[:2]


def test_without_a_key_nothing_asks_the_store(mock_s3: tuple[MockStore, S3Target]) -> None:
    mock, target = mock_s3
    assert store.load(target, None) == store.LoadResult(None, store.REASON_NO_KEY)
    assert mock.requests == []


def test_each_unusable_object_is_simply_no_stored_login(
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    mock, target = mock_s3
    key = new_key().encode()
    assert store.load(target, key).reason == store.REASON_NO_OBJECT
    mock.put(store.OBJECT_KEY, b"{not json")
    assert store.load(target, key) == store.LoadResult(None, store.REASON_BROKEN)
    mock.put(store.OBJECT_KEY, b"[]")
    assert store.load(target, key).reason == store.REASON_BROKEN
    store.save_login(target, key, SECRET, ADMIN_ID)
    document = stored_document(mock)
    for change, reason in (
        ({"v": 2}, store.REASON_VERSION),
        ({"v": True}, store.REASON_BROKEN),
        ({"state": "paused"}, store.REASON_BROKEN),
        ({"cipher": ""}, store.REASON_BROKEN),
        ({"stop_reason": "Bad Reason!"}, store.REASON_BROKEN),
        ({"entered_at": 3}, store.REASON_BROKEN),
    ):
        mock.put(store.OBJECT_KEY, json.dumps({**document, **change}).encode())
        assert store.load(target, key) == store.LoadResult(None, reason), change
    mock.put(store.OBJECT_KEY, json.dumps(document).encode())
    assert store.load(target, new_key().encode()) == store.LoadResult(
        None, store.REASON_UNDECRYPTABLE
    )
    assert store.load(target, key).stored is not None


def test_a_store_that_cannot_be_read_is_unread_with_its_kind(
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    _, target = mock_s3
    wrong = S3Target(
        endpoint_url=target.endpoint_url,
        bucket=target.bucket,
        region=target.region,
        access_key=target.access_key,
        secret_key="demo-wrong-secret-key",
    )
    loaded = store.load(wrong, new_key().encode())
    assert loaded.stored is None
    assert loaded.reason == store.REASON_UNREAD
    assert loaded.failure_kind == s3_small.KIND_AUTH


def test_the_stop_mark_keeps_the_cipher_and_rewrites_only_the_meta(
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    mock, target = mock_s3
    key = new_key().encode()
    written = store.save_login(target, key, SECRET, ADMIN_ID)
    assert written.stored is not None
    before = stored_document(mock)
    moment = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)
    marked = store.mark_stopped(target, "token_unchanged", cipher=written.stored.cipher, at=moment)
    assert marked.ok
    after = stored_document(mock)
    assert after["cipher"] == before["cipher"]
    assert after["entered_by"] == before["entered_by"]
    assert after["entered_at"] == before["entered_at"]
    assert after["state"] == "stopped"
    assert after["stop_reason"] == "token_unchanged"
    assert after["stopped_at"] == "2026-11-16T12:00:00+09:00"
    loaded = store.load(target, key)
    assert loaded.stored is not None and loaded.stored.stopped
    assert loaded.stored.secret == SECRET
    memo = store.current()
    assert memo is not None and memo.stopped and memo.stop_reason == "token_unchanged"


def test_the_stop_mark_leaves_a_newer_login_alone(mock_s3: tuple[MockStore, S3Target]) -> None:
    mock, target = mock_s3
    key = new_key().encode()
    first = store.save_login(target, key, SECRET, ADMIN_ID)
    assert first.stored is not None
    store.save_login(target, key, LoginSecret(OTHER_ACCOUNT, PASSWORD), ADMIN_ID)
    with mock.lock:
        body = mock.objects[store.OBJECT_KEY]
    marked = store.mark_stopped(target, "token_unchanged", cipher=first.stored.cipher)
    assert marked == store.WriteResult(False, store.WRITE_CHANGED)
    with mock.lock:
        assert mock.objects[store.OBJECT_KEY] == body
    assert store.mark_stopped(target, "Bad!", cipher="x").reason == store.WRITE_BAD_INPUT
    store.delete_login(target)
    assert store.mark_stopped(target, "token_unchanged", cipher="x").reason == store.WRITE_GONE


def test_delete_removes_the_object_and_the_memo(mock_s3: tuple[MockStore, S3Target]) -> None:
    mock, target = mock_s3
    key = new_key().encode()
    store.save_login(target, key, SECRET, ADMIN_ID)
    assert store.current() is not None
    assert store.delete_login(target).ok
    with mock.lock:
        assert store.OBJECT_KEY not in mock.objects
    assert store.current() is None
    assert store.delete_login(target).ok
    assert requests_on(mock, store.OBJECT_KEY).count("DELETE") == 2


def test_s3_small_delete_object_accepts_a_missing_key_and_raises_on_refusal(
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    mock, target = mock_s3
    mock.put("secrets/demo.json", b"{}")
    s3_small.delete_object(target, "secrets/demo.json")
    s3_small.delete_object(target, "secrets/demo.json")
    with mock.lock:
        assert "secrets/demo.json" not in mock.objects
    mock.force["DELETE"] = (403, "AccessDenied")
    with pytest.raises(s3_small.S3Failure) as caught:
        s3_small.delete_object(target, "secrets/demo.json")
    assert caught.value.kind == s3_small.KIND_AUTH


def test_a_write_failure_keeps_the_memo(mock_s3: tuple[MockStore, S3Target]) -> None:
    mock, target = mock_s3
    key = new_key().encode()
    store.save_login(target, key, SECRET, ADMIN_ID)
    mock.force["PUT"] = (500, "InternalError")
    failed = store.save_login(target, key, LoginSecret(OTHER_ACCOUNT, PASSWORD), ADMIN_ID)
    assert not failed.ok and failed.reason == store.WRITE_FAILED
    assert failed.failure_kind == s3_small.KIND_OTHER
    memo = store.current()
    assert memo is not None and memo.secret.account == ACCOUNT


# --- 앱 프로세스 기억 · 계정 원천 -------------------------------------------------------------


def test_the_app_reads_once_and_the_account_source_follows_the_memo(
    monkeypatch: pytest.MonkeyPatch, mock_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setenv(BDQ_USER_NAME_ENV, "demo_env_user")
    monkeypatch.setattr(store, "app_target", lambda: target)
    assert store.effective_account() == "demo_env_user"
    reads = requests_on(mock, store.OBJECT_KEY)
    assert reads == ["GET"]
    for _ in range(3):
        assert store.effective_account() == "demo_env_user"
    assert requests_on(mock, store.OBJECT_KEY) == reads
    store.save_login(target, key.encode(), SECRET, ADMIN_ID)
    assert store.effective_account() == ACCOUNT
    store.save_login(target, key.encode(), LoginSecret(OTHER_ACCOUNT, PASSWORD), ADMIN_ID)
    assert store.effective_account() == OTHER_ACCOUNT
    store.forget_state()
    assert store.effective_account() == OTHER_ACCOUNT
    store.delete_login(target)
    assert store.effective_account() == "demo_env_user"


def test_switched_off_the_app_never_asks_the_store(
    monkeypatch: pytest.MonkeyPatch, mock_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = mock_s3
    monkeypatch.setattr(store, "app_target", lambda: target)
    monkeypatch.setenv(BDQ_USER_NAME_ENV, "demo_env_user")
    assert store.load_state() == store.LoadResult(None, store.REASON_NOT_MANAGED)
    monkeypatch.setenv("CAPA_S3_SYNC_MODE", "managed")
    store.forget_state()
    assert store.load_state().reason == store.REASON_NO_KEY
    monkeypatch.setenv(store.SECRET_KEY_ENV, "not-a-key")
    store.forget_state()
    assert store.load_state().reason == store.REASON_BAD_KEY
    assert store.effective_account() == "demo_env_user"
    assert mock.requests == []


def test_an_unread_store_is_retried_later_not_remembered(
    monkeypatch: pytest.MonkeyPatch, mock_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    store.save_login(target, key.encode(), SECRET, ADMIN_ID)
    store.forget_state()
    mock.force["GET"] = (500, "InternalError")
    assert store.load_state().reason == store.REASON_UNREAD
    assert store.load_state().reason == store.REASON_UNREAD
    assert requests_on(mock, store.OBJECT_KEY).count("GET") == 1
    del mock.force["GET"]
    monkeypatch.setattr(store, "UNREAD_RETRY_SECONDS", 0.0)
    assert store.current() is not None
    assert requests_on(mock, store.OBJECT_KEY).count("GET") == 2


def test_account_of_prefers_the_stored_login() -> None:
    stored = store.StoredLogin(SECRET, "c", "de", "t", store.STATE_STOPPED)
    assert store.account_of(stored, {BDQ_USER_NAME_ENV: "demo_env_user"}) == ACCOUNT
    assert store.account_of(None, {BDQ_USER_NAME_ENV: " demo_env_user "}) == "demo_env_user"
    assert store.account_of(None, {}) == ""


# --- 저장 경계 ---------------------------------------------------------------------------


def test_the_object_sits_outside_every_sync_audit_and_module_prefix() -> None:
    assert store.OBJECT_KEY.startswith(store.SECRETS_PREFIX)
    others = (
        *manifest.PRUNE_PREFIXES,
        manifest.HEAD_PREFIX,
        *(manifest.snapshot_prefix(name) for name in manifest.DATASET_NAMES),
        *(manifest.writer_key(name) for name in manifest.DATASET_NAMES),
        audit_layout.PREFIX,
        module_helpers.S3_KEY_PREFIX,
        "access/",
    )
    for prefix in others:
        assert prefix, "빈 접두는 버킷 전체를 덮는다"
        assert not store.OBJECT_KEY.startswith(prefix), prefix
        assert not prefix.startswith(store.SECRETS_PREFIX), prefix


@pytest.mark.parametrize(
    "name",
    [
        "../secrets/bdq_login.json",
        "..",
        "a/../../secrets/bdq_login.json",
        "/secrets/bdq_login.json",
        "secrets/../../secrets/bdq_login.json",
        "./x",
        "a\\..\\secrets",
    ],
)
def test_module_s3_names_cannot_climb_to_the_secret(name: str) -> None:
    assert not module_helpers.valid_s3_name(name)


def test_every_module_key_stays_under_its_module_folder() -> None:
    for name in ("data.csv", "a/b/c.json", "secrets/bdq_login.json"):
        assert module_helpers.valid_s3_name(name)
        key = module_helpers.s3_object_key("demo_mod", name)
        assert key.startswith(f"{module_helpers.S3_KEY_PREFIX}demo_mod/")
        assert key != store.OBJECT_KEY


def test_the_daily_prune_neither_lists_nor_deletes_the_secret() -> None:
    fake = FakeStore()
    fake.objects[store.OBJECT_KEY] = b'{"v": 1}'
    fake.objects["simulation/snapshots/orphan.duckdb.gz"] = b"x"
    fake.modified["simulation/snapshots/orphan.duckdb.gz"] = "2026-01-01T00:00:00+00:00"
    engine.prune(fake_client(fake), keep_days=1, include_orphans=True)
    assert store.OBJECT_KEY in fake.objects
    for call in fake.calls:
        args = list(call)
        if "--prefix" in args:
            prefix = args[args.index("--prefix") + 1]
            assert prefix and not store.OBJECT_KEY.startswith(prefix), call
        if "--key" in args:
            assert not args[args.index("--key") + 1].startswith(store.SECRETS_PREFIX), call
