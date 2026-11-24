# Purpose: 원천 CSV 를 등록과 같은 길로 읽어 사본 DB 의 같은 코드 원천과 견주고 수만 찍는다.

"""원천 CSV 견줌 — 원천 웹에서 받은 시나리오 CSV 가 같은 코드로 DB 에서 받아 둔 원천과
같은지 수로만 본다.

    uv run --no-sync python scripts/inspect_source_csv.py \\
        --database <DB 사본> --csv <원천 CSV> --output <저장소 밖 파일>

**CSV 쪽**은 DB 등록 탭 「CSV 파일」 길과 같은 함수로 읽는다 — 흘려 읽기 요약
(`summarize_source_csv`) → 원천 CSV 공급자(`SourceCsvCoreDataProvider.fetch` — 숫자 글자 칸
맞춤 · 설비대수변화관리 비움 · 파일 CUSTOM 붙이기 · 원천 보정) → 정규화(`normalize_core_data`).
**DB 쪽**은 파일의 코드마다 사본에 그 코드로 받아 둔 DB 길 원천(파생 넷 · CSV 원천 밖이고
`raw_data.core_data` 행이 있는 데이터셋) 가운데 가장 최근 것의 원천 행을 읽어 같은 정규화를
거친다. 그런 데이터셋이 없는 코드는 건너뛴다.

코드마다 견주는 것:

- **원천 행** — 두 쪽 행 수, 완전 중복을 접은 행 수, 두 쪽에 다 있는 행 수(행 해시
  `core_data_row_hashes`). DB 길은 상세 조회 창 안의 적재분을 모두 받아 재적재가 겹치면 완전
  중복 행이 는다.
- **원천 해시** — CSV 원천 해시(`core_data_hash`)가 그 데이터셋에 저장된 해시
  (`source_data_hash` — 저장소의 원천 코드 불변 검사가 견주는 값)와 같은가. 같으면 같은 코드를
  다른 길로 다시 등록해도 거절되지 않는다.
- **16표** — 두 원천을 지금 파이프라인(`build_reference_tables` · 두 쪽 같은 내장 표시순서)으로
  다시 파생해 표마다 견준다 — 저장된 리비전의 편집과 상관없다. 정확은 행 차례를 맞춘 뒤
  `DataFrame.equals` 이고, 오차 안은 숫자 칸을 `rtol=1e-12` · `atol=0` 으로, 그 밖 칸은 글자로
  견준다. 행 차례는 숫자 아닌 칸을 앞 열쇠로 맞춘다 — 끝자리만 다른 실수가 차례를 바꾸지 않게.
- **다른 열** — 계약 78열마다 두 원천(완전 중복을 접은 것)의 값 묶음(값마다 행 수)이 다른 수.
  숫자 칸이 오차 안에서만 다르면 「끝자리만」 으로 따로 센다 — 요약의 다른 열에는 오차 밖으로
  다른 열만 든다.
- **CUSTOM 뺌** — 두 원천의 CUSTOM 을 빈 값 표지(`CUSTOM_BLANK`)로 둔 16표를 한 번 더 견준다.
  CUSTOM 둘째 표를 붙이기 전에 DB 로 등록한 원천은 CUSTOM 칸에 조회문 상수가 있고 CSV 는 파일의
  부품 값을 붙여 CUSTOM 키 표가 늘 갈린다 — 그 밖의 칸이 같은지는 이 셈이 말한다.

판정(쓸 수 있다 · 없다)은 찍지 않는다 — 사실만 찍고 읽는 법은 런북이 적는다. 끝에 코드마다
`전송용 요약:` 한 줄을 찍는다 — 리뷰 압축본에 그대로 옮긴다.

**지키는 것** — `inspect_revision_calculations.py` 와 같다.

- **읽기만 한다.** DB 를 `read_only=True` 로 열고 저장소(Repository)를 만들지 않는다 —
  `initialize()` 는 마이그레이션을 건다(쓰기다). CSV 도 읽기만 한다.
- **사본에만 돌린다.** `--database` 는 기본값이 없고, 운영 DB 자리
  (`settings.is_operational_database_place` — 같은 파일 · 운영 `data/` 와 그 아래 · git 저장소
  안)는 DB 를 열기 전에 거절한다(종료 2). 사내에서는 사본도 사내 DB 라 사용자가 별도 PowerShell
  창에서 돌리고 에이전트는 `--output` 파일만 읽는다(런북 0장).
- **값을 찍지 않는다.** 수 · 같음/다름 · 원천 종류와 계약 이름(열 · `RQ_*` 표)만 찍는다. 파일
  이름 · 경로 · 시뮬레이션 코드 · 예외 문구는 찍지 않는다 — 원천 CSV · CUSTOM 멈춤 글에는 열
  이름 · 부품 코드가, 파생 멈춤 글에는 공정 · 제품 이름이 실린다. 멈추면 단계와 예외 종류만
  적는다. 코드가 여럿이면 파일 안 차례 번호(`코드 1`)로 적는다.

종료 코드는 0 끝까지 견줌 · 1 DB 를 다른 프로세스가 쥠 · 2 거절 · 파일 없음 · 읽지 못함 · 같은
코드 없음 · 견주다 멈춘 코드가 있음이다.

사외에서 돌린 수는 합성 표본의 `샘플 관측` 일 뿐 업무 사실이 아니다(AGENTS.md 10-1).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Final, TextIO

import duckdb
import numpy as np
import numpy.typing as npt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.io.core_data_source import (  # noqa: E402
    core_data_hash,
    core_data_row_hashes,
    load_core_data_contract,
    normalize_core_data,
)
from capa_simulation.io.source_csv import (  # noqa: E402
    SourceCsvCoreDataProvider,
    SourceCsvSummary,
    summarize_source_csv,
)
from capa_simulation.services.builtin_seed import load_builtin_display_order  # noqa: E402
from capa_simulation.services.core_data_derivation import CUSTOM_BLANK  # noqa: E402
from capa_simulation.services.reference_transformer import build_reference_tables  # noqa: E402
from capa_simulation.services.revision_compatibility import CUSTOM_COLUMN  # noqa: E402
from capa_simulation.settings import (  # noqa: E402
    DUCKDB_PATH,
    EQUIPMENT_DUCKDB_PATH,
    is_operational_database_place,
)

# 다른 시나리오에서 만든 데이터셋의 원천 종류 — 원천 행이 받은 그대로가 아니다(복제는 원천 행이
# 없다).
# `inspect_real_data_checks.DERIVED_SOURCE_TYPES` 와 같은 넷이다(시험이 맞댄다).
DERIVED_SOURCE_TYPES: Final[tuple[str, ...]] = (
    "DUCKDB_SCENARIO_CLONE",
    "SCENARIO_MONTH_MERGE",
    "SCENARIO_YEAR_SHIFT",
    "SCENARIO_EXTRA_PROCESS",
)
# CSV 원천(스크립트 첫 적재 · 원천 CSV 올림)의 원천 종류 접두어 — DB 길과 견줄 짝이 아니다.
CSV_SOURCE_PREFIX: Final = "CSV_CORE_DATA"
# 오차 안 — 숫자 칸의 상대 오차만 본다(절대 오차를 두면 작은 값의 차이가 그 안에 묻힌다).
RELATIVE_TOLERANCE: Final = 1e-12
# 요약 줄에 이름을 늘어놓는 다른 열 수 — 그 뒤는 「외 n」.
COLUMN_NAME_LIMIT: Final = 5
SUMMARY_LABEL: Final = "전송용 요약:"
SUMMARY_KEY: Final = "CSV견줌"

_HEADER: Final = "<!-- inspect_source_csv.py — 아래 블록을 리뷰 문서에 붙인다 -->\n"
_HEADING: Final = "### 원천 CSV 견줌 (`inspect_source_csv.py`)"
_OPERATIONAL_REFUSAL: Final = (
    "운영 DB 자리(운영 DB 와 같은 파일 · 운영 `data/` 와 그 아래 · git 저장소 안)는 받지 "
    "않는다 — DB 를 열지 않았다. 저장소 밖 사본의 경로를 저장소에서 준다"
    "(`--database <사본 폴더>/data/capa_simulation.duckdb`)."
)
_LOCK_MESSAGE: Final = (
    "DB 를 열지 못했습니다 — 다른 프로세스가 지금 쥐고 있다. 운영 DB 는 앱이 쉬는 동안 열리기도 "
    "하지만 그동안 사용자 앱의 연결이 막힌다 — 사본을 떠 `--database` 로 준다."
)
# 행 차례 · 글자 견줌에서 빈 값의 자리 — 값으로 오지 않는 글자다.
_MISSING: Final = "\x00<빈 값>"
# 원천 데이터셋 고르기 — 파생 넷 · CSV 원천 밖이고 원천 행이 있는 것.
_SOURCE_DATASET_FILTER: Final = (
    f"d.source_type NOT IN ({', '.join('?' for _ in DERIVED_SOURCE_TYPES)}) "
    "AND d.source_type NOT LIKE ? "
    "AND EXISTS (SELECT 1 FROM raw_data.core_data AS c WHERE c.dataset_id = d.dataset_id)"
)
_SOURCE_DATASET_PARAMETERS: Final = (*DERIVED_SOURCE_TYPES, f"{CSV_SOURCE_PREFIX}%")

READING_GUIDE: Final[tuple[str, ...]] = (
    "",
    "**읽는 법**",
    "",
    "- `원천 행` 은 CSV · DB 두 쪽의 행 수이고, `접음` 은 완전 중복 행을 하나로 접은 수, "
    "`두 쪽에 다 있음` 은 접은 행 가운데 두 쪽 모두에 있는 수다.",
    "- `원천 해시` 는 CSV 원천 해시가 그 데이터셋에 저장된 해시와 같은가다(같은 코드 다시 "
    "등록의 거절 판정과 같은 값).",
    "- `16표` 의 정확은 행 차례를 맞춘 뒤 값 · 꼴이 모두 같은 표 수, 오차 안은 숫자 칸을 상대 "
    "오차 1e-12 로 견준 표 수다. `CUSTOM 뺌` 은 두 쪽 CUSTOM 을 빈 값 표지로 두고 다시 파생해 "
    "견준 수다.",
    "- `다른 열` 은 오차 밖으로 값 묶음이 다른 계약 열이고, `끝자리만` 은 숫자 칸이 오차 "
    "안에서만 다른 열이다. 값은 찍지 않는다.",
)


@dataclass(frozen=True)
class SourceDataset:
    """코드 하나의 DB 길 원천 데이터셋 — 가장 최근 적재한 것과 같은 코드 데이터셋 수."""

    dataset_id: str
    source_type: str
    source_data_hash: str | None
    count: int


@dataclass(frozen=True)
class TableMatch:
    """16표 가운데 하나의 견줌 — 행 수와 정확 · 오차 안."""

    name: str
    csv_rows: int
    db_rows: int
    exact: bool
    tolerant: bool


@dataclass(frozen=True)
class ColumnDifference:
    """값 묶음이 다른 계약 열 하나 — 다른 값 묶음 수와 오차 안에서만 다른가(숫자 칸)."""

    name: str
    groups: int
    within_tolerance: bool


@dataclass(frozen=True)
class TableComparison:
    """16표 견줌 한 벌 — 파생이 멈췄으면 표 대신 그 쪽과 예외 종류(`stopped`)를 든다."""

    matches: tuple[TableMatch, ...] = ()
    stopped: str | None = None

    @property
    def exact(self) -> int:
        return sum(match.exact for match in self.matches)

    @property
    def tolerant(self) -> int:
        return sum(match.tolerant for match in self.matches)


@dataclass(frozen=True)
class SourceComparison:
    """코드 하나의 견줌 — 원천 행 · 해시 · 열 · 16표 두 벌(그대로 · CUSTOM 뺌)."""

    csv_rows: int
    db_rows: int
    csv_folded: int
    db_folded: int
    shared: int
    hash_same: bool
    columns: tuple[ColumnDifference, ...]
    tables: TableComparison
    custom_set_aside: TableComparison

    @property
    def differing_columns(self) -> tuple[ColumnDifference, ...]:
        return tuple(column for column in self.columns if not column.within_tolerance)

    @property
    def last_digit_columns(self) -> tuple[ColumnDifference, ...]:
        return tuple(column for column in self.columns if column.within_tolerance)


# ---------------------------------------------------------------------------------- 견줌


def _is_number(series: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(
        series.dtype
    )


def _sort_key(series: pd.Series) -> pd.Series:
    return series if _is_number(series) else series.astype("string")


def ordered(frame: pd.DataFrame) -> pd.DataFrame:
    """행 차례를 맞춘 표 — 숫자 아닌 칸(글자로 견줌)을 앞 열쇠로, 숫자 칸을 뒤 열쇠로 정렬한다.

    끝자리만 다른 실수가 행 차례를 바꾸면 오차 안 견줌이 다른 행끼리 맞대므로 숫자 칸은 뒤에 둔다.
    """
    if frame.empty or len(frame.columns) == 0:
        return frame.reset_index(drop=True)
    texts = [column for column in frame.columns if not _is_number(frame[column])]
    numbers = [column for column in frame.columns if _is_number(frame[column])]
    return frame.sort_values(
        by=[*texts, *numbers],
        key=_sort_key,
        na_position="last",
        kind="mergesort",
        ignore_index=True,
    )


def _texts(series: pd.Series) -> list[str]:
    return [str(value) for value in series.astype("string").fillna(_MISSING).tolist()]


def _numbers(series: pd.Series) -> npt.NDArray[np.float64]:
    return np.asarray(series.to_numpy(dtype="float64", na_value=np.nan), dtype=np.float64)


def tables_equal_exactly(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    """행 차례를 맞춘 뒤 칸 이름 · 차례 · 꼴 · 값이 모두 같은가(`DataFrame.equals`)."""
    if list(left.columns) != list(right.columns) or len(left) != len(right):
        return False
    return ordered(left).equals(ordered(right))


def tables_equal_within_tolerance(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    """행 차례를 맞춘 뒤 숫자 칸은 상대 오차 `RELATIVE_TOLERANCE` 안(절대 오차 0), 그 밖 칸은
    글자로 같은가.

    빈 값은 같은 자리의 빈 값과만 같다. 숫자 칸끼리가 아니면(글자 · 숫자) 글자로 견준다.
    """
    if list(left.columns) != list(right.columns) or len(left) != len(right):
        return False
    first, second = ordered(left), ordered(right)
    for column in first.columns:
        a, b = first[column], second[column]
        if _is_number(a) and _is_number(b):
            if not np.allclose(
                _numbers(a), _numbers(b), rtol=RELATIVE_TOLERANCE, atol=0.0, equal_nan=True
            ):
                return False
        elif _texts(a) != _texts(b):
            return False
    return True


def compare_tables(
    csv_tables: Mapping[str, pd.DataFrame], db_tables: Mapping[str, pd.DataFrame]
) -> tuple[TableMatch, ...]:
    """표마다 정확 · 오차 안 — 표 이름 차례는 DB 쪽(파생 차례)이다. 한쪽에만 있는 표는 다르다."""
    matches: list[TableMatch] = []
    for name in dict.fromkeys([*db_tables, *csv_tables]):
        csv_table = csv_tables.get(name)
        db_table = db_tables.get(name)
        if csv_table is None or db_table is None:
            present = csv_table if csv_table is not None else db_table
            rows = 0 if present is None else len(present)
            matches.append(
                TableMatch(
                    name,
                    rows if csv_table is not None else 0,
                    rows if db_table is not None else 0,
                    False,
                    False,
                )
            )
            continue
        matches.append(
            TableMatch(
                name,
                len(csv_table),
                len(db_table),
                tables_equal_exactly(csv_table, db_table),
                tables_equal_within_tolerance(csv_table, db_table),
            )
        )
    return tuple(matches)


def differing_value_groups(left: pd.Series, right: pd.Series) -> int:
    """값마다 행 수를 센 묶음이 두 쪽에서 다른 값의 수 — 빈 값 수가 다르면 하나를 더한다."""
    counts = pd.concat(
        [left.dropna().value_counts(), right.dropna().value_counts()], axis=1, sort=False
    ).fillna(0)
    differing = int(counts.iloc[:, 0].ne(counts.iloc[:, 1]).sum()) if not counts.empty else 0
    return differing + int(int(left.isna().sum()) != int(right.isna().sum()))


def within_tolerance(left: pd.Series, right: pd.Series) -> bool:
    """두 숫자 칸의 값을 각각 정렬해 맞대면 상대 오차 안인가(빈 값 수도 같아야). 숫자 칸이
    아니면 False 다."""
    if not (_is_number(left) and _is_number(right)):
        return False
    if int(left.isna().sum()) != int(right.isna().sum()):
        return False
    a = np.sort(_numbers(left.dropna()))
    b = np.sort(_numbers(right.dropna()))
    return a.shape == b.shape and bool(np.allclose(a, b, rtol=RELATIVE_TOLERANCE, atol=0.0))


def compare_columns(
    csv_source: pd.DataFrame, db_source: pd.DataFrame, names: Sequence[str]
) -> tuple[ColumnDifference, ...]:
    """계약 열마다 값 묶음을 견준다 — 다른 열만 계약 차례로 돌려준다."""
    differences: list[ColumnDifference] = []
    for name in names:
        left, right = csv_source[name], db_source[name]
        groups = differing_value_groups(left, right)
        if groups:
            differences.append(ColumnDifference(name, groups, within_tolerance(left, right)))
    return tuple(differences)


def _folded(frame: pd.DataFrame, hashes: pd.Series) -> pd.DataFrame:
    return frame.loc[~hashes.duplicated().to_numpy(dtype=bool)]


def custom_set_aside(source: pd.DataFrame) -> pd.DataFrame:
    """CUSTOM 을 모두 빈 값 표지로 둔 원천 사본 — 받은 원천은 고치지 않는다."""
    blank = pd.Series(CUSTOM_BLANK, index=source.index, dtype="string")
    return source.assign(**{CUSTOM_COLUMN: blank})


def _failure(side: str, exc: BaseException) -> str:
    return f"{side} {type(exc).__name__}"


def derive_and_compare(
    csv_source: pd.DataFrame, db_source: pd.DataFrame, display_order: pd.DataFrame
) -> TableComparison:
    """두 원천을 지금 파이프라인으로 파생해 16표를 견준다 — 멈추면 그 쪽과 예외 종류만 든다."""
    try:
        csv_tables = build_reference_tables(csv_source, display_order)
    except Exception as exc:  # 파생 멈춤 글에는 공정 · 제품 이름이 실린다 — 종류만 적는다
        return TableComparison(stopped=_failure("CSV", exc))
    try:
        db_tables = build_reference_tables(db_source, display_order)
    except Exception as exc:  # 위와 같다
        return TableComparison(stopped=_failure("DB", exc))
    return TableComparison(matches=compare_tables(csv_tables, db_tables))


def compare_sources(
    csv_source: pd.DataFrame,
    db_source: pd.DataFrame,
    stored_hash: str | None,
    display_order: pd.DataFrame,
) -> SourceComparison:
    """정규화한 두 원천을 견준다. 저장된 해시가 없으면 DB 원천에서 다시 셈한 해시와 견준다."""
    csv_hashes = core_data_row_hashes(csv_source)
    db_hashes = core_data_row_hashes(db_source)
    db_hash = stored_hash if stored_hash is not None else core_data_hash(db_source)
    names = [column.name for column in load_core_data_contract().columns]
    return SourceComparison(
        csv_rows=len(csv_source),
        db_rows=len(db_source),
        csv_folded=int(csv_hashes.nunique()),
        db_folded=int(db_hashes.nunique()),
        shared=len(set(csv_hashes.tolist()) & set(db_hashes.tolist())),
        hash_same=core_data_hash(csv_source) == db_hash,
        columns=compare_columns(
            _folded(csv_source, csv_hashes), _folded(db_source, db_hashes), names
        ),
        tables=derive_and_compare(csv_source, db_source, display_order),
        custom_set_aside=derive_and_compare(
            custom_set_aside(csv_source), custom_set_aside(db_source), display_order
        ),
    )


# ---------------------------------------------------------------------------------- 사본 읽기


def source_codes(connection: duckdb.DuckDBPyConnection) -> set[str]:
    """사본에 DB 길 원천 데이터셋이 있는 시뮬레이션 코드."""
    rows = connection.execute(
        "SELECT DISTINCT s.source_simulation_code FROM app_meta.scenario AS s "
        "JOIN app_meta.dataset AS d ON d.scenario_id = s.scenario_id "
        f"WHERE {_SOURCE_DATASET_FILTER}",
        list(_SOURCE_DATASET_PARAMETERS),
    ).fetchall()
    return {str(row[0]) for row in rows}


def source_dataset(connection: duckdb.DuckDBPyConnection, code: str) -> SourceDataset | None:
    """그 코드의 DB 길 원천 데이터셋 가운데 가장 최근에 적재한 것과 그런 데이터셋 수."""
    rows = connection.execute(
        "SELECT d.dataset_id, d.source_type, d.source_data_hash FROM app_meta.scenario AS s "
        "JOIN app_meta.dataset AS d ON d.scenario_id = s.scenario_id "
        f"WHERE s.source_simulation_code = ? AND {_SOURCE_DATASET_FILTER} "
        "ORDER BY d.imported_at DESC, d.dataset_id",
        [code, *_SOURCE_DATASET_PARAMETERS],
    ).fetchall()
    if not rows:
        return None
    dataset_id, source_type, data_hash = rows[0]
    return SourceDataset(
        dataset_id=str(dataset_id),
        source_type=str(source_type),
        source_data_hash=None if data_hash is None else str(data_hash),
        count=len(rows),
    )


def read_source_rows(connection: duckdb.DuckDBPyConnection, dataset_id: str) -> pd.DataFrame:
    """그 데이터셋의 원천 행(받은 차례) — 등록 때 정규화해 저장한 그대로다."""
    return connection.execute(
        "SELECT * EXCLUDE (dataset_id, source_row_no, row_hash) "
        "FROM raw_data.core_data WHERE dataset_id = ? ORDER BY source_row_no",
        [dataset_id],
    ).fetch_df()


# ---------------------------------------------------------------------------------- 찍기


def _same(value: bool) -> str:
    return "같음" if value else "다름"


def _names(columns: Sequence[ColumnDifference]) -> str:
    shown = ", ".join(column.name for column in columns[:COLUMN_NAME_LIMIT])
    hidden = len(columns) - COLUMN_NAME_LIMIT
    return f"{shown} 외 {hidden}" if hidden > 0 else shown


def _table_cells(prefix: str, tables: TableComparison) -> str:
    if tables.stopped is not None:
        return f"{prefix} 멈춤({tables.stopped})"
    total = len(tables.matches)
    return f"{prefix} 정확 {tables.exact}/{total} · 오차안 {tables.tolerant}/{total}"


def summary_line(label: str, comparison: SourceComparison) -> str:
    """`전송용 요약:` 한 줄 — 짧은 키와 수 · 같음/다름 · 계약 열 이름만."""
    differing = comparison.differing_columns
    columns = f"다른열 {len(differing)}" + (f"({_names(differing)})" if differing else "")
    cells = [
        f"원천행 {_same(comparison.csv_rows == comparison.db_rows)}",
        f"해시 {_same(comparison.hash_same)}",
        _table_cells("16표", comparison.tables),
        columns,
        _table_cells("CUSTOM뺌", comparison.custom_set_aside),
    ]
    return f"{SUMMARY_LABEL} {_key(label)} " + " · ".join(cells)


def stopped_line(label: str, reason: str) -> str:
    return f"{SUMMARY_LABEL} {_key(label)} {reason}"


def _key(label: str) -> str:
    return f"{SUMMARY_KEY} {label.replace(' ', '')}" if label else SUMMARY_KEY


def _block_head(label: str) -> str:
    return f"#### {label}" if label else "#### 견줌"


def _yes(value: bool) -> str:
    return "같음" if value else "**다름**"


def _table_block(comparison: SourceComparison) -> list[str]:
    plain, aside = comparison.tables, comparison.custom_set_aside
    if plain.stopped is not None or aside.stopped is not None:
        return [
            f"- 16표: {_table_cells('그대로', plain)} · {_table_cells('CUSTOM 뺌', aside)}",
        ]
    lines = [
        "",
        "| 표 | 행 CSV | 행 DB | 정확 | 오차 안 | CUSTOM 뺌 정확 | CUSTOM 뺌 오차 안 |",
        "|---|---:|---:|---|---|---|---|",
    ]
    set_aside = {match.name: match for match in aside.matches}
    for match in plain.matches:
        other = set_aside.get(match.name)
        lines.append(
            f"| `{match.name}` | {match.csv_rows:,} | {match.db_rows:,} | {_yes(match.exact)} | "
            f"{_yes(match.tolerant)} | {'-' if other is None else _yes(other.exact)} | "
            f"{'-' if other is None else _yes(other.tolerant)} |"
        )
    return lines


def _column_block(comparison: SourceComparison) -> list[str]:
    if not comparison.columns:
        return []
    lines = ["", "| 다른 열 | 다른 값 묶음 | 갈래 |", "|---|---:|---|"]
    for column in comparison.columns:
        kind = "끝자리만" if column.within_tolerance else "다름"
        lines.append(f"| `{column.name}` | {column.groups:,} | {kind} |")
    return lines


def comparison_lines(label: str, dataset: SourceDataset, comparison: SourceComparison) -> list[str]:
    """코드 하나의 블록 — 수와 같음/다름 · 원천 종류 · 계약 이름만."""
    return [
        "",
        _block_head(label),
        "",
        f"- DB 쪽 원천 종류 `{dataset.source_type}` · 같은 코드 원천 데이터셋 {dataset.count:,}"
        "(가장 최근 적재한 것과 견줌)",
        f"- 원천 행 CSV {comparison.csv_rows:,} · DB {comparison.db_rows:,} — 접음 "
        f"{comparison.csv_folded:,} · {comparison.db_folded:,} · 두 쪽에 다 있음 "
        f"{comparison.shared:,}",
        f"- 원천 해시 {_same(comparison.hash_same)}",
        f"- {_table_cells('16표', comparison.tables)} · "
        f"{_table_cells('CUSTOM 뺌', comparison.custom_set_aside)}",
        f"- 다른 열 {len(comparison.differing_columns):,} · 끝자리만 "
        f"{len(comparison.last_digit_columns):,}",
        *_table_block(comparison),
        *_column_block(comparison),
    ]


class _Sink:
    """조각이 끝나는 대로 화면과 `--output` 파일에 쓴다 — 중간에 멈춰도 앞 조각은 남는다."""

    def __init__(self, path: Path | None) -> None:
        self._file: TextIO | None = (
            None if path is None else path.open("w", encoding="utf-8", newline="\n")
        )

    def emit(self, text: str) -> None:
        print(text, flush=True)
        if self._file is not None:
            self._file.write(text + "\n")
            self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()


# ---------------------------------------------------------------------------------- 실행


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="원천 CSV 를 DB 사본의 같은 코드 원천과 견준다(읽기 전용 · 수만 찍음)."
    )
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="시뮬레이션 DuckDB 사본. 운영 DB 자리(저장소 data/ 아래 · git 저장소 안)는 거절한다",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="원천 웹에서 받은 시나리오 CSV(받은 그대로)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="같은 출력을 이 파일에도 쓴다(UTF-8). 저장소 밖 경로를 준다",
    )
    return parser.parse_args(argv)


def _use_utf8_stdout() -> None:
    # Windows 콘솔 기본 코드페이지(cp949)는 이 출력의 기호를 못 쓴다.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def operational_path(path: Path) -> bool:
    """사용자 앱이 여는 운영 DB 자리인가 — `inspect_revision_calculations.operational_path` 와
    같은 판정이다.

    운영 DB 와 같은 파일, 운영 `data/`(`settings.DUCKDB_PATH` 의 폴더와 이 저장소의 `data/`) 그
    자체나 그 아래, git 작업 트리 안을 막는다. 경로는 찍지 않는다.
    """
    return is_operational_database_place(
        path, (DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH, PROJECT_ROOT / "data" / DUCKDB_PATH.name)
    )


def _open_read_only(path: Path) -> tuple[duckdb.DuckDBPyConnection | None, str | None, int]:
    """(연결, 실패 한 줄, 종료 코드). 파일 경로는 찍지 않는다 — 이름만."""
    if not path.exists():
        return None, f"`{path.name}` 파일이 없다", 2
    try:
        return duckdb.connect(str(path), read_only=True), None, 0
    except duckdb.IOException:
        return None, _LOCK_MESSAGE, 1
    except duckdb.Error as exc:
        return None, f"`{path.name}` 파일을 열지 못했다 — {type(exc).__name__}", 2


def main(argv: Sequence[str] | None = None) -> int:
    _use_utf8_stdout()
    args = parse_args(argv)
    # `--output` 은 먼저 비우고 머리 한 줄부터 쓴다 — 일찍 끝나도 지난 실행의 파일이 새것처럼
    # 남지 않는다.
    sink = _Sink(None if args.output is None else Path(args.output))
    try:
        sink.emit(_HEADER)
        return _run(args, sink)
    finally:
        sink.close()


def _run(args: argparse.Namespace, sink: _Sink) -> int:
    database = Path(args.database)
    if operational_path(database):
        sink.emit(_OPERATIONAL_REFUSAL)
        return 2
    csv_path = Path(args.csv)
    if not csv_path.is_file():
        # 파일 이름에도 날짜 · 시뮬레이션명이 실릴 수 있어 찍지 않는다.
        sink.emit("`--csv` 파일이 없다")
        return 2
    started = time.perf_counter()
    with csv_path.open("rb") as handle:
        try:
            summary = summarize_source_csv(handle, file_id="inspect_source_csv")
        except Exception as exc:  # 원천 CSV 멈춤 글에는 열 이름이 실린다 — 종류만 적는다
            sink.emit(
                f"원천 CSV 를 읽지 못했다 — {type(exc).__name__}(까닭 글은 앱 DB 등록 탭 "
                "「CSV 파일」 에 같은 파일을 올리면 보인다 — 저장은 누르지 않는다)"
            )
            sink.emit(stopped_line("", f"읽지 못함({type(exc).__name__})"))
            return 2
        connection, failure, code = _open_read_only(database)
        if connection is None:
            sink.emit(str(failure))
            return code
        try:
            return _compare_codes(connection, handle, summary, database, sink, started)
        finally:
            connection.close()


def _compare_codes(
    connection: duckdb.DuckDBPyConnection,
    handle: BinaryIO,
    summary: SourceCsvSummary,
    database: Path,
    sink: _Sink,
    started: float,
) -> int:
    file_codes = list(dict.fromkeys(item.code for item in summary.codes))
    try:
        registered = source_codes(connection)
    except duckdb.Error as exc:
        sink.emit(
            f"시나리오 표를 읽지 못했다 — {type(exc).__name__}"
            "(앱이 한 번도 열지 않아 표가 없는 DB 일 수 있다)"
        )
        return 2
    numbered = [(number, code) for number, code in enumerate(file_codes, 1) if code in registered]
    sink.emit(
        "\n".join(
            [
                _HEADING,
                "",
                f"- 실행 {datetime.now():%Y-%m-%d %H:%M} · DB `{database.name}` · 파일 코드 "
                f"{len(file_codes):,} · 그 가운데 사본에 DB 길 원천이 있는 코드 {len(numbered):,}",
            ]
        )
    )
    if not numbered:
        sink.emit(stopped_line("", "같은 코드 없음"))
        return 2
    display_order = load_builtin_display_order()

    def open_buffer() -> BinaryIO | None:
        return handle

    # 시뮬레이션명은 원천 묶음의 빈칸 검사만 지나면 된다 — 견줌에 쓰지 않는다.
    provider = SourceCsvCoreDataProvider(open_buffer, summary, simulation_name=SUMMARY_KEY)
    summaries: list[str] = []
    stopped = False
    for number, code in numbered:
        label = f"코드 {number}" if len(file_codes) > 1 else ""
        line, compared = _compare_code(connection, provider, code, label, display_order, sink)
        stopped = stopped or not compared
        summaries.append(line)
    sink.emit("\n".join([*READING_GUIDE, f"- 걸린 시간 {time.perf_counter() - started:.1f}초", ""]))
    for line in summaries:
        sink.emit(line)
    return 2 if stopped else 0


def _compare_code(
    connection: duckdb.DuckDBPyConnection,
    provider: SourceCsvCoreDataProvider,
    code: str,
    label: str,
    display_order: pd.DataFrame,
    sink: _Sink,
) -> tuple[str, bool]:
    """코드 하나를 견주고 블록을 찍는다 — (그 코드의 요약 줄, 끝까지 견줬나). 요약 줄은
    찍지 않는다."""
    try:
        csv_source = normalize_core_data(provider.fetch(code).frame)
    except Exception as exc:  # CUSTOM 멈춤 글에는 부품 코드가 실린다 — 종류만 적는다
        sink.emit(f"\n{_block_head(label)}\n\n- CSV 원천을 짓지 못했다 — {type(exc).__name__}")
        return stopped_line(label, f"멈춤(CSV 원천 {type(exc).__name__})"), False
    try:
        dataset = source_dataset(connection, code)
        if dataset is None:
            raise LookupError("데이터셋 없음")
        db_source = normalize_core_data(read_source_rows(connection, dataset.dataset_id))
    except Exception as exc:  # 정규화 멈춤 글에는 열 이름 · 행 수가 실린다 — 종류만 적는다
        sink.emit(f"\n{_block_head(label)}\n\n- DB 원천을 읽지 못했다 — {type(exc).__name__}")
        return stopped_line(label, f"멈춤(DB 원천 {type(exc).__name__})"), False
    comparison = compare_sources(csv_source, db_source, dataset.source_data_hash, display_order)
    sink.emit("\n".join(comparison_lines(label, dataset, comparison)))
    stopped = (
        comparison.tables.stopped is not None or comparison.custom_set_aside.stopped is not None
    )
    return summary_line(label, comparison), not stopped


if __name__ == "__main__":
    raise SystemExit(main())
