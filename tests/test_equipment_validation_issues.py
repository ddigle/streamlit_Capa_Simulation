# Purpose: 설비 마스터 규칙 표를 저장 거부·칸 결과·칸 다듬기가 같은 규칙·문구로 보는지 검증한다.

"""설비 마스터 규칙 표(`equipment_validation.MASTER_RULES`)의 세 쓰임.

- `prepare_equipment_master` — 처음 걸린 규칙 하나를 지금까지와 같은 문구·예외 형으로 던진다.
- `equipment_master_issues` — 같은 표를 끝까지 보며 칸마다 결과를 낸다. 처음 막는 결과의 규칙이
  저장이 던지는 규칙이고, 그 문구는 저장 거부 문구의 앞머리다.
- `coerce_master_cell` — 칸 하나를 저장 정규화와 같은 함수로 다듬는다.

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
    assert [rule.code for rule in MASTER_RULES if rule.after_valid] == ["module_ratio_default"]


def test_an_untouched_sample_has_no_issue_and_is_not_changed() -> None:
    for frame in (_master(), _modules()):
        before = frame.copy()

        assert equipment_master_issues(frame, today=ANCHOR) == ()
        prepare_equipment_master(frame, today=ANCHOR)

        # 넘긴 표는 그대로다 — 다듬기는 늘 사본에서 한다.
        pd.testing.assert_frame_equal(frame, before)


# ------------------------------------------------------------------ 규칙마다 한 군데씩


@dataclass(frozen=True)
class _Broken:
    """한 규칙만 깨뜨린 표 — `break_` 가 표를 고치고 기대 (줄, 칸) 목록을 돌려준다."""

    rule: str
    break_: Callable[[pd.DataFrame], list[tuple[int, str]]]
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


BROKEN = {
    "공정소분류 빈 글": _Broken("required_text", _set(2, "공정소분류", " ")),
    "설비명 중복(앞뒤 공백)": _Broken("duplicate_unit", _duplicate),
    "Main 설비 = 다른 행 설비명": _Broken(
        "unit_group_collision", _collision, _modules, UnitGroupCollisionError
    ),
    "모듈 행 동이 갈림": _Broken("unit_group_mixed", _mixed_building, _modules),
    "Y/N 밖": _Broken("flag", _set(4, "레이아웃표시", "X")),
    "Y/N 빈 칸": _Broken("flag", _set(4, "보관유무", "")),
    "좌표 못 읽음": _Broken("number_unreadable", _set(2, "Y좌표", "12m")),
    "크기 천 단위 쉼표": _Broken("number_unreadable", _set(2, "Xsize", "1,2")),
    "층 범위 밖": _Broken("location_range", _set(3, "층", "7F")),
    "좌표 한쪽만": _Broken("position_pair", _set(2, "X좌표", None)),
    "크기 한쪽만": _Broken("size_pair", _set(2, "Ysize", "")),
    "좌표만 있고 크기 없음": _Broken("position_needs_size", _no_position_size),
    "레이아웃 Y 인데 동·층 없음": _Broken("layout_needs_location", _no_building_or_floor),
    "좌표 음수": _Broken("position_negative", _set(2, "Y좌표", -1)),
    "크기 0": _Broken("size_not_positive", _set(2, "Xsize", 0)),
    "캔버스 밖": _Broken("canvas_outside", _outside, canvases={("C1", "1F"): (50.0, 40.0)}),
    "환산비 못 읽음": _Broken("ratio_unreadable", _set(4, "환산비", "1.5배")),
    "환산비 0": _Broken("ratio_not_positive", _set(4, "환산비", "0")),
    "날짜 못 읽음": _Broken("date_unreadable", _set(5, "물류일정", "다음 주")),
    "시각 24:00": _Broken("date_unreadable", _set(5, "Qual실적", "2026-06-01 24:00")),
    "Qual상태 없음": _Broken("qual_status_required", _set(6, "Qual상태", None)),
    "반입상태 값 밖": _Broken("status_value", _set(6, "반입상태", "검토중")),
    "물류 < 제진대": _Broken("schedule_order", _logistics_before_vibration),
    "Qual < 반입": _Broken("schedule_order", _qual_before_arrival),
    "반입 빈 신규의 Qual < 물류": _Broken("schedule_order", _present_chain),
    "반입 없는 신규의 반출": _Broken("exit_without_arrival", _exit_without_arrival),
    "정지 > 반출/이설": _Broken("stop_after_exit", _stop_after_exit),
    "정지 < 반입": _Broken("exit_before_arrival", _exit_before_arrival),
    "실적이 오늘보다 늦음": _Broken(
        "actual_future", _set(0, "Qual실적", "2026-12-01"), today=ANCHOR
    ),
    "반입실적 > Qual실적": _Broken("actual_reversed", _actuals_reversed, today=ANCHOR),
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
    blocking = _blocking(issues)
    first = blocking[0]
    # 처음 막는 결과의 규칙 = 저장이 던진 규칙이고, 그 문구가 저장 거부 문구의 앞머리다.
    assert first.rule == case.rule
    if case.rule == "canvas_outside":
        assert str(caught.value).startswith("Space 블럭이 층 캔버스 범위를 벗어났습니다")
    else:
        assert str(caught.value).startswith(first.message)
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
    assert str(mixed.value) == "같은 Main 설비의 모듈 행은 동 이 같아야 합니다: ['GRP-1']"

    frame = _master()
    frame.at[0, "Qual실적"] = "2026-12-01"
    with pytest.raises(ValueError) as future:
        prepare_equipment_master(frame, today=ANCHOR)
    assert str(future.value) == (
        "Qual실적은 오늘(2026-10-01)보다 늦을 수 없습니다 — 실적은 이미 끝난 날을 적습니다: "
        f"['{names[0]}']"
    )


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


def test_mixed_time_zones_still_fail_where_they_failed() -> None:
    frame = _master()
    frame.at[0, "물류일정"] = "2026-05-24T00:00+09:00"
    # 시간대가 섞인 날짜 칸은 pandas 가 읽기에서 멈춘다 — 그 앞 규칙(설비명 중복)이 먼저다.
    frame.at[3, "설비명"] = frame.at[1, "설비명"]
    with pytest.raises(ValueError, match="설비명은 중복될 수 없습니다"):
        prepare_equipment_master(frame)

    frame.at[3, "설비명"] = "SAMPLE-ONLY-ONE"
    # 그 칸 차례에서 예전과 같은 pandas 예외로 멈춘다(규칙 문구가 아니다).
    with pytest.raises((AttributeError, ValueError)) as caught:
        prepare_equipment_master(frame)
    assert "날짜 형식" not in str(caught.value)
    issues = equipment_master_issues(frame)
    # 어느 값 탓인지 칸 전체로는 알 수 없어 그 칸의 찬 줄 모두에 단다.
    assert {issue.rule for issue in issues} == {"date_unreadable"}
    assert {issue.column for issue in issues} == {"물류일정"}
    assert len(issues) == int(frame["물류일정"].notna().sum())


def test_a_time_zoned_date_column_is_unreadable_for_cells() -> None:
    frame = _master()
    frame["Qual실적"] = None
    frame.at[0, "Qual실적"] = "2026-06-30T00:00+09:00"

    issues = equipment_master_issues(frame, today=ANCHOR)

    # 칸 결과는 시간대 붙은 칸을 견주지 않고 못 읽은 날짜로 본다 — `coerce_master_cell` 과 같다.
    assert [(issue.rule, issue.position, issue.column) for issue in issues] == [
        ("date_unreadable", 0, "Qual실적")
    ]
    assert isinstance(coerce_master_cell("Qual실적", "2026-06-30T00:00+09:00"), CellParseError)


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
    # 막는 결과가 남은 표에서는 묶음 키를 믿을 수 없어 건너뛴다(지금 화면과 같다).
    frame.at[4, "레이아웃표시"] = "X"
    assert "module_ratio_default" not in {issue.rule for issue in equipment_master_issues(frame)}


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
