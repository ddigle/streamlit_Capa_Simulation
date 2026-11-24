# Purpose: BDQ 자동 로그인 멈춤 알림 · 계정 없는 서버의 AD-10 가리킴 · AD-11 해소를 본다.

"""BigDataQuery 토큰 관리자 알림 셋(`container_start_check.render_token_alert`)과 자동 로그인.

결과 파일이 있는 C-DEP 서버는 회차마다 이벤트 칸 세 자리(`AD-10` · `AD-11` · `AD-23`)를 쓴다.
자동 로그인 상태는 S3 에 묻지 않고 읽는다 — 이 프로세스가 기억한 저장 객체(`bdq_login_store`)와
프로세스 안 멈춤, 아직 읽지 않았으면 이번 시작 기록(결과 파일의 `bdq_login` 칸). 값은 모두 합성이다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alert_marks import active_state, states
from bdq_login_support import ACCOUNT, PASSWORD, new_key
from streamlit.testing.v1 import AppTest
from test_bdq_token import fake_jwt
from test_token_failure_alert import _query

from capa_simulation import alerts
from capa_simulation import settings as app_settings
from capa_simulation.components import bdq_token_admin, container_start_check, sso_identity
from capa_simulation.components.bdq_login_admin import bdq_login_target
from capa_simulation.io import bdq_login, bdq_token
from capa_simulation.io import bdq_login_store as store
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.io.bdq_login_store import LoginSecret, StoredLogin
from capa_simulation.io.object_storage import MODE_ENV
from capa_simulation.navigation import ADMIN_AREA
from capa_simulation.page_tabs_state import tab_label

SCRIPT = """
from capa_simulation.components.container_start_check import render_token_alert

render_token_alert()
"""
STOP = container_start_check.LOGIN_STOP_ALERT_CODE
TROUBLE = container_start_check.LOGIN_TROUBLE_ALERT_CODE
FAILURE = container_start_check.TOKEN_ALERT_CODE
EXPIRY = bdq_token_admin.EXPIRY_ALERT_CODE
ENV_USER = "demo_env_user"


def _server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cell: Mapping[str, object] | None = None
) -> Path:
    """C-DEP 서버 꼴 — 결과 파일(자동 로그인 칸 `cell`) · `managed` + 키 · tmp 토큰 폴더 ·
    관리자."""
    path = tmp_path / "container_start.json"
    steps = {name: {"status": "ok", "reason": "정상"} for name in report_contract.STEPS}
    data: dict[str, object] = {"version": 1, "written_at": "", "steps": steps}
    if cell is not None:
        data["bdq_login"] = dict(cell)
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(app_settings, "CONTAINER_START_REPORT_PATH", path)
    monkeypatch.setenv(MODE_ENV, "managed")
    monkeypatch.setenv(report_contract.BDQ_SECRET_KEY_ENV, new_key())
    monkeypatch.setenv(report_contract.BDQ_USER_NAME_ENV, ENV_USER)
    folder = tmp_path / "credential"
    monkeypatch.setattr(bdq_token, "CREDENTIAL_DIR", folder)
    monkeypatch.setattr(sso_identity, "viewer_is_developer", lambda: True)
    return folder


def _stored(state: store.StoredState = store.STATE_OK, reason: str | None = None) -> StoredLogin:
    return StoredLogin(
        secret=LoginSecret(ACCOUNT, PASSWORD),
        cipher="demo-cipher",
        entered_by="de",
        entered_at="2026-11-16T09:00:00+09:00",
        state=state,
        stop_reason=reason,
        stopped_at="2026-11-16T10:00:00+09:00" if reason else None,
    )


def _secret_free(note: Mapping[str, object]) -> None:
    text = json.dumps(note, ensure_ascii=False)
    assert ACCOUNT not in text and PASSWORD not in text


def test_the_stop_alert_is_registered_as_an_action_state() -> None:
    spec = alerts.REGISTRY[STOP]
    assert (spec.level, spec.kind) == ("action", "state")


def test_a_stored_stop_tells_the_administrator_to_enter_the_account_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """기억한 저장 객체가 멈춤이면 관리자에게 — 까닭 낱말과 Admin Area 「BDQ 자동 로그인」 을
    가리킨다. 계정 · 비밀번호는 없다. 토큰 알림 셋이 한 자리씩 선다."""
    _server(tmp_path, monkeypatch)
    store.remember(_stored(store.STATE_STOPPED, "token_unchanged"))

    app = AppTest.from_string(SCRIPT).run()

    note = active_state(app, STOP)
    assert note is not None
    assert note["short"] == "BigDataQuery 자동 로그인 멈춤 — 계정을 다시 넣으세요"
    assert len(note["short"]) <= alerts.SHORT_LIMIT
    assert "토큰이 바뀌지 않음" in note["full"] and "「BDQ 자동 로그인」" in note["full"]
    assert "`" not in note["full"]
    assert (note["page"], note["href"]) == (tab_label(ADMIN_AREA), ADMIN_AREA.href)
    _secret_free(note)
    for code in (FAILURE, EXPIRY, STOP, TROUBLE):
        assert len(states(app, code)) == 1, code

    # 관리자가 다시 넣어 성공하면(기억이 `ok`) 해소로 닫힌다.
    store.remember(_stored())
    app.run()
    assert active_state(app, STOP) is None


def test_a_stop_without_a_marker_says_the_login_was_not_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """하위 프로세스가 표지 없이 끝난 멈춤은 「로그인 확인 못 함」 — 비밀번호를 의심해 다시 넣게
    하는 글이 아니라 진단 줄을 먼저 보라는 글이다. 멈춤 · 풀리는 길은 거절과 같다."""
    _server(tmp_path, monkeypatch)
    store.remember(_stored(store.STATE_STOPPED, bdq_login.REASON_NO_MARKER))

    note = active_state(AppTest.from_string(SCRIPT).run(), STOP)

    assert note is not None
    assert note["short"] == "BigDataQuery 자동 로그인 멈춤 — 로그인 확인 못 함"
    assert len(note["short"]) <= alerts.SHORT_LIMIT
    full = note["full"]
    assert "로그인 확인 못 함 — 결과 표지 없음" in full and "진단 줄" in full
    assert "비밀번호가 틀렸는지 모릅니다" in full and "다시 시도하지 않습니다" in full
    assert "`" not in full
    _secret_free(note)


def test_a_stop_found_at_start_tells_the_administrator_before_any_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이 프로세스가 아직 저장 객체를 읽지 않았으면(또는 S3 를 못 읽었으면) 이번 시작 기록으로
    가른다 — 시작의 거절은 멈춤이다."""
    _server(tmp_path, monkeypatch, {"status": "rejected", "reason": "login_raised"})

    note = active_state(AppTest.from_string(SCRIPT).run(), STOP)

    assert note is not None and "로그인 예외" in note["full"]


def test_an_in_process_stop_also_tells_the_administrator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """조회 중 거절로 멈춤 표시를 객체에 쓰지 못했어도(프로세스 안 멈춤) 알린다."""
    _server(tmp_path, monkeypatch)
    stored = _stored()
    store.remember(stored)
    monkeypatch.setattr(bdq_login, "_STATE", bdq_login._Process(stopped_cipher=stored.cipher))

    assert active_state(AppTest.from_string(SCRIPT).run(), STOP) is not None


@pytest.mark.parametrize("admin", [False, True], ids=["관리자 아님", "멈춤 아님"])
def test_the_stop_alert_stays_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, admin: bool
) -> None:
    _server(tmp_path, monkeypatch)
    monkeypatch.setattr(sso_identity, "viewer_is_developer", lambda: admin)
    store.remember(_stored() if admin else _stored(store.STATE_STOPPED, "token_unchanged"))

    app = AppTest.from_string(SCRIPT).run()

    assert active_state(app, STOP) is None
    assert [item["active"] for item in states(app, STOP)] == [False]


def test_a_server_without_the_key_never_raises_the_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """키가 없으면 기능이 없다 — 시작 기록 · 기억이 무엇이든 멈춤 알림은 해소다."""
    _server(tmp_path, monkeypatch, {"status": "rejected", "reason": "login_raised"})
    monkeypatch.delenv(report_contract.BDQ_SECRET_KEY_ENV)

    assert active_state(AppTest.from_string(SCRIPT).run(), STOP) is None


def test_a_token_failure_without_a_stored_account_points_at_the_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`managed` + 키인데 저장된 계정이 없으면 조회 토큰 실패(`AD-10`)의 할 일은 Admin Area 「BDQ
    자동 로그인」 에 계정 넣기다. 키가 없으면 지금처럼 「토큰 넣기」 다."""
    _server(tmp_path, monkeypatch)
    store.remember(None)
    _query(monkeypatch, ConnectionError("500 invalid token"))

    note = active_state(AppTest.from_string(SCRIPT).run(), FAILURE)
    assert note is not None
    assert bdq_token_admin.AUTO_LOGIN_FIX in note["full"]
    assert "「토큰 넣기」" not in note["full"] and "`" not in note["full"]

    monkeypatch.delenv(report_contract.BDQ_SECRET_KEY_ENV)
    note = active_state(AppTest.from_string(SCRIPT).run(), FAILURE)
    assert note is not None
    assert "「토큰 넣기」 로 새 토큰을 넣으면" in note["full"]
    assert bdq_token_admin.AUTO_LOGIN_FIX not in note["full"]


def test_the_expiry_alert_rests_while_the_auto_login_stands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """만료 1시간 전(`AD-11`)은 자동 로그인이 서 있는 동안 내지 않는다 — 토큰 파일은 저장된 계정
    이름이다(계정 하나의 원천). 계정이 없으면(기억 「없음」) 지금처럼 선다."""
    folder = _server(tmp_path, monkeypatch)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).replace(microsecond=0)
    folder.mkdir(parents=True)
    (folder / f"bigdataquery.token.{ACCOUNT}").write_text(fake_jwt(expires), encoding="utf-8")
    (folder / f"bigdataquery.token.{ENV_USER}").write_text(fake_jwt(expires), encoding="utf-8")

    store.remember(_stored())
    app = AppTest.from_string(SCRIPT).run()
    assert active_state(app, EXPIRY) is None
    assert [item["active"] for item in states(app, EXPIRY)] == [False]

    store.remember(None)
    assert active_state(app.run(), EXPIRY) is not None


def test_a_view_that_cannot_be_read_falls_back_to_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """상태를 읽다 무엇이 나도 모든 화면 회차의 알림 자리는 해소로 물러선다(`login_view`)."""
    _server(tmp_path, monkeypatch, {"status": "rejected", "reason": "login_raised"})

    def explode(_start: object = None) -> bdq_login.LoginView:
        raise RuntimeError("view")

    monkeypatch.setattr(bdq_login, "current_view", explode)
    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert [item["active"] for item in states(app, STOP)] == [False]


def test_the_stop_and_the_entry_alerts_open_the_bdq_login_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「그 화면으로」 는 Admin 「BDQ 자동 로그인」 펼침까지 연다(UI-NAV-01) — 멈춤 `AD-23` 과, 할
    일이 계정 넣기인 `AD-10`. 패키지가 읽는 토큰 환경변수 갈래의 `AD-10` 은 대상이 없다(할 일이 그
    펼침이 아니다)."""
    _server(tmp_path, monkeypatch)
    store.remember(_stored(store.STATE_STOPPED, "token_unchanged"))
    note = active_state(AppTest.from_string(SCRIPT).run(), STOP)
    assert note is not None and note["target"] == bdq_login_target()

    store.remember(None)
    _query(monkeypatch, ConnectionError("500 invalid token"))
    note = active_state(AppTest.from_string(SCRIPT).run(), FAILURE)
    assert note is not None and note["target"] == bdq_login_target()

    monkeypatch.setenv(bdq_token.LOGIN_TOKEN_ENV, "demo-environment-token")
    note = active_state(AppTest.from_string(SCRIPT).run(), FAILURE)
    assert note is not None and "target" not in note


@pytest.mark.parametrize(
    ("start_failed", "state", "environment_token", "targeted"),
    [
        (False, "none", False, True),
        (True, "none", False, False),
        (False, "none", True, False),
        (False, "ok", False, True),
        (False, "stopped", False, True),
        (False, "off", False, False),
    ],
)
def test_the_token_alert_target_follows_the_fix_it_names(
    monkeypatch: pytest.MonkeyPatch,
    start_failed: bool,
    state: bdq_login.ViewState,
    environment_token: bool,
    targeted: bool,
) -> None:
    """`AD-10` 의 대상은 전문의 첫 할 일이 계정 넣기 · 다시 넣기일 때만이다 — 시작 점검 실패 ·
    토큰 환경변수 · 꺼짐은 대상이 없다."""
    if environment_token:
        monkeypatch.setenv(bdq_token.LOGIN_TOKEN_ENV, "demo-environment-token")
    target = container_start_check._token_alert_target(start_failed, bdq_login.LoginView(state))
    assert target == (bdq_login_target() if targeted else None)


def test_a_token_failure_with_a_stored_account_points_at_entering_it_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """저장된 계정이 있는데(정상 · 멈춤) 조회가 토큰 갈래로 실패 — 조회 중 다시 로그인이 풀지
    못했으므로(멈춤 · 쉬는 중 · 그 문구 밖의 토큰 낱말), 첫 할 일은 Admin 「BDQ 자동 로그인」 에서
    다시 넣기(곧바로 새 토큰)다. 「토큰 넣기」 는 그 뒤 또는이다."""
    _server(tmp_path, monkeypatch)
    _query(monkeypatch, ConnectionError("500 invalid token"))
    for stored in (_stored(), _stored(store.STATE_STOPPED, "token_unchanged")):
        store.remember(stored)
        note = active_state(AppTest.from_string(SCRIPT).run(), FAILURE)
        assert note is not None
        full = note["full"]
        assert bdq_token_admin.RELOGIN_FIX in full and bdq_token_admin.INSTALL_FIX in full
        assert full.index(bdq_token_admin.RELOGIN_FIX) < full.index(bdq_token_admin.INSTALL_FIX)
        assert note["target"] == bdq_login_target()
        _secret_free(note)


@pytest.mark.parametrize(
    ("cell", "word", "reason"),
    [
        ({"status": "unreached", "reason": "timeout"}, "서버에 닿지 못함", "시간 초과"),
        (
            {"status": "unconfirmed", "reason": "remaining_unknown"},
            "로그인 확인 못 함",
            "남은 시간 모름",
        ),
        (
            {"status": "unavailable", "reason": "import_failed"},
            "시도하지 못함",
            "패키지를 불러오지 못함",
        ),
    ],
)
def test_a_start_that_could_not_stand_the_auto_login_tells_the_administrator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cell: Mapping[str, object],
    word: str,
    reason: str,
) -> None:
    """시작 때 자동 로그인이 멈추지 않은 채 서지 못함(닿지 못함 · 확인 못 함 · 못 함) — D6
    「알림만」 을 `AD-24` 가 낸다. 멈춤 알림은 서지 않고, 지문은 갈래 낱말 하나다."""
    _server(tmp_path, monkeypatch, cell)

    app = AppTest.from_string(SCRIPT).run()

    note = active_state(app, TROUBLE)
    assert note is not None
    assert note["short"] == f"BigDataQuery 자동 로그인 {word} — 다시 시도 대기"
    assert len(note["short"]) <= alerts.SHORT_LIMIT
    assert reason in note["full"] and "「BDQ 자동 로그인」" in note["full"]
    assert note["target"] == bdq_login_target()
    assert active_state(app, STOP) is None
    _secret_free(note)


def test_the_trouble_alert_follows_the_process_and_clears_on_success_or_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """앱이 기억을 읽은 뒤에는 이 프로세스의 자동 시도가 고쳐 쓴다 — 서지 못하면 서고, 성공 · 멈춤 ·
    관리자 아님이면 해소다."""
    _server(tmp_path, monkeypatch)
    stored = _stored()
    store.remember(stored)
    monkeypatch.setattr(
        bdq_login, "_STATE", bdq_login._Process(trouble="unreached", trouble_reason="connection")
    )
    app = AppTest.from_string(SCRIPT).run()
    note = active_state(app, TROUBLE)
    assert note is not None and "연결 실패" in note["full"]

    monkeypatch.setattr(sso_identity, "viewer_is_developer", lambda: False)
    assert active_state(app.run(), TROUBLE) is None
    monkeypatch.setattr(sso_identity, "viewer_is_developer", lambda: True)

    monkeypatch.setattr(bdq_login, "_STATE", bdq_login._Process())
    assert active_state(app.run(), TROUBLE) is None

    monkeypatch.setattr(
        bdq_login, "_STATE", bdq_login._Process(trouble="unreached", trouble_reason="connection")
    )
    store.remember(_stored(store.STATE_STOPPED, "miss_limit"))
    app.run()
    assert active_state(app, TROUBLE) is None and active_state(app, STOP) is not None


def test_a_cut_before_sending_shows_its_retry_turn_and_the_limit_stop_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """보내기 전 끊김(`import_killed`)은 `AD-24` 짧은 글 · 지문에 「다시 시도 n/3」 이 붙고(차례가
    바뀌면 다시 선다) 전문은 다음 시도 시각과 멈추는 때, 새 서버 시작은 그 시각을 기다리지 않는
    것을 말한다. 다시 시도 상한을 넘긴 멈춤(`cut_limit`)은 `AD-23` 짧은 글이 「다시 시도 3/3
    끊김」 이고 전문은 계정 잠김 때문이 아니라 다시 시도를 다 썼다고, 떠 있는 서버는 더 하지 않고
    풀리는 길은 새 서버 시작의 한 번 · 계정 다시 넣기 둘이라고 말한다."""
    _server(tmp_path, monkeypatch)
    now = datetime(2026, 11, 20, 9, 0, tzinfo=store.KST)
    monkeypatch.setattr(bdq_login, "_wall", lambda: now)
    due = "2026-11-20T09:05:00+09:00"
    store.remember(replace(_stored(), cuts=1, retry_after=due))
    monkeypatch.setattr(
        bdq_login,
        "_STATE",
        bdq_login._Process(
            trouble=bdq_login.OUTCOME_UNAVAILABLE, trouble_reason=bdq_login.REASON_IMPORT_KILLED
        ),
    )
    app = AppTest.from_string(SCRIPT).run()
    note = active_state(app, TROUBLE)
    assert note is not None
    assert note["short"] == "BigDataQuery 자동 로그인 시도하지 못함 — 다시 시도 1/3 대기"
    assert len(note["short"]) <= alerts.SHORT_LIMIT
    assert "불러오는 중 끊김 — 비밀번호를 보내기 전" in note["full"]
    assert "다시 시도 1/3 — 2026-11-20 09:05:00 뒤" in note["full"]
    assert "3번이 모두 끊기면 멈춥니다" in note["full"]
    assert "서버가 새로 뜨면 기다리지 않고 시작 때 한 번 해 봅니다" in note["full"]
    assert "재시작 때 다시 시도하고" not in note["full"]
    assert active_state(app, STOP) is None
    _secret_free(note)
    first = note["fp"]

    store.remember(replace(_stored(), cuts=2, retry_after="2026-11-20T09:15:00+09:00"))
    note = active_state(app.run(), TROUBLE)
    assert note is not None and "다시 시도 2/3" in note["short"] and note["fp"] != first

    store.remember(
        replace(_stored(store.STATE_STOPPED, bdq_login.REASON_CUT_LIMIT), cuts=4, retry_after=None)
    )
    app.run()
    assert active_state(app, TROUBLE) is None
    stop = active_state(app, STOP)
    assert stop is not None
    assert stop["short"] == "BigDataQuery 자동 로그인 멈춤 — 다시 시도 3/3 끊김"
    assert len(stop["short"]) <= alerts.SHORT_LIMIT
    assert "불러오는 중 끊김 다시 시도 상한" in stop["full"]
    assert "더는 다시 시도하지 않습니다" in stop["full"]
    assert "서버가 새로 뜨면(CI/CD · 컨테이너 재시작) 그때 한 번은 해 보아" in stop["full"]
    assert "계정을 다시 넣어 로그인이 성공해도 풀립니다" in stop["full"]
    assert "계정이 잠기지 않게" not in stop["full"]
    _secret_free(stop)


def test_a_cut_at_start_is_a_standing_trouble_not_a_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """시작의 보내기 전 끊김은 멈춤이 아니라 서 있는 채 서지 못함(`AD-24`)이다 — 앱이 아직 기억을
    읽지 않았으면 시작 기록으로 가르고, 차례는 기억을 읽은 뒤 붙는다."""
    _server(
        tmp_path,
        monkeypatch,
        {"status": "unavailable", "reason": bdq_login.REASON_IMPORT_KILLED, "key": "ok"},
    )
    app = AppTest.from_string(SCRIPT).run()
    note = active_state(app, TROUBLE)
    assert note is not None
    assert note["short"] == "BigDataQuery 자동 로그인 시도하지 못함 — 다시 시도 대기"
    assert "불러오는 중 끊김 — 비밀번호를 보내기 전" in note["full"]
    assert "3번이 모두 끊기면 멈춥니다" in note["full"] and "성공 없이" not in note["full"]
    assert "보내기 전). 다음 토큰 오류 때 다시 시도하고(서버가 새로 뜨면" in note["full"]
    assert active_state(app, STOP) is None
