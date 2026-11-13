# Purpose: BigDataQuery 토큰 파일 넣기 · 거절 · 비밀 숨김 · 만료 읽기(가짜 토큰)를 검증한다.

from __future__ import annotations

import base64
import json
import os
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
# 「만료 없음」 자리표시로 흔한 9999-12-31T23:59:59Z — UTC 로는 읽히지만 UTC 보다 앞선 시각대로
# 옮기면 10000년이 된다.
FAR_EXPIRY = datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


def jwt_with_body(body: bytes) -> str:
    """몸을 그대로 담은 가짜 JWT."""
    middle = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    return f"{fake_jwt(FAR_EXPIRY).split('.')[0]}.{middle}.FAKE-signature"


def deeply_nested_jwt() -> str:
    """몸이 깊은 중첩 JSON(`[` 를 길게 이은 것)인 가짜 JWT — 풀면 `RecursionError` 가 난다."""
    return jwt_with_body(b"[" * 100_000)


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


def test_a_deeply_nested_body_is_an_unknown_expiry(folder: Path) -> None:
    """만료 읽기는 덧붙은 보기다 — 풀다 재귀 한도를 넘어도 예외 없이 모름이다(파일 · 환경변수)."""
    token = deeply_nested_jwt()

    assert bdq_token.token_expiry(token.encode()) is None
    assert bdq_token.install_token(token, env()).status == "written"
    state = bdq_token.current_token(env())
    assert state.source == "file" and state.expires_at is None
    environ = env(**{bdq_token.LOGIN_TOKEN_ENV: token})
    assert bdq_token.current_token(environ) == bdq_token.TokenState("environment")


def test_an_expiry_no_time_zone_can_show_is_unknown() -> None:
    """어느 시각대로 옮겨도 넘치지 않는 안쪽만 만료로 받는다 — 시각대와 무관한 판정이다."""
    assert bdq_token.token_expiry(fake_jwt(FAR_EXPIRY).encode()) is None
    assert bdq_token.token_expiry(jwt_with_body(b'{"exp":-62135596800}').encode()) is None
    inside = datetime(9999, 12, 29, tzinfo=timezone.utc)
    assert bdq_token.token_expiry(fake_jwt(inside).encode()) == inside


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


def _same_size_tokens() -> tuple[datetime, str, datetime, str]:
    first = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)
    second = first + timedelta(days=1)
    tokens = (fake_jwt(first), fake_jwt(second))
    assert len(tokens[0]) == len(tokens[1])
    return first, tokens[0], second, tokens[1]


def test_a_file_replaced_from_outside_in_the_same_tick_is_read_again(folder: Path) -> None:
    """프로세스 밖(시작 스크립트 · 다른 앱)이 같은 크기 토큰을 같은 시각 눈금 안에 바꿔 끼워도 새
    만료를 본다 — 바꿔 끼우는 쓰기는 inode 가 바뀐다(기억 열쇠)."""
    first, token, second, other = _same_size_tokens()
    bdq_token.install_token(token, env())
    target = folder / f"bigdataquery.token.{ACCOUNT}"
    assert bdq_token.current_token(env()).expires_at == first
    before = target.stat()

    bdq_token.write_private(target, other.encode())
    os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))

    after = target.stat()
    assert (after.st_mtime_ns, after.st_size) == (before.st_mtime_ns, before.st_size)
    assert bdq_token.current_token(env()).expires_at == second


def test_a_put_token_shows_its_expiry_even_where_inodes_stay(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """inode 를 믿을 수 없는 파일 체계(같은 자리에 덮어씀 · 같은 시각 눈금 · 같은 크기)에서도 넣은
    토큰의 만료를 바로 본다 — 넣기가 쓴 뒤 기억을 비운다."""
    first, token, second, other = _same_size_tokens()
    bdq_token.install_token(token, env())
    assert bdq_token.current_token(env()).expires_at == first

    def in_place(target: Path, content: bytes) -> None:
        before = target.stat()
        target.write_bytes(content)
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert target.stat().st_ino == before.st_ino

    monkeypatch.setattr(bdq_token, "write_private", in_place)
    assert bdq_token.install_token(other, env()).status == "written"

    assert bdq_token.current_token(env()).expires_at == second


def test_the_warning_starts_one_hour_before_and_stays_after() -> None:
    expires = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)
    state = bdq_token.TokenState("file", expires_at=expires)
    hour = timedelta(seconds=bdq_token.EXPIRY_WARNING_SECONDS)

    assert bdq_token.expiry_is_near(state, expires - hour - timedelta(seconds=1)) is False
    assert bdq_token.expiry_is_near(state, expires - hour) is True
    assert bdq_token.expiry_is_near(state, expires + timedelta(days=1)) is True
    assert bdq_token.expiry_is_near(bdq_token.TokenState("file"), expires) is False
