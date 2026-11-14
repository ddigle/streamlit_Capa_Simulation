# Purpose: 데이터 때문에 화면 · 구획을 못 그린 자리의 공통 「데이터 Error」 마크와 그 알림을 낸다.

"""「데이터 Error」 마크 — 화면 전체가 같은 꼴이다(2026-11-05 사용자 지시 — 「페이지에는 데이터
Error 마크를 넣고 Alarm 확인 필요 문구까지만 배치, 나머지는 알람으로 확인」).

**무엇이 마크인가.** 데이터 때문에 화면 · 탭 · 구획을 그리지 못한 자리다 — 자료 없는 달을
고름(`page_bootstrap.resolve_effective_months`), 계산 멈춤(`stop_calculation_on_error`), DB ·
기준정보를 읽지 못함, 다른 화면에서 채울 입력이 빠져 멈춤(재공 현황 주차별 가용대수 · 필요 단축
일정과 Space 「필요 단축」 Cut-off · 공정 Capa 상세 · 제약 시뮬레이션 · 개조 일정의 저장본 · 이름 ·
Cut-off — `goto` 로 Alarm 줄의 「그 화면으로」 가 그 화면(셋째 칸이 있으면 그 탭 · 종류 단추까지)을
연다, 자리에 길 안내를 두지 않는다).
자리에는 마크와 「Alarm 확인 필요」 만 서고, 오류 글(까닭 · 예시 행 · 고칠 곳)은 오류 단계 사건
알림으로만 간다 — 오른쪽 아래 알림창에 한 번, 머리 `Alarm` 줄에 전문 · 로그 ·
복사.

**무엇이 마크가 아닌가.** 볼 것이 없는 빈 상태(회색 평문 한 줄 — 설계 규칙 UI-TXT-04), 그 자리에
고칠 입력이 있는 거부 · 동작 실패(곁 오류 — UI-NTF-03), 모듈 오류 카드(`module_failure_card`), 앱이
서지 못해 알림 칸이 없는 부트스트랩 실패(`app.py` — 그때는 볼 `Alarm` 이 없다).

**불러온 리비전이 없는 회차는 빈 상태다.** 이 함수들이 받은 글이 `page_bootstrap.empty_state` 의 글
(공식버전 없음 · 보관본만 · 안 불러옴 — 화면이 머리를 붙였어도)이면 마크 대신 회색 한 줄(「공식버전
없음」)을 세운다. 공식버전이 없는 두 갈래의 알림은 화면마다 따로 내지 않고 상태 알림 `SC-01`
하나다(`page_bootstrap.missing_official_note` — 시나리오 관리 「Capa 시나리오」 탭과 같은 표지라
어느 화면을 돌아도 Alarm 줄 하나 · 알림창 한 번, 2026-11-14 물음 보드 decided 5). 해소는
공식버전이 있다고 확인한 회차의 알림 칸이 낸다(`alert_center`). 공식은 있는데 이 세션이 안 불러온
갈래만 그 화면 코드의 **확인 단계** 사건 알림(「불러온 시나리오 없음 — 새로고침하면 공식버전을
엶」)이다.

**알림 짧은 글 꼴.** 사람이 고칠 수 없는 DB 실패(`page_bootstrap.screen_error_short`)는 「… —
관리자에게 알려 주세요」 로 끝나고, 사용자가 고칠 원인인데 부르는 쪽이 고칠 화면을 주지 않은 경로 ·
계획 표 빈 리비전은 「그 화면으로」 가 시나리오 관리 「DB 등록」 을
연다(`page_bootstrap.screen_error_goto`). 그 DB 실패의 전문(파일 경로 · 파일을 연 프로세스 번호 ·
원문 줄)은 관리자 몫(`admin_view.admin_notes_visible` — 운영 아닌 꺼진 서버는 누구에게나)에만
싣고, 그 밖에는 첫 문단과 「관리자에게 알려 주세요.」 만이다(`page_bootstrap.screen_error_public`).

**한 칸에 함께 그린다.** 마크와 알림 표지(`alerts.hidden_marker`)가 `st.html` 하나라 이벤트 칸을
쓰지 않는다 — 본문 프래그먼트 · 팝업 본문에서도 갈래마다 이벤트 칸 자리 수가 그대로다(AGENTS 9장).
색은 그 회차 테마 토큰이고, 폭이 좁으면 두 칸이 줄을 바꾼다.
"""

from __future__ import annotations

import html
from typing import Final, TypeAlias

import streamlit as st

from capa_simulation import alerts, page_bootstrap
from capa_simulation.design import tokens

MARK_LABEL: Final = "데이터 Error"
MARK_NEXT: Final = "Alarm 확인 필요"
# 마크의 클래스 — 시험이 이 이름으로 찾는다.
MARK_CLASS: Final = "capa-data-error-mark"
# 빈 상태 회색 한 줄의 클래스 — 시험이 이 이름으로 찾는다.
EMPTY_CLASS: Final = "capa-empty-state"
# 빈 상태 알림의 로그 「계기」.
EMPTY_CAUSE: Final = "불러온 시나리오가 없어 볼 것이 없음"
# 칠한 칸 옆 면의 농도 — 글이 묻히지 않을 만큼만 물들인다.
_TINT_ALPHA: Final = 0.08

# 「그 화면으로」 가 열 화면 — (이름, 주소), 그 화면의 탭 · 종류 단추까지 열면 셋째 칸이 그 글이다.
ErrorGoto: TypeAlias = tuple[str, str] | tuple[str, str, str]


def data_error_mark_html() -> str:
    """마크 한 칸의 HTML(서식 포함) — 그 회차 테마 토큰으로 짓는다. 칠한 칸의 글자는 면 색이다.

    아이콘은 CSS 동그라미 「!」 다 — `st.html` 은 SVG 를 걷고, 글꼴 아이콘은 늦게 뜰 수 있다."""
    return (
        "<style>"
        f".{MARK_CLASS}{{display:inline-flex;flex-wrap:wrap;align-items:stretch;max-width:100%;"
        f"border:1.5px solid {tokens.ALERT_ERROR};border-radius:8px;overflow:hidden;"
        f"background:{tokens.opaque_mix(tokens.ALERT_ERROR, tokens.SURFACE, _TINT_ALPHA)};"
        "font-size:0.875rem;line-height:1.4;}"
        f".{MARK_CLASS}__label{{display:inline-flex;align-items:center;gap:6px;padding:6px 12px;"
        f"background:{tokens.ALERT_ERROR};color:{tokens.SURFACE};font-weight:700;}}"
        f".{MARK_CLASS}__icon{{display:inline-flex;align-items:center;justify-content:center;"
        f"width:18px;height:18px;border-radius:50%;background:{tokens.SURFACE};"
        f"color:{tokens.ALERT_ERROR};font-size:0.9375rem;font-weight:800;line-height:1;}}"
        f".{MARK_CLASS}__next{{display:inline-flex;align-items:center;padding:6px 12px;"
        f"color:{tokens.TEXT};font-weight:600;}}"
        "</style>"
        f'<div class="{MARK_CLASS}" role="status">'
        f'<span class="{MARK_CLASS}__label">'
        f'<span class="{MARK_CLASS}__icon" aria-hidden="true">!</span>{MARK_LABEL}</span>'
        f'<span class="{MARK_CLASS}__next">{MARK_NEXT}</span>'
        "</div>"
    )


def empty_state_html(line: str) -> str:
    """빈 상태 회색 한 줄의 HTML — 캡션과 같은 크기 · 흐린 글자(그 회차 테마 토큰)."""
    return (
        f'<p class="{EMPTY_CLASS}" style="margin:0;color:{tokens.TEXT_MUTED};'
        f'font-size:0.875rem;line-height:1.5;">{html.escape(line)}</p>'
    )


def _empty_state_note(
    message: str, state: page_bootstrap.EmptyState, *, code: str
) -> alerts.AlertNote:
    """빈 상태의 알림 — 공식버전이 없으면 상태 알림 `SC-01` 하나(어느 화면이든 같은 표지), 공식은
    있는데 안 불러왔으면 그 화면의 확인 단계 사건 알림(같은 코드 + 같은 글이면 같은 id 라 이 탭에 한
    번 뜬다)."""
    if state.missing is not None:
        return page_bootstrap.missing_official_note(state.missing)
    plain = alerts.plain_text(message)
    return alerts.event_note(
        code,
        text=state.text,
        full=plain,
        level="check",
        cause=EMPTY_CAUSE,
        alert_id="empty-" + alerts.fingerprint(code, None, plain),
        keep=True,
    )


def data_error_note(
    message: str,
    *,
    code: str,
    tab: str = "",
    text: str | None = None,
    goto: ErrorGoto | None = None,
) -> alerts.AlertNote:
    """오류 글의 사건 알림 표지 한 칸(`alerts.page_error_note`) — `goto` 셋째 칸을 `tab` 으로 푼다.
    그 칸이 있으면 줄의 화면 칸이 「화면 › 표」 이고 「그 화면으로」 가 그 표까지 연다.

    빈 상태 글이면 그 알림(`_empty_state_note` — 공식버전이 없으면 `SC-01`)이고, `text` ·
    `goto` 를 주지 않았으면 짧은 글 · 고칠 곳을 글에서 고른다(`page_bootstrap.screen_error_short`
    · `screen_error_goto`). 사람이 고칠 수 없는 DB 실패의 전문은 관리자 몫이 아니면
    걷는다(`screen_error_public`)."""
    state = page_bootstrap.empty_state(message)
    if state is not None:
        return _empty_state_note(message, state, code=code)
    admin_short = page_bootstrap.screen_error_short(message)
    if admin_short is not None:
        # 부를 때 읽는다 — 관리자 판정이 이끄는 머리 띠 모듈들이 이 모듈을 부른다(순환).
        from capa_simulation.components import admin_view

        if not admin_view.admin_notes_visible():
            message = page_bootstrap.screen_error_public(message)
    if text is None:
        text = admin_short
    elif admin_short is not None and not text.endswith(page_bootstrap.ADMIN_TAIL):
        text += page_bootstrap.ADMIN_TAIL
    if goto is None:
        goto = page_bootstrap.screen_error_goto(message)
    if goto is None:
        return alerts.page_error_note(message, code=code, tab=tab, text=text)
    name, href, *rest = goto
    return alerts.page_error_note(
        message, code=code, tab=rest[0] if rest else tab, text=text, goto=(name, href)
    )


def place_html(message: str | None) -> str:
    """오류 자리 한 칸 — 빈 상태 글이면 회색 한 줄, 아니면 「데이터 Error」 마크."""
    state = None if message is None else page_bootstrap.empty_state(message)
    return data_error_mark_html() if state is None else empty_state_html(state.line)


def render_data_error_mark(message: str | None = None) -> None:
    """마크만 그린다 — 알림을 따로 한 번 보내는 자리(`state_alerts.alert_page_error`)가 쓴다.
    `message` 가 빈 상태 글이면 마크 대신 회색 한 줄이다."""
    st.html(place_html(message))


def render_data_error(
    message: str,
    *,
    code: str,
    tab: str = "",
    text: str | None = None,
    goto: ErrorGoto | None = None,
) -> None:
    """마크를 그리고 오류 글을 사건 알림으로 보낸다(`data_error_note` — 같은 글이면 알림창
    한 번). 담아 둔 사건 알림도 같은 표지로 보낸다 — 이 뒤에 `st.stop()` 이 오면 표지 자리가 더
    없다. `code` 는 그 화면의 코드, `tab` 은 「그 화면으로」 가 열 탭, `text` 는 알림창 짧은
    글, `goto` 는 채울 입력이 다른 화면에 있을 때 「그 화면으로」 가 열 화면(`ErrorGoto`)이다."""
    note = data_error_note(message, code=code, tab=tab, text=text, goto=goto)
    st.html(place_html(message) + alerts.hidden_marker([*alerts.drain_outbox(), note]))
