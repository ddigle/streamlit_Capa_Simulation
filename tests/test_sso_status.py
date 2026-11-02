# Purpose: Admin 「통합인증 점검」·「서버 시작 점검」 통합인증 줄이 값 없이 판정만 싣는지 지킨다.

"""`components/sso_status.py`.

- 꺼짐 · 개발이면 아무것도 그리지 않는다(개발 PC · 사내 WebIDE 화면 그대로).
- 꺼짐(운영)이면 경고와 「켜면 막힐 문제」, 켜짐이면 판정 · 표 · 사실 · 최근 사건.
- 비밀값 · client id · 계정 원문은 어디에도 없다.
"""

from __future__ import annotations

import logging

import pytest
from sso_support import CLIENT_ID, PUBLIC_URL, signing, sso_secret, use_config
from streamlit.testing.v1 import AppTest

from capa_simulation.auth import names, runtime
from capa_simulation.components import sso_status

SCRIPT = """
from capa_simulation.components.sso_status import render_sso_status

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
    """운영인데 client id 가 없으면 「누구나 들어온다」 경고 — 나머지 값의 문제를 미리 보인다."""
    runtime.start({names.ENV_APP_ENV: "prod", names.ENV_PUBLIC_URL: "http://capa.example.invalid"})

    app = AppTest.from_string(SCRIPT).run()

    assert not list(app.exception)
    assert _labels(app) == ["통합인증 점검 · 꺼짐(운영)"]
    assert [warning.value for warning in app.warning] == [sso_status.OFF_IN_PRODUCTION_WARNING]
    text = _all_text(app)
    assert "켜면 막힐 문제: " in text and f"`{names.ENV_ISSUER}` — 값이 없음" in text
    assert f"`{names.ENV_PUBLIC_URL}` — https 가 아님" in text


def test_off_in_production_with_everything_else_ready_says_nothing_blocks() -> None:
    """첫 배포 ①: client id 만 비우고 나머지를 넣으면 「켜면 막힐 문제: 없음」 이다."""
    use_config(drop=[names.ENV_CLIENT_ID])

    app = AppTest.from_string(SCRIPT).run()

    assert _labels(app) == ["통합인증 점검 · 꺼짐(운영)"]
    assert "켜면 막힐 문제: 없음" in _all_text(app)


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
    assert (secret_row["상태"], secret_row["까닭"]) == ("있음", "길이 · 글자 수 검사 통과")
    assert "redirect\\_uri" in text and "auth\\/callback" in text
    assert signing().x5t.replace("-", "\\-").replace("_", "\\_") in text
    assert "문지기: 있음" in text and "세션 시간: 12시간" in text
    events = app.dataframe[1].value
    assert events["사건"].tolist() == ["login_fail", "login_ok", "config"]
    assert events["사유 코드"].tolist()[0] == "aud_mismatch"
    assert set(events["계정"].tolist()[:2]) == {"de***"}
    assert sso_status._event_code({"days": "12", "x5t": "abc"}) == "남은 날 12"
    assert sso_status._event_code({"loginid": "-"}) == "-"
    assert cfg.public_url == PUBLIC_URL


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
        ({}, "시작 때 있던 통합인증 환경변수: 없음"),
        (
            {names.ENV_SECRET: True, names.ENV_CLIENT_ID: True, names.ENV_SCOPE: False},
            f"시작 때 있던 통합인증 환경변수: `{names.ENV_CLIENT_ID}` · `{names.ENV_SECRET}`",
        ),
    ],
)
def test_the_started_environment_caption_lists_names_only(
    presence: dict[str, bool] | None, expected: str | None
) -> None:
    assert sso_status.started_environment_caption(presence) == expected
