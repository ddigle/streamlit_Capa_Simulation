# Purpose: 기준정보 편집이 계산에 필요한 다른 표의 행을 빠뜨렸는지 저장 전에 가린다.

"""표 하나를 고친 적용이 **다른 표와 어긋나는 것**을 적용 경계에서 가린다.

편집표의 빈 칸은 「값이 빈 행」이 아니라 「행 없음」이다(`capacity_reference_editor.
reference_from_edit_table` 가 빈 칸을 `dropna` 로 버린다). 그래서 칸을 채우면 행이 생기고,
비우면 행이 사라진다. 대당 Capa 는 `RQ_UPEH` 한 행마다 여섯 표를 왼쪽 조인하는데
(`unit_capacity._join_reference`), 연결값이 없을 때의 처리가 표마다 다르다.

- **측정률 두 표** — 행이 없으면 1.0 으로 가정해 이어 가고 화면이 알린다(40a09b8). 그래도
  UPEH 의 빈 달을 채워 **경로를 새로 만드는** 편집은 측정률 행을 먼저 갖추게 한다(정책 —
  2026-09-23 사내에서 저장 뒤 계산이 멈춘 일로 들어온 검사다. 멈춤은 40a09b8 로 가정·알림이
  됐지만, 새 경로를 가정값으로 시작하게 두지 않는다). `added_performance_keys`·
  `missing_ratio_rows`.
- **효율·여유율·일수** — 중립값이 없다. 경로가 쓰는 칸을 비우면 계산 전체가 「… 연결값이 없는
  대당 Capa 기준이 있습니다」로 멈춘다(2026-09-29 버그 보고 횡전개). `cleared_keys_in_use`.

**이번 편집이 만든 것만 본다.** 이미 어긋나 있던 것까지 막으면, 상관없는 칸 하나를
고치려던 사람이 자기가 만들지 않은 문제에 걸려 아무것도 못 하게 된다.

**비교 기준은 활성 시나리오다.** 저장 리비전과 맞대면 이 세션에서 먼저 적용한 STEP 추가·
측정률 입력이 보이지 않아, 안내대로 채워도 저장하기 전에는 풀리지 않았다(2026-09-29).

**측정률 두 표를 함께 본다.** Lot 만 채우면 바로 다음 적용에서 `RQ_WF_RATIO` 로 같은
문구가 이어진다 — 한 번에 알려 주지 않으면 사용자가 같은 일을 두 번 겪는다.
"""

from __future__ import annotations

import pandas as pd

from capa_simulation.services.frame_checks import strip_text_columns
from capa_simulation.services.frame_contracts import normalize_area_name, normalize_month_column
from capa_simulation.services.unit_capacity import (
    PERFORMANCE_KEYS,
    RUN_DAY_KEYS,
    RUN_RATE_KEYS,
    UNIMPLEMENTED_BASES,
    VITAL_KEYS,
)

# 측정률 두 표. 대당 Capa 가 `PERFORMANCE_KEYS` 로 붙이는 것이 이 둘뿐이라 한 곳에 둔다.
RATIO_TABLES: tuple[str, ...] = ("RQ_LOT_RATIO", "RQ_WF_RATIO")
# 중립값이 없는 표와 대당 Capa 가 붙이는 키. 경로가 쓰는 칸이 비면 계산 전체가 멈춘다.
REQUIRED_TABLE_KEYS: dict[str, list[str]] = {
    "RQ_RUN_RATE": RUN_RATE_KEYS,
    "RQ_VITAL": VITAL_KEYS,
    "RQ_RUN_DAY": RUN_DAY_KEYS,
}


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
    # 측정률 행이 없으면 계산은 멈추지 않고 1.0 으로 가정해 이어 간다(40a09b8). 전에는 「계산
    # 화면을 열 때 … 멈춥니다」라고 적었는데 그 뒤로는 거짓이다. 막는 것은 정책이다 — 새로 만든
    # 경로를 가정값으로 시작하게 두지 않는다.
    return (
        "UPEH 에 새로 만든 경로의 측정률 행이 없습니다. 새 경로는 측정률을 먼저 갖춘 뒤에 "
        "만듭니다 — 이대로 두면 계산이 그 경로의 측정률을 1.0 으로 가정합니다. "
        + " / ".join(parts)
        + ". 그 탭에서 같은 행의 같은 달 칸에 값을 넣고 「변경사항 적용」을 누른 뒤 UPEH 를 "
        "다시 적용하세요 — 측정 대상이 아닌 경로라면 `1` 이 중립값입니다."
    )


def _required_keys(data: pd.DataFrame, keys: list[str], table_name: str) -> pd.DataFrame:
    """조인과 같은 규칙(월 정수·공백 제거)으로 줄인 키."""
    result = data[keys].copy()
    normalize_month_column(result, table_name)
    strip_text_columns(result, [key for key in keys if key != "생산계획년월"])
    return result.drop_duplicates().reset_index(drop=True)


def cleared_keys_in_use(
    table_name: str,
    before: pd.DataFrame,
    after: pd.DataFrame,
    value_column: str,
    upeh: pd.DataFrame,
) -> pd.DataFrame:
    """이번 편집이 값을 지운 (월 + 키) 가운데 `RQ_UPEH` 경로가 쓰는 것.

    효율·여유율·일수(`REQUIRED_TABLE_KEYS`)에만 쓴다. `before` 는 편집표를 만든 원본(같은
    기간), `after` 는 적용할 행이다. **원본에 값이 있던 칸만** 센다 — 처음부터 비어 있던
    칸은 이번 편집이 만든 문제가 아니다. `RQ_UPEH` 는 적용 전 활성 시나리오 것이고, 계산이
    쓰지 않는 소요기준(`UNIMPLEMENTED_BASES`)의 행은 빼고 본다 — 그 행은 조인 전에 빠진다.
    """
    keys = REQUIRED_TABLE_KEYS[table_name]
    empty = pd.DataFrame(columns=keys)
    if before.empty:
        return empty
    had_value = pd.to_numeric(before[value_column], errors="coerce").notna()
    old = _required_keys(before.loc[had_value], keys, table_name)
    if old.empty:
        return empty
    new = _required_keys(after, keys, table_name)
    marked = old.merge(new, on=keys, how="left", indicator=True)
    cleared = marked.loc[marked["_merge"].eq("left_only"), keys]
    if cleared.empty or upeh.empty:
        return empty
    bases = upeh["소요기준"].astype("string").str.strip().str.upper()
    used = _required_keys(upeh.loc[~bases.isin(UNIMPLEMENTED_BASES).fillna(False)], keys, "RQ_UPEH")
    return (
        cleared.merge(used, on=keys, how="inner")
        .sort_values(keys, kind="stable")
        .reset_index(drop=True)
    )


def describe_cleared_keys_in_use(
    label: str, table_name: str, cleared: pd.DataFrame, limit: int = 3
) -> str:
    """어느 칸(월·키)인지, 왜 막는지, 어떻게 풀지를 적는다."""
    examples = []
    for _, row in cleared.head(limit).iterrows():
        path = " / ".join(
            f"{key}={row[key]}" for key in REQUIRED_TABLE_KEYS[table_name] if key != "생산계획년월"
        )
        examples.append(f"{row['생산계획년월']} · {path}")
    more = f" 외 {len(cleared) - limit:,}건" if len(cleared) > limit else ""
    return (
        f"「{label}」 표에서 값을 지운 칸 {len(cleared):,}개를 UPEH 경로가 씁니다 — "
        f"{'; '.join(examples)}{more}. {label}에는 중립값이 없어 비우면 계산 전체가 "
        f"「{table_name} 연결값이 없는 대당 Capa 기준이 있습니다」로 멈춥니다. 그 칸에 값을 "
        "넣거나, 그 경로를 먼저 UPEH 에서 비운 뒤 지우세요."
    )
