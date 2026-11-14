# Purpose: 앱 시작 실패 판의 갈래 판정 · 그리기 · 진짜 app.py 배선 · 입장 화면 표지를 지킨다.

"""`components/boot_stop.py`(2026-11-13 「앱 대신 뜨는 화면」 보드 카드 p1-boot · d12 (가)).

부트스트랩이 실패하면 쉬운 경고 한 줄 · 「다시 시도」(판 올리기 실패는 없음) · 문의 캡션 · 참고
줄(끝에 오류 종류 이름) · 접힌 「관리자용 진단」 이 선다. 프로세스 번호 · 서버 파일 경로 · 원문은
접힌 진단 안에만 있고, 그 진단은 관리자 몫(`admin_view.admin_notes_visible`)에만 선다. 입장 화면이
읽는 스타일 표지도 함께 간다.
"""

from __future__ import annotations

import errno
import os
import re
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from sso_support import sso_environ, use_config
from streamlit.testing.v1 import AppTest

from capa_simulation.auth import names, runtime
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import admin_view, boot_stop, sso_identity, stop_panel
from capa_simulation.components.diagnostic_copy import ADMIN_DIAGNOSTIC_LABEL
from capa_simulation.page_bootstrap import ADMIN_TAIL, bootstrap_error_message, screen_error_short
from capa_simulation.persistence._migration_core import (
    MigrationChanged,
    MigrationFailed,
    apply_migrations_to,
)
from capa_simulation.persistence._sql_helpers import lock_holder_pid
from capa_simulation.settings import APP_CONTACT_EMAIL_ENV

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
INTRO_ASSETS = PROJECT_ROOT / "src" / "capa_simulation" / "components" / "intro_overlay_assets"
SECRET_PATH = "/srv/demo-secret/capa_simulation.duckdb"


def _lock(pid: int) -> duckdb.IOException:
    return duckdb.IOException(
        f'IO Error: Could not set lock on file "{SECRET_PATH}": Conflicting lock is held in '
        f"/usr/bin/python3 (PID {pid}) by user demo."
    )


def _failed_sql() -> MigrationFailed:
    """새 SQL 이 Catalog 오류로 실패해 판 올리기 실패로 감싼 꼴(`apply_migrations_to`)."""
    try:
        raise MigrationFailed("DuckDB 마이그레이션을 적용하지 못했습니다: 0099_demo.sql") from (
            duckdb.CatalogException("Catalog Error: Table with name demo_gone does not exist!")
        )
    except MigrationFailed as error:
        return error


@pytest.mark.parametrize(
    ("make", "code", "retry"),
    [
        (lambda: _lock(424242), boot_stop.LOCKED, True),
        (lambda: _lock(os.getpid()), boot_stop.LOCKED, True),
        (
            lambda: MigrationChanged("이미 적용된 DuckDB 마이그레이션이 변경되었습니다: 0001.sql"),
            boot_stop.MIGRATION_FAILED,
            False,
        ),
        (_failed_sql, boot_stop.MIGRATION_FAILED, False),
        (lambda: OSError(errno.ENOSPC, "No space left on device"), boot_stop.DISK_FULL, True),
        (
            lambda: duckdb.IOException("IO Error: Could not write file: No space left on device"),
            boot_stop.DISK_FULL,
            True,
        ),
        (lambda: PermissionError(errno.EACCES, "Permission denied"), boot_stop.PERMISSION, True),
        (
            lambda: duckdb.IOException(
                f'IO Error: Cannot open file "{SECRET_PATH}": Permission denied'
            ),
            boot_stop.PERMISSION,
            True,
        ),
        (
            lambda: duckdb.IOException(
                f'IO Error: Cannot open file "{SECRET_PATH}": Is a directory'
            ),
            boot_stop.CANNOT_OPEN,
            True,
        ),
        (
            lambda: duckdb.IOException("IO Error: Could not write file: Input/output error"),
            boot_stop.OTHER,
            True,
        ),
        (
            lambda: duckdb.CatalogException("Catalog Error: Table x does not exist"),
            boot_stop.OTHER,
            True,
        ),
        (lambda: ValueError("한국어 문장"), boot_stop.OTHER, True),
    ],
)
def test_failures_split_into_the_board_branches(
    make: Callable[[], BaseException], code: str, retry: bool
) -> None:
    """잠김(남 · 자기) → 판 올리기 실패 → 디스크 가득 → 권한 → 열 수 없음 → 그 밖. 판 올리기 실패만
    「다시 시도」 가 없다(다시 해도 같다). 자기 잠김(다시 하면 풀림) · 판 올리기 실패 밖은 모두 「—
    관리자에게 알려 주세요」 로 끝난다 — 열기 · 쓰기 실패는 까닭을 괄호에 싣는다(보드 decided-login
    7)."""
    error = make()
    failure = boot_stop.classify_boot_failure(error)

    assert (failure.code, failure.retry) == (code, retry)
    if code == boot_stop.LOCKED:
        own = lock_holder_pid(error) == os.getpid()
        assert failure.line == (boot_stop.LOCKED_LINE if own else boot_stop.HELD_LINE)
    elif code == boot_stop.MIGRATION_FAILED:
        assert failure.line == boot_stop.UPDATE_LINE
    elif code == boot_stop.OTHER:
        assert failure.line == boot_stop.HELD_LINE
    else:
        word = boot_stop.IO_WORDS[code]
        assert failure.line == f"{boot_stop.LOCKED_LINE}({word}){ADMIN_TAIL}"


@pytest.mark.parametrize(
    ("code", "line"),
    [
        (
            boot_stop.DISK_FULL,
            "지금은 데이터를 열 수 없습니다(디스크가 가득 참) — 관리자에게 알려 주세요",
        ),
        (
            boot_stop.PERMISSION,
            "지금은 데이터를 열 수 없습니다(파일 권한) — 관리자에게 알려 주세요",
        ),
        (
            boot_stop.CANNOT_OPEN,
            "지금은 데이터를 열 수 없습니다(파일을 열 수 없음) — 관리자에게 알려 주세요",
        ),
        (boot_stop.OTHER, "지금은 데이터를 열 수 없습니다 — 관리자에게 알려 주세요"),
    ],
    ids=["disk-full", "permission", "cannot-open", "other"],
)
def test_an_io_failure_asks_for_the_admin_like_the_later_rounds(code: str, line: str) -> None:
    """열기 · 쓰기 실패와 그 밖은 사람이 고칠 수 없다 — 경고가 「…(<까닭>) — 관리자에게 알려
    주세요」 로 뒤 회차 DB 실패 알림의 짧은 글(「…(다른 프로그램이 엶) — 관리자에게 알려
    주세요」)과 같은 꼴이고 「다시 시도」 는 그대로다(보드 decided-login 7)."""
    failure = boot_stop._io_failure(code)

    assert failure.line == line
    assert failure.retry
    later = screen_error_short(bootstrap_error_message(_lock(424242)))
    assert later is not None
    assert re.fullmatch(r".+\(.+\) — 관리자에게 알려 주세요", later)
    assert later.endswith(ADMIN_TAIL) and failure.line.endswith(ADMIN_TAIL)


@pytest.mark.parametrize("own", [False, True], ids=["held-by-another", "own-process"])
def test_the_first_and_later_rounds_ask_the_same_of_a_locked_database(own: bool) -> None:
    """같은 잠김이면 첫 회차(앱 시작 실패 판)와 뒤 회차(화면 DB 실패 알림의 짧은 글)가 일반
    사용자에게 같은 일을 시킨다 — 남이 쥔 잠김은 사람이 고칠 수 없어 둘 다 「— 관리자에게 알려
    주세요」, 이 앱 자신이 정리하는 동안이면 둘 다 다시 하면 풀린다(「다시 시도」 · 새로고침,
    관리자 꼬리 없음 — 카드 p1-boot · p1-no-revision)."""
    error = _lock(os.getpid() if own else 424242)

    first = boot_stop.classify_boot_failure(error)
    later = screen_error_short(bootstrap_error_message(error))

    assert first.retry
    if own:
        assert ADMIN_TAIL not in first.line and later is None
        assert "새로고침" in bootstrap_error_message(error)
    else:
        assert first.line.endswith(ADMIN_TAIL)
        assert later is not None and later.endswith(ADMIN_TAIL)


def test_a_changed_migration_is_still_a_runtime_error() -> None:
    """종류만 따로 두었다 — `RuntimeError` 를 받던 자리는 그대로 받는다."""
    assert issubclass(MigrationChanged, MigrationFailed)
    assert issubclass(MigrationFailed, RuntimeError)


@pytest.fixture
def demo_migrations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """시험 전용 마이그레이션 패키지(저장소 밖 임시 폴더) — SQL 파일을 넣고 이름을 돌려준다."""
    name = f"demo_migrations_{uuid.uuid4().hex[:8]}"
    package = tmp_path / name
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield package
    sys.modules.pop(name, None)


def _apply(package: Path) -> None:
    with duckdb.connect(":memory:") as connection:
        apply_migrations_to(
            connection,
            package=package.name,
            schema="app_meta",
            label="DuckDB",
            database_name="시험 DB",
        )


@pytest.mark.parametrize(
    ("sql", "cause"),
    [
        ("SELEC 1;", duckdb.ParserException),
        ("DROP TABLE demo_gone;", duckdb.CatalogException),
        (
            "CREATE TABLE demo_once (id INTEGER PRIMARY KEY); "
            "INSERT INTO demo_once VALUES (1), (1);",
            duckdb.ConstraintException,
        ),
        ("SELECT CAST('a' AS INTEGER);", duckdb.ConversionException),
    ],
)
def test_a_new_migration_that_fails_as_sql_is_an_update_failure(
    demo_migrations: Path, sql: str, cause: type[duckdb.Error]
) -> None:
    """새 SQL 이 SQL · 데이터 오류로 실패하면 다시 해도 같다 — 판 올리기 실패(「다시 시도」 없음)로
    가른다. 원문은 감싼 DuckDB 오류다(카드 p1-boot · 조사 boot-migration-failed 의 (나))."""
    (demo_migrations / "0001_demo.sql").write_text(sql, encoding="utf-8")

    with pytest.raises(MigrationFailed) as raised:
        _apply(demo_migrations)

    error = raised.value
    assert isinstance(error.__cause__, cause)
    assert str(error) == "DuckDB 마이그레이션을 적용하지 못했습니다: 0001_demo.sql"
    failure = boot_stop.classify_boot_failure(error)
    assert (failure.code, failure.line, failure.retry) == (
        boot_stop.MIGRATION_FAILED,
        boot_stop.UPDATE_LINE,
        False,
    )
    assert boot_stop.original_line(error).startswith(f"{cause.__name__}: ")


def test_an_io_failure_while_migrating_is_not_wrapped(
    demo_migrations: Path, tmp_path: Path
) -> None:
    """입출력 오류는 지나갈 수 있어 감싸지 않는다 — 제 갈래(열 수 없음 · 디스크 가득 등)로 간다."""
    target = tmp_path / "no-such-folder" / "out.csv"
    (demo_migrations / "0001_demo.sql").write_text(
        f"COPY (SELECT 1) TO '{target.as_posix()}';", encoding="utf-8"
    )

    with pytest.raises(duckdb.IOException) as raised:
        _apply(demo_migrations)

    assert not isinstance(raised.value, MigrationFailed)
    assert boot_stop.classify_boot_failure(raised.value).retry


SCRIPT = """
import os

import duckdb

from capa_simulation.components.boot_stop import render_boot_stop

kind = os.environ["BOOT_STOP_KIND"]
if kind == "lock":
    error = duckdb.IOException(
        'IO Error: Could not set lock on file "/srv/demo-secret/capa_simulation.duckdb": '
        "Conflicting lock is held in /usr/bin/python3 (PID 424242) by user demo."
    )
else:
    from capa_simulation.persistence._migration_core import MigrationChanged

    error = MigrationChanged("이미 적용된 DuckDB 마이그레이션이 변경되었습니다: 0001.sql")
render_boot_stop(error)
"""


def _run(kind: str, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.setenv("BOOT_STOP_KIND", kind)
    return AppTest.from_string(SCRIPT, default_timeout=30).run()


def _main_text(app: AppTest) -> str:
    """접힌 진단 밖의 글 — 경고 · 캡션 · 단추 이름."""
    return "\n".join(
        [str(item.value) for item in app.error]
        + [str(item.value) for item in app.caption]
        + [str(item.label) for item in app.button]
    )


def test_a_locked_database_shows_a_plain_line_a_retry_and_folds_the_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(APP_CONTACT_EMAIL_ENV, "help@example.com")
    # 접속 요청 창구 글은 이 판에 싣지 않는다 — 데이터를 열지 못한 실패의 연락처가 아니다.
    monkeypatch.setenv(names.ENV_ACCESS_CONTACT, "데모 창구")

    app = _run("lock", monkeypatch)

    assert not list(app.exception)
    assert [item.value for item in app.error] == [boot_stop.HELD_LINE]
    assert app.error[0].icon == ":material/database_off:"
    [retry] = app.button
    assert (retry.label, retry.key) == (stop_panel.RETRY_LABEL, boot_stop.RETRY_KEY)
    captions = [str(item.value) for item in app.caption]
    assert captions[0] == "문의 help@example.com"
    assert re.fullmatch(
        r"참고 db_locked · \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC · IOException", captions[1]
    )
    # 프로세스 번호 · 서버 파일 경로 · 개발 PC 조치는 접힌 진단 안에만 있다.
    main = _main_text(app)
    assert "PID" not in main and SECRET_PATH not in main
    [fold] = app.expander
    assert fold.label == ADMIN_DIAGNOSTIC_LABEL
    folded = "\n".join(str(item.value) for item in fold.markdown) + "\n".join(
        str(item.value) for item in fold.code
    )
    assert "PID 424242" in folded and SECRET_PATH in folded


def _every_text(app: AppTest) -> str:
    """그려진 모든 글 — 경고 · 캡션 · 단추 이름 · 자리 글 · 코드 칸 · 펼침 이름 · 원문 HTML."""
    parts = [
        *(str(item.value) for item in app.error),
        *(str(item.value) for item in app.caption),
        *(str(item.label) for item in app.button),
        *(str(item.value) for item in app.markdown),
        *(str(item.value) for item in app.code),
        *(str(item.label) for item in app.expander),
        *(str(item.proto.body) for item in app.get("html")),
    ]
    return "\n".join(parts)


def _prod_sso_off() -> None:
    """운영(`APP_ENV=prod`)인데 통합인증이 꺼진 서버 — 관리자 신원이 없다."""
    runtime.reset()
    runtime.start(sso_environ(drop=[names.ENV_CLIENT_ID]))


def _prod_sso_on_as(monkeypatch: pytest.MonkeyPatch, loginid: str) -> None:
    """통합인증이 켜진 운영 서버의 그 사람 회차(진짜 세션 쿠키)."""
    cfg = use_config({names.ENV_ACCESS_ADMINS: "demo.admin", names.ENV_ACCESS_USERS: "demo.user"})
    token, _ = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: {cfg.session_cookie: token})


@pytest.mark.parametrize("audience", ["prod-sso-off", "plain-user"])
def test_someone_outside_the_admin_audience_sees_only_the_kind_name(
    monkeypatch: pytest.MonkeyPatch, audience: str
) -> None:
    """관리자 몫이 아닌 회차(운영인데 통합인증 꺼짐 · 켜진 운영 서버의 일반 사용자)에는 접힌 진단이
    없고 참고 줄 끝의 오류 종류 이름만 있다 — 프로세스 번호 · 서버 파일 경로 · 개발 PC 조치 · 원문이
    어느 칸에도 없다(카드 p1-boot · 보드 d12 (가))."""
    if audience == "prod-sso-off":
        _prod_sso_off()
    else:
        _prod_sso_on_as(monkeypatch, "demo.user")

    app = _run("lock", monkeypatch)

    assert not list(app.exception), [item.message for item in app.exception]
    assert list(app.expander) == []
    shown = _every_text(app)
    for secret in ("PID", "424242", SECRET_PATH, "Conflicting lock", "DB 도구", "IO Error"):
        assert secret not in shown, secret
    assert any(str(item.value).endswith(" · IOException") for item in app.caption)
    assert [item.label for item in app.button] == [stop_panel.RETRY_LABEL]


def test_the_admin_of_a_signed_in_server_gets_the_details_fold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """켜진 운영 서버의 관리자에게는 접힌 진단이 선다 — C-DEP 에는 셸도 로그도 없다."""
    _prod_sso_on_as(monkeypatch, "demo.admin")

    app = _run("lock", monkeypatch)

    [fold] = app.expander
    assert fold.label == ADMIN_DIAGNOSTIC_LABEL
    folded = "\n".join(str(item.value) for item in fold.code)
    assert "PID 424242" in folded and SECRET_PATH in folded


def test_a_failing_admin_check_falls_back_to_no_details(monkeypatch: pytest.MonkeyPatch) -> None:
    """마지막 자리 — 관리자 몫 판정이 무엇을 내도 판은 서고 진단은 닫힌 쪽(없음)으로 물러선다."""

    def broken() -> bool:
        raise RuntimeError("판정 실패")

    monkeypatch.setattr(admin_view, "admin_notes_visible", broken)

    app = _run("lock", monkeypatch)

    assert not list(app.exception), [item.message for item in app.exception]
    assert list(app.expander) == []
    assert "PID" not in _every_text(app)


def test_a_changed_migration_offers_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(APP_CONTACT_EMAIL_ENV, raising=False)

    app = _run("migration", monkeypatch)

    assert [item.value for item in app.error] == [boot_stop.UPDATE_LINE]
    assert list(app.button) == [], "다시 해도 같아 「다시 시도」 를 두지 않는다"
    captions = [str(item.value) for item in app.caption]
    assert len(captions) == 1 and captions[0].startswith("참고 migration_failed · ")


def test_the_intro_marker_carries_the_line_without_taking_a_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """입장 화면 JS 가 읽는 표지는 스타일만 든 칸(자리를 먹지 않는다)이고 경고 한 줄을 값으로
    싣는다."""
    app = _run("lock", monkeypatch)

    bodies = [str(item.proto.body) for item in app.get("html")]
    assert bodies[0] == f'<style {boot_stop.BOOT_STOP_ATTRIBUTE}="{boot_stop.HELD_LINE}"></style>'
    tricky = boot_stop.BootFailure("x", 'a"<b>', retry=True)
    assert boot_stop.boot_marker_html(tricky) == (
        f'<style {boot_stop.BOOT_STOP_ATTRIBUTE}="a&quot;&lt;b&gt;"></style>'
    )


def test_the_intro_script_reads_the_same_marker_and_shows_the_failure() -> None:
    """입장 화면 JS 는 같은 속성 이름으로 표지를 읽고, 그릴 때마다 다시 읽어 붙들지 않는다. 실패면
    상태 낱말 「열지 못함」 · 멈춘 칸의 실패 색 + 낱말 · 상태 줄 아래 까닭 한 줄이고, Summary 는
    잠근 채 까닭 풍선이며 장면의 웨이퍼는 끝남으로 펼치지 않는다(멈춤)."""
    script = (INTRO_ASSETS / "intro.js").read_text(encoding="utf-8")
    page = (INTRO_ASSETS / "intro.html").read_text(encoding="utf-8")
    css = (INTRO_ASSETS / "intro.css").read_text(encoding="utf-8")

    assert f'const BOOT_STOP_ATTRIBUTE = "{boot_stop.BOOT_STOP_ATTRIBUTE}";' in script
    render = script.split("  function render() {", 1)[1].split("\n  }\n", 1)[0]
    assert "const stopped = ready ? bootStopLine() : null;" in render
    assert 'status.textContent = text.failed || "";' in render
    assert "reason.textContent = stopped" in render
    assert 'li.className = fail ? "failed"' in render
    # 멈춘 칸은 신호로 끝낸 단계 다음 칸이다 — 실행 끝만으로 앞 칸을 끝남으로 그리지 않는다.
    assert "Math.min(signalledSteps(), items.length - 1)" in render
    poll = script.split("  function poll() {", 1)[1].split("\n  }\n", 1)[0]
    assert (
        "if (ready && bootStopLine() !== shownStop) {\n      render();\n      sendProgress();"
        in poll
    )
    # 실패면 Summary 는 잠근 채 까닭(경고 한 줄)을 풍선으로 단다 — 「공식버전 요약을 봅니다」 를
    # 말하지 않는다(UI-INP-07).
    assert "summaryButton.disabled = failed || !canSummary();" in render
    assert 'if (failed) summaryButton.title = stopped || text.failed || "";' in render
    # 장면에도 끝남(ready) 대신 멈춤(halted)과 신호로 끝낸 단계 수를 보낸다 — 웨이퍼가 다 펼쳐지지
    # 않는다.
    send = script.split("  const sendProgress = () => {", 1)[1].split("\n  };\n", 1)[0]
    assert "const halted = ready && bootStopLine() !== null;" in send
    assert "reached: halted ? signalledSteps() : reached," in send
    assert "ready: ready && !halted," in send
    assert "halted = !!m.halted;" in script
    assert "settle += ((ready || halted ? 1 : 0) - settle)" in script
    assert "settle = ready || halted ? 1 : 0;" in script
    assert "shownStop = stopped;" in render
    assert '<p class="reason" hidden></p>' in page
    assert ".steps li.failed .track {\n  background: var(--fail);" in css
    assert '"--fail": palette["die-short"],' in script


def test_the_intro_text_names_the_failure() -> None:
    from capa_simulation.components import intro_overlay

    text = intro_overlay._data()["text"]
    assert (text["failed"], text["failed_step"]) == ("열지 못함", "멈춤")


@pytest.fixture
def real_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """부트스트랩이 잠김으로 실패하는 `app.py`. 브라우저로 보내는 컴포넌트만 바꿔 끼운다."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.scenario_activation as scenario_activation
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    monkeypatch.setattr(
        month_range_picker, "_MONTH_RANGE_APPLY", lambda **kwargs: SimpleNamespace(apply=None)
    )
    calls: list[str] = []
    real = scenario_activation.bootstrap_latest_official_scenario

    def bootstrap(database_path: str) -> bool:
        calls.append(database_path)
        if len(calls) == 1:
            raise _lock(424242)
        return real(database_path)

    monkeypatch.setattr(scenario_activation, "bootstrap_latest_official_scenario", bootstrap)
    return AppTest.from_file(str(APP_PATH), default_timeout=300)


def test_the_real_app_stops_on_the_panel_and_retries_into_home(real_app: AppTest) -> None:
    """진짜 `app.py` — 첫 회차는 멈춤 판(머리 띠 아래), 「다시 시도」 를 누르면 다시 열어 HOME 이
    선다(부트스트랩은 실패한 회차에 「해 봤다」 표지를 세우지 않는다)."""
    app = real_app.run()

    assert not list(app.exception), [item.message for item in app.exception]
    assert [item.value for item in app.error] == [boot_stop.HELD_LINE]
    assert "Capa LOB Summary" not in [item.value for item in app.title]

    app = app.button(key=boot_stop.RETRY_KEY).click().run()

    assert not list(app.exception), [item.message for item in app.exception]
    assert boot_stop.HELD_LINE not in [item.value for item in app.error]
    assert "Capa LOB Summary" in [item.value for item in app.title], "HOME 이 섰다"
