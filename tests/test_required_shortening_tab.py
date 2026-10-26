# Purpose: 필요 단축 일정 화면의 그림·목표·공정 필터·CSV·공용 조건·표시명·시나리오 없음을 검사한다.

"""필요 단축 일정 화면(AppTest) — 가용설비 현황의 탭이던 것을 실행 관리 아래 별도 화면으로
뗐다(2026-10-18).

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
import pytest
import streamlit.elements.lib.policies as policies
from shortening_script import shortening_script
from streamlit.testing.v1 import AppTest

import capa_simulation.components.required_shortening_panel as required_shortening_panel
from capa_simulation.components.required_shortening_panel import (
    SHORTENING_END_KEY,
    SHORTENING_LEVEL_KEY,
    SHORTENING_PROCESS_KEY,
    SHORTENING_START_KEY,
    _card_table,
    _LobRows,
    _unit_row,
)
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
from capa_simulation.components.shortening_board import (
    BOARD_ORDER_KEY,
    HIGHLIGHT_FROM_DETAIL,
    HIGHLIGHT_OFF_KEY,
    SHORTENING_HIGHLIGHT_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    empty_downtime_schedule,
    empty_equipment_baseline,
)
from capa_simulation.services.equipment_samples import sample_equipment_master
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    LEVEL_COLUMN,
    PROCESS_MONTH_EXPORT_COLUMNS,
    STATUS_EXPIRED,
    STATUS_NEW_LIMIT,
    STATUS_SHORTENED,
    UNIT_EXPORT_COLUMNS,
)
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.shortening_filter_profile import ShorteningFilterProfile
from capa_simulation.services.shortening_watch import ORDER_LARGEST_GAP
from capa_simulation.upeh_assumption_state import (
    UPEH_ASSUMPTION_END_KEY,
    UPEH_ASSUMPTION_PERCENT_KEY,
    UPEH_ASSUMPTION_START_KEY,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "required_shortening.py"


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
    sidebar_last: int | None = None,
    labels: dict[str, str] | None = None,
) -> str:
    return shortening_script(
        database_path,
        PAGE,
        fail_scenario=fail_scenario,
        past_months=past_months,
        sidebar_first=sidebar_first,
        sidebar_last=sidebar_last,
        labels=labels,
    )


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
    sidebar_last: int | None = None,
    labels: dict[str, str] | None = None,
) -> AppTest:
    script = _script(
        database_path,
        fail_scenario=fail_scenario,
        past_months=past_months,
        sidebar_first=sidebar_first,
        sidebar_last=sidebar_last,
        labels=labels,
    )
    return AppTest.from_string(script, default_timeout=120).run()


def _html(app: AppTest) -> str:
    return "\n".join(str(element.proto.body) for element in app.get("html"))


def _cards(app: AppTest) -> list[str]:
    body = _html(app)
    return [
        chunk.split('"', 1)[0] for chunk in body.split('<section class="shk-card" aria-label="')[1:]
    ]


def test_the_page_draws_kpis_the_plan_summary_and_process_cards(tmp_path: Path) -> None:
    app = _run(_database(tmp_path))

    assert not app.exception, [element.message for element in app.exception]
    # 별도 화면이라 가용설비 현황의 탭 묶음(Main·Static 대비 일정·Qual 마감 계산기·Preference·
    # RawData)이 없다.
    assert not [tab for tab in app.tabs if tab.label.endswith((" Main", " RawData"))]
    body = _html(app)
    assert "부족 공정" in body and "신규 필요" in body
    assert "계획 · LOB 요약" in body
    assert "일정 기준 B/N 확보율 현재" in body and "일정 기준 B/N 확보율 단축 후" in body
    assert "Dynamic" not in body
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


def test_the_page_offers_three_csvs_with_the_unit_schedule(tmp_path: Path) -> None:
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


def test_a_missing_scenario_stops_with_a_notice(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    app = _run(database_path, fail_scenario=True)

    assert not app.exception
    warnings = " ".join(str(item.value) for item in app.warning)
    assert "소요대수를 읽지 못해" in warnings, warnings
    assert "활성 시나리오가 없습니다" in warnings
    assert not _cards(app)
    clear_equipment_repository()


def test_a_period_outside_the_scenario_data_stops_with_the_data_range(tmp_path: Path) -> None:
    """조회기간이 시나리오 데이터 밖이면 다른 계산 화면처럼 데이터 범위를 알리고 멈춘다.

    소요대수가 하나도 없는 기간인데 계획을 세우면 맞댈 공정이 비어 「공정소분류가 시나리오
    공정명과 같은지 확인하세요」로 엉뚱한 원인(이름 불일치)을 가리켰다. 범위 밖 달이 시작 월·끝 월
    선택지(공용 프로필에 저장되는 값)로 서지도 않는다.
    """
    months = _months()
    app = _run(
        _database(tmp_path),
        sidebar_first=_shift(months[-1], 3),
        sidebar_last=_shift(months[-1], 6),
    )

    assert not app.exception, [element.message for element in app.exception]
    errors = " ".join(str(item.value) for item in app.error)
    assert "선택 범위에 소요대수 산출 기준이 없습니다." in errors, errors
    assert f"(데이터 범위 {month_label(months[0])}–{month_label(months[-1])})" in errors, errors
    infos = " ".join(str(item.value) for item in app.info)
    assert "같은 이름으로 함께 있는 공정" not in infos, infos
    assert not [expander.label for expander in app.expander if "맞대지 못한 공정" in expander.label]
    assert not {"시작 월", "끝 월"} & {widget.label for widget in app.sidebar.selectbox}
    assert not _cards(app)
    clear_equipment_repository()


def test_a_period_partly_before_the_scenario_data_still_plans(tmp_path: Path) -> None:
    """조회기간이 데이터와 일부만 겹치면 지금처럼 겹친 달로 좁혀 계획을 세운다."""
    months = _months()
    app = _run(_database(tmp_path), sidebar_first=_shift(months[0], -6))

    assert not app.exception, [element.message for element in app.exception]
    assert not app.error, [str(item.value) for item in app.error]
    assert list(app.selectbox(key=SHORTENING_START_KEY).options) == [
        month_label(month) for month in months
    ]
    assert _cards(app)
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
    blank = ["반입일정", "Qual일정", "Qual상태", "정지일정", "반출/이설일정", "X좌표", "Y좌표"]
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

    기여 시작일·늘어난 환산대수·모듈 수는 줄에서 빠지고 풍선에 남는다. 올해 날짜는 연도 없이 적는다.
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

    markup = _unit_row(row, axis, "", today=date(2026, 10, 8))
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


def test_the_shortfall_cell_puts_the_after_value_and_the_status_on_separate_lines() -> None:
    """과부족 칸 둘째 줄은 「→ 단축 후」 한 줄, 상태 글(기한 지남 · 남은 날 부족)은 그 아래 한
    줄이다(2026-10-24 사용자 결정 2-3 (가)) — 한 줄로 이으면 `nowrap` 이라 84px 달 칸을 넘어 옆
    달에 얹혔다."""
    months = [202611, 202612, 202701]

    def row(gap: float, after: float, status: str) -> dict[str, object]:
        return {
            "가용대수": 10.0,
            "단축후가용대수": 10.0,
            "소요대수": 12.0,
            "확보율": 10 / 12,
            "과부족": gap,
            "단축후과부족": after,
            "상태": status,
        }

    markup = _card_table(
        {
            202611: row(-102.63, -102.63, STATUS_EXPIRED),
            202612: row(-3.5, -1.2, STATUS_NEW_LIMIT),
            202701: row(-2.0, 0.0, STATUS_SHORTENED),
        },
        months,
        1.0,
        SecurementThresholds(1.0, 0.9),
    )

    assert (
        '<span class="shk-sub">→ −102.63</span><span class="shk-sub">기한 지남</span></div>'
        in markup
    )
    assert (
        '<span class="shk-sub">→ −1.20</span><span class="shk-sub">남은 날 부족</span></div>'
        in markup
    )
    assert " · 기한 지남" not in markup and " · 남은 날 부족" not in markup
    # 상태 글이 없는 부족 칸도 그 줄 자리를 비워 둔다 — 칸은 세로 가운데 맞춤이라 줄 수가 갈리면
    # 같은 줄 부족 칩의 높이가 어긋난다(10-24 리뷰).
    assert (
        '<span class="shk-sub">→ +0.00</span>'
        '<span class="shk-sub" aria-hidden="true">&nbsp;</span></div>' in markup
    )
    assert {len(lines) for lines in _shortfall_cells(markup)} == {2}


def _shortfall_cells(markup: str) -> list[list[str]]:
    """카드 표 과부족 줄의 부족 칸(빨간 칩)마다 큰 숫자 아래 줄들."""
    return [
        re.findall(r'<span class="shk-sub"[^>]*>(.*?)</span>', cell)
        for cell in re.findall(
            r'<div title="[^"]*"><span class="shk-num shk-short">.*?</div>', markup
        )
    ]


def test_shortfall_chips_in_one_card_keep_one_height() -> None:
    """한 카드 과부족 줄의 부족 칸은 줄 수가 같다 — 상태 글 줄이 하나라도 서면 모든 부족 칸이 그 줄
    자리를 갖고, 아무 달에도 상태 글이 없으면 「→ 단축 후」 한 줄 그대로다."""
    months = [202611, 202612, 202701]

    def row(gap: float, status: str) -> dict[str, object]:
        return {
            "가용대수": 10.0,
            "단축후가용대수": 10.0,
            "소요대수": 12.0,
            "확보율": 10 / 12,
            "과부족": gap,
            "단축후과부족": gap + 1,
            "상태": status,
        }

    thresholds = SecurementThresholds(1.0, 0.9)
    mixed = _card_table(
        {
            202611: row(-0.02, STATUS_EXPIRED),
            202612: row(-0.17, STATUS_SHORTENED),
            202701: row(0.5, STATUS_SHORTENED),
        },
        months,
        1.0,
        thresholds,
    )
    plain = _card_table(
        {202611: row(-0.02, STATUS_SHORTENED), 202612: row(-0.17, STATUS_SHORTENED)},
        months,
        1.0,
        thresholds,
    )

    assert _shortfall_cells(mixed) == [["→ +0.98", "기한 지남"], ["→ +0.83", "&nbsp;"]]
    assert _shortfall_cells(plain) == [["→ +0.98"], ["→ +0.83"]]
    assert "&nbsp;" not in plain
    # 부족이 아닌 달은 숫자 하나 그대로다.
    assert '<div><span class="shk-num">+0.50</span></div>' in mixed


def test_a_row_date_in_another_year_carries_its_year() -> None:
    """해가 다른 날짜만 `YY.MM.DD` 로 적는다(2026-10-08 사용자 결정). 「기존 02.25 → 단축
    10.08」 처럼 해를 넘는 단축이 거꾸로 읽히고, 2027·2028 의 「필요 09.21」·「필요 09.22」 가 같은
    꼴로 보였다."""
    axis = (date(2026, 10, 1), date(2028, 12, 1))
    today = date(2026, 10, 8)
    shortened: dict[str, object] = {
        "호기": "SMP-LG-11",
        "구분": KIND_SHORTENED,
        "기존 Qual": date(2027, 2, 25),
        "목표 Qual": date(2026, 10, 8),
        "단축일수": 140,
        "늘어난 환산대수": 1.0,
        "모듈 수": None,
        "해소 기여 월": "26.11",
    }
    virtual: dict[str, object] = {
        "호기": "추가3",
        "구분": KIND_NEW,
        "기존 Qual": None,
        "목표 Qual": date(2028, 9, 22),
        "단축일수": None,
        "늘어난 환산대수": 0.3,
        "모듈 수": None,
        "해소 기여 월": "28.10",
    }

    shortened_visible = _visible(_unit_row(shortened, axis, "", today=today))
    virtual_visible = _visible(_unit_row(virtual, axis, "", today=today))

    assert (
        '<span class="shk-muted">기존</span> 27.02.25 → <span class="shk-muted">단축</span> 10.08'
    ) in shortened_visible
    assert '<span class="shk-muted">필요</span> 28.09.22' in virtual_visible


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

    markup = _unit_row(row, axis, "", today=date(2026, 10, 8))
    visible = _visible(markup)

    assert '<span class="shk-muted">필요</span> 11.03' in visible
    assert '<div class="shk-result"><span class="shk-new">신규</span></div>' in visible
    assert "−" not in visible and "기여" not in visible and "+0.26대" not in visible
    assert "신규 필요 Qual 2026-11-03 · 기여 시작 2026-11-04 · 늘어난 환산대수 +0.26대" in markup


# ------------------------------------------------------- 공용 조회 조건 프로필(0019)


def _processes() -> list[str]:
    return sorted(set(sample_equipment_master()["공정소분류"]))


def _profile(database_path: Path) -> ShorteningFilterProfile:
    return DuckDBEquipmentRepository(database_path).load_shortening_filter_profile()


def test_a_new_session_opens_with_the_shared_filter_profile(tmp_path: Path) -> None:
    """세션에 값이 없으면 공용 프로필로 심는다 — 지금 맞댄 공정에 없는 공정만 빼고(프로필에는
    남는다).

    심기는 프로필에 쓰지 않는다 — 공용 행이라 쓰면 version 이 오르고 남의 선택을 되쓴다.
    """
    database_path = _database(tmp_path)
    months = _months()
    first = _processes()[0]
    repository = DuckDBEquipmentRepository(database_path)
    repository.save_shortening_filter_months(months[1], months[3], source="test")
    repository.save_shortening_filter_processes(
        [first, "ABSENT-PROC"], visible=[first, "ABSENT-PROC"], source="test"
    )

    app = _run(database_path)

    assert not app.exception, [element.message for element in app.exception]
    assert app.session_state[SHORTENING_START_KEY] == months[1]
    assert app.session_state[SHORTENING_END_KEY] == months[3]
    assert app.multiselect(key=SHORTENING_PROCESS_KEY).value == [first]
    assert _cards(app) == [first]
    captions = " ".join(str(item.value) for item in app.sidebar.caption)
    assert "공용 설정" in captions
    assert "ABSENT-PROC" in captions and "공용 설정에는 남습니다" in captions
    stored = _profile(database_path)
    assert stored.version == 2
    assert stored.processes == (first, "ABSENT-PROC")
    clear_equipment_repository()


def test_changing_the_filter_saves_it_for_every_new_session(tmp_path: Path) -> None:
    """바꾸면 그 자리에서 저장하고, 새 세션(다른 사용자)은 그 값으로 연다. 기간·공정은 따로 쓴다."""
    database_path = _database(tmp_path)
    months = _months()
    app = _run(database_path)
    assert _profile(database_path).version == 0, "처음 열기만 해서는 쓰지 않는다"

    app = app.selectbox(key=SHORTENING_START_KEY).set_value(months[2]).run()
    assert not app.exception
    stored = _profile(database_path)
    assert (stored.start_month, stored.end_month, stored.processes) == (months[2], months[-1], ())
    assert stored.version == 1

    chosen = list(app.multiselect(key=SHORTENING_PROCESS_KEY).options)[1]
    app = app.multiselect(key=SHORTENING_PROCESS_KEY).set_value([chosen]).run()
    assert not app.exception
    stored = _profile(database_path)
    assert (stored.start_month, stored.processes) == (months[2], (chosen,))
    assert stored.version == 2

    # 목표 확보율은 공용 설정이 아니다 — 바꿔도 쓰지 않는다.
    app = app.selectbox(key=SHORTENING_LEVEL_KEY).set_value(0.9).run()
    assert _profile(database_path).version == 2

    other = _run(database_path)
    assert not other.exception
    assert other.session_state[SHORTENING_START_KEY] == months[2]
    assert other.session_state[SHORTENING_END_KEY] == months[-1]
    assert other.multiselect(key=SHORTENING_PROCESS_KEY).value == [chosen]
    assert _cards(other) == [chosen]

    # 비우면 「미선택 = 목표 미달 공정 전체」가 공용 설정이 된다.
    cleared = other.multiselect(key=SHORTENING_PROCESS_KEY).set_value([]).run()
    assert not cleared.exception
    assert _profile(database_path).processes == ()
    clear_equipment_repository()


def test_a_profile_month_outside_the_options_falls_back_to_the_default(tmp_path: Path) -> None:
    """저장된 달이 지금 고를 수 없는 달이면 코드 기본값(조회기간 전체)으로 연다. 프로필은
    그대로다."""
    database_path = _database(tmp_path)
    months = _months()
    early, late = _shift(months[0], -24), _shift(months[-1], 24)
    DuckDBEquipmentRepository(database_path).save_shortening_filter_months(
        early, late, source="test"
    )

    app = _run(database_path)

    assert not app.exception
    assert app.session_state[SHORTENING_START_KEY] == months[0]
    assert app.session_state[SHORTENING_END_KEY] == months[-1]
    stored = _profile(database_path)
    assert (stored.start_month, stored.end_month, stored.version) == (early, late, 1)
    clear_equipment_repository()


def test_seeding_the_filter_raises_no_widget_value_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """심은 세션 값과 위젯 기본값(`index=`·`default=`)을 함께 주면 Streamlit 이 경고한다(AGENTS
    9장).

    경고는 프로세스에 한 번만 찍히므로 그 표시를 되돌려 놓고 잰다.
    """
    database_path = _database(tmp_path)
    months = _months()
    first = _processes()[0]
    repository = DuckDBEquipmentRepository(database_path)
    repository.save_shortening_filter_months(months[1], months[2], source="test")
    repository.save_shortening_filter_processes([first], visible=[first], source="test")
    warnings: list[object] = []
    monkeypatch.setattr(policies, "_shown_default_value_warning", False)
    monkeypatch.setattr(policies._LOGGER, "warning", lambda *args, **_kwargs: warnings.append(args))

    app = _run(database_path)
    app = app.selectbox(key=SHORTENING_END_KEY).set_value(months[4]).run()

    assert not app.exception
    assert warnings == []
    clear_equipment_repository()


# ------------------------------------------------------- 계획 · LOB 요약 글 넘침


def _class_style(body: str, classes: list[str]) -> dict[str, str]:
    """`<style>` 의 한 클래스 규칙(`.이름 {…}`)을 적힌 차례대로 합친 선언 — 뒤 규칙이 앞 것을
    덮는다(같은 우선순위의 CSS 차례)."""
    wanted = {f".{name}" for name in classes}
    style: dict[str, str] = {}
    for selector, block in re.findall(r"(?m)^(\.[\w-]+) \{([^{}]*)\}", body):
        if selector in wanted:
            for declaration in block.split(";"):
                if ":" in declaration:
                    name, value = declaration.split(":", 1)
                    style[name.strip()] = value.strip()
    return style


def _lob_section(body: str) -> str:
    return body.split('aria-label="계획 · LOB 요약"', 1)[1].split("</section>", 1)[0]


def test_bn_process_names_end_inside_their_month_cell(tmp_path: Path) -> None:
    """B/N 아래 공정 이름은 달 칸(84px) 안에서 말줄임으로 끝나고 전체 이름은 풍선이다 — `nowrap`
    만 두면 칸을 넘어 옆 달 이름과 포개졌다(2026-10-26 E2E — 1440px 에서 이름 60개 가운데 41개)."""
    app = _run(_database(tmp_path))

    assert not app.exception, [element.message for element in app.exception]
    body = _html(app)
    names = re.findall(r'<span class="([^"]*)" title="([^"]*)">([^<]*)</span>', _lob_section(body))
    assert names
    for classes, title, text in names:
        assert title == text
        style = _class_style(body, classes.split())
        assert style.get("white-space") == "nowrap"
        assert style.get("max-width") == "100%"
        assert style.get("overflow") == "hidden"
        assert style.get("text-overflow") == "ellipsis"
    clear_equipment_repository()


def test_a_long_plan_error_wraps_inside_the_lob_panel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """계획 값을 못 읽은 까닭은 길 수 있다 — 한 줄(`nowrap`)이면 상자 오른쪽 밖으로 나가므로 줄을
    바꾼다."""
    reason = "까닭 " * 80
    monkeypatch.setattr(
        required_shortening_panel, "_lob_rows", lambda _context, _months: _LobRows({}, {}, reason)
    )
    app = _run(_database(tmp_path))

    assert not app.exception, [element.message for element in app.exception]
    body = _html(app)
    found = re.search(r'<div class="([^"]*)">계획 값을 읽지 못했습니다 — ([^<]*)</div>', body)
    assert found is not None
    assert found.group(2) == reason
    style = _class_style(body, found.group(1).split())
    assert style.get("white-space") == "normal"
    clear_equipment_repository()


# ------------------------------------------------------- 공정 표시명(Proc Rename)


def test_process_display_names_label_the_screen_but_values_stay_original(tmp_path: Path) -> None:
    """선택지·카드 제목·B/N 공정은 표시명이고, 세션·공용 프로필·CSV `공정` 은 원본이다."""
    database_path = _database(tmp_path)
    first, second = _processes()[:2]
    DuckDBEquipmentRepository(database_path).save_shortening_filter_processes(
        [first], visible=[first], source="test"
    )
    labels = {first: "표시-첫공정", second: "표시-둘째공정"}

    app = _run(database_path, labels=labels)

    assert not app.exception, [element.message for element in app.exception]
    picker = app.multiselect(key=SHORTENING_PROCESS_KEY)
    assert "표시-첫공정" in picker.options and first not in picker.options
    assert picker.value == [first]
    assert app.session_state[SHORTENING_PROCESS_KEY] == [first]
    assert _cards(app) == ["표시-첫공정"]
    body = _html(app)
    assert f'title="원본 공정명 {first}"' in body
    # 고른 공정 하나라 B/N 아래 공정 이름은 그 공정이다.
    assert '<span class="shk-sub shk-bn-name" title="표시-첫공정">표시-첫공정</span>' in body
    _, units = _csv(app, "equipment_shortening_units_csv")
    assert set(units["공정"]) <= {first}
    for key in (
        "equipment_shortening_units_csv",
        "equipment_shortening_units_all_levels_csv",
        "equipment_shortening_months_csv",
    ):
        data = app.session_state["captured_downloads"][key]["data"]
        assert "표시-" not in data.decode("utf-8-sig"), key

    changed = picker.set_value([second]).run()
    assert not changed.exception
    assert _cards(changed) == ["표시-둘째공정"]
    assert _profile(database_path).processes == (second,)
    clear_equipment_repository()


def test_a_display_name_equal_to_another_process_still_saves_the_chosen_process(
    tmp_path: Path,
) -> None:
    """첫 공정의 표시명이 둘째 공정의 원본 이름과 같으면 multiselect 가 같은 글자 둘 중 첫째로
    돌아와 다른 공정이 세션·공용 프로필에 들어갔다(병합 전 리뷰). 「표시명 (원본)」 으로 가른다."""
    database_path = _database(tmp_path)
    first, second = _processes()[:2]

    app = _run(database_path, labels={first: second})

    assert not app.exception, [element.message for element in app.exception]
    picker = app.multiselect(key=SHORTENING_PROCESS_KEY)
    assert f"{second} ({first})" in picker.options and second in picker.options
    # 같은 글자 둘 중 어느 쪽이 먼저든 한쪽은 틀렸다 — 둘 다 골라 본다.
    for chosen in (second, first):
        app = app.multiselect(key=SHORTENING_PROCESS_KEY).set_value([chosen]).run()
        assert not app.exception
        assert app.session_state[SHORTENING_PROCESS_KEY] == [chosen]
        assert _profile(database_path).processes == (chosen,)
    clear_equipment_repository()


def test_the_unmatched_list_keeps_the_original_names(tmp_path: Path) -> None:
    """「맞대지 못한 공정」은 마스터·Cut-off 이름을 맞추라는 안내라 원본 이름이다."""
    database_path = _database(tmp_path)
    repository = DuckDBEquipmentRepository(database_path)
    processes = _processes()
    # 첫 공정의 Cut-off 를 빼면 그 공정은 시나리오 쪽에만 남는다.
    repository.save_process_cutoff(
        pd.DataFrame(
            {
                "공정": processes[1:],
                "Cutoff일수": [10.0] * (len(processes) - 1),
                "비고": [None] * (len(processes) - 1),
            }
        )
    )

    app = _run(database_path, labels={processes[0]: "표시-빠진공정"})

    assert not app.exception
    texts = " ".join(str(item.value) for item in app.text)
    assert processes[0] in texts and "표시-빠진공정" not in texts
    clear_equipment_repository()


# ------------------------------------------------------------------ UPEH 가정


def _assumed(tmp_path: Path, percent: int = 150) -> AppTest:
    """조건 카드의 UPEH 가정을 `percent`% · 조회 달 전체로 둔 화면."""
    app = _run(_database(tmp_path))
    months = _months()
    app.session_state[UPEH_ASSUMPTION_PERCENT_KEY] = percent
    app.session_state[UPEH_ASSUMPTION_START_KEY] = months[0]
    app.session_state[UPEH_ASSUMPTION_END_KEY] = months[-1]
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    return app


_ASSUMPTION_HINT = "켜져 있습니다 — 이 화면"


def test_the_upeh_assumption_sits_in_the_condition_card_and_keeps_the_screen_official(
    tmp_path: Path,
) -> None:
    """가정을 켜도 이 화면(보기·CSV 세 벌·기준선·진척 비교)은 공식 계획이다 — 머리 아래 한 줄이
    알리고 가정의 효과는 공정 Capa 상세로 보낸다. 공식 대 가정 비교 보기(토글)는 없다. 입력은 조건
    카드(사이드바) 끝 「이 세션만」 묶음이다(공정 Capa 상세와 같은 세션 칸)."""
    app = _assumed(tmp_path)
    assert {"UPEH 적용 시작", "UPEH 적용 끝"} <= {box.label for box in app.sidebar.selectbox}
    assert app.sidebar.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).value == 150
    hint = [str(item.value) for item in app.caption if _ASSUMPTION_HINT in str(item.value)]
    assert hint and "UPEH 가정 150%" in hint[0] and "공식 계획" in hint[0]
    assert "공정 Capa 상세" in hint[0]
    assert not any("UPEH 가정 비교" in str(toggle.label) for toggle in app.toggle)
    assert "UPEH 가정 비교" not in _html(app)
    _, units = _csv(app, "equipment_shortening_units_csv")
    assert "UPEH 가정" not in units.columns
    captured = app.session_state["captured_downloads"]["equipment_shortening_units_csv"]
    assert "upeh" not in str(captured["file_name"])
    clear_equipment_repository()


def test_the_upeh_assumption_notice_picks_the_particle_by_the_end_month(tmp_path: Path) -> None:
    """알림의 주격 조사는 구간 끝 달의 끝소리로 고른다 — 「27-06 가」 가 아니라 「27-06이」.

    끝 두 자리를 읽은 끝 글자(영·일·삼·육·칠·팔)에 받침이 있으면 「이」, 없으면 「가」 다.
    """
    app = _assumed(tmp_path)
    end = _months()[-1]
    span_end = f"{end // 100 % 100:02d}-{end % 100:02d}"
    particle = "이" if span_end[-1] in "013678" else "가"
    hint = [str(item.value) for item in app.caption if _ASSUMPTION_HINT in str(item.value)]
    assert hint and f"–{span_end}{particle} 켜져 있습니다" in hint[0]
    clear_equipment_repository()


def test_a_baseline_is_not_saved_while_an_assumption_is_on() -> None:
    """가정이 켜진 동안 기준선 저장을 거절한다(미저장 시나리오 편집과 같은 꼴). 100% 면 거절하지
    않는다.

    샘플 fleet 화면은 그 전에 샘플이라 거절하므로 저장 문맥 함수를 바로 본다."""
    from types import SimpleNamespace
    from typing import Any, cast

    from capa_simulation.components.required_shortening_panel import _save_context
    from capa_simulation.services.upeh_assumption import UpehAssumption

    context = cast(
        Any, SimpleNamespace(reference_version=1, active_scenario={"content_token": "token"})
    )
    plan = cast(Any, object())

    def refusal(percent: int) -> str | None:
        save = _save_context(
            plan,
            today=date(2026, 6, 1),
            context=context,
            database_path="equipment.duckdb",
            revision=(None, None),
            refusal=None,
            assumption=UpehAssumption(percent, 202607, 202612),
        )
        assert save is not None
        return save.refusal

    refused = refusal(120)
    assert refused is not None
    assert "UPEH 가정 120%" in refused and "100% 로 되돌린 뒤" in refused
    assert refusal(100) is None


def test_an_assumption_outside_the_card_months_reads_the_same_one_line(tmp_path: Path) -> None:
    """적용 구간이 카드 기간(공용 설정)과 겹치지 않아도 같은 한 줄이다 — 이 화면은 어느 쪽이든
    가정을 걸지 않는다."""
    database_path = _database(tmp_path)
    months = _months()
    DuckDBEquipmentRepository(database_path).save_shortening_filter_months(
        months[0], months[1], source="test"
    )
    app = _run(database_path)
    app.session_state[UPEH_ASSUMPTION_PERCENT_KEY] = 120
    app.session_state[UPEH_ASSUMPTION_START_KEY] = months[3]
    app.session_state[UPEH_ASSUMPTION_END_KEY] = months[-1]
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    captions = [str(item.value) for item in app.caption]
    assert any(_ASSUMPTION_HINT in caption and "UPEH 가정 120%" in caption for caption in captions)
    assert not any("적용된 달 없음" in caption for caption in captions)
    clear_equipment_repository()


def test_at_100_percent_there_is_no_assumption_line(tmp_path: Path) -> None:
    app = _run(_database(tmp_path))
    assert not any(_ASSUMPTION_HINT in str(item.value) for item in app.caption)
    assert not any("UPEH 가정 비교" in str(toggle.label) for toggle in app.toggle)
    clear_equipment_repository()


# ------------------------------------------------------- 진척 관리 한 페이지(2026-10-22)

DETAIL_LINK_FALLBACK = "사이드바에서 공정 Capa 상세에서 근거 보기"


def _captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.caption]


def _board(app: AppTest) -> pd.DataFrame:
    boards = [
        frame
        for frame in app.dataframe
        if str(frame.proto.id).split("-", 2)[-1].startswith("equipment_shortening_board_")
    ]
    assert len(boards) == 1, [str(frame.proto.id) for frame in app.dataframe]
    value = boards[0].value
    assert isinstance(value, pd.DataFrame)
    return value


def _highlighted(database_path: Path, process: str) -> AppTest:
    app = AppTest.from_string(_script(database_path), default_timeout=120)
    app.session_state[SHORTENING_HIGHLIGHT_KEY] = (process, HIGHLIGHT_FROM_DETAIL)
    return app.run()


def test_the_page_states_its_identity_and_draws_the_progress_board(tmp_path: Path) -> None:
    """머리말은 이 화면의 정체성, KPI 아래·카드 위에 공정 진척 보드(카드와 같은 공정·차례)와 기한
    임박, 이행 지연 안내가 선다. 샘플 fleet 에서는 상세 근거 링크를 숨긴다(상세는 저장본만 본다)."""
    app = _run(_database(tmp_path))

    assert not app.exception, [element.message for element in app.exception]
    captions = _captions(app)
    assert any("단축이 필요한 공정 전부의 진척 관리 한 페이지" in text for text in captions)
    assert "**공정 진척 보드**" in [str(item.value) for item in app.markdown]
    board = _board(app)
    cards = _cards(app)
    assert list(board["공정"]) == cards and cards
    assert "기준선 대비" not in board.columns
    assert {"첫 부족 달", "월 최대 부족", "당길 호기", "가장 이른 목표 Qual"} <= set(board.columns)
    assert app.selectbox(key=BOARD_ORDER_KEY).label == "카드 차례"
    assert any(widget.label == "기한 임박(일)" for widget in app.number_input)
    # 아이콘을 단 접는 상자는 AppTest 에서 `status` 로 잡힌다.
    assert any(str(box.label).startswith("기한 임박 ") for box in app.status)
    assert any("이행 지연은 「진척 비교」 에서 기준선을 고르면" in text for text in captions)
    assert DETAIL_LINK_FALLBACK not in captions
    clear_equipment_repository()


def test_the_card_order_follows_the_board_order(tmp_path: Path) -> None:
    app = _run(_database(tmp_path))
    app = app.selectbox(key=SHORTENING_LEVEL_KEY).set_value(1.3).run()
    app = app.selectbox(key=BOARD_ORDER_KEY).set_value(ORDER_LARGEST_GAP).run()

    assert not app.exception, [element.message for element in app.exception]
    board = _board(app)
    gaps = [float(value) for value in board["월 최대 부족"]]
    assert gaps == sorted(gaps, reverse=True)
    assert list(board["공정"]) == _cards(app)
    clear_equipment_repository()


def test_a_highlight_from_the_detail_page_tops_the_cards_without_writing_the_shared_filter(
    tmp_path: Path,
) -> None:
    """공정 Capa 상세에서 옮겨 온 공정은 카드 맨 위(테두리·배지)다. 공용 설정의 공정 선택 밖이면 그
    까닭을 적고, 공정 필터(0019 세션 칸·공용 프로필)는 건드리지 않는다 — 강조를 꺼도 그대로다."""
    database_path = _database(tmp_path)
    processes = _processes()
    shared, outside = processes[0], processes[-1]
    DuckDBEquipmentRepository(database_path).save_shortening_filter_processes(
        [shared], visible=[shared], source="test"
    )
    before = _profile(database_path)

    app = _highlighted(database_path, outside)

    assert not app.exception, [element.message for element in app.exception]
    assert _cards(app) == [outside, shared]
    body = _html(app)
    assert 'data-highlight="공정 Capa 상세에서 연 공정"' in body
    assert "공용 설정의 공정 선택 밖 — KPI·CSV 에 들지 않음" in " ".join(_captions(app))
    assert app.multiselect(key=SHORTENING_PROCESS_KEY).value == [shared]
    # KPI·CSV 는 공용 설정의 공정만이다.
    _, units = _csv(app, "equipment_shortening_units_csv")
    assert set(units["공정"]) <= {shared}
    assert _profile(database_path) == before

    app = app.button(key=HIGHLIGHT_OFF_KEY).click().run()
    assert not app.exception
    assert SHORTENING_HIGHLIGHT_KEY not in app.session_state
    assert _cards(app) == [shared]
    assert "data-highlight" not in _html(app)
    assert _profile(database_path) == before
    clear_equipment_repository()


def test_an_unmatched_highlight_says_there_is_no_card(tmp_path: Path) -> None:
    app = _highlighted(_database(tmp_path), "DEMO-NOT-MATCHED")

    assert not app.exception, [element.message for element in app.exception]
    assert any("맞댄 공정이 아니라 카드가 없습니다" in text for text in _captions(app))
    assert "DEMO-NOT-MATCHED" not in _cards(app)
    clear_equipment_repository()


def test_saved_fleet_cards_link_to_the_detail_page_and_carry_the_manager(tmp_path: Path) -> None:
    """저장된 호기 마스터면 카드마다 「공정 Capa 상세에서 근거 보기」(단독 실행은 글자로 물러선다)가
    서고, 설비 마스터 담당자가 호기 줄 풍선과 「호기별」 CSV 에 실린다."""
    database_path = _database(tmp_path)
    DuckDBEquipmentRepository(database_path).save_snapshot(
        empty_equipment_baseline(),
        sample_equipment_master(),
        empty_downtime_schedule(),
        note="상세 링크 시험",
    )

    app = _run(database_path)

    assert not app.exception, [element.message for element in app.exception]
    cards = _cards(app)
    assert cards
    assert _captions(app).count(DETAIL_LINK_FALLBACK) == len(cards)
    assert "담당자 샘플 담당자" in _html(app)
    _, units = _csv(app, "equipment_shortening_units_csv")
    shortened = units.loc[units["구분"].eq(KIND_SHORTENED)]
    assert set(shortened["담당자"]) == {"샘플 담당자"}
    clear_equipment_repository()
