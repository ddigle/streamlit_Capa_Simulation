from capa_simulation.performance import PerformanceTrace


def test_performance_trace_records_phase_labels_and_total() -> None:
    trace = PerformanceTrace()

    trace.mark("기준정보")
    trace.mark("Figure")

    rows = trace.rows()
    assert [row["단계"] for row in rows] == ["기준정보", "Figure", "합계"]
    assert all(row["시간"].endswith("초") for row in rows)
