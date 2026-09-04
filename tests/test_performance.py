# Purpose: performance 관련 정상·예외·회귀 동작을 검증한다.

import pandas as pd

from capa_simulation.performance import PerformanceTrace
from capa_simulation.services.simulation_cache import build_home_simulation_cache_key


def test_performance_trace_records_phase_labels_and_total() -> None:
    trace = PerformanceTrace()

    trace.mark("기준정보")
    trace.mark("Figure")

    rows = trace.rows()
    assert [row["단계"] for row in rows] == ["기준정보", "Figure", "합계"]
    assert all(row["시간"].endswith("초") for row in rows)


def test_home_cache_key_is_small_and_tracks_display_order() -> None:
    display_order = pd.DataFrame({"페이지 구분": ["HOME"], "값표시순서": [1]})

    first = build_home_simulation_cache_key(
        reference_version=11,
        scenario_token="token-3",
        start_month=202608,
        end_month=202612,
        display_order=display_order,
    )
    same = build_home_simulation_cache_key(
        reference_version=11,
        scenario_token="token-3",
        start_month=202608,
        end_month=202612,
        display_order=display_order.copy(),
    )
    changed_order = display_order.assign(값표시순서=2)
    changed = build_home_simulation_cache_key(
        reference_version=11,
        scenario_token="token-3",
        start_month=202608,
        end_month=202612,
        display_order=changed_order,
    )

    assert first == same
    assert first != changed
    assert len(first) == 5
