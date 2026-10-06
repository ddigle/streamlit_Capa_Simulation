# Purpose: 소수가 정상인 원천 컬럼이 정수 계약에 갇히지 않게 지킨다.

"""비율·모듈수 계열 컬럼이 `integer` 로 굳는 것을 막는다.

`normalize_core_data` 는 `dtype: integer` 컬럼에 소수가 하나라도 있으면
`Core Data 정수 컬럼에 소수값이 있습니다` 로 **적재 전체를 중단**시킨다. RQ 파생 이전에
터지므로 시나리오 등록 자체가 실패한다.

아래 네 컬럼이 정수로 적혀 있던 근거는 **로컬 합성 표본의 우연**뿐이었다.
`scripts/generate_sample_core_data.py` 가 `Side반영률`·`MCP_Chip_Ratio` 에 문자열 `"1"` 을
쓰고 `설비보유HCB` 는 아예 쓰지 않아, 표본에서 고유값이 각각 1개·1개·0개다. 이름부터가
`반영률`·`Ratio` 이고 형제 컬럼 `설비보유` 는 이미 실수다. `모듈수` 는 더 분명하다 —
`docs/TODO.md` 에 사내 BigDataQuery 실데이터에서 나온 `MPGA TEST` 의 **소수 `모듈수`**
규칙이 미결로 남아 있다. 즉 실데이터가 이 계약을 이미 반박한다.

하류는 이미 실수를 전제한다(`services/unit_capacity.py` 가 곱셈에 쓴다). 정수 제약이
정말 업무 규칙이라면 적재를 막는 계약이 아니라 진단으로 보여 줄 검증 규칙이어야 한다.
"""

import pandas as pd
import pytest

from capa_simulation.io.core_data_source import load_core_data_contract, normalize_core_data

# 표본이 상수 하나만 담았거나 통째로 비워서 정수로 굳었던 컬럼들.
FRACTIONAL_TOLERANT = ("모듈수", "Side반영률", "MCP_Chip_Ratio", "설비보유HCB")


def _dtype_of(name: str) -> str:
    contract = load_core_data_contract()
    for column in contract.columns:
        if column.name == name:
            return column.dtype
    raise AssertionError(f"계약에 없는 컬럼: {name}")


@pytest.mark.parametrize("name", FRACTIONAL_TOLERANT)
def test_ratio_like_columns_accept_decimals(name: str) -> None:
    """정수로 되돌리면 소수 한 행이 시나리오 등록 전체를 막는다."""
    assert _dtype_of(name) == "number"


def test_a_decimal_module_count_loads_instead_of_stopping_the_import() -> None:
    """`MPGA TEST` 의 소수 모듈수가 실제로 통과하는지 본다. 계약만 보면 놓친다."""
    from test_core_data_pipeline import _core_data_row

    frame = _core_data_row()
    frame["모듈수"] = frame["모듈수"].astype(object)
    frame.loc[0, "모듈수"] = "2.5"

    normalized = normalize_core_data(frame)

    assert normalized.loc[0, "모듈수"] == pytest.approx(2.5)


def test_true_integer_columns_still_reject_decimals() -> None:
    """완화가 번지면 안 된다. 개수·년월은 여전히 정수여야 한다."""
    assert _dtype_of("생산계획년월") == "integer"
    assert _dtype_of("Chip수") == "integer"

    from test_core_data_pipeline import _core_data_row

    frame = _core_data_row()
    frame["Chip수"] = frame["Chip수"].astype(object)
    frame.loc[0, "Chip수"] = "2.5"

    with pytest.raises(ValueError, match="정수 컬럼에 소수값"):
        normalize_core_data(frame)


def test_every_column_the_contract_declares_is_one_of_three_dtypes() -> None:
    """오타 난 dtype 은 조용히 문자열로 떨어진다. 계약이 스스로를 검사하게 둔다."""
    contract = load_core_data_contract()
    unexpected = sorted(
        {column.dtype for column in contract.columns} - {"string", "number", "integer"}
    )

    assert not unexpected, f"알 수 없는 dtype: {unexpected}"


def test_normalized_frame_keeps_the_declared_numeric_kind() -> None:
    """계약이 number 라고 했는데 정수로 다운캐스트되면 소수가 다시 잘린다."""
    from test_core_data_pipeline import _core_data_row

    normalized = normalize_core_data(_core_data_row())

    for name in FRACTIONAL_TOLERANT:
        assert pd.api.types.is_float_dtype(normalized[name]), name
