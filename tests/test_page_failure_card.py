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
from capa_simulation.components.diagnostic_copy import ADMIN_DIAGNOSTIC_LABEL

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
    머리 한 줄 · 참고 번호 · 오류 종류. 카드 뒤에는 `st.stop()` 으로 멈춰 감싸기 뒤 꼬리가 돌지
    않는다(`app.py` 는 멈춤 길에서 회차 끝 일을 한다)."""
    app = AppTest.from_function(_crashing_page).run()

    assert not app.exception
    (card,) = app.error
    assert card.value == page_failure_card.HEADLINE
    assert "오류 앞까지 그린 줄" in [str(item.value) for item in app.markdown]
    assert "감싸기 뒤 꼬리" not in [str(item.value) for item in app.markdown]
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

    (box,) = [item for item in app.expander if item.label == ADMIN_DIAGNOSTIC_LABEL]
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

    assert app.error and not [item for item in app.expander if item.label == ADMIN_DIAGNOSTIC_LABEL]
    assert "DEMO 값 없음" not in "\n".join(str(item.value) for item in app.caption)


def _draft_page() -> None:
    import streamlit as st

    from capa_simulation.components.page_failure_card import run_core_page

    @st.fragment
    def broken_part() -> None:
        raise IndexError("DEMO 프래그먼트")

    def body() -> None:
        failure = st.session_state.get("demo_failure")
        if failure == "page":
            raise AttributeError("DEMO 값 없음")
        if failure == "fragment":
            broken_part()
        st.text_input("초안", key="demo_draft")

    run_core_page(body, page="공정 Capa 상세", href="process_capa_detail")


@pytest.mark.parametrize("failure", ["page", "fragment"])
def test_a_failed_run_keeps_unsaved_widget_values_below_it(failure: str) -> None:
    """처리한 실패는 멈춤으로 끝난다 — 정상으로 돌아오면 Streamlit 이 끝까지 돈 회차로 보고 오류
    자리 아래에서 이번에 그리지 못한 위젯의 미저장 값을 지웠다(감싸기 없이 예외가 밖으로 나가던
    꼴은 남겼다). 카드 · 프래그먼트 실패 둘 다 실패한 회차 뒤에도 그 값이 세션에 그대로다."""
    app = AppTest.from_function(_draft_page).run()
    app.text_input(key="demo_draft").set_value("저장 전 초안").run()

    app.session_state["demo_failure"] = failure
    app.run()

    assert len(page_failures.recent_failures()) == 1
    assert app.session_state["demo_draft"] == "저장 전 초안"
    if failure == "page":
        assert not app.exception and len(app.error) == 1
    else:
        # 프래그먼트 실패는 Streamlit 이 그 안에 그린 오류 상자뿐이다 — 카드는 없다.
        assert [item.message for item in app.exception] == ["DEMO 프래그먼트"]
        assert not app.error


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


@pytest.fixture
def start_check_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """시작 점검 결과가 있는 서버(C-DEP) — `AD-22` 를 회차마다 부르는 프로세스."""
    monkeypatch.setattr(page_failure_card, "start_check_alert_possible", lambda: True)


@pytest.mark.parametrize("possible", [True, False], ids=["start-check", "plain"])
def test_the_event_slot_count_does_not_change_with_the_first_failure(
    monkeypatch: pytest.MonkeyPatch, possible: bool
) -> None:
    """이벤트 칸 수는 프로세스 동안 같다 — 다른 세션의 첫 실패가 이 세션의 이벤트 칸 차례(팝업
    호스트 자리)를 밀지 않는다. 시작 점검 판정이 참인 서버는 실패 앞뒤 모두 한 자리, 거짓인
    서버(개발 · 사내 PC · 시험)는 앞뒤 모두 0 이다."""
    monkeypatch.setattr(page_failure_card, "start_check_alert_possible", lambda: possible)
    monkeypatch.setattr(page_failure_card, "admin_notes_visible", lambda: True)
    app = AppTest.from_function(_alert_script).run()
    before = len(app.get("html"))

    page_failures.record_failure(page="Static Capa", href="static_capa", kind="AttributeError")
    app.run()

    assert before == len(app.get("html")) == (1 if possible else 0)
    assert (active_state(app, page_failure_card.ALERT_CODE) is not None) is possible


@pytest.mark.usefixtures("start_check_server")
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


@pytest.mark.usefixtures("start_check_server")
def test_one_broken_screen_opened_again_does_not_pop_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """고장 난 한 화면을 여럿이 거듭 열어도 같은 (화면, 종류)면 지문이 같아 알림창이 거듭 뜨지
    않는다 — 건수 · 최근 참고 번호는 글에 실린다. 다른 화면 · 다른 종류면 새 지문이다."""
    monkeypatch.setattr(page_failure_card, "admin_notes_visible", lambda: True)
    page_failures.record_failure(page="Static Capa", href="static_capa", kind="AttributeError")
    app = AppTest.from_function(_alert_script).run()
    first = active_state(app, page_failure_card.ALERT_CODE)

    latest = page_failures.record_failure(
        page="Static Capa", href="static_capa", kind="AttributeError"
    )
    app.run()
    again = active_state(app, page_failure_card.ALERT_CODE)
    assert first is not None and again is not None
    assert again["fp"] == first["fp"]
    assert again["short"].startswith("화면 오류 2건") and latest.ref in str(again["full"])

    page_failures.record_failure(page="VOC", href="voc", kind="IndexError")
    app.run()
    other = active_state(app, page_failure_card.ALERT_CODE)
    assert other is not None and other["fp"] != first["fp"]


@pytest.mark.usefixtures("start_check_server")
def test_a_broken_home_still_offers_its_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    """HOME 은 기본 화면이라 주소가 빈 글자다 — 그래도 「그 화면으로」 는 HOME 을 가리킨다(빈
    주소로 빼면 줄이 관리자가 지금 보는 화면을 가리켰다)."""
    monkeypatch.setattr(page_failure_card, "admin_notes_visible", lambda: True)
    page_failures.record_failure(page="HOME", href="", kind="KeyError")

    app = AppTest.from_function(_alert_script).run()

    note = active_state(app, page_failure_card.ALERT_CODE)
    assert note is not None and (note["page"], note["href"]) == ("HOME", "")


@pytest.mark.usefixtures("start_check_server")
def test_the_count_and_fingerprint_outlive_the_recent_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """최근 줄은 `RECENT_LIMIT` 건이지만 건수는 거기서 멈추지 않고, 지문은 줄에서 밀려난 (화면,
    종류) 쌍도 든다 — 같은 고장이 줄에서 밀렸다고 다시 뜨지 않는다."""
    monkeypatch.setattr(page_failure_card, "admin_notes_visible", lambda: True)
    page_failures.record_failure(page="VOC", href="voc", kind="IndexError")
    page_failures.record_failure(page="Static Capa", href="static_capa", kind="AttributeError")
    app = AppTest.from_function(_alert_script).run()
    first = active_state(app, page_failure_card.ALERT_CODE)

    for _ in range(page_failures.RECENT_LIMIT):
        page_failures.record_failure(page="Static Capa", href="static_capa", kind="AttributeError")
    app.run()
    later = active_state(app, page_failure_card.ALERT_CODE)

    assert all(item.page == "Static Capa" for item in page_failures.recent_failures())
    assert first is not None and later is not None
    assert later["fp"] == first["fp"]
    assert later["short"].startswith(f"화면 오류 {page_failures.RECENT_LIMIT + 2}건")
