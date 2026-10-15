# Purpose: 실행 줄 허락이 있는 앱 프로세스에서 공식버전 자동 갱신을 매일 지정 시각에 돌린다.

"""공식버전 자동 갱신의 예약 실행 — 앱 프로세스 안 배경 스레드 하나.

DuckDB 는 프로세스 배타 잠금이라 앱 밖 프로그램(OS 작업 스케줄러)으로 돌리면 사용자 화면과 잠금을
다툰다. 그래서 예약은 **앱 프로세스 안**에서 돈다(2026-10-15 사용자 결정).

**켜는 조건은 둘이다.**

1. 실행 줄 허락 — 환경변수 `CAPA_AUTO_OFFICIAL_UPDATE=1`. 이것이 없으면 스레드를 세우지 않는다.
   같은 `app.py` 를 도는 프로세스는 사용자 앱만이 아니다(사내 화면 확인 스크립트의 자식 앱, AppTest,
   개발 실행) — 그쪽이 같은 DB 로 발행하지 않게 한다.
2. 화면 토글 — 공용 설정(`app_meta.global_auto_official_update`)의 켜짐. 확인할 때마다 다시 읽으므로
   화면에서 끄면 다음 확인부터 돌지 않는다.

**언제 도나.** 스레드는 `TICK_SECONDS` 마다 벽시계를 보고, 직전 확인과 지금 사이에 오늘 지정 시각이
지나갔으면 그 날의 예약 회차를 돈다(`services.auto_official_update.crossed_slot`). 첫 확인의
「직전」은 스레드를 세운 시각이다 — **앱이 그 시각에 떠 있지 않았으면(꺼졌거나, 그 뒤에 떴거나,
잠들었으면) 따라잡지 않고** 다음 날 지정 시각을 기다린다. 같은 날 두 번 돌지 않는 것은 DB 의 회차
선점(날짜 키)이 지킨다 — 여러 세션·스레드·재시작에도 한 번이다.

**스레드는 첫 접속 때 선다.** Streamlit 은 브라우저 세션이 붙어야 `app.py` 를 돌린다. 그래서 앱을
띄운 뒤 누군가 한 번 들어와야 예약이 시작된다(`app.py` 가 부트스트랩 뒤에
`ensure_auto_update_scheduler` 를 부른다 — 허락이 없으면 환경변수만 보고 돌아간다). 앱을 다시 띄운
날 지정 시각 전에 아무도 들어오지 않으면 그날은 돌지 않는다 — 사내 런북 4-4 가 「띄운 뒤 브라우저
탭 하나를 열어 두고 『이 실행에서 예약이 켜져 있습니다』를 확인」을 확인 항목으로 둔다(열어 둔 탭은
서버가 다시 떠도 스스로 다시 붙어 `app.py` 를 돌린다).

**프로세스에 하나.** `st.cache_resource` 를 쓰지 않는다 — 그 키는 함수 소스에서 나와 개발 중 코드를
고치면 새 스레드가 하나 더 선다. 스레드 이름(`THREAD_NAME`)으로 살아 있는 것을 찾고, 있으면 새로
세우지 않는다. 모듈을 다시 읽어도(Streamlit 의 바뀐 모듈 재적재) 스레드 목록은 프로세스에 하나라
같은 답이 나온다. 그래서 이 모듈은 Streamlit 캐시 경계가 아니다.

**스레드에는 Streamlit 실행 문맥이 없다.** `st.*` 화면 명령·`st.session_state`·`st.cache_data`
래퍼를 부르지 않는다. 회차는 세션 없는 `auto_official_update_runner` 가 돈다. 발행 뒤 정리는 전역
범위 `st.cache_data` 함수의 `.clear()` 하나다
(`persistence.cache.clear_global_securement_threshold_cache`) — 전역 범위 캐시는 지우는 데 실행
문맥이 필요 없다. `Exception` 계열과 `SystemExit` 은 스레드를 죽이지 않는다 — 회차 안의 실패는 실행
기록에(실제 사유 그대로), 그 밖(설정 읽기·선점 전 DB 잠금)은 로그와 `SchedulerStatus` 에 남는다.

**사내 조회에는 시간 제한이 없다.** 조회가 응답하지 않으면 그 회차 안에서 스레드가 기다린다. 회차를
부르기 직전에 「회차 진행 중」을 상태에 남겨, 화면이 그 시작 시각과 경과로 멈춤을 드러낸다.

**로그.** 앱은 로깅을 설정하지 않아 INFO 는 어디에도 나오지 않는다. 그래서 드문 사건(예약 시작,
중단된 회차 정리)은 WARNING 으로 남긴다. 설정을 계속 못 읽는 상태는 처음과 회복 때만 남긴다 —
30초마다 같은 경고가 쌓이지 않게 한다.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final, Literal, Protocol, cast

from capa_simulation.auto_official_update_runner import (
    BUSY_MESSAGE,
    AutoUpdateRunResult,
    AutoUpdateSources,
    Clock,
    abandon_interrupted_runs,
    run_auto_official_update,
)
from capa_simulation.persistence.cache import clear_global_securement_threshold_cache
from capa_simulation.persistence.models import AutoOfficialUpdateRun
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.auto_official_update import (
    TRIGGER_SCHEDULED,
    crossed_slot,
)

_LOGGER = logging.getLogger(__name__)

# 실행 줄 허락. 값이 아래 낱말 가운데 하나면 켠다(대소문자 무시) — 그 밖은 모두 꺼짐이다.
ENV_VAR: Final = "CAPA_AUTO_OFFICIAL_UPDATE"
_TRUE_VALUES: Final = frozenset({"1", "true", "yes", "on"})
# 벽시계를 보는 간격. 「잠들었다」고 보는 간격(`SLOT_TICK_TOLERANCE`, 10분)보다 충분히 짧아야 한다.
TICK_SECONDS: Final = 30.0
THREAD_NAME: Final = "capa-auto-official-update"

TickKind = Literal[
    "settings_error", "disabled", "waiting", "running", "ran", "not_run", "run_error"
]
TICK_LABELS: Final[dict[str, str]] = {
    "settings_error": "설정을 읽지 못함",
    "disabled": "꺼져 있음",
    "waiting": "지정 시각 기다림",
    "running": "회차 진행 중",
    "ran": "회차 돎",
    "not_run": "회차를 잡지 못함",
    "run_error": "회차 시작 실패",
}

RunFunction = Callable[..., AutoUpdateRunResult]


def scheduler_opted_in(environ: Mapping[str, str] | None = None) -> bool:
    """이 실행 줄이 예약을 허락했는가(`CAPA_AUTO_OFFICIAL_UPDATE=1`)."""
    source = os.environ if environ is None else environ
    return source.get(ENV_VAR, "").strip().casefold() in _TRUE_VALUES


@dataclass(frozen=True)
class TickOutcome:
    """확인 한 번의 결과. 화면의 「지금 상태」가 마지막 것을 보여 준다."""

    kind: TickKind
    at: datetime
    run_day: date | None = None
    run: AutoOfficialUpdateRun | None = None
    message: str | None = None

    @property
    def label(self) -> str:
        return TICK_LABELS.get(self.kind, self.kind)


@dataclass(frozen=True)
class SchedulerStatus:
    """배경 스레드의 지금 상태(이 프로세스 안). 화면이 읽기만 한다."""

    started_at: datetime
    last_tick_at: datetime | None
    last_outcome: TickOutcome | None
    # 같은 날 다시 시도할 예약 회차의 날짜(다른 회차가 도는 중이었거나 선점 전 DB 를 못 열었을 때).
    pending_day: date | None
    alive: bool
    tick_seconds: float


class SchedulerHandle(Protocol):
    """화면이 보는 예약 스레드의 얼굴. 모듈을 다시 읽어도 옛 객체에 같은 이름으로 묻는다."""

    def status(self) -> SchedulerStatus: ...


class AutoUpdateScheduler:
    """예약 판단과 배경 스레드. 판단(`tick`)은 스레드 없이도 불러 시험한다."""

    def __init__(
        self,
        repository: DuckDBScenarioRepository,
        *,
        clock: Clock = datetime.now,
        sources: AutoUpdateSources | None = None,
        run: RunFunction = run_auto_official_update,
        after_publish: Callable[[], None] | None = clear_global_securement_threshold_cache,
        tick_seconds: float = TICK_SECONDS,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._sources = sources
        self._run = run
        self._after_publish = after_publish
        self._tick_seconds = tick_seconds
        self._started_at = clock()
        # 직전 확인 시각. 처음에는 세운 시각이라 그 전에 지나간 지정 시각은 따라잡지 않는다.
        self._previous = self._started_at
        self._pending_day: date | None = None
        self._abandoned = False
        self._last_tick_at: datetime | None = None
        self._last_outcome: TickOutcome | None = None
        # 설정 읽기 실패를 처음 한 번만 경고로 남기려는 표시. 회복하면 다시 내린다.
        self._settings_failing = False
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def started_at(self) -> datetime:
        return self._started_at

    def tick(self) -> TickOutcome:
        """벽시계를 한 번 보고, 오늘 지정 시각을 지금 막 지났으면 예약 회차를 돈다."""
        now = self._clock()
        if not self._abandoned:
            self._abandon_interrupted(now)
        try:
            config = self._repository.load_auto_official_update_settings().config
        except Exception as exc:  # 다른 프로세스의 DB 잠금 등. 직전 확인 시각을 그대로 둔다 —
            # 그 사이 지정 시각이 지났어도 잠깐이면 다음 확인이 그 시각을 본다.
            if not self._settings_failing:
                _LOGGER.warning("자동 갱신 설정을 읽지 못했습니다(회복하면 다시 알립니다): %s", exc)
            self._settings_failing = True
            return self._remember(TickOutcome("settings_error", now, message=_error_text(exc)))
        if self._settings_failing:
            _LOGGER.warning("자동 갱신 설정을 다시 읽었습니다.")
            self._settings_failing = False
        previous, self._previous = self._previous, now
        if self._pending_day is not None and self._pending_day != now.date():
            self._pending_day = None
        if not config.enabled:
            self._pending_day = None
            return self._remember(TickOutcome("disabled", now))
        day = crossed_slot(previous, now, config.check_time) or self._pending_day
        if day is None:
            return self._remember(TickOutcome("waiting", now))
        # 회차가 끝날 때까지 이 확인은 돌아오지 않는다(사내 조회는 시간 제한이 없다). 화면이 「진행
        # 중」과 그 시작 시각을 보게 먼저 남긴다.
        self._remember(TickOutcome("running", now, run_day=day))
        try:
            result = self._run(
                self._repository,
                trigger=TRIGGER_SCHEDULED,
                run_day=day,
                sources=self._sources,
                clock=self._clock,
                after_publish=self._after_publish,
            )
        except Exception as exc:  # 선점·설정 읽기 전의 실패다. 같은 날 다음 확인에 다시 잡는다.
            _LOGGER.exception("자동 갱신 예약 회차(%s)를 시작하지 못했습니다.", day)
            self._pending_day = day
            return self._remember(
                TickOutcome("run_error", now, run_day=day, message=_error_text(exc))
            )
        if result.run is None:
            # 다른 회차(「지금 실행」)가 도는 중이면 선점하지 않았다 — 같은 날 다시 시도한다.
            # 이미 잡힌 날이면 더 할 일이 없다.
            self._pending_day = day if result.not_run_reason == BUSY_MESSAGE else None
            return self._remember(
                TickOutcome("not_run", now, run_day=day, message=result.not_run_reason)
            )
        self._pending_day = None
        return self._remember(TickOutcome("ran", now, run_day=day, run=result.run))

    def start(self) -> None:
        """배경 스레드를 세운다(데몬 — 앱 프로세스가 끝나면 함께 끝난다)."""
        if self._thread is not None:
            return
        thread = threading.Thread(target=self._loop, name=THREAD_NAME, daemon=True)
        # 화면이 스레드 목록에서 이 객체를 찾는다(`running_scheduler`).
        thread.scheduler = self  # type: ignore[attr-defined]
        self._thread = thread
        thread.start()

    def stop(self, timeout: float | None = None) -> None:
        """다음 확인 전에 멈춘다. 도는 회차는 끊지 않는다(시험·종료용)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def status(self) -> SchedulerStatus:
        with self._state_lock:
            return SchedulerStatus(
                started_at=self._started_at,
                last_tick_at=self._last_tick_at,
                last_outcome=self._last_outcome,
                pending_day=self._pending_day,
                alive=self._thread is not None and self._thread.is_alive(),
                tick_seconds=self._tick_seconds,
            )

    def _loop(self) -> None:
        self._abandon_interrupted(self._clock())
        while not self._stop.wait(self._tick_seconds):
            try:
                self.tick()
            except (Exception, SystemExit):  # 스레드는 죽지 않는다. `tick` 이 잡는 것 밖의
                # 실패만 온다 — 회차 안의 `SystemExit` 은 러너가 실행 기록에 남긴 뒤 다시 올린다.
                _LOGGER.exception("자동 갱신 예약 확인이 실패했습니다.")

    def _abandon_interrupted(self, now: datetime) -> None:
        """옛 프로세스가 회차 도중에 꺼져 「실행 중」으로 남은 기록을 닫는다. 한 번 성공하면 끝."""
        try:
            closed = abandon_interrupted_runs(
                self._repository, started_before=self._started_at, now=now
            )
        except Exception as exc:  # DB 를 열지 못했으면 다음 확인에 다시 한다.
            _LOGGER.warning("중단된 자동 갱신 회차를 닫지 못했습니다: %s", exc)
            return
        self._abandoned = True
        if closed:
            _LOGGER.warning("중단된 자동 갱신 회차 %d건을 오류로 닫았습니다.", closed)

    def _remember(self, outcome: TickOutcome) -> TickOutcome:
        with self._state_lock:
            self._last_tick_at = outcome.at
            self._last_outcome = outcome
        return outcome


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


_START_LOCK = threading.Lock()


def running_scheduler() -> SchedulerHandle | None:
    """이 프로세스에서 살아 있는 예약 스레드. 없으면 None(실행 줄 허락이 없거나 서지 않았다)."""
    for thread in threading.enumerate():
        if thread.name != THREAD_NAME or not thread.is_alive():
            continue
        scheduler = getattr(thread, "scheduler", None)
        if scheduler is not None and callable(getattr(scheduler, "status", None)):
            return cast(SchedulerHandle, scheduler)
    return None


def ensure_auto_update_scheduler(
    database_path: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> SchedulerHandle | None:
    """실행 줄 허락이 있으면 이 프로세스의 예약 스레드를 (없을 때만) 세운다. 앱이 매 회차 부른다.

    허락이 없으면 환경변수만 보고 돌아간다. 어떤 실패도 올리지 않는다 — 예약이 서지 않아도 화면은
    돌아야 한다(실패는 로그에 남고, 화면의 「지금 상태」가 「이 실행에서 돌지 않음」으로 보인다).
    """
    if not scheduler_opted_in(environ):
        return None
    existing = running_scheduler()
    if existing is not None:
        return existing
    try:
        with _START_LOCK:
            existing = running_scheduler()
            if existing is not None:
                return existing
            scheduler = AutoUpdateScheduler(DuckDBScenarioRepository(Path(database_path)))
            scheduler.start()
            _LOGGER.warning("공식버전 자동 갱신 예약을 시작했습니다(%s).", database_path)
            return scheduler
    except Exception:
        _LOGGER.exception("공식버전 자동 갱신 예약을 시작하지 못했습니다.")
        return None
