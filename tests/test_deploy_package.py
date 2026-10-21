# Purpose: 사내 배포 세트가 무엇을 담고 무엇을 빼는지 고정한다.

import json
import subprocess
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
    leftover_placeholders,
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


def test_real_data_input_never_ships() -> None:
    """`data/input/` 은 실데이터 자리다. 세트에 들어오면 빌드가 멈춰야 한다.

    한때 표시순서 CSV 를 `EXTRA_FILES` 로 실어 보냈는데, 그 파일에 실제 고객명·제품명이
    들어 있고 배포는 메일로 나간다. 사내가 만든 사본을 사외 것이 덮는 문제도 있었다.
    """
    assert "data/input/RQ_DISPLAY_ORDER.csv" not in deploy_set(["app.py"])
    assert forbidden_entries(["data/input/RQ_DISPLAY_ORDER.csv"]) == [
        "data/input/RQ_DISPLAY_ORDER.csv"
    ]
    # 빈 폴더 자리표는 데이터가 아니라 계속 보낸다.
    assert forbidden_entries(["data/input/.gitkeep"]) == []


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
    paths = ["app.py", "README.md", "config/bootstrap_display_order.json"]

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


def test_runbook_placeholders_are_counted_until_filled() -> None:
    """7장 초안의 자리표가 남으면 빌드가 막힌다 — stamp 선언 대조는 머리 한 곳만 본다."""
    draft = "이 절은 stamp `<STAMP>` 배포용이다. `review/<STAMP>.md` · 추가 {APPLY_FACTS}"

    assert leftover_placeholders(draft) == {"<STAMP>": 2, "{APPLY_FACTS}": 1}
    assert leftover_placeholders("이 절은 stamp `202610121200` 배포용이다. 추가 13") == {}
    assert leftover_placeholders("커밋 `deploy: <stamp>` 꼴") == {}


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


@pytest.fixture
def pushed_repo(tmp_path: Path) -> Path:
    """`main` 을 원격(빈 저장소)에 올린 작은 저장소. 트리가 깨끗하고 HEAD == origin/main 이다."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")
    root = tmp_path / "work"
    root.mkdir()
    # 사내 Windows 4관문에서도 돈다 — 그쪽 git 판·전역 설정에 기대지 않는다. `init -b` 는
    # git 2.28 부터라 HEAD 를 손으로 돌리고, 전역 서명·훅이 빌더의 `git tag` 와 커밋을
    # 막지 않게 끈다.
    _git(root, "init", "-q")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    for key, value in (
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
        ("core.hooksPath", str(tmp_path / "no-hooks")),
        # 빌더는 작업 트리 바이트를 그대로 싣는다. 같은 바이트를 견주도록 `write_text`(Windows
        # 에서 `\n` → `\r\n`) 대신 바이트로 쓰고 줄끝 변환도 끈다.
        ("core.autocrlf", "false"),
    ):
        _git(root, "config", key, value)
    (root / "app.py").write_bytes(b"x = 1\n")
    _git(root, "add", "app.py")
    _git(root, "commit", "-q", "-m", "첫 커밋")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-q", "origin", "main")
    return root


def test_a_clean_pushed_tree_has_no_source_problems(pushed_repo: Path) -> None:
    from build_deploy_package import source_problems

    assert source_problems(pushed_repo) == []


@pytest.mark.parametrize("staged", [False, True])
def test_an_uncommitted_tracked_edit_is_a_source_problem(pushed_repo: Path, staged: bool) -> None:
    """내용은 작업 트리에서 읽는다. 커밋하지 않은 수정은 ZIP 에 실리고 송장의 커밋과 어긋난다."""
    from build_deploy_package import source_problems

    (pushed_repo / "app.py").write_bytes(b"x = 2\n")
    if staged:
        _git(pushed_repo, "add", "app.py")

    problems = source_problems(pushed_repo)

    assert len(problems) == 1
    assert "커밋하지 않은 수정이 1개" in problems[0]
    assert "app.py" in problems[0]


def test_an_unpushed_commit_is_a_source_problem(pushed_repo: Path) -> None:
    """송장의 커밋이 원격에 없으면 사내 리뷰가 부르는 커밋을 사외가 다시 꺼낼 수 없다."""
    from build_deploy_package import source_problems

    (pushed_repo / "app.py").write_bytes(b"x = 2\n")
    _git(pushed_repo, "commit", "-q", "-am", "푸시 전")

    problems = source_problems(pushed_repo)

    assert len(problems) == 1
    assert "origin/main" in problems[0]
    assert "앞선 커밋 1 · 뒤진 커밋 0" in problems[0]


def test_a_missing_upstream_is_a_source_problem(pushed_repo: Path) -> None:
    from build_deploy_package import source_problems

    _git(pushed_repo, "remote", "remove", "origin")

    problems = source_problems(pushed_repo)

    assert len(problems) == 1
    assert "origin/main 을 찾지 못했습니다" in problems[0]


def test_untracked_files_are_reported_but_are_not_source_problems(pushed_repo: Path) -> None:
    """추적하지 않는 파일은 ZIP 에 실리지 않는다 — 내용이 HEAD 와 어긋나게 만들지는 않는다."""
    from build_deploy_package import source_problems, untracked_entries

    (pushed_repo / "new_module.py").write_text("", encoding="utf-8")

    assert source_problems(pushed_repo) == []
    assert untracked_entries(pushed_repo) == ["new_module.py"]


def test_the_build_stops_before_writing_when_the_tree_is_not_pushed(
    pushed_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """보낼 ZIP(태그를 남기는 빌드)은 만들지도 태그를 달지도 않고 멈춘다."""
    import build_deploy_package

    monkeypatch.setattr(build_deploy_package, "PROJECT_ROOT", pushed_repo)
    (pushed_repo / "app.py").write_bytes(b"x = 2\n")
    out = tmp_path / "out"

    assert build_deploy_package.main(["--out", str(out), "--stamp", "202610131200"]) == 1
    assert not (out / "202610131200.zip").exists()
    assert _git(pushed_repo, "tag", "--list") == ""


def test_a_trial_build_only_warns_about_an_unpushed_tree(
    pushed_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """런북 수치를 재는 시험 빌드는 커밋·푸시 전에 돈다. 알리고 만들되 태그는 남기지 않는다."""
    import build_deploy_package

    monkeypatch.setattr(build_deploy_package, "PROJECT_ROOT", pushed_repo)
    (pushed_repo / "app.py").write_bytes(b"x = 2\n")
    out = tmp_path / "out"

    code = build_deploy_package.main(["--out", str(out), "--stamp", "202610131200", "--no-tag"])

    assert code == 0
    assert "시험 빌드(--no-tag)라 멈추지 않습니다" in capsys.readouterr().out
    with zipfile.ZipFile(out / "202610131200.zip") as archive:
        assert archive.read("app.py") == b"x = 2\n"
    assert _git(pushed_repo, "tag", "--list") == ""


def test_a_clean_pushed_build_ships_head_and_tags_it(
    pushed_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import build_deploy_package

    monkeypatch.setattr(build_deploy_package, "PROJECT_ROOT", pushed_repo)
    out = tmp_path / "out"

    assert build_deploy_package.main(["--out", str(out), "--stamp", "202610131200"]) == 0
    with zipfile.ZipFile(out / "202610131200.zip") as archive:
        manifest = json.loads(archive.read("DEPLOY_MANIFEST.json"))
        assert archive.read("app.py") == b"x = 1\n"
    assert manifest["commit"] == _git(pushed_repo, "rev-parse", "HEAD")
    assert _git(pushed_repo, "tag", "--list") == "deploy/202610131200"


def test_a_second_tagged_build_with_the_same_stamp_stops_before_overwriting(
    pushed_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """같은 stamp 의 태그가 이미 있으면 확인을 마친 ZIP 을 덮지 않고 멈춘다.

    그대로 다시 만들면 송장의 직전 배포가 자기 자신이 되어 변경 목록이 비거나 고친 것 하나로
    줄고, 태그는 첫 빌드 커밋에 남은 채 다른 내용의 ZIP 이 성공(0)으로 나간다.
    """
    import build_deploy_package

    monkeypatch.setattr(build_deploy_package, "PROJECT_ROOT", pushed_repo)
    out = tmp_path / "out"
    zip_path = out / "202610131200.zip"
    assert build_deploy_package.main(["--out", str(out), "--stamp", "202610131200"]) == 0
    first_bytes = zip_path.read_bytes()
    first_commit = _git(pushed_repo, "rev-parse", "HEAD")
    (pushed_repo / "app.py").write_bytes(b"x = 2\n")
    _git(pushed_repo, "commit", "-q", "-am", "확인 뒤 고침")
    _git(pushed_repo, "push", "-q", "origin", "main")
    capsys.readouterr()

    assert build_deploy_package.main(["--out", str(out), "--stamp", "202610131200"]) == 1
    assert "태그 deploy/202610131200 가 이미 있습니다" in capsys.readouterr().err
    assert zip_path.read_bytes() == first_bytes
    assert _git(pushed_repo, "rev-parse", "deploy/202610131200^{commit}") == first_commit


def test_the_previous_deploy_is_the_last_tag_before_this_stamp(
    pushed_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이번 stamp 이상인 태그(같은 stamp 의 남은 태그·더 늦은 시험 태그)는 직전 배포가 아니다."""
    import build_deploy_package

    monkeypatch.setattr(build_deploy_package, "PROJECT_ROOT", pushed_repo)
    first_commit = _git(pushed_repo, "rev-parse", "HEAD")
    _git(pushed_repo, "tag", "deploy/202610121200")
    (pushed_repo / "app.py").write_bytes(b"x = 2\n")
    _git(pushed_repo, "commit", "-q", "-am", "둘째 커밋")
    _git(pushed_repo, "push", "-q", "origin", "main")
    _git(pushed_repo, "tag", "deploy/202610131200")
    _git(pushed_repo, "tag", "deploy/202610141200")
    out = tmp_path / "out"

    code = build_deploy_package.main(["--out", str(out), "--stamp", "202610131200", "--no-tag"])

    assert code == 0
    with zipfile.ZipFile(out / "202610131200.zip") as archive:
        manifest = json.loads(archive.read("DEPLOY_MANIFEST.json"))
    assert manifest["previous_deploy"] == "202610121200"
    assert manifest["previous_commit"] == first_commit
    assert manifest["changes"] == {"M": ["app.py"]}
