# Purpose: Admin 「BDQ 자동 로그인」 폼 — 넣기 · 실패 · 지우기 · 문지기 · 세션에 비밀 없음을 본다.

"""`components/bdq_login_admin.py` 시험.

로그인은 진짜 하위 프로세스가 가짜 `bigdataquery`(`tests/fixtures/bdq_fake/`)를 불러 돈다. 장면마다
`login()` 이 불린 수를 센다(`FakeBdq.logins`) — 폼 제출 한 번에 시도 한 번, 다시 그리기는 0 번이다.
저장은 가짜 S3 다. 계정은 `CAPA_BDQ_USER_NAME` 과 다른 합성 ID, 비밀번호는 카나리아 글이고 세션 ·
화면 · 감사 줄 어디에도 없어야 한다.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from alert_marks import GOTO_PRELUDE, GOTO_PRESS_KEY, box_expanded, flashed
from bdq_login_support import (
    ACCOUNT,
    ADMIN_ID,
    OTHER_ACCOUNT,
    PASSWORD,
    WRONG_PASSWORD,
    FakeBdq,
    requests_on,
    running_mock,
    switch_on,
    target_of,
    use_fake_bdq,
)
from s3_mock_store import MockStore
from streamlit.testing.v1 import AppTest

from capa_simulation.audit import recorder
from capa_simulation.components import bdq_login_admin, sso_identity
from capa_simulation.components.paste_form import PASTE_CONFIRM_WHY
from capa_simulation.io import bdq_login
from capa_simulation.io import bdq_login_store as login_store
from capa_simulation.io.bdq_login_store import LoginSecret
from capa_simulation.io.container_start_report import BDQ_LOGIN_LABEL, BDQ_USER_NAME_ENV
from capa_simulation.io.object_storage import MODE_ENV
from capa_simulation.io.s3_small import S3Target

SCRIPT = """
from capa_simulation.components.bdq_login_admin import render_bdq_login_admin

render_bdq_login_admin()
"""
# 한 회차에 두 번 누른 꼴 — 겹쳐 온 둘째 누름(같은 값 · 폼이 비운 빈 값)이 첫 시도의 창 안에 닿는다.
DOUBLE_SCRIPT = f"""
import streamlit as st

from capa_simulation.components import bdq_login_admin
from capa_simulation.components.flash import render_flash

answers = [
    bdq_login_admin.submit_login({ACCOUNT!r}, {WRONG_PASSWORD!r}),
    bdq_login_admin.submit_login({ACCOUNT!r}, {WRONG_PASSWORD!r}),
    bdq_login_admin.submit_login("", ""),
]
st.text(repr(answers))
render_flash(bdq_login_admin.FLASH_KEY)
"""
# 로그인 하위 프로세스까지 기다리는 회차의 마감(초).
LOGIN_RUN = 120
LAST = bdq_login_admin.LAST_LABEL


@pytest.fixture()
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeBdq:
    return use_fake_bdq(monkeypatch, tmp_path)


@pytest.fixture()
def login_s3(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[MockStore, S3Target]]:
    with running_mock() as (mock, endpoint):
        target = target_of(mock, endpoint)
        monkeypatch.setattr(login_store, "app_target", lambda: target)
        yield mock, target


@pytest.fixture()
def server(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> tuple[MockStore, S3Target, str]:
    """C-DEP 꼴 — `managed` + 키 · 관리자 회차 · 요청자 계정은 저장 계정과 다른 이름."""
    mock, target = login_s3
    key = switch_on(monkeypatch)
    monkeypatch.setenv(BDQ_USER_NAME_ENV, "demo_env_user")
    _admin(monkeypatch)
    return mock, target, key


def _admin(monkeypatch: pytest.MonkeyPatch, *, admin: bool = True) -> None:
    monkeypatch.setattr(sso_identity, "viewer_is_admin", lambda: admin)
    monkeypatch.setattr(
        sso_identity, "verified_identity", lambda: SimpleNamespace(loginid=ADMIN_ID)
    )


def _submit(app: AppTest, account: str, password: str) -> AppTest:
    app.text_input(key=bdq_login_admin.ACCOUNT_KEY).set_value(account)
    app.text_input(key=bdq_login_admin.PASSWORD_KEY).set_value(password)
    button = next(item for item in app.button if item.label == bdq_login_admin.APPLY_LABEL)
    return button.click().run(timeout=LOGIN_RUN)


def _captions(app: AppTest) -> list[str]:
    return [str(caption.value) for caption in app.caption]


def _status(app: AppTest) -> str:
    return next(text for text in _captions(app) if text.startswith(bdq_login_admin.STATUS_LABEL))


def _shown_everywhere(app: AppTest) -> str:
    """화면 글 · 알림 표지 · 세션 — 비밀이 새는지 훑는 자리 전부."""
    parts = [
        *_captions(app),
        *(str(item.value) for item in app.error),
        *(str(item.value) for item in app.markdown),
        *(json.dumps(item.note, ensure_ascii=False) for item in flashed(app)),
        str(app.session_state.filtered_state),
    ]
    return "\n".join(parts)


def _no_secret_left(app: AppTest, *values: str) -> None:
    for key in (bdq_login_admin.ACCOUNT_KEY, bdq_login_admin.PASSWORD_KEY):
        assert key not in app.session_state or app.session_state[key] == ""
    everything = _shown_everywhere(app)
    for value in values:
        assert value not in everything


def _object(mock: MockStore) -> dict[str, object] | None:
    with mock.lock:
        body = mock.objects.get(login_store.OBJECT_KEY)
    if body is None:
        return None
    data = json.loads(body)
    assert isinstance(data, dict)
    return data


def _save(target: S3Target, key: str, account: str = OTHER_ACCOUNT) -> login_store.StoredLogin:
    written = login_store.save_login(target, key.encode(), LoginSecret(account, PASSWORD), "zz.adm")
    assert written.ok and written.stored is not None
    return written.stored


# --- 서는 자리 -------------------------------------------------------------------------------


def test_the_box_stands_only_for_an_administrator_on_a_managed_server_with_a_key(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    mock, _ = login_s3
    _admin(monkeypatch)
    nothing = AppTest.from_string(SCRIPT).run()
    assert not nothing.exception
    assert box_expanded(nothing, bdq_login_admin.EXPANDER_KEY) is None and not nothing.text_input

    monkeypatch.setenv(MODE_ENV, "managed")
    no_key = AppTest.from_string(SCRIPT).run()
    assert box_expanded(no_key, bdq_login_admin.EXPANDER_KEY) is None and not no_key.text_input

    switch_on(monkeypatch)
    _admin(monkeypatch, admin=False)
    not_admin = AppTest.from_string(SCRIPT).run()
    assert box_expanded(not_admin, bdq_login_admin.EXPANDER_KEY) is None
    assert not not_admin.text_input

    _admin(monkeypatch)
    shown = AppTest.from_string(SCRIPT).run()
    assert not shown.exception
    assert box_expanded(shown, bdq_login_admin.EXPANDER_KEY) is not None
    assert [box.label for box in shown.main.status] == [BDQ_LOGIN_LABEL]
    keys = [item.key for item in shown.text_input]
    assert keys == [bdq_login_admin.ACCOUNT_KEY, bdq_login_admin.PASSWORD_KEY]
    assert shown.text_input(key=bdq_login_admin.PASSWORD_KEY).proto.type == 1  # PASSWORD
    assert _status(shown) == f"{bdq_login_admin.STATUS_LABEL} · {bdq_login_admin.NONE_WORD}"
    assert not shown.checkbox and fake.logins() == 0


# --- 넣기 ---------------------------------------------------------------------------------


def test_a_right_login_is_saved_announced_and_leaves_no_secret(
    server: tuple[MockStore, S3Target, str], fake: FakeBdq
) -> None:
    mock, _, _ = server
    app = AppTest.from_string(SCRIPT).run()

    app = _submit(app, f"  {ACCOUNT} ", PASSWORD)

    assert not app.exception
    assert fake.logins() == 1
    stored = _object(mock)
    assert stored is not None and stored["state"] == "ok" and stored["entered_by"] == "de"
    popup = [item.value for item in flashed(app, "success")]
    assert len(popup) == 1 and popup[0].startswith("BigDataQuery 로그인 됨 · 남은 7시간")
    status = _status(app)
    assert status.startswith(f"{bdq_login_admin.STATUS_LABEL} · {bdq_login_admin.OK_WORD} · ")
    assert "넣은 사람 de" in status
    assert any(text.startswith(bdq_login_admin.LAST_LABEL) for text in _captions(app))
    assert login_store.effective_account() == ACCOUNT
    _no_secret_left(app, ACCOUNT, PASSWORD)

    again = app.run(timeout=LOGIN_RUN)
    assert fake.logins() == 1
    _no_secret_left(again, ACCOUNT, PASSWORD)


def test_a_failed_login_saves_nothing_and_keeps_what_was_there(
    server: tuple[MockStore, S3Target, str], fake: FakeBdq
) -> None:
    mock, target, key = server
    _save(target, key)
    before = _object(mock)
    app = AppTest.from_string(SCRIPT).run()

    app = _submit(app, ACCOUNT, WRONG_PASSWORD)

    assert not app.exception
    assert fake.logins() == 1
    assert _object(mock) == before
    assert [str(item.value) for item in app.error] == ["로그인 실패 — 저장 안 함"]
    assert [item.value for item in flashed(app, "error")] == ["로그인 실패 — 저장 안 함"]
    assert login_store.effective_account() == OTHER_ACCOUNT
    assert _status(app).startswith(f"{bdq_login_admin.STATUS_LABEL} · {bdq_login_admin.OK_WORD}")
    _no_secret_left(app, ACCOUNT, WRONG_PASSWORD, OTHER_ACCOUNT)
    assert fake.logins() == 1


@pytest.mark.parametrize(
    ("scene", "line"),
    [
        ("connection", "서버에 닿지 못함 — 저장 안 함"),
        ("import_fails", "패키지 없음 — 저장 안 함"),
        ("time_raises", "로그인 확인 못 함(남은 시간 모름) — 저장 안 함"),
        ("time_short", "로그인 확인 못 함(남은 시간 7시간 이하) — 저장 안 함"),
    ],
)
def test_a_login_that_could_not_be_judged_says_so_and_saves_nothing(
    server: tuple[MockStore, S3Target, str],
    fake: FakeBdq,
    monkeypatch: pytest.MonkeyPatch,
    scene: str,
    line: str,
) -> None:
    mock, _, _ = server
    monkeypatch.setenv("FAKE_BDQ_SCENE", scene)
    app = _submit(AppTest.from_string(SCRIPT).run(), ACCOUNT, PASSWORD)

    assert not app.exception
    assert [str(item.value) for item in app.error] == [line]
    assert _object(mock) is None
    assert fake.logins() == (0 if scene == "import_fails" else 1)
    _no_secret_left(app, ACCOUNT, PASSWORD)


def test_blank_values_are_refused_without_a_login(
    server: tuple[MockStore, S3Target, str], fake: FakeBdq
) -> None:
    app = _submit(AppTest.from_string(SCRIPT).run(), ACCOUNT, "")

    assert [str(item.value) for item in app.error] == [bdq_login_admin.BLANK_MESSAGE]
    assert fake.logins() == 0
    _no_secret_left(app, ACCOUNT)


def test_a_viewer_who_is_no_longer_an_administrator_gets_no_login(
    server: tuple[MockStore, S3Target, str], fake: FakeBdq, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock, _, _ = server
    app = AppTest.from_string(SCRIPT).run()
    app.text_input(key=bdq_login_admin.ACCOUNT_KEY).set_value(ACCOUNT)
    app.text_input(key=bdq_login_admin.PASSWORD_KEY).set_value(PASSWORD)
    button = next(item for item in app.button if item.label == bdq_login_admin.APPLY_LABEL)
    _admin(monkeypatch, admin=False)

    app = button.click().run(timeout=LOGIN_RUN)

    assert not app.exception
    assert fake.logins() == 0 and _object(mock) is None
    assert box_expanded(app, bdq_login_admin.EXPANDER_KEY) is None
    assert PASSWORD not in str(app.session_state.filtered_state)


def test_the_submit_checks_the_administrator_again(
    server: tuple[MockStore, S3Target, str], fake: FakeBdq, monkeypatch: pytest.MonkeyPatch
) -> None:
    """그려진 폼을 믿지 않는다 — 누른 회차의 신원으로 다시 본다."""
    _admin(monkeypatch, admin=False)
    script = f"""
import streamlit as st

from capa_simulation.components import bdq_login_admin

st.text(str(bdq_login_admin.submit_login({ACCOUNT!r}, {PASSWORD!r})))
"""
    app = AppTest.from_string(script).run()

    assert [str(item.value) for item in app.text] == [bdq_login_admin.NOT_ADMIN_MESSAGE]
    assert fake.logins() == 0
    _no_secret_left(app, ACCOUNT, PASSWORD)


def test_a_second_press_on_top_of_the_first_tries_once(
    server: tuple[MockStore, S3Target, str], fake: FakeBdq
) -> None:
    """같은 세션의 겹쳐 온 둘째 누름은 첫 시도의 결과를 다시 알릴 뿐 로그인하지 않는다(계정 잠김
    방지 — 틀린 비밀번호라도 시도 한 번). 폼이 이미 비운 칸의 꼬리 누름은 빈 칸 거부도 세우지
    않는다."""
    app = AppTest.from_string(DOUBLE_SCRIPT).run(timeout=LOGIN_RUN)

    assert not app.exception
    assert [str(item.value) for item in app.text] == ["[None, None, None]"]
    assert fake.logins() == 1
    assert [item.value for item in flashed(app, "error")] == ["로그인 실패 — 저장 안 함"]
    _no_secret_left(app, ACCOUNT, WRONG_PASSWORD)


def test_a_stopped_login_shows_the_reason_and_a_form_success_lifts_it(
    server: tuple[MockStore, S3Target, str], fake: FakeBdq
) -> None:
    mock, target, key = server
    stored = _save(target, key)
    assert login_store.mark_stopped(target, "token_unchanged", cipher=stored.cipher).ok
    app = AppTest.from_string(SCRIPT).run()
    status = _status(app)
    assert status.startswith(f"{bdq_login_admin.STATUS_LABEL} · {bdq_login_admin.STOPPED_WORD}(")
    assert "토큰이 바뀌지 않음" in status and "넣은 사람 zz" in status and "멈춘 때" in status
    assert OTHER_ACCOUNT not in "\n".join(_captions(app))

    app = _submit(app, ACCOUNT, PASSWORD)

    assert _status(app).startswith(f"{bdq_login_admin.STATUS_LABEL} · {bdq_login_admin.OK_WORD}")
    stored_now = _object(mock)
    assert stored_now is not None and stored_now["state"] == "ok"
    assert bdq_login.status().active and fake.logins() == 1


def test_an_unreadable_store_is_not_shown_as_absent(
    server: tuple[MockStore, S3Target, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    mock, _, _ = server
    mock.force["GET"] = (500, "InternalError")
    login_store.forget_state()
    switch_on(monkeypatch)

    app = AppTest.from_string(SCRIPT).run()

    assert not app.exception
    assert _status(app).startswith(
        f"{bdq_login_admin.STATUS_LABEL} · {bdq_login_admin.UNREAD_WORD}("
    )


# --- 지우기 --------------------------------------------------------------------------------


def test_deleting_needs_the_confirm_check_and_then_removes_the_login(
    server: tuple[MockStore, S3Target, str], fake: FakeBdq
) -> None:
    mock, target, key = server
    _save(target, key)
    app = AppTest.from_string(SCRIPT).run()
    delete = app.button(key=bdq_login_admin.DELETE_KEY)
    assert delete.disabled and delete.help == PASTE_CONFIRM_WHY

    app = app.checkbox(key=bdq_login_admin.DELETE_CONFIRM_KEY).check().run()
    delete = app.button(key=bdq_login_admin.DELETE_KEY)
    assert not delete.disabled and delete.help == bdq_login_admin.DELETE_HELP

    app = delete.click().run()

    assert not app.exception
    assert _object(mock) is None and login_store.current() is None
    assert login_store.effective_account() == "demo_env_user"
    assert [item.value for item in flashed(app, "success")] == [bdq_login_admin.DELETED_MESSAGE]
    assert _status(app) == f"{bdq_login_admin.STATUS_LABEL} · {bdq_login_admin.NONE_WORD}"
    assert not app.checkbox
    assert fake.logins() == 0


def test_the_delete_callback_refuses_without_the_confirm_check(
    server: tuple[MockStore, S3Target, str], fake: FakeBdq
) -> None:
    """잠긴 단추를 믿지 않는다 — 콜백이 확인 체크를 다시 보고, 꺼져 있으면 S3 에 지우기를 보내지
    않는다."""
    mock, target, key = server
    _save(target, key)
    script = """
from capa_simulation.components import bdq_login_admin
from capa_simulation.components.flash import render_flash

bdq_login_admin._delete()
render_flash(bdq_login_admin.FLASH_KEY)
"""
    app = AppTest.from_string(script).run()

    assert not app.exception
    assert [item.value for item in flashed(app, "warning")] == [
        bdq_login_admin.CONFIRM_FIRST_MESSAGE
    ]
    assert _object(mock) is not None
    assert requests_on(mock, login_store.OBJECT_KEY).count("DELETE") == 0


def test_a_login_without_a_marker_is_not_called_a_failure_and_shows_its_diag(
    server: tuple[MockStore, S3Target, str], fake: FakeBdq, monkeypatch: pytest.MonkeyPatch
) -> None:
    """하위 프로세스가 표지 없이 끝나면 폼 아래 · 알림창은 「로그인 확인 못 함(결과 표지
    없음)」 이고(비밀번호를 의심해 되풀이하지 않게) 「마지막 시도」 바로 아래 진단 값 줄이 선다.
    감사 상세에는 진단의 수 · 이름 · 판만 있고 화면 · 세션 · 감사 어디에도 계정 · 비밀번호가
    없다."""
    mock, _, _ = server
    recorder.start(env="cdep", version="test", inst="abcabcabcabc")
    monkeypatch.setenv("FAKE_BDQ_SCENE", "exit_hard")
    app = _submit(AppTest.from_string(SCRIPT).run(), ACCOUNT, PASSWORD)

    assert not app.exception
    line = "로그인 확인 못 함(결과 표지 없음) — 저장 안 함"
    assert [str(item.value) for item in app.error] == [line]
    assert [item.value for item in flashed(app, "error")] == [line]
    assert _object(mock) is None
    captions = _captions(app)
    last = next(index for index, text in enumerate(captions) if text.startswith(LAST))
    assert captions[last].endswith("로그인 확인 못 함(결과 표지 없음)")
    diag = captions[last + 1]
    assert diag.startswith(f"{bdq_login_admin.DIAG_LABEL} · ")
    plain = diag.replace("\\", "")
    assert "종료 3 · " in plain and "단계 login" in plain
    assert "stderr bigdataquery.LoginRefused" in plain and "bigdataquery 0.0.0+fake" in plain
    _no_secret_left(app, ACCOUNT, PASSWORD, "bad password")

    lines = [line for line in recorder.take_pending() if line["ev"] == bdq_login_admin.AUDIT_SET]
    assert len(lines) == 1
    det = lines[0]["det"]
    assert (det["result"], det["reason"], det["exit"], det["stage"], det["stderr"]) == (
        bdq_login.OUTCOME_REJECTED,
        bdq_login.REASON_NO_MARKER,
        3,
        "login",
        "bigdataquery.LoginRefused",
    )
    payload = json.dumps(lines, ensure_ascii=False)
    assert ACCOUNT not in payload and PASSWORD not in payload and "bad password" not in payload


# --- 감사 · 「그 화면으로」 ----------------------------------------------------------------------


def test_the_audit_lines_carry_results_and_codes_but_never_the_account_or_password(
    server: tuple[MockStore, S3Target, str], fake: FakeBdq
) -> None:
    recorder.start(env="cdep", version="test", inst="abcabcabcabc")
    app = AppTest.from_string(SCRIPT).run()
    app = _submit(app, ACCOUNT, WRONG_PASSWORD)
    app = _submit(app, ACCOUNT, PASSWORD)
    app = app.checkbox(key=bdq_login_admin.DELETE_CONFIRM_KEY).check().run()
    app.button(key=bdq_login_admin.DELETE_KEY).click().run()

    lines = [
        line
        for line in recorder.take_pending()
        if line["ev"] in (bdq_login_admin.AUDIT_SET, bdq_login_admin.AUDIT_DELETE)
    ]
    assert [(line["ev"], line["out"], line["det"]["result"]) for line in lines] == [
        (bdq_login_admin.AUDIT_SET, "fail", "rejected"),
        (bdq_login_admin.AUDIT_SET, "success", "saved"),
        (bdq_login_admin.AUDIT_DELETE, "success", "deleted"),
    ]
    payload = json.dumps(lines, ensure_ascii=False)
    assert ACCOUNT not in payload and PASSWORD not in payload and WRONG_PASSWORD not in payload


def test_the_goto_target_opens_the_box(server: tuple[MockStore, S3Target, str]) -> None:
    app = AppTest.from_string(GOTO_PRELUDE + SCRIPT).run()
    assert box_expanded(app, bdq_login_admin.EXPANDER_KEY) is False

    app.session_state[GOTO_PRESS_KEY] = dict(bdq_login_admin.bdq_login_target())
    app = app.run()

    assert box_expanded(app, bdq_login_admin.EXPANDER_KEY) is True


def test_the_form_works_after_the_app_took_the_key_out_of_the_environment(
    monkeypatch: pytest.MonkeyPatch, fake: FakeBdq, login_s3: tuple[MockStore, S3Target]
) -> None:
    """운영 앱은 기동 때 키를 쥐고 환경에서 뺀다(`take_secret_key`) — 펼침 · 넣기 · 저장이 쥔 키를
    본다."""
    mock, _ = login_s3
    switch_on(monkeypatch)
    _admin(monkeypatch)
    login_store.take_secret_key(os.environ)
    assert login_store.SECRET_KEY_ENV not in os.environ

    app = _submit(AppTest.from_string(SCRIPT).run(), ACCOUNT, PASSWORD)

    assert not app.exception
    stored = _object(mock)
    assert stored is not None and stored["state"] == "ok"
    assert fake.logins() == 1 and login_store.effective_account() == ACCOUNT
    assert login_store.SECRET_KEY_ENV not in os.environ
