# Purpose: 사내 배포 적용기의 안전 장치 — 무엇을 지우고 무엇을 남기며 언제 멈추는지 고정한다.

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import apply_deploy_package  # noqa: E402
from apply_deploy_package import (  # noqa: E402
    PLACEHOLDER_NAMES,
    PRESERVED_PREFIXES,
    ApplyError,
    describe_plan,
    describe_reconcile,
    digest_mismatches,
    is_protected,
    member_problems,
    order_problems,
    plan_removals,
    read_manifest,
    reconcile,
    tracked_files,
    untracked_files,
)


def test_preserved_paths_are_never_removed() -> None:
    """리뷰 기록·적용 이력·권한 설정은 사내가 만든 것이라 배포가 지우면 안 된다."""
    tracked = [
        "app.py",
        "src/capa_simulation/settings.py",
        "review/202609161506.md",
        ".deploy/applied.json",
        ".claude/settings.json",
    ]

    removals = plan_removals(tracked)

    assert removals == ["app.py", "src/capa_simulation/settings.py"]
    for path in tracked:
        if path.startswith(PRESERVED_PREFIXES):
            assert path not in removals


def test_ignored_data_is_out_of_reach_because_only_tracked_files_are_removed() -> None:
    """사내 DuckDB 와 `data/` 실데이터는 `git ls-files` 에 없다.

    지울 대상을 추적 파일에서만 고르므로 그 둘은 애초에 후보가 아니다. `git clean -x` 를
    쓰지 않는 이유가 이것이고, 한 글자 차이로 되돌릴 수 없는 데이터가 날아간다.

    두 번째 겹은 `is_protected` 다 — 추적 목록에 **들어와 버린** 경우까지 막는다.
    """
    tracked = ["app.py", "data/input/.gitkeep"]

    removals = plan_removals(tracked)

    assert removals == ["app.py"]
    assert "data/capa_simulation.duckdb" not in removals


@pytest.mark.parametrize(
    "name",
    [
        "../escape.py",
        "/absolute.py",
        "app/../../escape.py",
        "review/notes.md",
        ".deploy/applied.json",
    ],
)
def test_dangerous_archive_members_are_refused(name: str) -> None:
    """저장소 밖을 가리키거나 사내 전용 자리를 덮는 항목은 풀기 전에 걸러진다."""
    assert member_problems([name]), f"걸러지지 않았습니다: {name}"


@pytest.mark.parametrize(
    "name",
    [
        "data/capa_simulation.duckdb",
        "data/equipment_availability.duckdb.wal",
        "data/capa_simulation.duckdb.sync.json",
        ".env",
        ".streamlit/Secrets.toml",
        "data/input/Core_Data.csv",
        "DATA/Input/RQ_DISPLAY_ORDER.csv",
        "data/output/result.csv",
        "templates/structure_template.xlsb",
    ],
)
def test_archive_members_that_would_overwrite_operational_data_are_refused(name: str) -> None:
    """운영 데이터 자리를 덮는 항목은 풀기 전에 멈춘다.

    그 파일들은 무시 파일이라 덮인 뒤에는 `git checkout -- .` 로도 돌아오지 않는다. 삭제를
    `is_protected` 가 막는 것과 같은 이유로, 덮어쓰기도 빌더의 `forbidden_entries` 한 겹에만
    맡기지 않는다 — 옛 빌더나 손으로 만든 ZIP 은 송장 해시까지 맞은 채 들어온다.
    """
    problems = member_problems([name])

    assert any("운영 데이터" in problem for problem in problems), name


def test_directory_placeholders_in_the_archive_are_not_refused() -> None:
    """`data/input/.gitkeep` 등은 배포가 싣는 빈 폴더 자리표다 — 거절하면 모든 배포가 멈춘다."""
    names = ["data/input/.gitkeep", "data/output/.gitkeep", "data/temp/.gitkeep", "app.py"]

    assert member_problems(names) == []


def test_the_current_deploy_set_passes_the_member_checks() -> None:
    """규칙이 아니라 지금 빌더가 보낼 실제 목록으로 확인한다 — 정상 배포가 멈추면 안 된다.

    사내 전용 자리는 뺀다. 사내 저장소는 `review/` 를 추적하고, 빌더는 그 자리를 따로
    (`internal_only_entries`) 막아 ZIP 에 싣지 않는다.
    """
    from build_deploy_package import deploy_set, tracked_files

    shipped = [
        path
        for path in deploy_set(tracked_files(PROJECT_ROOT))
        if not path.startswith(PRESERVED_PREFIXES)
    ]

    assert member_problems(shipped) == []


def test_case_only_duplicates_are_refused() -> None:
    """Windows 는 대소문자를 가리지 않아 두 항목이 한 파일로 겹치고 하나가 사라진다."""
    problems = member_problems(["app_pages/Home.py", "app_pages/home.py"])

    assert any("대소문자" in problem for problem in problems)


def test_a_normal_member_list_passes() -> None:
    assert member_problems(["app.py", "src/capa_simulation/settings.py"]) == []


def test_reapplying_the_same_deploy_stops() -> None:
    problems = order_problems({"stamp": "202609161506"}, {"stamp": "202609161506"})

    assert problems and problems[0].startswith("중단:")


def test_an_older_zip_stops_so_the_repository_cannot_go_backwards() -> None:
    """메일함에서 옛 배포를 잘못 열면 사내가 과거로 돌아간다."""
    problems = order_problems({"stamp": "202609161506"}, {"stamp": "202609161253"})

    assert problems and problems[0].startswith("중단:")


def test_a_newer_zip_proceeds() -> None:
    problems = order_problems({"stamp": "202609161253"}, {"stamp": "202609161506"})

    assert all(not problem.startswith("중단:") for problem in problems)


def test_a_skipped_deploy_is_reported_but_does_not_stop() -> None:
    """건너뛴 배포는 알릴 일이지 막을 일이 아니다 — ZIP 은 늘 전체를 담는다."""
    problems = order_problems(
        {"stamp": "202609151706", "commit": "aaaaaaa"},
        {"stamp": "202609161506", "previous_commit": "bbbbbbb"},
    )

    assert problems
    assert all(not problem.startswith("중단:") for problem in problems)
    assert any("건너뛴" in problem for problem in problems)


def test_the_first_apply_has_nothing_to_compare_and_proceeds() -> None:
    assert order_problems({}, {"stamp": "202609161506"}) == []


def test_a_zip_without_a_manifest_is_refused(tmp_path: Path) -> None:
    import zipfile

    path = tmp_path / "old.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("app.py", "x = 1\n")

    with zipfile.ZipFile(path) as archive:
        with pytest.raises(ApplyError, match="송장 없이는"):
            read_manifest(archive)


def test_an_unknown_manifest_version_is_refused(tmp_path: Path) -> None:
    import json
    import zipfile

    path = tmp_path / "future.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("DEPLOY_MANIFEST.json", json.dumps({"manifest_version": 99}))

    with zipfile.ZipFile(path) as archive:
        with pytest.raises(ApplyError, match="적용기를 먼저 갱신"):
            read_manifest(archive)


def test_digest_mismatch_names_the_file(tmp_path: Path) -> None:
    import hashlib

    # `write_text` 는 Windows 에서 `\n` 을 `\r\n` 으로 바꾼다. 적용기는 `write_bytes` 로
    # ZIP 바이트를 그대로 쓰므로, 여기서도 바이트로 적어야 실제와 같은 비교가 된다.
    payload = b"x = 1\n"
    (tmp_path / "app.py").write_bytes(payload)
    good = "sha256:" + hashlib.sha256(payload).hexdigest()

    assert digest_mismatches(tmp_path, {"app.py": good}) == []
    assert digest_mismatches(tmp_path, {"app.py": "sha256:0" * 8})[0].startswith("app.py")
    assert "파일이 없습니다" in digest_mismatches(tmp_path, {"gone.py": good})[0]


def test_files_the_zip_deliberately_omits_are_never_removed() -> None:
    """`pyproject.toml`·`uv.lock` 은 사내 것이라 보내지 않는다 — 지우면 복구할 길이 없다.

    사내 `pyproject.toml` 에는 Artifactory 인덱스가, 그 락에는 `bigdataquery` 가 들어
    있다. ZIP 에 없다는 이유로 지우면 적용할 때마다 사내 환경이 무너진다.
    """
    tracked = ["app.py", "pyproject.toml", "uv.lock", "src/gone.py"]
    members = ["app.py"]
    kept = ["pyproject.toml", "uv.lock"]

    removals = plan_removals(tracked, members, kept)

    assert removals == ["src/gone.py"]


def test_only_files_that_vanished_outside_are_removed() -> None:
    """ZIP 이 다시 깔 파일은 지웠다 쓸 이유가 없다 — 실패 지점만 는다."""
    tracked = ["app.py", "src/old.py"]
    members = ["app.py", "src/new.py"]

    assert plan_removals(tracked, members) == ["src/old.py"]


def test_nothing_is_removed_when_the_zip_matches_the_tree() -> None:
    tracked = ["app.py", "src/settings.py"]

    assert plan_removals(tracked, tracked) == []


def test_reconcile_separates_what_the_deploy_owns_from_what_nobody_owns() -> None:
    """사외 목록과 사내 폴더를 맞대어 세 갈래로 가른다.

    **정체불명 칸이 이 기능의 핵심이다.** 추적도 무시도 되지 않는 파일은 지울 대상 계산에
    아예 들어오지 않아 그동안 보이지 않았다 — 옛 배포의 잔해가 조용히 쌓이고, 읽는 쪽은
    그것이 살아 있는 코드인지 알 수 없어 일단 읽는다.
    """
    report = reconcile(
        tracked=["app.py", "src/gone.py", "review/2026.md", "pyproject.toml"],
        untracked=[".omo/run-continuation/s1.json", "scripts/leftover.py"],
        expected=["app.py", "docs/new.md"],
        kept=["pyproject.toml"],
    )

    assert report["사외에서_지워짐"] == ["src/gone.py"]
    assert report["정체불명"] == [".omo/run-continuation/s1.json", "scripts/leftover.py"]
    assert report["목록에만_있음"] == ["docs/new.md"]
    # 보존 자리와 「남기라고 한 것」은 어느 칸에도 들어가지 않는다.
    assert "review/2026.md" not in sum(report.values(), [])
    assert "pyproject.toml" not in sum(report.values(), [])


def test_reconcile_is_quiet_when_the_folder_matches_the_list() -> None:
    report = reconcile(tracked=["app.py"], untracked=[], expected=["app.py"])

    assert all(not paths for paths in report.values())


def test_unknown_files_are_reported_but_never_removed() -> None:
    """무엇인지 모르는 채 지우는 것이 가장 위험하다 — 보고만 하고 사람에게 묻는다."""
    unknown = ".omo/run-continuation/s1.json"
    report = reconcile(tracked=["app.py"], untracked=[unknown], expected=["app.py"])

    assert report["정체불명"] == [unknown]
    assert unknown not in plan_removals(["app.py"], ["app.py"])

    rendered = describe_reconcile(report, applied=False)
    assert "손대지 않았습니다" in rendered
    assert "사용자에게 물으세요" in rendered


# 운영 데이터는 사내 `.gitignore` 가 막아 추적 목록에 없다 — 는 것이 `plan_removals` 의
# 전제였다. 그 규칙이 사내에서 지워지거나 파일이 먼저 커밋되면 전제가 깨지고, ZIP 이 싣지
# 않는 DuckDB 가 「사외에서 없어진 파일」로 판정돼 지워진다. 되돌릴 수 없는 종류다.


def test_a_tracked_operational_database_is_never_removed() -> None:
    tracked = [
        "app.py",
        "data/capa_simulation.duckdb",
        "data/equipment_availability.duckdb",
        "data/capa_simulation.duckdb.sync.json",
        "old_module.py",
    ]

    removals = plan_removals(tracked, members=["app.py"])

    assert removals == ["old_module.py"]


def test_tracked_real_data_and_secrets_are_never_removed() -> None:
    tracked = [
        ".env",
        ".streamlit/secrets.toml",
        "data/input/Core_Data.csv",
        "data/output/result.csv",
        "data/temp/scratch.csv",
        "templates/structure_template.xlsb",
        "gone.py",
    ]

    assert plan_removals(tracked) == ["gone.py"]


def test_directory_placeholders_are_protected_too() -> None:
    """`data/output/.gitkeep` 은 배포 세트에 있지만, 없더라도 지우면 폴더가 사라진다."""
    assert plan_removals(["data/output/.gitkeep", "data/temp/.gitkeep"]) == []


def test_the_plan_says_out_loud_that_data_is_tracked() -> None:
    """지우지 않는 것만으로는 부족하다 — 추적되고 있다는 사실 자체가 고쳐야 할 상태다."""
    text = describe_plan(
        {"zip_name": "z.zip", "file_count": 1},
        [],
        ["app.py"],
        tracked=["app.py", "data/capa_simulation.duckdb"],
    )

    assert "data/capa_simulation.duckdb" in text
    assert "git rm -r --cached" in text


def test_protection_does_not_depend_on_spelling() -> None:
    """확장자만 소문자로 보고 이름·접두사는 원래 철자로 보고 있었다.

    Windows 에서 `.ENV` 는 실제로 생기는 철자다. 그 한 글자 차이로 `is_protected` 가
    「지워도 되는 파일」이라고 답했고, 같은 뜻을 가진 `build_deploy_package.forbidden_entries`
    는 셋 다 소문자로 보고 있어 **한 파일이 배포에서는 금지이고 적용에서는 허용**이었다.
    """
    for path in (".ENV", ".Env", "data/Input/Core_Data.csv", "DATA/TEMP/x.csv", "data/DB.DuckDB"):
        assert is_protected(path), path


def test_the_two_deploy_scripts_agree_on_what_is_untouchable() -> None:
    """한쪽이 「보내면 안 된다」고 한 것을 다른 쪽이 「지워도 된다」고 하면 안 된다."""
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    import build_deploy_package as build
    from build_deploy_package import INTERNAL_ONLY_PREFIXES, forbidden_entries

    assert set(INTERNAL_ONLY_PREFIXES) == set(PRESERVED_PREFIXES)
    assert set(build.PLACEHOLDER_NAMES) == set(PLACEHOLDER_NAMES)

    for path in (
        ".env",
        ".ENV",
        ".streamlit/secrets.toml",
        ".streamlit/Secrets.toml",
        "data/capa_simulation.duckdb",
        "data/capa_simulation.duckdb.sync.json",
        "data/output/result.csv",
        "data/temp/scratch.csv",
    ):
        assert forbidden_entries([path]) == [path], path
        assert is_protected(path), path
        assert member_problems([path]), path

    for placeholder in ("data/input/.gitkeep", "data/output/.gitkeep", "data/temp/.gitkeep"):
        assert forbidden_entries([placeholder]) == [], placeholder
        assert member_problems([placeholder]) == [], placeholder


def test_reconcile_does_not_call_protected_files_deleted() -> None:
    """계획은 안 지운다고 하는데 대조는 지울 것이라고 적으면 같은 출력이 모순이다."""
    report = reconcile(
        ["app.py", "data/capa_simulation.duckdb", ".env", "gone.py"],
        [],
        ["app.py"],
    )

    assert report["사외에서_지워짐"] == ["gone.py"]


# 커밋 단계 실패 — 파일 적용·해시 대조가 끝난 뒤 스테이징이나 커밋이 멈추면 인덱스에 이번 배포가
# 반쯤 올라가고 적용 기록은 새 stamp 가 된다. 그 상태로 두면 같은 명령은 「이미 적용했습니다」로
# 거절되고, 런북 6장의 `git checkout -- .` 한 줄로도 돌아오지 않는다(인덱스가 이미 바뀌었다).

_DEPLOY_STAMP = "202610220000"
_DEPLOY_COMMIT = "f65de0f" + "0" * 33


def _repo_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _internal_repo(tmp_path: Path, previous_stamp: str | None) -> Path:
    """사내 흉내 저장소. 적용기는 `-c user.*` 없이 커밋하므로 사용자 이름은 저장소 설정에 둔다."""
    root = tmp_path / "internal"
    root.mkdir()
    _repo_git(root, "init", "-q")
    # 사내 Windows 4관문에서도 돈다 — 전역 서명·훅·줄끝 변환에 기대지 않는다.
    for key, value in (
        ("user.name", "test"),
        ("user.email", "test@example.com"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", str(tmp_path / "no-hooks")),
        ("core.autocrlf", "false"),
    ):
        _repo_git(root, "config", key, value)
    (root / "app.py").write_bytes(b"x = 1\n")
    (root / "gone.py").write_bytes(b"old\n")
    paths = ["app.py", "gone.py"]
    if previous_stamp is not None:
        (root / ".deploy").mkdir()
        (root / ".deploy" / "applied.json").write_bytes(
            json.dumps({"stamp": previous_stamp, "commit": "a" * 40}).encode("utf-8") + b"\n"
        )
        paths.append(".deploy/applied.json")
    _repo_git(root, "add", *paths)
    _repo_git(root, "commit", "-q", "-m", "첫 커밋")
    return root


def _deploy_zip(tmp_path: Path, *, digests: Mapping[str, str] | None = None) -> Path:
    """`digests` 는 송장에 적을 해시를 경로별로 바꿔 쓴다 — 전송 중 깨진 ZIP 의 흉내."""
    files = {"app.py": b"x = 2\n", "src/new.py": b"y = 1\n"}
    manifest = {
        "manifest_version": 1,
        "stamp": _DEPLOY_STAMP,
        "commit": _DEPLOY_COMMIT,
        "commit_subject": "사외 커밋 제목",
        "file_count": len(files),
        "files": {
            path: "sha256:" + hashlib.sha256(data).hexdigest() for path, data in files.items()
        }
        | dict(digests or {}),
    }
    path = tmp_path / f"{_DEPLOY_STAMP}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("DEPLOY_MANIFEST.json", json.dumps(manifest, ensure_ascii=False))
        for name, data in files.items():
            archive.writestr(name, data)
    return path


@pytest.mark.parametrize("failing_step", ["add", "commit"])
@pytest.mark.parametrize("previous_stamp", [None, "202610010000"])
def test_a_failed_commit_step_rolls_back_so_the_same_command_can_run_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failing_step: str,
    previous_stamp: str | None,
) -> None:
    """커밋 훅·다른 프로그램이 쥔 `.git/index.lock`·빈 git 사용자 이름이 커밋 단계를 막는 경우.

    스테이징은 200개씩 나눠 하므로 중간에 멈추면 일부만 올라가 있다 — 여기서는 `add` 가 실제로
    올린 뒤 실패를 내어 그 꼴을 만든다. 적용기는 인덱스와 적용 기록을 적용 전으로 되돌리고, 사람은
    런북대로 `git checkout -- .` 한 줄 뒤 같은 명령을 다시 쳐서 `deploy:` 커밋까지 간다.
    """
    root = _internal_repo(tmp_path, previous_stamp)
    state_file = root / ".deploy" / "applied.json"
    state_before = state_file.read_bytes() if state_file.is_file() else None
    archive = _deploy_zip(tmp_path)
    monkeypatch.setattr(apply_deploy_package, "PROJECT_ROOT", root)

    real_git = apply_deploy_package.git

    def blocked_git(repo: Path, *args: str, check: bool = True) -> str:
        if args and args[0] == failing_step:
            if failing_step == "add":
                real_git(repo, *args, check=check)
            raise ApplyError(f"git {' '.join(args)} 실패: blocked")
        return real_git(repo, *args, check=check)

    monkeypatch.setattr(apply_deploy_package, "git", blocked_git)

    assert apply_deploy_package.main([str(archive)]) == 1
    stderr = capsys.readouterr().err
    assert "커밋 단계" in stderr
    assert "git checkout -- ." in stderr
    # 인덱스는 적용 전(HEAD)과 같고, 적용 기록도 적용 전 그대로다.
    assert _repo_git(root, "diff", "--cached", "--name-only") == ""
    assert (state_file.read_bytes() if state_file.is_file() else None) == state_before
    assert _repo_git(root, "log", "-1", "--format=%s") == "첫 커밋"

    monkeypatch.setattr(apply_deploy_package, "git", real_git)
    _repo_git(root, "checkout", "--", ".")

    assert apply_deploy_package.main([str(archive)]) == 0
    assert _repo_git(root, "log", "-1", "--format=%s") == (
        f"deploy: {_DEPLOY_STAMP} ({_DEPLOY_COMMIT[:7]})"
    )
    assert _repo_git(root, "status", "--porcelain", "--untracked-files=no") == ""
    assert _repo_git(root, "ls-files", "gone.py") == ""
    assert (root / "app.py").read_bytes() == b"x = 2\n"
    assert _DEPLOY_STAMP in state_file.read_text(encoding="utf-8")


def test_a_held_index_lock_names_the_manual_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """다른 프로그램(IDE 등)이 `.git/index.lock` 을 쥐고 있으면 스테이징도 `git reset` 도 막힌다.

    적용기가 인덱스를 되돌리지 못한 것을 감추지 않고, 손으로 칠 줄을 차례로 적는다.
    """
    root = _internal_repo(tmp_path, None)
    archive = _deploy_zip(tmp_path)
    monkeypatch.setattr(apply_deploy_package, "PROJECT_ROOT", root)
    lock = root / ".git" / "index.lock"
    lock.write_bytes(b"")

    assert apply_deploy_package.main([str(archive)]) == 1
    stderr = capsys.readouterr().err
    assert "커밋 단계" in stderr
    assert "인덱스 되돌리기 실패" in stderr
    assert "git reset -q" in stderr
    assert "git checkout -- ." in stderr
    assert not (root / ".deploy" / "applied.json").exists()

    lock.unlink()
    _repo_git(root, "reset", "-q")
    _repo_git(root, "checkout", "--", ".")

    assert apply_deploy_package.main([str(archive)]) == 0
    assert _repo_git(root, "log", "-1", "--format=%s").startswith(f"deploy: {_DEPLOY_STAMP} ")


@pytest.mark.parametrize("previous_stamp", [None, "202610010000"])
def test_the_runbook_tells_a_finished_deploy_from_one_left_at_the_commit_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    previous_stamp: str | None,
) -> None:
    """런북 6장 `이미 적용했습니다` 줄의 판별 — 적용 기록을 마지막으로 바꾼 커밋의 제목.

    정상 흐름은 `deploy:` 커밋 뒤에 5장의 `review:` 커밋이 오므로 맨 `git log -1` 로는 가를 수 없다.
    판별은 `deploy:` 커밋이 적용 기록을 함께 싣는다는 데 기댄다. 커밋 단계에서 멈춘 꼴(적용 기록은
    새 stamp, `deploy:` 커밋은 없음)은 `--no-commit` 으로 만든다.
    """
    judge = ("log", "-1", "--format=%s", "--", ".deploy/applied.json")
    archive = _deploy_zip(tmp_path)

    stuck_home = tmp_path / "stuck"
    stuck_home.mkdir()
    stuck = _internal_repo(stuck_home, previous_stamp)
    monkeypatch.setattr(apply_deploy_package, "PROJECT_ROOT", stuck)
    assert apply_deploy_package.main([str(archive), "--no-commit"]) == 0
    assert apply_deploy_package.main([str(archive)]) == 1
    assert "이미 적용했습니다" in capsys.readouterr().err
    assert _repo_git(stuck, *judge) == ("" if previous_stamp is None else "첫 커밋")

    done_home = tmp_path / "done"
    done_home.mkdir()
    done = _internal_repo(done_home, previous_stamp)
    monkeypatch.setattr(apply_deploy_package, "PROJECT_ROOT", done)
    assert apply_deploy_package.main([str(archive)]) == 0
    (done / "review").mkdir()
    (done / "review" / "r.md").write_bytes(b"review\n")
    _repo_git(done, "add", "review/r.md")
    _repo_git(done, "commit", "-q", "-m", "review: r")
    assert apply_deploy_package.main([str(archive)]) == 1
    assert "이미 적용했습니다" in capsys.readouterr().err
    assert _repo_git(done, "log", "-1", "--format=%s") == "review: r"
    assert _repo_git(done, *judge) == f"deploy: {_DEPLOY_STAMP} ({_DEPLOY_COMMIT[:7]})"


@pytest.mark.parametrize("staged", [False, True])
def test_uncommitted_edits_stop_the_apply_and_survive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    staged: bool,
) -> None:
    """사용자가 지시한 사내 임시 수정(런북 0장·1-5)이 남은 채 적용하면 아무것도 안 건드리고 멈춘다.

    런북은 적용 전에 그 diff 를 저장소 밖에 남기고 되돌리라고 한다. 그 단계를 빠뜨렸을 때 남는
    방어선이 이 멈춤 하나다 — 없으면 지우고 푸는 과정이 임시 수정을 `deploy:` 커밋 밑에 말없이
    덮고 되살릴 근거도 남지 않는다. 스테이징만 해 둔 수정도 같은 미저장 변경이다. 보기만 하는
    `--dry-run` 은 깨끗한 트리를 요구하지 않는다 — 작업 중에 대조해 보는 것이 그 쓸모다.
    """
    root = _internal_repo(tmp_path, "202610010000")
    state_file = root / ".deploy" / "applied.json"
    state_before = state_file.read_bytes()
    temp_fix = b"x = 99  # temp fix\n"
    (root / "app.py").write_bytes(temp_fix)
    if staged:
        _repo_git(root, "add", "app.py")
    archive = _deploy_zip(tmp_path)
    monkeypatch.setattr(apply_deploy_package, "PROJECT_ROOT", root)

    assert apply_deploy_package.main([str(archive), "--dry-run"]) == 0
    assert "보기만 했습니다" in capsys.readouterr().out

    assert apply_deploy_package.main([str(archive)]) == 1
    stderr = capsys.readouterr().err
    assert "미저장 변경" in stderr
    assert "app.py" in stderr
    assert (root / "app.py").read_bytes() == temp_fix
    assert (root / "gone.py").read_bytes() == b"old\n"
    assert not (root / "src" / "new.py").exists()
    assert _repo_git(root, "diff", "--cached", "--name-only") == ("app.py" if staged else "")
    assert state_file.read_bytes() == state_before
    assert _repo_git(root, "log", "-1", "--format=%s") == "첫 커밋"


def test_a_digest_mismatch_after_unpacking_stops_before_the_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """푼 파일의 해시가 송장과 어긋나면 `deploy:` 커밋도 적용 기록도 만들지 않고 멈춘다.

    ZIP 의 CRC 가 맞아도 내용이 송장과 다를 수 있다. 적용 기록이 먼저 새 stamp 로 바뀌면 다시 받은
    ZIP 이 「이미 적용했습니다」로 거절되므로, 런북 6장대로 `git checkout -- .` 한 줄 뒤 다시 받은
    ZIP 이 그대로 적용돼야 한다.
    """
    root = _internal_repo(tmp_path, "202610010000")
    state_file = root / ".deploy" / "applied.json"
    state_before = state_file.read_bytes()
    archive = _deploy_zip(tmp_path, digests={"app.py": "sha256:" + "0" * 64})
    monkeypatch.setattr(apply_deploy_package, "PROJECT_ROOT", root)

    assert apply_deploy_package.main([str(archive)]) == 1
    stderr = capsys.readouterr().err
    assert "해시 대조에서 1건" in stderr
    assert "app.py — 해시가 다릅니다" in stderr
    assert "git checkout -- ." in stderr
    assert _repo_git(root, "log", "-1", "--format=%s") == "첫 커밋"
    assert _repo_git(root, "diff", "--cached", "--name-only") == ""
    assert state_file.read_bytes() == state_before

    _repo_git(root, "checkout", "--", ".")
    assert _repo_git(root, "status", "--porcelain", "--untracked-files=no") == ""
    assert (root / "app.py").read_bytes() == b"x = 1\n"

    assert apply_deploy_package.main([str(_deploy_zip(tmp_path))]) == 0
    assert _repo_git(root, "log", "-1", "--format=%s") == (
        f"deploy: {_DEPLOY_STAMP} ({_DEPLOY_COMMIT[:7]})"
    )
    assert (root / "app.py").read_bytes() == b"x = 2\n"


@pytest.fixture
def korean_review_repo(tmp_path: Path) -> Path:
    """한글 이름 리뷰 문서를 커밋하고 추적 안 된 한글 이름 파일을 둔 사내 흉내 저장소.

    git 기본값 `core.quotePath=true` 는 비ASCII 경로를 `"review/\\354…"` 처럼 따옴표·8진수로
    감싸 낸다. 개인·사내 전역 설정에 기대지 않도록 그 기본값을 저장소에 적어 둔다 — 적용기가
    스스로 풀어 읽어야만 통과한다.
    """
    root = tmp_path / "internal"
    root.mkdir()
    _repo_git(root, "init", "-q")
    _repo_git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    for key, value in (
        ("user.name", "test"),
        ("user.email", "test@example.com"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", str(tmp_path / "no-hooks")),
        ("core.autocrlf", "false"),
        ("core.quotePath", "true"),
    ):
        _repo_git(root, "config", key, value)
    (root / "app.py").write_bytes(b"x = 1\n")
    (root / "review").mkdir()
    (root / "review" / "사내 회의록.md").write_bytes("# 회의록\n".encode())
    _repo_git(root, "add", "app.py", "review")
    _repo_git(root, "commit", "-q", "-m", "review: 회의록")
    (root / "정체불명.txt").write_bytes(b"?\n")
    return root


def test_non_ascii_paths_are_read_as_written_not_as_git_quotes(korean_review_repo: Path) -> None:
    """따옴표째 읽으면 `review/` 접두사가 안 맞아 보존 자리 파일이 「사외에서 지워짐」이 된다."""
    tracked = tracked_files(korean_review_repo)

    assert "review/사내 회의록.md" in tracked
    assert plan_removals(tracked, ["app.py"]) == []
    report = reconcile(tracked, untracked_files(korean_review_repo), ["app.py"])
    assert report["사외에서_지워짐"] == []
    assert report["정체불명"] == ["정체불명.txt"]


def test_a_deploy_commits_past_a_non_ascii_review_file(
    korean_review_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """스테이징에 따옴표 경로를 넘기면 git 이 pathspec 을 못 찾아 커밋 단계에서 멈춘다."""
    payload = b"x = 2\n"
    manifest = {
        "manifest_version": 1,
        "stamp": "202610211200",
        "zip_name": "202610211200.zip",
        "commit": "0" * 40,
        "commit_subject": "사외 커밋",
        "kept_on_target": [],
        "file_count": 1,
        "files": {"app.py": "sha256:" + hashlib.sha256(payload).hexdigest()},
    }
    package = tmp_path / "202610211200.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("app.py", payload)
        archive.writestr("DEPLOY_MANIFEST.json", json.dumps(manifest, ensure_ascii=False))
    monkeypatch.setattr(apply_deploy_package, "PROJECT_ROOT", korean_review_repo)

    assert apply_deploy_package.main([str(package), "--dry-run"]) == 0
    preview = capsys.readouterr().out
    assert "지움    없음" in preview
    assert "? 정체불명.txt" in preview

    assert apply_deploy_package.main([str(package)]) == 0
    assert (korean_review_repo / "review" / "사내 회의록.md").is_file()
    assert (korean_review_repo / "app.py").read_bytes() == payload
    assert _repo_git(korean_review_repo, "log", "-1", "--format=%s") == (
        "deploy: 202610211200 (0000000)"
    )
    committed = _repo_git(korean_review_repo, "show", "--name-only", "--format=", "HEAD")
    assert sorted(committed.splitlines()) == [".deploy/applied.json", "app.py"]


def test_the_stop_reason_on_stderr_is_utf8_like_stdout_in_a_cp949_pipe(tmp_path: Path) -> None:
    """사내 Windows 파이프는 cp949 다. 표준 출력만 UTF-8 로 바꾸면 멈춤 사유(표준 오류)만
    cp949 로 나와 한 실행 안에서 인코딩이 갈리고, UTF-8 로 읽는 쪽에서는 가장 중요한 그 줄이 깨진다.
    """
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "cp949"

    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "apply_deploy_package.py"),
            str(tmp_path / "missing.zip"),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        env=environment,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 1
    assert "멈췄습니다 — ZIP 을 찾지 못했습니다" in completed.stderr
