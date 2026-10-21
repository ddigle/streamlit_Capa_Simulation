# Purpose: 리뷰 문서에 붙는 WF 구분·재이관 진단 스크립트 셋이 DB 경로 없이 이름만 찍는지 고정한다.

"""사내 런북은 이 셋의 출력을 리뷰 문서에 그대로 붙인다. 리뷰 문서는 사내에서 사외로 나가는
유일한 것이고, DB 절대경로에는 사내 사용자 폴더 이름이 든다. 그래서 같은 8장의 형제 스크립트
(`inspect_real_data_checks.py`·`inspect_revision_calculations.py`)처럼 파일 **이름만** 찍어야 한다.

세 갈래를 본다 — 파일이 없을 때, 빈 DB 를 열 때(정상 갈래의 첫 줄), 앱이 잠근 DB 를 열지 못할 때.
마지막 갈래의 DuckDB 문구는 DB 경로와 잠근 파이썬 실행 파일 경로를 함께 싣는다.
`inspect_wf_division` 은 하나 더 — 쉬는 사용자 앱이 프로세스로 보일 때 DB 를 열지 않고 고정 문구
한 줄로 멈춘다.
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
import check_deploy_screens  # noqa: E402
import inspect_top_remigration  # noqa: E402
import inspect_wf_division  # noqa: E402

SCRIPTS = (inspect_wf_division, inspect_top_remigration, audit_top_remigration)
DB_NAME = "capa_simulation.duckdb"


def _point_at(monkeypatch: pytest.MonkeyPatch, script: ModuleType, tmp_path: Path) -> Path:
    path = tmp_path / DB_NAME
    monkeypatch.setattr(script, "DUCKDB_PATH", path)
    # 사용자 앱 프로세스 훑기(`inspect_wf_division`)는 이 기계에 무엇이 떠 있는지에 달렸다 — 막는다.
    monkeypatch.setattr(check_deploy_screens, "running_app_count", lambda *_a, **_k: 0)
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


def test_a_resting_user_app_stops_the_wf_division_count_before_it_opens_the_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """앱은 rerun 동안만 DB 를 쥐므로 쉬는 앱은 잠금 갈래에 안 잡힌다 — 프로세스를 먼저
    본다(런북 8장 뒤에 돌린다). 열지 않았으니 예외 종류 줄도 없다."""
    path = _point_at(monkeypatch, inspect_wf_division, tmp_path)
    duckdb.connect(str(path)).close()
    monkeypatch.setattr(check_deploy_screens, "running_app_count", lambda *_a, **_k: 1)

    def _must_not_open(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("사용자 앱이 떠 있으면 DB 를 열지 않는다")

    monkeypatch.setattr(duckdb, "connect", _must_not_open)

    assert inspect_wf_division.main() == 1

    out = capsys.readouterr().out
    assert out.splitlines() == [
        "사용자 앱이 떠 있습니다 — DB 는 열지 않았습니다. 앱을 끈 뒤 다시 칩니다(런북 1-1)."
    ]
