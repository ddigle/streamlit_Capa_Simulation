# Purpose: 설비 DB 현행값·설비 시나리오 목록·합친 본문 캐시의 저장·발행 반영과 래퍼 미사용을 본다.

"""「지금 무엇이 저장돼 있나」 읽기 캐시(`persistence/equipment_cache.py`).

가용설비 현황·Space 는 회차마다 최신 리비전 id 와 Cut-off 를, 표준 목표·표준 대비 재공 현황은 주차별
가용대수를 읽느라 설비 DB 를 열었다. 이제 키를 DB·WAL stat 으로 둔 캐시에서 받는다. 놓치면 옛
리비전·옛 Cut-off·옛 가용대수로 센 숫자가 나오므로 두 장치를 따로 본다.

1. **비우기(1차)** — 이 앱의 저장은 저장 직후 캐시를 비우고 쓰기 세대를 올린다. stat 을 일부러
   고정해도 저장한 값이 다음 읽기에 나와야 한다 — 화면의 저장 경로(RawData·Space·Cut-off·주차별
   가용대수 붙여넣기·입력 초기화)와, 저장 직전에 시작된 다른 세션의 읽기가 겹친 경우까지(stat 이
   없는 조회 조건·기준선·도면 캐시도).
2. **stat(2차)** — 이 앱을 지나지 않은 쓰기(다른 Repository 객체 = 다른 프로세스 흉내)는 파일
   stat(본 파일, 연결을 열어 둔 쓰기면 WAL)이 바뀌어 다시 읽는다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import fields as dataclass_fields
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
from test_standard_target_capa_page import TEST_SCRIPT as STANDARD_TARGET_SCRIPT
from test_wip_status_page import TEST_SCRIPT as WIP_STATUS_SCRIPT

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
    clear_equipment_scenario_cache,
    clear_equipment_snapshot_cache,
    clear_floor_layout_cache,
    clear_floor_state_cache,
    clear_process_cutoff_cache,
    clear_shortening_baseline_cache,
    clear_shortening_filter_cache,
    clear_standard_target_availability_cache,
    latest_equipment_revision_id,
    load_equipment_scenario_catalog,
    load_equipment_schedule_revisions,
    load_floor_layout_canvases,
    load_floor_states,
    load_merged_equipment_snapshot,
    load_official_equipment_snapshot,
    load_process_cutoff,
    load_schedule_layout_overlay,
    load_shortening_baselines,
    load_shortening_filter_profile,
    load_standard_target_availability,
)
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentSaveRequest,
    EquipmentSnapshot,
)
from capa_simulation.services.equipment_samples import (
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.floor_layout_mark import FloorLayoutMark, floor_layout_fingerprint
from capa_simulation.services.floor_state import FloorStates
from capa_simulation.services.layout_overlay import LayoutOverlay
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


def _weekly_availability(count: float) -> pd.DataFrame:
    """표준 목표 화면 대본(`STANDARD_TARGET_SCRIPT`)의 공정·주차와 같은 주차별 가용대수."""
    weeks = ["26-W32", "26-W33", "26-W34", "26-W35", "26-W36"]
    return pd.DataFrame(
        {"공정": ["Process-A"] * len(weeks), "Weeknum": weeks, "가용대수": [count] * len(weeks)}
    )


def _seeded(tmp_path: Path) -> tuple[str, DuckDBEquipmentRepository]:
    """r1·Cut-off·주차별 가용대수를 저장한 DB. 돌려주는 Repository 는 **이 앱 밖의 쓰기**를 흉내
    낸다."""
    database = tmp_path / "equipment.duckdb"
    outsider = DuckDBEquipmentRepository(database)
    outsider.initialize()
    outsider.save_snapshot(_baseline(), _equipment(), _downtime(), note="r1")
    outsider.save_process_cutoff(_cutoff(10.0))
    outsider.save_standard_target_availability(_weekly_availability(2.0))
    clear_equipment_repository()
    return str(database.resolve()), outsider


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """세 읽기가 실제로 DB 를 몇 번 열었나."""
    counts = {"latest": 0, "cutoff": 0, "standard_target": 0}
    latest = DuckDBEquipmentRepository.latest_revision_id
    cutoff = DuckDBEquipmentRepository.load_process_cutoff
    availability = DuckDBEquipmentRepository.load_standard_target_availability

    def counting_latest(self: DuckDBEquipmentRepository) -> str | None:
        counts["latest"] += 1
        return latest(self)

    def counting_cutoff(self: DuckDBEquipmentRepository) -> pd.DataFrame:
        counts["cutoff"] += 1
        return cutoff(self)

    def counting_availability(self: DuckDBEquipmentRepository) -> pd.DataFrame:
        counts["standard_target"] += 1
        return availability(self)

    monkeypatch.setattr(DuckDBEquipmentRepository, "latest_revision_id", counting_latest)
    monkeypatch.setattr(DuckDBEquipmentRepository, "load_process_cutoff", counting_cutoff)
    monkeypatch.setattr(
        DuckDBEquipmentRepository, "load_standard_target_availability", counting_availability
    )
    return counts


def test_unchanged_reads_do_not_open_the_database(tmp_path: Path, counted: dict[str, int]) -> None:
    database, outsider = _seeded(tmp_path)
    expected = outsider.latest_revision_id()
    expected_availability = outsider.load_standard_target_availability()
    # 심을 때의 읽기(저장이 돌려주는 값)는 세지 않는다
    counted.update(latest=0, cutoff=0, standard_target=0)

    for _ in range(3):
        assert latest_equipment_revision_id(database) == expected
        pd.testing.assert_frame_equal(load_process_cutoff(database), outsider.load_process_cutoff())
        pd.testing.assert_frame_equal(
            load_standard_target_availability(database), expected_availability
        )

    assert counted["latest"] == 1
    # 위 루프의 `outsider.load_process_cutoff()` 셋 + 캐시 한 번
    assert counted["cutoff"] == 4
    assert counted["standard_target"] == 1
    clear_equipment_repository()


def test_a_write_outside_the_app_is_seen_through_the_file_stat(
    tmp_path: Path, counted: dict[str, int]
) -> None:
    """다른 프로세스의 저장은 이 앱의 캐시를 비우지 않는다 — DB·WAL stat 이 바뀌어 다시 읽는다."""
    database, outsider = _seeded(tmp_path)
    first = latest_equipment_revision_id(database)
    assert load_process_cutoff(database)["Cutoff일수"].tolist() == [10.0]

    assert load_standard_target_availability(database)["가용대수"].eq(2.0).all()

    saved = outsider.save_snapshot(_baseline(), _equipment().assign(담당자="담당B"), _downtime())
    outsider.save_process_cutoff(_cutoff(20.0))
    outsider.save_standard_target_availability(_weekly_availability(5.0))

    assert saved is not None
    assert latest_equipment_revision_id(database) == saved.revision.revision_id != first
    snapshot = load_official_equipment_snapshot(database)
    assert snapshot is not None and snapshot.revision.revision_no == 2
    assert load_process_cutoff(database)["Cutoff일수"].tolist() == [20.0]
    assert load_standard_target_availability(database)["가용대수"].eq(5.0).all()
    clear_equipment_repository()


def test_clearing_is_enough_even_when_the_stat_looks_the_same(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stat 을 고정해도(못 잡은 경우) 앱의 저장 경로가 부르는 비우기가 새 값을 읽게 한다."""
    database, outsider = _seeded(tmp_path)
    monkeypatch.setattr(equipment_cache, "database_stamp", lambda _path: (None, None))
    first = latest_equipment_revision_id(database)
    load_process_cutoff(database)
    load_standard_target_availability(database)

    saved = outsider.save_snapshot(_baseline(), _equipment().assign(담당자="담당B"), _downtime())
    outsider.save_process_cutoff(_cutoff(20.0))
    outsider.save_standard_target_availability(_weekly_availability(5.0))
    assert saved is not None
    # stat 이 못 잡으면 비우기 전까지는 옛 값이다 — 그래서 앱의 저장은 반드시 비운다.
    assert latest_equipment_revision_id(database) == first
    assert load_process_cutoff(database)["Cutoff일수"].tolist() == [10.0]
    assert load_standard_target_availability(database)["가용대수"].eq(2.0).all()

    clear_equipment_snapshot_cache()
    clear_process_cutoff_cache()
    clear_standard_target_availability_cache()

    assert latest_equipment_revision_id(database) == saved.revision.revision_id
    assert load_process_cutoff(database)["Cutoff일수"].tolist() == [20.0]
    assert load_standard_target_availability(database)["가용대수"].eq(5.0).all()

    # 입력 초기화도 같은 비우기를 지난다 — 빈 표가 다음 읽기에 나온다.
    outsider.clear_standard_target_availability()
    clear_standard_target_availability_cache()
    assert load_standard_target_availability(database).empty
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

    reader, release, result = _in_flight_read(
        monkeypatch,
        "load_standard_target_availability",
        lambda: load_standard_target_availability(database),
    )
    outsider.save_standard_target_availability(_weekly_availability(5.0))
    clear_standard_target_availability_cache()
    release.set()
    reader.join(30)
    assert cast(pd.DataFrame, result["value"])["가용대수"].eq(2.0).all()
    assert load_standard_target_availability(database)["가용대수"].eq(5.0).all()
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


def test_floor_states_follow_the_stat_the_clearing_and_a_read_in_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """층 사용 상태(설비 0029)는 Cut-off 와 같은 꼴이다 — 앱 밖의 저장은 stat 이, 앱의 저장(Space 층
    목록의 저장 콜백)은 비우기가, 저장과 겹친 읽기는 쓰기 세대가 맡는다."""
    database, outsider = _seeded(tmp_path)
    equipment_cache.get_equipment_repository(database)
    assert load_floor_states(database).rows == ()

    outsider.save_floor_states({("C1", "3F"): "UNUSED"}, expected_version=0, source="밖")
    assert load_floor_states(database).inactive == {("C1", "3F"): "UNUSED"}

    monkeypatch.setattr(equipment_cache, "database_stamp", lambda _path: (None, None))
    load_floor_states(database)
    outsider.save_floor_states({}, expected_version=1, source="밖")
    assert load_floor_states(database).version == 1  # stat 이 못 잡으면 비우기 전까지 옛 값
    clear_floor_state_cache()
    assert (load_floor_states(database).rows, load_floor_states(database).version) == ((), 2)

    clear_floor_state_cache()  # 다른 세션의 캐시 미스를 흉내 내려 칸을 비운다
    reader, release, result = _in_flight_read(
        monkeypatch, "load_floor_states", lambda: load_floor_states(database)
    )
    outsider.save_floor_states({("C2", "1F"): "NOT_LINE"}, expected_version=2, source="밖")
    clear_floor_state_cache()
    release.set()
    reader.join(30)
    assert cast(FloorStates, result["value"]).rows == ()
    assert load_floor_states(database).inactive == {("C2", "1F"): "NOT_LINE"}
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


_FAKE_EQUIPMENT_REPOSITORY = (
    "equipment_cache.get_equipment_repository = lambda _path: FakeEquipmentRepository()"
)


def _on_equipment_database(script: str, database: Path) -> str:
    """화면 대본의 가짜 설비 저장소를 걷고 tmp 설비 DB 를 보게 한다(나머지 대역은 그대로)."""
    assert _FAKE_EQUIPMENT_REPOSITORY in script
    return script.replace(
        _FAKE_EQUIPMENT_REPOSITORY,
        "import capa_simulation.settings as settings\n"
        f"settings.EQUIPMENT_DUCKDB_PATH = Path({str(database)!r})",
        1,
    )


@pytest.mark.parametrize(
    "script", [STANDARD_TARGET_SCRIPT, WIP_STATUS_SCRIPT], ids=["표준 목표", "표준 대비 재공 현황"]
)
def test_a_warm_run_of_the_page_does_not_reopen_the_equipment_database(
    tmp_path: Path, counted: dict[str, int], script: str
) -> None:
    """두 화면이 그 회차에 설비 DB 를 여는 곳은 주차별 가용대수 읽기 하나다. 위젯 하나에 다시 도는
    회차가 그 읽기를 캐시에서 받아야 회차마다 DB 인스턴스를 새로 만들지 않는다."""
    database, _outsider = _seeded(tmp_path)
    counted.update(latest=0, cutoff=0, standard_target=0)
    app = AppTest.from_string(_on_equipment_database(script, Path(database)), default_timeout=120)
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    assert counted["standard_target"] == 1

    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert counted["standard_target"] == 1
    clear_equipment_repository()


def test_a_warm_run_of_the_space_page_reads_the_floor_states_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Space 는 회차마다 층 사용 상태를 읽는다 — 위젯 하나에 다시 도는 회차는 캐시에서 받는다(설비
    DB 를 다시 열지 않는다)."""
    database, _outsider = _seeded(tmp_path)
    calls = {"floor_state": 0}
    original = DuckDBEquipmentRepository.load_floor_states

    def counting(self: DuckDBEquipmentRepository) -> FloorStates:
        calls["floor_state"] += 1
        return original(self)

    monkeypatch.setattr(DuckDBEquipmentRepository, "load_floor_states", counting)
    monkeypatch.setattr(
        space_layout_editor, "_EDITOR", lambda **_kwargs: SimpleNamespace(apply=None)
    )
    space_page = PROJECT_ROOT / "app_pages" / "space_status.py"
    app = AppTest.from_string(_page_script(space_page, Path(database)), default_timeout=120)
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert calls["floor_state"] == 1

    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert calls["floor_state"] == 1
    clear_equipment_repository()


def test_availability_pasted_or_cleared_on_the_screen_is_what_the_next_run_counts_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """화면: 표준 목표에서 가용설비를 붙여넣거나 입력을 초기화하면 다음 회차가 그 값으로 센다 —
    stat 을 고정해도(비우기가 빠지면 옛 가용대수로 그린다)."""
    database, _outsider = _seeded(tmp_path)
    monkeypatch.setattr(equipment_cache, "database_stamp", lambda _path: (None, None))
    app = AppTest.from_string(
        _on_equipment_database(STANDARD_TARGET_SCRIPT, Path(database)), default_timeout=120
    ).run()
    assert not app.exception, [item.message for item in app.exception]
    before = app.session_state["captured_first_week_value"]

    app.button(key="open_standard_target_availability_paste").click().run()
    app.text_area(key="standard_target_availability_clipboard_text").set_value(
        "공정\tWeeknum\t가용대수\nProcess-A\t26-W32\t5\n"
    )
    next(button for button in app.button if button.label == "붙여넣기 적용").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    # 첫 열이 26-W32 다 — 일 표준 가능량은 가용대수에 비례한다(2 → 5).
    assert app.session_state["captured_first_week_value"] == pytest.approx(before * 2.5)
    assert not app.button(key="open_standard_target_availability_clear").disabled

    app.button(key="open_standard_target_availability_clear").click().run()
    app.checkbox(key="standard_target_clear_confirm").check().run()
    app.button(key="clear_standard_target_availability").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    assert DuckDBEquipmentRepository(Path(database)).load_standard_target_availability().empty
    # 저장된 가용대수가 없으면 초기화 버튼이 잠긴다 — 다음 회차가 빈 표를 읽었다는 뜻이다.
    assert app.button(key="open_standard_target_availability_clear").disabled
    clear_equipment_repository()


def test_a_rawdata_save_on_the_screen_rebuilds_the_draft_from_the_new_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """화면: RawData 에서 리비전을 저장하면 다음 회차의 편집본은 **방금 저장한 리비전**에서 선다 —
    stat 을 고정해도.

    비우기가 빠지면 최신 id 캐시가 옛 리비전을 내 편집본이 옛 저장본으로 다시 세워진다(지운 호기가
    되살아난다). 그 편집본에서 다시 저장하면 출발 공통 대조로 막힌다 — 그래서 두 번째 저장까지
    돈다(바뀐 것이 없어 리비전은 생기지 않지만 대조는 쓰기 잠금 안에서 먼저 한다). 편집은 칸을
    누르지 않는 길(동 필터 → 맞는 행 모두 선택 → 삭제 확정)로 한다. 편집본 토큰은 (공통, 일정)
    쌍이다.
    """
    seed = _bulk_seeded(tmp_path)
    repository = DuckDBEquipmentRepository(seed.database)
    first = repository.latest_revision_id()
    assert first is not None
    clear_equipment_repository()
    monkeypatch.setattr(equipment_cache, "database_stamp", lambda _path: (None, None))
    app = AppTest.from_string(_bulk_page_script(seed.database), default_timeout=120).run()
    assert not app.exception
    assert app.session_state[DRAFT_REVISION_KEY] == repository.load_snapshot(first).token

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
    assert app.session_state[DRAFT_REVISION_KEY] == repository.load_snapshot(second).token
    assert len(app.session_state[EQUIPMENT_DRAFT_KEY]) == kept

    app.button(key=EDIT_SAVE_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    latest = repository.list_revisions()[0]
    # 바뀐 것 없는 저장은 빈 리비전을 만들지 않는다(결정 모음 「묻지 않고 하기로 한 것」).
    assert latest.revision_no == 2
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
    # 좌표만 고친 저장은 공통 대장만 새로 쓴다 — 편집본 토큰의 공통 쪽이 새 리비전이다.
    assert app.session_state[DRAFT_REVISION_KEY] == outsider.load_snapshot(second).token
    assert space_editor_calls[-1]["epoch"].split("|")[2] == second
    moved = app.session_state[EQUIPMENT_DRAFT_KEY].set_index("설비명").loc["EQ-01", "X좌표"]
    assert moved == 40.0
    clear_equipment_repository()


# ── 설비 시나리오 캐시(설계 4-1) ──────────────────────────────────────────────────────


def _scenario_seeded(tmp_path: Path) -> tuple[str, DuckDBEquipmentRepository, str]:
    """래퍼로 r1 을 넣고 「셋업 실무」 를 복제한 DB. (DB, 앱 밖 저장소, 복제 시나리오 id)."""
    database, outsider = _seeded(tmp_path)
    release = outsider.latest_equipment_release()
    assert release is not None
    clone = outsider.clone_equipment_scenario(
        release.schedule_revision_id, name="셋업 실무", created_by=None
    )
    clear_equipment_repository()
    return database, outsider, clone.equipment_scenario_id


def test_the_scenario_catalog_sees_renames_releases_and_saves_after_a_clear_or_a_stat_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """목록 캐시는 공통 최신 id 와 같은 세 장치다 — 앱의 비우기(세대 `equipment_scenario`)가 1차,
    파일 stat 이 2차. 리비전 내용 캐시와 달리 이름·발행·각 최신은 바뀔 수 있다."""
    database, outsider, clone_id = _scenario_seeded(tmp_path)
    first = load_equipment_scenario_catalog(database)
    assert [item.scenario_name for item in first.scenarios] == ["운영 일정", "셋업 실무"]
    assert first.release_no == 1

    # stat 이 바뀌면(앱 밖의 쓰기) 비우지 않아도 다시 읽는다.
    outsider.rename_equipment_scenario(clone_id, name="셋업 실무 2차", expected_name="셋업 실무")
    assert load_equipment_scenario_catalog(database).scenarios[1].scenario_name == "셋업 실무 2차"

    # stat 을 고정하면 비우기 전까지 옛 값이다 — 그래서 앱의 쓰기는 반드시 비운다.
    monkeypatch.setattr(equipment_cache, "database_stamp", lambda _path: (None, None))
    before = load_equipment_scenario_catalog(database)
    clone_latest = before.scenarios[1].latest_schedule_revision_id
    assert clone_latest is not None
    outsider.publish_equipment_release(
        clone_latest, released_by=None, note=None, expected_latest_release_no=1
    )
    assert load_equipment_scenario_catalog(database).release_no == 1
    clear_equipment_scenario_cache()
    after = load_equipment_scenario_catalog(database)
    assert after.release_no == 2 and after.official_scenario_id == clone_id
    assert load_equipment_schedule_revisions(database, clone_id)[0].revision_no == 1
    clear_equipment_repository()


def test_publishing_alone_changes_what_the_official_snapshot_shows(tmp_path: Path) -> None:
    """공식 스냅샷 = 공통 최신 + 목록의 최신 발행 → 쌍 키 본문. 공통이 그대로여도 발행만 바꾸면 다른
    쌍 키로 가 결과가 바뀐다(래퍼 `load_snapshot` 을 공통 id 하나 키로 캐시하면 놓친다)."""
    database, outsider, clone_id = _scenario_seeded(tmp_path)
    clone_session = outsider.load_merged_snapshot(
        str(outsider.latest_revision_id()),
        next(
            item.latest_schedule_revision_id
            for item in outsider.list_equipment_scenarios()
            if item.equipment_scenario_id == clone_id
        ),
    )
    edited = clone_session.equipment.copy()
    edited.loc[edited["설비명"].eq("EQ-02"), "Qual일정"] = pd.Timestamp("2026-09-30")
    assert clone_session.schedule is not None
    saved = outsider.save_equipment(
        EquipmentSaveRequest(
            baseline=clone_session.baseline,
            equipment=edited,
            downtime=clone_session.downtime,
            equipment_scenario_id=clone_id,
            base_common_revision_id=clone_session.revision.revision_id,
            base_schedule_revision_id=clone_session.schedule.schedule_revision_id,
        )
    )
    assert saved.schedule is not None and saved.common is None
    before = load_official_equipment_snapshot(database)
    assert before is not None

    outsider.publish_equipment_release(
        saved.schedule.schedule_revision_id,
        released_by=None,
        note=None,
        expected_latest_release_no=1,
    )
    clear_equipment_scenario_cache()  # 이름·발행·복제·이어 쓰기 뒤에는 이것만 부른다
    after = load_official_equipment_snapshot(database)

    assert after is not None
    assert before.revision.revision_id == after.revision.revision_id
    assert before.token != after.token
    qual = after.equipment.set_index("설비명").loc["EQ-02", "Qual일정"]
    assert qual == pd.Timestamp("2026-09-30")
    clear_equipment_repository()


def test_the_merged_body_is_shared_by_pair_key_and_pickles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """세션이 공식 발행 쌍이면 공식 스냅샷과 같은 칸을 쓴다(한 번만 꺼냄). 본문 페이로드는 쌍
    튜플·frozenset 이라 pickle 이 된다 — `MappingProxyType` 을 실으면 캐시가 깨진다(검토 1-12)."""
    import pickle

    database, outsider, _clone_id = _scenario_seeded(tmp_path)
    calls: list[tuple[str, str | None]] = []
    original = DuckDBEquipmentRepository.load_merged_snapshot

    def counted(
        self: DuckDBEquipmentRepository, common: str, schedule: str | None
    ) -> EquipmentSnapshot:
        calls.append((common, schedule))
        return original(self, common, schedule)

    monkeypatch.setattr(DuckDBEquipmentRepository, "load_merged_snapshot", counted)
    official = load_official_equipment_snapshot(database)
    assert official is not None and official.schedule is not None
    again = load_merged_equipment_snapshot(
        database, official.revision.revision_id, official.schedule.schedule_revision_id
    )

    assert len(calls) == 1
    assert again.token == official.token
    assert again.unit_keys == official.unit_keys and official.unit_key_pairs
    payload = equipment_cache._load_merged_payload(
        database, official.revision.revision_id, official.schedule.schedule_revision_id
    )
    restored = pickle.loads(pickle.dumps(payload))
    assert restored["unit_key_pairs"] == official.unit_key_pairs
    assert isinstance(restored["unscheduled_units"], frozenset)
    clear_equipment_repository()


_WRAPPERS = frozenset({"save_snapshot", "save_space_layout", "load_snapshot"})


def _wrapper_calls(path: Path) -> list[str]:
    """한 파일에서 저장소 호환 래퍼를 부르는 자리(`<무엇>.save_snapshot(` 꼴)."""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} {node.func.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _WRAPPERS
    ]


def test_caches_and_screens_never_call_the_repository_wrappers() -> None:
    """화면(`app_pages/`·`components/`)·세션(`equipment_scenario_activation.py`)·캐시 경계
    (`persistence/equipment_cache.py`)는 래퍼를 부르지 않는다(설계 3-5) — 래퍼 `load_snapshot` 은
    발행에 따라 값이 바뀌는 뜻이고, 래퍼 저장은 늘 두 쪽을 써 공식으로 발행한다. 화면 저장은
    `save_equipment`(바뀐 쪽만·이 세션의 시나리오)다."""
    package = PROJECT_ROOT / "src" / "capa_simulation"
    paths = [
        *sorted((PROJECT_ROOT / "app_pages").glob("*.py")),
        *sorted((package / "components").glob("*.py")),
        package / "persistence" / "equipment_cache.py",
        package / "equipment_scenario_activation.py",
        PROJECT_ROOT / "app.py",
    ]
    found = [call for path in paths for call in _wrapper_calls(path)]
    assert found == []


# ── 가정 배치 차이 캐시(설비 0031 — 설계 7-2) ─────────────────────────────────────────


def _hypothetical_layout_saved(tmp_path: Path) -> tuple[str, DuckDBEquipmentRepository, str]:
    """「셋업 실무」 에서 EQ-01 을 옮기고 그 층 요소 하나·Main 설비명 위치 하나를 가정 배치로 저장한
    DB. (DB, 앱 밖 저장소, 그 리비전 id)."""
    database, outsider, clone_id = _scenario_seeded(tmp_path)
    common = outsider.latest_revision_id()
    clone = next(
        item
        for item in outsider.list_equipment_scenarios()
        if item.equipment_scenario_id == clone_id
    )
    assert common is not None and clone.latest_schedule_revision_id is not None
    session = outsider.load_merged_snapshot(common, clone.latest_schedule_revision_id)
    moved = session.equipment.copy()
    moved.loc[moved["설비명"].eq("EQ-01"), "X좌표"] = 55.0
    mark = FloorLayoutMark(
        mark_id="MK-1",
        kind="column",
        x=1.0,
        y=1.0,
        w=2.0,
        h=2.0,
        rotation=0,
        label="",
        color="",
        hatch=False,
        keep_out=False,
    )
    saved = outsider.save_equipment(
        EquipmentSaveRequest(
            baseline=session.baseline,
            equipment=moved,
            downtime=session.downtime,
            equipment_scenario_id=clone_id,
            base_common_revision_id=common,
            base_schedule_revision_id=clone.latest_schedule_revision_id,
            floor_marks={("C1", "1F"): [mark.editor_payload()]},
            floor_group_labels={("C1", "1F"): {"APW1": "top"}},
            floor_layout_bases={("C1", "1F"): (None, floor_layout_fingerprint((), {}))},
        )
    )
    assert saved.schedule is not None and saved.layout_overlay_written
    clear_equipment_repository()
    return database, outsider, saved.schedule.schedule_revision_id


def test_every_snapshot_field_round_trips_through_the_merged_body_payload(tmp_path: Path) -> None:
    """검토 F16 — 새 필드를 payload 에 빠뜨리면 기본값으로 말없이 꺼내 「공식과 견주기」 가 빈다."""
    import pickle

    database, outsider, schedule_id = _hypothetical_layout_saved(tmp_path)
    common = outsider.latest_revision_id()
    assert common is not None
    direct = outsider.load_merged_snapshot(common, schedule_id)
    cached = load_merged_equipment_snapshot(database, common, schedule_id)

    assert set(equipment_cache._MergedSnapshotPayload.__annotations__) == {
        item.name for item in dataclass_fields(EquipmentSnapshot)
    }
    for item in dataclass_fields(EquipmentSnapshot):
        mine, theirs = getattr(cached, item.name), getattr(direct, item.name)
        if isinstance(mine, pd.DataFrame):
            pd.testing.assert_frame_equal(mine, theirs)
        elif item.name == "schedule":
            assert mine is not None and theirs is not None
            assert mine.layout_hash == theirs.layout_hash and mine.revision_name is None
        else:
            assert mine == theirs, item.name
    assert cached.layout_official_places and cached.layout_overridden_keys
    payload = equipment_cache._load_merged_payload(database, common, schedule_id)
    assert pickle.loads(pickle.dumps(payload))["layout_official_places"] == (
        direct.layout_official_places
    )
    clear_equipment_repository()


def test_the_mark_and_label_differences_are_cached_by_one_schedule_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, _outsider, schedule_id = _hypothetical_layout_saved(tmp_path)
    calls: list[str | None] = []
    original = DuckDBEquipmentRepository.load_layout_overlay

    def counting(self: DuckDBEquipmentRepository, revision_id: str | None) -> LayoutOverlay:
        calls.append(revision_id)
        return original(self, revision_id)

    monkeypatch.setattr(DuckDBEquipmentRepository, "load_layout_overlay", counting)
    first = load_schedule_layout_overlay(database, schedule_id)
    again = load_schedule_layout_overlay(database, schedule_id)

    assert calls == [schedule_id]
    assert first == again and type(first) is LayoutOverlay
    # 호기 차이는 합친 본문에 이미 얹혀 있어 싣지 않는다.
    assert first.units == () and first.marks_for(("C1", "1F")) and first.labels_for(("C1", "1F"))
    assert load_schedule_layout_overlay(database, None) == LayoutOverlay()
    clear_equipment_snapshot_cache()
    load_schedule_layout_overlay(database, schedule_id)
    assert calls == [schedule_id, schedule_id]
    clear_equipment_repository()
