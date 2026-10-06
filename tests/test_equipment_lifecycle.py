# Purpose: 호기 생애주기 구간 조립과 Gantt 조립 규칙을 검증한다.

from datetime import date

import pandas as pd

from capa_simulation.components.equipment_lifecycle_gantt import (
    build_equipment_lifecycle_gantt,
)
from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_equipment_status_as_of,
)
from capa_simulation.services.equipment_contract import (
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
)

WINDOW = {"start_date": date(2026, 1, 1), "end_date": date(2026, 6, 30)}


def _equipment(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = dict.fromkeys(EQUIPMENT_COLUMNS, None)
    row.update(
        {
            "설비명": "EQ-1",
            "공정대분류": "조립",
            "공정소분류": "SAW",
            "반입일정": date(2026, 2, 1),
            "Qual일정": date(2026, 3, 1),
            "확정상태": "계획",
            "보관유무": "N",
            "기존설비여부": "N",
            "레이아웃표시": "N",
        }
    )
    row.update(overrides)
    return pd.DataFrame([row], columns=list(EQUIPMENT_COLUMNS))


def _no_downtime() -> pd.DataFrame:
    return pd.DataFrame(columns=list(DOWNTIME_COLUMNS))


def test_point_events_become_adjoining_spans() -> None:
    """입고·Qual 은 점이다. 그 사이가 셋업 구간으로 길이를 가져야 한다."""
    spans = build_equipment_lifecycle_spans(_equipment(), _no_downtime(), **WINDOW)

    assert list(zip(spans["상태"], spans["시작일"], spans["종료일"], strict=True)) == [
        ("입고 예정", date(2026, 1, 1), date(2026, 1, 31)),
        ("셋업 진행중", date(2026, 2, 1), date(2026, 2, 28)),
        ("가용", date(2026, 3, 1), date(2026, 6, 30)),
    ]


def test_spans_never_overlap_on_the_switching_day() -> None:
    """앞 구간은 전환일 **전날**까지다. 같은 날 두 상태가 겹치면 그림이 거짓말한다."""
    spans = build_equipment_lifecycle_spans(_equipment(), _no_downtime(), **WINDOW)

    for earlier, later in zip(spans.itertuples(), spans.iloc[1:].itertuples(), strict=False):
        assert earlier.종료일 < later.시작일


def test_downtime_turns_off_the_day_after_it_ends() -> None:
    downtime = pd.DataFrame(
        [
            {
                "설비명": "EQ-1",
                "비가동유형": "PM",
                "시작일": date(2026, 4, 1),
                "종료일": date(2026, 4, 10),
                "상세사유": None,
                "비고": None,
            }
        ],
        columns=list(DOWNTIME_COLUMNS),
    )

    spans = build_equipment_lifecycle_spans(_equipment(), downtime, **WINDOW)
    offline = spans.loc[spans["상태"].eq("운영 비가동")]

    assert list(offline["시작일"]) == [date(2026, 4, 1)]
    assert list(offline["종료일"]) == [date(2026, 4, 10)]
    assert list(spans["상태"]) == ["입고 예정", "셋업 진행중", "가용", "운영 비가동", "가용"]


def test_spans_agree_with_the_as_of_status_on_every_day_it_covers() -> None:
    """구간은 상태 판정을 접은 것이다. 하루라도 어긋나면 두 화면이 다른 말을 한다."""
    equipment = _equipment(반출일정=date(2026, 5, 15))
    spans = build_equipment_lifecycle_spans(equipment, _no_downtime(), **WINDOW)

    for day in pd.date_range(WINDOW["start_date"], WINDOW["end_date"], freq="11D"):
        expected = build_equipment_status_as_of(equipment, _no_downtime(), as_of=day.date())[
            "상태"
        ].iloc[0]
        covering = spans.loc[
            (spans["시작일"] <= day.date()) & (spans["종료일"] >= day.date()), "상태"
        ]
        assert list(covering) == [expected], day.date()


def test_empty_master_returns_the_contract_columns() -> None:
    spans = build_equipment_lifecycle_spans(
        pd.DataFrame(columns=list(EQUIPMENT_COLUMNS)), _no_downtime(), **WINDOW
    )

    assert spans.empty
    assert "상태" in spans.columns


def test_gantt_reports_how_many_units_it_could_not_draw() -> None:
    """자른 것을 세지 않으면 「이게 전부」로 읽힌다."""
    spans = pd.DataFrame(
        {
            "설비명": [f"EQ-{index:02d}" for index in range(6)],
            "공정소분류": ["SAW"] * 6,
            "공정대분류": ["조립"] * 6,
            "상태": ["가용"] * 6,
            "시작일": [date(2026, 1, 1)] * 6,
            "종료일": [date(2026, 3, 1)] * 6,
        }
    )

    figure, hidden = build_equipment_lifecycle_gantt(spans, max_units=4)

    assert figure is not None
    assert hidden == 2


def test_a_single_day_span_keeps_a_visible_width() -> None:
    """Plotly 의 구간 끝은 배타적이다. 하루짜리를 그대로 넘기면 폭 0 이 된다."""
    spans = pd.DataFrame(
        {
            "설비명": ["EQ-1"],
            "공정소분류": ["SAW"],
            "공정대분류": ["조립"],
            "상태": ["가용"],
            "시작일": [date(2026, 1, 1)],
            "종료일": [date(2026, 1, 1)],
        }
    )

    figure, _ = build_equipment_lifecycle_gantt(spans)

    assert figure is not None
    assert figure.data[0].base[0] != figure.data[0].x[0]
