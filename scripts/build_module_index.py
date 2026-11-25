# Purpose: 추적 소스 모듈의 경로 전체를 docs/reference/module_index.md 로 쓰고 어긋남을 검사한다.

"""모듈 색인 만들기.

소스 모듈은 모두 문서 어딘가에 등재되어 있어야 한다(`tests/test_documentation_inventory.py`). 그
등재를 손으로 이어 적지 않고 이 생성기가 `git ls-files` 로 쓴다 — 범위는 `app.py` · `app_pages/` ·
`src/capa_simulation/` 의 추적 `.py` 이고 `__init__.py` 는 뺀다. 파일마다 맡은 일은 그 파일의
Purpose 헤더와 `docs/reference/files/` 가 적는다.

사용:

    .venv/bin/python scripts/build_module_index.py          # 색인을 쓴다
    .venv/bin/python scripts/build_module_index.py --check  # 다르면 실패한다(쓰지 않는다)

모듈을 더하거나 지우거나 옮기면 `git add` 뒤 이것을 돌려 색인을 함께 커밋한다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = "docs/reference/module_index.md"
ENTRY_FILE = "app.py"
SOURCE_PREFIXES = ("app_pages/", "src/capa_simulation/")
PACKAGE_MARKER = "__init__.py"
INDEX_TITLE = "모듈 색인"


def is_indexed_module(path: str) -> bool:
    """색인에 싣는 추적 파일인가 — 진입점 · 화면 · 패키지 소스의 `.py`, 패키지 표지는 뺀다."""
    return (
        path.endswith(".py")
        and (path == ENTRY_FILE or path.startswith(SOURCE_PREFIXES))
        and not path.endswith(PACKAGE_MARKER)
    )


def tracked_modules(root: Path = PROJECT_ROOT) -> list[str]:
    """색인에 싣는 추적 모듈 경로를 정렬해 돌려준다."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=root,
        check=True,
    ).stdout.split("\0")
    return sorted(path for path in listed if path and is_indexed_module(path))


def render_index(modules: Sequence[str]) -> str:
    """색인 Markdown. 같은 목록이면 늘 같은 글자다 — 시각 · 개수를 넣지 않는다."""
    rows = "\n".join(f"- `{path}`" for path in modules)
    return (
        f"# {INDEX_TITLE}\n"
        "\n"
        "`scripts/build_module_index.py` 가 `git ls-files` 로 쓰는 생성물이다 — "
        "손으로 고치지 않는다.\n"
        "범위는 `app.py` · `app_pages/` · `src/capa_simulation/` 의 추적 `.py` 파일"
        "(`__init__.py` 뺌)이고,\n"
        "파일마다 맡은 일은 그 파일의 Purpose 헤더와 `docs/reference/files/` 가 적는다.\n"
        "\n"
        f"{rows}\n"
    )


def main(argv: Sequence[str] | None = None, *, root: Path = PROJECT_ROOT) -> int:
    """성공 0 · 실을 모듈이 없거나 `--check` 에서 색인이 다르면 1."""
    parser = argparse.ArgumentParser(description="추적 소스 모듈 경로로 모듈 색인을 쓴다.")
    parser.add_argument("--check", action="store_true", help="쓰지 않고 다르면 실패한다")
    args = parser.parse_args(argv)

    modules = tracked_modules(root)
    if not modules:
        print("색인에 실을 추적 모듈이 없습니다 — git 저장소 뿌리에서 돌립니다.", file=sys.stderr)
        return 1

    rendered = render_index(modules)
    target = root / INDEX_PATH
    if args.check:
        # 바이트로 읽는다 — 글자로 읽으면 줄바꿈 변환이 CR 을 가린다.
        current = target.read_bytes() if target.is_file() else b""
        if current != rendered.encode("utf-8"):
            print(
                f"{INDEX_PATH} 색인이 추적 모듈 목록과 다릅니다. "
                "scripts/build_module_index.py 를 돌려 함께 커밋합니다.",
                file=sys.stderr,
            )
            return 1
        print(f"모듈 색인 맞음 — 모듈 {len(modules)}개")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(rendered.encode("utf-8"))
    print(f"{INDEX_PATH} 색인을 썼습니다 — 모듈 {len(modules)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
