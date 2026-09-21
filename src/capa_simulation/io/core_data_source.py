# Purpose: Core Data source adapters and the shared 78-column normalization boundary.

"""Core Data source adapters and the shared 78-column normalization boundary."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Hashable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol, cast

import pandas as pd

from capa_simulation.services.month_filter import valid_month_mask
from capa_simulation.settings import PROJECT_ROOT

# 확장자만 YAML 이고 내용도 파서도 JSON 이었다. 실제 형식에 맞춰 이름을 바꿨다.
DATA_CONTRACT_PATH = PROJECT_ROOT / "config" / "data_contract.json"
ColumnType = Literal["string", "integer", "number"]

# 계약의 `quote_style` 이 실제 파서 동작을 정한다. 예전에는 이 키가 적혀만 있고
# `csv.QUOTE_NONE` 이 코드에 박혀 있어, 값에 쉼표가 든 표준 CSV 를 읽을 방법이 없었다.
# 로컬 표본에 큰따옴표가 한 글자도 없어서 드러나지 않았을 뿐이다.
# pandas 의 `quoting` 은 int 가 아니라 리터럴 넷만 받는다. 타입을 좁혀 둬야 통과한다.
QUOTE_STYLES: dict[str, Literal[0, 1, 2, 3]] = {
    "minimal": csv.QUOTE_MINIMAL,
    "none": csv.QUOTE_NONE,
}


@dataclass(frozen=True)
class CoreDataColumn:
    name: str
    dtype: ColumnType


@dataclass(frozen=True)
class CoreDataContract:
    version: int
    encoding: str
    delimiter: str
    quote_style: str
    columns: tuple[CoreDataColumn, ...]
    derived_keys: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class CoreDataBatch:
    simulation_code: str
    simulation_name: str
    source_type: str
    frame: pd.DataFrame
    source_registered_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name, label in (
            ("simulation_code", "시뮬레이션 코드"),
            ("simulation_name", "시뮬레이션명"),
            ("source_type", "원천 유형"),
        ):
            value = cast(str, getattr(self, field_name)).strip()
            if not value:
                raise ValueError(f"{label}은(는) 비어 있을 수 없습니다.")
            object.__setattr__(self, field_name, value)
        if not isinstance(self.frame, pd.DataFrame):
            raise TypeError("Core Data 원천은 pandas DataFrame이어야 합니다.")


class CoreDataProvider(Protocol):
    def fetch(self, simulation_code: str) -> CoreDataBatch: ...


@dataclass(frozen=True)
class CsvCoreDataProvider:
    """Development adapter that has the same output contract as BigDataQuery."""

    path: Path
    simulation_name: str

    def fetch(self, simulation_code: str) -> CoreDataBatch:
        code = simulation_code.strip()
        if not code:
            raise ValueError("시뮬레이션 코드는 비어 있을 수 없습니다.")
        return CoreDataBatch(
            simulation_code=code,
            simulation_name=self.simulation_name,
            source_type="CSV_CORE_DATA",
            frame=read_core_data_csv(self.path),
        )


def load_core_data_contract(path: Path | None = None) -> CoreDataContract:
    contract_path = path or DATA_CONTRACT_PATH
    payload = cast(object, json.loads(contract_path.read_text(encoding="utf-8")))
    root = _mapping(payload, "data contract")
    version = _integer(root.get("contract_version"), "contract_version")
    source = _mapping(root.get("source"), "source")
    encoding = _text(source.get("encoding"), "source.encoding")
    delimiter = _text(source.get("delimiter"), "source.delimiter")
    if len(delimiter) != 1:
        raise ValueError("source.delimiter는 한 글자여야 합니다.")
    quote_style = _text(source.get("quote_style"), "source.quote_style")
    if quote_style not in QUOTE_STYLES:
        raise ValueError(
            f"지원하지 않는 source.quote_style 입니다: {quote_style} "
            f"({', '.join(sorted(QUOTE_STYLES))} 중 하나)"
        )

    raw_columns = source.get("columns")
    if not isinstance(raw_columns, list):
        raise ValueError("source.columns는 목록이어야 합니다.")
    columns: list[CoreDataColumn] = []
    for index, raw_column in enumerate(raw_columns, start=1):
        column = _mapping(raw_column, f"source.columns[{index}]")
        name = _text(column.get("name"), f"source.columns[{index}].name")
        dtype_value = _text(column.get("dtype"), f"source.columns[{index}].dtype")
        if dtype_value not in {"string", "integer", "number"}:
            raise ValueError(f"지원하지 않는 Core Data dtype입니다: {dtype_value}")
        columns.append(CoreDataColumn(name, cast(ColumnType, dtype_value)))
    names = [column.name for column in columns]
    if len(names) != len(set(names)):
        raise ValueError("Core Data 계약 컬럼명이 중복되었습니다.")

    raw_keys = _mapping(root.get("derived_keys"), "derived_keys")
    derived_keys: dict[str, tuple[str, ...]] = {}
    for table_name, raw_value in raw_keys.items():
        if not isinstance(raw_value, list) or not all(
            isinstance(value, str) and value.strip() for value in raw_value
        ):
            raise ValueError(f"{table_name} derived key가 올바르지 않습니다.")
        derived_keys[table_name] = tuple(cast(list[str], raw_value))
    return CoreDataContract(
        version=version,
        encoding=encoding,
        delimiter=delimiter,
        quote_style=quote_style,
        columns=tuple(columns),
        derived_keys=derived_keys,
    )


def read_core_data_csv(
    path: Path,
    contract: CoreDataContract | None = None,
) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    selected = contract or load_core_data_contract()
    string_dtypes: dict[Hashable, str] = {
        column.name: "string" for column in selected.columns if column.dtype == "string"
    }
    frame = pd.read_csv(
        path,
        encoding=selected.encoding,
        delimiter=selected.delimiter,
        quoting=QUOTE_STYLES[selected.quote_style],
        dtype=string_dtypes,
        low_memory=False,
    )
    return normalize_core_data(frame, selected)


def normalize_core_data(
    frame: pd.DataFrame,
    contract: CoreDataContract | None = None,
) -> pd.DataFrame:
    """Normalize CSV and BigDataQuery frames through one strict column contract."""
    selected = contract or load_core_data_contract()
    if frame.columns.duplicated().any():
        duplicates = frame.columns[frame.columns.duplicated()].astype(str).tolist()
        raise ValueError(f"Core Data 컬럼명이 중복되었습니다: {', '.join(duplicates[:5])}")
    expected = [column.name for column in selected.columns]
    actual = [str(column) for column in frame.columns]
    missing = [column for column in expected if column not in actual]
    extra = [column for column in actual if column not in expected]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"누락: {', '.join(missing[:10])}")
        if extra:
            details.append(f"추가: {', '.join(extra[:10])}")
        raise ValueError(f"Core Data 78컬럼 계약이 일치하지 않습니다 ({'; '.join(details)}).")

    saved_source_dtypes = frame.attrs.get("source_dtypes")
    source_dtypes = (
        cast(dict[str, str], saved_source_dtypes)
        if isinstance(saved_source_dtypes, dict)
        else {column: str(frame[column].dtype) for column in expected}
    )
    normalized = pd.DataFrame(index=frame.index)
    for column in selected.columns:
        series = frame[column.name]
        if column.dtype == "string":
            normalized[column.name] = series.astype("string")
        elif column.dtype == "integer":
            normalized[column.name] = _numeric_series(series, column.name, integer=True)
        else:
            normalized[column.name] = _numeric_series(series, column.name, integer=False)
    _validate_production_month(normalized["생산계획년월"])
    normalized = normalized.reset_index(drop=True)
    normalized.attrs["source_dtypes"] = source_dtypes
    normalized.attrs["contract_version"] = selected.version
    return normalized


def build_source_column_profile(frame: pd.DataFrame) -> pd.DataFrame:
    source_dtypes = frame.attrs.get("source_dtypes")
    source_dtype_by_column = (
        cast(dict[str, str], source_dtypes) if isinstance(source_dtypes, dict) else {}
    )
    return pd.DataFrame(
        {
            "ordinal_position": range(1, len(frame.columns) + 1),
            "column_name": [str(column) for column in frame.columns],
            "source_dtype": [
                source_dtype_by_column.get(str(column), str(frame[column].dtype))
                for column in frame.columns
            ],
            "nullable_dtype": [str(frame[column].dtype) for column in frame.columns],
            "null_count": [int(frame[column].isna().sum()) for column in frame.columns],
            "unique_count": [int(frame[column].nunique(dropna=True)) for column in frame.columns],
        }
    )


def core_data_row_hashes(frame: pd.DataFrame) -> pd.Series:
    values = pd.util.hash_pandas_object(frame, index=False, categorize=True)
    return values.map(lambda value: f"{int(value):016x}").astype("string")


def core_data_schema_hash(frame: pd.DataFrame) -> str:
    payload = [(str(column), str(frame[column].dtype)) for column in frame.columns]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def core_data_hash(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update(core_data_schema_hash(frame).encode("ascii"))
    for value in sorted(core_data_row_hashes(frame).astype(str).tolist()):
        digest.update(str(value).encode("ascii"))
    return digest.hexdigest()


def _numeric_series(series: pd.Series, column_name: str, *, integer: bool) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(series.dtype):
        # read_csv·DuckDB 가 이미 숫자로 읽은 컬럼에는 공백 문자열이 있을 수 없다. 그런데
        # 공백을 찾으려고 매번 문자열로 바꾸는 것이 정규화 시간의 71% 였다(호출당 0.4s,
        # 저장 한 번에 네 번). 문자열·object 컬럼만 옛 경로를 탄다.
        missing = series.isna()
        numeric = pd.to_numeric(series, errors="coerce")
    else:
        as_text = series.astype("string")
        blank = as_text.str.strip().eq("").fillna(False)
        missing = series.isna() | blank
        numeric = pd.to_numeric(series.mask(blank), errors="coerce")
    invalid = numeric.isna() & ~missing
    if invalid.any():
        raise ValueError(
            f"Core Data 숫자 컬럼에 변환할 수 없는 값이 있습니다: {column_name} "
            f"({int(invalid.sum())}행)"
        )
    if integer:
        fractional = numeric.notna() & numeric.mod(1).ne(0)
        if fractional.any():
            raise ValueError(
                f"Core Data 정수 컬럼에 소수값이 있습니다: {column_name} "
                f"({int(fractional.sum())}행)"
            )
        if column_name == "생산계획년월":
            # 일반 정수 컬럼은 nullable 이지만 월은 필수 달력 값이다. Int64 캐스트 전에
            # 검사해야 너무 큰 숫자도 pandas 내부 예외 대신 기존 입력 오류로 전달된다.
            _validate_production_month(numeric)
        return numeric.astype("Int64")
    return numeric.astype("Float64")


def _validate_production_month(series: pd.Series) -> None:
    numeric = pd.to_numeric(series, errors="coerce")
    if not valid_month_mask(numeric).all():
        raise ValueError("Core Data 생산계획년월은 유효한 YYYYMM 정수여야 합니다.")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label}은 객체여야 합니다.")
    return cast(dict[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}은 비어 있지 않은 문자열이어야 합니다.")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label}은 정수여야 합니다.")
    return value
