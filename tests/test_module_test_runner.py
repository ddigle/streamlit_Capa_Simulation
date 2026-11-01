# Purpose: 모듈 시험 감시 러너가 코어 data 접근·모듈 폴더 쓰기를 막고 import 길을 앱과 맞춤을 본다.

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import check_module  # noqa: E402
import module_test_runner as runner  # noqa: E402

GUARDED_TESTS = """# Purpose: 감시 러너 시험 — 막힐 접근과 될 접근.

import os
import sqlite3
from pathlib import Path

import duckdb

PROTECT = Path(os.environ["DEMO_PROTECT"])
DATA = Path(os.environ["CAPA_MODULES_DATA_ROOT"])


def test_duckdb_in_the_protected_place() -> None:
    duckdb.connect(str(PROTECT / "x.duckdb"), read_only=True)


def test_sqlite_in_the_protected_place() -> None:
    sqlite3.connect(str(PROTECT / "x.db"))


def test_reading_the_protected_place() -> None:
    (PROTECT / "x.csv").read_text(encoding="utf-8")


def test_writing_the_module_folder() -> None:
    with open(Path(__file__).resolve().parents[1] / "out.txt", "w", encoding="utf-8") as handle:
        handle.write("x")


def test_a_swallowed_block_still_fails() -> None:
    try:
        (PROTECT / "x.csv").read_bytes()
    except OSError:
        pass


def test_writing_the_temporary_data_root() -> None:
    (DATA / "a.txt").write_text("x", encoding="utf-8")


def test_an_in_memory_database() -> None:
    assert duckdb.connect(":memory:").execute("select 1").fetchone() == (1,)
"""

BARE_IMPORT_TEST = """# Purpose: 같은 폴더 맨이름 import 화면을 AppTest 로 연다.

from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[1] / "page.py"


def test_the_page_opens() -> None:
    app = AppTest.from_file(str(PAGE)).run(timeout=60)
    assert not app.exception
"""


def _module(root: Path, files: dict[str, str]) -> Path:
    folder = root / "demo_x"
    for rel, text in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    manifest = {
        "id": "demo_x",
        "name": "시험 모듈",
        "api": 1,
        "owner": "시험 담당",
        "enabled": True,
        "maturity": "L0",
        "pages": [{"slug": "main", "file": "page.py", "title": "시험 화면"}],
    }
    (folder / "module.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return folder


def _environment(root: Path, data: Path, **extra: str) -> dict[str, str]:
    environment = check_module.module_test_environment(root=root, tree=PROJECT_ROOT, data_root=data)
    environment.update(extra)
    return environment


def _pytest_args(folder: Path) -> list[str]:
    return [
        "-c",
        str(PROJECT_ROOT / "pyproject.toml"),
        "--rootdir",
        str(PROJECT_ROOT),
        "-p",
        "no:cacheprovider",
        "--import-mode=importlib",
        "-rfE",
        str(folder / "tests"),
    ]


def _run_runner(
    root: Path, folder: Path, *, protect: Path, data: Path, **extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "module_test_runner.py"),
            "--modules-root",
            str(root),
            "--protect",
            str(protect),
            "--data-root",
            str(data),
            "--",
            "--basetemp",
            str(data / "pytest"),
            *_pytest_args(folder),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PROJECT_ROOT,
        env=_environment(root, data, **extra),
        timeout=300,
        check=False,
    )


def test_blocked_accesses_fail_their_tests_and_are_counted(tmp_path: Path) -> None:
    protect = tmp_path / "core" / "data"
    protect.mkdir(parents=True)
    (protect / "x.csv").write_text("a,b\n", encoding="utf-8")
    root = tmp_path / "modules"
    data = tmp_path / "module-data"
    data.mkdir()
    folder = _module(
        root, {"page.py": "# Purpose: x.\n", "tests/test_demo_x_guard.py": GUARDED_TESTS}
    )

    completed = _run_runner(root, folder, protect=protect, data=data, DEMO_PROTECT=str(protect))

    lines = completed.stdout.splitlines()
    assert completed.returncode != 0, completed.stdout
    assert lines[-1] == "module-tests 2 5 7", completed.stdout
    assert f"{runner.BLOCKED_PREFIX} 5" in lines, completed.stdout
    assert "test_a_swallowed_block_still_fails" in completed.stdout
    assert not (folder / "out.txt").exists()
    assert sorted(path.name for path in protect.iterdir()) == ["x.csv"]
    # 막은 경로는 지킨 폴더 기준 상대 꼴만 찍는다.
    shown = lines[lines.index(f"{runner.BLOCKED_PREFIX} 5") + 1 : -1]
    assert sorted(shown) == [
        "  duckdb.connect data/x.duckdb",
        "  open data/x.csv",
        "  open data/x.csv",
        "  open modules/demo_x/out.txt",
        "  sqlite3.connect data/x.db",
    ]
    assert (data / "a.txt").read_text(encoding="utf-8") == "x"


RELATIVE_WRITE_TESTS = """# Purpose: 감시 러너 시험 — 작업 폴더 기준 상대 경로 쓰기.

NOTE_PATH = "probe_notes.txt"


def test_a_relative_write() -> None:
    with open(NOTE_PATH, "a", encoding="utf-8") as handle:
        handle.write("x")
"""


def test_a_relative_write_into_the_workspace_fails_its_test(tmp_path: Path) -> None:
    """상대 경로 쓰기는 작업 폴더(점검하는 트리 — 앱에서는 운영 체크아웃 뿌리)에 말없이 남는다.
    `--workspace` 아래 쓰기는 막혀 그 시험이 실패하고 파일도 생기지 않는다."""
    workspace = tmp_path / "tree"
    workspace.mkdir()
    root = tmp_path / "modules"
    data = tmp_path / "module-data"
    data.mkdir()
    folder = _module(
        root,
        {"page.py": "# Purpose: x.\n", "tests/test_demo_x_note.py": RELATIVE_WRITE_TESTS},
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "module_test_runner.py"),
            "--modules-root",
            str(root),
            "--protect",
            str(tmp_path / "core-data"),
            "--workspace",
            str(workspace),
            "--data-root",
            str(data),
            "--",
            "--basetemp",
            str(data / "pytest"),
            *_pytest_args(folder),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=workspace,
        env=_environment(root, data),
        timeout=300,
        check=False,
    )

    lines = completed.stdout.splitlines()
    assert lines[-1] == "module-tests 0 1 1", completed.stdout
    assert f"{runner.BLOCKED_PREFIX} 1" in lines, completed.stdout
    assert "  open probe_notes.txt" in lines, completed.stdout
    assert list(workspace.iterdir()) == []


def test_check_module_guards_its_tree_as_the_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """점검은 러너를 트리에서 돌리고(`cwd`) 그 트리를 `--workspace` 로 넘긴다."""
    seen: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["command"], seen["cwd"] = command, kwargs.get("cwd")
        return subprocess.CompletedProcess(command, 0, f"{runner.SUMMARY_PREFIX} 1 0 1\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    tree = tmp_path / "tree"
    folder = tmp_path / "modules" / "demo_x"

    check_module.run_tests(
        folder, root=folder.parent, tree=tree, protect=[tree / "data"], timeout=60
    )

    command = seen["command"]
    assert isinstance(command, list)
    assert command[command.index("--workspace") + 1] == str(tree)
    assert seen["cwd"] == tree


def test_a_same_folder_bare_import_breaks_under_the_runner_like_in_the_app(
    tmp_path: Path,
) -> None:
    root = tmp_path / "modules"
    data = tmp_path / "module-data"
    data.mkdir()
    folder = _module(
        root,
        {
            "page.py": "# Purpose: x.\nimport helper\n\nVALUE = helper.VALUE\n",
            "helper.py": "# Purpose: 도움.\nVALUE = 1\n",
            "tests/test_demo_x_page.py": BARE_IMPORT_TEST,
        },
    )

    guarded = _run_runner(root, folder, protect=tmp_path / "core-data", data=data)
    plain = subprocess.run(
        [sys.executable, "-m", "pytest", *_pytest_args(folder)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PROJECT_ROOT,
        env=_environment(root, data),
        timeout=300,
        check=False,
    )

    assert guarded.stdout.splitlines()[-1] == "module-tests 0 1 1", guarded.stdout
    assert plain.returncode == 0, plain.stdout


def test_the_streamlit_name_the_runner_replaces_still_exists() -> None:
    from streamlit.runtime.scriptrunner import script_runner

    assert hasattr(script_runner, runner.STREAMLIT_SYS_PATH_NAME)


def test_the_app_like_sys_path_skips_only_module_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from streamlit.runtime.scriptrunner import script_runner

    # 시험이 끝나면 원래 이름으로 되돌린다(같은 값을 다시 넣어 두면 monkeypatch 가 복원한다).
    original = getattr(script_runner, runner.STREAMLIT_SYS_PATH_NAME)
    monkeypatch.setattr(script_runner, runner.STREAMLIT_SYS_PATH_NAME, original)
    root = tmp_path / "modules"
    (root / "demo_x").mkdir(parents=True)
    page = root / "demo_x" / "page.py"
    page.write_text("", encoding="utf-8")
    other = tmp_path / "app.py"
    other.write_text("", encoding="utf-8")

    assert runner.install_app_like_sys_path(str(root))
    factory = getattr(script_runner, runner.STREAMLIT_SYS_PATH_NAME)
    before = list(sys.path)
    with factory(str(page)):
        assert sys.path == before
    with factory(str(other)):
        assert sys.path[0] == str(tmp_path)
    assert sys.path == before


def test_a_missing_streamlit_name_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    from streamlit.runtime.scriptrunner import script_runner

    monkeypatch.delattr(script_runner, runner.STREAMLIT_SYS_PATH_NAME)
    assert runner.install_app_like_sys_path("/x/modules") is False


def test_the_guard_verdicts(tmp_path: Path) -> None:
    protect = tmp_path / "data"
    data_root = protect / "modules-tmp"
    modules = tmp_path / "modules"
    guard = runner.Guard.build(
        protect=[str(protect)], modules_root=str(modules), data_root=str(data_root)
    )

    assert guard.verdict(str(protect / "capa_simulation.duckdb"), write=False) == "protect"
    assert guard.verdict(str(protect), write=False) == "protect"
    assert guard.verdict(str(data_root / "x.csv"), write=True) is None
    assert guard.verdict(str(modules / "demo_x" / "page.py"), write=False) is None
    assert guard.verdict(str(modules / "demo_x" / "out.txt"), write=True) == "modules"
    assert guard.verdict(":memory:", write=True) is None
    assert guard.verdict(str(tmp_path / "data-other" / "x"), write=True) is None
    with pytest.raises(PermissionError):
        guard.check(str(protect / "x.csv"), write=False, action="open")
    assert guard.blocked == [("open", "data/x.csv")]


def test_the_workspace_verdict_blocks_writes_only(tmp_path: Path) -> None:
    workspace = tmp_path / "tree"
    data_root = workspace / "tmp-data"
    guard = runner.Guard.build(
        protect=[str(workspace / "data")],
        modules_root=str(workspace / "modules"),
        data_root=str(data_root),
        workspace=str(workspace),
    )

    assert guard.verdict(str(workspace / "notes.txt"), write=True) == "workspace"
    assert guard.verdict(str(workspace / "pyproject.toml"), write=False) is None
    assert guard.verdict(str(workspace / "modules" / "demo_x" / "a.txt"), write=True) == "modules"
    assert guard.verdict(str(workspace / "data" / "x.duckdb"), write=True) == "protect"
    assert guard.verdict(str(data_root / "a.csv"), write=True) is None
    assert guard.verdict(str(tmp_path / "elsewhere.txt"), write=True) is None
    with pytest.raises(PermissionError, match="ctx.data_dir"):
        guard.check(str(workspace / "sub" / "notes.txt"), write=True, action="open")
    assert guard.blocked == [("open", "sub/notes.txt")]


def test_the_audit_hook_reads_open_flags(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    guard = runner.Guard.build(protect=[], modules_root=str(modules), data_root=None)
    target = str(modules / "demo_x" / "out.txt")

    guard.audit("open", (target, "r", os.O_RDONLY))
    with pytest.raises(PermissionError):
        guard.audit("open", (target, None, os.O_WRONLY | os.O_CREAT))
    with pytest.raises(PermissionError):
        guard.audit("os.mkdir", (target, 0o777, None))
    guard.audit("import", ("x", None, None, None, None))
    assert len(guard.blocked) == 2


def test_the_runner_summary_line_is_what_check_module_reads() -> None:
    result = check_module.parse_runner_output(
        "....\nFAILED tests/test_demo_x_a.py::test_one - assert 1\n"
        f"{runner.BLOCKED_PREFIX} 0\n{runner.SUMMARY_PREFIX} 3 1 4\n",
        1,
    )
    assert (result.state, result.passed, result.failed, result.total) == ("failed", 3, 1, 4)
    assert result.failures == ["test_demo_x_a.py::test_one"]
    assert check_module.parse_runner_output("빈 출력", 3).state == "runner"
