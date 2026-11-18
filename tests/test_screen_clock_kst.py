# Purpose: 화면 · 알림 · 복사 글의 시각이 서버 시각대(TZ)와 상관없이 KST 로 서는지 — 대표 자리를
# UTC 서버에서 본다.

"""화면 시각은 KST(설계 규칙 UI-DAT-11 · UI-CON-02 — 시각 한 곳 `korea_time`).

감사 표(「시각(KST)」)와 같은 Admin Area 의 다른 시각(접속 명단 「등록 시각」 · 「최근 등록 ·
빼기」 · 서버 시작 점검 · DB 동기화 · 토큰 · 통합인증 최근 사건 · 화면 오류 알림 · 모듈 상태)이
서버 시각대를 따르면, C-DEP 컨테이너가 UTC 일 때 같은 일이 9시간 어긋나 보인다. 개발 WSL · 사내
PC 는 KST 라 드러나지 않으므로 여기서는 프로세스 시각대를 UTC 로 바꿔 끼우고 본다(CI 러너
ubuntu-latest 도 UTC 다). 고른 순간은 KST 로 날짜가 넘어가는 때다 — UTC 로 그리면 날짜부터
다르다.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from capa_simulation import korea_time, module_failures, page_failures
from capa_simulation.audit import read as audit_read
from capa_simulation.auth import page_frame, runtime
from capa_simulation.auth.access import ListChange, ListDocument, ListEntry
from capa_simulation.components import (
    access_list_admin,
    access_list_grid,
    bdq_token_admin,
    container_start_check,
    object_sync_status,
    sso_status,
)
from capa_simulation.io.bdq_token import TokenState
from capa_simulation.object_sync_worker import SyncHealth, WorkerStatus

# 2026-11-14 16:56:09 UTC = 2026-11-15 01:56:09 KST.
MOMENT = datetime(2026, 11, 14, 16, 56, 9, tzinfo=timezone.utc)
MOMENT_TEXT = "2026-11-14T16:56:09Z"
EPOCH = int(MOMENT.timestamp())
KST_MINUTE = "2026-11-15 01:56"
KST_SECOND = "2026-11-15 01:56:09"


def _clock_at(epoch: int) -> SimpleNamespace:
    """`time` 모듈 대역 — 지금이 `epoch` 이다. 서식 · 시각대 부름은 진짜 것이라 서버 시각대 변환을
    쓰면 바꿔 끼운 UTC 가 나온다."""
    return SimpleNamespace(
        time=lambda: float(epoch),
        strftime=lambda layout, moment=None: time.strftime(
            layout, time.localtime(epoch) if moment is None else moment
        ),
        localtime=time.localtime,
    )


@pytest.fixture
def utc_server() -> Iterator[None]:
    """프로세스 시각대를 UTC 로 바꿔 끼우고 끝에 되돌린다(시각대 db 가 없어도 서는 POSIX 꼴).
    바꿔 끼울 수 없는 OS(Windows)는 건너뛴다."""
    tzset = getattr(time, "tzset", None)
    if tzset is None:
        pytest.skip("시각대를 바꿔 끼울 수 없는 OS")
    before = os.environ.get("TZ")
    os.environ["TZ"] = "UTC0"
    tzset()
    try:
        # 바꿔 끼움이 먹었는지 — 서버 시각대 변환이 UTC 를 내야 아래 맞댐이 뜻이 있다.
        assert MOMENT.astimezone().utcoffset() == timezone.utc.utcoffset(None)
        yield
    finally:
        if before is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = before
        tzset()


def test_the_access_list_times_are_korean_on_a_utc_server(utc_server: None) -> None:
    """접속 명단 편집 표 「등록일」 과 「최근 등록 · 빼기」 의 시각 — 파일의 UTC 를 KST 로 옮긴다
    (UTC 16:56 은 KST 다음 날 01:56)."""
    document = ListDocument(
        revision=1,
        entries=(ListEntry("dev.user", added_by="admin", added_at=MOMENT_TEXT),),
        changes=(ListChange(by="admin", at=MOMENT_TEXT, what="add", loginid="dev.user"),),
    )

    recent = access_list_admin.recent_changes_table(document, now=EPOCH + 60)

    assert access_list_grid.date_text(MOMENT_TEXT) == KST_MINUTE[:10]
    assert recent.iloc[0, 0] == KST_MINUTE


def test_a_hand_written_time_without_a_zone_stays_as_written() -> None:
    """사람이 고친 파일의 시각대 없는 시각은 어느 시각대인지 몰라 옮기지 않고 받은 글 그대로다
    — 서버 시각대로 읽어 옮기지 않는다."""
    assert access_list_grid.date_text("2026-11-14T16:56:09") == "2026-11-14T16:56:09"


def test_the_one_clock_turns_moments_and_seconds_into_korean_time(utc_server: None) -> None:
    """한 곳 `korea_time` — 시각대 붙은 시각 · UNIX 초는 서버 시각대와 상관없이 KST 다."""
    assert korea_time.kst_clock(MOMENT, "%Y-%m-%d %H:%M:%S") == KST_SECOND
    assert korea_time.kst_clock(EPOCH, "%Y-%m-%d %H:%M:%S") == KST_SECOND


def test_the_one_clock_does_not_guess_a_zone_and_is_the_only_kst() -> None:
    """시각대 없는 시각은 옮기지 않는다(`ValueError`). 감사 기록 화면 · 앱 밖 화면의 KST 도 이
    상수 하나다."""
    with pytest.raises(ValueError):
        korea_time.kst_clock(datetime(2026, 11, 14, 16, 56, 9), "%H:%M")
    assert audit_read.KST is korea_time.KST
    assert page_frame.KST is korea_time.KST


def test_the_start_check_time_is_korean_on_a_utc_server(utc_server: None) -> None:
    """서버 시작 점검의 시작 기록 · 토큰 파일 수정 시각(진단 펼침 꼴 — 초까지)."""
    assert container_start_check.clock_text(MOMENT_TEXT) == KST_SECOND
    assert container_start_check.clock_text("2026-11-15T01:56:09+09:00") == KST_SECOND


def test_the_sync_times_are_korean_on_a_utc_server(utc_server: None) -> None:
    """DB 동기화 펼침의 「마지막 올림」 · 「마지막 정리」."""
    status = WorkerStatus(
        alive=True,
        phase="idle",
        last_tick=0.0,
        last_success_utc=MOMENT_TEXT,
        last_prune_utc=MOMENT_TEXT,
        last_prune_deleted=0,
    )

    lines = object_sync_status.status_lines(status, SyncHealth(title="정상"), now=0.0)

    assert f"**마지막 올림** · {KST_SECOND}" in lines
    assert any(line.startswith(f"**마지막 정리** · {KST_SECOND}") for line in lines)


def test_the_token_times_are_korean_on_a_utc_server(utc_server: None) -> None:
    """Admin 「서버 시작 점검」 의 「지금 토큰」 줄 — 파일 수정 · 만료 시각."""
    state = TokenState("file", modified_at=MOMENT, expires_at=MOMENT)

    line = bdq_token_admin.token_line(state)

    assert line == f"**지금 토큰** · 파일 · 수정 {KST_SECOND} · 만료 {KST_SECOND} · 지남"


def test_the_sso_event_time_is_korean_on_a_utc_server(
    utc_server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """통합인증 진단 펼침의 최근 사건 표 「시각」."""
    monkeypatch.setattr(runtime, "_now", lambda: EPOCH)
    runtime.record_event("session_closed", reason="revoked", loginid="dev.user")

    assert sso_status.recent_event_table()["시각"].tolist()[0] == KST_SECOND


def test_the_page_failure_time_is_korean_on_a_utc_server(
    utc_server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """화면 오류 관리자 알림(`AD-22`) 전문의 시각 — 카드 참고 줄(UTC 분)과 같은 순간의 KST."""
    monkeypatch.setattr(page_failures, "time", _clock_at(EPOCH))

    failure = page_failures.record_failure(page="HOME", href="", kind="ValueError")

    assert failure.at == "01:56:09"


def test_the_module_failure_time_is_korean_on_a_utc_server(
    utc_server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Admin 모듈 상태 표 「최근 실패」 칸의 시각."""
    monkeypatch.setattr(module_failures, "time", _clock_at(EPOCH))

    module_failures.record_failure("demo_clock", page="main", kind="ValueError", where="page")

    assert module_failures.last_failures()["demo_clock"].at == "01:56:09"
