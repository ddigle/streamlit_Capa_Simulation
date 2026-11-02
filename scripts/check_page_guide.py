# Purpose: 가이드 점검기 — 사내 두 파일 · 촬영을 뼈대 · 검수 마친 판에 대 보고 리뷰 한 줄을 낸다.

"""따라하기 가이드 점검기(handoff §6). 브라우저 · 앱 없이 몇 초에 돈다.

    .venv/bin/python scripts/check_page_guide.py --work <저장소 밖>/guide_work \\
        --overrides review/guide/overrides.json --params review/guide/params.json \\
        --accepted review/guide/accepted.json
    # 검수가 끝난 뒤 한 번(사용자가 「검수 끝」 이라고 한 뒤에만) — 같은 줄 끝에 --accept

| 검사 | 걸리면 |
|---|---|
| 형식(스키마) · ID 중복 · 원고의 상태와 표적이 계획에 있는지 | 사외 시험 실패 · 여기서는 멈춤(2) |
| 덮어쓰기 주소가 원고에 있는지(고아) · 뼈대 판이 맞는지 | 한 줄에 「고아 n」 · 「판 다름」 |
| 덮어쓰기에 금지 칸 · HTML · 스크립트가 있는지 | 조립 거절(2) — 주소만 찍는다 |
| 매개값의 형 | 조립 거절(2) — 이름만 찍는다 |
| 촬영 결과에서 못 찾은 표적 | 한 줄에 `ng <표적@상태>` |
| 검수 마친 판(`--accepted`)과 달라진 자리 | 한 줄에 `바뀜 n/N`(못 쓰면 `na`) · `바뀜 <자리>` |
| `--accept` | 검수 마친 판을 쓴다(아래 거절 일곱이면 쓰지 않고 2) |

stdout 에는 리뷰 md 에 옮길 한 줄만 찍는다. 생성기(`build_page_guide.py`)의 마지막 줄과 같은
길(`page_guide_core.review_for_work`)이고, `--accepted` 를 주면 `예시 n;` 뒤에 `바뀜` 칸이 선다
(생성기 끝 줄에는 없다). `--work` 를 주지 않으면 덮어쓰기 · 매개값만 본다(덮어쓰기를 고치는 동안
`--assemble-only` 앞에 돌린다). stderr 에는 못 찾은 표적 · 고아 주소 · 예시로 대신한 자리, 그 뒤에
기준 · 흔들림 · 바뀜 줄을 ID · 수 · 고정 낱말로만 찍는다 — 사내 글 값 · 화면 글자 · px 는 안 찍는다.

**바뀐 자리 검수.** `--accepted` 는 검수를 마친 판(사내 `review/guide/accepted.json`)이다. 원고 자리
마다 표적 자리 · 자르기 틀 · 원고 · 덮어쓰기 · 촬영 동작의 지문을 견줘 달라진 자리를 원고 차례로
찍고(까닭 `잃음` · `찾음` · `상자` · `틀` · `계획` · `원고` · `덮어씀` · `새 자리` · `데이터 자리`),
데이터 자리(`page_guide_core.DATA_SHAPED`)는 늘 목록에 든다. 기준 파일이 없거나 깨졌거나 봉인 ·
모드가 어긋나면 멈추지 않고 `바뀜 na`(모든 자리를 본다)로 0 이다.

`--accept` 는 그 판을 새로 쓴다 — 이번에 바뀜 · 새 자리로 찍힌 자리만 지금 값으로, 나머지는 앞 값을
두고 데이터 자리는 적지 않는다. 옆 `.tmp` 에 써서 `os.replace` 한다. `--work` · `--accepted` ·
`--overrides` · `--params` 가 다 있어야 하고, `--accepted` 는 git 저장소 뿌리(`.git` · `app.py` ·
`src/capa_simulation/`)의 이미 있는 `review/guide/` 안 `accepted.json` 이어야 한다(연결 폴더 거절 —
사본 트리에는 `.git` 이 없어 쓰지 않는다). 성공하면 stderr 에 `기준 씀 — n자리` 를 찍고 앞 기준과
견준 리뷰 한 줄을 낸다.

종료 코드: 0 한 줄을 냄(`ng` · 고아가 있어도, 기준 파일을 못 읽어도) · 2 멈춤(뼈대가 깨짐 · 조립
거절 · 읽지 못함 · 작업 폴더가 다른 뼈대 판, `--accept` 거절 — 인자 모자람 · 자리가 아님 · 판
다름 · DB 변화 있음 · 조립 기록 없음 · 조립 뒤 바뀜 · 쓰지 못함).
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import page_guide_core as core

EXIT_OK: Final = 0
EXIT_NOT_READY: Final = 2
# `--accept` 를 거절할 때의 stdout(뒤에 까닭) — 경로는 찍지 않는다.
NOT_WRITTEN: Final = "기준을 쓰지 않았습니다 — {}"
WRITE_FAILED: Final = "기준을 쓰지 못했습니다 — {}"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="따라하기 가이드 점검기 — 리뷰 한 줄을 낸다.")
    parser.add_argument("--guide", default=core.DEFAULT_GUIDE, help="가이드 이름(기본 lob)")
    parser.add_argument("--work", type=Path, default=None, help="생성기의 --work(촬영 결과)")
    parser.add_argument("--overrides", type=Path, default=None, help="사내 덮어쓰기")
    parser.add_argument("--params", type=Path, default=None, help="사내 매개값")
    parser.add_argument(
        "--accepted",
        type=Path,
        default=None,
        help="검수 마친 판(review/guide/accepted.json) — 주면 리뷰 한 줄에 「바뀜 n/N」 칸",
    )
    parser.add_argument(
        "--accept",
        action="store_true",
        help="검수를 마친 판을 --accepted 에 쓴다(사용자가 「검수 끝」 이라고 한 뒤에만)",
    )
    return parser.parse_args(argv)


def accepted_place_ok(path: Path) -> bool:
    """`--accept` 가 쓸 자리인가 — `<저장소 뿌리>/review/guide/accepted.json`.

    resolve 한 경로의 이름 셋(`accepted.json` · `guide` · `review`)을 보고, `review` ·
    `review/guide` 가 연결(symlink · junction — 부모를 resolve 한 자리 + 이름과 다르게 풀림)이거나
    파일이 연결이면 거절한다. 뿌리에 `.git` · `app.py` · `src/capa_simulation/` 가 있어야 하고(사본
    트리에는 `.git` 이 없다), `review/guide/` 는 이미 있어야 한다(만들지 않는다). 뿌리를 이 파일
    자리로 정하지 않는다 — 점검기는 사본 트리의 `scripts/` 에서 돈다."""
    try:
        absolute = Path(os.path.abspath(path))
        resolved = absolute.resolve()
        if absolute.is_symlink():
            return False
        if (resolved.name, resolved.parent.name, resolved.parent.parent.name) != (
            core.ACCEPTED_FILE,
            "guide",
            "review",
        ):
            return False
        for folder in (absolute.parent.parent, absolute.parent):
            if folder.resolve() != folder.parent.resolve() / folder.name:
                return False
        root = resolved.parent.parent.parent
        return (
            (root / ".git").exists()
            and (root / "app.py").is_file()
            and (root / "src" / "capa_simulation").is_dir()
            and resolved.parent.is_dir()
        )
    except (OSError, RuntimeError, ValueError):
        return False


def accept_refusal(
    review: core.WorkReview, work: Path, content: Mapping[str, Any], skeleton: core.Skeleton
) -> str | None:
    """`--accept` 를 거절할 까닭 — 판 다름 · DB 변화 있음 · 조립 기록 없음 · 조립 뒤 바뀜(없으면
    None). `ng` · 고아 · 예시는 거절하지 않는다."""
    if review.stale:
        return "판 다름"
    if review.run.db == "changed":
        return "DB 변화 있음"
    stamp = core.load_assembly_stamp(work)
    if stamp is None:
        return "조립 기록 없음"
    try:
        current = core.assembly_stamp(work, content, skeleton.plan)
    except OSError:
        return "조립 기록 없음"
    return None if stamp == current else "조립 뒤 바뀜"


def check(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.accept:
        if None in (args.work, args.accepted, args.overrides, args.params):
            print(NOT_WRITTEN.format("인자 모자람"))
            return EXIT_NOT_READY
        if not accepted_place_ok(args.accepted):
            print(NOT_WRITTEN.format("자리가 아님"))
            return EXIT_NOT_READY
    review: core.WorkReview | None = None
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
            review = core.work_review(
                skeleton, content, args.work, overrides, params, accepted=args.accepted
            )
            line, details = review.line, list(review.details)
    except core.GuideInputError as exc:
        print(str(exc))
        for problem in exc.problems:
            print(f"  {problem}", file=sys.stderr)
        return EXIT_NOT_READY
    except (OSError, ValueError, KeyError) as exc:
        print(f"읽지 못했습니다 — {type(exc).__name__}")
        return EXIT_NOT_READY
    if args.accept:
        assert review is not None and review.changes is not None
        refusal = accept_refusal(review, args.work, content, skeleton)
        if refusal is not None:
            print(NOT_WRITTEN.format(refusal))
            return EXIT_NOT_READY
        try:
            document = core.accepted_record(
                skeleton, review.changes, review.shots, date=datetime.date.today().isoformat()
            )
            core.save_accepted(args.accepted.resolve(), document)
        except (OSError, ValueError) as exc:
            print(WRITE_FAILED.format(type(exc).__name__))
            return EXIT_NOT_READY
        details.append(f"기준 씀 — {len(document['places'])}자리")
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
