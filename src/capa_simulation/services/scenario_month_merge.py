# Purpose: 겹침 정책으로 월별 원본을 정해 16표를 합치고 무월 표 보충·결과 결손·월 축을 검증한다.

from collections.abc import Mapping, Sequence
from typing import Literal, NamedTuple

import pandas as pd

from capa_simulation.services.frame_contracts import (
    UNIMPLEMENTED_BASES,
    normalize_month_column,
    require_columns,
)
from capa_simulation.services.load_calculator import drop_unplanned_rows
from capa_simulation.services.month_filter import MONTH_COLUMN
from capa_simulation.services.scenario_transform import (
    MONTHLY_TABLES,
    NON_MONTHLY_TABLES,
    copy_scenario_tables,
    format_month_runs,
    scenario_months,
    validate_month_axes,
)
from capa_simulation.services.virtual_product import PRODUCT_KEY_COLUMNS
from capa_simulation.settings import format_month

OverlapPolicy = Literal["reject", "base", "donor"]

# 월 없는 표를 합치는 규칙 — **사용자 확인 대기 기본안**(사내 리뷰 202610120655 1장). 여기 있는
# 표는 겹치는 키를 베이스 값으로 두고, 베이스에 없는 키의 행만 덧붙일 쪽에서 보충한다. 없는 표는
# 베이스 그대로다. 이 사전을 비우면 네 표 모두 베이스 그대로가 된다.
#
# 베이스 것만 남기면 덧붙인 달이 쓰는 공정·제품의 기준이 빠진다. 공정이 빠지면 대당 Capa 계산이
# 멈추고(`RQ_MODULE` — 앱에서 고칠 수 없다), 제품이 빠지면 그 계획이 부하량에서 조용히 빠진다
# (`RQ_CHIP_*` — 가상 제품이 대표적이다).
#
# - Chip 두 표의 키는 계산이 계획에 붙이는 `제품정보 + Stack` 이다. `WF 구분` 은 한 제품의 행을
#   펼치는 칸이라 키에 넣지 않는다 — 넣으면 베이스 제품에 덧붙일 쪽의 WF 구분 행이 섞여 그 제품의
#   부하가 바뀐다. 제품 단위로 통째로 베이스 것이거나 통째로 덧붙일 쪽 것이다.
# - `RQ_DISPLAY_ORDER` 는 계산에 쓰이지 않고 불러올 때 공용 표시순서가 덮으므로 베이스 그대로다.
NON_MONTHLY_SUPPLEMENT_KEYS: Mapping[str, tuple[str, ...]] = {
    "RQ_CHIP_QTY": PRODUCT_KEY_COLUMNS,
    "RQ_CHIP_EQ": PRODUCT_KEY_COLUMNS,
    "RQ_MODULE": ("공정",),
}

# 결손 문구에 싣는 키 예시 수.
GAP_EXAMPLE_LIMIT = 5


def non_monthly_rule(name: str) -> str:
    """월 없는 표 한 장을 합치는 규칙을 화면·출처 메모에 적을 말로."""
    keys = NON_MONTHLY_SUPPLEMENT_KEYS.get(name)
    if not keys:
        return "베이스 그대로"
    return f"겹치는 키는 베이스, 베이스에 없는 {' + '.join(keys)}만 덧붙일 쪽에서 보충"


def _key_frame(frame: pd.DataFrame, keys: Sequence[str]) -> pd.DataFrame:
    """계산의 연결과 같이 키 칸을 글자로 올리고 앞뒤 공백만 뗀다(`strip_text_columns`)."""
    return pd.DataFrame(
        {key: frame[key].astype("string").str.strip() for key in keys}, index=frame.index
    )


def _complete_keys(frame: pd.DataFrame, keys: Sequence[str]) -> list[tuple[str, ...] | None]:
    """행마다 정규화한 키. 빈 칸이 있는 키는 `None` — 어느 쪽과도 맞대지 않는다."""
    return [
        None if any(pd.isna(value) for value in row) else tuple(str(value) for value in row)
        for row in _key_frame(frame, keys).itertuples(index=False, name=None)
    ]


def _supplement_rows(name: str, base: pd.DataFrame, donor: pd.DataFrame) -> pd.DataFrame:
    """덧붙일 쪽 행 가운데 베이스에 그 키가 없는 것. 규칙이 베이스 그대로인 표는 빈 표다.

    빈 칸이 든 키의 행은 보충하지 않는다 — 계산이 그런 키를 오류로 받는 표가 있다(`RQ_CHIP_EQ`).
    """
    keys = NON_MONTHLY_SUPPLEMENT_KEYS.get(name)
    if not keys or donor.empty:
        return donor.iloc[:0]
    require_columns(base, keys, name)
    require_columns(donor, keys, name)
    known = {key for key in _complete_keys(base, keys) if key is not None}
    return donor.loc[[key is not None and key not in known for key in _complete_keys(donor, keys)]]


def compare_non_monthly_tables(
    base: Mapping[str, pd.DataFrame], donor: Mapping[str, pd.DataFrame]
) -> pd.DataFrame:
    """행·컬럼 순서와 dtype 표현을 제외한 값 차이, 양쪽 행 수와 보충할 행 수를 표시한다."""
    rows = []
    for name in NON_MONTHLY_TABLES:
        left, right = base[name], donor[name]
        equal = set(left.columns) == set(right.columns)
        if equal:
            columns = sorted(left.columns)
            try:
                pd.testing.assert_frame_equal(
                    left[columns].sort_values(columns).reset_index(drop=True),
                    right[columns].sort_values(columns).reset_index(drop=True),
                    check_dtype=False,
                    check_exact=True,
                )
            except AssertionError:
                equal = False
        supplement = len(_supplement_rows(name, left, right))
        rows.append(
            {
                "표": name,
                "베이스 행 수": len(left),
                "덧붙일 쪽 행 수": len(right),
                "비교": (
                    "같음"
                    if equal
                    else "다름 · 베이스에 없는 키 보충"
                    if supplement
                    else "다름 · 베이스 유지"
                ),
                "보충 행 수": supplement,
                "합치는 규칙": non_monthly_rule(name),
            }
        )
    return pd.DataFrame(rows)


def _prepare_month_sources(
    base: Mapping[str, pd.DataFrame],
    donor: Mapping[str, pd.DataFrame],
    start_month: int,
    end_month: int,
    overlap_policy: OverlapPolicy,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], pd.DataFrame]:
    """미리보기와 저장이 같은 범위 검증 및 월 전체 선택 규칙을 사용하게 한다."""
    if overlap_policy not in ("reject", "base", "donor"):
        raise ValueError(f"지원하지 않는 월 겹침 정책입니다: {overlap_policy}")
    bounds = pd.DataFrame({MONTH_COLUMN: [start_month, end_month]})
    normalize_month_column(bounds, "덧붙일 월 범위")
    start_month, end_month = (int(value) for value in bounds[MONTH_COLUMN])
    if start_month > end_month:
        raise ValueError("덧붙일 시작 월은 종료 월보다 클 수 없습니다.")
    base_copy = copy_scenario_tables(base)
    donor_copy = copy_scenario_tables(donor)
    selected_months = {
        month for month in scenario_months(donor_copy) if start_month <= month <= end_month
    }
    if not selected_months:
        raise ValueError("선택한 범위에 덧붙일 월 데이터가 없습니다.")
    base_months = set(scenario_months(base_copy))
    overlap_source = {
        "reject": "미선택 · 저장 차단",
        "base": "베이스",
        "donor": "덧붙일 쪽",
    }[overlap_policy]
    rows = []
    for month in sorted(base_months | selected_months):
        in_base, in_donor = month in base_months, month in selected_months
        selected_source = (
            overlap_source if in_base and in_donor else "베이스" if in_base else "덧붙일 쪽"
        )
        rows.append(
            {
                MONTH_COLUMN: month,
                "베이스": in_base,
                "덧붙일 쪽": in_donor,
                "선택 출처": selected_source,
            }
        )
    return base_copy, donor_copy, pd.DataFrame(rows)


def preview_month_sources(
    base: Mapping[str, pd.DataFrame],
    donor: Mapping[str, pd.DataFrame],
    start_month: int,
    end_month: int,
    *,
    overlap_policy: OverlapPolicy = "reject",
) -> pd.DataFrame:
    """베이스 전체와 선택 범위의 덧붙일 월을 비교하고 월별 선택 출처를 보여 준다."""
    _, _, preview = _prepare_month_sources(base, donor, start_month, end_month, overlap_policy)
    return preview


def merge_scenario_months(
    base: Mapping[str, pd.DataFrame],
    donor: Mapping[str, pd.DataFrame],
    start_month: int,
    end_month: int,
    *,
    overlap_policy: OverlapPolicy = "reject",
) -> dict[str, pd.DataFrame]:
    """겹친 월 전체를 고른 원본에서 가져온다. 월 없는 표는 `NON_MONTHLY_SUPPLEMENT_KEYS` 대로."""
    result, donor_copy, preview = _prepare_month_sources(
        base, donor, start_month, end_month, overlap_policy
    )
    blocked = preview.loc[preview["선택 출처"].eq("미선택 · 저장 차단"), MONTH_COLUMN]
    if not blocked.empty:
        sample = ", ".join(format_month(int(month)) for month in blocked.iloc[:12])
        raise ValueError(
            f"베이스와 {len(blocked)}개월이 겹쳐 저장할 수 없습니다: {sample}. "
            "겹친 월에 사용할 시나리오를 선택하거나 덧붙일 월 범위를 좁혀 주세요."
        )
    base_months = preview.loc[preview["선택 출처"].eq("베이스"), MONTH_COLUMN]
    donor_months = preview.loc[preview["선택 출처"].eq("덧붙일 쪽"), MONTH_COLUMN]
    for name in MONTHLY_TABLES:
        if set(result[name].columns) != set(donor_copy[name].columns):
            raise ValueError(f"{name}의 두 시나리오 컬럼이 일치하지 않습니다.")
        # 제품·공정 키가 달라도 패자의 그 월 행은 전부 제외한다. 누락값을 보충하지 않는다.
        result[name] = result[name].loc[result[name][MONTH_COLUMN].isin(base_months)].copy()
        addition = donor_copy[name].loc[donor_copy[name][MONTH_COLUMN].isin(donor_months)]
        if not addition.empty:
            result[name] = pd.concat([result[name], addition], ignore_index=True)
    for name in NON_MONTHLY_TABLES:
        supplement = _supplement_rows(name, result[name], donor_copy[name])
        if supplement.empty:
            continue
        if set(result[name].columns) != set(supplement.columns):
            raise ValueError(
                f"{name}의 두 시나리오 컬럼이 일치하지 않아 덧붙일 쪽 키를 보충할 수 없습니다."
            )
        result[name] = pd.concat(
            [result[name], supplement[list(result[name].columns)]], ignore_index=True
        )
    validate_month_axes(result)
    return result


class TableGaps(NamedTuple):
    """머지 결과 16표의 결손. `blocking` 은 계산이 멈추는 것, `warnings` 는 조용히 빠지는 것."""

    blocking: tuple[str, ...]
    warnings: tuple[str, ...]


def _uncovered_keys(
    rows: pd.DataFrame, keys: Sequence[str], reference: pd.DataFrame
) -> list[tuple[tuple[str, ...], tuple[int, ...], int]]:
    """`rows` 가 쓰는 키 가운데 `reference` 에 없는 것과 그 키의 달·행 수(키 차례)."""
    known = {key for key in _complete_keys(reference, keys) if key is not None}
    months = pd.to_numeric(rows[MONTH_COLUMN], errors="coerce")
    found: dict[tuple[str, ...], list[int]] = {}
    for key, month in zip(_complete_keys(rows, keys), months, strict=True):
        if key is None or key in known:
            continue
        found.setdefault(key, [])
        if pd.notna(month):
            found[key].append(int(month))
    return [(key, tuple(sorted(set(found[key]))), len(found[key])) for key in sorted(found)]


def _gap_examples(gaps: list[tuple[tuple[str, ...], tuple[int, ...], int]]) -> str:
    shown = ", ".join(
        f"{' · '.join(key)}({format_month_runs(months)})"
        for key, months, _ in gaps[:GAP_EXAMPLE_LIMIT]
    )
    rest = len(gaps) - GAP_EXAMPLE_LIMIT
    return shown + (f" 외 {rest}개" if rest > 0 else "")


def merged_table_gaps(tables: Mapping[str, pd.DataFrame]) -> TableGaps:
    """월 표가 쓰는 키가 월 없는 표에 있는지 본다. 머지는 두 쪽을 다른 단위로 합치기 때문이다.

    월 표는 달마다 한쪽 원본의 것을 통째로 가져오지만 월 없는 표는 그렇지 않다. 그래서 결과에서만
    생기는 결손이 이 둘 사이에 있다.

    - `RQ_UPEH` 가 쓰는 공정에 `RQ_MODULE` 이 없으면 대당 Capa 계산이 멈춘다 → 막는다. 계산에서
      먼저 빠지는 소요기준(BOX·PCB) 행은 보지 않는다. `RQ_MODULE` 은 앱에서 고칠 수 없다.
    - 계획(생산수량 > 0) 제품에 `RQ_CHIP_QTY`·`RQ_CHIP_EQ` 가 없으면 그 계획이 부하량·Density
      에서 멈추지 않고 빠진다 → 경고한다.
    """
    blocking: list[str] = []
    upeh = tables["RQ_UPEH"]
    implemented = upeh.loc[
        ~upeh["소요기준"].astype("string").str.strip().str.upper().isin(UNIMPLEMENTED_BASES)
    ]
    module_gaps = _uncovered_keys(implemented, ("공정",), tables["RQ_MODULE"])
    if module_gaps:
        blocking.append(
            f"RQ_MODULE(모듈수)에 없는 공정 {len(module_gaps)}개 — RQ_UPEH 가 쓰는 공정이라 대당 "
            f"Capa 계산이 멈춥니다: {_gap_examples(module_gaps)}. RQ_MODULE 은 앱에서 고칠 수 "
            "없어 이대로 저장하면 그 시나리오는 계산도 발행도 할 수 없습니다. 이 공정의 모듈수를 "
            "가진 시나리오를 베이스나 덧붙일 쪽으로 골라 다시 머지하거나, 원천을 다시 등록하세요."
        )
    warnings: list[str] = []
    plan = drop_unplanned_rows(tables["RQ_PKG_PLAN"])
    for name, effect in (
        ("RQ_CHIP_QTY", "부하량·소요대수"),
        ("RQ_CHIP_EQ", "Density 환산(HOME)"),
    ):
        gaps = _uncovered_keys(plan, PRODUCT_KEY_COLUMNS, tables[name])
        if gaps:
            rows = sum(count for _, _, count in gaps)
            warnings.append(
                f"{name}에 없는 제품 {len(gaps)}개 · 계획 {rows}행은 {effect}에서 빠집니다"
                f"(계산은 멈추지 않습니다): {_gap_examples(gaps)}."
            )
    return TableGaps(tuple(blocking), tuple(warnings))
