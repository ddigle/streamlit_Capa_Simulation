# Purpose: 필요단축일정 탭의 그림·목표 전환·공정 필터·CSV 세 벌과 시나리오 없을 때 정지를 검사한다.

"""필요단축일정 탭(AppTest).

빈 설비 DB 는 오늘 날짜에 맞춘 샘플 fleet 을 보이므로(`equipment_samples.py`) 그 호기로 계산이
돈다. 시나리오 쪽(기준정보·활성 시나리오·소요대수·HOME 계획)은 모듈 속성을 갈아 끼워 흉내 낸다 —
페이지와 컴포넌트가 그 함수를 **부를 때** 모듈에서 찾는다.
"""

from __future__ import annotations

import codecs
import io
import re
from datetime import date
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _open_tab

from capa_simulation.components.required_shortening_panel import (
    SHORTENING_LEVEL_KEY,
    SHORTENING_PROCESS_KEY,
    _unit_row,
)
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
from capa_simulation.navigation import EQUIPMENT_SHORTENING_TAB
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    empty_downtime_schedule,
    empty_equipment_baseline,
)
from capa_simulation.services.equipment_samples import sample_equipment_master
from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    LEVEL_COLUMN,
    PROCESS_MONTH_EXPORT_COLUMNS,
    UNIT_EXPORT_COLUMNS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
TAB = "필요단축일정"


def _months(count: int = 6) -> list[int]:
    today = date.today()
    year, month = today.year, today.month
    months = []
    for _ in range(count):
        months.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _shift(month: int, delta: int) -> int:
    year, index = divmod(month // 100 * 12 + month % 100 - 1 + delta, 12)
    return year * 100 + index + 1


def _script(
    database_path: Path,
    *,
    fail_scenario: bool = False,
    past_months: tuple[int, ...] = (),
    sidebar_first: int | None = None,
) -> str:
    simulation_path = database_path.with_name(f"{database_path.stem}_simulation.duckdb")
    months = _months()
    first, last = sidebar_first or months[0], months[-1]
    return f"""
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st

import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.persistence.cache as persistence_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache
import capa_simulation.settings as settings
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
active = {{"content_token": "shortening-test", "tables": {{}}}}
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
try:
    # streamlit 모듈 자체를 바꾸는 패치라 원복이 반드시 돌아야 한다.
    st.download_button = record_download_button
    st.session_state["production_month_range_v2"] = ("{first // 100}-{first % 100:02d}",
                                                      "{last // 100}-{last % 100:02d}")
    page_source = Path({str(PAGE)!r}).read_text(encoding="utf-8")
    exec(compile(page_source, {str(PAGE)!r}, "exec"), {{"__name__": "__main__"}})
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
    st.download_button = original_download_button
"""


def _database(tmp_path: Path) -> Path:
    database_path = tmp_path / "availability.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    processes = sorted(set(sample_equipment_master()["공정소분류"]))
    repository.save_process_cutoff(
        pd.DataFrame(
            {
                "공정": processes,
                "Cutoff일수": [10.0] * len(processes),
                "비고": [None] * len(processes),
            }
        )
    )
    return database_path


def _run(
    database_path: Path,
    *,
    fail_scenario: bool = False,
    past_months: tuple[int, ...] = (),
    sidebar_first: int | None = None,
) -> AppTest:
    script = _script(
        database_path,
        fail_scenario=fail_scenario,
        past_months=past_months,
        sidebar_first=sidebar_first,
    )
    app = AppTest.from_string(script, default_timeout=120).run()
    return _open_tab(app, TAB)


def _html(app: AppTest) -> str:
    return "\n".join(str(element.proto.body) for element in app.get("html"))


def _cards(app: AppTest) -> list[str]:
    body = _html(app)
    return [
        chunk.split('"', 1)[0] for chunk in body.split('<section class="shk-card" aria-label="')[1:]
    ]


def test_the_tab_draws_kpis_the_plan_summary_and_process_cards(tmp_path: Path) -> None:
    app = _run(_database(tmp_path))

    assert not app.exception, [element.message for element in app.exception]
    # 탭은 RawData 뒤 다섯째다. `app.tabs` 는 깊이 우선이라 RawData 안쪽 탭이 그 사이에 낀다.
    labels = [tab.label for tab in app.tabs]
    assert labels[:4] == [
        ":material/dashboard: Main",
        ":material/compare_arrows: Static/Dynamic",
        ":material/tune: Preference",
        ":material/table_rows: RawData",
    ]
    assert labels.index(EQUIPMENT_SHORTENING_TAB) > labels.index(":material/table_rows: RawData")
    body = _html(app)
    assert "부족 공정" in body and "신규 필요" in body
    assert "계획 · LOB 요약" in body
    assert "Dynamic B/N 확보율 현재" in body and "Dynamic B/N 확보율 단축 후" in body
    # Density·Wafer 는 HOME 계산 결과를 그대로 쓴다(여기서는 흉내 낸 값).
    assert "12.50" in body and "198K" in body
    # 소요 6.0 x 110% 는 샘플 가용으로 모자라는 공정이 있다 — 공정을 안 고르면 그 공정만 카드다.
    assert _cards(app), body[:500]
    # 호기 줄은 한 줄이다 — 늘어난 환산대수 줄과 「(기여 …)」 는 줄에 없고 풍선에만 있다.
    assert 'class="shk-unit"' in body
    assert "shk-gain" not in body and "(기여 " not in body
    # 조건 카드에는 기간과 공정이, 본문 머리에는 목표 확보율이 선다.
    assert {"시작 월", "끝 월"} <= {widget.label for widget in app.sidebar.selectbox}
    assert "공정 (표시순서)" in {widget.label for widget in app.sidebar.multiselect}
    assert "목표 확보율" in {widget.label for widget in app.main.selectbox}
    downloads = {str(button.key) for button in app.get("download_button")}
    assert {
        "equipment_shortening_units_csv",
        "equipment_shortening_units_all_levels_csv",
        "equipment_shortening_months_csv",
    } <= downloads
    clear_equipment_repository()


def _csv(app: AppTest, key: str) -> tuple[dict[str, object], pd.DataFrame]:
    """잡아 둔 내려받기 하나 — 인자와, 바이트를 다시 읽은 표."""
    captured = app.session_state["captured_downloads"][key]
    data = captured["data"]
    assert isinstance(data, bytes)
    # Excel 이 한글을 깨뜨리지 않게 BOM 이 붙은 UTF-8 이다.
    assert data.startswith(codecs.BOM_UTF8), data[:8]
    frame = pd.read_csv(io.StringIO(data.decode("utf-8-sig")), dtype=str, keep_default_na=False)
    return captured, frame


def test_the_tab_offers_three_csvs_with_the_unit_schedule(tmp_path: Path) -> None:
    """CSV 세 벌 — 고른 목표의 호기별 단축 일정, 다섯 목표를 한 파일로, 공정·월(목표 칸 추가)."""
    app = _run(_database(tmp_path))
    assert not app.exception, [element.message for element in app.exception]

    labels = {str(button.key): button.label for button in app.download_button}
    assert labels["equipment_shortening_units_csv"] == "호기별 단축 일정 CSV"
    assert labels["equipment_shortening_units_all_levels_csv"] == "호기별 단축 일정 CSV · 목표 전체"
    assert labels["equipment_shortening_months_csv"] == "공정·월 CSV"

    captured, units = _csv(app, "equipment_shortening_units_csv")
    assert list(units.columns) == list(UNIT_EXPORT_COLUMNS)
    assert str(captured["file_name"]).startswith("required_shortening_units_110pct_")
    # 처음 목표는 110% 이고, 샘플 가용으로는 소요 6.0 x 110% 를 못 채우는 공정이 있다.
    assert not units.empty
    assert set(units[LEVEL_COLUMN]) == {"110"}
    assert set(units["구분"]) <= {KIND_SHORTENED, KIND_NEW}
    shortened = units.loc[units["구분"].eq(KIND_SHORTENED)]
    # 샘플 fleet 은 오늘에 맞춰 Qual 이 남은 신규 호기를 둔다 — 당긴 호기 줄이 있어야 뜻이 있다.
    assert not shortened.empty
    # 당긴 호기에는 마스터 속성이 붙고(공정소분류 = 공정), 가상 호기는 비어 있다.
    assert shortened["공정소분류"].eq(shortened["공정"]).all()
    assert shortened["설비명"].ne("").all()
    assert units.loc[units["구분"].eq(KIND_NEW), "설비명"].eq("").all()
    for column in ("기존 Qual 완료일", "기존 기여 시작일", "목표 Qual 완료일", "목표 기여 시작일"):
        assert shortened[column].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all(), column
    assert units["대상 월"].str.fullmatch(r"\d{4}-\d{2}").all()

    _, all_levels = _csv(app, "equipment_shortening_units_all_levels_csv")
    assert list(all_levels.columns) == list(UNIT_EXPORT_COLUMNS)
    levels = list(dict.fromkeys(all_levels[LEVEL_COLUMN]))
    assert levels == sorted(levels, key=int)
    assert set(levels) <= {"90", "100", "110", "120", "130"}
    # 고른 목표의 블록은 고른 목표 파일과 같다.
    pd.testing.assert_frame_equal(
        all_levels.loc[all_levels[LEVEL_COLUMN].eq("110")].reset_index(drop=True), units
    )

    _, months = _csv(app, "equipment_shortening_months_csv")
    assert list(months.columns) == list(PROCESS_MONTH_EXPORT_COLUMNS)
    assert set(months[LEVEL_COLUMN]) == {"110"}

    # 목표를 바꾸면 고른 목표 파일이 따라 바뀌고, 목표 전체 파일은 그대로다.
    high = app.selectbox(key=SHORTENING_LEVEL_KEY).set_value(1.3).run()
    assert not high.exception
    _, high_units = _csv(high, "equipment_shortening_units_csv")
    assert set(high_units[LEVEL_COLUMN]) == {"130"}
    _, high_all = _csv(high, "equipment_shortening_units_all_levels_csv")
    pd.testing.assert_frame_equal(high_all, all_levels)
    clear_equipment_repository()


def test_switching_the_target_level_changes_the_result_without_errors(tmp_path: Path) -> None:
    app = _run(_database(tmp_path))
    low = app.selectbox(key=SHORTENING_LEVEL_KEY).set_value(0.9).run()
    assert not low.exception
    low_body = _html(low)
    low_cards = _cards(low)

    high = low.selectbox(key=SHORTENING_LEVEL_KEY).set_value(1.3).run()
    assert not high.exception
    high_body = _html(high)
    assert "과부족 (목표 130%)" in high_body
    assert "목표 130% 기준" in high_body and "목표 90% 기준" in low_body
    # 목표를 올리면 모자란 공정이 늘거나 같다 — 미선택이면 그 공정이 모두 카드로 선다.
    assert len(_cards(high)) >= len(low_cards)
    assert len(_cards(high)) > 0
    clear_equipment_repository()


def test_the_process_filter_narrows_the_cards(tmp_path: Path) -> None:
    app = _run(_database(tmp_path))
    options = list(app.multiselect(key=SHORTENING_PROCESS_KEY).options)
    assert options, "맞댄 공정이 공정 선택지가 되어야 한다"
    chosen = options[0]

    filtered = app.multiselect(key=SHORTENING_PROCESS_KEY).set_value([chosen]).run()

    assert not filtered.exception
    assert _cards(filtered) == [chosen]
    # 고른 공정은 목표를 채워도 카드가 선다(「목표 충족」 배지).
    satisfied = filtered.selectbox(key=SHORTENING_LEVEL_KEY).set_value(0.9).run()
    assert _cards(satisfied) == [chosen]
    clear_equipment_repository()


def test_a_missing_scenario_stops_only_this_tab(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    app = _run(database_path, fail_scenario=True)

    assert not app.exception
    warnings = " ".join(str(item.value) for item in app.warning)
    assert "소요대수를 읽지 못해" in warnings, warnings
    assert "활성 시나리오가 없습니다" in warnings
    assert not _cards(app)
    # 다른 탭(Cut-off 입력)은 그대로 쓴다.
    _open_tab(app, "Preference")
    assert not app.exception
    assert any(button.label == "Cut-off 저장" for button in app.button)
    clear_equipment_repository()


def test_the_plan_summary_uses_homes_key_with_past_data(tmp_path: Path) -> None:
    """Density·Wafer 는 HOME 과 **같은 키**로 부른다 — 과거 구간(Past Data)이 있으면 그 달까지다.

    HOME 의 키 달은 조회기간 ∩ (계획 범위를 과거 달까지 넓힌 범위)다. 계획 범위만 보면 과거 구간이
    있을 때 키가 갈려 HOME 계산을 한 번 더 했다(2026-10-07 리뷰).
    """
    months = _months()
    past = _shift(months[0], -6)
    app = _run(_database(tmp_path), past_months=(past,), sidebar_first=_shift(months[0], -12))

    assert not app.exception
    key = app.session_state["captured_home_key"]
    assert (key[2], key[3]) == (past, months[-1])
    clear_equipment_repository()


def test_undated_new_units_are_announced_as_not_being_candidates(tmp_path: Path) -> None:
    """일정 미정 신규 호기는 Dynamic 에도 단축 후보에도 들지 않는다 — 다른 탭과 같은 한 줄로 알린다.

    알리지 않으면 「그 호기를 당기면 될 텐데 왜 추가N 이 필요한가」로 읽힌다(2026-10-08 점검 A5).
    """
    database_path = _database(tmp_path)
    sample = sample_equipment_master()
    master = pd.concat([sample, sample.iloc[[0]]], ignore_index=True)
    last = master.index[-1]
    process = str(master.at[last, "공정소분류"])
    master.loc[last, "설비명"] = "UNDATED-NEW-01"
    blank = ["반입일정", "Qual일정", "확정상태", "반출일정", "이설일정", "X좌표", "Y좌표"]
    master.loc[last, [*blank, "Xsize", "Ysize"]] = None
    master.loc[last, ["기존설비여부", "보관유무", "레이아웃표시"]] = "N"
    master.loc[last, "사용기준"] = "HBM"
    DuckDBEquipmentRepository(database_path).save_snapshot(
        empty_equipment_baseline(), master, empty_downtime_schedule(), note="일정 미정 호기"
    )

    app = _run(database_path)

    assert not app.exception, [element.message for element in app.exception]
    captions = [str(item.value) for item in app.main.caption]
    expected = (
        ":material/event_busy: 일정 미정 1대 (반입 미정 1) — 날짜가 들어올 때까지 가용대수에 "
        "세지 않습니다. 단축 후보에도 들지 않습니다."
    )
    assert expected in captions, captions
    # 공정을 고르면 그 공정만 센다 — 다른 공정만 고르면 줄이 사라진다.
    others = [
        name for name in app.multiselect(key=SHORTENING_PROCESS_KEY).options if name != process
    ]
    narrowed = app.multiselect(key=SHORTENING_PROCESS_KEY).set_value(others[:1]).run()
    assert not narrowed.exception
    assert not any("일정 미정" in str(item.value) for item in narrowed.main.caption)
    clear_equipment_repository()


def test_an_empty_fleet_explains_the_empty_card(tmp_path: Path) -> None:
    """호기가 없고 샘플도 끄면 고를 조건이 없다 — 카드를 비워 두지 않고 까닭을 한 줄 적는다."""
    app = _run(_database(tmp_path))
    app = app.toggle(key=SAMPLE_TOGGLE_KEY).set_value(False).run()

    assert not app.exception
    assert any("조회할 호기가 없습니다" in str(item.value) for item in app.sidebar.caption)
    assert any("등록된 호기가 없습니다" in str(item.value) for item in app.info)
    assert not _cards(app)
    clear_equipment_repository()


def _visible(markup: str) -> str:
    """풍선(`title`)을 뺀 줄 글자."""
    return re.sub(r'title="[^"]*"', "", markup)


def test_a_shortened_unit_row_is_one_line_with_the_full_detail_in_its_title() -> None:
    """왼쪽은 이름과 「기존 MM.DD → 단축 MM.DD」, 오른쪽은 「−N일」 하나다(2026-10-07 사용자 요청).

    기여 시작일·늘어난 환산대수·모듈 수·연도는 줄에서 빠지고 풍선에 남는다.
    """
    axis = (date(2026, 10, 1), date(2027, 1, 1))
    row: dict[str, object] = {
        "호기": "EQ<LONG>-0001",
        "구분": KIND_SHORTENED,
        "기존 Qual": date(2026, 12, 10),
        "목표 Qual": date(2026, 10, 7),
        "단축일수": 64,
        "늘어난 환산대수": 0.29,
        "모듈 수": 2,
        "해소 기여 월": "26.10",
    }

    markup = _unit_row(row, axis, "")
    visible = _visible(markup)

    assert '<span class="shk-unit-name">EQ&lt;LONG&gt;-0001</span>' in markup
    assert (
        '<span class="shk-muted">기존</span> 12.10 → <span class="shk-muted">단축</span> 10.07'
    ) in visible
    assert '<div class="shk-result"><span class="shk-cut">−64일</span></div>' in visible
    for gone in ("기여", "+0.29대", "모듈", "26.12.10", "2026"):
        assert gone not in visible, gone
    title = re.search(r'title="([^"]*)"', markup)
    assert title is not None
    assert title.group(1) == (
        "EQ&lt;LONG&gt;-0001 · 기존 Qual 2026-12-10 → 목표 Qual 2026-10-07 · −64일 · "
        "기여 시작 2026-10-08 · 늘어난 환산대수 +0.29대 · 모듈 2 · 해소 기여 월 26.10"
    )


def test_a_virtual_unit_row_says_when_it_is_needed_and_new() -> None:
    """가상 호기는 이름과 「필요 MM.DD」, 오른쪽은 「신규」 하나다."""
    axis = (date(2026, 10, 1), date(2027, 1, 1))
    row: dict[str, object] = {
        "호기": "추가1",
        "구분": KIND_NEW,
        "기존 Qual": None,
        "목표 Qual": date(2026, 11, 3),
        "단축일수": None,
        "늘어난 환산대수": 0.26,
        "모듈 수": None,
        "해소 기여 월": "26.11",
    }

    markup = _unit_row(row, axis, "")
    visible = _visible(markup)

    assert '<span class="shk-muted">필요</span> 11.03' in visible
    assert '<div class="shk-result"><span class="shk-new">신규</span></div>' in visible
    assert "−" not in visible and "기여" not in visible and "+0.26대" not in visible
    assert "신규 필요 Qual 2026-11-03 · 기여 시작 2026-11-04 · 늘어난 환산대수 +0.26대" in markup
