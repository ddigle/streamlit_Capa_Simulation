# Purpose: 카탈로그 표시용 정리·검색·자동입력 기본값 규칙을 검증한다.

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from capa_simulation.components.bigdataquery_registration import _optional_datetime
from capa_simulation.services import bigdataquery_catalog_view as view


def _frame(**overrides: list[object]) -> pd.DataFrame:
    data: dict[str, list[object]] = {
        "simulation_name": ["DEMO 시뮬레이션"],
        "simulation_code": ["DEMO-A-001"],
        "plan_name": ["DEMO PLAN"],
        "plan_code": ["DEMO-PLAN-001"],
        "regist_data": ["2026-09-02 03:04:05"],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_registered_at_normalizes_timestamp_nat_number_and_z_suffix() -> None:
    """정수 등록시각이 1970년으로 저장되던 결함의 회귀선.

    `pd.to_datetime` 은 20260902030405 를 나노초로 읽는다. 숫자형은 단위를 알 수 없으니
    통째로 버린다.
    """
    assert view.format_registered_at(pd.Timestamp("2026-08-29 14:30:00")) == "2026-08-29 14:30:00"
    assert view.format_registered_at(datetime(2026, 8, 29, 14, 30)) == "2026-08-29 14:30:00"
    assert view.format_registered_at(pd.NaT) == ""
    assert view.format_registered_at(None) == ""
    assert view.format_registered_at(20260902030405) == ""
    assert view.format_registered_at(np.int64(20260902030405)) == ""
    assert view.format_registered_at("2026-08-29T14:30:00Z") == "2026-08-29 14:30:00"
    assert view.format_registered_at("뒤죽박죽") == ""
    assert view.format_registered_at("   ") == ""


def test_registered_at_output_is_accepted_by_the_save_path() -> None:
    """저장 경로가 쓰는 `datetime.fromisoformat` 은 Z 접미사를 거부한다."""
    text = view.format_registered_at("2026-08-29T14:30:00Z")

    assert _optional_datetime(text) == datetime(2026, 8, 29, 14, 30)


def test_normalize_rejects_a_missing_contract_column() -> None:
    with pytest.raises(ValueError, match="plan_name"):
        view.normalize_catalog(_frame().drop(columns=["plan_name"]))


def test_normalize_keeps_the_contract_column_names() -> None:
    normalized = view.normalize_catalog(_frame())

    assert normalized.columns.tolist() == [
        "simulation_name",
        "simulation_code",
        "plan_name",
        "plan_code",
        "regist_data",
    ]


def test_normalize_sorts_newest_first_and_empty_last() -> None:
    frame = _frame(
        simulation_name=["A", "B", "C"],
        simulation_code=["DEMO-A", "DEMO-B", "DEMO-C"],
        plan_name=["P", "P", "P"],
        plan_code=["PC-1", "PC-2", "PC-3"],
        regist_data=["2026-09-01 00:00:00", "뒤죽박죽", "2026-09-05 00:00:00"],
    )

    normalized = view.normalize_catalog(frame)

    assert normalized["simulation_code"].tolist() == ["DEMO-C", "DEMO-A", "DEMO-B"]


def test_normalize_collapses_rows_to_one_per_code_and_plan() -> None:
    """`reg_date` 가 행 단위 적재시각이면 코드 하나가 수천 행으로 펼쳐진다."""
    frame = _frame(
        simulation_name=["A", "A", "A"],
        simulation_code=["DEMO-A", "DEMO-A", "DEMO-A"],
        plan_name=["P", "P", "P"],
        plan_code=["PC-1", "PC-1", "PC-1"],
        regist_data=[
            "2026-09-01 00:00:00",
            "2026-09-03 00:00:00",
            "2026-09-02 00:00:00",
        ],
    )

    normalized = view.normalize_catalog(frame)

    assert len(normalized) == 1
    assert normalized.loc[0, "regist_data"] == "2026-09-03 00:00:00"


def test_same_code_with_different_plans_stays_as_separate_rows() -> None:
    frame = _frame(
        simulation_name=["A", "A"],
        simulation_code=["DEMO-A", "DEMO-A"],
        plan_name=["P1", "P2"],
        plan_code=["PC-1", "PC-2"],
        regist_data=["2026-09-01 00:00:00", "2026-09-01 00:00:00"],
    )

    assert len(view.normalize_catalog(frame)) == 2


def test_display_frame_marks_registration_and_savability() -> None:
    frame = _frame(
        simulation_name=["A", "B"],
        simulation_code=["DEMO-A", "DEMO 공백"],
        plan_name=["P", "P"],
        plan_code=["PC-1", "PC-2"],
        regist_data=["2026-09-02 00:00:00", "2026-09-01 00:00:00"],
    )
    normalized = view.normalize_catalog(frame)

    display = view.build_display_frame(normalized, registered_codes={"DEMO-A"})

    assert display.columns.tolist() == list(view.DISPLAY_COLUMNS)
    assert display.loc[0, "등록여부"] == view.REGISTERED_LABEL
    assert display.loc[1, "등록여부"] == view.UNREGISTERED_LABEL
    assert display.loc[0, "저장가능"] == view.SAVABLE_LABEL
    # 공백이 든 코드는 조회·저장 정규식을 통과하지 못한다.
    assert display.loc[1, "저장가능"] == view.UNSAVABLE_LABEL


def test_filter_matches_every_keyword_and_resets_positions() -> None:
    frame = _frame(
        simulation_name=["알파 시뮬", "베타 시뮬"],
        simulation_code=["DEMO-A", "DEMO-B"],
        plan_name=["PLAN-1", "PLAN-2"],
        plan_code=["PC-1", "PC-2"],
        regist_data=["2026-09-02 00:00:00", "2026-09-01 00:00:00"],
    )
    normalized = view.normalize_catalog(frame)

    filtered = view.filter_catalog(
        normalized,
        keyword="베타 pc-2",
        scope=view.SCOPE_ALL,
        registered_codes=set(),
    )

    assert filtered["simulation_code"].tolist() == ["DEMO-B"]
    assert filtered.index.tolist() == [0]


def test_filter_scope_splits_registered_rows() -> None:
    frame = _frame(
        simulation_name=["A", "B"],
        simulation_code=["DEMO-A", "DEMO-B"],
        plan_name=["P", "P"],
        plan_code=["PC-1", "PC-2"],
        regist_data=["2026-09-02 00:00:00", "2026-09-01 00:00:00"],
    )
    normalized = view.normalize_catalog(frame)

    unregistered = view.filter_catalog(
        normalized, keyword="", scope=view.SCOPE_UNREGISTERED, registered_codes={"DEMO-A"}
    )
    registered = view.filter_catalog(
        normalized, keyword="", scope=view.SCOPE_REGISTERED, registered_codes={"DEMO-A"}
    )

    assert unregistered["simulation_code"].tolist() == ["DEMO-B"]
    assert registered["simulation_code"].tolist() == ["DEMO-A"]


def test_row_position_uses_the_full_signature() -> None:
    """코드·PLAN 만으로 찾으면 등록시각만 다른 이웃 행으로 미끄러진다."""
    frame = _frame(
        simulation_name=["A", "A"],
        simulation_code=["DEMO-A", "DEMO-A"],
        plan_name=["P", "P"],
        plan_code=["PC-1", "PC-2"],
        regist_data=["2026-09-01 00:00:00", "2026-09-03 00:00:00"],
    )
    normalized = view.normalize_catalog(frame)
    second = view.catalog_row_at(normalized, 1)

    assert second is not None
    assert view.row_position(normalized, second.signature) == 1
    assert view.row_position(normalized, "없는|서명|값") is None


def test_catalog_row_at_rejects_out_of_range_positions() -> None:
    normalized = view.normalize_catalog(_frame())

    assert view.catalog_row_at(normalized, -1) is None
    assert view.catalog_row_at(normalized, 5) is None


def test_prefill_never_leaves_a_required_field_empty() -> None:
    """`ScenarioCreate` 와 `CoreDataBatch` 가 빈 이름을 거부한다."""
    row = view.CatalogRow(
        simulation_code="DEMO-A-001",
        simulation_name="   ",
        plan_code="DEMO-PLAN-001",
        plan_name="DEMO PLAN",
        registered_at="",
        savable=True,
    )

    prefill = view.registration_prefill(
        row,
        catalog_window_label="2026-09-01 ~ 2026-09-08",
    )

    assert prefill.source_name == "DEMO-A-001"
    assert prefill.scenario_name == "DEMO-A-001 (DEMO-A-001)"
    assert prefill.revision_name == "초기 리비전"
    assert "DEMO PLAN(DEMO-PLAN-001)" in prefill.note
    assert "2026-09-01 ~ 2026-09-08" in prefill.note


def test_view_token_is_stable_across_calls() -> None:
    """내장 `hash()` 는 프로세스마다 값이 달라 위젯 key 에 쓸 수 없다."""
    assert view.view_token("a", "b") == view.view_token("a", "b")
    assert view.view_token("a", "b") != view.view_token("b", "a")


def test_the_code_registration_span_ignores_the_plan() -> None:
    """상세 조회는 PLAN 을 가리지 않고 코드 전체를 받는다.

    그래서 기본 창도 그 코드의 모든 PLAN 줄 등록일을 덮는다.
    """
    frame = pd.DataFrame(
        {
            "simulation_name": ["알파", "알파", "베타"],
            "simulation_code": ["DEMO-A", "DEMO-A", "DEMO-B"],
            "plan_name": ["P", "Q", "R"],
            "plan_code": ["P1", "Q1", "R1"],
            "regist_data": [
                "2026-03-10 00:00:00",
                "2026-04-02 09:00:00",
                "2026-01-01 00:00:00",
            ],
        }
    )
    catalog = view.normalize_catalog(frame)
    first = {("DEMO-A", "P1"): date(2026, 3, 1), ("DEMO-B", "R1"): date(2025, 12, 1)}

    assert view.code_registration_span(catalog, first, "DEMO-A") == (
        date(2026, 3, 1),
        date(2026, 4, 2),
    )
    assert view.code_registration_span(catalog, {}, "DEMO-A") == (
        date(2026, 3, 10),
        date(2026, 4, 2),
    )
    assert view.code_registration_span(catalog, first, "DEMO-Z") is None


def test_first_registration_dates_keep_the_earliest_day_per_code_and_plan() -> None:
    """정리는 최신 1행만 남기지만 상세 조회 창은 가장 이른 적재부터 덮어야 한다."""
    frame = pd.DataFrame(
        {
            "simulation_name": ["알파", "알파", "알파", "베타"],
            "simulation_code": ["DEMO-A", "DEMO-A", "DEMO-A", "DEMO-B"],
            "plan_name": ["P", "P", "P", "Q"],
            "plan_code": ["P1", "P1", "P1", "Q1"],
            "regist_data": [
                "2026-09-02 03:04:05",
                "2026-03-01 00:00:00",
                "읽을 수 없음",
                "2026-08-15 10:00:00",
            ],
        }
    )

    earliest = view.first_registration_dates(frame)

    assert earliest == {("DEMO-A", "P1"): date(2026, 3, 1), ("DEMO-B", "Q1"): date(2026, 8, 15)}
    assert view.normalize_catalog(frame).loc[0, "regist_data"] == "2026-09-02 03:04:05"
