# Purpose: 월별 억Gb 한 칸짜리 공용 프로필(선행 B/O·선행 입고)의 정규화와 편집 병합을 맡는다.

"""월별 억Gb 값 한 칸짜리 공용 프로필의 공통 규칙.

선행 B/O(`advance_load`)와 선행 입고 실적(`advance_shipment`)은 쓰임이 다르지만 저장 모양과
입력 규칙이 같다 — `생산계획년월` 하나에 값 하나, 부호는 입력한 그대로, 0 과 빈칸은 「넣지 않은
달」이라 지운다, 화면에 보인 달만 갈아 끼우고 조회기간 밖 저장분은 그대로 둔다. 규칙을 두 곳에
적으면 한쪽만 고쳐져 두 편집기가 같은 입력을 다르게 저장한다. 그래서 여기 한 번만 적고 두 모듈은
컬럼 이름과 문구 주어만 넘긴다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from capa_simulation.services.frame_contracts import require_exact_columns

MONTH_COLUMN = "생산계획년월"


def empty_monthly_amounts(value_column: str) -> pd.DataFrame:
    """아직 아무것도 넣지 않은 정상 상태의 빈 프레임."""
    return pd.DataFrame(
        {
            MONTH_COLUMN: pd.Series(dtype="int64"),
            value_column: pd.Series(dtype="float64"),
        }
    )


def prepare_monthly_amounts(
    frame: pd.DataFrame,
    *,
    value_column: str,
    subject: str,
) -> pd.DataFrame:
    """저장·계산 공용 정규화. 0 과 결측은 「넣지 않은 달」이라 지운다.

    0 을 남겨 두면 저장본이 조회기간만큼 커지고, 그 달에 값을 **지정했다**는 뜻으로 읽힌다.
    지정하지 않은 것과 0 을 지정한 것은 결과가 같으므로 구분해 둘 이유가 없다. 부호는 입력한
    그대로다 — 음수도 뜻이 있는 값이다. `subject` 는 오류 문구의 주어다(예: 「선행 물량」).
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{subject}은(는) pandas DataFrame이어야 합니다.")
    columns = (MONTH_COLUMN, value_column)
    require_exact_columns(frame.columns, columns, f"{subject} 컬럼")
    if frame.empty:
        return empty_monthly_amounts(value_column)
    prepared = frame.loc[:, list(columns)].copy()
    prepared[MONTH_COLUMN] = pd.to_numeric(prepared[MONTH_COLUMN], errors="coerce")
    prepared[value_column] = pd.to_numeric(prepared[value_column], errors="coerce")
    prepared = prepared.dropna(subset=[MONTH_COLUMN])
    prepared[MONTH_COLUMN] = prepared[MONTH_COLUMN].astype("int64")
    invalid_month = ~prepared[MONTH_COLUMN].mod(100).between(1, 12)
    if invalid_month.any():
        examples = sorted({int(value) for value in prepared.loc[invalid_month, MONTH_COLUMN]})[:5]
        raise ValueError(f"생산계획년월이 YYYYMM 형식이 아닙니다: {', '.join(map(str, examples))}")
    duplicated = prepared[MONTH_COLUMN].duplicated()
    if duplicated.any():
        examples = sorted({int(value) for value in prepared.loc[duplicated, MONTH_COLUMN]})[:5]
        raise ValueError(f"같은 달이 두 번 들어 있습니다: {', '.join(map(str, examples))}")
    prepared[value_column] = prepared[value_column].fillna(0.0).astype("float64")
    prepared = prepared.loc[prepared[value_column].ne(0.0)]
    return prepared.sort_values(MONTH_COLUMN).reset_index(drop=True)


def merge_monthly_amount_edits(
    stored: pd.DataFrame,
    months: Sequence[int],
    values: Sequence[object],
    *,
    value_column: str,
    subject: str,
) -> pd.DataFrame:
    """화면에 보인 달만 갈아 끼우고 나머지 저장분은 그대로 둔다.

    조회기간이 좁혀져 있으면 표에 없는 달이 저장본에 남아 있다. 통째로 교체하면 그 달의
    입력을 누른 사람이 모르는 새 날린다. 보이지 않는 것을 지우지 않는다. 빈칸은 0(지움)이다.
    """
    if len(months) != len(values):
        raise ValueError(f"{subject} 입력의 월 수와 값 수가 다릅니다.")
    prepared = prepare_monthly_amounts(stored, value_column=value_column, subject=subject)
    merged = {
        int(month): float(value)
        for month, value in zip(prepared[MONTH_COLUMN], prepared[value_column], strict=True)
    }
    for month, value in zip(months, values, strict=True):
        numeric = pd.to_numeric(pd.Series([value], dtype="object"), errors="coerce").iloc[0]
        merged[int(month)] = 0.0 if pd.isna(numeric) else float(numeric)
    return prepare_monthly_amounts(
        pd.DataFrame({MONTH_COLUMN: list(merged), value_column: list(merged.values())}),
        value_column=value_column,
        subject=subject,
    )


def amounts_by_month(rows: pd.DataFrame, value_column: str) -> dict[int, float]:
    """저장본을 `{YYYYMM: 값}` 으로. 편집기 칸과 그림 글자가 같은 사전을 읽는다."""
    if rows.empty:
        return {}
    return {
        int(month): float(value)
        for month, value in zip(rows[MONTH_COLUMN], rows[value_column], strict=True)
    }
