# Purpose: 런북 7장 화면 확인을 별도 포트 앱과 저장소 밖 Playwright 로 돌려 개수·있음/없음만 찍는다.

"""사내 배포 화면 확인 — 런북 7장(`docs/internal_update_runbook.md`)의 화면 확인을 코드로 고정한다.

사내 에이전트는 배포마다 7장의 화면 확인을 저장소 밖에 설치한 Playwright 와 이미 깔린 Chrome 으로
손수 해 왔다(`202610081500` 리뷰 「사외 요청」 4번). 그 요령 — 입장 화면 단추는 `#capa-intro-host`
안, 데이터 편집기 머리 칸은 `[role=columnheader]` 의 `aria-colindex` 를 가로로 굴려 찾기, Space
서랍 검색은 `type`(fill 은 반응이 없다) — 을 이 파일이 갖는다. 사외에서 만들며 더 찾은 넷도 있다 —
첫 방문의 테마 스크립트가 화면을 한 번 새로 읽어 그 사이 `evaluate` 가 끊긴다(`Screen.enter`), 접힌
사이드바 묶음을 펴는 동안 누른 링크는 이동하지 않는다(`Screen.open_page`), 컴포넌트(Space 편집기)는
shadow root 안이라 `document.querySelector` 로 닿지 않는다(로케이터로 잡은 요소에서 `evaluate`), CSS
선택자에 한글을 `json.dumps` 기본값(`\\uXXXX`)으로 넣으면 아무것도 못 찾는다(`_css_string`).

    uv pip install --target <저장소 밖>/pw playwright        # 처음 한 번. 브라우저는 받지 않는다
    uv run --no-sync python scripts/check_deploy_screens.py --playwright-dir <저장소 밖>/pw \\
        --output <저장소 밖>/screens.md
    uv run --no-sync python scripts/check_deploy_screens.py --list   # 항목 목록만(Playwright 없이)

**하는 일.** 사용자 앱이 떠 있는지 먼저 본다 — `streamlit run … app.py` 프로세스, 그리고
두 DuckDB 를 열 수 있는지. 있으면 「사용자 앱이 떠 있습니다 — 화면 확인은 미룹니다」 한 줄과
코드 1 로 멈춘다(사용자 앱은 절대 끄지 않는다). 앱은 rerun 동안만 DB 를 쥐어 가만히 떠 있는
앱은 잠금 확인을 지나치므로 프로세스를 함께 본다. 그다음 `--port` 에 이 저장소의 앱을 따로 띄우고
`/_stcore/health` 를 기다린 뒤, 헤드리스 Chrome 으로 입장 화면을 넘겨 항목을 차례로 돌린다. 끝나면
(예외로 끝나도) 띄운 앱을 끈다. 결과는 리뷰 문서에 그대로 붙이는 Markdown 블록이다.

**지키는 것.**

- **값을 찍지 않는다.** 결과 칸에는 개수·있음/없음·같음/다름·px 만 둔다. 공정·제품·설비·시나리오
  이름이나 코드처럼 화면에서 읽은 글자는 넣지 않는다 — 화면 글자는 판정에만 쓰고 버린다. 실패는
  예외 종류(클래스 이름)만 적는다. 이 앱의 오류 문구에는 식별값이 실린다.
- **DB 에 쓰지 않는다.** 쓰는 항목은 `writes=True` 로 등록하고, `--allow-writes` 없이는 돌리지 않고
  「안 함(허락 없음)」으로 찍는다. 쓰는 항목은 저장한 것을 같은 항목 안에서 지워 원상 복구하는 것만
  둔다.
- **경로는 저장소 밖만 받는다.** `--output`·`--shots`·`--playwright-dir` 가 저장소 안이면 거절한다.
  스크린샷은 `--shots` 를 줄 때만 찍는다(화면에 이름이 보이므로 리뷰 커밋 전에 지운다).
- **Playwright 는 이 저장소의 의존성이 아니다.** `--playwright-dir` 를 `sys.path` 끝에 붙여
  부를 때만 읽는다. 이 파일의 나머지(경로 검사·잠금 확인·앱 수명·결과 꼴)는 Playwright 없이
  돈다.
- **30분 안에 끝난다.** 사내 백그라운드 실행은 30분이면 죽는다. `--budget-minutes`(기본 20)를
  넘긴 뒤의 항목은 「미기록 — 시간 예산 넘음」으로 남기고, `--output` 은 항목마다 다시 써서
  중간에 끊겨도 그때까지 돈 칸이 남는다.

**항목 더하는 법**(통합자가 배포마다 7장을 쓰며 더한다). 함수 하나를 쓰고 `ITEMS` 에 한 줄을 더한다.

    def check_new_thing(screen: Screen) -> str:
        screen.open_page(EQUIPMENT_PAGE)
        screen.open_tab("RawData")
        return "있음" if screen.selectbox_value("등록할 표") is not None else "없음"

    ITEMS = (..., Item("new_thing", "새 확인", check_new_thing),)

함수는 `Screen`(공통 뼈대 — 페이지 이동·탭·사이드바 상자·선택 상자·스위치·데이터 편집기 머리 칸·
행 읽기)만 쓰고, 결과 문자열은 고정 글자와 수로만 만든다. 항목 하나가 예외로 끝나도 나머지는 돈다.
돌기 전에 뼈대가 열린 덮개(Summary)·펼친 목록을 닫는다(`Screen.settle`). 화면을 바꾸는 토글은 항목
안에서 `try/finally` 로 되돌린다.

사외에서 돈 수는 합성 표본의 `샘플 관측` 일 뿐이다(AGENTS.md 10-1).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Protocol

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.components.theme_toggle import (  # noqa: E402
    GUIDE_BUTTON_ID,
    PRINT_BUTTON_ID,
    THEME_BUTTON_ID,
    TOOLBAR_BUTTON_ORDER,
)
from capa_simulation.settings import (  # noqa: E402
    DEPLOY_STATE_PATH,
    DUCKDB_PATH,
    EQUIPMENT_DUCKDB_PATH,
)

EXIT_OK: Final = 0
# 사용자 앱이 떠 있다(프로세스 또는 DB 잠금) — 미룬다. 사내 런북이 이 코드를 「나중에 다시」로
# 읽는다.
EXIT_DEFERRED: Final = 1
# 준비가 안 됐다 — 경로·Playwright·포트·앱 기동·브라우저.
EXIT_NOT_READY: Final = 2

DEFERRED_MESSAGE: Final = "사용자 앱이 떠 있습니다 — 화면 확인은 미룹니다"
INSTALL_HINT: Final = (
    "Playwright 가 없습니다 — 저장소 밖에 한 번 설치합니다"
    "(브라우저는 받지 않고 깔린 Chrome 을 씁니다):\n"
    "  uv pip install --target <저장소 밖 폴더> playwright\n"
    "그 폴더를 --playwright-dir 로 줍니다."
)
UNRECORDED: Final = "미기록"
SKIPPED_NO_PERMISSION: Final = "안 함(허락 없음)"
OVER_BUDGET: Final = f"{UNRECORDED} — 시간 예산 넘음"

DEFAULT_PORT: Final = 8551
DEFAULT_CHANNEL: Final = "chrome"
DEFAULT_BUDGET_MINUTES: Final = 20.0
VIEWPORT: Final = (1600, 1000)
# 앱이 health 에 답할 때까지, 입장 화면의 `Detail` 이 눌릴 수 있을 때까지(공식버전 요약을 다
# 받은 뒤다 — 사외 합성 표본에서 18초). 사내 실데이터는 더 걸린다.
START_TIMEOUT_SECONDS: Final = 180.0
INTRO_TIMEOUT_SECONDS: Final = 180.0
STOP_TIMEOUT_SECONDS: Final = 15.0
# 항목 하나 안의 Playwright 기다림(클릭·나타남) 기본값.
ACTION_TIMEOUT_MS: Final = 30_000

# 화면 계약. 바뀌면 `tests/test_check_deploy_screens.py` 가 자산·코드와 대조해 알린다.
# 입장 화면 호스트(`intro_overlay_assets/intro.js` 의 `HOST_ID`). 열린 shadow root 라 CSS 로 뚫린다.
INTRO_HOST_ID: Final = "capa-intro-host"
# 사이드바 머리칸의 `S.PKG CAPA` 라벨(`intro_overlay.SUMMARY_LABEL_ID`). 그 모듈을 부르면 Streamlit
# 캐시 경고가 수십 줄 찍혀 출력이 지저분해진다 — 값만 옮기고 테스트가 같은지 본다.
SUMMARY_LABEL_ID: Final = "capa-brand-label"
EQUIPMENT_PAGE: Final = "available_equipment_status"
SPACE_PAGE: Final = "space_status"
TOOLBAR_LABELS: Final[dict[str, str]] = {
    GUIDE_BUTTON_ID: "Guide",
    PRINT_BUTTON_ID: "Print",
    THEME_BUTTON_ID: "테마",
}


# ---------------------------------------------------------------------------------- 경로


def inside_repository(path: Path, root: Path = PROJECT_ROOT) -> bool:
    """저장소 안(루트 포함)인가. Windows 는 대소문자를 가리지 않으므로 `normcase` 로 견준다."""
    target = os.path.normcase(os.path.abspath(path.expanduser().resolve()))
    base = os.path.normcase(os.path.abspath(root.resolve()))
    return target == base or target.startswith(base.rstrip("\\/") + os.sep)


def refused_paths(args: argparse.Namespace, root: Path = PROJECT_ROOT) -> list[str]:
    """저장소 안을 가리키는 경로 옵션의 이름. 비어 있어야 돈다. 경로 자체는 찍지 않는다."""
    named = (
        ("--output", args.output),
        ("--shots", args.shots),
        ("--playwright-dir", args.playwright_dir),
    )
    return [name for name, value in named if value is not None and inside_repository(value, root)]


# ---------------------------------------------------------------------------------- 준비


def load_playwright(directory: Path) -> Any | None:
    """`playwright.sync_api` 모듈. 없으면 None.

    폴더는 `sys.path` **끝**에 붙인다 — `--target` 설치는 `typing_extensions` 같은 공용 패키지도
    함께 깔아서, 앞에 두면 이 저장소의 의존성을 가린다.
    """
    if not directory.is_dir():
        return None
    entry = str(directory.resolve())
    if entry not in sys.path:
        sys.path.append(entry)
    try:
        return importlib.import_module("playwright.sync_api")
    except ImportError:
        return None


def locked_databases(
    paths: Sequence[Path], *, connect: Callable[..., Any] = duckdb.connect
) -> list[Path]:
    """다른 프로세스가 잡고 있는 DB. DuckDB 는 프로세스 배타 잠금이라 `read_only` 로도 못 연다.

    없는 파일은 건너뛴다(앱이 처음 열 때 만든다). 연 연결은 바로 닫는다 — 띄울 앱이 열어야 한다.
    """
    locked: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            connection = connect(str(path), read_only=True)
        except duckdb.IOException:
            locked.append(path)
            continue
        connection.close()
    return locked


# `streamlit run … app.py` 꼴의 명령줄. 런북의 사람 규칙(「명령줄에 app.py 가 있으면 사용자
# 앱」)과 같다.
_APP_COMMAND = re.compile(r"streamlit.*\brun\b.*\bapp\.py\b", re.IGNORECASE)
# 그 명령줄을 돌리는 프로그램. 셸(`bash -c "… streamlit run app.py …"`)이나 그 글자를 찾는 명령은
# 앱이 아니다 — 파이썬·streamlit 실행 파일만 센다.
_APP_PROGRAM = re.compile(r"(python[\d.]*w?|streamlit)(\.exe)?", re.IGNORECASE)
# Windows 는 다른 프로세스의 작업 폴더를 볼 수 없어 명령줄만 읽는다(venv 의 python.exe 는 본
# 해석기를 자식으로 띄우므로 앱 하나가 두 줄로 나온다 — 하나라도 맞으면 된다). 여러 줄 명령줄은
# 한 줄로 접는다.
_WINDOWS_PROCESS_QUERY = (
    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*streamlit*' } | "
    r"ForEach-Object { $_.CommandLine -replace '\s+', ' ' }"
)


def _program(command_line: str) -> str:
    """명령줄 첫 낱말의 파일 이름(따옴표 경로 포함)."""
    text = command_line.strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        first = text[1:end] if end > 0 else text[1:]
    else:
        first = text.split(maxsplit=1)[0] if text else ""
    return re.split(r"[\\/]", first)[-1]


def is_app_command(command_line: str) -> bool:
    """파이썬·streamlit 이 `streamlit run … app.py` 를 돌리는 명령줄인가."""
    return bool(
        _APP_PROGRAM.fullmatch(_program(command_line)) and _APP_COMMAND.search(command_line)
    )


def _same_app(command_line: str, cwd: str | None, root: Path) -> bool:
    """그 명령줄의 `app.py` 가 이 저장소의 것인가. 작업 폴더를 모르면 같다고 본다(보수적으로)."""
    target = os.path.normcase(str((root / "app.py").resolve()))
    for token in re.split(r"[\s\"']+", command_line):
        if not token or Path(token).name.lower() != "app.py":
            continue
        candidate = Path(token)
        if not candidate.is_absolute():
            if cwd is None:
                return True
            candidate = Path(cwd) / candidate
        if os.path.normcase(str(candidate.resolve())) == target:
            return True
    return False


def _proc_commands() -> list[tuple[str, str | None]]:
    """Linux `/proc` 의 (명령줄, 작업 폴더). 남의 프로세스라 작업 폴더를 못 읽으면 None."""
    found: list[tuple[str, str | None]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        command = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
        if not is_app_command(command):
            continue
        try:
            cwd: str | None = os.readlink(entry / "cwd")
        except OSError:
            cwd = None
        found.append((command, cwd))
    return found


def _windows_commands() -> list[tuple[str, str | None]]:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_PROCESS_QUERY],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=True,
    )
    return [(line.strip(), None) for line in completed.stdout.splitlines() if line.strip()]


def running_app_count(
    root: Path = PROJECT_ROOT,
    *,
    list_commands: Callable[[], list[tuple[str, str | None]]] | None = None,
) -> int | None:
    """이 저장소의 앱으로 보이는 다른 프로세스 수. 살피지 못하면 None.

    DB 잠금만으로는 모자란다 — 앱은 rerun 동안만 DB 를 쥐므로(`_sql_helpers.pinned_connections`)
    가만히 떠 있는 사용자 앱은 잠금 확인을 지나친다. 그 사이 사용자가 누르면 그쪽 화면이 잠금 오류로
    선다. 이 스크립트가 띄울 앱보다 **먼저** 본다(제 자식을 세지 않게).
    """
    if list_commands is None:
        list_commands = _windows_commands if sys.platform == "win32" else _proc_commands
    try:
        commands = list_commands()
    except (OSError, subprocess.SubprocessError):
        return None
    return sum(
        1 for command, cwd in commands if is_app_command(command) and _same_app(command, cwd, root)
    )


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """그 포트에 누가 듣고 있는가. Windows 에서는 두 번째 Streamlit 이 오류 없이 먼저 뜬 쪽에 얹혀
    엉뚱한 앱을 재게 되므로 띄우기 전에 막는다."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1.0)
        return probe.connect_ex((host, port)) == 0


def health_ok(url: str) -> bool:
    """`/_stcore/health` 가 200 인가. 사내 프록시 환경변수를 타지 않게 프록시 없이 묻는다."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=2.0) as response:
            return int(response.status) == 200
    except (OSError, ValueError):
        return False


def applied_stamp(path: Path = DEPLOY_STATE_PATH) -> str:
    """적용 기록의 배포 번호(`YYYYMMDDHHMM`). 그 밖의 글자는 옮기지 않는다."""
    try:
        stamp = json.loads(path.read_text(encoding="utf-8")).get("stamp")
    except (OSError, ValueError, AttributeError):
        return "적용 기록 없음"
    if isinstance(stamp, str) and re.fullmatch(r"\d{12}", stamp):
        return f"적용 배포 `{stamp}`"
    return "적용 기록 꼴 다름"


# ---------------------------------------------------------------------------------- 앱 수명


class AppStartError(RuntimeError):
    """띄운 앱이 health 에 답하지 않았다. 문구에는 수와 고정 글자만 둔다."""


class Process(Protocol):
    """`subprocess.Popen` 에서 쓰는 만큼. 테스트가 가짜를 넣는다."""

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def send_signal(self, sig: int) -> None: ...


def app_command(port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--server.fileWatcherType",
        "none",
        "--browser.gatherUsageStats",
        "false",
    ]


class StreamlitApp:
    """확인용 앱 한 벌. `with` 를 나가면(예외여도) 끈다.

    끌 때는 먼저 Streamlit 이 받는 신호(Windows `CTRL_BREAK`, 그 밖 `SIGTERM`)로 서버를 멈춰
    DuckDB 연결이 닫히게 하고, `STOP_TIMEOUT_SECONDS` 안에 안 끝나면 죽인다. 환경변수는 그대로
    넘긴다 — 사외에서 워크트리 코드를 쓰게 하는 `PYTHONPATH` 가 자식에게도 가야 한다.
    """

    def __init__(
        self,
        port: int,
        *,
        root: Path = PROJECT_ROOT,
        popen: Callable[..., Process] = subprocess.Popen,
        probe: Callable[[str], bool] = health_ok,
        port_probe: Callable[[int], bool] = port_in_use,
        start_timeout: float = START_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.port = port
        self.root = root
        self.base_url = f"http://127.0.0.1:{port}/"
        self.process: Process | None = None
        self.started_seconds = 0.0
        self._popen = popen
        self._probe = probe
        self._port_probe = port_probe
        self.port_released = True
        self._start_timeout = start_timeout
        self._clock = clock
        self._sleep = sleep

    def __enter__(self) -> StreamlitApp:
        began = self._clock()
        options: dict[str, Any] = {
            "cwd": str(self.root),
            "env": os.environ.copy(),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            # `CTRL_BREAK` 는 프로세스 묶음 단위로 간다 — 자식을 따로 묶어야 이 스크립트가
            # 받지 않는다.
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        self.process = self._popen(app_command(self.port), **options)
        try:
            self._wait_ready(began)
        except BaseException:
            self.stop()
            raise
        self.started_seconds = self._clock() - began
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()

    def _wait_ready(self, began: float) -> None:
        assert self.process is not None
        health = f"{self.base_url}_stcore/health"
        while True:
            code = self.process.poll()
            if code is not None:
                raise AppStartError(f"앱이 뜨다가 끝났습니다(종료 코드 {code})")
            if self._probe(health):
                return
            if self._clock() - began > self._start_timeout:
                raise AppStartError(f"앱이 {self._start_timeout:.0f}초 안에 답하지 않았습니다")
            self._sleep(1.0)

    def stop(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return
        try:
            if sys.platform == "win32":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.terminate()
        except OSError:
            # 콘솔이 없는 셸에서는 `CTRL_BREAK` 를 보낼 수 없다 — 바로 끊는다.
            process.terminate()
        try:
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
        # Windows 의 venv `python.exe` 는 본 해석기를 자식으로 띄운다. 띄운 쪽이 끝나도 자식이
        # 포트를 잠깐 더 쥘 수 있어, 포트가 비는 것까지 본다.
        began = self._clock()
        while self._port_probe(self.port):
            if self._clock() - began > STOP_TIMEOUT_SECONDS:
                self.port_released = False
                break
            self._sleep(0.5)


# ---------------------------------------------------------------------------------- 공통 뼈대

_RUNNING_JS = """() => !!document.querySelector('[data-testid="stStatusWidget"]')"""
_INTRO_STATE_JS = """(id) => {
  const host = document.getElementById(id);
  if (!host) return "none";
  if (getComputedStyle(host).display === "none") return "hidden";
  const detail = host.shadowRoot && host.shadowRoot.querySelector(".btn.detail");
  return detail && !detail.disabled ? "ready" : "waiting";
}"""
_LISTBOX_OPEN_JS = """() => !!document.querySelector('[role="listbox"]')"""
# 펼친 목록의 선택지 수. 긴 목록은 그린 것만 DOM 에 있어(가상화) 굴리며 센다. 글자는 밖으로
# 내지 않는다.
_COUNT_OPTIONS_JS = """async () => {
  const box = document.querySelector('[role="listbox"]');
  if (!box) return 0;
  const seen = new Set();
  const read = () => box.querySelectorAll('[role="option"]')
    .forEach((o) => seen.add(o.textContent));
  const scroller = [box, ...box.querySelectorAll("*")]
    .find((e) => e.scrollHeight > e.clientHeight + 1);
  read();
  if (scroller) {
    for (let step = 0; step < 200; step += 1) {
      const before = scroller.scrollTop;
      scroller.scrollTop += Math.max(40, scroller.clientHeight * 0.6);
      await new Promise((r) => setTimeout(r, 120));
      read();
      if (scroller.scrollTop === before) break;
    }
    scroller.scrollTop = 0;
  }
  return seen.size;
}"""
# 데이터 편집기·표(Glide)의 머리 칸. 그린 칸만 DOM 에 있어 가로로 굴리며 찾는다.
_FIND_COLUMN_JS = """async (root, header) => {
  const wanted = header.replace(/\\s+/g, " ").trim();
  const find = () => {
    const cell = [...root.querySelectorAll('[role="columnheader"]')].find(
      (h) => h.textContent.replace(/\\s+/g, " ").trim() === wanted);
    return cell ? Number(cell.getAttribute("aria-colindex")) : null;
  };
  let found = find();
  const scroller = root.querySelector(".dvn-scroller");
  if (found !== null || !scroller) return found;
  scroller.scrollLeft = 0;
  await new Promise((r) => setTimeout(r, 250));
  for (let step = 0; step < 200; step += 1) {
    found = find();
    if (found !== null) return found;
    const before = scroller.scrollLeft;
    scroller.scrollLeft += Math.max(80, scroller.clientWidth * 0.5);
    await new Promise((r) => setTimeout(r, 250));
    if (scroller.scrollLeft === before) return find();
  }
  return null;
}"""
# 표의 행을 위에서 아래로 굴리며 읽는다. 지금 가로 위치에 그려진 칸만 읽힌다 — 먼 칸은
# `column_index` 가 굴려 둔 뒤 부른다.
_GRID_ROWS_JS = """async (root, columns) => {
  const scroller = root.querySelector(".dvn-scroller");
  const rows = new Map();
  const read = () => root.querySelectorAll('[role="row"]').forEach((row) => {
    const cells = {};
    row.querySelectorAll('[role="gridcell"]').forEach((c) => {
      cells[c.getAttribute("aria-colindex")] = c.textContent.trim();
    });
    if (Object.keys(cells).length) {
      const picked = columns.map((i) => cells[String(i)] ?? null);
      rows.set(Number(row.getAttribute("aria-rowindex")), picked);
    }
  });
  if (scroller) scroller.scrollTop = 0;
  await new Promise((r) => setTimeout(r, 250));
  read();
  if (scroller) {
    for (let step = 0; step < 2000; step += 1) {
      const before = scroller.scrollTop;
      scroller.scrollTop += Math.max(60, scroller.clientHeight * 0.6);
      await new Promise((r) => setTimeout(r, 250));
      read();
      if (scroller.scrollTop === before) break;
    }
    scroller.scrollTop = 0;
  }
  return [...rows.entries()].sort((a, b) => a[0] - b[0]).map((e) => e[1]);
}"""


def _css_string(value: str) -> str:
    """CSS 속성 선택자의 따옴표 값. 한글을 `\\uXXXX` 로 바꾸면 CSS 는 그것을 못 읽는다."""
    return json.dumps(value, ensure_ascii=False)


def _overlay_closed(state: str) -> bool:
    """입장 화면·Summary 덮개가 걷혔는가(호스트가 숨었거나 아직 없다)."""
    return state in ("hidden", "none")


class Screen:
    """항목 함수가 쓰는 공통 뼈대. Playwright 페이지(`page`)를 감싼다.

    한 브라우저 세션 안에서 사이드바 링크로 옮겨 다닌다 — 주소로 가면 세션이 새로 서서 입장 화면을
    다시 넘겨야 한다.
    """

    def __init__(self, page: Any, base_url: str, *, shots: Path | None = None) -> None:
        self.page = page
        self.base_url = base_url
        self.shots = shots

    # -- 기다림

    def js(self, script: str, arg: object = None) -> Any:
        return self.page.evaluate(script, arg)

    def poll(
        self,
        read: Callable[[], Any],
        *,
        timeout: float,
        accept: Callable[[Any], bool] = bool,
        every: float = 0.25,
    ) -> Any:
        """`read()` 가 `accept` 를 넘을 때까지 읽는다. 시간이 다 되면 마지막 값을 돌려준다."""
        deadline = time.monotonic() + timeout
        while True:
            value = read()
            if accept(value) or time.monotonic() >= deadline:
                return value
            time.sleep(every)

    def wait_for(
        self, read: Callable[[], Any], *, timeout: float, accept: Callable[[Any], bool] = bool
    ) -> Any:
        """`poll` 과 같되 시간이 다 되면 `TimeoutError`."""
        value = self.poll(read, timeout=timeout, accept=accept)
        if not accept(value):
            raise TimeoutError("기다린 화면이 서지 않았다")
        return value

    def wait_stable(self, read: Callable[[], Any], *, timeout: float = 15.0) -> Any:
        """같은 값이 세 번 이어 읽힐 때까지(움직임이 끝날 때까지) 읽는다."""
        deadline = time.monotonic() + timeout
        last: Any = None
        same = 0
        while time.monotonic() < deadline:
            value = read()
            same = same + 1 if value == last and value is not None else 0
            if same >= 2:
                return value
            last = value
            time.sleep(0.25)
        raise TimeoutError("화면이 멈추지 않았다")

    def wait_idle(self, timeout: float = 90.0) -> None:
        """Streamlit 이 다 돌 때까지. 도는 표시가 1초 동안 없으면 끝난 것으로 본다."""
        time.sleep(0.3)
        deadline = time.monotonic() + timeout
        quiet = 0
        while time.monotonic() < deadline:
            quiet = 0 if self.js(_RUNNING_JS) else quiet + 1
            if quiet >= 4:
                return
            time.sleep(0.25)
        raise TimeoutError("앱이 계속 도는 중")

    # -- 입장·정리

    def intro_state(self) -> str:
        return str(self.js(_INTRO_STATE_JS, INTRO_HOST_ID))

    def _intro_state_through_reload(self) -> str:
        """첫 방문의 테마 스크립트가 화면을 한 번 새로 읽는다(`theme_toggle` 의 새로고침 표지).
        그 사이 `evaluate` 는 「실행 문맥이 사라졌다」로 끝나므로 그때는 「아직」으로 읽는다."""
        try:
            return self.intro_state()
        except Exception:  # noqa: BLE001 — 새로 읽는 중이다. 다음 회차에 다시 읽는다
            return "reloading"

    def enter(self, timeout: float = INTRO_TIMEOUT_SECONDS) -> float:
        """첫 화면을 열고 입장 화면의 `Detail` 로 들어간다. 걸린 초."""
        began = time.monotonic()
        try:
            self.page.goto(self.base_url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except Exception:  # noqa: BLE001 — 첫 방문 새로고침이 이동을 끊을 수 있다. 아래가 기다린다
            pass
        # 같은 탭에서 이미 들어갔거나(세션 저장소의 표지) 입장 화면이 실패해 스스로 걷히면 덮개는
        # 숨은 채로 남는다 — 그때는 누를 것 없이 들어간 것이다.
        state = self.wait_for(
            self._intro_state_through_reload,
            timeout=timeout,
            accept=lambda state: state in ("ready", "hidden"),
        )
        if state == "hidden":
            # 숨은 채 생겨 곧 서는 호스트와 가르려고 잠깐 더 본다.
            state = self.poll(self.intro_state, timeout=2, accept=lambda state: state == "ready")
        if state == "ready":
            self.page.locator(f"#{INTRO_HOST_ID} .btn.detail").click()
        self.wait_for(self.intro_state, timeout=30, accept=_overlay_closed)
        self.wait_idle()
        return time.monotonic() - began

    def close_overlay(self) -> None:
        """Summary 덮개가 열려 있으면 닫는다. 여는 움직임 중에는 `Esc` 를 놓칠 수 있어 몇 번
        누르고, 그래도 서 있으면 머리 줄의 `Detail` 을 누른다(둘 다 같은 일을 한다)."""
        for _ in range(3):
            if _overlay_closed(self.intro_state()):
                return
            self.page.keyboard.press("Escape")
            if _overlay_closed(self.poll(self.intro_state, timeout=3, accept=_overlay_closed)):
                return
        detail = self.page.locator(f"#{INTRO_HOST_ID} .btn.detail")
        if detail.count() and detail.first.is_enabled():
            detail.first.click()
        self.wait_for(self.intro_state, timeout=15, accept=_overlay_closed)

    def settle(self) -> None:
        """항목 사이 정리 — 덮개와 펼친 목록을 닫는다. 앞 항목이 중간에 끊겨도 다음 항목이 선다."""
        if self.js(_LISTBOX_OPEN_JS):
            self.page.keyboard.press("Escape")
        self.close_overlay()

    def shot(self, name: str) -> None:
        if self.shots is not None:
            self.page.screenshot(path=str(self.shots / f"{name}.png"))

    # -- 이동

    def open_page(self, href_suffix: str) -> None:
        """사이드바 링크로 간다. 접힌 묶음(`details`) 안이면 묶음 머리부터 편다."""
        link = self.page.locator(f'[data-testid="stSidebar"] a[href$="{href_suffix}"]').first

        def arrived() -> bool:
            return bool(self.page.url.split("?")[0].rstrip("/").endswith(href_suffix))

        if not link.is_visible():
            link.locator("xpath=ancestor::details[1]/summary").click()
            # 펴지는 동안 누른 링크는 이동하지 않는다 — 자리가 멈출 때까지 기다린다.
            self.wait_stable(link.bounding_box, timeout=10)
        for _ in range(3):
            link.click()
            if self.poll(arrived, timeout=10, accept=bool):
                break
        self.wait_for(arrived, timeout=5)
        self.wait_idle()

    def open_tab(self, name: str) -> None:
        """탭을 누른다. 탭 이름 앞의 아이콘 글자(`table_rows`)는 부분 일치로 넘긴다."""
        self.page.get_by_role("tab", name=name).first.click()
        self.wait_idle()

    def main_text(self) -> str:
        return str(
            self.js("""() => document.querySelector('[data-testid="stMain"]')?.innerText ?? "" """)
        )

    # -- 위젯

    def selectbox(self, label: str) -> Any:
        return self.page.locator('[data-testid="stSelectbox"]').filter(
            has=self.page.locator(f"input[aria-label={_css_string(label)}]")
        )

    def selectbox_value(self, label: str) -> str | None:
        """선택 상자에 지금 보이는 값. 상자가 없으면 None. 값은 판정에만 쓴다."""
        box = self.selectbox(label)
        if box.count() == 0:
            return None
        return str(box.first.locator("input").input_value())

    def selectbox_option_count(self, label: str) -> int:
        """펼쳐 선택지 수를 세고 `Esc` 로 닫는다. 고르지 않는다."""
        field = self.selectbox(label).first.locator("input")
        field.click()
        self.wait_for(lambda: self.js(_LISTBOX_OPEN_JS), timeout=10)
        try:
            return int(self.js(_COUNT_OPTIONS_JS))
        finally:
            self.page.keyboard.press("Escape")

    def choose_by_typing(self, label: str, text: str) -> None:
        """선택 상자에 글자를 쳐서 고른다(긴 목록은 가상화라 누를 칸이 DOM 에 없을 수 있다)."""
        field = self.selectbox(label).first.locator("input")
        field.click()
        field.type(text, delay=20)
        self.page.keyboard.press("Enter")
        self.wait_idle()

    def switch(self, label: str, on: bool) -> bool:
        """`st.toggle` 을 켜거나 끈다. 숨은 input 대신 라벨을 누른다. 스위치가 없으면 False."""
        box = self.page.locator('[data-testid="stCheckbox"]').filter(
            has=self.page.locator(f"input[aria-label={_css_string(label)}]")
        )
        if box.count() == 0:
            return False
        if bool(box.first.locator("input").is_checked()) != on:
            box.first.locator("label").first.click()
            self.wait_idle()
        return True

    # -- 표(Glide)

    def grid_with_column(self, header: str, *, timeout: float = 30.0) -> tuple[Any, int]:
        """그 머리 칸이 있는 첫 표와 그 칸의 `aria-colindex`."""

        def find() -> tuple[Any, int] | None:
            grids = self.page.locator('[data-testid="stDataFrame"], [data-testid="stDataEditor"]')
            for index in range(grids.count()):
                grid = grids.nth(index)
                column = self.column_index(grid, header)
                if column is not None:
                    return grid, column
            return None

        found = self.wait_for(find, timeout=timeout, accept=lambda value: value is not None)
        grid, column = found
        return grid, int(column)

    def column_index(self, grid: Any, header: str) -> int | None:
        value = grid.evaluate(_FIND_COLUMN_JS, header)
        return None if value is None else int(value)

    def grid_rows(self, grid: Any, columns: Sequence[int]) -> list[list[str | None]]:
        """행마다 고른 칸의 글자(머리 행 제외). 판정에만 쓰고 결과에 옮기지 않는다."""
        rows = grid.evaluate(_GRID_ROWS_JS, list(columns))
        return [[None if cell is None else str(cell) for cell in row] for row in rows]


# ---------------------------------------------------------------------------------- 항목 실행


@dataclass(frozen=True)
class Item:
    """확인 항목 하나. `run` 은 결과 칸 글자(개수·있음/없음·같음/다름·px)를 돌려준다."""

    key: str
    title: str
    run: Callable[[Screen], str]
    writes: bool = False


@dataclass(frozen=True)
class Outcome:
    item: Item
    result: str
    seconds: float = 0.0

    @property
    def recorded(self) -> bool:
        return not (self.result.startswith(UNRECORDED) or self.result == SKIPPED_NO_PERMISSION)


def unrecorded(exc: BaseException) -> str:
    """예외 종류만. 문구는 식별값을 실을 수 있어 옮기지 않는다."""
    return f"{UNRECORDED} — {type(exc).__name__}"


def run_items(
    screen: Screen,
    items: Sequence[Item],
    *,
    allow_writes: bool,
    budget_seconds: float,
    on_outcome: Callable[[Outcome], None] = lambda outcome: None,
    clock: Callable[[], float] = time.monotonic,
) -> list[Outcome]:
    """항목을 차례로 돌린다. 하나가 예외로 끝나도 나머지는 돈다."""
    began = clock()
    outcomes: list[Outcome] = []
    for number, item in enumerate(items, start=1):
        started = clock()
        if item.writes and not allow_writes:
            outcome = Outcome(item, SKIPPED_NO_PERMISSION)
        elif started - began > budget_seconds:
            outcome = Outcome(item, OVER_BUDGET)
        else:
            try:
                screen.settle()
                result = item.run(screen)
            except Exception as exc:  # noqa: BLE001 — 항목 하나의 실패가 나머지를 막지 않는다
                result = unrecorded(exc)
            try:
                screen.shot(f"{number:02d}_{item.key}")
            except Exception:  # noqa: BLE001 — 스크린샷은 덤이다
                pass
            outcome = Outcome(item, result, clock() - started)
        outcomes.append(outcome)
        on_outcome(outcome)
    return outcomes


# ---------------------------------------------------------------------------------- 결과 꼴


@dataclass
class RunFacts:
    """블록 머리 두 줄의 재료. 모두 수와 고정 글자다. 실행하며 채운다."""

    channel: str
    stamp: str
    allow_writes: bool
    ignored_other_apps: bool = False
    started_seconds: float = 0.0
    entered_seconds: float = 0.0
    elapsed_seconds: float = 0.0


def _browser_name(channel: str) -> str:
    return {"chrome": "Chrome", "msedge": "Edge"}.get(channel, "Chromium")


def _duration(seconds: float) -> str:
    whole = int(round(seconds))
    return f"{whole // 60}분 {whole % 60}초" if whole >= 60 else f"{whole}초"


def render_block(outcomes: Sequence[Outcome], *, total: int, facts: RunFacts) -> str:
    """리뷰 문서에 그대로 붙이는 블록. 끊긴 실행이면 마지막 머리 줄이 그렇게 말한다."""
    recorded = sum(outcome.recorded for outcome in outcomes)
    skipped = sum(outcome.result == SKIPPED_NO_PERMISSION for outcome in outcomes)
    missing = len(outcomes) - recorded - skipped
    state = (
        "끝까지 돎"
        if len(outcomes) == total
        else f"**중간에 끊김 — {len(outcomes)}/{total} 항목까지**"
    )
    width, height = VIEWPORT
    lines = [
        "<!-- check_deploy_screens.py — 아래 블록을 리뷰 문서 7장 화면 확인 절에 그대로 붙인다 -->",
        "",
        "### 화면 확인 (에이전트 · `check_deploy_screens.py`)",
        "",
        f"- 헤드리스 {_browser_name(facts.channel)} {width}×{height} · 별도 포트에 띄운 앱 · "
        f"{facts.stamp} · {'쓰기 허락 있음' if facts.allow_writes else '쓰기 허락 없음'}"
        f"{' · 다른 앱 무시' if facts.ignored_other_apps else ''}",
        f"- 앱 기동 {_duration(facts.started_seconds)} · "
        f"입장 화면 {_duration(facts.entered_seconds)} · "
        f"항목 {total} — 기록 {recorded} · 미기록 {missing} · 안 함 {skipped} · "
        f"걸린 시간 {_duration(facts.elapsed_seconds)} · {state}",
        "",
        "| 항목 | 쓰기 | 결과 |",
        "|---|---|---|",
    ]
    for outcome in outcomes:
        writes = "씀(지워 되돌림)" if outcome.item.writes else "없음"
        cell = outcome.result.replace("|", "/").replace("\n", " ")
        lines.append(f"| {outcome.item.title} | {writes} | {cell} |")
    return "\n".join(lines) + "\n"


def render_item_list(items: Sequence[Item]) -> str:
    lines = ["| 키 | 항목 | 쓰기 |", "|---|---|---|"]
    lines.extend(
        f"| `{item.key}` | {item.title} | {'씀' if item.writes else '없음'} |" for item in items
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------------- 확인 항목
#
# 배포마다 바뀌는 자리다. 결과 문자열은 고정 글자와 수로만 만든다 — 화면에서 읽은 이름을
# 넣지 않는다.

_TOOLBAR_POSITIONS_JS = """(ids) => ids.map((id) => {
  const e = document.getElementById(id);
  if (!e) return null;
  const r = e.getBoundingClientRect();
  return r.width > 0 ? r.x : null;
})"""
_LABEL_MARK_JS = """(id) => {
  const label = document.getElementById(id);
  const mark = label && label.querySelector("svg");
  const hint = label && label.querySelector(".capa-brand-hint");
  if (!mark || !hint) return null;
  const m = mark.getBoundingClientRect();
  const h = hint.getBoundingClientRect();
  const l = label.getBoundingClientRect();
  return {
    w: Math.round(m.width * 10) / 10, h: Math.round(m.height * 10) / 10,
    fits: hint.scrollWidth <= hint.clientWidth + 0.5 && h.right <= l.right + 0.5,
    ready: label.getAttribute("aria-disabled") !== "true",
  };
}"""
_SUMMARY_MARK_JS = """(id) => {
  const host = document.getElementById(id);
  if (!host || getComputedStyle(host).display === "none" || !host.shadowRoot) return null;
  const mark = [...host.shadowRoot.querySelectorAll(".head > .logo svg")]
    .map((s) => s.getBoundingClientRect()).find((r) => r.width > 0);
  return mark ? [Math.round(mark.width * 10) / 10, Math.round(mark.height * 10) / 10] : null;
}"""
_BOX_LEFT_JS = """(el) => el.getBoundingClientRect().x"""
# 서랍은 컴포넌트의 shadow root 안이라 `document.querySelector` 로는 닿지 않는다. Playwright
# 로케이터(`.sle-tray`, shadow 를 뚫는다)로 잡은 서랍 요소를 받아 그 root 에서 찾는다.
_TRAY_JS = """(tray) => {
  if (tray.hidden) return null;
  const names = [...tray.querySelectorAll(".sle-tray-list .sle-chip")]
    .map((chip) => (chip.querySelector(".sle-chip-name") || {}).textContent || "");
  const order = new Intl.Collator("ko", { numeric: true, sensitivity: "base" });
  let violations = 0;
  for (let i = 1; i < names.length; i += 1) {
    if (order.compare(names[i - 1], names[i]) > 0) violations += 1;
  }
  const count = (tray.querySelector(".sle-tray-count") || {}).textContent || "";
  return { chips: names.length, violations, count, first: names[0] || "" };
}"""
_TRAY_STATE_JS = """(tray) => {
  const root = tray.getRootNode();
  const search = root.querySelector(".sle-tray-search");
  const empty = root.querySelector(".sle-tray-empty");
  return {
    open: !tray.hidden,
    count: (tray.querySelector(".sle-tray-count") || {}).textContent || "",
    query: search ? search.value : null,
    empty: !!empty && !empty.hidden,
  };
}"""


def _px(size: Sequence[float]) -> str:
    return f"{size[0]:g}×{size[1]:g}px"


def check_toolbar_order(screen: Screen) -> str:
    """툴바 단추 차례 — 왼쪽부터 Guide · Print · 테마(`TOOLBAR_BUTTON_ORDER`)."""
    ids = list(TOOLBAR_BUTTON_ORDER)
    positions = screen.poll(
        lambda: screen.js(_TOOLBAR_POSITIONS_JS, ids),
        timeout=15,
        accept=lambda values: all(value is not None for value in values),
    )
    present = [(x, button) for x, button in zip(positions, ids, strict=True) if x is not None]
    if len(present) < len(ids):
        missing = [TOOLBAR_LABELS[b] for x, b in zip(positions, ids, strict=True) if x is None]
        return f"단추 {len(present)}/{len(ids)} — 없음: {', '.join(missing)}"
    order = [button for _, button in sorted(present)]
    verdict = "같음" if order == ids else "다름"
    return f"{' · '.join(TOOLBAR_LABELS[b] for b in order)} — 정한 차례와 {verdict}"


def check_sidebar_symbol(screen: Screen) -> str:
    """사이드바 `S.PKG CAPA` 라벨 심볼과 Summary 머리 줄 심볼(px), 라벨 글자가 다 보이는가."""
    side = screen.wait_for(
        lambda: screen.js(_LABEL_MARK_JS, SUMMARY_LABEL_ID),
        timeout=30,
        accept=lambda value: bool(value) and bool(value["ready"]),
    )
    screen.page.locator(f"#{SUMMARY_LABEL_ID}").click()
    try:
        summary = screen.wait_stable(lambda: screen.js(_SUMMARY_MARK_JS, INTRO_HOST_ID), timeout=30)
    finally:
        screen.close_overlay()
    side_size = (float(side["w"]), float(side["h"]))
    same = all(abs(a - b) < 0.5 for a, b in zip(side_size, summary, strict=True))
    return (
        f"사이드바 {_px(side_size)} · Summary {_px(summary)} — {'같음' if same else '다름'} · "
        f"라벨 글자 {'다 보임' if side['fits'] else '잘림'}"
    )


def check_rawdata_target(screen: Screen) -> str:
    """`가용설비 현황` RawData 의 `등록할 표` 기본값이 「설비 마스터」인가, 옛 이름이 남았는가."""
    screen.open_page(EQUIPMENT_PAGE)
    screen.open_tab("RawData")
    box = screen.selectbox("등록할 표")
    screen.poll(box.count, timeout=30, accept=lambda count: count > 0)
    value = screen.selectbox_value("등록할 표")
    if value is None:
        return "`등록할 표` 상자 없음"
    old_names = screen.main_text().count("호기 마스터")
    shown = "있음" if value == "설비 마스터" else "없음(다른 값)"
    return f"「등록할 표: 설비 마스터」 {shown} · 옛 이름 「호기 마스터」 {old_names}곳"


def check_progress_box(screen: Screen) -> str:
    """`필요단축일정` 의 `진척 비교` 상자 — 있음·값·선택지 수·자리. 고르지 않는다."""
    screen.open_page(EQUIPMENT_PAGE)
    screen.open_tab("필요단축일정")
    box = screen.selectbox("진척 비교")
    if screen.poll(box.count, timeout=60, accept=lambda count: count > 0) == 0:
        return "상자 없음"
    value = screen.selectbox_value("진척 비교")
    options = screen.selectbox_option_count("진척 비교")
    target = screen.selectbox("목표 확보율")
    if target.count() == 0:
        place = "목표 확보율 상자 없음"
    else:
        left = float(box.first.evaluate(_BOX_LEFT_JS)) < float(target.first.evaluate(_BOX_LEFT_JS))
        place = f"목표 확보율 {'왼쪽' if left else '오른쪽'}"
    current = "비교 안 함" if value == "비교 안 함" else "그 밖"
    return f"상자 있음({place}) · {current} · 선택지 {options}개"


def _number(text: str | None) -> float:
    try:
        return float(str(text).replace(",", "").strip())
    except ValueError:
        return 0.0


def check_space_drawer(screen: Screen) -> str:
    """Space 미배치 서랍 — 미배치가 가장 많은 층을 열어 대수·이름 오름차순 위반·검색(빈 알림·`Esc`).

    호기를 끌어 놓지 않고 `적용` 도 누르지 않는다. 층 이름·호기 이름은 고르는 데만 쓴다.
    """
    screen.open_page(SPACE_PAGE)
    grid, unplaced_column = screen.grid_with_column("미배치대수")
    building_column = screen.column_index(grid, "동")
    floor_column = screen.column_index(grid, "층")
    if building_column is None or floor_column is None:
        return "층 목록 표의 `동`·`층` 칸 없음"
    rows = screen.grid_rows(grid, [building_column, floor_column, unplaced_column])
    floors = [(row[0], row[1], _number(row[2])) for row in rows if row[0] and row[1]]
    candidates = [floor for floor in floors if floor[2] > 0]
    if not candidates:
        return f"미배치 없음(층 {len(floors)}개 모두 0)"
    building, floor, unplaced = max(candidates, key=lambda floor: floor[2])
    screen.choose_by_typing("층 바로 가기", f"{building} {floor}")
    if screen.selectbox_value("층 바로 가기") != f"{building} {floor}":
        raise RuntimeError("층을 열지 못했다")
    if not screen.switch("배치 편집", True):
        return f"미배치 있는 층 {len(candidates)}개 · `배치 편집` 스위치 없음"
    try:
        return _read_drawer(screen, unplaced, len(candidates))
    finally:
        _close_drawer(screen)


def _read_drawer(screen: Screen, unplaced: float, floors: int) -> str:
    tab = screen.page.locator(".sle-drawer-tab").first
    tab.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
    tab.click()
    box = screen.page.locator(".sle-tray").first
    tray = screen.wait_for(lambda: box.evaluate(_TRAY_JS), timeout=15)
    total_match = re.fullmatch(r"(\d+)대", str(tray["count"]).strip())
    total = int(total_match.group(1)) if total_match else -1
    head = (
        f"미배치 있는 층 {floors}개 · 연 층 표 {unplaced:g}대 · 서랍 {total}대 · "
        f"칩 {tray['chips']}개 오름차순 위반 {tray['violations']}"
    )
    first = str(tray["first"])
    if not first:
        return f"{head} · 검색 안 해 봄(칩 없음)"
    search = screen.page.locator(".sle-tray-search").first

    def state() -> Any:
        return box.evaluate(_TRAY_STATE_JS)

    def narrowed(value: Any) -> re.Match[str] | None:
        return re.fullmatch(r"(\d+)/(\d+)대", str(value["count"]).strip())

    def restored(value: Any) -> bool:
        return value["query"] == "" and str(value["count"]).strip() == f"{total}대"

    # 사내 요령: `fill` 은 반응이 없다 — 한 글자씩 친다.
    search.click()
    search.type(first[: min(3, len(first))], delay=40)
    found = narrowed(screen.poll(state, timeout=5, accept=lambda v: narrowed(v) is not None))
    searched = f"검색 됨({found.group(1)}/{found.group(2)}대)" if found else "검색 안 됨"
    search.press("Escape")
    cleared = restored(screen.poll(state, timeout=5, accept=restored))
    search.type("zzz", delay=40)
    empty = bool(screen.poll(state, timeout=5, accept=lambda v: bool(v["empty"]))["empty"])
    search.press("Escape")
    cleared = cleared and restored(screen.poll(state, timeout=5, accept=restored))
    return (
        f"{head} · {searched} · 빈 알림 {'있음' if empty else '없음'} · "
        f"Esc {'지움' if cleared else '안 지움'}"
    )


def _close_drawer(screen: Screen) -> None:
    """검색 칸·서랍을 비우고 `배치 편집` 을 끈다. 놓은 호기가 없으니 `처음 상태로` 는 필요 없다."""
    try:
        box = screen.page.locator(".sle-tray")
        if box.count() == 0:
            return
        current = box.first.evaluate(_TRAY_STATE_JS)
        if current["query"]:
            screen.page.locator(".sle-tray-search").first.press("Escape")
        if current["open"]:
            screen.page.locator(".sle-drawer-close").first.click()
    finally:
        screen.switch("배치 편집", False)


# 배포마다 바뀌는 확인 목록 — 항목 하나에 한 줄. 차례대로 돈다.
ITEMS: tuple[Item, ...] = (
    Item("toolbar", "툴바 단추 차례", check_toolbar_order),
    Item("symbol", "사이드바 심볼 크기", check_sidebar_symbol),
    Item("rawdata_target", "RawData 등록할 표", check_rawdata_target),
    Item("progress_box", "필요단축일정 진척 비교 상자", check_progress_box),
    Item("space_drawer", "Space 미배치 서랍", check_space_drawer),
)


# ---------------------------------------------------------------------------------- 실행


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="사내 배포 화면 확인(런북 7장). 별도 포트 앱을 헤드리스 Chrome 으로 본다."
    )
    parser.add_argument(
        "--playwright-dir",
        type=Path,
        default=None,
        help="`uv pip install --target` 로 Playwright 를 깐 저장소 밖 폴더",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="확인용 앱 포트")
    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Playwright 브라우저 채널(기본 chrome — 깔린 Chrome). 빈 글자면 내장 Chromium",
    )
    parser.add_argument(
        "--items", default=None, help="돌릴 항목 키를 쉼표로(--list 로 본다). 비우면 전부"
    )
    parser.add_argument("--list", action="store_true", help="항목 목록만 찍고 끝낸다")
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="DB 에 쓰는 항목도 돌린다(저장 뒤 지워 되돌리는 항목만 있다). 사용자 허락이 있을 때만",
    )
    parser.add_argument(
        "--output", type=Path, default=None, help="같은 블록을 이 파일에도 쓴다(저장소 밖)"
    )
    parser.add_argument(
        "--shots", type=Path, default=None, help="항목마다 스크린샷을 둘 폴더(저장소 밖)"
    )
    parser.add_argument(
        "--budget-minutes",
        type=float,
        default=DEFAULT_BUDGET_MINUTES,
        help="이 시간을 넘으면 남은 항목은 돌리지 않는다(사내 백그라운드 제한 30분)",
    )
    parser.add_argument(
        "--start-timeout", type=float, default=START_TIMEOUT_SECONDS, help="앱 기동을 기다릴 초"
    )
    parser.add_argument(
        "--ignore-other-apps",
        action="store_true",
        help=(
            "떠 있는 다른 `streamlit run app.py` 를 보지 않는다(DB 잠금은 그대로 본다). 다른 "
            "저장소의 앱이 늘 떠 있는 사외 개발 PC 용 — 쓰면 블록 머리에 「다른 앱 무시」가 찍힌다"
        ),
    )
    return parser.parse_args(argv)


def select_items(spec: str | None, items: Sequence[Item] = ITEMS) -> list[Item] | None:
    """`--items` 로 고른 항목(등록 차례). 모르는 키가 있으면 None."""
    if spec is None:
        return list(items)
    keys = [key.strip() for key in spec.split(",") if key.strip()]
    known = {item.key for item in items}
    if not keys or any(key not in known for key in keys):
        return None
    return [item for item in items if item.key in keys]


def _use_utf8_stdout() -> None:
    # Windows 콘솔 기본 코드페이지(cp949)는 이 출력의 기호를 못 쓴다.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _progress(message: str) -> None:
    """진행 줄은 stderr 로 — stdout 에는 블록만 남는다. 항목 이름과 초만 찍는다."""
    print(message, file=sys.stderr, flush=True)


@contextmanager
def open_browser(sync_api: Any, channel: str) -> Iterator[Any]:
    """헤드리스 브라우저의 새 페이지. 나갈 때 브라우저를 닫는다."""
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=channel or None, headless=True)
        try:
            context = browser.new_context(
                viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]}, locale="ko-KR"
            )
            context.set_default_timeout(ACTION_TIMEOUT_MS)
            yield context.new_page()
        finally:
            browser.close()


def preflight(args: argparse.Namespace) -> int | None:
    """띄우기 전 확인 — 사용자 앱(프로세스·DB 잠금)과 포트. 막히면 종료 코드, 아니면 None.

    사용자 앱은 끄지 않는다. 다른 사람이 쓰고 있을 수 있다(런북 7장).
    """
    if not args.ignore_other_apps:
        running = running_app_count()
        if running is None:
            _progress("프로세스를 살피지 못했습니다 — DB 잠금만 봅니다")
        elif running:
            print(DEFERRED_MESSAGE)
            return EXIT_DEFERRED
    try:
        locked = locked_databases((DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH))
    except duckdb.Error as exc:
        print(f"DB 를 열지 못했습니다 — {type(exc).__name__}")
        return EXIT_NOT_READY
    if locked:
        print(DEFERRED_MESSAGE)
        return EXIT_DEFERRED
    if port_in_use(args.port):
        print(f"포트 {args.port} 를 이미 누가 쓰고 있습니다 — --port 로 빈 포트를 줍니다")
        return EXIT_NOT_READY
    return None


def main(argv: Sequence[str] | None = None) -> int:
    _use_utf8_stdout()
    args = parse_args(argv)
    if args.list:
        print(render_item_list(ITEMS))
        return EXIT_OK
    items = select_items(args.items)
    if items is None:
        print(f"모르는 항목: {args.items} — 고를 수 있는 키: {', '.join(i.key for i in ITEMS)}")
        return EXIT_NOT_READY
    refused = refused_paths(args)
    if refused:
        print(f"저장소 안 경로는 받지 않습니다 — {', '.join(refused)} 에 저장소 밖 경로를 줍니다")
        return EXIT_NOT_READY
    sync_api = load_playwright(args.playwright_dir) if args.playwright_dir is not None else None
    if sync_api is None:
        print(INSTALL_HINT)
        return EXIT_NOT_READY
    blocked = preflight(args)
    if blocked is not None:
        return blocked
    if args.shots is not None:
        Path(args.shots).mkdir(parents=True, exist_ok=True)

    began = time.monotonic()
    facts = RunFacts(
        channel=args.channel,
        stamp=applied_stamp(),
        allow_writes=args.allow_writes,
        ignored_other_apps=args.ignore_other_apps,
    )
    outcomes: list[Outcome] = []

    def emit() -> str:
        """지금까지의 블록. `--output` 은 항목마다 다시 써서 중간에 끊겨도 돈 칸이 남는다."""
        facts.elapsed_seconds = time.monotonic() - began
        block = render_block(outcomes, total=len(items), facts=facts)
        if args.output is not None:
            Path(args.output).write_bytes(block.encode("utf-8"))
        return block

    def record(outcome: Outcome) -> None:
        outcomes.append(outcome)
        _progress(f"· {outcome.item.title} — {outcome.seconds:.1f}초")
        emit()

    _progress(f"확인용 앱을 포트 {args.port} 에 띄웁니다 …")
    try:
        with StreamlitApp(args.port, start_timeout=args.start_timeout) as app:
            facts.started_seconds = app.started_seconds
            _progress(f"앱이 섰습니다({app.started_seconds:.1f}초). 브라우저로 들어갑니다 …")
            try:
                with open_browser(sync_api, args.channel) as page:
                    screen = Screen(page, app.base_url, shots=args.shots)
                    facts.entered_seconds = screen.enter()
                    run_items(
                        screen,
                        items,
                        allow_writes=args.allow_writes,
                        budget_seconds=args.budget_minutes * 60,
                        on_outcome=record,
                    )
            except Exception as exc:  # noqa: BLE001 — 브라우저·입장 실패는 까닭 종류만 알린다
                print(f"브라우저로 들어가지 못했습니다 — {type(exc).__name__}")
                emit()
                return EXIT_NOT_READY
    except AppStartError as exc:
        print(f"앱이 뜨지 않았습니다 — {exc}")
        return EXIT_NOT_READY
    if not app.port_released:
        _progress(
            f"확인용 앱 프로세스가 남았을 수 있습니다 — 포트 {args.port} 가 아직 열려 있습니다"
        )
    print(emit())
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
