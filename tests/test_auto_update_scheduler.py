# Purpose: 자동 갱신 예약의 실행 줄 허락·지정 시각 판단·따라잡지 않음·선점·재시도를 고정한다.

"""공식버전 자동 갱신 예약(`auto_update_scheduler`).

판단(`AutoUpdateScheduler.tick`)은 스레드 없이 부르고 시계를 주입한다. 회차 함수는 기록만 하는
가짜를 넣거나, 끝까지 가는 시험에서는 실제 회차(`run_auto_official_update`)에 가짜 BigDataQuery 를
넣는다 — 사외에서는 BigDataQuery 를 부를 수 없다.
"""

from __future__ import annotations

import logging
import os
import threading
import time as wall_time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest
from auto_update_fakes import (
    FakeBigDataQuery,
    catalog_frame,
    new_repository,
    official_w40,
)
from streamlit.runtime.scriptrunner_utils import script_run_context

import capa_simulation.auto_update_scheduler as scheduler_module
from capa_simulation.auto_official_update_runner import (
    ALREADY_CLAIMED_MESSAGE,
    BUSY_MESSAGE,
    AutoUpdateRunResult,
)
from capa_simulation.auto_update_scheduler import (
    ENV_VAR,
    THREAD_NAME,
    AutoUpdateScheduler,
    ensure_auto_update_scheduler,
    running_scheduler,
    scheduler_opted_in,
)
from capa_simulation.persistence.cache import clear_global_securement_threshold_cache
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.auto_official_update import (
    STATUS_ERROR,
    STATUS_PUBLISHED,
    STATUS_RUNNING,
    TRIGGER_SCHEDULED,
    AutoUpdateConfig,
)

DAY = date(2026, 10, 15)
SLOT = time(7, 0)


def _at(hour: int, minute: int, second: int = 0, *, day: date = DAY) -> datetime:
    return datetime.combine(day, time(hour, minute, second))


@dataclass
class Clock:
    """손으로 돌리는 시계."""

    now: datetime

    def __call__(self) -> datetime:
        return self.now

    def to(self, moment: datetime) -> None:
        self.now = moment


@dataclass
class RecordingRun:
    """회차 함수 대역. 부른 인자를 남기고 정해 둔 결과를 차례로 돌려준다."""

    results: list[AutoUpdateRunResult | BaseException] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, repository: DuckDBScenarioRepository, **kwargs: Any) -> AutoUpdateRunResult:
        self.calls.append(kwargs)
        outcome: AutoUpdateRunResult | BaseException = (
            self.results.pop(0) if self.results else AutoUpdateRunResult(None, "가짜 회차")
        )
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    @property
    def days(self) -> list[date]:
        return [call["run_day"] for call in self.calls]


@pytest.fixture
def repository(tmp_path: Path) -> DuckDBScenarioRepository:
    return new_repository(tmp_path / "auto_scheduler.duckdb")


def _enable(
    repository: DuckDBScenarioRepository,
    *,
    enabled: bool = True,
    check_time: time = SLOT,
) -> None:
    current = repository.load_auto_official_update_settings()
    repository.replace_auto_official_update_settings(
        AutoUpdateConfig(
            enabled=enabled,
            check_time=check_time,
            keyword=current.config.keyword,
            threshold=current.config.threshold,
        ),
        expected_version=current.version,
    )


def _scheduler(
    repository: DuckDBScenarioRepository, clock: Clock, run: RecordingRun
) -> AutoUpdateScheduler:
    return AutoUpdateScheduler(repository, clock=clock, run=run, after_publish=None)


# ---------------------------------------------------------------------------
# 실행 줄 허락
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("true", True), (" ON ", True), ("yes", True), ("0", False), ("", False)],
)
def test_only_an_explicit_opt_in_value_allows_the_schedule(value: str, expected: bool) -> None:
    assert scheduler_opted_in({ENV_VAR: value}) is expected


def test_the_test_session_strips_the_opt_in() -> None:
    """conftest 가 실행 줄 허락을 뺀다 — 앱을 띄운 창에서 pytest 를 돌려도 예약이 서지 않는다."""
    from conftest import AUTO_UPDATE_ENV_VAR

    assert AUTO_UPDATE_ENV_VAR == ENV_VAR
    assert ENV_VAR not in os.environ
    assert not scheduler_opted_in()


def test_without_the_opt_in_no_thread_is_started(tmp_path: Path) -> None:
    """화면 확인 스크립트의 자식 앱·AppTest·개발 실행은 허락이 없다 — 스레드가 서지 않는다."""
    assert ensure_auto_update_scheduler(str(tmp_path / "unused.duckdb"), environ={}) is None
    assert running_scheduler() is None
    assert not any(thread.name == THREAD_NAME for thread in threading.enumerate())
    assert not (tmp_path / "unused.duckdb").exists()


# ---------------------------------------------------------------------------
# 지정 시각 판단
# ---------------------------------------------------------------------------


def test_nothing_runs_before_the_check_time(repository: DuckDBScenarioRepository) -> None:
    _enable(repository)
    clock = Clock(_at(6, 58))
    run = RecordingRun()
    scheduler = _scheduler(repository, clock, run)

    clock.to(_at(6, 58, 30))
    outcome = scheduler.tick()
    clock.to(_at(6, 59, 59))
    scheduler.tick()

    assert outcome.kind == "waiting"
    assert run.calls == []


def test_crossing_the_check_time_runs_the_scheduled_round_once(
    repository: DuckDBScenarioRepository,
) -> None:
    _enable(repository)
    clock = Clock(_at(6, 59, 40))
    run = RecordingRun([AutoUpdateRunResult(None, ALREADY_CLAIMED_MESSAGE)])
    scheduler = _scheduler(repository, clock, run)

    clock.to(_at(7, 0, 10))
    crossed = scheduler.tick()
    clock.to(_at(7, 0, 40))
    after = scheduler.tick()

    assert crossed.kind == "not_run" and crossed.run_day == DAY
    assert after.kind == "waiting"
    assert run.days == [DAY]
    assert run.calls[0]["trigger"] == TRIGGER_SCHEDULED


def test_starting_after_the_check_time_skips_that_day_and_waits_for_the_next(
    repository: DuckDBScenarioRepository,
) -> None:
    """앱이 지정 시각에 떠 있지 않았으면(그 뒤에 떴으면) 따라잡지 않고 다음 날 그 시각에 돈다."""
    _enable(repository)
    clock = Clock(_at(7, 5))
    run = RecordingRun()
    scheduler = _scheduler(repository, clock, run)

    for minute in range(5, 60, 5):
        clock.to(_at(7, minute, 30))
        scheduler.tick()
    assert run.calls == []

    next_day = DAY + timedelta(days=1)
    # 밤새 30초마다 확인했다고 치고, 다음 날 지정 시각 앞뒤만 본다.
    clock.to(_at(6, 59, 50, day=next_day))
    scheduler._previous = _at(6, 59, 20, day=next_day)
    scheduler.tick()
    clock.to(_at(7, 0, 20, day=next_day))
    outcome = scheduler.tick()

    assert outcome.run_day == next_day
    assert run.days == [next_day]


def test_a_long_gap_between_checks_means_the_app_slept_and_is_not_caught_up(
    repository: DuckDBScenarioRepository,
) -> None:
    _enable(repository)
    clock = Clock(_at(6, 30))
    run = RecordingRun()
    scheduler = _scheduler(repository, clock, run)

    clock.to(_at(7, 30))  # 한 시간 동안 확인이 없었다(PC 절전 등)
    outcome = scheduler.tick()

    assert outcome.kind == "waiting"
    assert run.calls == []


def test_a_disabled_toggle_never_runs_and_is_reread_every_check(
    repository: DuckDBScenarioRepository,
) -> None:
    _enable(repository, enabled=False)
    clock = Clock(_at(6, 59, 40))
    run = RecordingRun()
    scheduler = _scheduler(repository, clock, run)

    clock.to(_at(7, 0, 10))
    assert scheduler.tick().kind == "disabled"
    assert run.calls == []

    # 화면에서 시각을 뒤로 미루고 켜면 다음 확인부터 그 값으로 돈다.
    _enable(repository, enabled=True, check_time=time(7, 1))
    clock.to(_at(7, 0, 40))
    assert scheduler.tick().kind == "waiting"
    clock.to(_at(7, 1, 10))
    assert scheduler.tick().run_day == DAY
    assert run.days == [DAY]


def test_turning_the_toggle_off_stops_the_next_round(repository: DuckDBScenarioRepository) -> None:
    _enable(repository)
    clock = Clock(_at(6, 59, 40))
    run = RecordingRun()
    scheduler = _scheduler(repository, clock, run)

    _enable(repository, enabled=False)
    clock.to(_at(7, 0, 10))
    scheduler.tick()

    assert run.calls == []


# ---------------------------------------------------------------------------
# 회차를 잡지 못했을 때
# ---------------------------------------------------------------------------


def test_a_busy_round_is_retried_the_same_day_but_not_the_next(
    repository: DuckDBScenarioRepository,
) -> None:
    """「지금 실행」이 도는 중이면 예약은 선점하지 않고 돌아와 같은 날 다음 확인에 다시 잡는다."""
    _enable(repository)
    clock = Clock(_at(6, 59, 40))
    run = RecordingRun(
        [
            AutoUpdateRunResult(None, BUSY_MESSAGE),
            AutoUpdateRunResult(None, ALREADY_CLAIMED_MESSAGE),
        ]
    )
    scheduler = _scheduler(repository, clock, run)

    clock.to(_at(7, 0, 10))
    first = scheduler.tick()
    assert first.kind == "not_run" and scheduler.status().pending_day == DAY
    clock.to(_at(7, 0, 40))
    scheduler.tick()
    assert scheduler.status().pending_day is None
    clock.to(_at(7, 1, 10))
    scheduler.tick()

    assert run.days == [DAY, DAY]


def test_a_pending_retry_does_not_carry_over_midnight(
    repository: DuckDBScenarioRepository,
) -> None:
    _enable(repository, check_time=time(23, 59))
    clock = Clock(_at(23, 58, 50))
    run = RecordingRun([AutoUpdateRunResult(None, BUSY_MESSAGE)])
    scheduler = _scheduler(repository, clock, run)

    clock.to(_at(23, 59, 20))
    scheduler.tick()
    clock.to(_at(0, 0, 10, day=DAY + timedelta(days=1)))
    scheduler.tick()

    assert run.days == [DAY]
    assert scheduler.status().pending_day is None


def test_a_failure_before_the_claim_is_retried_and_the_thread_keeps_going(
    repository: DuckDBScenarioRepository,
) -> None:
    """선점 전 실패(다른 프로세스가 DB 를 쥠 등)는 올라오지 않고 같은 날 다시 시도한다."""
    _enable(repository)
    clock = Clock(_at(6, 59, 40))
    run = RecordingRun(
        [duckdb.IOException("Conflicting lock is held"), AutoUpdateRunResult(None, "잡힘")]
    )
    scheduler = _scheduler(repository, clock, run)

    clock.to(_at(7, 0, 10))
    failed = scheduler.tick()
    clock.to(_at(7, 0, 40))
    scheduler.tick()

    assert failed.kind == "run_error" and failed.message is not None
    assert "IOException" in failed.message
    assert run.days == [DAY, DAY]


def test_settings_that_cannot_be_read_keep_the_previous_check_for_the_next_one(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """설정을 못 읽은 확인은 「직전 확인」을 옮기지 않는다 — 다음 확인이 지난 시각을 본다."""
    _enable(repository)
    clock = Clock(_at(6, 59, 40))
    run = RecordingRun()
    scheduler = _scheduler(repository, clock, run)
    real_load = repository.load_auto_official_update_settings

    def locked() -> Any:
        raise duckdb.IOException("Conflicting lock is held")

    monkeypatch.setattr(repository, "load_auto_official_update_settings", locked)
    clock.to(_at(7, 0, 10))
    assert scheduler.tick().kind == "settings_error"
    monkeypatch.setattr(repository, "load_auto_official_update_settings", real_load)
    clock.to(_at(7, 0, 40))
    outcome = scheduler.tick()

    assert outcome.run_day == DAY
    assert run.days == [DAY]


def test_settings_failures_are_logged_once_and_the_recovery_once(
    repository: DuckDBScenarioRepository,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """30초마다 같은 경고가 쌓이지 않는다 — 처음 한 번, 회복 때 한 번."""
    _enable(repository)
    clock = Clock(_at(6, 0))
    scheduler = _scheduler(repository, clock, RecordingRun())
    real_load = repository.load_auto_official_update_settings

    def locked() -> Any:
        raise duckdb.IOException("Conflicting lock is held")

    caplog.set_level(logging.WARNING, logger=scheduler_module.__name__)
    monkeypatch.setattr(repository, "load_auto_official_update_settings", locked)
    for second in (10, 40, 70):
        clock.to(_at(6, 0) + timedelta(seconds=second))
        assert scheduler.tick().kind == "settings_error"
    monkeypatch.setattr(repository, "load_auto_official_update_settings", real_load)
    clock.to(_at(6, 2))
    scheduler.tick()
    scheduler.tick()

    messages = [record.getMessage() for record in caplog.records]
    assert sum("읽지 못했습니다" in message for message in messages) == 1
    assert sum("다시 읽었습니다" in message for message in messages) == 1


def test_a_round_in_progress_shows_as_running(repository: DuckDBScenarioRepository) -> None:
    """회차가 끝날 때까지 확인은 돌아오지 않는다 — 그 사이 상태는 「회차 진행 중」과 시작 시각."""
    _enable(repository)
    clock = Clock(_at(6, 59, 40))
    seen: list[str] = []
    holder: list[AutoUpdateScheduler] = []

    def watching_run(repository: DuckDBScenarioRepository, **kwargs: Any) -> AutoUpdateRunResult:
        outcome = holder[0].status().last_outcome
        seen.append("" if outcome is None else outcome.kind)
        return AutoUpdateRunResult(None, "가짜 회차")

    scheduler = AutoUpdateScheduler(repository, clock=clock, run=watching_run, after_publish=None)
    holder.append(scheduler)
    clock.to(_at(7, 0, 10))

    assert scheduler.tick().kind == "not_run"
    assert seen == ["running"]


# ---------------------------------------------------------------------------
# 실제 회차와 함께
# ---------------------------------------------------------------------------


def test_the_scheduled_round_publishes_once_per_day_even_across_restarts(
    repository: DuckDBScenarioRepository,
) -> None:
    """같은 날 두 번째 프로세스(재시작)가 같은 시각을 지나도 회차 선점이 막는다."""
    official_w40(repository)
    _enable(repository)
    fake = FakeBigDataQuery(catalog_frame(("PSM W41", "SIM-W41", "2026-10-12 09:00:00")))
    cleared: list[str] = []
    clock = Clock(_at(6, 59, 40))
    scheduler = AutoUpdateScheduler(
        repository,
        clock=clock,
        sources=fake.sources,
        after_publish=lambda: cleared.append("cleared"),
    )

    clock.to(_at(7, 0, 10))
    outcome = scheduler.tick()

    assert outcome.kind == "ran" and outcome.run is not None
    assert (outcome.run.status, outcome.run.trigger_kind) == (STATUS_PUBLISHED, TRIGGER_SCHEDULED)
    assert outcome.run.run_key == "scheduled:2026-10-15"
    assert cleared == ["cleared"]

    restarted_clock = Clock(_at(6, 59, 50))
    restarted = AutoUpdateScheduler(repository, clock=restarted_clock, sources=fake.sources)
    restarted_clock.to(_at(7, 0, 20))
    again = restarted.tick()

    assert again.kind == "not_run" and again.message == ALREADY_CLAIMED_MESSAGE
    assert len(repository.list_auto_official_update_runs()) == 1
    assert repository.latest_official_release().release_no == 2  # type: ignore[union-attr]


def test_the_first_check_closes_runs_left_running_by_an_earlier_process(
    repository: DuckDBScenarioRepository,
) -> None:
    run_id = repository.claim_auto_official_update_run(
        run_key="manual:old",
        trigger_kind="MANUAL",
        run_date=DAY,
        started_at=_at(6, 0),
        keyword="PSM",
        threshold=0.8,
        settings_version=0,
    )
    assert run_id is not None
    clock = Clock(_at(6, 30))
    scheduler = _scheduler(repository, clock, RecordingRun())

    clock.to(_at(6, 30, 30))
    scheduler.tick()

    run = repository.load_auto_official_update_run(run_id)
    assert run.status == STATUS_ERROR and run.reason is not None
    assert repository.load_auto_official_update_run(run_id).status != STATUS_RUNNING


def test_clearing_the_threshold_cache_needs_no_script_run_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """발행 뒤 정리는 배경 스레드에서 부른다 — 실행 문맥을 찾지 않고 지워야 한다.

    전역 범위 `st.cache_data` 의 `.clear()` 는 세션을 묻지 않는다. 문맥을 찾는 순간 실패하게 바꿔
    두고 문맥 없는 스레드에서 부른다.
    """

    def no_context() -> None:
        raise AssertionError("배경 스레드가 실행 문맥을 찾았습니다")

    monkeypatch.setattr(script_run_context, "get_script_run_ctx", no_context)
    errors: list[BaseException] = []

    def clear() -> None:
        try:
            clear_global_securement_threshold_cache()
        except BaseException as exc:  # pragma: no cover - 실패할 때만 닿는다
            errors.append(exc)

    thread = threading.Thread(target=clear)
    thread.start()
    thread.join(10)

    assert errors == []


# ---------------------------------------------------------------------------
# 배경 스레드
# ---------------------------------------------------------------------------


@pytest.fixture
def stopped_threads() -> Iterator[list[AutoUpdateScheduler]]:
    started: list[AutoUpdateScheduler] = []
    yield started
    for scheduler in started:
        scheduler.stop(timeout=5)


def test_the_thread_starts_once_per_process_and_ticks_on_its_own(
    repository: DuckDBScenarioRepository,
    monkeypatch: pytest.MonkeyPatch,
    stopped_threads: list[AutoUpdateScheduler],
) -> None:
    """실행 줄 허락이 있으면 스레드 하나가 서고, 다시 불러도 같은 것을 돌려준다."""
    made: list[AutoUpdateScheduler] = []
    original = scheduler_module.AutoUpdateScheduler

    def quick(repository: DuckDBScenarioRepository) -> AutoUpdateScheduler:
        scheduler = original(repository, run=RecordingRun(), tick_seconds=0.05)
        made.append(scheduler)
        stopped_threads.append(scheduler)
        return scheduler

    monkeypatch.setattr(scheduler_module, "AutoUpdateScheduler", quick)
    path = str(repository.database_path)

    first = ensure_auto_update_scheduler(path, environ={ENV_VAR: "1"})
    second = ensure_auto_update_scheduler(path, environ={ENV_VAR: "1"})

    assert first is not None and first is second and len(made) == 1
    assert running_scheduler() is first
    deadline = wall_time.monotonic() + 5
    while first.status().last_tick_at is None and wall_time.monotonic() < deadline:
        wall_time.sleep(0.02)
    status = first.status()
    assert status.alive and status.last_outcome is not None
    assert status.last_outcome.kind == "disabled"

    made[0].stop(timeout=5)
    assert running_scheduler() is None


def test_a_system_exit_inside_a_round_does_not_kill_the_thread(
    repository: DuckDBScenarioRepository,
    monkeypatch: pytest.MonkeyPatch,
    stopped_threads: list[AutoUpdateScheduler],
) -> None:
    """사내 패키지가 `SystemExit` 을 올려도 스레드는 다음 확인을 이어 간다."""
    _enable(repository, check_time=SLOT)
    ticks: list[int] = []
    original_tick = AutoUpdateScheduler.tick

    def exiting_tick(self: AutoUpdateScheduler) -> Any:
        ticks.append(1)
        if len(ticks) == 1:
            raise SystemExit("사내 패키지가 끝냈다")
        return original_tick(self)

    monkeypatch.setattr(AutoUpdateScheduler, "tick", exiting_tick)
    scheduler = AutoUpdateScheduler(repository, run=RecordingRun(), tick_seconds=0.05)
    stopped_threads.append(scheduler)
    scheduler.start()

    deadline = wall_time.monotonic() + 5
    while len(ticks) < 3 and wall_time.monotonic() < deadline:
        wall_time.sleep(0.02)

    assert len(ticks) >= 3
    assert scheduler.status().alive
