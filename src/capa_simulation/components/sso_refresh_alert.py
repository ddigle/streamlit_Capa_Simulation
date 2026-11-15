# Purpose: 로그인 갱신이 출처·머리 검사에서만 거절되는 서버의 관리자 회차에 상태 알림 AD-21 을 낸다.

"""로그인 갱신 거절 알림(2026-11-13 「앱 대신 뜨는 화면」 보드 카드 p2-rare 한 조각).

쓰는 동안 로그인을 늘리는 갱신 요청(`POST /auth/sso/refresh` — `components/sso_refresh.py`)이
출처 · 머리 검사에서 되풀이 거절되면(접속 주소가 `CAPA_PUBLIC_URL` 과 다르거나 앞단이 갱신 머리 ·
`Origin` 을 버림) 쓰는 중에도 처음 로그인 뒤 유지 시간(기본 6시간)에 끊긴다. 사용자 화면은 그대로
둔다(끊기면 「다시 로그인」 띠가 알린다). 결과 누계는 Admin 「통합인증 점검」 의 로그인 갱신 줄에만
있어 Admin 을 열기 전에는 아무도 모른다 — 그래서 관리자의 모든 화면 회차에 상태 알림 `AD-21` 을
세운다.

- 조건: 기동 뒤 누계(`runtime.refresh_counts`)의 「출처·머리 거절」 이 1 이상이고 「다시 발급」 ·
  「건너뜀」 이 모두 0. 건너뜀(60초 안 · 상한)도 출처 · 머리 검사를 지난 요청이라, 한 번이라도 다시
  발급했거나 건너뛰었으면 길은 열린 것이라 세우지 않는다(한 사람의 다른 주소 접속 같은 잡음).
- 내용(지문)은 고정 값이다 — 거절 수를 넣으면 새 거절마다 알림창이 다시 뜬다.
- 관리자 몫(`admin_view.admin_notes_visible` — 켜진 서버라 관리자 회차)에만 세우고 다른
  회차는 해소로 부른다(`sso_status._access_read_alert` 와 같은 꼴 — 회차마다 이벤트 칸 한
  자리). 해소 표지에는 짧은 글 · 전문을 싣지 않는다 — 일반 사용자 회차의 숨은 표지에 운영
  낱말(접속 주소 환경변수 · 갱신 머리 이름)이 실리지 않게(알림 칸은 해소에 글을 쓰지 않는다).
- 통합인증이 켜진 서버만 부른다. 꺼짐 · 막힘이면 Streamlit 호출이 하나도 없다(요소 순번 그대로).
- 「그 화면으로」 는 전문이 가리키는 Admin 「통합인증 점검」 펼침까지다 — 줄이 대상을 들고 가 다른
  화면에서 눌려도 연다(`sso_status.open_sso_status`, 설계 규칙 UI-NAV-01).
"""

from __future__ import annotations

from capa_simulation import alerts
from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoMode
from capa_simulation.components.admin_view import admin_notes_visible
from capa_simulation.components.sso_status import sso_status_target
from capa_simulation.navigation import ADMIN_AREA
from capa_simulation.page_tabs_state import tab_label

ALERT_CODE = "AD-21"
SHORT_TEXT = "로그인 갱신이 거절됨 — 접속 주소 · 앞단 머리 확인"
FULL_TEXT = (
    "앱을 쓰는 동안 로그인을 늘리는 요청이 출처 · 머리 검사에서 거절됩니다(기동 뒤 다시 발급 0). "
    "그대로면 쓰는 중에도 처음 로그인 {hours}시간 뒤 끊깁니다. 접속 주소가 "
    f"{names.ENV_PUBLIC_URL} 과 같은지, 앞단이 {names.REFRESH_HEADER} 머리와 Origin 을 넘기는지 "
    "Admin 「통합인증 점검」 의 로그인 갱신 줄과 함께 봅니다."
)
# 지문의 내용 — 고정 값(거절 수를 넣으면 새 거절마다 다시 뜬다).
CONTENT = "forbidden-without-renewal"


def refresh_refused() -> bool:
    """기동 뒤 갱신이 출처 · 머리 검사에서만 거절됐는가(「출처·머리 거절」 1 이상 · 검사를 지난
    「다시 발급」 · 「건너뜀」 0)."""
    counts = runtime.refresh_counts()
    return counts["forbidden"] > 0 and counts["renewed"] == 0 and counts["skipped"] == 0


def render_refresh_alert() -> None:
    """상태 알림 `AD-21` — 켜진 서버의 매 회차에 부른다(관리자 회차에만 선다)."""
    cfg = runtime.config()
    if cfg.mode is not SsoMode.ON:
        return
    active = refresh_refused() and admin_notes_visible()
    alerts.state(
        ALERT_CODE,
        scope=None,
        content=CONTENT if active else None,
        active=active,
        text=SHORT_TEXT if active else None,
        full=FULL_TEXT.format(hours=cfg.session_seconds // 3600) if active else None,
        goto=(tab_label(ADMIN_AREA), ADMIN_AREA.href),
        target=sso_status_target(),
    )
