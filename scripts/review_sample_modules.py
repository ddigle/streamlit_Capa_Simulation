# Purpose: 검수용 모듈 견본 여섯을 시험 견본에서 산출 뿌리로 복사하고 빈 모듈 데이터 뿌리를 만든다.

"""검수용 합성 샘플 3단계 — 모듈 견본(`generate_review_sample.py --modules` 가 부른다).

    .venv/bin/python scripts/review_sample_modules.py --out <저장소 밖 뿌리>

**하는 일.**

1. `<fixtures>/`(기본 저장소 `tests/fixtures/modules/`)의 여섯 견본(`demo_ok`·`demo_crash`·
   `demo_keys`·`demo_off`·`demo_bad_manifest`·`demo_future_api`)을 파일 내용 그대로
   `<out>/modules/<id>/` 로 복사한다(`__pycache__` 는 뺀다). 그 여섯 폴더만 지우고 다시 쓴다 —
   `<out>/modules/` 의 다른 것은 건드리지 않는다.
2. `<out>/module-data/` 를 빈 폴더로 만든다. 모듈 데이터는 화면이 실행 중에 쓰는 자리라 손으로 넣지
   않는다. 이미 있고 안에 파일이 있으면(앱이 쓴 것) 지우지 않고 수만 알린다.
3. 앱의 모듈 찾기(`module_registry.scan_modules`, 코어 화면 이름 겹침 포함)로 복사본을 다시 읽어
   여섯의 상태·까닭을 찍는다. 기대와 다르면 종료 코드 1.

**지키는 것.** git 작업 트리(이 저장소 포함) 안에는 쓰지 않는다 — 저장소에 `modules/` 를 만들지
않고, 모듈 뿌리는 실행 줄 `CAPA_MODULES_ROOT`·`CAPA_MODULES_DATA_ROOT` 로만 준다. 견본은 합성이다.
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

import review_sample_story as story

# 견본 — 저장소 시험 견본(`tests/fixtures/modules/`)의 합성 모듈 여섯.
DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "modules"

# 견본 여섯과 기대 상태(scan_modules 의 state).
EXPECTED: dict[str, str] = {
    "demo_ok": "on",
    "demo_crash": "on",
    "demo_keys": "on",
    "demo_off": "off",
    "demo_bad_manifest": "failed",
    "demo_future_api": "failed",
}
SKIP_NAMES = ("__pycache__",)


def fail(message: str, code: int = 2) -> int:
    sys.stderr.write(message + "\n")
    return code


def copy_module(source: Path, target: Path) -> int:
    """`source` 폴더를 `target` 으로 내용 그대로 복사한다. 복사한 파일 수."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*SKIP_NAMES))
    return sum(1 for path in target.rglob("*") if path.is_file())


def same_tree(source: Path, target: Path) -> bool:
    """두 폴더의 파일 목록과 바이트가 같은가(`__pycache__` 제외)."""

    def files(root: Path) -> list[str]:
        return sorted(
            str(path.relative_to(root))
            for path in root.rglob("*")
            if path.is_file() and not any(part in SKIP_NAMES for part in path.parts)
        )

    left, right = files(source), files(target)
    if left != right:
        return False
    return all(filecmp.cmp(source / name, target / name, shallow=False) for name in left)


def scan_lines(root: Path) -> tuple[list[str], dict[str, str]]:
    """앱과 같은 판정(코어 화면 이름 겹침 포함)으로 다시 읽은 상태 줄과 id → 상태."""
    from capa_simulation import module_registry, navigation

    scan = module_registry.scan_modules(
        root, disabled="", reserved_titles=navigation.core_page_titles()
    )
    lines: list[str] = []
    states: dict[str, str] = {}
    for record in scan.records:
        pages = len(record.manifest.pages) if record.manifest is not None else 0
        states[record.folder_name] = record.state
        lines.append(
            f"  {record.folder_name:<18} {record.state:<6} 화면 {pages}"
            + (f" — {record.reason}" if record.reason else "")
        )
    return lines, states


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fixtures", type=Path, help="견본 폴더(기본: 사본의 tests/fixtures/modules)"
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="산출 뿌리(modules/·module-data/ 를 만든다)"
    )
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")

    fixtures = (args.fixtures or DEFAULT_FIXTURES).resolve()
    if not fixtures.is_dir():
        return fail(f"견본 폴더가 없습니다: {fixtures}")
    out = args.out.expanduser()
    refusal = story.refuse_place(out)
    if refusal is not None:
        return fail("멈춤 — " + refusal)

    modules_root = out / "modules"
    data_root = out / "module-data"
    modules_root.mkdir(parents=True, exist_ok=True)
    print(f"견본: {fixtures}")
    print(f"모듈 뿌리: {modules_root}")
    copied = 0
    for module_id in EXPECTED:
        source = fixtures / module_id
        if not source.is_dir():
            return fail(f"견본에 {module_id} 모듈이 없습니다: {source}")
        count = copy_module(source, modules_root / module_id)
        if not same_tree(source, modules_root / module_id):
            return fail(f"복사본이 견본과 다릅니다: {module_id}")
        copied += count
        print(f"  복사 {module_id}: 파일 {count}")
    others = sorted(
        entry.name
        for entry in os.scandir(modules_root)
        if entry.is_dir() and entry.name not in EXPECTED and not entry.name.startswith((".", "_"))
    )
    if others:
        print(f"  (그대로 둔 다른 폴더: {', '.join(others)})")

    data_root.mkdir(parents=True, exist_ok=True)
    existing = [path for path in data_root.rglob("*") if path.is_file()]
    if existing:
        print(
            f"모듈 데이터 뿌리: {data_root} — 앱이 쓴 파일 {len(existing)}개가 있어 지우지 "
            "않았습니다"
        )
    else:
        print(f"모듈 데이터 뿌리: {data_root} — 빈 폴더")

    lines, states = scan_lines(modules_root)
    print("앱 판정(module_registry.scan_modules, 코어 화면 이름 포함):")
    print("\n".join(lines))
    wrong = {
        mid: (states.get(mid), want) for mid, want in EXPECTED.items() if states.get(mid) != want
    }
    on_pages = sum(1 for mid, state in states.items() if state == "on")
    print(
        f"합계: 모듈 {len(states)} · 켜짐 {on_pages} · 꺼짐 "
        f"{sum(1 for s in states.values() if s == 'off')} · 실패 "
        f"{sum(1 for s in states.values() if s == 'failed')} · 복사 파일 {copied}"
    )
    print(
        "실행 줄: CAPA_MODULES_ROOT="
        + str(modules_root)
        + " CAPA_MODULES_DATA_ROOT="
        + str(data_root)
        + " (하나를 끄려면 CAPA_MODULES_DISABLED=demo_keys 를 더한다 — 안내만)"
    )
    if wrong:
        return fail(f"기대와 다른 상태: {wrong}", 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
