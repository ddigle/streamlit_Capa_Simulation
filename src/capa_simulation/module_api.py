# Purpose: 모듈이 import 하는 유일한 코어 창구 v1 — 문맥·키·머리말·색과 조회·S3 도우미를 낸다.

"""모듈 공개 창구 v1(모델 2 — 2026-11-01 사용자 결정).

모듈(`modules/<id>/`)은 코어에서 **이 모듈 하나만** import 한다. 겉면은 `__all__` 이 전부이고
`tests/test_module_api_surface.py` 가 이름·서명·칸을 고정한다. 바꾸는 법(AGENTS 12장 「코어 공개
창구 변경」): 같은 큰 판 안에서는 더하기만 하고 작은 판(`API_MINOR`)을 올린다. 지우기·이름
바꾸기·서명 바꾸기·뜻 바꾸기는 큰 판을 올린다. 이름·서명을 그대로 두고 인자를 폐기 예정으로
받기만 하거나 화면에 그리는 것만 줄이는 변경은 작은 판이다 — 넘기던 모듈이 고치지 않아도 돈다
(창구 1.1 `description` · 1.2 「구현중」 배지 줄).

- 코어 데이터(시나리오·기준정보·조회기간·DB)는 내지 않는다 — v2(데이터 연계)의 몫이다.
- 바깥 자리는 도우미로만 닿는다(창구 1.3 — 2026-11-12 사용자 결정 「도우미 함수로」) —
  `query_bigdataquery`(앱과 같은 길의 BigDataQuery 조회)와 `s3_upload` · `s3_download`(모듈 데이터
  자리 파일 하나를 버킷의 `modules/<id>/` 아래로). 요청자 계정 · 토큰 · S3 키는 코어가 쥐고 모듈은
  읽지 않는다(M21). 언제 올리고 받을지는 모듈이 정한다. 속은 `module_helpers` 다.
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
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Final

import pandas as pd
import streamlit as st
from streamlit.errors import FragmentHandledException
from streamlit.runtime.scriptrunner_utils.exceptions import ScriptControlException

# 코어 이름은 모두 `_` 별명으로 들인다 — 모듈이 `api.<이름>` 으로 닿는 공개 이름은 `__all__`
# 뿐이어야 한다(`api.module_registry.settings` 같은 길로 코어 설정·DB 자리에 닿지 않게). 겉면
# 시험이 지킨다.
from capa_simulation import module_failures as _module_failures
from capa_simulation import module_helpers as _module_helpers
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
    "S3_MAX_BYTES",
    "BigDataQueryError",
    "ModuleContext",
    "ModuleContextError",
    "S3Result",
    "context",
    "page_header",
    "palette",
    "query_bigdataquery",
    "s3_download",
    "s3_upload",
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
# S3 올리기 · 받기 한 번에 옮기는 파일 하나의 상한(바이트).
S3_MAX_BYTES: Final[int] = _module_helpers.S3_MAX_BYTES
# 도우미의 실패 · 결과 꼴. 정의는 속(`module_helpers`)에 있고 이름은 여기서 낸다.
BigDataQueryError = _module_helpers.BigDataQueryError
S3Result = _module_helpers.S3Result
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
    """화면 맨 위 머리말 한 번(제목 — 화면에서는 숨고 인쇄 · 읽기 도구에 남는다). 세션 키를 만들지
    않는다.

    성숙도 `L0` · `L1` 의 「구현중」 은 본문 배지 줄로 그리지 않는다(창구 1.2 — 2026-11-10 보드 Q-5,
    코어 구현 중 화면과 같은 꼴). 사이드바 라벨 「(구현중)」 과 화면 탭 이름 곁 「구현중」 표지가
    말한다. `description` 은 받기만 하고 그리지 않는다(창구 1.1 — 화면 머리에 소개 줄을 두지 않는다,
    설계 규칙 UI-TXT-01). 넘기던 모듈이 깨지지 않게 서명은 그대로다. 모듈 소개는 `module.json` 의
    `description` 이 모듈 색인에서 맡는다.
    """
    del ctx, description
    _render_page_header(title, show_status=False)


def palette() -> Mapping[str, str]:
    """이번 회차 테마의 역할 색(`PALETTE_KEYS` → 색). 캐시 함수에는 이 값을 인자로 넘긴다."""
    return MappingProxyType({key: getattr(_tokens, name) for key, name in _PALETTE_TOKENS.items()})


def query_bigdataquery(
    ctx: ModuleContext, sql: str, *, start: date | None = None, end: date | None = None
) -> pd.DataFrame:
    """BigDataQuery 조회 한 번 — 앱의 DB 등록과 같은 길 · 같은 실패 갈래로 묻고 표를 돌려준다.

    요청자 계정 · 토큰은 코어가 쥔다(모듈은 읽지 않는다 — M21). `start` · `end` 를 함께 주면
    조회문의 `{start_date}` 에 시작 날, `{end_date}` 에 끝 날 다음 날을 앱과 같은 꼴로 채운다 —
    조회문은 `>= '{start_date}' AND < '{end_date}'` 로 써야 끝 날까지 꼭 맞다. 최대 366일.
    실패는 `BigDataQueryError`(`kind` — 「입력」 · 「쓸 수 없음」 · 앱의 갈래)이고 글은 앱 화면과
    같은 안내다. 결과는 캐시하지 않는다 — 캐시는 모듈의 `cache.py` 에 둔다. 모듈
    시험(`check_module.py`)에서는 늘 「쓸 수 없음」 이다.
    """
    return _module_helpers.query_bigdataquery(ctx.id, sql, start=start, end=end)


def s3_upload(ctx: ModuleContext, name: str) -> S3Result:
    """`ctx.data_dir / name` 파일 하나를 버킷의 `modules/<id>/<name>` 으로 올린다(있으면 덮는다).

    `name` 은 `ctx.data_dir` 안의 상대 이름이다(`/` 로 나눈 마디 넷까지, 마디는 영문 · 숫자 ·
    `.` · `_` · `-`). 예외를 던지지 않고 늘 `S3Result` 를 돌려준다 — 운영 서버(동기화 모드
    `managed` · 키 · 주소 · 버킷이 있음)가 아니면 「쓸 수 없음」 이다. 파일 하나는 `S3_MAX_BYTES`
    까지.
    """
    if not _module_registry.is_valid_module_id(ctx.id):
        return S3Result(ok=False, reason=_module_helpers.S3_NAME_REJECTED)
    return _module_helpers.s3_upload(ctx.id, ctx.data_dir, name)


def s3_download(ctx: ModuleContext, name: str) -> S3Result:
    """버킷의 `modules/<id>/<name>` 을 받아 `ctx.data_dir / name` 에 둔다(있으면 바꾼다).

    다 받은 뒤 한 번에 바꾼다 — 받다 끊겨도 있던 파일은 그대로다. 버킷에 없으면 「파일 없음」 이고
    로컬 파일은 건드리지 않는다. 그 밖은 `s3_upload` 와 같다.
    """
    if not _module_registry.is_valid_module_id(ctx.id):
        return S3Result(ok=False, reason=_module_helpers.S3_NAME_REJECTED)
    return _module_helpers.s3_download(ctx.id, ctx.data_dir, name)
