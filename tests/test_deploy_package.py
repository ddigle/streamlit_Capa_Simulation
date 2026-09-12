# Purpose: 사내 배포 세트가 무엇을 담고 무엇을 빼는지 고정한다.

import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_deploy_package import (  # noqa: E402
    EXCLUDED_FILES,
    build_archive,
    deploy_set,
    forbidden_entries,
)


def test_the_dependency_declaration_and_its_lock_never_ship() -> None:
    """사내 PC 의 `pyproject.toml` 에는 삼성 Artifactory 인덱스가 손으로 들어가 있고, 그
    선언에서 나온 `uv.lock` 에는 `bigdataquery` 가 박혀 있다.

    개발 PC 쪽에는 둘 다 없다 — 적어 두면 인덱스에 닿지 못하는 곳에서 `uv lock` 이 깨지기
    때문에 일부러 뺐다. 그러니 덮어쓰면 사내 설정만 사라진다. **둘은 짝이라 함께 빼야
    한다** — 하나만 보내면 선언과 잠금이 어긋나 `uv sync` 가 락을 다시 만들고, 그 순간
    사내 전용 패키지가 환경에서 빠진다. 이 규칙이 주석으로만 남으면 다음 배포에서 조용히
    다시 들어간다.
    """
    tracked = ["app.py", "pyproject.toml", "uv.lock", "src/capa_simulation/settings.py"]

    shipped = deploy_set(tracked, extras=())

    assert shipped == ["app.py", "src/capa_simulation/settings.py"]


def test_the_deploy_set_keeps_tests_and_scripts() -> None:
    """사내 PC 에서 단독으로 돌려 보고 검증할 수 있어야 한다."""
    tracked = ["app.py", "tests/test_home_page.py", "scripts/benchmark_home.py"]

    assert deploy_set(tracked, extras=()) == sorted(tracked)


def test_untracked_operational_input_is_added() -> None:
    """공용 표시순서 부트스트랩 입력은 추적되지 않지만 운영에 필요하다."""
    assert "data/input/RQ_DISPLAY_ORDER.csv" in deploy_set(["app.py"])


def test_the_set_is_deduplicated_and_ordered() -> None:
    extras = ("data/input/RQ_DISPLAY_ORDER.csv",)
    tracked = ["b.py", "a.py", "data/input/RQ_DISPLAY_ORDER.csv"]

    assert deploy_set(tracked, extras=extras) == [
        "a.py",
        "b.py",
        "data/input/RQ_DISPLAY_ORDER.csv",
    ]


@pytest.mark.parametrize(
    "path",
    [
        "data/input/Core_Data.xlsb",
        "data/capa_simulation.duckdb",
        ".env",
        ".streamlit/secrets.toml",
        "data/output/result.csv",
        "data/temp/scratch.csv",
    ],
)
def test_forbidden_files_are_caught(path: str) -> None:
    """한 번 새면 되돌릴 수 없는 종류라 보내기 전에 다시 본다."""
    assert forbidden_entries([path]) == [path]


def test_ordinary_files_are_not_flagged() -> None:
    paths = ["app.py", "README.md", "data/input/RQ_DISPLAY_ORDER.csv"]

    assert forbidden_entries(paths) == []


def test_the_real_repository_ships_nothing_forbidden() -> None:
    """규칙이 아니라 지금 저장소의 실제 목록으로 확인한다."""
    from build_deploy_package import tracked_files

    assert forbidden_entries(deploy_set(tracked_files(PROJECT_ROOT))) == []


def test_a_missing_file_stops_the_build(tmp_path: Path) -> None:
    """빠진 파일을 조용히 건너뛰면 반쪽짜리 배포본이 나간다."""
    (tmp_path / "app.py").write_text("", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="배포 세트에 없는 파일"):
        build_archive(tmp_path, ["app.py", "gone.py"], tmp_path / "out" / "x.zip")


def test_the_archive_holds_exactly_the_set(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print()", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("", encoding="utf-8")
    destination = tmp_path / "out" / "202609121200.zip"

    count = build_archive(tmp_path, ["app.py", "pkg/mod.py"], destination)

    assert count == 2
    with zipfile.ZipFile(destination) as archive:
        assert sorted(archive.namelist()) == ["app.py", "pkg/mod.py"]


def test_the_exclusion_list_is_explicit() -> None:
    """제외 목록이 늘면 배포본에서 사라지는 파일이 는다. 눈에 띄게 고정한다."""
    assert EXCLUDED_FILES == frozenset({"pyproject.toml", "uv.lock"})


def test_directory_placeholders_still_ship() -> None:
    """`data/output`·`data/temp` 는 비어 있어야 하지만 폴더 자체는 있어야 한다."""
    assert forbidden_entries(["data/output/.gitkeep", "data/temp/.gitkeep"]) == []
