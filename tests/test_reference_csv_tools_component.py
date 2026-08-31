from streamlit.testing.v1 import AppTest


def test_reference_csv_expander_can_identify_equipment_category() -> None:
    app = AppTest.from_string(
        """
import pandas as pd

from capa_simulation.components.reference_csv_tools import render_reference_csv_tools

source = pd.DataFrame({"공정": ["Process-A"], "202608": [1.0]})
for table_name, label in (
    ("RQ_EQP_OWN", "보유설비 - CSV 일괄 수정"),
    ("RQ_EQP_LENT", "대여설비 - CSV 일괄 수정"),
    ("RQ_EQP_AVBL", "가용설비 - CSV 일괄 수정"),
):
    render_reference_csv_tools(
        source,
        table_name=table_name,
        key_columns=["공정"],
        file_name=f"{table_name}.csv",
        key=table_name.lower(),
        expander_label=label,
    )
""",
        default_timeout=30,
    ).run()

    assert not app.exception
    assert [expander.label for expander in app.status] == [
        "보유설비 - CSV 일괄 수정",
        "대여설비 - CSV 일괄 수정",
        "가용설비 - CSV 일괄 수정",
    ]
