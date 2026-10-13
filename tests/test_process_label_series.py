# Purpose: 공정 표시명 Series 변환이 행마다 바꾼 결과와 값·dtype·인덱스까지 같은지 본다.

"""`ProcessLabels.series` 의 고유값 펼치기가 예전 행 단위 변환과 같은 표를 내는지.

STEP 구성 요약(같은 공정이 월마다 되풀이되는 수만 행)에서 행마다 표시명을 찾던 비용을 고유값
수로 줄였다. 화면 글자가 하나라도 달라지면 안 되므로 빈 칸 종류(`None`·NaN·`pd.NA`)·글자 아닌 값·
`string` dtype·빈 표·표시명 없는 프로필을 모두 예전 식과 견준다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from capa_simulation.components.process_labels import (
    ProcessLabels,
    apply_process_label,
    process_labels_from_rules,
)

LABELS = process_labels_from_rules(
    pd.DataFrame(
        [("DA", "다이 어태치"), ("WB ", "와이어"), ("Process-C", "DA")],
        columns=["공정", "표시명"],
    ),
    5,
)


def _row_by_row(labels: ProcessLabels, values: pd.Series) -> pd.Series:
    """고치기 전 `series` 식 그대로 — 행마다 `apply_process_label`."""
    if not labels.labels:
        return values.astype("object")
    return pd.Series(
        [apply_process_label(value, labels.labels) for value in values],
        index=values.index,
        dtype="object",
    )


CASES = {
    "repeated": pd.Series(["DA", "WB", "DA", "Process-C", "X", "DA"] * 50),
    "padded": pd.Series([" DA ", "WB ", "DA", " Process-C"]),
    "string-dtype": pd.Series(["DA", None, "WB", "DA"], dtype="string"),
    "none-and-nan": pd.Series(["DA", None, np.nan, "WB", None], dtype="object"),
    "pd-na-object": pd.Series(["DA", pd.NA, "X"], dtype="object"),
    "all-missing": pd.Series([None, np.nan], dtype="object"),
    "empty": pd.Series([], dtype="object"),
    "mixed-types": pd.Series([1, 1.0, "DA", True], dtype="object"),
    "categorical": pd.Series(["DA", "WB", "DA"], dtype="category"),
    "custom-index": pd.Series(["WB", "DA", "DA"], index=[10, 3, 7]),
}


@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("labels", [LABELS, ProcessLabels()], ids=["renamed", "no-rename"])
def test_series_matches_the_row_by_row_labels(case: str, labels: ProcessLabels) -> None:
    values = CASES[case]
    before = values.copy()
    pd.testing.assert_series_equal(labels.series(values), _row_by_row(labels, values))
    # 받은 Series 는 그대로다.
    pd.testing.assert_series_equal(values, before)


def test_a_relabel_changes_only_the_renamed_process() -> None:
    """표시명을 바꾸면(버전이 오르면) 그 공정 칸만 새 글자다 — 펼친 값이 옛 매핑에 묶이지 않는다."""
    values = pd.Series(["DA", "WB", "DA", "X"])
    renamed = process_labels_from_rules(
        pd.DataFrame([("DA", "새이름")], columns=["공정", "표시명"]), 6
    )
    assert LABELS.series(values).tolist() == ["다이 어태치", "와이어", "다이 어태치", "X"]
    assert renamed.series(values).tolist() == ["새이름", "WB", "새이름", "X"]
