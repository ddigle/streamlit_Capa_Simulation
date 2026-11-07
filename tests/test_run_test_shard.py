# Purpose: CI 시험 조각이 어떤 시험 파일도 빠뜨리거나 겹치지 않고 고르게 나뉘는지 본다.

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from js_runner import refuse_overlong_command_line

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import run_test_shard  # noqa: E402

PIECES = [1, 2, 3, 8, 16]


@pytest.mark.parametrize("pieces", PIECES)
def test_every_test_file_lands_in_exactly_one_shard(pieces: int) -> None:
    shards = [run_test_shard.shard_of(shard, pieces) for shard in range(1, pieces + 1)]

    flat = [path for shard in shards for path in shard]
    on_disk = sorted(path.relative_to(PROJECT_ROOT) for path in _collected_by_a_bare_pytest())
    assert sorted(flat) == on_disk
    assert len(flat) == len(set(flat)), "한 파일이 두 조각에 들면 CI 가 두 번 돈다"
    assert all(shards), "빈 조각은 pytest 가 종료 코드 5 로 빨개진다"


def _collected_by_a_bare_pytest() -> list[Path]:
    """조각 쪽 코드를 쓰지 않는다 — 같은 틀린 glob 이면 시험이 빠뜨림을 못 본다."""
    return [
        path
        for path in (PROJECT_ROOT / "tests").rglob("*.py")
        if path.name.startswith("test_") or path.name.endswith("_test.py")
    ]


def test_a_new_test_file_is_picked_up_without_touching_the_workflow(tmp_path: Path) -> None:
    (tmp_path / "tests" / "nested").mkdir(parents=True)
    for name in ("test_a.py", "nested/test_b.py", "nested/c_test.py", "helper.py"):
        (tmp_path / "tests" / name).write_text("# 합성\n", encoding="utf-8")

    assert [path.as_posix() for path in run_test_shard.discover_files(tmp_path)] == [
        "tests/nested/c_test.py",
        "tests/nested/test_b.py",
        "tests/test_a.py",
    ]


def test_the_shards_stay_within_one_big_file_of_even() -> None:
    """가장 무거운 조각도 평균에서 가장 큰 파일 하나 이상 벌어지지 않는다."""
    weights = {
        path: (PROJECT_ROOT / path).stat().st_size for path in run_test_shard.discover_files()
    }
    pieces = 8

    loads = [sum(weights[path] for path in shard) for shard in _split(weights, pieces)]

    assert max(loads) <= sum(loads) / pieces + max(weights.values())


def _split(weights: dict[Path, int], pieces: int) -> list[list[Path]]:
    return run_test_shard.split_files(weights, pieces)


def test_the_split_does_not_depend_on_the_input_order() -> None:
    weights = {Path(f"tests/test_{index}.py"): 100 for index in range(9)}
    backwards = dict(reversed(list(weights.items())))

    assert _split(weights, 4) == _split(backwards, 4)


def test_both_systems_check_python_files_out_with_the_same_size() -> None:
    """크기로 나누므로 줄바꿈이 OS 마다 다르면 같은 번호가 다른 파일이 된다."""
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()

    assert "*.py text eol=lf" in attributes


def test_each_shard_command_fits_the_windows_command_line() -> None:
    for shard in range(1, 9):
        refuse_overlong_command_line(
            run_test_shard.pytest_command(run_test_shard.shard_of(shard, 8))
        )


@pytest.mark.parametrize(
    "arguments",
    [["--shard", "0", "--of", "8"], ["--shard", "9", "--of", "8"], ["--shard", "1", "--of", "0"]],
)
def test_a_shard_outside_the_split_is_refused(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as caught:
        run_test_shard.main(arguments)

    assert caught.value.code == 2
    assert "--shard" in capsys.readouterr().err


def test_more_shards_than_files_stops_instead_of_collecting_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    pieces = len(run_test_shard.discover_files()) + 1

    assert run_test_shard.main(["--shard", str(pieces), "--of", str(pieces)]) == 2
    assert "파일이 없습니다" in capsys.readouterr().err


def test_the_list_mode_prints_posix_paths_and_runs_nothing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def must_not_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("--list 는 pytest 를 부르지 않는다")

    monkeypatch.setattr(subprocess, "run", must_not_run)

    assert run_test_shard.main(["--shard", "1", "--of", "8", "--list"]) == 0
    listed = capsys.readouterr().out.split()
    assert listed == [path.as_posix() for path in run_test_shard.shard_of(1, 8)]
    assert all(line.startswith("tests/") for line in listed)


@pytest.mark.parametrize("code", [0, 1])
def test_the_shard_runs_pytest_from_the_root_and_gives_back_its_code(
    code: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[list[str], Path]] = []

    def fake_run(
        command: list[str], *, cwd: Path, check: bool
    ) -> subprocess.CompletedProcess[bytes]:
        assert check is False
        seen.append((command, cwd))
        return subprocess.CompletedProcess(command, code)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run_test_shard.main(["--shard", "2", "--of", "8"]) == code
    [(command, cwd)] = seen
    assert cwd == PROJECT_ROOT
    assert command[:4] == [sys.executable, "-m", "pytest", "-q"]
    assert "faulthandler_timeout=600" in command
    expected = [path.as_posix() for path in run_test_shard.shard_of(2, 8)]
    assert command[-len(expected) :] == expected
