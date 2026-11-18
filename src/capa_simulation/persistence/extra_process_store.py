# Purpose: 부대공정 판 내용 · 판 이력 · 데이터셋 출처(마이그레이션 0037)의 읽기와 넣기 SQL 을
# 담당한다.

"""부대공정 판 표의 SQL. 연결과 트랜잭션은 저장소(`repository.DuckDBScenarioRepository`)가 소유한다.

판 이력은 넣기만 하고(append-only) 마지막 줄이 지금 상태다. 판 내용은 본문 sha256 하나에 한 벌만
둔다. 데이터셋 출처는 새 데이터셋을 만드는 저장(등록 · 복제 · 파생 저장 · 얹기)이 같은 트랜잭션에서
넣는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import duckdb

from capa_simulation.persistence.models import (
    EXTRA_KIND_OFF,
    ExtraProcessProvenance,
    ExtraProcessState,
    ExtraProcessVersion,
)

_VERSION_COLUMNS = (
    "seq",
    "kind",
    "version_no",
    "sha256",
    "created_at",
    "applied_by",
    "process_count",
    "row_counts",
    "source_place",
    "s3_key",
    "s3_etag",
    "s3_last_modified",
    "byte_size",
    "base_scenario_ref",
    "base_revision_ref",
    "s3_write_result",
)


class ExtraProcessMoved(ValueError):
    """화면이 본 판 이력의 마지막 줄 뒤에 다른 쓰기가 끼었다 — 쓰지 않았다."""

    def __init__(self, expected: int, current: int) -> None:
        super().__init__(
            f"부대공정 판이 그 사이 바뀌었습니다(본 차례 {expected} · 지금 {current}) — 화면을 "
            "새로 읽고 다시 누르세요."
        )
        self.expected = expected
        self.current = current


def load_state(connection: duckdb.DuckDBPyConnection) -> ExtraProcessState:
    """판 이력 전체(오래된 차례)."""
    rows = connection.execute(
        f"SELECT {', '.join(_VERSION_COLUMNS)} FROM app_meta.extra_process_version ORDER BY seq"
    ).fetchall()
    return ExtraProcessState(tuple(_version(row) for row in rows))


def _version(row: Sequence[object]) -> ExtraProcessVersion:
    values = dict(zip(_VERSION_COLUMNS, row, strict=True))
    return ExtraProcessVersion(
        seq=int(str(values["seq"])),
        kind=str(values["kind"]),
        version_no=_optional_int(values["version_no"]),
        sha256=_optional_text(values["sha256"]),
        created_at=_timestamp(values["created_at"]),
        applied_by=_optional_text(values["applied_by"]),
        process_count=_optional_int(values["process_count"]),
        row_counts=_optional_text(values["row_counts"]),
        source_place=_optional_text(values["source_place"]),
        s3_key=_optional_text(values["s3_key"]),
        s3_etag=_optional_text(values["s3_etag"]),
        s3_last_modified=_optional_timestamp(values["s3_last_modified"]),
        byte_size=_optional_int(values["byte_size"]),
        base_scenario_ref=_optional_text(values["base_scenario_ref"]),
        base_revision_ref=_optional_text(values["base_revision_ref"]),
        s3_write_result=_optional_text(values["s3_write_result"]),
    )


def _optional_int(value: object) -> int | None:
    return None if value is None else int(str(value))


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    raise TypeError(f"시각 칸이 시각이 아닙니다: {value!r}")


def _optional_timestamp(value: object) -> datetime | None:
    return None if value is None else _timestamp(value)


def load_content(connection: duckdb.DuckDBPyConnection, sha256: str) -> bytes:
    """판 내용(양식 ZIP 바이트). 없으면 `KeyError`."""
    row = connection.execute(
        "SELECT pack_bytes FROM app_meta.extra_process_content WHERE sha256 = ?", [sha256]
    ).fetchone()
    if row is None:
        raise KeyError(f"부대공정 판 내용을 찾을 수 없습니다: {sha256[:8]}")
    value = row[0]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    raise TypeError("부대공정 판 내용이 바이트가 아닙니다.")


def append_version(
    connection: duckdb.DuckDBPyConnection,
    *,
    expected_seq: int,
    kind: str,
    version_no: int | None,
    sha256: str | None,
    pack_bytes: bytes | None,
    applied_by: str | None,
    process_count: int | None,
    row_counts: str | None,
    source_place: str | None,
    s3_key: str | None = None,
    s3_etag: str | None = None,
    s3_last_modified: datetime | None = None,
) -> int:
    """판 이력에 한 줄을 넣고 그 차례를 돌려준다.

    `expected_seq` 는 화면이 본 마지막 줄의 차례다(없으면 0). 트랜잭션 안에서 읽은 마지막 줄과
    다르면 `ExtraProcessMoved` 로 쓰지 않는다 — 같은 누름의 겹친 둘째 회차와 남의 쓰기를
    가른다(설계 규칙 UI-STA-05). 내용 바이트가 있으면 내용 표에 한 벌만 둔다.
    """
    row = connection.execute(
        "SELECT coalesce(max(seq), 0) FROM app_meta.extra_process_version"
    ).fetchone()
    current = 0 if row is None else int(str(row[0]))
    if current != expected_seq:
        raise ExtraProcessMoved(expected_seq, current)
    if (kind == EXTRA_KIND_OFF) != (sha256 is None):
        raise ValueError("부대공정 「끄기」 줄만 판 내용이 없습니다.")
    if pack_bytes is not None and sha256 is not None:
        connection.execute(
            """
            INSERT INTO app_meta.extra_process_content (sha256, pack_bytes, byte_size)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM app_meta.extra_process_content WHERE sha256 = ?)
            """,
            [sha256, pack_bytes, len(pack_bytes), sha256],
        )
    elif sha256 is not None:
        load_content(connection, sha256)
    seq = current + 1
    connection.execute(
        """
        INSERT INTO app_meta.extra_process_version (
            seq, kind, version_no, sha256, applied_by, process_count, row_counts, source_place,
            s3_key, s3_etag, s3_last_modified, byte_size
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            seq,
            kind,
            version_no,
            sha256,
            applied_by,
            process_count,
            row_counts,
            source_place,
            s3_key,
            s3_etag,
            s3_last_modified,
            None if pack_bytes is None else len(pack_bytes),
        ],
    )
    return seq


def insert_provenance(
    connection: duckdb.DuckDBPyConnection,
    dataset_id: str,
    records: Sequence[ExtraProcessProvenance],
) -> None:
    """새 데이터셋의 출처 줄을 넣는다. 같은 (공정, 판 차례)가 겹치면 앞 줄만 남긴다."""
    seen: set[tuple[str, int]] = set()
    for record in records:
        key = (record.process_name, record.version_seq)
        if key in seen:
            continue
        seen.add(key)
        connection.execute(
            """
            INSERT INTO app_meta.dataset_extra_process (
                dataset_id, process_name, version_seq, version_no, sha256, outcome, rule, reason,
                row_counts, note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                dataset_id,
                record.process_name,
                record.version_seq,
                record.version_no,
                record.sha256,
                record.outcome,
                record.rule,
                record.reason,
                record.row_counts,
                record.note,
            ],
        )


def load_provenance(
    connection: duckdb.DuckDBPyConnection, dataset_id: str
) -> tuple[ExtraProcessProvenance, ...]:
    """데이터셋 하나의 출처 줄(공정 · 판 차례 순)."""
    rows = connection.execute(
        """
        SELECT process_name, version_seq, version_no, sha256, outcome, rule, reason, row_counts,
               note
        FROM app_meta.dataset_extra_process
        WHERE dataset_id = ?
        ORDER BY process_name, version_seq
        """,
        [dataset_id],
    ).fetchall()
    return tuple(
        ExtraProcessProvenance(
            process_name=str(row[0]),
            version_seq=int(str(row[1])),
            version_no=int(str(row[2])),
            sha256=str(row[3]),
            outcome=str(row[4]),
            rule=_optional_text(row[5]),
            reason=_optional_text(row[6]),
            row_counts=_optional_text(row[7]),
            note=_optional_text(row[8]),
        )
        for row in rows
    )
