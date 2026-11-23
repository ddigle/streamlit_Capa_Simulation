# Purpose: CUSTOM 제품 구분 키의 값 규칙과 두 부품이 계산 끝까지 접히지 않는 끝단 계약을 고정한다.

"""CUSTOM 키 — 값 정규화와 끝단 계약.

원천 `CUSTOM` 은 같은 제품의 부품을 가르는 값이다. 빈 값을 NA 로 두면 조인 · 접기에서 행이 빠지거나
한 줄로 접히므로 파생 경계에서 한 번 `CUSTOM_BLANK` 로 세운다. 시험은 표지 글자를 따로 적지 않는다.
표지는 편집표 붙여넣기 · CSV 왕복에서도 키 값으로 남아야 한다.

끝단 시험은 RQ 여덟 표 · 계산 키에 CUSTOM 이 오른 뒤의 계약이다. CUSTOM 이 한 값이면 결과가 그
값과 상관없이 같고, 한 제품이 두 부품이면 Wafer · 대당 Capa · 소요대수가 부품마다 따로 난다 — 그
합이 부품 하나씩 따로 돌린 값과 같아야 조인이 두 부품 행을 겹쳐 붙이지 않은 것이다. 견본은
`custom_key_tables.two_part_tables`(내장 시드의 한 제품을 두 부품으로 가른 것)다.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from uuid import uuid4

import pandas as pd
import pytest
from custom_key_tables import (
    PART_A,
    PART_B,
    TWO_PART_PRODUCT,
    custom_keyed_tables,
    single_part_tables,
    two_part_tables,
)
from test_core_data_pipeline import _core_data_row

from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.clipboard_table import parse_clipboard_table
from capa_simulation.services.core_data_derivation import (
    ACTIVE_CORE_COLUMNS,
    CUSTOM_BLANK,
    build_q_core_data,
    custom_sort_key,
    normalize_custom_values,
)
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.load_calculator import (
    calculate_chip_and_wafer_loads,
    calculate_density_load,
)
from capa_simulation.services.reference_csv import (
    parse_reference_edit_clipboard,
    reference_edit_csv_bytes,
    strip_excel_text_guard,
)


def test_blank_custom_values_become_the_blank_marker() -> None:
    """NULL · 빈 글자 · 공백뿐인 값은 모두 같은 표지 하나가 된다."""
    values = pd.Series([None, "", "   ", pd.NA], dtype="object")

    assert normalize_custom_values(values).tolist() == [CUSTOM_BLANK] * 4


def test_surrounding_whitespace_is_stripped_and_values_are_kept() -> None:
    """앞뒤 공백만 떼고 값은 원천 글자 그대로다."""
    values = pd.Series([" DEMO_CUSTOM_A ", "DEMO_CUSTOM_B"], dtype="string")

    assert normalize_custom_values(values).tolist() == ["DEMO_CUSTOM_A", "DEMO_CUSTOM_B"]


def test_case_variants_are_unified_to_the_most_used_spelling() -> None:
    """대소문자만 다른 표기는 가장 많이 쓰인 표기로 모인다 — 한 부품이 두 키로 갈리지 않는다."""
    values = pd.Series(["DEMO_CUSTOM_A", "demo_custom_a", "DEMO_CUSTOM_A"], dtype="string")

    assert normalize_custom_values(values).tolist() == ["DEMO_CUSTOM_A"] * 3


def test_the_blank_marker_survives_the_real_paste_path() -> None:
    """붙여넣기 입구(`parse_clipboard_table`)는 표지를 빈 값으로 읽지 않는다."""
    content = f"제품정보\tCUSTOM\nDEMO_P1\t{CUSTOM_BLANK}\n"

    assert parse_clipboard_table(content, "RQ_YLD")["CUSTOM"].tolist() == [CUSTOM_BLANK]


def test_the_blank_marker_survives_the_edit_csv_round_trip() -> None:
    """편집표 양식을 내려받아 Excel 로 열었다 다시 붙여넣어도 표지가 키 값으로 남는다.

    표지가 빈 값으로 읽히면 「분류 칸이 비어 있는 행」 으로 붙여넣기가 막힌다(`_normalized_keys`).
    """
    template = pd.DataFrame(
        {
            "제품정보": ["DEMO_P1", "DEMO_P1"],
            "Stack": ["8H", "8H"],
            "CUSTOM": [CUSTOM_BLANK, "DEMO_CUSTOM_A"],
            "202701": [0.9, 0.8],
        }
    )
    key_columns = ["제품정보", "Stack", "CUSTOM"]
    downloaded = reference_edit_csv_bytes(template, key_columns).decode("utf-8-sig")
    # Excel 로 열면 `="…"` 껍데기를 계산해 안의 글자만 보이고, 그 셀을 복사하면 그 글자가 온다.
    opened = pd.read_csv(io.StringIO(downloaded), dtype="object", keep_default_na=False)
    opened["CUSTOM"] = opened["CUSTOM"].map(strip_excel_text_guard)

    result = parse_reference_edit_clipboard(
        opened.to_csv(index=False, sep="\t"), template, key_columns, "RQ_YLD"
    )

    assert result["CUSTOM"].tolist() == [CUSTOM_BLANK, "DEMO_CUSTOM_A"]


def test_the_derivation_boundary_carries_the_normalized_custom() -> None:
    """작업 프레임이 CUSTOM 을 싣고, 빈 원천 값은 표지가 된다."""
    blank = _core_data_row()
    blank["CUSTOM"] = pd.Series(["  "], dtype="string")
    padded = _core_data_row()
    padded["CUSTOM"] = pd.Series([" DEMO_CUSTOM_A "], dtype="string")

    assert "CUSTOM" in ACTIVE_CORE_COLUMNS
    assert build_q_core_data(blank)["CUSTOM"].tolist() == [CUSTOM_BLANK]
    assert build_q_core_data(padded)["CUSTOM"].tolist() == ["DEMO_CUSTOM_A"]


def _product_rule(page: str, tab: str) -> pd.DataFrame:
    """제품정보 오름차순 규칙 하나 — 같은 제품의 행은 규칙 열쇠가 같다."""
    return pd.DataFrame(
        {
            "페이지 구분": [page],
            "탭 구분": [tab],
            "정렬우선순위": [1],
            "분류컬럼": ["제품정보"],
            "정렬방식": ["오름차순"],
            "분류값": [None],
            "값표시순서": [None],
            "활성여부": ["Y"],
        }
    )


def test_the_custom_sort_key_puts_the_blank_marker_last() -> None:
    """부품 차례는 대소문자를 접은 글자 → 원문 오름차순이고, 빈 값(표지 · NA · 빈 글자)은 끝이다.
    파이썬 기본 차례는 표지를 글자 앞에 둔다."""
    values = ["b", CUSTOM_BLANK, "A", None, "a", "B", "  "]

    assert sorted(values, key=custom_sort_key)[:4] == ["A", "a", "B", "b"]
    assert all(custom_sort_key(value) == custom_sort_key(CUSTOM_BLANK) for value in (None, "  "))
    assert sorted(["DEMO_CUSTOM_B", CUSTOM_BLANK, "DEMO_CUSTOM_A"], key=custom_sort_key) == [
        "DEMO_CUSTOM_A",
        "DEMO_CUSTOM_B",
        CUSTOM_BLANK,
    ]


def test_display_order_ties_are_broken_by_custom_with_the_marker_last() -> None:
    """규칙 열쇠가 같은 행(같은 제품)은 부품 오름차순, 표지는 끝 — 원래 행 차례와 상관없다."""
    data = pd.DataFrame(
        {
            "제품정보": ["DEMO_P2", "DEMO_P1", "DEMO_P1", "DEMO_P1"],
            "CUSTOM": ["DEMO_CUSTOM_A", CUSTOM_BLANK, "DEMO_CUSTOM_B", "DEMO_CUSTOM_A"],
        }
    )

    result = apply_display_order(data, _product_rule("부하량", "환산"), "부하량", "환산")

    assert result.to_dict("records") == [
        {"제품정보": "DEMO_P1", "CUSTOM": "DEMO_CUSTOM_A"},
        {"제품정보": "DEMO_P1", "CUSTOM": "DEMO_CUSTOM_B"},
        {"제품정보": "DEMO_P1", "CUSTOM": CUSTOM_BLANK},
        {"제품정보": "DEMO_P2", "CUSTOM": "DEMO_CUSTOM_A"},
    ]


def test_display_order_keeps_the_source_order_without_rules_or_parts() -> None:
    """규칙이 없으면 원천 차례 그대로이고(동순위 열쇠도 없음), 부품이 한 값이면 규칙 뒤 차례가
    지금과 같다."""
    parts = pd.DataFrame(
        {"제품정보": ["DEMO_P1", "DEMO_P1"], "CUSTOM": [CUSTOM_BLANK, "DEMO_CUSTOM_A"]}
    )
    no_rules = _product_rule("부하량", "환산").iloc[0:0]
    assert apply_display_order(parts, no_rules, "부하량", "환산") is parts

    single = pd.DataFrame(
        {
            "제품정보": ["DEMO_P2", "DEMO_P1", "DEMO_P1"],
            "Capa Code": ["C3", "C2", "C1"],
            "CUSTOM": [CUSTOM_BLANK] * 3,
        }
    )
    result = apply_display_order(single, _product_rule("부하량", "환산"), "부하량", "환산")
    assert result["Capa Code"].tolist() == ["C2", "C1", "C3"]


# ------------------------------------------------------------------ 끝단 — 한 값 · 두 부품

# 끝단 시험이 맞대는 계산 결과 칸. 대당 Capa · 소요대수 상세는 CUSTOM 칸을 싣는다.
_CUSTOM = "CUSTOM"
# 소요기준 PKG 경로로 바꿔 보는 공정 — 시드에는 PKG 경로가 없다.
_PKG_PROCESS = "DEMO_Final_Test"


def _seed() -> dict[str, pd.DataFrame]:
    return dict(build_builtin_seed_dataset().reference_tables)


def _all_custom(tables: Mapping[str, pd.DataFrame], value: str) -> dict[str, pd.DataFrame]:
    """CUSTOM 키 표 여덟의 CUSTOM 을 모두 한 값으로 바꾼 사본."""
    keyed = custom_keyed_tables()
    return {
        name: frame.assign(**{_CUSTOM: value}) if name in keyed else frame.copy()
        for name, frame in tables.items()
    }


def _outcome(tables: Mapping[str, pd.DataFrame]) -> sc.CapacityOutcome:
    """시나리오 전체 기간의 대당 Capa · 소요대수(캐시 없는 순수 코어)."""
    outcome = sc.full_capacity_outcome(tables, tables)
    assert outcome.error is None, outcome.error
    return outcome


def _unit_and_required(tables: Mapping[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    outcome = _outcome(tables)
    assert outcome.unit_capacity is not None and outcome.required_equipment is not None
    return outcome.unit_capacity, outcome.required_equipment


def _wafer(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    _, wafer = calculate_chip_and_wafer_loads(
        tables["RQ_PKG_PLAN"], tables["RQ_YLD"], tables["RQ_CHIP_QTY"]
    )
    return wafer


def _density(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    return calculate_density_load(tables["RQ_PKG_PLAN"], tables["RQ_CHIP_EQ"])


def _without_custom(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.drop(columns=[_CUSTOM], errors="ignore").reset_index(drop=True)


def _assert_same_but_custom(left: pd.DataFrame, right: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(_without_custom(left), _without_custom(right))


def _part_rows(frame: pd.DataFrame, part: str) -> pd.DataFrame:
    rows = frame["제품정보"].eq(TWO_PART_PRODUCT) & frame[_CUSTOM].eq(part)
    return frame.loc[rows.fillna(False).astype("bool")].reset_index(drop=True)


def _process_month_sum(frame: pd.DataFrame, value: str) -> pd.Series:
    return frame.groupby(["공정", "생산계획년월"])[value].sum().sort_index()


def _home_results(
    tables: Mapping[str, pd.DataFrame], token: str
) -> tuple[list[pd.DataFrame], pd.DataFrame]:
    """HOME 세 함수(기본 · EDP 뺌 · 세부수량)의 결과 프레임.

    캐시는 프로세스 전역이라 부를 때마다 토큰을 새로 짓는다."""
    months = sorted(int(month) for month in pd.to_numeric(tables["RQ_PKG_PLAN"]["생산계획년월"]))
    display_order = tables["RQ_DISPLAY_ORDER"]
    key = sc.build_home_simulation_cache_key(
        reference_version=1,
        scenario_token=f"custom-end-to-end-{token}-{uuid4().hex}",
        start_month=months[0],
        end_month=months[-1],
        display_order=display_order,
    )
    simulation = sc.get_home_simulation(key, tables, display_order, tables)
    without_edp = sc.get_home_lob_without_edp(key, tables, display_order)
    detail = sc.get_home_plan_detail(
        key, tables, display_order, include_edp=False, include_customer=True
    )
    frames = [item for item in (*simulation, *without_edp) if isinstance(item, pd.DataFrame)]
    return frames, detail


def test_one_custom_value_gives_the_same_results_whatever_the_value() -> None:
    """① 여덟 표의 CUSTOM 이 모두 표지든 `DEMO_CUSTOM_A` 든 전체 기간 계산 · HOME 이 CUSTOM 칸
    말고 같다."""
    seed = _seed()
    renamed = _all_custom(seed, PART_A)

    seed_unit, seed_required = _unit_and_required(seed)
    renamed_unit, renamed_required = _unit_and_required(renamed)

    for before, after in ((seed_unit, renamed_unit), (seed_required, renamed_required)):
        assert set(before[_CUSTOM]) == {CUSTOM_BLANK}
        assert set(after[_CUSTOM]) == {PART_A}
        _assert_same_but_custom(before, after)
    _assert_same_but_custom(_wafer(seed), _wafer(renamed))
    _assert_same_but_custom(_density(seed), _density(renamed))

    seed_home, seed_detail = _home_results(seed, "seed")
    renamed_home, renamed_detail = _home_results(renamed, "renamed")
    assert len(seed_home) == len(renamed_home) > 0
    for before, after in zip(seed_home, renamed_home, strict=True):
        _assert_same_but_custom(before, after)
    _assert_same_but_custom(seed_detail, renamed_detail)


def test_two_parts_of_one_product_are_calculated_apart() -> None:
    """② 한 제품을 두 Capa Code · 두 부품으로 가르고 B 의 수율 · UPEH 만 바꾼다.

    Wafer · 대당 Capa · 소요대수가 부품마다 따로 나고 부품 하나씩 따로 돌린 값과 같다. B 를 바꾸지
    않으면 두 부품의 합이 시드 한 제품과 같다 — 조인이 다른 부품 행을 붙이면(many_to_many) 합이
    불어난다.
    """
    two = two_part_tables()
    two_unit, two_required = _unit_and_required(two)
    two_wafer = _wafer(two)

    for part in (PART_A, PART_B):
        alone = single_part_tables(part)
        alone_unit, alone_required = _unit_and_required(alone)
        for together, apart in (
            (two_unit, alone_unit),
            (two_required, alone_required),
            (two_wafer, _wafer(alone)),
        ):
            rows = _part_rows(together, part)
            assert not rows.empty
            pd.testing.assert_frame_equal(rows, _part_rows(apart, part))
    a_capacity = _part_rows(two_unit, PART_A)["대당 Capa"].astype("float64")
    b_capacity = _part_rows(two_unit, PART_B)["대당 Capa"].astype("float64")
    assert not a_capacity.equals(b_capacity)
    assert not _part_rows(two_wafer, PART_A)["물량"].equals(_part_rows(two_wafer, PART_B)["물량"])

    seed = _seed()
    even = two_part_tables(vary_b=False)
    seed_required = _unit_and_required(seed)[1]
    even_required = _unit_and_required(even)[1]
    pd.testing.assert_series_equal(
        _process_month_sum(even_required, "소요대수"),
        _process_month_sum(seed_required, "소요대수"),
        check_exact=False,
    )
    assert len(even_required) > len(seed_required)
    for load in (_wafer, _density):
        assert float(load(even)["물량"].sum()) == pytest.approx(float(load(seed)["물량"].sum()))


def _with_pkg_route(tables: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """`_PKG_PROCESS` 의 경로 · 실적 표를 소요기준 PKG · `Buffer` 로 바꾼다(모든 제품)."""
    out = dict(tables)
    for name in ("RQ_REQB", "RQ_UPEH", "RQ_LOT_RATIO", "RQ_WF_RATIO"):
        frame = out[name].copy()
        rows = frame["공정"].eq(_PKG_PROCESS).fillna(False).astype("bool")
        frame.loc[rows, "WF 구분"] = "Buffer"
        if "소요기준" in frame.columns:
            frame.loc[rows, "소요기준"] = "PKG"
        out[name] = frame
    return out


def test_pkg_routes_carry_the_load_of_each_part() -> None:
    """③ 소요기준 PKG 경로도 부품마다 부하가 붙는다 — PKG 부하 줄에 CUSTOM 이 비면 경로에 못 붙어
    그 부품의 PKG 소요대수가 말없이 0 이 된다."""
    two_required = _unit_and_required(_with_pkg_route(two_part_tables()))[1]
    pkg_rows = two_required["공정"].eq(_PKG_PROCESS)
    assert set(two_required.loc[pkg_rows, "소요기준"]) == {"PKG"}

    for part in (PART_A, PART_B):
        alone_required = _unit_and_required(_with_pkg_route(single_part_tables(part)))[1]
        together = _part_rows(two_required.loc[pkg_rows], part)
        apart = _part_rows(alone_required.loc[alone_required["공정"].eq(_PKG_PROCESS)], part)
        assert not together.empty
        assert float(together["부하량"].sum()) > 0
        pd.testing.assert_frame_equal(together, apart)


@pytest.mark.parametrize("name", custom_keyed_tables())
def test_a_table_without_the_custom_column_stops_instead_of_folding(name: str) -> None:
    """④ 두 부품 견본에서 한 표의 CUSTOM 칸을 빼면 두 부품이 말없이 한 줄로 접히지 않고 멈춘다."""
    tables = two_part_tables()
    tables[name] = tables[name].drop(columns=[_CUSTOM])

    outcome = sc.full_capacity_outcome(tables, tables)
    messages = [outcome.error or ""]
    try:
        _density(tables)
    except ValueError as error:
        messages.append(str(error))

    assert any(name in message and _CUSTOM in message for message in messages), messages
