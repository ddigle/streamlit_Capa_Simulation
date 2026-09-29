# Purpose: capacity standards page 관련 정상·예외·회귀 동작을 검증한다.

import ast
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

TEST_SCRIPT = r"""
from pathlib import Path

import pandas as pd
import streamlit as st

import capa_simulation
import capa_simulation.components.grouped_monthly_table as grouped_table
import capa_simulation.components.hierarchical_monthly_table as hierarchical_table
import capa_simulation.components.process_labels as process_labels_module
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
            "WF 구분": ["BUFFER"],
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
            "WF 구분": ["BUFFER"],
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
            "WF 구분": ["BUFFER"],
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
            "Pack Code": ["PK-1"],
            "생산수량": [100.0],
        }
    ),
    "RQ_YLD": pd.DataFrame(
        {
            "생산계획년월": [202608],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "WF 구분": ["BUFFER"],
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
            "WF 구분": ["BUFFER"],
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
#   P200 — Lot 측정률 음수. 대당 Capa 에서 빠지고, 계획에 있는 제품이라 부하량이 붙는다.
#   P300 — WF측정률 음수. 마찬가지로 대당 Capa 에서 빠지고 부하량이 붙는다.
# 0 이 아니라 음수를 쓰는 이유: 측정률 0 은 1.0 으로 올라가 제외되지 않는다.
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

    lot_negative_step = {"STEP_SEQ": "P200", "MCP_SEQ": "2A"}
    wf_negative_step = {"STEP_SEQ": "P300", "MCP_SEQ": "3A"}
    no_capacity_step = {"STEP_SEQ": "P400", "MCP_SEQ": "4A"}
    unplanned_step = {"STEP_SEQ": "P500", "MCP_SEQ": "5A", "제품정보": "Product-B"}

    for step in (lot_negative_step, wf_negative_step):
        tables["RQ_UPEH"] = clone_step(tables["RQ_UPEH"], **step)
    tables["RQ_LOT_RATIO"] = clone_step(
        tables["RQ_LOT_RATIO"], **lot_negative_step, **{"Lot 측정률": -0.5}
    )
    tables["RQ_LOT_RATIO"] = clone_step(tables["RQ_LOT_RATIO"], **wf_negative_step)
    tables["RQ_WF_RATIO"] = clone_step(tables["RQ_WF_RATIO"], **lot_negative_step)
    tables["RQ_WF_RATIO"] = clone_step(
        tables["RQ_WF_RATIO"], **wf_negative_step, **{"WF측정률": -0.5}
    )
    for step in (lot_negative_step, wf_negative_step, no_capacity_step, unplanned_step):
        tables["RQ_REQB"] = clone_step(tables["RQ_REQB"], **step)

# 소요기준 PKG 의 Buffer 가 아닌 행 하나. 계산에서 빠지되 「대당 Capa 가 없어」 경고가 아니라
# 안내로 따로 알려야 한다 — 고칠 기준정보가 없는데 고치러 가게 하면 안 된다. 기본은 꺼 둔다.
ADD_UNCOUNTED_PKG_ROW = False
if ADD_UNCOUNTED_PKG_ROW:
    core_row = tables["RQ_REQB"].iloc[0].to_dict()
    core_row.update({"WF 구분": "CORE", "STEP_SEQ": "P600", "MCP_SEQ": "6A"})
    tables["RQ_REQB"] = pd.concat(
        [tables["RQ_REQB"], pd.DataFrame([core_row])], ignore_index=True
    )

# 공정 필터를 보려면 공정이 둘 이상이어야 한다. 기본은 꺼 두어 다른 테스트의 건수 문구를
# 건드리지 않는다.
ADD_SECOND_PROCESS = False
if ADD_SECOND_PROCESS:
    for table_name in (
        "RQ_UPEH",
        "RQ_RUN_RATE",
        "RQ_VITAL",
        "RQ_RUN_DAY",
        "RQ_LOT_RATIO",
        "RQ_WF_RATIO",
        "RQ_REQB",
        "RQ_MODULE",
        "RQ_EQP_OWN",
        "RQ_EQP_LENT",
        "RQ_EQP_AVBL",
    ):
        second_row = tables[table_name].iloc[0].to_dict()
        second_row["공정"] = "Process-B"
        tables[table_name] = pd.concat(
            [tables[table_name], pd.DataFrame([second_row])], ignore_index=True
        )

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
    if st.session_state.get("test_fail_month_updates"):
        raise ValueError("PROBE_APPLY_ERROR")
    if "RQ_REQB" in replacements:
        st.session_state["test_step_reqb_rows"] = len(replacements["RQ_REQB"])
    # 적용 버튼은 `st.rerun()` 을 부르고 AppTest 는 그 rerun 에서 버튼값을 되돌리지 않아
    # 같은 적용이 여러 번 잡힌다. 사용자가 실제로 누른 첫 적용만 남긴다.
    st.session_state.setdefault(
        "test_month_updates",
        {name: frame.copy() for name, frame in replacements.items()},
    )
    return _scenario


scenario_state.apply_month_updates = capture_month_updates


def capture_hierarchical_table(*args, **kwargs):
    key = kwargs.get("key")
    if key:
        st.session_state[f"captured_dimensions::{key}"] = kwargs.get(
            "classification_columns"
        )
        frame = args[0] if args else kwargs.get("data")
        if frame is not None and "공정" in getattr(frame, "columns", []):
            st.session_state[f"captured_processes::{key}"] = sorted(set(frame["공정"]))


hierarchical_table.render_hierarchical_monthly_table = capture_hierarchical_table
grouped_table.render_grouped_monthly_table = lambda *_args, **_kwargs: None

original_download_button = st.download_button


def record_download_button(label, *args, **kwargs):
    downloads = st.session_state.setdefault("captured_downloads", {})
    downloads[kwargs.get("key")] = {
        "label": label,
        "file_name": kwargs.get("file_name"),
        # 내보낸 바이트는 위젯 proto 에 실리지 않는다. 파일이 원본 공정명인지 보려면
        # 여기서 잡아 두는 수밖에 없다.
        "data": kwargs.get("data"),
    }
    return original_download_button(label, *args, **kwargs)


# 화면 표기만 표시명으로 바꾼다. 페이지는 exec 로 새로 읽히므로 모듈 속성을 갈아끼우면
# 페이지의 `from ... import get_process_labels` 가 이 가짜를 집는다.
APPLY_RENAME = False
original_get_process_labels = process_labels_module.get_process_labels
# **표시명이 없는 경우에도 반드시 갈아끼운다.** 진짜 `get_process_labels` 는
# `settings.DUCKDB_PATH` 의 **공용 프로필**을 읽는데, 그것은 시나리오가 아니라 그 PC 의 DB 에
# 딸린 상태다. 갈아끼우지 않으면 「표시명이 없을 때」를 검사한다는 테스트가 실은 「이 PC 에
# 표시명이 없다」에 기대게 되고, 표시명을 쓰는 환경에서 같은 코드가 실패한다.
if APPLY_RENAME:
    rename_rules = pd.DataFrame([("Process-A", "가공")], columns=["공정", "표시명"])
    rename_version = 7
else:
    rename_rules = pd.DataFrame(columns=["공정", "표시명"])
    rename_version = 0
process_profile = process_labels_module.process_labels_from_rules(rename_rules, rename_version)
process_labels_module.get_process_labels = lambda: process_profile


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
            "WF 구분": ["BUFFER"],
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
    PAGE_NAME = "reference_data.py"
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
    process_labels_module.get_process_labels = original_get_process_labels
    st.download_button = original_download_button
"""

PROCESS_TEST_SCRIPT = TEST_SCRIPT.replace(
    'PAGE_NAME = "reference_data.py"',
    'PAGE_NAME = "calculation_result.py"',
)
LOAD_TEST_SCRIPT = TEST_SCRIPT.replace(
    'PAGE_NAME = "reference_data.py"',
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
            'PAGE_NAME = "reference_data.py"',
            f'PAGE_NAME = "{page_name}"',
        )
        .replace("ADD_EXCLUDED_STEP = False", "ADD_EXCLUDED_STEP = True")
        .replace("STUB_CALCULATIONS = True", "STUB_CALCULATIONS = False")
        .replace('"test-capacity-standards-page"', '"test-capacity-exclusion-page"')
    )


EXCLUSION_TEST_SCRIPT = _exclusion_script("reference_data.py")
EXCLUSION_PROCESS_TEST_SCRIPT = _exclusion_script("calculation_result.py")
# 위 제외 STEP 넷에 PKG 의 Core 행 하나를 더한다. 캐시 키가 되는 토큰도 따로 둔다.
PKG_UNCOUNTED_TEST_SCRIPT = EXCLUSION_PROCESS_TEST_SCRIPT.replace(
    "ADD_UNCOUNTED_PKG_ROW = False", "ADD_UNCOUNTED_PKG_ROW = True"
).replace('"test-capacity-exclusion-page"', '"test-capacity-pkg-uncounted-page"')
# 제외 STEP 없이 PKG 의 Core 행만 — 「대당 Capa 가 없어」 경고가 뜨면 안 된다.
PKG_ONLY_UNCOUNTED_TEST_SCRIPT = (
    TEST_SCRIPT.replace('PAGE_NAME = "reference_data.py"', 'PAGE_NAME = "calculation_result.py"')
    .replace("ADD_UNCOUNTED_PKG_ROW = False", "ADD_UNCOUNTED_PKG_ROW = True")
    .replace("STUB_CALCULATIONS = True", "STUB_CALCULATIONS = False")
    .replace('"test-capacity-standards-page"', '"test-capacity-pkg-only-page"')
)
PKG_UNCOUNTED_NOTICE = (
    "소요기준 PKG 는 Buffer 로만 셉니다. Core·Top·Dummy 등 1건은 Buffer 에 쌓여 있어 "
    "소요대수에 넣지 않았습니다."
)

# 공정 필터를 보려면 공정이 둘이어야 하고, STEP 뷰는 대당 Capa 를 실제로 돌려야 한다.
TWO_PROCESS_TEST_SCRIPT = (
    TEST_SCRIPT.replace("ADD_SECOND_PROCESS = False", "ADD_SECOND_PROCESS = True")
    .replace("STUB_CALCULATIONS = True", "STUB_CALCULATIONS = False")
    .replace('"test-capacity-standards-page"', '"test-capacity-two-process-page"')
)


def _renamed(script: str) -> str:
    """같은 픽스처를 공정 표시명 프로필이 있는 상태로 연다."""
    return script.replace("APPLY_RENAME = False", "APPLY_RENAME = True")


RENAMED_TEST_SCRIPT = _renamed(TEST_SCRIPT)
RENAMED_TWO_PROCESS_TEST_SCRIPT = _renamed(TWO_PROCESS_TEST_SCRIPT)
RENAMED_PROCESS_TEST_SCRIPT = _renamed(PROCESS_TEST_SCRIPT)
RENAMED_EXCLUSION_TEST_SCRIPT = _renamed(EXCLUSION_TEST_SCRIPT)
RENAMED_EXCLUSION_PROCESS_TEST_SCRIPT = _renamed(EXCLUSION_PROCESS_TEST_SCRIPT)
# 대당 Capa 탭은 `산출 결과` 페이지로 옮겨졌다. 그 탭을 보는 검증은 이 스크립트를 쓴다.
TWO_PROCESS_RESULT_SCRIPT = TWO_PROCESS_TEST_SCRIPT.replace(
    'PAGE_NAME = "reference_data.py"',
    'PAGE_NAME = "calculation_result.py"',
)
RENAMED_TWO_PROCESS_RESULT_SCRIPT = _renamed(TWO_PROCESS_RESULT_SCRIPT)

STEP_VIEW = "STEP별"
STEP_VIEW_HINT = (
    "STEP별 대당 Capa는 선택한 공정만 그립니다. 사이드바 「표 조건」의 공정 필터에서 공정을 "
    "선택하세요. 전체 공정을 한 번에 보려면 공정별을 사용하세요."
)
CALC_TAB_KEY = "calculation_result_active_tab"
REQUIRED_TAB = ":material/precision_manufacturing: 소요대수"
SECUREMENT_TAB = ":material/monitoring: 확보율"


def _open_calc_tab(app: AppTest, label: str) -> AppTest:
    """산출 결과의 탭 하나를 연다. 표·조건 카드는 열린 탭 것만 그린다."""
    app.session_state[CALC_TAB_KEY] = label
    app.run()
    assert not app.exception
    return app


CAPACITY_TABLE_KEY = "captured_dimensions::unit_capacity_monthly_table"
CAPACITY_PROCESS_KEY = "captured_processes::unit_capacity_monthly_table"

# 제외 상세 표에 실리는 제외사유. services 쪽 상수가 바뀌면 화면 문구도 함께 깨진다.
LOT_RATIO_EXCLUSION_REASON = "Lot 측정률 음수"
WF_RATIO_EXCLUSION_REASON = "WF측정률 음수"
MISSING_CAPACITY_REASON = "대당 Capa 없음"


REFERENCE_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "reference_data.py"


def _page_labels(name: str) -> dict[str, str]:
    """페이지의 탭 라벨 튜플을 **아이콘 뺀 이름 → 라벨** 로. 라벨은 위젯 값이라 그대로 써야 한다."""
    for node in ast.parse(REFERENCE_PAGE.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            labels = ast.literal_eval(node.value)
            return {label.split(" ", 1)[1]: label for label in labels}
    raise AssertionError(f"{name} 가 없습니다.")


REF_TAB = _page_labels("TAB_NAMES")
EQP_TAB = _page_labels("EQUIPMENT_TAB_NAMES")
TAB_EDITORS = {
    "UPEH": "capa_upeh_editor",
    "효율": "capa_run_rate_editor",
    "여유율": "capa_vital_editor",
    "Lot측정률": "capa_lot_ratio_editor",
    "WF측정률": "capa_wf_ratio_editor",
    "일수": "capa_run_day_editor",
}


def editor_widget_key_in(app: AppTest, key: str) -> str:
    """앱이 지금 편집표를 그리는 위젯 키(`editor_state.editor_widget_key` 와 같은 규칙).

    필터가 바뀌거나 편집을 버리면 편집표가 새 세대 키로 선다. 브라우저는 그 키로 편집을
    보내므로 테스트도 같은 키에 넣는다.
    """
    generation_key = f"{key}__generation"
    generation = app.session_state[generation_key] if generation_key in app.session_state else 0
    return key if not generation else f"{key}__g{generation}"


def _open_paste(app: AppTest, editor_key: str) -> AppTest:
    """작업 줄의 「Excel 붙여넣기」 로 그 표의 붙여넣기 팝업을 연다."""
    app.button(key=f"{editor_key}_open_paste").click().run()
    assert not app.exception
    return app


def _open_step_dialog(app: AppTest) -> AppTest:
    app.session_state["reference_data_active_tab"] = REF_TAB["STEP 구성"]
    app.run()
    app.button(key="open_capacity_step_dialog").click().run()
    assert not app.exception
    return app


def _download(app: AppTest, key: str) -> dict[str, str]:
    """`render_csv_download` 가 실제로 그린 버튼 하나를 키로 찾는다."""
    labels = {button.key: button.label for button in app.download_button}
    assert key in labels, f"CSV 다운로드 버튼이 없습니다: {sorted(labels)}"
    captured = app.session_state["captured_downloads"][key]
    return {"label": labels[key], "file_name": captured["file_name"]}


def _download_bytes(app: AppTest, key: str) -> bytes:
    """`render_csv_download` 가 실제로 내보낸 바이트. 파일은 언제나 원본 공정명이다."""
    captured = app.session_state["captured_downloads"]
    assert key in captured, f"CSV 다운로드 버튼이 없습니다: {sorted(captured)}"
    return bytes(captured[key]["data"])


def _download_frame(app: AppTest, key: str) -> pd.DataFrame:
    return pd.read_csv(BytesIO(_download_bytes(app, key)), encoding="utf-8-sig", dtype="object")


def _frame_with_column(app: AppTest, column: str) -> pd.DataFrame:
    for frame in app.dataframe:
        if column in getattr(frame.value, "columns", []):
            return frame.value
    raise AssertionError(f"`{column}` 컬럼이 있는 표가 없습니다.")


def _exclusion_frame(app: AppTest, reason: str) -> pd.DataFrame:
    """제외사유 컬럼에 해당 문자열이 든 상세 표를 찾는다."""
    for frame in app.dataframe:
        value = frame.value
        if "제외사유" in getattr(value, "columns", []) and reason in set(value["제외사유"]):
            return value
    raise AssertionError(f"제외 상세 표가 없습니다: {reason}")


def test_calculation_result_shows_the_excluded_capacity_rows_with_a_csv_download() -> None:
    app = AppTest.from_string(EXCLUSION_PROCESS_TEST_SCRIPT, default_timeout=60).run()

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
    assert excluded["Lot 측정률"].tolist() == [1.0, -0.5]
    assert excluded["WF측정률"].tolist() == [-0.5, 1.0]
    assert _download(app, "download_unit_capacity_exclusions_csv") == {
        "label": "CSV 다운로드",
        "file_name": "Capa_Unit_Capacity_Exclusions_202608_202608.csv",
    }


def test_calculation_result_shows_both_exclusion_expanders_with_csv_downloads() -> None:
    app = AppTest.from_string(EXCLUSION_PROCESS_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert "대당 Capa 산출에서 2개 기준을 제외했습니다." in {
        warning.value for warning in app.warning
    }
    assert "제외 기준정보 확인" in {expander.label for expander in app.expander}
    capacity_exclusions = _exclusion_frame(app, LOT_RATIO_EXCLUSION_REASON)
    assert capacity_exclusions["STEP_SEQ"].tolist() == ["P300", "P200"]
    assert _download(app, "download_unit_capacity_exclusions_csv") == {
        "label": "CSV 다운로드",
        "file_name": "Capa_Unit_Capacity_Exclusions_202608_202608.csv",
    }

    # 소요대수 탭의 제외 알림은 그 탭을 열어야 그린다.
    app = _open_calc_tab(app, REQUIRED_TAB)
    assert "대당 Capa가 없어 소요대수 산출에서 4건을 제외했습니다 (부하량 발생 3건)." in {
        warning.value for warning in app.warning
    }
    assert "소요대수 제외 기준정보" in {expander.label for expander in app.expander}
    required_exclusions = _exclusion_frame(app, MISSING_CAPACITY_REASON)
    assert required_exclusions["STEP_SEQ"].tolist() == ["P200", "P300", "P400", "P500"]
    # 제외된 STEP 은 대당 Capa 가 없을 뿐 부하량은 붙는다. 그 값이 화면에 남아야
    # 사용자가 얼마나 잘리는지 안다. 계획에 없는 제품만 0 이라 경고의 괄호 안 건수와 갈린다.
    assert required_exclusions["부하량"].tolist() == [100.0, 100.0, 100.0, 0.0]
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
        app.session_state["reference_data_active_tab"] = REF_TAB[tab_name]
        app.run()
        assert not app.exception
        # 붙여넣기 칸은 본문이 아니라 작업 줄의 팝업이다.
        assert input_label not in {text_area.label for text_area in app.text_area}
        app = _open_paste(app, TAB_EDITORS[tab_name])

        assert input_label in {text_area.label for text_area in app.text_area}
        if tab_name in route_editor_tabs:
            assert any(
                list(frame.value.columns)[-3:-1] == ["STEP_SEQ", "MCP_SEQ"]
                for frame in app.dataframe
            )


def test_load_input_tabs_expose_plan_and_yield_clipboard_round_trip() -> None:
    """붙여넣기는 표 위 작업 줄의 「Excel 붙여넣기」 팝업이다. 팝업은 한 번에 하나다."""
    app = AppTest.from_string(LOAD_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    # 닫혀 있는 동안에는 붙여넣기 칸이 본문을 차지하지 않는다.
    assert not app.text_area
    app.button(key="open_plan_paste").click().run()
    assert not app.exception
    assert {text_area.label for text_area in app.text_area} == {"RQ_PKG_PLAN 표 붙여넣기"}
    app.button(key="open_yield_paste").click().run()
    assert not app.exception
    assert {text_area.label for text_area in app.text_area} == {"RQ_YLD 표 붙여넣기"}


def test_equipment_tab_gives_each_rq_its_own_editor_and_clipboard() -> None:
    """설비대수 세 RQ 는 각각 편집기와 붙여넣기 양식을 갖는다.

    셋을 한 화면에 세로로 쌓지 않고 탭을 한 겹 더 두었으므로, 열린 안쪽 탭의 것만
    그려진다. 붙여넣기만 되던 화면이 아니라는 것을 편집기 존재로 고정한다.
    """
    for sub_tab, table_name, editor_key in (
        ("보유", "RQ_EQP_OWN", "capa_eqp_own_editor"),
        ("대여", "RQ_EQP_LENT", "capa_eqp_lent_editor"),
        ("가용", "RQ_EQP_AVBL", "capa_eqp_avbl_editor"),
    ):
        app = AppTest.from_string(TEST_SCRIPT, default_timeout=60)
        app.session_state["reference_data_active_tab"] = REF_TAB["설비대수"]
        app.session_state["equipment_count_active_tab"] = EQP_TAB[sub_tab]
        app.run()

        assert not app.exception
        assert f"{editor_key}_apply" in {button.key for button in app.button}
        app = _open_paste(app, editor_key)
        assert f"{table_name} 표 붙여넣기" in {text_area.label for text_area in app.text_area}


def test_equipment_editor_saves_the_edited_month_to_the_scenario() -> None:
    """시트에 직접 쓴 값이 활성 시나리오까지 간다.

    필터로 좁힌 화면에서 고쳐도 걸러진 공정이 조회기간에서 지워지지 않아야 한다 —
    `replace_month_range` 가 구간을 통째로 갈아끼우기 때문이다.
    """
    app = AppTest.from_string(TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["설비대수"]
    app.session_state["equipment_count_active_tab"] = EQP_TAB["보유"]
    app.session_state["capa_eqp_own_editor_filter_공정"] = ["Process-B"]
    app.run()
    assert not app.exception

    app = _edit_and_apply(app, "capa_eqp_own_editor", "202608", 7.0)

    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_EQP_OWN"]
    assert dict(zip(saved["공정"], saved["설비보유"], strict=True))["Process-B"] == 7.0
    assert set(saved["공정"]) == {"Process-A", "Process-B"}


def test_required_equipment_detail_exposes_route_filters() -> None:
    app = _open_calc_tab(AppTest.from_string(PROCESS_TEST_SCRIPT, default_timeout=60), REQUIRED_TAB)

    # 「상세」와 필터는 사이드바 `표 조건` 카드다.
    required_detail = next(toggle for toggle in app.sidebar.toggle if toggle.label == "상세")
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
    app = _open_step_dialog(AppTest.from_string(TEST_SCRIPT, default_timeout=60).run())

    new_mcp = next(widget for widget in app.text_input if widget.label == "신규 MCP_SEQ")
    app = new_mcp.set_value("2A").run()
    new_step = next(widget for widget in app.text_input if widget.label == "신규 STEP_SEQ")
    app = new_step.set_value("P200").run()
    add_button = next(button for button in app.button if button.label == "STEP 일괄 추가")
    app = add_button.click().run()

    assert not app.exception
    assert app.session_state["test_step_reqb_rows"] == 2


def test_step_changes_open_in_a_popup_from_the_action_row() -> None:
    """STEP 추가·삭제는 가끔 하는 쓰기라 본문이 아니라 표 위 작업 줄의 팝업이다."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["STEP 구성"]
    app.run()

    assert not app.exception
    assert "capacity_step_route" not in {widget.key for widget in app.selectbox}
    app.button(key="open_capacity_step_dialog").click().run()
    assert not app.exception
    assert app.selectbox(key="capacity_step_route").options


def test_step_unit_capacity_stays_empty_until_a_process_is_selected() -> None:
    """전 공정 STEP 을 그리면 Plotly 데이터가 폭증한다. 미선택이면 표를 만들지도 않는다."""
    app = AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60)
    app.session_state["unit_capacity_view_mode"] = STEP_VIEW
    app.run()

    assert not app.exception
    assert STEP_VIEW_HINT in {info.value for info in app.info}
    assert "download_unit_capacity_csv" not in {button.key for button in app.download_button}
    assert CAPACITY_TABLE_KEY not in app.session_state


def test_step_unit_capacity_draws_only_the_selected_process() -> None:
    app = AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60)
    app.session_state["unit_capacity_view_mode"] = STEP_VIEW
    app.session_state["unit_capacity_process_filter"] = ["Process-A"]
    app.run()

    assert not app.exception
    assert STEP_VIEW_HINT not in {info.value for info in app.info}
    assert app.session_state[CAPACITY_PROCESS_KEY] == ["Process-A"]
    assert "download_unit_capacity_csv" in {button.key for button in app.download_button}


def test_effective_process_capacity_still_shows_every_process_without_a_filter() -> None:
    """집계된 값이라 가볍다. 전체 조망이 이 뷰의 용도이므로 미선택 동작을 바꾸지 않는다."""
    app = AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert app.session_state[CAPACITY_PROCESS_KEY] == ["Process-A", "Process-B"]
    assert STEP_VIEW_HINT not in {info.value for info in app.info}
    assert "download_unit_capacity_csv" in {button.key for button in app.download_button}


def test_the_view_mode_sits_in_the_body_and_the_filters_in_the_card() -> None:
    """`표시 방식`(공정별·STEP별)은 탭 안의 하위 보기라 본문 표 위다(2026-09-29 사용자 결정).

    카드에 넣으면 지금 어느 표를 보는지 본문에서 사라진다. 집계 수준·공정 필터는 거르는 조건이라
    `표 조건` 카드에 남는다.
    """
    app = AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert "unit_capacity_view_mode" in {widget.key for widget in app.main.segmented_control}
    assert not app.sidebar.segmented_control
    assert "unit_capacity_process_filter" in {widget.key for widget in app.sidebar.multiselect}
    assert "unit_capacity_detail_level" in {widget.key for widget in app.sidebar.selectbox}


def test_the_process_filter_placeholder_follows_the_view() -> None:
    """`미선택 시 전체 공정` 은 STEP 뷰에서 거짓말이 된다."""
    app = AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60).run()
    assert not app.exception
    assert app.multiselect(key="unit_capacity_process_filter").proto.placeholder == (
        "미선택 시 전체 공정"
    )

    app.session_state["unit_capacity_view_mode"] = STEP_VIEW
    app.run()

    assert not app.exception
    assert app.multiselect(key="unit_capacity_process_filter").proto.placeholder == (
        "공정을 선택하세요"
    )


def _edit_and_apply(
    app: AppTest, editor_key: str, month_column: str, value: float | None
) -> AppTest:
    """셀 하나를 고치고 곧바로 「변경사항 적용」 을 누른다.

    편집 델타는 **보이는 표 안의 행 위치**로 기록되므로 필터를 건 다음에 넣어야 한다.
    AppTest 는 세션에 직접 넣은 data_editor 값을 다음 run 한 번만 들고 있어, 편집과 클릭을
    같은 run 에 태운다. 적용 버튼은 고친 것이 있는 회차에만 열리므로(고친 것이 없으면 잠긴다)
    먼저 편집을 넣고 한 번 돌려 버튼을 연 뒤, 같은 편집을 다시 넣고 누른다 — 브라우저에서
    칸을 고치면 한 번 다시 돌고 그다음에 누르는 것과 같다.
    """
    key = editor_widget_key_in(app, editor_key)
    edit = {"edited_rows": {0: {month_column: value}}, "added_rows": [], "deleted_rows": []}
    app.session_state[key] = edit
    app.run()
    app.session_state[key] = edit
    apply_button = next(button for button in app.button if button.key == f"{editor_key}_apply")
    apply_button.click()
    return app.run()


def _filtered_editor_app(tab_name: str, editor_key: str, filter_column: str) -> AppTest:
    """편집기 탭 하나를 열고 공정 필터로 Process-B 만 남긴 화면."""
    app = AppTest.from_string(TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB[tab_name]
    app.session_state[f"{editor_key}_filter_{filter_column}"] = ["Process-B"]
    app.run()
    assert not app.exception
    return app


def test_filtered_run_day_editor_keeps_the_process_the_filter_hid() -> None:
    """`replace_month_range` 는 조회기간을 통째로 갈아끼운다. 걸러진 공정이 빠지면 삭제된다."""
    app = _filtered_editor_app("일수", "capa_run_day_editor", "공정")
    app = _edit_and_apply(app, "capa_run_day_editor", "202608", 15.0)

    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_RUN_DAY"]
    assert dict(zip(saved["공정"], saved["RUN_DAY"], strict=True)) == {
        "Process-A": 31.0,
        "Process-B": 15.0,
    }


def _walk(node: object) -> list[object]:
    """화면 요소를 그려진 차례대로 편다."""
    found: list[object] = []
    for child in getattr(node, "children", {}).values():
        found.append(child)
        found.extend(_walk(child))
    return found


def test_an_apply_error_shows_right_under_the_button_above_the_sheet() -> None:
    """표 위 「변경사항 적용」 이 막힌 까닭은 그 버튼 바로 아래 뜬다 — 500px 표 아래가 아니다.

    버튼만 표 위로 올리고 오류 자리를 그대로 두면 누른 자리에서 아무 일도 없어 보여 적용된
    줄 안다(2026-09-28 리뷰에서 재현).
    """
    app = _filtered_editor_app("일수", "capa_run_day_editor", "공정")
    app.session_state["test_fail_month_updates"] = True
    app = _edit_and_apply(app, "capa_run_day_editor", "202608", 15.0)

    elements = _walk(app.main)
    error = next(
        index
        for index, node in enumerate(elements)
        if getattr(node, "type", None) == "error" and "PROBE_APPLY_ERROR" in str(node.value)
    )
    sheet = next(
        index
        for index, node in enumerate(elements)
        if getattr(node, "key", None) == editor_widget_key_in(app, "capa_run_day_editor")
    )
    assert error < sheet


def test_filtered_upeh_editor_keeps_the_process_the_filter_hid() -> None:
    """UPEH 탭은 분류 컬럼이 아홉 개다. 되머지 키가 탭마다 다르다는 것을 함께 고정한다."""
    app = _filtered_editor_app("UPEH", "capa_upeh_editor", "공정")
    app = _edit_and_apply(app, "capa_upeh_editor", "202608", 55.0)

    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_UPEH"]
    assert dict(zip(saved["공정"], saved["UPEH"], strict=True)) == {
        "Process-A": 100.0,
        "Process-B": 55.0,
    }


def test_run_rate_and_vital_tabs_do_not_share_their_process_filter() -> None:
    """두 탭은 `dimensions` 가 `공정`·`양산구분` 으로 완전히 같다.

    필터 상태를 갈라 놓는 것은 `editor_key` 로 만든 위젯 key 뿐이다. 한쪽 선택이 다른 쪽에
    새면 사용자가 보지도 않은 필터로 편집표가 좁아진다.
    """
    app = _filtered_editor_app("효율", "capa_run_rate_editor", "공정")

    # 열린 탭의 필터만 그려진다. 두 key 가 같으면 여기서 여유율 쪽도 함께 잡힌다.
    assert app.multiselect(key="capa_run_rate_editor_filter_공정").value == ["Process-B"]
    assert "capa_vital_editor_filter_공정" not in {widget.key for widget in app.multiselect}

    # 여유율 탭을 열면서 효율 쪽 선택을 그대로 남겨 둔다. key 가 겹치면 여유율 필터가
    # 그 선택을 그대로 집어 편집표가 Process-B 한 줄로 좁아진다.
    app = AppTest.from_string(TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["여유율"]
    app.session_state["capa_run_rate_editor_filter_공정"] = ["Process-B"]
    app.run()
    assert not app.exception
    assert app.multiselect(key="capa_vital_editor_filter_공정").value == []

    # 필터가 새지 않았으니 여유율 편집표의 첫 행은 걸러지지 않은 Process-A 다.
    app = _edit_and_apply(app, "capa_vital_editor", "202608", 0.5)

    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_VITAL"]
    assert dict(zip(saved["공정"], saved["편중률"], strict=True)) == {
        "Process-A": 0.5,
        "Process-B": 1.0,
    }


def test_unit_capacity_controls_keep_their_choice_across_tabs() -> None:
    """조건 카드는 열린 탭 것만 선다. 닫힌 동안 위젯은 없어도 선택은 `persist_state` 로 남는다."""
    app = AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60)
    app.session_state["unit_capacity_process_filter"] = ["Process-B"]
    app.run()
    assert not app.exception
    assert app.session_state[CAPACITY_PROCESS_KEY] == ["Process-B"]
    assert "unit_capacity_process_filter" in {widget.key for widget in app.sidebar.multiselect}

    app = _open_calc_tab(app, SECUREMENT_TAB)
    # 확보율 탭의 카드에는 대당 Capa 조건이 없다. 계산 결과를 쓰는 표·CSV 도 건너뛴다.
    assert "unit_capacity_process_filter" not in {widget.key for widget in app.multiselect}
    assert "download_unit_capacity_csv" not in {button.key for button in app.download_button}

    app = _open_calc_tab(app, ":material/insights: 대당 Capa")
    assert app.multiselect(key="unit_capacity_process_filter").value == ["Process-B"]
    assert app.selectbox(key="unit_capacity_detail_level").value == "공정"


def test_unfiltered_editor_apply_saves_the_same_rows_as_before() -> None:
    """필터를 만지지 않은 적용은 예전과 같아야 한다."""
    app = AppTest.from_string(TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["일수"]
    app.run()
    assert not app.exception
    app = _edit_and_apply(app, "capa_run_day_editor", "202608", 20.0)

    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_RUN_DAY"]
    assert dict(zip(saved["공정"], saved["RUN_DAY"], strict=True)) == {
        "Process-A": 20.0,
        "Process-B": 31.0,
    }


# ------------------------------------------------- 화면은 표시명, 파일은 원본


def test_capacity_exclusion_table_shows_the_display_name_while_its_csv_keeps_the_original() -> None:
    """제외 안내 목록은 화면 프레임과 CSV 프레임이 갈라져 있다."""
    app = AppTest.from_string(RENAMED_EXCLUSION_PROCESS_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    excluded = _exclusion_frame(app, LOT_RATIO_EXCLUSION_REASON)
    assert set(excluded["공정"]) == {"가공"}

    exported = _download_frame(app, "download_unit_capacity_exclusions_csv")
    assert set(exported["공정"]) == {"Process-A"}


def test_calculation_result_exclusion_csvs_keep_the_original_process_name() -> None:
    """두 제외 목록 모두 화면은 표시명, 내려받는 파일은 원본이다."""
    app = AppTest.from_string(RENAMED_EXCLUSION_PROCESS_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert set(_exclusion_frame(app, LOT_RATIO_EXCLUSION_REASON)["공정"]) == {"가공"}
    required_app = _open_calc_tab(
        AppTest.from_string(RENAMED_EXCLUSION_PROCESS_TEST_SCRIPT, default_timeout=60),
        REQUIRED_TAB,
    )
    assert set(_exclusion_frame(required_app, MISSING_CAPACITY_REASON)["공정"]) == {"가공"}

    assert set(_download_frame(app, "download_unit_capacity_exclusions_csv")["공정"]) == {
        "Process-A"
    }
    app = _open_calc_tab(app, REQUIRED_TAB)
    assert set(_download_frame(app, "download_required_exclusions_csv")["공정"]) == {"Process-A"}


def test_exclusion_tables_stay_original_without_a_rename_profile() -> None:
    """매핑이 비어 있으면 화면에도 원본 공정명이 그대로 보인다."""
    app = AppTest.from_string(EXCLUSION_PROCESS_TEST_SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert set(_exclusion_frame(app, LOT_RATIO_EXCLUSION_REASON)["공정"]) == {"Process-A"}


def test_step_summary_and_route_selector_show_the_display_name() -> None:
    """STEP 구성 요약 표와 복제·삭제 대상 선택 라벨도 화면이라 표시명을 쓴다."""
    app = AppTest.from_string(RENAMED_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["STEP 구성"]
    app.run()

    assert not app.exception
    summary = _frame_with_column(app, "STEP 수")
    assert set(summary["공정"]) == {"가공"}
    app.button(key="open_capacity_step_dialog").click().run()
    assert not app.exception
    assert all(
        option.startswith("가공 · ") for option in app.selectbox(key="capacity_step_route").options
    )


def test_step_route_selection_still_edits_the_original_process() -> None:
    """선택 라벨이 표시명이어도 STEP 복제는 원본 경로에 그대로 적용된다."""
    app = _open_step_dialog(AppTest.from_string(RENAMED_TEST_SCRIPT, default_timeout=60).run())

    new_mcp = next(widget for widget in app.text_input if widget.label == "신규 MCP_SEQ")
    app = new_mcp.set_value("2A").run()
    new_step = next(widget for widget in app.text_input if widget.label == "신규 STEP_SEQ")
    app = new_step.set_value("P200").run()
    add_button = next(button for button in app.button if button.label == "STEP 일괄 추가")
    app = add_button.click().run()

    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_REQB"]
    assert set(saved["공정"]) == {"Process-A"}


def _equipment_sub_tab_app(sub_tab: str, script: str = RENAMED_TEST_SCRIPT) -> AppTest:
    """설비대수 탭의 안쪽 탭 하나를 연 화면."""
    app = AppTest.from_string(script, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["설비대수"]
    app.session_state["equipment_count_active_tab"] = EQP_TAB[sub_tab]
    app.run()
    assert not app.exception
    return app


def test_equipment_count_table_shows_the_display_name_while_its_paste_form_stays_original() -> None:
    """설비대수 조회 표는 표시명이고, 편집 탭의 왕복 양식은 원본 공정명이다."""
    app = _equipment_sub_tab_app("현황")

    assert set(_frame_with_column(app, "공정")["공정"]) == {"가공"}
    assert app.multiselect(key="equipment_count_filter_공정").options == ["가공"]
    for sub_tab, editor_key in (
        ("보유", "capa_eqp_own_editor"),
        ("대여", "capa_eqp_lent_editor"),
        ("가용", "capa_eqp_avbl_editor"),
    ):
        editor_app = _open_paste(_equipment_sub_tab_app(sub_tab), editor_key)
        exported = _download_frame(editor_app, f"{editor_key}_csv_download")
        assert exported["공정"].tolist() == ["Process-A"], sub_tab


def test_equipment_count_filter_keeps_the_original_selection_value() -> None:
    """필터 표기만 표시명이다. 선택값이 표시명이면 `isin` 이 원본과 맞지 않아 표가 빈다."""
    app = _equipment_sub_tab_app("현황")
    app.multiselect(key="equipment_count_filter_공정").select("가공")
    app.run()

    assert not app.exception
    assert app.session_state["equipment_count_filter_공정"] == ["Process-A"]
    assert set(_frame_with_column(app, "공정")["공정"]) == {"가공"}


def test_month_editor_shows_the_label_but_returns_the_original_process() -> None:
    """편집기 분류 컬럼의 값은 원본이다. 되머지 키와 저장값이 여기 걸린다."""
    app = AppTest.from_string(RENAMED_TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["일수"]
    app.run()
    assert not app.exception

    editor = next(frame for frame in app.dataframe if "RUN_DAY" not in frame.value.columns)
    assert editor.value["공정"].tolist() == ["Process-A", "Process-B"]

    app = _edit_and_apply(app, "capa_run_day_editor", "202608", 20.0)

    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_RUN_DAY"]
    assert dict(zip(saved["공정"], saved["RUN_DAY"], strict=True)) == {
        "Process-A": 20.0,
        "Process-B": 31.0,
    }


def test_month_editor_paste_template_keeps_the_original_process_name() -> None:
    """붙여넣기 팝업의 왕복 양식은 표시명이 닿으면 안 되는 첫 번째 자리다."""
    app = AppTest.from_string(RENAMED_TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["일수"]
    app.run()

    assert not app.exception
    app = _open_paste(app, "capa_run_day_editor")
    exported = _download_frame(app, "capa_run_day_editor_csv_download")
    assert exported["공정"].tolist() == ["Process-A", "Process-B"]


def test_uncounted_pkg_rows_are_a_notice_not_a_capacity_warning() -> None:
    """PKG 의 Buffer 가 아닌 행은 고칠 것이 없다. 대당 Capa 경고 건수에 섞이면 안 된다."""
    app = _open_calc_tab(
        AppTest.from_string(PKG_UNCOUNTED_TEST_SCRIPT, default_timeout=60), REQUIRED_TAB
    )
    assert "대당 Capa가 없어 소요대수 산출에서 4건을 제외했습니다 (부하량 발생 3건)." in {
        warning.value for warning in app.warning
    }
    assert PKG_UNCOUNTED_NOTICE in {info.value for info in app.info}
    excluded = _exclusion_frame(app, "PKG 기준은 Buffer 로만 계수")
    uncounted = excluded.loc[excluded["제외사유"].eq("PKG 기준은 Buffer 로만 계수")]
    assert uncounted["STEP_SEQ"].tolist() == ["P600"]
    assert uncounted["부하량"].tolist() == [0.0]


def test_only_uncounted_pkg_rows_raise_no_capacity_warning() -> None:
    app = _open_calc_tab(
        AppTest.from_string(PKG_ONLY_UNCOUNTED_TEST_SCRIPT, default_timeout=60), REQUIRED_TAB
    )
    assert not any("대당 Capa가 없어" in warning.value for warning in app.warning)
    assert PKG_UNCOUNTED_NOTICE in {info.value for info in app.info}


# ------------------------------------------ 조건 카드 · 미적용 점 · Guide (2026-09-29)


def test_the_edited_tab_gets_a_pending_dot(monkeypatch: pytest.MonkeyPatch) -> None:
    """적용하지 않은 편집이 남은 탭 이름 옆에 점이 찍힌다. 편집이 없으면 아무 탭에도 없다."""
    import capa_simulation.components.tab_marks as tab_marks

    marked: dict[str, set[str]] = {}
    monkeypatch.setattr(
        tab_marks,
        "mark_pending_tabs",
        lambda key, labels, pending: marked.__setitem__(key, set(pending)),
    )
    app = AppTest.from_string(TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["일수"]
    app.run()
    assert not app.exception
    assert marked["reference_data_active_tab"] == set()

    app.session_state[editor_widget_key_in(app, "capa_run_day_editor")] = {
        "edited_rows": {0: {"202608": 20.0}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.run()
    assert not app.exception
    assert marked["reference_data_active_tab"] == {REF_TAB["일수"]}


def test_the_table_filters_and_the_overview_detail_live_in_the_sidebar_card() -> None:
    app = _filtered_editor_app("일수", "capa_run_day_editor", "공정")
    assert "capa_run_day_editor_filter_공정" in {widget.key for widget in app.sidebar.multiselect}
    assert not app.main.multiselect

    app = _equipment_sub_tab_app("현황")
    assert "equipment_count_detail" in {widget.key for widget in app.sidebar.toggle}
    assert "equipment_count_filter_공정" in {widget.key for widget in app.sidebar.multiselect}
    assert not app.main.toggle


def test_the_guide_carries_what_left_the_body() -> None:
    from capa_simulation.components.page_guide import load_guide

    guide = load_guide("reference_data")
    for text in (
        "3600 ÷ ST",
        "STEP 수는 같은 공정·제품 경로 안의",
        "필터는 화면만 좁힙니다",
        "편집 취소",
        "Excel 붙여넣기",
        "STEP 추가·삭제",
        "신규 리비전 저장",
        "주황 점",
    ):
        assert text in guide, text


def test_calculation_result_guide_carries_what_left_the_body() -> None:
    from capa_simulation.components.page_guide import load_guide

    guide = load_guide("calculation_result")
    for text in (
        "B/N(Bottleneck·병목) 공정",
        "중복되지 않은 원수요 부하량을 STEP별 소요대수 합계로 나눈 값",
        "`부하량 ÷ 대당 Capa`",
        "`가용대수 ÷ 소요대수`",
        "경로 수",
        "히트맵 주요 공정",
        "칸 안 숫자와 hover 는 자르지 않은 확보율",
    ):
        assert text in guide, text


def test_applying_one_table_keeps_another_tabs_unapplied_edits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """한 표를 적용해도 다른 탭에서 고치고 아직 적용하지 않은 편집은 버리지 않는다.

    적용은 활성 리비전을 올려 원본 토큰을 바꾼다. 전에는 그 토큰 변화가 **모든** 편집표를 비워
    UPEH 에서 고친 값이 일수를 적용하는 순간 조용히 사라졌다(2026-09-29 리뷰에서 재현). 이제
    적용한 표만 새 세대로 세운다.
    """

    def generation(app: AppTest, key: str) -> int:
        slot = f"{key}__generation"
        return int(app.session_state[slot]) if slot in app.session_state else 0

    app = AppTest.from_string(TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["일수"]
    app.run()
    assert not app.exception
    before = {key: generation(app, key) for key in ("capa_run_day_editor", "capa_upeh_editor")}
    app = _edit_and_apply(app, "capa_run_day_editor", "202608", 20.0)
    app.run()

    assert not app.exception
    # 적용한 표는 새 세대로 섰고, 다른 탭의 편집표는 그대로다.
    assert generation(app, "capa_run_day_editor") > before["capa_run_day_editor"]
    assert generation(app, "capa_upeh_editor") == before["capa_upeh_editor"]
    assert "reference_data_own_change" not in app.session_state


def test_the_step_popup_warns_before_it_drops_unapplied_upeh_edits() -> None:
    """STEP 을 더하거나 빼면 UPEH·측정률 표의 행이 바뀌어 그 표의 편집이 버려진다. 먼저 말한다."""
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60).run()
    app.session_state["reference_data_active_tab"] = REF_TAB["STEP 구성"]
    app.run()
    app.session_state[editor_widget_key_in(app, "capa_upeh_editor")] = {
        "edited_rows": {0: {"202608": 1.0}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.button(key="open_capacity_step_dialog").click().run()

    assert not app.exception
    assert any("UPEH 표에 적용하지 않은 편집" in item.value for item in app.warning)


# ---------------------------- 빈칸·적용 기준 횡전개 (2026-09-29 설비대수 빈칸 버그 보고)


def _real_apply(script: str, old_token: str, new_token: str) -> str:
    """적용이 활성 시나리오에 **실제로** 쓰이는 스크립트.

    기본 하네스는 적용을 가로채 첫 교체만 적어 둔다. 적용 뒤의 적용(STEP 추가 → UPEH 적용)을
    보려면 원래 `apply_month_updates` 가 세션의 시나리오를 갈아끼우고 다음 회차가 그것을 읽어야
    한다. 적용은 세션 상태만 바꾸므로 DB 는 열리지 않는다. 계산 캐시 키가 되는 토큰은 따로 둔다.
    """
    return (
        script.replace(
            "scenario_state.ensure_active_scenario = lambda _tables, _version: active",
            "scenario_state.ensure_active_scenario = lambda _tables, _version: (\n"
            "    st.session_state.get(scenario_state.ACTIVE_SCENARIO_KEY) or active\n"
            ")",
        )
        .replace("scenario_state.apply_month_updates = capture_month_updates", "pass")
        .replace(f'"{old_token}"', f'"{new_token}"')
    )


REAL_APPLY_TEST_SCRIPT = _real_apply(
    TEST_SCRIPT, "test-capacity-standards-page", "test-capacity-real-apply-page"
)
# UPEH 에 없는 달(202609)이 다른 표에만 있다 — UPEH 202609 열을 통째로 비워 저장한 리비전과 같은
# 모양이다. 선택기간은 08–09 라 적용 기간(선택기간 ∩ UPEH 범위)은 08 뿐이다.
_WINDOW_EXTRA = """
for _name, _row in (
    ("RQ_RUN_DAY", {"생산계획년월": 202609, "공정": "Process-A", "RUN_DAY": 30.0}),
    (
        "RQ_RUN_RATE",
        {"생산계획년월": 202609, "공정": "Process-A", "양산구분": "양산", "CAPA_RUN_RATE": 0.9},
    ),
    ("RQ_REQB", {**tables["RQ_REQB"].iloc[0].to_dict(), "생산계획년월": 202609}),
):
    tables[_name] = pd.concat([tables[_name], pd.DataFrame([_row])], ignore_index=True)
"""
WINDOW_TEST_SCRIPT = (
    TEST_SCRIPT.replace("\nactive = {", _WINDOW_EXTRA + "\nactive = {", 1)
    .replace(
        'st.session_state["production_month_range_v2"] = ("2026-08", "2026-08")',
        'st.session_state["production_month_range_v2"] = ("2026-08", "2026-09")',
    )
    .replace('"test-capacity-standards-page"', '"test-capacity-window-page"')
)


def _scenario_table(app: AppTest, name: str) -> pd.DataFrame:
    frame: pd.DataFrame = app.session_state["active_scenario"]["tables"][name]
    return frame


def _add_step(app: AppTest, mcp_seq: str, step_seq: str) -> AppTest:
    app = _open_step_dialog(app)
    app = next(w for w in app.text_input if w.label == "신규 MCP_SEQ").set_value(mcp_seq).run()
    app = next(w for w in app.text_input if w.label == "신규 STEP_SEQ").set_value(step_seq).run()
    app = next(b for b in app.button if b.label == "STEP 일괄 추가").click().run()
    assert not app.exception
    return app


def _paste(app: AppTest, editor_key: str, text: str) -> AppTest:
    app = _open_paste(app, editor_key)
    app.text_area(key=f"{editor_key}_csv_clipboard").set_value(text)
    app = next(b for b in app.button if b.label == "붙여넣기 일괄 적용").click().run()
    assert not app.exception
    return app


def test_upeh_apply_after_a_step_add_checks_against_the_active_scenario() -> None:
    """UPEH 적용 검사는 **적용 전 활성 시나리오**와 맞댄다(결함 1).

    저장 리비전과 맞대면 이 세션에서 먼저 한 STEP 추가가 안 보인다. 새 STEP 의 UPEH 행을 모두
    「새로 만든 경로」로 보고 그 측정률 행(복제로 시나리오에는 있다)을 저장 리비전에서 찾다 못해,
    STEP 을 더한 뒤에는 상관없는 UPEH 칸 하나도 적용할 수 없었다(2026-09-29).
    """
    app = AppTest.from_string(REAL_APPLY_TEST_SCRIPT, default_timeout=60).run()
    assert not app.exception
    app = _add_step(app, "2A", "P200")
    assert sorted(_scenario_table(app, "RQ_UPEH")["STEP_SEQ"]) == ["P100", "P200"]
    assert sorted(_scenario_table(app, "RQ_LOT_RATIO")["STEP_SEQ"]) == ["P100", "P200"]

    app.session_state["reference_data_active_tab"] = REF_TAB["UPEH"]
    app.run()
    app = _edit_and_apply(app, "capa_upeh_editor", "202608", 120.0)

    assert not app.exception
    assert [error.value for error in app.error] == []
    assert 120.0 in _scenario_table(app, "RQ_UPEH")["UPEH"].tolist()


def test_reference_editors_use_the_same_window_as_the_apply() -> None:
    """편집표·STEP 목록은 적용과 같은 기간(선택기간 ∩ UPEH 범위)이다(결함 3).

    편집표를 선택기간으로 자르면 UPEH 에 없는 달의 행이 편집값에 섞여, 적용이 그 기간만
    갈아끼우는 `replace_month_range` 에서 「편집값에 선택 범위 밖의 년월이 있습니다」로 모든 적용이
    막혔다. STEP 추가도 UPEH 가 없는 달의 수요를 복제하려다 멈췄다.
    """
    app = AppTest.from_string(WINDOW_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["일수"]
    app.run()
    assert not app.exception
    app = _edit_and_apply(app, "capa_run_day_editor", "202608", 20.0)

    assert not app.exception
    saved = app.session_state["test_month_updates"]["RQ_RUN_DAY"]
    assert set(saved["생산계획년월"]) == {202608}
    assert saved["RUN_DAY"].tolist() == [20.0]

    app = _add_step(AppTest.from_string(WINDOW_TEST_SCRIPT, default_timeout=60).run(), "2A", "P200")
    assert [error.value for error in app.error] == []
    # 202608 의 원본 한 행과 그 복제 한 행. 202609 수요는 적용 기간 밖이라 건드리지 않는다.
    assert app.session_state["test_step_reqb_rows"] == 2


def test_clearing_a_run_rate_cell_an_upeh_path_uses_is_blocked() -> None:
    """효율·여유율·일수에는 중립값이 없다. 경로가 쓰는 칸을 비우면 적용 전에 막는다(결함 4).

    전에는 적용이 성공으로 알리고 행을 지웠고, 그 뒤 계산 전체가 「RQ_RUN_RATE 연결값이 없는
    대당 Capa 기준이 있습니다」로 멈췄다.
    """
    app = AppTest.from_string(TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["효율"]
    app.run()
    assert not app.exception
    app = _edit_and_apply(app, "capa_run_rate_editor", "202608", None)

    assert not app.exception
    errors = [str(error.value) for error in app.error]
    assert any(
        "UPEH 경로가 씁니다" in error and "202608" in error and "Process-A" in error
        for error in errors
    ), errors
    assert "test_month_updates" not in app.session_state


def test_clearing_a_run_day_cell_by_paste_is_blocked_the_same_way() -> None:
    """붙여넣기도 격자와 같은 규칙을 탄다 — 팝업 안에 막힌 까닭을 쓴다."""
    app = AppTest.from_string(TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["일수"]
    app.run()
    assert not app.exception
    app = _paste(app, "capa_run_day_editor", "공정\t202608\nProcess-A\t\nProcess-B\t31\n")

    errors = [str(error.value) for error in app.error]
    assert any("「일수」 표에서 값을 지운 칸 1개" in error for error in errors), errors
    assert "test_month_updates" not in app.session_state


RATIO_PASTE_HEADER = (
    "공정\tArea_Name\t양산구분\t제품정보\tStack\tWF 구분\tSTEP_SEQ\tMCP_SEQ\t202608\n"
)


def _ratio_paste_row(process: str, value: str) -> str:
    return f"{process}\tMain\t양산\tProduct-A\t8H\tBUFFER\tP100\t1A\t{value}\n"


def test_the_paste_notice_says_what_happened_to_the_cleared_cells() -> None:
    """붙여넣기 완료 문구는 표마다 맞는 말이다(결함 5).

    전에는 모든 표가 「값이 지워진 칸 N개는 계산에서 빠집니다」였다. 측정률은 1.0 으로 가정해
    계산하고, 설비대수는 0 대로 저장한다 — 설비는 원래 없던 조합(양식의 0)을 비운 것은 세지 않는다.
    """
    app = AppTest.from_string(TWO_PROCESS_TEST_SCRIPT, default_timeout=60)
    app.session_state["reference_data_active_tab"] = REF_TAB["Lot측정률"]
    app.run()
    app = _paste(
        app,
        "capa_lot_ratio_editor",
        RATIO_PASTE_HEADER + _ratio_paste_row("Process-A", "") + _ratio_paste_row("Process-B", "1"),
    )
    notices = [str(item.value) for item in app.success]
    assert any("값이 지워진 칸 1개는 측정률 1.0 으로 계산합니다" in item for item in notices), (
        notices
    )
    assert not any("계산에서 빠집니다" in item for item in notices)

    # 보유 2 대를 비우면 0 대로 저장한다.
    app = _equipment_sub_tab_app("보유", TWO_PROCESS_TEST_SCRIPT)
    app = _paste(app, "capa_eqp_own_editor", "공정\t202608\nProcess-A\t\nProcess-B\t2\n")
    notices = [str(item.value) for item in app.success]
    assert any("빈칸 1개는 0 대로 저장했습니다" in item for item in notices), notices

    # 대여는 두 공정 모두 0 대다. 0 인 칸을 비운 것은 바뀐 것이 없어 세지 않는다.
    app = _equipment_sub_tab_app("대여", TWO_PROCESS_TEST_SCRIPT)
    app = _paste(app, "capa_eqp_lent_editor", "공정\t202608\nProcess-A\t\nProcess-B\t\n")
    notices = [str(item.value) for item in app.success]
    assert notices and not any("빈칸" in item or "지워진 칸" in item for item in notices), notices
