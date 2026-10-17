# Purpose: 사내 배포 화면 확인 스크립트의 경로 거절·사전 확인·앱 수명·항목·결과 꼴을 고정한다.

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest

from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import check_deploy_screens as screens  # noqa: E402
from check_deploy_screens import (  # noqa: E402
    ITEMS,
    OVER_BUDGET,
    SKIPPED_NO_PERMISSION,
    AppStartError,
    Item,
    Outcome,
    RunFacts,
    Screen,
    StreamlitApp,
)

COMPONENTS = PROJECT_ROOT / "src" / "capa_simulation" / "components"
SENTINEL = "ZZSENTINEL 설비호기 이름"
# 자동 픽스처가 진짜 프로세스 살피기를 막기 전에 잡아 둔다 — 셈 규칙은 가짜 목록으로 시험한다.
REAL_RUNNING_APP_COUNT = screens.running_app_count
EXPECTED_PATHS = (DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)
BS = "\\"


def _args(**overrides: Any) -> argparse.Namespace:
    values: dict[str, Any] = {"output": None, "shots": None, "playwright_dir": None}
    values.update(overrides)
    return argparse.Namespace(**values)


# ---------------------------------------------------------------------------------- 경로


def test_paths_inside_the_repository_are_refused(tmp_path: Path) -> None:
    assert screens.inside_repository(PROJECT_ROOT)
    assert screens.inside_repository(PROJECT_ROOT / "data" / "screens.md")
    assert not screens.inside_repository(tmp_path / "screens.md")
    # 이름 앞부분만 같은 옆 폴더(`capa-w4-other`)는 저장소 밖이다.
    assert not screens.inside_repository(PROJECT_ROOT.parent / f"{PROJECT_ROOT.name}-other" / "x")


@pytest.mark.skipif(sys.platform != "win32", reason="대소문자를 가리지 않는 파일 시스템만")
def test_a_case_varied_path_is_still_inside_on_windows() -> None:
    assert screens.inside_repository(Path(str(PROJECT_ROOT).upper()) / "review" / "x.md")


def _device_forms() -> dict[str, str]:
    root = str(PROJECT_ROOT)
    no_drive = root[2:] if root[1:2] == ":" else root
    return {
        "extended": BS * 2 + "?" + BS + root + BS + "x.md",
        "globalroot": BS * 2 + "?" + BS + "GLOBALROOT" + BS + "??" + BS + root + BS + "x.md",
        "unc_localhost": BS * 2 + "localhost" + BS + "C$" + no_drive + BS + "x.md",
        "unc_loopback": BS * 2 + "127.0.0.1" + BS + "C$" + no_drive + BS + "x.md",
        "unc_extended": BS * 2 + "?" + BS + "UNC" + BS + "localhost" + BS + "C$" + no_drive,
        "device": BS * 2 + "." + BS + root + BS + "x.md",
        "slashes": "//localhost/C$" + no_drive.replace(BS, "/") + "/x.md",
    }


@pytest.mark.parametrize("form", sorted(_device_forms()))
def test_device_and_unc_forms_are_refused_wherever_they_point(form: str) -> None:
    # 앞머리가 다른 드라이브처럼 보여 문자열 비교를 빠져나가던 꼴이다(병합 전 리뷰 재현).
    assert screens.inside_repository(Path(_device_forms()[form]))


def test_a_device_form_outside_the_repository_is_still_refused(tmp_path: Path) -> None:
    assert screens.inside_repository(Path(BS * 2 + "?" + BS + str(tmp_path / "x.md")))


def test_an_alias_of_the_root_is_caught_by_samefile(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    alias = tmp_path / "alias"
    if sys.platform == "win32":
        made = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(root)], capture_output=True
        )
        if made.returncode != 0:
            pytest.skip("연결 폴더를 만들 수 없다")
    else:
        alias.symlink_to(root, target_is_directory=True)
    try:
        assert screens.inside_repository(alias / "data" / "new" / "x.md", root)
        assert not screens.inside_repository(tmp_path / "elsewhere" / "x.md", root)
    finally:
        # 연결만 지운다(대상은 그대로).
        if sys.platform == "win32":
            os.rmdir(alias)
        else:
            alias.unlink()


def test_refused_paths_names_only_the_options(tmp_path: Path) -> None:
    args = _args(
        output=PROJECT_ROOT / "x.md",
        shots=tmp_path / "shots",
        playwright_dir=Path(_device_forms()["unc_localhost"]),
    )

    assert screens.refused_paths(args) == ["--output", "--playwright-dir"]


def test_main_refuses_an_output_inside_the_repository_before_anything_else(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("경로를 거절하기 전에 다음 단계로 갔다")

    monkeypatch.setattr(screens, "load_playwright", forbidden)

    code = screens.main(
        ["--output", str(PROJECT_ROOT / "review" / "x.md"), "--playwright-dir", str(tmp_path)]
    )

    assert code == screens.EXIT_NOT_READY
    assert "--output" in capsys.readouterr().out


def test_main_refuses_shots_inside_the_repository(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(screens, "load_playwright", lambda directory: object())

    code = screens.main(["--shots", str(PROJECT_ROOT / "shots"), "--playwright-dir", str(tmp_path)])

    assert code == screens.EXIT_NOT_READY
    assert "--shots" in capsys.readouterr().out


def test_an_output_folder_that_cannot_be_made_stops_with_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("", encoding="utf-8")

    code = screens.main(["--output", str(blocker / "x.md"), "--playwright-dir", str(tmp_path)])

    assert code == screens.EXIT_NOT_READY
    assert "출력 폴더를 만들지 못했습니다" in capsys.readouterr().out


# ---------------------------------------------------------------------------------- Playwright


def test_missing_playwright_prints_the_install_line(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert screens.main(["--playwright-dir", str(tmp_path / "empty")]) == screens.EXIT_NOT_READY
    assert "uv pip install --target" in capsys.readouterr().out
    assert screens.main([]) == screens.EXIT_NOT_READY


def test_playwright_is_read_from_the_given_folder_appended_to_sys_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "playwright"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "sync_api.py").write_text("MARK = 'fake'\n", encoding="utf-8")
    monkeypatch.setattr(sys, "path", list(sys.path))
    for name in ("playwright", "playwright.sync_api"):
        monkeypatch.delitem(sys.modules, name, raising=False)

    module = screens.load_playwright(tmp_path)

    assert module is not None and module.MARK == "fake"
    # 앞이 아니라 끝에 붙는다 — 함께 깔린 공용 패키지가 저장소 의존성을 가리지 않게.
    assert sys.path[-1] == str(tmp_path.resolve())
    for name in ("playwright", "playwright.sync_api"):
        sys.modules.pop(name, None)


def test_the_list_runs_without_playwright(capsys: pytest.CaptureFixture[str]) -> None:
    assert screens.main(["--list"]) == screens.EXIT_OK
    out = capsys.readouterr().out
    assert all(f"`{item.key}`" in out for item in ITEMS)


class _FakeBrowser:
    def __init__(self) -> None:
        self.closed = False

    def new_context(self, **options: Any) -> SimpleNamespace:
        return SimpleNamespace(set_default_timeout=lambda ms: None, new_page=lambda: "page")

    def close(self) -> None:
        self.closed = True


class _FakeDriver:
    def __init__(self, browser: _FakeBrowser) -> None:
        self.browser = browser
        self.exited = False

    def __enter__(self) -> SimpleNamespace:
        return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kw: self.browser))

    def __exit__(self, *exc: object) -> None:
        self.exited = True


def _fake_sync_api() -> tuple[SimpleNamespace, _FakeBrowser, _FakeDriver]:
    browser = _FakeBrowser()
    driver = _FakeDriver(browser)
    return SimpleNamespace(sync_playwright=lambda: driver), browser, driver


def test_the_browser_is_closed_on_a_normal_end_and_on_an_error() -> None:
    api, browser, _ = _fake_sync_api()
    with screens.open_browser(api, "chrome") as page:
        assert page == "page"
    assert browser.closed

    api, browser, _ = _fake_sync_api()
    with pytest.raises(ValueError), screens.open_browser(api, "chrome"):
        raise ValueError("항목 밖 실패")
    assert browser.closed


def test_ctrl_c_leaves_closing_to_the_driver() -> None:
    # `browser.close()` 는 Playwright 호출 중 끊긴 뒤 끝나지 않는 기다림에 빠진다(리뷰 재현).
    api, browser, driver = _fake_sync_api()

    with pytest.raises(KeyboardInterrupt), screens.open_browser(api, "chrome"):
        raise KeyboardInterrupt

    assert not browser.closed
    assert driver.exited


# ---------------------------------------------------------------------------------- 사전 확인


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_locked_databases_reports_only_the_locked_file(tmp_path: Path) -> None:
    locked, free, missing = tmp_path / "a.duckdb", tmp_path / "b.duckdb", tmp_path / "c.duckdb"
    locked.write_bytes(b"")
    free.write_bytes(b"")
    opened: list[_FakeConnection] = []

    def connect(path: str, read_only: bool) -> _FakeConnection:
        assert read_only
        if path == str(locked):
            raise duckdb.IOException("Could not set lock on file (PID 1)")
        opened.append(_FakeConnection())
        return opened[-1]

    assert screens.locked_databases([locked, free, missing], connect=connect) == [locked]
    assert len(opened) == 1 and opened[0].closed


def test_an_io_error_that_is_not_a_lock_is_not_a_user_app(tmp_path: Path) -> None:
    broken = tmp_path / "a.duckdb"
    broken.write_bytes(b"")

    def connect(path: str, read_only: bool) -> _FakeConnection:
        raise duckdb.IOException("The file is not a valid DuckDB database file!")

    with pytest.raises(duckdb.IOException):
        screens.locked_databases([broken], connect=connect)


def test_a_real_closed_database_is_not_locked(tmp_path: Path) -> None:
    path = tmp_path / "x.duckdb"
    duckdb.connect(str(path)).close()

    assert screens.locked_databases([path]) == []


def test_applied_versions_reads_the_migration_table(tmp_path: Path) -> None:
    path = tmp_path / "x.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE SCHEMA app_meta")
        connection.execute("CREATE TABLE app_meta.schema_migration (version INTEGER)")
        connection.execute("INSERT INTO app_meta.schema_migration VALUES (1), (4)")

    assert screens.applied_versions(path, "app_meta.schema_migration") == {1, 4}
    assert screens.applied_versions(path, "equipment_meta.schema_migration") == frozenset()
    assert screens.applied_versions(tmp_path / "none.duckdb", "x.y") == frozenset()


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (r'"C:\Dev\x\.venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501', True),
        (r"C:\Python310\python.exe -m streamlit run app.py", True),
        ("/usr/bin/python3.10 -m streamlit run /srv/repo/app.py --server.port 8501", True),
        ("streamlit run app.py", True),
        ('bash -c "cd repo && streamlit run app.py"', False),
        ("uv run streamlit run app.py", False),
        ("python -m pytest tests/test_app_navigation.py", False),
        ("python scripts/check_deploy_screens.py --port 8551", False),
        ("python -m streamlit run other_app.py", False),
    ],
)
def test_app_command_lines_are_recognised(command: str, expected: bool) -> None:
    assert screens.is_app_command(command) is expected


def test_the_app_counts_only_when_its_app_py_is_this_repository(tmp_path: Path) -> None:
    ours = f"python -m streamlit run {PROJECT_ROOT / 'app.py'}"
    others = f"python -m streamlit run {tmp_path / 'app.py'}"
    relative = "python -m streamlit run app.py"
    commands = [
        (ours, None),
        (others, None),
        (relative, str(PROJECT_ROOT)),
        (relative, str(tmp_path)),
        # 작업 폴더를 모르면(Windows) 같은 앱으로 본다 — 사용자 앱을 놓치지 않는 쪽.
        (relative, None),
        ("python -m pytest", None),
    ]

    assert REAL_RUNNING_APP_COUNT(list_commands=lambda: commands) == 3


def test_a_failed_process_scan_is_unknown_not_zero() -> None:
    def broken() -> list[tuple[str, str | None]]:
        raise subprocess.CalledProcessError(1, "powershell")

    assert REAL_RUNNING_APP_COUNT(list_commands=broken) is None


def test_the_windows_process_query_asks_for_utf8() -> None:
    # 콘솔 코드페이지(cp949) 그대로면 한글 경로의 명령줄이 깨져 앱을 놓친다.
    assert screens._WINDOWS_PROCESS_QUERY.startswith(
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
    )


def _ready_for_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screens, "load_playwright", lambda directory: object())
    monkeypatch.setattr(screens, "port_in_use", lambda port: False)

    def no_app(*args: object, **kwargs: object) -> None:
        raise AssertionError("사용자 앱이 있는데 확인용 앱을 띄웠다")

    monkeypatch.setattr(screens, "StreamlitApp", no_app)


def test_a_running_user_app_defers_without_starting_anything(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _ready_for_preflight(monkeypatch)
    monkeypatch.setattr(screens, "running_app_count", lambda: 2)

    code = screens.main(["--playwright-dir", str(tmp_path)])

    assert code == screens.EXIT_DEFERRED
    assert capsys.readouterr().out.strip() == screens.DEFERRED_MESSAGE


def test_a_failed_process_scan_defers_instead_of_trusting_the_lock_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    # 가만히 떠 있는 앱은 DB 를 쥐지 않는다 — 잠금이 없다고 사용자 앱이 없는 것이 아니다.
    _ready_for_preflight(monkeypatch)
    monkeypatch.setattr(screens, "running_app_count", lambda: None)

    def no_lock_check(paths: object) -> list[Path]:
        raise AssertionError("프로세스를 못 봤는데 DB 잠금만 보고 넘어가려 했다")

    monkeypatch.setattr(screens, "locked_databases", no_lock_check)

    code = screens.main(["--playwright-dir", str(tmp_path)])

    assert code == screens.EXIT_DEFERRED
    out = capsys.readouterr().out
    assert screens.SCAN_FAILED_MESSAGE in out and "--ignore-other-apps" in out


def test_ignore_other_apps_still_defers_on_a_locked_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _ready_for_preflight(monkeypatch)

    def scan() -> int:
        raise AssertionError("--ignore-other-apps 인데 프로세스를 살폈다")

    monkeypatch.setattr(screens, "running_app_count", scan)
    monkeypatch.setattr(screens, "locked_databases", lambda paths: [Path("x.duckdb")])

    code = screens.main(["--playwright-dir", str(tmp_path), "--ignore-other-apps"])

    assert code == screens.EXIT_DEFERRED
    assert capsys.readouterr().out.strip() == screens.DEFERRED_MESSAGE


def test_a_database_that_cannot_be_opened_is_2_not_a_deferral(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _ready_for_preflight(monkeypatch)

    def broken(paths: object) -> list[Path]:
        raise duckdb.IOException(f"not a valid database file {SENTINEL}")

    monkeypatch.setattr(screens, "locked_databases", broken)

    code = screens.main(["--playwright-dir", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == screens.EXIT_NOT_READY
    assert "DB 를 열지 못했습니다 — IOException" in out and SENTINEL not in out


def test_a_busy_port_is_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screens, "locked_databases", lambda paths: [])
    monkeypatch.setattr(screens, "port_in_use", lambda port: True)

    args = screens.parse_args(["--port", "8559"])

    result = screens.preflight(args)
    assert result is not None and result[0] == screens.EXIT_NOT_READY


def test_an_unexpected_exception_is_2_with_only_its_type(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(screens, "load_playwright", lambda directory: object())

    def boom(args: object) -> None:
        raise ValueError(SENTINEL)

    monkeypatch.setattr(screens, "preflight", boom)

    code = screens.main(["--playwright-dir", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == screens.EXIT_NOT_READY
    assert "예상 밖 오류로 멈췄습니다 — ValueError" in out and SENTINEL not in out


# ---------------------------------------------------------------------------------- 앱 수명


class _FakeProcess:
    def __init__(self, *, exit_code: int | None = None, hang: bool = False) -> None:
        self.exit_code = exit_code
        self.hang = hang
        self.calls: list[str] = []

    def poll(self) -> int | None:
        return self.exit_code

    def wait(self, timeout: float | None = None) -> int:
        self.calls.append("wait")
        if self.hang and "kill" not in self.calls:
            raise subprocess.TimeoutExpired("streamlit", timeout or 0)
        self.exit_code = 0 if self.exit_code is None else self.exit_code
        return self.exit_code

    def terminate(self) -> None:
        self.calls.append("terminate")

    def kill(self) -> None:
        self.calls.append("kill")

    def send_signal(self, sig: int) -> None:
        self.calls.append("signal")


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _app(
    process: _FakeProcess,
    *,
    healthy: bool = True,
    port_open: bool = False,
    seen: dict[str, Any] | None = None,
    child_paths: tuple[Path, Path] = EXPECTED_PATHS,
    contain: bool = False,
) -> StreamlitApp:
    clock = _Clock()

    def popen(command: list[str], **options: Any) -> _FakeProcess:
        if seen is not None:
            seen.update(command=command, **options)
        return process

    return StreamlitApp(
        8559,
        popen=popen,
        probe=lambda url: healthy,
        port_probe=lambda port: port_open,
        path_probe=lambda env, root: child_paths,
        start_timeout=5,
        contain=contain,
        clock=clock,
        sleep=clock.sleep,
    )


def _stopped(process: _FakeProcess) -> bool:
    return ("signal" in process.calls or "terminate" in process.calls) and "wait" in process.calls


def test_the_app_listens_locally_with_this_repository_first_on_the_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONPATH", "worktree-src")
    seen: dict[str, Any] = {}
    process = _FakeProcess()

    with _app(process, seen=seen):
        pass

    command = seen["command"]
    assert command[:5] == [sys.executable, "-m", "streamlit", "run", "app.py"]
    assert command[command.index("--server.port") + 1] == "8559"
    assert command[command.index("--server.address") + 1] == "127.0.0.1"
    assert seen["cwd"] == str(PROJECT_ROOT)
    assert seen["env"]["PYTHONPATH"] == os.pathsep.join([str(PROJECT_ROOT / "src"), "worktree-src"])
    assert _stopped(process)


def test_the_app_environment_puts_this_repository_first_once() -> None:
    source = str(PROJECT_ROOT / "src")

    assert screens.app_environment(PROJECT_ROOT, {})["PYTHONPATH"] == source
    twice = screens.app_environment(PROJECT_ROOT, {"PYTHONPATH": os.pathsep.join(["a", source])})
    assert twice["PYTHONPATH"] == os.pathsep.join([source, "a"])


def test_the_child_app_never_gets_the_auto_update_opt_in() -> None:
    """사용자 앱을 띄운 창(예약 허락이 든 환경)에서 돌려도 자식 앱은 예약 스레드를 세우지 않는다."""
    from capa_simulation.auto_update_scheduler import ENV_VAR

    assert screens.AUTO_UPDATE_ENV_VAR == ENV_VAR
    env = screens.app_environment(PROJECT_ROOT, {ENV_VAR: "1", "OTHER": "x"})
    assert ENV_VAR not in env and env["OTHER"] == "x"


def test_an_app_that_would_open_another_database_is_not_started(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}
    other = (tmp_path / "a.duckdb", tmp_path / "b.duckdb")

    with (
        pytest.raises(AppStartError, match="다른 DB"),
        _app(_FakeProcess(), seen=seen, child_paths=other),
    ):
        pass

    assert seen == {}


def test_the_child_database_paths_are_this_repositorys() -> None:
    paths = screens.child_database_paths(screens.app_environment(PROJECT_ROOT), PROJECT_ROOT)

    assert all(
        screens._same_path(a, b.resolve()) for a, b in zip(paths, EXPECTED_PATHS, strict=True)
    )


def test_the_app_is_stopped_when_the_checks_raise() -> None:
    process = _FakeProcess()

    with pytest.raises(RuntimeError), _app(process):
        raise RuntimeError("항목 밖 실패")

    assert _stopped(process)


def test_an_app_that_never_answers_is_stopped_and_reported() -> None:
    process = _FakeProcess()

    with pytest.raises(AppStartError), _app(process, healthy=False):
        pass

    assert _stopped(process)


def test_an_app_that_exits_while_starting_is_reported_with_its_code() -> None:
    process = _FakeProcess(exit_code=3)

    with pytest.raises(AppStartError, match="3"), _app(process, healthy=False):
        pass

    assert process.calls == []


def test_a_hanging_app_is_killed() -> None:
    process = _FakeProcess(hang=True)

    with _app(process):
        pass

    assert "kill" in process.calls


def test_a_port_still_open_after_stop_is_flagged() -> None:
    app = _app(_FakeProcess(), port_open=True)

    with app:
        pass

    assert app.port_released is False


@pytest.mark.skipif(sys.platform != "win32", reason="CTRL_BREAK 는 Windows 만")
def test_windows_falls_back_to_terminate_when_ctrl_break_cannot_be_sent() -> None:
    class NoConsole(_FakeProcess):
        def send_signal(self, sig: int) -> None:
            raise OSError("콘솔 없음")

    process = NoConsole()

    with _app(process):
        pass

    assert "terminate" in process.calls


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object 는 Windows 만")
def test_a_child_in_the_job_ends_when_the_job_closes() -> None:
    # 스크립트가 강제로 끝나면 잡의 마지막 핸들이 닫힌다 — 그 일을 손으로 한다.
    job = screens._create_kill_on_close_job()
    assert job is not None
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=screens._CREATE_SUSPENDED,
    )
    try:
        assert screens._adopt_and_resume(job, child)
        time.sleep(0.5)
        assert child.poll() is None
        screens._close_job(job)
        child.wait(timeout=10)
    finally:
        if child.poll() is None:
            child.kill()


# ------------------------------------------------------------------------- 항목 실행·결과 꼴


class _FakeScreen(Screen):
    def __init__(self) -> None:
        super().__init__(page=None, base_url="http://127.0.0.1:8559/")
        self.settled = 0
        self.shots_taken: list[str] = []

    def settle(self) -> None:
        self.settled += 1

    def shot(self, name: str) -> None:
        self.shots_taken.append(name)


def _items(called: list[str]) -> list[Item]:
    def ok(screen: Screen) -> str:
        called.append("ok")
        return "있음 · 3개"

    def writes(screen: Screen) -> str:
        called.append("writes")
        return "저장 토스트 있음 · 지운 뒤 비교 안 함"

    def broken(screen: Screen) -> str:
        called.append("broken")
        raise ValueError(SENTINEL)

    def after(screen: Screen) -> str:
        called.append("after")
        return "같음 | 다름"

    return [
        Item("ok", "읽기 항목", ok),
        Item("writes", "쓰는 항목", writes, writes=True),
        Item("broken", "깨지는 항목", broken),
        Item("after", "뒤 항목", after),
    ]


NO_DEADLINE = float("inf")


def test_write_items_are_skipped_without_permission_and_failures_do_not_stop_the_rest() -> None:
    called: list[str] = []
    screen = _FakeScreen()
    seen: list[Outcome] = []

    outcomes = screens.run_items(
        screen, _items(called), allow_writes=False, deadline=NO_DEADLINE, on_outcome=seen.append
    )

    assert called == ["ok", "broken", "after"]
    assert [outcome.result for outcome in outcomes] == [
        "있음 · 3개",
        SKIPPED_NO_PERMISSION,
        "미기록 — ValueError",
        "같음 | 다름",
    ]
    assert seen == outcomes
    assert screen.settled == 3
    assert screen.shots_taken == ["01_ok", "03_broken", "04_after"]


def test_write_items_run_only_with_permission() -> None:
    called: list[str] = []

    screens.run_items(_FakeScreen(), _items(called), allow_writes=True, deadline=NO_DEADLINE)

    assert "writes" in called


def test_items_past_the_deadline_are_not_run() -> None:
    called: list[str] = []
    clock = _Clock()

    def tick() -> float:
        clock.now += 100
        return clock.now

    outcomes = screens.run_items(
        _FakeScreen(), _items(called), allow_writes=True, deadline=250, clock=tick
    )

    assert outcomes[-1].result == OVER_BUDGET
    assert "after" not in called


def _facts(**overrides: Any) -> RunFacts:
    facts = RunFacts(
        channel="chrome",
        stamp="적용 배포 `202610081500`",
        allow_writes=False,
        started_seconds=1.4,
        entered_seconds=21.0,
        elapsed_seconds=64.0,
    )
    for name, value in overrides.items():
        setattr(facts, name, value)
    return facts


def test_the_block_is_a_paste_ready_table_without_exception_text() -> None:
    outcomes = screens.run_items(
        _FakeScreen(), _items([]), allow_writes=False, deadline=NO_DEADLINE
    )

    block = screens.render_block(outcomes, total=4, facts=_facts(applied_migrations=(0, 0)))

    assert SENTINEL not in block and "ZZSENTINEL" not in block
    assert "### 화면 확인" in block
    assert (
        "- 헤드리스 Chrome 1600×1000 · 별도 포트에 띄운 앱(127.0.0.1) · "
        "적용 배포 `202610081500` · 쓰기 허락 없음\n"
    ) in block
    assert (
        "- 사용자 앱 확인 — 프로세스 봄 · DB 잠금 없음 · 마이그레이션 — 이 확인이 건 것 없음\n"
    ) in block
    assert "항목 4 — 기록 2 · 미기록 1 · 안 함 1 · 걸린 시간 1분 4초 · 끝까지 돎" in block
    assert "| 항목 | 쓰기 | 결과 |" in block
    assert "| 읽기 항목 | 없음 | 있음 · 3개 |" in block
    assert f"| 쓰는 항목 | 씀(지워 되돌림) | {SKIPPED_NO_PERMISSION} |" in block
    assert "| 깨지는 항목 | 없음 | 미기록 — ValueError |" in block
    # 표를 깨는 세로줄은 바꾼다.
    assert "| 뒤 항목 | 없음 | 같음 / 다름 |" in block


def test_a_partial_block_says_where_it_stopped_and_how_apps_were_checked() -> None:
    outcomes = [Outcome(Item("ok", "읽기 항목", lambda screen: "있음"), "있음")]

    block = screens.render_block(
        outcomes, total=5, facts=_facts(process_scan="무시", pending_migrations=(2, 0))
    )

    assert "중간에 끊김 — 1/5 항목까지" in block
    assert "프로세스 무시(--ignore-other-apps)" in block
    assert "대기 마이그레이션 시뮬레이션 2 · 설비 0 — 확인용 앱이 건다" in block


def test_migrations_the_check_applied_are_called_out() -> None:
    block = screens.render_block([], total=0, facts=_facts(applied_migrations=(2, 1)))

    assert "**마이그레이션 3개를 이 확인이 걸었다**(시뮬레이션 2 · 설비 1)" in block


def test_an_app_error_screen_is_in_the_header() -> None:
    block = screens.render_block([], total=5, facts=_facts(app_problem="앱 오류 화면 있음"))

    assert "**앱 오류 화면 있음 — 항목 안 돎**" in block


def test_the_applied_stamp_carries_only_the_deploy_number(tmp_path: Path) -> None:
    state = tmp_path / "applied.json"
    assert screens.applied_stamp(state) == "적용 기록 없음"
    state.write_text('{"stamp": "202610081500", "commit": "abc"}', encoding="utf-8")
    assert screens.applied_stamp(state) == "적용 배포 `202610081500`"
    state.write_text(f'{{"stamp": "{SENTINEL}"}}', encoding="utf-8")
    assert SENTINEL not in screens.applied_stamp(state)


def test_items_are_chosen_by_key_in_registry_order() -> None:
    keys = [item.key for item in ITEMS]
    assert len(keys) == len(set(keys))
    assert screens.select_items(None, ITEMS) == list(ITEMS)
    chosen = screens.select_items(f"{keys[-1]},{keys[0]}", ITEMS)
    assert chosen is not None and [item.key for item in chosen] == [keys[0], keys[-1]]
    assert screens.select_items("없는키", ITEMS) is None


# ---------------------------------------------------------------------------------- main 전체


class _Run:
    """가짜 앱·브라우저로 main 을 끝까지 돌린다(Playwright·실제 앱 없이)."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        items: list[Item],
        *,
        problem: str | None = None,
        fail_start: bool = False,
    ) -> None:
        self.calls: list[str] = []
        calls = self.calls

        class FakeApp:
            def __init__(self, port: int, *, start_timeout: float) -> None:
                self.base_url = "http://127.0.0.1:8559/"
                self.started_seconds = 1.0
                self.port_released = True

            def __enter__(self) -> FakeApp:
                if fail_start:
                    raise AppStartError("앱이 5초 안에 답하지 않았습니다")
                calls.append("start")
                return self

            def __exit__(self, *exc: object) -> None:
                calls.append("stop")

        @contextmanager
        def fake_browser(sync_api: object, channel: str) -> Iterator[object]:
            yield object()

        monkeypatch.setattr(screens, "ITEMS", tuple(items))
        monkeypatch.setattr(screens, "load_playwright", lambda directory: object())
        monkeypatch.setattr(screens, "preflight", lambda args: None)
        monkeypatch.setattr(screens, "StreamlitApp", FakeApp)
        monkeypatch.setattr(screens, "open_browser", fake_browser)
        monkeypatch.setattr(screens, "_migration_snapshot", lambda: (frozenset(), frozenset()))
        monkeypatch.setattr(Screen, "enter", lambda self, timeout=0.0: 2.0)
        monkeypatch.setattr(Screen, "app_problem", lambda self, timeout=0.0: problem)
        monkeypatch.setattr(Screen, "settle", lambda self: None)


def test_main_runs_write_items_only_with_allow_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    called: list[str] = []
    _Run(monkeypatch, _items(called))

    assert screens.main(["--playwright-dir", str(tmp_path)]) == screens.EXIT_OK
    assert "writes" not in called

    called.clear()
    code = screens.main(["--playwright-dir", str(tmp_path), "--allow-writes"])

    assert code == screens.EXIT_OK
    assert "writes" in called


def test_main_rewrites_the_output_after_every_item(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    output = tmp_path / "made" / "on" / "demand" / "screens.md"
    seen_by_second: list[str] = []

    def first(screen: Screen) -> str:
        return "있음"

    def second(screen: Screen) -> str:
        seen_by_second.append(output.read_text(encoding="utf-8"))
        return "없음"

    run = _Run(monkeypatch, [Item("first", "첫 항목", first), Item("second", "둘째 항목", second)])

    code = screens.main(["--playwright-dir", str(tmp_path), "--output", str(output)])

    assert code == screens.EXIT_OK
    assert run.calls == ["start", "stop"]
    assert "| 첫 항목 | 없음 | 있음 |" in seen_by_second[0]
    assert "중간에 끊김 — 1/2 항목까지" in seen_by_second[0]
    final = output.read_text(encoding="utf-8")
    assert "| 둘째 항목 | 없음 | 없음 |" in final and "끝까지 돎" in final
    assert final.strip() in capsys.readouterr().out


def test_an_app_error_screen_runs_no_item_and_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    called: list[str] = []
    run = _Run(monkeypatch, _items(called), problem="앱 오류 화면 있음")

    code = screens.main(["--playwright-dir", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == screens.EXIT_NOT_READY
    assert called == []
    assert run.calls == ["start", "stop"]
    assert "**앱 오류 화면 있음 — 항목 안 돎**" in out
    assert out.count("| 미기록 — 앱 오류 화면 있음 |") == 4


def test_ctrl_c_inside_an_item_still_stops_the_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def interrupted(screen: Screen) -> str:
        raise KeyboardInterrupt

    run = _Run(monkeypatch, [Item("ki", "끊기는 항목", interrupted)])

    with pytest.raises(KeyboardInterrupt):
        screens.main(["--playwright-dir", str(tmp_path)])

    assert run.calls == ["start", "stop"]


# ---------------------------------------------------------------------------------- 세 번째 리뷰


def test_deferral_is_3_so_it_cannot_be_mistaken_for_a_kill_or_a_crash() -> None:
    # Windows `TerminateProcess` 와 파이썬의 처리 안 된 예외는 1 로 끝난다.
    assert screens.EXIT_DEFERRED == 3
    assert {screens.EXIT_OK, screens.EXIT_NOT_READY, screens.EXIT_DEFERRED} == {0, 2, 3}


def test_a_broken_app_import_exits_2_with_only_its_type() -> None:
    code = (
        "import runpy, sys; sys.modules['capa_simulation.settings'] = None; "
        f"runpy.run_path({str(PROJECT_ROOT / 'scripts' / 'check_deploy_screens.py')!r}, "
        "run_name='__main__')"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    assert completed.returncode == 2
    assert "앱 모듈을 불러오지 못했습니다 — " in completed.stdout
    assert "Traceback" not in completed.stderr


def test_a_tilde_is_expanded_once_for_both_the_check_and_the_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 검사할 때만 `~` 를 풀고 쓸 때 글자 그대로 쓰면 `<작업 폴더>\~\out.md`(저장소 안)에 쓴다.
    workdir, home = tmp_path / "repo-root", tmp_path / "home"
    workdir.mkdir()
    home.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    code = screens.main(["--output", "~/out.md", "--playwright-dir", str(tmp_path / "no-pw")])

    assert code == screens.EXIT_NOT_READY
    assert not (workdir / "~").exists()
    assert "멈춤 — Playwright 없음" in (home / "out.md").read_text(encoding="utf-8")


def test_options_are_normalised_in_place(tmp_path: Path) -> None:
    args = _args(output=tmp_path / "a" / ".." / "out.md", shots=tmp_path / "shots")

    assert screens.refused_paths(args) == []
    assert args.output == (tmp_path / "out.md").resolve()
    assert args.shots == (tmp_path / "shots").resolve()


@pytest.mark.skipif(sys.platform != "win32", reason="대체 데이터 스트림은 Windows(NTFS)만")
def test_an_alternate_data_stream_is_refused(tmp_path: Path) -> None:
    args = _args(output=Path(str(tmp_path / "x.md") + ":stream"))

    assert screens.refused_paths(args) == ["--output"]


def test_an_existing_file_with_another_hard_link_is_refused(tmp_path: Path) -> None:
    original = tmp_path / "inside.md"
    original.write_text("", encoding="utf-8")
    alias = tmp_path / "outside.md"
    try:
        os.link(original, alias)
    except OSError:
        pytest.skip("하드 링크를 만들 수 없다")

    assert screens.refused_paths(_args(output=alias)) == ["--output"]
    assert screens.refused_paths(_args(output=tmp_path / "new.md")) == []


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            'IO Error: Could not set lock on file "x": Conflicting lock is held in python (PID 7)',
            True,
        ),
        ("IO Error: File is already open in python.exe (PID 12)", True),
        ('IO Error: Could not set lock on file "x"', True),
        (
            "IO Error: Corrupt database file: computed checksum 1 does not match stored checksum 2 "
            "in block at location 12288",
            False,
        ),
        ('IO Error: Could not read all bytes from file "C:\\Block\\x.duckdb": wanted=4096', False),
        ('IO Error: Cannot open file "x.duckdb": 액세스가 거부되었습니다.', False),
        ('IO Error: Cannot open file "x.duckdb": 다른 프로세스가 파일을 사용 중', False),
    ],
)
def test_lock_errors_are_told_apart_by_fixed_phrases(message: str, expected: bool) -> None:
    # 경로를 모르는 「Cannot open file」 은 잠금으로 보지 않는다 — 액세스 거부와 같은 꼴이다.
    assert screens.is_lock_error(duckdb.IOException(message)) is expected
    assert screens.is_lock_error(ValueError(message)) is False


@pytest.mark.skipif(sys.platform != "win32", reason="공유 위반 판정은 Windows 만")
def test_cannot_open_file_is_a_lock_only_while_another_handle_holds_the_file(
    tmp_path: Path,
) -> None:
    held = tmp_path / "held.duckdb"
    held.write_bytes(b"x")
    message = duckdb.IOException('IO Error: Cannot open file "held.duckdb": 다른 프로세스가')
    denied = duckdb.IOException('IO Error: Cannot open file "d": 액세스가 거부되었습니다.')
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        # 공유 없이 쥔다 — 다른 프로세스가 DuckDB 파일을 쥔 것과 같은 공유 위반이 난다.
        handle = kernel32.CreateFileW(str(held), 0x80000000, 0, None, 3, 0x80, None)
        try:
            assert screens.is_lock_error(message, held)
        finally:
            kernel32.CloseHandle(wintypes.HANDLE(handle))
        assert not screens.is_lock_error(message, held)
    # 디렉터리는 액세스 거부다 — 잠금이 아니다.
    assert not screens.is_lock_error(denied, tmp_path)


@pytest.mark.skipif(sys.platform != "win32", reason="리뷰 재현은 Windows")
def test_a_directory_in_place_of_a_database_is_not_a_user_app(tmp_path: Path) -> None:
    folder = tmp_path / "x.duckdb"
    folder.mkdir()

    with pytest.raises(duckdb.Error):
        screens.locked_databases([folder])


def _stale_output(tmp_path: Path) -> Path:
    output = tmp_path / "screens.md"
    output.write_text("지난 실행의 블록 · DB 잠금 없음 · 끝까지 돎\n", encoding="utf-8")
    return output


@pytest.mark.parametrize(
    ("scan", "locked", "line", "code"),
    [
        (2, [], "미룸 — 사용자 앱이 떠 있습니다", 3),
        (None, [], "미룸 — 프로세스를 살피지 못했습니다", 3),
        (0, [Path("x.duckdb")], "미룸 — 사용자 앱이 떠 있습니다", 3),
        (0, "broken", "멈춤 — DB 를 열지 못했습니다(IOException)", 2),
    ],
)
def test_an_early_end_replaces_the_last_output_with_one_fixed_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scan: int | None,
    locked: object,
    line: str,
    code: int,
) -> None:
    _ready_for_preflight(monkeypatch)
    monkeypatch.setattr(screens, "running_app_count", lambda: scan)

    def lock_check(paths: object) -> object:
        if locked == "broken":
            raise duckdb.IOException("broken")
        return locked

    monkeypatch.setattr(screens, "locked_databases", lock_check)
    output = _stale_output(tmp_path)

    assert screens.main(["--playwright-dir", str(tmp_path), "--output", str(output)]) == code

    text = output.read_text(encoding="utf-8")
    assert text == screens.status_block(line)
    assert "지난 실행" not in text and "DB 잠금 없음" not in text


def test_an_app_that_does_not_start_leaves_a_fixed_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _Run(monkeypatch, [Item("ok", "읽기 항목", lambda screen: "있음")], fail_start=True)
    output = _stale_output(tmp_path)

    code = screens.main(["--playwright-dir", str(tmp_path), "--output", str(output)])

    assert code == screens.EXIT_NOT_READY
    assert output.read_text(encoding="utf-8") == screens.status_block(
        "멈춤 — 앱이 뜨지 않았습니다: 앱이 5초 안에 답하지 않았습니다"
    )


def test_items_skipped_by_the_budget_make_the_run_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    called: list[str] = []

    def item(screen: Screen) -> str:
        called.append("item")
        return "있음"

    items = [Item("a", "첫 항목", item), Item("b", "둘째 항목", item)]
    _Run(monkeypatch, items)

    code = screens.main(["--playwright-dir", str(tmp_path), "--budget-minutes", "0"])

    out = capsys.readouterr().out
    assert code == screens.EXIT_NOT_READY
    assert called == []
    assert "**예산 넘어 2 항목 안 돎**" in out and "끝까지 돎" not in out


def test_the_browser_context_has_a_default_timeout() -> None:
    timeouts: list[int] = []

    class TimedBrowser(_FakeBrowser):
        def new_context(self, **options: Any) -> SimpleNamespace:
            return SimpleNamespace(set_default_timeout=timeouts.append, new_page=lambda: "page")

    api = SimpleNamespace(sync_playwright=lambda: _FakeDriver(TimedBrowser()))

    with screens.open_browser(api, "chrome"):
        pass

    assert timeouts == [screens.ACTION_TIMEOUT_MS]


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object 는 Windows 만")
def test_no_job_means_no_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screens, "_create_kill_on_close_job", lambda: None)
    seen: dict[str, Any] = {}

    with pytest.raises(AppStartError, match="Job"), _app(_FakeProcess(), seen=seen, contain=True):
        pass

    assert seen == {}


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object 는 Windows 만")
def test_a_suspended_child_that_cannot_join_the_job_is_killed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int] = []
    monkeypatch.setattr(screens, "_create_kill_on_close_job", lambda: 77)
    monkeypatch.setattr(screens, "_adopt_and_resume", lambda job, process: False)
    monkeypatch.setattr(screens, "_close_job", closed.append)
    process = _FakeProcess()
    seen: dict[str, Any] = {}

    with pytest.raises(AppStartError, match="Job"), _app(process, seen=seen, contain=True):
        pass

    assert seen["creationflags"] & screens._CREATE_SUSPENDED
    assert "kill" in process.calls
    assert closed == [77]


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object 는 Windows 만")
def test_an_error_between_start_and_resume_still_kills_the_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(job: int, process: object) -> bool:
        raise RuntimeError("깨우기 전 실패")

    monkeypatch.setattr(screens, "_create_kill_on_close_job", lambda: 77)
    monkeypatch.setattr(screens, "_adopt_and_resume", broken)
    monkeypatch.setattr(screens, "_close_job", lambda job: None)
    process = _FakeProcess()

    with pytest.raises(RuntimeError), _app(process, contain=True):
        pass

    assert "kill" in process.calls


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_PDEATHSIG 는 Linux 만")
def test_linux_containment_failure_stops_the_start() -> None:
    def popen(command: list[str], **options: Any) -> _FakeProcess:
        assert options["preexec_fn"] is screens._die_with_parent
        raise subprocess.SubprocessError("Exception occurred in preexec_fn.")

    app = StreamlitApp(
        8559,
        popen=popen,
        probe=lambda url: True,
        port_probe=lambda port: False,
        path_probe=lambda env, root: EXPECTED_PATHS,
    )

    with pytest.raises(AppStartError), app:
        pass

    assert app.contained is False


# ---------------------------------------------------------------------------------- 화면 계약
#
# 항목이 찾는 선택자·화면 글자가 앱 코드·자산에 그대로 있는지만 본다. 화면에서의 동작은 사외
# 실측(브라우저)과 사내 실행이 본다.


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_intro_and_sidebar_ids_match_the_app() -> None:
    from capa_simulation.components.intro_overlay import SUMMARY_LABEL_ID

    assert screens.SUMMARY_LABEL_ID == SUMMARY_LABEL_ID
    assets = COMPONENTS / "intro_overlay_assets"
    assert f'const HOST_ID = "{screens.INTRO_HOST_ID}";' in _text(assets / "intro.js")
    assert '$(".btn.detail")' in _text(assets / "intro.js")
    html = _text(assets / "intro.html")
    assert '<header class="head">' in html and 'class="logo"' in html
    # `symbol` 항목이 재는 라벨 두 줄 — 사이드바(`capa-brand-*`)와 Summary 머리 줄(`brand-*`).
    for name in ("brand-word", "brand-sub"):
        assert f'class="{name}"' in html, name
        assert f'".{name}"' in screens._SUMMARY_MARK_JS, name
    label = _text(COMPONENTS / "intro_summary.py")
    for name in ("capa-brand-word", "capa-brand-sub", "capa-brand-hint"):
        assert f'class="{name}"' in label, name
        assert f'".{name}"' in screens._LABEL_MARK_JS, name


def test_the_symbol_line_check_allows_only_a_layout_unit_of_overflow() -> None:
    """「라벨 글자」의 줄마다 판정은 글자 본래 폭(Range)이 칸 폭을 배치 단위(1/64px) 남짓까지만
    넘어도 된다고 본다. 잘리지 않은 줄은 두 폭이 같고, 브라우저는 1px 보다 작은 넘침에도 말줄임을
    그린다 — 몫이 0.5px 이면 `S.PKG CA…` · `Summ…` 를 「다 보임」으로 읽는다. 둘째 줄로 내려가 라벨
    높이 밖에 있는 안내 글자는 빠진 것이다(잘림이 아니다 — `intro_summary._LABEL_CSS` 의 줄바꿈)."""
    assert 1 / 64 <= screens._RANGE_SLACK_PX < 0.05
    width = f"range.getBoundingClientRect().width <= r.width + {screens._RANGE_SLACK_PX}"
    for script in (screens._LABEL_MARK_JS, screens._SUMMARY_MARK_JS):
        assert width in script
    assert "hint.getBoundingClientRect().top >= l.bottom - 1" in screens._LABEL_MARK_JS
    assert "flex-wrap: wrap;" in _text(COMPONENTS / "intro_summary.py")


def _narrow_rows(**changes: dict[str, str]) -> list[dict[str, Any]]:
    """좁은 폭 라벨 측정값 — 기본은 폭마다 두 줄 다 보이고 안내 글자는 빠짐. `w236={"word": "cut"}`
    처럼 그 폭의 칸만 바꾼다."""
    rows = []
    for width in screens.LABEL_NARROW_WIDTHS_PX:
        row: dict[str, Any] = {"width": width, "word": "whole", "sub": "whole", "hint": "gone"}
        row.update(changes.get(f"w{width}", {}))
        rows.append(row)
    return rows


class _SymbolScreen(_FakeScreen):
    """`symbol` 항목이 읽는 세 값(사이드바 라벨·좁은 폭 라벨·Summary 머리 줄)을 정해 돌려준다."""

    def __init__(
        self,
        side: dict[str, Any],
        summary: dict[str, Any],
        narrow: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self.values = {
            screens._LABEL_MARK_JS: side,
            screens._LABEL_NARROW_JS: _narrow_rows() if narrow is None else narrow,
            screens._SUMMARY_MARK_JS: summary,
        }
        self.narrow_args: list[object] = []
        self.clicked: list[str] = []
        self.closed = 0
        self.page = SimpleNamespace(
            locator=lambda selector: SimpleNamespace(click=lambda: self.clicked.append(selector))
        )

    def js(self, script: str, arg: object = None) -> Any:
        if script == screens._LABEL_NARROW_JS:
            self.narrow_args.append(arg)
        return self.values[script]

    def close_overlay(self) -> None:
        self.closed += 1


@pytest.mark.parametrize(
    ("side_fits", "summary_fits", "verdict"),
    [(True, True, "다 보임"), (False, True, "잘림"), (True, False, "잘림")],
)
def test_the_symbol_item_says_cut_when_either_label_loses_a_line(
    monkeypatch: pytest.MonkeyPatch, side_fits: bool, summary_fits: bool, verdict: str
) -> None:
    """「라벨 글자」는 사이드바 라벨(두 줄 + 안내 글자)과 Summary 머리 줄 라벨(두 줄)을 함께 본다 —
    한 곳이라도 잘리면 「잘림」. 결과는 고정 낱말과 px 뿐이다(런북 7장의 기대 글과 같은 꼴)."""
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    screen = _SymbolScreen(
        {"w": 30, "h": 30, "fits": side_fits, "ready": True},
        {"size": [30, 30], "fits": summary_fits},
    )

    result = screens.check_sidebar_symbol(screen)

    assert result == f"사이드바 30×30px · Summary 30×30px — 같음 · 라벨 글자 {verdict}"
    assert screen.clicked == [f"#{screens.SUMMARY_LABEL_ID}"] and screen.closed == 1


@pytest.mark.parametrize(
    ("narrow", "verdict"),
    [
        # 좁은 폭마다 다 보인다 — 기본 폭만 재던 때와 같은 글(런북 7장의 기대 글).
        (_narrow_rows(), "다 보임"),
        # 기본 폭 바로 아래에서 안내 글자가 반쯤(`Summ…`) — 통째로 서거나 빠져야 한다.
        (_narrow_rows(w296={"hint": "cut"}), "잘림(좁은 폭 296px)"),
        # 줄이는 문턱 바로 아래의 말줄임은 결함이다(문턱이 늦게 서면 `S.PKG CA…`).
        (_narrow_rows(w236={"word": "ellipsis"}), "잘림(좁은 폭 236px)"),
        # 가장 좁은 폭의 말줄임은 정한 모양 — 세기만 한다.
        (
            _narrow_rows(w200={"word": "ellipsis", "sub": "ellipsis"}),
            "다 보임(좁은 폭 200px 말줄임 2)",
        ),
        # 말줄임 없이 잘림은 가장 좁은 폭에서도 결함이다(배포 202610171956 의 `S.PKG C`).
        (_narrow_rows(w200={"word": "cut"}), "잘림(좁은 폭 200px)"),
        (_narrow_rows(w236={"sub": "cut"}, w200={"word": "cut"}), "잘림(좁은 폭 236·200px)"),
        ([], "다 보임 · 좁은 폭 못 잼"),
    ],
)
def test_the_symbol_item_also_reads_the_label_at_narrow_sidebar_widths(
    monkeypatch: pytest.MonkeyPatch, narrow: list[dict[str, Any]], verdict: str
) -> None:
    """기본 폭만 재던 `symbol` 은 200px 에서 앱 이름이 말줄임 없이 잘려도(배포 202610171956)
    「라벨 글자 다 보임」 이었다. 좁게 끈 폭(`LABEL_NARROW_WIDTHS_PX`)마다 다시 재고, 잘린 폭을
    적는다. 잰 뒤에 라벨을 눌러 Summary 를 연다."""
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    screen = _SymbolScreen(
        {"w": 30, "h": 30, "fits": True, "ready": True}, {"size": [30, 30], "fits": True}, narrow
    )

    result = screens.check_sidebar_symbol(screen)

    assert result == f"사이드바 30×30px · Summary 30×30px — 같음 · 라벨 글자 {verdict}"
    assert screen.narrow_args == [
        {"id": screens.SUMMARY_LABEL_ID, "widths": list(screens.LABEL_NARROW_WIDTHS_PX)}
    ]


def test_a_cut_at_the_default_and_a_narrow_width_names_both() -> None:
    assert screens._label_verdict(False, ((236,), 0)) == "잘림(기본 폭 · 좁은 폭 236px)"
    assert screens._label_verdict(False, ((), 0)) == "잘림"


def test_the_narrow_label_widths_straddle_the_label_css_thresholds() -> None:
    """좁은 폭 셋은 라벨 CSS 의 문턱을 겨눈다 — 머리칸(사이드바 − 55px)이 296 에서는 안내 글자를
    감추는 문턱(240px) 위라 안내 글자가 줄바꿈으로만 빠지고, 236 에서는 글꼴을 줄이는
    문턱(190px) 바로 아래다. 마지막은 끌어 줄 수 있는 가장 좁은 폭이다. 잰 뒤 사이드바 원래 폭을
    되돌린다."""
    from capa_simulation.components import intro_summary

    css = intro_summary._label_css("light")
    hide, shrink = (
        int(width) for width in re.findall(r"@container capa-sidebar-head \(width < (\d+)px\)", css)
    )
    head = 55
    first, second, last = screens.LABEL_NARROW_WIDTHS_PX
    assert hide <= first - head < 300 - head
    assert shrink - 10 <= second - head < shrink
    assert last == screens.SIDEBAR_NARROW_WIDTH_PX
    script = screens._LABEL_NARROW_JS
    assert screens._WHOLE_LINE_JS in script
    for name in ("capa-brand-word", "capa-brand-sub", "capa-brand-hint"):
        assert f'".{name}"' in script, name
    assert 'side.style.transition = "none";' in script
    assert 'else side.setAttribute("style", saved);' in script


def test_the_toolbar_labels_cover_the_declared_order() -> None:
    from capa_simulation.components.theme_toggle import TOOLBAR_BUTTON_ORDER

    assert set(screens.TOOLBAR_LABELS) == set(TOOLBAR_BUTTON_ORDER)


def test_the_app_error_screen_is_an_error_box_without_the_sidebar_menu() -> None:
    app = _text(PROJECT_ROOT / "app.py")
    assert "st.error(bootstrap_error_message(exc)" in app
    assert "st.page_link(" in app


@pytest.mark.parametrize(
    "class_name",
    [
        "sle-drawer-tab",
        "sle-drawer-close",
        "sle-tray",
        "sle-tray-count",
        "sle-tray-search",
        "sle-tray-list",
        "sle-tray-empty",
    ],
)
def test_the_space_drawer_selectors_exist_in_the_editor(class_name: str) -> None:
    html = _text(COMPONENTS / "space_layout_editor_assets" / "editor.html")
    assert f'class="{class_name}"' in html


def test_the_space_chip_names_are_what_the_order_check_reads() -> None:
    editor = _text(COMPONENTS / "space_layout_editor_assets" / "editor.js")
    assert "chip.className = 'sle-chip'" in editor
    assert "text.className = 'sle-chip-name'" in editor
    assert "new Intl.Collator('ko', { numeric: true, sensitivity: 'base' })" in editor


@pytest.mark.parametrize(
    ("path", "label"),
    [
        ("src/capa_simulation/components/equipment_data_workspace.py", 'st.selectbox("등록할 표"'),
        ("src/capa_simulation/components/equipment_data_workspace.py", '_TARGETS = ("설비 마스터"'),
        (
            "src/capa_simulation/components/equipment_data_workspace.py",
            '["입력", "직접 편집", "저장 이력"]',
        ),
        ("src/capa_simulation/components/shortening_progress_panel.py", '"진척 비교",'),
        ("src/capa_simulation/components/shortening_progress_panel.py", '"비교 안 함"'),
        ("src/capa_simulation/components/required_shortening_panel.py", '"목표 확보율",'),
        (
            "app_pages/available_equipment_status.py",
            'TAB_RAWDATA = ":material/table_rows: RawData"',
        ),
        ("src/capa_simulation/navigation.py", '":material/event_upcoming: 필요단축일정"'),
        ("app_pages/space_status.py", '"층 바로 가기",'),
        ("app_pages/space_status.py", '"배치 편집",'),
        ("app_pages/space_status.py", '"미배치대수":'),
    ],
)
def test_the_labels_the_items_look_for_exist_in_the_app(path: str, label: str) -> None:
    assert label in _text(PROJECT_ROOT / path)


@pytest.mark.parametrize(
    "page",
    [
        screens.EQUIPMENT_PAGE,
        screens.SPACE_PAGE,
        screens.SCENARIO_MANAGEMENT_PAGE,
        screens.ADMIN_AREA_PAGE,
        screens.PROCESS_DETAIL_PAGE,
    ],
)
def test_the_pages_the_items_open_exist(page: str) -> None:
    assert (PROJECT_ROOT / "app_pages" / f"{page}.py").is_file()


# ------------------------------------------------------- 이번 배포 항목(통합 조건 패널 뒤)

NEW_ITEM_KEYS = [
    "sidebar_panel",
    "panel_rows_other_pages",
    "scenario_popup",
    "period_popup",
    "process_popup",
    "process_detail",
    "equipment_headers",
    "sidebar_groups",
    "space_fader",
    "gap_sheet",
]


def test_this_deploys_items_follow_the_five_pilot_items_and_do_not_write() -> None:
    keys = [item.key for item in ITEMS]

    assert keys[:5] == ["toolbar", "symbol", "rawdata_target", "progress_box", "space_drawer"]
    assert keys[5:] == NEW_ITEM_KEYS
    assert not any(item.writes for item in ITEMS if item.key in NEW_ITEM_KEYS)


def test_the_list_shows_this_deploys_items(capsys: pytest.CaptureFixture[str]) -> None:
    assert screens.main(["--list"]) == screens.EXIT_OK
    out = capsys.readouterr().out
    for item in ITEMS[5:]:
        assert f"| `{item.key}` | {item.title} | 없음 |" in out


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("시나리오", "시나리오"),
        ("시나리오 · r12", "시나리오"),
        (f"시나리오 · {SENTINEL}", "시나리오"),
        ("조회기간", "조회기간"),
        (" 공정 필터 ", "공정 필터"),
        ("주요공정 히트맵", "주요공정 히트맵"),
        ("B/N 집계 공정", "그 밖"),
        ("시나리오관리", "그 밖"),
        (SENTINEL, "그 밖"),
        ("", "그 밖"),
    ],
)
def test_panel_row_names_are_mapped_to_the_fixed_vocabulary(text: str, expected: str) -> None:
    assert screens.panel_row_name(text) == expected


def _panel(rows: list[str] | None, **overrides: Any) -> dict[str, Any]:
    facts: dict[str, Any] = {"title": "조회 조건", "rows": rows, "cards": 1, "below": True}
    facts.update(overrides)
    return facts


def test_the_home_panel_summary_reads_the_order_and_the_card() -> None:
    rows = ["시나리오 · r7", "조회기간", "공정 필터", "주요공정 히트맵"]

    assert screens.summarize_panel(_panel(rows), 0) == (
        "「조회 조건」 제목 있음 · 패널 4줄(시나리오 · 조회기간 · 공정 필터 · 주요공정 히트맵) "
        "— 정한 차례와 같음 · 옛 상자 제목 0곳 · LOB 표시 조건 카드 패널 아래 있음"
    )
    assert screens.summarize_panel(None, 2) == "「조회 조건」 패널 없음 · 옛 상자 제목 2곳"


def test_the_home_panel_summary_never_carries_screen_text() -> None:
    rows = [f"시나리오 · {SENTINEL}", "조회기간", SENTINEL]

    result = screens.summarize_panel(_panel(rows, title=SENTINEL, cards=1, below=False), 1)

    assert SENTINEL not in result and "ZZSENTINEL" not in result
    assert "제목 없음" in result
    assert "패널 3줄(시나리오 · 조회기간 · 그 밖) — 정한 차례와 다름" in result
    assert "옛 상자 제목 1곳" in result
    assert result.endswith("LOB 표시 조건 카드 있음(패널 아래 아님)")
    assert screens.summarize_panel(_panel([], cards=0), 0).endswith(
        "패널 0줄(줄 없음) — 정한 차례와 다름 · 옛 상자 제목 0곳 · LOB 표시 조건 카드 없음"
    )


def test_the_other_pages_summary_says_whether_the_rows_are_as_declared() -> None:
    seen = [
        ("시나리오 관리", ("시나리오", "조회기간"), ["시나리오 · r3", "조회기간"]),
        ("Admin Area", ("시나리오",), ["시나리오 · r3"]),
        ("Space 현황", None, None),
    ]

    assert screens.summarize_other_pages(seen) == (
        "시나리오 관리 2줄(시나리오 · 조회기간) · Admin Area 1줄(시나리오) · Space 현황 패널 없음 "
        "— 정한 대로 같음"
    )
    wrong = [
        ("Admin Area", ("시나리오",), [f"시나리오 · {SENTINEL}", SENTINEL]),
        ("Space 현황", None, []),
    ]
    result = screens.summarize_other_pages(wrong)
    assert SENTINEL not in result
    assert result == ("Admin Area 2줄(시나리오 · 그 밖) · Space 현황 0줄(줄 없음) — 정한 대로 다름")


def test_the_scenario_popup_summary() -> None:
    load = {"modes": ["불러오기", "새 리비전 저장"], "selected": "불러오기", "revisions": 3}

    result = screens.summarize_scenario_dialog("시나리오·리비전", load, True)
    assert result == (
        "팝업 제목 「시나리오·리비전」 같음 · 구획 「불러오기」·「새 리비전 저장」 있음 · "
        "리비전 3개 · Esc 닫힘"
    )
    # 결과 표는 `|` 를 `/` 로 바꾼다 — 그 글자를 쓰지 않는다.
    assert "|" not in result
    save = {**load, "selected": "새 리비전 저장", "revisions": None}
    assert "저장 구획으로 열림(리비전 목록 안 셈)" in screens.summarize_scenario_dialog(
        "시나리오·리비전", save, True
    )
    odd = {"modes": [SENTINEL], "selected": SENTINEL, "revisions": 9}
    result = screens.summarize_scenario_dialog(SENTINEL, odd, False)
    assert SENTINEL not in result
    assert result == (
        "팝업 제목 「시나리오·리비전」 다름 · 구획 「불러오기」·「새 리비전 저장」 없음 · "
        "구획 모름 · Esc 안 닫힘"
    )
    assert screens.summarize_scenario_dialog(None, None, True) == "팝업 안 열림"


def test_the_period_popup_summary() -> None:
    facts = {"months": 2, "apply": "적용", "inComponent": True}

    assert screens.summarize_period_dialog("조회기간", facts, True, True) == (
        "팝업 제목 「조회기간」 같음 · 월 칸 2개 · 「적용」 단추 컴포넌트 안 있음 · "
        "Esc 닫힘(적용 안 함) · 값 칸 글자 같음"
    )
    outside = screens.summarize_period_dialog(
        "조회기간", {**facts, "inComponent": False}, True, False
    )
    assert "「적용」 단추 있음(컴포넌트 밖)" in outside and outside.endswith("값 칸 글자 다름")
    odd = screens.summarize_period_dialog(SENTINEL, {**facts, "apply": SENTINEL}, False, True)
    assert SENTINEL not in odd
    assert "팝업 제목 「조회기간」 다름" in odd and "「적용」 단추 없음" in odd
    assert "Esc 안 닫힘" in odd


@pytest.mark.parametrize(
    ("place", "expected"),
    [
        ("head", "판정 기준 안내 머리에 있음"),
        ("body", "판정 기준 안내 머리에 없음(아래에 있음)"),
        ("none", "판정 기준 안내 없음"),
        (SENTINEL, "판정 기준 안내 없음"),
    ],
)
def test_the_process_popup_summary(place: str, expected: str) -> None:
    result = screens.summarize_process_dialog("공정 필터", {"pointer": place}, True)

    assert result == f"팝업 제목 「공정 필터」 같음 · {expected} · Esc 닫힘"


class _DialogScreen(Screen):
    """팝업 항목의 뼈대 호출만 흉내 낸다 — 본문 읽기가 실패해도 팝업이 닫히는지 본다."""

    def __init__(self, *, broken: bool) -> None:
        super().__init__(page=None, base_url="http://127.0.0.1:8559/")
        self.broken = broken
        self.calls: list[str] = []
        self.open = 0

    def open_home(self) -> None:
        self.calls.append("home")

    def open_dialog(self, selector: str, *, timeout: float = 30.0) -> None:
        self.calls.append("open")
        self.open = 1

    def dialog_title(self) -> str | None:
        return "시나리오·리비전" if self.open else None

    def dialog_read(self, script: str, arg: object = None) -> Any:
        if self.broken:
            raise RuntimeError(SENTINEL)
        return {"modes": ["불러오기", "새 리비전 저장"], "selected": "불러오기", "revisions": 2}

    def dialog_count(self) -> int:
        return self.open

    def close_dialog(self, timeout: float = 10.0) -> bool:
        self.calls.append("close")
        self.open = 0
        return True

    def js(self, script: str, arg: object = None) -> Any:
        return False

    def close_overlay(self) -> None:
        self.calls.append("overlay")


def test_a_popup_item_closes_its_popup_even_when_reading_fails() -> None:
    item = next(item for item in ITEMS if item.key == "scenario_popup")
    screen = _DialogScreen(broken=True)

    outcomes = screens.run_items(screen, [item], allow_writes=False, deadline=NO_DEADLINE)

    assert outcomes[0].result == "미기록 — RuntimeError"
    assert screen.calls[-1] == "close" and screen.open == 0


def test_the_scenario_popup_item_reads_then_closes() -> None:
    screen = _DialogScreen(broken=False)

    result = screens.check_scenario_popup(screen)

    assert screen.calls == ["home", "open", "close"]
    assert result.endswith("리비전 2개 · Esc 닫힘")


def test_settle_closes_a_popup_left_open_by_an_earlier_item() -> None:
    screen = _DialogScreen(broken=False)
    screen.open = 1

    screen.settle()

    assert screen.calls == ["close", "overlay"]
    assert screen.open == 0


def test_the_condition_panel_contract_matches_the_app() -> None:
    from capa_simulation import sidebar_status
    from capa_simulation.components import condition_field, period_field, scenario_status
    from capa_simulation.components.home_preference import (
        KEY_PROCESS_FIELD_LABEL,
        THRESHOLD_POINTER,
    )
    from capa_simulation.navigation import CONDITIONS_SECTION

    assert screens.CONDITIONS_SECTION_KEY == CONDITIONS_SECTION.key
    assert screens.CONDITIONS_SECTION_TITLE == CONDITIONS_SECTION.title
    assert screens.CONDITIONS_BOX_KEY == sidebar_status.CONDITIONS_BOX_KEY
    assert screens.CONDITION_CARD_PREFIX == sidebar_status.CONDITION_CARD_PREFIX
    assert screens.CONDITION_NAME_ROW_PREFIX == condition_field.NAME_ROW_KEY_PREFIX
    assert screens.SCENARIO_FIELD_KEY == scenario_status.SCENARIO_FIELD_KEY
    assert screens.SCENARIO_DIALOG_TITLE == scenario_status.SCENARIO_DIALOG_TITLE
    assert screens.SCENARIO_DIALOG_MODES == (scenario_status.LOAD_MODE, scenario_status.SAVE_MODE)
    assert screens.PERIOD_FIELD_KEY == period_field.PERIOD_FIELD_KEY
    assert screens.PERIOD_DIALOG_TITLE == period_field.PERIOD_FIELD_LABEL
    assert screens.THRESHOLD_POINTER == THRESHOLD_POINTER
    assert screens.PANEL_ROW_NAMES == (
        scenario_status.SCENARIO_FIELD_LABEL,
        period_field.PERIOD_FIELD_LABEL,
        screens.PROCESS_DIALOG_TITLE,
        KEY_PROCESS_FIELD_LABEL,
    )
    # 시나리오 줄 이름은 「시나리오 · rN」이다 — 앞머리로 어휘에 든다.
    assert screens.panel_row_name(scenario_status.scenario_name_label(12)) == "시나리오"
    assert screens.panel_row_name(scenario_status.scenario_name_label(None)) == "시나리오"


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("app.py", 'st.sidebar.container(key="home_navigation")'),
        ("app_pages/home.py", 'PROCESS_FIELD_LABEL = "공정 필터"'),
        ("app_pages/home.py", 'PROCESS_FIELD_KEY = "dashboard_bottleneck_process_dialog_open"'),
        ("app_pages/home.py", "@st.dialog(\n    PROCESS_FIELD_LABEL,"),
        ("app_pages/home.py", "st.caption(THRESHOLD_POINTER)"),
        ("app_pages/home.py", 'HOME_TAB_LABELS = (":material/dashboard: Main"'),
        (
            "src/capa_simulation/components/home_preference.py",
            'condition_card("LOB 표시 조건", name="home")',
        ),
        ("src/capa_simulation/components/scenario_status.py", '"리비전",'),
        (
            "src/capa_simulation/components/month_range_picker.py",
            '<input id="capa-start-month" type="month"',
        ),
        (
            "src/capa_simulation/components/month_range_picker.py",
            '<input id="capa-end-month" type="month"',
        ),
        (
            "src/capa_simulation/components/month_range_picker.py",
            '<button id="capa-month-apply" type="button" class="capa-month-apply">적용</button>',
        ),
        ("src/capa_simulation/components/month_range_picker.py", "isolate_styles=False,"),
    ],
)
def test_the_panel_texts_the_items_look_for_exist_in_the_app(path: str, text: str) -> None:
    assert text in _text(PROJECT_ROOT / path)


def test_the_month_picker_ids_are_the_ones_the_item_reads() -> None:
    picker = _text(COMPONENTS / "month_range_picker.py")

    assert all(f'id="{name}"' in picker for name in screens.MONTH_INPUT_IDS)
    assert f'id="{screens.MONTH_APPLY_ID}"' in picker
    assert f">{screens.MONTH_APPLY_LABEL}</button>" in picker


def test_the_other_page_panels_follow_the_navigation_declarations() -> None:
    from capa_simulation.navigation import ALL_SPECS

    specs = {Path(spec.path).stem: spec for spec in ALL_SPECS}
    for page, _title, expected in screens.OTHER_PAGE_PANELS:
        spec = specs[page]
        # 탭으로 가르지 않고, 주소 끝이 파일 이름이다(`open_page` 가 그 끝으로 찾는다).
        assert spec.condition_tabs is None and spec.url_path is None
        rows = tuple(
            name
            for name, shown in (("시나리오", spec.reads_scenario), ("조회기간", spec.reads_period))
            if shown
        )
        assert (rows or None) == expected


@pytest.fixture(autouse=True)
def _no_real_side_effects(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """어느 테스트도 진짜 프로세스를 살피지 않는다."""
    monkeypatch.setattr(screens, "running_app_count", lambda: 0)
    yield


# ------------------------------------------------------------------ 공정 Capa 상세


def test_the_process_detail_contract_matches_the_app() -> None:
    from capa_simulation.components import process_capa_canvas, process_capa_view
    from capa_simulation.navigation import PROCESS_CAPA_DETAIL
    from capa_simulation.process_detail_state import PROCESS_DETAIL_CANVAS_CHART_KEY

    assert PROCESS_CAPA_DETAIL.path == f"app_pages/{screens.PROCESS_DETAIL_PAGE}.py"
    assert screens.PROCESS_DETAIL_KEYS == {
        "kpi": process_capa_view.KPI_ROW_KEY,
        "canvas": PROCESS_DETAIL_CANVAS_CHART_KEY,
        "scroll": f"{process_capa_view.SCROLL_KEY}_scroll",
        "evidence": process_capa_view.EVIDENCE_PANEL_KEY,
        "absent": process_capa_view.DYNAMIC_ABSENT_KEY,
    }
    assert screens.PROCESS_DETAIL_RATE_ROW_PX == (
        process_capa_canvas.HEADER_HEIGHT_PX
        + process_capa_canvas.SUMMARY_TITLE_HEIGHT_PX
        + process_capa_canvas.VALUE_ROW_HEIGHT_PX * 3
        + process_capa_canvas.VALUE_ROW_HEIGHT_PX // 2
    )


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        ({"month": "26.03"}, "바뀜"),
        ({"month": "26.01"}, "그대로"),
        (None, "못 누름"),
    ],
)
def test_the_process_detail_summary_counts_without_screen_text(
    after: dict[str, Any] | None, expected: str
) -> None:
    before = {"kpis": 4, "canvas": True, "month": "26.01", "cards": 3, "absent": True}
    line = screens.summarize_process_detail(before, after)

    assert line == (
        "KPI 4개 · 결합 캔버스 있음 · 근거 카드 3개 · 설비 일정 구획 없음(까닭 카드) · "
        f"칸 누름 뒤 근거 달 {expected}"
    )
    # 달·공정 글자는 찍지 않는다.
    assert "26." not in line


# ------------------------------------------------------------------ RawData 설비 마스터 머리(38열)


def test_the_equipment_header_names_match_the_contract() -> None:
    """스크립트는 계약을 부르지 않고 값만 옮긴다 — 계약과 같은지 여기서 본다."""
    from capa_simulation.services.equipment_contract import (
        AREA_CODE_COLUMN,
        ARRIVAL_ACTUAL_COLUMN,
        ARRIVAL_STATUS_COLUMN,
        EQUIPMENT_COLUMNS,
        OBSOLETE_EQUIPMENT_COLUMNS,
        QUAL_ACTUAL_COLUMN,
        QUAL_STATUS_COLUMN,
        RELOCATION_DATE_COLUMN,
        STOP_DATE_COLUMN,
    )

    assert screens.EQUIPMENT_NEW_HEADERS == (
        AREA_CODE_COLUMN,
        ARRIVAL_ACTUAL_COLUMN,
        ARRIVAL_STATUS_COLUMN,
        QUAL_ACTUAL_COLUMN,
        QUAL_STATUS_COLUMN,
        STOP_DATE_COLUMN,
        RELOCATION_DATE_COLUMN,
    )
    assert set(screens.EQUIPMENT_NEW_HEADERS) <= set(EQUIPMENT_COLUMNS)
    assert screens.EQUIPMENT_DROPPED_HEADER in OBSOLETE_EQUIPMENT_COLUMNS
    assert screens.EQUIPMENT_DROPPED_HEADER not in EQUIPMENT_COLUMNS
    assert screens.EQUIPMENT_EDITOR_ANCHOR in EQUIPMENT_COLUMNS


def test_the_equipment_header_summary_counts_and_names_only_missing_contract_names() -> None:
    every = dict.fromkeys(screens.EQUIPMENT_NEW_HEADERS, True)

    assert screens.summarize_equipment_headers(every, False) == (
        "새 이름 7/7 있음 · 「설비가동현황」 없음"
    )
    partial = {**every, "반입실적": False, "Qual실적": False}
    line = screens.summarize_equipment_headers(partial, True)
    assert line == "새 이름 5/7 있음(없음: 반입실적, Qual실적) · 「설비가동현황」 있음"
    # 결과 표 칸을 깨는 글자가 없다.
    assert "|" not in line
    assert screens.summarize_equipment_headers({}, False).startswith("새 이름 0/7 있음(없음: ")


# ------------------------------------------------------------------ 사이드바 그룹 셋


def test_the_sidebar_group_boxes_match_the_navigation_declaration() -> None:
    """스크립트는 선언을 부르지 않고 값만 옮긴다 — 하위가 있는 그룹의 slug·제목·하위 수가 선언과
    같은지 여기서 본다. 상자 key 는 `app.py` 가 `<slug>_box` 로 단다."""
    from capa_simulation.navigation import SIDEBAR_GROUPS

    declared = tuple(
        (group.slug, group.main.title, len(group.subpages))
        for group in SIDEBAR_GROUPS
        if group.subpages
    )
    assert screens.SIDEBAR_GROUP_BOXES == declared
    assert 'key=f"{group.slug}_box"' in (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")


def _box(
    slug: str,
    title: str,
    subpages: int,
    *,
    lines: int = 1,
    clipped: bool = False,
    ellipsis: bool = False,
    cut: bool = False,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "title": title,
        "links": subpages + 1,
        "lines": lines,
        "clipped": clipped,
        "ellipsis": ellipsis,
        "cut": cut,
    }


def test_the_sidebar_groups_summary_counts_and_names_only_fixed_titles() -> None:
    every = [_box(slug, title, count) for slug, title, count in screens.SIDEBAR_GROUP_BOXES]

    assert screens.summarize_sidebar_groups(every) == (
        "Static Capa 머리 + 4 · 실행 Management 머리 + 6 · Dynamic Capa 머리 + 1 — "
        "정한 차례·수와 같음 · 상자 제목 한 줄 · 잘림 없음"
    )
    # 차례가 바뀌거나 하나가 빠지거나 하위 수가 다르면 「다름」, 줄바꿈·말줄임은 그 상자 이름만
    # 적는다.
    swapped = [every[1], every[0], _box("dynamic_capa", "Dynamic Capa", 2)]
    swapped[0] = {**swapped[0], "lines": 2}
    line = screens.summarize_sidebar_groups(swapped)
    assert line == (
        "실행 Management 머리 + 6 · Static Capa 머리 + 4 · Dynamic Capa 머리 + 2 — "
        "정한 차례·수와 다름 · 줄바꿈: 실행 Management"
    )
    missing = screens.summarize_sidebar_groups([every[0], {**every[2], "clipped": True}])
    assert missing.endswith("정한 차례·수와 다름(없음: 실행 Management) · 잘림: Dynamic Capa")
    # 문단 안에서는 넘치지 않아도 조상 칸이 글자를 자르면 잘림이다.
    cut = screens.summarize_sidebar_groups([every[0], {**every[1], "cut": True}, every[2]])
    assert cut.endswith("정한 차례·수와 같음 · 잘림: 실행 Management")
    # 화면 제목이 다르면 화면 글자를 옮기지 않고 「제목 다름」만 적는다.
    renamed = screens.summarize_sidebar_groups([{**every[0], "title": SENTINEL}, *every[1:]])
    assert SENTINEL not in renamed
    assert renamed.startswith("Static Capa(제목 다름) 머리 + 4")
    assert "정한 차례·수와 다름" in renamed
    assert screens.summarize_sidebar_groups(None) == "그룹 상자 없음"
    # 결과 표 칸을 깨는 글자가 없다.
    assert "|" not in line


def test_the_narrow_sidebar_summary_accepts_ellipsis_and_flags_wrapping() -> None:
    """좁게 끈 폭에서는 말줄임이 정한 모양(개수만)이고 줄바꿈이 결함이다(2026-10-17 사용자 결정)."""
    every = [_box(slug, title, count) for slug, title, count in screens.SIDEBAR_GROUP_BOXES]
    clipped = [every[0], {**every[1], "clipped": True, "ellipsis": True}, every[2]]

    assert screens.summarize_sidebar_narrow({"width": 213, "boxes": every}) == "좁은 폭 213px 한 줄"
    assert (
        screens.summarize_sidebar_narrow({"width": 213, "boxes": clipped})
        == "좁은 폭 213px 한 줄(말줄임 1)"
    )
    wrapped = [every[0], {**every[1], "lines": 2, "clipped": True, "ellipsis": True}, every[2]]
    assert (
        screens.summarize_sidebar_narrow({"width": 200, "boxes": wrapped})
        == "좁은 폭 200px 줄바꿈: 실행 Management"
    )
    # 넘쳤는데 말줄임이 없거나(규칙이 빠짐) 조상 칸이 자르면 결함이다. 보이는 링크도 센다.
    bare = [every[0], {**every[1], "clipped": True}, {**every[2], "cut": True}]
    assert (
        screens.summarize_sidebar_narrow({"width": 200, "boxes": bare, "links_cut": 2})
        == "좁은 폭 200px 말줄임 없이 잘림: 실행 Management, Dynamic Capa"
        " · 링크 말줄임 없이 잘림 2"
    )
    assert (
        screens.summarize_sidebar_narrow({"width": 200, "boxes": clipped, "links_cut": 1})
        == "좁은 폭 200px 링크 말줄임 없이 잘림 1"
    )
    assert screens.summarize_sidebar_narrow(None) == "좁은 폭 못 잼"
    assert screens.summarize_sidebar_narrow({"width": 200, "boxes": []}) == "좁은 폭 못 잼"
    assert screens.SIDEBAR_NARROW_WIDTH_PX == 200
    # 좁히는 스크립트는 기본 폭을 재는 스크립트를 그대로 품고, 잰 뒤 원래 폭으로 되돌린다.
    assert screens._SIDEBAR_GROUPS_JS in screens._SIDEBAR_GROUPS_NARROW_JS
    assert 'removeAttribute("style")' in screens._SIDEBAR_GROUPS_NARROW_JS
    assert 'side.style.transition = "none"' in screens._SIDEBAR_GROUPS_NARROW_JS
    # 잘림 판정 하나를 그룹 제목과 링크가 함께 쓴다 — 말줄임은 문단이 실제로 잘라 낼 때만 그려진다.
    assert screens._TEXT_CLIP_JS in screens._SIDEBAR_GROUPS_JS
    assert screens._SIDEBAR_GROUPS_NARROW_JS.count(screens._TEXT_CLIP_JS) == 2
    assert 'style.textOverflow === "ellipsis" && ownClip' in screens._TEXT_CLIP_JS


# ------------------------------------------------------- Space 기준일 페이더(`space_fader`)


@pytest.mark.parametrize(
    "class_name",
    ["sle-fader-input", "sle-fader-today", "sle-fader-rel"],
)
def test_the_space_fader_selectors_exist_in_the_editor(class_name: str) -> None:
    html = _text(COMPONENTS / "space_layout_editor_assets" / "editor.html")
    assert f'class="{class_name}"' in html


def test_the_space_fader_item_reads_what_the_app_draws() -> None:
    """항목이 읽는 것 — 호기 상자 class(`sle-unit`), 오늘 칩의 `is-today`, 범례 끝의 「기준 날짜」,
    층 목록 표의 `배치대수` 칸 — 이 앱에 있다. 페이더는 PageUp 으로 한 달을 옮긴다."""
    editor = _text(COMPONENTS / "space_layout_editor_assets" / "editor.js")
    assert "'sle-item sle-unit'" in editor
    assert "faderRel.classList.toggle('is-today', isToday)" in editor
    assert "PageUp: addMonths(now, 1)" in editor
    legend = _text(COMPONENTS / "space_layout.py")
    assert "기준 {as_of.isoformat()}" in legend
    found = screens._LEGEND_DATE.search("PKG 3대 기준 2026-10-17")
    assert found is not None and found.group(1) == "2026-10-17"
    # 「기준일 …에 반출/이설을 마친」(FAB 안내)은 범례 날짜가 아니다.
    assert screens._LEGEND_DATE.search("기준일 2026-10-17에 반출/이설") is None
    assert '"배치대수":' in _text(PROJECT_ROOT / "app_pages" / "space_status.py")


def test_the_space_fader_summary_carries_counts_only() -> None:
    line = screens.summarize_space_fader(1289.0, 37, True, True)
    assert line == (
        "배치 최다 층 1289대 · +1개월에 class 바뀐 상자 37개 · 놓은 뒤 범례 기준일 바뀜 · "
        "「오늘」 돌아옴"
    )
    assert "|" not in line
    assert "범례 없음" in screens.summarize_space_fader(1.5, 0, None, False)
    assert "안 돌아옴" in screens.summarize_space_fader(1.5, 0, False, False)


# ------------------------------------------------------- Static 대비 일정 비교 시트(`gap_sheet`)


def test_the_gap_sheet_contract_matches_the_app() -> None:
    """스크립트는 앱 모듈을 부르지 않고 값만 옮긴다 — key·탭·전환·닫힘 안내·9행 라벨·누를 칸이 앱과
    같은지 여기서 본다."""
    from capa_simulation.components import availability_gap_panel as panel
    from capa_simulation.components import availability_sheet_keys as keys
    from capa_simulation.components.availability_sheet_canvas import GROUP_TITLES
    from capa_simulation.navigation import EQUIPMENT_GAP_TAB
    from capa_simulation.services.availability_sheet import (
        ROW_ITEMS,
        ROW_SCHEDULE_AVAILABLE,
        ROW_SCHEDULE_LENT,
        SHEET_ROWS,
    )

    assert screens.GAP_SHEET_KEYS == {
        "chart": keys.GAP_SHEET_CHART_KEY,
        "labels": keys.GAP_SHEET_LABEL_CHART_KEY,
        "scroll": f"{keys.GAP_SHEET_SCROLL_KEY}_scroll",
        "evidence": keys.GAP_SHEET_EVIDENCE_KEY,
    }
    assert EQUIPMENT_GAP_TAB.endswith(f" {screens.GAP_TAB}")
    assert screens.GAP_RESULT_VIEW_KEY == panel.RESULT_VIEW_KEY
    assert screens.GAP_SHEET_VIEW in panel._RESULT_VIEWS
    assert screens.GAP_DETAIL_MODE_KEY == panel.DETAIL_MODE_KEY
    assert screens.GAP_SHEET_MODE == panel._DETAIL_MODES[0]
    source = _text(COMPONENTS / "availability_gap_panel.py")
    assert f'st.markdown("**{screens.GAP_SHEET_CLOSED_TEXT}**")' in source
    # 월 칸 스크롤 상자는 `horizontal_scroll_canvas(key=…)` 의 `<key>_scroll` 이다.
    assert 'target_selector=f".st-key-{GAP_SHEET_SCROLL_KEY}_scroll"' in source
    assert screens.GAP_SHEET_ROWS == tuple(
        (GROUP_TITLES[row.split(":")[0]], ROW_ITEMS[row]) for row in SHEET_ROWS
    )
    assert screens.GAP_SHEET_SCHEDULE_CELLS == (
        (ROW_SCHEDULE_LENT, ROW_ITEMS[ROW_SCHEDULE_LENT]),
        (ROW_SCHEDULE_AVAILABLE, ROW_ITEMS[ROW_SCHEDULE_AVAILABLE]),
    )
    # 칸 누름 세대는 월 그림 `layout.meta.generation` 이다 — 항목은 그것이 오르는 것을 기다린다.
    assert "plot.layout.meta.generation" in screens._GAP_SHEET_JS
    canvas = _gap_canvas((0.0, 0.0, 0.0), generation=7)
    assert canvas.months.to_plotly_json()["layout"]["meta"]["generation"] == 7
    # 칸 선택을 켠 그림이라 앱의 터치 스크롤 막이 묶음(`CELL_SELECT_CHART_KEYS`)에 든다.
    tree = ast.parse(_text(PROJECT_ROOT / "app.py"))
    members = [
        element.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and [getattr(target, "id", None) for target in node.targets] == ["CELL_SELECT_CHART_KEYS"]
        and isinstance(node.value, ast.Tuple)
        for element in node.value.elts
        if isinstance(element, ast.Name)
    ]
    assert "GAP_SHEET_CHART_KEY" in members
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == keys.__name__
        and any(
            alias.name == "GAP_SHEET_CHART_KEY" and alias.asname is None for alias in node.names
        )
        for node in tree.body
    )


def test_the_evidence_heading_the_item_looks_for_is_what_the_app_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """근거 카드 제목(h5)은 `<달> · <구획> <행 라벨> · <공정 표시명>` 이다 — 항목은 공정 이름
    앞까지의 고정 앞머리로 시작하는가만 본다."""
    from contextlib import nullcontext

    from capa_simulation.components import availability_gap_panel as panel
    from capa_simulation.services.month_columns import month_label

    written: list[str] = []
    fake = SimpleNamespace(
        container=lambda **kwargs: nullcontext(),
        markdown=lambda body, **kwargs: written.append(str(body)),
        caption=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(panel, "st", fake)
    # 값이 없는 칸이면 제목 뒤에 까닭 안내만 선다 — 제목 꼴만 본다.
    bundle: Any = SimpleNamespace(
        view=SimpleNamespace(value=lambda row, month: None, reason=lambda row, month: None),
        process_label=SENTINEL,
    )
    for month in (202512, 202601, 202611):
        for row, label in screens.GAP_SHEET_SCHEDULE_CELLS:
            written.clear()
            panel._render_evidence(bundle, (month, row))
            heading = screens.gap_evidence_heading((month, row))
            assert heading == f"{month_label(month)} · 설비 일정 기준 {label} · "
            assert written[0] == f"##### {heading}{SENTINEL}"
    # 대여 (비가동) 칸의 앞머리가 다른 행 라벨의 앞머리가 되지 않는다(뒤 「 · 」 까지 본다).
    lent, available = (
        screens.gap_evidence_heading((202611, row)) for row, _ in screens.GAP_SHEET_SCHEDULE_CELLS
    )
    assert not lent.startswith(available) and not available.startswith(lent)


_GAP_MONTHS = (202610, 202611, 202612)


def _gap_canvas(
    lent: tuple[float, ...], *, selected: tuple[int, str] | None = None, generation: int = 0
) -> Any:
    """앱이 그리는 시트 그림 한 쌍. 머리 글에 공정 이름 대신 `SENTINEL` 을 넣는다."""
    import pandas as pd

    from capa_simulation.components.availability_sheet_canvas import (
        build_availability_sheet_canvas,
    )
    from capa_simulation.services.availability_sheet import SHEET_ROWS, SheetView

    values = pd.DataFrame(1.0, index=list(SHEET_ROWS), columns=list(_GAP_MONTHS))
    values.loc["sched:lent"] = list(lent)
    values.loc["sched:available", 202610] = 0.0
    values.loc["static:lent", 202610] = float("nan")
    view = SheetView(months=_GAP_MONTHS, values=values)
    return build_availability_sheet_canvas(
        view=view,
        process_label=SENTINEL,
        schedule_detail="설비 DB · 환산대수 · Cut-off 공정별",
        selected=selected,
        generation=generation,
    )


def _gap_notes(canvas: Any) -> list[dict[str, Any]]:
    """`_GAP_SHEET_JS` 가 라벨 그림에서 읽는 꼴."""
    return [
        {
            "text": note["text"],
            "shift": note.get("xshift", 0),
            "size": note.get("font", {}).get("size", 0),
            "y": note["y"],
        }
        for note in canvas.labels.to_plotly_json()["layout"]["annotations"]
    ]


def _gap_cells(canvas: Any) -> list[dict[str, Any]]:
    """`_GAP_SHEET_JS` 가 월 그림에서 읽는 꼴 — 표적 막대마다 칸 가운데 글자(굵게 뗌)와 굵은가."""
    data = canvas.months.to_plotly_json()["data"]
    written: dict[tuple[int, int], str] = {}
    for trace in data[1:]:
        if trace.get("mode") != "text":
            continue
        for x, y, text in zip(trace["x"], trace["y"], trace["text"], strict=True):
            written[(round((x - 0.5) * 1000), round(y * 1000))] = str(text)
    target = data[0]
    cells = []
    for point, x, y in zip(target["customdata"], target["base"], target["y"], strict=True):
        text = written.get((round(x * 1000), round(y * 1000)))
        cells.append(
            {
                "month": point[0],
                "row": point[1],
                "text": None if text is None else screens._HTML_TAG.sub("", text).strip(),
                "bold": text is not None and text.lstrip().lower().startswith("<b>"),
            }
        )
    return cells


def test_the_gap_sheet_rows_are_read_from_what_the_app_draws() -> None:
    canvas = _gap_canvas((0.0, -0.66, 0.0))
    notes = _gap_notes(canvas)

    rows = screens.gap_sheet_row_labels(notes)
    assert rows == screens.GAP_SHEET_ROWS
    # 머리 글(공정 이름 자리)은 행에 실리지 않는다. 주석 차례가 섞여도 세로 자리로 읽는다.
    assert SENTINEL not in repr(rows)
    assert screens.gap_sheet_row_labels(list(reversed(notes))) == rows
    assert screens.gap_sheet_row_labels([]) == ()


def test_the_gap_sheet_cell_to_click_prefers_a_non_zero_lent_month() -> None:
    cells = _gap_cells(_gap_canvas((0.0, -0.66, 0.0)))
    assert {cell["text"] for cell in cells if cell["row"] == "sched:lent"} == {"0.00", "−0.66"}

    assert screens.gap_sheet_click_target(cells) == ((202611, "sched:lent"), 1)
    # 대여(비가동)가 모두 0 이면 0 아닌 가용 칸의 첫 달이다(202610 가용은 0).
    quiet = _gap_cells(_gap_canvas((0.0, 0.0, 0.0)))
    assert screens.gap_sheet_click_target(quiet) == ((202611, "sched:available"), 0)
    # 값이 없는(「—」) 칸은 누르지 않는다. 가용이 모두 0 이면 0 칸이라도 누른다.
    empty = [{**cell, "text": "—"} for cell in quiet]
    assert screens.gap_sheet_click_target(empty) == (None, 0)
    zero = [{**cell, "text": "0.00"} for cell in quiet]
    assert screens.gap_sheet_click_target(zero) == ((202610, "sched:available"), 0)


def test_the_bold_cell_is_the_one_the_sheet_selected() -> None:
    aimed = (202611, "sched:lent")
    cells = _gap_cells(_gap_canvas((0.0, -0.66, 0.0), selected=aimed))

    assert screens.gap_sheet_bold_cells(cells) == [aimed]
    assert screens.gap_sheet_bold_cells(_gap_cells(_gap_canvas((0.0, -0.66, 0.0)))) == []
    # 굵은 칸도 글자는 굵게 뗀 값이다 — 누를 칸 고르기가 그대로다.
    assert screens.gap_sheet_click_target(cells) == (aimed, 1)


def test_the_gap_sheet_summary_carries_counts_and_fixed_words_only() -> None:
    rows = screens.GAP_SHEET_ROWS
    line = screens.summarize_gap_sheet(rows, 4, 2, "sched:lent", True, True, 3, True, 0)

    assert line == (
        "행 9 — 정한 차례와 같음 · 달 4칸 · 대여(비가동) 0 아닌 달 2 · "
        "「설비 일정 기준 대여 (비가동)」 칸 누름 → 근거 카드 열림 · 근거 표 3줄(합계 뺌) · "
        "같은 칸 다시 누름 → 닫힘 · 예외 0"
    )
    assert "|" not in line
    swapped = (rows[1], rows[0], *rows[2:])
    assert "행 9 — 정한 차례와 다름" in screens.summarize_gap_sheet(
        swapped, 4, 0, "sched:available", True, True, 5, False, 0
    )
    # 화면 글자가 다르면 같음·다름만 적는다 — 화면 글자를 옮기지 않는다.
    renamed = ((SENTINEL, "보유"), *rows[1:])
    other = screens.summarize_gap_sheet(renamed, 4, 0, "sched:available", True, True, 5, False, 1)
    assert SENTINEL not in other
    assert other.endswith(
        "「설비 일정 기준 가용」 칸 누름 → 근거 카드 열림 · 근거 표 5줄(합계 뺌) · "
        "같은 칸 다시 누름 → 안 닫힘 · 예외 1"
    )
    assert screens.summarize_gap_sheet(rows[:8], 4, 0, None, False, False, None, None, 0) == (
        "행 8 — 정한 차례와 다름 · 달 4칸 · 대여(비가동) 0 아닌 달 0 · "
        "값 있는 설비 일정 기준 칸 없음(안 누름) · 예외 0"
    )
    not_opened = screens.summarize_gap_sheet(
        rows, 4, 0, "sched:available", False, False, None, None, 0
    )
    assert not_opened.endswith("칸 누름 → 근거 카드 안 열림 · 예외 0")
    assert "근거 카드 열림 · 근거 표 없음 · 같은 칸" in screens.summarize_gap_sheet(
        rows, 4, 0, "sched:available", True, True, None, True, 0
    )
    # 카드가 열렸어도 제목 앞머리·굵은 칸이 누른 칸이 아니면 「다른 칸 열림」 이고 표 줄을 세지
    # 않는다.
    elsewhere = screens.summarize_gap_sheet(rows, 4, 2, "sched:lent", True, False, 3, True, 0)
    assert elsewhere.endswith(
        "「설비 일정 기준 대여 (비가동)」 칸 누름 → 다른 칸 열림 · "
        "같은 칸 다시 누름 → 닫힘 · 예외 0"
    )
    assert "근거 카드 열림" not in elsewhere and "근거 표" not in elsewhere
    assert screens.summarize_gap_sheet(None, 0, 0, None, False, False, None, None, 2) == (
        "비교 시트 없음 · 예외 2"
    )


class _GapSheetScreen(_FakeScreen):
    """페이지·탭을 여는 대신 아무것도 하지 않는 화면 — 전환과 시트 읽기는 테스트가 바꿔 끼운다."""

    def open_page(self, href_suffix: str) -> None:
        pass

    def open_tab(self, name: str) -> None:
        pass


@pytest.mark.parametrize(
    ("shown", "restored"),
    [
        (
            {
                screens.GAP_RESULT_VIEW_KEY: "가용대수 비교",
                screens.GAP_DETAIL_MODE_KEY: "호기 목록",
            },
            [
                (screens.GAP_DETAIL_MODE_KEY, "호기 목록"),
                (screens.GAP_RESULT_VIEW_KEY, "가용대수 비교"),
            ],
        ),
        # 이미 그 선택지였던 전환은 바꾸지 않았으니 되돌리지도 않는다.
        (
            {
                screens.GAP_RESULT_VIEW_KEY: screens.GAP_SHEET_VIEW,
                screens.GAP_DETAIL_MODE_KEY: "호기 목록",
            },
            [(screens.GAP_DETAIL_MODE_KEY, "호기 목록")],
        ),
    ],
)
def test_the_gap_sheet_item_restores_the_switches_it_changed_even_when_reading_fails(
    monkeypatch: pytest.MonkeyPatch,
    shown: dict[str, str],
    restored: list[tuple[str, str]],
) -> None:
    from capa_simulation.components import availability_gap_panel as panel

    assert set(shown.values()) <= {*panel._RESULT_VIEWS, *panel._DETAIL_MODES}
    first = dict(shown)
    chosen: list[tuple[str, str]] = []

    def choose(screen: Screen, key: str, option: str) -> str | None:
        chosen.append((key, option))
        before = shown[key]
        shown[key] = option
        return before

    def broken(screen: Screen, *, timeout: float = 30.0) -> Any:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(screens, "_choose_segment", choose)
    monkeypatch.setattr(screens, "_gap_sheet", broken)
    item = next(item for item in ITEMS if item.key == "gap_sheet")

    outcomes = screens.run_items(
        _GapSheetScreen(), [item], allow_writes=False, deadline=NO_DEADLINE
    )

    assert outcomes[0].result == "미기록 — RuntimeError"
    assert chosen[:2] == [
        (screens.GAP_RESULT_VIEW_KEY, screens.GAP_SHEET_VIEW),
        (screens.GAP_DETAIL_MODE_KEY, screens.GAP_SHEET_MODE),
    ]
    # 바꾼 것만, 바꾼 차례의 거꾸로 되돌린다 — 화면은 처음 선택지로 돌아온다.
    assert chosen[2:] == restored
    assert shown == first
