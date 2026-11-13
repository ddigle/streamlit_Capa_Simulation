# Purpose: Admin 토큰 넣기의 관리자 문 · 비밀 칸 뒷정리 · 거절과 만료 관리자 알림(AD-11)을 본다.

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alert_marks import active_state, states
from streamlit.testing.v1 import AppTest
from test_bdq_token import ACCOUNT, FAKE_TOKEN, fake_jwt

from capa_simulation import alerts
from capa_simulation import settings as app_settings
from capa_simulation.components import bdq_token_admin, container_start_check, sso_identity
from capa_simulation.io import bdq_token
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.navigation import ADMIN_AREA
from capa_simulation.page_tabs_state import tab_label

CHECK_SCRIPT = """
from capa_simulation.components.container_start_check import render_container_start_check

render_container_start_check()
"""
ALERT_SCRIPT = """
from capa_simulation.components.container_start_check import render_token_alert

render_token_alert()
"""
CLOSE_SCRIPT = """
import streamlit as st

from capa_simulation.components import bdq_token_admin
from capa_simulation.components.container_start_check import render_container_start_check

st.button("닫기", key="test_close_token_dialog", on_click=bdq_token_admin.HOST.close)
render_container_start_check()
"""
INSTALL_SCRIPT = f"""
import streamlit as st

from capa_simulation.components.bdq_token_admin import install_from_dialog

st.text(install_from_dialog({FAKE_TOKEN!r}))
"""
CODE = bdq_token_admin.EXPIRY_ALERT_CODE


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """C-DEP 서버 꼴 — 시작 점검 결과 파일 · 계정 · tmp 토큰 폴더. 돌려주는 값은 토큰 파일 자리."""
    path = tmp_path / "container_start.json"
    steps = {name: {"status": "ok", "reason": "정상"} for name in report_contract.STEPS}
    path.write_text(
        json.dumps(
            {
                "version": report_contract.REPORT_VERSION,
                "written_at": "2026-11-13T00:00:00+09:00",
                "steps": steps,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_settings, "CONTAINER_START_REPORT_PATH", path)
    monkeypatch.setenv(report_contract.BDQ_USER_NAME_ENV, ACCOUNT)
    folder = tmp_path / "credential"
    monkeypatch.setattr(bdq_token, "CREDENTIAL_DIR", folder)
    yield folder / f"bigdataquery.token.{ACCOUNT}"


def _admin(monkeypatch: pytest.MonkeyPatch, *, admin: bool = True) -> None:
    monkeypatch.setattr(sso_identity, "viewer_is_admin", lambda: admin)


def _open(app: AppTest) -> AppTest:
    return app.button(key=bdq_token_admin.OPEN_KEY).click().run()


def _submit(app: AppTest, value: str) -> AppTest:
    app.text_input(key=bdq_token_admin.INPUT_KEY).set_value(value)
    submit = next(button for button in app.button if button.label == bdq_token_admin.APPLY_LABEL)
    return submit.click().run()


def _dialog_open(app: AppTest) -> bool:
    return any(item.key == bdq_token_admin.INPUT_KEY for item in app.text_input)


def _texts(app: AppTest) -> str:
    return " ".join(
        str(getattr(element, "value", "")) for element in [*app.caption, *app.error, *app.markdown]
    )


def test_someone_who_is_not_an_administrator_sees_only_the_value_line(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _admin(monkeypatch, admin=False)

    app = AppTest.from_string(CHECK_SCRIPT).run()

    assert not app.exception
    assert not any(button.key == bdq_token_admin.OPEN_KEY for button in app.button)
    assert any(
        "지금 토큰" in caption.value and "파일 없음" in caption.value for caption in app.caption
    )


def test_an_administrator_puts_a_token_and_nothing_of_it_stays_in_the_session(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _admin(monkeypatch)
    app = AppTest.from_string(CHECK_SCRIPT).run()
    opener = app.button(key=bdq_token_admin.OPEN_KEY)
    assert opener.help == bdq_token_admin.OPEN_HELP and not opener.disabled

    app = _open(app)
    assert _dialog_open(app)
    app = _submit(app, FAKE_TOKEN)

    assert not app.exception
    assert server.read_text(encoding="utf-8") == FAKE_TOKEN
    assert not _dialog_open(app)
    assert FAKE_TOKEN not in str(app.session_state.filtered_state)
    assert bdq_token_admin.INPUT_KEY not in app.session_state
    assert FAKE_TOKEN not in _texts(app)
    shown = [caption.value for caption in app.caption if "지금 토큰" in caption.value]
    assert shown and "파일 · 수정" in shown[0] and "만료 모름" in shown[0]


def test_a_refused_value_keeps_the_dialog_without_keeping_the_value(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _admin(monkeypatch)
    app = _open(AppTest.from_string(CHECK_SCRIPT).run())

    app = _submit(app, "FAKE-short")

    assert not app.exception
    assert _dialog_open(app)
    errors = [error.value for error in app.error]
    assert len(errors) == 1 and "16바이트보다 짧아" in errors[0]
    assert "FAKE-short" not in errors[0] and "10" not in errors[0]
    assert "FAKE-short" not in str(app.session_state.filtered_state)
    assert not server.exists()


def test_closing_the_dialog_drops_its_input(server: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """닫기(X · 바깥 · Esc — 팝업의 `on_dismiss` 는 `HOST.close`)는 그 팝업의 입력 칸 값을 지운다.
    AppTest 는 팝업 닫기를 보낼 수 없어 같은 콜백을 단 단추로 누른다."""
    _admin(monkeypatch)
    app = _open(AppTest.from_string(CLOSE_SCRIPT).run())
    app.text_input(key=bdq_token_admin.INPUT_KEY).set_value(FAKE_TOKEN)

    app = app.button(key="test_close_token_dialog").click().run()

    assert not _dialog_open(app)
    assert FAKE_TOKEN not in str(app.session_state.filtered_state)
    assert not server.exists()


def test_the_submit_checks_the_administrator_again(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """그려진 단추를 믿지 않는다 — 누른 회차에 관리자가 아니면 쓰지 않는다. 그 회차에는 단추 ·
    팝업도 서지 않고, 넣기 자체도 신원을 다시 본다."""
    _admin(monkeypatch)
    app = _open(AppTest.from_string(CHECK_SCRIPT).run())
    _admin(monkeypatch, admin=False)

    app = _submit(app, FAKE_TOKEN)

    assert not app.exception and not _dialog_open(app)
    assert not server.exists()
    direct = AppTest.from_string(INSTALL_SCRIPT).run()
    assert [text.value for text in direct.text] == [bdq_token_admin.NOT_ADMIN_MESSAGE]
    assert not server.exists()


def test_the_opener_is_locked_when_the_package_reads_an_environment_token(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _admin(monkeypatch)
    monkeypatch.setenv(bdq_token.LOGIN_TOKEN_ENV, "FAKE-env-token-0000000000")

    app = AppTest.from_string(CHECK_SCRIPT).run()

    opener = app.button(key=bdq_token_admin.OPEN_KEY)
    assert opener.disabled and opener.help is not None
    assert bdq_token.LOGIN_TOKEN_ENV in opener.help and "FAKE-env" not in opener.help
    assert any(
        "환경변수" in caption.value for caption in app.caption if "지금 토큰" in caption.value
    )


def test_the_value_line_and_the_copy_text_show_a_readable_expiry(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _admin(monkeypatch, admin=False)
    expires = datetime.now(timezone.utc) + timedelta(days=2)
    server.parent.mkdir(parents=True)
    server.write_text(fake_jwt(expires), encoding="utf-8")

    line = bdq_token_admin.token_line()

    assert "만료 " + expires.astimezone().strftime("%Y-%m-%d %H:%M") in line
    assert "지남" not in line
    assert fake_jwt(expires) not in line


def _token(server: Path, expires: datetime | None) -> None:
    server.parent.mkdir(parents=True, exist_ok=True)
    server.write_text(FAKE_TOKEN if expires is None else fake_jwt(expires), encoding="utf-8")


def test_the_expiry_alert_rises_an_hour_before_for_the_administrator(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _admin(monkeypatch)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).replace(microsecond=0)
    _token(server, expires)

    app = AppTest.from_string(ALERT_SCRIPT).run()

    note = active_state(app, CODE)
    assert note is not None
    assert note["level"] == "action"
    assert note["short"] == (
        f"BigDataQuery 로그인 토큰 만료 {expires.astimezone().strftime('%m-%d %H:%M')} — "
        "새 토큰을 넣으세요"
    )
    assert len(note["short"]) <= alerts.SHORT_LIMIT
    assert "「토큰 넣기」" in note["full"] and report_contract.BDQ_TOKEN_ENV in note["full"]
    assert (note["page"], note["href"]) == (tab_label(ADMIN_AREA), ADMIN_AREA.href)

    # 새 토큰(만료가 1시간 밖)을 넣으면 해소로 닫힌다.
    assert bdq_token.install_token(fake_jwt(expires + timedelta(days=1))).status == "written"
    app.run()
    assert active_state(app, CODE) is None
    assert [item["active"] for item in states(app, CODE)][-1] is False


@pytest.mark.parametrize(
    ("admin", "expires_in"),
    [(True, timedelta(hours=2)), (True, None), (False, timedelta(minutes=10))],
    ids=["1시간 밖", "만료 모름", "관리자 아님"],
)
def test_the_expiry_alert_stays_down(
    server: Path, monkeypatch: pytest.MonkeyPatch, admin: bool, expires_in: timedelta | None
) -> None:
    _admin(monkeypatch, admin=admin)
    _token(server, None if expires_in is None else datetime.now(timezone.utc) + expires_in)

    app = AppTest.from_string(ALERT_SCRIPT).run()

    assert active_state(app, CODE) is None
    assert [item["active"] for item in states(app, CODE)] == [False]


def test_a_past_expiry_still_tells_the_administrator(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _admin(monkeypatch)
    _token(server, datetime.now(timezone.utc) - timedelta(hours=5))

    note = active_state(AppTest.from_string(ALERT_SCRIPT).run(), CODE)

    assert note is not None
    assert "지남" in bdq_token_admin.token_line()


def test_nothing_is_written_off_the_cd_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """결과 파일이 없는 서버 — 만료 알림도 Streamlit 호출이 없다."""
    _admin(monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(alerts, "state", lambda *args, **_kwargs: calls.append(args[0]))

    container_start_check.render_token_alert()

    assert calls == []
