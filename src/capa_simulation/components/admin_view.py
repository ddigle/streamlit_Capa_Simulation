# Purpose: 관리자 몫 알림 · 전문을 이 회차에 보일지 가른다(통합인증 꺼진 서버는 누구에게나).

"""관리자 몫 보기(2026-11-14 「앱 대신 뜨는 화면」 보드 — 카드 p1-not-canonical · p2-sync 의 리뷰
반영).

일반 사용자가 할 수 없는 일(C-DEP 환경변수 · CI/CD · 런북 · Admin 의 관리자 단추)을 가리키는 알림 ·
전문은 관리자 회차에만 싣는다. 관리자 판정(`sso_identity.viewer_is_admin`)은 통합인증이 켜짐이
아니면 늘 거짓이라, 그 판정만 쓰면 통합인증이 꺼진 서버(개발 PC · 사내 PC · WebIDE)에서는 아무도 그
글을 보지 못한다. 그래서 꺼진 서버는 지금처럼 누구에게나 보인다.

이 판정은 보이기만 가른다 — 쓰기 · 관리자 단추의 두 번째 벽은 그 자리의 판정(`viewer_is_admin`)
그대로다.
"""

from __future__ import annotations

from capa_simulation.auth import runtime
from capa_simulation.auth.config import SsoMode
from capa_simulation.components import sso_identity


def admin_notes_visible() -> bool:
    """이 회차에 관리자 몫 알림 · 전문을 싣나 — 통합인증이 켜짐이 아니면 참, 켜짐이면 관리자일
    때만."""
    if runtime.config().mode is not SsoMode.ON:
        return True
    return sso_identity.viewer_is_admin()
