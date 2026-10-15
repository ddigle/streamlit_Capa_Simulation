# Purpose: 공식버전 자동 갱신의 주차 해석·후보 선택·확보율 판정·포함 공정·설정·예약 규칙을 검증한다.

"""자동 갱신의 순수 규칙(`services/auto_official_update.py`).

사용자 결정(2026-10-15): 시뮬레이션명에 `PSM` 과 `W##` 가 있는 코드만 보고, 현재 공식버전보다 큰
주차나 같은 주차의 더 늦은 새 코드를 받는다. 한 달이라도 기준 확보율(기본 80%) 미만이면 그 공정은
공정 필터 off 다. 앱이 지정 시각에 떠 있지 않았으면 따라잡지 않는다.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

import pandas as pd
import pytest

from capa_simulation.services.auto_official_update import (
    DEFAULT_CONFIG,
    MISSING_WEEK_MESSAGE,
    AutoUpdateConfig,
    MissingOfficialWeek,
    OfficialBaseline,
    ProcessMinimum,
    anchor_week_year,
    auto_off_processes,
    auto_update_memo,
    crossed_slot,
    describe_config_change,
    falls_below_threshold,
    has_keyword,
    included_after_off,
    inherited_manual_off,
    manual_run_key,
    next_scheduled_run,
    official_release_name,
    parse_week,
    percent_text,
    process_minimum_rates,
    reqb_process_names,
    resolve_official_baseline,
    scheduled_run_key,
    select_candidate,
    week_label,
    week_numbers,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("PSM W41", 41),
        ("PSM_W05_v2", 5),
        ("26W41 PSM", 41),
        ("PSM(W41)", 41),
        ("PSM-W41", 41),
        ("psm w41 계획", 41),
        ("W41 PSM W41 재적재", 41),
        # 앞에 영문자가 붙으면 낱말의 일부다.
        ("NEW41 PSM", None),
        ("PSMW41", None),
        # 뒤에 숫자가 이어지면 두 자리 주차가 아니다.
        ("PSM W415", None),
        ("PSM W4", None),
        # 주차 범위 밖.
        ("PSM W00", None),
        ("PSM W54", None),
        # 서로 다른 주차가 둘이면 하나로 정할 수 없다.
        ("PSM W40→W41", None),
        ("PSM", None),
    ],
)
def test_week_code_is_two_digits_with_a_boundary(name: str, expected: int | None) -> None:
    assert parse_week(name) == expected


def test_every_distinct_week_is_listed_in_order() -> None:
    assert week_numbers("PSM W41 · W40 · W41") == (41, 40)
    assert week_label(5) == "W05"


def test_keyword_match_ignores_case() -> None:
    assert has_keyword("2026 psm W41", "PSM")
    assert has_keyword("2026 PSM W41", " psm ")
    assert not has_keyword("2026 PSS W41", "PSM")
    assert not has_keyword("PSM W41", "  ")


@pytest.mark.parametrize(
    ("week", "anchor", "year"),
    [
        (41, date(2026, 10, 10), 2026),
        # 1월 초에 등록된 W52 는 전해 마지막 주다.
        (52, date(2027, 1, 3), 2026),
        # 12월 말에 등록된 W01 은 다음 해 첫 주다.
        (1, date(2026, 12, 30), 2027),
        (1, date(2027, 1, 4), 2027),
        # 2026 년은 53주가 있다(1월 1일이 목요일).
        (53, date(2026, 12, 31), 2026),
    ],
)
def test_week_year_follows_the_registration_time(week: int, anchor: date, year: int) -> None:
    assert anchor_week_year(week, anchor) == year


def _baseline(
    week: int = 40,
    *,
    anchor: datetime = datetime(2026, 10, 5, 9, 0),
    year: int | None = None,
) -> OfficialBaseline:
    return OfficialBaseline(
        release_no=3,
        release_name="PSM W40 (SIM-W40) 공식안",
        scenario_id="scenario",
        revision_id="revision",
        scenario_name="PSM W40 (SIM-W40)",
        week=week,
        week_year=anchor_week_year(week, anchor.date()) if year is None else year,
        anchor_at=anchor,
        week_source="시나리오명",
    )


def _resolve(**overrides: object) -> OfficialBaseline:
    values: dict[str, object] = {
        "release_no": 3,
        "release_name": "공식안",
        "scenario_id": "scenario",
        "revision_id": "revision",
        "scenario_name": "데모",
        "source_simulation_name": "데모 원천",
        "source_registered_at": datetime(2026, 10, 5, 9, 0),
        "published_at": datetime(2026, 10, 6, 8, 0),
    }
    values.update(overrides)
    return resolve_official_baseline(**values)  # type: ignore[arg-type]


def test_the_scenario_name_decides_the_official_week_first() -> None:
    baseline = _resolve(scenario_name="PSM W41 손수", source_simulation_name="PSM W40")

    assert (baseline.week, baseline.week_source) == (41, "시나리오명")
    assert baseline.anchor_at == datetime(2026, 10, 5, 9, 0)


def test_the_source_name_and_then_the_release_name_are_read_next() -> None:
    from_source = _resolve(source_simulation_name="PSM W40")
    from_release = _resolve(source_simulation_name="원천", release_name="W39 공식안")

    assert (from_source.week, from_source.week_source) == (40, "원천 시뮬레이션명")
    assert (from_release.week, from_release.week_source) == (39, "공식버전명")


def test_without_a_registration_time_the_publish_time_anchors_the_week() -> None:
    baseline = _resolve(scenario_name="PSM W52", source_registered_at=None)

    assert baseline.anchor_at == datetime(2026, 10, 6, 8, 0)
    assert baseline.key == (2026, 52)


def test_an_official_version_without_a_week_is_an_error() -> None:
    with pytest.raises(MissingOfficialWeek, match=re.escape(MISSING_WEEK_MESSAGE)):
        _resolve()


def test_an_official_name_with_two_weeks_is_an_error() -> None:
    with pytest.raises(MissingOfficialWeek, match="둘 이상"):
        _resolve(scenario_name="PSM W40→W41")


def test_the_code_tail_added_by_registration_is_not_read_as_a_week() -> None:
    """등록이 붙인 「 (코드)」 안의 `W##` 꼴은 주차가 아니다 — 원천명의 주차만 읽는다."""
    baseline = _resolve(
        scenario_name="PSM W41 (SIM_W40_A)",
        release_name="PSM W41 (SIM_W40_A) 공식안",
        source_simulation_code="SIM_W40_A",
    )

    assert (baseline.week, baseline.week_source) == (41, "시나리오명")
    assert baseline.simulation_code == "SIM_W40_A"


def _catalog(*rows: tuple[str, str, str, str]) -> pd.DataFrame:
    """(시뮬레이션명, 코드, PLAN 코드, 원천 등록시각) 행으로 목록 조회 결과(계약 5컬럼)."""
    return pd.DataFrame(
        {
            "simulation_name": [row[0] for row in rows],
            "simulation_code": [row[1] for row in rows],
            "plan_name": [f"PLAN {row[2]}" for row in rows],
            "plan_code": [row[2] for row in rows],
            "regist_data": [row[3] for row in rows],
        }
    )


def test_the_largest_week_wins_over_a_later_registration() -> None:
    catalog = _catalog(
        ("PSM W41", "SIM-W41", "P1", "2026-10-14 09:00:00"),
        ("PSM W42", "SIM-W42", "P1", "2026-10-12 09:00:00"),
        ("PSM W41 재", "SIM-W41B", "P1", "2026-10-14 10:00:00"),
    )

    selection = select_candidate(
        catalog, keyword="PSM", registered_codes=(), baseline=_baseline(40)
    )

    assert selection.chosen is not None
    assert selection.chosen.simulation_code == "SIM-W42"
    assert (selection.matched, selection.eligible, selection.newer) == (3, 3, 3)


def test_within_the_largest_week_the_latest_registration_wins() -> None:
    catalog = _catalog(
        ("PSM W41", "SIM-A", "P1", "2026-10-12 09:00:00"),
        ("PSM W41", "SIM-B", "P1", "2026-10-13 09:00:00"),
        ("PSM W41", "SIM-C", "P1", "2026-10-11 09:00:00"),
    )

    selection = select_candidate(
        catalog, keyword="PSM", registered_codes=(), baseline=_baseline(40)
    )

    assert selection.chosen is not None and selection.chosen.simulation_code == "SIM-B"


def test_the_same_week_is_taken_only_when_registered_later_than_the_official() -> None:
    catalog = _catalog(
        ("PSM W40 수정", "SIM-LATE", "P1", "2026-10-07 09:00:00"),
        ("PSM W40 옛", "SIM-EARLY", "P1", "2026-10-04 09:00:00"),
        ("PSM W39", "SIM-OLD", "P1", "2026-10-08 09:00:00"),
    )

    selection = select_candidate(
        catalog, keyword="PSM", registered_codes=(), baseline=_baseline(40)
    )

    assert selection.chosen is not None and selection.chosen.simulation_code == "SIM-LATE"
    assert selection.newer == 1


def test_registered_unsavable_unnamed_and_undated_codes_are_not_candidates() -> None:
    catalog = _catalog(
        # 이미 등록된 코드(보관본 포함 — 부르는 쪽이 넘긴다).
        ("PSM W42", "SIM-DONE", "P1", "2026-10-14 09:00:00"),
        # 키워드가 없다.
        ("PSS W43", "SIM-PSS", "P1", "2026-10-14 09:00:00"),
        # 주차가 없다.
        ("PSM 정기", "SIM-NOWEEK", "P1", "2026-10-14 09:00:00"),
        # 저장할 수 없는 코드(영문·숫자·`._-` 밖의 문자).
        ("PSM W44", "SIM W44", "P1", "2026-10-14 09:00:00"),
        # 원천 등록시각이 없다 — 상세 조회 창을 정할 수 없다.
        ("PSM W45", "SIM-W45", "P1", ""),
    )

    selection = select_candidate(
        catalog, keyword="PSM", registered_codes={"SIM-DONE"}, baseline=_baseline(40)
    )

    assert selection.chosen is None
    assert (selection.listed, selection.matched, selection.eligible) == (5, 3, 0)
    reason = selection.skip_reason("PSM", _baseline(40))
    assert reason.startswith("새 코드 없음") and "공식 v3 W40" in reason


def test_the_year_end_rollover_is_read_from_the_registration_time() -> None:
    late_december = _baseline(52, anchor=datetime(2026, 12, 24, 9, 0))
    catalog = _catalog(
        ("PSM W01", "SIM-W01", "P1", "2026-12-31 09:00:00"),
        # 지난해 W52 가 아직 목록에 남아 있다 — 번호는 크지만 옛 것이다.
        ("PSM W51", "SIM-W51-OLD", "P1", "2025-12-18 09:00:00"),
    )

    selection = select_candidate(
        catalog, keyword="PSM", registered_codes=(), baseline=late_december
    )

    assert selection.chosen is not None and selection.chosen.simulation_code == "SIM-W01"
    assert selection.chosen.key == (2027, 1)

    early_january = _baseline(1, anchor=datetime(2027, 1, 2, 9, 0))
    stale = select_candidate(
        _catalog(("PSM W52", "SIM-W52", "P1", "2026-12-24 09:00:00")),
        keyword="PSM",
        registered_codes=(),
        baseline=early_january,
    )
    assert stale.chosen is None


def test_a_code_with_several_plans_spans_every_registration_day() -> None:
    catalog = _catalog(
        ("PSM W41", "SIM-W41", "P1", "2026-10-09 09:00:00"),
        ("PSM W41", "SIM-W41", "P1", "2026-10-11 09:00:00"),
        ("PSM W41", "SIM-W41", "P2", "2026-10-13 09:00:00"),
    )

    chosen = select_candidate(
        catalog, keyword="PSM", registered_codes=(), baseline=_baseline(40)
    ).chosen

    assert chosen is not None
    assert chosen.registered_at == datetime(2026, 10, 13, 9, 0)
    assert chosen.first_registered_at == datetime(2026, 10, 9, 9, 0)
    assert (chosen.first_registered_on, chosen.last_registered_on) == (
        date(2026, 10, 9),
        date(2026, 10, 13),
    )


def _w41_official(*, anchor: datetime, code: str) -> OfficialBaseline:
    return OfficialBaseline(
        release_no=2,
        release_name=f"PSM W41 ({code}) 공식안",
        scenario_id="scenario",
        revision_id="revision",
        scenario_name=f"PSM W41 ({code})",
        week=41,
        week_year=2026,
        anchor_at=anchor,
        week_source="시나리오명",
        simulation_code=code,
    )


def test_an_old_code_loaded_again_later_is_not_a_newer_code() -> None:
    """같은 주차 옛 코드에 나중 적재 줄이 있어도 새 코드가 아니다 — 처음 생긴 시각이 잣대다."""
    official = _w41_official(anchor=datetime(2026, 10, 8, 9, 0), code="SIM-A")
    catalog = _catalog(
        ("PSM W41", "SIM-A", "P1", "2026-10-08 09:00:00"),
        ("PSM W41", "SIM-B", "P1", "2026-10-06 03:00:00"),
        ("PSM W41", "SIM-B", "P1", "2026-10-15 03:00:00"),
    )

    selection = select_candidate(
        catalog, keyword="PSM", registered_codes={"SIM-A"}, baseline=official
    )

    assert selection.chosen is None and selection.newer == 0


def test_a_visible_official_code_is_compared_by_its_first_registration() -> None:
    """공식 코드가 목록에 보이면 저장된 등록시각(그 PLAN 최신 줄) 대신 처음 생긴 시각으로 견준다."""
    official = _w41_official(anchor=datetime(2026, 10, 10, 9, 0), code="SIM-A")
    catalog = _catalog(
        ("PSM W41", "SIM-A", "P1", "2026-10-07 09:00:00"),
        ("PSM W41", "SIM-A", "P1", "2026-10-10 09:00:00"),
        ("PSM W41 수정", "SIM-C", "P1", "2026-10-08 09:00:00"),
    )

    selection = select_candidate(
        catalog, keyword="PSM", registered_codes={"SIM-A"}, baseline=official
    )

    assert selection.chosen is not None and selection.chosen.simulation_code == "SIM-C"


def test_within_a_week_the_code_that_appeared_last_wins_not_the_last_reload() -> None:
    catalog = _catalog(
        ("PSM W42", "SIM-X", "P1", "2026-10-09 09:00:00"),
        ("PSM W42", "SIM-X", "P1", "2026-10-14 09:00:00"),
        ("PSM W42", "SIM-Y", "P1", "2026-10-11 09:00:00"),
    )

    selection = select_candidate(
        catalog, keyword="PSM", registered_codes=(), baseline=_baseline(40)
    )

    assert selection.chosen is not None and selection.chosen.simulation_code == "SIM-Y"


def _rates(*rows: tuple[int, str, float | None]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [row[0] for row in rows],
            "공정": [row[1] for row in rows],
            "가용대수": [1.0 for _ in rows],
            "소요대수": [1.0 for _ in rows],
            "확보율": pd.array([row[2] for row in rows], dtype="Float64"),
        }
    )


def test_each_process_keeps_its_lowest_valid_month() -> None:
    minimums = process_minimum_rates(
        _rates(
            (202601, "A", 1.2),
            (202602, "A", 0.7),
            (202603, "A", 0.7),
            (202601, " B ", None),
            (202602, "B", 0.95),
            (202601, "C", None),
            (202602, "D", float("inf")),
        )
    )

    assert minimums == (
        # 같은 최저값이면 이른 달.
        ProcessMinimum("A", 0.7, 202602),
        ProcessMinimum("B", 0.95, 202602),
    )
    assert minimums[0].label == "확보율 70%, 26.02"


def test_the_threshold_boundary_is_strictly_below() -> None:
    assert falls_below_threshold(0.7999, 0.8)
    assert not falls_below_threshold(0.8, 0.8)
    assert not falls_below_threshold(1.5, 0.8)


def test_only_processes_that_can_sit_in_the_filter_are_turned_off() -> None:
    minimums = (
        ProcessMinimum("A", 0.5, 202601),
        ProcessMinimum("B", 0.9, 202601),
        ProcessMinimum("Z", 0.1, 202601),
    )

    off = auto_off_processes(minimums, 0.8, ("A", "B"))

    assert [item.process for item in off] == ["A"]


def test_reqb_processes_are_trimmed_unique_and_sorted() -> None:
    reqb = pd.DataFrame({"공정": [" B", "A", "B ", None, ""]})

    assert reqb_process_names(reqb) == ("A", "B")
    with pytest.raises(ValueError, match="공정 컬럼"):
        reqb_process_names(pd.DataFrame({"x": [1]}))


def test_only_manual_offs_still_present_are_inherited() -> None:
    inherited = inherited_manual_off(
        previous_processes=("A", "B", "C", "D"),
        previous_included=("A",),
        # C 는 지난 회차가 확보율로 뺀 것이라 이어받지 않는다(이번에 새로 판정한다).
        previous_auto_off=("C",),
        # D 는 새 데이터에 없다. E 는 새로 생긴 공정이라 포함된다.
        current_processes=("A", "B", "C", "E"),
    )

    assert inherited == ("B",)
    assert included_after_off(("A", "B", "C", "E"), {"C"}, inherited) == ("A", "E")


def test_the_memo_and_release_name_follow_the_manual_form() -> None:
    assert auto_update_memo(threshold=0.8, auto_off_count=2, inherited_off_count=1) == (
        "자동 갱신 · 기준 확보율 80% · off 2공정 · 이어받은 수동 off 1공정"
    )
    assert official_release_name("PSM W41 (SIM-W41)") == "PSM W41 (SIM-W41) 공식안"
    assert percent_text(0.825) == "82.5%"
    assert percent_text(1.0) == "100%"


def test_settings_are_validated_and_trimmed_to_minutes() -> None:
    config = AutoUpdateConfig(
        enabled=True, check_time=time(6, 30, 45), keyword="  PSM ", threshold=0.75
    )

    assert (config.check_time, config.keyword) == (time(6, 30), "PSM")
    assert DEFAULT_CONFIG == AutoUpdateConfig(False, time(7, 0), "PSM", 0.8)
    with pytest.raises(ValueError, match="키워드"):
        AutoUpdateConfig(True, time(7, 0), "  ", 0.8)
    with pytest.raises(ValueError, match="기준 확보율"):
        AutoUpdateConfig(True, time(7, 0), "PSM", 0.0)
    with pytest.raises(ValueError, match="기준 확보율"):
        AutoUpdateConfig(True, time(7, 0), "PSM", 2.5)
    with pytest.raises(ValueError, match="기준 확보율"):
        AutoUpdateConfig(True, time(7, 0), "PSM", float("nan"))


def test_a_settings_change_is_described_field_by_field() -> None:
    after = AutoUpdateConfig(True, time(8, 30), "PSM2", 0.75)

    assert describe_config_change(DEFAULT_CONFIG, after) == (
        "자동 갱신 끔 → 켬 · 확인 시각 07:00 → 08:30 · 키워드 PSM → PSM2 · 기준 확보율 80% → 75%"
    )
    assert describe_config_change(after, after) == "바뀐 값 없음"


def test_run_keys_claim_one_slot_per_day_and_a_new_one_per_manual_run() -> None:
    assert scheduled_run_key(date(2026, 10, 15)) == "scheduled:2026-10-15"
    now = datetime(2026, 10, 15, 9, 0, 1)
    assert manual_run_key(now, "a") != manual_run_key(now, "b")


def test_the_next_run_is_today_until_the_time_passes() -> None:
    check = time(7, 0)

    assert next_scheduled_run(datetime(2026, 10, 15, 6, 59), check) == datetime(2026, 10, 15, 7)
    assert next_scheduled_run(datetime(2026, 10, 15, 7, 0), check) == datetime(2026, 10, 15, 7)
    assert next_scheduled_run(datetime(2026, 10, 15, 7, 1), check) == datetime(2026, 10, 16, 7)


def test_a_slot_fires_only_when_the_app_was_up_across_the_check_time() -> None:
    check = time(7, 0)
    tick = timedelta(minutes=1)

    assert crossed_slot(
        datetime(2026, 10, 15, 6, 59, 30), datetime(2026, 10, 15, 7, 0, 30), check
    ) == (date(2026, 10, 15))
    # 지정 시각 뒤에 떴으면(첫 확인의 직전 시각 = 기동 시각) 따라잡지 않는다.
    started = datetime(2026, 10, 15, 7, 5)
    assert crossed_slot(started, started + tick, check) is None
    # 확인 사이가 길게 벌어졌으면(잠들었거나 멈췄으면) 그 시각에 떠 있지 않았던 것이다.
    assert crossed_slot(datetime(2026, 10, 15, 6, 0), datetime(2026, 10, 15, 7, 30), check) is None
    # 자정을 넘는 지정 시각.
    assert crossed_slot(
        datetime(2026, 10, 15, 23, 59, 30), datetime(2026, 10, 16, 0, 0, 30), time(0, 0)
    ) == date(2026, 10, 16)
    # 시계가 뒤로 갔으면 아무것도 하지 않는다.
    assert crossed_slot(datetime(2026, 10, 15, 7, 1), datetime(2026, 10, 15, 6, 59), check) is None
