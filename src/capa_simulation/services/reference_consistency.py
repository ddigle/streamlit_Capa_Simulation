# Purpose: 기준정보 편집이 계산에 필요한 다른 표의 행·값을 깨뜨렸는지 저장 전에 가린다.

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
  여유율·일수는 0 이하 값도 「… 0보다 커야 합니다」로 멈춘다 — `nonpositive_keys_in_use`
  (2026-09-29 2차 리뷰). 효율 0 은 그 경로만 제외 목록으로 빠져 계산이 멈추지 않는다.
- UPEH 의 빈 달을 채워 **경로를 새로 만들 때**도 세 표의 행이 있어야 한다. 측정률만 보던 검사가
  이 셋을 보지 않아, 효율 행이 없는 달을 채우면 적용은 성공하고 계산 전체가 멈췄다(2026-09-29
  2차 리뷰). `missing_required_rows` — 측정률 결손과 **한 오류문**으로 알린다
  (`describe_missing_path_rows`).
- **「경로가 쓰는 칸」 은 제외 뒤에도 남는 경로가 쓰는 칸이다**(`_live_upeh`). 대당 Capa 는
  Main UPEH 0 이하 · 효율 0 이하 · 측정률 음수인 경로를 먼저 빼고 남은 경로에서만 빈 값 · 행 없음 ·
  0 이하로 멈춘다(2026-11-01 사용자 결정 — 0655 결정 7). 빠질 경로에만 붙은 칸을 막으면 계산이
  받는 편집을 편집기만 막는다. 거꾸로 **빠지던 경로를 살리는 편집**(UPEH·효율 0 이하 → 0 보다
  큼)은 새 경로와 같다 — 빠지는 동안 멈추지 않던 그 경로의 빈 칸 · 행 없음이 살아나면 계산을
  멈추므로 세 표의 행을 먼저 갖추게 한다(`missing_required_rows`·`revived_route_rows`).
- **UPEH 의 MI 행 ST** — 0 이하면 계산 전체가 멈추는데 편집기 하한은 0 이다.
  `nonpositive_mi_st_rows`.

**이번 편집이 만든 것만 본다.** 이미 어긋나 있던 것까지 막으면, 상관없는 칸 하나를
고치려던 사람이 자기가 만들지 않은 문제에 걸려 아무것도 못 하게 된다.

**비교 기준은 활성 시나리오다.** 저장 리비전과 맞대면 이 세션에서 먼저 적용한 STEP 추가·
측정률 입력이 보이지 않아, 안내대로 채워도 저장하기 전에는 풀리지 않았다(2026-09-29).

**측정률 두 표를 함께 본다.** Lot 만 채우면 바로 다음 적용에서 `RQ_WF_RATIO` 로 같은
문구가 이어진다 — 한 번에 알려 주지 않으면 사용자가 같은 일을 두 번 겪는다.

적용 경계가 부르는 것은 판정과 문구를 묶은 `validate_upeh_edit`·`validate_required_edit` 다.
행 생성(`capacity_reference_editor`)은 부르는 쪽이 하고 결과 행만 넘긴다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from capa_simulation.services.frame_checks import strip_text_columns
from capa_simulation.services.frame_contracts import (
    UNIMPLEMENTED_BASES,
    normalize_area_name,
    normalize_month_column,
)
from capa_simulation.services.korean_particle import (
    with_object_particle,
    with_subject_particle,
)
from capa_simulation.services.unit_capacity import (
    PERFORMANCE_KEYS,
    RUN_DAY_KEYS,
    RUN_RATE_KEYS,
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
# 그 가운데 0 이하 값도 계산 전체를 멈추는 표와 값 컬럼(`unit_capacity._assert_positive`).
# 효율(`CAPA_RUN_RATE`) 0 이하는 그 경로만 제외 목록으로 빠지므로 여기 없다.
POSITIVE_REQUIRED_COLUMNS: dict[str, str] = {"RQ_VITAL": "편중률", "RQ_RUN_DAY": "RUN_DAY"}
# 오류문이 가리키는 기준 정보 화면의 표 이름(종류 단추 글).
REQUIRED_TABLE_LABELS: dict[str, str] = {
    "RQ_RUN_RATE": "효율",
    "RQ_VITAL": "여유율",
    "RQ_RUN_DAY": "일수",
}
REQUIRED_VALUE_COLUMNS: dict[str, str] = {
    "RQ_RUN_RATE": "CAPA_RUN_RATE",
    "RQ_VITAL": "편중률",
    "RQ_RUN_DAY": "RUN_DAY",
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


def _ratio_parts(missing: dict[str, pd.DataFrame], limit: int) -> list[str]:
    """측정률 결손을 탭마다 한 토막으로. 편집표 차원이 월을 뺀 8개라 월과 분류를 함께 적는다."""
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
            f"「{labels.get(table_name, table_name)}」 표에 {len(gap):,}건 — "
            f"{'; '.join(examples)}{more}"
        )
    return parts


def describe_missing_ratio_rows(missing: dict[str, pd.DataFrame], limit: int = 3) -> str:
    """사용자가 **어느 탭 어느 칸을 채워야 하는지** 알 수 있게 적는다.

    개수만 말하면 「그래서 뭘 하라는 것인가」가 남는다. 측정률 편집표의 차원은 월을 뺀
    8개이므로 월과 분류를 함께 적어야 그 칸을 찾을 수 있다.
    """
    if not missing:
        return ""
    # 측정률 행이 없으면 계산은 멈추지 않고 1.0 으로 가정해 이어 간다(40a09b8). 전에는 「계산
    # 화면을 열 때 … 멈춥니다」라고 적었는데 그 뒤로는 거짓이다. 막는 것은 정책이다 — 새로 만든
    # 경로를 가정값으로 시작하게 두지 않는다.
    return (
        "UPEH 에 새로 만든 경로의 측정률 행이 없습니다. 새 경로는 측정률을 먼저 갖춘 뒤에 "
        "만듭니다 — 이대로 두면 계산이 그 경로의 측정률을 1.0 으로 가정합니다. "
        + " / ".join(_ratio_parts(missing, limit))
        + ". 그 표에서 같은 행의 같은 달 칸에 값을 넣고 「변경사항 적용」을 누른 뒤 UPEH 를 "
        "다시 적용하세요 — 측정 대상이 아닌 경로라면 `1` 이 중립값입니다."
    )


def _required_keys(data: pd.DataFrame, keys: list[str], table_name: str) -> pd.DataFrame:
    """조인과 같은 규칙(월 정수·공백 제거)으로 줄인 키."""
    result = data[keys].copy()
    normalize_month_column(result, table_name)
    strip_text_columns(result, [key for key in keys if key != "생산계획년월"])
    return result.drop_duplicates().reset_index(drop=True)


def _keyed_values(
    data: pd.DataFrame, keys: list[str], value_column: str, table_name: str
) -> pd.DataFrame:
    """조인과 같은 규칙으로 줄인 키와 그 숫자값(숫자가 아니면 NaN)."""
    result = data[[*keys, value_column]].copy()
    normalize_month_column(result, table_name)
    strip_text_columns(result, [key for key in keys if key != "생산계획년월"])
    result[value_column] = pd.to_numeric(result[value_column], errors="coerce")
    return result.reset_index(drop=True)


def _calculated_upeh(upeh: pd.DataFrame) -> pd.DataFrame:
    """계산이 쓰는 `RQ_UPEH` 행. 쓰지 않는 소요기준(`UNIMPLEMENTED_BASES`) 행은 조인 전에 빠진다."""
    if upeh.empty:
        return upeh
    bases = upeh["소요기준"].astype("string").str.strip().str.upper()
    return upeh.loc[~bases.isin(UNIMPLEMENTED_BASES).fillna(False)]


# 제외를 가리는 표와 그 값 칸 — `unit_capacity.calculate_unit_capacity` 가 효율 0 이하·측정률 음수로
# 경로를 뺀다.
_RATIO_VALUE_COLUMNS: dict[str, str] = {"RQ_LOT_RATIO": "Lot 측정률", "RQ_WF_RATIO": "WF측정률"}


def _lenient_keys(data: pd.DataFrame, keys: Sequence[str]) -> pd.DataFrame:
    """맞대기만 할 키 — 계산과 같이 월은 정수, 글자는 앞뒤 공백을 떼고 `Area_Name` 은 대소문자를
    접는다. 깨진 값(월 형식·Area_Name)은 멈추지 않고 맞지 않는 키로 둔다 — 이 검사는 이번 편집이
    만든 것만 본다."""
    result = pd.DataFrame(index=range(len(data)))
    for key in keys:
        values = data[key].reset_index(drop=True)
        if key == "생산계획년월":
            result[key] = pd.to_numeric(values, errors="coerce").astype("Float64").round()
        elif key == "Area_Name":
            result[key] = values.astype("string").str.strip().str.casefold()
        else:
            result[key] = values.astype("string").str.strip()
    return result


def _joined_values(
    routes: pd.DataFrame, table: pd.DataFrame, keys: Sequence[str], value_column: str
) -> pd.Series:
    """경로마다 붙는 그 표의 값(숫자, 없으면 NaN). 겹친 키는 첫 행 — 계산이 멈출 꼴은 여기서 묻지
    않는다."""
    values = _lenient_keys(table, keys)
    values[value_column] = pd.to_numeric(
        table[value_column].reset_index(drop=True), errors="coerce"
    ).astype("float64")
    values = values.dropna(subset=list(keys)).drop_duplicates(subset=list(keys), keep="first")
    joined = routes[list(keys)].merge(values, on=list(keys), how="left")
    return joined[value_column]


def _live_upeh(upeh: pd.DataFrame, tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """제외 뒤에도 계산이 쓰는 `RQ_UPEH` 행 — 「경로가 쓰는 칸」 을 가리는 기준이다.

    계산이 쓰지 않는 소요기준(`_calculated_upeh`)에 더해 `unit_capacity.calculate_unit_capacity` 가
    빼는 경로 — Main 행 UPEH 0 이하, 붙는 효율(`RQ_RUN_RATE`) 0 이하, 붙는 Lot·WF 측정률 음수 — 를
    뺀다. 그런 경로에만 붙은 칸은 비거나 행이 없거나 0 이하여도 계산이 멈추지 않는다(2026-11-01
    사용자 결정 — 0655 결정 7). `tables` 에 없는 표로는 빼지 않는다. 행 차례·컬럼은 받은 `upeh`
    그대로다.
    """
    calculated = _calculated_upeh(upeh)
    if calculated.empty:
        return calculated
    routes = _lenient_keys(calculated, PERFORMANCE_KEYS)
    upeh_values = pd.to_numeric(calculated["UPEH"].reset_index(drop=True), errors="coerce")
    dropped = (routes["Area_Name"].eq("main") & upeh_values.le(0)).fillna(False).to_numpy(bool)
    run_rate = tables.get("RQ_RUN_RATE")
    if run_rate is not None and not run_rate.empty:
        rates = _joined_values(routes, run_rate, RUN_RATE_KEYS, "CAPA_RUN_RATE")
        dropped |= rates.le(0).fillna(False).to_numpy(bool)
    for table_name, value_column in _RATIO_VALUE_COLUMNS.items():
        ratio = tables.get(table_name)
        if ratio is not None and not ratio.empty:
            ratios = _joined_values(routes, ratio, PERFORMANCE_KEYS, value_column)
            dropped |= ratios.lt(0).fillna(False).to_numpy(bool)
    return calculated.loc[~dropped]


def _key_examples(
    found: pd.DataFrame,
    table_name: str,
    limit: int,
    value_column: str | None = None,
    value_label: str = "지금 값",
) -> str:
    """「월 · 키=값 / …」 예시 몇 개와 나머지 건수. `value_column` 을 주면 그 값도 붙인다."""
    examples = []
    for _, row in found.head(limit).iterrows():
        path = " / ".join(
            f"{key}={row[key]}" for key in REQUIRED_TABLE_KEYS[table_name] if key != "생산계획년월"
        )
        value = "" if value_column is None else _value_note(row[value_column], value_label)
        examples.append(f"{row['생산계획년월']} · {path}{value}")
    more = f" 외 {len(found) - limit:,}건" if len(found) > limit else ""
    return f"{'; '.join(examples)}{more}"


def _value_note(value: object, label: str) -> str:
    """값이 있으면 ` (label 값)`. 행이 없어 NaN 이면 붙이지 않는다."""
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "" if pd.isna(number) else f" ({label} {float(number):g})"


def cleared_keys_in_use(
    table_name: str,
    before: pd.DataFrame,
    after: pd.DataFrame,
    value_column: str,
    tables: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    """이번 편집이 값을 지운 (월 + 키) 가운데 제외 뒤에도 남는 `RQ_UPEH` 경로가 쓰는 것.

    효율·여유율·일수(`REQUIRED_TABLE_KEYS`)에만 쓴다. `before` 는 편집표를 만든 원본(같은 기간),
    `after` 는 적용할 행이다. **원본에 값이 있던 칸만** 센다 — 처음부터 비어 있던 칸은 이번 편집이
    만든 문제가 아니다. `tables` 는 적용 전 활성 시나리오의 표(`RQ_UPEH` 와 제외를 가리는
    효율·측정률)다. 경로는 계산이 쓰지 않는 소요기준(`UNIMPLEMENTED_BASES`)과 뒤에서 빠질 경로를
    빼고 본다(`_live_upeh`) — 효율을 고치는 편집이면 효율 0 이하는 고친 뒤 값으로 가린다.
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
    if cleared.empty:
        return empty
    used = _used_keys(table_name, after, tables)
    if used.empty:
        return empty
    return (
        cleared.merge(used, on=keys, how="inner")
        .sort_values(keys, kind="stable")
        .reset_index(drop=True)
    )


def _used_keys(
    table_name: str, after: pd.DataFrame, tables: Mapping[str, pd.DataFrame]
) -> pd.DataFrame:
    """그 표의 키 가운데 제외 뒤에도 남는 UPEH 경로가 쓰는 것 — 고친 표는 고친 뒤 값(`after`)으로
    본다."""
    keys = REQUIRED_TABLE_KEYS[table_name]
    upeh = tables.get("RQ_UPEH")
    if upeh is None or upeh.empty:
        return pd.DataFrame(columns=keys)
    live = _live_upeh(upeh, {**tables, table_name: after})
    if live.empty:
        return pd.DataFrame(columns=keys)
    return _required_keys(live, keys, "RQ_UPEH")


def describe_cleared_keys_in_use(
    label: str, table_name: str, cleared: pd.DataFrame, limit: int = 3
) -> str:
    """어느 칸(월·키)인지, 왜 막는지, 어떻게 풀지를 적는다."""
    # 「값을 넣거나」가 아니라 「0보다 큰 값」이다 — 여유율·일수는 0 도 계산을 멈추고(아래
    # `nonpositive_keys_in_use` 가 막는다), 효율 0 은 그 경로를 제외 목록으로 뺀다(2026-09-29
    # 2차 리뷰).
    return (
        f"「{label}」 표에서 값을 지운 칸 {len(cleared):,}개를 UPEH 경로가 씁니다 — "
        f"{_key_examples(cleared, table_name, limit)}. {label}에는 중립값이 없어 비우면 계산 "
        f"전체가 「{table_name} 연결값이 없는 대당 Capa 기준이 있습니다」로 멈춥니다. 그 칸에 "
        "0보다 큰 값을 넣거나, 그 경로를 먼저 UPEH 에서 비운 뒤 지우세요."
    )


def nonpositive_keys_in_use(
    table_name: str,
    before: pd.DataFrame,
    after: pd.DataFrame,
    value_column: str,
    tables: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    """이번 편집이 0 이하로 만든 (월 + 키) 가운데 제외 뒤에도 남는 `RQ_UPEH` 경로가 쓰는 것. 그 값도
    함께 준다.

    여유율·일수(`POSITIVE_REQUIRED_COLUMNS`)에만 쓴다. 둘은 0 이하면 계산 전체가
    「… 0보다 커야 합니다」(`unit_capacity._assert_positive`)로 멈추는데, 편집기는 0 을 받는다
    (편집 그리드 칸 하한 0 — `reference_grid.GRID_FORMATS`). 비우기만 막고 0 은 받아, 쓰는 칸에
    0 을 넣으면 적용·저장이 되고 계산이 멈췄다(2026-09-29 2차 리뷰).

    막는 범위는 계산과 같다 — **쓰는 경로가 없는 칸의 0 은 둔다**(계산이 멈추지 않는다). 0 이하
    검사는 제외 뒤에 남은 경로에만 돌므로 뒤에서 빠질 경로에만 붙은 칸도 쓰지 않는 칸이다.
    `cleared_keys_in_use` 와 같이 **원본에서 이미 0 이하이던 칸은 세지 않는다** — 이번 편집이 만든
    문제가 아니다. 인자의 뜻도 그 함수와 같다.
    """
    keys = REQUIRED_TABLE_KEYS[table_name]
    columns = [*keys, value_column]
    empty = pd.DataFrame(columns=columns)
    if after.empty:
        return empty
    new = _keyed_values(after, keys, value_column, table_name)
    new = new.loc[new[value_column].le(0)]
    if new.empty:
        return empty
    if not before.empty:
        old = _keyed_values(before, keys, value_column, table_name)
        old = old.loc[old[value_column].le(0), keys].drop_duplicates()
        if not old.empty:
            marked = new.merge(old, on=keys, how="left", indicator=True)
            new = marked.loc[marked["_merge"].eq("left_only"), columns]
    if new.empty:
        return empty
    used = _used_keys(table_name, after, tables)
    if used.empty:
        return empty
    return (
        new.merge(used, on=keys, how="inner")
        .sort_values(keys, kind="stable")
        .reset_index(drop=True)
    )


def describe_nonpositive_keys_in_use(
    label: str, table_name: str, value_column: str, found: pd.DataFrame, limit: int = 3
) -> str:
    """어느 칸(월·키)에 무슨 값을 넣었는지, 왜 막는지, 어떻게 풀지를 적는다."""
    examples = _key_examples(found, table_name, limit, value_column, "넣은 값")
    return (
        f"「{label}」 표에 0 이하 값을 넣은 칸 {len(found):,}개를 UPEH 경로가 씁니다 — "
        f"{examples}. 0 이하이면 계산 전체가 "
        f"「{table_name}의 {value_column} 값은 0보다 커야 합니다」로 멈춥니다. "
        "그 칸에 0보다 큰 값을 넣으세요 — 쓰는 UPEH 경로가 없는 칸은 0 이어도 됩니다."
    )


def missing_required_rows(
    before: pd.DataFrame,
    after: pd.DataFrame,
    tables: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """이번 UPEH 편집이 **새로 만든** 경로 가운데 효율·여유율·일수 연결값이 없는 것.

    `before`·`after` 는 적용 전후의 `RQ_UPEH`(같은 기간), `tables` 는 **적용 전 활성 시나리오**의 세
    표와, 있으면 측정률 두 표다(`missing_ratio_rows` 와 같은 기준 — 먼저 적용한 효율 입력이 보여야
    한다). 표 이름마다 결손 (월 + 키)와 지금 값(행이 없으면 NaN)을 돌려준다.

    측정률만 보던 검사가 이 셋을 보지 않아, 효율 행이 없는 달의 UPEH 칸을 채우면 적용은 성공하고
    계산 전체가 「RQ_RUN_RATE 연결값이 없는 대당 Capa 기준이 있습니다」로 멈췄다(2026-09-29 2차
    리뷰). 가리는 규칙은 계산과 같다.

    - 쓰지 않는 소요기준(`UNIMPLEMENTED_BASES`)의 행은 조인 전에 빠지므로 새 경로로 세지 않는다.
    - 여유율·일수는 **0 이하 값도 없는 것과 같다**(`_assert_positive` 로 멈춘다). 효율 0 이하는 그
      경로만 제외 목록으로 빠지므로 행이 있으면 있는 것이다.
    - 값이 숫자가 아닌 행은 없는 것으로 본다. 다만 거절 글이 인용하는 멈춤 글은 계산과 같이
      행 없음 · 값이 빈 행 · 숫자 아님을 가른다(`_missing_required_for`).
    - 새 경로가 뒤에서 빠질 경로(넣은 UPEH 0 이하 · 그 달 효율 0 이하 · 측정률 음수 —
      `_live_upeh`)면 세 표의 행이 없어도 계산이 멈추지 않으므로 세지 않는다.
    - 거꾸로 **빠지던 경로를 살린 것**(Main UPEH 0 이하 → 0 보다 큼)은 새 경로로 센다. 빠지는
      동안은 그 경로의 빈 칸 · 행 없음이 계산을 멈추지 않았으니(0655 결정 7) 살리는 이 편집이 만든
      멈춤이다.
    """
    added = added_performance_keys(_live_upeh(before, tables), _live_upeh(after, tables))
    return _missing_required_for(added, tables, tuple(REQUIRED_TABLE_KEYS))


# 결손 줄마다 계산이 무엇으로 멈추는지 — `unit_capacity._raise_on_unusable_values` 의 세 갈래(숫자
# 아님 → 빈 값 → 연결값 없음)와 같다. 값이 있으면(0 이하) 비운다. 거절 글이 계산이 실제로 낼 멈춤
# 글을 인용하게 한다 — 행은 있고 값만 빈 칸(BigDataQuery 원천)을 「연결값이 없는」 으로 인용하면 한
# 화면 안에서 등록 띠와 글이 갈렸다(E2E 2026-11-02).
_GAP_STATE_COLUMN = "_결손_까닭"
_GAP_NOT_NUMERIC = "not_numeric"
_GAP_BLANK = "blank"
_GAP_NO_ROW = "no_row"


def _gap_states(table: pd.DataFrame, keyed: pd.DataFrame, value_column: str) -> pd.Series:
    """`_keyed_values` 줄마다 값이 숫자가 아닐 때의 까닭 — 빈 값(결측·빈 글자)인가 숫자 아님인가.
    숫자면 결측이다. 빈 글자 판정은 계산(`unit_capacity._join_reference`)과 같다."""
    raw = table[value_column].reset_index(drop=True)
    blank = raw.isna()
    if not pd.api.types.is_numeric_dtype(raw):
        blank |= raw.astype("string").str.strip().eq("").fillna(False)
    states = pd.Series(_GAP_NOT_NUMERIC, index=keyed.index, dtype="object")
    states[blank.to_numpy(bool)] = _GAP_BLANK
    return states.where(keyed[value_column].isna())


def _missing_required_for(
    added: pd.DataFrame, tables: Mapping[str, pd.DataFrame], table_names: Sequence[str]
) -> dict[str, pd.DataFrame]:
    """경로 키(`PERFORMANCE_KEYS`) 가운데 `table_names` 표의 행이 없거나(값이 비거나 숫자 아님 포함)
    여유율·일수가 0 이하인 것 — 표 이름마다 결손 (월 + 키)와 지금 값(행이 없으면 NaN), 그리고 값이
    없는 줄의 까닭(`_GAP_STATE_COLUMN` — 행 없음 · 빈 값 · 숫자 아님)."""
    if added.empty:
        return {}
    result: dict[str, pd.DataFrame] = {}
    for table_name in table_names:
        keys = REQUIRED_TABLE_KEYS[table_name]
        table = tables.get(table_name)
        if table is None:
            continue
        value_column = REQUIRED_VALUE_COLUMNS[table_name]
        need = added[keys].drop_duplicates().reset_index(drop=True)
        keyed = _keyed_values(table, keys, value_column, table_name)
        keyed[_GAP_STATE_COLUMN] = _gap_states(table, keyed, value_column)
        have = keyed.loc[keyed[value_column].notna()].drop(columns=_GAP_STATE_COLUMN)
        if table_name in POSITIVE_REQUIRED_COLUMNS:
            # 0 이하 행은 결손으로 알리되 지금 값을 함께 적는다 — 「행이 없다」와 고칠 곳이 같다.
            usable = have.loc[have[value_column].gt(0), keys].drop_duplicates()
        else:
            usable = have[keys].drop_duplicates()
        if usable.empty:
            gap = need
        else:
            marked = need.merge(usable, on=keys, how="left", indicator=True)
            gap = marked.loc[marked["_merge"].eq("left_only"), keys]
        if gap.empty:
            continue
        values = have.drop_duplicates(subset=keys)
        if values.empty:
            gap = gap.assign(**{value_column: float("nan")})
        else:
            gap = gap.merge(values, on=keys, how="left")
        unusable = keyed.loc[keyed[_GAP_STATE_COLUMN].notna(), [*keys, _GAP_STATE_COLUMN]]
        if unusable.empty:
            gap = gap.assign(**{_GAP_STATE_COLUMN: None})
        else:
            gap = gap.merge(unusable.drop_duplicates(subset=keys), on=keys, how="left")
        no_value = gap[value_column].isna()
        gap[_GAP_STATE_COLUMN] = (
            gap[_GAP_STATE_COLUMN]
            .where(no_value)
            .mask(no_value & gap[_GAP_STATE_COLUMN].isna(), _GAP_NO_ROW)
        )
        result[table_name] = gap.sort_values(keys, kind="stable").reset_index(drop=True)
    return result


def describe_missing_path_rows(
    missing_ratio: dict[str, pd.DataFrame],
    missing_required: dict[str, pd.DataFrame],
    limit: int = 3,
    *,
    subject: str = "UPEH 에 새로 만들었거나 0 이하에서 다시 살린 경로",
    retry: str = "UPEH 를",
) -> str:
    """UPEH 에 새로 만든 경로가 기다리는 행을 **한 오류문**으로 적는다.

    측정률만 빠졌으면 `describe_missing_ratio_rows` 그대로다. 효율·여유율·일수가 빠졌으면 그 셋을
    먼저 적는다 — 이대로 두면 계산 전체가 멈춘다(측정률은 1.0 으로 가정하므로 정책으로 막는다).
    따로 알리면 하나를 채운 뒤 다음 적용에서 다른 표로 같은 일을 또 겪는다.
    """
    if not missing_required:
        return describe_missing_ratio_rows(missing_ratio, limit)
    parts: list[str] = []
    halts: list[str] = []
    for table_name, gap in missing_required.items():
        value_column = REQUIRED_VALUE_COLUMNS[table_name]
        parts.append(
            f"「{REQUIRED_TABLE_LABELS[table_name]}」 표에 {len(gap):,}건 — "
            f"{_key_examples(gap, table_name, limit, value_column)}"
        )
        values = pd.to_numeric(gap[value_column], errors="coerce")
        # 값이 없는 줄은 그 까닭대로 계산이 멈추는 글을 든다 — 계산의 차례(숫자 아님 → 빈 값 →
        # 연결값 없음)와 같다.
        states = gap[_GAP_STATE_COLUMN]
        if states.eq(_GAP_NOT_NUMERIC).any():
            halts.append(f"「{table_name}의 {value_column} 컬럼에 숫자가 아닌 값이 있습니다」")
        if states.eq(_GAP_BLANK).any():
            halts.append(f"「{table_name}의 {value_column} 값이 빈 대당 Capa 기준이 있습니다」")
        if states.eq(_GAP_NO_ROW).any():
            halts.append(f"「{table_name} 연결값이 없는 대당 Capa 기준이 있습니다」")
        if values.le(0).any():
            halts.append(f"「{table_name}의 {value_column} 값은 0보다 커야 합니다」")
    ratio_note = ""
    neutral_note = "."
    if missing_ratio:
        parts.extend(_ratio_parts(missing_ratio, limit))
        ratio_note = (
            " 측정률은 없으면 1.0 으로 가정하지만 새 경로는 측정률을 먼저 갖춘 뒤에 만듭니다."
        )
        neutral_note = " — 측정 대상이 아닌 경로라면 측정률은 `1` 이 중립값입니다."
    # 탭끼리는 문장으로 끊는다. 경로 안의 키가 이미 ` / ` 로 이어져 있어 같은 기호로 이으면
    # 어디서 다음 탭이 시작하는지 읽히지 않는다.
    return (
        f"{with_subject_particle(subject)} 쓰는 기준정보 행이 없습니다. "
        + "".join(f"{part}. " for part in parts)
        + "효율·여유율·일수에는 중립값이 없어 이대로 두면 계산 전체가 멈춥니다("
        + ", ".join(halts)
        + ")."
        + ratio_note
        + " 그 표에서 같은 행의 같은 달 칸에 먼저 0보다 큰 값을 넣고 「변경사항 적용」을 누른 뒤 "
        f"{retry} 다시 적용하세요" + neutral_note
    )


def _mi_st_values(upeh: pd.DataFrame) -> pd.DataFrame:
    """계산이 쓰는 MI 행의 경로 키(조인과 같은 규칙으로 줄인 것)와 ST 숫자값."""
    calculated = _calculated_upeh(upeh)
    columns = [*PERFORMANCE_KEYS, "ST"]
    if calculated.empty:
        return pd.DataFrame(columns=columns)
    result = calculated[PERFORMANCE_KEYS].copy()
    normalize_month_column(result, "RQ_UPEH")
    strip_text_columns(result, [key for key in PERFORMANCE_KEYS if key != "생산계획년월"])
    result["Area_Name"] = normalize_area_name(result["Area_Name"], "RQ_UPEH")
    result["ST"] = pd.to_numeric(calculated["ST"], errors="coerce").to_numpy()
    return result.loc[result["Area_Name"].eq("MI"), columns].reset_index(drop=True)


def nonpositive_mi_st_rows(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    """이번 UPEH 편집이 0 이하로 만든 MI 행 ST. (월 + 경로)와 넣은 값을 돌려준다.

    MI 행은 ST(분)로 환산 UPEH(`60 ÷ ST`)를 만든다. 계산이 쓰는 MI 행(`UNIMPLEMENTED_BASES` 제외)의
    ST 가 0 이하면 대당 Capa 전체가 「RQ_UPEH의 MI 행 ST 값은 0보다 커야 합니다」로 멈추는데
    (`unit_capacity._prepare_performance`), 편집기는 하한이 0 이라 0 을 받는다. Main 행 UPEH 0 은 그
    경로만 제외 목록으로 빠지므로 여기 없다.
    `cleared_keys_in_use` 와 같이 **원본에서 이미 0 이하이던 칸은 세지 않는다.**
    """
    columns = [*PERFORMANCE_KEYS, "ST"]
    new = _mi_st_values(after)
    new = new.loc[new["ST"].le(0)]
    if new.empty:
        return pd.DataFrame(columns=columns)
    old = _mi_st_values(before)
    old = old.loc[old["ST"].le(0), PERFORMANCE_KEYS].drop_duplicates()
    if not old.empty:
        marked = new.merge(old, on=PERFORMANCE_KEYS, how="left", indicator=True)
        new = marked.loc[marked["_merge"].eq("left_only"), columns]
    return new.sort_values(PERFORMANCE_KEYS, kind="stable").reset_index(drop=True)


def describe_nonpositive_mi_st_rows(found: pd.DataFrame, limit: int = 3) -> str:
    """어느 (월, 경로)에 무슨 ST 를 넣었는지, 왜 막는지, 어떻게 풀지를 적는다."""
    examples = []
    for _, row in found.head(limit).iterrows():
        path = " / ".join(f"{key}={row[key]}" for key in PERFORMANCE_KEYS if key != "생산계획년월")
        examples.append(f"{row['생산계획년월']} · {path}{_value_note(row['ST'], '넣은 값')}")
    more = f" 외 {len(found) - limit:,}건" if len(found) > limit else ""
    return (
        f"「UPEH」 표에서 MI 행 ST 를 0 이하로 넣은 칸 {len(found):,}개 — "
        f"{'; '.join(examples)}{more}. MI 행은 ST(분)로 환산 UPEH(60 ÷ ST)를 만들어 0 이하이면 "
        "계산 전체가 「RQ_UPEH의 MI 행 ST 값은 0보다 커야 합니다」로 멈춥니다. 그 칸에 0보다 큰 "
        "ST 를 넣거나, 그 달 경로를 쓰지 않으려면 칸을 비우세요."
    )


def validate_upeh_edit(
    before_upeh: pd.DataFrame,
    rows: pd.DataFrame,
    scenario_tables: Mapping[str, pd.DataFrame],
) -> None:
    """UPEH 편집의 적용 행 `rows` 가 새로 만든 경로에 기다리는 행이 없으면 `ValueError` 를 낸다.

    `before_upeh` 는 편집표를 만든 같은 기간의 시나리오 `RQ_UPEH`, `scenario_tables` 는
    **적용 전 활성 시나리오**의 표들이다(측정률 두 표와 효율·여유율·일수를 꺼내 쓴다).

    빈 월 칸을 채우는 것은 값 수정이 아니라 **경로를 하나 더 만드는 일**이다. 측정률 행이
    없으면 계산은 1.0 으로 가정해 이어 가지만(40a09b8), 새 경로는 측정률을 먼저 갖추게 한다
    (정책 — 2026-09-23 사내에서 겪은 일로 들어온 검사). **이번 편집이 새로 만든 조합만** 본다
    — 이미 어긋나 있던 것까지 막으면 상관없는 칸을 고치려던 사람이 자기가 만들지 않은 문제에
    걸린다. 비교 기준은 **적용 전 활성 시나리오**다. 저장 리비전과 맞대면 이 세션에서 먼저
    적용한 STEP 추가·측정률 입력이 안 보여, STEP 을 더한 뒤에는 UPEH 어느 칸을 고쳐도
    막혔고 안내대로 측정률을 채워도 저장 전에는 풀리지 않았다(2026-09-29).

    효율·여유율·일수도 본다. 측정률(없으면 1.0 가정)만 보고 이 셋을 보지 않아, 효율 행이 없는
    달을 채우면 적용은 성공하고 계산 전체가 「RQ_RUN_RATE 연결값이 없는 …」로 멈췄다
    (2026-09-29 2차 리뷰). 측정률 결손과 **한 오류문**으로 알린다 — 따로 알리면 하나를 채운 뒤
    다음 적용에서 다른 표로 같은 일을 또 겪는다.

    MI 행 ST 를 0 이하로 넣은 칸도 본다(`nonpositive_mi_st_rows`). 경로 결손과 함께 있으면 그
    뒤에 이어 한 오류문으로 낸다.
    """
    missing_ratio = missing_ratio_rows(
        added_performance_keys(before_upeh, rows),
        {name: scenario_tables[name] for name in RATIO_TABLES},
    )
    missing_required = missing_required_rows(
        before_upeh,
        rows,
        {name: scenario_tables[name] for name in (*REQUIRED_TABLE_KEYS, *RATIO_TABLES)},
    )
    problems: list[str] = []
    if missing_ratio or missing_required:
        problems.append(describe_missing_path_rows(missing_ratio, missing_required))
    nonpositive_st = nonpositive_mi_st_rows(before_upeh, rows)
    if not nonpositive_st.empty:
        problems.append(describe_nonpositive_mi_st_rows(nonpositive_st))
    if problems:
        raise ValueError(" ".join(problems))


def validate_required_edit(
    table_name: str,
    label: str,
    source: pd.DataFrame,
    rows: pd.DataFrame,
    value_column: str,
    scenario_tables: Mapping[str, pd.DataFrame],
) -> None:
    """효율·여유율·일수의 적용 행 `rows` 가 **UPEH 경로가 쓰는 칸**을 깨면 `ValueError` 를 낸다.

    세 표에는 측정률의 1.0 같은 중립값이 없다. 경로가 쓰는 (키, 월) 칸을 비우면 적용은 성공으로
    알리고 행이 지워지는데, 그 뒤 계산 전체가 「… 연결값이 없는 대당 Capa 기준이 있습니다」로
    멈췄다(2026-09-29 버그 보고 횡전개). 쓰는 경로가 없는 칸을 지우는 것은 그대로 둔다. `source` 는
    편집표를 만든 같은 기간의 원본, `scenario_tables` 는 적용 전 활성 시나리오의 표다(`RQ_UPEH` 와
    뒤에서 빠질 경로를 가리는 효율·측정률을 꺼내 쓴다 — `_live_upeh`).

    여유율·일수(`POSITIVE_REQUIRED_COLUMNS`)는 0 이하도 계산 전체를 「… 0보다 커야 합니다」로
    멈춘다. 편집기는 0 을 받아(`min_value` 0) 비우기만 막던 동안 쓰는 칸의 0 이 적용·저장됐다
    (2026-09-29 2차 리뷰). 쓰는 경로가 없는 칸의 0 은 계산이 멈추지 않으므로 둔다 — 막는 범위를
    계산과 같게 하려고 편집기의 하한은 올리지 않는다. 효율 0 은 그 경로만 제외라 여기 없다.
    두 문제가 함께 있으면 비운 칸 → 0 이하 칸 순서로 한 오류문에 잇는다.

    효율 편집이 0 이하이던 칸을 0 보다 크게 바꿔 빠지던 경로를 살리면 그 경로의 여유율·일수 행도
    본다(`revived_route_rows`) — 빠지는 동안 멈추지 않던 빈 칸 · 행 없음이 살아나면 계산 전체가
    멈춘다. 이 문제는 맨 뒤에 잇는다.
    """
    problems: list[str] = []
    cleared = cleared_keys_in_use(table_name, source, rows, value_column, scenario_tables)
    if not cleared.empty:
        problems.append(describe_cleared_keys_in_use(label, table_name, cleared))
    if table_name in POSITIVE_REQUIRED_COLUMNS:
        nonpositive = nonpositive_keys_in_use(
            table_name, source, rows, value_column, scenario_tables
        )
        if not nonpositive.empty:
            problems.append(
                describe_nonpositive_keys_in_use(label, table_name, value_column, nonpositive)
            )
    revived = revived_route_rows(table_name, source, rows, scenario_tables)
    if revived:
        problems.append(
            describe_missing_path_rows(
                {},
                revived,
                subject=f"「{label}」 표에서 0 이하이던 칸을 0보다 크게 바꿔 다시 계산에 드는 경로",
                retry=with_object_particle(label),
            )
        )
    if problems:
        raise ValueError(" ".join(problems))


def revived_route_rows(
    table_name: str,
    before: pd.DataFrame,
    after: pd.DataFrame,
    tables: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """이번 효율 편집이 0 이하에서 0 보다 크게 바꿔 **다시 계산에 드는** 경로 가운데 여유율·일수
    행이 없거나 0 이하인 것. 효율(`RQ_RUN_RATE`) 밖의 표는 경로를 빼지 않아 빈 결과다.

    효율 0 이하 경로는 계산에서 빠지므로 그 경로에만 붙은 여유율·일수의 빈 칸 · 행 없음은 계산을
    멈추지 않는다(2026-11-01 사용자 결정 — 0655 결정 7). 그 효율을 0 보다 크게 고치면 경로가 살아나
    멈추므로, 이 편집이 만든 멈춤으로 막는다. `before` 는 편집표를 만든 같은 기간의 원본, `after` 는
    적용할 행, `tables` 는 적용 전 활성 시나리오의 표다(`validate_required_edit` 와 같다). 살아나는
    경로는 그 기간 안의 칸만이다 — 다른 측정률 음수 · Main UPEH 0 이하로 여전히 빠지면 세지 않는다.
    """
    if table_name != "RQ_RUN_RATE" or before.empty or after.empty:
        return {}
    keys = REQUIRED_TABLE_KEYS[table_name]
    value_column = REQUIRED_VALUE_COLUMNS[table_name]
    old = _keyed_values(before, keys, value_column, table_name)
    old = old.loc[old[value_column].le(0), keys].drop_duplicates()
    new = _keyed_values(after, keys, value_column, table_name)
    new = new.loc[new[value_column].gt(0), keys].drop_duplicates()
    revived = old.merge(new, on=keys, how="inner")
    upeh = tables.get("RQ_UPEH")
    if revived.empty or upeh is None or upeh.empty:
        return {}
    live = _live_upeh(upeh, {**tables, table_name: after})
    if live.empty:
        return {}
    routes = _performance_keys(live, "RQ_UPEH").merge(revived, on=keys, how="inner")
    return _missing_required_for(routes, tables, ("RQ_VITAL", "RQ_RUN_DAY"))
