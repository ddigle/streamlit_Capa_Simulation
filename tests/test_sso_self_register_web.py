# Purpose: 거절 표·거절 갈래 화면·「접속 권한 신청」 경로(위조·만료·출처·폼 칸·S3 꺼짐·실패)를
# 지킨다.

"""거절 화면의 스스로 등록(`auth/web.py` · `auth/page_frame.py`).

문지기 + 우리 경로 여섯을 ASGI 운전기로 돌린다. 저장소는 서명을 검증하는 가짜 S3 이고 값은 모두 합성
(`demo.*` · `*.example.invalid`)이다. 신원은 콜백이 심은 거절 표에서만 온다 — 폼 칸 · 주소 · 다른
쓰임 토큰으로는 남의 계정이나 관리자 등급을 얻지 못한다.
"""

from __future__ import annotations

import json
import re
import secrets
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

import pytest
from asgi_driver import App, AsgiResponse, http
from sso_support import PUBLIC_URL, use_config
from test_sso_access import (
    ADMIN,
    NAVIGATE,
    apply_cookies,
    cookie_header,
    gated_app,
    has_live_session,
    session_token,
    sign_in,
)

from capa_simulation.auth import access_store, names, page_frame, runtime, web
from capa_simulation.auth.access import GRADE_ADMIN, GRADE_USER
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.tokens import DENIED_TTL, issue_denied

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from s3_mock_store import MockStore, start_mock  # noqa: E402

NEWCOMER = "demo.newcomer"
LISTED = "demo.user"
OBJECT = names.DEFAULT_ACCESS_OBJECT
SAME_ORIGIN = {"origin": PUBLIC_URL, "sec-fetch-site": "same-origin"}


@pytest.fixture()
def mock_s3() -> Iterator[tuple[MockStore, str]]:
    store = MockStore()
    server, endpoint = start_mock(store)
    yield store, endpoint
    server.shutdown()
    server.server_close()


def s3_started(store: MockStore, endpoint: str, *people: str, **extra: str) -> SsoConfig:
    """운영 · 켜짐 · 환경변수 관리자 하나 · S3 명단(사람들) — 진입 파일처럼 읽기까지."""
    if people:
        users = [{"loginid": person, "grade": GRADE_USER} for person in people]
        store.put(OBJECT, json.dumps({"format": 1, "revision": 1, "users": users}).encode())
        store.put(names.ACCESS_SEEDED_OBJECT, b'{"format": 1}')
    cfg = use_config(
        {
            names.ENV_ACCESS_ADMINS: ADMIN,
            names.ENV_ACCESS_USERS: "",
            names.ENV_S3_ACCESS_KEY: store.access_key,
            names.ENV_S3_SECRET_KEY: store.secret_key,
            names.ENV_S3_ENDPOINT: endpoint,
            names.ENV_S3_BUCKET: store.bucket,
            names.ENV_S3_REGION: store.region,
            **extra,
        }
    )
    access_store.read_at_start(cfg)
    return cfg


def stored_users(store: MockStore) -> dict[str, dict[str, str]]:
    payload = json.loads(store.objects[OBJECT].decode("utf-8"))
    return {item["loginid"]: item for item in payload["users"]}


def follow(app: App, jar: dict[str, str], response: AsgiResponse) -> AsgiResponse:
    """303 Location 을 그 브라우저(쿠키 통)로 연다."""
    assert response.status == 303, (response.status, response.text)
    location = urlsplit(response.header("location") or "")
    return http(
        app,
        "GET",
        f"{location.path}?{location.query}",
        headers={**NAVIGATE, "cookie": cookie_header(jar)},
    )


def denied(app: App, jar: dict[str, str], loginid: str, **claims: str) -> AsgiResponse:
    """명단 밖 로그인 → 거절 화면(쿠키 통에 거절 표가 든다)."""
    callback = sign_in(app, jar, loginid, **claims)
    apply_cookies(jar, callback)
    return follow(app, jar, callback)


def form_mark(page: AsgiResponse) -> str:
    match = re.search(r'name="t" value="([^"]+)"', page.text)
    assert match is not None, "신청 폼이 없다"
    return match.group(1)


def press(
    app: App,
    jar: dict[str, str],
    fields: dict[str, str],
    *,
    headers: dict[str, str] | None = None,
) -> AsgiResponse:
    return http(
        app,
        "POST",
        names.REGISTER_PATH,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "cookie": cookie_header(jar),
            **(SAME_ORIGIN if headers is None else headers),
        },
        body=urlencode(fields).encode(),
    )


def code_of(response: AsgiResponse) -> str:
    assert response.status == 303, (response.status, response.text)
    return parse_qs(urlsplit(response.header("location") or "").query)["code"][0]


# --- 거절 표 --------------------------------------------------------------------------------------


def test_a_denial_plants_a_short_http_only_ticket(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = s3_started(store, endpoint, LISTED)
    jar: dict[str, str] = {}

    callback = sign_in(gated_app(), jar, NEWCOMER)

    ticket = callback.cookie(cfg.denied_cookie)
    assert ticket is not None and not ticket.deleted
    assert cfg.denied_cookie.startswith(names.HOST_PREFIX), "https 공개 주소 — __Host- 앞붙이"
    assert ticket.has("httponly") and ticket.has("secure")
    assert ticket.get("samesite") == "lax"
    assert ticket.get("max-age") == str(DENIED_TTL) == "900"
    assert not has_live_session(cfg, callback)


def test_the_ticket_shows_the_account_only_in_that_browser(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    s3_started(store, endpoint, LISTED)
    app = gated_app()
    jar: dict[str, str] = {}

    mine = denied(app, jar, NEWCOMER, username="새 사람", deptname="새 부서")
    other_browser = http(app, "GET", f"{names.ERROR_PATH}?code=not_on_list", headers=NAVIGATE)

    assert mine.status == 403 and NEWCOMER in mine.text
    assert web.REGISTER_LABEL in mine.text and 'name="t"' in mine.text
    assert mine.header("referrer-policy") == "same-origin", "폼 POST 가 출처를 싣게"
    assert "form-action 'self'" in (mine.header("content-security-policy") or "")
    for value in (NEWCOMER, "새 사람", "새 부서"):
        assert value not in other_browser.text, value
    assert web.SIGN_IN_TO_APPLY_LABEL in other_browser.text
    assert web.REGISTER_LABEL not in other_browser.text


@pytest.mark.parametrize("kind", ["tampered", "expired", "session_token", "other_secret"])
def test_a_ticket_that_is_not_ours_shows_nothing_and_writes_nothing(
    mock_s3: tuple[MockStore, str], kind: str
) -> None:
    store, endpoint = mock_s3
    cfg = s3_started(store, endpoint, LISTED)
    app = gated_app()
    jar: dict[str, str] = {}
    page = denied(app, jar, NEWCOMER)
    mark = form_mark(page)
    token = jar[cfg.denied_cookie]
    if kind == "tampered":
        jar[cfg.denied_cookie] = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    elif kind == "expired":
        old, _ = issue_denied(
            cfg, loginid=NEWCOMER, name=None, dept=None, next_path="/", now=int(time.time()) - 901
        )
        jar[cfg.denied_cookie] = old
    elif kind == "session_token":
        jar[cfg.denied_cookie] = session_token(cfg, NEWCOMER)
    else:
        other = use_config({names.ENV_SECRET: secrets.token_urlsafe(48)})
        forged, _ = issue_denied(
            other, loginid=NEWCOMER, name=None, dept=None, next_path="/", now=int(time.time())
        )
        cfg = s3_started(store, endpoint)
        jar = {cfg.denied_cookie: forged}

    shown = http(
        app,
        "GET",
        f"{names.ERROR_PATH}?code=not_on_list",
        headers={**NAVIGATE, "cookie": cookie_header(jar)},
    )
    pressed = press(app, jar, {"t": mark})

    assert NEWCOMER not in shown.text
    assert code_of(pressed) == web.NOT_ON_LIST
    assert NEWCOMER not in stored_users(store)


def test_form_fields_cannot_choose_the_account_or_the_grade(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    s3_started(store, endpoint, LISTED)
    app = gated_app()
    jar: dict[str, str] = {}
    mark = form_mark(denied(app, jar, NEWCOMER))

    pressed = press(
        app, jar, {"t": mark, "loginid": "demo.victim", "grade": GRADE_ADMIN, "sub": ADMIN}
    )

    assert code_of(pressed) == web.REGISTERED
    users = stored_users(store)
    assert "demo.victim" not in users
    assert users[NEWCOMER]["grade"] == GRADE_USER and users[NEWCOMER]["via"] == "self"


def test_a_mark_from_another_ticket_is_refused(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    s3_started(store, endpoint, LISTED)
    app = gated_app()
    first: dict[str, str] = {}
    mark = form_mark(denied(app, first, "demo.first"))
    second: dict[str, str] = {}
    denied(app, second, "demo.second")

    pressed = press(app, second, {"t": mark})

    assert pressed.status == 403
    assert "demo.second" not in stored_users(store)


@pytest.mark.parametrize(
    "headers",
    [
        {"origin": "https://evil.example.invalid", "sec-fetch-site": "cross-site"},
        {"origin": "null"},
        {"sec-fetch-site": "same-site"},
    ],
)
def test_a_cross_site_press_is_refused(
    mock_s3: tuple[MockStore, str], headers: dict[str, str]
) -> None:
    store, endpoint = mock_s3
    s3_started(store, endpoint, LISTED)
    app = gated_app()
    jar: dict[str, str] = {}
    mark = form_mark(denied(app, jar, NEWCOMER))

    pressed = press(app, jar, {"t": mark}, headers=headers)

    assert pressed.status == 403
    assert NEWCOMER not in stored_users(store)


def test_get_on_the_register_path_goes_to_the_denied_page(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    s3_started(store, endpoint, LISTED)

    response = http(gated_app(), "GET", names.REGISTER_PATH, headers=NAVIGATE)

    assert code_of(response) == web.NOT_ON_LIST


# --- 등록 한 바퀴 ---------------------------------------------------------------------------------


def test_register_then_reconnect_goes_in_without_a_restart(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = s3_started(store, endpoint, LISTED)
    app = gated_app()
    jar: dict[str, str] = {}
    callback = sign_in_to(app, jar, NEWCOMER, "/space?theme=dark")
    apply_cookies(jar, callback)
    page = follow(app, jar, callback)

    pressed = press(app, jar, {"t": form_mark(page)})
    done = follow(app, jar, pressed)

    assert code_of(pressed) == web.REGISTERED
    assert done.status == 200
    assert web.REGISTERED_TITLE in done.text and NEWCOMER in done.text
    assert page_frame.CHIP_WORDS["registered"] in done.text
    reconnect = re.search(r'<a class="button" href="([^"]+)">다시 접속</a>', done.text)
    assert reconnect is not None
    assert unquote(reconnect.group(1)).endswith("next=/space?theme=dark")

    again = sign_in_to(app, jar, NEWCOMER, "/space?theme=dark")
    assert has_live_session(cfg, again), "재시작 없이 들어온다"
    assert again.header("location") == f"{PUBLIC_URL}/space?theme=dark"
    cleared = again.cookie(cfg.denied_cookie)
    assert cleared is not None and cleared.deleted, "로그인하면 거절 표를 지운다"


def sign_in_to(app: App, jar: dict[str, str], loginid: str, next_path: str) -> AsgiResponse:
    from sso_support import id_token_claims, make_id_token
    from test_sso_access import post_form, start_login

    state, nonce = start_login(app, jar, next_path)
    return post_form(app, jar, make_id_token(id_token_claims(nonce, loginid=loginid)), state)


def test_pressing_twice_or_reloading_writes_once(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    s3_started(store, endpoint, LISTED)
    app = gated_app()
    jar: dict[str, str] = {}
    mark = form_mark(denied(app, jar, NEWCOMER))

    first = press(app, jar, {"t": mark})
    puts = sum(1 for method, _ in store.requests if method == "PUT")
    second = press(app, jar, {"t": mark})
    reloaded = follow(app, jar, first)

    assert code_of(first) == code_of(second) == web.REGISTERED
    assert sum(1 for method, _ in store.requests if method == "PUT") == puts
    assert reloaded.status == 200
    assert json.loads(store.objects[OBJECT])["revision"] == 2


def test_the_registered_page_needs_the_ticket_and_the_listing(
    mock_s3: tuple[MockStore, str],
) -> None:
    """로그인 없이 열리는 주소 — 코드만 넣어 열면 「등록했습니다」 가 아니다."""
    store, endpoint = mock_s3
    s3_started(store, endpoint, LISTED)
    app = gated_app()
    jar: dict[str, str] = {}
    denied(app, jar, NEWCOMER)

    bare = http(app, "GET", f"{names.ERROR_PATH}?code=registered", headers=NAVIGATE)
    unlisted = http(
        app,
        "GET",
        f"{names.ERROR_PATH}?code=registered",
        headers={**NAVIGATE, "cookie": cookie_header(jar)},
    )

    assert bare.status == 403 and web.REGISTERED_TITLE not in bare.text
    assert unlisted.status == 403 and web.REGISTERED_TITLE not in unlisted.text
    assert web.REGISTER_LABEL in unlisted.text


def test_an_admin_pressing_register_keeps_the_grade(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = s3_started(store, endpoint, LISTED)
    app = gated_app()
    jar: dict[str, str] = {}
    mark = form_mark(denied(app, jar, NEWCOMER))
    press(app, jar, {"t": mark})
    from test_sso_access_s3 import identity_of

    access_store.save_changes(cfg, identity_of(cfg, ADMIN), grades={NEWCOMER: GRADE_ADMIN})

    again = press(app, jar, {"t": mark})

    assert code_of(again) == web.REGISTERED
    assert stored_users(store)[NEWCOMER]["grade"] == GRADE_ADMIN


def test_logout_clears_the_ticket() -> None:
    cfg = use_config()

    response = http(gated_app(), "GET", names.LOGOUT_PATH, headers=NAVIGATE)

    cleared = response.cookie(cfg.denied_cookie)
    assert cleared is not None and cleared.deleted


# --- 넣지 못하는 서버
# ------------------------------------------------------------------------------


def test_without_the_s3_list_there_is_no_button_but_a_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPA_APP_CONTACT_EMAIL", "capa-help@example.invalid")
    use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_CONTACT: "CAPA 창구"})
    app = gated_app()
    jar: dict[str, str] = {}

    page = denied(app, jar, NEWCOMER, username="새 사람")

    assert page.status == 403 and NEWCOMER in page.text
    assert web.REGISTER_LABEL not in page.text and "<form" not in page.text
    assert web.SEND_NOTE_STEP in page.text and '<pre class="pick">' in page.text
    note = re.search(r'<pre class="pick">(.*?)</pre>', page.text, re.S)
    assert note is not None and NEWCOMER in note.group(1) and "새 사람" in note.group(1)
    assert 'href="mailto:capa-help@example.invalid"' in page.text and "CAPA 창구" in page.text


def test_a_failed_save_shows_the_note_instead(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    s3_started(store, endpoint, LISTED)
    app = gated_app()
    jar: dict[str, str] = {}
    mark = form_mark(denied(app, jar, NEWCOMER))
    store.force["PUT"] = (403, "AccessDenied")

    pressed = press(app, jar, {"t": mark})
    page = follow(app, jar, pressed)

    assert code_of(pressed) == web.REGISTER_FAILED
    assert page.status == 403 and web.REGISTER_FAILED_TITLE in page.text
    assert page_frame.CHIP_WORDS["retry"] in page.text
    assert "<form" not in page.text and '<pre class="pick">' in page.text
    assert NEWCOMER not in stored_users(store)


@pytest.mark.parametrize(
    ("force", "text"),
    [
        ((503, "SlowDown"), web.LIST_UNREAD_WAIT_TEXT),
        ((403, "AccessDenied"), web.LIST_UNREAD_ADMIN_TEXT),
    ],
)
def test_an_unread_list_shows_maintenance_without_a_button(
    mock_s3: tuple[MockStore, str], force: tuple[int, str], text: str
) -> None:
    store, endpoint = mock_s3
    store.force["GET"] = force
    s3_started(store, endpoint)
    app = gated_app()
    jar: dict[str, str] = {}

    page = denied(app, jar, NEWCOMER)

    assert page.status == 403
    assert web.LIST_UNREAD_TITLE in page.text and text in page.text
    assert page_frame.CHIP_WORDS["maintenance"] in page.text
    assert web.REGISTER_LABEL not in page.text and "<form" not in page.text
    assert "1분 뒤" in page.text if text == web.LIST_UNREAD_WAIT_TEXT else "1분 뒤" not in page.text
    assert '<pre class="pick">' in page.text, "표가 있으면 문의처로 보낼 글"
    pressed = press(app, jar, {"t": "x" * 32})
    assert pressed.status == 403
    assert OBJECT not in store.objects


def test_the_off_server_answers_404_on_the_register_path() -> None:
    runtime.reset()
    runtime.start({})

    response = http(gated_app(), "POST", names.REGISTER_PATH, headers=SAME_ORIGIN)

    assert response.status == 404


def test_the_page_frame_carries_the_same_mark_as_the_app() -> None:
    from capa_simulation.components import intro_overlay

    assert page_frame.MARK_RING_PATH == intro_overlay.MARK_RING_PATH
    assert page_frame.MARK_DIE_ORIGINS == intro_overlay.MARK_DIE_ORIGINS


def test_the_frame_escapes_every_text() -> None:
    frame = page_frame.Frame(
        title="<b>제목</b>",
        chip="denied",
        lead=("계정 {account} 끝",),
        primary=page_frame.Link("<i>단추</i>", 'https://x.example.invalid/"'),
        account="<script>",
        note_text="</pre><script>",
        contact_text="<a>",
    )

    html_text = page_frame.render(frame, now=int(time.time()))

    assert "<script>" not in html_text and "<b>제목" not in html_text and "<i>" not in html_text
    assert "&lt;script&gt;" in html_text


@pytest.mark.parametrize("code", [web.NOT_ON_LIST, web.LIST_UNREAD, web.REGISTER_FAILED])
def test_a_ticket_whose_account_is_now_listed_goes_in_instead_of_being_told_otherwise(
    mock_s3: tuple[MockStore, str], code: str
) -> None:
    """명단을 못 읽은 동안 거절된 사람이 명단이 돌아온 뒤 새로 고침 · 그 사이 관리자가 넣음 —
    「명단에 없습니다」 를 보이지 않고 로그인 경로(처음 가려던 화면)로 보낸다(2026-11-08 답 U4)."""
    store, endpoint = mock_s3
    cfg = s3_started(store, endpoint, LISTED)
    app = gated_app()
    jar: dict[str, str] = {}
    callback = sign_in_to(app, jar, NEWCOMER, "/space")
    apply_cookies(jar, callback)
    from test_sso_access_s3 import identity_of

    access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[NEWCOMER])

    page = http(
        app,
        "GET",
        f"{names.ERROR_PATH}?code={code}",
        headers={**NAVIGATE, "cookie": cookie_header(jar)},
    )

    assert page.status == 303
    assert page.header("location") == f"{PUBLIC_URL}{names.LOGIN_PATH}?next=%2Fspace"
    assert web.NOT_ON_LIST_TITLE not in page.text


def test_an_oversize_ticket_still_fits_and_verifies(mock_s3: tuple[MockStore, str]) -> None:
    """돌아갈 자리 2 KiB + 긴 한글 이름 · 부서 — 브라우저가 큰 쿠키를 버리지 않게 줄여 심는다."""
    store, endpoint = mock_s3
    cfg = s3_started(store, endpoint, LISTED)
    app = gated_app()
    jar: dict[str, str] = {}
    long_next = "/space?" + "&".join(f"p{index}=" + "x" * 20 for index in range(80))
    assert len(long_next) < web.MAX_NEXT_LENGTH
    callback = sign_in_to_with(
        app, jar, NEWCOMER, long_next, username="가" * 100, deptname="나" * 100
    )

    ticket = callback.cookie(cfg.denied_cookie)
    assert ticket is not None
    assert len(cfg.denied_cookie) + len(ticket.value) <= web.MAX_SESSION_COOKIE_BYTES
    apply_cookies(jar, callback)
    page = follow(app, jar, callback)
    assert NEWCOMER in page.text and web.REGISTER_LABEL in page.text


def sign_in_to_with(
    app: App, jar: dict[str, str], loginid: str, next_path: str, *, username: str, deptname: str
) -> AsgiResponse:
    from sso_support import id_token_claims, make_id_token
    from test_sso_access import post_form, start_login

    state, nonce = start_login(app, jar, next_path)
    claims = id_token_claims(nonce, loginid=loginid, username=username, deptname=deptname)
    return post_form(app, jar, make_id_token(claims), state)
