# Purpose: 가이드 점검기 — 덮어쓰기 · 매개값 · 촬영 결과를 뼈대에 대 보고 리뷰 한 줄을 낸다.

"""따라하기 가이드 점검기(handoff §6). 브라우저 · 앱 없이 몇 초에 돈다.

    .venv/bin/python scripts/check_page_guide.py --work <저장소 밖>/guide_work \\
        --overrides review/guide/overrides.json --params review/guide/params.json

| 검사 | 걸리면 |
|---|---|
| 형식(스키마) · ID 중복 · 원고의 상태와 표적이 계획에 있는지 | 사외 시험 실패 · 여기서는 멈춤(2) |
| 덮어쓰기 주소가 원고에 있는지(고아) · 뼈대 판이 맞는지 | 한 줄에 「고아 n」 · 「판 다름」 |
| 덮어쓰기에 금지 칸 · HTML · 스크립트가 있는지 | 조립 거절(2) — 주소만 찍는다 |
| 매개값의 형 | 조립 거절(2) — 이름만 찍는다 |
| 촬영 결과에서 못 찾은 표적 | 한 줄에 `ng <표적@상태>` |

stdout 에는 리뷰 md 에 옮길 한 줄만 찍는다. 생성기(`build_page_guide.py`)의 마지막 줄과 같은
길(`page_guide_core.review_for_work`)이다. `--work` 를 주지 않으면 덮어쓰기 · 매개값만 본다
(덮어쓰기를 고치는 동안 `--assemble-only` 앞에 돌린다). stderr 에는 못 찾은 표적 · 고아 주소 ·
예시로 대신한 자리를 ID 로만 찍는다 — 사내 글 값은 찍지 않는다.

종료 코드: 0 한 줄을 냄(`ng` · 고아가 있어도) · 2 멈춤(뼈대가 깨짐 · 조립 거절 · 읽지 못함 ·
작업 폴더가 다른 뼈대 판).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import page_guide_core as core

EXIT_OK: Final = 0
EXIT_NOT_READY: Final = 2


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="따라하기 가이드 점검기 — 리뷰 한 줄을 낸다.")
    parser.add_argument("--guide", default=core.DEFAULT_GUIDE, help="가이드 이름(기본 lob)")
    parser.add_argument("--work", type=Path, default=None, help="생성기의 --work(촬영 결과)")
    parser.add_argument("--overrides", type=Path, default=None, help="사내 덮어쓰기")
    parser.add_argument("--params", type=Path, default=None, help="사내 매개값")
    return parser.parse_args(argv)


def check(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        skeleton = core.load_skeleton(args.guide)
        broken = core.skeleton_problems(skeleton)
        if broken:
            raise core.GuideInputError("뼈대가 깨졌습니다(사외 정본)", broken)
        override_doc = core.load_json(args.overrides) if args.overrides is not None else None
        param_doc = core.load_json(args.params) if args.params is not None else None
        content, overrides = core.apply_overrides(
            skeleton.content, override_doc, version=skeleton.version
        )
        _values, params = core.resolve_params(skeleton.plan, param_doc)
        if args.work is None:
            line = core.review_line(skeleton, None, None, overrides, params)
            details = [f"고아 {address}" for address in overrides.orphans]
        else:
            line, details = core.review_for_work(skeleton, content, args.work, overrides, params)
    except core.GuideInputError as exc:
        print(str(exc))
        for problem in exc.problems:
            print(f"  {problem}", file=sys.stderr)
        return EXIT_NOT_READY
    except (OSError, ValueError, KeyError) as exc:
        print(f"읽지 못했습니다 — {type(exc).__name__}")
        return EXIT_NOT_READY
    for detail in details:
        print(f"  {detail}", file=sys.stderr)
    print(line)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    return check(argv)


if __name__ == "__main__":
    raise SystemExit(main())
