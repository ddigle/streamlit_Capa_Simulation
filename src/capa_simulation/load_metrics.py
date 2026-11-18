# Purpose: 화면 응답 시간 · CPU 5분 평균 · 동시 세션 최고값을 회차 끝에 이 프로세스 메모리로 모은다.

"""부하 계측(`docs/TODO.md` 2장 「Streamlit 에 남는 조건 셋」 ② — 신호표의 화면 응답 · CPU ·
동시 접속을 재는 자리).

배경 스레드를 세우지 않는다. `app.py` 가 전체 회차 맨 앞에서 `begin_run` 으로 시각을 쥐고, 끝까지
돈 회차의 끝(정상 끝 · 페이지가 스스로 멈춘 `st.stop()`)에서
`components/load_diagnostic.note_run_end` 가 `finish_run` 을 부른다. 재는 몫은 그 회차의 스크립트
시간 · 프로세스 CPU 시간 · 연결된 세션 수 셋이다. 값은 프로세스 메모리에만 있고 재시작하면 빈다.
Streamlit 을 import 하지 않는다.

- **화면 응답** — 회차 스크립트 시간(`perf_counter`)을 최근 `RESPONSE_WINDOW_SECONDS`(1시간)
  안, 많으면 최근 `RESPONSE_SAMPLE_LIMIT`(5,000)회만 둔다. 「느린 쪽」 은 그 창의 20번 중 1번
  꼴(p95 — 작은 쪽부터 `ceil(0.95 n)` 째, 가까운 순위)이고 `SLOW_MIN_RUNS`(20)회 전에는 모른다.
  「최고」 는 같은 창의 가장 긴 회차다. 정렬은 읽을 때 하고 그 값은
  `RESPONSE_CACHE_SECONDS`(5초) 동안 다시 쓴다.
- **CPU 5분 평균** — 프로세스 CPU 시간(`time.process_time` — 모든 스레드의 사용자 + 시스템
  시간)을 회차 끝마다 5초에 한 번까지 표본으로 둔다(첫 표본은 import 때). 평균은 (지금 CPU 시간
  − 5분 전 CPU 시간) ÷ 300초이고, 5분 전 값은 그 시각을 낀 두 표본(마지막은 지금)을 곧게 이어
  읽는다 — 회차가 없던 빈 시간에 CPU 를 고르게 썼다고 본다. 표본이 5분을 덮기 전(기동 뒤
  5분)에는 모른다. 「기동 뒤 최고」 는 회차 끝 · 읽을 때마다 잰 평균의 최고와 그 시각이다.
- **동시 세션** — 연결된 세션 수(부르는 쪽이 Streamlit 세션 관리자에서 읽어 넘긴다)의 기동 뒤
  최고와 그 시각. 같은 값이 다시 나오면 처음 시각을 둔다.

세지 않는 회차 · 몫: 새 상호작용이 끊은 회차 · `st.rerun()` 으로 끝난 회차 · 페이지 앞에서 멈춘
회차(통합인증 멈춤 · 앱 시작 실패) · 프래그먼트만 도는 회차, 그리고 스크립트보다 먼저 도는 위젯
콜백(누른 단추의 저장 등)과 회차 뒤 Streamlit 의 `gc.collect(2)`. 그 몫만큼 화면 응답은 실제보다
짧다. 회차가 겹치면(세션마다 스크립트 스레드) 잠금 하나로 적는다. 「기동 뒤」 는 이 모듈을 처음
불러온 때 — `app.py` 첫 회차(첫 접속) — 부터다.

**신호표 문턱**(`SLOW_SIGNAL_SECONDS` · `CPU_SIGNAL_CORES` · `SESSION_SIGNAL` — 제안값, 같은
TODO 줄)은 `crossed` 가 판정한다 — 느린 쪽 3초 이상 · CPU 5분 평균 0.7코어 이상 · 지금 연결
25 이상(최고가 아니라 지금 — 상태 알림이 조건이 사라지면 해소로 닫히게).
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Final

RESPONSE_WINDOW_SECONDS: Final = 3600.0
RESPONSE_SAMPLE_LIMIT: Final = 5000
SLOW_RANK: Final = 0.95
SLOW_MIN_RUNS: Final = 20
RESPONSE_CACHE_SECONDS: Final = 5.0
CPU_WINDOW_SECONDS: Final = 300.0
CPU_SAMPLE_GAP_SECONDS: Final = 5.0

SLOW_SIGNAL_SECONDS: Final = 3.0
CPU_SIGNAL_CORES: Final = 0.7
SESSION_SIGNAL: Final = 25

SIGNAL_SLOW: Final = "slow"
SIGNAL_CPU: Final = "cpu"
SIGNAL_SESSIONS: Final = "sessions"


@dataclass(frozen=True)
class ResponseView:
    """최근 창의 회차 수 · 느린 쪽(p95) · 최고 — 초. 모르면 None."""

    runs: int
    slow_seconds: float | None
    max_seconds: float | None


@dataclass(frozen=True)
class CpuView:
    """CPU 5분 평균 · 기동 뒤 최고(코어)와 그 시각(UNIX 초). 모르면 None."""

    cores: float | None
    peak_cores: float | None
    peak_at: float | None


@dataclass(frozen=True)
class SessionView:
    """연결된 세션 지금 · 기동 뒤 최고와 그 시각(UNIX 초). 모르면 None."""

    now: int | None
    peak: int | None
    peak_at: float | None


class _State:
    """프로세스 하나의 계측 값 — `_LOCK` 안에서만 읽고 쓴다."""

    def __init__(self, now: float, cpu: float) -> None:
        self.runs: deque[tuple[float, float]] = deque(maxlen=RESPONSE_SAMPLE_LIMIT)
        self.cpu: deque[tuple[float, float]] = deque([(now, cpu)])
        self.cpu_peak: tuple[float, float] | None = None
        self.session_peak: tuple[int, float] | None = None
        self.response_cache: tuple[float, ResponseView] | None = None


_LOCK = threading.Lock()
_STATE = _State(time.monotonic(), time.process_time())


def begin_run() -> float:
    """회차 맨 앞의 시각 표(`perf_counter`) — `finish_run` 에 넘긴다."""
    return time.perf_counter()


def finish_run(started: float, sessions: int | None) -> None:
    """끝까지 돈 회차의 끝 — 지금 시계로 `record_run`."""
    record_run(
        seconds=time.perf_counter() - started,
        now=time.monotonic(),
        cpu=time.process_time(),
        wall=time.time(),
        sessions=sessions,
    )


def record_run(
    *, seconds: float, now: float, cpu: float, wall: float, sessions: int | None
) -> None:
    """회차 하나 — 스크립트 시간(`seconds`) · 단조 시각(`now`) · 프로세스 CPU 시간 · 벽시계 ·
    연결 수."""
    with _LOCK:
        _STATE.runs.append((now, seconds))
        _note_cpu(now, cpu, wall)
        if sessions is not None:
            _note_sessions(sessions, wall)


def response_view(now: float | None = None) -> ResponseView:
    """최근 창의 회차 수 · 느린 쪽 · 최고. 5초 안에 다시 읽으면 앞서 정렬한 값이다."""
    moment = time.monotonic() if now is None else now
    with _LOCK:
        cached = _STATE.response_cache
        if cached is not None and 0 <= moment - cached[0] < RESPONSE_CACHE_SECONDS:
            return cached[1]
        floor = moment - RESPONSE_WINDOW_SECONDS
        recent = sorted(seconds for at, seconds in _STATE.runs if at >= floor)
        view = ResponseView(
            runs=len(recent),
            slow_seconds=slow_seconds(recent),
            max_seconds=recent[-1] if recent else None,
        )
        _STATE.response_cache = (moment, view)
        return view


def slow_seconds(ordered: list[float]) -> float | None:
    """오름차순 회차 시간의 느린 쪽(p95 — 가까운 순위). `SLOW_MIN_RUNS` 전에는 None."""
    if len(ordered) < SLOW_MIN_RUNS:
        return None
    return ordered[math.ceil(SLOW_RANK * len(ordered)) - 1]


def cpu_view(
    now: float | None = None, cpu: float | None = None, wall: float | None = None
) -> CpuView:
    """CPU 5분 평균(지금) · 기동 뒤 최고. 읽은 평균도 최고에 든다."""
    moment = time.monotonic() if now is None else now
    used = time.process_time() if cpu is None else cpu
    with _LOCK:
        cores = _cores(moment, used)
        _note_peak(cores, time.time() if wall is None else wall)
        peak = _STATE.cpu_peak
    return CpuView(
        cores=cores,
        peak_cores=None if peak is None else peak[0],
        peak_at=None if peak is None else peak[1],
    )


def session_view(current: int | None, wall: float | None = None) -> SessionView:
    """연결 세션 지금(부르는 쪽이 읽은 값 — 최고에 든다) · 기동 뒤 최고."""
    with _LOCK:
        if current is not None:
            _note_sessions(current, time.time() if wall is None else wall)
        peak = _STATE.session_peak
    return SessionView(
        now=current,
        peak=None if peak is None else peak[0],
        peak_at=None if peak is None else peak[1],
    )


def crossed(response: ResponseView, cpu: CpuView, sessions: SessionView) -> tuple[str, ...]:
    """넘은 신호표 문턱 — `SIGNAL_SLOW` · `SIGNAL_CPU` · `SIGNAL_SESSIONS` 차례. 모르는 값은
    넘지 않는다."""
    found: list[str] = []
    if response.slow_seconds is not None and response.slow_seconds >= SLOW_SIGNAL_SECONDS:
        found.append(SIGNAL_SLOW)
    if cpu.cores is not None and cpu.cores >= CPU_SIGNAL_CORES:
        found.append(SIGNAL_CPU)
    if sessions.now is not None and sessions.now >= SESSION_SIGNAL:
        found.append(SIGNAL_SESSIONS)
    return tuple(found)


def reset(*, now: float | None = None, cpu: float | None = None) -> None:
    """값을 비우고 CPU 첫 표본을 다시 둔다 — 시험이 프로세스 전역 값을 사이마다 되돌린다."""
    global _STATE
    with _LOCK:
        _STATE = _State(
            time.monotonic() if now is None else now,
            time.process_time() if cpu is None else cpu,
        )


def _note_cpu(now: float, cpu: float, wall: float) -> None:
    _note_peak(_cores(now, cpu), wall)
    samples = _STATE.cpu
    if now - samples[-1][0] >= CPU_SAMPLE_GAP_SECONDS:
        samples.append((now, cpu))
    # 5분 경계보다 오래된 표본은 경계 앞 마지막 하나만 남긴다(그 시각을 낄 점).
    boundary = now - CPU_WINDOW_SECONDS
    while len(samples) >= 2 and samples[1][0] <= boundary:
        samples.popleft()


def _cores(now: float, cpu: float) -> float | None:
    """(지금 CPU 시간 − 5분 전 CPU 시간) ÷ 300초. 표본이 5분을 덮지 못하면 None."""
    boundary = now - CPU_WINDOW_SECONDS
    samples = _STATE.cpu
    if samples[0][0] > boundary:
        return None
    points = [*samples, (now, cpu)]
    for (start, start_cpu), (end, end_cpu) in zip(points, points[1:], strict=False):
        if start <= boundary <= end:
            span = end - start
            base = (
                end_cpu
                if span <= 0
                else start_cpu + (end_cpu - start_cpu) * (boundary - start) / span
            )
            return max(0.0, (cpu - base) / CPU_WINDOW_SECONDS)
    return None


def _note_peak(cores: float | None, wall: float) -> None:
    peak = _STATE.cpu_peak
    if cores is not None and (peak is None or cores > peak[0]):
        _STATE.cpu_peak = (cores, wall)


def _note_sessions(count: int, wall: float) -> None:
    peak = _STATE.session_peak
    if peak is None or count > peak[0]:
        _STATE.session_peak = (count, wall)
