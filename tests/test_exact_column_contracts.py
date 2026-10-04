# Purpose: 컬럼 계약 정확 일치 검사 9곳의 오류 문구를 경우별로 바이트 단위까지 고정한다.

"""컬럼 계약 정확 일치 검사의 오류 문구 스냅샷.

기존 테스트는 `match="컬럼 계약"` 부분 일치뿐이라 괄호 안 세부(누락·추가 순서, 구분자,
상한 10개, 순서 변형 문구)가 바뀌어도 잡지 못한다. 여기서는 9곳의 문구 전체를 같음으로
비교한다. 순서를 보지 않는 곳은 컬럼 차례만 바꾼 입력이 계약 오류를 내지 않는지도 본다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import duckdb
import pandas as pd
import pytest

from capa_simulation.io.core_data_source import load_core_data_contract, normalize_core_data
from capa_simulation.persistence._sql_helpers import insert_frame
from capa_simulation.persistence.display_order_store import (
    GLOBAL_DISPLAY_ORDER_COLUMNS,
    validate_global_display_order_frame,
)
from capa_simulation.services.advance_load import ADVANCE_LOAD_COLUMNS, prepare_advance_load
from capa_simulation.services.display_order_csv import validate_display_order_import
from capa_simulation.services.display_order_editor import DISPLAY_ORDER_COLUMNS
from capa_simulation.services.execution_capacity import (
    EXECUTION_CAPACITY_COLUMNS,
    prepare_execution_capacity,
)
from capa_simulation.services.frame_contracts import require_exact_columns
from capa_simulation.services.past_data import (
    PAST_DETAIL_COLUMNS,
    PAST_MONTH_COLUMNS,
    PAST_SECUREMENT_COLUMNS,
    prepare_past_table,
)
from capa_simulation.services.process_rename import (
    PROCESS_RENAME_COLUMNS,
    validate_process_rename_frame,
    validate_process_rename_import,
)


def _frame(columns: Sequence[object]) -> pd.DataFrame:
    # dict 로 만들면 겹친 머리글이 하나로 접힌다. 겹침도 입력의 일부라 그대로 둔다.
    return pd.DataFrame(columns=list(columns), dtype="object")


def _message(call: Callable[[], object]) -> str:
    with pytest.raises(ValueError) as caught:
        call()
    return str(caught.value)


def _no_contract_error(call: Callable[[], object]) -> None:
    """컬럼 차례만 바꾼 입력은 계약 검사를 통과해야 한다. 뒤의 다른 검사는 상관하지 않는다."""
    try:
        call()
    except (ValueError, TypeError, KeyError) as error:
        assert "컬럼 계약" not in str(error)


# --- 순서를 보지 않는 서비스·저장 검사 -------------------------------------------------

_UNORDERED_SITES: list[tuple[str, tuple[str, ...], Callable[[pd.DataFrame], object]]] = [
    ("선행 물량", ADVANCE_LOAD_COLUMNS, prepare_advance_load),
    ("실행 Capa 반영", EXECUTION_CAPACITY_COLUMNS, prepare_execution_capacity),
    ("공정 표시명", PROCESS_RENAME_COLUMNS, validate_process_rename_frame),
    ("공용 표시순서", GLOBAL_DISPLAY_ORDER_COLUMNS, validate_global_display_order_frame),
    (
        "과거 월별 실적",
        PAST_MONTH_COLUMNS,
        lambda frame: prepare_past_table(frame, PAST_MONTH_COLUMNS),
    ),
    (
        "과거 계획 세부수량",
        PAST_DETAIL_COLUMNS,
        lambda frame: prepare_past_table(frame, PAST_DETAIL_COLUMNS),
    ),
    (
        "과거 공정별 확보율",
        PAST_SECUREMENT_COLUMNS,
        lambda frame: prepare_past_table(frame, PAST_SECUREMENT_COLUMNS),
    ),
]


@pytest.mark.parametrize(("label", "columns", "call"), _UNORDERED_SITES)
def test_unordered_sites_report_missing_extra_and_both(
    label: str,
    columns: tuple[str, ...],
    call: Callable[[pd.DataFrame], object],
) -> None:
    head, *rest = columns

    missing_only = _frame(list(rest))
    assert _message(lambda: call(missing_only)) == (
        f"{label} 컬럼 계약이 일치하지 않습니다 (누락: {head})."
    )

    extra_only = _frame([*columns, "추가A", "추가B"])
    assert _message(lambda: call(extra_only)) == (
        f"{label} 컬럼 계약이 일치하지 않습니다 (추가: 추가A, 추가B)."
    )

    # 누락은 계약 차례, 추가는 입력 차례로 싣는다.
    both = _frame(["추가B", *reversed(rest), "추가A"])
    assert _message(lambda: call(both)) == (
        f"{label} 컬럼 계약이 일치하지 않습니다 (누락: {head}; 추가: 추가B, 추가A)."
    )

    missing_two = _frame(list(columns[2:]) + ["추가A"])
    assert _message(lambda: call(missing_two)) == (
        f"{label} 컬럼 계약이 일치하지 않습니다 (누락: {columns[0]}, {columns[1]}; 추가: 추가A)."
    )

    reordered = _frame(list(reversed(columns)))
    _no_contract_error(lambda: call(reordered))


def test_unordered_sites_list_non_text_column_names_as_text() -> None:
    frame = pd.DataFrame({"생산계획년월": [], "선행 물량": [], 7: []})

    assert _message(lambda: prepare_advance_load(frame)) == (
        "선행 물량 컬럼 계약이 일치하지 않습니다 (추가: 7)."
    )


def test_unordered_sites_still_accept_duplicated_contract_columns_in_the_check() -> None:
    """중복 머리글은 순서를 보지 않는 곳에서는 계약 검사가 아니라 뒤 단계의 문제다."""
    frame = pd.DataFrame([[1, 2, 3]], columns=["공정", "표시명", "표시명"])

    _no_contract_error(lambda: validate_process_rename_frame(frame))


# --- DuckDB 저장 경계 -------------------------------------------------------------------


def _insert(frame: pd.DataFrame) -> None:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("CREATE SCHEMA s")
        connection.execute(
            'CREATE TABLE s.t (owner_id VARCHAR, source_row_no BIGINT, "공정" VARCHAR, '
            '"제품정보" VARCHAR, "값" DOUBLE)'
        )
        insert_frame(
            connection,
            schema="s",
            table_name="t",
            owner_column="owner_id",
            owner_id="O1",
            frame=frame,
            logical_name="RQ_TEST",
        )
    finally:
        connection.close()


def test_insert_frame_reports_missing_extra_and_both() -> None:
    assert _message(lambda: _insert(_frame(["공정", "값"]))) == (
        "RQ_TEST 컬럼 계약이 일치하지 않습니다 (누락: 제품정보)."
    )
    assert _message(lambda: _insert(_frame(["공정", "제품정보", "값", "추가A"]))) == (
        "RQ_TEST 컬럼 계약이 일치하지 않습니다 (추가: 추가A)."
    )
    assert _message(lambda: _insert(_frame(["추가A", "값", 0]))) == (
        "RQ_TEST 컬럼 계약이 일치하지 않습니다 (누락: 공정, 제품정보; 추가: 추가A, 0)."
    )

    _insert(pd.DataFrame({"값": [1.0], "제품정보": ["D"], "공정": ["P"]}))


# --- Core Data 78컬럼 -------------------------------------------------------------------


def test_core_data_contract_caps_each_list_at_ten_names() -> None:
    contract = load_core_data_contract()
    expected = [column.name for column in contract.columns]
    extras = [f"추가{index:02d}" for index in range(12)]

    missing_only = _frame(expected[1:])
    assert _message(lambda: normalize_core_data(missing_only, contract)) == (
        f"Core Data 78컬럼 계약이 일치하지 않습니다 (누락: {expected[0]})."
    )

    extra_only = _frame([*expected, "추가00"])
    assert _message(lambda: normalize_core_data(extra_only, contract)) == (
        "Core Data 78컬럼 계약이 일치하지 않습니다 (추가: 추가00)."
    )

    many = _frame([*extras, *expected[12:]])
    assert _message(lambda: normalize_core_data(many, contract)) == (
        "Core Data 78컬럼 계약이 일치하지 않습니다 "
        f"(누락: {', '.join(expected[:10])}; 추가: {', '.join(extras[:10])})."
    )


# --- 붙여넣기·CSV 입력(순서와 머리글 공백까지 본다) -----------------------------------

_ORDERED_SITES: list[tuple[str, tuple[str, ...], Callable[[pd.DataFrame], object]]] = [
    ("표시순서 입력 표", DISPLAY_ORDER_COLUMNS, validate_display_order_import),
    ("공정 표시명 입력 표", PROCESS_RENAME_COLUMNS, validate_process_rename_import),
]


@pytest.mark.parametrize(("label", "columns", "call"), _ORDERED_SITES)
def test_ordered_import_sites_report_missing_extra_both_and_order(
    label: str,
    columns: tuple[str, ...],
    call: Callable[[pd.DataFrame], object],
) -> None:
    head, *rest = columns

    assert _message(lambda: call(_frame(list(rest)))) == (
        f"{label} 컬럼 계약이 일치하지 않습니다 (누락: {head})."
    )
    assert _message(lambda: call(_frame([*columns, " 추가A "]))) == (
        f"{label} 컬럼 계약이 일치하지 않습니다 (추가: 추가A)."
    )
    assert _message(lambda: call(_frame(["추가B", *rest]))) == (
        f"{label} 컬럼 계약이 일치하지 않습니다 (누락: {head}; 추가: 추가B)."
    )
    assert _message(lambda: call(_frame(list(reversed(columns))))) == (
        f"{label} 컬럼 계약이 일치하지 않습니다 (컬럼 순서가 양식과 다름)."
    )
    # 머리글이 겹치면 누락·추가가 모두 비어도 양식과 다르다.
    assert _message(lambda: call(_frame([*columns, columns[-1]]))) == (
        f"{label} 컬럼 계약이 일치하지 않습니다 (컬럼 순서가 양식과 다름)."
    )


def test_ordered_import_sites_strip_header_whitespace_before_comparing() -> None:
    parsed = pd.DataFrame({" 공정 ": ["SAW"], "표시명\t": ["절단"]})

    result = validate_process_rename_import(parsed)

    assert list(result.columns) == list(PROCESS_RENAME_COLUMNS)
    assert result.to_dict("records") == [{"공정": "SAW", "표시명": "절단"}]


# --- 공용 함수 자체 -----------------------------------------------------------------------


def test_require_exact_columns_passes_exact_and_reordered_columns() -> None:
    require_exact_columns(["가", "나"], ("가", "나"), "표 컬럼")
    require_exact_columns(["나", "가"], ("가", "나"), "표 컬럼")
    require_exact_columns([" 가", "나 "], ("가", "나"), "표 컬럼", check_order=True, strip=True)

    with pytest.raises(ValueError, match=r"^표 컬럼 계약이 일치하지 않습니다 \(컬럼 순서가"):
        require_exact_columns(["나", "가"], ("가", "나"), "표 컬럼", check_order=True)
