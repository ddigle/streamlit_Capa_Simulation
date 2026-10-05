# Purpose: 새 리비전이 부모 리비전의 가상제품 이력을 물려받고 세션 등록과 합치는 규칙을 검증한다.

import pandas as pd

from capa_simulation.services.scenario_virtual_products import inherit_virtual_product_records
from capa_simulation.services.virtual_product import VirtualProductRecord


def _record(product: str, stack: str = "8H", source: str = "DEMO_SOURCE") -> VirtualProductRecord:
    return VirtualProductRecord(
        product=product, stack=stack, source_product=source, source_stack="8H"
    )


def _keyed(*keys: tuple[str, str]) -> pd.DataFrame:
    return pd.DataFrame(list(keys), columns=["제품정보", "Stack"])


def test_parent_rows_still_in_any_product_table_are_inherited_and_gone_ones_dropped() -> None:
    """계획에서만 지운 제품은 다른 표에 남아 있어 물려받고, 모든 표에서 사라진 제품만 빠진다."""
    tables = {
        "RQ_PKG_PLAN": _keyed(("DEMO_SOURCE", "8H"), ("DEMO_KEPT", "8H")),
        # 공백이 섞인 키도 같은 제품으로 본다(복제 등록은 공백을 걷어 저장한다).
        "RQ_YLD": _keyed(("DEMO_SOURCE", "8H"), (" DEMO_YIELD_ONLY ", "8H ")),
        "RQ_REQB": pd.DataFrame({"공정": ["DEMO_PROCESS"]}),
    }
    parent = (_record("DEMO_KEPT"), _record("DEMO_YIELD_ONLY"), _record("DEMO_GONE"))

    result = inherit_virtual_product_records(parent, (), tables)

    assert result == (_record("DEMO_KEPT"), _record("DEMO_YIELD_ONLY"))


def test_without_any_product_table_every_parent_row_is_inherited() -> None:
    """제품 키를 가진 표가 없으면 사라졌는지 판단할 수 없으므로 하나도 버리지 않는다."""
    parent = (_record("DEMO_A"), _record("DEMO_B"))

    result = inherit_virtual_product_records(
        parent, (), {"RQ_REQB": pd.DataFrame({"공정": ["DEMO_PROCESS"]})}
    )

    assert result == parent


def test_session_rows_are_added_once_and_win_over_the_parent_row_with_the_same_key() -> None:
    """같은 제품·Stack 은 한 건이다. 세션 등록이 지금 표의 출처이므로 세션 쪽 원본을 남긴다."""
    tables = {"RQ_PKG_PLAN": _keyed(("DEMO_A", "8H"), ("DEMO_B", "8H"))}
    parent = (_record("DEMO_A"), _record("DEMO_B", source="DEMO_OLD_SOURCE"))
    # 세션 등록은 표에 없어도 거르지 않는다 — 지금까지 저장하던 그대로다.
    session = (_record("DEMO_B"), _record("DEMO_A"), _record("DEMO_NEW", stack="4H"))

    result = inherit_virtual_product_records(parent, session, tables)

    assert result == (_record("DEMO_A"), _record("DEMO_B"), _record("DEMO_NEW", stack="4H"))


def test_no_parent_keeps_only_the_session_rows() -> None:
    session = (_record("DEMO_A"),)
    assert inherit_virtual_product_records((), session, {}) == session
