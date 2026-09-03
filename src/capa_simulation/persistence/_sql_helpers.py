# Purpose: DuckDB 프레임 저장·조회와 값 변환에 쓰는 공용 헬퍼를 제공한다.

"""DuckDB 프레임 저장·조회와 값 변환에 쓰는 공용 헬퍼를 제공한다."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import uuid4

import duckdb
import pandas as pd


def insert_frame(
    connection: duckdb.DuckDBPyConnection,
    *,
    schema: str,
    table_name: str,
    owner_column: str,
    owner_id: str,
    frame: pd.DataFrame,
    logical_name: str,
) -> None:
    target_columns = business_columns(connection, schema, table_name, owner_column)
    actual_columns = [str(column) for column in frame.columns]
    missing = [column for column in target_columns if column not in actual_columns]
    extra = [column for column in actual_columns if column not in target_columns]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"누락: {', '.join(missing)}")
        if extra:
            details.append(f"추가: {', '.join(extra)}")
        raise ValueError(f"{logical_name} 컬럼 계약이 일치하지 않습니다 ({'; '.join(details)}).")

    prepared = frame.reindex(columns=target_columns).copy()
    if "생산계획년월" in prepared.columns:
        prepared["생산계획년월"] = normalize_months(prepared["생산계획년월"], logical_name)
    prepared.insert(0, "source_row_no", range(1, len(prepared) + 1))
    prepared.insert(0, owner_column, owner_id)
    view_name = f"_incoming_{uuid4().hex}"
    connection.register(view_name, prepared)
    try:
        connection.execute(
            f"INSERT INTO {quote(schema)}.{quote(table_name)} BY NAME "
            f"SELECT * FROM {quote(view_name)}"
        )
    finally:
        connection.unregister(view_name)
    stored_count = connection.execute(
        f"SELECT COUNT(*) FROM {quote(schema)}.{quote(table_name)} WHERE {quote(owner_column)} = ?",
        [owner_id],
    ).fetchone()
    if stored_count is None or int(stored_count[0]) != len(frame):
        raise RuntimeError(f"{logical_name} 적재 행 수 검증에 실패했습니다.")


def load_frame(
    connection: duckdb.DuckDBPyConnection,
    *,
    schema: str,
    table_name: str,
    owner_column: str,
    owner_id: str,
) -> pd.DataFrame:
    columns = business_columns(connection, schema, table_name, owner_column)
    projection = ", ".join(quote(column) for column in columns)
    return connection.execute(
        f"SELECT {projection} FROM {quote(schema)}.{quote(table_name)} "
        f"WHERE {quote(owner_column)} = ? ORDER BY source_row_no",
        [owner_id],
    ).fetchdf()


def business_columns(
    connection: duckdb.DuckDBPyConnection,
    schema: str,
    table_name: str,
    owner_column: str,
) -> list[str]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ?
        ORDER BY ordinal_position
        """,
        [schema, table_name],
    ).fetchall()
    excluded = {owner_column, "source_row_no"}
    columns = [str(row[0]) for row in rows if str(row[0]) not in excluded]
    if not columns:
        raise RuntimeError(f"DuckDB 대상 테이블 계약을 찾을 수 없습니다: {schema}.{table_name}")
    return columns


def normalize_months(series: pd.Series, table_name: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.notna() & numeric.mod(1).eq(0)
    months = numeric.fillna(0).astype("int64")
    valid &= months.mod(100).between(1, 12)
    if not valid.all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    return months


def hash_tables(tables: Mapping[str, pd.DataFrame], names: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(names):
        frame = tables[name]
        digest.update(name.encode("utf-8"))
        digest.update("\x1f".join(str(column) for column in frame.columns).encode("utf-8"))
        digest.update(
            pd.util.hash_pandas_object(frame, index=False).to_numpy(dtype="uint64").tobytes()
        )
    return digest.hexdigest()


def require_tables(
    tables: Mapping[str, pd.DataFrame],
    required: Sequence[str],
    label: str,
) -> None:
    missing = [name for name in required if name not in tables]
    if missing:
        raise KeyError(f"{label} 테이블이 없습니다: {', '.join(missing)}")
    invalid = [name for name in required if not isinstance(tables[name], pd.DataFrame)]
    if invalid:
        raise TypeError(f"{label} 값이 DataFrame이 아닙니다: {', '.join(invalid)}")


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("DuckDB TIMESTAMP 결과가 datetime이 아닙니다.")
    return value


def as_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"DuckDB {label} 결과가 정수가 아닙니다.")
    return value


def required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label}은(는) 비어 있을 수 없습니다.")
    return normalized
