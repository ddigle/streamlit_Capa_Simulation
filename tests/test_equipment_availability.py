# Purpose: equipment availability 관련 정상·예외·회귀 동작을 검증한다.

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.services.equipment_availability import (
    build_equipment_status_as_of,
    build_inactive_equipment,
    build_inactive_equipment_in_month,
    build_milestone_transition_events,
    build_space_equipment_status,
    build_weekly_equipment_availability,
    inactive_equipment_moments,
)
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_COLUMNS,
    empty_downtime_schedule,
    empty_equipment_master,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_master,
)

GENERATOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_sample_core_data.py"


def _baseline() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["Process-A"],
            "분류": ["전체"],
            "기존보유대수": [2],
            "비고": [None],
        }
    )


def _equipment() -> pd.DataFrame:
    defaults: dict[str, object] = {
        "공정대분류": "B/N",
        "공정소분류": "Process-A",
        "공정구분": None,
        "투자구분": "양산",
        "투자Capa": None,
        "담당자": "담당A",
        "Maker": None,
        "Model": None,
        "구분": None,
        "사용기준": None,
        "설비가동현황": None,
        "동": "C1",
        "층": "1F",
        "Xsize": 12,
        "Ysize": 7,
        "반출일정": None,
        "이설일정": None,
        "보관유무": "N",
        "기존설비여부": "N",
        "호기이력": None,
        "설비이력": None,
        "레이아웃표시": "Y",
        "확정상태": "확정",
    }
    rows = [
        {
            **defaults,
            "설비명": "EQ-01",
            "X좌표": 10,
            "Y좌표": 10,
            "제진대일정": "2026-08-01",
            "물류일정": "2026-08-03",
            "반입일정": "2026-08-04",
            "Qual일정": "2026-08-09",
        },
        {
            **defaults,
            "설비명": "EQ-02",
            "X좌표": 30,
            "Y좌표": 10,
            "제진대일정": "2026-08-08",
            "물류일정": "2026-08-10",
            "반입일정": "2026-08-11",
            "Qual일정": "2026-08-21",
            "설비이력": "셋업 중",
        },
    ]
    return pd.DataFrame(rows, columns=EQUIPMENT_COLUMNS)


def _downtime() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "설비명": ["EQ-01"],
            "비가동유형": ["고장"],
            "시작일": ["2026-08-10"],
            "종료일": ["2026-08-20"],
            "상세사유": ["부품 교체"],
            "비고": [None],
        }
    )


def _generator_owned_counts() -> dict[str, float]:
    """합성 Core Data 생성기가 공정마다 적는 `설비보유`(`ProcessSpec.owned`)."""
    name = "generate_sample_core_data_for_equipment_sample"
    spec = importlib.util.spec_from_file_location(name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return {process.name: float(process.owned) for process in module.PROCESS_SPECS}


def test_sample_baseline_matches_development_process_sample() -> None:
    """설비 샘플 보유대수는 생성기 값과 같아야 한다 — 갈라지면 빈 설비 DB 의 GAP 이 부푼다.

    기대값은 생성기에서 읽는다. 행 수나 특정 공정의 대수를 숫자로 못박지 않는다.
    """
    result = sample_equipment_baseline()
    expected = _generator_owned_counts()

    assert result["분류"].unique().tolist() == ["전체"]
    assert result["공정"].tolist() == list(expected)
    assert dict(zip(result["공정"], result["기존보유대수"], strict=True)) == expected


def test_sample_units_cover_every_active_status() -> None:
    anchor = date(2026, 8, 31)
    equipment = sample_equipment_master(anchor_date=anchor)
    downtime = sample_downtime_schedule(anchor_date=anchor)

    result = build_space_equipment_status(equipment, downtime, as_of=anchor)

    # 대수는 표본 고유 수치라 못박지 않는다. 검사할 것은 **상태 색이 하나도 빠지지 않는가**다.
    assert set(result["상태"]) == {
        "입고 예정",
        "셋업 진행중",
        "가용",
        "반출 예정",
        "이설 예정",
        "보관 설비",
        "운영 비가동",
    }
    assert equipment["구분"].unique().tolist() == ["임시 샘플"]
    # 비가동 호기는 모두 마스터에 있어야 한다. 없으면 검증이 프레임 전체를 거부한다.
    assert set(downtime["설비명"]) <= set(equipment["설비명"])
    assert set(equipment["확정상태"].dropna()) == {"계획", "확정", "완료", "지연"}


def test_sample_fleet_spreads_across_floors_so_the_layout_is_readable() -> None:
    """한 층에 두 대가 서 있으면 배치도가 아니라 점 두 개다."""
    equipment = sample_equipment_master(anchor_date=date(2026, 8, 31))

    floors = equipment[["동", "층"]].drop_duplicates()

    assert len(floors) >= 4
    assert equipment["동"].nunique() >= 3
    assert equipment.groupby(["동", "층"]).size().min() >= 4


def test_weekly_counts_use_qual_and_downtime() -> None:
    result = build_weekly_equipment_availability(
        _baseline(),
        _equipment(),
        _downtime(),
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 16),
    )

    assert result["Weeknum"].tolist() == ["26-W32", "26-W33"]
    assert result["총대수"].tolist() == [3, 4]
    assert result["가용대수"].tolist() == [3, 2]
    assert result["셋업중대수"].tolist() == [0, 1]
    assert result["운영비가동대수"].tolist() == [0, 1]
    assert result["비가동대수"].tolist() == [0, 2]


def test_weekly_counts_prepare_equipment_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from capa_simulation.services import equipment_availability

    prepare_calls = 0
    original_prepare = equipment_availability.prepare_equipment_master

    def counted_prepare(data: pd.DataFrame) -> pd.DataFrame:
        nonlocal prepare_calls
        prepare_calls += 1
        return original_prepare(data)

    monkeypatch.setattr(equipment_availability, "prepare_equipment_master", counted_prepare)

    build_weekly_equipment_availability(
        _baseline(),
        _equipment(),
        _downtime(),
        start_date=date(2026, 8, 3),
        end_date=date(2026, 9, 6),
    )

    assert prepare_calls == 1


def test_status_shows_setup_and_downtime_override() -> None:
    result = build_equipment_status_as_of(
        _equipment(),
        _downtime(),
        as_of=date(2026, 8, 16),
    )

    assert result["상태"].tolist() == ["운영 비가동", "셋업 진행중"]
    assert result["보유여부"].tolist() == [True, True]
    assert result["가용여부"].tolist() == [False, False]
    assert result.loc[0, "비가동유형"] == "고장"


def test_removal_excludes_owned_available_and_layout_from_effective_date() -> None:
    equipment = _equipment().iloc[[0]].copy()
    equipment.loc[:, "반출일정"] = "2026-08-18"

    planned = build_equipment_status_as_of(
        equipment, _downtime().iloc[0:0], as_of=date(2026, 8, 17)
    )
    completed = build_equipment_status_as_of(
        equipment, _downtime().iloc[0:0], as_of=date(2026, 8, 18)
    )

    assert planned.loc[0, "상태"] == "반출 예정"
    assert planned.loc[0, "가용여부"]
    assert completed.loc[0, "상태"] == "반출 완료"
    assert not completed.loc[0, "보유여부"]
    assert not completed.loc[0, "레이아웃반영여부"]


def test_storage_and_existing_equipment_do_not_require_arrival_or_qual() -> None:
    equipment = _equipment()
    equipment.loc[0, ["반입일정", "Qual일정"]] = None
    equipment.loc[0, "기존설비여부"] = "Y"
    equipment.loc[0, "확정상태"] = None
    equipment.loc[1, ["반입일정", "Qual일정"]] = None
    equipment.loc[1, "보관유무"] = "Y"
    equipment.loc[1, "확정상태"] = None

    prepared = prepare_equipment_master(equipment)
    status = build_equipment_status_as_of(prepared, _downtime().iloc[0:0], as_of=date(2026, 8, 16))

    assert status["상태"].tolist() == ["가용", "보관 설비"]
    assert status["가용여부"].tolist() == [True, False]


def test_transition_events_include_completed_and_planned_stages() -> None:
    result = build_milestone_transition_events(
        _equipment(),
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 11),
        as_of=date(2026, 8, 8),
    )

    assert set(result["전환단계"]) == {"물류", "입고", "제진대", "Qual"}
    assert result["일정상태"].value_counts().to_dict() == {"완료": 3, "예정": 3}
    qual = result.loc[result["설비명"].eq("EQ-01") & result["전환단계"].eq("Qual")].iloc[0]
    assert qual["이전단계"] == "입고"
    assert qual["확정상태"] == "확정"
    assert qual["기준일대비"] == "D-1"


def test_inactive_equipment_includes_setup_and_operational_downtime() -> None:
    result = build_inactive_equipment(
        _equipment(),
        _downtime(),
        as_of=date(2026, 8, 16),
    )

    assert result["설비명"].tolist() == ["EQ-01", "EQ-02"]
    assert result["상태"].tolist() == ["운영 비가동", "셋업 진행중"]


def test_new_equipment_may_leave_arrival_and_qual_blank() -> None:
    """반입·Qual 일정은 비워도 저장된다(2026-10-06 사용자 결정). 상태 뜻은 그대로다 — 반입이 비면
    입고 예정, 반입만 있고 Qual 이 비면 셋업 진행중에 머물러 가용대수에 들지 않는다."""
    equipment = _equipment()
    equipment.loc[0, ["반입일정", "Qual일정", "확정상태"]] = None
    equipment.loc[0, ["제진대일정", "물류일정"]] = None
    equipment.loc[1, ["Qual일정", "확정상태"]] = None

    prepared = prepare_equipment_master(equipment)
    status = build_equipment_status_as_of(prepared, _downtime().iloc[0:0], as_of=date(2030, 1, 1))

    assert status["상태"].tolist() == ["입고 예정", "셋업 진행중"]
    assert status["가용여부"].tolist() == [False, False]
    assert status["보유여부"].tolist() == [False, True]


def test_confirmation_is_required_only_when_a_qual_date_is_present() -> None:
    equipment = _equipment()
    equipment.loc[0, "확정상태"] = None

    with pytest.raises(ValueError, match="Qual일정이 있는 호기.*확정상태가 필수.*EQ-01"):
        prepare_equipment_master(equipment)

    equipment.loc[0, "Qual일정"] = None
    assert pd.isna(prepare_equipment_master(equipment).loc[0, "확정상태"])
    # Qual 없이 고른 확정상태도 받는다.
    equipment.loc[1, "Qual일정"] = None
    assert prepare_equipment_master(equipment).loc[1, "확정상태"] == "확정"


def test_order_checks_still_apply_when_both_dates_exist() -> None:
    equipment = _equipment()
    equipment.loc[0, "Qual일정"] = "2026-08-01"

    with pytest.raises(ValueError, match="일정 순서"):
        prepare_equipment_master(equipment)

    # 반입을 비우면 Qual 은 그 앞의 있는 날짜(물류 08-03)와 견준다.
    equipment.loc[0, "반입일정"] = None
    with pytest.raises(ValueError, match="일정 순서"):
        prepare_equipment_master(equipment)
    equipment.loc[0, "Qual일정"] = "2026-08-05"
    assert prepare_equipment_master(equipment).loc[0, "Qual일정"] == pd.Timestamp("2026-08-05")


def test_qual_confirmation_status_does_not_change_availability() -> None:
    equipment = _equipment().iloc[[0]].copy()
    equipment.loc[:, "확정상태"] = "지연"

    result = build_equipment_status_as_of(
        equipment,
        _downtime().iloc[0:0],
        as_of=date(2026, 8, 16),
    )

    assert result.loc[0, "가용여부"]
    assert result.loc[0, "확정상태"] == "지연"


def test_equipment_rejects_unknown_qual_confirmation_status() -> None:
    equipment = _equipment()
    equipment.loc[0, "확정상태"] = "검토중"

    with pytest.raises(ValueError, match="계획·확정·완료·지연"):
        prepare_equipment_master(equipment)


def test_equipment_rejects_both_removal_and_relocation() -> None:
    equipment = _equipment()
    equipment.loc[0, "반출일정"] = "2026-09-01"
    equipment.loc[0, "이설일정"] = "2026-09-02"

    with pytest.raises(ValueError, match="동시에"):
        prepare_equipment_master(equipment)


def test_downtime_rejects_duplicate_natural_key() -> None:
    downtime = pd.concat([_downtime(), _downtime()], ignore_index=True)

    with pytest.raises(ValueError, match="중복"):
        prepare_downtime_schedule(downtime, equipment=_equipment())


def test_downtime_rejects_unknown_equipment() -> None:
    downtime = _downtime()
    downtime.loc[0, "설비명"] = "UNKNOWN"

    with pytest.raises(ValueError, match="없는 설비"):
        prepare_downtime_schedule(downtime, equipment=_equipment())


def test_cached_weekly_availability_matches_direct_call() -> None:
    """캐시 래퍼가 원 계산과 같은 값을 돌려주는지 고정한다.

    `st.cache_data` 는 DataFrame 인자를 내용으로 해시하므로 리비전과 4개 화면 필터가
    이미 반영된 프레임을 넘기면 키가 저절로 맞는다. 그 전제가 깨지면 여기서 걸린다.
    """
    from capa_simulation.services.simulation_cache import get_weekly_equipment_availability

    baseline, equipment, downtime = _baseline(), _equipment(), _downtime()
    window = {"start_date": date(2026, 9, 1), "end_date": date(2026, 10, 31)}

    expected = build_weekly_equipment_availability(baseline, equipment, downtime, **window)
    cached = get_weekly_equipment_availability(baseline, equipment, downtime, **window)

    pd.testing.assert_frame_equal(cached, expected)

    # 화면 필터가 바뀌면(= 프레임 내용이 바뀌면) 캐시가 아니라 새 결과가 나와야 한다.
    narrowed = equipment.loc[equipment["설비명"].eq("EQ-01")].copy()
    assert not get_weekly_equipment_availability(baseline, narrowed, downtime, **window).equals(
        cached
    )


def _october_fleet() -> tuple[pd.DataFrame, pd.DataFrame]:
    """2026년 10월 fleet. 1일이 목요일이라 그 달의 일요일은 4·11·18·25일뿐이다.

    - `EQ-WEEKDAY` 는 월요일에 시작해 토요일에 끝나는 비가동이다. 일요일 표본 사이에 숨는다.
    - `EQ-REMOVAL` 은 셋업 중인데 반출일정이 적혀 있어 상태가 내내 「반출 예정」이다.
      이름으로 고르는 집계도, 상태 이름으로 묶은 생애주기 구간도 이 호기를 잃는다.
    - `EQ-CARRY` 는 9월에 시작해 10월 초에 끝난다. 월초 시점이 잡아야 한다.
    - `EQ-NEIGHBOR` 는 11월에만 비가동이다. 10월에는 빠져야 한다.
    """
    template = {
        **_equipment().iloc[0].to_dict(),
        "기존설비여부": "Y",
        "제진대일정": None,
        "물류일정": None,
        "반입일정": None,
        "Qual일정": None,
        "확정상태": None,
    }
    rows = [
        {**template, "설비명": "EQ-WEEKDAY"},
        {**template, "설비명": "EQ-CARRY"},
        {**template, "설비명": "EQ-NEIGHBOR"},
        {
            **template,
            "설비명": "EQ-REMOVAL",
            "기존설비여부": "N",
            "반입일정": "2026-10-05",
            "Qual일정": "2026-10-09",
            "반출일정": "2026-11-30",
            "확정상태": "계획",
        },
    ]
    equipment = pd.DataFrame(rows, columns=EQUIPMENT_COLUMNS)
    downtime = pd.DataFrame(
        {
            "설비명": ["EQ-WEEKDAY", "EQ-CARRY", "EQ-NEIGHBOR"],
            "비가동유형": ["고장", "고장", "고장"],
            "시작일": ["2026-10-05", "2026-09-28", "2026-11-02"],
            "종료일": ["2026-10-10", "2026-10-02", "2026-11-06"],
            "상세사유": [None, None, None],
            "비고": [None, None, None],
        }
    )
    return equipment, downtime


def _sunday_union(equipment: pd.DataFrame, downtime: pd.DataFrame) -> set[str]:
    """그 달의 일요일만 재었을 때 잡히는 호기. 주차별 집계가 보던 시점이다."""
    units: set[str] = set()
    for day in (4, 11, 18, 25):
        frame = build_inactive_equipment(equipment, downtime, as_of=date(2026, 10, day))
        units |= {str(unit) for unit in frame["설비명"]}
    return units


def test_month_view_catches_a_weekday_downtime_the_sunday_samples_miss() -> None:
    """10-05(월)~10-10(토) 비가동은 일요일 표본 둘(4·11일) 사이에 통째로 숨는다."""
    equipment, downtime = _october_fleet()

    result = build_inactive_equipment_in_month(equipment, downtime, month=date(2026, 10, 15))

    assert "EQ-WEEKDAY" in set(result["설비명"])
    assert "EQ-WEEKDAY" not in _sunday_union(equipment, downtime)


def test_month_view_catches_a_setup_unit_whose_status_name_is_masked_by_removal() -> None:
    """반출일정이 적히면 입고 전·셋업 중·Qual 후가 모두 「반출 예정」 한 이름이다.

    그래서 상태 이름 화이트리스트도, 상태 이름으로 묶은 생애주기 구간의 시작일도 이 호기의
    셋업 구간(10-05~10-08)을 알려 주지 못한다. 시점은 판정이 보는 날짜 컬럼에서 나와야 한다.
    """
    equipment, downtime = _october_fleet()
    month = date(2026, 10, 15)
    moments = inactive_equipment_moments(equipment, downtime, month=month)

    result = build_inactive_equipment_in_month(equipment, downtime, month=month).set_index("설비명")

    assert "EQ-REMOVAL" in result.index
    assert result.at["EQ-REMOVAL", "상태"] == "반출 예정"
    # 이름이 그대로인 채 판정만 바뀌는 날(입고일·Qual일)이 시점에 들어 있다.
    assert {date(2026, 10, 5), date(2026, 10, 9)} <= set(moments)


def test_month_view_ignores_a_unit_that_is_idle_only_in_a_neighbouring_month() -> None:
    equipment, downtime = _october_fleet()

    units = set(
        build_inactive_equipment_in_month(equipment, downtime, month=date(2026, 10, 15))["설비명"]
    )

    assert "EQ-NEIGHBOR" not in units
    # 9월에 시작해 10월로 넘어온 비가동은 월초 시점이 잡는다.
    assert "EQ-CARRY" in units


def test_month_view_reports_the_first_and_last_moment_each_unit_was_caught() -> None:
    equipment, downtime = _october_fleet()
    month = date(2026, 10, 15)
    caught: dict[str, list[date]] = {}
    for moment in inactive_equipment_moments(equipment, downtime, month=month):
        for unit in build_inactive_equipment(equipment, downtime, as_of=moment)["설비명"]:
            caught.setdefault(str(unit), []).append(moment)

    result = build_inactive_equipment_in_month(equipment, downtime, month=month).set_index("설비명")

    assert caught
    for unit, days in caught.items():
        assert result.at[unit, "비가동 시작"] == min(days)
        assert result.at[unit, "비가동 종료"] == max(days)
    # 두 컬럼은 설비명 바로 뒤 자리다.
    columns = list(build_inactive_equipment_in_month(equipment, downtime, month=month).columns)
    at = columns.index("설비명")
    assert columns[at + 1 : at + 3] == ["비가동 시작", "비가동 종료"]


def test_month_view_matches_a_direct_union_over_the_same_moments() -> None:
    """결과는 같은 시점 집합으로 시점 표를 직접 union 한 것과 호기 집합이 같다."""
    equipment, downtime = _october_fleet()
    month = date(2026, 10, 15)
    expected: set[str] = set()
    for moment in inactive_equipment_moments(equipment, downtime, month=month):
        frame = build_inactive_equipment(equipment, downtime, as_of=moment)
        expected |= {str(unit) for unit in frame["설비명"]}

    result = build_inactive_equipment_in_month(equipment, downtime, month=month)

    assert expected
    assert {str(unit) for unit in result["설비명"]} == expected


def test_month_view_degrades_to_an_empty_table_for_an_empty_fleet() -> None:
    """호기 마스터가 비면 시점은 월초와 일요일로 줄고 결과는 같은 컬럼의 빈 표다."""
    equipment, downtime = empty_equipment_master(), empty_downtime_schedule()
    month = date(2026, 10, 15)

    result = build_inactive_equipment_in_month(equipment, downtime, month=month)

    assert result.empty
    at = list(result.columns).index("설비명")
    assert list(result.columns[at + 1 : at + 3]) == ["비가동 시작", "비가동 종료"]
    assert inactive_equipment_moments(equipment, downtime, month=month) == [
        date(2026, 10, 1),
        date(2026, 10, 4),
        date(2026, 10, 11),
        date(2026, 10, 18),
        date(2026, 10, 25),
    ]


def test_blank_arrival_does_not_hide_an_out_of_order_chain() -> None:
    """빈 일정은 건너뛰고 있는 날짜끼리 본다 — 반입이 비어도 물류가 Qual 보다 늦으면 막는다."""
    equipment = _equipment()
    equipment.loc[0, ["제진대일정", "반입일정"]] = None
    equipment.loc[0, ["물류일정", "Qual일정"]] = ["2026-12-01", "2026-10-01"]

    with pytest.raises(ValueError, match="일정 순서가 올바르지 않습니다.*EQ-01"):
        prepare_equipment_master(equipment)


def test_a_new_unit_without_arrival_cannot_have_an_exit_date() -> None:
    """들어온 적 없는 신규 설비를 내보내면 반입 없이 「반출 완료」가 되어 대수에서 사라진다."""
    for exit_column in ("반출일정", "이설일정"):
        equipment = _equipment()
        equipment.loc[0, ["제진대일정", "물류일정", "반입일정", "Qual일정", "확정상태"]] = None
        equipment.loc[0, exit_column] = "2026-09-01"

        with pytest.raises(
            ValueError,
            match=r"반입일정이 없는 신규 설비에는 반출·이설일정을 넣을 수 없습니다: \['EQ-01'\]",
        ):
            prepare_equipment_master(equipment)


def test_existing_and_stored_units_keep_the_old_date_rules() -> None:
    """기존설비·보관 설비는 반입 없이 반출하고 이웃한 둘만 차례를 본다 — 그런 저장본이 열린다."""
    equipment = _equipment()
    equipment.loc[0, ["제진대일정", "반입일정", "확정상태"]] = None
    equipment.loc[0, ["물류일정", "Qual일정", "반출일정"]] = [
        "2026-12-01",
        "2026-10-01",
        "2026-09-01",
    ]
    equipment.loc[0, "기존설비여부"] = "Y"
    equipment.loc[1, ["반입일정", "Qual일정", "확정상태"]] = None
    equipment.loc[1, "이설일정"] = "2026-09-01"
    equipment.loc[1, "보관유무"] = "Y"

    prepared = prepare_equipment_master(equipment)

    assert prepared.loc[0, "반출일정"] == pd.Timestamp("2026-09-01")
    assert prepared.loc[1, "이설일정"] == pd.Timestamp("2026-09-01")
