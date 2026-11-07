# Purpose: 데이터 때문에 화면 · 구획을 못 그린 자리의 공통 「데이터 Error」 마크와 그 알림을 낸다.

"""「데이터 Error」 마크 — 화면 전체가 같은 꼴이다(2026-11-05 사용자 지시 — 「페이지에는 데이터
Error 마크를 넣고 Alarm 확인 필요 문구까지만 배치, 나머지는 알람으로 확인」).

**무엇이 마크인가.** 데이터 때문에 화면 · 탭 · 구획을 그리지 못한 자리다 — 자료 없는 달을
고름(`page_bootstrap.resolve_effective_months`), 계산 멈춤(`stop_calculation_on_error`), DB ·
기준정보를 읽지 못함, 다른 화면에서 채울 입력이 빠져 멈춤(재공 현황 주차별 가용대수 · 필요 단축
일정과 Space 「필요 단축」 Cut-off · 공정 Capa 상세 · 제약 시뮬레이션 · 개조 일정의 저장본 · 이름 ·
Cut-off — `goto` 로 Alarm 줄의 「그 화면으로」 가 그 화면을 연다, 자리에 길 안내를 두지 않는다).
자리에는 마크와 「Alarm 확인 필요」 만 서고, 오류 글(까닭 · 예시 행 · 고칠 곳)은 오류 단계 사건
알림으로만 간다 — 오른쪽 아래 알림창에 한 번, 머리 `Alarm` 줄에 전문 · 로그 ·
복사.

**무엇이 마크가 아닌가.** 볼 것이 없는 빈 상태(회색 평문 한 줄 — 설계 규칙 UI-TXT-04), 그 자리에
고칠 입력이 있는 거부 · 동작 실패(곁 오류 — UI-NTF-03), 모듈 오류 카드(`module_failure_card`), 앱이
서지 못해 알림 칸이 없는 부트스트랩 실패(`app.py` — 그때는 볼 `Alarm` 이 없다).

**한 칸에 함께 그린다.** 마크와 알림 표지(`alerts.hidden_marker`)가 `st.html` 하나라 이벤트 칸을
쓰지 않는다 — 본문 프래그먼트 · 팝업 본문에서도 갈래마다 이벤트 칸 자리 수가 그대로다(AGENTS 9장).
색은 그 회차 테마 토큰이고, 폭이 좁으면 두 칸이 줄을 바꾼다.
"""

from __future__ import annotations

from typing import Final

import streamlit as st

from capa_simulation import alerts
from capa_simulation.design import tokens

MARK_LABEL: Final = "데이터 Error"
MARK_NEXT: Final = "Alarm 확인 필요"
# 마크의 클래스 — 시험이 이 이름으로 찾는다.
MARK_CLASS: Final = "capa-data-error-mark"
# 칠한 칸 옆 면의 농도 — 글이 묻히지 않을 만큼만 물들인다.
_TINT_ALPHA: Final = 0.08


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


def render_data_error_mark() -> None:
    """마크만 그린다 — 알림을 따로 한 번 보내는 자리(`state_alerts.alert_page_error`)가 쓴다."""
    st.html(data_error_mark_html())


def render_data_error(
    message: str,
    *,
    code: str,
    tab: str = "",
    text: str | None = None,
    goto: tuple[str, str] | None = None,
) -> None:
    """마크를 그리고 오류 글을 사건 알림으로 보낸다(`alerts.page_error_note` — 같은 글이면 알림창
    한 번). 담아 둔 사건 알림도 같은 표지로 보낸다 — 이 뒤에 `st.stop()` 이 오면 표지 자리가 더
    없다. `code` 는 그 화면의 코드, `tab` 은 「그 화면으로」 가 열 탭, `text` 는 알림창 짧은
    글, `goto` 는 채울 입력이 다른 화면에 있을 때 「그 화면으로」 가 열 화면(이름, 주소)이다."""
    note = alerts.page_error_note(message, code=code, tab=tab, text=text, goto=goto)
    st.html(data_error_mark_html() + alerts.hidden_marker([*alerts.drain_outbox(), note]))
