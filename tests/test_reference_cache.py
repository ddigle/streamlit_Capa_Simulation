# Purpose: reference cache 관련 정상·예외·회귀 동작을 검증한다.

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


def test_both_reads_without_an_activated_snapshot_raise_the_no_active_revision_kind() -> None:
    """불러온 리비전이 없다는 것을 종류로 알린다 — 오류를 글로 바꾸는 쪽
    (`page_bootstrap.bootstrap_error_message`)이 보관본만 남은 저장소를 갈라 낸다. 계산 화면들이
    잡는 `RuntimeError` 그대로다."""
    test_script = """
import streamlit as st
from capa_simulation.io.reference_cache import (
    NoActiveRevision,
    get_effective_reference_tables,
    get_effective_reference_version,
)

for read in (get_effective_reference_tables, get_effective_reference_version):
    try:
        read()
    except NoActiveRevision as exc:
        st.write(isinstance(exc, RuntimeError))
"""
    app = AppTest.from_string(test_script).run()

    assert not app.exception
    assert [item.value for item in app.markdown] == ["`True`", "`True`"]
