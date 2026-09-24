# Purpose: UPEH 편집이 만든 새 경로에 측정률 행이 없으면 저장 전에 걸리는지 검증한다.

"""**저장은 되는데 화면에서 터지는 일**을 저장 경계에서 막는지 본다.

사내에서 실제로 겪은 순서가 이랬다(2026-09-23). `RQ_UPEH` 의 빈 월 칸에 값을 넣고 적용
→ 정상 완료 → Capa LOB Summary 로 가니 「RQ_LOT_RATIO 연결값이 없는 대당 Capa 기준이
있습니다」. 빈 칸을 채우는 것은 값 수정이 아니라 **경로를 하나 더 만드는 일**인데, 저장
경계에 표 사이 정합성을 보는 검사가 없었다.

여기서 고정하는 것은 셋이다 — 새 조합을 찾는가, 측정률 두 표를 **함께** 보는가,
**이미 어긋나 있던 것은 건드리지 않는가.**
"""

from __future__ import annotations

import pandas as pd

from capa_simulation.services.reference_consistency import (
    added_performance_keys,
    describe_missing_ratio_rows,
    missing_ratio_rows,
)
from capa_simulation.services.unit_capacity import PERFORMANCE_KEYS


def _row(month: int, process: str = "Process-A", stack: str = "8") -> dict[str, object]:
    return {
        "생산계획년월": month,
        "Area_Name": "Main",
        "공정": process,
        "STEP_SEQ": 10,
        "MCP_SEQ": 1,
        "양산구분": "양산",
        "제품정보": "DEMO-A",
        "Stack": stack,
        "WF 구분": "Top",
    }


def _upeh(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["소요기준"] = "WF"
    frame["UPEH"] = 100.0
    frame["ST"] = 0.0
    return frame


def _ratio(rows: list[dict[str, object]], value_column: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows) if rows else pd.DataFrame(columns=PERFORMANCE_KEYS)
    frame[value_column] = 1.0
    return frame


def _tables(lot_rows: list[dict[str, object]], wf_rows: list[dict[str, object]]) -> dict:
    return {
        "RQ_LOT_RATIO": _ratio(lot_rows, "Lot 측정률"),
        "RQ_WF_RATIO": _ratio(wf_rows, "WF측정률"),
    }


def test_filling_an_empty_month_is_reported_as_a_new_path() -> None:
    """빈 칸 채우기는 값 수정이 아니라 행 추가다. 그것이 이 검사의 출발점이다."""
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])

    added = added_performance_keys(before, after)

    assert len(added) == 1
    assert int(added.loc[0, "생산계획년월"]) == 202609


def test_both_ratio_tables_are_reported_at_once() -> None:
    """Lot 만 채우면 다음 조인에서 WF 로 같은 문구가 이어진다. 한 번에 알린다."""
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    added = added_performance_keys(before, after)

    missing = missing_ratio_rows(added, _tables([_row(202608)], [_row(202608)]))

    assert set(missing) == {"RQ_LOT_RATIO", "RQ_WF_RATIO"}
    message = describe_missing_ratio_rows(missing)
    assert "Lot측정률" in message and "WF측정률" in message
    # 어느 달 어느 경로인지 말해 줘야 그 칸을 찾을 수 있다.
    assert "202609" in message and "Process-A" in message


def test_a_path_that_already_has_ratio_rows_passes() -> None:
    """측정률이 갖춰진 경로를 채우는 것은 막을 이유가 없다."""
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    added = added_performance_keys(before, after)

    missing = missing_ratio_rows(
        added, _tables([_row(202608), _row(202609)], [_row(202608), _row(202609)])
    )

    assert missing == {}


def test_a_pre_existing_gap_does_not_block_an_unrelated_edit() -> None:
    """**이미 어긋나 있던 것은 건드리지 않는다.**

    막으면 상관없는 칸 하나를 고치려던 사람이 자기가 만들지 않은 문제에 걸려 아무것도
    못 한다. 되돌릴 길까지 막는 셈이다.
    """
    # 202608 은 처음부터 측정률이 없다. 편집은 그 행을 건드리지 않았다.
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608)])

    added = added_performance_keys(before, after)

    assert added.empty
    assert missing_ratio_rows(added, _tables([], [])) == {}


def test_only_one_side_missing_is_reported_alone() -> None:
    """Lot 은 있고 WF 만 없으면 WF 만 말한다."""
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    added = added_performance_keys(before, after)

    missing = missing_ratio_rows(added, _tables([_row(202608), _row(202609)], [_row(202608)]))

    assert set(missing) == {"RQ_WF_RATIO"}


def test_whitespace_and_month_shape_do_not_create_false_gaps() -> None:
    """조인과 **같은 규칙으로** 줄여야 없는 결손을 있다고 하지 않는다.

    `_join_reference` 는 월 정규화·공백 제거·`Area_Name` 정규화를 거쳐 맞댄다.
    """
    before = _upeh([_row(202608)])
    after = _upeh([_row(202608), _row(202609)])
    ratio_row = _row(202609)
    ratio_row["공정"] = " Process-A "
    ratio_row["Area_Name"] = "main"
    lot = [_row(202608), ratio_row]

    added = added_performance_keys(before, after)
    missing = missing_ratio_rows(added, _tables(lot, [_row(202608), _row(202609)]))

    assert missing == {}
