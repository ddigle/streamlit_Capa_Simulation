# Purpose: 이 작업 폴더가 제 가상환경·제 코드·제 DuckDB 만 쓰는지 확인한다.

"""병행 개발에서 **아무 신호도 없이** 나는 사고 하나를 기계가 잡게 한다.

`AGENTS.md` 14-1 이 「`.venv` 를 공유하지 않는다」고 적어 두었지만 검사가 없었다. 그런데
이것은 사람이 지키기에 가장 나쁜 종류의 규칙이다 — 어겼을 때 **아무 일도 일어나지 않는
것처럼 보이기** 때문이다.

남의 `.venv` 를 쓰면 editable 설치의 `__editable__.capa_simulation-0.1.0.pth` 가 **절대경로**
로 남의 `src/` 를 가리킨다. 화면은 내 코드처럼 보이는데 `import capa_simulation` 은 남의
모듈을 읽고, `settings.PROJECT_ROOT` 가 남의 폴더가 되어 **남의 DuckDB 를 연다.** 그러면서
`pytest` 는 `pythonpath = ["src"]` 로 제 폴더를 보므로 **검증 4종이 전부 초록이다.**

그래서 이 스크립트는 **`pytest` 로 돌리지 않는다.** 테스트로 만들면 그 경로 주입 때문에
검사하려는 바로 그 상황을 못 본다. 설치된 패키지가 실제로 어디서 오는지 보려면 앱이 뜨는
것과 같은 방식으로 맨 인터프리터에서 import 해야 한다.

    .\.venv\Scripts\python.exe scripts\check_worktree_isolation.py

어긋나면 0 이 아닌 값으로 끝난다.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows 콘솔 기본 코드페이지(cp949)는 이 파일의 한글 기호를 못 쓴다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 이 파일은 `<작업폴더>/scripts/` 에 있다. 저장소 밖을 보지 않으려면 이 값이 기준이다.
WORKTREE = Path(__file__).resolve().parents[1]


def _inside(path: Path) -> bool:
    try:
        path.resolve().relative_to(WORKTREE)
    except ValueError:
        return False
    return True


def _report(name: str, path: Path | None, *, detail: str = "") -> bool:
    if path is None:
        print(f"  ?  {name}: 찾지 못함 {detail}")
        return True
    ok = _inside(path)
    mark = "OK" if ok else "!!"
    print(f"  {mark} {name}: {path}")
    if not ok and detail:
        print(f"       {detail}")
    return ok


def _editable_targets() -> list[Path]:
    """site-packages 의 `__editable__*.pth` 가 가리키는 경로."""
    targets: list[Path] = []
    for entry in map(Path, sys.path):
        if entry.name != "site-packages" or not entry.is_dir():
            continue
        for pth in entry.glob("__editable__*.pth"):
            for line in pth.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("import"):
                    targets.append(Path(line))
    return targets


def main() -> int:
    print(f"작업 폴더: {WORKTREE}\n")
    ok = True

    print("가상환경")
    ok &= _report(
        "sys.prefix",
        Path(sys.prefix),
        detail="다른 폴더의 .venv 를 쓰고 있습니다. 이 폴더에서 `uv sync` 로 제 것을 만드세요.",
    )

    print("\neditable 설치가 가리키는 곳")
    targets = _editable_targets()
    if not targets:
        print("  ?  __editable__*.pth 없음 — editable 설치가 아닙니다")
    for target in targets:
        ok &= _report(
            "pth",
            target,
            detail="남의 src/ 를 읽습니다. 화면은 내 코드인데 동작은 남의 코드입니다.",
        )

    print("\n실제로 import 되는 패키지")
    try:
        import capa_simulation
        from capa_simulation import settings
    except Exception as error:  # noqa: BLE001 - 어떤 실패든 원인을 그대로 보여 준다
        print(f"  !! import 실패: {type(error).__name__}: {error}")
        return 1

    module_file = Path(capa_simulation.__file__ or "")
    ok &= _report("capa_simulation", module_file.parent)

    print("\nDuckDB 경로")
    for name, path in (
        ("시뮬레이션", settings.DUCKDB_PATH),
        ("가용설비", settings.EQUIPMENT_DUCKDB_PATH),
    ):
        ok &= _report(
            name,
            Path(path),
            detail="남의 DB 를 엽니다. 배타 잠금이라 상대 앱이 떠 있으면 실패하고, "
            "안 떠 있으면 조용히 남의 데이터를 고칩니다.",
        )

    print()
    if ok:
        print("격리 확인. 이 폴더는 제 것만 씁니다.")
        print("앱을 띄울 때 포트를 반드시 주세요 — 폴더마다 다른 번호입니다(AGENTS 14-1).")
        return 0
    print("격리가 깨졌습니다. 위 `!!` 줄을 먼저 고치세요.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
