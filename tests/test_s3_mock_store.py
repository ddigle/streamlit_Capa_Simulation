# Purpose: 가짜 S3 의 목록·지우기·메타데이터·실패 흉내가 서명을 지키며 저장소 꼴로 답하는지 본다.

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest

from capa_simulation.io.s3_small import canonical_request, credential_scope, signature_v4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from s3_mock_store import MockStore, start_mock  # noqa: E402

NAMESPACE = "{http://s3.amazonaws.com/doc/2006-03-01/}"
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.fixture()
def mock() -> Iterator[tuple[MockStore, str]]:
    store = MockStore()
    server, endpoint = start_mock(store)
    yield store, endpoint
    server.shutdown()
    server.server_close()


def _signed(
    store: MockStore, endpoint: str, method: str, path: str, query: str = ""
) -> urllib.request.Request:
    """`aws` 처럼 질의까지 서명한 요청."""
    amz_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    host = endpoint.removeprefix("http://")
    headers = {"host": host, "x-amz-content-sha256": EMPTY_SHA256, "x-amz-date": amz_date}
    canonical = canonical_request(method, path, query, headers, EMPTY_SHA256)
    signature = signature_v4(
        canonical, amz_date=amz_date, region=store.region, secret_key=store.secret_key
    )
    scope = credential_scope(amz_date, store.region)
    authorization = (
        f"AWS4-HMAC-SHA256 Credential={store.access_key}/{scope}, "
        f"SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature={signature}"
    )
    url = f"{endpoint}{path}{'?' + query if query else ''}"
    return urllib.request.Request(
        url,
        method=method,
        headers={
            "x-amz-content-sha256": EMPTY_SHA256,
            "x-amz-date": amz_date,
            "Authorization": authorization,
        },
    )


def _list(store: MockStore, endpoint: str, query: str) -> ElementTree.Element:
    request = _signed(store, endpoint, "GET", f"/{store.bucket}", query)
    with urllib.request.urlopen(request, timeout=5) as answer:
        return ElementTree.fromstring(answer.read())


def _keys(root: ElementTree.Element) -> list[str]:
    return [item.text or "" for item in root.iter(f"{NAMESPACE}Key")]


def test_listing_is_sorted_filtered_and_signed_with_its_query(
    mock: tuple[MockStore, str],
) -> None:
    store, endpoint = mock
    for key in ("b/2", "a/1", "b/1"):
        store.put(key, b"x")

    root = _list(store, endpoint, "encoding-type=url&list-type=2&prefix=b%2F")

    assert _keys(root) == ["b/1", "b/2"]


def test_listing_pages_with_a_continuation_token(mock: tuple[MockStore, str]) -> None:
    store, endpoint = mock
    for index in range(5):
        store.put(f"k/{index}", b"x")

    first = _list(store, endpoint, "list-type=2&max-keys=2&prefix=k%2F")
    token = first.findtext(f"{NAMESPACE}NextContinuationToken")
    second = _list(
        store, endpoint, f"continuation-token={token}&list-type=2&max-keys=2&prefix=k%2F"
    )

    assert first.findtext(f"{NAMESPACE}IsTruncated") == "true"
    assert _keys(first) == ["k/0", "k/1"]
    assert _keys(second) == ["k/2", "k/3"]


def test_a_changed_query_fails_the_signature(mock: tuple[MockStore, str]) -> None:
    store, endpoint = mock
    request = _signed(store, endpoint, "GET", f"/{store.bucket}", "list-type=2")
    tampered = urllib.request.Request(
        f"{endpoint}/{store.bucket}?list-type=2&prefix=x", headers=dict(request.headers)
    )

    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(tampered, timeout=5)

    assert caught.value.code == 403


def test_delete_answers_204_even_for_a_missing_key(mock: tuple[MockStore, str]) -> None:
    store, endpoint = mock
    store.put("a", b"x")

    for _ in range(2):
        request = _signed(store, endpoint, "DELETE", f"/{store.bucket}/a")
        with urllib.request.urlopen(request, timeout=5) as answer:
            assert answer.status == 204

    assert store.objects == {}


def test_objects_carry_a_time_the_test_can_set(mock: tuple[MockStore, str]) -> None:
    store, endpoint = mock
    moment = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    store.clock = lambda: moment
    store.put("a", b"x")

    root = _list(store, endpoint, "list-type=2")

    assert root.findtext(f"{NAMESPACE}Contents/{NAMESPACE}LastModified") == (
        "2026-11-01T00:00:00.000Z"
    )
    store.modified["a"] = moment - timedelta(days=9)
    head = _signed(store, endpoint, "HEAD", f"/{store.bucket}/a")
    with urllib.request.urlopen(head, timeout=5) as answer:
        assert answer.headers["Last-Modified"] == "Fri, 23 Oct 2026 00:00:00 GMT"


def test_a_fault_fires_after_its_count_on_its_prefix(mock: tuple[MockStore, str]) -> None:
    store, endpoint = mock
    store.put("a/1", b"x")
    store.force_on("GET", "a/", after=1, times=1, status=503, code="SlowDown")

    def get() -> int:
        request = _signed(store, endpoint, "GET", f"/{store.bucket}/a/1")
        try:
            with urllib.request.urlopen(request, timeout=5) as answer:
                return int(answer.status)
        except urllib.error.HTTPError as error:
            return error.code

    assert [get(), get(), get()] == [200, 503, 200]
