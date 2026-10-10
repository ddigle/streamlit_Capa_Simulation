# Purpose: 사내 배포 화면 확인 스크립트의 경로 거절·사전 확인·앱 수명·항목·결과 꼴을 고정한다.

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest

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


def test_refused_paths_names_only_the_options(tmp_path: Path) -> None:
    args = _args(
        output=PROJECT_ROOT / "x.md",
        shots=tmp_path / "shots",
        playwright_dir=PROJECT_ROOT / "pw",
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


def test_a_real_closed_database_is_not_locked(tmp_path: Path) -> None:
    path = tmp_path / "x.duckdb"
    duckdb.connect(str(path)).close()

    assert screens.locked_databases([path]) == []


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


def test_a_locked_database_defers_when_the_process_scan_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _ready_for_preflight(monkeypatch)
    monkeypatch.setattr(screens, "running_app_count", lambda: None)
    monkeypatch.setattr(screens, "locked_databases", lambda paths: [Path("x.duckdb")])

    code = screens.main(["--playwright-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert code == screens.EXIT_DEFERRED
    assert captured.out.strip() == screens.DEFERRED_MESSAGE
    assert "DB 잠금만" in captured.err


def test_ignore_other_apps_skips_only_the_process_scan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def scan() -> int:
        raise AssertionError("--ignore-other-apps 인데 프로세스를 살폈다")

    monkeypatch.setattr(screens, "running_app_count", scan)
    monkeypatch.setattr(screens, "locked_databases", lambda paths: [])
    monkeypatch.setattr(screens, "port_in_use", lambda port: True)

    args = screens.parse_args(["--ignore-other-apps", "--port", "8559"])

    assert screens.preflight(args) == screens.EXIT_NOT_READY


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
        start_timeout=5,
        clock=clock,
        sleep=clock.sleep,
    )


def _stopped(process: _FakeProcess) -> bool:
    return ("signal" in process.calls or "terminate" in process.calls) and "wait" in process.calls


def test_the_app_is_started_on_its_own_port_with_the_callers_environment(
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
    assert seen["cwd"] == str(PROJECT_ROOT)
    assert seen["env"]["PYTHONPATH"] == "worktree-src"
    assert _stopped(process)


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


def test_write_items_are_skipped_without_permission_and_failures_do_not_stop_the_rest() -> None:
    called: list[str] = []
    screen = _FakeScreen()
    seen: list[Outcome] = []

    outcomes = screens.run_items(
        screen, _items(called), allow_writes=False, budget_seconds=600, on_outcome=seen.append
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

    screens.run_items(_FakeScreen(), _items(called), allow_writes=True, budget_seconds=600)

    assert "writes" in called


def test_items_past_the_budget_are_not_run() -> None:
    called: list[str] = []
    clock = _Clock()

    def tick() -> float:
        clock.now += 100
        return clock.now

    outcomes = screens.run_items(
        _FakeScreen(), _items(called), allow_writes=True, budget_seconds=250, clock=tick
    )

    assert outcomes[-1].result == OVER_BUDGET
    assert "after" not in called


def _facts() -> RunFacts:
    return RunFacts(
        channel="chrome",
        stamp="적용 배포 `202610081500`",
        allow_writes=False,
        started_seconds=1.4,
        entered_seconds=21.0,
        elapsed_seconds=64.0,
    )


def test_the_block_is_a_paste_ready_table_without_exception_text() -> None:
    outcomes = screens.run_items(_FakeScreen(), _items([]), allow_writes=False, budget_seconds=600)

    block = screens.render_block(outcomes, total=4, facts=_facts())

    assert SENTINEL not in block and "ZZSENTINEL" not in block
    assert "### 화면 확인" in block
    assert "헤드리스 Chrome 1600×1000" in block
    assert "적용 배포 `202610081500` · 쓰기 허락 없음" in block
    assert "항목 4 — 기록 2 · 미기록 1 · 안 함 1 · 걸린 시간 1분 4초 · 끝까지 돎" in block
    assert "| 항목 | 쓰기 | 결과 |" in block
    assert "| 읽기 항목 | 없음 | 있음 · 3개 |" in block
    assert f"| 쓰는 항목 | 씀(지워 되돌림) | {SKIPPED_NO_PERMISSION} |" in block
    assert "| 깨지는 항목 | 없음 | 미기록 — ValueError |" in block
    # 표를 깨는 세로줄은 바꾼다.
    assert "| 뒤 항목 | 없음 | 같음 / 다름 |" in block


def test_a_partial_block_says_where_it_stopped() -> None:
    outcomes = [Outcome(Item("ok", "읽기 항목", lambda screen: "있음"), "있음")]
    facts = _facts()
    facts.ignored_other_apps = True

    block = screens.render_block(outcomes, total=5, facts=facts)

    assert "중간에 끊김 — 1/5 항목까지" in block
    assert "다른 앱 무시" in block


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
    assert screens.select_items(None) == list(ITEMS)
    chosen = screens.select_items(f"{keys[-1]},{keys[0]}")
    assert chosen is not None and [item.key for item in chosen] == [keys[0], keys[-1]]
    assert screens.select_items("없는키") is None


# ---------------------------------------------------------------------------------- 화면 계약


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
    assert 'class="capa-brand-hint"' in _text(COMPONENTS / "intro_summary.py")


def test_the_toolbar_labels_cover_the_declared_order() -> None:
    from capa_simulation.components.theme_toggle import TOOLBAR_BUTTON_ORDER

    assert set(screens.TOOLBAR_LABELS) == set(TOOLBAR_BUTTON_ORDER)


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


@pytest.mark.parametrize("page", [screens.EQUIPMENT_PAGE, screens.SPACE_PAGE])
def test_the_pages_the_items_open_exist(page: str) -> None:
    assert (PROJECT_ROOT / "app_pages" / f"{page}.py").is_file()


@pytest.fixture(autouse=True)
def _no_real_side_effects(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """어느 테스트도 진짜 프로세스를 살피거나 진짜 앱을 띄우지 않는다."""
    monkeypatch.setattr(screens, "running_app_count", lambda: 0)
    yield
