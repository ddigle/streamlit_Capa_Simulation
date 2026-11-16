# Purpose: BigDataQuery 로그인 하위 프로세스 본문 — 표준 입력으로 로그인하고 표지 한 줄만 남긴다.

"""BigDataQuery 로그인 하위 프로세스.

`io/bdq_login.py` 가 `sys.executable` 하위 프로세스로 이 파일을 돌린다(`runpy.run_path` — 이 폴더를
`sys.path` 에 넣지 않는다). 표준 라이브러리만 쓰고 `capa_simulation` 을 import 하지 않는다 — 앱
패키지 경로가 없는 자리에서도 돈다.

**표준 입력 세 줄.** 첫 줄은 이 본문이 읽는 계정(로그인 뒤 `getTokenTime` 에 넘긴다)이고, 남은 두
줄(계정 · 비밀번호)은 패키지 `login()` 이 읽는다 — 계정은 `input()`, 비밀번호는 `getpass` 계열이 tty
가 없으면 표준 입력으로 읽는다(2026-11-16 사내 확인). 계정 · 비밀번호는 명령줄 · 환경변수에 없다.

**표지 한 줄.** 패키지는 import 마다 안내 배너를 찍고 로그인 중에도 글을 낼 수 있다 — 부르는 쪽은
표준 출력을 버리고 마지막 표지 줄(`MARKER`)만 읽는다. 표지에는 어디서 멈췄나(`stage`) · 예외 종류의
`모듈.이름`(`error` · `time_error`) · 서버에 닿지 못한 양의 증거(`net`) · 남은 분(`minutes`)만 있고
예외 문구 · 계정 · 비밀번호는 없다.

**「닿지 못함」 의 증거**(`is_unreached`)는 요청을 서버에 보내기 **전** 단계(연결)의 실패뿐이다 —
연결 거절 · 길 없음 · 이름 풀기 · 연결 시간 초과. 종류 이름만으로 가르지 않는다: 패키지가 서버가
답한 HTTP 오류(틀린 비밀번호의 401)를 `ConnectionError` 꼴로 낼 수 있어서다(사내 문구 「Auth
Connection failed: HTTP Response Code :」). 그래서 OS 가 낸 연결 단계 errno 가 붙은 것, `urllib3` 의
연결 단계 종류, 그리고 그것을 감싼 `requests` 의 연결 실패(응답이 없고 첫 인자가 그 원인 예외 —
라이브러리가 만든 꼴)만 받는다. 읽기 시간 초과(`ReadTimeout`) · 연결이 끊김(`ECONNRESET` ·
`Connection aborted`)은 비밀번호가 서버에 이미 간 뒤일 수 있어 증거가 아니다 — 거절(멈춤)로 간다.

`stage` — `input`(계정 줄 없음) · `import`(패키지를 불러오지 못함 — 로그인 시도 없음) · `login`
(`login()` 이 예외) · `done`(`login()` 이 돌아옴). 로그인이 받아들여졌는지는 부르는 쪽이 토큰 파일
다이제스트로 가른다 — 이 본문은 판정하지 않는다.
"""

from __future__ import annotations

import errno
import importlib
import re
import socket
import sys
from collections.abc import Mapping

MARKER = "capa-bdq-login"
STAGES = ("input", "import", "login", "done")
# `getTokenTime` 의 남은 날 칸 — 옮겨 적힌 철자(`remining_days`)도 받는다. 둘 다 없으면 0 날이다.
DAYS_KEYS = ("remaining_days", "remining_days")
HOURS_KEY = "remaining_hours"
MINUTES_KEY = "remaining_minutes"
_NAME_PART = re.compile(r"[^A-Za-z0-9_.]")
_NAME_LIMIT = 200
# 원인을 따라가는 깊이(`__cause__` 만 — 아래 `is_unreached`).
_CHAIN_LIMIT = 5
# 연결 단계에서 OS 가 내는 errno — 요청을 보내기 전(거절 · 길 없음 · 연결 시간 초과 · 주소 없음).
# 끊김(`ECONNRESET` · `EPIPE` · `ECONNABORTED`)은 서버가 요청을 읽은 뒤일 수 있어 넣지 않는다.
CONNECT_ERRNOS = frozenset(
    code
    for code in (
        getattr(errno, name, None)
        for name in (
            "ECONNREFUSED",
            "ENETUNREACH",
            "EHOSTUNREACH",
            "ENETDOWN",
            "EHOSTDOWN",
            "ETIMEDOUT",
            "EADDRNOTAVAIL",
        )
    )
    if code is not None
)
# `urllib3` 의 연결 단계 종류 — 요청을 보내기 전(`urllib3.exceptions`).
_URLLIB3_CONNECT = frozenset({"NewConnectionError", "ConnectTimeoutError", "NameResolutionError"})
# 그 밖에서 정의된 `OSError` 하위 종류만 errno 로 가른다 — 라이브러리 종류는 아래 꼴로 따로 본다.
_LIBRARY_ROOTS = frozenset({"requests", "urllib3"})


def qualified_name(error: BaseException) -> str:
    """예외 종류의 `모듈.이름` — 표지에 실을 수 있는 글자만 남긴다(`<locals>` 따위는 `_`)."""
    kind = type(error)
    text = _NAME_PART.sub("_", f"{kind.__module__}.{kind.__qualname__}")[:_NAME_LIMIT]
    return text if text[:1].isalpha() or text[:1] == "_" else f"_{text}"[:_NAME_LIMIT]


def _has_kind(error: BaseException, module: str, names: frozenset[str]) -> bool:
    """종류 사슬(`__mro__`)에 그 모듈의 그 이름이 있나 — 패키지를 import 하지 않는다."""
    return any(
        kind.__module__ == module and kind.__qualname__ in names for kind in type(error).__mro__
    )


def _connect_stage(error: BaseException, depth: int = 0) -> bool:
    """요청을 서버에 보내기 전(연결 단계)의 실패라는 양의 증거인가.

    - OS 연결 오류: errno 가 `CONNECT_ERRNOS` 인 `OSError`(이름 풀기 `socket.gaierror` 와 errno 가
      붙은 연결 거절은 errno 값과 상관없이) — 라이브러리(`requests` · `urllib3`)가 정의한 종류는
      뺀다. errno 가 없는 `ConnectionError("…HTTP Response Code…")` 는 패키지가 글로 만든 것이라
      아니다.
    - `urllib3` 의 연결 단계 종류(`_URLLIB3_CONNECT`), 그리고 그 까닭(`reason`)을 단
    `MaxRetryError`.
    - `requests` 의 연결 실패(`ConnectionError` · `ConnectTimeout`): 응답이 없고 첫 인자가 원인
      예외일 때 그 원인으로 — 라이브러리가 만든 꼴이다. 글만 든 것 · 읽기 단계 원인
      (`ProtocolError`)은 아니다.
    """
    if depth >= _CHAIN_LIMIT:
        return False
    root = type(error).__module__.split(".", 1)[0]
    if isinstance(error, OSError) and root not in _LIBRARY_ROOTS:
        if error.errno is None:
            return False
        if isinstance(error, (socket.gaierror, ConnectionRefusedError)):
            return True
        return error.errno in CONNECT_ERRNOS
    if _has_kind(error, "urllib3.exceptions", _URLLIB3_CONNECT):
        return True
    if _has_kind(error, "urllib3.exceptions", frozenset({"MaxRetryError"})):
        reason = getattr(error, "reason", None)
        return isinstance(reason, BaseException) and _connect_stage(reason, depth + 1)
    if _has_kind(error, "requests.exceptions", frozenset({"ConnectionError"})):
        if getattr(error, "response", None) is not None or not error.args:
            return False
        first = error.args[0]
        return isinstance(first, BaseException) and _connect_stage(first, depth + 1)
    return False


def is_unreached(error: BaseException) -> bool:
    """로그인 예외가 서버에 닿지 못한 양의 증거인가 — 그 예외나 명시적 원인(`raise … from`) 사슬의
    고리 가운데 연결 단계 실패(`_connect_stage`)가 있으면. 다른 예외를 처리하다 난 것(`__context__`
    만)은 증거로 보지 않는다 — 앞 시도가 끊기고 다음 시도가 닿아 거절된 꼴일 수 있다. 문구는 보지
    않는다."""
    current: BaseException | None = error
    for _ in range(_CHAIN_LIMIT):
        if current is None:
            break
        if _connect_stage(current):
            return True
        current = current.__cause__
    return False


def _whole_number(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def remaining_minutes(answer: object) -> int | None:
    """`getTokenTime` 의 답 → 남은 분(`days*1440 + hours*60 + minutes`). 날 칸은 두 철자를 받고
    없으면 0 이다. 시 · 분 칸이 없거나 수가 아니면 모름(`None`) — 꼴이 다른 답은 실패가 아니라
    모름이다."""
    if not isinstance(answer, Mapping):
        return None
    days: int | None = 0
    for key in DAYS_KEYS:
        if key in answer:
            days = _whole_number(answer[key])
            break
    hours = _whole_number(answer.get(HOURS_KEY))
    minutes = _whole_number(answer.get(MINUTES_KEY))
    if days is None or hours is None or minutes is None:
        return None
    return days * 1440 + hours * 60 + minutes


def marker_line(
    stage: str,
    *,
    error: str = "-",
    net: bool = False,
    minutes: int | None = None,
    time_error: str = "-",
) -> str:
    """표지 한 줄."""
    shown = "-" if minutes is None else str(minutes)
    return (
        f"{MARKER} stage={stage} error={error} net={int(net)} minutes={shown} "
        f"time_error={time_error}"
    )


def _emit(line: str) -> None:
    stream = sys.__stdout__
    if stream is None:
        return
    try:
        stream.write(f"\n{line}\n")
        stream.flush()
    except (OSError, ValueError):
        pass


def run() -> str:
    """로그인 한 번 → 표지 한 줄(찍지 않고 돌려준다)."""
    account = sys.stdin.readline().rstrip("\r\n")
    if not account:
        return marker_line("input")
    try:
        module = importlib.import_module("bigdataquery")
    except BaseException as error:  # 패키지 초기화가 낼 종류를 모른다 — 무엇이든 로그인 시도 없음
        return marker_line("import", error=qualified_name(error))
    try:
        module.login()
    except BaseException as error:  # 틀린 비밀번호 · 연결 · 종료 요청까지 모두 종류 이름만 남긴다
        return marker_line("login", error=qualified_name(error), net=is_unreached(error))
    try:
        answer = module.getTokenTime(account)
    except BaseException as error:  # 남은 시간을 못 재도 로그인 판정은 부르는 쪽 몫이다
        return marker_line("done", time_error=qualified_name(error))
    try:
        minutes = remaining_minutes(answer)
    except Exception:  # 답이 낯선 Mapping 이어도 모름일 뿐이다
        minutes = None
    return marker_line("done", minutes=minutes)


def main() -> int:
    line = marker_line("input")
    try:
        line = run()
    finally:
        _emit(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
