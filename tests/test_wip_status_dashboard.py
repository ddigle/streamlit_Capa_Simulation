from datetime import date

import pandas as pd

from capa_simulation.components.wip_status_dashboard import (
    WIP_GRID_CELL_HEIGHT_PX,
    WIP_GRID_CELL_WIDTH_PX,
    build_wip_status_grid_figure,
)
from capa_simulation.services.wip_status import build_wip_history_demo


def test_wip_grid_places_steps_in_columns_and_products_in_rows() -> None:
    routes = pd.DataFrame(
        {
            "공정": ["T-Process", "P-Process", "T-Process", "P-Process"],
            "STEP_SEQ": ["T100", "P100", "T100", "P100"],
            "제품정보": ["Product-B", "Product-B", "Product-A", "Product-A"],
            "소요기준": ["WF", "CHIP", "WF", "CHIP"],
        }
    )
    dates = pd.date_range("2026-09-01", "2026-09-02", freq="D")
    standard_rows: list[dict[str, object]] = []
    for current_date in dates:
        for process, basis in (("P-Process", "CHIP"), ("T-Process", "WF")):
            for product in ("Product-A", "Product-B"):
                standard_rows.append(
                    {
                        "일자": current_date,
                        "공정": process,
                        "소요기준": basis,
                        "제품정보": product,
                        "일 표준 가능량": 100.0,
                    }
                )
    history = build_wip_history_demo(
        routes,
        pd.DataFrame(standard_rows),
        date(2026, 9, 1),
        date(2026, 9, 2),
        today=date(2026, 9, 1),
    )

    figure = build_wip_status_grid_figure(
        history,
        routes,
        ["Product-B", "Product-A"],
        date(2026, 9, 1),
        date(2026, 9, 2),
    )

    titles = [annotation.text for annotation in figure.layout.annotations]
    assert titles[:4] == [
        "<b>P100</b> · P-Process<br>Product-B",
        "<b>T100</b> · T-Process<br>Product-B",
        "<b>P100</b> · P-Process<br>Product-A",
        "<b>T100</b> · T-Process<br>Product-A",
    ]
    assert figure.layout.width == 2 * WIP_GRID_CELL_WIDTH_PX + 90
    assert figure.layout.height == 2 * WIP_GRID_CELL_HEIGHT_PX + 110
    assert figure.layout.barmode == "group"
    trace_names = {trace.name for trace in figure.data}
    assert {"보유 재공", "유입", "표준 가능량"}.issubset(trace_names)
    assert {"Flow 충족", "Flow 부족"} & trace_names
