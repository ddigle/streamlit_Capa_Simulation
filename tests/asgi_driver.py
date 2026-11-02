# Purpose: httpx 없이 ASGI 앱을 직접 부르는 시험 도우미(http 요청·websocket 핸드셰이크).

"""ASGI 시험 운전기.

Starlette 의 `TestClient` 는 httpx 가 있어야 하는데 이 저장소의 의존성에는 httpx 가 없다(넣지
않는다). 그래서 ASGI 앱을 `asyncio` 로 직접 부른다 — 받은 메시지를 모아 상태 · 머리(여러 Set-Cookie)
· 본문으로 돌려준다. websocket 은 첫 응답 메시지가 `websocket.accept` 인지 `websocket.close` 인지만
본다(수락 전 닫으면 서버가 핸드셰이크에 HTTP 403 으로 답한다).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
App = Callable[[Scope, Receive, Send], Awaitable[None]]


@dataclass(frozen=True)
class SetCookie:
    name: str
    value: str
    attributes: Mapping[str, str]

    def has(self, attribute: str) -> bool:
        return attribute.lower() in self.attributes

    def get(self, attribute: str) -> str | None:
        return self.attributes.get(attribute.lower())

    @property
    def deleted(self) -> bool:
        return self.get("max-age") == "0"


def parse_set_cookie(header: str) -> SetCookie:
    first, *rest = [part.strip() for part in header.split(";")]
    name, _, value = first.partition("=")
    attributes: dict[str, str] = {}
    for part in rest:
        key, _, attr_value = part.partition("=")
        attributes[key.strip().lower()] = attr_value.strip()
    return SetCookie(name=name.strip(), value=value.strip(), attributes=attributes)


@dataclass(frozen=True)
class AsgiResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def header(self, name: str) -> str | None:
        for key, value in self.headers:
            if key == name.lower():
                return value
        return None

    def all_headers(self, name: str) -> list[str]:
        return [value for key, value in self.headers if key == name.lower()]

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    @property
    def set_cookies(self) -> list[SetCookie]:
        return [parse_set_cookie(value) for value in self.all_headers("set-cookie")]

    def cookie(self, name: str) -> SetCookie | None:
        found = [item for item in self.set_cookies if item.name == name]
        return found[-1] if found else None


def _scope_headers(headers: Mapping[str, str] | None) -> list[tuple[bytes, bytes]]:
    return [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]


def _split_target(target: str) -> tuple[str, str]:
    path, _, query = target.partition("?")
    return path, query


def http(
    app: App,
    method: str,
    target: str,
    *,
    headers: Mapping[str, str] | None = None,
    body: bytes = b"",
    chunks: list[bytes] | None = None,
) -> AsgiResponse:
    """요청 하나. `target` 은 경로(+ `?질의`, 퍼센트 인코딩 그대로).

    `chunks` 를 주면 본문을 나눠 보낸다(`Content-Length` 없이 흘려 보내는 요청).
    """
    return asyncio.run(
        _http(app, method, target, headers, chunks if chunks is not None else [body])
    )


async def _http(
    app: App,
    method: str,
    target: str,
    headers: Mapping[str, str] | None,
    chunks: list[bytes],
) -> AsgiResponse:
    raw_path, query = _split_target(target)
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": unquote(raw_path),
        "raw_path": raw_path.encode("ascii"),
        "query_string": query.encode("ascii"),
        "root_path": "",
        "headers": _scope_headers(headers),
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8581),
    }
    pending: list[Message] = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]

    async def receive() -> Message:
        if pending:
            return pending.pop(0)
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    await asyncio.wait_for(app(scope, receive, send), timeout=30)
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        bytes(message.get("body", b""))
        for message in sent
        if message["type"] == "http.response.body"
    )
    pairs = tuple(
        (bytes(key).decode("latin-1").lower(), bytes(value).decode("latin-1"))
        for key, value in start.get("headers", [])
    )
    return AsgiResponse(status=int(start["status"]), headers=pairs, body=body)


def websocket_connect(
    app: App, target: str, *, headers: Mapping[str, str] | None = None
) -> str | tuple[str, int]:
    """핸드셰이크 하나 → `"accepted"` 또는 `("closed", code)`."""
    return asyncio.run(_websocket(app, target, headers))


async def _websocket(
    app: App, target: str, headers: Mapping[str, str] | None
) -> str | tuple[str, int]:
    raw_path, query = _split_target(target)
    scope: Scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": unquote(raw_path),
        "raw_path": raw_path.encode("ascii"),
        "query_string": query.encode("ascii"),
        "root_path": "",
        "headers": _scope_headers(headers),
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8581),
        "subprotocols": [],
    }
    connected = False
    first: asyncio.Future[Message] = asyncio.get_running_loop().create_future()

    async def receive() -> Message:
        nonlocal connected
        if not connected:
            connected = True
            return {"type": "websocket.connect"}
        await asyncio.sleep(3600)
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(message: Message) -> None:
        if not first.done():
            first.set_result(message)

    task: asyncio.Future[None] = asyncio.ensure_future(app(scope, receive, send))
    waiting: set[asyncio.Future[Any]] = {task, first}
    await asyncio.wait(waiting, timeout=30, return_when=asyncio.FIRST_COMPLETED)
    if not first.done():
        task.cancel()
        raise AssertionError("websocket 앱이 아무 메시지도 보내지 않았습니다")
    message = first.result()
    if not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    if message["type"] == "websocket.accept":
        return "accepted"
    if message["type"] == "websocket.close":
        return ("closed", int(message.get("code", 1000)))
    raise AssertionError(f"모르는 첫 메시지: {message['type']}")
