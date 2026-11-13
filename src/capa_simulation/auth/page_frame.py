# Purpose: 앱 밖 화면(접속 거절 · 등록 완료 · 확인 못 함 · 포털 거절)이 함께 쓰는 틀 — 순수 HTML.

"""앱 밖 화면의 공통 틀(「앱 대신 뜨는 화면」 보드 카드 frame — 2026-11-14 답 「좋음」).

위에서 아래 차례 하나로 그린다.

1. 머리 — 맨 위 강조색 줄 + 앱 마크 + 「S.PKG CAPA」 / 작은 글 「AX Management」(앱 머리
   띠와 같은 두 줄).
2. 상태 표지 — 낱말 + 색(색만으로 뜻을 싣지 않는다 — UI-ACC-03). 낱말은 `CHIP_WORDS` 다섯뿐.
3. 제목 한 문장(마침표 없음) → 까닭 1~2문장 → 다음에 할 일(번호, 넷까지 — 보드 D8 답).
4. 주 단추 하나(링크 또는 폼) + 보조 링크. 막다른 화면을 두지 않는다 — 주 단추는 늘 있다.
5. (있으면) 미리 채운 글 상자 — 한 번 눌러 통째로 고른다(`user-select: all`, 스크립트 없음).
6. 문의 줄 — 문의 메일(`settings.app_contact_email`)은 메일 링크, 창구 글
   (`CAPA_ACCESS_CONTACT`)은 그 뒤에. 둘 다 비면 그리지 않는다(UI-TXT-08).
7. 바닥 「참고 <사유 코드> · <시각> UTC」(한 번 눌러 고름) — 새 번호 체계 없이 지금 사유
   코드를 쓴다.
8. 접힌 「관리자용 진단」 — 접어도 누구나 펼친다(값 · 토큰 · 주소를 싣지 않는다).

스크립트가 없다(CSP `default-src 'none'`) — 마크는 인라인 SVG, 서식은 인라인 `<style>` 이다.
밝은 · 어두운 팔레트(`design/tokens`)를 함께 싣고 `prefers-color-scheme` 로 고른다
(UI-ACC-01). 좁은 창은 양옆 16px(UI-ACC-02). 표준 라이브러리와 토큰 팔레트만 쓴다 —
Streamlit 을 import 하지 않는다(문지기는 이벤트 루프에서 돈다). 넘겨받은 글은 모두 이 모듈이
`html.escape` 한다 — 부르는 쪽은 평문을 넘긴다.
"""

from __future__ import annotations

import functools
import html
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Final

from capa_simulation import settings

# 상태 표지 — 낱말과 색 역할(토큰 이름). 로그아웃 화면은 표지가 없다.
CHIP_WORDS: Final = {
    "denied": "권한 없음",
    "registered": "등록 완료",
    "retry": "다시 시도",
    "maintenance": "점검 중",
    "starting": "시작 중",
}
_CHIP_ROLES: Final = {
    "denied": "ALERT_ERROR",
    "registered": "ACCENT",
    "retry": "ALERT_CHECK",
    "maintenance": "ALERT_CHECK",
    "starting": "ALERT_ACTION",
}
DIAGNOSTIC_LABEL: Final = "관리자용 진단"
CONTACT_LABEL: Final = "문의"
# 본문 글의 `{account}` 자리 — 거절 표가 있는 그 브라우저에만 본인 계정이 선다(보드 D2 답).
ACCOUNT_SLOT: Final = "{account}"
# 마크 모양 — `components/intro_overlay.MARK_RING_PATH` · `MARK_DIE_ORIGINS` 와 같다(시험이 맞댄다).
MARK_RING_PATH: Final = "M83.59 26.48 A41 41 0 1 0 83.59 73.52"
MARK_DIE_ORIGINS: Final = (28, 44, 60)

_PALETTE_ROLES: Final = (
    ("fg", "TEXT"),
    ("muted", "TEXT_MUTED"),
    ("bg", "SURFACE_PAGE"),
    ("card", "SURFACE"),
    ("line", "BORDER"),
    ("accent", "ACCENT"),
    ("accent-text", "ACCENT_TEXT"),
    ("die-warm", "BRAND_DIE_WARM"),
    *((f"chip-{name}", role) for name, role in _CHIP_ROLES.items()),
)
_FRAME_CSS: Final = """
body { margin: 0; padding: 0 16px; background: var(--bg); color: var(--fg); line-height: 1.6;
  font-family: var(--font); }
.bar { height: 4px; background: var(--accent); margin: 0 -16px; }
main { max-width: 640px; margin: 32px auto; padding: 24px 28px; background: var(--card);
  border: 1px solid var(--line); border-radius: 12px; }
header { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
header svg { width: 32px; height: 32px; flex: none; }
.ring { stroke: var(--fg); } .die { fill: var(--accent); } .core { fill: var(--die-warm); }
.brand { display: flex; flex-direction: column; line-height: 1.2; }
.brand b { font-size: 1rem; } .brand span { font-size: .78rem; color: var(--muted); }
.chip { display: inline-block; padding: 1px 10px; border: 1px solid currentColor;
  border-radius: 999px; font-size: .82rem; font-weight: 600; margin-bottom: 8px; }
h1 { font-size: 1.3rem; margin: 0 0 10px; }
p { margin: 8px 0; }
ol { margin: 8px 0; padding-left: 1.4em; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; margin: 16px 0 8px; }
.actions form { margin: 0; }
.button { display: inline-block; padding: 8px 16px; border: 0; border-radius: 8px;
  background: var(--accent); color: var(--accent-text); font: inherit; text-decoration: none;
  cursor: pointer; }
a { color: var(--accent); }
.pick { user-select: all; -webkit-user-select: all; }
pre.pick { white-space: pre-wrap; word-break: break-all; margin: 6px 0 12px; padding: 10px 12px;
  border: 1px solid var(--line); border-radius: 8px; font-family: ui-monospace, Consolas, monospace;
  font-size: .9rem; }
.muted { color: var(--muted); font-size: .88rem; }
.ref { margin-top: 18px; }
details { margin-top: 6px; color: var(--muted); font-size: .88rem; }
details ul { margin: 6px 0; padding-left: 1.2em; }
strong.account { font-family: ui-monospace, Consolas, monospace; word-break: break-all; }
"""


@functools.cache
def palette_css() -> str:
    """밝은 · 어두운 팔레트 변수(+ 서체). tokens 는 여기서만 불러온다 — `auth` 꾸러미가 import 때
    Streamlit(테마 모듈이 딸려 온다)을 끌고 오지 않게. `palette_value` 는 실행 문맥을 보지
    않는다."""
    from capa_simulation.design import tokens

    def variables(mode: str) -> str:
        return " ".join(
            f"--{name}: {tokens.palette_value(mode, role)};" for name, role in _PALETTE_ROLES
        )

    font = f"--font: {tokens.FONT_FAMILY};"
    return (
        f":root {{ color-scheme: light dark; {variables('light')} {font} }}\n"
        f"@media (prefers-color-scheme: dark) {{ :root {{ {variables('dark')} }} }}"
    )


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _with_account(text: str, account: str) -> str:
    """평문 한 줄을 이스케이프하고 `{account}` 자리에만 굵은 본인 계정을 넣는다."""
    parts = text.split(ACCOUNT_SLOT)
    shown = f'<strong class="account">{_esc(account)}</strong>'
    return shown.join(_esc(part) for part in parts)


@dataclass(frozen=True)
class Link:
    """단추 · 보조 링크 하나. 주소는 부르는 쪽이 공개 주소 바탕으로 만든 것이다."""

    label: str
    href: str


@dataclass(frozen=True)
class Form:
    """주 단추가 폼(POST)일 때 — 숨은 칸은 표지 하나 같은 고정 값만 싣는다."""

    label: str
    action: str
    fields: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Frame:
    """화면 한 장의 내용 — 모두 평문이다(이 모듈이 이스케이프한다)."""

    title: str
    chip: str | None
    lead: tuple[str, ...]
    primary: Link | Form
    steps: tuple[str, ...] = ()
    secondary: tuple[Link, ...] = ()
    note_label: str = ""
    note_text: str = ""
    reference: str = ""
    diagnostics: tuple[str, ...] = ()
    account: str = field(default="", repr=False)
    contact_email: str = field(default="", repr=False)
    contact_text: str = field(default="", repr=False)


def mark_svg() -> str:
    """앱 마크(C 링 + 3×3 다이) — 색은 팔레트 변수라 두 테마를 따른다."""
    dies = "".join(
        f'<rect class="{"core" if (x, y) == (44, 44) else "die"}" x="{x}" y="{y}" '
        'width="12" height="12" rx="2"/>'
        for y in MARK_DIE_ORIGINS
        for x in MARK_DIE_ORIGINS
    )
    return (
        '<svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">'
        f'<path class="ring" d="{MARK_RING_PATH}" fill="none" stroke-width="9" '
        'stroke-linecap="round"/>'
        f"{dies}</svg>"
    )


def contact_line(email: str, text: str) -> str:
    """문의 줄 — 메일은 링크, 창구 글은 그 뒤 평문. 둘 다 비면 빈 글(그리지 않는다)."""
    parts: list[str] = []
    if email:
        parts.append(f'<a href="mailto:{_esc(email)}">{_esc(email)}</a>')
    if text:
        parts.append(_esc(text))
    if not parts:
        return ""
    return f'<p class="muted">{CONTACT_LABEL} · {" · ".join(parts)}</p>'


def reference_line(code: str, now: int) -> str:
    """바닥 참고 줄 — 사유 코드와 시각(UTC, 분까지). 한 번 눌러 통째로 고른다."""
    moment = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    return f'<p class="muted ref"><span class="pick">참고 {_esc(code)} · {moment} UTC</span></p>'


def _action_html(action: Link | Form, *, primary: bool) -> str:
    css = ' class="button"' if primary else ""
    if isinstance(action, Link):
        return f'<a{css} href="{_esc(action.href)}">{_esc(action.label)}</a>'
    hidden = "".join(
        f'<input type="hidden" name="{_esc(name)}" value="{_esc(value)}">'
        for name, value in action.fields
    )
    return (
        f'<form method="post" action="{_esc(action.action)}">{hidden}'
        f'<button type="submit"{css}>{_esc(action.label)}</button></form>'
    )


def frame_body(frame: Frame, *, now: int) -> str:
    """`<main>` 안 HTML — 머리부터 접힌 진단까지 정해진 차례로."""
    account = frame.account
    parts = [
        "<header>",
        mark_svg(),
        f'<div class="brand"><b>{_esc(settings.APP_LABEL)}</b>'
        f"<span>{_esc(settings.APP_SUBTITLE)}</span></div>",
        "</header>",
    ]
    if frame.chip is not None:
        word = CHIP_WORDS[frame.chip]
        parts.append(
            f'<span class="chip" style="color: var(--chip-{frame.chip})">{_esc(word)}</span>'
        )
    parts.append(f"<h1>{_esc(frame.title)}</h1>")
    parts.extend(f"<p>{_with_account(line, account)}</p>" for line in frame.lead)
    if frame.steps:
        items = "".join(f"<li>{_with_account(step, account)}</li>" for step in frame.steps)
        parts.append(f"<ol>{items}</ol>")
    actions = [_action_html(frame.primary, primary=True)]
    actions.extend(_action_html(link, primary=False) for link in frame.secondary)
    parts.append(f'<div class="actions">{"".join(actions)}</div>')
    if frame.note_text:
        if frame.note_label:
            parts.append(f'<p class="muted">{_esc(frame.note_label)}</p>')
        parts.append(f'<pre class="pick">{_esc(frame.note_text)}</pre>')
    parts.append(contact_line(frame.contact_email, frame.contact_text))
    if frame.reference:
        parts.append(reference_line(frame.reference, now))
    if frame.diagnostics:
        items = "".join(f"<li>{_esc(line)}</li>" for line in frame.diagnostics)
        parts.append(f"<details><summary>{DIAGNOSTIC_LABEL}</summary><ul>{items}</ul></details>")
    return "".join(parts)


def render(frame: Frame, *, now: int) -> str:
    """한 파일 화면 — 바깥 자원 없음. `<title>` 은 「<제목> · S.PKG CAPA」."""
    title = f"{frame.title} · {settings.APP_LABEL}"
    return (
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(title)}</title><style>{palette_css()}{_FRAME_CSS}</style></head>"
        f'<body><div class="bar"></div><main>{frame_body(frame, now=now)}</main></body></html>'
    )


def request_note(
    *, account: str, name: str | None, code: str, now: int, lines: Sequence[str] = ()
) -> str:
    """문의처로 보낼 미리 채운 글 — 앱 이름 · 계정 · 이름 · 시각 · 참고(사유 코드)."""
    moment = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    rows = [f"[{settings.APP_LABEL}] 접속 권한", f"계정: {account}"]
    if name:
        rows.append(f"이름: {name}")
    rows.extend(lines)
    rows += [f"시각: {moment} UTC", f"참고: {code}"]
    return "\n".join(rows)
