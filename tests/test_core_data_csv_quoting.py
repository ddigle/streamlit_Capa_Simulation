# Purpose: 값에 쉼표나 큰따옴표가 든 표준 CSV 를 읽을 수 있는지 지킨다.

"""CSV 인용 방식이 계약을 따르는지 고정한다.

원래는 계약에 `quote_style` 이 적혀 있는데 파서가 그 키를 읽지 않고 `csv.QUOTE_NONE` 을
코드에 박아 두었다. `QUOTE_NONE` 은 큰따옴표를 값의 일부로 보고 `escapechar` 도 없어서,
**값에 쉼표가 하나라도 들어간 표준 CSV 를 읽을 방법이 아예 없었다.**

드러나지 않은 이유는 로컬 표본에 큰따옴표가 한 글자도 없기 때문이다 —
`scripts/generate_sample_core_data.py` 가 `csv.DictWriter` 기본값으로 쓰는데 값에 쉼표가
없으니 인용이 발생하지 않았다. 그 우연이 계약값이 되어 있었다.

실데이터에서 위험한 컬럼은 자유 텍스트다: `설비대여평가DESC`, `설비대여평가항목`,
`모델명`, `Customer`, `PKG Part No`, `제품정보`. 쉼표가 들어가면 78컬럼 계약이 깨져
적재 전체가 멈추거나, 필드 수가 우연히 맞으면 값이 컬럼 경계를 넘어 조인 키가 조용히
어긋난다. 뒤쪽이 더 나쁘다.
"""

import csv
from pathlib import Path

import pandas as pd
import pytest
from test_core_data_pipeline import _core_data_row

from capa_simulation.io.core_data_source import (
    QUOTE_STYLES,
    load_core_data_contract,
    read_core_data_csv,
)

# 자유 텍스트라 쉼표가 실제로 들어올 수 있는 컬럼.
FREE_TEXT_COLUMN = "설비대여평가DESC"


def _write(frame: pd.DataFrame, path: Path) -> None:
    """표준 CSV 로 쓴다. 값에 쉼표가 있으면 파이썬이 알아서 따옴표로 감싼다."""
    frame.to_csv(path, index=False, encoding=load_core_data_contract().encoding)


def test_contract_declares_a_quote_style_the_parser_understands() -> None:
    """계약값이 파서에 닿지 않으면 이 키는 장식일 뿐이다."""
    assert load_core_data_contract().quote_style in QUOTE_STYLES


def test_a_value_containing_a_comma_round_trips(tmp_path: Path) -> None:
    """쉼표가 든 값 하나가 78컬럼 계약을 깨뜨리면 안 된다."""
    frame = _core_data_row()
    frame[FREE_TEXT_COLUMN] = frame[FREE_TEXT_COLUMN].astype(object)
    frame.loc[0, FREE_TEXT_COLUMN] = "대여 평가, 2차 검토 필요"
    path = tmp_path / "Core_Data.csv"
    _write(frame, path)

    loaded = read_core_data_csv(path)

    assert loaded.loc[0, FREE_TEXT_COLUMN] == "대여 평가, 2차 검토 필요"


def test_a_quoted_value_does_not_keep_its_quotes(tmp_path: Path) -> None:
    """따옴표가 값에 박힌 채 조인 키로 쓰이면 조용히 어긋난다."""
    frame = _core_data_row()
    frame.loc[0, "제품정보"] = "Product, A"
    path = tmp_path / "Core_Data.csv"
    _write(frame, path)

    loaded = read_core_data_csv(path)

    assert loaded.loc[0, "제품정보"] == "Product, A"
    assert '"' not in str(loaded.loc[0, "제품정보"])


def test_the_old_quote_none_reading_corrupts_silently(tmp_path: Path) -> None:
    """회귀 방지 — 옛 방식은 **예외를 내지 않는다.** 그래서 더 위험하다.

    필드가 하나 늘면 pandas 는 첫 컬럼을 인덱스로 삼아 **모든 값을 한 칸씩 민다.**
    `시뮬레이션 ID` 자리에 `PLAN ID` 값이 들어가고 조인 키 `제품정보` 에는 따옴표가
    박힌 파편(`' A"'`)이 남는다. 오류 없이 틀린 숫자가 나오는 경로다.
    """
    frame = _core_data_row()
    frame.loc[0, "제품정보"] = "Product, A"
    path = tmp_path / "Core_Data.csv"
    _write(frame, path)
    contract = load_core_data_contract()

    shifted = pd.read_csv(
        path,
        encoding=contract.encoding,
        delimiter=contract.delimiter,
        quoting=csv.QUOTE_NONE,
        low_memory=False,
    )

    assert list(shifted.index) == ["SIM-001"], "첫 컬럼이 인덱스로 먹혔다"
    assert shifted.iloc[0]["시뮬레이션 ID"] == "PLAN-001", "값이 한 칸 밀렸다"
    assert shifted.iloc[0]["제품정보"] != "Product, A"


def test_an_unknown_quote_style_is_rejected_at_load(tmp_path: Path) -> None:
    """오타 난 계약값이 조용히 기본값으로 떨어지면 안 된다."""
    import json

    payload = json.loads(Path("config/data_contract.json").read_text(encoding="utf-8"))
    payload["source"]["quote_style"] = "느슨하게"
    broken = tmp_path / "data_contract.json"
    broken.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="quote_style"):
        load_core_data_contract(broken)
