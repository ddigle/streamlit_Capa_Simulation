from streamlit.testing.v1 import AppTest


def test_reference_cache_requires_an_activated_duckdb_snapshot() -> None:
    test_script = """
import streamlit as st
from capa_simulation.io.reference_cache import get_effective_reference_tables

try:
    get_effective_reference_tables()
except RuntimeError as exc:
    st.write(str(exc))
"""
    app = AppTest.from_string(test_script).run()

    assert not app.exception
    assert "활성 DuckDB 시나리오가 없습니다" in app.markdown[0].value


def test_activated_duckdb_snapshot_is_the_only_effective_reference() -> None:
    test_script = """
import pandas as pd
import streamlit as st
from capa_simulation.io.reference_cache import (
    activate_persisted_reference_tables,
    get_effective_reference_tables,
    get_effective_reference_version,
)

version = activate_persisted_reference_tables(
    {"RQ_TEST": pd.DataFrame({"value": [1]})},
    "12345678-1234-1234-1234-123456789abc",
)
st.write(get_effective_reference_tables()["RQ_TEST"].loc[0, "value"])
st.write(version == get_effective_reference_version())
"""
    app = AppTest.from_string(test_script).run()

    assert not app.exception
    assert app.markdown[0].value == "`1`"
    assert app.markdown[1].value == "`True`"
