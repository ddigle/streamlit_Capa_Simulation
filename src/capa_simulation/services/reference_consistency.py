# Purpose: 기준정보 편집이 계산에 필요한 다른 표의 행을 빠뜨렸는지 저장 전에 가린다.

"""**저장은 되는데 화면에서 터지는 일**을 저장 경계에서 막는다.

`RQ_UPEH` 의 빈 월 칸에 값을 넣으면 Long 테이블에 행이 하나 생긴다. 값을 고치는 일이
아니라 **경로를 하나 더 만드는 일**이다(`capacity_reference_editor.reference_from_edit_table`
가 빈 칸을 `dropna` 로 버리므로, 빈 칸은 「값이 빈 행」이 아니라 「행 없음」이다).

그런데 대당 Capa 는 `RQ_UPEH` 한 행마다 여섯 표를 왼쪽 조인하고 **첫 결손에서 즉시
멈춘다**(`unit_capacity._join_reference`). 측정률 두 표에 그 (경로 + 월) 행이 없으면
저장은 정상으로 끝나고 **HOME 을 열 때** 「RQ_LOT_RATIO 연결값이 없는 대당 Capa 기준이
있습니다」로 터진다. 실제로 사내에서 그렇게 됐다(2026-09-23).

저장 경계에는 표 사이 정합성을 보는 검사가 없었다 — UPEH 탭은 `RQ_UPEH` 하나만 갱신한다.
여기서 그 검사를 한다.

**이번 편집이 새로 만든 조합만 본다.** 이미 어긋나 있던 것까지 막으면, 상관없는 칸 하나를
고치려던 사람이 자기가 만들지 않은 문제에 걸려 아무것도 못 하게 된다.

**측정률 두 표를 함께 본다.** Lot 만 채우면 바로 다음 조인에서 `RQ_WF_RATIO` 로 같은
문구가 이어진다 — 한 번에 알려 주지 않으면 사용자가 같은 일을 두 번 겪는다.
"""

from __future__ import annotations

import pandas as pd

from capa_simulation.services.frame_checks import strip_text_columns
from capa_simulation.services.frame_contracts import normalize_area_name, normalize_month_column
from capa_simulation.services.unit_capacity import PERFORMANCE_KEYS

# 측정률 두 표. 대당 Capa 가 `PERFORMANCE_KEYS` 로 붙이는 것이 이 둘뿐이라 한 곳에 둔다.
RATIO_TABLES: tuple[str, ...] = ("RQ_LOT_RATIO", "RQ_WF_RATIO")


def _performance_keys(data: pd.DataFrame, table_name: str) -> pd.DataFrame:
    """`PERFORMANCE_KEYS` 만 남기고 조인과 **같은 규칙으로** 줄인다.

    `unit_capacity._join_reference` 가 월 정규화·공백 제거·`Area_Name` 정규화를 거쳐
    맞대므로, 여기서 다르게 줄이면 없는 결손을 있다고 하거나 있는 결손을 놓친다.
    """
    missing = [key for key in PERFORMANCE_KEYS if key not in data.columns]
    if missing:
        raise KeyError(f"{table_name}에 연결 키가 없습니다: {', '.join(missing)}")
    keys = data[PERFORMANCE_KEYS].copy()
    normalize_month_column(keys, table_name)
    strip_text_columns(keys, [key for key in PERFORMANCE_KEYS if key != "생산계획년월"])
    keys["Area_Name"] = normalize_area_name(keys["Area_Name"], table_name)
    return keys.drop_duplicates().reset_index(drop=True)


def added_performance_keys(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    """이번 편집이 **새로 만든** (경로 + 월) 조합."""
    if after.empty:
        return after.head(0)
    new_keys = _performance_keys(after, "RQ_UPEH")
    if before.empty:
        return new_keys
    old_keys = _performance_keys(before, "RQ_UPEH")
    marked = new_keys.merge(old_keys, on=PERFORMANCE_KEYS, how="left", indicator=True)
    return (
        marked.loc[marked["_merge"].eq("left_only"), PERFORMANCE_KEYS]
        .drop_duplicates()
        .reset_index(drop=True)
    )


def missing_ratio_rows(
    added: pd.DataFrame,
    ratio_tables: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """새 조합 중 측정률 행이 없는 것. 표 이름마다 결손 키를 돌려준다."""
    if added.empty:
        return {}
    result: dict[str, pd.DataFrame] = {}
    for table_name in RATIO_TABLES:
        ratio = ratio_tables.get(table_name)
        if ratio is None:
            continue
        have = _performance_keys(ratio, table_name) if not ratio.empty else None
        if have is None:
            result[table_name] = added
            continue
        marked = added.merge(have, on=PERFORMANCE_KEYS, how="left", indicator=True)
        gap = marked.loc[marked["_merge"].eq("left_only"), PERFORMANCE_KEYS]
        if not gap.empty:
            result[table_name] = gap.reset_index(drop=True)
    return result


def describe_missing_ratio_rows(missing: dict[str, pd.DataFrame], limit: int = 3) -> str:
    """사용자가 **어느 탭 어느 칸을 채워야 하는지** 알 수 있게 적는다.

    개수만 말하면 「그래서 뭘 하라는 것인가」가 남는다. 측정률 편집표의 차원은 월을 뺀
    8개이므로 월과 분류를 함께 적어야 그 칸을 찾을 수 있다.
    """
    if not missing:
        return ""
    labels = {"RQ_LOT_RATIO": "Lot측정률", "RQ_WF_RATIO": "WF측정률"}
    parts: list[str] = []
    for table_name, gap in missing.items():
        examples = []
        for _, row in gap.head(limit).iterrows():
            month = row["생산계획년월"]
            path = " / ".join(
                f"{key}={row[key]}" for key in PERFORMANCE_KEYS if key != "생산계획년월"
            )
            examples.append(f"{month} · {path}")
        more = f" 외 {len(gap) - limit:,}건" if len(gap) > limit else ""
        parts.append(
            f"「{labels.get(table_name, table_name)}」 탭에 {len(gap):,}건 — "
            f"{'; '.join(examples)}{more}"
        )
    return (
        "UPEH 에 새로 만든 경로의 측정률 행이 없습니다. 이대로 적용하면 저장은 되지만 "
        "**계산 화면을 열 때 「연결값이 없는 대당 Capa 기준이 있습니다」로 멈춥니다.** "
        + " / ".join(parts)
        + ". 그 탭에서 같은 행의 같은 달 칸에 값을 넣은 뒤 다시 적용하세요 — "
        "측정 대상이 아닌 경로라면 `1` 이 중립값입니다."
    )
