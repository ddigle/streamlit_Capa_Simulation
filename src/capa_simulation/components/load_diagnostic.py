# Purpose: 「서버 시작 점검」 의 부하 값 줄(화면 응답 · CPU · 동시 세션)과 문턱 넘음 글을 짓는다.

"""부하 진단 — `load_metrics` 가 모은 값을 사람이 읽는 줄로 짓는다(`memory_diagnostic` 과 같은 꼴).

Admin 「서버 시작 점검」 펼침(C-DEP 에만 선다)이 사실 줄 끝 메모리 값 줄 뒤에 싣고 「복사」 글에도
든다. 값은 이 프로세스의 지금이다. 화면에는 값 줄만 두고 뜻은 Guide 「서버 시작 점검」 이 말한다.

- **화면 응답** · 최근 1시간 n회 · 느린 쪽(20번 중 1번 꼴) · 최고 — 초, 소수 둘째 자리.
- **CPU** · 5분 평균 · 기동 뒤 최고(시각) — 코어, 소수 둘째 자리.
- **동시 세션** · 지금 · 기동 뒤 최고(시각) — 연결된 세션(브라우저 탭) 수.

못 잰 값은 「모름」 이다(회차가 아직 없음 · 20회 전 · 기동 뒤 5분 전 · 세션 관리자를 못 읽음).
시각은 진단 펼침 시각 꼴(`sso_status.CLOCK_FORMAT` — KST)이다.

신호표 문턱을 넘으면 개발자 상태 알림 `AD-26` 이 선다 — 판정 · 글은 `load_signal`, 알림은
`container_start_check.render_load_alert` 가 낸다(같은 판정의 서버에서만 — 이벤트 칸 한 자리).
회차 끝 기록(`note_run_end`)은 `app.py` 가 끝까지 돈 회차의 끝에서 부른다.
"""

from __future__ import annotations

from dataclasses import dataclass

from capa_simulation import load_metrics
from capa_simulation.components.memory_diagnostic import NOT_KNOWN, session_counts
from capa_simulation.components.sso_status import CLOCK_FORMAT
from capa_simulation.korea_time import kst_clock
from capa_simulation.load_metrics import CpuView, ResponseView, SessionView

RESPONSE_LABEL = "화면 응답"
CPU_LABEL = "CPU"
SESSION_LABEL = "동시 세션"
WINDOW_TEXT = "최근 1시간"


@dataclass(frozen=True)
class LoadSignal:
    """넘은 문턱 이름(지문 재료 — 값은 싣지 않는다) · 알림 짧은 글 · 전문."""

    names: tuple[str, ...]
    text: str
    full: str


def connected_sessions() -> int | None:
    """연결된 세션 수 — 세션 관리자를 못 읽으면 None(`memory_diagnostic.session_counts`)."""
    counts = session_counts()
    return None if counts is None else counts[0]


def note_run_end(started: float) -> None:
    """끝까지 돈 회차의 끝 — `app.py` 가 부른다(`load_metrics.finish_run`). 진단이 회차를 멈추지
    않게 무엇이 나도 건너뛴다."""
    try:
        load_metrics.finish_run(started, connected_sessions())
    except Exception:  # 계측 — 실패해도 화면은 그대로 선다
        return


def seconds_text(value: float | None) -> str:
    return NOT_KNOWN if value is None else f"{value:.2f}초"


def cores_text(value: float | None) -> str:
    return NOT_KNOWN if value is None else f"{value:.2f}코어"


def clock_text(epoch: float | None) -> str:
    if epoch is None:
        return NOT_KNOWN
    try:
        return kst_clock(epoch, CLOCK_FORMAT)
    except (OverflowError, OSError, ValueError):
        return NOT_KNOWN


def response_line(view: ResponseView) -> str:
    """「**화면 응답** · 최근 1시간 n회 · 느린 쪽 · 최고」 한 줄."""
    parts = [
        f"{WINDOW_TEXT} {view.runs}회",
        f"느린 쪽 {seconds_text(view.slow_seconds)}",
        f"최고 {seconds_text(view.max_seconds)}",
    ]
    return f"**{RESPONSE_LABEL}** · {' · '.join(parts)}"


def cpu_line(view: CpuView) -> str:
    """「**CPU** · 5분 평균 · 기동 뒤 최고(시각)」 한 줄."""
    peak = cores_text(view.peak_cores)
    if view.peak_cores is not None:
        peak += f"({clock_text(view.peak_at)})"
    return f"**{CPU_LABEL}** · 5분 평균 {cores_text(view.cores)} · 기동 뒤 최고 {peak}"


def session_line(view: SessionView) -> str:
    """「**동시 세션** · 지금 · 기동 뒤 최고(시각)」 한 줄."""
    now = NOT_KNOWN if view.now is None else str(view.now)
    peak = NOT_KNOWN if view.peak is None else f"{view.peak}({clock_text(view.peak_at)})"
    return f"**{SESSION_LABEL}** · 지금 {now} · 기동 뒤 최고 {peak}"


def load_lines() -> list[str]:
    """펼침 사실 줄 끝(메모리 값 줄 뒤)에 더하는 값 줄 셋."""
    return [
        response_line(load_metrics.response_view()),
        cpu_line(load_metrics.cpu_view()),
        session_line(load_metrics.session_view(connected_sessions())),
    ]


def signal_of(response: ResponseView, cpu: CpuView, sessions: SessionView) -> LoadSignal | None:
    """넘은 문턱이 있으면 그 이름 · 짧은 글 · 전문. 없으면 None."""
    names = load_metrics.crossed(response, cpu, sessions)
    if not names:
        return None
    values = {
        load_metrics.SIGNAL_SLOW: f"화면 응답 느린 쪽 {seconds_text(response.signal_seconds)}",
        load_metrics.SIGNAL_CPU: f"CPU 5분 평균 {cores_text(cpu.cores)}",
        load_metrics.SIGNAL_SESSIONS: f"동시 세션 {sessions.now}",
    }
    crossed = " · ".join(values[name] for name in names)
    thresholds = (
        f"화면 응답 느린 쪽 {load_metrics.SLOW_SIGNAL_SECONDS:g}초 · "
        f"CPU 5분 평균 {load_metrics.CPU_SIGNAL_CORES:g}코어 · "
        f"동시 세션 {load_metrics.SESSION_SIGNAL}"
    )
    return LoadSignal(
        names=names,
        text=f"서버 부하 신호 — {crossed}",
        full=(
            f"서버 부하가 신호표 문턱({thresholds})을 넘었습니다 — {crossed}. 값은 Admin "
            "「서버 시작 점검」 의 화면 응답 · CPU · 동시 세션 줄에 있습니다."
        ),
    )


def load_signal() -> LoadSignal | None:
    """지금 값으로 판정한 `signal_of`."""
    return signal_of(
        load_metrics.response_view(),
        load_metrics.cpu_view(),
        load_metrics.session_view(connected_sessions()),
    )
