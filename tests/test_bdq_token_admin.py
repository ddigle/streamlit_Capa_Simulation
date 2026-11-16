# Purpose: Admin 토큰 넣기 · 지금 토큰 줄 · 만료 알림(AD-11)과 그 물러서기를 본다.

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alert_marks import active_state, flashed, states
from streamlit.testing.v1 import AppTest
from test_bdq_token import ACCOUNT, FAKE_TOKEN, FAR_EXPIRY, deeply_nested_jwt, fake_jwt

from capa_simulation import alerts
from capa_simulation import settings as app_settings
from capa_simulation.components import bdq_token_admin, container_start_check, sso_identity
from capa_simulation.components.diagnostic_copy import COMPONENT_KEY_PREFIX
from capa_simulation.io import bdq_token
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.navigation import ADMIN_AREA
from capa_simulation.page_tabs_state import tab_label

# 화면 시각의 기준 — 서버 시각대가 무엇이든 한국 시각(+09:00)이다(`korea_time`).
SEOUL = timezone(timedelta(hours=9))
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


def _install_script(value: str) -> str:
    """넣기 한 번 + 그 알림창 — 돌려준 거절 글(없으면 `None`)을 글로 그린다."""
    return f"""
import streamlit as st

from capa_simulation.components.bdq_token_admin import FLASH_KEY, install_from_dialog
from capa_simulation.components.flash import render_flash

st.text(str(install_from_dialog({value!r})))
render_flash(FLASH_KEY)
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


@pytest.fixture
def east_clock() -> Iterator[None]:
    """서버 시각대를 UTC 보다 9시간 앞(서울과 같은 차)으로 바꿔 끼우고 끝에 되돌린다. 시각대 db 가
    없어도 서는 POSIX 꼴이다. 바꿔 끼울 수 없는 OS(Windows)는 건너뛴다."""
    tzset = getattr(time, "tzset", None)
    if tzset is None:
        pytest.skip("시각대를 바꿔 끼울 수 없는 OS")
    before = os.environ.get("TZ")
    os.environ["TZ"] = "KST-9"
    tzset()
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = before
        tzset()


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
    popup = [item.value for item in flashed(app, "success")]
    assert popup == ["BigDataQuery 토큰을 넣었습니다 · 만료 모름"]
    assert len(popup[0]) <= alerts.SHORT_LIMIT


def test_a_refused_value_keeps_the_dialog_without_keeping_the_value(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _admin(monkeypatch)
    app = _open(AppTest.from_string(CHECK_SCRIPT).run())

    app = _submit(app, "FAKE-short")

    assert not app.exception
    assert _dialog_open(app)
    errors = [error.value for error in app.error]
    assert errors == ["넣지 않았습니다 — 16바이트보다 짧아 토큰이 아닌 값으로 봅니다"]
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

    assert "만료 " + expires.astimezone(SEOUL).strftime("%Y-%m-%d %H:%M") in line
    assert "지남" not in line
    assert fake_jwt(expires) not in line


def test_the_copy_text_carries_the_value_line(
    server: Path, monkeypatch: pytest.MonkeyPatch, diagnostic_copies: dict[str, str]
) -> None:
    """복사 글(리뷰로 옮기는 글)에도 「지금 토큰」 줄이 들어가고 토큰 글은 없다."""
    _admin(monkeypatch, admin=False)
    token = fake_jwt(datetime.now(timezone.utc) + timedelta(days=2))
    server.parent.mkdir(parents=True)
    server.write_text(token, encoding="utf-8")

    app = AppTest.from_string(CHECK_SCRIPT).run()

    assert not app.exception
    text = diagnostic_copies[f"{COMPONENT_KEY_PREFIX}{container_start_check.COPY_KEY}"]
    lines = [line for line in text.splitlines() if line.startswith("지금 토큰")]
    assert len(lines) == 1 and "파일 · 수정" in lines[0] and "만료 " in lines[0]
    assert "만료 모름" not in lines[0]
    assert token not in text


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
        f"BigDataQuery 로그인 토큰 만료 {expires.astimezone(SEOUL).strftime('%m-%d %H:%M')} — "
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


def test_a_deeply_nested_token_leaves_every_screen_standing(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """만료를 읽다 재귀 한도를 넘는 토큰이어도 모든 화면 회차의 알림 자리(`render_token_alert`)와
    Admin 펼침이 끝까지 돈다 — 만료는 모름이고 알림은 해소다."""
    _admin(monkeypatch)
    server.parent.mkdir(parents=True)
    server.write_text(deeply_nested_jwt(), encoding="utf-8")

    alert = AppTest.from_string(ALERT_SCRIPT).run()
    check = AppTest.from_string(CHECK_SCRIPT).run()

    assert not alert.exception and not check.exception
    assert [item["active"] for item in states(alert, CODE)] == [False]
    assert any(
        "지금 토큰" in caption.value and "만료 모름" in caption.value for caption in check.caption
    )


def test_a_failure_reading_the_token_falls_back_without_stopping_the_screen(
    server: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """지금 토큰을 읽다 무엇이 나도 값 줄은 「확인하지 못함」, 만료 알림은 해소로 그 자리를 쓰고,
    넣기는 쓴 뒤 넣음으로 끝난다."""
    _admin(monkeypatch)

    def broken(_environ: object = None) -> bdq_token.TokenState:
        raise RuntimeError("읽다 남")

    monkeypatch.setattr(bdq_token, "current_token", broken)

    alert = AppTest.from_string(ALERT_SCRIPT).run()
    check = AppTest.from_string(CHECK_SCRIPT).run()
    direct = AppTest.from_string(_install_script(FAKE_TOKEN)).run()

    assert not alert.exception and not check.exception and not direct.exception
    assert [item["active"] for item in states(alert, CODE)] == [False]
    assert any(
        "지금 토큰" in caption.value and "확인하지 못함" in caption.value
        for caption in check.caption
    )
    assert [text.value for text in direct.text] == ["None"]
    assert server.read_text(encoding="utf-8") == FAKE_TOKEN
    assert [item.value for item in flashed(direct, "success")] == [
        "BigDataQuery 토큰을 넣었습니다 · 만료 모름"
    ]


def test_a_far_expiry_is_shown_as_unknown_east_of_utc(
    server: Path, monkeypatch: pytest.MonkeyPatch, east_clock: None
) -> None:
    """「만료 없음」 자리표시(9999-12-31T23:59:59Z)는 UTC 보다 앞선 시각대로 옮길 수 없다 — 넣기는
    넣음으로 끝나고 값 줄은 「만료 모름」 이다. 시각대로 못 옮기는 시각은 「알 수 없음」 이다."""
    _admin(monkeypatch)

    direct = AppTest.from_string(_install_script(fake_jwt(FAR_EXPIRY))).run()

    assert not direct.exception
    assert [text.value for text in direct.text] == ["None"]
    assert server.read_text(encoding="utf-8") == fake_jwt(FAR_EXPIRY)
    assert [item.value for item in flashed(direct, "success")] == [
        "BigDataQuery 토큰을 넣었습니다 · 만료 모름"
    ]
    assert "만료 모름" in bdq_token_admin.token_line()
    edge = datetime.max.replace(tzinfo=timezone.utc)
    line = bdq_token_admin.token_line(
        bdq_token.TokenState("file", modified_at=edge, expires_at=edge)
    )
    assert line == f"{bdq_token_admin.TOKEN_LINE_LABEL} · 파일 · 수정 알 수 없음 · 만료 알 수 없음"


def test_nothing_is_written_off_the_cd_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """결과 파일이 없는 서버 — 만료 알림도 Streamlit 호출이 없다."""
    _admin(monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(alerts, "state", lambda *args, **_kwargs: calls.append(args[0]))

    container_start_check.render_token_alert()

    assert calls == []


def test_the_retired_token_alert_numbers_stay_empty() -> None:
    """토큰 알림은 `AD-10` · `AD-11` · `AD-23`(자동 로그인 멈춤) 셋이다 — 걷은 `AD-17`(자동 갱신
    멈춤 · 실패) · `AD-18`(갱신 토큰 80일)은 등록부에 없고 다시 쓰지 않는다(`alerts` 모듈 설명)."""
    for code in ("AD-10", "AD-11", "AD-23"):
        assert alerts.REGISTRY[code].kind == "state"
    assert "AD-17" not in alerts.REGISTRY and "AD-18" not in alerts.REGISTRY
