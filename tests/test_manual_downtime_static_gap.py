# Purpose: 입력 비가동이 Static 대비 일정의 일정 기준 가용·시트·근거·교차검증에서 빠지는지 본다.

"""가용설비 현황 › Summary › 「Static 대비 일정」 의 입력 비가동(가용설비 현황 › Preference).

입력 비가동은 실행 쪽 「설비 일정 기준 가용대수」 에서 빠진다(2026-10-27 사용자 결정 1 — 「실행
가용대수에서 뺀다」). Static 대비 일정의 그림·9행 시트·확보율 교차검증도 그 가용을 보이므로 같은
칸을 같은 멈춤 규칙으로 뺀다 — 필요 단축 일정 계획·공정 Capa 상세 ② 와 같은 값이어야 한다.

- 시트: 설비 일정 기준 가용 = 소계 − 뺀 몫, 보유는 그대로라 그 몫이 대여(비가동)에 든다. 그 달
  가용보다 크면 가용은 0 에서 멈춘다.
- 다른 화면과 같은 값: 시트 가용 = 필요 단축 일정 계획 가용 = 공정 Capa 상세 `bridge.가용대수` =
  교차검증 일정기준가용대수.
- 캐시 키: 조회 달 안의 칸이 바뀌면 시트·교차검증 키가 갈리고, 달 밖 칸은 가르지 않는다.
- 패널(AppTest): 시트 값·근거 카드 「입력 비가동 · Preference」 줄(줄을 더하면 칸)·교차검증 캡션,
  호기 필터 시트에는 들지 않는다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from sheet_reader import chart_spec, open_cell, sheet_cells, sheet_value
from streamlit.testing.v1 import AppTest
from test_availability_gap_panel import _panel_app
from test_availability_gap_unit_filter import _filter_app
from test_availability_sheet import KEYS, _Built, _f
from test_equipment_pages import _open_tab, _page_script

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.availability_gap_panel import (
    PROCESS_FILTER_KEY,
    RESULT_VIEW_KEY,
    UNIT_FILTER_COLUMNS_KEY,
    unit_filter_key,
)
from capa_simulation.components.availability_sheet_keys import GAP_SHEET_LABEL_CHART_KEY
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_manual_downtime_cache,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services import simulation_cache
from capa_simulation.services.availability_sheet import (
    BREAKDOWN_LENT_COLUMN,
    KIND_MANUAL_LINE,
    MANUAL_APPLIED_COLUMN,
    MANUAL_ENTERED_COLUMN,
    ROW_GAP_AVAILABLE,
    ROW_SCHEDULE_AVAILABLE,
    ROW_SCHEDULE_LENT,
    ROW_SCHEDULE_OWNED,
    build_availability_sheet,
    manual_downtime_lines,
    sheet_view,
)
from capa_simulation.services.manual_downtime import (
    MANUAL_DOWNTIME_BAND,
    ManualDowntime,
    ManualRow,
    period_months,
)
from capa_simulation.services.process_equipment_timeline import build_process_equipment_timeline
from capa_simulation.services.required_shortening import plan_required_shortening
from capa_simulation.services.securement_cross_check import cross_check_from_monthly

MONTH = 202610


@pytest.fixture(autouse=True)
def _no_scrollbar(monkeypatch: pytest.MonkeyPatch) -> None:
    """AppTest 에서 등록되지 않는 가로 스크롤바 컴포넌트를 뺀다(다른 패널 시험과 같다)."""
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda **_: None)


@pytest.fixture(scope="module")
def built() -> _Built:
    return _Built()


def _manual_sheet(built: _Built, rows: tuple[ManualRow, ...]) -> Any:
    return build_availability_sheet(
        built.monthly, built.free_monthly, *built.static, built.months, manual_downtime=rows
    )


# ------------------------------------------------------------------ 시트(서비스)


def test_the_sheet_takes_the_input_from_available_into_lent_and_stops_at_zero(
    built: _Built,
) -> None:
    month = built.months[0]
    before = built.sheet.rows.set_index(KEYS)
    available = _f(before.at[(month, "P_A"), ROW_SCHEDULE_AVAILABLE])
    p_b = _f(before.at[(month, "P_B"), ROW_SCHEDULE_AVAILABLE])
    rows: tuple[ManualRow, ...] = (("P_A", month, 1.25), ("P_B", month, p_b + 3.0))
    after = _manual_sheet(built, rows).rows.set_index(KEYS)

    # P_A — 가용에서 1.25 를 빼고 보유는 그대로, 그 몫이 대여에 든다.
    assert _f(after.at[(month, "P_A"), ROW_SCHEDULE_AVAILABLE]) == pytest.approx(available - 1.25)
    assert _f(after.at[(month, "P_A"), ROW_SCHEDULE_OWNED]) == pytest.approx(
        _f(before.at[(month, "P_A"), ROW_SCHEDULE_OWNED])
    )
    assert _f(after.at[(month, "P_A"), ROW_SCHEDULE_LENT]) == pytest.approx(
        _f(before.at[(month, "P_A"), ROW_SCHEDULE_LENT]) - 1.25
    )
    assert _f(after.at[(month, "P_A"), MANUAL_APPLIED_COLUMN]) == pytest.approx(1.25)
    # P_B — 그 달 가용보다 크게 넣으면 가용은 0 에서 멈추고 넣은 값은 그대로 남는다.
    assert _f(after.at[(month, "P_B"), ROW_SCHEDULE_AVAILABLE]) == pytest.approx(0.0)
    assert _f(after.at[(month, "P_B"), MANUAL_APPLIED_COLUMN]) == pytest.approx(p_b)
    assert _f(after.at[(month, "P_B"), MANUAL_ENTERED_COLUMN]) == pytest.approx(p_b + 3.0)
    # 다른 달은 그대로다.
    other = built.months[1]
    assert _f(after.at[(other, "P_A"), ROW_SCHEDULE_AVAILABLE]) == pytest.approx(
        _f(before.at[(other, "P_A"), ROW_SCHEDULE_AVAILABLE])
    )

    view = sheet_view(_manual_sheet(built, rows), processes=("P_A", "P_B"))
    assert view.manual_at(month) == pytest.approx((1.25 + p_b, 1.25 + p_b + 3.0))
    assert view.manual_at(other) == (0.0, 0.0)
    lines = manual_downtime_lines(_manual_sheet(built, rows), month, ("P_A", "P_B"))
    assert lines["구분"].tolist() == [KIND_MANUAL_LINE, KIND_MANUAL_LINE]
    assert lines["가용"].sum() == pytest.approx(-(1.25 + p_b))
    assert lines[BREAKDOWN_LENT_COLUMN].sum() == pytest.approx(-(1.25 + p_b))
    assert "그 달 가용에서 멈춤" in str(lines.loc[lines["공정"].eq("P_B"), "비가동 내역"].iloc[0])


def test_without_input_the_sheet_is_unchanged(built: _Built) -> None:
    columns = [column for column in built.sheet.rows.columns if column != MANUAL_APPLIED_COLUMN]
    plain = _manual_sheet(built, ())
    pd.testing.assert_frame_equal(plain.rows.loc[:, columns], built.sheet.rows.loc[:, columns])
    assert float(plain.rows[MANUAL_APPLIED_COLUMN].abs().sum()) == 0.0


def test_the_sheet_matches_required_shortening_process_detail_and_cross_check(
    built: _Built,
) -> None:
    """입력 비가동이 있어도 Static 대비 일정의 설비 일정 기준 가용 = 필요 단축 일정 계획 가용 = 공정
    Capa 상세 ② = 교차검증 일정기준가용대수다(넘친 칸 포함)."""
    first, second = built.months[0], built.months[1]
    rows: tuple[ManualRow, ...] = (
        ("P_A", first, 0.75),
        ("P_A", second, 2.5),
        ("P_B", second, 99.0),
    )
    sheet = _manual_sheet(built, rows).rows.set_index(KEYS)

    for process in ("P_A", "P_B"):
        timeline = build_process_equipment_timeline(
            built.master,
            built.downtime,
            built.baseline,
            built.cutoff,
            process=process,
            months=built.months,
            manual_downtime=tuple((month, units) for name, month, units in rows if name == process),
        )
        bridge = timeline.bridge.set_index("생산계획년월")
        for month in built.months:
            assert _f(bridge.at[month, "가용대수"]) == pytest.approx(
                _f(sheet.at[(month, process), ROW_SCHEDULE_AVAILABLE]), abs=5e-9
            )

    required = built.static[2][["생산계획년월", "공정"]].assign(소요대수=1.0)
    plan = plan_required_shortening(
        equipment=built.master,
        downtime=built.downtime,
        baseline=built.baseline,
        cutoff=built.cutoff,
        required_equipment=required,
        months=built.months,
        today=date(2026, 10, 17),
        levels=(1.0,),
        manual_downtime=rows,
    )
    planned = plan.at(1.0).process_months.set_index(KEYS)["가용대수"]
    for key, value in planned.items():
        assert _f(value) == pytest.approx(_f(sheet.at[key, ROW_SCHEDULE_AVAILABLE]), abs=1e-9)

    check = cross_check_from_monthly(built.static[2], built.monthly, required, manual_downtime=rows)
    crossed = check.rows.set_index(KEYS)
    for process in ("P_A", "P_B"):
        for month in (first, second):
            assert _f(crossed.at[(month, process), "Dynamic가용대수"]) == pytest.approx(
                _f(sheet.at[(month, process), ROW_SCHEDULE_AVAILABLE]), abs=1e-9
            )


# ------------------------------------------------------------------ 캐시 키


def test_the_sheet_and_cross_check_keys_carry_the_cells_of_their_months(built: _Built) -> None:
    monthly_key = simulation_cache.dynamic_monthly_cache_key(
        spans=built.monthly,
        baseline=built.baseline,
        cutoff=built.cutoff,
        months=built.months,
        conversion_ratios=built.ratios,
    )
    owned, lent, available = built.static

    def sheet_key(manual: ManualDowntime) -> simulation_cache.AvailabilitySheetCacheKey:
        return simulation_cache.availability_sheet_cache_key(
            monthly_key,
            None,
            static_owned=owned,
            static_lent=lent,
            static_available=available,
            manual_downtime=manual,
        )

    comparison_key = simulation_cache.availability_comparison_cache_key(
        monthly_key, static=available
    )

    def cross_key(manual: ManualDowntime) -> simulation_cache.SecurementCrossCheckCacheKey:
        return simulation_cache.securement_cross_check_cache_key(
            comparison_key, (1, "token", MONTH, MONTH), manual_downtime=manual
        )

    empty = ManualDowntime()
    inside = ManualDowntime(rows=(("P_A", built.months[0], 1.0),), version=3)
    outside = ManualDowntime(rows=(("P_A", 203001, 1.0),), version=9)
    for build in (sheet_key, cross_key):
        assert build(inside) != build(empty)
        # 조회 달 밖 칸·version 만 다른 저장은 키를 가르지 않는다.
        assert build(outside) == build(empty)
        assert build(inside)[-1] == (("P_A", built.months[0], 1.0),)


# ------------------------------------------------------------------ 패널(AppTest)


def _run(**state: object) -> AppTest:
    app = AppTest.from_function(_panel_app, default_timeout=30)
    for key, value in state.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    return app


def _view(app: AppTest, value: str) -> None:
    app.segmented_control(key=RESULT_VIEW_KEY).set_value(value).run()
    assert not app.exception, [element.message for element in app.exception]


def test_the_panel_sheet_figure_and_evidence_take_the_input_out() -> None:
    """Die Attach 202610 — 기존보유 3 + EQ-1 환산 1.5 = 4.5 에서 입력 1.0 을 뺀다."""
    simulation_cache.get_availability_sheet.clear()
    app = _run(manual_rows=[("Die Attach", MONTH, 1.0)])
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()

    # 그림 — 쌓은 두 조각의 합이 뺀 가용이고 가용 풍선이 뺀 몫을 적는다.
    chart = json.loads(app.get("plotly_chart")[0].proto.spec)
    pieces = {trace["name"]: trace for trace in chart["data"]}
    assert pieces["기존보유"]["y"] == [3.0]
    assert pieces["가용(일할·환산)"]["y"] == [0.5]
    assert "입력 비가동 −1.00" in pieces["가용(일할·환산)"]["customdata"][0]

    _view(app, "분류별 내역")
    assert sheet_value(app, MONTH, ROW_SCHEDULE_OWNED) == 4.5
    assert sheet_value(app, MONTH, ROW_SCHEDULE_LENT) == -1.0
    assert sheet_value(app, MONTH, ROW_SCHEDULE_AVAILABLE) == 3.5
    assert sheet_value(app, MONTH, ROW_GAP_AVAILABLE) == -2.5

    open_cell(app, MONTH, ROW_SCHEDULE_AVAILABLE)
    app.run()
    assert not app.exception
    (lines,) = [element.value for element in app.dataframe]
    body = lines.loc[lines["구분"].astype(str).ne("합계")]
    assert "입력 비가동 · Preference" in body["설비명"].tolist()
    assert body["가용"].sum() == pytest.approx(3.5)
    assert lines["가용"].iloc[-1] == pytest.approx(3.5)  # 합계 줄 = 칸
    markdown = " ".join(item.value for item in app.markdown)
    assert "(그 가운데 입력 비가동 −1.00)" in markdown
    captions = " ".join(item.value for item in app.caption)
    assert "Preference 에서 공정 × 달로 넣은 비가동" in captions

    open_cell(app, MONTH, ROW_SCHEDULE_LENT)
    app.run()
    (lines,) = [element.value for element in app.dataframe]
    body = lines.loc[lines["설비명"].astype(str).ne("합계")]
    assert body["설비명"].tolist() == ["입력 비가동 · Preference"]
    assert body[BREAKDOWN_LENT_COLUMN].sum() == pytest.approx(-1.0)


def test_an_input_above_the_month_stops_at_zero_and_says_so() -> None:
    simulation_cache.get_availability_sheet.clear()
    app = _run(manual_rows=[("Die Attach", MONTH, 10.0)])
    app.selectbox(key=PROCESS_FILTER_KEY).select("Die Attach").run()
    _view(app, "분류별 내역")
    assert sheet_value(app, MONTH, ROW_SCHEDULE_AVAILABLE) == 0.0
    assert sheet_value(app, MONTH, ROW_SCHEDULE_LENT) == -4.5
    open_cell(app, MONTH, ROW_SCHEDULE_AVAILABLE)
    app.run()
    captions = " ".join(item.value for item in app.caption)
    assert "넣은 10대 가운데 그 달 가용만큼만 뺐습니다" in captions


@pytest.mark.parametrize("keyed", [False, True])
def test_the_cross_check_numerator_takes_the_input_out(keyed: bool) -> None:
    simulation_cache.get_securement_cross_check.clear()
    app = _run(manual_rows=[("Die Attach", MONTH, 1.0)], keyed_required=keyed)
    _view(app, "확보율 교차검증")
    table = app.dataframe[0].value.set_index("공정")
    assert table.at["Die Attach", "일정기준가용대수"] == pytest.approx(3.5)
    assert table.at["Etch", "일정기준가용대수"] == pytest.approx(6.0)
    captions = " ".join(item.value for item in app.caption)
    assert "입력 비가동 반영(1칸 · 합 1대)" in captions


def test_the_unit_filter_sheet_leaves_the_input_out() -> None:
    """호기 필터 시트는 호기만 더한다 — 기존보유처럼 공정 단위인 입력 비가동은 들지 않는다."""
    app = AppTest.from_function(_filter_app, default_timeout=30)
    app.session_state["manual_rows"] = [("Die Attach", MONTH, 1.0)]
    app.run()
    app.segmented_control(key=RESULT_VIEW_KEY).set_value("분류별 내역").run()
    # 필터 없이는 기존보유(3 + 5) + 가용 호기 셋 − 입력 1.
    assert sheet_value(app, MONTH, ROW_SCHEDULE_AVAILABLE) == 10.0
    app.multiselect(key=UNIT_FILTER_COLUMNS_KEY).set_value(["공정구분"]).run()
    app.multiselect(key=unit_filter_key("공정구분")).set_value(["Line-A"]).run()
    assert not app.exception
    assert sheet_value(app, MONTH, ROW_SCHEDULE_AVAILABLE) == 2.0
    assert any("기존보유·입력 비가동은" in caption.value for caption in app.caption)


def test_the_real_page_takes_the_saved_input_out_of_the_static_comparison(tmp_path: Path) -> None:
    """실제 가용설비 현황 페이지 — 설비 DB 에 넣은 입력 비가동이 Static 대비 일정 시트에 닿는다
    (페이지가 `load_manual_downtime` 으로 읽어 패널에 넘긴다). 빈 설비 DB 는 샘플 fleet·샘플
    기존보유를 보인다(시뮬레이션 DB 가 없어 Static 은 「—」 — 설비 일정 기준 세 줄만 본다)."""
    process = "Wafer_Sorter"
    database_path = tmp_path / "availability.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    repository.save_process_cutoff(
        pd.DataFrame({"공정": [process], "Cutoff일수": [10.0], "비고": [None]})
    )
    page = Path(__file__).resolve().parents[1] / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page, database_path), default_timeout=120).run()
    app = _open_tab(app, "Static 대비 일정")
    app.selectbox(key=PROCESS_FILTER_KEY).select(process).run()
    _view(app, "분류별 내역")

    def schedule(app: AppTest) -> dict[int, float]:
        cells = {month for month, row in sheet_cells(app) if row == ROW_SCHEDULE_AVAILABLE}
        values = {month: sheet_value(app, month, ROW_SCHEDULE_AVAILABLE) for month in cells}
        return {month: value for month, value in values.items() if value is not None}

    before = schedule(app)
    assert before and any(value >= 1.0 for value in before.values()), before
    assert MANUAL_DOWNTIME_BAND not in json.dumps(chart_spec(app, GAP_SHEET_LABEL_CHART_KEY))

    months = period_months(202501, 202812)
    repository.save_manual_downtime(
        {(process, month): 1.0 for month in months},
        processes=[process],
        months=months,
        expected_version=None,
    )
    clear_manual_downtime_cache()
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    after = schedule(app)
    for month, value in before.items():
        assert after[month] == pytest.approx(max(value - 1.0, 0.0), abs=0.011), month
    assert sheet_value(app, min(before), ROW_SCHEDULE_LENT) is not None
    assert MANUAL_DOWNTIME_BAND in json.dumps(
        chart_spec(app, GAP_SHEET_LABEL_CHART_KEY), ensure_ascii=False
    )
    clear_equipment_repository()
