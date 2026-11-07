# Purpose: 스크립트가 표준 오류를 UTF-8 로 돌려도 현지 인코딩 바이트가 뒤 시험을 깨지 않는지 본다.

"""자식 pytest 로 본다 — 지키는 쪽이 망가지면 이 세션의 뒤 시험이 전부 깨지므로 여기서 재현하지
않는다."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from _pytest.capture import EncodedFile

TESTS = Path(__file__).resolve().parent

_SPREADS = """
import os
import sys


def test_a_script_switches_the_console_to_utf8():
    sys.stderr.reconfigure(encoding="utf-8")


def test_local_bytes_reach_the_capture_file():
    os.write(2, "현재 연결은".encode("cp949") + b"\\n")


def test_the_next_one_is_not_hit():
    pass
"""

_GUARD = f"""
import sys

sys.path.insert(0, {str(TESTS)!r})

from capture_guard import keep_capture_tolerant

keep_capture_tolerant()
"""


def _child_pytest(folder: Path) -> subprocess.CompletedProcess[str]:
    (folder / "test_spreads.py").write_text(_SPREADS, encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if key != "PYTEST_ADDOPTS"}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--rootdir", str(folder)],
        cwd=folder,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def test_local_bytes_stay_in_one_report_with_the_guard(tmp_path: Path) -> None:
    (tmp_path / "conftest.py").write_text(_GUARD, encoding="utf-8")

    finished = _child_pytest(tmp_path)

    assert finished.returncode == 0, finished.stdout
    assert "3 passed" in finished.stdout


def test_without_the_guard_the_next_tests_fail_in_setup(tmp_path: Path) -> None:
    """지키는 까닭 — pytest 를 올려 이 시험이 깨지면 지키는 쪽을 걷어도 되는지 본다."""
    finished = _child_pytest(tmp_path)

    assert finished.returncode != 0
    assert "UnicodeDecodeError" in finished.stdout
    assert "ERROR test_spreads.py::test_the_next_one_is_not_hit" in finished.stdout


def test_this_session_keeps_its_capture_file_tolerant() -> None:
    if not isinstance(sys.stderr, EncodedFile):
        pytest.skip("붙잡기를 끈 실행(-s)")

    sys.stderr.reconfigure(encoding="utf-8")

    assert sys.stderr.errors == "replace"
