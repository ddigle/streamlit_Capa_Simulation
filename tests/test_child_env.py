# Purpose: 좁은 환경 시험이 Windows 필수 변수만 더하고 손으로 지은 환경이 다시 생기지 않는지 본다.

from __future__ import annotations

import re
from pathlib import Path

import pytest
from child_env import narrow_child_env

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HAND_BUILT = re.compile(r"\benv=\{\s*[\"']")


def test_linux_gets_only_what_the_caller_chose(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEMROOT", "합성")

    assert narrow_child_env({"PYTHONPATH": "src"}, windows=False) == {"PYTHONPATH": "src"}


def test_windows_adds_the_process_variables_and_no_app_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYSTEMROOT", "합성")
    monkeypatch.setenv("CAPA_S3_BUCKET", "Demo_bucket")

    made = narrow_child_env({"PYTHONPATH": "src", "PATH": ""}, windows=True)

    assert made["SYSTEMROOT"] == "합성"
    assert made["PYTHONPATH"] == "src"
    assert made["PATH"] == "", "부르는 쪽이 고른 값이 이긴다"
    assert "CAPA_S3_BUCKET" not in made


def test_no_child_process_gets_a_hand_built_narrow_environment() -> None:
    """Windows 파이썬은 `SYSTEMROOT` 없이 첫 줄에서 죽는다 — 리터럴 env 는 사내에서야 드러난다."""
    sources = [*(PROJECT_ROOT / "tests").glob("*.py"), *(PROJECT_ROOT / "scripts").glob("*.py")]

    found = [
        path.name
        for path in sources
        if path.name != Path(__file__).name and HAND_BUILT.search(path.read_text(encoding="utf-8"))
    ]

    assert not found, f"tests/child_env.py 의 narrow_child_env 로 짓습니다: {found}"
