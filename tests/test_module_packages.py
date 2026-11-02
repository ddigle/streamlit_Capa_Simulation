# Purpose: 코어가 import 하는 제3자 패키지와 모듈 요청 목록이 코어 직접 의존·고정 요구인지 고정한다.

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = PROJECT_ROOT / "config" / "module_packages.json"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import module_check_rules as rules  # noqa: E402


def _project_dependencies(pyproject: str) -> set[str]:
    """`[project]` 의 `dependencies` 이름들 — Python 3.10 에는 tomllib 이 없어 글로 읽는다."""
    project = pyproject.split("[project]", 1)[1].split("\n[", 1)[0]
    block = project.split("dependencies = [", 1)[1].split("\n]", 1)[0]
    names = set()
    for line in block.splitlines():
        text = line.split("#", 1)[0].strip()
        matched = re.match(r'"([A-Za-z0-9][A-Za-z0-9._-]*)', text)
        if matched is not None:
            names.add(rules.normalize_name(matched.group(1)))
    return names


def _listed() -> dict[str, object]:
    data = json.loads(PACKAGES.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_the_list_has_only_its_two_fields_and_normalized_names() -> None:
    data = _listed()
    assert set(data) == {"_설명", "packages"}
    packages = data["packages"]
    assert isinstance(packages, list)
    assert all(isinstance(name, str) for name in packages)
    assert packages == sorted(set(packages)), "이름은 겹치지 않게 가나다 차례로 적는다"
    assert all(name == rules.normalize_name(name) for name in packages), "PEP 503 정규화 꼴로"


def test_every_listed_package_is_a_direct_core_dependency_pinned_for_the_image() -> None:
    dependencies = _project_dependencies((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    pinned = rules.parse_requirements((PROJECT_ROOT / "requirements.txt").read_text("utf-8"))
    packages = _listed()["packages"]
    assert isinstance(packages, list)

    missing_direct = [name for name in packages if name not in dependencies]
    missing_pinned = [name for name in packages if name not in pinned or not pinned[name].direct]
    assert not missing_direct, (
        f"pyproject.toml [project].dependencies 에 없습니다: {missing_direct}"
    )
    assert not missing_pinned, (
        f"requirements.txt 에 직접 의존으로 고정되지 않았습니다: {missing_pinned}"
    )


def test_the_dependency_reader_sees_the_core_declaration() -> None:
    dependencies = _project_dependencies((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    core = {"pandas", "numpy", "streamlit", "duckdb", "plotly", "altair", "pydantic"}
    assert core <= dependencies
    assert "ruff" not in dependencies, "개발 의존 묶음은 읽지 않는다"


def _core_import_tops() -> set[str]:
    """앱이 실행하는 코어 코드(`app.py`·`app_pages`·`src`)의 절대 import 최상위 이름."""
    files = [
        PROJECT_ROOT / "app.py",
        *sorted((PROJECT_ROOT / "app_pages").rglob("*.py")),
        *sorted((PROJECT_ROOT / "src").rglob("*.py")),
    ]
    tops: set[str] = set()
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                tops.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                tops.add(node.module.split(".")[0])
    return {top for top in tops if top not in sys.stdlib_module_names and top != "capa_simulation"}


def test_every_third_party_package_the_core_imports_is_a_direct_dependency() -> None:
    """코어가 import 하는 제3자 패키지는 다른 패키지가 끌어온 전이 의존에 기대지 않는다 — 끌어온
    쪽이 의존을 바꾸면 사내 이미지에서 말없이 빠진다. 모듈 점검(M09)도 같은 직접 의존 표를
    본다."""
    dependencies = _project_dependencies((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    pinned = rules.parse_requirements((PROJECT_ROOT / "requirements.txt").read_text("utf-8"))
    distributions = rules.installed_distributions()
    tops = _core_import_tops()

    assert {"numpy", "pandas", "streamlit"} <= tops
    resolved = {
        top: [rules.normalize_name(name) for name in distributions.get(top, [])] for top in tops
    }
    assert all(resolved.values()), [top for top, names in resolved.items() if not names]
    not_direct = sorted(
        top for top, names in resolved.items() if not any(name in dependencies for name in names)
    )
    not_pinned = sorted(
        top
        for top, names in resolved.items()
        if not any(name in pinned and pinned[name].direct for name in names)
    )
    assert not not_direct, f"pyproject.toml [project].dependencies 에 없습니다: {not_direct}"
    assert not not_pinned, f"requirements.txt 에 직접 의존으로 고정되지 않았습니다: {not_pinned}"


def test_check_module_reads_the_same_list() -> None:
    packages = _listed()["packages"]
    assert isinstance(packages, list)
    assert rules.read_module_packages(PACKAGES) == frozenset(packages)
    assert rules.load_environment(PROJECT_ROOT).module_packages == frozenset(packages)
