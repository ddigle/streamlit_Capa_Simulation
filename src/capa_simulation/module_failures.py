# Purpose: 모듈의 실행 실패·제외된 화면·회차 시간·접두 없는 키를 프로세스 안에 적고 읽는다.

"""모듈 실행 기록(UI 없음 — Streamlit 실행 문맥 없이 돈다).

모듈 화면 감싸기(`module_runtime`), 콜백·프래그먼트 감싸기(`module_api` 의 `ctx.callback`·
`ctx.guard`), 화면 등록 실패(`navigation`)가 모두 여기에 적고 Admin Area 「모듈 상태」 가
읽는다.
세 곳이 서로를 import 하지 않게(순환 막기) 저장소를 UI 없는 이 파일 하나로 뗐다.

- 프로세스 전역 dict 몇 개에 `threading.Lock` 하나를 건다(스레드를 세우는 것이 아니다).
- **메시지 본문은 적지 않는다** — 시각·예외 형식 이름·자리·화면 slug 만. 실데이터 값이 기록에 남지
  않게 한다.
- 재시작하면 비어 있다(CD 에는 로그가 없어 Admin 표가 마지막 오류를 보이는 자리다).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from capa_simulation.module_registry import key_prefix

# 모듈 화면마다 남기는 접두 없는 키 이름의 상한.
MAX_KEY_WARNINGS: Final = 5
# 콜백 실패 표지 칸의 꼬리. 모듈 키는 `_` 로 시작하지 못하므로(`ModuleContext.key`) 모듈 자기 키와
# 겹치지 않는다.
CALLBACK_FAILURE_SUFFIX: Final = "_core_callback_failure"


@dataclass(frozen=True)
class ModuleFailure:
    # "HH:MM:SS"(서버 시각).
    at: str
    # 화면 slug — 콜백·guard 에서는 화면을 몰라 빈 글자다.
    page: str
    # 예외 형식 이름.
    kind: str
    # "page" | "callback" | "guard" | "load".
    where: str


_LOCK = threading.Lock()
_FAILURES: dict[str, ModuleFailure] = {}
_EXCLUDED: dict[tuple[str, str], str] = {}
_RUN_SECONDS: dict[str, float] = {}
_KEY_WARNINGS: dict[str, tuple[str, ...]] = {}


def record_failure(module_id: str, *, page: str, kind: str, where: str) -> None:
    """모듈의 마지막 실패 하나를 적는다(앞의 것은 덮는다)."""
    failure = ModuleFailure(at=time.strftime("%H:%M:%S"), page=page, kind=kind, where=where)
    with _LOCK:
        _FAILURES[module_id] = failure


def last_failures() -> Mapping[str, ModuleFailure]:
    """id → 마지막 실패. 읽기 전용 사본이다."""
    with _LOCK:
        return MappingProxyType(dict(_FAILURES))


def exclude_page(module_id: str, slug: str, reason: str) -> None:
    """`st.Page` 를 못 만든 화면을 재시작까지 뺀다 — 들락거리면 사이드바 요소 수가 바뀐다."""
    with _LOCK:
        _EXCLUDED[(module_id, slug)] = reason


def excluded_pages() -> frozenset[tuple[str, str]]:
    """재시작까지 뺀 화면 (id, slug)."""
    with _LOCK:
        return frozenset(_EXCLUDED)


def note_run_seconds(module_id: str, seconds: float) -> None:
    """모듈 화면 회차 하나가 걸린 시간(초). 한 프로세스라 오래 돌면 모든 사용자가 느리다."""
    with _LOCK:
        _RUN_SECONDS[module_id] = seconds


def last_run_seconds() -> Mapping[str, float]:
    with _LOCK:
        return MappingProxyType(dict(_RUN_SECONDS))


def note_key_warnings(module_id: str, keys: Sequence[str]) -> None:
    """모듈 화면이 건드린 접두 없는 세션 키 이름(최대 `MAX_KEY_WARNINGS` 개, 값은 적지 않는다)."""
    with _LOCK:
        _KEY_WARNINGS[module_id] = tuple(keys[:MAX_KEY_WARNINGS])


def key_warnings() -> Mapping[str, tuple[str, ...]]:
    with _LOCK:
        return MappingProxyType(dict(_KEY_WARNINGS))


def clear_records() -> None:
    """기록을 모두 비운다(시험용)."""
    with _LOCK:
        _FAILURES.clear()
        _EXCLUDED.clear()
        _RUN_SECONDS.clear()
        _KEY_WARNINGS.clear()


def callback_failure_key(module_id: str) -> str:
    """콜백 실패 표지 칸 — `mod_<id>___core_callback_failure`(접두 + `_` 로 시작하는 꼬리)."""
    return key_prefix(module_id) + CALLBACK_FAILURE_SUFFIX
