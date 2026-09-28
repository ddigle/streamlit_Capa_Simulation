# Purpose: reference csv tools component 관련 정상·예외·회귀 동작을 검증한다.

from streamlit.testing.v1 import AppTest


def test_each_clipboard_form_names_its_table_and_template() -> None:
    """팝업 하나에 붙여넣기 칸 하나다. 칸 이름이 어느 RQ 인지 말하고 양식 버튼이 함께 선다."""
    app = AppTest.from_string(
        """
import pandas as pd

from capa_simulation.components.reference_csv_tools import render_reference_clipboard_form

source = pd.DataFrame({"공정": ["Process-A"], "202608": [1.0]})
for table_name in ("RQ_EQP_OWN", "RQ_EQP_LENT", "RQ_EQP_AVBL"):
    render_reference_clipboard_form(
        source,
        table_name=table_name,
        key_columns=["공정"],
        file_name=f"{table_name}.csv",
        key=table_name.lower(),
    )
""",
        default_timeout=30,
    ).run()

    assert not app.exception
    assert {text_area.label for text_area in app.text_area} == {
        "RQ_EQP_OWN 표 붙여넣기",
        "RQ_EQP_LENT 표 붙여넣기",
        "RQ_EQP_AVBL 표 붙여넣기",
    }
    assert {button.key for button in app.download_button} == {
        "rq_eqp_own_download",
        "rq_eqp_lent_download",
        "rq_eqp_avbl_download",
    }
