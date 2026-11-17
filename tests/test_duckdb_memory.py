# Purpose: DuckDB 메모리 한도 칸의 판정 · 연결 설정과 핀이 닫힐 때의 DB 메모리 표본을 지킨다.

"""`persistence/duckdb_memory.py` 와 `_sql_helpers` 의 연결 설정 · 핀 닫기 자리.

값이 없으면 연결 설정이 이 칸이 생기기 전과 같다(DuckDB 기본). 바른 값은 DuckDB 가 그대로 받고,
틀린 값(꼴 · 범위)은 넣지 않는다. 환경변수는 import 때 한 번 읽으므로 새 프로세스로 본다. 표본은
핀을 닫기 직전에 그 핀으로 읽어 새 연결을 열지 않는다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import duckdb
import pytest

from capa_simulation.persistence import duckdb_memory
from capa_simulation.persistence._sql_helpers import (
    DUCKDB_BLOCK_SIZE,
    connect,
    pinned_connections,
)
from capa_simulation.persistence.duckdb_memory import (
    MEMORY_LIMIT_ENV,
    MIB,
    PROBLEM_FORM,
    PROBLEM_RANGE,
    database_key,
    memory_limit_config,
    memory_limit_setting,
    memory_sample,
    observe,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _fresh_samples() -> Iterator[None]:
    duckdb_memory.reset_samples()
    yield
    duckdb_memory.reset_samples()


@pytest.mark.parametrize("environ", [{}, {MEMORY_LIMIT_ENV: ""}, {MEMORY_LIMIT_ENV: "   "}])
def test_no_value_leaves_the_connect_config_as_it_was(environ: dict[str, str]) -> None:
    """없음 · 빈 값은 연결 설정에 아무것도 더하지 않는다 — DuckDB 기본 그대로다."""
    setting = memory_limit_setting(environ)

    assert (setting.raw, setting.value, setting.problem) == (None, None, None)
    assert memory_limit_config(setting) == {}


@pytest.mark.parametrize(
    ("raw", "value", "limit_bytes"),
    [
        ("256MiB", "256MiB", 256 * MIB),
        (" 256 mib ", "256MiB", 256 * MIB),
        ("0.5GiB", "0.5GiB", 512 * MIB),
        ("300mb", "300MB", 300 * 1000**2),
        ("64MiB", "64MiB", 64 * MIB),
        ("1TiB", "1TiB", 1024**4),
        ("000256MiB", "000256MiB", 256 * MIB),
        ("256.50MiB", "256.50MiB", int(256.5 * MIB)),
    ],
)
def test_a_value_in_form_goes_to_duckdb(
    tmp_path: Path, raw: str, value: str, limit_bytes: int
) -> None:
    """수 + 단위는 단위 철자만 맞춰 그대로 넘기고, DuckDB 가 그 값으로 연다."""
    setting = memory_limit_setting({MEMORY_LIMIT_ENV: raw})

    assert (setting.value, setting.limit_bytes, setting.problem) == (value, limit_bytes, None)
    assert memory_limit_config(setting) == {"memory_limit": value}
    config: dict[str, Any] = {
        "default_block_size": DUCKDB_BLOCK_SIZE,
        **memory_limit_config(setting),
    }
    connection = duckdb.connect(str(tmp_path / "limit.duckdb"), config=config)
    try:
        connection.execute("create table t as select range as i from range(1000)")
        row = connection.execute("select current_setting('memory_limit')").fetchone()
    finally:
        connection.close()
    assert row is not None
    if value == "256MiB":
        assert row[0] == "256.0 MiB"


@pytest.mark.parametrize(
    ("raw", "problem"),
    [
        ("256", PROBLEM_FORM),
        ("80%", PROBLEM_FORM),
        ("none", PROBLEM_FORM),
        ("-1", PROBLEM_FORM),
        ("2 56MiB", PROBLEM_FORM),
        ("256MiB;", PROBLEM_FORM),
        ("1KB", PROBLEM_RANGE),
        ("63MiB", PROBLEM_RANGE),
        ("2TiB", PROBLEM_RANGE),
        ("99999999999999999999GB", PROBLEM_RANGE),
        pytest.param("1" * 400 + "MiB", PROBLEM_RANGE, id="400-digits"),
        pytest.param("\uff12\uff15\uff16MiB", PROBLEM_FORM, id="fullwidth-digits"),
        pytest.param("\u0662\u0665\u0666MiB", PROBLEM_FORM, id="arabic-indic-digits"),
        pytest.param("256M\u0131B", PROBLEM_FORM, id="dotless-i-unit"),
        pytest.param("256\u3000MiB", PROBLEM_FORM, id="ideographic-space"),
    ],
)
def test_a_value_out_of_form_or_range_is_left_out(raw: str, problem: str) -> None:
    """틀린 값은 넣지 않는다 — 꼴이 맞아도 너무 작으면 DuckDB 가 첫 표에서 메모리 부족으로
    멈추고(모든 DB 열기 실패), 너무 크면 DuckDB 가 거절한다. 수는 ASCII 숫자만 받는다 — 전각 ·
    아라비아 숫자는 `float` 이 읽어도 DuckDB 가 거절하고, 끝없이 긴 수는 무한대라 범위 밖이다
    (판정은 import 때 돌아 예외를 내지 않는다)."""
    setting = memory_limit_setting({MEMORY_LIMIT_ENV: f" {raw} "})

    assert (setting.raw, setting.value, setting.problem) == (raw, None, problem)
    assert memory_limit_config(setting) == {}


def test_every_unit_with_ascii_digits_in_range_is_taken_by_duckdb(tmp_path: Path) -> None:
    """받는 꼴은 DuckDB 가 받는 꼴의 부분이다 — 단위마다 앞 0 · 소수 · 긴 자리를 붙여도 범위 안이면
    DuckDB 가 그 값으로 연다(DuckDB 판을 올려 파서가 좁아지면 여기서 깨진다)."""
    numbers = ("256", "000256", "256.0", "256.25", "256." + "0" * 30, "0" * 30 + "256")
    taken = 0
    for unit in ("KB", "MB", "GB", "TB", "KiB", "MiB", "GiB", "TiB"):
        for number in numbers:
            setting = memory_limit_setting({MEMORY_LIMIT_ENV: f"{number}{unit}"})
            if setting.value is None:
                continue
            taken += 1
            connection = duckdb.connect(
                str(tmp_path / f"unit-{taken}.duckdb"),
                config={"default_block_size": DUCKDB_BLOCK_SIZE, **memory_limit_config(setting)},
            )
            connection.close()
    assert taken >= 12


def _config_in_a_fresh_process(value: str | None, database: Path) -> dict[str, Any]:
    """새 프로세스가 import 때 지은 `DUCKDB_CONNECT_CONFIG` — 그 설정으로 `connect()` 가 파일 하나를
    열어 본 뒤에 돌려준다(DuckDB 가 거절하는 값이 들어갔으면 여기서 깨진다)."""
    environ = {name: text for name, text in os.environ.items() if name != MEMORY_LIMIT_ENV}
    if value is not None:
        environ[MEMORY_LIMIT_ENV] = value
    environ["PYTHONPATH"] = os.pathsep.join(
        [str(PROJECT_ROOT / "src"), *filter(None, [os.environ.get("PYTHONPATH")])]
    )
    code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from capa_simulation.persistence import _sql_helpers\n"
        "_sql_helpers.connect(Path(sys.argv[1])).close()\n"
        "print(json.dumps(_sql_helpers.DUCKDB_CONNECT_CONFIG))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code, str(database)],
        env=environ,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return cast(dict[str, Any], json.loads(done.stdout.strip().splitlines()[-1]))


def test_the_connect_config_reads_the_variable_once_at_import(tmp_path: Path) -> None:
    """없으면 이 칸이 생기기 전 설정 그대로, 바른 값은 `memory_limit` 하나가 더해지고, 틀린 값은
    빠진다. 두 DB 가 이 설정 한 벌을 쓴다 — 한도는 DB 마다 같은 값이다. 전각 숫자(DuckDB 가
    거절)와 끝없이 긴 수(무한대)도 빠져 import 와 연결이 그대로 선다 — 동기화 `boot-pull` 도 같은
    import 를 거친다."""
    base = {"default_block_size": DUCKDB_BLOCK_SIZE}
    cases: list[tuple[str | None, dict[str, Any]]] = [
        (None, base),
        ("256MiB", {**base, "memory_limit": "256MiB"}),
        ("80%", base),
        ("\uff12\uff15\uff16MiB", base),
        ("1" * 400 + "MiB", base),
    ]
    for index, (value, expected) in enumerate(cases):
        database = tmp_path / f"fresh-{index}.duckdb"
        assert _config_in_a_fresh_process(value, database) == expected, value


def _counting(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    opened: list[str] = []
    real_connect = duckdb.connect

    def counted(database: Any = ":memory:", *args: Any, **kwargs: Any) -> Any:
        opened.append(str(database))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", counted)
    return opened


def test_the_pin_release_samples_the_memory_without_a_new_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """회차 끝(가장 바깥 핀을 닫기 직전)에 그 핀으로 읽는다 — 연결 수가 늘지 않는다."""
    database = tmp_path / "sample.duckdb"
    opened = _counting(monkeypatch)

    with pinned_connections(database):
        connection = connect(database)
        connection.execute(
            "create table t as select range as i, 'x' || range as s from range(50000)"
        )
        connection.execute("select count(distinct s) from t").fetchone()
        connection.close()
        assert memory_sample(database) is None
        before = len(opened)

    assert len(opened) == before
    sample = memory_sample(database)
    assert sample is not None and sample.count == 1
    assert sample.last_bytes > 0 and sample.peak_bytes == sample.last_bytes
    assert sample.limit
    monkeypatch.chdir(tmp_path)
    assert memory_sample("sample.duckdb") == sample


class _Result:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None


class _FakeConnection:
    """`duckdb_memory()` 행과 한도 글을 돌려주는 대역 — 한도를 몇 번 물었는지 센다."""

    def __init__(self, used: int, temporary: int) -> None:
        self.rows: list[tuple[Any, ...]] = [(used, temporary), (None, 0)]
        self.limit_asked = 0

    def execute(self, sql: str) -> _Result:
        if "duckdb_memory" in sql:
            return _Result(self.rows)
        self.limit_asked += 1
        return _Result([("256.0 MiB",)])


def test_samples_keep_the_last_and_the_peak_and_ask_the_limit_once() -> None:
    key = database_key("demo_sample.duckdb")
    first, second = _FakeConnection(10 * MIB, 0), _FakeConnection(4 * MIB, 2 * MIB)

    observe(key, cast(duckdb.DuckDBPyConnection, first))
    observe(key, cast(duckdb.DuckDBPyConnection, second))

    sample = memory_sample("demo_sample.duckdb")
    assert sample is not None
    assert (sample.last_bytes, sample.peak_bytes, sample.peak_temporary_bytes) == (
        4 * MIB,
        10 * MIB,
        2 * MIB,
    )
    assert (sample.limit, sample.count) == ("256.0 MiB", 2)
    assert (first.limit_asked, second.limit_asked) == (1, 0)


def test_the_sample_carries_the_limit_duckdb_applies(tmp_path: Path) -> None:
    """한도 글은 DuckDB 가 실제로 쓰는 값이다 — 한도 칸을 넣은 연결이면 그 값이 보인다."""
    path = tmp_path / "limited.duckdb"
    config: dict[str, Any] = {"default_block_size": DUCKDB_BLOCK_SIZE, "memory_limit": "64MiB"}
    connection = duckdb.connect(str(path), config=config)
    try:
        observe(database_key(path), connection)
    finally:
        connection.close()

    sample = memory_sample(path)
    assert sample is not None and sample.limit == "64.0 MiB"


def test_a_broken_connection_is_skipped_without_raising(tmp_path: Path) -> None:
    """진단은 회차를 멈추지 않는다 — 닫힌 연결이면 표본 없이 지나간다."""
    path = tmp_path / "closed.duckdb"
    connection = duckdb.connect(str(path), config={"default_block_size": DUCKDB_BLOCK_SIZE})
    connection.close()

    observe(database_key(path), connection)

    assert memory_sample(path) is None
