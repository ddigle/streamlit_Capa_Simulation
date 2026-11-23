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

**단계 줄**(`STEP_MARKER`)은 표지와 따로 선다 — 패키지를 불러오기 · `login()` · `getTokenTime`
에 들어가기 바로 앞에 한 줄씩 찍고 곧바로 내보낸다. 하위 프로세스가 표지 없이 끝나도(죽음 ·
시그널) 부르는 쪽이 어디까지 갔는지와 판(`VERSION_PACKAGES` — 불러온 모듈의 `__version__`, 아니면
설치 정보)을 읽는다. 판은 짧은 판 글자 꼴만 싣고(`?` — 꼴이 낯섦, `-` — 없음) 표지의 꼴에는 들지
않는다 — 낯선 판 글자 하나가 표지를 깨 좋은 로그인을 「표지 없음」 으로 만들지 않게.

**「비밀번호를 보내기 전」 의 근거.** 단계 줄 `login` 을 내보내지(쓰고 비우지) 못하면 `login()` 에
들어가지 않는다 — 그래서 부르는 쪽이 받은 마지막 단계 줄이 `import` 면 패키지가 비밀번호를 서버에
보내는 `login()` 은 불리지 않았다(`bdq_login.PRE_SEND_STAGES` — 표준 입력의 비밀번호는 이 프로세스의
파이프에만 있었다).

**가벼운 불러오기 길**(2026-11-23 사용자 요청). 패키지를 통째로 불러오면 판 하위 꾸러미
(`bigdataquery/py<주판><부판>`)의 `__init__` 이 import 때 망 초기화를 하고, 앱이 이미 한 그 초기화를
하위가 한 번 더 해 메모리를 크게 쓴다. `login` · `getTokenTime` 은 그 판 하위 꾸러미의 `server_auth`
에 있어, 꾸러미 둘을 빈 꾸러미(`__path__` 만 — 판 하위 꾸러미는 맨 위 꾸러미의 속성으로 묶는다)로
심고 `server_auth` 만 불러온다(`load_light` — `nest_asyncio.apply()` 는 남기고 `pyarrow` 는
`server_auth` 를 불러오는 동안만 막는다). 설치 판이 `LIGHT_VERSION` 이고 판 폴더가 있고
끄개(`LIGHT_SWITCH_ENV=off`)가 없을 때만 가고(`light_folder`), `server_auth` 에 둘이 부를 수 있는
것으로 있어야 쓴다. 이 준비는 모두 단계 줄 `login` 앞이고, 무엇이 실패해도 심은 것을 걷고 같은
프로세스에서 전체 import 로 간다 — 준비에서 난 실패는 `login()` 안(부르는 쪽이 거절로 판정하는
자리)으로 넘어가지 않는다. 다만 `login()` · `getTokenTime` 이 돌면서 빈 꾸러미의 꼴(꾸러미 전역 ·
속성 · 꾸러미에서 이름을 찾는 늦은 import)에 기대 나는 실패는 그 선 뒤에서 나고, 지금 규칙대로
거절 · 확인 못 함이다. 단계 줄의 끝 칸 `load` 가 어느 길로 갔는지다(`light` · `full` — 전체로
돌아가면 `import` 단계 줄을 `full` 로 한 번 더 낸다).
"""

from __future__ import annotations

import errno
import importlib
import importlib.util
import os
import re
import socket
import sys
import types
from collections.abc import Callable, Mapping

MARKER = "capa-bdq-login"
STAGES = ("input", "import", "login", "done")
# 단계 줄 — 표지와 다른 머리(표지 줄 머리는 `MARKER` 뒤 공백이라 겹치지 않는다).
STEP_MARKER = "capa-bdq-login-step"
# 단계 줄의 단계 — 그 일에 들어가기 바로 앞에 찍는다.
STEP_STAGES = ("import", "login", "time")
# 단계 줄 `login` 을 내보내지 못해 `login()` 에 들어가지 않은 표지의 종류 칸.
STEP_UNWRITTEN = "capa_step_unwritten"
# 단계 줄에 판을 싣는 배포 — 패키지와 그 비밀번호 칸 패키지.
VERSION_PACKAGES = ("bigdataquery", "getpass_asterisk")
# 판 글자 꼴 — 그 밖은 `?`, 없으면 `-`.
VERSION_TEXT = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+!_-]{0,39}")
# 단계 줄 끝 칸 `load` — 패키지를 불러온 길(가벼운 길 · 전체).
LOAD_LIGHT = "light"
LOAD_FULL = "full"
STEP_LOADS = (LOAD_LIGHT, LOAD_FULL)
# 가벼운 길을 가는 설치 판 하나 — 판 하위 꾸러미 `__init__` 과 `server_auth` 의 짜임을 사내에서
# 본 판이다.
LIGHT_VERSION = "2.5.0"
LIGHT_PACKAGE = "bigdataquery"
LIGHT_MODULE = "server_auth"
# 가벼운 길에서 `server_auth` 를 불러오는 동안만 막는 모듈(값 `None` — 불러오면 `ImportError`).
LIGHT_BLOCKED = "pyarrow"
# 끄개 — 값이 `off`(앞뒤 공백 · 대소문자 무시)면 늘 전체 길. 하위는 앱 환경을 그대로 받는다.
LIGHT_SWITCH_ENV = "CAPA_BDQ_LOGIN_LIGHT"
LIGHT_SWITCH_OFF = "off"
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


def version_text(value: object) -> str:
    """판 글자 — 꼴(`VERSION_TEXT`)에 맞으면 그대로, 빈 값 · 글이 아니면 `-`, 꼴이 낯설면 `?`."""
    if not isinstance(value, str) or not value:
        return "-"
    return value if VERSION_TEXT.fullmatch(value) else "?"


def installed_version(name: str) -> str:
    """설치 정보(`importlib.metadata`)의 판 — 불러오지 않고 읽는다. 없거나 읽다 깨지면 `-`."""
    try:
        from importlib import metadata

        return version_text(metadata.version(name))
    except Exception:  # 설치 정보가 없거나 낯선 꼴이어도 진단 칸 하나가 빌 뿐이다
        return "-"


def loaded_version(name: str, fallback: str) -> str:
    """불러온 모듈의 `__version__` — 아직 불러오지 않았거나 없으면 `fallback`(설치 판). 읽다 무엇이
    나도 `fallback` 이다 — 판 읽기가 로그인 길을 끊지 않게."""
    try:
        module = sys.modules.get(name)
        value = getattr(module, "__version__", None) if module is not None else None
    except Exception:  # 낯선 모듈 속성이 깨져도 진단 칸 하나가 빌 뿐이다
        return fallback
    return version_text(value) if isinstance(value, str) and value else fallback


def step_line(stage: str, versions: Mapping[str, str], load: str = LOAD_FULL) -> str:
    """단계 줄 하나 — 단계와 판(`VERSION_PACKAGES` 차례), 끝에 불러온 길(`STEP_LOADS`)."""
    shown = " ".join(f"{name}={versions.get(name, '-')}" for name in VERSION_PACKAGES)
    return f"{STEP_MARKER} stage={stage} {shown} load={load}"


def light_switch_on(environ: Mapping[str, str]) -> bool:
    """끄개가 내려져 있지 않은가 — `LIGHT_SWITCH_ENV` 가 `off` 가 아니면 가벼운 길을 볼 수 있다."""
    return environ.get(LIGHT_SWITCH_ENV, "").strip().lower() != LIGHT_SWITCH_OFF


def version_package() -> str:
    """돌고 있는 파이썬의 판 하위 꾸러미 이름(`py310` 꼴)."""
    return f"py{sys.version_info.major}{sys.version_info.minor}"


def light_folder(installed: str, environ: Mapping[str, str]) -> tuple[list[str], str] | None:
    """가벼운 길로 갈 수 있으면 (꾸러미 자리들, 판 하위 꾸러미 폴더), 아니면 `None`.

    끄개 · 설치 판(`installed` — 설치 정보에서 읽은 판) · 이미 불러옴 · 꾸러미 자리 · 판 폴더만 보고
    패키지 코드를 돌리지 않는다 — 자리 찾기(`find_spec`)는 맨 위 이름에만 쓴다(점이 든 이름은 부모를
    불러와 그 `__init__` 을 돌린다). 읽다 무엇이 나도 `None` 이다."""
    if not light_switch_on(environ) or installed != LIGHT_VERSION:
        return None
    if LIGHT_PACKAGE in sys.modules:
        return None
    try:
        spec = importlib.util.find_spec(LIGHT_PACKAGE)
        places = list(spec.submodule_search_locations or ()) if spec is not None else []
        for place in places:
            folder = os.path.join(place, version_package())
            if os.path.isdir(folder):
                return places, folder
    except Exception:  # 자리를 못 읽으면 지금처럼 전체 길이다
        return None
    return None


def fill_package(package: types.ModuleType) -> None:
    """빈 판 하위 꾸러미를 채우는 자리 — 원래 그 `__init__` 이 import 때 하던 일 가운데 로그인에
    드는 것만 대신한다. 지금은 `nest_asyncio.apply()` 하나다. `server_auth` 가 그 `__init__` 이
    만들던 전역을 기대한다고 확인되면 여기서 `package` 에 채운다 — 짐작으로 패키지 함수를 부르지
    않는다."""
    del package
    importlib.import_module("nest_asyncio").apply()


def _block_present() -> bool:
    """`LIGHT_BLOCKED` 가 막혀 있는가(값이 `None` 인 항목)."""
    return LIGHT_BLOCKED in sys.modules and sys.modules.get(LIGHT_BLOCKED) is None


def _lift_block(blocked: bool) -> None:
    """우리가 둔 막음을 걷는다(`blocked` 이고 값이 아직 `None` 인 것만). 막은 동안 불린 모듈이
    정한 「없음」 은 그대로 남는다."""
    if blocked and _block_present():
        del sys.modules[LIGHT_BLOCKED]


def _drop_light(blocked: bool) -> None:
    """가벼운 길이 심은 것을 걷는다 — `bigdataquery` 와 `bigdataquery.` 로 시작하는 모듈 모두,
    그리고 우리가 둔 막음(`_lift_block`)."""
    for name in list(sys.modules):
        if name == LIGHT_PACKAGE or name.startswith(f"{LIGHT_PACKAGE}."):
            sys.modules.pop(name, None)
    _lift_block(blocked)


def load_light(places: list[str], folder: str) -> types.SimpleNamespace | None:
    """가벼운 길 — 빈 꾸러미 둘(`__path__` 만 — 판 하위 꾸러미는 맨 위 꾸러미의 속성으로 묶는다)을
    심고 판 하위 꾸러미의 `server_auth` 만 불러와 `login` · `getTokenTime` 을 묶는다
    (`nest_asyncio.apply()` 는 `fill_package` 가 부른다). `pyarrow` 는 `server_auth` 를 불러오는
    동안만 막고 묶은 뒤 걷는다 — 그 뒤 `login()` · `getTokenTime` 이 늦게 불러와도 선다. 그 앞에
    이미 불린 `pyarrow` 는 막지 않는다. 무엇이 실패해도(예외 · 속성 없음 · 부를 수 없음) 심은 것을
    걷고 `None` 이다 — 부르는 쪽이 같은 프로세스에서 전체 import 로 간다. 단계 줄 `login` 을
    내보내기 전에 끝난다."""
    blocked = False
    try:
        top = types.ModuleType(LIGHT_PACKAGE)
        top.__path__ = list(places)
        child = version_package()
        name = f"{LIGHT_PACKAGE}.{child}"
        package = types.ModuleType(name)
        package.__path__ = [folder]
        fill_package(package)
        # 하위 꾸러미를 불러온 import 가 부모 속성으로 묶는 일 — 손으로 심어 빠지는 몫이다.
        setattr(top, child, package)
        sys.modules[LIGHT_PACKAGE] = top
        sys.modules[name] = package
        if LIGHT_BLOCKED not in sys.modules:
            sys.modules[LIGHT_BLOCKED] = None  # type: ignore[assignment]  # 막음 꼴(값 None)
            blocked = True
        auth = importlib.import_module(f"{name}.{LIGHT_MODULE}")
        login = getattr(auth, "login", None)
        token_time = getattr(auth, "getTokenTime", None)
        if callable(login) and callable(token_time):
            _lift_block(blocked)
            return types.SimpleNamespace(login=login, getTokenTime=token_time)
    except BaseException:  # 가벼운 길에만 있는 실패는 무엇이든 전체 길로 돌아간다
        pass
    _drop_light(blocked)
    return None


def _emit(line: str) -> bool:
    """한 줄을 표준 출력에 쓰고 곧바로 비운다. 쓰지 못했으면 `False`."""
    stream = sys.__stdout__
    if stream is None:
        return False
    try:
        stream.write(f"\n{line}\n")
        stream.flush()
    except (OSError, ValueError):
        return False
    return True


def run(emit: Callable[[str], object] = _emit) -> str:
    """로그인 한 번 → 표지 한 줄(찍지 않고 돌려준다). 단계 줄은 그 자리에서 `emit` 으로 내보낸다 —
    단계 줄 `login` 을 내보내지 못하면(`emit` 이 `False`) `login()` 에 들어가지 않는다.

    가벼운 길(`light_folder` · `load_light`)이 서면 묶은 `login` · `getTokenTime` 을 부르고, 아니면
    지금처럼 패키지 전체를 불러와 부른다 — 전체 길은 속성을 미리 묶지 않는다(없으면 `login()` 의
    try 안에서 터진다)."""
    account = sys.stdin.readline().rstrip("\r\n")
    if not account:
        return marker_line("input")
    versions = {name: installed_version(name) for name in VERSION_PACKAGES}
    module: types.ModuleType | types.SimpleNamespace | None = None
    found = light_folder(versions["bigdataquery"], os.environ)
    if found is not None:
        emit(step_line("import", versions, LOAD_LIGHT))
        module = load_light(*found)
    load = LOAD_FULL if module is None else LOAD_LIGHT
    if module is None:
        emit(step_line("import", versions, LOAD_FULL))
        # 패키지 초기화가 낼 종류를 모른다 — 무엇이든 로그인 시도 없음.
        try:
            module = importlib.import_module("bigdataquery")
        except BaseException as error:
            return marker_line("import", error=qualified_name(error))
    versions = {name: loaded_version(name, versions[name]) for name in VERSION_PACKAGES}
    if emit(step_line("login", versions, load)) is False:
        return marker_line("import", error=STEP_UNWRITTEN)
    try:
        module.login()
    except BaseException as error:  # 틀린 비밀번호 · 연결 · 종료 요청까지 모두 종류 이름만 남긴다
        return marker_line("login", error=qualified_name(error), net=is_unreached(error))
    versions = {name: loaded_version(name, versions[name]) for name in VERSION_PACKAGES}
    emit(step_line("time", versions, load))
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
