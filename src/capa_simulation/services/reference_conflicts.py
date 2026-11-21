# Purpose: Core 파생 RQ의 동일 업무 키 값 충돌을 수집하고 보고서로 만든다.

"""Core 파생 RQ의 동일 업무 키 값 충돌을 수집하고 보고서로 만든다."""

from __future__ import annotations

import json
import math
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from capa_simulation.io.core_data_source import CoreDataContract
from capa_simulation.services.core_data_derivation import ACTIVE_CORE_COLUMNS
from capa_simulation.services.frame_contracts import require_columns

# 형제 행 순위의 칸 차례 — 제품을 가르는 구분 칸을 먼저 보고, 그다음
# `ACTIVE_CORE_COLUMNS` 의 나머지를 정의 차례대로 본다. 다른 부품끼리 값이 갈리면 부품
# 차례(이 줄의 차례)로 정해진다.
SOURCE_ROW_CLASS_COLUMNS: Final = (
    "제품정보",
    "Stack",
    "CUSTOM",
    "Capa Code",
    "Customer",
    "CS",
    "Pack Code",
)
# 순위의 한 칸에서 「0」 과 「빈 값」 의 차례. 참이면 0 이 앞서 0 행이 남고, 거짓이면 빈 값
# 행이 남는다. 같은 부품이 두 번 실려 한 칸만 0 과 빈 값으로 갈릴 때를 가른다(효율 · UPEH
# 표는 아래 `ZERO_BEFORE_BLANK_TABLES` 가 먼저 가르므로 이 값과 상관없이 0 행이다).
ZERO_OVER_BLANK: Final = True
# 충돌 보고서 「키밖구분」 칸 — 업무 키 밖의 구분 칸 하나로 설명되지 않는 갈림(재적재 등).
OTHER_CONFLICT_CAUSE: Final = "그 밖"
CONFLICT_CAUSE_COLUMN: Final = "키밖구분"
# 같은 업무 키에 0 행과 빈 값 행이 함께 오면 0 행을 고르는 표(2026-11-01 사용자 결정 —
# 효율·UPEH 부터). 두 표는 0 의 뜻이 확인됐다 — 효율 0 · Main UPEH 0 은 그 경로만 제외
# 목록으로 빠지고, 빈 값은 그 경로가 남으면 계산 전체를 멈춘다(Main UPEH 는 늘). 다른 표는
# 원천 행 순위(`ZERO_OVER_BLANK`)가 가른다.
ZERO_BEFORE_BLANK_TABLES: Final = frozenset({"RQ_RUN_RATE", "RQ_UPEH"})
ZERO_BEFORE_BLANK_RESOLUTION: Final = (
    "값이 있는 행 유지(0·빈값은 값 없음으로 보고, 그 둘만 다르면 0 행) — 같으면 원천 행 순위"
)


def row_rank_resolution() -> str:
    """효율 · UPEH 밖 표의 「임시처리」 글 — `ZERO_OVER_BLANK` 를 따라 0 · 빈 값 차례를 적는다."""
    tail = "0 · 빈 값" if ZERO_OVER_BLANK else "빈 값 · 0"
    return (
        "값이 있는 행 유지(0·빈값은 값 없음으로 본다) — 같으면 원천 행 순위"
        f"(구분 칸부터 칸마다 작은 값 · {tail} 차례)"
    )


def conflict_resolution(table_name: str) -> str:
    """충돌 보고서 「임시처리」 칸 — 그 표에서 형제 행을 고른 규칙."""
    if table_name in ZERO_BEFORE_BLANK_TABLES:
        return ZERO_BEFORE_BLANK_RESOLUTION
    return row_rank_resolution()


CONFLICT_REPORT_META_COLUMNS = [
    "RQ테이블",
    "충돌그룹",
    "업무키컬럼",
    "충돌컬럼",
    "키밖구분",
    "후보값",
    "선택값",
    "충돌행수",
    "임시제외행수",
    "후보원천행번호",
    "선택원천행번호",
    "임시처리",
]


def source_row_rank(frame: pd.DataFrame) -> pd.Series:
    """원천 행마다 하나의 순위(0 부터, 작을수록 앞) — 행 차례와 상관없이 같은 행이 같은 자리에 선다.

    칸 차례는 `SOURCE_ROW_CLASS_COLUMNS` → `ACTIVE_CORE_COLUMNS` 의 나머지 → 프레임의 그 밖 칸이고,
    앞 칸에서 갈리면 뒤 칸은 보지 않는 사전식이다. 칸마다:

    - 숫자 칸은 실값(0 · 빈 값이 아닌 값)을 작은 값부터, 그 뒤에 0 과 빈 값(차례는
      `ZERO_OVER_BLANK`). 0 을 실값 뒤에 두는 것은 원천이 「해당 없음」 을 0 으로 적어서다 —
      형제를 고를 때 0 을 값 없음으로 보는 규칙과 같은 뜻이다.
    - 글자 칸은 앞뒤 공백을 뗀 글자 차례, 빈 글자는 끝. 공백만 다른 두 값은 원래 글자
      차례로 가른다.

    모든 칸이 같은 행끼리만 원래 위치로 갈리고, 그런 행은 어느 표에서든 같은 값을 낸다.
    표마다가 아니라 원천 행 전체의 순위 하나라서 보유 · 대여 · 가용처럼 한 원천 행에서 나온
    형제 표도, 표마다 「값이 있는 칸 수」(`_informative_first` 의 앞 키)가 같으면 같은 행을
    고른다. 한 형제만 대여 0 · 가용 0 이면 그 표만 값이 있는 다른 행을 골라
    `보유 − 대여 = 가용` 이 서지 않을 수 있다 — 조회 차례와는 상관없이 늘 같은 쪽이다.
    0 · 빈 값 차례(`ZERO_OVER_BLANK`)도 그 칸보다 앞선 칸이 모두 같은 형제에만 걸린다.
    """
    columns = _rank_columns(frame)
    keys: list[npt.NDArray[Any]] = []
    for column in columns:
        keys.extend(_column_rank_keys(frame[column]))
    if not keys:
        return pd.Series(np.arange(len(frame), dtype="int64"), index=frame.index)
    position = np.arange(len(frame))
    # `lexsort` 는 마지막 키가 1순위다 — 앞 칸의 키가 뒤에 오도록 뒤집어 넣는다.
    order = np.lexsort((position, *reversed(keys)))
    rank = np.empty(len(frame), dtype="int64")
    rank[order] = position
    return pd.Series(rank, index=frame.index)


def _rank_columns(frame: pd.DataFrame) -> list[str]:
    present = [column for column in SOURCE_ROW_CLASS_COLUMNS if column in frame.columns]
    active = [
        column
        for column in ACTIVE_CORE_COLUMNS
        if column in frame.columns and column not in SOURCE_ROW_CLASS_COLUMNS
    ]
    rest = [column for column in frame.columns if column not in {*present, *active}]
    return [*present, *active, *rest]


def _column_rank_keys(series: pd.Series) -> list[npt.NDArray[Any]]:
    """한 칸의 순위 키 — 앞 키가 더 무겁다.

    숫자 칸은 (자리, 값), 글자 칸은 (빈 값, 뗀 글자, 원래 글자)다.
    """
    if pd.api.types.is_bool_dtype(series.dtype) or pd.api.types.is_numeric_dtype(series.dtype):
        numeric = pd.to_numeric(series, errors="coerce").astype("float64").to_numpy()
        blank = np.isnan(numeric)
        zero = numeric == 0
        zero_slot, blank_slot = (1, 2) if ZERO_OVER_BLANK else (2, 1)
        slot = np.where(blank, blank_slot, np.where(zero, zero_slot, 0))
        return [slot, np.where(blank | zero, 0.0, numeric)]
    raw = series.astype("string")
    stripped = raw.str.strip()
    blank_text = (stripped.isna() | stripped.eq("")).to_numpy(dtype=bool)
    stripped_codes, _ = pd.factorize(stripped.fillna(""), sort=True)
    raw_codes, _ = pd.factorize(raw.fillna(""), sort=True)
    return [blank_text.astype("int64"), stripped_codes, raw_codes]


def validated_distinct(
    frame: pd.DataFrame,
    table_name: str,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
    *,
    row_rank: pd.Series | None = None,
    source_classes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """업무 키로 접은 표. 형제 행은 `_informative_first` 의 차례로 하나만 남고, 값이 갈린
    그룹은 보고된다.

    `row_rank` 는 원천 작업 프레임 전체로 만든 `source_row_rank` 이고(원천 index),
    `source_classes` 는 같은 index 의 구분 칸이다(충돌 원인 「키밖구분」). 없으면 이 프레임의
    칸만으로 만든다.
    """
    keys = contract.derived_keys.get(table_name)
    if keys is None:
        raise KeyError(f"{table_name} 업무 키 계약이 없습니다.")
    require_columns(frame, list(keys), table_name)
    require_non_null(frame, list(keys), table_name)
    duplicated = frame.duplicated(subset=list(keys), keep=False)
    if not duplicated.any():
        return frame.reset_index(drop=True)
    non_keys = [column for column in frame.columns if column not in keys]
    rank = _aligned(row_rank if row_rank is not None else source_row_rank(frame), frame, table_name)
    classes = _aligned_classes(source_classes, frame, table_name)
    order = _informative_first(
        frame,
        list(keys),
        non_keys,
        rank.to_numpy(dtype="int64"),
        zero_before_blank=table_name in ZERO_BEFORE_BLANK_TABLES,
    )
    ordered = frame.take(order)
    siblings = ordered.duplicated(subset=list(keys), keep=False).to_numpy()
    _collect_conflicting_duplicates(
        ordered.loc[siblings],
        table_name,
        list(keys),
        non_keys,
        conflict_records,
        classes.take(order).loc[siblings, [c for c in classes.columns if c not in keys]],
    )
    return ordered.drop_duplicates(subset=list(keys), keep="first").reset_index(drop=True)


def _aligned(rank: pd.Series, frame: pd.DataFrame, table_name: str) -> pd.Series:
    """순위를 프레임 행에 맞춘다. 원천 index 가 어긋나면 순위가 뒤섞이므로 멈춘다."""
    if not frame.index.isin(rank.index).all():
        raise ValueError(f"{table_name} 행 순위가 원천 행 번호(index)와 맞지 않습니다.")
    return rank.loc[frame.index]


def _aligned_classes(
    source_classes: pd.DataFrame | None, frame: pd.DataFrame, table_name: str
) -> pd.DataFrame:
    """구분 칸을 프레임 행 차례(자리)에 맞춘다 — 순위와 같이 원천 index 가 어긋나면 멈춘다."""
    if source_classes is None:
        return frame.loc[:, [c for c in SOURCE_ROW_CLASS_COLUMNS if c in frame.columns]]
    if not frame.index.isin(source_classes.index).all():
        raise ValueError(f"{table_name} 구분 칸이 원천 행 번호(index)와 맞지 않습니다.")
    return source_classes.loc[frame.index]


def _informative_first(
    frame: pd.DataFrame,
    keys: list[str],
    value_columns: list[str],
    row_rank: npt.NDArray[np.int64],
    *,
    zero_before_blank: bool = False,
) -> npt.NDArray[np.intp]:
    """업무 키가 같은 형제 행 가운데 남길 행을 그룹 안에서 앞으로 보내는 행 자리(`take` 용).

    업무 키는 Core Data 행을 유일하게 가르지 못한다 — 예를 들어 `RQ_UPEH` 9키에는
    `Capa Code`·`Customer`·`CS`·`Pack Code` 가 없어 한 키에 형제 행이 여럿 온다. 원천이
    '해당 없음' 을 0 으로 적는 탓에 0 행을 고르면 형제에 실값이 남아 있어도 0 이 저장되고,
    그 0 은 `대당 Capa 0 이하` 로 조용히 제외돼 공정 하나가 통째로 사라진다.

    그래서 차례는 그룹 → **값이 있는 칸이 많은 행** → (효율 · UPEH 의 0 이 빈 값보다 먼저) →
    **원천 행 순위**(`source_row_rank`) → 원천 행 위치다. **값을 지어내지 않는다** — 형제가
    모두 0 이면 결과는 0 이다. 고르는 행만 달라지고 값은 원천 그대로다. BigDataQuery 조회에는
    차례(ORDER BY)가 없어, 원천 행 위치가 승자를 정하던 때는 같은 원천이 조회마다 다른 값으로
    저장될 수 있었다. 원천 행 위치는 모든 칸이 같은 행끼리만 닿아 값에 영향이 없다.

    `zero_before_blank` 인 표(`ZERO_BEFORE_BLANK_TABLES`)는 값 개수가 같은 형제 가운데 **0 이 빈
    값보다 먼저**다 — 0 칸이 많은 행, 같으면 앞 값 컬럼(표를 만드는 컬럼 차례 — `RQ_UPEH` 는 UPEH →
    ST)부터 0 인 행. 숫자 값 컬럼의 실값이 서로 다른 형제(`_real_values_agree` 가 거짓인 그룹)는 이
    규칙을 건너 원천 행 순위로 간다 — 다른 컬럼의 0 이 실값 충돌의 승자를 정하지 않는다.

    그룹의 자리(첫 등장 순서)와 그룹 간 순서는 그대로다. 접은 뒤의 행 순서가 예전과 같아야
    `source_row_no` 와 `reference_hash` 가 흔들리지 않는다.
    """
    if not value_columns:
        return np.arange(len(frame))
    group_number = frame.groupby(keys, dropna=False, sort=False).ngroup().to_numpy()
    usable, zeros = _value_flags(frame, value_columns)
    position = np.arange(len(frame))
    tie_breaks: list[npt.NDArray[np.int64]] = []
    if zero_before_blank:
        # 0 과 빈 값만 다른 그룹에서만 가른다. 앞 값 컬럼의 0 이 더 무겁다 — `lexsort` 에는 뒤
        # 컬럼부터 넣는다.
        agree = _real_values_agree(frame, group_number, value_columns)
        tie_breaks = [np.where(agree, -flag, 0) for flag in reversed(zeros)]
        tie_breaks.append(np.where(agree, -np.sum(zeros, axis=0, dtype="int64"), 0))
    # `lexsort` 는 마지막 키가 1순위다. 그룹 → 값이 많은 행 → (0 이 빈 값보다 먼저) → 원천 행 순위
    # → 원천 행 위치.
    order: npt.NDArray[np.intp] = np.lexsort(
        (
            position,
            row_rank,
            *tie_breaks,
            -np.sum(usable, axis=0, dtype="int64"),
            group_number,
        )
    )
    return order


def _real_values_agree(
    frame: pd.DataFrame, group_number: npt.NDArray[np.integer[Any]], value_columns: list[str]
) -> npt.NDArray[np.bool_]:
    """행마다 — 그 행의 그룹에서 숫자 값 컬럼의 실값(0·빈 값이 아닌 값)이 컬럼마다 하나뿐인가.

    거짓이면 실값끼리 다른 충돌이라 0 이 빈 값보다 먼저인 규칙으로 가르지 않는다. 글자 컬럼은 보지
    않는다(효율·UPEH 표의 값 컬럼은 모두 숫자다).
    """
    agree = np.ones(len(frame), dtype=bool)
    groups = pd.Series(group_number)
    for column in value_columns:
        numeric = pd.to_numeric(frame[column], errors="coerce").reset_index(drop=True)
        if not numeric.notna().any():
            continue
        real = numeric.where(numeric.ne(0))
        agree &= real.groupby(groups).transform("nunique").le(1).to_numpy()
    return agree


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
    source_classes: pd.DataFrame,
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
    group_ids = grouped.ngroup().to_numpy()
    causes = _conflict_causes(frame, group_ids, value_columns, source_classes)
    conflicting_rows = np.isin(group_ids, conflicting_groups)
    loop = frame.loc[conflicting_rows].groupby(keys, dropna=False, sort=False)
    for group_id, (_, group) in zip(conflicting_groups, loop, strict=True):
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
                CONFLICT_CAUSE_COLUMN: causes.get(int(group_id), OTHER_CONFLICT_CAUSE),
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


def _conflict_causes(
    frame: pd.DataFrame,
    group_ids: npt.NDArray[np.integer[Any]],
    value_columns: list[str],
    classes: pd.DataFrame,
) -> dict[int, str]:
    """그룹 번호 → 원인(업무 키 밖 구분 칸 이름, 여럿이면 ` | `). 없는 그룹은 「그 밖」 이다.

    구분 칸 c 가 원인인 조건: 그룹 안에서 c 값이 둘 이상이고, c 의 값마다 그 안에서는 값 칸이
    모두 하나로 맞는다(값이 c 값끼리만 다르다). 같은 c 안에서 값이 갈리면(재적재 등) c 탓이
    아니다. 갈리지 않은 값 칸은 그룹 전체에서 하나라 c 값 안에서도 하나다 — 그래서 값 칸 전부를
    한 번에 본다. 그룹마다 돌지 않고 구분 칸마다 groupby 한 번이다(`classes` 는 `frame` 과 같은
    자리 차례).
    """
    found: dict[int, list[str]] = {}
    groups = pd.Series(group_ids)
    values = frame.loc[:, value_columns].reset_index(drop=True)
    for column in classes.columns:
        by_class = classes[column].astype("string").str.strip().fillna("").reset_index(drop=True)
        varied = by_class.groupby(groups).nunique().ge(2)
        agree = values.groupby([groups, by_class]).nunique(dropna=False).le(1).all(axis=1)
        caused = varied & agree.groupby(level=0).all().reindex(varied.index, fill_value=False)
        for group_id in caused.index[caused.to_numpy()]:
            found.setdefault(int(group_id), []).append(str(column))
    return {group_id: " | ".join(names) for group_id, names in found.items()}


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
