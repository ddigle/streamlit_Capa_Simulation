# Purpose: 공정별 부하 산출 예외 선언의 판 이력(마이그레이션 0040) 읽기와 넣기 SQL 을 담당한다.

"""부하 예외 선언 판 이력 표의 SQL. 연결과 트랜잭션은 저장소
(`repository.DuckDBScenarioRepository`)가 소유한다.

판 이력은 넣기만 하고(append-only) 마지막 줄이 지금 선언이다. 모두 뺀 저장도 한 줄(비움 판)이다.
쓰기는 화면이 본 마지막 판 차례와 대조하고(`RouteLoadExceptionMoved`), 지문이 지금 판과 같으면
쓰지 않는다(`RouteLoadExceptionUnchanged`). 쓰기 앞에서 계산 쪽 정규화
(`route_load_exceptions.normalize_route_load_declaration`)로 검증해 이 코드가 모르는 산식 id ·
빈 공정 이름은 표에 들어가지 않는다.

읽기는 표가 없으면 `None` 이다 — 확인 스크립트가 마이그레이션하지 않고 여는 `0040` 전 DB 사본을
가른다(표를 만들지 않는다).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final

import duckdb

from capa_simulation.persistence.models import (
    RouteLoadExceptionEntries,
    RouteLoadExceptionState,
    RouteLoadExceptionVersion,
)
from capa_simulation.services.route_load_exceptions import (
    normalize_route_load_declaration,
    route_load_declaration_digest,
)

# 이 표를 만든 시뮬레이션 마이그레이션 번호와 표 자리.
ROUTE_LOAD_EXCEPTION_MIGRATION: Final = 40
# 확인 스크립트가 선언 표 없는 사본(0039 뒤 · 0040 전)을 읽었을 때 찍는 표지 — 세 스크립트가 같은
# 글자를 쓴다. 그 사본은 빈 선언으로 셈한다(`read_route_load_exceptions` 가 None).
BEFORE_ROUTE_EXCEPTION_COPY: Final = f"사본 {ROUTE_LOAD_EXCEPTION_MIGRATION:04d} 전"
ROUTE_LOAD_EXCEPTION_SCHEMA: Final = "app_meta"
ROUTE_LOAD_EXCEPTION_TABLE: Final = "route_load_exception_version"

_COLUMNS: Final = (
    "seq",
    "created_at",
    "applied_by",
    "source_place",
    "entries_json",
    "digest",
)


class RouteLoadExceptionMoved(ValueError):
    """화면이 본 판 뒤에 다른 쓰기가 끼었다 — 쓰지 않았다."""

    def __init__(self, expected: int, current: int) -> None:
        super().__init__(
            f"부하 예외 선언이 그 사이 바뀌었습니다(본 판 {expected} · 지금 판 {current}) — 화면을 "
            "새로 읽고 다시 누르세요."
        )
        self.expected = expected
        self.current = current


class RouteLoadExceptionUnchanged(ValueError):
    """저장할 선언이 지금 판과 같다(견줌 키로 같은 선언) — 쓰지 않았다."""

    def __init__(self, current: int) -> None:
        super().__init__(f"부하 예외 선언이 지금 판({current})과 같아 저장하지 않았습니다.")
        self.current = current


def has_route_load_exception_table(connection: duckdb.DuckDBPyConnection) -> bool:
    """판 이력 표가 있는가 — `0040` 전 DB 는 없다."""
    row = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
        [ROUTE_LOAD_EXCEPTION_SCHEMA, ROUTE_LOAD_EXCEPTION_TABLE],
    ).fetchone()
    return row is not None and int(str(row[0])) > 0


def read_route_load_exceptions(
    connection: duckdb.DuckDBPyConnection,
) -> RouteLoadExceptionState | None:
    """판 이력 전체(오래된 차례). 표가 없으면(`0040` 전 DB) `None` 이다."""
    if not has_route_load_exception_table(connection):
        return None
    rows = connection.execute(
        f"SELECT {', '.join(_COLUMNS)} "
        f"FROM {ROUTE_LOAD_EXCEPTION_SCHEMA}.{ROUTE_LOAD_EXCEPTION_TABLE} ORDER BY seq"
    ).fetchall()
    return RouteLoadExceptionState(tuple(_version(row) for row in rows))


def _version(row: Sequence[object]) -> RouteLoadExceptionVersion:
    values = dict(zip(_COLUMNS, row, strict=True))
    created_at = values["created_at"]
    if not isinstance(created_at, datetime):
        raise TypeError(f"부하 예외 선언 판의 시각 칸이 시각이 아닙니다: {created_at!r}")
    return RouteLoadExceptionVersion(
        seq=int(str(values["seq"])),
        created_at=created_at,
        entries=_entries(str(values["entries_json"])),
        digest=str(values["digest"]),
        applied_by=_optional_text(values["applied_by"]),
        source_place=_optional_text(values["source_place"]),
    )


def _entries(text: str) -> RouteLoadExceptionEntries:
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise TypeError("부하 예외 선언 판의 항목 칸이 JSON 객체가 아닙니다.")
    return tuple((str(process), str(formula)) for process, formula in loaded.items())


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def append_route_load_exceptions(
    connection: duckdb.DuckDBPyConnection,
    *,
    expected_seq: int,
    entries: Mapping[str, str],
    applied_by: str | None,
    source_place: str | None,
) -> int:
    """판 이력에 한 줄을 넣고 그 차례를 돌려준다.

    `entries` 는 원본 공정명 → 산식 id 이고 빈 사상이면 비움 판이다. 검증(모르는 산식 id · 빈 공정
    이름 · 대소문자만 다른 두 공정의 다른 산식은 `ValueError`) → 판 대조(`expected_seq` 는 화면이 본
    마지막 판 차례, 없으면 0 — 다르면 `RouteLoadExceptionMoved`) → 지문 대조(지금 판과 같으면
    `RouteLoadExceptionUnchanged` — 한 번도 저장하지 않은 표에 비움을 넣는 것도 같다) 차례다. 어느
    것이든 걸리면 아무것도 쓰지 않는다.
    """
    normalize_route_load_declaration(entries)
    digest = route_load_declaration_digest(entries)
    row = connection.execute(
        f"SELECT coalesce(max(seq), 0) FROM {ROUTE_LOAD_EXCEPTION_SCHEMA}."
        f"{ROUTE_LOAD_EXCEPTION_TABLE}"
    ).fetchone()
    current = 0 if row is None else int(str(row[0]))
    if current != expected_seq:
        raise RouteLoadExceptionMoved(expected_seq, current)
    current_digest = ""
    if current:
        digest_row = connection.execute(
            f"SELECT digest FROM {ROUTE_LOAD_EXCEPTION_SCHEMA}.{ROUTE_LOAD_EXCEPTION_TABLE} "
            "WHERE seq = ?",
            [current],
        ).fetchone()
        current_digest = "" if digest_row is None else str(digest_row[0])
    if digest == current_digest:
        raise RouteLoadExceptionUnchanged(current)
    ordered = dict(sorted((str(process), str(formula)) for process, formula in entries.items()))
    seq = current + 1
    connection.execute(
        f"""
        INSERT INTO {ROUTE_LOAD_EXCEPTION_SCHEMA}.{ROUTE_LOAD_EXCEPTION_TABLE} (
            seq, applied_by, source_place, entries_json, entry_count, digest
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            seq,
            applied_by,
            source_place,
            json.dumps(ordered, ensure_ascii=False, separators=(",", ":")),
            len(ordered),
            digest,
        ],
    )
    return seq
