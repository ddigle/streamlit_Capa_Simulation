# Purpose: 코어 화면 실행을 감싸 처리 못 한 오류를 그 화면 카드 · 참고 번호 · 관리자 알림으로.

"""코어 화면 오류 카드(2026-11-14 「앱 대신 뜨는 화면」 보드 카드 p2-rare — 처리 못 한 오류,
d12 (가)).

`app.py` 가 모듈이 아닌 화면의 `navigation.run()` 을 `run_core_page` 로 부른다(모듈 화면은
`module_runtime.run_module_page` — 같은 꼴). 화면 본문에서 잡히지 않은 오류(`BOOTSTRAP_ERRORS` 밖의
`AttributeError` · `IndexError` 등)는 Streamlit 기본 오류 상자(형식 · 글 · traceback · 서버 경로)
대신 그 화면 자리에 카드 하나로 선다 — 사이드바 · 머리 띠 · 탭 줄 · 다른 화면은 그대로다.

- **카드** — 오류 상자 머리 한 줄 「이 화면에 오류가 났습니다 — 다른 화면은 그대로 쓸 수
  있습니다」 + 값 줄 「참고 번호 <8자> · <오류 종류>」(운영 서버도 오류 종류 이름은 보인다 — d12
  (가)). 관리자 몫(`admin_view.admin_notes_visible` — 운영 아닌 꺼진 서버는 누구에게나)에만 접힌
  「관리자용 진단」 이 선다 — 첫 줄(200자) · 이 저장소 안 프레임(`<상대 경로>:<줄> in <함수>` —
  절대 경로 · 설치 패키지 프레임 없음) · 복사 단추. C-DEP 에는 셸도 로그도 없어 관리자가 원문을
  보는 자리가 이 접힘이다.
- **멈춤으로 끝낸다** — 처리한 실패(카드 · 아래 프래그먼트 실패)는 `st.stop()` 으로 회차를
  끝낸다. 정상으로 돌아오면 Streamlit 이 그 회차를 끝까지 돈 회차로 보고, 이번에 그리지 못한
  위젯(오류 자리 아래의 편집 칸 · 입력 칸)의 미저장 값을 지운다. 멈춤은 그 값을 남기고
  `app.py` 의 멈춤 길(`AppRun.finish_stopped` — 스스로 멈춘 화면이라 끝난 회차)을 탄다.
- **기록 · 관리자 알림** — 실패는 `page_failures` 에 참고 번호 · 시각 · 화면 · 종류만 적고(본문
  없음) 서버 로그에 참고 번호와 함께 원문을 남긴다. 관리자 상태 알림 `AD-22`
  (`render_page_failure_alert` — `app.py` 가 토큰 알림 곁에서 부른다)는 그 기록에서 낸다 — 오류가
  난 탭이 관리자의 탭이 아니어서다. 이벤트 칸 수는 프로세스 동안 같아야 해서(팝업 호스트 차례 —
  AGENTS 9장) 시작 점검 알림 `AD-01` 과 같은 판정(`start_check_alert_possible` — 결과 파일 · CD
  전용 환경변수, 프로세스 동안 그대로)이 참인 서버만 회차마다 한 자리를 쓰고(실패가 없거나
  관리자 몫이 아니면 해소로), 그 밖(개발 · 사내 PC · 시험)은 Streamlit 호출이 없다 — 그 서버는
  운영이 아니고 통합인증이 꺼져 카드의 「관리자용 진단」 이 누구에게나 선다.
- **지나가는 것** — Streamlit 제어 예외(`st.stop()` · `st.rerun()` · `st.switch_page` —
  `ScriptControlException`)와 `KeyboardInterrupt` 는 그대로 다시 던진다. 전체 실행 안 프래그먼트
  실패(`FragmentHandledException` — Streamlit 이 이미 그 안에 그렸다)는 적고 카드 없이 멈춘다.
  `SystemExit` · `CancelledError` 도 카드로 받는다 — 두면 회차 스레드가 끝나 세션이 「실행 중」 에
  머문다(`module_runtime` 과 같은 까닭).
- 감싸지 못하는 자리(위젯 콜백 · 프래그먼트만 도는 회차 · `app.py` 의 페이지 앞)는 Streamlit 기본
  오류 상자 그대로이고, 운영 이미지가 그 상자에 오류 종류 이름만 싣는다(`docker/Dockerfile-prod` 의
  `STREAMLIT_CLIENT_SHOW_ERROR_DETAILS=type`).
"""

from __future__ import annotations

import logging
import os
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Final

import streamlit as st
from streamlit.errors import FragmentHandledException
from streamlit.runtime.scriptrunner_utils.exceptions import ScriptControlException

from capa_simulation import alerts, page_failures, settings
from capa_simulation.components.admin_view import admin_notes_visible
from capa_simulation.components.container_start_check import start_check_alert_possible
from capa_simulation.components.diagnostic_copy import (
    ADMIN_DIAGNOSTIC_LABEL,
    diagnostic_text,
    render_diagnostic_copy,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.page_failures import PageFailure

# 카드 칸 key — 한 회차에 카드는 하나다(화면 하나). 화면 확인 스크립트가 이 칸을 오류로 센다.
CARD_KEY: Final = "capa_page_failure"
COPY_KEY: Final = "page_failure"
# 접힌 진단의 key — 이름이 글자 그대로가 아니라(공용 상수) 고정 key 를 단다(`test_popover_keys`).
# 한 회차에 카드는 하나다.
DIAGNOSTIC_KEY: Final = "page_failure_diagnostic"
CARD_ICON: Final = ":material/error:"
HEADLINE: Final = "이 화면에 오류가 났습니다 — 다른 화면은 그대로 쓸 수 있습니다"
ALERT_CODE: Final = "AD-22"
MESSAGE_LIMIT: Final = 200
FRAME_LIMIT: Final = 12
# 관리자 알림 전문에 싣는 최근 실패 수.
RECENT_SHOWN: Final = 5
_LOGGER = logging.getLogger(__name__)
_HERE: Final = os.path.realpath(__file__)


def first_line(exc: BaseException) -> str:
    """예외 글의 첫 줄(`MESSAGE_LIMIT` 자까지). 비면 빈 글자."""
    text = str(exc).strip()
    return text.splitlines()[0][:MESSAGE_LIMIT] if text else ""


def project_frames(exc: BaseException) -> tuple[str, ...]:
    """이 저장소 안 프레임만 `<상대 경로>:<줄> in <함수>` 꼴로(절대 경로 · 가상환경 · 설치 패키지
    없음)."""
    root = Path(os.path.realpath(settings.PROJECT_ROOT))
    frames: list[str] = []
    for frame in traceback.extract_tb(exc.__traceback__):
        try:
            relative = Path(os.path.realpath(frame.filename)).relative_to(root).as_posix()
        except ValueError:
            continue
        # 가상환경 프레임과 이 감싸기 자신의 프레임(늘 같은 줄)은 뺀다.
        if relative.startswith(".venv") or os.path.realpath(frame.filename) == _HERE:
            continue
        frames.append(f"{relative}:{frame.lineno} in {frame.name}")
    return tuple(frames[-FRAME_LIMIT:])


def diagnostic_lines(failure: PageFailure, exc: BaseException) -> list[str]:
    """「관리자용 진단」 의 평문 줄 — 화면 · 오류(종류: 첫 줄) · 참고 번호 · 위치."""
    message = first_line(exc)
    lines = [
        f"화면 · {failure.page or failure.href or '-'}",
        f"오류 · {failure.kind}" + (f": {message}" if message else ""),
        f"참고 번호 · {failure.ref} · {failure.at}",
    ]
    frames = project_frames(exc)
    if frames:
        lines.append("위치")
        lines.extend(f"  {frame}" for frame in frames)
    return lines


def render_page_failure(failure: PageFailure, exc: BaseException) -> None:
    """카드를 지금 자리에 그린다(모듈 설명)."""
    with st.container(key=CARD_KEY):
        st.error(HEADLINE, icon=CARD_ICON)
        st.caption(f"참고 번호 {failure.ref} · {literal_markdown(failure.kind)}")
        if admin_notes_visible():
            lines = diagnostic_lines(failure, exc)
            with st.expander(ADMIN_DIAGNOSTIC_LABEL, key=DIAGNOSTIC_KEY):
                render_diagnostic_copy(diagnostic_text(HEADLINE, lines), key=COPY_KEY)
                st.code("\n".join(lines), language=None)


def _record(page: str, href: str, exc: BaseException) -> PageFailure:
    failure = page_failures.record_failure(page=page, href=href, kind=type(exc).__name__)
    _LOGGER.error("코어 화면 %s 실패 — 참고 번호 %s", href or page, failure.ref, exc_info=exc)
    return failure


def run_core_page(run: Callable[[], None], *, page: str, href: str) -> None:
    """코어 화면을 `run`(보통 `navigation.run`)으로 돌리며 처리 못 한 오류를 카드로 바꾼다.
    `page` · `href` 는 이 화면의 이름 · 주소다(기록 · 알림 「그 화면으로」 — HOME 은 빈 글자).
    처리한 실패는 `st.stop()` 으로 끝난다(모듈 설명 「멈춤으로 끝낸다」)."""
    try:
        run()
    except FragmentHandledException as handled:
        # Streamlit 이 이미 그 프래그먼트 안에 그렸다 — 카드 없이 적는다.
        original = handled.args[0] if handled.args else handled
        _record(page, href, original if isinstance(original, BaseException) else handled)
    except (ScriptControlException, KeyboardInterrupt):
        raise
    # SystemExit · CancelledError 도 받는다 — 두면 회차 스레드가 끝나 세션이 「실행 중」 에 머문다.
    except BaseException as error:
        render_page_failure(_record(page, href, error), error)
    else:
        return
    # 예외 처리 칸 밖에서 멈춘다 — 멈춤 예외에 처리한 오류가 이어 붙지 않게.
    st.stop()


def render_page_failure_alert() -> None:
    """코어 화면 오류 관리자 알림(`AD-22`) — `app.py` 가 회차마다 조건 없이 부른다(모듈 설명).

    `start_check_alert_possible` 이 거짓인 프로세스는 아무것도 쓰지 않고, 참이면 회차마다 이벤트 칸
    한 자리다 — 실패가 없거나 관리자가 아닌 회차는 해소로 부른다. 지문은 프로세스에서 난 (화면, 오류
    종류) 쌍 모두다 — 새 화면 · 새 종류의 실패면 다시 뜨고, 고장 난 한 화면을 여럿이 거듭 열어도
    거듭 뜨지 않는다(건수 · 최근 참고 번호는 글에 싣는다)."""
    if not start_check_alert_possible():
        return
    failures = page_failures.recent_failures()
    if not failures or not admin_notes_visible():
        alerts.state(ALERT_CODE, scope=None, content=None, active=False)
        return
    shown = failures[-RECENT_SHOWN:]
    last = shown[-1]
    lines = " · ".join(
        f"{item.at} 「{item.page}」 {item.kind} 참고 번호 {item.ref}" for item in shown
    )
    alerts.state(
        ALERT_CODE,
        scope=None,
        content=page_failures.failure_pairs(),
        active=True,
        text=f"화면 오류 {page_failures.failure_count()}건 — 「{last.page}」 · {last.kind}",
        full=(
            f"이 서버의 화면에서 처리하지 못한 오류가 났습니다 — {lines}. 원문은 그 화면 "
            "카드의 「관리자용 진단」 과 서버 로그(참고 번호)에 있습니다."
        ),
        # HOME 의 주소는 빈 글자다(기본 화면 — 알림 칸 · 탭 줄이 그 글자로 HOME 을 연다).
        goto=(last.page, last.href) if last.page else None,
    )
