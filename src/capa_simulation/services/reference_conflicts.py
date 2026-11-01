# Purpose: Core 파생 RQ의 동일 업무 키 값 충돌을 수집하고 보고서로 만든다.

"""Core 파생 RQ의 동일 업무 키 값 충돌을 수집하고 보고서로 만든다."""

from __future__ import annotations

import json
import math
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from capa_simulation.io.core_data_source import CoreDataContract
from capa_simulation.services.frame_contracts import require_columns

TEMPORARY_CONFLICT_RESOLUTION = "값이 있는 첫 행 유지(0·빈값은 값 없음으로 본다)"
# 같은 업무 키에 0 행과 빈 값 행이 함께 오면 원천 행 차례와 상관없이 0 행을 고르는 표(2026-11-01
# 사용자 결정 — 효율·UPEH 부터). 두 표는 0 의 뜻이 확인됐다 — 효율 0 · Main UPEH 0 은 그 경로만 제외
# 목록으로 빠지고, 빈 값은 그 경로가 남으면 계산 전체를 멈춘다(Main UPEH 는 늘). BigDataQuery
# 조회에는 차례(ORDER BY)가 없어 같은 원천이 한 번은 서고 한 번은 멈췄다. 수율 0 · 보유 0 처럼 빈
# 값과 결과가 다를 수 있는 다른 표는 0 의 뜻을 확인할 때까지 지금대로(원천 행 차례) 둔다.
ZERO_BEFORE_BLANK_TABLES: Final = frozenset({"RQ_RUN_RATE", "RQ_UPEH"})
ZERO_BEFORE_BLANK_RESOLUTION: Final = (
    "값이 있는 첫 행 유지(0·빈값은 값 없음으로 보고, 그 둘만 다르면 0 행)"
)


def conflict_resolution(table_name: str) -> str:
    """충돌 보고서 「임시처리」 칸 — 그 표에서 형제 행을 고른 규칙."""
    if table_name in ZERO_BEFORE_BLANK_TABLES:
        return ZERO_BEFORE_BLANK_RESOLUTION
    return TEMPORARY_CONFLICT_RESOLUTION


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
    ordered = _informative_first(
        frame, list(keys), non_keys, zero_before_blank=table_name in ZERO_BEFORE_BLANK_TABLES
    )
    _collect_conflicting_duplicates(
        ordered.loc[ordered.duplicated(subset=list(keys), keep=False)],
        table_name,
        list(keys),
        non_keys,
        conflict_records,
    )
    return ordered.drop_duplicates(subset=list(keys), keep="first").reset_index(drop=True)


def _informative_first(
    frame: pd.DataFrame,
    keys: list[str],
    value_columns: list[str],
    *,
    zero_before_blank: bool = False,
) -> pd.DataFrame:
    """업무 키가 같은 형제 행 중 값이 있는 행을 그룹 안에서 앞으로 보낸다.

    업무 키는 Core Data 행을 유일하게 가르지 못한다 — 예를 들어 `RQ_UPEH` 9키에는
    `Capa Code`·`Customer`·`CS`·`Pack Code` 가 없어 한 키에 형제 행이 여럿 온다. 예전에는
    그중 **원천 행 순서상 첫 행**을 골랐는데, 원천이 '해당 없음' 을 0 으로 적는 탓에 0 행이
    앞서면 형제에 실값이 남아 있어도 0 이 저장됐다. 그 0 은 `대당 Capa 0 이하` 로 조용히
    제외돼 공정 하나가 통째로 사라졌다.

    그래서 승자를 '값이 있는 첫 행' 으로 바꾼다. **값을 지어내지 않는다** — 형제가 모두
    0 이면 결과는 종전과 같은 0 이다. 고르는 행만 달라지고 값은 원천 그대로다.

    `zero_before_blank` 인 표(`ZERO_BEFORE_BLANK_TABLES`)는 값 개수가 같은 형제 가운데 **0 이 빈
    값보다 먼저**다 — 0 칸이 많은 행, 같으면 앞 값 컬럼(표를 만드는 컬럼 차례 — `RQ_UPEH` 는 UPEH →
    ST)부터 0 인 행. 0 과 빈 값만 다른 형제는 원천 행 차례와 상관없이 늘 같은 행이 이긴다. 실값끼리
    다른 형제는 지금처럼 원천 행 차례다.

    그룹의 자리(첫 등장 순서)와 그룹 간 순서는 그대로다. 접은 뒤의 행 순서가 예전과 같아야
    `source_row_no` 와 `reference_hash` 가 흔들리지 않는다.
    """
    if not value_columns:
        return frame
    group_number = frame.groupby(keys, dropna=False, sort=False).ngroup().to_numpy()
    usable, zeros = _value_flags(frame, value_columns)
    position = np.arange(len(frame))
    tie_breaks: list[npt.NDArray[np.int64]] = []
    if zero_before_blank:
        # 앞 값 컬럼의 0 이 더 무겁다 — `lexsort` 에는 뒤 컬럼부터 넣는다.
        tie_breaks = [-flag for flag in reversed(zeros)]
        tie_breaks.append(-np.sum(zeros, axis=0, dtype="int64"))
    # `lexsort` 는 마지막 키가 1순위다. 그룹 → 값이 많은 행 → (0 이 빈 값보다 먼저) → 원천 행 순서.
    return frame.take(
        np.lexsort((position, *tie_breaks, -np.sum(usable, axis=0, dtype="int64"), group_number))
    )


def _value_flags(
    frame: pd.DataFrame, value_columns: list[str]
) -> tuple[list[npt.NDArray[np.int64]], list[npt.NDArray[np.int64]]]:
    """값 컬럼마다 행이 실제로 값을 든 칸(1)과 숫자 0 인 칸(1). 숫자 컬럼의 0 과 빈 문자열은 값
    없음이다."""
    usable_flags: list[npt.NDArray[np.int64]] = []
    zero_flags: list[npt.NDArray[np.int64]] = []
    for column in value_columns:
        series = frame[column]
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().any():
            # 숫자로 읽히는 컬럼. 0 은 원천이 '해당 없음' 을 적는 표기라 값으로 세지 않는다.
            usable = (numeric.notna() & numeric.ne(0)).to_numpy()
            zero = numeric.eq(0).fillna(False).to_numpy()
        else:
            text = series.astype("string").str.strip()
            usable = (text.notna() & text.ne("")).to_numpy()
            zero = np.zeros(len(frame), dtype=bool)
        usable_flags.append(usable.astype("int64"))
        zero_flags.append(zero.astype("int64"))
    return usable_flags, zero_flags


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
                "임시처리": conflict_resolution(table_name),
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
