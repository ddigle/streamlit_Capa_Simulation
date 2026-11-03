# Purpose: 검수용 합성 샘플(두 DB · 모듈 견본)을 저장소 밖 뿌리에 차례로 만들거나 개수만 찍는다.

"""검수용 합성 샘플 생성기 — 입구(`docs/review_sample.md`).

    # 만들기 — <뿌리>/data/ 에 두 DB(와 input/ CSV 둘), 기록은 <뿌리>/build-log*.txt
    .venv/bin/python scripts/generate_review_sample.py --out <저장소 밖 뿌리> [--replace]

    # 모듈 견본도 — <뿌리>/modules/ · <뿌리>/module-data/(실행 줄 CAPA_MODULES_ROOT 로 준다)
    .venv/bin/python scripts/generate_review_sample.py --out <뿌리> --modules

    # 이미 만든 뿌리의 개수만(읽기 전용 — 설비 DB 는 임시 사본으로 연다)
    .venv/bin/python scripts/generate_review_sample.py --count <뿌리>

차례는 시뮬레이션 DB(`review_sample_sim.py`) → 설비 DB(`review_sample_equip.py` — 앞 DB 의 최신
공식버전을 사본으로 읽어 짠다) → 모듈 견본(`review_sample_modules.py`, `--modules` 일 때만)이다. 앞
단계가 끝 점검에 어긋나면 뒤 단계를 돌리지 않는다. 이야기 상수는 `review_sample_story.py`, 78컬럼
원천은 `review_sample_core_frame.py` 다.

**지키는 것.** 산출은 늘 저장소 밖이다 — 뿌리가 git 작업 트리(이 저장소 · 워크트리 포함) 안이면
아무것도 쓰지 않고 2 로 끝낸다. 저장소의 `data/` · `modules/` 를 만들지 않는다(사외 저장소에는
`modules/` 를 두지 않는다). `git archive` 사본(가이드 예시판의 앱 사본)은 `.git` 이 없어 받는다 —
`build_page_guide.py --example` 이 사본 뿌리를 그대로 `--out` 으로 준다. 값은 모두 합성(DEMO
꼴)이다.

**종료 코드.** 0 끝까지 통과 · 1 끝 점검 어긋남(시뮬레이션 DB 는 옮기지 않고 준비 자리에 남긴다) ·
2 준비 안 됨(자리 거절 · 이미 있는 산출물에 `--replace` 없음 · 앞 DB 없음).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import review_sample_story as story

EXIT_OK: Final = 0
EXIT_CHECK_FAILED: Final = 1
EXIT_NOT_READY: Final = 2
DATA_DIR_NAME: Final = "data"
SIMULATION_DB_NAME: Final = "capa_simulation.duckdb"
EQUIPMENT_DB_NAME: Final = "equipment_availability.duckdb"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="검수용 합성 샘플을 저장소 밖 뿌리에 만든다.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path, help="산출 뿌리(그 아래 data/ · 기록 · 모듈 견본)")
    mode.add_argument("--count", type=Path, help="이미 만든 뿌리의 개수만 찍는다(읽기 전용)")
    parser.add_argument("--replace", action="store_true", help="이 생성기의 산출물만 덮는다")
    parser.add_argument("--modules", action="store_true", help="모듈 견본 여섯도 만든다")
    parser.add_argument("--no-csv", action="store_true", help="data/input/ CSV 둘을 쓰지 않는다")
    parser.add_argument(
        "--skip-inspect",
        action="store_true",
        help="inspect_revision_calculations 사본 점검을 건너뛴다(앱 계산 점검은 그대로)",
    )
    return parser.parse_args(argv)


def _utf8_streams() -> None:
    """Windows 콘솔에서도 한글 진행 줄이 깨지지 않게 한다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def build(root: Path, *, replace: bool, modules: bool, csv: bool, inspect: bool) -> int:
    """뿌리에 차례로 만든다. 앞 단계가 0 이 아니면 그 코드로 멈춘다."""
    refusal = story.refuse_place(root)
    if refusal is not None:
        print("멈춤 — " + refusal, file=sys.stderr)
        return EXIT_NOT_READY
    data = root / DATA_DIR_NAME
    # 무거운 앱 import 는 만들 때만 — `--count` 는 시뮬레이션 계산 모듈을 읽지 않는다.
    import review_sample_equip
    import review_sample_sim

    sim_args = ["--out", str(data)]
    sim_args += ["--replace"] if replace else []
    sim_args += ["--no-csv"] if not csv else []
    sim_args += ["--skip-inspect"] if not inspect else []
    try:
        code = review_sample_sim.main(sim_args)
    except SystemExit as exc:  # 자리 거절 · 이미 있는 산출물 — 글은 그대로 알린다
        print(f"멈춤 — {exc.code}", file=sys.stderr)
        return EXIT_NOT_READY
    if code != EXIT_OK:
        return code
    equip_args = ["--out", str(data)] + (["--replace"] if replace else [])
    code = review_sample_equip.main(equip_args)
    if code != EXIT_OK or not modules:
        return code
    import review_sample_modules

    return review_sample_modules.main(["--out", str(root)])


def count(root: Path) -> int:
    """뿌리의 두 DB · 모듈 견본 개수를 찍는다. 설비 DB 는 임시 사본으로 연다(원본 바이트 그대로)."""
    from capa_simulation import module_registry, navigation
    from capa_simulation.persistence.repository import DuckDBScenarioRepository

    data = root / DATA_DIR_NAME
    with tempfile.TemporaryDirectory(prefix="review_sample_count_") as folder:
        simulation = data / SIMULATION_DB_NAME
        if simulation.is_file():
            copy = Path(folder) / simulation.name
            shutil.copy2(simulation, copy)
            scenarios = DuckDBScenarioRepository(copy)
            active = scenarios.list_scenarios()
            every = scenarios.list_scenarios(include_archived=True)
            releases = scenarios.list_official_releases()
            print(
                f"시뮬레이션 DB: 시나리오 {len(every)}(활성 {len(active)}) · 공식버전 "
                f"{len(releases)}"
            )
        else:
            print(f"시뮬레이션 DB 없음: {simulation}")
        source = data / EQUIPMENT_DB_NAME
        if source.is_file():
            _count_equipment(source, Path(folder))
        else:
            print(f"설비 DB 없음: {source}")

    modules_root = root / "modules"
    data_root = root / "module-data"
    if modules_root.is_dir():
        scan = module_registry.scan_modules(
            modules_root, disabled="", reserved_titles=navigation.core_page_titles()
        )
        print(f"모듈 뿌리 {modules_root}: {len(scan.records)}개")
        for record in scan.records:
            pages = len(record.manifest.pages) if record.manifest is not None else 0
            reason = f" — {record.reason}" if record.reason else ""
            print(f"  {record.folder_name:<18} {record.state:<6} 화면 {pages}{reason}")
    else:
        print(f"모듈 뿌리 없음: {modules_root}")
    files = [path for path in data_root.rglob("*") if path.is_file()] if data_root.is_dir() else []
    state = "있음" if data_root.is_dir() else "없음"
    print(f"모듈 데이터 뿌리 {data_root}: {state} · 파일 {len(files)}")
    return EXIT_OK


def _count_equipment(source: Path, folder: Path) -> None:
    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

    copy = folder / source.name
    shutil.copy2(source, copy)
    repo = DuckDBEquipmentRepository(copy)
    wal = "있음" if source.with_name(source.name + ".wal").exists() else "없음"
    print(f"설비 DB {source} ({source.stat().st_size / 1e6:.1f}MB, .wal {wal})")
    release = repo.latest_equipment_release()
    print(
        f"  설비 공식 v{release.release_no if release else '-'} · "
        f"공통 대장 리비전 {len(repo.list_revisions(limit=50))}"
    )
    for summary in repo.list_equipment_scenarios():
        revisions = sorted(
            repo.list_schedule_revisions(summary.equipment_scenario_id),
            key=lambda item: item.revision_no,
        )
        names = " · ".join(
            f"r{item.revision_no} {item.origin}"
            + (f"「{item.revision_name}」" if item.revision_name else "")
            for item in revisions
        )
        print(
            f"  설비 시나리오 「{summary.scenario_name}」 리비전 {len(revisions)}: {names}"
            f" · 배치 차이(호기·요소·이름표) {summary.latest_layout_rows}"
        )
    snapshot = repo.load_official_snapshot()
    if snapshot is not None:
        equipment = snapshot.equipment
        print(
            f"  공식 쌍: 호기 행 {len(equipment)} · 공정 {equipment['공정소분류'].nunique()}"
            f" · 기존보유 행 {len(snapshot.baseline)} · 비가동 {len(snapshot.downtime)}"
        )
        kinds = Counter(snapshot.downtime["비가동유형"].astype(str)).most_common()
        print(f"  비가동 유형 {kinds}")
        print(f"  사용기준 {equipment['사용기준'].fillna('(빈칸)').value_counts().to_dict()}")
        print(f"  Qual상태 {equipment['Qual상태'].fillna('(빈칸)').value_counts().to_dict()}")
        print(
            f"  모듈 묶음 {equipment['Main 설비'].dropna().nunique()}"
            f" · 레이아웃표시 N {int(equipment['레이아웃표시'].eq('N').sum())}"
            f" · 보관 {int(equipment['보관유무'].eq('Y').sum())}"
        )
    print(
        f"  Cut-off {len(repo.load_process_cutoff())}공정 · 표준 목표 주차 가용 "
        f"{len(repo.load_standard_target_availability())}행"
    )
    manual = repo.load_manual_downtime()
    print(f"  입력 비가동 칸 {len(manual.rows)} · version {manual.version}")
    profile = repo.load_shortening_filter_profile()
    print(
        f"  공용 조회 조건 {profile.start_month}–{profile.end_month}"
        f" · 공정 {len(profile.processes)}"
    )
    print(f"  기준선 {[item.name for item in repo.list_shortening_baselines()]}")
    states = repo.load_floor_states()
    print(f"  층 사용 version {states.version} · 비활성 {len(states.rows)}")
    canvases = repo.load_floor_layout_canvases()
    marks = sum(len(repo.load_floor_layout_marks(*key)) for key in canvases)
    fab = "있음" if repo.load_fab_layout_profile() else "기본"
    print(f"  층 캔버스 {len(canvases)} · 도면 요소 {marks} · FAB 배치 {fab}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    _utf8_streams()
    if args.count is not None:
        return count(args.count.expanduser())
    return build(
        args.out.expanduser(),
        replace=args.replace,
        modules=args.modules,
        csv=not args.no_csv,
        inspect=not args.skip_inspect,
    )


if __name__ == "__main__":
    raise SystemExit(main())
