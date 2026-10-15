# Purpose: HOME 벤치마크의 첫 실행 모듈 순서와 사본 모드의 인코딩·출력 단속을 본다.

"""`scripts/benchmark_home.py` 의 첫 회차가 실제 화면과 같은 Figure 를 그리는지, 그리고 사본 모드
(`--data-dir`)의 출력이 사내 Windows 에서도 끝까지 나오고 실데이터를 싣지 않는지.

Components v2 는 **모듈을 처음 불러올 때** `st.components.v2.component(...)` 로 등록되고 등록은
프로세스당 한 번이다. 벤치마크가 첫 `AppTest.run()` 전에 그런 모듈을 불러오면(직접이든, 키 상수를
꺼내려고 `home_preference` 를 불러와 딸려 오든) 등록이 AppTest 실행 밖에서 일어나, 실행 안에서
그 컴포넌트를 부르는 순간 「Component 'capa_horizontal_scrollbar' is not registered.」로 HOME 이
멈추고 Figure 가 4개만 남는다(사내 실데이터 E2E, 202610120655 리뷰 3장).

그래서 두 가지를 본다 — 첫 실행 직전에 등록 모듈이 이미 올라와 있지 않은지(대역으로 바꿔 부르지
않는 것만 예외), 그리고 스크롤바를 대역 없이 둔 채 모든 단계가 정한 Figure 수로 끝나는지. 둘 다 새
프로세스에서 돈다 — 이 pytest 프로세스는 다른 테스트가 화면 모듈을 이미 불러 놓았다.

사본 모드는 둘을 더 본다. 사내 Windows(한국어 로캘)의 파이프 출력은 cp949 라 「—」 같은 기호를 못
쓴다 — 자식의 `PYTHONIOENCODING` 을 cp949 로 두어 그 꼴을 흉내 낸다. 그리고 HOME 이 멈춘 문구에는
공정·제품 이름과 DB 경로가 실린다 — 표지값(`ZZSENTINEL`)을 심은 사본에서 멈춰도 표준 출력·표준
오류 어디에도 표지값과 사본 경로가 없어야 한다(출력은 리뷰 문서를 거쳐 사외로 나간다).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence.repository import DuckDBScenarioRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
SCRIPT = PROJECT_ROOT / "scripts" / "benchmark_home.py"
SENTINEL = "ZZSENTINEL"
NOTE = "프로필 없음 — 켠 비용만 잼"

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

# HOME 계산 안에서 잡히지 않는 예외를 낸다. Streamlit 은 그런 예외를 화면에 그리면서 자기 로거로도
# 표준 오류에 문구와 함께 찍는다.
_UNCAUGHT_IN_HOME = """
import sys
from unittest.mock import patch

sys.path.insert(0, sys.argv[1])
import benchmark_home

with patch(
    "capa_simulation.services.unit_capacity.calculate_unit_capacity",
    side_effect=ZeroDivisionError(sys.argv[3]),
):
    raise SystemExit(benchmark_home.main(["--data-dir", sys.argv[2]]))
"""


def _environment(io_encoding: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(SOURCE_ROOT), *filter(None, [environment.get("PYTHONPATH")])]
    )
    environment["PYTHONIOENCODING"] = io_encoding
    return environment


def _run(*arguments: str, io_encoding: str = "utf-8") -> subprocess.CompletedProcess[str]:
    """새 파이썬으로 돌린다. `io_encoding` 은 자식의 표준 출력 인코딩이다(사내 Windows 는 cp949)."""
    return subprocess.run(
        [sys.executable, *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=PROJECT_ROOT,
        env=_environment(io_encoding),
        timeout=600,
        check=False,
    )


def _seed_copy(folder: Path) -> Path:
    """실 DB 사본 꼴 — 내장 시드만 있는 시뮬레이션 DB. 비교·선행·실행 프로필이 없다."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "capa_simulation.duckdb"
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    ensure_initial_scenario(repository)
    return path


def _phases(stdout: str) -> dict[str, dict[str, object]]:
    return {str(phase["phase"]): phase for phase in json.loads(stdout)["phases"]}


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
    finished = _run("-c", _STOP_AT_FIRST_RUN, str(SCRIPT.parent))
    assert finished.returncode == 0, finished.stderr[-3000:]
    loaded = frozenset(json.loads(finished.stdout.strip().splitlines()[-1]))

    early = sorted((loaded & _component_modules()) - STAND_IN_COMPONENT_MODULES)
    assert early == [], f"첫 AppTest 실행 전에 불러온 컴포넌트 모듈: {early}"
    assert "capa_simulation.components.home_preference" not in loaded


def test_a_copy_folder_is_measured_and_locked_toggles_are_skipped(tmp_path: Path) -> None:
    """비교 토글은 잠겨 건너뛰고, 선행·실행 토글은 켜지지만 그림에 더할 것이 없다고 적는다."""
    _seed_copy(tmp_path)

    finished = _run(str(SCRIPT), "--data-dir", str(tmp_path))

    assert finished.returncode == 0, finished.stderr[-3000:]
    assert str(tmp_path) not in finished.stdout
    phases = _phases(finished.stdout)
    assert phases["cold_summary"]["figure_count"] == 8
    assert phases["on_comparison"] == {"phase": "on_comparison", "skipped": "입력 없음(토글 잠김)"}
    for name in ("on_advance", "on_advance_shipment", "on_execution"):
        assert phases[name]["note"] == NOTE
    assert phases["hidden_main_tab"]["figure_count"] == 0


def test_a_cp949_pipe_still_gets_the_whole_report(tmp_path: Path) -> None:
    """사내 Windows 의 파이프 출력(cp949)에서도 끝까지 찍는다 — 「—」(U+2014)는 cp949 에 없다.

    표준 출력을 UTF-8 로 바꾸지 않으면 note 와 거절 문구에서 `UnicodeEncodeError` 로 멈춘다. 4-3
    관문 pytest 와 런북 6-3 b 가 사내에서 이 꼴로 돈다.
    """
    _seed_copy(tmp_path)

    finished = _run(str(SCRIPT), "--data-dir", str(tmp_path), io_encoding="cp949")

    assert finished.returncode == 0, finished.stderr[-3000:]
    assert _phases(finished.stdout)["on_advance"]["note"] == NOTE

    refused = _run(str(SCRIPT), "--data-dir", str(PROJECT_ROOT / "data"), io_encoding="cp949")

    assert refused.returncode == 2, refused.stderr[-3000:]
    assert refused.stdout.strip() == "저장소의 data/ 는 쓰지 않는다 — 사본 폴더를 준다(런북 6-3)"


def test_the_output_file_is_emptied_and_holds_the_same_report(tmp_path: Path) -> None:
    """런북 6-3 b 는 `--output` 으로 받는다 — PowerShell 5.1 의 `>` 는 자식 출력을 콘솔 코드페이지로
    읽어 UTF-8 한글을 깨뜨린다. 파일은 먼저 비워 지난 실행의 결과가 새것처럼 남지 않는다."""
    _seed_copy(tmp_path / "copy")
    target = tmp_path / "home_bench.json"
    target.write_text("STALE 지난 실행", encoding="utf-8")

    finished = _run(str(SCRIPT), "--data-dir", str(tmp_path / "copy"), "--output", str(target))

    assert finished.returncode == 0, finished.stderr[-3000:]
    assert json.loads(target.read_text(encoding="utf-8")) == json.loads(finished.stdout)


def test_a_failing_copy_names_only_the_phase_kind_and_contract_tables(tmp_path: Path) -> None:
    """HOME 이 멈춘 문구(공정 이름이 실린다)는 찍지 않는다 — 단계·예외 종류·계약 표 이름만.

    사내 E2E 에도 있던 꼴이다 — 한 공정의 `RQ_MODULE` 이 빠져 대당 Capa 가 멈춘다.
    """
    path = _seed_copy(tmp_path)
    with duckdb.connect(str(path)) as connection:
        for schema, table in connection.execute(
            "SELECT table_schema, table_name FROM information_schema.columns "
            "WHERE table_schema IN ('rev_data', 'ref_data') AND column_name = '공정'"
        ).fetchall():
            connection.execute(
                f'UPDATE {schema}.{table} SET "공정" = ? || "공정" WHERE "공정" IS NOT NULL',
                [f"{SENTINEL}-"],
            )
        connection.execute(
            'DELETE FROM ref_data.rq_module WHERE "공정" = '
            '(SELECT min("공정") FROM ref_data.rq_module)'
        )
    target = tmp_path / "home_bench.json"

    finished = _run(str(SCRIPT), "--data-dir", str(tmp_path), "--output", str(target))

    assert finished.returncode == 1
    printed = finished.stdout + finished.stderr + target.read_text(encoding="utf-8")
    assert SENTINEL not in printed
    assert str(tmp_path) not in printed
    assert "Traceback" not in printed
    line = finished.stderr.strip()
    assert line.startswith("cold_summary 실행 실패 — "), line
    assert "RQ_MODULE" in line
    assert target.read_text(encoding="utf-8").strip() == line


def test_an_uncaught_home_exception_does_not_reach_stderr_through_the_streamlit_log(
    tmp_path: Path,
) -> None:
    """잡히지 않은 예외는 Streamlit 이 「Uncaught app execution」 과 함께 문구째 찍는다."""
    _seed_copy(tmp_path)

    finished = _run(
        "-c", _UNCAUGHT_IN_HOME, str(SCRIPT.parent), str(tmp_path), f"{SENTINEL}-uncaught"
    )

    assert finished.returncode == 1
    assert SENTINEL not in finished.stdout + finished.stderr
    assert "ZeroDivisionError" in finished.stderr.strip()


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
    finished = _run(str(SCRIPT))
    assert finished.returncode == 0, finished.stderr[-3000:]
    phases = {
        name: int(str(phase["figure_count"])) for name, phase in _phases(finished.stdout).items()
    }
    assert phases["cold_summary"] == 8
    assert phases["warm_all_on"] == 9
    assert phases["hidden_main_tab"] == 0
