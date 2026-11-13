# Purpose: 시험 · 스크립트가 창의 프록시를 따르는 맨 urlopen · urlretrieve 로 요청하는지 훑는다.

"""기본 요청기(`urllib.request.urlopen` · `urlretrieve`)는 창의 `HTTP(S)_PROXY` 를 따른다.

사내 PC 창에는 프록시가 있고 `NO_PROXY` 에 `127.0.0.1` 이 없을 수 있어, 시험이 띄운 루프백
서버로 가는 맨 요청이 프록시의 403 을 받았다(리뷰 202611111500 발견 2). 시험 · 스크립트의 요청은
모두 루프백이거나 일부러 곧장 가는 길이라 `build_opener(ProxyHandler({}))` 로 짓는다
(`tests/test_s3_mock_store.py` · `scripts/check_deploy_screens.py` · `scripts/container_start.py`).
앱 코드(`src/` · `app_pages/`)는 보지 않는다 — 바깥 주소로 가는 앱 요청은 사내 프록시를 따라야 할 수
있다(지금은 맨 요청이 없다).
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCANNED = ("scripts", "tests")
BARE = frozenset({"urlopen", "urlretrieve"})


def bare_requests(source: str) -> list[int]:
    """`source` 에서 기본 요청기(`urllib.request.urlopen` · `urlretrieve`)를 가져오거나 부르는
    줄."""
    with warnings.catch_warnings():
        # 훑는 파일 글자의 경고(잘못된 이스케이프 등)는 이 그물의 일이 아니다.
        warnings.simplefilter("ignore")
        tree = ast.parse(source)
    modules = {"urllib.request"}
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(
                alias.asname
                for alias in node.names
                if alias.name == "urllib.request" and alias.asname
            )
        elif isinstance(node, ast.ImportFrom) and node.module == "urllib":
            modules.update(
                alias.asname or alias.name for alias in node.names if alias.name == "request"
            )
        elif isinstance(node, ast.ImportFrom) and node.module == "urllib.request":
            lines.update(node.lineno for alias in node.names if alias.name in BARE)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in BARE
            and ast.unparse(node.value) in modules
        ):
            lines.add(node.lineno)
    return sorted(lines)


def _scanned_files() -> list[Path]:
    return sorted(path for folder in SCANNED for path in (PROJECT_ROOT / folder).rglob("*.py"))


def test_no_test_or_script_sends_through_the_default_opener() -> None:
    found = [
        f"{path.relative_to(PROJECT_ROOT).as_posix()}:{line}"
        for path in _scanned_files()
        for line in bare_requests(path.read_text(encoding="utf-8"))
    ]

    assert not found, "프록시 없는 요청기(ProxyHandler({}))로 짓는다: " + ", ".join(found)


def test_the_scan_reaches_the_known_direct_openers() -> None:
    """훑는 자리가 비어 그물이 아무것도 안 보는 꼴을 막는다 — 곧장 가는 요청기를 지은 파일이
    든다."""
    names = {path.relative_to(PROJECT_ROOT).as_posix() for path in _scanned_files()}

    assert {
        "tests/test_s3_mock_store.py",
        "scripts/check_deploy_screens.py",
        "scripts/container_start.py",
    } <= names


@pytest.mark.parametrize(
    "source",
    [
        "import urllib.request\nurllib.request.urlopen('http://127.0.0.1:9000/')",
        "import urllib.request as web\nweb.urlopen('http://127.0.0.1:9000/')",
        "from urllib import request\nrequest.urlretrieve('http://127.0.0.1:9000/', 'x')",
        "from urllib import request as web\nhandler = web.urlopen",
        "from urllib.request import urlopen\nurlopen('http://127.0.0.1:9000/')",
        "from urllib.request import Request, urlretrieve as fetch\nfetch('http://x', 'y')",
        "def probe():\n    import urllib.request\n    return urllib.request.urlopen('http://x')",
    ],
    ids=["dotted", "module-alias", "from-urllib", "attribute-only", "name", "name-alias", "local"],
)
def test_the_net_catches_each_spelling(source: str) -> None:
    assert bare_requests(source)


@pytest.mark.parametrize(
    "source",
    [
        "import urllib.request\n"
        "direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))\n"
        "direct.open('http://127.0.0.1:9000/')",
        "import http.client\nhttp.client.HTTPConnection('127.0.0.1', 9000).request('GET', '/')",
        "text = 'urllib.request.urlopen(…) 은 쓰지 않는다'",
        "class Pool:\n    def urlopen(self):\n        return None\n\nPool().urlopen()",
    ],
    ids=["direct-opener", "http-client", "in-a-string", "other-urlopen"],
)
def test_the_net_leaves_direct_requests_alone(source: str) -> None:
    assert bare_requests(source) == []
