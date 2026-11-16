# Purpose: BDQ 자동 로그인 실행기(결과 갈래 · 잠김 방지 · 다시 로그인 · 비밀 경계)를 검증한다.

"""`io/bdq_login.py` · `io/bdq_login_child.py` 시험.

로그인은 진짜 하위 프로세스가 가짜 `bigdataquery`(`tests/fixtures/bdq_fake/`)를 불러 돈다 — 배너 ·
`input()` · `getpass` 의 표준 입력 폴백 · 토큰 파일 쓰기 · 나뉜 남은 시간까지 사내 2.5.0 확인과 같은
꼴이다. 장면마다 하위 프로세스에서 `login()` 이 불린 수를 센다(`FakeBdq.logins`) — 계정 잠김 방지가
불변식이라 수가 곧 계약이다. 비밀번호는 카나리아 글이고 명령줄 · 하위 환경 · 결과 · 예외 · 로그
어디에도 없어야 한다.
"""

from __future__ import annotations

import errno
import importlib.util
import json
import logging
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from bdq_login_support import (
    ACCOUNT,
    ADMIN_ID,
    MEASURED_FRAGMENTS,
    MEASURED_INNER,
    MEASURED_OUTER,
    OTHER_ACCOUNT,
    PASSWORD,
    WRONG_PASSWORD,
    FakeBdq,
    measured_token_failure,
    requests_on,
    running_mock,
    s3_environment,
    switch_on,
    target_of,
    use_fake_bdq,
)
from s3_mock_store import MockStore

from capa_simulation.auth import names as sso_names
from capa_simulation.io import bdq_login, bdq_login_child, bdq_token
from capa_simulation.io import bdq_login_store as store
from capa_simulation.io.bdq_login_store import LoginSecret
from capa_simulation.io.container_start_report import (
    APP_WITHHELD_ENVIRONMENT,
    BDQ_TOKEN_ENV,
    BDQ_USER_NAME_ENV,
)
from capa_simulation.io.object_storage import MODE_ENV
from capa_simulation.io.s3_small import S3Target

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _fresh_state() -> Iterator[None]:
    bdq_login.forget_state()
    yield
    bdq_login.forget_state()


@pytest.fixture()
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeBdq:
    return use_fake_bdq(monkeypatch, tmp_path)


@pytest.fixture()
def mock_s3() -> Iterator[tuple[MockStore, S3Target]]:
    with running_mock() as (mock, endpoint):
        yield mock, target_of(mock, endpoint)


class Spawned:
    """로그인 하위 프로세스를 띄운 명령줄 · 환경 · 표준 입력을 적는다(그대로 띄운다)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[dict[str, Any]] = []
        real = subprocess.run

        def record(*args: Any, **kwargs: Any) -> Any:
            self.calls.append({"argv": list(args[0]), **kwargs})
            return real(*args, **kwargs)

        monkeypatch.setattr(subprocess, "run", record)


@pytest.fixture()
def spawned(monkeypatch: pytest.MonkeyPatch) -> Spawned:
    return Spawned(monkeypatch)


def scene(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    monkeypatch.setenv("FAKE_BDQ_SCENE", ",".join(names))


def stored_login(
    target: S3Target, key: str, account: str = ACCOUNT, password: str = PASSWORD
) -> store.StoredLogin:
    written = store.save_login(target, key.encode(), LoginSecret(account, password), ADMIN_ID)
    assert written.ok and written.stored is not None
    return written.stored


def stored_meta(mock: MockStore) -> dict[str, object]:
    import json

    with mock.lock:
        data = json.loads(mock.objects[store.OBJECT_KEY])
    assert isinstance(data, dict)
    return data


def object_state(mock: MockStore) -> str:
    state = stored_meta(mock)["state"]
    assert isinstance(state, str)
    return state


# --- 로그인 한 번의 갈래 --------------------------------------------------------------------


def test_a_right_password_is_ok_with_the_remaining_minutes(fake: FakeBdq, spawned: Spawned) -> None:
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.outcome == bdq_login.OUTCOME_OK and result.ok
    assert result.remaining_minutes is not None and 470 <= result.remaining_minutes <= 480
    assert fake.token_path().is_file()
    assert fake.logins() == 1
    call = spawned.calls[0]
    assert call["start_new_session"] is (os.name == "posix")
    assert call["stderr"] is subprocess.DEVNULL
    assert call["timeout"] == bdq_login.LOGIN_TIMEOUT_SECONDS


def test_a_wrong_password_that_only_prints_is_rejected_even_with_a_live_old_token(
    fake: FakeBdq,
) -> None:
    old = fake.write_live_token()
    result = bdq_login.attempt_login(ACCOUNT, WRONG_PASSWORD)
    assert result == bdq_login.LoginResult(
        bdq_login.OUTCOME_REJECTED, bdq_login.REASON_TOKEN_UNCHANGED
    )
    assert fake.token_path().read_bytes() == old
    assert fake.logins() == 1


@pytest.mark.parametrize(
    ("names", "kind"),
    [(("wrong_raises",), "builtins.Exception"), (("exit_on_wrong",), "builtins.SystemExit")],
)
def test_a_wrong_password_that_raises_is_rejected(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, names: tuple[str, ...], kind: str
) -> None:
    fake.write_live_token()
    scene(monkeypatch, *names)
    result = bdq_login.attempt_login(ACCOUNT, WRONG_PASSWORD)
    assert result.outcome == bdq_login.OUTCOME_REJECTED
    assert result.reason == bdq_login.REASON_LOGIN_RAISED
    assert result.error_kind == kind
    assert fake.logins() == 1


def test_only_a_connection_kind_is_unreached(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    scene(monkeypatch, "connection")
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.outcome == bdq_login.OUTCOME_UNREACHED
    assert result.reason == bdq_login.REASON_CONNECTION
    assert result.error_kind == "requests.exceptions.ConnectionError"
    scene(monkeypatch, "connection_context")
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.outcome == bdq_login.OUTCOME_REJECTED
    assert result.error_kind == "builtins.RuntimeError"
    assert fake.logins() == 2


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("wrong_conn_builtin", "builtins.ConnectionError"),
        ("wrong_conn_subclass", None),
        ("wrong_requests_conn_text", "requests.exceptions.ConnectionError"),
        ("wrong_read_timeout", "requests.exceptions.ReadTimeout"),
        ("wrong_http_error_from_conn", "builtins.ConnectionError"),
    ],
)
def test_a_wrong_password_in_a_connection_shape_is_rejected_not_unreached(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, name: str, kind: str | None
) -> None:
    """서버가 답한 401 을 패키지가 연결 꼴(errno 없는 `ConnectionError` · 그 하위 종류 · 글만 든
    `requests` 연결 실패 · 읽기 시간 초과 · HTTP 오류를 원인으로 단 것)로 내도 「닿지 못함」 이
    아니다 — 멈춤으로 가야 재시작마다 틀린 비밀번호로 다시 로그인하지 않는다(계정 잠김 방지)."""
    fake.write_live_token()
    scene(monkeypatch, name)
    result = bdq_login.attempt_login(ACCOUNT, WRONG_PASSWORD)
    assert result.outcome == bdq_login.OUTCOME_REJECTED
    assert result.reason == bdq_login.REASON_LOGIN_RAISED
    if kind is not None:
        assert result.error_kind == kind
    assert fake.logins() == 1


def test_a_child_past_its_time_limit_is_unreached(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    scene(monkeypatch, "slow")
    monkeypatch.setenv("FAKE_BDQ_SLOW_SECONDS", "20")
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD, timeout=3)
    assert result == bdq_login.LoginResult(bdq_login.OUTCOME_UNREACHED, bdq_login.REASON_TIMEOUT)
    assert fake.logins() == 1


def test_a_changed_token_past_the_time_limit_is_unconfirmed_never_unreached_or_rejected(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    """로그인은 토큰을 바꿨는데 남은 시간을 재다 시간을 넘김 — 성공으로 세지 않되(7시간 초과를 못
    봄) 거절도 닿지 못함도 아니다."""
    scene(monkeypatch, "time_slow")
    monkeypatch.setenv("FAKE_BDQ_SLOW_SECONDS", "20")
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD, timeout=3)
    assert result == bdq_login.LoginResult(
        bdq_login.OUTCOME_UNCONFIRMED, bdq_login.REASON_REMAINING_UNKNOWN
    )


def test_a_package_that_fails_to_import_is_unavailable_without_a_login(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    scene(monkeypatch, "import_fails")
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.outcome == bdq_login.OUTCOME_UNAVAILABLE
    assert result.reason == bdq_login.REASON_IMPORT_FAILED
    assert result.error_kind == "builtins.RuntimeError"
    assert fake.imports() == 1 and fake.logins() == 0


def test_a_missing_package_is_unavailable(monkeypatch: pytest.MonkeyPatch, fake: FakeBdq) -> None:
    if importlib.util.find_spec("bigdataquery") is not None:
        pytest.skip("이 환경에는 진짜 bigdataquery 가 있다")
    monkeypatch.delenv("PYTHONPATH")
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.outcome == bdq_login.OUTCOME_UNAVAILABLE
    assert result.error_kind == "builtins.ModuleNotFoundError"
    assert fake.logins() == 0


@pytest.mark.parametrize(
    ("names", "password", "minutes", "reason"),
    [
        (("time_odd",), PASSWORD, None, bdq_login.REASON_REMAINING_UNKNOWN),
        (("time_raises",), PASSWORD, None, bdq_login.REASON_REMAINING_UNKNOWN),
        (("time_short",), PASSWORD, 25, bdq_login.REASON_REMAINING_SHORT),
        (("wrong_truncates",), WRONG_PASSWORD, None, bdq_login.REASON_REMAINING_UNKNOWN),
        (("wrong_writes_garbage",), WRONG_PASSWORD, None, bdq_login.REASON_REMAINING_UNKNOWN),
    ],
)
def test_a_changed_token_without_more_than_seven_hours_is_unconfirmed_never_rejected(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBdq,
    names: tuple[str, ...],
    password: str,
    minutes: int | None,
    reason: str,
) -> None:
    """성공은 「토큰이 바뀌었고 남은 시간이 7시간 초과」(사용자 답)다. 바뀌었어도 남은 시간이 꼴이
    다르거나 · 못 재거나 · 짧으면 — 또 틀린 비밀번호에 패키지가 파일을 비우거나 다른 글로 덮어도 —
    성공이 아니고(폼은 저장하지 않는다), 꼴이 다른 답이 멈춤이 되지도 않는다."""
    fake.write_live_token()
    scene(monkeypatch, *names)
    result = bdq_login.attempt_login(ACCOUNT, password)
    assert result.outcome == bdq_login.OUTCOME_UNCONFIRMED and not result.ok
    assert result.reason == reason
    assert result.remaining_minutes == minutes
    assert fake.logins() == 1


def test_the_misspelled_days_field_is_read(monkeypatch: pytest.MonkeyPatch, fake: FakeBdq) -> None:
    scene(monkeypatch, "time_typo")
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.ok and result.remaining_minutes is not None
    assert 1440 + 470 <= result.remaining_minutes <= 1440 + 480


@pytest.mark.parametrize(
    ("account", "password", "reason"),
    [
        ("", PASSWORD, bdq_login.REASON_BAD_INPUT),
        (ACCOUNT, "", bdq_login.REASON_BAD_INPUT),
        (ACCOUNT, f"{PASSWORD}\nextra", bdq_login.REASON_BAD_INPUT),
        (f"{ACCOUNT}\r", PASSWORD, bdq_login.REASON_BAD_INPUT),
        (f" {ACCOUNT}", PASSWORD, bdq_login.REASON_BAD_INPUT),
        ("../demo", PASSWORD, bdq_login.REASON_BAD_ACCOUNT),
        ("..", PASSWORD, bdq_login.REASON_BAD_ACCOUNT),
    ],
)
def test_values_that_break_the_line_protocol_are_refused_before_spawning(
    fake: FakeBdq, spawned: Spawned, account: str, password: str, reason: str
) -> None:
    result = bdq_login.attempt_login(account, password)
    assert result == bdq_login.LoginResult(bdq_login.OUTCOME_UNAVAILABLE, reason)
    assert spawned.calls == [] and fake.logins() == 0


def test_a_token_put_in_while_a_wrong_login_runs_does_not_count_as_a_new_token(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    """틀린 비밀번호 로그인이 도는 사이 관리자가 「토큰 넣기」 를 누름 — 넣기는 로그인이 끝날 때까지
    기다리고, 로그인 앞뒤 다이제스트는 넣은 토큰을 보지 않는다(거절 그대로)."""
    monkeypatch.setenv(BDQ_USER_NAME_ENV, ACCOUNT)
    fake.write_live_token()
    scene(monkeypatch, "slow")
    monkeypatch.setenv("FAKE_BDQ_SLOW_SECONDS", "2")
    installed: list[str] = []
    started = threading.Event()

    def install() -> None:
        started.wait(timeout=10)
        installed.append(bdq_token.install_token("demo-installed-token-0123456789").status)

    helper = threading.Thread(target=install)
    helper.start()
    real_run = subprocess.run

    def run_and_signal(*args: Any, **kwargs: Any) -> Any:
        started.set()
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run_and_signal)
    result = bdq_login.attempt_login(ACCOUNT, WRONG_PASSWORD, timeout=30)
    helper.join(timeout=30)
    assert result == bdq_login.LoginResult(
        bdq_login.OUTCOME_REJECTED, bdq_login.REASON_TOKEN_UNCHANGED
    )
    assert installed == ["written"]
    assert fake.token_path().read_bytes() == b"demo-installed-token-0123456789"


def test_a_token_environment_variable_blocks_the_login(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, spawned: Spawned
) -> None:
    monkeypatch.setenv(bdq_token.LOGIN_TOKEN_ENV, "demo-token-value-0123456789")
    result = bdq_login.attempt_login(ACCOUNT, PASSWORD)
    assert result.reason == bdq_login.REASON_ENV_TOKEN
    assert spawned.calls == []


_TTY_DRIVER = """
import os, sys
from pathlib import Path
place, out, account, password = sys.argv[1:5]
fd = os.open(place, os.O_RDWR)
try:
    os.close(os.open("/dev/tty", os.O_RDWR))
except OSError:
    Path(out).write_text("no-ctty")
    raise SystemExit(0)
from capa_simulation.io import bdq_login
result = bdq_login.attempt_login(account, password, folder=Path(sys.argv[5]), timeout=10)
Path(out).write_text(result.outcome)
"""


@pytest.mark.skipif(os.name != "posix", reason="제어 터미널은 POSIX 의 것")
def test_a_controlling_terminal_does_not_take_the_password_from_stdin(
    fake: FakeBdq, tmp_path: Path
) -> None:
    """부르는 프로세스에 제어 터미널이 있어도(WebIDE · tmux) `getpass` 가 `/dev/tty` 를 읽어 멈추지
    않고 표준 입력으로 읽는다 — 로그인 하위 프로세스를 새 세션으로 띄운다."""
    master, slave = os.openpty()
    try:
        out = tmp_path / "outcome.txt"
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(PROJECT_ROOT / "src"), os.environ["PYTHONPATH"])),
        }
        subprocess.run(
            [
                sys.executable,
                "-c",
                _TTY_DRIVER,
                os.ttyname(slave),
                str(out),
                ACCOUNT,
                PASSWORD,
                str(fake.credential_dir),
            ],
            env=env,
            start_new_session=True,
            timeout=60,
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        os.close(slave)
        os.close(master)
    outcome = out.read_text(encoding="utf-8")
    if outcome == "no-ctty":
        pytest.skip("이 자리에서는 제어 터미널을 세우지 못한다")
    assert outcome == bdq_login.OUTCOME_OK
    assert fake.logins() == 1


# --- 비밀 경계 ---------------------------------------------------------------------------


def test_the_password_and_account_stay_out_of_argv_environment_results_and_logs(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBdq,
    spawned: Spawned,
    caplog: pytest.LogCaptureFixture,
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    _, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    monkeypatch.setenv(BDQ_TOKEN_ENV, "demo-start-token-0123456789")
    for name in APP_WITHHELD_ENVIRONMENT:
        monkeypatch.setenv(name, f"{name}-secret-value")
    monkeypatch.setenv(sso_names.ENV_SECRET, "demo-jwt-secret-value-0123456789abcdef")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "demo-aws-secret")
    caplog.set_level(logging.DEBUG)
    results: list[object] = []
    results.append(bdq_login.attempt_login(ACCOUNT, WRONG_PASSWORD))
    scene(monkeypatch, "wrong_raises")
    results.append(bdq_login.attempt_login(ACCOUNT, WRONG_PASSWORD))
    scene(monkeypatch)
    results.append(bdq_login.login_from_form(ACCOUNT, PASSWORD, ADMIN_ID))
    results.append(bdq_login.status())
    results.append(bdq_login.start_login(dict(os.environ)))
    for call in spawned.calls:
        command = " ".join(call["argv"])
        assert PASSWORD not in command and WRONG_PASSWORD not in command
        assert ACCOUNT not in command
        env: dict[str, str] = call["env"]
        values = " ".join(env.values())
        assert PASSWORD not in values and WRONG_PASSWORD not in values
        assert ACCOUNT not in values
        assert key not in values
        for name in (
            store.SECRET_KEY_ENV,
            BDQ_TOKEN_ENV,
            *APP_WITHHELD_ENVIRONMENT,
            sso_names.ENV_SECRET,
            "AWS_SECRET_ACCESS_KEY",
        ):
            assert name not in env, name
        assert not any(name.startswith(("CAPA_S3_", "AWS_")) for name in env)
        assert env["PYTHONPATH"] == os.environ["PYTHONPATH"]
    assert len(spawned.calls) == 3
    for item in results:
        text = repr(item)
        assert PASSWORD not in text and WRONG_PASSWORD not in text and ACCOUNT not in text, text
        assert "login failed" not in text and "banner" not in text
    assert PASSWORD not in caplog.text and WRONG_PASSWORD not in caplog.text
    assert ACCOUNT not in caplog.text
    assert key not in caplog.text


def test_child_environment_drops_every_secret_name_and_prefix() -> None:
    environ = {
        **{name: "x" for name in bdq_login.CHILD_WITHHELD_ENVIRONMENT},
        "CAPA_S3_SYNC_MODE": "managed",
        "CAPA_S3_BUCKET": "b",
        "AWS_PROFILE": "p",
        "PYTHONPATH": "/demo/site",
        BDQ_USER_NAME_ENV: "demo_env_user",
        "HOME": "/home/demo",
        "PYTHONIOENCODING": "latin-1",
    }
    env = bdq_login.child_environment(environ)
    assert env == {
        "PYTHONPATH": "/demo/site",
        BDQ_USER_NAME_ENV: "demo_env_user",
        "HOME": "/home/demo",
        "PYTHONIOENCODING": "utf-8",
    }
    for name in (
        store.SECRET_KEY_ENV,
        BDQ_TOKEN_ENV,
        *sso_names.SECRET_ENVIRONMENT,
        *sso_names.WITHHELD_ENVIRONMENT,
    ):
        assert name in bdq_login.CHILD_WITHHELD_ENVIRONMENT


def test_the_command_line_carries_no_values() -> None:
    command = bdq_login.login_command()
    assert command[0] == sys.executable
    assert "-I" not in command and "-E" not in command and "-s" not in command
    assert command[-1] == str(bdq_login.CHILD_SCRIPT)
    assert bdq_login.CHILD_SCRIPT.is_file()


def test_the_light_modules_bring_no_streamlit_pandas_or_cryptography() -> None:
    code = (
        "import sys\n"
        "import capa_simulation.io.bdq_login\n"
        "import capa_simulation.io.bdq_login_store\n"
        "import capa_simulation.io.bdq_login_child\n"
        "print(sorted(n for n in ('streamlit', 'pandas', 'cryptography', 'duckdb', 'bigdataquery')"
        " if n in sys.modules))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
    )
    assert completed.stdout.strip() == "[]"


# --- 표지 · 남은 분 ------------------------------------------------------------------------


def test_only_the_last_well_formed_marker_line_counts() -> None:
    line = bdq_login_child.marker_line("done", minutes=419)
    banner = b"=== banner ===\nAD Account : Password : login failed for demo_user\n"
    found = bdq_login.parse_marker(banner + line.encode() + b"\n")
    assert found == bdq_login.Marker("done", "", False, 419, "")
    earlier = bdq_login_child.marker_line("login", error="pkg.Error", net=True)
    found = bdq_login.parse_marker(f"{earlier}\n{line}\n".encode())
    assert found is not None and found.stage == "done"
    assert bdq_login.parse_marker(banner) is None
    assert bdq_login.parse_marker(f"{line} {PASSWORD}\n".encode()) is None
    assert bdq_login.parse_marker(f"{line}\n{bdq_login_child.MARKER} stage=x\n".encode()) is None
    assert bdq_login.parse_marker(b"\xff\xfe" + line.encode()) is None
    weird = bdq_login_child.marker_line("login", error="pkg.<locals>.Err")
    assert bdq_login.parse_marker(weird.encode()) is None


def test_qualified_names_are_sanitized_for_the_marker() -> None:
    def local_error() -> Exception:
        class Err(Exception):
            pass

        return Err()

    name = bdq_login_child.qualified_name(local_error())
    assert "<" not in name and ">" not in name
    line = bdq_login_child.marker_line("login", error=name)
    found = bdq_login.parse_marker(line.encode())
    assert found is not None and found.error == name


@pytest.mark.parametrize(
    ("answer", "minutes"),
    [
        ({"remaining_days": 0, "remaining_hours": 7, "remaining_minutes": 59}, 479),
        ({"remining_days": 1, "remaining_hours": 0, "remaining_minutes": 5}, 1445),
        ({"remaining_hours": 7, "remaining_minutes": 23}, 443),
        ({"remaining_days": "1", "remaining_hours": 2.0, "remaining_minutes": "3"}, 1563),
        ({"remaining_hours": 7}, None),
        ({"remaining_days": True, "remaining_hours": 7, "remaining_minutes": 1}, None),
        ({"remaining_days": 0, "remaining_hours": -1, "remaining_minutes": 1}, None),
        ({"remaining_days": 0, "remaining_hours": 1.5, "remaining_minutes": 1}, None),
        ({"expiration_date": "2026-11-16 18:00:00"}, None),
        ([0, 7, 59], None),
        (None, None),
    ],
)
def test_remaining_minutes_joins_the_split_fields(answer: object, minutes: int | None) -> None:
    assert bdq_login_child.remaining_minutes(answer) == minutes


def test_the_unreached_evidence_follows_only_explicit_causes() -> None:
    refused = ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")
    connect_timeout = TimeoutError(errno.ETIMEDOUT, "Connection timed out")

    def caused() -> BaseException:
        try:
            try:
                raise refused
            except ConnectionRefusedError as error:
                raise RuntimeError("wrapped") from error
        except RuntimeError as wrapped:
            return wrapped

    def context_only() -> BaseException:
        try:
            try:
                raise connect_timeout
            except TimeoutError:
                raise RuntimeError("auth") from None
        except RuntimeError as wrapped:
            return wrapped

    assert bdq_login_child.is_unreached(connect_timeout)
    assert bdq_login_child.is_unreached(caused())
    assert not bdq_login_child.is_unreached(context_only())
    assert not bdq_login_child.is_unreached(ValueError("timeout connection refused"))


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _real_request_error(*, read_timeout: bool = False) -> BaseException:
    """`requests` 가 스스로 만든 실패 — 닫힌 포트(연결 거절) 또는 답하지 않는 소켓(읽기 시간
    초과)."""
    import requests

    session = requests.Session()
    session.trust_env = False
    if not read_timeout:
        with pytest.raises(requests.exceptions.ConnectionError) as refused:
            session.post(f"http://127.0.0.1:{_closed_port()}/auth", timeout=5)
        return refused.value
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = int(listener.getsockname()[1])
        with pytest.raises(requests.exceptions.ReadTimeout) as late:
            session.post(f"http://127.0.0.1:{port}/auth", data=b"x", timeout=(5, 0.5))
        return late.value


def test_the_unreached_evidence_is_the_connect_stage_not_the_kind_name() -> None:
    """닿지 못함은 요청을 보내기 전(연결 단계)의 양의 증거뿐이다 — 라이브러리가 만든 연결 거절 ·
    errno 가 붙은 OS 연결 오류 · 이름 풀기. 종류 이름만 맞은 것(errno 없는 `ConnectionError` · 글만
    든 `requests` 연결 실패 · 응답을 든 것)과 요청이 이미 간 뒤의 것(읽기 시간 초과 · 끊김 · errno
    없는 `socket.timeout`)은 아니다."""
    import requests

    real_refusal = _real_request_error()
    assert bdq_login_child.is_unreached(real_refusal)
    assert bdq_login_child.is_unreached(ConnectionRefusedError(errno.ECONNREFUSED, "refused"))
    assert bdq_login_child.is_unreached(OSError(errno.EHOSTUNREACH, "No route to host"))
    assert bdq_login_child.is_unreached(socket.gaierror(socket.EAI_NONAME, "Name not known"))
    wrapped = RuntimeError("login failed")
    wrapped.__cause__ = real_refusal
    assert bdq_login_child.is_unreached(wrapped)

    assert not bdq_login_child.is_unreached(_real_request_error(read_timeout=True))
    assert not bdq_login_child.is_unreached(ConnectionError("HTTP Response Code : 401"))
    assert not bdq_login_child.is_unreached(ConnectionRefusedError())
    assert not bdq_login_child.is_unreached(ConnectionResetError(errno.ECONNRESET, "reset"))
    assert not bdq_login_child.is_unreached(TimeoutError("timed out"))
    assert not bdq_login_child.is_unreached(
        requests.exceptions.ConnectionError("Auth Connection failed: HTTP Response Code : 401")
    )
    assert not bdq_login_child.is_unreached(requests.exceptions.ConnectTimeout("connect (text)"))
    answered = requests.Response()
    answered.status_code = 401
    assert not bdq_login_child.is_unreached(
        requests.exceptions.ConnectionError(real_refusal.args[0], response=answered)
    )
    library_kind = type(
        "BdqConnectionError", (requests.exceptions.ConnectionError,), {"__module__": "bigdataquery"}
    )
    assert not bdq_login_child.is_unreached(library_kind("HTTP Response Code : 401"))


# --- 다시 로그인의 문 ----------------------------------------------------------------------


def token_error(
    name: str = "TokenNotFoundException", module: str = "bigdataquery.exceptions"
) -> type[Exception]:
    return type(name, (Exception,), {"__module__": module})


def test_the_named_package_token_kinds_open_the_relogin() -> None:
    token = token_error()
    child = type("TokenExpiredLater", (token,), {"__module__": "bigdataquery.exceptions"})
    assert bdq_login.is_relogin_error(token("no token for demo"))
    assert bdq_login.is_relogin_error(child())
    wrapped = RuntimeError("wrapped")
    wrapped.__cause__ = token()
    assert bdq_login.is_relogin_error(wrapped)
    assert not bdq_login.is_relogin_error(token_error(module="other.exceptions")())
    assert not bdq_login.is_relogin_error(RuntimeError("invalid token: token has expired"))
    assert not bdq_login.is_relogin_error(token_error("InvalidTokenException")())


@pytest.mark.parametrize("link", ["context", "cause"])
def test_the_measured_invalid_token_chain_opens_the_relogin(link: str) -> None:
    """만료 · 무효 토큰의 `getData`(2026-11-16 사내 실측) — 바깥 `ConnectionError` · 안쪽
    `Exception`. 둘 다 `bigdataquery.exceptions` 종류가 아니어서 안쪽 글의 문구
    (`RELOGIN_MESSAGES`)로 건다 — 안쪽이 문맥이든 원인이든, 바깥 `ConnectionError` 를 연결로 먼저
    가르지 않는다."""
    failure = measured_token_failure(link)
    inner = failure.__cause__ if link == "cause" else failure.__context__
    assert type(failure) is ConnectionError and type(inner) is Exception
    assert (failure.__cause__ is None, failure.__context__ is None) == (
        link == "context",
        link == "cause",
    )
    assert bdq_login.is_relogin_error(failure)
    assert bdq_login.is_relogin_error(Exception(MEASURED_INNER))
    assert bdq_login.is_relogin_error(RuntimeError(MEASURED_INNER.upper()))
    deep = RuntimeError("wrapped twice")
    deep.__context__ = ValueError("wrapped once")
    deep.__context__.__cause__ = failure
    assert bdq_login.is_relogin_error(deep)


@pytest.mark.parametrize(
    "error",
    [
        ConnectionError(MEASURED_OUTER),
        RuntimeError("invalid token: token has expired"),
        RuntimeError("HTTP 500 invalid token"),
        RuntimeError("Token expired"),
        RuntimeError("Syntax error: unexpected token"),
        RuntimeError("ParseException: invalid token near 'FROM'"),
        ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused"),
    ],
)
def test_only_the_phrase_in_the_constant_opens_the_relogin(error: BaseException) -> None:
    """문구 상수 밖 — 문구 없는 바깥 `ConnectionError` 하나 · 그 밖의 토큰 낱말 · 구문 오류의
    token · 연결 거절은 다시 로그인을 걸지 않는다(알림만 — 어댑터 갈래)."""
    assert not bdq_login.is_relogin_error(error)


def test_every_relogin_phrase_is_a_plain_casefolded_phrase() -> None:
    """문구 상수는 비지 않은 소문자 문구만 — 빈 글은 모든 예외에 맞는다."""
    assert bdq_login.RELOGIN_MESSAGES
    for message in bdq_login.RELOGIN_MESSAGES:
        assert message and message == message.casefold() == message.strip(), message
        assert message in MEASURED_INNER.casefold(), message


_FAKE_TOKEN_SCRIPT = """
import json
import sys

import bigdataquery

from capa_simulation.io import bdq_login

out = {"time": bigdataquery.getTokenTime(sys.argv[1])}
try:
    bigdataquery.getData(param="SELECT 1", user_name=sys.argv[1])
except BaseException as error:
    inner = error.__context__
    out["outer"] = type(error).__name__
    out["inner"] = type(inner).__name__ if inner is not None else None
    out["cause"] = error.__cause__ is not None
    out["relogin"] = bdq_login.is_relogin_error(error)
    out["kinds"] = [type(link).__module__ for link in (error, inner) if link is not None]
print(json.dumps(out))
"""


@pytest.mark.parametrize("state", ["expired", "revoked"])
def test_the_fake_package_answers_a_dead_token_like_the_internal_measurement(
    state: str, monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    """가짜 패키지가 2026-11-16 사내 실측 꼴을 낸다 — 만료 토큰의 `getTokenTime` 은 예외 없이 그
    문구를 찍고 0/0/0, 만료 · 무효(다른 로그인으로 밀려남) 토큰의 `getData` 는 바깥
    `ConnectionError` · 안쪽 `Exception`(문맥만 — 원인 없음)이고 둘 다 패키지 종류가 아니다."""
    if state == "expired":
        fake.write_expired_token()
    else:
        monkeypatch.setenv("FAKE_BDQ_REVOKED", fake.write_live_token().decode("ascii"))
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(PROJECT_ROOT / "src"), os.environ["PYTHONPATH"])),
    }
    completed = subprocess.run(
        [sys.executable, "-c", _FAKE_TOKEN_SCRIPT, ACCOUNT],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    out = json.loads(completed.stdout.strip().splitlines()[-1])
    assert (out["outer"], out["inner"], out["cause"], out["relogin"]) == (
        "ConnectionError",
        "Exception",
        False,
        True,
    )
    assert out["kinds"] == ["builtins", "builtins"]
    names = ("remaining_days", "remaining_hours", "remaining_minutes")
    left = [out["time"][name] for name in names]
    if state == "expired":
        assert left == [0, 0, 0]
        assert "The token already has expired at" in completed.stdout
    else:
        assert left[1] >= 7
        assert "already has expired" not in completed.stdout


# --- 자동 시도의 잠김 방지 --------------------------------------------------------------------


def test_a_rejected_auto_attempt_stops_in_process_and_in_the_object(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    fake.write_live_token()
    stored = stored_login(target, key, password=WRONG_PASSWORD)
    with mock.lock:
        cipher_before = mock.objects[store.OBJECT_KEY]
    seen = bdq_login.token_digest(ACCOUNT)
    recovery = bdq_login.recover_after_token_failure(seen)
    assert not recovery.retry and not recovery.logged_in
    assert recovery.attempt is not None and recovery.attempt.result is not None
    assert recovery.attempt.result.outcome == bdq_login.OUTCOME_REJECTED
    assert recovery.attempt.stop_write == ""
    assert object_state(mock) == "stopped"
    import json

    with mock.lock:
        after = json.loads(mock.objects[store.OBJECT_KEY])
    assert after["cipher"] == json.loads(cipher_before)["cipher"] == stored.cipher
    assert after["stop_reason"] == bdq_login.REASON_TOKEN_UNCHANGED
    again = bdq_login.recover_after_token_failure(seen)
    assert again.attempt is not None and again.attempt.skipped == bdq_login.SKIP_STOPPED
    status = bdq_login.status()
    assert status.state == "stopped" and not status.active
    assert status.stop_reason == bdq_login.REASON_TOKEN_UNCHANGED
    assert fake.logins() == 1


def test_a_stop_that_cannot_be_written_still_stops_the_process(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    """시도 표시는 썼는데 결과(거절의 멈춤)를 적지 못함 — 객체는 시도 표시(멈춤)로 남고 프로세스도
    멈춘다. 로그인은 한 번뿐."""
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stored_login(target, key, password=WRONG_PASSWORD)
    mock.force_on("PUT", store.SECRETS_PREFIX, after=1, times=100, status=500)
    recovery = bdq_login.recover_after_token_failure(bdq_login.token_digest(ACCOUNT))
    assert recovery.attempt is not None
    assert recovery.attempt.stop_write.startswith(store.WRITE_FAILED)
    assert stored_meta(mock)["stop_reason"] == bdq_login.REASON_ATTEMPTING
    assert object_state(mock) == "stopped"
    for _ in range(3):
        skipped = bdq_login.recover_after_token_failure(bdq_login.token_digest(ACCOUNT))
        assert skipped.attempt is not None and skipped.attempt.skipped == bdq_login.SKIP_STOPPED
    status = bdq_login.status()
    assert status.state == "stopped"
    assert status.stop_reason == bdq_login.REASON_TOKEN_UNCHANGED
    assert fake.logins() == 1


def test_an_unwritable_attempt_mark_means_no_login(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    """시도 표시를 쓰지 못하면 로그인하지 않는다(멈춤 아님 · 쉰다) — 결과를 적을 길이 없는 채로
    로그인하면 재시작이 그 결과를 모른다."""
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stored_login(target, key, password=WRONG_PASSWORD)
    mock.force["PUT"] = (500, "InternalError")
    recovery = bdq_login.recover_after_token_failure(bdq_login.token_digest(ACCOUNT))
    assert recovery.attempt is not None and recovery.attempt.result is None
    assert recovery.attempt.skipped == bdq_login.SKIP_UNGUARDED
    assert recovery.attempt.stop_write.startswith(store.WRITE_FAILED)
    assert not recovery.retry
    assert object_state(mock) == "ok"
    again = bdq_login.recover_after_token_failure(bdq_login.token_digest(ACCOUNT))
    assert again.attempt is not None and again.attempt.skipped == bdq_login.SKIP_PAUSED
    assert bdq_login.status().state == "ok"
    assert fake.logins() == 0


def test_unreached_attempts_pause_and_stop_at_the_limit(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stored_login(target, key)
    scene(monkeypatch, "connection")
    clock = [1000.0]
    monkeypatch.setattr(bdq_login, "_monotonic", lambda: clock[0])
    outcomes: list[str] = []
    for _ in range(8):
        recovery = bdq_login.recover_after_token_failure(bdq_login.token_digest(ACCOUNT))
        assert recovery.attempt is not None
        attempt = recovery.attempt
        outcomes.append(attempt.result.outcome if attempt.result else attempt.skipped)
        clock[0] += bdq_login.UNREACHED_PAUSE_SECONDS / 2
    assert outcomes == [
        "unreached",
        "paused",
        "unreached",
        "paused",
        "unreached",
        "stopped",
        "stopped",
        "stopped",
    ]
    assert fake.logins() == bdq_login.MISS_LIMIT
    assert object_state(mock) == "stopped"
    assert stored_meta(mock)["stop_reason"] == bdq_login.REASON_MISS_LIMIT
    status = bdq_login.status()
    assert status.state == "stopped" and status.stop_reason == bdq_login.REASON_MISS_LIMIT


def test_an_ok_attempt_resets_the_streak(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    _, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stored_login(target, key)
    clock = [0.0]
    monkeypatch.setattr(bdq_login, "_monotonic", lambda: clock[0])
    scene(monkeypatch, "connection")
    for _ in range(2):
        bdq_login.recover_after_token_failure(bdq_login.token_digest(ACCOUNT))
        clock[0] += bdq_login.UNREACHED_PAUSE_SECONDS + 1
    view = bdq_login.current_view()
    assert (view.state, view.trouble, view.trouble_reason) == (
        "ok",
        bdq_login.OUTCOME_UNREACHED,
        bdq_login.REASON_CONNECTION,
    )
    scene(monkeypatch)
    recovery = bdq_login.recover_after_token_failure(bdq_login.token_digest(ACCOUNT))
    assert recovery.retry and recovery.logged_in
    assert bdq_login.status().streak == 0
    assert bdq_login.current_view().trouble == ""
    assert fake.logins() == 3


# --- 조회 중 다시 로그인 -------------------------------------------------------------------


def query_reading_the_token(fake: FakeBdq, stale: bytes, calls: list[int]) -> Callable[[], str]:
    """토큰 파일이 옛 내용이면 토큰 예외, 바뀌었으면 성공하는 조회."""
    error = token_error()

    def query() -> str:
        calls.append(1)
        if fake.token_path().read_bytes() == stale:
            raise error("There is no bigdataquery token issued for AD user (fake)")
        return "rows"

    return query


def test_a_token_error_logs_in_again_and_repeats_the_query_once(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    _, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stale = fake.write_live_token()
    stored_login(target, key)
    calls: list[int] = []
    assert bdq_login.run_with_relogin(query_reading_the_token(fake, stale, calls)) == "rows"
    assert len(calls) == 2 and fake.logins() == 1
    assert bdq_login.status().last is not None


def test_two_queries_failing_together_log_in_once(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    _, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stale = fake.write_live_token()
    stored_login(target, key)
    barrier = threading.Barrier(2)
    error = token_error()
    answers: list[str] = []
    failures: list[BaseException] = []

    def query() -> str:
        if fake.token_path().read_bytes() == stale:
            barrier.wait(timeout=10)
            raise error("stale")
        return "rows"

    def worker() -> None:
        try:
            answers.append(bdq_login.run_with_relogin(query))
        except BaseException as caught:
            failures.append(caught)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert failures == []
    assert answers == ["rows", "rows"]
    assert fake.logins() == 1


def test_a_second_token_error_after_our_own_login_stops(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    fake.write_live_token()
    stored_login(target, key)
    error = token_error()
    calls: list[int] = []

    def query() -> str:
        calls.append(1)
        raise error(f"still no token {len(calls)}")

    with pytest.raises(error) as caught:
        bdq_login.run_with_relogin(query)
    assert str(caught.value) == "still no token 2"
    assert caught.value.__context__ is None
    assert len(calls) == 2 and fake.logins() == 1
    assert object_state(mock) == "stopped"
    status = bdq_login.status()
    assert status.state == "stopped"
    assert status.stop_reason == bdq_login.REASON_TOKEN_AFTER_LOGIN
    with pytest.raises(error):
        bdq_login.run_with_relogin(query)
    assert fake.logins() == 1


@pytest.mark.parametrize("link", ["context", "cause"])
def test_a_measured_expiry_logs_in_again_and_repeats_the_query_once(
    link: str,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBdq,
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    """만료 · 무효 토큰의 실측 꼴 사슬(안쪽이 문맥 · 원인 둘 다) — 다시 로그인 1번, 같은 조회 1번
    다시."""
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stale = fake.write_expired_token()
    stored_login(target, key)
    calls: list[int] = []

    def query() -> str:
        calls.append(1)
        if fake.token_path().read_bytes() == stale:
            raise measured_token_failure(link)
        return "rows"

    assert bdq_login.run_with_relogin(query) == "rows"
    assert len(calls) == 2 and fake.logins() == 1
    assert object_state(mock) == "ok" and bdq_login.status().state == "ok"


@pytest.mark.parametrize("link", ["context", "cause"])
def test_a_measured_failure_again_after_our_own_login_stops(
    link: str,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBdq,
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    """스스로 다시 로그인한 뒤 다시 한 조회도 같은 사슬 — 멈춤을 저장한다(D4). 다시 한 조회의
    예외가 그대로 올라가고, 멈춘 뒤의 같은 실패는 로그인하지 않는다."""
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    fake.write_expired_token()
    stored_login(target, key)
    failures: list[BaseException] = []

    def query() -> str:
        failures.append(measured_token_failure(link))
        raise failures[-1]

    with pytest.raises(ConnectionError) as caught:
        bdq_login.run_with_relogin(query)
    assert len(failures) == 2 and caught.value is failures[1]
    assert caught.value.__context__ is not failures[0]
    assert fake.logins() == 1
    assert object_state(mock) == "stopped"
    assert stored_meta(mock)["stop_reason"] == bdq_login.REASON_TOKEN_AFTER_LOGIN
    status = bdq_login.status()
    assert status.state == "stopped"
    assert status.stop_reason == bdq_login.REASON_TOKEN_AFTER_LOGIN
    with pytest.raises(ConnectionError):
        bdq_login.run_with_relogin(query)
    assert len(failures) == 3 and fake.logins() == 1


def test_the_relogin_phrase_stays_out_of_results_logs_and_the_object(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBdq,
    mock_s3: tuple[MockStore, S3Target],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """문구는 판정에만 쓴다 — 다시 로그인 · 멈춤까지 간 길의 로그 · 결과 · 상태 · 저장 객체에 문구
    조각이 없다(문구에는 계정이 실릴 수 있다)."""
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    fake.write_expired_token()
    stored_login(target, key)

    def query() -> str:
        raise measured_token_failure()

    caplog.set_level(logging.DEBUG)
    with pytest.raises(ConnectionError):
        bdq_login.run_with_relogin(query)
    status = bdq_login.status()
    assert status.last is not None
    with mock.lock:
        saved = mock.objects[store.OBJECT_KEY].decode("utf-8")
    seen = " ".join(
        (
            caplog.text,
            repr(status),
            status.stop_reason,
            repr(bdq_login.current_view()),
            saved,
        )
    ).casefold()
    assert status.state == "stopped"
    for fragment in MEASURED_FRAGMENTS:
        assert fragment.casefold() not in seen, fragment


def test_a_retry_after_someone_else_renewed_that_still_fails_does_not_stop(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    """누가 이미 다시 로그인해(토큰이 바뀜) 로그인 없이 다시 한 조회가 또 토큰 오류 — 이 프로세스는
    로그인하지 않았으니 멈추지 않는다(멈춤은 스스로 로그인한 뒤의 둘째 토큰 오류에만 — D4)."""
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stored_login(target, key)
    fake.write_live_token()
    error = token_error()
    calls: list[int] = []

    def query() -> str:
        calls.append(1)
        if len(calls) == 1:
            fake.token_path().write_bytes(b"renewed-by-someone-else_1")
        raise error("still")

    with pytest.raises(error):
        bdq_login.run_with_relogin(query)
    assert len(calls) == 2 and fake.logins() == 0
    assert object_state(mock) == "ok"
    assert bdq_login.status().state == "ok"


def test_a_restart_with_a_stored_stop_never_logs_in_until_the_form(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, tmp_path: Path
) -> None:
    """멈춤이 저장된 채 재시작 — 시작 스크립트도, 앱으로 바뀐 프로세스의 조회 토큰 예외도 로그인하지
    않는다(멈춤을 넘겨받을 시작 거절이 없어도 객체의 멈춤 하나로). 폼으로 다시 넣어 성공하면
    풀린다."""
    import json

    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "start.json")
    with running_mock() as (mock, endpoint):
        target = target_of(mock, endpoint)
        key = switch_on(monkeypatch)
        stored = stored_login(target, key)
        assert store.mark_stopped(target, "token_after_login", cipher=stored.cipher).ok
        bdq_login.forget_state()
        started = bdq_login.start_login(start_environment(mock, endpoint, key))
        assert started.status == "stopped" and fake.logins() == 0
        (tmp_path / "start.json").write_text(
            json.dumps({"bdq_login": {"status": "stopped", "reason": "token_after_login"}}),
            encoding="utf-8",
        )
        bdq_login.forget_state()
        monkeypatch.setattr(store, "app_target", lambda: target)
        switch_on(monkeypatch, key)
        bdq_login.start_in_app(os.environ)
        assert bdq_login.current_view().state == "stopped"
        error = token_error()

        def query() -> str:
            if not fake.token_path().is_file():
                raise error("no token")
            return "rows"

        for _ in range(3):
            with pytest.raises(error):
                bdq_login.run_with_relogin(query)
        assert fake.logins() == 0
        assert object_state(mock) == "stopped"
        form = bdq_login.login_from_form(ACCOUNT, PASSWORD, ADMIN_ID)
        assert form.saved and fake.logins() == 1
        fake.token_path().unlink()
        assert bdq_login.run_with_relogin(query) == "rows"
        assert fake.logins() == 2


@pytest.mark.parametrize(
    ("make", "logins"),
    [
        (lambda: measured_token_failure("context"), 1),
        (lambda: RuntimeError(MEASURED_INNER), 1),
        (lambda: RuntimeError("invalid token: token has expired"), 0),
        (lambda: RuntimeError("HTTP 500 invalid token"), 0),
        (lambda: ConnectionError(MEASURED_OUTER), 0),
        (lambda: RuntimeError("Syntax error: unexpected token"), 0),
    ],
)
def test_only_the_constant_phrase_logs_in_and_other_token_words_only_alert(
    make: Callable[[], BaseException],
    logins: int,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBdq,
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    """2026-11-16 사용자 결정 — 다시 로그인은 문구 「You have invalid token」(`RELOGIN_MESSAGES`)
    기준이다. 그 문구면 다시 로그인 1번 + 같은 조회 1번 다시, 그 밖의 토큰 낱말만 맞은 실패 · 문구
    없는 바깥 `ConnectionError` · 구문 오류는 로그인 없이 원래 실패 그대로다(알림만)."""
    _, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stale = fake.write_live_token()
    stored_login(target, key)
    failures: list[BaseException] = []

    def query() -> str:
        if fake.token_path().read_bytes() == stale:
            failures.append(make())
            raise failures[-1]
        return "rows"

    if logins:
        assert bdq_login.run_with_relogin(query) == "rows"
    else:
        with pytest.raises(Exception) as caught:
            bdq_login.run_with_relogin(query)
        assert caught.value is failures[0]
    assert len(failures) == 1 and fake.logins() == logins


def test_with_nothing_stored_the_query_runs_as_before(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBdq,
    spawned: Spawned,
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    mock, target = mock_s3
    monkeypatch.setattr(store, "app_target", lambda: target)
    error = token_error()
    failure = error("no token")
    calls: list[int] = []

    def query() -> str:
        calls.append(1)
        raise failure

    with pytest.raises(error) as caught:
        bdq_login.run_with_relogin(query)
    assert caught.value is failure and len(calls) == 1
    assert bdq_login.run_with_relogin(lambda: "rows") == "rows"
    switch_on(monkeypatch)
    store.forget_state()
    with pytest.raises(error):
        bdq_login.run_with_relogin(query)
    assert len(calls) == 2
    assert spawned.calls == [] and fake.logins() == 0
    assert requests_on(mock, store.OBJECT_KEY) == ["GET"]
    assert bdq_login.start_login({}) == bdq_login.StartLogin("off", store.REASON_NOT_MANAGED)
    assert not bdq_login.status().active


# --- 폼 ---------------------------------------------------------------------------------


def test_a_failed_form_login_saves_nothing_and_keeps_what_was_there(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stored_login(target, key)
    with mock.lock:
        before = mock.objects[store.OBJECT_KEY]
    fake.write_live_token(OTHER_ACCOUNT)
    outcome = bdq_login.login_from_form(OTHER_ACCOUNT, WRONG_PASSWORD, ADMIN_ID)
    assert not outcome.saved and outcome.result.outcome == bdq_login.OUTCOME_REJECTED
    with mock.lock:
        assert mock.objects[store.OBJECT_KEY] == before
    assert store.effective_account() == ACCOUNT
    assert fake.logins() == 1


@pytest.mark.parametrize(
    ("name", "password"), [("wrong_writes_garbage", WRONG_PASSWORD), ("time_short", PASSWORD)]
)
def test_an_unconfirmed_form_login_saves_nothing(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBdq,
    mock_s3: tuple[MockStore, S3Target],
    name: str,
    password: str,
) -> None:
    """폼 저장은 사용자 판정 그대로 — 토큰이 바뀌었어도 남은 시간 7시간 초과를 보지 못하면 저장하지
    않고 앞 저장 · 상태를 그대로 둔다(D5)."""
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stored_login(target, key)
    with mock.lock:
        before = mock.objects[store.OBJECT_KEY]
    scene(monkeypatch, name)
    outcome = bdq_login.login_from_form(OTHER_ACCOUNT, password, ADMIN_ID)
    assert not outcome.saved
    assert outcome.result.outcome == bdq_login.OUTCOME_UNCONFIRMED
    with mock.lock:
        assert mock.objects[store.OBJECT_KEY] == before
    assert store.effective_account() == ACCOUNT
    assert fake.logins() == 1


def test_a_form_success_saves_and_lifts_a_stop(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stored_login(target, key, password=WRONG_PASSWORD)
    bdq_login.recover_after_token_failure(bdq_login.token_digest(ACCOUNT))
    assert bdq_login.status().state == "stopped"
    outcome = bdq_login.login_from_form(OTHER_ACCOUNT, PASSWORD, ADMIN_ID)
    assert outcome.saved and outcome.result.ok and outcome.save_failure == ""
    assert object_state(mock) == "ok"
    status = bdq_login.status()
    assert status.state == "ok" and status.active and status.streak == 0
    assert status.load.stored is not None and status.load.stored.entered_by == ADMIN_ID[:2]
    assert store.effective_account() == OTHER_ACCOUNT
    assert fake.logins() == 2
    assert fake.token_path(OTHER_ACCOUNT).is_file()


def test_a_form_login_whose_save_fails_reports_it_and_keeps_the_old_login(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stored_login(target, key)
    mock.force["PUT"] = (500, "InternalError")
    outcome = bdq_login.login_from_form(OTHER_ACCOUNT, PASSWORD, ADMIN_ID)
    assert outcome.result.ok and not outcome.saved
    assert outcome.save_failure.startswith(store.WRITE_FAILED)
    assert store.effective_account() == ACCOUNT


def test_the_form_does_not_try_while_switched_off(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, spawned: Spawned
) -> None:
    outcome = bdq_login.login_from_form(ACCOUNT, PASSWORD, ADMIN_ID)
    assert outcome == bdq_login.FormResult(
        bdq_login.LoginResult(bdq_login.OUTCOME_UNAVAILABLE, store.REASON_NOT_MANAGED)
    )
    monkeypatch.setenv(MODE_ENV, "managed")
    assert bdq_login.login_from_form(ACCOUNT, PASSWORD, ADMIN_ID).result.reason == (
        store.REASON_NO_KEY
    )
    assert spawned.calls == [] and fake.logins() == 0


def test_forget_login_removes_the_object_and_resets(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    monkeypatch.setenv(BDQ_USER_NAME_ENV, "demo_env_user")
    stored_login(target, key)
    assert bdq_login.forget_login().ok
    with mock.lock:
        assert store.OBJECT_KEY not in mock.objects
    assert bdq_login.status().state == "none"
    assert store.effective_account() == "demo_env_user"


# --- 시작 -------------------------------------------------------------------------------


def start_environment(mock: MockStore, endpoint: str, key: str) -> dict[str, str]:
    return {
        **os.environ,
        **s3_environment(mock, endpoint),
        MODE_ENV: "managed",
        store.SECRET_KEY_ENV: key,
    }


def test_start_logs_in_with_an_ok_object(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, spawned: Spawned
) -> None:
    with running_mock() as (mock, endpoint):
        key = switch_on(monkeypatch)
        environ = start_environment(mock, endpoint, key)
        assert bdq_login.start_login(environ).status == "absent"
        stored_login(target_of(mock, endpoint), key)
        store.forget_state()
        started = bdq_login.start_login(environ)
        assert started.status == "ok" and started.result is not None and started.result.ok
        assert started.stored is not None and started.stored.secret.account == ACCOUNT
        assert fake.logins() == 1
        env = spawned.calls[0]["env"]
        assert store.SECRET_KEY_ENV not in env
        assert not any(name.startswith("CAPA_S3_") for name in env)


def test_start_stores_a_stop_and_then_never_tries_again(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    with running_mock() as (mock, endpoint):
        key = switch_on(monkeypatch)
        environ = start_environment(mock, endpoint, key)
        fake.write_live_token()
        stored_login(target_of(mock, endpoint), key, password=WRONG_PASSWORD)
        first = bdq_login.start_login(environ)
        assert first.status == "rejected" and first.stop_write == ""
        assert object_state(mock) == "stopped"
        for _ in range(3):
            bdq_login.forget_state()
            again = bdq_login.start_login(environ)
            assert again.status == "stopped"
            assert again.reason == bdq_login.REASON_TOKEN_UNCHANGED
        assert fake.logins() == 1


def test_start_with_a_broken_object_or_a_wrong_key_is_absent(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, spawned: Spawned
) -> None:
    with running_mock() as (mock, endpoint):
        key = switch_on(monkeypatch)
        stored_login(target_of(mock, endpoint), key)
        other = switch_on(monkeypatch)
        started = bdq_login.start_login(start_environment(mock, endpoint, other))
        assert started.status == "absent" and started.reason == store.REASON_UNDECRYPTABLE
        mock.put(store.OBJECT_KEY, b"{broken")
        started = bdq_login.start_login(start_environment(mock, endpoint, key))
        assert started == bdq_login.StartLogin("absent", store.REASON_BROKEN)
        no_key = {k: v for k, v in start_environment(mock, endpoint, key).items()}
        no_key.pop(store.SECRET_KEY_ENV)
        requests_before = len(mock.requests)
        assert bdq_login.start_login(no_key) == bdq_login.StartLogin("off", store.REASON_NO_KEY)
        assert len(mock.requests) == requests_before
        assert spawned.calls == [] and fake.logins() == 0


# --- 재시작을 건너는 잠김 방지 ----------------------------------------------------------------


def test_persistent_unreached_starts_stop_at_the_miss_limit_across_restarts(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    """닿지 못함은 멈추지 않지만(D6) 객체의 `misses` 가 재시작을 건너 센다 — 성공 없이 `MISS_LIMIT`
    번이면 멈추고, 그 뒤 재시작은 로그인하지 않는다."""
    with running_mock() as (mock, endpoint):
        key = switch_on(monkeypatch)
        scene(monkeypatch, "connection")
        environ = start_environment(mock, endpoint, key)
        stored_login(target_of(mock, endpoint), key)
        statuses: list[str] = []
        for _ in range(bdq_login.MISS_LIMIT + 2):
            bdq_login.forget_state()
            statuses.append(bdq_login.start_login(environ).status)
        assert statuses == [
            *(["unreached"] * (bdq_login.MISS_LIMIT - 1)),
            "stopped",
            "stopped",
            "stopped",
        ]
        assert fake.logins() == bdq_login.MISS_LIMIT
        meta = stored_meta(mock)
        assert meta["state"] == "stopped" and meta["stop_reason"] == bdq_login.REASON_MISS_LIMIT
        assert meta["misses"] == bdq_login.MISS_LIMIT


def test_a_success_clears_the_misses(monkeypatch: pytest.MonkeyPatch, fake: FakeBdq) -> None:
    with running_mock() as (mock, endpoint):
        key = switch_on(monkeypatch)
        scene(monkeypatch, "connection")
        stored_login(target_of(mock, endpoint), key)
        unreached = bdq_login.start_login(start_environment(mock, endpoint, key))
        assert unreached.status == "unreached"
        assert stored_meta(mock)["misses"] == 1
        scene(monkeypatch)
        bdq_login.forget_state()
        assert bdq_login.start_login(start_environment(mock, endpoint, key)).status == "ok"
        meta = stored_meta(mock)
        assert meta["misses"] == 0 and meta["state"] == "ok" and meta["stop_reason"] is None


def test_a_stop_that_cannot_be_written_at_start_is_still_stopped_at_every_restart(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    """시작이 거절을 보고 멈춤을 쓰지 못함(시도 표시 뒤의 PUT 500) — 객체는 앞서 써 둔 시도
    표시(멈춤)로 남아 다시 띄워도 로그인하지 않는다."""
    with running_mock() as (mock, endpoint):
        key = switch_on(monkeypatch)
        environ = start_environment(mock, endpoint, key)
        fake.write_live_token()
        stored_login(target_of(mock, endpoint), key, password=WRONG_PASSWORD)
        mock.force_on("PUT", store.SECRETS_PREFIX, after=1, times=100, status=500)
        first = bdq_login.start_login(environ)
        assert first.status == "rejected" and first.stop_write.startswith(store.WRITE_FAILED)
        for _ in range(3):
            bdq_login.forget_state()
            again = bdq_login.start_login(environ)
            assert again.status == "stopped"
            assert again.reason == bdq_login.REASON_ATTEMPTING
        assert fake.logins() == 1


def test_an_attempt_cut_short_leaves_a_stop_for_the_next_start(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    """시도 표시를 써 둔 채 프로세스가 끊김(결과를 적기 전) — 다음 시작은 멈춤으로 읽고 로그인하지
    않는다."""
    with running_mock() as (mock, endpoint):
        key = switch_on(monkeypatch)
        stored = stored_login(target_of(mock, endpoint), key)
        assert store.mark_attempting(target_of(mock, endpoint), cipher=stored.cipher).ok
        bdq_login.forget_state()
        started = bdq_login.start_login(start_environment(mock, endpoint, key))
        assert started.status == "stopped" and started.reason == bdq_login.REASON_ATTEMPTING
        assert fake.logins() == 0


def test_an_unwritable_attempt_mark_at_start_logs_in_nowhere(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    with running_mock() as (mock, endpoint):
        key = switch_on(monkeypatch)
        stored_login(target_of(mock, endpoint), key)
        mock.force["PUT"] = (500, "InternalError")
        started = bdq_login.start_login(start_environment(mock, endpoint, key))
        assert started.status == "unavailable" and started.reason == bdq_login.SKIP_UNGUARDED
        assert object_state(mock) == "ok"
        assert fake.logins() == 0


def test_refusals_before_spawning_do_not_count_as_attempts(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBdq,
    spawned: Spawned,
    mock_s3: tuple[MockStore, S3Target],
) -> None:
    """하위 프로세스를 띄우기 전 거절(패키지가 먼저 읽는 토큰 환경변수)은 연속 시도 수에 들지 않고
    시도 표시도 쓰지 않는다."""
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    stored_login(target, key)
    monkeypatch.setenv(bdq_token.LOGIN_TOKEN_ENV, "demo-token-value-0123456789")
    recovery = bdq_login.recover_after_token_failure(bdq_login.token_digest(ACCOUNT))
    assert recovery.attempt is not None and recovery.attempt.result is not None
    assert recovery.attempt.result.reason == bdq_login.REASON_ENV_TOKEN
    assert bdq_login.status().streak == 0
    assert requests_on(mock, store.OBJECT_KEY).count("PUT") == 1
    assert spawned.calls == []


def test_a_retry_stop_does_not_hit_a_login_the_form_put_in_meanwhile(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, mock_s3: tuple[MockStore, S3Target]
) -> None:
    """스스로 다시 로그인한 뒤 다시 한 조회가 또 토큰 오류인데, 그 사이 관리자가 폼으로 다른 계정을
    넣었다 — 멈춤은 옛 계정의 것이라 새 계정을 덮지 않는다(로그인 잠금 아래 `cipher` 대조)."""
    mock, target = mock_s3
    key = switch_on(monkeypatch)
    monkeypatch.setattr(store, "app_target", lambda: target)
    fake.write_live_token()
    stored_login(target, key)
    error = token_error()
    calls: list[int] = []

    def query() -> str:
        calls.append(1)
        if len(calls) == 2:
            assert bdq_login.login_from_form(OTHER_ACCOUNT, PASSWORD, ADMIN_ID).saved
        raise error("still no token")

    with pytest.raises(error):
        bdq_login.run_with_relogin(query)
    assert len(calls) == 2
    assert object_state(mock) == "ok"
    assert store.effective_account() == OTHER_ACCOUNT
    assert bdq_login.status().state == "ok"


def test_a_wrong_password_answered_in_a_connection_shape_stops_at_the_first_start(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    """저장된 비밀번호가 틀렸고 패키지가 서버의 401 을 errno 없는 `ConnectionError` 로 낸다 — 첫
    시작에서 거절로 멈추고, 다시 띄워도 로그인하지 않는다(검토 high 의 장면)."""
    with running_mock() as (mock, endpoint):
        key = switch_on(monkeypatch)
        scene(monkeypatch, "wrong_conn_builtin")
        environ = start_environment(mock, endpoint, key)
        fake.write_live_token()
        stored_login(target_of(mock, endpoint), key, password=WRONG_PASSWORD)
        assert bdq_login.start_login(environ).status == "rejected"
        for _ in range(2):
            bdq_login.forget_state()
            assert bdq_login.start_login(environ).status == "stopped"
        assert fake.logins() == 1
        assert object_state(mock) == "stopped"


def test_a_wrong_password_that_overwrites_the_token_stops_at_the_miss_limit(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq
) -> None:
    """저장된 비밀번호가 틀렸고 패키지가 실패 때 토큰 파일을 다른 글로 덮는다 — 성공이 아니고
    (`unconfirmed`), 재시작을 건너 세어 성공 없이 `MISS_LIMIT` 번이면 멈춘다(검토 medium 장면)."""
    with running_mock() as (mock, endpoint):
        key = switch_on(monkeypatch)
        scene(monkeypatch, "wrong_writes_garbage")
        environ = start_environment(mock, endpoint, key)
        stored_login(target_of(mock, endpoint), key, password=WRONG_PASSWORD)
        statuses: list[str] = []
        for _ in range(bdq_login.MISS_LIMIT + 2):
            bdq_login.forget_state()
            statuses.append(bdq_login.start_login(environ).status)
        assert statuses == [
            *(["unconfirmed"] * (bdq_login.MISS_LIMIT - 1)),
            "stopped",
            "stopped",
            "stopped",
        ]
        assert fake.logins() == bdq_login.MISS_LIMIT
        assert stored_meta(mock)["stop_reason"] == bdq_login.REASON_MISS_LIMIT
