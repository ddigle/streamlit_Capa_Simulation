# Purpose: 제약 시뮬레이션 화면의 보유 「호기 고르기」·목록에 없는 보유 칸·보유로 덮이면 신규를
# 붙이지 않는 글이 세션·잠김·알림·왕복을 지키는지 AppTest 로 본다.

"""보유 제약 설비 「호기 고르기」 화면(2026-11-01 사용자 결정 B1 · B3 — AppTest).

하네스는 `tests/test_constraint_simulation_options_page.py` 의 설비 DB 두 벌이다 — 시드 공정
하나(`DEMO_Chip_Attach`)에 기존보유 4대 + Qual 끝난 기존 신규 8대(`CA-01` ~ `CA-08`, 2025-01-10)와
신규 한 대. 제약 기간 첫 달(26.01) W/D 첫날은 2025-12-25 이고 시드 소요가 작아 제약 몫은 1대다.
숫자는 손계산 시험(`tests/test_constraint_simulation_holdings.py`)이 보고, 여기서는 칸·글·세션·
알림을 본다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_constraint_simulation_options_page import (
    BEFORE_NEW_UNIT,
    EARLY_UNIT,
    FAR_UNIT,
    NEW_UNIT,
    _options_database,
    _with_new_units,
)
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

import capa_simulation.services.constraint_simulation as constraint_simulation
from capa_simulation.components.constraint_simulation_view import NEW_SKIPPED_TEXT
from capa_simulation.constraint_simulation_state import (
    CONSTRAINT_HELD_DROPPED_KEY,
    CONSTRAINT_HELD_IDLE_KEY,
    CONSTRAINT_HELD_INPUT_KEY,
    CONSTRAINT_HELD_KEY,
    CONSTRAINT_MODIFY_KEY,
    CONSTRAINT_OWNED_KEY,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

HELD_LABEL = "보유 제약 호기"
ARRIVING_HELD = "CA-N5"
"""기간 첫 달 W/D 첫날(2025-12-25) 뒤 2026-03-11 에 기여를 시작하는 호기 — 보유로 고른다."""
LATE_NEW = "CA-N6"
"""2026-05-20 에 기여를 시작하는 신규 — 6월 W/D 첫날(5/25)이 개조 30일 안이다."""


@pytest.fixture(scope="module")
def early_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """신규 CA-N1 이 기간 첫 달 W/D 첫날(12/25) 나흘 전(12/21)부터 기여하는 벌."""
    root = tmp_path_factory.mktemp("constraint_simulation_held")
    return root / "scenario.duckdb", _options_database(
        root / "equipment.duckdb", new_unit=EARLY_UNIT, qual=date(2025, 12, 20)
    )


@pytest.fixture(scope="module")
def arriving_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """신규 CA-N2 가 기간 첫 달 W/D 첫날(12/25)에 기여를 시작하는 벌."""
    root = tmp_path_factory.mktemp("constraint_simulation_held_arriving")
    return root / "scenario.duckdb", _options_database(
        root / "equipment.duckdb", new_unit=NEW_UNIT, qual=date(2025, 12, 24)
    )


@pytest.fixture(scope="module")
def empty_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """설비 DB 가 빈 벌 — 까닭 카드 갈래."""
    root = tmp_path_factory.mktemp("constraint_simulation_held_empty")
    return root / "scenario.duckdb", root / "equipment.duckdb"


@pytest.fixture(scope="module")
def far_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """신규 CA-N0 이 1월 W/D 첫날(12/25)보다 개조 기간(30일)을 넘게 앞서(11/21) 들어온 벌."""
    root = tmp_path_factory.mktemp("constraint_simulation_held_far")
    return root / "scenario.duckdb", _options_database(
        root / "equipment.duckdb",
        new_unit=FAR_UNIT,
        qual=date(2025, 11, 20),
        arrival=date(2025, 11, 1),
    )


@pytest.fixture(scope="module")
def later_cover_databases(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """기존 8대에 축 안에서 들어오는 두 대(`ARRIVING_HELD` 3/11 · `LATE_NEW` 5/20)를 더한 벌."""
    root = tmp_path_factory.mktemp("constraint_simulation_held_later")
    path = root / "equipment.duckdb"
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    units = [
        _unit(
            f"CA-{index:02d}", date(2025, 1, 10), process=DYNAMIC_PROCESS, arrival=date(2024, 12, 1)
        )
        for index in range(1, 9)
    ]
    units.append(
        _unit(ARRIVING_HELD, date(2026, 3, 10), process=DYNAMIC_PROCESS, arrival=date(2026, 3, 1))
    )
    units.append(
        _unit(LATE_NEW, date(2026, 5, 19), process=DYNAMIC_PROCESS, arrival=date(2026, 5, 1))
    )
    baseline = pd.DataFrame(
        {"공정": [DYNAMIC_PROCESS], "분류": ["전체"], "기존보유대수": [4.0], "비고": [None]}
    )
    repository.save_snapshot(baseline, _master(units), _downtime([]))
    repository.save_process_cutoff(_cutoff(7, DYNAMIC_PROCESS))
    return root / "scenario.duckdb", path


def _june_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """시드 소요는 제약 몫이 늘 1대라 증가가 첫 달 하나뿐이다 — 26.06 부터 제약 소요를 1.5(×120% →
    2대)로 올려 둘째 증가를 세운다(합성 — 화면 갈래를 보려는 것이다)."""
    original = constraint_simulation.constraint_month_inputs

    def stepped(*args: Any, **kwargs: Any) -> Sequence[constraint_simulation.ConstraintMonthInput]:
        return [
            replace(row, required=max(row.required, 2.0), constrained_demand=1.5)
            if row.month >= 202606
            else row
            for row in original(*args, **kwargs)
        ]

    monkeypatch.setattr(constraint_simulation, "constraint_month_inputs", stepped)


def _pick(app: AppTest, *names: str) -> AppTest:
    app.multiselect(key=CONSTRAINT_HELD_INPUT_KEY).set_value(list(names))
    return _ok(app.run())


def _infos(app: AppTest) -> str:
    return " ".join(str(element.value) for element in app.info)


def test_the_picker_input_keeps_one_width_with_and_without_focus(
    early_databases: tuple[Path, Path],
) -> None:
    """「보유 제약 호기」 칸의 입력 칸은 초점 때도 넓어지지 않는다 — 1.63 multiselect 는 초점 때
    입력 칸 min-width 가 42px 로 늘어 칩 옆에 들지 못하면 새 줄로 내려가 칸이 한 줄 커진다.
    사이드바가 끝까지 내려가 있으면 그만큼 위 버튼(기준 확보율 · 개조 기간)이 밀려, 호기를 고른 뒤
    처음 누른 버튼이 다른 버튼 위에서 떼어져 사라졌다(2026-11-02 E2E). 행동은 브라우저로 잰다."""
    app = _opened(early_databases)

    rule = f".st-key-{CONSTRAINT_HELD_INPUT_KEY} input {{ min-width: 7px !important; }}"
    assert [el.proto.body for el in app.get("html") if rule in el.proto.body]


# ------------------------------------------------------------------ 선택지·기본값


def test_the_picker_lists_the_session_units_and_changes_nothing_until_picked(
    early_databases: tuple[Path, Path],
) -> None:
    """선택지는 그 공정 세션 설비 시나리오의 호기다(기존보유는 호기가 아니라 없다) — 호기 번호 차례.
    축 첫 W/D 날(12/25) 전에 기여를 시작한 호기는 날짜를 적지 않는다. 고르지 않으면 1판과 같은
    요약이고, 숫자 칸은 「목록에 없는 보유」 로 같이 선다(결정 B3-3)."""
    app = _opened(early_databases)
    picker = app.multiselect(key=CONSTRAINT_HELD_INPUT_KEY)
    assert picker.label == HELD_LABEL
    assert picker.value == []
    assert not picker.disabled
    assert picker.options == [
        "CA-01 · 환산 1",
        f"{EARLY_UNIT} · 환산 1",
        *(f"CA-{index:02d} · 환산 1" for index in range(2, 9)),
    ]
    assert app.number_input(key=CONSTRAINT_OWNED_KEY).label == (
        "목록에 없는 보유 제약 설비 (환산 대수)"
    )
    assert _metric(app, "개조 대수") == "1대"
    assert "보유" not in _header_line(app)


def test_a_unit_arriving_inside_the_axis_shows_its_start(tmp_path: Path) -> None:
    """축 안에서 기여를 시작하는 호기는 그날을 적는다 — 그날부터 보유로 센다."""
    databases = (
        tmp_path / "scenario.duckdb",
        _options_database(
            tmp_path / "equipment.duckdb",
            new_unit="CA-N5",
            qual=date(2026, 3, 10),
            arrival=date(2026, 3, 1),
        ),
    )
    app = _opened(databases)
    assert (
        "CA-N5 · 환산 1 · 2026-03-11 기여 시작"
        in app.multiselect(key=CONSTRAINT_HELD_INPUT_KEY).options
    )


# ------------------------------------------------------------------ 고르기


def test_picking_a_unit_holds_it_without_a_modification(
    early_databases: tuple[Path, Path],
) -> None:
    app = _pick(_opened(early_databases), "CA-01")
    assert _metric(app, "개조 대수") == "0대"
    assert _metric_caption(app, "개조 대수") == "전용 최대 1대 = 보유 1 · 개조 0"
    assert "보유 제약 호기 1대" in _header_line(app)
    captions = _plain(_captions(app))
    assert "고른 호기 1대 · 환산 합 1대" in captions
    assert "개조 없이 쓰는 전용 — 보유 제약 설비 1대(고른 호기 1대 · 보유 1대 중)" in captions
    assert "보유 호기 = " in captions and "에서 고른 1대" in captions
    assert app.session_state[CONSTRAINT_HELD_KEY] == {DYNAMIC_PROCESS: ["CA-01"]}


def test_picked_units_and_the_number_field_add_up(early_databases: tuple[Path, Path]) -> None:
    """고른 호기 + 목록에 없는 보유 칸 — 머리는 「보유 제약 호기 1대 + 2대」, 개조 일정 카드는
    출처를 둘 다 적는다."""
    app = _opened(early_databases)
    app.number_input(key=CONSTRAINT_OWNED_KEY).set_value(2)
    app = _pick(_ok(app.run()), "CA-03")
    assert "보유 제약 호기 1대 + 2대" in _header_line(app)
    captions = _plain(_captions(app))
    assert "보유 제약 설비 1대(고른 호기 1대 · 입력 2대 · 보유 3대 중)" in captions


def test_a_picked_new_unit_is_no_longer_a_new_unit(
    arriving_databases: tuple[Path, Path],
) -> None:
    """신규 CA-N2(12/25 기여 시작)를 보유로 고르면 신규 후보에서 빠진다 — 두 번 세지 않는다."""
    app = _with_new_units(_opened(arriving_databases), BEFORE_NEW_UNIT)
    assert f"기준일 이후 기여 시작 신규 설비 1대(조회기간에 가용 1대) · {NEW_UNIT}" in _plain(
        _captions(app)
    )
    app = _pick(app, NEW_UNIT)
    captions = _plain(_captions(app))
    assert "기준일 이후 기여를 시작하는 신규 설비가 없습니다." in captions
    assert _metric_caption(app, "개조 대수") == "전용 최대 1대 = 신규 0 · 보유 1 · 개조 0"
    assert "**신규 대기**" not in captions


def test_holdings_covering_the_period_skip_the_new_unit(
    early_databases: tuple[Path, Path],
) -> None:
    """보유(고른 CA-01)만으로 제약 기간을 다 덮으면 CA-N1(12/21)을 붙이지 않는다(결정 B1) — 옛
    차례였다면 CA-N1 이 1월 몫에 붙어 12/21 ~ 12/24 대기가 섰다."""
    app = _with_new_units(_opened(early_databases), BEFORE_NEW_UNIT)
    assert "**신규 대기** — 셋업 때부터 제약용으로 붙인 신규 설비" in _captions(app)
    app = _pick(app, "CA-01")
    captions = _plain(_captions(app))
    assert NEW_SKIPPED_TEXT in captions
    assert "**신규 대기**" not in captions
    assert (
        f"일반 설비가 된 신규 1대 — {EARLY_UNIT} · 보유 제약 설비로 제약 기간을 다 덮어 기존 "
        "제품 몫" in captions
    )
    assert _metric_caption(app, "개조 대수") == "전용 최대 1대 = 신규 0 · 보유 1 · 개조 0"
    assert not any("대기 4일" in _plain(text) for text in _markdown(app))


def test_a_later_cover_names_its_month_on_the_schedule_card(
    later_cover_databases: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """뒤 증가에서만 덮이는 꼴(결정 B1 — 증가마다). 1월 증가는 보유가 아직 없어(CA-N5 는 3/11)
    개조로 채우고, 6월 증가(W/D 첫날 5/25)에서 남은 보유 CA-N5 가 남은 증가를 다 덮어 그 증가부터
    신규를 붙이지 않는다 — B1 이 없었다면 CA-N6(5/20)이 6월 몫에 붙었다. 카드 한 줄은 그 달을
    적는다(첫 증가 꼴의 `NEW_SKIPPED_TEXT` 가 아니다 — 화면이 `new_stopped_line` 을 그리는지,
    2026-11-01 리뷰)."""
    _june_step(monkeypatch)
    app = _with_new_units(_opened(later_cover_databases), date(2026, 1, 1))
    app = _pick(app, ARRIVING_HELD)
    captions = _plain(_captions(app))
    assert (
        "26년 6월 증가부터는 남은 보유 제약 설비만으로 제약 기간 끝까지 늘어난 전용을 다 채워 신규 "
        "설비를 더 붙이지 않았습니다" in captions
    )
    assert NEW_SKIPPED_TEXT not in captions
    assert (
        f"일반 설비가 된 신규 1대 — {LATE_NEW} · 26년 6월 증가부터 보유 제약 설비로 다 덮어 기존 "
        "제품 몫" in captions
    )
    assert "**신규 대기**" not in captions


def test_a_first_cover_holding_back_no_unit_says_nothing_on_the_card(
    far_databases: tuple[Path, Path],
) -> None:
    """첫 증가에서 보유(CA-01)가 다 덮었지만 신규 CA-N0(11/21)은 1월 증가(12/25)가 34일 뒤라 B1 이
    없어도 붙지 않았다 — 카드 한 줄(`NEW_SKIPPED_TEXT`)은 서지 않고, 까닭은 창 안 증가 없음이다."""
    app = _with_new_units(_opened(far_databases), date(2025, 11, 1))
    app = _pick(app, "CA-01")
    captions = _plain(_captions(app))
    assert NEW_SKIPPED_TEXT not in captions
    assert "신규 설비를 더 붙이지 않았습니다" not in captions
    assert (
        f"일반 설비가 된 신규 1대 — {FAR_UNIT} · 개조 30일 안에 늘어날 전용이 없어 기존 제품 몫"
        in captions
    )


# ------------------------------------------------------------------ 시나리오에 없는 호기(B3-2)


def test_units_missing_from_the_scenario_are_dropped_with_one_notice(
    early_databases: tuple[Path, Path],
) -> None:
    """지금 설비 시나리오 · 조회기간의 이 공정 목록에 없는 호기는 고름에서 빼고 한 줄로 알린다(결정
    B3-2 — 선택지가 조회기간에 하루라도 있는 호기라 조회기간을 좁혀 빠진 호기도 같다).
    알림은 같은 화면에 남고, 고름을 바꾸면 걷힌다. 다른 공정의 고름은 그대로다."""
    app = _app(early_databases)
    app.session_state[CONSTRAINT_HELD_KEY] = {
        DYNAMIC_PROCESS: ["CA-02", "CA-GONE"],
        "DEMO_Other": ["X-1"],
    }
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    notice = _plain(_infos(app))
    assert "지금 설비 시나리오 · 조회기간의 이 공정 목록에 없는 1대(CA-GONE)를 뺐습니다" in notice
    assert app.multiselect(key=CONSTRAINT_HELD_INPUT_KEY).value == ["CA-02"]
    assert app.session_state[CONSTRAINT_HELD_KEY] == {
        DYNAMIC_PROCESS: ["CA-02"],
        "DEMO_Other": ["X-1"],
    }
    assert "보유 제약 호기 1대" in _header_line(app)

    _ok(app.run())
    assert "CA-GONE" in _plain(_infos(app))

    app = _pick(app, "CA-02", "CA-04")
    assert "CA-GONE" not in _plain(_infos(app))
    assert CONSTRAINT_HELD_DROPPED_KEY not in app.session_state
    assert "보유 제약 호기 2대" in _header_line(app)


# ------------------------------------------------------------------ 잠김·왕복·멈춘 갈래


def test_turning_modification_off_locks_the_picker_and_keeps_the_picks(
    early_databases: tuple[Path, Path],
) -> None:
    app = _pick(_opened(early_databases), "CA-01")
    app.toggle(key=CONSTRAINT_MODIFY_KEY).set_value(False)
    _ok(app.run())
    picker = app.multiselect(key=CONSTRAINT_HELD_INPUT_KEY)
    assert picker.disabled and picker.value == ["CA-01"]
    assert "보유" not in _header_line(app)
    assert _metric(app, "개조 대수") == "—"

    app.toggle(key=CONSTRAINT_MODIFY_KEY).set_value(True)
    _ok(app.run())
    assert "보유 제약 호기 1대" in _header_line(app)


def test_the_picks_survive_a_round_trip(early_databases: tuple[Path, Path]) -> None:
    app = _pick(_opened(early_databases), "CA-05", "CA-06")
    app.session_state["_test_page"] = "away"
    _ok(app.run())
    app.session_state["_test_page"] = "constraint"
    _ok(app.run())
    assert app.multiselect(key=CONSTRAINT_HELD_INPUT_KEY).value == ["CA-05", "CA-06"]
    assert "보유 제약 호기 2대" in _header_line(app)


def test_a_stopped_branch_stands_an_idle_picker(empty_databases: tuple[Path, Path]) -> None:
    """설비 일정이 서지 않는 공정(빈 설비 DB)은 까닭 카드 갈래다 — 카드에는 잠긴 빈 고르기 칸이 제
    key 로 선다(카드 모양이 같게 — 페이지 위젯은 key 를 받는다, AGENTS 9장). 정본은 건드리지
    않는다."""
    app = _app(empty_databases)
    app.session_state[CONSTRAINT_HELD_KEY] = {DYNAMIC_PROCESS: ["CA-01"]}
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    idle = [element for element in app.multiselect if element.label == HELD_LABEL]
    assert len(idle) == 1 and idle[0].disabled and idle[0].options == []
    assert app.multiselect(key=CONSTRAINT_HELD_IDLE_KEY).proto.placeholder == (
        "설비 일정이 서는 공정에서 고릅니다"
    )
    assert app.session_state[CONSTRAINT_HELD_KEY] == {DYNAMIC_PROCESS: ["CA-01"]}


@pytest.mark.parametrize("broken", [["CA-01"], "CA-01", 3])
def test_a_broken_held_map_is_read_as_empty(
    early_databases: tuple[Path, Path], broken: object
) -> None:
    """정본 칸이 틀린 꼴이면 빈 것으로 본다 — 위젯 예외 없이 고름이 비어 선다."""
    app = _app(early_databases)
    app.session_state[CONSTRAINT_HELD_KEY] = broken
    app.query_params["process"] = DYNAMIC_PROCESS
    _ok(app.run())
    assert app.multiselect(key=CONSTRAINT_HELD_INPUT_KEY).value == []
