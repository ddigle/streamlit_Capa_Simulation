# Purpose: BDQ 로그인 가벼운 길 시험의 가짜 패키지를 임시 자리에 짓는다.

"""가벼운 불러오기 길 시험의 가짜 패키지.

기존 가짜(`tests/fixtures/bdq_fake/`)는 설치 정보(dist-info) · 판 하위 꾸러미가
없어 늘 전체 길이다. 이 가짜는 시험마다 임시 자리에 지어 하위 프로세스가
`PYTHONPATH` 로 찾는다 — 판 하위 꾸러미 이름은 돌고 있는 파이썬의
`py<주판><부판>` 이고, 설치 정보의 판은 `version` 이다.

- 꾸러미 `__init__` · 판 하위 꾸러미 `__init__` 은 불리면 부른 기록
  (`FAKE_BDQ_LOG`)에 `package_init` · `version_init` 을 남긴다 — 가벼운 길이
  그것을 돌리지 않았음을 시험이 본다. 판 하위 꾸러미 `__init__` 은
  `nest_asyncio.apply()` 를 부르고(없으면 건너뜀) 준비 표지 `PACKAGE_READY` 를
  둔 뒤 `server_auth` 를 불러온다.
- `server_auth` 는 형제 `config` · `meta` · `util` · `exceptions` 를
  불러오고(`sibling <이름>`), 불러올 때 준비 표지와 `pyarrow` 가 막혔는지를
  `server_auth ready=<0|1> pyarrow=<blocked|open>` 으로 남긴다. `login()` 은
  기존 가짜와 같이 표준 입력 두 줄을 읽고 맞으면 토큰 파일을 쓴다(`login`).
- 대신 모듈 `nest_asyncio` — `nest=True` 면 `apply()` 가 `nest_apply` 를
  남기고, `False` 면 불러올 때 `ImportError`(진짜가 깔려 있어도 없는 꼴).
- 장면(`FAKE_BDQ_SCENE`)은 판 하위 꾸러미 `__init__` 을 거치지 않은
  `server_auth`(가벼운 길)에서만 든다 — 전체 길은 그대로 선다:
  `light_import_raises`(불러올 때 예외) · `light_import_kill`(불러올 때 제
  프로세스에 SIGKILL — POSIX) · `light_no_login` · `light_login_not_callable` ·
  `light_no_token_time` · `light_login_name_error`(`login()` 이 입력을 읽은 뒤
  `NameError` — 꾸러미 전역을 기대한 꼴).
"""

from __future__ import annotations

import sys
from pathlib import Path

PINNED_VERSION = "2.5.0"
# 판이 다른 설치 정보 — 실제 판이 아닌 합성 글.
OTHER_VERSION = "0.0.1+demo"

_TOP_INIT = """\
import os


def _trace(event):
    place = os.environ.get("FAKE_BDQ_LOG", "")
    if place:
        with open(place, "a", encoding="utf-8") as handle:
            handle.write(event + "\\n")


_trace("package_init")
__version__ = "{version}"
from bigdataquery.{sub} import getTokenTime, login
"""

_SUB_INIT = """\
from .util import trace

trace("version_init")
try:
    import nest_asyncio
except ImportError:
    pass
else:
    nest_asyncio.apply()
PACKAGE_READY = True
from .server_auth import getTokenTime, login
"""

_UTIL = """\
import os


def trace(event):
    place = os.environ.get("FAKE_BDQ_LOG", "")
    if place:
        with open(place, "a", encoding="utf-8") as handle:
            handle.write(event + "\\n")


trace("sibling util")
"""

_SIBLING = """\
from .util import trace

trace("sibling {name}")
"""

_EXCEPTIONS = """\
from .util import trace

trace("sibling exceptions")


class TokenNotFoundException(Exception):
    pass
"""

_SERVER_AUTH = """\
import getpass
import hashlib
import os
import secrets
import signal
import sys
import time
from pathlib import Path

from . import config, meta
from .exceptions import TokenNotFoundException
from .util import trace

_SCENES = frozenset(
    part.strip() for part in os.environ.get("FAKE_BDQ_SCENE", "").split(",") if part.strip()
)
_READY = bool(getattr(sys.modules[__name__.rpartition(".")[0]], "PACKAGE_READY", False))
_BLOCKED = "pyarrow" in sys.modules and sys.modules["pyarrow"] is None
trace(f"server_auth ready={int(_READY)} pyarrow={'blocked' if _BLOCKED else 'open'}")


def _light(name):
    return not _READY and name in _SCENES


if _light("light_import_raises"):
    raise RuntimeError("fake server_auth needs the package init")
if _light("light_import_kill") and sys.platform != "win32":
    os.kill(os.getpid(), signal.SIGKILL)


def _token_path(account):
    return Path(os.environ.get("FAKE_BDQ_CREDENTIAL_DIR", ".")) / f"bigdataquery.token.{account}"


def _read_password(prompt):
    if os.name == "nt":
        return str(vars(getpass)["fallback_getpass"](prompt))
    return getpass.getpass(prompt)


def _login():
    trace("login")
    account = input("AD Account : ")
    password = _read_password("Password : ")
    if _light("light_login_name_error"):
        raise NameError("name 'demo_global' is not defined")
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if digest != os.environ.get("FAKE_BDQ_PASSWORD_SHA256", ""):
        print("login failed")
        return
    target = _token_path(account)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{secrets.token_hex(12)}_{int(time.time() * 1000)}", encoding="utf-8")


def _token_time(user_name):
    if not _token_path(user_name).is_file():
        raise TokenNotFoundException("no token")
    return {"remaining_days": 0, "remaining_hours": 8, "remaining_minutes": 0}


if not _light("light_no_login"):
    login = "not callable" if _light("light_login_not_callable") else _login
if not _light("light_no_token_time"):
    getTokenTime = _token_time
"""

_NEST_PRESENT = """\
import os


def apply(loop=None):
    place = os.environ.get("FAKE_BDQ_LOG", "")
    if place:
        with open(place, "a", encoding="utf-8") as handle:
            handle.write("nest_apply\\n")
"""

_NEST_MISSING = 'raise ImportError("No module named nest_asyncio (fake)")\n'


def version_folder_name() -> str:
    """돌고 있는 파이썬의 판 하위 꾸러미 이름(`py<주판><부판>`)."""
    return f"py{sys.version_info.major}{sys.version_info.minor}"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_light_package(
    root: Path,
    *,
    version: str = PINNED_VERSION,
    folder: bool = True,
    nest: bool = True,
) -> Path:
    """가짜 패키지를 `root` 에 짓고 `root` 를 돌려준다(하위 프로세스의 `PYTHONPATH` 자리).

    `folder=False` 면 판 하위 꾸러미를 돌고 있는 파이썬과 다른 이름으로 둔다(전체 길은 그대로 선다).
    """
    sub = version_folder_name() if folder else "py00"
    package = root / "bigdataquery"
    _write(
        root / f"bigdataquery-{version}.dist-info" / "METADATA",
        f"Metadata-Version: 2.1\nName: bigdataquery\nVersion: {version}\n",
    )
    _write(package / "__init__.py", _TOP_INIT.format(version=version, sub=sub))
    _write(package / sub / "__init__.py", _SUB_INIT)
    _write(package / sub / "util.py", _UTIL)
    for name in ("config", "meta"):
        _write(package / sub / f"{name}.py", _SIBLING.format(name=name))
    _write(package / sub / "exceptions.py", _EXCEPTIONS)
    _write(package / sub / "server_auth.py", _SERVER_AUTH)
    _write(root / "nest_asyncio.py", _NEST_PRESENT if nest else _NEST_MISSING)
    return root
