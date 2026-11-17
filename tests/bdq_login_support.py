# Purpose: BDQ 자동 로그인 시험 공용 — 가짜 패키지 자리 · 합성 값 · 실측 꼴 실패 · 가짜 S3.

"""BDQ 자동 로그인 시험의 공용 부품.

가짜 `bigdataquery`(`tests/fixtures/bdq_fake/`)는 시험 프로세스의 `sys.path` 에 두지 않는다 — 진짜
패키지가 없다는 판정을 쓰는 시험이 있다. 로그인 하위 프로세스만 `PYTHONPATH` 로 찾는다
(`use_fake_bdq`). 가짜 패키지를 제 프로세스 안에서 불러오는 시험 스크립트는 `run_with_fake_package`
로 띄운다. 값은 모두 합성이다 — 비밀번호는 어디에 새는지 찾기 쉬운 카나리아 글이다.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from capa_simulation.auth import names as sso_names
from capa_simulation.io import bdq_token
from capa_simulation.io.bdq_login_store import SECRET_KEY_ENV
from capa_simulation.io.object_storage import MODE_ENV
from capa_simulation.io.s3_small import S3Target

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FAKE_PACKAGE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "bdq_fake"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from s3_mock_store import MockStore, start_mock  # noqa: E402

ACCOUNT = "demo_user"
OTHER_ACCOUNT = "demo_other"
PASSWORD = "CANARY-pw-7Q2"
WRONG_PASSWORD = "CANARY-wrong-3Z8"
ADMIN_ID = "demo.admin"
# 만료 · 무효 토큰의 `getData` 가 내는 두 줄(2026-11-16 사내 실측 — 둘이 같다). 안쪽이 다시 로그인
# 문구를 든다. 가짜 패키지도 같은 글을 낸다.
MEASURED_INNER = (
    "You have invalid token. Please login again using the login() function: "
    "HTTP Response Code : 400"
)
MEASURED_OUTER = (
    "There is a problem with authentication. Please contact the person in charge of bigdataquery"
)
# 다시 로그인 문구가 결과 · 로그 · 저장 객체에 새지 않았는지 볼 조각.
MEASURED_FRAGMENTS = ("invalid token", "login() function", "problem with authentication")


def measured_token_failure(link: str = "context") -> ConnectionError:
    """실측 꼴 사슬 하나(부를 때마다 새로) — 바깥 `ConnectionError` · 안쪽 `Exception`. `link` 는
    안쪽을 다는 길이다 — `context`(안쪽을 잡은 `except` 안에서 바깥을 냄 — 가짜 패키지 꼴) ·
    `cause`(`raise … from`)."""
    inner = Exception(MEASURED_INNER)
    try:
        if link == "cause":
            raise ConnectionError(MEASURED_OUTER) from inner
        try:
            raise inner
        except Exception:
            raise ConnectionError(MEASURED_OUTER)  # noqa: B904 — 실측 꼴(문맥만)
    except ConnectionError as outer:
        return outer


def new_key() -> str:
    """합성 Fernet 키(시험마다 새로)."""
    return Fernet.generate_key().decode("ascii")


@contextmanager
def running_mock() -> Iterator[tuple[MockStore, str]]:
    """서명을 검증하는 가짜 S3 한 벌."""
    store = MockStore()
    server, endpoint = start_mock(store)
    try:
        yield store, endpoint
    finally:
        server.shutdown()
        server.server_close()


def target_of(store: MockStore, endpoint: str) -> S3Target:
    return S3Target(
        endpoint_url=endpoint,
        bucket=store.bucket,
        region=store.region,
        access_key=store.access_key,
        secret_key=store.secret_key,
    )


def s3_environment(store: MockStore, endpoint: str) -> dict[str, str]:
    """시작 스크립트 꼴 환경의 S3 칸(주소 · 버킷 · 영역 · 키 둘)."""
    return {
        sso_names.ENV_S3_ACCESS_KEY: store.access_key,
        sso_names.ENV_S3_SECRET_KEY: store.secret_key,
        sso_names.ENV_S3_ENDPOINT: endpoint,
        sso_names.ENV_S3_BUCKET: store.bucket,
        sso_names.ENV_S3_REGION: store.region,
    }


def requests_on(store: MockStore, key: str) -> list[str]:
    """그 키에 온 요청 메서드들."""
    with store.lock:
        return [method for method, path in store.requests if path.endswith(key)]


@dataclass(frozen=True)
class FakeBdq:
    """가짜 패키지가 쓰는 자리 — 토큰 폴더와 부른 기록 파일."""

    credential_dir: Path
    log: Path

    def logins(self) -> int:
        """하위 프로세스에서 `login()` 이 불린 수."""
        if not self.log.is_file():
            return 0
        return self.log.read_text(encoding="utf-8").splitlines().count("login")

    def imports(self) -> int:
        if not self.log.is_file():
            return 0
        return self.log.read_text(encoding="utf-8").splitlines().count("import")

    def token_path(self, account: str = ACCOUNT) -> Path:
        return self.credential_dir / f"bigdataquery.token.{account}"

    def write_live_token(self, account: str = ACCOUNT) -> bytes:
        """지금 발급된 꼴의 살아 있는 토큰(옛 토큰 장면 — 가짜 패키지의 `getTokenTime` 이 받는
        꼴)."""
        return self._write_issued(account, time.time())

    def write_expired_token(self, account: str = ACCOUNT) -> bytes:
        """9시간 전에 발급된 꼴의 만료 토큰(수명 8시간)."""
        return self._write_issued(account, time.time() - 9 * 3600)

    def _write_issued(self, account: str, issued: float) -> bytes:
        content = f"{secrets.token_hex(12)}_{int(issued * 1000)}".encode("ascii")
        self.credential_dir.mkdir(parents=True, exist_ok=True)
        self.token_path(account).write_bytes(content)
        return content


def use_fake_bdq(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeBdq:
    """하위 프로세스가 가짜 패키지를 찾게 하고 토큰 폴더를 앱과 같은 tmp 자리로 맞춘다."""
    credential_dir = tmp_path / "credential"
    credential_dir.mkdir()
    log = tmp_path / "fake-bdq.log"
    monkeypatch.setenv("PYTHONPATH", str(FAKE_PACKAGE_ROOT))
    monkeypatch.setenv("FAKE_BDQ_CREDENTIAL_DIR", str(credential_dir))
    monkeypatch.setenv("FAKE_BDQ_PASSWORD_SHA256", hashlib.sha256(PASSWORD.encode()).hexdigest())
    monkeypatch.setenv("FAKE_BDQ_LOG", str(log))
    monkeypatch.delenv("FAKE_BDQ_SCENE", raising=False)
    monkeypatch.delenv("FAKE_BDQ_SLOW_SECONDS", raising=False)
    monkeypatch.delenv("FAKE_BDQ_REVOKED", raising=False)
    monkeypatch.setattr(bdq_token, "CREDENTIAL_DIR", credential_dir)
    return FakeBdq(credential_dir, log)


def switch_on(monkeypatch: pytest.MonkeyPatch, key: str | None = None) -> str:
    """앱 프로세스 꼴로 켠다 — 동기화 모드 `managed` 와 키. 넣은 키를 돌려준다."""
    value = new_key() if key is None else key
    monkeypatch.setenv(MODE_ENV, "managed")
    monkeypatch.setenv(SECRET_KEY_ENV, value)
    return value


def run_with_fake_package(
    code: str,
    *args: str,
    input_text: str | None = None,
    extra_env: Mapping[str, str] | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    """가짜 패키지를 제 프로세스 안에서 불러오는 시험 스크립트 한 번(앱 `src` 와 가짜 패키지 자리가
    `PYTHONPATH` 에 있다). 하위 표준 입출력을 UTF-8 로 정하고 부모도 UTF-8 로 읽는다 — 부모 환경에서
    물려받은 `PYTHONIOENCODING` 보다 앞선다.

    가짜 배너의 em dash(U+2014)는 cp949 에 없어 Windows 파이프(로캘 cp949)로는 import 가 깨진다.
    하위만 UTF-8 이면 부모의 `text=True` 읽기(Windows 는 읽기 스레드가 로캘로 푼다)가
    `UnicodeDecodeError` 로 스레드째 끝나 `stdout` 이 `None` 이 된다."""
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(PROJECT_ROOT / "src"), os.environ["PYTHONPATH"])),
        **(extra_env or {}),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        input=input_text,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
        check=False,
    )
