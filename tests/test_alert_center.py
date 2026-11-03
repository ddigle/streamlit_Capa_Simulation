# Purpose: 알림 칸 컴포넌트의 data 계약·app.py 자리·변경 칩 목록(세션 판정)을 AppTest 로 시험한다.

"""알림 칸(`components/alert_center.py`)은 JS 라 AppTest 가 돌리지 못한다. 컴포넌트 한 겹만 기록
대역으로 바꿔 받은 data 를 본다(`tests/test_page_tabs.py` 와 같은 꼴). JS 의 순수 구획은
`tests/test_alert_center_assets.py` 가 본다."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alert_marks import alert_notes
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts
from capa_simulation.components import alert_center, change_summary
from capa_simulation.components.theme_toggle import (
    ALARM_BUTTON_ID,
    CHANGES_CHIP_ID,
    GUIDE_BUTTON_ID,
    PRINT_BUTTON_ID,
    THEME_BUTTON_ID,
    TOOLBAR_BUTTON_ORDER,
)
from capa_simulation.navigation import HOME, PROCESS_CAPA_DETAIL
from capa_simulation.upeh_assumption_state import UPEH_ASSUMPTION_PERCENT_KEY

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """알림 칸 기록 대역 — 받은 인자를 쌓는다."""
    calls: list[dict[str, Any]] = []

    def record(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(alert_center, "_ALERT_CENTER", record)
    return calls


@pytest.fixture
def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sent: list[dict[str, Any]]) -> AppTest:
    """빈 DuckDB 를 보는 `app.py`. 내장 시드가 부트스트랩을 채운다(`test_page_tabs` 꼴)."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    monkeypatch.setattr(
        month_range_picker, "_MONTH_RANGE_APPLY", lambda **kwargs: SimpleNamespace(apply=None)
    )
    return AppTest.from_file(str(APP_PATH), default_timeout=300)


def _ok(app: AppTest) -> AppTest:
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def test_the_data_carries_the_registry_levels_limits_and_toolbar_order() -> None:
    """단계 넷의 이름 · 알림창 시간, 쌓기 · 반복 창 · 보관, 시선 끌기, 툴바 차례(변경 칩 · Guide ·
    Alarm · Print · 테마 — Alarm 은 Guide 오른쪽), 표지 이름 · 저장 칸이 등록부 · 상수 그대로다."""
    data = alert_center.alert_center_data(changes=[], events=[])
    assert [(level["id"], level["label"], level["ms"]) for level in data["levels"]] == [
        ("info", "알림", 8000),
        ("check", "확인 필요", 15000),
        ("action", "조치 필요", 15000),
        ("error", "오류", 15000),
    ]
    assert data["limits"] == {
        "popups": 3,
        "repeat_ms": 60000,
        "rows": 200,
        "hours": 12,
        "attention_ms": 450,
        "easing": "cubic-bezier(0.5, 1, 0.89, 1)",
    }
    assert (
        data["toolbar"]["order"]
        == list(TOOLBAR_BUTTON_ORDER)
        == [
            CHANGES_CHIP_ID,
            GUIDE_BUTTON_ID,
            ALARM_BUTTON_ID,
            PRINT_BUTTON_ID,
            THEME_BUTTON_ID,
        ]
    )
    assert (data["toolbar"]["alarm"], data["toolbar"]["chip"]) == (ALARM_BUTTON_ID, CHANGES_CHIP_ID)
    assert data["marker"] == alerts.MARKER_ATTRIBUTE
    assert data["here"] == ""
    assert set(data["storage"]) == {"log", "states", "seen"}
    assert [group["id"] for group in data["groups"]] == ["lose", "keep", "assume"]


def test_the_palette_follows_the_theme_tokens_in_both_themes() -> None:
    from capa_simulation.design import theme, tokens

    previous = theme.current_mode()
    try:
        for mode in ("light", "dark"):
            theme._LOCAL.mode = mode
            colors = alert_center.palette()
            assert colors["check"] == tokens.palette_value(mode, "PENDING_MARK")
            assert colors["error"] == tokens.palette_value(mode, "ALERT_ERROR")
            assert colors["info"] == tokens.palette_value(mode, "TEXT_MUTED")
            assert colors["badge_ink"] == tokens.palette_value(mode, "SURFACE")
            assert all(value.startswith("#") for value in colors.values())
    finally:
        theme._LOCAL.mode = previous


def test_the_texts_are_korean_without_the_inside_word() -> None:
    """앱 화면 글에 「사내」 를 쓰지 않는다(2026-11-03)."""
    assert all("사내" not in value for value in alert_center.TEXT.values())
    assert alert_center.TEXT["alarm"] == "Alarm"


def test_the_app_draws_the_alert_center_before_the_page_and_sends_queued_events(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    """`app.py` 가 매 앱 전체 회차 페이지 앞에서 그린다. 콜백이 담아 둔 사건 알림은 그 회차에 한 번
    나간다 — 알림 칸 data 나, 그보다 먼저 서는 표지 자리(사이드바 시나리오 줄의 `render_flash`)가
    꺼낸다. 「화면」 · 「그 화면으로」 를 달 이번 화면을 적는다."""
    app = _ok(_app.run())
    assert sent and sent[-1]["key"] == alert_center.ALERT_CENTER_KEY
    assert sent[-1]["data"]["events"] == []
    assert app.session_state[alerts.PAGE_KEY] == {"page": "HOME", "href": ""}

    app.session_state[alerts.OUTBOX_KEY] = [
        alerts.AlertNote(id="demo", code="FL-01", kind="event", level="info", short="저장했습니다.")
    ]
    _ok(app.run())
    delivered = [note["id"] for note in sent[-1]["data"]["events"]] + [
        note["id"] for note in alert_notes(app) if note.get("id") == "demo"
    ]
    assert delivered == ["demo"]
    assert alerts.OUTBOX_KEY not in app.session_state


def test_the_change_chip_lists_an_upeh_assumption_in_the_assume_group(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    """UPEH 가정(100% 아님)은 「가정 사용 중」 묶음 한 줄 — 그 화면(공정 Capa 상세)으로 가는 주소를
    단다."""
    app = _ok(_app.run())
    assert sent[-1]["data"]["changes"] == []
    app.session_state[UPEH_ASSUMPTION_PERCENT_KEY] = 110
    _ok(app.run())
    (item,) = sent[-1]["data"]["changes"]
    assert item == {
        "group": "assume",
        "page": PROCESS_CAPA_DETAIL.title,
        "text": "UPEH 가정 110%",
        "top": "UPEH 가정",
        "href": "process_capa_detail",
    }


def test_session_changes_put_leaving_edits_before_unsaved_and_assumptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """차례 — 떠나면 사라짐 → 저장 안 함(시나리오 · 설비 · 붙여넣기 · Past Data · 목록) → 가정.
    세션만 읽는다."""
    monkeypatch.setattr(change_summary, "has_unsaved_scenario_changes", lambda: True)
    monkeypatch.setattr(change_summary, "past_data_has_pending", lambda: True)
    monkeypatch.setattr(
        change_summary,
        "remembered_equipment_label",
        lambda: {"scenario_name": "DEMO 셋업안", "revision_no": 3, "official_scenario": False},
    )
    script = f"""
import streamlit as st
from capa_simulation.components.change_summary import session_changes

st.session_state["{UPEH_ASSUMPTION_PERCENT_KEY}"] = 90
st.session_state["items"] = session_changes(None, hrefs={{"{HOME.path}": ""}})
"""
    app = AppTest.from_string(script).run()
    assert not app.exception
    items = app.session_state["items"]
    assert [(item["group"], item["top"]) for item in items] == [
        ("keep", "시나리오 미저장"),
        ("keep", "Past Data 미저장"),
        ("assume", "설비 가정"),
        ("assume", "UPEH 가정"),
    ]
    assert items[0]["href"] is None and items[1]["href"] == ""
    assert items[2]["text"] == "가정 「DEMO 셋업안」 r3"
    assert items[3]["text"] == "UPEH 가정 90%"
    assert change_summary.GROUPS[0][0] == "lose"


def test_a_drawn_marker_and_the_center_share_the_page_label(sent: list[dict[str, Any]]) -> None:
    """표지의 「화면」 은 `app.py` 가 적은 이번 화면이다 — 알림 칸이 같은 회차에 그 값을 안다."""
    script = """
from capa_simulation import alerts
from capa_simulation.components.alert_center import render_alert_center
from capa_simulation.components.flash import queue_flash, render_flash

alerts.note_page("VOC", "voc")
render_alert_center(changes=[])
queue_flash("demo", "글을 올렸습니다.")
render_flash("demo")
"""
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert sent and sent[-1]["data"]["events"] == []
    (note,) = alert_notes(app)
    assert (note["page"], note["href"]) == ("VOC", "voc")
    # 「그 화면으로」 가 탭을 고를 때 견주는 이번 화면 주소도 같은 값이다.
    assert sent[-1]["data"]["here"] == "voc"
