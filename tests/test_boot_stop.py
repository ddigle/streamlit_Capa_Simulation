# Purpose: 앱 시작 실패 판의 갈래 판정 · 그리기 · 진짜 app.py 배선 · 입장 화면 표지를 지킨다.

"""`components/boot_stop.py`(2026-11-13 「앱 대신 뜨는 화면」 보드 카드 p1-boot).

부트스트랩이 실패하면 쉬운 경고 한 줄 · 「다시 시도」(판 올리기 실패는 없음) · 문의 캡션 · 참고 줄 ·
접힌 「관리자용 진단」 이 선다. 프로세스 번호 · 서버 파일 경로 · 원문은 접힌 진단 안에만 있다. 입장
화면이 읽는 스타일 표지도 함께 간다.
"""

from __future__ import annotations

import errno
import os
import re
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components import boot_stop
from capa_simulation.persistence._migration_core import MigrationChanged
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
    「다시 시도」 가 없다(다시 해도 같다)."""
    failure = boot_stop.classify_boot_failure(make())

    assert (failure.code, failure.retry) == (code, retry)
    if code == boot_stop.LOCKED:
        assert failure.line == boot_stop.LOCKED_LINE
    elif code == boot_stop.MIGRATION_FAILED:
        assert failure.line == boot_stop.UPDATE_LINE
    else:
        assert failure.line == f"{boot_stop.LOCKED_LINE} — {boot_stop.IO_WORDS[code]}"


def test_a_changed_migration_is_still_a_runtime_error() -> None:
    """종류만 따로 두었다 — `RuntimeError` 를 받던 자리는 그대로 받는다."""
    assert issubclass(MigrationChanged, RuntimeError)


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

    app = _run("lock", monkeypatch)

    assert not list(app.exception)
    assert [item.value for item in app.error] == [boot_stop.LOCKED_LINE]
    assert app.error[0].icon == ":material/database_off:"
    [retry] = app.button
    assert (retry.label, retry.key) == (boot_stop.RETRY_LABEL, boot_stop.RETRY_KEY)
    captions = [str(item.value) for item in app.caption]
    assert captions[0] == "문의 help@example.com"
    assert re.fullmatch(r"참고 db_locked · \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", captions[1])
    # 프로세스 번호 · 서버 파일 경로 · 개발 PC 조치는 접힌 진단 안에만 있다.
    main = _main_text(app)
    assert "PID" not in main and SECRET_PATH not in main
    [fold] = app.expander
    assert fold.label == boot_stop.DIAGNOSTIC_LABEL
    folded = "\n".join(str(item.value) for item in fold.markdown) + "\n".join(
        str(item.value) for item in fold.code
    )
    assert "PID 424242" in folded and SECRET_PATH in folded


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
    assert bodies[0] == f'<style {boot_stop.BOOT_STOP_ATTRIBUTE}="{boot_stop.LOCKED_LINE}"></style>'
    tricky = boot_stop.BootFailure("x", 'a"<b>', retry=True)
    assert boot_stop.boot_marker_html(tricky) == (
        f'<style {boot_stop.BOOT_STOP_ATTRIBUTE}="a&quot;&lt;b&gt;"></style>'
    )


def test_the_intro_script_reads_the_same_marker_and_shows_the_failure() -> None:
    """입장 화면 JS 는 같은 속성 이름으로 표지를 읽고, 그릴 때마다 다시 읽어 붙들지 않는다. 실패면
    상태 낱말 「열지 못함」 · 멈춘 칸의 실패 색 + 낱말 · 상태 줄 아래 까닭 한 줄이다."""
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
    assert "if (ready && bootStopLine() !== shownStop) render();" in poll
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
    assert [item.value for item in app.error] == [boot_stop.LOCKED_LINE]
    assert "Capa LOB Summary" not in [item.value for item in app.title]

    app = app.button(key=boot_stop.RETRY_KEY).click().run()

    assert not list(app.exception), [item.message for item in app.exception]
    assert boot_stop.LOCKED_LINE not in [item.value for item in app.error]
    assert "Capa LOB Summary" in [item.value for item in app.title], "HOME 이 섰다"
