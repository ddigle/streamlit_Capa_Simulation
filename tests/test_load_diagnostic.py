# Purpose: 「서버 시작 점검」 의 부하 값 줄과 문턱 넘음 개발자 알림(`AD-26`)의 자리를 지킨다.

"""`components/load_diagnostic.py` 와 `container_start_check.render_load_alert`.

값 줄은 「서버 시작 점검」 펼침(C-DEP)의 메모리 값 줄 뒤에 서고 「복사」 글에도 든다. 못 잰 값은
「모름」 이다. 문턱을 넘으면 시작 점검 알림과 같은 판정의 서버에서 개발자 상태 알림 `AD-26` 이
선다 — 지문은 넘은 문턱 이름뿐이고, 그 판정이 거짓인 서버(개발 · 사내 PC · 시험)는 Streamlit 호출이
없으며, 개발자가 아닌 회차는 글 없는 해소다.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alert_marks import active_state, states
from streamlit.testing.v1 import AppTest

import capa_simulation.settings as settings
from capa_simulation import alerts, load_metrics
from capa_simulation.components import container_start_check, load_diagnostic
from capa_simulation.components.diagnostic_copy import COMPONENT_KEY_PREFIX
from capa_simulation.components.load_diagnostic import (
    cpu_line,
    response_line,
    session_line,
    signal_of,
)
from capa_simulation.load_metrics import CpuView, ResponseView, SessionView

# 2026-11-18 14:03:00 KST.
PEAK_EPOCH = datetime(2026, 11, 18, 5, 3, tzinfo=timezone.utc).timestamp()
QUIET = (ResponseView(40, 0.4, 1.2), CpuView(0.1, 0.3, PEAK_EPOCH), SessionView(3, 7, PEAK_EPOCH))
BUSY = (ResponseView(40, 3.4, 8.0), CpuView(0.82, 0.9, PEAK_EPOCH), SessionView(26, 26, PEAK_EPOCH))


def test_unknown_values_read_as_unknown() -> None:
    assert response_line(ResponseView(0, None, None)) == (
        "**화면 응답** · 최근 1시간 0회 · 느린 쪽 모름 · 최고 모름"
    )
    assert cpu_line(CpuView(None, None, None)) == "**CPU** · 5분 평균 모름 · 기동 뒤 최고 모름"
    assert session_line(SessionView(None, None, None)) == (
        "**동시 세션** · 지금 모름 · 기동 뒤 최고 모름"
    )


def test_the_lines_carry_values_and_kst_times() -> None:
    response, cpu, sessions = QUIET
    assert (
        response_line(response) == "**화면 응답** · 최근 1시간 40회 · 느린 쪽 0.40초 · 최고 1.20초"
    )
    assert cpu_line(cpu) == (
        "**CPU** · 5분 평균 0.10코어 · 기동 뒤 최고 0.30코어(2026-11-18 14:03:00)"
    )
    assert session_line(sessions) == "**동시 세션** · 지금 3 · 기동 뒤 최고 7(2026-11-18 14:03:00)"


def test_a_signal_names_only_what_crossed_and_its_fingerprint_is_the_names() -> None:
    """넘은 문턱만 글에 싣고 지문 재료는 이름뿐이다 — 값이 오르내려도 다시 뜨지 않는다."""
    assert signal_of(*QUIET) is None
    signal = signal_of(*BUSY)
    assert signal is not None
    assert signal.names == ("slow", "cpu", "sessions")
    assert (
        signal.text
        == "서버 부하 신호 — 화면 응답 느린 쪽 3.40초 · CPU 5분 평균 0.82코어 · 동시 세션 26"
    )
    assert "화면 응답 느린 쪽 3초 · CPU 5분 평균 0.7코어 · 동시 세션 25" in signal.full
    assert "「서버 시작 점검」" in signal.full
    higher = signal_of(
        ResponseView(80, 5.0, 9.0), CpuView(0.95, 0.95, 1.0), SessionView(30, 30, 1.0)
    )
    assert higher is not None and higher.names == signal.names
    assert alerts.fingerprint("AD-26", None, list(higher.names)) == alerts.fingerprint(
        "AD-26", None, list(signal.names)
    )
    only_cpu = signal_of(QUIET[0], BUSY[1], QUIET[2])
    assert only_cpu is not None and only_cpu.names == ("cpu",)
    assert only_cpu.text == "서버 부하 신호 — CPU 5분 평균 0.82코어"


def test_the_run_end_never_breaks_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: object) -> None:
        raise RuntimeError("계측 실패")

    monkeypatch.setattr(load_metrics, "finish_run", broken)
    load_diagnostic.note_run_end(load_metrics.begin_run())


def test_the_run_end_records_the_connected_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(load_diagnostic, "session_counts", lambda: (4, 6))
    load_diagnostic.note_run_end(load_metrics.begin_run())
    assert load_metrics.response_view().runs == 1
    assert load_metrics.session_view(None).peak == 4


# ---------------------------------------------------------------- 「서버 시작 점검」 자리

SCRIPT = """
from capa_simulation.components.container_start_check import render_container_start_check

render_container_start_check()
"""


def _report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """모든 단계가 정상인 시작 결과 파일(C-DEP 꼴)."""
    report = tmp_path / "container_start.json"
    report.write_text(
        json.dumps(
            {
                "version": 1,
                "written_at": "2026-11-18T09:00:00+09:00",
                "steps": {
                    step: {"status": "ok", "reason": "정상"}
                    for step in ("install", "token", "user_name")
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", report)
    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")


def test_the_start_check_carries_the_load_lines_after_the_memory_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diagnostic_copies: dict[str, str]
) -> None:
    _report(tmp_path, monkeypatch)
    monkeypatch.setattr(load_diagnostic, "session_counts", lambda: (2, 3))
    # 화면이 진짜 시계로 읽으므로 회차는 지금 바로 앞(최근 1시간 안)에 둔다. CPU 는 첫 표본이 이
    # 시험 맨 앞이라 5분을 덮지 못해 「모름」 이다.
    moment = time.monotonic() - 100.0
    for index in range(25):
        load_metrics.record_run(
            seconds=0.1 * (index + 1),
            now=moment + index,
            cpu=time.process_time(),
            wall=PEAK_EPOCH,
            sessions=2,
        )

    app = AppTest.from_string(SCRIPT).run(timeout=60)

    assert not list(app.exception), [item.message for item in app.exception]
    captions = "\n".join(caption.value for caption in app.caption)
    assert "**화면 응답** · 최근 1시간 25회 · 느린 쪽 2.40초 · 최고 2.50초" in captions
    assert "**CPU** · 5분 평균 모름" in captions
    assert "**동시 세션** · 지금 2 · 기동 뒤 최고 2(2026-11-18 14:03:00)" in captions
    assert captions.index("**메모리 지금**") < captions.index("**화면 응답**")
    text = diagnostic_copies[f"{COMPONENT_KEY_PREFIX}container_start_check"]
    assert "화면 응답 · 최근 1시간 25회 · 느린 쪽 2.40초" in text
    assert "동시 세션 · 지금 2" in text


# ---------------------------------------------------------------- 개발자 알림 `AD-26`


def _alert_script() -> None:
    from capa_simulation.components.container_start_check import render_load_alert

    render_load_alert()


def _busy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(container_start_check, "load_signal", lambda: signal_of(*BUSY))


@pytest.mark.parametrize("possible", [True, False], ids=["start-check", "plain"])
def test_the_alert_takes_one_event_slot_only_on_start_check_servers(
    monkeypatch: pytest.MonkeyPatch, possible: bool
) -> None:
    """이벤트 칸 수는 프로세스 동안 같다 — 시작 점검 판정이 참인 서버는 조건 앞뒤 모두 한 자리,
    거짓인 서버(개발 · 사내 PC · 시험)는 앞뒤 모두 0 이다."""
    monkeypatch.setattr(container_start_check, "start_check_alert_possible", lambda: possible)
    monkeypatch.setattr(container_start_check, "developer_alerts_visible", lambda: True)
    app = AppTest.from_function(_alert_script).run()
    before = len(app.get("html"))
    assert active_state(app, container_start_check.LOAD_ALERT_CODE) is None

    _busy(monkeypatch)
    app.run()

    assert before == len(app.get("html")) == (1 if possible else 0)
    assert (active_state(app, container_start_check.LOAD_ALERT_CODE) is not None) is possible


@pytest.mark.parametrize("developer", [True, False], ids=["developer", "user"])
def test_a_crossed_threshold_is_told_to_the_developer(
    monkeypatch: pytest.MonkeyPatch, developer: bool
) -> None:
    """개발자 회차는 넘은 값과 「그 화면으로」 Admin 「서버 시작 점검」, 다른 회차는 글 없는
    해소다."""
    monkeypatch.setattr(container_start_check, "start_check_alert_possible", lambda: True)
    monkeypatch.setattr(container_start_check, "developer_alerts_visible", lambda: developer)
    _busy(monkeypatch)

    app = AppTest.from_function(_alert_script).run()

    [note] = states(app, container_start_check.LOAD_ALERT_CODE)
    if not developer:
        assert note["active"] is False
        assert note["short"] == alerts.REGISTRY["AD-26"].title
        assert "느린 쪽" not in json.dumps(note, ensure_ascii=False)
        return
    expected = signal_of(*BUSY)
    assert expected is not None
    assert note["active"] is True
    assert note["short"] == expected.text and note["full"] == expected.full
    assert note["href"] == "admin_area"
    assert note["target"]["kind"] == container_start_check.START_CHECK_TARGET_KIND
    assert alerts.REGISTRY["AD-26"].level == "check"


def test_the_alert_resolves_when_the_load_falls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(container_start_check, "start_check_alert_possible", lambda: True)
    monkeypatch.setattr(container_start_check, "developer_alerts_visible", lambda: True)
    _busy(monkeypatch)
    app = AppTest.from_function(_alert_script).run()
    assert active_state(app, container_start_check.LOAD_ALERT_CODE) is not None

    monkeypatch.setattr(container_start_check, "load_signal", lambda: None)
    app.run()

    [note] = states(app, container_start_check.LOAD_ALERT_CODE)
    assert note["active"] is False


# ---------------------------------------------------------------- `app.py` 이음


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


@pytest.mark.parametrize("possible", [True, False], ids=["start-check", "plain"])
def test_the_app_records_its_runs_and_raises_the_alert_on_start_check_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, possible: bool
) -> None:
    """`app.py` 의 이음 셋 — 맨 앞 `begin_run`, 끝까지 돈 회차 끝 `note_run_end`, 페이지 앞
    `render_load_alert` — 이 빠지면 여기서 멈춘다. 개발 · 시험(시작 점검 판정 거짓)도 회차를 재고
    알림 표지는 없다."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **_: None)
    monkeypatch.setattr(container_start_check, "start_check_alert_possible", lambda: possible)
    monkeypatch.setattr(container_start_check, "developer_alerts_visible", lambda: True)
    _busy(monkeypatch)

    app = AppTest.from_file(str(APP_PATH), default_timeout=300).run()

    assert not list(app.exception), [item.message for item in app.exception]
    assert load_metrics.response_view().runs >= 1
    note = active_state(app, container_start_check.LOAD_ALERT_CODE)
    assert (note is not None) is possible
    assert len(states(app, container_start_check.LOAD_ALERT_CODE)) == (1 if possible else 0)


def test_the_alert_was_added_at_the_end_of_the_registry() -> None:
    """등록부는 끝에만 더한다 — `AD-26` 은 공지 `GL-09` 뒤다(`AD-14` ~ `AD-18` 은 비워 둔 · 걷은
    번호 그대로). 뒤에 더 붙는 줄이 있어도 차례만 본다."""
    codes = [spec.code for spec in alerts.SPECS]
    assert codes.index("GL-09") < codes.index("AD-26")
    spec = alerts.spec("AD-26")
    assert (spec.kind, spec.title) == (
        "state",
        "서버 부하 신호 — 화면 응답 · CPU · 동시 세션 문턱 넘음",
    )
