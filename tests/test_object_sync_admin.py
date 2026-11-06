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

import pytest
from alert_marks import active_state
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts, object_sync_worker, sync_boot
from capa_simulation.components import object_sync_status
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
SY_CODES = ("SY-01", "SY-02", "SY-03", "SY-04")


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
) -> None:
    decided = SyncBoot(managed, disabled_reason, handed_over_utc)
    monkeypatch.setattr(sync_boot, "_boot", lambda: decided)


def _worker(monkeypatch: pytest.MonkeyPatch, **values: object) -> _Handle:
    idle = WorkerStatus(alive=True, phase=object_sync_worker.PHASE_IDLE, last_tick=time.monotonic())
    handle = _Handle(replace(idle, **values))  # type: ignore[arg-type]
    monkeypatch.setattr(object_sync_worker, "running_worker", lambda: handle)
    monkeypatch.setattr(object_sync_worker, "current_status", lambda: handle.current)
    return handle


def _admin(monkeypatch: pytest.MonkeyPatch, *, admin: bool = True) -> None:
    monkeypatch.setattr(object_sync_status, "_viewer_is_admin", lambda: admin)


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
        ({}, "DB 동기화 · 올릴 것 없음"),
        ({"dirty": {"simulation": True}}, "DB 동기화 · 올릴 것 있음"),
        ({"phase": object_sync_worker.PHASE_UPLOADING}, "DB 동기화 · 올리는 중"),
        ({"failures": 3, "failure_kind": "denied"}, "DB 동기화 · 실패"),
        ({"blocked": "parent_moved"}, "DB 동기화 · 멈춤"),
    ],
)
def test_the_title_is_the_verdict(
    monkeypatch: pytest.MonkeyPatch, values: dict[str, object], title: str
) -> None:
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch, admin=False)
    _worker(monkeypatch, **values)

    app = AppTest.from_string(PANEL).run()

    assert not list(app.exception)
    assert _labels(app) == [title]


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


def test_a_missing_worker_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch, admin=False)
    monkeypatch.setattr(object_sync_worker, "current_status", lambda: None)

    app = AppTest.from_string(PANEL).run()

    assert _labels(app) == ["DB 동기화 · 실패"]
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


def test_the_button_is_locked_while_uploading(monkeypatch: pytest.MonkeyPatch) -> None:
    _boot(monkeypatch, managed=True)
    _admin(monkeypatch)
    _worker(monkeypatch, phase=object_sync_worker.PHASE_UPLOADING)

    app = AppTest.from_string(PANEL).run()

    button = app.button(key=object_sync_status.UPLOAD_NOW_KEY)
    assert button.disabled is True
    assert button.help == object_sync_status.UPLOADING_WHY


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
    from pathlib import Path

    guide = Path(alerts.__file__).parent / "guides" / "admin_area.md"

    assert "#### DB 동기화" in guide.read_text(encoding="utf-8")
