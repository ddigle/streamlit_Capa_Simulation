# Purpose: 알림 2단계 b 화면(설비 · 실행 관리 · 재공 · 시나리오 관리 · Admin)의 상태 알림을 잰다.

"""알림 체계 2단계 b — 2026-11-03 결정 보드 D2 (나)(상태 경고는 자리에서 지우고 알림창 · Alarm
에만).

- 탭 안 상태 알림은 그 탭이 열린 회차에만 내고(설계 2-3 「숨은 자리는 세지 않는다」), 표지에 탭
  이름을 실어 「그 화면으로」 가 그 탭까지 연다(`state_alerts.open_tab_name` · `tab_name`).
- 자리에는 경고 상자를 그리지 않는다 — 상태 줄(캡션 · 마크다운)은 칸의 일이라 남는다.
- 화면을 그리지 못한 오류는 자리에 「데이터 Error」 마크만 세우고 글은 같은 글이면 한 번 뜨는
  사건 알림으로 보낸다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from alert_marks import active_state, alert_notes, data_error_marks, events, states
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script
from test_wip_status_page import TEST_SCRIPT as WIP_SCRIPT

from capa_simulation.components.equipment_scenario_management import (
    SCENARIO_MANAGEMENT_TABS_KEY,
)
from capa_simulation.components.state_alerts import open_tab_name, tab_name
from capa_simulation.navigation import STANDARD_TARGET_CAPA
from capa_simulation.page_tabs_state import tab_label

NOW = datetime(2026, 10, 15, 9, 0)


# ---------------------------------------------------------------- 탭 이름


def test_a_tab_name_drops_the_icon_and_joins_nested_tabs() -> None:
    """알림의 `tab` 은 아이콘 없는 탭 단추 글 — 탭 안 탭은 바깥 → 안 차례로 ` › ` 로 잇는다(알림 칸
    JS `TAB_PATH`). 닫힌 탭은 None 이라 그 회차에는 탭 안 상태 알림을 내지 않는다."""
    assert tab_name(":material/autorenew: 자동 갱신") == "자동 갱신"
    assert (
        tab_name(":material/insights: Summary", ":material/compare_arrows: Static 대비 일정")
        == "Summary › Static 대비 일정"
    )
    assert tab_name("Proc Rename") == "Proc Rename"
    assert open_tab_name(SimpleNamespace(open=True), ":material/label: Proc Rename") == (
        "Proc Rename"
    )
    assert open_tab_name(SimpleNamespace(open=False), ":material/label: Proc Rename") is None
    # 탭 위젯이 아닌 탭(`open` 이 None — 늘 그린다)과 탭이 없는 자리는 연 것으로 본다.
    assert open_tab_name(SimpleNamespace(open=None), "Proc Rename") == "Proc Rename"
    assert open_tab_name(None, "Proc Rename") == "Proc Rename"


# ---------------------------------------------------------------- 자동 갱신 예약(AU-01 · AU-02)


def _scheduler_status(database: str, tab: str | None, mode: str) -> None:
    from datetime import datetime, timedelta
    from pathlib import Path
    from types import SimpleNamespace

    import capa_simulation.components.auto_official_update_tab as tab_module
    from capa_simulation.auto_update_scheduler import SchedulerStatus, TickOutcome
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    repository = DuckDBScenarioRepository(Path(database))
    repository.initialize()
    now = datetime(2026, 10, 15, 9, 0)
    status = SchedulerStatus(
        started_at=now - timedelta(hours=1),
        last_tick_at=now - timedelta(minutes=10),
        last_outcome=TickOutcome("waiting", now - timedelta(minutes=10)),
        pending_day=None,
        alive=True,
        tick_seconds=30.0,
    )
    scheduler = SimpleNamespace(status=lambda: status) if mode == "stalled" else None
    # 모듈이 들여온 이름을 이 회차 동안만 갈아 끼운다(내보내지 않은 이름이라 모듈 사전으로).
    original = (vars(tab_module)["running_scheduler"], vars(tab_module)["scheduler_opted_in"])
    vars(tab_module)["running_scheduler"] = lambda: scheduler
    vars(tab_module)["scheduler_opted_in"] = lambda *args: mode == "missing"
    try:
        tab_module._render_status(
            repository,
            repository.load_auto_official_update_settings(),
            now=now,
            alert_tab=tab,
        )
    finally:
        vars(tab_module)["running_scheduler"] = original[0]
        vars(tab_module)["scheduler_opted_in"] = original[1]


def _status_app(tmp_path: Path, tab: str | None, mode: str) -> AppTest:
    app = AppTest.from_function(
        _scheduler_status,
        args=(str(tmp_path / "scenario.duckdb"), tab, mode),
        default_timeout=60,
    ).run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def test_a_stalled_scheduler_is_an_alert_on_the_auto_update_tab(tmp_path: Path) -> None:
    """멈춘 것 같은 예약(`AU-01`)은 알림창 · Alarm 으로 가고 「지금 상태」 칸에는 상태 줄만 선다 —
    경고 상자도, 「켜져 있습니다」 성공 상자도 없다. 지문은 마지막 확인 시각 · 갈래라 회차마다
    바뀌는 「n분」 글에 흔들리지 않는다."""
    app = _status_app(tmp_path, "자동 갱신", "stalled")

    assert not app.warning and not app.success
    note = active_state(app, "AU-01")
    assert note is not None and note["tab"] == "자동 갱신" and note["level"] == "action"
    assert "멈춰 있습니다" in note["full"], note
    assert [item["active"] for item in states(app, "AU-02")] == [False]
    assert any("멈춘 것 같음" in str(item.value) for item in app.markdown)
    again = _status_app(tmp_path, "자동 갱신", "stalled")
    assert active_state(again, "AU-01")["fp"] == note["fp"]  # type: ignore[index]


def test_a_missing_thread_is_an_alert_and_a_status_line(tmp_path: Path) -> None:
    app = _status_app(tmp_path, "자동 갱신", "missing")

    assert not app.warning
    note = active_state(app, "AU-02")
    assert note is not None and "예약 스레드가 서 있지 않습니다" in note["full"], note
    assert [item["active"] for item in states(app, "AU-01")] == [False]
    assert any("스레드 없음" in str(item.value) for item in app.markdown)


def test_a_closed_auto_update_tab_sends_no_scheduler_alert(tmp_path: Path) -> None:
    app = _status_app(tmp_path, None, "stalled")

    assert not states(app, "AU-01") and not states(app, "AU-02")
    assert any("멈춘 것 같음" in str(item.value) for item in app.markdown)


# ---------------------------------------------------------------- 시나리오 관리 탭


@pytest.fixture(scope="module")
def scenario_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("area_b_scenario_management")
    return root / "scenario.duckdb", root / "equipment.duckdb"


def test_scenario_management_alerts_only_from_the_open_tab(
    scenario_databases: tuple[Path, Path],
) -> None:
    """탭을 늘 그리지만 상태 알림은 열린 탭의 것만 낸다 — 「Capa 시나리오」(`SC-01`) ·
    「DB 등록」(`AD-04`) · 「자동 갱신」(`AU-01/02`). 표지의 탭 이름이 「그 화면으로」 의 탭이다."""
    database, equipment = scenario_databases
    app = AppTest.from_string(
        _page_script("app_pages/scenario_management.py", database, equipment), default_timeout=120
    ).run()
    assert not app.exception, [item.message for item in app.exception]

    (official,) = states(app, "SC-01")
    assert official["tab"] == "Capa 시나리오"
    assert not states(app, "AD-04") and not states(app, "AU-01") and not states(app, "AU-02")

    app.session_state[SCENARIO_MANAGEMENT_TABS_KEY] = ":material/cloud_download: DB 등록"
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    (query,) = states(app, "AD-04")
    assert query["tab"] == "DB 등록"
    assert not states(app, "SC-01")
    # 설정이 덜 됐으면 자리에는 경고 상자 대신 상태 캡션이 선다.
    if query["active"]:
        assert not [item for item in app.warning if "bigdataquery" in str(item.value).lower()]

    app.session_state[SCENARIO_MANAGEMENT_TABS_KEY] = ":material/autorenew: 자동 갱신"
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    tabs = {str(item["code"]): item.get("tab") for item in states(app)}
    assert tabs.get("AU-01") == "자동 갱신" and tabs.get("AU-02") == "자동 갱신", tabs
    assert "AD-04" not in tabs and "SC-01" not in tabs


def test_the_missing_official_alert_points_at_the_archive_when_only_archives_are_left(
    tmp_path: Path,
) -> None:
    """공식버전이 없고 시나리오가 보관본만 남았으면 `SC-01` 이 고를 것 없는 목록 대신 보관함의
    「되돌리기」 를 가리킨다(검수 보드 st-sc01 — 작은 결정 a8 과 같은 꼴). 활성 시나리오가 있으면
    보관함을 가리키지 않는 다른 글이다."""
    from test_page_bootstrap import _store_with_scenarios

    database = tmp_path / "scenario.duckdb"
    _store_with_scenarios(database, archived=2, active=0)
    app = AppTest.from_string(
        _page_script("app_pages/scenario_management.py", database, tmp_path / "equipment.duckdb"),
        default_timeout=120,
    ).run()
    assert not app.exception, [item.message for item in app.exception]

    official = active_state(app, "SC-01")
    assert official is not None and official["tab"] == "Capa 시나리오"
    assert "보관본만 있음 · 목록 관리 「보관함」 › 「되돌리기」" in str(official["short"])
    assert "「보관함」 에서 「되돌리기」 한 뒤 「공식으로 지정…」" in str(official["full"])

    listed = tmp_path / "listed.duckdb"
    _store_with_scenarios(listed, archived=1, active=1)
    app = AppTest.from_string(
        _page_script("app_pages/scenario_management.py", listed, tmp_path / "equipment.duckdb"),
        default_timeout=120,
    ).run()
    assert not app.exception, [item.message for item in app.exception]
    official_listed = active_state(app, "SC-01")
    assert official_listed is not None
    assert "보관함" not in str(official_listed["short"])
    assert official_listed["fp"] != official["fp"]


# ---------------------------------------------------------------- Admin 탭 · 점검 펼침


def _rename_collision(database: str, tab: str | None) -> None:
    from pathlib import Path

    import pandas as pd

    from capa_simulation.components.process_rename_management import (
        render_process_rename_management,
    )
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    repository = DuckDBScenarioRepository(Path(database))
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "MOLD")], columns=["공정", "표시명"]), source="테스트"
    )
    render_process_rename_management(repository, ["SAW", "MOLD"], alert_tab=tab)


def test_the_proc_rename_collision_alert_names_its_tab_and_skips_a_closed_one(
    tmp_path: Path,
) -> None:
    from capa_simulation.persistence.cache import clear_global_process_rename_cache

    database = str(tmp_path / "rename.duckdb")
    opened = AppTest.from_function(
        _rename_collision, args=(database, "Proc Rename"), default_timeout=60
    ).run()
    assert not opened.exception, [item.message for item in opened.exception]
    note = active_state(opened, "AD-06")
    assert note is not None and note["tab"] == "Proc Rename" and "MOLD" in note["full"]
    assert not opened.warning

    closed = AppTest.from_function(
        _rename_collision, args=(database, None), default_timeout=60
    ).run()
    assert not closed.exception, [item.message for item in closed.exception]
    assert not states(closed, "AD-06")
    clear_global_process_rename_cache()


def _admin_checks(cert: bool, root_error: str) -> None:
    import capa_simulation.components.module_status as module_status
    import capa_simulation.components.sso_status as sso_status
    from capa_simulation.module_registry import ModuleScan

    scan = ModuleScan(
        root=None, root_exists=False, records=(), disabled_value="", unknown_disabled=()
    )
    if root_error:
        scan = ModuleScan(
            root=None,
            root_exists=True,
            records=(),
            disabled_value="",
            unknown_disabled=(),
            root_error=root_error,
        )
    original = (vars(sso_status)["_expiring_certs"], vars(module_status)["module_scan"])
    vars(sso_status)["_expiring_certs"] = lambda cfg, now: ["DEMO-X5T"] if cert else []
    vars(module_status)["module_scan"] = lambda: scan
    try:
        sso_status.render_sso_status()
        module_status.render_module_status()
    finally:
        vars(sso_status)["_expiring_certs"] = original[0]
        vars(module_status)["module_scan"] = original[1]


def test_cert_expiry_and_an_unreadable_module_root_are_alerts() -> None:
    """서명 인증서 만료 임박(`AD-03`) · 모듈 뿌리를 못 읽음(`MO-01`)은 그 펼침을 그리지 않는
    회차에도 상태 알림으로 낸다 — 운영 점검 결과가 화면 구석 펼침에만 있지 않게. 조건이 없으면 해소
    표지다."""
    app = AppTest.from_function(
        _admin_checks, args=(True, "DEMO 모듈 폴더를 읽지 못했습니다"), default_timeout=30
    ).run()
    assert not app.exception, [item.message for item in app.exception]
    cert = active_state(app, "AD-03")
    assert cert is not None and "만료" in cert["short"]
    root = active_state(app, "MO-01")
    assert root is not None and root["full"] == "DEMO 모듈 폴더를 읽지 못했습니다"
    assert not app.warning
    # 펼침 안에는 까닭이 캡션으로 남는다(점검 보고).
    assert any("DEMO 모듈 폴더" in str(item.value) for item in app.caption)

    quiet = AppTest.from_function(_admin_checks, args=(False, ""), default_timeout=30).run()
    assert [item["active"] for item in states(quiet, "AD-03")] == [False]
    assert [item["active"] for item in states(quiet, "MO-01")] == [False]


# ---------------------------------------------------------------- 재공 현황(WIP-04)


def _wip_part_unset_script() -> str:
    """P-Process 만 가용대수 · 일 표준 가능량이 빈 재공 현황 — 일부만 빈 자리(화면은 그린다)."""
    script = WIP_SCRIPT.replace(
        '"일 표준 가능량": 200.0 / 30.0,',
        '"일 표준 가능량": float("nan") if process == "P-Process" else 200.0 / 30.0,',
    ).replace(
        '"가용대수": 2.0,\n', '"가용대수": float("nan") if process == "P-Process" else 2.0,\n'
    )
    assert script != WIP_SCRIPT
    return script


def test_a_wip_route_without_a_baseline_is_an_alert_not_a_box() -> None:
    """가용대수가 없어 기준선을 못 그린 경로(`WIP-04`)는 상태 알림이다 — 범위는 활성 리비전 내용
    토큰 + 조회일, 내용은 있음/없음뿐이라 공정 · 제품 거르기를 바꿔도 다시 뜨지 않는다."""
    app = AppTest.from_string(_wip_part_unset_script(), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]

    assert not [item for item in app.warning if "기준선" in str(item.value)]
    note = active_state(app, "WIP-04")
    assert note is not None, states(app, "WIP-04")
    assert "표준 목표" in note["short"] and note["level"] == "action"
    assert note["scope_label"].endswith(
        f"{datetime.now().date() - timedelta(days=7):%y.%m.%d}–"
        f"{datetime.now().date() + timedelta(days=3):%y.%m.%d}"
    ), note


def test_a_part_unset_wip_keeps_no_link_and_the_alarm_opens_the_target() -> None:
    """일부 주차만 비어 화면을 그리는 자리도 멈춘 자리(`WIP-01`)와 같은 원칙이다 — 자리에 「표준
    목표에서 주차별 가용설비 입력」 링크가 없고(네비게이션 없는 시험에서 링크가 물러서는 캡션 글도
    없다), 길은 그 Alarm 줄의 「그 화면으로」 다. 줄의 화면 칸 · 주소가 재공 현황이 아니라 표준
    목표다."""
    app = AppTest.from_string(_wip_part_unset_script(), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]

    # 화면은 그대로 선다 — 지표 · 격자 구획이 있고 마크가 없다.
    assert [metric.label for metric in app.metric][-1] == "표준 미설정"
    assert data_error_marks(app) == 0
    assert not app.get("page_link")
    assert not [item for item in app.caption if "표준 목표" in str(item.value)]
    note = active_state(app, "WIP-04")
    assert note is not None, states(app, "WIP-04")
    assert (note["page"], note["href"]) == (
        tab_label(STANDARD_TARGET_CAPA),
        STANDARD_TARGET_CAPA.href,
    )
    # 줄의 화면 칸이 표준 목표라 어느 화면의 기준선인지는 전문이 말한다 — 표준 목표에서 이 줄을 봐도
    # 표준 목표 자신의 문제로 읽히지 않게.
    assert note["full"].startswith("재공 현황 — "), note["full"]


def test_a_wip_baseline_alert_resolves_on_the_same_row_target() -> None:
    """빈 칸이 없는 회차도 같은 코드로 부르고(해소) 줄의 화면 칸 · 주소는 그대로 표준 목표다 — 해소
    표지가 줄을 재공 현황으로 돌려 놓지 않는다."""
    app = AppTest.from_string(WIP_SCRIPT, default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]

    (note,) = states(app, "WIP-04")
    assert note["active"] is False
    assert (note["page"], note["href"]) == (
        tab_label(STANDARD_TARGET_CAPA),
        STANDARD_TARGET_CAPA.href,
    )


# ---------------------------------------------------------------- 화면을 그리지 못한 오류


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BROKEN_ADMIN_SCRIPT = f"""
from pathlib import Path

import duckdb

import capa_simulation.persistence.cache as cache


def broken(path):
    raise duckdb.IOException("DEMO lock")


original = cache.get_scenario_repository
cache.get_scenario_repository = broken
try:
    source = Path({str(PROJECT_ROOT / "app_pages/admin_area.py")!r})
    code = compile(source.read_text(encoding="utf-8"), str(source), "exec")
    exec(code, {{"__name__": "__main__"}})
finally:
    cache.get_scenario_repository = original
"""


def test_a_screen_error_stands_as_a_mark_and_alerts_once_per_text() -> None:
    """화면을 그리지 못한 오류(`AD-07`)는 자리에 「데이터 Error」 마크만 서고 글은 같은 글이면 같은
    id 의 사건 알림으로만 간다 — 이 브라우저 탭에 한 번만 알림창이 뜬다
    (`components/data_error_mark.render_data_error`)."""
    first = AppTest.from_string(BROKEN_ADMIN_SCRIPT, default_timeout=60).run()
    assert data_error_marks(first) == 1 and not first.error
    (note,) = events(first, "AD-07")
    assert note["level"] == "error"
    assert note["short"] == "Admin Area 를 준비하지 못했습니다(시뮬레이션 DB)"
    assert "DEMO lock" in str(note["full"]), note
    assert str(note["id"]).startswith("page-")
    second = AppTest.from_string(BROKEN_ADMIN_SCRIPT, default_timeout=60).run()
    (again,) = events(second, "AD-07")
    assert again["id"] == note["id"]


def test_no_state_alert_box_is_left_in_the_area_b_screens_of_one_run() -> None:
    """이 갈래가 옮긴 상태 알림은 표지에만 있다 — 표지의 상태 알림 코드는 모두 등록부에 있다."""
    from capa_simulation import alerts

    app = AppTest.from_function(_admin_checks, args=(True, "DEMO"), default_timeout=30).run()
    for note in alert_notes(app):
        kind = "state" if note["kind"] == "state" else "event"
        assert alerts.spec(str(note["code"])).kind == kind, note
