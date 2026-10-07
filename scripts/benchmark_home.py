# Purpose: 격리된 합성 시나리오에서 HOME의 콜드·웜·토글별 Python rerun 시간을 측정한다.

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
"""

import json
import platform
import subprocess
import sys
from contextlib import ExitStack
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

HOME_TAB_KEY = "home_active_tab"


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
    repository.initialize_global_display_order(load_builtin_display_order())
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


def run_phase(app: AppTest, phase: str) -> dict[str, object]:
    from capa_simulation.io.reference_cache import HOME_FIGURE_CACHE_KEY

    started_at = perf_counter()
    app.run()
    elapsed = perf_counter() - started_at
    exceptions = [str(exception.value) for exception in app.exception]
    errors = [str(error.value) for error in app.error]
    if exceptions or errors:
        raise RuntimeError(f"{phase} 실행 실패: {exceptions + errors}")
    chart_count = len(app.get("plotly_chart"))
    cache = app.session_state[HOME_FIGURE_CACHE_KEY]
    applied = next(reversed(cache))[1]
    # 비교가 붙으면 격자 여덟 Figure 아래에 분류별 덤벨 하나가 추가된다.
    expected_charts = 0 if phase == "hidden_main_tab" else 8 + bool(applied.comparison_revision_id)
    if chart_count != expected_charts:
        raise RuntimeError(f"{phase}의 Figure 수가 {expected_charts}개가 아닙니다: {chart_count}")
    return {
        "phase": phase,
        "seconds": round(elapsed, 3),
        "figure_count": chart_count,
    }


def measure_phases(app: AppTest) -> list[dict[str, object]]:
    from capa_simulation.components.home_preference import (
        ADVANCE_SHIPMENT_TOGGLE_KEY,
        ADVANCE_TOGGLE_KEY,
        COMPARISON_REVISION_KEY,
        COMPARISON_TOGGLE_KEY,
        EDP_TOGGLE_KEY,
        EXECUTION_TOGGLE_KEY,
        PLAN_DETAIL_CUSTOMER_KEY,
    )
    from capa_simulation.io.reference_cache import HOME_FIGURE_CACHE_KEY

    results = [run_phase(app, "cold_summary"), run_phase(app, "warm_summary")]

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
        if toggle.disabled:
            raise RuntimeError(f"{phase} 토글을 적용할 입력 조건이 없습니다.")
        toggle.set_value(True)
        result = run_phase(app, f"on_{phase}")
        if app.session_state[key] is not True:
            raise RuntimeError(f"{phase} 토글이 적용되지 않았습니다.")
        cache = app.session_state[HOME_FIGURE_CACHE_KEY]
        applied = next(reversed(cache))[1]
        if phase == "advance" and not (
            applied.show_advance and applied.advance_profile_version > 0
        ):
            raise RuntimeError("선행 프로필이 Figure에 적용되지 않았습니다.")
        if phase == "advance_shipment" and not (
            applied.show_advance_shipment and applied.advance_shipment_profile_version > 0
        ):
            raise RuntimeError("선행 입고 프로필이 Figure에 적용되지 않았습니다.")
        if phase == "execution" and not (
            applied.show_execution and applied.execution_profile_version > 0
        ):
            raise RuntimeError("실행 프로필이 Figure에 적용되지 않았습니다.")
        if (
            phase == "comparison"
            and applied.comparison_revision_id != app.session_state[COMPARISON_REVISION_KEY]
        ):
            raise RuntimeError("비교 리비전이 Figure에 적용되지 않았습니다.")
        results.append(result)

    # 켠 상태 그대로 한 번 더. 캐시가 흡수하는 몫을 가른다.
    results.append(run_phase(app, "warm_all_on"))

    # 숨은 탭으로 옮긴다. `stateful_tabs` 가 Main 의 Figure 를 건너뛰는 몫이다.
    app.session_state[HOME_TAB_KEY] = ":material/history: Past Data"
    results.append(run_phase(app, "hidden_main_tab"))
    return results


def main() -> int:
    # UI/캐시 모듈이 settings 경로를 잡기 전에 임시 경로를 설정한다.
    import capa_simulation.settings as settings

    with TemporaryDirectory(prefix="capa-home-benchmark-") as temporary, ExitStack() as stack:
        root = Path(temporary)
        database_path = root / "scenario.duckdb"
        stack.enter_context(patch.object(settings, "DUCKDB_PATH", database_path))
        stack.enter_context(
            patch.object(settings, "EQUIPMENT_DUCKDB_PATH", root / "equipment.duckdb")
        )
        stack.enter_context(patch.object(settings, "CORE_DATA_CSV_PATH", root / "unused.csv"))
        stack.enter_context(
            patch(
                "capa_simulation.services.builtin_seed.LOCAL_DISPLAY_ORDER_CSV_PATH",
                root / "unused_display_order.csv",
            )
        )
        # AppTest는 브라우저의 custom-component JavaScript를 실행하지 않는다.
        stack.enter_context(
            patch("capa_simulation.components.horizontal_scrollbar.render_horizontal_scrollbar")
        )
        stack.enter_context(
            patch(
                "capa_simulation.components.month_range_picker.render_month_range_picker",
                side_effect=lambda *, start, end, **_: (start, end),
            )
        )
        stack.enter_context(patch("capa_simulation.sync_boot.enable_sync_state_if_managed"))
        stack.enter_context(patch("capa_simulation.sync_boot.heartbeat_if_managed"))
        started_at = perf_counter()
        sample = prepare_sample(database_path)
        setup_seconds = round(perf_counter() - started_at, 3)
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=300)
        results = measure_phases(app)

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
    print(
        json.dumps(
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
                    "합성 표본의 Python rerun; 브라우저 렌더링 제외; "
                    "edp_plan_rows=0이면 EDP 데이터 증감은 미측정"
                ),
                "phases": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
