"""Apply workbook-managed display order rules to Streamlit tables."""

import pandas as pd

DISPLAY_ORDER_REQUIRED_COLUMNS = [
    "적용화면",
    "컬럼순서",
    "분류컬럼",
    "정렬방식",
    "분류값",
    "정렬순서",
    "활성여부",
]
DISPLAY_ORDER_MODES = {"사용자지정", "오름차순", "내림차순"}


def _prepare_display_order(display_order: pd.DataFrame) -> pd.DataFrame:
    missing = [
        column
        for column in DISPLAY_ORDER_REQUIRED_COLUMNS
        if column not in display_order.columns
    ]
    if missing:
        raise ValueError(f"RQ_DISPLAY_ORDER 필수 컬럼이 없습니다: {', '.join(missing)}")

    prepared = display_order[DISPLAY_ORDER_REQUIRED_COLUMNS].copy()
    text_columns = ["적용화면", "분류컬럼", "정렬방식", "분류값", "활성여부"]
    for column in text_columns:
        prepared[column] = prepared[column].astype("string").str.strip()
    prepared["활성여부"] = prepared["활성여부"].str.upper()
    prepared["컬럼순서"] = pd.to_numeric(prepared["컬럼순서"], errors="coerce")
    prepared["정렬순서"] = pd.to_numeric(prepared["정렬순서"], errors="coerce")

    required_values = prepared[["적용화면", "컬럼순서", "분류컬럼", "정렬방식", "활성여부"]]
    if required_values.isna().any(axis=None):
        raise ValueError("RQ_DISPLAY_ORDER의 필수 설정값에 누락이 있습니다.")
    invalid_modes = sorted(set(prepared["정렬방식"].dropna()) - DISPLAY_ORDER_MODES)
    if invalid_modes:
        raise ValueError(f"RQ_DISPLAY_ORDER에 지원하지 않는 정렬방식이 있습니다: {invalid_modes}")
    invalid_active = sorted(set(prepared["활성여부"].dropna()) - {"Y", "N"})
    if invalid_active:
        raise ValueError(f"RQ_DISPLAY_ORDER 활성여부는 Y 또는 N이어야 합니다: {invalid_active}")
    return prepared


def apply_display_order(
    data: pd.DataFrame,
    display_order: pd.DataFrame | None,
    screen: str,
    value_aliases: dict[str, dict[str, str]] | None = None,
) -> pd.DataFrame:
    """Sort data using active rules for a screen; unmapped custom values sort last."""
    if display_order is None:
        return data

    prepared = _prepare_display_order(display_order)
    rules = prepared.loc[
        prepared["활성여부"].eq("Y") & prepared["적용화면"].eq(screen)
    ].copy()
    if rules.empty:
        return data

    aliases = value_aliases or {}
    for column, mapping in aliases.items():
        mask = rules["분류컬럼"].eq(column)
        rules.loc[mask, "분류값"] = rules.loc[mask, "분류값"].replace(mapping)

    rule_summary = rules[["컬럼순서", "분류컬럼", "정렬방식"]].drop_duplicates()
    conflicts = rule_summary.groupby("분류컬럼").agg(
        컬럼순서수=("컬럼순서", "nunique"),
        정렬방식수=("정렬방식", "nunique"),
    )
    if conflicts.gt(1).any(axis=None):
        invalid_columns = conflicts.loc[conflicts.gt(1).any(axis=1)].index.tolist()
        raise ValueError(f"RQ_DISPLAY_ORDER의 컬럼 정렬 규칙이 충돌합니다: {invalid_columns}")

    rule_summary = rule_summary.sort_values("컬럼순서", kind="stable")
    result = data.copy()
    helper_columns: list[str] = []
    ascending: list[bool] = []

    for position, rule in enumerate(rule_summary.itertuples(index=False)):
        column = str(rule.분류컬럼)
        mode = str(rule.정렬방식)
        if column not in result.columns:
            continue

        helper = f"__display_order_{position}"
        column_rules = rules.loc[rules["분류컬럼"].eq(column)]
        if mode == "사용자지정":
            custom = column_rules[["분류값", "정렬순서"]]
            if custom.isna().any(axis=None):
                raise ValueError(
                    f"RQ_DISPLAY_ORDER의 사용자지정 규칙에 값이 누락되었습니다: {screen}.{column}"
                )
            duplicated = custom["분류값"].duplicated(keep=False)
            if duplicated.any():
                values = custom.loc[duplicated, "분류값"].drop_duplicates().tolist()
                raise ValueError(
                    f"RQ_DISPLAY_ORDER의 사용자지정 값이 중복되었습니다: {screen}.{column} {values}"
                )
            mapping = dict(zip(custom["분류값"], custom["정렬순서"], strict=True))
            result[helper] = result[column].astype("string").map(mapping).fillna(float("inf"))
            ascending.append(True)
        else:
            result[helper] = result[column].astype("string")
            ascending.append(mode == "오름차순")
        helper_columns.append(helper)

    if not helper_columns:
        return result

    result["__display_original_order"] = range(len(result))
    sorted_result = result.sort_values(
        [*helper_columns, "__display_original_order"],
        ascending=[*ascending, True],
        kind="stable",
        na_position="last",
    )
    return sorted_result.drop(
        columns=[*helper_columns, "__display_original_order"]
    ).reset_index(drop=True)
