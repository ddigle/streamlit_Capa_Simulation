# Purpose: 사내에서 배포 ZIP 을 송장대로 검증하고 지우고 풀어 적용한 뒤 커밋한다.
"""사내 배포 적용기.

**사내에서 돌리는 물건인데 사외에서 만든다.** 처음 한 번은 사람이 사내에 옮겨 두어야 하고,
그 뒤로는 ZIP 에 실려 스스로 갱신된다.

왜 손으로 덮어쓰지 않는가
--------------------------
「덮어쓰기」는 파일을 더하고 바꿀 뿐 **지우지 않는다.** 사외에서 지운 모듈이 사내에 남으면
트리를 훑는 검사(`test_documentation_inventory`·`test_source_metadata`)가 **사내에서만**
깨지고, 사내는 그것을 진짜 결함으로 보고 리뷰에 적는다. 사외에서는 재현되지 않는다.

그래서 **추적 파일을 먼저 지우고** 푼다. 지우는 대상은 `git ls-files` 가 준 것뿐이라
무시된 파일(사내 DuckDB·`data/` 실데이터)은 손대지 않는다 — `git clean -x` 를 쓰지 않는
이유가 이것이다. 한 글자 차이로 사내 데이터가 날아간다.

되돌리기
--------
이 스크립트는 인덱스를 건드리지 않는다. 중간에 실패하면 `git checkout -- .` 한 번으로
지운 파일이 전부 돌아온다. 실패할 때 그 문장을 출력한다.

사용:

    uv run python scripts/apply_deploy_package.py <내려받은 ZIP 경로>
    uv run python scripts/apply_deploy_package.py <ZIP> --dry-run
    uv run python scripts/apply_deploy_package.py <ZIP> --reconcile-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MANIFEST_NAME = "DEPLOY_MANIFEST.json"
SUPPORTED_MANIFEST_VERSIONS = (1,)

# 사내가 만든 것. 배포가 지우지도 덮지도 않는다.
PRESERVED_PREFIXES: tuple[str, ...] = ("review/", ".deploy/", ".claude/")
# 적용 이력. **두 저장소는 히스토리가 달라 커밋 조상 관계를 볼 수 없으므로**, 무엇을 어디까지
# 적용했는지 사내가 스스로 적어 둔다. 보존 목록 안에 있어 배포가 지우지 않는다.
STATE_PATH = ".deploy/applied.json"

# **무슨 일이 있어도 지우지 않는 것.** 아래 `plan_removals` 는 「사외에서 없어진 파일」을
# 추적 목록으로 가리는데, 그 전제는 운영 데이터가 `.gitignore` 에 걸려 추적되지 않는다는
# 것이다. 사내에서 그 규칙이 지워졌거나 파일이 먼저 커밋돼 버리면 전제가 깨지고, 배포가
# 운영 DB 를 지운다. 되돌릴 수 없는 종류라 전제에 기대지 않고 여기서 한 번 더 막는다.
NEVER_REMOVE_SUFFIXES: tuple[str, ...] = (
    ".duckdb",
    ".db",
    ".wal",
    ".sync.json",
    ".xlsb",
    ".xlsx",
    ".xlsm",
)
# **전부 소문자로 적는다** — 대조가 `lower()` 를 거친다. 대문자를 섞어 적으면 그 항목만
# 조용히 아무것도 막지 않는다.
NEVER_REMOVE_NAMES: tuple[str, ...] = (".env", "secrets.toml")
NEVER_REMOVE_PREFIXES: tuple[str, ...] = ("data/input/", "data/output/", "data/temp/")


class ApplyError(RuntimeError):
    """멈춰야 하는 상황. 메시지를 그대로 사람에게 보여 준다."""


# ---------- git ----------


def git(root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and completed.returncode != 0:
        raise ApplyError(f"git {' '.join(args)} 실패: {completed.stderr.strip()}")
    return completed.stdout.strip()


def tracked_files(root: Path) -> list[str]:
    listed = git(root, "ls-files")
    return [line.strip() for line in listed.splitlines() if line.strip()]


def untracked_files(root: Path) -> list[str]:
    """추적되지 않고 무시되지도 않은 파일.

    **적용기가 보지 못하던 자리다.** 지울 대상을 `git ls-files` 에서만 골라 왔는데, 사내에만
    생긴 파일은 추적되지 않아 그 목록에 없다. 옛 배포의 잔해든 누가 받아 둔 산출물이든
    조용히 쌓이고, 읽는 쪽은 그것이 살아 있는 코드인지 알 수 없어 일단 읽는다.
    """
    listed = git(root, "ls-files", "--others", "--exclude-standard")
    return [line.strip() for line in listed.splitlines() if line.strip()]


def dirty_entries(root: Path) -> list[str]:
    """미저장 변경. 있으면 멈춘다 — 지우고 푸는 과정이 그것을 소리 없이 없앤다."""
    listed = git(root, "status", "--porcelain", "--untracked-files=no")
    return [line.strip() for line in listed.splitlines() if line.strip()]


# ---------- 송장 ----------


def read_manifest(archive: zipfile.ZipFile) -> dict[str, object]:
    if MANIFEST_NAME not in archive.namelist():
        raise ApplyError(
            f"{MANIFEST_NAME} 이 없는 ZIP 입니다. 송장 없이는 어느 버전인지, 온전히 왔는지 "
            "확인할 수 없습니다. 사외에서 최신 스크립트로 다시 만들어 받으세요."
        )
    try:
        manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApplyError(f"{MANIFEST_NAME} 을 읽지 못했습니다: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ApplyError(f"{MANIFEST_NAME} 의 형식이 올바르지 않습니다.")
    version = manifest.get("manifest_version")
    if version not in SUPPORTED_MANIFEST_VERSIONS:
        raise ApplyError(
            f"송장 형식 {version} 을 이 적용기가 모릅니다"
            f"(아는 것: {SUPPORTED_MANIFEST_VERSIONS}). 적용기를 먼저 갱신하세요."
        )
    return manifest


def load_state(root: Path) -> dict[str, object]:
    path = root / STATE_PATH
    if not path.is_file():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return state if isinstance(state, dict) else {}


def order_problems(state: Mapping[str, object], manifest: Mapping[str, object]) -> list[str]:
    """시간을 거스르거나 건너뛴 적용을 가려낸다.

    첫 줄은 **멈출 이유**, 나머지는 알리기만 하는 것이다. 호출자가 첫 항목의 접두사로 가른다.
    """
    problems: list[str] = []
    applied_stamp = str(state.get("stamp") or "")
    incoming_stamp = str(manifest.get("stamp") or "")
    if applied_stamp and incoming_stamp:
        if incoming_stamp == applied_stamp:
            problems.append(f"중단: 이 묶음({incoming_stamp})은 이미 적용했습니다.")
        elif incoming_stamp < applied_stamp:
            problems.append(
                f"중단: 이 묶음({incoming_stamp})은 적용해 둔 {applied_stamp} 보다 과거입니다. "
                "옛 메일을 연 것이 아닌지 확인하세요."
            )
    applied_commit = str(state.get("commit") or "")
    previous_commit = str(manifest.get("previous_commit") or "")
    if applied_commit and previous_commit and applied_commit != previous_commit:
        problems.append(
            f"알림: 이 ZIP 의 직전 배포는 {previous_commit[:7]} 인데 사내에 적용된 것은 "
            f"{applied_commit[:7]} 입니다 — 건너뛴 배포가 있습니다. 적용은 계속합니다."
        )
    return problems


# ---------- ZIP 검사 ----------


def member_problems(names: Sequence[str]) -> list[str]:
    """푸는 순간 저장소 밖을 건드리거나 사내 기록을 덮는 항목."""
    problems: list[str] = []
    seen: dict[str, str] = {}
    for name in names:
        if name == MANIFEST_NAME:
            continue
        if name.endswith("/"):
            continue
        if name.startswith("/") or ".." in Path(name).parts or ":" in name:
            problems.append(f"경로가 저장소 밖을 가리킵니다: {name}")
            continue
        if name.startswith(PRESERVED_PREFIXES):
            problems.append(f"사내 전용 자리를 덮으려 합니다: {name}")
            continue
        # Windows 는 대소문자를 가리지 않는다. 두 항목이 같은 파일로 겹쳐 하나가 사라진다.
        lowered = name.lower()
        if lowered in seen:
            problems.append(f"대소문자만 다른 항목이 겹칩니다: {seen[lowered]} / {name}")
        seen[lowered] = name
    return problems


def plan_removals(
    tracked: Iterable[str],
    members: Iterable[str] = (),
    kept: Iterable[str] = (),
    *,
    preserved: Sequence[str] = PRESERVED_PREFIXES,
) -> list[str]:
    """지울 대상 — **ZIP 이 트리를 정의하되 남기라고 한 것은 빼고.**

    네 가지를 뺀다.

    1. ZIP 이 다시 깔 파일(`members`) — 지웠다 쓰는 것은 같은 결과이고, 실패 지점만 는다.
    2. 송장이 남기라고 한 파일(`kept`) — `pyproject.toml`·`uv.lock` 이다. 사내 Artifactory
       인덱스와 그 락은 사내 것이라 보내지 않으므로, 지우면 **복구할 길이 없다.**
    3. 사내 전용 자리(`preserved`) — 리뷰 기록·적용 이력·권한 설정.
    4. 무시된 파일 — `git ls-files` 에 없어 애초에 후보가 아니다. `git clean -x` 를 쓰지
       않는 이유가 이것이다.
    5. 운영 데이터(`is_protected`) — 4번이 이미 막아 줄 것 같지만, **그것은 사내
       `.gitignore` 가 사외와 같다는 전제**다. 규칙이 지워졌거나 파일이 먼저 커밋됐으면
       DuckDB 가 추적 목록에 들어오고, ZIP 은 그것을 싣지 않으므로 「사외에서 없어진
       파일」로 판정된다. 운영 DB 는 되돌릴 수 없어 전제에 기대지 않는다.

    남는 것이 곧 **사외에서 지워졌는데 사내에 남은 파일**이다. 그것만 지운다.
    """
    keep = set(members) | set(kept)
    return sorted(
        path
        for path in tracked
        if path not in keep and not path.startswith(tuple(preserved)) and not is_protected(path)
    )


def is_protected(path: str) -> bool:
    """운영 데이터라 어떤 경우에도 배포가 지우지 않는 경로인가."""
    # 확장자만 소문자로 보고 이름·접두사는 원래 철자로 보고 있었다. Windows 에서 `.ENV` 는
    # 실제로 생기는 철자이고, 그 한 글자 차이로 이 함수가 "지워도 되는 파일" 이라고 답했다.
    # 같은 뜻을 가진 `build_deploy_package.forbidden_entries` 는 셋 다 소문자로 본다.
    lowered = path.lower()
    return (
        lowered.endswith(NEVER_REMOVE_SUFFIXES)
        or lowered.rsplit("/", 1)[-1] in NEVER_REMOVE_NAMES
        or lowered.startswith(NEVER_REMOVE_PREFIXES)
    )


def reconcile(
    tracked: Iterable[str],
    untracked: Iterable[str],
    expected: Iterable[str],
    kept: Iterable[str] = (),
    *,
    preserved: Sequence[str] = PRESERVED_PREFIXES,
) -> dict[str, list[str]]:
    """사외가 보낸 목록과 사내 폴더를 대조한다.

    송장의 `files` 가 **사외 기준의 정본 목록**이다. 사내 폴더를 그것과 맞대어 세 갈래로 가른다.

    - `사외에서_지워짐` : 추적되는데 목록에 없다 → 사외에서 지운 파일이다. 적용이 지운다.
    - `정체불명`        : 추적도 무시도 되지 않는데 목록에 없다 → **누구도 책임지지 않는 파일.**
      옛 배포의 잔해일 수도, 누가 받아 둔 산출물일 수도, 사내에서 급히 만든 것일 수도 있다.
      **함부로 지우지 않는다** — 무엇인지 모르는 채 지우는 것이 가장 위험하다. 사람에게 묻는다.
    - `목록에만_있음`   : 목록에 있는데 사내에 없다. 적용 **전**이면 정상(ZIP 이 채운다),
      적용 **뒤**에 남아 있으면 해제가 덜 된 것이다.
    """
    expected_set = set(expected)
    kept_set = set(kept)
    prefixes = tuple(preserved)

    def owned(path: str) -> bool:
        # 운영 데이터도 「사내 것」이다. `plan_removals` 가 지우지 않기로 한 파일을 여기서
        # 「사외에서 지워짐」으로 적으면, 같은 출력 안의 두 블록이 서로 다른 말을 한다 —
        # 계획은 안 지운다고 하고 대조는 지울 것이라고 한다.
        return path.startswith(prefixes) or path in kept_set or is_protected(path)

    return {
        "사외에서_지워짐": sorted(
            path for path in tracked if path not in expected_set and not owned(path)
        ),
        "정체불명": sorted(
            path for path in untracked if path not in expected_set and not owned(path)
        ),
        "목록에만_있음": sorted(expected_set - set(tracked) - set(untracked)),
    }


def describe_reconcile(report: Mapping[str, Sequence[str]], *, applied: bool) -> str:
    """대조 결과와 **무엇을 물어야 하는지**를 적는다.

    스크립트는 판단하지 않는다. 사실을 보여 주고, 에이전트가 사용자에게 고를 것을 내민다.
    """
    lines = ["", "── 사외 목록과 사내 폴더 대조 ──────────────────────────────"]
    removed = report.get("사외에서_지워짐") or []
    unknown = report.get("정체불명") or []
    missing = report.get("목록에만_있음") or []

    if removed:
        lines.append(f"사외에서 지워진 파일 {len(removed)}개 — 적용이 함께 지웁니다.")
        lines.extend(f"   - {path}" for path in removed[:15])
        if len(removed) > 15:
            lines.append(f"   … 외 {len(removed) - 15}개")

    if unknown:
        lines.append("")
        lines.append(f"**사내에만 있는 정체불명 파일 {len(unknown)}개** — 손대지 않았습니다.")
        lines.extend(f"   ? {path}" for path in unknown[:30])
        if len(unknown) > 30:
            lines.append(f"   … 외 {len(unknown) - 30}개")
        lines.append("")
        lines.append("   무엇인지 모르는 채 지우는 것이 가장 위험합니다. 사용자에게 물으세요:")
        lines.append(
            "     (1) 사내에서만 쓰는 것이니 그대로 둔다 → `.gitignore` 에 넣을지 함께 정한다"
        )
        lines.append("     (2) 사외에도 있어야 하는 것이다 → 리뷰 문서에 적어 사외가 추가하게 한다")
        lines.append("     (3) 옛 배포의 잔해다 → 지운다")
        lines.append("   판단이 서지 않으면 (1)로 두고 리뷰 문서에 남기는 편이 안전합니다.")

    if missing:
        label = "해제가 덜 됐습니다" if applied else "ZIP 이 채웁니다 — 정상입니다"
        lines.append("")
        lines.append(f"목록에 있는데 사내에 없는 파일 {len(missing)}개 — {label}.")
        lines.extend(f"   - {path}" for path in missing[:10])
        if len(missing) > 10:
            lines.append(f"   … 외 {len(missing) - 10}개")

    if not (removed or unknown or missing):
        lines.append("어긋나는 파일이 없습니다.")
    return "\n".join(lines)


def digest_mismatches(root: Path, files: Mapping[str, object]) -> list[str]:
    mismatched: list[str] = []
    for path, expected in sorted(files.items()):
        target = root / path
        if not target.is_file():
            mismatched.append(f"{path} — 파일이 없습니다")
            continue
        actual = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            mismatched.append(f"{path} — 해시가 다릅니다")
    return mismatched


# ---------- 적용 ----------


def describe_plan(
    manifest: Mapping[str, object],
    removals: Sequence[str],
    members: Sequence[str],
    *,
    tracked: Sequence[str] = (),
) -> str:
    changes = manifest.get("changes")
    lines = [
        f"ZIP     {manifest.get('zip_name')}  ({manifest.get('file_count')}개)",
        f"출처    {str(manifest.get('commit'))[:7]}  {manifest.get('commit_subject')}",
        f"빌드    {manifest.get('built_at')}",
    ]
    if isinstance(changes, dict) and changes:
        label = {"A": "추가", "M": "수정", "D": "삭제"}
        summary = " · ".join(
            f"{label.get(status, status)} {len(paths)}" for status, paths in sorted(changes.items())
        )
        lines.append(f"변경    {summary}  (직전 {manifest.get('previous_deploy') or '없음'} 대비)")
        for status, paths in sorted(changes.items()):
            for path in list(paths)[:8]:
                lines.append(f"        {status}  {path}")
            if len(paths) > 8:
                lines.append(f"        … 외 {len(paths) - 8}개")
    else:
        lines.append("변경    직전 배포 정보 없음 — 전체를 새로 깝니다")
    kept = manifest.get("kept_on_target")
    if isinstance(kept, list) and kept:
        lines.append(f"유지    {' · '.join(str(item) for item in kept)} (사내 것을 남깁니다)")
    if removals:
        lines.append(f"지움    사외에서 없어진 {len(removals):,}개")
        for path in removals[:8]:
            lines.append(f"        - {path}")
        if len(removals) > 8:
            lines.append(f"        … 외 {len(removals) - 8}개")
    else:
        lines.append("지움    없음")
    lines.append(f"보존    {' · '.join(PRESERVED_PREFIXES)} · 무시 목록(데이터) 전부")
    protected = sorted(path for path in tracked if is_protected(path))
    if protected:
        lines.append(
            f"주의    운영 데이터 {len(protected)}개가 **git 에 추적되고 있습니다.** "
            "지우지는 않았지만 정상이 아닙니다 —"
        )
        for path in protected[:8]:
            lines.append(f"        ! {path}")
        if len(protected) > 8:
            lines.append(f"        … 외 {len(protected) - 8}개")
        lines.append("        `git rm -r --cached <경로>` 로 추적만 풉니다(파일은 남습니다).")
    lines.append(f"적용    {len(members):,}개 해제")
    return "\n".join(lines)


def apply_archive(
    root: Path, archive: zipfile.ZipFile, members: Sequence[str], removals: Sequence[str]
) -> None:
    """지우고 푼다. 인덱스는 건드리지 않으므로 실패해도 `git checkout -- .` 로 돌아온다."""
    for path in removals:
        target = root / path
        if target.is_file() or target.is_symlink():
            target.unlink()
    for name in members:
        destination = root / name
        # `member_problems` 가 경로를 이미 검사했다. 그래도 한 번 더 확인한다 — 이 한 줄이
        # 저장소 밖에 쓰는 것을 막는 마지막 문이다.
        resolved = destination.resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ApplyError(f"저장소 밖에 쓰려 합니다: {name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive.read(name))


def stage_paths(root: Path, paths: Sequence[str]) -> None:
    """준 경로만 스테이징한다. 삭제도 함께 잡히도록 `-A` 를 경로에 한정해 쓴다.

    나눠 부르는 것은 명령줄 길이 때문이다. 배포 세트는 수백 개고 Windows 의 한 줄 한계는
    32,767자라, 한 번에 넘기면 저장소가 조금만 커져도 조용히 깨진다.
    """
    chunk = 200
    for start in range(0, len(paths), chunk):
        git(root, "add", "-A", "--", *paths[start : start + chunk])


def write_state(root: Path, manifest: Mapping[str, object]) -> None:
    path = root / STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "stamp": manifest.get("stamp"),
                "commit": manifest.get("commit"),
                "commit_subject": manifest.get("commit_subject"),
                "applied_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "file_count": manifest.get("file_count"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description="사내에서 배포 ZIP 을 적용한다.")
    parser.add_argument("zip_path", type=Path, help="내려받은 배포 ZIP")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="아무것도 바꾸지 않고 무엇이 지워지고 덮일지만 보여 준다.",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="적용만 하고 커밋하지 않는다.",
    )
    parser.add_argument(
        "--reconcile-only",
        action="store_true",
        help="적용하지 않고 사외 목록과 사내 폴더의 차이만 대조해 보여 준다.",
    )
    args = parser.parse_args(argv)

    try:
        return _run(args)
    except ApplyError as exc:
        print(f"\n멈췄습니다 — {exc}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace) -> int:
    root = PROJECT_ROOT
    if not args.zip_path.is_file():
        raise ApplyError(f"ZIP 을 찾지 못했습니다: {args.zip_path}")
    if not zipfile.is_zipfile(args.zip_path):
        raise ApplyError(f"ZIP 파일이 아닙니다: {args.zip_path}")

    with zipfile.ZipFile(args.zip_path) as archive:
        broken = archive.testzip()
        if broken is not None:
            raise ApplyError(f"ZIP 이 손상되었습니다 (처음 깨진 항목: {broken})")
        manifest = read_manifest(archive)
        names = archive.namelist()
        problems = member_problems(names)
        if problems:
            raise ApplyError("ZIP 항목에 문제가 있습니다:\n  - " + "\n  - ".join(problems))

        members = [name for name in names if name != MANIFEST_NAME and not name.endswith("/")]
        files = manifest.get("files")
        if not isinstance(files, dict):
            raise ApplyError("송장에 파일 해시가 없습니다.")
        only_in_zip = sorted(set(members) - set(files))
        only_in_manifest = sorted(set(files) - set(members))
        if only_in_zip or only_in_manifest:
            raise ApplyError(
                "송장과 ZIP 내용이 어긋납니다 — "
                f"ZIP 에만 {len(only_in_zip)}개, 송장에만 {len(only_in_manifest)}개"
            )

        for problem in order_problems(load_state(root), manifest):
            if problem.startswith("중단:"):
                raise ApplyError(problem)
            print(problem)

        kept = manifest.get("kept_on_target")
        kept_paths = [str(item) for item in kept] if isinstance(kept, list) else []
        tracked = tracked_files(root)
        removals = plan_removals(tracked, members, kept_paths)
        print(describe_plan(manifest, removals, members, tracked=tracked))
        print(
            describe_reconcile(
                reconcile(tracked, untracked_files(root), files, kept_paths), applied=False
            )
        )
        # 보기만 하는 길은 여기서 끝난다. **깨끗한 트리를 요구하지 않는다** — 아무것도 바꾸지
        # 않으므로 요구할 이유가 없고, 오히려 작업 중에 대조해 보는 것이 이 기능의 쓸모다.
        if args.dry_run or args.reconcile_only:
            print("\n보기만 했습니다 — 아무것도 바꾸지 않았습니다.")
            return 0

        dirty = dirty_entries(root)
        if dirty:
            raise ApplyError(
                "작업트리에 미저장 변경이 있습니다. 지우고 푸는 과정이 그것을 없앱니다 — "
                "먼저 커밋하거나 되돌리세요:\n  " + "\n  ".join(dirty[:10])
            )

        try:
            apply_archive(root, archive, members, removals)
        except Exception as exc:  # 어떤 실패든 되돌리는 법을 알려야 한다
            raise ApplyError(
                f"적용 중 멈췄습니다: {exc}\n"
                "인덱스는 건드리지 않았습니다. `git checkout -- .` 로 되돌리세요."
            ) from exc

    mismatched = digest_mismatches(root, files)
    if mismatched:
        raise ApplyError(
            f"해시 대조에서 {len(mismatched)}건이 어긋났습니다. `git checkout -- .` 로 "
            "되돌리고 ZIP 을 다시 받으세요:\n  - " + "\n  - ".join(mismatched[:10])
        )
    print(f"대조    {len(files):,}/{len(files):,} 해시 일치")
    # 적용 뒤에 한 번 더 본다. 사외에서 지워진 것이 정말 없어졌는지, 정체불명 파일이 그대로
    # 남았는지 — 사용자에게 무엇을 물어야 하는지가 여기서 정해진다.
    print(
        describe_reconcile(
            reconcile(tracked_files(root), untracked_files(root), files, kept_paths),
            applied=True,
        )
    )

    write_state(root, manifest)
    if args.no_commit:
        print("커밋    건너뜀 (--no-commit)")
        return 0

    # **`git add -A` 를 쓰지 않는다.** 그것은 바로 위에서 "손대지 않았습니다" 라고 적은
    # 정체불명 파일까지 스테이징해 `deploy:` 커밋에 넣는다. 그러면 다음 배포에서 그 파일은
    # "추적되는데 목록에 없는 것" 이 되어 삭제 대상으로 잡힌다 — 약속이 한 사이클만 유효해진다.
    # 아직 커밋하지 않은 `review/*.md` 가 딸려 들어가 `deploy:` 와 `review:` 커밋이 섞이는
    # 것도 같은 한 줄이 만든다. 이번 배포가 실제로 건드린 것만 올린다.
    stage_paths(root, [STATE_PATH, *members, *removals])
    staged = git(root, "diff", "--cached", "--name-only")
    if not staged:
        print("커밋    바뀐 것이 없어 커밋하지 않았습니다.")
        return 0
    subject = f"deploy: {manifest.get('stamp')} ({str(manifest.get('commit'))[:7]})"
    git(root, "commit", "-m", subject, "-m", str(manifest.get("commit_subject") or ""))
    print(f"커밋    {subject}")
    print("\n다음 — 실데이터로 확인한 뒤 `review/` 에 리뷰 문서를 쓰고 사내 GitHub 에 푸시하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
