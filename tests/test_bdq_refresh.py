# Purpose: BDQ 토큰 자동 갱신의 켜기 · 입력 · 갱신 때 · 고리 멈춤 · 비밀을 가짜 교환으로 검증한다.

from __future__ import annotations

import base64
import errno
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from types import FrameType, SimpleNamespace
from typing import get_args

import pandas as pd
import pytest

from capa_simulation import settings
from capa_simulation.io import bdq_refresh, bdq_token
from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.io.container_start_report import BDQ_AUTO_REFRESH_ENV, BDQ_USER_NAME_ENV

ACCOUNT = "fakeaccount"
# 가짜 값만 쓴다 — 사내 꼴을 모른다. 심은 값이 어떤 글에도 나오지 않는지 찾는다.
FAKE_TOKEN = "FAKE-bdq-login-token-0000-abcdefghi"
TOKEN_ERROR = "HTTP 401 invalid token"


def answered() -> urllib.error.HTTPError:
    """갱신 서버가 답한 거절 — 요청이 닿았으니 그 교환이 계정의 최신 토큰을 죽였을 수 있다(셈에
    든다)."""
    return urllib.error.HTTPError(
        "https://refresh.example.invalid/", 400, "Bad Request", Message(), None
    )


class Clock:
    """바꿔 끼우는 시각 — 잠들지 않고 옮긴다. 진짜 지금에서 시작해 토큰 파일 수정 시각과 맞는다."""

    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class FakeExchange:
    """가짜 교환(`bdq_refresh.renew`) — 부른 수와 받은 (지금 토큰, 계정)을 세고, 새 가짜 토큰을
    준다(또는 `error` 를 낸다)."""

    def __init__(
        self,
        *,
        error: BaseException | None = None,
        token: Callable[[int], bytes] | None = None,
        gate: threading.Event | None = None,
    ) -> None:
        self.calls = 0
        self.received: list[tuple[bytes, str]] = []
        self.error = error
        self.token = token
        self.gate = gate
        self._lock = threading.Lock()

    def __call__(self, current_token: bytes, account: str) -> bdq_refresh.Exchanged:
        with self._lock:
            self.calls += 1
            number = self.calls
            self.received.append((current_token, account))
        if self.gate is not None:
            self.gate.wait(5)
        if self.error is not None:
            raise self.error
        made = (
            self.token(number) if self.token else f"FAKE-new-login-{number:04d}-abcdefgh".encode()
        )
        return bdq_refresh.Exchanged(made)


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """자동 갱신을 켠 C-DEP 서버의 자격 폴더 — 켜기 값 `on` · 계정 · 시작 점검 결과 파일."""
    target = tmp_path / "credential"
    monkeypatch.setattr(bdq_token, "CREDENTIAL_DIR", target)
    monkeypatch.setenv(BDQ_USER_NAME_ENV, ACCOUNT)
    monkeypatch.setenv(BDQ_AUTO_REFRESH_ENV, "on")
    report = tmp_path / "container-start-report.json"
    report.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", report)
    return target


def test_the_switch_is_ignored_outside_a_c_dep_server(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """켜기 값이 있어도 시작 점검 결과 파일이 없는 서버(WebIDE · 개발 app.py · 사내 PC)는 꺼짐이다 —
    같은 계정의 운영 토큰을 그 자리에서 갱신해 죽이지 않게(그 자리에는 표 줄 · 알림도 없다)."""
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", folder.parent / "absent.json")

    state = bdq_refresh.status()

    assert state.mode == "off"
    assert state.reason == bdq_refresh.NOT_C_DEP


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    moment = Clock()
    monkeypatch.setattr(bdq_refresh, "clock", moment)
    return moment


def turn_on(monkeypatch: pytest.MonkeyPatch, fake: FakeExchange) -> None:
    """갱신 명령을 안 것으로 — 교환 자리를 가짜로 바꿔 끼운다."""
    monkeypatch.setattr(bdq_refresh, "REQUEST_SHAPE_KNOWN", True)
    monkeypatch.setattr(bdq_refresh, "renew", fake)


def token_file(folder: Path) -> Path:
    return folder / f"bigdataquery.token.{ACCOUNT}"


def lay_out(
    folder: Path,
    clock: Clock,
    *,
    issued_ago: timedelta = timedelta(hours=1),
    source: bdq_token.InstallSource = "start",
    token: str = FAKE_TOKEN,
) -> datetime:
    """켠 서버의 시작 스크립트가 남기는 꼴 — `issued_ago` 앞에 넣은 토큰 · 넣은 때 표지."""
    folder.mkdir(parents=True, exist_ok=True)
    issued = clock.now - issued_ago
    bdq_token.put_token(folder, ACCOUNT, token.encode(), source, issued)
    os.utime(token_file(folder), (issued.timestamp(), issued.timestamp()))
    return issued


def snapshot(folder: Path) -> dict[str, tuple[bytes, int]]:
    return {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in folder.iterdir()}


class FakeModule:
    """`getData` 를 흉내 낸다 — 차례대로 `outcomes` 를 내고(예외면 올림) 부른 수를 센다."""

    def __init__(self, *outcomes: BaseException | None) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def getData(self, **_kwargs: object) -> pd.DataFrame:  # noqa: N802 - 패키지 이름 그대로
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else self.outcomes_tail()
        if outcome is not None:
            raise outcome
        return pd.DataFrame({"a": [1]})

    def outcomes_tail(self) -> BaseException | None:
        return Exception(TOKEN_ERROR)


def query(module: FakeModule) -> object:
    return adapter.call_get_data(SimpleNamespace(getData=module.getData), "SELECT 1")


# --- 교환 한 곳 · 준비 ------------------------------------------------------------------


def test_the_renewal_says_the_command_is_not_known_yet() -> None:
    """갱신 명령은 2026-11-16 에 받는다 — 지금 교환 한 곳은 「미정」 을 내고 받은 지금 토큰 · 계정을
    글에 싣지 않는다."""
    assert bdq_refresh.REQUEST_SHAPE_KNOWN is False
    with pytest.raises(bdq_refresh.RefreshNotConfigured) as caught:
        bdq_refresh.renew(FAKE_TOKEN.encode(), ACCOUNT)
    assert FAKE_TOKEN not in str(caught.value) and ACCOUNT not in str(caught.value)


def test_the_exchanged_token_stays_out_of_its_repr() -> None:
    got = bdq_refresh.Exchanged(FAKE_TOKEN.encode())
    assert FAKE_TOKEN not in repr(got)


def test_the_modes_match_what_the_report_reads() -> None:
    assert set(get_args(bdq_refresh.Mode)) == set(report_contract.REFRESH_MODES)
    assert set(bdq_refresh.MODE_LABELS) == set(report_contract.REFRESH_MODES)


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("no switch", "켜지 않음"),
        ("other value", f"{BDQ_AUTO_REFRESH_ENV} 값이 on 이 아님"),
        ("no account", f"{BDQ_USER_NAME_ENV} 없음"),
        ("environment token", f"{bdq_token.LOGIN_TOKEN_ENV} 있음"),
    ],
)
def test_without_the_switch_or_a_usable_place_it_is_off(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, setup: str, reason: str
) -> None:
    """켜기는 `CAPA_BDQ_AUTO_REFRESH=on` 하나다 — 없거나 그 밖의 값이면 토큰이 있어도 꺼짐이고
    까닭에 값을 싣지 않는다."""
    lay_out(folder, clock)
    if setup == "no switch":
        monkeypatch.delenv(BDQ_AUTO_REFRESH_ENV)
    if setup == "other value":
        monkeypatch.setenv(BDQ_AUTO_REFRESH_ENV, "true")
    if setup == "no account":
        monkeypatch.delenv(BDQ_USER_NAME_ENV)
    if setup == "environment token":
        monkeypatch.setenv(bdq_token.LOGIN_TOKEN_ENV, "FAKE-env-token-value")

    state = bdq_refresh.status()

    assert (state.mode, state.reason, state.label) == ("off", reason, "꺼짐")
    assert "true" not in state.reason


@pytest.mark.parametrize("value", ["on", " ON ", "On"])
def test_the_switch_reads_on_without_case_or_spaces(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    lay_out(folder, clock)
    monkeypatch.setenv(BDQ_AUTO_REFRESH_ENV, value)

    assert bdq_refresh.status().mode == "ready"


def test_off_changes_nothing_on_the_query_path_even_when_the_command_is_known(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """켜지 않은 서버 — 명령을 알고 갱신할 때(7시간)여도 교환을 부르지 않고 자격 폴더는 그대로다
    (사람이 `CAPA_BDQ_TOKEN` · 「토큰 넣기」 로 넣는 지금 길)."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    monkeypatch.delenv(BDQ_AUTO_REFRESH_ENV)
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    before = snapshot(folder)

    module = FakeModule(Exception(TOKEN_ERROR))
    with pytest.raises(adapter.BigDataQueryCallError):
        query(module)

    assert (fake.calls, module.calls) == (0, 1)
    assert snapshot(folder) == before


def test_switched_on_without_the_command_it_is_ready(folder: Path, clock: Clock) -> None:
    lay_out(folder, clock)

    state = bdq_refresh.status()

    assert (state.mode, state.reason, state.label) == ("ready", "요청 꼴 미정", "준비")


def test_ready_changes_nothing_on_the_query_path(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """지금 꼴(갱신 명령 미정) — 켰고 6시간이 지나 갱신할 때여도 교환을 부르지 않고 자격 폴더는
    바이트 · 시각 그대로, 조회 · 실패 · 관리자 표지는 끈 서버와 똑같다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    called: list[bytes] = []
    monkeypatch.setattr(bdq_refresh, "renew", lambda token, _account: called.append(token))
    before = snapshot(folder)

    module = FakeModule(Exception(TOKEN_ERROR))
    with pytest.raises(adapter.BigDataQueryCallError) as caught:
        query(module)

    assert module.calls == 1 and called == []
    assert caught.value.kind == adapter.QUERY_FAILURE_TOKEN
    assert adapter.last_query_failed_on_token() is True
    assert snapshot(folder) == before
    ok = FakeModule(None)
    query(ok)
    assert ok.calls == 1 and snapshot(folder) == before
    assert bdq_refresh.status().mode == "ready"


def test_a_known_shape_with_an_unfilled_body_falls_back_to_ready(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """표지만 참으로 바꾸고 몸을 채우지 않았으면 — 토큰 · 표지를 바꾸지 않고 준비로 물러선다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    monkeypatch.setattr(bdq_refresh, "REQUEST_SHAPE_KNOWN", True)
    token_before = token_file(folder).read_bytes()
    mark_before = bdq_token.read_installed_mark(folder, ACCOUNT)

    query(FakeModule(None))

    assert token_file(folder).read_bytes() == token_before
    assert bdq_token.read_installed_mark(folder, ACCOUNT) == mark_before
    assert bdq_refresh.status().mode == "ready"


# --- 언제 갱신하나 -----------------------------------------------------------------------


def test_a_young_token_is_not_refreshed(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay_out(folder, clock, issued_ago=timedelta(hours=5, minutes=59))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)

    ticket = bdq_refresh.before_query()

    assert fake.calls == 0 and ticket.active
    assert bdq_refresh.status().mode == "on"


def test_six_hours_after_it_was_put_the_token_is_refreshed_first(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, keeps_permission_bits: bool
) -> None:
    lay_out(folder, clock, issued_ago=timedelta(hours=6))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)

    module = FakeModule(None)
    query(module)

    assert fake.calls == 1 and module.calls == 1
    # 입력은 지금 토큰 — 넣기 길이 쓴 토큰 파일의 바이트 그대로다.
    assert fake.received == [(FAKE_TOKEN.encode(), ACCOUNT)]
    assert token_file(folder).read_bytes() == b"FAKE-new-login-0001-abcdefgh"
    mark = bdq_token.read_installed_mark(folder, ACCOUNT)
    assert mark == bdq_token.InstalledMark(clock.now, "refresh")
    if keeps_permission_bits:
        assert token_file(folder).stat().st_mode & 0o777 == 0o600
    state = bdq_refresh.status()
    assert (state.mode, state.last_refreshed_at, state.last_failure) == ("on", clock.now, "")


def test_a_token_whose_expiry_is_within_an_hour_is_refreshed(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def part(value: object) -> str:
        raw = json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    soon = int((clock.now + timedelta(minutes=50)).timestamp())
    jwt = f"{part({'alg': 'none'})}.{part({'exp': soon})}.FAKE-signature"
    lay_out(folder, clock, issued_ago=timedelta(hours=1), token=jwt)
    fake = FakeExchange()
    turn_on(monkeypatch, fake)

    bdq_refresh.before_query()

    assert fake.calls == 1


def test_an_expiry_the_exchange_reported_brings_the_next_refresh_forward(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """토큰에서 만료를 읽지 못하는 꼴(실측 35바이트)이어도 갱신 응답이 알려 준 만료로 앞당긴다 —
    표지에 시각만 싣는다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    reported = clock.now + timedelta(hours=2)
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    monkeypatch.setattr(
        bdq_refresh,
        "renew",
        lambda token, account: bdq_refresh.Exchanged(fake(token, account).token, reported),
    )

    bdq_refresh.before_query()
    mark = bdq_token.read_installed_mark(folder, ACCOUNT)
    assert mark is not None and mark.expires_at == reported
    assert set(json.loads((folder / f"capa-bdq-installed.{ACCOUNT}.json").read_bytes())) == {
        "installed_at",
        "source",
        "expires_at",
    }

    clock.advance(minutes=59)
    bdq_refresh.before_query()
    assert fake.calls == 1
    clock.advance(minutes=1)
    bdq_refresh.before_query()
    assert fake.calls == 2


@pytest.mark.parametrize(
    "reported",
    [timedelta(minutes=30), timedelta(hours=-1), None],
    ids=["30분 뒤", "이미 지남", "시각대 없음"],
)
def test_a_reported_expiry_already_inside_the_hour_is_not_trusted(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, reported: timedelta | None
) -> None:
    """갱신 응답의 만료가 넣을 때 이미 1시간 안이면(시각대를 잘못 읽은 응답) 모름으로 둔다 — 믿으면
    넣을 때마다 다시 「만료 1시간 안」 이라 조회마다 교환한다(죽이기 고리)."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)

    def exchange(token: bytes, account: str) -> bdq_refresh.Exchanged:
        got = fake(token, account)
        moment = clock.now.replace(tzinfo=None) if reported is None else clock.now + reported
        return bdq_refresh.Exchanged(got.token, moment)

    monkeypatch.setattr(bdq_refresh, "renew", exchange)
    for _ in range(10):
        query(FakeModule(None))
        clock.advance(minutes=6)

    assert fake.calls == 1
    mark = bdq_token.read_installed_mark(folder, ACCOUNT)
    assert mark is not None and mark.source == "refresh" and mark.expires_at is None
    assert bdq_refresh.status().last_failure == ""


def _jwt(expires: datetime, number: int) -> bytes:
    def part(value: object) -> str:
        raw = json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    claims = {"exp": int(expires.timestamp()), "n": number}
    return f"{part({'alg': 'none'})}.{part(claims)}.FAKE-signature".encode()


@pytest.mark.parametrize(
    ("where", "minutes"),
    [("응답", 61), ("응답", 66), ("JWT", 30), ("JWT", 61)],
    ids=["응답 +61분", "응답 +66분", "JWT +30분", "JWT +61분"],
)
def test_a_refreshed_token_is_not_refreshed_again_on_its_expiry_right_after_it_was_put(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, where: str, minutes: int
) -> None:
    """만료가 넣을 때 1시간을 조금 넘거나(응답 만료) 토큰 자신이 곧 만료라고 말해도(JWT `exp`) —
    갱신으로 넣은 토큰은 넣은 지 `REFRESHED_HOLD` 안에는 만료를 근거로 다시 갱신하지 않는다(조회마다
    교환하는 고리를 막는다)."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)

    def exchange(token: bytes, account: str) -> bdq_refresh.Exchanged:
        got = fake(token, account)
        expires = clock.now + timedelta(minutes=minutes)
        if where == "JWT":
            return bdq_refresh.Exchanged(_jwt(expires, fake.calls))
        return bdq_refresh.Exchanged(got.token, expires)

    monkeypatch.setattr(bdq_refresh, "renew", exchange)
    for _ in range(10):
        query(FakeModule(None))
        clock.advance(minutes=6)

    assert 1 <= fake.calls <= 2
    assert bdq_refresh.status().mode == "on"


def test_a_refreshed_token_killed_within_the_hold_still_counts_toward_the_loop(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """만료가 1시간 남짓한 토큰이 넣은 지 몇 분 만에 죽어도 「제 수명」 으로 빼지 않는다 — 다른 곳의
    로그인 고리는 그대로 멈춘다(토큰 실패 뒤 갱신은 이 고리 셈이 막는다)."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    monkeypatch.setattr(
        bdq_refresh,
        "renew",
        lambda token, account: bdq_refresh.Exchanged(
            fake(token, account).token, clock.now + timedelta(minutes=61)
        ),
    )
    query(FakeModule(None))
    for _ in range(3):
        clock.advance(minutes=6)
        try:
            query(FakeModule(Exception(TOKEN_ERROR), None))
        except adapter.BigDataQueryCallError:
            pass

    state = bdq_refresh.status()
    assert (state.mode, state.reason) == ("halted", bdq_refresh.HALT_ELSEWHERE)
    assert fake.calls == 2


def test_the_next_renewal_takes_the_token_the_last_one_put(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """6시간마다 이어진다 — 둘째 갱신의 입력은 첫 갱신이 넣은 토큰이다(시작 때 토큰이 아니다)."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)

    bdq_refresh.before_query()
    clock.advance(hours=6)
    bdq_refresh.before_query()

    assert [token for token, _account in fake.received] == [
        FAKE_TOKEN.encode(),
        b"FAKE-new-login-0001-abcdefgh",
    ]
    assert token_file(folder).read_bytes() == b"FAKE-new-login-0002-abcdefgh"


def _unreadable(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    reader = Path.read_bytes

    def refuse(self: Path) -> bytes:
        if self == target:
            raise PermissionError(errno.EACCES, "Permission denied")
        return reader(self)

    monkeypatch.setattr(Path, "read_bytes", refuse)


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        ("missing", "지금 토큰 없음"),
        ("empty", "지금 토큰이 비었음"),
        ("unreadable", "지금 토큰을 읽지 못함(PermissionError)"),
    ],
    ids=["없음", "빔", "못 읽음"],
)
def test_a_token_that_cannot_be_read_is_not_renewed_and_says_why(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, damage: str, reason: str
) -> None:
    """입력(지금 토큰)이 없거나 · 비었거나 · 못 읽으면 교환을 부르지 않고 그 까닭이 마지막 시도
    실패로 선다(표 줄). 교환을 부르지 않았으니 조회가 이어져도 거듭 실패로 멈추지 않는다."""
    issued = lay_out(folder, clock, issued_ago=timedelta(hours=7))
    if damage == "missing":
        token_file(folder).unlink()
    if damage == "empty":
        token_file(folder).write_bytes(b"  \n")
        os.utime(token_file(folder), (issued.timestamp(), issued.timestamp()))
    if damage == "unreadable":
        _unreadable(monkeypatch, token_file(folder))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)

    for _ in range(2 * bdq_refresh.FAILED_EXCHANGE_LIMIT):
        bdq_refresh.before_query()
        clock.advance(minutes=6)

    state = bdq_refresh.status()
    assert fake.calls == 0
    assert (state.mode, state.last_failure, state.last_failure_unreached) == ("on", reason, False)


def test_a_mark_from_the_future_or_older_than_the_file_falls_back_to_the_file_time(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """시계가 뒤로 간 표지 · 밖에서 바꾼 토큰 파일 — 표지 대신 파일 수정 시각으로 센다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=1))
    bdq_token.write_installed_mark(folder, ACCOUNT, "start", clock.now + timedelta(days=1))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)

    bdq_refresh.before_query()
    assert fake.calls == 0

    clock.advance(hours=5, minutes=1)
    bdq_refresh.before_query()
    assert fake.calls == 1


# --- 토큰 실패 뒤 한 번 ------------------------------------------------------------------


def test_a_token_failure_refreshes_once_and_asks_again_once(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay_out(folder, clock)
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    module = FakeModule(Exception(TOKEN_ERROR), None)

    answer = query(module)

    assert isinstance(answer, pd.DataFrame)
    assert (fake.calls, module.calls) == (1, 2)
    assert adapter.last_query_failed_on_token() is False


def test_a_failure_after_the_new_token_is_the_query_failure(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay_out(folder, clock)
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    module = FakeModule(Exception(TOKEN_ERROR), Exception(TOKEN_ERROR))

    with pytest.raises(adapter.BigDataQueryCallError) as caught:
        query(module)

    assert (fake.calls, module.calls) == (1, 2)
    assert caught.value.kind == adapter.QUERY_FAILURE_TOKEN
    assert adapter.last_query_failed_on_token() is True


@pytest.mark.parametrize(
    ("second", "kind", "type_name"),
    [
        (TimeoutError("read timed out"), adapter.QUERY_FAILURE_TIMEOUT, "TimeoutError"),
        (
            Exception("ORA-00942 table or view does not exist"),
            adapter.QUERY_FAILURE_SQL,
            "Exception",
        ),
    ],
    ids=["시간 초과", "SQL"],
)
def test_a_retry_that_fails_another_way_is_judged_by_its_own_failure(
    folder: Path,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    second: BaseException,
    kind: str,
    type_name: str,
) -> None:
    """갱신으로 넣은 토큰이 바깥 로그인 한 번에 죽고, 새 토큰으로 다시 물은 것이 시간 초과 · SQL 로
    끝나면 — 올라가는 갈래는 그 실패 자신이고(첫 토큰 실패가 사슬에 붙지 않는다) `AD-10` 은 서지
    않으며, 새 토큰은 죽음으로 세지 않는다(조회 한 번에 멈추지 않는다)."""
    lay_out(folder, clock, source="refresh")
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    caplog.set_level(logging.WARNING)

    with pytest.raises(adapter.BigDataQueryCallError) as caught:
        query(FakeModule(Exception(TOKEN_ERROR), second))

    assert fake.calls == 1
    assert caught.value.kind == kind
    assert caught.value.type_names == (type_name,)
    assert caught.value.__cause__ is second and second.__context__ is None
    assert adapter.last_query_failed_on_token() is False
    assert bdq_refresh.status().mode == "on"
    failures = [r.getMessage() for r in caplog.records if "BigDataQuery 실패" in r.getMessage()]
    assert failures and all(f"종류={type_name}" in line for line in failures)
    # 그 새 토큰으로 다음 조회가 되면 아무 일도 없다 — 멈춤도 다시 묻기도 없다.
    clock.advance(minutes=6)
    ok = FakeModule(None)
    query(ok)
    assert (ok.calls, fake.calls, bdq_refresh.status().mode) == (1, 1, "on")


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("read timed out"),
        Exception("syntax error near unexpected token"),
        Exception("TokenizeError in parser"),
    ],
)
def test_a_failure_that_is_not_the_token_kind_does_not_refresh(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    """토큰 갈래(`AD-10` 을 세우는 판정)만 갱신한다 — 넓은 안내 추정으로 산 토큰을 죽이지 않는다."""
    lay_out(folder, clock)
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    module = FakeModule(error)

    with pytest.raises(adapter.BigDataQueryCallError):
        query(module)

    assert (fake.calls, module.calls) == (0, 1)


def test_a_failed_early_refresh_does_not_fail_the_query(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange(error=answered())
    turn_on(monkeypatch, fake)
    module = FakeModule(None)

    assert isinstance(query(module), pd.DataFrame)

    assert (fake.calls, module.calls) == (1, 1)
    state = bdq_refresh.status()
    assert (state.mode, state.last_failure) == ("on", "교환 실패(HTTPError)")


# --- 죽이기 고리 막기 ---------------------------------------------------------------------


def test_threads_that_all_find_it_due_exchange_once(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    gate = threading.Event()
    fake = FakeExchange(gate=gate)
    turn_on(monkeypatch, fake)
    tickets: list[bdq_refresh.Ticket] = []
    threads = [
        threading.Thread(target=lambda: tickets.append(bdq_refresh.before_query()))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 5
    while fake.calls == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    gate.set()
    for thread in threads:
        thread.join(5)

    assert fake.calls == 1
    assert len(tickets) == 8
    marks = {ticket.mark for ticket in tickets}
    assert marks == {bdq_token.InstalledMark(clock.now, "refresh")}


def test_a_failure_while_another_thread_already_refreshed_asks_again_without_exchange(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """조회가 도는 사이 다른 쪽이 새 토큰을 넣었으면 — 잠금 뒤 표지가 달라 교환 없이 한 번 다시."""
    lay_out(folder, clock)
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    ticket = bdq_refresh.before_query()
    clock.advance(minutes=1)
    bdq_token.install_content(b"FAKE-other-thread-token-abcdef", "refresh", at=clock.now)

    retry = bdq_refresh.after_token_failure(ticket)

    assert retry is not None and fake.calls == 0
    assert retry.mark == bdq_token.InstalledMark(clock.now, "refresh")


def test_a_token_our_own_early_refresh_replaced_is_not_counted_as_killed_elsewhere(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """긴 조회가 갱신으로 넣은 토큰 T1 으로 도는 사이 이 프로세스가 6시간 갱신으로 T2 를 넣으면 —
    그 조회의 토큰 실패는 우리 교환이 죽인 것이라 고리 기록에 들지 않는다(바깥 로그인 한 번에
    멈추지 않는다)."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    long_query = bdq_refresh.before_query()
    assert long_query.mark is not None and long_query.mark.source == "refresh"
    clock.advance(hours=6)
    bdq_refresh.before_query()
    assert fake.calls == 2

    retry = bdq_refresh.after_token_failure(long_query)
    assert retry is not None and fake.calls == 2
    clock.advance(minutes=10)
    current = bdq_refresh.before_query()
    bdq_refresh.after_token_failure(current, refresh=False)

    assert bdq_refresh.status().mode == "on"


def test_attempts_are_at_least_five_minutes_apart(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange(error=OSError("unreachable"))
    turn_on(monkeypatch, fake)

    bdq_refresh.before_query()
    clock.advance(minutes=4, seconds=59)
    bdq_refresh.before_query()
    assert fake.calls == 1
    ticket = bdq_refresh.before_query()
    assert bdq_refresh.after_token_failure(ticket) is None
    assert fake.calls == 1

    clock.advance(seconds=1)
    bdq_refresh.before_query()
    assert fake.calls == 2


def test_refreshed_tokens_that_keep_dying_stop_the_refresh(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """같은 계정이 다른 곳(WebIDE · 다른 서버)에서 로그인해 갱신으로 넣은 토큰이 거듭 죽으면 — 교환
    수가 묶이고 멈춤 · 까닭이 서며, 그 뒤로는 교환하지 않는다."""
    lay_out(folder, clock)
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    caplog.set_level(logging.WARNING)

    for _ in range(6):
        with pytest.raises(adapter.BigDataQueryCallError):
            query(FakeModule(Exception(TOKEN_ERROR), Exception(TOKEN_ERROR)))
        clock.advance(minutes=6)

    assert fake.calls == 2
    state = bdq_refresh.status()
    assert (state.mode, state.label, state.reason) == ("halted", "멈춤", bdq_refresh.HALT_ELSEWHERE)
    assert adapter.last_query_failed_on_token() is True
    assert any(bdq_refresh.HALT_ELSEWHERE in record.getMessage() for record in caplog.records)


def test_one_death_of_a_refreshed_token_does_not_stop_it(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """한 번(같은 계정의 WebIDE 로그인 한 번)은 갱신으로 이긴다 — 겹친 실패는 한 번으로 센다."""
    lay_out(folder, clock)
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    query(FakeModule(Exception(TOKEN_ERROR), None))
    ticket = bdq_refresh.before_query()
    clock.advance(minutes=10)
    for _ in range(3):
        bdq_refresh.after_token_failure(ticket, refresh=False)

    assert bdq_refresh.status().mode == "on"


def test_refreshed_tokens_that_keep_dying_slowly_also_stop_the_refresh(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1시간보다 드물게 되풀이되는 고리(막힐 때마다 다시 로그인하는 WebIDE) — 24시간 안에 셋이면
    멈춘다."""
    lay_out(folder, clock)
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    query(FakeModule(Exception(TOKEN_ERROR), None))
    assert fake.calls == 1

    for _ in range(2):
        clock.advance(hours=2)
        query(FakeModule(Exception(TOKEN_ERROR), None))
    assert (fake.calls, bdq_refresh.status().mode) == (3, "on")

    clock.advance(hours=2)
    with pytest.raises(adapter.BigDataQueryCallError):
        query(FakeModule(Exception(TOKEN_ERROR)))

    state = bdq_refresh.status()
    assert (state.mode, state.reason, fake.calls) == ("halted", bdq_refresh.HALT_ELSEWHERE, 3)


@pytest.mark.parametrize(
    ("age", "mode"), [(timedelta(hours=6, minutes=1), "on"), (timedelta(hours=1), "halted")]
)
def test_a_refreshed_token_past_its_refresh_time_dying_is_not_a_loop(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, age: timedelta, mode: str
) -> None:
    """갱신할 때(6시간)를 넘긴 토큰의 실패는 제 수명이다 — 미리 한 갱신이 실패해 서버 쪽 수명이 다한
    것을 다른 곳의 로그인으로 세지 않는다."""
    lay_out(folder, clock)
    turn_on(monkeypatch, FakeExchange(error=OSError("unreachable")))
    for _ in range(bdq_refresh.LOOP_LIMIT):
        put = clock.now - age
        bdq_token.install_content(
            f"FAKE-refreshed-{clock.now.timestamp():.0f}-abcdefgh".encode(), "refresh", at=put
        )
        mark = bdq_token.read_installed_mark(folder, ACCOUNT)
        bdq_refresh.after_token_failure(bdq_refresh.Ticket(True, mark), refresh=False)
        clock.advance(minutes=10)

    assert bdq_refresh.status().mode == mode


def test_a_token_put_by_a_person_after_the_stop_turns_it_back_on(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay_out(folder, clock)
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    for _ in range(3):
        with pytest.raises(adapter.BigDataQueryCallError):
            query(FakeModule(Exception(TOKEN_ERROR), Exception(TOKEN_ERROR)))
        clock.advance(minutes=6)
    assert bdq_refresh.status().mode == "halted"

    clock.advance(minutes=1)
    bdq_token.install_content(b"FAKE-admin-put-login-token-abc", "admin", at=clock.now)

    assert bdq_refresh.status().mode == "on"
    calls = fake.calls
    clock.advance(hours=6)
    bdq_refresh.before_query()
    assert fake.calls == calls + 1


def test_a_token_that_cannot_be_put_is_a_failure_and_keeps_the_old_file(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange(token=lambda _number: b"short")
    turn_on(monkeypatch, fake)

    bdq_refresh.before_query()

    assert fake.calls == 1
    assert token_file(folder).read_bytes() == FAKE_TOKEN.encode()
    failure = bdq_refresh.status().last_failure
    assert failure.startswith("받은 토큰을 넣지 못함 — ") and "short" not in failure


@pytest.mark.parametrize(
    ("fake", "kind"),
    [
        (FakeExchange(token=lambda _number: b"short"), "받은 토큰을 넣지 못함"),
        (FakeExchange(error=answered()), "교환 실패(HTTPError)"),
        (FakeExchange(error=ConnectionResetError("reset")), "교환 실패(ConnectionResetError)"),
        (FakeExchange(token=lambda _number: "not bytes"), "교환 응답 꼴이 다름"),  # type: ignore[arg-type, return-value]
    ],
    ids=["넣기 거절", "서버가 거절", "닿은 뒤 끊김", "응답 꼴"],
)
def test_exchanges_that_keep_failing_after_the_call_stop_the_refresh(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, fake: FakeExchange, kind: str
) -> None:
    """교환은 됐는데 받은 토큰을 못 넣거나 교환이 예외로 끝나면 — 그 교환이 계정의 최신 토큰을
    죽였을 수 있다. 조회가 이어져도 교환은 `FAILED_EXCHANGE_LIMIT` 번에서 멈추고 까닭이 선다."""
    lay_out(folder, clock)
    turn_on(monkeypatch, fake)

    for _ in range(10):
        with pytest.raises(adapter.BigDataQueryCallError):
            query(FakeModule(Exception(TOKEN_ERROR)))
        clock.advance(minutes=6)

    assert fake.calls == bdq_refresh.FAILED_EXCHANGE_LIMIT
    state = bdq_refresh.status()
    assert (state.mode, state.reason) == ("halted", bdq_refresh.HALT_FAILING)
    assert state.last_failure.startswith(kind)
    assert token_file(folder).read_bytes() == FAKE_TOKEN.encode()


def test_a_success_between_failed_exchanges_starts_the_count_again(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    outcomes = [True, True, False, True, True]
    fake = FakeExchange()

    def flaky(current_token: bytes, account: str) -> bdq_refresh.Exchanged:
        got = fake(current_token, account)
        if outcomes.pop(0):
            raise answered()
        return got

    turn_on(monkeypatch, fake)
    monkeypatch.setattr(bdq_refresh, "renew", flaky)
    for hours in (0, 0, 0, 6, 0):
        clock.advance(hours=hours, minutes=6)
        query(FakeModule(None))

    assert fake.calls == 5
    assert bdq_refresh.status().mode == "on"


UNREACHED = [
    ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused"),
    socket.gaierror(socket.EAI_NONAME, "Name or service not known"),
    TimeoutError("timed out"),
    urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")),
    urllib.error.URLError(socket.gaierror(socket.EAI_NONAME, "Name or service not known")),
    urllib.error.URLError(TimeoutError("timed out")),
    bdq_refresh.ExchangeUnreached("요청을 보내지 못함"),
]
UNREACHED_IDS = [
    "연결 거부",
    "이름 풀기",
    "시간 초과",
    "urllib 연결 거부",
    "urllib 이름 풀기",
    "urllib 시간 초과",
    "닿지 못함 예외",
]


@pytest.mark.parametrize("error", UNREACHED, ids=UNREACHED_IDS)
def test_an_outage_that_never_reached_the_server_does_not_stop_and_it_resumes(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    """짧은 인증 서버 장애(연결 거부 · 이름 풀기 · 시간 초과) — 갱신 서버에 닿지 못한 교환은 아무
    토큰도 죽이지 않았으니 멈춤 셈에 넣지 않는다. 5분 간격으로 다시 시도하며 그동안 까닭 「갱신
    서버에 닿지 못함」 이 서고, 서버가 돌아오면 사람 손 없이 이어진다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=6, minutes=1), source="refresh")
    fake = FakeExchange()
    down = [True]

    def outage(token: bytes, account: str) -> bdq_refresh.Exchanged:
        got = fake(token, account)
        if down[0]:
            raise error
        return got

    turn_on(monkeypatch, fake)
    monkeypatch.setattr(bdq_refresh, "renew", outage)
    tries = 2 * bdq_refresh.FAILED_EXCHANGE_LIMIT + 1
    for _ in range(tries):
        query(FakeModule(None))
        clock.advance(minutes=6)

    state = bdq_refresh.status()
    assert fake.calls == tries
    assert (state.mode, state.reason, state.last_failure_unreached) == ("on", "", True)
    assert state.last_failure.startswith(f"{bdq_refresh.UNREACHED}(")
    assert token_file(folder).read_bytes() == FAKE_TOKEN.encode()

    down[0] = False
    query(FakeModule(None))

    state = bdq_refresh.status()
    assert fake.calls == tries + 1
    assert token_file(folder).read_bytes() == f"FAKE-new-login-{tries + 1:04d}-abcdefgh".encode()
    assert (state.mode, state.last_failure, state.last_failure_unreached) == ("on", "", False)


def test_unreached_attempts_neither_count_toward_the_stop_nor_reset_it(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """닿지 못한 시도는 잇따른 실패 수에 더하지도 0 으로 되돌리지도 않는다 — 서버가 답한 거절 셋이면
    그 사이에 닿지 못한 시도가 끼어도 멈춘다. 닿으면 까닭이 그 거절로 바뀐다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    outcomes: list[BaseException] = [
        answered(),
        ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused"),
        answered(),
        TimeoutError("timed out"),
        TimeoutError("timed out"),
    ]
    fake = FakeExchange()

    def mixed(token: bytes, account: str) -> bdq_refresh.Exchanged:
        fake(token, account)
        raise outcomes.pop(0) if outcomes else answered()

    turn_on(monkeypatch, fake)
    monkeypatch.setattr(bdq_refresh, "renew", mixed)
    for _ in range(5):
        query(FakeModule(None))
        clock.advance(minutes=6)
    state = bdq_refresh.status()
    assert (state.mode, state.last_failure_unreached) == ("on", True)

    query(FakeModule(None))

    state = bdq_refresh.status()
    assert fake.calls == 6
    assert (state.mode, state.reason) == ("halted", bdq_refresh.HALT_FAILING)
    assert (state.last_failure, state.last_failure_unreached) == ("교환 실패(HTTPError)", False)


def test_an_answered_refusal_is_not_taken_for_an_outage() -> None:
    """서버가 답한 것(HTTP 오류 — `URLError` 의 갈래)과 연결이 닿은 뒤 끊긴 것은 셈에 든다."""
    reached: list[BaseException] = [
        answered(),
        ConnectionResetError("reset"),
        OSError("other"),
        RuntimeError("x"),
    ]
    for error in reached:
        assert bdq_refresh.reached_the_server(error) is True
    for error in UNREACHED:
        assert bdq_refresh.reached_the_server(error) is False


@pytest.mark.skipif(sys.platform == "win32", reason="파일 잠금은 POSIX 만")
def test_a_folder_lock_the_file_system_refuses_falls_back_to_the_thread_lock(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`/config` 가 잠금을 받지 않는 파일 체계(`ENOLCK`)여도 갱신이 소리 없이 죽지 않는다 — 스레드
    잠금만으로 가고 그 사실을 로그에 한 줄 남긴다(이 프로세스에서 한 번 — 조회마다 쌓지 않는다).
    표 줄 · `AD-17` 에는 서지 않는다 — 갱신은 제대로 돌았다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)

    def refuse(_descriptor: int, _operation: int) -> None:
        raise OSError(errno.ENOLCK, "No locks available")

    import fcntl

    monkeypatch.setattr(fcntl, "flock", refuse)
    caplog.set_level(logging.WARNING)

    query(FakeModule(None))

    assert fake.calls == 1
    assert token_file(folder).read_bytes() == b"FAKE-new-login-0001-abcdefgh"
    assert bdq_refresh.status().last_failure == ""
    assert any("파일 잠금을 걸지 못함(OSError)" in r.getMessage() for r in caplog.records)

    clock.advance(minutes=6)
    retried = FakeModule(Exception(TOKEN_ERROR), None)
    query(retried)
    assert (fake.calls, retried.calls) == (2, 2)
    clock.advance(hours=7)
    query(FakeModule(None))
    assert fake.calls == 3
    warnings = [r for r in caplog.records if "파일 잠금을 걸지 못함" in r.getMessage()]
    assert len(warnings) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="파일 잠금은 POSIX 만")
def test_a_lock_file_that_cannot_be_opened_is_logged_once_per_process(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """잠금 파일을 열지 못해도(권한) 갱신은 돌고, 멈춘 뒤 조회마다 잠금을 다시 시도해도 경고는 한
    줄이다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange(error=answered())
    turn_on(monkeypatch, fake)
    opened = os.open

    def refuse(path: object, flags: int, mode: int = 0o777) -> int:
        if str(path).endswith(bdq_refresh.LOCK_SUFFIX):
            raise PermissionError(errno.EACCES, "Permission denied")
        return opened(path, flags, mode)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", refuse)
    caplog.set_level(logging.WARNING)

    for _ in range(bdq_refresh.FAILED_EXCHANGE_LIMIT + 3):
        query(FakeModule(None))
        clock.advance(minutes=6)

    assert fake.calls == bdq_refresh.FAILED_EXCHANGE_LIMIT
    assert bdq_refresh.status().mode == "halted"
    warnings = [r for r in caplog.records if "잠금 파일을 열지 못함" in r.getMessage()]
    assert len(warnings) == 1


def test_an_unexpected_failure_on_the_query_path_is_recorded_not_swallowed(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """갱신 쪽의 뜻밖의 예외 — 조회는 그대로 가고, 실패 갈래(종류 이름)가 표 줄 · `AD-17` 에
    보인다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    turn_on(monkeypatch, FakeExchange())

    def broken(*_args: object) -> bool:
        raise LookupError(FAKE_TOKEN)

    monkeypatch.setattr(bdq_refresh, "_due", broken)

    assert isinstance(query(FakeModule(None)), pd.DataFrame)

    state = bdq_refresh.status()
    assert (state.mode, state.last_failure) == ("on", "예상하지 못한 실패(LookupError)")


def test_a_token_a_person_puts_after_a_failure_clears_the_failure(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """미리 한 갱신이 실패한 뒤 관리자가 「토큰 넣기」 를 하면 마지막 시도 실패(`AD-17`)가 풀린다 —
    다음 교환은 그 토큰의 6시간 뒤다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange(error=answered())
    turn_on(monkeypatch, fake)
    query(FakeModule(None))
    assert bdq_refresh.status().last_failure == "교환 실패(HTTPError)"

    clock.advance(minutes=10)
    bdq_token.install_content(b"FAKE-admin-put-login-token-abc", "admin", at=clock.now)
    clock.advance(hours=1)
    query(FakeModule(None))

    state = bdq_refresh.status()
    assert (state.mode, state.last_failure, state.last_failure_at) == ("on", "", None)
    assert fake.calls == 1


def test_a_token_a_person_puts_after_a_failing_stop_clears_both(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay_out(folder, clock)
    fake = FakeExchange(error=answered())
    turn_on(monkeypatch, fake)
    for _ in range(bdq_refresh.FAILED_EXCHANGE_LIMIT):
        with pytest.raises(adapter.BigDataQueryCallError):
            query(FakeModule(Exception(TOKEN_ERROR)))
        clock.advance(minutes=6)
    assert bdq_refresh.status().mode == "halted"

    bdq_token.install_content(b"FAKE-admin-put-login-token-abc", "admin", at=clock.now)

    state = bdq_refresh.status()
    assert (state.mode, state.reason, state.last_failure) == ("on", "", "")
    # 사람이 넣은 뒤로 다시 센다 — 교환이 또 잇따라 실패하면 다시 멈춘다.
    for _ in range(bdq_refresh.FAILED_EXCHANGE_LIMIT):
        clock.advance(minutes=6)
        with pytest.raises(adapter.BigDataQueryCallError):
            query(FakeModule(Exception(TOKEN_ERROR)))
    assert fake.calls == 2 * bdq_refresh.FAILED_EXCHANGE_LIMIT
    assert bdq_refresh.status().reason == bdq_refresh.HALT_FAILING


def test_the_same_token_back_still_moves_the_put_time(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 토큰을 돌려받아도 넣은 때를 옮긴다 — 그러지 않으면 5분마다 다시 묻는다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange(token=lambda _number: FAKE_TOKEN.encode())
    turn_on(monkeypatch, fake)

    bdq_refresh.before_query()
    clock.advance(minutes=6)
    bdq_refresh.before_query()

    assert fake.calls == 1
    mark = bdq_token.read_installed_mark(folder, ACCOUNT)
    assert mark is not None and mark.source == "refresh"


# --- 비밀 · 스레드 · 나이 ------------------------------------------------------------------


def test_no_secret_reaches_a_status_a_log_or_an_exception(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """교환이 지금 토큰(입력)을 원문 · base64 로 문구에 실어 실패해도 상태 · 로그 · 조회 예외 ·
    표지에 없고, 실패 갈래에 토큰 길이도 없다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    encoded = base64.b64encode(FAKE_TOKEN.encode()).decode()
    leaked = f"bad request body token={FAKE_TOKEN} encoded={encoded}"
    fake = FakeExchange(error=RuntimeError(leaked))
    turn_on(monkeypatch, fake)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(adapter.BigDataQueryCallError) as caught:
        query(FakeModule(Exception(TOKEN_ERROR)))

    state = bdq_refresh.status()
    mark = (folder / f"capa-bdq-installed.{ACCOUNT}.json").read_text(encoding="utf-8")
    messages = [record.getMessage() for record in caplog.records]
    texts = [repr(state), str(caught.value), repr(caught.value.__cause__), mark, *messages]
    for secret in (FAKE_TOKEN, encoded):
        for text in texts:
            assert secret not in text
    assert set(json.loads(mark)) == {"installed_at", "source"}
    assert state.last_failure == "교환 실패(RuntimeError)"
    assert str(len(FAKE_TOKEN)) not in state.last_failure + state.reason


def streamlit_calls_in_a_thread(work: Callable[[], object]) -> list[str]:
    """실행 문맥 없는 스레드(공식버전 자동 갱신 예약 스레드 이름)에서 `work` 를 돌리고, 그
    스레드에서 돈 Streamlit 코드의 함수(모듈 · 이름)를 모두 모은다. 갱신 쪽이 예외를 삼키므로
    부름 자체를 잡는다 — `st.*` 를 하나라도 부르면 빈 목록이 아니다."""
    seen: list[str] = []
    errors: list[BaseException] = []

    def watch(frame: FrameType, event: str, _arg: object) -> None:
        module = str(frame.f_globals.get("__name__", ""))
        if event == "call" and (module == "streamlit" or module.startswith("streamlit.")):
            seen.append(f"{module}.{frame.f_code.co_name}")

    def run() -> None:
        sys.setprofile(watch)
        try:
            work()
        except BaseException as error:  # pragma: no cover - 실패만 담는다
            errors.append(error)
        finally:
            sys.setprofile(None)

    worker = threading.Thread(target=run, name="capa-auto-official-update")
    worker.start()
    worker.join(10)
    assert errors == []
    return seen


def test_the_thread_watch_catches_a_streamlit_call() -> None:
    """감시가 듣는지 — 실행 문맥 없는 스레드에서 `st.*` 를 부르면 잡힌다(경고만 내고 예외가 아니라
    import 글자 찾기로는 못 잡는 꼴)."""
    import streamlit as st

    assert streamlit_calls_in_a_thread(lambda: st.session_state.get("x")) != []


def test_the_refresh_runs_in_a_thread_without_streamlit(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """공식버전 자동 갱신 예약 스레드도 조회한다 — 미리 갱신 · 토큰 실패 뒤 갱신 · 다시 묻기 · 고리
    멈춤 · 사람 넣기로 풂 · 서버에 닿지 못함 · 교환 실패 기록 · 거듭 실패 멈춤 · 상태 읽기까지 그
    스레드에서 Streamlit 코드를 한 줄도 돌리지 않는다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    failing = FakeExchange(error=answered())
    unreachable = FakeExchange(error=urllib.error.URLError(ConnectionRefusedError()))

    def quietly(module: FakeModule) -> None:
        try:
            query(module)
        except adapter.BigDataQueryCallError:
            pass

    def work() -> None:
        quietly(FakeModule(None))
        for _ in range(2):
            clock.advance(minutes=6)
            quietly(FakeModule(Exception(TOKEN_ERROR), Exception(TOKEN_ERROR)))
        assert bdq_refresh.status().reason == bdq_refresh.HALT_ELSEWHERE
        clock.advance(minutes=1)
        bdq_token.install_content(b"FAKE-admin-put-login-token-abc", "admin", at=clock.now)
        bdq_refresh.renew = unreachable
        clock.advance(minutes=6)
        quietly(FakeModule(Exception(TOKEN_ERROR)))
        assert bdq_refresh.status().last_failure_unreached
        bdq_refresh.renew = failing
        for _ in range(bdq_refresh.FAILED_EXCHANGE_LIMIT):
            clock.advance(minutes=6)
            quietly(FakeModule(Exception(TOKEN_ERROR)))
        bdq_refresh.status()

    assert streamlit_calls_in_a_thread(work) == []
    assert fake.calls == 2 and failing.calls == bdq_refresh.FAILED_EXCHANGE_LIMIT
    assert unreachable.calls == 1
    assert bdq_refresh.status().reason == bdq_refresh.HALT_FAILING


def test_the_refresh_modules_load_without_streamlit() -> None:
    """시작 스크립트가 앱 의존성보다 먼저 읽는다 — 갱신 · 조회 길 모듈은 Streamlit 을 싣지
    않는다."""
    code = (
        "import sys\n"
        "import capa_simulation.io.bdq_refresh, capa_simulation.io.company_bigdataquery_adapter\n"
        "print('streamlit' in sys.modules)\n"
    )
    source_root = Path(bdq_refresh.__file__).resolve().parents[2]
    environ = {**os.environ, "PYTHONPATH": str(source_root)}
    done = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
        env=environ,
    )
    assert done.stdout.strip() == "False"
