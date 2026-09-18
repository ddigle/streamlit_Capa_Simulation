# Purpose: 사내 배포 세트가 무엇을 담고 무엇을 빼는지 고정한다.

import json
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


def test_the_dependency_declaration_and_its_lock_now_ship() -> None:
    """선언과 잠금은 이제 **양쪽이 같아서** 함께 보낸다.

    예전에는 사내 `pyproject.toml` 에만 Artifactory 인덱스가 손으로 들어가 있어 두 파일을
    뺐고, 그 대가로 「의존성을 바꾸면 ZIP 만으로는 사내에 반영되지 않는다」는 예외를 지고
    있었다. 사내 전용 패키지를 `requirements-company.txt` 로 옮긴 뒤 그 예외가 없어졌다.

    되돌아가지 않도록 여기서 고정한다 — 다시 빼기 시작하면 사내 파일을 손으로 맞추는
    일이 함께 돌아온다.
    """
    tracked = ["app.py", "pyproject.toml", "uv.lock", "src/capa_simulation/settings.py"]

    shipped = deploy_set(tracked, extras=())

    assert shipped == sorted(tracked)
    assert EXCLUDED_FILES == frozenset()


def test_the_company_only_package_stays_out_of_the_declaration() -> None:
    """`bigdataquery` 가 `pyproject.toml` 로 돌아오면 개발 PC 의 `uv lock` 이 죽는다.

    uv 락은 universal 이라 extra·group 을 가리지 않고 전부 해석한다. `--extra` 를 고르지
    않아도 사내 인덱스를 찾으러 가고, 닿지 못하는 곳에서는 그 자리에서 실패한다
    (실측: `dns error`). 그래서 선언이 아니라 별도 파일에 둔다.
    """
    declaration = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requirements = PROJECT_ROOT / "requirements-company.txt"

    assert "bigdataquery==" not in declaration, (
        "사내 전용 패키지가 pyproject.toml 로 돌아왔습니다 — 개발 PC 의 `uv lock` 이 "
        "사내 인덱스를 찾다가 실패합니다. `requirements-company.txt` 에 두세요."
    )
    assert "artifactory" not in declaration.lower()
    assert requirements.is_file()
    assert "bigdataquery==" in requirements.read_text(encoding="utf-8")


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


def test_the_exclusion_list_is_empty() -> None:
    """제외 목록이 늘면 배포본에서 사라지는 파일이 늘고, 그만큼 사내 파일을 손으로 맞춰야
    한다. 지금은 비어 있다 — 늘어날 때 눈에 띄도록 고정한다."""
    assert EXCLUDED_FILES == frozenset()


def test_directory_placeholders_still_ship() -> None:
    """`data/output`·`data/temp` 는 비어 있어야 하지만 폴더 자체는 있어야 한다."""
    assert forbidden_entries(["data/output/.gitkeep", "data/temp/.gitkeep"]) == []


def test_the_manifest_never_hashes_itself(tmp_path: Path) -> None:
    """송장은 자기 자신을 해시할 수 없다. 세트에 같은 이름이 있으면 그 자리에서 멈춘다."""
    from build_deploy_package import MANIFEST_NAME, build_archive

    (tmp_path / MANIFEST_NAME).write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="송장과 이름이"):
        build_archive(tmp_path, [MANIFEST_NAME], tmp_path / "out.zip")


def test_internal_only_paths_never_ship() -> None:
    """사외에 `review/` 가 생기면 ZIP 에 실려 사내 리뷰 기록을 덮는다."""
    from build_deploy_package import internal_only_entries

    flagged = internal_only_entries(["app.py", "review/2026.md", ".deploy/applied.json"])

    assert flagged == [".deploy/applied.json", "review/2026.md"]


def test_the_archive_carries_the_manifest_beside_the_files(tmp_path: Path) -> None:
    from build_deploy_package import MANIFEST_NAME, build_archive

    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    destination = tmp_path / "out" / "deploy.zip"

    build_archive(tmp_path, ["app.py"], destination, manifest={"manifest_version": 1})

    with zipfile.ZipFile(destination) as archive:
        assert sorted(archive.namelist()) == ["DEPLOY_MANIFEST.json", "app.py"]
        assert json.loads(archive.read(MANIFEST_NAME))["manifest_version"] == 1
