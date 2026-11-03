# Purpose: 검수용 합성 샘플 생성기가 저장소 밖에 두 DB · 공식버전 · 모듈 견본을 세우는지 본다.

"""검수용 합성 샘플 생성기(`scripts/generate_review_sample.py`)의 계약.

이야기는 크기가 고정이다(52개 끝 점검이 26개월 · 24공정 판정 칸에 맞춰져 있다) — 여기서는 사본 점검
(`inspect_revision_calculations`)과 CSV 를 빼고 한 번만 돌려(약 40초) 생성기가 끝 점검을 통과하고
세우는 것의 **꼴**을 본다. 수는 업무 계약이 아니라 이야기 꼴이다(`docs/review_sample.md`). 앱과 같은
길로 자식 프로세스에서 돈다 — `PYTHONPATH` 맨 앞이 이 저장소 `src` 다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import generate_review_sample as generator  # noqa: E402
import review_sample_modules as modules_step  # noqa: E402
import review_sample_story as story  # noqa: E402

from capa_simulation import module_registry, navigation  # noqa: E402
from capa_simulation.persistence.equipment_repository import (  # noqa: E402
    DuckDBEquipmentRepository,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository  # noqa: E402

GUIDE_PLAN = PROJECT_ROOT / "src" / "capa_simulation" / "guides" / "howto" / "lob" / "plan.json"
GENERATOR_TIMEOUT_SECONDS = 600


@pytest.fixture(scope="module")
def sample_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("review_sample") / "out"
    env = dict(os.environ)
    source = str(PROJECT_ROOT / "src")
    rest = [part for part in env.get("PYTHONPATH", "").split(os.pathsep) if part]
    env["PYTHONPATH"] = os.pathsep.join([source, *rest])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "generate_review_sample.py"),
            "--out",
            str(root),
            "--modules",
            "--no-csv",
            "--skip-inspect",
        ],
        cwd=str(root.parent),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GENERATOR_TIMEOUT_SECONDS,
        check=False,
    )
    assert completed.returncode == generator.EXIT_OK, (
        completed.stdout[-3000:] + "\n" + completed.stderr[-3000:]
    )
    return root


def test_the_simulation_database_holds_the_story_scenarios_and_four_officials(
    sample_root: Path,
) -> None:
    data = sample_root / generator.DATA_DIR_NAME
    database = data / generator.SIMULATION_DB_NAME
    assert database.is_file()
    assert not database.with_name(database.name + ".wal").exists()
    assert not (data / "input").exists()  # --no-csv

    repository = DuckDBScenarioRepository(database)
    active = repository.list_scenarios()
    every = repository.list_scenarios(include_archived=True)
    assert (len(active), len(every)) == (7, 9)
    names = {summary.scenario_name for summary in every}
    assert {story.S1_NAME, story.S2_NAME, story.S3_NAME, story.S4_NAME, story.S5_NAME} <= names
    revisions = sum(len(repository.list_revisions(item.scenario_id)) for item in every)
    assert revisions == 16

    releases = repository.list_official_releases()
    assert sorted(release.release_no for release in releases) == [1, 2, 3, 4]
    latest = repository.latest_official_release()
    assert latest is not None
    assert (latest.release_no, latest.scenario_name, latest.revision_no) == (4, story.S1_NAME, 3)


def test_the_equipment_database_holds_three_scenarios_and_the_official_v3(
    sample_root: Path,
) -> None:
    database = sample_root / generator.DATA_DIR_NAME / generator.EQUIPMENT_DB_NAME
    assert database.is_file()
    repository = DuckDBEquipmentRepository(database)
    scenarios = repository.list_equipment_scenarios()
    assert len(scenarios) == 3
    release = repository.latest_equipment_release()
    assert release is not None
    assert (release.release_no, release.revision_no) == (3, 3)
    snapshot = repository.load_official_snapshot()
    assert snapshot is not None
    assert 0 < len(snapshot.equipment) < 1_000
    names = snapshot.equipment["설비명"].astype(str)
    assert names.str.startswith("DEMO-").all()


def test_the_module_samples_keep_their_expected_states(sample_root: Path) -> None:
    scan = module_registry.scan_modules(
        sample_root / "modules", disabled="", reserved_titles=navigation.core_page_titles()
    )
    states = {record.folder_name: record.state for record in scan.records}
    assert states == modules_step.EXPECTED
    assert (sample_root / "module-data").is_dir()
    assert not any((sample_root / "module-data").iterdir())


def test_the_build_logs_record_every_check_passing(sample_root: Path) -> None:
    sim_log = (sample_root / "build-log-sim.txt").read_text(encoding="utf-8")
    assert "점검 실패 0건" in sim_log
    assert " FAIL " not in sim_log
    equip_log = (sample_root / "build-log-equip.txt").read_text(encoding="utf-8")
    assert "결과: 통과" in equip_log


def test_count_reads_the_root_without_writing(
    sample_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = sample_root / generator.DATA_DIR_NAME
    before = {path.name: path.stat().st_mtime_ns for path in data.iterdir()}
    assert generator.main(["--count", str(sample_root)]) == generator.EXIT_OK
    out = capsys.readouterr().out
    assert "시뮬레이션 DB: 시나리오 9(활성 7) · 공식버전 4" in out
    assert "설비 공식 v3" in out
    assert "모듈 뿌리" in out
    assert {path.name: path.stat().st_mtime_ns for path in data.iterdir()} == before


def test_the_guide_plan_edits_the_story_cell() -> None:
    """가이드 원고의 고칠 칸(공정 · 달 · 더할 대수)이 샘플 이야기 칸과 맞물린다.

    26.12 Pre B/D 소요 33.3 · 가용 32(96.1%) — 가용 +2 로 부족을 벗어난다(102.1%).
    """
    params = json.loads(GUIDE_PLAN.read_text(encoding="utf-8"))["params"]
    assert params["edit_process"]["default"] == story.STORY_PROCESS
    assert params["edit_month"]["default"] == str(story.STORY_MONTH)
    delta = params["edit_delta"]["default"]
    before = story.STORY_AVAILABLE / story.STORY_REQUIRED * 100
    after = (story.STORY_AVAILABLE + delta) / story.STORY_REQUIRED * 100
    assert (round(before, 1), round(after, 1)) == (96.1, 102.1)


def test_a_root_inside_a_git_work_tree_is_refused_before_anything_is_written(
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = PROJECT_ROOT / "data" / "review-sample-refused"
    assert generator.main(["--out", str(root)]) == generator.EXIT_NOT_READY
    assert not root.exists()
    assert "git 작업 트리" in capsys.readouterr().err


def test_the_place_guard_accepts_a_folder_outside_git(tmp_path: Path) -> None:
    assert story.git_work_tree(tmp_path / "not-yet" / "data") is None
    assert story.refuse_place(tmp_path / "not-yet") is None
    (tmp_path / ".git").mkdir()
    assert story.git_work_tree(tmp_path / "not-yet" / "data") == tmp_path.resolve()
    assert story.refuse_place(tmp_path / "not-yet") is not None
