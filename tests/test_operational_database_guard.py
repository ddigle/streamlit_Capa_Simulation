# Purpose: 시험이 운영 DB 자리를 열면 열지 않고 실패로 남기는 시험 문지기(conftest)를 본다.

"""사내 관문(런북 4-3)은 운영 저장소에서 pytest 를 돈다 — 시험이 저장소 `data/` 의 운영 DB 를 열면
사내 DB 를 읽고 마이그레이션까지 건다. `tests/conftest.py` 의 문지기가 같은 프로세스의 모든
`duckdb.connect` 를 지켜, 운영 DB 자리(`settings.is_operational_database_place` — 시험이 갈아끼우기
전 저장소 경로로)를 열지 않고 멈추며 그 시험을 실패로 바꾼다(2026-11-12 사용자 답 ⑤-6 (가)).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest
from conftest import (
    _OPERATIONAL_OPENS,
    _REPOSITORY_DATA_DIR,
    _REPOSITORY_DATABASES,
    _operational_place,
)

import capa_simulation.settings as settings

TESTS = Path(__file__).resolve().parent

# 자식이 겨누는 자리 — 저장소 `data/` 아래(운영 자리)의 없는 파일을 읽기 전용으로. 문지기가 깨져도
# 자식은 사내 운영 DB 를 열지 않고 파일도 만들지 않는다(읽기 전용은 없는 파일을 만들지 않는다) —
# 이 시험도 사내 관문에서 운영 저장소를 놓고 돈다.
_PROBE = """
import duckdb
from conftest import _REPOSITORY_DATA_DIR

PLACE = _REPOSITORY_DATA_DIR / "operational-guard-probe-never-made.duckdb"


def swallow_the_refusal():
    try:
        duckdb.connect(str(PLACE), read_only=True)
    except Exception:
        pass
"""

_SWALLOWED_IN_A_TEST = (
    _PROBE
    + """

def test_opens_and_swallows():
    swallow_the_refusal()
"""
)

_SWALLOWED_AFTER_THE_LAST_TEST = (
    _PROBE
    + """
import pytest


@pytest.fixture(scope="session")
def opens_on_the_way_out():
    yield
    swallow_the_refusal()


def test_passes(opens_on_the_way_out):
    pass
"""
)


def test_opening_a_repository_database_is_refused_without_touching_it() -> None:
    """있는 운영 DB 를 여는 것도, 없는 자리에 새로 만드는 것도 열기 전에 멈춘다."""
    for path in _REPOSITORY_DATABASES:
        existed = path.exists()
        with pytest.raises(PermissionError):
            duckdb.connect(str(path), read_only=True)
        with pytest.raises(PermissionError):
            duckdb.connect(database=path)
        assert path.exists() == existed

    assert _OPERATIONAL_OPENS == [str(path) for path in _REPOSITORY_DATABASES for _ in range(2)]
    # 이 시험은 일부러 열어 봤다 — 끝의 실패 판정(`_no_operational_database_opened`)에 넘기지
    # 않는다.
    _OPERATIONAL_OPENS.clear()


def test_the_place_is_the_repository_even_when_a_test_moves_the_data_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """시험이 `settings.DATA_DIR` · DB 경로를 tmp 로 바꿔도 그 tmp 는 운영 자리가 아니고, 저장소
    `data/` 는 여전히 운영 자리다. 메모리 DB 는 막지 않는다."""
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "capa_simulation.duckdb")

    assert not _operational_place(tmp_path / "capa_simulation.duckdb")
    assert _operational_place(_REPOSITORY_DATA_DIR / "anything.duckdb")
    assert _operational_place(str(_REPOSITORY_DATABASES[1]))
    for memory in (":memory:", "", ":memory:named", None, 3):
        assert not _operational_place(memory)
    with duckdb.connect(str(tmp_path / "capa_simulation.duckdb")) as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)
    with duckdb.connect() as connection:
        assert connection.execute("SELECT 2").fetchone() == (2,)
    assert _OPERATIONAL_OPENS == []


def _child_pytest(folder: Path, body: str) -> subprocess.CompletedProcess[str]:
    """이 저장소의 `tests/conftest.py` 를 플러그인(`-p conftest`)으로 실은 자식 pytest — 문지기와
    끝 판정이 이 세션과 같은 코드다. 자식 폴더에는 conftest 를 두지 않는다(이름이 겹친다)."""
    (folder / "test_probe.py").write_text(body, encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if key != "PYTEST_ADDOPTS"}
    env["PYTHONPATH"] = os.pathsep.join(
        [str(TESTS), str(TESTS.parent / "src"), *filter(None, [env.get("PYTHONPATH")])]
    )
    return subprocess.run(
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


def test_a_test_that_swallows_the_refusal_still_fails(tmp_path: Path) -> None:
    """여는 쪽이 `except Exception` 으로 거절을 삼켜도 그 시험이 실패로 끝난다 — 시험 끝의
    autouse 판정(`_no_operational_database_opened`)이 붙든다."""
    finished = _child_pytest(tmp_path, _SWALLOWED_IN_A_TEST)

    assert finished.returncode == pytest.ExitCode.TESTS_FAILED, finished.stdout
    assert "시험이 운영 DB 자리를 열려 했습니다(열지 않음)" in finished.stdout
    # 판정은 시험 정리에서 나므로 그 시험이 「오류」 로 찍힌다 — 세션 끝 판정만 남았다면 오류 없이
    # 「1 passed」 뿐이다.
    assert "1 error" in finished.stdout.splitlines()[-1], finished.stdout
    assert not (_REPOSITORY_DATA_DIR / "operational-guard-probe-never-made.duckdb").exists()


def test_an_open_after_the_last_test_still_fails_the_session(tmp_path: Path) -> None:
    """마지막 시험의 판정 뒤(세션 범위 정리)에 열고 삼켜도 세션이 실패로 끝난다 — 시험은 통과로
    찍히지만 `pytest_sessionfinish` 가 종료 코드를 바꾼다."""
    finished = _child_pytest(tmp_path, _SWALLOWED_AFTER_THE_LAST_TEST)

    assert finished.returncode == pytest.ExitCode.TESTS_FAILED, finished.stdout
    assert "1 passed" in finished.stdout, finished.stdout
    assert "시험이 운영 DB 자리를 열려 했습니다(열지 않음)" in finished.stdout
