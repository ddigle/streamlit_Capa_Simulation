# Purpose: 모듈 오류 카드(이름·형식·첫 줄·끄는 법·import 안내·모듈 안 프레임)를 그린다.

"""모듈 오류 카드.

화면 본문 감싸기(`module_runtime.render_failure`)·콜백 표지(`module_runtime` 이 다음 회차 맨 위에)·
프래그먼트 감싸기(`module_api` 의 `ctx.guard`)가 함께 쓴다. 그 화면(또는 그 자리)만 멈추고 사이드바·
머리 띠·탭 줄·다른 화면은 그대로다.

- Streamlit 기본 traceback 전문(서버 경로가 나간다)을 그리지 않는다. 프레임은 **모듈 폴더 안**의
  것만 `<id>/<상대 경로>:<줄> in <함수>` 꼴로 싣는다.
- 예외 글은 첫 줄 200자만, 마크다운으로 해석되지 않게(`literal_markdown`) 싣는다.
- 위젯 key 를 쓰지 않는다(한 화면에 카드가 여럿 서도 겹치지 않는다).
"""

from __future__ import annotations

import os
import traceback
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from capa_simulation.components.literal_markdown import literal_markdown, quoted
from capa_simulation.module_registry import API_MAJOR, API_MINOR, DISABLED_ENV_VAR

MESSAGE_LIMIT = 200
FRAME_LIMIT = 12
CARD_ICON = ":material/extension_off:"
GUIDE_DOCUMENT = "docs/module_guide.md"
API_MODULE = "capa_simulation.module_api"


@dataclass(frozen=True)
class FailureParts:
    """카드에 싣는 것 — 콜백 표지(세션 칸)에도 이 꼴로 남긴다."""

    kind: str
    message: str
    frames: tuple[str, ...]
    hint: str


def first_line(exc: BaseException) -> str:
    """예외 글의 첫 줄(200자까지). 비면 빈 글자."""
    text = str(exc).strip()
    return text.splitlines()[0][:MESSAGE_LIMIT] if text else ""


def _local_names(folder: Path) -> frozenset[str]:
    """모듈 폴더 안 `.py`(확장자 뗀 것)·폴더 이름 — 같은 폴더 맨이름 import 를 가른다."""
    try:
        entries = os.listdir(folder)
    except OSError:
        return frozenset()
    names = {Path(entry).stem for entry in entries if entry.endswith(".py")}
    names.update(entry for entry in entries if (folder / entry).is_dir())
    return frozenset(names)


def import_hint(exc: BaseException, *, module_id: str, folder: Path) -> str:
    """import 실패면 셋 가운데 하나(첫 해당)의 안내 한 줄, 아니면 빈 글자."""
    if not isinstance(exc, ImportError):
        return ""
    name = exc.name or ""
    if name == API_MODULE or name.startswith(f"{API_MODULE}."):
        return (
            f"이 모듈이 쓰는 코어 창구 이름이 이 코어(API {API_MAJOR}.{API_MINOR})에 없습니다 — "
            f"module.json 의 api·api_minor 와 `{GUIDE_DOCUMENT}` 부록 C 를 봅니다."
        )
    if not isinstance(exc, ModuleNotFoundError) or not name:
        return ""
    head = name.split(".", 1)[0]
    if head == "modules" or head in _local_names(folder):
        helper = head if head != "modules" else "<이름>"
        return (
            f"같은 모듈의 파일은 이렇게 부릅니다 — `from modules.{module_id} import {helper}`"
            f"(`{GUIDE_DOCUMENT}` 3장)."
        )
    return (
        f"이 서버에 없는 패키지입니다: `{head}` — 담당자가 앱 관리자에게 알리면 앱 관리자가 "
        f"「사외 요청」 으로 코어 의존성에 넣습니다(`{GUIDE_DOCUMENT}` 6장)."
    )


def module_frames(exc: BaseException, *, module_id: str, folder: Path) -> tuple[str, ...]:
    """모듈 폴더 안 프레임만 `<id>/<상대 경로>:<줄> in <함수>` 꼴로(절대 경로·코어 프레임 없음)."""
    base = Path(os.path.realpath(folder))
    frames: list[str] = []

    def inside(filename: str) -> str | None:
        try:
            return Path(os.path.realpath(filename)).relative_to(base).as_posix()
        except ValueError:
            return None

    for frame in traceback.extract_tb(exc.__traceback__):
        relative = inside(frame.filename)
        if relative is not None:
            frames.append(f"{module_id}/{relative}:{frame.lineno} in {frame.name}")
    if isinstance(exc, SyntaxError) and exc.filename:
        relative = inside(exc.filename)
        if relative is not None:
            frames.append(f"{module_id}/{relative}:{exc.lineno} (문법 오류)")
    return tuple(frames[-FRAME_LIMIT:])


def failure_parts(exc: BaseException, *, module_id: str, folder: Path) -> FailureParts:
    return FailureParts(
        kind=type(exc).__name__,
        message=first_line(exc),
        frames=module_frames(exc, module_id=module_id, folder=folder),
        hint=import_hint(exc, module_id=module_id, folder=folder),
    )


def _headline(module_name: str, page_title: str | None, parts: FailureParts, where: str) -> str:
    detail = literal_markdown(parts.kind) + (
        f": {literal_markdown(parts.message)}" if parts.message else ""
    )
    if page_title is None:
        return f"{quoted(module_name)} 모듈에서 오류가 났습니다 — {detail}"
    if where == "callback":
        return (
            f"방금 한 동작에서 오류가 났습니다 — {quoted(module_name)} 모듈의 {quoted(page_title)} "
            f"화면 · {detail}"
        )
    return f"{quoted(module_name)} 모듈의 {quoted(page_title)} 화면에서 오류가 났습니다 — {detail}"


def render_failure_parts(
    *,
    module_id: str,
    module_name: str,
    owner: str,
    page_title: str | None,
    parts: FailureParts,
    where: str,
) -> None:
    """카드를 지금 자리에 그린다. `page_title` 이 None 이면(guard) 그 자리만 멈춘 꼴로 쓴다."""
    st.error(_headline(module_name, page_title, parts, where), icon=CARD_ICON)
    stopped = (
        "이 자리만 멈췄습니다 — 화면의 나머지와 다른 화면은 그대로 씁니다."
        if page_title is None
        else "이 화면만 멈췄습니다 — 다른 화면은 그대로 씁니다."
    )
    owner_text = f" 담당 {literal_markdown(owner)}." if owner else ""
    st.caption(
        f"{stopped}{owner_text} 끄려면 `module.json` 의 `enabled` 를 false 로 하거나 실행 "
        f"환경변수(`{DISABLED_ENV_VAR}={module_id}`)를 넣고 앱을 다시 띄웁니다."
    )
    if parts.hint:
        st.caption(parts.hint)
    if parts.frames:
        with st.expander("오류 위치"):
            st.code("\n".join(parts.frames), language=None)


def render_module_failure_card(
    *,
    module_id: str,
    module_name: str,
    owner: str,
    folder: Path,
    page_title: str | None,
    exc: BaseException,
    where: str,
) -> None:
    """예외 하나의 카드를 지금 자리에 그린다(예외에서 뽑은 것을 `render_failure_parts` 로)."""
    render_failure_parts(
        module_id=module_id,
        module_name=module_name,
        owner=owner,
        page_title=page_title,
        parts=failure_parts(exc, module_id=module_id, folder=folder),
        where=where,
    )
