# Purpose: 시작 스크립트의 BDQ 자동 로그인 단계 · 결과 칸 · 비밀 경계 · 잠든 불변식을 고정한다.

"""시작 스크립트(`scripts/container_start.py`)의 BigDataQuery 자동 로그인 단계.

차례는 설치 → 자동 로그인 → 예비 토큰(`CAPA_BDQ_TOKEN`) → 요청자 계정이다. 갈래마다의 차례는 로그인
단계를 바꿔 끼워(`start_login`) 보고, 끝까지는 가짜 `bigdataquery`(진짜 하위 프로세스)와 서명을
검증하는 가짜 S3 로 본다 — 하위 프로세스에서 `login()` 이 불린 수가 곧 계정 잠김 방지 계약이다.

값은 모두 합성이다. 저장된 계정은 `CAPA_BDQ_USER_NAME` 과 다른 카나리아 글이라 결과 파일 · 출력 ·
하위 프로세스 환경 어디에 새는지 찾기 쉽다.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest
from bdq_login_support import (
    ACCOUNT,
    ADMIN_ID,
    PASSWORD,
    WRONG_PASSWORD,
    FakeBdq,
    new_key,
    requests_on,
    running_mock,
    s3_environment,
    target_of,
    use_fake_bdq,
)
from test_container_start import (
    ALL_ENVIRONMENT,
    FAKE_BDQ_TOKEN,
    FAKE_BDQ_USER,
    FakeRunner,
    _main,
    _probe,
    _steps,
    place,
)

import capa_simulation.settings as settings
from capa_simulation.components import container_start_check
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.io import bdq_login, bdq_token
from capa_simulation.io import bdq_login_store as store
from capa_simulation.io import container_start_report as report_contract
from capa_simulation.io.bdq_login_store import LoginSecret, StoredLogin
from capa_simulation.io.object_storage import MODE_ENV

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import container_start  # noqa: E402

__all__ = ["place"]

KEY_ENV = report_contract.BDQ_SECRET_KEY_ENV
# 걷은 판(자동 로그인 앞)이 결과 파일에 쓰던 칸 — 키도 객체도 없는 서버는 이 칸들이 그대로다.
WALKED_KEYS = {
    "version",
    "written_at",
    "steps",
    "bigdataquery_version",
    "token_file",
    "runtime",
    "user_name",
    "missing_environment",
    "pip_tail",
    "sso_environment",
}


def _stored(state: store.StoredState = store.STATE_OK, reason: str | None = None) -> StoredLogin:
    """저장된 한 벌(합성) — 계정은 `CAPA_BDQ_USER_NAME`(`FAKE_BDQ_USER`)과 다르다."""
    return StoredLogin(
        secret=LoginSecret(ACCOUNT, PASSWORD),
        cipher="demo-cipher",
        entered_by="de",
        entered_at="2026-11-16T09:00:00+09:00",
        state=state,
        stop_reason=reason,
    )


def _login_stub(started: bdq_login.StartLogin) -> container_start.StartLoginFn:
    def start(_environ: Mapping[str, str], _folder: Path) -> bdq_login.StartLogin:
        return started

    return start


def _check(
    environ: Mapping[str, str],
    credential_dir: Path,
    *,
    start_login: container_start.StartLoginFn | None = None,
    runner: FakeRunner | None = None,
) -> dict[str, object]:
    """시작 점검 한 번(설치 · 자동 로그인 · 토큰 · 계정) — `managed` 받기 앞까지. 결과 파일 내용."""
    container_start.check_and_record(
        dict(environ),
        credential_dir=credential_dir,
        runner=runner or FakeRunner([_probe("ok", "9.9.9")]),
        start_login=start_login or container_start.default_start_login,
    )
    written = json.loads(settings.CONTAINER_START_REPORT_PATH.read_text(encoding="utf-8"))
    assert isinstance(written, dict)
    return written


def _cell(report: Mapping[str, object]) -> dict[str, object]:
    cell = report["bdq_login"]
    assert isinstance(cell, dict)
    return cell


def _assert_no_login_secret(text: str) -> None:
    for value in (ACCOUNT, PASSWORD, WRONG_PASSWORD):
        assert value not in text, f"자동 로그인 비밀이 남았다: {value!r}"


# --- 잠든 불변식 — 키도 객체도 없으면 걷은 판과 같다 ----------------------------------------------


def test_without_a_key_the_start_is_the_walked_one(
    place: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """키가 없으면 로그인 하위 프로세스를 띄우지 않고, 결과 파일은 새 칸(`bdq_login` — 꺼짐) 밖이
    걷은 판의 칸 그대로이며, 하위 프로세스 차례 · 앱 환경 · 출력이 로그인 단계를 비운 실행과
    같다."""
    spawned: list[object] = []
    monkeypatch.setattr(bdq_login, "attempt_login", lambda *a, **k: spawned.append(a))

    real_runner = FakeRunner([_probe("ok", "9.9.9")])
    real, real_exec = _main(place, ALL_ENVIRONMENT, real_runner)
    real_out = capsys.readouterr().out
    token = place / "config" / ".credential" / f"bigdataquery.token.{FAKE_BDQ_USER}"
    assert token.read_text(encoding="utf-8") == FAKE_BDQ_TOKEN
    shutil.rmtree(place / "config")

    def empty_login(_environ: Mapping[str, str], _folder: Path) -> bdq_login.StartLogin:
        return bdq_login.StartLogin("off", store.REASON_NOT_MANAGED)

    empty_runner = FakeRunner([_probe("ok", "9.9.9")])
    empty_exec = container_start_exec(place, ALL_ENVIRONMENT, empty_runner, empty_login)
    empty = json.loads(settings.CONTAINER_START_REPORT_PATH.read_text(encoding="utf-8"))
    empty_out = capsys.readouterr().out

    assert spawned == []
    assert set(real) == WALKED_KEYS | {"bdq_login"}
    assert _cell(real) == {
        "status": "off",
        "reason": store.REASON_NOT_MANAGED,
        "key": report_contract.LOGIN_KEY_MISSING,
        "remaining_minutes": None,
        "error_kind": "",
        "failure_kind": "",
        "stop_write": "",
        "entered_at": "",
        "child": None,
        "retry": 0,
    }
    steps = _steps(real)
    assert steps[report_contract.STEP_TOKEN] == {"status": "ok", "reason": "토큰 파일을 씀"}
    assert steps[report_contract.STEP_USER_NAME] == {"status": "ok", "reason": "있음"}
    assert real["missing_environment"] == []
    assert _without_clock(real) == _without_clock(empty)
    assert real_runner.calls == empty_runner.calls
    assert real_exec.calls == empty_exec
    assert real_out == empty_out
    assert report_contract.BDQ_LOGIN_LABEL not in real_out, "managed 아닌 서버는 줄을 찍지 않는다"


def _without_clock(report: Mapping[str, object]) -> dict[str, object]:
    """결과 파일에서 시각(쓴 때 · 토큰 파일 수정 시각)과 새 칸을 뺀 것."""
    token_file = report["token_file"]
    assert isinstance(token_file, dict)
    rest = {k: v for k, v in report.items() if k not in ("written_at", "bdq_login")}
    rest["token_file"] = {k: v for k, v in token_file.items() if k != "modified_at"}
    return rest


def container_start_exec(
    place: Path,
    environ: Mapping[str, str],
    runner: FakeRunner,
    start_login: container_start.StartLoginFn,
) -> list[tuple[str, list[str], dict[str, str]]]:
    """`_main` 과 같되 로그인 단계를 바꿔 끼운 실행 — `exec` 부름을 돌려준다."""
    calls: list[tuple[str, list[str], dict[str, str]]] = []
    container_start.main(
        ["--credential-dir", str(place / "config" / ".credential")],
        environ=dict(environ),
        runner=runner,
        exec_app=lambda file, args, env: calls.append((file, list(args), dict(env))),
        start_login=start_login,
    )
    return calls


def test_a_managed_server_without_a_key_never_asks_s3_and_writes_the_fallback(
    place: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`managed` 인데 키가 없으면 버킷의 저장 자리에 한 번도 묻지 않고(요청 0) 로그인도 없다. 예비
    토큰은 지금처럼 `CAPA_BDQ_USER_NAME` 이름으로 쓰고, 표 줄은 「꺼짐 — 키 없음」(건너뜀)이다."""
    spawned: list[object] = []
    monkeypatch.setattr(bdq_login, "attempt_login", lambda *a, **k: spawned.append(a))
    credentials = place / "config" / ".credential"
    with running_mock() as (mock, endpoint):
        environ = {**ALL_ENVIRONMENT, **s3_environment(mock, endpoint), MODE_ENV: "managed"}
        report = _check(environ, credentials)
        assert mock.requests == []
    assert spawned == []
    assert _cell(report)["status"] == "off" and _cell(report)["reason"] == store.REASON_NO_KEY
    assert _steps(report)[report_contract.STEP_TOKEN] == {
        "status": "ok",
        "reason": "토큰 파일을 씀",
    }
    assert (credentials / f"bigdataquery.token.{FAKE_BDQ_USER}").is_file()
    read = report_contract.read_container_start_report()
    assert read is not None and read.bdq_login is not None
    assert report_contract.login_step(read.bdq_login) == report_contract.StartStep(
        report_contract.STATUS_SKIPPED, "꺼짐 — 키 없음"
    )
    assert "BDQ 자동 로그인 — 건너뜀: 꺼짐 — 키 없음" in capsys.readouterr().out


# --- 갈래마다 — 로그인 단계를 바꿔 끼운다 ---------------------------------------------------------


def test_an_ok_login_keeps_the_new_token_and_skips_the_fallback(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """로그인이 성공하면 패키지가 쓴 새 토큰을 `CAPA_BDQ_TOKEN` 으로 덮지 않는다. 토큰 줄은 정상,
    요청자 계정은 저장된 계정이라 정상이다. 칸에는 남은 분이 실린다."""
    credentials = place / "config" / ".credential"
    result = bdq_login.LoginResult("ok", remaining_minutes=479)
    started = bdq_login.StartLogin("ok", result=result, stored=_stored())
    environ = {k: v for k, v in ALL_ENVIRONMENT.items() if k != report_contract.BDQ_USER_NAME_ENV}

    report = _check({**environ, KEY_ENV: new_key()}, credentials, start_login=_login_stub(started))

    steps = _steps(report)
    assert steps[report_contract.STEP_TOKEN]["status"] == report_contract.STATUS_OK
    assert "자동 로그인이 새 토큰을 씀" in steps[report_contract.STEP_TOKEN]["reason"]
    assert steps[report_contract.STEP_USER_NAME] == {
        "status": "ok",
        "reason": "저장된 BDQ 자동 로그인 계정",
    }
    assert not credentials.exists(), "예비 토큰을 쓰지 않는다"
    cell = _cell(report)
    assert (cell["status"], cell["remaining_minutes"], cell["key"]) == ("ok", 479, "ok")
    printed = capsys.readouterr().out
    assert "BDQ 자동 로그인 — 정상: 정상 · 남은 7시간 59분" in printed
    _assert_no_login_secret(json.dumps(report, ensure_ascii=False) + printed)


def test_a_start_login_without_a_marker_records_its_child_diag(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """표지 없이 끝난 시작 로그인(멈춤)은 결과 칸 `child` 에 하위 프로세스 진단(수 · 이름 · 판)을
    싣고, 「서버 시작 점검」 이 표 줄 아래 값 줄로 보인다 — 앱 프로세스의 마지막 시도 줄은 시작 뒤
    exec 로 사라지므로 시작 길의 진단은 이 칸이 남긴다. 비밀이 없다."""
    credentials = place / "config" / ".credential"
    diag = report_contract.ChildDiag(-9, "SIGKILL", 4.1, "import", "", "2.5.0", "-")
    result = replace(bdq_login.LoginResult("rejected", bdq_login.REASON_NO_MARKER), diag=diag)
    started = bdq_login.StartLogin(
        "rejected", bdq_login.REASON_NO_MARKER, result=result, stored=_stored()
    )

    report = _check(
        {**ALL_ENVIRONMENT, KEY_ENV: new_key()}, credentials, start_login=_login_stub(started)
    )

    assert _cell(report)["child"] == diag.fields()
    parsed = report_contract.parse_report(report)
    assert parsed is not None and parsed.bdq_login is not None
    assert parsed.bdq_login.child == diag
    step = report_contract.login_step(parsed.bdq_login)
    assert step == report_contract.StartStep("failed", "멈춤 — 결과 표지 없음 · 예비 토큰")
    lines = container_start_check.fact_lines(parsed)
    label = f"**{report_contract.BDQ_LOGIN_LABEL} 진단**"
    assert lines[-1] == f"{label} · {literal_markdown(diag.text)}"
    _assert_no_login_secret(json.dumps(report, ensure_ascii=False) + capsys.readouterr().out)
    without = report_contract.parse_report(
        {**report, "bdq_login": {**_cell(report), "child": None}}
    )
    assert without is not None
    assert not any(line.startswith(label) for line in container_start_check.fact_lines(without))


def test_a_start_diag_carries_the_memory_and_process_clues_through_the_result_file(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """시작 로그인의 메모리 · 띄우기 앞 프로세스 단서(시작 스크립트 프로세스 — 막 떴으니 뜬 시간은
    0 에 가깝다)도 결과 칸 `child` 를 지나 「서버 시작 점검」 진단 줄에 그대로 선다."""
    credentials = place / "config" / ".credential"
    memory = report_contract.ChildMemory(420, 610, 1024, False, 0, 0, 90, 92, 58)
    process = report_contract.ProcessClues(0.0, 1, 6, 3, None, True, 0)
    diag = report_contract.ChildDiag(-9, "SIGKILL", 2.6, "import", "", "-", "-", memory, process)
    result = replace(
        bdq_login.LoginResult(bdq_login.OUTCOME_UNAVAILABLE, bdq_login.REASON_IMPORT_KILLED),
        diag=diag,
    )
    started = bdq_login.StartLogin(
        "unavailable", bdq_login.REASON_IMPORT_KILLED, result=result, stored=_stored()
    )

    report = _check(
        {**ALL_ENVIRONMENT, KEY_ENV: new_key()}, credentials, start_login=_login_stub(started)
    )

    assert _cell(report)["child"] == diag.fields()
    parsed = report_contract.parse_report(json.loads(json.dumps(report)))
    assert parsed is not None and parsed.bdq_login is not None
    assert parsed.bdq_login.child == diag
    label = f"**{report_contract.BDQ_LOGIN_LABEL} 진단**"
    line = container_start_check.fact_lines(parsed)[-1]
    assert line == f"{label} · {literal_markdown(diag.text)}"
    assert diag.text.endswith(
        "하위 최고 58MiB · 앱 뜬 지 0.0시간 · 스레드 1 · 열린 파일 6 · pids 3/max · 좀비 0"
    )
    _assert_no_login_secret(json.dumps(report, ensure_ascii=False) + capsys.readouterr().out)


def test_a_cut_retry_at_start_tails_its_turn_on_the_start_diag_line(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """비밀번호를 보내기 전에 끊긴 시작 다시 시도는 결과 칸 `retry` 에 그 시도의 차례를 싣고
    「서버 시작 점검」 진단 줄 끝에 「다시 시도 n/3」 이 붙는다(Admin 진단 줄과 같은 꼴). 처음
    시도(차례 0) · 옛 파일(칸 없음) · 꼴이 어긋난 값은 꼬리가 없다."""
    credentials = place / "config" / ".credential"
    diag = report_contract.ChildDiag(-9, "SIGKILL", 0.8, "import", "", "-", "-")
    result = replace(
        bdq_login.LoginResult(bdq_login.OUTCOME_UNAVAILABLE, bdq_login.REASON_IMPORT_KILLED),
        diag=diag,
    )
    started = bdq_login.StartLogin(
        "unavailable", bdq_login.REASON_IMPORT_KILLED, result=result, stored=_stored(), retry=2
    )

    report = _check(
        {**ALL_ENVIRONMENT, KEY_ENV: new_key()}, credentials, start_login=_login_stub(started)
    )

    assert _cell(report)["retry"] == 2
    parsed = report_contract.parse_report(report)
    assert parsed is not None and parsed.bdq_login is not None
    assert parsed.bdq_login.retry == 2
    step = report_contract.login_step(parsed.bdq_login)
    assert step == report_contract.StartStep("failed", "못 함 — 불러오는 중 끊김 · 예비 토큰")
    label = f"**{report_contract.BDQ_LOGIN_LABEL} 진단**"
    lines = container_start_check.fact_lines(parsed)
    assert lines[-1] == f"{label} · {literal_markdown(diag.text)} · 다시 시도 2/3"
    _assert_no_login_secret(json.dumps(report, ensure_ascii=False) + capsys.readouterr().out)
    for odd in (0, None, True, -1, 99, "2"):
        cell = {**_cell(report), "retry": odd}
        if odd is None:
            del cell["retry"]
        other = report_contract.parse_report({**report, "bdq_login": cell})
        assert other is not None and other.bdq_login is not None
        assert other.bdq_login.retry == 0, odd
        assert container_start_check.fact_lines(other)[-1] == (
            f"{label} · {literal_markdown(diag.text)}"
        )


def test_the_child_diag_is_read_leniently() -> None:
    """진단 칸의 꼴이 어긋난 값은 그 값만 비운다 — 화면에 값이 실리지 않게."""
    assert report_contract.parse_child(None) is None
    assert report_contract.parse_child("exit=0") is None
    found = report_contract.parse_child(
        {
            "exit": True,
            "signal": "kill me",
            "sec": -1,
            "stage": "done",
            "stderr": "bad kind with spaces",
            "bigdataquery": "2.5.0 beta",
            "getpass_asterisk": "?",
        }
    )
    assert found == report_contract.ChildDiag(getpass_asterisk="?")
    big = report_contract.parse_child({"exit": 3221225477, "sec": 5.678})
    assert big == report_contract.ChildDiag(exit_code=3221225477, seconds=5.7)


@pytest.mark.parametrize(
    ("started", "row"),
    [
        (
            bdq_login.StartLogin(
                "rejected",
                bdq_login.REASON_TOKEN_UNCHANGED,
                result=bdq_login.LoginResult("rejected", bdq_login.REASON_TOKEN_UNCHANGED),
                stored=_stored(),
            ),
            ("failed", "멈춤 — 토큰이 바뀌지 않음 · 예비 토큰"),
        ),
        (
            bdq_login.StartLogin(
                "rejected",
                bdq_login.REASON_LOGIN_RAISED,
                result=bdq_login.LoginResult("rejected", bdq_login.REASON_LOGIN_RAISED),
                stop_write="write_failed:auth_rejected",
                stored=_stored(),
            ),
            ("failed", "멈춤 — 로그인 예외 · 멈춤 저장 못 함 · 예비 토큰"),
        ),
        (
            bdq_login.StartLogin(
                "unreached",
                bdq_login.REASON_CONNECTION,
                result=bdq_login.LoginResult("unreached", bdq_login.REASON_CONNECTION),
                stored=_stored(),
            ),
            ("failed", "닿지 못함 — 연결 실패 · 예비 토큰"),
        ),
        (
            bdq_login.StartLogin(
                "unavailable",
                bdq_login.REASON_IMPORT_FAILED,
                result=bdq_login.LoginResult("unavailable", bdq_login.REASON_IMPORT_FAILED),
                stored=_stored(),
            ),
            ("failed", "못 함 — 패키지를 불러오지 못함 · 예비 토큰"),
        ),
        (
            bdq_login.StartLogin(
                "stopped", bdq_login.REASON_TOKEN_UNCHANGED, stored=_stored(store.STATE_STOPPED)
            ),
            ("failed", "멈춤 — 토큰이 바뀌지 않음 · 예비 토큰"),
        ),
    ],
    ids=["거절", "거절-저장 못 함", "닿지 못함", "패키지 없음", "멈춤"],
)
def test_other_outcomes_take_the_fallback_under_the_stored_account(
    place: Path,
    capsys: pytest.CaptureFixture[str],
    started: bdq_login.StartLogin,
    row: tuple[str, str],
) -> None:
    """성공이 아니면 예비 토큰 길이다 — 파일 이름은 계정 하나의 원천(저장된 계정)이다. 저장된 계정
    ID 는 결과 파일 · 출력에 앞 두 글자도 없다(파일 자리는 통째로 가린다). 요청자 계정 칸은 CD
    환경변수 값의 것이다."""
    credentials = place / "config" / ".credential"
    environ = {**ALL_ENVIRONMENT, KEY_ENV: new_key()}

    report = _check(environ, credentials, start_login=_login_stub(started))

    token_path = credentials / f"bigdataquery.token.{ACCOUNT}"
    assert token_path.read_text(encoding="utf-8") == FAKE_BDQ_TOKEN
    assert not (credentials / f"bigdataquery.token.{FAKE_BDQ_USER}").exists()
    token_file = report["token_file"]
    assert isinstance(token_file, dict)
    assert str(token_file["path"]).endswith("bigdataquery.token.***")
    user_name = report["user_name"]
    assert isinstance(user_name, dict) and user_name["masked"] == "fa***"
    printed = capsys.readouterr().out
    _assert_no_login_secret(json.dumps(report, ensure_ascii=False) + printed)
    read = report_contract.read_container_start_report()
    assert read is not None and read.bdq_login is not None
    step = report_contract.login_step(read.bdq_login)
    assert step is not None and (step.status, step.reason) == row
    assert report_contract.report_verdict(read) == "실패 있음"


def test_an_unexpected_failure_keeps_only_the_kind_and_takes_the_fallback(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """로그인 단계가 예상하지 못한 예외로 멈추면 종류 이름만 남기고 예비 토큰 길로 간다 — 예외
    문구(풀린 값이 들 수 있다)는 어디에도 없다. 그 전에 풀어 둔 한 벌이 있으면 파일 이름은 그
    계정."""

    def explode(_environ: Mapping[str, str], _folder: Path) -> bdq_login.StartLogin:
        store.remember(_stored())
        raise RuntimeError(f"leak {ACCOUNT} {PASSWORD}")

    credentials = place / "config" / ".credential"
    report = _check({**ALL_ENVIRONMENT, KEY_ENV: new_key()}, credentials, start_login=explode)

    cell = _cell(report)
    assert (cell["status"], cell["reason"], cell["error_kind"]) == (
        report_contract.LOGIN_ERROR,
        bdq_login.REASON_UNEXPECTED,
        "RuntimeError",
    )
    assert (credentials / f"bigdataquery.token.{ACCOUNT}").is_file()
    _assert_no_login_secret(json.dumps(report, ensure_ascii=False) + capsys.readouterr().out)


def test_the_key_reaches_the_app_but_no_child_process_or_output(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """키는 앱이 저장 · 다시 로그인에 쓰므로 앱 환경에는 넘긴다(`APP_WITHHELD` 밖 — 앱 환경의 그
    이름들은 「시작 스크립트가 안 돎」 표지다). 하위 프로세스(import 확인 · pip)와 출력 · 결과
    파일에는 없다."""
    key = new_key()
    runner = FakeRunner([_probe("ok", "9.9.9")])

    report, fake_exec = _main(place, {**ALL_ENVIRONMENT, KEY_ENV: key}, runner)

    [(_file, _args, app_env)] = fake_exec.calls
    assert app_env[KEY_ENV] == key
    assert runner.envs and all(KEY_ENV not in env for env in runner.envs)
    assert key not in json.dumps(report, ensure_ascii=False) + capsys.readouterr().out
    assert _cell(report)["key"] == report_contract.LOGIN_KEY_OK


def test_a_bad_key_is_named_on_the_line_without_its_value(
    place: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """키 꼴(Fernet)이 아니면 기능이 서지 않는다 — 칸의 키 검사 결과와 표 줄(실패 「꺼짐 — 키 꼴이
    틀림」)에 이름만, 값은 없다. 버킷에 묻지 않는다."""
    bad = "demo-not-a-fernet-key-0123456789"
    credentials = place / "config" / ".credential"
    with running_mock() as (mock, endpoint):
        environ = {
            **ALL_ENVIRONMENT,
            **s3_environment(mock, endpoint),
            MODE_ENV: "managed",
            KEY_ENV: bad,
        }
        report = _check(environ, credentials)
        assert mock.requests == []
    cell = _cell(report)
    assert (cell["status"], cell["reason"], cell["key"]) == ("off", "bad_key", "bad_key")
    read = report_contract.read_container_start_report()
    assert read is not None and read.bdq_login is not None
    assert report_contract.login_step(read.bdq_login) == report_contract.StartStep(
        report_contract.STATUS_FAILED, "꺼짐 — 키 꼴이 틀림"
    )
    assert bad not in json.dumps(report, ensure_ascii=False) + capsys.readouterr().out


# --- 끝까지 — 가짜 패키지 + 가짜 S3 ---------------------------------------------------------------


@pytest.fixture()
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeBdq:
    return use_fake_bdq(monkeypatch, tmp_path)


def _managed(mock: object, endpoint: str, key: str) -> dict[str, str]:
    assert hasattr(mock, "bucket")
    return {
        **os.environ,
        **ALL_ENVIRONMENT,
        **s3_environment(mock, endpoint),  # type: ignore[arg-type]
        MODE_ENV: "managed",
        KEY_ENV: key,
    }


def test_a_stored_account_logs_in_once_at_start_and_the_fallback_is_not_written(
    place: Path, fake: FakeBdq, capsys: pytest.CaptureFixture[str]
) -> None:
    """`managed` + 키 + 상태 `ok` 객체 — 시작에 한 번 로그인하고(`login()` 1번) 패키지가 쓴 새
    토큰(저장된 계정 이름)을 남긴다. 예비 토큰 값은 쓰이지 않는다."""
    key = new_key()
    with running_mock() as (mock, endpoint):
        store.save_login(
            target_of(mock, endpoint), key.encode(), LoginSecret(ACCOUNT, PASSWORD), ADMIN_ID
        )
        store.forget_state()
        report = _check(_managed(mock, endpoint, key), fake.credential_dir)
    assert fake.logins() == 1
    assert fake.token_path(ACCOUNT).read_text(encoding="ascii") != FAKE_BDQ_TOKEN
    assert not fake.token_path(FAKE_BDQ_USER).exists()
    cell = _cell(report)
    assert cell["status"] == "ok"
    minutes = cell["remaining_minutes"]
    assert isinstance(minutes, int) and minutes > bdq_login.REMAINING_WARNING_MINUTES
    _assert_no_login_secret(json.dumps(report, ensure_ascii=False) + capsys.readouterr().out)


def test_a_rejected_start_stores_the_stop_and_the_next_start_does_not_log_in(
    place: Path, fake: FakeBdq
) -> None:
    """틀린 비밀번호 — 시작이 거절을 보면 객체에 멈춤을 쓰고 예비 토큰 길로 간다. 다시
    띄워도(프로세스
    상태 없음) 로그인하지 않는다 — `login()` 은 처음 한 번뿐이다."""
    key = new_key()
    with running_mock() as (mock, endpoint):
        target = target_of(mock, endpoint)
        store.save_login(target, key.encode(), LoginSecret(ACCOUNT, WRONG_PASSWORD), ADMIN_ID)
        store.forget_state()
        environ = _managed(mock, endpoint, key)
        first = _check(environ, fake.credential_dir)
        assert json.loads(mock.objects[store.OBJECT_KEY])["state"] == "stopped"
        for _ in range(2):
            bdq_login.forget_state()
            again = _check(environ, fake.credential_dir)
            assert _cell(again)["status"] == "stopped"
        puts = requests_on(mock, store.OBJECT_KEY).count("PUT")
        assert puts == 3, "저장 한 번 + 시도 표시 한 번 + 멈춤 한 번"
    assert _cell(first)["status"] == "rejected" and _cell(first)["stop_write"] == ""
    assert fake.logins() == 1
    assert fake.token_path(ACCOUNT).read_text(encoding="utf-8") == FAKE_BDQ_TOKEN


# --- 결과 칸 읽기 · 표 줄 -------------------------------------------------------------------------


def test_the_login_cell_is_read_leniently() -> None:
    """칸이 없거나 갈래 낱말이 어긋나면 `None`(옛 파일), 꼴이 어긋난 나머지 칸은 그 칸만 비운다 —
    화면 · 알림에 값이 실리지 않게."""
    assert report_contract.parse_login(None) is None
    assert report_contract.parse_login({"status": "maybe"}) is None
    login = report_contract.parse_login(
        {
            "status": "rejected",
            "reason": "Token Unchanged!",
            "key": "secret",
            "remaining_minutes": -5,
            "error_kind": "bad kind with spaces",
            "failure_kind": "auth_rejected",
            "stop_write": "write_failed:auth_rejected",
        }
    )
    assert login == report_contract.LoginStart(
        status="rejected",
        failure_kind="auth_rejected",
        stop_write="write_failed:auth_rejected",
    )


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ({"status": "off", "reason": "not_managed"}, None),
        ({"status": "off", "reason": "no_key"}, ("skipped", "꺼짐 — 키 없음")),
        ({"status": "absent", "reason": "no_object"}, ("skipped", "계정 없음")),
        (
            {"status": "absent", "reason": "unread", "failure_kind": "timeout"},
            ("failed", "계정 없음 — 읽지 못함(timeout)"),
        ),
        ({"status": "ok", "remaining_minutes": 25}, ("ok", "정상 · 남은 0시간 25분")),
        ({"status": "ok"}, ("ok", "정상 · 남은 시간 모름")),
        (
            {"status": "ok", "remaining_minutes": 479, "stop_write": "write_failed:timeout"},
            ("failed", "정상 · 남은 7시간 59분 · 결과 저장 못 함"),
        ),
        (
            {"status": "unconfirmed", "reason": "remaining_unknown"},
            ("failed", "확인 못 함 — 남은 시간 모름"),
        ),
        (
            {"status": "unavailable", "reason": "unguarded", "stop_write": "write_failed:x"},
            ("failed", "못 함 — 시도 표시를 쓰지 못함 · 결과 저장 못 함 · 예비 토큰"),
        ),
        (
            {"status": "stopped", "reason": "miss_limit"},
            ("failed", "멈춤 — 닿지 못함 · 확인 못 함 연속 상한 · 예비 토큰"),
        ),
        (
            {"status": "stopped", "reason": "attempting"},
            ("failed", "멈춤 — 시도 결과를 적지 못함 · 예비 토큰"),
        ),
        (
            {"status": "error", "reason": "unexpected", "error_kind": "OSError"},
            ("failed", "예상하지 못한 실패(OSError) · 예비 토큰"),
        ),
    ],
)
def test_the_login_line_is_status_words_only(
    cell: dict[str, object], expected: tuple[str, str] | None
) -> None:
    login = report_contract.parse_login(cell)
    assert login is not None
    step = report_contract.login_step(login)
    assert (None if step is None else (step.status, step.reason)) == expected


def test_the_start_check_table_gains_the_login_row_only_where_it_is_shown() -> None:
    """「서버 시작 점검」 표 — `managed` 서버에만 「BDQ 자동 로그인」 줄이 서고 판정에도 든다. 옛
    파일
    · `managed` 아닌 서버는 줄이 없다."""
    from capa_simulation.components.container_start_check import login_rows

    step = report_contract.StartStep(status="ok", reason="정상")
    base = report_contract.ContainerStartReport(
        written_at="",
        steps={name: step for name in report_contract.STEPS},
        bigdataquery_version=None,
        token_file_exists=None,
        token_file_modified_at=None,
        user_name_masked=None,
        missing_environment=(),
        pip_tail=(),
    )
    off = report_contract.LoginStart("off", "not_managed")
    no_key = report_contract.LoginStart("off", "no_key")
    stopped = report_contract.LoginStart("stopped", "token_unchanged")

    assert login_rows(base) == []
    assert login_rows(_with(base, off)) == []
    assert report_contract.report_verdict(_with(base, off)) == "모두 정상"
    # 키 없는 `managed` 서버(이관을 마친 지금의 운영)는 줄은 서되 제목 판정에 세지 않는다 — 키도
    # 객체도 없으면 지금과 같다(잠든 불변식).
    assert login_rows(_with(base, no_key)) == [("BDQ 자동 로그인", "건너뜀", "꺼짐 — 키 없음")]
    assert report_contract.report_verdict(_with(base, no_key)) == "모두 정상"
    assert login_rows(_with(base, stopped)) == [
        ("BDQ 자동 로그인", "실패", "멈춤 — 토큰이 바뀌지 않음 · 예비 토큰")
    ]
    assert report_contract.report_verdict(_with(base, stopped)) == "실패 있음"


def test_the_key_alone_does_not_make_a_missing_report_notice() -> None:
    """자동 로그인 키는 CD 서버를 가르는 데 쓰지 않는다 — 키를 넣고 `app.py` 로 띄운 자리(개발 ·
    WebIDE 시험)에 「결과 파일이 없다」 안내가 붙지 않는다(운영 앱은 기동 때 키를 환경에서 뺀다)."""
    assert report_contract.BDQ_SECRET_KEY_ENV not in report_contract.CD_ONLY_ENVIRONMENT
    assert report_contract.BDQ_SECRET_KEY_ENV not in report_contract.APP_WITHHELD_ENVIRONMENT
    assert report_contract.missing_report_notice({report_contract.BDQ_SECRET_KEY_ENV: "x"}) is None


def _with(
    report: report_contract.ContainerStartReport, login: report_contract.LoginStart
) -> report_contract.ContainerStartReport:
    from dataclasses import replace

    return replace(report, bdq_login=login)


# --- 계정 하나의 원천 — 앱은 저장 객체 기억을 읽는다 ---------------------------------------


def test_the_token_file_follows_the_stored_account_and_falls_back_after_forgetting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """앱 프로세스가 기억한 저장된 계정이 있으면 토큰 파일 이름 · 지금 토큰 · 「토큰 넣기」 모두 그
    ID 를 쓴다(`CAPA_BDQ_USER_NAME` 과 달라도). 지우면(기억 「없음」) 환경변수 계정으로 돌아간다. S3
    에 묻지 않는다."""
    folder = tmp_path / "credential"
    monkeypatch.setattr(bdq_token, "CREDENTIAL_DIR", folder)
    monkeypatch.setenv(report_contract.BDQ_USER_NAME_ENV, FAKE_BDQ_USER)

    assert bdq_token.account_name() == FAKE_BDQ_USER
    store.remember(_stored())
    assert bdq_token.account_name() == ACCOUNT
    assert bdq_token.current_token().source == "missing"
    assert bdq_token.install_token("demo-token-for-the-stored-account").status == "written"
    assert (folder / f"bigdataquery.token.{ACCOUNT}").is_file()
    assert bdq_token.current_token().source == "file"

    monkeypatch.delenv(report_contract.BDQ_USER_NAME_ENV)
    assert bdq_token.blocked_reason() is None, "저장된 계정이 있으면 환경변수 없이도 이름이 선다"

    store.remember(None)
    monkeypatch.setenv(report_contract.BDQ_USER_NAME_ENV, FAKE_BDQ_USER)
    assert bdq_token.account_name() == FAKE_BDQ_USER
    assert bdq_token.current_token().source == "missing"


# --- 앱 기동 — 키를 쥐고 빼고 · 한 번 읽고 · 시작 거절을 넘겨받는다 ----------------------


def _start_report(path: Path, cell: Mapping[str, object] | None) -> None:
    steps = {name: {"status": "ok", "reason": "정상"} for name in report_contract.STEPS}
    data: dict[str, object] = {"version": 1, "written_at": "", "steps": steps}
    if cell is not None:
        data["bdq_login"] = dict(cell)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_the_app_takes_the_key_out_of_its_environment_and_reads_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """앱 기동(`start_in_app`) — 키를 쥐고 프로세스 환경에서 뺀 뒤에도 기능은 선다(쥔 키). 저장
    객체는 기동에 한 번 읽어 두고, 화면 회차의 상태 보기(`current_view`)는 S3 에 묻지 않는다."""
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "start.json")
    _start_report(tmp_path / "start.json", {"status": "ok", "remaining_minutes": 470})
    key = new_key()
    with running_mock() as (mock, endpoint):
        target = target_of(mock, endpoint)
        store.save_login(target, key.encode(), LoginSecret(ACCOUNT, PASSWORD), ADMIN_ID)
        store.forget_state()
        monkeypatch.setattr(store, "app_target", lambda: target)
        monkeypatch.setenv(MODE_ENV, "managed")
        monkeypatch.setenv(KEY_ENV, key)

        bdq_login.start_in_app(os.environ)

        assert KEY_ENV not in os.environ
        assert store.secret_key() == key.encode() and store.availability() is None
        gets = requests_on(mock, store.OBJECT_KEY).count("GET")
        for _ in range(3):
            assert bdq_login.current_view().state == "ok"
        assert requests_on(mock, store.OBJECT_KEY).count("GET") == gets == 1
    assert store.effective_account() == ACCOUNT


@pytest.mark.parametrize("status", ["rejected", "error"])
def test_the_app_takes_over_a_start_stop_that_was_not_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    """시작이 거절을 보고도 멈춤 표시를 쓰지 못했거나(객체는 아직 `ok`) 로그인 단계가 예상하지
    못하게
    멈췄으면, 앱은 그 한 벌을 프로세스에서 멈춘다 — 첫 토큰 예외가 같은 계정으로 또 로그인하지 않게.
    거절은 멈춤 표시를 다시 써 본다."""
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "start.json")
    cell = {"status": status, "reason": "token_unchanged", "stop_write": "write_failed:timeout"}
    _start_report(tmp_path / "start.json", cell)
    key = new_key()
    spawned: list[object] = []
    monkeypatch.setattr(bdq_login, "attempt_login", lambda *a, **k: spawned.append(a))
    with running_mock() as (mock, endpoint):
        target = target_of(mock, endpoint)
        store.save_login(target, key.encode(), LoginSecret(ACCOUNT, PASSWORD), ADMIN_ID)
        store.forget_state()
        monkeypatch.setattr(store, "app_target", lambda: target)
        monkeypatch.setenv(MODE_ENV, "managed")
        monkeypatch.setenv(KEY_ENV, key)

        bdq_login.start_in_app(os.environ)

        assert bdq_login.status().state == "stopped"
        assert bdq_login.current_view().state == "stopped"
        saved = json.loads(mock.objects[store.OBJECT_KEY])["state"]
        assert saved == ("stopped" if status == "rejected" else "ok")
        recovery = bdq_login.recover_after_token_failure(bdq_login.token_digest(ACCOUNT))
        assert not recovery.retry
    assert spawned == []


@pytest.mark.parametrize("same", [True, False], ids=["같은 한 벌", "다시 넣은 한 벌"])
def test_the_app_holds_a_start_rejection_only_for_the_login_it_judged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, same: bool
) -> None:
    """앱 기동이 넘겨받는 시작 거절은 시작이 판정한 한 벌(넣은 시각 `entered_at`)에만 — 그 뒤 다시
    넣은 계정에는 멈춤을 쓰지 않는다."""
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "start.json")
    key = new_key()
    spawned: list[object] = []
    monkeypatch.setattr(bdq_login, "attempt_login", lambda *a, **k: spawned.append(a))
    with running_mock() as (mock, endpoint):
        target = target_of(mock, endpoint)
        written = store.save_login(target, key.encode(), LoginSecret(ACCOUNT, PASSWORD), ADMIN_ID)
        assert written.stored is not None
        judged = written.stored.entered_at if same else "2026-01-01T09:00:00+09:00"
        cell = {"status": "rejected", "reason": "token_unchanged", "entered_at": judged}
        _start_report(tmp_path / "start.json", cell)
        store.forget_state()
        monkeypatch.setattr(store, "app_target", lambda: target)
        monkeypatch.setenv(MODE_ENV, "managed")
        monkeypatch.setenv(KEY_ENV, key)

        bdq_login.start_in_app(os.environ)

        assert bdq_login.current_view().state == ("stopped" if same else "ok")
        saved = json.loads(mock.objects[store.OBJECT_KEY])["state"]
        assert saved == ("stopped" if same else "ok")
    assert spawned == []


def test_the_app_start_without_a_key_asks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "start.json")
    with running_mock() as (mock, endpoint):
        monkeypatch.setattr(store, "app_target", lambda: target_of(mock, endpoint))
        monkeypatch.setenv(MODE_ENV, "managed")
        bdq_login.start_in_app(os.environ)
        assert mock.requests == []
    assert bdq_login.current_view().state == "off"


def test_a_start_stop_holds_even_when_the_boot_read_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """시작이 거절을 보고도 멈춤 표시를 쓰지 못했는데 앱의 기동 읽기마저 실패해도, 뒤에 다시 읽은
    객체(`ok`)로 첫 토큰 예외가 로그인하지 않는다 — 멈춤은 읽기와 따로 들고 있다가 그 자리에서
    표시를 써 본다. 관리자가 폼으로 다시 넣어 성공하면 풀린다."""
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", tmp_path / "start.json")
    cell = {"status": "rejected", "reason": "token_unchanged", "stop_write": "write_failed:x"}
    _start_report(tmp_path / "start.json", cell)
    key = new_key()
    spawned: list[object] = []
    with running_mock() as (mock, endpoint):
        target = target_of(mock, endpoint)
        store.save_login(target, key.encode(), LoginSecret(ACCOUNT, PASSWORD), ADMIN_ID)
        store.forget_state()
        monkeypatch.setattr(store, "app_target", lambda: target)
        monkeypatch.setattr(store, "UNREAD_RETRY_SECONDS", 0.0)
        monkeypatch.setenv(MODE_ENV, "managed")
        monkeypatch.setenv(KEY_ENV, key)
        mock.force_on("GET", store.OBJECT_KEY, times=1)
        monkeypatch.setattr(bdq_login, "attempt_login", lambda *a, **k: spawned.append(a))

        bdq_login.start_in_app(os.environ)

        seen = store.peek_state()
        assert seen is not None and seen.reason == store.REASON_UNREAD
        assert bdq_login.current_view().state == "stopped"
        recovery = bdq_login.recover_after_token_failure(bdq_login.token_digest(ACCOUNT))
        assert not recovery.retry and spawned == []
        assert json.loads(mock.objects[store.OBJECT_KEY])["state"] == "stopped"
        assert bdq_login.status().state == "stopped"
        assert bdq_login.current_view().stop_reason == "token_unchanged"

        monkeypatch.setattr(bdq_login, "attempt_login", lambda *a, **k: bdq_login.LoginResult("ok"))
        form = bdq_login.login_from_form(
            ACCOUNT, PASSWORD, ADMIN_ID, target=target, key=key.encode()
        )
        assert form.saved
        assert bdq_login.status().state == "ok" and bdq_login.current_view().state == "ok"
