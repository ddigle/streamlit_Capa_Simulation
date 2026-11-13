# Purpose: 앱이 데이터를 열지 못한 회차의 앱 안 멈춤 판 — 갈래 판정 · 그리기 · 입장 화면 표지.

"""앱 시작 실패 판(2026-11-13 「앱 대신 뜨는 화면」 보드 카드 p1-boot).

`app.py` 의 공식 시나리오 부트스트랩이 실패하면(DB 잠김 · DB 판 올리기 실패 · DB 열기 · 쓰기 실패 ·
그 밖) 사이드바 · 앱 정보 카드 · 알림 칸이 서지 못한다. 그 자리에 앱 안 멈춤 판(`stop_panel`)을
그린다 — 경고 한 줄 · 주 단추 「다시 시도」 · 문의 캡션(사이드바 카드가 없어 여기에) · 참고 「사유 ·
시각」 · 접힌 「관리자용 진단」.

- 경고 한 줄은 사용자가 할 일이 보이는 쉬운 말이다. 프로세스 번호 · 서버 파일 경로 · 개발 PC 조치
  (DB 도구를 닫으라 등) · 원문은 접힌 진단 안으로 옮긴다(복사 단추 — UI-NTF-10). 접어도 누구나
  펼친다 — 로그인한 사람만 닿는 앱 안 화면이다.
- 갈래(`classify_boot_failure`): 잠김(다른 프로세스 · 이 앱 자신이 정리하는 동안) → 「지금은
  데이터를 열 수 없습니다」 + 「다시 시도」. 판 올리기 실패(이미 적용된 마이그레이션이 바뀜 —
  `MigrationChanged`) → 「앱 업데이트를 마치지 못했습니다 — 관리자가 고칠 때까지 열 수 없습니다」,
  다시 해도 같아 「다시 시도」 를 두지 않는다(UI-INP-07). 열기 · 쓰기 실패와 그 밖 → 같은 경고 끝에
  낱말 하나(「디스크가 가득 참」 · 「파일 권한」 · 「파일을 열 수 없음」 · 「그 밖」) + 「다시
  시도」. 새 SQL 을 적용하다 난 DuckDB 오류는 종류로 가를 길이 없어 「그 밖」 이다.
- 참고 줄의 사유 낱말은 이 갈래 키이고 새 번호 체계가 아니다. 시각은 UTC 분까지다.
- 「다시 시도」 는 회차 하나다(누름이 앱 전체를 다시 돌린다) — 부트스트랩은 성공한 회차에만 「해
  봤다」 표지를 세워 다음 회차가 다시 연다.
- 입장 화면 표지: 스타일만 든 칸(`BOOT_STOP_ATTRIBUTE` — 경고 한 줄을 값으로)을 함께 보낸다. 첫
  입장이면 입장 화면이 이 실패를 덮으므로 입장 화면 JS 가 실행이 끝났을 때 이 표지를 읽어 「준비
  완료」 대신 「열지 못함」 을 보인다(`intro_overlay_assets/intro.js`). 본문 자리를 먹지 않는다.
"""

from __future__ import annotations

import errno
import html
import logging
from dataclasses import dataclass
from typing import Final

import duckdb
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.diagnostic_copy import diagnostic_text, render_diagnostic_copy
from capa_simulation.components.stop_panel import reference_line, render_contact_caption
from capa_simulation.page_bootstrap import bootstrap_error_message
from capa_simulation.persistence._migration_core import MigrationChanged
from capa_simulation.persistence._sql_helpers import lock_holder_pid

_LOGGER = logging.getLogger(__name__)

# 입장 화면 JS 가 읽는 표지 속성 — `intro.js` 의 `BOOT_STOP_ATTRIBUTE` 와 같다(시험이 맞댄다).
BOOT_STOP_ATTRIBUTE: Final = "data-capa-boot-stop"
LOCKED_LINE: Final = "지금은 데이터를 열 수 없습니다"
UPDATE_LINE: Final = "앱 업데이트를 마치지 못했습니다 — 관리자가 고칠 때까지 열 수 없습니다"
RETRY_LABEL: Final = "다시 시도"
RETRY_KEY: Final = "boot_stop_retry"
DIAGNOSTIC_LABEL: Final = "관리자용 진단"
DIAGNOSTIC_TITLE: Final = "앱 시작 실패 진단"
COPY_KEY: Final = "boot_stop"
# 화면에 옮기는 원문 길이 — DuckDB 글에는 SQL 줄 · 위치 표시가 붙어 길어진다.
ORIGINAL_LIMIT: Final = 300

# 갈래 키(참고 줄의 사유 낱말) → 경고 끝 낱말. 잠김 · 판 올리기 실패는 낱말 없이 제 글이다.
LOCKED: Final = "db_locked"
MIGRATION_FAILED: Final = "migration_failed"
DISK_FULL: Final = "db_disk_full"
PERMISSION: Final = "db_permission"
CANNOT_OPEN: Final = "db_cannot_open"
OTHER: Final = "db_other"
IO_WORDS: Final = {
    DISK_FULL: "디스크가 가득 참",
    PERMISSION: "파일 권한",
    CANNOT_OPEN: "파일을 열 수 없음",
    OTHER: "그 밖",
}
# DuckDB · OS 의 영문 고정 문구(로캘이 깨도 남는 ASCII 꼬리).
_DISK_FULL_MARKERS: Final = ("No space left on device",)
_PERMISSION_MARKERS: Final = ("Permission denied",)
_OPEN_MARKERS: Final = ("Cannot open", "Could not set lock")


@dataclass(frozen=True)
class BootFailure:
    """앱 시작 실패 한 갈래 — 참고 줄의 사유 낱말 · 경고 한 줄 · 「다시 시도」 를 두는가."""

    code: str
    line: str
    retry: bool


def _io_failure(code: str) -> BootFailure:
    return BootFailure(code, f"{LOCKED_LINE} — {IO_WORDS[code]}", retry=True)


def classify_boot_failure(exc: BaseException) -> BootFailure:
    """부트스트랩 예외 → 갈래. 차례는 잠김 → 판 올리기 실패 → 디스크 가득 → 권한 → 열 수 없음 →
    그 밖이다. 글은 종류 · 영문 고정 문구 · errno 로만 가른다(번역된 앞부분은 보지 않는다)."""
    if lock_holder_pid(exc) is not None:
        return BootFailure(LOCKED, LOCKED_LINE, retry=True)
    if isinstance(exc, MigrationChanged):
        return BootFailure(MIGRATION_FAILED, UPDATE_LINE, retry=False)
    text = str(exc)
    code = getattr(exc, "errno", None)
    if code == errno.ENOSPC or any(marker in text for marker in _DISK_FULL_MARKERS):
        return _io_failure(DISK_FULL)
    if (
        isinstance(exc, PermissionError)
        or code in (errno.EACCES, errno.EPERM)
        or any(marker in text for marker in _PERMISSION_MARKERS)
    ):
        return _io_failure(PERMISSION)
    if isinstance(exc, duckdb.IOException) and any(marker in text for marker in _OPEN_MARKERS):
        return _io_failure(CANNOT_OPEN)
    return _io_failure(OTHER)


def original_line(exc: BaseException) -> str:
    """원문 한 줄 — 종류 이름과 앞 `ORIGINAL_LIMIT` 자(줄바꿈은 빈칸으로)."""
    text = " ".join(str(exc).split())
    return f"{type(exc).__name__}: {text[:ORIGINAL_LIMIT]}"


def boot_marker_html(failure: BootFailure) -> str:
    """입장 화면이 읽는 스타일만 든 표지 — 경고 한 줄을 값으로 싣는다(자리를 먹지 않는다)."""
    return f'<style {BOOT_STOP_ATTRIBUTE}="{html.escape(failure.line, quote=True)}"></style>'


def render_boot_stop(exc: BaseException) -> None:
    """앱 시작 실패 판을 그린다 — `app.py` 가 머리 띠 뒤에 부르고 곧바로 `st.stop()` 한다."""
    failure = classify_boot_failure(exc)
    reference = reference_line(failure.code)
    # 운영 서버의 서버 기록에는 갈래와 종류 이름만 — 원문은 화면의 접힌 진단에 있다.
    _LOGGER.warning("앱 시작 실패 %s (%s)", failure.code, type(exc).__name__)
    st.html(boot_marker_html(failure))
    st.error(failure.line, icon=":material/database_off:")
    if failure.retry:
        st.button(RETRY_LABEL, key=RETRY_KEY, type="primary")
    render_contact_caption()
    st.caption(reference)
    message = bootstrap_error_message(exc)
    with st.expander(DIAGNOSTIC_LABEL):
        render_diagnostic_copy(
            diagnostic_text(
                DIAGNOSTIC_TITLE,
                [reference],
                [alerts.plain_text(message)],
                [original_line(exc)],
            ),
            key=COPY_KEY,
        )
        st.markdown(message)
        st.code(original_line(exc), wrap_lines=True)
