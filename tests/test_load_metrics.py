# Purpose: 부하 계측(`load_metrics`)의 느린 쪽 · 최근 창 · CPU 평균 · 세션 최고 · 문턱 판정을 잰다.

"""`capa_simulation.load_metrics` — 회차 끝에 모으는 화면 응답 · CPU · 동시 세션 값.

시계는 인자로 넣는다(`record_run` · `*_view` 의 `now` · `cpu` · `wall`, `reset` 의 첫 표본).
conftest 가 시험마다 값을 비운다.
"""

from __future__ import annotations

import threading

import pytest

from capa_simulation import load_metrics
from capa_simulation.load_metrics import CpuView, ResponseView, SessionView


def _run(seconds: float, *, now: float, cpu: float = 0.0, sessions: int | None = None) -> None:
    load_metrics.record_run(
        seconds=seconds, now=now, cpu=cpu, wall=1_000.0 + now, sessions=sessions
    )


def test_the_slow_side_is_one_in_twenty_after_twenty_runs() -> None:
    """느린 쪽은 작은 쪽부터 `ceil(0.95 n)` 째(가까운 순위) — 20회 전에는 모르고 최고는 첫
    회부터."""
    load_metrics.reset(now=0.0, cpu=0.0)
    for index in range(19):
        _run(float(index + 1), now=10.0 + index)
    early = load_metrics.response_view(now=100.0)
    assert early == ResponseView(runs=19, slow_seconds=None, max_seconds=19.0)

    _run(20.0, now=40.0)
    view = load_metrics.response_view(now=200.0)
    assert view == ResponseView(runs=20, slow_seconds=19.0, max_seconds=20.0)

    for index in range(80):
        _run(0.5, now=50.0 + index)
    # 100회 가운데 95번째는 15초 — 이보다 느린 회차가 5회(16 ~ 20초), 20번 중 1번 꼴이다.
    assert load_metrics.response_view(now=300.0).slow_seconds == 15.0


def test_the_signal_side_leaves_out_the_first_five_minutes_after_start() -> None:
    """막 띄운 서버의 첫 그리기(캐시가 빈 HOME 4초대 둘)는 값 줄의 느린 쪽에는 들고 신호 판정의
    느린 쪽에서는 빠진다 — 기동 뒤 5분 뒤 회차가 20회 차야 신호 쪽 값이 선다."""
    load_metrics.reset(now=0.0, cpu=0.0)
    _run(4.5, now=10.0)
    _run(4.4, now=20.0)
    for index in range(28):
        _run(0.3, now=30.0 + index)
    early = load_metrics.response_view(now=400.0)
    assert early.runs == 30 and early.slow_seconds == 4.4
    assert early.signal_seconds is None

    for index in range(20):
        _run(0.4, now=load_metrics.SLOW_SETTLE_SECONDS + index)
    later = load_metrics.response_view(now=1_000.0)
    assert later.slow_seconds is not None and later.slow_seconds >= 0.4
    assert later.signal_seconds == 0.4


def test_runs_older_than_the_window_leave_and_the_count_is_capped() -> None:
    load_metrics.reset(now=0.0, cpu=0.0)
    _run(9.0, now=0.0)
    _run(1.0, now=3_000.0)
    view = load_metrics.response_view(now=load_metrics.RESPONSE_WINDOW_SECONDS + 1.0)
    assert view == ResponseView(runs=1, slow_seconds=None, max_seconds=1.0)

    load_metrics.reset(now=0.0, cpu=0.0)
    for index in range(load_metrics.RESPONSE_SAMPLE_LIMIT + 7):
        _run(0.1, now=index * 0.01)
    assert load_metrics.response_view(now=100.0).runs == load_metrics.RESPONSE_SAMPLE_LIMIT


def test_the_sorted_view_is_reused_for_a_few_seconds() -> None:
    """읽을 때 정렬한 값은 5초 동안 다시 쓴다 — 회차마다 5,000개를 정렬하지 않는다."""
    load_metrics.reset(now=0.0, cpu=0.0)
    _run(1.0, now=1.0)
    first = load_metrics.response_view(now=10.0)
    _run(7.0, now=11.0)
    assert load_metrics.response_view(now=12.0) == first
    later = load_metrics.response_view(now=10.0 + load_metrics.RESPONSE_CACHE_SECONDS)
    assert later.max_seconds == 7.0 and later.runs == 2


def test_the_cpu_average_waits_for_five_minutes_of_samples() -> None:
    load_metrics.reset(now=0.0, cpu=0.0)
    assert load_metrics.cpu_view(now=100.0, cpu=50.0, wall=1.0).cores is None
    view = load_metrics.cpu_view(now=300.0, cpu=150.0, wall=2.0)
    assert view.cores == pytest.approx(0.5)
    assert view.peak_cores == pytest.approx(0.5) and view.peak_at == 2.0


def test_the_cpu_value_five_minutes_ago_is_read_across_an_idle_gap() -> None:
    """회차가 없던 빈 시간은 CPU 를 고르게 썼다고 보고 5분 전 값을 두 표본 사이에서 곧게 읽는다 —
    한 시간 쉬고 몰린 회차도 그 몰린 몫으로 잰다."""
    load_metrics.reset(now=0.0, cpu=0.0)
    _run(0.2, now=10.0, cpu=1.0)
    _run(0.2, now=600.0, cpu=30.0)
    view = load_metrics.cpu_view(now=700.0, cpu=130.0, wall=3.0)
    base = 1.0 + 29.0 * (400.0 - 10.0) / (600.0 - 10.0)
    assert view.cores == pytest.approx((130.0 - base) / 300.0)

    load_metrics.reset(now=0.0, cpu=0.0)
    _run(0.2, now=3_600.0, cpu=36.0)
    _run(0.2, now=3_840.0, cpu=276.0)
    burst = load_metrics.cpu_view(now=3_900.0, cpu=336.0, wall=4.0)
    # 5분 전(3,600초)의 값은 그 자리 표본 36 — 몰린 4분의 CPU 300초 ÷ 300초.
    assert burst.cores == pytest.approx(1.0)


def test_the_cpu_samples_stay_few() -> None:
    """표본은 5초에 한 번까지이고 5분 경계 앞 하나만 남긴다 — 회차가 많아도 몇십 개다."""
    load_metrics.reset(now=0.0, cpu=0.0)
    for index in range(10_000):
        _run(0.05, now=index * 0.1, cpu=index * 0.01)
    window = load_metrics.CPU_WINDOW_SECONDS / load_metrics.CPU_SAMPLE_GAP_SECONDS
    assert len(load_metrics._STATE.cpu) <= window + 2


def test_the_session_peak_keeps_its_first_time() -> None:
    load_metrics.reset(now=0.0, cpu=0.0)
    _run(0.1, now=1.0, sessions=3)
    _run(0.1, now=2.0, sessions=7)
    _run(0.1, now=3.0, sessions=7)
    _run(0.1, now=4.0, sessions=2)
    view = load_metrics.session_view(4, wall=5_000.0)
    assert view == SessionView(now=4, peak=7, peak_at=1_002.0)
    assert load_metrics.session_view(9, wall=5_001.0) == SessionView(9, 9, 5_001.0)
    assert load_metrics.session_view(None).now is None


@pytest.mark.parametrize(
    ("response", "cpu", "sessions", "expected"),
    [
        (
            ResponseView(20, 3.0, 9.0, 3.0),
            CpuView(0.7, None, None),
            SessionView(25, 25, 1.0),
            ("slow", "cpu", "sessions"),
        ),
        (ResponseView(20, 2.99, 9.0, 2.99), CpuView(0.69, 0.9, 1.0), SessionView(24, 30, 1.0), ()),
        (ResponseView(5, None, 9.0), CpuView(None, None, None), SessionView(None, 40, 1.0), ()),
        (
            ResponseView(40, 0.4, 1.0, 0.4),
            CpuView(0.1, None, None),
            SessionView(26, 26, 1.0),
            ("sessions",),
        ),
        (ResponseView(30, 4.5, 4.6, None), CpuView(None, None, None), SessionView(2, 2, 1.0), ()),
    ],
    ids=["all-at-threshold", "just-below", "unknown", "sessions-only", "cold-start-only"],
)
def test_the_signal_thresholds_are_inclusive_and_use_now(
    response: ResponseView, cpu: CpuView, sessions: SessionView, expected: tuple[str, ...]
) -> None:
    """문턱은 이상(≥)이고 모르는 값은 넘지 않는다. 세션은 최고가 아니라 지금을 본다 — 상태 알림이
    조건이 사라지면 해소로 닫히게."""
    assert load_metrics.crossed(response, cpu, sessions) == expected


def test_the_real_clock_path_records_a_run() -> None:
    started = load_metrics.begin_run()
    load_metrics.finish_run(started, 3)
    view = load_metrics.response_view()
    assert view.runs == 1 and view.max_seconds is not None and view.max_seconds >= 0
    assert load_metrics.session_view(None).peak == 3


def test_runs_from_many_script_threads_are_all_kept() -> None:
    """세션마다 스크립트 스레드라 회차 끝이 겹친다 — 잠금 하나로 모두 적는다."""
    load_metrics.reset(now=0.0, cpu=0.0)

    def burst(offset: int) -> None:
        for index in range(200):
            _run(0.01, now=offset + index * 0.001, sessions=offset)

    threads = [threading.Thread(target=burst, args=(offset,)) for offset in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert load_metrics.response_view(now=60.0).runs == 1_600
    assert load_metrics.session_view(None).peak == 7
