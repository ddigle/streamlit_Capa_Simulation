# Purpose: 후보 브랜치가 배정받은 홀짝 밖의 마이그레이션 번호를 만들지 못하게 막는다.

"""**같은 번호를 둘이 만들면 git 은 깨끗이 합치고, 그다음에 앱이 시작조차 못 한다.**

러너는 파일명이 아니라 버전 번호로 체크섬을 대조한다. 두 후보 브랜치가 각각 `0026` 을
만들면 텍스트가 겹치지 않아 git 이 충돌을 알려 주지 않고, 합친 뒤 그 번호가 이미 적용된
DB 에서만 「이미 적용된 마이그레이션이 변경되었습니다」로 죽는다. **나중에 번호를 바꿀
수도 없다** — 바꾸는 순간 그 DB 에서 같은 일이 난다.

그래서 `AGENTS.md` 14-4 가 홀짝으로 나눠 갖게 했는데, 배정이 「과제를 낼 때 정한다」라
사람이 기억해야 했다. 여기서는 **브랜치 이름에서 끌어온다** — 규약이
`cand/<과제>/<에이전트>` 이므로 마지막 조각이 곧 에이전트이고, 그 에이전트의 홀짝은
`config/parallel_agents.json` 이 갖는다(포트를 정하는 것과 같은 파일이다).

**후보 브랜치에서만 본다.** `main` 이나 사람이 만든 `feat/`·`fix/` 는 배정 대상이 아니라
건너뛴다. 그래서 통합 폴더에서 돌리면 이 검사는 늘 통과한다 — 잡히는 자리는 후보 폴더와
`cand/**` 푸시와 후보 브랜치 PR 의 CI 다. PR 체크아웃의 HEAD 는 브랜치가 아니므로
GitHub Actions 에서만 `GITHUB_HEAD_REF`·`GITHUB_REF_NAME` 을 보고 후보 이름을 복원한다.
로컬에서는 그 환경변수가 남아 있어도 Git 브랜치를 쓴다.

두 마이그레이션 디렉터리는 **번호가 서로 독립**이라 따로 본다.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_CONFIG = PROJECT_ROOT / "config" / "parallel_agents.json"
CANDIDATE_PREFIX = "cand/"
MIGRATION_DIRECTORIES = (
    PROJECT_ROOT / "src" / "capa_simulation" / "persistence" / "migrations",
    PROJECT_ROOT / "src" / "capa_simulation" / "persistence" / "equipment_migrations",
)
PARITY_REMAINDER = {"odd": 1, "even": 0}


def _agents() -> dict[str, dict[str, object]]:
    return dict(json.loads(AGENT_CONFIG.read_text(encoding="utf-8"))["agents"])


def _git(*args: str) -> str | None:
    """실패를 예외가 아니라 `None` 으로 돌려준다 — git 이 없거나 얕은 복제일 수 있다."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def _current_agent() -> str | None:
    """지금 후보 브랜치에 있으면 그 에이전트 이름."""
    branch = None
    if _in_github_actions():
        branch = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME")
    if not branch:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch or not branch.startswith(CANDIDATE_PREFIX):
        return None
    return branch.rsplit("/", 1)[-1]


def _in_github_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def _versions_added_against_main(directory: Path) -> list[int] | None:
    """main 과 갈라진 뒤 추가한 번호. 기준이나 차이를 조회하지 못하면 `None`.

    Actions 체크아웃은 로컬 main 없이 원격 추적 브랜치만 가져올 수 있다.
    """
    relative = directory.relative_to(PROJECT_ROOT).as_posix()
    base = _git("merge-base", "main", "HEAD") or _git("merge-base", "origin/main", "HEAD")
    if not base:
        return None
    listed = _git("diff", "--name-only", "--diff-filter=A", base, "HEAD", "--", relative)
    if listed is None:
        return None
    versions: list[int] = []
    for line in listed.splitlines():
        name = Path(line.strip()).name
        if name.endswith(".sql") and name[:4].isdigit():
            versions.append(int(name[:4]))
    return versions


def test_the_agent_config_assigns_distinct_parities() -> None:
    """설정 자체를 먼저 본다. 이 검사는 `main` 에서도 돌아 선언이 썩는 것을 막는다."""
    agents = _agents()
    assert agents, "에이전트 선언이 비어 있습니다."

    parities = {}
    for name, spec in agents.items():
        parity = spec.get("migration_parity")
        assert parity in PARITY_REMAINDER, f"{name}: 홀짝이 odd/even 이 아닙니다 — {parity!r}"
        parities.setdefault(parity, []).append(name)

    shared = {parity: names for parity, names in parities.items() if len(names) > 1}
    assert not shared, (
        f"두 에이전트가 같은 홀짝을 배정받았습니다. 그러면 나눠 갖는 뜻이 없어집니다:\n  {shared}"
    )


def test_new_migrations_match_the_branch_parity() -> None:
    agent = _current_agent()
    if agent is None:
        pytest.skip("후보 브랜치(cand/…)가 아닙니다 — 홀짝 배정 대상이 아닙니다.")

    agents = _agents()
    if agent not in agents:
        pytest.fail(
            f"브랜치 마지막 조각이 '{agent}' 인데 config/parallel_agents.json 에 없습니다. "
            f"아는 이름: {sorted(agents)}. 이름을 맞추거나 선언에 더하세요."
        )

    parity = str(agents[agent]["migration_parity"])
    expected = PARITY_REMAINDER[parity]

    offenders: list[str] = []
    for directory in MIGRATION_DIRECTORIES:
        versions = _versions_added_against_main(directory)
        if versions is None:
            message = (
                "`main` 또는 `origin/main` 기준의 마이그레이션 비교를 완료하지 못했습니다. "
                "Git 조회 오류와 기준 브랜치 이력을 확인하세요 — "
                "CI 는 `fetch-depth: 0` 으로 가져와야 합니다."
            )
            if _in_github_actions():
                pytest.fail(message)
            pytest.skip(message)
        offenders += [
            f"{directory.name}/{version:04d}" for version in versions if version % 2 != expected
        ]

    assert not offenders, (
        f"'{agent}' 는 {parity}(홀짝) 번호만 만듭니다. 아래는 그 밖입니다:\n"
        f"  {', '.join(offenders)}\n"
        "번호를 바꾸세요. 합친 뒤에는 바꿀 수 없습니다 — 러너가 버전으로 체크섬을 대조해서, "
        "그 번호가 이미 적용된 DB 에서 앱이 시작조차 못 하게 됩니다."
    )


@pytest.mark.parametrize(
    ("branch", "actions", "head_ref", "ref_name", "expected"),
    [
        ("cand/task/codex", "false", "cand/other/claude", "main", "codex"),
        ("main", "false", "cand/task/codex", "cand/task/codex", None),
        ("HEAD", "true", "cand/task/codex", "17/merge", "codex"),
        ("HEAD", "true", "", "cand/task/claude", "claude"),
        ("HEAD", "true", "fix/example", "17/merge", None),
    ],
)
def test_candidate_detection_uses_ci_refs_only_inside_actions(
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
    actions: str,
    head_ref: str,
    ref_name: str,
    expected: str | None,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", actions)
    monkeypatch.setenv("GITHUB_HEAD_REF", head_ref)
    monkeypatch.setenv("GITHUB_REF_NAME", ref_name)
    monkeypatch.setitem(globals(), "_git", lambda *_args: branch)

    assert _current_agent() == expected


@pytest.mark.parametrize("baseline_ref", ["main", "origin/main"])
def test_added_versions_use_an_available_main_ref(
    monkeypatch: pytest.MonkeyPatch, baseline_ref: str
) -> None:
    directory = MIGRATION_DIRECTORIES[0]
    relative = directory.relative_to(PROJECT_ROOT).as_posix()
    calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> str | None:
        calls.append(args)
        if args == ("merge-base", baseline_ref, "HEAD"):
            return "base-commit"
        if args == (
            "diff",
            "--name-only",
            "--diff-filter=A",
            "base-commit",
            "HEAD",
            "--",
            relative,
        ):
            return f"{relative}/0026_new_profile.sql\n{relative}/README.md"
        return None

    monkeypatch.setitem(globals(), "_git", fake_git)

    assert _versions_added_against_main(directory) == [26]
    assert calls[0] == ("merge-base", "main", "HEAD")
    assert (("merge-base", "origin/main", "HEAD") in calls) == (baseline_ref == "origin/main")


def test_non_candidate_ci_still_skips_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_HEAD_REF", "")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setitem(globals(), "_git", lambda *_args: "HEAD")

    with pytest.raises(pytest.skip.Exception, match="후보 브랜치"):
        test_new_migrations_match_the_branch_parity()


@pytest.mark.parametrize("failed_step", ["baseline", "diff"])
def test_candidate_ci_fails_when_the_migration_comparison_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, failed_step: str
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_HEAD_REF", "cand/task/codex")
    monkeypatch.setenv("GITHUB_REF_NAME", "17/merge")

    def fake_git(*args: str) -> str | None:
        if args == ("rev-parse", "--abbrev-ref", "HEAD"):
            return "HEAD"
        if args[0] == "merge-base" and failed_step == "diff":
            return "base-commit"
        return None

    monkeypatch.setitem(globals(), "_git", fake_git)

    # skip도 잡아야 기존의 조용한 건너뛰기가 이 회귀 테스트 자체를 건너뛰지 못한다.
    with pytest.raises((pytest.fail.Exception, pytest.skip.Exception)) as outcome:
        test_new_migrations_match_the_branch_parity()
    assert isinstance(outcome.value, pytest.fail.Exception), str(outcome.value)
    assert "비교" in str(outcome.value)
