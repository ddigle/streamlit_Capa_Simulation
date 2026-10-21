# Purpose: 리뷰 문서에 붙는 WF 구분·재이관 진단 스크립트 셋이 DB 경로 없이 이름만 찍는지 고정한다.

"""사내 런북은 이 셋의 출력을 리뷰 문서에 그대로 붙인다. 리뷰 문서는 사내에서 사외로 나가는
유일한 것이고, DB 절대경로에는 사내 사용자 폴더 이름이 든다. 그래서 같은 8장의 형제 스크립트
(`inspect_real_data_checks.py`·`inspect_revision_calculations.py`)처럼 파일 **이름만** 찍어야 한다.

세 갈래를 본다 — 파일이 없을 때, 빈 DB 를 열 때(정상 갈래의 첫 줄), 앱이 잠근 DB 를 열지 못할 때.
마지막 갈래의 DuckDB 문구는 DB 경로와 잠근 파이썬 실행 파일 경로를 함께 싣는다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import NoReturn

import duckdb
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import audit_top_remigration  # noqa: E402
import inspect_top_remigration  # noqa: E402
import inspect_wf_division  # noqa: E402

SCRIPTS = (inspect_wf_division, inspect_top_remigration, audit_top_remigration)
DB_NAME = "capa_simulation.duckdb"


def _point_at(monkeypatch: pytest.MonkeyPatch, script: ModuleType, tmp_path: Path) -> Path:
    path = tmp_path / DB_NAME
    monkeypatch.setattr(script, "DUCKDB_PATH", path)
    return path


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda module: module.__name__)
def test_missing_database_prints_only_the_file_name(
    script: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _point_at(monkeypatch, script, tmp_path)

    assert script.main() == 1

    out = capsys.readouterr().out
    assert out.splitlines() == [f"DB 파일이 없습니다: {DB_NAME}"]
    assert str(tmp_path) not in out


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda module: module.__name__)
def test_first_line_names_the_file_without_its_folder(
    script: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _point_at(monkeypatch, script, tmp_path)
    duckdb.connect(str(path)).close()

    assert script.main() == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0] == f"파일 {DB_NAME}"
    assert str(tmp_path) not in out


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda module: module.__name__)
def test_lock_failure_keeps_the_advice_but_drops_the_paths(
    script: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _point_at(monkeypatch, script, tmp_path)
    path.touch()
    holder = tmp_path / ".venv" / "bin" / "python"

    def _locked(*_args: object, **_kwargs: object) -> NoReturn:
        raise duckdb.IOException(
            f'IO Error: Could not set lock on file "{path}": '
            f"Conflicting lock is held in {holder} (PID 4242)"
        )

    monkeypatch.setattr(script.duckdb, "connect", _locked)

    assert script.main() == 1

    out = capsys.readouterr().out
    assert "앱이 떠 있으면 먼저 끄세요" in out
    assert "IOException" in out
    assert str(tmp_path) not in out
