# Purpose: BigDataQuery 토큰 파일 넣기 · 거절 · 비밀 숨김 · 만료 읽기(가짜 토큰)를 검증한다.

from __future__ import annotations

import base64
import json
import stat
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from capa_simulation.io import bdq_token
from capa_simulation.io.container_start_report import BDQ_USER_NAME_ENV

ACCOUNT = "fakeaccount"
# 가짜 토큰만 쓴다 — 사내 토큰 꼴(35바이트 · 한 줄)을 흉내 낸 값과 가짜 JWT.
FAKE_TOKEN = "FAKE-bdq-login-token-0000-abcdefghi"


def fake_jwt(expires: datetime) -> str:
    """서명 없는 가짜 JWT — 몸의 `exp` 만 뜻이 있다."""

    def part(value: object) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{part({'alg': 'none'})}.{part({'exp': int(expires.timestamp())})}.FAKE-signature"


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "credential"
    monkeypatch.setattr(bdq_token, "CREDENTIAL_DIR", target)
    return target


def env(**extra: str) -> dict[str, str]:
    return {BDQ_USER_NAME_ENV: ACCOUNT, **extra}


def test_a_token_is_written_where_the_package_reads_it(
    folder: Path, keeps_permission_bits: bool
) -> None:
    """0600 · 폴더 0700 — 비트를 담지 못하는 파일 체계(Windows)에서는 자리 · 내용만 본다."""
    outcome = bdq_token.install_token(f"  {FAKE_TOKEN}\n", env())

    assert outcome == bdq_token.InstallOutcome("written")
    target = folder / f"bigdataquery.token.{ACCOUNT}"
    assert target.read_bytes() == FAKE_TOKEN.encode("utf-8")
    if keeps_permission_bits:
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert [path.name for path in folder.iterdir()] == [target.name]


def test_a_base64_value_is_written_decoded_like_the_cd_variable(folder: Path) -> None:
    encoded = base64.b64encode(f"{FAKE_TOKEN}\n".encode()).decode()

    assert bdq_token.install_token(f"base64:{encoded}", env()).status == "written"
    assert (folder / f"bigdataquery.token.{ACCOUNT}").read_bytes() == f"{FAKE_TOKEN}\n".encode()


def test_the_same_token_is_not_written_again(folder: Path) -> None:
    assert bdq_token.install_token(FAKE_TOKEN, env()).status == "written"
    target = folder / f"bigdataquery.token.{ACCOUNT}"
    before = target.stat().st_mtime_ns

    assert bdq_token.install_token(FAKE_TOKEN, env()) == bdq_token.InstallOutcome("same")
    assert target.stat().st_mtime_ns == before


@pytest.mark.parametrize(
    ("raw", "words"),
    [
        ("   ", "비었습니다"),
        ("base64:***not base64***", "풀지 못했습니다"),
        (f"base64:{base64.b64encode(b'   ').decode()}", "푼 내용이 비었습니다"),
        ("FAKE-short", "16바이트보다 짧아"),
    ],
    ids=["빈 값", "base64 아님", "푼 내용 빔", "짧음"],
)
def test_a_value_that_is_not_a_token_is_refused_without_echoing_it(
    folder: Path, raw: str, words: str
) -> None:
    outcome = bdq_token.install_token(raw, env())

    assert outcome.status == "refused" and words in outcome.reason
    assert raw.strip() not in outcome.reason or not raw.strip()
    # 길이는 비밀에서 나온 수다 — 문턱 말고 다른 수를 싣지 않는다.
    assert str(len(raw.strip())) not in outcome.reason.replace("16", "")
    assert not folder.exists()


def test_without_the_account_the_file_name_is_unknown(folder: Path) -> None:
    reason = bdq_token.blocked_reason({})

    assert reason is not None and BDQ_USER_NAME_ENV in reason
    assert bdq_token.install_token(FAKE_TOKEN, {}) == bdq_token.InstallOutcome("refused", reason)
    assert bdq_token.blocked_reason(env(**{BDQ_USER_NAME_ENV: "../x"})) is not None
    assert not folder.exists()


def test_the_package_environment_variable_wins_over_the_file(folder: Path) -> None:
    """패키지가 `BIGDATAQUERY_LOGIN_TOKEN` 을 파일보다 먼저 읽으니 파일에 넣어도 쓰이지 않는다."""
    environ = env(**{bdq_token.LOGIN_TOKEN_ENV: "FAKE-env-token-0000000000"})
    reason = bdq_token.blocked_reason(environ)

    assert reason is not None and bdq_token.LOGIN_TOKEN_ENV in reason
    assert "FAKE-env-token" not in reason
    assert bdq_token.install_token(FAKE_TOKEN, environ).status == "refused"
    assert not folder.exists()


def test_a_write_failure_names_only_the_error_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(bdq_token, "CREDENTIAL_DIR", blocker / "credential")

    outcome = bdq_token.install_token(FAKE_TOKEN, env())

    assert outcome.status == "refused"
    assert (
        outcome.reason.startswith("토큰 파일을 쓰지 못했습니다(")
        and str(tmp_path) not in outcome.reason
    )
    assert FAKE_TOKEN not in outcome.reason and ACCOUNT not in outcome.reason


def test_two_sessions_writing_at_once_leave_one_whole_token(folder: Path) -> None:
    tokens = [f"FAKE-bdq-login-token-{n:04d}-abcdefghi" for n in range(8)]
    threads = [
        threading.Thread(target=bdq_token.install_token, args=(token, env())) for token in tokens
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    target = folder / f"bigdataquery.token.{ACCOUNT}"
    assert target.read_text(encoding="utf-8") in tokens
    assert [path.name for path in folder.iterdir()] == [target.name]


def test_the_expiry_is_read_from_a_jwt_exp_only() -> None:
    expires = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)

    assert bdq_token.token_expiry(fake_jwt(expires).encode()) == expires
    # 지금 아는 꼴은 JWT 하나다 — 한 줄 글(사내 실측 35바이트 꼴) · JSON 의 exp 는 모름이다.
    assert bdq_token.token_expiry(FAKE_TOKEN.encode()) is None
    assert bdq_token.token_expiry(json.dumps({"exp": 1763000000}).encode()) is None
    assert bdq_token.token_expiry(b"a.b.c") is None
    assert bdq_token.token_expiry(b"\xff\xfe") is None
    no_exp = fake_jwt(expires).split(".")
    no_exp[1] = base64.urlsafe_b64encode(b'{"exp":"soon"}').decode().rstrip("=")
    assert bdq_token.token_expiry(".".join(no_exp).encode()) is None


def test_the_current_token_follows_the_package_order(folder: Path) -> None:
    assert bdq_token.current_token({}) == bdq_token.TokenState("unknown")
    assert bdq_token.current_token(env()) == bdq_token.TokenState("missing")

    expires = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)
    bdq_token.install_token(fake_jwt(expires), env())
    state = bdq_token.current_token(env())
    assert state.source == "file" and state.expires_at == expires
    assert state.modified_at is not None

    bdq_token.install_token(FAKE_TOKEN, env())
    state = bdq_token.current_token(env())
    assert state.source == "file" and state.expires_at is None

    later = expires + timedelta(hours=3)
    environ = env(**{bdq_token.LOGIN_TOKEN_ENV: fake_jwt(later)})
    assert bdq_token.current_token(environ) == bdq_token.TokenState("environment", expires_at=later)


def test_the_file_is_read_again_only_when_it_changes(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expires = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)
    bdq_token.install_token(fake_jwt(expires), env())
    reads: list[bytes] = []
    real = bdq_token.token_expiry

    def counted(content: bytes) -> datetime | None:
        reads.append(content)
        return real(content)

    monkeypatch.setattr(bdq_token, "token_expiry", counted)
    for _ in range(3):
        assert bdq_token.current_token(env()).expires_at == expires
    assert len(reads) == 1

    bdq_token.install_token(fake_jwt(expires + timedelta(days=1)), env())
    assert bdq_token.current_token(env()).expires_at == expires + timedelta(days=1)
    assert len(reads) == 2


def test_the_warning_starts_one_hour_before_and_stays_after() -> None:
    expires = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)
    state = bdq_token.TokenState("file", expires_at=expires)
    hour = timedelta(seconds=bdq_token.EXPIRY_WARNING_SECONDS)

    assert bdq_token.expiry_is_near(state, expires - hour - timedelta(seconds=1)) is False
    assert bdq_token.expiry_is_near(state, expires - hour) is True
    assert bdq_token.expiry_is_near(state, expires + timedelta(days=1)) is True
    assert bdq_token.expiry_is_near(bdq_token.TokenState("file"), expires) is False
