# Purpose: 모듈이 import 하는 유일한 코어 창구 v1 — 문맥·키·머리말·색만 내고 데이터는 없다.

"""모듈 공개 창구 v1(모델 2 — 2026-11-01 사용자 결정).

모듈(`modules/<id>/`)은 코어에서 **이 모듈 하나만** import 한다. 겉면은 `__all__` 이 전부이고
`tests/test_module_api_surface.py` 가 이름·서명·칸을 고정한다. 바꾸는 법(AGENTS 12장 「코어 공개
창구 변경」): 같은 큰 판 안에서는 더하기만 하고 작은 판(`API_MINOR`)을 올린다. 지우기·이름
바꾸기·서명 바꾸기는 큰 판을 올린다.

- 데이터(시나리오·기준정보·조회기간·DB)는 내지 않는다 — v2(데이터 연계)의 몫이다.
- 위젯 콜백은 `ctx.callback(fn)` 으로 감싼다. 콜백은 회차 맨 앞(`app.py` 가 돌기 전)에 불려, 감싸지
  않은 콜백의 예외는 그 회차의 사이드바·머리 띠·탭 줄을 지운다.
- 프래그먼트·`st.dialog` 본문은 `with ctx.guard():` 로 감싼다 — 프래그먼트만 도는 회차는 `app.py`
  밖이라 화면 감싸기(`module_runtime`)가 닿지 않는다.
- `palette()` 는 이번 회차 테마의 색이다. 캐시 함수 안에서 부르지 말고 값을 인자로 넘긴다(한 테마가
  모든 사용자에게 굳는다).
"""

from __future__ import annotations

import contextlib
import functools
import logging
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

import streamlit as st
from streamlit.errors import FragmentHandledException
from streamlit.runtime.scriptrunner_utils.exceptions import ScriptControlException

# 코어 이름은 모두 `_` 별명으로 들인다 — 모듈이 `api.<이름>` 으로 닿는 공개 이름은 `__all__`
# 뿐이어야 한다(`api.module_registry.settings` 같은 길로 코어 설정·DB 자리에 닿지 않게). 겉면
# 시험이 지킨다.
from capa_simulation import module_failures as _module_failures
from capa_simulation import module_registry as _module_registry
from capa_simulation.components.module_failure_card import failure_parts as _failure_parts
from capa_simulation.components.module_failure_card import (
    render_module_failure_card as _render_module_failure_card,
)
from capa_simulation.components.page_header import render_page_header as _render_page_header
from capa_simulation.design import tokens as _tokens
from capa_simulation.navigation import IMPLEMENTING_SUFFIX as _IMPLEMENTING_SUFFIX

__all__ = [
    "API_VERSION",
    "FONT_FAMILY",
    "IMPLEMENTING_SUFFIX",
    "PALETTE_KEYS",
    "ModuleContext",
    "ModuleContextError",
    "context",
    "page_header",
    "palette",
]

API_VERSION: Final[tuple[int, int]] = (_module_registry.API_MAJOR, _module_registry.API_MINOR)
FONT_FAMILY: Final[str] = _tokens.FONT_FAMILY
IMPLEMENTING_SUFFIX: Final[str] = _IMPLEMENTING_SUFFIX
PALETTE_KEYS: Final[tuple[str, ...]] = (
    "surface",
    "surface_subtle",
    "border",
    "text",
    "text_muted",
    "accent",
    "secure",
    "warning",
    "shortage",
)
# 역할 이름 → 디자인 토큰 이름(`design/tokens.py` — 테마에 따라 값이 갈린다).
_PALETTE_TOKENS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "surface": "SURFACE",
        "surface_subtle": "SURFACE_SUBTLE",
        "border": "BORDER",
        "text": "TEXT",
        "text_muted": "TEXT_MUTED",
        "accent": "ACCENT",
        "secure": "STATUS_SECURE",
        "warning": "STATUS_WARNING",
        "shortage": "STATUS_SHORTAGE",
    }
)
_LOGGER = logging.getLogger("capa_simulation.modules")


class ModuleContextError(RuntimeError):
    """모듈 문맥을 만들지 못했다 — `module.json` 을 못 찾았거나 선언이 틀렸다."""


@dataclass(frozen=True)
class ModuleContext:
    """모듈 하나의 문맥. 화면·도움 코드가 `ctx = api.context(__file__)` 로 받는다."""

    id: str
    name: str
    owner: str
    # "L0" | "L1" | "L2"
    maturity: str
    # 모듈 폴더(읽기용 — 실행 중 쓰기는 `data_dir` 만).
    folder: Path
    api_version: tuple[int, int]

    @property
    def key_prefix(self) -> str:
        """이 모듈 세션 키의 접두 — `mod_<id>__`."""
        return _module_registry.key_prefix(self.id)

    def key(self, name: str) -> str:
        """`mod_<id>__<name>`. 이미 접두가 있으면 그대로다(멱등).

        빈 이름과 `_` 로 시작하는 이름은 `ValueError` — 접두 뒤 `_` 자리는 코어 표지 칸이다.
        """
        prefix = self.key_prefix
        rest = name[len(prefix) :] if isinstance(name, str) and name.startswith(prefix) else name
        if not isinstance(rest, str) or not rest or rest.startswith("_"):
            raise ValueError("모듈 키 이름은 비어 있지 않고 `_` 로 시작하지 않아야 합니다")
        return prefix + rest

    @property
    def data_dir(self) -> Path:
        """이 모듈의 데이터 자리(`data/modules/<id>/`) — 처음 읽을 때 만든다. git·이미지 밖이다."""
        path = _module_registry.data_root() / self.id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def callback(self, fn: Callable[..., object]) -> Callable[..., None]:
        """위젯 콜백(`on_change`·`on_click`·`on_submit`·`on_select`·`on_dismiss`)에 넘길 감싼 함수.

        `Exception`·`SystemExit`(그 밖의 `BaseException` 도)을 잡아 기록하고(자리 "callback") 세션
        표지를 남긴다 — 같은 회차의 화면 감싸기가 그 화면 맨 위에 카드를 그린다. Streamlit 제어
        예외(`st.stop`·`st.rerun`)와 `KeyboardInterrupt` 는 다시 던진다.
        """

        @functools.wraps(fn)
        def wrapped(*args: object, **kwargs: object) -> None:
            try:
                fn(*args, **kwargs)
            except (ScriptControlException, KeyboardInterrupt):
                raise
            # SystemExit·CancelledError 도 잡는다 — 두면 회차 스레드가 끝나 세션이 멈춘다.
            except BaseException as error:
                self._note_callback_failure(error)

        return wrapped

    def guard(self) -> AbstractContextManager[None]:
        """`with ctx.guard():` — 프래그먼트·팝업 본문용. 안의 오류를 그 자리 카드로 바꾼다.

        Streamlit 제어 예외와 `FragmentHandledException`(안쪽 프래그먼트가 이미 그린 오류)은 그대로
        지나간다.
        """
        return _guarded(self)

    def _note_callback_failure(self, error: BaseException) -> None:
        _module_failures.record_failure(
            self.id, page="", kind=type(error).__name__, where="callback"
        )
        _LOGGER.error("모듈 %s 콜백 실패", self.id, exc_info=error)
        parts = _failure_parts(error, module_id=self.id, folder=self.folder)
        with contextlib.suppress(Exception):  # 실행 문맥 밖(단위 시험)에서는 표지를 남기지 않는다
            st.session_state[_module_failures.callback_failure_key(self.id)] = {
                "kind": parts.kind,
                "message": parts.message,
                "frames": list(parts.frames),
                "hint": parts.hint,
            }


@contextlib.contextmanager
def _guarded(ctx: ModuleContext) -> Iterator[None]:
    try:
        yield
    except (FragmentHandledException, ScriptControlException, KeyboardInterrupt):
        raise
    # SystemExit·CancelledError 도 잡는다 — 두면 회차 스레드가 끝나 세션이 멈춘다.
    except BaseException as error:
        _module_failures.record_failure(ctx.id, page="", kind=type(error).__name__, where="guard")
        _LOGGER.error("모듈 %s guard 안 실패", ctx.id, exc_info=error)
        _render_module_failure_card(
            module_id=ctx.id,
            module_name=ctx.name,
            owner=ctx.owner,
            folder=ctx.folder,
            page_title=None,
            exc=error,
            where="guard",
        )


def context(file: str | os.PathLike[str]) -> ModuleContext:
    """보통 `api.context(__file__)`. 파일 위의 `module.json` 을 찾아 문맥을 만든다.

    못 찾았거나 선언이 틀렸으면 `ModuleContextError`. 꺼짐·실패 상태는 보지 않는다 — 앱은 그런
    모듈의 화면을 등록하지 않고, 모듈 시험(`AppTest.from_file`)은 상태와 상관없이 돈다.
    """
    try:
        folder = _module_registry.module_folder_for(file)
        manifest = _module_registry.cached_manifest(folder)
    except _module_registry.ManifestError as error:
        raise ModuleContextError(error.reason) from error
    return ModuleContext(
        id=manifest.id,
        name=manifest.name,
        owner=manifest.owner,
        maturity=manifest.maturity,
        folder=folder,
        api_version=API_VERSION,
    )


def page_header(ctx: ModuleContext, title: str, *, description: str | None = None) -> None:
    """화면 맨 위 머리말 한 번. L0·L1 은 「(구현중)」 배지를 단다. 세션 키를 만들지 않는다.

    `description` 은 받기만 하고 그리지 않는다(창구 1.1 — 화면 머리에 소개 줄을 두지 않는다, 설계
    규칙 UI-TXT-01). 넘기던 모듈이 깨지지 않게 인자는 남긴다. 모듈 소개는 `module.json` 의
    `description` 이 모듈 색인에서 맡는다.
    """
    del description
    implementing = ctx.maturity in _module_registry.IMPLEMENTING_LEVELS
    _render_page_header(f"{title} {IMPLEMENTING_SUFFIX}" if implementing else title)


def palette() -> Mapping[str, str]:
    """이번 회차 테마의 역할 색(`PALETTE_KEYS` → 색). 캐시 함수에는 이 값을 인자로 넘긴다."""
    return MappingProxyType({key: getattr(_tokens, name) for key, name in _PALETTE_TOKENS.items()})
