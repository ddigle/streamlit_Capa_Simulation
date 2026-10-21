# Purpose: 설비 DB 현행값 읽기 캐시(최신 id·Cut-off·조건·기준선·도면)가 저장을 놓치지 않는지 본다.

"""「지금 무엇이 저장돼 있나」 읽기 캐시(`persistence/equipment_cache.py`).

가용설비 현황·Space 는 회차마다 최신 리비전 id 와 Cut-off 를 읽느라 설비 DB 를 열었다. 이제 키를
DB·WAL stat 으로 둔 캐시에서 받는다. 놓치면 옛 리비전·옛 Cut-off 로 센 숫자가 나오므로 두 장치를
따로 본다.

1. **비우기(1차)** — 이 앱의 저장은 저장 직후 캐시를 비우고 쓰기 세대를 올린다. stat 을 일부러
   고정해도 저장한 값이 다음 읽기에 나와야 한다 — 화면의 저장 경로(RawData·Space·Cut-off)와, 저장
   직전에 시작된 다른 세션의 읽기가 겹친 경우까지(stat 이 없는 조회 조건·기준선·도면 캐시도).
2. **stat(2차)** — 이 앱을 지나지 않은 쓰기(다른 Repository 객체 = 다른 프로세스 흉내)는 파일
   stat(본 파일, 연결을 열어 둔 쓰기면 WAL)이 바뀌어 다시 읽는다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import duckdb
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_bulk_delete_page import (
    BUILDING_FILTER_KEY,
    DELETE_SELECTED_KEY,
    SELECT_MATCHING_KEY,
)
from test_equipment_bulk_delete_page import _page_script as _bulk_page_script
from test_equipment_bulk_delete_page import _seeded as _bulk_seeded
from test_equipment_pages import _open_tab, _page_script
from test_shortening_baseline import _bundle_plan

from capa_simulation.components import space_layout_editor
from capa_simulation.components.cutoff_management import CUTOFF_DRAFT_KEY
from capa_simulation.components.equipment_data_workspace import (
    CONFIRM_DELETE_BUTTON_KEY,
    DRAFT_REVISION_KEY,
    EDIT_SAVE_BUTTON_KEY,
    EQUIPMENT_DRAFT_KEY,
)
from capa_simulation.persistence import equipment_cache
from capa_simulation.persistence._sql_helpers import DUCKDB_CONNECT_CONFIG
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_equipment_snapshot_cache,
    clear_floor_layout_cache,
    clear_process_cutoff_cache,
    clear_shortening_baseline_cache,
    clear_shortening_filter_cache,
    latest_equipment_revision_id,
    load_floor_layout_canvases,
    load_latest_equipment_snapshot,
    load_process_cutoff,
    load_shortening_baselines,
    load_shortening_filter_profile,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_samples import (
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.monthly_equipment_availability import processes_in
from capa_simulation.services.shortening_baseline import freeze_plan
from capa_simulation.services.shortening_filter_profile import ShorteningFilterProfile

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


def test_the_stamp_follows_the_database_file(tmp_path: Path) -> None:
    """쓰기마다 연결을 닫는 Repository 는 닫을 때 체크포인트한다 — 본 파일 stat 이 바뀌고 WAL 은
    남지 않는다."""
    database, outsider = _seeded(tmp_path)
    before = equipment_cache.database_stamp(database)
    assert before[0] is not None

    outsider.save_process_cutoff(_cutoff(30.0))

    assert equipment_cache.database_stamp(database) != before
    assert equipment_cache.database_stamp(str(tmp_path / "없는.duckdb")) == (None, None)
    clear_equipment_repository()


def test_a_commit_that_only_grows_the_wal_is_seen(tmp_path: Path) -> None:
    """연결 하나를 열어 둔 채 커밋하면(체크포인트 없음) 본 파일은 그대로이고 WAL 만 는다 — stat 의
    WAL 성분이 그 쓰기를 알아채 비우지 않아도 새 값을 읽는다."""
    database, outsider = _seeded(tmp_path)
    assert load_process_cutoff(database)["Cutoff일수"].tolist() == [10.0]
    first = latest_equipment_revision_id(database)
    before = equipment_cache.database_stamp(database)
    keeper = duckdb.connect(database, config=DUCKDB_CONNECT_CONFIG)
    try:
        outsider.save_process_cutoff(_cutoff(30.0))
        saved = outsider.save_snapshot(
            _baseline(), _equipment().assign(담당자="담당B"), _downtime()
        )
        after = equipment_cache.database_stamp(database)

        assert after[0] == before[0]  # 본 파일은 그대로다 — 이 경우는 WAL 만 말해 준다
        assert before[1] is None and after[1] is not None
        assert load_process_cutoff(database)["Cutoff일수"].tolist() == [30.0]
        assert saved is not None
        assert latest_equipment_revision_id(database) == saved.revision.revision_id != first
    finally:
        keeper.close()
    clear_equipment_repository()


def _in_flight_read(
    monkeypatch: pytest.MonkeyPatch, method: str, read: Callable[[], object]
) -> tuple[threading.Thread, threading.Event, dict[str, object]]:
    """다른 세션의 캐시 미스 — DB 에서 값을 읽은 뒤, 캐시에 심기 전에 멈춘다."""
    original = getattr(DuckDBEquipmentRepository, method)
    read_done = threading.Event()
    release = threading.Event()

    def paused(self: DuckDBEquipmentRepository) -> object:
        value = original(self)
        read_done.set()
        release.wait(30)
        return value

    monkeypatch.setattr(DuckDBEquipmentRepository, method, paused)
    result: dict[str, object] = {}
    reader = threading.Thread(target=lambda: result.setdefault("value", read()))
    reader.start()
    assert read_done.wait(30)
    monkeypatch.setattr(DuckDBEquipmentRepository, method, original)
    return reader, release, result


def test_a_read_in_flight_during_a_save_does_not_bring_the_old_value_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """저장 직전에 시작된 다른 세션의 읽기가 비운 뒤에 옛 값을 심어도, 비운 뒤의 읽기는 새 값이다 —
    stat 을 고정해도. `.clear()` 만으로는 그 옛 값이 TTL 동안 남았다(쓰기 세대가 막는다)."""
    database, outsider = _seeded(tmp_path)
    monkeypatch.setattr(equipment_cache, "database_stamp", lambda _path: (None, None))
    first = outsider.latest_revision_id()

    reader, release, result = _in_flight_read(
        monkeypatch, "latest_revision_id", lambda: latest_equipment_revision_id(database)
    )
    saved = outsider.save_snapshot(_baseline(), _equipment().assign(담당자="담당B"), _downtime())
    clear_equipment_snapshot_cache()  # 앱의 저장 경로가 부르는 비우기
    release.set()
    reader.join(30)
    assert result["value"] == first  # 진행 중이던 읽기는 옛 값을 돌려준다(그 회차는 그렇다)
    assert saved is not None
    assert latest_equipment_revision_id(database) == saved.revision.revision_id

    reader, release, result = _in_flight_read(
        monkeypatch, "load_process_cutoff", lambda: load_process_cutoff(database)
    )
    outsider.save_process_cutoff(_cutoff(20.0))
    clear_process_cutoff_cache()
    release.set()
    reader.join(30)
    assert cast(pd.DataFrame, result["value"])["Cutoff일수"].tolist() == [10.0]
    assert load_process_cutoff(database)["Cutoff일수"].tolist() == [20.0]
    clear_equipment_repository()


def test_a_read_in_flight_does_not_bring_back_an_old_filter_baseline_list_or_floor_canvas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """필요 단축 일정 조회 조건·기준선 목록·층 캔버스도 같다 — 키가 DB 경로뿐이고 TTL 이 없어, 비운
    뒤에 심긴 옛 값이 다음 저장·재시작까지 모든 세션에 남았다(쓰기 세대가 막는다)."""
    database, outsider = _seeded(tmp_path)
    equipment_cache.get_equipment_repository(database)  # 앱 저장소는 미리 선다

    reader, release, result = _in_flight_read(
        monkeypatch,
        "load_shortening_filter_profile",
        lambda: load_shortening_filter_profile(database),
    )
    assert outsider.save_shortening_filter_months(202605, 202607, source="테스트")
    clear_shortening_filter_cache()
    release.set()
    reader.join(30)
    assert cast(ShorteningFilterProfile, result["value"]).start_month != 202605
    assert load_shortening_filter_profile(database).start_month == 202605

    reader, release, result = _in_flight_read(
        monkeypatch, "list_shortening_baselines", lambda: load_shortening_baselines(database)
    )
    outsider.save_shortening_baseline(freeze_plan(_bundle_plan(), name="겹친 저장"))
    clear_shortening_baseline_cache()
    release.set()
    reader.join(30)
    assert result["value"] == ()
    assert [summary.name for summary in load_shortening_baselines(database)] == ["겹친 저장"]

    reader, release, result = _in_flight_read(
        monkeypatch, "load_floor_layout_summaries", lambda: load_floor_layout_canvases(database)
    )
    outsider.save_floor_layout_canvas("C1", "1F", 120.0, 80.0)
    clear_floor_layout_cache()
    release.set()
    reader.join(30)
    assert result["value"] == {}
    assert load_floor_layout_canvases(database) == {("C1", "1F"): (120.0, 80.0)}
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


def test_a_rawdata_save_on_the_screen_rebuilds_the_draft_from_the_new_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """화면: RawData 에서 리비전을 저장하면 다음 회차의 편집본은 **방금 저장한 리비전**에서 선다 —
    stat 을 고정해도.

    비우기가 빠지면 최신 id 캐시가 옛 리비전을 내 편집본이 옛 저장본으로 다시 세워진다(지운 호기가
    되살아난다). 그 편집본에서 다시 저장하면 `base_revision_id` 충돌로 막힌다 — 그래서 두 번째
    저장까지 돈다. 편집은 칸을 누르지 않는 길(동 필터 → 맞는 행 모두 선택 → 삭제 확정)로 한다.
    """
    seed = _bulk_seeded(tmp_path)
    repository = DuckDBEquipmentRepository(seed.database)
    first = repository.latest_revision_id()
    clear_equipment_repository()
    monkeypatch.setattr(equipment_cache, "database_stamp", lambda _path: (None, None))
    app = AppTest.from_string(_bulk_page_script(seed.database), default_timeout=120).run()
    assert not app.exception
    assert app.session_state[DRAFT_REVISION_KEY] == first

    app.multiselect(key=BUILDING_FILTER_KEY).set_value([seed.building])
    app.button(key=SELECT_MATCHING_KEY).click().run()
    app.button(key=DELETE_SELECTED_KEY).click().run()
    app.button(key=CONFIRM_DELETE_BUTTON_KEY).click().run()
    app.button(key=EDIT_SAVE_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    second = repository.latest_revision_id()
    assert second is not None and second != first
    kept = len(seed.machines) - len(seed.building_machines)

    app.run()  # 저장 다음의 아무 회차(위젯 하나)
    assert not app.exception
    assert app.session_state[DRAFT_REVISION_KEY] == second
    assert len(app.session_state[EQUIPMENT_DRAFT_KEY]) == kept

    app.button(key=EDIT_SAVE_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    latest = repository.list_revisions()[0]
    assert latest.revision_no == 3
    assert len(repository.load_snapshot(latest.revision_id).equipment) == kept
    clear_equipment_repository()


SPACE_PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
_FAKE_APPLY_KEY = "test_current_reads_fake_editor_apply"


@pytest.fixture
def space_editor_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """브라우저 편집기(JS) 대역 — 받은 data 를 적고, 세션에 넣어 둔 적용값을 돌려준다."""
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        calls.append(kwargs["data"])
        return SimpleNamespace(apply=st.session_state.pop(_FAKE_APPLY_KEY, None))

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


def test_a_space_layout_save_rebuilds_the_draft_from_the_new_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, space_editor_calls: list[dict[str, Any]]
) -> None:
    """화면: Space `배치 저장`(`save_space_layout` 경로)도 같다 — stat 을 고정해도 저장 뒤 편집본과
    편집기가 새 리비전에서 선다."""
    database, outsider = _seeded(tmp_path)
    monkeypatch.setattr(equipment_cache, "database_stamp", lambda _path: (None, None))
    app = AppTest.from_string(_page_script(SPACE_PAGE, Path(database)), default_timeout=120)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    assert not app.exception
    first = outsider.latest_revision_id()

    app.session_state[_FAKE_APPLY_KEY] = {
        "epoch": space_editor_calls[-1]["epoch"],
        "changes": [{"id": "EQ-01", "placed": True, "x": 40, "y": 20, "w": 12, "h": 7}],
        "canvas": None,
        "marks": [],
    }
    app.run()
    app.button(key="space_layout_save").click().run()
    assert not app.exception, [item.message for item in app.exception]
    second = outsider.latest_revision_id()
    assert second is not None and second != first

    app.run()
    assert not app.exception
    assert app.session_state[DRAFT_REVISION_KEY] == second
    assert space_editor_calls[-1]["epoch"].split("|")[2] == second
    moved = app.session_state[EQUIPMENT_DRAFT_KEY].set_index("설비명").loc["EQ-01", "X좌표"]
    assert moved == 40.0
    clear_equipment_repository()
