# Purpose: Core 파생 RQ의 동일 업무 키 값 충돌을 수집하고 보고서로 만든다.

"""Core 파생 RQ의 동일 업무 키 값 충돌을 수집하고 보고서로 만든다."""

from __future__ import annotations

import json
import math

import numpy as np
import numpy.typing as npt
import pandas as pd

from capa_simulation.io.core_data_source import CoreDataContract
from capa_simulation.services.frame_contracts import require_columns

TEMPORARY_CONFLICT_RESOLUTION = "값이 있는 첫 행 유지(0·빈값은 값 없음으로 본다)"

CONFLICT_REPORT_META_COLUMNS = [
    "RQ테이블",
    "충돌그룹",
    "업무키컬럼",
    "충돌컬럼",
    "후보값",
    "선택값",
    "충돌행수",
    "임시제외행수",
    "후보원천행번호",
    "선택원천행번호",
    "임시처리",
]


def validated_distinct(
    frame: pd.DataFrame,
    table_name: str,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    keys = contract.derived_keys.get(table_name)
    if keys is None:
        raise KeyError(f"{table_name} 업무 키 계약이 없습니다.")
    require_columns(frame, list(keys), table_name)
    require_non_null(frame, list(keys), table_name)
    duplicated = frame.duplicated(subset=list(keys), keep=False)
    if not duplicated.any():
        return frame.reset_index(drop=True)
    non_keys = [column for column in frame.columns if column not in keys]
    ordered = _informative_first(frame, list(keys), non_keys)
    _collect_conflicting_duplicates(
        ordered.loc[ordered.duplicated(subset=list(keys), keep=False)],
        table_name,
        list(keys),
        non_keys,
        conflict_records,
    )
    return ordered.drop_duplicates(subset=list(keys), keep="first").reset_index(drop=True)


def _informative_first(
    frame: pd.DataFrame, keys: list[str], value_columns: list[str]
) -> pd.DataFrame:
    """업무 키가 같은 형제 행 중 값이 있는 행을 그룹 안에서 앞으로 보낸다.

    업무 키는 Core Data 행을 유일하게 가르지 못한다 — 예를 들어 `RQ_UPEH` 9키에는
    `Capa Code`·`Customer`·`CS`·`Pack Code` 가 없어 한 키에 형제 행이 여럿 온다. 예전에는
    그중 **원천 행 순서상 첫 행**을 골랐는데, 원천이 '해당 없음' 을 0 으로 적는 탓에 0 행이
    앞서면 형제에 실값이 남아 있어도 0 이 저장됐다. 그 0 은 `대당 Capa 0 이하` 로 조용히
    제외돼 공정 하나가 통째로 사라졌다.

    그래서 승자를 '값이 있는 첫 행' 으로 바꾼다. **값을 지어내지 않는다** — 형제가 모두
    0 이면 결과는 종전과 같은 0 이다. 고르는 행만 달라지고 값은 원천 그대로다.

    그룹의 자리(첫 등장 순서)와 그룹 간 순서는 그대로다. 접은 뒤의 행 순서가 예전과 같아야
    `source_row_no` 와 `reference_hash` 가 흔들리지 않는다.
    """
    if not value_columns:
        return frame
    group_number = frame.groupby(keys, dropna=False, sort=False).ngroup().to_numpy()
    usable = _usable_value_count(frame, value_columns)
    position = np.arange(len(frame))
    # `lexsort` 는 마지막 키가 1순위다. 그룹 → 값이 많은 행 → 원천 행 순서.
    return frame.take(np.lexsort((position, -usable, group_number)))


def _usable_value_count(frame: pd.DataFrame, value_columns: list[str]) -> npt.NDArray[np.int64]:
    """행이 실제로 들고 있는 값의 개수. 숫자 컬럼의 0 과 빈 문자열은 값 없음으로 센다."""
    counts = np.zeros(len(frame), dtype="int64")
    for column in value_columns:
        series = frame[column]
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().any():
            # 숫자로 읽히는 컬럼. 0 은 원천이 '해당 없음' 을 적는 표기라 값으로 세지 않는다.
            usable = (numeric.notna() & numeric.ne(0)).to_numpy()
        else:
            text = series.astype("string").str.strip()
            usable = (text.notna() & text.ne("")).to_numpy()
        counts += usable.astype("int64")
    return counts


def _collect_conflicting_duplicates(
    frame: pd.DataFrame,
    table_name: str,
    keys: list[str],
    value_columns: list[str],
    conflict_records: list[dict[str, object]],
) -> None:
    if not value_columns:
        return
    conflict_number = sum(1 for record in conflict_records if record.get("RQ테이블") == table_name)
    grouped = frame.groupby(keys, dropna=False, sort=False)
    # 그룹마다 파이썬 루프를 돌며 nunique 를 부르면 그룹 수에 비례해 느려진다. 실측으로
    # 적재 한 번(23,250행)에 21,796 그룹을 돌아 8~14초를 썼는데 실제 충돌은 0건이었다.
    # 판정은 groupby 한 번으로 벡터화하고, 보고서를 만드는 루프는 충돌 그룹에만 돈다.
    # `nunique()` 의 행 순서와 `ngroup()` 의 번호는 둘 다 첫 등장 순서라 서로 맞는다.
    distinct_counts = grouped[value_columns].nunique(dropna=False)
    conflicting_groups = np.flatnonzero(distinct_counts.gt(1).any(axis=1).to_numpy())
    if conflicting_groups.size == 0:
        return
    conflicting_rows = grouped.ngroup().isin(conflicting_groups)
    for _, group in frame.loc[conflicting_rows].groupby(keys, dropna=False, sort=False):
        conflicting_columns = [
            column for column in value_columns if group[column].nunique(dropna=False) > 1
        ]
        conflict_number += 1
        selected = group.iloc[0]
        candidate_rows = group.loc[:, conflicting_columns].drop_duplicates(keep="first")
        record: dict[str, object] = {
            "RQ테이블": table_name,
            "충돌그룹": f"{table_name}-{conflict_number:04d}",
            "업무키컬럼": " | ".join(keys),
        }
        record.update({key: _report_scalar(selected[key]) for key in keys})
        record.update(
            {
                "충돌컬럼": " | ".join(conflicting_columns),
                "후보값": _report_json(candidate_rows.to_dict("records")),
                "선택값": _report_json(
                    {column: selected[column] for column in conflicting_columns}
                ),
                "충돌행수": len(group),
                "임시제외행수": len(group) - 1,
                "후보원천행번호": " | ".join(str(int(index) + 1) for index in group.index),
                "선택원천행번호": int(group.index[0]) + 1,
                "임시처리": TEMPORARY_CONFLICT_RESOLUTION,
            }
        )
        conflict_records.append(record)


def conflict_report(
    records: list[dict[str, object]],
    business_key_columns: list[str],
) -> pd.DataFrame:
    columns = [
        "RQ테이블",
        "충돌그룹",
        "업무키컬럼",
        *business_key_columns,
        *CONFLICT_REPORT_META_COLUMNS[3:],
    ]
    if not records:
        return pd.DataFrame(columns=columns)
    report = pd.DataFrame.from_records(records)
    return report.reindex(columns=columns)


def _report_json(value: object) -> str:
    if isinstance(value, list):
        normalized: object = [
            {key: _report_scalar(item) for key, item in row.items()}
            if isinstance(row, dict)
            else _report_scalar(row)
            for row in value
        ]
    elif isinstance(value, dict):
        normalized = {key: _report_scalar(item) for key, item in value.items()}
    else:
        normalized = _report_scalar(value)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def _report_scalar(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    item_method = getattr(value, "item", None)
    normalized = item_method() if callable(item_method) else value
    if isinstance(normalized, float) and math.isnan(normalized):
        return None
    return normalized


def require_non_null(frame: pd.DataFrame, columns: list[str], table_name: str) -> None:
    invalid_columns = [column for column in columns if frame[column].isna().any()]
    for column in columns:
        if pd.api.types.is_string_dtype(frame[column].dtype):
            if frame[column].astype("string").str.strip().eq("").any():
                invalid_columns.append(column)
    if invalid_columns:
        labels = ", ".join(dict.fromkeys(invalid_columns))
        raise ValueError(f"{table_name} 업무 키에 null 또는 빈값이 있습니다: {labels}")
