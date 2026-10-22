# Purpose: 따라하기 가이드를 앱 사본에서 찍어 원고 · 덮어쓰기와 한 파일 HTML 로 묶는다.

"""따라하기 가이드 생성기 — 촬영 → 조립.

    # 사외 예시판(합성 시드). 결과는 --dist 에 나오고, 사람이 저장소 자리로 복사해 커밋한다
    .venv/bin/python scripts/build_page_guide.py --example --playwright-dir <저장소 밖>/pw \\
        --work <저장소 밖>/guide_work --dist <저장소 밖>/guide_out --output <저장소 밖>/guide.md
    cp <guide_out>/lob.html static/guides/howto/lob.html
    cp <guide_out>/example/* src/capa_simulation/guides/howto/lob/example/

    # 사내판(런북 10장). 사본 트리의 스크립트로, 사본에서만 돈다
    & $py "$e2e\\scripts\\build_page_guide.py" --internal --copy-root $e2e \\
        --playwright-dir $HOME/pw --params review/guide/params.json \\
        --overrides review/guide/overrides.json --work $HOME/guide_work \\
        --dist $HOME/guide_out --output $HOME/guide.md

    # 덮어쓰기만 고쳤을 때 — 촬영 없이 다시 조립(몇 초)
    ... --internal --copy-root $e2e --assemble-only --overrides ... --work ... --dist ...

**두 모드.**

- `--example`: 이 저장소의 `git archive HEAD` 를 `--work` 아래 새 폴더에 풀고, 그 `data/` 에
  가이드 합성 시드 DB(`scripts/guide_example_seed.py`)를 만든 뒤 띄워 모든 상태를 찍는다.
  결과는 `--dist/<가이드>.html`(예시판)과 `--dist/example/`(사내가 찍지 않는 상태의 합성 그림 ·
  좌표)이다. **저장소 트리에는 쓰지 않는다** — 사외 정본 자리(`static/guides/howto/` ·
  `src/capa_simulation/guides/howto/<가이드>/example/`)로는 사람이 복사해 `git diff` 로 보고
  커밋한다. 생성기가 저장소에 쓰는 길을 두지 않으면 사내에서 잘못 돌려도 사내 저장소가 바뀌지
  않고, 출력은 모드와 상관없이 「저장소 밖만」 한 규칙이다. 작업 트리에 커밋하지 않은 앱
  변경이 있으면 알린다(사본은 HEAD 다). 쓴 앱 사본은 끝나면 지운다.
- `--internal --copy-root <사본>`: 사내. 런북 6-3 의 사본 트리에서만 돈다. 사본 폴더나 그 위에
  `.git` 이 있으면(저장소 안) 거절하고, 사본 `data/` 에 두 DB 가 있고 `.wal` 이 없어야 한다.
  계획의 쓰기 등급으로 찍을지를 가른다 — 사슬에 `db`(리비전 · 공식) · `shared`(공용 프로필)가
  있는 상태는 건너뛰고 뼈대의 합성 예시 그림으로 대신한다(`--allow-writes` 일 때만 연다 — 런북
  7장이 사본 예외를 적었을 때). `none` · `session` 만 돌았으면 사본 두 DB 의 크기 · sha256 이
  앞뒤로 같아야 한다 — 다르면 「DB 변화 있음」을 찍고 2 로 끝낸다. 「앞」은 그 `--work` 의 첫
  촬영 앞에 잰 기준 지문(`--work/db_baseline.json`)이다. 같은 `--work` 로 다시 돌면 `--states`
  여부와 상관없이 그 기준과 견주고, 찍기 전에 사본 DB 가 이미 기준과 다르면(앞 실행이 바꿨거나
  앱 오류 · 예외로 끝난 뒤) 앱을 띄우지 않고 2 로 멈춘다 — 새 사본 · 새 `--work` 로 다시 돈다.
  바뀐 DB 를 새 기준으로 삼아 「DB 변화 없음」을 내는 길을 두지 않는다. 앱 오류 · 기동 실패로
  멈출 때도 사본 DB 를 기준과 견줘 `run.json` 에 적는다.

**자리.** 앱은 `127.0.0.1` 에서만 듣는다. 포트는 `--port` 를 주지 않으면 8552 부터 빈 것을
고르고, 8501(사용자 앱) · 8551(화면 확인 기본)은 거절한다. 자식 앱 환경에서
`CAPA_AUTO_OFFICIAL_UPDATE` 를 뺀다(`check_deploy_screens.app_environment`). 앱 수명 · 프로세스
묶음(Windows Job Object · Linux `PR_SET_PDEATHSIG`) · 경로 거절은 `check_deploy_screens.py` 의
것을 그대로 쓴다.

**출력.** `--work`(중간 그림 · `shots.json` · `run.json` · 사내 `db_baseline.json`) · `--dist`(결과
HTML) · `--output`(진행 블록) · `--playwright-dir` 는 저장소 밖만 받는다(사내는 사본 밖도). stdout ·
로그 · 진행 블록에는 상태 ID · 수 · 예외 종류만 찍는다 — 화면 글자는 판정에만 쓴다. 마지막 줄은
리뷰 md 에 옮길 한 줄(`page_guide_core.review_line`)이고, 같은 줄을 점검기
(`scripts/check_page_guide.py`)가 다시 낸다.

**시간.** 15분 예산(`--budget-minutes`)을 시작부터 재고, 넘기면 남은 상태는 찍지 않고 조립한 뒤
3(미룸)으로 끝낸다 — `--states a,b` 로 남은 것만 다시 돌리면 앞 결과에 합친다. `--assemble-only`
는 촬영 없이 조립만 한다.

**종료 코드**(`check_deploy_screens.py` 와 같은 표). 0 끝까지 돎(못 찾은 표적이 있어도 — 리뷰
한 줄의 `ng`) · 2 준비 안 됨 · 멈춤(경로 · 모드 · 뼈대 · 조립 거절 · Playwright · 포트 · 사본 ·
앱 기동 · 앱 오류 화면 · 브라우저 · DB 변화 있음 · 사본 DB 가 기준 지문과 다름 · 예상 밖 예외는
종류만) · 3 미룸(예산을 넘어 남은 상태가 있음, 사본 DB 를 다른 프로세스가 쥐고 있음).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import check_deploy_screens as screens  # noqa: E402 — 자식 앱 · 경로 거절 · Playwright 읽기
import page_guide_capture as capture  # noqa: E402
import page_guide_core as core  # noqa: E402

from capa_simulation.settings import (  # noqa: E402
    APP_CONTACT_EMAIL,
    APP_OWNER_TEAM,
    DUCKDB_PATH,
    EQUIPMENT_DUCKDB_PATH,
)

EXIT_OK: Final = screens.EXIT_OK
EXIT_NOT_READY: Final = screens.EXIT_NOT_READY
EXIT_DEFERRED: Final = screens.EXIT_DEFERRED

FIRST_PORT: Final = 8552
PORT_TRIES: Final = 8
# 사용자 앱(8501)과 배포 화면 확인 기본 포트(8551)는 쓰지 않는다.
REFUSED_PORTS: Final = frozenset({8501, 8551})
DEFAULT_BUDGET_MINUTES: Final = 15.0
DATABASE_NAMES: Final = (DUCKDB_PATH.name, EQUIPMENT_DUCKDB_PATH.name)
# 사내 `--work` 의 첫 촬영 앞에 잰 사본 두 DB 지문 — 그 `--work` 로 다시 돌 때도 이것과 견준다.
BASELINE_FILE: Final = "db_baseline.json"
DB_CHANGED_MESSAGE: Final = (
    "DB 변화 있음 — 사본 DB 가 이 --work 의 첫 촬영 앞(기준 지문)과 다릅니다"
)
# 찍기 전마다 감추고, 감춘 뒤에도 남으면 찍지 않는 글 — 담당 조직 · 문의처(settings 정본).
MASK_NEEDLES: Final = (APP_OWNER_TEAM, APP_CONTACT_EMAIL)
SEED_SCRIPT: Final = Path("scripts") / "guide_example_seed.py"
SEED_TIMEOUT_SECONDS: Final = 600
# 예시판 사본이 HEAD 와 견줄 앱 자리 — 여기에 커밋하지 않은 변경이 있으면 알린다.
APP_PATHS: Final = ("app.py", "app_pages", "src", ".streamlit", "static", "config")
INSTALL_HINT: Final = screens.INSTALL_HINT

_PATH_OPTIONS: Final = (
    ("--work", "work"),
    ("--dist", "dist"),
    ("--output", "output"),
    ("--playwright-dir", "playwright_dir"),
)


def _progress(message: str) -> None:
    """진행 줄은 stderr 로 — stdout 에는 리뷰 한 줄만 남는다. ID · 수 · 종류만 찍는다."""
    print(message, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------------- 인자


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="따라하기 가이드를 앱 사본에서 찍어 한 파일 HTML 로 묶는다."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--example", action="store_true", help="사외 합성 예시판(git archive 사본)")
    mode.add_argument("--internal", action="store_true", help="사내판(런북 6-3 사본 트리에서만)")
    parser.add_argument("--copy-root", type=Path, default=None, help="--internal 의 사본 트리")
    parser.add_argument("--guide", default=core.DEFAULT_GUIDE, help="가이드 이름(기본 lob)")
    parser.add_argument("--work", type=Path, required=True, help="중간 그림 · 촬영 기록(저장소 밖)")
    parser.add_argument("--dist", type=Path, required=True, help="결과 HTML 을 둘 곳(저장소 밖)")
    parser.add_argument("--output", type=Path, default=None, help="진행 블록 파일(저장소 밖)")
    parser.add_argument("--overrides", type=Path, default=None, help="사내 덮어쓰기(--internal)")
    parser.add_argument("--params", type=Path, default=None, help="사내 매개값(--internal)")
    parser.add_argument("--playwright-dir", type=Path, default=None, help="Playwright 폴더")
    parser.add_argument("--channel", default=screens.DEFAULT_CHANNEL, help="브라우저 채널")
    parser.add_argument(
        "--no-chrome-sandbox",
        action="store_true",
        help="Chrome 을 --no-sandbox 로 띄운다(리눅스 샌드박스 안에서 돌 때만)",
    )
    parser.add_argument("--port", type=int, default=None, help="앱 포트(주지 않으면 8552 부터)")
    parser.add_argument("--states", default=None, help="찍을 상태 ID 를 쉼표로(앞 결과에 합친다)")
    parser.add_argument("--assemble-only", action="store_true", help="촬영 없이 조립만")
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="--internal 에서도 db · shared 상태를 찍는다(런북 7장이 사본 예외를 적었을 때만)",
    )
    parser.add_argument(
        "--budget-minutes", type=float, default=DEFAULT_BUDGET_MINUTES, help="시간 예산(분)"
    )
    parser.add_argument(
        "--start-timeout",
        type=float,
        default=screens.START_TIMEOUT_SECONDS,
        help="앱 기동을 기다릴 초",
    )
    return parser.parse_args(argv)


def mode_problems(args: argparse.Namespace) -> list[str]:
    """모드와 함께 쓸 수 없는 인자."""
    problems = []
    if args.internal and args.copy_root is None:
        problems.append("--internal 에는 --copy-root 가 있어야 합니다")
    if args.example and args.copy_root is not None:
        problems.append("--example 은 --copy-root 를 받지 않습니다(사본을 스스로 만든다)")
    if args.example and (args.overrides is not None or args.params is not None):
        problems.append("--example 은 사내 덮어쓰기 · 매개값을 받지 않습니다(예시판은 뼈대 그대로)")
    if args.example and args.allow_writes:
        problems.append("--allow-writes 는 --internal 에만 씁니다")
    if not args.assemble_only and args.playwright_dir is None:
        problems.append("촬영에는 --playwright-dir 가 있어야 합니다")
    if args.port is not None and args.port in REFUSED_PORTS:
        problems.append(f"포트 {args.port} 는 쓰지 않습니다(8501 사용자 앱 · 8551 화면 확인)")
    if args.budget_minutes <= 0:
        problems.append("--budget-minutes 는 0 보다 커야 합니다")
    return problems


def wanted_states(spec: str | None, skeleton: core.Skeleton) -> list[str] | None:
    """`--states` 로 고른 상태(계획 차례). 모르는 ID 가 있으면 None."""
    known = skeleton.state_ids()
    if spec is None:
        return known
    picked = [item.strip() for item in spec.split(",") if item.strip()]
    if not picked or any(item not in known for item in picked):
        return None
    return [state_id for state_id in known if state_id in picked]


# ---------------------------------------------------------------------------------- 경로


def inside_git_tree(path: Path) -> bool:
    """그 경로나 그 위 어느 폴더에 `.git` 이 있는가 — git 작업 트리 안이다."""
    resolved = path.resolve()
    return any((folder / ".git").exists() for folder in (resolved, *resolved.parents))


def refused_paths(
    args: argparse.Namespace, roots: Sequence[Path], root: Path = PROJECT_ROOT
) -> list[str]:
    """출력 · 입력 폴더 옵션을 한 번 정규화하고 거절할 옵션 이름을 돌려준다.

    `check_deploy_screens.refused_paths` 와 같은 거절(저장소 안 · 장치 · UNC · 스트림 · 하드
    링크)에 더해, `roots`(사내 사본 트리) 안과 git 작업 트리 안도 거절한다 — 사내 실화면 그림이
    어느 저장소에도 떨어지지 않게.
    """
    probe = argparse.Namespace(
        output=args.output, shots=args.work, playwright_dir=args.playwright_dir
    )
    refused = [{"--shots": "--work"}.get(flag, flag) for flag in screens.refused_paths(probe, root)]
    args.output, args.work, args.playwright_dir = probe.output, probe.shots, probe.playwright_dir
    dist_probe = argparse.Namespace(output=args.dist, shots=None, playwright_dir=None)
    if screens.refused_paths(dist_probe, root):
        refused.append("--dist")
    else:
        args.dist = dist_probe.output
    for flag, name in _PATH_OPTIONS:
        value = getattr(args, name)
        if value is None or flag in refused:
            continue
        if any(screens.inside_repository(Path(value), extra) for extra in roots):
            refused.append(flag)
        elif flag != "--playwright-dir" and inside_git_tree(Path(value)):
            refused.append(flag)
    return sorted(set(refused))


def copy_root_problems(copy_root: Path, root: Path = PROJECT_ROOT) -> list[str]:
    """사내 사본 트리가 받을 꼴인가 — 고정 글자만 돌려준다(경로는 찍지 않는다)."""
    if not copy_root.is_dir():
        return ["사본 폴더가 없습니다"]
    problems = []
    if not (copy_root / "app.py").is_file() or not (copy_root / "src" / "capa_simulation").is_dir():
        problems.append("사본이 앱 트리가 아닙니다(app.py · src/capa_simulation)")
    if inside_git_tree(copy_root):
        problems.append(
            "사본이 git 저장소 안입니다(.git) — 런북 6-3 의 git archive 사본만 받습니다"
        )
    elif screens.inside_repository(copy_root, root) and inside_git_tree(root):
        problems.append("사본이 저장소 안입니다")
    data = copy_root / "data"
    for name in DATABASE_NAMES:
        if not (data / name).is_file():
            problems.append(f"사본 DB 가 없습니다({name})")
        if (data / f"{name}.wal").exists():
            problems.append(f"사본 DB 에 .wal 이 있습니다({name}) — 런북 6-3 2) 로 다시 복사합니다")
    return problems


# ---------------------------------------------------------------------------------- DB 지문


Fingerprint = tuple[tuple[str, int, str], ...]


def db_fingerprint(data: Path) -> Fingerprint:
    """사본 두 DB 와 `.wal` 의 (이름, 크기, sha256). 없는 파일은 (이름, -1, "")."""
    rows: list[tuple[str, int, str]] = []
    for name in DATABASE_NAMES:
        for path in (data / name, data / f"{name}.wal"):
            if not path.is_file():
                rows.append((path.name, -1, ""))
                continue
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(block)
            rows.append((path.name, path.stat().st_size, digest.hexdigest()))
    return tuple(rows)


def db_verdict(before: Fingerprint, after: Fingerprint) -> str:
    """`same` | `changed` — 리뷰 한 줄의 「DB 변화 없음 · 있음」."""
    return "same" if before == after else "changed"


def load_baseline(work: Path) -> Fingerprint | None:
    """작업 폴더의 기준 지문(그 `--work` 의 첫 사내 촬영 앞에 잰 것). 없으면 None, 깨졌으면
    `ValueError` — 고쳐 쓰지 않고 멈춘다(바뀐 DB 를 새 기준으로 삼지 않게)."""
    path = work / BASELINE_FILE
    if not path.exists():
        return None
    raw = core.load_json(path)
    try:
        return tuple((str(name), int(size), str(digest)) for name, size, digest in raw["files"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(BASELINE_FILE) from exc


def save_baseline(work: Path, fingerprint: Fingerprint) -> None:
    text = json.dumps({"files": [list(row) for row in fingerprint]}, ensure_ascii=False, indent=1)
    (work / BASELINE_FILE).write_text(text + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------------- 예시판 사본


class PrepareError(RuntimeError):
    """사본 · 시드를 만들지 못했다. 문구는 고정 글자만."""


def uncommitted_app_changes(root: Path = PROJECT_ROOT) -> int:
    """앱 자리(`APP_PATHS`)에서 HEAD 와 다른 추적 파일 수 — 예시판 사본은 HEAD 다."""
    completed = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no", "--", *APP_PATHS],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return len([line for line in completed.stdout.splitlines() if line.strip()])


def make_example_copy(work: Path, root: Path = PROJECT_ROOT) -> Path:
    """`git archive HEAD` 를 `work/app-<시각>` 에 푼다(추적 파일만 — `data/` 는 빈 자리)."""
    completed = subprocess.run(
        ["git", "-C", str(root), "archive", "--format=zip", "HEAD"],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise PrepareError("git archive 를 만들지 못했습니다(--example 은 git 저장소에서만)")
    target = work / f"app-{time.strftime('%Y%m%d%H%M%S')}"
    with zipfile.ZipFile(io.BytesIO(completed.stdout)) as bundle:
        bundle.extractall(target)
    return target


def seed_example(copy_root: Path) -> None:
    """사본의 시드 스크립트로 사본 `data/` 에 합성 시드 DB 를 만든다(사본 코드 · 사본 경로)."""
    script = copy_root / SEED_SCRIPT
    if not script.is_file():
        raise PrepareError("사본에 예시판 시드 스크립트가 없습니다")
    completed = subprocess.run(
        [sys.executable, str(script), "--out", str(copy_root / "data" / DUCKDB_PATH.name)],
        cwd=str(copy_root),
        env=screens.app_environment(copy_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=SEED_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        raise PrepareError(f"합성 시드를 만들지 못했습니다(종료 코드 {completed.returncode})")


def choose_port(
    requested: int | None, in_use: Callable[[int], bool] = screens.port_in_use
) -> int | None:
    """쓸 포트. 준 포트가 쓰이고 있으면 None, 주지 않았으면 8552 부터 빈 것."""
    if requested is not None:
        return None if requested in REFUSED_PORTS or in_use(requested) else requested
    for port in range(FIRST_PORT, FIRST_PORT + PORT_TRIES):
        if port not in REFUSED_PORTS and not in_use(port):
            return port
    return None


# ---------------------------------------------------------------------------------- 진행 블록


@dataclass
class Progress:
    """`--output` 진행 블록 — 상태 ID · 결과 · 표적 수 · 초만."""

    path: Path | None
    title: str
    rows: list[capture.StateOutcome] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    line: str | None = None
    status: str = "시작 — 아직 상태 없음"
    failed: bool = False

    def add(self, outcome: capture.StateOutcome) -> None:
        self.rows.append(outcome)
        word = {"captured": "찍음", "skipped": "건너뜀(쓰기 등급)", "left": "남음(예산)"}
        result = word.get(outcome.result, f"실패 {outcome.failure}")
        found = f"{outcome.found}/{outcome.total}" if outcome.result == "captured" else "—"
        _progress(f"· {outcome.state_id} {result} · 표적 {found} · {outcome.seconds:.1f}초")
        self.write()

    def note(self, line: str) -> None:
        self.notes.append(line)
        self.write()

    def stop(self, status: str) -> None:
        """끝난 꼴(끝 · 미룸 · 멈춤)을 머리 줄에 적는다."""
        self.status = status
        self.write()

    def render(self) -> str:
        counts = {key: 0 for key in ("captured", "failed", "skipped", "left")}
        for row in self.rows:
            counts[row.result] += 1
        lines = [
            f"## {self.title}",
            "",
            f"- {self.status}",
            f"- 찍음 {counts['captured']} · 실패 {counts['failed']} · "
            f"건너뜀 {counts['skipped']} · 남음 {counts['left']}",
            *[f"- {note}" for note in self.notes],
            "",
        ]
        if self.rows:
            lines += ["| 상태 | 결과 | 표적 | 초 |", "|---|---|---|---|"]
            for row in self.rows:
                result = {"captured": "찍음", "skipped": "건너뜀", "left": "남음"}.get(
                    row.result, f"실패 `{row.failure}`"
                )
                found = f"{row.found}/{row.total}" if row.result == "captured" else "—"
                lines.append(f"| `{row.state_id}` | {result} | {found} | {row.seconds:.1f} |")
            lines.append("")
        if self.line is not None:
            lines += ["리뷰 한 줄:", "", "```text", self.line, "```", ""]
        return "\n".join(lines)

    def write(self) -> None:
        if self.path is None or self.failed:
            return
        try:
            self.path.write_bytes(self.render().encode("utf-8"))
        except OSError as exc:
            self.failed = True
            _progress(f"--output 에 쓰지 못했습니다 — {type(exc).__name__}")


# ---------------------------------------------------------------------------------- 실행


@dataclass
class Inputs:
    skeleton: core.Skeleton
    content: dict[str, Any]
    overrides: core.OverrideReport
    params: dict[str, str | int]
    param_report: core.ParamReport


def read_inputs(args: argparse.Namespace) -> Inputs:
    """뼈대 · 덮어쓰기 · 매개값을 읽고 검사한다. 받을 수 없으면 `GuideInputError`."""
    skeleton = core.load_skeleton(args.guide)
    broken = core.skeleton_problems(skeleton)
    if broken:
        raise core.GuideInputError("뼈대가 깨졌습니다(사외 정본)", broken)
    override_doc = core.load_json(args.overrides) if args.overrides is not None else None
    param_doc = core.load_json(args.params) if args.params is not None else None
    content, report = core.apply_overrides(skeleton.content, override_doc, version=skeleton.version)
    params, param_report = core.resolve_params(skeleton.plan, param_doc)
    return Inputs(skeleton, content, report, params, param_report)


@contextmanager
def open_browser(sync_api: Any, channel: str, no_sandbox: bool) -> Iterator[Any]:
    with sync_api.sync_playwright() as playwright:
        launch_args = ["--hide-scrollbars"] + (["--no-sandbox"] if no_sandbox else [])
        browser = playwright.chromium.launch(
            channel=channel or None, headless=True, args=launch_args
        )
        try:
            yield browser
        finally:
            browser.close()


def assemble_to_dist(inputs: Inputs, args: argparse.Namespace) -> core.AssemblyReport:
    """작업 폴더의 촬영 결과로 `--dist/<가이드>.html` 을 쓴다(예시판은 `example/` 도)."""
    skeleton = inputs.skeleton
    shots, _run = core.board_shots(skeleton, args.work)
    data, report = core.assemble(inputs.content, shots)
    template = (core.HOWTO_DIR / "template.html").read_text(encoding="utf-8")
    html = core.render_html(template, data)
    args.dist.mkdir(parents=True, exist_ok=True)
    (args.dist / f"{skeleton.name}.html").write_bytes(html.encode("utf-8"))
    if args.example:
        substitute = [sid for sid in skeleton.state_ids() if not skeleton.read_only(sid)]
        exported = core.export_examples(shots, substitute, args.dist / core.EXAMPLE_DIR)
        _progress(f"예시 그림 {len(exported)}/{len(substitute)}장을 내보냈습니다")
    _progress(f"조립 — 그림 {report.images}장 · 그림 없는 자리 {len(report.no_picture)}")
    return report


def run(argv: Sequence[str] | None = None) -> int:
    began = time.monotonic()
    args = parse_args(argv)
    problems = mode_problems(args)
    if problems:
        for problem in problems:
            print(problem)
        return EXIT_NOT_READY
    roots: list[Path] = []
    if args.internal:
        args.copy_root = args.copy_root.expanduser().resolve()
        roots.append(args.copy_root)
    refused = refused_paths(args, roots)
    if refused:
        print(
            "저장소 · 사본 · git 작업 트리 안이거나 장치 · UNC · 스트림 · 하드 링크 경로라 받지 "
            f"않습니다 — {', '.join(refused)} 에 그 밖의 드라이브 경로를 줍니다"
        )
        return EXIT_NOT_READY
    if args.internal:
        copy_problems = copy_root_problems(args.copy_root)
        if copy_problems:
            for problem in copy_problems:
                print(problem)
            return EXIT_NOT_READY
    try:
        inputs = read_inputs(args)
    except core.GuideInputError as exc:
        print(str(exc))
        for problem in exc.problems:
            _progress(f"  {problem}")
        return EXIT_NOT_READY
    except (OSError, ValueError) as exc:
        print(f"덮어쓰기 · 매개값을 읽지 못했습니다 — {type(exc).__name__}")
        return EXIT_NOT_READY
    try:
        for folder in (args.work, args.dist, *([args.output.parent] if args.output else [])):
            folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"출력 폴더를 만들지 못했습니다 — {type(exc).__name__}")
        return EXIT_NOT_READY
    mode = "internal" if args.internal else "example"
    progress = Progress(
        args.output,
        f"따라하기 가이드 — {core.compact_version(inputs.skeleton.version)} · "
        f"{'사내' if args.internal else '예시'}",
    )
    progress.write()
    if args.assemble_only and not (args.work / core.SHOTS_FILE).exists():
        print("작업 폴더에 촬영 결과(shots.json)가 없습니다 — 먼저 촬영합니다")
        progress.stop("멈춤 — 촬영 결과 없음")
        return EXIT_NOT_READY
    try:
        code = (
            EXIT_OK if args.assemble_only else capture_states(args, inputs, mode, progress, began)
        )
        if code == EXIT_NOT_READY:
            if progress.status.startswith("시작"):
                progress.stop("멈춤")
            return code
        if not (args.work / core.SHOTS_FILE).exists():
            return code  # 미뤄 한 장도 찍지 않았다 — 조립할 것이 없다
        assemble_to_dist(inputs, args)
        line, details = core.review_for_work(
            inputs.skeleton, inputs.content, args.work, inputs.overrides, inputs.param_report
        )
    except core.GuideInputError as exc:
        print(str(exc))
        progress.stop(f"멈춤 — {exc}")
        return EXIT_NOT_READY
    except Exception as exc:  # noqa: BLE001 — 문구 대신 종류만
        print(f"예상 밖 오류로 멈췄습니다 — {type(exc).__name__}")
        progress.stop(f"멈춤 — 예상 밖 오류({type(exc).__name__})")
        return EXIT_NOT_READY
    for detail in details:
        _progress(f"  {detail}")
    progress.line = line
    print(line)
    run_facts = core.load_run(args.work)
    if run_facts.db == "changed":
        print(DB_CHANGED_MESSAGE)
        progress.stop("멈춤 — DB 변화 있음")
        return EXIT_NOT_READY
    if code == EXIT_DEFERRED:
        progress.stop("미룸 — 남은 상태는 --states 로")
    else:
        progress.stop("끝 — 조립만" if args.assemble_only else "끝")
    return code


def internal_baseline(
    args: argparse.Namespace, data: Path, progress: Progress
) -> Fingerprint | None:
    """사내 촬영의 기준 지문. 이 `--work` 의 첫 촬영이면 지금 사본 DB 를 재 적고, 이미 적혀
    있으면 지금 사본이 그것과 같아야 한다(`--states` 여부와 상관없이). 다르면 앞 실행이 사본을
    바꿨거나(앱 오류 · 예외로 끝난 뒤 포함) 다른 사본이다 — `run.json` 에 「DB 변화 있음」을 적고
    멈춘다(None). `--allow-writes` 는 쓰기를 허락한 실행이라 다름을 멈추지 않는다(판정은
    `writes`)."""
    try:
        current = db_fingerprint(data)
        baseline = load_baseline(args.work)
        if baseline is None:
            save_baseline(args.work, current)
            return current
        if baseline == current or args.allow_writes:
            return baseline
        if (args.work / core.RUN_FILE).exists():
            facts = core.load_run(args.work)
            facts.db = "changed"
            core.save_run(facts, args.work)
    except (OSError, ValueError) as exc:
        print(f"사본 DB 기준 지문을 읽거나 적지 못했습니다 — {type(exc).__name__}")
        progress.stop("멈춤 — 기준 지문을 읽거나 적지 못함")
        return None
    print(
        "사본 DB 가 이 --work 의 첫 촬영 앞(기준 지문)과 다릅니다 — 앞 실행이 사본을 바꿨거나 "
        "다른 사본입니다. 새 사본(런북 6-3) · 새 --work 로 다시 돌립니다"
    )
    progress.note(core.DB_WORDS["changed"])
    progress.stop("멈춤 — 사본 DB 가 기준 지문과 다름")
    return None


def capture_states(
    args: argparse.Namespace, inputs: Inputs, mode: str, progress: Progress, began: float
) -> int:
    """촬영 — 상태를 찍어 `--work` 에 합치고 `run.json` 을 쓴다. 종료 코드를 돌려준다."""
    skeleton = inputs.skeleton
    wanted = wanted_states(args.states, skeleton)
    if wanted is None:
        print(f"모르는 상태: {args.states} — 계획의 상태 ID 를 줍니다")
        return EXIT_NOT_READY
    skip = (
        []
        if (args.example or args.allow_writes)
        else [sid for sid in wanted if not skeleton.read_only(sid)]
    )
    sync_api = screens.load_playwright(args.playwright_dir)
    if sync_api is None:
        print(INSTALL_HINT)
        progress.stop("멈춤 — Playwright 없음")
        return EXIT_NOT_READY
    previous: core.ShotSet | None = None
    previous_run: core.RunFacts | None = None
    if (args.work / core.SHOTS_FILE).exists():
        previous = core.load_shots(args.work)
        previous_run = core.load_run(args.work)
        if previous.version != skeleton.version or previous.mode != mode:
            print("작업 폴더의 앞 결과가 다른 뼈대 판 · 모드입니다 — 새 --work 를 줍니다")
            return EXIT_NOT_READY
        if args.states is None:
            previous = None  # 전부 다시 찍는다 — 앞 결과에 합치는 것은 --states 일 때만
            previous_run = None

    app_root: Path
    example_copy: Path | None = None
    baseline: Fingerprint | None = None
    if args.example:
        changed = uncommitted_app_changes()
        if changed:
            progress.note(f"알림 — 커밋하지 않은 앱 변경 {changed}파일(사본은 HEAD)")
        try:
            example_copy = make_example_copy(args.work)
            seed_example(example_copy)
        except (PrepareError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
            reason = str(exc) if isinstance(exc, PrepareError) else type(exc).__name__
            print(f"예시판 사본을 만들지 못했습니다 — {reason}")
            if example_copy is not None:
                shutil.rmtree(example_copy, ignore_errors=True)
            return EXIT_NOT_READY
        app_root = example_copy
    else:
        app_root = args.copy_root
        data = app_root / "data"
        try:
            locked = screens.locked_databases([data / name for name in DATABASE_NAMES])
        except Exception as exc:  # noqa: BLE001 — 종류만
            print(f"사본 DB 를 열지 못했습니다 — {type(exc).__name__}")
            return EXIT_NOT_READY
        if locked:
            print("사본 DB 를 다른 프로세스가 쥐고 있습니다 — 사본 앱을 끈 뒤 다시 돌립니다")
            progress.stop("미룸 — 사본 DB 를 다른 프로세스가 쥐고 있음")
            return EXIT_DEFERRED
        baseline = internal_baseline(args, data, progress)
        if baseline is None:
            return EXIT_NOT_READY

    try:
        return _shoot(
            args,
            inputs,
            mode,
            progress,
            began,
            sync_api,
            app_root,
            wanted,
            skip,
            previous,
            previous_run,
            baseline,
        )
    finally:
        if example_copy is not None:
            shutil.rmtree(example_copy, ignore_errors=True)


def _shoot(
    args: argparse.Namespace,
    inputs: Inputs,
    mode: str,
    progress: Progress,
    began: float,
    sync_api: Any,
    app_root: Path,
    wanted: list[str],
    skip: list[str],
    previous: core.ShotSet | None,
    previous_run: core.RunFacts | None,
    baseline: Fingerprint | None,
) -> int:
    skeleton = inputs.skeleton
    port = choose_port(args.port)
    if port is None:
        print("빈 포트가 없습니다 — --port 로 빈 포트를 줍니다(8501 · 8551 제외)")
        progress.stop("멈춤 — 빈 포트 없음")
        return EXIT_NOT_READY
    data = app_root / "data"
    viewport_spec: Mapping[str, Any] = skeleton.plan["viewport"]
    fresh = core.ShotSet(
        viewport=(int(viewport_spec["width"]), int(viewport_spec["height"])),
        scale=float(viewport_spec["scale"]),
        mode=mode,
        version=skeleton.version,
    )
    run_facts = core.RunFacts(mode=mode, version=skeleton.version, allow_writes=args.allow_writes)
    shots_folder = args.work / "shots"
    deadline = began + args.budget_minutes * 60

    def save() -> None:
        merged = fresh if previous is None else core.merge_shots(previous, fresh)
        core.save_shots(merged, args.work)
        facts = run_facts if previous_run is None else core.merge_runs(previous_run, run_facts)
        core.save_run(facts, args.work)

    def judge_db() -> None:
        """이 실행의 DB 판정 — 사내는 사본 DB 를 그 `--work` 의 기준 지문과 견준다."""
        if mode == "example":
            run_facts.db = "example"
        elif args.allow_writes:
            run_facts.db = "writes"
        else:
            assert baseline is not None
            run_facts.db = db_verdict(baseline, db_fingerprint(data))

    def judge_db_on_stop() -> None:
        """멈추는 길(앱 기동 실패 · 앱 오류 · 예상 밖 예외)에서도 사본 DB 를 견줘 `run.json` 에
        적는다 — 그 `--work` 로 조립 · 점검기를 돌려도 「DB 안 봄」이 아니라 사실이 나온다."""
        if mode != "internal":
            return
        try:
            judge_db()
            facts = run_facts if previous_run is None else core.merge_runs(previous_run, run_facts)
            core.save_run(facts, args.work)
        except OSError as exc:
            _progress(f"멈춘 뒤 사본 DB 를 견주지 못했습니다 — {type(exc).__name__}")
            return
        if run_facts.db == "changed":
            print(DB_CHANGED_MESSAGE)
            progress.note(core.DB_WORDS["changed"])

    def on_state(outcome: capture.StateOutcome, shot: core.ShotState | None) -> None:
        if outcome.result == "skipped":
            run_facts.skipped.append(outcome.state_id)
        elif outcome.result == "left":
            run_facts.left.append(outcome.state_id)
        elif shot is not None:
            fresh.states[outcome.state_id] = shot
        progress.add(outcome)
        save()

    to_shoot = [sid for sid in wanted if sid not in skip]
    code = EXIT_OK
    if to_shoot:
        _progress(f"앱을 {screens.APP_ADDRESS}:{port} 에 띄웁니다 …")
        app_paths = (data / DUCKDB_PATH.name, data / EQUIPMENT_DUCKDB_PATH.name)
        try:
            with screens.StreamlitApp(
                port, root=app_root, expected_paths=app_paths, start_timeout=args.start_timeout
            ) as app:
                progress.note(f"앱 기동 {app.started_seconds:.1f}초")
                with open_browser(sync_api, args.channel, args.no_chrome_sandbox) as browser:
                    camera = capture.Camera(
                        browser,
                        app.base_url,
                        viewport=fresh.viewport,
                        scale=fresh.scale,
                        mask=list(skeleton.plan["mask"]),
                        needles=MASK_NEEDLES,
                    )
                    try:
                        capture.run_states(
                            camera,
                            skeleton,
                            inputs.params,
                            wanted=wanted,
                            skip=skip,
                            deadline=deadline,
                            folder=shots_folder,
                            on_state=on_state,
                        )
                    finally:
                        camera.close()
        except screens.AppStartError as exc:
            print(f"앱이 뜨지 않았습니다 — {exc}")
            judge_db_on_stop()
            progress.stop(f"멈춤 — 앱이 뜨지 않았습니다: {exc}")
            return EXIT_NOT_READY
        except capture.AppProblem:
            print("앱이 오류 화면입니다 — 상태를 찍지 않습니다")
            judge_db_on_stop()
            progress.stop("멈춤 — 앱 오류 화면")
            return EXIT_NOT_READY
        except Exception:
            judge_db_on_stop()
            raise
    else:
        for sid in wanted:
            on_state(
                capture.StateOutcome(sid, "skipped", total=len(skeleton.target_names(sid))), None
            )

    judge_db()
    save()
    progress.note(core.DB_WORDS.get(run_facts.db, core.DB_WORDS["unchecked"]))
    if run_facts.left:
        progress.note(f"미룸 — 예산을 넘어 남은 상태 {len(run_facts.left)}(--states 로 이어 돈다)")
        code = EXIT_DEFERRED
    return code


def main(argv: Sequence[str] | None = None) -> int:
    """종료 코드 — 0 끝 · 2 준비 안 됨 · 멈춤 · 3 미룸. 예상 밖 예외는 종류만 찍고 2."""
    screens._use_utf8_stdout()
    try:
        return run(argv)
    except Exception as exc:  # noqa: BLE001 — 문구 대신 종류만
        print(f"예상 밖 오류로 멈췄습니다 — {type(exc).__name__}")
        return EXIT_NOT_READY


if __name__ == "__main__":
    raise SystemExit(main())
