# Purpose: 텍스트 파일 입출력 · 자식 프로세스 텍스트 부름이 인코딩을 적었는지 AST 로 훑는다.

"""인코딩을 적지 않은 텍스트 입출력은 그 PC 의 로캘 인코딩으로 읽고 쓴다.

사외 Linux 는 UTF-8 이지만 사내 Windows 는 cp949, GitHub Windows 러너는 cp1252 라 UTF-8 로
저장한 한글 문서를 `read_text()` 로 읽으면 Windows 에서만 `UnicodeDecodeError` 가 난다. 그래서
텍스트 입출력은 인코딩을 늘 적는다(AGENTS 2장 ⑪).

- 저장소 · 사용자 파일은 `encoding="utf-8"`.
- 자식 프로세스의 텍스트 출력은 자식이 쓰는 인코딩으로 읽는다. 파이썬 자식은 부르는 쪽이
  환경에 `PYTHONIOENCODING=utf-8` 을 주고 `encoding="utf-8"` 로 읽는다. 환경을 일부러 좁히거나
  물려받기를 보는 시험은 환경을 그대로 두고 `encoding="utf-8", errors="replace"` 로 읽는다.
  git 은 UTF-8 로 쓴다. 로캘로 쓰는 자식(aws)은 `encoding="locale"` 이다.

ruff `PLW1514` 는 preview 규칙이고 `(폴더 / 이름).read_text()` 처럼 받는 쪽 꼴을 모르는 부름과
자식 프로세스(`text=True`)를 보지 못해 이 그물이 대신한다. 사내 `modules/` 와 `review/` 는 훑지
않는다.
"""

from __future__ import annotations

import ast
import functools
import warnings
from dataclasses import dataclass
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCANNED = ("app.py", "capa_server.py", "app_pages", "src", "scripts", "tests")

# 일부러 인코딩을 적지 않은 자리 — (파일, 부름 글) → 까닭. 자리가 사라지면 이 표에서도 지운다.
ALLOWED: dict[tuple[str, str], str] = {
    ("src/capa_simulation/sidebar_status.py", "registered.open()"): (
        "패널 칸을 여는 `_DeferredPanel.open` 이다 — 파일을 여는 부름이 아니다"
    ),
}


@dataclass(frozen=True)
class TextOpener:
    """모드 · 인코딩 인자 자리. `mode_position` 이 None 이면 늘 텍스트다."""

    mode_position: int | None
    default_mode: str
    encoding_position: int | None
    # 압축 모듈의 `open` 은 모드에 `t` 가 있어야 텍스트다(기본은 바이트).
    needs_t: bool = False


OPENERS: dict[str, TextOpener] = {
    "builtins.open": TextOpener(1, "r", 3),
    "io.open": TextOpener(1, "r", 3),
    "codecs.open": TextOpener(1, "r", 2),
    "os.fdopen": TextOpener(1, "r", 3),
    "gzip.open": TextOpener(1, "rb", 3, needs_t=True),
    "bz2.open": TextOpener(1, "rb", 3, needs_t=True),
    "lzma.open": TextOpener(1, "rb", None, needs_t=True),
    "tempfile.NamedTemporaryFile": TextOpener(0, "w+b", 2),
    "tempfile.TemporaryFile": TextOpener(0, "w+b", 2),
    "tempfile.SpooledTemporaryFile": TextOpener(1, "w+b", 3),
    "io.TextIOWrapper": TextOpener(None, "", 1),
    "logging.FileHandler": TextOpener(None, "", 2),
    "logging.handlers.RotatingFileHandler": TextOpener(None, "", 4),
    "logging.handlers.TimedRotatingFileHandler": TextOpener(None, "", 4),
    "logging.handlers.WatchedFileHandler": TextOpener(None, "", 2),
}
# 인코딩을 받지 않고 늘 로캘로 푸는 부름.
ALWAYS_LOCALE = frozenset({"os.popen", "subprocess.getoutput", "subprocess.getstatusoutput"})
SUBPROCESS_CALLS = frozenset(
    {
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
    }
)
MODE_LETTERS = frozenset("rwaxbt+")


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for item in call.keywords:
        if item.arg == name:
            return item.value
    return None


def _is_none(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _has_encoding(call: ast.Call, position: int | None) -> bool:
    """`encoding=` 이 None 아닌 값으로 있거나 그 자리 위치 인자가 있다."""
    value = _keyword(call, "encoding")
    if value is not None:
        return not _is_none(value)
    return position is not None and len(call.args) > position


def _argument(call: ast.Call, position: int, name: str) -> ast.expr | None:
    if len(call.args) > position:
        return call.args[position]
    return _keyword(call, name)


def _constant_text(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _opens_text(call: ast.Call, opener: TextOpener) -> bool:
    """텍스트 모드거나 모드를 모른다(모르면 잡는다 — 인코딩을 적으면 풀린다)."""
    if opener.mode_position is None:
        return True
    node = _argument(call, opener.mode_position, "mode")
    mode = opener.default_mode if node is None else _constant_text(node)
    if mode is None:
        return True
    if opener.needs_t:
        return "t" in mode
    return "b" not in mode


def _subprocess_text(call: ast.Call) -> bool:
    """`text` · `universal_newlines` 가 거짓이 아니거나 `errors` 를 주면 텍스트 모드다."""
    for name in ("text", "universal_newlines"):
        value = _keyword(call, name)
        if value is not None and not (
            isinstance(value, ast.Constant) and value.value in (False, None)
        ):
            return True
    errors = _keyword(call, "errors")
    return errors is not None and not _is_none(errors)


class _Names:
    """한 파일의 import 이름 — 지역 이름 → 모듈 · 함수 전체 이름."""

    def __init__(self, tree: ast.AST) -> None:
        self.bound: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        self.bound[alias.asname] = alias.name
                    else:
                        head = alias.name.split(".")[0]
                        self.bound[head] = head
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                for alias in node.names:
                    self.bound[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    def qualified(self, func: ast.expr) -> str | None:
        """부름 대상의 전체 이름. 뿌리가 import 이름이 아닌 객체의 메서드면 None."""
        parts: list[str] = []
        node = func
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        root = self.bound.get(node.id)
        if root is None:
            if parts or node.id != "open":
                return None
            root = "builtins.open"
        return ".".join([root, *reversed(parts)])


def _method_problem(call: ast.Call, name: str) -> bool:
    """객체 메서드 — `Path` 꼴의 `read_text` · `write_text` · `open`."""
    if name == "read_text":
        return not _has_encoding(call, 0)
    if name == "write_text":
        return not _has_encoding(call, 1)
    if name != "open" or _has_encoding(call, 2):
        return False
    if call.args:
        mode = _constant_text(call.args[0])
        # 첫 인자가 모드 글이 아니면 다른 `open`(묶음 파일의 멤버 이름 등)이다.
        if mode is None or not mode or not set(mode) <= MODE_LETTERS:
            return False
        return "b" not in mode
    node = _keyword(call, "mode")
    mode = "r" if node is None else _constant_text(node)
    return mode is None or "b" not in mode


def unspecified_encodings(source: str) -> list[tuple[int, str]]:
    """`source` 에서 인코딩을 적지 않은 텍스트 입출력 부름 — (줄, 부름 글)."""
    with warnings.catch_warnings():
        # 훑는 파일 글자의 경고(잘못된 이스케이프 등)는 이 그물의 일이 아니다.
        warnings.simplefilter("ignore")
        tree = ast.parse(source)
    names = _Names(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if any(isinstance(item, ast.Starred) for item in node.args) or any(
            item.arg is None for item in node.keywords
        ):
            continue  # 펼친 인자는 무엇이 들었는지 모른다
        target = names.qualified(node.func)
        if target in ALWAYS_LOCALE:
            problem = True
        elif target in SUBPROCESS_CALLS:
            problem = _subprocess_text(node) and not _has_encoding(node, None)
        elif target in OPENERS:
            opener = OPENERS[target]
            problem = _opens_text(node, opener) and not _has_encoding(
                node, opener.encoding_position
            )
        else:
            # 객체 메서드거나 import 한 모듈의 값(`settings.CONFIG_PATH`)에 붙은 메서드다.
            problem = isinstance(node.func, ast.Attribute) and _method_problem(node, node.func.attr)
        if problem:
            found.append((node.lineno, ast.unparse(node)))
    return sorted(found)


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for name in SCANNED:
        place = PROJECT_ROOT / name
        files.extend([place] if place.is_file() else sorted(place.rglob("*.py")))
    return files


@functools.cache
def _found_in_repository() -> dict[tuple[str, str], list[int]]:
    """훑은 결과 — 저장소 전체를 한 번만 읽는다(두 시험이 함께 쓴다, 고쳐 쓰지 않는다)."""
    found: dict[tuple[str, str], list[int]] = {}
    for path in _scanned_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for line, call in unspecified_encodings(path.read_text(encoding="utf-8")):
            found.setdefault((relative, call), []).append(line)
    return found


def test_every_text_read_and_write_names_its_encoding() -> None:
    found = _found_in_repository()
    unexpected = [
        f"{relative}:{line}: {call}"
        for (relative, call), lines in sorted(found.items())
        if (relative, call) not in ALLOWED
        for line in lines
    ]

    assert not unexpected, (
        '인코딩을 적지 않은 텍스트 입출력입니다 — 파일은 encoding="utf-8", 자식 프로세스는 자식이 '
        "쓰는 인코딩을 적습니다(AGENTS 2장 ⑪):\n" + "\n".join(unexpected)
    )


def test_every_allowed_site_still_exists_and_says_why() -> None:
    found = _found_in_repository()

    stale = [f"{relative}: {call}" for relative, call in ALLOWED if (relative, call) not in found]
    assert not stale, "사라진 자리입니다 — ALLOWED 에서 지웁니다:\n" + "\n".join(stale)
    assert all(reason.strip() for reason in ALLOWED.values())


def test_the_scan_reaches_every_layer() -> None:
    """훑는 자리가 비어 그물이 아무것도 안 보는 꼴을 막는다."""
    names = {path.relative_to(PROJECT_ROOT).as_posix() for path in _scanned_files()}

    assert {
        "app.py",
        "capa_server.py",
        "app_pages/home.py",
        "src/capa_simulation/io/object_storage.py",
        "scripts/build_deploy_package.py",
        "tests/test_grade_name_net.py",
        "tests/test_explicit_text_encoding.py",
    } <= names
    assert not any(name.startswith(("modules/", "review/")) for name in names)


@pytest.mark.parametrize(
    "source",
    [
        "open('a')",
        "open('a', 'w')",
        "open(path, mode='a+')",
        "open(path, mode)",
        "open('a', encoding=None)",
        "from pathlib import Path\nPath('a').read_text()",
        "(folder / 'name').read_text()",
        "from capa_simulation import settings\nsettings.CONFIG_PATH.read_text()",
        "import json\njson.loads(Path(name).read_text())",
        "path.write_text('x')",
        "path.open()",
        "path.open('w')",
        "path.open(mode='r', newline='')",
        "import io\nio.open('a')",
        "import io\nio.TextIOWrapper(buffer)",
        "import os\nos.fdopen(fd, 'w')",
        "import os\nos.popen('ls').read()",
        "import codecs\ncodecs.open('a')",
        "import gzip\ngzip.open('a.gz', 'rt')",
        "import tempfile\ntempfile.NamedTemporaryFile('w')",
        "from tempfile import NamedTemporaryFile\nNamedTemporaryFile(mode='w+')",
        "import logging\nlogging.FileHandler('a.log')",
        "import logging.handlers\nlogging.handlers.RotatingFileHandler('a.log')",
        "import subprocess\nsubprocess.run(['a'], capture_output=True, text=True)",
        "import subprocess\nsubprocess.run(['a'], text=True, encoding=None)",
        "import subprocess as sp\nsp.check_output(['a'], universal_newlines=True)",
        "from subprocess import run\nrun(['a'], text=flag)",
        "import subprocess\nsubprocess.run(['a'], errors='replace')",
        "import subprocess\nsubprocess.Popen(['a'], stdout=subprocess.PIPE, text=True)",
        "import subprocess\nsubprocess.getoutput('a')",
        "def read(path):\n    with open(path) as handle:\n        return handle.read()",
    ],
)
def test_the_net_catches_each_spelling(source: str) -> None:
    assert unspecified_encodings(source)


@pytest.mark.parametrize(
    "source",
    [
        "open('a', encoding='utf-8')",
        "open('a', 'rb')",
        "open('a', mode='wb')",
        "open('a', 'r', -1, 'utf-8')",
        "path.read_text(encoding='utf-8')",
        "path.read_text('utf-8')",
        "path.read_bytes()",
        "path.write_text('x', encoding='utf-8')",
        "path.write_text('x', 'utf-8')",
        "path.open('rb')",
        "path.open(encoding='utf-8')",
        "path.open('w', -1, 'utf-8')",
        "archive.open('member.txt')",
        "archive.open(name)",
        "import io\nio.TextIOWrapper(buffer, encoding='utf-8')",
        "import os\nos.fdopen(fd, 'wb')",
        "import os\nos.open(path, os.O_RDONLY)",
        "import gzip\ngzip.open('a.gz')",
        "import tempfile\ntempfile.NamedTemporaryFile()",
        "import tempfile\ntempfile.NamedTemporaryFile('w', encoding='utf-8')",
        "import webbrowser\nwebbrowser.open('http://127.0.0.1')",
        "import tarfile\ntarfile.open('a.tar')",
        "from capa_simulation import settings\nsettings.CONFIG_PATH.read_text(encoding='utf-8')",
        "import importlib.resources\nimportlib.resources.read_text('pkg', 'a.txt')",
        "import subprocess\nsubprocess.run(['a'], capture_output=True)",
        "import subprocess\nsubprocess.run(['a'], text=False)",
        "import subprocess\nsubprocess.run(['a'], text=True, encoding='utf-8')",
        "import subprocess\nsubprocess.run(['a'], text=True, encoding='locale', errors='replace')",
        "import subprocess\nsubprocess.check_output(['a']).decode('utf-8')",
        "open(*arguments)",
        "open(path, **options)",
        "import subprocess\nsubprocess.run(['a'], **options)",
        "text = 'open(\"a\")'",
        "class Panel:\n    def show(self):\n        return self.slot.open(index)",
    ],
)
def test_the_net_leaves_named_encodings_and_bytes_alone(source: str) -> None:
    assert unspecified_encodings(source) == []
