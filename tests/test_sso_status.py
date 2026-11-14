# Purpose: Admin 「통합인증 점검」·「서버 시작 점검」 통합인증 줄이 값 없이 판정만 싣는지 지킨다.

"""`components/sso_status.py`.

- 꺼짐 · 개발이면 아무것도 그리지 않는다(개발 PC · 사내 WebIDE 화면 그대로).
- 꺼짐(운영)이면 경고와 「켜면 막힐 문제」, 켜짐이면 판정 · 표 · 사실 · 최근 사건.
- 비밀값 · client id · 계정 원문은 어디에도 없다.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

import pytest
from alert_marks import active_state
from sso_support import (
    CLIENT_ID,
    PUBLIC_URL,
    expiring_signing,
    signing,
    sso_secret,
    use_config,
)
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts
from capa_simulation.auth import access_store, names, runtime
from capa_simulation.components import sso_status
from capa_simulation.components.literal_markdown import literal_markdown

SCRIPT = """
from capa_simulation.components.sso_status import render_sso_status

render_sso_status()
"""
# Admin Area 의 차례 — 운영인데 꺼짐 알림(`AD-02`)은 잠금 앞에서 펼침 밖으로 낸다.
ADMIN_AREA_SCRIPT = """
from capa_simulation.components.sso_status import (
    render_off_in_production_alert,
    render_sso_status,
)

render_off_in_production_alert()
render_sso_status()
"""


def _labels(app: AppTest) -> list[str]:
    """펼침 제목. 아이콘이 달린 펼침을 AppTest 는 `status` 로 센다."""
    return [item.label for item in app.expander] + [item.label for item in app.status]


def _all_text(app: AppTest) -> str:
    parts = [str(element.value) for element in app.caption]
    parts += [str(element.value) for element in app.warning]
    parts += [str(element.value) for element in app.error]
    parts += [frame.value.to_csv() for frame in app.dataframe]
    parts += _labels(app)
    return "\n".join(parts)


def test_off_in_development_draws_nothing() -> None:
    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert _labels(app) == []
    assert not list(app.caption) and not list(app.dataframe)


def test_off_in_production_warns_and_lists_what_would_block() -> None:
    """운영인데 client id 가 없으면 「누구나 들어온다」 — 상태 알림(`AD-02` — 알림창 · Alarm)이고
    펼침 안에는 까닭 캡션이 선다(2026-11-03 D2). 나머지 값의 문제를 미리 보인다."""
    runtime.start({names.ENV_APP_ENV: "prod", names.ENV_PUBLIC_URL: "http://capa.example.invalid"})

    app = AppTest.from_string(ADMIN_AREA_SCRIPT).run()

    assert not list(app.exception)
    assert _labels(app) == ["통합인증 점검 · 꺼짐(운영)"]
    assert not list(app.warning)
    assert active_state(AppTest.from_string(SCRIPT).run(), "AD-02") is None, "펼침은 내지 않는다"
    note = active_state(app, "AD-02")
    assert note is not None
    assert note["full"] == alerts.plain_text(sso_status.OFF_IN_PRODUCTION_WARNING)
    # 펼침의 결론은 값 한 줄이고 하는 법은 풍선 · 알림 전문이 말한다(설계 규칙 UI-TXT-01).
    (conclusion,) = [c for c in app.caption if sso_status.OFF_IN_PRODUCTION_CONCLUSION in c.value]
    assert conclusion.proto.help == sso_status.OFF_IN_PRODUCTION_HELP
    assert "포털 승인 메일" not in conclusion.value and "포털 승인 메일" in note["full"]
    text = _all_text(app)
    assert "**켜면 막힐 문제** · " in text and f"`{names.ENV_ISSUER}` — 값이 없음" in text
    assert f"`{names.ENV_PUBLIC_URL}` — https 가 아님" in text


def test_off_in_production_with_everything_else_ready_says_nothing_blocks() -> None:
    """첫 배포 ①: client id 만 비우고 나머지를 넣으면 「켜면 막힐 문제 · 없음」 이다."""
    use_config(drop=[names.ENV_CLIENT_ID])

    app = AppTest.from_string(SCRIPT).run()

    assert _labels(app) == ["통합인증 점검 · 꺼짐(운영)"]
    assert "**켜면 막힐 문제** · 없음" in _all_text(app)


def test_on_shows_facts_without_any_secret() -> None:
    cfg = use_config()
    runtime.mark_gate_installed()
    runtime.record_event("login_ok", loginid="dev.user", hours="12", jti="abcdefgh")
    runtime.record_event(
        "login_fail", level=logging.WARNING, reason="aud_mismatch", loginid="dev.user"
    )

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert _labels(app) == ["통합인증 점검 · 켜짐"]
    text = _all_text(app)
    for secret in (sso_secret(), CLIENT_ID, "dev.user", signing().der_b64[:40]):
        assert secret not in text, secret
    environment = app.dataframe[0].value
    assert environment["환경변수"].tolist()[: len(names.SSO_ENVIRONMENT)] == list(
        names.SSO_ENVIRONMENT
    )
    secret_row = environment.set_index("환경변수").loc[names.ENV_SECRET]
    assert (secret_row["상태"], secret_row["까닭"]) == ("있음", sso_status.SECRET_CHECKS_PASSED)
    widths = {
        name: column["width"]
        for name, column in json.loads(app.dataframe[0].proto.columns).items()
        if name in environment.columns
    }
    assert widths["까닭"] > widths["환경변수"] + widths["상태"], "까닭 칸이 잘리지 않게 넓다"
    assert sum(widths.values()) <= 918, "창 1283 의 표 폭(샘플 관측) 안이다"
    assert "redirect\\_uri" in text and "auth\\/callback" in text
    assert signing().x5t.replace("-", "\\-").replace("_", "\\_") in text
    assert (
        "**문지기** · 있음" in text
        and "**로그인 유지** · 마지막 사용 뒤 6시간 · 최대 24시간" in text
    )
    events = app.dataframe[1].value
    assert events["사건"].tolist() == ["login_fail", "login_ok", "config"]
    assert events["사유 코드"].tolist()[0] == "aud_mismatch"
    assert set(events["계정"].tolist()[:2]) == {"de***"}
    assert sso_status._event_code({"days": "12", "x5t": "abc"}) == "남은 날 12"
    assert sso_status._event_code({"loginid": "-"}) == "-"
    assert cfg.public_url == PUBLIC_URL


def test_recent_events_tell_an_idle_end_from_the_maximum() -> None:
    """만료로 닫은 열린 탭은 사유 코드에 끝난 까닭(idle · max)이 붙는다 — C-DEP 에는 로그 창구가
    없어 「쓰는 중인데 끊겼다」 문의를 이 표로 가른다."""
    use_config()
    runtime.record_event("session_closed", reason="expired", loginid="dev.user", end="max")
    runtime.record_event("session_closed", reason="expired", loginid="dev.user", end="idle")
    runtime.record_event("session_closed", reason="revoked", loginid="dev.user")

    codes = sso_status.recent_event_table()["사유 코드"].tolist()

    assert codes[:3] == ["revoked", "expired · idle", "expired · max"]


def test_recent_events_show_the_unreadable_entries_a_list_write_dropped() -> None:
    """명단을 다시 쓰며 못 읽는 항목을 빠뜨린 저장 — 관리자 저장(`access_saved`)이든 스스로
    등록(`access_self_registered`)이든 — 은 사유 코드에 파일의 고친 기록과 같은 이름
    `drop_unreadable n` 이 선다. 빠진 것이 없으면(0) 「-」 이고, 「복사」 글의 표에도 같은 칸이다
    (물음 보드 「정한 것」 9 — 감사 기록기가 꺼진 서버에서는 이 표가 그 수의 화면 창구다)."""
    cfg = use_config()
    runtime.record_event(
        "access_saved", loginid="dev.user", added="1", removed="0", revision="3", dropped="0"
    )
    runtime.record_event("access_self_registered", users="3", revision="4", dropped="2")
    runtime.record_event(
        "access_saved", loginid="dev.user", added="1", removed="0", revision="5", dropped="1"
    )

    rows = sso_status.recent_event_table()

    assert rows["사건"].tolist()[:3] == ["access_saved", "access_self_registered", "access_saved"]
    assert rows["사유 코드"].tolist()[:3] == ["drop_unreadable 1", "drop_unreadable 2", "-"]
    copied = sso_status.status_text("통합인증 점검", cfg, now=dt.datetime.now(dt.timezone.utc))
    assert "drop_unreadable 2" in copied and "drop_unreadable 1" in copied


def _refresh_caption_elements(app: AppTest) -> list[Any]:
    return [item for item in app.caption if str(item.value).startswith("**로그인 갱신(")]


def _refresh_caption(app: AppTest) -> list[str]:
    return [str(item.value) for item in _refresh_caption_elements(app)]


def test_the_status_shows_how_long_a_login_lasts_and_the_refresh_counts() -> None:
    """켜짐: 사실 줄에 유지 시간(마지막 사용 뒤 · 최대), 그 아래 갱신 결과 누계 한 줄."""
    use_config({names.ENV_SESSION_HOURS: "4", names.ENV_SESSION_MAX_HOURS: "10"})
    runtime.mark_gate_installed()
    for outcome, times in (("renewed", 3), ("skipped", 2), ("unauthorized", 1)):
        for _ in range(times):
            runtime.count_refresh(outcome)

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert "**로그인 유지** · 마지막 사용 뒤 4시간 · 최대 10시간 · 세션 쿠키 이름 " in _all_text(
        app
    )
    assert _refresh_caption(app) == [
        "**로그인 갱신(기동 뒤 누계)** · 다시 발급 3 · 건너뜀 2 · 로그인 없음 1 · "
        "출처·머리 거절 0 · 꼴 거절 0"
    ]
    # 사건 표는 그대로 둘째 데이터프레임이다 — 갱신은 사건 고리에 적지 않는다.
    assert len(app.dataframe) == 2
    assert "refresh" not in "".join(app.dataframe[1].value["사건"].tolist())


def test_the_refresh_counts_stay_a_value_line_and_the_help_says_how_to_read_them() -> None:
    """누계 줄은 값이다 — 범위와 「출처·머리 거절」 을 읽는 법은 풍선이 말한다(UI-TXT-01 · 04)."""
    use_config()
    runtime.count_refresh("forbidden")
    runtime.count_refresh("bad_request")

    assert sso_status.refresh_count_line().endswith("출처·머리 거절 1 · 꼴 거절 1")
    assert f"`{names.ENV_PUBLIC_URL}`" in sso_status.REFRESH_HELP
    assert "재시작" in sso_status.REFRESH_HELP
    (caption,) = _refresh_caption_elements(AppTest.from_string(SCRIPT).run())
    assert caption.proto.help == sso_status.REFRESH_HELP
    assert list(sso_status.REFRESH_OUTCOME_LABELS) == list(runtime.REFRESH_OUTCOMES)


def test_the_login_starts_and_returns_stand_as_a_value_line_with_their_help() -> None:
    """「로그인 시작 · 돌아옴」 누계(기동 뒤) — 값 한 줄, 읽는 법(돌아옴이 적으면 ADFS 화면에서
    멈춤)은 풍선이 말한다(보드 critic-missing 1 · UI-TXT-01 · 04). 리뷰로 옮기는 복사 글에도 실리고,
    꺼짐(운영)에서는 서지 않는다."""
    cfg = use_config()
    runtime.mark_gate_installed()
    runtime.count_login_start()
    runtime.count_login_start()
    runtime.count_login_return()

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    [line] = [item for item in app.caption if item.proto.help == sso_status.LOGIN_FLOW_HELP]
    assert line.value == "**로그인 시작 · 돌아옴(기동 뒤 누계)** · 시작 2 · 돌아옴 1"
    assert "ADFS 화면에서 멈춘" in sso_status.LOGIN_FLOW_HELP
    assert "재시작" in sso_status.LOGIN_FLOW_HELP
    copied = sso_status.status_text("통합인증 점검", cfg, now=dt.datetime.now(dt.timezone.utc))
    assert "로그인 시작 · 돌아옴(기동 뒤 누계) · 시작 2 · 돌아옴 1" in copied
    use_config(drop=[names.ENV_CLIENT_ID])
    off = AppTest.from_string(SCRIPT).run()
    assert not [item for item in off.caption if item.proto.help == sso_status.LOGIN_FLOW_HELP]


def test_an_expiring_certificate_stays_in_the_table_and_the_alarm_not_in_a_line() -> None:
    """만료 임박은 상태 알림(`AD-03`)과 표 까닭 칸이 말한다 — 펼침에 같은 말을 세우지
    않는다(설계 규칙 UI-TXT-07 · UI-NTF-02). 새 인증서를 더하는 법은 알림 전문 · Guide 다."""
    use_config({names.ENV_SIGNING_CERT: expiring_signing().der_b64})

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    note = active_state(app, "AD-03")
    assert note is not None and names.ENV_SIGNING_CERT in note["full"]
    assert not any("만료가" in str(item.value) for item in app.caption)
    table = app.dataframe[0].value.set_index("환경변수")
    assert "만료" in str(table.loc[names.ENV_SIGNING_CERT, "까닭"])


def test_the_lines_of_the_status_say_nothing_about_a_restart() -> None:
    """보관 범위는 풍선 · Guide 몫이다(설계 규칙 UI-TXT-01). 라벨은 값 앞의 이름만 둔다."""
    use_config()
    runtime.record_event("login_fail", level=logging.WARNING, reason="state_bad")

    text = _all_text(AppTest.from_string(SCRIPT).run())

    assert "재시작" not in text and "한 글자도" not in text
    assert "**redirect\\_uri** · " in text


def test_the_redirect_help_stands_on_the_redirect_line() -> None:
    """풍선은 그 말이 걸린 칸 곁에 선다 — 사실 줄 묶음에 달면 아이콘이 묶음 끝 「S3 명단」 줄에
    붙는다(설계 규칙 UI-TXT-01)."""
    use_config()

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    helped = [item for item in app.caption if item.proto.help == sso_status.REDIRECT_HELP]
    assert [item.value.split(" · ")[0] for item in helped] == ["**redirect\\_uri**"]
    assert "\n" not in helped[0].value


def test_the_refresh_counts_are_not_shown_while_off_in_production() -> None:
    """꺼짐(운영)은 갱신 경로가 404 라 누계가 늘 0 — 그리지 않는다."""
    use_config(drop=[names.ENV_CLIENT_ID])

    app = AppTest.from_string(SCRIPT).run()

    assert _labels(app) == ["통합인증 점검 · 꺼짐(운영)"]
    assert _refresh_caption(app) == []
    assert "**로그인 유지** · 마지막 사용 뒤 6시간 · 최대 24시간" in _all_text(app)


def test_the_start_check_row_follows_the_current_setting() -> None:
    assert sso_status.sso_start_step() == ("통합인증", "건너뜀", "ADFS_CLIENT_ID 없음")
    use_config()
    assert sso_status.sso_start_step() == ("통합인증", "정상", "")
    use_config(drop=[names.ENV_ISSUER, names.ENV_SIGNING_CERT])
    assert sso_status.sso_start_step() == (
        "통합인증",
        "실패",
        f"{names.ENV_ISSUER} · {names.ENV_SIGNING_CERT}",
    )


def test_a_broken_setting_marks_the_wrong_rows() -> None:
    cfg = use_config({names.ENV_SECRET: "short"}, drop=[names.ENV_ISSUER])

    table = sso_status.environment_table(cfg).set_index("환경변수")

    assert sso_status.sso_verdict(cfg) == "막힘"
    assert (table.loc[names.ENV_ISSUER, "상태"], table.loc[names.ENV_ISSUER, "까닭"]) == (
        "없음",
        "값이 없음",
    )
    assert table.loc[names.ENV_SECRET, "상태"] == "틀림"
    assert "short" not in table.to_csv()


@pytest.mark.parametrize(
    ("presence", "expected"),
    [
        (None, None),
        ({}, "**시작 때 있던 통합인증 환경변수** · 없음"),
        (
            {names.ENV_SECRET: True, names.ENV_CLIENT_ID: True, names.ENV_SCOPE: False},
            f"**시작 때 있던 통합인증 환경변수** · `{names.ENV_CLIENT_ID}` · `{names.ENV_SECRET}`",
        ),
    ],
)
def test_the_started_environment_caption_lists_names_only(
    presence: dict[str, bool] | None, expected: str | None
) -> None:
    assert sso_status.started_environment_caption(presence) == expected


def _flood(times: int) -> None:
    """로그인하지 않은 사람이 콜백으로 남길 수 있는 실패를 `times` 번 남긴다."""
    for index in range(times):
        runtime.record_event("idp_error", level=logging.WARNING, error="access_denied")
        runtime.record_event(
            "login_fail",
            level=logging.WARNING,
            reason="idp_error:access_denied" if index % 2 else "state_missing",
            loginid="-",
        )


def test_anonymous_failures_cannot_push_out_the_audit_events() -> None:
    """무인증 콜백 수십 번이 실제 로그인 · 설정 · 인증서 기록을 고리에서 밀어내지 못한다."""
    use_config()
    runtime.record_event("cert_expiring", level=logging.WARNING, days="12", x5t="abcd")
    runtime.record_event("login_ok", loginid="dev.user", hours="12", jti="abcdefgh")
    runtime.record_event(
        "login_fail", level=logging.WARNING, reason="aud_mismatch", loginid="dev.user"
    )

    _flood(runtime.MAX_EVENTS * 2)

    kept = [event.event for event in runtime.recent_events(anonymous=False)]
    assert kept == ["login_fail", "login_ok", "cert_expiring", "config"]
    anonymous = runtime.recent_events(anonymous=True)
    assert len(anonymous) == runtime.MAX_EVENTS
    assert {event.event for event in anonymous} == {"idp_error", "login_fail"}
    assert runtime.anonymous_failure_counts() == {
        "idp_error:access_denied": 100,
        "login_fail:idp_error:access_denied": 50,
        "login_fail:state_missing": 50,
    }
    merged = runtime.recent_events(runtime.MAX_EVENTS * 3)
    assert len(merged) == runtime.MAX_EVENTS + 4


def test_anonymous_failure_kinds_are_capped() -> None:
    """IdP 오류 원문은 남이 고를 수 있다 — 사유 가짓수는 고리 크기까지만 세고 나머지는 한데 센다."""
    use_config()

    for index in range(runtime.MAX_EVENTS + 10):
        runtime.record_event("idp_error", level=logging.WARNING, error=f"made_up_{index}")

    counts = runtime.anonymous_failure_counts()
    assert len(counts) == runtime.MAX_EVENTS + 1
    assert counts["idp_error:other"] == 10


def test_the_status_shows_audit_events_and_anonymous_failures_apart() -> None:
    use_config()
    runtime.mark_gate_installed()
    runtime.record_event("login_ok", loginid="dev.user", hours="12", jti="abcdefgh")
    _flood(30)

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    events = app.dataframe[1].value
    assert events["사건"].tolist() == ["login_ok", "config"]
    caption = [str(c.value) for c in app.caption if str(c.value).startswith("**로그인 전 실패")]
    assert len(caption) == 1 and "누계 60" in caption[0]
    anonymous = app.dataframe[2].value
    assert len(anonymous) == sso_status.ANONYMOUS_EVENT_LIMIT
    assert set(anonymous["계정"].tolist()) == {"-"}


def test_with_the_audit_log_on_the_status_keeps_the_pre_login_failure_table() -> None:
    """감사 기록이 켜진 서버는 사람 단위 사건 표(최근 사건 · 명단 밖 로그인)를 「접속 · 작업 기록」
    탭이 보인다 — 점검 펼침에는 그 둘의 누계 줄과 리뷰용 「복사」 만 남는다(설계 AU19). 로그인 전
    실패 표는 그대로 그린다 — 감사 줄에는 그 실패가 한 시간 건수뿐이라 겹치지 않고, 실패 화면의 진단
    번호를 맞추는 자리다(보드 decided-login 5). 복사 글은 그대로 표까지."""
    from capa_simulation.audit import recorder

    cfg = use_config()
    runtime.mark_gate_installed()
    recorder.start(env="cdep", version="test", inst="b0b0b0b0b0b0")
    runtime.record_event("login_ok", loginid="dev.user", hours="12", jti="abcdefgh")
    runtime.record_event(runtime.DENIED_EVENT, level=logging.WARNING, loginid="demo.gone")
    _flood(30)

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert len(app.dataframe) == 2, "설정 진단 표와 로그인 전 실패 표"
    anonymous = app.dataframe[1].value
    assert len(anonymous) == sso_status.ANONYMOUS_EVENT_LIMIT
    assert set(anonymous["계정"].tolist()) == {"-"}
    assert "login_ok" not in anonymous["사건"].tolist()
    captions = [str(c.value) for c in app.caption]
    assert not any(caption.startswith("최근 사건") for caption in captions)
    assert len([c for c in captions if c.startswith("**로그인 전 실패")]) == 1
    assert len([c for c in captions if c.startswith("명단 밖 로그인")]) == 1
    copied = sso_status.status_text("통합인증 점검", cfg, now=dt.datetime.now(dt.timezone.utc))
    assert "최근 사건(새것 먼저)" in copied


def _boot_failure_captions(app: AppTest) -> list[str]:
    return [
        str(c.value) for c in app.caption if str(c.value).startswith(sso_status.BOOT_FAILURE_LABEL)
    ]


def test_with_the_audit_log_on_the_status_still_shows_the_boot_failure_line() -> None:
    """감사 기록이 켜진 서버(통합인증 켜짐 — C-DEP)도 펼침에 앱 시작 실패 줄을 늘 싣는다 — 감사
    대응표 밖이라 「접속 · 작업 기록」 탭에 없고, 사람이 불러 준 판의 참고 줄(「참고 db_locked ·
    <UTC 분>」)과 짝을 맞추는 자리다(보드 boot-record). 줄은 고리의 `boot_fail` 마다 하나(새것
    먼저)이고 시각은 참고 줄과 같은 UTC 분이다. 최근 사건 표의 상한(20)보다 많은 사건 뒤에도 남는다.
    실패가 없으면 줄이 없다."""
    from capa_simulation.audit import recorder
    from capa_simulation.components import stop_panel

    use_config()
    runtime.mark_gate_installed()
    recorder.start(env="cdep", version="test", inst="b0b0b0b0b0b0")
    assert _boot_failure_captions(AppTest.from_string(SCRIPT).run()) == []

    assert runtime.note_boot_failure("db_locked", "IOException")
    for index in range(sso_status.RECENT_EVENT_LIMIT + 5):
        runtime.record_event("login_ok", loginid=f"dev.user{index}", hours="12", jti="abcdefgh")
    assert runtime.note_boot_failure("migration_failed", "MigrationChanged")

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    boots = [item for item in runtime.recent_events() if item.event == runtime.BOOT_FAIL_EVENT]
    expected = []
    for item in boots:
        code, kind = item.value("reason"), item.value("kind")
        # 시각은 판의 참고 줄 끝과 같은 글자다.
        moment = stop_panel.reference_line(code, now=item.at).split(" · ", 1)[1]
        expected.append(
            f"{sso_status.BOOT_FAILURE_LABEL} · {literal_markdown(code)} · {kind} · {moment}"
        )
    assert [line.split(" · ")[1] for line in expected] == ["migration\\_failed", "db\\_locked"]
    assert _boot_failure_captions(app) == ["  \n".join(expected)]
    # 사람 단위 사건 표는 그대로 그리지 않는다(최근 사건 표 없음).
    assert not any(str(c.value).startswith("최근 사건") for c in app.caption)


def test_without_the_audit_log_the_boot_failure_stays_in_the_recent_event_table() -> None:
    """감사가 꺼진 서버는 최근 사건 표가 `boot_fail` 줄을 싣는다 — 같은 펼침에 줄을 한 번 더 그리지
    않는다(UI-TXT-07)."""
    use_config()
    runtime.mark_gate_installed()
    assert runtime.note_boot_failure("db_locked", "IOException")

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert _boot_failure_captions(app) == []
    events = app.dataframe[1].value
    assert runtime.BOOT_FAIL_EVENT in events["사건"].tolist()


def test_an_unknown_list_file_reads_as_an_unknown_format() -> None:
    """S3 명단을 모르는 꼴로 받았을 때의 까닭 이름은 「모르는 파일 형식」 이다(검수 보드
    ad-format-word — `docs/sso_setup.md` 의 까닭 목록과 같은 낱말)."""
    assert sso_status.ACCESS_PROBLEM_LABELS[access_store.KIND_UNKNOWN_FORMAT] == "모르는 파일 형식"
