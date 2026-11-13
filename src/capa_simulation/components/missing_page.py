# Purpose: 없는 화면 주소로 들어온 회차를 가려 한 번 알린다(꺼진 · 실패한 모듈이면 그 모듈 · 담당).

"""없는 화면 주소(2026-11-14 「앱 대신 뜨는 화면」 보드 카드 p2-rare — 없는 주소 알림).

등록되지 않은 경로(꺼진 · 실패한 모듈 화면, 이름을 바꾼 옛 화면 주소, 북마크 · 남이 보낸 링크)로
들어오면 Streamlit 이 영어 팝업 「Page not found」 를 띄우고 HOME 을 돈다. 그 회차를 가려 알림창
· Alarm 에 한 번 알린다 — 「없는 화면 주소 — HOME 을 열었습니다」, 꺼진 · 실패한 모듈 화면이면
「「<모듈>」 은 꺼져 있습니다 · 담당 <이름>」. 영어 팝업을 감추는 것은 비공식 길이라(입장 화면의 Esc
닫기와 같은 길) 하지 않는다 — 브라우저로 확인한 뒤의 일이다.

- 판정은 Streamlit 페이지 관리자가 이 회차에 받은 주소 이름(`intended_page_name` — 주소창 · 링크로
  연 화면)과 `st.navigation()` 이 고른 화면 주소를 맞대는 것이다. 화면 해시로 옮기는
  길(`st.switch_page` · 페이지 링크)은 늘 등록된 화면이라 여기 오지 않는다.
- 같은 주소는 이 세션에 한 번만 알린다(`SEEN_KEY`) — 주소 이름이 다음 회차에 남아도 거듭 뜨지
않는다.
- 알림 코드는 지금 등록부의 「동작 결과 — 안내」(`FL-02`)다 — 이 알림만의 번호는 정하지 않았다.
"""

from __future__ import annotations

from typing import Final

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from capa_simulation import alerts, module_registry

MISSING_CODE: Final = "FL-02"
MISSING_CAUSE: Final = "없는 화면 주소로 들어옴"
# 이 세션에 알린 주소 — 같은 주소는 한 번만.
SEEN_KEY: Final = "missing_page_seen_v1"
UNKNOWN_TEXT: Final = "없는 화면 주소 — HOME 을 열었습니다"
_MODULE_PREFIX: Final = "mod-"


def requested_path() -> str:
    """이 회차에 주소창 · 링크로 요청한 화면 주소 이름(없으면 빈 글자). 시험이 바꿔 끼운다."""
    ctx = get_script_run_ctx()
    if ctx is None:
        return ""
    name = getattr(ctx.pages_manager, "intended_page_name", None)
    return name if isinstance(name, str) else ""


def _module_of(path: str) -> module_registry.ModuleRecord | None:
    """`mod-<id>-<slug>` 주소의 모듈 기록(꺼짐 · 실패 포함). 모르면 None."""
    if not path.startswith(_MODULE_PREFIX):
        return None
    for record in module_registry.discovered().records:
        manifest = record.manifest
        if manifest is not None and path.startswith(f"{_MODULE_PREFIX}{manifest.id}-"):
            return record
    return None


def missing_text(path: str) -> tuple[str, str]:
    """(짧은 글, 전문). 꺼진 · 실패한 모듈 화면이면 그 모듈 이름 · 담당을 싣는다."""
    record = _module_of(path)
    manifest = None if record is None else record.manifest
    if record is not None and manifest is not None and record.state != "on":
        owner = f" · 담당 {manifest.owner}" if manifest.owner else ""
        short = f"「{manifest.name}」 은 꺼져 있습니다{owner}"
        return short, f"{short} — 연 주소 /{path} 대신 HOME 을 열었습니다."
    return UNKNOWN_TEXT, f"없는 화면 주소(/{path})로 들어와 HOME 을 열었습니다."


def notice_missing_page(landed: str) -> None:
    """요청한 주소가 등록된 화면이 아니어서 다른 화면(`landed` — HOME)을 돌면 사건 알림 하나를
    담는다(그리지 않는다 — 알림 칸이 보낸다). `app.py` 가 이번 화면을 적은 뒤 · 알림 칸 앞에서
    부른다."""
    path = requested_path().strip("/")
    if not path or path == landed:
        return
    seen = st.session_state.get(SEEN_KEY)
    seen_paths = seen if isinstance(seen, list) else []
    if path in seen_paths:
        return
    st.session_state[SEEN_KEY] = [*seen_paths, path][-20:]
    short, full = missing_text(path)
    alerts.event(MISSING_CODE, text=short, full=full, cause=MISSING_CAUSE)
