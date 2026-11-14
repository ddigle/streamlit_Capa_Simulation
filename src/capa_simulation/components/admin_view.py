# Purpose: 관리자 몫 알림 · 전문 · 진단을 보일지 가르는 한 판정(관리자, 운영 아닌 꺼진 서버).

"""관리자 몫 보기(2026-11-14 「앱 대신 뜨는 화면」 보드 — 카드 p1-not-canonical · p2-sync 의 리뷰
반영 · 카드 p1-boot · d12 (가)).

일반 사용자가 할 수 없는 일(C-DEP 환경변수 · CI/CD · 런북 · Admin 의 관리자 단추)을 가리키는 알림 ·
전문과 서버 경로 · 프로세스 번호 · 원문을 담은 접힌 「관리자용 진단」 은 관리자 몫이다. 보일지는
이 함수 하나가 가른다 — 시작 점검 `AD-01` · 접속 명단 `AD-08` · `AD-09` · `AD-19` · 로그인 갱신
거절 `AD-21` · 코어 화면 오류 `AD-22` · 동기화 `SY-*` 의 관리자 전문 · DB 실패 전문 · 코어 화면
오류 카드 · 앱 시작 실패 판 · 문지기 없이 뜬 앱 판의 「관리자용 진단」. BigDataQuery 토큰
알림(`AD-10` · `AD-11` · `AD-17` · `AD-18`)은 이 판정 밖이다 — 통합인증이 꺼진 C-DEP 에서는
아무에게도 띄우지 않기로 했고(규칙집 결정 ad10-nosso — 할 일인 「토큰 넣기」 단추도 관리자 신원이
있어야 선다) 관리자 판정(`viewer_is_admin`) 그대로다.

- 관리자(`sso_identity.viewer_is_admin` — 환경변수 관리자 ∪ 명단 관리자 등급)면 늘 보인다.
- 통합인증이 켜짐이 아니고(꺼짐 · 막힘 — 관리자 신원이 없다) 운영 서버가 아니면(개발 `app.py` ·
  사내 WebIDE · 사내 PC) 누구에게나 보인다 — 관리자 판정만 쓰면 그 서버에서는 아무도 그 글을 보지
  못한다.
- 운영 서버(`SsoConfig.operational` — Admin Area 잠금 `sso_identity.admin_area_locked` 와 한
  뿌리)에서 통합인증이 꺼진 동안은 아무에게도 서지 않는다 — Admin Area 가 모두에게 잠긴 것과
  같다. 그래서 이 판정이 참인 회차에는 Admin Area 가 늘 열려 있고(「그 화면으로」 가 잠긴 화면을
  가리키지 않는다) 운영 서버의 일반 사용자에게 서버 경로 · 프로세스 번호 · 운영 지시가 실리지
  않는다.

이 판정은 보이기만 가른다 — 쓰기 · 관리자 단추의 두 번째 벽은 그 자리의 판정(`viewer_is_admin`)
그대로다.
"""

from __future__ import annotations

from capa_simulation.auth import runtime
from capa_simulation.auth.config import SsoMode
from capa_simulation.components import sso_identity


def admin_notes_visible() -> bool:
    """이 회차에 관리자 몫 알림 · 전문 · 진단을 싣나 — 관리자, 또는 통합인증이 켜짐이 아니고 운영
    서버가 아닌 회차의 누구나(모듈 설명)."""
    if sso_identity.viewer_is_admin():
        return True
    cfg = runtime.config()
    return cfg.mode is not SsoMode.ON and not cfg.operational
