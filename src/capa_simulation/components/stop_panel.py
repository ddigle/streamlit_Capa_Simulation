# Purpose: 앱 안 멈춤 화면이 함께 쓰는 작은 판 조각 — 같은 탭 주 단추 링크 · 문의 캡션 · 참고 줄.

"""앱 안 멈춤 판(통합인증 멈춤 · 부트스트랩 실패).

앱이 서지 못하거나 멈춘 회차에는 사이드바 앱 정보 카드 · 알림 칸이 없다. 그래서 멈춘 자리에 같은
차례의 작은 판을 둔다 — 경고 한 줄(부르는 쪽) · 주 단추 하나 · 문의 캡션 · 참고 줄 · 접힌
진단(부르는 쪽). 문장을 늘리지 않는다(설계 규칙 UI-TXT-01) — 캡션은 값(문의 메일 · 사유 낱말 ·
시각)만 싣는다(UI-TXT-04).

**주 단추는 같은 탭 링크다.** 다시 로그인 · 새로고침은 새 문서를 열어 새 Streamlit 세션을 만들어야
한다(`st.rerun` 은 같은 세션이라 앞 계정의 세션 상태가 남는다). `st.link_button` 은 늘 새 탭이라
원문 HTML 링크(`target="_self"`)에 앱 주 단추와 같은 색(강조색 면 · 그 위 글자색 — 그 회차 테마
토큰)을 입힌다. 멈춤은 `app.py` 가 강조 단추 서식을 보내기 전이라 서식을 링크에 직접 싣는다.
풍선(`title`)은 누르기 전에 알아야 하는 되돌릴 수 없는 결과에만 단다(UI-NTF-09).
"""

from __future__ import annotations

import html
import time
from datetime import datetime, timezone

import streamlit as st

from capa_simulation.design import tokens
from capa_simulation.settings import app_contact_email

CONTACT_PREFIX = "문의"
REFERENCE_PREFIX = "참고"


def primary_link_style() -> str:
    """같은 탭 주 단추 링크의 서식 — 그 회차 테마의 강조색 면과 그 위 글자색."""
    return (
        "display:inline-flex;align-items:center;min-height:2.5rem;padding:0.25rem 0.875rem;"
        f"border-radius:0.5rem;background:{tokens.ACCENT};color:{tokens.ACCENT_TEXT};"
        "text-decoration:none;font-weight:600;line-height:1.6;"
    )


def primary_link(url: str, label: str, *, title: str | None = None) -> str:
    """같은 탭에서 여는 주 단추 꼴 링크(원문 HTML). `label` 은 앱이 지은 글이다."""
    tip = "" if title is None else f' title="{html.escape(title, quote=True)}"'
    return (
        f'<a href="{html.escape(url, quote=True)}" target="_self" role="button"{tip} '
        f'style="{primary_link_style()}">{html.escape(label, quote=False)}</a>'
    )


def contact_caption() -> str | None:
    """「문의 <메일>」 — 문의 메일 환경변수가 비면 `None`(줄을 그리지 않는다)."""
    email = app_contact_email()
    return f"{CONTACT_PREFIX} {email}" if email else None


def render_contact_caption() -> None:
    """문의 캡션 한 줄. 문의 메일이 없으면 아무것도 그리지 않는다."""
    line = contact_caption()
    if line is not None:
        st.caption(line)


def reference_line(code: str, *, now: float | None = None) -> str:
    """「참고 <사유 낱말> · <YYYY-MM-DD HH:MM> UTC」 — 관리자가 시각으로 짝을 맞춘다."""
    moment = datetime.fromtimestamp(time.time() if now is None else now, tz=timezone.utc)
    return f"{REFERENCE_PREFIX} {code} · {moment.strftime('%Y-%m-%d %H:%M')} UTC"
