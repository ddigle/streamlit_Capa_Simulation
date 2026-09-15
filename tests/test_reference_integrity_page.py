# Purpose: Dynamic Capa 상위 화면이 공정 표시명을 쓰고 선택값은 원본으로 두는지 검증한다.

import pandas as pd
from streamlit.testing.v1 import AppTest

TEST_SCRIPT = r"""
from pathlib import Path

import pandas as pd
import streamlit as st

import capa_simulation
import capa_simulation.components.process_labels as process_labels_module
from capa_simulation.services.dynamic_capacity import build_dynamic_capacity_demo

# 데모 공정명은 합성 표본이라 리터럴로 고정하지 않는다. 표본에서 첫 공정을 뽑아 규칙을
# 만든다 — 나머지 공정은 매핑 밖이라 원본 그대로 나와야 한다.
demo_processes = sorted(build_dynamic_capacity_demo()["공정"].astype(str).unique())
st.session_state["renamed_source"] = demo_processes[0]
st.session_state["untouched_source"] = demo_processes[1]

original_get_process_labels = process_labels_module.get_process_labels
APPLY_RENAME = False
if APPLY_RENAME:
    renamed = process_labels_module.process_labels_from_rules(
        pd.DataFrame([(demo_processes[0], "표시공정")], columns=["공정", "표시명"]), 5
    )
    process_labels_module.get_process_labels = lambda: renamed

try:
    page = Path(capa_simulation.__file__).resolve().parents[2] / "app_pages"
    source = page / "reference_integrity.py"
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"))
finally:
    process_labels_module.get_process_labels = original_get_process_labels
"""

RENAMED_TEST_SCRIPT = TEST_SCRIPT.replace("APPLY_RENAME = False", "APPLY_RENAME = True")

PRIORITY_COLUMNS = {"순위", "공정", "Capa 실현률"}


def _priority_frame(app: AppTest) -> pd.DataFrame:
    for frame in app.dataframe:
        if PRIORITY_COLUMNS.issubset(set(getattr(frame.value, "columns", []))):
            return frame.value
    raise AssertionError("관리 우선순위 표가 없습니다.")


def test_priority_table_and_process_selector_show_the_display_name() -> None:
    app = AppTest.from_string(RENAMED_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    renamed_source = app.session_state["renamed_source"]
    untouched_source = app.session_state["untouched_source"]

    priority = _priority_frame(app)
    assert "표시공정" in set(priority["공정"])
    assert renamed_source not in set(priority["공정"])
    # 매핑 밖 공정은 원본 그대로다.
    assert untouched_source in set(priority["공정"])

    process_filter = app.selectbox(key="dynamic_capacity_process_filter")
    assert "표시공정" in process_filter.options
    assert renamed_source not in process_filter.options


def test_selecting_a_renamed_process_keeps_the_original_value() -> None:
    """표기만 표시명이다. 선택값이 표시명이면 아래 `eq` 가 원본 컬럼과 맞지 않는다."""
    app = AppTest.from_string(RENAMED_TEST_SCRIPT, default_timeout=60).run()
    renamed_source = app.session_state["renamed_source"]

    # 워터폴은 「공정 상세」 탭 안이고 숨은 탭에서는 그리지 않는다. 조회 조건 위젯은
    # 숨어 있어도 그려지므로 선택은 어느 탭에서든 걸린다.
    app.session_state["dynamic_capa_active_tab"] = "공정 상세"
    app.selectbox(key="dynamic_capacity_process_filter").set_value(renamed_source)
    app.run()

    assert not app.exception
    assert app.session_state["dynamic_capacity_process_filter"] == renamed_source
    assert any("표시공정 공정의 표준 Capa부터" in caption.value for caption in app.caption)


def test_priority_table_stays_original_without_a_rename_profile() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert app.session_state["renamed_source"] in set(_priority_frame(app)["공정"])
