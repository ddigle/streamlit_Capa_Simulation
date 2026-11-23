# Purpose: 제품 부품(CUSTOM) 도우미의 판정 · 접기 · 칸 채움 · 차례 · 모으기 · 줄임을 고정한다.

"""제품 부품 도우미 — `services/product_parts.py` 와 `home_figure_common._fit_part_label`.

판정 규칙은 세 데이터로 본다 — 모두 표지 `-` 인 옛 리비전, 제품마다 실값 하나인 새 등록, 한 제품에
부품 둘. 앞의 둘은 지금과 같이(가르지 않음) 두고 셋째만 가른다. 견본은
`custom_key_tables.two_part_tables`(내장 시드의 한 제품을 두 부품으로 가른 RQ 표)다.
"""

from __future__ import annotations

import pandas as pd
import pytest
from custom_key_tables import PART_A, PART_B, TWO_PART_PRODUCT, two_part_tables

from capa_simulation.components.home_figure_common import (
    _calibri_width_units,
    _fit_part_label,
    _fit_to_units,
    _text_width_units,
)
from capa_simulation.components.home_lob_figures import _legend_name_budget_units
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.core_data_derivation import CUSTOM_BLANK, custom_sort_key
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.display_order_scopes import PAGE_PLAN, TAB_PKG_PLAN
from capa_simulation.services.product_parts import (
    PART_NOT_SPLIT,
    keep_parts_together,
    multi_part_products,
    part_merged_columns,
    part_order_key,
    product_part_label,
    split_product_parts,
)


def _seed_plan() -> pd.DataFrame:
    return build_builtin_seed_dataset().reference_tables["RQ_PKG_PLAN"].copy()


def _plan(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["제품정보", "CUSTOM"])


# ---------------------------------------------------------------- 판정 — 세 데이터


def test_an_old_revision_with_only_the_blank_marker_splits_nothing() -> None:
    plan = _seed_plan()
    assert set(plan["CUSTOM"]) == {CUSTOM_BLANK}

    assert multi_part_products(plan) == frozenset()


def test_one_real_part_per_product_splits_nothing() -> None:
    """새 등록 — 제품마다 실값이 하나면 `-` 가 아니어도 가르지 않는다(이름이 길어지지 않는다)."""
    plan = _seed_plan()
    products = sorted(plan["제품정보"].unique())
    plan["CUSTOM"] = plan["제품정보"].map(
        {product: f"DEMO_CUSTOM_{index}" for index, product in enumerate(products)}
    )

    assert multi_part_products(plan) == frozenset()


def test_a_product_with_two_parts_is_split() -> None:
    plan = two_part_tables()["RQ_PKG_PLAN"]

    assert multi_part_products(plan) == frozenset({TWO_PART_PRODUCT})


def test_the_blank_marker_beside_a_real_value_is_a_second_part() -> None:
    """표지 `-` 도 부품 하나다 — 계산 키에서 `-` 와 실값은 다른 제품이다. 빈 값 · 공백은 표지와
    같다."""
    plan = _plan(
        [
            ("DEMO_A", "DEMO_CUSTOM_A"),
            ("DEMO_A", "  "),
            ("DEMO_B", " DEMO_CUSTOM_A "),
            ("DEMO_B", "DEMO_CUSTOM_A"),
            ("DEMO_C", "-"),
            ("DEMO_C", ""),
        ]
    )

    assert multi_part_products(plan) == frozenset({"DEMO_A"})


def test_a_plan_without_the_custom_column_splits_nothing() -> None:
    plan = _seed_plan().drop(columns=["CUSTOM"])

    assert multi_part_products(plan) == frozenset()
    assert multi_part_products(plan.iloc[0:0]) == frozenset()


def test_product_names_are_compared_without_surrounding_spaces() -> None:
    plan = _plan([(" DEMO_A", "DEMO_CUSTOM_A"), ("DEMO_A ", "DEMO_CUSTOM_B")])

    assert multi_part_products(plan) == frozenset({"DEMO_A"})


# ---------------------------------------------------------------- 이름표


def test_a_folded_part_shows_the_product_name_alone() -> None:
    assert product_part_label("DEMO_A", PART_NOT_SPLIT) == "DEMO_A"


def test_a_split_part_is_named_in_brackets_after_the_product() -> None:
    """2026-11-23 보드 답 D1 (가) — 괄호. 가운뎃점은 「양산 · DEMO_A」 같은 잇기 구분자라 쓰지
    않는다."""
    assert product_part_label("DEMO_A", "DEMO_CUSTOM_A") == "DEMO_A (DEMO_CUSTOM_A)"
    assert product_part_label("DEMO_A", CUSTOM_BLANK) == "DEMO_A (-)"


def test_a_product_named_like_a_part_label_is_split_too_so_labels_never_clash() -> None:
    """제품정보에 「 (」 가 들어 있어 다른 제품의 부품 이름표와 글자가 같으면 그 제품도 부품을
    붙인다.

    이름표가 조각 · 줄의 열쇠라 겹치면 두 (제품, 부품)이 한 조각으로 합쳐진다. 붙인 이름표가 또
    겹치면 다시 넓힌다.
    """
    clashing = f"DEMO_A ({PART_A})"
    plan = _plan(
        [
            ("DEMO_A", PART_A),
            ("DEMO_A", PART_B),
            (clashing, CUSTOM_BLANK),
            (f"{clashing} (-)", CUSTOM_BLANK),
            ("DEMO_B (X)", CUSTOM_BLANK),
        ]
    )

    split = multi_part_products(plan)

    assert split == frozenset({"DEMO_A", clashing, f"{clashing} (-)"})
    folded = split_product_parts(plan, split)
    labels = [
        product_part_label(product, part)
        for product, part in zip(folded["제품정보"], folded["CUSTOM"], strict=True)
    ]
    assert len(set(labels)) == len(labels)
    # 겹치지 않는 괄호 이름은 그대로다 — 부품이 하나뿐인 제품의 이름은 길어지지 않는다.
    assert "DEMO_B (X)" in labels


# ---------------------------------------------------------------- 접기 · 칸 채움


def test_single_part_products_fold_to_the_internal_value_and_split_ones_keep_their_parts() -> None:
    plan = two_part_tables()["RQ_PKG_PLAN"]
    split = multi_part_products(plan)

    folded = split_product_parts(plan, split)

    assert list(folded.columns) == list(plan.columns)
    by_product: dict[str, set[str]] = {}
    for product, part in zip(folded["제품정보"], folded["CUSTOM"], strict=True):
        by_product.setdefault(str(product), set()).add(str(part))
    assert by_product.pop(TWO_PART_PRODUCT) == {PART_A, PART_B}
    assert by_product and all(parts == {PART_NOT_SPLIT} for parts in by_product.values())
    # 제품정보와 다른 칸은 그대로다.
    pd.testing.assert_frame_equal(folded.drop(columns=["CUSTOM"]), plan.drop(columns=["CUSTOM"]))


def test_folding_twice_gives_the_same_frame() -> None:
    plan = two_part_tables()["RQ_PKG_PLAN"]
    split = multi_part_products(plan)

    once = split_product_parts(plan, split)

    pd.testing.assert_frame_equal(split_product_parts(once, split), once)


def test_a_table_without_custom_gets_the_column_filled_by_the_judgement() -> None:
    """Past Data 계획 세부수량처럼 CUSTOM 칸이 없는 표 — 가르지 않는 제품은 접힌 값, 가르는 제품은
    부품을 모르므로 표지 `-` 다(`DEMO_A (-)`)."""
    past = pd.DataFrame(
        {"제품정보": [TWO_PART_PRODUCT, "DEMO PRODUCT B"], "생산수량": [30.0, 10.0]}
    )

    filled = split_product_parts(past, frozenset({TWO_PART_PRODUCT}))

    assert list(filled.columns) == ["제품정보", "생산수량", "CUSTOM"]
    assert filled["CUSTOM"].tolist() == [CUSTOM_BLANK, PART_NOT_SPLIT]
    assert split_product_parts(past, frozenset())["CUSTOM"].tolist() == [PART_NOT_SPLIT] * 2


def test_blank_parts_of_a_split_product_read_as_the_marker() -> None:
    frame = _plan([("DEMO_A", "DEMO_CUSTOM_A"), ("DEMO_A", ""), (" DEMO_A ", None)])  # type: ignore[list-item]

    folded = split_product_parts(frame, frozenset({"DEMO_A"}))

    assert folded["CUSTOM"].tolist() == ["DEMO_CUSTOM_A", CUSTOM_BLANK, CUSTOM_BLANK]
    assert folded["제품정보"].tolist() == ["DEMO_A", "DEMO_A", " DEMO_A "]


# ---------------------------------------------------------------- 차례 열쇠


def test_the_folded_value_comes_first_and_the_marker_last() -> None:
    parts = ["-", "demo_custom_b", "DEMO_CUSTOM_A", PART_NOT_SPLIT, "DEMO_CUSTOM_B"]

    ordered = sorted(parts, key=part_order_key)

    assert ordered == [PART_NOT_SPLIT, "DEMO_CUSTOM_A", "DEMO_CUSTOM_B", "demo_custom_b", "-"]
    # 파이썬 기본 차례는 표지를 글자 앞에 둔다 — 그래서 이 열쇠를 쓴다.
    assert sorted(parts)[1] == "-"


def test_the_part_key_wraps_the_display_order_key_for_every_real_value() -> None:
    """접힌 값 말고는 표시 차례 열쇠(`custom_sort_key`)와 같은 차례다 — 열쇠 함수가 두 벌이
    아니다."""
    values = ["DEMO_CUSTOM_B", "-", "demo_custom_a", "DEMO_CUSTOM_A", " "]

    assert sorted(values, key=part_order_key) == sorted(values, key=custom_sort_key)
    assert all(part_order_key(value) == (True, custom_sort_key(value)) for value in values)
    assert part_order_key(pd.NA) == (True, custom_sort_key(pd.NA))


# ---------------------------------------------------------------- 모으기


def _stack_rules() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "페이지 구분": [PAGE_PLAN] * 4,
            "탭 구분": [TAB_PKG_PLAN] * 4,
            "정렬우선순위": [1, 1, 2, 2],
            "분류컬럼": ["제품정보", "제품정보", "Stack", "Stack"],
            "정렬방식": ["사용자지정"] * 4,
            "분류값": ["DEMO_B", "DEMO_A", "12H", "8H"],
            "값표시순서": [1, 2, 1, 2],
            "활성여부": ["Y"] * 4,
        }
    )


def _detail() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "제품정보": ["DEMO_A", "DEMO_A", "DEMO_A", "DEMO_A", "DEMO_B"],
            "CUSTOM": [PART_B, PART_A, PART_B, PART_A, PART_NOT_SPLIT],
            "Stack": ["8H", "8H", "12H", "12H", "8H"],
            "값": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )


def test_a_stack_rule_interleaves_parts_and_keeping_them_together_regroups_each_part() -> None:
    """CUSTOM 뒤 칸(Stack)에 규칙이 있으면 표시순서 끝 열쇠만으로는 부품이 Stack 마다 번갈아
    선다."""
    ordered = apply_display_order(_detail(), _stack_rules(), PAGE_PLAN, TAB_PKG_PLAN)
    assert ordered["CUSTOM"].tolist() == [PART_NOT_SPLIT, PART_A, PART_B, PART_A, PART_B]

    together = keep_parts_together(ordered)

    assert together["CUSTOM"].tolist() == [PART_NOT_SPLIT, PART_A, PART_A, PART_B, PART_B]
    # 한 부품 안의 Stack 차례 · 다른 제품의 자리는 받은 그대로다.
    assert together["Stack"].tolist() == ["8H", "12H", "8H", "12H", "8H"]
    assert together["제품정보"].tolist() == ["DEMO_B", "DEMO_A", "DEMO_A", "DEMO_A", "DEMO_A"]
    assert sorted(together["값"]) == sorted(ordered["값"])


def test_keeping_parts_together_does_not_reorder_what_the_display_order_already_grouped() -> None:
    """Stack 규칙이 없으면 끝 열쇠가 이미 부품을 이웃하게 세운다 — 모으기는 아무것도 옮기지
    않는다."""
    ordered = apply_display_order(_detail(), _stack_rules().iloc[:2], PAGE_PLAN, TAB_PKG_PLAN)

    pd.testing.assert_frame_equal(keep_parts_together(ordered), ordered)


def test_keeping_parts_together_never_moves_rows_across_another_product() -> None:
    """제품 덩이(이웃한 같은 제품 행) 안에서만 모은다 — 사이에 다른 제품이 끼면 그 덩이는 따로다."""
    frame = pd.DataFrame(
        {
            "제품정보": ["DEMO_A", "DEMO_A", "DEMO_B", "DEMO_A", "DEMO_A"],
            "CUSTOM": [PART_A, PART_B, PART_NOT_SPLIT, PART_A, PART_B],
            "Stack": ["12H", "12H", "12H", "8H", "8H"],
        }
    )

    pd.testing.assert_frame_equal(keep_parts_together(frame), frame)
    without_custom = frame.drop(columns=["CUSTOM"])
    assert keep_parts_together(without_custom) is without_custom


def test_keeping_parts_together_follows_the_owner_columns() -> None:
    """공정 Capa 상세 「양산구분·제품」 처럼 주인이 두 칸이면 두 칸이 같은 이웃 행 덩이에서
    모은다."""
    frame = pd.DataFrame(
        {
            "양산구분": ["양산", "양산", "양산", "ER"],
            "제품정보": ["DEMO_A"] * 4,
            "CUSTOM": [PART_A, PART_B, PART_A, PART_B],
            "WF 구분": ["Core", "Core", "Top", "Core"],
        }
    )

    together = keep_parts_together(frame, ("양산구분", "제품정보"))

    assert together["CUSTOM"].tolist() == [PART_A, PART_A, PART_B, PART_B]
    assert together["양산구분"].tolist() == ["양산", "양산", "양산", "ER"]
    assert together["WF 구분"].tolist() == ["Core", "Top", "Core", "Core"]


# ---------------------------------------------------------------- 칸 녹이기


def test_merging_the_part_into_the_product_column_drops_custom_from_the_visible_columns() -> None:
    frame = _detail()

    visible, merged = part_merged_columns(frame, ["제품정보", "CUSTOM", "Stack"])

    assert visible == ["제품정보", "Stack"]
    assert "CUSTOM" not in merged.columns
    assert merged["제품정보"].tolist() == [
        f"DEMO_A ({PART_B})",
        f"DEMO_A ({PART_A})",
        f"DEMO_A ({PART_B})",
        f"DEMO_A ({PART_A})",
        "DEMO_B",
    ]
    pd.testing.assert_frame_equal(merged[["Stack", "값"]], frame[["Stack", "값"]])
    assert frame["제품정보"].tolist()[0] == "DEMO_A", "받은 표는 고치지 않는다"


def test_merging_keeps_the_dimensions_when_custom_or_the_product_is_not_among_them() -> None:
    frame = _detail()

    assert part_merged_columns(frame, ["제품정보", "Stack"]) == (["제품정보", "Stack"], frame)
    visible, kept = part_merged_columns(frame, ["CUSTOM", "Stack"])
    assert visible == ["CUSTOM", "Stack"] and kept is frame
    visible, without = part_merged_columns(frame.drop(columns=["CUSTOM"]), ["제품정보", "CUSTOM"])
    assert visible == ["제품정보"]
    assert without["제품정보"].tolist() == frame["제품정보"].tolist()


def test_merging_reads_blank_parts_as_the_marker() -> None:
    frame = pd.DataFrame(
        {"양산구분": ["양산", "양산"], "제품정보": ["DEMO_A", "DEMO_A"], "CUSTOM": [pd.NA, " "]}
    )

    visible, merged = part_merged_columns(frame, ("양산구분", "제품정보", "CUSTOM"))

    assert visible == ["양산구분", "제품정보"]
    assert merged["제품정보"].tolist() == ["DEMO_A (-)", "DEMO_A (-)"]


# ---------------------------------------------------------------- 좁은 칸 줄임


def test_a_folded_part_is_fitted_exactly_like_the_product_name() -> None:
    budget = _legend_name_budget_units()
    for name in ("DEMO PRODUCT A", "DEMO_A", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        for width in (_text_width_units, _calibri_width_units):
            assert _fit_part_label(name, PART_NOT_SPLIT, budget, width) == _fit_to_units(
                name, budget, width
            )


def test_a_label_that_fits_is_left_whole() -> None:
    assert _fit_part_label("A", "B", 100.0, _text_width_units) == "A (B)"


def test_fitting_shortens_the_product_first_and_keeps_the_part() -> None:
    label = product_part_label("DEMO PRODUCT A", PART_A)
    budget = _text_width_units(label) - 2.0

    fitted = _fit_part_label("DEMO PRODUCT A", PART_A, budget, _text_width_units)

    assert fitted.endswith(f"… ({PART_A})")
    assert fitted.startswith("DEMO")
    assert _text_width_units(fitted) <= budget


@pytest.mark.parametrize("part", [PART_A, PART_B])
def test_on_the_legend_the_part_tail_survives_when_even_the_part_overflows(part: str) -> None:
    """도넛 범례 한 칸(`_legend_name_budget_units`)은 부품 이름만으로도 넘친다 — 앞을 줄이고
    구별되는 끝을 남겨 한 제품의 두 부품이 범례에서 갈린다(`_fit_to_units` 는 앞을 남겨 둘이 같은
    글이 된다)."""
    budget = _legend_name_budget_units()

    fitted = _fit_part_label(TWO_PART_PRODUCT, part, budget, _text_width_units)

    assert _text_width_units(fitted) <= budget
    assert fitted.startswith("(…") and fitted.endswith(f"{part[-1]})")
    assert _fit_part_label(TWO_PART_PRODUCT, PART_A, budget, _text_width_units) != _fit_part_label(
        TWO_PART_PRODUCT, PART_B, budget, _text_width_units
    )
    plain = [
        _fit_to_units(product_part_label(TWO_PART_PRODUCT, value), budget, _text_width_units)
        for value in (PART_A, PART_B)
    ]
    assert plain[0] == plain[1], "앞을 남기는 줄임은 두 부품을 가르지 못한다"
