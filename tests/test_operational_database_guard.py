# Purpose: 시험이 운영 DB 자리를 열면 열지 않고 실패로 남기는 시험 문지기(conftest)를 본다.

"""사내 관문(런북 4-3)은 운영 저장소에서 pytest 를 돈다 — 시험이 저장소 `data/` 의 운영 DB 를 열면
사내 DB 를 읽고 마이그레이션까지 건다. `tests/conftest.py` 의 문지기가 같은 프로세스의 모든
`duckdb.connect` 를 지켜, 운영 DB 자리(`settings.is_operational_database_place` — 시험이 갈아끼우기
전 저장소 경로로)를 열지 않고 멈추며 그 시험을 실패로 바꾼다(2026-11-12 사용자 답 ⑤-6 (가)).
"""

from __future__ import annotations

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
