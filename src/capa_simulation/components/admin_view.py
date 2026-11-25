# Purpose: 개발자 몫 알림 · 전문 · 진단을 보일지 가르는 한 판정과 아래 등급에게 줄이는 진단 글.

"""개발자 몫 보기(2026-11-14 「앱 대신 뜨는 화면」 보드 — 카드 p1-not-canonical · p2-sync 의 리뷰
반영 · 카드 p1-boot · d12 (가) · 2026-11-18 접속 등급 「운영 진단 글」).

다른 사람이 할 수 없는 일(C-DEP 환경변수 · CI/CD · 런북 · Admin 의 개발자 단추)을 가리키는 알림 ·
전문과 서버 경로 · 프로세스 번호 · 원문을 담은 접힌 「개발자용 진단」 은 개발자 몫(`diag.full`)이다.
보일지는 `developer_notes_visible` 하나가 가른다 — 시작 점검 `AD-01` · 접속 명단 `AD-08` · `AD-09` ·
`AD-19` · 등급 파일 `AD-25` · 로그인 갱신 거절 `AD-21` · 코어 화면 오류 `AD-22` · 동기화 `SY-*` 의
개발자 전문 · DB 실패 전문 · 코어 화면 오류 카드 · 앱 시작 실패 판 · 문지기 없이 뜬 앱 판의
「개발자용 진단」. 그 가운데 서버 상태 알림(`AD-01` · `AD-08` · `AD-09` · `AD-19` · `AD-21` ·
`AD-22` · `AD-25` · 서버 부하 `AD-26` · `SY-*` 전문)은 `developer_alerts_visible` 로 세운다 — 「이
등급으로 보기」 를 따르지 않아 켜고 끄는 사이 알림 칸 상태가 그대로다(감사 알림 `AD-12` · `AD-13`
도 같은 까닭으로 실제 개발자). BigDataQuery 토큰 알림(`AD-10` · `AD-11` · `AD-23` · `AD-24`)은
이 판정 밖이다 — 통합인증이 꺼진 C-DEP 에서는 아무에게도 띄우지 않기로 했고(규칙집 결정
ad10-nosso) 실제 개발자 판정(`sso_identity.viewer_is_developer`) 그대로다.

- 화면 등급(`sso_identity.viewer_can("diag.full")`)으로 개발자면 보인다 — 운영 + 켜짐의 개발자(「이
  등급으로 보기」 동안은 보는 등급을 따른다), 운영 아닌 꺼진 서버(개발 `app.py` · 사내 WebIDE · 사내
  PC)의 누구나(제한 없음 — 그 서버에서 아무도 그 글을 보지 못하지 않게).
- 운영 아닌 서버에서 통합인증이 켜진 회차(루프백 + 가짜 IdP — 사외 시험)는 지금처럼 실제 개발자만
  본다.
- 운영 서버에서 통합인증이 꺼진 동안은 관리자까지라 아무에게도 서지 않는다 — Admin Area 가 모두에게
  잠긴 것과 같다. 그래서 이 판정이 참인 회차에는 Admin Area 가 늘 열려 있고(「그 화면으로」 가 잠긴
  화면을 가리키지 않는다) 운영 서버의 다른 사람에게 서버 경로 · 프로세스 번호 · 운영 지시가 실리지
  않는다.

이 판정은 보이기만 가른다 — 쓰기 · 개발자 단추의 두 번째 벽은 그 자리의 판정(실제 등급) 그대로다.
설비 저장 실패 · 자동 갱신 진단처럼 아래 등급에게도 한 줄을 남겨야 하는 자리는 `diagnostic_message`
로 짓는다(개발자 몫이면 원문, 아니면 화면 공용 꼴 — DB 실패 글은
`page_bootstrap.screen_error_public`, BigDataQuery 실패 글은
`company_bigdataquery_adapter.public_failure_text`).
"""

from __future__ import annotations

from capa_simulation.auth import runtime
from capa_simulation.auth.config import SsoMode
from capa_simulation.components import sso_identity


def developer_notes_visible() -> bool:
    """이 회차에 개발자 몫 알림 · 전문 · 진단을 싣나(모듈 설명)."""
    cfg = runtime.config()
    if not cfg.operational and cfg.mode is SsoMode.ON:
        return sso_identity.viewer_is_developer()
    return sso_identity.viewer_can("diag.full")


def developer_alerts_visible() -> bool:
    """이 회차에 개발자 상태 알림(서버 상태 — 그 자리가 Admin Area 인 알림)을 세우나.

    `developer_notes_visible` 와 같되 「이 등급으로 보기」 를 따르지 않는다. 미리 보기는 운영 +
    켜짐의 실제 개발자에게만 있고 화면만 바꾼다 — 그 등급을 따르면 켜는 순간 서 있던 알림이
    「해소」 되고 끄면 「새로 뜸」 으로 다시 서서 알림 칸 상태(해소 · 다시 뜸 기록)가 흔들린다.
    미리 보기 동안 그 알림의 「그 화면으로」 는 잠긴 Admin Area 에 닿는다 — 「끝내기」 뒤 열린다."""
    return sso_identity.preview_grade() is not None or developer_notes_visible()


def diagnostic_message(message: str) -> str:
    """개발자 몫이면 원문, 아니면 화면 공용 꼴 — DB 실패 글(`page_bootstrap.screen_error_public`)을
    줄인 뒤 BigDataQuery 실패 글(`company_bigdataquery_adapter.public_failure_text` — 갈래와 할
    일만, 준비 실패는 한 문장)도 줄인다. 둘 다 부를 때 읽는다(순환 import 를 피함)."""
    if developer_notes_visible():
        return message
    from capa_simulation.io.company_bigdataquery_adapter import public_failure_text
    from capa_simulation.page_bootstrap import screen_error_public

    shown = screen_error_public(message)
    public = public_failure_text(shown)
    return shown if public is None else public
