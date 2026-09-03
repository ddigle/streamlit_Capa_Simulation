# Purpose: bigdataquery registration 관련 정상·예외·회귀 동작을 검증한다.

from streamlit.testing.v1 import AppTest

REPORT_SCRIPT = """
import pandas as pd
import streamlit as st

from capa_simulation.components.bigdataquery_registration import (
    CONFLICT_REPORT_STATE_KEY,
    _render_reference_conflict_report,
)

st.session_state.setdefault(
    CONFLICT_REPORT_STATE_KEY,
    {
        "report": pd.DataFrame(
            {
                "RQ테이블": ["RQ_PKG_PLAN"],
                "충돌그룹": ["RQ_PKG_PLAN-0001"],
                "업무키컬럼": ["생산계획년월 | 제품정보"],
                "생산계획년월": [202608],
                "제품정보": ["Product-A"],
                "충돌컬럼": ["생산수량"],
                "후보값": ['[{"생산수량":100.0},{"생산수량":200.0}]'],
                "선택값": ['{"생산수량":100.0}'],
                "충돌행수": [2],
                "임시제외행수": [1],
                "후보원천행번호": ["1 | 2"],
                "선택원천행번호": [1],
                "임시처리": ["원천 행 순서상 첫 번째 행 유지"],
            }
        ),
        "file_name": "RQ_업무키_충돌_SIM-001.csv",
    },
)
_render_reference_conflict_report()
"""


def test_conflict_report_renders_summary_and_download() -> None:
    app = AppTest.from_string(REPORT_SCRIPT).run()

    assert not app.exception
    assert "1개 업무 키 그룹" in app.warning[0].value
    assert app.dataframe[0].value.loc[0, "RQ테이블"] == "RQ_PKG_PLAN"
    assert len(app.get("download_button")) == 1
