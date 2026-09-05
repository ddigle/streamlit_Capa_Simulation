# Purpose: 16개 RQ 가 하나도 빠짐없이 업무 키 계약과 중복 검출을 받는지 지킨다.

"""`RQ_REQB` 만 업무 키 계약 밖에 있던 것을 고정한다.

`validated_distinct` 는 업무 키 중복을 잡아 충돌 리포트로 올리고 `drop_duplicates` 로
접는다. 15개 RQ 는 그 경로를 타는데 `RQ_REQB` 만 빠져 있었다. 이 표는 부하량을 공정으로
흘리는 조인 척추이고, `required_equipment` 가 이것을 왼쪽에 두고 `many_to_one` 으로
붙이므로 **왼쪽 중복은 막히지 않는다**. 원천에 완전 중복 행이 하나 들어오면 그 경로의
소요대수가 조용히 두 배가 된다.

`RQ_REQB` 는 13개 컬럼 전부가 키인 경로 표라 값 충돌이라는 개념이 없다. 그래서 충돌
리포트에는 오르지 않고 중복만 접힌다 — `_collect_conflicting_duplicates` 는 값 컬럼이
없으면 그냥 돌아간다.
"""

import pandas as pd
from test_duckdb_repository import _core_data_source

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.services.reference_transformer import build_reference_tables

# 표시순서는 공용 DB 프로필로 분리돼 `transform_display_order()` 로 우회한다.
CONTRACT_EXEMPT = frozenset({"RQ_DISPLAY_ORDER"})


def _display_order() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "페이지 구분": ["HOME"],
            "탭 구분": ["계획"],
            "정렬우선순위": [1],
            "분류컬럼": ["제품정보"],
            "정렬방식": ["사용자지정"],
            "분류값": ["Product-A"],
            "값표시순서": [1],
            "활성여부": ["Y"],
        }
    )


def test_every_built_rq_table_has_a_business_key() -> None:
    """계약에 없는 테이블은 `validated_distinct` 를 부를 수조차 없다(KeyError)."""
    contract = load_core_data_contract()
    tables = build_reference_tables(_core_data_source(), _display_order())

    missing = sorted(
        name for name in tables if name not in CONTRACT_EXEMPT and name not in contract.derived_keys
    )

    assert not missing, f"업무 키 계약이 없는 RQ: {missing}"


def test_reqb_key_covers_every_column_it_carries() -> None:
    """경로 표에는 값 컬럼이 없다. 하나라도 키 밖에 남으면 그 값이 조용히 버려진다."""
    contract = load_core_data_contract()
    tables = build_reference_tables(_core_data_source(), _display_order())

    carried = set(tables["RQ_REQB"].columns)
    keys = set(contract.derived_keys["RQ_REQB"])

    assert carried == keys, f"키 밖 컬럼: {sorted(carried - keys)}"


def test_duplicate_route_rows_are_collapsed_not_doubled() -> None:
    """중복 경로 행이 들어와도 행이 늘지 않아야 한다. 늘면 그 경로의 소요대수가 배가 된다."""
    source = _core_data_source()
    baseline = build_reference_tables(source, _display_order())["RQ_REQB"]
    assert not baseline.empty

    doubled = pd.concat([source, source], ignore_index=True)
    result = build_reference_tables(doubled, _display_order())["RQ_REQB"]

    assert len(result) == len(baseline)
