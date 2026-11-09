# Purpose: 알림 칸 컴포넌트의 data 계약·app.py 자리·변경 칩 목록(세션 판정)을 AppTest 로 시험한다.

"""알림 칸(`components/alert_center.py`)은 JS 라 AppTest 가 돌리지 못한다. 컴포넌트 한 겹만 기록
대역으로 바꿔 받은 data 를 본다(`tests/test_page_tabs.py` 와 같은 꼴). JS 의 순수 구획은
`tests/test_alert_center_assets.py` 가 본다."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alert_marks import alert_notes
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts
from capa_simulation.components import alert_center, change_summary
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
from capa_simulation.components.theme_toggle import (
    ALARM_BUTTON_ID,
    CHANGES_CHIP_ID,
    GUIDE_BUTTON_ID,
    PRINT_BUTTON_ID,
    PROCESS_CHIP_ID,
    SAMPLE_MARK_ID,
    THEME_BUTTON_ID,
    TOOLBAR_BUTTON_ORDER,
)
from capa_simulation.navigation import (
    AVAILABLE_EQUIPMENT_STATUS,
    CAPA_CHATBOT,
    DYNAMIC_CAPA,
    EXECUTION_MANAGEMENT_SUBPAGES,
    HOME,
    PROCESS_CAPA_DETAIL,
)
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
    """단계 넷의 이름 · 알림창 시간, 쌓기 · 반복 창 · 보관, 시선 끌기, 툴바 차례(공정 칩 · 합성 샘플
    · 변경 칩 · Guide · Alarm · Print · 테마 — 공정 칩이 맨 왼쪽, Alarm 은 Guide 오른쪽), 표지 이름
    · 저장 칸이 등록부 · 상수 그대로다."""
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
            PROCESS_CHIP_ID,
            SAMPLE_MARK_ID,
            CHANGES_CHIP_ID,
            GUIDE_BUTTON_ID,
            ALARM_BUTTON_ID,
            PRINT_BUTTON_ID,
            THEME_BUTTON_ID,
        ]
    )
    assert (data["toolbar"]["alarm"], data["toolbar"]["chip"]) == (ALARM_BUTTON_ID, CHANGES_CHIP_ID)
    assert (data["toolbar"]["process"], data["toolbar"]["sample"]) == (
        PROCESS_CHIP_ID,
        SAMPLE_MARK_ID,
    )
    # 공용 공정 값이 없으면 칩이 서지 않고, 화면 선언이 없으면 합성 샘플 표지도 서지 않는다.
    assert data["process"] is None
    assert data["sample"] is False
    assert data["marker"] == alerts.MARKER_ATTRIBUTE
    assert data["here"] == ""
    assert set(data["storage"]) == {"log", "states", "seen", "boot"}
    assert [group["id"] for group in data["groups"]] == ["lose", "keep", "assume"]


def test_the_data_carries_the_restart_notice_built_through_the_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """부트 표지와 등록부를 지난 재시작 알림 한 줄이 data 에 실린다(2026-11-07 통합 검수 D4 (가) ·
    2차 보드 R3 (가)). 어느 화면의 일도 아니라 화면 · 주소가 없고(「그 화면으로」 가 서지 않는다),
    표지 · 알림은 화면이 달라도 값이 같다 — 알림 id 를 회차마다 뽑으면 data 가 달라져 JS 가 회차마다
    다시 불린다."""
    boot = alert_center.alert_center_data(changes=[], events=[])["boot"]
    assert re.fullmatch(r"[0-9a-f]{16}", boot["mark"]) and boot["mark"] == alert_center.BOOT_MARK
    notice = boot["notice"]
    entry = alerts.spec(alerts.SERVER_RESTART_CODE)
    assert (entry.code, entry.kind, entry.level) == ("GL-07", "event", "check")
    assert (notice["code"], notice["kind"], notice["level"]) == ("GL-07", "event", "check")
    assert notice["id"] == f"restart-{alert_center.BOOT_MARK}"
    assert notice["short"] == notice["full"] == entry.short
    assert notice["short"] == (
        "서버가 다시 시작돼 화면을 처음으로 돌렸습니다. 저장하지 않은 고침과 입력은 사라졌습니다."
    )
    assert notice["cause"] == alerts.SERVER_RESTART_CAUSE
    assert "page" not in notice and "href" not in notice

    monkeypatch.setattr(alerts, "current_page", lambda: ("공정 Capa 상세", "process-capa-detail"))
    other = alert_center.alert_center_data(changes=[], events=[])
    assert other["here"] == "process-capa-detail"
    assert other["boot"] == boot


def test_the_data_carries_the_session_notice_built_through_the_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """세션 표지와 등록부를 지난 세션 만료 알림 한 줄이 data 에 실린다(2차 보드 R2 (가)) — 재시작
    알림과 같은 꼴이고, 표지 · 알림은 화면이 달라도 값이 같다."""
    session = alert_center.alert_center_data(changes=[], events=[])["session"]
    assert re.fullmatch(r"[0-9a-f]{16}", session["mark"])
    notice = session["notice"]
    entry = alerts.spec(alerts.SESSION_LOST_CODE)
    assert (entry.code, entry.kind, entry.level) == ("GL-08", "event", "check")
    assert (notice["code"], notice["kind"], notice["level"]) == ("GL-08", "event", "check")
    assert notice["id"] == f"session-{session['mark']}"
    assert notice["short"] == notice["full"] == entry.short
    assert notice["short"] == "연결이 오래 끊겨 저장하지 않은 고침이 사라졌습니다."
    assert notice["cause"] == alerts.SESSION_LOST_CAUSE
    assert "page" not in notice and "href" not in notice

    monkeypatch.setattr(alerts, "current_page", lambda: ("공정 Capa 상세", "process-capa-detail"))
    assert alert_center.alert_center_data(changes=[], events=[])["session"] == session


def test_the_session_mark_stays_in_a_session_and_differs_between_sessions(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    """세션마다 한 번 정한다 — 회차가 달라도 그대로라 data 약속이 깨지지 않고, 새 세션은 달라 JS 가
    세션이 바뀐 것을 안다."""
    app = _ok(_app.run())
    _ok(app.run())
    _ok(AppTest.from_file(str(APP_PATH), default_timeout=300).run())
    first, again, other = (call["data"]["session"] for call in sent)
    assert first == again
    assert first["mark"] != other["mark"]
    assert first["notice"]["id"] != other["notice"]["id"]


def test_the_component_declares_the_reconnect_trigger_with_a_callback_that_does_nothing(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    """재연결 회차(2차 보드 R1 (가))는 회차가 도는 것이 목적이다 — 콜백은 상태를 건드리지 않는다."""
    _ok(_app.run())
    callback = sent[0]["on_reconnected_change"]
    assert callback is alert_center._reconnected
    assert callback() is None
    # 둘째 트리거 — 공정 칩 판 「모든 화면에서 해제」.
    assert sent[0]["on_process_clear_change"] is alert_center._clear_process


def _chip_script() -> None:
    import streamlit as st

    from capa_simulation import alerts, shared_process
    from capa_simulation.components import alert_center
    from capa_simulation.navigation import ALL_SPECS

    for name, args, kwargs in st.session_state.pop("ops", []):
        getattr(shared_process, name)(*args, **kwargs)
    path = st.session_state.get("test_path")
    alerts.note_page("", st.session_state.get("test_href", ""))
    current = next((spec for spec in ALL_SPECS if spec.path == path), None)
    if st.session_state.pop("test_clear", False):
        alert_center._clear_process()
    st.session_state["data"] = alert_center.alert_center_data(
        changes=[], events=[], current=current
    )


def test_the_process_chip_carries_the_shared_value_labels_and_a_guess_for_this_screen() -> None:
    """머리 띠 공정 칩(2026-11-09 보드 C1 (라)) — 공용 값 · 보이는 글자 · 「Mold 외 2개」 · 출처 ·
    판을 싣고, 지금 화면이 따라가는 화면이면 세션 기록의 짐작(`here`)을 단다. 따라가지 않는
    화면(HOME)은 짐작이 없다(흐린 칩). 값이 그대로면 data 가 같다."""
    app = AppTest.from_function(_chip_script)
    app.session_state["ops"] = [
        ("publish", (["Mold", "Underfill", "PMC"], "산출 결과"), {"labels": {"Mold": "몰드"}}),
    ]
    app.session_state["test_path"] = HOME.path
    app.run()
    assert not app.exception
    chip = app.session_state["data"]["process"]
    assert chip["values"] == ["Mold", "Underfill", "PMC"]
    assert chip["labels"] == ["몰드", "Underfill", "PMC"]
    assert chip["top"] == "몰드 외 2개"
    assert chip["origin"] == "산출 결과"
    assert chip["here"] is None
    assert chip["field"] == "sidebar_process_field"
    assert chip["marker"] == "data-capa-process"
    app.run()
    assert app.session_state["data"]["process"] == chip

    app.session_state["test_path"] = AVAILABLE_EQUIPMENT_STATUS.path
    app.session_state["ops"] = [("note_drawn", ("가용설비", "multi", ["Mold", "Underfill"]), {})]
    app.run()
    here = app.session_state["data"]["process"]["here"]
    assert here == {
        "on": True,
        "follows": True,
        "inside": ["Mold", "Underfill"],
        "missing": ["PMC"],
    }


def test_the_process_chip_names_the_first_process_in_this_screens_order() -> None:
    """머리 칩 · 판의 차례는 따라가는 화면이면 이 화면 선택지 차례다 — 걸린 공정 먼저, 없는 공정
    뒤. 칩의 첫 이름이 사이드바 값 칸(표시순서상 첫 공정) · 탭 풍선과 같아진다. 따라가지 않는 화면
    (HOME)은 보낸 차례 그대로다. 이 화면 기록이 그대로면 data 가 같다."""
    app = AppTest.from_function(_chip_script)
    app.session_state["ops"] = [
        ("publish", (["Underfill", "PMC", "Mold"], "산출 결과"), {}),
        ("note_drawn", ("가용설비", "multi", ["Mold", "WF", "Underfill"]), {}),
    ]
    app.session_state["test_path"] = HOME.path
    app.run()
    assert not app.exception
    home = app.session_state["data"]["process"]
    assert (home["values"], home["top"]) == (["Underfill", "PMC", "Mold"], "Underfill 외 2개")

    app.session_state["test_path"] = AVAILABLE_EQUIPMENT_STATUS.path
    app.run()
    chip = app.session_state["data"]["process"]
    assert chip["values"] == ["Mold", "Underfill", "PMC"]
    assert chip["labels"] == ["Mold", "Underfill", "PMC"]
    assert chip["top"] == "Mold 외 2개"
    assert chip["here"]["inside"] == ["Mold", "Underfill"]
    app.run()
    assert app.session_state["data"]["process"] == chip


def test_clearing_from_the_chip_panel_empties_the_shared_value_and_the_chip() -> None:
    """판 「모든 화면에서 해제」 트리거의 콜백은 공용 값을 지운다 — 다음 data 에 칩이 없다."""
    app = AppTest.from_function(_chip_script)
    app.session_state["ops"] = [("publish", (["Mold"], "HOME"), {})]
    app.run()
    assert app.session_state["data"]["process"] is not None
    app.session_state["test_clear"] = True
    app.run()
    assert not app.exception
    assert app.session_state["data"]["process"] is None


def test_the_sample_mark_stands_only_on_pending_source_screens_with_samples_on() -> None:
    """합성 샘플 표지(2026-11-09 보드 T8) — 원천 미연결 화면(`pending_source`)이고 「샘플 데이터」
    가 켜졌을 때만. 스위치는 처음 연 세션에 켜짐이다."""
    actual = next(spec for spec in EXECUTION_MANAGEMENT_SUBPAGES if spec.pending_source)
    app = AppTest.from_function(_chip_script)
    for spec, expected in (
        (HOME, False),
        (CAPA_CHATBOT, True),
        (actual, True),
        (DYNAMIC_CAPA, True),
    ):
        app.session_state["test_path"] = spec.path
        app.run()
        assert not app.exception
        assert app.session_state["data"]["sample"] is expected, spec.title
    app.session_state[SAMPLE_TOGGLE_KEY] = False
    app.session_state["test_path"] = CAPA_CHATBOT.path
    app.run()
    assert app.session_state["data"]["sample"] is False


def test_the_boot_mark_is_the_same_in_every_run_and_session_of_this_process(
    _app: AppTest, sent: list[dict[str, Any]]
) -> None:
    """새로고침 · 테마 전환은 같은 프로세스의 새 세션이다 — 회차와 세션이 달라도 표지 · 알림이 같아
    JS 가 재시작으로 읽지 않는다."""
    app = _ok(_app.run())
    _ok(app.run())
    _ok(AppTest.from_file(str(APP_PATH), default_timeout=300).run())
    assert len(sent) == 3
    assert all(call["data"]["boot"] == sent[0]["data"]["boot"] for call in sent)


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
        "tab": "",
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
