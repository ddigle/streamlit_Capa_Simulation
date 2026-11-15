# Purpose: 앱 안 멈춤 판 셋의 한 꼴 — 주 단추 링크 · 문의 줄 · 참고 줄 · 접힌 관리자용 진단.

"""앱 안 멈춤 판(앱 시작 실패 `boot_stop` · 접속 멈춤 `sso_identity` · 한 화면 오류
`page_failure_card`).

앱이 서지 못하거나 멈춘 자리에는 같은 차례의 판 하나를 둔다 — **경고 띠 → 주 단추 하나 → 문의 줄 →
참고 줄 → 접힌 「관리자용 진단」**(2026-11-14 보드 stop-panels 「한 꼴로 맞춘다」). 경고 띠와 주
단추는 부르는 쪽이 그리고(판마다 글 · 아이콘 · 단추가 다르다 — 다시 해도 같은 판은 주 단추가 없다),
문의 줄 · 참고 줄 · 접힌 진단은 이 모듈의 `render_stop_footer` 가 같은 차례로 그린다. 문장을 늘리지
않는다(설계 규칙 UI-TXT-01) — 캡션은 값(문의 메일 · 창구 글 · 사유 낱말 · 시각 · 오류 종류)만
싣는다(UI-TXT-04).

- **문의 줄** — 앱 밖 화면의 문의 줄과 같은 차례다. 메일, 그 뒤에 창구 글(`CAPA_ACCESS_CONTACT` —
  로그인 · 접속 멈춤만 넘긴다), 둘 다 비면 줄이 없다. 메일은 그 회차 테마의 강조색(`ACCENT`)
  링크다 — 사이드바 앱 정보 카드 · 앱 밖 화면의 문의처와 같은 색(UI-ACC-01 · UI-CON-04). 줄은
  원문 HTML 문단 하나로 그린다(`contact_markup`).
- **참고 줄** — 「참고 <사유 낱말> · <YYYY-MM-DD HH:MM> UTC」(+ 「 · <오류 종류>」). 사유 낱말은
  판의 갈래 키(앱 시작 실패 `db_locked` · 접속 멈춤 `sso_expired` 등)이고, 한 화면 오류는 그 자리에
  참고 번호(8자 — 관리자 알림 `AD-22` · 서버 로그가 같은 번호를 싣는다)를 둔다. 새 번호 체계가
  아니다. 시작 임시 화면(`scripts/container_stage.py`)이 문의 줄 · 참고 줄을 같은 글자 꼴로 따로
  짓는다(시험이 맞댄다 — 그쪽은 앱 밖 공통 틀이라 창구 글을 늘 싣는다).
- **접힌 「관리자용 진단」** — 서버 경로 · 프로세스 번호 · 원문 · 실행 명령은 여기에만 둔다(복사
  단추 — UI-NTF-10). 관리자 몫(`admin_view.admin_notes_visible` 한 판정)에만 선다 — 접어도 누구나
  펼치므로 접힘으로 가리지 않는다. 판이 마지막 자리라 판정이 무엇을 내도 닫힌 쪽(진단 없음)으로
  물러선다. 복사 글 · 펼친 글 맨 위는 참고 줄이다.

**주 단추가 링크인 판(접속 멈춤)은 같은 탭 링크다.** 다시 로그인 · 새로고침은 새 문서를 열어 새
Streamlit 세션을 만들어야 한다(`st.rerun` 은 같은 세션이라 앞 계정의 세션 상태가 남는다).
`st.link_button` 은 늘 새 탭이라 원문 HTML 링크(`target="_self"`)에 앱 주 단추와 같은 색(강조색 면 ·
그 위 글자색 — 그 회차 테마 토큰)을 입힌다. 멈춤은 `app.py` 가 강조 단추 서식을 보내기 전이라 서식을
링크에 직접 싣는다. 역할은 링크 그대로다(`role="button"` 을 달면 낭독기는 단추로 읽는데 Space 로
열리지 않는다 — Enter 로 연다). 회차 하나로 풀리는 판(앱 시작 실패 · 한 화면 오류)은 주 단추가
`st.button` 「다시 시도」(`RETRY_LABEL`)다. 풍선(`title`)은 누르기 전에 알아야 하는 되돌릴 수 없는
결과에만 단다(UI-NTF-09).

진단 복사 부품(`diagnostic_copy`)과 관리자 몫 판정(`admin_view`)은 함수 안에서 불러온다 — 이 모듈은
`sso_identity` 가 맨 위에서 부르고(그것을 진입 파일이 실행기 전에 부를 수 있다 — Components v2 는
import 때 등록된다), `admin_view` 는 `sso_identity` 를 부른다(순환).
"""

from __future__ import annotations

import html
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

import streamlit as st

from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.design import tokens
from capa_simulation.settings import app_contact_email

CONTACT_PREFIX = "문의"
REFERENCE_PREFIX = "참고"
# 회차 하나로 풀리는 판(앱 시작 실패 · 한 화면 오류)의 주 단추.
RETRY_LABEL: Final = "다시 시도"
# 판 아래 문의 · 참고 줄을 감싸는 칸 — 그 칸의 캡션 흐림을 걷는다(`footer_style`).
STOP_FOOTER_KEY: Final = "capa_stop_footer"


@dataclass(frozen=True)
class AdminFold:
    """접힌 「관리자용 진단」 한 칸 — 복사 글 머리(`title`) · 펼침 key · 복사 단추 key 와 글.

    `blocks` 는 평문 칸(빈 줄로 나눈다)이고 펼친 글 · 복사 글이 같다. `notes` 는 마크다운 줄(실행
    명령 · 환경변수 이름을 코드 꼴로) — 있으면 펼친 글은 이 줄들의 캡션이고 복사 글은 그 평문이다.
    둘 다 맨 위에 참고 줄이 붙는다(`render_stop_footer`)."""

    title: str
    key: str
    copy_key: str
    blocks: tuple[tuple[str, ...], ...] = ()
    notes: tuple[str, ...] = ()


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
        f'<a href="{html.escape(url, quote=True)}" target="_self"{tip} '
        f'style="{primary_link_style()}">{html.escape(label, quote=False)}</a>'
    )


def _contact_parts(access_contact: str) -> tuple[str, str]:
    """문의 줄의 두 칸 — 메일과 창구 글. 창구 글은 공백(줄바꿈 포함)을 하나로 접는다(한 줄
    값이다)."""
    return app_contact_email(), " ".join(access_contact.split())


def contact_caption(access_contact: str = "") -> str | None:
    """「문의 <메일> · <창구 글>」 평문 — 보이는 글자 그대로다(시작 임시 화면의 문의 줄과 시험이
    맞댄다). 둘 다 비면 `None`(줄을 그리지 않는다)."""
    parts = [part for part in _contact_parts(access_contact) if part]
    return f"{CONTACT_PREFIX} {' · '.join(parts)}" if parts else None


def contact_link_style() -> str:
    """문의 메일 링크 서식 — 그 회차 테마의 강조색 + 밑줄. 강조색과 둘레 글(`TEXT_MUTED`)의 밝기
    대비가 1.01(밝게) · 1.48(어둡게)이라 색만으로는 링크가 갈리지 않는다(UI-ACC-03 — 앱 밖 틀 ·
    사이드바 앱 정보 카드의 문의 링크와 같은 꼴)."""
    return f"color:{tokens.ACCENT};text-decoration:underline"


def contact_markup(access_contact: str = "") -> str | None:
    """문의 줄의 원문 HTML — 문단 하나(`<p>…</p>`)이고 메일은 그 회차 테마의 강조색 링크다. 둘 다
    비면 `None`.

    마크다운 줄 안에 `<a>` 를 끼우면 GFM 자동 링크가 안의 메일 글을 한 번 더 링크로 감싸, 색을 든
    링크는 비고 기본색 링크만 보인다. 문단 하나로 시작하는 원문 HTML 은 마크다운이 풀지 않으므로
    창구 글(운영자가 적은 글)은 HTML 로 막는다 — 빈 줄은 문단을 끊으므로 `_contact_parts` 가 공백을
    접는다. 색은 그릴 때마다 읽는다(멈춤은 `app.py` 가 앱 서식을 보내기 전이라 링크에 직접
    싣는다)."""
    email, text = _contact_parts(access_contact)
    parts: list[str] = []
    if email:
        parts.append(
            f'<a href="mailto:{html.escape(email, quote=True)}" '
            f'style="{contact_link_style()}">{html.escape(email, quote=False)}</a>'
        )
    if text:
        parts.append(html.escape(text, quote=False))
    return f"<p>{CONTACT_PREFIX} {' · '.join(parts)}</p>" if parts else None


def render_contact_caption(access_contact: str = "") -> None:
    """문의 캡션 한 줄(`contact_markup`) — `access_contact` 는 접속 요청 창구 글(로그인 · 접속
    멈춤만 넘긴다). 둘 다 비면 아무것도 그리지 않는다."""
    line = contact_markup(access_contact)
    if line is not None:
        st.caption(line, unsafe_allow_html=True)


def footer_style() -> str:
    """판 아래 캡션(문의 · 참고 줄)의 흐림을 걷고 `TEXT_MUTED` 글자로 — 사이드바 앱 정보 카드와 같은
    꼴. Streamlit 은 캡션 칸에 흐림 0.6 을 걸어, 그대로면 강조색 메일 링크가 밝게에서 2.5:1 로
    흐려진다. 멈춤은 `app.py` 가 앱 서식을 보내기 전이라 판이 스스로 싣는다(스타일만 든 `st.html` 은
    자리를 먹지 않는다)."""
    box = f'.st-key-{STOP_FOOTER_KEY} [data-testid="stCaptionContainer"]'
    return f"<style>{box} {{ opacity: 1; }} {box} p {{ color: {tokens.TEXT_MUTED}; }}</style>"


def reference_line(code: str, *, now: float | None = None) -> str:
    """「참고 <사유 낱말> · <YYYY-MM-DD HH:MM> UTC」 — 관리자가 시각으로 짝을 맞춘다."""
    moment = datetime.fromtimestamp(time.time() if now is None else now, tz=timezone.utc)
    return f"{REFERENCE_PREFIX} {code} · {moment.strftime('%Y-%m-%d %H:%M')} UTC"


def admin_fold_visible() -> bool:
    """접힌 「관리자용 진단」 을 세우나 — 관리자 몫(`admin_view.admin_notes_visible`)일 때만. 판이
    마지막 자리라 판정이 무엇을 내도 닫힌 쪽으로 물러선다."""
    try:
        from capa_simulation.components import admin_view

        return admin_view.admin_notes_visible()
    except Exception:
        return False


def _render_fold(fold: AdminFold, reference: str) -> None:
    from capa_simulation.components.diagnostic_copy import (
        ADMIN_DIAGNOSTIC_LABEL,
        diagnostic_text,
        plain_lines,
        render_diagnostic_copy,
    )

    body = [list(block) for block in fold.blocks]
    if not body and fold.notes:
        body = [plain_lines(fold.notes)]
    blocks = [[reference], *body]
    with st.expander(ADMIN_DIAGNOSTIC_LABEL, key=fold.key):
        render_diagnostic_copy(diagnostic_text(fold.title, *blocks), key=fold.copy_key)
        if fold.notes:
            for line in fold.notes:
                st.caption(line)
        else:
            # 진단 글은 글자 그대로(평문 칸) — 조치 문장 · 파일 경로 · 원문을 자리 글로 늘어놓지
            # 않는다.
            text = "\n\n".join("\n".join(block) for block in blocks)
            st.code(text, language=None, wrap_lines=True)


def render_stop_footer(
    code: str,
    *,
    kind: str | None = None,
    access_contact: str = "",
    fold: AdminFold | None = None,
    now: float | None = None,
) -> str:
    """판의 경고 띠 · 주 단추 아래 — 문의 줄 → 참고 줄 → (관리자 몫이면) 접힌 진단. 참고 줄 평문을
    돌려준다. 오류 종류 이름(있으면 「 · <종류>」 — 누구에게나 보이는 값, 보드 d12 (가))은 마크다운
    글자 그대로 막아 캡션에 싣는다."""
    head = reference_line(code, now=now)
    with st.container(key=STOP_FOOTER_KEY):
        st.html(footer_style())
        render_contact_caption(access_contact)
        st.caption(head if kind is None else f"{head} · {literal_markdown(kind)}")
    reference = head if kind is None else f"{head} · {kind}"
    if fold is not None and admin_fold_visible():
        _render_fold(fold, reference)
    return reference
