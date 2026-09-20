# Purpose: 사내 배포용 ZIP 을 배포 세트 규칙대로 만들고 금지·제외 파일을 검사한다.

"""사내 배포 ZIP 만들기.

배포 세트는 `git ls-files` 전체에 운영에 필요한 몇 개를 더한 것이다. `tests/`·`scripts/` 도
넣는다 — 사내 PC 에서 단독으로 돌려 보고 검증할 수 있어야 한다.

**빼는 파일은 없다.** 사내 전용 `bigdataquery` 를 `requirements-company.txt` 로 옮긴 뒤로
`pyproject.toml` 과 `uv.lock` 이 사내·사외에서 같아졌다. 예전에는 사내 선언에만 Artifactory
인덱스가 손으로 들어가 있어 두 파일을 빼야 했고, 그래서 **의존성을 바꾸면 ZIP 만으로는 사내에
반영되지 않는** 예외가 있었다. 지금은 그 예외가 없다.

목록을 비운 채로 두는 이유는 다시 빼야 할 파일이 생겼을 때 규칙이 들어갈 자리를 남기기
위해서다 — 규칙이 주석으로만 있으면 다음 배포에서 조용히 어긋난다.

사용:

    .\\.venv\\Scripts\\python.exe scripts\\build_deploy_package.py --out C:\\Dev\\배포
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

# Windows 콘솔은 cp949 라 그냥 두면 이 스크립트의 한글 안내가 `UnicodeEncodeError` 로
# 죽는다 — ZIP 은 이미 만들어진 뒤라 더 나쁘다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ZIP 안에 함께 넣는 송장. 사내는 이것을 읽어 **무엇을 받았는지** 안다 — 파일만 보내면
# 어느 커밋인지, 온전히 왔는지, 무엇이 달라졌는지 알 길이 없다.
MANIFEST_NAME = "DEPLOY_MANIFEST.json"
# 매니페스트 형식이 바뀌면 올린다. 사내 적용기가 읽을 수 있는지 이 값으로 가른다.
MANIFEST_VERSION = 1
# 배포마다 남기는 태그. 다음 배포가 「직전 배포 이후 무엇이 바뀌었나」를 여기서 구한다.
DEPLOY_TAG_PREFIX = "deploy/"

# 사내에만 있는 자리. 여기에 해당하는 경로는 **보내지도 않고 지우지도 않는다** —
# 리뷰 기록과 적용 이력은 사내가 만든 것이라 사외 배포가 건드리면 안 된다.
INTERNAL_ONLY_PREFIXES: tuple[str, ...] = ("review/", ".deploy/", ".claude/")

# `git ls-files` 에 없지만 보내야 하는 파일. **지금은 비어 있다.**
#
# 한때 여기에 `data/input/RQ_DISPLAY_ORDER.csv` 가 있었다. 두 가지가 잘못이었다.
# ① 그 파일에는 실제 고객명·제품명·공정명이 들어 있고 배포는 메일로 나간다 — `.gitignore`
#    가 일부러 뺀 값을 첨부로 내보내는 길이 된다.
# ② **데이터 정본은 사내다.** 보내면 사내가 실데이터로 만든 표시순서를 사외 개발 PC 의
#    사본이 매 적용마다 덮는다. 적용기의 `is_protected` 는 삭제만 막고 덮어쓰기는 막지
#    않아, 무시 파일이라 `git checkout -- .` 로도 돌아오지 않는다.
# 표시순서 부트스트랩은 `config/bootstrap_display_order.json` 이 맡고, 사내는 이미 자기
# 사본을 갖고 있다.
EXTRA_FILES: tuple[str, ...] = ()

# 추적되지만 보내지 않는 파일. 지금은 비어 있다 — 사내 전용 패키지를
# `requirements-company.txt` 로 뺀 뒤로 선언과 잠금이 양쪽에서 같아졌다.
EXCLUDED_FILES: frozenset[str] = frozenset()

# 들어가면 안 되는 것. `git ls-files` 로 시작하므로 보통은 걸릴 일이 없지만, 한 번 새면
# 되돌릴 수 없는 종류라(실데이터·비밀값) 보내기 전에 다시 본다.
FORBIDDEN_SUFFIXES: tuple[str, ...] = (".xlsb", ".xlsx", ".xlsm", ".duckdb", ".db", ".wal")
FORBIDDEN_NAMES: tuple[str, ...] = (".env", "secrets.toml")
# `data/input/` 이 여기 있는 것은 위 `EXTRA_FILES` 의 결정을 규칙으로 못 박은 것이다 —
# 그 아래는 실데이터 자리이므로 무엇이 들어오든 보내지 않는다(`.gitkeep` 만 예외).
FORBIDDEN_PREFIXES: tuple[str, ...] = ("data/input/", "data/output/", "data/temp/")

# 위 폴더 아래여도 보내는 파일. 빈 폴더를 만들어 두는 자리표이지 데이터가 아니다.
PLACEHOLDER_NAMES: tuple[str, ...] = (".gitkeep",)


def tracked_files(root: Path) -> list[str]:
    """`git ls-files` 결과. 경로 구분자는 git 이 쓰는 `/` 그대로 둔다."""
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def deploy_set(tracked: Iterable[str], *, extras: Sequence[str] = EXTRA_FILES) -> list[str]:
    """보낼 파일 목록. 제외 목록을 빼고 추가 파일을 더한 뒤 한 번만 남긴다."""
    selected = [path for path in tracked if path not in EXCLUDED_FILES]
    for extra in extras:
        if extra not in selected:
            selected.append(extra)
    return sorted(set(selected))


def forbidden_entries(paths: Iterable[str]) -> list[str]:
    """배포하면 안 되는 경로. 빈 목록이어야 보낼 수 있다."""
    flagged: list[str] = []
    for path in paths:
        lowered = path.lower()
        name = lowered.rsplit("/", 1)[-1]
        if name in PLACEHOLDER_NAMES:
            continue
        if (
            lowered.endswith(FORBIDDEN_SUFFIXES)
            or name in FORBIDDEN_NAMES
            or lowered.startswith(FORBIDDEN_PREFIXES)
        ):
            flagged.append(path)
    return flagged


def git_output(root: Path, *args: str) -> str:
    """git 한 줄 실행. 실패하면 빈 문자열 — 태그가 하나도 없는 첫 배포가 정상이다."""
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def previous_deploy_tag(root: Path) -> str:
    """직전 배포 태그. 이름이 `deploy/YYYYMMDDHHMM` 이라 사전순이 곧 시간순이다."""
    listed = git_output(root, "tag", "--list", f"{DEPLOY_TAG_PREFIX}*")
    tags = sorted(line.strip() for line in listed.splitlines() if line.strip())
    return tags[-1] if tags else ""


def change_entries(root: Path, previous_tag: str) -> dict[str, list[str]]:
    """직전 배포 이후 무엇이 바뀌었나. **손으로 적지 않고 git 이 만든다.**

    손으로 적은 목록은 실제와 어긋날 수 있고, 어긋나면 사내가 그 틀린 기준으로 판단한다.
    """
    if not previous_tag:
        return {}
    listed = git_output(root, "diff", "--name-status", f"{previous_tag}..HEAD")
    changes: dict[str, list[str]] = {}
    for line in listed.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        # 이름이 바뀐 항목은 `R100\told\tnew` 로 온다. 옛 이름은 삭제, 새 이름은 추가로 편다.
        status = parts[0][:1]
        if status == "R" and len(parts) >= 3:
            changes.setdefault("D", []).append(parts[1])
            changes.setdefault("A", []).append(parts[2])
            continue
        changes.setdefault(status, []).append(parts[1])
    return {status: sorted(paths) for status, paths in sorted(changes.items())}


def file_digests(root: Path, paths: Iterable[str]) -> dict[str, str]:
    """보내는 파일마다 sha256. 사내가 적용 뒤 이걸로 전량 대조한다."""
    digests: dict[str, str] = {}
    for path in paths:
        digest = hashlib.sha256((root / path).read_bytes()).hexdigest()
        digests[path] = f"sha256:{digest}"
    return digests


def build_manifest(root: Path, paths: Sequence[str], *, stamp: str) -> dict[str, object]:
    """ZIP 에 함께 넣는 송장."""
    previous_tag = previous_deploy_tag(root)
    return {
        "manifest_version": MANIFEST_VERSION,
        "stamp": stamp,
        "zip_name": f"{stamp}.zip",
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "commit": git_output(root, "rev-parse", "HEAD"),
        "commit_subject": git_output(root, "log", "-1", "--format=%s"),
        "previous_deploy": previous_tag.removeprefix(DEPLOY_TAG_PREFIX),
        "previous_commit": git_output(root, "rev-parse", previous_tag) if previous_tag else "",
        "changes": change_entries(root, previous_tag),
        # 보내지 않지만 **사내 것을 남겨야 하는** 파일. 적용기가 이 목록을 보고 지우지
        # 않는다 — 없으면 사내 Artifactory 인덱스와 락이 적용 때마다 사라진다.
        "kept_on_target": sorted(EXCLUDED_FILES),
        "hygiene": hygiene_report(root, paths),
        "file_count": len(paths),
        "files": file_digests(root, paths),
    }


def hygiene_report(root: Path, paths: Sequence[str]) -> dict[str, object]:
    """막지 않고 **알리기만** 하는 위생 수치.

    판정이 명확한 것(고아 모듈·없는 파일 참조·정체불명 최상위 파일)은 이미
    `tests/test_repository_hygiene.py` 가 막는다. 여기 담는 것은 그 반대 — 옳고 그름이
    없어 검사로 만들 수 없지만 **조용히 자라는** 것들이다.

    문서는 지우는 사람이 없으면 늘기만 한다. 늘어난 문서는 읽는 쪽의 비용이고, 사내는 쓸
    수 있는 양이 적어 그 비용이 먼저 나타난다. 숫자를 송장에 실어 사내 리뷰가 추세를 보게
    한다 — 배포를 막을 일은 아니다.
    """
    documents = sorted(path for path in paths if path.endswith(".md"))
    lines = {
        path: len((root / path).read_text(encoding="utf-8", errors="ignore").splitlines())
        for path in documents
    }
    return {
        "tracked_files": len(paths),
        "document_count": len(documents),
        "document_lines": sum(lines.values()),
        "largest_documents": [
            {"path": path, "lines": count}
            for path, count in sorted(lines.items(), key=lambda item: -item[1])[:5]
        ],
    }


def internal_only_entries(paths: Iterable[str]) -> list[str]:
    """사내 전용 자리를 침범하는 경로. 하나라도 있으면 사내 기록을 덮는다."""
    return sorted(path for path in paths if path.startswith(INTERNAL_ONLY_PREFIXES))


def build_archive(
    root: Path,
    paths: Sequence[str],
    destination: Path,
    *,
    manifest: Mapping[str, object] | None = None,
) -> int:
    """ZIP 을 만들고 넣은 항목 수를 돌려준다. 없는 파일은 그 자리에서 멈춘다.

    매니페스트는 자기 자신을 해시하지 않으므로 `files` 에 들어가지 않는다.
    """
    missing = [path for path in paths if not (root / path).is_file()]
    if missing:
        raise FileNotFoundError(f"배포 세트에 없는 파일이 있습니다: {', '.join(missing[:5])}")
    if MANIFEST_NAME in paths:
        raise ValueError(f"배포 세트에 {MANIFEST_NAME} 이 있습니다 — 송장과 이름이 부딪힙니다.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(root / path, arcname=path)
        if manifest is not None:
            archive.writestr(
                MANIFEST_NAME,
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            )
    return len(paths)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="사내 배포 ZIP 을 만든다.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="ZIP 을 둘 폴더. 파일 이름은 `YYYYMMDDHHMM.zip` 으로 짓는다.",
    )
    parser.add_argument(
        "--stamp",
        default=None,
        help="파일 이름에 쓸 시각. 생략하면 지금 시각을 쓴다.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="ZIP 을 만들지 않고 보낼 목록만 출력한다.",
    )
    parser.add_argument(
        "--no-tag",
        action="store_true",
        help="배포 태그를 남기지 않는다. 시험 삼아 만들어 볼 때만 쓴다.",
    )
    args = parser.parse_args(argv)

    paths = deploy_set(tracked_files(PROJECT_ROOT))
    flagged = forbidden_entries(paths)
    if flagged:
        print("배포하면 안 되는 파일이 세트에 있습니다:", file=sys.stderr)
        for path in flagged:
            print(f"  - {path}", file=sys.stderr)
        return 1

    # 사외에 `review/` 같은 폴더가 생기면 ZIP 에 실려 사내 리뷰 기록을 덮는다.
    intruding = internal_only_entries(paths)
    if intruding:
        print("사내 전용 자리를 침범하는 파일이 세트에 있습니다:", file=sys.stderr)
        for path in intruding:
            print(f"  - {path}", file=sys.stderr)
        print(f"  ({', '.join(INTERNAL_ONLY_PREFIXES)} 는 사내만 씁니다)", file=sys.stderr)
        return 1

    if args.list_only:
        for path in paths:
            print(path)
        print(f"\n총 {len(paths):,}개")
        return 0

    if args.out is None:
        parser.error("ZIP 을 만들려면 --out 이 필요합니다(--list-only 는 예외).")
    stamp = args.stamp or datetime.now().strftime("%Y%m%d%H%M")
    destination = args.out / f"{stamp}.zip"
    manifest = build_manifest(PROJECT_ROOT, paths, stamp=stamp)
    count = build_archive(PROJECT_ROOT, paths, destination, manifest=manifest)
    size = destination.stat().st_size
    print(f"{destination} ({size:,} bytes, 엔트리 {count:,}개 + 송장)")
    commit = str(manifest["commit"])
    previous = str(manifest["previous_deploy"])
    print(f"출처 {commit[:7]}  {manifest['commit_subject']}")
    if previous:
        changes = manifest["changes"]
        summary = (
            ", ".join(f"{status} {len(paths_)}" for status, paths_ in sorted(changes.items()))
            if isinstance(changes, dict) and changes
            else "변경 없음"
        )
        print(f"직전 {previous} 대비 — {summary}")
    else:
        print("직전 배포 태그가 없습니다 — 첫 배포로 기록합니다.")

    if not args.no_tag:
        tag = f"{DEPLOY_TAG_PREFIX}{stamp}"
        tagged = subprocess.run(
            ["git", "tag", tag],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if tagged.returncode == 0:
            print(
                f"태그 {tag} — 다음 배포가 여기서 변경 목록을 구합니다. "
                "`git push --tags` 를 잊지 마세요."
            )
        else:
            print(f"태그 {tag} 를 남기지 못했습니다: {tagged.stderr.strip()}", file=sys.stderr)

    hygiene = manifest["hygiene"]
    if isinstance(hygiene, dict):
        print(
            f"위생  파일 {hygiene['tracked_files']:,}개 · "
            f"문서 {hygiene['document_count']}개 {hygiene['document_lines']:,}줄 "
            "(막지 않습니다 — 추세만 봅니다)"
        )
    print(f"제외: {', '.join(sorted(EXCLUDED_FILES)) if EXCLUDED_FILES else '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
