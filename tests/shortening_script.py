# Purpose: 필요 단축 일정·Space 필요 단축 보기 AppTest 가 같이 쓰는 시나리오 흉내 스크립트를 만든다.

"""시나리오 쪽(기준정보·활성 시나리오·소요대수·HOME 계획·판정 기준·Past Data·공정 표시명)을 모듈
속성으로 갈아 끼우고 페이지 하나를 돌리는 AppTest 스크립트 글(`AppTest.from_string`). 페이지와
컴포넌트가 그 함수를 **부를 때** 모듈에서 찾으므로 두 화면이 같은 흉내를 본다 — Space 「필요 단축」
보기와 필요 단축 일정의 키 같음 시험(T-P5)이 같은 수요로 돈다. 빈 설비 DB 는 오늘에 맞춘 샘플
fleet 을 보이므로 그 호기로 계산이 돈다.

현재 일정 기준(Static | 설비 마스터 — 2026-11-20)은 `basis` 로 처음 세션 값을 심는다. 기본은 설비
마스터다 — 그 앞에 쓴 시험이 설비 마스터 기준의 숫자를 본다. `None` 이면 심지 않아 화면 기본값
(Static)이다. `static` 을 주면 활성 시나리오에 Static 가용대수 표(`RQ_EQP_AVBL` — 모든 공정 · 달에
그 값)를 싣는다.

스크립트가 돈 수는 세션 칸 `test_runs` 에 쌓인다 — 한 조작이 앱 전체 회차를 몇 번 돌렸는지 본다.
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
    basis: str | None = "설비 마스터",
    static: float | None = None,
) -> str:
    simulation_path = database_path.with_name(f"{database_path.stem}_simulation.duckdb")
    months = months_from_today()
    first, last = sidebar_first or months[0], sidebar_last or months[-1]
    static_tables = (
        ""
        if static is None
        else (
            'active["tables"]["RQ_EQP_AVBL"] = pd.DataFrame(\n'
            f'    [{{"생산계획년월": month, "공정": process, "가용대수": {static!r}}}\n'
            "     for month in months for process in processes]\n)\n"
        )
    )
    token_tail = "" if static is None else f"-static-{static}"
    basis_seed = (
        ""
        if basis is None
        else f'    st.session_state.setdefault("equipment_shortening_basis_v1", {basis!r})\n'
    )
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
from capa_simulation.persistence.models import RouteLoadExceptionState
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
# 내용 토큰은 Static 가용대수 표까지 덮는다(앱에서는 표가 바뀌면 새 토큰) — 표를 실은 흉내는
# 다른 토큰.
active = {{
    "content_token": "shortening-test{token_tail}",
    "tables": {{"RQ_REQB": pd.DataFrame({{"생산계획년월": months}})}},
}}
{static_tables}
density = pd.DataFrame({{"생산계획년월": months, "부하량": [12.5 + i for i in range(len(months))]}})
# HOME 집계 기준(Dummy 계열 뺌) 월 합 — 이 화면의 「Wafer 계획」 줄이 읽는 셋째 원소.
home_wafer = pd.DataFrame({{"생산계획년월": months, "Wafer 부하량": [176000.0] * len(months)}})
# 거르지 않은 합은 다른 값으로 마지막(여섯째, 제품×월 수량 자리) 원소에 둔다 — 마지막 원소를 읽는
# 풀기로 돌아가면 이 값이 보인다.
unfiltered_wafer = pd.DataFrame(
    {{"생산계획년월": months, "Wafer 부하량": [198000.0] * len(months)}}
)

originals = (
    reference_cache.get_effective_reference_version,
    reference_cache.get_effective_reference_tables,
    scenario_state.ensure_active_scenario,
    simulation_cache.get_scenario_capacity_and_demand,
    simulation_cache.get_home_simulation,
    persistence_cache.load_global_securement_threshold,
    persistence_cache.load_global_past_data,
    persistence_cache.load_global_route_load_exceptions,
)
# 공정 표시명. 갈아 끼우지 않으면 진짜 조회가 시뮬레이션 DB 를 만들고 마이그레이션을 모두 건다.
original_get_process_labels = process_labels_module.get_process_labels


def home_simulation(**kwargs):
    # HOME 과 같은 키로 부르는지 보려고 받은 키를 잡아 둔다.
    st.session_state["captured_home_key"] = kwargs["cache_key"]
    return density, None, home_wafer, None, None, unfiltered_wafer


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
# 부하 예외 선언(공용 프로필)도 DB 조회 경계다 — 빈 선언 판을 준다.
persistence_cache.load_global_route_load_exceptions = (
    lambda _path: RouteLoadExceptionState().profile
)
process_labels_module.get_process_labels = lambda: ProcessLabels(
    version=1, labels={dict(labels or {})!r}
)
try:
    # 스크립트가 돈 수(앱 전체 회차 — `st.rerun` 으로 다시 돈 것 포함).
    st.session_state["test_runs"] = st.session_state.get("test_runs", 0) + 1
    # streamlit 모듈 자체를 바꾸는 패치라 원복이 반드시 돌아야 한다.
    st.download_button = record_download_button
    st.session_state["production_month_range_v2"] = ("{first // 100}-{first % 100:02d}",
                                                      "{last // 100}-{last % 100:02d}")
{basis_seed}
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
        persistence_cache.load_global_route_load_exceptions,
    ) = originals
    process_labels_module.get_process_labels = original_get_process_labels
    st.download_button = original_download_button
"""
