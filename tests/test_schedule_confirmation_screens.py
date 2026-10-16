# Purpose: 일정 확인 알림이 RawData 경고 줄·목록과 캐시에 편집본·오늘 기준으로 잇는지 본다.

"""일정 확인 알림의 화면 연결(2026-10-16 사용자 결정 3 — 저장은 막지 않는다).

- **RawData** — 편집표 위 늘 서 있는 알림 칸에 「미확인 N대 · 실적 누락 N대 · 상태 갱신 필요
  N대」 한 줄과 접힌 목록. 편집본(미리보기 중이면 저장될 후보) 기준이라 저장하지 않은 편집이
  바로 보인다. 0 이면 줄도 목록도 없다.
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
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

from capa_simulation.components.equipment_data_workspace import (
    BUFFER_KEY,
    CLIPBOARD_KEY,
    CONFIRMATION_EXPANDER_KEY,
    DOWNLOADS_EXPANDER_KEY,
    EQUIPMENT_EDITOR_KEY,
    PREVIEW_BUTTON_KEY,
    TARGET_KEY,
    WORKSPACE_TABS_KEY,
)
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
    # 실제 페이지처럼 최신 리비전만 읽고 페이지와 같은 「오늘」을 넘긴다.
    return AppTest.from_string(
        f"""
from datetime import date
from pathlib import Path
from capa_simulation.components.equipment_data_workspace import render_equipment_data_workspace
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
repository = DuckDBEquipmentRepository(Path({str(path)!r}))
repository.initialize()
snapshot = repository.load_snapshot(repository.latest_revision_id())
render_equipment_data_workspace(
    repository=repository, latest_snapshot=snapshot,
    baseline=snapshot.baseline, equipment=snapshot.equipment, downtime=snapshot.downtime,
    floor_canvases={{}}, max_extent=(100.0, 60.0), today=date.fromisoformat({TODAY.isoformat()!r}),
)
""",
        default_timeout=30,
    ).run()


def _confirmation_lines(app: AppTest) -> list[str]:
    return [
        item.value
        for item in app.warning
        if any(kind in item.value for kind in (UNCONFIRMED, MISSING_ACTUAL, STATUS_UPDATE_NEEDED))
    ]


def _confirmation_list(app: AppTest) -> Any:
    return app.get_by_key(CONFIRMATION_EXPANDER_KEY)


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


# ------------------------------------------------------------------ RawData


def test_rawdata_warns_in_one_line_and_lists_each_unit_and_stage(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    _saved(path, _late(), _done_without_actual(), _actual_but_open(), _unit("EQ-OK"))

    app = _app(path)

    assert not app.exception
    (line,) = _confirmation_lines(app)
    assert line.startswith(
        f"{UNCONFIRMED} 1대 · {MISSING_ACTUAL} 1대 · {STATUS_UPDATE_NEEDED} 1대 — "
    )
    listing = _confirmation_list(app)
    assert listing.label == "일정 확인 목록 · 3건"
    # 빈 일정·실적은 빈칸이다 — 자리표시 글자를 비워 두지 않으면 브라우저가 "None" 을 그린다.
    proto = listing.dataframe[0].proto
    assert proto.HasField("placeholder") and proto.placeholder == ""
    table = listing.dataframe[0].value
    assert list(table.columns) == [
        "확인구분",
        "설비명",
        "공정소분류",
        "단계",
        "일정",
        "실적",
        "상태",
    ]
    assert list(zip(table["확인구분"], table["설비명"], table["단계"], strict=True)) == [
        (UNCONFIRMED, "EQ-LATE", "반입"),
        (MISSING_ACTUAL, "EQ-DONE", "Qual"),
        (STATUS_UPDATE_NEEDED, "EQ-MOVED", "반입"),
    ]
    # 저장을 막지 않는다 — 오류가 없다.
    assert not app.error


def test_rawdata_shows_nothing_when_every_stage_is_consistent(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    _saved(path, _unit("EQ-OK"), _unit("EQ-PLAN", Qual일정=_day(3), Qual상태="계획"))

    app = _app(path)

    assert not app.exception
    assert _confirmation_lines(app) == []
    with pytest.raises(KeyError):
        _confirmation_list(app)


def test_rawdata_follows_unsaved_edits_and_the_preview_candidate(tmp_path: Path) -> None:
    """편집본 기준이다 — 저장하지 않은 고침이 바로 줄에서 빠지고, 미리보기 중이면 저장될
    후보를 본다."""
    path = tmp_path / "equipment.duckdb"
    _saved(path, _late(), _done_without_actual())
    app = _app(path)
    assert [line.split(" — ")[0] for line in _confirmation_lines(app)] == [
        f"{UNCONFIRMED} 1대 · {MISSING_ACTUAL} 1대"
    ]

    # EQ-DONE 의 Qual실적을 채운 편집본(저장 안 함). 편집본을 바꾸는 공용 길
    # (`replace_equipment_buffer`)처럼 편집표의 적용된 보기도 함께 버린다 — 남기면 다음 제출이 옛
    # 보기로 그 편집을 되돌린다.
    baseline, equipment, downtime = app.session_state[BUFFER_KEY]
    edited = equipment.copy()
    edited.loc[edited["설비명"].eq("EQ-DONE"), "Qual실적"] = pd.Timestamp(_day(-100))
    app.session_state[BUFFER_KEY] = (baseline, edited, downtime)
    del app.session_state[f"{EQUIPMENT_EDITOR_KEY}_applied_view"]
    app.run()
    assert not app.exception
    assert [line.split(" — ")[0] for line in _confirmation_lines(app)] == [f"{UNCONFIRMED} 1대"]
    assert _confirmation_list(app).label == "일정 확인 목록 · 1건"

    # 붙여넣기 미리보기가 EQ-LATE 의 반입실적·반입상태를 채운다 — 저장될 후보에는 남은 것이 없다.
    app.selectbox(TARGET_KEY).set_value("설비 마스터")
    app.text_area(CLIPBOARD_KEY).set_value(
        f"설비명\t반입실적\t반입상태\nEQ-LATE\t{_day(-29)}\t완료"
    )
    app.button(PREVIEW_BUTTON_KEY).click().run()
    assert not app.exception
    assert not app.error
    assert _confirmation_lines(app) == []


def test_the_confirmation_list_does_not_shift_the_keyed_blocks_below(tmp_path: Path) -> None:
    """목록은 늘 서 있는 알림 칸 안이다 — 생기고 사라져도 아래 내려받기·작업 탭의 자리가
    그대로다."""
    quiet_path = tmp_path / "quiet.duckdb"
    noisy_path = tmp_path / "noisy.duckdb"
    _saved(quiet_path, _unit("EQ-OK"))
    _saved(noisy_path, _late(), _done_without_actual())

    def slots(app: AppTest) -> dict[str, int]:
        found: dict[str, int] = {}
        for index, node in app.main.children.items():
            for key in (DOWNLOADS_EXPANDER_KEY, WORKSPACE_TABS_KEY):
                if any(getattr(inner, "key", None) == key for inner in node):
                    found[key] = int(index)
        return found

    quiet, noisy = _app(quiet_path), _app(noisy_path)

    assert _confirmation_lines(quiet) == [] and _confirmation_lines(noisy)
    assert slots(noisy) == slots(quiet)
    assert set(slots(quiet)) == {DOWNLOADS_EXPANDER_KEY, WORKSPACE_TABS_KEY}
