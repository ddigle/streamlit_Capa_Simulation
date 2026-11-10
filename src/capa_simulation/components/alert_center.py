# Purpose: 알림창 · Alarm · 변경 칩 · 공정 칩 · 합성 샘플 표지를 맡는 알림 칸을 페이지 앞에 세운다.

"""알림 칸(2026-11-03 결정 보드 D1 ~ D5 — 검수표 home-06 · home-08 · home-09). 규칙은 `alerts` 모듈
설명이다.

**`app.py` 에서만 불러온다**(화면 탭 줄과 같은 까닭 — 모듈을 읽을 때 Components v2 를 등록한다).
`app.py` 가 화면 탭 줄 바로 뒤, 페이지보다 앞에서 매 앱 전체 회차 고정 key(`ALERT_CENTER_KEY`)로
그린다 — 페이지가 `st.stop()` 해도 이 칸은 이미 섰다.

- **그리는 자리는 본문 칸이 아니다.** JS 가 `document.body` 에 제 호스트(`#capa-alert-host`, 그림자
  DOM)를 붙여 알림창 · 패널 · 시선 끌기 테두리를 그리고, 머리 툴바 슬롯에 공정 칩 · 합성 샘플 표지 ·
  변경 칩 · Alarm 단추 호스트(`theme_toggle.PROCESS_CHIP_ID` · `SAMPLE_MARK_ID` · `CHANGES_CHIP_ID`
  · `ALARM_BUTTON_ID`)를 세운다 — 컴포넌트 칸 안에 그리면 머리말 · 사이드바 · 대화상자의 쌓임 맥락
  밑에 깔린다. 칸 자체는 `_HIDE_STYLE` 로 접어 본문에 틈을 남기지 않는다(입장 화면과 같은 꼴).
- **data 는 세션만 읽는다**(DB · 캐시 없음). 회차마다 드는 것은 이 세션의 변경 몇
  줄(`change_summary.session_changes`)과 콜백이 담은 사건 알림(`alerts.drain_outbox`), 이번 화면
  주소(`here`), 공용 공정 값과 이 화면에 대한 짐작(`process_field.header_chip`), 합성 샘플 표지를
  세울지 뿐이라, 그대로면 data 가 같아 JS 가 다시 불리지 않는다. 색은 이 회차 테마의 토큰이다(테마
  전환은 새로고침이라 다음 data 가 새 색을 싣는다).
- **공용 공정 칩**(2026-11-09 보드 C1 (라) — 본문 위에는 칩을 두지 않는다). 공용 공정 값이 있을 때만
  툴바 맨 왼쪽에 선다 — 깔때기 · 「공정」 · 수 · 「Mold 외 2개」 · 이 화면이 따라가는데 없는 공정이
  있으면 주황 「n개 이 화면 없음」(1400px 미만은 수만, 없음은 주황 점). 이 화면에 걸리면 강조색,
  따라가지 않거나 걸리지 않으면 흐린 테두리다(풍선이 「이 화면엔 안 걸림」). 이 화면에 대한 값은
  페이지보다 먼저라 세션 기록으로 짐작하고, 공정 값 칸을 그린 회차의
  표지(`process_field.MARKER_ATTRIBUTE`)를 JS 가 회차 끝에 읽어 바로잡는다 — 지금 화면 탭 표지도
  같은 표지로 바로잡게 문서 사건(`capa-process-here`)을 보낸다. 누르면 판(변경 판처럼 브라우저
  안에서만 열고 닫는다 — UI-PRF-01): 공정마다 ✓ / – 「이 화면에 없음」, 「공정 고르기」(이 화면에
  사이드바 공정 칸이 있을 때만 — 그 칸을 눌러 팝업을 연다), 「모든 화면에서 해제」(트리거
  `process_clear` → `shared_process.clear`).
- **합성 샘플 표지**(2026-11-09 보드 T8). 「샘플 데이터」 스위치가 켜져 있고 지금 화면이 원천 미연결
  화면(`PageSpec.pending_source`)일 때만 공정 칩 오른쪽에 선다. 누르는 것이 없고 풍선만 있다.
- **다시 붙은 탭은 앱 전체 회차를 한 번 돈다**(2026-11-07 2차 보드 R1 (가)). 프런트는 마지막 회차가
  앱 전체였던 탭에 다시 붙어도 회차를 요청하지 않고, 새 세션은 모르는 프래그먼트의 요청을 회차
  없이 버린다 — 그 탭의 첫 프래그먼트 · 대화상자 저장이 조용히 버려졌다. JS 가 앱 뿌리의 연결
  표지가 붙음으로 돌아온 것을 보고 본 스레드가 300ms + 왕복 시간 조용해지기를 기다려, 그 사이
  프런트가 스스로 돈 회차가 없으면 트리거(`reconnected`)로 회차를 부른다. 시계로만 기다리면 무거운
  화면에서 겹친다 — 다시 그리느라 바쁜 동안 프런트 회차의 표지가 메시지 큐에 묶여 있다. 기다리는
  동안 사람 손이 닿으면 그 누름의 회차가 돌아오기를 더 기다린다 — 그 사이 부르면 누름의 회차를 끊어
  누름이 사라진다. 콜백은 하는 일이 없다 — 회차가 도는 것이 목적이다. 세션이 남아 있었는지는
  회차를 돌려야 알 수 있어 짧은 끊김에도 한 번 돈다(입력 · 고침은 남는다).
  **이 칸이 파이썬을 부르는 자리는 둘이다** — 이 재연결 트리거와 공정 칩 판의 「모든 화면에서 해제」
  (`process_clear`). 나머지(패널 · 판 여닫기, 거르기, 읽음, 복사, CSV)는 모두 브라우저 안이다.
- **서버 재시작은 브라우저가 가른다**(2026-11-07 통합 검수 D4 (가) · 2차 보드 R3 (가)). 재시작 뒤
  세션은 새것이라 파이썬만으로는 재시작과 첫 접속을 가르지 못한다. 프로세스마다 한 번 정하는 부트
  표지(`BOOT_MARK`)와 알림 `GL-07`(`alerts.server_restart_note`)을 data 에 미리 싣고, JS 가 이
  탭에 적어 둔 앞 표지와 다를 때만 그 알림을 띄운다 — 첫 접속 · 새 탭(앞 표지 없음)과 새로고침 ·
  테마 전환 · 복제한 탭(같은 프로세스 — 표지 같음)에는 뜨지 않는다. 둘 다 프로세스 안에서 값이 같아
  위 data 약속이 그대로다. 열어 둔 탭에는 위 재연결 회차의 data 로 조작 없이 뜬다(AGENTS 9장
  「서버 재시작 알림」).
- **세션만 사라진 탭도 브라우저가 가른다**(2차 보드 R2 (가)). 서버는 그대로인데 끊긴 지
  `server.disconnectedSessionTTL`(기본 120초)이 지나면 새 세션이라 부트 표지로는 알 수 없다.
  세션마다 한 번 정하는 표지(`session_mark`)와 알림 `GL-08`(`alerts.session_lost_note`)을 data 에
  싣고, JS 가 **문서 메모리**의 앞 data 와 견준다 — 새 문서(새로고침 · 테마 전환 · 새 탭 · 복제한
  탭 · 첫 접속)에는 앞 data 가 없어 뜨지 않는다. 앞 data 의 변경 목록이 있었거나 끊길 때 대화상자가
  열려 있던 탭에만 띄워, 잃은 것이 없는 탭이 노트북 덮개를 여닫을 때마다 뜨지 않게 한다.
- **패널은 브라우저 안에서만 열고 닫는다** — 패널 · 변경 판 · 공정 판은 트리거를 보내지 않아 열어도
  파이썬 회차가 돌지 않는다(HOME 한 번 그리기가 85 ~ 300ms 라 중요하다). 기록은 이 브라우저 탭의
  `sessionStorage`(`STORAGE`)다(D1 (가)).
- **알림에 딸린 표**(`alerts.AlertTable` — 산출 결과의 제외 목록 · 표준 목표 누락 공정·주차 · 생산
  계획 · 필요 단축 일정의 목록, 한 줄에 여럿일 수 있다)는 Alarm 줄의 「… 보기」 단추가 표마다 펼치고
  「CSV 내려받기」 가 브라우저 안에서 파일을 만든다(원본 값 · BOM — 서버를 부르지 않는다). 칸 머리
  풍선(`help`)은 `title` 이다. 표는 코드마다 가장 새 줄에만 남겨 탭 저장소에 옛 범위 표를 쌓지 않고,
  저장소가 넘치면 저장본에서 오래된 줄의 표부터 뺀다(그 화면이 다시 보내면 다시 붙는다).
- **「로그」 펼침의 「복사」 는 그 줄의 로그 전문을 평문으로 클립보드에 넣는다**(2026-11-04
  검수 의견 alarm-05) — 막히면(보안 연결이 아님 · DRM) 고른 글을 든 읽기 전용 칸을 펼침 안에
  세우고 Ctrl+C 를 청한다. 딸린 표는 행을 싣지 않고 이름 · 행 수만 적는다(표는 「CSV 내려받기」).
- **Alarm 패널 · 변경 판 · 공정 판에는 설명 글을 두지 않는다**(2026-11-04 검수 의견 alarm-02 ·
  alarm-11). 보관 · 판정 · 공정 칩 설명은 HOME Guide 「알림창 · Alarm · 변경 칩」 이 맡는다.
- **Alarm 단추는 툴바 글꼴을 물려받는다**(alarm-01) — Guide · Print · 테마 단추(`font:inherit`)와
  같은 글꼴 · 13px · 600 · 높이. 변경 칩은 한글 글이라 앱 글꼴(`tokens.FONT_FAMILY`) 그대로다.
- **「그 화면으로」 는 그 화면 안 탭까지 연다** — 표지의 `tab` 이 있으면 그 화면에 닿은 회차가 끝난
  뒤 이름이 맞는 탭 단추를 누른다(`stateful_tabs` 탭이라 보통 누름과 같은 회차가 돈다).
- **키보드 · 초점 껍데기도 이 칸이 맡는다**(`installFocusShell`) — 앱 전체 꼴이라 화면마다 고치지
  않고, 페이지마다 서는 이 칸이 문서에 처리기를 둔다. 꺼진 단추는 Tab 이 건너뛰어 감싼 풍선 칸이 탭
  자리를 맡고(설계 규칙 UI-INP-07 · 윤곽은 `sidebar_style`), 마우스로 누른 단추는 초점을 쥔 채 남아
  풍선이 닫히지 않으므로 마우스가 떠날 때 닫고(키보드 초점은 그대로 둔다), 고른 탭이 회차 중
  `tabindex` 를 잠깐 잃어 초점이 문서로 빠지면 열린 대화상자 안으로 되돌린다(대화상자의 Esc 는 그
  안의 키 사건으로만 듣는다).
- **알림창 층은 Streamlit 대화상자 위다**(`.stack` z-index 1000200 — 1.63 대화상자 1000059 위,
  2026-11-03 사본 실측). 누름을 받지 않아(`pointer-events: none`) 대화상자 조작을 막지 않는다. Alarm
  · 변경 판은 머리 띠(999990) · 진행 막대 자리(999991) 위, 모바일 사이드바(999995) · 대화상자
  아래다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import streamlit as st

from capa_simulation import alerts, shared_process
from capa_simulation.components import process_field
from capa_simulation.components.change_summary import GROUPS, ChangeItem
from capa_simulation.components.sample_data import sample_switch_on
from capa_simulation.components.theme_toggle import (
    ALARM_BUTTON_ID,
    CHANGES_CHIP_ID,
    PROCESS_CHIP_ID,
    SAMPLE_MARK_ID,
    TOOLBAR_BUTTON_ORDER,
    TOOLBAR_SLOT,
)
from capa_simulation.design import tokens
from capa_simulation.navigation import PageSpec

_ASSETS = Path(__file__).with_name("alert_center_assets")
# 컴포넌트 key — 접는 스타일이 `.st-key-<key>` 로 고른다. Components v2 key 에는 `__` 를 쓰지
# 않는다.
ALERT_CENTER_KEY: Final = "capa_alert_center"
HEADER_SELECTOR: Final = '[data-testid="stHeader"]'
# 이 브라우저 탭의 `sessionStorage` 칸 — 기록 줄 · 상태 표 · 본 사건 id · 앞 부트 표지.
STORAGE: Final = {
    "log": "capa-alerts-log-v1",
    "states": "capa-alerts-states-v1",
    "seen": "capa-alerts-seen-v1",
    "boot": "capa-alerts-boot-v1",
}
# 이 서버 프로세스의 부트 표지 — 프로세스마다 한 번 정해 세션 · 회차가 달라도 그대로다.
BOOT_MARK: Final = alerts.new_id()
# 이 세션의 표지가 사는 세션 칸 — 세션마다 한 번 정해 회차가 달라도 그대로다.
SESSION_MARK_KEY: Final = "alert_center_session_mark_v1"

# 알림 칸이 쓰는 글. `{…}` 는 JS 가 채운다. 「사내」 를 쓰지 않는다.
TEXT: Final[dict[str, str]] = {
    "alarm": "Alarm",
    "alarm_title": "알림 모아 보기",
    "alarm_aria": "Alarm — 안 읽음 {n}건",
    "panel": "알림",
    "summary": "안 읽음 {unread} · 전체 {total}",
    "read_all": "모두 읽음",
    "close": "닫기",
    "all": "전체",
    "all_pages": "모든 화면",
    "level_filter": "단계 거르기",
    "page_filter": "화면 거르기",
    # 닫힌 상태 알림 줄(해소 · 내용 바뀜 · 범위 바뀜)을 감춘다 — 「해소」 만이 아니다(지난 보드
    # a-hide-closed).
    "hide_resolved": "닫힌 것 숨김",
    "empty": "고른 조건의 알림이 없습니다.",
    "none": "아직 알림이 없습니다.",
    "go": "그 화면으로",
    "log": "로그",
    "table_open": "{title} 보기",
    "table_rows": "{n}행",
    "table_rows_clipped": "앞 {n}건 · 전체 {total}건",
    "table_csv": "CSV 내려받기",
    "open": "지금도 있음",
    "resolved": "해소 {time}",
    # 범위(리비전 · 시나리오 · 조회기간)가 바뀌어 닫힌 상태 알림 줄 — 조건이 사라진 것이
    # 아니다(2026-11-08 사용자 답 a3 — 모든 상태 알림).
    "scope_moved": "범위 바뀜 {time}",
    # 같은 범위에서 내용(건수 · 목록)만 바뀌어 새 줄로 넘어가며 닫힌 앞 줄 — 이것도 조건이 사라진
    # 것이 아니다(지난 보드 a-content-changed — a3 의 「범위 바뀜」 과 같은 뜻).
    "content_moved": "내용 바뀜 {time}",
    "kind_event": "사건 알림",
    "kind_state": "상태 알림(바뀔 때만)",
    "log_code": "코드",
    "log_first": "처음",
    "log_last": "마지막",
    "log_times": "{n}번",
    "log_page": "화면",
    "log_cause": "계기",
    "log_scope": "범위",
    "log_resolved": "해소",
    "log_scope_moved": "범위 바뀜",
    "log_content_moved": "내용 바뀜",
    "log_detail": "원본 오류",
    "log_full": "전문",
    "log_table": "딸린 표",
    "log_table_value": "{title} {n}행 — 복사에 넣지 않음(「CSV 내려받기」)",
    "log_table_value_clipped": "{title} 앞 {n}건 · 전체 {total}건 — 복사에 넣지 않음(CSV 단추)",
    "log_copy": "복사",
    "log_copy_title": "이 줄의 로그를 글로 복사",
    "log_copied": "복사했습니다",
    "log_copy_manual": "Ctrl+C 로 복사하세요",
    "resolved_gone": "조건이 사라짐",
    "not_yet": "아직",
    "cause_new": "조건이 처음 보임",
    "cause_change": "내용이 바뀜",
    "cause_event": "동작 결과",
    "changes": "이 세션의 변경",
    "changes_word": "변경",
    "changes_title": "이 세션에서 바꾸고 아직 저장 · 적용하지 않은 것과 가정",
    "changes_aria": "변경 {n}건 — {top}",
    "changes_sum": "{n}건",
    # 공용 공정 칩 · 판(2026-11-09 보드 C1 (라)).
    "process_word": "공정",
    "process_rest": process_field.REST_TEXT,
    "process_absent": "{n}개 이 화면 없음",
    "process_names": "공정 {names}",
    "process_from": "{origin} 에서",
    "process_off": "이 화면엔 안 걸림",
    "process_aria": "공정 거름 {n}개",
    "process_panel": "공정 거름 {n}개",
    "process_absent_row": "이 화면에 없음",
    "process_pick": "공정 고르기",
    "process_clear": "모든 화면에서 해제",
    # 합성 샘플 표지(2026-11-09 보드 T8).
    "sample": "합성 샘플",
    "sample_title": "합성 샘플 — 실적이 아님 · 사이드바 「샘플 데이터」 로 끔",
}


def _registered_js() -> str:
    """alert_center.js 앞에 서식을 붙인다 — 서식은 컴포넌트 `css=` 로 주지 않는다(칸의 그림자 DOM
    에만 들어가 `document.body` · 툴바에 붙인 호스트에 닿지 않는다)."""
    css = (_ASSETS / "alert_center.css").read_text(encoding="utf-8")
    js = (_ASSETS / "alert_center.js").read_text(encoding="utf-8")
    return f"const ALERT_CSS = {json.dumps(css)};\n{js}"


_ALERT_CENTER = st.components.v2.component("capa_alert_center", js=_registered_js())

# 컴포넌트 칸을 접는다(스타일만 든 `st.html` — 이벤트 칸 한 자리, 매 회차 같은 글). 칸이 그려지기
# **전**에 보낸다.
_HIDE_STYLE: Final = (
    "<style>"
    f'[data-testid="stLayoutWrapper"]:has(> .st-key-{ALERT_CENTER_KEY}),'
    f".st-key-{ALERT_CENTER_KEY}"
    "{display:none !important;}"
    "</style>"
)


def palette() -> dict[str, str]:
    """이 회차 테마의 색. 배지 글자는 면 색이다 — 밝게는 흰 글자, 어둡게는 어두운 글자가 단계 색
    위에 읽힌다."""
    return {
        "surface": tokens.SURFACE,
        "page": tokens.SURFACE_PAGE,
        "sub": tokens.SURFACE_CLASSIFICATION,
        "text": tokens.TEXT,
        "muted": tokens.TEXT_MUTED,
        "border": tokens.BORDER,
        "accent": tokens.ACCENT,
        "accent_text": tokens.ACCENT_TEXT,
        "pending": tokens.PENDING_MARK,
        "badge_ink": tokens.SURFACE,
        "info": tokens.ALERT_INFO,
        "check": tokens.ALERT_CHECK,
        "action": tokens.ALERT_ACTION,
        "error": tokens.ALERT_ERROR,
    }


def session_mark() -> str:
    """이 세션의 표지. 앱 전체 회차에 처음 그릴 때 한 번 정한다."""
    mark = st.session_state.get(SESSION_MARK_KEY)
    if not isinstance(mark, str):
        mark = alerts.new_id()
        st.session_state[SESSION_MARK_KEY] = mark
    return mark


def shows_sample_mark(current: PageSpec | None) -> bool:
    """합성 샘플 표지를 세우나 — 지금 화면이 원천 미연결 화면이고 「샘플 데이터」 가 켜졌다."""
    return current is not None and current.pending_source is not None and sample_switch_on()


def alert_center_data(
    *,
    changes: list[ChangeItem],
    events: list[alerts.AlertNote],
    current: PageSpec | None = None,
) -> dict[str, Any]:
    """알림 칸 data. 같은 변경 · 사건 · 공용 공정 값이면 회차마다 같은 값이다(시각 · 카운터를 싣지
    않는다). `current` 는 지금 화면의 선언이다 — 공정 칩의 짐작과 합성 샘플 표지가 읽는다."""
    mark = session_mark()
    return {
        "events": events,
        "changes": changes,
        "groups": [{"id": group, "label": label} for group, label in GROUPS],
        "levels": [
            {
                "id": level,
                "label": alerts.LEVEL_LABELS[level],
                "ms": alerts.POPUP_SECONDS[level] * 1000,
            }
            for level in alerts.LEVELS
        ],
        "limits": {
            "popups": alerts.POPUP_LIMIT,
            "repeat_ms": alerts.REPEAT_WINDOW_SECONDS * 1000,
            "rows": alerts.HISTORY_ROWS,
            "hours": alerts.HISTORY_HOURS,
            "attention_ms": alerts.ATTENTION_MS,
            "easing": alerts.ATTENTION_EASING,
        },
        "toolbar": {
            "slot": TOOLBAR_SLOT,
            "header": HEADER_SELECTOR,
            "order": list(TOOLBAR_BUTTON_ORDER),
            "alarm": ALARM_BUTTON_ID,
            "chip": CHANGES_CHIP_ID,
            "process": PROCESS_CHIP_ID,
            "sample": SAMPLE_MARK_ID,
        },
        "marker": alerts.MARKER_ATTRIBUTE,
        # 이번 화면 주소 — 「그 화면으로」 가 탭을 고를 때 그 화면에 닿았는지 본다.
        "here": alerts.current_page()[1],
        "storage": dict(STORAGE),
        "boot": {"mark": BOOT_MARK, "notice": alerts.server_restart_note(BOOT_MARK)},
        "session": {"mark": mark, "notice": alerts.session_lost_note(mark)},
        "palette": palette(),
        "font": tokens.FONT_FAMILY,
        "text": dict(TEXT),
        "process": process_field.header_chip(None if current is None else current.path),
        "sample": shows_sample_mark(current),
    }


def _reconnected() -> None:
    """재연결 트리거의 콜백 — 회차가 도는 것이 목적이라 할 일이 없다."""


def _clear_process() -> None:
    """공정 칩 판 「모든 화면에서 해제」 트리거의 콜백 — 공용 공정 값을 지운다(앱 전체가 돈다)."""
    shared_process.clear()


def render_alert_center(*, changes: list[ChangeItem], current: PageSpec | None = None) -> None:
    """알림 칸을 그린다 — `app.py` 가 화면 탭 줄 바로 뒤, 페이지 앞에서 매 앱 전체 회차 부른다.

    콜백이 담아 둔 사건 알림(`alerts.event`)을 이 회차 data 로 꺼내 보낸다. 이벤트 칸에는 접는
    스타일 한 자리를 쓴다. `current` 는 지금 화면의 선언이다(없으면 None).
    """
    st.html(_HIDE_STYLE)
    _ALERT_CENTER(
        key=ALERT_CENTER_KEY,
        data=alert_center_data(changes=changes, events=alerts.drain_outbox(), current=current),
        width="stretch",
        on_reconnected_change=_reconnected,
        on_process_clear_change=_clear_process,
    )
