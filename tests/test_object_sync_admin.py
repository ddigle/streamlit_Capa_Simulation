# Purpose: Admin 「DB 동기화」 펼침과 동기화 알림이 값 없이 판정만 싣고 local 에서는 없는지 지킨다.

"""`components/object_sync_status.py`.

- local(개발 · 사내 PC · 시험)에서는 펼침도 표지도 없다 — 요소 순번이 그대로다.
- 제목 끝이 판정이고, 본문은 라벨 · 값 줄이다. 주소 · 버킷 · 키가 없다.
- 「지금 올리기」 는 관리자 회차에만 있고, 콜백이 권한을 다시 본다.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from alert_marks import (
    GOTO_PRELUDE,
    GOTO_PRESS_KEY,
    active_state,
    alert_notes,
    box_expanded,
    flashed,
)
from fragment_browser import FragmentBrowser, install_fragment_browser
from sso_support import use_config
from streamlit.testing.v1 import AppTest
from test_sso_access import session_token

from capa_simulation import alerts, object_sync_worker, sync_boot
from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoConfig, SsoMode
from capa_simulation.components import object_sync_status, sso_identity
from capa_simulation.object_sync_worker import WorkerStatus
from capa_simulation.persistence import sync_state
from capa_simulation.sync_boot import SyncBoot

PANEL = """
from capa_simulation.components.object_sync_status import render_object_sync_status

render_object_sync_status()
"""
ALERTS = """
from capa_simulation.components.object_sync_status import render_object_sync_alerts

render_object_sync_alerts()
"""
NEIGHBOUR_BOX = "object_sync_test_neighbour_box"
# `app.py` 처럼 실행 표지를 맨 앞에 세우고 끝에서 닫는 페이지 — 펼침 곁에 여닫기 상자 하나.
PANEL_WITH_A_NEIGHBOUR_BOX = """
import streamlit as st

from capa_simulation.components.object_sync_status import render_object_sync_status
from capa_simulation.sidebar_status import begin_app_run, on_box_toggle

run = begin_app_run()
render_object_sync_status()
st.checkbox(
    "이웃 상자",
    key="object_sync_test_neighbour_box",
    on_change=on_box_toggle,
    args=("object_sync_test_neighbour_box", "이웃 상자"),
)
run.finish()
"""
SY_CODES = ("SY-01", "SY-02", "SY-03", "SY-04", "SY-05", "SY-06")
ADMIN = "demo.admin"
USER = "demo.user"


class _Handle:
    def __init__(self, status: WorkerStatus) -> None:
        self.current = status
        self.requests = 0

    def status(self) -> WorkerStatus:
        return self.current

    def request_now(self) -> None:
        self.requests += 1

    def stop(self, timeout: float | None = None) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolated() -> Iterator[None]:
    sync_state.clear_all()
    sync_boot.forget_boot_result()
    yield
    sync_state.clear_all()
    sync_boot.forget_boot_result()


def _boot(
    monkeypatch: pytest.MonkeyPatch,
    *,
    managed: bool = False,
    disabled_reason: str | None = None,
    handed_over_utc: str | None = None,
    head_ignored: bool = False,
    head_unchecked: tuple[str, ...] = (),
) -> None:
    decided = SyncBoot(managed, disabled_reason, handed_over_utc, head_ignored, head_unchecked)
    monkeypatch.setattr(sync_boot, "_boot", lambda: decided)


def _worker(monkeypatch: pytest.MonkeyPatch, **values: object) -> _Handle:
    idle = WorkerStatus(alive=True, phase=object_sync_worker.PHASE_IDLE, last_tick=time.monotonic())
    handle = _Handle(replace(idle, **values))  # type: ignore[arg-type]
    monkeypatch.setattr(object_sync_worker, "running_worker", lambda: handle)
    monkeypatch.setattr(object_sync_worker, "current_status", lambda: handle.current)
    return handle


def _admin(monkeypatch: pytest.MonkeyPatch, *, admin: bool = True) -> None:
    monkeypatch.setattr(object_sync_status, "_viewer_is_developer", lambda: admin)


def _labels(app: AppTest) -> list[str]:
    """펼침 제목. 아이콘이 달린 펼침을 AppTest 는 `status` 로 센다."""
    return [item.label for item in app.expander] + [item.label for item in app.status]


def _text(app: AppTest) -> str:
    return "\n".join([*(str(item.value) for item in app.caption), *_labels(app)])


def test_nothing_is_drawn_in_local_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """개발 · 사내 PC · 시험의 화면과 요소 순번이 그대로여야 한다."""
    _boot(monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(alerts, "state", lambda *args, **kwargs: calls.append(args[0]))

    panel = AppTest.from_string(PANEL).run()
    marks = AppTest.from_string(ALERTS).run()

    assert not list(panel.exception) and not list(marks.exception)
    assert _labels(panel) == []
    assert not list(panel.main.children.values())
    assert not list(marks.main.children.values())
    assert calls == []


def test_a_plain_local_app_has_no_worker_or_alert_chance() -> None:
    """설정을 바꾸지 않은 프로세스 — 실제 판정으로 본다."""
    assert sync_boot.is_managed() is False
    assert sync_boot.sync_alerts_possible() is False
    assert object_sync_worker.running_worker() is None


@pytest.mark.parametrize(
    ("values", "title"),
    [
        ({}, "DB 동기화 · 올릴 것 없음 :green-badge[CI/CD 눌러도 됨]"),
        ({"dirty": {"simulation": True}}, "DB 동기화 · 올릴 것 있음 :orange-badge[기다리세요]"),
        (
            {"phase": object_sync_worker.PHASE_UPLOADING},
            "DB 동기화 · 올리는 중 :orange-badge[기다리세요]",
        ),
        (
            {"failures": 3, "failure_kind": "denied"},
            "DB 동기화 · 실패 :red-badge[누르면 저장 잃음]",
        ),
        ({"blocked": "parent_moved"}, "DB 동기화 · 멈춤 :red-badge[누르면 저장 잃음]"),
    ],
)
def test_the_title_is_the_verdict(
    monkeypatch: pytest.MonkeyPatch, values: dict[str, object], title: str
) -> None:
    """펼침 제목 끝에 지금 CI/CD 를 눌러도 되는지 판정 배지 하나(색 + 낱말 — 카드 p2-sync)."""
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch, admin=False)
    _worker(monkeypatch, **values)

    app = AppTest.from_string(PANEL).run()

    assert not list(app.exception)
    assert _labels(app) == [title]


def test_every_health_title_has_a_cicd_verdict() -> None:
    """일꾼 판정 제목마다 CI/CD 판정이 있다 — 새 제목을 더하면 여기서 걸린다."""
    titles = {
        object_sync_worker.TITLE_CLEAN,
        object_sync_worker.TITLE_DIRTY,
        object_sync_worker.TITLE_UPLOADING,
        object_sync_worker.TITLE_FAILED,
        object_sync_worker.TITLE_BLOCKED,
    }
    assert set(object_sync_status.CICD_VERDICTS) == titles


def test_lines_carry_labels_and_numbers_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch, admin=False)
    _worker(
        monkeypatch,
        seq=12,
        last_success_utc="2026-11-07T00:00:00Z",
        sizes={"simulation": 62_800_000},
        lock_seconds=0.09,
        transfer_seconds=63.2,
        last_prune_utc="2026-11-07T01:00:00Z",
        last_prune_deleted=4,
        prune_failure="unreachable",
        failures=2,
        failure_kind="timeout",
    )

    app = AppTest.from_string(PANEL).run()

    text = _text(app)
    assert "**세대** · 12" in text
    assert "59.9 MiB" in text
    assert "**복사 잠금** · 0.09초" in text
    assert "**전송** · 63.2초" in text
    assert "**연속 실패** · 2회 · 시간 초과" in text
    assert "**정리 실패** · 저장소에 닿지 못함" in text


@pytest.mark.parametrize(
    ("origin", "line"),
    [
        ("boot", "**세대** · 2 (시작 펜스)"),
        ("app", "**세대** · 2"),
        ("rollback", "**세대** · 2"),
        (None, "**세대** · 2"),
    ],
)
def test_a_start_fence_generation_carries_a_tail_and_a_saved_one_does_not(
    monkeypatch: pytest.MonkeyPatch, origin: str | None, line: str
) -> None:
    """이관 직후 아무도 저장하지 않았는데 세대 2 가 올라가 「마지막 올림」 으로 보였다(사내 리뷰
    202611131000 정할 것 7 (가)). 펜스는 그대로 두고 세대 줄 끝에 꼬리 한 마디만 단다."""
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch, admin=False)
    _worker(monkeypatch, seq=2, origin=origin, last_success_utc="2026-11-13T07:14:16Z")

    app = AppTest.from_string(PANEL).run()

    captions = [str(item.value) for item in app.caption]
    assert any(line in caption.split("  \n") for caption in captions), captions
    assert ("시작 펜스" in _text(app)) is (origin == "boot")


def test_a_missing_worker_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch, admin=False)
    monkeypatch.setattr(object_sync_worker, "current_status", lambda: None)

    app = AppTest.from_string(PANEL).run()

    assert _labels(app) == ["DB 동기화 · 실패 :red-badge[누르면 저장 잃음]"]
    assert "동기화 일꾼이 돌지 않음" in _text(app)


def test_the_button_is_for_admins_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _boot(monkeypatch, managed=True)
    _worker(monkeypatch)

    _admin(monkeypatch, admin=False)
    viewer = AppTest.from_string(PANEL).run()
    _admin(monkeypatch)
    admin = AppTest.from_string(PANEL).run()

    assert [button.label for button in viewer.button] == []
    assert [button.label for button in admin.button] == ["지금 올리기"]


def test_the_button_only_asks_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """올리는 시간을 화면이 기다리지 않는다."""
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch)
    handle = _worker(monkeypatch)

    app = AppTest.from_string(PANEL).run()
    app.button(key=object_sync_status.UPLOAD_NOW_KEY).click().run()

    assert not list(app.exception)
    assert handle.requests == 1


def test_the_callback_checks_the_viewer_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """위젯 콜백은 본문보다 먼저 돈다 — 보인 회차의 권한을 믿지 않는다."""
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch)
    handle = _worker(monkeypatch)
    app = AppTest.from_string(PANEL).run()

    _admin(monkeypatch, admin=False)
    app.button(key=object_sync_status.UPLOAD_NOW_KEY).click().run()

    assert handle.requests == 0


def test_a_refused_upload_goes_to_the_alert_popup_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """거부는 그 자리에 고칠 입력이 없다 — 곁 상자 없이 알림창에만 뜬다(설계 규칙 UI-NTF-03)."""
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch)
    _worker(monkeypatch)
    app = AppTest.from_string(PANEL).run()

    _admin(monkeypatch, admin=False)
    app.button(key=object_sync_status.UPLOAD_NOW_KEY).click().run()

    assert not list(app.error)
    assert [item.value for item in flashed(app, "error")] == [object_sync_status.NOT_ADMIN_MESSAGE]


def test_the_button_is_locked_while_uploading(monkeypatch: pytest.MonkeyPatch) -> None:
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch)
    _worker(monkeypatch, phase=object_sync_worker.PHASE_UPLOADING)

    app = AppTest.from_string(PANEL).run()

    button = app.button(key=object_sync_status.UPLOAD_NOW_KEY)
    assert button.disabled is True
    assert button.help == object_sync_status.UPLOADING_WHY


# --- 열어 둔 화면이 따라가기(E2E C-11 · C-15 F3) ------------------------------------------------


def _live_fragment(browser: FragmentBrowser) -> str:
    """본문(복사 단추 · 값 줄)을 그린 프래그먼트 — 그 프래그먼트가 `run_every` 로 다시 돈다."""
    return browser.fragment_keyed("admin_area_object_sync_live")


def test_an_open_panel_follows_a_save_from_another_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """올릴 것이 없을 때 연 화면도 본문이 프래그먼트로 다시 돈다. 다른 회차가 저장하면 판정이
    달라지므로 앱 회차로 돌아가 제목 배지까지 고친다 — 그린 순간의 초록 「CI/CD 눌러도 됨」 이 남지
    않는다."""
    browser = install_fragment_browser(monkeypatch)
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch)
    handle = _worker(monkeypatch)
    app = AppTest.from_string(PANEL).run()
    assert _labels(app) == ["DB 동기화 · 올릴 것 없음 :green-badge[CI/CD 눌러도 됨]"]
    live = _live_fragment(browser)

    browser.fragment_queue = [live]
    app = app.run()
    assert not list(app.exception)
    assert browser.started == [[live]], "판정이 그대로면 프래그먼트만 돈다"

    handle.current = replace(handle.current, dirty={"simulation": True})
    browser.fragment_queue = [live]
    app = app.run()

    assert not list(app.exception)
    assert browser.started == [[live], []]
    assert _labels(app) == ["DB 동기화 · 올릴 것 있음 :orange-badge[기다리세요]"]


def test_a_panel_opened_while_uploading_unlocks_the_button_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = install_fragment_browser(monkeypatch)
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch)
    handle = _worker(monkeypatch, phase=object_sync_worker.PHASE_UPLOADING)
    app = AppTest.from_string(PANEL).run()
    assert app.button(key=object_sync_status.UPLOAD_NOW_KEY).disabled is True
    live = _live_fragment(browser)

    handle.current = replace(handle.current, phase=object_sync_worker.PHASE_IDLE, seq=3)
    browser.fragment_queue = [live]
    app = app.run()

    assert not list(app.exception)
    assert browser.started == [[live], []]
    assert app.button(key=object_sync_status.UPLOAD_NOW_KEY).disabled is False
    assert _labels(app) == ["DB 동기화 · 올릴 것 없음 :green-badge[CI/CD 눌러도 됨]"]


def test_the_panel_keeps_toggles_on_the_whole_app_while_it_watches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """여닫기 콜백이 앱 전체 요청을 프래그먼트 회차로 바꾸면 브라우저가 이미 지운 `run_every`
    시계를 다시 세울 회차가 오지 않는다 — 펼침이 선 실행 뒤의 여닫기는 앱 전체로 돈다(E2E 실측:
    이웃 상자를 여닫은 뒤 45초 동안 다시 돌지 않았다)."""
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch)
    _worker(monkeypatch)

    import streamlit as st_module

    from capa_simulation import sidebar_status

    monkeypatch.setattr(sidebar_status, "_current_page_hash", lambda: "page")
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(st_module, "rerun", lambda *args, **kwargs: calls.append(args))
    app = AppTest.from_string(PANEL_WITH_A_NEIGHBOUR_BOX).run()
    state = app.session_state[sidebar_status.APP_RUN_STATE_KEY]
    assert state["complete"] is True

    app.checkbox(key=NEIGHBOUR_BOX).check().run()

    assert not list(app.exception)
    assert calls == [], "앱 전체 재실행으로 물러난다"


def test_a_broken_setting_raises_the_off_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    """조용히 local 로 강등하지 않는다 — 사용자가 저장이 올라간다고 믿지 않게."""
    _boot(monkeypatch, disabled_reason="CAPA_S3_SYNC_MODE 는 local 또는 managed 여야 합니다")

    app = AppTest.from_string(ALERTS).run()

    assert not list(app.exception)
    assert active_state(app, "SY-01")
    assert not active_state(app, "SY-02")


def test_a_missing_worker_raises_the_overdue_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    _boot(monkeypatch, managed=True)
    monkeypatch.setattr(object_sync_worker, "current_status", lambda: None)

    app = AppTest.from_string(ALERTS).run()

    assert active_state(app, "SY-02")


def test_a_blocked_worker_raises_its_alert_and_it_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    _boot(monkeypatch, managed=True)
    handle = _worker(monkeypatch, blocked="forked")

    app = AppTest.from_string(ALERTS).run()
    assert active_state(app, "SY-03")

    handle.current = WorkerStatus(
        alive=True,
        phase=object_sync_worker.PHASE_IDLE,
        last_tick=time.monotonic(),
    )
    app.run()
    assert not active_state(app, "SY-03")


def test_a_handed_over_pc_raises_its_alert_in_local_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """사내 PC 앱은 local 이어도 그 DB 가 사본임을 안다."""
    _boot(monkeypatch, handed_over_utc="2026-11-07T00:00:00Z")

    app = AppTest.from_string(ALERTS).run()

    assert active_state(app, "SY-04")
    assert not active_state(app, "SY-02")


def test_the_codes_are_registered_as_states() -> None:
    for code in SY_CODES:
        assert alerts.REGISTRY[code].kind == "state"


def test_no_value_reaches_the_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """리뷰 압축본에 그대로 옮기는 자리다. 주소 · 버킷 · 키가 들어올 칸이 없어야 한다."""
    monkeypatch.setenv("CAPA_S3_BUCKET", "Demo_secret_bucket")
    monkeypatch.setenv("CAPA_S3_ENDPOINT_URL", "http://hidden.example.invalid:9020")
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch)
    _worker(monkeypatch, failures=3, failure_kind="unreachable")

    app = AppTest.from_string(PANEL).run()

    text = _text(app)
    assert "Demo_secret_bucket" not in text
    assert "hidden.example.invalid" not in text


def test_the_guide_explains_the_panel() -> None:
    guide = Path(alerts.__file__).parent / "guides" / "admin_area.md"

    assert "#### DB 동기화" in guide.read_text(encoding="utf-8")


def test_the_documents_keep_the_panel_between_the_two_checks() -> None:
    """운영 서버에서 「DB 동기화」 는 「서버 시작 점검」 과 「통합인증 점검」 사이에 선다 — 그
    서버를 보는 Guide 와 AGENTS 가 둘을 바로 잇지 않는다."""
    root = Path(__file__).resolve().parents[1]
    page = (root / "app_pages" / "admin_area.py").read_text(encoding="utf-8")
    calls = ("render_container_start_check()", "render_object_sync_status()", "render_sso_status()")
    moments = [page.index(call) for call in calls]
    assert moments == sorted(moments)
    guide = Path(alerts.__file__).parent / "guides" / "admin_area.md"
    assert "「서버 시작 점검」 · 「DB 동기화」 뒤에 서는" in guide.read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "그 뒤 `managed` 서버면 「DB 동기화」 펼침" in agents


def _app_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """빈 DuckDB 를 보는 `app.py`. 내장 시드가 부트스트랩을 채운다(`test_app_navigation` 꼴)."""
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
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    return AppTest.from_file(str(app_path), default_timeout=300)


def _sync_files(folder: Path) -> list[str]:
    return sorted(
        item.name
        for item in folder.iterdir()
        if item.name.endswith(".sync.json") or item.name == sync_state.GENERATION_FILENAME
    )


def test_a_local_app_stays_as_it_was(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """사내 PC · 개발 · 시험 — 알림 · 스레드 · 파일이 늘지 않는다. 시드 저장도 표시를 안 남긴다."""
    app = _app_test(tmp_path, monkeypatch).run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert not [note for note in alert_notes(app) if str(note.get("code", "")).startswith("SY-")]
    assert object_sync_worker.running_worker() is None
    assert _sync_files(tmp_path) == []
    assert not sync_state.is_enabled(tmp_path / "scenario.duckdb")


def test_a_broken_setting_keeps_the_app_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """조용히 local 로 강등하지 않고 앱도 막지 않는다(2026-10-22 결정 (다))."""
    from capa_simulation.io import object_storage

    def broken() -> object_storage.StorageSettings:
        raise object_storage.ObjectStorageError("CAPA_S3_SYNC_MODE 는 local 또는 managed")

    monkeypatch.setattr(sync_boot, "load_settings", broken)

    app = _app_test(tmp_path, monkeypatch).run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert active_state(app, "SY-01")


def test_a_server_that_did_not_read_the_bucket_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """빈 값은 유효한 `local` 이라 `SY-01` 이 서지 않는다. 이 알림이 없으면 화면이 멀쩡해 보인다."""
    _boot(monkeypatch, head_ignored=True)

    app = AppTest.from_string(ALERTS).run()

    note = active_state(app, "SY-05")
    assert note is not None
    assert "CAPA_S3_SYNC_MODE" in note["full"]
    assert not active_state(app, "SY-01")


def test_a_server_that_could_not_list_the_bucket_names_the_missing_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """빈 CD 환경변수로 버킷 목록을 못 보면 `SY-05` 를 세울지 모른다 — 넣을 이름을 대는 `SY-06`."""
    _boot(monkeypatch, head_unchecked=("CAPA_S3_PROFILE",))

    app = AppTest.from_string(ALERTS).run()

    note = active_state(app, "SY-06")
    assert note is not None
    assert "CAPA_S3_PROFILE" in note["short"] and "CAPA_S3_PROFILE" in note["full"]
    assert not active_state(app, "SY-05")
    assert not active_state(app, "SY-01")


def test_a_wrong_mode_reaches_the_alert_as_a_word(monkeypatch: pytest.MonkeyPatch) -> None:
    """`SY-01` 은 로그인한 사람 모두가 본다. 잘못 붙여 넣은 값이 실리면 안 된다."""
    monkeypatch.setenv("CAPA_S3_SYNC_MODE", "pasted-demo-value-1234")

    app = AppTest.from_string(ALERTS).run()

    note = active_state(app, "SY-01")
    assert note is not None
    assert "pasted-demo-value-1234" not in str(note)
    assert "모드 값 틀림" in note["full"]


# --------------------------------------------------------------------------- 실제 신원 판정
def _real_viewer(monkeypatch: pytest.MonkeyPatch, *, cookie: str | None) -> SsoConfig:
    """`_viewer_is_developer` 을 바꿔 끼우지 않는다 — 쿠키만 주고 판정 길을 그대로 태운다."""
    cfg = use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER})
    cookies = {} if cookie is None else {cfg.session_cookie: session_token(cfg, cookie)}
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: cookies)
    return cfg


@pytest.mark.parametrize(
    ("cookie", "expected"), [(ADMIN, True), (USER, False), (None, False)], ids=str
)
def test_the_viewer_is_judged_from_the_cookie(
    monkeypatch: pytest.MonkeyPatch, cookie: str | None, expected: bool
) -> None:
    _real_viewer(monkeypatch, cookie=cookie)

    assert object_sync_status._viewer_is_developer() is expected


def test_a_tampered_cookie_is_not_an_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _real_viewer(monkeypatch, cookie=ADMIN)
    head, payload, signature = session_token(cfg, ADMIN).split(".")
    forged = {cfg.session_cookie: f"{head}.{payload}.{signature[::-1]}"}
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: forged)

    assert object_sync_status._viewer_is_developer() is False


def test_nobody_is_an_admin_with_sso_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """꺼진 서버에는 신원이 없다. 쿠키가 남아 있어도 단추는 서지 않는다."""
    cfg = _real_viewer(monkeypatch, cookie=ADMIN)
    token = session_token(cfg, ADMIN)
    runtime.reset()
    off = runtime.start({})
    assert off.mode is not SsoMode.ON
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: {cfg.session_cookie: token})

    assert object_sync_status._viewer_is_developer() is False


def test_a_stale_button_of_someone_who_lost_the_right_does_not_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """관리자 회차의 단추를 일반 쿠키로 누른다 — 콜백은 그 회차 쿠키로 다시 본다."""
    _boot(monkeypatch, managed=True)
    cfg = _real_viewer(monkeypatch, cookie=ADMIN)
    handle = _worker(monkeypatch)
    app = AppTest.from_string(PANEL).run()
    button = app.button(key=object_sync_status.UPLOAD_NOW_KEY)
    lowered = {cfg.session_cookie: session_token(cfg, USER)}
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: lowered)

    button.click().run()

    assert not list(app.exception)
    assert handle.requests == 0


def _view(monkeypatch: pytest.MonkeyPatch, *, admin: bool) -> None:
    """개발자 상태 알림 판정(`admin_view.developer_alerts_visible`)을 바꿔 끼운다."""
    monkeypatch.setattr(object_sync_status, "developer_alerts_visible", lambda: admin)


@pytest.mark.parametrize("admin", [True, False], ids=["admin", "user"])
def test_a_server_that_skipped_the_canon_says_so_in_plain_words(
    monkeypatch: pytest.MonkeyPatch, admin: bool
) -> None:
    """`SY-05` 짧은 글은 누구나 읽는 꼴이고, 환경변수 칸 · CI/CD 지시는 관리자 몫 전문에만 있다(카드
    p1-not-canonical)."""
    _boot(monkeypatch, head_ignored=True)
    _view(monkeypatch, admin=admin)

    app = AppTest.from_string(ALERTS).run()

    note = active_state(app, "SY-05")
    assert note is not None
    assert note["short"] == "정본이 아닌 데이터 — 여기 저장은 다음 배포에 사라집니다"
    assert ("CAPA_S3_SYNC_MODE" in str(note["full"])) is admin
    assert ("개발자에게 알려 주세요" in str(note["full"])) is not admin


@pytest.mark.parametrize("admin", [True, False], ids=["admin", "user"])
def test_a_broken_setting_says_saves_do_not_reach_the_canon(
    monkeypatch: pytest.MonkeyPatch, admin: bool
) -> None:
    """`SY-01` 짧은 글은 「저장이 정본에 올라가지 않습니다」 하나이고 설정 파일 이름은 관리자
    몫에만."""
    _boot(monkeypatch, disabled_reason="CAPA_S3_SYNC_MODE 는 local 또는 managed 여야 합니다")
    _view(monkeypatch, admin=admin)

    app = AppTest.from_string(ALERTS).run()

    note = active_state(app, "SY-01")
    assert note is not None
    assert note["short"] == "저장이 정본에 올라가지 않습니다"
    assert ("config/object_storage.json" in str(note["full"])) is admin


@pytest.mark.parametrize("admin", [True, False], ids=["admin", "user"])
def test_an_unchecked_canon_is_for_the_admin_only(
    monkeypatch: pytest.MonkeyPatch, admin: bool
) -> None:
    """정본 점검을 못 한 서버(`SY-06`)는 일반 사용자가 할 일이 없어 관리자 몫에만 선다. 관리자가
    아닌 회차도 같은 수의 표지를 쓴다(조건만 거짓)."""
    _boot(monkeypatch, head_unchecked=("CAPA_S3_PROFILE",))
    _view(monkeypatch, admin=admin)

    app = AppTest.from_string(ALERTS).run()

    assert (active_state(app, "SY-06") is not None) is admin
    assert len([note for note in alert_notes(app) if note["code"] in SY_CODES]) == 6


@pytest.mark.parametrize(
    ("boot", "code"),
    [
        ({"head_ignored": True}, "SY-05"),
        ({"disabled_reason": "꼴이 틀림", "head_ignored": True}, "SY-05"),
        ({"disabled_reason": "꼴이 틀림"}, "SY-01"),
        ({"head_unchecked": ("CAPA_S3_PROFILE",)}, None),
        ({"managed": True}, None),
        ({}, None),
    ],
)
def test_the_head_mark_names_the_code_of_a_server_off_the_canon(
    monkeypatch: pytest.MonkeyPatch, boot: dict[str, object], code: str | None
) -> None:
    """머리 띠 「정본 아님」 표지는 정본을 받지 않은 서버(`SY-05`)와 동기화가 꺼진 서버(`SY-01`)에만
    선다 — 점검을 못 한 서버(`SY-06`)는 정본이 아닌지 모른다."""
    _boot(monkeypatch, **boot)  # type: ignore[arg-type]

    assert object_sync_status.not_canonical_code() == code


@pytest.mark.parametrize("admin", [True, False], ids=["admin", "user"])
def test_an_upload_that_cannot_reach_the_canon_asks_the_user_to_tell_the_admin(
    monkeypatch: pytest.MonkeyPatch, admin: bool
) -> None:
    """`SY-02` · `SY-03` 짧은 글은 일반 사용자에게 「— 개발자에게 알려 주세요」 이고, 관리자 몫은
    갈래 · 런북 · 「그 화면으로」 Admin 「DB 동기화」 다. 일꾼이 서지 않은 서버의 관리자 전문에는
    CI/CD 를 누르면 저장이 사라진다는 한 줄이 붙는다(카드 p2-sync)."""
    _boot(monkeypatch, managed=True)
    _view(monkeypatch, admin=admin)
    monkeypatch.setattr(object_sync_worker, "current_status", lambda: None)

    app = AppTest.from_string(ALERTS).run()

    overdue = active_state(app, "SY-02")
    assert overdue is not None
    if admin:
        assert overdue["short"] == "저장이 정본에 올라가지 못함 — 동기화 일꾼이 돌지 않음"
        assert str(overdue["full"]).endswith(object_sync_status.WORKER_ABSENT_LINE)
        assert overdue["href"] == "admin_area"
    else:
        assert overdue["short"] == "저장이 정본에 올라가지 못함 — 개발자에게 알려 주세요"
        assert "Admin" not in str(overdue["full"]) and "CI/CD" not in str(overdue["full"])
        assert overdue.get("href", "") != "admin_area"

    handle = _worker(monkeypatch, blocked="forked")
    app.run()
    blocked = active_state(app, "SY-03")
    assert blocked is not None and handle is not None
    if admin:
        assert blocked["short"] == "올리기가 멈춤 — 원격이 갈라짐"
        assert "런북" in str(blocked["full"])
    else:
        assert blocked["short"] == "올리기가 멈춤 — 개발자에게 알려 주세요"
        assert "런북" not in str(blocked["full"])


# 다른 화면 ↔ Admin 「DB 동기화」 — `app.py` 가 회차마다 내는 동기화 알림과 알림 칸 「그 화면으로」
# 의 콜백(`GOTO_PRELUDE`). 세션 `test_page` 가 `admin` 일 때만 펼침을 그린다.
PANEL_AFTER_GOTO = (
    GOTO_PRELUDE
    + """
import streamlit as st

from capa_simulation.components.object_sync_status import (
    render_object_sync_alerts,
    render_object_sync_status,
)

render_object_sync_alerts()
if st.session_state.get("test_page") == "admin":
    render_object_sync_status()
"""
)


def test_the_upload_alerts_open_the_db_sync_box_from_another_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """관리자 몫 `SY-02` · `SY-03` 의 「그 화면으로」 는 다른 화면에서 눌러도 Admin 「DB 동기화」
    펼침까지 연다(설계 규칙 UI-NAV-01 — 전문이 「Admin 「DB 동기화」 를 보세요」 다). 관리자가 아닌
    회차에는 「그 화면으로」 도 대상도 없다."""
    from capa_simulation.components import alert_center

    _boot(monkeypatch, managed=True)
    _view(monkeypatch, admin=True)
    _admin(monkeypatch)
    monkeypatch.setattr(object_sync_worker, "current_status", lambda: None)
    app = AppTest.from_string(PANEL_AFTER_GOTO)
    app.session_state["test_page"] = "other"
    app.run()
    overdue = active_state(app, "SY-02")
    assert overdue is not None and overdue["href"] == "admin_area"
    assert overdue["target"]["kind"] == object_sync_status.SYNC_TARGET_KIND

    app.session_state["test_page"] = "admin"
    app.run()
    assert box_expanded(app, object_sync_status.EXPANDER_KEY) is False
    app.session_state[GOTO_PRESS_KEY] = overdue["target"]
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert box_expanded(app, object_sync_status.EXPANDER_KEY) is True
    receiver = alert_center.GOTO_RECEIVERS[object_sync_status.SYNC_TARGET_KIND]
    assert receiver is object_sync_status.open_sync_panel

    _worker(monkeypatch, blocked="forked")
    app.run()
    blocked = active_state(app, "SY-03")
    assert blocked is not None and blocked["target"] == overdue["target"]

    _view(monkeypatch, admin=False)
    app.run()
    user_blocked = active_state(app, "SY-03")
    assert user_blocked is not None and "target" not in user_blocked
    assert user_blocked.get("href", "") != "admin_area"


def test_a_handed_over_copy_tells_the_moment_in_korean_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """넘긴 시각은 KST 분까지 — UTC ISO 그대로면 KST 0 ~ 9시에 넘긴 사본이 하루 앞 날짜로 읽혔다
    (E2E E-10)."""
    _boot(monkeypatch, handed_over_utc="2026-11-14T16:43:02Z")

    app = AppTest.from_string(ALERTS).run()

    note = active_state(app, "SY-04")
    assert note is not None
    assert str(note["full"]).startswith("이 DB 는 2026-11-15 01:43 에 정본을 넘긴 사본입니다.")
    assert "T16:43" not in str(note["full"])


def test_a_handed_over_copy_says_how_to_get_fresh_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """정본을 넘긴 사본(`SY-04`)의 전문은 최신 데이터를 보려면 사본을 다시 받으라고 끝난다 — 할
    일은 런북을 가리키고 스크립트 이름은 싣지 않는다(카드 p2-sync 글 그대로)."""
    _boot(monkeypatch, handed_over_utc="2026-11-07T00:00:00Z")

    app = AppTest.from_string(ALERTS).run()

    note = active_state(app, "SY-04")
    assert note is not None
    assert str(note["full"]).endswith("최신 데이터를 보려면 사본을 다시 받습니다(런북).")
    assert "sync_object_storage" not in str(note["full"])
