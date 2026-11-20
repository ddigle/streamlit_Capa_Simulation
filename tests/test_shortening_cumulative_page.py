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

import pandas as pd
import pytest
from alert_marks import flashed, texts
from process_board_press import apply_board, board_data, board_options, live_board
from streamlit.testing.v1 import AppTest
from test_required_shortening_tab import _csv, _database, _html, _run, _run_static
from test_shortening_progress_tab import _name_input as _baseline_name
from test_shortening_progress_tab import _progress_cards, _saved_database
from test_shortening_progress_tab import _save_button as _baseline_save

from capa_simulation.components.required_shortening_panel import (
    PROCESS_BOARD_KEY,
    SHORTENING_DIALOG_HOST,
    SHORTENING_PROCESS_KEY,
)
from capa_simulation.components.shortening_cumulative import (
    _FILL_BUTTON_KEY,
    _FILL_KEY,
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
    strip_markup,
)
from capa_simulation.components.shortening_progress_panel import SHORTENING_COMPARE_KEY
from capa_simulation.components.shortening_source import SHORTENING_BASIS_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.required_shortening import KIND_SHORTENED
from capa_simulation.services.shortening_progress_log import (
    PROGRESS_DAYS_MAX,
    ProgressEntry,
    ProgressGoal,
    ProgressGoalState,
    ProgressLog,
    ProgressWeek,
)

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


def test_the_strip_gives_way_from_the_first_record_and_stacks_the_overdue_note() -> None:
    """띠는 한 줄(UI-LAY-13) — 「첫 기록 … →」 과 「최종 목표 …」 가 따로 줄어(앞 글이 먼저, 목표
    칸이 좁으면 컨테이너 질의로 숨김) 목표 글이 남고, 목표 주차 지남은 남은 일수 아래 작은
    줄이다."""
    log = ProgressLog(
        entries=(
            ProgressEntry(ProgressWeek(2026, 40), 2200),
            ProgressEntry(ProgressWeek(2026, 46), 1790),
        ),
        goal=ProgressGoalState(goal=ProgressGoal(600, ProgressWeek(2026, 44)), version=1),
    )
    markup = strip_markup(log, date(2026, 11, 20))
    assert '<span class="shk-cum-route-from">첫 기록 2,200일(26-W40) →</span>' in markup
    assert '<span class="shk-cum-route-goal">최종 목표 600일(26-W44)</span>' in markup
    assert '남은 1,190일<span class="shk-cum-left-note">목표 주차 지남</span>' in markup
    assert "@container (max-width: 220px)" in markup


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


def _stored(database_path: Path) -> int | None:
    return (
        DuckDBEquipmentRepository(database_path).load_shortening_progress_log().days_of(THIS_WEEK)
    )


def test_an_unchanged_save_is_judged_by_the_store_not_by_what_the_popup_saw(
    tmp_path: Path,
) -> None:
    """칸이 본 값(100) 그대로 눌러도 그 사이 남이 120 으로 고쳤으면 겹친 저장이다 — 「이미 100일」
    이라는 사실과 다른 글을 내지 않고 120 을 남긴다."""
    database_path, _ = _saved_database(tmp_path)
    _seed(database_path, [(THIS_WEEK, 100)])
    app = _open(_run(database_path))
    assert _number(app, "단축 필요일수").value == 100
    DuckDBEquipmentRepository(database_path).save_shortening_progress_entry(
        THIS_WEEK, 120, expected_days=100
    )
    clear_equipment_repository()
    app.button(key=_RECORD_SAVE_KEY).click().run()
    assert not app.exception
    assert _stored(database_path) == 120
    assert any("다른 사용자가 먼저" in text for text in texts(flashed(app, "warning")))
    assert not any("바뀐 것이 없습니다" in text for text in texts(flashed(app)))
    assert _number(app, "단축 필요일수").value == 120, "칸이 지금 저장본으로 새로 선다"
    clear_equipment_repository()


def test_a_delete_refuses_a_record_this_popup_never_saw(tmp_path: Path) -> None:
    """팝업을 연 때 그 주가 비어 있었는데 남이 넣고(70) 다시 고쳤으면(80) 「기록 지우기」 는 겹친
    저장으로 거절한다 — 누른 회차에 새로 읽은 값을 기대값으로 넘기지 않는다."""
    database_path, _ = _saved_database(tmp_path)
    app = _open(_run(database_path))
    assert app.button(key=_RECORD_DELETE_KEY).disabled
    repository = DuckDBEquipmentRepository(database_path)
    repository.save_shortening_progress_entry(THIS_WEEK, 70, expected_days=None)
    clear_equipment_repository()
    _number(app, "단축 필요일수").set_value(5).run()
    assert not app.button(key=_RECORD_DELETE_KEY).disabled, "표가 70 을 보여 지우기가 풀린다"
    repository.save_shortening_progress_entry(THIS_WEEK, 80, expected_days=70)
    clear_equipment_repository()
    app.button(key=_RECORD_DELETE_KEY).click().run()
    assert not app.exception
    assert _stored(database_path) == 80
    assert any("다른 사용자가 먼저" in text for text in texts(flashed(app, "warning")))
    assert not any("기록을 지웠습니다" in text for text in texts(flashed(app)))

    # 거절 뒤 칸이 지금 값(80)을 본 세대로 다시 서므로 다시 누르면 지운다.
    app.button(key=_RECORD_DELETE_KEY).click().run()
    assert not app.exception
    assert _stored(database_path) is None
    clear_equipment_repository()


def _dialog_script(database_path: str, today: str) -> None:
    """팝업 본문만 — 화면 합계는 시험이 세션 칸에 넣는다(본문이 덮지 않게)."""
    from datetime import date

    from capa_simulation.components.shortening_cumulative import _dialog_body

    _dialog_body(database_path, date.fromisoformat(today))


def test_a_screen_total_above_the_input_limit_locks_the_fill(tmp_path: Path) -> None:
    """화면 합계가 적을 수 있는 위끝을 넘으면 「이번 주 값 넣기」 는 잠기고 풍선이 까닭을 말한다.
    눌린 채 남은 넣은 값(세션 칸)이 있어도 칸은 그 값으로 서지 않아 팝업이 멈추지 않는다."""
    database_path = _database(tmp_path)
    app = AppTest.from_function(
        _dialog_script, args=(str(database_path), date.today().isoformat()), default_timeout=60
    )
    app.session_state[SCREEN_TOTAL_KEY] = ScreenTotal(
        days=PROGRESS_DAYS_MAX + 20_001,
        level_percent=110,
        process_count=70,
        selected=False,
        basis="Static",
    )
    app.run()
    assert not app.exception
    fill = app.button(key=_FILL_BUTTON_KEY)
    assert fill.disabled and "위끝" in str(fill.help)
    # 잠기기 전에 넣은 값이 세션 칸에 남은 회차 — 칸은 그 값으로 서지 않는다.
    app.session_state[_FILL_KEY] = (THIS_WEEK.label, PROGRESS_DAYS_MAX + 20_001)
    app.run()
    assert not app.exception
    assert _number(app, "단축 필요일수").value is None
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


def _shortened_days(units: pd.DataFrame) -> int:
    """호기별 단축 일정 CSV(화면과 같은 목표 · 공정 · 달)의 당긴 호기 단축일수 합."""
    chosen = units.loc[units["구분"].eq(KIND_SHORTENED), "단축일수"]
    return int(pd.to_numeric(chosen, errors="coerce").fillna(0).sum())


def test_this_weeks_value_follows_the_basis_switch_even_beside_another_basis_baseline(
    tmp_path: Path,
) -> None:
    """「이번 주 값 넣기」 의 화면 합계는 조건 카드 「Static | 설비 마스터」 전환이 고른 기준의
    계획이다. 진척 비교가 기준선과 같은 다른 기준의 계획을 보이는 회차(보드 답 Q14 (가))에도 합계는
    전환의 기준 그대로다 — 풍선이 그 기준을 말한다."""
    database_path, _ = _saved_database(tmp_path)
    app = _run_static(database_path)
    assert not app.exception, [element.message for element in app.exception]
    static_total = app.session_state[SCREEN_TOTAL_KEY]
    assert isinstance(static_total, ScreenTotal) and static_total.refusal is None
    _, units = _csv(app, "equipment_shortening_units_csv")
    assert set(units["현재 일정 기준"]) == {"Static"}
    assert static_total.days == _shortened_days(units) and static_total.basis == "Static"

    # Static 기준선을 남긴다(그때 전환 Static).
    app = _baseline_name(app).set_value("Static 기준선").run()
    app = _baseline_save(app).click().run()
    assert not app.exception, [element.message for element in app.exception]
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()

    app = app.sidebar.button_group(key=SHORTENING_BASIS_KEY).set_value("설비 마스터").run()
    assert not app.exception, [element.message for element in app.exception]
    master_total = app.session_state[SCREEN_TOTAL_KEY]
    _, units = _csv(app, "equipment_shortening_units_csv")
    assert set(units["현재 일정 기준"]) == {"설비 마스터"}
    assert master_total.days == _shortened_days(units) and master_total.basis == "설비 마스터"
    # 두 기준의 합계가 이 표본에서 달라야 아래 단언이 무엇을 막는다.
    assert master_total.days != static_total.days

    # 전환은 설비 마스터 그대로 Static 기준선과 견준다 — 본문은 Static 계획, 합계는 설비 마스터.
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()
    assert not app.exception, [element.message for element in app.exception]
    assert "이 기준으로 견줌(전환은 설비 마스터)" in _html(app)
    assert app.session_state[SCREEN_TOTAL_KEY] == master_total
    _open(app)
    help_text = str(app.button(key=_FILL_BUTTON_KEY).help)
    assert f"{master_total.days:,}일(설비 마스터 기준 · 목표" in help_text
    clear_equipment_repository()


def test_applying_processes_keeps_the_basis_the_comparison_and_the_strip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """조건 카드 「공정」 은 여럿 고른 뒤 「적용」 한 번이다(2026-11-20 사용자 결정). 「적용」 은 앱
    전체 회차 하나이고 같은 카드의 「Static | 설비 마스터」 전환 · 진척 비교 고름 · 머리 「누적
    진척」 띠를 건드리지 않는다 — 진척 비교는 적용한 공정의 카드로 좁혀 견주고, 「이번 주 값 넣기」
    의 화면 합계는 적용한 공정 · 전환의 기준 그대로의 합계다. 전환을 바꿔도 적용한 공정은
    그대로다."""
    live_board(monkeypatch)
    database_path, _ = _saved_database(tmp_path)
    app = _run_static(database_path)
    assert not app.exception, [element.message for element in app.exception]
    app = _baseline_name(app).set_value("Static 기준선").run()
    app = _baseline_save(app).click().run()
    assert not app.exception, [element.message for element in app.exception]
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()
    assert not app.exception, [element.message for element in app.exception]
    whole_cards = _progress_cards(app)
    strip = _strip(app)
    options = board_options(app, PROCESS_BOARD_KEY)
    chosen = next(option for option in options if [option] != whole_cards)
    runs = int(app.session_state["test_runs"])

    app = apply_board(app, PROCESS_BOARD_KEY, [chosen])

    assert not app.exception, [element.message for element in app.exception]
    assert int(app.session_state["test_runs"]) - runs == 1
    assert app.session_state[SHORTENING_BASIS_KEY] == "Static"
    assert app.session_state[SHORTENING_COMPARE_KEY] == stored.baseline_id
    assert set(_progress_cards(app)) <= {chosen}
    assert _strip(app) == strip
    total = app.session_state[SCREEN_TOTAL_KEY]
    _, units = _csv(app, "equipment_shortening_units_csv")
    assert set(units["공정"]) <= {chosen}
    assert (total.basis, total.selected) == ("Static", True)
    assert total.days == _shortened_days(units)

    app = app.sidebar.button_group(key=SHORTENING_BASIS_KEY).set_value("설비 마스터").run()
    assert not app.exception, [element.message for element in app.exception]
    assert app.session_state[SHORTENING_PROCESS_KEY] == [chosen]
    assert board_data(app, PROCESS_BOARD_KEY)["selected"] == [chosen]
    assert app.session_state[SCREEN_TOTAL_KEY].basis == "설비 마스터"
    clear_equipment_repository()
