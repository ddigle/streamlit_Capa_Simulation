# Purpose: 사내 배포 화면 확인 스크립트의 경로 거절·사전 확인·앱 수명·항목·결과 꼴을 고정한다.

from __future__ import annotations

import argparse
import ast
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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


def _flaky(runs: list[str], *, failures: int, error: type[Exception] = TimeoutError) -> Item:
    def run(screen: Screen) -> str:
        runs.append("run")
        screen.step("층 고르기")
        if len(runs) <= failures:
            raise error(SENTINEL)
        return "있음"

    return Item("flaky", "가끔 늦는 항목", run)


def test_a_first_timeout_is_named_by_its_step_and_run_once_more() -> None:
    """사내 리뷰 202610200720 — 페이더가 두 배포 이어 첫 판에만 `TimeoutError` 였고 어느 기다림인지
    남지 않았다. 단계 이름을 남기고, 쓰지 않는 항목은 한 번 더 돈다."""
    runs: list[str] = []
    screen = _FakeScreen()

    [outcome] = screens.run_items(
        screen, [_flaky(runs, failures=1)], allow_writes=False, deadline=NO_DEADLINE
    )

    assert runs == ["run", "run"]
    assert screen.settled == 2
    assert outcome.result == "있음 · 첫 판 TimeoutError(층 고르기) 뒤 다시 돎"
    assert outcome.recorded


def test_a_second_timeout_stays_unrecorded_and_other_failures_are_not_retried() -> None:
    runs: list[str] = []
    [twice] = screens.run_items(
        _FakeScreen(), [_flaky(runs, failures=2)], allow_writes=False, deadline=NO_DEADLINE
    )
    assert runs == ["run", "run"]
    assert twice.result == (
        "미기록 — TimeoutError(층 고르기) · 첫 판 TimeoutError(층 고르기) 뒤 다시 돎"
    )
    assert not twice.recorded

    runs.clear()
    [other] = screens.run_items(
        _FakeScreen(),
        [_flaky(runs, failures=1, error=ValueError)],
        allow_writes=False,
        deadline=NO_DEADLINE,
    )
    assert runs == ["run"]
    assert other.result == "미기록 — ValueError(층 고르기)"
    assert SENTINEL not in twice.result + other.result


def test_a_writing_item_is_not_run_twice() -> None:
    runs: list[str] = []
    item = _flaky(runs, failures=1)
    writing = Item(item.key, item.title, item.run, writes=True)

    [outcome] = screens.run_items(_FakeScreen(), [writing], allow_writes=True, deadline=NO_DEADLINE)

    assert runs == ["run"]
    assert outcome.result == "미기록 — TimeoutError(층 고르기)"


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
            def __init__(self, port: int, *, start_timeout: float, console: Any = None) -> None:
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


@pytest.mark.parametrize("io_encoding", ["utf-8", "cp949"])
def test_a_broken_app_import_exits_2_with_only_its_type(io_encoding: str) -> None:
    """사내 Windows(한국어 로캘)의 파이프는 cp949 라 「—」를 못 쓴다 — 자식의 `PYTHONIOENCODING` 을
    cp949 로 두어 사내 에이전트 셸이 부르는 꼴을 흉내 낸다. 이 갈래는 `main()` 의 UTF-8 전환보다
    먼저 찍으므로 거기서 바꾸지 않으면 트레이스백과 종료 1 로 끝나고 원래 예외 문구까지 실린다."""
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
        env={**os.environ, "PYTHONIOENCODING": io_encoding},
    )

    assert completed.returncode == 2
    assert "앱 모듈을 불러오지 못했습니다 — ModuleNotFoundError" in completed.stdout
    assert "Traceback" not in completed.stderr
    assert "UnicodeEncodeError" not in completed.stderr
    assert "halted" not in completed.stdout + completed.stderr


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
    # 라벨의 오른쪽 이웃은 dock 의 첫 보이는 단추다 — Summary 의 ← 단추가 dock 맨 앞에 있고,
    # Detail 은 Summary 에서 그 뒤로 붙는다(`dock.appendChild(detail)`). 둘 다 `button` 이라 한
    # 선택자로 잡는다.
    assert '<span class="dock" data-slot="dock"><button type="button" class="back">' in html
    assert '<button type="button" class="btn detail"' in html
    assert "dock.appendChild(detail);" in _text(assets / "intro.js")
    assert '".dock > button"' in screens._SUMMARY_MARK_JS
    label = _text(COMPONENTS / "intro_summary.py")
    for name in ("capa-brand-word", "capa-brand-sub", "capa-brand-hint"):
        assert f'class="{name}"' in label, name
        assert f'".{name}"' in screens._LABEL_MARK_JS, name


def test_the_symbol_line_check_allows_only_a_layout_unit_of_overflow() -> None:
    """「라벨 글자」의 줄마다 판정은 글자 본래 폭(Range)이 칸 폭을 배치 단위(1/64px) 남짓까지만
    넘어도 된다고 본다. 잘리지 않은 줄은 두 폭이 같고, 브라우저는 1px 보다 작은 넘침에도 말줄임을
    그린다 — 몫이 0.5px 이면 `S.PKG CA…` 를 「다 보임」으로 읽는다. 둘째 줄로 내려가 라벨
    높이 밖에 있는 Summary 단추는 빠진 것이다(잘림이 아니다 — `intro_summary._LABEL_CSS` 의
    줄바꿈)."""
    assert 1 / 64 <= screens._RANGE_SLACK_PX < 0.05
    width = f"range.getBoundingClientRect().width <= r.width + {screens._RANGE_SLACK_PX}"
    for script in (screens._LABEL_MARK_JS, screens._SUMMARY_MARK_JS):
        assert width in script
    assert "hint.getBoundingClientRect().top >= l.bottom - 1" in screens._LABEL_MARK_JS
    assert "flex-wrap: wrap;" in _text(COMPONENTS / "intro_summary.py")


def _narrow_rows(**changes: dict[str, str]) -> list[dict[str, Any]]:
    """좁은 폭 라벨 측정값 — 기본은 폭마다 두 줄 다 보이고 Summary 단추는 빠짐.
    `w236={"word": "cut"}` 처럼 그 폭의 칸만 바꾼다."""
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
    """「라벨 글자」는 사이드바 라벨(두 줄 + Summary 단추)과 Summary 머리 줄 라벨(두 줄)을 함께
    본다 — 한 곳이라도 잘리면 「잘림」. 결과는 고정 낱말과 px 뿐이다(런북 7장의 기대 글과 같은
    꼴)."""
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
        # 단추를 빼는 문턱 바로 위에서 단추가 반쯤 — 통째로 서거나 빠져야 한다.
        (_narrow_rows(w280={"hint": "cut"}), "잘림(좁은 폭 280px)"),
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


class _StaleUrlPage:
    """Playwright 의 `page.url` 은 이동 사건으로 고쳐 두는 값이라 `time.sleep` 동안에는 옛 주소에
    머문다. 페이지에 물으면(`evaluate`) 지금 경로가 온다."""

    def __init__(self, start: str, target: str) -> None:
        self.url = f"http://127.0.0.1:8559{start}"
        self.location = start
        self.clicks = 0
        self._target = target
        link = SimpleNamespace(is_visible=lambda: True, click=self._click)
        self._locator = SimpleNamespace(first=link)

    def _click(self) -> None:
        self.clicks += 1
        self.location = self._target

    def locator(self, selector: str) -> Any:
        return self._locator

    def evaluate(self, script: str, arg: object = None) -> Any:
        if script == screens._PATH_JS:
            return self.location
        if script == screens._RUNNING_JS:
            return False
        if script == screens._PAGE_TABS_JS:
            # 탭 줄이 아직 없다 — 자리 비우기(`make_tab_room`)가 아무것도 하지 않는다.
            return None
        raise AssertionError(script)


@pytest.mark.parametrize(
    ("start", "target", "go"),
    [
        ("/", "/equipment_availability", lambda s: s.open_page("equipment_availability")),
        ("/equipment_availability", "/", lambda s: s.open_home()),
    ],
)
def test_moving_between_pages_reads_the_path_from_the_page_not_the_stale_url(
    monkeypatch: pytest.MonkeyPatch, start: str, target: str, go: Any
) -> None:
    """옛 `page.url` 로 도착을 보면 링크마다 10초씩 기다려 다시 눌렀다(사내 리뷰 202610182227 —
    링크마다 약 72초). 한 번 누르고, 기다림은 회차가 끝났는지 보는 몫뿐이다."""
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    page = _StaleUrlPage(start, target)

    go(Screen(page, "http://127.0.0.1:8559/"))

    assert page.clicks == 1
    assert page.url.endswith(start)
    assert sum(slept) < 2


def test_a_cut_at_the_default_and_a_narrow_width_names_both() -> None:
    assert screens._label_verdict(False, ((236,), 0)) == "잘림(기본 폭 · 좁은 폭 236px)"
    assert screens._label_verdict(False, ((), 0)) == "잘림"


def test_the_narrow_label_widths_straddle_the_label_css_thresholds() -> None:
    """좁은 폭 셋은 라벨 CSS 의 문턱을 겨눈다 — 머리칸(사이드바 − 55px)이 280 에서는 Summary 단추를
    감추는 문턱(222px) 바로 위라 단추가 다 서거나 줄바꿈으로만 빠지고, 236 에서는 글꼴을 줄이는
    문턱(190px) 바로 아래다. 마지막은 끌어 줄 수 있는 가장 좁은 폭이다. 잰 뒤 사이드바 원래 폭을
    되돌린다."""
    from capa_simulation.components import intro_summary

    css = intro_summary._label_css("light")
    hide, shrink = (
        int(width) for width in re.findall(r"@container capa-sidebar-head \(width < (\d+)px\)", css)
    )
    head = 55
    first, second, last = screens.LABEL_NARROW_WIDTHS_PX
    assert hide <= first - head < hide + 10
    assert shrink - 10 <= second - head < shrink
    assert last == screens.SIDEBAR_NARROW_WIDTH_PX
    script = screens._LABEL_NARROW_JS
    assert screens._WHOLE_LINE_JS in script
    # 칸 상자끼리만 견주면 라벨 테두리 안쪽에서 잘린 「g」 꼬리를 못 본다(사내 리뷰 202610182227) —
    # 「다 보임」 과 좁은 폭의 「말줄임」 모두 글자 잉크가 자르는 선 안에 들어야 한다.
    assert "&& inked(el);" in screens._WHOLE_LINE_JS
    assert "inside && inked(el)" in script
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


def test_the_drawer_floorless_count_reads_what_the_editor_hangs_on_a_chip() -> None:
    """서랍 안 층 미정 수는 칩의 `__entry.list` 호기마다 `floorless`·`group` 으로 센다 — 편집기가
    그 이름으로 달고, 서버가 그 뜻(이 층이 아닌 층 미정 · Main 설비 묶음)으로 보낸다."""
    editor = _text(COMPONENTS / "space_layout_editor_assets" / "editor.js")
    assert "chip.__entry = { lead, list }" in editor
    assert "floorless: Boolean(raw.floorless)" in editor
    service = _text(PROJECT_ROOT / "src" / "capa_simulation" / "services" / "space_layout_edit.py")
    assert '"floorless": bool(row["_floorless"]),' in service
    assert '"group": str(parent) if _present(parent) else None,' in service
    for name in ("chip.__entry", "unit.floorless", "unit.group", "groups"):
        assert name in screens._TRAY_JS
    # 칩 하나가 묶음 하나다 — 묶음 칩 수가 표에서 그 묶음들이 차지하는 대수다.
    assert "const list = item.group ? members(item).filter(keep) : [item]" in editor


def test_the_drawer_head_splits_the_drawer_into_this_floor_and_floorless_units() -> None:
    """`202610231430` 리뷰 사외 요청 2 — 서랍이 층 미정 호기까지 실어 서랍 N 이 표 N 보다 큰
    것이 네 배포 이어 `ng` 였다. 머리가 서랍 N 을 이 층 몫과 층 미정으로 갈라 찍고 이 층 몫을 표와
    견준다."""
    line = screens.summarize_drawer_counts(6, 160.0, 549, 389, 0, 0)
    assert line == (
        "미배치 있는 층 6개 · 연 층 표 160대 · 서랍 549대 = 이 층 160대 + 층 미정 389대 · "
        "이 층 표와 같음"
    )
    # 층 미정이 없으면 예전처럼 서랍 N 이 표 N 과 같다.
    assert screens.summarize_drawer_counts(1, 4.0, 4, 0, 0, 0).endswith(
        "서랍 4대 = 이 층 4대 + 층 미정 0대 · 이 층 표와 같음"
    )
    assert screens.summarize_drawer_counts(2, 3.0, 8, 2, 0, 0).endswith("이 층 표와 다름")
    # 칩에서 층 미정 · 묶음을 셀 수 없으면 견주지 않는다.
    assert screens.summarize_drawer_counts(2, 3.0, 8, None, None, None) == (
        "미배치 있는 층 2개 · 연 층 표 3대 · 서랍 8대(층 미정 못 셈)"
    )
    assert screens.summarize_drawer_counts(2, 3.0, 8, 2, 4, None).endswith("(층 미정 못 셈)")


def test_the_drawer_head_explains_a_difference_only_by_the_bundle_surplus() -> None:
    """묶음 모듈은 서랍이 한 대씩, 표는 설비지분(묶음 하나가 1대)으로 센다(2026-10-26 리뷰 — 차이가
    얼마든 「다름(묶음 모듈 m대)」 으로 넘기면 줄이 스스로 검산되지 않는다). 묶음 g개 · 모듈 m대면
    넘침이 m − g 대라 `이 층 a = 표 N + 넘침` 이 설 때만 묶음으로 설명된다 — 그 식을 줄에 적는다."""
    # 4모듈 묶음 하나 — 이 층 6대 = 표 3대 + 넘침 3대.
    assert screens.summarize_drawer_counts(2, 3.0, 8, 2, 4, 1).endswith(
        "서랍 8대 = 이 층 6대 + 층 미정 2대 · 이 층 표와 다름 · 묶음 1개 모듈 4대 · "
        "이 층 6대 = 표 3대 + 묶음 넘침 3대"
    )
    # 묶음 둘이면 넘침은 2대뿐이라 표 3대를 설명하지 못한다(묶음 밖 차이 1대).
    assert screens.summarize_drawer_counts(2, 3.0, 8, 2, 4, 2).endswith(
        "이 층 표와 다름 · 묶음 2개 모듈 4대 · 묶음으로 설명 안 됨"
    )
    # 지분 합인 표 N 의 소수도 그대로 견준다 — 묶음 넘침은 정수라 설명되지 않는다.
    assert screens.summarize_drawer_counts(1, 2.5, 5, 2, 1, 1).endswith("묶음으로 설명 안 됨")


@pytest.mark.parametrize(
    ("path", "label"),
    [
        ("src/capa_simulation/components/equipment_import_dialog.py", 'st.selectbox("등록할 표"'),
        ("src/capa_simulation/components/equipment_data_workspace.py", '_TARGETS = ("설비 마스터"'),
        ("src/capa_simulation/components/shortening_progress_panel.py", '"진척 비교",'),
        ("src/capa_simulation/components/shortening_progress_panel.py", '"비교 안 함"'),
        ("src/capa_simulation/components/required_shortening_panel.py", '"목표 확보율",'),
        # 가용설비 현황 탭 라벨은 사이드바(설비 시나리오 줄을 세우는 탭)와 함께 `navigation` 에
        # 있다(2026-10-24 두 탭 개편 — RawData 는 설비 마스터 탭).
        (
            "src/capa_simulation/navigation.py",
            'EQUIPMENT_MASTER_TAB = ":material/table_rows: 설비 마스터"',
        ),
        # 필요 단축 일정은 별도 화면이다(2026-10-18) — 사이드바 링크 주소로 간다(`SHORTENING_PAGE`).
        ("src/capa_simulation/navigation.py", '"app_pages/required_shortening.py",'),
        ("app_pages/space_status.py", '"층 바로 가기",'),
        ("app_pages/space_status.py", '"배치 편집",'),
        ("src/capa_simulation/components/space_floor_list.py", '"미배치대수":'),
        # 층 사용 칸 항목(`space_floor_state`)이 찾는 칸·스위치 이름.
        ("src/capa_simulation/components/space_floor_list.py", '"사용 편집",'),
        ("src/capa_simulation/components/space_floor_list.py", '_USE_COLUMN = "사용"'),
        ("src/capa_simulation/components/space_floor_list.py", '_REASON_COLUMN = "사유"'),
        ("src/capa_simulation/components/space_floor_list.py", '_UNITS_COLUMN = "호기"'),
        # 사유 칸이 직접 입력 칸이라야 `사유 직접 입력` 이다(Glide 글 편집기 — textarea).
        (
            "src/capa_simulation/components/space_floor_list.py",
            "_REASON_COLUMN: st.column_config.TextColumn(",
        ),
        ("src/capa_simulation/components/space_floor_list.py", '"비활성 층 {len(inactive)}개"'),
        ("src/capa_simulation/components/space_layout_editor_assets/editor.js", "'is-inactive'"),
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
        screens.CONSTRAINT_PAGE,
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
    "equipment_scenario_line",
    "space_floor_state",
    "page_tabs",
    "equipment_moves",
    "constraint_sim",
    "space_scenario_row",
    "equipment_grid",
    "space_shortening",
    # 사내 리뷰 202610231430 사외 요청 4 — 7-18 B 대행이 못 센 칸을 옮긴 넷(다음 배포 몫).
    "upeh_rows",
    "entry_sections",
    "upeh_help",
    "space_zone_fields",
]


def test_this_deploys_items_follow_the_five_pilot_items_and_do_not_write() -> None:
    keys = [item.key for item in ITEMS]

    assert keys[:5] == ["toolbar", "symbol", "bulk_import_target", "progress_box", "space_drawer"]
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
        ("설비 시나리오", "설비 시나리오"),
        (" 설비 시나리오 ", "설비 시나리오"),
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


def test_the_equipment_scenario_line_contract_matches_the_app() -> None:
    """설비 시나리오 줄 항목이 읽는 key·이름·팝업 구획은 앱 값과 같다(스크립트는 앱 모듈을 부르지
    않고 값만 옮긴다)."""
    from capa_simulation.components import equipment_scenario_status as status

    assert screens.EQUIPMENT_SCENARIO_FIELD_KEY == status.EQUIPMENT_SCENARIO_FIELD_KEY
    assert screens.EQUIPMENT_SCENARIO_ROW_NAME == status.EQUIPMENT_SCENARIO_FIELD_LABEL
    assert screens.EQUIPMENT_SCENARIO_DIALOG_TITLE == status.EQUIPMENT_SCENARIO_DIALOG_TITLE
    assert screens.EQUIPMENT_SCENARIO_DIALOG_MODES == (status.LOAD_MODE, status.SAVE_MODE)
    assert 'slug="equipment_scenario"' in _text(COMPONENTS / "equipment_scenario_status.py")
    assert screens.panel_row_name(status.EQUIPMENT_SCENARIO_FIELD_LABEL) == "설비 시나리오"
    assert screens.REVISION_RADIO_LABEL == "리비전"
    assert '"리비전",' in _text(COMPONENTS / "equipment_scenario_status.py")


def test_the_equipment_scenario_value_reads_the_label_without_the_icon_text() -> None:
    """값 칸 단추에는 머티리얼 아이콘이 있다 — 실제 Chrome 의 단추 `innerText` 는
    「account_tree\\n\\n운영 일정 · r3」 이었다(FG 차례 실행). 스크립트는 라벨 칸만 읽고, 그래도
    단추 전체 글이 오면 마지막 줄로 꼴을 본다(거짓 「꼴 다름」 을 내지 않는다)."""
    assert "stMarkdownContainer" in screens._EQUIPMENT_ROW_JS
    assert screens.equipment_field_text("account_tree\n\n운영 일정 · r3") == "운영 일정 · r3"
    assert screens.equipment_field_text("운영 일정 · r3") == "운영 일정 · r3"
    assert screens.equipment_field_text(None) == ""
    row = {"name": "설비 시나리오", "badge": "공식 v1", "value": "account_tree\n\n운영 일정 · r3"}
    line = screens.summarize_equipment_scenario_line(row, None, None, False)
    assert "꼴 같음" in line and "account_tree" not in line


def test_the_equipment_scenario_line_summary_names_only_shapes_and_badge_kinds() -> None:
    row = {"name": "설비 시나리오", "badge": "공식 v3", "value": "운영 일정 · r12"}
    facts = {"modes": ["불러오기", "저장"], "selected": "불러오기", "revisions": 4}

    line = screens.summarize_equipment_scenario_line(row, "설비 시나리오", facts, True)

    assert line == (
        "「설비 시나리오」 줄 있음 · 값 칸 「이름 · rN」 꼴 같음 · 배지 「공식 v…」 · 팝업 제목 "
        "「설비 시나리오」 같음 · 구획 「불러오기」·「저장」 있음 · 리비전 4개 · Esc 닫힘"
    )
    # 시나리오 이름·번호는 값이라 찍지 않는다.
    assert "운영 일정" not in line and "r12" not in line and "v3" not in line
    assert "|" not in line
    assert screens.summarize_equipment_scenario_line(None, None, None, False) == (
        "「설비 시나리오」 줄 없음"
    )
    odd = screens.summarize_equipment_scenario_line(
        {"name": "설비 시나리오", "badge": "", "value": "운영 일정"}, None, None, False
    )
    assert (
        odd == "「설비 시나리오」 줄 있음 · 값 칸 「이름 · rN」 꼴 다름 · 배지 없음 · 팝업 안 열림"
    )


def test_the_space_scenario_row_summary_names_the_pickable_load_only_row() -> None:
    """설비 시나리오 2단계 S4 — Space 사이드바 줄은 고를 수 있는 줄(「(고정)」 없음)이고 팝업은
    「불러오기」 구획 하나다. 이름·번호는 찍지 않는다."""
    row = {
        "name": "설비 시나리오",
        "badge": "가정 배치",
        "value": "셋업 실무 · r4",
        "disabled": False,
    }
    facts = {"modes": [], "load": True, "revisions": 3}

    line = screens.summarize_space_scenario_row(row, "설비 시나리오", facts, True)

    assert line == (
        "Space 「설비 시나리오」 줄 있음 · 고를 수 있음 · 「(고정)」 없음 · 배지 「가정 배치」 · "
        "팝업 제목 「설비 시나리오」 같음 · 「불러오기」 만 · 리비전 3개 · Esc 닫힘"
    )
    assert "셋업 실무" not in line and "r4" not in line
    fixed = screens.summarize_space_scenario_row(
        {**row, "value": "운영 일정 · r3 (고정)", "disabled": True, "badge": "공식 v2"},
        None,
        None,
        False,
    )
    assert fixed == (
        "Space 「설비 시나리오」 줄 있음 · 고를 수 없음(잠김) · 「(고정)」 있음 · "
        "배지 「공식 v…」 · 팝업 안 열림"
    )
    two = screens.summarize_space_scenario_row(
        row, "설비 시나리오", {"modes": ["불러오기", "저장"], "load": True, "revisions": 3}, True
    )
    assert "구획 다름" in two
    assert screens.summarize_space_scenario_row(None, None, None, False) == (
        "Space 「설비 시나리오」 줄 없음"
    )


def test_the_space_scenario_row_contract_matches_the_app() -> None:
    """Space 의 팝업에는 「저장」 구획이 없다(저장은 편집본을 세우는 화면 둘만) — 스크립트가 찾는
    「불러오기」 단추 글과 「(고정)」 꼬리가 앱 값과 같다."""
    from capa_simulation.components import equipment_scenario_status as status

    assert status.SAVE_PAGES and "space_status.py" not in status.SAVE_PAGES
    assert screens.SPACE_SCENARIO_LOAD_BUTTON == status.LOAD_MODE
    assert screens.SPACE_SCENARIO_FIXED_TAIL == status.FIXED_LOCK_REASON
    assert '"불러오기",\n        icon=":material/download:"' in _text(
        COMPONENTS / "equipment_scenario_status.py"
    )


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("app.py", 'st.sidebar.container(key="home_navigation")'),
        ("app_pages/home.py", 'PROCESS_FIELD_LABEL = "공정 필터"'),
        ("app_pages/home.py", 'PROCESS_FIELD_KEY = "dashboard_bottleneck_process_dialog_open"'),
        ("app_pages/home.py", "@st.dialog(\n    PROCESS_FIELD_LABEL,"),
        ("app_pages/home.py", "st.caption(THRESHOLD_POINTER)"),
        ("src/capa_simulation/home_state.py", 'HOME_MAIN_TAB = ":material/dashboard: Main"'),
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


def test_every_equipment_badge_kind_is_known_to_the_screen_check() -> None:
    """사이드바 설비 시나리오 배지가 낼 수 있는 모든 글이 화면 확인의 배지 종류로 읽힌다 — 빠지면 그
    회차가 「배지 없음」 으로 찍힌다(설계 8-2 — S3 가 「가정 배치」 를 더했다)."""
    from capa_simulation.components.equipment_scenario_status import equipment_status_badge

    def badge(**state: object) -> str:
        session: Any = SimpleNamespace(
            scenario=object(),
            unmerged=False,
            is_official_pair=False,
            release_no=None,
            stale=False,
            latest_revision_no=None,
            layout_differs=False,
        )
        for name, value in state.items():
            setattr(session, name, value)
        text = equipment_status_badge(session, unsaved=bool(state.get("unsaved")))
        return text[text.index("[") + 1 : text.rindex("]")]

    shown = [
        badge(unsaved=True),
        badge(unmerged=True),
        badge(is_official_pair=True, release_no=3),
        badge(stale=True, latest_revision_no=7),
        badge(layout_differs=True),
        badge(),
    ]
    for text in shown:
        assert any(text.startswith(kind) for kind in screens.EQUIPMENT_STATUS_BADGES), text


def test_the_other_page_panels_follow_the_navigation_declarations() -> None:
    from capa_simulation.navigation import ALL_SPECS

    specs = {Path(spec.path).stem: spec for spec in ALL_SPECS}
    for page, _title, expected in screens.OTHER_PAGE_PANELS:
        spec = specs[page]
        # 주소 끝이 파일 이름이다(`open_page` 가 그 끝으로 찾는다). 탭으로 가르지 않는다 — Space
        # 현황만 보기 값(색 기준)으로 가르고, 화면 확인은 기본 색 기준(첫 값)에서 돈다.
        assert spec.url_path is None
        assert spec.condition_tabs is None or page == screens.SPACE_PAGE
        active = spec.condition_tabs.first if spec.condition_tabs is not None else None
        common = spec.reads_common_conditions_on(active)
        # 설비 시나리오 줄(`equipment_scenario`·`reads_equipment_scenario_on`)도 선언에서 읽는다 —
        # Space 현황은 설비 시나리오 줄 하나다(세션 시나리오를 고르는 줄 — 설비 시나리오 2단계 S3).
        rows = tuple(
            name
            for name, shown in (
                ("시나리오", common and spec.reads_scenario),
                ("조회기간", common and spec.reads_period),
                ("설비 시나리오", spec.reads_equipment_scenario_on(active)),
            )
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


# ------------------------------------------------------------------ RawData 설비 마스터 머리(39열)


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
        SCENARIO_MEMO_COLUMN,
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
        SCENARIO_MEMO_COLUMN,
    )
    assert len(EQUIPMENT_COLUMNS) == 39
    assert set(screens.EQUIPMENT_NEW_HEADERS) <= set(EQUIPMENT_COLUMNS)
    assert screens.EQUIPMENT_DROPPED_HEADER in OBSOLETE_EQUIPMENT_COLUMNS
    assert screens.EQUIPMENT_DROPPED_HEADER not in EQUIPMENT_COLUMNS


def test_the_equipment_grid_contract_matches_the_app() -> None:
    """설비 마스터 표 확인(`bulk_import_target`·`equipment_headers`·`equipment_grid`)이 옮겨 둔
    값 — 마운트 key·단추 글·칸 묶음·머리 칸 수·시나리오 칸 수·넣어 볼 칸 — 이 앱과 같다."""
    from capa_simulation.components import equipment_master_grid as emg
    from capa_simulation.components import equipment_master_tab as tab
    from capa_simulation.components.equipment_import_dialog import IMPORT_DIALOG_TITLE
    from capa_simulation.services import equipment_grid as eg
    from capa_simulation.services.equipment_contract import (
        DATE_COLUMNS,
        EQUIPMENT_COLUMNS,
        SCENARIO_SCHEDULE_COLUMNS,
    )

    assert screens.EQUIPMENT_GRID_KEY == emg.GRID_KEY
    assert screens.EQUIPMENT_LOADER_KEY == emg.LOADER_KEY
    assert screens.BULK_IMPORT_TITLE == IMPORT_DIALOG_TITLE
    js = _text(COMPONENTS / "equipment_master_grid_assets" / "grid.js")
    assert f"'{screens.BULK_IMPORT_BUTTON}'" in js
    assert "'전체 ' + total.toLocaleString() + '대 불러오기'" in js
    assert len(eg.COLUMN_SETS) == screens.GRID_COLUMN_SETS
    assert any(item.label == screens.GRID_ALL_COLUMNS_SET for item in eg.COLUMN_SETS)
    assert len(EQUIPMENT_COLUMNS) == screens.GRID_ALL_COLUMNS
    assert len(SCENARIO_SCHEDULE_COLUMNS) == screens.GRID_SCENARIO_HEADERS
    assert screens.GRID_TEXT_COLUMN in EQUIPMENT_COLUMNS
    assert screens.GRID_TEXT_COLUMN not in SCENARIO_SCHEDULE_COLUMNS
    assert screens.GRID_DATE_COLUMN in DATE_COLUMNS
    assert eg.GRID_COLUMNS[eg.NAME_INDEX].name == "설비명" and eg.NAME_INDEX == 5
    assert tab.SIDE_CHANGES == screens.EQUIPMENT_SIDE_CHANGES
    assert tab.SIDE_KEY == screens.EQUIPMENT_SIDE_KEY
    assert tab.DISCARD_POPOVER_KEY == screens.EQUIPMENT_DISCARD_KEY
    master = _text(COMPONENTS / "equipment_master_tab.py")
    assert f'"{screens.GRID_DISCARD_CONFIRM}"' in master
    # 「전체 39칸」 머리 차례(설비명 맨 앞 + 나머지 계약 차례) → 계약 자리 번호.
    headers = ["설비명", *[name for name in EQUIPMENT_COLUMNS if name != "설비명"]]
    for name in (screens.GRID_TEXT_COLUMN, screens.GRID_DATE_COLUMN, "Area Code", "Model"):
        assert screens._contract_index(headers, name) == EQUIPMENT_COLUMNS.index(name)


def test_the_equipment_grid_summary_is_counts_and_marks_only() -> None:
    assert screens.summarize_equipment_grid(5, 12, True, True, True) == (
        "칸 묶음 5/5 · 줄 있음 · 고친 칸 표지 있음 · 틀린 날짜 오류 있음 · 모두 버리기 됨"
    )
    assert screens.summarize_equipment_grid(5, 3, True, None, True) == (
        "칸 묶음 5/5 · 줄 있음 · 고친 칸 표지 있음 · 틀린 날짜 칸 잠김 · 모두 버리기 됨"
    )
    assert screens.summarize_equipment_grid(5, 0, None, None, False) == (
        "칸 묶음 5/5 · 줄 없음 · 모두 버리기 안 됨"
    )


def test_the_equipment_header_summary_counts_and_names_only_missing_contract_names() -> None:
    every = dict.fromkeys(screens.EQUIPMENT_NEW_HEADERS, True)

    assert screens.summarize_equipment_headers(every, False) == (
        "새 이름 8/8 있음 · 「설비가동현황」 없음"
    )
    partial = {**every, "반입실적": False, "Qual실적": False}
    line = screens.summarize_equipment_headers(partial, True)
    assert line == "새 이름 6/8 있음(없음: 반입실적, Qual실적) · 「설비가동현황」 있음"
    # 결과 표 칸을 깨는 글자가 없다.
    assert "|" not in line
    assert screens.summarize_equipment_headers({}, False).startswith("새 이름 0/8 있음(없음: ")


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
        "Static Capa 머리 + 4 · 실행 관리 머리 + 8 · Dynamic Capa 머리 + 1 — "
        "정한 차례·수와 같음 · 상자 제목 한 줄 · 잘림 없음"
    )
    # 차례가 바뀌거나 하나가 빠지거나 하위 수가 다르면 「다름」, 줄바꿈·말줄임은 그 상자 이름만
    # 적는다.
    swapped = [every[1], every[0], _box("dynamic_capa", "Dynamic Capa", 2)]
    swapped[0] = {**swapped[0], "lines": 2}
    line = screens.summarize_sidebar_groups(swapped)
    assert line == (
        "실행 관리 머리 + 8 · Static Capa 머리 + 4 · Dynamic Capa 머리 + 2 — "
        "정한 차례·수와 다름 · 줄바꿈: 실행 관리"
    )
    missing = screens.summarize_sidebar_groups([every[0], {**every[2], "clipped": True}])
    assert missing.endswith("정한 차례·수와 다름(없음: 실행 관리) · 잘림: Dynamic Capa")
    # 문단 안에서는 넘치지 않아도 조상 칸이 글자를 자르면 잘림이다.
    cut = screens.summarize_sidebar_groups([every[0], {**every[1], "cut": True}, every[2]])
    assert cut.endswith("정한 차례·수와 같음 · 잘림: 실행 관리")
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
        == "좁은 폭 200px 줄바꿈: 실행 관리"
    )
    # 넘쳤는데 말줄임이 없거나(규칙이 빠짐) 조상 칸이 자르면 결함이다. 보이는 링크도 센다.
    bare = [every[0], {**every[1], "clipped": True}, {**every[2], "cut": True}]
    assert (
        screens.summarize_sidebar_narrow({"width": 200, "boxes": bare, "links_cut": 2})
        == "좁은 폭 200px 말줄임 없이 잘림: 실행 관리, Dynamic Capa"
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
    assert '"배치대수":' in _text(COMPONENTS / "space_floor_list.py")


def test_the_space_fader_summary_carries_counts_only() -> None:
    line = screens.summarize_space_fader(1289.0, 37, True, True)
    assert line == (
        "배치 최다 층 1289대 · +1개월에 class 바뀐 상자 37개 · 놓은 뒤 범례 기준일 바뀜 · "
        "「오늘」 돌아옴"
    )
    assert "|" not in line
    assert "범례 없음" in screens.summarize_space_fader(1.5, 0, None, False)
    assert "안 돌아옴" in screens.summarize_space_fader(1.5, 0, False, False)
    assert screens.summarize_space_fader(3.0, 0, True, True, pressed=2).endswith(
        "「오늘」 돌아옴 · PageUp 2번(첫 키가 오늘로 돌아감)"
    )


def test_the_space_fader_item_clicks_today_only_when_the_button_is_on() -> None:
    """페이더가 오늘이면 「오늘」 단추가 꺼진다 — 꺼진 단추를 누르면 30초 기다린 `TimeoutError`
    가 결과를 가렸다(사내 리뷰 202610200720 페이더 첫 판). 항목은 켜졌을 때만 누르고 단계마다
    이름을 둔다."""
    editor = _text(COMPONENTS / "space_layout_editor_assets" / "editor.js")
    assert "faderToday.disabled = isToday" in editor
    source = inspect.getsource(screens.check_space_fader)
    assert "if today.is_enabled():" in source
    assert source.count("screen.step(") >= 6


def _unit_classes(month: int) -> list[str]:
    """한 달 옮기면 앞의 두 상자만 판정 class 가 붙는다(합성 — 셈만 본다)."""
    units = ["sle-item sle-unit"] * 3
    if month:
        units[:2] = ["sle-item sle-unit is-pending"] * 2
    return units


class _FaderScreen(_FakeScreen):
    """`space_fader` 항목이 만지는 것(층 목록 표·층 고르기·페이더·「오늘」 단추·범례)만 가진 화면.
    PageUp 한 번에 페이더가 한 달 옮겨 가되, 앞의 `lost` 번은 늦은 그림이 오늘로 되돌린다(층을
    옮긴 회차의 새 epoch). 「오늘」 단추는 페이더가 오늘이면 꺼져 있고, 꺼진 단추를 누르면
    Playwright 처럼 켜지기를 기다리다 `TimeoutError` 로 끝난다. `fail_at` 단계에서 범례를 읽으면
    예외가 난다. `floor_open` 이면 앞 항목이 연 층이 세션에 남은 채 페이지가 열린다 — 층 상세에는
    층 목록 표가 없고, 경로 줄 `S.PKG FAB 전체` 는 보조 단추이며 누르면 FAB 로 돌아간다."""

    def __init__(
        self, *, lost: int = 0, fail_at: str | None = None, floor_open: bool = False
    ) -> None:
        super().__init__()
        self.lost = lost
        self.fail_at = fail_at
        self.floor_open = floor_open
        self.month = 0
        self.presses = 0
        self.clicks = 0
        self.crumb_clicks = 0
        self.chosen: list[str] = []
        fader = SimpleNamespace(
            wait_for=lambda **kwargs: None,
            evaluate=self._fader_evaluate,
            focus=lambda: None,
            press=self._press,
        )
        today = SimpleNamespace(is_enabled=lambda: self.month != 0, click=self._click)
        crumb = SimpleNamespace(
            wait_for=lambda **kwargs: None,
            get_attribute=self._crumb_attribute,
            click=self._crumb_click,
        )
        found = {
            ".sle-fader-input": fader,
            ".sle-fader-today": today,
            f".st-key-{screens.SPACE_FAB_CRUMB_KEY} button": crumb,
        }
        self.page = SimpleNamespace(locator=lambda selector: SimpleNamespace(first=found[selector]))

    def _crumb_attribute(self, name: str) -> str:
        assert name == "data-testid"
        return "stBaseButton-secondary" if self.floor_open else "stBaseButton-primary"

    def _crumb_click(self) -> None:
        self.crumb_clicks += 1
        self.floor_open = False

    def _fader_evaluate(self, script: str) -> Any:
        if script == screens._FADER_TODAY_JS:
            return self.month == 0
        assert script == screens._UNIT_CLASSES_JS
        return _unit_classes(self.month)

    def _press(self, key: str) -> None:
        assert key == "PageUp"
        self.presses += 1
        if self.presses > self.lost:
            self.month += 1

    def _click(self) -> None:
        if self.month == 0:
            raise TimeoutError("꺼진 단추가 켜지기를 기다렸다")
        self.clicks += 1
        self.month = 0

    def open_page(self, href_suffix: str) -> None:
        assert href_suffix == screens.SPACE_PAGE

    def grid_with_column(self, header: str, *, timeout: float = 30.0) -> tuple[Any, int]:
        assert header == "배치대수"
        if self.floor_open:
            # 층 상세에는 층 목록 표가 없다 — 실제 화면은 30초 기다린 뒤 이 예외다.
            raise TimeoutError("기다린 화면이 서지 않았다")
        return "층 목록", 2

    def column_index(self, grid: Any, header: str) -> int | None:
        return {"동": 0, "층": 1}.get(header)

    def grid_rows(self, grid: Any, columns: Sequence[int]) -> list[list[str | None]]:
        assert list(columns) == [0, 1, 2]
        return [["A동", "1F", "3"], ["A동", "2F", "1,289"], ["B동", "1F", "0"]]

    def choose_by_typing(self, label: str, text: str) -> None:
        self.chosen.append(text)

    def selectbox_value(self, label: str) -> str | None:
        return self.chosen[-1] if self.chosen else None

    def main_text(self) -> str:
        if self.fail_at is not None and self.current_step == self.fail_at:
            raise RuntimeError(SENTINEL)
        return f"PKG 3대 기준 2026-{10 + self.month}-21"

    def wait_idle(self, timeout: float = 90.0) -> None:
        pass

    def poll(
        self,
        read: Callable[[], Any],
        *,
        timeout: float,
        accept: Callable[[Any], bool] = bool,
        every: float = 0.25,
    ) -> Any:
        # 가짜 화면은 누른 즉시 선다 — 기다리지 않고 한 번 읽는다.
        return read()


FADER_SUMMARY_HEAD = "배치 최다 층 1289대 · +1개월에 class 바뀐 상자 "


@pytest.mark.parametrize(
    ("lost", "presses", "tail"),
    [
        # 첫 키가 먹으면 한 번만 누르고 PageUp 꼬리는 없다.
        (0, 1, ""),
        # 층을 옮긴 회차의 늦은 그림이 첫 키를 오늘로 되돌리면 한 번 더 누르고 그 사실을 적는다.
        (1, 2, " · PageUp 2번(첫 키가 오늘로 돌아감)"),
    ],
)
def test_the_space_fader_item_presses_page_up_again_only_when_the_first_key_is_lost(
    lost: int, presses: int, tail: str
) -> None:
    """두 배포 이어 페이더 첫 판이 `TimeoutError` 였다(사내 리뷰 202610200720) — 첫 PageUp 이
    오늘로 되돌려진 탓이다. 항목은 페이더가 오늘에 남았을 때만 다시 누르고, 옮겨 간 페이더는
    「오늘」 단추(켜져 있다)로 되돌린다."""
    screen = _FaderScreen(lost=lost)

    result = screens.check_space_fader(screen)

    assert result == f"{FADER_SUMMARY_HEAD}2개 · 놓은 뒤 범례 기준일 바뀜 · 「오늘」 돌아옴{tail}"
    assert (screen.presses, screen.clicks, screen.month) == (presses, 1, 0)
    assert screen.chosen == ["A동 2F"]


def test_the_space_fader_item_does_not_click_the_disabled_today_button() -> None:
    """두 키 모두 오늘로 되돌려지면 페이더는 오늘에 남아 「오늘」 단추가 꺼져 있다 — 누르면 켜지기를
    30초 기다린 `TimeoutError` 가 위 결과를 가린다. 세 번째 키는 누르지 않고, 단추도 누르지 않고
    결과를 낸다."""
    screen = _FaderScreen(lost=2)

    result = screens.check_space_fader(screen)

    assert result == (
        f"{FADER_SUMMARY_HEAD}0개 · 놓은 뒤 범례 기준일 안 바뀜 · 「오늘」 돌아옴"
        " · PageUp 2번(첫 키가 오늘로 돌아감)"
    )
    assert (screen.presses, screen.clicks, screen.month) == (2, 0, 0)


def test_the_space_fader_item_names_the_failed_step_after_returning_to_today() -> None:
    """범례를 기다리다 예외가 나도 `finally` 가 「오늘」로 되돌린다. 되돌리기가 단계 이름을
    「「오늘」」로 바꾸므로, 미기록 줄이 멈춘 단계(범례)를 말하게 되돌려 둔다. `TimeoutError` 가
    아니라 다시 돌지 않고, 예외 문구는 옮기지 않는다."""
    screen = _FaderScreen(fail_at="범례")
    item = next(item for item in ITEMS if item.key == "space_fader")

    [outcome] = screens.run_items(screen, [item], allow_writes=False, deadline=NO_DEADLINE)

    assert outcome.result == "미기록 — RuntimeError(범례)"
    assert SENTINEL not in outcome.result
    assert (screen.presses, screen.clicks, screen.month) == (1, 1, 0)


@pytest.mark.parametrize(("floor_open", "crumb_clicks"), [(False, 0), (True, 1)])
def test_the_space_fader_item_starts_from_the_fab_even_when_a_floor_was_left_open(
    floor_open: bool, crumb_clicks: int
) -> None:
    """연 층은 세션 키라 `space_drawer` 가 연 층이 페이지를 다시 열어도 남는다 — 페이더 항목이
    층 목록 표를 기다리다 첫 판 · 다시 돈 판 모두 `TimeoutError(층 목록)` 였다(사내 리뷰
    202610200720 발견 1 — 사외 흉내 저장소에서 재현). 항목은 경로 줄 `S.PKG FAB 전체` 가 보조
    단추일 때만 눌러 FAB 에서 시작하고, 첫 판에 기록한다."""
    screen = _FaderScreen(floor_open=floor_open)
    item = next(item for item in ITEMS if item.key == "space_fader")

    [outcome] = screens.run_items(screen, [item], allow_writes=False, deadline=NO_DEADLINE)

    assert outcome.result == f"{FADER_SUMMARY_HEAD}2개 · 놓은 뒤 범례 기준일 바뀜 · 「오늘」 돌아옴"
    assert (screen.crumb_clicks, screen.floor_open) == (crumb_clicks, False)
    assert screen.chosen == ["A동 2F"]


def test_both_space_items_open_the_fab_overview_the_app_draws() -> None:
    """두 Space 항목이 같은 길로 FAB 전체를 연다. 경로 줄 첫 칸은 그 키의 단추이고, FAB 전체면 주
    단추 · 층을 열었으면 보조 단추이며, 누르면 세션의 연 층을 지운다(Streamlit 단추의 `data-testid`
    는 `stBaseButton-<type>` 이다)."""
    for check in (screens.check_space_drawer, screens.check_space_fader):
        source = inspect.getsource(check)
        assert "screen.open_space_overview()" in source
        assert "screen.open_page(" not in source
    page = _text(PROJECT_ROOT / "app_pages" / "space_status.py")
    assert f'key="{screens.SPACE_FAB_CRUMB_KEY}",' in page
    assert 'type="primary" if selected is None else "secondary",' in page
    assert "on_click=_show_fab_overview," in page
    assert '"stBaseButton-primary"' in inspect.getsource(screens.Screen.open_space_overview)


# ------------------------------------------- 가용설비 현황 두 탭 개편(`equipment_moves`)


def test_the_equipment_moves_contract_matches_the_app() -> None:
    """스크립트는 앱 모듈을 부르지 않고 값만 옮긴다 — 탭 이름·단추 key·팝업 제목·지표·전환이 앱과
    같은지 여기서 본다."""
    from capa_simulation.components import equipment_scenario_management as section
    from capa_simulation.components import equipment_settings_dialog as settings
    from capa_simulation.navigation import (
        EQUIPMENT_MASTER_TAB,
        EQUIPMENT_SUMMARY_TAB,
        EQUIPMENT_SUMMARY_TAB_KEY,
        EQUIPMENT_SUMMARY_TABS,
        EQUIPMENT_TAB_KEY,
    )

    assert EQUIPMENT_MASTER_TAB.endswith(f" {screens.EQUIPMENT_MASTER_TAB}")
    assert EQUIPMENT_SUMMARY_TAB.endswith(f" {screens.EQUIPMENT_SUMMARY_TAB}")
    assert [label.split(" ", 1)[1] for label in EQUIPMENT_SUMMARY_TABS] == list(
        screens.EQUIPMENT_SUMMARY_TABS
    )
    assert screens.EQUIPMENT_SETTINGS_BUTTON_KEY == settings.SETTINGS_BUTTON_KEY
    assert screens.EQUIPMENT_SETTINGS_TITLE == settings.SETTINGS_DIALOG_TITLE
    shortening = _text(PROJECT_ROOT / "app_pages" / "required_shortening.py")
    assert f'QUAL_CALCULATOR_BUTTON_KEY = "{screens.QUAL_CALCULATOR_BUTTON_KEY}"' in shortening
    assert f'"{screens.QUAL_CALCULATOR_TITLE}", width="large"' in shortening
    calculator_source = _text(COMPONENTS / "qual_deadline_calculator.py")
    for label in screens.QUAL_CALCULATOR_KPIS:
        assert f'"{label}",' in calculator_source
    assert screens.SCENARIO_KIND_KEY == section.SCENARIO_KIND_KEY
    assert screens.SCENARIO_KINDS == section.SCENARIO_KINDS
    assert screens.EQUIPMENT_TAB_KEY == EQUIPMENT_TAB_KEY
    assert screens.EQUIPMENT_SUMMARY_TAB_KEY == EQUIPMENT_SUMMARY_TAB_KEY
    assert f'"{screens.EQUIPMENT_SCENARIO_TABLE_ANCHOR}":' in _text(
        COMPONENTS / "equipment_scenario_management.py"
    )
    cutoff_source = _text(COMPONENTS / "cutoff_management.py")
    assert f'"{screens.CUTOFF_EDITOR_ANCHOR}"' in cutoff_source


def test_the_equipment_moves_summary_is_fixed_words_and_counts() -> None:
    outer = ["table_rows 설비 마스터", "insights Summary"]
    summary = ["dashboard Main", "compare_arrows Static 대비 일정"]
    anywhere = [*outer, "입력", "직접 편집", "저장 이력", "설비 마스터", "비가동 일정", *summary]
    text = screens.summarize_equipment_moves(
        screens.EquipmentTabNames(outer, summary, anywhere),
        ("설정", True, True),
        ("Qual 마감 계산기", 4, True),
        (True, True),
    )
    assert text == (
        "탭 2/2 · Summary 안쪽 2/2 · 옛 탭 0곳 · 설정 — 팝업 제목 「설정」 같음 · Cut-off 표 "
        "있음 · Esc 닫힘 · 필요 단축 일정 — 팝업 제목 「Qual 마감 계산기」 같음 · 지표 4/4 · "
        "Esc 닫힘 · 시나리오 관리 — 설비 시나리오 구획 표 있음 · 전환 되돌림"
    )
    old_tabs = ["table_rows RawData", "tune Preference"]
    old = screens.summarize_equipment_moves(
        screens.EquipmentTabNames(old_tabs, [], old_tabs), None, None, None
    )
    assert old.startswith("탭 0/2 · Summary 안쪽 0/2 · 옛 탭 2곳")
    assert "「설정」 단추 없음" in old and "「관리할 시나리오」 전환 없음" in old


def test_the_equipment_moves_outer_count_ignores_the_inner_editor_tab_of_the_same_name() -> None:
    """다른 탭 묶음의 같은 이름(개편 D 전 ① 안 「직접 편집」 의 편집표 탭 「설비 마스터」 같은 것)은
    바깥 탭이 아니다 — 바깥 ① 이 없어지거나 이름이 바뀌어도 그 탭으로 「탭 2/2」 가 나오면 안 된다
    (2026-10-25 리뷰). 셈은 바깥 탭 묶음(`st-key-equipment_active_tab`)·Summary 안쪽 탭 묶음의 제 탭
    목록에서만 한다."""
    inner_editor = ["입력", "직접 편집", "저장 이력", "설비 마스터", "비가동 일정"]
    summary = ["dashboard Main", "compare_arrows Static 대비 일정"]
    text = screens.summarize_equipment_moves(
        screens.EquipmentTabNames(
            ["table_rows 설비 대장", "insights Summary"],
            summary,
            ["table_rows 설비 대장", "insights Summary", *inner_editor, *summary],
        ),
        None,
        None,
        None,
    )
    assert text.startswith("탭 1/2 · Summary 안쪽 2/2 · 옛 탭 0곳")
    # 안쪽 탭 묶음의 「Main」 만 Summary 안쪽으로 센다 — 다른 자리의 같은 이름은 들지 않는다.
    stray = screens.summarize_equipment_moves(
        screens.EquipmentTabNames(["table_rows 설비 마스터", "insights Summary"], [], summary),
        None,
        None,
        None,
    )
    assert stray.startswith("탭 2/2 · Summary 안쪽 0/2")
    script = inspect.getsource(screens.check_equipment_moves)
    assert "_KEYED_TAB_NAMES_JS, EQUIPMENT_TAB_KEY" in script
    assert "_KEYED_TAB_NAMES_JS, EQUIPMENT_SUMMARY_TAB_KEY" in script


def test_the_deploy_chapter_names_what_the_app_and_the_script_show() -> None:
    """런북 7장(앞 몫 7-19 · 이번 몫 7-23)이 가리키는 단추 글·기대 꼴·A 표·항목 수가 앱·스크립트와
    맞는다(2026-10-25 리뷰). 사내 에이전트는 런북 글 그대로 찾는다.

    - 7-19 B 손 확인의 공정 Capa 상세 다음 화면 단추는 앱 글 그대로다(없는 「… 에서 보기」 가
      아니다).
    - 7-18 머리 「7-18 항목의 새 자리」 표의 `equipment_headers` 줄은 39열 기대(`새 이름 8/8`)로
      읽는다(7-18 은 하지 않지만 다른 절이 그 표를 부른다).
    - 개편 A 가 바꾼 Space 층 상세 표 위 줄 「… 의 설비 마스터 n줄」 이 그 표에 있다.
    - 7-23 A 표의 키가 `--list`(`ITEMS`) 앞머리 차례와 같고, 런북 압축본 기대와 TODO 「다음 배포 —
      사내 이관 확인」 줄의 항목 수가 그 표의 수와 같다. 그 배포 뒤에 더한 항목은 TODO 「다음 배포 —
      화면 확인 항목」 줄이 키와 `ITEMS` 전체 수를 적는다(7장은 그 배포의 기록이다). 앞머리만 같아도
      통과하므로 7장을 고치지 않은 다음 배포는 빌더가 막는다(`build_deploy_package.
      runbook_screen_count_mismatch` — 아래 시험이 빌더의 셈과 `ITEMS` 를 묶는다).
    """
    runbook = _text(PROJECT_ROOT / "docs" / "internal_update_runbook.md")
    chapter = runbook.split("\n## 7. ", 1)[1].split("\n## 8. ", 1)[0]
    previous = chapter.split("### 7-19. ", 1)[1].split("### 7-20. ", 1)[0]
    draft = chapter.split("### 7-23. ", 1)[1].split("### 7-5. ", 1)[0]
    view = _text(COMPONENTS / "process_capa_view.py")
    assert 'f"가용 불일치 {kpis.mismatch_months}개월 — 가용설비 현황"' in view
    assert '"이 달 가용 불일치 — 가용설비 현황"' in view
    assert "`가용 불일치 n개월 — 가용설비 현황`" in previous
    assert "`이 달 가용 불일치 — 가용설비 현황`" in previous
    assert "에서 보기」 다음 화면 단추" not in previous

    places = chapter.split("**7-18 항목의 새 자리**", 1)[1].split("**DB 에 쓰지 않는다**", 1)[0]
    headers_row = next(line for line in places.splitlines() if "| A `equipment_headers` |" in line)
    count = len(screens.EQUIPMENT_NEW_HEADERS)
    assert f"`새 이름 {count}/{count} 있음 · 「설비가동현황」 없음 · 머리 " in headers_row
    assert 'f"**{_markdown_text(str(picked_unit))}** 의 설비 마스터 {len(picked_rows)}줄"' in _text(
        PROJECT_ROOT / "app_pages" / "space_status.py"
    )
    assert "「… 의 **설비 마스터** n줄」" in places

    a_table = draft.split("#### A. ", 1)[1].split("#### B. ", 1)[0]
    table_keys = re.findall(r"^\| `([a-z_]+)` \| ([^|]+) \|", a_table, re.MULTILINE)
    # 7장은 그 배포의 기록이다 — 표는 `ITEMS` 의 앞머리와 같고, 그 뒤에 더한 항목은 다음 배포
    # 7장이 싣기 전까지 TODO 「다음 배포」 줄이 키와 전체 수를 적는다.
    recorded = len(table_keys)
    assert [(key, title.strip()) for key, title in table_keys] == [
        (item.key, item.title) for item in screens.ITEMS[:recorded]
    ]
    assert f"`A {recorded} = 기록 {recorded} + 미기록 0 + 안함 0`" in draft
    todo = _text(PROJECT_ROOT / "docs" / "TODO.md")
    next_deploy = todo.split("**다음 배포 — 사내 이관 확인**", 1)[1].split("\n- [", 1)[0]
    assert f"`A {recorded}`" in next_deploy
    added = screens.ITEMS[recorded:]
    if added:
        later = todo.split("**다음 배포 — 화면 확인 항목", 1)[1].split("\n- [", 1)[0]
        items = len(screens.ITEMS)
        assert f"`A {items} = 기록 {items} + 미기록 0 + 안함 0`" in later
        for item in added:
            assert f"`{item.key}`" in later


def test_the_builder_counts_the_same_items_as_the_script_lists() -> None:
    """빌더는 앱 모듈을 불러오지 않으려고 `ITEMS` 선언을 글로 센다 — 그 셈이 `--list` 와 같아야 7장
    화면 확인 수 대조가 선다."""
    import build_deploy_package

    assert build_deploy_package.screen_item_count(PROJECT_ROOT) == len(ITEMS)


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


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            (30, 30, 0, 0, True, True),
            "사용 칸 있음 · 목록 30줄(사용 30) · 비활성 층 0개 · 회색 블록 0개 · "
            "편집 칸 사용·사유·호기 있음 · 사유 직접 입력",
        ),
        (
            (23, 23, 7, 7, True, False),
            "사용 칸 있음 · 목록 23줄(사용 23) · 비활성 층 7개 · 회색 블록 7개 · "
            "편집 칸 사용·사유·호기 있음 · 사유 직접 입력 아님",
        ),
        (
            (30, 30, 0, 0, True, None),
            "사용 칸 있음 · 목록 30줄(사용 30) · 비활성 층 0개 · 회색 블록 0개 · "
            "편집 칸 사용·사유·호기 있음 · 사유 칸 열지 못함",
        ),
        (
            (29, 29, 1, 0, False),
            "사용 칸 있음 · 목록 29줄(사용 29) · 비활성 층 1개 · 회색 블록 0 ≠ 비활성 1 · "
            "편집 칸 없음",
        ),
        (
            (30, 30, None, 0, None),
            "사용 칸 있음 · 목록 30줄(사용 30) · 비활성 층 0개 · 회색 블록 0개 · 스위치 없음",
        ),
        ((None, 0, None, 0, None), "사용 칸 없음"),
    ],
)
def test_the_space_floor_state_summary_carries_counts_only(
    args: tuple[int | None, int, int | None, int, bool | None, bool | None], expected: str
) -> None:
    assert screens.summarize_space_floor_state(*args) == expected


def test_the_page_tab_constants_match_the_app() -> None:
    from capa_simulation.page_tabs_state import MAX_TABS, PAGE_TABS_COMPONENT_KEY

    assert screens.PAGE_TABS_KEY == PAGE_TABS_COMPONENT_KEY
    assert screens.PAGE_TABS_MAX == MAX_TABS


@pytest.mark.parametrize(
    ("opened", "back_home", "closed", "verdict"),
    [
        (
            [
                {"active": False, "closable": False, "pinned": True},
                {"active": True, "closable": True},
            ],
            True,
            [{"active": True, "closable": False, "pinned": True}],
            "연 뒤 탭 2 · HOME 고정 있음 · 탭으로 HOME 옮김 · 닫은 뒤 탭 1 — 정한 동작과 같음",
        ),
        (
            [{"active": True, "closable": True}],
            False,
            [{"active": True}],
            "연 뒤 탭 1 · HOME 고정 없음 · 탭으로 HOME 못 옮김 · 닫은 뒤 탭 1 — 정한 동작과 다름",
        ),
    ],
)
def test_the_page_tab_line_counts_only(
    opened: list[dict[str, bool]], back_home: bool, closed: list[dict[str, bool]], verdict: str
) -> None:
    assert screens.summarize_page_tabs(opened, back_home, closed) == verdict


# ------------------------------------------------------------------ 제약 시뮬레이션


def test_the_constraint_simulation_contract_matches_the_app() -> None:
    """스크립트는 앱 모듈을 부르지 않고 key 값만 옮긴다 — 앱과 같은지 여기서 본다. 두 그림은 칸
    선택을 켠 그림이라 앱의 터치 스크롤 막이 묶음(`CELL_SELECT_CHART_KEYS`)에 든다."""
    import capa_simulation.constraint_simulation_state as state
    from capa_simulation.components import constraint_simulation_view as view
    from capa_simulation.navigation import CONSTRAINT_SIMULATION
    from capa_simulation.process_detail_state import PROCESS_DETAIL_PROCESS_KEY

    assert CONSTRAINT_SIMULATION.path == f"app_pages/{screens.CONSTRAINT_PAGE}.py"
    assert screens.CONSTRAINT_KEYS == {
        "kpi": view.KPI_ROW_KEY,
        "chart": state.CONSTRAINT_CHART_KEY,
        "sheet": state.CONSTRAINT_SHEET_KEY,
        "steps": view.STEPS_CARD_KEY,
        "schedule": view.SCHEDULE_CARD_KEY,
        "absent": state.CONSTRAINT_ABSENT_KEY,
        "process": state.CONSTRAINT_PROCESS_KEY,
        "detailProcess": PROCESS_DETAIL_PROCESS_KEY,
    }
    detail = _text(PROJECT_ROOT / "app_pages" / "process_capa_detail.py")
    assert f'label="{screens.CONSTRAINT_LINK_LABEL}"' in detail
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
    assert {"CONSTRAINT_CHART_KEY", "CONSTRAINT_SHEET_KEY"} <= set(members)
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == state.__name__
        and {alias.name for alias in node.names} >= {"CONSTRAINT_CHART_KEY", "CONSTRAINT_SHEET_KEY"}
        for node in tree.body
    )


@pytest.mark.parametrize(
    ("link", "before", "after", "same", "expected"),
    [
        (
            {"found": True, "disabled": False},
            {"kpis": 4, "chart": True, "sheet": True, "steps": 5, "schedule": 3, "month": "27.05"},
            {"month": "27.01"},
            True,
            "링크 켜짐 · 공정 같음 · KPI 4개 · 그림 있음 · 표 있음 · 계산 5단계 · 개조 일정 3줄 · "
            "칸 누름 뒤 고른 달 바뀜",
        ),
        (
            {"found": True, "disabled": True},
            {"absent": True},
            None,
            None,
            "링크 꺼짐(까닭) · 설비 일정 없음(까닭 카드)",
        ),
        (
            None,
            {"kpis": 4, "chart": True, "sheet": False, "steps": 5, "schedule": 0, "month": "27.05"},
            None,
            None,
            "링크 없음 · KPI 4개 · 그림 있음 · 표 없음 · 계산 5단계 · 개조 일정 0줄 · "
            "칸 누름 뒤 고른 달 못 누름",
        ),
    ],
)
def test_the_constraint_simulation_summary_counts_without_screen_text(
    link: dict[str, Any] | None,
    before: dict[str, Any],
    after: dict[str, Any] | None,
    same: bool | None,
    expected: str,
) -> None:
    line = screens.summarize_constraint_simulation(link, before, after, same)
    assert line == expected
    # 달·공정 글자는 찍지 않는다.
    assert "27." not in line


# 브라우저 없이 두 JS 를 돌리는 가짜 문서 — 고르는 글(선택자)마다 요소를 돌려준다. 요소는
# `innerText`·`value`·속성과 제 아래 선택자 표를 갖는다. 모르는 선택자는 없음(null·빈 목록)이다.
_FAKE_DOM_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const element = (spec) => spec && {
  innerText: spec.innerText ?? '',
  textContent: spec.innerText ?? '',
  value: spec.value,
  getAttribute: (name) => (spec.attrs || {})[name] ?? null,
  hasAttribute: (name) => name in (spec.attrs || {}),
  getBoundingClientRect: () => ({left: 0, top: 0, width: 100, height: 100}),
  querySelector: (selector) => element((spec.one || {})[selector]) || null,
  querySelectorAll: (selector) => ((spec.all || {})[selector] || []).map(element),
};
globalThis.document = element(input.document);
globalThis.getComputedStyle = () => ({pointerEvents: 'auto'});
const run = (source, arg) => eval(source)(arg);
process.stdout.write(JSON.stringify({
  link: run(input.linkScript, input.linkArg),
  page: run(input.pageScript, input.pageArg),
}));
"""


def _run_constraint_scripts(document: dict[str, Any]) -> dict[str, Any]:
    runtime = shutil.which("node") or shutil.which("bun")
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 화면 확인 JS 시험을 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    payload = {
        "document": document,
        "linkScript": screens._CONSTRAINT_LINK_JS,
        "linkArg": {**screens.CONSTRAINT_KEYS, "label": screens.CONSTRAINT_LINK_LABEL},
        "pageScript": screens._CONSTRAINT_JS,
        "pageArg": screens.CONSTRAINT_KEYS,
    }
    completed = subprocess.run(
        [runtime, "-e", _FAKE_DOM_RUNNER],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result: dict[str, Any] = json.loads(completed.stdout)
    return result


@pytest.mark.parametrize("box_text", ["", "공정"])
def test_the_constraint_check_reads_the_chosen_process_from_the_combobox_value(
    box_text: str,
) -> None:
    """Streamlit 1.63 selectbox 는 고른 값을 콤보 상자 `<input>` 의 `value` 에만 둔다 — 상자 글은
    카드가 접혔으면 빈 글자, 폈으면 라벨 「공정」 뿐이다. 그 글로 견주면 링크가 켜진 정상 화면이
    늘 「공정 다름」 이었다(2026-10-25 리뷰 — 사본 앱에서 두 상자 모두 `innerText` "" · 값
    'Wafer Saw'). 두 JS 를 가짜 문서로 돌려 값끼리 견주는지 본다."""
    keys = screens.CONSTRAINT_KEYS

    def box(value: str) -> dict[str, Any]:
        return {"innerText": box_text, "one": {"input": {"value": value}}}

    link = {"innerText": screens.CONSTRAINT_LINK_LABEL, "attrs": {}}
    document: dict[str, dict[str, Any]] = {
        "all": {
            '[data-testid="stMain"] a': [link],
            '.st-key-process_detail_kpis [data-testid="stMetric"]': [{}] * 4,
        },
        "one": {
            f".st-key-{keys['detailProcess']}": box("Wafer Saw"),
            f".st-key-{keys['process']}": box("Wafer Saw"),
        },
    }
    result = _run_constraint_scripts(document)
    assert result["link"] == {
        "found": True,
        "disabled": False,
        "ready": True,
        "process": "Wafer Saw",
    }
    assert result["page"]["process"] == "Wafer Saw"
    assert screens.constraint_process_matches(result["link"], result["page"]) is True

    # 제약 화면이 다른 공정으로 열렸으면 다름이다.
    document["one"][f".st-key-{keys['process']}"] = box("Mold")
    other = _run_constraint_scripts(document)
    assert screens.constraint_process_matches(other["link"], other["page"]) is False


def test_the_constraint_process_match_is_none_without_a_followed_link() -> None:
    page = {"process": "Wafer Saw"}
    assert screens.constraint_process_matches(None, page) is None
    assert screens.constraint_process_matches({"found": False}, page) is None
    assert screens.constraint_process_matches({"found": True, "disabled": True}, page) is None
    # 값을 읽지 못하면 같다고 짐작하지 않는다.
    assert (
        screens.constraint_process_matches(
            {"found": True, "disabled": False, "process": None}, {"process": None}
        )
        is False
    )


# ------------------------------------------------------------------ Space 필요 단축 보기


@pytest.mark.parametrize("class_name", ["sle-short-badges", "sle-pinned", "sle-fader"])
def test_the_space_shortening_selectors_exist_in_the_editor(class_name: str) -> None:
    html = _text(COMPONENTS / "space_layout_editor_assets" / "editor.html")
    assert f'class="{class_name}' in html


def test_the_space_shortening_item_reads_what_the_app_draws() -> None:
    """항목이 읽는 것 — 색 기준 라디오 칸·값(navigation 과 같은 글자), FAB 블록 풍선의 단축 줄, 층
    목록 표 `단축 호기` 칸, 배지 `data-pick`·모듈 상자 `is-module`, 고정 줄."""
    from capa_simulation import navigation
    from capa_simulation.components import space_floor_list

    assert screens.SPACE_COLOR_BASIS_KEY == navigation.SPACE_COLOR_BASIS_KEY
    assert screens.SPACE_SHORTENING_BASIS == navigation.SPACE_SHORTENING_BASIS
    assert screens.SPACE_DEFAULT_BASIS == navigation.SPACE_DEFAULT_BASIS
    page = _text(PROJECT_ROOT / "app_pages" / "space_status.py")
    assert f'SPACE_CARD_NAME = "{screens.SPACE_CARD_NAME}"' in page
    assert '"단축 호기":' in _text(COMPONENTS / "space_floor_list.py")
    assert "단축 호기" in space_floor_list._LAYER_COLUMNS
    editor = _text(COMPONENTS / "space_layout_editor_assets" / "editor.js")
    assert "node.dataset.pick = ids[0]" in editor
    assert "group.classList.toggle('is-module'" in editor
    assert "stats.occupancy, stats.short" in editor
    layer = _text(
        PROJECT_ROOT / "src" / "capa_simulation" / "services" / "space_shortening_layer.py"
    )
    assert 'f"단축 {count.units}대 · 최대 −{count.max_days}일"' in layer
    source = inspect.getsource(screens.check_space_shortening)
    assert "_choose_color_basis(screen, SPACE_DEFAULT_BASIS)" in source
    assert source.index("finally:") < source.index(
        "_choose_color_basis(screen, SPACE_DEFAULT_BASIS)"
    )


def test_the_space_shortening_summary_carries_counts_only() -> None:
    line = screens.summarize_space_shortening(
        6, {"badges": 4, "modules": 1, "pinned": True, "fader": False}, True
    )
    assert line == (
        "단축 줄 블록 6개 · 최다 층 배지 4개(모듈 묶음 1) · 고정 줄 있음 · 페이더 숨음 · "
        "되돌린 뒤 페이더 있음"
    )
    assert "|" not in line
    assert screens.summarize_space_shortening(0, None, True).startswith(
        "단축 줄 블록 0개 · 단축 층 없음"
    )
    assert screens.summarize_space_shortening(0, None, True, stopped="Cut-off 먼저 알림") == (
        "Cut-off 먼저 알림 · 되돌린 뒤 페이더 있음"
    )
    # 층을 열지 못해 보지 않은 것은 「있음」 으로 적지 않는다(리뷰 — 늘 같은 글이면 사내 리뷰에서
    # 정보가 되지 않는다).
    assert screens.summarize_space_shortening(0, None, None, stopped="Cut-off 먼저 알림") == (
        "Cut-off 먼저 알림 · 되돌린 뒤 페이더 확인 안 함(연 층 없음)"
    )
    assert screens.summarize_space_shortening(0, None, None).endswith(
        "되돌린 뒤 페이더 확인 안 함(연 층 없음)"
    )
    assert screens.summarize_space_shortening(0, None, False).endswith("되돌린 뒤 페이더 없음")


def test_the_space_shortening_item_checks_the_fader_on_a_floor_it_opened() -> None:
    """단축 층을 열지 못한 실행은 되돌린 뒤 배치 최다 층을 열어 페이더를 본다 — 열지 않은 채
    「페이더 있음」 으로 적지 않는다(옛 판은 `fader_back or floor is None` 이었다)."""
    source = inspect.getsource(screens.check_space_shortening)
    assert "or floor is None" not in source
    assert source.index("_choose_color_basis(screen, SPACE_DEFAULT_BASIS)") < source.index(
        "_open_most_placed_floor(screen)"
    )
    assert "summarize_space_shortening(blocks, floor, fader_back, stopped=stopped)" in source


# ------------------------------------------- 사내 리뷰 202610231430 사외 요청 4 — 대행이 못 센 칸


def test_the_console_goes_to_a_pipe_only_when_counted() -> None:
    """콘솔 출력은 세기(`console`)를 줄 때만 파이프 하나로 받는다 — 버퍼에 머물지 않게
    `PYTHONUNBUFFERED` 를 켠다. 주지 않으면 예전처럼 버린다. 파일은 어디에도 쓰지 않는다."""
    seen: dict[str, Any] = {}
    with _app(_FakeProcess(), seen=seen):
        pass
    assert seen["stdout"] is subprocess.DEVNULL and seen["stderr"] is subprocess.DEVNULL
    assert "PYTHONUNBUFFERED" not in seen["env"]

    clock = _Clock()
    given: dict[str, Any] = {}
    output = (
        f"\n  Warning: {screens.FRAGMENT_CALLBACK_WARNING} with a callback {SENTINEL}\n다른 줄\n"
    ).encode()

    class PipedProcess(_FakeProcess):
        def __init__(self) -> None:
            super().__init__()
            self.stdout = io.BytesIO(output)

    def popen(command: list[str], **options: Any) -> _FakeProcess:
        given.update(options)
        return PipedProcess()

    console = screens.ConsoleCounter(screens.CONSOLE_NEEDLES)
    app = StreamlitApp(
        8559,
        popen=popen,
        probe=lambda url: True,
        port_probe=lambda port: False,
        path_probe=lambda env, root: EXPECTED_PATHS,
        start_timeout=5,
        contain=False,
        clock=clock,
        sleep=clock.sleep,
        console=console,
    )
    with app:
        pass
    assert given["stdout"] is subprocess.PIPE and given["stderr"] is subprocess.STDOUT
    assert given["env"]["PYTHONUNBUFFERED"] == "1"
    # 끌 때 읽기 스레드가 파이프 끝까지 읽기를 기다린다.
    assert console.count(screens.FRAGMENT_CALLBACK_WARNING) == 1


def test_console_lines_are_counted_and_never_kept() -> None:
    console = screens.ConsoleCounter([screens.FRAGMENT_CALLBACK_WARNING])
    console.attach(
        io.BytesIO(
            (
                f"\n  Warning: {screens.FRAGMENT_CALLBACK_WARNING} with a callback {SENTINEL}\n"
                "다른 줄\n"
                f"{screens.FRAGMENT_CALLBACK_WARNING}\n"
            ).encode()
            + b"\xff\xfe broken\n"
        )
    )
    console.join(timeout=5)
    assert console.count(screens.FRAGMENT_CALLBACK_WARNING) == 2
    # 세기로 정하지 않은 글은 세지 않는다 — 줄 글은 어디에도 남지 않는다.
    assert console.count("다른 줄") is None
    assert SENTINEL not in repr(vars(console))
    # 파이프가 없으면(가짜 프로세스) 아무것도 않는다.
    idle = screens.ConsoleCounter(["x"])
    idle.attach(None)
    idle.join(timeout=1)
    assert idle.count("x") == 0


def test_settled_console_lines_waits_for_a_late_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """누른 뒤 경고 줄은 읽기 스레드를 거쳐 늦게 올 수 있다 — 늘 때까지 잠깐 기다린다."""
    monkeypatch.setattr(screens, "CONSOLE_SETTLE_SECONDS", 0.3)
    screen = Screen(SimpleNamespace(), "http://127.0.0.1:8559/")
    needle = screens.FRAGMENT_CALLBACK_WARNING
    assert screens.console_lines(screen, needle) is None
    assert screens.settled_console_lines(screen, needle, None) is None
    console = screens.ConsoleCounter([needle])
    screen.console = console
    assert screens.console_lines(screen, needle) == 0
    assert screens.settled_console_lines(screen, needle, 0) == 0
    console.feed(needle.encode())
    assert screens.settled_console_lines(screen, needle, 0) == 1


def test_the_fragment_warning_prefix_is_what_streamlit_prints() -> None:
    import streamlit.delta_generator as generator

    source = inspect.getsource(generator._maybe_print_fragment_callback_warning)
    assert screens.FRAGMENT_CALLBACK_WARNING in source
    assert screens.FRAGMENT_CALLBACK_WARNING in screens.CONSOLE_NEEDLES


def test_the_check_hands_the_items_the_console_counter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """항목은 `screen.console` 로 콘솔 줄 수를 센다 — 앱을 띄울 때 준 그 세기다."""
    seen: list[Any] = []
    given: list[Any] = []

    def item(screen: Screen) -> str:
        seen.append(screen.console)
        return "있음"

    run = _Run(monkeypatch, [Item("log", "콘솔", item)])
    original = screens.StreamlitApp

    def app_with_console(port: int, *, start_timeout: float, console: Any = None) -> Any:
        given.append(console)
        return original(port, start_timeout=start_timeout, console=console)

    monkeypatch.setattr(screens, "StreamlitApp", app_with_console)

    assert screens.main(["--playwright-dir", str(tmp_path)]) == screens.EXIT_OK
    assert run.calls == ["start", "stop"]
    assert isinstance(given[0], screens.ConsoleCounter)
    assert seen == given


def test_the_upeh_rows_item_reads_what_the_app_draws() -> None:
    """가정 % 칸 라벨 · ① 끝 세 줄 라벨 · 조건 카드 key · 구간 없음 안내는 앱과 같다."""
    controls = _text(COMPONENTS / "upeh_assumption_controls.py")
    assert f'"{screens.UPEH_PERCENT_LABEL}",' in controls
    assert "걸 구간이 없습니다" in controls
    canvas = _text(COMPONENTS / "process_capa_canvas.py")
    assert 'prefix = f"UPEH {assumption.percent}%"' in canvas
    for name in screens.UPEH_ROW_NAMES:
        assert f'label=f"{{prefix}} · {name}",' in canvas
    from capa_simulation.services.upeh_assumption import PERCENT_DEFAULT
    from capa_simulation.sidebar_status import CONDITION_CARD_PREFIX

    assert screens.UPEH_DEFAULT_PERCENT == PERCENT_DEFAULT
    page = _text(PROJECT_ROOT / "app_pages" / "process_capa_detail.py")
    card = screens.PROCESS_DETAIL_CARD_KEY.removeprefix(CONDITION_CARD_PREFIX)
    assert f'CARD_NAME = "{card}"' in page


def test_the_upeh_rows_summary_carries_counts_only() -> None:
    rows = [f"UPEH 110% · {name}" for name in screens.UPEH_ROW_NAMES]
    assert screens.summarize_upeh_rows(rows, True, 0, False) == (
        "가정 줄 3 — 정한 세 줄과 같음 · 110 배지 있음 · 100 되돌린 뒤 가정 줄 0 · 배지 사라짐"
    )
    assert "정한 세 줄과 다름" in screens.summarize_upeh_rows(rows[:2], True, 0, False)
    assert screens.summarize_upeh_rows(rows, False, 3, True).endswith(
        "110 배지 없음 · 100 되돌린 뒤 가정 줄 3 · 배지 남음"
    )
    assert screens.summarize_upeh_rows(None, False, None, False).startswith("가정 구간 없음")


def test_the_entry_sections_item_reads_what_the_app_draws() -> None:
    """구획 칩 key · 칩 글자 차례 · HOME 그림 key · 이동 칸 수 · 근거 카드 링크 · 공정 상자는 앱과
    같다. 들어온 길마다 다시 펴는 구획(HOME → ①, 가용설비 현황 → ④)도 앱의 표와 같다."""
    from capa_simulation.components import availability_gap_panel as gap
    from capa_simulation.components.home_rendering import KEY_PROCESS_MONTHS_CHART_KEY
    from capa_simulation.components.process_capa_canvas import SECTION_IDS
    from capa_simulation.components.process_capa_view import ENTRY_SECTIONS, SECTION_LABELS
    from capa_simulation.process_detail_state import (
        FROM_GAP,
        FROM_HOME,
        HOME_CELL_LINK_FIELDS,
        PROCESS_DETAIL_SECTIONS_KEY,
    )
    from capa_simulation.sidebar_status import CONDITION_CARD_PREFIX

    assert screens.PROCESS_DETAIL_SECTIONS_KEY == PROCESS_DETAIL_SECTIONS_KEY
    assert screens.PROCESS_DETAIL_SECTION_LABELS == tuple(
        SECTION_LABELS[section] for section in SECTION_IDS
    )
    assert SECTION_IDS.index(ENTRY_SECTIONS[FROM_HOME]) == 0
    assert SECTION_IDS.index(ENTRY_SECTIONS[FROM_GAP]) == 3
    assert screens.HOME_KEY_PROCESS_CHART_KEY == KEY_PROCESS_MONTHS_CHART_KEY
    assert screens.HOME_CELL_LINK_FIELD_COUNT == len(HOME_CELL_LINK_FIELDS)
    assert HOME_CELL_LINK_FIELDS[0] == "process"
    assert screens.GAP_PROCESS_KEY == gap.PROCESS_FILTER_KEY
    assert screens.GAP_ALL_PROCESSES == gap._ALL_PROCESSES
    assert f'label="{screens.GAP_DETAIL_LINK_LABEL}",' in _text(
        COMPONENTS / "availability_gap_panel.py"
    )
    page = _text(PROJECT_ROOT / "app_pages" / "available_equipment_status.py")
    card = screens.EQUIPMENT_CARD_KEY.removeprefix(CONDITION_CARD_PREFIX)
    assert f'condition_card("설비 조회 조건", name="{card}")' in page


def test_the_home_cell_link_sits_at_the_end_of_the_key_process_customdata() -> None:
    """스크립트는 표적 막대 `customdata` 끝 일곱 칸의 첫 칸(공정)으로 누를 칸을 고른다 — 과거 실적
    칸은 그 자리가 비어 누르지 않는다."""
    import pandas as pd

    from capa_simulation.components.home_key_process_figures import (
        build_key_process_heatmap_figures,
    )
    from capa_simulation.services.securement_threshold import SecurementThresholds

    rates = pd.DataFrame(
        {
            "공정": [SENTINEL, SENTINEL],
            "생산계획년월": [202601, 202602],
            "확보율": [0.9, 1.2],
            "가용대수": [9.0, 12.0],
            "소요대수": [10.0, 10.0],
        }
    )
    _, months = build_key_process_heatmap_figures(
        securement_rate=rates,
        key_processes=[SENTINEL],
        month_labels=["26.01", "26.02"],
        thresholds=SecurementThresholds(default_secure=1.0, default_warning=0.95),
        past_month_labels={"26.01"},
    )
    custom = months.data[0].customdata
    at = -screens.HOME_CELL_LINK_FIELD_COUNT
    assert [row[at] for row in custom] == [None, SENTINEL]


def test_opened_section_text_names_only_the_entry_section() -> None:
    assert screens.opened_section_text([True, False, False, False], 0) == "① 공식 만 펼침"
    assert screens.opened_section_text([False, False, False, True], 3) == "④ 비가동 만 펼침"
    assert screens.opened_section_text([True, True, False, True], 3) == (
        "④ 비가동 펼침 · 다른 구획 2개도 펼침"
    )
    assert screens.opened_section_text([False, False, False, False], 0) == "① 공식 접힌 채"
    assert screens.opened_section_text(None, 0) == "구획 칩 없음"


def test_the_entry_sections_summary_carries_counts_only() -> None:
    line = screens.summarize_entry_sections(True, "① 공식 만 펼침", 0, "④ 비가동 만 펼침", True)
    assert line == (
        "구획 모두 접음 · HOME 칸 → ① 공식 만 펼침 · 콘솔 경고 0줄 · 근거 카드 링크 → ④ 비가동 만 "
        "펼침 · 구획 되돌림"
    )
    assert "콘솔 경고 못 셈" in screens.summarize_entry_sections(True, "x", None, "y", True)
    assert screens.summarize_entry_sections(False, "안 해 봄", None, "안 해 봄", False).startswith(
        "구획 못 접음"
    )


def test_the_entry_sections_item_restores_the_chips_even_when_a_path_fails() -> None:
    """칩을 접은 채 끝나면 같은 세션의 다른 항목(공정 Capa 상세 · 제약 시뮬레이션)이 접힌 그림을
    본다 — 되돌림은 `finally` 에 있다. 가용설비 현황의 공정 상자 · 전환도 `finally` 로 되돌린다."""
    source = inspect.getsource(screens.check_entry_sections)
    assert source.index("finally:") < source.index("_set_sections(screen, initial)")
    gap_source = inspect.getsource(screens._gap_link_entry)
    assert gap_source.index("finally:") < gap_source.index("_restore_gap_process(screen)")
    assert "_choose_segment(screen, key, option)" in gap_source.split("finally:")[-1]


class _EntryScreen:
    """`check_entry_sections` 의 두 길 가름만 보는 가짜 화면 — 연 페이지와 콘솔 줄 수만 든다."""

    def __init__(self, console: list[int] | None = None) -> None:
        self.where = ""
        self.opened: list[str] = []
        self.current_step: str | None = None
        self._console = iter(console or [])
        self.console = None if console is None else SimpleNamespace(count=self._count)

    def _count(self, needle: str) -> int:
        return next(self._console)

    def step(self, name: str) -> None:
        self.current_step = name

    def open_page(self, suffix: str) -> None:
        self.where = suffix
        self.opened.append(suffix)

    def path(self) -> str:
        return f"/{self.where}"

    def poll(self, read: Callable[[], Any], *, timeout: float, accept: Any = bool) -> Any:
        return read()


def _entry_paths(
    monkeypatch: pytest.MonkeyPatch,
    screen: _EntryScreen,
    *,
    home: Callable[[], str | None],
    gap: Callable[[], str],
) -> list[str]:
    """두 길을 가짜로 갈아 끼운다. 「구획」 칩 접기는 그 페이지가 열려 있을 때만 된다(아니면 칩이
    없다) — 돌려주는 목록에 칩을 접은 페이지를 차례로 적는다."""
    folded: list[str] = []

    def set_sections(_: object, wanted: object) -> bool:
        folded.append(screen.where)
        return screen.where == screens.PROCESS_DETAIL_PAGE

    def click_home(_: object) -> str | None:
        screen.where = "home"
        return home()

    def gap_entry(_: object) -> str:
        screen.where = screens.EQUIPMENT_PAGE
        return gap()

    monkeypatch.setattr(screens, "_wait_sections", lambda _: [True, False, False, False])
    monkeypatch.setattr(screens, "_set_sections", set_sections)
    monkeypatch.setattr(screens, "_click_home_cell", click_home)
    monkeypatch.setattr(screens, "_gap_link_entry", gap_entry)
    return folded


def _raise(exc: BaseException) -> Callable[[], Any]:
    def run() -> Any:
        raise exc

    return run


def test_a_home_path_that_stops_still_leaves_the_link_path_and_the_warning_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-10-26 리뷰 — ④ 길이 HOME 길에 묶여 HOME 칸 누름이 예외(1430 대행의 `TimeoutError`)로
    끝나면 대행 칸 셋(들어온 길 1 · 4 · 경고 0줄)을 한꺼번에 잃었다. 이제 HOME 길만 `멈춤(종류)` 로
    적고, 공정 Capa 상세를 다시 열어 구획을 접은 뒤 ④ 길을 돌며, 경고 줄은 그때까지를 센다."""
    screen = _EntryScreen(console=[2, 2])
    folded = _entry_paths(
        monkeypatch,
        screen,
        home=_raise(TimeoutError("화면이 멈추지 않았다")),
        gap=lambda: "④ 비가동 만 펼침",
    )

    line = screens.check_entry_sections(cast(Screen, screen))

    assert line == (
        "구획 모두 접음 · HOME 칸 → 멈춤(TimeoutError) · 콘솔 경고 0줄 · 근거 카드 링크 → "
        "④ 비가동 만 펼침 · 구획 되돌림"
    )
    assert "화면이 멈추지 않았다" not in line
    # 접기는 늘 공정 Capa 상세에서 — 처음 · HOME 길 뒤(다시 열고) · 끝 되돌림.
    assert folded == [screens.PROCESS_DETAIL_PAGE] * 3
    assert screen.opened.count(screens.PROCESS_DETAIL_PAGE) == 3


def test_a_home_path_without_a_cell_still_runs_the_link_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HOME 에 누를 칸이 없으면(결함 아님) 예전에는 ④ 칸이 「안 해 봄」 이었다 — 이제 ④ 길은
    돈다."""
    screen = _EntryScreen()
    _entry_paths(
        monkeypatch, screen, home=lambda: "주요공정 그림 없음", gap=lambda: "④ 비가동 만 펼침"
    )

    line = screens.check_entry_sections(cast(Screen, screen))

    assert (
        "HOME 칸 → 주요공정 그림 없음 · 콘솔 경고 못 셈 · 근거 카드 링크 → ④ 비가동 만 펼침" in line
    )


def test_a_link_path_that_stops_keeps_the_home_cell(monkeypatch: pytest.MonkeyPatch) -> None:
    screen = _EntryScreen(console=[0, 1])
    _entry_paths(monkeypatch, screen, home=lambda: None, gap=_raise(RuntimeError("공정 ZZ")))

    line = screens.check_entry_sections(cast(Screen, screen))

    assert line == (
        "구획 모두 접음 · HOME 칸 → ① 공식 만 펼침 · 콘솔 경고 1줄 · 근거 카드 링크 → "
        "멈춤(RuntimeError) · 구획 되돌림"
    )


def test_the_upeh_help_item_reads_what_the_app_draws() -> None:
    page = _text(PROJECT_ROOT / "app_pages" / "reference_data.py")
    help_line = next(line for line in page.splitlines() if line.strip().startswith('"RQ_UPEH": "'))
    for word in screens.UPEH_HELP_WORDS:
        assert word in help_line
    assert '":material/timer: UPEH",' in page
    assert "help=value_help," in _text(COMPONENTS / "month_editor.py")
    assert screens.REFERENCE_PAGE == "reference_data"
    assert '"app_pages/reference_data.py"' in _text(
        PROJECT_ROOT / "src" / "capa_simulation" / "navigation.py"
    )


def test_the_upeh_help_summary_never_carries_the_balloon_text() -> None:
    assert screens.summarize_upeh_help(None) == "UPEH 편집표 없음"
    assert screens.summarize_upeh_help("") == "월 칸 머리 풍선 없음"
    full = f"Main 행은 UPEH, MI 행은 ST(분) {SENTINEL}"
    assert screens.summarize_upeh_help(full) == "월 칸 머리 풍선 있음 · Main UPEH · MI ST(분) 밝힘"
    assert screens.summarize_upeh_help(f"UPEH {SENTINEL}") == (
        "월 칸 머리 풍선 있음 · 없는 낱말 1개"
    )
    assert SENTINEL not in screens.summarize_upeh_help(full)


def test_the_zone_selectors_exist_in_the_editor() -> None:
    """영역은 이름표(`sle-zone-tag`)만 눌림을 받는다 — 스크립트는 그것을 누른다. 선택 칸의 두 칸은
    영역에만 서는 칸이다."""
    editor = _text(COMPONENTS / "space_layout_editor_assets" / "editor.js")
    html = _text(COMPONENTS / "space_layout_editor_assets" / "editor.html")
    assert "el('g', { class: `sle-item sle-mark mark-${item.kind}` })" in editor
    assert "el('rect', { class: 'sle-zone-tag'" in editor
    assert "// 영역은 이름표로도 잡는다(안쪽은 비워 둔다) — 이름표만 눌림을 받게 한다." in editor
    for selector, name in zip(screens.ZONE_FIELDS, ("테두리", "글자 정렬"), strict=True):
        assert (
            '<label class="sle-field sle-zone-only"' in html
            and f'<span>{name}</span><select class="{selector.lstrip(".")}"' in html
        )


def test_the_zone_summary_carries_counts_only() -> None:
    assert screens.summarize_space_zone_fields(12, None, None, True) == "영역 없음(층 12개 봄)"
    assert screens.summarize_space_zone_fields(8, 4, [True, True], True) == (
        "영역 있는 층 4번째 · 테두리 칸 있음 · 글자 정렬 칸 있음 · 적용 안 함"
    )
    assert screens.summarize_space_zone_fields(8, 2, [True, False], False).endswith(
        "글자 정렬 칸 없음 · 적용 안 함 · 편집 못 끔"
    )
    assert "스위치 없음" in screens.summarize_space_zone_fields(8, 1, None, True)
    # 편집기가 그 층 그림으로 서지 않은 층은 「봄」 에 넣지 않고 따로 센다 — 「영역 없음」 이 결함
    # 아님으로 읽히는 것은 못 본 층이 없을 때뿐이다.
    assert screens.summarize_space_zone_fields(12, None, None, True, missed=2) == (
        "영역 없음(층 12개 봄 · 못 본 층 2개)"
    )


def test_the_zone_count_waits_for_the_editor_of_the_chosen_floor() -> None:
    """2026-10-26 리뷰 — 층마다 5초만 기다려 무거운 층의 영역을 놓치면 「영역 없음」 이 결함
    아님으로 읽혔다. 영역 수는 편집기 머리 이름(`.sle-title`)이 고른 층일 때만 내고, 고른 층 값도
    확인한다. 편집기는 보기 화면에도 그 머리에 층 이름(「동 층」)을 싣는다."""
    editor = _text(COMPONENTS / "space_layout_editor_assets" / "editor.js")
    html = _text(COMPONENTS / "space_layout_editor_assets" / "editor.html")
    view = _text(COMPONENTS / "space_layout_editor.py")
    assert "setText(q('.sle-title'), data.title || '')" in editor
    assert "const svg = q('.sle-canvas')" in editor
    assert '<span class="sle-title sle-edit-only"></span>' in html
    assert '"title": floor_label(floor),' in view
    from capa_simulation.services.fab_layout import floor_label

    assert floor_label(("C1", "1F")) == "C1 1F"
    source = inspect.getsource(screens.check_space_zone_fields)
    assert 'screen.selectbox_value("층 바로 가기") != label' in source
    assert "timeout=ZONE_FLOOR_DRAW_SECONDS" in source
    assert screens.ZONE_SELECTOR in screens._ZONE_COUNT_JS


def test_the_new_items_never_write() -> None:
    added = {"upeh_rows", "entry_sections", "upeh_help", "space_zone_fields"}
    assert added <= {item.key for item in ITEMS}
    assert not any(item.writes for item in ITEMS if item.key in added)
