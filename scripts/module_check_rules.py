# Purpose: 모듈 점검의 정적 규칙(M02 ~ M14·M18 ~ M21)을 모듈 폴더의 파일과 AST 로 본다.

"""모듈 정적 규칙 — `scripts/check_module.py` 가 부른다(사람이 직접 칠 일은 없다).

규칙 번호와 뜻은 `docs/module_guide.md` 부록 B 와 같아야 한다(`RULES` 가 코드 쪽 표다).
여기서는 모듈의 `.py` 를 import 하지 않는다 — `ast.parse(..., feature_version=(3, 10))` 로만
읽는다. 값(실데이터)은 찍지 않는다. 찍는 것은 규칙 · 파일 · 줄 · 고칠 말이다.

판정할 수 없는 식(변수로 만든 키 · 넘겨받은 콜백 등)은 대부분 넘긴다 — 정적 점검은 그물이고
실행 알림(`module_runtime`)과 감시 러너(`module_test_runner.py`)가 뒤를 받친다. 다만
지우기(`del st.session_state[k]`)·감싸지 않은 콜백은 판정할 수 없으면 오류로 본다(틀리면 코어
칸이 지워지거나 회차가 `app.py` 앞에서 끝난다).
"""

from __future__ import annotations

import ast
import functools
import importlib.metadata
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

Level = Literal["error", "warning"]

# 코드 쪽 규칙 표(번호 → 짧은 이름). 지침서 부록 B 와 번호 집합이 같아야 한다(통합 시험이 맞댄다).
RULES: Final[Mapping[str, str]] = {
    "M01": "선언",
    "M02": "st.set_page_config",
    "M03": "전역 CSS·JS·끼워 넣기",
    "M04": "st.sidebar·st.logo",
    "M05": "내비·주소",
    "M06": "코어 내부·같은 폴더 맨이름 import·창구 우회",
    "M07": "코어 데이터 자리",
    "M08": "세션 키 접두·세션 전역 조작",
    "M09": "패키지",
    "M10": "배경 실행",
    "M11": "프로세스 전역 상태",
    "M12": "캐시",
    "M13": "파일",
    "M14": "시험 없음",
    "M15": "ruff check",
    "M16": "ruff format",
    "M17": "자기 시험",
    "M18": "감싸지 않은 콜백",
    "M19": "폐기 예정 Streamlit 인자",
    "M20": "닫을 수 없는 팝업",
    "M21": "자격 · 비밀",
}
# 이 규칙 가운데 하나라도 오류면 자기 시험(M17)을 돌리지 않는다 — 코어 데이터 자리·코어 내부·배경
# 실행·프로세스 전역·자격을 건드리는 코드를 실행하지 않는다.
BLOCKING_RULES: Final = frozenset({"M01", "M06", "M07", "M10", "M11", "M21"})

CACHE_FILE: Final = "cache.py"
TESTS_DIR: Final = "tests"
README_NAME: Final = "README.md"
SKIP_DIRS: Final = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"})
PURPOSE_PREFIX: Final = "# Purpose: "
LARGE_FILE_BYTES: Final = 5 * 1024 * 1024
LARGE_JSON_BYTES: Final = 1024 * 1024
TEXT_SUFFIXES: Final = frozenset(
    {".py", ".md", ".json", ".txt", ".toml", ".yaml", ".yml", ".cfg", ".ini", ".csv", ".tsv"}
)
DATA_FILE_SUFFIXES: Final = frozenset(
    {".duckdb", ".db", ".sqlite", ".sqlite3", ".wal", ".xls", ".xlsx", ".xlsb", ".xlsm", ".env"}
)
PICKLE_SUFFIXES: Final = frozenset({".pkl", ".pickle"})
STYLE_SUFFIXES: Final = frozenset({".css", ".js", ".html", ".htm"})
DATA_LIKE_SUFFIXES: Final = frozenset(
    {".csv", ".tsv", ".parquet", ".feather", ".arrow", ".npy", ".npz"}
)
ASSETS_DIR: Final = "assets"

# 그 이름을 쓰는 순간 앱이나 다른 모듈과 겹치는 Streamlit 이름(M02 ~ M05).
_PAGE_CONFIG: Final = "streamlit.set_page_config"
_INJECTING_CALLS: Final = frozenset({"streamlit.html", "streamlit.iframe"})
_INJECTING_MARKERS: Final = ("<style", "<script", "<link", "<iframe")
_SIDEBAR_NAMES: Final = frozenset({"streamlit.sidebar", "streamlit.logo"})
_NAVIGATION_NAMES: Final = frozenset(
    {"streamlit.navigation", "streamlit.Page", "streamlit.switch_page", "streamlit.set_option"}
)
_QUERY_PARAMS: Final = "streamlit.query_params"
_SESSION_STATE: Final = "streamlit.session_state"
_SESSION_METHODS: Final = frozenset(
    {
        "get",
        "pop",
        "setdefault",
        "clear",
        "popitem",
        "update",
        "keys",
        "values",
        "items",
        "to_dict",
    }
)
_CALLBACK_KEYWORDS: Final = ("on_change", "on_click", "on_submit", "on_select", "on_dismiss")
_MODULE_API: Final = "capa_simulation.module_api"
# 글자 상수 하나로 모듈을 불러오는 호출 — 같은 import 규칙(M06·M09·M10)으로 본다.
_DYNAMIC_IMPORTS: Final = frozenset(
    {"importlib.import_module", "importlib.__import__", "builtins.__import__"}
)
# 창구(`module_api`)를 돌아 코어에 닿는 길(M06). 모듈은 코어와 한 프로세스라 이 길로 세션 비밀 ·
# S3 키 · 명단 쓰기 함수까지 닿는다. **막는 것은 쉬운 꼴뿐이다** — 의도를 가진 코드는 다른 길을 찾을
# 수 있어 점검 통과가 보증이 아니고, 방어선은 앱 관리자의 PR 점검이다(런북 4-6). 판정할 수 없으면
# 오류다.
_ESCAPE_ATTRIBUTES: Final = frozenset(
    {
        "__globals__",
        "__builtins__",
        "__subclasses__",
        "__self__",
        "f_globals",
        "f_locals",
        "f_builtins",
        "f_back",
        "tb_frame",
        "gi_frame",
        "cr_frame",
        "ag_frame",
    }
)
_ESCAPE_REFERENCES: Final = frozenset(
    {
        "sys.modules",
        "sys._getframe",
        "sys._current_frames",
        "inspect.currentframe",
        "inspect.stack",
        "inspect.trace",
        "inspect.getmodule",
        "inspect.getmembers",
        "inspect.getouterframes",
        "inspect.getinnerframes",
        "gc.get_objects",
        "gc.get_referrers",
        "gc.get_referents",
        "builtins.eval",
        "builtins.exec",
        "builtins.compile",
        "importlib.util",
        "importlib.machinery",
        "pkgutil",
        "pydoc",
        "runpy",
    }
)
_ESCAPE_BUILTINS: Final = frozenset({"eval", "exec", "compile"})
# 지침서 부록 B 의 M06 줄이 이 이름을 다 적는다(`tests/test_module_guide_sync.py`).
WINDOW_ESCAPE_NAMES: Final = _ESCAPE_ATTRIBUTES | _ESCAPE_REFERENCES | _ESCAPE_BUILTINS
# 값이 아니라 이 뿌리를 통째로 들여다보는 호출은 무엇을 꺼내는지 판정한다(`getattr(sys, 이름)`).
_REFLECTION_ROOTS: Final = frozenset(
    {
        "capa_simulation",
        "sys",
        "importlib",
        "builtins",
        "inspect",
        "gc",
        "pkgutil",
        "pydoc",
        "runpy",
    }
)
# 경로 마디를 잇는 호출 — 이은 글이 코어 데이터 자리를 가리키는지 본다(M07).
_PATH_JOINERS: Final = frozenset(
    {
        "os.path.join",
        "posixpath.join",
        "ntpath.join",
        "pathlib.Path",
        "pathlib.PurePath",
        "pathlib.PurePosixPath",
        "pathlib.PureWindowsPath",
    }
)
_CORE_TOP_NAMES: Final = frozenset({"app", "app_pages", "scripts", "tests"})
_TEST_ONLY_PACKAGES: Final = frozenset({"pytest", "_pytest"})

_CORE_DATA_MARKERS: Final = (
    "capa_simulation.duckdb",
    "equipment_availability.duckdb",
    "data/input",
    "data/output",
    "data/temp",
    ".deploy/",
    ".aws/",
)
# 프로세스 환경의 커널 사본이 있는 자리다 — `os.environ` 에서 지운 키도 여기 남는다. 뿌리에서 시작할
# 때만 그 자리다. `proc` 은 공정을 뜻하는 흔한 낱말이라 열 이름 · 모듈 폴더를 걸면 안 된다.
_KERNEL_MARKER: Final = "/proc/"
_KERNEL_PATTERN: Final = re.compile(r"(?<![\w.\-])/proc/")

# 자격 · 비밀(M21) — 2026-11-12 사용자 결정 「도우미 함수로」: BigDataQuery 요청자 계정 · 토큰과
# S3 키는 코어가 쥐고 모듈은 창구 도우미만 부른다. 그 환경변수 이름(글자 전체가 이름 꼴 — `$` ·
# `%` · `{}` 표지 허용, 대소문자 무시 — Windows 환경변수는 대소문자를 가리지 않는다. 그래서
# 같은 꼴의 데이터 열 이름도 걸린다)과 BigDataQuery 토큰 파일 자리를 막는다. 토큰 파일 자리는
# 경로 마디로만 잡는다 — 마디 전체가 `.credential`, 또는 `bigdataquery.token` 으로 시작하고
# 뒤가 `.<계정>` · 끝인 마디(역슬래시는 `/` 로 읽는다). 열 이름 · 설명 글 안의 낱말
# (`db.credential_log` · `(.credential)`)은 걸지 않는다. 글자로 찾는 그물이라 이름을 이어 만든
# 꼴은 못 잡는다(방어선은 PR 점검 — 런북 4-6). 시험 파일도 같다. `check_module.py` 는 모듈
# 시험의 환경에서 같은 이름의 변수를 뺀다.
CREDENTIAL_ENV_PREFIXES: Final = ("CAPA_BDQ_", "CAPA_S3_", "AWS_", "JWT_SECRET", "ADFS_")
_CREDENTIAL_NAME: Final = re.compile(
    r"[$%{]*(?P<name>(?:" + "|".join(CREDENTIAL_ENV_PREFIXES) + r")[A-Z0-9_]*)[}%]*",
    re.IGNORECASE,
)
_CREDENTIAL_FILE_PATTERNS: Final = (
    (".credential", re.compile(r"(?:^|/)\.credential(?:/|$)")),
    ("bigdataquery.token", re.compile(r"(?:^|/)bigdataquery\.token(?:[./]|$)")),
)
CREDENTIAL_FILE_MARKERS: Final = tuple(marker for marker, _ in _CREDENTIAL_FILE_PATTERNS)

_BACKGROUND_IMPORTS: Final = frozenset(
    {"threading", "_thread", "multiprocessing", "subprocess", "signal"}
)
_BACKGROUND_CALLS: Final = frozenset(
    {"os.system", "os.popen", "os.fork", "os.forkpty", "sys.exit", "os._exit", "os.abort"}
)
_BACKGROUND_PREFIXES: Final = ("os.spawn", "os.posix_spawn", "os.exec")
_BACKGROUND_WARN_IMPORTS: Final = frozenset({"asyncio", "argparse", "click", "typer", "fire"})

_GLOBAL_CALLS: Final = frozenset(
    {
        "os.putenv",
        "os.unsetenv",
        "os.chdir",
        "os.fchdir",
        "sys.setrecursionlimit",
        "sys.settrace",
        "sys.setprofile",
        "gc.disable",
        "gc.set_threshold",
        "gc.freeze",
        "socket.setdefaulttimeout",
        "locale.setlocale",
        "pandas.set_option",
        "pandas.reset_option",
        "numpy.seterr",
        "numpy.set_printoptions",
        "altair.themes.enable",
        "altair.theme.enable",
        "altair.data_transformers.enable",
        "altair.data_transformers.disable_max_rows",
        "matplotlib.use",
        "matplotlib.rcParams.update",
        "matplotlib.pyplot.rcParams.update",
        "matplotlib.style.use",
        "matplotlib.pyplot.style.use",
        "logging.basicConfig",
    }
)
_GLOBAL_MUTATORS: Final[Mapping[str, frozenset[str]]] = {
    "os.environ": frozenset({"update", "pop", "setdefault", "clear", "popitem", "__setitem__"}),
    "sys.path": frozenset({"append", "insert", "extend", "remove", "pop", "clear", "reverse"}),
    "sys.modules": frozenset({"pop", "update", "clear", "setdefault", "popitem"}),
}
_GLOBAL_TARGETS: Final = frozenset(
    {
        "sys.path",
        "sys.excepthook",
        "threading.excepthook",
        "plotly.io.templates.default",
        "plotly.io.renderers.default",
    }
)
# `px.defaults.template = …` 는 코어의 plotly express 그림(설비 일정 간트)까지 바꾼다.
_GLOBAL_TARGET_PREFIXES: Final = ("pandas.options.", "plotly.express.defaults.")
_GLOBAL_SUBSCRIPTS: Final = frozenset(
    {"os.environ", "sys.path", "sys.modules", "matplotlib.rcParams", "matplotlib.pyplot.rcParams"}
)
_ROOT_LOGGER_METHODS: Final = frozenset({"addHandler", "removeHandler", "setLevel"})
_WARNING_FILTERS: Final = frozenset(
    {"warnings.filterwarnings", "warnings.simplefilter", "warnings.resetwarnings"}
)
_MUTATING_METHODS: Final = frozenset(
    {
        "append",
        "extend",
        "insert",
        "add",
        "update",
        "pop",
        "popitem",
        "clear",
        "remove",
        "discard",
        "setdefault",
    }
)
_CACHE_DECORATORS: Final = frozenset({"streamlit.cache_data", "streamlit.cache_resource"})
_WRITE_METHODS: Final = frozenset(
    {"write_text", "write_bytes", "touch", "mkdir", "unlink", "rename", "replace", "rmdir"}
)
_FRAME_WRITERS: Final = frozenset(
    {"to_csv", "to_parquet", "to_excel", "to_json", "to_pickle", "to_feather"}
)
# 상대 경로 쓰기(M13 경고)에서 경로 글자를 감싸는 생성자와, 상대가 아닌 Windows 경로 꼴.
_PATH_CONSTRUCTORS: Final = frozenset({"pathlib.Path", "pathlib.PurePath"})
_WINDOWS_ABSOLUTE: Final = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{2})")
_DEPRECATED_KEYWORDS: Final[Mapping[str, str]] = {
    "use_container_width": 'width="stretch" 또는 width="content" 로 바꿉니다',
}
# 닫을 수 없게 연 팝업(M20 경고) — 처음 들어온 사람에게는 입장 화면이 먼저 덮이는데, 그 밑에 숨은
# 팝업이 앱 화면을 묶어 누름 · Enter · Esc 가 모두 보이지 않는 팝업에 닿는다(새로고침해도 같다).
_DIALOG: Final = "streamlit.dialog"

# CD 는 Linux 다 — 요구 파일의 환경 표지를 이 값으로 따진다.
LINUX_MARKER_VALUES: Final[Mapping[str, str]] = {
    "sys_platform": "linux",
    "platform_system": "Linux",
    "os_name": "posix",
}


@dataclass(frozen=True)
class Finding:
    """점검이 찾은 것 하나. `path` 는 모듈 폴더 기준 POSIX 상대 경로, `line` 0 은 파일 전체다."""

    rule: str
    level: Level
    path: str
    line: int
    message: str

    def text(self) -> str:
        label = "오류" if self.level == "error" else "경고"
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{label} {self.rule} {where} {self.message}"


# --- 패키지 환경(M09) ------------------------------------------------------------------------


@dataclass(frozen=True)
class Requirement:
    """`requirements.txt` 의 고정 줄 하나. `direct` 는 `# via` 에 `capa-simulation` 이 있는가."""

    name: str
    marker: str
    direct: bool


@dataclass(frozen=True)
class PackageEnvironment:
    """M09 가 보는 것 — 고정 요구(CD 이미지가 까는 것)·사내 전용·사외 요청 목록·설치된 배포."""

    requirements: Mapping[str, Requirement]
    company: frozenset[str]
    module_packages: frozenset[str]
    # 최상위 import 이름 → 배포 이름들.
    distributions: Mapping[str, Sequence[str]]


def normalize_name(name: str) -> str:
    """PEP 503 정규화 — 소문자, `-`·`_`·`.` 이어진 것을 `-` 하나로."""
    return re.sub(r"[-_.]+", "-", name).lower()


_REQUIREMENT_LINE: Final = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?P<rest>[^;]*)(?:;(?P<marker>.*))?$"
)


def parse_requirements(text: str) -> dict[str, Requirement]:
    """`uv export` 꼴 요구 파일 — 고정 줄과 그 아래 `# via` 묶음을 읽는다."""
    found: dict[str, tuple[str, list[str]]] = {}
    current: str | None = None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if raw[0].isspace():
            comment = raw.strip()
            if current is None or not comment.startswith("#"):
                continue
            body = comment.lstrip("#").strip()
            if body.startswith("via"):
                body = body[len("via") :].strip()
            if body:
                found[current][1].append(normalize_name(body))
            continue
        line = raw.strip()
        if line.startswith(("#", "-")):
            current = None
            continue
        matched = _REQUIREMENT_LINE.match(line)
        if matched is None:
            current = None
            continue
        current = normalize_name(matched.group("name"))
        found[current] = ((matched.group("marker") or "").strip(), [])
    return {
        name: Requirement(name=name, marker=marker, direct="capa-simulation" in via)
        for name, (marker, via) in found.items()
    }


def parse_name_list(text: str) -> frozenset[str]:
    """`requirements-company.txt` 꼴 — 주석·옵션 줄을 빼고 이름만."""
    names: set[str] = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        matched = _REQUIREMENT_LINE.match(line)
        if matched is not None:
            names.add(normalize_name(matched.group("name")))
    return frozenset(names)


def read_module_packages(path: Path) -> frozenset[str]:
    """`config/module_packages.json` 의 `packages`(없거나 못 읽으면 빈 목록)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return frozenset()
    packages = data.get("packages") if isinstance(data, dict) else None
    if not isinstance(packages, list):
        return frozenset()
    return frozenset(normalize_name(item) for item in packages if isinstance(item, str))


def installed_distributions() -> dict[str, list[str]]:
    """최상위 import 이름 → 배포 이름. Python 3.10 의 `packages_distributions` 는 `top_level.txt` 만
    읽어 pandas 같은 배포를 놓친다 — `RECORD`(배포 파일 목록)의 첫 마디도 함께 본다."""
    mapping: dict[str, list[str]] = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        if not name:
            continue
        tops: set[str] = set()
        top_level = dist.read_text("top_level.txt")
        if top_level:
            tops.update(line.strip() for line in top_level.splitlines() if line.strip())
        for file in dist.files or ():
            parts = file.parts
            if not parts:
                continue
            first = parts[0]
            if first in ("..", "__pycache__") or first.endswith(
                (".dist-info", ".egg-info", ".data")
            ):
                continue
            if len(parts) == 1:
                if first.endswith(".py"):
                    tops.add(first[: -len(".py")])
                continue
            tops.add(first)
        for top in tops:
            bucket = mapping.setdefault(top, [])
            if name not in bucket:
                bucket.append(name)
    return mapping


def load_environment(
    tree: Path, *, distributions: Mapping[str, Sequence[str]] | None = None
) -> PackageEnvironment:
    """점검하는 트리의 요구 파일 둘과 `config/module_packages.json` 을 읽는다."""

    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8-sig")
        except OSError:
            return ""

    return PackageEnvironment(
        requirements=parse_requirements(_read(tree / "requirements.txt")),
        company=parse_name_list(_read(tree / "requirements-company.txt")),
        module_packages=read_module_packages(tree / "config" / "module_packages.json"),
        distributions=installed_distributions() if distributions is None else distributions,
    )


_MARKER_TOKEN: Final = re.compile(
    r"\s*(\(|\)|not\s+in\b|in\b|and\b|or\b|==|!=|<=|>=|<|>|'[^']*'|\"[^\"]*\"|[A-Za-z_][A-Za-z0-9_.]*)"
)


class _UnknownMarker(Exception):
    """따질 수 없는 환경 표지(모르는 변수·꼴)."""


def _marker_tokens(marker: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    text = marker.strip()
    while position < len(text):
        matched = _MARKER_TOKEN.match(text, position)
        if matched is None:
            raise _UnknownMarker(text)
        tokens.append(re.sub(r"\s+", " ", matched.group(1)))
        position = matched.end()
    return tokens


def _version(text: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        raise _UnknownMarker(text) from None


def _marker_value(token: str) -> tuple[str, str]:
    """(값, 종류) — 종류는 `str` · `version` · `var`."""
    if token[:1] in ("'", '"'):
        return token[1:-1], "str"
    if token in LINUX_MARKER_VALUES:
        return LINUX_MARKER_VALUES[token], "str"
    if token == "python_version":
        return f"{sys.version_info.major}.{sys.version_info.minor}", "version"
    if token == "python_full_version":
        info = sys.version_info
        return f"{info.major}.{info.minor}.{info.micro}", "version"
    raise _UnknownMarker(token)


def _compare(left: str, op: str, right: str, *, version: bool) -> bool:
    if op == "in":
        return left in right
    if op == "not in":
        return left not in right
    if version:
        a, b = _version(left), _version(right)
        width = max(len(a), len(b))
        a, b = a + (0,) * (width - len(a)), b + (0,) * (width - len(b))
        outcome = {"==": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}
    else:
        outcome = {"==": left == right, "!=": left != right}
    if op not in outcome:
        raise _UnknownMarker(op)
    return outcome[op]


class _MarkerParser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.index = 0

    def _peek(self) -> str | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _take(self) -> str:
        token = self._peek()
        if token is None:
            raise _UnknownMarker("끝")
        self.index += 1
        return token

    def expression(self) -> bool:
        value = self._conjunction()
        while self._peek() == "or":
            self._take()
            value = self._conjunction() or value
        return value

    def _conjunction(self) -> bool:
        value = self._atom()
        while self._peek() == "and":
            self._take()
            value = self._atom() and value
        return value

    def _atom(self) -> bool:
        if self._peek() == "(":
            self._take()
            value = self.expression()
            if self._take() != ")":
                raise _UnknownMarker(")")
            return value
        left, left_kind = _marker_value(self._take())
        op = self._take()
        right, right_kind = _marker_value(self._take())
        return _compare(left, op, right, version="version" in (left_kind, right_kind))


def marker_on_linux(marker: str) -> bool | None:
    """요구 줄의 환경 표지가 CD(Linux, 이 Python 판)에서 참인가. 따질 수 없으면 None."""
    if not marker.strip():
        return True
    try:
        parser = _MarkerParser(_marker_tokens(marker))
        value = parser.expression()
        if parser.index != len(parser.tokens):
            return None
        return value
    except _UnknownMarker:
        return None


# --- 이름 풀기 --------------------------------------------------------------------------------


def _module_level_statements(body: Sequence[ast.stmt]) -> Iterator[ast.stmt]:
    """모듈 수준 문장 — `if`·`try`·`with`·`for` 안까지, 함수·클래스 본문은 빼고."""
    for statement in body:
        yield statement
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for name in ("body", "orelse", "finalbody"):
            inner = getattr(statement, name, None)
            if isinstance(inner, list):
                yield from _module_level_statements(inner)
        for handler in getattr(statement, "handlers", ()) or ():
            if isinstance(handler, ast.ExceptHandler):
                yield from _module_level_statements(handler.body)


class _Names:
    """한 파일의 import 별명과 모듈 수준 한 번 대입을 들고 이름을 점 이름으로 푼다.

    예: `st.sidebar` → `streamlit.sidebar`.
    """

    def __init__(self, tree: ast.Module) -> None:
        self.aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        self.aliases[alias.asname] = alias.name
                    else:
                        top = alias.name.split(".")[0]
                        self.aliases[top] = top
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                for alias in node.names:
                    if alias.name != "*":
                        self.aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        assigned: dict[str, list[ast.expr]] = {}
        for statement in _module_level_statements(tree.body):
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(statement, ast.Assign):
                targets, value = list(statement.targets), statement.value
            elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
                targets, value = [statement.target], statement.value
            for target in targets:
                if isinstance(target, ast.Name) and value is not None:
                    assigned.setdefault(target.id, []).append(value)
        # 한 번만 대입한 이름만 믿는다 — 두 번 이상이면 어느 값인지 정적으로 모른다.
        self.single: dict[str, ast.expr] = {
            name: values[0] for name, values in assigned.items() if len(values) == 1
        }
        self.module_names = set(assigned)
        # 함수 안까지 파일 전체에서 한 번만 대입한 이름 — `def main(): cb = ctx.callback(f)` 꼴의
        # 감싼 콜백을 알아본다(`is_method_call` 만 쓴다 — 별명 풀기는 모듈 수준만 믿는다).
        everywhere: dict[str, list[ast.expr]] = {}
        for inner in ast.walk(tree):
            if isinstance(inner, ast.Assign):
                for target in inner.targets:
                    if isinstance(target, ast.Name):
                        everywhere.setdefault(target.id, []).append(inner.value)
            elif isinstance(inner, ast.AnnAssign) and inner.value is not None:
                if isinstance(inner.target, ast.Name):
                    everywhere.setdefault(inner.target.id, []).append(inner.value)
        self.single_anywhere: dict[str, ast.expr] = {
            name: values[0] for name, values in everywhere.items() if len(values) == 1
        }
        self._resolving: set[str] = set()

    def resolve(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            if node.id in self.aliases:
                return self.aliases[node.id]
            value = self.single.get(node.id)
            if value is not None and node.id not in self._resolving:
                self._resolving.add(node.id)
                try:
                    resolved = self.resolve(value)
                finally:
                    self._resolving.discard(node.id)
                # 별명으로 믿는 것은 Streamlit 이름뿐이다(`state = st.session_state`·
                # `cache = st.cache_data`·`sb = st.sidebar`) — 금지 이름을 별명으로 비켜 가지
                # 못하게.
                if resolved is not None and (
                    resolved == "streamlit" or resolved.startswith("streamlit.")
                ):
                    return resolved
            return None
        if isinstance(node, ast.Attribute):
            base = self.resolve(node.value)
            return None if base is None else f"{base}.{node.attr}"
        return None

    def constant(self, node: ast.AST, depth: int = 0) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name) and depth < 3:
            value = self.single.get(node.id)
            if value is not None:
                return self.constant(value, depth + 1)
        return None

    def is_method_call(self, node: ast.AST, method: str, depth: int = 0) -> bool:
        """`<무엇>.<method>(…)` 호출이거나 그것을 한 번 대입한 이름인가."""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            return node.func.attr == method
        if isinstance(node, ast.Name) and depth < 3:
            value = self.single.get(node.id) or self.single_anywhere.get(node.id)
            if value is not None:
                return self.is_method_call(value, method, depth + 1)
        return False


# --- 파일 하나의 AST 규칙 ----------------------------------------------------------------------


@dataclass
class _WriteTaint:
    """`__file__`(또는 `ctx.folder`)에서 나온 경로를 담은 모듈 수준 이름과 문맥 이름."""

    names: set[str] = field(default_factory=set)
    contexts: set[str] = field(default_factory=set)


@dataclass
class _FileContext:
    module_id: str
    rel: str
    is_page: bool
    is_test: bool
    is_cache_file: bool
    local_names: frozenset[str]
    environment: PackageEnvironment
    findings: list[Finding] = field(default_factory=list)
    third_party: set[str] = field(default_factory=set)
    strings: list[tuple[int, str]] = field(default_factory=list)
    taint: _WriteTaint = field(default_factory=_WriteTaint)

    @property
    def prefix(self) -> str:
        return f"mod_{self.module_id}__"

    def add(self, rule: str, level: Level, node: ast.AST | int, message: str) -> None:
        line = node if isinstance(node, int) else int(getattr(node, "lineno", 0))
        self.findings.append(Finding(rule, level, self.rel, line, message))


@functools.lru_cache(maxsize=1)
def module_api_names() -> frozenset[str]:
    """`capa_simulation.module_api.__all__` — 모듈이 창구에서 쓸 수 있는 이름(겉면) 전부."""
    from capa_simulation import module_api

    return frozenset(module_api.__all__)


def _outside_surface(resolved: str) -> str | None:
    """`capa_simulation.<…>` 참조가 창구 겉면 밖으로 처음 벗어난 마디까지의 이름(아니면 None).

    마디마다 한 번만 걸리게 벗어난 그 마디에서만 이름을 돌려준다 — `api.module_registry.settings`
    는 `…module_api.module_registry` 하나로 센다.
    """
    parts = resolved.split(".")
    if parts[0] != "capa_simulation" or len(parts) == 1:
        return None
    if parts[1] != "module_api":
        return resolved if len(parts) == 2 else None
    if len(parts) == 3 and parts[2] not in module_api_names():
        return resolved
    return None


def _root_name(node: ast.AST) -> ast.Name | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node if isinstance(node, ast.Name) else None


def _short(text: str, limit: int = 30) -> str:
    flat = text.replace("\n", " ")
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _key_verdict(names: _Names, node: ast.AST, prefix: str, depth: int = 0) -> tuple[str, str]:
    """(판정, 보일 글) — 판정은 `ok` · `bad` · `unknown`."""
    if names.is_method_call(node, "key"):
        return "ok", ""
    text = names.constant(node)
    if text is not None:
        return ("ok", text) if text.startswith(prefix) else ("bad", text)
    if isinstance(node, ast.JoinedStr):
        first = node.values[0] if node.values else None
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            shown = first.value + "{…}"
            return ("ok", shown) if first.value.startswith(prefix) else ("bad", shown)
        return "unknown", ""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and depth < 3:
        verdict, shown = _key_verdict(names, node.left, prefix, depth + 1)
        return verdict, shown + "+…" if shown else shown
    return "unknown", ""


def _is_widget_call(names: _Names, call: ast.Call) -> bool:
    """`key=`·`on_*=` 를 볼 호출 — Streamlit 이름으로 풀리는 것과 풀리지 않는 속성 호출(`col.x`).

    다른 라이브러리로 풀리는 호출(`pd.Grouper(key=…)`)과 맨 함수 호출(`sorted(key=…)`)은 넘긴다.
    """
    resolved = names.resolve(call.func)
    if resolved is not None:
        return resolved.startswith("streamlit.")
    return isinstance(call.func, ast.Attribute)


def _contains_markers(text: str) -> str | None:
    lowered = text.lower()
    return next((marker for marker in _INJECTING_MARKERS if marker in lowered), None)


def _core_data_marker(text: str) -> str | None:
    """글자가 코어 데이터 자리를 가리키는가. 끝 슬래시 없이 쓴 마디(`~/.aws`)도 같다."""
    lowered = text.lower().replace("\\", "/")
    if _KERNEL_PATTERN.search(f"{lowered}/"):
        return _KERNEL_MARKER
    edged = f"/{lowered}/"
    return next(
        (
            marker
            for marker in _CORE_DATA_MARKERS
            if marker in lowered or f"/{marker.strip('/')}/" in edged
        ),
        None,
    )


def credential_marker(text: str) -> str | None:
    """글자가 자격 · 비밀 자리(M21)를 가리키면 보일 글(환경변수 이름 또는 토큰 파일 표지)."""
    found = _CREDENTIAL_NAME.fullmatch(text.strip())
    if found is not None:
        return found["name"]
    lowered = text.strip().lower().replace("\\", "/")
    return next(
        (marker for marker, pattern in _CREDENTIAL_FILE_PATTERNS if pattern.search(lowered)), None
    )


def _check_imports(tree: ast.Module, context: _FileContext) -> None:
    own = f"modules.{context.module_id}"
    for node in ast.walk(tree):
        imported: list[tuple[str, str | None]] = []
        if isinstance(node, ast.Import):
            imported = [(alias.name, None) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if context.is_page:
                    context.add(
                        "M06",
                        "error",
                        node,
                        "화면 파일은 `__main__` 으로 돌아 상대 import 가 깨집니다 — "
                        f"`from {own} import <이름>` 으로 부릅니다",
                    )
                continue
            if not node.module:
                continue
            imported = [(node.module, alias.name) for alias in node.names]
        for module, member in imported:
            _check_one_import(node, module, member, context, own)


def _check_one_import(
    node: ast.AST, module: str, member: str | None, context: _FileContext, own: str
) -> None:
    top = module.split(".")[0]
    full = module if member is None else f"{module}.{member}"
    if top == "__future__":
        return
    if top == "capa_simulation":
        if module == _MODULE_API and member not in (None, "*") and member not in module_api_names():
            context.add(
                "M06",
                "error",
                node,
                f"`{member}` 이름은 창구 겉면(`module_api.__all__`) 밖의 코어 것입니다 — "
                "겉면 이름만 씁니다",
            )
            return
        if full == _MODULE_API or full.startswith(_MODULE_API + ".") or module == _MODULE_API:
            return
        context.add(
            "M06",
            "error",
            node,
            f"코어 내부 `{full}` 모듈을 import 합니다 — 코어는 `capa_simulation.module_api` 하나만 "
            "씁니다",
        )
        return
    if top == "modules":
        if (
            module == own
            or module.startswith(own + ".")
            or (module == "modules" and member == context.module_id)
        ):
            return
        what = "맨 `modules`" if module == "modules" else f"다른 모듈 `{module}`"
        context.add("M06", "error", node, f"{what} 코드를 import 합니다 — 자기 `{own}` 만 부릅니다")
        return
    if top in _CORE_TOP_NAMES:
        context.add(
            "M06",
            "error",
            node,
            f"코어 `{top}` 모듈을 import 합니다 — 코어는 `capa_simulation.module_api` 하나만 "
            "씁니다",
        )
        return
    if top in context.local_names:
        context.add(
            "M06",
            "error",
            node,
            f"같은 폴더 맨이름 `import {top}` 꼴은 앱에서 깨집니다 — `from {own} import {top}` "
            "꼴로 부릅니다",
        )
        return
    if top in sys.stdlib_module_names:
        if not context.is_test:
            _check_background_import(node, module, member, context)
        return
    if top == "streamlit":
        if module.startswith("streamlit.components") or (
            module == "streamlit" and member == "components"
        ):
            context.add(
                "M03",
                "error",
                node,
                "`streamlit.components` 는 쓰지 않습니다(전역 이름·끼워 넣기 — iframe 방식 금지)",
            )
        return
    if context.is_test and top in _TEST_ONLY_PACKAGES:
        return
    if not context.is_test and top in _BACKGROUND_WARN_IMPORTS:
        _check_background_import(node, module, member, context)
    context.third_party.add(top)
    _check_package(node, top, context)


def _check_background_import(
    node: ast.AST, module: str, member: str | None, context: _FileContext
) -> None:
    top = module.split(".")[0]
    full = module if member is None else f"{module}.{member}"
    if top in _BACKGROUND_IMPORTS or full.startswith("concurrent.futures"):
        context.add(
            "M10",
            "error",
            node,
            f"`{top if top != 'concurrent' else 'concurrent.futures'}` 모듈을 씁니다 — 모듈은 "
            "스레드·프로세스를 세우지 않습니다(모든 사용자와 한 프로세스)",
        )
    elif top in _BACKGROUND_WARN_IMPORTS:
        reason = (
            "회차 안에서 이벤트 루프를 돌리지 않습니다"
            if top == "asyncio"
            else "명령줄을 읽는 코드는 지웁니다(`SystemExit` 을 냅니다)"
        )
        context.add("M10", "warning", node, f"`{top}` — {reason}")


def _check_package(node: ast.AST, top: str, context: _FileContext) -> None:
    environment = context.environment
    distributions = environment.distributions.get(top)
    if not distributions:
        context.add(
            "M09",
            "error",
            node,
            f"`import {top}` — 이 서버에 설치되지 않은 이름입니다(담당자 → 앱 관리자 → 사외 요청)",
        )
        return
    names = [normalize_name(name) for name in distributions]
    pinned = [environment.requirements[name] for name in names if name in environment.requirements]
    if not pinned:
        if any(name in environment.company for name in names):
            hint = (
                " — 조회는 `api.query_bigdataquery` 를 씁니다(계정 · 토큰을 코어가 쥔다)"
                if top == "bigdataquery"
                else ""
            )
            context.add(
                "M09",
                "warning",
                node,
                f"`import {top}` — requirements-company.txt 에만 있습니다(CD 설치 보장 없음){hint}",
            )
            return
        context.add(
            "M09",
            "error",
            node,
            f"`import {top}` — requirements.txt 에 없습니다(담당자 → 앱 관리자 → 사외 요청)",
        )
        return
    verdicts = [(requirement, marker_on_linux(requirement.marker)) for requirement in pinned]
    usable = [requirement for requirement, on_linux in verdicts if on_linux]
    if not usable:
        if any(on_linux is None for _, on_linux in verdicts):
            context.add(
                "M09",
                "warning",
                node,
                f"`import {top}` — requirements.txt 의 환경 표지를 따질 수 없습니다(CD 는 Linux)",
            )
        else:
            context.add(
                "M09",
                "error",
                node,
                f"`import {top}` — CD(Linux)에 설치되지 않음(requirements.txt 의 환경 표지)",
            )
        return
    if any(req.direct or req.name in environment.module_packages for req in usable):
        return
    context.add(
        "M09",
        "warning",
        node,
        f"`import {top}` — 직접 의존 아님(코어가 끌어온 의존이라 빠질 수 있다) — 사외 요청으로 "
        "올린다",
    )


def _check_strings(tree: ast.Module, context: _FileContext) -> None:
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        text = node.value
        context.strings.append((int(getattr(node, "lineno", 0)), text))
        marker = _contains_markers(text)
        if marker is not None:
            context.add(
                "M03",
                "error",
                node,
                f"글자에 `{marker}` 꼴이 있습니다 — 전역 CSS·스크립트를 넣지 않습니다",
            )
        data_marker = _core_data_marker(text)
        if data_marker is not None:
            context.add(
                "M07",
                "error",
                node,
                f"코어 데이터 자리(`{data_marker}`)를 가리킵니다 — 모듈은 `ctx.data_dir` 만 씁니다",
            )
        elif text.replace("\\", "/").startswith("data/"):
            context.add(
                "M07",
                "warning",
                node,
                "`data/` 로 시작하는 경로입니다 — 모듈 데이터는 `ctx.data_dir` 를 씁니다",
            )
        credential = credential_marker(text)
        if credential is not None:
            context.add(
                "M21",
                "error",
                node,
                f"자격 · 비밀 자리(`{_short(credential)}`)를 가리킵니다 — 계정 · 토큰 · 키는 "
                "코어가 쥡니다. BigDataQuery 는 `api.query_bigdataquery`, S3 는 `api.s3_upload` · "
                "`api.s3_download` 를 씁니다",
            )


def _reference_rules(node: ast.AST, resolved: str, context: _FileContext) -> None:
    if resolved == _PAGE_CONFIG:
        context.add("M02", "error", node, "`st.set_page_config` 는 앱이 한 번 부릅니다 — 지웁니다")
    elif resolved in _INJECTING_CALLS:
        context.add(
            "M03",
            "error",
            node,
            f"`{resolved.replace('streamlit.', 'st.')}` 호출은 쓰지 않습니다(앱과 같은 출처로 끼워 "
            "넣습니다)",
        )
    elif resolved == "streamlit.components":
        context.add("M03", "error", node, "`st.components` 는 쓰지 않습니다(iframe 방식 금지)")
    elif resolved in _SIDEBAR_NAMES:
        context.add(
            "M04",
            "error",
            node,
            f"`{resolved.replace('streamlit.', 'st.')}` 자리는 앱이 씁니다 — 본문 위 `st.columns`·"
            '`st.expander("조건")` 로 옮깁니다',
        )
    elif resolved in _NAVIGATION_NAMES:
        context.add(
            "M05",
            "error",
            node,
            f"`{resolved.replace('streamlit.', 'st.')}` 호출은 앱이 맡습니다 — 화면은 "
            "module.json 의 pages 로, 이동은 사이드바·탭 줄로",
        )
    elif resolved == "streamlit.page_link":
        context.add(
            "M05",
            "warning",
            node,
            "`st.page_link` 는 단독 시험에서 죽습니다 — 화면 사이 이동은 사이드바·탭 줄이 합니다",
        )
    elif resolved in ("streamlit.cache_data.clear", "streamlit.cache_resource.clear"):
        context.add(
            "M12",
            "error",
            node,
            f"맨 `{resolved.replace('streamlit.', 'st.')}()` 호출은 코어 캐시까지 비웁니다 — "
            "자기 함수의 `.clear()` 를 씁니다",
        )


def _check_references(tree: ast.Module, names: _Names, context: _FileContext) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Name, ast.Attribute)):
            continue
        if (
            isinstance(node, ast.Attribute)
            and node.attr in ("parent", "parents")
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "data_dir"
        ):
            context.add(
                "M07",
                "error",
                node,
                f"`data_dir.{node.attr}` 경로는 모듈 데이터 자리 밖(코어 `data/`)입니다 — "
                "`ctx.data_dir` 안만 씁니다",
            )
        resolved = names.resolve(node)
        if resolved is None:
            continue
        _reference_rules(node, resolved, context)
        outside = _outside_surface(resolved)
        root = _root_name(node)
        # import 문이 이미 M06 으로 걸린 이름(`from capa_simulation import settings`)은 다시 세지
        # 않는다 — 허용된 import(`capa_simulation.module_api`·그 별명)로 들어와 속성으로 벗어난
        # 것만 본다.
        if (
            outside is not None
            and root is not None
            and names.aliases.get(root.id) in ("capa_simulation", _MODULE_API)
        ):
            context.add(
                "M06",
                "error",
                node,
                f"`{_short(outside.replace(_MODULE_API, 'api'), 50)}` 이름은 창구 겉면"
                "(`module_api.__all__`) 밖의 코어 것입니다 — 겉면 이름만 씁니다",
            )
        if context.is_test:
            continue
        if resolved in _BACKGROUND_CALLS or resolved.startswith(_BACKGROUND_PREFIXES):
            context.add(
                "M10",
                "error",
                node,
                f"`{resolved}` — 모듈은 프로세스를 끝내거나 새로 세우지 않습니다",
            )
        elif resolved in _GLOBAL_CALLS:
            context.add(
                "M11",
                "error",
                node,
                f"`{resolved}` 호출은 프로세스 전체(모든 사용자·코어)를 바꿉니다 — 지웁니다",
            )
        elif resolved in _WARNING_FILTERS:
            context.add(
                "M11",
                "warning",
                node,
                f"`{resolved}` 호출은 프로세스 전체의 경고 거름을 바꿉니다 — "
                "`warnings.catch_warnings()` 안에서만 씁니다",
            )


def _first_argument(call: ast.Call, keyword: str) -> ast.expr | None:
    if call.args:
        return call.args[0]
    return next((item.value for item in call.keywords if item.arg == keyword), None)


def _check_calls(tree: ast.Module, names: _Names, context: _FileContext) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        resolved = names.resolve(node.func)
        if not context.is_test and isinstance(node.func, ast.Name):
            if node.func.id in ("exit", "quit") and node.func.id not in names.aliases:
                context.add(
                    "M10", "error", node, f"`{node.func.id}()` — 모듈은 프로세스를 끝내지 않습니다"
                )
        _check_dynamic_import(node, resolved, names, context)
        _check_unsafe_html(node, names, context)
        _check_widget_keywords(node, names, context)
        if resolved is not None:
            _check_session_call(node, resolved, names, context)
            if not context.is_test:
                _check_global_call(node, resolved, context)
            if resolved == "streamlit.fragment" and not context.is_test:
                run_every = next((k.value for k in node.keywords if k.arg == "run_every"), None)
                if run_every is not None and not (
                    isinstance(run_every, ast.Constant) and run_every.value is None
                ):
                    context.add(
                        "M10",
                        "warning",
                        node,
                        "`st.fragment(run_every=…)` 는 모든 사용자 세션에서 계속 돕니다",
                    )
            if resolved == _DIALOG and not context.is_test:
                _check_dialog(node, context)
            if resolved in ("streamlit.query_params.clear", "streamlit.query_params.from_dict"):
                context.add(
                    "M05",
                    "error",
                    node,
                    f"`{resolved.replace('streamlit.', 'st.')}` 호출은 주소의 theme 인자까지 "
                    "지웁니다",
                )
        if not context.is_test:
            _check_root_logger(node, names, context)
        _check_file_write(node, names, context)


def _check_dialog(node: ast.Call, context: _FileContext) -> None:
    """`st.dialog(…, dismissible=…)` 에 `True` 가 아닌 값 — 닫기(✕·Esc·바깥 누름)가 없는 팝업."""
    dismissible = next((item.value for item in node.keywords if item.arg == "dismissible"), None)
    if dismissible is None or (isinstance(dismissible, ast.Constant) and dismissible.value is True):
        return
    shown = repr(dismissible.value) if isinstance(dismissible, ast.Constant) else "…"
    context.add(
        "M20",
        "warning",
        dismissible,
        f"`st.dialog(dismissible={shown})` — 닫을 수 없는 팝업은 처음 들어온 사람의 입장 화면 밑에 "
        "숨어 앱을 묶습니다. dismissible 을 빼고 단추를 눌렀을 때만 엽니다",
    )


def _is_bare_import(node: ast.AST, names: _Names) -> bool:
    return isinstance(node, ast.Name) and node.id == "__import__" and node.id not in names.aliases


def _check_dynamic_import(
    node: ast.Call, resolved: str | None, names: _Names, context: _FileContext
) -> None:
    """`importlib.import_module("x")`·`__import__("x")` — 글자 상수면 `import x` 와 같은 규칙.

    글자 상수가 아니면 무엇을 불러오는지 판정할 수 없어 오류다. 창구도 이 꼴로 부르지 않는다 —
    돌려받은 값의 속성은 겉면 판정(`_outside_surface`)을 지나지 않는다.
    """
    if not _is_bare_import(node.func, names) and resolved not in _DYNAMIC_IMPORTS:
        return
    target = names.constant(node.args[0]) if node.args else None
    if not target or target.startswith("."):
        context.add(
            "M06",
            "error",
            node,
            "글자 상수가 아닌 동적 import 는 무엇을 불러오는지 판정할 수 없습니다 — "
            "`import` 로 씁니다",
        )
        return
    if target.split(".")[0] == "capa_simulation":
        context.add(
            "M06",
            "error",
            node,
            f"`{target}` 모듈을 동적 import 로 부릅니다 — "
            "`from capa_simulation import module_api as api` 로 씁니다",
        )
        return
    _check_one_import(node, target, None, context, f"modules.{context.module_id}")


def _add_escape(node: ast.AST, shown: str, context: _FileContext) -> None:
    context.add(
        "M06",
        "error",
        node,
        f"`{shown}` 꼴은 창구(`module_api`)를 돌아 코어에 닿는 길입니다 — 창구 이름만 씁니다",
    )


def _is_escape_reference(resolved: str) -> bool:
    return resolved in _ESCAPE_REFERENCES or resolved.endswith(".sys.modules")


def _check_reflection_call(node: ast.Call, names: _Names, context: _FileContext) -> None:
    """`getattr(sys, "modules")`·`vars(api)` — 뿌리를 들여다보는 호출을 그 참조처럼 본다.

    값 객체(`getattr(row, 이름)`)는 넘긴다 — 뿌리가 `_REFLECTION_ROOTS` 인 것만 본다.
    """
    func = node.func
    if not isinstance(func, ast.Name) or func.id in names.aliases or not node.args:
        return
    if func.id not in ("getattr", "vars"):
        return
    owner = names.resolve(node.args[0])
    if owner is None or owner.split(".")[0] not in _REFLECTION_ROOTS:
        return
    attribute = (
        names.constant(node.args[1]) if func.id == "getattr" and len(node.args) > 1 else None
    )
    if attribute is None:
        _add_escape(node, f"{func.id}({owner}, …)", context)
        return
    resolved = f"{owner}.{attribute}"
    if (
        _is_escape_reference(resolved)
        or resolved in _DYNAMIC_IMPORTS
        or _outside_surface(resolved) is not None
    ):
        _add_escape(node, resolved, context)


def _check_window_escapes(tree: ast.Module, names: _Names, context: _FileContext) -> None:
    """창구를 돌아 코어에 닿는 꼴(M06) — 시험 파일도 같다(화면이 import 할 수 있다)."""
    called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            _check_reflection_call(node, names, context)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, str) and node.value in _ESCAPE_ATTRIBUTES:
                _add_escape(node, node.value, context)
        elif isinstance(node, ast.Attribute) and node.attr in _ESCAPE_ATTRIBUTES:
            _add_escape(node, node.attr, context)
        elif (
            isinstance(node, ast.Name)
            and node.id not in names.aliases
            and (node.id in _ESCAPE_ATTRIBUTES or node.id in _ESCAPE_BUILTINS)
        ):
            _add_escape(node, node.id, context)
        elif isinstance(node, (ast.Name, ast.Attribute)):
            if _is_bare_import(node, names) and id(node) not in called:
                _add_escape(node, "__import__", context)
                continue
            resolved = names.resolve(node)
            if resolved is None:
                continue
            # 이름으로 들어온 것(`from pkgutil import resolve_name`)은 그 아래 이름까지 본다 — 속성
            # 꼴은 윗마디(`pkgutil`)에서 한 번 걸린다.
            imported_under = (
                isinstance(node, ast.Name) and resolved.rsplit(".", 1)[0] in _ESCAPE_REFERENCES
            )
            if (
                _is_escape_reference(resolved)
                or imported_under
                or (resolved in _DYNAMIC_IMPORTS and id(node) not in called)
            ):
                _add_escape(node, resolved, context)


# 이름표(`ModuleContext`)를 손으로 짓는 꼴(M06) — 자기 id 가 아닌 이름표는 남의 데이터 자리
# (`data/modules/<그 id>/`)와 버킷의 `modules/<그 id>/` 를 읽고 덮는다(2026-11-12 사용자 답 ④-4
# (가)). 이름표는 `api.context(__file__)` 로만 받는다. 자기 id — 글자 상수(모듈 시험의 대역)와
# `api.context(__file__)` 이름표의 `.id` — 는 넘기고, 판정할 수 없는 id 는 오류다. 막는 것은
# 쉬운 꼴뿐이다 — 방어선은 앱 관리자의 PR 점검이다(런북 4-6).
CONTEXT_CLASS: Final = f"{_MODULE_API}.ModuleContext"
_CONTEXT_FACTORY: Final = f"{_MODULE_API}.context"
_DATACLASS_REPLACE: Final = "dataclasses.replace"
# 지침서 부록 B 의 M06 우회 줄이 이 꼴을 다 적는다(`tests/test_module_guide_sync.py`).
HAND_MADE_CONTEXT_FORMS: Final = (
    "ModuleContext(…)",
    "dataclasses.replace(ctx, id=…)",
    "type(ctx)(…)",
    "ctx.__class__(…)",
    'object.__setattr__(ctx, "id", …)',
)


def _context_holders(tree: ast.Module, names: _Names) -> set[str]:
    """이 파일에서 이름표를 담는 이름 — `api.context(…)` 를 대입한 이름과 `api.ModuleContext` 로
    적은 인자 · 이름."""
    holders: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arg):
            if node.annotation is not None and names.resolve(node.annotation) == CONTEXT_CLASS:
                holders.add(node.arg)
            continue
        targets: list[ast.expr]
        value: ast.expr | None
        annotation: ast.expr | None
        if isinstance(node, ast.Assign):
            targets, value, annotation = node.targets, node.value, None
        elif isinstance(node, ast.AnnAssign):
            targets, value, annotation = [node.target], node.value, node.annotation
        else:
            continue
        made = isinstance(value, ast.Call) and names.resolve(value.func) == _CONTEXT_FACTORY
        typed = annotation is not None and names.resolve(annotation) == CONTEXT_CLASS
        if made or typed:
            holders.update(target.id for target in targets if isinstance(target, ast.Name))
    return holders


def _holds_context(node: ast.AST, names: _Names, holders: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in holders
    return isinstance(node, ast.Call) and names.resolve(node.func) == _CONTEXT_FACTORY


def _is_own_context_call(node: ast.AST, names: _Names) -> bool:
    """글자 그대로 `api.context(__file__)` — 이 파일이 든 모듈의 이름표다."""
    return (
        isinstance(node, ast.Call)
        and names.resolve(node.func) == _CONTEXT_FACTORY
        and len(node.args) == 1
        and not node.keywords
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "__file__"
    )


def _own_context_names(tree: ast.Module, names: _Names) -> set[str]:
    """파일 어디서나 `api.context(__file__)` 만 대입한 이름 — 그 `.id` 는 자기 id 다. 다른 값 ·
    인자 · 반복 변수 · `with … as` 따위로도 묶이는 이름은 넣지 않는다(어느 이름표인지
    정적으로 모른다)."""
    stores: Counter[str] = Counter()
    own: Counter[str] = Counter()
    others: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            stores[node.id] += 1
        elif isinstance(node, ast.arg):
            others.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            others.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            others.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            others.update(node.names)
        if isinstance(node, ast.Assign) and _is_own_context_call(node.value, names):
            own.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and _is_own_context_call(node.value, names)
            and isinstance(node.target, ast.Name)
        ):
            own[node.target.id] += 1
    if stores["__file__"] or "__file__" in others:
        return set()
    return {
        name
        for name, count in own.items()
        if stores[name] == count and name not in others and name not in names.aliases
    }


def _is_own_id(node: ast.expr, names: _Names, own_names: set[str], module_id: str) -> bool:
    """자기 id 로 판정되는 식 — 자기 id 글자 상수(모듈 시험의 대역)와 `api.context(__file__)`
    이름표의 `.id`."""
    if names.constant(node) == module_id:
        return True
    if not (isinstance(node, ast.Attribute) and node.attr == "id"):
        return False
    base = node.value
    return (isinstance(base, ast.Name) and base.id in own_names) or _is_own_context_call(
        base, names
    )


def _context_id(node: ast.Call) -> ast.expr | None:
    """지어지는 이름표의 id 식 — 첫 자리 인자나 `id=`. `**` 로 넘기면 None(판정할 수 없음)."""
    for keyword in node.keywords:
        if keyword.arg == "id":
            return keyword.value
    if node.args and not isinstance(node.args[0], ast.Starred):
        return node.args[0]
    return None


def _check_hand_made_context(tree: ast.Module, names: _Names, context: _FileContext) -> None:
    """이름표를 손으로 짓는 꼴(M06) — `ModuleContext(…)` · `dataclasses.replace(ctx, id=…)` ·
    `type(ctx)(…)` · `ctx.__class__(…)` · `object.__setattr__(ctx, "id", …)`. 시험 파일도 같다."""
    holders = _context_holders(tree, names)
    own_names = _own_context_names(tree, names)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        given: ast.expr | None
        if names.resolve(func) == CONTEXT_CLASS:
            shown, given = "ModuleContext(…)", _context_id(node)
        elif (
            isinstance(func, ast.Call)
            and isinstance(func.func, ast.Name)
            and func.func.id == "type"
            and func.func.id not in names.aliases
            and len(func.args) == 1
            and _holds_context(func.args[0], names, holders)
        ):
            shown, given = "type(ctx)(…)", _context_id(node)
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "__class__"
            and _holds_context(func.value, names, holders)
        ):
            shown, given = "ctx.__class__(…)", _context_id(node)
        elif (
            names.resolve(func) == _DATACLASS_REPLACE
            and node.args
            and _holds_context(node.args[0], names, holders)
        ):
            keyword = {item.arg: item.value for item in node.keywords}
            if "id" not in keyword and None not in keyword:
                continue
            shown, given = "dataclasses.replace(ctx, id=…)", keyword.get("id")
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "__setattr__"
            and len(node.args) >= 2
            and _holds_context(node.args[0], names, holders)
            and names.constant(node.args[1]) == "id"
        ):
            shown = 'object.__setattr__(ctx, "id", …)'
            given = node.args[2] if len(node.args) >= 3 else None
        else:
            continue
        if given is not None and _is_own_id(given, names, own_names, context.module_id):
            continue
        what = (
            "판정할 수 없는 id 로"
            if given is None or names.constant(given) is None
            else "남의 id 로"
        )
        context.add(
            "M06",
            "error",
            node,
            f"`{shown}` 꼴로 이름표(`ModuleContext`)를 {what} 짓습니다 — 남의 데이터 자리와 버킷을 "
            "읽고 덮게 됩니다. 이름표는 `api.context(__file__)` 로만 받습니다",
        )


def _path_pieces(node: ast.AST, names: _Names, depth: int = 0) -> list[str | None] | None:
    """경로 식(`a / "b"`·`Path("a", "b")`·`os.path.join(…)`·`p.joinpath(…)`)의 마디 — 모르는 마디는
    None. 경로 식이 아니면 None."""
    if depth > 12:
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _path_pieces(node.left, names, depth + 1) or [names.constant(node.left)]
        right = _path_pieces(node.right, names, depth + 1) or [names.constant(node.right)]
        return [*left, *right]
    if isinstance(node, ast.Call):
        func = node.func
        base: list[str | None] = []
        if isinstance(func, ast.Attribute) and func.attr == "joinpath":
            base = _path_pieces(func.value, names, depth + 1) or [None]
        elif names.resolve(func) not in _PATH_JOINERS:
            return None
        pieces = [*base]
        for argument in node.args:
            pieces += _path_pieces(argument, names, depth + 1) or [names.constant(argument)]
        return pieces
    return None


def _check_joined_paths(tree: ast.Module, names: _Names, context: _FileContext) -> None:
    """마디로 나눠 이은 경로가 코어 데이터 자리를 가리키면 M07 오류.

    `… / "data" / "input"`·`os.path.join("data", "temp")` 꼴과 `ctx.data_dir / ".."` 꼴이다. 글자
    하나에 다 든 꼴은 글자 검사(`_check_strings`)가 이미 잡으므로 이은 뒤에야 서는 것만 본다.
    마디 경계에서만 맞댄다(`"data" / "input.csv"` 는 `data/input` 이 아니다).
    """
    # 바깥 경로 식 하나만 본다 — 안쪽 마디(`a / "b"` 의 `a`)를 다시 보면 같은 줄을 두 번 센다.
    inner: set[ast.AST] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            inner.update((node.left, node.right))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
                inner.add(node.func.value)
                inner.update(node.args)
            elif names.resolve(node.func) in _PATH_JOINERS:
                inner.update(node.args)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.BinOp, ast.Call)) or node in inner:
            continue
        pieces = _path_pieces(node, names)
        if not pieces or len(pieces) < 2:
            continue
        known = [piece for piece in pieces if piece is not None]
        if any(_core_data_marker(piece) is not None for piece in known):
            continue
        spelled = "/".join(piece if piece is not None else "?" for piece in pieces).lower()
        spelled = spelled.replace("\\", "/")
        joined = f"/{spelled}/"
        marker = next(
            (item for item in _CORE_DATA_MARKERS if f"/{item.strip('/')}/" in joined), None
        )
        if marker is None and re.sub("/+", "/", f"{spelled}/").startswith(_KERNEL_MARKER):
            marker = _KERNEL_MARKER
        if marker is not None:
            context.add(
                "M07",
                "error",
                node,
                f"이은 경로가 코어 데이터 자리(`{marker.rstrip('/')}`)를 가리킵니다 — 모듈은 "
                "`ctx.data_dir` 만 씁니다",
            )
        elif ".." in known and any(
            isinstance(inner, ast.Attribute) and inner.attr == "data_dir"
            for inner in ast.walk(node)
        ):
            context.add(
                "M07",
                "error",
                node,
                "`data_dir` 에서 `..` 로 올라갑니다 — 모듈 데이터 자리 밖(코어 `data/`)입니다",
            )


def _check_unsafe_html(node: ast.Call, names: _Names, context: _FileContext) -> None:
    flag = next((item.value for item in node.keywords if item.arg == "unsafe_allow_html"), None)
    if flag is None or (isinstance(flag, ast.Constant) and not flag.value):
        return
    body = _first_argument(node, "body")
    text = None if body is None else names.constant(body)
    if text is None:
        context.add(
            "M03",
            "error",
            node,
            "`unsafe_allow_html` 의 글이 글자 상수가 아닙니다(변수·f-문자열·읽은 글) — 꾸밈 "
            "글을 뺍니다",
        )
    elif _contains_markers(text) is None:
        context.add(
            "M03",
            "warning",
            node,
            "`unsafe_allow_html=True` — 전역 CSS 가 섞이지 않게 꾸밈 글을 빼세요",
        )


@functools.lru_cache(maxsize=256)
def _positional_slots(widget: str) -> Mapping[str, int]:
    """Streamlit 위젯 `st.<widget>` 의 `key`·콜백 인자가 위치 인자로도 올 수 있는 자리(0부터).

    `st.button("x", "plain")` 처럼 키·콜백을 위치로 넘기면 키워드만 보는 검사를 비켜 간다.
    """
    import inspect

    import streamlit

    function = getattr(streamlit, widget, None)
    if not callable(function):
        return {}
    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return {}
    positional = [
        item.name
        for item in parameters
        if item.kind in (item.POSITIONAL_ONLY, item.POSITIONAL_OR_KEYWORD)
    ]
    wanted = ("key", *_CALLBACK_KEYWORDS)
    return {name: index for index, name in enumerate(positional) if name in wanted}


def _widget_arguments(node: ast.Call, names: _Names) -> list[tuple[str | None, ast.expr]]:
    """(인자 이름, 값) — 키워드 인자와, Streamlit 위젯 서명에서 `key`·콜백 자리에 온 위치 인자."""
    found: list[tuple[str | None, ast.expr]] = [(item.arg, item.value) for item in node.keywords]
    resolved = names.resolve(node.func)
    widget = (
        resolved.rsplit(".", 1)[-1]
        if resolved is not None
        else node.func.attr
        if isinstance(node.func, ast.Attribute)
        else None
    )
    if widget is not None and node.args:
        for name, index in _positional_slots(widget).items():
            if index < len(node.args) and not isinstance(node.args[index], ast.Starred):
                found.append((name, node.args[index]))
    return found


def _check_widget_keywords(node: ast.Call, names: _Names, context: _FileContext) -> None:
    widget = _is_widget_call(names, node)
    for keyword in node.keywords:
        if keyword.arg is not None and keyword.arg in _DEPRECATED_KEYWORDS:
            context.add(
                "M19",
                "error",
                keyword.value,
                f"`{keyword.arg}=` 는 Streamlit 이 곧 지웁니다 — "
                f"{_DEPRECATED_KEYWORDS[keyword.arg]}",
            )
    if not widget:
        return
    for argument, value in _widget_arguments(node, names):
        if argument == "key":
            verdict, shown = _key_verdict(names, value, context.prefix)
            if verdict == "bad":
                context.add(
                    "M08",
                    "error",
                    value,
                    f'key="{_short(shown)}" — {context.prefix} 접두가 없습니다(ctx.key("…"))',
                )
        elif argument in _CALLBACK_KEYWORDS:
            if isinstance(value, ast.Constant) and (
                value.value is None or isinstance(value.value, str)
            ):
                continue
            if names.is_method_call(value, "callback"):
                continue
            context.add(
                "M18",
                "error",
                value,
                f"`{argument}=` 콜백을 `ctx.callback(함수)` 로 감쌉니다 — 감싸지 않은 콜백의 "
                "예외는 "
                "사이드바·탭 줄까지 지웁니다",
            )


def _check_session_call(
    node: ast.Call, resolved: str, names: _Names, context: _FileContext
) -> None:
    if not resolved.startswith(_SESSION_STATE + "."):
        return
    method = resolved[len(_SESSION_STATE) + 1 :]
    if method in ("clear", "popitem", "update"):
        context.add(
            "M08",
            "error",
            node,
            f"`st.session_state.{method}()` 호출은 코어 칸까지 건드립니다 — 자기 키만 하나씩 "
            "다룹니다",
        )
    elif method in ("get", "pop", "setdefault") and node.args:
        verdict, shown = _key_verdict(names, node.args[0], context.prefix)
        if verdict == "bad":
            context.add(
                "M08",
                "error",
                node,
                f'st.session_state.{method}("{_short(shown)}") — {context.prefix} 접두가 없습니다',
            )
        elif verdict == "unknown" and method == "pop":
            context.add(
                "M08",
                "error",
                node,
                "`st.session_state.pop(…)` 의 키를 판정할 수 없습니다 — "
                '`ctx.key("…")` 로 지울 키를 적습니다',
            )


def _check_global_call(node: ast.Call, resolved: str, context: _FileContext) -> None:
    for owner, methods in _GLOBAL_MUTATORS.items():
        if resolved.startswith(owner + ".") and resolved[len(owner) + 1 :] in methods:
            context.add(
                "M11",
                "error",
                node,
                f"`{resolved}()` 호출은 프로세스 전체(모든 사용자·코어)를 바꿉니다 — 지웁니다",
            )


def _check_root_logger(node: ast.Call, names: _Names, context: _FileContext) -> None:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in _ROOT_LOGGER_METHODS:
        return
    target = func.value
    root = names.resolve(target) == "logging.root"
    if isinstance(target, ast.Call) and names.resolve(target.func) == "logging.getLogger":
        argument = target.args[0] if target.args else None
        root = argument is None or (
            isinstance(argument, ast.Constant) and argument.value in (None, "")
        )
    if root:
        context.add(
            "M11",
            "error",
            node,
            f"뿌리 로거의 `{func.attr}` 호출은 코어 로그까지 바꿉니다 — "
            '`logging.getLogger("modules.<id>")` 를 씁니다',
        )


def _tainted(node: ast.AST, tainted_names: set[str], context_names: set[str]) -> bool:
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and (inner.id == "__file__" or inner.id in tainted_names):
            return True
        if (
            isinstance(inner, ast.Attribute)
            and inner.attr == "folder"
            and isinstance(inner.value, ast.Name)
            and inner.value.id in context_names
        ):
            return True
    return False


def _write_taint(tree: ast.Module, names: _Names) -> _WriteTaint:
    contexts = {
        name
        for name, value in names.single.items()
        if isinstance(value, ast.Call) and names.resolve(value.func) == f"{_MODULE_API}.context"
    }
    tainted: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, value in names.single.items():
            # 문맥 이름(`ctx = api.context(__file__)`)은 `__file__` 을 받아도 코드 폴더 경로가
            # 아니다 — `ctx.data_dir` 는 데이터 자리라 쓰기를 권하는 길이고, 코드 폴더는
            # `ctx.folder` 로만 잡는다.
            if name in contexts:
                continue
            if name not in tainted and _tainted(value, tainted, contexts):
                tainted.add(name)
                changed = True
    return _WriteTaint(tainted, contexts)


def _check_file_write(node: ast.Call, names: _Names, context: _FileContext) -> None:
    taint = context.taint
    func = node.func
    target: ast.AST | None = None
    if (
        isinstance(func, ast.Name)
        and func.id == "open"
        or names.resolve(func)
        in (
            "io.open",
            "builtins.open",
        )
    ):
        mode = node.args[1] if len(node.args) > 1 else None
        mode = mode or next((item.value for item in node.keywords if item.arg == "mode"), None)
        mode_text = names.constant(mode) if mode is not None else None
        if mode_text is not None and any(flag in mode_text for flag in "wax+") and node.args:
            target = node.args[0]
    elif isinstance(func, ast.Attribute):
        if func.attr in _WRITE_METHODS:
            target = func.value
        elif func.attr == "open":
            mode = node.args[0] if node.args else None
            mode_text = names.constant(mode) if mode is not None else None
            if mode_text is not None and any(flag in mode_text for flag in "wax+"):
                target = func.value
        elif func.attr in _FRAME_WRITERS:
            target = _first_argument(node, "path_or_buf") or _first_argument(node, "path")
    if target is None:
        return
    if _tainted(target, taint.names, taint.contexts):
        context.add(
            "M13",
            "warning",
            node,
            "`__file__` 기준 경로에 씁니다 — 모듈 코드 폴더에는 실행 중 쓰지 않고 "
            "`ctx.data_dir` 에 씁니다",
        )
        return
    relative = _relative_literal_path(target, names)
    if relative is not None:
        context.add(
            "M13",
            "warning",
            node,
            f"상대 경로 `{relative}` 에 씁니다 — 앱에서는 작업 폴더(저장소 뿌리)에 말없이 생겨 "
            '다른 PC · 배포 서버에 닿지 않습니다 — `ctx.data_dir / "<이름>"` 에 씁니다',
        )


def _relative_literal_path(node: ast.AST, names: _Names, depth: int = 0) -> str | None:
    """경로 식이 상대 경로 글자에서 시작하면 그 글자 — `"x.txt"` · `NAME`(모듈 수준 글자) ·
    `Path("x")` · `Path("out") / "x"`. `ctx.data_dir / …` · 변수 · 절대 경로는 None 이다.

    `data/` 로 시작하는 글자는 M07 이 이미 알리므로 넘긴다. 상대 경로는 작업 폴더 기준이라 앱에서는
    운영 체크아웃 뿌리에 쓴다(시험 러너는 트리 안 쓰기를 실패로 만든다).
    """
    if depth > 4:
        return None
    text = names.constant(node)
    if text is not None:
        posix = text.replace("\\", "/")
        if (
            "://" in text
            or posix.startswith(("/", "~", "data/"))
            or posix == "data"
            or _WINDOWS_ABSOLUTE.match(text) is not None
        ):
            return None
        return text
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _relative_literal_path(node.left, names, depth + 1)
    if isinstance(node, ast.Call) and node.args and names.resolve(node.func) in _PATH_CONSTRUCTORS:
        return _relative_literal_path(node.args[0], names, depth + 1)
    if isinstance(node, ast.Name):
        value = names.single.get(node.id)
        if value is not None:
            return _relative_literal_path(value, names, depth + 1)
    return None


def _check_subscripts_and_targets(tree: ast.Module, names: _Names, context: _FileContext) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            owner = names.resolve(node.value)
            if owner == _SESSION_STATE:
                _check_session_subscript(node, names, context)
            elif owner == _QUERY_PARAMS:
                if isinstance(node.ctx, ast.Del):
                    context.add(
                        "M05",
                        "error",
                        node,
                        "`del st.query_params[…]` 는 주소의 theme 인자까지 지울 수 있습니다",
                    )
                else:
                    verdict, shown = _key_verdict(names, node.slice, context.prefix)
                    if verdict == "bad":
                        context.add(
                            "M08",
                            "error",
                            node,
                            f'st.query_params["{_short(shown)}"] — {context.prefix} 접두가 '
                            "없습니다",
                        )
            elif (
                not context.is_test
                and owner in _GLOBAL_SUBSCRIPTS
                and isinstance(node.ctx, (ast.Store, ast.Del))
            ):
                context.add(
                    "M11",
                    "error",
                    node,
                    f"`{owner}[…]` 를 바꾸면 프로세스 전체(모든 사용자·코어)가 바뀝니다 — 지웁니다",
                )
        elif isinstance(node, ast.Attribute):
            owner = names.resolve(node.value)
            if owner == _SESSION_STATE and node.attr not in _SESSION_METHODS:
                if not node.attr.startswith(context.prefix):
                    context.add(
                        "M08",
                        "error",
                        node,
                        f"st.session_state.{_short(node.attr)} — {context.prefix} 접두가 없습니다",
                    )
            elif not context.is_test and isinstance(node.ctx, (ast.Store, ast.Del)):
                resolved = names.resolve(node)
                if resolved is not None and (
                    resolved in _GLOBAL_TARGETS
                    or resolved.startswith(_GLOBAL_TARGET_PREFIXES)
                    or owner == "builtins"
                ):
                    context.add(
                        "M11",
                        "error",
                        node,
                        f"`{resolved} =` 은 프로세스 전체(모든 사용자·코어)를 바꿉니다 — 지웁니다",
                    )
        elif isinstance(node, ast.Compare):
            if any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops) and any(
                names.resolve(comparator) == _SESSION_STATE for comparator in node.comparators
            ):
                verdict, shown = _key_verdict(names, node.left, context.prefix)
                if verdict == "bad":
                    context.add(
                        "M08",
                        "error",
                        node,
                        f'"{_short(shown)}" in st.session_state — {context.prefix} 접두가 없습니다',
                    )
        elif isinstance(node, (ast.Assign, ast.AugAssign)) and not context.is_test:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and names.resolve(target) == "sys.path":
                    context.add("M11", "error", target, "`sys.path` 를 바꾸지 않습니다")


def _check_session_subscript(node: ast.Subscript, names: _Names, context: _FileContext) -> None:
    verdict, shown = _key_verdict(names, node.slice, context.prefix)
    if verdict == "bad":
        action = "del " if isinstance(node.ctx, ast.Del) else ""
        context.add(
            "M08",
            "error",
            node,
            f'{action}st.session_state["{_short(shown)}"] — {context.prefix} 접두가 없습니다',
        )
    elif verdict == "unknown" and isinstance(node.ctx, ast.Del):
        context.add(
            "M08",
            "error",
            node,
            "`del st.session_state[…]` 의 키를 판정할 수 없습니다(변수·반복) — "
            '`ctx.key("…")` 로 지울 키를 적습니다',
        )


def _check_cache(tree: ast.Module, names: _Names, context: _FileContext) -> None:
    context_names = set(context.taint.contexts)
    if "ctx" in names.module_names or "ctx" in names.aliases:
        context_names.add("ctx")
    decorators = _decorator_calls(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node not in decorators:
            resolved = names.resolve(node.func)
            if resolved in _CACHE_DECORATORS and not context.is_cache_file:
                context.add(
                    "M12",
                    "error",
                    node,
                    "캐시는 `cache.py` 한 파일에만 둡니다(화면 파일은 `__main__` 이라 모듈끼리 "
                    "칸이 겹칩니다)",
                )
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if names.resolve(target) not in _CACHE_DECORATORS:
                continue
            if not context.is_cache_file:
                context.add(
                    "M12",
                    "error",
                    decorator,
                    "캐시는 `cache.py` 한 파일에만 둡니다(화면 파일은 `__main__` 이라 모듈끼리 "
                    "칸이 겹칩니다)",
                )
            limits = [
                item.value
                for item in (decorator.keywords if isinstance(decorator, ast.Call) else [])
                if item.arg in ("max_entries", "ttl")
            ]
            if not any(not (isinstance(v, ast.Constant) and v.value is None) for v in limits):
                context.add(
                    "M12",
                    "error",
                    decorator,
                    "캐시에 `max_entries`·`ttl` 이 없습니다 — 공용 서버 메모리가 넘치면 모든 "
                    "사용자의 앱이 "
                    "함께 내려갑니다",
                )
            _check_cache_body(node, names, context, context_names)


def _decorator_calls(tree: ast.Module) -> set[ast.AST]:
    found: set[ast.AST] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.update(item for item in node.decorator_list if isinstance(item, ast.Call))
    return found


def _local_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    arguments = function.args
    local = {
        argument.arg
        for argument in (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            *((arguments.vararg,) if arguments.vararg else ()),
            *((arguments.kwarg,) if arguments.kwarg else ()),
        )
    }
    for inner in ast.walk(function):
        if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Store):
            local.add(inner.id)
    return local


def _check_cache_body(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    names: _Names,
    context: _FileContext,
    context_names: set[str],
) -> None:
    local = _local_names(function)
    for inner in ast.walk(function):
        if (
            isinstance(inner, ast.Name)
            and isinstance(inner.ctx, ast.Load)
            and inner.id in context_names
            and inner.id not in local
        ):
            context.add(
                "M12",
                "error",
                inner,
                f"`{function.name}` 캐시 함수가 전역 `{inner.id}` 이름을 읽습니다 — 키에 들지 않아 "
                "다른 모듈·"
                "세션 값이 섞입니다. `ctx.data_dir` 를 인자로 받습니다",
            )
        elif isinstance(inner, ast.Call):
            resolved = names.resolve(inner.func)
            if resolved == f"{_MODULE_API}.context":
                context.add(
                    "M12",
                    "error",
                    inner,
                    f"캐시 함수 `{function.name}` 안에서 `api.context(…)` 를 부릅니다 — 문맥 "
                    "값을 인자로 받습니다",
                )
            elif resolved == f"{_MODULE_API}.palette":
                context.add(
                    "M12",
                    "warning",
                    inner,
                    f"캐시 함수 `{function.name}` 안의 `api.palette()` — 한 테마가 모든 "
                    "사용자에게 굳습니다"
                    "(값을 인자로)",
                )


def _check_helper_globals(tree: ast.Module, context: _FileContext) -> None:
    """화면 밖 도움 파일 — `global` 문과 함수 안에서 바꾸는 모듈 수준 list·dict·set(경고)."""
    mutable: set[str] = set()
    for statement in _module_level_statements(tree.body):
        if isinstance(statement, (ast.Assign, ast.AnnAssign)) and statement.value is not None:
            value = statement.value
            is_mutable = isinstance(value, (ast.List, ast.Dict, ast.Set)) or (
                isinstance(value, ast.Call)
                and isinstance(value.func, (ast.Name, ast.Attribute))
                and (value.func.id if isinstance(value.func, ast.Name) else value.func.attr)
                in ("list", "dict", "set", "defaultdict", "OrderedDict", "Counter", "deque")
            )
            if not is_mutable:
                continue
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            mutable.update(target.id for target in targets if isinstance(target, ast.Name))
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            context.add(
                "M11",
                "warning",
                node,
                f"`global {', '.join(node.names)}` — 도움 코드의 전역은 모든 세션·사용자가 함께 "
                "씁니다",
            )
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not mutable:
            continue
        local = _local_names(node)
        for inner in ast.walk(node):
            name: str | None = None
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr in _MUTATING_METHODS
                and isinstance(inner.func.value, ast.Name)
            ):
                name = inner.func.value.id
            elif (
                isinstance(inner, ast.Subscript)
                and isinstance(inner.ctx, (ast.Store, ast.Del))
                and isinstance(inner.value, ast.Name)
            ):
                name = inner.value.id
            if name is not None and name in mutable and name not in local:
                context.add(
                    "M11",
                    "warning",
                    inner,
                    f"`{node.name}` 함수가 모듈 수준 `{name}` 이름을 바꿉니다 — 모든 세션·사용자가 "
                    "함께 씁니다",
                )


def check_source(
    source: str,
    *,
    module_id: str,
    rel: str,
    is_page: bool,
    local_names: frozenset[str],
    environment: PackageEnvironment,
) -> tuple[list[Finding], set[str], list[tuple[int, str]]]:
    """`.py` 하나 — (찾은 것, 제3자 최상위 import 이름, 글자 상수(줄, 값))."""
    parts = rel.split("/")
    context = _FileContext(
        module_id=module_id,
        rel=rel,
        is_page=is_page,
        is_test=parts[0] == TESTS_DIR and len(parts) > 1,
        is_cache_file=rel == CACHE_FILE,
        local_names=local_names,
        environment=environment,
    )
    try:
        tree = ast.parse(source, filename=rel, feature_version=(3, 10))
    except SyntaxError as error:
        context.add(
            "M13",
            "error",
            int(error.lineno or 0),
            "Python 3.10 문법 오류입니다 — 고쳐야 화면이 섭니다",
        )
        return context.findings, context.third_party, context.strings
    except (ValueError, MemoryError, RecursionError) as error:
        # 널 글자(`ValueError`)·지나치게 깊은 식 — 문법 오류가 아니라서 위에서 걸리지 않는다.
        context.add(
            "M13",
            "error",
            0,
            f"파이썬 소스로 읽지 못했습니다({type(error).__name__} — 널 글자·지나치게 깊은 식) — "
            "고쳐야 화면이 섭니다",
        )
        return context.findings, context.third_party, context.strings
    names = _Names(tree)
    context.taint = _write_taint(tree, names)
    _check_imports(tree, context)
    _check_strings(tree, context)
    _check_joined_paths(tree, names, context)
    _check_references(tree, names, context)
    _check_calls(tree, names, context)
    _check_window_escapes(tree, names, context)
    _check_hand_made_context(tree, names, context)
    _check_subscripts_and_targets(tree, names, context)
    _check_cache(tree, names, context)
    if not context.is_test and not is_page:
        _check_helper_globals(tree, context)
    return context.findings, context.third_party, context.strings


# --- 파일(M13)·시험(M14) ----------------------------------------------------------------------


@dataclass(frozen=True)
class GitView:
    """뿌리가 git 작업트리 안일 때 보는 것.

    무시되는(커밋되지 않을) 파일과, git 철자가 디스크 철자와 대소문자만 다른 것.
    """

    ignored: frozenset[str]
    case_mismatches: tuple[tuple[str, str], ...]


def _git(folder: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(folder), *args],
        input=None if stdin is None else stdin.encode("utf-8"),
        capture_output=True,
        check=False,
    )


def inside_git_work_tree(folder: Path) -> bool:
    try:
        result = _git(folder, "rev-parse", "--is-inside-work-tree")
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() == b"true"


def module_files(folder: Path) -> list[str]:
    """모듈 폴더 안 파일(폴더 기준 POSIX 상대 경로) — 캐시 폴더는 뺀다."""
    found: list[str] = []
    for current, directories, files in os.walk(folder):
        directories[:] = sorted(name for name in directories if name not in SKIP_DIRS)
        base = Path(current).relative_to(folder)
        for name in sorted(files):
            found.append((base / name).as_posix())
    return found


def _exists_exactly(folder: Path, rel: str) -> bool:
    current = folder
    for part in rel.split("/"):
        try:
            if part not in os.listdir(current):
                return False
        except OSError:
            return False
        current = current / part
    return True


def git_view(folder: Path, files: Sequence[str]) -> GitView | None:
    """git 작업트리 안이면 무시 파일과 대소문자 철자 어긋남을 본다. 밖(사본)이면 None."""
    if not inside_git_work_tree(folder):
        return None
    listed = _git(folder, "ls-files", "-z", "--", ".")
    tracked = [item for item in listed.stdout.decode("utf-8", "replace").split("\0") if item]
    ignored_run = _git(
        folder, "check-ignore", "--no-index", "-z", "--stdin", stdin="\0".join(files)
    )
    ignored = {
        item for item in ignored_run.stdout.decode("utf-8", "replace").split("\0") if item
    } - set(tracked)
    lowered = {item.lower(): item for item in files}
    mismatches = tuple(
        (path, lowered[path.lower()])
        for path in tracked
        if not _exists_exactly(folder, path) and path.lower() in lowered
    )
    return GitView(ignored=frozenset(ignored), case_mismatches=mismatches)


def _is_text_utf8(path: Path) -> bool:
    try:
        path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return True


def check_files(folder: Path, files: Sequence[str]) -> list[Finding]:
    """파일 꼴(M13 — 이름·종류·크기·인코딩)."""
    findings: list[Finding] = []
    for rel in files:
        path = folder / rel
        name = rel.rsplit("/", 1)[-1]
        lower = name.lower()
        suffix = Path(lower).suffix
        parts = rel.split("/")
        if rel != README_NAME and any(char.isupper() for char in rel):
            findings.append(
                Finding(
                    "M13",
                    "error",
                    rel,
                    0,
                    "이름에 대문자가 있습니다 — Linux CD 는 대소문자를 가립니다(소문자로)",
                )
            )
        if suffix == ".ps1":
            findings.append(Finding("M13", "error", rel, 0, "`.ps1` 은 모듈에 두지 않습니다"))
        if (
            suffix in DATA_FILE_SUFFIXES
            or lower == ".env"
            or lower.startswith(".env.")
            or lower == "secrets.toml"
            or lower.endswith(".sync.json")
        ):
            findings.append(
                Finding(
                    "M13",
                    "error",
                    rel,
                    0,
                    "데이터·비밀 파일입니다 — 모듈 데이터는 `data/modules/<id>/`(git 밖)에 둡니다",
                )
            )
        if suffix in PICKLE_SUFFIXES:
            findings.append(
                Finding(
                    "M13",
                    "error",
                    rel,
                    0,
                    "pickle 파일은 import 처럼 코드를 실행합니다 — 두지 않습니다",
                )
            )
        if suffix in STYLE_SUFFIXES:
            findings.append(
                Finding(
                    "M13",
                    "error",
                    rel,
                    0,
                    "`.css`·`.js`·`.html` 은 전역 꾸밈 길입니다 — 두지 않습니다(M03)",
                )
            )
        if suffix in DATA_LIKE_SUFFIXES:
            if parts[0] == ASSETS_DIR and len(parts) > 1:
                findings.append(
                    Finding(
                        "M13",
                        "warning",
                        rel,
                        0,
                        "assets/ 안의 데이터 꼴 파일 — 1 MB 아래 합성만 둡니다",
                    )
                )
            else:
                findings.append(
                    Finding(
                        "M13",
                        "error",
                        rel,
                        0,
                        "데이터 꼴 파일은 assets/ 안에 합성만 둡니다(실데이터는 "
                        "`data/modules/<id>/`)",
                    )
                )
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if size > LARGE_FILE_BYTES:
            findings.append(Finding("M13", "warning", rel, 0, "5 MB 넘는 파일입니다"))
        elif suffix == ".json" and size > LARGE_JSON_BYTES:
            findings.append(
                Finding(
                    "M13", "warning", rel, 0, "1 MB 넘는 .json — 데이터면 `data/modules/<id>/` 로"
                )
            )
        if suffix in TEXT_SUFFIXES and not _is_text_utf8(path):
            findings.append(
                Finding("M13", "error", rel, 0, "UTF-8 이 아닌 글 파일입니다 — UTF-8 로 저장합니다")
            )
    return findings


def purpose_finding(rel: str, source: str) -> Finding | None:
    first = source.lstrip("﻿").splitlines()[:1]
    if first and first[0].startswith(PURPOSE_PREFIX) and first[0][len(PURPOSE_PREFIX) :].strip():
        return None
    return Finding("M13", "error", rel, 1, "첫 줄에 `# Purpose: <한 문장>` 이 없습니다")


def has_tests(folder: Path) -> bool:
    tests = folder / TESTS_DIR
    return tests.is_dir() and any(path.is_file() for path in tests.glob("test_*.py"))


@dataclass
class StaticResult:
    findings: list[Finding]
    third_party: set[str]


def local_import_names(folder: Path) -> frozenset[str]:
    """같은 폴더 맨이름 import 로 잡힐 이름.

    모듈 폴더 바로 아래 `.py`(확장자 뗀 것)와 폴더 이름이다.
    """
    names: set[str] = set()
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return frozenset()
    for entry in entries:
        if entry.name.startswith((".", "_")) or entry.name in SKIP_DIRS:
            continue
        if entry.is_file() and entry.name.endswith(".py"):
            names.add(entry.name[: -len(".py")])
        elif entry.is_dir() and entry.name != TESTS_DIR:
            names.add(entry.name)
    return frozenset(names)


def check_module_folder(
    folder: Path,
    *,
    module_id: str,
    pages: Iterable[str],
    environment: PackageEnvironment,
    git: GitView | None,
) -> StaticResult:
    """모듈 폴더 하나의 정적 규칙(M02 ~ M14·M18 ~ M21) 전부."""
    files = module_files(folder)
    page_files = frozenset(pages)
    local_names = local_import_names(folder)
    findings = check_files(folder, files)
    third_party: set[str] = set()
    strings: dict[str, list[tuple[int, str]]] = {}
    for rel in files:
        if not rel.endswith(".py"):
            continue
        try:
            source = (folder / rel).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        header = purpose_finding(rel, source)
        if header is not None:
            findings.append(header)
        found, imported, constants = check_source(
            source.lstrip("﻿"),
            module_id=module_id,
            rel=rel,
            is_page=rel in page_files,
            local_names=local_names,
            environment=environment,
        )
        findings.extend(found)
        third_party.update(imported)
        strings[rel] = constants
    if not has_tests(folder):
        findings.append(
            Finding(
                "M14",
                "error",
                TESTS_DIR,
                0,
                "tests/test_*.py 가 없습니다 — 진입 스모크 시험을 둡니다",
            )
        )
    if git is not None:
        findings.extend(_git_findings(folder, git, strings))
    return StaticResult(findings=_unique(findings), third_party=third_party)


def _git_findings(
    folder: Path, git: GitView, strings: Mapping[str, Sequence[tuple[int, str]]]
) -> list[Finding]:
    findings = [
        Finding(
            "M13",
            "error",
            disk,
            0,
            f"git 에는 `{tracked}` 철자로 들어 있습니다(대소문자만 다름) — `git mv` 로 철자를 "
            "맞춥니다(Linux CD 에서 파일 없음)",
        )
        for tracked, disk in git.case_mismatches
    ]
    try:
        manifest_text = (folder / "module.json").read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        manifest_text = ""
    for rel in sorted(git.ignored):
        base = rel.rsplit("/", 1)[-1]
        findings.append(
            Finding(
                "M13",
                "warning",
                rel,
                0,
                "git 이 무시하는 파일입니다 — 커밋되지 않아 운영·CD 에 없습니다",
            )
        )
        for source, constants in strings.items():
            for line, text in constants:
                if base in text:
                    findings.append(
                        Finding(
                            "M13",
                            "error",
                            source,
                            line,
                            f"git 이 무시하는 `{_short(base)}` 파일을 가리킵니다 — 운영·CD 에 "
                            "없습니다",
                        )
                    )
        if base in manifest_text:
            findings.append(
                Finding(
                    "M13",
                    "error",
                    "module.json",
                    0,
                    f"git 이 무시하는 `{_short(base)}` 파일을 가리킵니다 — 운영·CD 에 없습니다",
                )
            )
    return findings


def _unique(findings: Iterable[Finding]) -> list[Finding]:
    return list(dict.fromkeys(findings))
