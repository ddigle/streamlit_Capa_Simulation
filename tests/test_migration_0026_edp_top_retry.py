# Purpose: 0026 재이관이 원천 표기 대문자 `TOP` 을 실제로 집어내는지 러너 경로로 고정한다.

"""**`0014` 를 통과시킨 것이 바로 이 테스트의 부재다.**

`0014` 는 `trim("WF 구분") = 'Top'` 으로 맞댔는데 원천 표기는 대문자 `TOP` 이다
(`AGENTS.md` product_type 절, 2026-09-18 사용자 확인). 운영 데이터에서 한 행도 바꾸지
못했고, **로컬 합성 표본만 `Top` 이라 검사가 조용히 통과했다.** 표본이 원천과 다르면
검사가 결함을 덮는다 — 그래서 여기 고정하는 값은 로컬 표본 표기가 아니라 **원천 표기**다.

러너(`apply_migrations`)를 그대로 지나간다. 트랜잭션 안에서 TEMP VIEW 를 만드는 파일이라
SQL 만 떼어 돌리면 실제 적용 경로를 증명하지 못한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from capa_simulation.persistence.migration_runner import apply_migrations

RETRY_VERSION = 26
NBSP = " "
# `0014`·`0026` 이 손대는 표. 대표로 하나만 쓰지 않는 이유는 스키마마다 스코프 컬럼이
# 다르기 때문이다 — `ref_data` 는 `dataset_id`, `rev_data` 는 `revision_id` 다.
TARGET_TABLE = "rq_upeh"


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """빈 DB 에 전 마이그레이션을 적용한 연결. 스키마는 러너가 만든 것 그대로다."""
    con = duckdb.connect(str(tmp_path / "retry.duckdb"))
    apply_migrations(con)
    yield con
    con.close()


def _rewind_and_apply(con: duckdb.DuckDBPyConnection) -> None:
    """`0026` 만 되감아 다시 적용한다. 픽스처를 넣은 뒤 그 파일만 돌리는 방법이다."""
    con.execute("DELETE FROM app_meta.schema_migration WHERE version = ?", [RETRY_VERSION])
    applied = apply_migrations(con).applied
    assert RETRY_VERSION in applied


def _plant_source(
    con: duckdb.DuckDBPyConnection, row_no: int, product: str, product_type: str | None
) -> None:
    con.execute(
        "INSERT INTO raw_data.core_data (dataset_id, source_row_no, row_hash, "
        '"제품정보", "제품타입") VALUES (?, ?, ?, ?, ?)',
        ["ds1", row_no, f"h{row_no}", product, product_type],
    )


def _plant_target(con: duckdb.DuckDBPyConnection, row_no: int, product: str, division: str) -> None:
    con.execute(
        f'INSERT INTO ref_data.{TARGET_TABLE} (dataset_id, source_row_no, "제품정보", "WF 구분") '
        "VALUES (?, ?, ?, ?)",
        ["ds1", row_no, product, division],
    )


def _division(con: duckdb.DuckDBPyConnection, product: str) -> str:
    row = con.execute(
        f'SELECT "WF 구분" FROM ref_data.{TARGET_TABLE} WHERE "제품정보" = ?', [product]
    ).fetchone()
    assert row is not None, product
    return str(row[0])


def test_retry_converts_uppercase_top_from_the_source_product_map(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """원천 표기 `TOP` 을 집는다. `0014` 가 놓친 바로 그 자리다."""
    _plant_source(connection, 1, "EDP ONE", "EDP-TSV")
    _plant_target(connection, 1, "EDP ONE", "TOP")

    _rewind_and_apply(connection)

    assert _division(connection, "EDP ONE") == "Top_e"


def test_retry_leaves_hbm_rows_alone(connection: duckdb.DuckDBPyConnection) -> None:
    """HBM 의 `TOP` 은 원천 표기 그대로 남는다. 두 제품군이 같은 이름을 쓴다."""
    _plant_source(connection, 1, "HBM ONE", "HBM")
    _plant_target(connection, 1, "HBM ONE", "TOP")

    _rewind_and_apply(connection)

    assert _division(connection, "HBM ONE") == "TOP"


def test_retry_matches_product_names_through_the_derivation_normalization(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    r"""원천 이름과 파생 이름이 다르다. 정규화를 걸어야 조인이 붙는다.

    NBSP 가 함께 있는 것은 DuckDB 의 RE2 에서 `\s` 가 ASCII 공백만 뜻하기 때문이다 —
    파이썬 `re` 는 NBSP 를 잡으므로 그 한 글자에서 파생과 갈린다.
    """
    _plant_source(connection, 1, "EDP*_TWO_A", "EDP-TSV")
    _plant_source(connection, 2, f"EDP{NBSP}THREE", "EDP-TSV")
    _plant_target(connection, 1, "EDP TWO A", "TOP")
    _plant_target(connection, 2, "EDP THREE", "TOP")

    _rewind_and_apply(connection)

    assert _division(connection, "EDP TWO A") == "Top_e"
    assert _division(connection, "EDP THREE") == "Top_e"


def test_retry_skips_products_whose_type_is_split(connection: duckdb.DuckDBPyConnection) -> None:
    """한 제품이 두 타입을 가지면 판별할 수 없다. 건드리면 HBM 행까지 오염된다."""
    _plant_source(connection, 1, "MIXED", "EDP-TSV")
    _plant_source(connection, 2, "MIXED", "HBM")
    _plant_target(connection, 1, "MIXED", "TOP")

    _rewind_and_apply(connection)

    assert _division(connection, "MIXED") == "TOP"


def test_retry_ignores_blank_product_types_instead_of_dropping_the_product(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """빈 `제품타입` 은 「두 번째 타입」이 아니다. 세면 EDP 제품이 통째로 빠진다."""
    _plant_source(connection, 1, "EDP FOUR", "EDP-TSV")
    _plant_source(connection, 2, "EDP FOUR", "  ")
    _plant_source(connection, 3, "EDP FOUR", None)
    _plant_target(connection, 1, "EDP FOUR", "TOP")

    _rewind_and_apply(connection)

    assert _division(connection, "EDP FOUR") == "Top_e"


def test_retry_converts_rows_found_through_the_plan_product_type(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """계획(`rq_pkg_plan`)의 `제품타입` 으로도 찾는다. 대소문자를 가리지 않는다."""
    connection.execute(
        'INSERT INTO ref_data.rq_pkg_plan (dataset_id, source_row_no, "제품정보", "제품타입") '
        "VALUES (?, ?, ?, ?)",
        ["ds1", 1, "PLAN ONE", "edp-tsv"],
    )
    _plant_target(connection, 1, "PLAN ONE", "TOP")

    _rewind_and_apply(connection)

    assert _division(connection, "PLAN ONE") == "Top_e"


def test_retry_is_idempotent(connection: duckdb.DuckDBPyConnection) -> None:
    """두 번 돌려도 같다. 이미 바꾼 `Top_e` 는 `TOP` 대조에 걸리지 않는다."""
    _plant_source(connection, 1, "EDP FIVE", "EDP-TSV")
    _plant_target(connection, 1, "EDP FIVE", "TOP")

    _rewind_and_apply(connection)
    _rewind_and_apply(connection)

    assert _division(connection, "EDP FIVE") == "Top_e"
