# Purpose: Space 도면 호기의 경계 날짜와 기준일 판정이 브라우저의 글자 비교 판정과 같은지 검사한다.

"""브라우저(`space_layout_editor_assets/editor.js` 의 `unitState`)는 경계 날짜를 `YYYY-MM-DD` 글자로
받아 기준일(T)과 **글자 비교**로 판정한다. AppTest 는 그 JS 를 돌리지 못하므로 같은 비교식을 여기
`_browser_state` 로 옮겨 적고, T 를 경계일 앞뒤로 훑으며 파이썬 판정(`unit_states_at`)과 대조한다.
JS 의 식이 바뀌면 `test_the_browser_state_function_is_the_one_mirrored_here` 가 먼저 깨진다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from capa_simulation.components import space_layout_editor
from capa_simulation.services.equipment_availability import build_space_equipment_status
from capa_simulation.services.equipment_contract import (
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    LAYOUT_EXITED_COLUMN,
    LAYOUT_REFLECTED_COLUMN,
)
from capa_simulation.services.space_unit_state import (
    DELAYED_STATE,
    EXIT_PLANNED_STATE,
    FLAG_STATE,
    OFFLINE_STATE,
    REAL_FROM_START,
    REAL_STATE,
    STOPPED_STATE,
    STORAGE_STATE,
    VISIBLE_STATE,
    as_of_range,
    boundary_payload,
    clamp_as_of,
    drawn_in_range,
    unit_boundaries,
    unit_states_at,
)

TODAY = date(2026, 10, 16)
JS = (space_layout_editor._ASSETS / "editor.js").read_text(encoding="utf-8")


def _row(name: str, **values: object) -> dict[str, object]:
    """검증을 지나는 설비 마스터 한 행(신규 호기 — 반입·Qual 일정과 Qual상태가 있다)."""
    row: dict[str, object] = {column: None for column in EQUIPMENT_COLUMNS}
    row.update(
        {
            "설비명": name,
            "공정대분류": "B/N",
            "공정소분류": "P",
            "공정구분": "PKG",
            "투자구분": "양산",
            "사용기준": "HBM",
            "동": "C1",
            "층": "1F",
            "X좌표": 1,
            "Y좌표": 1,
            "Xsize": 2,
            "Ysize": 2,
            "반입일정": "2026-01-05",
            "Qual일정": "2026-01-20",
            "Qual상태": "완료",
            "보관유무": "N",
            "기존설비여부": "N",
            "레이아웃표시": "Y",
        }
    )
    row.update(values)
    return row


def _existing(name: str, **values: object) -> dict[str, object]:
    blank: dict[str, object] = {
        "반입일정": None,
        "Qual일정": None,
        "Qual상태": None,
        "기존설비여부": "Y",
    }
    return _row(name, **{**blank, **values})


def _fleet() -> tuple[pd.DataFrame, pd.DataFrame]:
    """경계 날짜의 경우를 한 벌씩 — 실적·지연·일정·처음부터·없음, 정지·반출/이설, 지연 구간, 비가동,
    미확인."""
    rows = [
        _row("ACTUAL", 반입실적="2026-01-07", 반입상태="완료"),
        _row("FUTURE", 반입일정="2026-11-01", Qual일정="2026-11-20", Qual상태="계획"),
        _row(
            "LATE_IN",
            반입일정="2026-09-01",
            반입상태="지연",
            Qual일정="2026-12-01",
            Qual상태="계획",
        ),
        _existing("EXISTING"),
        _row("STORED", 반입일정=None, Qual일정=None, Qual상태=None, 보관유무="Y"),
        _existing("STOP_EXIT", 정지일정="2026-11-01", **{"반출/이설일정": "2027-02-01"}),
        _existing("STOP_ONLY", 정지일정="2026-12-15"),
        _existing("EXIT_ONLY", **{"반출/이설일정": "2026-09-30"}),
        _existing("SAME_DAY", 정지일정="2026-11-10", **{"반출/이설일정": "2026-11-10"}),
        _row("LATE_QUAL", Qual일정="2026-08-01", Qual상태="지연", Qual실적="2026-10-10"),
        _row("LATE_QUAL_OPEN", Qual일정="2026-12-01", Qual상태="지연"),
        _row(
            "UNCONFIRMED",
            반입일정="2026-09-15",
            반입상태="확정",
            Qual일정="2026-12-01",
            Qual상태="계획",
        ),
        _existing("EXISTING_LATER", 반입일정="2027-01-10"),
    ]
    downtime = pd.DataFrame(
        [
            {
                "설비명": "ACTUAL",
                "비가동유형": "고장",
                "시작일": "2026-10-01",
                "종료일": "2026-10-05",
            },
            {"설비명": "STOP_EXIT", "비가동유형": "PM", "시작일": "2026-10-20", "종료일": None},
        ],
        columns=list(DOWNTIME_COLUMNS),
    )
    return pd.DataFrame(rows, columns=list(EQUIPMENT_COLUMNS)), downtime


def _browser_state(item: dict[str, Any], moment: str) -> dict[str, bool]:
    """`editor.js` 의 `unitState` 를 그대로 옮긴 글자 비교 판정."""
    exit_on = item["exitOn"]
    real_from = item["realFrom"]
    stop_on = item["stopOn"]
    return {
        VISIBLE_STATE: exit_on is None or moment < exit_on,
        REAL_STATE: real_from is not None and real_from <= moment,
        EXIT_PLANNED_STATE: exit_on is not None and moment < exit_on,
        STOPPED_STATE: stop_on is not None and exit_on is not None and stop_on <= moment < exit_on,
        DELAYED_STATE: any(
            start <= moment and (until is None or moment < until) for start, until in item["delays"]
        ),
        OFFLINE_STATE: any(
            start <= moment and (until is None or moment <= until)
            for start, until in item["offline"]
        ),
        STORAGE_STATE: item["storage"],
        FLAG_STATE: item["flag"],
    }


def _moments(payload: list[dict[str, Any]]) -> list[date]:
    """경계 날짜마다 앞날·그날·다음날, 그리고 오늘 앞뒤와 먼 과거·미래."""
    days = {TODAY, date(2020, 1, 1), date(2030, 12, 31)}
    for item in payload:
        found = [item["realFrom"], item["exitOn"], item["stopOn"]]
        found += [day for span in item["delays"] + item["offline"] for day in span]
        days |= {date.fromisoformat(day) for day in found if day and day != REAL_FROM_START}
    return sorted({day + timedelta(days=step) for day in days for step in (-1, 0, 1)})


def test_the_browser_state_function_is_the_one_mirrored_here() -> None:
    """`_browser_state` 는 JS 의 식을 옮긴 것이다 — JS 쪽 식이 바뀌면 여기를 함께 고친다."""
    body = JS[JS.index("function unitState(item, T) {") : JS.index("function unitColors(")]
    for expression in (
        "visible: exitOn === null || T < exitOn,",
        "real: realFrom !== null && realFrom <= T,",
        "exitPlan: exitOn !== null && T < exitOn,",
        "stopped: stopOn !== null && exitOn !== null && stopOn <= T && T < exitOn,",
        "delay: (item.delays || []).some(([from, until]) => "
        "from <= T && (until === null || T < until)),",
        "offline: (item.offline || []).some(([from, until]) => "
        "from <= T && (until === null || T <= until)),",
    ):
        assert expression in body, expression


def test_the_browser_and_python_judge_every_as_of_date_alike() -> None:
    """T 를 모든 경계일 앞뒤로 훑어 브라우저의 글자 비교와 파이썬 판정이 같은지 본다. 도면에
    보이는가는 상태 판정의 `도면이탈여부` 와도 같다(같은 규칙 — 반출/이설일정, 없으면
    정지일정)."""
    equipment, downtime = _fleet()
    status = build_space_equipment_status(equipment, downtime, as_of=TODAY)
    boundaries = unit_boundaries(status, downtime, today=TODAY)
    payload = boundary_payload(boundaries)
    names = status["설비명"].tolist()

    for moment in _moments(payload):
        python = unit_states_at(boundaries, as_of=moment)
        exited = build_space_equipment_status(equipment, downtime, as_of=moment)[
            LAYOUT_EXITED_COLUMN
        ]
        for position, (name, item) in enumerate(zip(names, payload, strict=True)):
            browser = _browser_state(item, moment.isoformat())
            assert browser == python.iloc[position].to_dict(), (name, moment)
            assert browser[VISIBLE_STATE] == (not bool(exited.iloc[position])), (name, moment)


def test_the_boundary_dates_follow_the_decided_rules() -> None:
    """실물시작일 = 반입실적 → (반입 지연이면 없음) → 반입일정 → (날짜 없으면 기존·보관 처음부터,
    신규 없음). 도면이탈일 = 반출/이설 → 정지. 정지일은 둘 다 있을 때만. 지연은 [min(일정, 오늘),
    실적). 미확인은 오늘 기준(계획·확정 + 실적 공백 + 일정 < 오늘)."""
    equipment, downtime = _fleet()
    status = build_space_equipment_status(equipment, downtime, as_of=TODAY)
    payload = boundary_payload(unit_boundaries(status, downtime, today=TODAY))
    by_name = dict(zip(status["설비명"], payload, strict=True))

    assert by_name["ACTUAL"]["realFrom"] == "2026-01-07"
    assert by_name["FUTURE"]["realFrom"] == "2026-11-01"
    assert by_name["LATE_IN"]["realFrom"] is None
    assert by_name["LATE_IN"]["delays"] == [["2026-09-01", None]]
    assert by_name["EXISTING"]["realFrom"] == by_name["STORED"]["realFrom"] == REAL_FROM_START
    assert by_name["EXISTING_LATER"]["realFrom"] == "2027-01-10"  # 날짜가 있으면 날짜가 이긴다
    assert (by_name["STOP_EXIT"]["stopOn"], by_name["STOP_EXIT"]["exitOn"]) == (
        "2026-11-01",
        "2027-02-01",
    )
    assert (by_name["STOP_ONLY"]["stopOn"], by_name["STOP_ONLY"]["exitOn"]) == (None, "2026-12-15")
    assert by_name["EXIT_ONLY"]["exitOn"] == "2026-09-30"
    assert by_name["LATE_QUAL"]["delays"] == [["2026-08-01", "2026-10-10"]]
    assert by_name["LATE_QUAL_OPEN"]["delays"] == [["2026-10-16", None]]  # 일정이 뒤면 오늘부터
    assert by_name["ACTUAL"]["offline"] == [["2026-10-01", "2026-10-05"]]
    assert by_name["STOP_EXIT"]["offline"] == [["2026-10-20", None]]
    assert {name for name, item in by_name.items() if item["flag"]} == {"UNCONFIRMED"}
    assert by_name["STORED"]["storage"] is True


def test_an_old_revision_without_the_new_columns_reads_schedules_only() -> None:
    """옛 리비전·검증 전 편집본에는 실적·반입상태 칸이 없다 — 빈 칸으로 보고 일정으로 판정한다."""
    old = pd.DataFrame(
        [
            {
                "설비명": "OLD",
                "반입일정": "2026-11-01",
                "Qual일정": None,
                "정지일정": None,
                "반출/이설일정": None,
                "보관유무": "N",
                "기존설비여부": "N",
            }
        ]
    )
    boundaries = unit_boundaries(old, pd.DataFrame(), today=TODAY)

    assert boundary_payload(boundaries)[0]["realFrom"] == "2026-11-01"
    assert not unit_states_at(boundaries, as_of=TODAY).loc[0, REAL_STATE]


@pytest.mark.parametrize("moment", ["2026-10-16", "1999-01-01", "9999-12-31"])
def test_the_start_sentinel_precedes_every_date_text(moment: str) -> None:
    """「처음부터 실물」은 어느 날짜 글자보다 앞서 글자 비교로 늘 실물이다."""
    assert moment >= REAL_FROM_START


# ---------------------------------------------------------------- 기준일 페이더의 범위·그리는 목록


def test_the_fader_range_is_twelve_calendar_months_either_side_of_today() -> None:
    """페이더는 오늘 −12개월 ~ +12개월(양 끝 포함, 달력 달). 그 날이 없는 달이면 그달 말일이다."""
    assert as_of_range(TODAY) == (date(2025, 10, 16), date(2027, 10, 16))
    assert as_of_range(date(2028, 2, 29)) == (date(2027, 2, 28), date(2029, 2, 28))
    assert as_of_range(date(2026, 3, 31)) == (date(2025, 3, 31), date(2027, 3, 31))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2026, 11, 1), date(2026, 11, 1)),
        (date(2024, 1, 1), date(2025, 10, 16)),  # 날이 지나 범위를 벗어남 — 가까운 끝
        (date(2030, 1, 1), date(2027, 10, 16)),
        ("2026-12-01", date(2026, 12, 1)),
        ("2026-02-30", TODAY),  # 없는 날
        (None, TODAY),  # 페이더를 건드리지 않은 세션
        (datetime(2026, 11, 2, 13, 0), date(2026, 11, 2)),
        (pd.Timestamp("2026-11-03"), date(2026, 11, 3)),
        (pd.NaT, TODAY),
        (20261101, TODAY),
    ],
)
def test_a_session_date_is_clamped_into_the_fader_range(value: object, expected: date) -> None:
    assert clamp_as_of(value, TODAY) == expected


def test_the_drawn_roster_is_every_unit_the_fader_range_can_show() -> None:
    """층 도면이 그리는 목록(`drawn_in_range`)은 범위 안 **어느** 기준일에 도면에 서는 호기(레이아웃
    표시 Y · 좌표 · T < 도면이탈일)를 모두 품고, 목록 밖 호기는 범위 어디에서도 서지 않는다 — 끄는
    동안 목록(epoch)을 바꿀 일이 없다. 도면이탈일이 범위 시작 그날이거나 그 앞이면 빠진다."""
    equipment, downtime = _fleet()
    extra = [
        _existing("GONE_LONG_AGO", **{"반출/이설일정": "2025-06-01"}),
        _existing("GONE_AT_START", **{"반출/이설일정": "2025-10-16"}),
        _existing("GONE_AFTER_START", **{"반출/이설일정": "2025-10-17"}),
        _existing("NOT_SHOWN", 레이아웃표시="N"),
        _existing("NO_PLACE", X좌표=None, Y좌표=None, Xsize=None, Ysize=None),
    ]
    equipment = pd.concat(
        [equipment, pd.DataFrame(extra, columns=list(EQUIPMENT_COLUMNS))], ignore_index=True
    )
    status = build_space_equipment_status(equipment, downtime, as_of=TODAY)
    boundaries = unit_boundaries(status, downtime, today=TODAY)
    start, end = as_of_range(TODAY)
    roster = drawn_in_range(status, boundaries, start=start)
    names = set(status.loc[roster, "설비명"])

    assert {"GONE_AFTER_START", "EXIT_ONLY", "STOP_ONLY", "STOP_EXIT", "FUTURE"} <= names
    assert not names & {"GONE_LONG_AGO", "GONE_AT_START", "NOT_SHOWN", "NO_PLACE"}
    placed = status[["X좌표", "Y좌표", "Xsize", "Ysize"]].notna().all(axis=1)
    moments = {start, end, TODAY} | {
        day for day in _moments(boundary_payload(boundaries)) if start <= day <= end
    }
    shown_somewhere = pd.Series(False, index=status.index)
    for moment in sorted(moments):
        located = (
            build_space_equipment_status(equipment, downtime, as_of=moment)[LAYOUT_REFLECTED_COLUMN]
            .fillna(False)
            .astype(bool)
            & placed
        )
        assert not (located & ~roster).any(), moment
        shown_somewhere |= located
    # 목록은 꽉 맞는다 — 범위 안에서 한 번도 서지 않는 호기는 목록에 없다.
    assert shown_somewhere.equals(roster)
