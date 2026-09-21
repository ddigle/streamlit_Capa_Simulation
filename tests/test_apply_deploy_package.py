# Purpose: 사내 배포 적용기의 안전 장치 — 무엇을 지우고 무엇을 남기며 언제 멈추는지 고정한다.

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from apply_deploy_package import (  # noqa: E402
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
    from build_deploy_package import INTERNAL_ONLY_PREFIXES, forbidden_entries

    assert set(INTERNAL_ONLY_PREFIXES) == set(PRESERVED_PREFIXES)

    for path in (
        ".env",
        ".ENV",
        ".streamlit/secrets.toml",
        ".streamlit/Secrets.toml",
        "data/capa_simulation.duckdb",
        "data/output/result.csv",
        "data/temp/scratch.csv",
    ):
        assert forbidden_entries([path]) == [path], path
        assert is_protected(path), path


def test_reconcile_does_not_call_protected_files_deleted() -> None:
    """계획은 안 지운다고 하는데 대조는 지울 것이라고 적으면 같은 출력이 모순이다."""
    report = reconcile(
        ["app.py", "data/capa_simulation.duckdb", ".env", "gone.py"],
        [],
        ["app.py"],
    )

    assert report["사외에서_지워짐"] == ["gone.py"]
