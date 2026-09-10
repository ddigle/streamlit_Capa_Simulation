# Purpose: equipment availability 관련 정상·예외·회귀 동작을 검증한다.

from datetime import date

import pandas as pd
import pytest

from capa_simulation.services.equipment_availability import (
    build_equipment_status_as_of,
    build_inactive_equipment,
    build_milestone_transition_events,
    build_space_equipment_status,
    build_weekly_equipment_availability,
)
from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_master,
)


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
        "라인구분": None,
        "활용구분": "양산",
        "투자기준": None,
        "담당자": "담당A",
        "Maker": None,
        "모델": None,
        "분류1": None,
        "분류2": None,
        "분류3": None,
        "동": "C1",
        "층": "1F",
        "Xsize": 12,
        "Ysize": 7,
        "반출일정": None,
        "이설일": None,
        "장기보관여부": "N",
        "기존설비여부": "N",
        "호기이력": None,
        "비고": None,
        "레이아웃표시": "Y",
        "확정상태": "확정",
    }
    rows = [
        {
            **defaults,
            "호기": "EQ-01",
            "X좌표": 10,
            "Y좌표": 10,
            "제진대일정": "2026-08-01",
            "물류일정": "2026-08-03",
            "입고일정": "2026-08-04",
            "Qual일정": "2026-08-09",
        },
        {
            **defaults,
            "호기": "EQ-02",
            "X좌표": 30,
            "Y좌표": 10,
            "제진대일정": "2026-08-08",
            "물류일정": "2026-08-10",
            "입고일정": "2026-08-11",
            "Qual일정": "2026-08-21",
            "비고": "셋업 중",
        },
    ]
    return pd.DataFrame(rows, columns=EQUIPMENT_COLUMNS)


def _downtime() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "호기": ["EQ-01"],
            "비가동유형": ["고장"],
            "시작일": ["2026-08-10"],
            "종료일": ["2026-08-20"],
            "상세사유": ["부품 교체"],
            "비고": [None],
        }
    )


def test_sample_baseline_matches_development_process_sample() -> None:
    result = sample_equipment_baseline()

    assert len(result) == 30
    assert result["분류"].unique().tolist() == ["전체"]
    assert result.loc[result["공정"].eq("TC Bonding"), "기존보유대수"].item() == 51.0


def test_sample_units_cover_every_active_status() -> None:
    anchor = date(2026, 8, 31)
    equipment = sample_equipment_master(anchor_date=anchor)
    downtime = sample_downtime_schedule(anchor_date=anchor)

    result = build_space_equipment_status(equipment, downtime, as_of=anchor)

    assert len(result) == 7
    assert set(result["상태"]) == {
        "입고 예정",
        "셋업 진행중",
        "가용",
        "반출 예정",
        "이설 예정",
        "보관 설비",
        "운영 비가동",
    }
    assert equipment["분류1"].unique().tolist() == ["임시 샘플"]
    assert downtime.loc[0, "호기"] == "SAMPLE-DOWN-01"
    assert set(equipment["확정상태"].dropna()) == {"계획", "확정", "완료", "지연"}


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
    equipment.loc[0, ["입고일정", "Qual일정"]] = None
    equipment.loc[0, "기존설비여부"] = "Y"
    equipment.loc[0, "확정상태"] = None
    equipment.loc[1, ["입고일정", "Qual일정"]] = None
    equipment.loc[1, "장기보관여부"] = "Y"
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
    qual = result.loc[result["호기"].eq("EQ-01") & result["전환단계"].eq("Qual")].iloc[0]
    assert qual["이전단계"] == "입고"
    assert qual["확정상태"] == "확정"
    assert qual["기준일대비"] == "D-1"


def test_inactive_equipment_includes_setup_and_operational_downtime() -> None:
    result = build_inactive_equipment(
        _equipment(),
        _downtime(),
        as_of=date(2026, 8, 16),
    )

    assert result["호기"].tolist() == ["EQ-01", "EQ-02"]
    assert result["상태"].tolist() == ["운영 비가동", "셋업 진행중"]


def test_equipment_rejects_missing_required_dates() -> None:
    equipment = _equipment()
    equipment.loc[0, "Qual일정"] = None

    with pytest.raises(ValueError, match="필수"):
        prepare_equipment_master(equipment)


def test_equipment_rejects_missing_qual_confirmation_status() -> None:
    equipment = _equipment()
    equipment.loc[0, "확정상태"] = None

    with pytest.raises(ValueError, match="확정상태"):
        prepare_equipment_master(equipment)


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
    equipment.loc[0, "이설일"] = "2026-09-02"

    with pytest.raises(ValueError, match="동시에"):
        prepare_equipment_master(equipment)


def test_downtime_rejects_duplicate_natural_key() -> None:
    downtime = pd.concat([_downtime(), _downtime()], ignore_index=True)

    with pytest.raises(ValueError, match="중복"):
        prepare_downtime_schedule(downtime, equipment=_equipment())


def test_downtime_rejects_unknown_equipment() -> None:
    downtime = _downtime()
    downtime.loc[0, "호기"] = "UNKNOWN"

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
    narrowed = equipment.loc[equipment["호기"].eq("EQ-01")].copy()
    assert not get_weekly_equipment_availability(baseline, narrowed, downtime, **window).equals(
        cached
    )
