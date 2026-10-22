# Purpose: 합성 표본이나 실 DB 사본에서 HOME의 콜드·웜·토글별 Python rerun 시간을 측정한다.

"""HOME 의 파이썬 rerun 시간을 단계별로 잰다.

**세션 키는 화면이 실제로 읽는 이름이어야 한다.** 예전에는 아무도 읽지 않는
`dashboard_show_details` 를 심어 두고 「상세」 단계를 잰다고 적었다. 그 단계는 직전 단계와
같은 화면을 한 번 더 그린 것이라 늘 캐시 적중만 쟀고, 상세를 켜는 비용은 한 번도 잰 적이
없다. 키는 `components/home_preference.py` 에서 가져온다 — 여기 문자열로 베껴 두면 한쪽만
바뀌어도 드러나지 않는다.

임시 DB에 합성 시드·비교 시나리오·선행/실행 프로필을 준비하고 같은 시나리오에서
토글을 누적해 켠다. 시나리오를 바꾸면 HOME 토글은 기본값으로 돌아간다.
로컬 DB·CSV·동기화 상태는 사용하지 않는다. 입력 준비 시간은 별도로 기록한다.

수치는 이 PC 의 합성 표본 기준이고 실데이터 크기에 따라 달라진다. 절대값이 아니라
**단계 사이의 차이**를 본다.

**실 DB 사본(`--data-dir <사본 폴더>`).** 사내 런북 6-3 이 실 DB 사본으로 HOME 을 잴 때 쓴다. 합성
표본을 만들지 않고 그 폴더의 두 DB 를 그대로 쓰며, 비교·선행·실행 프로필이 없어 잠긴 토글은
`skipped` 로 적고 건너뛴다. 저장소의 `data/`(사용자 앱의 운영 DB)와 저장소 안은 받지 않는다 — 앱이
마이그레이션을 걸 수 있어 저장소 밖 사본에만 돌린다. 출력에는 사본의 이름·경로·행 수가 없다. HOME 이
멈추면 그 문구(공정·제품 이름, DB 오류면 사본 경로가 실린다)도 찍지 않는다 — 단계·예외 종류·문구에
든 계약 표 이름(`RQ_*`)만 한 줄로 찍고 1 로 끝난다(`inspect_revision_calculations.py` 와 같은 규칙).
잡히지 않은 예외는 Streamlit 이 자기 로거로 문구를 표준 오류에 찍으므로 사본을 재는 동안은 로그를
끈다. 출력은 리뷰 문서를 거쳐 사외로 나간다.

**출력은 UTF-8 이다.** 사내 Windows(한국어 로캘)의 파이프 출력은 cp949 라 「—」 같은 기호에서
멈추므로 표준 출력·오류를 UTF-8 로 바꾼다. PowerShell 5.1 의 `>` 는 그 출력을 콘솔 코드페이지로
읽어 한글을 깨뜨리므로 파일은 `--output` 으로 받는다(런북 6-3 b).

**화면 모듈은 첫 `AppTest.run()` 안에서 처음 불러온다.** Components v2(가로 스크롤바
등)는 모듈을 처음 불러올 때 등록되고 등록은 프로세스당 한 번이다. 첫 실행 전에 그런
모듈을 불러오면 — 키 상수를 꺼내려고 `home_preference` 를 불러와도 스크롤바가 딸려
온다 — 등록이 AppTest 실행 밖에서 일어나 HOME 이 「Component 'capa_horizontal_scrollbar'
is not registered.」로 멈추고 Figure 가 4개만 남는다(사내 실데이터 E2E, 202610120655
리뷰 3장). 그래서 키 상수는 첫 단계를 잰 뒤에 꺼내고, 스크롤바는 대역 없이 실제로
부른다 — 대역을 걸려면 그 모듈을 먼저 불러와야 해 같은 함정이 된다. 월 범위 「적용」
단추만 대역이다(AppTest 가 누를 수 없어 늘 「안 누름」이다). `tests/test_benchmark_home.py`
가 첫 실행 직전에 올라온 모듈과 단계별 Figure 수를 본다.
"""

import argparse
import json
import logging
import os
import platform
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from contextlib import ExitStack
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TYPE_CHECKING, TextIO
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

if TYPE_CHECKING:
    from capa_simulation.components.home_rendering import LobFigureKey

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

HOME_TAB_KEY = "home_active_tab"
_COPY_MODE_SUFFIX = "(사본이라 문구는 찍지 않는다)"


class BenchmarkStop(RuntimeError):
    """벤치마크가 스스로 멈춘 까닭. 문구는 이 파일이 쓴 글자뿐이라(값·경로 없음) 사본도 찍는다."""


class HomeFailure(RuntimeError):
    """HOME 이 예외나 오류 표시로 끝난 단계. 문구에는 공정·제품 이름과 DB 경로가 실릴 수 있다."""

    def __init__(self, phase: str, failures: Sequence[tuple[str, str]]) -> None:
        super().__init__(f"{phase} 실행 실패: {[message for _, message in failures]}")
        self.phase = phase
        # (종류, 문구) — 종류는 예외 클래스 이름이거나 오류 표시면 `st.error` 다.
        self.failures = tuple(failures)


def copy_mode_failure(exc: BaseException) -> str:
    """사본 모드에서 찍는 실패 한 줄 — HOME 의 문구 대신 단계·예외 종류·계약 표 이름만."""
    if isinstance(exc, BenchmarkStop):
        return str(exc)
    if not isinstance(exc, HomeFailure):
        return f"실행 실패 — {type(exc).__name__} {_COPY_MODE_SUFFIX}"
    # 문구에서 무엇을 남길지는 전 리비전 계산 집계와 한 규칙이다.
    from inspect_revision_calculations import contract_tables_in

    kinds = Counter(kind for kind, _ in exc.failures)
    named = contract_tables_in("\n".join(message for _, message in exc.failures))
    return (
        f"{exc.phase} 실행 실패 — "
        + " · ".join(f"{kind} {count}" for kind, count in sorted(kinds.items()))
        + f" · 문구가 가리키는 표 {', '.join(named) or '-'} {_COPY_MODE_SUFFIX}"
    )


def prepare_sample(database_path: Path) -> dict[str, object]:
    """수량이 다른 비교 시나리오와 비어 있지 않은 조정 프로필을 임시 DB에 준비한다."""
    from capa_simulation.application_bootstrap import ensure_initial_scenario
    from capa_simulation.persistence.models import ScenarioCreate
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.advance_shipment import ADVANCE_SHIPMENT_VALUE_COLUMN
    from capa_simulation.services.builtin_seed import load_builtin_display_order
    from capa_simulation.services.frame_contracts import match_key
    from capa_simulation.services.product_type import EDP_PRODUCT_TYPE, PRODUCT_TYPE_COLUMN

    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order)
    release = ensure_initial_scenario(repository).release
    if release is None:
        raise RuntimeError("벤치마크 합성 공식 시나리오가 만들어지지 않았습니다.")
    snapshot = repository.load_revision(release.revision_id)
    tables = dict(snapshot.tables)
    plan = tables["RQ_PKG_PLAN"].copy()
    plan["생산수량"] = pd.to_numeric(plan["생산수량"]) * 0.9
    tables["RQ_PKG_PLAN"] = plan
    comparison = repository.create_scenario(
        ScenarioCreate(
            scenario_name="BENCHMARK 비교",
            source_simulation_code="BENCHMARK-COMPARE",
            source_simulation_name="BENCHMARK 비교",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        tables,
        snapshot.preset,
    )
    repository.replace_global_comparison_scenario(
        comparison.scenario.scenario_id,
        comparison.revision.revision_id,
        source="합성 벤치마크",
    )
    month = snapshot.preset.start_month
    process = snapshot.preset.included_processes[0]
    repository.replace_global_advance_load(
        pd.DataFrame({"생산계획년월": [month], "선행 물량": [2.5]}), source="합성 벤치마크"
    )
    repository.replace_global_advance_shipment(
        pd.DataFrame({"생산계획년월": [month], ADVANCE_SHIPMENT_VALUE_COLUMN: [1.5]}),
        source="합성 벤치마크",
    )
    repository.replace_global_execution_capacity(
        pd.DataFrame(
            {"생산계획년월": [month], "공정": [process], "증감 확보율": [-5.0], "비고": ["합성"]}
        ),
        source="합성 벤치마크",
    )
    return {
        "source": "services/builtin_seed.py",
        "rq_rows": {name: len(frame) for name, frame in snapshot.tables.items()},
        "month_count": int(plan["생산계획년월"].nunique()),
        "advance_rows": len(repository.load_global_advance_load().rows),
        "advance_shipment_rows": len(repository.load_global_advance_shipment().rows),
        "execution_rows": len(repository.load_global_execution_capacity().rows),
        "comparison_plan_factor": 0.9,
        "edp_plan_rows": int(match_key(plan[PRODUCT_TYPE_COLUMN]).eq(EDP_PRODUCT_TYPE).sum()),
    }


def applied_lob_key(app: AppTest) -> "LobFigureKey":
    """이번 회차 화면에 나간 LOB 묶음의 Figure 키. 켠 토글이 그림에 실제로 적용됐는지 본다."""
    from capa_simulation.components.home_rendering import LOB_FIGURES, latest_home_figure_key
    from capa_simulation.io.reference_cache import HOME_FIGURE_CACHE_KEY

    applied = latest_home_figure_key(app.session_state[HOME_FIGURE_CACHE_KEY], LOB_FIGURES)
    if applied is None:
        raise BenchmarkStop("LOB Figure 캐시가 비어 있습니다.")
    return applied


def run_phase(app: AppTest, phase: str) -> dict[str, object]:
    started_at = perf_counter()
    app.run()
    elapsed = perf_counter() - started_at
    failures = [
        (str(exception.proto.type or "Exception"), str(exception.value))
        for exception in app.exception
    ]
    failures.extend(("st.error", str(error.value)) for error in app.error)
    if failures:
        raise HomeFailure(phase, failures)
    chart_count = len(app.get("plotly_chart"))
    applied = applied_lob_key(app)
    # 비교가 붙으면 격자 여덟 Figure 아래에 분류별 덤벨 하나가 추가된다.
    expected_charts = 0 if phase == "hidden_main_tab" else 8 + bool(applied.comparison_revision_id)
    if chart_count != expected_charts:
        raise BenchmarkStop(f"{phase}의 Figure 수가 {expected_charts}개가 아닙니다: {chart_count}")
    return {
        "phase": phase,
        "seconds": round(elapsed, 3),
        "figure_count": chart_count,
    }


def measure_phases(app: AppTest, *, skip_unavailable: bool = False) -> list[dict[str, object]]:
    """단계별로 잰다. `skip_unavailable` 이면 입력이 없어 잠긴 토글은 건너뛰고 그렇다고 적는다.

    합성 표본은 모든 토글의 입력(비교·선행·실행 프로필)을 갖춰 두므로 잠긴 토글은 결함이다.
    실 DB 사본(`--data-dir`)은 그 프로필이 없을 수 있다 — 그때만 건너뛴다.
    """
    results = [run_phase(app, "cold_summary"), run_phase(app, "warm_summary")]

    # 첫 실행이 화면 모듈을 불러온 **뒤에** 꺼낸다(모듈 설명 — 먼저 꺼내면 스크롤바가 미등록이다).
    from capa_simulation.components.home_preference import (
        ADVANCE_SHIPMENT_TOGGLE_KEY,
        ADVANCE_TOGGLE_KEY,
        COMPARISON_REVISION_KEY,
        COMPARISON_TOGGLE_KEY,
        EDP_TOGGLE_KEY,
        EXECUTION_TOGGLE_KEY,
        PLAN_DETAIL_CUSTOMER_KEY,
    )

    # 토글을 하나씩 켠다. 끄지 않고 쌓는 것은 실제 사용이 그렇기 때문이다 — 켜 둔 채로
    # 다음 것을 켠다. 각 줄의 차이가 그 토글 하나가 더하는 몫이다.
    for phase, key in (
        ("plan_detail_customer", PLAN_DETAIL_CUSTOMER_KEY),
        ("advance", ADVANCE_TOGGLE_KEY),
        ("advance_shipment", ADVANCE_SHIPMENT_TOGGLE_KEY),
        ("execution", EXECUTION_TOGGLE_KEY),
        ("comparison", COMPARISON_TOGGLE_KEY),
        ("edp", EDP_TOGGLE_KEY),
    ):
        toggle = app.toggle(key=key)
        if toggle.disabled and skip_unavailable:
            results.append({"phase": f"on_{phase}", "skipped": "입력 없음(토글 잠김)"})
            continue
        if toggle.disabled:
            raise BenchmarkStop(f"{phase} 토글을 적용할 입력 조건이 없습니다.")
        toggle.set_value(True)
        result = run_phase(app, f"on_{phase}")
        if app.session_state[key] is not True:
            raise BenchmarkStop(f"{phase} 토글이 적용되지 않았습니다.")
        applied = applied_lob_key(app)
        problem = None
        if phase == "advance" and not (
            applied.show_advance and applied.advance_profile_version > 0
        ):
            problem = "선행 프로필이 Figure에 적용되지 않았습니다."
        if phase == "advance_shipment" and not (
            applied.show_advance_shipment and applied.advance_shipment_profile_version > 0
        ):
            problem = "선행 입고 프로필이 Figure에 적용되지 않았습니다."
        if phase == "execution" and not (
            applied.show_execution and applied.execution_profile_version > 0
        ):
            problem = "실행 프로필이 Figure에 적용되지 않았습니다."
        if (
            phase == "comparison"
            and applied.comparison_revision_id != app.session_state[COMPARISON_REVISION_KEY]
        ):
            problem = "비교 리비전이 Figure에 적용되지 않았습니다."
        if problem is not None and not skip_unavailable:
            raise BenchmarkStop(problem)
        if problem is not None:
            # 사본에 그 프로필이 없으면 토글은 켜지지만 그림에 더할 것이 없다 — 켠 비용만 잰 것이다.
            result["note"] = "프로필 없음 — 켠 비용만 잼"
        results.append(result)

    # 켠 상태 그대로 한 번 더. 캐시가 흡수하는 몫을 가른다.
    results.append(run_phase(app, "warm_all_on"))

    # 숨은 탭으로 옮긴다. `stateful_tabs` 가 Main 의 Figure 를 건너뛰는 몫이다.
    app.session_state[HOME_TAB_KEY] = ":material/history: Past Data"
    results.append(run_phase(app, "hidden_main_tab"))
    return results


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HOME 단계별 Python rerun 시간. 기본은 임시 DB 의 합성 표본이다."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help=(
            "실 DB 사본 폴더(capa_simulation.duckdb 가 있는 곳 — 사내 런북 6-3). 저장소의 "
            "data/ 는 받지 않는다. 입력이 없는 토글은 건너뛴다"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="같은 출력을 이 파일에도 쓴다(UTF-8, 먼저 비운다). 저장소 밖 경로를 준다",
    )
    return parser.parse_args(argv)


def copy_folder_problem(data_dir: Path) -> str | None:
    """`--data-dir` 로 쓸 수 없는 까닭. 쓸 수 있으면 None.

    저장소의 `data/` 는 사용자 앱이 쓰는 운영 DB 다 — 벤치마크는 마이그레이션을 걸고 세션 상태를
    만들므로 사본에만 돌린다. 그 아래 폴더와 git 저장소 안도 받지 않는다
    (`inspect_revision_calculations.py` 의 `--database` 거절과 같은 판정 —
    `settings.is_operational_database_place`. 운영 DB 옆에 둔 사본은 경로 한 글자 틀림이 곧 운영 DB
    다).
    """
    from capa_simulation.settings import is_operational_database_place

    folder = data_dir.expanduser().resolve()
    if is_operational_database_place(folder, (PROJECT_ROOT / "data" / "capa_simulation.duckdb",)):
        return "저장소 안(data/ 포함)은 쓰지 않는다 — 저장소 밖 사본 폴더를 준다(런북 6-3)"
    if not (folder / "capa_simulation.duckdb").is_file():
        return "그 폴더에 capa_simulation.duckdb 가 없다"
    return None


def _use_utf8_output() -> None:
    # Windows(한국어 로캘)의 콘솔·파이프 기본 인코딩(cp949)은 이 출력의 「—」 같은 기호를 못 쓴다.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _emit(text: str, output: Path | None, stream: TextIO) -> None:
    """화면과 `--output` 파일에 같은 글을 쓴다. 실행마다 한 번만 부른다."""
    print(text, file=stream, flush=True)
    if output is not None:
        output.write_text(text + "\n", encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    _use_utf8_output()
    args = parse_args(argv)
    data_dir: Path | None = args.data_dir
    output: Path | None = args.output
    if output is not None:
        # 먼저 비운다 — 일찍 끝나도 지난 실행의 결과가 새것처럼 남지 않는다.
        output.write_text("", encoding="utf-8")
    if data_dir is not None:
        problem = copy_folder_problem(data_dir)
        if problem is not None:
            _emit(problem, output, sys.stdout)
            return 2
    # UI/캐시 모듈이 settings 경로를 잡기 전에 임시 경로를 설정한다.
    import capa_simulation.settings as settings

    with TemporaryDirectory(prefix="capa-home-benchmark-") as temporary, ExitStack() as stack:
        root = Path(temporary)
        data_root = root if data_dir is None else data_dir.expanduser().resolve()
        database_path = data_root / (
            "scenario.duckdb" if data_dir is None else "capa_simulation.duckdb"
        )
        equipment_path = data_root / (
            "equipment.duckdb" if data_dir is None else "equipment_availability.duckdb"
        )
        stack.enter_context(patch.object(settings, "DUCKDB_PATH", database_path))
        stack.enter_context(patch.object(settings, "EQUIPMENT_DUCKDB_PATH", equipment_path))
        stack.enter_context(patch.object(settings, "CORE_DATA_CSV_PATH", root / "unused.csv"))
        stack.enter_context(
            patch(
                "capa_simulation.services.builtin_seed.LOCAL_DISPLAY_ORDER_CSV_PATH",
                root / "unused_display_order.csv",
            )
        )
        # 「적용」 단추만 대역이다 — AppTest 는 컴포넌트 JavaScript 를 돌리지 않아 누를 수 없다.
        # 스크롤바는 대역을 걸지 않는다(모듈 설명).
        stack.enter_context(
            patch(
                "capa_simulation.components.month_range_picker.render_month_range_apply",
                side_effect=lambda **_: None,
            )
        )
        stack.enter_context(patch("capa_simulation.sync_boot.enable_sync_state_if_managed"))
        stack.enter_context(patch("capa_simulation.sync_boot.heartbeat_if_managed"))
        if data_dir is not None:
            # 잡히지 않은 HOME 예외는 Streamlit 로거가 문구째 표준 오류에 찍는다(모듈 설명).
            logging.disable(logging.CRITICAL)
            stack.callback(logging.disable, logging.NOTSET)
        # 공식버전 자동 갱신 예약의 실행 줄 허락을 뺀다. 앱을 띄운 창에서 이 스크립트를 돌려도
        # AppTest 의 app.py 가 임시 DB 로 예약 스레드를 세우지 않는다.
        stack.enter_context(patch.dict(os.environ))
        os.environ.pop("CAPA_AUTO_OFFICIAL_UPDATE", None)
        started_at = perf_counter()
        # 사본은 이름·경로·행 수를 찍지 않는다 — 출력이 리뷰 문서로 나간다.
        sample = (
            prepare_sample(database_path)
            if data_dir is None
            else {"source": "--data-dir 사본(이름·경로·행 수는 찍지 않는다)"}
        )
        setup_seconds = round(perf_counter() - started_at, 3)
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=300)
        try:
            results = measure_phases(app, skip_unavailable=data_dir is not None)
        except Exception as exc:
            if data_dir is None:
                raise
            _emit(copy_mode_failure(exc), output, sys.stderr)
            return 1

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    report = json.dumps(
        {
            "revision": revision,
            "working_tree_dirty": bool(dirty),
            "python": platform.python_version(),
            "packages": {
                name: version(name) for name in ("streamlit", "pandas", "plotly", "duckdb")
            },
            "sample": sample,
            "setup_seconds": setup_seconds,
            "measurement": (
                (
                    "합성 표본의 Python rerun; 브라우저 렌더링 제외; "
                    "edp_plan_rows=0이면 EDP 데이터 증감은 미측정"
                )
                if data_dir is None
                else "실 DB 사본의 Python rerun; 브라우저 렌더링 제외; 잠긴 토글은 skipped"
            ),
            "phases": results,
        },
        ensure_ascii=False,
        indent=2,
    )
    _emit(report, output, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
