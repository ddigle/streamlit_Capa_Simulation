# Purpose: 제약 시뮬레이션 화면의 보유 제약 설비·「신규 설비는 개조 없이」 칸이 잠김·결과 글·캐시
# 공유· 오류 갈래를 지키는지 AppTest 로 본다.

"""제약 시뮬레이션 2판 옵션 화면(AppTest — 하네스는 `tests/test_constraint_simulation_page.py`).

설비 DB 는 시드 공정 하나(`DEMO_Chip_Attach`)에 기존보유 4대 + Qual 끝난 기존 신규 8대(2025-01-10)에
**축 안에서 붙는 신규 한 대**(`CA-N1` — Qual 2025-12-20, 기여 시작 12/21)를 더한다. Cut-off 7 이면
1월 W/D (2025-12-24, 2026-01-24] 를 다 덮고 12월 W/D 는 4/31 만 덮어 1월에 새로 붙는 1대다(반 달
몫은 다음 달 몫). 시드 소요가 작아 제약 몫은 기간 첫 달(26.01) 1대뿐이다 — 숫자는 손계산 시험
(`tests/test_constraint_simulation_options.py`)이 보고, 여기서는 칸·글·캐시·오류 갈래를 본다. 시험은
오늘에 기대지 않게 기준일 칸을 늘 직접 적는다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_constraint_simulation_page import (
    DYNAMIC_PROCESS,
    _app,
    _captions,
    _header_line,
    _markdown,
    _metric,
    _metric_caption,
    _ok,
    _opened,
    _plain,
)
from test_required_shortening import _cutoff, _downtime, _master, _unit

import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.constraint_simulation_view import FREE_ONLY_TEXT
from capa_simulation.constraint_simulation_state import (
    CONSTRAINT_MODIFY_KEY,
    CONSTRAINT_NEW_SINCE_KEY,
    CONSTRAINT_NEW_UNITS_KEY,
    CONSTRAINT_OWNED_KEY,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.process_equipment_timeline import build_process_equipment_timeline

NEW_UNIT = "CA-N1"
BEFORE_NEW_UNIT = date(2025, 12, 1)
AFTER_NEW_UNIT = date(2026, 2, 1)


def _options_database(path: Path) -> Path:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    units = [
        _unit(
            f"CA-{index:02d}", date(2025, 1, 10), process=DYNAMIC_PROCESS, arrival=date(2024, 12, 1)
        )
        for index in range(1, 9)
    ]
    units.append(
        _unit(NEW_UNIT, date(2025, 12, 20), process=DYNAMIC_PROCESS, arrival=date(2025, 12, 1))
    )
    baseline = pd.DataFrame(
        {"공정": [DYNAMIC_PROCESS], "분류": ["전체"], "기존보유대수": [4.0], "비고": [None]}
    )
    repository.save_snapshot(baseline, _master(units), _downtime([]))
    repository.save_process_cutoff(_cutoff(7, DYNAMIC_PROCESS))
    return path


@pytest.fixture(scope="module")
def option_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("constraint_simulation_options")
    return root / "scenario.duckdb", _options_database(root / "equipment.duckdb")


@pytest.fixture()
def timeline_builds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """설비 일정 계산(캐시 래퍼 안)을 세는 대역 — 캐시를 비우고 센다."""
    calls: list[str] = []
    original = build_process_equipment_timeline

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(str(kwargs.get("process")))
        return original(*args, **kwargs)

    monkeypatch.setattr(simulation_cache, "build_process_equipment_timeline", counting)
    simulation_cache.get_process_equipment_timeline.clear()
    return calls


def _with_new_units(app: AppTest, since: date) -> AppTest:
    """브라우저처럼 — 토글을 켠 회차 뒤에야 기준일 칸이 풀린다."""
    app.toggle(key=CONSTRAINT_NEW_UNITS_KEY).set_value(True)
    _ok(app.run())
    app.date_input(key=CONSTRAINT_NEW_SINCE_KEY).set_value(since)
    return _ok(app.run())


# ------------------------------------------------------------------ 기본값·잠김


def test_the_defaults_keep_the_first_version_and_skip_the_timeline(
    option_databases: tuple[Path, Path], timeline_builds: list[str]
) -> None:
    """보유 0 · 신규 끔이 기본 — 1판과 같은 요약이고 설비 일정 칸은 받지 않는다(끈 세션 비용 0)."""
    app = _opened(option_databases)
    assert app.number_input(key=CONSTRAINT_OWNED_KEY).value == 0
    assert app.toggle(key=CONSTRAINT_NEW_UNITS_KEY).value is False
    assert isinstance(app.date_input(key=CONSTRAINT_NEW_SINCE_KEY).value, date)
    assert not app.number_input(key=CONSTRAINT_OWNED_KEY).disabled
    assert not app.toggle(key=CONSTRAINT_NEW_UNITS_KEY).disabled
    assert app.date_input(key=CONSTRAINT_NEW_SINCE_KEY).disabled
    assert _metric(app, "개조 대수") == "1대"
    assert _metric_caption(app, "개조 대수").startswith("1번에 나눠 개조 · 첫 비가동 ")
    assert "보유" not in _header_line(app) and "신규" not in _header_line(app)
    assert "개조 없이 쓰는 전용" not in _captions(app)
    assert timeline_builds == []


def test_turning_modification_off_locks_both_options(
    option_databases: tuple[Path, Path],
) -> None:
    app = _opened(option_databases)
    app.number_input(key=CONSTRAINT_OWNED_KEY).set_value(3)
    app = _with_new_units(app, BEFORE_NEW_UNIT)
    app.toggle(key=CONSTRAINT_MODIFY_KEY).set_value(False)
    _ok(app.run())
    assert app.number_input(key=CONSTRAINT_OWNED_KEY).disabled
    assert app.toggle(key=CONSTRAINT_NEW_UNITS_KEY).disabled
    assert app.date_input(key=CONSTRAINT_NEW_SINCE_KEY).disabled
    # 걸리지 않은 조건은 머리·결과에 남지 않는다 — 위젯 값은 세션에 그대로다.
    header = _header_line(app)
    assert "개조 없음" in header and "보유" not in header and "신규" not in header
    assert _metric(app, "개조 대수") == "—"
    assert app.session_state[CONSTRAINT_OWNED_KEY] == 3
    assert app.session_state[CONSTRAINT_NEW_UNITS_KEY] is True


# ------------------------------------------------------------------ 보유 제약 설비


def test_owned_units_replace_the_modification_and_say_so(
    option_databases: tuple[Path, Path],
) -> None:
    app = _opened(option_databases)
    app.number_input(key=CONSTRAINT_OWNED_KEY).set_value(1)
    _ok(app.run())
    assert _metric(app, "개조 대수") == "0대"
    assert _metric_caption(app, "개조 대수") == (
        "전용 최대 1대 = 보유 1 · 개조 0 — 개조 비가동 없음"
    )
    assert "보유 제약 1대" in _header_line(app)
    captions = _captions(app)
    assert "개조 없이 쓰는 전용 — 보유 제약 설비 1대(입력 1대 중)" in captions
    assert FREE_ONLY_TEXT in captions
    assert not any("비가동 · **" in text for text in _markdown(app))


# ------------------------------------------------------------------ 신규 설비는 개조 없이


def test_new_units_follow_the_reference_day_through_one_shared_timeline(
    option_databases: tuple[Path, Path], timeline_builds: list[str]
) -> None:
    """기준일 12/1 이면 CA-N1(기여 시작 12/21)이 신규라 1월 몫 1대를 개조 없이 덮는다. 기준일만
    바꾸면 같은 설비 일정 칸을 다시 쓴다(기준일은 캐시 키 밖) — 2/1 이면 신규가 없어 1판과 같다."""
    app = _with_new_units(_opened(option_databases), BEFORE_NEW_UNIT)
    assert not app.date_input(key=CONSTRAINT_NEW_SINCE_KEY).disabled
    captions = _plain(_captions(app))
    assert f"기준일 이후 기여 시작 신규 설비 1대(조회기간에 가용 1대) · {NEW_UNIT}" in captions
    assert "신규 = 기여 시작 2025-12-01 이후 호기 1대(공정 Capa 상세 ③ 과 같은 날짜)" in captions
    assert "신규 개조 없이(2025-12-01~)" in _header_line(app)
    assert _metric(app, "개조 대수") == "0대"
    assert _metric_caption(app, "개조 대수") == (
        "전용 최대 1대 = 신규 1 · 개조 0 — 개조 비가동 없음"
    )
    assert "신규 설비 1대(기준일 2025-12-01 이후 기여 시작 · 들어온 달 몫만)" in captions
    assert timeline_builds == [DYNAMIC_PROCESS]

    app.date_input(key=CONSTRAINT_NEW_SINCE_KEY).set_value(AFTER_NEW_UNIT)
    _ok(app.run())
    assert "기준일 이후 기여를 시작하는 신규 설비가 없습니다." in _captions(app)
    assert _metric(app, "개조 대수") == "1대"
    assert timeline_builds == [DYNAMIC_PROCESS]


def test_the_detail_page_and_this_page_share_one_timeline(
    option_databases: tuple[Path, Path], timeline_builds: list[str]
) -> None:
    """공정 Capa 상세 → 이 화면(신규 켬): 설비 일정은 상세에서만 돈다(같은 키 — 새 캐시 없음)."""
    app = _app(option_databases)
    app.session_state[CONSTRAINT_NEW_UNITS_KEY] = True
    app.session_state[CONSTRAINT_NEW_SINCE_KEY] = BEFORE_NEW_UNIT
    app.session_state["_test_page"] = "detail"
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    assert timeline_builds == [DYNAMIC_PROCESS]
    app.session_state["_test_page"] = "constraint"
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    assert _metric(app, "개조 대수") == "0대"
    assert timeline_builds == [DYNAMIC_PROCESS]


def test_the_options_survive_a_round_trip(option_databases: tuple[Path, Path]) -> None:
    app = _opened(option_databases)
    app.number_input(key=CONSTRAINT_OWNED_KEY).set_value(2)
    app = _with_new_units(app, BEFORE_NEW_UNIT)
    app.session_state["_test_page"] = "away"
    _ok(app.run())
    app.session_state["_test_page"] = "constraint"
    _ok(app.run())
    assert app.number_input(key=CONSTRAINT_OWNED_KEY).value == 2
    assert app.toggle(key=CONSTRAINT_NEW_UNITS_KEY).value is True
    assert app.date_input(key=CONSTRAINT_NEW_SINCE_KEY).value == BEFORE_NEW_UNIT


def test_a_broken_session_value_is_reseeded(option_databases: tuple[Path, Path]) -> None:
    """범위 밖 보유 값·날짜가 아닌 기준일은 위젯 앞에서 기본값으로 다시 심는다(위젯 예외 없음)."""
    app = _app(option_databases)
    app.session_state[CONSTRAINT_OWNED_KEY] = 5000
    app.session_state[CONSTRAINT_NEW_SINCE_KEY] = "2026-01-01"
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    assert app.number_input(key=CONSTRAINT_OWNED_KEY).value == 0
    assert isinstance(app.date_input(key=CONSTRAINT_NEW_SINCE_KEY).value, date)


def test_a_timeline_failure_is_an_equipment_error(
    option_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """설비 일정 계산이 터지면 「설비 일정을 계산하지 못했습니다」 다(「제약 시뮬레이션을 …」 가
    아니다)."""

    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("설비 마스터 계약 위반(시험)")

    monkeypatch.setattr(simulation_cache, "build_process_equipment_timeline", broken)
    simulation_cache.get_process_equipment_timeline.clear()
    app = _with_new_units(_opened(option_databases), BEFORE_NEW_UNIT)
    errors = " ".join(str(item.value) for item in app.error)
    assert "설비 일정을 계산하지 못했습니다" in errors
    assert "제약 시뮬레이션을 계산하지 못했습니다" not in errors
    assert not app.metric
