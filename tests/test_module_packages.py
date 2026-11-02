# Purpose: 사내 모듈이 사외 요청으로 받은 패키지 목록이 코어 직접 의존·고정 요구에 있는지 고정한다.

from __future__ import annotations

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
    assert {"pandas", "streamlit", "duckdb", "plotly", "altair", "pydantic"} <= dependencies
    assert "ruff" not in dependencies, "개발 의존 묶음은 읽지 않는다"


def test_check_module_reads_the_same_list() -> None:
    packages = _listed()["packages"]
    assert isinstance(packages, list)
    assert rules.read_module_packages(PACKAGES) == frozenset(packages)
    assert rules.load_environment(PROJECT_ROOT).module_packages == frozenset(packages)
