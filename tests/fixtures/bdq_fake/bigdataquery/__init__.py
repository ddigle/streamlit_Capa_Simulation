# Purpose: 시험용 가짜 bigdataquery — 배너 · 표준 입력 로그인 · 나뉜 남은 시간 · 장면 스위치.

"""가짜 `bigdataquery` — 로그인 하위 프로세스(`io/bdq_login.py`)를 끝까지 태우는 시험 전용 패키지.

시험 프로세스의 `sys.path` 에는 두지 않는다(진짜 패키지가 없다는 판정을 쓰는 시험이 있다). 하위
프로세스만 `PYTHONPATH` 로 이 폴더의 부모를 찾는다.

사내 2.5.0 확인(2026-11-16)을 따른다 — import 마다 안내 배너를 표준 출력에 찍고, `login()` 은 계정을
`input()` 으로 · 비밀번호를 `getpass` 로 읽는다(tty 가 없으면 표준 입력 폴백과
`GetPassWarning`). 맞으면 토큰 파일을 `<자리>/bigdataquery.token.<계정>` 에 `<난수>_<발급 ms>`
꼴로 쓴다. `getTokenTime` 은 파일에 든 토큰의 남은 시간을 나뉜 값(`remaining_days` ·
`remaining_hours` · `remaining_minutes`)으로 준다.

시험 전용 환경변수(`FAKE_BDQ_*`):

- `FAKE_BDQ_CREDENTIAL_DIR` — 토큰 폴더(앱의 `bdq_token.CREDENTIAL_DIR` 와 같은 곳으로).
- `FAKE_BDQ_PASSWORD_SHA256` — 맞는 비밀번호의 sha256(16진). 비밀번호 글 자체는 환경에 두지 않는다 —
  하위 환경에 비밀번호가 없다는 시험이 그대로 선다.
- `FAKE_BDQ_LOG` — 부른 기록(`import` · `login`)을 한 줄씩 덧붙이는 파일.
- `FAKE_BDQ_SLOW_SECONDS` — `slow` · `time_slow` 장면에서 잠드는 초(기본 30).
- `FAKE_BDQ_SCENE` — 쉼표로 이은 장면:
  `wrong_raises`(틀린 비밀번호에 예외 — 기본은 문구만 찍고 끝남) · `exit_on_wrong`(틀린 비밀번호에
  `sys.exit`) · `connection`(연결 예외 — `requests` 가 있으면 그 종류) · `connection_context`(연결
  예외를 처리하다 난 다른 예외 — 원인 사슬이 아니라 문맥만) · `slow`(로그인 중 잠듦) · `time_odd`
  (`getTokenTime` 꼴이 다름) · `time_typo`(날 칸이 `remining_days`, 하루 더) · `time_short`
  (25분 남음) ·
  `time_raises`(`getTokenTime` 예외) · `time_slow`(`getTokenTime` 중 잠듦 — 토큰은 이미 새로 씀) ·
  `import_fails`(import 때 예외).
"""

from __future__ import annotations

import getpass
import hashlib
import os
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bigdataquery.exceptions import TokenNotFoundException

__all__ = ["TokenNotFoundException", "getData", "getTokenTime", "login"]
__version__ = "0.0.0+fake"

TOKEN_LIFETIME = timedelta(hours=8)
_KST = timezone(timedelta(hours=9))


def _scenes() -> frozenset[str]:
    raw = os.environ.get("FAKE_BDQ_SCENE", "")
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _log(event: str) -> None:
    place = os.environ.get("FAKE_BDQ_LOG", "")
    if place:
        with open(place, "a", encoding="utf-8") as handle:
            handle.write(f"{event}\n")


def _token_path(account: str) -> Path:
    return Path(os.environ.get("FAKE_BDQ_CREDENTIAL_DIR", ".")) / f"bigdataquery.token.{account}"


def _connection_error() -> Exception:
    requests_errors = sys.modules.get("requests.exceptions")
    if requests_errors is None:
        try:
            import requests.exceptions as requests_errors
        except ImportError:
            requests_errors = None
    found = getattr(requests_errors, "ConnectionError", None)
    if isinstance(found, type) and issubclass(found, Exception):
        return found("HTTPSConnectionPool: Max retries exceeded (fake)")
    return ConnectionError("connection refused (fake)")


def _read_password(prompt: str) -> str:
    """POSIX 는 `getpass.getpass`(제어 터미널이 있으면 `/dev/tty`, 없으면 표준 입력 폴백) 그대로다.
    Windows 의 `getpass` 는 표준 입력이 아니라 콘솔 키보드(`msvcrt`)를 읽어 시험이 멈추므로 표준
    입력 폴백 길만 흉내 낸다 — 이 기능이 도는 자리(C-DEP)는 Linux 다."""
    if os.name == "nt":
        # 표준 라이브러리 타입 스텁에 없는 이름이라 이름으로 찾는다.
        fallback = vars(getpass)["fallback_getpass"]
        return str(fallback(prompt))
    return getpass.getpass(prompt)


print("========================================")
print(" bigdataquery (fake) — 안내 배너")
print("========================================")
_log("import")
if "import_fails" in _scenes():
    raise RuntimeError("fake package init failure")


def login() -> None:
    """표준 입력 두 줄(계정 · 비밀번호)로 로그인한다. 맞으면 토큰 파일을 새로 쓴다."""
    _log("login")
    account = input("AD Account : ")
    password = _read_password("Password : ")
    scenes = _scenes()
    if "slow" in scenes:
        time.sleep(float(os.environ.get("FAKE_BDQ_SLOW_SECONDS", "30")))
    if "connection" in scenes:
        raise _connection_error()
    if "connection_context" in scenes:
        try:
            raise _connection_error()
        except Exception:
            raise RuntimeError("Auth Connection failed: HTTP Response Code : 401") from None
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if digest != os.environ.get("FAKE_BDQ_PASSWORD_SHA256", ""):
        if "wrong_raises" in scenes:
            raise Exception(f"Auth Connection failed: HTTP Response Code : 401 ({account})")
        if "exit_on_wrong" in scenes:
            sys.exit(f"login failed for {account}")
        print(f"login failed for {account} — check the password")
        return
    target = _token_path(account)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{secrets.token_hex(12)}_{int(time.time() * 1000)}", encoding="utf-8")
    print(f"login success: {account}")


def getTokenTime(user_name: str) -> dict[str, object]:
    """파일에 든 토큰의 남은 시간 — 나뉜 값. 파일이 없으면 `TokenNotFoundException`."""
    scenes = _scenes()
    if "time_slow" in scenes:
        time.sleep(float(os.environ.get("FAKE_BDQ_SLOW_SECONDS", "30")))
    if "time_raises" in scenes:
        raise RuntimeError("Auth Connection failed: HTTP Response Code : 500")
    path = _token_path(user_name)
    if not path.is_file():
        raise TokenNotFoundException(
            f"There is no bigdataquery token issued for AD user {user_name}"
        )
    issued_ms = int(path.read_text(encoding="utf-8").strip().rsplit("_", 1)[1])
    issued = datetime.fromtimestamp(issued_ms / 1000, tz=_KST)
    now = datetime.now(_KST)
    left = max(issued + TOKEN_LIFETIME - now, timedelta(0))
    if "time_short" in scenes:
        left = timedelta(minutes=25)
    if "time_typo" in scenes:
        left += timedelta(days=1)
    total = int(left.total_seconds() // 60)
    days, rest = divmod(total, 1440)
    hours, minutes = divmod(rest, 60)
    expiration = (now + left).strftime("%Y-%m-%d %H:%M:%S")
    print(f"토큰 만료 시각: {expiration}+09:00")
    if "time_odd" in scenes:
        return {"expiration_date": expiration, "remaining": f"{hours}h {minutes}m"}
    days_key = "remining_days" if "time_typo" in scenes else "remaining_days"
    return {
        "expiration_date": expiration,
        days_key: days,
        "remaining_hours": hours,
        "remaining_minutes": minutes,
    }


def getData(
    *, param: str, convert_type: bool = True, verbose: bool = True, user_name: str = ""
) -> list[dict[str, str]]:
    """조회마다 토큰 파일을 다시 읽는다. 없으면 `TokenNotFoundException`."""
    del convert_type, verbose
    path = _token_path(user_name)
    if not path.is_file():
        raise TokenNotFoundException(
            f"There is no bigdataquery token issued for AD user {user_name}"
        )
    return [{"param": param}]
