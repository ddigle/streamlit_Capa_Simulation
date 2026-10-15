# Purpose: HOME 벤치마크가 컴포넌트 등록 모듈을 첫 AppTest 실행 안에서 처음 불러오는지 본다.

"""`scripts/benchmark_home.py` 의 첫 회차가 실제 화면과 같은 Figure 를 그리는지.

Components v2 는 **모듈을 처음 불러올 때** `st.components.v2.component(...)` 로 등록되고 등록은
프로세스당 한 번이다. 벤치마크가 첫 `AppTest.run()` 전에 그런 모듈을 불러오면(직접이든, 키 상수를
꺼내려고 `home_preference` 를 불러와 딸려 오든) 등록이 AppTest 실행 밖에서 일어나, 실행 안에서
그 컴포넌트를 부르는 순간 「Component 'capa_horizontal_scrollbar' is not registered.」로 HOME 이
멈추고 Figure 가 4개만 남는다(사내 실데이터 E2E, 202610120655 리뷰 3장).

그래서 두 가지를 본다 — 첫 실행 직전에 등록 모듈이 이미 올라와 있지 않은지(대역으로 바꿔 부르지
않는 것만 예외), 그리고 스크롤바를 대역 없이 둔 채 모든 단계가 정한 Figure 수로 끝나는지. 둘 다 새
프로세스에서 돈다 — 이 pytest 프로세스는 다른 테스트가 화면 모듈을 이미 불러 놓았다.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence.repository import DuckDBScenarioRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
SCRIPT = PROJECT_ROOT / "scripts" / "benchmark_home.py"

# 벤치마크가 대역으로 바꿔 끼워 실행 안에서 부르지 않는 컴포넌트 모듈. 대역을 걸려고 먼저 불러오는
# 것은 괜찮다 — 등록된 컴포넌트를 부르지 않으니 어디에 등록됐든 상관없다. 월 범위 「적용」 단추는
# AppTest 가 누를 수 없어 늘 「안 누름」(None)으로 둔다.
STAND_IN_COMPONENT_MODULES = frozenset({"capa_simulation.components.month_range_picker"})

# 첫 `AppTest.run()` 에서 멈추고 그때 올라와 있던 이 앱의 모듈을 찍는다.
_STOP_AT_FIRST_RUN = """
import json
import sys

sys.path.insert(0, sys.argv[1])
import benchmark_home
from streamlit.testing.v1 import AppTest


def stop_at_first_run(self, *args, **kwargs):
    loaded = sorted(name for name in sys.modules if name.startswith("capa_simulation."))
    print(json.dumps(loaded))
    raise SystemExit(0)


AppTest.run = stop_at_first_run
sys.argv = [benchmark_home.__file__]
benchmark_home.main()
"""


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(SOURCE_ROOT), *filter(None, [environment.get("PYTHONPATH")])]
    )
    return environment


def _component_modules() -> frozenset[str]:
    """모듈 최상위에서 Components v2 를 등록하는 이 앱의 모듈 — 새 컴포넌트도 저절로 든다."""
    found = set()
    for path in SOURCE_ROOT.rglob("*.py"):
        if "st.components.v2.component(" in path.read_text(encoding="utf-8"):
            found.add(".".join(path.relative_to(SOURCE_ROOT).with_suffix("").parts))
    return frozenset(found)


def test_component_modules_load_first_inside_the_first_app_run() -> None:
    """첫 실행 전에 올라와 있으면 그 컴포넌트는 AppTest 밖에서 등록돼 실행 안에서 「미등록」이다."""
    assert "capa_simulation.components.horizontal_scrollbar" in _component_modules()
    finished = subprocess.run(
        [sys.executable, "-c", _STOP_AT_FIRST_RUN, str(SCRIPT.parent)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PROJECT_ROOT,
        env=_environment(),
        timeout=300,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr[-3000:]
    loaded = frozenset(json.loads(finished.stdout.strip().splitlines()[-1]))

    early = sorted((loaded & _component_modules()) - STAND_IN_COMPONENT_MODULES)
    assert early == [], f"첫 AppTest 실행 전에 불러온 컴포넌트 모듈: {early}"
    assert "capa_simulation.components.home_preference" not in loaded


def test_a_copy_folder_is_measured_and_locked_toggles_are_skipped(tmp_path: Path) -> None:
    """실 DB 사본 꼴 — 내장 시드만 있는 DB 라 비교·선행·실행 프로필이 없다.

    비교 토글은 잠겨 건너뛰고, 선행·실행 토글은 켜지지만 그림에 더할 것이 없어 그렇다고 적는다.
    """
    repository = DuckDBScenarioRepository(tmp_path / "capa_simulation.duckdb")
    repository.initialize()
    ensure_initial_scenario(repository)

    finished = subprocess.run(
        [sys.executable, str(SCRIPT), "--data-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PROJECT_ROOT,
        env=_environment(),
        timeout=600,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr[-3000:]
    report = json.loads(finished.stdout)
    assert str(tmp_path) not in finished.stdout
    phases = {str(phase["phase"]): phase for phase in report["phases"]}
    assert phases["cold_summary"]["figure_count"] == 8
    assert phases["on_comparison"] == {"phase": "on_comparison", "skipped": "입력 없음(토글 잠김)"}
    for name in ("on_advance", "on_advance_shipment", "on_execution"):
        assert phases[name]["note"] == "프로필 없음 — 켠 비용만 잼"
    assert phases["hidden_main_tab"]["figure_count"] == 0


def test_the_repository_data_folder_is_refused() -> None:
    """저장소의 `data/` 는 사용자 앱의 운영 DB 다 — 벤치마크가 마이그레이션을 걸 수 있다."""
    sys.path.insert(0, str(SCRIPT.parent))
    import benchmark_home

    assert benchmark_home.copy_folder_problem(PROJECT_ROOT / "data") == (
        "저장소의 data/ 는 쓰지 않는다 — 사본 폴더를 준다(런북 6-3)"
    )
    assert benchmark_home.copy_folder_problem(PROJECT_ROOT / "no-such-folder") == (
        "그 폴더에 capa_simulation.duckdb 가 없다"
    )


def test_every_phase_draws_its_figures_with_the_real_scrollbar() -> None:
    """스크롤바를 대역 없이 둔다 — 단계마다 Figure 수가 어긋나면 스크립트가 스스로 멈춘다."""
    finished = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PROJECT_ROOT,
        env=_environment(),
        timeout=600,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr[-3000:]
    phases = {
        str(phase["phase"]): int(phase["figure_count"])
        for phase in json.loads(finished.stdout)["phases"]
    }
    assert phases["cold_summary"] == 8
    assert phases["warm_all_on"] == 9
    assert phases["hidden_main_tab"] == 0
