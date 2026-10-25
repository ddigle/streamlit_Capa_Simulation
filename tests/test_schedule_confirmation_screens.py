# Purpose: 일정 확인 알림이 설비 마스터 탭 불러오기 줄·표 풍선·캐시에 편집본·오늘로 잇는지 본다.

"""일정 확인 알림의 화면 연결(2026-10-16 사용자 결정 3 — 저장은 막지 않는다).

- **설비 마스터 탭**(가용설비 현황 ①, 개편 명세 4-1·4-4) — 불러오기 줄 「일정 확인 필요 n대」 가
  그 호기를 세고(누르면 그 호기를 불러온다) 표 줄 설비명 풍선이 「반입 미확인」 같은 단계·갈래를
  말한다. 편집본 기준이라 표에서 고친 저장 전 실적·넣은 행이 바로 보인다. 0 이면 단추가 꺼진다.
  AppTest 는 표 JS 를 못 돌려 대역(`tests/grid_fake.py`)이 받은 data 를 본다.
- **캐시** — `simulation_cache.get_schedule_confirmation_issues` 는 내용 지문 + 오늘이 키다. 같은
  표·같은 날이면 다시 고르지 않고, 칸 하나나 날짜가 바뀌면 새로 고른다.

Main 호기 현황 한 줄은 `tests/test_equipment_explorer.py` 가 본다. 설비 DB 는 테스트마다
`tmp_path` 의 새 파일이다(운영 `data/` 를 열지 않는다).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from grid_fake import Calls, install_fake_grid, last, load, send_ops
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest
from test_equipment_pages import PROJECT_ROOT, _page_script

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.equipment_data_workspace import (
    CLIPBOARD_KEY,
    PREVIEW_BUTTON_KEY,
)
from capa_simulation.components.equipment_import_dialog import IMPORT_APPLY_BUTTON_KEY
from capa_simulation.components.equipment_master_tab import SIDE_CHANGES, SIDE_KEY
from capa_simulation.components.equipment_settings_dialog import EQUIPMENT_DIALOG_KEY
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services import simulation_cache
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_COLUMNS,
    empty_downtime_schedule,
    empty_equipment_baseline,
)
from capa_simulation.services.schedule_confirmation import (
    MISSING_ACTUAL,
    STATUS_UPDATE_NEEDED,
    UNCONFIRMED,
    schedule_confirmation_issues,
    schedule_confirmation_summary,
)

TODAY = date.today()
PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


def _unit(name: str, **overrides: Any) -> dict[str, Any]:
    """검증을 지나는 기존 설비 한 행. 신규 호기·일정·실적은 `overrides` 로 준다."""
    row: dict[str, Any] = dict.fromkeys(EQUIPMENT_COLUMNS)
    row.update(
        {
            "설비명": name,
            "공정소분류": "DEMO_P",
            "보관유무": "N",
            "기존설비여부": "Y",
            "레이아웃표시": "N",
        }
    )
    row.update(overrides)
    return row


def _day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def _late(name: str = "EQ-LATE") -> dict[str, Any]:
    """반입일정이 30일 지났는데 실적이 없고 반입상태가 확정 — 반입 미확인."""
    return _unit(
        name,
        기존설비여부="N",
        반입일정=_day(-30),
        반입상태="확정",
        Qual일정=_day(30),
        Qual상태="계획",
    )


def _done_without_actual(name: str = "EQ-DONE") -> dict[str, Any]:
    """Qual상태 완료인데 Qual실적이 빈 기존 설비 — Qual 실적 누락."""
    return _unit(name, Qual일정=_day(-100), Qual상태="완료")


def _actual_but_open(name: str = "EQ-MOVED") -> dict[str, Any]:
    """반입실적이 있는데 반입상태가 아직 확정 — 반입 상태 갱신 필요."""
    return _unit(
        name,
        기존설비여부="N",
        반입일정=_day(-20),
        반입실적=_day(-21),
        반입상태="확정",
        Qual일정=_day(10),
        Qual상태="계획",
    )


def _master(*rows: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=list(EQUIPMENT_COLUMNS))


def _saved(path: Path, *rows: dict[str, Any]) -> None:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    repository.save_snapshot(
        empty_equipment_baseline(), _master(*rows), empty_downtime_schedule(), note="원본"
    )


def _app(path: Path) -> AppTest:
    """실제 가용설비 현황 페이지의 탭 ① 「설비 마스터」(표 대역) — 페이지는 Main 과 같은 「오늘」을
    넘긴다."""
    app = AppTest.from_string(_page_script(PAGE, path), default_timeout=60)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _alert_ids(grid: Calls) -> list[str]:
    """불러오기 줄 「일정 확인 필요 n대」 의 호기(행 id)."""
    return list(last(grid, emg.LOADER_KEY)["alertIds"])


def _row_alerts(grid: Calls) -> dict[str, str]:
    """불러온 표 줄의 설비명 풍선 갈래 글(「반입 미확인」 등) — 있는 줄만."""
    return {row["id"]: row["alert"] for row in last(grid, emg.GRID_KEY)["rows"] if row.get("alert")}


# ------------------------------------------------------------------ 한 줄


def test_the_summary_counts_units_per_kind_and_skips_empty_kinds() -> None:
    master = _master(
        _late("EQ-A"),
        # 반입·Qual 둘 다 미확인이어도 1대다.
        _unit(
            "EQ-B",
            기존설비여부="N",
            반입일정=_day(-40),
            반입상태="계획",
            Qual일정=_day(-10),
            Qual상태="확정",
        ),
        _done_without_actual("EQ-C"),
    )

    summary = schedule_confirmation_summary(schedule_confirmation_issues(master, today=TODAY))

    assert summary is not None
    assert summary.startswith(f"{UNCONFIRMED} 2대 · {MISSING_ACTUAL} 1대 — ")
    assert STATUS_UPDATE_NEEDED not in summary
    assert "저장은 됩니다" in summary


def test_no_summary_when_nothing_needs_a_look() -> None:
    master = _master(_unit("EQ-OK", Qual일정=_day(-5), Qual실적=_day(-5), Qual상태="완료"))

    assert schedule_confirmation_summary(schedule_confirmation_issues(master, today=TODAY)) is None


# ------------------------------------------------------------------ 캐시 경계


def _counting(monkeypatch: pytest.MonkeyPatch) -> list[date]:
    seen: list[date] = []

    def counting(equipment: pd.DataFrame, *, today: date) -> pd.DataFrame:
        seen.append(today)
        return schedule_confirmation_issues(equipment, today=today)

    monkeypatch.setattr(simulation_cache, "schedule_confirmation_issues", counting)
    return seen


@pytest.mark.parametrize("change", ["today", "cell"])
def test_the_cached_issues_follow_the_content_and_the_day(
    change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """키는 내용 지문 + 오늘이다 — 같은 표·같은 날은 다시 고르지 않고, 하나가 바뀌면 새로 고른다."""
    simulation_cache._cached_schedule_confirmation_issues.clear()
    master = _master(_unit("EQ-1", 기존설비여부="N", 반입일정=_day(0), 반입상태="확정"))
    seen = _counting(monkeypatch)

    first = simulation_cache.get_schedule_confirmation_issues(master, today=TODAY)
    again = simulation_cache.get_schedule_confirmation_issues(master.copy(), today=TODAY)

    assert seen == [TODAY]
    assert first.empty  # 일정 당일은 아직 미확인이 아니다
    assert_frame_equal(again, first)

    day = TODAY
    if change == "today":
        day = TODAY + timedelta(days=1)
    else:
        master = master.copy()
        master.loc[0, "반입일정"] = _day(-1)
    moved = simulation_cache.get_schedule_confirmation_issues(master, today=day)

    assert seen == [TODAY, day]
    assert_frame_equal(moved, schedule_confirmation_issues(master, today=day))
    assert list(moved["확인구분"]) == [UNCONFIRMED]


# ------------------------------------------------------------------ 설비 마스터 탭


def test_the_master_tab_marks_each_unit_and_stage_to_check(tmp_path: Path, grid: Calls) -> None:
    """불러오기 줄 「일정 확인 필요 n대」 가 그 호기를 세고, 표 줄 설비명 풍선이 단계·갈래를
    말한다(개편 명세 4-1·4-4). 저장은 막지 않는다 — 고칠 것(오류)이 없다."""
    path = tmp_path / "equipment.duckdb"
    _saved(path, _late(), _done_without_actual(), _actual_but_open(), _unit("EQ-OK"))

    app = _app(path)
    assert sorted(_alert_ids(grid)) == ["s:EQ-DONE", "s:EQ-LATE", "s:EQ-MOVED"]
    # 「일정 확인 필요」 단추 — 브라우저가 그 호기 id 를 보낸다.
    load(app, _alert_ids(grid), kind="alerts")
    assert _row_alerts(grid) == {
        "s:EQ-LATE": f"반입 {UNCONFIRMED}",
        "s:EQ-DONE": f"Qual {MISSING_ACTUAL}",
        "s:EQ-MOVED": f"반입 {STATUS_UPDATE_NEEDED}",
    }
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    assert not app.exception
    assert last(grid, emg.side_key("changes"))["counts"]["errors"] == 0
    assert not app.error


def test_the_master_tab_shows_nothing_when_every_stage_is_consistent(
    tmp_path: Path, grid: Calls
) -> None:
    path = tmp_path / "equipment.duckdb"
    _saved(path, _unit("EQ-OK"), _unit("EQ-PLAN", Qual일정=_day(3), Qual상태="계획"))

    app = _app(path)
    assert _alert_ids(grid) == []
    load(app, [], kind="all")
    assert _row_alerts(grid) == {}


def test_the_master_tab_follows_unsaved_edits_and_the_put_rows(tmp_path: Path, grid: Calls) -> None:
    """편집본 기준이다 — 표에서 고친 저장 전 실적이 곧바로 그 호기를 빼고, 「엑셀·CSV로 한꺼번에」
    로 편집본에 넣은 행도 그렇다."""
    path = tmp_path / "equipment.duckdb"
    _saved(path, _late(), _done_without_actual())
    app = _app(path)
    assert sorted(_alert_ids(grid)) == ["s:EQ-DONE", "s:EQ-LATE"]

    load(app, [], kind="all")
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-DONE", "col": "Qual실적", "text": _day(-100)})
    assert _alert_ids(grid) == ["s:EQ-LATE"]

    app.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    app.run()
    app.text_area(key=CLIPBOARD_KEY).set_value(
        f"설비명\t반입실적\t반입상태\nEQ-LATE\t{_day(-29)}\t완료"
    )
    app.button(key=PREVIEW_BUTTON_KEY).click().run()
    assert not app.exception and not app.error
    app.button(key=IMPORT_APPLY_BUTTON_KEY).click().run()
    assert not app.exception
    assert _alert_ids(grid) == []
