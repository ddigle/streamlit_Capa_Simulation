# Purpose: 앱 밖 화면(거절·로그인 실패·되풀이·로그아웃·설정 막힘)이 함께 쓰는 틀 — 순수 HTML.

"""앱 밖 화면의 공통 틀(「앱 대신 뜨는 화면」 보드 카드 frame — 2026-11-14 답 「좋음」).

위에서 아래 차례 하나로 그린다.

1. 머리 — 맨 위 강조색 줄 + 앱 마크 + 「S.PKG CAPA」 / 작은 글 「AX Management」(앱 머리
   띠와 같은 두 줄).
2. 상태 표지 — 낱말 + 색(색만으로 뜻을 싣지 않는다 — UI-ACC-03). 낱말은 `CHIP_WORDS` 다섯뿐.
3. 제목 한 문장(마침표 없음) → 까닭 1~2문장 → 다음에 할 일(번호, 넷까지 — 보드 D8 답).
4. 주 단추 하나(링크 또는 폼) + 보조 링크. 막다른 화면을 두지 않는다 — 단추나 링크가 하나는
   있다. 주 단추가 없는 화면은 보조 링크만 선다(로그인 설정 문제 — 「다시 시도」 가 보조, 카드
   p1-login-fail).
5. (있으면) 미리 채운 글 상자 — 한 번 눌러 통째로 고른다(`user-select: all`, 스크립트 없음).
6. 문의 줄 — 문의 메일(`settings.app_contact_email`)은 메일 링크, 창구 글
   (`CAPA_ACCESS_CONTACT`)은 그 뒤에. 둘 다 비면 그리지 않는다(UI-TXT-08).
7. 바닥 「참고 <사유 코드> · <시각> UTC」(+ 있으면 「 · 진단 <번호>」 — 오류 화면이 보관한
   진단의 번호, 한 번 눌러 통째로 고름) — 새 번호 체계 없이 지금 사유 코드 · 진단 번호를 쓴다.
8. 접힌 「관리자용 진단」 — 머리 줄(설정 막힘의 「고칠 것 n개」) · 줄 · 이름표와 값의 표 · 그
   안에 다시 접힌 칸 하나(설정 막힘의 「환경변수 전체(n)」 — 표 · 값 표 · 줄). 접어도 누구나
   펼친다 — 토큰 · 비밀값 · 쿠키 값은 싣지 않고, 지금까지 실어 온 계산한 주소 · 등록 번호 ·
   인증서 지문과 이름 · 수만 싣는다(보드 D9 「이름 · 수」).

스크립트가 없다(CSP `default-src 'none'`) — 마크는 인라인 SVG, 서식은 인라인 `<style>` 이다.
밝은 · 어두운 팔레트(`design/tokens`)를 함께 싣고 `prefers-color-scheme` 로 고른다
(UI-ACC-01). 좁은 창은 양옆 16px(UI-ACC-02) — 표는 칸 안에서 줄을 바꿔 가로로 넘치지 않는다.
글은 띄어쓰기에서만 줄을 바꿔 한국어 낱말을 가운데서 가르지 않고(`word-break: keep-all`), 띄어쓰기
없는 긴 메일 · 주소만 아무 데서나 접는다(`overflow-wrap: anywhere`).
사람이 읽는 시각(「○시 ○분」)은 한국 시각(KST — +09:00 고정, 일광 절약 시간 없음 — 감사 기록
화면과 같은 기준)이고, 관리자가 사건과 맞추는 바닥 참고 줄은 UTC 다. 표준 라이브러리와 토큰
팔레트만 쓴다 —
Streamlit 을 import 하지 않는다(문지기는 이벤트 루프에서 돈다). 넘겨받은 글은 모두 이 모듈이
`html.escape` 한다 — 부르는 쪽은 평문을 넘긴다.
"""

from __future__ import annotations

import functools
import html
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Final

from capa_simulation import korea_time, settings

# 상태 표지 — 낱말과 색 역할(토큰 이름). 로그아웃 화면은 표지가 없다. 시작 임시 화면
# (`scripts/container_stage.py` — 「시작 중」 · 「다시 시도」 · 「점검 중」)도 이 두 표를 불러 쓴다.
CHIP_WORDS: Final = {
    "denied": "권한 없음",
    "registered": "등록 완료",
    "retry": "다시 시도",
    "maintenance": "점검 중",
    "starting": "시작 중",
}
CHIP_ROLES: Final = {
    "denied": "ALERT_ERROR",
    "registered": "ACCENT",
    "retry": "ALERT_CHECK",
    "maintenance": "ALERT_CHECK",
    "starting": "ALERT_ACTION",
}
DIAGNOSTIC_LABEL: Final = "관리자용 진단"
CONTACT_LABEL: Final = "문의"
REFERENCE_LABEL: Final = "참고"
DIAGNOSTIC_ID_LABEL: Final = "진단"
# 사람이 읽는 시각의 기준(「○시 ○분」) — 화면 시각 한 곳 `korea_time.KST` 그대로(감사 기록
# 화면과 같다).
KST: Final = korea_time.KST
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
    *((f"chip-{name}", role) for name, role in CHIP_ROLES.items()),
)
_FRAME_CSS: Final = """
body { margin: 0; padding: 0 16px; background: var(--bg); color: var(--fg); line-height: 1.6;
  font-family: var(--font); word-break: keep-all; overflow-wrap: anywhere; }
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
details details { margin: 8px 0 0; }
summary { cursor: pointer; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; table-layout: fixed; }
th, td { border-bottom: 1px solid var(--line); padding: 4px 6px; text-align: left;
  vertical-align: top; overflow-wrap: anywhere; }
th { font-weight: 600; }
th:first-child, td:first-child { width: 42%; }
code { font-family: ui-monospace, Consolas, monospace; font-size: .92em; overflow-wrap: anywhere; }
strong.account { font-family: ui-monospace, Consolas, monospace; word-break: break-all; }
@media (max-width: 480px) {
  main { margin: 16px auto; padding: 18px 16px; }
  th, td { padding: 4px 3px; }
}
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
class Table:
    """접힌 진단 안의 표 하나 — 머리(없으면 빈 튜플) · 줄 · 글자 그대로 보일 칸 번호(`<code>`) ·
    좁은 창에서 `_` 뒤에서 먼저 끊을 칸 번호(환경변수 이름 — `<wbr>`, 복사한 글은 그대로다)."""

    rows: tuple[tuple[str, ...], ...]
    head: tuple[str, ...] = ()
    code_columns: tuple[int, ...] = ()
    break_columns: tuple[int, ...] = ()


@dataclass(frozen=True)
class Fold:
    """접힌 진단 안에 다시 접힌 칸 하나 — 이름 · 표 · 값 표(이름표 | 값) · 그 아래 줄."""

    summary: str
    table: Table | None = None
    lines: tuple[str, ...] = ()
    facts: Table | None = None


@dataclass(frozen=True)
class Frame:
    """화면 한 장의 내용 — 모두 평문이다(이 모듈이 이스케이프한다).

    `primary` 가 `None` 이면 보조 링크만 선다 — 그때 `secondary` 가 비어 있으면 안 된다(막다른
    화면). `reference_id` 는 오류 화면이 보관한 진단의 번호(바닥 참고 줄 끝)다. `diagnostic_head` 는
    접힌 진단 맨 위의 글머리 없는 한 줄이다(그 아래 `diagnostics` 줄의 수를 말하는 머리).
    """

    title: str
    chip: str | None
    lead: tuple[str, ...]
    primary: Link | Form | None
    steps: tuple[str, ...] = ()
    secondary: tuple[Link, ...] = ()
    note_label: str = ""
    note_text: str = ""
    reference: str = ""
    reference_id: str = ""
    diagnostic_head: str = ""
    diagnostics: tuple[str, ...] = ()
    diagnostic_table: Table | None = None
    diagnostic_fold: Fold | None = None
    account: str = field(default="", repr=False)
    contact_email: str = field(default="", repr=False)
    contact_text: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if self.primary is None and not self.secondary:
            raise ValueError("막다른 화면 — 주 단추도 보조 링크도 없다")


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


def reference_text(code: str, now: int, diagnostic_id: str = "") -> str:
    """바닥 참고 줄의 글 — 「참고 <사유 코드> · <시각> UTC」(+ 「 · 진단 <번호>」)."""
    moment = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    text = f"{REFERENCE_LABEL} {code} · {moment} UTC"
    return f"{text} · {DIAGNOSTIC_ID_LABEL} {diagnostic_id}" if diagnostic_id else text


def reference_line(code: str, now: int, diagnostic_id: str = "") -> str:
    """바닥 참고 줄 — 사유 코드 · 시각(UTC, 분까지) · (있으면) 진단 번호. 한 번 눌러 통째로
    고른다."""
    text = reference_text(code, now, diagnostic_id)
    return f'<p class="muted ref"><span class="pick">{_esc(text)}</span></p>'


def clock_text(moment: int, *, round_up: bool = False) -> str:
    """사람이 읽는 「○시 ○분」(KST). `round_up` 이면 초가 있을 때 다음 분으로 올린다 — 「이
    시각 뒤에」 를 말할 때 그 분이 되면 늘 지나 있게."""
    stamp = datetime.fromtimestamp(moment, tz=KST)
    if round_up and stamp.second:
        stamp = stamp.replace(second=0) + timedelta(minutes=1)
    return f"{stamp.hour}시 {stamp.minute}분"


def table_html(table: Table) -> str:
    """진단 표 — 칸 글은 모두 이스케이프하고, `code_columns` 칸은 글자 그대로(`<code>`),
    `break_columns` 칸은 `_` 뒤에 끊을 자리(`<wbr>`)를 둔다."""

    def cell(index: int, value: str, tag: str) -> str:
        shown = _esc(value)
        if tag == "td" and index in table.break_columns:
            shown = shown.replace("_", "_<wbr>")
        if tag == "td" and index in table.code_columns and value:
            shown = f"<code>{shown}</code>"
        return f"<{tag}>{shown}</{tag}>"

    head = ""
    if table.head:
        cells = "".join(cell(index, name, "th") for index, name in enumerate(table.head))
        head = f"<thead><tr>{cells}</tr></thead>"
    rows = "".join(
        "<tr>" + "".join(cell(index, value, "td") for index, value in enumerate(row)) + "</tr>"
        for row in table.rows
    )
    return f"<table>{head}<tbody>{rows}</tbody></table>"


def _lines_html(lines: Sequence[str]) -> str:
    if not lines:
        return ""
    return "<ul>" + "".join(f"<li>{_esc(line)}</li>" for line in lines) + "</ul>"


def diagnostics_html(frame: Frame) -> str:
    """접힌 「관리자용 진단」 — 머리 줄 → 줄 → 표 → 다시 접힌 칸(표 → 값 표 → 줄). 넷 다 없으면
    빈 글(그리지 않는다)."""
    if not (
        frame.diagnostic_head
        or frame.diagnostics
        or frame.diagnostic_table
        or frame.diagnostic_fold
    ):
        return ""
    parts = [f"<p>{_esc(frame.diagnostic_head)}</p>"] if frame.diagnostic_head else []
    parts.append(_lines_html(frame.diagnostics))
    if frame.diagnostic_table is not None:
        parts.append(table_html(frame.diagnostic_table))
    fold = frame.diagnostic_fold
    if fold is not None:
        inner = "".join(
            table_html(table) for table in (fold.table, fold.facts) if table is not None
        )
        parts.append(
            f"<details><summary>{_esc(fold.summary)}</summary>{inner}"
            f"{_lines_html(fold.lines)}</details>"
        )
    return f"<details><summary>{DIAGNOSTIC_LABEL}</summary>{''.join(parts)}</details>"


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
    actions = [] if frame.primary is None else [_action_html(frame.primary, primary=True)]
    actions.extend(_action_html(link, primary=False) for link in frame.secondary)
    parts.append(f'<div class="actions">{"".join(actions)}</div>')
    if frame.note_text:
        if frame.note_label:
            parts.append(f'<p class="muted">{_esc(frame.note_label)}</p>')
        parts.append(f'<pre class="pick">{_esc(frame.note_text)}</pre>')
    parts.append(contact_line(frame.contact_email, frame.contact_text))
    if frame.reference:
        parts.append(reference_line(frame.reference, now, frame.reference_id))
    parts.append(diagnostics_html(frame))
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
