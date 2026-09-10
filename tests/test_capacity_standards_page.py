# Purpose: capacity standards page 관련 정상·예외·회귀 동작을 검증한다.

import pandas as pd
from streamlit.testing.v1 import AppTest

TEST_SCRIPT = r"""
from pathlib import Path

import pandas as pd
import streamlit as st

import capa_simulation
import capa_simulation.components.grouped_monthly_table as grouped_table
import capa_simulation.components.hierarchical_monthly_table as hierarchical_table
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache


def empty_display_order():
    return pd.DataFrame(
        columns=[
            "페이지 구분",
            "탭 구분",
            "정렬우선순위",
            "분류컬럼",
            "정렬방식",
            "분류값",
            "값표시순서",
            "활성여부",
        ]
    )


tables = {
    "RQ_UPEH": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "STEP_SEQ": ["P100"],
            "MCP_SEQ": ["1A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "WF 구분": ["PKG"],
            "소요기준": ["PKG"],
            "UPEH": [100.0],
            "ST": [None],
        }
    ),
    "RQ_RUN_RATE": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "공정": ["Process-A"],
            "양산구분": ["양산"],
            "CAPA_RUN_RATE": [0.9],
        }
    ),
    "RQ_VITAL": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "공정": ["Process-A"],
            "양산구분": ["양산"],
            "편중률": [1.0],
        }
    ),
    "RQ_RUN_DAY": pd.DataFrame(
        {"생산계획년월": [202608], "공정": ["Process-A"], "RUN_DAY": [31.0]}
    ),
    "RQ_LOT_RATIO": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "STEP_SEQ": ["P100"],
            "MCP_SEQ": ["1A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "WF 구분": ["PKG"],
            "Lot 측정률": [1.0],
        }
    ),
    "RQ_WF_RATIO": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "STEP_SEQ": ["P100"],
            "MCP_SEQ": ["1A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "WF 구분": ["PKG"],
            "WF측정률": [1.0],
        }
    ),
    "RQ_PKG_PLAN": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "양산구분": ["양산"],
            "CS": ["MP"],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "생산수량": [100.0],
        }
    ),
    "RQ_YLD": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "WF 구분": ["PKG"],
            "EDS_수율": [1.0],
            "BE_수율": [1.0],
        }
    ),
    "RQ_REQB": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "CS": ["MP"],
            "WF 구분": ["PKG"],
            "STEP_SEQ": ["P100"],
            "MCP_SEQ": ["1A"],
            "소요기준": ["PKG"],
        }
    ),
    "RQ_MODULE": pd.DataFrame({"공정": ["Process-A"], "모듈수": [1.0]}),
    "RQ_EQP_OWN": pd.DataFrame(
        {"생산계획년월": [202608], "공정": ["Process-A"], "설비보유": [2.0]}
    ),
    "RQ_EQP_LENT": pd.DataFrame(
        {"생산계획년월": [202608], "공정": ["Process-A"], "설비대여평가": [0.0]}
    ),
    "RQ_EQP_AVBL": pd.DataFrame(
        {"생산계획년월": [202608], "공정": ["Process-A"], "가용대수": [2.0]}
    ),
    "RQ_CHIP_QTY": pd.DataFrame(),
    "RQ_CHIP_EQ": pd.DataFrame(),
    "RQ_DISPLAY_ORDER": empty_display_order(),
}

# 제외 STEP 을 네 줄 붙여 세 건수가 모두 다른 값으로 갈리게 한다. P100 은 살아남으므로
# 표·확보율은 계속 그려지고 제외 경고만 추가로 나온다.
#   P200 — Lot 측정률 0. 대당 Capa 에서 빠지고, 계획에 있는 제품이라 부하량이 붙는다.
#   P300 — WF측정률 0. 마찬가지로 대당 Capa 에서 빠지고 부하량이 붙는다.
#   P400 — RQ_REQB 에만 있어 대당 Capa 가 아예 없고, 계획에 있는 제품이라 부하량이 붙는다.
#   P500 — RQ_REQB 에만 있고 RQ_PKG_PLAN 에 없는 제품이라 부하량이 0 이다.
# 그래서 대당 Capa 제외 2건 · 소요대수 제외 4건 · 그중 부하량 발생 3건이다. 셋이 서로 다르고
# 모두 1 이 아니므로 건수의 출처가 어긋나거나 상수로 박히면 문구가 반드시 틀어진다.
ADD_EXCLUDED_STEP = False
if ADD_EXCLUDED_STEP:

    def clone_step(frame, **overrides):
        row = frame.iloc[0].to_dict()
        row.update(overrides)
        return pd.concat([frame, pd.DataFrame([row])], ignore_index=True)

    lot_zero_step = {"STEP_SEQ": "P200", "MCP_SEQ": "2A"}
    wf_zero_step = {"STEP_SEQ": "P300", "MCP_SEQ": "3A"}
    no_capacity_step = {"STEP_SEQ": "P400", "MCP_SEQ": "4A"}
    unplanned_step = {"STEP_SEQ": "P500", "MCP_SEQ": "5A", "제품정보": "Product-B"}

    for step in (lot_zero_step, wf_zero_step):
        tables["RQ_UPEH"] = clone_step(tables["RQ_UPEH"], **step)
    tables["RQ_LOT_RATIO"] = clone_step(
        tables["RQ_LOT_RATIO"], **lot_zero_step, **{"Lot 측정률": 0.0}
    )
    tables["RQ_LOT_RATIO"] = clone_step(tables["RQ_LOT_RATIO"], **wf_zero_step)
    tables["RQ_WF_RATIO"] = clone_step(tables["RQ_WF_RATIO"], **lot_zero_step)
    tables["RQ_WF_RATIO"] = clone_step(tables["RQ_WF_RATIO"], **wf_zero_step, **{"WF측정률": 0.0})
    for step in (lot_zero_step, wf_zero_step, no_capacity_step, unplanned_step):
        tables["RQ_REQB"] = clone_step(tables["RQ_REQB"], **step)

active = {
    "reference_version": 1,
    "revision": 1,
    # 계산 캐시 키. 프로세스 전역 캐시라 다른 테스트 파일의 가짜 active 와 겹치면 안 된다.
    "content_token": "test-capacity-standards-page",
    "tables": {
        name: frame.copy()
        for name, frame in tables.items()
        if name in scenario_state.EDITABLE_SCENARIO_TABLES
    },
}

original_reference_version = reference_cache.get_effective_reference_version
original_reference_tables = reference_cache.get_effective_reference_tables
original_ensure_active = scenario_state.ensure_active_scenario
original_scenario_table = scenario_state.scenario_table
original_apply_month_updates = scenario_state.apply_month_updates
original_hierarchical_render = hierarchical_table.render_hierarchical_monthly_table
original_grouped_render = grouped_table.render_grouped_monthly_table
original_capacity_and_demand = simulation_cache.get_scenario_capacity_and_demand
original_securement_rate = simulation_cache.get_securement_rate

reference_cache.get_effective_reference_version = lambda: 1
reference_cache.get_effective_reference_tables = lambda: tables
scenario_state.ensure_active_scenario = lambda _tables, _version: active
scenario_state.scenario_table = lambda scenario, name: scenario["tables"][name].copy()


def capture_month_updates(_scenario, replacements, _start, _end):
    st.session_state["test_step_reqb_rows"] = len(replacements["RQ_REQB"])
    return _scenario


scenario_state.apply_month_updates = capture_month_updates


def capture_hierarchical_table(*_args, **kwargs):
    key = kwargs.get("key")
    if key:
        st.session_state[f"captured_dimensions::{key}"] = kwargs.get(
            "classification_columns"
        )


hierarchical_table.render_hierarchical_monthly_table = capture_hierarchical_table
grouped_table.render_grouped_monthly_table = lambda *_args, **_kwargs: None

original_download_button = st.download_button


def record_download_button(label, *args, **kwargs):
    downloads = st.session_state.setdefault("captured_downloads", {})
    downloads[kwargs.get("key")] = {"label": label, "file_name": kwargs.get("file_name")}
    return original_download_button(label, *args, **kwargs)


# 제외 경로 테스트는 대당 Capa·소요대수·확보율을 실제로 돌려야 하므로 갈아끼우지 않는다.
STUB_CALCULATIONS = True
if STUB_CALCULATIONS:
    required_equipment_stub = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "Area_Name": ["Main"],
            "공정": ["Process-A"],
            "양산구분": ["양산"],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "Capa Code": ["CAPA-A"],
            "Customer": ["Customer-A"],
            "CS": ["MP"],
            "WF 구분": ["PKG"],
            "STEP_SEQ": ["P100"],
            "MCP_SEQ": ["1A"],
            "소요기준": ["PKG"],
            "부하량": [100.0],
            "대당 Capa": [100.0],
            "소요대수": [1.0],
        }
    )
    simulation_cache.get_scenario_capacity_and_demand = lambda *_args, **_kwargs: (
        pd.DataFrame(),
        required_equipment_stub.copy(),
    )
    simulation_cache.get_securement_rate = lambda *_args: pd.DataFrame(
        {
            "생산계획년월": [202608],
            "공정": ["Process-A"],
            "가용대수": [2.0],
            "소요대수": [1.0],
            "확보율": [2.0],
        }
    )

try:
    # `file_name` 은 위젯 proto 에 실리지 않아 AppTest 로는 볼 수 없다. 버튼은 실제로 그리고
    # 인자만 세션 상태에 적어 둔다. streamlit 모듈 자체를 바꾸는 패치라 원복이 반드시
    # 돌아야 하고, 그래서 try 안에서만 갈아끼운다.
    st.download_button = record_download_button
    st.session_state["production_month_range_v2"] = ("2026-08", "2026-08")
    PAGE_NAME = "capacity_standards.py"
    page = Path(capa_simulation.__file__).resolve().parents[2] / "app_pages" / PAGE_NAME
    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))
finally:
    reference_cache.get_effective_reference_version = original_reference_version
    reference_cache.get_effective_reference_tables = original_reference_tables
    scenario_state.ensure_active_scenario = original_ensure_active
    scenario_state.scenario_table = original_scenario_table
    scenario_state.apply_month_updates = original_apply_month_updates
    hierarchical_table.render_hierarchical_monthly_table = original_hierarchical_render
    grouped_table.render_grouped_monthly_table = original_grouped_render
    simulation_cache.get_scenario_capacity_and_demand = original_capacity_and_demand
    # 모듈 속성 교체는 프로세스 전역이다. 원복하지 않으면 같은 프로세스의 다른 테스트가
    # 가짜 확보율을 본다.
    simulation_cache.get_securement_rate = original_securement_rate
    st.download_button = original_download_button
"""

PROCESS_TEST_SCRIPT = TEST_SCRIPT.replace(
    'PAGE_NAME = "capacity_standards.py"',
    'PAGE_NAME = "process_securement.py"',
)
LOAD_TEST_SCRIPT = TEST_SCRIPT.replace(
    'PAGE_NAME = "capacity_standards.py"',
    'PAGE_NAME = "load_conversion.py"',
)


def _exclusion_script(page_name: str) -> str:
    """제외되는 STEP 이 섞인 시나리오로 페이지 한 장을 여는 스크립트.

    계산 스텁을 끄고 활성 시나리오 표를 그대로 파이프라인에 태운다. 캐시 키가 되는
    `content_token` 도 바꾼다 — `st.cache_data` 는 프로세스 전역이라 정상 픽스처의
    결과가 그대로 적중하면 제외가 생기지 않는다.
    """
    return (
        TEST_SCRIPT.replace(
            'PAGE_NAME = "capacity_standards.py"',
            f'PAGE_NAME = "{page_name}"',
        )
        .replace("ADD_EXCLUDED_STEP = False", "ADD_EXCLUDED_STEP = True")
        .replace("STUB_CALCULATIONS = True", "STUB_CALCULATIONS = False")
        .replace('"test-capacity-standards-page"', '"test-capacity-exclusion-page"')
    )


EXCLUSION_TEST_SCRIPT = _exclusion_script("capacity_standards.py")
EXCLUSION_PROCESS_TEST_SCRIPT = _exclusion_script("process_securement.py")

# 제외 상세 표에 실리는 제외사유. services 쪽 상수가 바뀌면 화면 문구도 함께 깨진다.
LOT_RATIO_EXCLUSION_REASON = "Lot 측정률 0 이하"
WF_RATIO_EXCLUSION_REASON = "WF측정률 0 이하"
MISSING_CAPACITY_REASON = "대당 Capa 없음"


def _download(app: AppTest, key: str) -> dict[str, str]:
    """`render_csv_download` 가 실제로 그린 버튼 하나를 키로 찾는다."""
    labels = {button.key: button.label for button in app.download_button}
    assert key in labels, f"CSV 다운로드 버튼이 없습니다: {sorted(labels)}"
    captured = app.session_state["captured_downloads"][key]
    return {"label": labels[key], "file_name": captured["file_name"]}


def _exclusion_frame(app: AppTest, reason: str) -> pd.DataFrame:
    """제외사유 컬럼에 해당 문자열이 든 상세 표를 찾는다."""
    for frame in app.dataframe:
        value = frame.value
        if "제외사유" in getattr(value, "columns", []) and reason in set(value["제외사유"]):
            return value
    raise AssertionError(f"제외 상세 표가 없습니다: {reason}")


def test_capacity_standards_shows_the_excluded_capacity_rows_with_a_csv_download() -> None:
    app = AppTest.from_string(EXCLUSION_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert "대당 Capa 산출에서 2개 기준을 제외했습니다." in {
        warning.value for warning in app.warning
    }
    assert "제외 기준정보 확인" in {expander.label for expander in app.expander}
    excluded = _exclusion_frame(app, LOT_RATIO_EXCLUSION_REASON)
    assert excluded["STEP_SEQ"].tolist() == ["P300", "P200"]
    assert excluded["제외사유"].tolist() == [
        WF_RATIO_EXCLUSION_REASON,
        LOT_RATIO_EXCLUSION_REASON,
    ]
    assert excluded["Lot 측정률"].tolist() == [1.0, 0.0]
    assert excluded["WF측정률"].tolist() == [0.0, 1.0]
    assert _download(app, "download_unit_capacity_exclusions_csv") == {
        "label": "CSV 다운로드",
        "file_name": "Capa_Unit_Capacity_Exclusions_202608_202608.csv",
    }


def test_process_securement_shows_both_exclusion_expanders_with_csv_downloads() -> None:
    app = AppTest.from_string(EXCLUSION_PROCESS_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    warnings = {warning.value for warning in app.warning}
    assert "0 이하 기준값으로 대당 Capa 2건을 제외했습니다." in warnings
    assert "대당 Capa가 없어 소요대수 산출에서 4건을 제외했습니다 (부하량 발생 3건)." in warnings
    assert {"제외된 대당 Capa 기준정보", "소요대수 제외 기준정보"}.issubset(
        {expander.label for expander in app.expander}
    )

    capacity_exclusions = _exclusion_frame(app, LOT_RATIO_EXCLUSION_REASON)
    assert capacity_exclusions["STEP_SEQ"].tolist() == ["P300", "P200"]
    required_exclusions = _exclusion_frame(app, MISSING_CAPACITY_REASON)
    assert required_exclusions["STEP_SEQ"].tolist() == ["P200", "P300", "P400", "P500"]
    # 제외된 STEP 은 대당 Capa 가 없을 뿐 부하량은 붙는다. 그 값이 화면에 남아야
    # 사용자가 얼마나 잘리는지 안다. 계획에 없는 제품만 0 이라 경고의 괄호 안 건수와 갈린다.
    assert required_exclusions["부하량"].tolist() == [100.0, 100.0, 100.0, 0.0]

    assert _download(app, "download_capacity_exclusions_csv") == {
        "label": "CSV 다운로드",
        "file_name": "Capa_Unit_Capacity_Exclusions_202608_202608.csv",
    }
    assert _download(app, "download_required_exclusions_csv") == {
        "label": "CSV 다운로드",
        "file_name": "Capa_Required_Equipment_Exclusions_202608_202608.csv",
    }


def test_capacity_editors_show_route_keys_without_exceptions() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    expected_inputs = {
        "UPEH": "RQ_UPEH 표 붙여넣기",
        "효율": "RQ_RUN_RATE 표 붙여넣기",
        "여유율": "RQ_VITAL 표 붙여넣기",
        "Lot측정률": "RQ_LOT_RATIO 표 붙여넣기",
        "WF측정률": "RQ_WF_RATIO 표 붙여넣기",
        "일수": "RQ_RUN_DAY 표 붙여넣기",
    }
    route_editor_tabs = {"UPEH", "Lot측정률", "WF측정률"}
    for tab_name, input_label in expected_inputs.items():
        app.session_state["capacity_standards_active_tab"] = tab_name
        app.run()

        assert not app.exception
        assert input_label in {text_area.label for text_area in app.text_area}
        if tab_name in route_editor_tabs:
            assert any(
                list(frame.value.columns)[-3:-1] == ["STEP_SEQ", "MCP_SEQ"]
                for frame in app.dataframe
            )


def test_load_input_tabs_expose_plan_and_yield_clipboard_round_trip() -> None:
    app = AppTest.from_string(LOAD_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert {text_area.label for text_area in app.text_area}.issuperset(
        {"RQ_PKG_PLAN 표 붙여넣기", "RQ_YLD 표 붙여넣기"}
    )


def test_equipment_tab_exposes_three_rq_clipboard_inputs() -> None:
    app = AppTest.from_string(PROCESS_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert {text_area.label for text_area in app.text_area}.issuperset(
        {
            "RQ_EQP_OWN 표 붙여넣기",
            "RQ_EQP_LENT 표 붙여넣기",
            "RQ_EQP_AVBL 표 붙여넣기",
        }
    )


def test_required_equipment_detail_exposes_route_filters() -> None:
    app = AppTest.from_string(PROCESS_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    required_detail = next(toggle for toggle in app.toggle if toggle.label == "상세")
    app = required_detail.set_value(True).run()

    assert not app.exception
    filter_labels = [widget.label for widget in app.multiselect]
    assert "Step" in filter_labels
    assert "MCP" in filter_labels
    assert filter_labels.index("MCP") == filter_labels.index("Step") + 1
    assert app.session_state["captured_dimensions::required_equipment_detail_table"][-2:] == [
        "STEP_SEQ",
        "MCP_SEQ",
    ]


def test_step_editor_clones_the_selected_route_in_one_submit() -> None:
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    new_mcp = next(widget for widget in app.text_input if widget.label == "신규 MCP_SEQ")
    app = new_mcp.set_value("2A").run()
    new_step = next(widget for widget in app.text_input if widget.label == "신규 STEP_SEQ")
    app = new_step.set_value("P200").run()
    add_button = next(button for button in app.button if button.label == "STEP 일괄 추가")
    app = add_button.click().run()

    assert not app.exception
    assert app.session_state["test_step_reqb_rows"] == 2


def test_step_tab_widgets_render_while_the_tab_is_hidden() -> None:
    """숨은 탭에서는 그림만 건너뛴다. 위젯까지 건너뛰면 탭을 오갈 때 선택값이 초기화된다."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    # 기본 탭은 유효 Capa 다. STEP 구성 탭의 경로 선택은 닫혀 있어도 그려져야 한다.
    assert app.selectbox(key="capacity_step_route").options
