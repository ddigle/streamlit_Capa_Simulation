# Purpose: 설비 DB 최신 리비전 id·Cut-off 읽기 캐시가 앱 저장·파일 변경을 놓치지 않는지 검사한다.

"""「지금 무엇이 저장돼 있나」 읽기 캐시(`persistence/equipment_cache.py`).

가용설비 현황·Space 는 회차마다 최신 리비전 id 와 Cut-off 를 읽느라 설비 DB 를 열었다. 이제 키를
DB·WAL stat 으로 둔 캐시에서 받는다. 놓치면 옛 리비전·옛 Cut-off 로 센 숫자가 나오므로 두 장치를
따로 본다.

1. **비우기(1차)** — 이 앱의 저장은 저장 직후 캐시를 비운다. stat 을 일부러 고정해도 저장한 값이
   다음 읽기에 나와야 한다.
2. **stat(2차)** — 이 앱을 지나지 않은 쓰기(다른 Repository 객체 = 다른 프로세스 흉내)는 파일
   stat 이 바뀌어 다시 읽는다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_pages import _open_tab, _page_script

from capa_simulation.components.cutoff_management import CUTOFF_DRAFT_KEY
from capa_simulation.persistence import equipment_cache
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_equipment_snapshot_cache,
    clear_process_cutoff_cache,
    latest_equipment_revision_id,
    load_latest_equipment_snapshot,
    load_process_cutoff,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_samples import (
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.monthly_equipment_availability import processes_in

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"


def _cutoff(days: float, processes: list[str] | None = None) -> pd.DataFrame:
    names = processes or ["Process-A"]
    return pd.DataFrame(
        {"공정": names, "Cutoff일수": [days] * len(names), "비고": [None] * len(names)}
    )


def _seeded(tmp_path: Path) -> tuple[str, DuckDBEquipmentRepository]:
    """r1 과 Cut-off 하나를 저장한 DB. 돌려주는 Repository 는 **이 앱 밖의 쓰기**를 흉내 낸다."""
    database = tmp_path / "equipment.duckdb"
    outsider = DuckDBEquipmentRepository(database)
    outsider.initialize()
    outsider.save_snapshot(_baseline(), _equipment(), _downtime(), note="r1")
    outsider.save_process_cutoff(_cutoff(10.0))
    clear_equipment_repository()
    return str(database.resolve()), outsider


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """두 읽기가 실제로 DB 를 몇 번 열었나."""
    counts = {"latest": 0, "cutoff": 0}
    latest = DuckDBEquipmentRepository.latest_revision_id
    cutoff = DuckDBEquipmentRepository.load_process_cutoff

    def counting_latest(self: DuckDBEquipmentRepository) -> str | None:
        counts["latest"] += 1
        return latest(self)

    def counting_cutoff(self: DuckDBEquipmentRepository) -> pd.DataFrame:
        counts["cutoff"] += 1
        return cutoff(self)

    monkeypatch.setattr(DuckDBEquipmentRepository, "latest_revision_id", counting_latest)
    monkeypatch.setattr(DuckDBEquipmentRepository, "load_process_cutoff", counting_cutoff)
    return counts


def test_unchanged_reads_do_not_open_the_database(tmp_path: Path, counted: dict[str, int]) -> None:
    database, outsider = _seeded(tmp_path)
    expected = outsider.latest_revision_id()
    counted.update(latest=0, cutoff=0)  # 심을 때의 읽기(저장이 돌려주는 값)는 세지 않는다

    for _ in range(3):
        assert latest_equipment_revision_id(database) == expected
        pd.testing.assert_frame_equal(load_process_cutoff(database), outsider.load_process_cutoff())

    assert counted["latest"] == 1
    # 위 루프의 `outsider.load_process_cutoff()` 셋 + 캐시 한 번
    assert counted["cutoff"] == 4
    clear_equipment_repository()


def test_a_write_outside_the_app_is_seen_through_the_file_stat(
    tmp_path: Path, counted: dict[str, int]
) -> None:
    """다른 프로세스의 저장은 이 앱의 캐시를 비우지 않는다 — DB·WAL stat 이 바뀌어 다시 읽는다."""
    database, outsider = _seeded(tmp_path)
    first = latest_equipment_revision_id(database)
    assert load_process_cutoff(database)["Cutoff일수"].tolist() == [10.0]

    saved = outsider.save_snapshot(_baseline(), _equipment().assign(담당자="담당B"), _downtime())
    outsider.save_process_cutoff(_cutoff(20.0))

    assert saved is not None
    assert latest_equipment_revision_id(database) == saved.revision.revision_id != first
    snapshot = load_latest_equipment_snapshot(database)
    assert snapshot is not None and snapshot.revision.revision_no == 2
    assert load_process_cutoff(database)["Cutoff일수"].tolist() == [20.0]
    clear_equipment_repository()


def test_clearing_is_enough_even_when_the_stat_looks_the_same(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stat 을 고정해도(못 잡은 경우) 앱의 저장 경로가 부르는 비우기가 새 값을 읽게 한다."""
    database, outsider = _seeded(tmp_path)
    monkeypatch.setattr(equipment_cache, "database_stamp", lambda _path: (None, None))
    first = latest_equipment_revision_id(database)
    load_process_cutoff(database)

    saved = outsider.save_snapshot(_baseline(), _equipment().assign(담당자="담당B"), _downtime())
    outsider.save_process_cutoff(_cutoff(20.0))
    assert saved is not None
    # stat 이 못 잡으면 비우기 전까지는 옛 값이다 — 그래서 앱의 저장은 반드시 비운다.
    assert latest_equipment_revision_id(database) == first
    assert load_process_cutoff(database)["Cutoff일수"].tolist() == [10.0]

    clear_equipment_snapshot_cache()
    clear_process_cutoff_cache()

    assert latest_equipment_revision_id(database) == saved.revision.revision_id
    assert load_process_cutoff(database)["Cutoff일수"].tolist() == [20.0]
    clear_equipment_repository()


def test_the_stamp_follows_the_database_and_its_wal(tmp_path: Path) -> None:
    database, outsider = _seeded(tmp_path)
    before = equipment_cache.database_stamp(database)
    assert before[0] is not None

    outsider.save_process_cutoff(_cutoff(30.0))

    assert equipment_cache.database_stamp(database) != before
    assert equipment_cache.database_stamp(str(tmp_path / "없는.duckdb")) == (None, None)
    clear_equipment_repository()


def test_a_cutoff_saved_on_the_screen_is_what_the_next_run_counts_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """화면: Preference 에서 Cut-off 를 저장하면 다음 회차가 그 값을 쓴다 — stat 을 고정해도.

    샘플 fleet 의 공정 전부에 Cut-off 를 적으면 「적지 않은 공정」 경고가 사라진다(저장 전에는
    선다).
    """
    database = tmp_path / "availability.duckdb"
    monkeypatch.setattr(equipment_cache, "database_stamp", lambda _path: (None, None))
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=120).run()
    app = _open_tab(app, "Preference")
    assert not app.exception
    assert any("Cut-off 를 적지 않은 공정" in str(item.value) for item in app.warning)

    processes = processes_in(
        sample_equipment_master(anchor_date=date.today()), sample_equipment_baseline()
    )
    app.session_state[CUTOFF_DRAFT_KEY] = _cutoff(12.0, list(processes))
    next(button for button in app.button if button.label == "Cut-off 저장").click().run()

    assert not app.exception
    assert not any("Cut-off 를 적지 않은 공정" in str(item.value) for item in app.warning)
    assert any("모두 채워졌습니다" in str(item.value) for item in app.caption)
    saved = DuckDBEquipmentRepository(database).load_process_cutoff()
    assert sorted(saved["공정"]) == sorted(processes)
    clear_equipment_repository()
