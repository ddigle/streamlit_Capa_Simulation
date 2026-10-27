# Purpose: 설비 DB 의 입력 비가동이 공정 Capa 상세·필요 단축 일정·제약 시뮬레이션에 닿는지 본다.

"""입력 비가동 대수(설비 `0032`)가 계산 화면에 실제로 닿는가(AppTest).

키 수준 시험(`tests/test_manual_downtime_plan.py`)은 계획 키에 칸을 **싣는가** 만 본다. 어느 화면이
`load_manual_downtime(equipment_path)` 대신 빈 `ManualDowntime()` 을 넘기거나 출처 띠를 빠뜨리는
회귀는 그 시험이 잡지 못한다(2026-10-27 리뷰). 여기서는 설비 DB 에 칸을 심고 화면을 띄워 그 칸이
닿은 흔적 — 공정 Capa 상세 ④ 줄·② 제목 꼬리·닫는 알림, 필요 단축 일정 출처 줄과 줄어든 가용(공정·월
CSV), 제약 시뮬레이션 출처 띠 — 을 본다. 하네스는 각 화면 시험의 것을 그대로 쓴다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from shortening_script import months_from_today
from test_constraint_simulation_page import _captions as constraint_captions
from test_constraint_simulation_page import _equipment_database
from test_constraint_simulation_page import _opened as constraint_opened
from test_process_capa_detail_page import DYNAMIC_PROCESS, _dynamic_app, _label_texts
from test_required_shortening import _cutoff, _downtime, _master, _unit
from test_required_shortening_tab import _csv
from test_required_shortening_tab import _database as shortening_database
from test_required_shortening_tab import _run as shortening_run

from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_manual_downtime_cache,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_samples import sample_equipment_master
from capa_simulation.services.manual_downtime import MANUAL_DOWNTIME_BAND, period_months

# 시드·샘플 축이 어디에 있든 덮도록 넓게 심는 달(칸마다 0.5대).
WIDE_MONTHS = period_months(202501, 202812)


def _seed(equipment_path: Path, process: str, months: tuple[int, ...], units: float) -> None:
    """설비 DB 에 입력 비가동 칸을 심는다(Preference 저장과 같은 저장소 길)."""
    DuckDBEquipmentRepository(equipment_path).save_manual_downtime(
        {(process, month): units for month in months},
        processes=[process],
        months=months,
        expected_version=None,
        saved_by="시험",
    )
    clear_manual_downtime_cache()


def _texts(app: object) -> str:
    """캡션·마크다운·알림 글 전부."""
    parts: list[str] = []
    for kind in ("caption", "markdown", "info", "warning", "success"):
        parts += [str(element.value) for element in getattr(app, kind)]
    return " ".join(parts)


@pytest.fixture()
def detail_databases(tmp_path: Path) -> tuple[Path, Path]:
    """공정 Capa 상세 설비 일정 하네스(`dynamic_databases` 와 같은 호기)의 따로 된 한 벌."""
    equipment_path = tmp_path / "equipment.duckdb"
    repository = DuckDBEquipmentRepository(equipment_path)
    repository.initialize()
    master = _master(
        [
            _unit("DA-01", date(2026, 12, 10), process=DYNAMIC_PROCESS, arrival=date(2026, 11, 1)),
            _unit("DA-02", date(2027, 1, 20), process=DYNAMIC_PROCESS, arrival=date(2026, 12, 1)),
        ]
    )
    baseline = pd.DataFrame(
        {"공정": [DYNAMIC_PROCESS], "분류": ["전체"], "기존보유대수": [3.0], "비고": [None]}
    )
    repository.save_snapshot(
        baseline, master, _downtime([("DA-01", date(2026, 12, 20), date(2026, 12, 24))])
    )
    repository.save_process_cutoff(_cutoff(10, DYNAMIC_PROCESS))
    return tmp_path / "scenario.duckdb", equipment_path


def test_process_capa_detail_draws_the_entered_row_and_names_it(
    detail_databases: tuple[Path, Path],
) -> None:
    before = _dynamic_app(detail_databases)
    assert "월별 비가동 대수(입력)" not in _label_texts(before)
    assert MANUAL_DOWNTIME_BAND not in _texts(before)

    _seed(detail_databases[1], DYNAMIC_PROCESS, WIDE_MONTHS, 0.5)
    app = _dynamic_app(detail_databases)
    labels = _label_texts(app)
    # ④ 첫 줄과 ② 제목 꼬리.
    assert "월별 비가동 대수(입력)" in labels
    assert f"· {MANUAL_DOWNTIME_BAND}" in labels
    # 닫는 알림 — 계획이 건 칸(이 공정·축의 달)이다. 호기가 있는 공정이라 ④ 첫 줄을 가리킨다.
    texts = _texts(app)
    assert f"{MANUAL_DOWNTIME_BAND}(" in texts
    assert "② 가용에서 뺐습니다(④ 첫 줄)" in texts
    clear_equipment_repository()


def test_process_capa_detail_points_below_two_when_there_are_no_units(tmp_path: Path) -> None:
    """호기 일정이 없는 공정(기존보유만)은 ④ 가 서지 않아 입력 줄이 ② 아래에 선다 — 닫는 알림도
    그 자리를 가리킨다(2026-10-27 리뷰 nit)."""
    equipment_path = tmp_path / "equipment.duckdb"
    repository = DuckDBEquipmentRepository(equipment_path)
    repository.initialize()
    baseline = pd.DataFrame(
        {"공정": [DYNAMIC_PROCESS], "분류": ["전체"], "기존보유대수": [5.0], "비고": [None]}
    )
    repository.save_snapshot(baseline, _master([]), _downtime([]))
    repository.save_process_cutoff(_cutoff(10, DYNAMIC_PROCESS))
    _seed(equipment_path, DYNAMIC_PROCESS, WIDE_MONTHS, 0.5)

    app = _dynamic_app((tmp_path / "scenario.duckdb", equipment_path))
    assert "월별 비가동 대수(입력)" in _label_texts(app)
    texts = _texts(app)
    assert "② 가용에서 뺐습니다(② 아래 줄)" in texts
    assert "(④ 첫 줄)" not in texts
    clear_equipment_repository()


def test_required_shortening_takes_the_input_from_the_available_units(tmp_path: Path) -> None:
    database_path = shortening_database(tmp_path)
    before = shortening_run(database_path)
    assert not before.exception, [element.message for element in before.exception]
    _, plain = _csv(before, "equipment_shortening_months_csv")
    process = sorted(set(sample_equipment_master()["공정소분류"]))[0]

    # 그 공정 축의 달마다 0.5대 — 가용이 0.5 보다 작은 달은 0 에서 멈춘다.
    _seed(database_path, process, tuple(months_from_today()), 0.5)
    app = shortening_run(database_path)
    assert not app.exception, [element.message for element in app.exception]
    captions = " ".join(str(element.value) for element in app.caption)
    assert f"{MANUAL_DOWNTIME_BAND}(" in captions
    assert "가용설비 현황 › Preference 의 공정 × 달 비가동" in captions

    _, entered = _csv(app, "equipment_shortening_months_csv")

    def available(frame: pd.DataFrame) -> dict[str, float]:
        rows = frame.loc[frame["공정"].eq(process)]
        return {
            str(month): float(value)
            for month, value in zip(rows["생산계획년월"], rows["가용대수"], strict=True)
        }

    old, new = available(plain), available(entered)
    assert old
    for month, value in old.items():
        assert new[month] == pytest.approx(max(value - 0.5, 0.0), abs=0.011)
    # 다른 공정은 그대로다.
    others = plain.loc[plain["공정"].ne(process)].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        entered.loc[entered["공정"].ne(process)].reset_index(drop=True), others
    )
    clear_equipment_repository()


def test_constraint_simulation_names_the_entered_downtime_in_its_band(tmp_path: Path) -> None:
    databases = (tmp_path / "scenario.duckdb", _equipment_database(tmp_path / "equipment.duckdb"))
    before = constraint_opened(databases)
    assert MANUAL_DOWNTIME_BAND not in constraint_captions(before)

    _seed(databases[1], DYNAMIC_PROCESS, WIDE_MONTHS, 0.5)
    app = constraint_opened(databases)
    band = constraint_captions(app)
    assert "가용 = 설비 일정 기준" in band
    assert f"{MANUAL_DOWNTIME_BAND}(" in band
    # 모든 달 가용 12 라 넘친 칸은 없다.
    assert "가용 넘침" not in band
    clear_equipment_repository()
