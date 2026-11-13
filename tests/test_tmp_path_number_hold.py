# Purpose: 보존 정책 failed 에서도 시험마다 tmp_path 이름이 겹치지 않는지(공용 정리 훅) 본다.

"""`tests/conftest.py` 의 `pytest_fixture_post_finalizer`(빈 폴더로 번호 붙잡기).

pytest 8.4 의 `tmp_path_retention_policy=failed` 는 통과한 시험의 `tmp_path` 를 그 자리에서
지우고, 지운 이름(시험 이름 앞 30자 + 번호)을 다음 시험에 다시 내준다. 경로를 키로 쓰는 프로세스
캐시가 앞 시험의 저장소를 돌려줘 뒤 시험이 깨진다. 조각 실행기가 그 정책을 쓰므로 공용 훅이
번호를 붙잡는지 자식 pytest 에 실제 정책을 걸어 본다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

# 두 시험 이름은 앞 30자가 같다 — pytest 가 같은 `tmp_path` 이름 줄기를 쓴다.
_TWO_TESTS_ONE_STEM = """
import os
from pathlib import Path


def _note(tmp_path):
    (tmp_path / "mark").write_text("x", encoding="utf-8")
    with open(os.environ["SEEN_TMP_PATHS"], "a", encoding="utf-8") as seen:
        seen.write(str(tmp_path) + "\\n")


def test_a_reused_tmp_path_name_never_comes_back_first(tmp_path):
    _note(tmp_path)


def test_a_reused_tmp_path_name_never_comes_back_second(tmp_path):
    _note(tmp_path)


def test_a_reused_tmp_path_name_never_comes_back_failing(tmp_path):
    _note(tmp_path)
    assert False, "실패한 시험의 폴더는 남는다"
"""


# 짝마다 앞 30자가 같다. 짝의 첫 시험은 훅이 시험 정리 순서만 보면 놓치는 꼴이다 — 같은 시험의 다른
# 준비가 정리에서 오류를 냄(A), `tmp_path` 를 `request.getfixturevalue` 로 늦게 받음(B), 준비 오류로
# 본문까지 못 감(C). 본문에서 건너뛴 시험(D)은 정책이 지우지 않는 꼴이다.
_PAIRS_THE_TEARDOWN_ORDER_MISSES = """
import os
from pathlib import Path

import pytest


def _note(tmp_path):
    (tmp_path / "mark").write_text("x", encoding="utf-8")
    with open(os.environ["SEEN_TMP_PATHS"], "a", encoding="utf-8") as seen:
        seen.write(str(tmp_path) + "\\n")


@pytest.fixture
def breaks_on_teardown(tmp_path):
    yield
    raise RuntimeError("정리 오류")


@pytest.fixture
def late_tmp_path(tmp_path):
    return tmp_path


@pytest.fixture
def breaks_on_setup(tmp_path):
    _note(tmp_path)
    raise RuntimeError("준비 오류")


def test_after_a_teardown_error_one_a(tmp_path, breaks_on_teardown):
    _note(tmp_path)


def test_after_a_teardown_error_one_b(tmp_path):
    _note(tmp_path)


def test_after_a_late_tmp_path_one_a(request):
    _note(request.getfixturevalue("late_tmp_path"))


def test_after_a_late_tmp_path_one_b(tmp_path):
    _note(tmp_path)


def test_after_a_setup_error_held_one_a(breaks_on_setup):
    pass


def test_after_a_setup_error_held_one_b(tmp_path):
    _note(tmp_path)


def test_after_a_skip_in_the_body_a(tmp_path):
    _note(tmp_path)
    pytest.skip("본문에서 건너뜀")


def test_after_a_skip_in_the_body_b(tmp_path):
    _note(tmp_path)
"""


def _child_pytest(
    folder: Path, probe: str, *options: str
) -> tuple[subprocess.CompletedProcess[str], list[Path]]:
    """이 저장소의 `tests/conftest.py` 를 플러그인(`-p conftest`)으로 실은 자식 pytest."""
    (folder / "test_probe.py").write_text(probe, encoding="utf-8")
    seen = folder / "seen.txt"
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    env["PYTHONIOENCODING"] = "utf-8"
    env["SEEN_TMP_PATHS"] = str(seen)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(TESTS), str(TESTS.parent / "src"), *filter(None, [env.get("PYTHONPATH")])]
    )
    finished = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "conftest",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(folder),
            f"--basetemp={folder / 'basetemp'}",
            *options,
            "test_probe.py",
        ],
        cwd=folder,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    paths = [Path(line) for line in seen.read_text(encoding="utf-8").splitlines()]
    return finished, paths


def test_the_failed_retention_never_hands_a_passed_tests_name_to_the_next(tmp_path: Path) -> None:
    finished, (first, second, failing) = _child_pytest(
        tmp_path, _TWO_TESTS_ONE_STEM, "-o", "tmp_path_retention_policy=failed"
    )

    assert finished.returncode == pytest.ExitCode.TESTS_FAILED, finished.stdout + finished.stderr
    assert len({first, second, failing}) == 3, (
        "지운 이름을 다시 내주면 경로 키 캐시가 앞 시험 것을 낸다"
    )
    # 통과한 시험의 파일은 정책대로 지워지고 빈 폴더만 번호를 붙잡는다. 실패한 시험은 그대로 남는다.
    for passed in (first, second):
        assert passed.is_dir() and not any(passed.iterdir())
    assert (failing / "mark").is_file()


def test_the_default_retention_is_left_as_it_was(tmp_path: Path) -> None:
    """기본 보존에서는 훅이 할 일이 없다 — 지운 것이 없으니 파일이 그대로다."""
    finished, paths = _child_pytest(tmp_path, _TWO_TESTS_ONE_STEM)

    assert finished.returncode == pytest.ExitCode.TESTS_FAILED, finished.stdout + finished.stderr
    assert len(set(paths)) == 3
    assert all((path / "mark").is_file() for path in paths)


def test_a_name_stays_held_when_the_test_order_alone_would_miss_it(tmp_path: Path) -> None:
    """정리 오류 · 늦게 받은 `tmp_path` · 준비 오류에도 번호를 붙잡는다 — 짝의 뒤 시험이 앞 시험의
    지워진 이름을 다시 받으면 경로 키 캐시가 앞 시험 것을 「조용히」 낸다."""
    finished, paths = _child_pytest(
        tmp_path, _PAIRS_THE_TEARDOWN_ORDER_MISSES, "-o", "tmp_path_retention_policy=failed"
    )

    assert finished.returncode == pytest.ExitCode.TESTS_FAILED, finished.stdout + finished.stderr
    assert len(paths) == 8, finished.stdout + finished.stderr
    assert len(set(paths)) == 8, f"지운 이름을 다시 받았다: {[path.name for path in paths]}"
    teardown_error, late, setup_error, skipped = paths[0], paths[2], paths[4], paths[6]
    # 정책은 call 이 통과했거나(정리 오류가 나도) call 까지 못 간(준비 오류) 시험의 것을 지운다.
    for removed in (teardown_error, late, setup_error):
        assert removed.is_dir() and not any(removed.iterdir()), removed.name
    # call 이 통과하지 못한 시험(실패 · 본문 건너뜀 · xfail)의 것은 남긴다.
    assert (skipped / "mark").is_file()
