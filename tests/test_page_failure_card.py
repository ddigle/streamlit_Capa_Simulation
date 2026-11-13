# Purpose: 코어 화면 감싸기가 처리 못 한 오류를 카드 · 참고 번호 · 알림 AD-22 로 바꾸는지 시험한다.

"""코어 화면 오류 카드(`components/page_failure_card.py` — 2026-11-14 「앱 대신 뜨는 화면」 보드
카드 p2-rare · d12 (가)). 이 모듈의 시험은 감싸기를 걷지 않는다(`conftest` 의 기본은 걷는다)."""

from __future__ import annotations

import pytest
from alert_marks import active_state, states
from streamlit.runtime.scriptrunner_utils.exceptions import StopException
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts, page_failures
from capa_simulation.components import page_failure_card

pytestmark = pytest.mark.page_failure_card


def _crashing_page() -> None:
    import streamlit as st

    from capa_simulation.components.page_failure_card import run_core_page

    def body() -> None:
        st.write("오류 앞까지 그린 줄")
        raise AttributeError("DEMO 값 없음")

    run_core_page(body, page="공정 Capa 상세", href="process_capa_detail")
    st.write("감싸기 뒤 꼬리")


def test_an_unhandled_error_becomes_a_card_with_a_reference_number() -> None:
    """처리 못 한 오류는 Streamlit 기본 오류 상자(경로 · traceback) 대신 그 화면 안 카드 하나다 —
    머리 한 줄 · 참고 번호 · 오류 종류. 감싸기 뒤 꼬리(앱 회차 끝)는 그대로 돈다."""
    app = AppTest.from_function(_crashing_page).run()

    assert not app.exception
    (card,) = app.error
    assert card.value == page_failure_card.HEADLINE
    assert "오류 앞까지 그린 줄" in [str(item.value) for item in app.markdown]
    assert "감싸기 뒤 꼬리" in [str(item.value) for item in app.markdown]
    (failure,) = page_failures.recent_failures()
    assert (failure.page, failure.href, failure.kind) == (
        "공정 Capa 상세",
        "process_capa_detail",
        "AttributeError",
    )
    assert len(failure.ref) == 8 and failure.ref.upper() == failure.ref
    (caption,) = [item for item in app.caption if "참고 번호" in str(item.value)]
    assert caption.value == f"참고 번호 {failure.ref} · AttributeError"


def test_the_admin_diagnostic_carries_the_message_and_repository_frames() -> None:
    """관리자 몫(통합인증이 꺼진 서버는 누구에게나)에는 접힌 「관리자용 진단」 이 첫 줄 · 이 저장소
    안 프레임 · 복사 단추를 싣는다 — C-DEP 에는 로그가 없어 원문을 보는 자리다."""
    app = AppTest.from_function(_crashing_page).run()

    (box,) = [item for item in app.expander if item.label == page_failure_card.DIAGNOSTIC_LABEL]
    (code,) = box.code
    assert "오류 · AttributeError: DEMO 값 없음" in code.value
    # 감싸기 자신의 프레임(늘 같은 줄)과 저장소 밖 경로는 싣지 않는다.
    assert "page_failure_card.py" not in code.value
    assert "/home/" not in code.value and "site-packages" not in code.value


def test_frames_are_repository_relative_without_the_wrapper() -> None:
    """프레임은 이 저장소 안 것만 상대 경로로 — 감싸기 자신 · 설치 패키지 · 절대 경로는 없다."""
    try:
        raise ValueError("DEMO")
    except ValueError as error:
        frames = page_failure_card.project_frames(error)
    assert frames and all(not frame.startswith("/") for frame in frames)
    assert frames[0].startswith("tests/test_page_failure_card.py:")


def test_a_viewer_who_is_not_the_admin_sees_only_the_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    """통합인증이 켜진 서버의 관리자가 아닌 사람은 오류 종류 이름 · 참고 번호만 본다(d12 (가))."""
    monkeypatch.setattr(page_failure_card, "admin_notes_visible", lambda: False)

    app = AppTest.from_function(_crashing_page).run()

    assert app.error and not [
        item for item in app.expander if item.label == page_failure_card.DIAGNOSTIC_LABEL
    ]
    assert "DEMO 값 없음" not in "\n".join(str(item.value) for item in app.caption)


@pytest.mark.parametrize("control", [StopException(), KeyboardInterrupt()])
def test_control_exceptions_pass_through(control: BaseException) -> None:
    """`st.stop()` · `st.rerun()`(Streamlit 제어 예외)와 `KeyboardInterrupt` 는 오류가 아니다 —
    그대로 다시 던지고 적지 않는다."""

    def body() -> None:
        raise control

    with pytest.raises(type(control)):
        page_failure_card.run_core_page(body, page="HOME", href="")
    assert page_failures.recent_failures() == ()


def _alert_script() -> None:
    from capa_simulation.components.page_failure_card import render_page_failure_alert

    render_page_failure_alert()


def test_no_failure_writes_no_marker() -> None:
    """프로세스에서 아직 실패가 없으면 표지를 쓰지 않는다 — 개발 · 시험의 요소 순번이 그대로다."""
    app = AppTest.from_function(_alert_script).run()

    assert not states(app, page_failure_card.ALERT_CODE)


@pytest.mark.parametrize("admin", [True, False], ids=["admin", "user"])
def test_a_failure_is_told_to_the_admin_with_its_reference(
    monkeypatch: pytest.MonkeyPatch, admin: bool
) -> None:
    """오류가 난 탭은 관리자의 탭이 아니다 — 관리자 몫 회차가 프로세스 기록에서 `AD-22` 를 낸다.
    「그 화면으로」 는 그 화면이고, 글에는 본문 없이 화면 · 종류 · 참고 번호만 있다."""
    failure = page_failures.record_failure(
        page="공정 Capa 상세", href="process_capa_detail", kind="AttributeError"
    )
    monkeypatch.setattr(page_failure_card, "admin_notes_visible", lambda: admin)

    app = AppTest.from_function(_alert_script).run()

    assert len(states(app, page_failure_card.ALERT_CODE)) == 1
    note = active_state(app, page_failure_card.ALERT_CODE)
    if not admin:
        assert note is None
        return
    assert note is not None
    assert note["short"] == "화면 오류 1건 — 「공정 Capa 상세」 · AttributeError"
    assert failure.ref in str(note["full"])
    assert (note["page"], note["href"]) == ("공정 Capa 상세", "process_capa_detail")
    assert alerts.REGISTRY[page_failure_card.ALERT_CODE].level == "error"
