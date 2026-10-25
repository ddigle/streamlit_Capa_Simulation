# Purpose: 필요 단축 일정·Space 필요 단축 보기 AppTest 가 같이 쓰는 시나리오 흉내 스크립트를 만든다.

"""시나리오 쪽(기준정보·활성 시나리오·소요대수·HOME 계획·판정 기준·Past Data·공정 표시명)을 모듈
속성으로 갈아 끼우고 페이지 하나를 돌리는 AppTest 스크립트 글(`AppTest.from_string`). 페이지와
컴포넌트가 그 함수를 **부를 때** 모듈에서 찾으므로 두 화면이 같은 흉내를 본다 — Space 「필요 단축」
보기와 필요 단축 일정의 키 같음 시험(T-P5)이 같은 수요로 돈다. 빈 설비 DB 는 오늘에 맞춘 샘플
fleet 을 보이므로 그 호기로 계산이 돈다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path


def months_from_today(count: int = 6) -> list[int]:
    today = date.today()
    year, month = today.year, today.month
    months = []
    for _ in range(count):
        months.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def shortening_script(
    database_path: Path,
    page: Path,
    *,
    fail_scenario: bool = False,
    past_months: tuple[int, ...] = (),
    sidebar_first: int | None = None,
    sidebar_last: int | None = None,
    labels: dict[str, str] | None = None,
) -> str:
    simulation_path = database_path.with_name(f"{database_path.stem}_simulation.duckdb")
    months = months_from_today()
    first, last = sidebar_first or months[0], sidebar_last or months[-1]
    return f"""
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st

import capa_simulation.components.process_labels as process_labels_module
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.persistence.cache as persistence_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache
import capa_simulation.settings as settings
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.services.equipment_samples import sample_equipment_master
from capa_simulation.services.securement_threshold import SecurementThresholds

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database_path)!r})
settings.DUCKDB_PATH = Path({str(simulation_path)!r})
months = {months!r}
processes = sorted(set(sample_equipment_master()["공정소분류"]))
required = pd.DataFrame(
    [
        {{"생산계획년월": month, "공정": process, "STEP": step, "소요대수": 6.0}}
        for month in months
        for process in processes
        for step in ("S1", "S2")
    ]
)
display_order = pd.DataFrame(
    columns=["페이지 구분", "탭 구분", "정렬우선순위", "분류컬럼", "정렬방식", "분류값",
             "값표시순서", "활성여부"]
)
reference_tables = {{
    "RQ_DISPLAY_ORDER": display_order,
    "RQ_PKG_PLAN": pd.DataFrame({{"생산계획년월": months}}),
}}
# 소요대수 산출 기준(RQ_REQB)은 데이터 범위만 쓰인다 — 조회기간이 그 밖일 때 알리는 범위.
active = {{
    "content_token": "shortening-test",
    "tables": {{"RQ_REQB": pd.DataFrame({{"생산계획년월": months}})}},
}}
density = pd.DataFrame({{"생산계획년월": months, "부하량": [12.5 + i for i in range(len(months))]}})
wafer = pd.DataFrame({{"생산계획년월": months, "Wafer 부하량": [198000.0] * len(months)}})

originals = (
    reference_cache.get_effective_reference_version,
    reference_cache.get_effective_reference_tables,
    scenario_state.ensure_active_scenario,
    simulation_cache.get_scenario_capacity_and_demand,
    simulation_cache.get_home_simulation,
    persistence_cache.load_global_securement_threshold,
    persistence_cache.load_global_past_data,
)
# 공정 표시명. 갈아 끼우지 않으면 진짜 조회가 시뮬레이션 DB 를 만들고 마이그레이션을 모두 건다.
original_get_process_labels = process_labels_module.get_process_labels


def home_simulation(**kwargs):
    # HOME 과 같은 키로 부르는지 보려고 받은 키를 잡아 둔다.
    st.session_state["captured_home_key"] = kwargs["cache_key"]
    return density, None, wafer, None, None, None


def missing_scenario(_tables, _version):
    raise RuntimeError("활성 시나리오가 없습니다.")


original_download_button = st.download_button


def record_download_button(label, *args, **kwargs):
    # 내보낸 바이트·파일 이름은 위젯 proto 에 실리지 않는다. 버튼은 그대로 그리고 인자만 적어 둔다.
    downloads = st.session_state.setdefault("captured_downloads", {{}})
    downloads[kwargs.get("key")] = {{
        "label": label,
        "file_name": kwargs.get("file_name"),
        "data": kwargs.get("data"),
    }}
    return original_download_button(label, *args, **kwargs)


reference_cache.get_effective_reference_version = lambda: 1
reference_cache.get_effective_reference_tables = lambda: reference_tables
scenario_state.ensure_active_scenario = (
    missing_scenario if {fail_scenario!r} else (lambda _tables, _version: active)
)
simulation_cache.get_scenario_capacity_and_demand = lambda cache_key, **_kwargs: (
    pd.DataFrame(),
    required.loc[required["생산계획년월"].between(cache_key[2], cache_key[3])],
)
simulation_cache.get_home_simulation = home_simulation
persistence_cache.load_global_securement_threshold = lambda _path: SimpleNamespace(
    thresholds=SecurementThresholds(1.095, 0.995)
)
persistence_cache.load_global_past_data = lambda _path: SimpleNamespace(
    monthly=pd.DataFrame({{"생산계획년월": {list(past_months)!r}}})
)
process_labels_module.get_process_labels = lambda: ProcessLabels(
    version=1, labels={dict(labels or {})!r}
)
try:
    # streamlit 모듈 자체를 바꾸는 패치라 원복이 반드시 돌아야 한다.
    st.download_button = record_download_button
    st.session_state["production_month_range_v2"] = ("{first // 100}-{first % 100:02d}",
                                                      "{last // 100}-{last % 100:02d}")
    page_source = Path({str(page)!r}).read_text(encoding="utf-8")
    exec(compile(page_source, {str(page)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    (
        reference_cache.get_effective_reference_version,
        reference_cache.get_effective_reference_tables,
        scenario_state.ensure_active_scenario,
        simulation_cache.get_scenario_capacity_and_demand,
        simulation_cache.get_home_simulation,
        persistence_cache.load_global_securement_threshold,
        persistence_cache.load_global_past_data,
    ) = originals
    process_labels_module.get_process_labels = original_get_process_labels
    st.download_button = original_download_button
"""
