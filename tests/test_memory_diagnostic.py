# Purpose: Admin 「서버 시작 점검」 의 메모리 값 줄 · DuckDB 메모리 한도 줄과 그 실패 알림을 지킨다.

"""`components/memory_diagnostic.py` 와 「서버 시작 점검」 펼침의 그 자리.

값은 이 프로세스의 지금이고 못 읽으면 「모름」 이다(읽는 함수를 대역으로 바꿔 갈래를 본다 —
같은 프로세스의 다른 시험이 Streamlit `Runtime` 을 세웠을 수 있다). 세션 표 · 캐시 값의 크기를
깊이 재지 않는다 — `DataFrame.memory_usage` · 세션 상태 · `cache_resource` 크기 재기를 부르면
실패하게 막고 돈다. DuckDB 한도 칸이 틀리면 표 끝 줄이
「실패」 이고 제목 판정 · 시작 점검 관리자 알림(`AD-01`)에 든다.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pandas as pd
import pytest
import streamlit as st
from alert_marks import active_state
from streamlit.runtime import Runtime
from streamlit.runtime.caching import cache_data_api, cache_resource_api
from streamlit.runtime.state import session_state
from streamlit.runtime.stats import CacheStat
from streamlit.testing.v1 import AppTest

import capa_simulation.settings as settings
from capa_simulation.components import memory_diagnostic
from capa_simulation.components.diagnostic_copy import COMPONENT_KEY_PREFIX
from capa_simulation.components.memory_diagnostic import (
    MEMORY_LIMIT_STEP_LABEL,
    ProcessMemory,
    cache_data_bytes,
    duckdb_line,
    memory_limit_step,
    memory_lines,
    process_line,
    process_memory,
    session_counts,
)
from capa_simulation.persistence import _sql_helpers, duckdb_memory
from capa_simulation.persistence.duckdb_memory import (
    MEMORY_LIMIT_ENV,
    MIB,
    MemorySample,
    database_key,
    memory_limit_setting,
)

SCRIPT = """
from capa_simulation.components.container_start_check import (
    render_container_start_check,
    render_start_check_alert,
)

render_start_check_alert()
render_container_start_check()
"""


@pytest.fixture(autouse=True)
def _fresh_samples() -> Iterator[None]:
    duckdb_memory.reset_samples()
    yield
    duckdb_memory.reset_samples()


def test_the_process_memory_is_vmrss_and_vmhwm(tmp_path: Path) -> None:
    status = tmp_path / "status"
    status.write_text(
        "Name:\tpython\nVmPeak:\t  900000 kB\nVmHWM:\t    2048 kB\nVmRSS:\t    1024 kB\n",
        encoding="ascii",
    )

    assert process_memory(status) == ProcessMemory(rss_bytes=1024 * 1024, peak_bytes=2048 * 1024)


def test_without_proc_only_the_peak_comes_from_resource(tmp_path: Path) -> None:
    """`/proc` 가 없는 곳(macOS · Windows)은 RSS 지금이 「모름」 이고 최고만 `resource` 로 — Windows
    는 그것도 없다."""
    memory = process_memory(tmp_path / "missing")

    assert memory.rss_bytes is None
    if sys.platform == "win32":
        assert memory.peak_bytes is None
    else:
        assert memory.peak_bytes is not None and memory.peak_bytes > 0


def test_the_session_counts_are_unknown_without_a_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """내부 API 라 없거나 무엇이 나면 「모름」 — 있으면 연결된 세션 · 전체 세션이다."""
    monkeypatch.setattr(Runtime, "exists", classmethod(lambda cls: False))
    assert session_counts() is None

    manager = SimpleNamespace(num_active_sessions=lambda: 3, num_sessions=lambda: 5)
    monkeypatch.setattr(Runtime, "exists", classmethod(lambda cls: True))
    monkeypatch.setattr(
        Runtime, "instance", classmethod(lambda cls: SimpleNamespace(_session_mgr=manager))
    )
    assert session_counts() == (3, 5)

    def broken(cls: type[Runtime]) -> Any:
        raise RuntimeError("판이 바뀜")

    monkeypatch.setattr(Runtime, "instance", classmethod(broken))
    assert session_counts() is None


def test_the_cache_data_total_is_the_stored_length(monkeypatch: pytest.MonkeyPatch) -> None:
    stats = {
        "cache_memory_bytes": [
            CacheStat("st_cache_data", "demo_a", 100),
            CacheStat("st_cache_data", "demo_b", 28),
        ]
    }
    monkeypatch.setattr(
        cache_data_api,
        "get_data_cache_stats_provider",
        lambda: SimpleNamespace(get_stats=lambda: stats),
    )
    assert cache_data_bytes() == 128

    def broken() -> Any:
        raise RuntimeError("판이 바뀜")

    monkeypatch.setattr(cache_data_api, "get_data_cache_stats_provider", broken)
    assert cache_data_bytes() is None


def test_the_lines_never_size_session_tables_deeply(monkeypatch: pytest.MonkeyPatch) -> None:
    """잠긴 세션 표의 크기 재기(`memory_usage(deep=True)`)와 세션 상태 · `cache_resource` 크기
    재기를 부르지 않는다 — 진단은 프로세스 · DuckDB 값과 `cache_data` 저장 길이뿐이다."""

    @st.cache_data
    def demo_frame() -> pd.DataFrame:
        return pd.DataFrame({"공정": ["DEMO_A", "DEMO_B"], "값": [1, 2]})

    demo_frame()

    def refuse(*_: Any, **__: Any) -> Any:
        raise AssertionError("깊은 크기 재기를 불렀다")

    monkeypatch.setattr(pd.DataFrame, "memory_usage", refuse)
    monkeypatch.setattr(session_state.SessionStateStatProvider, "get_stats", refuse)
    monkeypatch.setattr(cache_resource_api.ResourceCaches, "get_stats", refuse)
    try:
        lines = memory_lines()
        total = cache_data_bytes()
    finally:
        demo_frame.clear()

    assert len(lines) == 3 and total is not None and total > 0


def test_unknown_values_read_as_unknown() -> None:
    assert process_line(ProcessMemory(None, None), None, None) == (
        "**메모리 지금** · RSS 모름 · 최고 모름 · 세션 모름 · cache_data 모름"
    )
    assert duckdb_line("설비", None) == "**DuckDB 설비 회차 끝** · 모름"
    sample = MemorySample(
        last_bytes=3 * MIB // 2, peak_bytes=12 * MIB, peak_temporary_bytes=0, limit=None, count=4
    )
    assert duckdb_line("시뮬레이션", sample) == (
        "**DuckDB 시뮬레이션 회차 끝** · 마지막 1.5 MiB · 최고 12.0 MiB · 임시 파일 최고 0.0 MiB"
        " · 한도 모름"
    )


def test_the_limit_step_reads_the_applied_setting() -> None:
    assert memory_limit_step(memory_limit_setting({})) == (
        MEMORY_LIMIT_STEP_LABEL,
        "건너뜀",
        f"{MEMORY_LIMIT_ENV} 없음 — DuckDB 기본",
    )
    assert memory_limit_step(memory_limit_setting({MEMORY_LIMIT_ENV: "256 mib"})) == (
        MEMORY_LIMIT_STEP_LABEL,
        "정상",
        "DB 마다 256MiB",
    )
    assert memory_limit_step(memory_limit_setting({MEMORY_LIMIT_ENV: "80%"})) == (
        MEMORY_LIMIT_STEP_LABEL,
        "실패",
        f"{MEMORY_LIMIT_ENV} 꼴이 틀림 — DuckDB 기본 그대로",
    )
    assert memory_limit_step(memory_limit_setting({MEMORY_LIMIT_ENV: "16MiB"}))[2] == (
        f"{MEMORY_LIMIT_ENV} 64MiB ~ 1TiB 밖 — DuckDB 기본 그대로"
    )


def _report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """모든 단계가 정상인 시작 결과 파일 · 시뮬레이션 DB 자리."""
    report = tmp_path / "container_start.json"
    report.write_text(
        json.dumps(
            {
                "version": 1,
                "written_at": "2026-11-17T09:00:00+09:00",
                "steps": {
                    step: {"status": "ok", "reason": "정상"}
                    for step in ("install", "token", "user_name")
                },
            }
        ),
        encoding="utf-8",
    )
    database = tmp_path / "scenario.duckdb"
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", report)
    monkeypatch.setattr(settings, "DUCKDB_PATH", database)
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    return database


def _start_check(app: AppTest) -> tuple[str, pd.DataFrame, str]:
    """(펼침 제목, 단계 표, 캡션 전부). 아이콘이 달린 펼침을 AppTest 는 `status` 로 센다."""
    labels = [item.label for item in app.expander] + [item.label for item in app.status]
    [title] = [label for label in labels if "서버 시작 점검" in label]
    [steps] = [frame for frame in app.dataframe if "단계" in getattr(frame.value, "columns", [])]
    captions = "\n".join(caption.value for caption in app.caption)
    return title, steps.value, captions


def test_the_start_check_carries_the_limit_row_and_unknown_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diagnostic_copies: dict[str, str]
) -> None:
    """한도 칸이 없으면 끝 줄이 「건너뜀」 이고 제목 판정 · `AD-01` 은 그대로다. 아직 못 잰 DuckDB
    와 읽지 못한 세션은 「모름」."""
    _report(tmp_path, monkeypatch)
    monkeypatch.setattr(memory_diagnostic, "session_counts", lambda: None)

    app = AppTest.from_string(SCRIPT).run(timeout=60)

    assert not list(app.exception), [item.message for item in app.exception]
    title, steps, captions = _start_check(app)
    assert title == "서버 시작 점검 · 모두 정상"
    assert steps.iloc[-1].tolist() == [
        MEMORY_LIMIT_STEP_LABEL,
        "건너뜀",
        f"{MEMORY_LIMIT_ENV} 없음 — DuckDB 기본",
    ]
    assert "**메모리 지금** · RSS " in captions and "세션 모름" in captions
    assert "**DuckDB 시뮬레이션 회차 끝** · 모름" in captions
    assert "**DuckDB 설비 회차 끝** · 모름" in captions
    assert active_state(app, "AD-01") is None
    text = diagnostic_copies[f"{COMPONENT_KEY_PREFIX}container_start_check"]
    assert "DuckDB 메모리 한도\t건너뜀\t" in text
    assert "메모리 지금 · RSS " in text and "DuckDB 시뮬레이션 회차 끝 · 모름" in text


def test_the_start_check_shows_the_values_it_can_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diagnostic_copies: dict[str, str]
) -> None:
    database = _report(tmp_path, monkeypatch)
    monkeypatch.setattr(
        _sql_helpers, "DUCKDB_MEMORY_LIMIT", memory_limit_setting({MEMORY_LIMIT_ENV: "256MiB"})
    )
    monkeypatch.setattr(
        memory_diagnostic, "process_memory", lambda: ProcessMemory(600 * MIB, 800 * MIB)
    )
    monkeypatch.setattr(memory_diagnostic, "session_counts", lambda: (3, 5))
    monkeypatch.setattr(memory_diagnostic, "cache_data_bytes", lambda: 38 * MIB)
    connection = duckdb.connect(
        str(database), config={"default_block_size": 16384, "memory_limit": "256MiB"}
    )
    try:
        duckdb_memory.observe(database_key(database), connection)
    finally:
        connection.close()

    app = AppTest.from_string(SCRIPT).run(timeout=60)

    assert not list(app.exception), [item.message for item in app.exception]
    title, steps, captions = _start_check(app)
    assert title == "서버 시작 점검 · 모두 정상"
    assert steps.iloc[-1].tolist() == [MEMORY_LIMIT_STEP_LABEL, "정상", "DB 마다 256MiB"]
    assert (
        "**메모리 지금** · RSS 600.0 MiB · 최고 800.0 MiB · 세션 연결 3 · 전체 5 · "
        "cache_data 38.0 MiB"
    ) in captions
    assert "**DuckDB 시뮬레이션 회차 끝** · 마지막 " in captions
    assert "한도 256\\.0 MiB" in captions
    text = diagnostic_copies[f"{COMPONENT_KEY_PREFIX}container_start_check"]
    assert "한도 256.0 MiB" in text


# 옆 칸을 잘못 붙여 넣은 값 꼴(비밀 키 같은 44글자) — 합성 값이다.
PASTED_BY_MISTAKE = "demoPastedSecretValue0123456789abcdefABCDEF="


def test_a_wrong_limit_fails_the_row_the_title_and_raises_ad01(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diagnostic_copies: dict[str, str]
) -> None:
    """틀린 값은 기본으로 물러서고(연결 설정에 넣지 않음) 표 끝 줄이 「실패」 — 시작 점검 관리자
    알림 `AD-01` 에 든다(「그 화면으로」 Admin Area). 틀린 값의 글은 표 · 복사 글 · 알림 전문
    어디에도 싣지 않는다 — 옆 칸(비밀 키 · 토큰)을 잘못 붙여 넣은 값일 수 있다."""
    _report(tmp_path, monkeypatch)
    monkeypatch.setattr(
        _sql_helpers,
        "DUCKDB_MEMORY_LIMIT",
        memory_limit_setting({MEMORY_LIMIT_ENV: PASTED_BY_MISTAKE}),
    )

    app = AppTest.from_string(SCRIPT).run(timeout=60)

    assert not list(app.exception), [item.message for item in app.exception]
    title, steps, _ = _start_check(app)
    assert title == "서버 시작 점검 · 실패 있음"
    assert steps.iloc[-1].tolist() == [
        MEMORY_LIMIT_STEP_LABEL,
        "실패",
        f"{MEMORY_LIMIT_ENV} 꼴이 틀림 — DuckDB 기본 그대로",
    ]
    note = active_state(app, "AD-01")
    assert note is not None and note["short"] == "서버 시작 점검 실패 — DuckDB 메모리 한도"
    assert f"DuckDB 메모리 한도: {MEMORY_LIMIT_ENV} 꼴이 틀림" in note["full"]
    assert note["href"] == "admin_area"
    text = diagnostic_copies[f"{COMPONENT_KEY_PREFIX}container_start_check"]
    assert f"DuckDB 메모리 한도\t실패\t{MEMORY_LIMIT_ENV} 꼴이 틀림" in text
    shown = [*steps.astype(str).to_numpy().ravel(), note["short"], note["full"], text]
    for piece in (PASTED_BY_MISTAKE[:8], PASTED_BY_MISTAKE[-8:]):
        assert not [place for place in shown if piece in place], piece
