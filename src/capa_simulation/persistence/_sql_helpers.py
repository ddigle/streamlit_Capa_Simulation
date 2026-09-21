# Purpose: DuckDB 프레임 저장·조회·값 변환과 트랜잭션 경계에 쓰는 공용 헬퍼를 제공한다.

"""DuckDB 프레임 저장·조회·값 변환과 트랜잭션 경계에 쓰는 공용 헬퍼를 제공한다."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.services.month_filter import valid_month_mask

# DuckDB 기본 블록은 256 KiB 라서 행이 2,767개뿐인 첫 부팅 DB 도 24.5 MiB 를 차지한다.
# 16 KiB 로 만들면 같은 내용이 4.2 MiB 가 되고, 리비전 저장당 증가분도 2.5~9.5 MB 에서
# 0.6 MB 로 줄어든다. 값은 파일 생성 시점에 각인되며 기존 파일에서는 무시된다.
DUCKDB_BLOCK_SIZE = 16384
DUCKDB_CONNECT_CONFIG: dict[str, str | bool | int | float | list[str]] = {
    "default_block_size": DUCKDB_BLOCK_SIZE
}


def connect(database_path: Path) -> duckdb.DuckDBPyConnection:
    """같은 파일에 붙는 모든 연결이 동일한 configuration 을 쓰도록 한 곳에서 연다."""
    # configuration 이 다른 연결이 하나라도 섞이면 DuckDB 가 "Can't open a connection to
    # same database file with a different configuration" 로 연결 자체를 거부한다.
    # 그래서 read_only 도 쓰지 않고, 설정도 여기서만 만든다.
    return duckdb.connect(str(database_path), config=DUCKDB_CONNECT_CONFIG)


@contextmanager
def pinned_connections(*database_paths: Path) -> Iterator[None]:
    """블록이 도는 동안 DB 파일마다 유휴 연결 하나를 잡아 둔다.

    DuckDB 는 한 프로세스 안에서 같은 파일의 인스턴스를 공유한다. 연결이 하나라도 열려
    있으면 다음 `connect()` 는 인스턴스를 새로 만들지 않아 0.2ms 로 끝나고, 없으면 48ms 다.
    작업별 연결을 여닫는 설계는 그대로 두고, app.py 가 rerun 한 번을 이 블록으로 감싸
    사이드바 3콜이 인스턴스를 세 번 만들던 것(161ms)을 한 번(핀 48ms + 10ms)으로 줄인다.

    rerun 이 끝나면 풀린다. 상시 앵커를 두지 않는 이유: 배치가 같은 파일을 갱신하는
    환경에서는 rerun 사이 틈이 있어야 하고(Windows 는 교체 실패, Linux 는 옛 inode 를 계속
    읽는다), 핀이 닫히며 인스턴스가 내려갈 때 WAL 체크포인트가 돈다.

    열지 못하는 파일(다른 프로세스의 잠금, 없는 폴더)은 건너뛴다. 뒤의 실제 연결이 같은
    오류를 내고 그 자리의 안내가 처리하므로 여기서 판단하지 않는다.
    """
    pins: list[duckdb.DuckDBPyConnection] = []
    for database_path in database_paths:
        try:
            pins.append(connect(database_path))
        except duckdb.Error:
            continue
    try:
        yield
    finally:
        for pin in reversed(pins):
            pin.close()


@contextmanager
def transaction(connection: duckdb.DuckDBPyConnection) -> Iterator[None]:
    """쓰기 한 묶음을 트랜잭션 경계로 감싼다. 예외가 나면 되돌리고 그대로 올린다.

    두 Repository 의 쓰기 경계와 마이그레이션 적용이 같은 한 벌을 쓴다 — 경계가 여러 벌로
    갈려 있으면 한쪽만 고쳐져도 아무 데서도 드러나지 않는다.
    """
    connection.execute("BEGIN TRANSACTION")
    try:
        yield
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def insert_by_name(
    connection: duckdb.DuckDBPyConnection,
    *,
    schema: str,
    table_name: str,
    frame: pd.DataFrame,
) -> None:
    """임시 뷰 하나를 걸어 컬럼 이름으로 넣고, 무슨 일이 있어도 뷰를 되돌린다.

    뷰 이름이 겹치면 같은 연결의 다른 적재가 엉키므로 호출마다 uuid 로 만든다.
    """
    view_name = f"_incoming_{uuid4().hex}"
    connection.register(view_name, frame)
    try:
        connection.execute(
            f"INSERT INTO {quote(schema)}.{quote(table_name)} BY NAME "
            f"SELECT * FROM {quote(view_name)}"
        )
    finally:
        connection.unregister(view_name)


def insert_profile_header(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    *,
    version: int,
    source: str,
) -> None:
    """시나리오와 분리된 공용 프로필의 헤더 한 행을 넣는다."""
    connection.execute(
        f"INSERT INTO app_meta.{quote(table)} (profile_id, version, source) VALUES (1, ?, ?)",
        [version, source],
    )


def load_profile_header(
    connection: duckdb.DuckDBPyConnection,
    table: str,
) -> tuple[int, str, datetime] | None:
    """공용 프로필 헤더 한 행(version·source·updated_at). 한 번도 저장하지 않았으면 None."""
    row = connection.execute(
        f"""
        SELECT version, source, updated_at
        FROM app_meta.{quote(table)}
        WHERE profile_id = 1
        """
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), str(row[1]), row[2]


def reset_profile(
    connection: duckdb.DuckDBPyConnection,
    header_table: str,
    *detail_tables: str,
) -> int:
    """공용 프로필의 현재본을 지우고 다음 version 을 돌려준다. 쓰기 트랜잭션 안에서만 부른다.

    상세 표를 먼저, 헤더를 나중에 지운다. 헤더 INSERT 는 호출자가 그대로 쥐고 있으므로
    행 0건(전체 해제) 저장에서도 version 은 올라간다.
    """
    row = connection.execute(
        f"SELECT version FROM app_meta.{quote(header_table)} WHERE profile_id = 1"
    ).fetchone()
    for table in detail_tables:
        connection.execute(f"DELETE FROM app_meta.{quote(table)} WHERE profile_id = 1")
    connection.execute(f"DELETE FROM app_meta.{quote(header_table)} WHERE profile_id = 1")
    return 1 if row is None else int(row[0]) + 1


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
    insert_by_name(connection, schema=schema, table_name=table_name, frame=prepared)
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
    # information_schema.columns 는 카탈로그 전체를 훑어 호출당 4~6ms 다. load 16회·save 28회가
    # 부르므로 리비전 적재의 22% 였다. PRAGMA table_info 는 표 하나만 봐 0.5ms 다. 표가
    # 없으면 빈 결과가 아니라 CatalogException 이므로 기존 RuntimeError 계약으로 되돌린다.
    try:
        rows = connection.execute(
            f"PRAGMA table_info({quote(schema)}.{quote(table_name)})"
        ).fetchall()
    except duckdb.CatalogException:
        rows = []
    excluded = {owner_column, "source_row_no"}
    # 행은 (cid, name, type, ...). cid 순서가 컬럼 선언 순서다.
    columns = [
        str(row[1])
        for row in sorted(rows, key=lambda row: int(row[0]))
        if str(row[1]) not in excluded
    ]
    if not columns:
        raise RuntimeError(f"DuckDB 대상 테이블 계약을 찾을 수 없습니다: {schema}.{table_name}")
    return columns


def normalize_months(series: pd.Series, table_name: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if not valid_month_mask(numeric).all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    return numeric.astype("int64")


def _frame_digest_parts(frame: pd.DataFrame) -> tuple[bytes, bytes]:
    """해시에 먹이는 바이트 두 토막(컬럼 이름, 행 값).

    저장된 `reference_hash`·설비 해시가 이 순서로 만들어진 감사값이므로 바꾸지 않는다.
    """
    return (
        "\x1f".join(str(column) for column in frame.columns).encode("utf-8"),
        pd.util.hash_pandas_object(frame, index=False).to_numpy(dtype="uint64").tobytes(),
    )


def hash_tables(tables: Mapping[str, pd.DataFrame], names: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(names):
        digest.update(name.encode("utf-8"))
        for part in _frame_digest_parts(tables[name]):
            digest.update(part)
    return digest.hexdigest()


def hash_frame(frame: pd.DataFrame) -> str:
    """표 하나의 감사 해시. `hash_tables` 와 같은 바이트 열을 쓴다."""
    digest = hashlib.sha256()
    for part in _frame_digest_parts(frame):
        digest.update(part)
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
