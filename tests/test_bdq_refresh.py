# Purpose: BDQ 토큰 자동 갱신의 준비 · 갱신 때 · 잠금 · 고리 멈춤 · 비밀을 가짜 교환으로 검증한다.

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pandas as pd
import pytest

from capa_simulation.io import bdq_refresh, bdq_token
from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.io.container_start_report import BDQ_USER_NAME_ENV

ACCOUNT = "fakeaccount"
# 가짜 값만 쓴다 — 사내 꼴을 모른다. 심은 값이 어떤 글에도 나오지 않는지 찾는다.
FAKE_TOKEN = "FAKE-bdq-login-token-0000-abcdefghi"
FAKE_REFRESH = "FAKE-bdq-refresh-token-9999-zyxwvuts"
TOKEN_ERROR = "HTTP 401 invalid token"


class Clock:
    """바꿔 끼우는 시각 — 잠들지 않고 옮긴다. 진짜 지금에서 시작해 토큰 파일 수정 시각과 맞는다."""

    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class FakeExchange:
    """가짜 교환 — 부른 수와 받은 값을 세고, 새 가짜 토큰을 준다(또는 `error` 를 낸다)."""

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

    def __call__(self, refresh_token: bytes, account: str) -> bdq_refresh.Exchanged:
        with self._lock:
            self.calls += 1
            number = self.calls
            self.received.append((refresh_token, account))
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
    target = tmp_path / "credential"
    monkeypatch.setattr(bdq_token, "CREDENTIAL_DIR", target)
    monkeypatch.setenv(BDQ_USER_NAME_ENV, ACCOUNT)
    return target


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    moment = Clock()
    monkeypatch.setattr(bdq_refresh, "clock", moment)
    return moment


def turn_on(monkeypatch: pytest.MonkeyPatch, fake: FakeExchange) -> None:
    """요청 꼴을 안 것으로 — 교환 자리를 가짜로 바꿔 끼운다."""
    monkeypatch.setattr(bdq_refresh, "REQUEST_SHAPE_KNOWN", True)
    monkeypatch.setattr(bdq_refresh, "exchange", fake)


def token_file(folder: Path) -> Path:
    return folder / f"bigdataquery.token.{ACCOUNT}"


def lay_out(
    folder: Path,
    clock: Clock,
    *,
    issued_ago: timedelta = timedelta(hours=1),
    source: bdq_token.InstallSource = "start",
    token: str = FAKE_TOKEN,
    refresh: str | None = FAKE_REFRESH,
) -> datetime:
    """시작 스크립트가 남기는 꼴 — 갱신 토큰 파일과 `issued_ago` 앞에 넣은 토큰 · 표지."""
    folder.mkdir(parents=True, exist_ok=True)
    if refresh is not None:
        bdq_token.write_private(folder / f"capa-bdq-refresh.{ACCOUNT}", refresh.encode())
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


def test_the_exchange_says_the_request_shape_is_not_known_yet() -> None:
    assert bdq_refresh.REQUEST_SHAPE_KNOWN is False
    with pytest.raises(bdq_refresh.RefreshNotConfigured) as caught:
        bdq_refresh.exchange(FAKE_REFRESH.encode(), ACCOUNT)
    assert FAKE_REFRESH not in str(caught.value) and ACCOUNT not in str(caught.value)


def test_the_exchanged_token_stays_out_of_its_repr() -> None:
    got = bdq_refresh.Exchanged(FAKE_TOKEN.encode())
    assert FAKE_TOKEN not in repr(got)


def test_the_modes_match_what_the_report_reads() -> None:
    assert set(get_args(bdq_refresh.Mode)) == set(report_contract.REFRESH_MODES)
    assert set(bdq_refresh.MODE_LABELS) == set(report_contract.REFRESH_MODES)


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("nothing", bdq_refresh.NO_REFRESH_TOKEN),
        ("no account", f"{BDQ_USER_NAME_ENV} 없음"),
        ("environment token", f"{bdq_token.LOGIN_TOKEN_ENV} 있음"),
    ],
)
def test_without_a_usable_refresh_token_it_is_off(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch, setup: str, reason: str
) -> None:
    if setup != "nothing":
        lay_out(folder, clock)
    if setup == "no account":
        monkeypatch.delenv(BDQ_USER_NAME_ENV)
    if setup == "environment token":
        monkeypatch.setenv(bdq_token.LOGIN_TOKEN_ENV, "FAKE-env-token-value")

    state = bdq_refresh.status()

    assert (state.mode, state.reason, state.label) == ("off", reason, "꺼짐")


def test_with_a_refresh_token_and_no_request_shape_it_is_ready(folder: Path, clock: Clock) -> None:
    lay_out(folder, clock)

    state = bdq_refresh.status()

    assert (state.mode, state.reason, state.label) == ("ready", "요청 꼴 미정", "준비")


def test_ready_changes_nothing_on_the_query_path(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """지금 꼴(요청 꼴 미정) — 갱신 토큰이 있고 6시간이 지나 갱신할 때여도 교환을 부르지 않고 자격
    폴더는 바이트 · 시각 그대로, 조회 · 실패 · 관리자 표지는 갱신 토큰이 없을 때와 똑같다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    called: list[bytes] = []
    monkeypatch.setattr(bdq_refresh, "exchange", lambda token, _account: called.append(token))
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
    assert fake.received == [(FAKE_REFRESH.encode(), ACCOUNT)]
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
        "exchange",
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


def test_a_missing_token_is_refreshed(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    lay_out(folder, clock)
    token_file(folder).unlink()
    fake = FakeExchange()
    turn_on(monkeypatch, fake)

    bdq_refresh.before_query()

    assert fake.calls == 1 and token_file(folder).is_file()


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
    fake = FakeExchange(error=ConnectionError("refused"))
    turn_on(monkeypatch, fake)
    module = FakeModule(None)

    assert isinstance(query(module), pd.DataFrame)

    assert (fake.calls, module.calls) == (1, 1)
    state = bdq_refresh.status()
    assert (state.mode, state.last_failure) == ("on", "교환 실패(ConnectionError)")


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
    """교환이 갱신 토큰 · 새 토큰을 문구에 실어 실패해도 상태 · 로그 · 조회 예외 · 표지에 없다."""
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    leaked = f"bad request body refresh={FAKE_REFRESH} token={FAKE_TOKEN}"
    fake = FakeExchange(error=RuntimeError(leaked))
    turn_on(monkeypatch, fake)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(adapter.BigDataQueryCallError) as caught:
        query(FakeModule(Exception(TOKEN_ERROR)))

    state = bdq_refresh.status()
    mark = (folder / f"capa-bdq-installed.{ACCOUNT}.json").read_text(encoding="utf-8")
    messages = [record.getMessage() for record in caplog.records]
    texts = [repr(state), str(caught.value), repr(caught.value.__cause__), mark, *messages]
    for secret in (FAKE_REFRESH, FAKE_TOKEN):
        for text in texts:
            assert secret not in text
    assert set(json.loads(mark)) == {"installed_at", "source"}
    assert state.last_failure == "교환 실패(RuntimeError)"


def test_the_refresh_runs_in_a_thread_without_streamlit(
    folder: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """공식버전 자동 갱신 예약 스레드도 조회한다 — 실행 문맥 없이 돌고 Streamlit 을 안 부른다."""
    source = Path(bdq_refresh.__file__).read_text(encoding="utf-8")
    assert "import streamlit" not in source and "from streamlit" not in source
    lay_out(folder, clock, issued_ago=timedelta(hours=7))
    fake = FakeExchange()
    turn_on(monkeypatch, fake)
    errors: list[BaseException] = []

    def run() -> None:
        try:
            query(FakeModule(None))
        except BaseException as error:  # pragma: no cover - 실패만 담는다
            errors.append(error)

    worker = threading.Thread(target=run, name="capa-auto-official-update")
    worker.start()
    worker.join(10)

    assert errors == [] and fake.calls == 1


def test_a_refresh_token_is_due_for_replacement_after_eighty_days(
    folder: Path, clock: Clock
) -> None:
    lay_out(folder, clock)
    refresh_file = folder / f"capa-bdq-refresh.{ACCOUNT}"
    seen = (clock.now - timedelta(days=79, hours=23)).timestamp()
    os.utime(refresh_file, (seen, seen))

    state = bdq_refresh.status()
    assert state.refresh_token_since is not None
    assert bdq_refresh.refresh_token_aging(state) is False

    clock.advance(hours=1)
    assert bdq_refresh.refresh_token_aging(bdq_refresh.status()) is True
    assert bdq_refresh.refresh_token_aging(bdq_refresh.RefreshStatus("off")) is False
