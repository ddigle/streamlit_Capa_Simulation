# Purpose: 모듈 시험을 감시 아래 pytest 로 돌린다(코어 data 접근·저장소 안 쓰기를 막는다).

"""모듈 시험 러너 — `scripts/check_module.py` 만 부른다(사람이 직접 칠 일은 없다).

    python scripts/module_test_runner.py --modules-root <뿌리> --protect <트리>/data \\
        [--protect <운영 저장소>/data] [--workspace <트리>] --data-root <임시 폴더> \\
        -- <pytest 인자…>

모듈 시험은 담당자가 쓴 코드를 실행한다. 코어 시험 틀(DB 자리 돌림·sessionfinish 검사)이 걸리지
않으므로 이 러너가 그 몫을 한다. 감사 훅(`sys.addaudithook`)은 지울 수 없어 이 하위 프로세스
안에서만 건다.

- **감시** — `--protect` 아래는 읽기·쓰기 모두 막는다(임시 데이터 뿌리는 빼고). `--modules-root`
  아래는 쓰기만 막는다(모듈 코드 폴더에는 실행 중 쓰지 않는다). `--workspace`(점검하는 트리 — 하위
  프로세스의 작업 폴더) 아래도 쓰기만 막는다 — 상대 경로(`open("notes.txt", "a")`)로 쓴 파일은 그
  뿌리에 생기고, 앱에서는 운영 체크아웃 뿌리에 말없이 남는다. 감사 사건이 없는 `duckdb.connect` 는
  감싸서 같은 규칙으로 본다(읽기 전용도 막는다 — 잠금이 사용자 앱과 겹친다). 막은 접근은 그 시험의
  실패가 되고(시험이 예외를 삼켜도), 끝에 「감시가 막은 접근 n」 을 찍는다. AppTest 의 import 길도
  앱과 같게 맞춘다(아래).
- **앱과 같은 import 길** — Streamlit 은 메인 스크립트의 폴더를 회차 동안 `sys.path` 에 넣는다.
  앱에서는 저장소 뿌리지만 `AppTest.from_file(<모듈 화면>)` 에서는 모듈 폴더다. 그래서 같은 폴더
  맨이름 `import helper` 가 모듈 시험에서만 통과한다. 러너는 스크립트 폴더가 모듈 뿌리 아래이면
  아무것도 넣지 않게 `script_runner.modified_sys_path` 를 바꿔 끼운다. 이 러너 자신의
  폴더(`scripts/`)도 `sys.path` 에서 뺀다.

마지막 줄은 `module-tests <통과> <실패> <전체>` 다(check_module 이 읽는다). 종료 코드는 pytest 의
것이고, 감시가 막은 접근이 있었는데 pytest 가 0 이면 1 이다. Streamlit 내부 이름이 바뀌어 길을
맞추지 못하면 3.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Literal

import pytest

SUMMARY_PREFIX: Final = "module-tests"
BLOCKED_PREFIX: Final = "감시가 막은 접근"
STREAMLIT_SYS_PATH_NAME: Final = "modified_sys_path"
_WRITE_FLAGS: Final = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_SHOWN_BLOCKS: Final = 10
_BLOCKED_WHAT: Final[dict[str, str]] = {
    "protect": "코어 데이터 자리",
    "modules": "모듈 코드 폴더 쓰기",
    "workspace": "저장소 안 쓰기(상대 경로면 ctx.data_dir 로)",
}
# 감사 사건 → 인자 가운데 (경로 자리, 쓰기인가).
_PATH_EVENTS: Final[dict[str, tuple[tuple[int, bool], ...]]] = {
    "os.remove": ((0, True),),
    "os.rmdir": ((0, True),),
    "os.mkdir": ((0, True),),
    "os.rename": ((0, True), (1, True)),
    "os.link": ((0, False), (1, True)),
    "os.symlink": ((1, True),),
    "os.truncate": ((0, True),),
    "os.listdir": ((0, False),),
    "os.scandir": ((0, False),),
    "shutil.rmtree": ((0, True),),
    "shutil.copyfile": ((0, False), (1, True)),
    "shutil.copytree": ((0, False), (1, True)),
    "shutil.move": ((0, True), (1, True)),
    "sqlite3.connect": ((0, False),),
}


def _normalized(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


@dataclass
class Guard:
    """코어 데이터 자리(`protect`)와 모듈 뿌리(`modules_root`)를 지키는 판정과 막은 기록."""

    protect: tuple[str, ...]
    modules_root: str
    data_root: str | None
    workspace: str | None = None
    blocked: list[tuple[str, str]] = field(default_factory=list)
    _busy: threading.local = field(default_factory=threading.local)

    @classmethod
    def build(
        cls,
        *,
        protect: Sequence[str],
        modules_root: str,
        data_root: str | None,
        workspace: str | None = None,
    ) -> Guard:
        return cls(
            protect=tuple(_normalized(path) for path in protect),
            modules_root=_normalized(modules_root),
            data_root=None if data_root is None else _normalized(data_root),
            workspace=None if workspace is None else _normalized(workspace),
        )

    def verdict(
        self, path: str, *, write: bool
    ) -> Literal["protect", "modules", "workspace"] | None:
        """막을 까닭(`protect` · `modules` · `workspace`) 또는 None. 임시 데이터 뿌리는 늘 된다."""
        if path in (":memory:", "") or path.startswith(":memory:"):
            return None
        place = _normalized(path)
        if self.data_root is not None and _under(place, self.data_root):
            return None
        if any(_under(place, root) for root in self.protect):
            return "protect"
        if write and _under(place, self.modules_root):
            return "modules"
        if write and self.workspace is not None and _under(place, self.workspace):
            return "workspace"
        return None

    def check(self, raw: object, *, write: bool, action: str) -> None:
        """막을 접근이면 적고 `PermissionError` 를 낸다."""
        if isinstance(raw, int) or raw is None:
            return
        try:
            path = os.fsdecode(raw)  # type: ignore[arg-type]
        except TypeError:
            return
        kind = self.verdict(path, write=write)
        if kind is None:
            return
        self.blocked.append((action, self._relative(path, kind)))
        what = _BLOCKED_WHAT[kind]
        raise PermissionError(f"모듈 시험 감시가 막음 — {what}: {self._relative(path, kind)}")

    def _relative(self, path: str, kind: str) -> str:
        place = _normalized(path)
        if kind == "workspace" and self.workspace is not None:
            # 저장소 뿌리 기준 상대 꼴 — 뿌리 폴더 이름(사본 트리면 임시 이름)은 붙이지 않는다.
            return Path(os.path.relpath(place, self.workspace)).as_posix()
        roots = self.protect if kind == "protect" else (self.modules_root,)
        for root in roots:
            if _under(place, root):
                name = os.path.basename(root.rstrip(os.sep))
                rest = os.path.relpath(place, root)
                return name if rest == "." else f"{name}/{Path(rest).as_posix()}"
        return os.path.basename(place)

    def audit(self, event: str, args: tuple[Any, ...]) -> None:
        if event != "open" and event not in _PATH_EVENTS:
            return
        if getattr(self._busy, "active", False):
            return
        self._busy.active = True
        try:
            if event == "open":
                path, mode, flags = (args + (None, None, None))[:3]
                write = bool(isinstance(flags, int) and flags & _WRITE_FLAGS) or bool(
                    isinstance(mode, str) and any(flag in mode for flag in "wax+")
                )
                self.check(path, write=write, action="open")
                return
            for index, write in _PATH_EVENTS[event]:
                if index < len(args):
                    self.check(args[index], write=write, action=event)
        finally:
            self._busy.active = False


def install_duckdb_guard(guard: Guard) -> bool:
    """`duckdb.connect` 를 감싼다(DuckDB 는 C 에서 파일을 열어 감사 사건이 없다). 없으면 False."""
    try:
        import duckdb
    except ImportError:
        return False
    original: Callable[..., Any] = duckdb.connect

    def connect(database: object = ":memory:", *args: Any, **kwargs: Any) -> Any:
        read_only = bool(kwargs.get("read_only", args[0] if args else False))
        guard.check(database, write=not read_only, action="duckdb.connect")
        return original(database, *args, **kwargs)

    duckdb.connect = connect
    return True


def install_app_like_sys_path(modules_root: str) -> bool:
    """AppTest 가 모듈 화면 폴더를 `sys.path` 에 넣지 않게 한다(앱과 같다). 이름이 없으면 False."""
    try:
        from streamlit.runtime.scriptrunner import script_runner
    except ImportError:
        return False
    original = getattr(script_runner, STREAMLIT_SYS_PATH_NAME, None)
    if original is None:
        return False
    factory: Callable[[str], Any] = original
    root = _normalized(modules_root)

    class AppLikeSysPath:
        """스크립트 폴더가 모듈 뿌리 아래이면 `sys.path` 를 건드리지 않는다. 그 밖은 원래대로."""

        def __init__(self, main_script_path: str) -> None:
            self._skip = _under(
                _normalized(os.path.dirname(os.path.abspath(main_script_path))), root
            )
            self._inner = factory(main_script_path)

        def __enter__(self) -> None:
            if not self._skip:
                self._inner.__enter__()

        def __exit__(
            self,
            kind: type[BaseException] | None,
            error: BaseException | None,
            trace: TracebackType | None,
        ) -> Literal[False]:
            if not self._skip:
                self._inner.__exit__(kind, error, trace)
            return False

    setattr(script_runner, STREAMLIT_SYS_PATH_NAME, AppLikeSysPath)
    return True


class GuardPlugin:
    """pytest 플러그인 — 단계마다 막은 접근이 있었으면 그 시험을 실패로 바꾸고 수를 센다."""

    def __init__(self, guard: Guard) -> None:
        self.guard = guard
        self.collected = 0
        self.collection_errors = 0
        self.passed: set[str] = set()
        self.failed: set[str] = set()
        self._phase_start = 0

    def _mark(self) -> None:
        self._phase_start = len(self.guard.blocked)

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_setup(self, item: pytest.Item) -> Generator[None, None, None]:
        self._mark()
        return (yield)

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_call(self, item: pytest.Item) -> Generator[None, None, None]:
        self._mark()
        return (yield)

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_teardown(self, item: pytest.Item) -> Generator[None, None, None]:
        self._mark()
        return (yield)

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(
        self, item: pytest.Item, call: pytest.CallInfo[None]
    ) -> Generator[None, pytest.TestReport, pytest.TestReport]:
        report = yield
        fresh = self.guard.blocked[self._phase_start :]
        if fresh and not report.failed:
            report.outcome = "failed"
            shown = ", ".join(path for _, path in fresh[:3])
            report.longrepr = f"{BLOCKED_PREFIX} {len(fresh)} — {shown}"
        return report

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.failed:
            self.collection_errors += 1

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        self.collected = len(session.items)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.failed:
            self.failed.add(report.nodeid)
        elif report.when == "call" and report.passed:
            self.passed.add(report.nodeid)

    def summary(self) -> tuple[int, int, int]:
        failed = len(self.failed) + self.collection_errors
        passed = len(self.passed - self.failed)
        return passed, failed, self.collected + self.collection_errors


def _split(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    items = list(argv)
    if "--" in items:
        index = items.index("--")
        return items[:index], items[index + 1 :]
    return items, []


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="모듈 시험 감시 러너(check_module.py 가 부른다)")
    parser.add_argument("--modules-root", required=True, help="모듈 뿌리 — 그 아래 쓰기를 막는다")
    parser.add_argument(
        "--protect", action="append", default=[], help="읽기·쓰기를 모두 막을 폴더(여러 번)"
    )
    parser.add_argument(
        "--data-root", default=None, help="모듈 시험의 임시 데이터 뿌리(막지 않는다)"
    )
    parser.add_argument(
        "--workspace", default=None, help="점검하는 트리 — 그 아래 쓰기를 막는다(상대 경로 쓰기)"
    )
    return parser.parse_args(argv)


def _drop_own_directory() -> None:
    own = _normalized(str(Path(__file__).resolve().parent))
    sys.path[:] = [entry for entry in sys.path if not entry or _normalized(entry) != own]


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    own_args, pytest_args = _split(sys.argv[1:] if argv is None else argv)
    args = _parse(own_args)
    guard = Guard.build(
        protect=args.protect,
        modules_root=args.modules_root,
        data_root=args.data_root,
        workspace=args.workspace,
    )
    if not install_app_like_sys_path(args.modules_root):
        print(
            "Streamlit 내부 이름이 바뀜 — streamlit.runtime.scriptrunner.script_runner."
            f"{STREAMLIT_SYS_PATH_NAME} 를 찾지 못해 앱과 같은 import 길을 맞추지 못했습니다"
        )
        print(f"{SUMMARY_PREFIX} 0 0 0")
        return 3
    install_duckdb_guard(guard)
    _drop_own_directory()
    sys.addaudithook(guard.audit)
    plugin = GuardPlugin(guard)
    code = int(pytest.main(pytest_args, plugins=[plugin]))
    blocked = list(guard.blocked)
    print(f"{BLOCKED_PREFIX} {len(blocked)}")
    for action, path in blocked[:_SHOWN_BLOCKS]:
        print(f"  {action} {path}")
    passed, failed, total = plugin.summary()
    print(f"{SUMMARY_PREFIX} {passed} {failed} {total}")
    if blocked and code == 0:
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
