# Purpose: 설비 DB 의 입력 비가동이 공정 Capa 상세·필요 단축 일정·제약 시뮬레이션에 닿는지 본다.

"""입력 비가동 대수(설비 `0032`)가 계산 화면에 실제로 닿는가(AppTest).

키 수준 시험(`tests/test_manual_downtime_plan.py`)은 계획 키에 칸을 **싣는가** 만 본다. 어느 화면이
`load_manual_downtime(equipment_path)` 대신 빈 `ManualDowntime()` 을 넘기거나 출처 띠를 빠뜨리는
회귀는 그 시험이 잡지 못한다(2026-10-27 리뷰). 여기서는 설비 DB 에 칸을 심고 화면을 띄워 그 칸이
닿은 흔적 — 공정 Capa 상세 ⑤ 첫 줄·닫는 알림, 필요 단축 일정 출처 줄과 줄어든 가용(공정·월
CSV), 제약 시뮬레이션 상태 알림 `CS-05`(두 모드) — 을 본다. 하네스는 각 화면 시험의 것을 그대로
쓴다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from alert_marks import active_state, data_error_marks, states
from shortening_script import months_from_today
from streamlit.testing.v1 import AppTest
from test_constraint_simulation_page import _captions as constraint_captions
from test_constraint_simulation_page import _equipment_database
from test_constraint_simulation_page import _opened as constraint_opened
from test_modification_schedule_page import _schedule as schedule_opened
from test_process_capa_detail_page import DYNAMIC_PROCESS, _dynamic_app, _label_texts
from test_required_shortening import _cutoff, _downtime, _master, _unit
from test_required_shortening_tab import _csv
from test_required_shortening_tab import _database as shortening_database
from test_required_shortening_tab import _run as shortening_run

import capa_simulation.page_bootstrap as page_bootstrap
from capa_simulation.components.required_shortening_panel import MANUAL_NOTICE_HELP
from capa_simulation.navigation import AVAILABLE_EQUIPMENT_STATUS
from capa_simulation.page_tabs_state import tab_label
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


def _manual_mark_help(app: AppTest) -> str:
    """공정 Capa 상세 정리 줄의 「입력 비가동 반영(…)」 값 한 마디의 풍선."""
    marks = [item for item in app.caption if f"{MANUAL_DOWNTIME_BAND}(" in str(item.value)]
    assert len(marks) == 1, [str(item.value) for item in app.caption]
    return str(marks[0].help)


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
    assert "월별 비가동대수(입력)" not in _label_texts(before)
    assert MANUAL_DOWNTIME_BAND not in _texts(before)

    _seed(detail_databases[1], DYNAMIC_PROCESS, WIDE_MONTHS, 0.5)
    app = _dynamic_app(detail_databases)
    labels = _label_texts(app)
    # ⑤ 첫 줄. ② 제목 줄에는 꼬리를 달지 않는다 — ② 가용은 비가동을 빼기 전 값이고 입력 비가동은
    # ③ 비가동대수에 든다(2026-11-12 사용자 답 n1 (가)).
    assert "월별 비가동대수(입력)" in labels
    assert not any(MANUAL_DOWNTIME_BAND in label for label in labels)
    # 정리 줄의 값 한 마디 — 계획이 건 칸(이 공정·축의 달)이다. 그 자리는 풍선이 말한다(설명은 자리
    # 글이 아니다 — UI-TXT-01). 호기가 있는 공정이라 ⑤ 첫 줄을 가리킨다.
    texts = _texts(app)
    assert f"{MANUAL_DOWNTIME_BAND}(" in texts
    assert "비가동대수에 넣었습니다" not in texts
    assert "③ 비가동대수에 넣었습니다(⑤ 첫 줄" in _manual_mark_help(app)
    clear_equipment_repository()


def test_process_capa_detail_points_to_the_downtime_section_when_there_are_no_units(
    tmp_path: Path,
) -> None:
    """호기 일정이 없는 공정(기존보유만)은 ④ · ⑤ 가 서지 않아 입력 줄이 ③ 끝에 선다 — 닫는 알림도
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
    assert "월별 비가동대수(입력)" in _label_texts(app)
    mark_help = _manual_mark_help(app)
    assert "③ 비가동대수에 넣었습니다(③ 끝 줄" in mark_help
    assert "⑤ 첫 줄" not in mark_help
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
    # 자리에는 그리지 않는다 — 합 대수 띠(「입력 비가동 반영(n칸 · 합 x대)」)는 상태 알림 짧은 글,
    # 출처 설명은 그 전문이다(설계 규칙 UI-NTF-02 · UI-TXT-07).
    assert MANUAL_DOWNTIME_BAND not in captions
    assert "가용설비 현황 › Preference 의 공정 × 달 비가동" in MANUAL_NOTICE_HELP
    assert "가용설비 현황 › Preference 의 공정 × 달 비가동" not in captions
    note = active_state(app, "RS-05")
    assert note is not None and note["short"].startswith(f"{MANUAL_DOWNTIME_BAND}(")
    # 고칠 입력은 가용설비 현황 › Preference 에 있다 — 짧은 글이 그 자리를 말하고 줄의 「그
    # 화면으로」 가 그 탭을 열며, 전문 첫머리가 이 화면의 일임을 말한다(설계 규칙 UI-NTF-02 ·
    # UI-NTF-06).
    assert note["short"].endswith("— 가용설비 현황 › Preference")
    assert (note["page"], note["href"], note.get("tab")) == (
        tab_label(AVAILABLE_EQUIPMENT_STATUS),
        AVAILABLE_EQUIPMENT_STATUS.href,
        "Preference",
    )
    assert note["full"].startswith(f"필요 단축 일정 — {MANUAL_DOWNTIME_BAND}(")
    assert MANUAL_NOTICE_HELP in note["full"]

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


def test_constraint_simulation_raises_the_entered_downtime_as_a_state_alert(
    tmp_path: Path,
) -> None:
    """입력 비가동을 뺀 계획이면 상태 알림 `CS-05` 가 선다 — 짧은 글은 합 대수 띠(「입력 비가동
    반영(n칸 · 합 x대)」)와 고칠 자리, 전문 첫머리는 이 화면 · 공정이고 줄의 「그 화면으로」 는
    가용설비 현황 › Preference 다. 머리 줄 · 본문에는 서지 않는다(2026-11-10 보드 Q-4 — 필요 단축
    일정 `RS-05` 와 같은 꼴, 설계 규칙 UI-NTF-02). 칸이 없으면 「해소」(`active` 거짓)다."""
    from capa_simulation.components.constraint_equipment_plan import MANUAL_DOWNTIME_HELP

    databases = (tmp_path / "scenario.duckdb", _equipment_database(tmp_path / "equipment.duckdb"))
    before = constraint_opened(databases)
    assert MANUAL_DOWNTIME_BAND not in constraint_captions(before)
    assert active_state(before, "CS-05") is None
    assert [note["active"] for note in states(before, "CS-05")] == [False]

    _seed(databases[1], DYNAMIC_PROCESS, WIDE_MONTHS, 0.5)
    app = constraint_opened(databases)
    assert MANUAL_DOWNTIME_BAND not in _texts(app)
    note = active_state(app, "CS-05")
    assert note is not None
    assert note["short"].startswith(f"{MANUAL_DOWNTIME_BAND}(")
    assert note["short"].endswith("— 가용설비 현황 › Preference")
    # 모든 달 가용 12 라 넘친 칸은 없다.
    assert "가용 넘침" not in note["short"]
    assert note["full"].startswith(f"제약 시뮬레이션 · {DYNAMIC_PROCESS} — {MANUAL_DOWNTIME_BAND}(")
    assert MANUAL_DOWNTIME_HELP in note["full"]
    assert (note["page"], note["href"], note.get("tab")) == (
        tab_label(AVAILABLE_EQUIPMENT_STATUS),
        AVAILABLE_EQUIPMENT_STATUS.href,
        "Preference",
    )
    assert "가용 = 설비 일정 기준" not in constraint_captions(app)
    clear_equipment_repository()


def test_a_stopped_constraint_screen_closes_the_entered_downtime_alert(tmp_path: Path) -> None:
    """설비 일정이 서지 않아 계획 앞에서 멈춘 회차는 입력 비가동 알림 `CS-05` 를 「해소」(`active`
    거짓 하나)로 낸다 — 두 모드가 `render_equipment_plan` 바로 뒤 한 자리에서 부르고 계획이 없으면
    조건도 없다(필요 단축 일정 `RS-05` 의 멈춘 회차 꼴)."""
    from test_constraint_simulation_page import OTHER_PROCESS

    databases = (tmp_path / "scenario.duckdb", _equipment_database(tmp_path / "equipment.duckdb"))
    _seed(databases[1], DYNAMIC_PROCESS, WIDE_MONTHS, 0.5)
    _seed(databases[1], OTHER_PROCESS, WIDE_MONTHS, 0.5)
    app = constraint_opened(databases, OTHER_PROCESS)
    assert data_error_marks(app) == 1 and not app.metric
    assert [note["active"] for note in states(app, "CS-05")] == [False]
    clear_equipment_repository()


@pytest.mark.parametrize("mode", ["constraint", "schedule"])
def test_a_screen_without_a_process_closes_the_entered_downtime_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """조회기간에 확보율을 낼 공정이 없어 계획 앞에서 멈춘 회차도 두 모드가 `CS-05` 를 낸다(`active`
    거짓 — 공정이 빈 범위라 앞 회차 줄은 알림 칸이 「범위 바뀜」 으로 닫는다). 그 회차에 표지가
    오지 않으면 앞 줄이 「지금도 있음」 으로 남는다."""
    databases = (tmp_path / "scenario.duckdb", _equipment_database(tmp_path / "equipment.duckdb"))
    _seed(databases[1], DYNAMIC_PROCESS, WIDE_MONTHS, 0.5)
    app = constraint_opened(databases) if mode == "constraint" else schedule_opened(databases)
    opened = active_state(app, "CS-05")
    assert opened is not None

    real = page_bootstrap.process_page_inputs
    monkeypatch.setattr(
        page_bootstrap,
        "process_page_inputs",
        lambda path: replace(real(path), process_options=[]),
    )
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert "조회기간에 확보율을 낼 공정이 없습니다." in constraint_captions(app)
    (note,) = states(app, "CS-05")
    assert note["active"] is False and note["scope"] != opened["scope"]
    clear_equipment_repository()


def test_the_schedule_mode_raises_the_same_entered_downtime_alert(tmp_path: Path) -> None:
    """「개조 일정」 모드도 같은 함수 · 같은 범위 · 같은 내용으로 `CS-05` 를 낸다 — 모드를 바꿔도
    같은 알림이라 다시 뜨지 않는다. 출처 띠 끝에는 「입력 비가동 반영(…)」 이 없다(2026-11-09
    보드 c-schedule-head · 2026-11-10 보드 Q-4)."""
    databases = (tmp_path / "scenario.duckdb", _equipment_database(tmp_path / "equipment.duckdb"))
    _seed(databases[1], DYNAMIC_PROCESS, WIDE_MONTHS, 0.5)
    impact = constraint_opened(databases)
    schedule = schedule_opened(databases)
    assert MANUAL_DOWNTIME_BAND not in _texts(schedule)
    first, second = active_state(impact, "CS-05"), active_state(schedule, "CS-05")
    assert first is not None and second is not None
    assert (second["scope"], second["fp"], second["short"], second["full"]) == (
        first["scope"],
        first["fp"],
        first["short"],
        first["full"],
    )
    clear_equipment_repository()


def test_the_overdrawn_places_sit_in_the_alert_full_text_not_on_the_short_line() -> None:
    """0 에서 멈춘 칸은 짧은 글 꼬리 「· 가용 넘침 k칸」 하나로 말하고, 그 자리(공정 · 달 — 내역)는
    상태 알림 전문에 둔다 — 짧은 글에 ⚠ 자리 목록을 늘어놓지 않는다(설계 규칙 UI-TXT-04 ·
    UI-NTF-06). 합 대수 띠는 알림 짧은 글이다."""
    from types import SimpleNamespace
    from typing import Any, cast

    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.components.required_shortening_panel import _manual_note
    from capa_simulation.services.manual_downtime import apply_manual_downtime

    available = pd.DataFrame(
        [(202607, "DEMO-A", 3.0), (202608, "DEMO-A", 0.8)],
        columns=["생산계획년월", "공정", "가용대수"],
    )
    _, effect = apply_manual_downtime(
        available, (("DEMO-A", 202607, 1.25), ("DEMO-A", 202608, 1.5))
    )
    plan = cast(Any, SimpleNamespace(manual_downtime=effect))
    note = _manual_note(plan, scope=["DEMO-A"], labels=ProcessLabels())

    assert note is not None
    assert "⚠" not in note.text and "0 에서 멈춤" not in note.text
    assert MANUAL_NOTICE_HELP in note.full
    places = "가용 넘침(그 달 가용보다 커 0 에서 멈춘 칸): DEMO\\-A 26.08."
    assert places in note.full and places not in note.text
    # 짧은 글은 합 대수 띠와 고칠 자리다(설계 규칙 UI-NTF-06).
    assert note.text == (
        f"{MANUAL_DOWNTIME_BAND}(2칸 · 합 2.75대 · 가용 넘침 1칸) — 가용설비 현황 › Preference"
    )
