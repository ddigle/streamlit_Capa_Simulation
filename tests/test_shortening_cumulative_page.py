# Purpose: 필요 단축 일정 「누적 진척」 띠 · 주차별 그림 · 설정 팝업의 기록과 목표를 화면으로 본다.

"""필요 단축 일정 「누적 진척」(2026-11-20 사용자 보드 답 누적-1 A · 누적-2 c · 누적-3 a · 누적-4
「한 줄 기록」 · 누적-5 a).

화면은 `test_required_shortening_tab` 의 흉내 스크립트로 돈다(빈 설비 DB 는 샘플 fleet, 저장본
DB 는 `test_shortening_progress_tab._saved_database`). 일수는 합성 예시(DEMO)다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from alert_marks import flashed, texts
from streamlit.testing.v1 import AppTest
from test_required_shortening_tab import _database, _html, _run
from test_shortening_progress_tab import _saved_database

from capa_simulation.components.required_shortening_panel import SHORTENING_DIALOG_HOST
from capa_simulation.components.shortening_cumulative import (
    _FILL_BUTTON_KEY,
    _GOAL_CLEAR_KEY,
    _GOAL_SAVE_KEY,
    _RECORD_DELETE_KEY,
    _RECORD_SAVE_KEY,
    _WEEKS_BUTTON_KEY,
    CUMULATIVE_BUTTON_KEY,
    CUMULATIVE_DIALOG,
    CUMULATIVE_TITLE,
    SCREEN_TOTAL_KEY,
    ScreenTotal,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.shortening_progress_log import ProgressGoal, ProgressWeek

THIS_WEEK = ProgressWeek.of(date.today())


def _seed(
    database_path: Path, entries: list[tuple[ProgressWeek, int]], goal: ProgressGoal | None = None
) -> None:
    repository = DuckDBEquipmentRepository(database_path)
    for week, days in entries:
        repository.save_shortening_progress_entry(week, days, expected_days=None)
    if goal is not None:
        repository.save_shortening_progress_goal(goal, expected_version=None)


def _strip(app: AppTest) -> str:
    body = _html(app)
    start = body.index('<div class="shk-cum"')
    return body[start : body.index("</div>", start)]


def _charts(app: AppTest) -> list[dict[str, Any]]:
    return [json.loads(chart.proto.spec) for chart in app.get("plotly_chart")]


def _number(app: AppTest, label: str) -> Any:
    return next(widget for widget in app.number_input if widget.label == label)


def _open(app: AppTest) -> AppTest:
    app.button(key=CUMULATIVE_BUTTON_KEY).click().run()
    assert not app.exception
    assert app.session_state[SHORTENING_DIALOG_HOST.open_key] == CUMULATIVE_DIALOG
    return app


def test_without_records_the_strip_stands_with_marks_and_a_locked_weeks_button(
    tmp_path: Path,
) -> None:
    """누적-5 a — 진척 비교를 고르지 않아도 머리 한 줄이 KPI 위에 선다. 기록 · 목표가 없으면 점선
    표지(설계 규칙 UI-LAY-10)이고 「주차별」 은 잠겨 까닭 풍선을 단다(UI-INP-07)."""
    app = _run(_database(tmp_path))
    assert not app.exception
    strip = _strip(app)
    assert "기록 없음" in strip and "최종 목표 미지정" in strip
    body = _html(app)
    assert body.index('class="shk-cum"') < body.index('class="shk-kpis"')
    weeks = app.button(key=_WEEKS_BUTTON_KEY)
    assert weeks.disabled and "기록이 없습니다" in str(weeks.help)
    # 사이드바 상자 — 상자 = 단추 → 같은 제목 팝업(UI-LAY-01).
    assert CUMULATIVE_TITLE in [button.label for button in app.sidebar.button]
    clear_equipment_repository()


def test_records_draw_the_latest_days_change_and_what_is_left_to_the_goal(tmp_path: Path) -> None:
    """값은 기록 기준 — 마지막 기록 · 그 앞 기록 대비(늘면 ▲ 와 +) · 첫 기록 → 목표 막대와 남은
    일수. 「주차별」 을 누르면 띠 아래에 꺾은선 + 목표선이 펼쳐지고 앱 전체가 다시 돌아도 남는다."""
    database_path = _database(tmp_path)
    _seed(
        database_path,
        [(THIS_WEEK.shifted(-2), 142), (THIS_WEEK.shifted(-1), 120), (THIS_WEEK, 126)],
        ProgressGoal(30, THIS_WEEK.shifted(5)),
    )
    app = _run(database_path)
    assert not app.exception
    strip = _strip(app)
    assert "126일" in strip and THIS_WEEK.label in strip
    assert "지난 기록 대비 ▲ +6일" in strip
    assert f"최종 목표 30일({THIS_WEEK.shifted(5).label})" in strip
    assert "남은 96일" in strip
    assert not _charts(app)

    app.button(key=_WEEKS_BUTTON_KEY).click().run()
    assert not app.exception
    (figure,) = _charts(app)
    line = figure["data"][0]
    assert line["y"] == [142, 120, 126]
    assert line["marker"]["symbol"] == ["circle", "circle", "triangle-up"], "늘어난 주는 ▲"
    rises = figure["data"][1]
    assert rises["text"] == ["+6일"]
    shapes = figure["layout"]["shapes"]
    assert any(shape.get("y0") == 30 and shape.get("y1") == 30 for shape in shapes), "목표선"

    app.run()
    assert len(_charts(app)) == 1, "편 상태는 세션 칸 — 앱 전체 회차에도 남는다"
    app.button(key=_WEEKS_BUTTON_KEY).click().run()
    assert not _charts(app)
    clear_equipment_repository()


def test_this_weeks_value_is_locked_on_the_sample_fleet(tmp_path: Path) -> None:
    """샘플 fleet 은 기준선과 같은 까닭으로 「이번 주 값 넣기」 가 잠긴다 — 손으로는 적는다."""
    app = _open(_run(_database(tmp_path)))
    fill = app.button(key=_FILL_BUTTON_KEY)
    assert fill.disabled and "기준선과 같은 까닭" in str(fill.help)
    assert not app.button(key=_RECORD_SAVE_KEY).disabled
    clear_equipment_repository()


def test_a_record_is_filled_from_the_screen_saved_edited_and_deleted(tmp_path: Path) -> None:
    """「이번 주 값 넣기」 는 본문이 그린 화면 합계로 이번 주 칸을 채우고(고쳐 적을 수 있다) 「기록
    저장」 이 공용 기록에 남긴다. 팝업은 열린 채 띠가 새 값으로 선다(UI-STA-06), 결과는 알림창."""
    database_path, _ = _saved_database(tmp_path)
    app = _run(database_path)
    assert not app.exception
    total = app.session_state[SCREEN_TOTAL_KEY]
    assert isinstance(total, ScreenTotal) and total.refusal is None
    _open(app)

    fill = app.button(key=_FILL_BUTTON_KEY)
    assert not fill.disabled and f"{total.days:,}일" in str(fill.help)
    fill.click().run()
    assert not app.exception
    assert _number(app, "단축 필요일수").value == total.days
    _number(app, "단축 필요일수").set_value(total.days + 5).run()
    app.button(key=_RECORD_SAVE_KEY).click().run()
    assert not app.exception
    log = DuckDBEquipmentRepository(database_path).load_shortening_progress_log()
    assert [(entry.week, entry.days) for entry in log.entries] == [(THIS_WEEK, total.days + 5)]
    assert app.session_state[SHORTENING_DIALOG_HOST.open_key] == CUMULATIVE_DIALOG
    assert f"{total.days + 5:,}일" in _strip(app)
    assert any("누적 진척 기록을 저장했습니다" in text for text in texts(flashed(app)))

    # 같은 값으로 다시 누르면 쓰지 않는다(알림창 「바뀐 것이 없습니다」).
    app.button(key=_RECORD_SAVE_KEY).click().run()
    assert not app.exception
    assert DuckDBEquipmentRepository(database_path).load_shortening_progress_log().days_of(
        THIS_WEEK
    ) == (total.days + 5)

    app.button(key=_RECORD_DELETE_KEY).click().run()
    assert not app.exception
    assert not DuckDBEquipmentRepository(database_path).load_shortening_progress_log().entries
    assert "기록 없음" in _strip(app)
    clear_equipment_repository()


def test_a_record_refuses_a_save_when_someone_else_changed_that_week(tmp_path: Path) -> None:
    """겹친 저장(UI-STA-05) — 팝업이 본 뒤 남이 같은 주를 고쳤으면 쓰지 않고 곁 + 알림창으로
    알린다."""
    database_path, _ = _saved_database(tmp_path)
    app = _open(_run(database_path))
    _number(app, "단축 필요일수").set_value(50).run()
    _seed(database_path, [(THIS_WEEK, 70)])
    clear_equipment_repository()
    app.button(key=_RECORD_SAVE_KEY).click().run()
    assert not app.exception
    assert (
        DuckDBEquipmentRepository(database_path).load_shortening_progress_log().days_of(THIS_WEEK)
        == 70
    )
    assert any("다른 사용자가 먼저" in text for text in texts(flashed(app, "warning")))
    clear_equipment_repository()


def test_the_goal_is_saved_and_cleared_from_the_popup(tmp_path: Path) -> None:
    database_path, _ = _saved_database(tmp_path)
    _seed(database_path, [(THIS_WEEK.shifted(-1), 80), (THIS_WEEK, 60)])
    app = _open(_run(database_path))
    goal_week = THIS_WEEK.shifted(6)
    _number(app, "목표 일수").set_value(30).run()
    next(widget for widget in app.selectbox if widget.label == "목표 주차").set_value(
        goal_week.label
    ).run()
    app.button(key=_GOAL_SAVE_KEY).click().run()
    assert not app.exception
    state = DuckDBEquipmentRepository(database_path).load_shortening_progress_log().goal
    assert (state.goal, state.version) == (ProgressGoal(30, goal_week), 1)
    assert "남은 30일" in _strip(app)

    app.button(key=_GOAL_CLEAR_KEY).click().run()
    assert not app.exception
    state = DuckDBEquipmentRepository(database_path).load_shortening_progress_log().goal
    assert (state.goal, state.version) == (None, 2)
    assert "최종 목표 미지정" in _strip(app)
    clear_equipment_repository()


def test_a_goal_with_only_days_is_refused_beside_the_inputs(tmp_path: Path) -> None:
    database_path, _ = _saved_database(tmp_path)
    app = _open(_run(database_path))
    _number(app, "목표 일수").set_value(30).run()
    app.button(key=_GOAL_SAVE_KEY).click().run()
    assert not app.exception
    assert [item.value for item in app.warning] == ["목표 일수와 목표 주차를 함께 적으세요."]
    assert DuckDBEquipmentRepository(database_path).load_shortening_progress_log().goal.version == 0
    clear_equipment_repository()
