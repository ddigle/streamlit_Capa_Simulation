# Purpose: 앱이 데이터를 열지 못한 회차의 앱 안 멈춤 판 — 갈래 판정 · 그리기 · 입장 화면 표지.

"""앱 시작 실패 판(2026-11-13 「앱 대신 뜨는 화면」 보드 카드 p1-boot).

`app.py` 의 공식 시나리오 부트스트랩이 실패하면(DB 잠김 · DB 판 올리기 실패 · DB 열기 · 쓰기 실패 ·
그 밖) 사이드바 · 앱 정보 카드 · 알림 칸이 서지 못한다. 그 자리에 앱 안 멈춤 판(`stop_panel`)을
그린다 — 경고 한 줄 · 주 단추 「다시 시도」 · 문의 캡션(사이드바 카드가 없어 여기에) · 참고 「사유 ·
시각 · 오류 종류」 · 접힌 「관리자용 진단」(관리자 몫에만).

- 경고 한 줄은 사용자가 할 일이 보이는 쉬운 말이다. 프로세스 번호 · 서버 파일 경로 · 개발 PC 조치
  (DB 도구를 닫으라 등) · 원문은 접힌 진단 안으로 옮긴다(복사 단추 — UI-NTF-10). 접힌 진단은 관리자
  몫(`admin_view.admin_notes_visible` — 관리자, 또는 운영 아닌 꺼진 서버의 누구나)에만 선다 — 접어도
  누구나 펼치므로 접힘으로 가리지 않는다. 다른 사람에게는 참고 줄 끝의 오류 종류 이름만이다(보드
  d12 (가) — 문의할 때 쓸 이름). 판정이 무엇을 내도 닫힌 쪽(진단 없음)으로 물러선다 — 마지막 자리다.
- 갈래(`classify_boot_failure`): 잠김 → 「지금은 데이터를 열 수 없습니다」 + 「다시 시도」. 다른
  프로세스가 쥔 잠김은 사람이 고칠 수 없는 원인이라 경고 끝이 「— 관리자에게 알려 주세요」 다 — 뒤
  회차의 같은 잠김(`page_bootstrap.screen_error_short` 의 `ADMIN_TAIL`, 카드 p1-no-revision)과 같은
  일을 시킨다. 이 앱 자신이 정리하는 동안의 잠김은 다시 하면 풀려 붙이지 않는다(뒤 회차도
  새로고침을 권한다). 판 올리기 실패(`MigrationFailed` — 이미 적용된
  마이그레이션이 바뀜 · 새 SQL 이 SQL · 데이터 오류로 실패함) → 「앱 업데이트를 마치지 못했습니다 —
  관리자가 고칠 때까지 열 수 없습니다」, 다시 해도 같아 「다시 시도」 를 두지 않는다(UI-INP-07).
  열기 · 쓰기 실패와 그 밖 → 같은 경고 끝에 낱말 하나(「디스크가 가득 참」 · 「파일 권한」 ·
  「파일을 열 수 없음」 · 「그 밖」) + 「다시 시도」. 새 SQL 을 적용하다 난 입출력 오류(디스크 가득
  등)는 감싸지 않아 제 갈래로 간다.
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
from capa_simulation.components.admin_view import admin_notes_visible
from capa_simulation.components.diagnostic_copy import (
    ADMIN_DIAGNOSTIC_LABEL,
    diagnostic_text,
    render_diagnostic_copy,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.stop_panel import reference_line, render_contact_caption
from capa_simulation.page_bootstrap import ADMIN_TAIL, bootstrap_error_message
from capa_simulation.persistence._migration_core import MigrationFailed
from capa_simulation.persistence._sql_helpers import is_own_process_lock, lock_holder_pid

_LOGGER = logging.getLogger(__name__)

# 입장 화면 JS 가 읽는 표지 속성 — `intro.js` 의 `BOOT_STOP_ATTRIBUTE` 와 같다(시험이 맞댄다).
BOOT_STOP_ATTRIBUTE: Final = "data-capa-boot-stop"
LOCKED_LINE: Final = "지금은 데이터를 열 수 없습니다"
# 다른 프로세스가 쥔 잠김 — 뒤 회차의 DB 실패 알림 짧은 글과 같은 꼬리.
HELD_LINE: Final = f"{LOCKED_LINE}{ADMIN_TAIL}"
UPDATE_LINE: Final = "앱 업데이트를 마치지 못했습니다 — 관리자가 고칠 때까지 열 수 없습니다"
RETRY_LABEL: Final = "다시 시도"
RETRY_KEY: Final = "boot_stop_retry"
DIAGNOSTIC_KEY: Final = "boot_stop_diagnostic"
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
        line = LOCKED_LINE if is_own_process_lock(exc) else HELD_LINE
        return BootFailure(LOCKED, line, retry=True)
    if isinstance(exc, MigrationFailed):
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


def _source(exc: BaseException) -> BaseException:
    """원문이 될 오류 — 판 올리기 실패가 감싼 DuckDB 오류면 그것(`__cause__`), 아니면 그대로."""
    cause = exc.__cause__
    return cause if isinstance(exc, MigrationFailed) and cause is not None else exc


def kind_name(exc: BaseException) -> str:
    """오류 종류 이름 — 판 올리기 실패가 감싼 DuckDB 오류면 그 종류. 누구에게나 보이는 값이다."""
    return type(_source(exc)).__name__


def original_line(exc: BaseException) -> str:
    """원문 한 줄 — 종류 이름과 앞 `ORIGINAL_LIMIT` 자(줄바꿈은 빈칸으로). 판 올리기 실패가 감싼
    DuckDB 오류면 그 오류다(어느 파일인지는 진단의 앞 글이 말한다)."""
    source = _source(exc)
    text = " ".join(str(source).split())
    return f"{type(source).__name__}: {text[:ORIGINAL_LIMIT]}"


def boot_marker_html(failure: BootFailure) -> str:
    """입장 화면이 읽는 스타일만 든 표지 — 경고 한 줄을 값으로 싣는다(자리를 먹지 않는다)."""
    return f'<style {BOOT_STOP_ATTRIBUTE}="{html.escape(failure.line, quote=True)}"></style>'


def render_boot_stop(exc: BaseException) -> None:
    """앱 시작 실패 판을 그린다 — `app.py` 가 머리 띠 뒤에 부르고 곧바로 `st.stop()` 한다."""
    failure = classify_boot_failure(exc)
    head = reference_line(failure.code)
    kind = kind_name(exc)
    reference = f"{head} · {kind}"
    # 운영 서버의 서버 기록에는 갈래와 종류 이름만 — 원문은 관리자 몫의 접힌 진단에 있다.
    _LOGGER.warning("앱 시작 실패 %s (%s)", failure.code, kind)
    st.html(boot_marker_html(failure))
    st.error(failure.line, icon=":material/database_off:")
    if failure.retry:
        st.button(RETRY_LABEL, key=RETRY_KEY, type="primary")
    render_contact_caption()
    st.caption(f"{head} · {literal_markdown(kind)}")
    if not _diagnostic_visible():
        return
    blocks = ([reference], [alerts.plain_text(bootstrap_error_message(exc))], [original_line(exc)])
    with st.expander(ADMIN_DIAGNOSTIC_LABEL, key=DIAGNOSTIC_KEY):
        render_diagnostic_copy(diagnostic_text(DIAGNOSTIC_TITLE, *blocks), key=COPY_KEY)
        # 진단 글은 글자 그대로(평문 칸) — 조치 문장 · 파일 경로 · 원문을 자리 글로 늘어놓지 않는다.
        st.code("\n\n".join("\n".join(block) for block in blocks), language=None, wrap_lines=True)


def _diagnostic_visible() -> bool:
    """접힌 진단을 세우나 — 관리자 몫(`admin_notes_visible`)일 때만. 이 판이 마지막 자리라 판정이
    무엇을 내도 닫힌 쪽으로 물러선다."""
    try:
        return admin_notes_visible()
    except Exception:
        return False
