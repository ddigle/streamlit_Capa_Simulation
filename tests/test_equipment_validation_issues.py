# Purpose: 설비 마스터 규칙 표를 저장 거부·칸 결과·칸 다듬기가 같은 규칙·문구로 보는지 검증한다.

"""설비 마스터 규칙 표(`equipment_validation.MASTER_RULES`)의 세 쓰임.

- `prepare_equipment_master` — 처음 걸린 규칙 하나를 지금까지와 같은 문구·예외 형으로 던진다.
- `equipment_master_issues` — 같은 표를 끝까지 보며 칸마다 결과를 낸다. 처음 막는 결과의 규칙이
  저장이 던지는 규칙이고, 그 문구는 저장 거부 문구의 앞머리다.
- `coerce_master_cell` — 칸 하나를 저장 정규화와 같은 함수로 다듬는다.

거부 문구는 **글자 그대로** 시험에 적는다(규칙 상수에서 가져오지 않는다) — 상수를 바꾸면 칸 문구와
거부 문구가 함께 바뀌어 둘을 견주는 시험으로는 잡히지 않는다.

표본은 합성 fleet(`sample_equipment_master`)이다 — 줄 수·공정 이름을 계약으로 보지 않고, 깨뜨릴 줄은
표본 값에서 골라 쓴다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
import pytest

from capa_simulation.services.equipment_csv import merge_equipment_rows, read_equipment_update
from capa_simulation.services.equipment_samples import sample_equipment_master
from capa_simulation.services.equipment_units import module_group_warnings
from capa_simulation.services.equipment_validation import (
    MASTER_RULES,
    CellParseError,
    MasterIssue,
    UnitGroupCollisionError,
    area_code_warnings,
    coerce_master_cell,
    equipment_master_issues,
    prepare_equipment_master,
)
from capa_simulation.services.floor_layout_profile import FloorCanvasMap

ANCHOR = date(2026, 10, 1)


def _master() -> pd.DataFrame:
    """합성 표본 fleet 앞 12대를 입력 꼴(object)로 — 그대로는 규칙을 하나도 어기지 않는다."""
    frame = sample_equipment_master(anchor_date=ANCHOR).head(12).astype(object)
    return frame.reset_index(drop=True)


def _modules() -> pd.DataFrame:
    """앞 두 줄을 한 설비(Main 설비 GRP-1)의 모듈 행으로 묶은 표본."""
    frame = _master()
    frame.loc[1, "공정소분류"] = frame.loc[0, "공정소분류"]
    frame.loc[[0, 1], "Main 설비"] = "GRP-1"
    frame.loc[[0, 1], "환산비"] = 0.5
    return frame


def _blocking(issues: tuple[MasterIssue, ...]) -> list[MasterIssue]:
    return [issue for issue in issues if issue.blocking]


def _ordinary_with_dates(frame: pd.DataFrame) -> int:
    """제진대·물류·반입·Qual 일정이 다 있는 신규 호기(보관·기존설비 아님) 첫 줄."""
    ordinary = frame["보관유무"].eq("N") & frame["기존설비여부"].eq("N")
    dated = frame.loc[:, ["제진대일정", "물류일정", "반입일정", "Qual일정"]].notna().all(axis=1)
    exits = frame.loc[:, ["정지일정", "반출/이설일정"]].isna().all(axis=1)
    return int(frame.index[ordinary & dated & exits][0])


def _days(frame: pd.DataFrame, row: int, column: str, days: int) -> pd.Timestamp:
    value: Any = frame.at[row, column]
    return pd.Timestamp(value) + pd.Timedelta(days=days)


# ------------------------------------------------------------------ 규칙 표


def test_the_rule_table_keeps_its_order_and_warnings_last() -> None:
    codes = [rule.code for rule in MASTER_RULES]

    assert codes == [
        "required_text",
        "duplicate_unit",
        "unit_group_collision",
        "unit_group_mixed",
        "flag",
        "number_unreadable",
        "location_range",
        "position_pair",
        "size_pair",
        "position_needs_size",
        "layout_needs_location",
        "position_negative",
        "size_not_positive",
        "canvas_outside",
        "ratio_unreadable",
        "ratio_not_positive",
        "date_unreadable",
        "qual_status_required",
        "status_value",
        "schedule_order",
        "exit_without_arrival",
        "stop_after_exit",
        "exit_before_arrival",
        "actual_future",
        "actual_reversed",
        "area_code_unknown",
        "unit_case_variant",
        "module_ratio_default",
    ]
    blocking = [rule.blocking for rule in MASTER_RULES]
    # 막지 않는 경고는 끝에 모인다 — 저장 함수가 보는 막는 규칙의 차례가 흐트러지지 않는다.
    assert blocking == sorted(blocking, reverse=True)


def test_an_untouched_sample_has_no_issue_and_is_not_changed() -> None:
    for frame in (_master(), _modules()):
        before = frame.copy()

        assert equipment_master_issues(frame, today=ANCHOR) == ()
        prepare_equipment_master(frame, today=ANCHOR)

        # 넘긴 표는 그대로다 — 다듬기는 늘 사본에서 한다.
        pd.testing.assert_frame_equal(frame, before)


# ------------------------------------------------------------------ 규칙마다 한 군데씩


_Cells = list[tuple[int, str]]
_Text = Callable[[pd.DataFrame, _Cells], str]


def _units(head: str) -> _Text:
    """「{head}: [그 줄들의 설비명]」 — 예시는 앞뒤 공백을 뗀 설비명(겹친 이름은 한 번)이다."""

    def text(frame: pd.DataFrame, cells: _Cells) -> str:
        names: list[str] = []
        for row, _ in cells:
            name = str(frame.at[row, "설비명"]).strip()
            if name not in names:
                names.append(name)
        return f"{head}: {names}"

    return text


def _entered(head: str) -> _Text:
    """「{head}: [입력 값]」 — 날짜 예시는 설비명이 아니라 그 칸에 친 값 그대로다."""

    def text(frame: pd.DataFrame, cells: _Cells) -> str:
        return f"{head}: {[frame.at[row, column] for row, column in cells]}"

    return text


def _exact(value: str) -> _Text:
    return lambda frame, cells: value


def _collision_text(frame: pd.DataFrame, cells: _Cells) -> str:
    modules = ", ".join(str(frame.at[row, "설비명"]) for row, column in cells if column != "설비명")
    return (
        "Main 설비는 다른 행의 설비명과 같을 수 없습니다 — 설비 행과 그 설비를 Main 설비로 적은 "
        "모듈 행을 함께 두면 같은 설비가 두 번 세어집니다: "
        f"설비 행 GRP-1 · 모듈 행 {modules}. 한쪽만 남기세요 — "
        "모듈로 나눠 세려면 설비 행을, 한 대로 세려면 모듈 행을 지우거나 "
        "그 행의 Main 설비를 비웁니다."
    )


def _canvas_text(frame: pd.DataFrame, cells: _Cells) -> str:
    on_floor = frame["동"].eq("C1") & frame["층"].eq("1F")
    right = (frame["X좌표"].astype(float) + frame["Xsize"].astype(float)).loc[on_floor].max()
    top = (frame["Y좌표"].astype(float) + frame["Ysize"].astype(float)).loc[on_floor].max()
    names = [str(frame.at[row, "설비명"]) for row, _ in cells][:5]
    return (
        "Space 블럭이 층 캔버스 범위를 벗어났습니다 — 그 동·층의 캔버스가 호기 좌표보다 좁습니다. "
        f"C1 1F 캔버스 50 × 40 — 이 층 호기를 모두 담으려면 {max(50.0, round(right, 2)):g} × "
        f"{max(40.0, round(top, 2)):g} 이상: {names}. 설비 마스터 저장은 모든 호기를 한 번에 "
        "검증하므로 그 층과 무관한 칸만 고쳐도 같은 오류로 막힙니다. Space 현황의 그 동·층 상세 "
        "레이아웃에서 「도면·캔버스 편집」으로 캔버스를 넓히거나, 가용설비 현황에서 그 호기의 "
        "X좌표·Y좌표·Xsize·Ysize 를 고치세요."
    )


@dataclass(frozen=True)
class _Broken:
    """한 규칙만 깨뜨린 표 — `break_` 가 표를 고치고 기대 (줄, 칸) 목록을 돌려준다. `text` 는 그
    표에서 저장이 던질 문구(글자 그대로)다."""

    rule: str
    break_: Callable[[pd.DataFrame], list[tuple[int, str]]]
    text: _Text
    base: Callable[[], pd.DataFrame] = _master
    error: type[Exception] = ValueError
    canvases: FloorCanvasMap | None = None
    today: date | None = None


def _set(row: int, column: str, value: Any) -> Callable[[pd.DataFrame], list[tuple[int, str]]]:
    def apply(frame: pd.DataFrame) -> list[tuple[int, str]]:
        frame.at[row, column] = value
        return [(row, column)]

    return apply


def _duplicate(frame: pd.DataFrame) -> list[tuple[int, str]]:
    frame.at[3, "설비명"] = f"  {frame.at[1, '설비명']} "
    return [(1, "설비명"), (3, "설비명")]


def _collision(frame: pd.DataFrame) -> list[tuple[int, str]]:
    frame.at[5, "설비명"] = "GRP-1"
    return [(0, "Main 설비"), (1, "Main 설비"), (5, "설비명")]


def _mixed_building(frame: pd.DataFrame) -> list[tuple[int, str]]:
    frame.at[1, "동"] = "C2"
    return [(0, "동"), (1, "동")]


def _no_position_size(frame: pd.DataFrame) -> list[tuple[int, str]]:
    frame.loc[2, ["Xsize", "Ysize"]] = None
    return [(2, "Xsize")]


def _no_building_or_floor(frame: pd.DataFrame) -> list[tuple[int, str]]:
    frame.loc[2, ["동", "층"]] = None
    return [(2, "동")]


def _outside(frame: pd.DataFrame) -> list[tuple[int, str]]:
    on_floor = frame["동"].eq("C1") & frame["층"].eq("1F")
    right = frame["X좌표"].astype(float) + frame["Xsize"].astype(float)
    top = frame["Y좌표"].astype(float) + frame["Ysize"].astype(float)
    rows = frame.index[on_floor & (right.gt(50) | top.gt(40))]
    return [(int(row), "X좌표") for row in rows]


def _logistics_before_vibration(frame: pd.DataFrame) -> list[tuple[int, str]]:
    row = _ordinary_with_dates(frame)
    frame.at[row, "물류일정"] = _days(frame, row, "제진대일정", -1)
    return [(row, "물류일정")]


def _qual_before_arrival(frame: pd.DataFrame) -> list[tuple[int, str]]:
    row = _ordinary_with_dates(frame)
    frame.at[row, "Qual일정"] = _days(frame, row, "반입일정", -1)
    return [(row, "Qual일정")]


def _present_chain(frame: pd.DataFrame) -> list[tuple[int, str]]:
    # 반입이 빈 신규 호기도 있는 날짜끼리 차례를 본다 — 물류 ≤ Qual.
    row = _ordinary_with_dates(frame)
    frame.at[row, "반입일정"] = None
    frame.at[row, "Qual일정"] = _days(frame, row, "물류일정", -1)
    return [(row, "Qual일정")]


def _exit_without_arrival(frame: pd.DataFrame) -> list[tuple[int, str]]:
    row = _ordinary_with_dates(frame)
    frame.loc[row, ["반입일정", "Qual일정", "Qual상태"]] = None
    frame.at[row, "반출/이설일정"] = "2027-01-01"
    return [(row, "반출/이설일정")]


def _stop_after_exit(frame: pd.DataFrame) -> list[tuple[int, str]]:
    row = _ordinary_with_dates(frame)
    frame.at[row, "정지일정"] = "2027-02-01"
    frame.at[row, "반출/이설일정"] = "2027-01-01"
    return [(row, "정지일정")]


def _exit_before_arrival(frame: pd.DataFrame) -> list[tuple[int, str]]:
    row = _ordinary_with_dates(frame)
    frame.at[row, "정지일정"] = _days(frame, row, "반입일정", -1)
    return [(row, "정지일정")]


def _actuals_reversed(frame: pd.DataFrame) -> list[tuple[int, str]]:
    frame.at[0, "반입실적"] = "2026-06-05"
    frame.at[0, "Qual실적"] = "2026-06-01"
    return [(0, "반입실적")]


_ORDER = "제진대·물류·반입·Qual 일정 순서가 올바르지 않습니다"

BROKEN = {
    "공정소분류 빈 글": _Broken(
        "required_text",
        _set(2, "공정소분류", " "),
        _exact("설비 마스터의 공정소분류에 누락값이 있습니다."),
    ),
    "설비명 중복(앞뒤 공백)": _Broken(
        "duplicate_unit", _duplicate, _units("설비명은 중복될 수 없습니다")
    ),
    "Main 설비 = 다른 행 설비명": _Broken(
        "unit_group_collision", _collision, _collision_text, _modules, UnitGroupCollisionError
    ),
    "모듈 행 동이 갈림": _Broken(
        "unit_group_mixed",
        _mixed_building,
        _exact("같은 Main 설비의 모듈 행은 동이 같아야 합니다: ['GRP-1']"),
        _modules,
    ),
    "Y/N 밖": _Broken(
        "flag", _set(4, "레이아웃표시", "X"), _units("레이아웃표시는 Y 또는 N이어야 합니다")
    ),
    "Y/N 빈 칸": _Broken(
        "flag", _set(4, "보관유무", ""), _units("보관유무는 Y 또는 N이어야 합니다")
    ),
    "좌표 못 읽음": _Broken(
        "number_unreadable", _set(2, "Y좌표", "12m"), _units("Y좌표를 숫자로 읽을 수 없습니다")
    ),
    "크기 천 단위 쉼표": _Broken(
        "number_unreadable", _set(2, "Xsize", "1,2"), _units("Xsize를 숫자로 읽을 수 없습니다")
    ),
    "층 범위 밖": _Broken(
        "location_range",
        _set(3, "층", "7F"),
        _units("동은 C1~C5, 층은 1F~6F 범위여야 합니다"),
    ),
    "좌표 한쪽만": _Broken(
        "position_pair",
        _set(2, "X좌표", None),
        _units("X좌표·Y좌표는 함께 넣거나 함께 비워야 합니다"),
    ),
    "크기 한쪽만": _Broken(
        "size_pair", _set(2, "Ysize", ""), _units("Xsize·Ysize는 함께 넣거나 함께 비워야 합니다")
    ),
    "좌표만 있고 크기 없음": _Broken(
        "position_needs_size",
        _no_position_size,
        _units("Space 좌표(X좌표·Y좌표)가 있으면 Xsize·Ysize 도 넣어야 합니다"),
    ),
    "레이아웃 Y 인데 동·층 없음": _Broken(
        "layout_needs_location",
        _no_building_or_floor,
        _units("레이아웃표시 Y 호기에 좌표를 넣으면 동·층도 넣어야 합니다"),
    ),
    "좌표 음수": _Broken(
        "position_negative",
        _set(2, "Y좌표", -1),
        _units("Space 좌표(X좌표·Y좌표)는 0 이상이어야 합니다"),
    ),
    "크기 0": _Broken(
        "size_not_positive", _set(2, "Xsize", 0), _units("Xsize·Ysize는 0 보다 커야 합니다")
    ),
    "캔버스 밖": _Broken(
        "canvas_outside", _outside, _canvas_text, canvases={("C1", "1F"): (50.0, 40.0)}
    ),
    "환산비 못 읽음": _Broken(
        "ratio_unreadable", _set(4, "환산비", "1.5배"), _units("환산비를 숫자로 읽을 수 없습니다")
    ),
    "환산비 0": _Broken(
        "ratio_not_positive", _set(4, "환산비", "0"), _units("환산비는 0보다 큰 숫자여야 합니다")
    ),
    "날짜 못 읽음": _Broken(
        "date_unreadable",
        _set(5, "물류일정", "다음 주"),
        _entered("물류일정은 날짜 형식이어야 합니다"),
    ),
    "시각 24:00": _Broken(
        "date_unreadable",
        _set(5, "Qual실적", "2026-06-01 24:00"),
        _entered("Qual실적은 날짜 형식이어야 합니다"),
    ),
    "Qual상태 없음": _Broken(
        "qual_status_required",
        _set(6, "Qual상태", None),
        _units("Qual일정이 있는 호기(보관·기존설비 제외)는 Qual상태가 필수입니다"),
    ),
    "반입상태 값 밖": _Broken(
        "status_value",
        _set(6, "반입상태", "검토중"),
        _units("반입상태는 계획·확정·완료·지연 중 하나여야 합니다"),
    ),
    "물류 < 제진대": _Broken("schedule_order", _logistics_before_vibration, _units(_ORDER)),
    "Qual < 반입": _Broken("schedule_order", _qual_before_arrival, _units(_ORDER)),
    "반입 빈 신규의 Qual < 물류": _Broken("schedule_order", _present_chain, _units(_ORDER)),
    "반입 없는 신규의 반출": _Broken(
        "exit_without_arrival",
        _exit_without_arrival,
        _units("반입일정이 없는 신규 설비에는 정지일정·반출/이설일정을 넣을 수 없습니다"),
    ),
    "정지 > 반출/이설": _Broken(
        "stop_after_exit", _stop_after_exit, _units("정지일정은 반출/이설일정보다 늦을 수 없습니다")
    ),
    "정지 < 반입": _Broken(
        "exit_before_arrival",
        _exit_before_arrival,
        _units("정지일정은 반입일정보다 빠를 수 없습니다"),
    ),
    "실적이 오늘보다 늦음": _Broken(
        "actual_future",
        _set(0, "Qual실적", "2026-12-01"),
        _units("Qual실적은 오늘(2026-10-01)보다 늦을 수 없습니다 — 실적은 이미 끝난 날을 적습니다"),
        today=ANCHOR,
    ),
    "반입실적 > Qual실적": _Broken(
        "actual_reversed",
        _actuals_reversed,
        _units("반입실적은 Qual실적보다 늦을 수 없습니다"),
        today=ANCHOR,
    ),
}


@pytest.mark.parametrize("name", list(BROKEN))
def test_each_rule_is_the_same_rule_for_saving_and_for_cells(name: str) -> None:
    case = BROKEN[name]
    frame = case.base()
    cells = case.break_(frame)
    with pytest.raises(ValueError) as caught:
        prepare_equipment_master(frame, floor_canvases=case.canvases, today=case.today)
    issues = equipment_master_issues(frame, floor_canvases=case.canvases, today=case.today)

    assert type(caught.value) is case.error
    # 거부 문구는 예전 글자 그대로다 — 앞머리와 예시(어느 줄의 무엇을, 몇 개까지)까지.
    assert str(caught.value) == case.text(frame, cells)
    blocking = _blocking(issues)
    first = blocking[0]
    # 처음 막는 결과의 규칙 = 저장이 던진 규칙이고, 그 문구가 저장 거부 문구의 앞머리다.
    assert first.rule == case.rule
    if case.rule == "canvas_outside":
        assert str(caught.value).startswith("Space 블럭이 층 캔버스 범위를 벗어났습니다")
    elif case.rule == "required_text":
        assert str(caught.value) == f"{first.message}."
    else:
        assert str(caught.value).startswith(f"{first.message}: ")
    assert [(issue.position, issue.column) for issue in blocking if issue.rule == case.rule] == (
        cells
    )
    # 뒤 규칙이 이어 걸릴 수는 있다(모으는 쪽은 못 읽은 값을 빈 칸으로 보고 이어 본다) — 앞
    # 규칙은 없다.
    order = [rule.code for rule in MASTER_RULES]
    assert all(order.index(issue.rule) >= order.index(case.rule) for issue in blocking)
    assert all(issue.unit == str(frame.at[issue.position, "설비명"]).strip() for issue in issues)


def test_the_rejection_text_is_byte_for_byte_the_old_text() -> None:
    frame = _master()
    names = frame["설비명"].tolist()
    frame.at[2, "공정소분류"] = ""
    with pytest.raises(ValueError) as missing:
        prepare_equipment_master(frame)
    assert str(missing.value) == "설비 마스터의 공정소분류에 누락값이 있습니다."

    frame = _master()
    frame.at[3, "설비명"] = names[1]
    with pytest.raises(ValueError) as duplicated:
        prepare_equipment_master(frame)
    assert str(duplicated.value) == f"설비명은 중복될 수 없습니다: ['{names[1]}']"

    frame = _master()
    frame.at[5, "물류일정"] = " 다음 주 "
    with pytest.raises(ValueError) as unreadable:
        prepare_equipment_master(frame)
    # 날짜 예시는 설비명이 아니라 입력 글자 그대로다.
    assert str(unreadable.value) == "물류일정은 날짜 형식이어야 합니다: [' 다음 주 ']"

    frame = _modules()
    frame.at[1, "동"] = "C2"
    with pytest.raises(ValueError) as mixed:
        prepare_equipment_master(frame)
    assert str(mixed.value) == "같은 Main 설비의 모듈 행은 동이 같아야 합니다: ['GRP-1']"

    # 받침 없는 칸 이름은 「가」 — 「공정소분류 이 같아야」 로 조사가 못박혀 있었다(2026-10-26 E2E).
    frame = _modules()
    frame.at[1, "공정소분류"] = "DEMO-다른공정"
    with pytest.raises(ValueError) as process:
        prepare_equipment_master(frame)
    assert str(process.value) == (
        "같은 Main 설비의 모듈 행은 공정소분류가 같아야 합니다: ['GRP-1']"
    )

    frame = _master()
    frame.at[0, "Qual실적"] = "2026-12-01"
    with pytest.raises(ValueError) as future:
        prepare_equipment_master(frame, today=ANCHOR)
    assert str(future.value) == (
        "Qual실적은 오늘(2026-10-01)보다 늦을 수 없습니다 — 실적은 이미 끝난 날을 적습니다: "
        f"['{names[0]}']"
    )


def test_a_rejection_lists_at_most_five_examples() -> None:
    names = _master()["설비명"].tolist()

    frame = _master()
    frame.loc[0:6, "레이아웃표시"] = "X"
    with pytest.raises(ValueError) as flags:
        prepare_equipment_master(frame)
    assert str(flags.value) == f"레이아웃표시는 Y 또는 N이어야 합니다: {names[:5]}"

    frame = _master()
    entered = [f"다음 주 {index}" for index in range(7)]
    frame.loc[0:6, "물류일정"] = entered
    with pytest.raises(ValueError) as dates:
        prepare_equipment_master(frame)
    assert str(dates.value) == f"물류일정은 날짜 형식이어야 합니다: {entered[:5]}"

    frame = _master()
    frame.loc[6:11, "설비명"] = names[0:6]
    with pytest.raises(ValueError) as duplicated:
        prepare_equipment_master(frame)
    # 겹친 이름은 한 번씩, 앞 다섯.
    assert str(duplicated.value) == f"설비명은 중복될 수 없습니다: {names[:5]}"

    frame = _master()
    frame["공정소분류"] = frame.at[0, "공정소분류"]
    groups = [f"GRP-{index:02d}" for index in range(6)]
    frame["Main 설비"] = [group for group in groups for _ in range(2)]
    frame["환산비"] = 0.5
    frame.loc[1::2, "동"] = frame["동"].map(lambda value: "C5" if value != "C5" else "C4")
    with pytest.raises(ValueError) as mixed:
        prepare_equipment_master(frame)
    assert str(mixed.value) == f"같은 Main 설비의 모듈 행은 동이 같아야 합니다: {groups[:5]}"


def test_within_a_rule_cells_come_column_by_column_then_row_by_row() -> None:
    frame = _master()
    frame.at[5, "보관유무"] = "X"
    frame.at[2, "레이아웃표시"] = "X"

    issues = equipment_master_issues(frame)

    # 칸 차례(보관유무 → 레이아웃표시)가 줄 차례보다 먼저다 — 저장도 그 칸에서 먼저 멈춘다.
    assert [(issue.rule, issue.position, issue.column) for issue in issues] == [
        ("flag", 5, "보관유무"),
        ("flag", 2, "레이아웃표시"),
    ]
    with pytest.raises(ValueError) as caught:
        prepare_equipment_master(frame)
    assert str(caught.value) == f"보관유무는 Y 또는 N이어야 합니다: ['{frame.at[5, '설비명']}']"


def test_canvas_cells_name_the_floor_canvas() -> None:
    frame = _master()
    canvases: FloorCanvasMap = {("C1", "1F"): (50.0, 40.0)}

    issues = equipment_master_issues(frame, floor_canvases=canvases)

    assert issues
    assert {issue.message for issue in issues} == {
        "C1 1F 캔버스 50 × 40 밖 — 캔버스를 넓히거나 좌표를 고칩니다"
    }
    # 캔버스를 넘기지 않으면 상한을 보지 않는다(다시 읽기).
    assert equipment_master_issues(frame) == ()


# ------------------------------------------------------------------ 모으기 · 조이지 않기


def test_collecting_goes_past_earlier_rules_and_reads_unreadable_values_as_blank() -> None:
    frame = _master()
    frame.at[3, "설비명"] = frame.at[1, "설비명"]
    frame.at[4, "레이아웃표시"] = "X"
    frame.at[2, "X좌표"] = "12m"
    frame.at[5, "물류일정"] = "다음 주"

    issues = equipment_master_issues(frame)

    with pytest.raises(ValueError, match="설비명은 중복될 수 없습니다"):
        prepare_equipment_master(frame)
    cells = {(issue.rule, issue.position, issue.column) for issue in issues}
    assert {
        ("duplicate_unit", 1, "설비명"),
        ("duplicate_unit", 3, "설비명"),
        ("flag", 4, "레이아웃표시"),
        ("number_unreadable", 2, "X좌표"),
        # 못 읽은 X좌표는 빈 칸으로 보고 다음 규칙을 본다 — Y좌표만 남아 짝이 깨진다.
        ("position_pair", 2, "X좌표"),
        ("date_unreadable", 5, "물류일정"),
    } <= cells
    assert [issue.rule for issue in issues][0] == "duplicate_unit"


def test_positions_are_rows_of_the_given_table() -> None:
    frame = _master()
    blank = frame.iloc[[0]].copy()
    blank.loc[:, "설비명"] = "  "
    frame = pd.concat([frame.iloc[:2], blank, frame.iloc[2:]])
    frame.index = [index * 10 for index in range(len(frame))]
    floor, name = list(frame.columns).index("층"), list(frame.columns).index("설비명")
    frame.iat[5, floor] = "9F"

    issues = equipment_master_issues(frame)

    # 설비명이 빈 셋째 줄은 조용히 빠지지만 줄 자리는 넘긴 표의 `iloc` 그대로다.
    assert [(issue.position, issue.column, issue.rule) for issue in issues] == [
        (5, "층", "location_range")
    ]
    assert issues[0].unit == frame.iat[5, name]


def test_rules_that_a_reread_revision_passed_are_not_tightened() -> None:
    frame = _master()
    row = _ordinary_with_dates(frame)
    # 레이아웃표시 N 행은 동·층 없이 좌표만 있어도 받는다.
    frame.loc[2, ["레이아웃표시", "동", "층"]] = ["N", None, None]
    # 보관 호기는 이웃한 둘만 본다 — 반입이 빈 채 Qual 이 물류보다 일러도 받고, Qual상태도
    # 필수가 아니다.
    frame.loc[row, ["보관유무", "반입일정", "Qual상태"]] = ["Y", None, None]
    frame.at[row, "Qual일정"] = _days(frame, row, "물류일정", -1)
    # 실적이 오늘보다 늦어도 `today` 없이 다시 읽으면 막지 않는다.
    frame.at[0, "Qual실적"] = "2027-01-01"

    prepare_equipment_master(frame)
    assert _blocking(equipment_master_issues(frame)) == []
    rules = {issue.rule for issue in equipment_master_issues(frame, today=ANCHOR)}
    assert rules == {"actual_future"}


def _date_text(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """날짜 칸을 `YYYY-MM-DD` 글로 — 붙여넣기처럼 칸 첫 값으로 날짜 꼴을 정하게."""
    text = frame[column].map(lambda value: None if pd.isna(value) else f"{pd.Timestamp(value):%F}")
    return frame.assign(**{column: text})


def _assert_unreadable_dates(
    frame: pd.DataFrame, column: str, rows: list[int], *, today: date | None = None
) -> None:
    """시간대 붙은 그 줄들만 「날짜 형식」 으로 막는다 — 저장·칸 결과가 같은 줄, 같은 문구다."""
    entered = [frame.at[row, column] for row in rows]
    with pytest.raises(ValueError) as caught:
        prepare_equipment_master(frame, today=today)
    assert type(caught.value) is ValueError
    assert str(caught.value) == f"{column}은 날짜 형식이어야 합니다: {entered}"
    blocking = _blocking(equipment_master_issues(frame, today=today))
    assert [(issue.rule, issue.position, issue.column) for issue in blocking] == [
        ("date_unreadable", row, column) for row in rows
    ]


def test_time_zoned_dates_are_unreadable_for_saving_as_for_cells() -> None:
    # 시간대가 서로 다른 두 값 — pandas 가 칸을 날짜로 모으지 못해 예전 저장은 화면이 잡지 못하는
    # AttributeError 로 멈췄다.
    frame = _master()
    frame.at[0, "물류일정"] = "2026-05-03T00:00+09:00"
    frame.at[1, "물류일정"] = "2026-05-04T00:00+00:00"
    _assert_unreadable_dates(frame, "물류일정", [0, 1])

    # 시간대 붙은 값이 칸 첫 값 — 예전에는 칸 전체를 그 꼴로 읽어 멀쩡한 날짜들을 탓했다.
    frame = _date_text(_master(), "물류일정")
    frame.at[0, "물류일정"] = "2026-05-03T00:00+09:00"
    _assert_unreadable_dates(frame, "물류일정", [0])

    # 칸의 찬 값이 모두 시간대 꼴 — 예전 저장은 `today` 없이 그대로 받고, `today` 를 주면 영어
    # pandas 문구로 멈췄다.
    frame = _master()
    frame["Qual실적"] = None
    frame.at[0, "Qual실적"] = "2026-06-30T00:00+09:00"
    _assert_unreadable_dates(frame, "Qual실적", [0])
    _assert_unreadable_dates(frame, "Qual실적", [0], today=ANCHOR)
    assert isinstance(coerce_master_cell("Qual실적", "2026-06-30T00:00+09:00"), CellParseError)


def test_a_time_zoned_date_waits_for_the_earlier_rules() -> None:
    frame = _master()
    frame.at[0, "물류일정"] = "2026-05-24T00:00+09:00"
    frame.at[3, "설비명"] = frame.at[1, "설비명"]

    with pytest.raises(ValueError, match="설비명은 중복될 수 없습니다"):
        prepare_equipment_master(frame)
    rules = [issue.rule for issue in equipment_master_issues(frame)]
    assert rules == ["duplicate_unit", "duplicate_unit", "date_unreadable"]


def test_pasting_time_zoned_dates_names_the_cells_instead_of_crashing() -> None:
    current = _master()
    first, second = current["설비명"].tolist()[:2]
    payload = f"설비명\t물류일정\n{first}\t2026-05-03T00:00+09:00\n{second}\t2026-05-04T00:00+00:00"

    # 화면은 ValueError 를 잡아 오류 칸에 세운다(예전 AttributeError 는 Traceback 이었다).
    with pytest.raises(ValueError) as caught:
        read_equipment_update(payload, current)
    assert type(caught.value) is ValueError
    assert str(caught.value) == (
        "물류일정은 날짜 형식이어야 합니다: ['2026-05-03T00:00+09:00', '2026-05-04T00:00+00:00']"
    )


# ------------------------------------------------------------------ 경고 셋


def test_warnings_do_not_block_and_keep_their_sentences() -> None:
    frame = _master()
    names = frame["설비명"].tolist()
    frame.at[0, "Area Code"] = " 기타 "
    frame.at[1, "설비명"] = names[0].lower()

    issues = equipment_master_issues(frame)

    prepare_equipment_master(frame)
    assert [(issue.rule, issue.position, issue.column, issue.blocking) for issue in issues] == [
        ("area_code_unknown", 0, "Area Code", False),
        ("unit_case_variant", 0, "설비명", False),
        ("unit_case_variant", 1, "설비명", False),
    ]
    assert issues[0].message == "Area Code 가 Main·MI·부대 밖입니다 — 저장은 되지만 값을 확인하세요"
    assert area_code_warnings(frame) == [
        "Area Code 가 Main·MI·부대 밖인 호기 1건 — 저장은 되지만 값을 확인하세요(기타): "
        f"['{names[0]}']"
    ]


def test_the_module_ratio_warning_is_the_same_rows_as_its_sentence() -> None:
    frame = _modules()
    frame.loc[[0, 1], "환산비"] = None

    issues = equipment_master_issues(frame)

    assert [(issue.rule, issue.position, issue.column) for issue in issues] == [
        ("module_ratio_default", 0, "환산비"),
        ("module_ratio_default", 1, "환산비"),
    ]
    assert issues[0].message == (
        "Main 설비로 묶은 모듈 행의 환산비가 모두 1 입니다 — 능력이 모듈 수만큼 부풀려집니다"
    )
    assert module_group_warnings(prepare_equipment_master(frame)) == [
        "Main 설비로 묶은 모듈 행의 환산비가 모두 1 입니다 — 능력이 모듈 수만큼 부풀려집니다. "
        "모듈 행에는 1 ÷ 모듈수(4모듈이면 0.25)를 적습니다: ['GRP-1']"
    ]


def test_warnings_stand_beside_blocking_cells_as_their_sentences_do() -> None:
    # 화면의 경고 문장은 검증 전 편집본(막는 오류가 남아도)으로 선다 — 칸 결과도 같은 편집본에서
    # 같은 줄에 경고를 낸다.
    frame = _modules()
    frame.loc[[0, 1], "환산비"] = None
    frame.at[2, "Area Code"] = "기타"
    frame.at[7, "물류일정"] = "다음 주"

    issues = equipment_master_issues(frame)

    assert [(issue.rule, issue.position) for issue in _blocking(issues)] == [("date_unreadable", 7)]
    warnings = [(issue.rule, issue.position) for issue in issues if not issue.blocking]
    assert warnings == [
        ("area_code_unknown", 2),
        ("module_ratio_default", 0),
        ("module_ratio_default", 1),
    ]
    assert len(module_group_warnings(frame)) == 1
    assert len(area_code_warnings(frame)) == 1


def test_rows_that_saving_drops_or_rejects_raise_no_warning_sentence() -> None:
    # 설비명이 빈 줄은 저장이 조용히 뺀다 — 칸 결과에 없고, 문장도 그 줄을 세지 않는다.
    blank = _master().iloc[[0, 1]].copy()
    blank["설비명"] = ["", "  "]
    blank["Area Code"] = "기타"
    blank["환산비"] = None
    frame = pd.concat([_master(), blank], ignore_index=True)

    assert equipment_master_issues(frame) == ()
    assert area_code_warnings(frame) == []
    assert module_group_warnings(frame) == []

    # 설비명이 겹친 두 줄은 「설비명 중복」 이지 Main 설비로 묶은 모듈 묶음이 아니다.
    frame = _master()
    frame.at[3, "설비명"] = frame.at[1, "설비명"]
    frame.loc[[1, 3], "환산비"] = None

    assert [issue.rule for issue in equipment_master_issues(frame)] == ["duplicate_unit"] * 2
    assert module_group_warnings(frame) == []


def test_the_paste_preview_and_the_cells_name_the_same_case_variants() -> None:
    current = _master()
    existing = str(current.at[0, "설비명"])
    pasted = current.iloc[[0]].assign(설비명=existing.lower())
    payload = pasted.to_csv(sep="\t", index=False)

    paste = read_equipment_update(payload, current)
    issues = equipment_master_issues(merge_equipment_rows(current, paste.rows))

    # 미리보기는 (새 이름, 기존 이름) 짝이고, 칸 결과는 합친 표 안의 짝이다 — 같은 열쇠라 미리보기의
    # 두 이름이 모두 칸 경고를 받는다.
    assert paste.case_variants == ((existing.lower(), existing),)
    flagged = {issue.unit for issue in issues if issue.rule == "unit_case_variant"}
    assert flagged == {existing, existing.lower()}


# ------------------------------------------------------------------ 칸 다듬기


@pytest.mark.parametrize(
    ("column", "text", "expected"),
    [
        ("반입일정", "2026-05-03", pd.Timestamp("2026-05-03")),
        ("반입일정", " 2026/5/3 ", pd.Timestamp("2026-05-03")),
        ("반입일정", "2026.05.03", pd.Timestamp("2026-05-03")),
        ("반입일정", "2026-05-03 13:30", pd.Timestamp("2026-05-03")),
        ("반입일정", "2026-05-03T08:00:00", pd.Timestamp("2026-05-03")),
        ("반입일정", "", pd.NA),
        ("X좌표", " 12.5 ", 12.5),
        ("X좌표", "", pd.NA),
        ("X좌표", "inf", float("inf")),
        ("환산비", "", 1.0),
        ("환산비", "0.25", 0.25),
        ("레이아웃표시", " y ", "Y"),
        ("레이아웃표시", "", pd.NA),
        ("Area Code", " main ", "Main"),
        ("Area Code", "기타", "기타"),
        ("동", " C2 ", "C2"),
        ("층", "", pd.NA),
        ("Qual상태", " 확정 ", "확정"),
        ("설비명", "  EQ-9  ", "EQ-9"),
        ("메모1", "   ", pd.NA),
    ],
)
def test_a_cell_is_coerced_to_its_contract_value(column: str, text: str, expected: object) -> None:
    value = coerce_master_cell(column, text)

    if expected is pd.NA:
        assert value is pd.NA
    else:
        assert value == expected
        assert type(value) is type(expected)


@pytest.mark.parametrize(
    ("column", "text", "rule", "message"),
    [
        ("반입일정", "다음 주", "date_unreadable", "반입일정은 날짜 형식이어야 합니다"),
        ("반입일정", "2026-05-03 24:00", "date_unreadable", "반입일정은 날짜 형식이어야 합니다"),
        ("X좌표", "1,5", "number_unreadable", "X좌표를 숫자로 읽을 수 없습니다"),
        ("Ysize", "12m", "number_unreadable", "Ysize를 숫자로 읽을 수 없습니다"),
        ("환산비", "abc", "ratio_unreadable", "환산비를 숫자로 읽을 수 없습니다"),
        ("환산비", "-1", "ratio_not_positive", "환산비는 0보다 큰 숫자여야 합니다"),
        ("보관유무", "X", "flag", "보관유무는 Y 또는 N이어야 합니다"),
        ("동", "C9", "location_range", "동은 C1~C5, 층은 1F~6F 범위여야 합니다"),
        ("반입상태", "검토중", "status_value", "반입상태는 계획·확정·완료·지연 중 하나여야 합니다"),
    ],
)
def test_a_cell_that_cannot_fit_names_the_saving_rule(
    column: str, text: str, rule: str, message: str
) -> None:
    refused = coerce_master_cell(column, text)

    assert refused == CellParseError(column, text, rule, message)
    assert rule in {item.code for item in MASTER_RULES}


def test_an_unknown_column_is_not_coerced() -> None:
    with pytest.raises(ValueError, match="설비 마스터 계약 칸이 아닙니다"):
        coerce_master_cell("없는 칸", "1")


@pytest.mark.parametrize(
    ("column", "text"),
    [
        ("제진대일정", "2026/05/14 13:00"),
        ("제진대일정", "2026.5.14"),
        ("제진대일정", ""),
        ("제진대일정", "2026-05-14 24:00"),
        ("제진대일정", "다음 주"),
        ("X좌표", " 8 "),
        ("X좌표", "8,0"),
        ("X좌표", "8m"),
        ("환산비", ""),
        ("환산비", "0"),
        ("환산비", "1.5배"),
        ("레이아웃표시", " n "),
        ("레이아웃표시", "X"),
        ("Area Code", " mi "),
        ("동", " C1 "),
        ("동", "C9"),
        ("Qual상태", " 지연 "),
        ("Qual상태", "검토중"),
        ("공정대분류", "  B/N  "),
    ],
)
def test_coercing_a_cell_agrees_with_saving_it(column: str, text: str) -> None:
    frame = _master()
    frame.at[0, column] = text

    coerced = coerce_master_cell(column, text)

    if isinstance(coerced, CellParseError):
        with pytest.raises(ValueError) as caught:
            prepare_equipment_master(frame)
        assert str(caught.value).startswith(coerced.message)
        return
    saved = prepare_equipment_master(frame).at[0, column]
    if coerced is pd.NA:
        assert pd.isna(saved)
    else:
        assert saved == coerced
